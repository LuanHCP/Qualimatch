/* Compatibilidade de texto de validação legado: Subconjunto dos certificados acima */
/* Compatibilidade de texto legado: Fonte: coluna <b>Entrega</b> da d.KIT */
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
/* v3.9.7 — carro, caminhão e rolo compactador cruzam a pista com velocidades diferentes,
   controlados via JS (requestAnimationFrame) em vez de @keyframes CSS soltos: assim dá
   para impedir que um ultrapasse/atravesse o outro (nunca ficam sobrepostos — o de trás
   sempre respeita uma distância mínima do que está à frente, como uma fila de trânsito
   real) e também dá para travar todos na catraca (window.__qmGate) quando ela está
   fechada/emperrada. window.__qmRoadVehicles fica exposto para o tollGateController. */
(function driveRoadVehicles(){
 if(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 const W=window.innerWidth||1280;
 const specs=[
  {sel:'.road-scene .car',    span:W+90},
  {sel:'.road-scene .truck',  span:W+110},
  {sel:'.road-scene .roller', span:W+70}
 ];
 const durations={'.road-scene .car':17,'.road-scene .truck':23,'.road-scene .roller':29};
 const vehicles=specs.map(s=>{
  const el=$(s.sel);if(!el)return null;
  const width=el.getBoundingClientRect().width||60;
  return {el,width,speed:s.span/durations[s.sel],x:-(width+Math.random()*W*1.3),paused:false};
 }).filter(Boolean);
 if(!vehicles.length)return;
 window.__qmRoadVehicles=vehicles;
 const MIN_GAP=16;
 let last=null;
 function frame(now){
  if(document.hidden||$('#app-layout')?.classList.contains('auth-hidden')){last=now;requestAnimationFrame(frame);return}
  if(last===null)last=now;
  if(now-last<32){requestAnimationFrame(frame);return}
  const dt=Math.min(.05,(now-last)/1000);last=now;
  const order=[...vehicles].sort((a,b)=>(b.x+b.width)-(a.x+a.width));
  const gate=window.__qmGate;
  for(let i=0;i<order.length;i++){
   const v=order[i];
   if(v.paused)continue;
   let nextX=v.x+v.speed*dt;
   if(i>0){
    const leader=order[i-1];
    const maxX=leader.x-MIN_GAP-v.width;
    if(nextX>maxX)nextX=Math.max(maxX,v.x);
   }
   if(gate&&gate.blocking&&v.x<=gate.x-v.width){
    const gateMax=gate.x-v.width;
    if(nextX>gateMax)nextX=Math.max(gateMax,v.x);
   }
   v.x=nextX;
   if(v.x>window.innerWidth+v.width+20)v.x=-(v.width+Math.random()*260);
   v.el.style.transform='translateX('+v.x.toFixed(1)+'px)';
  }
  requestAnimationFrame(frame);
 }
 requestAnimationFrame(frame);
})();
/* v3.9.7 — a catraca fica fechada por padrão e abre de verdade quando um veículo se
   aproxima (deixando ele passar), fechando de novo assim que ele (e quem vier logo
   atrás) já tiver atravessado — em vez de abrir/fechar num ciclo solto sem relação
   com os carros. Com 1 em ~10 chance, em vez de abrir ela emperra: um funcionário sai
   da cabaninha ao fundo, desce os 3 degraus, resolve em ~5s e ela volta a funcionar.
   Os veículos ficam parados na fila (sem se sobrepor) nesse meio tempo. */
(function tollGateController(){
 if(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 const bar=$('.road-scene .toll-bar'),worker=$('.road-scene .toll-worker'),toll=$('.road-scene .toll');
 if(!bar||!toll)return;
 function gateX(){const r=bar.getBoundingClientRect();return r.left+2}
 window.__qmGate={x:gateX(),blocking:true};
 window.addEventListener('resize',()=>{window.__qmGate.x=gateX()});
 const APPROACH=95,CLEAR=52,WALK=1100,FIX=5000,MIN_OPEN=650;
 let state='closed',openedAt=0;
 function nearGate(v){const g=window.__qmGate;return v.x<g.x+CLEAR && v.x+v.width>g.x-APPROACH}
 function anyNear(){return (window.__qmRoadVehicles||[]).some(nearGate)}
 function triggerJam(){
  state='jammed';
  window.__qmGate.blocking=true;
  bar.classList.remove('open');bar.classList.add('jam');
  if(worker)worker.classList.add('out');
  setTimeout(()=>{if(worker)worker.classList.add('fixing')},WALK);
  setTimeout(()=>{
   if(worker){worker.classList.remove('fixing');worker.classList.remove('out');worker.classList.add('back');}
   bar.classList.remove('jam');
   state='closed';
  },WALK+FIX);
  setTimeout(()=>{if(worker)worker.classList.remove('back')},WALK+FIX+WALK);
 }
 function frame(){
  if(document.hidden||$('#app-layout')?.classList.contains('auth-hidden')){requestAnimationFrame(frame);return}
  if(state==='closed'&&anyNear()){
   if(Math.random()<0.1){triggerJam()}
   else{state='open';openedAt=performance.now();window.__qmGate.blocking=false;bar.classList.add('open')}
  }else if(state==='open'){
   if(!anyNear()&&performance.now()-openedAt>MIN_OPEN){state='closed';window.__qmGate.blocking=true;bar.classList.remove('open')}
  }
  requestAnimationFrame(frame);
 }
 requestAnimationFrame(frame);
})();
const brl=v=>(Number(v||0)).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const num=(v,d=2)=>v===null||v===undefined||v===''?'—':Number(v).toLocaleString('pt-BR',{minimumFractionDigits:0,maximumFractionDigits:d});
const pct=(v,d=1)=>v===null||v===undefined?'—':num(v,d)+'%';
const fixedNum=(v,d=1)=>v===null||v===undefined||v===''?'—':Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
// Precisão visual por assunto: se um valor do mesmo grupo exigir mais casas,
// todos os valores daquele grupo recebem a mesma quantidade de casas decimais.
const decimalPlaces=(v,max=4)=>{if(v===null||v===undefined||v==='')return 0;const n=Number(v);if(!Number.isFinite(n))return 0;const s=Math.abs(n).toFixed(max).replace(/0+$/,'').replace(/\.$/,'');return s.includes('.')?s.split('.')[1].length:0};
const groupDecimals=(values,min=0,max=4)=>Math.max(min,...(values||[]).filter(v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))).map(v=>Math.min(max,decimalPlaces(v,max))),0);
const groupNum=(v,d)=>fixedNum(v,d);
const groupPct=(v,d)=>v===null||v===undefined?'—':fixedNum(v,d)+'%';
const groupCm=(v,d)=>v===null||v===undefined?'—':fixedNum(v,d)+' cm';
const vvPct=v=>v===null||v===undefined?'—':fixedNum(v,1)+'%';
const cm=(v)=>v===null||v===undefined?'—':num(v,2)+' cm';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dateBR=s=>{if(!s)return '—';const [y,m,d]=String(s).slice(0,10).split('-');return y&&m&&d?`${d}/${m}/${y}`:s};
let currentUser=null;
let currentPortal=null;
function resetEmbeddedFrame(kind){
 const frame=$(kind==='traces'?'#traces-app-frame':'#nc-app-frame');
 if(!frame)return;
 frame.onload=null;frame.dataset.ready='';frame.removeAttribute('src');frame.hidden=true;
 const loading=$(kind==='traces'?'#traces-app-loading':'#nc-app-loading');
 if(loading)loading.hidden=false;
}
function releaseEmbeddedProject(kind){
 resetEmbeddedFrame(kind);
 return fetch(`/api/embedded-projects/${kind}/release`,{method:'POST',keepalive:true}).catch(()=>{});
}
function releasePortalProject(portal){
 if(portal==='TRACES')return releaseEmbeddedProject('traces');
 if(portal==='NC')return releaseEmbeddedProject('nc');
 return Promise.resolve();
}
const isAdmin=()=>String(currentUser?.role||'').toUpperCase()==='ADMIN';
const canEdit=()=>isAdmin()||String(currentUser?.permission_level||'VIEWER').toUpperCase()==='EDITOR';
const canAccessPortal=portal=>{portal=String(portal||'').toUpperCase();if(!currentUser)return false;if(portal==='UNIVERSAL')return true;if(['QUALITY','TRACES'].includes(portal))return isAdmin()||!!currentUser.access_quality_general;if(portal==='NC')return isAdmin()||!!currentUser.access_quality_nc;if(isAdmin())return ['BV','CONTRACTOR','ADMIN'].includes(portal);if(portal==='BV')return !!currentUser.access_bv;if(portal==='CONTRACTOR')return !!currentUser.access_contractor;return false};
const contractorScopes=()=>isAdmin()?['ARENA','PAVIDEZ']:[...(currentUser?.contractors||[])].filter(x=>['ARENA','PAVIDEZ'].includes(String(x).toUpperCase())).map(x=>String(x).toUpperCase());
function applyContractorScopeUI(){const allowed=contractorScopes();const ids=['contractor-home-company','kit-contractor','kit-doc-contractor','contractor-doc-company','contractor-pending-company'];ids.forEach(id=>{const el=$('#'+id);if(!el)return;const current=el.value;const opts=[];if(allowed.length>1)opts.push(['ALL','Arena + Pavidez']);if(allowed.includes('ARENA'))opts.push(['ARENA','ARENA']);if(allowed.includes('PAVIDEZ'))opts.push(['PAVIDEZ','PAVIDEZ']);el.innerHTML=opts.map(([v,t])=>`<option value="${v}">${t}</option>`).join('');if(opts.some(([v])=>v===current))el.value=current;else if(opts.length)el.value=opts[0][0];});}
const authMessage=(msg,bad=false)=>{const el=$('#auth-message');if(!el)return;el.textContent=msg||'';el.className='auth-message '+(msg?(bad?'bad-text':'ok-text'):'')};
function showAuthMode(mode='login'){
 ['login','register','forgot','reset'].forEach(x=>$('#'+x+'-form')?.classList.toggle('auth-hidden',x!==mode));authMessage('');
}
function showAuthScreen(mode='login'){const previous=currentPortal;$('#app-layout')?.classList.add('auth-hidden');$('#portal-shell')?.classList.add('auth-hidden');$('#auth-shell')?.classList.remove('auth-hidden');currentPortal=null;if(previous)void releasePortalProject(previous);showAuthMode(mode)}
function showApp(){ $('#auth-shell')?.classList.add('auth-hidden');$('#portal-shell')?.classList.add('auth-hidden');$('#app-layout')?.classList.remove('auth-hidden') }
function showPortalSelector(){
 const previous=currentPortal;currentPortal=null;if(previous)void releasePortalProject(previous);$('#auth-shell')?.classList.add('auth-hidden');$('#app-layout')?.classList.add('auth-hidden');$('#portal-shell')?.classList.remove('auth-hidden');
 $('#portal-user-name').textContent=currentUser?.name||'Usuário';
 let available=0;$$('[data-portal-card]').forEach(card=>{const portal=card.dataset.portalCard,ok=canAccessPortal(portal);available+=ok?1:0;card.classList.toggle('portal-locked',!ok);card.setAttribute('aria-disabled',ok?'false':'true');const label=card.querySelector('.portal-access-label');if(label)label.textContent=ok?'LIBERADO':'BLOQUEADO';const action=card.querySelector('.portal-card-state b');if(action)action.textContent=ok?'Entrar →':'🔒 Sem acesso'});
 $('#portal-empty-note')?.classList.toggle('auth-hidden',available>0);
}
function applyRoleUI(){
 const admin=isAdmin();
 $('#user-name').textContent=currentUser?.name||'Usuário';$('#user-role').textContent=admin?'ADMINISTRADOR':(canEdit()?'EDITOR':'VISUALIZADOR');
 $('#user-avatar').textContent=(currentUser?.name||'U').trim().charAt(0).toUpperCase();
 applyContractorScopeUI();
 const upload=$('.import-panel');if(upload)upload.classList.toggle('read-only-block',!canEdit());
 $('#c-reprocess-no-result')?.classList.toggle('auth-hidden',!admin);
}
function applyPortalUI(){
 const names={BV:'Ambiente BV',CONTRACTOR:'Ambiente Contratada',TRACES:'Traços',NC:'Não conformidades',UNIVERSAL:'Ferramentas Universais',ADMIN:'Administração'};
 $('#portal-context').textContent=names[currentPortal]||'QualiMatch';
 $$('#nav button[data-portal]').forEach(b=>b.classList.toggle('auth-hidden',b.dataset.portal!==currentPortal));
 $$('[data-portal-block]').forEach(b=>b.classList.toggle('auth-hidden',b.dataset.portalBlock!==currentPortal));
 $('#sync-all')?.classList.toggle('auth-hidden',!(currentPortal==='BV'&&isAdmin()));
}
function enterPortal(portal,page=null){
 portal=String(portal||'').toUpperCase();
 if(portal==='QUALITY')portal=String(page||'').startsWith('quality-nc-')||page==='nc-app'?'NC':'TRACES';
 if(!canAccessPortal(portal)){toast('Este ambiente ainda não foi liberado para sua conta.',true);return}
 const previous=currentPortal;if(previous&&previous!==portal)void releasePortalProject(previous);
 currentPortal=portal;showApp();applyRoleUI();applyPortalUI();
 const defaults={BV:'dashboard',CONTRACTOR:'contractor-home',TRACES:'traces-app',NC:'nc-app',UNIVERSAL:'universal-split',ADMIN:'admin'};
 const target=page&&$(`#nav button[data-page="${page}"][data-portal="${portal}"]`)?page:defaults[portal];openPage(target);refreshNotifications();
}
async function refreshSetupStatus(){
 try{const d=await api('/api/auth/setup-status');const el=$('#auth-setup-warning');if(!d.admin_configured)el.innerHTML='<div class="setup-alert"><b>Administrador ainda não configurado.</b><br>Execute <code>configurar_admin.bat</code> no servidor antes do primeiro acesso.</div>';else if(!d.email_configured)el.innerHTML='<div class="setup-alert">Aprovação pelo painel está ativa, mas o SMTP ainda não foi configurado. Execute <code>configurar_admin.bat</code> novamente para receber solicitações por e-mail.</div>';else el.innerHTML=''}catch{}
}
async function bootstrapAuth(){
 refreshSetupStatus();
 const params=new URLSearchParams(location.search),token=params.get('reset_token');if(token){showAuthScreen('reset');return}
 try{currentUser=await api('/api/auth/me');applyRoleUI();const requested=params.get('page');if(requested==='admin'&&canAccessPortal('ADMIN'))enterPortal('ADMIN','admin');else if(requested==='nc-app'&&canAccessPortal('NC'))enterPortal('NC',requested);else if(['traces-app','quality-overview','quality-approved','quality-traces'].includes(requested)&&canAccessPortal('QUALITY'))enterPortal('QUALITY',requested);else showPortalSelector()}catch{showAuthScreen('login')}
}
async function doLogout(){const previous=currentPortal;if(previous)await releasePortalProject(previous);currentPortal=null;try{await api('/api/auth/logout',{method:'POST'})}catch{}currentUser=null;showAuthScreen('login');authMessage('Sessão encerrada.')}
window.addEventListener('pagehide',()=>{if(currentPortal==='TRACES')void fetch('/api/embedded-projects/traces/release',{method:'POST',keepalive:true});if(currentPortal==='NC')void fetch('/api/embedded-projects/nc/release',{method:'POST',keepalive:true})});
const pendingReads=new Map();
async function api(url,opt={}){
 const read=(opt.method||'GET').toUpperCase()==='GET'&&!opt.signal&&!opt.headers;
 if(!read)pendingReads.clear();
 if(read&&pendingReads.has(url))return pendingReads.get(url);
 const work=(async()=>{const r=await fetch(url,opt);const txt=await r.text();let d;try{d=txt?JSON.parse(txt):{}}catch{d={detail:txt}}if(!r.ok){if(r.status===401&&!url.includes('/api/auth/login'))showAuthScreen('login');const e=new Error(d.detail||d.message||`HTTP ${r.status}`);e.status=r.status;throw e}return d})();
 if(read)pendingReads.set(url,work);
 try{return await work}finally{if(pendingReads.get(url)===work)pendingReads.delete(url)}
}
function toast(msg,bad=false){const t=$('#toast');t.textContent=msg;t.style.display='block';t.style.borderColor=bad?'#7d2e39':'#413b5b';clearTimeout(window._tt);window._tt=setTimeout(()=>t.style.display='none',5000)}
function statusBadge(v){const s=String(v||'').toUpperCase();const cls=s.includes('REPROV')||s.includes('ERRO')?'bad':s.includes('APROV')||s==='OK'||s==='ENTREGUE'||s==='NO PRAZO'||s.includes('CARREG')||s.includes('BD_QUALI_OK')?'ok':s.includes('NAO ENTREGUE')||s.includes('NÃO ENTREGUE')||s.includes('PEND')||s.includes('AVISO')||s.includes('ATEN')||s.includes('DESATUAL')||s.includes('PARCIAL')||s.includes('INCOMPLETO')||s.includes('REVISAR')?'warn':'neutral';return `<span class="status-badge ${cls}">${esc(v||'—')}</span>`}
function readStatus(v){const s=String(v||'').toUpperCase();return s==='OK'?'CARREGADO':(v||'CARREGADO')}
function stateClass(v){const s=String(v||'').toUpperCase();return s.includes('APROV')?'metric-ok':s.includes('REPROV')?'metric-bad':''}
function phaseMetric(label,value,range='',state=''){return `<div class="phase-metric ${stateClass(state)}"><span>${label}</span><b>${value}</b>${range?`<div class="range">${range}</div>`:''}</div>`}
function sampleState(value,type){if(value===null||value===undefined||value==='')return '';const n=Number(value);if(type==='vv')return n>=3.5&&n<=7.5?'value-ok':'value-bad';if(type==='ratio')return n>=90?'value-ok':'value-bad';return ''}
function trendMarkup(t,lowerBetter=false){if(!t||t.delta===null||t.delta===undefined)return '';const delta=Number(t.delta||0),pctValue=t.percent===null||t.percent===undefined?null:Number(t.percent);const dir=delta>0?'up':delta<0?'down':'flat';const good=delta===0?'flat':(lowerBetter?(delta<0?'good':'bad'):(delta>0?'good':'bad'));const arrow=delta>0?'↑':delta<0?'↓':'•';const amount=delta===0?'sem alteração':brl(Math.abs(delta));const percentText=pctValue===null?'':` (${delta>0?'+':delta<0?'-':''}${pct(Math.abs(pctValue),1)})`;const monthly=t.mode==='monthly';const ref=t.comparison_date?(monthly?` vs ${monthBR(String(t.comparison_date).slice(0,7))}`:` vs ${dateBR(t.comparison_date)}`):'';const title=monthly?'Variação da produção entre os dois meses mais recentes da BD_QUALI':'Variação financeira';return `<div class="metric-trend trend-${dir} trend-${good}" title="${title}"><b>${arrow} ${amount}${percentText}</b><span>${ref||'comparação indisponível'}</span></div>`}
function metric(label,value,hint='',technical=false,trend=null,lowerBetter=false){return `<div class="card ${technical?'technical':''}"><div class="label">${label}</div><div class="value">${value}</div>${trendMarkup(trend,lowerBetter)}<div class="hint">${hint}</div></div>`}
function renderDashboardWarnings(items){const box=$('#dashboard-warning'),count=$('#dashboard-warning-count'),tip=$('#dashboard-warning-tooltip');const warnings=(items||[]).filter(Boolean);window._dashboardWarningCount=warnings.length;if(!box||!count||!tip)return;count.textContent=warnings.length===1?'1 aviso':`${warnings.length} avisos`;tip.innerHTML=warnings.length?warnings.map(w=>`<div>${esc(w)}</div>`).join(''):'Sem avisos';const onDashboard=$('#page-dashboard')?.classList.contains('active');box.hidden=!warnings.length||!onDashboard}
function updateDashboardWarningVisibility(page){const box=$('#dashboard-warning');if(!box)return;box.hidden=page!=='dashboard'||!window._dashboardWarningCount}

function fmtSta(v){if(v===null||v===undefined)return '—';const km=Math.floor(Number(v)/1000),m=Math.round(Number(v)%1000);return `${km}+${String(m).padStart(3,'0')}`}
function phaseLabel(p){return p==='CONTRA_PROVA'?'CONTRA-PROVA':'ROTINA'}
function renderStatusPie(items){
 const source=(items||[]).filter(x=>Number(x.count||0)>0);
 if(!source.length)return '<div class="empty">Sem dados de qualidade sincronizados.</div>';
 let data=source;
 if(source.length>7){const top=source.slice(0,6),rest=source.slice(6).reduce((a,x)=>a+Number(x.count||0),0);data=[...top,{status:'OUTROS',count:rest}]}
 const total=data.reduce((a,x)=>a+Number(x.count||0),0)||1;
 const colors=['#8b5cf6','#36c690','#f0b95c','#ef6c7a','#5da9e9','#c084fc','#7dd3a7'];
 let acc=0;const stops=data.map((x,i)=>{const start=acc;acc+=Number(x.count||0)/total*100;return `${colors[i%colors.length]} ${start.toFixed(3)}% ${acc.toFixed(3)}%`});
 const legend=data.map((x,i)=>`<div class="pie-legend-row"><span class="pie-dot" style="background:${colors[i%colors.length]}"></span><span class="pie-name" title="${esc(x.status)}">${esc(x.status)}</span><b>${num(x.count,0)}</b><small>${pct(Number(x.count||0)/total*100,1)}</small></div>`).join('');
 return `<div class="pie-layout"><div class="pie-chart" style="background:conic-gradient(${stops.join(',')})"><div class="pie-hole"><b>${num(total,0)}</b><span>linhas</span></div></div><div class="pie-legend">${legend}</div></div>`;
}

/* v3.9.7 — visão financeira por mês removida do dashboard por completo (os 4 cards
   acima já mostram o total/aprovado/pendente/reprovado consolidado). */

