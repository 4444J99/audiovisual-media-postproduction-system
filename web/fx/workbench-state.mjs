import {clonePatch,validatePatch,CATALOG_BY_TYPE,buildSerialConnections} from './core.mjs';

/** Validate UI extensions before a portable patch can enter the workbench. */
export function normalizeWorkbenchPatch(input,context={}) {
  const patch=clonePatch(input);
  if(!patch||typeof patch!=='object'||Array.isArray(patch))throw Error('Patch must be an object.');
  patch.metadata??={};const m=patch.metadata;
  if(typeof m!=='object'||Array.isArray(m))throw Error('Patch metadata must be an object.');
  if(m.wordMode!=null&&!['cues','authored'].includes(m.wordMode))throw Error('Unknown word material mode.');
  if(m.words!=null&&(typeof m.words!=='string'||m.words.length>2000))throw Error('Authored words must be a string under 2,000 characters.');
  if(m.description!=null&&typeof m.description!=='string')throw Error('Patch description must be a string.');
  if(m.demoPhases!=null&&(!Array.isArray(m.demoPhases)||m.demoPhases.length>100||m.demoPhases.some(p=>!p||!Number.isFinite(p.start)||!Number.isFinite(p.end)||p.start<0||p.end>patch.duration+1e-6||p.end<=p.start||typeof p.name!=='string')))throw Error('Invalid demonstration phases.');
  if(m.demoPhases?.some((phase,index)=>index>0&&phase.start<m.demoPhases[index-1].end))throw Error('Demonstration phases must be ordered and non-overlapping.');
  if((patch.nodes?.length||0)>64||(patch.connections?.length||0)>1024||(patch.events?.length||0)>5000)throw Error('This browser workbench supports up to 64 nodes, 1,024 cables and 5,000 recorded changes.');
  if(context.duration!=null&&(Math.abs(patch.duration-context.duration)>1e-6||Math.abs(patch.source?.duration-context.duration)>1e-6))throw Error('Patch duration does not match the loaded source passage.');
  const check=value=>{
    if(Array.isArray(value.nodes))for(const n of value.nodes){
      if(n?.name!=null&&typeof n.name!=='string')throw Error('Processor names must be strings.');
      if(n?.objectRect!=null&&(!Array.isArray(n.objectRect)||n.objectRect.length!==4||n.objectRect.some(x=>!Number.isFinite(x)||x<0||x>1)))throw Error('Object rectangles require four normalized numbers.');
    }
    const result=validatePatch(value,context);if(!result.valid)throw Error(result.errors.slice(0,3).join(' · '));
  };
  check(patch);
  if(m.customModuleStates!=null){
    if(typeof m.customModuleStates!=='object'||Array.isArray(m.customModuleStates))throw Error('Saved custom module states must be a map.');
    const safe=Object.create(null);
    for(const [id,saved] of Object.entries(m.customModuleStates)){
      const current=patch.nodes.find(n=>n.id===id);
      if(!current||!Object.hasOwn(CATALOG_BY_TYPE,current.type)||!saved||typeof saved!=='object'||Array.isArray(saved))throw Error('Saved custom state refers to an invalid processor.');
      const node=saved.node||saved,events=saved.events||[];
      if(node.id!==id||node.type!==current.type||!Array.isArray(events)||events.some(e=>e.nodeId!==id))throw Error('Saved custom state does not match its processor.');
      check({...patch,nodes:patch.nodes.map(n=>n.id===id?node:n),events:patch.events.filter(e=>e.nodeId!==id).concat(events)});
      safe[id]={node:clonePatch(node),events:clonePatch(events)};
    }
    m.customModuleStates=safe;
  }
  return patch;
}

/** Read the authored toggle, independently of clip scope or another node's solo. */
export function toggleValue(node,parameter,time,patch) {
  if(!['bypass','solo'].includes(parameter))throw Error('Unknown processor toggle.');
  let value=node[parameter],latest=-Infinity;
  for(const event of patch.events||[])if(event.nodeId===node.id&&event.parameter===parameter&&event.time<=time&&event.time>=latest){
    value=event.value;latest=event.time;
  }
  return value;
}

