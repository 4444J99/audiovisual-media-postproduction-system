#!/usr/bin/env node
/** Join the 13 already rendered module demonstrations with title/phase labels.
 * WAVs, rather than independently AAC-encoded clip audio, are concatenated to
 * avoid accumulating AAC priming at the 13 joins. ffmpeg encodes audio once.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {isDeepStrictEqual} from 'node:util';
import {validateFactoryEntries} from './render-factory.mjs';
import {signalSignature} from '../web/fx/preview-key.mjs';
import {assertBoundRenderAssets} from '../web/fx/asset-pack.mjs';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const digest=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const rendererKeys=['core.mjs','catalog.mjs','visual-engine.mjs','audio-engine.mjs','asset-pack.mjs'];

/** Authenticate the complete producer chain before creating any assembly files. */
export async function authenticateDemoInputs(directory){
 const root=await fs.realpath(path.resolve(directory));
 async function read(name,expected,allowUnbound=false){
  if(!allowUnbound&&!digest(expected))throw Error(`Demo input identity is missing: ${name}`);
  if(typeof name!=='string'||!name||/[\\%?#\x00-\x1f:]/.test(name)||name.startsWith('/')||name.split('/').some(p=>!p||p==='.'||p==='..'))throw Error('Unsafe demo input path.');
  let filename=root;for(const part of name.split('/')){filename=path.join(filename,part);if((await fs.lstat(filename)).isSymbolicLink())throw Error('Demo inputs cannot be symlinks.');}
  if(!path.relative(root,await fs.realpath(filename)).split(path.sep).every(p=>p!=='..'))throw Error('Demo input escapes factory directory.');
  const bytes=await fs.readFile(filename),hash=sha(bytes);
  if(!allowUnbound&&hash!==expected)throw Error(`Demo input identity mismatch: ${name}`);
  return {name,path:filename,sha256:hash,bytes:bytes.length,content:bytes};
 }
 const manifestFile=await read('manifest.json',undefined,true),manifest=JSON.parse(manifestFile.content);
 if(manifest.schemaVersion!=='1.0.0'||manifest.complete!==true||!Array.isArray(manifest.entries)||manifest.entries.some(e=>e.status!=='complete'))throw Error('Complete factory manifest required.');
 validateFactoryEntries([],manifest.entries);
 const demos=manifest.entries.filter(e=>e.kind==='module demonstration');
 if(demos.length!==13)throw Error('All 13 module demonstrations are required.');
 if(manifest.fps!==12||manifest.width!==480||manifest.height!==270||manifest.portraitWidth!==270||manifest.portraitHeight!==480)throw Error('Incompatible factory picture clock.');
 if(!digest(manifest.source?.sha256)||!Number.isFinite(manifest.source?.offset))throw Error('Factory source identity is incomplete.');
 for(const key of rendererKeys)if(!digest(manifest.codeHashes?.[key]))throw Error('Factory producing code identity is incomplete.');
 if(manifest.codeHashes?.['preview-key.mjs']!==sha(await fs.readFile(new URL('../web/fx/preview-key.mjs',import.meta.url))))throw Error('Unsupported factory signal-signature code.');
 const assets=manifest.assetsIdentity;
 if(!assets||assets.schema!=='god-here-fx-asset-pack/1'||!digest(assets.manifestSha256)||!Array.isArray(assets.files)||!assets.files.length||
    sha(Buffer.from(JSON.stringify({schema:assets.schema,manifestSha256:assets.manifestSha256,files:assets.files})))!==assets.sha256)throw Error('Factory asset identity is incomplete or changed.');
 const files=[],result=[];
 for(const e of demos){
  for(const [key,expected]of Object.entries({video:`${e.id}.mp4`,portrait:`${e.id}-portrait.mp4`,patch:`${e.id}.patch.json`,receipt:`${e.id}.render.json`}))if(e[key]!==expected)throw Error('Demo filename differs from producer identity.');
  const receiptFile=await read(e.receipt,e.receiptSha256),receipt=JSON.parse(receiptFile.content);
  const patchFile=await read(e.patch,receipt.patchFileSha256),patch=JSON.parse(patchFile.content);
  if(sha(Buffer.from(JSON.stringify(patch)))!==receipt.patchSha256||signalSignature(patch)!==e.signalSignature||e.key!==e.signalSignature||
     receipt.patchId!==e.id||patch.id!==e.id||receipt.name!==e.name||patch.name!==e.name)throw Error(`Demo patch identity mismatch: ${e.id}`);
  if(!isDeepStrictEqual(receipt.source,manifest.source)||!isDeepStrictEqual(patch.source,manifest.source))throw Error('Demo source identity mismatch.');
  assertBoundRenderAssets(receipt,assets);
  if(e.assetsIdentitySha256!==assets.sha256||receipt.assetsManifestSha256!==assets.manifestSha256||!isDeepStrictEqual(receipt.assetsIdentity,assets))throw Error('Demo asset identity mismatch.');
  for(const key of rendererKeys)if(receipt.codeHashes?.[key]!==manifest.codeHashes[key])throw Error('Demo producing code identity mismatch.');
  if(!digest(receipt.codeHashes?.['workbench-state.mjs']))throw Error('Demo workbench code identity is missing.');
  if(!Number.isInteger(e.frameCount)||e.frameCount<=0||!Number.isFinite(e.duration)||Math.abs(e.duration-e.frameCount/12)>1e-6||
     receipt.fps!==12||receipt.frameCount!==e.frameCount||receipt.duration!==e.duration||Math.abs(patch.duration-e.duration)>1e-6)throw Error('Demo duration/frame clock mismatch.');
  if(!Array.isArray(patch.metadata?.demoPhases)||patch.metadata.demoPhases.some(p=>!['bypass','extreme','parameter sweep'].includes(p.name)||!Number.isFinite(p.start)||!Number.isFinite(p.end)))throw Error('Invalid authenticated demonstration phases.');
  if(!Array.isArray(receipt.outputs)||receipt.outputs.length!==2)throw Error('Demo video receipt is incomplete.');
  const inputHashes={receiptSha256:receiptFile.sha256,patchFileSha256:patchFile.sha256};
  let videoBytes=0;
  for(const [key,hashKey,width,height]of [['video','sha256',480,270],['portrait','portraitSha256',270,480]]){
   const outputs=receipt.outputs.filter(o=>o.file===e[key]);
   if(outputs.length!==1||outputs[0].sha256!==e[hashKey]||outputs[0].width!==width||outputs[0].height!==height)throw Error('Demo video identity differs from factory manifest.');
   const file=await read(e[key],e[hashKey]);if(file.bytes!==outputs[0].bytes)throw Error('Demo video byte count differs from receipt.');
   videoBytes+=file.bytes;delete file.content;files.push(file);inputHashes[key+'Sha256']=file.sha256;
  }
  if(e.bytes!==videoBytes)throw Error('Demo total video size differs from receipt.');
  const wavName=`${e.id}.wav`,audio=receipt.audio;
  if(audio?.file!==wavName||audio.sampleRate!==24000||audio.channels!==2||audio.samples!==Math.round(e.duration*24000))throw Error('Demo WAV clock/identity is incomplete.');
  const wav=await read(wavName,audio.pcmWavSha256);delete wav.content;files.push(wav);inputHashes.wavSha256=wav.sha256;
  result.push({...e,_patch:patch,_wav:wavName,_inputHashes:inputHashes,_nativeCodeHashes:receipt.codeHashes});
 }
 return {manifest,demos:result,manifestSha256:manifestFile.sha256,files};
}

export async function buildDemoReel(options){
if(!options['preview-dir'])throw Error('Required --preview-dir');
const root=path.resolve(options['preview-dir']);
const {manifest,demos,manifestSha256,files}=await authenticateDemoInputs(root);
const font=options.font||'/usr/share/fonts/opentype/urw-base35/NimbusSans-Bold.otf';
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'fx-reel-'));
try{
// Concatenation consumes authenticated private snapshots, even if the source
// package changes after preflight. All copies finish before any reel is opened.
const inputs=path.join(temp,'inputs');await fs.mkdir(inputs);
for(const file of files){const target=path.join(inputs,file.name);await fs.copyFile(file.path,target);if(sha(await fs.readFile(target))!==file.sha256)throw Error(`Demo input changed during snapshot: ${file.name}`);}
const duration=demos.reduce((s,e)=>s+e.duration,0),frameCount=demos.reduce((s,e)=>s+e.frameCount,0),fps=12,sr=24000;
const phaseFiles={};for(const name of ['bypass','extreme','parameter sweep']){const file=path.join(temp,name.replaceAll(' ','-')+'.txt');await fs.writeFile(file,name.toUpperCase());phaseFiles[name]=file;}
const metadata=[';FFMETADATA1','title=God here — thirteen processor demonstrations','comment=Actual95–107.166667 excerpt repeated for independent processor tests. Bypass → extreme → intensity sweep → bypass. Dialogue and masks remain workprint candidates.'];
let tick=0;
for(let i=0;i<demos.length;i++){
 const e=demos[i],title=`${String(i+1).padStart(2,'0')}  ${e.name.replace(/ — demonstration$/,'')}`;
 e._titleFile=path.join(temp,`title-${i}.txt`);await fs.writeFile(e._titleFile,title);
 const ticks=Math.round(e.frameCount/fps*12000);metadata.push('[CHAPTER]','TIMEBASE=1/12000',`START=${tick}`,`END=${tick+ticks}`,`title=${title}`);tick+=ticks;
}
const metadataFile=path.join(temp,'chapters.ffmetadata');await fs.writeFile(metadataFile,metadata.join('\n')+'\n');
async function command(binary,args){const p=spawn(binary,args,{stdio:['ignore','pipe','pipe']});let out='',err='';p.stdout.on('data',d=>out+=d);p.stderr.on('data',d=>err+=d);await new Promise((resolve,reject)=>{p.on('error',reject);p.on('close',code=>code===0?resolve():reject(Error(`${binary} exited ${code}: ${err.slice(-4000)}`)));});return out;}
const receipts=[];
 for(const orientation of ['landscape','portrait']){
  const portrait=orientation==='portrait',output=path.join(root,`god-here-13-processors-${orientation}.mp4`),width=portrait?270:480,height=portrait?480:270;
  const args=['-hide_banner','-loglevel','error','-y'];
  for(const e of demos)args.push('-i',path.join(inputs,portrait?e.portrait:e.video));
  for(const e of demos)args.push('-i',path.join(inputs,e._wav));
  args.push('-i',metadataFile);
  const filters=[];
  for(let i=0;i<demos.length;i++){
   const e=demos[i],bar=portrait?36:26,titleSize=portrait?11:12,phaseSize=portrait?9:10;
   let vf=`[${i}:v]fps=12,trim=end_frame=${e.frameCount},setpts=N/(12*TB),drawbox=x=0:y=0:w=iw:h=${bar}:color=black@0.87:t=fill,drawtext=fontfile='${font}':textfile='${e._titleFile}':fontsize=${titleSize}:x=8:y=${portrait?5:7}:fontcolor=0xf2f5e9`;
   for(const phase of e._patch.metadata.demoPhases){
    vf+=`,drawtext=fontfile='${font}':textfile='${phaseFiles[phase.name]}':fontsize=${phaseSize}:x=${portrait?'8':'w-tw-8'}:y=${portrait?22:8}:fontcolor=0xdefa66:enable='gte(t,${phase.start})*lt(t,${phase.end})'`;
   }
   filters.push(vf+`[v${i}]`);
   filters.push(`[${demos.length+i}:a]atrim=end_sample=${Math.round(e.duration*sr)},asetpts=N/SR/TB[a${i}]`);
  }
  filters.push(demos.map((_,i)=>`[v${i}][a${i}]`).join('')+`concat=n=${demos.length}:v=1:a=1[v][a]`);
  const script=path.join(temp,orientation+'.filters');await fs.writeFile(script,filters.join(';\n'));
  args.push('-filter_complex_threads','2','-filter_complex_script',script,'-map','[v]','-map','[a]','-map_metadata',String(demos.length*2),'-c:v','libx264','-threads','2','-preset','fast','-crf','22','-pix_fmt','yuv420p','-c:a','aac','-b:a','96k','-ar',String(sr),'-frames:v',String(frameCount),'-t',duration.toFixed(9),'-movflags','+faststart',output);
  const start=Date.now();process.stdout.write(`REEL ${orientation}: ${frameCount} frames / ${duration.toFixed(3)} s\n`);await command(options.ffmpeg||'ffmpeg',args);
  const probe=JSON.parse(await command(options.ffprobe||'ffprobe',['-v','error','-show_streams','-show_format','-show_chapters','-of','json',output]));
  const v=probe.streams.find(s=>s.codec_type==='video'),a=probe.streams.find(s=>s.codec_type==='audio');
  if(Number(v.nb_frames)!==frameCount||Number(v.width)!==width||Number(v.height)!==height||!a||probe.chapters.length!==13)throw Error('Reel media/chapters validation failed.');
  const bytes=await fs.readFile(output);receipts.push({orientation,file:path.basename(output),width,height,fps,frameCount,duration,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),elapsedSeconds:(Date.now()-start)/1000,probe});
 }
 const receipt={schemaVersion:'1.0.0',title:'God here — thirteen processor demonstrations',inputs:demos.map(e=>({id:e.id,signalSignature:e.signalSignature||e.key,video:e.video,portrait:e.portrait,sourceReceipt:e.receipt,...e._inputHashes,nativeCodeHashes:e._nativeCodeHashes})),factoryManifestSha256:manifestSha256,codeHashes:manifest.codeHashes,font,outputs:receipts,audio:{sampleRate:sr,samples:Math.round(duration*sr),method:'Concatenated exact renderer PCM WAVs, encoded once as AAC.'},method:'Title and phase overlay of complete factory module clips; source video decoded/re-encoded once; chapter boundaries preserve146frames each.'};
 await fs.writeFile(path.join(root,'god-here-13-processors.render.json'),JSON.stringify(receipt,null,2)+'\n');process.stdout.write(JSON.stringify(receipts.map(({probe,...r})=>r))+'\n');
}finally{await fs.rm(temp,{recursive:true,force:true});}

}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const options={};for(let i=2;i<process.argv.length;i++)options[process.argv[i].replace(/^--/,'')]=process.argv[++i];
 buildDemoReel(options).catch(error=>{process.stderr.write(`${error.stack||error}\n`);process.exitCode=1;});
}
