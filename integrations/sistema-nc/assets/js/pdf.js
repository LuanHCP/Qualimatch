/* Geração de documentos institucionais em PDF (A4 / jsPDF). */
window.App = window.App || {};
(function(App){
  "use strict";
  var fmtDate=App.util.fmtDate,fmtDateTime=App.util.fmtDateTime,fmtMoney=App.util.fmtMoney,byId=App.util.byId;
  var PAGE_W=210,PAGE_H=297,M=15,CONTENT_W=180;

  function text(v){return v===null||v===undefined||v===''?'Não informado':String(v);}
  function rgb(hex,fallback){return App.util.hexToRgb(hex||fallback||'#1c526e');}
  function color(doc,c){doc.setTextColor(c[0],c[1],c[2]);}
  function fill(doc,c){doc.setFillColor(c[0],c[1],c[2]);}
  function statusLabel(nc){var st=App.STATUS[nc.statusAtual];return st?st.label:text(nc.statusAtual);}

  function header(doc,sede,title,subtitle){
    var primary=rgb(sede.corPrimaria,'#1c526e'),accent=rgb(sede.corDestaque,'#c8791f');
    fill(doc,primary);doc.rect(0,0,PAGE_W,31,'F');fill(doc,accent);doc.rect(0,31,PAGE_W,2,'F');
    fill(doc,[255,255,255]);doc.roundedRect(M,7,17,17,3,3,'F');
    color(doc,primary);doc.setFont('helvetica','bold');doc.setFontSize(8);doc.text(text(sede.sigla).slice(0,5),M+8.5,17.5,{align:'center'});
    doc.setTextColor(255,255,255);doc.setFontSize(13);doc.text(text(title),38,14,{maxWidth:155});
    doc.setFont('helvetica','normal');doc.setFontSize(8);doc.text(text(subtitle),38,22,{maxWidth:155});
    return 42;
  }
  function newPage(doc,sede,title,subtitle){doc.addPage();return header(doc,sede,title,subtitle);}
  function need(doc,y,height,sede,title,subtitle){return y+height>278?newPage(doc,sede,title,subtitle):y;}
  function section(doc,y,label,sede,title,subtitle){
    y=need(doc,y,55,sede,title,subtitle);var primary=rgb(sede.corPrimaria,'#1c526e');fill(doc,primary);doc.roundedRect(M,y,CONTENT_W,9,2,2,'F');doc.setTextColor(255,255,255);doc.setFont('helvetica','bold');doc.setFontSize(9);doc.text(label.toUpperCase(),M+4,y+6);return y+14;
  }
  function fields(doc,y,items,sede,title,subtitle){
    var primary=rgb(sede.corPrimaria,'#1c526e');
    items.forEach(function(item,i){
      var value=doc.splitTextToSize(text(item[1]),126),h=Math.max(10,value.length*4.2+5);y=need(doc,y,h,sede,title,subtitle);
      if(i%2===0){fill(doc,[246,248,250]);doc.rect(M,y,CONTENT_W,h,'F');}
      color(doc,[92,103,112]);doc.setFont('helvetica','bold');doc.setFontSize(7.5);doc.text(String(item[0]).toUpperCase(),M+4,y+6);
      color(doc,[27,36,43]);doc.setFont('helvetica','normal');doc.setFontSize(9);doc.text(value,M+49,y+6);
      y+=h;
    });return y+4;
  }
  function paragraph(doc,y,label,value,sede,title,subtitle){
    var lines=doc.splitTextToSize(text(value),CONTENT_W-10),h=Math.max(19,lines.length*4.5+13);y=need(doc,y,h,sede,title,subtitle);
    fill(doc,[246,248,250]);doc.roundedRect(M,y,CONTENT_W,h,2,2,'F');color(doc,rgb(sede.corPrimaria,'#1c526e'));doc.setFont('helvetica','bold');doc.setFontSize(8);doc.text(label.toUpperCase(),M+5,y+6);
    color(doc,[27,36,43]);doc.setFont('helvetica','normal');doc.setFontSize(9);doc.text(lines,M+5,y+12);return y+h+5;
  }
  function moneyCards(doc,y,nc,sede,title,subtitle){
    y=need(doc,y,25,sede,title,subtitle);var values=[['VALOR ESTIMADO',fmtMoney(nc.valorEstimado)],['RETENÇÃO PROPOSTA',fmtMoney(nc.valorRetencaoProposto)],['RETENÇÃO EFETIVA',fmtMoney(nc.valorRetencaoEfetivo)]];
    values.forEach(function(v,i){var x=M+i*61;fill(doc,i===2?[236,247,242]:[241,246,249]);doc.roundedRect(x,y,57,22,2,2,'F');color(doc,[92,103,112]);doc.setFont('helvetica','bold');doc.setFontSize(6.8);doc.text(v[0],x+4,y+7);color(doc,rgb(sede.corPrimaria,'#1c526e'));doc.setFontSize(11);doc.text(v[1],x+4,y+16);});return y+28;
  }
  function footers(doc,sede,code){
    var pages=doc.internal.getNumberOfPages(),primary=rgb(sede.corPrimaria,'#1c526e');
    for(var p=1;p<=pages;p++){doc.setPage(p);doc.setDrawColor(218,224,228);doc.line(M,284,PAGE_W-M,284);color(doc,[105,115,124]);doc.setFont('helvetica','normal');doc.setFontSize(7);doc.text('Gerado em '+new Date().toLocaleString('pt-BR')+' | '+text(code),M,290);color(doc,primary);doc.setFont('helvetica','bold');doc.text('Página '+p+' de '+pages,PAGE_W-M,290,{align:'right'});}
  }
  function fileToData(blob){return new Promise(function(resolve,reject){var reader=new FileReader();reader.onload=function(){resolve(reader.result);};reader.onerror=reject;reader.readAsDataURL(blob);});}
  async function attachmentData(a){if(a.thumb)return a.thumb;if(!a.url||String(a.tipo||'').toLowerCase()==='pdf')return null;try{var response=await fetch(a.url,{credentials:'same-origin'});if(!response.ok)return null;return await fileToData(await response.blob());}catch(e){return null;}}
  function imageFormat(data){return String(data).indexOf('image/png')>=0?'PNG':'JPEG';}
  async function photos(doc,nc,sede,title,subtitle){
    var attachments=nc.anexos||[];if(!attachments.length)return;
    var loaded=await Promise.all(attachments.map(async function(a){return {item:a,data:await attachmentData(a)};}));
    var y=newPage(doc,sede,'Relatório fotográfico',text(nc.codigoFormatado)),col=0;
    for(var i=0;i<loaded.length;i++){
      var pack=loaded[i],a=pack.item,x=col===0?M:108,w=87,h=58;
      if(y+76>278){y=newPage(doc,sede,'Relatório fotográfico',text(nc.codigoFormatado));col=0;x=M;}
      fill(doc,[246,248,250]);doc.roundedRect(x,y,w,70,2,2,'F');
      if(pack.data){try{doc.addImage(pack.data,imageFormat(pack.data),x+2,y+2,w-4,h-4,undefined,'FAST');}catch(e){pack.data=null;}}
      if(!pack.data){color(doc,[105,115,124]);doc.setFontSize(8);doc.text(String(a.tipo||'ARQUIVO').toUpperCase()+' - '+text(a.nomeArquivo),x+4,y+29,{maxWidth:w-8,align:'center'});}
      color(doc,[27,36,43]);doc.setFont('helvetica','bold');doc.setFontSize(7.5);doc.text(doc.splitTextToSize(text(a.legenda),w-8).slice(0,2),x+4,y+61);
      color(doc,[105,115,124]);doc.setFont('helvetica','normal');doc.setFontSize(6.8);doc.text('Km '+text(a.km)+' | '+text(a.pista)+' | '+fmtDate(a.dataFoto),x+4,y+68,{maxWidth:w-8});
      col++;if(col===2){col=0;y+=76;}
    }
  }
  async function savePdf(doc,filename){var blob=doc.output('blob');if(App.CAN_DOWNLOAD){var buf=await blob.arrayBuffer();await App.CAN_DOWNLOAD.save({filename:filename,data:buf});}else doc.save(filename);}

  async function registro(nc,sede,contrato,contratada){
    var doc=new window.jspdf.jsPDF({unit:'mm',format:'a4',compress:true});doc.setProperties({title:text(nc.codigoFormatado),subject:'Registro de não conformidade',author:text(sede.nome),creator:'Sistema de Gestão de Não Conformidades'});
    var title=App.tipoLabel(sede,nc.tipoCore)+' - Registro de não conformidade',sub=text(nc.codigoFormatado)+' | '+statusLabel(nc),y=header(doc,sede,title,sub);
    y=section(doc,y,'Identificação',sede,title,sub);y=fields(doc,y,[['Código',nc.codigoFormatado],['Status',statusLabel(nc)],['SEDE',sede.nome],['Contrato',contrato?contrato.numero:null],['Contratada',contratada?contratada.razaoSocial:null],['Objeto da obra',contrato?contrato.descricaoObra:null],['Emissão',fmtDate(nc.dataEmissao)],['Ocorrência',fmtDate(nc.dataOcorrencia)],['Responsável',nc.responsavelEmissaoNome]],sede,title,sub);
    y=section(doc,y,'Classificação e localização',sede,title,sub);y=fields(doc,y,[['Área / disciplina',text(nc.area)+' / '+text(nc.disciplina)],['Categoria / item',[nc.categoria,nc.item,nc.subitem].filter(Boolean).join(' / ')],['Classificação',nc.classificacao],['Rodovia / trecho',text(nc.rodovia)+' / '+text(nc.trecho)],['Localização','Km '+text(nc.kmInicial)+' a '+text(nc.kmFinal)+' | '+text(nc.pistaSentido)+' | Faixa '+text(nc.faixa)],['Quantidade',text(nc.quantidade)+' '+text(nc.unidadeQuantidade)],['Referência normativa',nc.normaReferencia]],sede,title,sub);
    y=section(doc,y,'Descrição técnica',sede,title,sub);y=paragraph(doc,y,'Descrição da não conformidade',nc.descricao,sede,title,sub);if(nc.observacaoCampo)y=paragraph(doc,y,'Observações de campo',nc.observacaoCampo,sede,title,sub);y=moneyCards(doc,y,nc,sede,title,sub);y=fields(doc,y,[['Prazo para resposta',fmtDateTime(nc.prazoResposta)]],sede,title,sub);
    y=section(doc,y,'Resposta da contratada',sede,title,sub);if(nc.respostaContratada){var r=nc.respostaContratada;y=paragraph(doc,y,'Análise da causa',r.analiseCausa,sede,title,sub);y=paragraph(doc,y,'Ação corretiva',r.acaoCorretiva,sede,title,sub);y=paragraph(doc,y,'Plano de ação',r.planoDeAcao,sede,title,sub);y=fields(doc,y,[['Disposição solicitada',r.disposicaoSolicitada],['Data da resposta',fmtDateTime(r.dataResposta)]],sede,title,sub);}else y=paragraph(doc,y,'Situação','Sem resposta registrada até a emissão deste documento.',sede,title,sub);
    y=section(doc,y,'Avaliação da concessionária',sede,title,sub);if(nc.avaliacaoConcessionaria){var a=nc.avaliacaoConcessionaria;y=paragraph(doc,y,'Parecer técnico',a.parecerTecnico,sede,title,sub);y=fields(doc,y,[['Decisão',a.disposicaoStatus],['Resultado da eficácia',a.resultadoEficacia]],sede,title,sub);}else y=paragraph(doc,y,'Situação','Avaliação pendente.',sede,title,sub);
    if((nc.historico||[]).length){y=section(doc,y,'Rastreabilidade',sede,title,sub);(nc.historico||[]).slice(-12).forEach(function(h){y=fields(doc,y,[[fmtDateTime(h.dataHora),text(h.usuarioNome)+' - '+text(h.comentario)]],sede,title,sub);});}
    y=need(doc,y,28,sede,title,sub);color(doc,[27,36,43]);doc.setFont('helvetica','bold');doc.setFontSize(8);doc.text('VALIDAÇÃO E CIÊNCIA',M,y);y+=13;[['Emitente / Qualidade',M],['Fiscalização / Engenharia',77],['Representante da contratada',139]].forEach(function(v){doc.setDrawColor(140,150,158);doc.line(v[1],y,v[1]+55,y);color(doc,[105,115,124]);doc.setFont('helvetica','normal');doc.setFontSize(7);doc.text(v[0],v[1]+27.5,y+5,{align:'center'});});
    await photos(doc,nc,sede,title,sub);footers(doc,sede,nc.codigoFormatado);await savePdf(doc,text(nc.codigoFormatado).replace(/[^a-zA-Z0-9_-]/g,'_')+'.pdf');
  }

  async function anexos(nc){var sede=byId(App.state.sedes,nc.sedeId)||App.sedeAtual(),doc=new window.jspdf.jsPDF({unit:'mm',format:'a4',compress:true});header(doc,sede,'Relatório fotográfico',text(nc.codigoFormatado));await photos(doc,nc,sede,'Relatório fotográfico',text(nc.codigoFormatado));if(doc.internal.getNumberOfPages()>1)doc.deletePage(1);footers(doc,sede,nc.codigoFormatado);await savePdf(doc,'evidencias-'+text(nc.codigoFormatado).replace(/[^a-zA-Z0-9_-]/g,'_')+'.pdf');}

  async function relatorioMensal(ncs,sede){
    var doc=new window.jspdf.jsPDF({unit:'mm',format:'a4',compress:true}),title='Relatório executivo de não conformidades',sub=text(sede.nome),y=header(doc,sede,title,sub),total=ncs.length,abertas=ncs.filter(function(n){return App.STATUS[n.statusAtual].group==='aberto';}).length,encerradas=ncs.filter(function(n){return App.STATUS[n.statusAtual].group==='encerrado';}).length,vencidas=ncs.filter(App.isVencido).length;
    y=section(doc,y,'Resumo executivo',sede,title,sub);y=fields(doc,y,[['Registros analisados',total],['Em aberto',abertas],['Encerrados',encerradas],['Vencidos',vencidas],['Retenção proposta',fmtMoney(ncs.reduce(function(s,n){return s+(Number(n.valorRetencaoProposto)||0);},0))],['Retenção efetiva',fmtMoney(ncs.reduce(function(s,n){return s+(Number(n.valorRetencaoEfetivo)||0);},0))]],sede,title,sub);
    var byCat={};ncs.forEach(function(n){var c=n.categoria||'Sem categoria';byCat[c]=(byCat[c]||0)+1;});y=section(doc,y,'Ocorrências por categoria',sede,title,sub);y=fields(doc,y,Object.keys(byCat).sort(function(a,b){return byCat[b]-byCat[a];}).map(function(c){return[c,byCat[c]+' registro(s)'];}),sede,title,sub);
    y=section(doc,y,'Registros recentes',sede,title,sub);ncs.slice().sort(function(a,b){return new Date(b.dataEmissao)-new Date(a.dataEmissao);}).slice(0,20).forEach(function(n){y=fields(doc,y,[[text(n.codigoFormatado),fmtDate(n.dataEmissao)+' | '+statusLabel(n)+' | '+text(n.categoria)]],sede,title,sub);});footers(doc,sede,'Relatório executivo');await savePdf(doc,'relatorio-executivo-'+text(sede.sigla)+'.pdf');
  }
  App.pdf={registro:registro,anexos:anexos,relatorioMensal:relatorioMensal};
})(window.App);
