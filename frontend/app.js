const $=s=>document.querySelector(s),$$=s=>Array.from(document.querySelectorAll(s));
const state={page:'dashboard',certPage:1,measurementPage:1,dashCertificates:new Set(),certificateOptions:[]};
const titles={dashboard:['Dashboard','Visão financeira, qualidade e certificados'],certificates:['Certificados','BI330 com resumo estatístico, VV, espessura e corpos de prova'],pending:['Pendências','Somente certificados pendentes sob responsabilidade técnica'],measurements:['Medições','Base operacional usada no cruzamento']};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=1)=>Number(v??0).toLocaleString('pt-BR',{minimumFractionDigits:0,maximumFractionDigits:d});
const brl=v=>Number(v??0).toLocaleString('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0});
const dateBR=v=>{if(!v)return'—';const p=String(v).slice(0,10).split('-');return p.length===3?`${p[2]}/${p[1]}/${p[0]}`:String(v)};
const fmtSta=v=>{const n=Number(v);if(!Number.isFinite(n))return'—';return`${Math.floor(n/1000)}+${String(Math.round(n%1000)).padStart(3,'0')}`};
const pct=(v,d=1)=>v==null?'—':num(v,d)+'%';
const cm=(v,d=2)=>v==null?'—':num(v,d)+' cm';
const statusBadge=v=>{const s=String(v||'SEM RESULTADO').toUpperCase();const cls=s.includes('APROV')||s==='CARREGADO'||s==='ENTREGUE'?'ok':s.includes('REPROV')||s.includes('PENDENTE CERTIFICADO')?'bad':s.includes('PEND')||s.includes('PARCIAL')||s.includes('SEM')?'warn':'neutral';return`<span class="status-badge ${cls}">${esc(s)}</span>`};
const query=o=>{const p=new URLSearchParams();Object.entries(o).forEach(([k,v])=>{if(v!==''&&v!=null)p.set(k,v)});return p};
async function api(url){progress();const r=await fetch(url);let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||'Falha na API');return d}
function toast(m,bad=false){const e=$('#toast');e.textContent=m;e.style.display='block';e.style.borderColor=bad?'#6f303b':'#413b5b';clearTimeout(window.__toast);window.__toast=setTimeout(()=>e.style.display='none',3500)}
function progress(){const e=$('#qm-progress');e.classList.remove('run');void e.offsetWidth;e.classList.add('run')}
function metric(label,value,hint,technical=false){return`<div class="card ${technical?'technical':''}"><div class="label">${esc(label)}</div><div class="value">${value}</div><div class="hint">${esc(hint)}</div></div>`}
function measurementOptionLabel(x){return`${x.measurement} • ${dateBR(x.measurement_start)} a ${dateBR(x.measurement_end)}`}
function currentDashCertificates(){return[...state.dashCertificates]}

