from pathlib import Path

import qualimatch.local_sync as sync
import qualimatch.queries as queries


def test_scan_tree_reads_files_beyond_legacy_windows_path_limit(tmp_path: Path):
    folder = tmp_path / "pasta"
    sync._filesystem_path(folder).mkdir(parents=True)
    target = folder / (("arquivo_" + "x" * 185) + ".pdf")
    assert len(str(target)) > 260
    sync._filesystem_path(target).write_bytes(b"%PDF-1.4\n")

    files, errors = sync._scan_tree_files("ARENA", "bv_documentos", tmp_path, {".pdf"})

    assert errors == 0
    assert [x.name for x in files] == [target.name]
    assert queries._path_is_file(str(target)) is True


def test_discover_bv_source_follows_current_control_folder(tmp_path: Path, monkeypatch):
    target = (
        tmp_path / "Motiva" / "Qualidade PRVias - Documentos" / "General"
        / "02. Técnica" / "01. Laboratório" / "03. CONTROLE DE ENSAIOS"
        / "02. CA" / "01. 4500783073_ARENA_LOT.03" / "04.0 VV - CERTIFICADOS"
    )
    target.mkdir(parents=True)
    monkeypatch.setattr(sync.Path, "home", classmethod(lambda cls: tmp_path))

    assert sync.discover_bv_source("ARENA") == str(target)
