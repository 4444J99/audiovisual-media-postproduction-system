/** Bounded playback of a complete decision record through the retained FX engine.
 * No source extraction, model calls, remote locators or paid inference.
 */
import {VisualEngine} from '../fx/visual-engine.mjs';
import {createSingleModulePatch, CATALOG_BY_TYPE} from '../fx/core.mjs';
import {renderAudio} from '../fx/audio-engine.mjs';

const clone = value => structuredClone(value);
const BYTES = ['decoded_audio_bytes','texture_bytes','event_history_bytes'];
const terminal = status => ['cancelled','finished'].includes(status);
const clamp = value => Math.max(0,Math.min(1,value));
const integer = (value,min=0) => {if(!Number.isSafeInteger(value)||value<min)throw Error('Invalid performance integer');return value;};
const finite = (value,min=0,max=1) => {if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)throw Error('Invalid performance number');return value;};
const id = value => {if(typeof value!=='string'||! /^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(value))throw Error('Invalid performance identifier');return value;};
const hash = value => {if(typeof value!=='string'||! /^[a-f0-9]{64}$/.test(value))throw Error('Invalid performance hash');return value;};
export function canonicalJSON(value){
  if(value===null||typeof value==='boolean'||typeof value==='string')return JSON.stringify(value);
  if(typeof value==='number'){if(!Number.isFinite(value))throw Error('Nonfinite JSON');return JSON.stringify(value);}
  if(Array.isArray(value))return '['+value.map(canonicalJSON).join(',')+']';
  if(value&&Object.getPrototypeOf(value)===Object.prototype)return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonicalJSON(value[k])).join(',')+'}';
  throw Error('Unsupported JSON value');
}
export async function digest(value){const bytes=typeof value==='string'?new TextEncoder().encode(value):value;return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');}
function publicJSON(value){
  if(typeof value==='string'&&/^(?:\/|~\/|https?:\/\/|file:\/\/)/.test(value))throw Error('Private locator in performance record');
  if(Array.isArray(value))value.forEach(publicJSON);
  else if(value&&typeof value==='object')for(const [key,child]of Object.entries(value)){
    if(['path','locator','location','url','token'].includes(key.toLowerCase()))throw Error('Private locator in performance record');publicJSON(child);
  }
}
function timebase(value){integer(value?.num,1);integer(value?.den,1);return value.num/value.den;}
function span(value){integer(value?.start);integer(value?.end,1);if(value.end<=value.start)throw Error('Invalid source span');}

/** Check imported records before touching audio or allocating render resources. */
export function validateRecord(record){
  canonicalJSON(record);publicJSON(record);id(record.composition_id);id(record.record_id);span(record.span);
  timebase(record.timebase);const r=record.runtime;
  if(r?.schema!=='amps.performance-runtime.v1')throw Error('Unsupported performance record');
  const duration=integer(r.duration_frames,1);if(record.span.end-record.span.start!==duration)throw Error('Performance duration mismatch');
  if(integer(r.seed)>0xffffffff)throw Error('Invalid performance seed');
  for(const key of ['engine_sha256','rules_sha256','corpus_sha256'])hash(r[key]);
  const p=r.profile;for(const key of ['max_depth','audio_voices','visual_instances','pending_events','lookahead_frames'])integer(p?.[key],1);
  for(const [key,maximum]of Object.entries({max_depth:4,audio_voices:24,visual_instances:12,pending_events:256,lookahead_frames:10*timebase(record.timebase)}))if(p[key]>maximum)throw Error('Initial performance policy exceeded');
  if(typeof p.admitted!=='boolean'||!p.byte_caps||Array.isArray(p.byte_caps))throw Error('Explicit resource admission required');
  Object.values(p.byte_caps).forEach(v=>integer(v));
  if(!Array.isArray(r.materials)||!r.materials.length)throw Error('Prepared materials required');
  const materials=new Map();for(const m of r.materials){id(m.id);hash(m.sha256);span(m.span);timebase(m.span.timebase);
    if(materials.has(m.id)||m.metadata?.qualification?.technical!=='passed'||!m.metadata.qualification.allowed_uses?.includes('performance'))throw Error('Unqualified or duplicate prepared material');
    integer(m.metadata.audio_sample_rate,1);integer(m.metadata.audio_origin_sample);integer(m.metadata.audio_sample_count,1);materials.set(m.id,m);
  }
  const ref=materials.get(r.reference?.material_id),clock=r.reference?.clock;
  if(!ref||!['video','image','material'].includes(ref.kind)||!['loop','hold'].includes(clock?.mode)||clock.start_frame!==ref.span.start||clock.end_frame!==ref.span.end||!materials.has(r.fallback_material_id))throw Error('Protected full reference and fallback required');
  if(!Array.isArray(r.events)||!r.events.length)throw Error('Resolved events required');
  const seen=new Map();let roots=0;
  for(const e of r.events){id(e.id);integer(e.start_frame);integer(e.end_frame,1);integer(e.depth);
    if(seen.has(e.id)||e.start_frame>=e.end_frame||e.end_frame>duration||e.depth>p.max_depth||!['edition','scene','phrase','shot','frame'].includes(e.scale))throw Error('Invalid performance event');
    if(e.parent_id===null){roots++;if(e.depth!==0||e.kind!=='container'||e.start_frame!==0||e.end_frame!==duration)throw Error('Invalid edition root');}
    else{const parent=seen.get(e.parent_id);if(!parent||parent.kind!=='container'||e.depth!==parent.depth+1||e.start_frame<parent.start_frame||e.end_frame>parent.end_frame)throw Error('Invalid event parent');}
    if(e.reused_from!==undefined&&seen.get(e.reused_from)?.kind!==e.kind)throw Error('Invalid composite reuse');
    if(e.kind==='material'){
      const m=materials.get(e.material_id);if(!m)throw Error('Unknown prepared material');
      for(const name of ['picture_clock','matte_clock','audio_clock']){const c=e[name];integer(c?.rate_num,1);integer(c?.rate_den,1);if(!['loop','hold'].includes(c.mode))throw Error('Invalid source clock');
        if(name==='audio_clock'){integer(c.start_sample);integer(c.sample_rate,1);if(c.sample_rate!==m.metadata.audio_sample_rate||c.start_sample<m.metadata.audio_origin_sample||c.start_sample>=m.metadata.audio_origin_sample+m.metadata.audio_sample_count)throw Error('Audio sample domain mismatch');}
        else{integer(c.start_frame);if(c.start_frame<m.span.start||c.start_frame>=m.span.end)throw Error('Picture/matte frame domain mismatch');}
      }
      if(typeof e.audio!=='boolean'||typeof e.picture!=='boolean'||!CATALOG_BY_TYPE[e.fx?.type]||!Array.isArray(e.couplings))throw Error('Invalid resolved output decision');
      finite(e.gain);finite(e.fx.intensity);integer(e.z_index);
    }else if(e.kind!=='container')throw Error('Unknown event kind');
    seen.set(e.id,e);
  }
  if(roots!==1)throw Error('Exactly one edition root required');
  for(const e of r.events)for(const edge of e.couplings||[]){if(seen.get(edge.source_event_id)?.kind!=='material')throw Error('Unknown coupling source');integer(edge.lag_frames,1);finite(edge.amount,-1,1);}
  if(r.initial_state?.frame!==0||typeof r.initial_state.playing!=='boolean')throw Error('Explicit initial play intent required');
  if(r.execution)validateExecution(r.execution,seen,duration);
  return record;
}
function validateExecution(x,events,duration){
  if(!['playback','simulation'].includes(x.observation_mode)||!['degradation_windows','transitions','control_samples'].every(k=>Array.isArray(x[k]))||!x.resource_maxima)throw Error('Invalid execution history');
  for(const w of x.degradation_windows){integer(w.start_frame);if(w.start_frame>=duration||w.end_frame!==null&&(integer(w.end_frame,1)<=w.start_frame||w.end_frame>duration)||!Array.isArray(w.reasons)||!w.reasons.length||!w.reasons.every(v=>typeof v==='string'&&v.length))throw Error('Invalid degradation window');}
  let prior=-1;for(const sample of x.control_samples){integer(sample.frame);if(sample.frame<=prior||sample.frame>duration||!sample.values||Array.isArray(sample.values))throw Error('Invalid control history');prior=sample.frame;
    for(const [key,value]of Object.entries(sample.values)){const e=events.get(key);if(e?.kind!=='material'||sample.frame<e.start_frame||sample.frame>=e.end_frame)throw Error('Invalid observed event');finite(value);}}
  for(const t of x.transitions){integer(t.frame);if(t.frame>duration||!['tick','seek'].includes(t.kind))throw Error('Invalid transition');if(t.kind==='seek'&&typeof t.playing!=='boolean')throw Error('Invalid seek intent');if(t.kind==='tick'){integer(t.unobserved_frames);for(const key of ['started','ended'])if(!Array.isArray(t[key])||!t[key].every(v=>events.get(v)?.kind==='material'))throw Error('Invalid event transition');}}
  for(const [key,value]of Object.entries(x.resource_maxima)){if(!BYTES.includes(key))throw Error('Unknown measured resource');integer(value);}
}
// BigInt intermediate arithmetic preserves Python's rational source-clock floors.
function phase(frames,outputTB,sourceTB,clock={rate_num:1,rate_den:1}){
  return BigInt(frames)*BigInt(outputTB.den)*BigInt(sourceTB.num)*BigInt(clock.rate_num)/(BigInt(outputTB.num)*BigInt(sourceTB.den)*BigInt(clock.rate_den));
}
function position(start,elapsed,origin,count,mode){const value=BigInt(start)+BigInt(elapsed),first=BigInt(origin),length=BigInt(count),last=first+length-1n;return Number(mode==='loop'?first+((value-first)%length+length)%length:value<last?value:last);}

export class RuntimeSupervisor{
  constructor(record){this.record=clone(validateRecord(record));this.runtime=this.record.runtime;this.profile=this.runtime.profile;this.materials=new Map(this.runtime.materials.map(m=>[m.id,m]));this.events=this.runtime.events.filter(e=>e.kind==='material');this.duration=this.runtime.duration_frames;
    this.frame=0;this.playing=false;this.resumeIntent=false;this.status='paused';this.admitted=false;this.reasons=[];this.lastActive=new Set();
    const x=this.runtime.execution||{};this.windows=clone(x.degradation_windows||[]);this.transitions=clone(x.transitions||[]);this.controls=clone(x.control_samples||[]);this.maxima=clone(x.resource_maxima||{});
    if(x.observation_mode==='simulation')throw Error('Simulation history cannot become playback evidence');
  }
  checkFrame(frame){integer(frame);if(frame>this.duration)throw Error('Output frame exceeds recorded duration');return frame;}
  measurements(values){if(!values||!BYTES.every(key=>Number.isSafeInteger(values[key])&&values[key]>=0))throw Error('resource-measurement-unavailable');return Object.fromEntries(BYTES.map(key=>[key,values[key]]));}
  admit(values){if(terminal(this.status))throw Error('Terminal performance');if(this.profile.admitted!==true||!BYTES.every(key=>Number.isSafeInteger(this.profile.byte_caps[key])&&this.profile.byte_caps[key]>0))throw Error('performance-profile-not-admitted');this.measurements(values);this.admitted=true;this.observeResources(values);}
  reasonsAt(frame){return [...new Set(this.windows.filter(w=>w.start_frame<=frame&&(w.end_frame===null||frame<w.end_frame)).flatMap(w=>w.reasons))].sort();}
  degrade(reason){if(terminal(this.status))return;let w=this.windows.find(w=>w.start_frame<=this.frame&&w.end_frame===null);if(!w){w={start_frame:this.frame,end_frame:null,reasons:[]};this.windows.push(w);}if(!w.reasons.includes(reason))w.reasons.push(reason);this.reasons=this.reasonsAt(this.frame);this.status='degraded';}
  observeResources(values){try{values=this.measurements(values);}catch{this.degrade('resource-measurement-unavailable');return;}for(const key of BYTES){this.maxima[key]=Math.max(values[key],this.maxima[key]||0);if(values[key]>this.profile.byte_caps[key])this.degrade(key);}}
  recover(values){values=this.measurements(values);if(terminal(this.status)||!this.admitted||BYTES.some(key=>values[key]>this.profile.byte_caps[key]))throw Error('resource-pressure-not-cleared');for(const w of this.windows)if(w.start_frame<=this.frame&&w.end_frame===null)w.end_frame=Math.max(this.frame,w.start_frame+1);this.reasons=this.reasonsAt(this.frame);this.status=this.reasons.length?'degraded':this.playing?'playing':'paused';}
  resume(){if(!this.admitted||terminal(this.status))throw Error('performance-playback-not-admitted');this.playing=this.resumeIntent=true;this.status=this.reasons.length?'degraded':'playing';return this.advance(this.frame);}
  pause(){this.playing=this.resumeIntent=false;if(!terminal(this.status))this.status=this.reasons.length?'degraded':'paused';return this.snapshot();}
  cancel(){this.playing=this.resumeIntent=false;this.status='cancelled';this.lastActive.clear();return this.snapshot();}
  seek(frame){if(this.status==='cancelled')throw Error('Cancelled performance');this.frame=this.checkFrame(frame);this.reasons=this.reasonsAt(frame);this.lastActive.clear();this.status=frame===this.duration?'finished':this.reasons.length?'degraded':this.playing?'playing':'paused';if(frame===this.duration)this.playing=this.resumeIntent=false;this.transitions.push({kind:'seek',frame,playing:this.playing});return this.playing?this.advance(frame):this.snapshot();}
  omitted(e){return this.windows.some(w=>this.frame>=w.start_frame&&e.end_frame>w.start_frame&&e.start_frame<(w.end_frame??this.frame+1));}
  positions(event){const e=clone(event),m=this.materials.get(e.material_id),elapsed=this.frame-e.start_frame;
    for(const key of ['picture_clock','matte_clock']){const c=e[key];e[key+'_position']=position(c.start_frame,phase(elapsed,this.record.timebase,m.span.timebase,c),m.span.start,m.span.end-m.span.start,c.mode);}
    const c=e.audio_clock;e.audio_clock_position=position(c.start_sample,phase(elapsed,this.record.timebase,{num:c.sample_rate,den:1},c),m.metadata.audio_origin_sample,m.metadata.audio_sample_count,c.mode);
    let modulation=0;e.coupling_observations=e.couplings.map(edge=>{const sample=this.controls.findLast(v=>v.frame<=this.frame-edge.lag_frames),value=sample?.values[edge.source_event_id];if(value!==undefined)modulation+=edge.amount*value;return {source_event_id:edge.source_event_id,observation_frame:value===undefined?null:sample.frame,value:value??null,state:value===undefined?'initial':'observed'};});
    e.effective_gain=clamp(e.gain*(1+modulation));e.effective_intensity=clamp(e.fx.intensity*(1+modulation));return e;
  }
  snapshot(){const ref=clone(this.runtime.reference),m=this.materials.get(ref.material_id);ref.source_frame=position(m.span.start,phase(Math.min(this.frame,this.duration-1),this.record.timebase,m.span.timebase),m.span.start,m.span.end-m.span.start,ref.clock.mode);
    const suppressed=terminal(this.status)||this.reasons.length;const active=suppressed?[]:this.events.filter(e=>e.start_frame<=this.frame&&this.frame<e.end_frame&&!this.omitted(e)).map(e=>this.positions(e));const pending=suppressed?[]:this.events.filter(e=>this.frame<e.start_frame&&e.start_frame<=Math.min(this.duration,this.frame+this.profile.lookahead_frames)).map(clone);
    return {frame:this.frame,status:this.status,playing:this.playing,resume_intent:this.resumeIntent,mode:'playback',reference:ref,active,pending,audio_voices:this.playing?(this.reasons.length?1:active.filter(e=>e.audio).length):0,visual_instances:active.filter(e=>e.picture).length,fallback_material_id:this.reasons.length?this.runtime.fallback_material_id:null,degradation_reasons:[...this.reasons],resource_maxima:{...this.maxima}};
  }
  observeControls(values){if(terminal(this.status))throw Error('Terminal control observation');const expected=this.snapshot().active.map(e=>e.id).sort();if(canonicalJSON(Object.keys(values).sort())!==canonicalJSON(expected))throw Error('Incomplete measured controls');Object.values(values).forEach(v=>finite(v));const sample={frame:this.frame,values:clone(values)},previous=this.controls.find(v=>v.frame===this.frame);if(previous){if(canonicalJSON(previous)!==canonicalJSON(sample))throw Error('Control history is immutable');return;}if(this.controls.at(-1)?.frame>this.frame)throw Error('Cannot insert observations into replay history');if(expected.length)this.controls.push(sample);}
  advance(frame){this.checkFrame(frame);if(!this.playing||terminal(this.status))return this.snapshot();if(frame<this.frame)throw Error('Use explicit seek');const previous=this.frame;this.frame=frame;this.reasons=this.reasonsAt(frame);this.status=frame===this.duration?'finished':this.reasons.length?'degraded':'playing';if(frame===this.duration)this.playing=this.resumeIntent=false;
    let state=this.snapshot();for(const [key,count]of [['audio_voices',state.audio_voices],['visual_instances',state.visual_instances],['pending_events',state.pending.length]])if(count>this.profile[key])this.degrade(key);
    state=this.snapshot();const active=new Set(state.active.map(e=>e.id));if(canonicalJSON([...active].sort())!==canonicalJSON([...this.lastActive].sort())||(frame>previous+1&&!this.reasons.length))this.transitions.push({kind:'tick',frame,started:[...active].filter(v=>!this.lastActive.has(v)).sort(),ended:[...this.lastActive].filter(v=>!active.has(v)).sort(),unobserved_frames:Math.max(0,frame-previous-1)});this.lastActive=active;return state;
  }
  executionRecord(){const r=clone(this.record);r.runtime.execution={degradation_windows:clone(this.windows),observation_mode:'playback',transitions:clone(this.transitions),control_samples:clone(this.controls),resource_maxima:{...this.maxima}};return r;}
  async checkpoint(){const packet={schema:'amps.performance-browser-checkpoint.v1',record:this.executionRecord(),state:{frame:this.frame,playing:this.playing,resume_intent:this.resumeIntent,status:this.status}};return {...packet,sha256:await digest(canonicalJSON(packet))};}
  static async restore(checkpoint){const p=clone(checkpoint),expected=p.sha256;delete p.sha256;if(p.schema!=='amps.performance-browser-checkpoint.v1'||expected!==await digest(canonicalJSON(p)))throw Error('Checkpoint digest mismatch');const s=new RuntimeSupervisor(p.record);s.frame=s.checkFrame(p.state.frame);if(typeof p.state.playing!=='boolean'||typeof p.state.resume_intent!=='boolean'||!['paused','playing','degraded','cancelled','finished'].includes(p.state.status))throw Error('Invalid checkpoint state');s.resumeIntent=p.state.playing||p.state.resume_intent;s.reasons=s.reasonsAt(s.frame);s.status=terminal(p.state.status)?p.state.status:s.reasons.length?'degraded':'paused';return s;}
}

export function referenceGeometry(width,height,aspect){finite(width,1,16384);finite(height,1,16384);finite(aspect,0.01,100);const reserved={x:0,y:height*2/3,width,height:height/3};let w=width,h=w/aspect;if(h>reserved.height){h=reserved.height;w=h*aspect;}return {reserved,expressive:{x:0,y:0,width,height:height*2/3},image:{x:(width-w)/2,y:reserved.y+(reserved.height-h)/2,width:w,height:h}};}

export function audioVariantKey(record,event){return canonicalJSON({material:record.runtime.materials.find(m=>m.id===event.material_id).sha256,fx:event.fx,seed:record.runtime.seed});}
/** Prepare reusable native-rate FX buffers, never a process or model per grain.
 * Account for raw buffers, retained stereo variants and temporary DSP buffers
 * before computation. Cancellation is checked across each preparation boundary.
 */
export async function preparePerformanceAudio(record,prepared,audioContext,{signal}={}){
  validateRecord(record);const events=record.runtime.events.filter(e=>e.kind==='material'&&e.audio),unique=new Map();
  let rawBytes=0;const rawBuffers=new Set();for(const p of prepared.materials.values())if(!rawBuffers.has(p.audioBuffer)){const b=p.audioBuffer;rawBytes+=b.length*b.numberOfChannels*4;rawBuffers.add(b);}
  for(const e of events){const key=audioVariantKey(record,e);if(!unique.has(key))unique.set(key,e);}
  let retained=0,largest=0;for(const e of unique.values()){const b=prepared.materials.get(e.material_id)?.audioBuffer;if(!b)throw Error('Prepared audio unavailable');const bytes=b.length*2*4;retained+=bytes;largest=Math.max(largest,bytes);}
  const cap=record.runtime.profile.byte_caps.decoded_audio_bytes;
  // renderAudio retains source, output and several bounded processor temporaries.
  if(!Number.isSafeInteger(cap)||rawBytes+retained+largest*32>cap)throw Error('prepared-audio-byte-cap');
  const cache=new Map(),variants=new Map();
  for(const [key,e]of unique){signal?.throwIfAborted();await new Promise(resolve=>setTimeout(resolve,0));signal?.throwIfAborted();
    const p=prepared.materials.get(e.material_id),b=p.audioBuffer;
    const source=record.runtime.materials.find(m=>m.id===e.material_id);
    const patch=createSingleModulePatch(e.fx.type,{duration:b.length/b.sampleRate,demonstration:false,module:{intensity:e.fx.intensity,targets:['voice']}});patch.seed=record.runtime.seed;
    const input=Array.from({length:b.numberOfChannels},(_,c)=>b.getChannelData(c));
    const rendered=renderAudio(patch,input,b.sampleRate,b.length/b.sampleRate);
    const buffer=audioContext.createBuffer(2,b.length,b.sampleRate);for(let c=0;c<2;c++)buffer.copyToChannel(rendered.channels[c],c);
    cache.set(key,{key,buffer,report:rendered.report,source_sha256:source.sha256});
  }
  for(const e of events)variants.set(e.id,cache.get(audioVariantKey(record,e)));signal?.throwIfAborted();prepared.audioVariants=variants;return prepared;
}

/** Prepared input contract: persistent AudioBuffers + verified atlas pages.
 * The caller authenticates encoded bytes; this class meters decoded storage.
 */
export class PerformancePlayer{
  constructor({record,prepared,canvas,audioContext,createCanvas,autoTick=true}){
    this.supervisor=new RuntimeSupervisor(record);this.prepared=prepared;this.canvas=canvas;this.context=audioContext;this.createCanvas=createCanvas;this.autoTick=autoTick;this.voices=new Map();this.engines=new Map();this.generation=0;this.mode='horizontal';this.raf=null;this.playPending=false;
    this.measurePrepared();this.supervisor.admit(this.resources());this.safeRender(this.supervisor.snapshot());
  }
  measurePrepared(){let audio=0,textures=0;const buffers=new Set(),images=new Set();
    if(!(this.prepared?.materials instanceof Map))throw Error('Prepared materials unavailable');
    for(const m of this.supervisor.runtime.materials){const p=this.prepared.materials.get(m.id);if(!p||p.sha256!==m.sha256)throw Error('Prepared material identity mismatch');const b=p.audioBuffer;if(!b||b.sampleRate!==m.metadata.audio_sample_rate||b.length!==m.metadata.audio_sample_count||!Number.isSafeInteger(b.numberOfChannels)||b.numberOfChannels<1||b.numberOfChannels>2)throw Error('Prepared audio domain mismatch');
      if(!buffers.has(b)){audio+=b.length*b.numberOfChannels*4;buffers.add(b);}
      const md=p.media;if(!md||md.fps!==m.span.timebase.num/m.span.timebase.den||!Number.isFinite(md.duration)||md.duration*md.fps+1e-6<m.span.end||!Number.isSafeInteger(md.columns)||md.columns<1||!Number.isSafeInteger(md.framesPerPage)||md.framesPerPage<1)throw Error('Prepared picture clock mismatch');
      for(const kind of ['picture','matte']){if(!Array.isArray(p.assets?.[kind])||p.assets[kind].length<Math.ceil(m.span.end/md.framesPerPage))throw Error('Prepared atlas incomplete');for(const image of p.assets[kind]){integer(image.width,1);integer(image.height,1);if(!images.has(image)){textures+=image.width*image.height*4;images.add(image);}}}
    }
    for(const e of this.supervisor.events.filter(e=>e.audio)){const variant=this.prepared.audioVariants?.get(e.id),m=this.supervisor.materials.get(e.material_id),b=variant?.buffer;
      if(!b||variant.key!==audioVariantKey(this.supervisor.record,e)||b.sampleRate!==m.metadata.audio_sample_rate||b.length!==m.metadata.audio_sample_count)throw Error('Prepared retained audio FX unavailable');
      if(!buffers.has(b)){audio+=b.length*b.numberOfChannels*4;buffers.add(b);}
    }
    this.preparedBytes={decoded_audio_bytes:audio,texture_bytes:textures};
  }
  resources(){let rendering=0;for(const engine of this.engines.values()){const images=new Set([...engine.pool,...engine.freeTemporal,...engine.retiredTemporal,...[...engine.temporalCache.values()].map(v=>v.image)]);for(const image of images)rendering+=image.width*image.height*4;}
    return {...this.preparedBytes,texture_bytes:this.preparedBytes.texture_bytes+rendering+this.canvas.width*this.canvas.height*4,event_history_bytes:new TextEncoder().encode(JSON.stringify(this.supervisor.executionRecord())).byteLength};
  }
  stopVoices(){for(const {source,gain}of this.voices.values()){try{source.stop();}catch{}source.disconnect();gain.disconnect();}this.voices.clear();}
  async play(){if(terminal(this.supervisor.status))throw Error('Terminal performance');const generation=++this.generation;this.playPending=true;try{await this.context.resume();}catch(error){if(generation!==this.generation)return;this.playPending=false;throw error;}if(generation!==this.generation)return;this.playPending=false;this.supervisor.resume();this.anchorTime=this.context.currentTime;this.anchorFrame=this.supervisor.frame;this.tick();if(this.autoTick)this.schedule();}
  schedule(){if(this.raf!==null||!this.supervisor.playing)return;this.raf=requestAnimationFrame(()=>{this.raf=null;this.tick();this.schedule();});}
  pause(){++this.generation;this.playPending=false;this.stopVoices();if(this.raf!==null){cancelAnimationFrame(this.raf);this.raf=null;}return this.supervisor.pause();}
  suspend(){const intent=this.playPending||this.supervisor.playing||this.supervisor.resumeIntent;this.pause();if(!terminal(this.supervisor.status))this.supervisor.resumeIntent=intent;return this.supervisor.snapshot();}
  cancel(){this.pause();return this.supervisor.cancel();}
  seek(frame){this.stopVoices();const state=this.supervisor.seek(frame);this.anchorTime=this.context.currentTime;this.anchorFrame=frame;this.safeRender(state);if(this.supervisor.playing)this.syncAudio(this.supervisor.snapshot());return this.supervisor.snapshot();}
  rotate(mode){if(!['horizontal','vertical'].includes(mode))throw Error('Unknown orientation');this.mode=mode;const long=Math.max(this.canvas.width,this.canvas.height),short=Math.min(this.canvas.width,this.canvas.height);this.canvas.width=mode==='horizontal'?long:short;this.canvas.height=mode==='horizontal'?short:long;this.safeRender(this.supervisor.snapshot());}
  tick(){if(!this.supervisor.playing)return this.supervisor.snapshot();const frame=Math.min(this.supervisor.duration,this.anchorFrame+Math.floor(Math.max(0,this.context.currentTime-this.anchorTime)*timebase(this.supervisor.record.timebase)+1e-7));this.supervisor.advance(frame);this.supervisor.observeResources(this.resources());this.safeRender(this.supervisor.snapshot());this.measureControls();const state=this.supervisor.snapshot();this.syncAudio(state);return state;}
  measureControls(){const s=this.supervisor,state=s.snapshot();if(!state.playing||s.controls.some(v=>v.frame===s.frame)||s.controls.at(-1)?.frame>s.frame)return;
    const values={};for(const e of state.active){if(e.audio){const b=this.prepared.audioVariants.get(e.id).buffer,m=s.materials.get(e.material_id),start=e.audio_clock_position-m.metadata.audio_origin_sample;let energy=0,count=0;
        for(let c=0;c<b.numberOfChannels;c++){const pcm=b.getChannelData(c);for(let i=0;i<256;i++){const at=e.audio_clock.mode==='loop'?(start+i)%b.length:Math.min(start+i,b.length-1);const value=pcm[at]*e.effective_gain;energy+=value*value;count++;}}values[e.id]=clamp(Math.sqrt(energy/count));
      }else if(e.picture&&this.visualMeasures?.has(e.id))values[e.id]=this.visualMeasures.get(e.id);
      else{s.degrade('control-measurement-unavailable');return;}}
    s.observeControls(values);
  }
  syncAudio(state){
    let events=state.active.filter(e=>e.audio);
    if(state.playing&&state.fallback_material_id){const m=this.supervisor.materials.get(state.fallback_material_id);events=[{id:'fallback',material_id:m.id,audio_clock:{sample_rate:m.metadata.audio_sample_rate,rate_num:1,rate_den:1,mode:'loop'},audio_clock_position:m.metadata.audio_origin_sample,effective_gain:.25,end_frame:this.supervisor.duration}];}
    if(!state.playing)events=[];const active=new Set(events.map(e=>e.id));for(const [key,voice]of this.voices)if(!active.has(key)){try{voice.source.stop();}catch{}voice.source.disconnect();voice.gain.disconnect();this.voices.delete(key);}
    for(const e of events){let voice=this.voices.get(e.id);if(!voice){const material=this.supervisor.materials.get(e.material_id),p=this.prepared.materials.get(e.material_id),source=this.context.createBufferSource(),gain=this.context.createGain();source.buffer=e.id==='fallback'?p.audioBuffer:this.prepared.audioVariants.get(e.id).buffer;source.loop=true;source.loopStart=e.audio_clock.mode==='loop'?0:(source.buffer.length-1)/source.buffer.sampleRate;source.loopEnd=source.buffer.length/source.buffer.sampleRate;source.playbackRate.value=e.audio_clock.rate_num/e.audio_clock.rate_den;source.connect(gain);gain.connect(this.context.destination);
        const offset=(e.audio_clock_position-material.metadata.audio_origin_sample)/e.audio_clock.sample_rate;
        const duration=(e.end_frame-state.frame)/timebase(this.supervisor.record.timebase);gain.gain.value=e.effective_gain;source.start(this.context.currentTime,offset);source.stop(this.context.currentTime+duration);voice={source,gain};this.voices.set(e.id,voice);}
      voice.gain.gain.setValueAtTime(e.effective_gain,this.context.currentTime);
    }
  }
  engine(materialId){let engine=this.engines.get(materialId);if(!engine){const p=this.prepared.materials.get(materialId);const allocate=(w,h)=>{const bytes=w*h*4;if(this.resources().texture_bytes+bytes>this.supervisor.profile.byte_caps.texture_bytes)throw Error('texture-byte-cap');const canvas=this.createCanvas?this.createCanvas(w,h):document.createElement('canvas');canvas.width=w;canvas.height=h;return canvas;};engine=new VisualEngine(p.media,p.assets,{width:320,height:180,cacheFrames:8,createCanvas:allocate});this.engines.set(materialId,engine);}return engine;}
  drawSource(ctx,materialId,frame,box){const p=this.prepared.materials.get(materialId),md=p.media,index=frame,cell=index%md.framesPerPage,image=p.assets.picture[Math.floor(index/md.framesPerPage)];ctx.drawImage(image,(cell%md.columns)*md.picture.width,Math.floor(cell/md.columns)*md.picture.height,md.picture.width,md.picture.height,box.x,box.y,box.width,box.height);}
  safeRender(state){try{this.render(state);}catch(error){if(error.message!=='texture-byte-cap')throw error;this.supervisor.degrade('texture_bytes');this.stopVoices();this.render(this.supervisor.snapshot());}this.supervisor.observeResources(this.resources());}
  render(state){this.visualMeasures=new Map();const c=this.canvas,ctx=c.getContext('2d'),m=this.supervisor.materials.get(state.reference.material_id),p=this.prepared.materials.get(m.id),aspect=p.media.picture.width/p.media.picture.height,box=referenceGeometry(c.width,c.height,aspect);
    ctx.setTransform(1,0,0,1,0,0);ctx.globalAlpha=1;ctx.fillStyle='#000';ctx.fillRect(0,0,c.width,c.height);
    ctx.save();ctx.beginPath();ctx.rect(0,0,box.expressive.width,box.expressive.height);ctx.clip();
    try{
    const events=[...state.active].filter(e=>e.picture).sort((a,b)=>a.z_index-b.z_index);
    for(const e of events){const engine=this.engine(e.material_id),material=this.supervisor.materials.get(e.material_id);const patch=createSingleModulePatch(e.fx.type,{duration:engine.media.duration,demonstration:false,module:{intensity:e.effective_intensity,targets:['picture']}});patch.seed=this.supervisor.runtime.seed;
      // Explicit picture and categorical matte clocks remain independent.
      const originalFrame=engine.frame;engine.frame=(time,matte=false)=>{const fps=timebase(material.span.timebase),requested=Math.floor(Math.max(0,time)*fps+1e-6),bounded=position(requested,0,material.span.start,material.span.end-material.span.start,e.picture_clock.mode);return originalFrame.call(engine,matte?e.matte_clock_position/fps:bounded/fps,matte);};
      let image;try{image=engine.render(patch,e.picture_clock_position/timebase(material.span.timebase));}finally{engine.frame=originalFrame;}
      if(!e.audio){const pixels=image.getContext('2d').getImageData(0,0,image.width,image.height).data;let sum=0,count=0;for(let i=0;i<pixels.length;i+=64){sum+=(.2126*pixels[i]+.7152*pixels[i+1]+.0722*pixels[i+2])/255*(pixels[i+3]/255);count++;}this.visualMeasures.set(e.id,clamp(sum/Math.max(1,count)));}
      ctx.globalAlpha=1/Math.max(1,events.length);ctx.drawImage(image,0,0,box.expressive.width,box.expressive.height);
    }
    if(!events.length&&state.fallback_material_id){const fm=this.supervisor.materials.get(state.fallback_material_id);this.drawSource(ctx,fm.id,fm.span.start,box.expressive);}
    }finally{ctx.restore();}ctx.globalAlpha=1;ctx.fillStyle='#000';ctx.fillRect(box.reserved.x,box.reserved.y,box.reserved.width,box.reserved.height);
    this.drawSource(ctx,m.id,state.reference.source_frame,box.image);
  }
  async checkpoint(){return this.supervisor.checkpoint();}
  async restore(packet){this.pause();const restored=await RuntimeSupervisor.restore(packet);const graph=r=>{const copy=clone(r);delete copy.runtime.execution;return canonicalJSON(copy);};if(graph(restored.record)!==graph(this.supervisor.record))throw Error('Checkpoint uses another performance');restored.admit(this.resources());this.supervisor=restored;this.safeRender(restored.snapshot());return restored.snapshot();}
}