const titles={dashboard:['Dashboard','Visão financeira, qualidade e certificados'],certificates:['Certificados','BI330 com resumo estatístico, VV, espessura e corpos de prova'],pending:['Pendências BV','Somente certificados pendentes sob responsabilidade da BV'],measurements:['Medições','Base operacional usada no cruzamento'],cycles:['Gestão Mxx','Cobertura, SLA e pendências por ciclo de medição'],'bv-kpi':['Levantamento KPI','Aprovação, reprovação e pendências operacionais'],'bv-general-report':['Relatório Geral','Certificados BV por medição e tipo'],'traces-app':['Traços','Recebimento, análise e organização de cartas-traço'],'nc-app':['Não conformidades','Gestão de NC, RNC e ações corretivas e preventivas'],'quality-overview':['Traços','Visão executiva dos projetos de traço'],'quality-approved':['Traços aprovados','Consulta detalhada dos traços liberados por contratada'],'quality-traces':['Todos os traços','Inventário consolidado com status e vencimentos'],'quality-nc-overview':['Não conformidades','Visão executiva das RNCs e retenções'],'quality-nc-list':['Consulta de NCs','Base detalhada das Não Conformidades'],'bv-files':['Arquivos BV','Navegação por medição nas pastas alimentadas automaticamente pela BV'],
'contractor-home':['Contratada','Visão inicial do novo ambiente da contratada'],'contractor-kits':['Kits de ensaio','Controle sincronizado das tabelas de kits Arena e Pavidez'],'contractor-certificates':['Arquivos da Contratada','Navegação por pastas da Entrega Contratada'],'contractor-pending':['Pendências da Contratada','Somente execuções ainda sem kit entregue'],
sync:['Sincronização','Arquivos e pastas locais sincronizados pelo OneDrive/SharePoint'],history:['Histórico','Execuções e erros de sincronização'],backups:['Backups','Cópias seguras do banco local'],admin:['Administração','Usuários, permissões de ambiente e auditoria'],tools:['Ferramentas','Automação assistida de PDFs, medições e BD_QUALI'],review:['Revisões','Inconsistências e ações necessárias'],health:['Saúde do sistema','Banco, fontes, backups e sincronizações']};
titles['universal-split']=['Separador de PDF','Divida documentos em intervalos, blocos ou páginas individuais'];
titles['universal-merge']=['Unificador de PDF','Combine documentos na ordem desejada'];
titles['universal-compress']=['Compressor de PDF','Reduza o tamanho de documentos antes do envio'];
titles['universal-images-pdf']=['Imagens para PDF','Reúna fotografias e imagens em um documento'];
titles['universal-organize']=['Organizador de páginas','Reordene, gire ou exclua páginas de um PDF'];
titles['universal-jfif']=['JFIF para PNG','Converta imagens localmente, sem envio externo'];
let currentTraceTarget='dashboard',currentNcTarget='dashboard';
function embeddedNavActive(page,button){
 if(page==='traces-app'&&button.dataset.traceTarget)return button.dataset.traceTarget===currentTraceTarget;
 if(page==='nc-app'&&button.dataset.ncTarget)return button.dataset.ncTarget===currentNcTarget;
 return button.dataset.page===page&&!button.dataset.traceTarget&&!button.dataset.ncTarget;
}
function sendEmbeddedNavigation(kind,target){
 const frame=$(kind==='traces'?'#traces-app-frame':'#nc-app-frame');
 if(!frame||frame.dataset.ready!=='1'||!frame.contentWindow)return;
 try{frame.contentWindow.postMessage({source:'qualimatch',type:kind+'-navigate',target},'*')}catch{}
}
function openEmbeddedSection(kind,target){
 if(kind==='traces')currentTraceTarget=target||'dashboard';else currentNcTarget=target||'dashboard';
 const page=kind==='traces'?'traces-app':'nc-app';
 openPage(page);
 sendEmbeddedNavigation(kind,target);
}
function openPage(page){const btn=$(`#nav button[data-page="${page}"]`);if(btn&&currentPortal&&btn.dataset.portal!==currentPortal)return;$$('#nav button').forEach(x=>x.classList.toggle('active',embeddedNavActive(page,x)));$$('.page').forEach(x=>x.classList.toggle('active',x.id==='page-'+page));const title=titles[page]||[page,''];$('#page-title').textContent=title[0];$('#page-subtitle').textContent=title[1];updateDashboardWarningVisibility(page);({dashboard:loadDash,sync:()=>{loadSources();loadRuntimeState()},measurements:loadMeasurements,cycles:loadCycles,'bv-kpi':loadBvKpi,'bv-general-report':loadBvGeneralReport,'bv-files':loadBvFiles,certificates:loadCertificates,pending:loadPending,'contractor-home':loadContractorHome,'contractor-kits':async()=>{await loadKitFilterOptions();await loadKits();await loadKitDocuments()},'contractor-certificates':loadContractorFolderBrowser,'contractor-pending':loadContractorPending,'traces-app':loadTracesApp,'nc-app':loadNcApp,'quality-overview':loadGeneralQualityOverview,'quality-approved':loadGeneralQualityApproved,'quality-traces':loadGeneralQualityTraces,'quality-nc-overview':loadGeneralQualityNCOverview,'quality-nc-list':loadGeneralQualityNCList,history:loadHistory,backups:loadBackups,admin:loadAdmin,tools:loadTools,review:loadReview,health:loadHealth}[page]||(()=>{}))()}
$$('#nav button').forEach(b=>b.onclick=()=>b.dataset.traceTarget?openEmbeddedSection('traces',b.dataset.traceTarget):b.dataset.ncTarget?openEmbeddedSection('nc',b.dataset.ncTarget):openPage(b.dataset.page));
window.addEventListener('message',event=>{
 const data=event.data||{};
 if(data.source==='traces-app'&&data.type==='traces-route'&&currentPortal==='TRACES'){
  currentTraceTarget=data.target||'dashboard';
  $$('#nav button[data-trace-target]').forEach(x=>x.classList.toggle('active',x.dataset.traceTarget===currentTraceTarget));
 }
 if(data.source==='nc-app'&&data.type==='nc-route'&&currentPortal==='NC'){
  currentNcTarget=data.target||'dashboard';
  $$('#nav button[data-nc-target]').forEach(x=>x.classList.toggle('active',x.dataset.ncTarget===currentNcTarget));
 }
 if(data.source==='nc-app'&&data.type==='nc-context'){
  const select=$('#nc-sede-select'),sedes=Array.isArray(data.sedes)?data.sedes:[];
  if(select){select.innerHTML=sedes.map(s=>`<option value="${esc(s.id)}">${esc(s.sigla||s.nome||s.id)}</option>`).join('');select.value=data.sedeId||'';}
 }
});
$('#nc-sede-select').onchange=event=>{
 const frame=$('#nc-app-frame'),sedeId=event.target.value;
 if(frame?.contentWindow&&sedeId)frame.contentWindow.postMessage({source:'qualimatch',type:'nc-select-sede',sedeId},'*');
};

let tracesAppLoading=false;
async function loadTracesApp(){
 const frame=$('#traces-app-frame'),loading=$('#traces-app-loading');
 if(!frame||tracesAppLoading||frame.dataset.ready==='1')return;
 tracesAppLoading=true;frame.hidden=true;loading.hidden=false;
 const slowTimer=window.setTimeout(()=>{const p=loading?.querySelector('p');if(p)p.textContent='Primeira abertura: finalizando a interface local. As próximas serão imediatas...'},7000);
 try{
  const d=await api('/api/traces-project/launch',{method:'POST'});
  frame.onload=()=>{
   // Login automático: já autenticado no QualiMatch, não faz sentido pedir
   // senha de novo lá dentro. d.sso só existe quando o backend conseguiu
   // casar o e-mail com um usuário do Controle de Traços; sem ele, o iframe
   // simplesmente mostra a tela de login normal.
   if(d.sso&&d.sso.token)try{frame.contentWindow.postMessage({source:'qualimatch',type:'sso-login',token:d.sso.token,user:d.sso.user},new URL(d.url).origin)}catch(err){}
   frame.dataset.ready='1';frame.hidden=false;loading.hidden=true;sendEmbeddedNavigation('traces',currentTraceTarget)
  };
  frame.src=d.url;
 }catch(e){loading.innerHTML=`<div class="empty"><b>Não foi possível abrir o Controle de Traços.</b><br>${esc(e.message)}<br><button class="primary compact" type="button" onclick="retryTracesApp()">Tentar novamente</button></div>`}
 finally{window.clearTimeout(slowTimer);tracesAppLoading=false}
}
function retryTracesApp(){const frame=$('#traces-app-frame');if(frame){frame.dataset.ready='';frame.removeAttribute('src')}const loading=$('#traces-app-loading');if(loading)loading.innerHTML='<div class="traces-loader"></div><h2>Preparando o Controle de Traços</h2><p>Carregando banco, Excel e pastas oficiais...</p>';loadTracesApp()}

let ncAppLoading=false;
async function loadNcApp(){
 const frame=$('#nc-app-frame'),loading=$('#nc-app-loading');
 if(!frame||ncAppLoading||frame.dataset.ready==='1')return;
 ncAppLoading=true;frame.hidden=true;loading.hidden=false;
 const slowTimer=window.setTimeout(()=>{const p=loading?.querySelector('p');if(p)p.textContent='Primeira abertura: finalizando o sistema local. As próximas serão imediatas...'},7000);
 try{
  const d=await api('/api/nc-project/launch',{method:'POST'});
  frame.onload=()=>{frame.dataset.ready='1';frame.hidden=false;loading.hidden=true;sendEmbeddedNavigation('nc',currentNcTarget)};
  frame.src=d.url;
 }catch(e){loading.innerHTML=`<div class="empty"><b>Não foi possível abrir o Sistema de Não Conformidades.</b><br>${esc(e.message)}<br><button class="primary compact" type="button" onclick="retryNcApp()">Tentar novamente</button></div>`}
 finally{window.clearTimeout(slowTimer);ncAppLoading=false}
}
function retryNcApp(){const frame=$('#nc-app-frame');if(frame){frame.dataset.ready='';frame.removeAttribute('src')}const loading=$('#nc-app-loading');if(loading){loading.hidden=false;loading.innerHTML='<div class="nc-loader"></div><h2>Preparando o Sistema de Não Conformidades</h2><p>Carregando registros, contratos e ações...</p>'}loadNcApp()}

function measurementOptionLabel(x){
 const a=x?.measurement_start?dateBR(x.measurement_start):'',b=x?.measurement_end?dateBR(x.measurement_end):'';
 return `${x?.measurement||''}${a&&b?` • ${a} a ${b}`:''}`;
}
async function loadDashboardMeasurementOptions(){
 const sel=$('#dash-measurement');if(!sel)return;
 const current=sel.value,contractor=$('#dash-contractor')?.value||'ALL';
 try{const items=await api('/api/measurement-cycles/options?contractor='+encodeURIComponent(contractor));sel.innerHTML='<option value="">Todas as medições</option>'+(items||[]).map(x=>`<option value="${esc(x.measurement)}">${esc(measurementOptionLabel(x))}</option>`).join('');if((items||[]).some(x=>x.measurement===current))sel.value=current}catch(e){toast('Não foi possível carregar as medições: '+e.message,true)}
}
let dashboardCertificateOptions=[],dashboardCertificateSelected=new Set();
function updateDashboardCertificateTrigger(){
 const trigger=$('#dash-certificates-trigger');if(!trigger)return;
 const n=dashboardCertificateSelected.size;
 trigger.querySelector('span').textContent=!n?'Todos os certificados':n===1?[...dashboardCertificateSelected][0]:`${n} certificados selecionados`;
}
function renderDashboardCertificateOptions(filter=''){
 const box=$('#dash-certificates-options');if(!box)return;
 const q=String(filter||'').trim().toLowerCase();
 const list=dashboardCertificateOptions.filter(x=>!q||String(x).toLowerCase().includes(q));
 box.innerHTML=list.length?list.map(x=>`<label class="multi-select-option"><input type="checkbox" value="${esc(x)}" ${dashboardCertificateSelected.has(x)?'checked':''}><span>${esc(x)}</span></label>`).join(''):'<div class="empty">Nenhum certificado encontrado.</div>';
 box.querySelectorAll('input').forEach(el=>el.onchange=()=>{if(el.checked)dashboardCertificateSelected.add(el.value);else dashboardCertificateSelected.delete(el.value);updateDashboardCertificateTrigger()});
}
async function loadDashboardCertificateOptions(){
 try{
  const contractor=$('#dash-contractor')?.value||'ALL';
  const d=await api('/api/certificates-filter-options?contractor='+encodeURIComponent(contractor));
  dashboardCertificateOptions=d.numbers||[];
  dashboardCertificateSelected=new Set([...dashboardCertificateSelected].filter(x=>dashboardCertificateOptions.includes(x)));
  renderDashboardCertificateOptions($('#dash-certificates-search')?.value||'');
  updateDashboardCertificateTrigger();
 }catch(e){toast('Não foi possível carregar os certificados do filtro: '+e.message,true)}
}
async function loadDash(){
 if(!$('#page-dashboard')?.classList.contains('active'))return;
 try{
  const q=new URLSearchParams({contractor:$('#dash-contractor').value,status:$('#dash-status')?.value||'ALL'});if($('#dash-measurement')?.value)q.set('measurement',$('#dash-measurement').value);if($('#dash-start').value)q.set('start',$('#dash-start').value);if($('#dash-end').value)q.set('end',$('#dash-end').value);if(dashboardCertificateSelected.size)q.set('certificates',[...dashboardCertificateSelected].join(','));
  const [,d]=await Promise.all([Promise.all([loadDashboardMeasurementOptions(),loadDashboardCertificateOptions()]),api('/api/dashboard?'+q)]),T=d.totals,F=d.financial||{},TR=d.financial_trends||{},C=d.certificate_summary||{};
  const period=$('#dash-measurement-period');if(period){const m=d.measurement_period;period.textContent=m?`${m.measurement}: ${dateBR(m.measurement_start)} a ${dateBR(m.measurement_end)}`:'';}
  $('#financial-kpis').innerHTML=[
   metric('Total serviço',brl(T.total_service),'RELATÓRIO consolidado; fallback = soma completa da BD_QUALI',false,TR.total_service,false),
   metric('Aprovado',brl(F.approved),'Avaliação financeira do RELATÓRIO',false,TR.approved,false),
   metric('Pendente',brl(F.pending),'Avaliação financeira do RELATÓRIO',false,TR.pending,true),
   metric('Reprovado',brl(F.reproved),'Avaliação financeira do RELATÓRIO',false,TR.reproved,true),
   metric('Extensão',num(T.extension_m,0)+' m','RELATÓRIO / BD_QUALI completa'),
   metric('CBUQ',num(T.quantity_t)+' t','Quantidade de projeto'),
   metric('CAP',num(T.cap_project_t)+' t','Validado; corrige CAP inconsistente pela quantidade × teor ótimo')].join('');
  $('#technical-kpis').innerHTML=[
   metric('Certificados',num(C.total,0),`Classificação: ${num(C.approved,0)} aprovados + ${num(C.reproved,0)} reprovados + ${num(C.adjustments,0)} ajustes`,true),
   metric('Aprovados',num(C.approved,0),'Status final do BI; se houver contra-prova entregue, vale a contra-prova',true),
   metric('Reprovados',num(C.reproved,0),'Status final do BI; se houver contra-prova entregue, vale a contra-prova',true),
   metric('Ajustes / sem resultado',num(C.adjustments,0),'Completa a classificação do total; inclui leitura parcial/sem resultado',true),
   metric('Dias pendentes',num(d.pending_days,0),'Dias com medição e sem certificado',true),metric('Quantidade CPs',num(C.sample_count,0),'Total de corpos de prova dos certificados exibidos',true)].join('');
  renderDashboardWarnings(d.warnings||[]);
  $('#status-pie').innerHTML=renderStatusPie(d.statuses||[]);
  $('#source-info').innerHTML=d.sources?.length?d.sources.map(x=>`<div class="source-info"><div class="big-source"><b>${x.contractor}</b> ${statusBadge(x.summary_source||'OK')}</div><span><b>Usado:</b> ${esc(x.cell||'fallback')}</span><br><small>${num(x.total_records,0)} linhas totais • ${num(x.visible_records,0)} visíveis no Excel • sincronizado ${esc(x.synced_at||'—')}</small>${x.subtotal_cell?`<div class="audit-line">SUBTOTAL filtrado: ${brl(x.subtotal_excel)} em ${esc(x.subtotal_cell)}</div>`:''}${x.all_rows_total!=null?`<div class="audit-line">Soma completa BD_QUALI: ${brl(x.all_rows_total)}</div>`:''}${x.cap_source?`<div class="audit-line">CAP: ${esc(x.cap_source)}</div>`:''}</div>`).join(''):'<div class="empty">Sincronize as planilhas de Qualidade.</div>';
  $('#recent-certificates').innerHTML=renderRecent(C.recent||[]);
 }catch(e){toast(e.message,true)}
}
function renderRecent(list){if(!list.length)return '<div class="empty">Nenhum certificado importado ainda.</div>';const thicknessDigits=groupDecimals(list.map(x=>x.mean_thickness_cm),0,3);return `<div class="table-wrap"><table><thead><tr><th>Certificado</th><th>Data</th><th>Trecho</th><th>VV médio</th><th>Esp. média</th><th>VV</th><th>Esp.</th></tr></thead><tbody>${list.map(x=>`<tr><td><button class="cert-link" onclick="openCertificate(${x.id})">${esc(x.number)}</button><span class="sub">${esc(x.contractor)}</span></td><td>${dateBR(x.certificate_date||x.extraction_date||x.service_date)}</td><td>${esc(x.road||'—')}<span class="sub">${fmtSta(x.kmi)} a ${fmtSta(x.kmf)}</span></td><td>${vvPct(x.mean_vv)}</td><td>${groupCm(x.mean_thickness_cm,thicknessDigits)}</td><td>${statusBadge(x.status_vv)}</td><td>${statusBadge(x.status_thickness)}</td></tr>`).join('')}</tbody></table></div>`}

const controlLabels={status_1:'1. Aplicação',status_2:'2. Usinagem',status_3:'3. Vv',status_4:'4. Taxa',status_5:'5. Ligante',status_6:'6. Mancha de areia',status_7:'7. Pêndulo',status_8:'8. Esp. úmida',sin_retro:'SIN. - Retro'};
function renderControlCards(controls){
 return Object.entries(controlLabels).map(([key,label])=>{
  const c=controls?.[key]||{},ok=Number(c.ok||0),total=Number(c.applicable||0),pct=total?ok/total*100:0;
  const cls=total===0?'neutral':pct>=95?'ok':pct>=85?'warn':'bad';
  return `<div class="control-status-card ${cls}"><div class="control-status-head"><b>${esc(label)}</b><span>${num(ok,0)} / ${num(total,0)}</span></div><div class="control-status-value">${pct.toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})}%</div><div class="control-progress"><span style="width:${Math.max(0,Math.min(100,pct))}%"></span></div><small>${num(ok,0)} OK${total?` de ${num(total,0)} aplicáveis`:''}</small></div>`;
 }).join('');
}
function monthBR(month){
 const m=String(month||'');if(!/^\d{4}-\d{2}$/.test(m))return m;
 const [y,mo]=m.split('-');return `${mo}/${y}`;
}
function renderDeliveryChart(items){
 const data=(items||[]);
 if(!data.length)return '<div class="empty">Nenhuma entrega mensal disponível.</div>';
 const max=Math.max(...data.map(x=>Number(x.count||0)),1);
 const W=Math.max(760,data.length*84),H=320,left=44,right=22,top=30,bottom=54;
 const innerW=W-left-right,innerH=H-top-bottom,step=innerW/data.length,barW=Math.min(42,step*.56);
 const y=v=>top+innerH-(Number(v||0)/max*innerH);
 const grid=[0,.25,.5,.75,1].map(f=>{const val=Math.round(max*f),yy=y(val);return `<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="monthly-grid-line"/><text x="${left-8}" y="${yy+4}" text-anchor="end" class="monthly-axis-text">${val}</text>`}).join('');
 const bars=data.map((x,i)=>{const cx=left+step*i+step/2,c=Number(x.count||0),yy=y(c),h=top+innerH-yy;return `<g><rect x="${cx-barW/2}" y="${yy}" width="${barW}" height="${Math.max(h,1)}" rx="6" class="monthly-delivery-bar"><title>${monthBR(x.month)}: ${c} entrega(s)</title></rect><text x="${cx}" y="${Math.max(top+12,yy-7)}" text-anchor="middle" class="monthly-value">${c}</text><text x="${cx}" y="${H-24}" text-anchor="middle" class="monthly-axis-text">${monthBR(x.month)}</text></g>`}).join('');
 return `<div class="monthly-chart-wrap"><div class="monthly-chart-legend"><span><i class="legend-bar"></i>Entregas</span></div><svg class="monthly-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Entregas mensais">${grid}${bars}</svg></div>`;
}

const BV_REPORT_COLORS=['#8b5cf6','#36c690','#f0b95c','#ef6c7a','#5da9e9','#c084fc'];
function renderBvCategoryStack(measurements,categories,colors){
 const data=[...(measurements||[])].reverse(); // o backend devolve do mais novo pro mais antigo; o gráfico lê da esquerda (mais antigo) pra direita
 if(!data.length)return '<div class="empty">Nenhum certificado BV sincronizado para este filtro.</div>';
 const max=Math.max(...data.map(x=>Number(x.total||0)),1);
 const W=Math.max(760,data.length*76),H=320,left=40,right=18,top=26,bottom=54;
 const innerW=W-left-right,innerH=H-top-bottom,step=innerW/data.length,barW=Math.min(40,step*.58);
 const y=v=>top+innerH-(Number(v||0)/max*innerH);
 const grid=[0,.25,.5,.75,1].map(f=>{const val=Math.round(max*f),yy=y(val);return `<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="monthly-grid-line"/><text x="${left-8}" y="${yy+4}" text-anchor="end" class="monthly-axis-text">${val}</text>`}).join('');
 const bars=data.map((x,i)=>{
  const cx=left+step*i+step/2,total=Number(x.total||0);
  let acc=0,segs='';
  categories.forEach((cat,ci)=>{
   const n=Number(x.counts?.[cat]||0);if(!n)return;
   const y0=y(acc),y1=y(acc+n);acc+=n;
   segs+=`<rect x="${cx-barW/2}" y="${y1}" width="${barW}" height="${Math.max(y0-y1,1)}" class="bv-stack-seg" fill="${colors[ci%colors.length]}"><title>${esc(x.measurement)} • ${esc(cat)}: ${n}</title></rect>`;
  });
  return `<g>${segs}${total?`<text x="${cx}" y="${Math.max(top+12,y(total)-7)}" text-anchor="middle" class="monthly-value">${total}</text>`:''}<text x="${cx}" y="${H-24}" text-anchor="middle" class="monthly-axis-text">${esc(x.measurement)}</text></g>`;
 }).join('');
 const legend=categories.map((cat,ci)=>`<span><i class="legend-bar" style="background:${colors[ci%colors.length]}"></i>${esc(cat)}</span>`).join('');
 return `<div class="monthly-chart-wrap"><div class="monthly-chart-legend bv-stack-legend">${legend}</div><svg class="monthly-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Certificados por medição">${grid}${bars}</svg></div>`;
}

