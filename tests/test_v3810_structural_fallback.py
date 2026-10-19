from io import BytesIO
from pathlib import Path
import pytest
from zipfile import ZipFile
import json

import qualimatch.quality_excel_writer as q
from qualimatch.normalizers import norm_header
from qualimatch.xlsx_xml import sheet_path


def _analysis_without_quality_template():
    return {
        'certificates': [{
            'contractor': 'ARENA',
            'certificate': 'BI330-9999',
            'parse_status': 'CARREGADO',
            'warnings': [],
            'quality_fields': {
                'Nº CERTIFICADO Vv': 9999,
                'TOTAL CPs': 1,
                'STATUS Vv rotina': 'APROVADO',
                'STATUS ESPESSURA rotina': 'APROVADO',
            },
            'lines': [{
                'match_status': 'VINCULADO',
                'measurement': {
                    'id': 777,
                    'line_measurement': '9876',
                    'road': 'BR-369',
                    'direction': 'SUL',
                    'lane': '1',
                },
            }],
        }]
    }


def _measurement():
    raw = {
        'LINHA': 9876,
        'REF MEDIÇÃO': 14,
        'EQUIPE': 'EQUIPE 03',
        'TURNO': 'NOTURNO',
        'FISCAL': 'Teste QualiMatch',
        'DATA': 46254,
        'MÊS': 'AGOSTO',
        'ANO': 2026,
        'RODOVIA': 'BR-369',
        'SENTIDO': 'SUL',
        'KMI': 101000,
        'KMF': 101500,
        'FAIXA': 1,
        'ESCOPO': 'PREVISTO',
        'EXTENSÃO (m)': 500,
        'LARGURA (m)': 3.6,
        'ESPESSURA (m)': 0.04,
        'TIPO': 'FAIXA DE ROL.',
        'DMT FRESADO (km)': 15,
        'CÓDIGO TRAÇO': 1305,
        'AREA MED (m²)': 1800,
        'VOLUME MASSA (m³)': 72,
        'VOLUME FRESADO (m³)': 70,
        'QUANT PROJETO (ton)': 180,
    }
    return {
        'id': 777,
        'contractor': 'ARENA',
        'source_row': 5000,
        'line_measurement': '9876',
        'ref_measurement': '14',
        'team': 'EQUIPE 03',
        'inspector': 'Teste QualiMatch',
        'date': '2026-08-20',
        'road': 'BR-369',
        'direction': 'SUL',
        'kmi': 101000,
        'kmf': 101500,
        'lane': '1',
        'extension_m': 500.0,
        'width_m': 3.6,
        'thickness_m': 0.04,
        'scope': 'PREVISTO',
        'mass_type': '',
        'area_m2': 1800.0,
        'paint_m2': None,
        'volume_mass_m3': 72.0,
        'volume_milled_m3': 70.0,
        'quantity_t': 180.0,
        'dmt_milled_km': 15.0,
        'raw_json': json.dumps(raw, ensure_ascii=False),
        'raw': raw,
    }


def test_write_plan_uses_structural_fallback_when_measurement_has_no_quality_row(monkeypatch):
    measurement = _measurement()

    def fake_rows(sql, params=()):
        if 'line_measurement IN' in sql:
            return []
        if 'ORDER BY source_row DESC LIMIT 250' in sql:
            return [{
                'source_row': 21,
                'line_measurement': '22',
                'date': '2025-07-15',
                'road': 'BR-376',
                'direction': 'NORTE',
                'lane': '2',
                'raw_json': '{}',
            }]
        if 'FROM quality_rows' in sql:
            # consulta de certificado existente: linha sem BI não é existente
            return [{
                'source_row': 21,
                'line_measurement': '22',
                'date': '2025-07-15',
                'road': 'BR-376',
                'direction': 'NORTE',
                'lane': '2',
                'raw_json': '{}',
            }]
        return []

    monkeypatch.setattr(q, 'rows', fake_rows)
    monkeypatch.setattr(q, 'row', lambda sql, params=(): measurement if 'FROM measurements' in sql else None)
    monkeypatch.setattr(q, '_projected_first_append_row', lambda contractor: 4000)

    out = q.enrich_write_plan(_analysis_without_quality_template())
    plan = out['certificates'][0]['excel_write']
    assert plan['ready'] is True
    assert plan['mode'] == 'ADICIONAR_NOVO'
    assert plan['assignments'][0]['template_strategy'] == 'STRUCTURAL_FALLBACK'
    assert plan['assignments'][0]['template_row'] == 21
    assert plan['assignments'][0]['measurement_id'] == 777


