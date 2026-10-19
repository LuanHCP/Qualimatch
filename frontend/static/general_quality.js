/* QualiMatch — Qualidade Geral (traços + RNCs) */
var qgTraceMap = new Map();
var qgNCMap = new Map();
var qgApprovedContractorPending = "";

function qgDateTimeBR(value){
  if(!value) return "—";
  var text=String(value), day=dateBR(text), m=text.match(/[T ](\d{2}):(\d{2})/);
  return m ? day+" "+m[1]+":"+m[2] : day;
}
function qgBytes(value){
  var n=Number(value||0), units=["B","KB","MB","GB"], i=0;
  while(n>=1024 && i<units.length-1){n/=1024;i++;}
  return n.toLocaleString("pt-BR",{maximumFractionDigits:i?1:0})+" "+units[i];
}
function qgNorm(value){
  return String(value||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toUpperCase();
}
function qgTraceKey(x){return String(x.sheet||"S")+":"+String(x.source_row||0);}
function qgNCKey(x){return String(x.emission_no||x.source_row||"");}
function qgRememberTraces(items){(items||[]).forEach(function(x){qgTraceMap.set(qgTraceKey(x),x);});}
function qgRememberNC(items){(items||[]).forEach(function(x){qgNCMap.set(qgNCKey(x),x);});}
function qgFillSelect(id, values, allLabel){
  var el=$("#"+id); if(!el)return;
  var current=el.value||"ALL";
  el.innerHTML='<option value="ALL">'+esc(allLabel)+'</option>'+(values||[]).map(function(v){return '<option value="'+esc(v)+'">'+esc(v)+'</option>';}).join("");
  if(Array.from(el.options).some(function(o){return o.value===current;})) el.value=current;
}
function qgFillTraceFilters(f){
  [
    ["qg-overview-contractor",f.contractors,"Todas as contratadas"],["qg-overview-type",f.trace_types,"Todos os tipos"],
    ["qga-contractor",f.contractors,"Todas as contratadas"],["qga-type",f.trace_types,"Todos os tipos"],
    ["qga-plant",f.plants,"Todas as usinas"],["qga-binder",f.binders,"Todos os ligantes"],
    ["qgt-contractor",f.contractors,"Todas as contratadas"],["qgt-type",f.trace_types,"Todos os tipos"],
    ["qgt-status",f.statuses,"Todos os status"],["qgt-plant",f.plants,"Todas as usinas"],
    ["qgt-binder",f.binders,"Todos os ligantes"]
  ].forEach(function(a){qgFillSelect(a[0],a[1]||[],a[2]);});
}
function qgTraceClass(value){
  var s=qgNorm(value);
  if(s==="VENCIDO")return "expired";
  if(s==="APROVADO")return "approved";
  if(s.indexOf("RESTR")>=0||s.indexOf("RESSALV")>=0)return "restricted";
  if(s.indexOf("REPROV")>=0||s.indexOf("NAO CONFORM")>=0)return "rejected";
  if(s.indexOf("ANAL")>=0||s.indexOf("SOLICIT")>=0||s.indexOf("AGUARD")>=0)return "analysis";
  if(s.indexOf("CANCEL")>=0)return "cancelled";
  return "other";
}
function qgTraceBadge(value){return '<span class="qg-status qg-status-'+qgTraceClass(value)+'">'+esc(value||"—")+'</span>';}
function qgDays(x){
  var n=x&&x.days_to_expire;
  if(n===null||n===undefined)return "—";
  n=Number(n);
  if(n<0)return '<span class="qg-expired">Vencido há '+Math.abs(n)+'d</span>';
  if(n<=30)return '<span class="qg-expiring">'+num(n,0)+'d</span>';
  return num(n,0)+"d";
}
function qgSourceLabel(source, fallback){
  if(!source||!source.exists)return "Fonte não configurada";
  return (source.file_name||fallback)+" • atualizado "+qgDateTimeBR(source.modified_at);
}
function qgDoc(x){
  var url=String((x&&x.link)||"").trim();
  if(/^https?:\/\//i.test(url))return '<a class="qg-doc-link" href="'+esc(url)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">Abrir</a>';
  return url?'<span class="qg-doc-muted">Referência</span>':"—";
}
function qgTraceRow(x, approved){
  qgTraceMap.set(qgTraceKey(x),x);
  var html='<tr class="qg-click-row" onclick="openGeneralQualityDetail(\''+esc(qgTraceKey(x))+'\')">';
  html+='<td><b>'+esc(x.code||"—")+'</b></td><td>'+esc(x.contractor||"—")+'</td><td>'+esc(x.category||x.sheet||"—")+'</td>';
  html+='<td class="qg-trace-cell" title="'+esc(x.trace||"")+'">'+esc(x.trace||"—")+'</td><td>'+esc(x.plant||"—")+'</td><td>'+esc(x.binder_type||"—")+'</td>';
  if(approved){
    html+='<td>'+dateBR(x.approval_date)+'</td><td>'+dateBR(x.expiration_date)+'<small>'+qgDays(x)+'</small></td><td>'+qgDoc(x)+'</td>';
  }else{
    html+='<td>'+qgTraceBadge(x.status)+'</td><td>'+dateBR(x.approval_date)+'</td><td>'+dateBR(x.expiration_date)+'</td>';
  }
  return html+'</tr>';
}
function qgField(label,value){
  return '<div class="detail-field"><b>'+esc(label)+'</b><span>'+esc(value||"—")+'</span></div>';
}
window.openGeneralQualityDetail=function(key){
  var x=qgTraceMap.get(String(key)); if(!x)return;
  var doc=/^https?:\/\//i.test(String(x.link||""))?'<a class="primary qg-detail-doc" target="_blank" rel="noopener" href="'+esc(x.link)+'">Abrir documento ↗</a>':"";
  var fields="";
  fields+=qgField("Traço",x.trace)+qgField("Contratada",x.contractor)+qgField("Tipo / classificação",[x.trace_type,x.classification].filter(Boolean).join(" • "));
  fields+=qgField("Contrato",x.contract)+qgField("Obra",x.work)+qgField("Aplicação",x.application)+qgField("Usina",x.plant)+qgField("Cidade",x.city);
  fields+=qgField("Origem do agregado",x.aggregate_origin)+qgField("Fornecedor do ligante",x.binder_supplier)+qgField("Ligante",x.binder_type);
  fields+=qgField("Código de aprovação",x.approval_code)+qgField("Responsável",x.approver)+qgField("Data de aprovação",dateBR(x.approval_date))+qgField("Vencimento",dateBR(x.expiration_date));
  if(x.expired&&x.source_status)fields+=qgField("Status original da planilha",x.source_status);
  fields+=qgField("Selo",x.seal);
  $("#modal-content").innerHTML='<div class="detail-head"><div><span class="eyebrow">QUALIDADE GERAL • '+esc(x.category||x.sheet||"")+'</span><h2>'+esc(x.code||x.trace||"Traço")+'</h2><div class="subtitle">'+qgTraceBadge(x.status)+' • linha '+esc(x.source_row)+' da aba '+esc(x.sheet)+'</div></div>'+doc+'</div><div class="detail-grid qg-detail-grid">'+fields+'</div>'+(x.observations?'<div class="panel qg-detail-observation"><b>Observações</b><p>'+esc(x.observations)+'</p></div>':"");
  $("#modal").classList.add("open"); $("#modal").setAttribute("aria-hidden","false");
};
function qgOverviewQuery(){
  var q=new URLSearchParams();
  q.set("contractor",$("#qg-overview-contractor")?$("#qg-overview-contractor").value:"ALL");
  q.set("trace_type",$("#qg-overview-type")?$("#qg-overview-type").value:"ALL");
  if($("#qg-overview-search")&&$("#qg-overview-search").value)q.set("search",$("#qg-overview-search").value);
  return q;
}
function qgRenderTraceKPIs(s){
  $("#qg-kpis").innerHTML=[
    metric("Total de traços",num(s.total,0),"Registros válidos nas abas operacionais"),
    metric("Aprovados",num(s.approved,0),"Somente status aprovado e vigente"),
    metric("Restritos",num(s.restricted,0),"Restrito / com ressalvas"),
    metric("Reprovados / NC",num(s.rejected,0),"Reprovado + Não conforme"),
    metric("Em análise",num(s.analysis,0),"Em análise, solicitado ou aguardando"),
    metric("Vencem em 30 dias",num(s.expiring_30d,0),num(s.expired||0,0)+" vencido(s) pela data de validade")
  ].join("");
}
function qgRenderContractorStatus(rows){
  var max=Math.max.apply(null,[1].concat((rows||[]).map(function(x){return Number(x.total||0);})));
  $("#qg-contractor-status").innerHTML=(rows||[]).map(function(x){
    var total=Number(x.total||0)||1;
    var parts=[["approved",x.approved],["restricted",x.restricted],["analysis",x.analysis],["rejected",x.rejected],["expired",x.expired],["cancelled",x.cancelled]];
    var segs=parts.filter(function(p){return Number(p[1]||0)>0;}).map(function(p){return '<i class="qg-seg qg-seg-'+p[0]+'" style="width:'+(Number(p[1]||0)/total*100)+'%"></i>';}).join("");
    return '<button class="qg-contractor-row" type="button" onclick="openQGApprovedContractor(\''+esc(x.contractor)+'\')"><span class="qg-contractor-name"><b>'+esc(x.contractor)+'</b><small>'+num(x.total,0)+' traços • '+num(x.approved,0)+' aprovados</small></span><span class="qg-stack" style="--qg-row-width:'+Math.max(20,Number(x.total||0)/max*100)+'%">'+segs+'</span><span class="qg-contract-pct">'+num(x.approved_pct,1)+'%</span></button>';
  }).join("")||'<div class="empty">Sem dados de contratadas.</div>';
}
function qgRenderTypes(rows){
  var max=Math.max.apply(null,[1].concat((rows||[]).map(function(x){return Number(x.count||0);})));
  $("#qg-type-bars").innerHTML=(rows||[]).map(function(x){return '<div class="qg-type-row"><span>'+esc(x.trace_type)+'</span><i><b style="width:'+(Number(x.count||0)/max*100)+'%"></b></i><strong>'+num(x.count,0)+'</strong></div>';}).join("")||'<div class="empty">Sem dados.</div>';
}
function qgRenderApprovedCards(rows){
  var list=(rows||[]).filter(function(x){return Number(x.approved||0)>0;}).sort(function(a,b){return Number(b.approved||0)-Number(a.approved||0);});
  $("#qg-approved-contractors").innerHTML=list.map(function(x){return '<button type="button" class="qg-approved-card" onclick="openQGApprovedContractor(\''+esc(x.contractor)+'\')"><span>'+esc(x.contractor)+'</span><b>'+num(x.approved,0)+'</b><small>traços aprovados • ver quais →</small></button>';}).join("")||'<div class="empty">Nenhum traço aprovado neste filtro.</div>';
}
function qgRenderExpiring(items){
  qgRememberTraces(items);
  $("#qg-expiring-body").innerHTML=(items||[]).map(function(x){return '<tr class="qg-click-row" onclick="openGeneralQualityDetail(\''+esc(qgTraceKey(x))+'\')"><td><b>'+esc(x.code||"—")+'</b></td><td>'+esc(x.contractor||"—")+'</td><td>'+esc(x.category||x.sheet||"—")+'</td><td class="qg-trace-cell">'+esc(x.trace||"—")+'</td><td>'+dateBR(x.expiration_date)+'</td><td>'+qgDays(x)+'</td></tr>';}).join("")||'<tr><td colspan="6">Nenhum vencimento nos próximos 30 dias.</td></tr>';
}
async function loadGeneralQualityOverview(){
  try{
    var d=await api("/api/general-quality/overview?"+qgOverviewQuery());
    qgFillTraceFilters(d.filters||{}); qgRememberTraces(d.items||[]);
    if($("#qg-admin-source"))$("#qg-admin-source").classList.toggle("auth-hidden",!isAdmin());
    $("#qg-source-state").textContent=qgSourceLabel(d.source,"Inventário");
    if(isAdmin()){
      if(d.source&&d.source.path)$("#qg-source-path").value=d.source.path;
      $("#qg-source-detail").textContent=d.source&&d.source.exists?(d.source.file_name+" • "+qgBytes(d.source.size)+" • "+num(d.summary&&d.summary.total||0,0)+" traços lidos"):"Nenhuma fonte disponível. Envie a planilha ou configure o caminho sincronizado.";
    }
    qgRenderTraceKPIs(d.summary||{}); qgRenderContractorStatus(d.summary&&d.summary.by_contractor||[]);
    qgRenderTypes(d.summary&&d.summary.by_type||[]); qgRenderApprovedCards(d.summary&&d.summary.by_contractor||[]);
    qgRenderExpiring(d.summary&&d.summary.expiring||[]);
  }catch(e){toast(e.message,true);}
}
window.openQGApprovedContractor=function(contractor){qgApprovedContractorPending=contractor||"ALL";openPage("quality-approved");};
window.selectQGApprovedContractor=function(contractor){if($("#qga-contractor"))$("#qga-contractor").value=contractor;loadGeneralQualityApproved();};
function qgApprovedQuery(){
  var q=new URLSearchParams();
  q.set("contractor",qgApprovedContractorPending||($("#qga-contractor")?$("#qga-contractor").value:"ALL"));
  q.set("trace_type",$("#qga-type")?$("#qga-type").value:"ALL");
  q.set("plant",$("#qga-plant")?$("#qga-plant").value:"ALL");
  q.set("binder",$("#qga-binder")?$("#qga-binder").value:"ALL");
  if($("#qga-search")&&$("#qga-search").value)q.set("search",$("#qga-search").value);
  qgApprovedContractorPending="";
  return q;
}
async function loadGeneralQualityApproved(){
  try{
    var q=qgApprovedQuery(), requested=q.get("contractor"), d=await api("/api/general-quality/approved?"+q);
    qgFillTraceFilters(d.filters||{}); qgRememberTraces(d.items||[]);
    if($("#qga-contractor")&&Array.from($("#qga-contractor").options).some(function(o){return o.value===requested;}))$("#qga-contractor").value=requested;
    $("#qga-title").textContent=requested==="ALL"?"Traços aprovados":"Traços aprovados • "+requested;
    $("#qga-hint").textContent=num(d.total_filtered,0)+" registro(s) vigente(s).";
    $("#qga-contractor-chips").innerHTML='<button class="qg-contractor-chip '+(requested==="ALL"?"active":"")+'" onclick="selectQGApprovedContractor(\'ALL\')">Todas</button>'+(d.approved_contractors||[]).map(function(x){return '<button class="qg-contractor-chip '+(requested===x.contractor?"active":"")+'" onclick="selectQGApprovedContractor(\''+esc(x.contractor)+'\')">'+esc(x.contractor)+' <span>'+num(x.count,0)+'</span></button>';}).join("");
    $("#qga-body").innerHTML=(d.items||[]).map(function(x){return qgTraceRow(x,true);}).join("")||'<tr><td colspan="9">Nenhum traço aprovado encontrado.</td></tr>';
  }catch(e){toast(e.message,true);}
}
function qgTracesQuery(){
  var q=new URLSearchParams();
  q.set("contractor",$("#qgt-contractor")?$("#qgt-contractor").value:"ALL");
  q.set("trace_type",$("#qgt-type")?$("#qgt-type").value:"ALL");
  q.set("status",$("#qgt-status")?$("#qgt-status").value:"ALL");
  q.set("plant",$("#qgt-plant")?$("#qgt-plant").value:"ALL");
  q.set("binder",$("#qgt-binder")?$("#qgt-binder").value:"ALL");
  if($("#qgt-search")&&$("#qgt-search").value)q.set("search",$("#qgt-search").value);
  return q;
}
async function loadGeneralQualityTraces(){
  try{
    var d=await api("/api/general-quality/traces?"+qgTracesQuery()), s=d.summary||{};
    qgFillTraceFilters(d.filters||{}); qgRememberTraces(d.items||[]);
    $("#qgt-summary").innerHTML='<span class="summary-chip"><b>'+num(d.total_filtered,0)+'</b> traços</span><span class="summary-chip"><b>'+num(s.approved,0)+'</b> aprovados</span><span class="summary-chip"><b>'+num(s.restricted,0)+'</b> restritos</span><span class="summary-chip"><b>'+num(s.rejected,0)+'</b> reprovados/NC</span><span class="summary-chip"><b>'+num(s.expired,0)+'</b> vencidos</span>';
    $("#qgt-body").innerHTML=(d.items||[]).map(function(x){return qgTraceRow(x,false);}).join("")||'<tr><td colspan="9">Nenhum traço encontrado.</td></tr>';
  }catch(e){toast(e.message,true);}
}
async function saveGeneralQualitySource(){
  if(!isAdmin())return;
  try{await api("/api/general-quality/source",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:$("#qg-source-path").value||""})});toast("Fonte da Qualidade Geral atualizada.");loadGeneralQualityOverview();}catch(e){toast(e.message,true);}
}
async function uploadGeneralQualitySource(){
  if(!isAdmin())return;
  var file=$("#qg-source-file")&&$("#qg-source-file").files[0]; if(!file)return toast("Selecione a planilha do inventário.",true);
  var fd=new FormData();fd.append("file",file);
  try{var d=await api("/api/general-quality/source/upload",{method:"POST",body:fd});toast(num(d.summary&&d.summary.total||0,0)+" traços importados.");$("#qg-source-file").value="";loadGeneralQualityOverview();}catch(e){toast(e.message,true);}
}
function clearQGApproved(){["qga-contractor","qga-type","qga-plant","qga-binder"].forEach(function(id){if($("#"+id))$("#"+id).value="ALL";});if($("#qga-search"))$("#qga-search").value="";loadGeneralQualityApproved();}
function clearQGTraces(){["qgt-contractor","qgt-type","qgt-status","qgt-plant","qgt-binder"].forEach(function(id){if($("#"+id))$("#"+id).value="ALL";});if($("#qgt-search"))$("#qgt-search").value="";loadGeneralQualityTraces();}

