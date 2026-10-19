from qualimatch.write_policy import HIGH_SCORE_WRITE_THRESHOLD, line_can_write_by_score


def _line(status: str, score: float, measurement=True):
    return {
        "match_status": status,
        "match_score": score,
        "measurement": {"id": 1, "line_measurement": "M14"} if measurement else None,
    }


def test_threshold_is_80():
    assert HIGH_SCORE_WRITE_THRESHOLD == 80.0


def test_review_with_80_is_authorized_for_excel_write():
    assert line_can_write_by_score(_line("REVISAR", 80.0)) is True


def test_review_above_80_is_authorized_for_excel_write():
    assert line_can_write_by_score(_line("REVISAR", 92.4)) is True


def test_review_below_80_remains_blocked():
    assert line_can_write_by_score(_line("REVISAR", 79.9)) is False


def test_score_without_measurement_remains_blocked():
    assert line_can_write_by_score(_line("REVISAR", 100.0, measurement=False)) is False


def test_linked_remains_authorized():
    assert line_can_write_by_score(_line("VINCULADO", 60.0)) is True
