/* ============================================================
   pages/usuarios.js — administração de usuários
   Mantém o mecanismo do protótipo (seleção de usuário, sem senha);
   apenas a tabela/administração ganham camada visual nova.
   ============================================================ */
window.App = window.App || {};
(function(App){
  "use strict";
  var qs=App.util.qs, qsa=App.util.qsa, esc=App.util.esc, byId=App.util.byId;

  function closeAndRefresh(bg){
    return async function(){ await App.refreshAll(); App.closeModal(bg); App.router.render(); };
  }

  function modalUsuario(usuarioExistente){
    var u = usuarioExistente || {nome:'', email:'', perfil:'consulta', sedeIds:[], contratoIds:[]};
    var bg = App.openModal(
      '<form id="f-usuario-modal">'+
        App.FormField({id:'u-nome', label:'Nome', required:true, value:u.nome})+
        App.FormField({id:'u-email', label:'E-mail', inputType:'email', value:u.email})+
        (!usuarioExistente ? App.FormField({id:'u-senha', label:'Senha provisória', inputType:'password', required:true, placeholder:'Mínimo de 8 caracteres'}) : '')+
        App.FormField({id:'u-perfil', label:'Perfil', type:'select', value:u.perfil,
          options: Object.keys(App.PERFIS).map(function(k){ return [k, App.PERFIS[k]]; })})+
        '<div class="field"><label class="field-label">Sedes (múltiplas — vazio = todas, apenas p/ Administrador geral)</label><select id="u-sedes" multiple size="3">'+
          App.state.sedes.map(function(s){ return '<option value="'+s.id+'"'+((u.sedeIds||[]).indexOf(s.id)>=0?' selected':'')+'>'+esc(s.sigla)+'</option>'; }).join('')+
        '</select></div>'+
        '<div class="field"><label class="field-label">Contratos (múltiplos, opcional)</label><select id="u-contratos" multiple size="3">'+
          App.state.contratos.map(function(c){ return '<option value="'+c.id+'"'+((u.contratoIds||[]).indexOf(c.id)>=0?' selected':'')+'>'+esc(c.numero)+'</option>'; }).join('')+
        '</select></div>'+
        '<div class="close-row">'+App.Button({label:'Cancelar', variant:'ghost', type:'button', id:'u-cancel'})+App.Button({label:'Salvar', variant:'primary', type:'submit'})+'</div>'+
      '</form>', {title: usuarioExistente ? 'Editar usuário' : 'Novo usuário'}
    );
    qs('#u-cancel', bg).onclick = function(){ App.closeModal(bg); };
    qs('#f-usuario-modal', bg).onsubmit = async function(ev){
      ev.preventDefault();
      var nome = qs('#u-nome', bg).value.trim();
      if(!nome){ App.setFieldError('u-nome','Informe o nome do usuário.'); return; }
      var sedeIds = Array.prototype.slice.call(qs('#u-sedes', bg).selectedOptions).map(function(o){ return o.value; });
      var contratoIds = Array.prototype.slice.call(qs('#u-contratos', bg).selectedOptions).map(function(o){ return o.value; });
      var data = { nome:nome, email:qs('#u-email', bg).value, perfil:qs('#u-perfil', bg).value, sedeIds:sedeIds, contratoIds:contratoIds };
      if(!usuarioExistente){ data.senhaProvisoria=qs('#u-senha',bg).value; if(data.senhaProvisoria.length<8){App.setFieldError('u-senha','Informe pelo menos 8 caracteres.');return;} }
      if(usuarioExistente){
        await App.DB.doc('usuarios/'+usuarioExistente.id).update(data);
        App.toast('Usuário atualizado.','success');
      } else {
        await App.DB.collection('usuarios').add(data);
        App.toast('Usuário cadastrado.','success');
      }
      await closeAndRefresh(bg)();
    };
  }

  async function render(mount){
    if(!App.perm.podeAdmUsuarios()){
      mount.innerHTML = App.PageHeader({title:'Usuários'})+
        '<div class="page-body">'+App.EmptyState({icon:'users', title:'Sem permissão', text:'Apenas Administrador geral ou Administrador da SEDE podem gerenciar usuários.'})+'</div>';
      return;
    }
    var usuarios = App.state.usuarios.slice().sort(function(a,b){return (a.approvalStatus==='pendente'?-1:1)-(b.approvalStatus==='pendente'?-1:1);});
    var pendentes = usuarios.filter(function(u){return u.approvalStatus==='pendente';}).length;

    mount.innerHTML =
      App.PageHeader({
        title:'Usuários',
        sub:'Perfil e escopo (sedes/contratos) de cada usuário.',
        actionsHtml: ''
      })+
      '<div class="page-body">'+(pendentes?'<div class="alert-banner warn" style="margin:0 0 16px;">'+App.icon('clock')+'<div><strong>'+pendentes+' cadastro(s) aguardando aprovação</strong>Revise o perfil e as sedes após aprovar.</div></div>':'')+'<div id="usr-table"></div></div>';

    if(!usuarios.length){
      qs('#usr-table').innerHTML = App.EmptyState({icon:'users', title:'Nenhum usuário cadastrado'});
      return;
    }

    var columns = [
      {label:'Usuário', render:function(u){ return '<b>'+esc(u.nome)+'</b>'; }},
      {label:'E-mail', render:function(u){ return esc(u.email||'—'); }},
      {label:'Perfil', render:function(u){ return App.Badge(App.PERFIS[u.perfil]||u.perfil, App.PERFIL_TONE[u.perfil]||'neutral'); }},
      {label:'Situação', render:function(u){return App.Badge(u.approvalStatus==='pendente'?'Aguardando aprovação':'Aprovado',u.approvalStatus==='pendente'?'warn':'good');}},
      {label:'SEDE', render:function(u){
        var nomes = (u.sedeIds||[]).map(function(id){ var s=byId(App.state.sedes,id); return s?s.sigla:''; }).filter(Boolean);
        return esc(nomes.join(', ') || 'Todas');
      }},
      {label:'Contratos', render:function(u){
        var n = (u.contratoIds||[]).length;
        return n ? (n+' contrato'+(n>1?'s':'')) : 'Todos visíveis ao perfil';
      }},
      {label:'', cls:'row-action', render:function(u){ return (u.approvalStatus==='pendente'?App.Button({label:'Aprovar',variant:'primary',size:'sm',attrs:' data-approve="'+u.id+'"'}):'')+App.Button({label:'Redefinir acesso',variant:'ghost',size:'sm',attrs:' data-reset-access="'+u.id+'"'})+App.Button({label:'Editar', variant:'ghost', size:'sm', attrs:' data-edit="'+u.id+'"'}); }}
    ];
    qs('#usr-table').innerHTML = App.Table(columns, usuarios, {});
    qsa('[data-edit]').forEach(function(b){
      b.onclick = function(){ var u = byId(App.state.usuarios, b.getAttribute('data-edit')); if(u) modalUsuario(u); };
    });
    qsa('[data-approve]').forEach(function(b){b.onclick=async function(){var u=byId(App.state.usuarios,b.getAttribute('data-approve'));if(!u)return;b.disabled=true;try{await App.api.post('/api/admin/usuarios/'+u.id+'/aprovar',{perfil:u.perfil,sedeIds:(u.sedeIds&&u.sedeIds.length)?u.sedeIds:[App.state.sedeId]});App.toast('Cadastro aprovado.','success');await App.refreshAll();App.router.render();}catch(e){App.toast(e.message,'danger');b.disabled=false;}};});
    qsa('[data-reset-access]').forEach(function(b){b.onclick=async function(){var u=byId(App.state.usuarios,b.getAttribute('data-reset-access'));if(!u)return;var ok=await App.confirmDialog({title:'Redefinir acesso?',message:'Será criada uma senha provisória, os bloqueios serão removidos e as sessões atuais de '+u.nome+' serão encerradas.',confirmLabel:'Redefinir acesso'});if(!ok)return;b.disabled=true;try{var result=await App.api.post('/api/admin/usuarios/'+u.id+'/reset-senha',{});var bg=App.openModal('<p class="small" style="color:var(--ink-soft);margin-bottom:14px;">Entregue esta senha provisória ao usuário por um canal seguro. Ela será exibida apenas agora.</p><div class="input-group"><input id="temporary-password" readonly value="'+esc(result.senhaProvisoria)+'"><button class="btn primary" id="copy-temporary" type="button"><span>Copiar</span></button></div>',{title:'Acesso redefinido'});qs('#copy-temporary',bg).onclick=function(){var input=qs('#temporary-password',bg);input.select();if(navigator.clipboard)navigator.clipboard.writeText(input.value);else document.execCommand('copy');App.toast('Senha provisória copiada.','success');};await App.refreshAll();}catch(e){App.toast(e.message,'danger');b.disabled=false;}};});
  }

  App.pages = App.pages || {};
  App.pages.usuarios = { render:render };
})(window.App);
