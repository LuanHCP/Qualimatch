from io import BytesIO

from pypdf import PdfReader

from qualimatch.bv_general_report_pdf import build_bv_missing_report_pdf


def test_missing_report_consolidates_measurement_and_highlights_gaps():
    data = {"measurements": [{
        "measurement": "M10", "execution_days": 17,
        "counts": {"VV/ESP": 16, "CA": 4, "LIGANTE": 1, "DUI": 1, "AGREGADOS": 2},
        "expected": {"VV/ESP": 17, "CA": 3, "LIGANTE": 3, "DUI": 1, "AGREGADOS": 3},
        "manual_override": False,
    }]}
    pdf = build_bv_missing_report_pdf(data, "ARENA")
    assert pdf.startswith(b"%PDF")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    assert "M10" in text
    assert "VV/ESP" in text
    assert "Ligante" in text
    assert "Agregados" in text
    assert "ITENS FALTANTES" in text
    assert "4 / 3" in text
    assert "1 / 3" in text
    assert "2 / 3" in text


def test_combined_pdf_keeps_contractors_separate():
    base = {"measurement":"M1","execution_days":3,"counts":{"VV/ESP":2},"expected":{"VV/ESP":3}}
    data = {"contractor_sections":[{"contractor":"ARENA","measurements":[base]},{"contractor":"PAVIDEZ","measurements":[base]}]}
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(build_bv_missing_report_pdf(data,"ALL"))).pages)
    assert "ARENA" in text
    assert "PAVIDEZ" in text