/* RNCs */
function qgNCClass(x){var g=String(x&&x.status_group||"OTHER");return g==="OPEN"?"open":g==="TREATMENT"?"treatment":g==="CLOSED"?"closed":g==="CANCELLED"?"cancelled":"other";}
function qgNCBadge(x){return '<span class="qgnc-status qgnc-status-'+qgNCClass(x)+'">'+esc(x&&x.final_status||"—")+'</span>';}
function qgNCDeadline(x){var d=dateBR(x&&x.response_due);return Number(x&&x.days_overdue||0)>0?d+'<small class="qgnc-overdue">'+num(x.days_overdue,0)+'d vencido</small>':d;}
function qgFillNCFilters(f){
  [
    ["qgnco-contractor",f.contractors,"Todas as contratadas"],["qgnco-status",f.statuses,"Todos os status"],["qgnco-discipline",f.disciplines,"Todas as disciplinas"],
    ["qgncl-contractor",f.contractors,"Todas as contratadas"],["qgncl-status",f.statuses,"Todos os status"],["qgncl-subject",f.subjects,"Todos os assuntos"],
    ["qgncl-discipline",f.disciplines,"Todas as disciplinas"],["qgncl-classification",f.classifications,"Todas as classificações"],["qgncl-retention",f.retention_statuses,"Retido / não retido"]
  ].forEach(function(a){qgFillSelect(a[0],a[1]||[],a[2]);});
}
function qgNCKPIs(s){
  $("#qgnc-kpis").innerHTML=[
    metric("Total de RNCs",num(s.total,0),"Registros do tipo RNC"),metric("Abertas",num(s.open,0),"Aguardando tratamento"),
    metric("Em tratamento",num(s.treatment,0),"Ações em andamento"),metric("Encerradas",num(s.closed,0),"RNCs já encerradas"),
    metric("Canceladas",num(s.cancelled,0),"Registros cancelados"),metric("Prazo vencido",num(s.overdue,0),"Abertas/em tratamento fora do prazo")
  ].join("");
  $("#qgnc-proposed-retention").textContent=brl(s.proposed_retention||0);
  $("#qgnc-real-retained").textContent=brl(s.real_retained||0);
  $("#qgnc-retained-hint").textContent=num(s.retained_count||0,0)+" ocorrência(s) com retenção registrada.";
}
function qgNCRenderContractors(rows){
  var max=Math.max.apply(null,[1].concat((rows||[]).map(function(x){return Number(x.total||0);})));
  $("#qgnc-contractor-status").innerHTML=(rows||[]).map(function(x){
    var total=Number(x.total||0)||1, parts=[["open",x.open],["treatment",x.treatment],["closed",x.closed],["cancelled",x.cancelled],["other",x.other]];
    var segs=parts.filter(function(p){return Number(p[1]||0)>0;}).map(function(p){return '<i class="qgnc-seg qgnc-seg-'+p[0]+'" style="width:'+(Number(p[1]||0)/total*100)+'%"></i>';}).join("");
    return '<button class="qg-contractor-row" type="button" onclick="openQGNCContractor(\''+esc(x.contractor)+'\')"><span class="qg-contractor-name"><b>'+esc(x.contractor)+'</b><small>'+num(x.total,0)+' RNCs • '+num(x.closed,0)+' encerradas</small></span><span class="qg-stack" style="--qg-row-width:'+Math.max(20,Number(x.total||0)/max*100)+'%">'+segs+'</span><span class="qg-contract-pct">'+num(x.closed_pct,1)+'%</span></button>';
  }).join("")||'<div class="empty">Sem RNCs para o filtro.</div>';
}
function qgNCRenderSubjects(rows){
  var max=Math.max.apply(null,[1].concat((rows||[]).map(function(x){return Number(x.count||0);})));
  $("#qgnc-subject-bars").innerHTML=(rows||[]).map(function(x){return '<div class="qg-type-row qgnc-subject-row"><span title="'+esc(x.subject)+'">'+esc(x.subject)+'</span><i><b style="width:'+(Number(x.count||0)/max*100)+'%"></b></i><strong>'+num(x.count,0)+'</strong></div>';}).join("")||'<div class="empty">Sem assuntos.</div>';
}
function qgNCOpenRows(items){
  qgRememberNC(items);
  $("#qgnc-open-body").innerHTML=(items||[]).map(function(x){return '<tr class="qg-click-row" onclick="openGeneralQualityNCDetail(\''+esc(qgNCKey(x))+'\')"><td><b>'+esc(x.emission_no||"—")+'</b></td><td>'+esc(x.contractor||"—")+'</td><td class="qg-trace-cell">'+esc(x.subject||"—")+'</td><td>'+qgNCBadge(x)+'</td><td>'+dateBR(x.emission_date)+'</td><td>'+qgNCDeadline(x)+'</td><td>'+brl(x.real_retained||0)+'</td></tr>';}).join("")||'<tr><td colspan="7">Nenhuma RNC aberta ou em tratamento.</td></tr>';
}
function qgNCRow(x){
  return '<tr class="qg-click-row" onclick="openGeneralQualityNCDetail(\''+esc(qgNCKey(x))+'\')"><td><b>'+esc(x.emission_no||"—")+'</b><small>'+esc(x.contract||"")+'</small></td><td>'+esc(x.contractor||"—")+'</td><td class="qg-trace-cell">'+esc(x.subject||"—")+'<small>'+esc(x.segment||"")+'</small></td><td>'+qgNCBadge(x)+'</td><td>'+esc(x.discipline||"—")+'</td><td>'+dateBR(x.emission_date)+'</td><td>'+qgNCDeadline(x)+'</td><td>'+brl(x.proposed_retention||0)+'</td><td>'+brl(x.real_retained||0)+'</td></tr>';
}
window.openGeneralQualityNCDetail=function(key){
  var x=qgNCMap.get(String(key)); if(!x)return;
  var fields="";
  fields+=qgField("Contratada",x.contractor)+qgField("Assunto",x.subject)+qgField("Disciplina",x.discipline)+qgField("Classificação",x.classification);
  fields+=qgField("Contrato",x.contract)+qgField("Lote / trecho",[x.lot,x.segment].filter(Boolean).join(" • "))+qgField("Emissão",dateBR(x.emission_date))+qgField("Prazo de resposta",dateBR(x.response_due));
  fields+=qgField("Situação",x.final_status)+qgField("Disposição final",x.final_disposition)+qgField("Implementação",x.implementation_status)+qgField("Eficácia",x.effectiveness);
  fields+=qgField("Valor a reter",brl(x.proposed_retention||0))+qgField("Valor real retido",brl(x.real_retained||0))+qgField("Retenção",x.retention_status)+qgField("Medição retida",x.retained_measurement);
  fields+=qgField("Solicitante",x.requester)+qgField("Aberta por",x.opened_by)+qgField("Gestor da obra",x.work_manager)+qgField("Resposta da contratada",dateBR(x.response_date));
  fields+=qgField("Validação supervisão",x.supervision_validation_status)+qgField("Validação CCR",x.ccr_validation_status)+qgField("Encerramento",dateBR(x.close_date))+qgField("Responsável encerramento",x.close_owner);
  var links=[["Fulcrum",x.fulcrum_link],["Foto da anomalia",x.anomaly_photo_link],["Foto da evidência",x.evidence_photo_link]].filter(function(a){return a[1];}).map(function(a){return '<a class="ghost compact qgnc-link" href="'+esc(a[1])+'" target="_blank" rel="noopener">'+esc(a[0])+' ↗</a>';}).join("");
  var extra=(x.description?'<div class="panel qg-detail-observation"><b>Descrição detalhada</b><p>'+esc(x.description)+'</p></div>':"")+(x.action_proposal?'<div class="panel qg-detail-observation"><b>Proposta de ação da contratada</b><p>'+esc(x.action_proposal)+'</p></div>':"")+(x.non_retention_reason?'<div class="panel qg-detail-observation"><b>Justificativa da não retenção</b><p>'+esc(x.non_retention_reason)+'</p></div>':"");
  $("#modal-content").innerHTML='<div class="detail-head"><div><span class="eyebrow">NÃO CONFORMIDADE</span><h2>'+esc(x.emission_no||"RNC")+'</h2><div class="subtitle">'+qgNCBadge(x)+' • linha '+esc(x.source_row)+' da aba NC</div></div><div class="detail-actions">'+links+'</div></div><div class="detail-grid qg-detail-grid">'+fields+'</div>'+extra;
  $("#modal").classList.add("open");$("#modal").setAttribute("aria-hidden","false");
};
function qgNCOverviewQuery(){
  var q=new URLSearchParams();q.set("contractor",$("#qgnco-contractor")?$("#qgnco-contractor").value:"ALL");q.set("status",$("#qgnco-status")?$("#qgnco-status").value:"ALL");q.set("discipline",$("#qgnco-discipline")?$("#qgnco-discipline").value:"ALL");if($("#qgnco-search")&&$("#qgnco-search").value)q.set("search",$("#qgnco-search").value);return q;
}
async function loadGeneralQualityNCOverview(){
  try{
    var d=await api("/api/general-quality/nonconformities/overview?"+qgNCOverviewQuery());qgFillNCFilters(d.filters||{});qgRememberNC(d.items||[]);
    if($("#qgnc-admin-source"))$("#qgnc-admin-source").classList.toggle("auth-hidden",!isAdmin());
    $("#qgnc-source-state").textContent=qgSourceLabel(d.source,"Controle NC");
    if(isAdmin()){if(d.source&&d.source.path)$("#qgnc-source-path").value=d.source.path;$("#qgnc-source-detail").textContent=d.source&&d.source.exists?(d.source.file_name+" • "+qgBytes(d.source.size)+" • "+num(d.summary&&d.summary.total||0,0)+" RNCs lidas"):"Nenhuma fonte configurada. Informe o caminho local da planilha de NCs.";}
    qgNCKPIs(d.summary||{});qgNCRenderContractors(d.summary&&d.summary.by_contractor||[]);qgNCRenderSubjects(d.summary&&d.summary.by_subject||[]);qgNCOpenRows(d.summary&&d.summary.recent_open||[]);
  }catch(e){toast(e.message,true);}
}
window.openQGNCContractor=function(contractor){if($("#qgncl-contractor"))$("#qgncl-contractor").dataset.pendingValue=contractor||"ALL";openPage("quality-nc-list");};
function qgNCListQuery(){
  var q=new URLSearchParams();
  [["contractor","qgncl-contractor"],["status","qgncl-status"],["subject","qgncl-subject"],["discipline","qgncl-discipline"],["classification","qgncl-classification"],["retention_status","qgncl-retention"]].forEach(function(a){q.set(a[0],$("#"+a[1])?$("#"+a[1]).value:"ALL");});
  if($("#qgncl-search")&&$("#qgncl-search").value)q.set("search",$("#qgncl-search").value);return q;
}
async function loadGeneralQualityNCList(){
  try{
    var desired=$("#qgncl-contractor")&&$("#qgncl-contractor").dataset.pendingValue||"", q=qgNCListQuery();if(desired)q.set("contractor",desired);
    var d=await api("/api/general-quality/nonconformities?"+q);qgFillNCFilters(d.filters||{});qgRememberNC(d.items||[]);
    if(desired&&$("#qgncl-contractor")&&Array.from($("#qgncl-contractor").options).some(function(o){return o.value===desired;}))$("#qgncl-contractor").value=desired;
    if($("#qgncl-contractor"))delete $("#qgncl-contractor").dataset.pendingValue;
    var s=d.summary||{};
    $("#qgncl-summary").innerHTML='<span class="summary-chip"><b>'+num(d.total_filtered,0)+'</b> RNCs</span><span class="summary-chip"><b>'+num(s.open,0)+'</b> abertas</span><span class="summary-chip"><b>'+num(s.treatment,0)+'</b> em tratamento</span><span class="summary-chip"><b>'+num(s.closed,0)+'</b> encerradas</span><span class="summary-chip"><b>'+num(s.overdue,0)+'</b> com prazo vencido</span><span class="summary-chip"><b>'+brl(s.real_retained||0)+'</b> retido</span>';
    $("#qgncl-body").innerHTML=(d.items||[]).map(qgNCRow).join("")||'<tr><td colspan="9">Nenhuma RNC encontrada.</td></tr>';
  }catch(e){toast(e.message,true);}
}
async function saveGeneralQualityNCSource(){if(!isAdmin())return;try{await api("/api/general-quality/nonconformities/source",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:$("#qgnc-source-path").value||""})});toast("Fonte das Não Conformidades atualizada.");loadGeneralQualityNCOverview();}catch(e){toast(e.message,true);}}
async function uploadGeneralQualityNCSource(){if(!isAdmin())return;var file=$("#qgnc-source-file")&&$("#qgnc-source-file").files[0];if(!file)return toast("Selecione a planilha de Não Conformidades.",true);var fd=new FormData();fd.append("file",file);try{var d=await api("/api/general-quality/nonconformities/source/upload",{method:"POST",body:fd});toast(num(d.summary&&d.summary.total||0,0)+" RNCs importadas.");$("#qgnc-source-file").value="";loadGeneralQualityNCOverview();}catch(e){toast(e.message,true);}}
function clearQGNCList(){["qgncl-contractor","qgncl-status","qgncl-subject","qgncl-discipline","qgncl-classification","qgncl-retention"].forEach(function(id){if($("#"+id))$("#"+id).value="ALL";});if($("#qgncl-search"))$("#qgncl-search").value="";loadGeneralQualityNCList();}

