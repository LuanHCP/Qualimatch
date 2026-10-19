/* ============================================================
   components.js — biblioteca de componentes reutilizáveis
   (ícones SVG, Button, Card, KpiCard, Badge/StatusBadge,
   PageHeader, FilterPanel, Table, Pagination, Modal, Toast,
   EmptyState, ConfirmDialog, FormField, Timeline, EvidenceCard...)
   Tudo em funções puras que devolvem HTML (string) — sem
   framework, compatível com execução local via file://.
   ============================================================ */
window.App = window.App || {};

(function(App){
  "use strict";
  var esc = function(s){ return App.util.esc(s); };

  /* ---------------- ícones (SVG neutro, sem emoji) ---------------- */
  var ICON_PATHS = {
    dashboard:'<rect x="3" y="3" width="7" height="9" rx="1.5"></rect><rect x="14" y="3" width="7" height="5" rx="1.5"></rect><rect x="14" y="12" width="7" height="9" rx="1.5"></rect><rect x="3" y="16" width="7" height="5" rx="1.5"></rect>',
    list:'<line x1="9" y1="6" x2="21" y2="6"></line><line x1="9" y1="12" x2="21" y2="12"></line><line x1="9" y1="18" x2="21" y2="18"></line><circle cx="4" cy="6" r="1.2" fill="currentColor" stroke="none"></circle><circle cx="4" cy="12" r="1.2" fill="currentColor" stroke="none"></circle><circle cx="4" cy="18" r="1.2" fill="currentColor" stroke="none"></circle>',
    file:'<path d="M6 2.5h8l4 4v15H6z"></path><line x1="9" y1="12" x2="15" y2="12"></line><line x1="9" y1="16" x2="15" y2="16"></line>',
    book:'<path d="M4 4.5c2-1 5-1 8 0v15c-3-1-6-1-8 0z"></path><path d="M20 4.5c-2-1-5-1-8 0v15c3-1 6-1 8 0z"></path>',
    settings:'<circle cx="12" cy="12" r="3"></circle><path d="M12 3v3M12 18v3M4.2 7.5l2.6 1.5M17.2 15l2.6 1.5M4.2 16.5l2.6-1.5M17.2 9l2.6-1.5"></path>',
    users:'<circle cx="9" cy="8" r="3"></circle><path d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5"></path><circle cx="17" cy="9" r="2.4"></circle><path d="M15.7 14.3c2.4.3 4.3 2.1 4.3 4.7"></path>',
    swap:'<polyline points="4 8 20 8"></polyline><polyline points="16 4 20 8 16 12"></polyline><polyline points="20 16 4 16"></polyline><polyline points="8 12 4 16 8 20"></polyline>',
    chevronDown:'<polyline points="6 9 12 15 18 9"></polyline>',
    chevronRight:'<polyline points="9 6 15 12 9 18"></polyline>',
    chevronLeft:'<polyline points="15 6 9 12 15 18"></polyline>',
    search:'<circle cx="10.5" cy="10.5" r="6.5"></circle><line x1="15.3" y1="15.3" x2="20.5" y2="20.5"></line>',
    alertTriangle:'<path d="M12 3.5 21 19.5H3z"></path><line x1="12" y1="9.5" x2="12" y2="14"></line><circle cx="12" cy="16.7" r="0.6" fill="currentColor" stroke="none"></circle>',
    checkCircle:'<circle cx="12" cy="12" r="9"></circle><polyline points="8 12.5 11 15.5 16.5 9"></polyline>',
    check:'<polyline points="4 12 9.5 17.5 20 6"></polyline>',
    clock:'<circle cx="12" cy="12" r="9"></circle><polyline points="12 7 12 12 16 14.5"></polyline>',
    x:'<line x1="6" y1="6" x2="18" y2="18"></line><line x1="18" y1="6" x2="6" y2="18"></line>',
    plus:'<line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line>',
    filter:'<path d="M4 5h16l-6 7.5v6L10 21v-8.5z"></path>',
    download:'<path d="M12 3v12"></path><polyline points="7 11 12 16 17 11"></polyline><line x1="4" y1="20" x2="20" y2="20"></line>',
    upload:'<path d="M12 21V9"></path><polyline points="7 13 12 8 17 13"></polyline><line x1="4" y1="4" x2="20" y2="4"></line>',
    image:'<rect x="3" y="4" width="18" height="16" rx="2"></rect><circle cx="9" cy="10" r="1.8"></circle><polyline points="4 18 9.5 12.5 13 16 16.5 12.5 20 16"></polyline>',
    menu:'<line x1="3.5" y1="6.5" x2="20.5" y2="6.5"></line><line x1="3.5" y1="12" x2="20.5" y2="12"></line><line x1="3.5" y1="17.5" x2="20.5" y2="17.5"></line>',
    logout:'<path d="M9 4H5.5A1.5 1.5 0 0 0 4 5.5v13A1.5 1.5 0 0 0 5.5 20H9"></path><line x1="21" y1="12" x2="10.5" y2="12"></line><polyline points="17 7.5 21.5 12 17 16.5"></polyline>',
    building:'<rect x="4" y="3" width="16" height="18" rx="1.5"></rect><line x1="8" y1="7.5" x2="8" y2="7.5"></line><line x1="12" y1="7.5" x2="12" y2="7.5"></line><line x1="16" y1="7.5" x2="16" y2="7.5"></line><rect x="7" y="7" width="2" height="2"></rect><rect x="11" y="7" width="2" height="2"></rect><rect x="15" y="7" width="2" height="2"></rect><rect x="7" y="11.5" width="2" height="2"></rect><rect x="11" y="11.5" width="2" height="2"></rect><rect x="15" y="11.5" width="2" height="2"></rect><rect x="10" y="16" width="4" height="5"></rect>',
    info:'<circle cx="12" cy="12" r="9"></circle><line x1="12" y1="11" x2="12" y2="16"></line><circle cx="12" cy="7.6" r="0.6" fill="currentColor" stroke="none"></circle>',
    dot:'<circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"></circle>',
    arrowUpRight:'<line x1="7" y1="17" x2="17" y2="7"></line><polyline points="9 7 17 7 17 15"></polyline>',
    calendar:'<rect x="3.5" y="5" width="17" height="16" rx="2"></rect><line x1="3.5" y1="10" x2="20.5" y2="10"></line><line x1="8" y1="3" x2="8" y2="7"></line><line x1="16" y1="3" x2="16" y2="7"></line>',
    coins:'<circle cx="9" cy="9" r="6"></circle><path d="M14 9.3A6 6 0 1 1 14.5 15"></path>',
    eye:'<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"></path><circle cx="12" cy="12" r="2.6"></circle>',
    camera:'<path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"></path><circle cx="12" cy="14" r="3.4"></circle>',
    paperclip:'<path d="M17 8.5 9.5 16a3 3 0 0 1-4.2-4.2l8-8a4.5 4.5 0 0 1 6.4 6.4l-8.6 8.6"></path>',
    arrowLeft:'<line x1="19" y1="12" x2="5" y2="12"></line><polyline points="10.5 6 5 12 10.5 18"></polyline>',
    grip:'<circle cx="9" cy="6" r="1" fill="currentColor" stroke="none"></circle><circle cx="9" cy="12" r="1" fill="currentColor" stroke="none"></circle><circle cx="9" cy="18" r="1" fill="currentColor" stroke="none"></circle><circle cx="15" cy="6" r="1" fill="currentColor" stroke="none"></circle><circle cx="15" cy="12" r="1" fill="currentColor" stroke="none"></circle><circle cx="15" cy="18" r="1" fill="currentColor" stroke="none"></circle>',
    trendUp:'<polyline points="4 16 10 10 14 13 20 6"></polyline><polyline points="14 6 20 6 20 12"></polyline>',
    fileText:'<path d="M6 2.5h8l4 4v15H6z"></path><line x1="9" y1="11" x2="15" y2="11"></line><line x1="9" y1="14.5" x2="15" y2="14.5"></line><line x1="9" y1="18" x2="13" y2="18"></line>'
  };
  App.icon = function(name, cls){
    var body = ICON_PATHS[name] || ICON_PATHS.dot;
    return '<svg class="icon '+(cls||'')+'" viewBox="0 0 24 24" aria-hidden="true">'+body+'</svg>';
  };

  /* ---------------- Button ---------------- */
  App.Button = function(opts){
    opts = opts||{};
    var cls = ['btn'];
    if(opts.variant) cls.push(opts.variant); // primary | accent | ghost | danger
    if(opts.size) cls.push(opts.size); // sm | lg
    if(opts.block) cls.push('block');
    if(opts.iconOnly) cls.push('icon-only');
    return '<button type="'+(opts.type||'button')+'" class="'+cls.join(' ')+'"'+(opts.id?(' id="'+opts.id+'"'):'')+(opts.disabled?' disabled':'')+(opts.attrs||'')+'>'+
      (opts.icon?App.icon(opts.icon):'')+(opts.label?('<span>'+esc(opts.label)+'</span>'):'')+'</button>';
  };

  /* ---------------- Badge / StatusBadge ---------------- */
  App.Badge = function(text, tone){ return '<span class="badge '+(tone||'neutral')+'">'+esc(text)+'</span>'; };
  App.StatusBadge = function(statusKey){
    var st = App.STATUS[statusKey] || {label:statusKey};
    return '<span class="status-pill st-'+statusKey+'"><span class="dot"></span>'+esc(st.label)+'</span>';
  };
  App.DeadlineBadge = function(nc){
    var sit = App.situacaoPrazo(nc);
    var ic = sit.tone==='late' ? App.icon('alertTriangle','sm') : (sit.tone==='soon'?App.icon('clock','sm'):'');
    return '<span class="deadline '+(sit.tone==='late'?'late':sit.tone==='soon'?'soon':'ok')+'">'+ic+esc(sit.label)+'</span>';
  };

  /* ---------------- Card / KPI Card ---------------- */
  App.Card = function(innerHtml, opts){
    opts=opts||{};
    return '<div class="card"'+(opts.id?(' id="'+opts.id+'"'):'')+(opts.style?(' style="'+opts.style+'"'):'')+'>'+
      (opts.title?('<h3>'+esc(opts.title)+'</h3>'):'')+(opts.sub?('<div class="card-sub">'+esc(opts.sub)+'</div>'):'')+
      innerHtml+'</div>';
  };
  App.KpiCard = function(opts){
    return '<div class="kpi-card tone-'+(opts.tone||'default')+'">'+
      '<div class="kpi-top"><span class="kpi-label">'+esc(opts.label)+'</span>'+(opts.icon?('<span class="kpi-icon">'+App.icon(opts.icon)+'</span>'):'')+'</div>'+
      '<div class="kpi-value">'+opts.value+'</div>'+
      (opts.extra?('<div class="kpi-extra">'+opts.extra+'</div>'):'')+
    '</div>';
  };

  /* ---------------- PageHeader ---------------- */
  App.PageHeader = function(opts){
    opts=opts||{};
    return '<div class="page-header">'+
      (opts.breadcrumb?('<div class="breadcrumb">'+opts.breadcrumb+'</div>'):'')+
      '<div class="ph-row"><div><h2>'+esc(opts.title)+'</h2>'+(opts.sub?('<div class="ph-sub">'+esc(opts.sub)+'</div>'):'')+'</div>'+
      (opts.actionsHtml?('<div class="ph-actions">'+opts.actionsHtml+'</div>'):'')+
      '</div></div>';
  };

  /* ---------------- FormField ---------------- */
  App.FormField = function(opts){
    opts=opts||{};
    var id = opts.id;
    var tag = opts.type==='textarea' ? 'textarea' : (opts.type==='select' ? 'select' : 'input');
    var attrs = ' id="'+id+'"';
    if(tag==='input'){ attrs += ' type="'+(opts.inputType||'text')+'"'; if(opts.value!==undefined) attrs += ' value="'+esc(opts.value)+'"'; }
    if(opts.placeholder) attrs += ' placeholder="'+esc(opts.placeholder)+'"';
    if(opts.required) attrs += ' required';
    if(opts.step!==undefined) attrs += ' step="'+opts.step+'"';
    var control;
    if(tag==='select'){
      control = '<select'+attrs+'>'+(opts.options||[]).map(function(o){
        var val=Array.isArray(o)?o[0]:o.value, lab=Array.isArray(o)?o[1]:o.label;
        return '<option value="'+esc(val)+'"'+((opts.value!==undefined && String(opts.value)===String(val))?' selected':'')+'>'+esc(lab)+'</option>';
      }).join('')+'</select>';
    } else if(tag==='textarea'){
      control = '<textarea'+attrs+' rows="'+(opts.rows||3)+'">'+esc(opts.value||'')+'</textarea>';
    } else {
      control = '<input'+attrs+'>';
    }
    return '<div class="field" id="fieldwrap-'+id+'">'+
      (opts.label?('<label class="field-label" for="'+id+'">'+esc(opts.label)+(opts.required?'<span class="req">*</span>':'')+(opts.optionalTag?'<span class="opt">(opcional)</span>':'')+'</label>'):'')+
      control+
      (opts.hint?('<div class="hint">'+esc(opts.hint)+'</div>'):'')+
      '<div class="error-msg hidden" data-err-for="'+id+'"></div>'+
    '</div>';
  };
  App.setFieldError = function(id, msg){
    var wrap = document.getElementById('fieldwrap-'+id);
    var err = document.querySelector('[data-err-for="'+id+'"]');
    if(!wrap||!err) return;
    if(msg){ wrap.classList.add('has-error'); err.textContent = msg; err.classList.remove('hidden'); }
    else { wrap.classList.remove('has-error'); err.classList.add('hidden'); }
  };
  App.clearFieldErrors = function(root){
    App.util.qsa('.field.has-error', root).forEach(function(f){ f.classList.remove('has-error'); });
    App.util.qsa('.error-msg', root).forEach(function(e){ e.classList.add('hidden'); });
  };

  /* ---------------- Table ---------------- */
  App.Table = function(columns, rows, opts){
    opts=opts||{};
    var thead = '<tr>'+columns.map(function(c){ return '<th>'+esc(c.label)+'</th>'; }).join('')+'</tr>';
    var tbody = rows.map(function(row){
      var cells = columns.map(function(c){ return '<td class="'+(c.cls||'')+'">'+c.render(row)+'</td>'; }).join('');
      return '<tr class="'+(opts.rowClickable?'row-click':'')+'" data-id="'+esc(row.id)+'">'+cells+'</tr>';
    }).join('');
    return '<div class="table-wrap"><table><thead>'+thead+'</thead><tbody>'+(tbody||'')+'</tbody></table></div>';
  };

  /* ---------------- Pagination ---------------- */
  App.Pagination = function(total, page, pageSize){
    var pages = Math.max(1, Math.ceil(total/pageSize));
    var from = total===0?0:(page-1)*pageSize+1;
    var to = Math.min(total, page*pageSize);
    var btns = '';
    var maxBtns = 5;
    var start = Math.max(1, page-2), end = Math.min(pages, start+maxBtns-1);
    start = Math.max(1, end-maxBtns+1);
    for(var i=start;i<=end;i++){ btns += '<button data-page="'+i+'" class="'+(i===page?'active':'')+'">'+i+'</button>'; }
    return '<div class="pagination"><span>'+from+'–'+to+' de '+total+'</span><div class="pg-btns">'+
      '<button data-page="'+(page-1)+'" '+(page<=1?'disabled':'')+'>'+App.icon('chevronLeft','sm')+'</button>'+
      btns+
      '<button data-page="'+(page+1)+'" '+(page>=pages?'disabled':'')+'>'+App.icon('chevronRight','sm')+'</button>'+
    '</div></div>';
  };

  /* ---------------- EmptyState ---------------- */
  App.EmptyState = function(opts){
    opts=opts||{};
    return '<div class="empty-state">'+
      '<div class="empty-icon">'+App.icon(opts.icon||'info','lg')+'</div>'+
      '<h4>'+esc(opts.title)+'</h4>'+(opts.text?('<p>'+esc(opts.text)+'</p>'):'')+
      (opts.actionHtml?('<div class="empty-actions">'+opts.actionHtml+'</div>'):'')+
    '</div>';
  };

  /* ---------------- Modal ---------------- */
  App.openModal = function(innerHtml, opts){
    opts=opts||{};
    var bg = document.createElement('div'); bg.className='modal-bg'; bg.id='modal-bg-'+App.util.uid();
    bg.innerHTML = '<div class="modal '+(opts.large?'modal-lg':'')+'" role="dialog" aria-modal="true">'+
      (opts.title? ('<div class="modal-head"><h3>'+esc(opts.title)+'</h3><button class="modal-close" aria-label="Fechar">'+App.icon('x')+'</button></div>') : '')+
      innerHtml+'</div>';
    document.body.appendChild(bg);
    function close(){ bg.remove(); document.removeEventListener('keydown', onKey); }
    function onKey(e){ if(e.key==='Escape') close(); }
    document.addEventListener('keydown', onKey);
    bg.addEventListener('click', function(e){ if(e.target===bg) close(); });
    var closeBtn = bg.querySelector('.modal-close');
    if(closeBtn) closeBtn.onclick = close;
    bg.__close = close;
    return bg;
  };
  App.closeModal = function(bg){ if(bg && bg.__close) bg.__close(); };

  App.confirmDialog = function(opts){
    return new Promise(function(resolve){
      var tone = opts.tone||'primary';
      var bg = App.openModal(
        '<div class="confirm-modal tone-'+tone+'">'+
          '<div class="confirm-icon">'+App.icon(tone==='danger'?'alertTriangle':'info')+'</div>'+
          '<h3 style="margin-bottom:6px;">'+esc(opts.title)+'</h3>'+
          '<p class="small" style="font-size:.85rem;color:var(--ink-soft);">'+esc(opts.message||'')+'</p>'+
          '<div class="close-row">'+
            App.Button({label:opts.cancelLabel||'Cancelar', variant:'ghost'}) +
            App.Button({label:opts.confirmLabel||'Confirmar', variant:(tone==='danger'?'danger':'primary')}) +
          '</div>'+
        '</div>'
      );
      var okBtn = bg.querySelector('.confirm-modal .btn.primary, .confirm-modal .btn.danger');
      var cancelBtn = bg.querySelector('.confirm-modal .btn.ghost');
      okBtn.onclick = function(){ App.closeModal(bg); resolve(true); };
      cancelBtn.onclick = function(){ App.closeModal(bg); resolve(false); };
    });
  };

  /* ---------------- Toast ---------------- */
  function toastStack(){
    var s = document.getElementById('toast-stack');
    if(!s){ s = document.createElement('div'); s.id='toast-stack'; s.className='toast-stack'; document.body.appendChild(s); }
    return s;
  }
  App.toast = function(message, type){
    type = type||'info';
    var icon = type==='success'?'checkCircle':type==='error'?'x':type==='warn'?'alertTriangle':'info';
    var el = document.createElement('div');
    el.className = 'toast '+type;
    el.innerHTML = '<span class="toast-icon">'+App.icon(icon,'sm')+'</span><span>'+esc(message)+'</span><button class="toast-close">'+App.icon('x','sm')+'</button>';
    toastStack().appendChild(el);
    var timer = setTimeout(remove, 4200);
    el.querySelector('.toast-close').onclick = remove;
    function remove(){ clearTimeout(timer); if(el.parentNode) el.parentNode.removeChild(el); }
  };

  /* ---------------- FilterPanel ---------------- */
  App.FilterPanel = function(fieldsHtml, opts){
    opts=opts||{};
    return '<div class="filter-panel" id="'+opts.id+'">'+
      '<div class="filter-grid">'+fieldsHtml+'</div>'+
      '<div class="filter-actions">'+
        App.Button({label:'Limpar filtros', variant:'ghost', size:'sm', id:opts.id+'-clear'})+
      '</div></div>';
  };
  App.FilterToggle = function(id, label){
    return '<button class="btn filter-toggle" id="'+id+'">'+App.icon('filter','sm')+'<span>'+esc(label||'Filtros')+'</span><span class="count hidden" id="'+id+'-count">0</span>'+App.icon('chevronDown','sm')+'</button>';
  };

  /* ---------------- Timeline ---------------- */
  App.Timeline = function(historico){
    var hist = (historico||[]).slice().sort(function(a,b){ return new Date(a.dataHora)-new Date(b.dataHora); });
    if(!hist.length) return App.EmptyState({icon:'clock', title:'Sem eventos registrados'});
    var rows = hist.map(function(h,i){
      var tone='';
      var stNovo = App.STATUS[h.statusNovo];
      if(stNovo && stNovo.group==='encerrado') tone='tone-good';
      if(h.statusNovo==='disposicao_recusada'||h.statusNovo==='nao_eficaz') tone='tone-bad';
      if(h.statusNovo==='disposicao_aprovada'||h.statusNovo==='eficaz') tone='tone-accent';
      return '<div class="tl-row '+tone+'"><div class="tl-rail"><div class="tl-dot"></div><div class="tl-line"></div></div>'+
        '<div class="tl-body"><div class="tl-when">'+App.util.fmtDateTime(h.dataHora)+'</div>'+
        '<div class="tl-what">'+(h.statusAnterior?esc(App.STATUS[h.statusAnterior]?App.STATUS[h.statusAnterior].label:h.statusAnterior)+' → ':'')+esc(stNovo?stNovo.label:h.statusNovo)+'</div>'+
        '<div class="tl-who">'+esc(h.usuarioNome)+'</div>'+
        (h.comentario?('<div class="tl-comment">'+esc(h.comentario)+'</div>'):'')+
        '</div></div>';
    }).join('');
    return '<div class="timeline">'+rows+'</div>';
  };

  /* ---------------- FlowStepper ---------------- */
  App.FlowStepper = function(statusAtual){
    var steps = App.FLOW_STEPS;
    var curIdx = -1;
    steps.forEach(function(s,i){ if(s.statuses.indexOf(statusAtual)>=0) curIdx=i; });
    var blocked = (statusAtual==='disposicao_recusada' || statusAtual==='nao_eficaz');
    return '<div class="flow-stepper">'+steps.map(function(s,i){
      var cls = 'flow-step';
      var node = (i+1);
      if(i<curIdx) { cls+=' done'; node = App.icon('check','sm'); }
      else if(i===curIdx){ cls += blocked ? ' blocked' : ' current'; node = blocked ? App.icon('x','sm') : (i+1); }
      return '<div class="'+cls+'"><div class="flow-track"></div><div class="flow-node">'+node+'</div><div class="flow-label">'+esc(s.label)+'</div></div>';
    }).join('')+'</div>';
  };

  /* ---------------- EvidenceCard / galeria ---------------- */
  App.EvidenceGallery = function(anexos){
    if(!anexos || !anexos.length) return App.EmptyState({icon:'image', title:'Nenhuma evidência anexada', text:'Anexe fotos com legenda, km, pista e data para compor o relatório fotográfico.'});
    var cards = anexos.map(function(a,i){
      return '<div class="evidence-card" data-idx="'+i+'">'+
        (a.thumb? ('<img class="ev-thumb" src="'+a.thumb+'" alt="'+esc(a.legenda||'evidência')+'">') : '<div class="ev-thumb-empty">'+App.icon('image','lg')+'</div>')+
        '<div class="ev-body"><div class="ev-caption">'+esc(a.legenda||a.nomeArquivo||'Evidência')+'</div>'+
        '<div class="ev-meta">'+[a.km?('km '+a.km):'',a.pista?('pista '+a.pista):'',a.faixa?('faixa '+a.faixa):'',a.dataFoto?App.util.fmtDate(a.dataFoto):''].filter(Boolean).join(' · ')+'</div></div>'+
      '</div>';
    }).join('');
    return '<div class="evidence-grid">'+cards+'</div>';
  };
  App.openLightbox = function(anexo){
    var bg = document.createElement('div'); bg.className='lightbox-bg';
    bg.innerHTML = '<button class="lightbox-close">'+App.icon('x')+'</button>'+
      (anexo.thumb?('<div><img src="'+anexo.thumb+'"><div class="lightbox-cap">'+esc(anexo.legenda||'')+' '+[anexo.km?('· km '+anexo.km):'',anexo.pista?('· pista '+anexo.pista):'',anexo.dataFoto?('· '+App.util.fmtDate(anexo.dataFoto)):''].filter(Boolean).join(' ')+'</div></div>'):'');
    document.body.appendChild(bg);
    function close(){ bg.remove(); }
    bg.addEventListener('click', function(e){ if(e.target===bg) close(); });
    bg.querySelector('.lightbox-close').onclick = close;
  };

  /* ---------------- helpers de HTML simples ---------------- */
  App.selectHtml = function(id,label,opts,selected){
    return '<div class="field"><label class="field-label" for="'+id+'">'+esc(label)+'</label><select id="'+id+'">'+opts.map(function(o){
      var val=Array.isArray(o)?o[0]:o.value, lab=Array.isArray(o)?o[1]:o.label;
      return '<option value="'+esc(val)+'"'+(selected!==undefined && String(selected)===String(val)?' selected':'')+'>'+esc(lab)+'</option>';
    }).join('')+'</select></div>';
  };
  App.inputHtml = function(id,label,type,val,extra){
    return '<div class="field"><label class="field-label" for="'+id+'">'+esc(label)+'</label><input id="'+id+'" type="'+type+'" value="'+esc(val||'')+'" '+(extra||'')+'></div>';
  };
})(window.App);