async function loadContractorHome(){
 try{
  const contractor=$('#contractor-home-company')?.value||'ALL';
  const d=await api('/api/contractor/kits/summary?contractor='+encodeURIComponent(contractor));
  const pending=Number(d.incomplete||0)+Number(d.pending||0)+Number(d.error||0);
  $('#contractor-kit-kpis').innerHTML=[
   metric('Kits',num(d.total,0),'Registros sincronizados da tabela d.KIT',true),
   metric('Recebidos',num(d.received,0),'Linhas preenchidas da tabela d.KIT',true),
   metric('Status OK',num(d.ok,0),'Kits com todos os controles considerados concluídos',true),
   metric('Atenção',num(pending,0),`${num(d.incomplete,0)} incompletos • ${num(d.pending,0)} pendentes • ${num(d.error,0)} erros`,true)
  ].join('');
  $('#contractor-control-cards').innerHTML=renderControlCards(d.controls||{});
  $('#contractor-delivery-chart').innerHTML=renderDeliveryChart(d.deliveries||[]);
 }catch(e){toast(e.message,true)}
}
async function loadKitFilterOptions(){
 try{
  const contractor=$('#kit-contractor')?.value||'ALL';
  const d=await api('/api/contractor/kits/filter-options?contractor='+encodeURIComponent(contractor));
  const road=$('#kit-road'),curRoad=road?.value||'';if(road){const items=d.roads||[];road.innerHTML='<option value="">Todas as BR/PR</option>'+items.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');if(items.includes(curRoad))road.value=curRoad}
  const period=$('#kit-period'),curPeriod=period?.value||'';if(period){const items=['DIURNO','NOTURNO'];period.innerHTML='<option value="">Todos os períodos</option>'+items.map(v=>`<option value="${v}">${v}</option>`).join('');if(items.includes(curPeriod))period.value=curPeriod}
  const st=$('#kit-status'),curStatus=st?.value||'ALL';if(st){const items=['OK','INCOMPLETO','PENDENTE'];st.innerHTML='<option value="ALL">Todas</option>'+items.map(v=>`<option value="${v}">${v}</option>`).join('');if(curStatus==='ALL'||items.includes(curStatus))st.value=curStatus}
 }catch(e){toast('Não foi possível carregar os filtros de kits: '+e.message,true)}
}
function clearKitFilters(){
 $('#kit-contractor').value='ALL';$('#kit-sort').value='newest';$('#kit-status').value='ALL';$('#kit-road').value='';$('#kit-period').value='';$('#kit-start').value='';$('#kit-end').value='';$('#kit-search').value='';loadKitFilterOptions().then(loadKits);
}
let currentKitRows=[],kitPage=1,kitTotal=0,kitPageSize=25;
const kitControlOptions=v=>{const value=String(v||'').toUpperCase();const items=['','OK','PENDENTE','INCOMPLETO','N/A','-'];if(value&&!items.includes(value))items.push(value);return items.map(x=>`<option value="${esc(x)}" ${x===value?'selected':''}>${esc(x||'—')}</option>`).join('')};
function kitStatusOptions(v){const value=String(v||'').toUpperCase();return ['OK','INCOMPLETO','PENDENTE'].map(x=>`<option value="${x}" ${x===value?'selected':''}>${x}</option>`).join('')}
function kitPeriodOptions(v){const value=String(v||'').toUpperCase();return ['DIURNO','NOTURNO'].map(x=>`<option value="${x}" ${x===value?'selected':''}>${x}</option>`).join('')}
async function openKitEdit(id){
 try{
  const k=await api('/api/contractor/kits/'+id);
  showModal(`<div class="edit-modal"><span class="eyebrow">KIT DE ENSAIO / EDIÇÃO</span><h2>Kit ${esc(k.seq||('#'+k.source_row))} • ${esc(k.contractor)}</h2><div class="management-note"><b>Edição protegida</b><span>Esta alteração fica salva no QualiMatch e não é sobrescrita pela próxima sincronização da d.KIT. A planilha SharePoint original não é alterada.</span></div><form id="kit-edit-form" class="edit-form-grid">
   <label>#SEQ<input name="seq" value="${esc(k.seq||'')}"></label><label>Serviço<input name="service" value="${esc(k.service||'')}"></label>
   <label>Data aplicação<input type="date" name="application_date" value="${esc(k.application_date||'')}"></label><label>Data<input type="date" name="receipt_date" value="${esc(k.receipt_date||'')}"></label>
   <label>Projeto mistura<input name="mix_project" value="${esc(k.mix_project||'')}"></label><label>Período<select name="period">${kitPeriodOptions(k.period)}</select></label>
   <label>Rodovia<input name="road" value="${esc(k.road||'')}"></label><label>KMI<input name="kmi" value="${esc(fmtSta(k.kmi)==='—'?'':fmtSta(k.kmi))}" placeholder="405+845"></label>
   <label>KMF<input name="kmf" value="${esc(fmtSta(k.kmf)==='—'?'':fmtSta(k.kmf))}" placeholder="406+100"></label><label>Situação<select name="status">${kitStatusOptions(k.status)}</select></label>
   <label>1. Aplicação<select name="status_1">${kitControlOptions(k.status_1)}</select></label><label>2. Usinagem<select name="status_2">${kitControlOptions(k.status_2)}</select></label>
   <label>3. Vv<select name="status_3">${kitControlOptions(k.status_3)}</select></label><label>4. Taxa<select name="status_4">${kitControlOptions(k.status_4)}</select></label>
   <label>5. Ligante<select name="status_5">${kitControlOptions(k.status_5)}</select></label><label>6. Mancha de areia<select name="status_6">${kitControlOptions(k.status_6)}</select></label>
   <label>7. Pêndulo<select name="status_7">${kitControlOptions(k.status_7)}</select></label><label>8. Esp. úmida<select name="status_8">${kitControlOptions(k.status_8)}</select></label>
   <label>SIN. - Retro<select name="sin_retro">${kitControlOptions(k.sin_retro)}</select></label>
   <div class="edit-actions"><button type="button" class="ghost" onclick="closeModal()">Cancelar</button><button class="primary">Salvar kit</button></div>
  </form></div>`);
  $('#kit-edit-form').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.currentTarget),body=Object.fromEntries(fd.entries());try{const r=await api('/api/contractor/kits/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});toast(r.message||'Kit atualizado');closeModal();await Promise.all([loadKits(),loadContractorHome()])}catch(err){toast(err.message,true)}};
 }catch(e){toast(e.message,true)}
}
async function archiveKit(id){
 const k=currentKitRows.find(x=>Number(x.id)===Number(id));if(!confirm(`Remover o kit ${k?.seq||id} das telas e estatísticas?\n\nA linha original da d.KIT no SharePoint NÃO será apagada.`))return;
 try{const r=await api('/api/contractor/kits/'+id,{method:'DELETE'});toast(r.message||'Kit removido');await Promise.all([loadKits(),loadContractorHome()])}catch(e){toast(e.message,true)}
}
async function loadKits(page=1){
 try{
  const contractor=$('#kit-contractor')?.value||'ALL';
  const q=new URLSearchParams({contractor,search:$('#kit-search')?.value||'',sort:$('#kit-sort')?.value||'newest',status:$('#kit-status')?.value||'ALL',road:$('#kit-road')?.value||'',period:$('#kit-period')?.value||'',page:String(page),page_size:String(kitPageSize)});
  if($('#kit-start')?.value)q.set('start',$('#kit-start').value);if($('#kit-end')?.value)q.set('end',$('#kit-end').value);
  const [list,sum]=await Promise.all([api('/api/contractor/kits?'+q),api('/api/contractor/kits/summary?contractor='+encodeURIComponent(contractor))]);
  currentKitRows=list.items||[];kitPage=list.page||page;kitTotal=Number(list.total||0);
  const pending=Number(sum.incomplete||0)+Number(sum.pending||0)+Number(sum.error||0);
  $('#kit-summary').innerHTML=[metric('Kits',num(kitTotal,0),'Registros encontrados com os filtros aplicados',true),metric('Recebidos',num(sum.received,0),'Linhas preenchidas da tabela d.KIT',true),metric('Status OK',num(sum.ok,0),'Situação geral da linha',true),metric('Atenção',num(pending,0),`${num(sum.incomplete,0)} incompletos • ${num(sum.pending,0)} pendentes • ${num(sum.error,0)} erros`,true)].join('');
  const actions=x=>canEdit()?`<div class="row-actions"><button class="tiny-btn" onclick="openKitEdit(${x.id})">Editar</button><button class="tiny-btn danger" onclick="archiveKit(${x.id})">Excluir</button></div>`:'Somente leitura';
  $('#kit-body').innerHTML=currentKitRows.map(x=>`<tr><td><b>${esc(x.seq||'—')}</b></td><td>${esc(x.contractor)}</td><td>${esc(x.service||'—')}</td><td>${dateBR(x.application_date)}</td><td class="kit-project" title="${esc(x.mix_project||'')}">${esc(x.mix_project||'—')}</td><td>${esc(x.period||'—')}</td><td>${esc(x.road||'—')}</td><td>${fmtSta(x.kmi)}</td><td>${fmtSta(x.kmf)}</td><td>${dateBR(x.receipt_date)}</td><td>${statusBadge(x.delivery_status||'—')}</td><td>${statusBadge(x.status)}</td><td>${statusBadge(x.status_1)}</td><td>${statusBadge(x.status_2)}</td><td>${statusBadge(x.status_3)}</td><td>${statusBadge(x.status_4)}</td><td>${statusBadge(x.status_5)}</td><td>${statusBadge(x.status_6)}</td><td>${statusBadge(x.status_7)}</td><td>${statusBadge(x.status_8)}</td><td>${statusBadge(x.sin_retro)}</td><td>${actions(x)}</td></tr>`).join('')||'<tr><td colspan="22">Nenhum kit sincronizado para este filtro.</td></tr>';
  renderPagination('#kit-pagination',kitTotal,kitPage,kitPageSize,p=>loadKits(p),size=>{kitPageSize=size;loadKits(1)});
 }catch(e){toast(e.message,true)}
}


function humanSize(bytes){const n=Number(bytes||0);if(n<1024)return n+' B';if(n<1024*1024)return (n/1024).toFixed(1)+' KB';if(n<1024*1024*1024)return (n/1024/1024).toFixed(1)+' MB';return (n/1024/1024/1024).toFixed(1)+' GB'}
let currentKitDocuments=[];
function previewKitDocument(id){
 const item=currentKitDocuments.find(x=>Number(x.id)===Number(id))||contractorFolderDocs.find(x=>Number(x.id)===Number(id))||{};const name=item.file_name||('Documento '+id),ext=item.extension||'';
 const e=String(ext||'').toLowerCase(),url=`/api/contractor/kit-documents/${id}/file?preview=true`;let content='';
 if(e==='.pdf')content=`<iframe class="document-preview-frame" src="${url}#toolbar=1&navpanes=0" title="${esc(name)}"></iframe>`;
 else if(['.png','.jpg','.jpeg','.gif','.webp','.bmp','.svg'].includes(e))content=`<div class="document-preview-image"><img src="${url}" alt="${esc(name)}"></div>`;
 else content=`<div class="empty">Este formato não possui pré-visualização no navegador. Use o botão Abrir.</div>`;
 showModal(`<div class="document-preview-modal"><span class="eyebrow">PRÉ-VISUALIZAÇÃO</span><h2>${esc(name)}</h2>${content}<div class="edit-actions"><button class="ghost" onclick="closeModal()">Fechar</button><a class="primary button-link" target="_blank" href="/api/contractor/kit-documents/${id}/file?preview=true">Abrir em nova aba</a></div></div>`);
}
async function loadKitDocuments(){
 try{
  const contractor=$('#kit-doc-contractor')?.value||'ALL',search=$('#kit-doc-search')?.value||'';
  const q=new URLSearchParams({contractor,search,limit:'5000'});
  const list=await api('/api/contractor/kit-documents?'+q);
  currentKitDocuments=list;
  const linked=list.filter(x=>x.kit_id).length;
  const folders=new Set(list.map(x=>x.folder||'').filter(Boolean)).size;
  $('#kit-doc-summary').innerHTML=`<div class="summary-chip"><b>${list.length}</b> arquivos</div><div class="summary-chip"><b>${folders}</b> pastas</div><div class="summary-chip"><b>${linked}</b> vinculados por #SEQ</div><div class="summary-chip"><b>${list.length-linked}</b> sem vínculo automático</div>`;
  $('#kit-doc-body').innerHTML=list.map(x=>{const can=canInlinePreview(x.extension);return `<tr><td>${esc(x.contractor)}</td><td>${x.kit_seq?`<b>${esc(x.kit_seq)}</b>`:(x.seq_guess?esc(x.seq_guess):'—')}</td><td><b>${esc(x.file_name)}</b></td><td class="kit-project" title="${esc(x.relative_path||'')}">${esc(x.relative_path||'—')}</td><td>${esc((x.extension||'').replace('.','').toUpperCase()||'—')}</td><td>${humanSize(x.size)}</td><td><div class="row-actions">${can?`<button class="tiny-btn" onclick="previewKitDocument(${x.id})">Pré-visualizar</button>`:''}<a class="tiny-btn link-btn" target="_blank" href="/api/contractor/kit-documents/${x.id}/file?preview=true">Abrir</a></div></td></tr>`}).join('')||'<tr><td colspan="7">Nenhum documento indexado. Configure “Documentos dos Kits” em Administração → Sincronização.</td></tr>';
 }catch(e){toast(e.message,true)}
}

// Compatibilidade v3.8.4: bvVisibleLimit=100 foi substituído por paginação real.
let bvFileDocs=[],bvFileGroups=[],bvSelectedFolder='',bvPage=1,bvTotal=0,bvPageSize=25;
function bvFolderKey(x){return x.measurement_label||x.top_folder||topFolder(x.relative_path)}
function previewBvFile(id){const x=bvFileDocs.find(v=>Number(v.id)===Number(id))||{},ext=String(x.extension||'').toLowerCase(),url=`/api/bv-documents/${id}/file`;let content='';if(ext==='.pdf')content=`<iframe class="document-preview-frame" src="${url}#toolbar=1&navpanes=0"></iframe>`;else if(['.png','.jpg','.jpeg','.gif','.webp','.bmp','.svg'].includes(ext))content=`<div class="document-preview-image"><img src="${url}" alt="${esc(x.file_name||'Arquivo')}"></div>`;else content='<div class="empty">Pré-visualização indisponível para este formato. Use Abrir.</div>';showModal(`<div class="document-preview-modal"><span class="eyebrow">ARQUIVO BV</span><h2>${esc(x.file_name||'Arquivo')}</h2>${content}<div class="edit-actions"><button class="ghost" onclick="closeModal()">Fechar</button><a class="primary button-link" target="_blank" href="${url}">Abrir</a></div></div>`)}
function renderBvFolderList(){if(!bvSelectedFolder||!bvFileGroups.some(x=>x.group===bvSelectedFolder))bvSelectedFolder=bvFileGroups[0]?.group||'';$('#bv-folder-list').innerHTML=bvFileGroups.map(x=>`<button class="folder-item ${x.group===bvSelectedFolder?'active':''}" data-folder="${esc(x.group)}"><span>▰</span><b>${esc(x.group)}</b><small>${num(x.count,0)}</small></button>`).join('')||'<div class="empty">Nenhuma pasta indexada.</div>';$$('#bv-folder-list .folder-item').forEach(b=>b.onclick=async()=>{bvSelectedFolder=b.dataset.folder;renderBvFolderList();await loadBvFolderDocs(1)})}
function bvImportBadge(x){const s=String(x.certificate_status||'').toUpperCase();if(!s)return '';const label=s==='DUPLICADO'?'DUPLICADO':s==='ERRO'?'ERRO':s==='PARCIAL'?'PARCIAL':'CERTIFICADO';return `<span class="status-badge ${s==='DUPLICADO'?'duplicate':s==='ERRO'?'bad':s==='PARCIAL'?'warn':'ok'}">${esc(label)}</span>${x.certificate_number?`<small>${esc(x.certificate_number)}</small>`:''}`}
function renderBvFiles(){const total=bvTotal;$('#bv-folder-summary').innerHTML=bvSelectedFolder?`<div class="summary-chip"><b>${esc(bvSelectedFolder)}</b> selecionada</div><div class="summary-chip"><b>${total}</b> arquivo(s)</div>`:'';$('#bv-file-preview').innerHTML=bvFileDocs.map(x=>{const ext=String(x.extension||'').toLowerCase(),url=`/api/bv-documents/${x.id}/file`,type=ext.replace('.','').toUpperCase()||'ARQUIVO';return `<article class="file-preview-card bv-metadata-card"><div class="file-preview-media unsupported"><span>${esc(type)}</span></div><div class="file-preview-copy"><b>${esc(x.file_name)}</b><span>${esc(x.relative_path||'')}</span><div class="bv-file-status">${bvImportBadge(x)}</div><div><small>${humanSize(x.size)}</small><span class="row-actions"><button class="tiny-btn" onclick="previewBvFile(${x.id})">Pré-visualizar</button><a class="tiny-btn link-btn" target="_blank" href="${url}">Abrir</a>${canEdit()?`<button class="tiny-btn danger" onclick="deleteBvFile(${x.id})">Excluir</button>`:''}</span></div></div></article>`}).join('')||'<div class="empty">Nenhum arquivo nesta pasta.</div>';renderPagination('#bv-pagination',total,bvPage,bvPageSize,p=>loadBvFolderDocs(p),size=>{bvPageSize=size;loadBvFolderDocs(1)})}
async function loadBvFolderDocs(page=1){if(!bvSelectedFolder){bvFileDocs=[];bvTotal=0;renderBvFiles();return}try{const q=new URLSearchParams({contractor:$('#bv-file-company')?.value||'ALL',search:$('#bv-file-search')?.value||'',extension:$('#bv-file-ext')?.value||'',measurement:bvSelectedFolder,page:String(page),page_size:String(bvPageSize)}),d=await api('/api/bv-documents?'+q);bvFileDocs=d.items||[];bvPage=d.page||page;bvTotal=Number(d.total||0);renderBvFiles()}catch(e){toast(e.message,true)}}
async function deleteBvFile(id){if(!confirm('Remover este arquivo da visualização do QualiMatch?\n\nO arquivo original no SharePoint/OneDrive NÃO será apagado.'))return;try{const d=await api(`/api/bv-documents/${id}`,{method:'DELETE'});toast(d.message||'Arquivo removido.');await loadBvFiles(true)}catch(e){toast(e.message,true)}}
async function cleanupBvDuplicates(){
 if(!canEdit())return toast('Seu perfil é somente leitura.',true);
 const contractor=$('#bv-file-company')?.value||'ALL',scope=contractor==='ALL'?'Arena + Pavidez':contractor;
 if(!confirm(`Remover de uma vez todos os arquivos BV marcados como DUPLICADO em ${scope}?\n\nO QualiMatch mantém a ocorrência original de cada certificado e remove somente as cópias duplicadas da visualização. Nenhum arquivo físico do SharePoint/OneDrive será apagado.`))return;
 const btn=$('#bv-file-clean-duplicates'),old=btn?.textContent||'Remover duplicados';
 if(btn){btn.disabled=true;btn.textContent='Limpando...'}
 try{const d=await api('/api/bv-documents/remove-duplicates?contractor='+encodeURIComponent(contractor),{method:'POST'});toast(d.message||'Duplicados removidos.');await loadBvFiles(false)}catch(e){toast(e.message,true)}finally{if(btn){btn.disabled=false;btn.textContent=old}}
}
async function loadBvFiles(keepFolder=false){try{const q=new URLSearchParams({contractor:$('#bv-file-company')?.value||'ALL',search:$('#bv-file-search')?.value||'',extension:$('#bv-file-ext')?.value||''});bvFileGroups=await api('/api/bv-documents/groups?'+q);if(!keepFolder)bvSelectedFolder='';renderBvFolderList();await loadBvFolderDocs(1)}catch(e){toast(e.message,true)}}

let contractorFolderDocs=[],contractorFolderGroups=[],contractorSelectedFolder='';
function topFolder(path){const p=String(path||'').replaceAll('\\','/').replace(/^\/+|\/+$/g,'');if(!p)return '(raiz)';const parts=p.split('/');return parts.length>1?parts[0]:'(raiz)'}
function canInlinePreview(ext){return ['.pdf','.png','.jpg','.jpeg','.gif','.webp','.bmp','.svg'].includes(String(ext||'').toLowerCase())}
function folderFileCard(x){
 const url=`/api/contractor/kit-documents/${x.id}/file?preview=true`,ext=String(x.extension||'').toLowerCase();
 let preview='';
 if(['.png','.jpg','.jpeg','.gif','.webp','.bmp','.svg'].includes(ext)) preview=`<div class="file-preview-media"><img loading="lazy" src="${url}" alt="${esc(x.file_name)}"></div>`;
 else if(ext==='.pdf') preview=`<div class="file-preview-media unsupported"><span>PDF</span><button class="tiny-btn" onclick="previewKitDocument(${x.id})">Visualizar documento</button></div>`;
 else preview=`<div class="file-preview-media unsupported"><span>${esc((ext||'arquivo').replace('.','').toUpperCase())}</span><small>Prévia no navegador não disponível</small></div>`;
 return `<article class="file-preview-card">${preview}<div class="file-preview-copy"><b title="${esc(x.file_name)}">${esc(x.file_name)}</b><span>${esc(x.relative_path||'')}</span><div><small>${humanSize(x.size)}</small><span class="row-actions"><button class="tiny-btn" onclick="previewKitDocument(${x.id})">Visualizar</button><a class="tiny-btn link-btn" target="_blank" href="/api/contractor/kit-documents/${x.id}/file?preview=true">Abrir</a></span></div></div></article>`;
}
function renderContractorFolderBrowser(){
 const folders=contractorFolderGroups.map(x=>x.folder);
 if(!contractorSelectedFolder||!folders.includes(contractorSelectedFolder))contractorSelectedFolder=folders[0]||'';
 $('#contractor-folder-list').innerHTML=contractorFolderGroups.map(x=>`<button class="folder-item ${x.folder===contractorSelectedFolder?'active':''}" data-folder="${esc(x.folder)}"><span>▰</span><b>${esc(x.folder)}</b><small>${x.count}</small></button>`).join('')||'<div class="empty">Nenhuma pasta indexada.</div>';
 $$('#contractor-folder-list .folder-item').forEach(b=>b.onclick=async()=>{contractorSelectedFolder=b.dataset.folder;await loadContractorFolderDocs()});
 const count=contractorFolderGroups.find(x=>x.folder===contractorSelectedFolder)?.count||0;
 $('#contractor-folder-summary').innerHTML=contractorSelectedFolder?`<div class="summary-chip"><b>${esc(contractorSelectedFolder)}</b> pasta selecionada</div><div class="summary-chip"><b>${count}</b> arquivo(s)</div><div class="summary-chip">Carregados somente os arquivos desta pasta</div>`:'';
 $('#contractor-file-preview').innerHTML=contractorFolderDocs.map(folderFileCard).join('')+(count>contractorFolderDocs.length?`<div class="empty preview-limit">Mostrando ${contractorFolderDocs.length} de ${count} arquivos. Use a busca para refinar.</div>`:'')||'<div class="empty">Nenhum arquivo nesta pasta.</div>';
}
async function loadContractorFolderDocs(){const contractor=$('#contractor-doc-company')?.value||'ALL',search=$('#contractor-doc-search')?.value||'';contractorFolderDocs=contractorSelectedFolder?await api('/api/contractor/kit-documents?'+new URLSearchParams({contractor,limit:'5000',top_folder:contractorSelectedFolder,search})):[];renderContractorFolderBrowser()}
async function loadContractorFolderBrowser(){
 try{
  const contractor=$('#contractor-doc-company')?.value||'ALL';
  contractorFolderGroups=await api('/api/contractor/kit-document-folders?contractor='+encodeURIComponent(contractor));
  contractorSelectedFolder='';renderContractorFolderBrowser();await loadContractorFolderDocs();
 }catch(e){toast(e.message,true)}
}
async function loadContractorPending(){
 try{
  // Compatibilidade da rota anterior: /api/contractor/pending?contractor=
  const contractor=$('#contractor-pending-company')?.value||'ALL';
  const view=await api('/api/contractor/pending-view?contractor='+encodeURIComponent(contractor)),d=view.items||[],justified=view.justified||[];
  window._contractorPendingItems=new Map(d.map(x=>[x.pending_key,x]));
  const missingDate=d.filter(x=>x.pending_reason==='DATA_NAO_PREENCHIDA').length;
  $('#contractor-pending-summary').innerHTML=`<div class="summary-chip"><b>${d.length}</b> pendência(s) ativa(s)</div><div class="summary-chip"><b>${justified.length}</b> justificada(s)</div>${missingDate?`<div class="summary-chip"><b>${missingDate}</b> linha(s) sem Data aplicação</div>`:''}`;
  $('#contractor-pending-body').innerHTML=d.map(x=>`<tr><td>${esc(x.contractor)}</td><td><b>${esc(x.measurement||'—')}</b><small class="table-sub">${x.measurement_start?dateBR(x.measurement_start)+' a '+dateBR(x.measurement_end):''}</small></td><td>${x.pending_reason==='DATA_NAO_PREENCHIDA'?'<span class="cert-date-warning">⚠ Data não preenchida</span>':dateBR(x.date)}</td><td>${esc(x.road||'—')}</td><td>${x.kmi==null&&x.kmf==null?'—':`${fmtSta(x.kmi)} a ${fmtSta(x.kmf)}`}</td><td>${num(x.lines,0)}</td><td>${statusBadge(x.delivery_status||'NÃO ENTREGUE')}</td><td>${statusBadge(x.status)}</td><td>${canEdit()?`<button class="tiny-btn" onclick="justifyContractorPending('${encodeURIComponent(x.pending_key)}')">Justificar</button>`:'—'}</td></tr>`).join('')||'<tr><td colspan="9">Nenhuma pendência ativa.</td></tr>';
  $('#contractor-justified-body').innerHTML=justified.map(x=>`<tr><td>${esc(x.contractor)}</td><td>${dateBR(x.date)}</td><td>${esc(x.road||'—')}</td><td>${esc(x.justification)}</td><td>${esc(x.justified_at||'—')}</td><td>${canEdit()?`<button class="tiny-btn" onclick="restoreContractorPending('${encodeURIComponent(x.pending_key)}')">Reabrir</button>`:'—'}</td></tr>`).join('')||'<tr><td colspan="6">Nenhuma pendência justificada.</td></tr>';
 }catch(e){toast(e.message,true)}
}
window.justifyContractorPending=async encoded=>{const key=decodeURIComponent(encoded),item=window._contractorPendingItems?.get(key);if(!item)return;const reason=prompt('Informe por que esta pendência não pode mais ser tratada:','');if(!reason)return;try{await api('/api/contractor/pending/justify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pending_key:key,contractor:item.contractor,reason,item})});toast('Pendência justificada e separada.');loadContractorPending()}catch(e){toast(e.message,true)}};
window.restoreContractorPending=async encoded=>{if(!confirm('Reabrir esta pendência?'))return;try{await api('/api/contractor/pending/justify/'+encoded,{method:'DELETE'});toast('Pendência reaberta.');loadContractorPending()}catch(e){toast(e.message,true)}};

const kindNames={medicao:'Medição',qualidade:'Qualidade oficial',kits:'Tabela de Kits',kit_documentos:'Documentos dos Kits',certificados:'Pasta de certificados',bv_documentos:'Arquivos BV por medição',bd_quali_auto:'Preenchimento BD_QUALI',certificado_edicao:'Edição de certificado'};
let monitorPage=1,monitorTotal=0,monitorPageSize=25;
async function loadAutoMonitor(page=1){
 try{
  const d=await api(`/api/admin/auto-monitor?page=${page}&page_size=${monitorPageSize}`),c=d.config||{};monitorPage=d.page||page;monitorTotal=Number(d.total||0);
  if($('#auto-monitor-enabled'))$('#auto-monitor-enabled').checked=!!c.enabled;
  if($('#auto-monitor-bv'))$('#auto-monitor-bv').checked=!!c.bv;
  if($('#auto-monitor-contractor'))$('#auto-monitor-contractor').checked=!!c.contractor;
  if($('#auto-monitor-quality'))$('#auto-monitor-quality').checked=c.auto_quality!==false;
  if($('#auto-monitor-seconds'))$('#auto-monitor-seconds').value=String(c.seconds||15);
  const badge=$('#auto-monitor-badge');if(badge){badge.textContent=c.enabled?'ATIVO':'PAUSADO';badge.className='badge '+(c.enabled?'ok':'warn')}
  const events=d.events||[];
  $('#auto-monitor-events').innerHTML=events.map(x=>`<tr><td>${esc(x.detected_at||'—')}</td><td>${esc(x.portal||'—')}</td><td>${esc(x.contractor||'—')}</td><td>${esc(kindNames[x.kind]||x.kind)}</td><td class="kit-project" title="${esc(x.file_path||'')}">${esc(x.file_name||'—')}</td><td>${esc(x.event_type||'—')}</td><td>${statusBadge(x.status||'—')}</td><td class="monitor-result" title="${esc(x.message||'')}">${esc(x.message||'—')}</td></tr>`).join('')||'<tr><td colspan="8" class="empty">Nenhum arquivo detectado automaticamente ainda.</td></tr>';
  renderPagination('#auto-monitor-pagination',monitorTotal,monitorPage,monitorPageSize,p=>loadAutoMonitor(p),size=>{monitorPageSize=size;loadAutoMonitor(1)});
 }catch(e){if($('#auto-monitor-events'))$('#auto-monitor-events').innerHTML=`<tr><td colspan="8" class="bad-text">${esc(e.message)}</td></tr>`}
}
async function saveAutoMonitor(){try{const body={enabled:!!$('#auto-monitor-enabled')?.checked,bv:!!$('#auto-monitor-bv')?.checked,contractor:!!$('#auto-monitor-contractor')?.checked,auto_quality:!!$('#auto-monitor-quality')?.checked,seconds:Number($('#auto-monitor-seconds')?.value||15)};await api('/api/admin/auto-monitor',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});toast('Monitor automático atualizado.');loadAutoMonitor()}catch(e){toast(e.message,true)}}
async function runAutoMonitor(){try{toast('Verificando pastas sincronizadas...');const d=await api('/api/admin/auto-monitor/run',{method:'POST'});toast(d.detected?`${d.detected} alteração(ões) detectada(s); ${d.processed} processada(s).`:'Nenhum arquivo novo encontrado.',!!d.errors);await Promise.all([loadAutoMonitor(),loadSources()])}catch(e){toast(e.message,true)}}
function sourceCountSummary(x){const stats=x.read_stats||{};if(x.kind==='certificados')return `${num(stats.found||x.current_count||0,0)} encontrados • ${num(stats.read_ok||0,0)} lidos corretamente • ${num(stats.ignored||0,0)} ignorados • ${num(stats.errors||0,0)} com erro`;if(x.kind==='bv_documentos')return `${num(x.current_count||0,0)} arquivos indexados • ${num(stats.found||0,0)} BI330 encontrados • ${num(stats.read_ok||0,0)} lidos corretamente • ${num(stats.errors||0,0)} com erro`;if(x.kind==='kit_documentos')return `${num(x.current_count||0,0)} arquivo(s) na árvore`;return esc(x.worksheet||'Arquivo local')}
async function loadSources(){
 try{await loadAutoMonitor();const s=await api('/api/sources');let html='';for(const c of ['ARENA','PAVIDEZ']){const group=s.filter(x=>x.contractor===c);html+=`<div class="section-title"><div><span class="eyebrow">${c}</span><h2>Fontes sincronizadas</h2></div></div>`;html+=group.map(x=>`<div class="source-card ${x.kind==='certificados'?'cert-source':''}" data-source="${x.contractor}-${x.kind}"><div><div class="source-kind">${kindNames[x.kind]||x.kind}</div><b>${sourceCountSummary(x)}</b><div class="meta">${statusBadge(x.last_status)}</div></div><div><input class="path-input" value="${esc(x.path||'')}" placeholder="${['certificados','kit_documentos','bv_documentos'].includes(x.kind)?'C:\\...\\Pasta local sincronizada':'C:\\...\\arquivo.xlsx'}"><div class="meta">${x.exists?'Encontrado':'Não encontrado'} ${x.current_mtime?'• atualização '+esc(x.current_mtime):''}${x.last_error?' • '+esc(x.last_error):''}</div></div><div>${x.kind==='kits'?`<button class="ghost compact" title="Procura a planilha dentro da pasta local sincronizada da contratada" onclick="discoverKits('${x.contractor}')">Localizar</button> `:''}${x.kind==='bv_documentos'?`<button class="ghost compact" title="Localiza a pasta atual da BV" onclick="discoverBvSource('${x.contractor}')">Localizar pasta</button> `:''}<button onclick="saveSource('${x.contractor}','${x.kind}','${esc(x.worksheet||'')}',this)">Salvar</button> <button class="primary" onclick="syncOne('${x.contractor}','${x.kind}',false)">Sincronizar</button> <button class="ghost compact" title="Reprocessa mesmo sem alteração; use apenas para diagnóstico" onclick="syncOne('${x.contractor}','${x.kind}',true)">Reprocessar</button></div></div>`).join('')}$('#sources').innerHTML=html}catch(e){toast(e.message,true)}
}
async function saveSource(c,k,w,btn){try{const card=btn.closest('.source-card');await api(`/api/sources/${c}/${k}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:card.querySelector('input').value,worksheet:w})});toast('Caminho salvo.');loadSources()}catch(e){toast(e.message,true)}}
async function discoverKits(c){try{toast(`Procurando a tabela de kits da ${c} na pasta local sincronizada...`);const d=await api(`/api/sources/${c}/kits/discover`,{method:'POST'});toast('Planilha localizada: '+d.path);loadSources()}catch(e){toast(e.message,true)}}
async function discoverBvSource(c){try{toast(`Procurando a pasta atual da BV / ${c}...`);const d=await api(`/api/sources/${c}/bv-documentos/discover`,{method:'POST'});toast('Pasta localizada: '+d.path);loadSources()}catch(e){toast(e.message,true)}}
async function syncOne(c,k,force=false){try{toast(`${force?'Reprocessando':'Verificando'} ${c} / ${kindNames[k]||k}...`);const d=await api(`/api/sync/${c}/${k}?force=${force?'true':'false'}`,{method:'POST'});let msg=d.message||'Sincronizado.';if(d.auto_quality?.written_certificates)msg+=` • BD_QUALI: ${d.auto_quality.written_certificates} certificado(s), ${d.auto_quality.written_rows} linha(s) gravadas automaticamente.`;else if(d.auto_quality?.review)msg+=` • ${d.auto_quality.review} certificado(s) aguardando revisão para BD_QUALI.`;toast(msg,!d.ok||!!d.auto_quality?.errors);loadSources();loadDash()}catch(e){toast(e.message,true)}}

function renderPagination(target,total,page,pageSize,onChange,onSizeChange){
 const box=$(target);if(!box)return;
 const pages=Math.max(1,Math.ceil(total/pageSize));page=Math.min(Math.max(1,page),pages);
 const start=(page-1)*pageSize+1,end=Math.min(total,page*pageSize),items=[];
 const from=Math.max(1,page-2),to=Math.min(pages,page+2);
 items.push(`<button ${page===1?'disabled':''} data-page="${page-1}">‹ Anterior</button>`);
 if(from>1){items.push('<button data-page="1">1</button>');if(from>2)items.push('<span class="pagination-ellipsis">…</span>')}
 for(let p=from;p<=to;p++)items.push(`<button class="${p===page?'active':''}" data-page="${p}">${p}</button>`);
 if(to<pages){if(to<pages-1)items.push('<span class="pagination-ellipsis">…</span>');items.push(`<button data-page="${pages}">${pages}</button>`)}
 items.push(`<button ${page===pages?'disabled':''} data-page="${page+1}">Próxima ›</button>`);
 const sizeControl=onSizeChange?`<label class="pagination-size">Itens por página <select>${[25,50,100].map(n=>`<option value="${n}" ${n===pageSize?'selected':''}>${n}</option>`).join('')}</select></label>`:'';
 box.innerHTML=`<span class="pagination-info">${total?`${start}–${end}`:'0'} de ${total}</span>${total>pageSize?`<div class="pagination-buttons">${items.join('')}</div>`:''}${sizeControl}`;
 box.querySelectorAll('button[data-page]').forEach(b=>b.onclick=()=>{const p=Number(b.dataset.page);if(p>=1&&p<=pages)onChange(p)});
 const size=box.querySelector('.pagination-size select');if(size&&onSizeChange)size.onchange=()=>onSizeChange(Number(size.value));
}
let measurementList=[],measurementPage=1,measurementTotal=0,measurementPageSize=25;
function renderMeasurements(){
 const d=measurementList,page=d;
 const digits={extension:groupDecimals(d.map(x=>x.extension_m),0,3),width:groupDecimals(d.map(x=>x.width_m),0,3),thickness:groupDecimals(d.map(x=>x.thickness_m==null?null:Number(x.thickness_m)*100),0,3),volume:groupDecimals(d.map(x=>x.volume_mass_m3),0,3)};
 $('#m-body').innerHTML=page.map(x=>`<tr><td>${esc(x.line_measurement||'—')}</td><td>${x.contractor}</td><td>${dateBR(x.date)}</td><td>${esc(x.ref_measurement||'')}</td><td>${esc(x.road||'')}</td><td>${esc(x.direction||'')}</td><td>${fmtSta(x.kmi)}</td><td>${fmtSta(x.kmf)}</td><td>${esc(x.lane||'')}</td><td>${groupNum(x.extension_m,digits.extension)} m</td><td>${groupNum(x.width_m,digits.width)} m</td><td>${x.thickness_m==null?'—':groupNum(Number(x.thickness_m)*100,digits.thickness)+' cm'}</td><td>${groupNum(x.volume_mass_m3,digits.volume)} m³</td><td><button class="tiny-btn" onclick="openTraceability(${x.id})">Ver fluxo</button></td></tr>`).join('')||'<tr><td colspan="14">Sem dados.</td></tr>';
 renderPagination('#m-pagination',measurementTotal,measurementPage,measurementPageSize,p=>loadMeasurements(p),size=>{measurementPageSize=size;loadMeasurements(1)});
}
async function loadMeasurements(page=1){try{const q=new URLSearchParams({contractor:$('#m-contractor').value,search:$('#m-search').value,page:String(page),page_size:String(measurementPageSize)}),d=await api('/api/measurements?'+q);measurementList=d.items||[];measurementPage=d.page||page;measurementTotal=Number(d.total||0);renderMeasurements()}catch(e){toast(e.message,true)}}

let certList=[],certificatePage=1,certificateTotal=0,certificatePageSize=25,certificateSummary={};
async function loadCertificateFilterOptions(){
 const sel=$('#c-road'),numberSel=$('#c-number'),measurementSel=$('#c-measurement'),current=sel.value,currentNumber=numberSel?.value||'',currentMeasurement=measurementSel?.value||'',contractor=$('#c-contractor').value;
 try{const d=await api('/api/certificates-filter-options?contractor='+encodeURIComponent(contractor));sel.innerHTML='<option value="">Todas as BR/PR</option>'+(d.roads||[]).map(r=>`<option value="${esc(r)}">${esc(r)}</option>`).join('');if((d.roads||[]).includes(current))sel.value=current;if(numberSel){numberSel.innerHTML='<option value="">Todos os certificados</option>'+(d.numbers||[]).map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('');if((d.numbers||[]).includes(currentNumber))numberSel.value=currentNumber}if(measurementSel){measurementSel.innerHTML='<option value="">Todas as medições</option>'+(d.measurements||[]).map(x=>`<option value="${esc(x.measurement)}">${esc(measurementOptionLabel(x))}</option>`).join('');if((d.measurements||[]).some(x=>x.measurement===currentMeasurement))measurementSel.value=currentMeasurement}}catch(e){toast('Não foi possível carregar as opções dos certificados: '+e.message,true)}
}
async function loadCertificates(page=1){
 if(!$('#page-certificates')?.classList.contains('active'))return;
 try{
  await loadCertificateFilterOptions();
  const q=new URLSearchParams({contractor:$('#c-contractor').value,measurement:$('#c-measurement')?.value||'',search:'',sort:$('#c-sort').value,status:'ALL',vv_status:$('#c-vv-status').value,thickness_status:$('#c-thickness-status').value,road:$('#c-road').value,segment:$('#c-segment').value,number:$('#c-number')?.value||'',counterproof:$('#c-counterproof')?.value||'ALL',date_issue:$('#c-date-issue')?.value||'ALL',page:String(page),page_size:String(certificatePageSize)});
  const d=await api('/api/certificates?'+q);certList=d.items||[];certificatePage=d.page||page;certificateTotal=Number(d.total||0);certificateSummary=d.summary||{};renderCertificateList()
 }catch(e){toast(e.message,true)}
}
function renderCertificateList(){
 const list=certList,pageList=list,s=certificateSummary,ap=Number(s.approved||0),rp=Number(s.reproved||0),adj=Number(s.adjustments||0),cp=Number(s.counterproof||0),partial=Number(s.partial||0),loaded=Number(s.loaded||0);
 const digits={thickness:groupDecimals(list.map(x=>x.mean_thickness_cm),0,3),ratio:groupDecimals(list.map(x=>x.mean_ratio),0,3)};
 const dups=Number(s.duplicates||0); $('#certificate-summary').innerHTML=`<div class="summary-chip"><b>${certificateTotal}</b> encontrados</div><div class="summary-chip"><b>${ap}</b> aprovados</div><div class="summary-chip"><b>${rp}</b> reprovados</div><div class="summary-chip"><b>${adj}</b> ajustes / sem resultado</div><div class="summary-chip"><b>${cp}</b> com contra-prova <small>já inclusos no total</small></div><div class="summary-chip"><b>${loaded}</b> carregados</div><div class="summary-chip"><b>${partial}</b> leitura parcial</div><div class="summary-chip"><b>${dups}</b> duplicado(s)</div><div class="cert-legend"><span><i class="legend-approved"></i>Verde: aprovado</span><span><i class="legend-reproved"></i>Vermelho: reprovado</span><span><i class="legend-adjust"></i>Amarelo: ajustes</span><span><i class="legend-duplicate"></i>Roxo: duplicado</span></div>`;
 $('#c-body').innerHTML=pageList.map(x=>{
  const activeDocs=(x.documents||[]).filter(d=>!['SUBSTITUIDO','EXCLUIDO'].includes(String(d.status||'').toUpperCase()));
  const doc=activeDocs.find(d=>d.kind==='CONTRA_PROVA')||activeDocs[0];
  const segment=(x.kmi!=null&&x.kmf!=null)?`${fmtSta(x.kmi)} a ${fmtSta(x.kmf)}`:'Segmento não identificado';
  const dateIssue=(x.business_warnings||[]).some(w=>String(w||'').includes('Data de recebimento em laboratório anterior à Data Ext. dos CPs'));
  const rowClass=x.has_duplicate?'cert-row-duplicate':dateIssue?'cert-row-date-warning':x.overall_status==='APROVADO'?'cert-row-approved':x.overall_status==='REPROVADO'?'cert-row-reproved':'';
  const dateWarn=dateIssue?`<span class="sub cert-date-warning">⚠ Data inconsistente</span>`:''; const dupWarn=x.has_duplicate?`<span class="duplicate-badge">DUPLICADO × ${num(x.duplicate_count||1,0)}</span>`:'';
  return `<tr class="${rowClass}"><td><button class="cert-link" onclick="openCertificate(${x.id})">${esc(x.number)}</button><span class="sub">${esc(x.contractor)} • ${phaseLabel(x.final_phase)}</span>${dupWarn}</td><td>${dateBR(x.certificate_date||x.extraction_date||x.service_date)}${dateWarn}</td><td><b>${esc(x.road||'Rodovia não identificada')}</b><span class="sub">${segment}</span></td><td title="${esc(x.trace_approved||'')}">${esc((x.trace_approved||'—').slice(0,36))}${(x.trace_approved||'').length>36?'…':''}</td><td>${num(x.sample_count,0)}</td><td><b>${vvPct(x.mean_vv)}</b></td><td><b>${groupCm(x.mean_thickness_cm,digits.thickness)}</b></td><td>${groupPct(x.mean_ratio,digits.ratio)}</td><td>${statusBadge(x.status_vv)}</td><td>${statusBadge(x.status_thickness)}</td><td>${statusBadge(x.counterproof_state||((x.counterproof_delivered||x.has_counterproof)?'ENTREGUE':'NÃO'))}</td><td title="${esc((x.parse_warnings||[]).join(' • '))}">${statusBadge(readStatus(x.parse_status))}</td><td>${doc?`<a target="_blank" href="/api/certificate-files/${doc.id}/file">Abrir</a>`:`<a target="_blank" href="/api/certificates/${x.id}/file">Abrir</a>`}</td></tr>`
 }).join('')||'<tr><td colspan="13">Nenhum certificado encontrado com esses filtros.</td></tr>';
 renderPagination('#c-pagination',certificateTotal,certificatePage,certificatePageSize,p=>loadCertificates(p),size=>{certificatePageSize=size;loadCertificates(1)});
}
function clearCertificateFilters(){
 $('#c-contractor').value='ALL';if($('#c-measurement'))$('#c-measurement').value='';$('#c-sort').value='newest';$('#c-vv-status').value='ALL';$('#c-thickness-status').value='ALL';$('#c-road').value='';$('#c-segment').value='';if($('#c-number'))$('#c-number').value='';if($('#c-counterproof'))$('#c-counterproof').value='ALL';if($('#c-date-issue'))$('#c-date-issue').value='ALL';loadCertificates();
}
async function removeCertificateDuplicates(){
 if(!canEdit())return toast('Seu perfil é somente leitura.',true);
 const contractor=$('#c-contractor')?.value||'ALL',scope=contractor==='ALL'?'Arena + Pavidez':contractor;
 const count=certList.filter(x=>x.has_duplicate).length;
 if(!confirm(`Remover todas as cópias DUPLICADAS da aba Certificados em ${scope}?\n\nSerão removidas somente cópias que o QualiMatch já confirmou como conteúdo técnico duplicado. Certificados com o mesmo número, mas data/trecho/conteúdo diferentes, NÃO serão apagados. Uma ocorrência original será preservada.\n\n${count?`Há ${count} certificado(s) com duplicidade visível no filtro atual.`:'A rotina verificará toda a contratada selecionada.'}`))return;
 const btn=$('#c-remove-duplicates'),old=btn?.textContent||'Remover duplicados';
 if(btn){btn.disabled=true;btn.textContent='Removendo...'}
 try{
  const d=await api('/api/certificates/remove-duplicates?contractor='+encodeURIComponent(contractor),{method:'POST'});
  toast(d.message||'Duplicados removidos.');
  await Promise.all([loadCertificates(),loadBvFiles(true)]);
 }catch(e){toast(e.message,true)}
 finally{if(btn){btn.disabled=false;btn.textContent=old}}
}

async function reprocessNoResultCertificates(){
 if(!isAdmin())return toast('Apenas o administrador pode reprocessar a base em lote.',true);
 const contractor=$('#c-contractor')?.value||'ALL';
 const scope=contractor==='ALL'?'Arena + Pavidez':contractor;
 if(!confirm(`Validar todos os certificados BV com situação SEM RESULTADO em ${scope}?\n\nO QualiMatch vai abrir somente os PDFs já vinculados, reprocessá-los com o parser atual e atualizar os CPs/status dos certificados. A BD_QUALI não será alterada por esta rotina.`))return;
 const btn=$('#c-reprocess-no-result'),msg=$('#c-reprocess-msg'),old=btn?.textContent||'Validar sem resultado';
 if(btn){btn.disabled=true;btn.textContent='Validando...'}
 if(msg)msg.textContent='Reprocessando somente certificados sem resultado. Em bases grandes isso pode levar alguns minutos...';
 try{
  const d=await api('/api/certificates/reprocess-no-result?contractor='+encodeURIComponent(contractor),{method:'POST'});
  const reasons=Object.entries(d.reason_counts||{}).sort((a,b)=>b[1]-a[1]).slice(0,4).map(([r,n])=>`${n}× ${r}`).join(' • ');
  if(msg)msg.innerHTML=`<b>${num(d.total_before||0,0)}</b> validados • <b class="ok-text">${num(d.fixed||0,0)} corrigidos</b> • <b>${num(d.remaining||0,0)} ainda sem resultado</b> • ${num(d.missing_files||0,0)} PDF(s) local(is) não encontrado(s) • ${num(d.unsupported_files||0,0)} compilação(ões) de passivos ignorada(s)${reasons?`<br><span>${esc(reasons)}</span>`:''}`;
  toast(d.message||'Validação concluída.',Number(d.errors||0)>0);
  await Promise.all([loadCertificates(),loadDash()]);
 }catch(e){if(msg)msg.innerHTML=`<span class="bad-text">${esc(e.message)}</span>`;toast(e.message,true)}
 finally{if(btn){btn.disabled=false;btn.textContent=old}}
}

async function uploadCert(){
 if(!canEdit())return toast('Seu perfil é somente leitura.',true);
 const files=[...$('#c-file').files];if(!files.length)return toast('Selecione um ou mais PDFs.',true);
 let loaded=0,partial=0,fail=0;$('#c-upload-msg').textContent=`Processando ${files.length} PDF(s)...`;
 for(const f of files){
  const fd=new FormData();fd.append('contractor',$('#c-upload-contractor').value);fd.append('file',f);
  try{const d=await api('/api/certificates/upload',{method:'POST',body:fd});if(readStatus(d.parse_status)==='CARREGADO')loaded++;else partial++}
  catch(e){fail++;toast(`${f.name}: ${e.message}`,true)}
 }
 $('#c-upload-msg').textContent=`${loaded} carregado(s) • ${partial} parcial(is) • ${fail} erro(s).`;$('#c-file').value='';
 toast(`${loaded+partial} certificado(s) processado(s).`,!!fail);loadCertificates();loadDash()
}

window.replaceCertificate=id=>{
 const input=document.createElement('input');input.type='file';input.accept='application/pdf';input.hidden=true;
 input.onchange=async()=>{
  const file=input.files?.[0];input.remove();if(!file)return;
  if(!confirm('Substituir este certificado pelo PDF selecionado?\n\nO PDF anterior será preservado no histórico e um backup automático do banco será criado.'))return;
  const fd=new FormData();fd.append('file',file);
  try{
   toast('Substituindo e reprocessando certificado...');
   const d=await api(`/api/certificates/${id}/replace`,{method:'POST',body:fd});
   closeModal();toast(d.message||'Certificado substituído.');
   await Promise.all([loadCertificates(),loadDash(),loadPending()]);
  }catch(e){toast(e.message,true)}
 };
 document.body.appendChild(input);input.click();
};

window.deleteCertificate=async(id,number)=>{
 const ok=confirm(`Excluir ${number||'este certificado'} do QualiMatch?\n\nEle sairá das estatísticas, listas e vínculos. O registro e os PDFs serão preservados como histórico, e um backup automático será criado.`);
 if(!ok)return;
 try{
  const d=await api(`/api/certificates/${id}`,{method:'DELETE'});
  closeModal();toast(d.message||'Certificado excluído.');
  await Promise.all([loadCertificates(),loadDash(),loadPending()]);
 }catch(e){toast(e.message,true)}
};

window.openCertificate=async id=>{
 try{
  const c=await api(`/api/certificates/${id}`);const raw=c.raw||{};
  const docs=[...(c.documents||[])].sort((a,b)=>{const oldA=['SUBSTITUIDO','EXCLUIDO'].includes(String(a.status||'').toUpperCase()),oldB=['SUBSTITUIDO','EXCLUIDO'].includes(String(b.status||'').toUpperCase());return Number(oldA)-Number(oldB)}).map(d=>{const historical=['SUBSTITUIDO','EXCLUIDO'].includes(String(d.status||'').toUpperCase());const docStatus=historical?d.status:c.parse_status;return `<div class="doc-item ${historical?'doc-history':''}">${statusBadge(d.kind==='CONTRA_PROVA'?'CONTRA-PROVA':'ROTINA')} ${statusBadge(readStatus(docStatus))} <span>${esc(d.file_name)}</span> <a target="_blank" href="/api/certificate-files/${d.id}/file">Abrir PDF</a></div>`}).join('')||`<div class="doc-item"><a target="_blank" href="/api/certificates/${c.id}/file">Abrir PDF principal</a></div>`;
  const dateList=a=>(a||[]).map(dateBR).join(', ')||'—';
  const serviceDates=(raw.service_dates&&raw.service_dates.length)?raw.service_dates:(c.service_date?[c.service_date]:[]);
  const phases=(c.phases||[]).map(f=>{
   const vvFailState=Number(f.vv_failed_samples||0)>0?'REPROVADO':'APROVADO';
   const ratioFailState=Number(f.ratio_failed_samples||0)>0?'REPROVADO':'APROVADO';
   const samples=f.samples||[];
   const digits={
    thicknessExec:groupDecimals([...samples.map(x=>x.thickness_exec_cm),f.thickness_mean_cm,f.thickness_min_cm,f.thickness_max_cm],0,3),
    thicknessProject:groupDecimals(samples.map(x=>x.thickness_project_cm),0,3),
    ratio:groupDecimals([...samples.map(x=>x.ratio_ab_pct),f.ratio_mean_pct,f.ratio_xmin_pct,f.ratio_xmax_pct],0,3),
    rice:groupDecimals(samples.map(x=>x.rice_gmm),0,3),
    gmb:groupDecimals(samples.map(x=>x.gmb),0,3),
    k:groupDecimals([f.k],0,3)
   };
   const sampleRows=samples.map(x=>{const vvClass=sampleState(x.voids_pct,'vv'),ratioClass=sampleState(x.ratio_ab_pct,'ratio'),rowClass=(vvClass==='value-bad'||ratioClass==='value-bad')?'cp-row-reproved':'cp-row-approved';const edit=isAdmin()?`<td><button class="ghost compact" onclick="editCertificateSample(${c.id},${x.id})">Editar</button></td>`:'';return `<tr class="${rowClass}"><td><b>${esc(x.cp_number)}</b></td><td>${dateBR(x.application_date)}</td><td>${x.counterproof?statusBadge('SIM'):statusBadge('NÃO')}</td><td>${esc(x.direction||'—')}</td><td>${esc(x.lane||'—')}</td><td>${fmtSta(x.station)}</td><td>${esc(x.position||'—')}</td><td>${groupCm(x.thickness_exec_cm,digits.thicknessExec)}</td><td>${groupCm(x.thickness_project_cm,digits.thicknessProject)}</td><td class="${ratioClass}">${groupPct(x.ratio_ab_pct,digits.ratio)}</td><td>${groupNum(x.rice_gmm,digits.rice)}</td><td>${groupNum(x.gmb,digits.gmb)}</td><td class="${vvClass}">${vvPct(x.voids_pct)}</td>${edit}</tr>`}).join('');
   const phaseEdit=isAdmin()?`<button class="ghost compact" onclick="editCertificatePhase(${c.id},'${f.phase}')">Editar resumo/status</button>`:'';
   return `<div class="phase-card ${stateClass(f.overall_status)}"><div class="phase-head"><div class="phase-title"><span class="eyebrow">FASE</span><h3>${phaseLabel(f.phase)}</h3></div><div class="phase-k"><span>K</span><b>${groupNum(f.k,digits.k)}</b></div><div class="phase-status">${statusBadge(f.overall_status)} ${statusBadge('VV '+(f.status_vv||'—'))} ${statusBadge('ESP '+(f.status_thickness||'—'))} ${phaseEdit}</div></div><div class="phase-metrics">${phaseMetric('VV médio',vvPct(f.vv_mean_pct),`Xmin ${vvPct(f.vv_xmin_pct)} • Xmax ${vvPct(f.vv_xmax_pct)}`,f.status_vv)}${phaseMetric('Desvio padrão',vvPct(f.vv_std_pct),'Dispersão do VV')}${phaseMetric('Esp. executada média',groupCm(f.thickness_mean_cm,digits.thicknessExec),`${groupCm(f.thickness_min_cm,digits.thicknessExec)} a ${groupCm(f.thickness_max_cm,digits.thicknessExec)}`,f.status_thickness)}${phaseMetric('Esp. média (%)',groupPct(f.ratio_mean_pct,digits.ratio),`Xmin ${groupPct(f.ratio_xmin_pct,digits.ratio)} • Xmax ${groupPct(f.ratio_xmax_pct,digits.ratio)}`,f.status_thickness)}${phaseMetric('CPs fora do VV',num(f.vv_failed_samples,0),pct(f.vv_failed_pct),vvFailState)}${phaseMetric('A/B < 90%',num(f.ratio_failed_samples,0),pct(f.ratio_failed_pct),ratioFailState)}</div><div class="cp-table table-wrap"><table><thead><tr><th>CP</th><th>Data</th><th>Contra-prova</th><th>Sentido</th><th>Faixa</th><th>Estaca</th><th>Posição</th><th>Esp. exec.</th><th>Esp. projeto</th><th>A/B</th><th>Rice (Gmm)</th><th>Gmb</th><th>VV</th>${isAdmin()?'<th>Ação</th>':''}</tr></thead><tbody>${sampleRows}</tbody></table></div><div class="limits-note">Referências usadas no resumo: VV estatístico entre 3,5% e 7,5%; Xmin da relação A/B ≥ 95%; CP individual A/B &lt; 90% é destacado como reprovação individual.</div></div>`
  }).join('');
  const management=isAdmin()?`<button class="ghost compact" onclick="replaceCertificate(${c.id})">↻ Substituir PDF</button><button class="danger compact" onclick="deleteCertificate(${c.id},'${esc(c.number).replace(/'/g,"\'")}')">Excluir</button>`:'';
  const managementNote=isAdmin()?`<div class="management-note"><b>Edição segura</b><span>Substituir mantém o mesmo registro e arquiva o PDF anterior. Excluir desativa o certificado. Edições manuais de resumo/CP criam backup e ficam protegidas contra sobrescrita pela sincronização.</span></div>`:'';
  const partialAlert=c.parse_status==='PARCIAL'?`<div class="callout"><b>Leitura parcial do PDF</b><span>${esc((c.parse_warnings||[]).join(' • ')||'Alguns campos não foram identificados automaticamente.')}</span></div>`:'';
  const bvAlerts=(c.business_warnings||[]).map(w=>`<div class="callout bv-alert"><b>Atenção — BV</b><span>${esc(w)}</span></div>`).join('');
  showModal(`<div class="detail-head"><div><span class="eyebrow">${esc(c.contractor)}</span><h2>${esc(c.number)}</h2><div class="subtitle">${esc(c.trace_approved||'Traço não identificado')}</div></div><div class="detail-actions">${statusBadge(c.overall_status)} ${statusBadge(c.final_phase?phaseLabel(c.final_phase):'SEM FASE')} ${statusBadge(readStatus(c.parse_status))} ${management}</div></div><div class="detail-grid"><div class="detail-field"><b>Data ext. dos CPs</b>${dateBR(c.certificate_date||c.extraction_date)}</div><div class="detail-field"><b>Data ex. serviço</b>${dateList(serviceDates)}</div><div class="detail-field"><b>Rodovia / segmento</b>${esc(c.road||'—')} • ${fmtSta(c.kmi)} a ${fmtSta(c.kmf)}</div><div class="detail-field"><b>CPs extraídos</b>${num(c.sample_count,0)}</div><div class="detail-field"><b>Linhas vinculadas por medição</b>${num(c.matched_measurements,0)}</div><div class="detail-field"><b>Extração dos CPs</b>${dateList(raw.extraction_dates)}</div><div class="detail-field"><b>Recebimento laboratório</b>${dateList(raw.receipt_dates)}</div><div class="detail-field"><b>Data dos ensaios</b>${dateList(raw.assay_dates)}</div></div>${partialAlert}${bvAlerts}${managementNote}<h3>Documentos vinculados</h3><div class="doc-list">${docs}</div><h3>Resultados por fase</h3>${phases||'<div class="empty">Nenhum corpo de prova extraído.</div>'}`)
 }catch(e){toast(e.message,true)}
}

const editNum=v=>v===null||v===undefined?'':String(v).replace('.',',');
const parseEditNum=v=>{const t=String(v??'').trim();if(!t)return null;const n=Number(t.replace(',','.'));return Number.isFinite(n)?n:null};
const parseStaEdit=v=>{const t=String(v??'').trim();if(!t)return null;const m=t.match(/(\d+)\s*\+\s*(\d+)/);if(m)return Number(m[1])*1000+Number(m[2]);const n=Number(t.replace(',','.'));return Number.isFinite(n)?Math.round(n):null};

window.editCertificatePhase=async(cid,phase)=>{
 try{
  const c=await api(`/api/certificates/${cid}`),f=(c.phases||[]).find(x=>x.phase===phase);if(!f)return toast('Fase não encontrada.',true);
  showModal(`<div class="edit-modal"><span class="eyebrow">EDIÇÃO MANUAL</span><h2>${esc(c.number)} • ${phaseLabel(phase)}</h2><div class="management-note"><b>Protegido</b><span>Ao salvar, o QualiMatch cria backup e marca o certificado como edição manual para a sincronização não sobrescrever os valores.</span></div><form id="phase-edit-form" class="edit-form-grid"><label>Status geral<select name="overall_status"><option value="APROVADO" ${f.overall_status==='APROVADO'?'selected':''}>APROVADO</option><option value="REPROVADO" ${f.overall_status==='REPROVADO'?'selected':''}>REPROVADO</option></select></label><label>Status VV<select name="status_vv"><option value="APROVADO" ${f.status_vv==='APROVADO'?'selected':''}>APROVADO</option><option value="REPROVADO" ${f.status_vv==='REPROVADO'?'selected':''}>REPROVADO</option></select></label><label>Status Espessura<select name="status_thickness"><option value="APROVADO" ${f.status_thickness==='APROVADO'?'selected':''}>APROVADO</option><option value="REPROVADO" ${f.status_thickness==='REPROVADO'?'selected':''}>REPROVADO</option></select></label><label>K<input name="k" value="${editNum(f.k)}"></label><label>VV médio (%)<input name="vv_mean_pct" value="${editNum(f.vv_mean_pct)}"></label><label>Desvio VV (%)<input name="vv_std_pct" value="${editNum(f.vv_std_pct)}"></label><label>VV Xmin (%)<input name="vv_xmin_pct" value="${editNum(f.vv_xmin_pct)}"></label><label>VV Xmax (%)<input name="vv_xmax_pct" value="${editNum(f.vv_xmax_pct)}"></label><label>A/B médio (%)<input name="ratio_mean_pct" value="${editNum(f.ratio_mean_pct)}"></label><label>Desvio A/B (%)<input name="ratio_std_pct" value="${editNum(f.ratio_std_pct)}"></label><label>A/B Xmin (%)<input name="ratio_xmin_pct" value="${editNum(f.ratio_xmin_pct)}"></label><label>A/B Xmax (%)<input name="ratio_xmax_pct" value="${editNum(f.ratio_xmax_pct)}"></label><div class="edit-actions"><button type="button" class="ghost" onclick="openCertificate(${cid})">Cancelar</button><button class="primary">Salvar edição</button></div></form></div>`);
  $('#phase-edit-form').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.currentTarget),payload={overall_status:fd.get('overall_status'),status_vv:fd.get('status_vv'),status_thickness:fd.get('status_thickness')};['k','vv_mean_pct','vv_std_pct','vv_xmin_pct','vv_xmax_pct','ratio_mean_pct','ratio_std_pct','ratio_xmin_pct','ratio_xmax_pct'].forEach(k=>payload[k]=parseEditNum(fd.get(k)));try{const d=await api(`/api/certificates/${cid}/phase/${phase}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});toast(`Resumo atualizado. Backup: ${d.backup}`);openCertificate(cid);loadCertificates();loadDash()}catch(err){toast(err.message,true)}};
 }catch(e){toast(e.message,true)}
};

window.editCertificateSample=async(cid,sid)=>{
 try{
  const c=await api(`/api/certificates/${cid}`);let sample=null;for(const f of c.phases||[]){sample=(f.samples||[]).find(x=>Number(x.id)===Number(sid));if(sample)break}if(!sample)return toast('CP não encontrado.',true);
  showModal(`<div class="edit-modal"><span class="eyebrow">EDIÇÃO DE CP</span><h2>${esc(c.number)} • CP ${esc(sample.cp_number)}</h2><form id="sample-edit-form" class="edit-form-grid"><label>Data aplicação<input type="date" name="application_date" value="${esc(sample.application_date||'')}"></label><label>Sentido<input name="direction" value="${esc(sample.direction||'')}"></label><label>Faixa<input name="lane" value="${esc(sample.lane||'')}"></label><label>Estaca<input name="station" value="${esc(fmtSta(sample.station)==='—'?'':fmtSta(sample.station))}" placeholder="405+845"></label><label>Posição<input name="position" value="${esc(sample.position||'')}"></label><label>Esp. executada (cm)<input name="thickness_exec_cm" value="${editNum(sample.thickness_exec_cm)}"></label><label>Esp. projeto (cm)<input name="thickness_project_cm" value="${editNum(sample.thickness_project_cm)}"></label><label>A/B (%)<input name="ratio_ab_pct" value="${editNum(sample.ratio_ab_pct)}"></label><label>Rice (Gmm)<input name="rice_gmm" value="${editNum(sample.rice_gmm)}"></label><label>Gmb<input name="gmb" value="${editNum(sample.gmb)}"></label><label>VV (%)<input name="voids_pct" value="${editNum(sample.voids_pct)}"></label><label class="edit-check"><input type="checkbox" name="recalculate_summary" checked> Recalcular os cartões estatísticos pelos CPs editados</label><div class="edit-actions"><button type="button" class="ghost" onclick="openCertificate(${cid})">Cancelar</button><button class="primary">Salvar CP</button></div></form></div>`);
  $('#sample-edit-form').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.currentTarget),payload={application_date:fd.get('application_date')||null,direction:String(fd.get('direction')||''),lane:String(fd.get('lane')||''),station:parseStaEdit(fd.get('station')),position:String(fd.get('position')||''),recalculate_summary:fd.get('recalculate_summary')==='on'};['thickness_exec_cm','thickness_project_cm','ratio_ab_pct','rice_gmm','gmb','voids_pct'].forEach(k=>payload[k]=parseEditNum(fd.get(k)));try{const d=await api(`/api/certificate-samples/${sid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});toast(`CP atualizado. Backup: ${d.backup}`);openCertificate(cid);loadCertificates();loadDash();loadPending()}catch(err){toast(err.message,true)}};
 }catch(e){toast(e.message,true)}
};

function showModal(html){$('#modal-content').innerHTML=html;$('#modal').classList.add('open');$('#modal').setAttribute('aria-hidden','false')}
function closeModal(){$('#modal').classList.remove('open');$('#modal').setAttribute('aria-hidden','true');$('#modal-content').innerHTML=''}
$('#modal-close').onclick=closeModal;$('#modal').onclick=e=>{if(e.target===$('#modal'))closeModal()};document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});