/* bindings */
if($("#qg-overview-refresh"))$("#qg-overview-refresh").onclick=loadGeneralQualityOverview;
if($("#qg-open-approved"))$("#qg-open-approved").onclick=function(){openQGApprovedContractor("ALL");};
if($("#qg-source-save"))$("#qg-source-save").onclick=saveGeneralQualitySource;
if($("#qg-source-upload"))$("#qg-source-upload").onclick=uploadGeneralQualitySource;
if($("#qga-refresh"))$("#qga-refresh").onclick=loadGeneralQualityApproved;
if($("#qga-clear"))$("#qga-clear").onclick=clearQGApproved;
if($("#qgt-refresh"))$("#qgt-refresh").onclick=loadGeneralQualityTraces;
if($("#qgt-clear"))$("#qgt-clear").onclick=clearQGTraces;
["qg-overview-search","qga-search","qgt-search"].forEach(function(id){var el=$("#"+id);if(el)el.addEventListener("keydown",function(e){if(e.key==="Enter"){if(id==="qg-overview-search")loadGeneralQualityOverview();else if(id==="qga-search")loadGeneralQualityApproved();else loadGeneralQualityTraces();}});});
if($("#qgnco-refresh"))$("#qgnco-refresh").onclick=loadGeneralQualityNCOverview;
if($("#qgnc-open-list"))$("#qgnc-open-list").onclick=function(){openPage("quality-nc-list");};
if($("#qgnc-source-save"))$("#qgnc-source-save").onclick=saveGeneralQualityNCSource;
if($("#qgnc-source-upload"))$("#qgnc-source-upload").onclick=uploadGeneralQualityNCSource;
if($("#qgncl-refresh"))$("#qgncl-refresh").onclick=loadGeneralQualityNCList;
if($("#qgncl-clear"))$("#qgncl-clear").onclick=clearQGNCList;
["qgnco-search","qgncl-search"].forEach(function(id){var el=$("#"+id);if(el)el.addEventListener("keydown",function(e){if(e.key==="Enter"){if(id==="qgnco-search")loadGeneralQualityNCOverview();else loadGeneralQualityNCList();}});});
