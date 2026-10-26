/** Read-only native Canvas check; expected layout reuses the retained renderer. */
import fs from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import {RuntimeSupervisor,referenceGeometry} from '../web/studies/performance-adapter.mjs';
const require=createRequire(import.meta.url);
let canvas;
try{canvas=require('@napi-rs/canvas');}catch(error){
  const modules=process.env.AMP_NODE_MODULES||process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES;
  if(!modules)throw error;canvas=createRequire(path.join(modules,'package.json'))('@napi-rs/canvas');
}
const {createCanvas,ImageData}=canvas;
const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const record=JSON.parse(fs.readFileSync(spec.performance_path,'utf8')),supervisor=new RuntimeSupervisor(record);
const source=spec.source,sourceFd=fs.openSync(source.path,'r'),sourceBytes=source.width*source.height*4,sourceBuffer=Buffer.alloc(sourceBytes);
const picture=createCanvas(source.width,source.height),pc=picture.getContext('2d');
const sourceFrames=[],views=[];let total=0,maximum=0,meanMaximum=0;
function read(fd,buffer,position){if(fs.readSync(fd,buffer,0,buffer.length,position)!==buffer.length)throw Error('Incomplete decoded frame');}
try{
  for(const view of spec.views){
    const fd=fs.openSync(view.path,'r'),stride=view.width*view.height*4,actual=Buffer.alloc(stride);
    const expected=createCanvas(view.width,view.height),ec=expected.getContext('2d'),box=referenceGeometry(view.width,view.height,source.width/source.height);
    if(!Number.isInteger(box.reserved.y)||box.image.x<0||box.image.y<box.reserved.y||box.image.x+box.image.width>view.width+1e-8||box.image.y+box.image.height>view.height+1e-8||Math.abs(box.image.width/box.image.height-source.width/source.height)>1e-10)throw Error('Invalid full-frame geometry');
    const maxErrors=[],meanErrors=[];let viewMax=0,viewMean=0;
    try{for(let frame=0;frame<view.frames;frame++){
      // Read-only random access: no transition/history allocation or playback claim.
      supervisor.frame=supervisor.checkFrame(frame+view.start_frame);const position=supervisor.snapshot().reference.source_frame;
      if(!Number.isSafeInteger(position)||position<0||position>=source.frames)throw Error('Source frame outside original');
      if(views.length===0)sourceFrames.push(position);else if(sourceFrames[frame]!==position)throw Error('H/V decisions differ');
      read(sourceFd,sourceBuffer,position*sourceBytes);pc.putImageData(new ImageData(new Uint8ClampedArray(sourceBuffer),source.width,source.height),0,0);
      ec.setTransform(1,0,0,1,0,0);ec.globalAlpha=1;ec.globalCompositeOperation='source-over';ec.fillStyle='#000';ec.fillRect(0,0,view.width,view.height);
      ec.drawImage(picture,0,0,source.width,source.height,box.image.x,box.image.y,box.image.width,box.image.height);
      const truth=ec.getImageData(0,0,view.width,view.height).data;read(fd,actual,frame*stride);
      let max=0,sum=0,count=0;
      for(let y=box.reserved.y;y<view.height;y++)for(let x=0;x<view.width;x++){
        const at=(y*view.width+x)*4;if(actual[at+3]!==255)throw Error('Transparent protected pixel');
        for(let c=0;c<3;c++){const error=Math.abs(actual[at+c]-truth[at+c]);max=Math.max(max,error);sum+=error;count++;}
      }
      const mean=sum/count;maxErrors.push(max);meanErrors.push(mean);viewMax=Math.max(viewMax,max);viewMean=Math.max(viewMean,mean);total++;
    }}finally{fs.closeSync(fd);}
    maximum=Math.max(maximum,viewMax);meanMaximum=Math.max(meanMaximum,viewMean);
    views.push({orientation:view.orientation,frames:view.frames,dimensions:[view.width,view.height],geometry:box,max_channel_error:viewMax,max_mean_channel_error:viewMean,per_frame_max_error:maxErrors,per_frame_mean_error:meanErrors});
  }
  console.log(JSON.stringify({status:maximum<=spec.max_channel_error&&meanMaximum<=spec.mean_channel_error?'passed':'failed',checked_frames:total,source_frames:sourceFrames,views,max_channel_error:maximum,max_mean_channel_error:meanMaximum,tolerance:{max_channel_error:spec.max_channel_error,mean_channel_error:spec.mean_channel_error}}));
}finally{fs.closeSync(sourceFd);}
