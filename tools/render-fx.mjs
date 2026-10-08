#!/usr/bin/env node
/**
 * Offline rendering of the exact workbench graph. Requires Node >= 20,
 * @napi-rs/canvas, and ffmpeg/ffprobe on PATH. No browser or synthetic source.
 *
 * node render-fx.mjs --engine-dir web/fx --assets-dir web/fx/assets \
 *   --patch saved-patch.json --output preview.mp4 [--duration 12.166666667]
 *   [--width 480 --height 270 --fps 12 --chunk-frames 6]
 *   [--overlay none|phase|title-phase --title "Routing"] [--keep-wav]
 *   [--portrait-output portrait.mp4 --portrait-width 270 --portrait-height 480]
 *
 * Rendering is deterministic in output time. Short isolated frame workers bound
 * native canvas memory without changing the graph or restarting the encoder.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {performance} from 'node:perf_hooks';

const self=fileURLToPath(import.meta.url);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const json=async filename=>JSON.parse(await fs.readFile(filename,'utf8'));
const writeJson=(filename,value)=>fs.writeFile(filename,JSON.stringify(value,null,2)+'\n');
function args(argv) {
  const output={};
  for(let i=0;i<argv.length;i++){
    const key=argv[i];if(!key.startsWith('--'))throw Error(`Unexpected argument: ${key}`);
    output[key.slice(2)]=argv[i+1]&&!argv[i+1].startsWith('--')?argv[++i]:true;
  }
  return output;
}
function finite(value,name,{min=0,max=Infinity,integer=false}={}){
  const n=Number(value);if(!Number.isFinite(n)||n<min||n>max||integer&&!Number.isInteger(n))throw Error(`Invalid ${name}: ${value}`);return n;
}
function childDone(child,name){
  return new Promise((resolve,reject)=>{child.once('error',reject);child.once('close',(code,signal)=>code===0?resolve():reject(Error(`${name} exited ${code??signal}`)));});
}
async function run(binary,argv){
  const child=spawn(binary,argv,{stdio:['ignore','pipe','pipe']});let stdout='',stderr='';
  child.stdout.on('data',d=>stdout+=d);child.stderr.on('data',d=>stderr+=d);
  try{await childDone(child,binary);}catch(error){throw Error(`${error.message}: ${stderr.slice(-3000)}`);}
  return stdout;
}
function canvasPackage(){
  const req=createRequire(import.meta.url);
  try{return req('@napi-rs/canvas');}catch(error){
    const modules=process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES;
    if(!modules)throw error;return createRequire(path.join(modules,'package.json'))('@napi-rs/canvas');
  }
}
async function configureFont(GlobalFonts,font){
  // Arial is not installed on the render host. Nimbus Sans is a metrically close
  // sans substitute. Register its family explicitly to avoid a serif fallback.
  const candidates=font?[font]:[
    '/usr/share/fonts/opentype/urw-base35/NimbusSans-Bold.otf',
    '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
  ];
  for(const candidate of candidates){
    try{await fs.access(candidate);if(GlobalFonts.registerFromPath(candidate,'Arial'))return {path:candidate,sha256:sha(await fs.readFile(candidate)),alias:'Arial'};}catch{}
  }
  if(font)throw Error(`Cannot register font: ${font}`);return {path:null,alias:'host default sans-serif',warning:'No explicit Arial substitute registered.'};
}
function overlay(canvas,patch,t,mode,title){
  if(mode==='none')return;
  const ctx=canvas.getContext('2d'),W=canvas.width,H=canvas.height;
  const phase=patch.metadata?.demoPhases?.find(p=>t>=p.start&&t<p.end)?.name||'patch';
  const size=Math.max(11,Math.round(H*.039)),bar=Math.max(23,Math.round(H*.09));
  ctx.save();ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;
  ctx.fillStyle='rgba(11,15,12,0.86)';ctx.fillRect(0,0,W,bar);
  ctx.font=`900 ${size}px Arial, sans-serif`;ctx.textBaseline='middle';ctx.fillStyle='#e4f69c';
  const label=mode==='title-phase'?`${title||patch.name}  /  ${phase.toUpperCase()}`:phase.toUpperCase();
  ctx.fillText(label,9,bar/2,W-64);ctx.textAlign='right';ctx.fillStyle='#fff';ctx.fillText(`${t.toFixed(1)}s`,W-8,bar/2);ctx.restore();
}
async function frameWorker(options){
  const job=await json(options.job),patch=await json(job.patchPath),media=await json(path.join(job.assetsDir,'manifest.json'));
  const {createCanvas,loadImage,GlobalFonts}=canvasPackage();
  await configureFont(GlobalFonts,job.fontPath);
  const {VisualEngine,paintViewport}=await import(pathToFileURL(path.join(job.engineDir,'visual-engine.mjs')));
  const [picture,matte,room,cues,regions,controls]=await Promise.all([
    Promise.all(media.picture.pages.map(p=>loadImage(path.join(job.assetsDir,p)))),
    Promise.all(media.matte.pages.map(p=>loadImage(path.join(job.assetsDir,p)))),
    loadImage(path.join(job.assetsDir,media.room.hybrid)),json(path.join(job.assetsDir,media.cues)),
    json(path.join(job.assetsDir,media.regions)),json(job.controlsPath),
  ]);
  const controlLane=(id,t)=>{
    const lane=controls.lanes[id];if(!lane)return undefined;
    return lane[Math.min(lane.length-1,Math.max(0,Math.floor(t*controls.fps)))];
  };
  const sourceId=patch.nodes.find(n=>n.type==='source')?.id||'source';
  const engine=new VisualEngine(media,{picture,matte,room,cues,regions},{createCanvas,width:job.width,height:job.height,control:t=>controlLane(sourceId,t)??0});
  engine.controlLane=controlLane;
  const views=[createCanvas(job.width,job.height)];
  if(job.portrait)views.push(createCanvas(job.portrait.width,job.portrait.height));
  const start=Number(options.start),count=Number(options.count);let totalMs=0,maximumMs=0;
  for(let frame=start;frame<start+count;frame++){
    const before=performance.now(),t=frame/job.fps;
    const layers=engine.renderLayers(patch,t);
    // Video variants share one graph evaluation. In portrait the three moving
    // picture bands sit below one full-height text plane, just as in the UI.
    for(const [viewIndex,canvas] of views.entries()){
      paintViewport(canvas,layers,viewIndex?'stack':'cover');overlay(canvas,patch,t,job.overlay,job.title);
      const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
      const bytes=Buffer.from(pixels.buffer,pixels.byteOffset,pixels.byteLength);
      if(!process.stdout.write(bytes))await once(process.stdout,'drain');
    }
    const ms=performance.now()-before;totalMs+=ms;maximumMs=Math.max(maximumMs,ms);
  }
  process.stderr.write(JSON.stringify({start,count,renderAndReadbackMs:totalMs,maximumFrameMs:maximumMs,rss:process.memoryUsage().rss})+'\n');
}
async function main(options){
  if(options.help){process.stdout.write(await fs.readFile(self,'utf8').then(s=>s.slice(s.indexOf('/**')+3,s.indexOf(' */')))+'\n');return;}
  for(const key of ['engine-dir','assets-dir','patch','output'])if(typeof options[key]!=='string')throw Error(`Required: --${key}`);
  const engineDir=path.resolve(options['engine-dir']),assetsDir=path.resolve(options['assets-dir']);
  const patchPath=path.resolve(options.patch),outputPath=path.resolve(options.output),outBase=outputPath.replace(/\.mp4$/i,'');
  if(!/\.mp4$/i.test(outputPath))throw Error('Output must end with .mp4');
  const [media,patch]=await Promise.all([json(path.join(assetsDir,'manifest.json')),json(patchPath)]);
  const duration=finite(options.duration??patch.duration,'duration',{min:.001,max:patch.duration});
  const width=finite(options.width??480,'width',{min:64,max:4096,integer:true}),height=finite(options.height??270,'height',{min:64,max:4096,integer:true});
  if(width%2||height%2)throw Error('H264 yuv420 dimensions must be even.');
  const fps=finite(options.fps??media.fps,'fps',{min:1,max:60}),frameCount=Math.ceil(duration*fps-1e-6);
  const chunkFrames=finite(options['chunk-frames']??6,'chunk-frames',{min:1,max:10000,integer:true});
  const portrait=options['portrait-output']?{output:path.resolve(options['portrait-output']),width:finite(options['portrait-width']??270,'portrait width',{min:64,max:4096,integer:true}),height:finite(options['portrait-height']??480,'portrait height',{min:64,max:4096,integer:true})}:null;
  if(portrait&&(portrait.width%2||portrait.height%2||!/\.mp4$/i.test(portrait.output)))throw Error('Portrait output requires even dimensions and an .mp4 path.');
  if(portrait?.output===outputPath)throw Error('Portrait and landscape output paths must differ.');
  const overlayMode=options.overlay??'none';if(!['none','phase','title-phase'].includes(overlayMode))throw Error('Overlay must be none, phase or title-phase.');
  const [provenance,regions,cues]=await Promise.all([media.provenance,media.regions,media.cues].map(p=>json(path.join(assetsDir,p))));
  const {validatePatch}=await import(pathToFileURL(path.join(engineDir,'core.mjs')));
  const validation=validatePatch(patch,{sourceHash:provenance.source.sha256,source:{offset:media.sourceIn},regions:regions.items.map(r=>r.id)});
  if(!validation.valid)throw Error(`Patch validation failed: ${validation.errors.join('; ')}`);
  if(patch.duration>media.duration+1e-6)throw Error('Patch exceeds available excerpt.');
  await fs.mkdir(path.dirname(outputPath),{recursive:true});
  if(portrait)await fs.mkdir(path.dirname(portrait.output),{recursive:true});
  const tempDir=await fs.mkdtemp(path.join(path.dirname(outputPath),'.fx-render-'));
  const partialVideo=path.join(tempDir,'video.mp4'),audioPath=path.join(tempDir,'audio.wav'),jobPath=path.join(tempDir,'job.json'),controlsPath=path.join(tempDir,'controls.json');
  const encoders=[];let worker=null;
  const before=performance.now();
  try{
    const {decodeWav,encodeWav,renderRackAudio}=await import(pathToFileURL(path.join(engineDir,'audio-engine.mjs')));
    const inputKind=options['audio-input']??'reference';if(!['reference','source'].includes(inputKind))throw Error('Audio input must be reference or source.');
    const inputPath=path.join(assetsDir,media.audio[inputKind]),inputBytes=await fs.readFile(inputPath),decoded=decodeWav(inputBytes);
    const audioStart=performance.now();
    // Queue timing uses the backend's fixed source windows. Provisional text cue
    // in/out fields are not passed as gesture/word arrival events.
    const audio=renderRackAudio(patch,decoded.channels,decoded.sampleRate,patch.duration,{peakTarget:.92,includeControlEnvelopes:true,controlFps:fps});
    if(!audio.controlEnvelopes||!audio.controlFps)throw Error('Audio backend lacks the shared controlEnvelopes API.');
    const controls={fps:audio.controlFps,lanes:Object.fromEntries(Object.entries(audio.controlEnvelopes).map(([id,lane])=>[id,Array.from(lane)]))};
    await writeJson(controlsPath,controls);
    const samples=Math.round(duration*decoded.sampleRate),channels=audio.channels.map(c=>c.slice(0,samples));
    const wavBytes=Buffer.from(encodeWav(channels,decoded.sampleRate));await fs.writeFile(audioPath,wavBytes);
    const audioRenderMs=performance.now()-audioStart;
    const {GlobalFonts}=canvasPackage(),font=await configureFont(GlobalFonts,options.font?path.resolve(options.font):null);
    const job={engineDir,assetsDir,patchPath,controlsPath,width,height,fps,portrait,overlay:overlayMode,title:options.title||patch.name,fontPath:font.path};
    await writeJson(jobPath,job);
    const views=[{output:outputPath,width,height,partial:partialVideo}];if(portrait)views.push({...portrait,partial:path.join(tempDir,'portrait.mp4')});
    for(const view of views){
      const ffmpegArgs=['-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgba','-video_size',`${view.width}x${view.height}`,'-framerate',String(fps),'-i','pipe:0','-i',audioPath,'-map','0:v:0','-map','1:a:0','-c:v','libx264','-threads','2','-preset','fast','-crf',String(options.crf??23),'-pix_fmt','yuv420p','-c:a','aac','-b:a','96k','-ar',String(decoded.sampleRate),'-frames:v',String(frameCount),'-t',duration.toFixed(10),'-movflags','+faststart',view.partial];
      const proc=spawn(options.ffmpeg||'ffmpeg',ffmpegArgs,{stdio:['pipe','ignore','pipe']});
      const encoder={...view,proc,stderr:'',pipeError:null,frameBytes:view.width*view.height*4};
      proc.stderr.on('data',d=>encoder.stderr+=d);proc.stdin.on('error',e=>encoder.pipeError=e);
      encoder.done=childDone(proc,'ffmpeg');encoder.done.catch(()=>{});encoders.push(encoder);
    }
    const chunks=[];
    process.stderr.write(`Rendering ${patch.name}: ${frameCount} frames, ${width}x${height}, ${fps} fps.\n`);
    for(let start=0;start<frameCount;start+=chunkFrames){
      const count=Math.min(chunkFrames,frameCount-start);let stats='',bytes=0,viewIndex=0,viewBytesRemaining=encoders[0].frameBytes;
      worker=spawn(process.execPath,[self,'--frame-worker','--job',jobPath,'--start',String(start),'--count',String(count)],{stdio:['ignore','pipe','pipe']});
      worker.stderr.on('data',d=>stats+=d);const workerDone=childDone(worker,'frame worker');workerDone.catch(()=>{});
      for await(const buffer of worker.stdout){
        bytes+=buffer.length;
        for(let offset=0;offset<buffer.length;){
          const encoder=encoders[viewIndex],length=Math.min(viewBytesRemaining,buffer.length-offset);
          if(encoder.pipeError)throw encoder.pipeError;
          if(!encoder.proc.stdin.write(buffer.subarray(offset,offset+length)))await once(encoder.proc.stdin,'drain');
          offset+=length;viewBytesRemaining-=length;
          if(viewBytesRemaining===0){viewIndex=(viewIndex+1)%encoders.length;viewBytesRemaining=encoders[viewIndex].frameBytes;}
        }
      }
      try{await workerDone;}catch(error){throw Error(`${error.message}: ${stats.slice(-3000)}`);}
      if(bytes!==count*encoders.reduce((sum,e)=>sum+e.frameBytes,0))throw Error(`Frame worker byte count mismatch: ${bytes}`);
      let row;try{row=JSON.parse(stats.trim().split('\n').at(-1));}catch{throw Error(`Missing frame worker receipt: ${stats}`);}
      chunks.push(row);worker=null;
      process.stderr.write(`${start+count}/${frameCount} frames; chunk ${(row.renderAndReadbackMs/1000).toFixed(2)} s, RSS ${(row.rss/1048576).toFixed(0)} MiB\n`);
    }
    for(const e of encoders)e.proc.stdin.end();
    await Promise.all(encoders.map(async e=>{try{await e.done;}catch(error){throw Error(`${error.message}: ${e.stderr}`);}}));
    const outputs=[];
    for(const e of encoders){
      const probe=JSON.parse(await run(options.ffprobe||'ffprobe',['-v','error','-show_streams','-show_format','-of','json',e.partial]));
      const video=probe.streams.find(s=>s.codec_type==='video'),sound=probe.streams.find(s=>s.codec_type==='audio');
      if(Number(video?.nb_frames)!==frameCount||!sound||Number(video.width)!==e.width||Number(video.height)!==e.height)throw Error('Output media validation failed.');
      await fs.rename(e.partial,e.output);outputs.push({file:path.basename(e.output),width:e.width,height:e.height,sha256:sha(await fs.readFile(e.output)),bytes:(await fs.stat(e.output)).size,probe:{video,audio:sound,duration:Number(probe.format.duration)}});
    }
    const codeHashes=Object.fromEntries(await Promise.all(['core.mjs','catalog.mjs','visual-engine.mjs','audio-engine.mjs'].map(async p=>[p,sha(await fs.readFile(path.join(engineDir,p)))])));
    const keepWav=Boolean(options['keep-wav']);if(keepWav)await fs.rename(audioPath,outBase+'.wav');
    await fs.copyFile(patchPath,outBase+'.patch.json');
    const report={schemaVersion:'1.0.0',patchId:patch.id,name:patch.name,output:outputs[0].file,bytes:outputs[0].bytes,sha256:outputs[0].sha256,outputs,width,height,fps,frameCount,duration,overlay:overlayMode,patchSha256:sha(JSON.stringify(patch)),source:patch.source,assetsManifestSha256:sha(await fs.readFile(path.join(assetsDir,'manifest.json'))),codeHashes,font,audio:{input:inputKind,inputSha256:sha(inputBytes),sampleRate:decoded.sampleRate,samples,channels:channels.length,pcmWavSha256:sha(wavBytes),file:keepWav?path.basename(outBase+'.wav'):null,controlFps:audio.controlFps,controlNodeIds:Object.keys(audio.controlEnvelopes),renderMs:audioRenderMs,report:audio.report},validation,chunks,elapsedSeconds:(performance.now()-before)/1000,probe:outputs[0].probe,limitations:['AAC/H264 previews are lossy encodes of the shared graph.','Text uses the recorded font substitute on the render host.','Inherited body masks and hybrid room plate remain workprint assets.','Machine-crosschecked speech cues and dialogue candidate await listener/artist acceptance.']};
    await writeJson(outBase+'.render.json',report);await fs.rm(tempDir,{recursive:true,force:true});
    process.stdout.write(JSON.stringify({output:outputPath,report:outBase+'.render.json',frameCount,duration,bytes:report.bytes,seconds:report.elapsedSeconds})+'\n');
  }catch(error){worker?.kill('SIGKILL');for(const e of encoders)e.proc.kill('SIGKILL');await fs.rm(tempDir,{recursive:true,force:true});throw error;}
}

try{const options=args(process.argv.slice(2));if(options['frame-worker'])await frameWorker(options);else await main(options);}
catch(error){process.stderr.write(`${error.stack||error}\n`);process.exitCode=1;}
