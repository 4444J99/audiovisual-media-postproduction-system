// Bound both the request and response-body read. A connected request can still
// stall while its body is arriving, so fetch's response alone is not readiness.
export async function readAsset(url,{label='Source asset',format='json',timeoutMs=25000,fetchImpl=fetch}={}){
  const controller=new AbortController();
  let timer;
  try{
    return await Promise.race([
      (async()=>{
        const response=await fetchImpl(url,{signal:controller.signal});
        if(!response.ok)throw Error(`${label} could not load (HTTP ${response.status}).`);
        return await (format==='json'?response.json():response.arrayBuffer());
      })(),
      new Promise((_,reject)=>{
        timer=setTimeout(()=>{
          reject(Error(`${label} took too long to load. Retry loading or play the demonstrations.`));
          controller.abort();
        },timeoutMs);
      })
    ]);
  }catch(error){
    if(error.message?.startsWith(label))throw error;
    throw Error(`${label} could not be read. Retry loading or play the demonstrations.`,{cause:error});
  }finally{
    clearTimeout(timer);
  }
}
