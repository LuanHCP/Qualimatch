/* ============================================================
   pages/configuracao.js — configuração da SEDE
   Todos os campos e o patch salvo em "sedes/{id}" são exatamente
   os mesmos da versão anterior — só a organização visual é nova.
   ============================================================ */
window.App = window.App || {};
(function(App){
  "use strict";
  var qs=App.util.qs, esc=App.util.esc;

  function section(title, desc, innerHtml, id){
    return '<div class="card" style="margin-bottom:var(--space-5);" id="'+id+'">'+
      '<div class="card-section-title" style="margin-top:0;">'+esc(title)+'</div>'+
      (desc?('<p class="card-sub" style="margin:-6px 0 16px;">'+esc(desc)+'</p>'):'')+
      innerHtml+
    '</div>';
  }

  async function render(mount){
    if(!App.perm.podeConfigurar()){
      mount.innerHTML = App.PageHeader({title:'Configuração da SEDE'})+
        '<div class="page-body">'+App.EmptyState({icon:'settings', title:'Sem permissão', text:'Apenas Administrador geral ou Administrador da SEDE podem alterar esta configuração.'})+'</div>';
      return;
    }
    var sede = App.sedeAtual();

    mount.innerHTML =
      App.PageHeader({
        title:'Configuração da SEDE — '+sede.sigla,
        sub:'Identidade, nomenclatura, regras e listas configuráveis. Nada aqui é fixado em código.'
      })+
      '<div class="page-body"><form id="f-config">'+

        section('Identidade','Como a SEDE se apresenta no sistema (sidebar, PDFs e telas).',
          '<div class="grid g4">'+
            App.FormField({id:'c-sigla', label:'Sigla', required:true, value:sede.sigla})+
            App.FormField({id:'c-nome', label:'Nome', required:true, value:sede.nome})+
            App.FormField({id:'c-razao', label:'Razão social', optionalTag:true, value:sede.razaoSocial})+
            App.FormField({id:'c-logoletra', label:'Sigla do selo (2-3 letras)', value:sede.logoLetra})+
          '</div>'+
          '<div class="grid g2">'+
            App.FormField({id:'c-cor1', label:'Cor institucional primária', inputType:'color', value:sede.corPrimaria||'#2e6c8e'})+
            App.FormField({id:'c-cor2', label:'Cor institucional secundária', inputType:'color', value:sede.corSecundaria||'#c8791f'})+
          '</div>'+
          '<div class="config-preview-row" id="config-preview"></div>', 'cfg-identidade')+

        section('Nomenclatura e numeração','Como o sistema chama e codifica cada tipo de registro nesta SEDE.',
          '<div class="grid g3">'+
            App.FormField({id:'c-nom-nc', label:'Nome usado para "Não conformidade"', value:(sede.nomenclatura&&sede.nomenclatura.NC)||'RNC'})+
            App.FormField({id:'c-nom-ac', label:'Nome usado para "Ação corretiva/preventiva"', value:(sede.nomenclatura&&sede.nomenclatura.AC)||'RACP'})+
            App.FormField({id:'c-mascara', label:'Máscara do código', hint:'Tokens disponíveis: {SIGLA} {TIPO} {SEQ} {ANO}', value:sede.mascaraNumeracao||'{SIGLA}_{TIPO}_{SEQ}_{ANO}'})+
          '</div>', 'cfg-nomenclatura')+

        section('Prazos e regras','Como os prazos de resposta são contados e o que acontece quando vencem.',
          '<div class="grid g3">'+
            App.FormField({id:'c-prazo', label:'Prazo padrão de resposta (dias)', inputType:'number', value:sede.prazoPadraoDias||3})+
            App.FormField({id:'c-diasuteis', label:'Contagem de prazo', type:'select', value: sede.diasUteis?'uteis':'corridos',
              options:[['uteis','Dias úteis'],['corridos','Dias corridos']]})+
            App.FormField({id:'c-autoenc', label:'Encerrar automaticamente com retenção quando vencido?', type:'select', value: sede.encerramentoAutomaticoComDesconto?'sim':'nao',
              options:[['sim','Sim'],['nao','Não']]})+
          '</div>', 'cfg-prazos')+

        section('Listas configuráveis','Opções que aparecem nos formulários desta SEDE (uma por linha).',
          '<div class="grid g2">'+
            App.FormField({id:'c-areas', label:'Áreas', type:'textarea', rows:4, value:(sede.areas||[]).join('\n')})+
            App.FormField({id:'c-disciplinas', label:'Disciplinas', type:'textarea', rows:4, value:(sede.disciplinas||[]).join('\n')})+
          '</div>'+
          App.FormField({id:'c-classif', label:'Classificações de gravidade', hint:'Formato: chave|rótulo — uma por linha.', type:'textarea', rows:3,
            value:(sede.classificacoes||[]).map(function(c){ return c.key+'|'+c.label; }).join('\n')}), 'cfg-listas')+

        '<div class="footer-actions">'+
          App.Button({label:'Cancelar', variant:'ghost', type:'button', id:'cfg-cancelar'})+
          App.Button({label:'Salvar configuração', variant:'primary', type:'submit'})+
        '</div>'+
      '</form></div>';

    function updatePreview(){
      var cor1 = qs('#c-cor1').value, cor2 = qs('#c-cor2').value;
      var letra = qs('#c-logoletra').value || sede.logoLetra || '?';
      qs('#config-preview').innerHTML =
        '<div style="display:flex;align-items:center;gap:10px;"><div class="sede-logo" style="background:'+cor1+';">'+esc(letra)+'</div><div><div class="kv-label">Primária</div><div class="kv-value mono">'+esc(cor1)+'</div></div></div>'+
        '<div style="display:flex;align-items:center;gap:10px;"><div class="sede-logo" style="background:'+cor2+';">'+esc(letra)+'</div><div><div class="kv-label">Secundária</div><div class="kv-value mono">'+esc(cor2)+'</div></div></div>';
    }
    qs('#c-cor1').oninput = updatePreview;
    qs('#c-cor2').oninput = updatePreview;
    qs('#c-logoletra').oninput = updatePreview;
    updatePreview();

    qs('#cfg-cancelar').onclick = function(){ App.router.render(); };
    qs('#f-config').onsubmit = async function(ev){
      ev.preventDefault();
      var patch = {
        sigla:qs('#c-sigla').value, nome:qs('#c-nome').value, razaoSocial:qs('#c-razao').value, logoLetra:qs('#c-logoletra').value,
        corPrimaria:qs('#c-cor1').value, corSecundaria:qs('#c-cor2').value,
        nomenclatura:{NC:qs('#c-nom-nc').value, AC:qs('#c-nom-ac').value},
        mascaraNumeracao:qs('#c-mascara').value,
        prazoPadraoDias:Number(qs('#c-prazo').value)||3,
        diasUteis: qs('#c-diasuteis').value==='uteis',
        encerramentoAutomaticoComDesconto: qs('#c-autoenc').value==='sim',
        areas: qs('#c-areas').value.split('\n').map(function(s){ return s.trim(); }).filter(Boolean),
        disciplinas: qs('#c-disciplinas').value.split('\n').map(function(s){ return s.trim(); }).filter(Boolean),
        classificacoes: qs('#c-classif').value.split('\n').map(function(l){ var p=l.split('|'); return p[0]?{key:p[0].trim(), label:(p[1]||p[0]).trim()}:null; }).filter(Boolean)
      };
      await App.DB.doc('sedes/'+sede.id).update(patch);
      await App.refreshAll();
      App.toast('Configuração da SEDE atualizada.','success');
      App.router.render();
    };
  }

  App.pages = App.pages || {};
  App.pages.configuracao = { render:render };
})(window.App);
