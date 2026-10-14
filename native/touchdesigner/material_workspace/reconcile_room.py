"""Retain historical availability evidence while binding recovered room studies."""
import json
from pathlib import Path


def apply(workspace, room_catalog_path, original_catalog_path):
    recovered=json.loads(Path(room_catalog_path).read_text(encoding='utf-8'))
    original=json.loads(Path(original_catalog_path).read_text(encoding='utf-8'))
    n=workspace.op('container_source_navigation')
    if not n.fetch('room_recovery_previous_gaps',None):n.store('room_recovery_previous_gaps',n.fetch('gaps'))
    gaps=n.fetch('gaps')
    available={a['track_id']:a for a in recovered['assets'] if a['mode']=='room'}
    changed=0
    for i,source_gap in enumerate(original['gaps']):
        track_id=source_gap.get('id')
        if track_id not in available:continue
        row=gaps[i]
        if not row['reason'].startswith(source_gap['title']+':'):
            if row.get('availability')=='recovered':continue
            raise ValueError('Availability record order changed; preserve edits')
        path='base_room_studies/track_room_'+track_id.lower()+'_room'
        row.update(availability='recovered',historical_reason=row['reason'],links=[path],
                   link_labels={path:'Recovered room study · retained hash verified'})
        row['reason']='Recovered · '+source_gap['title']+' · retained bytes matched; listening/producer qualification still open.'
        changed+=1
    for failure in recovered['failures']:
        identity='ROOM-'+failure['track']+'-'+failure['mode']
        if any(g['event_id']==identity for g in gaps):continue
        gaps.append({'event_id':identity,'availability':'unavailable',
                     'reason':f"Room {failure['track']} {failure['mode']}: full download returned HTTP {failure.get('http_status')}; historical hash retained, bytes unavailable."})
    n.store('gaps',gaps)
    table=n.op('table_gaps');table.clear();table.appendRow(['id','availability','ingredient_status'])
    for g in gaps:table.appendRow([g['event_id'],g.get('availability','open'),g['reason']])
    labels=list(n.par.View.menuLabels);labels[list(n.par.View.menuNames).index('gaps')]='Ingredient availability';n.par.View.menuLabels=labels
    page=n.customPages[0]
    for name,label in [('Soundbrowser','Use bank sound'),('Picturebrowser','Use bank picture')]:
        if not hasattr(n.par,name):page.appendToggle(name,label=label)
    n.op('parameter_filters').par.parscope='View Query Person Kind Count Soundbrowser Sound Picturebrowser Picture'
    transport=n.op('parameter_transport');transport.par.parscope='Category Material Play Time Monitor Volume Program';transport.par.h=185
    preview=n.op('container_program');preview.par.y=580;preview.par.h=300
    for kind,endpoint in [('Sound','null_audio'),('Picture','null_picture')]:
        selected="parent.Materials.op(str(parent.Materials.par.Category)+'/'+str(parent.Materials.par.Material))"
        n.op('parameter_'+kind.lower()).par.op.expr=(
            f"({selected} if parent.Navigator.par.{kind}browser and {selected} and {selected}.op('{endpoint}') "
            f"else parent.Materials.op('base_composition/'+str(parent.Navigator.par.{kind})))")
    bank=workspace.op('base_room_studies')
    failures=bank.op('table_unavailable') or bank.create('tableDAT','table_unavailable')
    failures.nodeX=350;failures.nodeY=180;failures.clear();failures.appendRow(['track','mode','http_status','disposition'])
    for f in recovered['failures']:failures.appendRow([f['track'],f['mode'],f.get('http_status'),'Historical context bytes unavailable; no replacement generated'])
    n.op('text_navigation').module.refresh()
    return {'prior_room_warnings_resolved':changed,'room_only_tracks_bound':len(available),
            'context_movies_unavailable':len(recovered['failures']),'ingredient_rows':len(gaps)}
