from pathlib import Path
from qualimatch.certificate_stats import summarize_phase

ROOT=Path(__file__).parents[1]

def test_manual_phase_status_overrides_are_respected():
    samples=[{'voids_pct':5.0,'ratio_ab_pct':100.0,'thickness_exec_cm':4.0,'thickness_project_cm':4.0}]
    out=summarize_phase(samples, {'status_vv':'REPROVADO','status_thickness':'APROVADO'})
    assert out['status_vv']=='REPROVADO'
    assert out['status_thickness']=='APROVADO'
    assert out['overall_status']=='REPROVADO'


def test_ui_has_luan_author_and_manual_edit_controls():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    js=(ROOT/'frontend/static/app.js').read_text(encoding='utf-8')
    assert 'Desenvolvido por Luan' in html
    assert 'Editar resumo/status' in js
    assert 'editCertificateSample' in js
    assert 'Selecionar medição...' in js
