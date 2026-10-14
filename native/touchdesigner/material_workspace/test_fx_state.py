"""Exact future continuation after typed native DSP memory restoration."""
import unittest
import numpy as np
import fx_dsp
import fx_state


class FxStateTests(unittest.TestCase):
    def test_all_processors_continue_exactly(self):
        kinds = ['routing', 'delay', 'stutter', 'freeze', 'granular', 'reverse',
                 'feedback', 'queue', 'gate', 'displacement', 'exchange', 'damage', 'typography']
        params = {'capture': .01, 'window': .02, 'grain': .02, 'time': .03,
                  'scatter': .03, 'span': .02, 'pivot': .08, 'burst': .4,
                  'rate': 30, 'release': 20, 'density': 30, 'band': 900}
        rng = np.random.default_rng(7)
        blocks = [rng.uniform(-.5, .5, (2, 735)).astype(np.float32) for _ in range(16)]
        for kind, seconds in [(k, s) for k in kinds for s in (.1, .5)]:
            with self.subTest(kind=kind, seconds=seconds):
                source = fx_dsp.Stream(seconds=seconds, seed=19)
                for block in blocks[:8]:source.process(kind, block, params)
                metadata, arrays = fx_state.snapshot(source)
                restored = fx_state.restore(metadata, arrays, fx_dsp.Stream)
                for block in blocks[8:]:
                    np.testing.assert_array_equal(source.process(kind, block, params), restored.process(kind, block, params))
                self.assertEqual(source.position, restored.position)

    def test_snapshot_is_independent(self):
        s = fx_dsp.Stream(seconds=.1);meta, arrays = fx_state.snapshot(s)
        s.input[:] = 1
        restored = fx_state.restore(meta, arrays, fx_dsp.Stream)
        self.assertEqual(float(np.max(restored.input)), 0)

    def test_rejects_nonfinite_and_excessive_state(self):
        with self.assertRaises(ValueError):fx_state.encode(np.array([np.nan], np.float32))
        with self.assertRaises(ValueError):fx_state.encode(np.zeros(100, np.float32), max_bytes=10)
        with self.assertRaises(ValueError):fx_state.encode(object())

    def test_rejects_incomplete_or_changed_dsp_shape(self):
        s = fx_dsp.Stream(seconds=.1);meta, arrays = fx_state.snapshot(s)
        state = fx_state.decode(meta, arrays);state['input'] = np.zeros((1, 4410), np.float32)
        changed, data = fx_state.encode(state)
        with self.assertRaises(ValueError):fx_state.restore(changed, data, fx_dsp.Stream)
        state.pop('position');changed, data = fx_state.encode(state)
        with self.assertRaises(ValueError):fx_state.restore(changed, data, fx_dsp.Stream)

    def test_rejects_unreferenced_array(self):
        meta, arrays = fx_state.encode({'position': 1});arrays['foreign'] = np.zeros(1, np.float32)
        with self.assertRaises(ValueError):fx_state.decode(meta, arrays)


class FxStateStoreTests(unittest.TestCase):
    def test_private_disk_roundtrip_and_corruption(self):
        import tempfile
        from pathlib import Path
        import fx_state_store
        with tempfile.TemporaryDirectory() as root:
            data = {'a0': np.arange(80, dtype=np.float32).reshape(2, 40)}
            path = fx_state_store.write(Path(root) / 'state', {'purpose': 'synthetic test'}, data)
            metadata, arrays = fx_state_store.read(path)
            self.assertEqual(metadata, {'purpose': 'synthetic test'})
            np.testing.assert_array_equal(arrays['a0'], data['a0'])
            with (path / 'a0.npy').open('r+b') as target:target.write(b'corrupt')
            with self.assertRaises(ValueError):fx_state_store.read(path)

    def test_uncommitted_state_is_unavailable(self):
        import tempfile
        import fx_state_store
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(FileNotFoundError):fx_state_store.read(root)


if __name__ == '__main__':unittest.main()
