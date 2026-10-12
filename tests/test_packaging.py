"""Exercise the distributed adapters from a wheel, outside the source checkout."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from amp.media_resolver import ContractError
from amp.runtime import runtime_path


ROOT = Path(__file__).resolve().parents[1]


class RuntimeLocationTests(unittest.TestCase):
    def test_checkout_preserves_existing_locations(self):
        self.assertEqual(runtime_path(ROOT, 'tools/render-fx.mjs'), ROOT/'tools/render-fx.mjs')
        self.assertEqual(runtime_path(ROOT, 'amp/core.py'), ROOT/'amp/core.py')

    def test_installed_producers_never_fall_back_to_unrelated_siblings(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'amp/_runtime').mkdir(parents=True)
            (root/'tools').mkdir();(root/'tools/render-fx.mjs').write_text('unrelated installation')
            self.assertEqual(runtime_path(root,'tools/render-fx.mjs'),root/'amp/_runtime/tools/render-fx.mjs')
            self.assertFalse(runtime_path(root,'tools/render-fx.mjs').exists())
            self.assertEqual(runtime_path(root,'amp/core.py'),root/'amp/core.py')

    def test_runtime_location_rejects_escaping_logical_paths(self):
        for path in ('../tools/render-fx.mjs','/tools/render-fx.mjs'):
            with self.subTest(path=path),self.assertRaises(ContractError):runtime_path(ROOT,path)


class InstalledWheelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='amp-wheel-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root=Path(cls.temporary.name)
        source=cls.root/'source';source.mkdir()
        cls.runtime_files=[line.split(' ',1)[1] for line in (ROOT/'MANIFEST.in').read_text().splitlines()
                           if line.startswith('include ')]
        for relative in ['pyproject.toml','setup.py','MANIFEST.in','README.md',*cls.runtime_files]:
            destination=source/relative;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/relative,destination)
        shutil.copytree(ROOT/'amp',source/'amp',ignore=shutil.ignore_patterns('__pycache__','*.pyc','_runtime'))
        cls.environment=os.environ.copy()
        cls.environment.pop('PYTHONPATH',None);cls.environment.pop('PYTHONHOME',None)
        if not cls.environment.get('AMP_NODE_MODULES'):
            modules=cls.environment.get('CODEX_PRIMARY_RUNTIME_NODE_MODULES') or str(ROOT/'node_modules')
            cls.environment['AMP_NODE_MODULES']=modules
        # The ordinary installed-runtime override must work without Codex's one.
        cls.environment.pop('CODEX_PRIMARY_RUNTIME_NODE_MODULES',None)
        cls.run_command([sys.executable,'setup.py','sdist','--dist-dir',str(cls.root/'dist')],source)
        sdist=next((cls.root/'dist').glob('*.tar.gz'))
        cls.run_command([sys.executable,'-m','pip','wheel','--no-index','--no-deps','--no-build-isolation',
                         '--wheel-dir',str(cls.root/'wheel'),str(sdist)],cls.root)
        cls.wheel=next((cls.root/'wheel').glob('*.whl'))
        cls.run_command([sys.executable,'-m','venv','--system-site-packages',str(cls.root/'environment')],cls.root)
        cls.python=cls.root/'environment/bin/python'
        cls.run_command([str(cls.python),'-m','pip','install','--no-index','--no-deps',str(cls.wheel)],cls.root)
        cls.consumer=cls.root/'consumer';cls.consumer.mkdir()
        cls.probe=cls.consumer/'probe.py';shutil.copyfile(ROOT/'tests/wheel_preflight_probe.py',cls.probe)

    @classmethod
    def run_command(cls,argv,cwd):
        result=subprocess.run(argv,cwd=cwd,env=cls.environment,text=True,capture_output=True,timeout=180)
        if result.returncode:raise AssertionError(f'{argv[:4]} failed:\n{result.stdout}\n{result.stderr}')
        return result

    def test_wheel_contains_only_the_exact_public_runtime_asset_closure(self):
        with zipfile.ZipFile(self.wheel) as archive:
            names=set(archive.namelist())
        self.assertEqual({name for name in names if name.startswith('amp/_runtime/')},
                         {'amp/_runtime/'+name for name in self.runtime_files})
        self.assertFalse(any(name.endswith(('.mp4','.wav','.flac','.ttf','.woff','.xlsx')) for name in names))

    def test_installed_wheel_preflights_both_adapters_and_executes_complete_fx_pack(self):
        result=self.run_command([str(self.python),'-I',str(self.probe),str(self.consumer)],self.consumer)
        receipt=json.loads(result.stdout)
        self.assertTrue(Path(receipt['package']).is_relative_to(self.root/'environment'))
        self.assertEqual(receipt['adapters'],['fx.rack.v1','amp.roomstretch.v1'])
        self.assertEqual(receipt['fx_frames'],12)
        self.assertEqual(receipt['room_samples'],48000)
        self.assertTrue(receipt['all_code_identities_match_installed_bytes'])
        self.assertTrue(receipt['missing_producer_rejected'])
        self.assertTrue(receipt['fx_render_verified'])
        self.assertTrue(receipt['complete_asset_pack_staged'])
        self.assertTrue(receipt['asset_dependency_failures_rejected'])
