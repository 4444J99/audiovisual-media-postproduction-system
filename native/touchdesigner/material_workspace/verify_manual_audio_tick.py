"""Finite main-mix inspection; keeps the device muted while sampling."""
def onFrameEnd(frame):
    import hashlib,time
    import numpy as np
    w=parent.Materials;job=w.fetch('manual_audio_check',{})
    if job.get('state')!='running':return
    try:
        if time.monotonic()>job['deadline']:raise ValueError('Audio inspection deadline')
        mix=w.op('script_mix');mix.cook()
        data=mix.numpyArray();clock=w.op('base_audio_clock/null_slice')
        source=op(w.fetch('original')).op('null_audio');audio=source.numpyArray()
        reference=np.vstack([w.op('text_audio_intervals').module.align(audio[min(i,len(audio)-1)],source.start,source.rate,clock.start,clock.numSamples) for i in range(2)])
        row={'native_frame':float(absTime.frame),'source_time':float(w.par.Time),
             'clock_start':clock.start,'clock_samples':clock.numSamples,
             'mix_start':mix.start,'mix_samples':mix.numSamples,
             'source_start':source.start,'source_samples':source.numSamples,
             'peak':float(np.max(np.abs(data))),'rms':float(np.sqrt(np.mean(data*data))),
             'sha256':hashlib.sha256(data.tobytes()).hexdigest(),
             'source_mix_error':float(np.max(np.abs(reference-data))),
             'error':mix.errors()}
        job['samples'].append(row)
        if len(job['samples'])>=120:
            job['state']='measured';me.par.active=False
    except Exception as error:
        job['state']='failed';job['error']=str(error);me.par.active=False
    w.store('manual_audio_check',job)