async function loadCycleOptions(selectors,contractor='ALL'){
  const items=await api('/api/measurement-cycles/options?contractor='+encodeURIComponent(contractor));
  for(const selector of selectors){const sel=$(selector);if(!sel)continue;const cur=sel.value;sel.innerHTML='<option value="">Todas as medições</option>'+items.map(x=>`<option value="${esc(x.measurement)}">${esc(measurementOptionLabel(x))}</option>`).join('');if(items.some(x=>x.measurement===cur))sel.value=cur}
  return items;
}
async function loadDashCertificateOptions(){
  const contractor=$('#dash-contractor').value,current=currentDashCertificates();
  const d=await api('/api/certificates-filter-options?contractor='+encodeURIComponent(contractor));
  state.certificateOptions=d.numbers||[];
  state.dashCertificates=new Set(current.filter(x=>state.certificateOptions.includes(x)));
  renderDashCertificateOptions();renderDashCertificateChips();
}
function renderDashCertificateOptions(){
  const q=($('#dash-cert-search')?.value||'').trim().toUpperCase();
  const items=state.certificateOptions.filter(x=>!q||x.toUpperCase().includes(q));
  $('#dash-cert-options').innerHTML=items.map(n=>`<label class="multi-option"><input type="checkbox" value="${esc(n)}" ${state.dashCertificates.has(n)?'checked':''}><span>${esc(n)}</span></label>`).join('')||'<div class="empty">Nenhum certificado.</div>';
  $$('#dash-cert-options input').forEach(cb=>cb.onchange=()=>{cb.checked?state.dashCertificates.add(cb.value):state.dashCertificates.delete(cb.value);renderDashCertificateChips();loadDash()});
  const c=state.dashCertificates.size;$('#dash-cert-count').textContent=c?`${c} sel.`:'Todos';
}
function renderDashCertificateChips(){
  $('#dash-cert-chips').innerHTML=currentDashCertificates().map(n=>`<span class="selection-chip">${esc(n)}<button type="button" data-remove-cert="${esc(n)}">×</button></span>`).join('');
  $$('[data-remove-cert]').forEach(b=>b.onclick=()=>{state.dashCertificates.delete(b.dataset.removeCert);renderDashCertificateOptions();renderDashCertificateChips();loadDash()});
}
function renderStatusPie(items){
  const total=items.reduce((s,x)=>s+Number(x.count||0),0);if(!total)return'<div class="empty">Sem dados neste filtro.</div>';
  const approved=items.filter(x=>String(x.status).includes('APROV')).reduce((s,x)=>s+Number(x.count||0),0),reproved=items.filter(x=>String(x.status).includes('REPROV')).reduce((s,x)=>s+Number(x.count||0),0),pending=Math.max(0,total-approved-reproved);
  const a=approved/total*100,r=reproved/total*100;
  const chart=`conic-gradient(#4bd6a0 0 ${a}%,#f3bf67 ${a}% ${100-r}%,#ff7180 ${100-r}% 100%)`;
  const rows=[['approved','Aprovado',approved],['pending','Pendente / ajustes',pending],['reproved','Reprovado',reproved]];
  return`<div class="pie-layout"><div class="pie-chart" style="background:${chart}"><div class="pie-hole"><b>${total}</b><span>linhas</span></div></div><div class="pie-legend">${rows.map(([c,n,v])=>`<div class="pie-legend-row"><i class="pie-dot ${c}"></i><span class="pie-name">${n}</span><b>${v}</b><small>${num(v/total*100,1)}%</small></div>`).join('')}</div></div>`;
}
async function loadDash(){
  try{
    await loadCycleOptions(['#dash-measurement'], $('#dash-contractor').value);
    const q={contractor:$('#dash-contractor').value,status:$('#dash-status').value,measurement:$('#dash-measurement').value,start:$('#dash-start').value,end:$('#dash-end').value,certificates:currentDashCertificates().join(',')};
    const d=await api('/api/dashboard?'+query(q)),T=d.totals||{},F=d.financial||{},C=d.certificate_summary||{};
    $('#dash-measurement-period').textContent=d.measurement_period?`${d.measurement_period.measurement}: ${dateBR(d.measurement_period.measurement_start)} a ${dateBR(d.measurement_period.measurement_end)}`:'';
    $('#financial-kpis').innerHTML=[metric('Total serviço',brl(T.total_service),'Base operacional sintética'),metric('Aprovado',brl(F.approved),'Classificação financeira fictícia'),metric('Pendente',brl(F.pending),'Registros aguardando fechamento'),metric('Reprovado',brl(F.reproved),'Registros classificados como reprovados'),metric('Extensão',num(T.extension_m,0)+' m','Extensão executada'),metric('CBUQ',num(T.quantity_t,1)+' t','Quantidade de projeto'),metric('CAP',num(T.cap_project_t,1)+' t','Quantidade estimada de ligante')].join('');
    $('#technical-kpis').innerHTML=[metric('Certificados',num(C.total,0),`${num(C.approved,0)} aprovados + ${num(C.reproved,0)} reprovados + ${num(C.adjustments,0)} ajustes`,true),metric('Aprovados',num(C.approved,0),'Status final do BI',true),metric('Reprovados',num(C.reproved,0),'Status final do BI',true),metric('Ajustes / sem resultado',num(C.adjustments,0),'Leitura parcial ou sem ensaio',true),metric('Dias pendentes',num(d.pending_days,0),'Dias medidos sem certificado válido',true),metric('Quantidade CPs',num(C.sample_count,0),'Corpos de prova fictícios',true)].join('');
    $('#recent-certificates').innerHTML=renderRecent(C.recent||[]);$('#status-pie').innerHTML=renderStatusPie(d.statuses||[]);
    $('#source-info').innerHTML=(d.sources||[]).map(x=>`<div class="source-info"><div class="big-source"><b>${esc(x.contractor)}</b> ${statusBadge(x.summary_source)}</div><span><b>Usado:</b> ${esc(x.cell)}</span><br><small>${num(x.total_records,0)} linhas • ${esc(x.synced_at)}</small><div class="meta">Soma demonstrativa: ${brl(x.all_rows_total)}</div></div>`).join('');
  }catch(e){toast(e.message,true)}
}
function renderRecent(list){if(!list.length)return'<div class="empty">Nenhum certificado neste filtro.</div>';return`<div class="table-wrap"><table><thead><tr><th>Certificado</th><th>Data</th><th>Trecho</th><th>VV médio</th><th>Esp. média</th><th>VV</th><th>Esp.</th></tr></thead><tbody>${list.map(x=>`<tr><td><button class="cert-link" onclick="openCertificate(${x.id})">${esc(x.number)}</button><span class="sub">${esc(x.contractor)}</span></td><td>${dateBR(x.extraction_date)}</td><td>${esc(x.road)}<span class="sub">${fmtSta(x.kmi)} a ${fmtSta(x.kmf)}</span></td><td>${pct(x.mean_vv,2)}</td><td>${cm(x.mean_thickness_cm,2)}</td><td>${statusBadge(x.status_vv)}</td><td>${statusBadge(x.status_thickness)}</td></tr>`).join('')}</tbody></table></div>`}

