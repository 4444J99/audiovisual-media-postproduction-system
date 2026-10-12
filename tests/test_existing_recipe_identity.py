"""A completed render must not authenticate changed source or production code."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.recovery import run_existing_recipe as runner
from tools.recovery import validate_existing_recipe as validator


class ExistingRecipeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        (self.repo / 'recipe.py').write_text('original recipe\n')
        self.git('add', 'recipe.py')
        self.git('commit', '-qm', 'fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        self.source = self.root / 'source.mp4'
        self.source.write_bytes(b'original source fixture')
        self.source_hash = runner.sha256(self.source)
        self.output, self.evidence = self.root / 'output', self.root / 'evidence'

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True)

    def execute(self, mutation=None):
        real_run = subprocess.run
        def run(command, **kwargs):
            if command[0] != sys.executable:
                return real_run(command, **kwargs)
            if command[1] == 'tools/finish_production.py' and mutation:
                mutation()
            return subprocess.CompletedProcess(command, 0)
        args = ['run-existing-recipe', '--repo', str(self.repo), '--source', str(self.source),
                '--output', str(self.output), '--evidence', str(self.evidence)]
        with patch.object(runner, 'PINNED_COMMIT', self.commit), \
                patch.object(runner, 'EXPECTED_SOURCE_SHA256', self.source_hash), \
                patch.object(sys, 'argv', args), \
                patch.object(runner.importlib.metadata, 'version', return_value='fixture'), \
                patch.object(runner.subprocess, 'run', side_effect=run), patch('builtins.print'):
            code = runner.main()
        return code, json.loads((self.evidence / 'execution-receipt.json').read_text())

    def validate_receipt(self, receipt):
        with patch.object(validator, 'PINNED_COMMIT', self.commit), \
                patch.object(validator, 'EXPECTED_SOURCE_SHA256', self.source_hash):
            validator.verify_execution_identity(receipt, self.repo)

    def test_clean_run_retains_independent_final_identities(self):
        code, receipt = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(receipt['status'], 'recipe_completed_validation_pending')
        self.assertEqual(receipt['tracked_file_sha256_final'], receipt['tracked_file_sha256'])
        self.assertEqual(receipt['source_sha256_final'], self.source_hash)
        self.validate_receipt(receipt)

    def test_source_mutation_blocks_completed_status_even_when_commands_succeed(self):
        code, receipt = self.execute(lambda: self.source.write_bytes(b'changed source'))
        self.assertEqual(code, 1)
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(receipt['failed_step'], 'final_input_identity')
        self.assertFalse(receipt['source_unchanged'])
        with self.assertRaises(SystemExit):
            self.validate_receipt(receipt)

    def test_deleted_source_produces_failed_receipt(self):
        code, receipt = self.execute(self.source.unlink)
        self.assertEqual(code, 1)
        self.assertEqual(receipt['status'], 'failed')
        self.assertIn('source_unavailable', receipt['identity_check_errors'])

    def test_tracked_mutation_fails_even_if_committed_to_clean_worktree(self):
        def mutate():
            (self.repo / 'recipe.py').write_text('changed recipe\n')
            self.git('add', 'recipe.py')
            self.git('commit', '-qm', 'mutation during execution')
        code, receipt = self.execute(mutate)
        self.assertEqual(code, 1)
        self.assertTrue(receipt['worktree_finally_clean'])
        self.assertFalse(receipt['tracked_files_unchanged'])
        self.assertFalse(receipt['revision_unchanged'])
        self.assertTrue(receipt['code_modified'])

    def test_untracked_dirty_worktree_blocks_completion(self):
        code, receipt = self.execute(lambda: (self.repo / 'scratch.txt').write_text('untracked output'))
        self.assertEqual(code, 1)
        self.assertTrue(receipt['tracked_files_unchanged'])
        self.assertFalse(receipt['worktree_finally_clean'])

    def test_missing_tracked_file_is_failed_identity_not_running_receipt(self):
        code, receipt = self.execute(lambda: (self.repo / 'recipe.py').unlink())
        self.assertEqual(code, 1)
        self.assertEqual(receipt['status'], 'failed')
        self.assertIn('tracked_files_unavailable', receipt['identity_check_errors'])

    def test_validator_rejects_legacy_false_or_inconsistent_completed_claims(self):
        _, receipt = self.execute()
        cases = [{'source_unchanged': False}, {'worktree_finally_clean': False},
                 {'tracked_files_unchanged': False}, {'source_sha256_final': '0' * 64},
                 {'tracked_file_sha256_final': {'recipe.py': '0' * 64}},
                 {'commit_final': '0' * 40}, {'execution_inputs_unchanged': None}]
        for mutation in cases:
            with self.subTest(mutation=mutation), self.assertRaises(SystemExit):
                self.validate_receipt({**copy.deepcopy(receipt), **mutation})
        del receipt['tracked_files_unchanged']
        with self.assertRaises(SystemExit):
            self.validate_receipt(receipt)

    def test_validator_rechecks_repository_after_execution(self):
        _, receipt = self.execute()
        (self.repo / 'recipe.py').write_text('changed after execution\n')
        with self.assertRaisesRegex(SystemExit, 'Repository changed'):
            self.validate_receipt(receipt)


if __name__ == '__main__':
    unittest.main()
