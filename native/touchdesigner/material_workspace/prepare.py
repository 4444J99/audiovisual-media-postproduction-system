"""Prepare local God-here ingredients. Never execute archived code or publish media."""
import argparse
import base64
import collections
import hashlib
import json
from pathlib import Path
import re
import zipfile
import concurrent.futures
import subprocess
import shutil
from fractions import Fraction

MEDIA = {'.mp4', '.mov', '.m4a', '.wav', '.flac', '.png', '.jpg', '.jpeg'}
SOURCE_SHA = 'bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225'


def category(name, kind):
    value = name.lower()
    if any(s in value for s in ['foley-', '/foley']): return 'foley'
    if any(s in value for s in ['room', 'pause', 'fill-']): return 'room'
    if any(s in value for s in ['mask-', 'mattes', 'alpha']): return 'layers'
    if any(s in value for s in ['color', 'colour', 'detail-', 'face']): return 'color_detail'
    if kind == 'audio': return 'dialogue_audio'
    if any(s in value for s in ['patch-', 'module-', 'fx-', '/renders/']): return 'fx_studies'
    if kind == 'image': return 'reference_images'
    return 'picture_studies'


def prepare(archive_root, output, repository):
    archive_root, output, repository = map(Path, (archive_root, output, repository))
    output.mkdir(parents=True, exist_ok=True)
    assets, seen, gaps = [], {}, []

    def add(path, origin, kind=None, **metadata):
        path = Path(path)
        kind = kind or ('audio' if path.suffix.lower() in {'.wav', '.m4a', '.flac'} else 'image' if path.suffix.lower() in {'.png', '.jpg', '.jpeg'} else 'video')
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha in seen:
            seen[sha]['aliases'].append(origin)
            return seen[sha]
        row = dict(id='m'+sha[:16], title=path.name, path=str(path.resolve()), kind=kind,
                   sha256=sha, bytes=path.stat().st_size, origin=origin, aliases=[],
                   category=category(origin, kind), decision='unselected material', **metadata)
        if sha == SOURCE_SHA:
            row.update(category='original', title='Original film · paired camera soundtrack', decision='untreated source', source_start=0, fps=30)
        assets.append(row); seen[sha] = row
        return row

    for root in [archive_root/'Media and deliverables', archive_root/'Hosted previews/Five realities']:
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix.lower() in MEDIA:
                # Sprite sheets are retained as support data, not mislabelled as moving footage.
                row = add(path, str(path.relative_to(archive_root)))
                if '/atlases/' in str(path): row['category'] = 'atlas_support'

    for package in sorted((archive_root/'Media and deliverables/Packages').glob('*.zip')):
        try:
            z = zipfile.ZipFile(package)
        except zipfile.BadZipFile:
            gaps.append(dict(title=package.name, reason='preserved file is not a readable ZIP'))
            continue
        package_id = hashlib.sha256(package.read_bytes()).hexdigest()[:12]
        target = output/'packages'/package_id
        sequences = collections.defaultdict(list)
        with z:
            for info in z.infolist():
                rel = Path(info.filename)
                if rel.is_absolute() or '..' in rel.parts: raise ValueError('Unsafe package member')
                if rel.suffix.lower() not in MEDIA: continue
                path = target/rel
                path.parent.mkdir(parents=True, exist_ok=True)
                data = z.read(info)
                if path.exists() and path.read_bytes() != data: raise ValueError('Prepared material changed')
                if not path.exists(): path.write_bytes(data)
                match = re.match(r'^(.*?)(\d+)(\.[^.]+)$', rel.name)
                if match and rel.suffix.lower() in {'.png', '.jpg'}:
                    sequences[(str(rel.parent), match[1], match[3])].append(path)
                else: add(path, package.name+' :: '+info.filename)
            for (directory, prefix, suffix), members in sequences.items():
                if len(members) < 3:
                    for path in members: add(path, package.name+' :: '+str(path.relative_to(target)))
                    continue
                folder = target/'sequences'/hashlib.sha256((directory+prefix+suffix).encode()).hexdigest()[:12]
                folder.mkdir(parents=True, exist_ok=True)
                digests = []
                for path in sorted(members):
                    data = path.read_bytes(); digests.append(hashlib.sha256(data).hexdigest())
                    dest = folder/path.name
                    if not dest.exists(): dest.write_bytes(data)
                sha = hashlib.sha256(''.join(digests).encode()).hexdigest()
                if sha in seen: continue
                layer = 'layer-study-03' in package.name
                row = dict(id='m'+sha[:16], title=f'{package.stem} · {directory}/{prefix} ({len(members)} frames)',
                           path=str(folder.resolve()), kind='sequence', sha256=sha,
                           category='layers', origin=package.name+' :: '+directory+'/'+prefix,
                           aliases=[], decision='unselected workprint sequence', frames=len(members),
                           fps=12 if layer else 15, source_start=24 if layer else 70)
                assets.append(row); seen[sha] = row

    # Existing portable studies contain recoverable audio data, not only finished videos.
    page = archive_root/'Media and deliverables/Other files/god-here-independent-time-player.html'
    text = page.read_text(encoding='utf-8'); marker = 'window.STUDY_DATA='
    data, _ = json.JSONDecoder().raw_decode(text, text.index(marker)+len(marker))
    for name, uri in data.get('audio', {}).items():
        if not isinstance(uri, str) or not uri.startswith('data:'): continue
        header, payload = uri.split(',', 1)
        suffix = '.wav' if 'wav' in header else '.m4a'
        dest = output/'portable-study-02'/ (name+suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = base64.b64decode(payload)
        if not dest.exists(): dest.write_bytes(content)
        add(dest, page.name+' :: '+name)

    page = archive_root/'Media and deliverables/Other files/god-here-review-workbench.html'
    text = page.read_text(encoding='utf-8'); marker = '<script id="project-data" type="application/json">'
    review, _ = json.JSONDecoder().raw_decode(text, text.index(marker)+len(marker))
    (output/'source-records.json').write_text(json.dumps(review['timeline'], indent=2), encoding='utf-8')
    (output/'independent-time-data.json').write_text(json.dumps({k:v for k,v in data.items() if k not in ['audio','pictures','alphas']}, indent=2), encoding='utf-8')

    room = json.loads((repository/'web/room-tone/media.json').read_text())
    for track in room['tracks']:
        # The wider catalogue is not present in the preserved hosted capture.
        url = track.get('media', {}).get('room', {}).get('url')
        if url and not any(Path(a['path']).name == Path(url).name for a in assets):
            gaps.append(dict(title='Room · '+track['title'], id=track['id'], reason='registered track absent from local material', expected=url))
    def probe(a):
        if a['kind'] in ['image','sequence'] or not shutil.which('ffprobe'): return
        try:
            d=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type,sample_rate,avg_frame_rate:format=duration','-of','json',a['path']],timeout=5))
            a['duration']=float(d.get('format',{}).get('duration',0))
            for stream in d.get('streams',[]):
                if stream['codec_type']=='audio':a['sample_rate']=int(stream['sample_rate'])
                if stream['codec_type']=='video' and stream.get('avg_frame_rate') not in [None,'0/0']:a['playback_fps']=float(Fraction(stream['avg_frame_rate']))
        except Exception as error:a['probe_error']=type(error).__name__
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(probe,assets))
    for a in assets:
        if ' :: ' in a['origin'] and a['kind']!='sequence':a['title']=a['origin'].split(' :: ')[0].removesuffix('.zip')+' · '+a['title']
        slug=re.sub('[^a-z0-9]+','_',a['title'].lower()).strip('_')
        a['node_name']=('layer_' if a['kind']=='sequence' else 'track_' if a['kind']=='audio' else 'media_')+slug[:48]+'_'+a['id'][-4:]
    result = dict(schema='god-here.native-material-workspace/1', assets=assets, gaps=gaps,
                  source_sha256=SOURCE_SHA, source_records=str((output/'source-records.json').resolve()),
                  independent_time_data=str((output/'independent-time-data.json').resolve()),
                  policy='All versions are reusable exercises; no treatment selected.')
    (output/'catalog.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'assets':len(assets),'categories':dict(collections.Counter(a['category'] for a in assets)), 'gaps':len(gaps)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive-root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--repository', required=True)
    args = parser.parse_args()
    prepare(args.archive_root, args.output, args.repository)
