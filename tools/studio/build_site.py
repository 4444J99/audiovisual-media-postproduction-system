#!/usr/bin/env python3
"""Build an OWNER-ONLY integration preview; never publishes or downloads.

The live site contains additional registered media, including R2-served assets.
This output is an additive overlay, not permission to delete existing paths.
Protected recovered tools and project snapshots require an owner-only deployment.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile

SOURCE_SHA = 'bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225'
MAIN = 'https://god-here-five-realities.ajpadavano.chatgpt.site/'
LIBRARY_TOOLS = {
    'god-here-study-03-player.html': ('studies/study-03.html', 'study-03'),
    'god-here-study-04-player.html': ('studies/study-04.html', 'study-04'),
    'god-here-study-05-player.html': ('evaluation/index.html', 'evaluation'),
    'god-here-layer-study-03.html': ('studies/layers.html', 'layers'),
}
FONT_SUFFIXES = {'.ttf','.otf','.woff','.woff2','.eot'}

def allowed_asset(path: Path) -> bool:
    return path.suffix.lower() not in FONT_SUFFIXES and not path.is_symlink()

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def require_hash(path: Path, expected: str) -> None:
    if sha256(path) != expected: raise ValueError(f'Identity mismatch: {path.name}')

def copy_exact(src: Path, dest: Path) -> None:
    if not src.is_file() or not allowed_asset(src): raise ValueError(f'Unsupported input: {src.name}')
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src,dest)
    if sha256(src)!=sha256(dest): raise ValueError(f'Copy mismatch: {src.name}')

def mount_record(src: Path, href: str, kind: str, workspace: str|None=None) -> dict:
    row = {'sha256':sha256(src),'bytes':src.stat().st_size,'names':[src.name],'type':kind,
           'links':[{'href':href,'label':'Open preserved exact file'}],
           'decode':'not_applicable','artistic_acceptance':'pending',
           'access':'owner-only integration preview; no publication performed'}
    if workspace:row['workspace']=workspace
    return row

def patch_player(text: str, tool: str) -> str:
    """Retained player derivative: isolate storage and tolerate disabled storage."""
    if tool=='layers': return text
    keys={'study-03':'god-here-study-02-reviews','study-04':'god-here-study-04-reviews','evaluation':'god-here-study-04-reviews'}
    old="'"+keys[tool]+"'"
    if text.count(old)!=2:raise ValueError('Unexpected player storage revision')
    text=text.replace(old,"'god-here-studio-"+tool+"-reviews'")
    if tool=='evaluation':
        old="localStorage.setItem('god-here-evaluation-05-last',JSON.stringify(report));"
        if text.count(old)!=1:raise ValueError('Unexpected evaluation export revision')
        text=text.replace(old,"try{"+old+"}catch{toast('Evaluation exported. Browser-local recovery is unavailable.');}")
    return text

def extract_layouts(archive: Path, dest: Path) -> list[Path]:
    result=[]
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            p=Path(item.filename)
            if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive member')
            if p.suffix!='.mp4':continue
            data=z.read(item)
            if len(data)>16*1024*1024:raise ValueError('Unexpectedly large layout member')
            out=dest/p.name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data);result.append(out)
    return result

def write_json(path:Path,data:dict|list)->None:
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')

def document_page(title:str,text:str)->str:
    # Source content is escaped, never interpreted as trusted markup or script.
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
      '<title>'+html.escape(title)+'</title><style>body{font:16px/1.65 system-ui;margin:32px auto;padding:0 20px;max-width:980px;background:#f6f6f1;color:#22332b}a{color:#275c47}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;border-top:1px solid #ccd5ca;padding-top:24px}h1{font-size:28px}</style>'
      '<a href="../index.html#project">← Project</a><h1>'+html.escape(title)+'</h1><p>Preserved source snapshot. Historical claims are not a current acceptance receipt.</p><pre>'+html.escape(text)+'</pre></html>')

def build(args:argparse.Namespace)->dict:
    repo=Path(__file__).resolve().parents[2];out=Path(args.output)
    if out.exists() and any(out.iterdir()):raise ValueError('Output must be empty; existing sites are never erased')
    out.mkdir(parents=True,exist_ok=True)
    live=Path(args.live_capture);work=Path(args.review_package);lib=Path(args.library)
    require_hash(work/'source/original-film.mp4',SOURCE_SHA)
    mounts={};protected=[];documents=[];sources=[]
    # Current captured site files take precedence over repository snapshots.
    # Never overlay a live media path with a guessed or reconstructed substitute.
    for root in [repo/'web',live]:
        for src in sorted(root.rglob('*')):
            if src.is_file() and allowed_asset(src) and '.git' not in src.parts:
                rel=src.relative_to(root)
                if rel.parts[0]=='studio' and root==live:continue
                copy_exact(src,out/rel)
    old=out/'index.html';rollback=out/'studio/rollback/original-index.html';copy_exact(old,rollback)
    copy_exact(old,out/'experience.html')
    copy_exact(repo/'web/studio/index.template.html',old)
    player=work/'god-here-review-workbench.html'
    copy_exact(player,out/'review-workbench/index.html')
    r=mount_record(player,'/review-workbench/index.html','code','review');mounts[r['sha256']]=r
    for name,kind in [('god-here-character-timeline.xlsx','data'),('workbook-values.json','data'),
                      ('original-film.mp4','video')]:
        src=work/'source'/name;dest='review-workbench/source/'+name;copy_exact(src,out/dest)
        r=mount_record(src,'/'+dest,kind,'review' if kind=='data' else None);mounts[r['sha256']]=r
    for name,kind in [('god-here-character-timeline.json','data'),('god-here-character-timeline.csv','data'),('god-here-character-timeline.md','document')]:
        src=work/'source'/name;dest='review-workbench/source/'+name;copy_exact(src,out/dest)
        r=mount_record(src,'/'+dest,kind,'review');mounts[r['sha256']]=r
    for name,(target,tool) in LIBRARY_TOOLS.items():
        src=lib/name
        if not src.is_file():raise ValueError(f'Required recovered player is missing: {name}')
        if tool=='evaluation':require_hash(src,'68149115437996f8837391e4bad45ce389c92e518a4064613dee9f6d588f675f')
        dest=out/target;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(patch_player(src.read_text(),tool));protected.append('/'+target)
        r=mount_record(dest,'/'+target,'code',tool);r['source_sha256']=sha256(src);r['transformation']='storage namespace isolation; guarded evaluation export; presentation injected by host';mounts[r['sha256']]=r
        if r['sha256']!=sha256(src):
            original=mount_record(src,'/'+target,'code',tool);original['links']=[];original['availability']='privately_preserved';original['derivative_sha256']=r['sha256'];mounts[original['sha256']]=original
    layout_paths=extract_layouts(Path(args.layouts),out/'studio/layout-media')
    if len(layout_paths)!=16:raise ValueError('Expected 16 layout studies; do not publish a partial selector')
    for src in layout_paths:
        r=mount_record(src,'/'+str(src.relative_to(out)),'video','layouts');mounts[r['sha256']]=r
    write_json(out/'studio/layouts.json',[{'filename':p.name,'href':'layout-media/'+p.name,'sha256':sha256(p)} for p in layout_paths])
    # Full text snapshots that actually exist in this runtime, not invented chats.
    for i,src in enumerate(sorted(Path(args.project_texts).glob('*.txt'))):
        if src.stat().st_size>2*1024*1024:continue
        target=f'documents/project-{i+1:02d}.html';(out/'documents').mkdir(exist_ok=True)
        (out/target).write_text(document_page(src.name,src.read_text()))
        raw=f'documents/raw/{src.name}';copy_exact(src,out/raw)
        documents.append({'title':src.name,'path':target,'source_sha256':sha256(src)})
        r=mount_record(src,'/'+raw,'document');mounts[r['sha256']]=r;sources.append({'name':src.name,'sha256':sha256(src)})
    protected.append('/documents/')
    for rel in ['docs/architecture/god-here-consolidation-map.md','docs/recovery/god-here-cross-session-register-2026-10-11.md','docs/ENGINEERING-INTEGRATION.md','docs/PRODUCTION-STATUS.md']:
        src=repo/rel
        if src.exists():
            target='documents/'+src.stem+'.html';(out/target).write_text(document_page(src.stem,src.read_text()))
            documents.append({'title':src.stem.replace('-',' '),'path':target,'source_sha256':sha256(src)})
    # Keep wider historical-document references inspectable, without private locators.
    refs=repo/'manifests/artifacts/god-here-recovered-document-references.json'
    if refs.exists():copy_exact(refs,out/'studio/recovered-document-references.json')
    write_json(out/'studio/mounts.json',mounts)
    catalog=json.loads((out/'recovery/catalog.json').read_text())
    ids={o['sha256'] for key in ['objects','reproductions','retained_outputs','retained_inputs'] for o in catalog.get(key,[])}
    additional=[v for k,v in mounts.items() if k not in ids]
    rows=[
      ('01 · Source, writing & critical studies','Source review + retained documents','Original film, immutable workbook, draft and 174 annotations. Critical studies and semantic/directing notes remain separate from performed wording.',['review']),
      ('02 · Dialogue restoration','Existing comparison tool','Blind original/DSP/neural/blended auditions, source phrases and effects. No listening certification is inferred.',['audio','evaluation']),
      ('03 · Room tone & foley','Existing sound workspaces','Retain assembled bed, A–E studies, ten stretched layers, eight stacks and movement/glass/sip/stove controls. Listening acceptance remains open.',['room','audio']),
      ('04 · Character dialogue & direction','Mounted from this chat','Workbook, original audio/video, waveform, four event lanes per character, grid A1–D3, shot-bound regions and portable notes.',['review']),
      ('05 · Bodies, objects, shadows & room','Recovered player + catalog','Actor/object layer-study interface is restored. Full-film passes, matte revisions, shadow/reflection estimates and unfinished roto remain distinct records.',['layers','library']),
      ('06 · Directed revision & native execution','Code and outputs registered','PR49/50 direction recipes and five verified execution bindings remain preserved. A source note is not automatically a new render. Complete hosted rendering and native-app imports remain open.',['recovery']),
      ('07 · Modular expressive FX','Existing rack retained','13 processors, six patches, routing, automation, bypass/solo, source timing and horizontal/portrait previews. Playback is paused on workspace changes.',['fx','fx-films']),
      ('08 · Independent-time studies','Three exact saved players recovered','Studies03/04/05 retain separate voice/body/word/room clocks, phrase review, audience choices and patch exports. Current protected-site audience records have not been retrieved.',['study-03','study-04','evaluation']),
      ('09 · Horizontal / vertical composition','16 recovered early studies + later catalog','All eight original six-second studies are playable in both orientations. Later full-frame-preserving, stacked and refined studies keep separate catalog identities; these early clips do not replace them.',['layouts','fx-films']),
      ('10 · Color & close-up coverage','Current color tool retained','Color and detail comparisons remain available. Reference photos, generative close-ups, multiple angles and kitchen repair are not claimed as fully recovered moving coverage.',['color']),
      ('11 · Reverse angles & reconstructed performance','Catalogued; partial executable coverage','Preserve reverse-angle studies, generated listeners, lip-sync trials, learned and amplitude-driven mouth versions, comparison films and unaccepted results.',['recovery']),
      ('12 · Full-film, generative & audience editions','Experience + evaluation preserved','Retain interactive five-realities room, linear workprints, seeded editions and source/output mappings. Physical Safari, live audience and installation acceptance remain open.',['experience','evaluation']),
      ('13 · Archive, provenance & session coverage','Evidence-led reconciliation','Frozen content hashes, later reproductions, retained inputs/outputs, recovered text snapshots and missing identities remain visible. An index is not byte recovery, playback or artistic acceptance.',['recovery'])
    ]
    coverage={
      'schema':'god-here-site-coverage/1','date':'2026-10-12','canonical_commit':'3ecdb13a1084c148e253c00fdeee0371de4b45a2',
      'live_publication':False,'target':MAIN,'source_sha256':SOURCE_SHA,
      'qualification':'All '+str(len(ids))+' canonical registered identities and '+str(len(additional))+' newly mounted identities are represented in this preview. The inherited register still has 160 unmatched historical hashes. Only '+str(len(sources))+' distinct mounted project text snapshots were directly copied here; the historical register separately records 823 document records. This is not a claim that every original conversation or work session has been recovered.',
      'stats':[{'value':len(ids)+len(additional),'label':'Identities in combined Library'},{'value':174,'label':'Original timecoded records'},{'value':13,'label':'Mapped workstreams'},{'value':160,'label':'Inherited unmatched hashes'}],
      'workstreams':[{'title':t,'status':s,'description':d,'tools':[x for x in tools if x!='library']} for t,s,d,tools in rows],
      'documents':documents,'directly_copied_text_sources':sources,
      'canonical_identities':len(ids),'new_identity_count':len(additional),'mounted_files':len(mounts),
      'gaps':[
       {'title':'Live main-site publication','detail':'This builder creates a prepared overlay. Consult the current canonical publication receipt for deployed source and hosted verification. Preserve existing media registrations and routes during rollout.'},
       {'title':'Protected evaluation state','detail':'The saved Study05 application is byte-verified and mounted for owner review. Browser-local reviews and audience responses require explicit export from the original browser/origin and import; application recovery does not migrate them.'},
       {'title':'Unrecovered original sessions and files','detail':'160 inherited content hashes remain unmatched. Some located Library files have no authorized raw-byte materialization path. Filename matches and registered references do not close these gaps.'},
       {'title':'Control and device acceptance','detail':'Consult the new verification receipt for the exact tested workflows. Tests are not a blanket claim about every legacy button or physical iPhone/Safari playback.'},
       {'title':'Performance, sound and artistic selection','detail':'Listening-certified words, masks, foley naturalness, reconstructed detail, full-frame editions and artistic acceptance retain their existing unresolved states. Directions never silently mutate source evidence.'},
       {'title':'Public versus owner-only hosting','detail':'Recovered private players and project snapshots must remain protected. Do not publish this owner integration as an anonymous static site. An authenticated main-site audience or protected routes must be established before migration.'}
      ]}
    write_json(out/'studio/coverage.json',coverage)
    inventory=[{'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':sha256(p)} for p in sorted(out.rglob('*')) if p.is_file()]
    manifest={'schema':'god-here-deployment-overlay/1','target':MAIN,'published':False,'delete_existing_paths':False,
              'required_access':'owner-only','protected_paths':protected,
              'source_clock':{'sha256':SOURCE_SHA,'frames':3360,'fps':30},
              'existing_media_policy':'Preserve all existing registered R2 and static media paths. Missing media are not substituted.',
              'rollback':'studio/rollback/original-index.html','files':inventory,'bytes':sum(r['bytes'] for r in inventory)}
    write_json(out/'studio/deployment-manifest.json',manifest)
    return {'site':str(out),'files':len(inventory),'bytes':manifest['bytes'],'mounted_identities':len(mounts),'canonical_identities':len(ids),'new_identities':len(additional),'project_text_snapshots':len(sources),'live_published':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['live-capture','review-package','library','layouts','project-texts','output']:parser.add_argument('--'+name,required=True)
    try:print(json.dumps(build(parser.parse_args()),indent=2))
    except (ValueError,OSError,zipfile.BadZipFile) as exc:parser.exit(1,str(exc)+'\n')
