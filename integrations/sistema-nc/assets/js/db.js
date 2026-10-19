/* Adaptador da interface original para a API/PostgreSQL. */
window.App = window.App || {};
(function(App){
  "use strict";
  var endpoints={sedes:'/api/sedes',contratos:'/api/contratos',contratadas:'/api/contratadas',textos_padrao:'/api/textos',usuarios:'/api/admin/usuarios',ncs:'/api/ncs'};
  function snapDoc(item){return {id:item.id,exists:true,data:function(){return item;}};}
  function snapshot(items){return {size:items.length,empty:!items.length,docs:items.map(snapDoc)};}
  function Query(name){this.name=name;this.filters=[];this.sort=null;this.max=null;}
  Query.prototype.where=function(field,op,value){this.filters.push([field,op,value]);return this;};
  Query.prototype.orderBy=function(field,direction){this.sort=[field,direction||'asc'];return this;};
  Query.prototype.limit=function(n){this.max=n;return this;};
  Query.prototype.get=async function(){
    var path=endpoints[this.name]; if(!path) throw new Error('Coleção não suportada: '+this.name);
    if(this.name==='ncs'){
      var sede=this.filters.find(function(f){return f[0]==='sedeId'&&f[1]==='==';});
      if(!sede) return snapshot([]);
      path+='?sedeId='+encodeURIComponent(sede[2]);
    }
    var items=await App.api.get(path);
    this.filters.forEach(function(f){items=items.filter(function(x){if(f[1]==='==')return x[f[0]]===f[2];if(f[1]==='array-contains')return(x[f[0]]||[]).indexOf(f[2])>=0;return true;});});
    if(this.sort){var s=this.sort;items.sort(function(a,b){var r=a[s[0]]>b[s[0]]?1:(a[s[0]]<b[s[0]]?-1:0);return s[1]==='desc'?-r:r;});}
    if(this.max)items=items.slice(0,this.max); return snapshot(items);
  };
  Query.prototype.add=async function(data){var item=await App.api.post(endpoints[this.name],data);return {id:item.id,data:item};};

  function dataUrlToFile(dataUrl,name){
    var parts=dataUrl.split(','),mime=(parts[0].match(/:(.*?);/)||[])[1]||'image/png',bytes=atob(parts[1]),arr=new Uint8Array(bytes.length);
    for(var i=0;i<bytes.length;i++)arr[i]=bytes.charCodeAt(i);
    return new File([arr],name||'evidencia.png',{type:mime});
  }
  async function updateNc(id,patch){
    if(patch.respostaContratada)return App.api.post('/api/ncs/'+id+'/resposta',patch.respostaContratada);
    var av=patch.avaliacaoConcessionaria||{};
    if(av.resultadoEficacia)return App.api.post('/api/ncs/'+id+'/eficacia',{resultado:av.resultadoEficacia,valor:av.valorRetidoFinal,parecer:av.parecerTecnico||''});
    if(patch.statusAtual==='aguardando_verificacao')return App.api.post('/api/ncs/'+id+'/solicitar-verificacao',{});
    if(patch.statusAtual==='encerrada')return App.api.post('/api/ncs/'+id+'/encerrar-vencido',{});
    if(patch.statusAtual==='em_execucao'||(patch.statusAtual==='aguardando_resposta'&&patch.avaliacaoConcessionaria))return App.api.post('/api/ncs/'+id+'/analise',{decisao:patch.statusAtual==='em_execucao'?'aprovada':'recusada',parecer:av.parecerTecnico||''});
    if(patch.anexos&&patch.anexos.length){
      var anexo=patch.anexos[patch.anexos.length-1];
      if(anexo.thumb&&anexo.thumb.indexOf('data:')===0){
        var fd=new FormData();fd.append('arquivo',dataUrlToFile(anexo.thumb,anexo.nomeArquivo||'evidencia.png'));
        ['legenda','dataFoto','km','pista','faixa'].forEach(function(k){if(anexo[k]!=null)fd.append(k,anexo[k]);});
        return App.api.request('/api/ncs/'+id+'/anexos',{method:'POST',body:fd});
      }
    }
    return App.api.patch('/api/ncs/'+id,patch);
  }
  function createApiStore(){return {
    collection:function(name){return new Query(name);},
    doc:function(path){var parts=path.split('/'),name=parts[0],id=parts[1];return {
      get:async function(){try{var item;if(name==='ncs')item=await App.api.get('/api/ncs/'+id);else{var s=await new Query(name).get();item=s.docs.map(function(d){return d.data();}).find(function(x){return x.id===id;});}return item?snapDoc(item):{id:id,exists:false,data:function(){return null;}};}catch(e){if(e.status===404)return{id:id,exists:false,data:function(){return null;}};throw e;}},
      update:function(data){if(name==='ncs')return updateNc(id,data);if(name==='sedes')return App.api.patch('/api/sedes/'+id,data);if(name==='contratos')return App.api.patch('/api/contratos/'+id,data);if(name==='textos_padrao')return App.api.patch('/api/textos/'+id,data);if(name==='usuarios')return App.api.patch('/api/admin/usuarios/'+id,data);throw new Error('Atualização não suportada para '+name+'.');},
      delete:function(){return App.api.remove(endpoints[name]+'/'+id);}
    };}
  };}
  function createLocalDownloader(){return {save:async function(o){var blob=new Blob([o.data]),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=o.filename;a.click();setTimeout(function(){URL.revokeObjectURL(a.href);},1000);}};}
  App.db={createApiStore:createApiStore,createLocalDownloader:createLocalDownloader};
})(window.App);
