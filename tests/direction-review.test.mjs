import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html=fs.readFileSync(process.env.AMP_DIRECTION_REVIEW_HTML||new URL('../web/direction-review.html',import.meta.url),'utf8');
const initial=JSON.parse(html.match(/<script id="initial" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const script=html.match(/<script>\s*('use strict';[\s\S]*?)<\/script>/)[1];
function panel(){
 const nodes=new Map();let downloads=0;
 const node=id=>{if(!nodes.has(id))nodes.set(id,{id,value:'',textContent:id==='initial'?JSON.stringify(initial):'',events:{},dataset:{},children:[],addEventListener(type,fn){this.events[type]=fn;},setAttribute(){},append(child){this.children.push(child);},click(){downloads++;}});return nodes.get(id);};
 const context={document:{getElementById:node,createElement:()=>node('generated-'+nodes.size),querySelectorAll:()=>node('variants').children},window:{},structuredClone,console,Blob,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},setTimeout:()=>{}};
 vm.runInNewContext(script,context);
 return {node,api:context.window.directionReview,downloads:()=>downloads,
  edit(id,value){node(id).value=value;node(id).events.input({target:node(id)});},
  async import(value){const control=node('import');control.files=[{size:100,text:async()=>JSON.stringify(value)}];await control.onchange({target:control});}};
}
const plain=value=>JSON.parse(JSON.stringify(value));
test('complete recipe validation rejects malformed nested data and unknown operations',()=>{
 const p=panel();assert.equal(p.api.validateRecipe(initial),685);
 const changes=[
  r=>r.segments[0].source_start='invalid',r=>r.camera[0]=null,
  r=>r.typography[0].position=[-1,.5],r=>r.note='',r=>r.note='x'.repeat(4001),
  r=>r.status='accepted',r=>r.fps=true,r=>r.camera[0].command='ignored',
  r=>r.segments[1].source_start++,r=>r.segments[1].output_frames=1,
  r=>r.camera[0].seed_roi=[.99,.5,.1,.2],r=>r.camera[1].id=r.camera[0].id,
  r=>r.typography[0].output_end=900,r=>r.typography[0].provenance='verified',
  r=>r.typography[0].text='bad\ntext',r=>r.typography[0].opacity=null,
 ];
 for(const change of changes){const value=structuredClone(initial);change(value);assert.throws(()=>p.api.validateRecipe(value));}
});
test('failed import preserves prior valid edits and remains exportable',async()=>{
 const p=panel();p.edit('note','Keep the preceding work.');const before=p.api.getRecipe();
 for(const change of [r=>r.segments[0].source_start='invalid',r=>r.camera[1]=null]){
  const invalid=structuredClone(initial);change(invalid);await p.import(invalid);
  assert.deepEqual(plain(p.api.getRecipe()),plain(before));
 }
 p.node('export').onclick();assert.equal(p.downloads(),1);
});
test('pace round trip restores original typography and does not alter opacity',()=>{
 const p=panel();p.edit('pace','0');assert.equal(p.api.getRecipe().typography[2].output_end,661);
 p.edit('pace','24');assert.deepEqual(plain(p.api.getRecipe()),initial);
});
test('imported typography becomes the reversible pace baseline',async()=>{
 const p=panel(),value=structuredClone(initial);value.typography[2].output_end=683;
 await p.import(value);p.edit('pace','0');p.edit('pace','24');assert.equal(p.api.getRecipe().typography[2].output_end,683);
});
test('empty and oversized note exports are blocked',()=>{
 const p=panel();for(const value of ['', 'x'.repeat(4001)]){p.edit('note',value);p.node('export').onclick();assert.equal(p.downloads(),0);assert.match(p.node('state').textContent,/Cannot export/);}
 p.edit('note','Repaired note');p.node('export').onclick();assert.equal(p.downloads(),1);
});
test('note-only edits retain distinct authored opacity values',()=>{
 const p=panel();p.edit('note','Text edit');assert.deepEqual(plain(p.api.getRecipe().typography),initial.typography);
});
