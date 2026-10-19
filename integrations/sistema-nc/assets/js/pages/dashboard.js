/* ============================================================
   pages/dashboard.js — painel executivo
   Regras de cálculo (KPIs, prazos, valores) preservadas.
   ============================================================ */
window.App = window.App || {};
(function(App){
  "use strict";
  var qs=App.util.qs, qsa=App.util.qsa, esc=App.util.esc, byId=App.util.byId, uniq=App.util.uniq,
      fmtMoney=App.util.fmtMoney, diasEntre=App.util.diasEntre;

  function achaData(historico, status){
    for(var i=0;i<historico.length;i++){ if(historico[i].statusNovo===status) return historico[i].dataHora; }
    return null;
  }

  function donutSvg(segments, size){
    size = size||150;
    var total = segments.reduce(function(s,x){return s+x.value;},0);
    var r = size/2 - 12, c = size/2, circ = 2*Math.PI*r, offset=0;
    var arcs = '';
    if(total===0){
      arcs = '<circle cx="'+c+'" cy="'+c+'" r="'+r+'" fill="none" stroke="var(--border)" stroke-width="16"></circle>';
    } else {
      segments.forEach(function(seg){
        if(seg.value<=0) return;
        var frac = seg.value/total;
        var len = frac*circ;
        arcs += '<circle cx="'+c+'" cy="'+c+'" r="'+r+'" fill="none" stroke="'+seg.color+'" stroke-width="16" '+
          'stroke-dasharray="'+len+' '+(circ-len)+'" stroke-dashoffset="'+(-offset)+'" transform="rotate(-90 '+c+' '+c+')"><title>'+esc(seg.label)+': '+seg.value+'</title></circle>';
        offset += len;
      });
    }
    return '<svg class="donut-svg" role="img" aria-label="Distribuição por status" viewBox="0 0 '+size+' '+size+'">'+arcs+
      '<text x="'+c+'" y="'+(c-3)+'" text-anchor="middle" font-family="var(--font-mono)" font-size="22" fill="var(--ink)" font-weight="600">'+total+'</text>'+
      '<text x="'+c+'" y="'+(c+15)+'" text-anchor="middle" font-family="var(--font-body)" font-size="10" fill="var(--ink-faint)">registros</text>'+
    '</svg>';
  }

  function barChartSvg(data, w, h, filterKind){
    w=Math.max(w||520,data.length*(filterKind==='categoria'?115:78)); h=h||255;
    var max = Math.max.apply(null, data.map(function(d){return d.value;}).concat([1]));
    var padL=10, padB=58, padT=20, slot=data.length?w/data.length:w, barGap=Math.max(22,slot*.42);
    var innerW = w - padL*2, innerH = h - padB - padT;
    var bw = data.length ? (innerW/data.length - barGap) : 0;
    var bars = data.map(function(d,i){
      var bh = max? (d.value/max)*innerH : 0;
      var x = padL + i*(innerW/data.length) + barGap/2;
      var y = padT + (innerH-bh);
      return '<g class="chart-filter" role="button" tabindex="0" data-kind="'+esc(filterKind||'')+'" data-value="'+esc(d.filterValue||d.label)+'" aria-label="Filtrar por '+esc(d.label)+'">'+'<rect class="bar" x="'+x+'" y="'+y+'" width="'+Math.max(bw,4)+'" height="'+Math.max(bh,2)+'" rx="4"><title>'+esc(d.label)+': '+d.value+'</title></rect>'+
             '<text class="val" x="'+(x+bw/2)+'" y="'+(y-6)+'" text-anchor="middle">'+d.value+'</text>'+
             '<text class="axis-label" x="'+(x+bw/2)+'" y="'+(h-38)+'" text-anchor="end" transform="rotate(-28 '+(x+bw/2)+' '+(h-38)+')">'+esc(d.label||'')+'</text></g>';
    }).join('');
    return '<div class="bar-chart-scroll"><svg class="bar-chart-svg" viewBox="0 0 '+w+' '+h+'" style="min-width:'+w+'px">'+
      '<line class="gridline" x1="'+padL+'" y1="'+(h-padB)+'" x2="'+(w-padL)+'" y2="'+(h-padB)+'"></line>'+bars+'</svg></div>';
  }

  async function render(mount){
    var sede = App.sedeAtual();
    var ncs = await App.loadNcs();
    var contratosSede = App.state.contratos.filter(function(c){return c.sedeId===App.state.sedeId;});
    var quickFilter = null;

    mount.innerHTML =
      App.PageHeader({
        title:'Painel',
        sub:'Visão consolidada das Não Conformidades da '+sede.sigla+'.',
        actionsHtml: App.Button({label:'Gerar relatório', icon:'download', variant:'primary', id:'btn-relatorio'})
      })+
      '<div class="page-body">'+
        '<div style="margin-bottom:14px;">'+App.FilterToggle('dash-filter-toggle','Filtros')+'</div>'+
        '<div id="dash-filter-panel" class="hidden"></div>'+
        '<div id="dash-chips" class="chip-row"></div>'+
        '<div class="kpi-grid" id="dash-kpis"></div>'+
        App.Card('<div class="retencao-row" id="dash-valores"></div>', {title:'Valores de retenção', sub:'Somatório dos registros no filtro atual.'})+
        '<div class="charts-grid" style="margin-top:16px;">'+
          App.Card('<div class="donut-wrap" id="chart-status"></div>', {title:'Distribuição por status'})+
          App.Card('<div id="chart-cat"></div>', {title:'Ocorrências por categoria'})+
        '</div>'+
        '<div class="charts-grid" style="margin-top:16px;">'+
          App.Card('<div id="rank-contratadas"></div>', {title:'Contratadas com mais registros'})+
          App.Card('<div id="chart-evolucao"></div>', {title:'Evolução de NCs por mês', sub:'Baseado na data de emissão dos registros existentes.'})+
        '</div>'+
        App.Card('<div id="tbl-recent"></div><div style="margin-top:12px;text-align:right;">'+App.Button({label:'Ver todos os registros', icon:'arrowUpRight', variant:'ghost', size:'sm', id:'btn-ver-todos'})+'</div>', {title:'Registros recentes', sub:'Os 10 mais recentes considerando o filtro atual.'})+
      '</div>';

    // ---- filtro
    var filterFields =
      App.selectHtml('f-contrato','Contrato',[['','Todos']].concat(contratosSede.map(function(c){return [c.id,c.numero];})))+
      App.selectHtml('f-status','Status',[['','Todos']].concat(Object.keys(App.STATUS).map(function(k){return [k,App.STATUS[k].label];})))+
      App.selectHtml('f-categoria','Categoria',[['','Todas']].concat(uniq(ncs.map(function(n){return n.categoria;})).map(function(c){return [c,c];})))+
      App.inputHtml('f-de','Data inicial','date')+ App.inputHtml('f-ate','Data final','date')+
      App.selectHtml('f-prazo','Situação de prazo',[['','Todas'],['vencido','Vencidas'],['no_prazo','No prazo']]);
    qs('#dash-filter-panel').outerHTML = App.FilterPanel(filterFields, {id:'dash-filter-panel'});

    var toggleBtn = qs('#dash-filter-toggle');
    var panel = qs('#dash-filter-panel');
    panel.classList.add('hidden'); // painel começa recolhido por padrão
    toggleBtn.onclick = function(){ panel.classList.toggle('hidden'); };

    function currentFilters(){
      return { contrato:qs('#f-contrato').value, status:qs('#f-status').value, categoria:qs('#f-categoria').value, de:qs('#f-de').value, ate:qs('#f-ate').value, prazo:qs('#f-prazo').value };
    }
    function filterLabel(key,val){
      if(!val) return null;
      if(key==='contrato'){ var c=byId(contratosSede,val); return 'Contrato: '+(c?c.numero:val); }
      if(key==='status') return 'Status: '+App.STATUS[val].label;
      if(key==='categoria') return 'Categoria: '+val;
      if(key==='de') return 'De: '+App.util.fmtDate(val);
      if(key==='ate') return 'Até: '+App.util.fmtDate(val);
      if(key==='prazo') return 'Prazo: '+(val==='vencido'?'Vencidas':'No prazo');
      return null;
    }
    function apply(){
      var f = currentFilters();
      var activeCount = Object.keys(f).filter(function(k){return f[k];}).length;
      var countBadge = qs('#dash-filter-toggle-count');
      if(countBadge){ countBadge.textContent=activeCount; countBadge.classList.toggle('hidden', activeCount===0); }
      var chipHtml = Object.keys(f).map(function(k){
        var lab = filterLabel(k,f[k]); if(!lab) return '';
        return '<span class="chip">'+esc(lab)+'<button data-clear="'+k+'">'+App.icon('x','sm')+'</button></span>';
      }).join('');
      if(quickFilter) chipHtml += '<span class="chip">'+esc(quickFilter.label)+'<button data-clear-quick="1">'+App.icon('x','sm')+'</button></span>';
      qs('#dash-chips').innerHTML = chipHtml;
      qsa('#dash-chips button[data-clear]').forEach(function(b){ b.onclick=function(){ var k=b.getAttribute('data-clear'); qs('#f-'+k).value=''; apply(); }; });
      var clearQuick=qs('#dash-chips button[data-clear-quick]');if(clearQuick)clearQuick.onclick=function(){quickFilter=null;apply();};

      var filtered = ncs.filter(function(n){
        if(f.contrato && n.contratoId!==f.contrato) return false;
        if(f.status && n.statusAtual!==f.status) return false;
        if(f.categoria && n.categoria!==f.categoria) return false;
        if(f.de && new Date(n.dataEmissao) < new Date(f.de)) return false;
        if(f.ate && new Date(n.dataEmissao) > new Date(f.ate)) return false;
        if(f.prazo==='vencido' && !App.isVencido(n)) return false;
        if(f.prazo==='no_prazo' && App.isVencido(n)) return false;
        return true;
      });
      if(quickFilter) filtered=filtered.filter(function(n){
        if(quickFilter.kind==='categoria')return (n.categoria||'Sem categoria')===quickFilter.value;
        if(quickFilter.kind==='contratada'){var c=byId(App.state.contratadas,n.contratadaId);return (c?c.razaoSocial:'—')===quickFilter.value;}
        if(quickFilter.kind==='mes')return String(n.dataEmissao||'').slice(0,7)===quickFilter.value;
        if(quickFilter.kind==='status'){
          if(quickFilter.value==='Aguardando resposta')return n.statusAtual==='aguardando_resposta'&&!App.isVencido(n);
          if(quickFilter.value==='Vencidas')return App.isVencido(n);
          if(quickFilter.value==='Em análise')return ['em_analise','disposicao_aprovada','disposicao_recusada'].indexOf(n.statusAtual)>=0;
          if(quickFilter.value==='Em execução')return ['em_execucao','aguardando_verificacao','nao_eficaz'].indexOf(n.statusAtual)>=0;
          if(quickFilter.value==='Encerradas')return App.STATUS[n.statusAtual].group==='encerrado';
          return ['rascunho','emitida','protocolada','respondida'].indexOf(n.statusAtual)>=0;
        }
        return true;
      });
      renderData(filtered);
    }
    qsa('#dash-filter-panel select, #dash-filter-panel input').forEach(function(el){ el.onchange = apply; });
    qs('#dash-filter-panel-clear').onclick = function(){
      qsa('#dash-filter-panel select, #dash-filter-panel input').forEach(function(el){ el.value=''; });
      apply();
    };
    qs('#btn-relatorio').onclick = function(){ App.pdf.relatorioMensal(ncs, sede); };
    qs('#btn-ver-todos').onclick = function(){ App.router.go('#/ncs'); };

    function renderData(list){
      var total=list.length;
      var abertas=list.filter(function(n){return App.STATUS[n.statusAtual].group==='aberto';}).length;
      var respondidas=list.filter(function(n){return n.respostaContratada;}).length;
      var encerradas=list.filter(function(n){return App.STATUS[n.statusAtual].group==='encerrado';}).length;
      var vencidas=list.filter(App.isVencido).length;
      var agora=Date.now(),venceBreve=list.filter(function(n){if(!n.prazoResposta||App.STATUS[n.statusAtual].group==='encerrado'||App.isVencido(n))return false;var dias=(new Date(n.prazoResposta).getTime()-agora)/86400000;return dias>=0&&dias<=3;}).length;
      var comResposta = list.filter(function(n){return n.respostaContratada && n.dataEmissao;});
      var prazoMedio = comResposta.length ? Math.round(comResposta.reduce(function(s,n){return s+Math.max(0,diasEntre(n.dataEmissao, achaData(n.historico||[],'respondida')||n.dataEmissao));},0)/comResposta.length) : 0;
      var encerradasComData = list.filter(function(n){return n.dataEncerramento;});
      var tempoMedioEnc = encerradasComData.length ? Math.round(encerradasComData.reduce(function(s,n){return s+Math.max(0,diasEntre(n.dataEmissao,n.dataEncerramento));},0)/encerradasComData.length) : 0;
      var valorProposto = list.reduce(function(s,n){return s+(Number(n.valorRetencaoProposto)||0);},0);
      var valorEfetivo = list.reduce(function(s,n){return s+(Number(n.valorRetencaoEfetivo)||0);},0);
      var diff = valorEfetivo - valorProposto;

      qs('#dash-kpis').innerHTML = [
        App.KpiCard({label:'Total de registros', value:total, icon:'list', tone:'default'}),
        App.KpiCard({label:'Em aberto', value:abertas, icon:'clock', tone:'accent'}),
        App.KpiCard({label:'Respondidas', value:respondidas, icon:'checkCircle', tone:'primary'}),
        App.KpiCard({label:'Encerradas', value:encerradas, icon:'checkCircle', tone:'good'}),
        App.KpiCard({label:'Vencidas', value:vencidas, icon:'alertTriangle', tone:'bad'}),
        App.KpiCard({label:'Vencem em até 3 dias', value:venceBreve, icon:'clock', tone:'accent'}),
        App.KpiCard({label:'Prazo médio', value:prazoMedio+'d', icon:'calendar', tone:'default', extra:'Encerramento: '+tempoMedioEnc+'d em média'})
      ].join('');

      qs('#dash-valores').innerHTML =
        '<div class="retencao-item"><div class="rt-label">Retenção proposta</div><div class="rt-value">'+fmtMoney(valorProposto)+'</div></div>'+
        '<div class="retencao-item"><div class="rt-label">Retenção efetiva</div><div class="rt-value">'+fmtMoney(valorEfetivo)+'</div></div>'+
        (valorProposto!==valorEfetivo ? '<div class="retencao-item diff"><div class="rt-label">Diferença</div><div class="rt-value">'+(diff>=0?'+':'')+fmtMoney(Math.abs(diff))+'</div></div>' : '');

      // donut de status
      var buckets = {
        'Aguardando resposta': list.filter(function(n){return n.statusAtual==='aguardando_resposta' && !App.isVencido(n);}).length,
        'Vencidas': vencidas,
        'Em análise': list.filter(function(n){return ['em_analise','disposicao_aprovada','disposicao_recusada'].indexOf(n.statusAtual)>=0;}).length,
        'Em execução': list.filter(function(n){return ['em_execucao','aguardando_verificacao','nao_eficaz'].indexOf(n.statusAtual)>=0;}).length,
        'Encerradas': encerradas,
        'Outras': list.filter(function(n){return ['rascunho','emitida','protocolada','respondida'].indexOf(n.statusAtual)>=0;}).length
      };
      var colors = {'Aguardando resposta':'var(--warning)','Vencidas':'var(--danger)','Em análise':'var(--primary)','Em execução':'var(--accent)','Encerradas':'var(--success)','Outras':'var(--n-300)'};
      var segs = Object.keys(buckets).map(function(k){ return {label:k, value:buckets[k], color:colors[k]}; });
      qs('#chart-status').innerHTML = donutSvg(segs)+
        '<div class="donut-legend">'+segs.map(function(s){ return '<button class="leg-item chart-filter" data-kind="status" data-value="'+esc(s.label)+'"><span class="leg-dot" style="background:'+s.color+'"></span><span class="leg-label">'+esc(s.label)+'</span><span class="leg-val">'+s.value+'</span></button>'; }).join('')+'</div>';

      // barras por categoria
      var byCat={}; list.forEach(function(n){ var c=n.categoria||'Sem categoria'; byCat[c]=(byCat[c]||0)+1; });
      var catData = Object.keys(byCat).map(function(k){return {label:k,value:byCat[k]};}).sort(function(a,b){return b.value-a.value;}).slice(0,8);
      qs('#chart-cat').innerHTML = catData.length ? barChartSvg(catData,0,0,'categoria') : App.EmptyState({icon:'dashboard', title:'Sem dados para o filtro atual'});

      // ranking contratadas
      var byC={}; list.forEach(function(n){ var c=byId(App.state.contratadas,n.contratadaId); var name=c?c.razaoSocial:'—'; byC[name]=(byC[name]||0)+1; });
      var rankRows = Object.keys(byC).map(function(k){return [k,byC[k]];}).sort(function(a,b){return b[1]-a[1];}).slice(0,6);
      qs('#rank-contratadas').innerHTML = rankRows.length ? rankRows.map(function(r,i){
        var max = rankRows[0][1];
        return '<button class="rank-row chart-filter" data-kind="contratada" data-value="'+esc(r[0])+'"><span class="rank-n">'+String(i+1).padStart(2,'0')+'</span><span class="rank-label">'+esc(r[0])+'</span>'+
          '<span class="rank-track"><span class="rank-fill" style="width:'+(r[1]/max*100)+'%"></span></span><span class="rank-val">'+r[1]+'</span></button>';
      }).join('') : App.EmptyState({icon:'users', title:'Sem dados'});

      // evolução por mês (apenas se houver ao menos 2 meses distintos nos dados reais)
      var byMonth={};
      list.forEach(function(n){ if(!n.dataEmissao) return; var m=String(n.dataEmissao).slice(0,7); byMonth[m]=(byMonth[m]||0)+1; });
      var months = Object.keys(byMonth).sort();
      if(months.length>=2){
        var evoData = months.map(function(m){
          var d=new Date(m+'-01'); var label=d.toLocaleDateString('pt-BR',{month:'short',year:'2-digit'});
          return {label:label, value:byMonth[m], filterValue:m};
        });
        qs('#chart-evolucao').innerHTML = barChartSvg(evoData,0,0,'mes');
      } else {
        qs('#chart-evolucao').innerHTML = App.EmptyState({icon:'calendar', title:'Histórico insuficiente', text:'A evolução mensal aparece quando os registros cobrem dois ou mais meses distintos.'});
      }

      // tabela de recentes
      var recent = list.slice().sort(function(a,b){return new Date(b.dataEmissao)-new Date(a.dataEmissao);}).slice(0,10);
      qs('#tbl-recent').innerHTML = App.pages.registros.tableHtml(recent);
      App.pages.registros.bindTableRows(qs('#tbl-recent'));
      qsa('.chart-filter').forEach(function(el){var activate=function(){var kind=el.getAttribute('data-kind'),value=el.getAttribute('data-value');if(!kind||!value)return;quickFilter={kind:kind,value:value,label:'Filtro: '+value};apply();};el.onclick=activate;el.onkeydown=function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}};});
    }

    apply();
  }

  App.pages = App.pages || {};
  App.pages.dashboard = { render:render };
})(window.App);
