import {evaluate, validateSession, stateFromEvents, makeSession} from './score.js';

const $=id=>document.getElementById(id);
const video=$('source'), canvas=$('picture'), stage=$('stage');
const config=await (await fetch('composition.json')).json();
video.src='media/dialogue-reference.mp4';
const gl=canvas.getContext('webgl',{alpha:false,preserveDrawingBuffer:false});
let selected=null, events=[], sessionLoaded=false, reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
$('motion').checked=reduced;
let priorShot=null,lastSourceTime=-1,history=[],nextCapture=0;
const maxHistory=21, historyWidth=640, historyHeight=360;
const capture=document.createElement('canvas');capture.width=historyWidth;capture.height=historyHeight;
const captureCtx=capture.getContext('2d',{willReadFrequently:true});
const scratch=document.createElement('canvas');scratch.width=historyWidth;scratch.height=historyHeight;
const scratchCtx=scratch.getContext('2d');
let program,textures=[];

function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
if(gl){
  const vs=shader(gl.VERTEX_SHADER,'attribute vec2 p;varying vec2 uv;void main(){uv=vec2((p.x+1.)*.5,(1.-p.y)*.5);gl_Position=vec4(p,0,1);}');
  const fs=shader(gl.FRAGMENT_SHADER,`precision mediump float;varying vec2 uv;uniform sampler2D now;uniform sampler2D past;uniform vec2 spans[5];uniform float amounts[5];uniform float styles[5];uniform float neutral;
void main(){vec3 c=texture2D(now,uv).rgb;if(neutral>.5){gl_FragColor=vec4(c,1);return;}for(int i=0;i<5;i++){vec2 r=spans[i];if(uv.x>=r.x&&uv.x<r.y){float a=amounts[i];float center=(r.x+r.y)*.5;vec2 q=uv;float s=styles[i];if(s<.5){q.x=center+(uv.x-center)*(1.-.56*a);c=mix(c,texture2D(now,q).rgb,min(1.,a*1.3));}else if(s<1.5){c=mix(c,texture2D(past,uv).rgb,min(.88,a));}else if(s<2.5){q.x=r.x+r.y-uv.x;c=mix(c,texture2D(now,q).rgb,.85*a);}else if(s<3.5){c=mix(c,texture2D(past,uv).rgb,.48*a);}else{float step=.012+.07*a;vec2 z=floor(uv/step)*step+step*.5;z.x=clamp(z.x,r.x+.0005,r.y-.0005);c=mix(c,mix(texture2D(now,z).rgb,vec3(.25),a*.7),a);} }}gl_FragColor=vec4(c,1);}`);
  program=gl.createProgram();gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
  gl.useProgram(program);const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);const loc=gl.getAttribLocation(program,'p');gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0);
  for(let i=0;i<2;i++){const tex=gl.createTexture();gl.activeTexture(gl.TEXTURE0+i);gl.bindTexture(gl.TEXTURE_2D,tex);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);textures.push(tex);gl.uniform1i(gl.getUniformLocation(program,i?'past':'now'),i);}
}else{canvas.hidden=true;$('status').textContent='This device uses the linear source picture fallback. Dialogue playback remains available.';}

