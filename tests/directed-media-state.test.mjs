import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const web=process.env.AMP_WEB_ROOT||new URL('../web/',import.meta.url);
function panel(name){
 const html=fs.readFileSync(typeof web==='string'?path.join(web,name):new URL(name,web),'utf8');
 const isDirection=name==='direction-review.html';
 const scripts=[...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)];
 const script=scripts.filter(([,attrs])=>!attrs.includes('application/json')).map(([,attrs,body])=>body).join('\n');
 const initial=scripts.find(([,attrs])=>attrs.includes('application/json'))?.[2]||'';
 const nodes=new Map(),blobs=[];let downloads=0;
 function node(id){if(!nodes.has(id))nodes.set(id,{id,value:id==='variant'?'proof-A.mp4':'',textContent:id==='initial'?initial:'',disabled:['save','saveReview','fullscreen'].includes(id),currentTime:0,duration:NaN,readyState:0,error:null,hidden:false,paused:true,loadCalls:0,events:{},children:[],dataset:{},
   pause(){this.paused=true;},play(){this.paused=false;return Promise.resolve();},load(){this.loadCalls++;},
   addEventListener(type,fn){(this.events[type]??=[]).push(fn);},setAttribute(){},append(child){this.children.push(child);},click(){downloads++;},
   dispatch(type){for(const fn of this.events[type]||[])fn({target:this});this['on'+type]?.({target:this});}
 });return nodes.get(id);}
 const context={document:{getElementById:node,createElement:()=>node('generated-'+nodes.size),querySelectorAll:()=>node('variants').children},window:{},structuredClone,Blob,URL:{createObjectURL:blob=>{blobs.push(blob);return 'blob:fixture';},revokeObjectURL(){}},setTimeout(){}};
 vm.runInNewContext(script,context,{filename:name});
 const video=node(isDirection?'film':'picture'),save=node(isDirection?'saveReview':'save');
 return {node,video,save,blobs,downloads:()=>downloads,ready(){video.readyState=1;video.duration=22.5;video.error=null;video.dispatch('loadedmetadata');},fail(){video.error={code:4};video.dispatch('error');},choose(){if(isDirection)node('variants').children[0].onclick();else{node('variant').value='directed-gap.mp4';node('variant').onchange();}}};
}
for(const name of ['direction-review.html','directed-review.html']){
 test(name+' cannot export a fabricated source time before metadata loads',()=>{
  const p=panel(name);assert.equal(p.save.disabled,true);p.save.onclick();assert.equal(p.downloads(),0);assert.match(p.node('mediaStatus').textContent,/Load a .*video before saving/);
 });
 test(name+' saves source time only after real metadata and disables it again on media failure',async()=>{
  const p=panel(name);p.ready();assert.equal(p.save.disabled,false);p.video.currentTime=2;p.save.onclick();assert.equal(p.downloads(),1);
  const data=JSON.parse(await p.blobs[0].text());assert.ok(Number.isFinite(data.source_seconds??data.source_time));
  p.node(name==='direction-review.html'?'review':'notes').value='Keep this observation';p.fail();assert.equal(p.save.disabled,true);assert.equal(p.video.hidden,true);p.save.onclick();assert.equal(p.downloads(),1);
  assert.equal(p.node(name==='direction-review.html'?'review':'notes').value,'Keep this observation');
 });
 test(name+' variant changes clear the prior ready state and retry recovers cleanly',()=>{
  const p=panel(name);p.ready();p.choose();assert.equal(p.save.disabled,true);p.save.onclick();assert.equal(p.downloads(),0);p.fail();assert.equal(p.node('retryMedia').hidden,false);p.node('retryMedia').onclick();assert.equal(p.video.loadCalls,1);p.ready();assert.equal(p.save.disabled,false);assert.equal(p.video.hidden,false);assert.equal(p.node('retryMedia').hidden,true);
 });
}
test('direction recipe exports remain available when its media is unavailable',()=>{const p=panel('direction-review.html');p.fail();p.node('export').onclick();assert.equal(p.downloads(),1);assert.equal(p.save.disabled,true);});