let notificationsLoading=false,notificationsUpdatedAt=0;
async function refreshNotifications(force=false){
 if(document.hidden||notificationsLoading||(!force&&Date.now()-notificationsUpdatedAt<60000))return;
 notificationsLoading=true;
 try{
  if(!currentUser)return;
  const d=await api('/api/notifications'),btn=$('#notification-btn'),count=$('#notification-count'),panel=$('#notification-panel');
  notificationsUpdatedAt=Date.now();
  if(count)count.textContent=String(d.count||0);if(btn)btn.classList.toggle('has-items',Number(d.count||0)>0);
  if(panel)panel.innerHTML='<button class="notification-item" onclick="openEmailNotifications()"><b>🔔 Configurar avisos</b><span>Notificações do Windows e preferências de e-mail.</span></button>'+((d.items||[]).map(x=>`<button class="notification-item ${esc(x.severity||'')}" data-page="${esc(x.page||'')}"><b>${esc(x.title)}</b><span>${esc(x.detail||'')}</span></button>`).join('')||'<div class="empty">Nenhuma notificação.</div>');
  $$('#notification-panel [data-page]').forEach(b=>b.onclick=()=>{const page=b.dataset.page;if(['admin','review','health','history','backups','tools','sync'].includes(page)&&canAccessPortal('ADMIN'))enterPortal('ADMIN',page);else if(String(page).startsWith('contractor')&&canAccessPortal('CONTRACTOR'))enterPortal('CONTRACTOR',page);else if(canAccessPortal('BV'))enterPortal('BV',page||'dashboard');$('#notification-panel').hidden=true});
 }catch{}finally{notificationsLoading=false}
}
let globalSearchTimer=null;
async function runGlobalSearch(){
 const input=$('#global-search-input'),panel=$('#global-search-results'),q=(input?.value||'').trim();if(!panel)return;
 if(q.length<2){panel.hidden=true;panel.innerHTML='';return}
 try{const list=await api('/api/search?q='+encodeURIComponent(q));panel.innerHTML=list.map(x=>`<button class="global-result" data-type="${esc(x.type)}" data-page="${esc(x.page)}" data-id="${x.entity_id}"><b>${esc(x.type)} • ${esc(x.title)}</b><span>${esc(x.subtitle||'')}</span></button>`).join('')||'<div class="empty">Nenhum resultado.</div>';panel.hidden=false;
 $$('#global-search-results .global-result').forEach(b=>b.onclick=()=>{const type=b.dataset.type,page=b.dataset.page,id=Number(b.dataset.id);panel.hidden=true;if(type==='CERTIFICADO'){enterPortal('BV','certificates');setTimeout(()=>openCertificate(id),100)}else if(type==='MEDIÇÃO'){enterPortal('BV','measurements');setTimeout(()=>openTraceability(id),100)}else if(type==='KIT'){enterPortal('CONTRACTOR','contractor-kits')}else if(type==='DOCUMENTO'){enterPortal('CONTRACTOR','contractor-certificates');setTimeout(()=>previewKitDocument(id),120)}})
 }catch(e){panel.innerHTML=`<div class="empty bad-text">${esc(e.message)}</div>`;panel.hidden=false}
}