def test_structural_clone_clears_old_values_but_preserves_formula():
    row = (
        b'<row r="10">'
        b'<c r="A10" s="1"><v>123</v></c>'
        b'<c r="B10" s="2" t="inlineStr"><is><t>ANTIGO</t></is></c>'
        b'<c r="C10" s="3"><f>A10+1</f><v>124</v></c>'
        b'</row>'
    )
    out = q._clear_non_formula_cells(row, 10)
    assert b'<c r="A10" s="1"/>' in out
    assert b'<c r="B10" s="2"/>' in out
    assert b'<f>A10+1</f>' in out


def test_moved_exact_template_becomes_safe_structural_fallback(monkeypatch):
    spec = {
        'template_line_measurement': '3690',
        'template_strategy': 'EXACT_MEASUREMENT',
        'measurement_id': 777,
    }
    monkeypatch.setattr(q, '_measurement_snapshot', lambda mid: _measurement() if int(mid) == 777 else None)

    assert q._recover_append_template(spec, '1935') is True
    assert spec['template_strategy'] == 'STRUCTURAL_FALLBACK'


def test_real_arena_workbook_can_append_from_generic_structural_template(monkeypatch):
    source = Path('/mnt/data/BD.QUALIDADE_ARENA_v02(5).xlsx')
    if not source.exists():
        pytest.skip('Planilha real opcional não disponível neste ambiente.')
    measurement = _measurement()
    monkeypatch.setattr(q, '_measurement_snapshot', lambda mid: measurement if int(mid) == 777 else None)
    monkeypatch.setattr(q, '_max_quality_id', lambda contractor: 9000)

    cert = {
        'contractor': 'ARENA',
        'certificate': 'BI330-9999',
        'quality_fields': {
            'Nº CERTIFICADO Vv': 9999,
            'TOTAL CPs': 1,
            'STATUS Vv rotina': 'APROVADO',
            'STATUS ESPESSURA rotina': 'APROVADO',
        },
        'excel_write': {
            'ready': True,
            'mode': 'ADICIONAR_NOVO',
            'final_status': 'APROVADO',
            'assignments': [{
                'template_row': 21,
                'template_line_measurement': '22',
                'template_strategy': 'STRUCTURAL_FALLBACK',
                'measurement_id': 777,
                'line_measurement': '9876',
            }],
        },
    }
    generated = q.patch_quality_workbook(source, 'ARENA', [cert])
    assert generated.appended_rows == 1
    target = generated.target_rows[0]

    with ZipFile(BytesIO(generated.content), 'r') as z:
        sp = sheet_path(z, 'BD_QUALI')
        tp = q._resolve_table_path(z, sp)
        _, _, _, headers, _ = q._table_info(z.read(tp))
        sheet = z.read(sp)
        found = q._find_row(sheet, target, 0)
        assert found is not None
        row_xml = found[2]
        assert q._read_simple_cell(row_xml, headers[norm_header('LINHA MEDIÇÃO')], target) == '9876'
        assert q._read_simple_cell(row_xml, headers[norm_header('RODOVIA')], target) == 'BR-369'
        assert q._read_simple_cell(row_xml, headers[norm_header('Nº CERTIFICADO Vv')], target) == '9999'
        # A linha genérica 21 tinha KIT ID; o fallback não pode transportar
        # dados operacionais de outra medição.
        kit_col = headers[norm_header('KIT ID')]
        assert q._read_simple_cell(row_xml, kit_col, target) == ''
