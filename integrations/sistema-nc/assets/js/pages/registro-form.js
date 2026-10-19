/* ============================================================
   pages/registro-form.js — cadastro de nova NC / AC-AP
   Regra de emissão preservada integralmente: numeração automática,
   máscara de código por SEDE, cálculo de prazo (dias úteis/corridos)
   e o mesmo conjunto de 3 eventos de histórico na criação.
   Não existe hoje uma etapa independente de "rascunho" persistido —
   por isso o formulário mantém uma única ação de emissão, sem criar
   uma regra nova de rascunho.
   ============================================================ */
window.App = window.App || {};
(function(App){
  "use strict";
  var qs=App.util.qs, qsa=App.util.qsa, esc=App.util.esc, byId=App.util.byId, uniq=App.util.uniq;

  function section(num, title, desc, innerHtml, id, actionHtml){
    return '<div class="card" id="'+id+'" style="margin-bottom:var(--space-5);">'+
      '<div class="form-section-head"><span class="fs-num">'+num+'</span><div><h3>'+esc(title)+'</h3>'+
      (desc?('<p class="card-sub">'+esc(desc)+'</p>'):'')+'</div>'+(actionHtml?('<div class="fs-action">'+actionHtml+'</div>'):'')+'</div>'+
      innerHtml+
    '</div>';
  }

  async function render(mount){
    var sede = App.sedeAtual();
    if(!App.perm.podeEmitir()){
      mount.innerHTML = App.PageHeader({title:'Novo registro'})+
        '<div class="page-body">'+App.EmptyState({
          icon:'alertTriangle', title:'Sem permissão para emitir registros',
          text:'Seu perfil não pode criar novos registros de NC/AC-AP nesta SEDE.',
          actionHtml: App.Button({label:'Voltar para Registros', variant:'ghost', id:'btn-back-noperm'})
        })+'</div>';
      qs('#btn-back-noperm').onclick = function(){ App.router.go('#/ncs'); };
      return;
    }

    var contratosSede = App.perm.contratosVisiveis();
    var podeConfigurar = App.perm.podeConfigurar();
    var textosDisponiveis = App.state.textos.filter(function(t){ return t.sedeId===App.state.sedeId || t.sedeId==='GLOBAL'; });
    var categorias = uniq(textosDisponiveis.map(function(t){ return t.categoria; }));
    var classificacoes = (sede.classificacoes||[{key:'leve',label:'Leve'},{key:'media',label:'Média'},{key:'grave',label:'Grave'}]);

    var steps = [
      ['sec-1','1. Identificação'],['sec-2','2. Classificação'],['sec-3','3. Localização'],
      ['sec-4','4. Descrição'],['sec-5','5. Valores e retenção'],['sec-6','6. Prazo e ações'],
      ['sec-7','7. Evidências'],['sec-8','8. Revisão']
    ];

    mount.innerHTML =
      App.PageHeader({
        breadcrumb:'<a href="#/ncs">Registros</a> <span style="opacity:.5;">/</span> Novo registro',
        title:'Novo registro',
        sub:'SEDE '+sede.sigla+' — os textos de descrição são sugeridos pela biblioteca padronizada e podem ser ajustados.'
      })+
      '<div class="page-body">'+
        '<div class="form-steps-nav">'+steps.map(function(s){ return '<button type="button" data-target="'+s[0]+'">'+esc(s[1])+'</button>'; }).join('')+'</div>'+
        '<form id="nc-form" novalidate>'+

        section(1,'Identificação','Contrato, contratada e datas do registro.',
          '<div class="grid g3">'+
            App.FormField({id:'tipoCore', label:'Tipo de registro', type:'select',
              options: Object.keys(App.TIPOS_CORE).map(function(k){ return [k, App.tipoLabel(sede,k)+' ('+App.TIPOS_CORE[k]+')']; })})+
            App.FormField({id:'contratoId', label:'Contrato', type:'select', required:true,
              options: contratosSede.map(function(c){ return [c.id, c.numero+' — '+(c.descricaoObra||'').slice(0,40)]; })})+
            App.FormField({id:'dataEmissao', label:'Data de emissão', inputType:'date', required:true, value:new Date().toISOString().slice(0,10)})+
          '</div>'+
          '<div class="grid g3">'+
            App.FormField({id:'contratadaId', label:'Contratada', type:'select', options:[]})+
            App.FormField({id:'dataOcorrencia', label:'Data da ocorrência/execução', inputType:'date'})+
            App.FormField({id:'responsavelEmissaoNome', label:'Responsável pela emissão', required:true, value:App.state.user.nome})+
          '</div>', 'sec-1')+

        section(2,'Classificação','A categoria e o item sugerem automaticamente um texto padronizado de descrição.',
          '<div class="grid g4">'+
            App.FormField({id:'area', label:'Área', type:'select', options:(sede.areas||[]).map(function(a){ return [a,a]; })})+
            App.FormField({id:'disciplina', label:'Disciplina', type:'select', options:(sede.disciplinas||[]).map(function(a){ return [a,a]; })})+
            App.FormField({id:'categoria', label:'Categoria', type:'select', required:true, options:[['','—']].concat(categorias.map(function(c){ return [c,c]; }))})+
            App.FormField({id:'item', label:'Item', type:'select', options:[['','—']]})+
          '</div>'+
          '<div class="grid g3">'+
            App.FormField({id:'subitem', label:'Subitem', type:'select', options:[['','—']]})+
            App.FormField({id:'classificacao', label:'Classificação', type:'select', options:classificacoes.map(function(c){ return [c.key,c.label]; })})+
            App.FormField({id:'unidadeQuantidade', label:'Unidade de quantidade', type:'select', options:App.UNIDADES.map(function(u){ return [u,u]; })})+
          '</div>', 'sec-2', podeConfigurar ? App.Button({label:'Adicionar opção', icon:'plus', variant:'ghost', size:'sm', id:'btn-add-option'}) : '')+

        section(3,'Localização','Identificação do trecho, pista e extensão da ocorrência.',
          '<div class="grid g4">'+
            App.FormField({id:'rodovia', label:'Rodovia', required:true, placeholder:'ex.: BR-381'})+
            App.FormField({id:'trecho', label:'Trecho'})+
            App.FormField({id:'kmInicial', label:'Km inicial', inputType:'number', step:'0.01'})+
            App.FormField({id:'kmFinal', label:'Km final', inputType:'number', step:'0.01'})+
          '</div>'+
          '<div class="grid g4">'+
            App.FormField({id:'pistaSentido', label:'Pista / sentido', type:'select',
              options:[['Norte','Norte'],['Sul','Sul'],['Leste','Leste'],['Oeste','Oeste'],['Externa','Externa'],['Interna','Interna']]})+
            App.FormField({id:'faixa', label:'Faixa(s)'})+
            App.FormField({id:'estacaInicial', label:'Estaca inicial'})+
            App.FormField({id:'estacaFinal', label:'Estaca final'})+
          '</div>'+
          '<div class="grid g4">'+
            App.FormField({id:'comprimento', label:'Comprimento (m)', inputType:'number', step:'0.01', optionalTag:true})+
            App.FormField({id:'largura', label:'Largura (m)', inputType:'number', step:'0.01', optionalTag:true})+
            App.FormField({id:'espessura', label:'Espessura (m)', inputType:'number', step:'0.01', optionalTag:true})+
            App.FormField({id:'quantidade', label:'Quantidade', inputType:'number', step:'0.01', optionalTag:true})+
          '</div>', 'sec-3')+

        section(4,'Descrição da ocorrência','O texto é sugerido pela biblioteca padronizada a partir da categoria/item — edite conforme necessário.',
          App.FormField({id:'descricao', label:'Descrição', type:'textarea', rows:6, required:true,
            hint:'Selecione categoria, item e subitem na seção 2 para sugerir um texto padronizado.'})+
          App.FormField({id:'observacaoCampo', label:'Observação / complemento de campo', type:'textarea', rows:2, optionalTag:true})+
          App.FormField({id:'normaReferencia', label:'Norma / especificação de referência', optionalTag:true, placeholder:'ex.: DER/SP ET-DE-H00/004'}), 'sec-4')+

        section(5,'Valores e retenção','Valores estimados de impacto financeiro e proposta de retenção contratual.',
          '<div class="grid g3">'+
            App.FormField({id:'valorEstimado', label:'Valor estimado (R$)', inputType:'number', step:'0.01', optionalTag:true})+
            App.FormField({id:'valorRetencaoProposto', label:'Valor retenção proposto (R$)', inputType:'number', step:'0.01', optionalTag:true})+
            App.FormField({id:'solicitaAcAp', label:'Solicita ação corretiva/preventiva?', type:'select', options:[['sim','Sim'],['nao','Não']]})+
          '</div>', 'sec-5')+

        section(6,'Prazo e ações','O prazo de resposta é calculado a partir da data de emissão, conforme a regra de dias '+(sede.diasUteis?'úteis':'corridos')+' configurada para esta SEDE.',
          '<div class="grid g2">'+
            App.FormField({id:'prazoDias', label:'Prazo p/ resposta (dias)', inputType:'number', value: sede.prazoPadraoDias||3})+
          '</div>'+
          '<div class="prazo-preview" id="prazo-preview"></div>', 'sec-6')+

        section(7,'Evidências','Fotos e documentos comprobatórios.',
          '<div class="form-hint-card">'+App.icon('info','sm')+
            '<span>As evidências fotográficas são anexadas após a emissão do registro, na aba <b>Evidências</b> do detalhe da NC — assim é possível vincular a foto ao código já gerado.</span>'+
          '</div>', 'sec-7')+

        section(8,'Revisão','Confira os dados preenchidos antes de emitir o registro.',
          '<div class="form-hint-card">'+App.icon('checkCircle','sm')+
            '<span>Ao emitir, o sistema gera automaticamente o código do registro, protocola-o e inicia a contagem do prazo de resposta da contratada. Após emitido, o registro pode ser acompanhado pela tela de detalhe.</span>'+
          '</div>', 'sec-8')+

        '<div class="footer-actions">'+
          App.Button({label:'Cancelar', variant:'ghost', type:'button', id:'btn-cancelar'})+
          App.Button({label:'Emitir registro', variant:'primary', type:'submit'})+
        '</div>'+
        '</form>'+
      '</div>';

    qsa('.form-steps-nav button').forEach(function(b){
      b.onclick = function(){
        var el = document.getElementById(b.getAttribute('data-target'));
        if(el) el.scrollIntoView({behavior:'smooth', block:'start'});
      };
    });
    qs('#btn-cancelar').onclick = function(){ App.router.go('#/ncs'); };

    if(podeConfigurar) qs('#btn-add-option').onclick = function(){
      var bg=App.openModal('<form id="f-add-option">'+
        App.FormField({id:'option-type',label:'Lista que receberá a opção',type:'select',options:[['area','Área'],['disciplina','Disciplina'],['classificacao','Classificação']]})+
        App.FormField({id:'option-label',label:'Nova opção',required:true,placeholder:'Digite o nome'})+
        '<div class="info-box" style="margin-bottom:16px;">Categorias, itens e subitens são cadastrados junto com um texto padronizado.</div>'+
        '<div class="close-row">'+App.Button({label:'Biblioteca de textos',variant:'ghost',type:'button',id:'go-textos'})+App.Button({label:'Cancelar',variant:'ghost',type:'button',id:'option-cancel'})+App.Button({label:'Adicionar',variant:'primary',type:'submit'})+'</div></form>',{title:'Adicionar opção de classificação'});
      qs('#option-cancel',bg).onclick=function(){App.closeModal(bg);};
      qs('#go-textos',bg).onclick=function(){App.closeModal(bg);App.router.go('#/textos');};
      qs('#f-add-option',bg).onsubmit=async function(ev){
        ev.preventDefault();var type=qs('#option-type',bg).value,label=qs('#option-label',bg).value.trim();if(!label){App.setFieldError('option-label','Informe o nome da opção.');return;}
        var patch={},selectId,value=label;
        if(type==='area'){patch.areas=(sede.areas||[]).slice();if(patch.areas.indexOf(label)<0)patch.areas.push(label);selectId='area';sede.areas=patch.areas;}
        if(type==='disciplina'){patch.disciplinas=(sede.disciplinas||[]).slice();if(patch.disciplinas.indexOf(label)<0)patch.disciplinas.push(label);selectId='disciplina';sede.disciplinas=patch.disciplinas;}
        if(type==='classificacao'){value=label.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'');patch.classificacoes=(sede.classificacoes||[]).slice();if(!patch.classificacoes.some(function(x){return x.key===value;}))patch.classificacoes.push({key:value,label:label});selectId='classificacao';sede.classificacoes=patch.classificacoes;}
        await App.DB.doc('sedes/'+sede.id).update(patch);
        var select=qs('#'+selectId);if(!Array.prototype.some.call(select.options,function(o){return o.value===value;})){var option=document.createElement('option');option.value=value;option.textContent=label;select.appendChild(option);}select.value=value;
        App.closeModal(bg);App.toast('Opção adicionada e salva para esta SEDE.','success');
      };
    };

    function refreshContratadas(){
      var c = byId(contratosSede, qs('#contratoId').value);
      var ids = c ? (c.contratadaIds||[]) : [];
      var opts = App.state.contratadas.filter(function(x){ return ids.indexOf(x.id)>=0; });
      qs('#contratadaId').innerHTML = opts.map(function(o){ return '<option value="'+o.id+'">'+esc(o.razaoSocial)+'</option>'; }).join('') || '<option value="">(sem contratada vinculada)</option>';
    }
    refreshContratadas();
    qs('#contratoId').onchange = refreshContratadas;

    function refreshItens(){
      var cat = qs('#categoria').value;
      var itens = uniq(textosDisponiveis.filter(function(t){ return t.categoria===cat; }).map(function(t){ return t.item; }));
      qs('#item').innerHTML = '<option value="">—</option>'+itens.map(function(i){ return '<option value="'+esc(i)+'">'+esc(i)+'</option>'; }).join('');
      refreshSub(); suggestText();
    }
    function refreshSub(){
      var cat = qs('#categoria').value, item = qs('#item').value;
      var subs = uniq(textosDisponiveis.filter(function(t){ return t.categoria===cat && t.item===item; }).map(function(t){ return t.subitem; })).filter(Boolean);
      qs('#subitem').innerHTML = '<option value="">—</option>'+subs.map(function(s){ return '<option value="'+esc(s)+'">'+esc(s)+'</option>'; }).join('');
    }
    function suggestText(){
      var cat = qs('#categoria').value, item = qs('#item').value, sub = qs('#subitem').value;
      var match = textosDisponiveis.find(function(t){ return t.categoria===cat && t.item===item && (!sub || t.subitem===sub); });
      if(match){ qs('#descricao').value = match.texto; App.setFieldError('descricao', null); }
    }
    qs('#categoria').onchange = refreshItens;
    qs('#item').onchange = function(){ refreshSub(); suggestText(); };
    qs('#subitem').onchange = suggestText;

    function updatePrazoPreview(){
      var dataEmissao = qs('#dataEmissao').value;
      var prazoDias = Number(qs('#prazoDias').value)||sede.prazoPadraoDias||3;
      var el = qs('#prazo-preview');
      if(!dataEmissao){ el.innerHTML = ''; return; }
      var prazo = App.util.addDias(dataEmissao, prazoDias, !!sede.diasUteis);
      el.innerHTML = 'Prazo de resposta calculado: <b>'+esc(App.util.fmtDateTime(prazo))+'</b> ('+prazoDias+' dia'+(prazoDias>1?'s':'')+' '+(sede.diasUteis?'úteis':'corridos')+').';
    }
    qs('#dataEmissao').onchange = updatePrazoPreview;
    qs('#prazoDias').oninput = updatePrazoPreview;
    updatePrazoPreview();

    qs('#nc-form').onsubmit = async function(ev){
      ev.preventDefault();
      App.clearFieldErrors(qs('#nc-form'));
      var errors = [];
      function req(id, msg){ if(!qs('#'+id).value){ App.setFieldError(id, msg); errors.push(id); } }
      req('contratoId', 'Selecione o contrato.');
      req('dataEmissao', 'Informe a data de emissão.');
      req('responsavelEmissaoNome', 'Informe o responsável pela emissão.');
      req('categoria', 'Selecione a categoria.');
      req('rodovia', 'Informe a rodovia.');
      req('descricao', 'Informe (ou selecione) a descrição da ocorrência.');
      if(errors.length){
        App.toast('Revise os campos destacados antes de emitir o registro.','warn');
        var firstEl = qs('#'+errors[0]);
        if(firstEl) firstEl.closest('.card').scrollIntoView({behavior:'smooth', block:'center'});
        return;
      }

      var tipoCore = qs('#tipoCore').value;
      var ano = new Date(qs('#dataEmissao').value).getFullYear();
      var seq = await App.proximoNumero(App.state.sedeId, tipoCore, ano);
      var codigo = App.gerarCodigo(sede, tipoCore, seq, ano);
      var prazoDias = Number(qs('#prazoDias').value)||sede.prazoPadraoDias||3;
      var prazoResposta = App.util.addDias(qs('#dataEmissao').value, prazoDias, !!sede.diasUteis);
      var agora = new Date().toISOString();
      var data = {
        sedeId: App.state.sedeId, tipoCore: tipoCore,
        contratoId: qs('#contratoId').value, contratadaId: qs('#contratadaId').value||null,
        numeroSequencial: seq, ano: ano, codigoFormatado: codigo,
        dataEmissao: qs('#dataEmissao').value, dataOcorrencia: qs('#dataOcorrencia').value||null,
        responsavelEmissaoNome: qs('#responsavelEmissaoNome').value,
        area: qs('#area').value, disciplina: qs('#disciplina').value,
        categoria: qs('#categoria').value, item: qs('#item').value, subitem: qs('#subitem').value,
        classificacao: qs('#classificacao').value, unidadeQuantidade: qs('#unidadeQuantidade').value,
        rodovia: qs('#rodovia').value, trecho: qs('#trecho').value,
        kmInicial: qs('#kmInicial').value, kmFinal: qs('#kmFinal').value,
        pistaSentido: qs('#pistaSentido').value, faixa: qs('#faixa').value,
        estacaInicial: qs('#estacaInicial').value, estacaFinal: qs('#estacaFinal').value,
        comprimento: qs('#comprimento').value, largura: qs('#largura').value, espessura: qs('#espessura').value, quantidade: qs('#quantidade').value,
        descricao: qs('#descricao').value, observacaoCampo: qs('#observacaoCampo').value, normaReferencia: qs('#normaReferencia').value,
        valorEstimado: qs('#valorEstimado').value||null, valorRetencaoProposto: qs('#valorRetencaoProposto').value||null, valorRetencaoEfetivo:null,
        prazoResposta: prazoResposta, solicitaAcAp: qs('#solicitaAcAp').value==='sim',
        statusAtual: 'aguardando_resposta',
        dataEncerramento: null, anexos: [],
        historico: [
          {dataHora:agora, usuarioNome:App.state.user.nome, statusAnterior:null, statusNovo:'emitida', comentario:'Registro emitido.'},
          {dataHora:agora, usuarioNome:App.state.user.nome, statusAnterior:'emitida', statusNovo:'protocolada', comentario:'Protocolado automaticamente.'},
          {dataHora:agora, usuarioNome:App.state.user.nome, statusAnterior:'protocolada', statusNovo:'aguardando_resposta', comentario:'Aguardando resposta da contratada até '+App.util.fmtDateTime(prazoResposta)+'.'}
        ],
        respostaContratada:null, avaliacaoConcessionaria:null
      };
      var ref = await App.DB.collection('ncs').add(data);
      App.toast('Registro '+codigo+' emitido com sucesso.','success');
      App.router.go('#/ncs/'+ref.id);
    };
  }

  App.pages = App.pages || {};
  App.pages.registroForm = { render:render };
})(window.App);
