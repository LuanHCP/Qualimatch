from pathlib import Path

from openpyxl import Workbook

from qualimatch.source_inspector import inspect_workbook


def test_source_inspector_finds_header_duplicates_formulas_and_hidden_sheet(tmp_path: Path):
    path = tmp_path / "fonte.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Dados"
    sheet.append(["Relatório operacional"])
    sheet.append([])
    sheet.append(["Data", "Rodovia", "Rodovia", "Total"])
    sheet.append(["2026-09-02", "BR-376", "BR-376", "=1+1"])
    hidden = workbook.create_sheet("Apoio")
    hidden.sheet_state = "hidden"
    hidden.append(["Código", "Descrição"])
    hidden.append([1, "Teste"])
    workbook.save(path)

    result = inspect_workbook(path)

    assert result["summary"]["sheets"] == 2
    assert result["summary"]["visible_sheets"] == 1
    data = result["sheets"][0]
    assert data["header_row"] == 3
    assert data["headers"] == ["Data", "Rodovia", "Rodovia", "Total"]
    assert data["duplicate_headers"] == [["Rodovia", "Rodovia"]]
    assert data["formula_count_sampled"] == 1
    assert data["sample"][0][-1] == "=1+1"
    assert result["summary"]["issues"] == 1


def test_source_inspector_is_exposed_in_tools_ui_and_api():
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (root / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    app = (root / "app.py").read_text(encoding="utf-8")

    assert "Inspetor de planilhas" in html
    assert 'id="tool-source-inspect"' in html
    assert "/api/admin/tools/source-inspector" in js
    assert "admin_tool_source_inspector" in app
