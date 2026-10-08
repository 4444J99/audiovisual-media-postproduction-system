/** Exact signal description for matching a rendered preview to an editable rack.
 * Cosmetic names, preset labels and saved UI snapshots do not change output.
 * Sub-microsecond differences from JSON float serialization are canonicalized.
 */
function stable(value) {
  if(typeof value==='number')return Math.round(value*1e6)/1e6;
  if(Array.isArray(value))return value.map(stable);
  if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().filter(k=>value[k]!==undefined).map(k=>[k,stable(value[k])]));
  return value;
}
export function signalSignature(patch) {
  const {seed,duration,source,connections,events}=patch;
  const nodes=patch.nodes.map(({name,presetId,metadata,...signal})=>signal);
  const metadata={wordMode:patch.metadata?.wordMode||'cues',words:patch.metadata?.wordMode==='authored'?(patch.metadata.words||'HOW WHY WHAT'):undefined,demoPhases:patch.metadata?.demoPhases};
  return JSON.stringify(stable({version:1,seed,duration,source,nodes,connections,events,metadata}));
}
