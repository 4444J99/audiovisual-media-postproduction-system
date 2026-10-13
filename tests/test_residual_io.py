"""Hash-bound WAV-window execution against the retained MediaResolver."""
import copy
import importlib
import json
from pathlib import Path
import struct
import numpy as np
import unittest
from unittest import mock
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from scipy.io import wavfile
from amp.media_resolver import ContractError, MediaResolver, file_identity

def runner():
    return importlib.import_module('amp.residual_io').run_residual_pair

def make_pair(tmp_path):
    source = np.column_stack((np.linspace(-0.7, 0.7, 120), np.linspace(0.4, -0.4, 120)))
    processed = source * 0.6
    locations = {'objects': {}}

    def bind(name, data, rate=44100):
        path = tmp_path / name
        wavfile.write(path, rate, data)
        ref = file_identity(path, 'fixture')
        locations['objects'][ref['sha256']] = str(path)
        return ref
    spec = {'schema': 'amps.residual-pair.v1', 'source': bind('private-source.wav', source), 'processed': bind('private-processed.wav', processed), 'sample_rate': 44100, 'source_start': 4, 'processed_start': 4, 'sample_count': 64, 'alignment': 'explicit-sample-windows'}
    record = tmp_path / 'private-processing-record.json'
    record.write_text(json.dumps({'note': 'opaque producer record; never execute or publish this text'}))
    spec['processing_record'] = file_identity(record, 'fixture')
    locations['objects'][spec['processing_record']['sha256']] = str(record)
    return (spec, locations, bind, source, processed)

def execute(tmp_path, pair, *, spec=None, output='result', dry_run=False):
    original, locations, _, _, _ = pair
    return runner()(spec or original, MediaResolver(tmp_path, locations), tmp_path / output, dry_run=dry_run)

