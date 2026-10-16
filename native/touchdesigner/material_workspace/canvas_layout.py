"""Native landscape/portrait canvas with a protected complete-frame anchor."""
from pathlib import Path
import json


def dimensions(orientation):
    return (1280,720) if orientation=='landscape' else (720,1280)


def anchor_rect(width,height,aspect,x,y,requested,caption_strip,margin=.02):
    width_norm=min(max(.05,requested),1-2*margin,
                   (1-caption_strip-2*margin)*height*aspect/width)
    height_norm=width_norm*width/aspect/height
    x=min(1-margin-width_norm/2,max(margin+width_norm/2,x))
    y=min(1-margin-height_norm/2,max(caption_strip+margin+height_norm/2,y))
    return x,y,width_norm,height_norm


def geometry(layout,orientation,field=None):
    width,height=dimensions(orientation);prefix='L' if orientation=='landscape' else 'P'
    source=layout.op('select_reference' if field is None else 'select_'+field.name)
    aspect=max(1,source.width)/max(1,source.height)
    owner=layout if field is None else field
    x=float(getattr(owner.par,prefix+'x'));y=float(getattr(owner.par,prefix+'y'))
    size=float(getattr(owner.par,prefix+'width'))
    if field is None:return anchor_rect(width,height,aspect,x,y,size,float(layout.par.Captionstrip))
    crop=crop_rect(field)
    aspect*=crop[2]/crop[3]
    return x,y,size,size*width/aspect/height


def crop_rect(field):
    x=min(.99,max(0,float(field.par.Cropx)));y=min(.99,max(0,float(field.par.Cropy)))
    return x,y,min(1-x,max(.01,float(field.par.Cropwidth))),min(1-y,max(.01,float(field.par.Cropheight)))


def source_time(layout):
    if layout.par.Reference=='performance':
        movie=parent.Materials.op('base_vocabulary/base_player/movie_material')
    else:
        movie=parent.Materials.op('base_original/media_original_film_paired_camera_soundtrack_41f8/movie_material')
    return float(movie.trueIndex)/30


def caption(layout):
    tracks=parent.Materials.op('base_text_tracks')
    if not tracks or not layout.par.Captions or not tracks.op('base_caption').par.Enabled:return ''
    runtime=tracks.op('text_runtime').module
    selected,invalid=runtime.timed(runtime.rows(tracks.op('table_captions')),float(layout.par.Time))
    owner=tracks.op('base_caption')
    if owner.par.Reviewedonly:selected=[r for r in selected if r['reviewed'].lower() in ['true','1','yes']]
    return '\n'.join((r['speaker']+': ' if owner.par.Showspeaker else '')+r['text'] for r in selected)


