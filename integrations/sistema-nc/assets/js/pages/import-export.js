window.App = window.App || {};
(function(App){
  "use strict";
  var qs=App.util.qs,esc=App.util.esc;
  async function render(mount){
    var sede=App.sedeAtual();
    if(!App.perm.podeConfigurar()){
      mount.innerHTML=App.PageHeader({title:'Importar / Exportar'})+'<div class="page-body">'+App.EmptyState({icon:'swap',title:'Sem permissão',text:'A importação e a exportação estão disponíveis para administradores.'})+'</div>';return;
    }
    mount.innerHTML=App.PageHeader({title:'Importar / Exportar',sub:'Migração da planilha de controle e exportação dos registros desta SEDE.'})+
      '<div class="page-body">'+
      App.Card('<div class="field"><label class="field-label" for="local-path">Caminho completo da planilha</label><div class="input-group"><input id="local-path" type="text" value="'+esc(sede.planilhaLocalPath||'')+'" placeholder="C:\\Pasta\\controle.xlsx"><button class="btn primary" id="btn-local" type="button">Salvar e ler planilha</button></div><div class="hint">O caminho fica salvo para esta SEDE e o arquivo é lido diretamente deste computador.</div></div><div id="local-report"></div>',{title:'Usar planilha por caminho local'})+
      App.Card('<div class="dropzone" id="dropzone"><div class="dz-icon">'+App.icon('upload')+'</div><h4>Arraste uma planilha para cá</h4><div class="small" style="color:var(--ink-faint);margin:6px 0 12px;">ou</div>'+App.Button({label:'Selecionar arquivo',variant:'primary',size:'sm',id:'btn-selecionar'})+'<div class="dz-sub">.xlsx, .xlsm ou .xls</div><input type="file" id="import-file" accept=".xlsx,.xlsm,.xls" hidden></div><div id="import-report" style="margin-top:16px;"></div>',{title:'Importar planilha Excel'})+
      App.Card('<div class="export-card"><div><h4 style="margin-bottom:4px;">Exportar registros da SEDE '+esc(sede.sigla)+'</h4><p class="small" style="color:var(--ink-faint);">Gera uma planilha .xlsx com os registros armazenados no PostgreSQL.</p></div>'+App.Button({label:'Exportar Excel',icon:'download',variant:'primary',id:'btn-export'})+'</div>',{title:'Exportação'})+'</div>';
    var dz=qs('#dropzone'),input=qs('#import-file');
    qs('#btn-local').onclick=async function(){
      var caminho=qs('#local-path').value.trim(),out=qs('#local-report');
      if(!caminho){out.innerHTML='<div class="info-box">Informe o caminho completo da planilha.</div>';return;}
      out.innerHTML='<p class="small">Lendo a planilha...</p>';
      try{
        var p=await App.api.post('/api/import/preview-local',{sedeId:App.state.sedeId,caminho:caminho}),c=p.counts;
        if(caminho!==(sede.planilhaLocalPath||'')){
          await App.api.patch('/api/sedes/'+App.state.sedeId,{planilhaLocalPath:caminho});
          sede.planilhaLocalPath=caminho;
        }
        var remocoes=c.remocoes||0;
        out.innerHTML='<p class="small">'+p.totalRows+' linha(s) encontradas na aba '+esc(p.sheetName)+'.</p><div class="import-report"><div class="ir-item ok"><div class="ir-n">'+c.validos+'</div><div class="ir-l">Válidas</div></div><div class="ir-item dup"><div class="ir-n">'+c.duplicados+'</div><div class="ir-l">Duplicadas</div></div><div class="ir-item ok"><div class="ir-n">'+c.atualizacoes+'</div><div class="ir-l">Atualizações</div></div><div class="ir-item bad"><div class="ir-n">'+(c.rejeitados+c.erros)+'</div><div class="ir-l">Rejeitadas/erros</div></div><div class="ir-item bad"><div class="ir-n">'+remocoes+'</div><div class="ir-l">Fora da planilha</div></div></div>'+(remocoes?'<div class="info-box" style="margin:12px 0;color:var(--danger);">Ao confirmar, '+remocoes+' registro(s) que não estão neste Excel serão excluídos desta SEDE.</div>':'')+((c.validos+c.atualizacoes+remocoes)>0?App.Button({label:'Sincronizar somente com o Excel de '+esc(sede.sigla),variant:'primary',id:'confirmar-local'}):'');
        var btn=qs('#confirmar-local');if(btn)btn.onclick=async function(){if(remocoes&&!window.confirm('Esta sincronização excluirá '+remocoes+' registro(s) que não estão no Excel. Deseja continuar?'))return;btn.disabled=true;try{var r=await App.api.post('/api/import/'+p.importId+'/confirmar',{somentePlanilha:true});App.toast((r.validCount||0)+' importado(s) e '+(r.removedCount||0)+' removido(s).','success');out.innerHTML+='<p class="small" style="color:var(--success);margin-top:10px;">Sincronização concluída. O sistema agora reflete somente esta planilha.</p>';}catch(e){App.toast(e.message,'danger');}finally{btn.disabled=false;}};
      }catch(e){out.innerHTML='<div class="info-box" style="color:var(--danger);">'+esc(e.message)+'</div>';}
    };
    qs('#btn-selecionar').onclick=function(){input.click();};
    dz.onclick=function(e){if(!e.target.closest('#btn-selecionar'))input.click();};
    ['dragenter','dragover'].forEach(function(n){dz.addEventListener(n,function(e){e.preventDefault();dz.classList.add('drag-over');});});
    ['dragleave','drop'].forEach(function(n){dz.addEventListener(n,function(e){e.preventDefault();dz.classList.remove('drag-over');});});
    dz.addEventListener('drop',function(e){var f=e.dataTransfer.files&&e.dataTransfer.files[0];if(f)preview(f);});input.onchange=function(){if(input.files[0])preview(input.files[0]);};
    async function preview(file){
      var out=qs('#import-report');out.innerHTML='<p class="small">Analisando a planilha...</p>';
      try{
        var fd=new FormData();fd.append('arquivo',file);fd.append('sedeId',App.state.sedeId);
        var p=await App.api.request('/api/import/preview',{method:'POST',body:fd}),c=p.counts;
        out.innerHTML='<p class="small" style="color:var(--ink-faint);margin-bottom:10px;">'+p.totalRows+' linha(s) encontrada(s) na aba '+esc(p.sheetName)+'.</p><div class="import-report"><div class="ir-item ok"><div class="ir-n">'+c.validos+'</div><div class="ir-l">Válidas</div></div><div class="ir-item dup"><div class="ir-n">'+c.duplicados+'</div><div class="ir-l">Duplicadas</div></div><div class="ir-item ok"><div class="ir-n">'+c.atualizacoes+'</div><div class="ir-l">Atualizações</div></div><div class="ir-item bad"><div class="ir-n">'+(c.rejeitados+c.erros)+'</div><div class="ir-l">Rejeitadas/erros</div></div></div>'+((c.validos+c.atualizacoes)>0?App.Button({label:'Confirmar importação para '+esc(sede.sigla),variant:'primary',id:'confirmar-import'}):'');
        var btn=qs('#confirmar-import');if(btn)btn.onclick=async function(){btn.disabled=true;try{var r=await App.api.post('/api/import/'+p.importId+'/confirmar',{});App.toast((r.validCount||0)+' registro(s) importado(s).','success');out.innerHTML+='<p class="small" style="color:var(--success);margin-top:10px;">Importação concluída.</p>';}catch(e){App.toast(e.message,'danger');}finally{btn.disabled=false;}};
      }catch(e){out.innerHTML='<div class="info-box" style="color:var(--danger);">'+esc(e.message)+'</div>';}
    }
    qs('#btn-export').onclick=function(){window.location.href='/api/export/ncs.xlsx?sedeId='+encodeURIComponent(App.state.sedeId);};
  }
  App.pages=App.pages||{};App.pages.importExport={render:render};
})(window.App);
