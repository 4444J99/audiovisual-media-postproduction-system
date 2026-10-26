/** Local, hash-verified prepared media; never fetch a locator from a record. */
import {canonicalJSON,digest,validateRecord,preparePerformanceAudio,validatePreparedGeometry} from './performance-adapter.mjs';
import {decodeWav} from '../fx/audio-engine.mjs';

const ENGINES=['core.mjs','catalog.mjs','visual-engine.mjs','audio-engine.mjs'];
export async function verifyRetainedEngine(record,fetcher=fetch){
  const hashes={};for(const name of ENGINES){const response=await fetcher(new URL('../fx/'+name,import.meta.url));if(!response.ok)throw Error('Retained engine unavailable');hashes['web/fx/'+name]=await digest(await response.arrayBuffer());}
  const actual=await digest(canonicalJSON(hashes));if(record.runtime.engine_sha256!==actual)throw Error('Saved performance uses a different FX engine');return actual;
}
function integer(value,min=0){if(!Number.isSafeInteger(value)||value<min)throw Error('Invalid prepared asset measurement');return value;}
function filename(value){if(typeof value!=='string'||! /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value))throw Error('Prepared asset must be a local basename');return value;}
function asset(row,files){filename(row?.file);if(! /^[a-f0-9]{64}$/.test(row.sha256||''))throw Error('Prepared asset hash required');integer(row.bytes,1);const file=files.get(row.file);if(!file||file.size!==row.bytes)throw Error('Prepared asset missing or changed');return file;}
async function verified(row,files,signal){signal?.throwIfAborted();const data=await asset(row,files).arrayBuffer();signal?.throwIfAborted();if(data.byteLength!==row.bytes||await digest(data)!==row.sha256)throw Error('Prepared asset hash mismatch');return data;}
function pngDimensions(bytes){const b=new Uint8Array(bytes),v=new DataView(bytes);if(b.length<24||![137,80,78,71,13,10,26,10].every((n,i)=>b[i]===n)||String.fromCharCode(...b.slice(12,16))!=='IHDR')throw Error('Prepared atlas must be PNG');return [v.getUint32(16),v.getUint32(20)];}
/** Inspect before decodeWav allocates sample arrays from an untrusted header. */
export function verifyWavHeader(bytes,row){const b=new Uint8Array(bytes),v=new DataView(bytes),text=(at,n)=>String.fromCharCode(...b.subarray(at,at+n));let fmt=null,data=null;
  if(b.length<44||text(0,4)!=='RIFF'||text(8,4)!=='WAVE')throw Error('WAV header measurements mismatch');
  for(let at=12;at+8<=b.length;){const size=v.getUint32(at+4,true),start=at+8;if(start+size>b.length)throw Error('WAV header measurements mismatch');
    if(text(at,4)==='fmt '){if(size<16)throw Error('WAV header measurements mismatch');let encoding=v.getUint16(start,true);if(encoding===65534&&size>=40)encoding=v.getUint16(start+24,true);fmt={encoding,channels:v.getUint16(start+2,true),rate:v.getUint32(start+4,true),align:v.getUint16(start+12,true),bits:v.getUint16(start+14,true)};}
    if(text(at,4)==='data')data={start,size};at=start+size+(size&1);
  }
  if(!fmt||!data||fmt.channels!==row.channels||fmt.rate!==row.sample_rate||![16,24,32].includes(fmt.bits)||fmt.align!==fmt.channels*fmt.bits/8||data.size!==row.samples*fmt.align||!(fmt.encoding===1||fmt.encoding===3&&fmt.bits===32))throw Error('WAV header measurements mismatch');
  if(fmt.encoding===3)for(let at=data.start;at<data.start+data.size;at+=4)if(!Number.isFinite(v.getFloat32(at,true)))throw Error('WAV contains nonfinite samples');
}
export function disposePrepared(prepared){const images=new Set();for(const p of prepared?.materials?.values()||[])for(const kind of ['picture','matte'])for(const image of p.assets[kind])images.add(image);for(const image of images)image.close?.();prepared?.materials?.clear();prepared?.audioVariants?.clear();}

