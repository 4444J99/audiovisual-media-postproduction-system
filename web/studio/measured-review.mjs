import {validateReceipt,verifyComparisonFiles,correspondingTime,makeDecision,MAX_RECEIPT_BYTES} from './measured-review-core.mjs';
import {digest} from '../studies/performance-adapter.mjs';
const $=name=>document.getElementById('measured-'+name),audio=$('audio');
let receipt=null,receiptHash=null,urls=new Map(),role='candidate',comparison=0,request=0,pendingTime=null,intendedPlay=false,events=[],importController=null;
const status=text=>{$('status').textContent=text;};
function disable(value){for(const id of ['comparison','candidate','baseline','record'])$(id).disabled=value;}
function release(){request++;audio.pause();audio.removeAttribute('src');audio.load();for(const url of urls.values())URL.revokeObjectURL(url);urls.clear();receipt=null;receiptHash=null;pendingTime=null;disable(true);}
function position(){if(!receipt)return;const c=receipt.comparisons[comparison],a=receipt.audio_checks.artifacts[c[role+'_id']],sample=(pendingTime??audio.currentTime)*a.sample_rate,s=a.source_map.find(s=>s.output_start<=sample&&sample<s.output_end);
  $('position').textContent=s?`Source sample ${(s.source_start+(sample-s.output_start)*(s.source_end-s.source_start)/(s.output_end-s.output_start)).toFixed(3)} · ${role}`:'Position outside source correspondence';
}
function loadSide(next,time,play){
  const serial=++request;audio.pause();role=next;pendingTime=time;intendedPlay=play;
  for(const side of ['candidate','baseline'])$(side).setAttribute('aria-pressed',String(side===role));
  const loaded=()=>{if(serial!==request)return;audio.currentTime=time;pendingTime=null;position();if(play)audio.play().catch(()=>{if(serial===request)status('Press play to continue the verified comparison.');});};
  audio.addEventListener('loadedmetadata',loaded,{once:true});audio.src=urls.get(receipt.comparisons[comparison].copies[role]);audio.load();position();
}
for(const side of ['candidate','baseline'])$(side).addEventListener('click',()=>{
  if(!receipt||side===role)return;try{const time=correspondingTime(receipt,comparison,role,pendingTime??audio.currentTime);loadSide(side,time,pendingTime===null?!audio.paused:intendedPlay);}catch(error){audio.pause();status(error.message);}
});
$('comparison').addEventListener('change',()=>{comparison=Number($('comparison').value);loadSide('candidate',0,false);});
audio.addEventListener('timeupdate',position);
audio.addEventListener('error',()=>{if(receipt)status('The verified WAV could not play in this browser.');});
audio.addEventListener('play',()=>{for(const item of document.querySelectorAll('video,audio'))if(item!==audio)item.pause();});
for(const id of ['receipt','files'])$(id).addEventListener('change',()=>{importController?.abort();release();status('Selection changed. Verify the receipt and copies to open playback.');});
$('import').addEventListener('click',async()=>{
  importController?.abort();const controller=importController=new AbortController();release();$('import').disabled=true;
  try{const file=$('receipt').files[0];if(!file||file.size>MAX_RECEIPT_BYTES)throw Error('Choose a measured receipt of at most 4 MiB.');
    const bytes=await file.arrayBuffer();controller.signal.throwIfAborted();const report=validateReceipt(JSON.parse(new TextDecoder().decode(bytes)));
    status('Checking local copy hashes and WAV clocks…');const verified=await verifyComparisonFiles(report,[...$('files').files],{signal:controller.signal});
    const identity=await digest(bytes);controller.signal.throwIfAborted();receipt=report;receiptHash=identity;
    for(const [name,{file}]of verified)urls.set(name,URL.createObjectURL(file));$('comparison').replaceChildren();
    report.comparisons.forEach((c,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=`${c.candidate_id} / ${c.baseline_id} · ${c.measured_delta_lu.toFixed(3)} LU`; $('comparison').appendChild(option);});
    $('assessments').textContent=`Imported observations: reference ${report.reference_frame.status}; ${Object.entries(report.qualification).map(([key,value])=>key+' '+value).join('; ')}. Human decisions remain independent.`;
    comparison=0;disable(false);loadSide('candidate',0,false);status('Local hashes and WAV clocks verified. Ready to listen.');$('decisions').textContent=`${events.length} appended decisions retained. Download the log to keep decisions beyond this tab.`;
  }catch(error){if(!controller.signal.aborted){release();status(error.message);}}
  finally{if(importController===controller)$('import').disabled=false;}
});
$('record').addEventListener('click',()=>{try{if(!receipt||pendingTime!==null)throw Error('Wait for the verified copy to load.');
  events.push(makeDecision(receipt,receiptHash,{reviewer:$('reviewer').value,axis:$('axis').value,disposition:$('disposition').value,notes:$('notes').value,comparison,role,time:audio.currentTime},events.length));
  $('export').disabled=false;$('decisions').textContent=`${events.length} appended decisions. Imported assessments are unchanged. Download the log to keep it.`;
}catch(error){status(error.message);}});
$('export').addEventListener('click',()=>{if(!events.length)return;const url=URL.createObjectURL(new Blob([events.map(e=>JSON.stringify(e)).join('\n')+'\n'],{type:'application/x-ndjson'})),link=document.createElement('a');
  link.href=url;link.download='measured-review-decisions.jsonl';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
window.addEventListener('pagehide',()=>{importController?.abort();release();});
