import {test} from 'node:test';
import assert from 'node:assert/strict';
import {installPresentation, contentHeight, reviewView} from '../../web/studio/presentation.mjs';

// Small DOM contract fixture: checks moved controls retain identity/listeners,
// responsive disclosure state, and height measurement. No browser/layout claims.
class Element {
  constructor(tag='div') {this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attrs={};this.listeners={};this.style={};this.rect={bottom:100};}
  get classList(){return {add:()=>{}};}
  append(...nodes){for(const node of nodes){node.detach();this.children.push(node);node.parent=this;}}
  prepend(node){node.detach();this.children.unshift(node);node.parent=this;}
  detach(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
  before(node){const p=this.parent;if(!p)throw Error('Fixture node must have a parent');node.detach();p.children.splice(p.children.indexOf(this),0,node);node.parent=p;}
  closest(selector){return selector==='label'?this.parent:null;}
  addEventListener(name,handler){(this.listeners[name]||=[]).push(handler);}
  click(){for(const handler of this.listeners.click||[])handler({target:this});}
  setAttribute(name,value){this.attrs[name]=value;}
  getBoundingClientRect(){return this.rect;}
}
function fixture(phone=true){
  const main=new Element('main'),body=new Element('body');body.append(main);
  const query={matches:phone,listeners:[],addEventListener(_,f){this.listeners.push(f);},change(value){this.matches=value;for(const f of this.listeners)f({matches:value});}};
  const ids=new Map(),selectors=new Map([['main',main]]);
  for(const id of ['rate','mute','volume','new-at-time','source-table','notes-view']){const e=new Element(id==='rate'?'select':'button');ids.set(id,e);main.append(e);}
  const label=new Element('label');main.append(label);label.append(ids.get('rate'));
  for(const name of ['.overlay-controls','.rangebar','.header-actions','.bottom','[data-tab="notes"]','[data-tab="events"]']){const e=new Element();main.append(e);selectors.set(name,e);}
  return {body,main,query,ids,selectors,createElement:tag=>new Element(tag),getElementById:id=>ids.get(id),querySelector:q=>selectors.get(q),defaultView:{scrollY:0,matchMedia:()=>query,getComputedStyle:el=>({display:'block',position:'static',marginBottom:'0',...el.style})}};
}
function nav(doc){return doc.main.children.find(e=>e.className==='studio-review-views');}
function details(doc){const result=[];function visit(e){if(e.tagName==='DETAILS')result.push(e);for(const child of e.children)visit(child);}visit(doc.body);return result;}

test('unknown review views return to Watch',()=>{for(const value of [null,'garbage','watch'])assert.equal(reviewView(value),'watch');assert.equal(reviewView('records'),'records');});
test('phone panes preserve the native record table and note handlers',()=>{
  const d=fixture();const original=d.ids.get('new-at-time');let notes=0;original.addEventListener('click',()=>notes++);
  installPresentation(d,'review');assert.equal(d.body.dataset.reviewView,'watch');
  assert.equal(nav(d).children.length,4);assert.equal(d.getElementById('new-at-time'),original);
  original.click();assert.equal(notes,1);assert.equal(d.body.dataset.reviewView,'notes');
  assert.equal(nav(d).children[2].attrs['aria-pressed'],'true');
});
test('Records and Notes activate their existing document tabs',()=>{
  const d=fixture();let records=0,notes=0;
  d.selectors.get('[data-tab="events"]').addEventListener('click',()=>records++);
  d.selectors.get('[data-tab="notes"]').addEventListener('click',()=>notes++);
  installPresentation(d,'review');nav(d).children[3].click();nav(d).children[2].click();
  assert.equal(records,1);assert.equal(notes,1);
});
test('desktop note creation keeps the simultaneous workspace',()=>{const d=fixture(false);installPresentation(d,'review');d.ids.get('new-at-time').click();assert.equal(d.body.dataset.reviewView,'watch');});
test('secondary controls collapse on phones and reopen on wider screens',()=>{
  const d=fixture();const mute=d.ids.get('mute');let muted=false;mute.addEventListener('click',()=>muted=true);
  installPresentation(d,'review');assert.equal(details(d).length,3);assert.ok(details(d).every(e=>!e.open));
  mute.click();assert.equal(muted,true);d.query.change(false);assert.ok(details(d).every(e=>e.open));
  d.query.change(true);assert.ok(details(d).every(e=>!e.open));
});
test('presentation installation is idempotent and retains control values',()=>{
  const d=fixture();d.ids.get('rate').value='0.75';installPresentation(d,'review');installPresentation(d,'review');
  assert.equal(d.main.children.filter(e=>e.className==='studio-review-views').length,1);assert.equal(d.ids.get('rate').value,'0.75');
});
test('content measurement excludes hidden/fixed overlays and can shrink',()=>{
  const d=fixture();d.main.rect.bottom=900;
  const toast=new Element();toast.style.position='fixed';toast.rect.bottom=5000;d.body.append(toast);
  const hidden=new Element();hidden.hidden=true;hidden.rect.bottom=6000;d.body.append(hidden);
  assert.equal(contentHeight(d),924);d.main.rect.bottom=300;assert.equal(contentHeight(d),324);
  d.defaultView.scrollY=50;d.main.style.marginBottom='10';assert.equal(contentHeight(d),384);
});
