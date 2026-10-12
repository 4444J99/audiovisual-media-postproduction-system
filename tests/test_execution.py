"""Contract checks use inert local bytes and native validators, never a film render."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from unittest.mock import patch

from amp.execution import (ADAPTERS, ContractError, ExecutionPlan, REPO_ROOT, code_provenance,
                           command_output, decode_audio, direction_clock, execute, expected_products,
                           preflight, presentation_clock, revision_clock, room_clock, room_output_identities,
                           runtime_dependencies, stage_inputs, verify_products)
from amp.media_resolver import MediaResolver, file_identity, read_json

SOURCE_HASH = "bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225"
CLOCK = {"sha256": SOURCE_HASH, "frame_rate": {"num": 30, "den": 1}, "frames": 3360}


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "private-original.bin"
        self.input.write_bytes(b"verified original\x00\xff")
        self.ref = file_identity(self.input, "source")
        self.locations = {"objects": {self.ref["sha256"]: str(self.input)}}

    def tearDown(self):
        self.temp.cleanup()

    def test_all_existing_inventory_shapes_supply_the_same_identity(self):
        for document in ([self.ref], {"objects": [self.ref]}, {"files": [self.ref]}, {"sources": [self.ref]}):
            with self.subTest(document=type(document)):
                resolver = MediaResolver(self.root, self.locations, [document])
                result = resolver.resolve({"sha256": self.ref["sha256"]}, "source")
                self.assertEqual(result, self.input)
                self.assertNotIn(str(self.input), json.dumps(resolver.records))

    def test_conflicting_index_size_is_not_silently_deduplicated(self):
        with self.assertRaisesRegex(ContractError, "inventory_binding_conflict"):
            MediaResolver(self.root, self.locations, [{"files": [self.ref, {**self.ref, "bytes": self.ref["bytes"] + 1}]}])

    def test_hash_mismatch_does_not_print_private_path(self):
        self.input.write_bytes(b"changed")
        with self.assertRaises(ContractError) as raised:
            MediaResolver(self.root, self.locations).resolve(self.ref, "source")
        self.assertEqual(raised.exception.code, "input_identity_mismatch")
        self.assertNotIn(str(self.input), str(raised.exception))

    def test_two_distinct_identical_locations_require_owner_choice(self):
        other = self.root / "identical-copy.bin"
        other.write_bytes(self.input.read_bytes())
        self.locations["objects"][self.ref["sha256"]] = [str(self.input), str(other)]
        with self.assertRaisesRegex(ContractError, "ambiguous_locations"):
            MediaResolver(self.root, self.locations).resolve(self.ref, "source")

    def test_repeated_same_location_is_not_ambiguous(self):
        self.locations["objects"][self.ref["sha256"]] = [str(self.input), str(self.input)]
        self.assertEqual(MediaResolver(self.root, self.locations).resolve(self.ref, "source"), self.input)

    def test_hash_only_dependency_observes_size_without_inventing_it(self):
        resolver = MediaResolver(self.root, self.locations)
        resolver.resolve({"sha256": self.ref["sha256"]}, "font")
        self.assertEqual(resolver.records[0]["bytes"], self.ref["bytes"])
        self.input.write_bytes(b"wrong font")
        with self.assertRaisesRegex(ContractError, "input_identity_mismatch"):
            MediaResolver(self.root, self.locations).resolve({"sha256": self.ref["sha256"]}, "font")

    def test_missing_location_never_searches_basename(self):
        with self.assertRaisesRegex(ContractError, "missing_location"):
            MediaResolver(self.root).resolve(self.ref, "source")

    def test_missing_file_has_explicit_dependency_error(self):
        self.input.unlink()
        with self.assertRaisesRegex(ContractError, "missing_dependency"):
            MediaResolver(self.root, self.locations).resolve(self.ref, "source")

    def test_repo_traversal_and_symlink_escape_rejected(self):
        with self.assertRaisesRegex(ContractError, "unsupported_relative_path"):
            MediaResolver(self.root).resolve({**self.ref, "repo_path": "../original.bin"}, "source")
        repo = self.root / "repo"
        repo.mkdir()
        (repo / "outside.bin").symlink_to(self.input)
        with self.assertRaisesRegex(ContractError, "repository_path_escape"):
            MediaResolver(repo).resolve({**self.ref, "repo_path": "outside.bin"}, "source")

    def test_inventory_and_locations_schema_mismatch(self):
        for document in ({"things": [self.ref]}, {"files": ["not-an-object"]}):
            with self.assertRaises(ContractError):
                MediaResolver(self.root, self.locations, [document])
        with self.assertRaisesRegex(ContractError, "invalid_locations_schema"):
            MediaResolver(self.root, {"objects": []})

    def test_mutation_after_resolution_fails_recheck(self):
        resolver = MediaResolver(self.root, self.locations)
        resolver.resolve(self.ref, "source")
        self.input.write_bytes(b"mutated later")
        with self.assertRaisesRegex(ContractError, "input_changed_during_execution"):
            resolver.recheck()

    def test_collection_requires_exact_safe_members_and_stable_roles(self):
        receipt = self.root / "receipt.json"
        (self.root / "manifest.json").write_text("{}")
        (self.root / "unused.txt").write_text("not consumed")
        rows = [{"path": p.name, **file_identity(p, "test")} for p in [self.input, self.root / "manifest.json", self.root / "unused.txt"]]
        receipt.write_text(json.dumps({"files": rows}))
        ref = file_identity(receipt, "receipt")
        loc = {"objects": {ref["sha256"]: str(receipt)}, "collections": {ref["sha256"]: str(self.root)}}
        resolver = MediaResolver(self.root, loc)
        resolver.collection(ref, ["manifest.json"])
        resolver.collection(ref, ["manifest.json", self.input.name])
        assets = [r for r in resolver.records if r["role"].startswith("asset-")]
        self.assertEqual(len(assets), 2)
        self.assertEqual(len({r["role"] for r in assets}), 2)
        (self.root / "unused.txt").unlink()  # Unused previews are not consumed dependencies.
        resolver.recheck()
        with self.assertRaisesRegex(ContractError, "missing_or_unsafe_asset_member"):
            resolver.collection(ref, ["missing.bin"])
        with self.assertRaisesRegex(ContractError, "unsupported_relative_path"):
            resolver.collection(ref, ["../escape.bin"])

    def test_invalid_json_never_echoes_content_or_locator(self):
        self.input.write_text('{"token":"private", "n":NaN}')
        with self.assertRaisesRegex(ContractError, "invalid_json") as raised:
            read_json(self.input)
        self.assertNotIn("private", str(raised.exception))


class NativeClockTests(unittest.TestCase):
    def test_fx_clock_uses_actual_javascript_rounding_and_proxy_rate(self):
        script = "import {outputClock} from './tools/validate-execution-fx.mjs'; console.log(JSON.stringify([outputClock(12.166666667,12,24000,480,270),outputClock(.0234375,12,24000,480,270)]));"
        run = subprocess.run(["node", "--input-type=module", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        clocks = json.loads(run.stdout)
        self.assertEqual(clocks[0]["frames"], 146)
        self.assertEqual(clocks[0]["pcm_samples_per_channel"], 292000)
        self.assertEqual(clocks[1]["pcm_samples_per_channel"], 563)  # Python round(562.5) differs.

    def test_direction_retained_map_and_output_typography_clock(self):
        recipe = read_json(REPO_ROOT / "projects/god-here/direction-proof.json")
        result = direction_clock(recipe, "directed", CLOCK, {"width": 1280, "height": 720})
        self.assertEqual(result["output"]["frames"], 685)
        self.assertEqual(result["output"]["pcm_samples_per_channel"], 1096000)
        self.assertEqual(result["output"]["dimensions"], [1920, 1080])
        self.assertEqual([(r["source_start"], r["source_end"], r["output_start"], r["output_end"]) for r in result["source_output_map"]],
                         [(2554, 2880, 0, 326), (2880, 3000, 326, 470), (3000, 3215, 470, 685)])
        self.assertEqual(result["typography_clock"], "output frames")
        self.assertEqual(direction_clock(recipe, "reference", CLOCK, {"width": 1280, "height": 720})["output"]["frames"], 661)

    def test_revision_retained_intervals_keep_source_time_events(self):
        recipe = {"schema_version": "1.0", "source_sha256": SOURCE_HASH, "segments": [
            {"source_start_frame": 2554, "source_end_frame": 2955, "output_frames": 401},
            {"source_start_frame": 2955, "source_end_frame": 2979, "output_frames": 42},
            {"source_start_frame": 2979, "source_end_frame": 3215, "output_frames": 236}]}
        result = revision_clock(recipe, {"fps": 30, "source_sha256": SOURCE_HASH}, CLOCK, 1280)
        self.assertEqual(result["output"]["frames"], 679)
        self.assertEqual(result["output"]["pcm_samples_per_channel"], 1086400)
        self.assertEqual(result["typography_clock"], "full-source seconds")
        self.assertEqual(result["source_output_map"][1]["output_start_frame"], 401)
        self.assertEqual(result["source_output_map"][1]["source_start_frame"], 2955)
        self.assertEqual(result["source_output_map"][1]["audio_speed"], 24 / 42)

    def test_native_recipe_schemas_are_not_interchangeable(self):
        recipe = read_json(REPO_ROOT / "projects/god-here/direction-proof.json")
        with self.assertRaisesRegex(ContractError, "native_schema_mismatch"):
            revision_clock(recipe, {"fps": 30, "source_sha256": SOURCE_HASH}, CLOCK, 1280)
        recipe["schema_version"] = "1.0"
        with self.assertRaisesRegex(ContractError, "native_schema_mismatch"):
            direction_clock(recipe, "directed", CLOCK, {"width": 1280, "height": 720})

    def test_source_clock_mismatch_is_rejected(self):
        recipe = read_json(REPO_ROOT / "projects/god-here/direction-proof.json")
        clock = {**CLOCK, "frame_rate": {"num": 24, "den": 1}}
        with self.assertRaisesRegex(ContractError, "native_clock_mismatch"):
            direction_clock(recipe, "directed", clock, {"width": 1280, "height": 720})

    def test_room_retained_sample_lineage_and_noninvertible_spectral_map(self):
        report = read_json(REPO_ROOT / "projects/god-here/room-stretch-20261011/room-stretch-report.json")
        inventory = read_json(REPO_ROOT / "projects/god-here/room-tone-report.json")
        result, options = room_clock(report, inventory, CLOCK)
        self.assertEqual(result["output"]["samples_per_channel"], 5376000)
        self.assertEqual(result["source_reel_samples"], 212160)
        self.assertEqual(len(result["source_reel_map"]), 8)
        self.assertEqual(result["source_reel_map"][0], {"source_start_sample": 349920, "source_end_sample": 362880, "reel_start_sample": 0, "reel_end_sample": 12960})
        self.assertEqual(options["periods"], [112, 84, 56, 28, 14])
        self.assertEqual(options["target_lufs"], -40.37)
        self.assertEqual(options["audition_boost_db"], 14)
        self.assertTrue(options["spectral"])
        self.assertIn("no invertible", result["event_mapping"])
        changed = deepcopy(report)
        changed["source_reel"]["portions"][0]["source_start_sample"] += 1
        with self.assertRaisesRegex(ContractError, "inventory_parameter_map_mismatch"):
            room_clock(changed, inventory, CLOCK)

    def test_partial_spectral_layer_selection_is_explicitly_unsupported(self):
        report = read_json(REPO_ROOT / "projects/god-here/room-stretch-20261011/room-stretch-report.json")
        inventory = read_json(REPO_ROOT / "projects/god-here/room-tone-report.json")
        report["layers"] = report["layers"][:-1]
        with self.assertRaisesRegex(ContractError, "unsupported_room_spectral_selection"):
            room_clock(report, inventory, CLOCK)

    def test_room_seed_is_a_native_dependency_not_an_ignored_report_field(self):
        report = read_json(REPO_ROOT / "projects/god-here/room-stretch-20261011/room-stretch-report.json")
        inventory = read_json(REPO_ROOT / "projects/god-here/room-tone-report.json")
        report["layers"][-1]["processing"]["seed"] += 1
        with self.assertRaisesRegex(ContractError, "unsupported_room_spectral_parameters"):
            room_clock(report, inventory, CLOCK)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "private-performer-original.mp4"
        self.source.write_bytes(b"inert source test bytes")
        self.audio = self.root / "private-audio.wav"
        self.audio.write_bytes(b"inert audio test bytes")
        self.recipe = read_json(REPO_ROOT / "projects/god-here/direction-proof.json")
        self.recipe["source_sha256"] = file_identity(self.source, "source")["sha256"]
        recipe_path = self.root / "recipe.json"
        recipe_path.write_text(json.dumps(self.recipe))
        self.inputs = {"source": file_identity(self.source, "source"), "audio": file_identity(self.audio, "audio"), "recipe": file_identity(recipe_path, "recipe")}
        self.locations = {"objects": {self.inputs[k]["sha256"]: str(v) for k, v in {"source": self.source, "audio": self.audio, "recipe": recipe_path}.items()}}
        self.binding = {"schema_version": "amps.execution.v1", "id": "retained-test", "adapter": "amp.direction.v1",
                        "upstream": {"pull_request": 49, "commit": "f4b2851b25b4279bf2098569c7dc1f4ce0657a30"},
                        "source_clock": {**CLOCK, "sha256": self.recipe["source_sha256"]}, "inputs": self.inputs, "options": {"variant": "reference"}}
        self.path = self.root / "binding.json"

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        self.path.write_text(json.dumps(self.binding))
        with patch("amp.execution.runtime_dependencies", return_value={"python": "test"}), \
             patch("amp.execution.checked_video", return_value=({"width": 1280, "height": 720}, 112.02)), \
             patch("amp.execution.probe", return_value={"format": {"duration": "112.02"}, "streams": [{"codec_type": "audio"}]}):
            return preflight(self.path, locations=self.locations)

    def direction_camera_binding(self, *, variant='directed', field_gain=0, include_fields=True):
        self.recipe['field_gain']=field_gain
        self.recipe['typography']=[]
        recipe_path=self.root/'recipe.json'
        recipe_path.write_text(json.dumps(self.recipe))
        self.inputs['recipe']=file_identity(recipe_path,'recipe')
        self.locations['objects'][self.inputs['recipe']['sha256']]=str(recipe_path)
        self.binding['options']={'variant':variant}
        if include_fields:
            fields_path=self.root/'fields.json'
            fields=read_json(REPO_ROOT/'projects/god-here/direction-field-score.json')
            fields['source_sha256']=self.recipe['source_sha256']
            fields_path.write_text(json.dumps(fields))
            self.inputs['fields']=file_identity(fields_path,'fields')
            self.locations['objects'][self.inputs['fields']['sha256']]=str(fields_path)

    def test_zero_field_gain_camera_requires_and_passes_fields_input(self):
        self.direction_camera_binding()
        for variant in ('directed','expressive'):
            self.binding['options']['variant']=variant
            plan=self.plan()
            self.assertIn('--fields',plan.argv(self.root/'products'))
        del self.inputs['fields']
        with self.assertRaisesRegex(ContractError,'missing_or_unused_dependency'):self.plan()

    def test_zero_field_gain_camera_still_checks_source_cuts(self):
        self.direction_camera_binding()
        with patch('amp.core.shot_at',side_effect=[{'id':'A'},{'id':'B'}]):
            with self.assertRaisesRegex(ContractError,'camera_crosses_source_cut'):self.plan()

    def test_fields_only_variant_does_not_validate_dormant_camera_cues(self):
        self.direction_camera_binding(variant='fields',field_gain=.4)
        with patch('amp.core.shot_at',side_effect=AssertionError('dormant camera must not run')):
            self.assertEqual(self.plan().options['variant'],'fields')

    def test_dry_run_verifies_inputs_and_records_clocks_without_output(self):
        plan = self.plan()
        result = plan.receipt()
        self.assertFalse(result["render_executed"])
        self.assertEqual(result["status"], "preflight_passed")
        self.assertEqual(len(result["inputs"]), 3)
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["binding.json", "private-audio.wav", "private-performer-original.mp4", "recipe.json"])

    def test_binding_cannot_inject_native_command_or_extra_argv(self):
        self.binding["options"]["command"] = "curl https://example.invalid"
        with self.assertRaisesRegex(ContractError, "schema_mismatch"):
            self.plan()
        self.binding["options"] = {"variant": "reference"}
        plan = self.plan()
        argv = plan.argv(self.root / "products")
        self.assertEqual(argv[:3], [sys.executable, "-m", "amp.direction"])
        self.assertNotIn("shell", argv)
        self.assertEqual(argv[-2:], ["--variant", "reference"])

    def test_different_workstream_cannot_be_claimed_as_upstream(self):
        self.binding["upstream"]["pull_request"] = 50
        with self.assertRaisesRegex(ContractError, "upstream_adapter_mismatch"):
            self.plan()

    def test_missing_runtime_dependency_has_named_gate(self):
        with patch("amp.execution.shutil.which", return_value=None):
            with self.assertRaisesRegex(ContractError, r"missing_runtime_dependency \[ffmpeg\]"):
                runtime_dependencies("fx.rack.v1")
        with patch("amp.execution.importlib.import_module", side_effect=ImportError("private path")):
            with self.assertRaisesRegex(ContractError, r"missing_runtime_dependency \[numpy\]"):
                runtime_dependencies("amp.direction.v1")

    def test_source_bound_clock_rejects_wrong_original(self):
        self.binding["source_clock"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "source_binding_mismatch"):
            self.plan()

    def test_output_directory_must_be_fresh(self):
        plan = self.plan()
        with self.assertRaisesRegex(ContractError, "output_directory_already_exists"):
            execute(plan, self.root)

    def test_changed_input_blocks_before_creating_output(self):
        plan = self.plan()
        self.audio.write_bytes(b"changed")
        output = self.root / "run"
        with self.assertRaisesRegex(ContractError, "input_changed_during_execution"):
            execute(plan, output)
        self.assertFalse(output.exists())

    def test_execution_uses_frozen_copies_and_keeps_receipt_path_free(self):
        plan = self.plan()
        output = self.root / "run"
        calls = []
        def native_run(argv, **kwargs):
            calls.append((argv, kwargs))
            self.assertFalse(kwargs.get("shell", False))
            self.assertNotIn(str(self.source), argv)
            staged = Path(argv[argv.index("--source") + 1])
            self.assertEqual(staged.read_bytes(), self.source.read_bytes())
            self.assertEqual(staged.stat().st_mode & 0o777, 0o444)
            (output / "products/render.mp4").write_bytes(b"inert output bytes")
            class Child:
                def wait(self, timeout=None):
                    return 0
            return Child()
        with patch("amp.execution.code_provenance", return_value=plan.code), \
             patch("amp.execution.subprocess.Popen", side_effect=native_run), \
             patch("amp.execution.verify_products", return_value=[{"file": "render.mp4", "sha256": "1" * 64, "bytes": 18, "full_decode": "test-double"}]):
            result = execute(plan, output)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.source.read_bytes(), b"inert source test bytes")
        self.assertEqual((output / "native-private.log").stat().st_mode & 0o777, 0o600)
        self.assertEqual(result["status"], "render_verified")
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_failure_before_launch_does_not_claim_a_render_ran(self):
        plan = self.plan()
        output = self.root / "run"
        with patch("amp.execution.code_provenance", return_value=plan.code), \
             patch("amp.execution.stage_inputs", side_effect=ContractError("staging_identity_mismatch")), \
             patch("amp.execution.subprocess.Popen") as process:
            with self.assertRaisesRegex(ContractError, "staging_identity_mismatch"):
                execute(plan, output)
        process.assert_not_called()
        self.assertFalse(read_json(output / "execution.json")["render_executed"])

    def test_mutating_consumed_copy_is_detected_even_when_original_is_unchanged(self):
        plan = self.plan()
        output = self.root / "run"
        class Child:
            def wait(self, timeout=None):
                staged = output / "inputs/audio.wav"
                staged.chmod(0o644)
                staged.write_bytes(b"native child changed staged bytes")
                return 0
        with patch("amp.execution.code_provenance", return_value=plan.code), \
             patch("amp.execution.subprocess.Popen", return_value=Child()):
            with self.assertRaisesRegex(ContractError, "staged_input_changed_during_execution"):
                execute(plan, output)
        self.assertEqual(self.audio.read_bytes(), b"inert audio test bytes")
        self.assertTrue(read_json(output / "execution.json")["render_executed"])

    def test_cli_error_is_nonzero_and_never_echoes_private_path(self):
        self.path.write_text(json.dumps(self.binding))
        result = subprocess.run([sys.executable, "-m", "amp.cli", "execute", "--binding", str(self.path), "--dry-run"], cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "missing_location")
        self.assertNotIn(str(self.root), result.stdout + result.stderr)

    def test_cli_rejects_silently_ignored_native_options(self):
        self.path.write_text(json.dumps(self.binding))
        result = subprocess.run([sys.executable, "-m", "amp.cli", "execute", "--binding", str(self.path), "--width", "320", "--dry-run"],
                                cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("native settings belong in the binding", result.stderr)

    def test_all_fixed_dispatch_families_use_native_entry_points(self):
        plan = self.plan()
        products = self.root / "products"
        plan.paths.update({k: self.root / k for k in ("composition", "track", "font", "inventory")})
        plan.asset_root = self.root / "assets"
        configs = {
            "amp.revision.v1": ({"width": 1280}, [sys.executable, "-m", "amp.cli", "revision"]),
            "fx.rack.v1": ({"width": 480, "height": 270, "fps": 12, "duration": 12.166666667, "overlay": "none", "audio_input": "reference"}, ["node", str(REPO_ROOT / "tools/render-fx.mjs")]),
            "amp.roomstretch.v1": ({"duration": 112, "periods": [112, 84, 56, 28, 14], "target_lufs": -40.37, "audition_boost_db": 14, "spectral": True}, [sys.executable, str(REPO_ROOT / "tools/run_room_stretch.py")])}
        for adapter, (options, prefix) in configs.items():
            plan.binding["adapter"], plan.options = adapter, options
            argv = plan.argv(products)
            self.assertEqual(argv[:len(prefix)], prefix)
            self.assertNotIn("--ffmpeg", argv)  # No binding-selected program override.


class OutputGatesTests(unittest.TestCase):
    def room_fixture(self, root):
        references = {}
        for name in ("source-reel-raw.wav", "source-reel-seam-smoothed.wav", "final.wav"):
            (root / name).write_bytes(("inert native output " + name).encode())
            references[name] = file_identity(root / name, "fixture")
        report = {"source_reel_raw": {"file": "source-reel-raw.wav", **references["source-reel-raw.wav"]},
                  "source_reel_processed": {"file": "source-reel-seam-smoothed.wav", **references["source-reel-seam-smoothed.wav"]},
                  "layers": [{"stem_wav": "final.wav", "receipts": {"wav": references["final.wav"]}}], "stacks": []}
        (root / "room-stretch-report.json").write_text(json.dumps(report))
        temporary = root / ".room-audition-native-test/audition.wav"
        temporary.parent.mkdir()
        temporary.write_bytes(b"incomplete temporary writer bytes, not a deliverable")
        plan = ExecutionPlan({"adapter": "amp.roomstretch.v1"}, {}, MediaResolver(root), root,
                             clock={"source_reel_samples": 2, "output": {"sample_rate": 48000, "channels": 2, "samples_per_channel": 4}})
        return plan, set(references) | {"room-stretch-report.json"}, temporary

    def test_revision_receipt_requires_the_consumed_direction_code_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            recipe={'schema_version':'1.0','source_sha256':SOURCE_HASH,
                    'segments':[{'source_start_frame':0,'source_end_frame':3,'output_frames':3}]}
            composition={'fps':30,'source_sha256':SOURCE_HASH}
            paths={}
            for role,value in (('recipe',recipe),('composition',composition)):
                paths[role]=root/f'{role}.json'
                paths[role].write_text(json.dumps(value))
            movie=root/'render.mp4';movie.write_bytes(b'inert rendered fixture')
            inputs={role:file_identity(path,role) for role,path in paths.items()}
            inputs['audio']={'sha256':'a'*64}
            code={'files':[{'path':path,**file_identity(REPO_ROOT/path,'code')}
                           for path in ('amp/revision.py','amp/core.py','amp/direction.py')]}
            clock=revision_clock(recipe,composition,CLOCK,1280)
            plan=ExecutionPlan({'adapter':'amp.revision.v1','inputs':inputs,'source_clock':CLOCK},{},
                               MediaResolver(root),REPO_ROOT,paths=paths,clock=clock,code=code)
            digests={row['path']:row['sha256'] for row in code['files']}
            report={'source_sha256':SOURCE_HASH,'audio_sha256':'a'*64,'frames':3,'fps':30,
                    'output_sha256':file_identity(movie,'output')['sha256'],
                    'recipe_sha256':hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest(),
                    'composition_sha256':hashlib.sha256(json.dumps(composition,sort_keys=True).encode()).hexdigest(),
                    'track_sha256':None,'session_sha256':None,'time_map':clock['source_output_map'],
                    'revision_code_sha256':digests['amp/revision.py'],'core_code_sha256':digests['amp/core.py'],
                    'direction_code_sha256':digests['amp/direction.py']}
            receipt=root/'render.revision.json';receipt.write_text(json.dumps(report))
            self.assertEqual(expected_products(plan,root),{'render.mp4','render.revision.json'})
            for mismatch in (None,'0'*64):
                broken=deepcopy(report)
                if mismatch is None:del broken['direction_code_sha256']
                else:broken['direction_code_sha256']=mismatch
                receipt.write_text(json.dumps(broken))
                with self.subTest(mismatch=mismatch),self.assertRaisesRegex(ContractError,'native_code_binding_mismatch'):
                    expected_products(plan,root)

    def test_native_temporary_file_is_accounted_without_replacing_or_decoding_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, required, temporary = self.room_fixture(root)
            (root / "undeclared.txt").write_bytes(b"needs separate review")
            accounting = {}
            with patch("amp.execution.expected_products", return_value=required), \
                 patch("amp.execution.probe", return_value={"streams": [{"codec_type": "audio", "codec_name": "pcm_f32le", "sample_rate": "48000", "channels": 2}]}), \
                 patch("amp.execution.decode_audio", return_value={"finite": True}) as decoder:
                rows = verify_products(plan, root, accounting=accounting)
            self.assertEqual({row["file"] for row in rows}, required)
            self.assertEqual({call.args[0].name for call in decoder.call_args_list}, {"final.wav", "source-reel-raw.wav", "source-reel-seam-smoothed.wav"})
            self.assertEqual(accounting["required_output_count"], 4)
            self.assertEqual(accounting["observed_file_count"], 6)
            incidental = {row["file"]: row for row in accounting["incidental_outputs"]}
            observed = incidental[temporary.relative_to(root).as_posix()]
            self.assertEqual({key: observed[key] for key in ("sha256", "bytes")}, file_identity(temporary, "fixture"))
            self.assertEqual(observed["disposition"], "reconstructible_intermediate_not_retained")
            self.assertEqual(observed["full_decode"], "not_checked_not_a_required_deliverable")
            self.assertFalse(observed["accepted_for_delivery"])
            self.assertEqual(incidental["undeclared.txt"]["disposition"], "review_required")
            self.assertNotIn(str(root), json.dumps(accounting))

    def test_native_temporary_file_does_not_satisfy_a_missing_required_room_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, required, _ = self.room_fixture(root)
            (root / "final.wav").unlink()
            with patch("amp.execution.expected_products", return_value=required), patch("amp.execution.probe") as probe_call:
                with self.assertRaisesRegex(ContractError, "missing_native_outputs"):
                    verify_products(plan, root)
            probe_call.assert_not_called()

    def test_temporary_prefix_only_classifies_a_native_replacement_of_a_required_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, required, _ = self.room_fixture(root)
            names = (".room-stretch-native/final.wav", "unknown/.room-stretch-native/unrelated.bin")
            for name in names:
                (root / name).parent.mkdir(parents=True)
                (root / name).write_bytes(b"temporary-looking bytes")
            accounting = {}
            with patch("amp.execution.expected_products", return_value=required), \
                 patch("amp.execution.probe", return_value={"streams": [{"codec_type": "audio", "codec_name": "pcm_f32le", "sample_rate": "48000", "channels": 2}]}), \
                 patch("amp.execution.decode_audio", return_value={"finite": True}):
                verify_products(plan, root, accounting=accounting)
            incidental = {row["file"]: row for row in accounting["incidental_outputs"]}
            self.assertEqual(incidental[names[0]]["disposition"], "reconstructible_intermediate_not_retained")
            self.assertEqual(incidental[names[1]]["disposition"], "review_required")

    def test_room_output_must_match_native_report_hash_even_if_clock_could_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, required, _ = self.room_fixture(root)
            target = root / "final.wav"
            target.write_bytes(b"x" * target.stat().st_size)
            with patch("amp.execution.expected_products", return_value=required), patch("amp.execution.probe") as probe_call:
                with self.assertRaisesRegex(ContractError, "native_output_identity_mismatch"):
                    verify_products(plan, root)
            probe_call.assert_not_called()

    def test_shifted_presentation_timestamps_fail_despite_correct_counts(self):
        stream = {"codec_name": "h264", "time_base": "1/15360", "start_pts": 0, "duration_ts": 348160}
        clock = presentation_clock(stream, Fraction(680, 30), Fraction(1, 30))
        self.assertEqual(clock["start_seconds"], 0)
        shifted = {**stream, "start_pts": 768}  # 50 ms shift with unchanged frame count/duration.
        with self.assertRaisesRegex(ContractError, "output_presentation_start_mismatch"):
            presentation_clock(shifted, Fraction(680, 30), Fraction(1, 30))
        with self.assertRaisesRegex(ContractError, "output_presentation_end_mismatch"):
            presentation_clock({**stream, "duration_ts": 348672}, Fraction(680, 30), Fraction(1, 30))

    def test_aac_endpoint_tolerance_does_not_allow_shifted_start(self):
        stream = {"codec_name": "aac", "time_base": "1/48000", "start_pts": 0, "duration_ts": 48000 + 512}
        self.assertEqual(presentation_clock(stream, Fraction(1), Fraction(1, 48000))["end_seconds"], 48512 / 48000)
        with self.assertRaisesRegex(ContractError, "output_presentation_start_mismatch"):
            presentation_clock({**stream, "start_pts": 512}, Fraction(1), Fraction(1, 48000))
    def test_audio_only_mp4_cannot_pass_as_the_required_movie(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "render.mp4").write_bytes(b"inert audio-only container")
            plan = ExecutionPlan({"adapter": "fx.rack.v1"}, {}, MediaResolver(root), root, clock={"output": {}})
            with patch("amp.execution.expected_products", return_value={"render.mp4"}), \
                 patch("amp.execution.probe", return_value={"streams": [{"codec_type": "audio"}]}), \
                 patch("amp.execution.decode_audio") as decoder:
                with self.assertRaisesRegex(ContractError, "missing_output_video"):
                    verify_products(plan, root)
            decoder.assert_not_called()

    def test_zero_exit_with_error_stderr_is_a_failed_decode(self):
        result = subprocess.CompletedProcess([], 0, stdout="", stderr="decoder CRC error at private filename")
        with patch("amp.execution.subprocess.run", return_value=result):
            with self.assertRaisesRegex(ContractError, "native_reported_error") as raised:
                command_output(["ffmpeg"], role="output-decode", require_empty_stderr=True)
        self.assertNotIn("private", str(raised.exception))
        result = subprocess.CompletedProcess([], 0, stdout=b"\x00" * 32, stderr=b"CRC error")
        with patch("amp.execution.subprocess.run", return_value=result):
            with self.assertRaisesRegex(ContractError, "output_audio_decode_failed"):
                decode_audio(Path("output.flac"), sample_rate=48000, channels=2, expected_samples=4, codec="flac")

    def test_actual_audio_count_finite_samples_and_codec_tail(self):
        import struct
        def checked(raw, count, codec):
            with patch("amp.execution.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=raw, stderr=b"")):
                return decode_audio(Path("output.wav"), sample_rate=48000, channels=2, expected_samples=count, codec=codec)
        self.assertEqual(checked(b"\x00" * 32, 4, "pcm_f32le")["decoded_samples_per_channel"], 4)
        with self.assertRaisesRegex(ContractError, "output_audio_sample_count_mismatch"):
            checked(b"\x00" * 24, 4, "flac")
        self.assertEqual(checked(b"\x00" * 40, 4, "aac")["codec_tail_padding_samples"], 1)
        with self.assertRaisesRegex(ContractError, "output_audio_sample_count_mismatch"):
            checked(b"\x00" * 40, 4, "flac")
        with self.assertRaisesRegex(ContractError, "output_audio_nonfinite"):
            checked(struct.pack("<8f", float("nan"), *([0.] * 7)), 4, "pcm_f32le")

    def test_an_unrelated_decodable_file_cannot_replace_required_render(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "unrelated.wav").write_bytes(b"inert bytes")
            with patch("amp.execution.expected_products", return_value={"render.mp4", "render.render.json"}), patch("amp.execution.probe") as probe_call:
                with self.assertRaisesRegex(ContractError, "missing_native_outputs"):
                    verify_products(None, root)
            probe_call.assert_not_called()

    def test_room_deliverable_set_covers_raw_production_audition_and_stacks(self):
        report_path = REPO_ROOT / "projects/god-here/room-stretch-20261011/room-stretch-report.json"
        inventory_path = REPO_ROOT / "projects/god-here/room-tone-report.json"
        report, inventory = read_json(report_path), read_json(inventory_path)
        clock, options = room_clock(report, inventory, CLOCK)
        binding = {"adapter": "amp.roomstretch.v1", "inputs": {"inventory": file_identity(inventory_path, "inventory")}, "source_clock": CLOCK}
        plan = ExecutionPlan(binding, {}, MediaResolver(REPO_ROOT), REPO_ROOT, paths={"parameter_report": report_path, "inventory": inventory_path}, clock=clock, options=options)
        with tempfile.TemporaryDirectory() as directory:
            products = Path(directory)
            (products / "room-stretch-report.json").write_text(json.dumps(report))
            required = expected_products(plan, products)
            self.assertTrue({"source-reel-raw.wav", "raw-stems/V112.wav", "stems/P14.wav", "web/P14-audition.m4a", "stacks/V5R.flac", "stacks/P5R.wav"} <= required)
            self.assertEqual(set(room_output_identities(report)) | {"room-stretch-report.json"}, required)
            report["layers"] = report["layers"][:-1]
            (products / "room-stretch-report.json").write_text(json.dumps(report))
            with self.assertRaises(ContractError):
                expected_products(plan, products)


if __name__ == "__main__":
    unittest.main()
