/* ============================================================
   app.js — estado global, utilitários e inicialização (boot)
   Regras de negócio (numeração, prazos, cálculo de vencimento)
   preservadas exatamente como na versão anterior do sistema.
   ============================================================ */
window.App = window.App || {};

(function(App){
  "use strict";

  /* ---------------- estado ---------------- */
  App.DB = null;
  App.CAN_DOWNLOAD = null;
  App.state = {
    user:null, sedeId:null,
    sedes:[], contratos:[], contratadas:[], textos:[], usuarios:[]
  };

  /* ---------------- utilitários genéricos ---------------- */
  var util = {};
  util.qs = function(sel,root){ return (root||document).querySelector(sel); };
  util.qsa = function(sel,root){ return Array.prototype.slice.call((root||document).querySelectorAll(sel)); };
  util.byId = function(list,id){ for(var i=0;i<list.length;i++){ if(list[i].id===id) return list[i]; } return null; };
  util.uid = function(){ return 'id'+Date.now().toString(36)+Math.random().toString(36).slice(2,8); };
  util.esc = function(s){ return (s===undefined||s===null)?"":String(s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];}); };
  util.uniq = function(arr){ var s=[]; arr.forEach(function(v){ if(v && s.indexOf(v)<0) s.push(v); }); return s; };
  util.fmtDate = function(d){ if(!d) return "—"; var dt=new Date(d); if(isNaN(dt)) return d; return dt.toLocaleDateString('pt-BR'); };
  util.fmtDateTime = function(d){ if(!d) return "—"; var dt=new Date(d); if(isNaN(dt)) return d; return dt.toLocaleDateString('pt-BR')+" "+dt.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}); };
  util.fmtMoney = function(v){ if(v===undefined||v===null||v==="") return "—"; var n=Number(v); if(isNaN(n)) return "—"; return "R$ "+n.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}); };
  util.diasEntre = function(a,b){ return Math.round((new Date(b)-new Date(a))/86400000); };
  util.addDias = function(dataISO, dias, diasUteis){
    var d = new Date(dataISO);
    if(!diasUteis){ d.setDate(d.getDate()+dias); return d.toISOString(); }
    var added=0;
    while(added<dias){
      d.setDate(d.getDate()+1);
      if(d.getDay()!==0 && d.getDay()!==6) added++;
    }
    return d.toISOString();
  };
  util.hexToRgb = function(hex){
    hex = (hex||'#2e6c8e').replace('#','');
    if(hex.length===3) hex = hex.split('').map(function(c){return c+c;}).join('');
    var num = parseInt(hex,16);
    return [(num>>16)&255,(num>>8)&255,num&255];
  };
  App.util = util;

  /* ---------------- domínio: sede / numeração ---------------- */
  App.sedeAtual = function(){ return util.byId(App.state.sedes, App.state.sedeId); };

  App.tipoLabel = function(sede, tipoCore){
    if(sede && sede.nomenclatura && sede.nomenclatura[tipoCore]) return sede.nomenclatura[tipoCore];
    return tipoCore==='NC' ? 'RNC' : 'RACP';
  };
  App.proximoNumero = async function(sedeId, tipoCore, ano){
    var snap = await App.DB.collection('ncs').where('sedeId','==',sedeId).where('tipoCore','==',tipoCore).where('ano','==',ano).get();
    return snap.size + 1;
  };
  App.gerarCodigo = function(sede, tipoCore, seq, ano){
    var label = App.tipoLabel(sede, tipoCore);
    var mask = (sede.mascaraNumeracao) || '{SIGLA}_{TIPO}_{SEQ}_{ANO}';
    var seqStr = String(seq).padStart(3,'0');
    return mask.replace('{SIGLA}', sede.sigla||'').replace('{TIPO}', label).replace('{SEQ}', seqStr).replace('{ANO}', ano);
  };

  /* ---------------- isVencido / situação de prazo ---------------- */
  App.isVencido = function(nc){
    if(!nc.prazoResposta) return false;
    if(App.STATUS[nc.statusAtual] && App.STATUS[nc.statusAtual].group==="encerrado") return false;
    if(["aguardando_resposta"].indexOf(nc.statusAtual)===-1) return false;
    return new Date(nc.prazoResposta) < new Date();
  };
  /* situação textual do prazo: 'late' | 'soon' | 'ok' — usada nos badges de prazo */
  App.situacaoPrazo = function(nc){
    if(!nc.prazoResposta) return {tone:'ok', label:'—'};
    var fechado = App.STATUS[nc.statusAtual] && App.STATUS[nc.statusAtual].group==='encerrado';
    var dt = new Date(nc.prazoResposta);
    var diffH = (dt - new Date())/3600000;
    if(!fechado && nc.statusAtual==='aguardando_resposta' && diffH<0){
      var dias = Math.max(1, Math.round(-diffH/24));
      return {tone:'late', label:'Vencido há '+dias+' dia'+(dias>1?'s':'')};
    }
    if(!fechado && nc.statusAtual==='aguardando_resposta' && diffH>=0 && diffH<=48){
      var diasV = Math.max(0, Math.round(diffH/24));
      return {tone:'soon', label: diasV<=0 ? 'Vence hoje' : ('Vence em '+diasV+' dia'+(diasV>1?'s':''))};
    }
    return {tone:'ok', label: util.fmtDate(nc.prazoResposta)};
  };

  /* ---------------- carga de dados ---------------- */
  App.refreshAll = async function(){
    var podeVerUsuarios = App.state.user && (App.state.user.perfil==='admin_geral' || App.state.user.perfil==='admin_sede');
    var r = await Promise.all([
      App.DB.collection('sedes').get(),
      App.DB.collection('contratos').get(),
      App.DB.collection('contratadas').get(),
      App.DB.collection('textos_padrao').get(),
      podeVerUsuarios ? App.DB.collection('usuarios').get() : Promise.resolve({docs:[]})
    ]);
    App.state.sedes = r[0].docs.map(function(d){ return Object.assign({id:d.id}, d.data()); });
    App.state.contratos = r[1].docs.map(function(d){ return Object.assign({id:d.id}, d.data()); });
    App.state.contratadas = r[2].docs.map(function(d){ return Object.assign({id:d.id}, d.data()); });
    App.state.textos = r[3].docs.map(function(d){ return Object.assign({id:d.id}, d.data()); });
    App.state.usuarios = r[4].docs.map(function(d){ return Object.assign({id:d.id}, d.data()); });
    if(!podeVerUsuarios && App.state.user) App.state.usuarios = [App.state.user];
  };
  App.loadNcs = async function(){
    var snap = await App.DB.collection('ncs').where('sedeId','==',App.state.sedeId).get();
    return snap.docs.map(function(d){ return Object.assign({id:d.id}, d.data()); });
  };
  App.loadNc = async function(id){
    var d = await App.DB.doc('ncs/'+id).get();
    if(!d.exists) return null;
    return Object.assign({id:d.id}, d.data());
  };

  /* ---------------- boot ---------------- */
  App.boot = async function(){
    App.DB = App.db.createApiStore();
    App.CAN_DOWNLOAD = App.db.createLocalDownloader();
    try{
      var session = await App.api.me();
      App.state.user = session.user;
      await App.refreshAll();
    }catch(e){ if(e.status!==401) console.error(e); }
    if(App.state.user && !App.state.sedeId){
      var vis = App.perm.sedesDoUsuario();
      if(vis.length) App.state.sedeId = vis[0].id;
    }
    window.addEventListener('hashchange', App.router.render);
    App.router.render();
  };
})(window.App);
