from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


REPORT_CATEGORIES = ("VV/ESP", "CA", "LIGANTE", "DUI", "AGREGADOS")
NAVY = colors.HexColor("#17152A")
PURPLE = colors.HexColor("#7047D7")
PURPLE_LIGHT = colors.HexColor("#F1EDFC")
TEXT = colors.HexColor("#252238")
MUTED = colors.HexColor("#6F6B7C")
BORDER = colors.HexColor("#DDD9E8")
SURFACE = colors.HexColor("#F8F7FB")
GREEN = colors.HexColor("#13795B")
GREEN_BG = colors.HexColor("#E7F5EF")
RED = colors.HexColor("#B4233D")
RED_BG = colors.HexColor("#FDECEF")


def _sections(data: dict[str, Any], contractor: str) -> list[dict[str, Any]]:
    sections = data.get("contractor_sections") or []
    if sections:
        return [
            {
                "contractor": str(section.get("contractor") or "-").upper(),
                "measurements": section.get("measurements") or [],
            }
            for section in sections
        ]
    return [{"contractor": contractor, "measurements": data.get("measurements") or []}]


def _gap(item: dict[str, Any], category: str) -> int:
    counts = item.get("counts") or {}
    expected = item.get("expected") or {}
    return max(0, int(expected.get(category) or 0) - int(counts.get(category) or 0))


def _has_pending(item: dict[str, Any]) -> bool:
    return any(_gap(item, category) for category in REPORT_CATEGORIES)