function clearHistory(){history=[];nextCapture=0;priorShot=null;lastSourceTime=-1;}
function dimensions(){const box=stage.getBoundingClientRect();const scale=Math.min(box.width/16,box.height/9);canvas.style.width=scale*16+'px';canvas.style.height=scale*9+'px';canvas.style.left=(box.width-scale*16)/2+'px';canvas.style.top=(box.height-scale*9)/2+'px';canvas.style.right='auto';canvas.style.bottom='auto';canvas.width=Math.min(1280,Math.round(scale*16));canvas.height=Math.round(canvas.width*9/16);if(gl)gl.viewport(0,0,canvas.width,canvas.height);}
new ResizeObserver(dimensions).observe(stage);
function render(){
 if(video.readyState<2)return;
 const t=video.currentTime;const {shot,layout,state}=evaluate(config,t);const shotId=shot?.id??null;
 if(shotId!==priorShot||t<lastSourceTime||Math.abs(t-lastSourceTime)>.25){clearHistory();priorShot=shotId;}
 lastSourceTime=t;
 if(t>=nextCapture&&(!video.paused||!history.length)){captureCtx.drawImage(video,0,0,historyWidth,historyHeight);history.push(captureCtx.getImageData(0,0,historyWidth,historyHeight));if(history.length>maxHistory)history.shift();nextCapture=t+1/30;}
 const control=stateFromEvents(events,t);if(sessionLoaded){selected=control.selected;$('amount').value=control.amount;}
 const influence=selected?{selected,amount:Number($('amount').value)}:control;
 if(influence.selected){state[influence.selected]=Math.min(1,Math.max(state[influence.selected],influence.amount));}
 // Withdrawn attention leaves an authored, source-time residue that decays on replay.
 if(control.residue&&control.residue.person in state)state[control.residue.person]=Math.max(state[control.residue.person],control.residue.amount);
 if(reduced)for(const p in state)state[p]=Math.min(.12,state[p]);
 if(gl){
  gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,textures[0]);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,video);
  scratchCtx.putImageData(history[Math.max(0,history.length-19)]??captureCtx.getImageData(0,0,historyWidth,historyHeight),0,0);gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,textures[1]);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,scratch);
  const spans=[],amounts=[],styles=[];const order=['pressure','lag','refraction','residue','erosion'];
  for(const f of layout?.fields??config.layouts.A.fields){spans.push(...f.span);amounts.push(state[f.performer]);styles.push(order.indexOf(config.performers[f.performer].style));}
  gl.uniform2fv(gl.getUniformLocation(program,'spans[0]'),new Float32Array(spans));gl.uniform1fv(gl.getUniformLocation(program,'amounts[0]'),new Float32Array(amounts));gl.uniform1fv(gl.getUniformLocation(program,'styles[0]'),new Float32Array(styles));gl.uniform1f(gl.getUniformLocation(program,'neutral'),!shot||!layout?.registered||$('original').checked?1:0);gl.drawArrays(gl.TRIANGLES,0,6);
 }
 if(!$('seek').matches(':active'))$('seek').value=t;
 $('clock').textContent=`${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')}`;
 document.querySelectorAll('[data-person]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.person===selected)));
}
function loop(){render();requestAnimationFrame(loop);}loop();
function record(person,amount){sessionLoaded=false;const time=video.currentTime;events=events.filter(e=>Math.abs(e.source_time-time)>.02);events.push({source_time:time,selected:person,amount});events.sort((a,b)=>a.source_time-b.source_time);selected=person;$('status').textContent=person?`Attention: ${config.performers[person].description}. The recorded dialogue stays intact.`:'Attention released. The room keeps a diminishing trace.';}
async function play(){try{await video.play();$('play').textContent='Pause';$('welcome').hidden=true;}catch(e){$('status').textContent='Playback needs a tap. '+e.message;}}
$('start').onclick=play;$('play').onclick=()=>{if(video.paused)play();else video.pause();};
video.onpause=()=>{$('play').textContent='Play';};video.onended=()=>{$('play').textContent='Play';};
video.onloadedmetadata=()=>{$('seek').max=video.duration;dimensions();};video.onseeking=()=>{clearHistory();sessionLoaded=true;};
$('seek').oninput=e=>{video.currentTime=Number(e.target.value);};
document.querySelectorAll('[data-person]').forEach(b=>b.onclick=()=>record(b.dataset.person,Number($('amount').value)));
canvas.onclick=e=>{const r=canvas.getBoundingClientRect(),x=(e.clientX-r.left)/r.width;const layout=evaluate(config,video.currentTime).layout;const f=layout?.fields.find(f=>x>=f.span[0]&&x<f.span[1]);if(f)record(f.performer,Number($('amount').value));};
$('amount').oninput=()=>{if(selected)record(selected,Number($('amount').value));};
$('release').onclick=()=>record(null,0);$('reset').onclick=()=>{events=[];selected=null;sessionLoaded=false;video.currentTime=0;clearHistory();$('status').textContent='Initial authored score restored.';};
$('motion').onchange=()=>{reduced=$('motion').checked;};
$('controls').onclick=()=>{$('panel').hidden=!$('panel').hidden;$('controls').setAttribute('aria-expanded',String(!$('panel').hidden));};
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else if(stage.requestFullscreen)await stage.requestFullscreen();else{$('status').textContent='Full-viewport presentation is active. This browser does not expose element full screen.';}}catch(e){$('status').textContent='Full-viewport presentation remains active. '+e.message;}};
document.addEventListener('visibilitychange',()=>{if(document.hidden)video.pause();});
$('save').onclick=()=>{const data=makeSession(config,events,reduced);const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='god-here-attention-score.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('load').onchange=async e=>{try{const data=JSON.parse(await e.target.files[0].text());validateSession(data,config);events=data.events;sessionLoaded=true;reduced=data.reduced_motion;$('motion').checked=reduced;video.currentTime=0;clearHistory();$('status').textContent='Saved attention score loaded. Playback replays its source-time events.';}catch(err){$('status').textContent='Score could not be loaded: '+err.message;}};
video.onerror=()=>{$('status').textContent='Media could not load. Use the downloaded review package or the linear workprint.';};
// Optional agent controls use exactly the same state transitions as the visible controls.
if(document.modelContext?.registerTool){
 const lifecycle=new AbortController();
 const expose=tool=>{try{Promise.resolve(document.modelContext.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{});}catch{}};
 expose({name:'read_room_state',description:'Read current source time, playback and selected attention without changing the room.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true},execute:()=>({source_time:video.currentTime,paused:video.paused,selected,reduced_motion:reduced})});
 expose({name:'set_room_attention',description:'Select a recorded performer and author attention at the current source moment.',inputSchema:{type:'object',properties:{performer:{enum:['P01','P02','P03','P04','P05',null]},amount:{type:'number',minimum:0,maximum:1}},required:['performer','amount'],additionalProperties:false},annotations:{readOnlyHint:false},execute:input=>{if(!input||input.performer!==null&&!(input.performer in config.performers)||!Number.isFinite(input.amount)||input.amount<0||input.amount>1)throw Error('Invalid attention');$('amount').value=input.amount;record(input.performer,input.amount);render();return {source_time:video.currentTime,selected,amount:input.amount};}});
 addEventListener('pagehide',()=>lifecycle.abort(),{once:true});
}
