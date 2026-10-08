(() => {
  'use strict';
  const $=id=>document.getElementById(id),video=$('film'),screen=$('screen');
  const links=[...document.querySelectorAll('[data-video]')];
  const orientation=matchMedia('(orientation: portrait)');
  let selected=links.find(a=>a.dataset.id===new URLSearchParams(location.search).get('clip'))||links[0];
  let generation=0,playIntent=false;
  const movie=a=>a.dataset.video+(orientation.matches?'-portrait':'')+'.mp4';
  const src=a=>'assets/renders/'+movie(a);
  const say=t=>$('play-status').textContent=t;
  function updateLinks(){
    for(const a of links){a.href=src(a);a.setAttribute('aria-current',String(a===selected));}
    $('direct').href=src(selected);$('download').href=src(selected);
    $('download').download=movie(selected);$('edit').href=selected.dataset.edit||'./';
    $('reel').href='assets/renders/god-here-13-processors-'+(orientation.matches?'portrait':'landscape')+'.mp4';
  }
  function requestPlay(token=generation){
    playIntent=true;$('play').textContent='Cancel';say('Starting picture and sound…');
    if(video.error)video.load();
    const playing=video.play();
    if(playing&&playing.catch)playing.catch(error=>{
      if(token!==generation||!playIntent||error.name==='AbortError')return;
      playIntent=false;$('play').textContent='Play';
      say('Tap the video’s play button, or open the video directly below.');
    });
  }
  function choose(link,{autoplay=false,at=0}={}){
    selected=link;generation++;playIntent=false;video.pause();
    updateLinks();$('title').textContent=link.dataset.name;
    $('sequence').hidden=link.dataset.kind!=='demo';
    const token=generation;
    video.src=src(link);video.load();
    if(at>0)video.addEventListener('loadedmetadata',()=>{
      if(generation===token&&Number.isFinite(video.duration))video.currentTime=Math.min(at,Math.max(0,video.duration-.01));
    },{once:true});
    $('play').textContent='Play';say('Tap Play for picture and sound.');
    const url=new URL(location.href);url.searchParams.set('clip',link.dataset.id);history.replaceState(null,'',url);
    if(autoplay)requestPlay(token);
  }
  $('play').onclick=()=>{if(playIntent||!video.paused){playIntent=false;video.pause();$('play').textContent='Play';say('Paused.');}else requestPlay();};
  $('restart').onclick=()=>{video.currentTime=0;requestPlay();};
  $('loop').onchange=()=>{video.loop=$('loop').checked;};
  video.addEventListener('playing',()=>{playIntent=true;$('play').textContent='Pause';say('Playing '+selected.dataset.name+'.');});
  video.addEventListener('pause',()=>{if(!playIntent||video.readyState>=2){playIntent=false;$('play').textContent='Play';}});
  video.addEventListener('ended',()=>{playIntent=false;$('play').textContent='Play';say('Finished. Choose another processor or play again.');});
  video.addEventListener('error',()=>{playIntent=false;$('play').textContent='Play';say('The video did not load. Tap Play to retry, or open the video directly below.');});
  for(const a of links)a.onclick=e=>{if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;e.preventDefault();choose(a,{autoplay:true});};
  function updateOrientation(){const at=video.currentTime||0,resume=!video.paused||playIntent;choose(selected,{autoplay:resume,at});}
  if(orientation.addEventListener)orientation.addEventListener('change',updateOrientation);else orientation.addListener(updateOrientation);
  async function full(){
    screen.classList.add('expanded');document.body.classList.add('fullscreen');$('exit-full').hidden=false;
    try{if(screen.requestFullscreen&&!document.fullscreenElement)await screen.requestFullscreen();}catch{}
  }
  async function exit(){
    screen.classList.remove('expanded');document.body.classList.remove('fullscreen');$('exit-full').hidden=true;
    if(document.fullscreenElement)try{await document.exitFullscreen();}catch{}
  }
  $('full').onclick=full;$('exit-full').onclick=exit;
  document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement&&screen.classList.contains('expanded'))exit();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')exit();});
  choose(selected);
})();
