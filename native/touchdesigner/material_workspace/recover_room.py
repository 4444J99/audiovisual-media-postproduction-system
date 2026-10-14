"""Recover retained room studies by exact hash; credentials stay in stdin/memory."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import termios
import time
import urllib.parse
import urllib.request


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':raise ValueError('Insecure media redirect')
        request=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            request.remove_header('Oai-sites-authorization')
        return request


def recover(repository, output, credentials):
    repository,output=Path(repository),Path(output)
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    receipt=json.loads((repository/'manifests/acceptance/2026-10-12/retained-room-identity-audit.json').read_text())
    prepared=json.loads((repository/'manifests/acceptance/2026-10-12/prepared-media-decode.json').read_text())
    sizes={r['path']:r['bytes'] for r in prepared['identities']}
    labels={r['id']:r for r in json.loads((repository/'web/room-tone/media.json').read_text())['tracks']}
    assert len(receipt['track_media'])==60
    assert sum(sizes[r['retained_path']] for r in receipt['track_media'])<200_000_000
    assert urllib.parse.urlsplit(credentials['base']).scheme=='https'
    deadline=time.monotonic()+240

    def one(row):
        if time.monotonic()>deadline:raise TimeoutError('Recovery deadline')
        sha=row['observed_sha256'];size=sizes[row['retained_path']]
        relative=row['retained_path'].removeprefix('public/')
        if '..' in Path(relative).parts:raise ValueError('Unsafe media path')
        destination=output/sha[:12]/Path(relative).name
        destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        digest=hashlib.sha256()
        if destination.exists():
            digest.update(destination.read_bytes())
        else:
            request=urllib.request.Request(credentials['base'].rstrip('/')+'/'+relative,
                headers={'OAI-Sites-Authorization':credentials['token']})
            partial=destination.with_name(destination.name+f'.partial-{time.time_ns()}')
            count=0
            with urllib.request.build_opener(SafeRedirect).open(request,timeout=15) as response, partial.open('xb') as target:
                while block:=response.read(1024*1024):
                    if time.monotonic()>deadline:raise TimeoutError('Recovery deadline')
                    count+=len(block)
                    if count>size:raise ValueError('Response exceeds retained size')
                    target.write(block);digest.update(block)
            if count!=size or digest.hexdigest()!=sha:raise ValueError('Retained identity mismatch')
            partial.rename(destination)
        if destination.stat().st_size!=size or digest.hexdigest()!=sha:raise ValueError('Existing local identity mismatch')
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
            'stream=codec_type,sample_rate,avg_frame_rate:format=duration','-of','json',str(destination)],timeout=8))
        label=labels.get(row['track_id'],{})
        asset={'id':'m'+sha[:16],'node_name':('media_' if destination.suffix=='.mp4' else 'track_')+'room_'+row['track_id'].lower()+'_'+row['mode'],
            'title':row['track_id']+' · '+label.get('title',row['track_id'])+' · '+row['mode'],
            'kind':'video' if destination.suffix=='.mp4' else 'audio','path':str(destination.resolve()),
            'sha256':sha,'bytes':size,'duration':float(probe['format']['duration']),
            'source_start':label.get('sourceStart',0),'origin':relative,
            'category':'room_studies','decision':'Historical study; byte identity verified. Listening and producer qualification remain open.',
            'description':label.get('description',''),'family':label.get('group','reference'),
            'mode':row['mode'],'track_id':row['track_id'],'producer_binding_status':row['producer_binding_status']}
        for stream in probe['streams']:
            if stream['codec_type']=='audio':asset['sample_rate']=int(stream['sample_rate'])
            if stream['codec_type']=='video':
                numerator,denominator=map(int,stream['avg_frame_rate'].split('/'));asset['fps']=numerator/denominator
        return asset

    assets=[];failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs={pool.submit(one,r):r for r in receipt['track_media']}
        for job in concurrent.futures.as_completed(jobs):
            row=jobs[job]
            try:assets.append(job.result())
            except Exception as error:failures.append({'track':row['track_id'],'mode':row['mode'],
                                                       'error':type(error).__name__,'http_status':getattr(error,'code',None)})
    result={'schema':'god-here.recovered-room-studies/1','assets':sorted(assets,key=lambda a:a['node_name']),
            'failures':failures,'source_sha256':receipt['source_sha256'],'policy':'Retained bytes; no new renders or acceptance claims.'}
    (output/'catalog.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'verified':len(assets),'bytes':sum(a['bytes'] for a in assets),'failures':failures}))
    return result


if __name__=='__main__':
    if sys.stdin.isatty():
        settings=termios.tcgetattr(sys.stdin);settings[3]&=~termios.ECHO
        termios.tcsetattr(sys.stdin,termios.TCSANOW,settings)
    recover(sys.argv[1],sys.argv[2],json.loads(sys.stdin.readline()))
