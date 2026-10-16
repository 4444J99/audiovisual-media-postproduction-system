"""Cold/idle scene ownership must not compile disabled native DAT modules."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import audio_intervals
import mix


class MixRoutingTests(unittest.TestCase):
    def fixture(self, active=False, cooking=False, owned=False):
        data=np.arange(10,dtype=np.float32).reshape(2,5)/20
        signal=SimpleNamespace(numpyArray=lambda:data,cook=lambda:None,
                               start=100,rate=44100,isTimeSlice=True)
        player=SimpleNamespace(par=SimpleNamespace(play=SimpleNamespace(eval=lambda:True)))
        track=SimpleNamespace(id=7,isCOMP=True,
            par=SimpleNamespace(Enabled=True,Mute=False,Solo=False,Pan=0),
            op=lambda name:signal if name=='null_audio' else player if name=='audiomovie_material' else None)

        class Poison:
            @property
            def Enabled(self):
                raise RuntimeError('Idle send evaluated a disabled runtime module')

        send=SimpleNamespace(isCOMP=True,par=Poison(),op=lambda name:signal)
        def scene_op(name):
            if name=='text_runtime':raise RuntimeError('Disabled runtime module accessed')
            return None
        scene=SimpleNamespace(isCOMP=True,allowCooking=cooking,
            par=SimpleNamespace(Controller='controller',Active=active),children=[send],op=scene_op)
        controller=SimpleNamespace(op=lambda name:track,fetch=lambda *args: {'run_id':'owned'} if owned else None)
        helper=SimpleNamespace(module=audio_intervals)
        workspace=SimpleNamespace(children=[SimpleNamespace(isCOMP=True,par=SimpleNamespace(),children=[track]),scene],
            time=SimpleNamespace(rate=60),op=lambda name:helper if name=='text_audio_intervals' else controller)
        clock=SimpleNamespace(numSamples=5,start=100)
        output=SimpleNamespace(inputs=[clock],clear=lambda:None)
        def copy(array):output.result=array.copy();output.start=0
        output.copyNumpyArray=copy
        with patch.object(mix,'parent',SimpleNamespace(Materials=workspace),create=True):mix.onCook(output)
        return output,data

    def test_disabled_idle_scene_does_not_compile_or_mix_its_send(self):
        output,data=self.fixture()
        np.testing.assert_allclose(output.result,data,rtol=1e-6)
        self.assertEqual(output.start,100)

    def test_enabled_but_inactive_scene_still_skips_its_send(self):
        output,data=self.fixture(cooking=True)
        np.testing.assert_allclose(output.result,data,rtol=1e-6)

    def test_held_owned_primary_stays_excluded_when_scene_cooking_stops(self):
        output,_=self.fixture(active=True,owned=True)
        self.assertEqual(np.count_nonzero(output.result),0)

    def test_controller_without_execution_does_not_own_primary(self):
        output,data=self.fixture(active=True)
        np.testing.assert_allclose(output.result,data,rtol=1e-6)


if __name__=='__main__':unittest.main()
