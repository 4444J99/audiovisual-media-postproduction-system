import {clonePatch,validatePatch,CATALOG_BY_TYPE} from './core.mjs';

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
