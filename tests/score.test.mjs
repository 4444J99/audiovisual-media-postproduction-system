import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
// Import .js as an ES module without imposing a package manager on a static site.
const moduleText=await readFile(new URL('../web/score.js',import.meta.url),'utf8');
const {evaluate,stateFromEvents,makeSession,validateSession}=await import('data:text/javascript;base64,'+Buffer.from(moduleText).toString('base64'));
const cfg=JSON.parse(await readFile(new URL('../projects/god-here/composition.json',import.meta.url),'utf8'));
assert.equal(evaluate(cfg,95).shot.id,'SHOT-06');
assert.equal(evaluate(cfg,3).shot,undefined);
const events=[{source_time:10,selected:'P01',amount:.7},{source_time:12,selected:null,amount:0}];
assert.equal(stateFromEvents(events,9).selected,null);
assert.equal(stateFromEvents(events,11).selected,'P01');
assert.equal(stateFromEvents(events,13).residue.person,'P01');
assert.equal(stateFromEvents(events,15).residue,null);
const data=makeSession(cfg,events,false);assert.equal(validateSession(data,cfg),true);
assert.throws(()=>validateSession({...data,events:[{source_time:-1,selected:'P01',amount:2}]},cfg));
assert.throws(()=>validateSession({...data,source_sha256:'wrong'},cfg));
console.log('Transport, score replay, residues, and invalid-session checks passed');
