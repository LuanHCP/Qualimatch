/* ============================================================
   router.js — roteamento por hash + shell (sidebar/topbar)
   ============================================================ */
window.App = window.App || {};

(function(App){
  "use strict";
  var qs = App.util.qs, qsa = App.util.qsa, esc = App.util.esc, byId = App.util.byId;

  function parseRoute(){
    var h = location.hash.replace(/^#\/?/,'');
    var parts = h.split('/').filter(Boolean);
    return {name:parts[0]||'dashboard', arg:parts[1], sub:parts[2]};
  }
  function go(hash){ location.hash = hash; }

  var NAV = [
    {group:'OPERAÇÃO', items:[
      {key:'dashboard', label:'Painel', icon:'dashboard'},
      {key:'ncs', label:'Registros', icon:'list'}
    ]},
    {group:'GESTÃO', items:[
      {key:'contratos', label:'Contratos', icon:'fileText'},
      {key:'textos', label:'Textos padronizados', icon:'book'}
    ]},
    {group:'ADMINISTRAÇÃO', items:[
      {key:'config', label:'Configuração da SEDE', icon:'settings', guard:function(){ return App.perm.podeConfigurar(); }},
      {key:'usuarios', label:'Usuários', icon:'users', guard:function(){ return App.perm.podeAdmUsuarios(); }},
      {key:'importexport', label:'Importar / Exportar', icon:'swap'}
    ]}
  ];

  function initials(name){
    var parts = (name||'').trim().split(/\s+/);
    return ((parts[0]||'')[0]||'')+((parts[1]||'')[0]||'');
  }

  function shellHtml(route){
    var sede = App.sedeAtual() || {sigla:'—',nome:'sem SEDE',corPrimaria:'#2e6c8e',logoLetra:'?'};
    var collapsed = localStorage.getItem('nc_sidebar_collapsed')==='1';
    var sedesUser = App.perm.sedesDoUsuario();
    var sedeOptions = sedesUser.map(function(s){ return '<option value="'+s.id+'" '+(s.id===App.state.sedeId?'selected':'')+'>'+esc(s.sigla)+' — '+esc(s.nome)+'</option>'; }).join('');

    var groupsHtml = NAV.map(function(g){
      var items = g.items.filter(function(it){ return !it.guard || it.guard(); });
      if(!items.length) return '';
      return '<div class="nav-group"><div class="nav-group-label">'+g.group+'</div>'+
        items.map(function(it){
          var active = route.name===it.key;
          return '<a class="nav-link '+(active?'active':'')+'" href="#/'+it.key+'" title="'+esc(it.label)+'">'+App.icon(it.icon)+'<span class="lbl">'+esc(it.label)+'</span></a>';
        }).join('')+
      '</div>';
    }).join('');

    return '<div class="shell '+(collapsed?'sidebar-collapsed':'')+'" id="app-shell">'+
      '<div class="mobile-topbar"><button id="mobile-menu-btn" aria-label="Abrir menu">'+App.icon('menu')+'</button>'+
        '<div class="sede-logo" style="background:'+(sede.corPrimaria||'#2e6c8e')+';width:28px;height:28px;font-size:.68rem;">'+esc(sede.logoLetra||'?')+'</div>'+
        '<b style="font-family:var(--font-display);font-size:.85rem;">'+esc(sede.sigla)+'</b></div>'+
      '<aside class="sidebar" id="sidebar">'+
        '<div class="sidebar-head">'+
          '<div class="sede-logo" style="background:'+(sede.corPrimaria||'#2e6c8e')+'">'+esc(sede.logoLetra||'?')+'</div>'+
          '<div class="sede-names"><span class="sede-sig">'+esc(sede.sigla||'')+'</span><span class="sede-nome">'+esc(sede.nome||'')+'</span></div>'+
          '<button class="collapse-btn" id="collapse-btn" title="Recolher/expandir menu">'+App.icon('chevronLeft','sm')+'</button>'+
        '</div>'+
        (sedesUser.length>1 ? '<div class="sede-switch-wrap"><select id="sede-switch">'+sedeOptions+'</select></div>' : '')+
        '<nav class="nav-scroll">'+groupsHtml+'</nav>'+
        '<div class="sidebar-foot">'+
          '<div class="who"><div class="who-avatar">'+esc(initials(App.state.user.nome))+'</div>'+
          '<div class="who-info"><div class="who-name">'+esc(App.state.user.nome)+'</div><div class="who-role">'+esc(App.PERFIS[App.state.user.perfil]||'')+'</div></div></div>'+
          App.Button({label:'Sair', icon:'logout', variant:'ghost', size:'sm', block:true, id:'logout-btn'})+
        '</div>'+
      '</aside>'+
      '<main class="content"><div id="view-mount"></div></main>'+
    '</div>';
  }

  function bindShell(){
    var sw = qs('#sede-switch');
    if(sw) sw.onchange = function(){ App.state.sedeId = sw.value; go('#/dashboard'); render(); };
    qs('#logout-btn').onclick = doLogout;
    var collapseBtn = qs('#collapse-btn');
    if(collapseBtn) collapseBtn.onclick = function(){
      var shell = qs('#app-shell');
      var collapsed = shell.classList.toggle('sidebar-collapsed');
      localStorage.setItem('nc_sidebar_collapsed', collapsed?'1':'0');
    };
    var mBtn = qs('#mobile-menu-btn');
    if(mBtn) mBtn.onclick = function(){ qs('#app-shell').classList.toggle('sidebar-open'); };
    // fecha sidebar mobile ao navegar
    qsa('.nav-link').forEach(function(a){ a.addEventListener('click', function(){ qs('#app-shell').classList.remove('sidebar-open'); }); });
  }

  async function doLogout(){
    try{ await App.api.logout(); }catch(e){}
    App.state.user=null; App.state.sedeId=null;
    location.hash='';
    render();
  }

  async function render(){
    var app = document.getElementById('app');
    if(!App.state.user){ app.innerHTML = App.pages.login.html(); App.pages.login.bind(); return; }
    if(App.state.user.mustChangePassword){ app.innerHTML=App.pages.changePassword.html(); App.pages.changePassword.bind(); return; }
    if(!App.state.sedeId){
      var vis = App.perm.sedesDoUsuario();
      if(vis.length){ App.state.sedeId = vis[0].id; }
      else {
        app.innerHTML = App.PageHeader({title:'Nenhuma SEDE liberada'}) +
          '<div class="page-body">'+App.EmptyState({icon:'building', title:'Seu usuário não está vinculado a nenhuma SEDE', text:'Peça a um administrador para configurar seu acesso.', actionHtml:App.Button({label:'Sair', id:'logout-empty', variant:'ghost'})})+'</div>';
        qs('#logout-empty').onclick = doLogout;
        return;
      }
    }
    var route = parseRoute();
    app.innerHTML = shellHtml(route);
    bindShell();
    var mount = qs('#view-mount');
    try{
      if(route.name==='dashboard') await App.pages.dashboard.render(mount);
      else if(route.name==='ncs' && !route.arg) await App.pages.registros.render(mount);
      else if(route.name==='ncs' && route.arg==='novo') await App.pages.registroForm.render(mount);
      else if(route.name==='ncs' && route.arg) await App.pages.registroDetail.render(mount, route.arg, route.sub);
      else if(route.name==='contratos') await App.pages.contratos.render(mount);
      else if(route.name==='textos') await App.pages.textos.render(mount);
      else if(route.name==='config') await App.pages.configuracao.render(mount);
      else if(route.name==='usuarios') await App.pages.usuarios.render(mount);
      else if(route.name==='importexport') await App.pages.importExport.render(mount);
      else await App.pages.dashboard.render(mount);
    }catch(err){
      mount.innerHTML = '<div class="page-body"><div class="card"><h3>Ocorreu um erro ao carregar esta tela</h3><p class="small mono">'+esc(err.message||String(err))+'</p></div></div>';
      console.error(err);
    }
  }

  App.router = { render:render, go:go, parseRoute:parseRoute, doLogout:doLogout };
  App.pages = App.pages || {};
})(window.App);
