/* QualiMatch — eventos visuais da rodovia: chuva cíclica, radar e abordagem policial.
   É puramente decorativo: não interfere em dados, sincronização ou regras de negócio. */
(function(){
 if(window.__qmRoadEventsInstalled)return;
 window.__qmRoadEventsInstalled=true;

 const reduced=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 const style=document.createElement('style');
 style.id='qm-road-events-style';
 style.textContent=`
  .qm-rain-layer{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden;opacity:0;transition:opacity .8s ease;background:linear-gradient(180deg,rgba(68,82,104,.02),rgba(24,31,44,.08))}
  body.qm-raining .qm-rain-layer{opacity:1}
  .qm-rain-drop{position:absolute;top:-16vh;width:1px;height:18px;background:linear-gradient(180deg,transparent,rgba(190,216,242,.72));transform:rotate(12deg);animation:qm-rain-fall .72s linear infinite;will-change:transform}
  @keyframes qm-rain-fall{from{transform:translate3d(0,-18vh,0) rotate(12deg)}to{transform:translate3d(-52px,124vh,0) rotate(12deg)}}
  body.qm-raining:after{content:'';position:fixed;inset:0;z-index:0;pointer-events:none;background:linear-gradient(180deg,rgba(28,39,57,.07),transparent 48%)}
  body.qm-raining .road-scene .asphalt{box-shadow:inset 0 5px 10px rgba(140,175,210,.08);filter:brightness(.9)}

  .road-scene .qm-radar{position:absolute;left:58%;bottom:8px;width:20px;height:38px;z-index:4;pointer-events:none}
  .qm-radar-pole{position:absolute;left:9px;bottom:0;width:3px;height:27px;border-radius:2px;background:#777e8d;box-shadow:inset 1px 0 rgba(255,255,255,.18)}
  .qm-radar-box{position:absolute;left:3px;top:0;width:15px;height:15px;border-radius:3px;background:#d8dde5;border:1px solid #8e96a5;box-shadow:0 2px 4px #0006}
  .qm-radar-lens{position:absolute;width:6px;height:6px;border-radius:50%;left:4px;top:4px;background:#202634;border:1px solid #697284}
  .qm-radar-label{position:absolute;left:-2px;top:17px;font:700 5px/1 Arial,sans-serif;color:#cfd5df;letter-spacing:.2px;white-space:nowrap;text-shadow:0 1px 2px #000}
  .road-scene .qm-radar.flash .qm-radar-lens{background:#ff3e4e;box-shadow:0 0 7px 2px rgba(255,62,78,.72)}

  .road-scene .qm-police-car{position:absolute;left:-100px;bottom:8px;width:68px;height:29px;z-index:7;filter:drop-shadow(0 3px 6px #000a);opacity:0;transition:left .9s cubic-bezier(.2,.75,.25,1),bottom .45s ease,opacity .18s ease}
  .road-scene .qm-police-car.visible{opacity:1}
  .qm-police-car .pc-body{position:absolute;left:3px;right:3px;bottom:4px;height:13px;border-radius:7px 9px 4px 4px;background:#f0f3f7;border:1px solid #aeb5c1}
  .qm-police-car .pc-cabin{position:absolute;left:20px;bottom:16px;width:29px;height:9px;border-radius:7px 8px 1px 1px;background:#e8edf3;border:1px solid #aeb5c1}
  .qm-police-car .pc-window{position:absolute;left:24px;bottom:18px;width:20px;height:5px;border-radius:4px 5px 1px 1px;background:#273345}
  .qm-police-car .pc-stripe{position:absolute;left:6px;right:6px;bottom:9px;height:4px;background:#263d71}
  .qm-police-car .pc-wheel{position:absolute;bottom:0;width:8px;height:8px;border-radius:50%;background:#151820;border:2px solid #555c68}
  .qm-police-car .pc-wheel.w1{left:13px}.qm-police-car .pc-wheel.w2{right:12px}
  .qm-police-car .pc-lightbar{position:absolute;left:27px;bottom:25px;width:16px;height:4px;border-radius:2px;background:linear-gradient(90deg,#e83845 0 49%,#4a76ea 51% 100%)}
  .qm-police-car.siren .pc-lightbar{animation:qm-siren .18s steps(1) infinite}
  @keyframes qm-siren{0%,49%{box-shadow:-5px 0 8px rgba(255,43,60,.75),5px 0 3px rgba(65,112,255,.15)}50%,100%{box-shadow:-5px 0 3px rgba(255,43,60,.15),5px 0 8px rgba(65,112,255,.8)}}
  .qm-police-car .pc-word{position:absolute;left:19px;bottom:8px;color:#fff;font:800 4px/1 Arial,sans-serif;letter-spacing:.45px;z-index:2}

  .road-scene .car.qm-speeding{filter:drop-shadow(0 3px 6px #000a) drop-shadow(-12px 0 7px rgba(190,210,255,.22))}
  .road-scene .car.qm-pulled-over{bottom:26px!important;transition:bottom .45s ease,filter .25s ease;filter:drop-shadow(0 3px 6px #000a)}
  .road-scene .car.qm-opposite-exit{bottom:26px!important;transition:none!important;filter:drop-shadow(0 3px 6px #000a)}
  .road-scene .qm-police-car.qm-opposite-exit{bottom:25px!important}
  .road-scene .qm-ticket{position:absolute;z-index:9;bottom:54px;padding:3px 6px;border-radius:5px;background:#f3bf67;color:#2b2110;font:900 7px/1 Arial,sans-serif;letter-spacing:.25px;box-shadow:0 2px 8px #0007;opacity:0;transform:translateY(4px);transition:opacity .22s ease,transform .22s ease;pointer-events:none}
  .road-scene .qm-ticket.show{opacity:1;transform:translateY(0)}

  @media(max-width:820px){.road-scene .qm-radar{left:56%;transform:scale(.8);transform-origin:bottom center}.road-scene .qm-police-car{width:55px}.road-scene .car.qm-pulled-over,.road-scene .car.qm-opposite-exit{bottom:22px!important}.road-scene .qm-police-car.qm-opposite-exit{bottom:22px!important}}
  @media(prefers-reduced-motion:reduce){.qm-rain-drop{animation:none}.qm-police-car{display:none!important}.qm-radar{opacity:.72}}
 `;
 document.head.appendChild(style);

 function createRain(){
  if(document.querySelector('.qm-rain-layer'))return;
  const layer=document.createElement('div');layer.className='qm-rain-layer';layer.setAttribute('aria-hidden','true');
  const count=58;
  for(let i=0;i<count;i++){
   const d=document.createElement('i');d.className='qm-rain-drop';
   d.style.left=((i*37)%103)+'%';
   d.style.animationDelay=(-(i%17)*.11)+'s';
   d.style.animationDuration=(.56+(i%9)*.045)+'s';
   d.style.opacity=String(.32+(i%6)*.09);
   layer.appendChild(d);
  }
  document.body.appendChild(layer);
 }

 let raining=false;
 function toggleRain(){
  raining=!raining;
  document.body.classList.toggle('qm-raining',raining);
 }

 function createRoadProps(){
  const road=document.querySelector('.road-scene');if(!road)return null;
  let radar=road.querySelector('.qm-radar');
  if(!radar){
   radar=document.createElement('div');radar.className='qm-radar';radar.setAttribute('aria-hidden','true');
   radar.innerHTML='<div class="qm-radar-pole"></div><div class="qm-radar-box"><span class="qm-radar-lens"></span></div><span class="qm-radar-label">60</span>';
   road.appendChild(radar);
  }
  let police=road.querySelector('.qm-police-car');
  if(!police){
   police=document.createElement('div');police.className='qm-police-car';police.setAttribute('aria-hidden','true');
   police.innerHTML='<div class="pc-body"></div><div class="pc-cabin"></div><div class="pc-window"></div><div class="pc-stripe"></div><div class="pc-lightbar"></div><div class="pc-wheel w1"></div><div class="pc-wheel w2"></div><span class="pc-word">PRF</span>';
   road.appendChild(police);
  }
  let ticket=road.querySelector('.qm-ticket');
  if(!ticket){ticket=document.createElement('div');ticket.className='qm-ticket';ticket.textContent='MULTA';road.appendChild(ticket)}
  return {road,radar,police,ticket};
 }

 function radarX(radar){const r=radar.getBoundingClientRect();return r.left+r.width/2}
 function flashRadar(radar){radar.classList.add('flash');setTimeout(()=>radar.classList.remove('flash'),260)}

 function setupEnforcement(){
  if(reduced)return;
  const props=createRoadProps();if(!props)return;
  const {radar,police,ticket}=props;
  let car=null,baseSpeed=0,lastX=null,evaluated=false,speeding=false,eventRunning=false;

  function findCar(){
   const vehicles=window.__qmRoadVehicles||[];
   const found=vehicles.find(v=>v&&v.el&&v.el.classList.contains('car'));
   if(found&&found!==car){car=found;baseSpeed=Number(found.speed||1);lastX=found.x;}
   return car;
  }

  function removeFromTraffic(v){
   const list=window.__qmRoadVehicles||[];const idx=list.indexOf(v);if(idx>=0)list.splice(idx,1);
  }
  function restoreToTraffic(v){
   const list=window.__qmRoadVehicles||[];if(!list.includes(v))list.push(v);
  }

  function animateOppositeLane(v,fromX,toX,duration,done){
   const started=performance.now();
   function step(now){
    const p=Math.min(1,(now-started)/duration);
    const eased=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;
    const x=fromX+(toX-fromX)*eased;
    v.x=x;
    // scaleX(-1) faz o carro realmente apontar para a direção contrária enquanto
    // percorre a segunda faixa, em vez de simplesmente desaparecer da cena.
    v.el.style.transform='translateX('+x.toFixed(1)+'px) scaleX(-1)';
    if(p<1)requestAnimationFrame(step);else if(done)done();
   }
   requestAnimationFrame(step);
  }

  function leaveByOppositeLane(v,stopX){
   ticket.classList.remove('show');
   police.classList.remove('siren');
   v.el.classList.add('qm-opposite-exit');
   police.classList.add('qm-opposite-exit');

   // Os dois fazem a saída pela faixa superior, como uma pista de mão dupla.
   // A viatura mantém distância atrás do carro e ambos dirigem até fora da tela.
   const carTarget=-(Number(v.width||66)+120);
   police.style.transition='left 2.6s cubic-bezier(.35,.05,.55,1),bottom .35s ease,opacity .18s ease';
   police.style.bottom=window.innerWidth<=820?'22px':'25px';
   police.style.transform='scaleX(-1)';
   police.style.left=Math.max(8,stopX-78)+'px';
   requestAnimationFrame(()=>requestAnimationFrame(()=>{police.style.left='-115px'}));

   animateOppositeLane(v,stopX,carTarget,2600,()=>{
    // Só depois que os dois realmente saíram da tela o carro volta ao ciclo normal.
    // Ele reaparece mais tarde pela entrada esquerda, novamente na faixa principal.
    v.el.classList.remove('qm-pulled-over','qm-opposite-exit');
    v.x=-(Number(v.width||66)+180);
    v.el.style.transform='translateX('+v.x.toFixed(1)+'px)';
    v.paused=false;v.speed=baseSpeed;restoreToTraffic(v);

    police.classList.remove('visible','qm-opposite-exit');
    police.style.transition='';police.style.transform='';police.style.left='-100px';police.style.bottom='8px';
    eventRunning=false;evaluated=false;speeding=false;lastX=v.x;
   });
  }

  function policeEvent(v){
   if(eventRunning)return;eventRunning=true;speeding=false;
   v.speed=baseSpeed;v.el.classList.remove('qm-speeding');flashRadar(radar);

   // Dá um pequeno avanço depois do radar e então conduz o veículo para a faixa ao lado.
   setTimeout(()=>{
    if(!v||!v.el){eventRunning=false;return}
    removeFromTraffic(v);v.paused=true;
    v.el.classList.add('qm-pulled-over');
    const stopX=Math.min(window.innerWidth-170,Math.max(radarX(radar)+95,v.x));
    v.x=stopX;v.el.style.transform='translateX('+stopX.toFixed(1)+'px)';

    police.classList.add('visible','siren');
    police.style.transform='';police.style.transition='left .9s cubic-bezier(.2,.75,.25,1),bottom .45s ease,opacity .18s ease';
    police.style.bottom='8px';police.style.left=Math.max(-90,stopX-260)+'px';
    requestAnimationFrame(()=>requestAnimationFrame(()=>{police.style.left=Math.max(8,stopX-78)+'px'}));

    setTimeout(()=>{
     police.style.bottom=window.innerWidth<=820?'22px':'25px';
     ticket.style.left=Math.max(8,stopX+18)+'px';ticket.classList.add('show');
    },950);

    // Depois da multa ninguém é "teletransportado": carro e viatura saem juntos
    // pela faixa oposta, dirigindo em sentido contrário, e só então o fluxo reinicia.
    setTimeout(()=>leaveByOppositeLane(v,stopX),6200);
   },650);
  }

  function frame(){
   const v=findCar();
   if(v&&!eventRunning){
    const x=Number(v.x||0),rx=radarX(radar);
    if(lastX!==null&&x<lastX-180){
     // O carro reapareceu no início da rodovia: começa uma nova passagem pelo radar.
     evaluated=false;speeding=false;v.speed=baseSpeed;v.el.classList.remove('qm-speeding');
    }
    if(!evaluated&&x>rx-230&&x<rx-80){
     evaluated=true;
     // Em uma de cada cinco passagens, o carro acelera acima do limite antes do radar.
     speeding=Math.random()<0.20;
     if(speeding){v.speed=baseSpeed*1.9;v.el.classList.add('qm-speeding')}
    }
    if(speeding&&x>=rx){policeEvent(v)}
    lastX=x;
   }
   requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
 }

 function init(){
  createRain();createRoadProps();
  if(!reduced)setInterval(toggleRain,25000); // 25 s seco, 25 s chuva, repetindo.
  setupEnforcement();
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
