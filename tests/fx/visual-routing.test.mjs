import test from 'node:test';
import assert from 'node:assert/strict';
import {visual, core} from './runtime.mjs';
import {renderAudio} from '../../web/fx/audio-engine.mjs';

const {VisualEngine} = visual;
function canvasStub(draws = []) {
  const ctx = {
    globalAlpha: 1,
    drawImage(image) {draws.push({image, alpha: this.globalAlpha, operation: this.globalCompositeOperation});},
    fillRect() {}, clearRect() {}, setTransform() {}, save() {}, restore() {},translate(){},rotate(){},scale(){},
  };
  return {width: 32, height: 18, getContext: () => ctx};
}

test('a sole unity-gain body return applies its alpha isolation', () => {
  let maskCalls = 0; const body = {id: 'body', targets: ['body'], region: 'light-gray-shirt'};
  const fake = {
    width: 32, height: 18,
    inputs: () => [{from: 'body', to: 'output', port: 'picture', role: 'return', gain: 1}],
    signal: () => ({image: canvasStub(), active: true}), canvas: () => canvasStub(), copy: () => canvasStub(),
    branchDescriptor: () => body, mask() {maskCalls++; return canvasStub();},
  };
  VisualEngine.prototype.input.call(fake, {id: 'output', type: 'output'}, 'picture', 4);
  assert.equal(maskCalls, 1);
});

test('room-only parallel returns preserve the dry performer pixels', () => {
  function pixels(values=[0,0],alphas=[0,0]){
    const image={values:[...values],alphas:[...alphas]},ctx={globalAlpha:1,globalCompositeOperation:'source-over',
      fillRect(){image.values.fill(0);image.alphas.fill(1);},
      drawImage(source){for(let i=0;i<2;i++){
        const a=source.alphas[i]*this.globalAlpha;
        if(this.globalCompositeOperation==='destination-in'){image.alphas[i]*=a;continue;}
        if(this.globalCompositeOperation==='lighter'){image.values[i]+=source.values[i]*a;image.alphas[i]=Math.min(1,image.alphas[i]+a);}
        else{image.values[i]=source.values[i]*a+image.values[i]*(1-a);image.alphas[i]=a+image.alphas[i]*(1-a);}
      }}};image.getContext=()=>ctx;return image;
  }
  const dry=pixels([40,20],[1,1]),returned=pixels([40,100],[1,1]),roomMask=pixels([0,0],[0,1]);
  const fake={width:2,height:1,canvas:()=>pixels(),copy:image=>pixels(image.values,image.alphas),
    inputs:()=>[{from:'dry',port:'picture',gain:1,role:'insert'},{from:'room',port:'picture',gain:1,role:'return'}],
    signal:id=>({image:id==='dry'?dry:returned,active:true}),
    branchDescriptor:()=>({id:'room',targets:['room'],region:'all'}),mask:()=>roomMask};
  const result=VisualEngine.prototype.input.call(fake,{id:'output'},'picture',2).image;
  assert.deepEqual(result.values,[40,100],'only the background pixel is replaced by the return');
});

function feedbackEngine(node,patch={nodes:[node],connections:[],events:[],seed:1}){
  const draws=[],engine=new VisualEngine({duration:4,fps:12},{},{width:32,height:18,createCanvas:()=>canvasStub(draws)});
  engine.patch=patch;engine.nodeMap=new Map(patch.nodes.map(n=>[n.id,n]));
  return {engine,patch,draws};
}

test('feedback reset ramps rebuild picture returns after a single crossing', () => {
  const node=core.createModule('feedback',{macro:[],params:{time:.25,repeats:8,reset:0},automation:[{parameter:'params.reset',interpolation:'linear',keyframes:[{time:0,value:0},{time:4,value:4}]}]});
  const {engine,patch,draws}=feedbackEngine(node);
  assert.equal(engine.feedbackEpoch(node,2),0);
  engine.effect(core.evaluatedNode(node,2,patch),2,'picture',()=>canvasStub());
  assert.equal(draws.length,9,'dry frame and eight feedback returns survive the reset ramp');
});

