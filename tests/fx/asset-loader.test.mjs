import test from 'node:test';
import assert from 'node:assert/strict';
import {readAsset} from '../../web/fx/asset-loader.mjs';

test('reads complete JSON and binary response bodies',async()=>{
  assert.deepEqual(await readAsset('/manifest.json',{fetchImpl:async()=>new Response('{"duration":12}')}),{duration:12});
  const bytes=new Uint8Array([82,73,70,70]);
  const result=await readAsset('/source.wav',{format:'arrayBuffer',fetchImpl:async()=>new Response(bytes)});
  assert.deepEqual(new Uint8Array(result),bytes);
});

test('reports a missing required asset with its name and HTTP status',async()=>{
  await assert.rejects(readAsset('/source.wav',{label:'Source sound',fetchImpl:async()=>new Response('',{status:404})}),/Source sound could not load \(HTTP 404\)/);
});

test('a stalled request cannot leave loading pending and is aborted',async()=>{
  let signal;
  await assert.rejects(readAsset('/manifest.json',{label:'Source details',timeoutMs:15,fetchImpl:(_url,options)=>{
    signal=options.signal;
    return new Promise(()=>{});
  }}),/Source details took too long to load/);
  assert.equal(signal.aborted,true);
});

test('a response with a stalled body also reaches the retry state',async()=>{
  let signal;
  await assert.rejects(readAsset('/source.wav',{label:'Source sound',format:'arrayBuffer',timeoutMs:15,fetchImpl:async(_url,options)=>{
    signal=options.signal;
    return {ok:true,arrayBuffer:()=>new Promise(()=>{})};
  }}),/Source sound took too long to load/);
  assert.equal(signal.aborted,true);
});

test('malformed metadata produces an actionable error',async()=>{
  await assert.rejects(readAsset('/manifest.json',{label:'Source details',fetchImpl:async()=>new Response('not json')}),/Source details could not be read/);
});

test('network failures produce an actionable error',async()=>{
  await assert.rejects(readAsset('/source.wav',{label:'Source sound',fetchImpl:async()=>{throw new TypeError('Failed to fetch');}}),/Source sound could not be read/);
});
