from __future__ import annotations

from typing import Any

HIGH_SCORE_WRITE_THRESHOLD = 80.0


def _score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def line_can_write_by_score(line: dict[str, Any]) -> bool:
    """Permite gravacao quando o matching encontrou medicao com score >= 80.

    O status tecnico original continua visivel (por exemplo, REVISAR). Esta
    politica afeta apenas a liberacao da escrita na BD_QUALI principal.
    """
    if str(line.get("match_status") or "").upper() == "VINCULADO":
        return True
    return bool(line.get("measurement")) and _score(line.get("match_score")) >= HIGH_SCORE_WRITE_THRESHOLD


def install_high_score_excel_write_policy() -> None:
    """Aplica a politica sem alterar o algoritmo de matching existente."""
    from . import quality_excel_writer as qew

    original = qew.enrich_write_plan
    if getattr(original, "_qualimatch_high_score_write_policy", False):
        return

    def wrapped(analysis: dict[str, Any]) -> dict[str, Any]:
        promoted: list[tuple[dict[str, Any], str]] = []
        for cert in analysis.get("certificates") or []:
            for line in cert.get("lines") or []:
                original_status = str(line.get("match_status") or "")
                if original_status.upper() != "VINCULADO" and line_can_write_by_score(line):
                    promoted.append((line, original_status))
                    # O writer legado bloqueia qualquer status diferente de
                    # VINCULADO. Promovemos apenas durante a montagem do plano
                    # de escrita; depois restauramos o status exibido ao usuario.
                    line["match_status"] = "VINCULADO"
                    line["excel_write_score_authorized"] = True
                    line["excel_write_score_threshold"] = HIGH_SCORE_WRITE_THRESHOLD

        try:
            return original(analysis)
        finally:
            for line, original_status in promoted:
                line["match_status"] = original_status

    wrapped._qualimatch_high_score_write_policy = True  # type: ignore[attr-defined]
    qew.enrich_write_plan = wrapped