async function loadCertificateFilterOptions(){
  const contractor=$('#c-contractor').value,d=await api('/api/certificates-filter-options?contractor='+encodeURIComponent(contractor));
  const road=$('#c-road'),number=$('#c-number'),measurement=$('#c-measurement');const cr=road.value,cn=number.value,cmv=measurement.value;
  road.innerHTML='<option value="">Todas as BR/PR</option>'+(d.roads||[]).map(x=>`<option>${esc(x)}</option>`).join('');if((d.roads||[]).includes(cr))road.value=cr;
  number.innerHTML='<option value="">Todos os certificados</option>'+(d.numbers||[]).map(x=>`<option>${esc(x)}</option>`).join('');if((d.numbers||[]).includes(cn))number.value=cn;
  measurement.innerHTML='<option value="">Todas as medições</option>'+(d.measurements||[]).map(x=>`<option value="${esc(x.measurement)}">${esc(measurementOptionLabel(x))}</option>`).join('');if((d.measurements||[]).some(x=>x.measurement===cmv))measurement.value=cmv;
}
async function loadCertificates(page=1){
  try{state.certPage=page;await loadCertificateFilterOptions();const q={contractor:$('#c-contractor').value,measurement:$('#c-measurement').value,vv_status:$('#c-vv-status').value,thickness_status:$('#c-thickness-status').value,road:$('#c-road').value,number:$('#c-number').value,segment:$('#c-segment').value,sort:$('#c-sort').value,page,page_size:30};const d=await api('/api/certificates?'+query(q));
    const list=d.items||[],ap=list.filter(x=>x.overall_status==='APROVADO').length,rp=list.filter(x=>x.overall_status==='REPROVADO').length,adj=list.length-ap-rp,cp=list.filter(x=>x.counterproof_state==='ENTREGUE').length;
    $('#certificate-summary').innerHTML=`<div class="summary-chip"><b>${d.total}</b> encontrados</div><div class="summary-chip"><b>${ap}</b> aprovados nesta página</div><div class="summary-chip"><b>${rp}</b> reprovados nesta página</div><div class="summary-chip"><b>${adj}</b> ajustes nesta página</div><div class="summary-chip"><b>${cp}</b> com contra-prova entregue</div>`;
    $('#c-body').innerHTML=list.map(x=>{const cls=x.overall_status==='APROVADO'?'cert-row-approved':x.overall_status==='REPROVADO'?'cert-row-reproved':'cert-row-adjust';return`<tr class="${cls}"><td><button class="cert-link" onclick="openCertificate(${x.id})">${esc(x.number)}</button><span class="sub">${esc(x.contractor)}</span></td><td>${dateBR(x.extraction_date)}</td><td><b>${esc(x.road)}</b><span class="sub">${fmtSta(x.kmi)} a ${fmtSta(x.kmf)}</span></td><td title="${esc(x.trace_approved)}">${esc(x.trace_approved)}</td><td>${num(x.sample_count,0)}</td><td><b>${pct(x.mean_vv,2)}</b></td><td><b>${cm(x.mean_thickness_cm,2)}</b></td><td>${pct(x.mean_ratio,2)}</td><td>${statusBadge(x.status_vv)}</td><td>${statusBadge(x.status_thickness)}</td><td>${statusBadge(x.counterproof_state)}</td><td>${statusBadge(x.parse_status)}</td></tr>`}).join('')||'<tr><td colspan="12">Nenhum certificado encontrado.</td></tr>';
    renderPagination('#certificate-pagination',d.total,d.page,d.page_size,p=>loadCertificates(p));
  }catch(e){toast(e.message,true)}
}
function clearCertificateFilters(){$('#c-contractor').value='ALL';$('#c-measurement').value='';$('#c-vv-status').value='ALL';$('#c-thickness-status').value='ALL';$('#c-road').value='';$('#c-number').value='';$('#c-segment').value='';$('#c-sort').value='newest';loadCertificates(1)}