def install(workspace,code_root):
    if workspace.op('base_canvas_layout'):raise ValueError('Canvas layout exists; preserve edits')
    previous_program=workspace.par.Program.eval()
    code=Path(code_root)/'native/touchdesigner/material_workspace'
    ns={};exec((code/'build.py').read_text(encoding='utf-8'),ns)
    node,custom,expr=[ns[k] for k in ['node','custom','expr']]
    layout=node(workspace,'baseCOMP','base_canvas_layout',3900,-2000,parentshortcut='Canvaslayout')
    custom(layout,'Orientation','Menu','landscape',choices=[('landscape','Landscape · 1280 × 720'),('portrait','Portrait · 720 × 1280')])
    custom(layout,'Reference','Menu','source',choices=[('source','Complete original frame'),('performance','Complete shared performance frame')])
    custom(layout,'Field','Menu','bald',choices=[(n,n.capitalize()+' · recovered layer') for n in ['bald','cook','left','right','stripe']])
    for key,value in [('Lx',.5),('Ly',.56),('Lwidth',.5),('Px',.5),('Py',.58),('Pwidth',.9),('Captionstrip',.2)]:
        custom(layout,key,'Float',value);getattr(layout.par,key).min=0;getattr(layout.par,key).max=1
    for prefix,label in [('L','Landscape'),('P','Portrait')]:
        for key,suffix in [('x','anchor X'),('y','anchor Y'),('width','anchor width')]:getattr(layout.par,prefix+key).label=label+' '+suffix
    layout.par.Captionstrip.min=.08;layout.par.Captionstrip.max=.3;layout.par.Captionstrip.clampMin=True;layout.par.Captionstrip.clampMax=True
    custom(layout,'Captions','Toggle',True)
    custom(layout,'Time','Float',0,readonly=True)
    custom(layout,'Colorstatus','Str','Accepted r2 master unbound; original monochrome reference retained',readonly=True)
    custom(layout,'Status','Str','Reference protected; default actor mattes cover 70–76s; auxiliary tracks retain their own clocks',readonly=True)
    for key,value in [('Backgroundr',.018),('Backgroundg',.025),('Backgroundb',.035)]:custom(layout,key,'Float',value)
    node(layout,'textDAT','text_layout',0,-1400,language='python',file=str(code/'canvas_layout.py'),syncfile=True)
    layout.par.Time.expr="me.op('text_layout').module.source_time(me)"
    records=json.loads(workspace.op('text_source_records').text)
    bindings=node(layout,'tableDAT','table_reference_bindings',0,350)
    bindings.appendRow(['id','operator','source_sha256','state','limit'])
    bindings.appendRow(['original','base_original/media_original_film_paired_camera_soundtrack_41f8/null_picture',records['metadata']['source_video_sha256'],'bound source reference','original surviving edited film'])
    bindings.appendRow(['performance','base_vocabulary/base_player/null_picture',records['metadata']['source_video_sha256'],'bound paired-source decoder','actual source frame; independent auxiliary clocks'])
    bindings.appendRow(['accepted_color_r2','','','unbound exact master/report','prior acceptance recorded in supplied plan; not reconstruction acceptance'])
    reference=node(layout,'selectTOP','select_reference',0,0,top=expr("parent.Materials.op('base_vocabulary/base_player/null_picture') if parent.Canvaslayout.par.Reference=='performance' else parent.Materials.op('base_original/media_original_film_paired_camera_soundtrack_41f8/null_picture')"))
    fields=[];selected=[]
    horizontal=[(.12,.39,.22),(.12,.76,.22),(.88,.39,.22),(.88,.76,.22),(.5,.91,.16)]
    portrait=[(.17,.85,.3),(.5,.85,.3),(.83,.85,.3),(.28,.31,.44),(.72,.31,.44)]
    for i,name in enumerate(['bald','cook','left','right','stripe']):
        field=node(layout,'baseCOMP','field_'+name,0,-250-i*175,parentshortcut='Canvasfield')
        custom(field,'Source','Str','base_composition/layer_actor_'+name+'/null_picture')
        custom(field,'Enabled','Toggle',True);custom(field,'Opacity','Float',1);custom(field,'Rotate','Float',0)
        field.par.Opacity.min=0;field.par.Opacity.max=1;field.par.Opacity.clampMin=True;field.par.Opacity.clampMax=True
        field.par.Rotate.min=-180;field.par.Rotate.max=180
        for prefix,values in [('L',horizontal[i]),('P',portrait[i])]:
            for key,value in zip(['x','y','width'],values):
                custom(field,prefix+key,'Float',value);getattr(field.par,prefix+key).min=-1 if key!='width' else .01;getattr(field.par,prefix+key).max=2
                getattr(field.par,prefix+key).label=('Landscape' if prefix=='L' else 'Portrait')+' '+key
                if key=='width':getattr(field.par,prefix+key).clampMin=True;getattr(field.par,prefix+key).clampMax=True
        for key,value in [('Cropx',0),('Cropy',0),('Cropwidth',1),('Cropheight',1)]:
            custom(field,key,'Float',value);getattr(field.par,key).min=.01 if key in ['Cropwidth','Cropheight'] else 0;getattr(field.par,key).max=1;getattr(field.par,key).clampMin=True;getattr(field.par,key).clampMax=True
        custom(field,'Provenance','Str','Recovered 70–76s actor matte; provisional subject identity; source track settings preserved',readonly=True)
        selected.append(node(layout,'selectTOP','select_'+field.name,350,-250-i*175,top=expr("parent.Materials.op(str(parent.Canvaslayout.op('"+field.name+"').par.Source))")))
        fields.append(field)
    outputs=[]
    for index,orientation in enumerate(['landscape','portrait']):
        width,height=dimensions(orientation)
        text=node(layout,'textTOP','text_caption_'+orientation,350,300+index*175,text=expr("parent.Canvaslayout.op('text_layout').module.caption(parent.Canvaslayout)"),outputresolution='custom',resolutionw=width,resolutionh=expr(str(height)+'*parent.Canvaslayout.par.Captionstrip'),font='Arial',fontsizex=expr("parent.Materials.op('base_text_tracks/base_caption').par.Fontsize"),fontsizexunit='pixels',fontautosize='fitiffat',wordwrap=True,borderspace1=36,borderspace2=12,bgalpha=0,fontalpha=expr("parent.Materials.op('base_text_tracks/base_caption').par.Opacity"))
        shader=node(layout,'glslmultiTOP','glsl_'+orientation,700,-index*350,[reference]+selected+[text],outputresolution='custom',resolutionw=width,resolutionh=height)
        dat=layout.op(shader.name+'_pixel');dat.par.file=str(code/'canvas_layout.glsl');dat.par.syncfile=True
        shader.seq.vec.numBlocks=18
        for i in range(18):
            for letter in 'xyzw':getattr(shader.par,'vec'+str(i)+'value'+letter).val=0
        shader.par.vec0name='uAnchor'
        for i,letter in enumerate('xyzw'):getattr(shader.par,'vec0value'+letter).expr="parent.Canvaslayout.op('text_layout').module.geometry(parent.Canvaslayout,'"+orientation+"')["+str(i)+"]"
        shader.par.vec1name='uCanvas';shader.par.vec1valuex=width;shader.par.vec1valuey=height;shader.par.vec1valuez.expr='parent.Canvaslayout.par.Captionstrip'
        shader.par.vec2name='uBackground';shader.par.vec2valuew=1
        for letter,suffix in zip('xyz','rgb'):getattr(shader.par,'vec2value'+letter).expr='parent.Canvaslayout.par.Background'+suffix
        for i,field in enumerate(fields):
            base=3+i*3;getattr(shader.par,'vec'+str(base)+'name').val='uField'+str(i)
            for j,letter in enumerate('xyzw'):getattr(shader.par,'vec'+str(base)+'value'+letter).expr="parent.Canvaslayout.op('text_layout').module.geometry(parent.Canvaslayout,'"+orientation+"',parent.Canvaslayout.op('"+field.name+"'))["+str(j)+"]"
            getattr(shader.par,'vec'+str(base+1)+'name').val='uCrop'+str(i)
            for j,letter in enumerate('xyzw'):getattr(shader.par,'vec'+str(base+1)+'value'+letter).expr="parent.Canvaslayout.op('text_layout').module.crop_rect(parent.Canvaslayout.op('"+field.name+"'))["+str(j)+"]"
            getattr(shader.par,'vec'+str(base+2)+'name').val='uLook'+str(i)
            getattr(shader.par,'vec'+str(base+2)+'valuex').expr="parent.Canvaslayout.op('"+field.name+"').par.Rotate"
            getattr(shader.par,'vec'+str(base+2)+'valuey').expr="parent.Canvaslayout.op('"+field.name+"').par.Opacity if parent.Canvaslayout.op('"+field.name+"').par.Enabled else 0"
        output=node(layout,'nullTOP','null_'+orientation,875,-index*350,[shader]);node(layout,'outTOP','out_'+orientation,1050,-index*350,[output],connectorder=index)
        outputs.append(output)
        unused=layout.op(shader.name+'_compute')
        if unused:unused.destroy()
    switch=node(layout,'switchTOP','switch_orientation',1225,0,outputs,index=expr("0 if parent.Canvaslayout.par.Orientation=='landscape' else 1"))
    node(layout,'nullTOP','null_picture',1400,0,[switch])
    panel=node(layout,'containerCOMP','container_controls',700,700,w=1280,h=800)
    node(panel,'parameterCOMP','parameter_canvas',0,0,op=expr('parent.Canvaslayout'),builtin=False,custom=True,x=0,y=0,w=350,h=780)
    node(panel,'parameterCOMP','parameter_field',350,0,op=expr("parent.Canvaslayout.op('field_'+str(parent.Canvaslayout.par.Field))"),builtin=False,custom=True,x=360,y=0,w=400,h=780)
    node(panel,'containerCOMP','container_preview',760,0,top=expr("parent.Canvaslayout.op('null_picture')"),topfill='best',x=770,y=100,w=500,h=600)
    program=workspace.par.Program;program.menuNames=list(program.menuNames)+['canvas'];program.menuLabels=list(program.menuLabels)+['Complete-frame canvas']
    program.val=previous_program
    selector=workspace.op('select_program').par.top;old=selector.expr
    selector.expr="parent.Materials.op('base_canvas_layout/null_picture') if parent.Materials.par.Program=='canvas' else ("+old+")"
    return {'outputs':['landscape','portrait'],'fields':5,'reference_last':True,'color_master':'unbound','program':str(workspace.par.Program)}
