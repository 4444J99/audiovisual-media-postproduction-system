"""Live GPU-region check; never alter a shader's shared DAT when copying it."""
from pathlib import Path
import json
import numpy as np


def verify(canvas,output):
    if canvas.name!='base_canvas_layout':raise ValueError('Expected the native canvas component')
    field=canvas.op('field_bald');reference=canvas.op('select_reference')
    state={p.name:(p.val,p.mode,p.expr,p.bindExpr) for p in field.customPars}
    enabled={n:(canvas.op('field_'+n).par.Enabled.val,canvas.op('field_'+n).par.Enabled.mode,canvas.op('field_'+n).par.Enabled.expr,canvas.op('field_'+n).par.Enabled.bindExpr) for n in ['bald','cook','left','right','stripe']}
    caption_state=(canvas.par.Captions.val,canvas.par.Captions.mode,canvas.par.Captions.expr,canvas.par.Captions.bindExpr)
    caption_value=bool(canvas.par.Captions);reference_lock=bool(reference.lock)
    workspace=canvas.parent()
    transport=lambda:{'source_play':bool(workspace.par.Play),'monitor':bool(workspace.par.Monitor),'volume':float(workspace.par.Volume),'program':str(workspace.par.Program),'global_play':bool(root.time.play)}
    before_transport=transport()
    created=[];checks={}
    code='uniform vec4 uAnchor; out vec4 fragColor; void main(){vec2 q=(vUV.st-uAnchor.xy)/uAnchor.zw+.5;float a=(all(greaterThanEqual(q,vec2(0)))&&all(lessThanEqual(q,vec2(1))))?1.:0.;fragColor=TDOutputSwizzle(vec4(a));}'
    try:
        reference.cook(force=True);reference.lock=True;canvas.par.Captions=False
        probe=canvas.create('constantTOP','constant_protection_probe');created.append(probe)
        probe.par.colorr=1;probe.par.colorg=0;probe.par.colorb=0;probe.par.alpha=1
        for name in enabled:canvas.op('field_'+name).par.Enabled=False
        before={o:canvas.op('null_'+o).numpyArray().copy() for o in ['landscape','portrait']}
        field.par.Source='base_canvas_layout/'+probe.name;field.par.Enabled=True
        field.par.Lx=.5;field.par.Ly=.5;field.par.Lwidth=2
        field.par.Px=.5;field.par.Py=.5;field.par.Pwidth=2
        for orientation in ['landscape','portrait']:
            shader=canvas.op('glsl_'+orientation);shader.cook(force=True)
            after=canvas.op('null_'+orientation).numpyArray()
            mask=canvas.copy(shader,name='glsl_protection_mask_'+orientation);created.append(mask)
            # copy() retains the source DAT reference. Assign a new DAT first.
            dat=canvas.create('textDAT','text_protection_mask_'+orientation);created.append(dat)
            dat.par.language='glsl';dat.text=code;mask.par.pixeldat=dat.name
            mask.cook(force=True);region=mask.numpyArray()[:,:,0]>.5
            difference=np.max(np.abs(after-before[orientation]),axis=2)
            x,y,w,h=canvas.op('text_layout').module.geometry(canvas,orientation)
            height,width=after.shape[:2]
            checks[orientation]={'dimensions':[width,height],'anchor_rect':[x,y,w,h],
                'pixel_aspect':w*width/(h*height),'anchor_pixels':int(region.sum()),
                'max_anchor_difference_under_opaque_cover':float(difference[region].max()),
                'changed_pixels_outside_anchor':int((difference[~region]>0).sum()),
                'protected':bool(np.all(difference[region]==0))}
    finally:
        def restore(par,saved):
            value,mode,expression,bind=saved
            par.val=value
            if expression:par.expr=expression
            if bind:par.bindExpr=bind
            par.mode=mode
        for key,saved in state.items():restore(getattr(field.par,key),saved)
        for name,saved in enabled.items():restore(canvas.op('field_'+name).par.Enabled,saved)
        restore(canvas.par.Captions,caption_state);reference.lock=reference_lock
        for operator in reversed(created):operator.destroy()
    checks['post_test']={'pixel_file_bindings':[str(canvas.op('glsl_'+o).par.pixeldat.eval().par.file) for o in ['landscape','portrait']],
        'before_transport':before_transport,'after_transport':transport(),'source_transport_changed':transport()!=before_transport,
        'reference_lock_restored':bool(reference.lock)==reference_lock,'captions_restored':bool(canvas.par.Captions)==caption_value}
    Path(output).write_text(json.dumps(checks,indent=2),encoding='utf-8')
    return checks
