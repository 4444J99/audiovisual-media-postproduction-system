/** Tiny synthetic source and actual retained-Canvas outputs; no production media. */
import fs from 'node:fs';
import path from 'node:path';
import {createCanvas,loadImage} from '@napi-rs/canvas';
import {PerformancePlayer} from '../../web/studies/performance-adapter.mjs';
const [mode,root,recordPath]=process.argv.slice(2);
if(mode==='source'){
  const atlas=createCanvas(128,18),ac=atlas.getContext('2d');
  for(let f=0;f<4;f++){
    const c=createCanvas(32,18),x=c.getContext('2d');x.fillStyle=['#438d32','#164fac','#b94516','#8d2389'][f];x.fillRect(0,0,32,18);
    x.fillStyle='#fff';x.fillRect(0,0,3,18);x.fillStyle='#000';x.fillRect(29,0,3,18);x.fillStyle='#f9e71b';x.fillRect(10+f,0,2,18);
    fs.writeFileSync(path.join(root,`source-${String(f).padStart(3,'0')}.png`),c.toBuffer('image/png'));ac.drawImage(c,f*32,0);
  }
  fs.writeFileSync(path.join(root,'atlas.png'),atlas.toBuffer('image/png'));
}else{
  const record=JSON.parse(fs.readFileSync(recordPath,'utf8')),picture=await loadImage(path.join(root,'atlas.png'));
  const matte=createCanvas(128,18),mc=matte.getContext('2d');mc.fillStyle='#fff';mc.fillRect(0,0,128,18);
  const m=record.runtime.materials[0],buffer={sampleRate:48000,length:96000,numberOfChannels:1,getChannelData:()=>new Float32Array(96000)};
  const prepared={materials:new Map([[m.id,{sha256:m.sha256,audioBuffer:buffer,
    media:{fps:2,duration:2,columns:4,framesPerPage:4,picture:{width:32,height:18},matte:{width:32,height:18}},assets:{picture:[picture],matte:[matte]}}]]),audioVariants:new Map()};
  const audio={currentTime:0,state:'suspended',destination:{}};
  for(const [orientation,w,h]of [['horizontal',97,55],['vertical',49,83]]){
    const canvas=createCanvas(w,h),player=new PerformancePlayer({record,prepared,canvas,audioContext:audio,createCanvas,autoTick:false});
    for(let f=0;f<record.runtime.duration_frames;f++){
      player.seek(f);fs.writeFileSync(path.join(root,`${orientation}-${String(f).padStart(3,'0')}.png`),canvas.toBuffer('image/png'));
    }
  }
}