def _page(canvas: Canvas, doc: SimpleDocTemplate) -> None:
    width, height = landscape(A4)
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 9 * mm, width, 9 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawString(14 * mm, height - 5.8 * mm, "QUALIMATCH  |  CONTROLE TECNICO BV")
    canvas.setStrokeColor(BORDER)
    canvas.line(14 * mm, 10 * mm, width - 14 * mm, 10 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(14 * mm, 6.2 * mm, "Relatorio gerado automaticamente pelo QualiMatch")
    canvas.drawRightString(width - 14 * mm, 6.2 * mm, f"Pagina {doc.page}")
    canvas.restoreState()


def _summary_card(label: str, value: str, accent: colors.Color, styles: dict[str, ParagraphStyle]) -> Table:
    card = Table(
        [[Paragraph(label.upper(), styles["card_label"])], [Paragraph(value, styles["card_value"])]],
        colWidths=[58 * mm],
        rowHeights=[8 * mm, 13 * mm],
    )
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return card


def build_bv_missing_report_pdf(data: dict[str, Any], contractor: str) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=17 * mm,
        bottomMargin=15 * mm,
        title="QualiMatch - Relatorio de pendencias BV",
        author="QualiMatch",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=NAVY, alignment=TA_LEFT, spaceAfter=3),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontSize=8.5, leading=12, textColor=MUTED, spaceAfter=10),
        "section": ParagraphStyle("section", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=NAVY),
        "section_meta": ParagraphStyle("section_meta", parent=base["Normal"], fontSize=8, leading=10, textColor=MUTED, alignment=TA_RIGHT),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=7.5, leading=9.5, textColor=TEXT, alignment=TA_CENTER),
        "cell_left": ParagraphStyle("cell_left", parent=base["Normal"], fontSize=7.5, leading=9.5, textColor=TEXT),
        "card_label": ParagraphStyle("card_label", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=6.8, leading=8, textColor=MUTED),
        "card_value": ParagraphStyle("card_value", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=17, leading=18, textColor=NAVY),
        "empty": ParagraphStyle("empty", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=GREEN, alignment=TA_CENTER),
    }

    sections = _sections(data, contractor)
    all_items = [item for section in sections for item in section["measurements"]]
    pending_items = [item for item in all_items if _has_pending(item)]
    expected_total = sum(sum(int((item.get("expected") or {}).get(category) or 0) for category in REPORT_CATEGORIES) for item in all_items)
    delivered_total = sum(sum(min(int((item.get("counts") or {}).get(category) or 0), int((item.get("expected") or {}).get(category) or 0)) for category in REPORT_CATEGORIES) for item in all_items)
    missing_total = max(0, expected_total - delivered_total)
    compliance = 100 if expected_total == 0 else round((delivered_total / expected_total) * 100)
    scope = contractor if contractor != "ALL" else "ARENA + PAVIDEZ"

    story: list[Any] = [
        Paragraph("Relatorio de pendencias de certificados", styles["title"]),
        Paragraph(
            f"Escopo: <b>{scope}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Atualizado em {datetime.now().strftime('%d/%m/%Y as %H:%M')}<br/>"
            "Criterios: VV/ESP por dia executado; CA, Ligante e Agregados em 20% dos dias, arredondado para baixo; DUI em 1 unidade por medicao.",
            styles["subtitle"],
        ),
    ]
    cards = Table([[
        _summary_card("Medicoes avaliadas", str(len(all_items)), PURPLE, styles),
        _summary_card("Medicoes pendentes", str(len(pending_items)), RED, styles),
        _summary_card("Itens faltantes", str(missing_total), colors.HexColor("#D97706"), styles),
        _summary_card("Conformidade", f"{compliance}%", GREEN, styles),
    ]], colWidths=[64 * mm] * 4)
    cards.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    story.extend([cards, Spacer(1, 8 * mm)])

    active_sections = [section for section in sections if any(_has_pending(item) for item in section["measurements"])]
    if not active_sections:
        success = Table([[Paragraph("Nenhuma pendencia encontrada para o filtro selecionado.", styles["empty"])]], colWidths=[269 * mm], rowHeights=[24 * mm])
        success.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN_BG), ("BOX", (0, 0), (-1, -1), 0.8, GREEN), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(success)
    else:
        for section_index, section in enumerate(active_sections):
            pending = [item for item in section["measurements"] if _has_pending(item)]
            if section_index and len(pending) > 7:
                story.append(PageBreak())
            header = Table([[
                Paragraph(section["contractor"], styles["section"]),
                Paragraph(f"{len(pending)} medicao(oes) com pendencia", styles["section_meta"]),
            ]], colWidths=[180 * mm, 89 * mm])
            header.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), PURPLE_LIGHT),
                ("LINEBELOW", (0, 0), (-1, -1), 1.2, PURPLE),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            rows: list[list[Any]] = [["Medicao", "Dias", "VV/ESP", "CA", "Ligante", "DUI", "Agregados", "Faltam", "Observacao"]]
            row_styles: list[tuple[Any, ...]] = []
            for row_index, item in enumerate(pending, start=1):
                counts, expected = item.get("counts") or {}, item.get("expected") or {}
                missing = sum(_gap(item, category) for category in REPORT_CATEGORIES)
                note = "Contagem ajustada manualmente" if item.get("manual_override") else "Entrega abaixo da meta"
                if item.get("override_reason"):
                    note = f"{note}: {item['override_reason']}"
                row = [
                    Paragraph(str(item.get("measurement") or "-"), styles["cell_left"]),
                    Paragraph(str(int(item.get("execution_days") or 0)), styles["cell"]),
                ]
                for column, category in enumerate(REPORT_CATEGORIES, start=2):
                    delivered = int(counts.get(category) or 0)
                    required = int(expected.get(category) or 0)
                    row.append(Paragraph(f"<b>{delivered}</b> / {required}", styles["cell"]))
                    row_styles.extend([
                        ("BACKGROUND", (column, row_index), (column, row_index), RED_BG if delivered < required else GREEN_BG),
                        ("TEXTCOLOR", (column, row_index), (column, row_index), RED if delivered < required else GREEN),
                    ])
                row.extend([Paragraph(f"<b>{missing}</b>", styles["cell"]), Paragraph(note, styles["cell_left"])])
                rows.append(row)
            table = Table(rows, colWidths=[24 * mm, 14 * mm, 25 * mm, 20 * mm, 25 * mm, 19 * mm, 28 * mm, 20 * mm, 94 * mm], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("ALIGN", (1, 0), (7, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE]),
                ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TEXTCOLOR", (7, 1), (7, -1), RED),
                ("FONTNAME", (7, 1), (7, -1), "Helvetica-Bold"),
                *row_styles,
            ]))
            story.extend([KeepTogether([header, Spacer(1, 1 * mm)]), table, Spacer(1, 6 * mm)])

    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return output.getvalue()
