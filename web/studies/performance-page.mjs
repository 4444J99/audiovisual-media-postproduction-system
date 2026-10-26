import {PerformancePlayer,RuntimeSupervisor,validateRecord} from './performance-adapter.mjs';
import {loadPreparedFiles,verifyRetainedEngine,disposePrepared} from './performance-assets.mjs';

const $=id=>document.getElementById(id);
let player=null,record=null,recovery=null,prepared=null,context=null,abort=null,sequence=0,preparing=false;
function status(text){$('status').textContent=text;}
function controls(){const ready=!!player,state=player?.supervisor.status;for(const id of ['pause','checkpoint','export-record'])$(id).disabled=!ready;$('play').disabled=!ready||['finished','cancelled'].includes(state)||player.supervisor.playing||player.playPending;$('seek').disabled=!ready||state==='cancelled';for(const id of ['record','assets'])$(id).disabled=preparing;$('prepare').disabled=preparing||!record||!$('assets').files.length;$('cancel').disabled=!preparing&&!ready;}
function pause(){sequence++;abort?.abort();if(preparing){preparing=false;status('Preparation paused. Select Prepare playback to try again.');}player?.pause();controls();}
function suspend(){sequence++;abort?.abort();preparing=false;player?.suspend();controls();}
function reset(){pause();player?.cancel();player=null;disposePrepared(prepared);prepared=null;}
$('record').addEventListener('change',async()=>{reset();record=recovery=null;const mine=++sequence;
  try{const file=$('record').files[0];if(!file)return;if(file.size>20*1024*1024)throw Error('Performance record exceeds the import limit');const data=JSON.parse(await file.text());if(mine!==sequence)return;
    if(data.schema==='amps.performance-browser-checkpoint.v1'){await RuntimeSupervisor.restore(data);if(mine!==sequence)return;recovery=data;record=data.record;}else record=data;
    validateRecord(record);$('seek').max=record.runtime.duration_frames;$('seek').value=recovery?.state.frame||0;
    status(record.runtime.profile.admitted?'Record loaded. Select its prepared folder, then Prepare playback.':'This record is saved. Playback needs its source owner to admit measured resource limits.');
  }catch(error){if(mine===sequence){record=recovery=null;status(error.message);}}finally{if(mine===sequence)controls();}
});
$('assets').addEventListener('change',controls);
$('prepare').addEventListener('click',async()=>{
  reset();const mine=++sequence;abort=new AbortController();const signal=abort.signal;preparing=true;controls();status('Verifying the retained engine and prepared media...');
  let loaded=null;
  try{context??=new AudioContext();await verifyRetainedEngine(record);signal.throwIfAborted();loaded=await loadPreparedFiles(record,$('assets').files,context,{signal});if(mine!==sequence){disposePrepared(loaded);return;}
    const next=new PerformancePlayer({record,prepared:loaded,canvas:$('stage'),audioContext:context});if(recovery)await next.restore(recovery);if(mine!==sequence){next.cancel();disposePrepared(loaded);return;}
    prepared=loaded;player=next;player.rotate($('orientation').value);status('Ready. Press Play to begin or resume.');
  }catch(error){disposePrepared(loaded);if(mine===sequence)status(error.name==='AbortError'?'Preparation cancelled.':error.message);}
  finally{if(mine===sequence){preparing=false;controls();}}
});
$('play').addEventListener('click',async()=>{const current=player;try{const pending=current.play();controls();await pending;if(player===current&&current.supervisor.playing)status(current.supervisor.reasons.length?'Playing qualified fallback: '+current.supervisor.reasons.join(', '):'Playing.');}catch(error){if(player===current)status(error.message);}finally{controls();}});
$('pause').addEventListener('click',()=>{pause();status('Paused. Your record and position are retained.');});
$('cancel').addEventListener('click',()=>{pause();player?.cancel();status('Cancelled. Save the performed record or prepare the saved performance again.');controls();});
$('seek').addEventListener('input',()=>{try{player.seek(Number($('seek').value));controls();}catch(error){status(error.message);}});
$('orientation').addEventListener('change',()=>{try{player?.rotate($('orientation').value);}catch(error){status(error.message);}});
function download(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('checkpoint').addEventListener('click',async()=>{try{download(await player.checkpoint(),record.record_id+'-checkpoint.json');}catch(error){status(error.message);}});
$('export-record').addEventListener('click',()=>download(player.supervisor.executionRecord(),record.record_id+'-performed.json'));
document.addEventListener('visibilitychange',()=>{if(document.hidden){suspend();status('Paused while hidden. Press Play to resume.');}});
window.addEventListener('pagehide',suspend);
setInterval(()=>{if(!player)return;controls();const state=player.supervisor.snapshot();$('seek').value=state.frame;$('clock').textContent=`Frame ${state.frame} / ${player.supervisor.duration} | ${state.audio_voices} voices | ${state.visual_instances} expressive pictures`;if(state.status==='finished')status('Performance finished. Save its performed record and recovery checkpoint.');else if(state.degradation_reasons.length)status('Qualified fallback: '+state.degradation_reasons.join(', '));},500);
window.ampPerformance=Object.freeze({pause,get ready(){return !!player;},get player(){return player;}});
