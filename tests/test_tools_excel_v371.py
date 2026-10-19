import json

import qualimatch.quality_excel_writer as q


def _analysis(lines=2):
    return {
        'certificates': [{
            'contractor': 'ARENA',
            'certificate': 'BI330-0123',
            'parse_status': 'CARREGADO',
            'warnings': [],
            'quality_fields': {
                'Nº CERTIFICADO Vv': 123,
                'TOTAL CPs': lines,
                'STATUS Vv rotina': 'APROVADO',
                'STATUS ESPESSURA rotina': 'APROVADO',
            },
            'lines': [
                {'match_status': 'VINCULADO', 'measurement': {'line_measurement': '500'}}
                for _ in range(lines)
            ],
        }]
    }


def test_write_plan_existing_certificate_updates_when_count_matches(monkeypatch):
    def fake_rows(sql, params=()):
        if 'FROM quality_rows' in sql:
            return [
                {'source_row': 20, 'line_measurement': '500', 'date': '2026-08-12', 'road': 'BR-376', 'direction': 'SUL', 'lane': '1', 'raw_json': json.dumps({'Nº CERTIFICADO Vv': 123})},
                {'source_row': 21, 'line_measurement': '500', 'date': '2026-08-12', 'road': 'BR-376', 'direction': 'SUL', 'lane': '1', 'raw_json': json.dumps({'Nº CERTIFICADO Vv': 123})},
            ]
        return []
    monkeypatch.setattr(q, 'rows', fake_rows)
    out = q.enrich_write_plan(_analysis(2))
    plan = out['certificates'][0]['excel_write']
    assert plan['ready'] is True
    assert plan['mode'] == 'ATUALIZAR_EXISTENTE'
    assert [x['target_row'] for x in plan['assignments']] == [20, 21]
    assert out['summary']['excel_ready_rows'] == 2


def test_write_plan_completes_partially_existing_certificate(monkeypatch):
    def fake_rows(sql, params=()):
        if 'FROM quality_rows' in sql:
            return [
                {'source_row': 20, 'line_measurement': '500', 'date': '2026-08-12', 'road': 'BR-376', 'direction': 'SUL', 'lane': '1', 'raw_json': json.dumps({'Nº CERTIFICADO Vv': 123})},
            ]
        return []
    monkeypatch.setattr(q, 'rows', fake_rows)
    out = q.enrich_write_plan(_analysis(2))
    plan = out['certificates'][0]['excel_write']
    assert plan['ready'] is True
    assert plan['mode'] == 'ATUALIZAR_E_COMPLETAR'
    assert len(plan['assignments']) == 2
    assert out['summary']['excel_blocked_certificates'] == 0


def test_write_plan_new_certificate_uses_measurement_template(monkeypatch):
    calls = {'n': 0}
    def fake_rows(sql, params=()):
        if 'FROM quality_rows' not in sql:
            return []
        calls['n'] += 1
        if 'line_measurement IN' in sql:
            return [
                {'source_row': 30, 'line_measurement': '500', 'date': '2026-08-12', 'road': 'BR-376', 'direction': 'SUL', 'lane': '1', 'raw_json': '{}'},
            ]
        return []
    monkeypatch.setattr(q, 'rows', fake_rows)
    out = q.enrich_write_plan(_analysis(2))
    plan = out['certificates'][0]['excel_write']
    assert plan['ready'] is True
    assert plan['mode'] == 'ADICIONAR_NOVO'
    assert [x['template_row'] for x in plan['assignments']] == [30, 30]


def test_setting_self_closing_cell_does_not_remove_neighbor_formula():
    row = (
        b'<row r="10"><c r="CJ10" s="1"/>'
        b'<c r="CK10" s="2"><f>_xlfn.XLOOKUP(CJ10,A:A,B:B)</f><v>1.2</v></c>'
        b'<c r="CL10" s="1"/></row>'
    )
    out = q._set_cell(row, 'CJ', 10, 9)
    assert b'<c r="CJ10" s="1"><v>9</v></c>' in out
    assert b'r="CK10"' in out
    assert b'XLOOKUP' in out
    assert b'r="CL10"' in out


def test_clone_row_materializes_shared_formula_and_preserves_formula_neighbors():
    row = (
        b'<row r="10">'
        b'<c r="A10"><f t="shared" si="7"/><v>99</v></c>'
        b'<c r="B10"><f>C10+1</f><v>3</v></c>'
        b'</row>'
    )
    out = q._clone_row(row, 10, 20, {'7': (2, 'C2+5')})
    assert b'r="A20"' in out and b'<f>C20+5</f>' in out
    assert b'r="B20"' in out and b'<f>C20+1</f>' in out
    assert b't="shared"' not in out


def test_final_status_uses_counterproof_when_present():
    assert q._final_status({'STATUS Vv rotina':'APROVADO','STATUS ESPESSURA rotina':'APROVADO'}) == 'APROVADO'
    assert q._final_status({'STATUS Vv rotina':'P CONTRA PROVA','STATUS ESPESSURA rotina':'APROVADO'}) == 'P. CONTRA PROVA'
    assert q._final_status({'Nº CERTIFICADO Vv CP': 123, 'STATUS Vv CP':'APROVADO','STATUS ESPESSURA CP':'APROVADO'}) == 'APROVADO CP'
    assert q._final_status({'Nº CERTIFICADO Vv CP': 123, 'STATUS Vv CP':'REPROVADO','STATUS ESPESSURA CP':'APROVADO'}) == 'REP Vv'
