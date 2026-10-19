from __future__ import annotations

from typing import Any, Callable

from .database import row


def _measurement_by_id(measurement_id: int) -> dict[str, Any] | None:
    data = row(
        "SELECT id,contractor,source_row,line_measurement,ref_measurement,date,road,direction,kmi,kmf,lane "
        "FROM measurements WHERE id=?",
        (int(measurement_id),),
    )
    return dict(data) if data else None


def _recount_summary(result: dict[str, Any]) -> None:
    lines = result.get("lines") or []
    summary = result.setdefault("summary", {})
    summary["linked"] = sum(1 for x in lines if str(x.get("match_status") or "").upper() == "VINCULADO")
    summary["review"] = sum(1 for x in lines if str(x.get("match_status") or "").upper() == "REVISAR")
    summary["missing"] = sum(1 for x in lines if str(x.get("match_status") or "").upper() == "SEM_MEDICAO")


def apply_manual_overrides(
    result: dict[str, Any],
    overrides: dict[str, int] | None,
    measurement_lookup: Callable[[int], dict[str, Any] | None] | None = None,
    replan: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aplica vínculos escolhidos manualmente, mesmo fora dos candidatos automáticos.

    A contratada do CP continua sendo uma trava de segurança: um CP da ARENA não
    pode ser ligado a uma medição da PAVIDEZ (e vice-versa). Depois da escolha do
    administrador, o CP passa a VINCULADO e o plano da BD_QUALI é recalculado.
    """
    overrides = overrides or {}
    if not overrides:
        return result

    lookup = measurement_lookup or _measurement_by_id
    by_key = {str(x.get("line_key") or ""): x for x in (result.get("lines") or [])}
    changed = False
    manual_count = 0

    for line_key, selected_id in overrides.items():
        line = by_key.get(str(line_key))
        if not line:
            continue
        try:
            measurement_id = int(selected_id)
        except (TypeError, ValueError):
            continue

        current = line.get("measurement") or {}
        if (
            str(line.get("match_status") or "").upper() == "VINCULADO"
            and int(current.get("id") or -1) == measurement_id
        ):
            continue

        measurement = lookup(measurement_id)
        if not measurement:
            line["manual_link_error"] = "Medição escolhida não foi encontrada na base sincronizada."
            continue

        line_contractor = str(line.get("contractor") or "").upper()
        measurement_contractor = str(measurement.get("contractor") or "").upper()
        if line_contractor != measurement_contractor:
            line["manual_link_error"] = (
                f"A medição escolhida pertence à {measurement_contractor or 'outra contratada'}; "
                f"o CP pertence à {line_contractor or 'contratada não identificada'}."
            )
            continue

        line["match_status"] = "VINCULADO"
        line["match_score"] = 100.0
        line["match_reason"] = "VÍNCULO MANUAL • medição escolhida pelo administrador na busca livre"
        line["manual_override"] = True
        line["manual_measurement_id"] = measurement_id
        line.pop("manual_link_error", None)
        line["measurement"] = {
            "id": measurement.get("id"),
            "source_row": measurement.get("source_row"),
            "line_measurement": measurement.get("line_measurement"),
            "ref_measurement": measurement.get("ref_measurement"),
            "date": measurement.get("date"),
            "road": measurement.get("road"),
            "direction": measurement.get("direction"),
            "kmi": measurement.get("kmi"),
            "kmf": measurement.get("kmf"),
            "lane": measurement.get("lane"),
        }
        changed = True
        manual_count += 1

    if not changed:
        return result

    _recount_summary(result)
    result.setdefault("summary", {})["manual_links"] = manual_count

    if replan is None:
        from . import quality_excel_writer as qew
        replan = qew.enrich_write_plan
    return replan(result)


def install_manual_override_policy() -> None:
    """Amplia o override legado para aceitar qualquer medição da mesma contratada."""
    from . import tools_pdf_quality as tools

    original = tools.analyze_certificates
    if getattr(original, "_qualimatch_free_manual_measurement_link", False):
        return

    def wrapped(certificates, overrides=None):
        result = original(certificates, overrides)
        return apply_manual_overrides(result, overrides)

    wrapped._qualimatch_free_manual_measurement_link = True  # type: ignore[attr-defined]
    wrapped._qualimatch_original_analyze_certificates = original  # type: ignore[attr-defined]
    tools.analyze_certificates = wrapped


def install_manual_measurement_frontend(app) -> None:
    """Serve a página principal com os complementos visuais carregados após app.js.

    Faz a injeção apenas em memória; não reescreve index.html no disco e não cria
    alterações locais no repositório ao iniciar o QualiMatch.
    """
    if getattr(app.state, "manual_measurement_frontend_installed", False):
        return

    from starlette.responses import HTMLResponse
    from starlette.routing import Route
    from .config import FRONTEND_DIR
    from .version import APP_VERSION

    extra_scripts = [
        f'<script src="/static/manual_measurement_link.js?v={APP_VERSION}"></script>',
        f'<script src="/static/theme_cycle.js?v={APP_VERSION}"></script>',
        f'<script src="/static/theme_phase_patch.js?v={APP_VERSION}"></script>',
        f'<script src="/static/road_events.js?v={APP_VERSION}"></script>',
    ]
    favicon_tag = f'<link rel="icon" type="image/svg+xml" href="/static/favicon-road.svg?v={APP_VERSION}">'

    async def manual_index(request):
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        marker = '<script src="/static/app.js?v=__QUALIMATCH_VERSION__"></script>'
        additions = [tag for tag in extra_scripts if tag not in html]
        if additions:
            payload = "\n".join(additions)
            if marker in html:
                html = html.replace(marker, marker + "\n" + payload, 1)
            else:
                html = html.replace("</body>", payload + "\n</body>", 1)
        if favicon_tag not in html:
            html = html.replace("</head>", favicon_tag + "\n</head>", 1)
        html = html.replace("__QUALIMATCH_VERSION__", APP_VERSION)
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    app.router.routes.insert(0, Route("/", manual_index, methods=["GET"], name="manual-measurement-index"))
    app.state.manual_measurement_frontend_installed = True