window.openTraceability=async id=>{
 try{const d=await api(`/api/measurements/${id}/traceability`),m=d.measurement||{},kits=d.kits||[],certs=d.certificates||[];
 const flow=`<div class="trace-flow"><div class="trace-node"><span>1</span><b>Medição ${esc(m.measurement||'')}</b><small>Linha ${esc(m.line_measurement||'—')} • ${dateBR(m.date)} • ${esc(m.road||'')}</small></div><div class="trace-arrow">↓</div><div class="trace-node ${kits.length?'ok':'warn'}"><span>2</span><b>${kits.length?`${kits.length} kit(s) localizado(s)`:'Kit não localizado'}</b><small>${kits.map(k=>`#${esc(k.seq||k.id)} ${statusBadge(k.status)}`).join(' ')||'Aguardando entrega da Contratada'}</small></div><div class="trace-arrow">↓</div><div class="trace-node ${certs.length?'ok':'warn'}"><span>3</span><b>${certs.length?`${certs.length} certificado(s)`:'Certificado não localizado'}</b><small>${certs.map(c=>`<button class="cert-link" onclick="closeModal();openCertificate(${c.id})">${esc(c.number)}</button>`).join(' ')||'Aguardando certificado BV'}</small></div></div>`;
 showModal(`<span class="eyebrow">RASTREABILIDADE</span><h2>Medição → Kit → Certificado</h2>${flow}`)
 }catch(e){toast(e.message,true)}
};

