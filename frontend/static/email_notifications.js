/* Preferences load only when requested, never during page navigation. */
let emailPreferencesLoading=false;
let desktopNotificationsChecking=false;
function desktopNotificationKey(name){
 const userId=(typeof currentUser!=='undefined'&&currentUser?.id)||'anonymous';
 return `qualimatch.desktop.${userId}.${name}`;
}
function desktopNotificationStorage(name,value){
 try{if(typeof localStorage==='undefined')return null;if(value===undefined)return localStorage.getItem(desktopNotificationKey(name));localStorage.setItem(desktopNotificationKey(name),String(value));return String(value)}catch{return null}
}
function desktopNotificationSupported(){return typeof Notification!=='undefined'&&typeof window!=='undefined'&&window.isSecureContext!==false}
function desktopNotificationEnabled(){return desktopNotificationSupported()&&Notification.permission==='granted'&&desktopNotificationStorage('enabled')==='1'}
function desktopNotificationMarkup(){
 const supported=desktopNotificationSupported(),permission=supported?Notification.permission:'unsupported',enabled=desktopNotificationEnabled();
 const status=enabled?'Ativadas neste computador':permission==='denied'?'Bloqueadas pelo navegador':supported?'Desativadas':'Navegador ou endereço não compatível';
 return `<div class="desktop-notification-card"><div><span class="eyebrow">ÁREA DE TRABALHO</span><h3>Notificações do Windows</h3><p>Avisa quando um certificado BV novo for importado. O QualiMatch precisa permanecer aberto em uma aba, mesmo minimizada.</p><span class="status-badge ${enabled?'ok':permission==='denied'?'bad':'neutral'}">${status}</span></div><div>${enabled?'<button type="button" id="desktop-notifications-disable" class="ghost">Desativar neste computador</button>':`<button type="button" id="desktop-notifications-enable" class="primary" ${supported&&permission!=='denied'?'':'disabled'}>Ativar neste computador</button>`}</div></div>${permission==='denied'?'<p class="warn-text">A permissão foi bloqueada. Abra as permissões deste site no navegador e permita “Notificações”.</p>':''}`;
}
function emailPreferencesMarkup(d){
 const counts=d.delivery_counts||{},pending=Number(counts.PENDING||0)+Number(counts.SENDING||0);
 return `<div class="edit-modal"><span class="eyebrow">MINHA CONTA / AVISOS</span><h2>Central de notificações</h2>
 ${desktopNotificationMarkup()}
 <div class="notification-settings-divider"><span class="eyebrow">E-MAIL</span><h3>Notificações por e-mail</h3></div>
 <p>Enviar para <b>${esc(d.email)}</b>, o e-mail cadastrado na sua conta.</p>
 ${d.smtp_configured?'':'<div class="management-note"><b>Envio ainda não configurado</b><span>Sua preferência pode ser salva, mas o administrador precisa configurar o SMTP no servidor para os e-mails saírem.</span></div>'}
 <form id="email-notifications-form">
 <label class="edit-check"><input id="email-bv-enabled" type="checkbox" ${d.bv_new_certificates?'checked':''} ${d.can_subscribe_bv?'':'disabled'}> <b>BV — novos certificados</b></label>
 <p class="muted">Um aviso por certificado novo importado das pastas BV/Certificados sincronizadas com o SharePoint, após ativar esta opção. Não envia a base antiga nem avisa sobre releituras ou atualizações de certificados existentes.</p>
 ${d.can_subscribe_bv?'':'<p class="warn-text">Solicite acesso à BV ao administrador para ativar este aviso.</p>'}
 <p class="muted">O servidor e a sincronização precisam estar funcionando. Desativar cancela os avisos ainda na fila; um e-mail já em envio pode chegar.</p>
 <p aria-live="polite">Na fila: ${pending} · Falhas após tentativas: ${Number(counts.FAILED||0)}${d.last_sent_at?' · Último envio: '+esc(d.last_sent_at.replace('T',' ')):''}</p>
 ${counts.FAILED?'<p class="warn-text">Há avisos que não puderam ser enviados. Confira o Histórico e a configuração SMTP antes de tentar novamente.</p>':''}
 <div class="edit-actions"><button type="button" class="ghost" onclick="closeModal()">Fechar</button><button id="email-preferences-save" class="primary">Salvar preferência</button></div>
 ${counts.FAILED?'<div class="edit-actions"><button id="email-retry-failed" type="button" class="ghost">Tentar enviar novamente ('+Number(counts.FAILED)+')</button></div>':''}
 </form></div>`;
}
async function enableDesktopNotifications(){
 if(!desktopNotificationSupported())return toast('As notificações exigem localhost ou acesso HTTPS.',true);
 try{
  const permission=await Notification.requestPermission();
  if(permission!=='granted')return toast('Permissão de notificação não concedida pelo navegador.',true);
  const baseline=await api('/api/desktop-notifications/certificates?after_id=0');
  desktopNotificationStorage('last_certificate_id',Number(baseline.latest_id||0));
  desktopNotificationStorage('enabled','1');
  new Notification('QualiMatch',{body:'Notificações da área de trabalho ativadas.'});
  closeModal();toast('Notificações do Windows ativadas neste computador.');
 }catch(err){toast(err.message||'Não foi possível ativar as notificações.',true)}
}
function disableDesktopNotifications(){desktopNotificationStorage('enabled','0');closeModal();toast('Notificações da área de trabalho desativadas neste computador.')}
async function checkDesktopCertificateNotifications(){
 if(desktopNotificationsChecking||!desktopNotificationEnabled()||typeof currentUser==='undefined'||!currentUser)return;
 desktopNotificationsChecking=true;
 try{
  const last=Math.max(0,Number(desktopNotificationStorage('last_certificate_id')||0));
  const data=await api('/api/desktop-notifications/certificates?after_id='+last);
  const latest=Number(data.latest_id||last),items=data.items||[],total=Number(data.new_count||items.length);
  if(!last){desktopNotificationStorage('last_certificate_id',latest);return}
  items.slice(0,3).reverse().forEach(item=>{
   const detail=[item.contractor,item.road].filter(Boolean).join(' • ');
   const notice=new Notification('Novo certificado BV',{body:`${item.number||'Certificado'}${detail?'\n'+detail:''}`,tag:`qualimatch-certificate-${item.id}`});
   notice.onclick=()=>{window.focus();if(typeof enterPortal==='function')enterPortal('BV','certificates');notice.close()};
  });
  if(total>3)new Notification('Novos certificados BV',{body:`${total} certificados foram importados. Abra o QualiMatch para conferir.`,tag:'qualimatch-certificates-summary'});
  desktopNotificationStorage('last_certificate_id',latest);
 }catch(err){if(err?.message&&!String(err.message).includes('Sessão'))console.warn('Desktop notification check failed',err)}finally{desktopNotificationsChecking=false}
}
async function openEmailNotifications(){
 if(emailPreferencesLoading)return;
 emailPreferencesLoading=true;
 try{
  const d=await api('/api/auth/email-notifications');
  $('#notification-panel').hidden=true;
  showModal(emailPreferencesMarkup(d));
  const desktopEnable=$('#desktop-notifications-enable'),desktopDisable=$('#desktop-notifications-disable');
  if(desktopEnable)desktopEnable.onclick=enableDesktopNotifications;
  if(desktopDisable)desktopDisable.onclick=disableDesktopNotifications;
  $('#email-notifications-form').onsubmit=async e=>{
   e.preventDefault();const button=$('#email-preferences-save');button.disabled=true;
   try{
    const saved=await api('/api/auth/email-notifications',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({bv_new_certificates:d.can_subscribe_bv&&$('#email-bv-enabled').checked})});
    closeModal();toast(saved.bv_new_certificates?(saved.smtp_configured?'Avisos BV ativados para novas importações.':'Preferência salva. Falta configurar o SMTP no servidor.'):'Avisos BV por e-mail desativados.');
   }catch(err){toast(err.message,true)}finally{button.disabled=false}
  };
  const retry=$('#email-retry-failed');
  if(retry)retry.onclick=async()=>{
   retry.disabled=true;
   try{
    const result=await api('/api/auth/email-notifications/retry',{method:'POST'});
    closeModal();toast(result.retried?`${result.retried} aviso(s) recolocado(s) na fila de envio.`:'Não há avisos com falha para reenviar.');
   }catch(err){toast(err.message,true)}finally{retry.disabled=false}
  };
 }catch(err){toast(err.message,true)}finally{emailPreferencesLoading=false}
}