class ResidualIOTests(unittest.TestCase):

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pair = make_pair(self.root)

    def patch_attribute(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_residual_io_module_exists(self):
        self.assertTrue(importlib.util.find_spec('amp.residual_io') is not None, 'residual IO not implemented')

    def test_complete_roundtrip_and_public_receipt(self):
        tmp_path = self.root
        pair = self.pair
        spec, _, _, source, processed = pair
        result = execute(tmp_path, pair)
        self.assertTrue(result['state'] == 'complete')
        self.assertTrue(result['arithmetic']['max_absolute_error'] <= 1e-06)
        self.assertTrue(result['native_residual'] is None)
        self.assertTrue(result['assessment'] == {'technical': 'passed', 'perceptual': 'pending', 'artistic': 'pending', 'delivery': 'pending'})
        self.assertTrue(result['alignment_assessment'] == 'caller-declared-not-independently-verified')
        self.assertTrue(result['processing_record_assessment'] == 'identity-only-not-provenance-validation')
        saved = json.loads((tmp_path / 'result/receipt.json').read_text())
        self.assertTrue(saved == result)
        text = json.dumps(result)
        self.assertTrue(str(tmp_path) not in text and 'private-' not in text and ('opaque producer' not in text))
        rate, raw = wavfile.read(tmp_path / 'result/raw-residual.wav')
        self.assertTrue(rate == spec['sample_rate'] and raw.dtype == np.float64)
        np.testing.assert_array_equal(raw, source[4:68] - processed[4:68])
        _, rebuilt = wavfile.read(tmp_path / 'result/reconstructed.wav')
        np.testing.assert_allclose(rebuilt, source[4:68], atol=1e-06, rtol=0)
        self.assertTrue(result['sample_maps']['source'] == {'start_sample': 4, 'sample_count': 64, 'sample_rate': 44100})
        for name, ref in result['outputs'].items():
            self.assertTrue(file_identity(tmp_path / 'result' / name, 'output') == ref)

    def test_dry_run_has_no_arithmetic_and_writes_nothing(self):
        tmp_path = self.root
        pair = self.pair
        module = importlib.import_module('amp.residual_io')
        self.patch_attribute(module, 'arithmetic_residual', lambda *_: self.fail('dry-run computed residue'))
        result = execute(tmp_path, pair, dry_run=True)
        self.assertTrue(result['state'] == 'preflight-only')
        self.assertTrue(result['arithmetic'] is None and result['outputs'] == {})
        self.assertTrue(result['assessment']['technical'] == 'preflight-only')
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_fresh_directories_are_deterministic(self):
        tmp_path = self.root
        pair = self.pair
        self.assertTrue(execute(tmp_path, pair, output='a') == execute(tmp_path, pair, output='b'))

    def test_existing_output_is_not_overwritten(self):
        tmp_path = self.root
        pair = self.pair
        output = tmp_path / 'result'
        output.mkdir()
        keep = output / 'receipt.json'
        keep.write_text('owner content')
        with self.assertRaisesRegex(ContractError, 'output_not_fresh'):
            execute(tmp_path, pair)
        self.assertTrue(keep.read_text() == 'owner content')

    def test_broken_output_symlink_is_rejected(self):
        tmp_path = self.root
        pair = self.pair
        (tmp_path / 'result').symlink_to(tmp_path / 'missing')
        with self.assertRaisesRegex(ContractError, 'output_not_fresh'):
            execute(tmp_path, pair)
        self.assertTrue(not (tmp_path / 'missing').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_01(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('sample_count', 0)
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_02(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('sample_count', -1)
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_03(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('sample_count', True)
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_04(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('sample_count', 2.5)
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_05(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('sample_count', 1000000000)
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_06(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('source_start', -1)
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_07(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('processed_start', False)
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_08(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('sample_rate', 0)
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_09(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('sample_rate', 44100.0)
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_10(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('alignment', 'guess')
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_numeric_and_schema_inputs_are_rejected_11(self):
        tmp_path = self.root
        pair = self.pair
        field, value = ('schema', 'amps.study.v1')
        spec = copy.deepcopy(pair[0])
        spec[field] = value
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_unexpected_operations_rejected_without_execution_or_path_leak(self):
        tmp_path = self.root
        pair = self.pair
        spec = copy.deepcopy(pair[0])
        spec['command'] = '/private/secret; touch /tmp/no'
        with self.assertRaises(ContractError) as error:
            execute(tmp_path, pair, spec=spec)
        self.assertTrue('/private' not in str(error.exception))
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_bad_hash_is_rejected_before_any_output(self):
        tmp_path = self.root
        pair = self.pair
        spec = copy.deepcopy(pair[0])
        spec['source']['sha256'] = 'a' * 64
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_sample_rate_is_not_implicitly_resampled(self):
        tmp_path = self.root
        pair = self.pair
        spec = copy.deepcopy(pair[0])
        spec['processed'] = pair[2]('other-rate.wav', pair[4], 48000)
        with self.assertRaisesRegex(ContractError, 'sample_rate_mismatch'):
            execute(tmp_path, pair, spec=spec)

    def test_channels_are_not_implicitly_mixed(self):
        tmp_path = self.root
        pair = self.pair
        spec = copy.deepcopy(pair[0])
        spec['processed'] = pair[2]('mono.wav', pair[4][:, 0])
        with self.assertRaisesRegex(ContractError, 'channel_count_mismatch'):
            execute(tmp_path, pair, spec=spec)

    def test_different_lengths_with_explicit_windows_are_supported(self):
        tmp_path = self.root
        pair = self.pair
        spec = copy.deepcopy(pair[0])
        spec['processed'] = pair[2]('shorter.wav', pair[4][4:])
        spec['processed_start'] = 0
        result = execute(tmp_path, pair, spec=spec)
        self.assertTrue(result['arithmetic']['max_absolute_error'] <= 1e-06)
        self.assertTrue(result['sample_maps']['processed']['start_sample'] == 0)

    def test_out_of_bounds_is_not_silently_padded(self):
        tmp_path = self.root
        pair = self.pair
        spec = copy.deepcopy(pair[0])
        spec['processed_start'] = 100
        with self.assertRaisesRegex(ContractError, 'sample_window_out_of_bounds'):
            execute(tmp_path, pair, spec=spec)

    def test_nonfinite_window_rejected_before_output(self):
        tmp_path = self.root
        pair = self.pair
        data = pair[4].copy()
        data[10] = np.nan
        spec = copy.deepcopy(pair[0])
        spec['processed'] = pair[2]('nan.wav', data)
        with self.assertRaisesRegex(ContractError, 'nonfinite_signal'):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_native_residual_measured_separately_without_forcing_closure(self):
        tmp_path = self.root
        pair = self.pair
        spec = copy.deepcopy(pair[0])
        spec['native_residual'] = pair[2]('native.wav', np.zeros_like(pair[3]))
        spec['native_residual_start'] = 4
        result = execute(tmp_path, pair, spec=spec)
        self.assertTrue(result['arithmetic']['passes_tolerance'] is True)
        self.assertTrue(result['native_residual']['passes_tolerance'] is False)
        self.assertTrue(result['native_residual']['max_absolute_error'] > 1e-06)
        _, native = wavfile.read(tmp_path / 'result/native-residual.wav')
        self.assertTrue(not np.any(native))

    def test_native_map_must_be_complete_01(self):
        tmp_path = self.root
        pair = self.pair
        ref_present, start_present = (True, False)
        spec = copy.deepcopy(pair[0])
        if ref_present:
            spec['native_residual'] = pair[0]['processed']
        if start_present:
            spec['native_residual_start'] = 0
        with self.assertRaisesRegex(ContractError, 'native_residual_map_incomplete'):
            execute(tmp_path, pair, spec=spec)

    def test_native_map_must_be_complete_02(self):
        tmp_path = self.root
        pair = self.pair
        ref_present, start_present = (False, True)
        spec = copy.deepcopy(pair[0])
        if ref_present:
            spec['native_residual'] = pair[0]['processed']
        if start_present:
            spec['native_residual_start'] = 0
        with self.assertRaisesRegex(ContractError, 'native_residual_map_incomplete'):
            execute(tmp_path, pair, spec=spec)

    def test_pcm_conversion_uses_full_scale_not_audition_gain_01(self):
        tmp_path = self.root
        pair = self.pair
        dtype, divisor, offset = (np.int16, 32768, 0)
        values = (np.arange(120) % 120).astype(dtype)
        spec = copy.deepcopy(pair[0])
        spec['source'] = pair[2]('pcm.wav', values)
        spec['processed'] = pair[2]('zero.wav', np.zeros(120))
        execute(tmp_path, pair, spec=spec)
        _, source = wavfile.read(tmp_path / 'result/source-window.wav')
        np.testing.assert_array_equal(source, (values[4:68].astype(np.float64) - offset) / divisor)

    def test_pcm_conversion_uses_full_scale_not_audition_gain_02(self):
        tmp_path = self.root
        pair = self.pair
        dtype, divisor, offset = (np.int32, 2147483648, 0)
        values = (np.arange(120) % 120).astype(dtype)
        spec = copy.deepcopy(pair[0])
        spec['source'] = pair[2]('pcm.wav', values)
        spec['processed'] = pair[2]('zero.wav', np.zeros(120))
        execute(tmp_path, pair, spec=spec)
        _, source = wavfile.read(tmp_path / 'result/source-window.wav')
        np.testing.assert_array_equal(source, (values[4:68].astype(np.float64) - offset) / divisor)

    def test_pcm_conversion_uses_full_scale_not_audition_gain_03(self):
        tmp_path = self.root
        pair = self.pair
        dtype, divisor, offset = (np.uint8, 128, 128)
        values = (np.arange(120) % 120).astype(dtype)
        spec = copy.deepcopy(pair[0])
        spec['source'] = pair[2]('pcm.wav', values)
        spec['processed'] = pair[2]('zero.wav', np.zeros(120))
        execute(tmp_path, pair, spec=spec)
        _, source = wavfile.read(tmp_path / 'result/source-window.wav')
        np.testing.assert_array_equal(source, (values[4:68].astype(np.float64) - offset) / divisor)

    def test_packed_24_bit_pcm_is_decoded_exactly(self):
        tmp_path = self.root
        pair = self.pair
        integers = [-8388608, -1, 0, 1, 8388607]
        payload = b''.join(((v & 16777215).to_bytes(3, 'little') for v in integers))
        fmt = struct.pack('<HHIIHH', 1, 1, 44100, 132300, 3, 24)
        chunks = b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(payload)) + payload + b'\x00'
        path = tmp_path / 'packed.wav'
        path.write_bytes(b'RIFF' + struct.pack('<I', len(chunks) + 4) + b'WAVE' + chunks)
        spec = copy.deepcopy(pair[0])
        spec['source'] = file_identity(path, 'fixture')
        pair[1]['objects'][spec['source']['sha256']] = str(path)
        spec['processed'] = pair[2]('five-zero.wav', np.zeros(5))
        spec.update(source_start=0, processed_start=0, sample_count=5)
        execute(tmp_path, pair, spec=spec)
        _, source = wavfile.read(tmp_path / 'result/source-window.wav')
        np.testing.assert_array_equal(source, np.array(integers) / 8388608)

    def test_malformed_wave_fails_before_allocating_or_writing_01(self):
        tmp_path = self.root
        pair = self.pair
        mutation = 'truncated'
        path = tmp_path / 'bad.wav'
        data = bytearray((tmp_path / 'private-source.wav').read_bytes())
        if mutation == 'truncated':
            data = data[:-7]
        elif mutation == 'riff_length':
            data[4:8] = struct.pack('<I', 4294967295)
        elif mutation == 'oversized_chunk':
            data[16:20] = struct.pack('<I', 4294967295)
        else:
            data += b'data' + struct.pack('<I', 8) + b'\x00' * 8
            data[4:8] = struct.pack('<I', len(data) - 8)
        path.write_bytes(data)
        spec = copy.deepcopy(pair[0])
        spec['source'] = file_identity(path, 'fixture')
        pair[1]['objects'][spec['source']['sha256']] = str(path)
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_malformed_wave_fails_before_allocating_or_writing_02(self):
        tmp_path = self.root
        pair = self.pair
        mutation = 'oversized_chunk'
        path = tmp_path / 'bad.wav'
        data = bytearray((tmp_path / 'private-source.wav').read_bytes())
        if mutation == 'truncated':
            data = data[:-7]
        elif mutation == 'riff_length':
            data[4:8] = struct.pack('<I', 4294967295)
        elif mutation == 'oversized_chunk':
            data[16:20] = struct.pack('<I', 4294967295)
        else:
            data += b'data' + struct.pack('<I', 8) + b'\x00' * 8
            data[4:8] = struct.pack('<I', len(data) - 8)
        path.write_bytes(data)
        spec = copy.deepcopy(pair[0])
        spec['source'] = file_identity(path, 'fixture')
        pair[1]['objects'][spec['source']['sha256']] = str(path)
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_malformed_wave_fails_before_allocating_or_writing_03(self):
        tmp_path = self.root
        pair = self.pair
        mutation = 'riff_length'
        path = tmp_path / 'bad.wav'
        data = bytearray((tmp_path / 'private-source.wav').read_bytes())
        if mutation == 'truncated':
            data = data[:-7]
        elif mutation == 'riff_length':
            data[4:8] = struct.pack('<I', 4294967295)
        elif mutation == 'oversized_chunk':
            data[16:20] = struct.pack('<I', 4294967295)
        else:
            data += b'data' + struct.pack('<I', 8) + b'\x00' * 8
            data[4:8] = struct.pack('<I', len(data) - 8)
        path.write_bytes(data)
        spec = copy.deepcopy(pair[0])
        spec['source'] = file_identity(path, 'fixture')
        pair[1]['objects'][spec['source']['sha256']] = str(path)
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_malformed_wave_fails_before_allocating_or_writing_04(self):
        tmp_path = self.root
        pair = self.pair
        mutation = 'duplicate_data'
        path = tmp_path / 'bad.wav'
        data = bytearray((tmp_path / 'private-source.wav').read_bytes())
        if mutation == 'truncated':
            data = data[:-7]
        elif mutation == 'riff_length':
            data[4:8] = struct.pack('<I', 4294967295)
        elif mutation == 'oversized_chunk':
            data[16:20] = struct.pack('<I', 4294967295)
        else:
            data += b'data' + struct.pack('<I', 8) + b'\x00' * 8
            data[4:8] = struct.pack('<I', len(data) - 8)
        path.write_bytes(data)
        spec = copy.deepcopy(pair[0])
        spec['source'] = file_identity(path, 'fixture')
        pair[1]['objects'][spec['source']['sha256']] = str(path)
        with self.assertRaises(ContractError):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_write_failure_never_leaves_success_receipt(self):
        tmp_path = self.root
        pair = self.pair
        module = importlib.import_module('amp.residual_io')
        real = module.wavfile.write
        count = 0

        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('/private/owner/path')
            return real(*args, **kwargs)
        self.patch_attribute(module.wavfile, 'write', fail_second)
        with self.assertRaises(ContractError) as error:
            execute(tmp_path, pair)
        self.assertTrue('private' not in str(error.exception))
        self.assertTrue(not (tmp_path / 'result/receipt.json').exists())

    def test_input_mutation_during_execution_prevents_success(self):
        tmp_path = self.root
        pair = self.pair
        module = importlib.import_module('amp.residual_io')
        real = module.wavfile.write

        def mutate(*args, **kwargs):
            real(*args, **kwargs)
            with (tmp_path / 'private-source.wav').open('ab') as stream:
                stream.write(b'changed')
        self.patch_attribute(module.wavfile, 'write', mutate)
        with self.assertRaisesRegex(ContractError, 'input_changed_during_execution'):
            execute(tmp_path, pair)
        self.assertTrue(not (tmp_path / 'result/receipt.json').exists())

    def test_receipt_write_failure_cannot_publish_success(self):
        tmp_path = self.root
        pair = self.pair
        module = importlib.import_module('amp.residual_io')

        def fail_json(_value, stream, **_kwargs):
            stream.write('{"state": "complete"')
            raise OSError('disk full /private/owner')
        self.patch_attribute(module.json, 'dump', fail_json)
        with self.assertRaises(ContractError):
            execute(tmp_path, pair)
        self.assertTrue(not (tmp_path / 'result/receipt.json').exists())

    def test_catastrophic_cancellation_rejected_before_output(self):
        tmp_path = self.root
        pair = self.pair
        spec = copy.deepcopy(pair[0])
        spec['source'] = pair[2]('small.wav', np.full((120, 2), 0.25))
        spec['processed'] = pair[2]('huge.wav', np.full((120, 2), 1e+16))
        with self.assertRaisesRegex(ContractError, 'arithmetic_closure_failed'):
            execute(tmp_path, pair, spec=spec)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_limits_reject_before_sample_decode(self):
        tmp_path = self.root
        pair = self.pair
        module = importlib.import_module('amp.residual_io')
        self.patch_attribute(module, 'MAX_WORKING_BYTES', 1)
        self.patch_attribute(module, '_read_window', lambda *_: self.fail('decoded before budget gate'))
        with self.assertRaisesRegex(ContractError, 'residual_resource_limit'):
            execute(tmp_path, pair)
        self.assertTrue(not (tmp_path / 'result').exists())

    def test_cli_uses_safe_structured_errors(self):
        module = importlib.import_module('amp.residual_io')
        stdout, stderr = (StringIO(), StringIO())
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = module.main(['--spec', str(self.root / 'private-missing.json'), '--locations', str(self.root / 'private.json'), '--output', str(self.root / 'out')])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(json.loads(stderr.getvalue())['state'], 'failed')
        self.assertNotIn(str(self.root), stderr.getvalue())
        self.assertNotIn('Traceback', stderr.getvalue())
if __name__ == '__main__':
    unittest.main()