async function loadPending(){try{await loadCycleOptions(['#p-measurement'],$('#p-contractor').value);const d=await api('/api/pending?'+query({contractor:$('#p-contractor').value,measurement:$('#p-measurement').value}));$('#pending-summary').innerHTML=`<div class="summary-chip"><b>${d.total}</b> dias pendentes</div><div class="summary-chip"><b>100%</b> dados fictícios</div>`;$('#p-body').innerHTML=(d.items||[]).map(x=>`<tr><td><b>${esc(x.contractor)}</b></td><td>${esc(x.measurement)}</td><td>${dateBR(x.date)}</td><td>${esc(x.road)}</td><td>${num(x.lines,0)}</td><td>${statusBadge(x.delivery)}</td><td>${statusBadge(x.status)}</td></tr>`).join('')||'<tr><td colspan="7">Sem pendências neste filtro.</td></tr>'}catch(e){toast(e.message,true)}}
async function loadMeasurements(page=1){try{state.measurementPage=page;await loadCycleOptions(['#m-measurement'],$('#m-contractor').value);const d=await api('/api/measurements?'+query({contractor:$('#m-contractor').value,measurement:$('#m-measurement').value,search:$('#m-search').value,page,page_size:40}));$('#m-body').innerHTML=(d.items||[]).map(x=>`<tr><td>${esc(x.line_measurement)}</td><td>${esc(x.contractor)}</td><td>${dateBR(x.date)}</td><td>${esc(x.ref_measurement)}</td><td>${esc(x.road)}</td><td>${esc(x.direction)}</td><td>${fmtSta(x.kmi)}</td><td>${fmtSta(x.kmf)}</td><td>${esc(x.lane)}</td><td>${num(x.extension_m,0)} m</td><td>${num(x.width_m,2)} m</td><td>${num(Number(x.thickness_m)*100,2)} cm</td><td>${num(x.volume_mass_m3,2)} m³</td><td>${num(x.quantity_t,1)} t</td></tr>`).join('')||'<tr><td colspan="14">Sem dados.</td></tr>';renderPagination('#measurement-pagination',d.total,d.page,d.page_size,p=>loadMeasurements(p))}catch(e){toast(e.message,true)}}
function renderPagination(selector,total,page,size,handler){const box=$(selector),pages=Math.max(1,Math.ceil(total/size)),from=total?(page-1)*size+1:0,to=Math.min(total,page*size),start=Math.max(1,page-2),end=Math.min(pages,start+4);let buttons=`<button ${page<=1?'disabled':''} data-p="${page-1}">Anterior</button>`;for(let p=start;p<=end;p++)buttons+=`<button data-p="${p}" class="${p===page?'active':''}">${p}</button>`;buttons+=`<button ${page>=pages?'disabled':''} data-p="${page+1}">Próxima</button>`;box.innerHTML=`<span>${from}–${to} de ${total}</span><div class="pagination-controls">${buttons}</div>`;box.querySelectorAll('[data-p]').forEach(b=>b.onclick=()=>{const p=Number(b.dataset.p);if(p>=1&&p<=pages&&p!==page)handler(p)})}