async function loadCycles(){
 try{const contractor=$('#cycle-contractor')?.value||'ALL',d=await api('/api/management/measurement-cycles?contractor='+encodeURIComponent(contractor)),list=d.cycles||[],latest=list[0]||{};
 $('#cycle-kpis').innerHTML=[metric('Medição atual',esc(latest.measurement||'—'),latest.measurement_start?`${dateBR(latest.measurement_start)} a ${dateBR(latest.measurement_end)}`:''),metric('Dias de execução',num(latest.execution_days,0),'Dias distintos com medição',true),metric('Cobertura certificado',pct(latest.certificate_coverage_pct||0,1),'Dias com certificado / dias executados',true),metric('Pendências',num(Number(latest.pending_contractor||0)+Number(latest.pending_certificate||0),0),`${num(latest.pending_contractor,0)} Contratada • ${num(latest.pending_certificate,0)} Certificado`,true)].join('');
 $('#cycle-body').innerHTML=list.map(x=>`<tr><td><b>${esc(x.measurement)}</b></td><td>${dateBR(x.measurement_start)} a ${dateBR(x.measurement_end)}</td><td>${num(x.execution_days,0)}</td><td>${num(x.kit_days,0)}</td><td>${num(x.certificate_days,0)}</td><td>${pct(x.kit_coverage_pct,1)}</td><td>${pct(x.certificate_coverage_pct,1)}</td><td>${statusBadge(String(x.pending_contractor||0))}</td><td>${statusBadge(String(x.on_time||0))}</td><td>${statusBadge(String(x.pending_certificate||0))}</td><td>${x.avg_kit_lead_days==null?'—':num(x.avg_kit_lead_days,1)+' d'}</td><td>${x.avg_certificate_lead_days==null?'—':num(x.avg_certificate_lead_days,1)+' d'}</td><td><a class="tiny-btn link-btn" href="/api/reports/measurement/${encodeURIComponent(x.measurement)}?contractor=${encodeURIComponent(contractor)}">Excel</a></td></tr>`).join('')||'<tr><td colspan="13">Sem medições para este filtro.</td></tr>'
 }catch(e){toast(e.message,true)}
}

let bvKpiDetails=[];
function bvKpiBadge(type){const labels={PENDENTE_CONTRAPROVA:'PENDENTE CONTRA-PROVA',PENDENTE_EXTRACAO:'PENDENTE EXTRAÇÃO',PENDENTE_CERTIFICADO:'PENDENTE CERTIFICADO'},cls={PENDENTE_CONTRAPROVA:'bad',PENDENTE_EXTRACAO:'warn',PENDENTE_CERTIFICADO:'info'};return `<span class="status-badge ${cls[type]||'neutral'}">${esc(labels[type]||type)}</span>`}
function renderBvKpiDetails(){
 const wanted=$('#bv-kpi-type')?.value||'ALL',rows=bvKpiDetails.filter(x=>wanted==='ALL'||x.type===wanted);
 $('#bv-kpi-detail-body').innerHTML=rows.map(x=>{const detail=x.type==='PENDENTE_CERTIFICADO'?(x.sla_status||'Aguardando BV'):x.type==='PENDENTE_EXTRACAO'?'Aguardando contratada':'Aguardando contra-prova',action=x.certificate_id?`<button class="tiny-btn" onclick="openCertificate(${Number(x.certificate_id)})">Abrir certificado</button>`:x.type==='PENDENTE_CERTIFICADO'?'<button class="tiny-btn" onclick="openPage(\'pending\')">Ver pendência</button>':'—';return `<tr><td>${bvKpiBadge(x.type)}</td><td><b>${esc(x.contractor||'—')}</b></td><td>${esc(x.measurement||'—')}</td><td>${dateBR(x.date)}</td><td>${esc(x.reference||'—')}</td><td>${esc(x.road||'—')}</td><td>${esc(detail)}</td><td>${action}</td></tr>`}).join('')||'<tr><td colspan="8">Nenhuma pendência para este filtro.</td></tr>';
}
async function loadBvKpi(){
 try{
  const contractor=$('#bv-kpi-contractor')?.value||'ALL',measurement=$('#bv-kpi-measurement')?.value||'ALL',params=new URLSearchParams({contractor,measurement}),d=await api('/api/management/bv-kpi?'+params),s=d.summary||{},rows=d.measurements||[];
  const measurementSelect=$('#bv-kpi-measurement'),current=measurement;if(measurementSelect){const options=rows.map(x=>x.measurement).filter(x=>x&&x!=='—');if(current==='ALL'){measurementSelect.innerHTML='<option value="ALL">Todas as medições</option>'+options.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('')}measurementSelect.value=[...measurementSelect.options].some(x=>x.value===current)?current:'ALL'}
  const card=(label,item,hint,kind)=>`<div class="card bv-kpi-card ${kind}"><div class="label">${esc(label)}</div><div class="bv-kpi-card-main"><div class="value">${pct(item?.percent||0,1)}</div><b>${num(item?.count||0,0)}</b></div><div class="hint">${esc(hint)}</div></div>`;
  const base=Number(s.operational_total||s.obligation_total||0),baseLabel=`${num(base,0)} item(ns) previsto(s)`,hint=item=>`${num(item?.count||0,0)} / ${baseLabel}`;$('#bv-kpi-cards').innerHTML=[card('Aprovados',s.approved,hint(s.approved),'approved'),card('Reprovados',s.reproved,hint(s.reproved),'reproved'),card('Pendente contra-prova',s.counterproof_pending,hint(s.counterproof_pending),'counterproof'),card('Pendente extração',s.extraction_pending,hint(s.extraction_pending),'extraction'),card('Pendente certificado',s.certificate_pending,hint(s.certificate_pending),'certificate')].join('');
  const bars=[['Aprovados',s.approved,'approved'],['Reprovados',s.reproved,'reproved'],['Pendente contra-prova',s.counterproof_pending,'counterproof'],['Pendente extração',s.extraction_pending,'extraction'],['Pendente certificado',s.certificate_pending,'certificate']];
  $('#bv-kpi-bars').innerHTML=bars.map(([label,item,kind])=>`<div class="bv-kpi-bar-row"><div><span>${esc(label)}</span><b>${pct(item?.percent||0,1)} <small>(${num(item?.count||0,0)})</small></b></div><div class="bv-kpi-bar-track"><i class="${kind}" style="width:${Math.max(0,Math.min(100,Number(item?.percent||0)))}%"></i></div></div>`).join('');
  $('#bv-kpi-measurement-body').innerHTML=rows.map(x=>`<tr><td><b>${esc(x.measurement)}</b></td><td>${num(x.certificates,0)}</td><td><span class="kpi-number approved">${num(x.approved,0)}</span></td><td><span class="kpi-number reproved">${num(x.reproved,0)}</span></td><td>${num(x.counterproof_pending,0)}</td><td>${num(x.extraction_pending,0)}</td><td>${num(x.certificate_pending,0)}</td></tr>`).join('')||'<tr><td colspan="7">Sem dados para este filtro.</td></tr>';
  bvKpiDetails=d.details||[];renderBvKpiDetails();
 }catch(e){toast(e.message,true)}
}

let bvGeneralReport=null;
function findBvReportItem(measurement,contractor=''){const sections=bvGeneralReport?.contractor_sections||[];if(contractor&&sections.length){const section=sections.find(x=>x.contractor===contractor);return (section?.measurements||[]).find(x=>x.measurement===measurement)}return (bvGeneralReport?.measurements||[]).find(x=>x.measurement===measurement)}
window.openBvReportFiles=(measurement,category,contractor='')=>{
 const item=findBvReportItem(measurement,contractor),files=item?.files?.[category]||[];
 const list=files.map(x=>`<div class="source-card"><div><b>${esc(x.file_name)}</b><div class="meta">${esc(x.contractor)} • ${esc(x.relative_path||'')}</div></div><div><a class="tiny-btn link-btn" target="_blank" href="/api/bv-documents/${x.id}/file">Abrir</a></div></div>`).join('')||'<div class="empty">Nenhum arquivo nesta categoria.</div>';
 showModal(`<span class="eyebrow">${esc(measurement)} / ${esc(category)}</span><h2>Certificados recebidos</h2>${list}<div class="edit-actions"><button class="ghost" onclick="closeModal()">Fechar</button></div>`)
};
window.editBvReportCounts=(measurement,contractor='')=>{
 const item=findBvReportItem(measurement,contractor);if(!item)return;
 const cats=['VV/ESP','CA','LIGANTE','DUI','AGREGADOS','OUTROS'];
 const fields=cats.map((c,i)=>`<label><span>${esc(c)}</span><input type="number" min="0" id="bv-override-${i}" value="${Number(item.counts?.[c]||0)}"></label>`).join('');
 showModal(`<span class="eyebrow">AJUSTE MANUAL • ${esc(contractor||$('#bv-report-contractor')?.value||'ALL')} • ${esc(measurement)}</span><h2>Editar quantidades entregues</h2><div class="certificate-filter-grid">${fields}<label class="filter-wide"><span>Justificativa</span><input id="bv-override-reason" value="${esc(item.override_reason||'')}" placeholder="Motivo do ajuste"></label></div><div class="edit-actions"><button class="ghost" onclick="closeModal()">Cancelar</button><button class="primary" onclick='saveBvReportCounts(${JSON.stringify(measurement)},${JSON.stringify(contractor)})'>Salvar</button></div>`)
};
window.saveBvReportCounts=async(measurement,contractor='')=>{
 const cats=['VV/ESP','CA','LIGANTE','DUI','AGREGADOS','OUTROS'],counts={};cats.forEach((c,i)=>counts[c]=Math.max(0,Number($(`#bv-override-${i}`)?.value||0)));
 try{await api('/api/bv-general-report/override',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({contractor:contractor||$('#bv-report-contractor')?.value||'ALL',measurement,counts,reason:$('#bv-override-reason')?.value||''})});closeModal();toast('Quantidades atualizadas.');await loadBvGeneralReport()}catch(e){toast(e.message,true)}
};
async function loadBvGeneralReport(){
 try{const contractor=$('#bv-report-contractor')?.value||'ALL',d=await api('/api/bv-general-report?contractor='+encodeURIComponent(contractor));bvGeneralReport=d;
 const t=d.totals||{},cats=d.categories||['VV/ESP','CA','LIGANTE','DUI','AGREGADOS','OUTROS'],meas=d.measurements||[],sections=d.contractor_sections||[],displayMeas=sections.length?sections.flatMap(section=>(section.measurements||[]).map(x=>({...x,contractor:section.contractor}))):meas;
 const covered=displayMeas.filter(x=>Number(x.total||0)>0).length,empty=displayMeas.filter(x=>!Number(x.total||0)).length;
 const topCat=cats.reduce((best,c)=>Number(t[c]||0)>Number(t[best]||0)?c:best,cats[0]||'');
 $('#bv-report-kpis').innerHTML=[
  metric('Total de certificados',num(d.total,0),'Todos os envios BV (apenas PDF)'),
  metric('Medições com envio',num(covered,0)+' / '+num(displayMeas.length,0),empty?`${empty} medição(ões) ainda sem nenhum certificado`:'Todas as medições têm ao menos 1 certificado'),
  metric('Tipo mais recebido',esc(topCat||'—'),topCat?`${num(t[topCat]||0,0)} certificado(s)`:'Sem dados'),
  metric('VV / Espessura',num(t['VV/ESP']||0,0),'Meta: 100% das aplicações')
 ].join('');
 $('#bv-report-chart').innerHTML=renderBvCategoryStack(meas,cats,BV_REPORT_COLORS);
 $('#bv-report-donut').innerHTML=renderStatusPie(cats.map(c=>({status:c,count:Number(t[c]||0)})));
 const cell=(x,c)=>{const n=Number(x.counts?.[c]||0),expected=Number(x.expected?.[c]||0),label=c==='OUTROS'?String(n):`${n}/${expected}`,state=expected&&n>=expected?'ok':expected?'warn':'info';return `<button class="tiny-btn status-badge ${state}" title="${esc(c)}: ${esc(label)}" onclick='openBvReportFiles(${JSON.stringify(x.measurement)},${JSON.stringify(c)},${JSON.stringify(x.contractor||'')})'>${esc(label)}</button>`};
 let lastContractor='';$('#bv-report-body').innerHTML=displayMeas.map(x=>{const group=x.contractor&&x.contractor!==lastContractor?`<tr class="bv-report-company-row"><td colspan="8">${esc(x.contractor)}</td></tr>`:'';if(x.contractor)lastContractor=x.contractor;return group+`<tr class="${Number(x.total||0)?'':'bv-report-row-empty'}"><td><b>${esc(x.measurement)}</b><small class="meta">${num(x.execution_days,0)} dia(s) executado(s)</small>${canEdit()?`<button class="tiny-btn" onclick='editBvReportCounts(${JSON.stringify(x.measurement)},${JSON.stringify(x.contractor||'')})'>Editar quantidades</button>`:''}${x.manual_override?'<small class="meta">• ajuste manual</small>':''}</td>${cats.map(c=>`<td>${cell(x,c)}</td>`).join('')}<td><b>${num(x.total,0)}</b></td></tr>`}).join('')||'<tr><td colspan="8">Nenhum arquivo BV sincronizado.</td></tr>'
 }catch(e){toast(e.message,true)}
}
function downloadBvMissingReport(){const contractor=$('#bv-report-contractor')?.value||'ALL';window.open('/api/bv-general-report/missing.pdf?contractor='+encodeURIComponent(contractor),'_blank')}

