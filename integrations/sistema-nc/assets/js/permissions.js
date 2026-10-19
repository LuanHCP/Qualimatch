/* ============================================================
   permissions.js — domínios (perfis, status, tipos) e regras de
   visibilidade/permissão. Mesmas regras da versão anterior.
   ============================================================ */
window.App = window.App || {};

(function(App){
  "use strict";

  App.PERFIS = {
    admin_geral:       "Administrador geral",
    admin_sede:        "Administrador da SEDE",
    qualidade:         "Qualidade",
    fiscalizacao:      "Fiscalização / Engenharia",
    gestor_contrato:   "Gestor do contrato",
    contratada:        "Contratada",
    consulta:          "Consulta / Auditoria"
  };

  /* rótulo curto usado em badges de perfil */
  App.PERFIL_TONE = {
    admin_geral:"primary", admin_sede:"primary", qualidade:"accent",
    fiscalizacao:"accent", gestor_contrato:"neutral", contratada:"warn", consulta:"neutral"
  };

  App.STATUS = {
    rascunho:               {label:"Rascunho", group:"aberto", ordem:1},
    emitida:                {label:"Emitida", group:"aberto", ordem:2},
    protocolada:            {label:"Protocolada", group:"aberto", ordem:3},
    aguardando_resposta:    {label:"Aguard. resposta da contratada", group:"aberto", ordem:4},
    respondida:             {label:"Respondida", group:"aberto", ordem:5},
    em_analise:             {label:"Em análise pela concessionária", group:"aberto", ordem:6},
    disposicao_aprovada:    {label:"Disposição aprovada", group:"aberto", ordem:7},
    disposicao_recusada:    {label:"Disposição recusada", group:"aberto", ordem:7},
    em_execucao:            {label:"Em execução", group:"aberto", ordem:8},
    aguardando_verificacao: {label:"Aguard. verificação de eficácia", group:"aberto", ordem:9},
    eficaz:                 {label:"Eficaz", group:"encerrado", ordem:10},
    nao_eficaz:             {label:"Não eficaz", group:"aberto", ordem:10},
    encerrada:              {label:"Encerrada", group:"encerrado", ordem:11}
  };

  /* etapas do stepper visual do fluxo (seção 7 do pedido) */
  App.FLOW_STEPS = [
    {key:'emissao', label:'Emissão', statuses:['rascunho','emitida']},
    {key:'protocolo', label:'Protocolo', statuses:['protocolada']},
    {key:'resposta', label:'Resposta', statuses:['aguardando_resposta','respondida']},
    {key:'analise', label:'Análise', statuses:['em_analise','disposicao_aprovada','disposicao_recusada']},
    {key:'execucao', label:'Execução', statuses:['em_execucao']},
    {key:'eficacia', label:'Eficácia', statuses:['aguardando_verificacao','eficaz','nao_eficaz']},
    {key:'encerramento', label:'Encerramento', statuses:['encerrada']}
  ];

  App.TIPOS_CORE = { NC:"Não Conformidade", AC:"Ação Corretiva/Preventiva" };
  App.UNIDADES = ["m²","m³","un","ml","kg","t"];

  App.perm = {
    perfil: function(){ return App.state.user ? App.state.user.perfil : null; },
    podeEmitir: function(){ return ["admin_geral","admin_sede","qualidade","fiscalizacao"].indexOf(this.perfil())>=0; },
    podeResponder: function(){ return ["contratada","admin_geral"].indexOf(this.perfil())>=0; },
    podeAvaliar: function(){ return ["admin_geral","admin_sede","qualidade","fiscalizacao","gestor_contrato"].indexOf(this.perfil())>=0; },
    podeConfigurar: function(){ return ["admin_geral","admin_sede"].indexOf(this.perfil())>=0; },
    podeAdmUsuarios: function(){ return ["admin_geral","admin_sede"].indexOf(this.perfil())>=0; },
    sedesDoUsuario: function(){
      if(!App.state.user) return [];
      if(App.state.user.perfil==="admin_geral") return App.state.sedes;
      var ids = App.state.user.sedeIds||[];
      return App.state.sedes.filter(function(s){ return ids.indexOf(s.id)>=0; });
    },
    contratosVisiveis: function(){
      var todos = App.state.contratos.filter(function(c){ return c.sedeId===App.state.sedeId; });
      if(!App.state.user) return [];
      if(["admin_geral","admin_sede","qualidade","fiscalizacao","consulta"].indexOf(App.state.user.perfil)>=0) return todos;
      var ids = App.state.user.contratoIds||[];
      return todos.filter(function(c){ return ids.indexOf(c.id)>=0; });
    }
  };
})(window.App);