window.openCertificate=async id=>{try{const c=await api('/api/certificates/'+id);$('#modal-body').innerHTML=`<div class="detail-head"><div><span class="eyebrow">CERTIFICADO BI330 • DEMO</span><h2>${esc(c.number)}</h2><div class="meta">${esc(c.contractor)} • ${dateBR(c.extraction_date)}</div></div><div>${statusBadge(c.overall_status)}</div></div><div class="detail-grid"><div class="detail-field"><b>Rodovia</b>${esc(c.road)}</div><div class="detail-field"><b>Trecho</b>${fmtSta(c.kmi)} a ${fmtSta(c.kmf)}</div><div class="detail-field"><b>Traço</b>${esc(c.trace_approved)}</div><div class="detail-field"><b>Data aplicação</b>${dateBR(c.service_date)}</div><div class="detail-field"><b>VV médio</b>${pct(c.mean_vv,2)}</div><div class="detail-field"><b>Esp. média</b>${cm(c.mean_thickness_cm,2)}</div><div class="detail-field"><b>A/B médio</b>${pct(c.mean_ratio,2)}</div><div class="detail-field"><b>Contra-prova</b>${statusBadge(c.counterproof_state)}</div></div><div class="phase-card"><div class="panel-head"><div><h3>Corpos de prova</h3><p>Valores sintéticos gerados a partir da média do certificado.</p></div></div><div class="table-wrap"><table><thead><tr><th>CP</th><th>Data</th><th>Rodovia</th><th>Estaca</th><th>Faixa</th><th>Vv</th><th>Espessura</th><th>A/B</th></tr></thead><tbody>${(c.samples||[]).map(s=>`<tr><td>CP ${s.cp}</td><td>${dateBR(s.application_date)}</td><td>${esc(s.road)}</td><td>${fmtSta(s.kmi)}</td><td>${esc(s.lane)}</td><td>${pct(s.vv,2)}</td><td>${cm(s.thickness_cm,2)}</td><td>${pct(s.ratio,2)}</td></tr>`).join('')}</tbody></table></div></div>`;$('#modal').classList.add('open')}catch(e){toast(e.message,true)}};
function closeModal(){$('#modal').classList.remove('open')}

function openPage(page){state.page=page;$$('#nav button').forEach(x=>x.classList.toggle('active',x.dataset.page===page));$$('.page').forEach(x=>x.classList.toggle('active',x.id==='page-'+page));const t=titles[page];$('#page-title').textContent=t[0];$('#page-subtitle').textContent=t[1];loadCurrent()}
async function loadCurrent(){if(state.page==='dashboard')return loadDash();if(state.page==='certificates')return loadCertificates(state.certPage);if(state.page==='pending')return loadPending();return loadMeasurements(state.measurementPage)}

$$('#nav button').forEach(b=>b.onclick=()=>openPage(b.dataset.page));$('#refresh-current').onclick=loadCurrent;$('#dash-refresh').onclick=loadDash;$('#dash-status').onchange=loadDash;$('#dash-measurement').onchange=()=>{if($('#dash-measurement').value){$('#dash-start').value='';$('#dash-end').value=''}loadDash()};$('#dash-contractor').onchange=async()=>{state.dashCertificates.clear();await Promise.all([loadDashCertificateOptions(),loadDash()])};['#dash-start','#dash-end'].forEach(id=>$(id).onchange=()=>{if($(id).value)$('#dash-measurement').value=''});$('#go-certificates').onclick=()=>openPage('certificates');
$('#dash-cert-trigger').onclick=e=>{e.stopPropagation();$('#dash-cert-menu').hidden=!$('#dash-cert-menu').hidden};$('#dash-cert-menu').onclick=e=>e.stopPropagation();$('#dash-cert-search').oninput=renderDashCertificateOptions;$('#dash-cert-all').onclick=()=>{state.dashCertificates.clear();renderDashCertificateOptions();renderDashCertificateChips();loadDash()};$('#dash-cert-clear').onclick=$('#dash-cert-all').onclick;document.addEventListener('click',()=>$('#dash-cert-menu').hidden=true);
$('#c-load').onclick=()=>loadCertificates(1);$('#c-clear').onclick=clearCertificateFilters;$('#c-contractor').onchange=()=>{loadCertificateFilterOptions();state.certPage=1};$('#c-segment').onkeydown=e=>{if(e.key==='Enter')loadCertificates(1)};$('#p-load').onclick=loadPending;$('#p-contractor').onchange=loadPending;$('#m-load').onclick=()=>loadMeasurements(1);$('#m-contractor').onchange=()=>loadMeasurements(1);$('#m-search').onkeydown=e=>{if(e.key==='Enter')loadMeasurements(1)};$('#modal-close').onclick=closeModal;$('#modal').onclick=e=>{if(e.target===$('#modal'))closeModal()};document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
(async()=>{try{await Promise.all([loadDashCertificateOptions(),loadCycleOptions(['#p-measurement','#m-measurement'])]);await loadDash()}catch(e){toast(e.message,true)}})();
