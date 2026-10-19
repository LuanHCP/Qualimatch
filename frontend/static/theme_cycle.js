/* QualiMatch — alternância Claro/Escuro + ciclo visual da lua.
   Não altera dados nem regras do sistema; atua somente no frontend. */
(function(){
 const THEME_KEY='qualimatch-theme';
 const phases=[
  ['🌑','Lua nova'],['🌒','Lua crescente'],['🌓','Quarto crescente'],['🌔','Gibosa crescente'],
  ['🌕','Lua cheia'],['🌖','Gibosa minguante'],['🌗','Quarto minguante'],['🌘','Lua minguante']
 ];

 const style=document.createElement('style');
 style.id='qm-theme-cycle-style';
 style.textContent=`
  html,body,.sidebar,.card,.panel,.source-card,.source-info,.detail-field,.phase-card,.phase-metric,
  .portal-card,.auth-card,.modal-card,input,select,button,th,td{transition:background-color .28s ease,border-color .28s ease,color .28s ease,box-shadow .28s ease,filter .28s ease}

  .qm-theme-toggle{display:inline-flex;align-items:center;gap:7px;white-space:nowrap;border-radius:999px!important;padding:8px 12px!important;font-weight:800}
  .qm-theme-toggle .qm-theme-icon{font-size:15px;line-height:1}
  .auth-card>.qm-theme-toggle{position:absolute;right:16px;top:16px;z-index:4}

  .qm-celestial-layer{position:fixed;inset:0;pointer-events:none;overflow:hidden;z-index:0}
  #app-layout,#portal-shell,#auth-shell{position:relative;z-index:1}
  .qm-moon{position:absolute;right:8vw;top:11vh;width:86px;height:86px;display:grid;place-items:center;font-size:72px;line-height:1;filter:drop-shadow(0 0 18px rgba(205,214,255,.26));opacity:0;transform:translateY(10px) scale(.94);transition:opacity .55s ease,transform .55s ease,filter .35s ease}
  .qm-sun-orb{position:absolute;right:9vw;top:4.5vh;width:74px;height:74px;border-radius:50%;opacity:0;transform:translateY(18px) scale(.9);transition:opacity .55s ease,transform .55s ease;box-shadow:0 0 28px rgba(255,199,84,.55),0 0 70px rgba(255,188,65,.22);background:radial-gradient(circle at 36% 32%,#fff7bf 0 18%,#ffd86a 38%,#f3ad35 72%,#e98d2c 100%)}
  .qm-sun-orb:before,.qm-sun-orb:after{content:'';position:absolute;inset:-20px;border-radius:50%;border:2px dashed rgba(255,192,61,.28);animation:qmSunSpin 18s linear infinite}
  .qm-sun-orb:after{inset:-34px;border-color:rgba(255,192,61,.14);animation-duration:28s;animation-direction:reverse}
  @keyframes qmSunSpin{to{transform:rotate(360deg)}}
  .qm-stars{position:absolute;inset:0;opacity:0;transition:opacity .45s ease}
  .qm-star{position:absolute;width:2px;height:2px;background:#fff;border-radius:50%;box-shadow:0 0 7px rgba(255,255,255,.7);animation:qmTwinkle 2.8s ease-in-out infinite alternate}
  @keyframes qmTwinkle{from{opacity:.25;transform:scale(.7)}to{opacity:1;transform:scale(1.45)}}

  body[data-qm-theme='dark'] .qm-moon{opacity:.88;transform:translateY(0) scale(1)}
  body[data-qm-theme='dark'] .qm-stars{opacity:.62}
  body[data-qm-theme='dark'] .qm-sun-orb{opacity:0}
  body[data-qm-theme='dark'] .sky-scene .sun{opacity:.08!important;filter:saturate(.55) brightness(.55)}

  body[data-qm-theme='light']{
   --bg:#eef4fb;--bg2:#f5f8fc;--panel:#ffffff;--panel2:#f5f7fb;--line:#d5ddea;--line2:#c6d0df;
   --text:#182033;--muted:#5f6980;--muted2:#7c8699;--purple:#7a50e8;--purple2:#6340c6;--purple3:#ece6ff;
   --ok:#168f68;--warn:#a96b09;--bad:#cf4656;--cyan:#2183aa;
   background:linear-gradient(180deg,#a9d8ff 0,#dff0ff 22%,#f5f8fc 48%,#eef4fb 100%)!important;color:var(--text)!important
  }
  body[data-qm-theme='light'] .qm-sun-orb{opacity:.98;transform:translateY(0) scale(1)}
  body[data-qm-theme='light'] .qm-moon,body[data-qm-theme='light'] .qm-stars{opacity:0}
  body[data-qm-theme='light'] .sky-scene{filter:brightness(1.14) saturate(.92)}
  body[data-qm-theme='light'] .sky-scene .sun{opacity:0!important}
  body[data-qm-theme='light'] .road-scene{filter:brightness(1.18) saturate(.82)}
  body[data-qm-theme='light'] .forest-scene{filter:brightness(1.18) saturate(.82);opacity:.65}

  body[data-qm-theme='light'] .sidebar{background:rgba(248,251,255,.93)!important;border-right-color:#d4ddea!important;box-shadow:10px 0 30px rgba(62,88,120,.06)}
  body[data-qm-theme='light'] nav button{color:#465066!important}
  body[data-qm-theme='light'] nav button:hover,body[data-qm-theme='light'] nav button.active{background:#ece7fb!important;color:#241846!important}
  body[data-qm-theme='light'] nav button.active span{color:#6944cf!important}
  body[data-qm-theme='light'] .card,body[data-qm-theme='light'] .panel,
  body[data-qm-theme='light'] .source-card,body[data-qm-theme='light'] .auth-card,
  body[data-qm-theme='light'] .portal-card,body[data-qm-theme='light'] .modal-card{
   background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(247,250,255,.96))!important;border-color:#d3dbea!important;box-shadow:0 10px 28px rgba(62,88,120,.09)!important
  }
  body[data-qm-theme='light'] .source-info,body[data-qm-theme='light'] .detail-field,
  body[data-qm-theme='light'] .phase-card,body[data-qm-theme='light'] .phase-metric,
  body[data-qm-theme='light'] .mini-grid div,body[data-qm-theme='light'] .summary-chip,
  body[data-qm-theme='light'] .doc-item{background:#f6f9fd!important;border-color:#d8e0eb!important}
  body[data-qm-theme='light'] input,body[data-qm-theme='light'] select{background:#fff!important;color:#1d2739!important;border-color:#cfd8e6!important}
  body[data-qm-theme='light'] button{color:#27324a}
  body[data-qm-theme='light'] .primary{color:white!important}
  body[data-qm-theme='light'] .ghost,body[data-qm-theme='light'] .file-btn{background:#f2f5fa!important;color:#33405a!important;border-color:#d2dbe8!important}
  body[data-qm-theme='light'] th{background:#edf2f8!important;color:#58647b!important}
  body[data-qm-theme='light'] td{color:#273148}
  body[data-qm-theme='light'] tbody tr:hover{background:#f0f4fb!important}
  body[data-qm-theme='light'] .metric-trend span,body[data-qm-theme='light'] .hint,body[data-qm-theme='light'] .meta,
  body[data-qm-theme='light'] header p,body[data-qm-theme='light'] .panel p{color:#69758b!important}
  body[data-qm-theme='light'] .modal-backdrop{background:rgba(88,110,142,.36)!important;backdrop-filter:blur(5px)}
  body[data-qm-theme='light'] #toast{background:#fff!important;color:#26334a!important;border-color:#cbd5e3!important;box-shadow:0 12px 30px rgba(58,76,104,.18)}
  body[data-qm-theme='light'] .pie-hole{background:#f7f9fd!important;border-color:#d7deea!important}
  body[data-qm-theme='light'] .bar-track{background:#e1e6ef!important}
  body[data-qm-theme='light'] .portal-topbar{background:rgba(247,250,255,.78)!important;border-color:#d6deea!important}

  @media(max-width:820px){
   .qm-moon{right:5vw;top:8vh;width:62px;height:62px;font-size:52px}
   .qm-sun-orb{right:6vw;top:3vh;width:56px;height:56px}
   .qm-theme-toggle .qm-theme-label{display:none}
  }
 `;
 document.head.appendChild(style);

 function createScene(){
  if(document.querySelector('.qm-celestial-layer'))return;
  const layer=document.createElement('div');
  layer.className='qm-celestial-layer';
  layer.setAttribute('aria-hidden','true');
  const stars=document.createElement('div');
  stars.className='qm-stars';
  for(let i=0;i<34;i++){
   const s=document.createElement('i');s.className='qm-star';
   s.style.left=`${3+((i*37)%94)}%`;s.style.top=`${2+((i*53)%42)}%`;
   s.style.animationDelay=`${(i%9)*.23}s`;s.style.animationDuration=`${2.1+(i%7)*.28}s`;
   stars.appendChild(s);
  }
  const sun=document.createElement('div');sun.className='qm-sun-orb';
  const moon=document.createElement('div');moon.className='qm-moon';moon.id='qm-moon-phase';
  layer.append(stars,sun,moon);document.body.appendChild(layer);
 }

 function phaseIndex(){return Math.floor(Date.now()/60000)%phases.length}
 function updateMoon(){
  const moon=document.querySelector('#qm-moon-phase');if(!moon)return;
  const idx=phaseIndex(),[icon,name]=phases[idx];
  if(moon.textContent!==icon)moon.textContent=icon;
  const title=`${name} • muda visualmente a cada 1 minuto`;
  if(moon.title!==title)moon.title=title;
  moon.dataset.phase=String(idx);
 }

 function setButtonState(theme){
  const nextIcon=theme==='light'?'🌙':'☀️';
  const nextLabel=theme==='light'?'Tema escuro':'Tema claro';
  const nextTitle=theme==='light'?'Mudar para tema escuro':'Mudar para tema claro';
  document.querySelectorAll('.qm-theme-toggle').forEach(btn=>{
   const icon=btn.querySelector('.qm-theme-icon'),label=btn.querySelector('.qm-theme-label');
   if(icon&&icon.textContent!==nextIcon)icon.textContent=nextIcon;
   if(label&&label.textContent!==nextLabel)label.textContent=nextLabel;
   if(btn.title!==nextTitle)btn.title=nextTitle;
   if(btn.getAttribute('aria-label')!==nextTitle)btn.setAttribute('aria-label',nextTitle);
  });
 }
 function applyTheme(theme,persist=true){
  const chosen=theme==='light'?'light':'dark';
  document.body.dataset.qmTheme=chosen;
  document.documentElement.dataset.qmTheme=chosen;
  if(persist){try{localStorage.setItem(THEME_KEY,chosen)}catch{}}
  setButtonState(chosen);updateMoon();
 }
 function toggleTheme(){applyTheme(document.body.dataset.qmTheme==='light'?'dark':'light')}

 function makeButton(){
  const b=document.createElement('button');b.type='button';b.className='ghost compact qm-theme-toggle';
  b.innerHTML='<span class="qm-theme-icon"></span><span class="qm-theme-label"></span>';
  b.addEventListener('click',toggleTheme);return b;
 }
 function installButtons(){
  const header=document.querySelector('.header-actions');
  if(header&&!header.querySelector('.qm-theme-toggle'))header.insertBefore(makeButton(),header.firstChild);
  const portal=document.querySelector('.portal-userbar');
  if(portal&&!portal.querySelector('.qm-theme-toggle'))portal.insertBefore(makeButton(),portal.querySelector('#portal-logout-btn'));
  const auth=document.querySelector('.auth-card');
  if(auth&&!auth.querySelector(':scope > .qm-theme-toggle'))auth.appendChild(makeButton());
  setButtonState(document.body.dataset.qmTheme||'dark');
 }

 function init(){
  createScene();installButtons();
  let saved='dark';try{saved=localStorage.getItem(THEME_KEY)||'dark'}catch{}
  applyTheme(saved,false);updateMoon();
  setInterval(updateMoon,60000);
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
