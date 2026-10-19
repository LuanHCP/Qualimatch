/* Cliente HTTP da API PostgreSQL/Flask. */
window.App = window.App || {};
(function(App){
  "use strict";
  var csrfToken = null;
  async function request(path, options){
    options = options || {};
    var headers = new Headers(options.headers || {});
    if(options.body && !(options.body instanceof FormData) && typeof options.body !== 'string'){
      headers.set('Content-Type','application/json'); options.body = JSON.stringify(options.body);
    }
    if(csrfToken && !/^(GET|HEAD|OPTIONS)$/i.test(options.method || 'GET')) headers.set('X-CSRF-Token', csrfToken);
    options.headers = headers; options.credentials = 'same-origin';
    var response = await fetch(path, options);
    var type = response.headers.get('content-type') || '';
    var data = type.indexOf('application/json') >= 0 ? await response.json() : await response.blob();
    if(!response.ok){ var err = new Error((data && data.error) || ('Falha na comunicação com o servidor ('+response.status+').')); err.status=response.status; err.field=data&&data.field; throw err; }
    if(data && data.csrfToken) csrfToken = data.csrfToken;
    return data;
  }
  App.api = {
    request:request,
    get:function(path){ return request(path); },
    post:function(path,body){ return request(path,{method:'POST',body:body}); },
    patch:function(path,body){ return request(path,{method:'PATCH',body:body}); },
    remove:function(path){ return request(path,{method:'DELETE'}); },
    login:function(email,senha){ return request('/api/auth/login',{method:'POST',body:{email:email,senha:senha}}); },
    register:function(nome,email,senha){ return request('/api/auth/register',{method:'POST',body:{nome:nome,email:email,senha:senha}}); },
    requestPasswordReset:function(email){ return request('/api/auth/request-password-reset',{method:'POST',body:{email:email}}); },
    resetPassword:function(token,novaSenha){ return request('/api/auth/reset-password',{method:'POST',body:{token:token,novaSenha:novaSenha}}); },
    logout:function(){ return request('/api/auth/logout',{method:'POST'}); },
    me:function(){ return request('/api/auth/me'); },
    changePassword:function(senhaAtual,novaSenha){ return request('/api/auth/change-password',{method:'POST',body:{senhaAtual:senhaAtual,novaSenha:novaSenha}}); }
  };
})(window.App);
