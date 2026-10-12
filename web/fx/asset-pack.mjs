/** Content identity of the exact derived assets consumed by the editable rack. */
export const ASSET_PACK_SCHEMA = 'god-here-fx-asset-pack/1';
const shaPattern=/^[a-f0-9]{64}$/;
const encoder=new TextEncoder();
function bytes(value){
  if(value instanceof ArrayBuffer)return new Uint8Array(value);
  if(ArrayBuffer.isView(value))return new Uint8Array(value.buffer,value.byteOffset,value.byteLength);
  throw new TypeError('Asset identity requires source bytes.');
}
async function sha256(value){
  const digest=await globalThis.crypto.subtle.digest('SHA-256',bytes(value));
  return Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,'0')).join('');
}
export function assetPackPaths(media){
  if(!Array.isArray(media?.picture?.pages)||!media.picture.pages.length||!Array.isArray(media?.matte?.pages)||!media.matte.pages.length)throw Error('Derived picture and matte pages are required.');
  const paths=[...media.picture.pages,...media.matte.pages,media.room?.hybrid,media.cues,media.regions,media.provenance,media.waveforms,media.audio?.source,media.audio?.reference];
  if(paths.some(value=>typeof value!=='string'||!value||value.startsWith('/')||/[\\?#%\x00-\x1f]/.test(value)||value.split('/').some(part=>!part||part==='.'||part==='..')||/^[a-z]+:/i.test(value)))throw Error('Invalid derived asset path.');
  return [...new Set(paths)].sort();
}
/** readBytes must return the exact bytes used by the renderer, not a metadata hash. */
export async function assetPackIdentity(manifestBytes,readBytes){
  const manifest=bytes(manifestBytes),media=JSON.parse(new TextDecoder().decode(manifest));
  const files=await Promise.all(assetPackPaths(media).map(async path=>{
    const content=bytes(await readBytes(path));
    return {path,bytes:content.byteLength,sha256:await sha256(content)};
  }));
  const payload={schema:ASSET_PACK_SCHEMA,manifestSha256:await sha256(manifest),files};
  return {...payload,sha256:await sha256(encoder.encode(JSON.stringify(payload)))};
}
export function sameAssetPack(expected,actual){
  return expected?.schema===ASSET_PACK_SCHEMA&&actual?.schema===ASSET_PACK_SCHEMA&&
    shaPattern.test(expected?.sha256)&&shaPattern.test(actual?.sha256)&&
    shaPattern.test(expected?.manifestSha256)&&shaPattern.test(actual?.manifestSha256)&&
    expected.sha256===actual.sha256&&expected.manifestSha256===actual.manifestSha256;
}
/** Appending cannot relabel historical renders as products of another asset pack. */
export function assertBoundRenderAssets(receipt,identity){
  if(!sameAssetPack(receipt?.assetsIdentity,identity))throw Error('Render receipt is not bound to the current derived asset bytes.');
  return identity.sha256;
}
