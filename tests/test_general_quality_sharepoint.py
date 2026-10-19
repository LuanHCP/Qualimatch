import os
from pathlib import Path
from zipfile import ZipFile

import pytest

import qualimatch.general_quality as general_quality


def _minimal_xlsx(path: Path, workbook_xml: str = "<workbook/>") -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)


def test_sharepoint_relative_hyperlink_uses_excel_absolute_base(tmp_path):
    source = tmp_path / "inventario.xlsx"
    _minimal_xlsx(
        source,
        """<workbook xmlns:x15ac="http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac">
        <x15ac:absPath url="https://empresa.sharepoint.com/sites/Qualidade/Documentos/General/Cartas/"/>
        </workbook>""",
    )

    base = general_quality._qg_workbook_link_base(source)
    target = "../../../../../:b:/r/sites/Qualidade/Documentos/General/carta.pdf?web=1"

    assert base == "https://empresa.sharepoint.com/sites/Qualidade/Documentos/General/Cartas/"
    assert general_quality._qg_resolve_link(target, base) == (
        "https://empresa.sharepoint.com/:b:/r/sites/Qualidade/Documentos/General/carta.pdf?web=1"
    )


def test_source_path_rejects_sharepoint_web_link(monkeypatch):
    monkeypatch.setattr(general_quality, "_qg_set_setting", lambda *args: None)

    with pytest.raises(ValueError, match="caminho do arquivo sincronizado"):
        general_quality._qg_set_path(
            "inventory", "https://empresa.sharepoint.com/sites/Qualidade/inventario.xlsx", Path("fallback.xlsx")
        )


def test_source_path_accepts_existing_local_excel(monkeypatch, tmp_path):
    source = tmp_path / "inventario.xlsx"
    _minimal_xlsx(source)
    saved = {}
    monkeypatch.setattr(general_quality, "_qg_set_setting", lambda key, value: saved.update({key: value}))

    result = general_quality._qg_set_path("inventory", f'"{source}"', tmp_path / "fallback.xlsx")

    assert result == source
    assert saved == {"inventory": str(source)}


def test_external_source_is_copied_and_refreshed_safely(monkeypatch, tmp_path):
    source = tmp_path / "sharepoint" / "inventario.xlsx"
    source.parent.mkdir()
    source.write_bytes(b"primeira-versao")
    monkeypatch.setattr(general_quality, "_QG_DIR", tmp_path / "managed")
    general_quality._qg_source_copy_cache.clear()

    cached = general_quality._qg_stable_source_copy(source, tmp_path / "upload.xlsx", "traces_test")
    assert cached.read_bytes() == b"primeira-versao"

    source.write_bytes(b"segunda-versao")
    os.utime(source, None)
    cached = general_quality._qg_stable_source_copy(source, tmp_path / "upload.xlsx", "traces_test")

    assert cached.read_bytes() == b"segunda-versao"
