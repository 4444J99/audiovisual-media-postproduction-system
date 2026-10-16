"""One bounded native passage check, optionally muted; records metrics, never media."""
import json
import time
import zlib
from pathlib import Path
import numpy as np


def start(p, output, muted=True):
    p.store('passage_check', dict(output=output, deadline=time.monotonic()+55,
        frames=0, sections={}, hashes=set(), peaks=[], interval_errors=0,
        source_first=None, source_last=None, idle_frames=0, idle_peak=0,
        distinct_banks=[], previous_hash=None, repeated_nonzero_blocks=0,
        prior_monitor=bool(parent.Materials.par.Monitor), audible_test=not muted,
        beats={}, words=[]))
    p.op('execute_verify_passage').par.active=True
    if muted:parent.Materials.par.Monitor=False
    p.par.Restart.pulse()


def onFrameEnd(frame):
    p=parent.Passage
    state=p.fetch('passage_check',None)
    if state is None:return
    w=parent.Materials
    p.op('null_picture').cook()
    mixer=w.op('script_mix');mixer.cook()
    data=mixer.numpyArray()
    peak=float(np.max(np.abs(data))) if data.size else 0
    clock=w.op('select_audio_interval')
    if p.par.Play and p.fetch('pending_cue',None) is None:
        source=float(p.par.Time)
        state['source_first']=source if state['source_first'] is None else state['source_first']
        state['source_last']=source
        state['frames']+=1
        section=str(p.par.Currentsection)
        state['sections'][section]=state['sections'].get(section,0)+1
        if hasattr(p.par,'Beat'):
            beat=str(p.par.Beat);state['beats'][beat]=state['beats'].get(beat,0)+1
            word=p.op('text_runtime').module.expressive(p)[0]
            if word and word not in state['words']:state['words'].append(word)
        digest=zlib.crc32(data.tobytes())
        state['hashes'].add(digest);state['peaks'].append(peak)
        if peak>1e-7 and digest==state['previous_hash']:state['repeated_nonzero_blocks']+=1
        state['previous_hash']=digest
        if mixer.start!=clock.start or mixer.numSamples!=clock.numSamples:state['interval_errors']+=1
        state['distinct_banks']=[n.name for n in w.op('text_mix').module.audible_banks(w)]
    elif state['frames'] and str(p.par.Status).startswith('Complete'):
        state['idle_frames']+=1;state['idle_peak']=max(state['idle_peak'],peak)
    expired=time.monotonic()>state['deadline']
    if state['idle_frames']>=3 or expired:
        p.op('execute_verify_passage').par.active=False
        report={k:v for k,v in state.items() if k not in ('hashes','peaks','deadline','output','previous_hash')}
        report.update(unique_blocks=len(state['hashes']),peak=max(state['peaks'],default=0),
                      deadline_expired=expired,errors=p.errors(recurse=True),
                      final_time=float(p.par.Time),playing=bool(p.par.Play),
                      device=str(w.op('audio_monitor').par.device))
        Path(state['output']).write_text(json.dumps(report,indent=2),encoding='utf-8')
        w.par.Monitor=state['prior_monitor']
        p.unstore('passage_check')
        if expired:p.par.Play=False
    else:p.store('passage_check',state)
