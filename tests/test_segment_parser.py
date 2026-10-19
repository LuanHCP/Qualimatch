from qualimatch.pdf_reader import _segment_from_candidates, _segment_from_text


def test_segment_header_br_standard():
    text = "Trecho: BR-376 Km Segmento Ensaiado: 405+845 a 406+100"
    road, kmi, kmf = _segment_from_text(text)
    assert road == "BR-376"
    assert kmi == 405845
    assert kmf == 406100


def test_segment_header_pr_with_suffix():
    text = "Trecho: PR 090 - PR Km Segmento Ensaiado: 386+860 a 387+320"
    road, kmi, kmf = _segment_from_text(text)
    assert road == "PR-090"
    assert kmi == 386860
    assert kmf == 387320


def test_segment_header_with_layout_line_breaks_and_station_spaces():
    text = """
    Trecho:\n      BR 376 - PR\n      Km\n
    Segmento\n    Ensaiado:     552 + 980\n       a\n      554 + 640
    """
    road, kmi, kmf = _segment_from_text(text)
    assert road == "BR-376"
    assert kmi == 552980
    assert kmf == 554640


def test_segment_uses_other_text_variant_when_first_one_is_broken():
    plain = "Trecho: BR-376 Km Segmento Ensaiado:"
    layout = "Trecho: BR-376       Km       Segmento Ensaiado: 305+360 a 306+300"
    road, kmi, kmf, source = _segment_from_candidates([plain, layout])
    assert road == "BR-376"
    assert kmi == 305360
    assert kmf == 306300
    assert source == "LAYOUT"


def test_segment_accepts_reverse_direction_without_reordering():
    text = "Trecho: BR-376 Km Segmento Ensaiado: 315+960 a 314+970"
    road, kmi, kmf = _segment_from_text(text)
    assert road == "BR-376"
    assert kmi == 315960
    assert kmf == 314970
