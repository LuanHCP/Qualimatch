from __future__ import annotations

from copy import deepcopy
from typing import Any


def _line_is_writeable(line: dict[str, Any]) -> bool:
    status = str(line.get("match_status") or "").upper()
    return status == "VINCULADO" or bool(line.get("excel_write_score_authorized"))


def _safe_to_complete(cert: dict[str, Any]) -> bool:
    if str(cert.get("parse_status") or "").upper() == "PARCIAL":
        return False
    if any("Número divergente:" in str(w) for w in cert.get("warnings") or []):
        return False
    lines = cert.get("lines") or []
    if not lines or any(not _line_is_writeable(x) for x in lines):
        return False
    return all(str((x.get("measurement") or {}).get("line_measurement") or "").strip() for x in lines)


def _completion_plan(cert: dict[str, Any]) -> dict[str, Any] | None:
    """Monta plano híbrido quando parte das linhas do BI330 já existe.

    Ex.: a BD_QUALI tem 5 linhas do BI330 e o PDF atual projeta 6. As 5 linhas
    existentes são atualizadas e apenas a sexta é adicionada ao fim da tabela.
    Nunca remove linhas existentes; se a BD tiver mais linhas que o PDF, mantém
    o bloqueio conservador.
    """
    from . import quality_excel_writer as qew

    if not _safe_to_complete(cert):
        return None

    contractor = str(cert.get("contractor") or "").upper()
    lines = cert.get("lines") or []
    existing = qew._existing_rows_for_cert(contractor, cert.get("certificate"))
    if not existing or len(existing) >= len(lines):
        return None

    # Casa cada linha já existente com uma das projeções do PDF pela Linha de Medição.
    remaining = list(range(len(lines)))
    update_assignments: list[dict[str, Any]] = []
    for row in existing:
        existing_lm = str(row.get("line_measurement") or "").strip()
        found = next(
            (
                idx for idx in remaining
                if str((lines[idx].get("measurement") or {}).get("line_measurement") or "").strip() == existing_lm
            ),
            None,
        )
        if found is None:
            return None
        remaining.remove(found)
        update_assignments.append({
            "target_row": int(row["source_row"]),
            "line_measurement": existing_lm,
        })

    missing_lines = [lines[idx] for idx in remaining]
    if not missing_lines:
        return None

    projected_lines = {
        str((x.get("measurement") or {}).get("line_measurement") or "").strip()
        for x in missing_lines
    }
    template_map = qew._template_candidates(contractor, projected_lines)
    fallback_cache: dict[int, list[dict[str, Any]]] = {}
    append_assignments: list[dict[str, Any]] = []

    for line in missing_lines:
        measurement_ref = line.get("measurement") or {}
        lm = str(measurement_ref.get("line_measurement") or "").strip()
        measurement_id = measurement_ref.get("id")
        exact = template_map.get(lm) or []
        strategy = "EXACT_MEASUREMENT"
        measurement_snapshot = None

        if exact:
            template = exact[0]
        else:
            measurement_snapshot = qew._measurement_snapshot(measurement_id)
            try:
                cache_key = int(measurement_id)
            except Exception:
                cache_key = -1
            fallback = fallback_cache.get(cache_key)
            if fallback is None:
                fallback = qew._fallback_template_candidates(contractor, measurement_snapshot or measurement_ref)
                fallback_cache[cache_key] = fallback
            if not fallback or not measurement_snapshot:
                return None
            template = fallback[0]
            strategy = "STRUCTURAL_FALLBACK"

        append_assignments.append({
            "template_row": int(template["source_row"]),
            "template_line_measurement": str(template.get("line_measurement") or ""),
            "template_strategy": strategy,
            "measurement_id": measurement_id,
            "line_measurement": lm,
            "projected_row": None,
        })

    return {
        "ready": True,
        "mode": "ATUALIZAR_E_COMPLETAR",
        "reason": "",
        "assignments": update_assignments + append_assignments,
        "final_status": qew._final_status(cert.get("quality_fields") or {}),
        "placement": (
            f"Atualiza {len(update_assignments)} linha(s) existente(s) e adiciona "
            f"{len(append_assignments)} linha(s) faltante(s) ao fim da BD_QUALI"
        ),
    }


def install_partial_existing_rows_policy() -> None:
    """Permite atualizar + completar BI330 parcialmente presente na BD_QUALI."""
    from . import quality_excel_writer as qew

    original_enrich = qew.enrich_write_plan
    if getattr(original_enrich, "_qualimatch_partial_existing_rows", False):
        return

    def enrich_wrapped(analysis: dict[str, Any]) -> dict[str, Any]:
        result = original_enrich(analysis)
        promoted_rows = 0
        promoted_certs = 0
        for cert in result.get("certificates") or []:
            plan = cert.get("excel_write") or {}
            if plan.get("ready"):
                continue
            completion = _completion_plan(cert)
            if not completion:
                continue
            cert["excel_write"] = completion
            promoted_certs += 1
            promoted_rows += len(cert.get("lines") or [])

        if promoted_certs:
            summary = result.setdefault("summary", {})
            summary["excel_ready_certificates"] = int(summary.get("excel_ready_certificates") or 0) + promoted_certs
            summary["excel_blocked_certificates"] = max(
                0, int(summary.get("excel_blocked_certificates") or 0) - promoted_certs
            )
            summary["excel_ready_rows"] = int(summary.get("excel_ready_rows") or 0) + promoted_rows
        return result

    enrich_wrapped._qualimatch_partial_existing_rows = True  # type: ignore[attr-defined]
    qew.enrich_write_plan = enrich_wrapped

    original_patch = qew.patch_quality_workbook
    if getattr(original_patch, "_qualimatch_partial_existing_rows", False):
        return

    def patch_wrapped(source_path, contractor, certificates):
        expanded: list[dict[str, Any]] = []
        for cert in certificates:
            plan = cert.get("excel_write") or {}
            if plan.get("mode") != "ATUALIZAR_E_COMPLETAR":
                expanded.append(cert)
                continue

            update_assignments = [a for a in plan.get("assignments") or [] if a.get("target_row") is not None]
            append_assignments = [a for a in plan.get("assignments") or [] if a.get("template_row") is not None]

            if update_assignments:
                update_cert = deepcopy(cert)
                update_cert["excel_write"] = {
                    **plan,
                    "mode": "ATUALIZAR_EXISTENTE",
                    "assignments": update_assignments,
                }
                expanded.append(update_cert)
            if append_assignments:
                append_cert = deepcopy(cert)
                append_cert["excel_write"] = {
                    **plan,
                    "mode": "ADICIONAR_NOVO",
                    "assignments": append_assignments,
                }
                expanded.append(append_cert)

        generated = original_patch(source_path, contractor, expanded)
        generated.certificates = len(certificates)
        return generated

    patch_wrapped._qualimatch_partial_existing_rows = True  # type: ignore[attr-defined]
    qew.patch_quality_workbook = patch_wrapped
