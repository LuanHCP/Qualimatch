/* Central de registros - consulta paginada diretamente no PostgreSQL. */
window.App = window.App || {};
(function(App){
  "use strict";
  var qs=App.util.qs,qsa=App.util.qsa,esc=App.util.esc,byId=App.util.byId,fmtMoney=App.util.fmtMoney,fmtDate=App.util.fmtDate;

  function localLabel(n){
    var parts=[];if(n.rodovia)parts.push(n.rodovia);if(n.trecho)parts.push(n.trecho);
    var km='';if(n.kmInicial!=null&&n.kmInicial!=='')km='Km '+n.kmInicial+(n.kmFinal!=null&&n.kmFinal!==''&&String(n.kmFinal)!==String(n.kmInicial)?' a '+n.kmFinal:'');
    if(km)parts.push(km);return parts.join(' · ')||'Local não informado';
  }
  function typeLabel(n){return n.tipoCore==='AP'?'Ação preventiva':n.tipoCore==='AC'?'Ação corretiva':'Não conformidade';}
  function tableHtml(list,opts){
    opts=opts||{};
    if(!list.length)return App.EmptyState({icon:'list',title:opts.emptyTitle||'Nenhum registro encontrado',text:opts.emptyText||'Revise os filtros ou a busca informada.',actionHtml:opts.showEmptyAction?App.Button({label:'Limpar filtros',variant:'ghost',id:'empty-clear-filters'}):''});
    return '<div class="record-table-shell"><div class="record-table-scroll"><table class="record-table"><thead><tr><th>Registro</th><th>Classificação</th><th>Contrato e responsável</th><th>Localização</th><th>Situação</th><th>Prazo</th><th class="money-col">Retenção</th><th aria-label="Abrir"></th></tr></thead><tbody>'+list.map(function(n){
      var contractor=byId(App.state.contratadas,n.contratadaId),contract=byId(App.state.contratos,n.contratoId),value=n.valorRetencaoEfetivo!=null?n.valorRetencaoEfetivo:n.valorRetencaoProposto;
      return '<tr class="record-row row-click" data-id="'+esc(n.id)+'" tabindex="0">'+
        '<td data-label="Registro"><div class="record-code">'+esc(n.codigoFormatado||'Sem código')+'</div><div class="record-meta"><span>'+esc(typeLabel(n))+'</span><span>'+esc(fmtDate(n.dataEmissao))+'</span></div></td>'+
        '<td data-label="Classificação"><div class="record-primary">'+esc(n.categoria||'Sem categoria')+'</div><div class="record-secondary">'+esc([n.item,n.subitem,n.classificacao].filter(Boolean).join(' · ')||'Sem detalhamento')+'</div></td>'+
        '<td data-label="Contrato"><div class="record-primary">'+esc(contractor?contractor.razaoSocial:'Contratada não vinculada')+'</div><div class="record-secondary">'+esc(contract?'Contrato '+contract.numero:'Contrato não informado')+'</div></td>'+
        '<td data-label="Localização"><div class="record-primary">'+esc(localLabel(n))+'</div><div class="record-secondary">'+esc([n.pistaSentido,n.faixa?('Faixa '+n.faixa):''].filter(Boolean).join(' · ')||'Pista/faixa não informada')+'</div></td>'+
        '<td data-label="Situação">'+App.StatusBadge(n.statusAtual)+'</td><td data-label="Prazo">'+App.DeadlineBadge(n)+'</td>'+
        '<td data-label="Retenção" class="money-col"><strong>'+fmtMoney(value)+'</strong><div class="record-secondary">'+(n.valorRetencaoEfetivo!=null?'Efetiva':'Proposta')+'</div></td>'+
        '<td class="record-open">'+App.icon('chevronRight','sm')+'</td></tr>';
    }).join('')+'</tbody></table></div></div>';
  }
  function bindTableRows(container){qsa('tr.row-click',container).forEach(function(tr){var open=function(){App.router.go('#/ncs/'+tr.getAttribute('data-id'));};tr.onclick=open;tr.onkeydown=function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}};});}

  async function render(mount){
    var sede=App.sedeAtual(),contratos=App.perm.contratosVisiveis(),podeEmitir=App.perm.podeEmitir(),page=1,pageSize=15,situacao='',timer=null,lastRequest=0;
    mount.innerHTML=App.PageHeader({title:'Central de registros',sub:'Consulta operacional de NC, RNC e AC/AP da '+sede.sigla+'.',actionsHtml:podeEmitir?App.Button({label:'Novo registro',icon:'plus',variant:'primary',id:'btn-novo-registro'}):''})+
      '<div class="page-body records-page"><div id="record-summary" class="record-summary-grid"><div class="record-summary-skeleton"></div><div class="record-summary-skeleton"></div><div class="record-summary-skeleton"></div><div class="record-summary-skeleton"></div><div class="record-summary-skeleton"></div></div>'+
      '<div class="record-workspace"><div class="record-viewbar"><div class="record-view-tabs"><button class="active" data-view="">Todos</button><button data-view="abertas">Em aberto</button><button data-view="vencidas">Vencidas</button><button data-view="breve">Próximas do prazo</button><button data-view="encerradas">Encerradas</button></div><div class="record-db-state">'+App.icon('building','sm')+' PostgreSQL · dados atualizados</div></div>'+
      '<div class="registros-toolbar"><div class="search-input record-search">'+App.icon('search','sm')+'<input type="search" id="reg-search" placeholder="Buscar código, categoria, rodovia, descrição ou contratada"></div>'+App.FilterToggle('reg-filter-toggle','Filtros')+'<select id="reg-sort" aria-label="Ordenação"><option value="emissao">Mais recentes</option><option value="prazo">Prazo mais próximo</option><option value="codigo">Código</option><option value="retencao">Maior retenção</option></select></div><div id="reg-filter-panel" class="hidden"></div><div id="reg-chips" class="chip-row"></div><div class="record-results-head"><div><strong id="reg-result-count">Carregando registros...</strong><span id="reg-result-context"></span></div><span>Selecione uma linha para abrir o registro completo</span></div><div id="reg-table"><div class="record-loading">Consultando o banco de dados...</div></div><div id="reg-pagination"></div></div></div>';
    if(podeEmitir)qs('#btn-novo-registro').onclick=function(){App.router.go('#/ncs/novo');};
    var fields=App.selectHtml('rf-contrato','Contrato',[['','Todos']].concat(contratos.map(function(c){return[c.id,c.numero];})))+App.selectHtml('rf-status','Status',[['','Todos']].concat(Object.keys(App.STATUS).map(function(k){return[k,App.STATUS[k].label];})))+App.selectHtml('rf-classificacao','Classificação',[['','Todas'],['leve','Leve'],['media','Média'],['grave','Grave']])+App.inputHtml('rf-dataDe','Emissão inicial','date')+App.inputHtml('rf-dataAte','Emissão final','date');
    qs('#reg-filter-panel').outerHTML=App.FilterPanel(fields,{id:'reg-filter-panel'});var panel=qs('#reg-filter-panel');panel.classList.add('hidden');qs('#reg-filter-toggle').onclick=function(){panel.classList.toggle('hidden');};

    function filters(){return{contratoId:qs('#rf-contrato').value,status:qs('#rf-status').value,classificacao:qs('#rf-classificacao').value,dataDe:qs('#rf-dataDe').value,dataAte:qs('#rf-dataAte').value};}
    function label(k,v){if(k==='contratoId'){var c=byId(contratos,v);return'Contrato: '+(c?c.numero:v);}if(k==='status')return'Status: '+App.STATUS[v].label;if(k==='classificacao')return'Classificação: '+v;if(k==='dataDe')return'De: '+fmtDate(v);if(k==='dataAte')return'Até: '+fmtDate(v);return v;}
    function renderChips(){var f=filters(),active=Object.keys(f).filter(function(k){return f[k];});var badge=qs('#reg-filter-toggle-count');badge.textContent=active.length;badge.classList.toggle('hidden',!active.length);qs('#reg-chips').innerHTML=active.map(function(k){return'<span class="chip">'+esc(label(k,f[k]))+'<button data-clear="'+k+'">'+App.icon('x','sm')+'</button></span>';}).join('');qsa('#reg-chips [data-clear]').forEach(function(b){b.onclick=function(){qs('#rf-'+b.getAttribute('data-clear')).value='';page=1;load();};});}
    function query(){var params=new URLSearchParams({sedeId:App.state.sedeId,page:String(page),pageSize:String(pageSize),sort:qs('#reg-sort').value}),f=filters(),term=qs('#reg-search').value.trim();Object.keys(f).forEach(function(k){if(f[k])params.set(k,f[k]);});if(term)params.set('busca',term);if(situacao)params.set('situacao',situacao);return params;}
    async function load(){
      var requestId=++lastRequest;renderChips();qs('#reg-table').innerHTML='<div class="record-loading">'+App.icon('clock')+' Consultando o PostgreSQL...</div>';
      try{var data=await App.api.get('/api/ncs?'+query().toString());if(requestId!==lastRequest)return;qs('#reg-result-count').textContent=data.total+' registro'+(data.total===1?'':'s');qs('#reg-result-context').textContent=situacao?' na visão selecionada':'';qs('#reg-table').innerHTML=tableHtml(data.items,{showEmptyAction:true});bindTableRows(qs('#reg-table'));var empty=qs('#empty-clear-filters');if(empty)empty.onclick=clearAll;qs('#reg-pagination').innerHTML=data.total?App.Pagination(data.total,page,pageSize):'';qsa('#reg-pagination [data-page]').forEach(function(b){b.onclick=function(){page=parseInt(b.getAttribute('data-page'),10);load();window.scrollTo({top:0,behavior:'smooth'});};});}catch(e){if(requestId!==lastRequest)return;qs('#reg-table').innerHTML='<div class="record-error">'+App.icon('alertTriangle')+'<div><strong>Não foi possível consultar os registros</strong><span>'+esc(e.message)+'</span></div></div>';}
    }
    function clearAll(){qsa('#reg-filter-panel select,#reg-filter-panel input').forEach(function(el){el.value='';});qs('#reg-search').value='';situacao='';qsa('.record-view-tabs button').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-view')==='');});page=1;load();}
    async function loadSummary(){try{var s=await App.api.get('/api/ncs/resumo?sedeId='+encodeURIComponent(App.state.sedeId));var cards=[['Total de registros',s.total,'list','default'],['Em aberto',s.abertas,'clock','primary'],['Vencidas',s.vencidas,'alertTriangle','bad'],['Vencem em 3 dias',s.vencem_breve,'calendar','accent'],['Retenção monitorada',fmtMoney(s.retencao),'coins','good']];qs('#record-summary').innerHTML=cards.map(function(c){return'<div class="record-summary-card tone-'+c[3]+'"><span class="record-summary-icon">'+App.icon(c[2])+'</span><div><span>'+esc(c[0])+'</span><strong>'+esc(c[1])+'</strong></div></div>';}).join('');}catch(e){qs('#record-summary').innerHTML='';}}
    qsa('.record-view-tabs button').forEach(function(b){b.onclick=function(){situacao=b.getAttribute('data-view');page=1;qsa('.record-view-tabs button').forEach(function(x){x.classList.toggle('active',x===b);});load();};});
    qsa('#reg-filter-panel select,#reg-filter-panel input').forEach(function(el){el.onchange=function(){page=1;load();};});qs('#reg-filter-panel-clear').onclick=clearAll;qs('#reg-sort').onchange=function(){page=1;load();};qs('#reg-search').oninput=function(){clearTimeout(timer);timer=setTimeout(function(){page=1;load();},280);};
    loadSummary();load();
  }
  App.pages=App.pages||{};App.pages.registros={render:render,tableHtml:tableHtml,bindTableRows:bindTableRows};
})(window.App);
