from qualimatch.pdf_reader import _extraction_dates_from_page, _clean_trace


def test_extraction_date_is_read_from_cp_label():
    text = "Datas ex. serviço: 15/07/2025 Data Ext. dos CP's: 18/07/2025 Turno: DIURNO"
    assert _extraction_dates_from_page(text) == ["2025-07-18"]


def test_extraction_date_accepts_typographic_apostrophe():
    text = "Data Ext. dos CP’s: 01/10/2025 Turno: DIURNO"
    assert _extraction_dates_from_page(text) == ["2025-10-01"]


def test_trace_layout_tail_is_removed():
    value = "TRACO_ABC_T-5,2%                              Quant. CP's = 15        Densidade água = 0,997"
    assert _clean_trace(value) == "TRACO_ABC_T-5,2%"