function reviewAction(x){if(x.entity_type==='certificate')return `<button class="tiny-btn" onclick="enterPortal('BV','certificates');setTimeout(()=>openCertificate(${Number(x.entity_id)}),100)">Abrir</button>`;if(x.entity_type==='kit')return `<button class="tiny-btn" onclick="enterPortal('CONTRACTOR','contractor-kits')">Ver kits</button>`;if(x.page==='pending')return `<button class="tiny-btn" onclick="enterPortal('BV','pending')">Pendências</button>`;return '—'}
let reviewItems=[],reviewFiltersRestored=false,reviewPage=1,reviewTotal=0,reviewPageSize=25;
function restoreReviewFilters(){if(reviewFiltersRestored)return;reviewFiltersRestored=true;try{const saved=JSON.parse(localStorage.getItem('qualimatch_review_filters')||'{}');for(const [id,key] of [['review-contractor','contractor'],['review-severity','severity'],['review-type','item_type'],['review-search','search']]){const el=$('#'+id),value=saved[key];if(!el||value==null)continue;if(id==='review-type'&&value!=='ALL'&&![...el.options].some(x=>x.value===value))el.add(new Option(String(value).replaceAll('_',' '),value));el.value=value}}catch(e){}}
function saveReviewFilters(){try{localStorage.setItem('qualimatch_review_filters',JSON.stringify({contractor:$('#review-contractor')?.value||'ALL',severity:$('#review-severity')?.value||'ALL',item_type:$('#review-type')?.value||'ALL',search:$('#review-search')?.value||''}))}catch(e){}}
async function loadReview(page=1){
 restoreReviewFilters();
 try{const params=new URLSearchParams({contractor:$('#review-contractor')?.value||'ALL',severity:$('#review-severity')?.value||'ALL',item_type:$('#review-type')?.value||'ALL',search:$('#review-search')?.value||'',page:String(page),page_size:String(reviewPageSize)}),d=await api('/api/management/review?'+params),sev=d.severity||{};saveReviewFilters();reviewItems=d.items||[];reviewPage=d.page||page;reviewTotal=Number(d.total||0);
 const typeSelect=$('#review-type'),currentType=typeSelect?.value||'ALL',types=d.available_types||[];if(typeSelect){typeSelect.innerHTML='<option value="ALL">Todos os tipos</option>'+types.map(x=>`<option value="${esc(x)}">${esc(x.replaceAll('_',' '))}</option>`).join('');typeSelect.value=types.includes(currentType)?currentType:'ALL'}
 $('#review-kpis').innerHTML=[metric('Total',num(d.total,0),'Itens que merecem ação'),metric('Críticos',num(sev.danger||0,0),'Pendências vencidas / bloqueios',true),metric('Avisos',num(sev.warning||0,0),'Leitura parcial, kit incompleto ou data',true),metric('Informativos',num(sev.info||0,0),'Itens ainda dentro do prazo',true)].join('');
 $('#review-body').innerHTML=reviewItems.map(x=>`<tr><td>${statusBadge(x.severity==='danger'?'CRÍTICO':x.severity==='warning'?'ATENÇÃO':'INFO')}</td><td>${esc(x.type)}</td><td>${esc(x.contractor||'—')}</td><td><b>${esc(x.title)}</b></td><td>${esc(x.detail||'')}</td><td>${reviewAction(x)}</td></tr>`).join('')||'<tr><td colspan="6">Nenhuma inconsistência encontrada para estes filtros.</td></tr>'
 renderPagination('#review-pagination',reviewTotal,reviewPage,reviewPageSize,p=>loadReview(p),size=>{reviewPageSize=size;loadReview(1)});
 }catch(e){toast(e.message,true)}
}
function exportReviewCsv(){if(!reviewItems.length)return toast('Nenhum item para exportar.',true);const quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"',headers=['Prioridade','Tipo','Contratada','Item','Detalhe','Entidade','ID'],data=reviewItems.map(x=>[x.severity,x.type,x.contractor,x.title,x.detail,x.entity_type,x.entity_id]),csv='\ufeff'+[headers,...data].map(row=>row.map(quote).join(';')).join('\r\n'),blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='qualimatch_conciliacao.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),500)}

function renderRuntimeState(op={},counts={},maintenance={}){
 const active=!!op.active,paused=!!op.paused,pct=Number(op.progress_pct||0),badge=$('#runtime-badge');
 if(badge){badge.textContent=active?'EM ANDAMENTO':paused?'AUTOMAÇÕES PAUSADAS':op.last_status||'PRONTO';badge.className='badge '+(active?'warn':paused?'warn':op.last_status==='ERRO'?'bad':'ok')}
 if($('#runtime-label'))$('#runtime-label').textContent=active?(op.label||'Operação em andamento'):'Nenhuma operação pesada em andamento';
 if($('#runtime-current'))$('#runtime-current').textContent=active?(op.current||'Processando...'):(paused?'Importações automáticas estão pausadas.':'As rotinas automáticas usam somente arquivos alterados.');
 if($('#runtime-progress'))$('#runtime-progress').style.width=(active?Math.max(3,pct):0)+'%';
 if($('#runtime-pause'))$('#runtime-pause').textContent=paused?'Retomar automações':'Pausar automações';
 if($('#runtime-cancel'))$('#runtime-cancel').disabled=!active;
 const uptime=Math.floor(Number(op.uptime_seconds||0)/60),logs=Number(counts.sync_logs||0),daily=maintenance.last_daily_backup||'ainda não executado';
 if($('#runtime-details'))$('#runtime-details').textContent=`Servidor ativo há ${uptime} min • ${logs.toLocaleString('pt-BR')} registros recentes • backup diário: ${daily}`;
 // Espelha o mesmo status na tela de Sincronização, para ver o progresso sem precisar trocar de aba.
 const syncBadge=$('#sync-runtime-badge');
 if(syncBadge){syncBadge.textContent=active?'EM ANDAMENTO':paused?'AUTOMAÇÕES PAUSADAS':op.last_status||'PRONTO';syncBadge.className='badge '+(active?'warn':paused?'warn':op.last_status==='ERRO'?'bad':'ok')}
 if($('#sync-runtime-label'))$('#sync-runtime-label').textContent=active?(op.label||'Operação em andamento'):'Nenhuma operação pesada em andamento';
 if($('#sync-runtime-current'))$('#sync-runtime-current').textContent=active?(op.current||'Processando...'):(paused?'Importações automáticas estão pausadas.':'Assim que uma sincronização iniciar, o progresso aparece aqui.');
 if($('#sync-runtime-progress'))$('#sync-runtime-progress').style.width=(active?Math.max(3,pct):0)+'%';
 if($('#sync-runtime-details')){
  let detail='';
  if(active){
   const startedMs=op.started_at?Date.parse(op.started_at):NaN,mins=isNaN(startedMs)?0:Math.max(0,Math.floor((Date.now()-startedMs)/60000));
   const countTxt=Number(op.total||0)?` • ${num(op.processed,0)} de ${num(op.total,0)}`:'';
   detail=`Em andamento há ${mins} min${countTxt}`;
  }else if(op.last_message&&op.finished_at){
   detail=op.last_message;
  }
  $('#sync-runtime-details').textContent=detail;
 }
 // Indicador global no topo da barra lateral (visível em qualquer página).
 const gIndicator=$('#global-sync-indicator');
 if(gIndicator){
  gIndicator.hidden=!active;
  if(active){
   if($('#global-sync-text'))$('#global-sync-text').textContent=op.current||op.label||'Sincronizando...';
   if($('#global-sync-bar'))$('#global-sync-bar').style.width=Math.max(3,pct)+'%';
  }
 }
}
async function loadRuntimeState(){try{const op=await api('/api/admin/runtime'),cached=window._qualimatchHealth||{};renderRuntimeState(op,cached.counts||{},cached.maintenance||{})}catch(e){}}
async function loadHealth(){
 try{const d=await api('/api/admin/health'),C=d.counts||{},last=d.last_backup,R=d.runtime||{},disk=d.disk||{},issues=d.warnings||[];
 window._qualimatchHealth={counts:C,maintenance:d.maintenance||{}};
 const sourceIssues=Number(d.failed_sources||0)+Number(d.stale_sources||0);
 $('#health-kpis').innerHTML=[metric('Banco',statusBadge('OK'),esc(d.database||''),true),metric('Versão',esc(R.version||'—'),`Python ${esc(R.python||'—')}`),metric('Espaço livre',disk.free_gb==null?'—':num(disk.free_gb,1)+' GB',disk.used_pct==null?'Disco de dados':num(disk.used_pct,1)+'% utilizado'),metric('Fontes',statusBadge(sourceIssues?'ATENÇÃO':'OK'),sourceIssues?`${sourceIssues} exigem atenção`:'Todas normais',true),metric('Certificados',num(C.certificates,0),'Ativos'),metric('Kits',num(C.kits,0),'Ativos'),metric('Usuários',num(C.users,0),'Aprovados'),metric('Último backup',last?esc(last.modified):'—',last?esc(last.name):'Nenhum backup')].join('');
 const alertBox=$('#health-alerts');alertBox.className='health-alerts '+(issues.length?'has-warning':'is-ok');alertBox.innerHTML=issues.length?`<b>⚠ ${issues.length} ponto(s) de atenção</b><ul>${issues.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'<b>✓ Nenhum alerta operacional detectado.</b>';
 renderRuntimeState(d.operation||{},C,d.maintenance||{});
 $('#health-body').innerHTML=(d.sources||[]).map(x=>`<tr><td>${esc(x.contractor)}</td><td>${esc(kindNames[x.kind]||x.kind)}</td><td>${statusBadge(x.health||x.last_status)}</td><td>${esc(x.last_sync||'—')}${x.age_minutes==null?'':`<small class="table-sub">há ${num(x.age_minutes,0)} min</small>`}</td><td class="kit-project">${esc(x.path||'—')}</td><td>${esc(x.last_error||'')}</td></tr>`).join('')||'<tr><td colspan="6">Nenhuma fonte configurada.</td></tr>'
 }catch(e){toast(e.message,true)}
}

async function toggleRuntimePause(){try{const current=await api('/api/admin/runtime'),op=await api('/api/admin/runtime/pause',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({paused:!current.paused})});renderRuntimeState(op);toast(op.paused?'Automações pausadas.':'Automações retomadas.')}catch(e){toast(e.message,true)}}
async function cancelRuntime(){if(!confirm('Cancelar a operação após o arquivo atual?'))return;try{await api('/api/admin/runtime/cancel',{method:'POST'});toast('Cancelamento solicitado.');loadRuntimeState()}catch(e){toast(e.message,true)}}
async function archiveRuntimeLogs(){try{const d=await api('/api/admin/logs/archive',{method:'POST'});toast(d.archived?`${d.archived.toLocaleString('pt-BR')} registros antigos foram compactados.`:'O histórico já está compacto.');loadHealth()}catch(e){toast(e.message,true)}}
async function shutdownQualimatch(){const confirmation=prompt('Para encerrar o QualiMatch com segurança, digite ENCERRAR:','');if(!confirmation)return;try{const d=await api('/api/admin/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmation})});toast(d.message||'QualiMatch encerrando...')}catch(e){toast(e.message,true)}}

async function loadPending(){
 try{
  const contractor=$('#p-contractor')?.value||'ALL';
  const view=await api('/api/pending-view?contractor='+encodeURIComponent(contractor)),d=view.items||[],justified=view.justified||[];
  window._bvPendingItems=new Map(d.map(x=>[x.pending_key,x]));
  const meds=new Set(d.map(x=>x.measurement).filter(Boolean));
  $('#pending-summary').innerHTML=`<div class="summary-chip"><b>${d.length}</b> pendência(s) ativa(s) da BV</div><div class="summary-chip"><b>${justified.length}</b> justificada(s)</div><div class="summary-chip"><b>${meds.size}</b> medição(ões)</div><div class="summary-chip">Validação: <b>Entrega = Entregue</b> na d.KIT</div>`;
  $('#p-body').innerHTML=d.map(x=>`<tr><td>${esc(x.contractor)}</td><td><b>${esc(x.measurement||'—')}</b><small class="table-sub">${x.measurement_start?dateBR(x.measurement_start)+' a '+dateBR(x.measurement_end):''}</small></td><td>${dateBR(x.date)}</td><td>${esc(x.road||'—')}</td><td>${num(x.lines,0)}</td><td>${statusBadge('ENTREGUE')}</td><td>${statusBadge(x.status)}</td><td>${canEdit()?`<button class="tiny-btn" onclick="justifyBvPending('${encodeURIComponent(x.pending_key)}')">Justificar</button>`:'—'}</td></tr>`).join('')||'<tr><td colspan="8">Nenhum dia sob responsabilidade da BV.</td></tr>';
  $('#p-justified-body').innerHTML=justified.map(x=>`<tr><td>${esc(x.contractor)}</td><td><b>${esc(x.measurement||'—')}</b></td><td>${dateBR(x.date)}</td><td>${esc(x.road||'—')}</td><td>${esc(x.justification)}</td><td>${esc(x.justified_at||'—')}</td><td>${canEdit()?`<button class="tiny-btn" onclick="restoreBvPending('${encodeURIComponent(x.pending_key)}')">Reabrir</button>`:'—'}</td></tr>`).join('')||'<tr><td colspan="7">Nenhuma pendência BV justificada.</td></tr>';
 }catch(e){toast(e.message,true)}
}
window.justifyBvPending=async encoded=>{const key=decodeURIComponent(encoded),item=window._bvPendingItems?.get(key);if(!item)return;const reason=prompt('Informe por que esta pendência não pode mais ser tratada:','');if(!reason)return;try{await api('/api/pending/justify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pending_key:key,contractor:item.contractor,reason,item})});toast('Pendência BV justificada e separada.');loadPending()}catch(e){toast(e.message,true)}};
window.restoreBvPending=async encoded=>{if(!confirm('Reabrir esta pendência BV?'))return;try{await api('/api/pending/justify/'+encoded,{method:'DELETE'});toast('Pendência BV reaberta.');loadPending()}catch(e){toast(e.message,true)}};
let currentChanges=[],historyLogPage=1,historyChangePage=1,historyPageSize=25;
async function loadHistory(logPage=1,changePage=1){try{const date=$('#history-date')?.value||'',base={page_size:String(historyPageSize)},logsQ=new URLSearchParams({...base,page:String(logPage)}),changesQ=new URLSearchParams({...base,page:String(changePage)});if(date){logsQ.set('date',date);changesQ.set('date',date)}const [d,changes]=await Promise.all([api('/api/logs?'+logsQ),api('/api/admin/changes?'+changesQ)]);historyLogPage=d.page||logPage;historyChangePage=changes.page||changePage;currentChanges=changes.items||[];$('#h-body').innerHTML=(d.items||[]).map(x=>`<tr><td>${esc(x.created_at)}</td><td>${x.contractor||'—'}</td><td>${esc(kindNames[x.kind]||x.kind)}</td><td>${statusBadge(x.status)}</td><td>${x.records}</td><td>${esc(x.message)}</td></tr>`).join('')||'<tr><td colspan="6">Sem sincronizações.</td></tr>';$('#change-body').innerHTML=currentChanges.map(x=>`<tr><td>${esc(x.created_at)}</td><td>${esc(x.user_name||'Sistema')}</td><td>${esc(x.action)}</td><td>${esc(x.entity_type)} #${esc(x.entity_id)}</td><td>${x.undone_at?statusBadge('DESFEITO'):statusBadge('ATIVO')}</td><td><div class="row-actions"><button class="tiny-btn" onclick="viewChange(${x.id})">Antes × Depois</button>${x.undone_at?'':`<button class="tiny-btn danger" onclick="undoChange(${x.id})">Desfazer</button>`}</div></td></tr>`).join('')||'<tr><td colspan="6">Nenhuma alteração reversível registrada.</td></tr>';renderPagination('#history-log-pagination',Number(d.total||0),historyLogPage,historyPageSize,p=>loadHistory(p,historyChangePage),size=>{historyPageSize=size;loadHistory(1,1)});renderPagination('#history-change-pagination',Number(changes.total||0),historyChangePage,historyPageSize,p=>loadHistory(historyLogPage,p),size=>{historyPageSize=size;loadHistory(1,1)})}catch(e){toast(e.message,true)}}
function prettySnapshot(raw){try{const obj=typeof raw==='string'?JSON.parse(raw||'{}'):(raw||{});return esc(JSON.stringify(obj,null,2))}catch(e){return esc(String(raw||'{}'))}}
window.viewChange=id=>{const x=currentChanges.find(c=>Number(c.id)===Number(id));if(!x)return;showModal(`<span class="eyebrow">HISTÓRICO DE ALTERAÇÃO</span><h2>${esc(x.action)} • ${esc(x.entity_type)} #${esc(x.entity_id)}</h2><p class="muted">${esc(x.created_at)} • ${esc(x.user_name||'Sistema')}</p><div class="change-compare"><div><h3>Antes</h3><pre>${prettySnapshot(x.before_json)}</pre></div><div><h3>Depois</h3><pre>${prettySnapshot(x.after_json)}</pre></div></div><div class="edit-actions"><button class="ghost" onclick="closeModal()">Fechar</button></div>`)};
window.undoChange=async id=>{if(!confirm('Desfazer esta alteração e restaurar o estado anterior do registro?'))return;try{await api(`/api/admin/changes/${id}/undo`,{method:'POST'});toast('Alteração desfeita.');loadHistory();refreshNotifications()}catch(e){toast(e.message,true)}};

let toolPdfPreview=null;
let toolPdfOverrides={};
function loadTools(){
 if(!toolPdfPreview){
  $('#tool-pdf-message').innerHTML='<span class="muted">A análise usa a base de Medições já sincronizada. Você pode gerar uma cópia ou, após revisar os vínculos, atualizar a BD_QUALI principal com backup automático.</span>';
 }
}
function renderSourceInspection(d){
 const s=d.summary||{},issues=d.issues||[];
 $('#tool-source-kpis').innerHTML=[
  metric('Abas',num(s.sheets,0),`${num(s.visible_sheets,0)} visível(is)`),
  metric('Linhas mapeadas',num(s.rows,0),'Soma das dimensões das abas'),
  metric('Maior largura',num(s.max_columns,0),'Colunas na aba mais larga'),
  metric('Pontos de atenção',num(s.issues,0),issues.length?'Revisar antes de sincronizar':'Estrutura sem alertas',true)
 ].join('');
 $('#tool-source-message').innerHTML=`<b>${esc(d.file_name||'Planilha')}</b> • ${num(Number(d.size_bytes||0)/1024/1024,2)} MB • ${issues.length?`<span class="warn-text">${issues.length} ponto(s) de atenção.</span>`:'<span class="ok-text">Estrutura pronta para conferência.</span>'}`;
 $('#tool-source-sheets').innerHTML=(d.sheets||[]).map(sheet=>{
  const headers=sheet.headers||[],shown=headers.slice(0,30),sample=sheet.sample||[],sheetIssues=sheet.issues||[],duplicates=sheet.duplicate_headers||[];
  const table=shown.length?`<div class="table-wrap source-sample"><table><thead><tr>${shown.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${sample.map(row=>`<tr>${shown.map((_,i)=>`<td>${esc(row[i]??'—')}</td>`).join('')}</tr>`).join('')||`<tr><td colspan="${shown.length}" class="empty">Sem linhas de amostra.</td></tr>`}</tbody></table></div>`:'<div class="empty">Cabeçalho não identificado.</div>';
  return `<details class="source-sheet-card" open><summary><span><b>${esc(sheet.name)}</b><small>${sheet.state==='visible'?'Visível':'Oculta'} • ${num(sheet.rows,0)} linhas • ${num(sheet.columns,0)} colunas</small></span>${statusBadge(sheetIssues.length?'ATENÇÃO':'OK')}</summary><div class="source-sheet-meta"><span>Cabeçalho provável: <b>linha ${num(sheet.header_row,0)}</b></span><span>Fórmulas encontradas na amostra: <b>${num(sheet.formula_count_sampled,0)}</b></span>${headers.length>shown.length?`<span>Prévia limitada às primeiras ${shown.length} de ${headers.length} colunas.</span>`:''}</div>${duplicates.length?`<div class="source-issues"><b>Colunas duplicadas:</b> ${duplicates.map(group=>group.map(esc).join(' / ')).join(' • ')}</div>`:''}${sheetIssues.length?`<div class="source-issues">${sheetIssues.map(x=>`<div>⚠ ${esc(x)}</div>`).join('')}</div>`:''}${table}</details>`;
 }).join('');
}
async function inspectSourceWorkbook(){
 const input=$('#tool-source-file'),file=input?.files?.[0];
 if(!file)return toast('Selecione uma planilha .xlsx ou .xlsm.',true);
 const fd=new FormData();fd.append('file',file);
 const btn=$('#tool-source-inspect'),old=btn.textContent;btn.disabled=true;btn.textContent='Inspecionando...';
 $('#tool-source-message').innerHTML='<b>Lendo abas e estrutura da planilha...</b>';
 try{const d=await api('/api/admin/tools/source-inspector',{method:'POST',body:fd});renderSourceInspection(d);toast('Inspeção concluída. Nenhum dado foi alterado.')}catch(e){$('#tool-source-message').innerHTML=`<span class="bad-text">${esc(e.message)}</span>`;toast(e.message,true)}finally{btn.disabled=false;btn.textContent=old}
}
function toolMatchBadge(status,reason=''){
 const s=String(status||'').toUpperCase();
 const cls=s==='VINCULADO'?'ok':s==='REVISAR'?'warn':'bad';
 const label=s==='SEM_MEDICAO'?'SEM MEDIÇÃO':s||'—';
 return `<span class="status-badge ${cls}" title="${esc(reason)}">${esc(label)}</span>`;
}
function toolReviewCell(x){
 const badge=toolMatchBadge(x.match_status,x.match_reason);
 const candidates=x.measurement_candidates||[];
 if(String(x.match_status||'').toUpperCase()==='VINCULADO'||!candidates.length)return badge;
 const opts=candidates.map(c=>`<option value="${Number(c.id)}">${esc(c.line_measurement||'Linha ?')} • ${esc(c.road||'')} ${fmtSta(c.kmi)}–${fmtSta(c.kmf)} • ${esc(c.direction||'')} ${esc(c.lane||'')} • score ${num(c.score,1)}</option>`).join('');
 return `<div class="tool-review-control">${badge}<select data-tool-review-key="${esc(x.line_key)}"><option value="">Selecionar medição...</option>${opts}</select><button class="ghost compact" data-tool-review-apply="${esc(x.line_key)}">Usar</button></div>`;
}

/* v3.9.1 — formata os campos de quality_fields na prévia do PDF -> BD_QUALI.
   É só apresentação: não influencia em nada o que de fato é gravado no Excel (isso continua
   inteiramente a cargo de qualimatch/quality_excel_writer.py, que não foi alterado). */
function toolFieldValue(k,v){
 if(v===null||v===undefined||v==='')return '<span class="muted">—</span>';
 if(/%/.test(k))return fixedNum(Number(v)*100,1)+'%';
 if(/^STATUS/i.test(k))return `<span class="${String(v).toUpperCase().includes('REPROV')?'bad-text':'ok-text'}">${esc(String(v))}</span>`;
 if(typeof v==='number'&&Number.isInteger(v))return num(v,0);
 if(typeof v==='number')return num(v,3);
 return esc(String(v));
}
function renderToolPdfPreview(d){
 toolPdfPreview=d;
 const S=d.summary||{};
 $('#tool-pdf-kpis').innerHTML=[
  metric('PDFs lidos',num(S.pdfs,0),'Certificados processados'),
  metric('Linhas esperadas',num(S.expected_rows,0),'1 CP de rotina = 1 linha'),
  metric('Vinculadas',num(S.linked,0),'Medição localizada automaticamente',true),
  metric('Revisar / sem medição',num(Number(S.review||0)+Number(S.missing||0),0),`${num(S.review,0)} revisar • ${num(S.missing,0)} sem medição`,true)
 ].join('');
 const errs=d.errors||[];
 const ready=Number(S.excel_ready_certificates||0),blocked=Number(S.excel_blocked_certificates||0);
 $('#tool-pdf-message').innerHTML=`<b>Prévia concluída.</b> ${num(S.expected_rows,0)} linhas projetadas. <span class="ok-text">${ready} certificado(s) pronto(s) para Excel.</span>${blocked?` <span class="warn-text">${blocked} bloqueado(s) para revisão.</span>`:''} ${errs.length?`<span class="bad-text">${errs.length} PDF(s) com erro.</span>`:'O original não será alterado.'}`;
 $('#tool-pdf-certificates').innerHTML=(d.certificates||[]).map(c=>{
  const diff=Number(c.existing_quality_rows||0)-Number(c.expected_quality_rows||0),plan=c.excel_write||{};
  const existing=c.existing_quality_rows?`<span class="tool-existing ${diff===0?'ok-text':'warn-text'}">BD atual: ${num(c.existing_quality_rows,0)} linhas</span>`:'<span class="tool-existing">Ainda não localizado na BD_QUALI</span>';
  const placement=plan.placement?`<small class="tool-placement">${esc(plan.placement)}</small>`:'';
  const write=plan.ready?`<span class="tool-write-ready">${plan.mode==='ATUALIZAR_EXISTENTE'?'✓ Atualizar linhas existentes':'＋ Adicionar novas linhas'} • ${esc(plan.final_status||'')}</span>${placement}`:`<span class="tool-write-blocked">⚠ Não gravar: ${esc(plan.reason||'revisão necessária')}</span>`;
  const warnings=(c.warnings||[]).map(w=>`<div>⚠ ${esc(w)}</div>`).join('');
  const qf=c.quality_fields||{},qfKeys=Object.keys(qf);
  const fieldsPreview=qfKeys.length?`<details class="tool-fields-preview"><summary>Ver ${qfKeys.length} valor(es) que serão gravados na BD_QUALI</summary><div class="detail-grid tool-fields-grid">${qfKeys.map(k=>`<div class="detail-field"><b>${esc(k)}</b>${toolFieldValue(k,qf[k])}</div>`).join('')}</div></details>`:'';
  return `<div class="tool-cert-summary"><div><b>${esc(c.certificate)}</b><span>${esc(c.contractor)} • ${esc(c.road||'Rodovia não lida')} • ${num(c.expected_quality_rows,0)} linhas esperadas${c.counterproof_samples?` • ${num(c.counterproof_samples,0)} CPs de contra-prova vinculáveis`:''}</span></div>${existing}<div class="tool-write-state">${write}</div>${warnings?`<div class="tool-cert-warnings">${warnings}</div>`:''}${fieldsPreview}</div>`;
 }).join('')+(errs.length?`<div class="tool-cert-summary tool-error-summary"><b>Arquivos não processados</b>${errs.map(e=>`<div>${esc(e.file_name)} — ${esc(e.error)}</div>`).join('')}</div>`:'');
 $('#tool-pdf-body').innerHTML=(d.lines||[]).map(x=>{const m=x.measurement||{};return `<tr class="${x.match_status==='VINCULADO'?'tool-linked':x.match_status==='REVISAR'?'tool-review':'tool-missing'}"><td><b>${esc(x.certificate)}</b><span class="sub">${esc(x.contractor)}</span></td><td>${esc(x.cp_number||'—')}</td><td>${dateBR(x.application_date)}</td><td>${esc(x.road_pdf||'—')}</td><td>${esc(x.direction||'—')}</td><td>${esc(x.lane||'—')}</td><td>${fmtSta(x.station)}</td><td>${vvPct(x.voids_pct)}</td><td>${x.ratio_ab_pct==null?'—':fixedNum(x.ratio_ab_pct,1)+'%'}</td><td>${x.rice_gmm==null?'—':num(x.rice_gmm,3)}</td><td>${esc(m.ref_measurement||'—')}</td><td>${esc(m.line_measurement||'—')}</td><td>${m.kmi==null?'—':`${esc(m.road||'')} ${fmtSta(m.kmi)} a ${fmtSta(m.kmf)}`}</td><td>${toolReviewCell(x)}</td></tr>`}).join('')||'<tr><td colspan="14" class="empty">Nenhuma linha gerada.</td></tr>';
 document.querySelectorAll('[data-tool-review-apply]').forEach(btn=>btn.onclick=()=>{const key=btn.dataset.toolReviewApply,sel=document.querySelector(`select[data-tool-review-key="${CSS.escape(key)}"]`);if(!sel||!sel.value)return toast('Escolha uma medição.',true);toolPdfOverrides[key]=Number(sel.value);analyzeToolPdfs(true)});
 $('#tool-pdf-csv').disabled=!(d.lines||[]).length;
 $('#tool-pdf-excel').disabled=!Number(S.excel_ready_certificates||0);if($('#tool-pdf-write-main'))$('#tool-pdf-write-main').disabled=!Number(S.excel_ready_certificates||0);
}
async function analyzeToolPdfs(silent=false){
 const input=$('#tool-pdf-files'),files=[...(input?.files||[])];
 if(!files.length)return toast('Selecione pelo menos um PDF.',true);
 if(files.length>30)return toast('Envie no máximo 30 PDFs por análise.',true);
 const fd=new FormData();files.forEach(f=>fd.append('files',f));fd.append('overrides_json',JSON.stringify(toolPdfOverrides));
 $('#tool-pdf-analyze').disabled=true;$('#tool-pdf-message').innerHTML='<b>Analisando PDFs e cruzando com as medições...</b>';
 try{const d=await api('/api/admin/tools/pdf-quality/analyze',{method:'POST',body:fd});renderToolPdfPreview(d);if(!silent)toast('Prévia gerada. Revise os vínculos antes da geração do Excel.');else toast('Vínculo manual aplicado.')}catch(e){$('#tool-pdf-message').innerHTML=`<span class="bad-text">${esc(e.message)}</span>`;toast(e.message,true)}finally{$('#tool-pdf-analyze').disabled=false}
}
async function generateToolExcel(){
 const input=$('#tool-pdf-files'),files=[...(input?.files||[])];
 if(!toolPdfPreview||!files.length)return toast('Gere a prévia antes do Excel.',true);
 if(!Number(toolPdfPreview?.summary?.excel_ready_certificates||0))return toast('Nenhum certificado está pronto para gravação segura.',true);
 const fd=new FormData();files.forEach(f=>fd.append('files',f));fd.append('overrides_json',JSON.stringify(toolPdfOverrides));
 const btn=$('#tool-pdf-excel');btn.disabled=true;const old=btn.textContent;btn.textContent='Gerando cópia...';
 try{
  const r=await fetch('/api/admin/tools/pdf-quality/generate-excel',{method:'POST',body:fd});
  if(!r.ok){const txt=await r.text();let d;try{d=JSON.parse(txt)}catch{d={detail:txt}};throw new Error(d.detail||d.message||`HTTP ${r.status}`)}
  const blob=await r.blob(),disp=r.headers.get('Content-Disposition')||'';const m=disp.match(/filename="?([^";]+)"?/i);const name=m?m[1]:'QualiMatch_BD_QUALI.xlsx';
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
  const blocked=Number(r.headers.get('X-QualiMatch-Blocked')||0),added=Number(r.headers.get('X-QualiMatch-Appended')||0),updated=Number(r.headers.get('X-QualiMatch-Updated')||0),writtenRows=r.headers.get('X-QualiMatch-Target-Rows')||'',filtersCleared=r.headers.get('X-QualiMatch-Filters-Cleared')==='true';
  toast(`Cópia Excel gerada e validada • ${added} linha(s) adicionada(s) • ${updated} atualizada(s)${writtenRows?` • linhas ${writtenRows}`:''}${filtersCleared?' • filtro da planilha limpo na cópia':''}${blocked?` • ${blocked} bloqueado(s)`:''}.`);
 }catch(e){toast(e.message,true)}finally{btn.textContent=old;btn.disabled=!Number(toolPdfPreview?.summary?.excel_ready_certificates||0)}
}


async function writeToolMainExcel(){
 const input=$('#tool-pdf-files'),files=[...(input?.files||[])];
 if(!toolPdfPreview||!files.length)return toast('Gere e revise a prévia antes de atualizar a planilha principal.',true);
 const ready=Number(toolPdfPreview?.summary?.excel_ready_certificates||0),blocked=Number(toolPdfPreview?.summary?.excel_blocked_certificates||0);
 if(!ready)return toast('Nenhum certificado está pronto para gravação.',true);
 const msg=`ATENÇÃO: o QualiMatch vai atualizar a BD_QUALI PRINCIPAL sincronizada no SharePoint.\n\nProntos: ${ready}\nBloqueados/revisão: ${blocked}\n\nSerá criado backup automático antes da alteração. Feche a planilha no Excel antes de continuar.\n\nDeseja gravar agora?`;
 if(!confirm(msg))return;
 const fd=new FormData();files.forEach(f=>fd.append('files',f));fd.append('overrides_json',JSON.stringify(toolPdfOverrides));
 const btn=$('#tool-pdf-write-main');btn.disabled=true;const old=btn.textContent;
 /* v3.9.1 — feedback de progresso: sem isso o botão fica com o mesmo texto do início ao fim,
    e uma gravação de alguns minutos (planilha grande / OneDrive) parece travada sem diferença
    visual nenhuma entre "processando" e "morto". Não muda a chamada nem a lógica de gravação. */
 const startedAt=Date.now();
 $('#tool-pdf-message').innerHTML='<b>Atualizando a BD_QUALI principal...</b> Pode levar alguns minutos em planilhas grandes ou pastas OneDrive/SharePoint — não feche esta aba.';
 const tick=()=>{const s=Math.floor((Date.now()-startedAt)/1000);btn.textContent=`Atualizando principal... (${String(Math.floor(s/60)).padStart(1,'0')}:${String(s%60).padStart(2,'0')})`};
 tick();const timer=setInterval(tick,1000);
 try{
  const d=await api('/api/admin/tools/pdf-quality/write-main',{method:'POST',body:fd}),report=d.report||{},filesReport=report.files||[];
  const added=filesReport.reduce((a,x)=>a+Number(x.appended_rows||0),0),updated=filesReport.reduce((a,x)=>a+Number(x.updated_rows||0),0);
  const ranges=filesReport.map(x=>{const rr=x.target_rows||[];return rr.length?`${x.contractor}: ${Math.min(...rr)}–${Math.max(...rr)}`:x.contractor}).join(' • ');
  const backups=filesReport.map(x=>`${x.contractor}: ${x.backup_path||'backup criado'}`).join('\n');
  toast(`BD_QUALI principal atualizada • ${added} linha(s) adicionada(s) • ${updated} atualizada(s)${ranges?` • ${ranges}`:''}.`);
  $('#tool-pdf-message').innerHTML=`<b class="ok-text">Planilha principal atualizada e validada.</b> ${added} linha(s) adicionada(s), ${updated} atualizada(s). ${ranges?`<span>Linhas: ${esc(ranges)}.</span>`:''}<small class="tool-placement">Backup(s): ${esc(backups)}</small>`;
  await analyzeToolPdfs(true);
 }catch(e){toast(e.message,true);$('#tool-pdf-message').innerHTML=`<span class="bad-text">${esc(e.message)}</span>`}finally{clearInterval(timer);btn.textContent=old;btn.disabled=!Number(toolPdfPreview?.summary?.excel_ready_certificates||0)}
}

function downloadToolCsv(){
 const lines=toolPdfPreview?.lines||[];if(!lines.length)return;
 const headers=['Certificado','Contratada','CP','Data Aplicação','Rodovia PDF','Sentido','Faixa','Estaca','VV %','A/B %','Rice Gmm','Medição','Linha Medição','Rodovia Medição','KMI Medição','KMF Medição','Status Vínculo','Motivo'];
 const quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
 const data=lines.map(x=>{const m=x.measurement||{};return [x.certificate,x.contractor,x.cp_number,x.application_date,x.road_pdf,x.direction,x.lane,x.station,x.voids_pct,x.ratio_ab_pct,x.rice_gmm,m.ref_measurement,m.line_measurement,m.road,m.kmi,m.kmf,x.match_status,x.match_reason]});
 const csv='\ufeff'+[headers,...data].map(r=>r.map(quote).join(';')).join('\r\n');
 const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='qualimatch_previa_pdf_bdquali.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),500);
}

async function loadAdmin(){
 if(!isAdmin())return showPortalSelector();
 try{
  const [users,auditRows]=await Promise.all([api('/api/admin/users'),api('/api/admin/audit?limit=100')]);
  const counts={PENDING:0,APPROVED:0,BLOCKED:0,REJECTED:0};users.forEach(u=>counts[u.status]=(counts[u.status]||0)+1);
  $('#admin-user-kpis').innerHTML=[metric('Pendentes',num(counts.PENDING,0),'Aguardando sua decisão'),metric('Ativos',num(counts.APPROVED,0),'Usuários aprovados'),metric('Bloqueados',num(counts.BLOCKED,0),'Sem acesso ao sistema'),metric('Recusados',num(counts.REJECTED,0),'Solicitações não aprovadas')].join('');
  $('#admin-users-body').innerHTML=users.map(u=>{
    const self=currentUser&&Number(u.id)===Number(currentUser.id),admin=String(u.role||'').toUpperCase()==='ADMIN',level=admin?'ADMIN':String(u.permission_level||'VIEWER').toUpperCase();
    let actions='';if(!self){if(u.status==='PENDING')actions=`<button class="primary compact" onclick="adminUserAction(${u.id},'APPROVE')">Aprovar</button><button class="danger compact" onclick="adminUserAction(${u.id},'REJECT')">Recusar</button>`;else if(u.status==='APPROVED')actions=`<button class="danger compact" onclick="adminUserAction(${u.id},'BLOCK')">Bloquear</button>`;else actions=`<button class="primary compact" onclick="adminUserAction(${u.id},'REACTIVATE')">Reativar</button>`}else actions='<span class="admin-self">Sua conta</span>';
    const access=`<div class="access-editor" data-access-user="${u.id}"><label class="access-chip"><input type="checkbox" data-access="bv" ${admin||Number(u.access_bv)?'checked':''} ${admin?'disabled':''}><span>BV</span></label><label class="access-chip contractor-scope"><input type="checkbox" data-access="arena" ${admin||Number(u.access_arena)?'checked':''} ${admin?'disabled':''}><span>Contratada • Arena</span></label><label class="access-chip contractor-scope"><input type="checkbox" data-access="pavidez" ${admin||Number(u.access_pavidez)?'checked':''} ${admin?'disabled':''}><span>Contratada • Pavidez</span></label><label class="access-chip quality-access"><input type="checkbox" data-access="quality_general" ${admin||Number(u.access_quality_general)?'checked':''} ${admin?'disabled':''}><span>Traços</span></label><label class="access-chip quality-access"><input type="checkbox" data-access="quality_nc" ${admin||Number(u.access_quality_nc)?'checked':''} ${admin?'disabled':''}><span>Não conformidades</span></label><label class="access-chip admin-access"><input type="checkbox" data-access="admin" ${admin?'checked':''} ${self?'disabled':''}><span>Administração</span></label><button class="ghost compact access-save" onclick="saveUserPermissions(${u.id})">Salvar</button></div>`;
    const levelSelect=admin?statusBadge('ADMIN'):`<select class="level-select" data-level-user="${u.id}"><option value="VIEWER" ${level==='VIEWER'?'selected':''}>Visualizador</option><option value="EDITOR" ${level==='EDITOR'?'selected':''}>Editor</option></select>`;
    return `<tr class="${u.status==='PENDING'?'admin-pending-row':u.status==='BLOCKED'?'admin-blocked-row':''}"><td><b>${esc(u.name)}</b></td><td>${esc(u.email)}</td><td>${statusBadge(u.role)}</td><td>${levelSelect}</td><td>${statusBadge(u.status)}</td><td>${access}</td><td>${esc(u.last_login||'—')}</td><td><div class="user-actions">${actions}</div></td></tr>`
  }).join('')||'<tr><td colspan="8">Nenhum usuário.</td></tr>';
  $('#admin-audit-body').innerHTML=auditRows.map(a=>`<tr><td>${esc(a.created_at||'')}</td><td>${esc(a.user_name||a.user_email||'Sistema')}</td><td>${statusBadge(a.action)}</td><td>${esc((a.entity_type||'')+(a.entity_id?' #'+a.entity_id:''))}</td><td>${esc(a.ip_address||'—')}</td></tr>`).join('')||'<tr><td colspan="5">Sem eventos.</td></tr>';
 }catch(e){toast(e.message,true)}
}
window.adminUserAction=async(id,action)=>{const labels={APPROVE:'aprovar',REJECT:'recusar',BLOCK:'bloquear',REACTIVATE:'reativar'};if(!confirm(`Deseja ${labels[action]||action.toLowerCase()} este usuário?`))return;try{await api(`/api/admin/users/${id}/${action}`,{method:'POST'});toast('Usuário atualizado.');loadAdmin()}catch(e){toast(e.message,true)}};
window.saveUserPermissions=async id=>{const box=$(`[data-access-user="${id}"]`);if(!box)return;const checked=k=>!!box.querySelector(`[data-access="${k}"]`)?.checked;const arena=checked('arena'),pavidez=checked('pavidez');try{await api(`/api/admin/users/${id}/permissions`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({bv:checked('bv'),quality_general:checked('quality_general'),quality_nc:checked('quality_nc'),contractor:arena||pavidez,arena,pavidez,admin:checked('admin'),permission_level:box.closest('tr')?.querySelector('[data-level-user]')?.value||'VIEWER'})});toast('Permissões atualizadas.');loadAdmin()}catch(e){toast(e.message,true)}};

async function loadBackups(){try{const d=await api('/api/backups');$('#backup-list').innerHTML=d.map(x=>`<div class="backup-item"><span><b>${esc(x.name)}</b><br><small>${esc(x.modified)} • ${num(x.size/1024/1024)} MB</small></span><div class="row-actions"><a href="/api/backups/${encodeURIComponent(x.name)}">Baixar</a><button class="tiny-btn danger" onclick="restoreBackup('${encodeURIComponent(x.name)}')">Restaurar</button></div></div>`).join('')||'<div class="empty">Nenhum backup criado.</div>'}catch(e){toast(e.message,true)}}
window.restoreBackup=async name=>{const typed=prompt('Restauração substitui o estado atual do banco. Um backup de segurança será criado antes.\n\nDigite RESTAURAR para confirmar:');if(String(typed||'').toUpperCase()!=='RESTAURAR')return;try{const d=await api(`/api/backups/${name}/restore`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmation:'RESTAURAR'})});toast(`Backup restaurado. Segurança: ${d.safety_backup}`);setTimeout(()=>location.reload(),1000)}catch(e){toast(e.message,true)}};

