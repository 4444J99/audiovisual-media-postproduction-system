import {renderRackAudio} from './audio-engine.mjs';
let source, reference, sampleRate;
onmessage = ({data}) => {
  if(data.type === 'init') {
    source=data.source;reference=data.reference;sampleRate=data.sampleRate;
    postMessage({type:'ready'});return;
  }
  if(data.type === 'render') {
    try {
      const input=data.input==='source'?source:reference;
      const output=renderRackAudio(data.patch,input,sampleRate,data.patch.duration,{peakTarget:.92,includeControlEnvelopes:true,controlFps:12});
      postMessage({type:'rendered',id:data.id,channels:output.channels,report:output.report,controlEnvelopes:output.controlEnvelopes,controlFps:output.controlFps},output.channels.map(c=>c.buffer));
    }catch(error){postMessage({type:'error',id:data.id,message:error.message});}
  }
};
