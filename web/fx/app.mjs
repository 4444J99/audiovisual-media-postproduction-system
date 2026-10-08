import {CATALOG, CATALOG_BY_TYPE, PATCH_CATALOG, createModule, createPatch, createSingleModulePatch, validatePatch, evaluatedNode, buildSerialConnections, clonePatch} from './core.mjs';
import {VisualEngine, paintViewport, clamp} from './visual-engine.mjs';
import {GOD_HERE_OPTIONS,GOD_HERE_DEMO_MODULES} from './god-here.config.mjs';
import {amplitudeEnvelope} from './audio-engine.mjs';
import {normalizeWorkbenchPatch} from './workbench-state.mjs';
import {signalSignature} from './preview-key.mjs';

const $=id=>document.getElementById(id);
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const human=s=>String(s).replaceAll('-',' ');
const isFX=n=>!!CATALOG_BY_TYPE[n.type];
const timeLabel=t=>`${String(Math.floor(t/60)).padStart(2,'0')}:${(t%60).toFixed(2).padStart(5,'0')}`;
const fmt=n=>Number.isInteger(n)?String(n):Number(n).toFixed(Math.abs(n)<.1?3:2).replace(/0+$/,'').replace(/\.$/,'');
const state={patch:null,selected:null,position:0,playing:false,playPending:false,loop:true,bypass:false,monitor:'expressive',volume:.7,layout:'auto',recording:false,ready:false,revision:0,drawRevision:-1,drawFrame:-1,undo:[],saved:Object.create(null),audioRevision:-1,audioDesired:0,audioBusy:false,audioError:null,audioWaiters:[],worker:null,workerReady:false};
let media,assets,sourceBinding,engine,sourcePCM,referencePCM,ctx,gain,player,startedAt=0,expressivePCM,renderDebounce,toastTimer;
const previews=new Map();let previewRevision=-1,previewEntry=null,previewPath='',previewFailed=new Set(),previewSeek=-1;
let playRequest=0,workerWatchdog,previewPlayPromise=null;
let controlEnvelopes={},controlFps=12;
const status=text=>$('status').textContent=text;
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3300);}
function position(){return state.playing?clamp(state.position+(ctx.currentTime-startedAt),0,media.duration):state.position;}
function snapshot(){if(state.patch){state.undo.push(clonePatch(state.patch));if(state.undo.length>30)state.undo.shift();}}
function remember(){try{localStorage.setItem('god-here-fx-patch-v1',JSON.stringify(state.patch));}catch{/* A private browser can disable persistence; explicit export remains available. */}}
function invalidate(audio=true){state.revision++;remember();if(audio){state.audioDesired++;clearTimeout(renderDebounce);renderDebounce=setTimeout(pumpAudio,80);}}
function validate(patch){const result=validatePatch(patch,{source:sourceBinding,regions:assets.regions.items.map(r=>r.id)});if(!result.valid)throw Error(result.errors.slice(0,3).join(' · '));for(const n of patch.nodes){if(n.objectRect&&(!Array.isArray(n.objectRect)||n.objectRect.length!==4||n.objectRect.some(x=>!Number.isFinite(x)||x<0||x>1)))throw Error('Object rectangles require four normalized numbers.');}return result;}
function setPatch(patch,{stash=true,seek=true}={}){
  patch=normalizeWorkbenchPatch(patch,{source:sourceBinding,regions:assets.regions.items.map(r=>r.id),duration:media.duration});
  validate(patch);if(stash&&state.patch){snapshot();state.saved[state.patch.id]=clonePatch(state.patch);}
  const wasPlaying=state.playing||state.playPending;pause();state.patch=patch;state.selected=patch.nodes.find(isFX)?.id;state.recording=false;
  if(seek)state.position=0;state.bypass=false;$('bypass').classList.remove('on');$('bypass').setAttribute('aria-pressed','false');
  renderUI();invalidate();status(patch.metadata?.description||'Adjust a processor, or play its extreme demonstration.');
  if(wasPlaying)play();
}
function loadNamed(id){
  const options={...GOD_HERE_OPTIONS,source:sourceBinding};
  const patch=state.saved[id]?clonePatch(state.saved[id]):createPatch(id,options);
  patch.metadata.wordMode=patch.metadata.wordMode||(id==='correction-machine'?'authored':'cues');patch.metadata.words=patch.metadata.words||'HOW WHY WHAT';
  setPatch(patch);
}
function single(type,demonstration=false){
  const opts={...GOD_HERE_OPTIONS,source:sourceBinding,demonstration,module:GOD_HERE_DEMO_MODULES[type]||{}};
  const patch=createSingleModulePatch(type,opts);patch.name=CATALOG_BY_TYPE[type].name;
  setPatch(patch);if(demonstration){state.loop=false;updateTransport();play();enterFullscreen();}
}
function setTab(name){document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));document.querySelectorAll('.tab-panel').forEach(p=>p.hidden=p.id!==`tab-${name}`);}
function renderUI(){
  $('patch-title').textContent=state.patch.name;
  $('patch-select').innerHTML=PATCH_CATALOG.map(p=>`<option value="${p.id}">${p.letter} · ${escape(p.name)}</option>`).join('')+(!PATCH_CATALOG.some(p=>p.id===state.patch.id)?'<option value="current">Current rack</option>':'');
  $('patch-select').value=PATCH_CATALOG.some(p=>p.id===state.patch.id)?state.patch.id:'current';
  $('module-library').innerHTML=CATALOG.map(c=>`<button class="module-button ${state.patch.nodes.find(n=>n.id===state.selected)?.type===c.type?'selected':''}" data-module="${c.type}" style="--fx-color:${c.color}"><i></i><span>${c.code}</span>${escape(c.name)}</button>`).join('');
  $('add-module').innerHTML='<option value="">Add processor…</option>'+CATALOG.map(c=>`<option value="${c.type}">${c.code} ${escape(c.name)}</option>`).join('');
  $('rack-count').textContent=`${state.patch.nodes.filter(isFX).length} inserts · ${state.patch.nodes.filter(n=>n.type==='mix').length} buses`;
  $('seed').value=state.patch.seed;$('word-mode').value=state.patch.metadata.wordMode||'cues';$('authored-words').value=state.patch.metadata.words||'HOW WHY WHAT';
  renderRack();renderConnections();renderAutomation();updateTransport();
}
function regionOptions(value){return `<option value="all" ${value==='all'?'selected':''}>All addresses</option>`+assets.regions.items.map(r=>`<option value="${r.id}" ${r.id===value?'selected':''}>${escape(human(r.id))}${r.labelValue?'':' · rectangle'}</option>`).join('');}
function renderRack(){
  $('rack').innerHTML=state.patch.nodes.filter(isFX).map(n=>{
    const c=CATALOG_BY_TYPE[n.type],effective=evaluatedNode(n,position(),state.patch),custom=Object.hasOwn(state.patch.metadata.customModuleStates||{},n.id)?state.patch.metadata.customModuleStates[n.id]:null;
    return `<article class="module-card ${state.selected===n.id?'selected':''} ${n.bypass?'bypassed':''}" data-node="${escape(n.id)}" style="--fx-color:${c.color}">
      <div class="module-card-head" data-select="${escape(n.id)}"><span class="module-number">${c.code}</span><h3>${escape(c.name)}</h3><button data-action="up" aria-label="Move ${escape(c.name)} earlier">↑</button><button data-action="down" aria-label="Move ${escape(c.name)} later">↓</button><button data-action="remove" aria-label="Remove ${escape(c.name)}">×</button></div>
      <div class="module-card-body"><div class="module-controls-top"><select data-preset aria-label="${escape(c.name)} preset">${c.presets.map(p=>`<option value="${p.id}" ${n.presetId===p.id?'selected':''}>${escape(p.name)}</option>`).join('')}${custom?'<option value="saved-custom">Saved custom setting</option>':''}</select><button class="toggle ${n.bypass?'on':''}" data-action="bypass" aria-pressed="${n.bypass}">Bypass</button><button class="toggle ${n.solo?'on':''}" data-action="solo" aria-pressed="${n.solo}">Solo</button></div>
      <div class="slider-row intensity-row"><label>Intensity</label><input data-parameter="intensity" type="range" min="0" max="1" step=".01" value="${effective.intensity}" aria-label="${escape(c.name)} intensity"><output>${Math.round(effective.intensity*100)}%</output></div>
      <div class="slider-row"><label>Wet / dry</label><input data-parameter="wet" type="range" min="0" max="1" step=".01" value="${effective.wet}" aria-label="${escape(c.name)} wet mix"><output>${Math.round(effective.wet*100)}%</output></div>
      <div class="target-buttons">${['voice','picture','body','text','objects','room'].map(t=>`<button class="${n.targets.includes(t)?'on':''}" data-target="${t}" ${!c.targets.includes(t)?'disabled':''} aria-pressed="${n.targets.includes(t)}">${t}</button>`).join('')}</div>
      <div class="region-select"><label>Address</label><select data-region aria-label="${escape(c.name)} target address">${regionOptions(n.region)}</select></div>
      <div class="scope-control"><label>Insert<select data-scope><option value="track" ${n.scope.type==='track'?'selected':''}>Track</option><option value="clip" ${n.scope.type==='clip'?'selected':''}>Clip</option></select></label>${n.scope.type==='clip'?`<label>In<input data-scope-time="start" type="number" min="0" max="${media.duration}" step=".01" value="${n.scope.start}"></label><label>Out<input data-scope-time="end" type="number" min="0" max="${media.duration}" step=".01" value="${n.scope.end}"></label>`:''}</div>
      <details><summary>Processor controls</summary>${c.params.map(p=>`<div class="param-row"><label>${escape(p.label)}<output>${p.options?escape(p.options[Math.round(effective.params[p.key])]):fmt(effective.params[p.key])+' '+escape(p.unit||'')}</output></label><input data-parameter="params.${p.key}" type="range" min="${p.min}" max="${p.sourceTime||p.outputTime?Math.min(p.max,media.duration):p.max}" step="${p.step}" value="${effective.params[p.key]}" aria-label="${escape(c.name+' '+p.label)}"></div>`).join('')}</details>
      <details><summary>Edit Intensity macro</summary><p class="small-copy">The left endpoint is Intensity 0; the right endpoint is Intensity 1. Directly editing a processor control removes that parameter from this macro.</p>${n.macro.map((m,i)=>`<div class="macro-row"><span>${escape(m.parameter)}</span><input data-macro="${i}:min" type="number" step="any" value="${m.min}" aria-label="${escape(m.parameter)} macro minimum"><input data-macro="${i}:max" type="number" step="any" value="${m.max}" aria-label="${escape(m.parameter)} macro maximum"></div>`).join('')}<button data-action="reset-macro">Restore preset macro</button></details>
      <details><summary>Sidechain & object selection</summary><label class="small-copy"><input data-sidechain type="checkbox" ${n.modulation?'checked':''}> Drive Intensity from source amplitude</label>${n.modulation?`<div class="param-row"><label>Envelope amount</label><input data-mod-amount type="range" min="0" max="1" step=".01" value="${n.modulation.amount}" aria-label="Sidechain amount"></div>`:''}${n.targets.includes('objects')?`<p class="small-copy">Rectangle coordinates, relative to the whole picture.</p>${['x','y','width','height'].map((k,i)=>`<div class="slider-row"><label>${k}</label><input data-object="${i}" type="range" min="0" max="1" step=".01" value="${(n.objectRect||[.6,.62,.1,.18])[i]}" aria-label="Object ${k}"><output>${fmt((n.objectRect||[.6,.62,.1,.18])[i])}</output></div>`).join('')}`:'<p class="small-copy">Select objects to adjust an authored rectangle.</p>'}</details>
      </div></article>`;
  }).join('');
}
function labelNode(id){const n=state.patch.nodes.find(n=>n.id===id);return n?.name||human(id);}
function renderConnections(){
  const portColors={audio:'#dbfb65',picture:'#78c7ff',text:'#ff95b7',matte:'#c6a5ff',control:'#ffc062'};
  $('graph-map').innerHTML=state.patch.nodes.map(n=>`<span class="graph-node" style="--fx-color:${CATALOG_BY_TYPE[n.type]?.color||'#64716a'}">${escape(labelNode(n.id))}</span>`).join('');
  $('connections').innerHTML=state.patch.connections.map((e,i)=>`<div class="connection"><strong>${escape(labelNode(e.from))} → ${escape(labelNode(e.to))}<br><small>${escape(e.role)}</small></strong><span class="port" style="--port-color:${portColors[e.port]}">${e.port}</span><input type="number" min="0" max="4" step=".05" value="${e.gain}" data-edge-gain="${i}" aria-label="Connection ${i+1} gain"><button data-remove-edge="${i}" aria-label="Remove connection ${i+1}">×</button></div>`).join('');
  $('connect-from').innerHTML=state.patch.nodes.filter(n=>n.type!=='output').map(n=>`<option value="${escape(n.id)}">${escape(labelNode(n.id))}</option>`).join('');
  $('connect-to').innerHTML=state.patch.nodes.filter(n=>n.type!=='source').map(n=>`<option value="${escape(n.id)}">${escape(labelNode(n.id))}</option>`).join('');
  $('connect-to').value=state.selected||'output';
}
function renderAutomation(){
  const prev=$('auto-node').value;
  $('auto-node').innerHTML=state.patch.nodes.filter(isFX).map(n=>`<option value="${escape(n.id)}">${escape(labelNode(n.id))}</option>`).join('');
  $('auto-node').value=state.patch.nodes.some(n=>n.id===prev)?prev:state.selected;renderAutoParameters();
  $('automation-list').innerHTML=state.patch.nodes.filter(isFX).flatMap(n=>n.automation.map((a,i)=>`<div class="automation-entry"><strong>${escape(labelNode(n.id))} / ${escape(a.parameter)}</strong><pre>${a.keyframes.map(k=>`${fmt(k.time)}s : ${fmt(k.value)}`).join('   ')}</pre><button data-remove-lane="${i}" data-lane-node="${escape(n.id)}">Remove curve</button></div>`)).join('');
  $('event-count').textContent=`${state.patch.events.length} recorded changes`;
  $('events-list').innerHTML=state.patch.events.slice(-35).map(e=>`<div class="event-row">${fmt(e.time)}s · ${escape(labelNode(e.nodeId))}<br>${escape(e.parameter)} = ${escape(e.value)}</div>`).join('');
  $('record').classList.toggle('recording',state.recording);$('record').textContent=state.recording?'Recording controls':'Record controls';$('record').setAttribute('aria-pressed',String(state.recording));
}
function renderAutoParameters(){const n=state.patch.nodes.find(n=>n.id===$('auto-node').value),c=CATALOG_BY_TYPE[n?.type];const prev=$('auto-param').value;$('auto-param').innerHTML='<option value="intensity">Intensity</option><option value="wet">Wet / dry</option>'+(c?.params||[]).map(p=>`<option value="params.${p.key}">${escape(p.label)}</option>`).join('');if([...$('auto-param').options].some(o=>o.value===prev))$('auto-param').value=prev;}
function rememberCustom(node){
  state.patch.metadata.customModuleStates=Object.assign(Object.create(null),state.patch.metadata.customModuleStates||{});
  state.patch.metadata.customModuleStates[node.id]={node:clonePatch(node),events:clonePatch(state.patch.events.filter(e=>e.nodeId===node.id))};
}
function setParameter(node,path,value){
  if(state.recording){
    const t=position(),last=state.patch.events.at(-1);
    if(last&&last.nodeId===node.id&&last.parameter===path&&Math.abs(last.time-t)<.05)last.value=value;
    else state.patch.events.push({time:t,nodeId:node.id,parameter:path,value});
    state.patch.events.sort((a,b)=>a.time-b.time);
  }else{
    state.patch.events=state.patch.events.filter(e=>!(e.nodeId===node.id&&e.parameter===path));
    node.automation=node.automation.filter(a=>a.parameter!==path);
    if(path.startsWith('params.')) {node.params[path.slice(7)]=value;node.macro=node.macro.filter(m=>m.parameter!==path.slice(7));}
    else node[path]=value;
  }
  rememberCustom(node);
  invalidate();$('event-count').textContent=`${state.patch.events.length} recorded changes`;
}
function serial(){const effects=state.patch.nodes.filter(isFX);state.patch.nodes=[{id:'source',type:'source'},...effects,{id:'output',type:'output',gain:1}];state.patch.connections=buildSerialConnections(state.patch.nodes.map(n=>n.id));}
function changeGraph(mutator){const prior=clonePatch(state.patch);try{snapshot();mutator();validate(state.patch);$('route-error').textContent='';renderUI();invalidate();}catch(error){state.patch=prior;state.undo.pop();$('route-error').textContent=error.message;toast(error.message);}}