if($('#auto-monitor-save'))$('#auto-monitor-save').onclick=saveAutoMonitor;if($('#auto-monitor-run'))$('#auto-monitor-run').onclick=runAutoMonitor;if($('#auto-monitor-refresh'))$('#auto-monitor-refresh').onclick=()=>loadAutoMonitor(1);
$('#sync-all').onclick=async()=>{try{toast('Verificando todas as fontes locais...');const r=await api('/api/sync/all?force=false',{method:'POST'});const bad=r.filter(x=>!x.ok);toast(bad.length?`${bad.length} fonte(s) com erro. Veja Sincronização.`:'Sincronização concluída.',!!bad.length);loadDash()}catch(e){toast(e.message,true)}};
$('#dash-refresh').onclick=loadDash;if($('#dash-status'))$('#dash-status').onchange=loadDash;if($('#dash-contractor'))$('#dash-contractor').onchange=()=>{dashboardCertificateSelected.clear();loadDash()};if($('#dash-measurement'))$('#dash-measurement').onchange=()=>{if($('#dash-measurement').value){$('#dash-start').value='';$('#dash-end').value=''}loadDash()};['#dash-start','#dash-end'].forEach(id=>{const el=$(id);if(el)el.onchange=()=>{if(el.value&&$('#dash-measurement'))$('#dash-measurement').value=''}});$('#m-load').onclick=()=>loadMeasurements(1);$('#c-load').onclick=()=>loadCertificates(1);$('#c-clear').onclick=clearCertificateFilters;if($('#c-remove-duplicates'))$('#c-remove-duplicates').onclick=removeCertificateDuplicates;if($('#c-reprocess-no-result'))$('#c-reprocess-no-result').onclick=reprocessNoResultCertificates;$('#c-contractor').onchange=loadCertificateFilterOptions;$('#c-upload').onclick=uploadCert;$('#p-load').onclick=loadPending;$('#backup-create').onclick=async()=>{try{const d=await api('/api/backups',{method:'POST'});toast(`Backup ${d.name} criado.`);loadBackups()}catch(e){toast(e.message,true)}};
$('#go-certificates').onclick=()=>openPage('certificates');
['#c-segment'].forEach(id=>{const el=$(id);if(el)el.addEventListener('keydown',e=>{if(e.key==='Enter')loadCertificates()})});
$$('[data-auth-mode]').forEach(b=>b.onclick=()=>showAuthMode(b.dataset.authMode));
$('#tool-pdf-analyze').onclick=analyzeToolPdfs;$('#tool-pdf-csv').onclick=downloadToolCsv;$('#tool-pdf-excel').onclick=generateToolExcel;if($('#tool-pdf-write-main'))$('#tool-pdf-write-main').onclick=writeToolMainExcel;
if($('#tool-source-inspect'))$('#tool-source-inspect').onclick=inspectSourceWorkbook;
$('#login-form').onsubmit=async e=>{e.preventDefault();authMessage('Entrando...');try{const d=await api('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('#login-email').value,password:$('#login-password').value})});currentUser=d.user;applyRoleUI();const requested=new URLSearchParams(location.search).get('page');if(requested==='admin'&&canAccessPortal('ADMIN'))enterPortal('ADMIN','admin');else showPortalSelector();$('#login-password').value=''}catch(err){authMessage(err.message,true)}};
$('#register-form').onsubmit=async e=>{e.preventDefault();const payload={name:$('#register-name').value,email:$('#register-email').value,password:$('#register-password').value,confirm_password:$('#register-confirm').value};if(payload.password!==payload.confirm_password)return authMessage('As senhas não conferem.',true);authMessage('Enviando solicitação...');try{const d=await api('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});showAuthMode('login');authMessage(d.message||'Solicitação enviada.');$('#login-email').value=payload.email}catch(err){authMessage(err.message,true)}};
$('#forgot-form').onsubmit=async e=>{e.preventDefault();authMessage('Enviando...');try{const d=await api('/api/auth/password-reset/request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('#forgot-email').value})});authMessage(d.message)}catch(err){authMessage(err.message,true)}};
$('#reset-form').onsubmit=async e=>{e.preventDefault();const token=new URLSearchParams(location.search).get('reset_token')||'';const payload={token,password:$('#reset-password').value,confirm_password:$('#reset-confirm').value};if(payload.password!==payload.confirm_password)return authMessage('As senhas não conferem.',true);try{const d=await api('/api/auth/password-reset/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});history.replaceState({},'',location.pathname);showAuthMode('login');authMessage(d.message)}catch(err){authMessage(err.message,true)}};
$$('[data-portal-card]').forEach(card=>card.onclick=()=>{if(card.classList.contains('portal-locked'))return toast('Acesso não liberado. Solicite ao administrador.',true);enterPortal(card.dataset.portalCard)});
$('#portal-back-btn').onclick=showPortalSelector;$('#portal-logout-btn').onclick=doLogout;$('#logout-btn').onclick=doLogout;$('#admin-refresh').onclick=loadAdmin;$('#contractor-home-refresh').onclick=loadContractorHome;$('#kit-load').onclick=()=>loadKits(1);$('#kit-clear').onclick=clearKitFilters;$('#kit-contractor').onchange=()=>{loadKitFilterOptions();loadKits(1)};$('#kit-search').addEventListener('keydown',e=>{if(e.key==='Enter')loadKits(1)});


if($('#history-load'))$('#history-load').onclick=()=>loadHistory(1,1);if($('#history-clear'))$('#history-clear').onclick=()=>{if($('#history-date'))$('#history-date').value='';loadHistory(1,1)};if($('#history-date'))$('#history-date').addEventListener('keydown',e=>{if(e.key==='Enter')loadHistory(1,1)});
if($('#cycle-refresh'))$('#cycle-refresh').onclick=loadCycles;if($('#cycle-contractor'))$('#cycle-contractor').onchange=loadCycles;
if($('#bv-kpi-refresh'))$('#bv-kpi-refresh').onclick=loadBvKpi;if($('#bv-kpi-contractor'))$('#bv-kpi-contractor').onchange=()=>{if($('#bv-kpi-measurement'))$('#bv-kpi-measurement').value='ALL';loadBvKpi()};if($('#bv-kpi-measurement'))$('#bv-kpi-measurement').onchange=loadBvKpi;if($('#bv-kpi-type'))$('#bv-kpi-type').onchange=renderBvKpiDetails;
if($('#bv-report-refresh'))$('#bv-report-refresh').onclick=loadBvGeneralReport;if($('#bv-report-contractor'))$('#bv-report-contractor').onchange=loadBvGeneralReport;
if($('#bv-report-pdf'))$('#bv-report-pdf').onclick=downloadBvMissingReport;
if($('#review-refresh'))$('#review-refresh').onclick=()=>loadReview(1);['review-contractor','review-severity','review-type'].forEach(id=>{if($('#'+id))$('#'+id).onchange=()=>loadReview(1)});if($('#review-search'))$('#review-search').addEventListener('keydown',e=>{if(e.key==='Enter')loadReview(1)});if($('#review-export'))$('#review-export').onclick=exportReviewCsv;
if($('#health-refresh'))$('#health-refresh').onclick=loadHealth;
if($('#runtime-pause'))$('#runtime-pause').onclick=toggleRuntimePause;
if($('#runtime-cancel'))$('#runtime-cancel').onclick=cancelRuntime;
if($('#runtime-archive'))$('#runtime-archive').onclick=archiveRuntimeLogs;
if($('#runtime-shutdown'))$('#runtime-shutdown').onclick=shutdownQualimatch;
setInterval(()=>{if(currentUser)loadRuntimeState()},2500);
if($('#notification-btn'))$('#notification-btn').onclick=()=>{const p=$('#notification-panel');p.hidden=!p.hidden;if(!p.hidden)refreshNotifications()};
if($('#global-search-input'))$('#global-search-input').addEventListener('input',()=>{clearTimeout(globalSearchTimer);globalSearchTimer=setTimeout(runGlobalSearch,250)});
if($('#global-search-input'))$('#global-search-input').addEventListener('keydown',e=>{if(e.key==='Escape')$('#global-search-results').hidden=true});
document.addEventListener('click',e=>{if(!e.target.closest('.global-search')&&$('#global-search-results'))$('#global-search-results').hidden=true;if(!e.target.closest('.notification-center')&&$('#notification-panel'))$('#notification-panel').hidden=true});
bootstrapAuth();
setInterval(()=>{if(currentUser){refreshNotifications();if(typeof checkDesktopCertificateNotifications==='function')checkDesktopCertificateNotifications()}},60000);

if($('#bv-file-refresh'))$('#bv-file-refresh').onclick=()=>loadBvFiles(false);if($('#bv-file-company'))$('#bv-file-company').onchange=()=>loadBvFiles(false);if($('#bv-file-ext'))$('#bv-file-ext').onchange=()=>loadBvFiles(false);if($('#bv-file-search'))$('#bv-file-search').addEventListener('keydown',e=>{if(e.key==='Enter')loadBvFiles(false)});
if($('#kit-doc-load'))$('#kit-doc-load').onclick=loadKitDocuments;if($('#contractor-doc-refresh'))$('#contractor-doc-refresh').onclick=loadContractorFolderBrowser;if($('#contractor-doc-company'))$('#contractor-doc-company').onchange=loadContractorFolderBrowser;if($('#contractor-doc-search'))$('#contractor-doc-search').oninput=()=>{clearTimeout(window._contractorDocSearchTimer);window._contractorDocSearchTimer=setTimeout(loadContractorFolderDocs,250)};if($('#contractor-pending-refresh'))$('#contractor-pending-refresh').onclick=loadContractorPending;if($('#contractor-pending-company'))$('#contractor-pending-company').onchange=loadContractorPending;if($('#kit-doc-contractor'))$('#kit-doc-contractor').onchange=loadKitDocuments;

$('#tool-pdf-files')?.addEventListener('change',()=>{toolPdfOverrides={};toolPdfPreview=null;});

if($('#dash-certificates-trigger'))$('#dash-certificates-trigger').onclick=e=>{e.stopPropagation();const menu=$('#dash-certificates-menu');menu.hidden=!menu.hidden;if(!menu.hidden)$('#dash-certificates-search')?.focus()};
if($('#dash-certificates-search'))$('#dash-certificates-search').oninput=e=>renderDashboardCertificateOptions(e.target.value);
if($('#dash-certificates-clear'))$('#dash-certificates-clear').onclick=()=>{dashboardCertificateSelected.clear();renderDashboardCertificateOptions($('#dash-certificates-search')?.value||'');updateDashboardCertificateTrigger();loadDash()};
if($('#dash-certificates-all'))$('#dash-certificates-all').onclick=()=>{dashboardCertificateSelected.clear();renderDashboardCertificateOptions($('#dash-certificates-search')?.value||'');updateDashboardCertificateTrigger();loadDash()};
document.addEventListener('click',e=>{if(!e.target.closest('#dash-certificates-filter')&&$('#dash-certificates-menu'))$('#dash-certificates-menu').hidden=true});
