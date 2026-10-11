import test from 'node:test';
import assert from 'node:assert/strict';
import {core,workbench,freshPatch} from './runtime.mjs';
import {renderAudio} from '../../web/fx/audio-engine.mjs';

test('multiple sinks and control-only paths are rejected',()=>{
 const p=freshPatch();p.nodes.push({id:'other',type:'output'});p.connections.push({from:'source',to:'other',port:'audio',gain:1,role:'insert'});
 assert.match(core.validatePatch(p).errors.join(),/exactly one output/);
 const q=freshPatch();q.connections=[{from:'source',to:'output',port:'control',gain:1,role:'sidechain'}];
 assert.match(core.validatePatch(q).errors.join(),/reachable/);
});
test('removing an effect coalesces an existing parallel dry cable and retains gain',()=>{
 const p=freshPatch(),id=p.nodes[1].id;
 p.connections.push({from:'source',to:'output',port:'audio',gain:.3,role:'send'});
 workbench.removeProcessor(p,id);
 assert.equal(p.nodes.some(n=>n.id===id),false);
 assert.equal(p.connections.filter(e=>e.port==='audio').length,1);
 assert.equal(p.connections.find(e=>e.port==='audio').gain,1.3);
 assert.equal(core.validatePatch(p).valid,true);
});
test('both decoded monitors must match the manifest rate and exact frame count',()=>{
 const media={duration:2,audio:{sampleRate:24000}},decoded={sampleRate:24000,channels:[new Float32Array(48000),new Float32Array(48000)]};
 assert.doesNotThrow(()=>workbench.validateDecodedAudio(decoded,media));
 assert.throws(()=>workbench.validateDecodedAudio({...decoded,sampleRate:44100},media),/sample rate/);
 assert.throws(()=>workbench.validateDecodedAudio({...decoded,channels:[new Float32Array(47999)]},media),/frame count/);
});
function render(type,params,automation=[],cues){
 const duration=3,sr=8000,n=duration*sr,p=core.createSingleModulePatch(type,{duration,demonstration:false});
 Object.assign(p.nodes[1],{params:{...p.nodes[1].params,...params},macro:[],automation});
 return renderAudio(p,[new Float32Array(n).fill(.1),new Float32Array(n).fill(.1)],sr,duration,{cues});
}
test('queue retains capacity arrivals and bursts only on the next arrival',()=>{
 const params={capacity:2,rate:7,release:.05,burst:10};
 const cue=i=>({id:String(i),start:i*.1,end:i*.1+.05,arrival:.2+i*.1});
 assert.equal(render('queue',params,[],[cue(0),cue(1)]).report.modules[0].overflowBursts,0);
 assert.equal(render('queue',params,[],[cue(0),cue(1),cue(2)]).report.modules[0].overflowBursts,1);
});
test('linear feedback reset automation resets once per crossing',()=>{
 const result=render('feedback',{reset:1},[{parameter:'params.reset',interpolation:'linear',keyframes:[{time:0,value:1},{time:3,value:2}]}]);
 assert.equal(result.report.modules[0].resetTimes.length,1);
 assert.ok(Math.abs(result.report.modules[0].resetTimes[0]-1.5)<.001);
});
