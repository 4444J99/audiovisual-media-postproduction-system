/** Local review of measured artifacts. Imported observations never grant acceptance. */
import {digest} from '../studies/performance-adapter.mjs';
import {verifyWavHeader} from '../studies/performance-assets.mjs';
const fail=message=>{throw Error(message);};
const number=(n,min=0)=>typeof n==='number'&&Number.isFinite(n)&&n>=min;
const integer=(n,min=0)=>Number.isSafeInteger(n)&&n>=min;
const hash=s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
const basename=s=>typeof s==='string'&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(s)&&!s.includes('..');
const own=(o,k)=>Object.hasOwn(o||{},k);
export const MAX_RECEIPT_BYTES=4*1024*1024,MAX_COPY_BYTES=128*1024*1024;

function artifact(row){
  if(!row||!integer(row.sample_count,1)||!integer(row.sample_rate,1)||row.sample_rate>384000||!integer(row.channels,1)||row.channels>2)fail('Invalid audio clock');
  const map=row.source_map;if(!Array.isArray(map)||!map.length||map.length>4096)fail('Source map required');let end=0;
  for(const segment of map){const {output_start:a,output_end:b,source_start:c,source_end:d}=segment;
    if(![a,b,c,d].every(v=>number(v))||a!==end||b<=a||b>row.sample_count)fail('Gapped or invalid source map');end=b;
  }if(end!==row.sample_count)fail('Incomplete source map');
}
export function validateReceipt(report){
  if(!report||report.schema!=='amps.audio-comparison-receipt.v1'||report.status!=='produced'||report.audio_checks?.status!=='passed')fail('A produced measured review receipt is required');
  if(!hash(report.inputs?.[report.source?.material_id]?.sha256)||!report.qualification||!report.reference_frame)fail('Source identity and independent assessments required');
  if(!Array.isArray(report.comparisons)||!report.comparisons.length||report.comparisons.length>16)fail('Comparisons required');
  let total=0;const seen=new Set();
  for(const c of report.comparisons){
    if(c.within_tolerance!==true||typeof c.measured_delta_lu!=='number'||!number(Math.abs(c.measured_delta_lu))||!number(c.tolerance_lu)||c.tolerance_lu>.5||Math.abs(c.measured_delta_lu)>c.tolerance_lu)fail('Measured loudness does not meet tolerance');
    for(const role of ['candidate','baseline']){const name=c.copies?.[role],id=c[role+'_id'],identity=report.outputs?.[name];
      if(!basename(name)||!name.endsWith('.wav')||!own(report.audio_checks.artifacts,id)||!identity||!hash(identity.sha256)||!integer(identity.bytes,1)||identity.bytes>MAX_COPY_BYTES)fail('Invalid comparison copy identity');
      artifact(report.audio_checks.artifacts[id]);if(!seen.has(name)){seen.add(name);total+=identity.bytes;}
    }
  }if(total>MAX_COPY_BYTES)fail('Comparison files exceed review memory limit');return report;
}
export async function verifyComparisonFiles(receipt,selected,{signal}={}){
  validateReceipt(receipt);const files=new Map(),expected=new Set(receipt.comparisons.flatMap(c=>Object.values(c.copies)));
  for(const file of selected){if(!expected.has(file.name)||files.has(file.name))fail('Unexpected or duplicate local comparison file');files.set(file.name,file);}
  const verified=new Map();
  for(const c of receipt.comparisons)for(const role of ['candidate','baseline']){
    signal?.throwIfAborted();const name=c.copies[role],file=files.get(name),identity=receipt.outputs[name];
    if(!file||file.size!==identity.bytes)fail('Comparison file missing or byte count changed');
    let bytes=verified.get(name)?.bytes;if(!bytes){bytes=await file.arrayBuffer();signal?.throwIfAborted();if(bytes.byteLength!==identity.bytes||await digest(bytes)!==identity.sha256)fail('Comparison file hash mismatch');}
    const a=receipt.audio_checks.artifacts[c[role+'_id']];verifyWavHeader(bytes,{sample_rate:a.sample_rate,samples:a.sample_count,channels:a.channels});
    verified.set(name,{file,bytes});
  }return verified;
}
function sourceAt(row,time){const sample=time*row.sample_rate;if(!number(sample)||sample>=row.sample_count)fail('Playback position is outside this copy');
  const s=row.source_map.find(s=>s.output_start<=sample&&sample<s.output_end);if(!s)fail('Missing source correspondence');
  return s.source_start+(sample-s.output_start)*(s.source_end-s.source_start)/(s.output_end-s.output_start);
}
export function correspondingTime(receipt,index,role,time){
  const c=receipt.comparisons[index];if(!c||!['candidate','baseline'].includes(role))fail('Comparison selection invalid');
  const from=receipt.audio_checks.artifacts[c[role+'_id']],other=role==='candidate'?'baseline':'candidate',to=receipt.audio_checks.artifacts[c[other+'_id']],source=sourceAt(from,time);
  const choices=[];let hold=false;
  for(const s of to.source_map){if(s.source_end===s.source_start){if(source===s.source_start)hold=true;continue;}
    const phase=(source-s.source_start)/(s.source_end-s.source_start);if(phase>=0&&phase<1)choices.push(s.output_start+phase*(s.output_end-s.output_start));}
  if(hold||choices.length!==1)fail('Source correspondence is missing or ambiguous');
  return choices[0]/to.sample_rate;
}
export function makeDecision(receipt,receiptHash,fields,sequence){
  const {reviewer,axis,disposition,notes='',comparison,role,time}=fields;
  if(!hash(receiptHash)||!integer(sequence)||typeof reviewer!=='string'||!reviewer.trim()||reviewer.length>120||!['technical','perceptual','artistic','distribution'].includes(axis)||!['pending','accepted','rejected'].includes(disposition)||typeof notes!=='string'||notes.length>8000||!integer(comparison)||!receipt.comparisons[comparison]||!['candidate','baseline'].includes(role))fail('Complete reviewer and decision fields required');
  const c=receipt.comparisons[comparison],a=receipt.audio_checks.artifacts[c[role+'_id']];
  return {schema:'amps.review-decision.v1',sequence,event:'human-review-decision',recorded_at:new Date().toISOString(),receipt_sha256:receiptHash,
    source_sha256:receipt.inputs[receipt.source.material_id].sha256,copy_sha256:receipt.outputs[c.copies[role]].sha256,comparison,role,source_sample:sourceAt(a,time),
    reviewer:reviewer.trim(),axis,disposition,notes};
}
