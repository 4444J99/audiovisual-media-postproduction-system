import {evaluatedNode} from './core.mjs';
import {stutterSourceTime, reverseSourceTime, freezeSourceTime} from './audio-engine.mjs';

const TAU = Math.PI * 2;
export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const mod = (x, n) => ((x % n) + n) % n;
const noise = (seed, i, j = 0) => {
  let n = (seed ^ Math.imul(i + 1, 374761393) ^ Math.imul(j + 1, 668265263)) >>> 0;
  n = Math.imul(n ^ n >>> 13, 1274126177); return ((n ^ n >>> 16) >>> 0) / 4294967296;
};

/** The same random-access, output-clock renderer runs in the browser and Node. */
export class VisualEngine {
  constructor(media, assets, options = {}) {
    this.media = media; this.assets = assets;
    this.width = options.width || 640; this.height = options.height || 360;
    this.createCanvas = options.createCanvas || ((w, h) => {const c = document.createElement('canvas'); c.width = w; c.height = h; return c;});
    this.regions = assets.regions?.items || [];
    this.cues = assets.cues || {words:[], phrases:[]};
    this.pool = []; this.poolIndex = 0; this.cache = new Map(); this.maskCache = new Map();
    this.temporalCache = new Map(); this.temporalCacheLimit = options.cacheFrames || 192;
    this.freeTemporal = []; this.retiredTemporal = [];
    this.control = options.control || (() => 0);
    this.controlLane = options.controlLane || null;
  }
  canvas(w = this.width, h = this.height) {
    const i = this.poolIndex++;
    let c = this.pool[i];
    if (!c || c.width !== w || c.height !== h) this.pool[i] = c = this.createCanvas(w, h);
    const ctx = c.getContext('2d'); ctx.setTransform(1,0,0,1,0,0); ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over'; ctx.clearRect(0,0,w,h); ctx.imageSmoothingEnabled = true;
    return c;
  }
  copy(input) {const c = this.canvas(); if (input) c.getContext('2d').drawImage(input,0,0,this.width,this.height); return c;}
  frame(t, matte = false) {
    const index = Math.floor(clamp(t, 0, this.media.duration - 1 / this.media.fps) * this.media.fps + 1e-6);
    const key = `${matte?'labels':'source'}:${index}`;
    if (this.cache.has(key)) return this.cache.get(key);
    const page = Math.floor(index / this.media.framesPerPage), cell = index % this.media.framesPerPage;
    const def = matte ? this.media.matte : this.media.picture;
    const image = (matte ? this.assets.matte : this.assets.picture)[page];
    const c = this.canvas(); const ctx = c.getContext('2d'); ctx.imageSmoothingEnabled = !matte;
    if (image) ctx.drawImage(image,(cell % this.media.columns) * def.width,Math.floor(cell / this.media.columns) * def.height,def.width,def.height,0,0,this.width,this.height);
    this.cache.set(key,c); return c;
  }
  word(t, patch = this.patch, persistence = Infinity) {
    if (patch?.metadata?.wordMode === 'authored') {
      const words = String(patch.metadata.words || 'HOW WHY WHAT').split(/\s+/).filter(Boolean);
      if(mod(Math.max(0,t),.7)>persistence)return '';
      return words[Math.floor(Math.max(0,t) / .7) % words.length] || 'HOW';
    }
    const words = this.cues.words || [];
    // Prefer the mutually supported OUT/HOW/WHAT anchors; disputed low-probability WHAT is excluded.
    const recent = words.filter(c => c.in <= t && (c.probability ?? 1) > .5).at(-1);
    return recent && t-(recent.out||recent.in)>persistence?'':recent?.text || 'OUT';
  }
  text(t, size = .75, color = '#f4faed', word = null) {
    const c = this.canvas(), ctx = c.getContext('2d');
    const value = word===null?this.word(t):word; const W = this.width, H = this.height;
    if(!value)return c;
    ctx.font = `900 ${Math.round(H * size)}px Arial, sans-serif`;
    const width = ctx.measureText(value).width;
    ctx.save(); ctx.translate(W / 2, H / 2); ctx.scale(Math.min(1, W * .96 / Math.max(1,width)),1);
    ctx.fillStyle = color; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(value,0,H * .035); ctx.restore();
    return c;
  }
  inputs(id, port) {return this.patch.connections.filter(e => e.to === id && e.port === port);}
  branchDescriptor(id, visited = new Set()) {
    if(visited.has(id))return null;visited.add(id);const node=this.nodeMap.get(id);
    if(node&&!['source','output','mix'].includes(node.type))return node;
    const incoming=this.inputs(id,'picture');return incoming.length===1?this.branchDescriptor(incoming[0].from,visited):null;
  }
  input(node, port, t, materialize = false) {
    const edges = this.inputs(node.id,port);
    if (!edges.length) return {image:this.canvas(),active:false};
    if (edges.length === 1 && (edges[0].gain ?? 1) === 1 && !(port==='picture'&&edges[0].role==='return')) return this.signal(edges[0].from,port,t,materialize);
    const image = this.canvas(), ctx = image.getContext('2d'); let active = false;
    if(port !== 'text') {ctx.fillStyle = '#000'; ctx.fillRect(0,0,this.width,this.height);}
    // Additive premultiplied mixing matches an explicit weighted parallel bus.
    ctx.globalCompositeOperation = 'lighter';
    for (const edge of edges) {
      const input = this.signal(edge.from,port,t,materialize);
      if (port === 'text' && !input.active) continue;
      let image=input.image;
      const branch=port==='picture'&&edge.role==='return'?this.branchDescriptor(edge.from):null;
      const isolated=branch&&!branch.targets.includes('picture')&&branch.targets.some(t=>['body','objects'].includes(t)) || branch?.targets.includes('picture')&&branch.region!=='all';
      if(isolated){
        image=this.copy(image);const ic=image.getContext('2d');
        const labels=this.signal(edge.from,'matte',t).image;
        ic.globalCompositeOperation='destination-in';ic.drawImage(this.mask({...branch,id:branch.id+':return'},t,labels),0,0);
        ic.globalCompositeOperation='source-over';ctx.globalCompositeOperation='source-over';
      }else ctx.globalCompositeOperation='lighter';
      const amount=clamp(edge.gain ?? 1,0,4);
      if(port==='matte'){
        // Labels identify performers; adding or fading their numbers would invent identities.
        const labels=this.copy(image),lc=labels.getContext('2d'),data=lc.getImageData(0,0,this.width,this.height);
        for(let i=0;i<data.data.length;i+=4)data.data[i+3]=data.data[i]>20?255:0;
        lc.putImageData(data,0,0);ctx.globalCompositeOperation='source-over';ctx.globalAlpha=amount>0?1:0;ctx.drawImage(labels,0,0);
      }
      else if(isolated){ctx.globalAlpha=clamp(amount);ctx.drawImage(image,0,0);}
      else {for(let g=amount;g>0;g-=1){ctx.globalAlpha=Math.min(1,g);ctx.drawImage(image,0,0);}}
      active ||= input.active;
    }
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    return {image,active};
  }
  envelope(id,t,visited = new Set()) {
    if(visited.has(id)) return 0; visited.add(id);
    const node = this.nodeMap.get(id);
    if(node?.type === 'source') return this.control(clamp(t,0,this.media.duration),'source');
    const edges=this.inputs(id,'control');
    return clamp(edges.reduce((sum,e)=>sum + (this.controlLane?.(e.from,t) ?? this.envelope(e.from,t,new Set(visited))) * (e.gain ?? 1),0));
  }
  mask(node,t, labels) {
    const W = this.width,H = this.height;
    const key = `${node.id}:${Math.floor(t*this.media.fps+1e-6)}:${node.targets.join(',')}:${node.region}`;
    if(this.maskCache.has(key)) return this.maskCache.get(key);
    const c = this.canvas(),ctx = c.getContext('2d');
    if(node.targets.includes('picture')) {
      ctx.fillStyle = '#fff';
      const r = this.regionBounds(node.region);
      if(node.region === 'all' || !r) ctx.fillRect(0,0,W,H);
      else ctx.fillRect(r[0]*W,0,r[2]*W,H);
    } else if (node.targets.includes('objects')) {
      const r = node.objectRect || this.regions.find(r=>r.id === node.region)?.bounds || [.6,.62,.1,.18];
      ctx.fillStyle='#fff';ctx.fillRect(r[0]*W,r[1]*H,r[2]*W,r[3]*H);
    }
    if (!node.targets.includes('picture') && (node.targets.includes('room') || node.targets.includes('body'))) {
      const small = this.canvas(320,180),sc=small.getContext('2d'); sc.imageSmoothingEnabled=false;sc.drawImage(labels||this.frame(t,true),0,0,320,180);
      const pixels = sc.getImageData(0,0,320,180); const label = this.regions.find(r=>r.id===node.region)?.labelValue;
      for(let i=0;i<pixels.data.length;i+=4) {
        const v=pixels.data[i]; const body=v>20 && (node.region === 'all' || !label || Math.abs(v-label)<17);
        const room=v<20; const alpha=(node.targets.includes('body')&&body || node.targets.includes('room')&&room)?255:0;
        pixels.data[i]=pixels.data[i+1]=pixels.data[i+2]=255;pixels.data[i+3]=alpha;
      }
      sc.putImageData(pixels,0,0); ctx.drawImage(small,0,0,W,H);
    }
    this.maskCache.set(key,c); return c;
  }
  regionBounds(id) {
    return this.regions.find(r=>r.id===id)?.bounds || null;
  }
  isolate(image,node,t) {
    if(node.targets.includes('picture')&&node.region==='all')return image;
    const out=this.copy(image),ctx=out.getContext('2d');
    const labels=node.targets.some(s=>['body','room'].includes(s))?this.input(node,'matte',t).image:null;
    ctx.globalCompositeOperation='destination-in';ctx.drawImage(this.mask(node,t,labels),0,0);ctx.globalCompositeOperation='source-over';return out;
  }
  signal(id, port, t, materialize = false) {
    t=Math.floor(clamp(t,0,this.media.duration-1e-6)*this.media.fps+1e-6)/this.media.fps;
    const cacheKey=`${id}|${port}|${Math.round(t*120)}|${materialize}`;
    if(this.cache.has(cacheKey))return this.cache.get(cacheKey);
    if(this.temporalCache.has(cacheKey)){
      const saved=this.temporalCache.get(cacheKey);this.temporalCache.delete(cacheKey);this.temporalCache.set(cacheKey,saved);return saved;
    }
    const node=this.nodeMap.get(id);
    if(!node) return {image:this.canvas(),active:false};
    let result;
    if(node.type==='source') {
      result={image:port==='text'?(materialize?this.text(t):this.canvas()):this.frame(t,port==='matte'),active:port!=='text'||materialize};
      if((node.gain??1)!==1&&port!=='matte'){
        const image=this.canvas(),ctx=image.getContext('2d');ctx.globalCompositeOperation='lighter';
        for(let g=clamp(node.gain??1,0,4);g>0;g-=1){ctx.globalAlpha=Math.min(1,g);ctx.drawImage(result.image,0,0);}
        result={image,active:result.active};
      }
    }
    else if(node.type==='mix'||node.type==='output') {
      result=this.input(node,port,t,materialize);
      if((node.gain??1)!==1&&port!=='matte'){
        const image=this.canvas(),ctx=image.getContext('2d');ctx.globalCompositeOperation='lighter';
        for(let g=clamp(node.gain??1,0,4);g>0;g-=1){ctx.globalAlpha=Math.min(1,g);ctx.drawImage(result.image,0,0);}
        result={image,active:result.active};
      }
    }
    else {
      const n=evaluatedNode(node,t,this.patch,this.envelope(id,t));
      const eligible=port==='text'?n.targets.includes('text'):port==='matte'?n.targets.some(s=>['body','picture','objects'].includes(s))&&!['damage','typography'].includes(n.type):n.targets.some(s=>['picture','body','room','objects'].includes(s));
      const clipOn=n.scope?.type!=='clip'||t>=n.scope.start&&t<n.scope.end;
      if(this.bypass || n.bypass || !eligible || !clipOn || n.wet<=0) result=this.input(node,port,t,materialize);
      else {
        const dry=this.input(node,port,t,materialize);
        const sample=(s)=> {
          const image=this.input(node,port,clamp(s,0,this.media.duration-1e-6),port==='text').image;
          return port==='picture'||port==='matte'?this.isolate(image,n,s):image;
        };
        const processed=this.effect(n,t,port,sample);
        let wet=processed;
        if((port==='picture'||port==='matte') && n.type!=='typography' && !(n.targets.includes('picture')&&n.region==='all')) {
          wet=this.copy(dry.image);const wc=wet.getContext('2d');
          const labels=n.targets.some(s=>['body','room'].includes(s))?this.input(node,'matte',t).image:null;
          const mask=this.mask(n,t,labels);
          // A qualified hybrid plate fills erased/moved body pixels. It never claims recovered footage.
          const fill=this.canvas(); const fc=fill.getContext('2d');
          const usePlate=port==='picture'&&(n.targets.includes('body')||n.targets.includes('objects'));
          if(usePlate&&this.assets.room) fc.drawImage(this.assets.room,0,0,this.width,this.height);
          else {fc.fillStyle='#080a0d';fc.fillRect(0,0,this.width,this.height);}
          fc.globalCompositeOperation='destination-in';fc.drawImage(mask,0,0);wc.drawImage(fill,0,0);
          if(!n.params.spill && ['displacement'].includes(n.type)){const pc=processed.getContext('2d');pc.globalCompositeOperation='destination-in';pc.drawImage(mask,0,0);pc.globalCompositeOperation='source-over';}
          wc.drawImage(processed,0,0);
        }
        if(port==='picture' && n.type==='typography') {
          if(Math.round(n.params.mode)===1) wet=processed;
          else {wet=this.copy(dry.image);wet.getContext('2d').drawImage(processed,0,0);}
        }
        const image=this.canvas(),ctx=image.getContext('2d');
        if(port==='matte')ctx.drawImage(n.wet<.5?dry.image:wet,0,0);
        else {if(n.wet<1) {ctx.globalAlpha=1-n.wet;ctx.drawImage(dry.image,0,0);ctx.globalCompositeOperation='lighter';}
          ctx.globalAlpha=n.wet;ctx.drawImage(wet,0,0);}
        ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';
        result={image,active:port!=='text'||true};
      }
    }
    this.cache.set(cacheKey,result);
    if(!['source','output','mix'].includes(node.type)) {
      const savedImage=this.freeTemporal.pop()||this.createCanvas(this.width,this.height);const sc=savedImage.getContext('2d');sc.clearRect(0,0,this.width,this.height);sc.drawImage(result.image,0,0);
      this.temporalCache.set(cacheKey,{image:savedImage,active:result.active});
      if(this.temporalCache.size>this.temporalCacheLimit){const oldest=this.temporalCache.keys().next().value;this.retiredTemporal.push(this.temporalCache.get(oldest).image);this.temporalCache.delete(oldest);}
    }
    return result;
  }
  effect(n,t,port,sample) {
    const p=n.params,W=this.width,H=this.height,seed=(this.patch.seed||1)+[...n.id].reduce((a,c)=>a+c.charCodeAt(0),0);
    const c=this.canvas(),ctx=c.getContext('2d');ctx.imageSmoothingEnabled=port!=='matte'; const frame=()=>sample(t);
    switch(n.type) {
      case 'routing': {
        const phase=mod(t/Math.max(.08,p.travel),2);const progress=phase<1?phase:2-phase;
        const x=(p.origin+(p.destination-p.origin)*progress)*W;
        const count=Math.round(p.copies);
        for(let k=count-1;k>=0;k--) {
          const q=clamp(progress-k*.12*p.spread);ctx.globalAlpha=port==='matte'?1:(1-k/(count+1))*.95;
          const pos=(p.origin+(p.destination-p.origin)*q)*W;
          const src=sample(t-k*.085);const s=port==='text'?1:.62;
          ctx.drawImage(src,pos-W*s/2,H*(.5-s/2)+Math.sin(q*Math.PI)*-H*.3,W*s,H*s);
        }
        if(port==='text'&&progress>.92){ctx.fillStyle='#ff5b46';for(let k=0;k<10;k++){const a=noise(seed,k)*TAU;const d=(progress-.9)*W*6*p.arrival;ctx.fillRect(x+Math.cos(a)*d,H*.5+Math.sin(a)*d,8,8);}}
        break;
      }
      case 'delay': {
        const taps=Math.round(p.taps),s=p.scale;
        for(let k=taps;k>0;k--) {if(t-k*p.time<0)continue;ctx.globalAlpha=port==='matte'?1:Math.pow(p.decay,k)*.92;
          const x=(k%2?1:-1)*W*p.spread*.18*k/taps;const y=(k/taps-.5)*H*p.spread*.35;
          ctx.drawImage(sample(t-k*p.time),W*(1-s)/2+x,H*(1-s)/2+y,W*s,H*s);
        }break;
      }
      case 'stutter': {
        const period=p.window/Math.max(.25,p.rate)+p.gap; const elapsed=t-p.capture;
        const active=elapsed>=0&&elapsed<period*Math.round(p.repeats);
        const phase=mod(elapsed,period);
        const st=stutterSourceTime(t,p);
        if(st!==null)ctx.drawImage(sample(st),0,0);
        if(active&&port==='text'){ctx.globalCompositeOperation='source-atop';ctx.fillStyle=Math.floor(elapsed/period)%2?'#ff6396':'#ffffff';ctx.fillRect(0,0,W,H);}
        break;
      }
      case 'granular': {
        const cols=Math.round(p.tiles),rows=Math.max(2,Math.round(cols*H/W)),cw=W/cols,ch=H/rows;
        const grain=Math.floor(t/Math.max(.015,p.size));
        // Finite temporal bins bound upstream evaluations, independent of tile count.
        const bins=Array.from({length:5},(_,k)=>sample(t+(noise(seed,grain,k)-.5)*2*p.scatter));
        for(let y=0;y<rows;y++)for(let x=0;x<cols;x++){
          const i=y*cols+x;const shuffled=Math.round(p.order)!==0;const r=noise(seed,i,grain);
          const dx=(noise(seed,i,grain+9)-.5)*W*p.spatial,dy=(noise(seed,i,grain+21)-.5)*H*p.spatial;
          const sx=shuffled?Math.floor(noise(seed,i,3)*cols)*cw:x*cw;const sy=shuffled?Math.floor(noise(seed,i,5)*rows)*ch:y*ch;
          ctx.save();ctx.translate(x*cw+cw/2+dx,y*ch+ch/2+dy);ctx.rotate((r-.5)*p.spatial*1.2);
          ctx.drawImage(bins[i%bins.length],sx,sy,cw,ch,-cw/2,-ch/2,cw*1.12,ch*1.12);ctx.restore();
        }break;
      }
      case 'reverse': {
        if(Math.round(p.mode)===1){const f=mod(t*p.speed,Math.max(.15,p.span))/p.span;ctx.drawImage(frame(),(1-2*f)*W*.75,0);}
        else {ctx.drawImage(sample(reverseSourceTime(t,p,this.media.duration)),0,0);}
        break;
      }
      case 'freeze': {
        const active=t>=p.capture&&t<p.capture+p.duration,st=freezeSourceTime(t,p);
        ctx.globalAlpha=active&&port!=='matte'?Math.max(.2,1-p.decay*(t-p.capture)/p.duration):1;
        const dx=active?Math.sin(t*7)*W*p.motion:0;ctx.drawImage(sample(st),dx,0);break;
      }
      case 'feedback': {
        const reset=t>=p.reset?p.reset:0;
        ctx.drawImage(frame(),0,0);
        const passes=Math.min(Math.round(p.repeats),Math.floor((t-reset)/p.time));
        for(let k=1;k<=passes;k++) {
          const gain=p.gain**k;if(gain<p.threshold)break;
          const scale=p.scale**k;ctx.save();ctx.translate(W/2,H/2);ctx.rotate(p.rotation*TAU*k);ctx.scale(scale,scale);
          ctx.globalAlpha=port==='matte'?1:gain;ctx.drawImage(sample(t-k*p.time),-W/2,-H/2);ctx.restore();
        }break;
      }
      case 'queue': {
        const period=Math.max(.4,p.burst),phase=mod(t,period),cycleStart=t-phase;
        const arrivals=Math.floor(phase*p.rate);const released=Math.floor(phase*p.release*.2);
        const backlog=Math.max(0,arrivals-released);const count=Math.min(Math.round(p.capacity),backlog);
        const overflow=backlog>p.capacity;const entries=[];
        for(let k=0;k<count;k++)entries.push(cycleStart+(released+k)/Math.max(.25,p.rate));
        if(Math.round(p.order))entries.reverse();
        for(let k=0;k<entries.length;k++) {
          const src=sample(entries[k]);const s=port==='text'?.65:.48;
          const burst=overflow?(phase/period)*p.spread:0;
          const x=W*.08+k*W*.025+burst*(noise(seed,k,Math.floor(t/period))-.5)*W;
          const y=H*.15+k*H*.055+burst*(noise(seed,k,5)-.5)*H;
          ctx.save();ctx.translate(x,y);ctx.rotate(overflow?(noise(seed,k)-.5)*.8:0);ctx.drawImage(src,0,0,W*s,H*s);ctx.restore();
        }
        if(!count)ctx.drawImage(frame(),0,0);break;
      }
      case 'gate': {
        const phase=mod(t/p.period+p.phase,1);const open=Math.round(p.detector||0)===1?this.envelope(n.id,t)>=p.threshold:phase<p.duty;
        ctx.globalAlpha=open?1:(port==='matte'?0:p.retain);ctx.drawImage(frame(),0,0);break;
      }
      case 'displacement': {
        const src=frame(),strips=48; const amount=p.amount*.32;
        if(Math.round(p.direction)===1){for(let x=0;x<W;x+=W/strips){const f=x/W;const d=Math.sin(f*TAU*p.scale+t*p.speed)*H*amount;ctx.drawImage(src,x,0,W/strips+1,H,x,d,W/strips+1,H);ctx.drawImage(src,x,0,W/strips+1,H,x,d-Math.sign(d)*H,W/strips+1,H);}}
        else if(Math.round(p.direction)===2){for(let k=0;k<12;k++){ctx.save();const s=1-k*.055;ctx.translate(W/2,H/2);ctx.rotate(Math.sin(t*p.speed+k*.3)*amount);ctx.scale(s,s);ctx.globalAlpha=port==='matte'?1:.7;ctx.drawImage(src,-W/2,-H/2);ctx.restore();}}
        else {for(let y=0;y<H;y+=H/strips){const f=y/H;const d=Math.sin(f*TAU*p.scale+t*p.speed)*W*amount;ctx.drawImage(src,0,y,W,H/strips+1,d,y,W,H/strips+1);ctx.drawImage(src,0,y,W,H/strips+1,d-Math.sign(d)*W,y,W,H/strips+1);}}break;
      }
      case 'exchange': {
        if(Math.round(p.mode)===1){ctx.drawImage(frame(),0,0);break;}
        const people=this.regions.filter(r=>r.labelValue).sort((a,b)=>a.bounds[0]-b.bounds[0]);const count=people.length||5;
        const offset=mod(Math.floor(t/p.interval)*Math.round(p.offset)+1,count);
        const src=sample(Math.max(0,t-p.timeOffset));
        for(let k=0;k<count;k++){
          const destination=mod(k+offset,count);const sx=k*W/count,dx=destination*W/count;
          ctx.drawImage(src,sx,0,W/count,H,dx,0,W/count,H);
        }break;
      }
      case 'typography': {
        if(port==='matte'){ctx.drawImage(frame(),0,0);break;}
        const mode=Math.round(p.mode),word=this.word(t,this.patch,p.persistence), size=p.size;
        if(mode===1){ctx.fillStyle='#060708';ctx.fillRect(0,0,W,H);const aperture=this.text(t,size,'white',word);const ac=aperture.getContext('2d');ac.globalCompositeOperation='source-in';ac.drawImage(this.input(n,'picture',t).image,0,0);ctx.drawImage(aperture,0,0);}
        else if(mode===2){const cols=3,rows=Math.max(2,Math.ceil(p.copies/cols));ctx.fillStyle='#dbfb65';ctx.font=`900 ${H/rows*.9}px Arial`;ctx.textBaseline='middle';for(let i=0;i<p.copies;i++)ctx.fillText(this.word(Math.max(0,t-i*.32),this.patch,p.persistence),i%cols*W/cols-10,Math.floor(i/cols)*H/rows+H/(rows*2),W/cols*1.1);}
        else {
          const img=this.text(t,size,'#dbfb65',word);const copies=Math.min(32,Math.round(p.copies));
          for(let k=copies-1;k>=0;k--){ctx.globalAlpha=k===0?1:.18;ctx.drawImage(img,(k?Math.sin(t*p.drift+k)*W*.16:0),(k?Math.cos(t*p.drift+k)*H*.18:0));}
          if(p.fragment>.3){ctx.globalAlpha=1;const h=H/12;for(let k=0;k<12;k++){const dx=Math.sin(k*4+Math.floor(t*5))*p.fragment*W*.045;ctx.drawImage(img,0,k*h,W,h,dx,k*h,W,h);}}
        }break;
      }
      case 'damage': {
        const cols=Math.max(3,Math.round(1/p.block)),rows=Math.max(2,Math.round(cols*H/W));
        const small=this.canvas(cols,rows),sc=small.getContext('2d');sc.drawImage(frame(),0,0,cols,rows);
        const data=sc.getImageData(0,0,cols,rows);const levels=Math.round(p.levels)-1;
        for(let i=0;i<data.data.length;i+=4){const v=(data.data[i]+data.data[i+1]+data.data[i+2])/765;const q=Math.round(clamp((v-.5)*p.drive+.5)*levels)/levels;data.data[i]=q*216;data.data[i+1]=q*242;data.data[i+2]=q*255;}
        sc.putImageData(data,0,0);ctx.imageSmoothingEnabled=false;ctx.drawImage(small,0,0,W,H);break;
      }
      default:ctx.drawImage(frame(),0,0);
    }
    ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';return c;
  }
  renderLayers(patch,t,options={}) {
    this.freeTemporal.push(...this.retiredTemporal);this.retiredTemporal=[];
    const signature=JSON.stringify(patch)+Boolean(options.bypass);
    if(signature!==this.cacheSignature){for(const entry of this.temporalCache.values())this.freeTemporal.push(entry.image);this.temporalCache.clear();this.cacheSignature=signature;}
    this.patch=patch;this.nodeMap=new Map(patch.nodes.map(n=>[n.id,n]));this.bypass=options.bypass||false;
    this.solo=patch.nodes.some(n=>n.solo);this.poolIndex=0;this.cache.clear();this.maskCache.clear();
    const phase=patch.metadata?.demoPhases?.find(p=>t>=p.start&&t<p.end);
    if(options.bypass||phase?.name==='bypass')return {picture:this.frame(t),text:this.canvas(),textActive:false};
    const output=patch.nodes.find(n=>n.type==='output');
    if(!output)throw Error('Patch has no output');
    const picture=this.signal(output.id,'picture',t).image;const text=this.signal(output.id,'text',t);
    return {picture,text:text.image,textActive:text.active};
  }
  render(patch,t,options={}) {
    const layers=this.renderLayers(patch,t,options),out=this.copy(layers.picture);
    if(layers.textActive)out.getContext('2d').drawImage(layers.text,0,0);return out;
  }
}

export function paintViewport(canvas,layers,mode='auto') {
  const ctx=canvas.getContext('2d'),W=canvas.width,H=canvas.height;ctx.clearRect(0,0,W,H);
  const src=layers.picture;const portrait=mode==='stack'||mode==='auto'&&W/H<.9;
  if(portrait){
    const band=H/3;for(let i=0;i<3;i++){
      const wanted=W/band;const cropWidth=Math.min(src.width,src.height*wanted),cropHeight=Math.min(src.height,src.width/wanted);
      const x=(src.width-cropWidth)*(i/2),y=(src.height-cropHeight)/2;
      ctx.drawImage(src,x,y,cropWidth,cropHeight,0,i*band,W,band+1);
    }
  }else{
    const wanted=W/H;let sw=src.width,sh=src.height;if(sw/sh>wanted)sw=sh*wanted;else sh=sw/wanted;
    ctx.drawImage(src,(src.width-sw)/2,(src.height-sh)/2,sw,sh,0,0,W,H);
  }
  if(layers.textActive)ctx.drawImage(layers.text,0,0,W,H);
}
