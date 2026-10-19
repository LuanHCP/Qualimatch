from types import SimpleNamespace

import pytest

from qualimatch import pdf_reader
from qualimatch.certificate_stats import summarize_phase


def test_image_only_pdf_is_not_imported_as_empty_certificate(monkeypatch):
    page = SimpleNamespace(extract_text=lambda *args, **kwargs: '')
    monkeypatch.setattr(pdf_reader, 'PdfReader', lambda path: SimpleNamespace(pages=[page]))
    with pytest.raises(ValueError, match='sem texto extraível'):
        pdf_reader.parse_pdf('BI330-0480-PAVIDEZ.pdf', 'PAVIDEZ')


def test_explicit_unavailable_result_does_not_invent_approval():
    samples = [{'voids_pct':11.4,'ratio_ab_pct':234.0,'thickness_exec_cm':4.68},
               {'voids_pct':10.3,'ratio_ab_pct':99.5,'thickness_exec_cm':3.98}]
    result = summarize_phase(samples, {'result_unavailable':True,'vv_mean_pct':8.2})
    assert result['sample_count'] == 2
    assert result['vv_mean_pct'] == 8.2
    assert result['overall_status'] == result['status_vv'] == result['status_thickness'] == ''
    assert result['k'] is result['vv_xmin_pct'] is result['ratio_xmin_pct'] is None
