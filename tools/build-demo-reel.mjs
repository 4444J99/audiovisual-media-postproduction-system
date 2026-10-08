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
const options={};for(let i=2;i<process.argv.length;i++)options[process.argv[i].replace(/^--/,'')]=process.argv[++i];
if(!options['preview-dir'])throw Error('Required --preview-dir');
const root=path.resolve(options['preview-dir']),manifest=JSON.parse(await fs.readFile(path.join(root,'manifest.json')));
const demos=manifest.entries.filter(e=>e.kind==='module demonstration');if(demos.length!==13||demos.some(e=>e.status!=='complete'))throw Error('All13 module demos must be complete.');
const font=options.font||'/usr/share/fonts/opentype/urw-base35/NimbusSans-Bold.otf';
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'fx-reel-'));
const duration=demos.reduce((s,e)=>s+e.duration,0),frameCount=demos.reduce((s,e)=>s+e.frameCount,0),fps=12,sr=24000;
const phaseFiles={};for(const name of ['bypass','extreme','parameter sweep']){const file=path.join(temp,name.replaceAll(' ','-')+'.txt');await fs.writeFile(file,name.toUpperCase());phaseFiles[name]=file;}
const metadata=[';FFMETADATA1','title=God here — thirteen processor demonstrations','comment=Actual95–107.166667 excerpt repeated for independent processor tests. Bypass → extreme → intensity sweep → bypass. Dialogue and masks remain workprint candidates.'];
let tick=0;
for(let i=0;i<demos.length;i++){
 const e=demos[i],title=`${String(i+1).padStart(2,'0')}  ${e.name.replace(/ — demonstration$/,'')}`;
 e._titleFile=path.join(temp,`title-${i}.txt`);await fs.writeFile(e._titleFile,title);
 e._patch=JSON.parse(await fs.readFile(path.join(root,e.patch),'utf8'));
 const ticks=Math.round(e.frameCount/fps*12000);metadata.push('[CHAPTER]','TIMEBASE=1/12000',`START=${tick}`,`END=${tick+ticks}`,`title=${title}`);tick+=ticks;
}
const metadataFile=path.join(temp,'chapters.ffmetadata');await fs.writeFile(metadataFile,metadata.join('\n')+'\n');
async function command(binary,args){const p=spawn(binary,args,{stdio:['ignore','pipe','pipe']});let out='',err='';p.stdout.on('data',d=>out+=d);p.stderr.on('data',d=>err+=d);await new Promise((resolve,reject)=>{p.on('error',reject);p.on('close',code=>code===0?resolve():reject(Error(`${binary} exited ${code}: ${err.slice(-4000)}`)));});return out;}
const receipts=[];
try{
 for(const orientation of ['landscape','portrait']){
  const portrait=orientation==='portrait',output=path.join(root,`god-here-13-processors-${orientation}.mp4`),width=portrait?270:480,height=portrait?480:270;
  const args=['-hide_banner','-loglevel','error','-y'];
  for(const e of demos)args.push('-i',path.join(root,portrait?e.portrait:e.video));
  for(const e of demos)args.push('-i',path.join(root,e.video.replace(/\.mp4$/,'.wav')));
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
 const receipt={schemaVersion:'1.0.0',title:'God here — thirteen processor demonstrations',inputs:demos.map(e=>({id:e.id,signalSignature:e.signalSignature||e.key,video:e.video,portrait:e.portrait,sourceReceipt:e.receipt})),codeHashes:manifest.codeHashes,font,outputs:receipts,audio:{sampleRate:sr,samples:Math.round(duration*sr),method:'Concatenated exact renderer PCM WAVs, encoded once as AAC.'},method:'Title and phase overlay of complete factory module clips; source video decoded/re-encoded once; chapter boundaries preserve146frames each.'};
 await fs.writeFile(path.join(root,'god-here-13-processors.render.json'),JSON.stringify(receipt,null,2)+'\n');process.stdout.write(JSON.stringify(receipts.map(({probe,...r})=>r))+'\n');
}finally{await fs.rm(temp,{recursive:true,force:true});}
