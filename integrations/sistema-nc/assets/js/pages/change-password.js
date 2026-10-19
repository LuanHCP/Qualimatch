window.App = window.App || {};
(function(App){
  "use strict";
  function html(){
    return '<div class="login-panel" style="min-height:100vh;"><div class="login-card">'+
      '<h2>Crie uma nova senha</h2><div class="lc-sub">No primeiro acesso, troque a senha provisória antes de continuar.</div>'+
      '<form id="password-form">'+
        App.FormField({id:'senha-atual',label:'Senha provisória',inputType:'password',required:true})+
        App.FormField({id:'senha-nova',label:'Nova senha',inputType:'password',required:true})+
        App.FormField({id:'senha-confirmar',label:'Confirmar nova senha',inputType:'password',required:true})+
        '<div id="password-error" class="info-box hidden" style="color:var(--danger);margin-bottom:12px;"></div>'+
        App.Button({label:'Salvar nova senha',variant:'primary',block:true,type:'submit',id:'password-submit'})+
      '</form></div></div>';
  }
  function bind(){if(App.pages.login&&App.pages.login.enhancePasswords)App.pages.login.enhancePasswords(document);App.util.qs('#password-form').onsubmit=async function(ev){
    ev.preventDefault();var atual=App.util.qs('#senha-atual').value,nova=App.util.qs('#senha-nova').value,confirmar=App.util.qs('#senha-confirmar').value,err=App.util.qs('#password-error'),btn=App.util.qs('#password-submit');
    err.classList.add('hidden'); if(nova.length<8||nova!==confirmar){err.textContent=nova.length<8?'A nova senha deve ter pelo menos 8 caracteres.':'As novas senhas não coincidem.';err.classList.remove('hidden');return;}
    btn.disabled=true;try{await App.api.changePassword(atual,nova);App.state.user.mustChangePassword=false;await App.refreshAll();App.router.render();}catch(e){err.textContent=e.message;err.classList.remove('hidden');}finally{btn.disabled=false;}
  };}
  App.pages=App.pages||{};App.pages.changePassword={html:html,bind:bind};
})(window.App);
