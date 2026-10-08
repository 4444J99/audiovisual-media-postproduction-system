export function evaluate(config,t){
 const shot=config.shots.find(s=>s.start<=t&&t<s.end),layout=shot?config.layouts[shot.layout]:null;
 const state=Object.fromEntries(Object.keys(config.performers).map(p=>[p,0]));
 for(const cue of config.cues){if(t<cue.start||t>=cue.end)continue;const ramp=Math.max(0,Math.min(1,(t-cue.start)/Math.max(cue.attack,.000001),(cue.end-t)/Math.max(cue.release,.000001)));state[cue.performer]=Math.max(state[cue.performer],cue.intensity*(.5-.5*Math.cos(Math.PI*ramp)));}
 return {shot,layout,state};
}
export function stateFromEvents(events,t){
 let previous=null,last=null;
 for(const e of events){if(e.source_time>t)break;previous=last;last=e;}
 if(!last)return {selected:null,amount:0,residue:null};
 const elapsed=t-last.source_time;
 const residue=previous?.selected&&previous.selected!==last.selected&&elapsed<2.5?{person:previous.selected,amount:previous.amount*.4*(1-elapsed/2.5)}:null;
 return {selected:last.selected,amount:last.amount,residue};
}
export function validateSession(data,config){
 if(data.schema_version!=='1.0'||data.project!==config.project||data.score_version!==config.score_version||data.source_sha256!==config.source_sha256)throw Error('Incompatible source or score version');
 if(!Array.isArray(data.events)||data.events.length>10000)throw Error('Invalid event count');
 let prior=-1;for(const e of data.events){if(!Number.isFinite(e.source_time)||e.source_time<prior||e.source_time<0||e.source_time>112||!Number.isFinite(e.amount)||e.amount<0||e.amount>1||e.selected!==null&&!(e.selected in config.performers))throw Error('Invalid event');prior=e.source_time;}
 if(typeof data.reduced_motion!=='boolean')throw Error('Invalid motion setting');return true;
}
export function makeSession(config,events,reduced){return {schema_version:'1.0',project:config.project,score_version:config.score_version,source_sha256:config.source_sha256,capture_kind:'source-time attention score; not a video recording or wall-clock interaction log',events:events.slice().sort((a,b)=>a.source_time-b.source_time),reduced_motion:reduced};}
