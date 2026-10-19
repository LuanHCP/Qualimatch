/* ============================================================
   pages/registro-detail.js — detalhe de uma NC/AC-AP
   Fluxo de status, regras de prazo/retenção e estrutura de dados
   preservados exatamente como na versão anterior; apenas a camada
   visual (abas, resumo, stepper, timeline, galeria) é nova.
   ============================================================ */
window.App = window.App || {};
(function(App){
  "use strict";
  var qs=App.util.qs, qsa=App.util.qsa, esc=App.util.esc, byId=App.util.byId, fmtDate=App.util.fmtDate,
      fmtDateTime=App.util.fmtDateTime, fmtMoney=App.util.fmtMoney;

  var DISPOSICAO_LABEL = {concessao:'Concessão', reparo:'Reparo', retrabalho:'Retrabalho', reprovacao:'Reprovação'};
  function dispLabel(v){ return DISPOSICAO_LABEL[v] || v || '—'; }

  function kv(label, value){
    return '<div class="kv-item"><div class="kv-label">'+esc(label)+'</div><div class="kv-value">'+
      (value===undefined||value===null||value===''?'—':esc(value))+'</div></div>';
  }
  function kvHtml(label, html){
    return '<div class="kv-item"><div class="kv-label">'+esc(label)+'</div><div class="kv-value" style="font-weight:500;">'+(html||'—')+'</div></div>';
  }

  function downscaleImage(file, maxDim, quality){
    return new Promise(function(resolve){
      var img = new Image();
      var reader = new FileReader();
      reader.onload = function(e){
        img.onload = function(){
          var scale = Math.min(1, maxDim/Math.max(img.width,img.height));
          var w = Math.round(img.width*scale), h = Math.round(img.height*scale);
          var canvas = document.createElement('canvas'); canvas.width=w; canvas.height=h;
          canvas.getContext('2d').drawImage(img,0,0,w,h);
          resolve(canvas.toDataURL('image/jpeg', quality));
        };
        img.src = e.target.result;
      };
      reader.readAsDataURL(file);
    });
  }

  /* ---------------- aba: visão geral ---------------- */
  function tabGeral(nc, sede){
    var itemSub = [nc.item, nc.subitem].filter(Boolean).join(' / ');
    var kmRange = (nc.kmInicial || nc.kmFinal) ? ((nc.kmInicial||'—')+' → '+(nc.kmFinal||'—')) : '';
    var estacaRange = [nc.estacaInicial, nc.estacaFinal].filter(Boolean).join(' → ');
    var temMedidas = [nc.comprimento, nc.largura, nc.espessura].some(Boolean);
    var medidas = temMedidas ? [nc.comprimento,nc.largura,nc.espessura].map(function(v){return v||'—';}).join(' × ') : '';

    return '<div class="card">'+
      '<div class="card-section-title">Identificação</div><div class="grid g4">'+
        kv('Data de emissão', fmtDate(nc.dataEmissao))+
        kv('Data de ocorrência/execução', fmtDate(nc.dataOcorrencia))+
        kv('Responsável pela emissão', nc.responsavelEmissaoNome)+
        kv('Prazo de resposta', fmtDateTime(nc.prazoResposta))+
      '</div>'+
      '<div class="card-section-title">Classificação</div><div class="grid g4">'+
        kv('Área', nc.area)+kv('Disciplina', nc.disciplina)+kv('Categoria', nc.categoria)+kv('Item / Subitem', itemSub)+
        kv('Classificação', nc.classificacao)+kv('Solicita AC/AP', nc.solicitaAcAp?'Sim':'Não')+
      '</div>'+
      '<div class="card-section-title">Localização</div><div class="grid g4">'+
        kv('Rodovia', nc.rodovia)+kv('Trecho', nc.trecho)+kv('Pista / sentido', nc.pistaSentido)+kv('Faixa', nc.faixa)+
        kv('Km inicial → final', kmRange)+kv('Estaca inicial → final', estacaRange)+
        kv('Comprimento × Largura × Espessura (m)', medidas)+
        kv('Quantidade', nc.quantidade ? (nc.quantidade+' '+(nc.unidadeQuantidade||'')) : '')+
      '</div>'+
      '<div class="card-section-title">Descrição</div>'+
      '<div class="nc-desc-box">'+esc(nc.descricao||'—').replace(/\n/g,'<br>')+'</div>'+
      (nc.observacaoCampo ? ('<div class="grid g4" style="margin-top:12px;">'+kv('Observação de campo', nc.observacaoCampo)+'</div>') : '')+
      (nc.normaReferencia ? ('<div class="grid g4" style="margin-top:12px;">'+kv('Norma / especificação de referência', nc.normaReferencia)+'</div>') : '')+
      '<div class="card-section-title">Valores</div><div class="grid g3">'+
        kv('Valor estimado', fmtMoney(nc.valorEstimado))+
        kv('Retenção proposta', fmtMoney(nc.valorRetencaoProposto))+
        kv('Retenção efetiva', fmtMoney(nc.valorRetencaoEfetivo))+
      '</div>'+
      (App.isVencido(nc) && sede.encerramentoAutomaticoComDesconto ?
        '<div style="margin-top:var(--space-5);padding-top:var(--space-4);border-top:1px solid var(--border);">'+
          App.Button({label:'Encerrar com retenção proposta (regra da SEDE)', variant:'danger', id:'btn-encerrar-vencido'})+
        '</div>' : '')+
    '</div>';
  }
  function bindGeral(nc){
    var btn = qs('#btn-encerrar-vencido');
    if(!btn) return;
    btn.onclick = async function(){
      var ok = await App.confirmDialog({
        title:'Encerrar registro com retenção proposta?',
        message:'O prazo de resposta está vencido. Esta ação aplica a retenção proposta ('+fmtMoney(nc.valorRetencaoProposto)+') como valor efetivo e encerra o registro, conforme a regra configurada para esta SEDE.',
        tone:'danger', confirmLabel:'Encerrar registro'
      });
      if(!ok) return;
      var hist = (nc.historico||[]).concat([{dataHora:new Date().toISOString(), usuarioNome:App.state.user.nome, statusAnterior:nc.statusAtual, statusNovo:'encerrada', comentario:'Encerrado automaticamente por prazo vencido, com aplicação da retenção proposta (regra da SEDE).'}]);
      await App.DB.doc('ncs/'+nc.id).update({statusAtual:'encerrada', dataEncerramento:new Date().toISOString(), valorRetencaoEfetivo:nc.valorRetencaoProposto, historico:hist});
      App.toast('Registro encerrado com a retenção proposta.', 'success');
      App.router.render();
    };
  }

  function modalEditarRegistro(nc, sede){
    var contratos=App.state.contratos.filter(function(c){return c.sedeId===nc.sedeId;});
    var bg=App.openModal('<form id="form-edit-nc">'+
      '<div class="grid g2">'+
        App.FormField({id:'e-contrato',label:'Contrato',type:'select',value:nc.contratoId||'',options:contratos.map(function(c){return[c.id,c.numero];})})+
        App.FormField({id:'e-contratada',label:'Contratada',type:'select',value:nc.contratadaId||'',options:[['','—']].concat(App.state.contratadas.map(function(c){return[c.id,c.razaoSocial];}))})+
        App.FormField({id:'e-area',label:'Área',value:nc.area||''})+App.FormField({id:'e-disciplina',label:'Disciplina',value:nc.disciplina||''})+
        App.FormField({id:'e-categoria',label:'Categoria',required:true,value:nc.categoria||''})+App.FormField({id:'e-item',label:'Item',value:nc.item||''})+
        App.FormField({id:'e-subitem',label:'Subitem',value:nc.subitem||''})+App.FormField({id:'e-classificacao',label:'Classificação',type:'select',value:nc.classificacao||'',options:(sede.classificacoes||[]).map(function(c){return[c.key,c.label];})})+
        App.FormField({id:'e-rodovia',label:'Rodovia',required:true,value:nc.rodovia||''})+App.FormField({id:'e-trecho',label:'Trecho',value:nc.trecho||''})+
        App.FormField({id:'e-kmi',label:'Km inicial',inputType:'number',step:'0.01',value:nc.kmInicial||''})+App.FormField({id:'e-kmf',label:'Km final',inputType:'number',step:'0.01',value:nc.kmFinal||''})+
        App.FormField({id:'e-valor',label:'Retenção proposta (R$)',inputType:'number',step:'0.01',value:nc.valorRetencaoProposto||''})+
      '</div>'+App.FormField({id:'e-descricao',label:'Descrição',type:'textarea',rows:6,required:true,value:nc.descricao||''})+
      '<div class="close-row">'+App.Button({label:'Cancelar',variant:'ghost',type:'button',id:'edit-cancel'})+App.Button({label:'Salvar alterações',variant:'primary',type:'submit'})+'</div></form>',{title:'Editar registro',large:true});
    qs('#edit-cancel',bg).onclick=function(){App.closeModal(bg);};
    qs('#form-edit-nc',bg).onsubmit=async function(ev){ev.preventDefault();var descricao=qs('#e-descricao',bg).value.trim(),categoria=qs('#e-categoria',bg).value.trim(),rodovia=qs('#e-rodovia',bg).value.trim();if(!descricao||!categoria||!rodovia){App.toast('Preencha categoria, rodovia e descrição.','warn');return;}await App.DB.doc('ncs/'+nc.id).update({contratoId:qs('#e-contrato',bg).value,contratadaId:qs('#e-contratada',bg).value||null,area:qs('#e-area',bg).value,disciplina:qs('#e-disciplina',bg).value,categoria:categoria,item:qs('#e-item',bg).value,subitem:qs('#e-subitem',bg).value,classificacao:qs('#e-classificacao',bg).value,rodovia:rodovia,trecho:qs('#e-trecho',bg).value,kmInicial:qs('#e-kmi',bg).value,kmFinal:qs('#e-kmf',bg).value,valorRetencaoProposto:qs('#e-valor',bg).value||null,descricao:descricao});App.closeModal(bg);App.toast('Registro atualizado.','success');App.router.render();};
  }

  /* ---------------- aba: resposta da contratada ---------------- */
  function tabResposta(nc){
    var r = nc.respostaContratada;
    if(r){
      return '<div class="card"><div class="grid g2">'+
        kvHtml('Análise da causa', esc(r.analiseCausa||'—').replace(/\n/g,'<br>'))+
        kvHtml('Correção imediata', esc(r.correcaoImediata||'—').replace(/\n/g,'<br>'))+
        kvHtml('Ação corretiva', esc(r.acaoCorretiva||'—').replace(/\n/g,'<br>'))+
        kvHtml('Ação preventiva', esc(r.acaoPreventiva||'—').replace(/\n/g,'<br>'))+
        kvHtml('Plano de ação', esc(r.planoDeAcao||'—').replace(/\n/g,'<br>'))+
        kv('Responsável', r.responsavel)+
        kv('Prazo de implementação', fmtDate(r.prazoImplementacao))+
        kv('Disposição solicitada', dispLabel(r.disposicaoSolicitada))+
        kvHtml('Conclusão', esc(r.conclusao||'—').replace(/\n/g,'<br>'))+
      '</div></div>';
    }
    var fechado = App.STATUS[nc.statusAtual].group==='encerrado';
    if(!App.perm.podeResponder() || fechado){
      return '<div class="card">'+App.EmptyState({
        icon:'fileText',
        title: fechado ? 'Registro encerrado' : 'Aguardando resposta da contratada',
        text: fechado ? 'Este registro foi encerrado sem pendência de resposta.' : 'A resposta poderá ser registrada pelo perfil Contratada vinculado a este contrato.'
      })+'</div>';
    }
    return '<div class="card"><h3 style="margin-bottom:4px;">Formulário de resposta da contratada</h3>'+
      '<p class="card-sub" style="margin-bottom:18px;">Preencha a análise da causa, a ação proposta e a disposição solicitada.</p>'+
      '<form id="form-resposta">'+
      '<div class="grid g2">'+
        App.FormField({id:'r-causa', label:'Análise da causa', type:'textarea', rows:3})+
        App.FormField({id:'r-correcao', label:'Correção imediata', type:'textarea', rows:3})+
        App.FormField({id:'r-corretiva', label:'Ação corretiva', type:'textarea', rows:3})+
        App.FormField({id:'r-preventiva', label:'Ação preventiva', type:'textarea', rows:3})+
        App.FormField({id:'r-plano', label:'Plano de ação', type:'textarea', rows:3})+
        App.FormField({id:'r-conclusao', label:'Conclusão', type:'textarea', rows:3})+
      '</div><div class="grid g3">'+
        App.FormField({id:'r-responsavel', label:'Responsável pela implementação', required:true})+
        App.FormField({id:'r-prazo', label:'Prazo de implementação', inputType:'date', required:true})+
        App.FormField({id:'r-disposicao', label:'Disposição solicitada', type:'select', required:true,
          options:[['concessao','Concessão'],['reparo','Reparo'],['retrabalho','Retrabalho'],['reprovacao','Reprovação']]})+
      '</div>'+
      '<div style="margin-top:6px;">'+App.Button({label:'Enviar resposta', variant:'primary', type:'submit'})+'</div>'+
    '</form></div>';
  }
  function bindResposta(nc){
    var f = qs('#form-resposta');
    if(!f) return;
    f.onsubmit = async function(ev){
      ev.preventDefault();
      App.clearFieldErrors(f);
      var responsavel = qs('#r-responsavel').value.trim();
      var prazo = qs('#r-prazo').value;
      var disposicao = qs('#r-disposicao').value;
      var hasError = false;
      if(!responsavel){ App.setFieldError('r-responsavel','Informe o responsável pela implementação.'); hasError=true; }
      if(!prazo){ App.setFieldError('r-prazo','Informe o prazo de implementação.'); hasError=true; }
      if(hasError){ App.toast('Revise os campos destacados antes de enviar.','warn'); return; }
      var resp = {
        analiseCausa:qs('#r-causa').value, correcaoImediata:qs('#r-correcao').value, acaoCorretiva:qs('#r-corretiva').value,
        acaoPreventiva:qs('#r-preventiva').value, planoDeAcao:qs('#r-plano').value, conclusao:qs('#r-conclusao').value,
        responsavel:responsavel, prazoImplementacao:prazo, disposicaoSolicitada:disposicao
      };
      var agora = new Date().toISOString();
      var hist = (nc.historico||[]).concat([
        {dataHora:agora, usuarioNome:App.state.user.nome, statusAnterior:nc.statusAtual, statusNovo:'respondida', comentario:'Contratada enviou resposta e disposição: '+dispLabel(disposicao)+'.'},
        {dataHora:agora, usuarioNome:App.state.user.nome, statusAnterior:'respondida', statusNovo:'em_analise', comentario:'Aguardando análise da concessionária.'}
      ]);
      await App.DB.doc('ncs/'+nc.id).update({respostaContratada:resp, statusAtual:'em_analise', historico:hist});
      App.toast('Resposta enviada. Aguardando análise da concessionária.','success');
      App.router.go('#/ncs/'+nc.id+'/analise');
    };
  }

  /* ---------------- aba: análise ---------------- */
  function tabAnalise(nc){
    var a = nc.avaliacaoConcessionaria;
    if(a && App.STATUS[nc.statusAtual].group==='encerrado'){
      return '<div class="card"><div class="grid g2">'+
        kvHtml('Parecer técnico', esc(a.parecerTecnico||'—').replace(/\n/g,'<br>'))+
        kv('Disposição', a.disposicaoStatus==='aprovada'?'Aprovada':a.disposicaoStatus==='recusada'?'Recusada':a.disposicaoStatus)+
        kv('Resultado de eficácia', a.resultadoEficacia==='eficaz'?'Eficaz':a.resultadoEficacia==='nao_eficaz'?'Não eficaz':a.resultadoEficacia)+
        kv('Valor retido (final)', fmtMoney(a.valorRetidoFinal))+
        kv('Data de encerramento', fmtDate(nc.dataEncerramento))+
      '</div></div>';
    }
    if(!App.perm.podeAvaliar()){
      return '<div class="card">'+App.EmptyState({icon:'checkCircle', title:'Sem permissão para analisar', text:'Os perfis Qualidade, Fiscalização/Engenharia ou Gestor do contrato podem registrar a análise técnica.'})+'</div>';
    }
    if(nc.statusAtual==='em_analise'){
      return '<div class="card"><h3 style="margin-bottom:4px;">Análise da disposição proposta pela contratada</h3>'+
        (nc.respostaContratada ? ('<p class="card-sub" style="margin-bottom:16px;">Disposição solicitada: <b>'+esc(dispLabel(nc.respostaContratada.disposicaoSolicitada))+'</b></p>') : '<p class="card-sub" style="margin-bottom:16px;">Sem resposta registrada ainda.</p>')+
        '<form id="form-analise">'+App.FormField({id:'a-parecer', label:'Parecer técnico', type:'textarea', rows:3})+
        '<div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap;">'+
          App.Button({label:'Aprovar disposição', variant:'primary', type:'submit', attrs:' data-decisao="aprovada"'})+
          App.Button({label:'Recusar / solicitar nova resposta', variant:'danger', type:'submit', attrs:' data-decisao="recusada"'})+
        '</div></form></div>';
    }
    if(nc.statusAtual==='em_execucao' || nc.statusAtual==='disposicao_aprovada'){
      return '<div class="card"><h3 style="margin-bottom:4px;">Execução</h3>'+
        '<p class="card-sub" style="margin-bottom:14px;">Disposição aprovada. Quando a ação corretiva/preventiva estiver concluída em campo, solicite a verificação de eficácia.</p>'+
        App.Button({label:'Solicitar verificação de eficácia', variant:'primary', id:'btn-solicitar-verificacao'})+
      '</div>';
    }
    if(nc.statusAtual==='aguardando_verificacao'){
      return '<div class="card"><h3 style="margin-bottom:4px;">Verificação de eficácia</h3><form id="form-eficacia">'+
        App.FormField({id:'e-parecer', label:'Parecer técnico da verificação', type:'textarea', rows:3})+
        '<div class="grid g2">'+
          App.FormField({id:'e-valor', label:'Valor efetivamente retido (R$)', inputType:'number'})+
          App.FormField({id:'e-resultado', label:'Resultado', type:'select', options:[['eficaz','Eficaz'],['nao_eficaz','Não eficaz']]})+
        '</div>'+
        '<div style="margin-top:6px;">'+App.Button({label:'Registrar decisão final', variant:'primary', type:'submit'})+'</div>'+
      '</form></div>';
    }
    return '<div class="card">'+App.EmptyState({icon:'clock', title:'Nada a analisar neste momento', text:'Status atual: '+App.STATUS[nc.statusAtual].label+'.'})+'</div>';
  }
  function bindAnalise(nc){
    var fa = qs('#form-analise');
    if(fa){
      qsa('button[type=submit]', fa).forEach(function(btn){
        btn.onclick = async function(ev){
          ev.preventDefault();
          var decisao = btn.getAttribute('data-decisao');
          var parecer = qs('#a-parecer').value;
          var novo = decisao==='aprovada' ? 'em_execucao' : 'aguardando_resposta';
          var agora = new Date().toISOString();
          var hist = (nc.historico||[]).concat([{dataHora:agora, usuarioNome:App.state.user.nome, statusAnterior:nc.statusAtual, statusNovo:(decisao==='aprovada'?'disposicao_aprovada':'disposicao_recusada'), comentario:parecer||('Disposição '+decisao+'.')}]);
          if(decisao==='aprovada') hist.push({dataHora:agora, usuarioNome:App.state.user.nome, statusAnterior:'disposicao_aprovada', statusNovo:'em_execucao', comentario:'Ação corretiva/preventiva liberada para execução.'});
          var avaliacao = Object.assign({}, nc.avaliacaoConcessionaria, {parecerTecnico:parecer, disposicaoStatus:decisao});
          await App.DB.doc('ncs/'+nc.id).update({statusAtual:novo, historico:hist, avaliacaoConcessionaria:avaliacao});
          App.toast(decisao==='aprovada' ? 'Disposição aprovada. Liberado para execução.' : 'Disposição recusada — aguardando nova resposta da contratada.', decisao==='aprovada'?'success':'warn');
          App.router.render();
        };
      });
    }
    var bv = qs('#btn-solicitar-verificacao');
    if(bv) bv.onclick = async function(){
      var hist = (nc.historico||[]).concat([{dataHora:new Date().toISOString(), usuarioNome:App.state.user.nome, statusAnterior:nc.statusAtual, statusNovo:'aguardando_verificacao', comentario:'Verificação de eficácia solicitada.'}]);
      await App.DB.doc('ncs/'+nc.id).update({statusAtual:'aguardando_verificacao', historico:hist});
      App.toast('Verificação de eficácia solicitada.','success');
      App.router.render();
    };
    var fe = qs('#form-eficacia');
    if(fe) fe.onsubmit = async function(ev){
      ev.preventDefault();
      var resultado = qs('#e-resultado').value;
      var valor = qs('#e-valor').value;
      var parecer = qs('#e-parecer').value;
      var avaliacao = Object.assign({}, nc.avaliacaoConcessionaria, {resultadoEficacia:resultado, valorRetidoFinal:valor, parecerTecnico:((nc.avaliacaoConcessionaria&&nc.avaliacaoConcessionaria.parecerTecnico)||'')+' | '+parecer});
      var novoStatus = resultado==='eficaz' ? 'encerrada' : 'em_execucao';
      var agora = new Date().toISOString();
      var hist = (nc.historico||[]).concat([{dataHora:agora, usuarioNome:App.state.user.nome, statusAnterior:nc.statusAtual, statusNovo:resultado, comentario:parecer}]);
      if(resultado==='eficaz') hist.push({dataHora:agora, usuarioNome:App.state.user.nome, statusAnterior:'eficaz', statusNovo:'encerrada', comentario:'Registro encerrado.'});
      var patch = {statusAtual:novoStatus, historico:hist, avaliacaoConcessionaria:avaliacao, valorRetencaoEfetivo:valor||nc.valorRetencaoEfetivo};
      if(novoStatus==='encerrada') patch.dataEncerramento = agora;
      await App.DB.doc('ncs/'+nc.id).update(patch);
      App.toast(novoStatus==='encerrada' ? 'Ação eficaz — registro encerrado.' : 'Registrado como não eficaz — retorna para execução.', novoStatus==='encerrada'?'success':'warn');
      App.router.render();
    };
  }

  /* ---------------- aba: evidências ---------------- */
  function tabEvidencias(nc){
    var anexos = nc.anexos||[];
    return '<div class="card"><h3 style="margin-bottom:4px;">Evidências fotográficas e documentos</h3>'+
      '<p class="card-sub" style="margin-bottom:16px;">Fotos são reduzidas a miniatura para armazenamento neste protótipo.</p>'+
      App.EvidenceGallery(anexos)+
      (anexos.length ? ('<div style="margin-top:14px;">'+App.Button({label:'Baixar evidências (PDF)', icon:'download', variant:'ghost', size:'sm', id:'btn-anexos-pdf'})+'</div>') : '')+
      ((App.perm.podeEmitir()||App.perm.podeAvaliar()) ?
        '<div class="card-section-title">Adicionar evidência</div>'+
        '<form id="form-anexo" class="grid g4" style="align-items:end;">'+
          '<div class="field" style="grid-column:span 2;"><label class="field-label" for="anexo-file">Arquivo (imagem)</label><input type="file" id="anexo-file" accept="image/*"></div>'+
          App.FormField({id:'anexo-legenda', label:'Legenda'})+
          App.FormField({id:'anexo-data', label:'Data da foto', inputType:'date'})+
          App.FormField({id:'anexo-km', label:'Km'})+
          App.FormField({id:'anexo-pista', label:'Pista'})+
          App.FormField({id:'anexo-faixa', label:'Faixa'})+
          '<div class="field">'+App.Button({label:'Adicionar evidência', variant:'primary', size:'sm', type:'submit'})+'</div>'+
        '</form>'
      : '')+
    '</div>';
  }
  function bindEvidencias(nc){
    qsa('.evidence-card').forEach(function(card){
      card.onclick = function(){
        var idx = parseInt(card.getAttribute('data-idx'),10);
        var a = (nc.anexos||[])[idx];
        if(a) App.openLightbox(a);
      };
    });
    var f = qs('#form-anexo');
    if(f) f.onsubmit = async function(ev){
      ev.preventDefault();
      var fileInput = qs('#anexo-file');
      var thumb = null;
      if(fileInput.files[0]) thumb = await downscaleImage(fileInput.files[0], 360, 0.6);
      var anexo = {
        id: App.util.uid(), tipo:'foto', nomeArquivo: fileInput.files[0] ? fileInput.files[0].name : null,
        legenda: qs('#anexo-legenda').value, dataFoto: qs('#anexo-data').value,
        km: qs('#anexo-km').value, pista: qs('#anexo-pista').value, faixa: qs('#anexo-faixa').value,
        thumb: thumb
      };
      var anexos = (nc.anexos||[]).concat([anexo]);
      await App.DB.doc('ncs/'+nc.id).update({anexos:anexos});
      App.toast('Evidência adicionada.','success');
      App.router.render();
    };
    var pdfBtn = qs('#btn-anexos-pdf');
    if(pdfBtn) pdfBtn.onclick = function(){ App.pdf.anexos(nc); };
  }

  /* ---------------- página ---------------- */
  var TABS = [
    {key:'geral', label:'Visão geral'},
    {key:'resposta', label:'Resposta da contratada'},
    {key:'analise', label:'Análise'},
    {key:'evidencias', label:'Evidências'},
    {key:'historico', label:'Histórico'}
  ];

  async function render(mount, id, sub){
    var nc = await App.loadNc(id);
    if(!nc){
      mount.innerHTML = App.PageHeader({title:'Registro não encontrado'})+
        '<div class="page-body">'+App.EmptyState({
          icon:'alertTriangle', title:'Registro não encontrado',
          text:'O registro pode ter sido removido ou o link está incorreto.',
          actionHtml: App.Button({label:'Voltar para Registros', variant:'primary', id:'btn-back-notfound'})
        })+'</div>';
      qs('#btn-back-notfound').onclick = function(){ App.router.go('#/ncs'); };
      return;
    }
    var sede = byId(App.state.sedes, nc.sedeId) || App.sedeAtual();
    var contrato = byId(App.state.contratos, nc.contratoId);
    var contratada = byId(App.state.contratadas, nc.contratadaId);
    var tab = sub || 'geral';
    var vencido = App.isVencido(nc);
    var podeEditar = App.perm.podeEmitir() || App.perm.podeAvaliar();
    var podeExcluir = App.perm.podeConfigurar();

    mount.innerHTML =
      App.PageHeader({
        breadcrumb:'<a href="#/ncs">Registros</a> <span style="opacity:.5;">/</span> '+esc(nc.codigoFormatado),
        title: nc.codigoFormatado,
        sub: App.tipoLabel(sede, nc.tipoCore)+' · '+(contrato?contrato.numero:'—')+' · '+(contratada?contratada.razaoSocial:'—'),
        actionsHtml: (podeEditar?App.Button({label:'Editar registro', icon:'fileText', variant:'ghost', id:'btn-edit-nc'}):'')+App.Button({label:'Gerar PDF', icon:'download', variant:'ghost', id:'btn-pdf'})+(podeExcluir?App.Button({label:'Excluir registro', icon:'x', variant:'danger', id:'btn-delete-nc'}):'')
      })+
      '<div class="page-body">'+
        (vencido ? ('<div class="alert-banner danger">'+App.icon('alertTriangle')+
          '<div><strong>RESPOSTA VENCIDA</strong>Prazo encerrado em '+fmtDateTime(nc.prazoResposta)+
          (sede.encerramentoAutomaticoComDesconto ? ' — a regra desta SEDE permite encerrar aplicando a retenção proposta.' : '')+
          '</div></div>') : '')+
        '<div class="card" style="margin-top:14px;">'+
          '<div class="nc-summary">'+
            '<div class="ns-item"><div class="ns-label">Código</div><div class="ns-value mono">'+esc(nc.codigoFormatado)+'</div></div>'+
            '<div class="ns-item"><div class="ns-label">Status</div><div class="ns-value">'+App.StatusBadge(nc.statusAtual)+'</div></div>'+
            '<div class="ns-item"><div class="ns-label">Categoria</div><div class="ns-value">'+esc(nc.categoria||'—')+'</div></div>'+
            '<div class="ns-item"><div class="ns-label">Contratada</div><div class="ns-value">'+esc(contratada?contratada.razaoSocial:'—')+'</div></div>'+
            '<div class="ns-item"><div class="ns-label">Emissão</div><div class="ns-value">'+esc(fmtDate(nc.dataEmissao))+'</div></div>'+
            '<div class="ns-item"><div class="ns-label">Prazo</div><div class="ns-value">'+App.DeadlineBadge(nc)+'</div></div>'+
          '</div>'+
          '<div style="margin-top:18px;">'+App.FlowStepper(nc.statusAtual)+'</div>'+
        '</div>'+
        '<div class="tabs" id="nc-tabs">'+TABS.map(function(t){
          var count = t.key==='evidencias' ? (nc.anexos||[]).length : null;
          return '<button class="tab '+(t.key===tab?'active':'')+'" data-tab="'+t.key+'">'+esc(t.label)+
            (count!==null ? (' <span class="tab-count">'+count+'</span>') : '')+'</button>';
        }).join('')+'</div>'+
        '<div id="tab-content"></div>'+
      '</div>';

    qsa('#nc-tabs .tab').forEach(function(t){
      t.onclick = function(){ App.router.go('#/ncs/'+id+'/'+t.getAttribute('data-tab')); };
    });
    qs('#btn-pdf').onclick = function(){ App.pdf.registro(nc, sede, contrato, contratada); };
    if(podeEditar) qs('#btn-edit-nc').onclick=function(){modalEditarRegistro(nc,sede);};
    if(podeExcluir) qs('#btn-delete-nc').onclick=async function(){
      var ok=await App.confirmDialog({
        title:'Excluir '+nc.codigoFormatado+'?',
        message:'Esta operação é definitiva e também remove o histórico e os anexos deste registro.',
        confirmLabel:'Excluir definitivamente',
        tone:'danger'
      });
      if(!ok)return;
      var btn=qs('#btn-delete-nc');btn.disabled=true;
      try{
        await App.DB.doc('ncs/'+nc.id).delete();
        await App.refreshAll();
        App.toast('Registro '+nc.codigoFormatado+' excluído.','success');
        App.router.go('#/ncs');
      }catch(e){App.toast(e.message,'danger');btn.disabled=false;}
    };

    var content = qs('#tab-content');
    if(tab==='geral'){ content.innerHTML = tabGeral(nc, sede); bindGeral(nc); }
    else if(tab==='resposta'){ content.innerHTML = tabResposta(nc); bindResposta(nc); }
    else if(tab==='analise'){ content.innerHTML = tabAnalise(nc); bindAnalise(nc); }
    else if(tab==='evidencias'){ content.innerHTML = tabEvidencias(nc); bindEvidencias(nc); }
    else if(tab==='historico'){ content.innerHTML = '<div class="card"><h3 style="margin-bottom:12px;">Linha do tempo</h3>'+App.Timeline(nc.historico)+'</div>'; }
    else { content.innerHTML = tabGeral(nc, sede); bindGeral(nc); }
  }

  App.pages = App.pages || {};
  App.pages.registroDetail = { render:render };
})(window.App);
