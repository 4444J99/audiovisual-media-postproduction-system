import test from 'node:test';
import assert from 'node:assert/strict';
import {validateReceipt,correspondingTime,makeDecision,verifyComparisonFiles} from '../../web/studio/measured-review-core.mjs';
import {createHash} from 'node:crypto';

const sha=b=>createHash('sha256').update(b).digest('hex');
function wav(){const b=Buffer.alloc(44+8*4);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(3,20);b.writeUInt16LE(1,22);b.writeUInt32LE(4,24);b.writeUInt32LE(16,28);b.writeUInt16LE(4,32);b.writeUInt16LE(32,34);b.write('data',36);b.writeUInt32LE(32,40);return b;}
function fixture(){const bytes=wav(),identity={sha256:sha(bytes),bytes:bytes.length};return {schema:'amps.audio-comparison-receipt.v1',status:'produced',study_id:'fixture',comparison_complete:false,
  qualification:{technical:'pending-missing-baselines',perceptual:'pending',artistic:'pending',distribution:'pending'},reference_frame:{status:'passed'},
  outputs:{'candidate.wav':identity,'baseline.wav':identity},inputs:{source:{sha256:'a'.repeat(64),bytes:1}},source:{material_id:'source'},
  audio_checks:{status:'passed',artifacts:{c:{sample_count:8,sample_rate:4,channels:1,source_map:[{output_start:0,output_end:8,source_start:0,source_end:4}]},b:{sample_count:8,sample_rate:8,channels:1,source_map:[{output_start:0,output_end:8,source_start:0,source_end:4}]}}},
  comparisons:[{candidate_id:'c',baseline_id:'b',within_tolerance:true,measured_delta_lu:0,tolerance_lu:.5,copies:{candidate:'candidate.wav',baseline:'baseline.wav'}}]};}
test('switches by corresponding source content, accounting for distinct sample rates',()=>{
  const r=validateReceipt(fixture());assert.equal(correspondingTime(r,0,'candidate',1),.5);assert.equal(correspondingTime(r,0,'baseline',.5),1);
  const changed=fixture();changed.audio_checks.artifacts.b.source_map=[{output_start:0,output_end:4,source_start:0,source_end:4},{output_start:4,output_end:8,source_start:0,source_end:4}];
  assert.throws(()=>correspondingTime(validateReceipt(changed),0,'candidate',1),/ambiguous/);
});
test('reverse and hold maps import; inverse holds and repeated content block ambiguous switches',()=>{
  const r=fixture();r.audio_checks.artifacts.c.source_map[0].source_start=4;r.audio_checks.artifacts.c.source_map[0].source_end=0;
  validateReceipt(r);assert.equal(correspondingTime(r,0,'candidate',.5),.75);assert.equal(correspondingTime(r,0,'baseline',.75),.5);
  r.audio_checks.artifacts.b.source_map[0].source_start=3;r.audio_checks.artifacts.b.source_map[0].source_end=3;
  validateReceipt(r);assert.throws(()=>correspondingTime(r,0,'candidate',.5),/ambiguous/);
  assert.equal(correspondingTime(r,0,'baseline',.5),.5);
});
test('rejects gapped maps, unsafe copies, unsupported receipts and false matching',()=>{
  for(const edit of [r=>r.comparisons[0].copies.candidate='https://example.test/a.wav',r=>r.status='preflight-only',r=>r.audio_checks.artifacts.c.source_map[0].output_start=1,r=>r.comparisons[0].measured_delta_lu=1,r=>r.outputs['candidate.wav'].bytes=2**40]){
    const r=fixture();edit(r);assert.throws(()=>validateReceipt(r));
  }
});
test('only verified actual WAV bytes can enter playback and decoder facts must agree',async()=>{
  const r=fixture();r.audio_checks.artifacts.b.sample_rate=4;const files=['candidate.wav','baseline.wav'].map(name=>new File([wav()],name));
  const verified=await verifyComparisonFiles(validateReceipt(r),files);assert.equal(verified.size,2);
  const changed=[new File([Buffer.alloc(wav().length)],'candidate.wav'),files[1]];
  await assert.rejects(verifyComparisonFiles(r,changed),/hash/);
  r.audio_checks.artifacts.b.sample_rate=8;await assert.rejects(verifyComparisonFiles(r,files),/WAV/);
});
test('decisions bind receipt and source hashes without mutating independent assessments',()=>{
  const r=fixture(),original=JSON.stringify(r);const event=makeDecision(r,'b'.repeat(64),{reviewer:'listener',axis:'perceptual',disposition:'rejected',notes:'Words disappear',comparison:0,role:'candidate',time:.5},2);
  assert.equal(event.sequence,2);assert.equal(event.source_sha256,'a'.repeat(64));assert.equal(event.receipt_sha256,'b'.repeat(64));assert.equal(event.disposition,'rejected');assert.equal(JSON.stringify(r),original);
  assert.throws(()=>makeDecision(r,'b'.repeat(64),{reviewer:'',axis:'technical',disposition:'accepted',comparison:0,role:'candidate',time:0},0));
});
