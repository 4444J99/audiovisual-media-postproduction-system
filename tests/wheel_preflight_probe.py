"""Synthetic native preflights and FX render in an isolated wheel consumer."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import wave

import amp
from amp.execution import CODE_FILES, COMMON_CODE, REPO_ROOT, execute, preflight
from amp.media_resolver import ContractError, file_identity
from amp.runtime import runtime_path


def write_json(path,data):
    path.write_text(json.dumps(data));return path


def main(root):
    # These are generated test pixels/tones, never artwork or private source.
    source=root/'source.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=black:s=64x64:r=30:d=1',
                    '-f','lavfi','-i','sine=frequency=220:sample_rate=48000:duration=1','-ac','2',
                    '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
    source_ref=file_identity(source,'source');source_hash=source_ref['sha256']
    clock={'sha256':source_hash,'frames':30,'frame_rate':{'num':30,'den':1}}
    objects={source_hash:str(source)}
    def reference(path):
        identity=file_identity(path,'fixture');objects[identity['sha256']]=str(path);return identity
    def binding(adapter,inputs,options,number):
        return {'schema_version':'amps.execution.v1','id':'wheel-'+adapter.split('.')[1],
                'adapter':adapter,'upstream':{'pull_request':number,'commit':'a'*40},
                'source_clock':clock,'inputs':inputs,'options':options}

    inventory=write_json(root/'inventory.json',{'source_sha256':source_hash,'sample_rate':48000,'channels':2,
                          'pauses':[{'id':'pause','usable_portions':[{'start':.1,'end':.3}]}]})
    inventory_ref=reference(inventory)
    report=write_json(root/'report.json',{
        'schema_version':'amps.room-stretch.v1','source_sha256':source_hash,
        'pause_inventory_sha256':inventory_ref['sha256'],'duration_seconds':1,'sample_rate':48000,
        'channels':2,'samples_per_channel':48000,'production_target_lufs':-40,'audition_boost_db':14,
        'source_reel':{'seam_window_seconds':.005,'processed_samples_per_channel':9600,
                       'portions':[{'source_start_sample':4800,'source_end_sample':14400,
                                    'reel_start_sample':0,'reel_end_sample':9600}]},
        'layers':[{'mode':'literal_varispeed','period_seconds':1,'period_samples':48000,'film_edge_fade_seconds':.01}]})
    room_binding=write_json(root/'room-binding.json',binding('amp.roomstretch.v1',
        {'source':source_ref,'inventory':inventory_ref,'parameter_report':reference(report)},{},53))

    assets=root/'assets';assets.mkdir()
    media={'schemaVersion':'1.0.0','originalFilmSha256':source_hash,'sourceIn':0,'sourceOut':1,'duration':1,
           'fps':12,'frameCount':12,'frameAddressing':'floor-time-times-fps','framesPerPage':12,'columns':12,
           'picture':{'pages':['picture.png'],'width':64,'height':64},
           'matte':{'pages':['matte.png'],'width':64,'height':64},'room':{'hybrid':'room.png'},
           'regions':'regions.json','cues':'cues.json','provenance':'provenance.json','waveforms':'waveforms.json',
           'audio':{'sampleRate':48000,'source':'source.wav','reference':'reference.wav'}}
    write_json(assets/'manifest.json',media)
    write_json(assets/'regions.json',{'items':[{'id':'all'}]})
    write_json(assets/'cues.json',[]);write_json(assets/'waveforms.json',{})
    write_json(assets/'provenance.json',{'source':{'sha256':source_hash}})
    from PIL import Image
    Image.new('RGB',(768,64),'red').save(assets/'picture.png')
    Image.new('RGB',(768,64),'black').save(assets/'matte.png')
    Image.new('RGB',(64,64),'blue').save(assets/'room.png')
    for name,sample in (('source.wav',b'\x00\x01'),('reference.wav',b'\x00\x02')):
        with wave.open(str(assets/name),'wb') as wav:
            wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(sample*48000*2)
    asset_receipt=write_json(root/'assets-receipt.json',{'files':[
        {'path':path.name,**file_identity(path,'asset')} for path in sorted(assets.iterdir())]})
    asset_ref=reference(asset_receipt)
    patch=write_json(root/'patch.json',{'schemaVersion':'1.0.0','id':'wheel','name':'Wheel fixture','seed':1,'duration':1,
        'source':{'id':'synthetic','sha256':source_hash,'offset':0,'duration':1},
        'nodes':[{'id':'source','type':'source'},{'id':'output','type':'output','gain':1}],
        'connections':[{'from':'source','to':'output','port':port,'gain':1,'role':'insert'}
                       for port in ('audio','picture','text','matte')],'events':[]})
    native_font=('/System/Library/Fonts/Supplemental/Arial.ttf' if sys.platform=='darwin'
                 else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    font=Path(os.environ.get('AMP_TEST_FONT',native_font))
    fx_binding=write_json(root/'fx-binding.json',binding('fx.rack.v1',
        {'recipe':reference(patch),'asset_receipt':asset_ref,'font':reference(font)},
        {'width':64,'height':64,'fps':12,'duration':1,'overlay':'none','audio_input':'reference'},51))
    locations={'objects':objects,'collections':{asset_ref['sha256']:str(assets)}}
    fx=preflight(fx_binding,locations=locations)
    room=preflight(room_binding,locations=locations)
    # Both selected and unselected audio, plus waveform metadata, are consumed
    # by the renderer's asset identity. Missing or changed bytes must fail now,
    # before a render directory or native process is created.
    for name in ('source.wav','reference.wav','waveforms.json'):
        member=assets/name;original=member.read_bytes();member.unlink()
        try:
            try:preflight(fx_binding,locations=locations)
            except ContractError as error:assert error.code=='missing_dependency'
            else:raise AssertionError(f'Missing asset accepted: {name}')
        finally:member.write_bytes(original)
        member.write_bytes(original+b'changed')
        try:
            try:preflight(fx_binding,locations=locations)
            except ContractError as error:assert error.code=='input_identity_mismatch'
            else:raise AssertionError(f'Changed asset accepted: {name}')
        finally:member.write_bytes(original)
    for plan in (fx,room):
        assert plan.receipt()['status']=='preflight_passed'
        assert plan.code['git_commit'] is None
        assert {r['path'] for r in plan.code['files']}==set(COMMON_CODE+CODE_FILES[plan.binding['adapter']])
        for row in plan.code['files']:
            assert file_identity(runtime_path(REPO_ROOT,row['path']),'code')=={k:row[k] for k in ('sha256','bytes')}
        assert Path(plan.argv(root/'products')[1]).is_relative_to(REPO_ROOT/'amp/_runtime')
    result=execute(fx,root/'fx-execution')
    assert result['status']=='render_verified' and result['render_executed'] is True
    staged=root/'fx-execution/inputs/assets'
    assert set(fx.asset_members)=={path.name for path in assets.iterdir()}
    for name in fx.asset_members:assert (staged/name).read_bytes()==(assets/name).read_bytes()
    native=json.loads((root/'fx-execution/products/render.render.json').read_text())
    assert {row['path'] for row in native['assetsIdentity']['files']}==set(fx.asset_members)-{'manifest.json'}
    for row in native['assetsIdentity']['files']:
        assert file_identity(staged/row['path'],'staged')=={key:row[key] for key in ('sha256','bytes')}
    # The packaged Python producer imports successfully from the same environment.
    subprocess.run([*room.argv(root/'products')[:2],'--help'],check=True,capture_output=True,text=True)
    # A broken installation must fail rather than consume checkout/sibling code.
    producer=runtime_path(REPO_ROOT,'tools/run_room_stretch.py');backup=producer.with_suffix('.saved')
    producer.rename(backup)
    try:
        try:preflight(room_binding,locations=locations)
        except ContractError as error:assert error.code=='missing_dependency'
        else:raise AssertionError('Missing installed producer was accepted')
    finally:backup.rename(producer)
    print(json.dumps({'package':amp.__file__,'adapters':[fx.binding['adapter'],room.binding['adapter']],
        'fx_frames':fx.clock['output']['frames'],'room_samples':room.clock['output']['samples_per_channel'],
        'all_code_identities_match_installed_bytes':True,'missing_producer_rejected':True,
        'fx_render_verified':True,'complete_asset_pack_staged':True,'asset_dependency_failures_rejected':True}))


if __name__=='__main__':main(Path(sys.argv[1]))