function decodeWav(buffer){
  const view=new DataView(buffer);let pos=12,format=1,channels=2,sr=24000,bits=16,start=0,length=0;
  while(pos+8<=buffer.byteLength){const id=String.fromCharCode(...new Uint8Array(buffer,pos,4)),n=view.getUint32(pos+4,true);if(id==='fmt '){format=view.getUint16(pos+8,true);channels=view.getUint16(pos+10,true);sr=view.getUint32(pos+12,true);bits=view.getUint16(pos+22,true);}if(id==='data'){start=pos+8;length=n;break;}pos+=8+n+(n%2);}
  if(!start||![16,32].includes(bits))throw Error('Unsupported reference audio encoding.');
  const count=Math.floor(length/(bits/8)/channels),out=[new Float32Array(count),new Float32Array(count)];
  for(let i=0;i<count;i++)for(let ch=0;ch<2;ch++){const at=start+(i*channels+Math.min(ch,channels-1))*(bits/8);out[ch][i]=format===3?view.getFloat32(at,true):bits===16?view.getInt16(at,true)/32768:view.getInt32(at,true)/2147483648;}
  return {channels:out,sampleRate:sr};
}
function ensureContext(){if(!ctx){ctx=new (window.AudioContext||window.webkitAudioContext)();gain=ctx.createGain();gain.gain.value=state.volume;gain.connect(ctx.destination);}return ctx.resume();}
function activePCM(){return state.monitor==='source'?sourcePCM:state.monitor==='reference'||state.bypass?referencePCM:expressivePCM;}
function startBuffer(offset){
  const pcm=activePCM();if(!pcm)return;
  if(player){player.onended=null;try{player.stop();}catch{}player.disconnect();}
  const buffer=ctx.createBuffer(2,pcm[0].length,media.audio.sampleRate);buffer.copyToChannel(pcm[0],0);buffer.copyToChannel(pcm[1],1);
  player=ctx.createBufferSource();player.buffer=buffer;player.connect(gain);startedAt=ctx.currentTime;state.position=clamp(offset,0,media.duration-.001);state.playing=true;player.start(0,state.position);
  player.onended=()=>{if(!state.playing)return;state.playing=false;state.position=0;if(state.loop)play();else{state.position=media.duration-.001;updateTransport();}};
  updateTransport();
}
async function play(){
  if(!state.ready)return;
  const request=++playRequest;state.playPending=true;updateTransport();
  if(state.position>=media.duration-.01)state.position=0;
  // Start media loading during the tap, including on metadata-only phone players.
  if(previewPath)previewFailed.delete(previewPath);syncPreview(state.position);
  try{await ensureContext();if(request!==playRequest)return;
    if(state.monitor==='expressive'&&!state.bypass&&(!expressivePCM||state.audioRevision<state.audioDesired)){status('Preparing this patch’s sound…');await waitForAudio();}
    if(request!==playRequest)return;
    state.playPending=false;startBuffer(state.position);status(state.recording?'Recording parameter changes.':'Playing the current patch.');
  }catch(error){if(request!==playRequest)return;state.playPending=false;$('rendered-picture').pause();updateTransport();status(state.audioError?'Sound needs to reconnect. Tap Retry sound, or open Play demonstrations.':error.message);toast(state.audioError?'Retry sound is available below the player.':'Playback could not start. Tap Play to try again.');}
}
function pause(){++playRequest;state.playPending=false;if(state.playing){state.position=position();state.playing=false;}if(player){player.onended=null;try{player.stop();}catch{}player.disconnect();player=null;}$('rendered-picture').pause();updateTransport();}
function refreshPlaying(){if(state.playing)startBuffer(position());}
function requestAudio(){state.audioDesired++;pumpAudio();}
function failAudio(message){
  clearTimeout(workerWatchdog);state.audioBusy=false;state.workerReady=false;state.audioError=String(message||'Sound loading stopped.');
  if(state.worker){state.worker.terminate();state.worker=null;}
  state.audioWaiters.splice(0).forEach(w=>w.reject(Error(state.audioError)));
  pause();$('audio-retry').hidden=false;status('Sound needs to reconnect. Tap Retry sound, or open Play demonstrations.');
}
function startAudioWorker(){
  clearTimeout(workerWatchdog);if(state.worker)state.worker.terminate();
  state.worker=null;state.workerReady=false;state.audioBusy=false;state.audioError=null;state.audioRevision=-1;
  $('audio-retry').hidden=true;
  try{
    const worker=new Worker(new URL('./audio-worker.mjs',import.meta.url),{type:'module'});state.worker=worker;
    workerWatchdog=setTimeout(()=>failAudio('Sound loading timed out.'),20000);
    worker.onmessage=({data})=>{
      if(state.worker!==worker)return;
      if(data.type==='ready'){clearTimeout(workerWatchdog);state.workerReady=true;pumpAudio();return;}
      clearTimeout(workerWatchdog);state.audioBusy=false;
      if(data.type==='error'){failAudio(data.message);return;}
      if(data.type!=='rendered'){failAudio('The sound response could not be read.');return;}
      if(data.id===state.audioDesired){expressivePCM=data.channels;controlEnvelopes=data.controlEnvelopes||{};controlFps=data.controlFps||12;engine.cacheSignature=null;state.revision++;state.audioRevision=data.id;state.audioReport=data.report;if(state.playing&&state.monitor==='expressive'&&!state.bypass)refreshPlaying();state.audioWaiters.splice(0).forEach(w=>w.resolve());}
      else pumpAudio();
    };
    worker.onerror=e=>{if(state.worker===worker)failAudio(e.message||'Sound loading stopped.');};
    worker.onmessageerror=()=>{if(state.worker===worker)failAudio('The sound response could not be read.');};
    worker.postMessage({type:'init',source:sourcePCM,reference:referencePCM,sampleRate:media.audio.sampleRate});
  }catch(error){failAudio(error.message);}
}
function pumpAudio(){
  if(!state.worker||!state.workerReady||state.audioBusy||state.audioError||!state.patch)return;
  if(state.audioRevision>=state.audioDesired)return;
  state.audioBusy=true;clearTimeout(workerWatchdog);workerWatchdog=setTimeout(()=>failAudio('This sound render took too long. Retry sound or choose a simpler patch.'),45000);
  try{state.worker.postMessage({type:'render',id:state.audioDesired,patch:state.patch,input:'reference'});}catch(error){failAudio(error.message);}
}
function waitForAudio(){if(state.audioError)return Promise.reject(Error(state.audioError));if(state.audioRevision>=state.audioDesired&&expressivePCM)return Promise.resolve();return new Promise((resolve,reject)=>{state.audioWaiters.push({resolve,reject});pumpAudio();});}
function updateTransport(){
  $('play').textContent=state.playing?'Pause':state.playPending?'Cancel':'Play';$('stage-play').hidden=state.playing||state.playPending||!state.ready;$('loop').classList.toggle('on',state.loop);$('loop').setAttribute('aria-pressed',String(state.loop));
  $('record').setAttribute('aria-pressed',String(state.recording));
}
function renderTimeline(t){
  const canvas=$('timeline'),ctx=canvas.getContext('2d'),W=canvas.width,H=canvas.height;
  ctx.clearRect(0,0,W,H);const values=assets.waveforms['dialogue-candidate']||assets.waveforms.reference||assets.waveforms.source;
  ctx.strokeStyle='#92a84c';ctx.lineWidth=1;
  for(let x=0;x<W;x+=3){const v=values[Math.min(values.length-1,Math.floor(x/W*values.length))]||0;ctx.beginPath();ctx.moveTo(x,H/2-v*H*.43);ctx.lineTo(x,H/2+v*H*.43);ctx.stroke();}
  ctx.strokeStyle='#ff8179';for(const e of state.patch.events){ctx.beginPath();ctx.moveTo(e.time/media.duration*W,0);ctx.lineTo(e.time/media.duration*W,H);ctx.stroke();}
  ctx.fillStyle='#ecffb6';ctx.fillRect(t/media.duration*W,0,2,H);
}
function refreshCanvasSize(){const c=$('picture'),rect=$('stage').getBoundingClientRect();const scale=Math.min(window.devicePixelRatio||1,1.5);const w=Math.round(rect.width*scale),h=Math.round(rect.height*scale);if(c.width!==w||c.height!==h){c.width=w;c.height=h;state.drawFrame=-1;$('reel').href=`assets/renders/god-here-13-processors-${innerHeight>innerWidth?'portrait':'landscape'}.mp4`;}}
function syncPreview(t){
  if(previewRevision!==state.revision){previewEntry=previews.get(signalSignature(state.patch))||null;previewRevision=state.revision;}
  const video=$('rendered-picture'),c=$('picture');
  const portrait=state.layout==='stack'||state.layout==='auto'&&c.width/c.height<.9;
  const path=!state.bypass&&state.monitor==='expressive'&&previewEntry?(portrait?previewEntry.portrait:previewEntry.video):null;
  if(!path||previewFailed.has(path)){video.hidden=true;video.pause();c.hidden=false;$('render-mode').textContent='Editable rack';return false;}
  if(previewPath!==path){previewPath=path;previewSeek=-1;video.src=`assets/renders/${path}`;video.load();}
  // A metadata preload need not decode a frame until play is requested.
  if((state.playing||state.playPending)&&video.paused&&!previewPlayPromise){
    const requestedPath=path;
    const pending=video.play();previewPlayPromise=pending;
    pending.catch(error=>{if(previewPath===requestedPath&&(state.playing||state.playPending)&&error.name!=='AbortError'){previewFailed.add(requestedPath);state.revision++;}}).finally(()=>{if(previewPlayPromise===pending)previewPlayPromise=null;});
  }
  if(video.readyState<2){video.hidden=true;c.hidden=false;return false;}
  if(!video.seeking&&(Math.abs(video.currentTime-t)>.14||!state.playing&&Math.abs(video.currentTime-t)>.018)&&previewSeek!==t){video.currentTime=t;previewSeek=t;}
  if(!state.playing&&!state.playPending&&!video.paused)video.pause();
  video.hidden=false;c.hidden=true;$('render-mode').textContent='Rendered preset';return true;
}
$('rendered-picture').onerror=()=>{if(previewPath)previewFailed.add(previewPath);state.revision++;};
function animate(){
  if(state.ready){
    const t=position(),frame=Math.floor(t*media.fps);refreshCanvasSize();
    const rendered=syncPreview(t);
    if(frame!==state.drawFrame||state.revision!==state.drawRevision){
      try{
        const isReference=state.bypass||state.monitor!=='expressive';
        if(!rendered){const layers=engine.renderLayers(state.patch,t,{bypass:isReference});paintViewport($('picture'),layers,state.layout);}
        state.drawFrame=frame;state.drawRevision=state.revision;renderTimeline(t);
      }catch(error){status(`Picture processing stopped: ${error.message}`);pause();}
    }
    $('seek').value=t;$('clock').textContent=timeLabel(t);
    const phases=state.patch.metadata.demoPhases;const phase=phases?.find(p=>t>=p.start&&t<p.end);$('demo-stages').hidden=!phases;
    $('phase').textContent=state.bypass?'RACK BYPASS':state.monitor!=='expressive'?'REFERENCE':phase?phase.name.toUpperCase():state.playing?'LIVE PATCH':'READY';
    $('phase').classList.toggle('live',!state.bypass&&state.monitor==='expressive'&&phase?.name!=='bypass');
    $('signal-label').textContent=state.monitor==='source'?'ORIGINAL RECORDING':state.monitor==='reference'?'DIALOGUE CANDIDATE':'EXPRESSIVE OUT';
    if(phases){const i=phases.indexOf(phase);document.querySelectorAll('#demo-stages span').forEach((s,k)=>s.classList.toggle('active',k===i));}
  }
  requestAnimationFrame(animate);
}
async function enterFullscreen(){
  const stage=$('stage');stage.classList.add('expanded');document.body.classList.add('stage-open');$('exit-full').hidden=false;state.drawFrame=-1;
  try{if(stage.requestFullscreen&&!document.fullscreenElement)await stage.requestFullscreen();}catch{/* Fixed-position full canvas is the supported phone fallback. */}
}
async function leaveFullscreen(){if(document.fullscreenElement)try{await document.exitFullscreen();}catch{}$('stage').classList.remove('expanded');document.body.classList.remove('stage-open');$('exit-full').hidden=true;state.drawFrame=-1;}

