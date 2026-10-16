"""Stable-path native layout; all bounds are derived from actual node sizes."""
GROUPS = [
    ('sources','01 Sources',[.25,.28,.35],[
        'base_original','base_dialogue_audio','base_room','base_foley','base_layers',
        'base_picture_studies','base_color_detail','base_fx_studies',
        'base_reference_images','base_atlas_support','base_room_studies'],25,0,3,550,200),
    ('start','02 Start here',[.22,.33,.22],[
        'container_controls','container_source_navigation'],1555,0,3,500,200),
    ('compose','03 Compose',[.30,.22,.33],[
        'base_composition','base_canvas_layout','base_fx_rack','base_text_tracks',
        'base_vocabulary','base_generated_scene'],1555,-300,3,500,200),
    ('picture','04 Picture output',[.25,.28,.35],[
        'composite_layers','null_composition','select_program','null_program','out_picture'],2985,0,3,500,200),
    ('audio','05 Audio output',[.22,.33,.22],[
        'select_audio_interval','script_mix','math_master','null_audio','out_audio','audio_monitor'],2985,-550,6,500,200),
    ('catalog','06 Catalog and recipes',[.25,.28,.35],[
        'table_materials','text_source_records','table_missing','base_fx_recipe_data'],25,-1000,3,550,200),
    ('support','07 Runtime support',[.25,.28,.35],[
        'base_audio_clock','text_mix','parexec_materials','text_audio_intervals'],2985,-1050,3,500,200),
    ('diagnostics','08 Diagnostics - idle',[.35,.30,.18],[
        'base_execution_test','base_scene_soak','base_fx_temporal_test',
        'base_fx_temporal_attempt1','execute_audio_check'],25,-1700,5,900,200),
]


def arrange(workspace):
    groups=[];assigned=set()
    for key,title,color,names,x,y,columns,dx,dy in GROUPS:
        nodes=[]
        for index,name in enumerate(names):
            node=workspace.op(name)
            if node is None:raise ValueError('Expected working node missing: '+name)
            if node.isCOMP:node.nodeWidth=360 if node.OPType=='containerCOMP' else 300
            node.nodeX=x+(index%columns)*dx
            node.nodeY=y-(index//columns)*dy
            nodes.append(node);assigned.add(name)
        if key=='picture':
            # Explicit parallel composition and selected-program paths.
            for name,px,py in [('composite_layers',2985,0),('null_composition',3485,0),
                               ('select_program',2985,-200),('null_program',3485,-200),('out_picture',3985,-200)]:
                node=workspace.op(name);node.nodeX=px;node.nodeY=py
        if key=='audio':
            workspace.op('out_audio').nodeX=4985;workspace.op('out_audio').nodeY=-450
            workspace.op('audio_monitor').nodeX=4985;workspace.op('audio_monitor').nodeY=-650
        left=min(n.nodeX for n in nodes)-25
        bottom=min(n.nodeY for n in nodes)-25
        right=max(n.nodeX+n.nodeWidth for n in nodes)+25
        top=max(n.nodeY+n.nodeHeight for n in nodes)+85
        if key in ('start','compose'):right=max(right,2880)
        if key=='catalog':right=max(right,1450)
        if key=='picture':
            top=max(top,215)
        if key in ('picture','audio','support','diagnostics'):right=max(right,5140)
        groups.append({'name':'annotate_'+key,'title':title,'color':color,
                       'position':[left,bottom],'size':[right-left,top-bottom],
                       'nodes':names})
    unassigned=[n.name for n in workspace.children
                if n.OPType!='annotateCOMP' and n.name not in assigned]
    if unassigned:raise ValueError('Unclassified workspace nodes: '+', '.join(unassigned))
    return groups


def verify(workspace,groups):
    boxes=[];errors=[]
    for group in groups:
        a=workspace.op(group['name'])
        if a is None:errors.append('Missing annotation '+group['name']);continue
        boxes.append(a)
        for name in group['nodes']:
            n=workspace.op(name)
            if not (n.nodeX>=a.nodeX+25 and n.nodeX+n.nodeWidth<=a.nodeX+a.nodeWidth-25
                    and n.nodeY>=a.nodeY+25 and n.nodeY+n.nodeHeight<=a.nodeY+a.nodeHeight-85):
                errors.append('Annotation containment: '+n.path)
    for i,a in enumerate(boxes):
        for b in boxes[i+1:]:
            if not (a.nodeX+a.nodeWidth+20<=b.nodeX or b.nodeX+b.nodeWidth+20<=a.nodeX
                    or a.nodeY+a.nodeHeight+20<=b.nodeY or b.nodeY+b.nodeHeight+20<=a.nodeY):
                errors.append('Annotation overlap: '+a.name+' / '+b.name)
    return errors
