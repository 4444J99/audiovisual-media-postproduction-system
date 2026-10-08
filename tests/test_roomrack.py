import unittest
import numpy as np
from amp.roomrack import split_bands, compress, BANDS

class RoomRackTests(unittest.TestCase):
    def test_flat_split_reconstruction(self):
        x=np.random.default_rng(1).normal(0,.02,(48000,2))
        np.testing.assert_allclose(sum(split_bands(x).values()),x,atol=1e-12)

    def test_linked_compression_controls_burst(self):
        x=np.ones((48000*3,2))*.003
        x[48000:96000]*=12
        x[:,1]*=.5
        y,r=compress(x,BANDS['mid'])
        self.assertGreater(r['max_reduction_db'],3)
        self.assertLess(np.max(np.abs(y)),np.max(np.abs(x)))
        np.testing.assert_allclose(y[:,1],y[:,0]*.5)
        self.assertTrue(np.isfinite(y).all())

if __name__=='__main__':unittest.main()
