/* Ajuste visual do tema: remove o brilho roxo da paisagem e mostra fases reais da lua. */
(function(){
 const phases=[
  ['new','Lua nova'],
  ['waxing-crescent','Lua crescente'],
  ['first-quarter','Quarto crescente'],
  ['waxing-gibbous','Gibosa crescente'],
  ['full','Lua cheia'],
  ['waning-gibbous','Gibosa minguante'],
  ['last-quarter','Quarto minguante'],
  ['waning-crescent','Lua minguante']
 ];

 const style=document.createElement('style');
 style.id='qm-theme-phase-patch-style';
 style.textContent=`
  /* Remove a antiga luz roxa posicionada sobre as montanhas. */
  .road-scene .sun{display:none!important}

  /* A lua deixa de ser emoji/brilho e vira um disco com fase desenhada. */
  .qm-moon{
   width:68px!important;height:68px!important;font-size:0!important;line-height:0!important;
   border-radius:50%!important;filter:none!important;box-shadow:none!important;
   overflow:hidden;background:#d9d9d2!important;border:1px solid rgba(255,255,255,.16)!important;
  }
  .qm-moon::before{content:'';position:absolute;inset:0;border-radius:50%;pointer-events:none}
  .qm-moon.qm-phase-new{background:#12131c!important;border-color:rgba(223,226,235,.18)!important}
  .qm-moon.qm-phase-new::before{background:transparent}

  /* crescente: parte clara à direita */
  .qm-moon.qm-phase-waxing-crescent{background:#d9d9d2!important}
  .qm-moon.qm-phase-waxing-crescent::before{background:#11121b;width:64px;height:68px;left:-5px;top:0;border-radius:50%}

  .qm-moon.qm-phase-first-quarter{background:linear-gradient(90deg,#11121b 0 50%,#d9d9d2 50% 100%)!important}
  .qm-moon.qm-phase-first-quarter::before{background:transparent}

  .qm-moon.qm-phase-waxing-gibbous{background:#d9d9d2!important}
  .qm-moon.qm-phase-waxing-gibbous::before{background:#11121b;width:34px;height:68px;left:-17px;top:0;border-radius:50%}

  .qm-moon.qm-phase-full{background:#d9d9d2!important}
  .qm-moon.qm-phase-full::before{background:radial-gradient(circle at 36% 35%,rgba(105,107,108,.16) 0 4px,transparent 5px),radial-gradient(circle at 64% 58%,rgba(105,107,108,.12) 0 6px,transparent 7px)}

  .qm-moon.qm-phase-waning-gibbous{background:#d9d9d2!important}
  .qm-moon.qm-phase-waning-gibbous::before{background:#11121b;width:34px;height:68px;right:-17px;left:auto;top:0;border-radius:50%}

  .qm-moon.qm-phase-last-quarter{background:linear-gradient(90deg,#d9d9d2 0 50%,#11121b 50% 100%)!important}
  .qm-moon.qm-phase-last-quarter::before{background:transparent}

  /* minguante: parte clara à esquerda */
  .qm-moon.qm-phase-waning-crescent{background:#d9d9d2!important}
  .qm-moon.qm-phase-waning-crescent::before{background:#11121b;width:64px;height:68px;right:-5px;left:auto;top:0;border-radius:50%}

  body[data-qm-theme='dark'] .qm-moon{opacity:.88!important;transform:translateY(0) scale(1)!important}
  body[data-qm-theme='light'] .qm-moon{opacity:0!important}
  @media(max-width:820px){.qm-moon{width:52px!important;height:52px!important}.qm-moon::before{height:52px!important}}
 `;
 document.head.appendChild(style);

 function phaseIndex(){return Math.floor(Date.now()/60000)%phases.length}
 function applyPhase(){
  const moon=document.querySelector('#qm-moon-phase');
  if(!moon)return;
  const idx=phaseIndex();
  const [key,name]=phases[idx];
  const cls='qm-phase-'+key;
  phases.forEach(([p])=>moon.classList.remove('qm-phase-'+p));
  moon.classList.add(cls);
  if(moon.textContent)moon.textContent='';
  moon.dataset.phase=String(idx);
  moon.dataset.phaseName=name;
  moon.title=`${name} • muda de fase a cada 1 minuto`;
 }

 function init(){
  applyPhase();
  const moon=document.querySelector('#qm-moon-phase');
  if(moon){
   const observer=new MutationObserver(()=>{if(moon.textContent)moon.textContent='';applyPhase()});
   observer.observe(moon,{childList:true,characterData:true,subtree:true});
  }
  let last=phaseIndex();
  setInterval(()=>{const now=phaseIndex();if(now!==last){last=now;applyPhase()}else if(document.querySelector('#qm-moon-phase')?.textContent)applyPhase()},1000);
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
