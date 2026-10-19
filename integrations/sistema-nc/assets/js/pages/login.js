/* Tela de entrada, cadastro e recuperação de acesso. */
window.App = window.App || {};
(function(App){
  "use strict";
  var qs=App.util.qs, qsa=App.util.qsa;

  function enhancePasswords(root){
    qsa('input[type="password"]',root||document).forEach(function(input){
      if(input.parentNode.classList.contains('password-control')) return;
      var wrap=document.createElement('div');wrap.className='password-control';
      input.parentNode.insertBefore(wrap,input);wrap.appendChild(input);
      var toggle=document.createElement('button');toggle.type='button';toggle.className='password-toggle';toggle.textContent='Mostrar';toggle.setAttribute('aria-label','Mostrar senha');wrap.appendChild(toggle);
      var caps=document.createElement('div');caps.className='caps-warning hidden';caps.textContent='Caps Lock está ativado.';wrap.parentNode.insertBefore(caps,wrap.nextSibling);
      toggle.onclick=function(){var show=input.type==='password';input.type=show?'text':'password';toggle.textContent=show?'Ocultar':'Mostrar';toggle.setAttribute('aria-label',(show?'Ocultar':'Mostrar')+' senha');input.focus();};
      function capsState(ev){if(ev.getModifierState)caps.classList.toggle('hidden',!ev.getModifierState('CapsLock'));}
      input.addEventListener('keyup',capsState);input.addEventListener('keydown',capsState);input.addEventListener('blur',function(){caps.classList.add('hidden');});
    });
  }

  function html(){return '<div class="login-shell"><div class="login-brand"><div class="lb-top"><div class="lb-mark"><span class="lb-mark-icon">'+App.icon('checkCircle')+'</span>Gestão da Qualidade</div><h1>Controle e rastreabilidade de não conformidades em contratos de obras rodoviárias.</h1><img class="login-hero-image" src="assets/images/inspecao-rodoviaria.png" alt="Equipe realizando inspeção de qualidade em obra rodoviária"></div></div><div class="login-panel"><div class="login-card"><h2>Acessar o sistema</h2><div class="lc-sub">Informe seus dados para continuar.</div><form id="login-form">'+App.FormField({id:'login-email',label:'E-mail',inputType:'email',required:true,placeholder:'seu.email@empresa.com'})+App.FormField({id:'login-senha',label:'Senha',inputType:'password',required:true,placeholder:'Sua senha'})+'<div id="login-error" class="info-box hidden" style="color:var(--danger);margin-bottom:12px;"></div>'+App.Button({label:'Entrar',variant:'primary',block:true,type:'submit',id:'login-submit'})+'<div class="login-secondary-actions"><button type="button" id="forgot-password">Esqueci minha senha</button><button type="button" id="create-account">Criar minha conta</button></div></form></div></div></div>';}

  function openRegister(){
    var bg=App.openModal('<form id="register-form">'+App.FormField({id:'register-name',label:'Nome completo',required:true})+App.FormField({id:'register-email',label:'E-mail corporativo',inputType:'email',required:true})+App.FormField({id:'register-password',label:'Senha',inputType:'password',required:true,hint:'Use pelo menos 8 caracteres.'})+App.FormField({id:'register-confirm',label:'Confirmar senha',inputType:'password',required:true})+'<div id="register-message" class="info-box hidden" style="margin-bottom:12px;"></div><div class="close-row">'+App.Button({label:'Cancelar',variant:'ghost',type:'button',id:'register-cancel'})+App.Button({label:'Enviar cadastro',variant:'primary',type:'submit',id:'register-submit'})+'</div></form>',{title:'Solicitar acesso'});
    enhancePasswords(bg);qs('#register-cancel',bg).onclick=function(){App.closeModal(bg);};
    qs('#register-form',bg).onsubmit=async function(ev){ev.preventDefault();var nome=qs('#register-name',bg).value.trim(),email=qs('#register-email',bg).value.trim(),senha=qs('#register-password',bg).value,confirmar=qs('#register-confirm',bg).value,msg=qs('#register-message',bg),btn=qs('#register-submit',bg);msg.classList.add('hidden');if(senha.length<8||senha!==confirmar){msg.textContent=senha.length<8?'A senha deve ter pelo menos 8 caracteres.':'As senhas não coincidem.';msg.classList.remove('hidden');return;}btn.disabled=true;try{var result=await App.api.register(nome,email,senha);msg.textContent=result.message;msg.style.color='var(--success)';msg.classList.remove('hidden');qs('#register-form',bg).reset();}catch(e){msg.textContent=e.message;msg.style.color='var(--danger)';msg.classList.remove('hidden');}finally{btn.disabled=false;}};
  }

  function openForgot(){
    var bg=App.openModal('<form id="forgot-form">'+App.FormField({id:'forgot-email',label:'E-mail cadastrado',inputType:'email',required:true,placeholder:'seu.email@empresa.com'})+'<div id="forgot-message" class="info-box hidden" style="margin-bottom:12px;"></div><div class="close-row">'+App.Button({label:'Cancelar',variant:'ghost',type:'button',id:'forgot-cancel'})+App.Button({label:'Enviar link',variant:'primary',type:'submit',id:'forgot-submit'})+'</div></form>',{title:'Recuperar senha'});
    qs('#forgot-cancel',bg).onclick=function(){App.closeModal(bg);};
    qs('#forgot-form',bg).onsubmit=async function(ev){ev.preventDefault();var msg=qs('#forgot-message',bg),btn=qs('#forgot-submit',bg);btn.disabled=true;msg.classList.add('hidden');try{var result=await App.api.requestPasswordReset(qs('#forgot-email',bg).value.trim());msg.textContent=result.message;msg.style.color='var(--success)';msg.classList.remove('hidden');}catch(e){msg.textContent=e.message;msg.style.color='var(--danger)';msg.classList.remove('hidden');}finally{btn.disabled=false;}};
  }

  function openReset(token){
    var bg=App.openModal('<form id="reset-form">'+App.FormField({id:'reset-password',label:'Nova senha',inputType:'password',required:true,hint:'Use pelo menos 8 caracteres.'})+App.FormField({id:'reset-confirm',label:'Confirmar nova senha',inputType:'password',required:true})+'<div id="reset-message" class="info-box hidden" style="margin-bottom:12px;"></div><div class="close-row">'+App.Button({label:'Cancelar',variant:'ghost',type:'button',id:'reset-cancel'})+App.Button({label:'Salvar nova senha',variant:'primary',type:'submit',id:'reset-submit'})+'</div></form>',{title:'Criar nova senha'});
    enhancePasswords(bg);qs('#reset-cancel',bg).onclick=function(){history.replaceState({},'',location.pathname);App.closeModal(bg);};
    qs('#reset-form',bg).onsubmit=async function(ev){ev.preventDefault();var senha=qs('#reset-password',bg).value,confirmar=qs('#reset-confirm',bg).value,msg=qs('#reset-message',bg),btn=qs('#reset-submit',bg);msg.classList.add('hidden');if(senha.length<8||senha!==confirmar){msg.textContent=senha.length<8?'A senha deve ter pelo menos 8 caracteres.':'As senhas não coincidem.';msg.classList.remove('hidden');return;}btn.disabled=true;try{var result=await App.api.resetPassword(token,senha);msg.textContent=result.message;msg.style.color='var(--success)';msg.classList.remove('hidden');history.replaceState({},'',location.pathname);setTimeout(function(){App.closeModal(bg);},1200);}catch(e){msg.textContent=e.message;msg.style.color='var(--danger)';msg.classList.remove('hidden');}finally{btn.disabled=false;}};
  }

  function bind(){
    enhancePasswords(document);qs('#create-account').onclick=openRegister;qs('#forgot-password').onclick=openForgot;
    qs('#login-form').onsubmit=async function(ev){ev.preventDefault();var btn=qs('#login-submit'),err=qs('#login-error');btn.disabled=true;err.classList.add('hidden');try{var data=await App.api.login(qs('#login-email').value.trim(),qs('#login-senha').value);App.state.user=data.user;App.state.sedeId=null;await App.refreshAll();App.router.render();}catch(e){err.textContent=e.message;err.classList.remove('hidden');}finally{btn.disabled=false;}};
    var token=new URLSearchParams(location.search).get('reset_token');if(token)openReset(token);
  }
  App.pages=App.pages||{};App.pages.login={html:html,bind:bind,enhancePasswords:enhancePasswords};
})(window.App);
