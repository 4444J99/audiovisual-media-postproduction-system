/** Exercise actual UI handlers with local Files; no native browser claim. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
class Element extends EventTarget{
  constructor(){super();this.value='';this.textContent='';this.files=[];this.children=[];this.paused=true;this.currentTime=0;this.attributes={};}
  setAttribute(k,v){this.attributes[k]=v;}removeAttribute(k){delete this.attributes[k];}
  appendChild(child){this.children.push(child);}replaceChildren(){this.children=[];}click(){this.dispatchEvent(new Event('click'));}
  pause(){this.paused=true;}load(){}play(){this.paused=false;this.dispatchEvent(new Event('play'));return Promise.resolve();}
}
function wave(){const b=Buffer.alloc(76);b.write('RIFF');b.writeUInt32LE(68,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(3,20);b.writeUInt16LE(1,22);b.writeUInt32LE(4,24);b.writeUInt32LE(16,28);b.writeUInt16LE(4,32);b.writeUInt16LE(32,34);b.write('data',36);b.writeUInt32LE(32,40);return b;}
test('actual review handlers verify Files, preserve rapid-switch intent and append hash-bound decisions',async()=>{
  const oldDocument=globalThis.document,oldWindow=globalThis.window,oldCreate=URL.createObjectURL,oldRevoke=URL.revokeObjectURL;
  const nodes=new Map(),get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);},audio=get('measured-audio'),peer=new Element(),blobs=[];
  globalThis.document={getElementById:get,querySelectorAll:()=>[audio,peer],createElement:()=>new Element()};globalThis.window=new EventTarget();
  URL.createObjectURL=blob=>{blobs.push(blob);return 'blob:test-'+blobs.length;};URL.revokeObjectURL=()=>{};
  try{
    await import('../../web/studio/measured-review.mjs');
    const bytes=wave(),sha=createHash('sha256').update(bytes).digest('hex'),row={sample_rate:4,sample_count:8,channels:1,source_map:[{output_start:0,output_end:8,source_start:0,source_end:8}]};
    const receipt={schema:'amps.audio-comparison-receipt.v1',status:'produced',source:{material_id:'source'},inputs:{source:{sha256:'a'.repeat(64)}},
      qualification:{technical:'pending',perceptual:'pending',artistic:'pending',distribution:'pending'},reference_frame:{status:'not_tested'},
      outputs:{'c.wav':{sha256:sha,bytes:76},'b.wav':{sha256:sha,bytes:76}},audio_checks:{status:'passed',artifacts:{c:row,b:row}},
      comparisons:[{candidate_id:'c',baseline_id:'b',within_tolerance:true,measured_delta_lu:0,tolerance_lu:.5,copies:{candidate:'c.wav',baseline:'b.wav'}}]};
    get('measured-receipt').files=[new File([JSON.stringify(receipt)],'comparisons.json')];get('measured-files').files=['c.wav','b.wav'].map(name=>new File([bytes],name));
    get('measured-import').click();
    const deadline=Date.now()+1000;while(get('measured-import').disabled&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,5));
    assert.match(get('measured-status').textContent,/hashes and WAV clocks verified/);
    audio.dispatchEvent(new Event('loadedmetadata'));audio.currentTime=1;await audio.play();
    get('measured-baseline').click();assert.equal(audio.paused,true);get('measured-candidate').click();audio.dispatchEvent(new Event('loadedmetadata'));
    assert.equal(audio.paused,false);assert.equal(audio.currentTime,1);
    get('measured-reviewer').value='fixture listener';get('measured-axis').value='perceptual';get('measured-disposition').value='rejected';get('measured-notes').value='fixture decision';
    get('measured-record').click();assert.match(get('measured-decisions').textContent,/1 appended/);get('measured-export').click();
    const event=JSON.parse(await blobs.at(-1).text());assert.equal(event.source_sha256,'a'.repeat(64));assert.equal(event.copy_sha256,sha);assert.equal(event.disposition,'rejected');assert.equal(event.source_sample,4);
    assert.equal(receipt.qualification.perceptual,'pending');
  }finally{globalThis.window.dispatchEvent(new Event('pagehide'));globalThis.document=oldDocument;globalThis.window=oldWindow;URL.createObjectURL=oldCreate;URL.revokeObjectURL=oldRevoke;}
});
