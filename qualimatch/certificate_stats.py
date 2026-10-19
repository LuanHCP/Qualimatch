from __future__ import annotations
import json, statistics
from functools import lru_cache
from typing import Any

K_BY_N={5:1.55,6:1.41,7:1.36,8:1.31,9:1.25,10:1.21,11:1.19,12:1.16,13:1.13,14:1.11,15:1.10,16:1.08,17:1.06,18:1.05,19:1.04,20:1.02,21:1.01}
LIMITS={'vv_min':3.5,'vv_max':7.5,'ratio_xmin':95.0,'ratio_individual':90.0}

def _f(v):
    try:return float(v) if v is not None else None
    except:return None

def _stats(vals:list[float],k:float|None):
    # Reuse pure arithmetic only: changed samples/k produce a different key.
    # Copy because printed BI330 values can override this dictionary per call.
    return dict(_cached_stats(tuple(vals), k))


@lru_cache(maxsize=4096)
def _cached_stats(vals:tuple[float,...],k:float|None):
    if not vals:return {'mean':None,'std':None,'xmin':None,'xmax':None,'min':None,'max':None}
    mean=statistics.mean(vals); sd=statistics.stdev(vals) if len(vals)>1 else 0.0; kk=k or 0.0
    return {'mean':round(mean,2),'std':round(sd,2),'xmin':round(mean-kk*sd,2),'xmax':round(mean+kk*sd,2),'min':round(min(vals),2),'max':round(max(vals),2)}

def summarize_phase(samples:list[dict[str,Any]], printed:dict[str,Any]|None=None)->dict[str,Any]:
    printed=printed or {}; n=len(samples); k=_f(printed.get('k')) or K_BY_N.get(n,1.0 if n>=22 else None)
    vv=[_f(x.get('voids_pct')) for x in samples]; vv=[x for x in vv if x is not None]
    ratio=[_f(x.get('ratio_ab_pct')) for x in samples]; ratio=[x for x in ratio if x is not None]
    thick=[_f(x.get('thickness_exec_cm')) for x in samples]; thick=[x for x in thick if x is not None]
    proj=[_f(x.get('thickness_project_cm')) for x in samples]; proj=[x for x in proj if x is not None]
    svv=_stats(vv,k); sratio=_stats(ratio,k); sth=_stats(thick,k)

    # Vv: os valores dos CPs são a fonte de verdade.
    # O parser já resolve a prioridade entre "Volume de Vazios (%)" e
    # "Volume de Vazios com Plástico Filme (%)". Portanto, quando os CPs
    # possuem Vv extraído, NÃO sobrescrevemos média/desvio/Xmin/Xmax com o
    # quadro estatístico impresso do BI330, pois esse quadro pode ter sido
    # calculado com a coluna de Vv sem plástico filme.
    #
    # Os valores impressos continuam como fallback para PDFs em que nenhum
    # Vv individual pôde ser extraído.
    if not vv:
        for key,target in [('vv_mean_pct','mean'),('vv_std_pct','std'),('vv_xmin_pct','xmin'),('vv_xmax_pct','xmax')]:
            if _f(printed.get(key)) is not None:
                svv[target]=_f(printed[key])

    # A/B: mantém o comportamento anterior, priorizando o quadro estatístico
    # impresso quando disponível.
    for key,target in [('ratio_mean_pct','mean'),('ratio_std_pct','std'),('ratio_xmin_pct','xmin'),('ratio_xmax_pct','xmax')]:
        if _f(printed.get(key)) is not None:
            sratio[target]=_f(printed[key])
    vv_fail=sum(1 for x in vv if x<LIMITS['vv_min'] or x>LIMITS['vv_max'])
    ratio_fail=sum(1 for x in ratio if x<LIMITS['ratio_individual'])
    status_vv='APROVADO' if svv['xmin'] is not None and svv['xmax'] is not None and svv['xmin']>=LIMITS['vv_min'] and svv['xmax']<=LIMITS['vv_max'] else ('REPROVADO' if vv else '')
    status_th='APROVADO' if sratio['xmin'] is not None and sratio['xmin']>=LIMITS['ratio_xmin'] else ('REPROVADO' if ratio else '')
    if str(printed.get('status_vv') or '').upper() in {'APROVADO','REPROVADO'}:
        status_vv=str(printed.get('status_vv')).upper()
    if str(printed.get('status_thickness') or '').upper() in {'APROVADO','REPROVADO'}:
        status_th=str(printed.get('status_thickness')).upper()
    overall='APROVADO' if status_vv=='APROVADO' and status_th=='APROVADO' else ('REPROVADO' if 'REPROVADO' in {status_vv,status_th} else '')
    if printed.get('result_unavailable'):
        # O documento oficial contém #N/D: não inventar um parecer estatístico.
        k = None
        svv['xmin'] = svv['xmax'] = sratio['xmin'] = sratio['xmax'] = None
        status_vv = status_th = overall = ''
    return {
        'sample_count':n,'k':k,
        'vv_mean_pct':svv['mean'],'vv_std_pct':svv['std'],'vv_xmin_pct':svv['xmin'],'vv_xmax_pct':svv['xmax'],'vv_min_sample':svv['min'],'vv_max_sample':svv['max'],
        'vv_failed_samples':vv_fail,'vv_failed_pct':round(vv_fail/len(vv)*100,1) if vv else None,'status_vv':status_vv,
        'ratio_mean_pct':sratio['mean'],'ratio_std_pct':sratio['std'],'ratio_xmin_pct':sratio['xmin'],'ratio_xmax_pct':sratio['xmax'],'ratio_min_sample':sratio['min'],'ratio_max_sample':sratio['max'],
        'ratio_failed_samples':ratio_fail,'ratio_failed_pct':round(ratio_fail/len(ratio)*100,1) if ratio else None,'status_thickness':status_th,
        'thickness_mean_cm':sth['mean'],'thickness_min_cm':sth['min'],'thickness_max_cm':sth['max'],'project_thickness_mean_cm':round(statistics.mean(proj),2) if proj else None,
        'overall_status':overall,
    }

def raw_json(cert:dict[str,Any])->dict[str,Any]:
    try:return json.loads(cert.get('raw_json') or '{}')
    except:return {}
