import unittest
import numpy as np
from audio_intervals import align


class AudioIntervalTests(unittest.TestCase):
    def test_native_interval_preserves_every_sample(self):
        source=np.arange(1470,dtype=np.float32)
        np.testing.assert_array_equal(align(source,735,44100,735,1470),source)

    def test_new_source_catchup_is_trimmed_to_current_interval(self):
        source=np.arange(8820,dtype=np.float32)
        np.testing.assert_array_equal(align(source,0,44100,8085,735),source[-735:])

    def test_gaps_are_silent_instead_of_stretched(self):
        np.testing.assert_array_equal(align([1,2,3],10,44100,8,7),[0,0,1,2,3,0,0])

    def test_sample_rate_coordinates_and_empty_signal(self):
        np.testing.assert_allclose(align([0,1,2,3],0,22050,0,7),np.arange(7)/2)
        np.testing.assert_array_equal(align([],0,44100,0,3),[0,0,0])
