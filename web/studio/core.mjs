/** Pure navigation and inventory rules. Availability is not artistic acceptance. */
export const TOOLS = Object.freeze({
  review:{mode:'review',title:'Source review',path:'/review-workbench/index.html',description:'Film, sound, 174 source records and your time/region-linked directions.'},
  audio:{mode:'compare',title:'Dialogue & sound',path:'/review.html',description:'Five aligned picture versions, four blind speech trials, room and foley.'},
  color:{mode:'compare',title:'Color & detail',path:'/color-studies/',description:'Full-frame source/color comparisons and photographic reference studies.'},
  'fx-films':{mode:'compare',title:'FX demonstrations',path:'/fx/watch.html',description:'13 processors and six patches, in landscape and portrait.'},
  layouts:{mode:'compare',title:'Eight compositions',path:'/studio/layouts.html',description:'Recovered six-second spatial studies in both orientations.'},
  room:{mode:'compose',title:'Room-tone rack',path:'/room-tone/',description:'Existing sound beds, stretched layers, combinations and listening notes.'},
  fx:{mode:'compose',title:'Audiovisual FX',path:'/fx/',description:'Editable processors, signal routes, automation and saved patches.'},
  performance:{mode:'compose',title:'Recorded performance',path:'/studies/performance.html',description:'Play and recover saved multiscale performances from qualified prepared media.'},
  direction:{mode:'compose',title:'Direction recipe',path:'/direction-review.html',description:'Editable direction recipes, proof variants and source/output timing. Media availability is checked on load.'},
  directed:{mode:'compose',title:'Directed comparisons',path:'/directed-review.html',description:'Reference and directed treatments with time-linked review notes. Unavailable renders retain an explicit recovery state.'},
  experience:{mode:'compose',title:'Five realities',path:'/experience.html',description:'The original interactive room; attention, residue and source playback.'},
  'study-03':{mode:'compose',title:'Independent time · 03',path:'/studies/study-03.html',description:'Recovered player with independent voice, body, word and room clocks.'},
  'study-04':{mode:'compose',title:'Independent time · 04',path:'/studies/study-04.html',description:'Recovered neural repair, role assignments and audience choices.'},
  evaluation:{mode:'compose',title:'Evaluation · Study 05',path:'/evaluation/index.html',description:'Recovered saved version: phrase review, audience choices and device checks.'},
  layers:{mode:'compose',title:'Actor & object layers',path:'/studies/layers.html',description:'Recovered layer-study compositor with independently timed actors and objects.'},
  recovery:{mode:'project',title:'Original recovery register',path:'/recovery/',description:'Detailed preserved manifests and historical dependencies.'}
});
const MODES=new Set(['review','compare','compose','library','project']);
export function parseRoute(hash){const [part,tool]=String(hash||'').replace(/^#/,'').split('/');const mode=MODES.has(part)?part:'review';return {mode,tool:TOOLS[tool]?.mode===mode?tool:null};}
export function toolForPath(path){if(typeof path!=='string'||!path.startsWith('/')||path.startsWith('//'))return null;const clean=path.split('?')[0].split('#')[0];return Object.entries(TOOLS).find(([,t])=>t.path===clean)?.[0]||null;}
export function validateSourceOutputMap(map){
  if(!map)return null;
  const items=Array.isArray(map)?map:(Array.isArray(map.spans)?map.spans:(Array.isArray(map.points)?map.points:null));
  if(!items||items.length===0)return null;
  const isSpan=items.every(item=>{
    if(!item||typeof item!=='object')return false;
    const os=item.outputStart??item.output_start;
    const oe=item.outputEnd??item.output_end;
    const ss=item.sourceStart??item.source_start;
    const se=item.sourceEnd??item.source_end;
    return Number.isFinite(os)&&Number.isFinite(oe)&&Number.isFinite(ss)&&Number.isFinite(se)&&os>=0&&oe>os&&ss>=0&&se>=0;
  });
  if(isSpan){
    const spans=items.map(item=>({
      outputStart:item.outputStart??item.output_start,
      outputEnd:item.outputEnd??item.output_end,
      sourceStart:item.sourceStart??item.source_start,
      sourceEnd:item.sourceEnd??item.source_end,
    })).sort((a,b)=>a.outputStart-b.outputStart);
    for(let i=0;i<spans.length-1;i++){
      if(spans[i].outputEnd>spans[i+1].outputStart)return null;
    }
    return {type:'spans',spans};
  }
  const isPoint=items.every(item=>{
    if(Array.isArray(item))return item.length>=2&&Number.isFinite(item[0])&&Number.isFinite(item[1])&&item[0]>=0&&item[1]>=0;
    if(item&&typeof item==='object'){
      const o=item.output??item.outputTime??item.output_time;
      const s=item.source??item.sourceTime??item.source_time;
      return Number.isFinite(o)&&Number.isFinite(s)&&o>=0&&s>=0;
    }
    return false;
  });
  if(isPoint){
    const points=items.map(item=>{
      if(Array.isArray(item))return {output:item[0],source:item[1]};
      return {
        output:item.output??item.outputTime??item.output_time,
        source:item.source??item.sourceTime??item.source_time,
      };
    }).sort((a,b)=>a.output-b.output);
    for(let i=0;i<points.length-1;i++){
      if(points[i].output>=points[i+1].output)return null;
    }
    return {type:'points',points};
  }
  return null;
}

export function interpolateSourceMoment(position,validatedMap){
  if(validatedMap.type==='spans'){
    const span=validatedMap.spans.find(s=>position>=s.outputStart-1e-9&&position<=s.outputEnd+1e-9);
    if(!span)return null;
    const clamped=Math.max(span.outputStart,Math.min(span.outputEnd,position));
    const fraction=(clamped-span.outputStart)/(span.outputEnd-span.outputStart);
    return span.sourceStart+fraction*(span.sourceEnd-span.sourceStart);
  }
  if(validatedMap.type==='points'){
    const pts=validatedMap.points;
    if(position<pts[0].output-1e-9||position>pts[pts.length-1].output+1e-9)return null;
    for(let i=0;i<pts.length-1;i++){
      if(position>=pts[i].output-1e-9&&position<=pts[i+1].output+1e-9){
        const clamped=Math.max(pts[i].output,Math.min(pts[i+1].output,position));
        const fraction=(clamped-pts[i].output)/(pts[i+1].output-pts[i].output);
        return pts[i].source+fraction*(pts[i+1].source-pts[i].source);
      }
    }
  }
  return null;
}

export function sourceMoment(tool,position,sourceOutputMap){
  if(!Number.isFinite(position)||position<0)return null;
  if(sourceOutputMap!==undefined&&sourceOutputMap!==null){
    let mapForTool=sourceOutputMap;
    if(typeof sourceOutputMap==='object'&&!Array.isArray(sourceOutputMap)&&!(sourceOutputMap.spans||sourceOutputMap.points)){
      mapForTool=sourceOutputMap[tool]??null;
    }
    if(mapForTool!==null&&mapForTool!==undefined){
      const validated=validateSourceOutputMap(mapForTool);
      if(validated)return interpolateSourceMoment(position,validated);
      return null;
    }
  }
  if(tool==='audio')return position<=22.033333334?85.133333333+position:null;
  if(tool==='experience'||tool==='review')return position<=112?position:null;
  if(tool==='fx')return position<=12.166666667?95+position:null;
  return null;
}
const FONT=/\.(ttf|otf|woff2?)(?:$|[?#])/i;
export function mediaLink(object){if(object.type==='font'||object.names?.some(n=>FONT.test(n)))return null;for(const l of object.links||[]){const href=typeof l==='string'?l:l?.href;if(typeof href!=='string'||/^(?:javascript|data|file):/i.test(href))continue;try{const u=new URL(href,'https://god-here-five-realities.ajpadavano.chatgpt.site/recovery/');if(u.origin!=='https://god-here-five-realities.ajpadavano.chatgpt.site'||FONT.test(u.pathname))continue;return u.pathname+u.search+u.hash;}catch{}}return null;}
export function availability(object){const href=mediaLink(object);if(object.decode==='failed')return {key:'failed',label:'Preserved · decode failed',playable:false,href:null};if(object.type==='font'||object.names?.some(n=>FONT.test(n)))return {key:'recorded',label:'Dependency record only',playable:false,href:null};if(href)return {key:'available',label:'Available on site',playable:['video','audio','image'].includes(object.type),href};if(object.availability==='privately_preserved')return {key:'preserved',label:'Privately preserved',playable:false,href:null};return {key:'recorded',label:'Registered · not mounted',playable:false,href:null};}
export function normalizeCatalog(catalog){const all=new Map();for(const group of ['objects','reproductions','retained_outputs','retained_inputs'])for(const o of catalog[group]||[]){if(!/^[a-f0-9]{64}$/.test(o.sha256||''))throw Error('Invalid artifact identity');if(!all.has(o.sha256))all.set(o.sha256,{...o,names:[...(o.names||[])],links:[...(o.links||[])]});else{const old=all.get(o.sha256);old.names=[...new Set([...old.names,...o.names||[]])];old.links=[...old.links,...o.links||[]];}}return [...all.values()];}
export function filterObjects(objects,q='',type='all',status='all'){const s=q.toLowerCase().trim();return objects.filter(o=>(!s||[o.sha256,...o.names].join(' ').toLowerCase().includes(s))&&(type==='all'||o.type===type)&&(status==='all'||availability(o).key===status));}
