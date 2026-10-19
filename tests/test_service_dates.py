from qualimatch.pdf_reader import _service_dates_from_page


def test_service_dates_normal_layout():
    text = "Datas ex. serviço: 21/07/2025 22/07/2025 Data Ext. dos CP's: 23/07/2025"
    assert _service_dates_from_page(text) == ["2025-07-21", "2025-07-22"]


def test_service_dates_scrambled_pdf_layout():
    text = """
    29/05/2026 01/06/2026 Data Ext. dos CP's: 30/05/2026 02/06/2026 Turno: DIURNO
    Datas ex. serviço:
    Data ensaios:
    ARENA
    295,000 - 547,000 BR376/PR - 29-05-26 - 1525 - 6
    BR376/PR - 01-06-26 - 1525 - 4
    """
    assert _service_dates_from_page(text)[:2] == ["2026-05-29", "2026-06-01"]
