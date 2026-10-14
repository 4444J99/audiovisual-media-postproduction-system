"""One finite shared audition, driven by native movie frames."""
import math


def onFrameStart(frame):
    v=parent.Vocabulary;p=v.op('base_player')
    if p.par.Play:p.op('movie_material').cook()
    if v.fetch('performance_state',None) and v.op('text_performance'):
        try:
            if not v.op('text_performance').module.observe_frame(p.op('movie_material')):return
        except Exception as error:
            v.op('text_performance').module.stop(str(error),failed=True);v.par.Status='Performance stopped: '+str(error);return
    if not p.par.Play:return
    if not all(math.isfinite(float(x)) for x in [p.par.In,p.par.Out,p.par.Speed]) or not 0<=p.par.In<p.par.Out<=112 or not .25<=p.par.Speed<=2:
        if v.op('text_performance'):v.op('text_performance').module.stop('Invalid interval or speed',failed=True)
        p.par.Play=False;v.par.Status='Audition stopped: invalid source interval or speed';return
    movie=p.op('movie_material');movie.cook()
    if movie.isOpening:
        waited=p.fetch('opening_frames',0)+1;p.store('opening_frames',waited)
        if waited>240:
            if v.op('text_performance'):v.op('text_performance').module.stop()
            p.par.Play=False;v.par.Status='Audition stopped: decoder did not open within 240 native frames'
        return
    if movie.lastIndexUploaded/30>=float(p.par.Out)-1/30-.00001:
        if v.fetch('performance_state',None):
            try:v.op('text_performance').module.advance()
            except Exception as error:
                v.op('text_performance').module.stop(str(error),failed=True);v.par.Status='Performance stopped: '+str(error)
            return
        done=p.fetch('repeats_done',0)+1;p.store('repeats_done',done)
        if done>=min(16,max(1,int(v.par.Repeats))):
            p.par.Play=False;v.par.Status='Audition finished: '+p.fetch('loaded_unit','')
        else:movie.par.cuepulse.pulse()