test('picture feedback follows audio reset crossings and is stable across backward seeks', () => {
  const node=core.createModule('feedback',{macro:[],params:{reset:1},automation:[{parameter:'params.reset',interpolation:'linear',keyframes:[{time:0,value:1},{time:3,value:2}]}]});
  const patch=core.createSingleModulePatch('feedback',{duration:3,demonstration:false});
  node.id=patch.nodes[1].id;patch.nodes[1]=node;
  const {engine}=feedbackEngine(node,patch);
  const sr=8000,input=[new Float32Array(sr*3).fill(.1),new Float32Array(sr*3).fill(.1)];
  const resets=renderAudio(patch,input,sr,3).report.modules[0].resetTimes;
  assert.equal(resets.length,1);assert.ok(Math.abs(resets[0]-1.5)<.001);
  assert.equal(engine.feedbackEpoch(node,2.75),1.5);
  assert.equal(engine.feedbackEpoch(node,1),0);
  assert.equal(engine.feedbackEpoch(node,2),1.5);
});

test('feedback resets again only after automation becomes inactive and crosses again', () => {
  const node=core.createModule('feedback',{macro:[],params:{reset:0},automation:[{parameter:'params.reset',interpolation:'step',keyframes:[{time:0,value:0},{time:1,value:3},{time:2,value:2}]}]});
  const {engine}=feedbackEngine(node);
  assert.equal(engine.feedbackEpoch(node,2.5),2);
  assert.equal(engine.feedbackEpoch(node,1.5),0);
  assert.equal(engine.feedbackEpoch(node,.5),0);
});

test('visual gate detector responds to the supplied control envelope and threshold', () => {
  const node = core.createModule('gate', {params: {detector: 1, threshold: .4, retain: .1}});
  for (const [envelope, expected] of [[.2, .1], [.8, 1]]) {
    const draws = [], fake = {width: 32, height: 18, patch: {seed: 1}, canvas: () => canvasStub(draws), envelope: () => envelope};
    VisualEngine.prototype.effect.call(fake, node, 2, 'picture', () => canvasStub());
    assert.equal(draws.at(-1).alpha, expected);
  }
});

test('source-node gain contributes to picture output', () => {
  const draws = [], sourceImage = canvasStub();
  const engine = new VisualEngine({duration: 2, fps: 12}, {}, {width: 32, height: 18, createCanvas: () => canvasStub(draws)});
  const source = {id: 'source', type: 'source', gain: .5};
  engine.patch = {nodes: [source], connections: []}; engine.nodeMap = new Map([[source.id, source]]);
  engine.frame = () => sourceImage;
  engine.signal('source', 'picture', 0);
  assert.ok(draws.some(draw => draw.image === sourceImage && draw.alpha === .5));
});

test('word persistence applies to both cue-based and authored word material', () => {
  const fake = {cues: {words: [{text: 'OUT', in: 1, out: 1.2, probability: 1}]}};
  assert.equal(VisualEngine.prototype.word.call(fake, 1.25, {metadata: {wordMode: 'cues'}}, .2), 'OUT');
  assert.equal(VisualEngine.prototype.word.call(fake, 1.8, {metadata: {wordMode: 'cues'}}, .2), '');
  const authored = {metadata: {wordMode: 'authored', words: 'HOW WHY WHAT'}};
  assert.equal(VisualEngine.prototype.word.call(fake, .1, authored, .2), 'HOW');
  assert.equal(VisualEngine.prototype.word.call(fake, .4, authored, .2), '');
});

test('named picture targets leave every pixel above, below and beside their rectangle untouched', () => {
  const width = 100, height = 80;
  function maskCanvas() {
    const pixels = new Uint8Array(width * height);
    const ctx = {
      setTransform() {}, clearRect() {pixels.fill(0);},
      fillRect(x, y, w, h) {
        for (let row = 0; row < height; row++) for (let col = 0; col < width; col++) {
          if (col >= x && col < x + w && row >= y && row < y + h) pixels[row * width + col] = 255;
        }
      },
    };
    return {width, height, pixels, getContext: () => ctx};
  }
  const engine = new VisualEngine({duration: 2, fps: 12}, {regions: {items: [{id: 'selected', bounds: [.2, .25, .4, .5]}]}}, {width, height, createCanvas: maskCanvas});
  const selected = engine.mask({id: 'region', targets: ['picture'], region: 'selected'}, 0);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    assert.equal(selected.pixels[y * width + x], x >= 20 && x < 60 && y >= 20 && y < 60 ? 255 : 0, `mask at ${x},${y}`);
  }
  const all = engine.mask({id: 'whole-frame', targets: ['picture'], region: 'all'}, 0);
  assert.ok(all.pixels.every(value => value === 255));
});
