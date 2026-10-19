from pathlib import Path

from qualimatch.pdf_reader import _parse_sample_line, parse_pdf

ROOT = Path(__file__).resolve().parents[1]


def test_rice_gmm_is_extracted_from_cp_row():
    s = _parse_sample_line(
        "5 02/09/2025 SIM SUL 1 306+922 EX 4,45 4,00 111,3% 101,10 2,634 787,60 792,80 478,30 1,65 6.1 314,50 2,497 5,2%",
        "CONTRA_PROVA",
    )
    assert s is not None
    assert s.rice_gmm == 2.634
    assert s.gmb == 2.497
    assert s.voids_pct == 5.2


def test_real_pdf_recovers_rice_when_fixture_exists():
    pdf = ROOT / "data/certificados/ARENA/_old_BI330-0063-ARENA_BR376_TR1288-29.09.25D.pdf"
    if not pdf.exists():
        return
    cert = parse_pdf(pdf, "ARENA")
    assert cert.samples
    assert any(s.rice_gmm is not None for s in cert.samples)
    assert cert.samples[0].rice_gmm == 2.718


def test_rice_is_rendered_in_certificate_table():
    js = (ROOT / "frontend/static/app.js").read_text(encoding="utf-8")
    assert "Rice (Gmm)" in js
    assert "rice:groupDecimals" in js
    assert "groupNum(x.rice_gmm,digits.rice)" in js