export async function loadPreparedFiles(record,selected,audioContext,{signal,decodeImage=blob=>createImageBitmap(blob)}={}){
  validateRecord(record);const profile=record.runtime.profile;
  if(profile.admitted!==true||!['decoded_audio_bytes','texture_bytes','event_history_bytes'].every(k=>Number.isSafeInteger(profile.byte_caps[k])&&profile.byte_caps[k]>0))throw Error('Performance profile needs measured admission');
  if(new TextEncoder().encode(JSON.stringify(record)).byteLength>profile.byte_caps.event_history_bytes)throw Error('Performance record exceeds history byte cap');
  const files=new Map();for(const file of selected){filename(file.name);if(files.has(file.name))throw Error('Duplicate local asset basename');files.set(file.name,file);}
  const manifests=new Map();let audioBytes=0,textureBytes=0,encodedBytes=0;const unique=new Set(),encoded=new Set();
  for(const m of record.runtime.materials){signal?.throwIfAborted();const file=files.get(m.id+'.material.json');if(!file||file.size>1024*1024)throw Error('Prepared material manifest missing or too large');const bytes=await file.arrayBuffer();if(await digest(bytes)!==m.sha256)throw Error('Prepared material manifest identity mismatch');const manifest=JSON.parse(new TextDecoder().decode(bytes));
    if(manifest.schema!=='amps.prepared-material.v1'||file.size!==m.bytes)throw Error('Unsupported prepared material manifest or byte count');const audio=manifest.audio;asset(audio,files);
    integer(audio.channels,1);integer(audio.samples,1);integer(audio.sample_rate,1000);if(audio.channels>2||audio.samples!==m.metadata.audio_sample_count||audio.sample_rate!==m.metadata.audio_sample_rate)throw Error('Prepared audio measurements disagree with corpus');
    if(!unique.has(audio.sha256)){audioBytes+=audio.samples*audio.channels*4;unique.add(audio.sha256);}
    for(const kind of ['picture','matte']){const pages=manifest.assets?.[kind];if(!Array.isArray(pages)||!pages.length)throw Error('Prepared atlas pages required');for(const row of pages){asset(row,files);integer(row.width,1);integer(row.height,1);if(!unique.has(row.sha256)){textureBytes+=row.width*row.height*4;unique.add(row.sha256);}}}
    manifests.set(m.id,manifest);
    for(const row of [audio,...manifest.assets.picture,...manifest.assets.matte])if(!encoded.has(row.sha256)){encoded.add(row.sha256);encodedBytes+=row.bytes;}
  }
  if(audioBytes>profile.byte_caps.decoded_audio_bytes||textureBytes>profile.byte_caps.texture_bytes||encodedBytes>profile.byte_caps.decoded_audio_bytes+profile.byte_caps.texture_bytes)throw Error('Prepared decoded media exceeds byte caps');
  const prepared={materials:new Map()},audioCache=new Map(),imageCache=new Map();
  try{
    for(const m of record.runtime.materials){signal?.throwIfAborted();const manifest=manifests.get(m.id),a=manifest.audio;let buffer=audioCache.get(a.sha256);
      if(!buffer){const bytes=await verified(a,files,signal);verifyWavHeader(bytes,a);const wav=decodeWav(bytes);if(wav.sampleRate!==a.sample_rate||wav.channels.length!==a.channels||wav.channels.some(c=>c.length!==a.samples))throw Error('Decoded audio measurements mismatch');buffer=audioContext.createBuffer(a.channels,a.samples,a.sample_rate);for(let c=0;c<a.channels;c++)buffer.copyToChannel(wav.channels[c],c);audioCache.set(a.sha256,buffer);}
      const assets={picture:[],matte:[]};prepared.materials.set(m.id,{sha256:m.sha256,audioBuffer:buffer,media:manifest.media,assets});
      for(const kind of ['picture','matte'])for(const row of manifest.assets[kind]){let image=imageCache.get(row.sha256);if(!image){const bytes=await verified(row,files,signal),dimensions=pngDimensions(bytes);if(dimensions[0]!==row.width||dimensions[1]!==row.height)throw Error('PNG header measurements mismatch');image=await decodeImage(new Blob([bytes],{type:'image/png'}));imageCache.set(row.sha256,image);signal?.throwIfAborted();if(image.width!==row.width||image.height!==row.height)throw Error('Decoded atlas measurements mismatch');}assets[kind].push(image);}
      validatePreparedGeometry(m,prepared.materials.get(m.id));
    }
    await preparePerformanceAudio(record,prepared,audioContext,{signal});return prepared;
  }catch(error){for(const image of imageCache.values())image.close?.();disposePrepared(prepared);throw error;}
}
