/* ============================================================
   pages/contratos.js — contratos e contratadas da SEDE
   Dados e regras de cadastro preservados (mesmos campos, mesma
   coleção); apenas a apresentação (cards + tabela) é nova.
   ============================================================ */
window.App = window.App || {};
(function(App){
  "use strict";
  var qs=App.util.qs, qsa=App.util.qsa, esc=App.util.esc, byId=App.util.byId, fmtDate=App.util.fmtDate;

  function cardsHtml(contratosSede){
    if(!contratosSede.length) return App.EmptyState({icon:'fileText', title:'Nenhum contrato cadastrado nesta SEDE'});
    var hoje = new Date();
    return '<div class="contratos-cards">'+contratosSede.map(function(c){
      var nomes = (c.contratadaIds||[]).map(function(id){ var x=byId(App.state.contratadas,id); return x?x.razaoSocial:'—'; });
      var vigente = !c.vigenciaFim || new Date(c.vigenciaFim) >= hoje;
      return '<div class="contrato-card">'+
        '<div class="cc-top"><div><div class="cc-num">'+esc(c.numero)+'</div><div class="cc-obra">'+esc(c.descricaoObra||'—')+'</div></div>'+
        App.Badge(vigente?'Vigente':'Encerrado', vigente?'good':'neutral')+
        '</div>'+
        '<div class="cc-meta">'+
          '<span>'+App.icon('users','sm')+' '+esc(nomes.join(', ')||'Sem contratada vinculada')+'</span>'+
          '<span>'+App.icon('calendar','sm')+' '+esc(fmtDate(c.vigenciaInicio))+' – '+esc(fmtDate(c.vigenciaFim))+'</span>'+
        '</div><div class="cc-actions"><button class="cc-expand" type="button" aria-expanded="false">Mostrar mais</button>'+
        (App.perm.podeConfigurar()?App.Button({label:'Editar',variant:'ghost',size:'sm',attrs:' data-edit-contract="'+c.id+'"'}):'')+'</div>'+
      '</div>';
    }).join('')+'</div>';
  }

  function contratadasTableHtml(rows){
    rows = rows || App.state.contratadas;
    if(!rows.length) return App.EmptyState({icon:'users', title:'Nenhuma contratada cadastrada'});
    var columns = [
      {label:'Razão social', render:function(c){ return esc(c.razaoSocial); }},
      {label:'CNPJ', cls:'code-cell', render:function(c){ return esc(c.cnpj||'—'); }},
      {label:'Contratos vinculados', render:function(c){
        var n = App.state.contratos.filter(function(k){ return (k.contratadaIds||[]).indexOf(c.id)>=0; }).length;
        return n ? (n+' contrato'+(n>1?'s':'')) : '—';
      }}
    ];
    return App.Table(columns, rows, {});
  }

  function closeAndRefresh(bg){
    return async function(){ await App.refreshAll(); App.closeModal(bg); App.router.render(); };
  }

  function modalContrato(sede, contratoExistente){
    var atual=contratoExistente||{numero:'',descricaoObra:'',vigenciaInicio:'',vigenciaFim:'',contratadaIds:[]};
    var bg = App.openModal(
      '<form id="f-contrato-modal">'+
        App.FormField({id:'m-numero', label:'Número do contrato', required:true, value:atual.numero})+
        App.FormField({id:'m-obra', label:'Descrição da obra', type:'textarea', rows:2, value:atual.descricaoObra})+
        '<div class="grid g2">'+
          App.FormField({id:'m-inicio', label:'Vigência início', inputType:'date', value:atual.vigenciaInicio||''})+
          App.FormField({id:'m-fim', label:'Vigência fim', inputType:'date', value:atual.vigenciaFim||''})+
        '</div>'+
        '<div class="field"><label class="field-label">Contratadas vinculadas</label><select id="m-contratadas" multiple size="4">'+
          App.state.contratadas.map(function(c){ return '<option value="'+c.id+'"'+((atual.contratadaIds||[]).indexOf(c.id)>=0?' selected':'')+'>'+esc(c.razaoSocial)+'</option>'; }).join('')+
        '</select></div>'+
        '<div class="close-row">'+App.Button({label:'Cancelar', variant:'ghost', type:'button', id:'m-cancel'})+App.Button({label:'Salvar', variant:'primary', type:'submit'})+'</div>'+
      '</form>', {title:contratoExistente?'Editar contrato':'Novo contrato'}
    );
    qs('#m-cancel', bg).onclick = function(){ App.closeModal(bg); };
    qs('#f-contrato-modal', bg).onsubmit = async function(ev){
      ev.preventDefault();
      var numero = qs('#m-numero', bg).value.trim();
      if(!numero){ App.setFieldError('m-numero','Informe o número do contrato.'); return; }
      var ids = Array.prototype.slice.call(qs('#m-contratadas', bg).selectedOptions).map(function(o){ return o.value; });
      var data={
        sedeId: App.state.sedeId, numero: numero, descricaoObra: qs('#m-obra', bg).value,
        vigenciaInicio: qs('#m-inicio', bg).value, vigenciaFim: qs('#m-fim', bg).value, contratadaIds: ids
      };
      if(contratoExistente){await App.DB.doc('contratos/'+contratoExistente.id).update(data);App.toast('Contrato '+numero+' atualizado.','success');}
      else{await App.DB.collection('contratos').add(data);App.toast('Contrato '+numero+' cadastrado.','success');}
      await closeAndRefresh(bg)();
    };
  }

  function modalContratada(){
    var bg = App.openModal(
      '<form id="f-contratada-modal">'+
        App.FormField({id:'m-razao', label:'Razão social', required:true})+
        App.FormField({id:'m-cnpj', label:'CNPJ', optionalTag:true})+
        '<div class="close-row">'+App.Button({label:'Cancelar', variant:'ghost', type:'button', id:'m-cancel2'})+App.Button({label:'Salvar', variant:'primary', type:'submit'})+'</div>'+
      '</form>', {title:'Nova contratada'}
    );
    qs('#m-cancel2', bg).onclick = function(){ App.closeModal(bg); };
    qs('#f-contratada-modal', bg).onsubmit = async function(ev){
      ev.preventDefault();
      var razao = qs('#m-razao', bg).value.trim();
      if(!razao){ App.setFieldError('m-razao','Informe a razão social.'); return; }
      await App.DB.collection('contratadas').add({ razaoSocial: razao, cnpj: qs('#m-cnpj', bg).value });
      App.toast('Contratada cadastrada.','success');
      await closeAndRefresh(bg)();
    };
  }

  async function render(mount){
    var sede = App.sedeAtual();
    var contratosSede = App.state.contratos.filter(function(c){ return c.sedeId===App.state.sedeId; });
    var podeConfigurar = App.perm.podeConfigurar();
    var tab = 'contratos';
    var page = 1, pageSize = 9;

    mount.innerHTML =
      App.PageHeader({
        title:'Contratos e contratadas',
        sub:'Vinculados à SEDE '+sede.sigla+'.',
        actionsHtml: podeConfigurar ? (
          App.Button({label:'Nova contratada', icon:'plus', variant:'ghost', id:'btn-nova-contratada'})+
          App.Button({label:'Novo contrato', icon:'plus', variant:'primary', id:'btn-novo-contrato'})
        ) : ''
      })+
      '<div class="page-body">'+
        '<div class="tabs" id="ct-tabs">'+
          '<button class="tab active" data-tab="contratos">Contratos <span class="tab-count">'+contratosSede.length+'</span></button>'+
          '<button class="tab" data-tab="contratadas">Contratadas <span class="tab-count">'+App.state.contratadas.length+'</span></button>'+
        '</div>'+
        '<div id="ct-content"></div>'+
      '</div>';

    if(podeConfigurar){
      qs('#btn-novo-contrato').onclick = function(){ modalContrato(sede); };
      qs('#btn-nova-contratada').onclick = function(){ modalContratada(); };
    }

    function renderTab(){
      qsa('#ct-tabs .tab').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-tab')===tab); });
      var list=tab==='contratos'?contratosSede:App.state.contratadas;
      var totalPages=Math.max(1,Math.ceil(list.length/pageSize)); if(page>totalPages)page=totalPages;
      var paged=list.slice((page-1)*pageSize,page*pageSize);
      qs('#ct-content').innerHTML = (tab==='contratos' ? cardsHtml(paged) : contratadasTableHtml(paged))+(list.length?App.Pagination(list.length,page,pageSize):'');
      qsa('.cc-expand').forEach(function(btn){ btn.onclick=function(){ var card=btn.closest('.contrato-card'),open=card.classList.toggle('expanded');btn.setAttribute('aria-expanded',open?'true':'false');btn.textContent=open?'Mostrar menos':'Mostrar mais'; }; });
      qsa('[data-edit-contract]').forEach(function(btn){btn.onclick=function(){var c=byId(contratosSede,btn.getAttribute('data-edit-contract'));if(c)modalContrato(sede,c);};});
      qsa('#ct-content .pagination button[data-page]').forEach(function(b){b.onclick=function(){var p=parseInt(b.getAttribute('data-page'),10);if(p>=1&&p<=totalPages){page=p;renderTab();}};});
    }
    qsa('#ct-tabs .tab').forEach(function(b){
      b.onclick = function(){ tab = b.getAttribute('data-tab'); page=1; renderTab(); };
    });
    renderTab();
  }

  App.pages = App.pages || {};
  App.pages.contratos = { render:render };
})(window.App);