/** Capture one undo entry before a pointer drag or a held keyboard range gesture. */
export function bindRangeUndo(element,snapshot) {
  const isRange=event=>event.target.matches('input[type=range]');
  element.addEventListener('pointerdown',event=>{if(isRange(event))snapshot();});
  const keys=new Set(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown']);
  element.addEventListener('keydown',event=>{if(isRange(event)&&keys.has(event.key)&&!event.repeat)snapshot();});
}

/** Insert at the declared sink; portable graphs do not reserve the ID "output". */
export function insertProcessorBeforeOutput(patch,node) {
  const index=patch.nodes.findIndex(candidate=>candidate.type==='output');
  if(index<0)throw Error('Patch has no output.');
  const outputId=patch.nodes[index].id;
  const incoming=patch.connections.filter(edge=>edge.to===outputId&&edge.port!=='control');
  const ports=[...new Set(incoming.map(edge=>edge.port))];
  let inputId=node.id;
  if(incoming.length>ports.length){
    // The sink is also a valid summing bus. Preserve that bus before inserting
    // a processor, which accepts only one incoming stream per typed port.
    const ids=new Set(patch.nodes.map(candidate=>candidate.id));ids.add(node.id);
    const base=`${node.id}-input-mix`;let id=base,suffix=1;
    while(ids.has(id))id=`${base}-${suffix++}`;
    patch.nodes.splice(index,0,{id,type:'mix',gain:1});
    inputId=id;
    patch.connections.push(...buildSerialConnections([id,node.id],ports));
  }
  patch.nodes.splice(patch.nodes.findIndex(candidate=>candidate.id===outputId),0,node);
  for(const edge of incoming)edge.to=inputId;
  patch.connections.push(...buildSerialConnections([node.id,outputId]));
}

/** Portable source IDs are not reserved names. */
export function setSourceSidechain(patch,node,enabled) {
  const source=enabled?patch.nodes.find(candidate=>candidate.type==='source'):null;
  if(enabled&&!source)throw Error('Patch has no source.');
  patch.connections=patch.connections.filter(edge=>!(edge.to===node.id&&edge.port==='control'));
  if(enabled){
    node.modulation={parameter:'intensity',amount:.6,mode:'add'};
    patch.connections.push({from:source.id,to:node.id,port:'control',gain:1,role:'sidechain'});
  }else delete node.modulation;
}

/** Preserve parallel signal amplitude while bypassing a removed processor. */
export function removeProcessor(patch,id) {
  const incoming=patch.connections.filter(e=>e.to===id),outgoing=patch.connections.filter(e=>e.from===id);
  const edges=patch.connections.filter(e=>e.from!==id&&e.to!==id);
  for(const a of incoming)for(const b of outgoing)if(a.port===b.port&&a.port!=='control'){
    const existing=edges.find(e=>e.from===a.from&&e.to===b.to&&e.port===a.port);
    const gain=a.gain*b.gain;
    if(existing)existing.gain+=gain;
    else edges.push({from:a.from,to:b.to,port:a.port,gain,role:b.role});
  }
  patch.connections=edges;patch.nodes=patch.nodes.filter(n=>n.id!==id);
  patch.events=patch.events.filter(e=>e.nodeId!==id);
  if(patch.metadata?.customModuleStates)delete patch.metadata.customModuleStates[id];
}

export function validateDecodedAudio(decoded,media) {
  const sr=media.audio.sampleRate,frames=Math.round(media.duration*sr);
  if(decoded.sampleRate!==sr)throw Error('Decoded WAV sample rate does not match the media manifest.');
  if(!decoded.channels?.length||decoded.channels.some(c=>c.length!==frames))throw Error('Decoded WAV frame count does not match the media manifest duration.');
  return decoded;
}