$('play').onclick=()=>state.playing||state.playPending?pause():play();$('stage-play').onclick=play;
$('audio-retry').onclick=()=>{pause();startAudioWorker();status('Reconnecting sound…');};
$('load-retry').onclick=()=>location.reload();
$('restart').onclick=()=>{const resume=state.playing;pause();state.position=0;state.revision++;if(resume)play();};
$('seek').oninput=()=>{const resume=state.playing;pause();state.position=Number($('seek').value);state.revision++;if(resume)play();};
$('loop').onclick=()=>{state.loop=!state.loop;updateTransport();};
$('volume').oninput=()=>{state.volume=Number($('volume').value);if(gain)gain.gain.setTargetAtTime(state.volume,ctx.currentTime,.015);};
$('monitor').onchange=()=>{state.monitor=$('monitor').value;invalidate(false);refreshPlaying();};
$('bypass').onclick=()=>{state.bypass=!state.bypass;$('bypass').classList.toggle('on',state.bypass);$('bypass').setAttribute('aria-pressed',String(state.bypass));invalidate(false);refreshPlaying();};
$('layout').onchange=()=>{state.layout=$('layout').value;state.revision++;};
$('fullscreen').onclick=enterFullscreen;$('exit-full').onclick=leaveFullscreen;
document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement&&$('stage').classList.contains('expanded'))leaveFullscreen();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')leaveFullscreen();if(e.code==='Space'&&!['INPUT','TEXTAREA','SELECT','BUTTON'].includes(e.target.tagName)){e.preventDefault();state.playing||state.playPending?pause():play();}});
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>setTab(b.dataset.tab));
$('source-details').onclick=()=>{setTab('source');$('tab-source').scrollIntoView({behavior:'smooth',block:'nearest'});};
$('patch-select').onchange=()=>{if($('patch-select').value!=='current')loadNamed($('patch-select').value);};
$('module-library').onclick=e=>{const b=e.target.closest('[data-module]');if(b)single(b.dataset.module);};
$('add-module').onchange=()=>{const type=$('add-module').value;if(!type)return;changeGraph(()=>{const id=`${type}-${Date.now().toString(36)}`;const node=createModule(type,{id});state.patch.nodes.splice(-1,0,node);for(const edge of state.patch.connections)if(edge.to==='output')edge.to=id;state.patch.connections.push(...buildSerialConnections([id,'output']));state.selected=id;});};
$('rack').addEventListener('pointerdown',e=>{if(e.target.matches('input[type=range]'))snapshot();});
$('rack').addEventListener('input',e=>{
  const card=e.target.closest('[data-node]');if(!card)return;const n=state.patch.nodes.find(n=>n.id===card.dataset.node);const d=e.target.dataset;
  if(d.parameter){const value=Number(e.target.value);setParameter(n,d.parameter,value);const row=e.target.closest('.slider-row,.param-row');const out=row?.querySelector('output');if(out)out.textContent=d.parameter.startsWith('params.')?fmt(value):`${Math.round(value*100)}%`;}
  else if(d.object){n.objectRect||=[.6,.62,.1,.18];n.objectRect[Number(d.object)]=Number(e.target.value);rememberCustom(n);invalidate(false);}
  else if('modAmount' in d){n.modulation.amount=Number(e.target.value);rememberCustom(n);invalidate();}
});
$('rack').addEventListener('change',e=>{
  const card=e.target.closest('[data-node]');if(!card)return;const n=state.patch.nodes.find(n=>n.id===card.dataset.node);const d=e.target.dataset;
  if('preset' in d){changeGraph(()=>{const saved=Object.hasOwn(state.patch.metadata.customModuleStates||{},n.id)?state.patch.metadata.customModuleStates[n.id]:null;if(e.target.value==='saved-custom'&&saved){const restored=clonePatch(saved.node||saved);Object.assign(n,{...restored,id:n.id,type:n.type});state.patch.events=state.patch.events.filter(ev=>ev.nodeId!==n.id).concat(clonePatch(saved.events||[])).sort((a,b)=>a.time-b.time);}else{state.patch.metadata.customModuleStates=Object.assign(Object.create(null),state.patch.metadata.customModuleStates||{});state.patch.metadata.customModuleStates[n.id]||={node:clonePatch(n),events:clonePatch(state.patch.events.filter(ev=>ev.nodeId===n.id))};const fresh=createModule(n.type,{presetId:e.target.value,id:n.id});Object.assign(n,{presetId:fresh.presetId,params:fresh.params,macro:fresh.macro,intensity:1,wet:1,automation:[]});state.patch.events=state.patch.events.filter(ev=>ev.nodeId!==n.id);}});}
  else if('region' in d){snapshot();n.region=e.target.value;rememberCustom(n);renderUI();invalidate();}
  else if('scope' in d){snapshot();n.scope=e.target.value==='track'?{type:'track'}:{type:'clip',start:2,end:Math.min(10,media.duration)};rememberCustom(n);renderUI();invalidate();}
  else if('scopeTime' in d){changeGraph(()=>{n.scope[d.scopeTime]=Number(e.target.value);rememberCustom(n);});}
  else if('macro' in d){const [i,key]=d.macro.split(':');const before=n.macro[i][key];n.macro[i][key]=Number(e.target.value);const result=validatePatch(state.patch);if(!result.valid){n.macro[i][key]=before;toast(result.errors[0]);}rememberCustom(n);renderUI();invalidate();}
  else if('sidechain' in d){changeGraph(()=>{state.patch.connections=state.patch.connections.filter(c=>!(c.to===n.id&&c.port==='control'));if(e.target.checked){n.modulation={parameter:'intensity',amount:.6,mode:'add'};state.patch.connections.push({from:'source',to:n.id,port:'control',gain:1,role:'sidechain'});}else delete n.modulation;rememberCustom(n);});}
});
$('rack').onclick=e=>{
  const card=e.target.closest('[data-node]');if(!card)return;const n=state.patch.nodes.find(n=>n.id===card.dataset.node);const action=e.target.closest('[data-action]')?.dataset.action;
  const target=e.target.closest('[data-target]')?.dataset.target;
  if(target){changeGraph(()=>{const next=n.targets.includes(target)?n.targets.filter(t=>t!==target):[...n.targets,target];if(!next.length)throw Error('Keep at least one target selected.');n.targets=next;rememberCustom(n);});return;}
  if(!action){if(e.target.closest('[data-select]')){state.selected=n.id;renderUI();}return;}
  if(action==='bypass'||action==='solo'){snapshot();setParameter(n,action,!evaluatedNode(n,position(),state.patch)[action]);renderUI();}
  else if(action==='up'||action==='down'){changeGraph(()=>{const effects=state.patch.nodes.filter(isFX);const i=effects.indexOf(n),j=i+(action==='up'?-1:1);if(j<0||j>=effects.length)return;const other=effects[j],a=state.patch.nodes.indexOf(n),b=state.patch.nodes.indexOf(other);[state.patch.nodes[a],state.patch.nodes[b]]=[state.patch.nodes[b],state.patch.nodes[a]];const swap=id=>id===n.id?other.id:id===other.id?n.id:id;state.patch.connections=state.patch.connections.map(edge=>edge.port==='control'?edge:{...edge,from:swap(edge.from),to:swap(edge.to)});});status('Processor positions exchanged. Buses and parallel branches are retained.');}
  else if(action==='remove')changeGraph(()=>{const incoming=state.patch.connections.filter(e=>e.to===n.id),outgoing=state.patch.connections.filter(e=>e.from===n.id);state.patch.connections=state.patch.connections.filter(e=>e.from!==n.id&&e.to!==n.id);for(const a of incoming)for(const b of outgoing)if(a.port===b.port&&a.port!=='control')state.patch.connections.push({from:a.from,to:b.to,port:a.port,gain:a.gain*b.gain,role:b.role});state.patch.nodes=state.patch.nodes.filter(x=>x.id!==n.id);state.patch.events=state.patch.events.filter(e=>e.nodeId!==n.id);if(state.patch.metadata.customModuleStates)delete state.patch.metadata.customModuleStates[n.id];state.selected=state.patch.nodes.find(isFX)?.id;});
  else if(action==='reset-macro'){snapshot();n.macro=clonePatch(CATALOG_BY_TYPE[n.type].presets.find(p=>p.id===n.presetId)?.macro||CATALOG_BY_TYPE[n.type].macro);rememberCustom(n);renderUI();invalidate();}
};
$('connections').onclick=e=>{const b=e.target.closest('[data-remove-edge]');if(b)changeGraph(()=>state.patch.connections.splice(Number(b.dataset.removeEdge),1));};
$('connections').onchange=e=>{if('edgeGain' in e.target.dataset)changeGraph(()=>state.patch.connections[Number(e.target.dataset.edgeGain)].gain=Number(e.target.value));};
$('connection-form').onsubmit=e=>{e.preventDefault();changeGraph(()=>state.patch.connections.push({from:$('connect-from').value,to:$('connect-to').value,port:$('connect-port').value,role:$('connect-role').value,gain:Number($('connect-gain').value)}));};
$('add-mix').onclick=()=>changeGraph(()=>state.patch.nodes.splice(-1,0,{id:`mix-${Date.now().toString(36)}`,type:'mix',gain:1}));
$('serial').onclick=()=>changeGraph(serial);
$('auto-node').onchange=renderAutoParameters;
$('automation-form').onsubmit=e=>{e.preventDefault();changeGraph(()=>{const n=state.patch.nodes.find(n=>n.id===$('auto-node').value);const parameter=$('auto-param').value;const keyframes=$('auto-points').value.split(',').map(pair=>{const [time,value]=pair.trim().split(':').map(Number);return {time:Math.min(media.duration,time),value};}).sort((a,b)=>a.time-b.time);n.automation=n.automation.filter(a=>a.parameter!==parameter);n.automation.push({parameter,interpolation:$('auto-curve').value,keyframes});state.patch.events=state.patch.events.filter(ev=>!(ev.nodeId===n.id&&ev.parameter===parameter));rememberCustom(n);});};
$('automation-list').onclick=e=>{const b=e.target.closest('[data-remove-lane]');if(b)changeGraph(()=>{const n=state.patch.nodes.find(n=>n.id===b.dataset.laneNode);n.automation.splice(Number(b.dataset.removeLane),1);rememberCustom(n);});};
$('record').onclick=()=>{state.recording=!state.recording;renderAutomation();status(state.recording?'Intensity, wet/dry, processor parameters, bypass and solo changes will be recorded at the current output time.':'Control recording stopped. Export the patch to keep this performance.');};
$('replay').onclick=()=>{state.recording=false;pause();state.position=0;renderAutomation();play();};
$('clear-events').onclick=()=>{snapshot();state.patch.events=[];delete state.patch.metadata.demoPhases;renderUI();invalidate();};
$('seed').onchange=()=>changeGraph(()=>state.patch.seed=Number($('seed').value));
$('word-mode').onchange=()=>{state.patch.metadata.wordMode=$('word-mode').value;invalidate(false);};
$('authored-words').oninput=()=>{state.patch.metadata.words=$('authored-words').value;invalidate(false);};
$('demo').onclick=()=>{const n=state.patch.nodes.find(n=>n.id===state.selected)||state.patch.nodes.find(isFX);if(n)single(n.type,true);};
$('demo-patch').onclick=()=>{
  snapshot();const patch=clonePatch(state.patch);const end=patch.duration;
  patch.metadata.demoPhases=[{name:'bypass',start:0,end:2},{name:'extreme',start:2,end:6},{name:'parameter sweep',start:6,end:10},{name:'bypass',start:10,end}];
  patch.events=[];for(const n of patch.nodes.filter(isFX)){n.solo=false;n.automation=n.automation.filter(a=>!['intensity','wet'].includes(a.parameter));n.automation.push({parameter:'intensity',interpolation:'linear',keyframes:[{time:0,value:1},{time:6,value:1},{time:8,value:.12},{time:10,value:1}]});}
  setPatch(patch,{stash:false});state.loop=false;updateTransport();play();enterFullscreen();
};
$('undo').onclick=()=>{const previous=state.undo.pop();if(previous){const stack=state.undo;setPatch(previous,{stash:false,seek:false});state.undo=stack;toast('Previous rack restored.');}};
$('save').onclick=()=>{const blob=new Blob([JSON.stringify(state.patch,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`god-here-${state.patch.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);toast('Patch exported with routing, source identity, seed and automation.');};
$('import').onchange=async()=>{const file=$('import').files[0];if(!file)return;try{if(file.size>2e6)throw Error('Patch file exceeds 2 MB.');const patch=JSON.parse(await file.text());setPatch(patch);toast('Patch loaded.');}catch(error){toast(`Import rejected: ${error.message}`);}finally{$('import').value='';}};

async function initialize(){
  try{
    const get=async path=>{const response=await fetch(`assets/${path}`);if(!response.ok)throw Error(`Missing media asset: ${path}`);return response.json();};
    media=await get('manifest.json');const [cues,regions,waveforms,provenance]=await Promise.all([get(media.cues),get(media.regions),get(media.waveforms),get(media.provenance)]);
    sourceBinding={id:'god-here-second-draft',sha256:provenance.source.sha256,offset:media.sourceIn,duration:media.duration};
    let loaded=0;const total=media.picture.pages.length+media.matte.pages.length+1;
    const loadImage=path=>new Promise((resolve,reject)=>{const image=new Image();const timer=setTimeout(()=>reject(Error('Picture loading timed out. Retry loading or play the demonstrations.')),25000);image.onload=()=>{clearTimeout(timer);$('loading-text').textContent=`Preparing picture layers… ${++loaded}/${total}`;resolve(image);};image.onerror=()=>{clearTimeout(timer);reject(Error(`Could not load ${path}`));};image.src=`assets/${path}`;});
    const picture=await Promise.all(media.picture.pages.map(loadImage));const matte=await Promise.all(media.matte.pages.map(loadImage));const room=await loadImage(media.room.hybrid);
    assets={picture,matte,room,cues,regions,waveforms};
    const audioResponses=await Promise.all([media.audio.source,media.audio.reference].map(async path=>{const r=await fetch(`assets/${path}`);if(!r.ok)throw Error(`Could not load sound: ${path}`);return r.arrayBuffer();}));
    sourcePCM=decodeWav(audioResponses[0]).channels;referencePCM=decodeWav(audioResponses[1]).channels;
    const envelope=amplitudeEnvelope(referencePCM,media.audio.sampleRate);
    const lane=(id,t)=>{const values=controlEnvelopes[id];return values?values[Math.min(values.length-1,Math.max(0,Math.floor(t*controlFps)))]:null;};
    engine=new VisualEngine(media,assets,{width:384,height:216,cacheFrames:matchMedia('(pointer: coarse)').matches?96:192,control:t=>envelope[Math.min(envelope.length-1,Math.max(0,Math.floor(t*media.audio.sampleRate)))],controlLane:lane});
    try{const response=await fetch('assets/renders/render-manifest.json');if(response.ok){const manifest=await response.json();for(const entry of manifest.entries||[])if(typeof entry.signalSignature==='string')previews.set(entry.signalSignature,entry);}}catch{/* An editable checkout can run without optional rendered previews. */}
    startAudioWorker();
    state.ready=true;$('loading').hidden=true;$('play').disabled=false;$('seek').max=media.duration;
    let saved;try{saved=JSON.parse(localStorage.getItem('god-here-fx-patch-v1'));if(saved)saved=normalizeWorkbenchPatch(saved,{source:sourceBinding,regions:assets.regions.items.map(r=>r.id),duration:media.duration});}catch{saved=null;}
    const query=new URLSearchParams(location.search),demo=query.get('demo'),named=query.get('patch');
    if(demo&&Object.hasOwn(CATALOG_BY_TYPE,demo)){const patch=createSingleModulePatch(demo,{...GOD_HERE_OPTIONS,source:sourceBinding,demonstration:true,module:GOD_HERE_DEMO_MODULES[demo]||{}});setPatch(patch,{stash:false});}
    else if(named&&PATCH_CATALOG.some(p=>p.id===named))loadNamed(named);
    else if(saved)setPatch(saved,{stash:false});else loadNamed('message-impact');
    state.position=0;state.revision++;status(state.audioError?'Sound needs to reconnect. Tap Retry sound, or open Play demonstrations.':'Ready. Choose a processor or play the patch.');
    // An inspectable read-only snapshot supports reproducible acceptance checks.
    window.fxWorkbench={getPatch:()=>clonePatch(state.patch),getStatus:()=>({ready:state.ready,playing:state.playing,playPending:state.playPending,time:position(),audioBusy:state.audioBusy,audioError:state.audioError,workerReady:state.workerReady,audioRevision:state.audioRevision,audioDesired:state.audioDesired,preview:!$('rendered-picture').hidden?'rendered':'editable',report:state.audioReport}),renderAt:t=>{pause();state.position=clamp(t,0,media.duration);state.revision++;},selectModule:type=>single(type),selectPatch:id=>loadNamed(id)};
  }catch(error){$('loading-text').textContent=error.message;$('load-retry').hidden=false;status('The media pack could not be prepared. Retry loading, or open Play demonstrations.');}
}
requestAnimationFrame(animate);initialize();
