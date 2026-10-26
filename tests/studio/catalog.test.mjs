import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeCatalog,availability,filterObjects,parseRoute,sourceMoment,toolForPath} from '../../web/studio/core.mjs';
const sha='a'.repeat(64),other='b'.repeat(64);
test('recorded performance is reachable through the existing compose workspace',()=>{
  assert.deepEqual(parseRoute('#compose/performance'),{mode:'compose',tool:'performance'});
  assert.equal(toolForPath('/studies/performance.html'),'performance');
});
const base={objects:[{sha256:sha,names:['original.mp4'],type:'video',links:[],decode:'passed'}],reproductions:[],retained_outputs:[],retained_inputs:[]};
test('every identity is retained once across addenda',()=>assert.equal(normalizeCatalog({...base,retained_outputs:[{sha256:sha,names:['alias.mp4'],links:[]}]}).length,1));
test('aliases are merged, never overwritten',()=>assert.deepEqual(normalizeCatalog({...base,retained_outputs:[{sha256:sha,names:['alias.mp4'],links:[]} ]})[0].names,['original.mp4','alias.mp4']));
test('private preservation is not playability',()=>assert.equal(availability({...base.objects[0],availability:'privately_preserved'}).key,'preserved'));
test('no link is not a broken play control',()=>assert.equal(availability(base.objects[0]).playable,false));
test('failed decode does not advertise playability',()=>assert.equal(availability({...base.objects[0],decode:'failed',links:[{href:'../media/x.mp4'}]}).playable,false));
test('font is retained as metadata but never a download',()=>assert.equal(availability({...base.objects[0],type:'font',names:['font.ttf'],links:[{href:'../font.ttf'}]}).playable,false));
test('source hashes remain searchable',()=>assert.equal(filterObjects(normalizeCatalog(base),sha,'all','all').length,1));
test('empty queries retain all records',()=>assert.equal(filterObjects(normalizeCatalog({...base,reproductions:[{sha256:other,names:['sound.wav'],type:'audio',links:[]}]}),'','all','all').length,2));
test('invalid route falls back to review',()=>assert.equal(parseRoute('#not-a-route').mode,'review'));
test('known tool is recovered from a deep link',()=>assert.deepEqual(parseRoute('#compose/fx'),{mode:'compose',tool:'fx'}));
test('arbitrary tool URLs are not accepted',()=>assert.equal(parseRoute('#compose/https://evil.test/').tool,null));
test('fixed excerpt time maps only inside its source interval',()=>assert.equal(sourceMoment('audio',2),87.133333333));
test('unmapped edited films have no source conversion',()=>assert.equal(sourceMoment('color',2),null));
test('non-finite media times have no source conversion',()=>assert.equal(sourceMoment('audio',Infinity),null));
test('negative source position is rejected',()=>assert.equal(sourceMoment('audio',-1),null));

test('retimed sourceMoment maps through piecewise linear span mapping', () => {
  const retimingMap = [
    { outputStart: 0, outputEnd: 20, sourceStart: 85.0, sourceEnd: 95.0 }
  ];
  // 2x slow-down: elapsed output of 10 maps to elapsed source of 5
  assert.equal(sourceMoment('audio', 10, retimingMap), 90.0);
  assert.equal(sourceMoment('audio', 0, retimingMap), 85.0);
  assert.equal(sourceMoment('audio', 20, retimingMap), 95.0);
  // Position outside span returns null
  assert.equal(sourceMoment('audio', 25, retimingMap), null);
});

test('retimed sourceMoment supports multi-span piecewise linear mapping with varying rates', () => {
  const multiSpanMap = [
    { output_start: 0, output_end: 10, source_start: 50.0, source_end: 70.0 },
    { output_start: 10, output_end: 30, source_start: 70.0, source_end: 80.0 }
  ];
  // Span 1 midpoint: 5s output -> 60s source
  assert.equal(sourceMoment('fx', 5, multiSpanMap), 60.0);
  // Span 2 midpoint: 20s output -> 75s source
  assert.equal(sourceMoment('fx', 20, multiSpanMap), 75.0);
});

test('retimed sourceMoment unwraps tool-keyed map objects and falls back when tool is unmapped', () => {
  const toolKeyedMap = {
    audio: [{ outputStart: 0, outputEnd: 10, sourceStart: 85.133333333, sourceEnd: 90.133333333 }],
    fx: [{ outputStart: 0, outputEnd: 5, sourceStart: 95.0, sourceEnd: 100.0 }]
  };
  assert.equal(sourceMoment('audio', 5, toolKeyedMap), 87.633333333);
  assert.equal(sourceMoment('fx', 2.5, toolKeyedMap), 97.5);
  // Unmapped tool in tool-keyed map falls back to null if no 1:1 fallback exists (or unmapped)
  assert.equal(sourceMoment('color', 2, toolKeyedMap), null);
});

test('invalid retiming map fails closed and returns null', () => {
  // Overlapping spans are invalid
  const overlapping = [
    { outputStart: 0, outputEnd: 15, sourceStart: 0, sourceEnd: 10 },
    { outputStart: 10, outputEnd: 25, sourceStart: 10, sourceEnd: 20 }
  ];
  assert.equal(sourceMoment('audio', 5, overlapping), null);

  // Non-finite times are invalid
  const nonFinite = [{ outputStart: 0, outputEnd: NaN, sourceStart: 0, sourceEnd: 10 }];
  assert.equal(sourceMoment('audio', 5, nonFinite), null);
});

test('fallback to 1:1 elapsed time when retiming map is null or undefined', () => {
  assert.equal(sourceMoment('audio', 2, null), 87.133333333);
  assert.equal(sourceMoment('audio', 2, undefined), 87.133333333);
  assert.equal(sourceMoment('fx', 2), 97);
  assert.equal(sourceMoment('experience', 50), 50);
});
test('previous root experience remains discoverable',()=>assert.equal(toolForPath('/experience.html'),'experience'));
test('URLs cannot sneak into the tool list',()=>assert.equal(toolForPath('https://evil.test/review.html'),null));

test('both recovered direction editors remain available in Compose',()=>{assert.deepEqual(parseRoute('#compose/direction'),{mode:'compose',tool:'direction'});assert.deepEqual(parseRoute('#compose/directed'),{mode:'compose',tool:'directed'});assert.equal(toolForPath('/direction-review.html'),'direction');assert.equal(toolForPath('/directed-review.html'),'directed');});
