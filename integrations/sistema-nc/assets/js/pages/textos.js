/* ============================================================
   pages/textos.js — biblioteca de textos padronizados
   Lógica de sugestão automática (usada no formulário de NC) não é
   tocada aqui — esta tela é apenas listagem/busca/cadastro/edição
   dos mesmos documentos da coleção "textos_padrao".
   ============================================================ */
window.App = window.App || {};
(function(App){
  "use strict";
  var qs=App.util.qs, qsa=App.util.qsa, esc=App.util.esc, uniq=App.util.uniq;

  function closeAndRefresh(bg){
    return async function(){ await App.refreshAll(); App.closeModal(bg); App.router.render(); };
  }

  function modalTexto(textoExistente){
    var t = textoExistente || {categoria:'', item:'', subitem:'', texto:''};
    var bg = App.openModal(
      '<form id="f-texto-modal">'+
        App.FormField({id:'t-categoria', label:'Categoria', required:true, value:t.categoria})+
        App.FormField({id:'t-item', label:'Item', required:true, value:t.item})+
        App.FormField({id:'t-subitem', label:'Subitem', optionalTag:true, value:t.subitem})+
        App.FormField({id:'t-texto', label:'Texto padrão', type:'textarea', rows:5, required:true, value:t.texto})+
        '<div class="close-row">'+App.Button({label:'Cancelar', variant:'ghost', type:'button', id:'t-cancel'})+App.Button({label:'Salvar', variant:'primary', type:'submit'})+'</div>'+
      '</form>', {title: textoExistente ? 'Editar texto padrão' : 'Novo texto padrão'}
    );
    qs('#t-cancel', bg).onclick = function(){ App.closeModal(bg); };
    qs('#f-texto-modal', bg).onsubmit = async function(ev){
      ev.preventDefault();
      var categoria = qs('#t-categoria', bg).value.trim();
      var item = qs('#t-item', bg).value.trim();
      var texto = qs('#t-texto', bg).value.trim();
      var hasError=false;
      if(!categoria){ App.setFieldError('t-categoria','Informe a categoria.'); hasError=true; }
      if(!item){ App.setFieldError('t-item','Informe o item.'); hasError=true; }
      if(!texto){ App.setFieldError('t-texto','Informe o texto padrão.'); hasError=true; }
      if(hasError) return;
      var data = { categoria:categoria, item:item, subitem:qs('#t-subitem', bg).value.trim(), texto:texto };
      if(textoExistente){
        await App.DB.doc('textos_padrao/'+textoExistente.id).update(data);
        App.toast('Texto padrão atualizado.','success');
      } else {
        data.sedeId = App.state.sedeId;
        await App.DB.collection('textos_padrao').add(data);
        App.toast('Texto padrão cadastrado.','success');
      }
      await closeAndRefresh(bg)();
    };
  }

  async function render(mount){
    var podeConfigurar = App.perm.podeConfigurar();
    var textos = App.state.textos.filter(function(t){ return t.sedeId===App.state.sedeId || t.sedeId==='GLOBAL'; });
    var categorias = uniq(textos.map(function(t){ return t.categoria; })).sort();
    var page = 1, pageSize = 9;

    mount.innerHTML =
      App.PageHeader({
        title:'Biblioteca de textos padronizados',
        sub:'Organizados por categoria → item → subitem. Sugeridos automaticamente no cadastro de NC.',
        actionsHtml: podeConfigurar ? App.Button({label:'Novo texto', icon:'plus', variant:'primary', id:'btn-novo-texto'}) : ''
      })+
      '<div class="page-body">'+
        '<div class="txt-search-row">'+
          '<div class="search-input" style="flex:2;min-width:240px;">'+App.icon('search','sm')+
            '<input type="text" id="txt-busca" placeholder="Buscar por categoria, item ou texto...">'+
          '</div>'+
          App.selectHtml('txt-cat','Categoria',[['','Todas as categorias']].concat(categorias.map(function(c){ return [c,c]; })))+
        '</div>'+
        '<div id="txt-list"></div><div id="txt-pagination"></div>'+
      '</div>';

    function apply(){
      var termo = (qs('#txt-busca').value||'').toLowerCase();
      var cat = qs('#txt-cat').value;
      var filtrados = textos.filter(function(t){
        if(cat && t.categoria!==cat) return false;
        if(termo){
          var hay = [t.categoria, t.item, t.subitem, t.texto].filter(Boolean).join(' ').toLowerCase();
          if(hay.indexOf(termo)<0) return false;
        }
        return true;
      });
      page = 1; renderList(filtrados);
    }

    function renderList(list){
      if(!list.length){
        qs('#txt-list').innerHTML = App.EmptyState({icon:'book', title:'Nenhum texto encontrado', text:'Ajuste a busca ou o filtro de categoria.'});
        qs('#txt-pagination').innerHTML = '';
        return;
      }
      var totalPages=Math.max(1,Math.ceil(list.length/pageSize)); if(page>totalPages)page=totalPages;
      var paged=list.slice((page-1)*pageSize,page*pageSize), byCat = {};
      paged.forEach(function(t){ (byCat[t.categoria]=byCat[t.categoria]||[]).push(t); });
      qs('#txt-list').innerHTML = Object.keys(byCat).sort().map(function(cat){
        return '<div class="card-section-title">'+esc(cat)+'</div>'+byCat[cat].map(function(t){
          return '<div class="txt-card">'+
            '<div class="txt-top">'+
              '<div class="txt-path">'+esc(t.item)+(t.subitem?(' <span style="opacity:.55;">/</span> '+esc(t.subitem)):'')+
                ' <span style="opacity:.55;font-weight:500;">· '+(t.sedeId==='GLOBAL'?'global':'desta SEDE')+'</span></div>'+
              (podeConfigurar ? App.Button({label:'Editar', variant:'ghost', size:'sm', attrs:' data-edit="'+t.id+'"'}) : '')+
            '</div>'+
            '<p>'+esc(t.texto)+'</p>'+
          '</div>';
        }).join('');
      }).join('');
      qsa('[data-edit]').forEach(function(b){
        b.onclick = function(){
          var t = App.util.byId(App.state.textos, b.getAttribute('data-edit'));
          if(t) modalTexto(t);
        };
      });
      qs('#txt-pagination').innerHTML=App.Pagination(list.length,page,pageSize);
      qsa('#txt-pagination button[data-page]').forEach(function(b){b.onclick=function(){var p=parseInt(b.getAttribute('data-page'),10);if(p>=1&&p<=totalPages){page=p;renderList(list);}};});
    }

    qs('#txt-busca').oninput = apply;
    qs('#txt-cat').onchange = apply;
    if(podeConfigurar) qs('#btn-novo-texto').onclick = function(){ modalTexto(null); };
    apply();
  }

  App.pages = App.pages || {};
  App.pages.textos = { render:render };
})(window.App);
