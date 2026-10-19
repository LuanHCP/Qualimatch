/* Busca manual livre de medição para PDF -> BD_QUALI.
   Carregado depois de app.js pelo run.py, sem substituir as customizações visuais existentes. */
(function(){
 const style=document.createElement('style');
 style.textContent=`
 .tool-review-control.qm-manual-link{gap:6px;flex-wrap:wrap;align-items:center}
 .qm-manual-link .manual-search-btn{white-space:nowrap}
 .qm-measurement-search{display:grid;gap:14px;min-width:min(860px,88vw)}
 .qm-measurement-search .manual-note{padding:10px 12px;border:1px solid rgba(126,104,205,.35);border-radius:10px;background:rgba(111,79,190,.09);font-size:13px;line-height:1.45}
 .qm-measurement-filters{display:grid;grid-template-columns:1.35fr .85fr .9fr .8fr;gap:10px}
 .qm-measurement-filters label{display:grid;gap:5px;font-size:12px;color:var(--muted,#aaa)}
 .qm-measurement-filters input{width:100%}
 .qm-measurement-results{max-height:48vh;overflow:auto;border:1px solid rgba(255,255,255,.08);border-radius:12px}
 .qm-measurement-result{display:grid;grid-template-columns:minmax(145px,1.05fr) minmax(100px,.75fr) minmax(200px,1.55fr) auto;gap:10px;align-items:center;padding:11px 12px;border-bottom:1px solid rgba(255,255,255,.07)}
 .qm-measurement-result:last-child{border-bottom:0}
 .qm-measurement-result b{display:block}
 .qm-measurement-result small{display:block;color:var(--muted,#aaa);margin-top:3px;line-height:1.35}
 .qm-measurement-empty{padding:18px;text-align:center;color:var(--muted,#aaa)}
 .qm-search-actions{display:flex;gap:8px;justify-content:flex-end;align-items:center}
 @media(max-width:820px){.qm-measurement-filters{grid-template-columns:1fr 1fr}.qm-measurement-result{grid-template-columns:1fr}.qm-measurement-result button{justify-self:start}}
 `;
 document.head.appendChild(style);

 const originalToolReviewCell=toolReviewCell;

 function quickCandidates(x){
  const candidates=x.measurement_candidates||[];
  if(!candidates.length||String(x.match_status||'').toUpperCase()==='VINCULADO')return '';
  const opts=candidates.map(c=>`<option value="${Number(c.id)}">${esc(c.line_measurement||'Linha ?')} • ${esc(c.road||'')} ${fmtSta(c.kmi)}–${fmtSta(c.kmf)} • ${esc(c.direction||'')} ${esc(c.lane||'')} • score ${num(c.score,1)}</option>`).join('');
  return `<select data-tool-review-key="${esc(x.line_key)}"><option value="">Sugestões automáticas...</option>${opts}</select><button class="ghost compact" data-tool-review-apply="${esc(x.line_key)}">Usar</button>`;
 }

 toolReviewCell=function(x){
  const badge=toolMatchBadge(x.match_status,x.match_reason);
  const linked=String(x.match_status||'').toUpperCase()==='VINCULADO';
  const label=linked?'Alterar vínculo':'Buscar medição';
  return `<div class="tool-review-control qm-manual-link">${badge}${quickCandidates(x)}<button class="ghost compact manual-search-btn" type="button" data-manual-line-key="${esc(x.line_key)}" onclick="openManualMeasurementSearch(this.dataset.manualLineKey)">${label}</button></div>`;
 };

 function currentLine(){
  const key=window.__qmManualMeasurementLineKey||'';
  return (toolPdfPreview?.lines||[]).find(x=>String(x.line_key||'')===String(key))||null;
 }

 function parseStationInput(value){
  const raw=String(value||'').trim().replace(/\s/g,'');
  if(!raw)return null;
  let m=raw.match(/^(\d{1,4})\+(\d{1,3})$/);
  if(m)return Number(m[1])*1000+Number(m[2]);
  const normalized=raw.replace(',','.');
  if(/^\d+(?:\.\d+)?$/.test(normalized)){
   const n=Number(normalized);
   if(!Number.isFinite(n))return null;
   if(normalized.includes('.')&&n<10000)return Math.round(n*1000);
   return Math.round(n);
  }
  return null;
 }

 function stationText(v){
  if(v===null||v===undefined||v==='')return '—';
  const n=Number(v);if(!Number.isFinite(n))return esc(v);
  return `${Math.floor(n/1000)}+${String(Math.round(n%1000)).padStart(3,'0')}`;
 }

 function resultMarkup(m){
  const road=m.road||'—',dir=m.direction||'—',lane=m.lane||'—';
  const trecho=(m.kmi==null||m.kmf==null)?'Trecho não informado':`${road} ${stationText(m.kmi)} a ${stationText(m.kmf)}`;
  return `<div class="qm-measurement-result">
   <div><b>${esc(m.line_measurement||'Linha não informada')}</b><small>Ref.: ${esc(m.ref_measurement||'—')} • linha fonte ${esc(m.source_row||'—')}</small></div>
   <div><b>${dateBR(m.date)}</b><small>${esc(m.contractor||'')}</small></div>
   <div><b>${trecho}</b><small>${esc(dir)} • ${esc(lane)}</small></div>
   <button class="primary compact" type="button" onclick="applyManualMeasurementLink(${Number(m.id)})">Vincular</button>
  </div>`;
 }

 window.openManualMeasurementSearch=function(lineKey){
  const line=(toolPdfPreview?.lines||[]).find(x=>String(x.line_key||'')===String(lineKey));
  if(!line)return toast('Não foi possível localizar este CP na prévia.',true);
  window.__qmManualMeasurementLineKey=String(lineKey);
  const current=line.measurement||{};
  showModal(`<div class="qm-measurement-search">
   <div><span class="eyebrow">VÍNCULO MANUAL</span><h2>Buscar medição para ${esc(line.certificate||'certificado')} • CP ${esc(line.cp_number||'—')}</h2>
   <p class="muted">A busca não fica limitada aos candidatos automáticos nem à data lida no PDF.</p></div>
   <div class="manual-note"><b>Ao confirmar uma medição, este CP será tratado como VINCULADO para a gravação na BD_QUALI principal.</b><br>A contratada fica fixa em <b>${esc(line.contractor||'—')}</b> para impedir vínculo cruzado entre ARENA e PAVIDEZ.</div>
   <div class="qm-measurement-filters">
    <label><span>Linha / referência</span><input id="qm-mm-q" placeholder="Ex.: 2175 ou M13" value="${esc(current.line_measurement||'')}"></label>
    <label><span>Data</span><input id="qm-mm-date" type="date" value="${esc(line.application_date||current.date||'')}"></label>
    <label><span>Rodovia</span><input id="qm-mm-road" placeholder="Ex.: BR-376" value="${esc(line.road_pdf||current.road||'')}"></label>
    <label><span>KM / Estaca</span><input id="qm-mm-km" placeholder="Ex.: 309+310" value="${line.station==null?'':stationText(line.station)}"></label>
   </div>
   <div class="qm-search-actions"><span class="muted" id="qm-mm-count"></span><button class="ghost" type="button" onclick="closeModal()">Cancelar</button><button class="primary" id="qm-mm-search" type="button" onclick="runManualMeasurementSearch()">Pesquisar</button></div>
   <div id="qm-mm-results" class="qm-measurement-results"><div class="qm-measurement-empty">Use os filtros acima e clique em Pesquisar.</div></div>
  </div>`);
 };

 window.runManualMeasurementSearch=async function(){
  const line=currentLine();if(!line)return;
  const q=String(document.querySelector('#qm-mm-q')?.value||'').trim();
  const date=String(document.querySelector('#qm-mm-date')?.value||'').trim();
  const road=String(document.querySelector('#qm-mm-road')?.value||'').trim().toUpperCase();
  const km=parseStationInput(document.querySelector('#qm-mm-km')?.value||'');
  const serverSearch=q||date||road||'';
  const btn=document.querySelector('#qm-mm-search'),box=document.querySelector('#qm-mm-results'),count=document.querySelector('#qm-mm-count');
  if(btn){btn.disabled=true;btn.textContent='Pesquisando...'}
  if(box)box.innerHTML='<div class="qm-measurement-empty">Consultando a base de Medições sincronizada...</div>';
  try{
   const url=`/api/measurements?contractor=${encodeURIComponent(line.contractor||'ALL')}&search=${encodeURIComponent(serverSearch)}&limit=2000`;
   const data=await api(url);
   const qUp=q.toUpperCase();
   let items=(Array.isArray(data)?data:(data?.items||[])).filter(m=>{
    if(String(m.contractor||'').toUpperCase()!==String(line.contractor||'').toUpperCase())return false;
    if(date&&String(m.date||'').slice(0,10)!==date)return false;
    if(road&&!String(m.road||'').toUpperCase().includes(road))return false;
    if(qUp){const hay=[m.line_measurement,m.ref_measurement,m.road,m.date,m.source_row].map(v=>String(v??'').toUpperCase()).join(' ');if(!hay.includes(qUp))return false}
    if(km!==null){const a=Number(m.kmi),b=Number(m.kmf);if(!Number.isFinite(a)||!Number.isFinite(b)||km<Math.min(a,b)||km>Math.max(a,b))return false}
    return true;
   });
   items=items.slice(0,100);
   if(count)count.textContent=`${items.length} resultado(s)`;
   if(box)box.innerHTML=items.length?items.map(resultMarkup).join(''):'<div class="qm-measurement-empty">Nenhuma medição encontrada com esses filtros. Tente remover a data ou o KM para ampliar a busca.</div>';
  }catch(e){if(box)box.innerHTML=`<div class="qm-measurement-empty bad-text">${esc(e.message||'Falha ao pesquisar medições.')}</div>`}
  finally{if(btn){btn.disabled=false;btn.textContent='Pesquisar'}}
 };

 window.applyManualMeasurementLink=function(measurementId){
  const key=window.__qmManualMeasurementLineKey;
  if(!key||!measurementId)return;
  toolPdfOverrides[key]=Number(measurementId);
  closeModal();
  analyzeToolPdfs(true);
 };
})();
