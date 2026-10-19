from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import stat
import threading
import time
import re
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, DATA_DIR
from .database import row, rows, transaction, log_sync, json_dumps
from .measurement_reader import read_measurements
from .quality_reader import read_quality
from .kit_reader import read_kits
from .pdf_reader import parse_pdf, PARSER_VERSION

# v3.8.19 — cópias removidas manualmente não devem reaparecer enquanto o arquivo não mudar.
DUPLICATE_REMOVED_STATUS = "DUPLICADO_REMOVIDO"
from .matching import recalculate_matches

SYNC_LOCK = threading.Lock()
_AUTO_QUALITY_LOCK = threading.Lock()
_AUTO_QUALITY_PENDING: dict[str, dict[str, Path]] = {}
_FOLDER_SCAN_LOCK = threading.Lock()
_FOLDER_SCAN_STATE: dict[tuple[str, str, str], dict[str, float]] = {}


class SourceFileUnavailable(RuntimeError):
    """Arquivo anunciado pelo OneDrive/SharePoint, mas ainda não legível."""


DOCUMENT_EXTENSIONS = {
    '.pdf', '.xlsx', '.xls', '.xlsm', '.docx', '.doc', '.csv',
    '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.zip', '.rar', '.7z',
}


def _filesystem_path(path: Path) -> Path:
    """Usa o prefixo estendido do Windows em caminhos acima de 260 caracteres."""
    raw = os.path.abspath(str(path))
    if os.name == "nt" and not raw.startswith("\\\\?\\"):
        raw = "\\\\?\\UNC\\" + raw[2:] if raw.startswith("\\\\") else "\\\\?\\" + raw
    return Path(raw)


def _path_stat(path: Path):
    return _filesystem_path(path).stat()


def _display_path(path: Path) -> str:
    return os.path.abspath(str(path))


def _scan_tree_files(
    contractor: str, kind: str, folder: Path, extensions: set[str] | None = None,
) -> tuple[list[Path], int]:
    """Varre toda a árvore sem deixar uma falha isolada interromper o lote."""
    found: list[Path] = []
    errors = 0

    def report(path: Path, exc: BaseException) -> None:
        nonlocal errors
        errors += 1
        message = f"Falha ao acessar {path}: {type(exc).__name__}: {exc}"
        log_sync(contractor, f"{kind}_arquivo", "AVISO", message, 0, str(path))

    def on_walk_error(exc: OSError) -> None:
        report(Path(getattr(exc, 'filename', None) or folder), exc)

    for root, dirs, names in os.walk(folder, topdown=True, onerror=on_walk_error, followlinks=False):
        dirs.sort(key=str.lower)
        names.sort(key=str.lower)
        for name in names:
            path = Path(root) / name
            if name.startswith('~$') or (extensions is not None and path.suffix.lower() not in extensions):
                continue
            try:
                if stat.S_ISREG(_path_stat(path).st_mode):
                    found.append(path)
            except (OSError, PermissionError) as exc:
                report(path, exc)
    return found, errors


def _enqueue_auto_quality(contractor: str, paths: list[Path]) -> int:
    """Agenda a BD_QUALI sem bloquear a importação dos certificados.

    A chave pelo caminho evita que vários ciclos do monitor empilhem o mesmo
    PDF enquanto o worker de qualidade ainda está ocupado.
    """
    queued = 0
    with _AUTO_QUALITY_LOCK:
        pending = _AUTO_QUALITY_PENDING.setdefault(contractor.upper(), {})
        for raw_path in paths:
            path = Path(raw_path)
            try:
                key = str(path.resolve())
            except OSError:
                key = str(path)
            if key not in pending:
                queued += 1
            pending[key] = path
    return queued


def _take_auto_quality_jobs() -> dict[str, list[Path]]:
    with _AUTO_QUALITY_LOCK:
        jobs = {
            contractor: list(pending.values())
            for contractor, pending in _AUTO_QUALITY_PENDING.items()
            if pending
        }
        _AUTO_QUALITY_PENDING.clear()
    return jobs


def _recover_pending_auto_quality_jobs() -> int:
    """Recupera tarefas que ficaram em andamento após reinício/interrupção."""
    pending = rows(
        """SELECT contractor,file_path FROM auto_import_events
           WHERE kind='bd_quali_auto' AND status='DETECTADO'
           ORDER BY id"""
    )
    total = 0
    grouped: dict[str, list[Path]] = {}
    for item in pending:
        path = Path(str(item.get('file_path') or ''))
        if path.exists() and path.suffix.lower() == '.pdf':
            grouped.setdefault(str(item.get('contractor') or '').upper(), []).append(path)
    for contractor, paths in grouped.items():
        if contractor:
            total += _enqueue_auto_quality(contractor, paths)
    return total


def _source_signature(kind: str, p: Path) -> tuple[int, int, int]:
    if kind not in {"certificados", "kit_documentos", "bv_documentos"} or not p.is_dir():
        st = p.stat()
        return st.st_mtime_ns, st.st_size, 1
    count = 0
    total = 0
    latest = p.stat().st_mtime_ns
    extensions = {'.pdf'} if kind == 'certificados' else (None if kind == 'bv_documentos' else DOCUMENT_EXTENSIONS)
    files, _ = _scan_tree_files('', kind, p, extensions)
    for pdf in files:
        try:
            st = _path_stat(pdf)
            count += 1
            total += st.st_size
            latest = max(latest, st.st_mtime_ns)
        except OSError:
            pass
    return latest, total, count


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_copy(src: Path, dst: Path) -> None:
    """Espera o arquivo parar de mudar de tamanho/mtime antes de copiar.

    Uma planilha grande (centenas de colunas, milhares de linhas) sincronizando
    ativamente pelo OneDrive/SharePoint pode continuar sendo escrita por vários
    segundos depois que o Explorer já mostra o ícone de "sincronizado". A janela
    antiga (no máx. ~1,6s, bastando UMA leitura repetida) era curta demais para
    esse cenário: a cópia usada para alimentar o banco do QualiMatch podia
    capturar um estado intermediário do arquivo, diferente do que ficaria no
    disco poucos segundos depois — fazendo a sincronização "terminar OK" com
    dados de uma versão que já não é mais a mais recente. Agora exige 3
    leituras consecutivas idênticas antes de copiar, com uma janela total bem
    maior.
    """
    last = None
    stable_hits = 0
    needed_hits = 3
    max_checks = 60  # até ~21s esperando o arquivo realmente parar de mudar
    for _ in range(max_checks):
        st = src.stat()
        cur = (st.st_size, st.st_mtime_ns)
        if cur == last:
            stable_hits += 1
            if stable_hits >= needed_hits:
                break
        else:
            stable_hits = 0
        last = cur
        time.sleep(.35)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    last_err = None
    for _ in range(5):
        try:
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)
            return
        except (PermissionError, OSError) as e:
            last_err = e
            time.sleep(.6)
    raise RuntimeError(f"Não foi possível copiar o arquivo local para o cache: {last_err}")


def get_sources() -> list[dict[str, Any]]:
    out = rows("SELECT * FROM sources ORDER BY contractor, CASE kind WHEN 'medicao' THEN 1 WHEN 'qualidade' THEN 2 WHEN 'kits' THEN 3 WHEN 'kit_documentos' THEN 4 WHEN 'certificados' THEN 5 WHEN 'bv_documentos' THEN 6 ELSE 7 END")
    for s in out:
        p = Path(s["path"]) if s["path"] else None
        s["exists"] = bool(p and p.exists())
        if p and p.exists():
            # Abrir a Administração não pode disparar uma varredura recursiva do
            # SharePoint. As contagens exibidas vêm do último índice sincronizado;
            # a leitura pesada acontece somente em Sincronizar/Reprocessar.
            kind = s["kind"]
            if kind == "bv_documentos":
                found = row("SELECT COUNT(*) total,COALESCE(SUM(size),0) size FROM bv_documents WHERE contractor=? AND COALESCE(is_active,1)=1", (s["contractor"],)) or {}
                count, size = int(found.get("total") or 0), int(found.get("size") or 0)
                mtime_ns = p.stat().st_mtime_ns
                s["read_stats"] = _certificate_read_stats(s["contractor"], p)
            elif kind == "kit_documentos":
                found = row("SELECT COUNT(*) total,COALESCE(SUM(size),0) size FROM kit_documents WHERE contractor=?", (s["contractor"],)) or {}
                count, size = int(found.get("total") or 0), int(found.get("size") or 0)
                mtime_ns = p.stat().st_mtime_ns
            elif kind == "certificados":
                found = row("SELECT COUNT(*) total FROM certificate_files WHERE contractor=?", (s["contractor"],)) or {}
                count, size = int(found.get("total") or 0), 0
                mtime_ns = p.stat().st_mtime_ns
                s["read_stats"] = _certificate_read_stats(s["contractor"], p)
            else:
                mtime_ns, size, count = _source_signature(kind, p)
            s["current_size"] = size
            s["current_count"] = count
            s["current_mtime"] = datetime.fromtimestamp(mtime_ns / 1_000_000_000).isoformat(timespec="seconds")
        else:
            s["current_size"] = None
            s["current_count"] = 0
            s["current_mtime"] = None
    return out


def _certificate_read_stats(contractor: str, folder: Path) -> dict[str, int]:
    """Contagem do estado atual, limitada à pasta configurada."""
    try:
        prefix = str(folder.resolve()).rstrip("\\/") + os.sep
    except OSError:
        prefix = str(folder).rstrip("\\/") + os.sep
    grouped = rows(
        "SELECT UPPER(COALESCE(status,'')) status,COUNT(*) total FROM certificate_files "
        "WHERE contractor=? AND SUBSTR(file_path,1,LENGTH(?))=? GROUP BY UPPER(COALESCE(status,''))",
        (contractor, prefix, prefix),
    )
    counts = {str(item.get("status") or ""): int(item.get("total") or 0) for item in grouped}
    good = sum(counts.get(status, 0) for status in {"OK", "CARREGADO", "PARCIAL"})
    errors = sum(counts.get(status, 0) for status in {"ERRO", "ADIADO"})
    ignored = sum(counts.get(status, 0) for status in {"DUPLICADO", "DUPLICADO_REMOVIDO", "SUBSTITUIDO", "EXCLUIDO"})
    return {"found": good + errors + ignored, "read_ok": good, "errors": errors, "ignored": ignored}


def update_source(contractor: str, kind: str, path: str, worksheet: str = "") -> None:
    with transaction() as con:
        con.execute(
            """UPDATE sources
               SET path=?,worksheet=?,last_mtime_ns=NULL,last_size=NULL,last_hash='',last_status='ALTERADO',last_error=''
               WHERE contractor=? AND kind=?""",
            (path.strip(), worksheet.strip(), contractor, kind),
        )


def _replace_measurements(contractor: str, items) -> int:
    payload = [
        (
            contractor, x.source_row, x.line_measurement, x.ref_measurement, x.team, x.inspector,
            x.date.isoformat() if x.date else None, x.road, x.direction, x.kmi, x.kmf, x.lane,
            x.extension_m, x.width_m, x.thickness_m, x.scope, x.mass_type, x.area_m2, x.paint_m2,
            x.volume_mass_m3, x.volume_milled_m3, x.quantity_t, x.dmt_milled_km, json_dumps(x.raw),
        )
        for x in items
    ]
    with transaction() as con:
        con.execute("DELETE FROM measurements WHERE contractor=?", (contractor,))
        con.executemany(
            """INSERT INTO measurements(contractor,source_row,line_measurement,ref_measurement,team,inspector,date,road,direction,kmi,kmf,lane,extension_m,width_m,thickness_m,scope,mass_type,area_m2,paint_m2,volume_mass_m3,volume_milled_m3,quantity_t,dmt_milled_km,raw_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            payload,
        )
    return len(payload)


def _replace_quality(contractor: str, items, summary, source_path: str, source_mtime: str) -> int:
    payload = [
        (
            contractor, x.source_row, int(x.visible_excel), x.line_measurement, x.ref_measurement,
            x.date.isoformat() if x.date else None, x.road, x.direction, x.kmi, x.kmf, x.lane,
            x.trace_code, x.status_final, x.status_summary, x.extension_m, x.volume_mass_m3,
            x.quantity_t, x.cap_project_t, x.total_service, x.proposed_retention, json_dumps(x.raw),
        )
        for x in items
    ]
    with transaction() as con:
        con.execute("DELETE FROM quality_rows WHERE contractor=?", (contractor,))
        con.executemany(
            """INSERT INTO quality_rows(contractor,source_row,visible_excel,line_measurement,ref_measurement,date,road,direction,kmi,kmf,lane,trace_code,status_final,status_summary,extension_m,volume_mass_m3,quantity_t,cap_project_t,total_service,proposed_retention,raw_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            payload,
        )
        con.execute(
            """INSERT INTO quality_snapshots(contractor,synced_at,source_path,source_mtime,total_service,total_service_visible_sum,total_difference,total_source_cell,extension_m,volume_mass_m3,quantity_t,cap_project_t,proposed_retention,visible_records,total_records,warning,summary_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                contractor, datetime.now().isoformat(timespec="seconds"), source_path, source_mtime,
                summary.total_service, summary.total_service_visible_sum, summary.total_difference,
                summary.total_source_cell, summary.extension_m, summary.volume_mass_m3,
                summary.quantity_t, summary.cap_project_t, summary.proposed_retention,
                summary.visible_records, summary.total_records, summary.warning,
                json_dumps(summary.to_dict()),
            ),
        )
    return len(payload)



def _replace_kits(contractor: str, items) -> int:
    """Substitui o espelho da d.KIT preservando edições/exclusões manuais.

    Linhas sem override continuam refletindo a planilha sincronizada. Quando o
    ADMIN corrige ou arquiva uma linha no site, manual_override=1 impede que a
    próxima sincronização sobrescreva a decisão. A referência estável usada é
    contractor+source_row, a mesma chave utilizada desde a importação inicial.
    """
    payload = [
        (
            contractor, x.source_row, x.seq, x.service,
            x.application_date.isoformat() if x.application_date else None,
            x.mix_project, x.period, x.road, x.kmi, x.kmf,
            x.receipt_date.isoformat() if x.receipt_date else None,
            x.delivery_status, x.status, x.status_1, x.status_2, x.status_3, x.status_4,
            x.status_5, x.status_6, x.status_7, x.status_8, x.sin_retro, json_dumps(x.raw),
        )
        for x in items
    ]
    with transaction() as con:
        manual_rows = {
            int(r["source_row"]): dict(r)
            for r in con.execute(
                "SELECT * FROM kit_rows WHERE contractor=? AND COALESCE(manual_override,0)=1",
                (contractor,),
            ).fetchall()
        }
        # O espelho automático pode ser recriado livremente; overrides ficam.
        con.execute(
            "DELETE FROM kit_rows WHERE contractor=? AND COALESCE(manual_override,0)=0",
            (contractor,),
        )
        fresh = [x for x in payload if int(x[1]) not in manual_rows]
        if fresh:
            con.executemany(
                """INSERT INTO kit_rows(contractor,source_row,seq,service,application_date,mix_project,period,road,kmi,kmf,receipt_date,delivery_status,status,status_1,status_2,status_3,status_4,status_5,status_6,status_7,status_8,sin_retro,raw_json,is_active,manual_override)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0)""",
                fresh,
            )
    return len(payload)

def _cert_identity(cert) -> str:
    lo = min(cert.kmi, cert.kmf) if cert.kmi is not None and cert.kmf is not None else cert.kmi or cert.kmf or 0
    hi = max(cert.kmi, cert.kmf) if cert.kmi is not None and cert.kmf is not None else cert.kmi or cert.kmf or 0
    return "|".join([
        cert.contractor,
        cert.number,
        cert.service_date.isoformat() if cert.service_date else "SEM_DATA",
        cert.road or "SEM_RODOVIA",
        str(lo), str(hi),
    ])



class DuplicateCertificateError(ValueError):
    """Bloqueia a entrada de um BI330 cujo conteúdo técnico já existe."""

    def __init__(self, existing_id: int, existing_number: str, fingerprint: str):
        self.existing_id = int(existing_id)
        self.existing_number = str(existing_number or "")
        self.fingerprint = fingerprint
        super().__init__(
            f"Certificado duplicado: todos os dados técnicos já existem no "
            f"certificado {self.existing_number or self.existing_id} (ID {self.existing_id})."
        )


def _fp_text(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _fp_number(value: Any):
    if value in (None, ""):
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return _fp_text(value)


def _fp_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)[:10]


def _phase_summaries_for_fingerprint(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fields = (
        "k", "ratio_mean_pct", "ratio_std_pct", "ratio_xmin_pct", "ratio_xmax_pct",
        "vv_mean_pct", "vv_std_pct", "vv_xmin_pct", "vv_xmax_pct",
    )
    result: dict[str, dict[str, Any]] = {}
    for phase, values in sorted((raw.get("phase_summaries") or {}).items()):
        values = values or {}
        result[_fp_text(phase)] = {key: _fp_number(values.get(key)) for key in fields}
    return result


def _sample_fingerprint_payload(sample: Any) -> dict[str, Any]:
    get = sample.get if isinstance(sample, dict) else lambda key, default=None: getattr(sample, key, default)
    return {
        "phase": _fp_text(get("phase")),
        "cp_number": _fp_text(get("cp_number")),
        "application_date": _fp_date(get("application_date")),
        "counterproof": bool(get("counterproof")),
        "direction": _fp_text(get("direction")),
        "lane": _fp_text(get("lane")),
        "station": int(get("station")) if get("station") not in (None, "") else None,
        "position": _fp_text(get("position")),
        "thickness_exec_cm": _fp_number(get("thickness_exec_cm")),
        "thickness_project_cm": _fp_number(get("thickness_project_cm")),
        "ratio_ab_pct": _fp_number(get("ratio_ab_pct")),
        "rice_gmm": _fp_number(get("rice_gmm")),
        "gmb": _fp_number(get("gmb")),
        "voids_pct": _fp_number(get("voids_pct")),
    }


def _certificate_content_payload(cert) -> dict[str, Any]:
    raw = dict(getattr(cert, "raw", {}) or {})
    service_dates = {_fp_date(x) for x in (raw.get("service_dates") or []) if _fp_date(x)}
    if getattr(cert, "service_date", None):
        service_dates.add(_fp_date(cert.service_date))
    samples = [_sample_fingerprint_payload(x) for x in (getattr(cert, "samples", []) or [])]
    samples.sort(key=lambda x: (
        x["phase"], x["application_date"] or "", x["cp_number"], x["station"] if x["station"] is not None else -1,
        x["counterproof"], x["position"], x["voids_pct"] if x["voids_pct"] is not None else -999,
    ))
    kmi = getattr(cert, "kmi", None); kmf = getattr(cert, "kmf", None)
    lo = min(kmi, kmf) if kmi is not None and kmf is not None else kmi if kmi is not None else kmf
    hi = max(kmi, kmf) if kmi is not None and kmf is not None else kmf if kmf is not None else kmi
    return {
        "contractor": _fp_text(getattr(cert, "contractor", "")),
        "number": _fp_text(getattr(cert, "number", "")),
        "service_dates": sorted(service_dates),
        "extraction_date": _fp_date(getattr(cert, "extraction_date", None)),
        "road": _fp_text(getattr(cert, "road", "")),
        "kmi": int(lo) if lo is not None else None,
        "kmf": int(hi) if hi is not None else None,
        "trace_approved": _fp_text(getattr(cert, "trace_approved", "")),
        "routine_result": _fp_text(getattr(cert, "routine_result", "")),
        "counterproof_result": _fp_text(getattr(cert, "counterproof_result", "")),
        "has_counterproof": bool(getattr(cert, "has_counterproof", False)),
        "phase_summaries": _phase_summaries_for_fingerprint(raw),
        "samples": samples,
    }


def _certificate_content_fingerprint(cert) -> str:
    payload = _certificate_content_payload(cert)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _db_certificate_content_fingerprint(con, cert_row) -> str:
    c = dict(cert_row)
    try:
        raw = json.loads(c.get("raw_json") or "{}")
    except Exception:
        raw = {}
    samples = [dict(x) for x in con.execute(
        """SELECT phase,cp_number,application_date,counterproof,direction,lane,station,position,
                  thickness_exec_cm,thickness_project_cm,ratio_ab_pct,rice_gmm,gmb,voids_pct
             FROM certificate_samples WHERE certificate_id=?""",
        (c["id"],),
    ).fetchall()]

    class ExistingCert:
        pass
    obj = ExistingCert()
    for key in ("contractor", "number", "service_date", "extraction_date", "road", "kmi", "kmf",
                "trace_approved", "routine_result", "counterproof_result", "has_counterproof"):
        setattr(obj, key, c.get(key))
    obj.raw = raw
    obj.samples = samples
    return _certificate_content_fingerprint(obj)


def _assert_no_content_duplicate(con, cert, exclude_id: int | None = None) -> str:
    """Compara conteúdo técnico, não nome/caminho do PDF.

    Um arquivo renomeado, copiado para outra pasta ou ressincronizado não pode
    criar um segundo certificado quando cabeçalho, resultados e todos os CPs são
    idênticos aos de um registro ativo existente.
    """
    fingerprint = _certificate_content_fingerprint(cert)
    raw = dict(getattr(cert, "raw", {}) or {})
    raw["content_fingerprint"] = fingerprint
    cert.raw = raw

    # Atalho forte: cópia byte a byte do mesmo PDF em outra pasta/nome.
    hash_params: list[Any] = [str(getattr(cert, "contractor", "")), str(getattr(cert, "file_hash", ""))]
    hash_where = ["cf.contractor=?", "cf.file_hash=?", "c.is_active=1"]
    if exclude_id is not None:
        hash_where.append("c.id<>?")
        hash_params.append(int(exclude_id))
    if hash_params[1]:
        same_file = con.execute(
            "SELECT c.id,c.number FROM certificate_files cf JOIN certificates c ON c.id=cf.certificate_id WHERE " + " AND ".join(hash_where) + " LIMIT 1",
            tuple(hash_params),
        ).fetchone()
        if same_file:
            same_file = dict(same_file)
            raise DuplicateCertificateError(same_file["id"], same_file.get("number") or "", fingerprint)

    params: list[Any] = [str(getattr(cert, "contractor", ""))]
    where = ["contractor=?", "is_active=1"]
    if exclude_id is not None:
        where.append("id<>?")
        params.append(int(exclude_id))
    candidates = con.execute(
        "SELECT * FROM certificates WHERE " + " AND ".join(where), tuple(params)
    ).fetchall()
    target_number = _fp_text(getattr(cert, "number", ""))
    for item in candidates:
        existing = dict(item)
        try:
            existing_raw = json.loads(existing.get("raw_json") or "{}")
        except Exception:
            existing_raw = {}
        stored = str(existing_raw.get("content_fingerprint") or "")
        if stored and stored == fingerprint:
            raise DuplicateCertificateError(existing["id"], existing.get("number") or "", fingerprint)
        # Bancos antigos ainda não possuem fingerprint salvo. Só faz a leitura
        # dos CPs quando o nº do certificado coincide; após o próximo parser o
        # fingerprint passa a ficar persistido no raw_json.
        if not stored and _fp_text(existing.get("number")) == target_number:
            if _db_certificate_content_fingerprint(con, existing) == fingerprint:
                raise DuplicateCertificateError(existing["id"], existing.get("number") or "", fingerprint)
    return fingerprint


def _merge_raw(old_raw: dict[str, Any], new_raw: dict[str, Any]) -> dict[str, Any]:
    merged = dict(old_raw or {})
    for key, value in (new_raw or {}).items():
        if key == "phase_summaries":
            phases = dict(merged.get("phase_summaries") or {})
            phases.update(value or {})
            merged["phase_summaries"] = phases
        elif value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _release_inactive_identity(con, identity: str, keep_id: int) -> None:
    """Libera a chave técnica ocupada apenas por uma cópia histórica inativa."""
    duplicate = con.execute(
        "SELECT id,is_active FROM certificates WHERE identity_key=? AND id<>?",
        (identity, keep_id),
    ).fetchone()
    if not duplicate:
        return
    if duplicate["is_active"]:
        raise ValueError(f"A identidade técnica já pertence ao certificado ativo ID {duplicate['id']}")
    historical_identity = f"{identity}|HISTORICO|{duplicate['id']}"
    con.execute("UPDATE certificates SET identity_key=? WHERE id=?", (historical_identity, duplicate["id"]))


def _snapshot_pdf(pdf: Path, contractor: str, expected_hash: str) -> str:
    """Keep immutable bytes even when SharePoint overwrites the same filename."""
    if not re.fullmatch(r'[a-fA-F0-9]{64}', expected_hash or ''):
        return ''
    if contractor not in {'ARENA', 'PAVIDEZ'}:
        raise ValueError('Contratada inválida para histórico de PDF')
    destination = DATA_DIR / 'certificate_versions' / contractor / expected_hash.lower() / pdf.name
    if destination.is_file():
        return str(destination.resolve())
    if not pdf.is_file():
        return ''
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(suffix='.pdf', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as target, pdf.open('rb') as source:
            shutil.copyfileobj(source, target)
        if _sha256(Path(temporary)) != expected_hash:
            raise SourceFileUnavailable('O PDF mudou durante a leitura; aguardando a versão estável.')
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(destination.resolve())


def _archive_documents(con, cid: int, docs: list[dict]) -> None:
    for doc in docs:
        snapshot = str(doc.get('snapshot_path') or '')
        if not snapshot:
            try:
                snapshot = _snapshot_pdf(Path(doc['file_path']), doc['contractor'], doc.get('file_hash') or '')
            except (OSError, SourceFileUnavailable):
                snapshot = ''
        old_hash = doc.get('file_hash') or ''
        history_path = snapshot
        if not history_path and re.fullmatch(r'[a-fA-F0-9]{64}', old_hash):
            history_path = str((DATA_DIR / 'certificate_versions' / doc['contractor'] / old_hash / Path(doc['file_path']).name).resolve())
        if history_path:
            con.execute(
                """INSERT INTO certificate_files(contractor,certificate_id,file_path,file_name,mtime_ns,size,file_hash,kind,status,parser_version,error,parsed_at,snapshot_path)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(contractor,file_path) DO NOTHING""",
                (doc['contractor'], cid, history_path, doc['file_name'], doc.get('mtime_ns'), doc.get('size'), old_hash,
                 doc['kind'], 'SUBSTITUIDO', doc.get('parser_version') or '',
                 '' if snapshot else 'PDF anterior indisponível: não havia cópia local antes da substituição.',
                 doc.get('parsed_at') or '', snapshot),
            )
        con.execute("UPDATE certificate_files SET status='SUBSTITUIDO',snapshot_path=? WHERE id=?", (snapshot, doc['id']))


def _upsert_certificate(cert, *, reactivate: bool = False, manual_override: bool = False) -> int:
    identity = _cert_identity(cert)
    now = datetime.now().isoformat(timespec="seconds")
    new_phases = {s.phase for s in cert.samples}
    new_service = cert.service_date.isoformat() if cert.service_date else None
    new_extraction = cert.extraction_date.isoformat() if getattr(cert, "extraction_date", None) else None

    with transaction() as con:
        old_by_number = False
        old_by_identity = False
        # Em upgrades do parser, campos antes vazios (ex.: rodovia) podem passar a
        # ser preenchidos e alterar a identity_key. Primeiro localiza pelo próprio
        # arquivo já conhecido para atualizar o registro, em vez de duplicá-lo.
        old = con.execute(
            """SELECT c.* FROM certificate_files cf JOIN certificates c ON c.id=cf.certificate_id
               WHERE cf.contractor=? AND cf.file_path=?""",
            (cert.contractor, cert.file_path),
        ).fetchone()
        old_by_file = old is not None
        # Um caminho antigo pode estar ligado a uma ocorrência já excluída,
        # enquanto outra ocorrência do mesmo BI330 continua ativa no site. Uma
        # correção mais nova do SharePoint deve atualizar a ativa, sem ressuscitar
        # a ocorrência histórica.
        if old and not old["is_active"]:
            active = con.execute(
                "SELECT * FROM certificates WHERE contractor=? AND number=? AND is_active=1 ORDER BY id DESC LIMIT 1",
                (cert.contractor, cert.number),
            ).fetchone()
            if active:
                old = active
                old_by_file = False
                old_by_number = True
        if not old:
            old = con.execute("SELECT * FROM certificates WHERE identity_key=?", (identity,)).fetchone()
            old_by_identity = old is not None
        if old and not old["is_active"]:
            active = con.execute(
                "SELECT * FROM certificates WHERE contractor=? AND number=? AND is_active=1 ORDER BY id DESC LIMIT 1",
                (cert.contractor, cert.number),
            ).fetchone()
            if active:
                old = active
                old_by_file = False
                old_by_number = True
        if not old:
            # Correção de um BI330 com erro: a contratada sobe um PDF novo (caminho
            # novo) e a própria correção muda data/rodovia/km — exatamente os campos
            # que compõem a identity_key, então nem o caminho nem a identity batem
            # mais. Mesma contratada + mesmo número do certificado é o mesmo BI330;
            # cai para essa checagem antes de tratar como um certificado novo.
            old = con.execute(
                "SELECT * FROM certificates WHERE contractor=? AND number=? ORDER BY is_active DESC,id DESC LIMIT 1",
                (cert.contractor, cert.number),
            ).fetchone()
            old_by_number = old is not None
        old_raw = {}
        if old:
            try:
                old_raw = json.loads(old["raw_json"] or "{}")
            except Exception:
                old_raw = {}
            incoming_mtime = 0
            try:
                incoming_mtime = Path(cert.file_path).stat().st_mtime_ns
            except OSError:
                pass
            latest_doc = con.execute(
                "SELECT MAX(COALESCE(mtime_ns,0)) latest_mtime FROM certificate_files WHERE certificate_id=?",
                (old["id"],),
            ).fetchone()
            incoming_priority = int((getattr(cert, 'raw', {}) or {}).get('source_priority') or 0)
            old_priority = int(old_raw.get('source_priority') or 0)
            different_content = str(cert.file_hash or "") != str(old["file_hash"] or "")
            source_correction = bool(
                different_content
                and (
                    incoming_priority > old_priority
                    or (
                        incoming_priority == old_priority
                        and incoming_mtime
                        and incoming_mtime > int(latest_doc["latest_mtime"] or 0)
                    )
                )
            )
            # Depois que o certificado veio da árvore oficial BV, uma cópia
            # auxiliar/manual de menor prioridade não pode desfazer a correção.
            if incoming_priority < old_priority and not reactivate:
                return old["id"]
            # Um certificado substituído/excluído manualmente não pode ser
            # sobrescrito novamente pela sincronização da pasta antiga.
            if old["manual_override"] and not reactivate and not source_correction:
                return old["id"]
            # Mesmo caminho = reprocessamento/atualização do próprio registro.
            # Outro arquivo que resolve para a mesma identity (ou para o mesmo
            # número) só é aceito quando trouxer conteúdo novo (ex.: contra-prova
            # ou a própria correção); se for tecnicamente idêntico a outro
            # certificado ativo, bloqueia — mas nunca compara o registro consigo
            # mesmo, por isso exclui old_id quando já sabemos que é o mesmo BI330.
            _assert_no_content_duplicate(
                con, cert,
                exclude_id=int(old["id"]) if (old_by_file or old_by_identity or old_by_number) else None,
            )
            cid = old["id"]
            _release_inactive_identity(con, identity, int(cid))
            has_cp = bool(old["has_counterproof"]) or cert.has_counterproof or "CONTRA_PROVA" in new_phases
            routine_result = cert.routine_result or old["routine_result"]
            counter_result = cert.counterproof_result or old["counterproof_result"]
            merged_raw = _merge_raw(old_raw, cert.raw)
            principal_path = cert.file_path if cert.has_counterproof or not old["has_counterproof"] else old["file_path"]
            principal_hash = cert.file_hash if principal_path == cert.file_path else old["file_hash"]
            # Nunca apaga um campo bom quando um layout parcial não conseguiu lê-lo.
            service_date = (new_service or old["service_date"]) if not source_correction else new_service
            if source_correction:
                extraction_date = new_extraction
            elif old_by_file:
                extraction_date = new_extraction or old["extraction_date"]
            else:
                extraction_candidates = [x for x in (old["extraction_date"], new_extraction) if x]
                extraction_date = min(extraction_candidates) if extraction_candidates else None
            road = cert.road or old["road"]
            kmi = cert.kmi if cert.kmi is not None else old["kmi"]
            kmf = cert.kmf if cert.kmf is not None else old["kmf"]
            old_trace = old["trace_approved"] or ""
            if "DIA 1 DIA 2" in old_trace.upper():
                old_trace = ""
            trace = cert.trace_approved or old_trace
            con.execute(
                """UPDATE certificates SET identity_key=?,file_path=?,file_hash=?,service_date=?,extraction_date=?,road=?,kmi=?,kmf=?,trace_approved=?,routine_result=?,counterproof_result=?,has_counterproof=?,parsed_at=?,raw_json=?,is_active=?,deleted_at=?,deleted_reason=?,manual_override=? WHERE id=?""",
                (
                    identity, principal_path, principal_hash, service_date, extraction_date,
                    road, kmi, kmf, trace, routine_result, counter_result, int(has_cp),
                    now, json_dumps(merged_raw), 1 if reactivate else int(old["is_active"]),
                    None if reactivate else old["deleted_at"], "" if reactivate else old["deleted_reason"],
                    1 if manual_override else int(old["manual_override"]), cid,
                ),
            )
            # Atualiza somente as fases presentes no novo documento; não apaga a
            # contra-prova já cadastrada quando um PDF de rotina é reencontrado.
            for phase in new_phases:
                con.execute("DELETE FROM certificate_samples WHERE certificate_id=? AND phase=?", (cid, phase))
        else:
            _assert_no_content_duplicate(con, cert)
            cur = con.execute(
                """INSERT INTO certificates(identity_key,contractor,number,file_path,file_hash,service_date,extraction_date,road,kmi,kmf,trace_approved,routine_result,counterproof_result,has_counterproof,parsed_at,raw_json,is_active,manual_override)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
                (
                    identity, cert.contractor, cert.number, cert.file_path, cert.file_hash,
                    new_service, new_extraction, cert.road, cert.kmi, cert.kmf,
                    cert.trace_approved, cert.routine_result, cert.counterproof_result, int(cert.has_counterproof),
                    now, json_dumps(cert.raw), 1, int(manual_override),
                ),
            )
            inserted = cur.fetchone()
            cid = inserted["id"] if hasattr(inserted, "keys") else inserted[0]
            # Enfileirar na mesma transação: atualização/releitura não é item novo.
            if (cert.raw or {}).get('source_kind') in {'bv_documentos', 'certificados'}:
                from .email_notifications import enqueue_new_bv_certificate
                enqueue_new_bv_certificate(con, cid)

        con.executemany(
            """INSERT INTO certificate_samples(certificate_id,phase,cp_number,application_date,counterproof,direction,lane,station,position,thickness_exec_cm,thickness_project_cm,ratio_ab_pct,rice_gmm,gmb,voids_pct)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(certificate_id,phase,cp_number,station,counterproof) DO UPDATE SET
                 application_date=excluded.application_date,direction=excluded.direction,lane=excluded.lane,position=excluded.position,
                 thickness_exec_cm=excluded.thickness_exec_cm,thickness_project_cm=excluded.thickness_project_cm,
                 ratio_ab_pct=excluded.ratio_ab_pct,rice_gmm=excluded.rice_gmm,gmb=excluded.gmb,voids_pct=excluded.voids_pct""",
            [
                (
                    cid, s.phase, s.cp_number, s.application_date.isoformat() if s.application_date else None,
                    int(s.counterproof), s.direction, s.lane, s.station, s.position, s.thickness_exec_cm,
                    s.thickness_project_cm, s.ratio_ab_pct, getattr(s, "rice_gmm", None), s.gmb, s.voids_pct,
                )
                for s in cert.samples
            ],
        )
        return cid


def replace_certificate_record(cert_id: int, cert) -> int:
    """Substitui apenas o conteúdo técnico de um certificado, preservando seu ID.

    O PDF/documento anterior continua cadastrado como SUBSTITUIDO para auditoria,
    enquanto amostras, campos técnicos e estatísticas passam a refletir somente o
    novo arquivo. O manual_override impede a pasta sincronizada antiga de desfazer
    a edição no próximo ciclo automático.
    """
    identity = _cert_identity(cert)
    now = datetime.now().isoformat(timespec="seconds")
    new_service = cert.service_date.isoformat() if cert.service_date else None
    new_extraction = cert.extraction_date.isoformat() if getattr(cert, "extraction_date", None) else None
    raw = dict(cert.raw or {})
    raw["management_action"] = "SUBSTITUIDO_MANUALMENTE"
    raw["management_updated_at"] = now

    with transaction() as con:
        old = con.execute("SELECT * FROM certificates WHERE id=?", (cert_id,)).fetchone()
        if not old or not old["is_active"]:
            raise ValueError("Certificado não encontrado ou já excluído")
        if old["contractor"] != cert.contractor:
            raise ValueError("A contratada do PDF substituto é diferente do certificado original")
        duplicate = con.execute("SELECT id,is_active FROM certificates WHERE identity_key=? AND id<>?", (identity, cert_id)).fetchone()
        if duplicate:
            if duplicate["is_active"]:
                raise ValueError(f"O PDF substituto corresponde a outro certificado ativo: ID {duplicate['id']}")
            _release_inactive_identity(con, identity, cert_id)
        _assert_no_content_duplicate(con, cert, exclude_id=cert_id)

        con.execute(
            "UPDATE certificate_files SET status=CASE WHEN status='EXCLUIDO' THEN status ELSE 'SUBSTITUIDO' END WHERE certificate_id=?",
            (cert_id,),
        )
        con.execute("DELETE FROM certificate_samples WHERE certificate_id=?", (cert_id,))
        con.execute(
            """UPDATE certificates SET identity_key=?,number=?,file_path=?,file_hash=?,service_date=?,extraction_date=?,road=?,kmi=?,kmf=?,trace_approved=?,routine_result=?,counterproof_result=?,has_counterproof=?,parsed_at=?,raw_json=?,is_active=1,deleted_at=NULL,deleted_reason='',manual_override=1 WHERE id=?""",
            (
                identity, cert.number, cert.file_path, cert.file_hash, new_service, new_extraction,
                cert.road, cert.kmi, cert.kmf, cert.trace_approved, cert.routine_result,
                cert.counterproof_result, int(cert.has_counterproof), now, json_dumps(raw), cert_id,
            ),
        )
        con.executemany(
            """INSERT INTO certificate_samples(certificate_id,phase,cp_number,application_date,counterproof,direction,lane,station,position,thickness_exec_cm,thickness_project_cm,ratio_ab_pct,rice_gmm,gmb,voids_pct)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(certificate_id,phase,cp_number,station,counterproof) DO UPDATE SET
                 application_date=excluded.application_date,direction=excluded.direction,lane=excluded.lane,position=excluded.position,
                 thickness_exec_cm=excluded.thickness_exec_cm,thickness_project_cm=excluded.thickness_project_cm,
                 ratio_ab_pct=excluded.ratio_ab_pct,rice_gmm=excluded.rice_gmm,gmb=excluded.gmb,voids_pct=excluded.voids_pct""",
            [
                (
                    cert_id, s.phase, s.cp_number, s.application_date.isoformat() if s.application_date else None,
                    int(s.counterproof), s.direction, s.lane, s.station, s.position, s.thickness_exec_cm,
                    s.thickness_project_cm, s.ratio_ab_pct, getattr(s, "rice_gmm", None), s.gmb, s.voids_pct,
                )
                for s in cert.samples
            ],
        )
    return cert_id


def deactivate_certificate(cert_id: int, reason: str = "EXCLUIDO PELO USUARIO") -> str:
    """Faz exclusão lógica: preserva histórico/PDFs, mas remove o BI da operação."""
    now = datetime.now().isoformat(timespec="seconds")
    with transaction() as con:
        cert = con.execute("SELECT contractor,is_active FROM certificates WHERE id=?", (cert_id,)).fetchone()
        if not cert or not cert["is_active"]:
            raise ValueError("Certificado não encontrado ou já excluído")
        con.execute(
            "UPDATE certificates SET is_active=0,deleted_at=?,deleted_reason=?,manual_override=1 WHERE id=?",
            (now, reason, cert_id),
        )
        con.execute(
            "UPDATE certificate_files SET status=CASE WHEN status='SUBSTITUIDO' THEN status ELSE 'EXCLUIDO' END WHERE certificate_id=?",
            (cert_id,),
        )
        con.execute("DELETE FROM matches WHERE certificate_id=?", (cert_id,))
        return cert["contractor"]


def _record_certificate_file(contractor: str, pdf: Path, cid: int | None, cert, status: str | None = None, error: str = "") -> None:
    st = pdf.stat()
    kind = "CONTRA_PROVA" if cert and getattr(cert, "has_counterproof", False) else "ROTINA"
    h = getattr(cert, "file_hash", "") if cert else ""
    if status is None:
        status = ((getattr(cert, "raw", {}) or {}).get("parse_status") if cert else None) or "CARREGADO"
    parser_version = ((getattr(cert, "raw", {}) or {}).get("parser_version") if cert else None) or PARSER_VERSION
    with transaction() as con:
        con.execute(
            """INSERT INTO certificate_files(contractor,certificate_id,file_path,file_name,mtime_ns,size,file_hash,kind,status,parser_version,error,parsed_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(contractor,file_path) DO UPDATE SET certificate_id=excluded.certificate_id,file_name=excluded.file_name,mtime_ns=excluded.mtime_ns,size=excluded.size,file_hash=excluded.file_hash,kind=excluded.kind,status=excluded.status,parser_version=excluded.parser_version,error=excluded.error,parsed_at=excluded.parsed_at""",
            (
                contractor, cid, str(pdf.resolve()), pdf.name, st.st_mtime_ns, st.st_size, h,
                kind, status, parser_version, error, datetime.now().isoformat(timespec="seconds"),
            ),
        )


def _record_certificate_issue(contractor: str, pdf: Path, status: str, error: str) -> None:
    """Registra a falha sem apagar o vínculo técnico válido já existente."""
    st = pdf.stat()
    resolved = str(pdf.resolve())
    now = datetime.now().isoformat(timespec="seconds")
    with transaction() as con:
        current = con.execute(
            "SELECT id FROM certificate_files WHERE contractor=? AND file_path=? ORDER BY id DESC LIMIT 1",
            (contractor, resolved),
        ).fetchone()
        if current:
            con.execute(
                "UPDATE certificate_files SET status=?,error=?,parsed_at=? WHERE id=?",
                (status, error, now, current["id"]),
            )
        else:
            con.execute(
                """INSERT INTO certificate_files(
                       contractor,certificate_id,file_path,file_name,mtime_ns,size,file_hash,kind,status,parser_version,error,parsed_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (contractor, None, resolved, pdf.name, st.st_mtime_ns, st.st_size, '', 'ROTINA', status, PARSER_VERSION, error, now),
            )


def _wait_file_ready(path: Path, checks: int = 3, attempts: int = 16, interval: float = .35) -> None:
    """Espera o OneDrive/SharePoint terminar de materializar/escrever o arquivo.

    Um PDF pode aparecer na pasta alguns instantes antes do download local estar
    completo. Só entregamos o arquivo ao parser depois de tamanho+mtime ficarem
    estáveis em várias leituras consecutivas e o arquivo aceitar leitura.
    """
    stable = 0
    last = None
    last_err = None
    for _ in range(max(checks, attempts)):
        try:
            st = path.stat()
            cur = (st.st_size, st.st_mtime_ns)
            if st.st_size > 0 and cur == last:
                stable += 1
            else:
                stable = 0
            last = cur
            with path.open('rb') as fh:
                fh.read(8)
            if stable >= checks:
                return
        except (OSError, PermissionError) as exc:
            last_err = exc
            stable = 0
        time.sleep(interval)
    if last_err:
        raise SourceFileUnavailable(f'Arquivo ainda não está disponível localmente: {last_err}')
    raise SourceFileUnavailable('Arquivo ainda está sendo sincronizado pelo OneDrive/SharePoint. Tente novamente em alguns segundos.')


def _parse_certificate_job(pdf: Path, contractor: str):
    _wait_file_ready(pdf)
    return pdf, parse_pdf(pdf, contractor)


def _is_aggregate_bi330_pdf(path: Path) -> bool:
    """Identifica pacotes/compilações que contêm vários BI330 no mesmo PDF.

    O parser técnico retorna um certificado por arquivo; compilações de passivos
    não podem ser tratadas como se fossem um BI330 individual.
    """
    name = path.name.upper()
    return "PASSIVOS" in name and "MANUTEN" in name


def _is_bi330_pdf(path: Path) -> bool:
    """Heurística barata para a árvore operacional BV.

    Arquivos BV podem conter relatórios, planilhas e outros PDFs. Para não jogar
    documentos comuns no parser de certificados, somente PDFs cujo nome indique
    BI330 entram automaticamente no pipeline técnico. Compilações de passivos
    são ignoradas porque podem conter vários certificados no mesmo arquivo.
    """
    # Aceita BI330, BI-330, BI_330, BI 330 e também pastas identificadas como
    # BI330 com PDFs de nome genérico. O parser continua sendo a validação final.
    return bool(
        path.suffix.lower() == ".pdf"
        and re.search(r"BI[^A-Z0-9]*330", str(path), re.I)
        and not _is_aggregate_bi330_pdf(path)
    )


def _sync_certificate_paths(
    contractor: str, pdfs: list[Path], force: bool, source_kind: str = ''
) -> tuple[int, int, int, int]:
    pdfs = sorted({Path(x) for x in pdfs}, key=lambda x: str(x).lower())
    changed: list[Path] = []
    skipped = 0
    discovery_errors = 0
    for pdf in pdfs:
        try:
            pst = pdf.stat()
        except OSError as exc:
            discovery_errors += 1
            log_sync(
                contractor, "certificado_pdf", "AVISO",
                f"{pdf.name}: falha ao acessar arquivo: {type(exc).__name__}: {exc}", 0, str(pdf),
            )
            continue
        prev = row(
            "SELECT * FROM certificate_files WHERE contractor=? AND file_path=? ORDER BY id DESC LIMIT 1",
            (contractor, str(pdf.resolve())),
        )
        unchanged = bool(prev and prev.get("mtime_ns") == pst.st_mtime_ns and prev.get("size") == pst.st_size)
        # v3.8.19 — uma cópia duplicada removida pelo usuário fica ignorada
        # enquanto o arquivo físico não mudar, inclusive em reprocessamento forçado.
        if prev and unchanged and str(prev.get("status") or "").upper() == DUPLICATE_REMOVED_STATUS:
            skipped += 1
            continue
        # Respeita edição manual: um PDF antigo marcado como substituído/excluído
        # nunca deve ressuscitar ou sobrescrever o certificado, nem com force=True.
        if prev and prev.get("certificate_id"):
            managed = row("SELECT is_active,manual_override FROM certificates WHERE id=?", (prev["certificate_id"],))
            if managed and managed.get("manual_override") and (not managed.get("is_active") or prev.get("status") in {"SUBSTITUIDO", "EXCLUIDO"}):
                skipped += 1
                continue
        # Falhas definitivas de um PDF inalterado também são cacheadas. Antes,
        # cada "Sincronizar tudo" reabria centenas de CA/arquivos incompatíveis,
        # recriava os mesmos avisos e deixava o site lento por vários minutos.
        # ADIADO não entra aqui porque um placeholder do OneDrive pode ficar
        # disponível depois; force=True continua permitindo reanálise manual.
        if not force and unchanged and prev.get("status") in {"OK", "CARREGADO", "PARCIAL", "DUPLICADO", "ERRO"} and prev.get("parser_version") == PARSER_VERSION:
            skipped += 1
            continue

        # Upgrade inteligente: certificados antigos que já têm os campos técnicos
        # essenciais não precisam ser relidos só porque mudou a versão do parser.
        if not force and unchanged and prev and prev.get("parser_version") != PARSER_VERSION and prev.get("certificate_id"):
            complete = row(
                """SELECT c.extraction_date,c.road,c.kmi,c.kmf,c.trace_approved,c.raw_json,
                          EXISTS(SELECT 1 FROM certificate_samples cs WHERE cs.certificate_id=c.id) has_samples,
                          EXISTS(SELECT 1 FROM certificate_samples cs WHERE cs.certificate_id=c.id AND cs.rice_gmm IS NOT NULL) has_rice
                     FROM certificates c WHERE c.id=?""",
                (prev["certificate_id"],),
            )
            complete_raw = {}
            if complete:
                try:
                    complete_raw = json.loads(complete.get("raw_json") or "{}")
                except Exception:
                    complete_raw = {}
            has_exact_segment_origin = complete_raw.get("segment_source") in {"TEXTO", "LAYOUT", "TEXTO+ARQUIVO", "LAYOUT+ARQUIVO"}
            if (complete and has_exact_segment_origin and complete.get("extraction_date") and complete.get("road")
                    and complete.get("kmi") is not None and complete.get("kmf") is not None
                    and complete.get("has_samples") and complete.get("has_rice") and complete.get("trace_approved")
                    and "DIA 1 DIA 2" not in complete.get("trace_approved", "").upper()):
                with transaction() as con:
                    con.execute("UPDATE certificate_files SET parser_version=?,status='CARREGADO' WHERE id=?", (PARSER_VERSION, prev["id"]))
                skipped += 1
                continue
        changed.append(pdf)

    parsed = 0
    errors = discovery_errors
    # Dois leitores evitam picos de CPU/memória em máquinas corporativas sem
    # perder o ganho do processamento paralelo.
    workers = min(max(1, int(os.getenv("QUALIMATCH_PDF_WORKERS", "2"))), max(1, len(changed)))
    results = []
    if changed:
        ex = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="qualimatch-pdf")
        futures = {ex.submit(_parse_certificate_job, pdf, contractor): pdf for pdf in changed}
        pending = set(futures)
        try:
            # v3.10.x — timeout geral evita que um único PDF preso (placeholder
            # do OneDrive/SharePoint ainda não baixado) trave o lote inteiro
            # para sempre; os demais arquivos já concluídos continuam normalmente.
            for fut in as_completed(futures, timeout=120):
                pending.discard(fut)
                pdf = futures[fut]
                try:
                    results.append(fut.result())
                except Exception as e:
                    errors += 1
                    try:
                        issue_status = "ADIADO" if isinstance(e, SourceFileUnavailable) else "ERRO"
                        _record_certificate_issue(contractor, pdf, issue_status, str(e))
                    except Exception:
                        pass
                    log_sync(contractor, "certificado_pdf", "AVISO", f"{pdf.name}: {e}", 0, str(pdf))
        except FuturesTimeoutError:
            pass
        finally:
            for fut in pending:
                pdf = futures[fut]
                errors += 1
                try:
                    _record_certificate_issue(contractor, pdf, "ADIADO", "Tempo esgotado ao ler o arquivo (provável placeholder do OneDrive/SharePoint ainda não baixado).")
                except Exception:
                    pass
                log_sync(contractor, "certificado_pdf", "AVISO", f"{pdf.name}: tempo esgotado ao abrir o arquivo — provável placeholder do OneDrive/SharePoint.", 0, str(pdf))
            # shutdown sem esperar: uma thread presa em I/O bloqueante não pode
            # ser cancelada à força, mas não precisamos mais aguardá-la aqui.
            ex.shutdown(wait=False)

    for pdf, cert in sorted(results, key=lambda x: x[0].name.lower()):
        try:
            raw = dict(cert.raw or {})
            raw['source_kind'] = source_kind or raw.get('source_kind') or 'desconhecida'
            raw['source_priority'] = 100 if source_kind == 'bv_documentos' else 10 if source_kind == 'certificados' else int(raw.get('source_priority') or 0)
            cert.raw = raw
            cid = _upsert_certificate(cert)
            _record_certificate_file(contractor, pdf, cid, cert)
            parsed += 1
        except DuplicateCertificateError as dup:
            _record_certificate_file(contractor, pdf, dup.existing_id, cert, "DUPLICADO", str(dup))
            skipped += 1
            log_sync(contractor, "certificado_pdf", "AVISO", f"{pdf.name}: {dup}", 0, str(pdf))
        except Exception as exc:
            # Um certificado inválido/corrompido nunca interrompe os próximos.
            errors += 1
            try:
                _record_certificate_issue(contractor, pdf, "ERRO", str(exc))
            except Exception:
                pass
            log_sync(
                contractor, "certificado_pdf", "ERRO",
                f"{pdf.name}: falha ao salvar certificado: {type(exc).__name__}: {exc}", 0, str(pdf),
            )
    return parsed, skipped, errors, len(pdfs)


def _sync_certificates(contractor: str, folder: Path, force: bool) -> tuple[int, int, int, int]:
    candidates, scan_errors = _scan_tree_files(contractor, 'certificados', folder, {'.pdf'})
    parsed, skipped, errors, total = _sync_certificate_paths(contractor, candidates, force, 'certificados')
    return parsed, skipped, errors + scan_errors, total


def _no_result_reason(cert: dict[str, Any]) -> str:
    warnings = [str(x).strip() for x in (cert.get("parse_warnings") or []) if str(x).strip()]
    if warnings:
        return warnings[0]
    samples = int(cert.get("sample_count") or 0)
    vv = str(cert.get("status_vv") or "").strip().upper()
    thickness = str(cert.get("status_thickness") or "").strip().upper()
    if samples == 0:
        return "Nenhum corpo de prova extraído"
    if not vv and not thickness:
        return "CPs extraídos, mas Vv e espessura não puderam ser classificados"
    if not vv:
        return "Volume de vazios sem resultado"
    if not thickness:
        return "Espessura sem resultado"
    return "Resultado técnico não identificado"


def reprocess_no_result_certificates(contractor: str = "ALL") -> dict[str, Any]:
    """Revalida somente os certificados BV cuja Situação está Sem resultado.

    Usa os PDFs já vinculados em certificate_files e força a leitura com o
    parser atual. Não toca na BD_QUALI nem dispara preenchimento automático da
    planilha; atualiza somente o cadastro técnico dos certificados e seus CPs.
    """
    contractor = str(contractor or "ALL").upper().strip()
    if contractor not in {"ALL", "ARENA", "PAVIDEZ"}:
        raise ValueError("Contratada inválida")

    # Import local evita acoplamento circular no carregamento dos módulos.
    from .queries import list_certificates

    scopes = [contractor] if contractor != "ALL" else ["ARENA", "PAVIDEZ"]
    before: list[dict[str, Any]] = []
    for scope in scopes:
        before.extend(list_certificates(scope, status="SEM_RESULTADO", limit=100000))

    before_ids = {int(x["id"]) for x in before}
    paths_by_contractor: dict[str, list[Path]] = {x: [] for x in scopes}
    missing: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for cert in before:
        active_docs = [
            d for d in (cert.get("documents") or [])
            if str(d.get("status") or "").upper() not in {"SUBSTITUIDO", "EXCLUIDO"}
        ]
        candidates = [str(d.get("file_path") or "") for d in active_docs]
        candidates.append(str(cert.get("file_path") or ""))
        found_for_cert = False
        aggregate_for_cert = False
        for raw_path in candidates:
            if not raw_path:
                continue
            pdf = Path(raw_path)
            if _is_aggregate_bi330_pdf(pdf):
                aggregate_for_cert = True
                continue
            try:
                exists = pdf.exists() and pdf.is_file() and pdf.suffix.lower() == ".pdf"
            except OSError:
                exists = False
            if not exists:
                continue
            resolved = str(pdf.resolve())
            found_for_cert = True
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            target = str(cert.get("contractor") or "").upper()
            if target in paths_by_contractor:
                paths_by_contractor[target].append(pdf)
        if not found_for_cert:
            target_list = unsupported if aggregate_for_cert else missing
            target_list.append({
                "id": int(cert["id"]),
                "contractor": cert.get("contractor"),
                "number": cert.get("number"),
                "file_path": cert.get("file_path"),
                "reason": (
                    "PDF agregado de Passivos/Manutenção contém múltiplos BI330; requer PDFs individuais"
                    if aggregate_for_cert else "PDF local não encontrado no caminho vinculado"
                ),
            })

    processed = skipped = errors = 0
    process_details: list[dict[str, Any]] = []
    for scope in scopes:
        paths = paths_by_contractor.get(scope) or []
        if not paths:
            continue
        parsed_n, skipped_n, errors_n, total_n = _sync_certificate_paths(scope, paths, True)
        processed += parsed_n
        skipped += skipped_n
        errors += errors_n
        process_details.append({
            "contractor": scope, "files": total_n, "processed": parsed_n,
            "skipped": skipped_n, "errors": errors_n,
        })
        # Recalcula uma única vez por contratada, após o lote completo.
        recalculate_matches(scope)

    after: list[dict[str, Any]] = []
    for scope in scopes:
        after.extend(list_certificates(scope, status="SEM_RESULTADO", limit=100000))
    after_ids = {int(x["id"]) for x in after}
    fixed_ids = before_ids - after_ids

    reason_counts: dict[str, int] = {}
    remaining_examples: list[dict[str, Any]] = []
    for cert in after:
        reason = _no_result_reason(cert)
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if len(remaining_examples) < 30:
            remaining_examples.append({
                "id": int(cert["id"]), "contractor": cert.get("contractor"),
                "number": cert.get("number"), "sample_count": int(cert.get("sample_count") or 0),
                "parse_status": cert.get("parse_status"), "reason": reason,
                "warnings": cert.get("parse_warnings") or [],
            })

    fixed_examples = [
        {"id": int(x["id"]), "contractor": x.get("contractor"), "number": x.get("number")}
        for x in before if int(x["id"]) in fixed_ids
    ][:30]

    return {
        "ok": errors == 0, "contractor": contractor, "parser_version": PARSER_VERSION,
        "total_before": len(before),
        "local_files_found": sum(len(x) for x in paths_by_contractor.values()),
        "missing_files": len(missing), "unsupported_files": len(unsupported), "processed_files": processed,
        "skipped_files": skipped, "errors": errors, "fixed": len(fixed_ids),
        "remaining": len(after), "reason_counts": reason_counts,
        "fixed_examples": fixed_examples, "remaining_examples": remaining_examples,
        "missing_examples": missing[:30], "unsupported_examples": unsupported[:30], "process_details": process_details,
        "message": (
            f"Validação concluída: {len(fixed_ids)} certificado(s) corrigido(s); "
            f"{len(after)} ainda sem resultado; {len(missing)} PDF(s) não encontrado(s); "
            f"{len(unsupported)} compilação(ões) de passivos ignorada(s)."
        ),
    }


def _sync_bv_certificates(contractor: str, folder: Path, force: bool = False) -> tuple[int, int, int, int]:
    archived={str(x.get('file_path')) for x in rows(
        "SELECT file_path FROM bv_documents WHERE contractor=? AND COALESCE(manual_override,0)=1 AND COALESCE(is_active,1)=0",
        (contractor,),
    )}
    pdfs, scan_errors = _scan_tree_files(contractor, 'bv_documentos', folder, {'.pdf'})
    candidates=[x for x in pdfs if _is_bi330_pdf(x) and str(x.resolve()) not in archived]
    parsed, skipped, errors, total = _sync_certificate_paths(contractor, candidates, force, 'bv_documentos')
    return parsed, skipped, errors + scan_errors, total


def _mark_source_ok(contractor: str, kind: str, mtime: int, size: int, content_hash: str = "") -> None:
    with transaction() as con:
        con.execute(
            """UPDATE sources SET last_mtime_ns=?,last_size=?,last_hash=?,last_sync=?,last_status='OK',last_error=''
               WHERE contractor=? AND kind=?""",
            (mtime, size, content_hash, datetime.now().isoformat(timespec="seconds"), contractor, kind),
        )


def discover_kits_source(contractor: str) -> str | None:
    """Procura a planilha de kits dentro da pasta local sincronizada da contratada.

    A busca parte da fonte de medição já configurada, portanto não percorre o
    OneDrive inteiro. Serve como atalho para bibliotecas SharePoint sincronizadas.
    """
    contractor = contractor.upper()
    roots: list[Path] = []
    # Parte das próprias fontes já configuradas para permanecer dentro das
    # bibliotecas SharePoint sincronizadas no Windows do usuário.
    for ref_kind in ("medicao", "qualidade"):
        ref = row("SELECT path FROM sources WHERE contractor=? AND kind=?", (contractor, ref_kind))
        if ref and ref.get("path"):
            rp = Path(ref["path"])
            for parent in (rp.parent, rp.parent.parent):
                if parent.exists():
                    roots.append(parent)
    for motiva in (
        Path.home() / "Motiva" / "Pavimentos - PRVias - interno - Documentos",
        Path.home() / "Motiva" / "Qualidade PRVias - Documentos",
    ):
        if motiva.exists():
            roots.append(motiva)

    seen: set[str] = set()
    candidates: list[tuple[int, Path]] = []
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            files = root.rglob("*.xlsx")
            for f in files:
                name = f.name.upper()
                if name.startswith("~$"):
                    continue
                score = 0
                full = str(f).upper()
                if contractor in name:
                    score += 6
                elif contractor in full:
                    score += 4
                if "FRESA" in name:
                    score += 5
                if "KIT" in name:
                    score += 5
                if name.startswith("BD_") or name.startswith("BD."):
                    score += 2
                # Exige ao menos um sinal forte (contratada + FRESA/KIT, ou
                # nome muito característico) antes de abrir o XLSX.
                if score < 7:
                    continue
                try:
                    # Valida de verdade o layout; evita selecionar outra planilha
                    # apenas porque o nome parece correto.
                    sample = read_kits(f, "d.KIT")
                    if sample:
                        candidates.append((score + min(len(sample), 500) // 100, f))
                except Exception:
                    continue
        except OSError:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1].stat().st_mtime_ns), reverse=True)
    return str(candidates[0][1])


def discover_bv_source(contractor: str) -> str | None:
    """Localiza a pasta VV atual mesmo quando a biblioteca foi renomeada."""
    contractor = contractor.upper().strip()
    lab = (
        Path.home() / "Motiva" / "Qualidade PRVias - Documentos" / "General"
        / "02. Técnica" / "01. Laboratório"
    )
    if not lab.exists():
        return None
    try:
        controls = [p for p in lab.iterdir() if p.is_dir() and "CONTROLE DE ENSAIOS" in p.name.upper()]
        for control in controls:
            ca_roots = [p for p in control.iterdir() if p.is_dir() and re.search(r"\bCA\b", p.name, re.I)]
            for ca_root in ca_roots:
                for company_root in ca_root.iterdir():
                    if not company_root.is_dir() or contractor not in company_root.name.upper():
                        continue
                    candidates = [
                        p for p in company_root.iterdir()
                        if p.is_dir() and re.match(r"^04\.0\s+VV\s*-\s*CERTIFICADOS$", p.name.strip(), re.I)
                    ]
                    if candidates:
                        return str(candidates[0])
    except (OSError, PermissionError):
        return None
    return None


def remap_bv_certificate_paths(contractor: str, new_folder: Path) -> int:
    """Preserva leituras anteriores quando a biblioteca pai foi renomeada."""
    marker = "04.0 vv - certificados"
    changed = 0
    files = rows("SELECT id,file_path FROM certificate_files WHERE contractor=?", (contractor,))
    with transaction() as con:
        for item in files:
            old = str(item.get("file_path") or "")
            lower = old.lower()
            pos = lower.find(marker)
            if pos < 0:
                continue
            relative = old[pos + len(marker):].lstrip("\\/")
            target_path = new_folder / relative
            try:
                if not stat.S_ISREG(_path_stat(target_path).st_mode):
                    continue
            except (OSError, PermissionError):
                continue
            target = _display_path(target_path)
            conflict = con.execute(
                "SELECT id FROM certificate_files WHERE contractor=? AND file_path=? AND id<>?",
                (contractor, target, item["id"]),
            ).fetchone()
            if conflict:
                continue
            con.execute("UPDATE certificate_files SET file_path=? WHERE id=?", (target, item["id"]))
            con.execute("UPDATE certificates SET file_path=? WHERE contractor=? AND file_path=?", (target, contractor, old))
            changed += 1
    return changed



def _normalize_seq_token(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


# Separador usado para "apontar" para um arquivo dentro de um .zip sem
# extraí-lo de fato no disco. Dois-pontos não aparecem em caminhos do
# Windows fora da unidade (C:), então é seguro como marcador.
ZIP_ENTRY_SEP = "::zip::"

# Extensões consideradas ao abrir um .zip de entrega para procurar
# certificados/documentos dentro dele. Ignora pastas e lixo de sistema
# (__MACOSX, .DS_Store, Thumbs.db) automaticamente via checagem de sufixo.
_ZIP_INNER_ALLOWED = {'.pdf', '.xlsx', '.xls', '.xlsm', '.docx', '.doc', '.csv', '.jpg', '.jpeg', '.png', '.tif', '.tiff'}


def _zip_entry_payloads(contractor: str, zip_path: Path, rel: str, st_mtime_ns: int, tokens, now: str) -> list[tuple]:
    """Abre um .zip de entrega e devolve uma linha de kit_documents para cada
    arquivo relevante dentro dele (sem extrair nada no disco).

    A pasta de entrega às vezes chega compactada como um único .zip por data
    (ex.: 20260530_BR376_..._D.zip) em vez de uma subpasta com os PDFs soltos.
    Sem isso, o certificado que está dentro do zip nunca aparecia na
    navegação por pasta, porque só o .zip em si era indexado.
    """
    out: list[tuple] = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                inner_name = info.filename
                base = inner_name.rsplit('/', 1)[-1]
                if not base or base.startswith('.') or base.startswith('~$') or '__MACOSX' in inner_name:
                    continue
                ext = ('.' + base.rsplit('.', 1)[-1].lower()) if '.' in base else ''
                if ext not in _ZIP_INNER_ALLOWED:
                    continue
                inner_rel = f"{rel}/{inner_name}"
                hay = _normalize_seq_token(inner_rel)
                kit_id = None
                seq_guess = ''
                for token, kid, raw_seq in tokens:
                    if len(token) >= 3 and token in hay:
                        kit_id, seq_guess = kid, raw_seq
                        break
                file_path = f"{zip_path.resolve()}{ZIP_ENTRY_SEP}{inner_name}"
                out.append((
                    contractor, kit_id, file_path, base, inner_rel,
                    str(Path(inner_rel).parent), ext, int(info.file_size),
                    st_mtime_ns, seq_guess, now,
                ))
    except (zipfile.BadZipFile, OSError) as exc:
        # Zip corrompido/ainda sincronizando pelo OneDrive: mantém só o
        # arquivo .zip em si na lista (indexado no loop principal) e ignora
        # o conteúdo por enquanto; a próxima sincronização tenta de novo.
        log_sync(
            contractor, "kit_documentos_arquivo", "AVISO",
            f"Falha ao abrir {zip_path}: {type(exc).__name__}: {exc}", 0, str(zip_path),
        )
        return []
    return out


def _sync_kit_documents(contractor: str, folder: Path) -> int:
    """Indexa recursivamente todos os documentos da pasta Entrega Contratada.

    O arquivo continua no SharePoint/OneDrive local; o banco guarda apenas o
    índice/caminho. Quando o #SEQ aparece no nome ou no caminho relativo, o
    documento é vinculado automaticamente ao kit correspondente. Um .zip de
    entrega também é aberto (sem extrair no disco) para indexar os
    certificados/documentos que estão dentro dele individualmente.
    """
    kit_rows = rows("SELECT id,seq FROM kit_rows WHERE contractor=?", (contractor,))
    tokens = []
    for k in kit_rows:
        token = _normalize_seq_token(k.get('seq'))
        if token:
            tokens.append((token, int(k['id']), str(k.get('seq') or '')))
    tokens.sort(key=lambda x: len(x[0]), reverse=True)
    payload = []
    now = datetime.now().isoformat(timespec='seconds')
    files, scan_errors = _scan_tree_files(contractor, 'kit_documentos', folder, None)
    for f in files:
        try:
            st = f.stat()
            rel = str(f.relative_to(folder))
            hay = _normalize_seq_token(rel)
            kit_id = None
            seq_guess = ''
            for token, kid, raw_seq in tokens:
                # Evita casar sequências curtíssimas dentro de outros números.
                if len(token) >= 3 and token in hay:
                    kit_id, seq_guess = kid, raw_seq
                    break
            payload.append((contractor, kit_id, str(f.resolve()), f.name, rel, str(Path(rel).parent), f.suffix.lower(), st.st_size, st.st_mtime_ns, seq_guess, now))
            if f.suffix.lower() == '.zip':
                payload.extend(_zip_entry_payloads(contractor, f, rel, st.st_mtime_ns, tokens, now))
        except (OSError, PermissionError, ValueError) as exc:
            scan_errors += 1
            log_sync(
                contractor, "kit_documentos_arquivo", "AVISO",
                f"Falha ao indexar {f}: {type(exc).__name__}: {exc}", 0, str(f),
            )
            continue
    with transaction() as con:
        if not scan_errors:
            con.execute("DELETE FROM kit_documents WHERE contractor=?", (contractor,))
        con.executemany(
            """INSERT INTO kit_documents(contractor,kit_id,file_path,file_name,relative_path,folder,extension,size,mtime_ns,seq_guess,synced_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(contractor,file_path) DO UPDATE SET
                 kit_id=excluded.kit_id,file_name=excluded.file_name,relative_path=excluded.relative_path,
                 folder=excluded.folder,extension=excluded.extension,size=excluded.size,
                 mtime_ns=excluded.mtime_ns,seq_guess=excluded.seq_guess,synced_at=excluded.synced_at""", payload
        )
    return len(payload)

def _measurement_label_from_path(relative_path: str) -> str:
    """Detecta M1, M02, MEDIÇÃO 14 etc. em qualquer nível do caminho relativo."""
    import re
    parts = tuple(x for x in str(relative_path).replace('\\','/').split('/') if x)
    patterns = [r"^M\s*0*(\d{1,3})$", r"^MEDI[CÇ][AÃ]O\s*0*(\d{1,3})$", r"^0*(\d{1,3})\s*[-_. ]*MEDI[CÇ][AÃ]O$"]
    for part in parts:
        text = str(part).strip().upper()
        short = re.match(r"^0*(\d{1,3})[_ .-]*MED(?:[_ .-]|$)", text, re.I)
        if short:
            return f"M{int(short.group(1))}"
        for pat in patterns:
            m = re.match(pat, text, re.I)
            if m:
                return f"M{int(m.group(1))}"
        m = re.search(r"(?:^|[^A-Z0-9])M\s*0*(\d{1,3})(?:[^0-9]|$)", text, re.I)
        if m:
            return f"M{int(m.group(1))}"
    return ""


def _bv_report_root(folder: Path) -> Path:
    if re.match(r"^04\.0\b", folder.name.strip(), re.I):
        return folder.parent
    return folder


def _bv_report_files(contractor: str, folder: Path) -> tuple[list[Path], int]:
    root = _bv_report_root(folder)
    files, errors = _scan_tree_files(contractor, 'bv_documentos', root, None)
    if root == folder:
        return files, errors
    # 07 passou a ser a pasta oficial de DUI. Mantemos 01–03 e 04.0 para
    # compatibilidade com os locais anteriores e incluímos a nova pasta irmã
    # sem deixar a varredura escapar para outras árvores do contrato.
    allowed = re.compile(r"^(?:01\.|02\.|03\.|04\.0\b|07\.)", re.I)
    ignored = re.compile(r"^04\.\s*VOLUME DE VAZIO$", re.I)
    selected = []
    for path in files:
        try:
            first = path.relative_to(root).parts[0]
        except ValueError:
            continue
        if allowed.match(first) and not ignored.match(first):
            selected.append(path)
    return selected, errors


def _sync_bv_documents(contractor: str, folder: Path) -> tuple[int, int]:
    """Indexa recursivamente a pasta operacional alimentada pela BV.

    O banco guarda somente metadados. Arquivos arquivados manualmente no site
    permanecem ocultos mesmo que continuem fisicamente no SharePoint.
    """
    payload=[]
    now=datetime.now().isoformat(timespec='seconds')
    # Arquivos por medição é um índice documental: não restringe extensão.
    root = _bv_report_root(folder)
    files, scan_errors = _bv_report_files(contractor, folder)
    for f in files:
        try:
            st=_path_stat(f); rel=str(f.relative_to(root)); parts=Path(rel).parts
            top=parts[0] if len(parts)>1 else '(raiz)'
            measurement=_measurement_label_from_path(rel)
            payload.append((contractor,_display_path(f),f.name,rel,str(Path(rel).parent),top,measurement,f.suffix.lower(),st.st_size,st.st_mtime_ns,now))
        except (OSError, PermissionError, ValueError) as exc:
            scan_errors += 1
            log_sync(
                contractor, "bv_documentos_arquivo", "AVISO",
                f"Falha ao indexar {f}: {type(exc).__name__}: {exc}", 0, str(f),
            )
            continue
    with transaction() as con:
        archived = {
            str(r['file_path'])
            for r in con.execute(
                "SELECT file_path FROM bv_documents WHERE contractor=? AND COALESCE(manual_override,0)=1 AND COALESCE(is_active,1)=0",
                (contractor,),
            ).fetchall()
        }
        # Só apaga o espelho anterior quando a varredura terminou integralmente.
        # Em erro de pasta/arquivo preserva registros antigos e faz upsert dos lidos.
        if not scan_errors:
            con.execute(
                "DELETE FROM bv_documents WHERE contractor=? AND COALESCE(manual_override,0)=0",
                (contractor,),
            )
        fresh=[x for x in payload if str(x[1]) not in archived]
        if fresh:
            con.executemany(
                """INSERT INTO bv_documents(contractor,file_path,file_name,relative_path,folder,top_folder,measurement_label,extension,size,mtime_ns,synced_at,is_active,manual_override)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,1,0)
                   ON CONFLICT(contractor,file_path) DO UPDATE SET
                     file_name=excluded.file_name,relative_path=excluded.relative_path,folder=excluded.folder,
                     top_folder=excluded.top_folder,measurement_label=excluded.measurement_label,
                     extension=excluded.extension,size=excluded.size,mtime_ns=excluded.mtime_ns,
                     synced_at=excluded.synced_at,is_active=1""",fresh
            )
    return len(payload), scan_errors


def sync_source(contractor: str, kind: str, force: bool = False, recalc: bool = True) -> dict[str, Any]:
    with SYNC_LOCK:
        started = time.perf_counter()
        src = row("SELECT * FROM sources WHERE contractor=? AND kind=?", (contractor, kind))
        if not src:
            raise KeyError("Fonte não cadastrada")
        # Na primeira utilização dos Kits, tenta localizar automaticamente a
        # planilha dentro das bibliotecas SharePoint/OneDrive já sincronizadas.
        # O caminho encontrado fica salvo em sources e pode ser editado pelo ADMIN.
        if kind == "kits":
            configured = Path(src["path"]) if src.get("path") else None
            if not configured or not configured.exists():
                found = discover_kits_source(contractor)
                if found:
                    update_source(contractor, "kits", found, "d.KIT")
                    src = row("SELECT * FROM sources WHERE contractor=? AND kind=?", (contractor, kind))
        if kind == "bv_documentos":
            configured = Path(src["path"]) if src.get("path") else None
            if not configured or not configured.exists():
                found = discover_bv_source(contractor)
                if found:
                    remap_bv_certificate_paths(contractor, Path(found))
                    update_source(contractor, "bv_documentos", found, "")
                    src = row("SELECT * FROM sources WHERE contractor=? AND kind=?", (contractor, kind))
        p = Path(src["path"]) if src["path"] else None
        if not p or not p.exists():
            msg = "Caminho local não encontrado. Aguarde a sincronização do OneDrive/SharePoint ou ajuste o caminho."
            with transaction() as con:
                con.execute("UPDATE sources SET last_status='ERRO',last_error=? WHERE contractor=? AND kind=?", (msg, contractor, kind))
            log_sync(contractor, kind, "ERRO", msg, 0, src["path"])
            return {"ok": False, "message": msg}

        tree_source = kind in {"certificados", "kit_documentos", "bv_documentos"} and p.is_dir()
        if tree_source:
            # A rotina específica abaixo já percorre toda a árvore e compara cada
            # arquivo com o índice do banco. Fazer _source_signature antes disso
            # duplicava a varredura (e no BV podia triplicá-la).
            root_stat = p.stat()
            sig_mtime, sig_size, sig_count = root_stat.st_mtime_ns, 0, 0
        else:
            sig_mtime, sig_size, sig_count = _source_signature(kind, p)
        # A fonte "qualidade" (BD_QUALI) nunca usa o atalho de "nada mudou": ela é a
        # que alimenta a validação de segurança da gravação (compara o que está no
        # banco com o que está de fato na linha do Excel na hora de escrever). Um
        # clique em "Sincronizar" nela precisa sempre reprocessar de verdade — o
        # ganho de desempenho do atalho não vale o risco de o botão mostrar "OK"
        # sem ter atualizado nada, deixando a gravação comparar contra dados velhos.
        if not tree_source and kind not in {"certificados", "qualidade", "kits"} and not force and src["last_mtime_ns"] == sig_mtime and src["last_size"] == sig_size:
            return {"ok": True, "skipped": True, "records": 0, "message": "Sem alterações. Nada foi reprocessado."}

        try:
            records = 0
            content_hash = ""
            if kind in {"medicao", "qualidade", "kits"}:
                cache = CACHE_DIR / f"{contractor}_{kind}{p.suffix.lower()}"
                _stable_copy(p, cache)
                # Retrato do arquivo já depois da espera de estabilidade — antes,
                # mtime/tamanho vinham de ANTES dessa espera e podiam já estar
                # desatualizados em relação ao que a cópia realmente capturou.
                st_final = p.stat()
                sig_mtime, sig_size = st_final.st_mtime_ns, st_final.st_size
                # O hash é calculado em cima da MESMA cópia que será lida abaixo.
                # Antes, era calculado no arquivo "ao vivo" ANTES da espera de
                # estabilidade (e antes da cópia em si): se o OneDrive ainda
                # estivesse entregando uma atualização grande, o hash podia
                # refletir um estado do arquivo diferente do que a cópia estável
                # (feita alguns segundos depois) realmente pegou — fazendo a
                # sincronização "concluir OK" com dados de uma versão que já não
                # era mais a mais recente.
                content_hash = _sha256(cache)
                # Mesmo motivo do atalho acima: para "qualidade" sempre reingere e
                # regrava quality_rows, mesmo que o hash pareça idêntico ao último
                # registrado — nunca deixamos esse atalho ser a razão de a base de
                # validação da gravação ficar desatualizada.
                if kind != "qualidade" and not force and src.get("last_hash") and src["last_hash"] == content_hash:
                    _mark_source_ok(contractor, kind, sig_mtime, sig_size, content_hash)
                    return {"ok": True, "skipped": True, "records": 0, "message": "Arquivo tocado pelo OneDrive, mas conteúdo idêntico. Nada foi reprocessado."}

                if kind == "medicao":
                    items = read_measurements(cache, src["worksheet"] or "RDO_RESTAURA")
                    records = _replace_measurements(contractor, items)
                elif kind == "qualidade":
                    items, summary = read_quality(cache, src["worksheet"] or "BD_QUALI")
                    records = _replace_quality(
                        contractor, items, summary, str(p),
                        datetime.fromtimestamp(sig_mtime / 1_000_000_000).isoformat(timespec="seconds"),
                    )
                else:
                    items = read_kits(cache, src["worksheet"] or "d.KIT")
                    records = _replace_kits(contractor, items)
            elif kind == "kit_documentos":
                if not p.is_dir():
                    raise ValueError("O caminho de Documentos dos Kits deve ser uma pasta.")
                records = _sync_kit_documents(contractor, p)
                _mark_source_ok(contractor, kind, sig_mtime, sig_size, "")
                elapsed = time.perf_counter() - started
                msg = f"Documentos dos kits: {records} arquivo(s) indexado(s) recursivamente em {elapsed:.1f}s."
                log_sync(contractor, kind, "OK", msg, records, str(p))
                return {"ok": True, "records": records, "message": msg}
            elif kind == "bv_documentos":
                if not p.is_dir():
                    raise ValueError("O caminho de Arquivos BV deve ser uma pasta.")
                records, index_errors = _sync_bv_documents(contractor, p)
                # A mesma árvore também passa a ser uma fonte automática de BI330.
                # PDFs comuns continuam apenas indexados; arquivos com BI330 no nome
                # entram no pipeline técnico de certificados e alimentam Dashboard/Pendências.
                imported, cert_skipped, cert_errors, cert_candidates = _sync_bv_certificates(contractor, p, force)
                if recalc and imported:
                    recalculate_matches(contractor)
                _mark_source_ok(contractor, kind, sig_mtime, sig_size, "")
                elapsed = time.perf_counter() - started
                read_stats = _certificate_read_stats(contractor, p)
                total_errors = index_errors + cert_errors
                msg = (f"Arquivos BV: {records} arquivo(s) indexado(s); "
                       f"{cert_candidates} BI330 encontrado(s) nesta varredura; "
                       f"{read_stats['read_ok']} lido(s) corretamente, {read_stats['ignored']} ignorado(s), "
                       f"{read_stats['errors']} com erro no índice atual; {imported} novo(s)/atualizado(s) • {elapsed:.1f}s.")
                log_sync(contractor, kind, "OK" if not total_errors else "AVISO", msg, records, str(p))
                return {"ok": total_errors == 0, "records": records, "index_errors": index_errors,
                        "read_stats": read_stats, "certificates_imported": imported,
                        "certificate_candidates": cert_candidates, "certificate_skipped": cert_skipped,
                        "certificate_errors": cert_errors, "message": msg}
            elif kind == "certificados":
                if not p.is_dir():
                    raise ValueError("O caminho de certificados deve ser uma pasta.")
                records, skipped, errors, sig_count = _sync_certificates(contractor, p, force)
                if recalc and records:
                    recalculate_matches(contractor)
                _mark_source_ok(contractor, kind, sig_mtime, sig_size, "")
                elapsed = time.perf_counter() - started
                read_stats = _certificate_read_stats(contractor, p)
                msg = (f"Certificados: {sig_count} PDF(s) encontrado(s); {read_stats['read_ok']} lido(s) corretamente, "
                       f"{read_stats['ignored']} ignorado(s), {read_stats['errors']} com erro; "
                       f"{records} novo(s)/atualizado(s) nesta execução • {elapsed:.1f}s.")
                log_sync(contractor, kind, "OK" if not errors else "AVISO", msg, records, str(p))
                return {"ok": errors == 0, "records": records, "read_stats": read_stats,
                        "found_files": sig_count, "skipped_files": skipped, "errors": errors, "message": msg}
            else:
                raise ValueError("Tipo de fonte inválido")

            if recalc and kind == "medicao":
                recalculate_matches(contractor)
            _mark_source_ok(contractor, kind, sig_mtime, sig_size, content_hash)
            elapsed = time.perf_counter() - started
            msg = f"Sincronizado: {records} registros em {elapsed:.1f}s."
            log_sync(contractor, kind, "OK", msg, records, str(p))
            return {"ok": True, "records": records, "message": msg}
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            with transaction() as con:
                con.execute("UPDATE sources SET last_status='ERRO',last_error=? WHERE contractor=? AND kind=?", (msg, contractor, kind))
            log_sync(contractor, kind, "ERRO", msg, 0, str(p))
            return {"ok": False, "message": msg}


def sync_all(force: bool = False, progress=None, cancelled=None) -> list[dict[str, Any]]:
    """Sincroniza em ordem previsível e recalcula matching só uma vez por empresa."""
    results = []
    jobs = []
    for contractor in ("ARENA", "PAVIDEZ"):
        for kind in ("medicao", "qualidade", "kits", "kit_documentos", "certificados", "bv_documentos"):
            source = row("SELECT contractor,kind,path,enabled FROM sources WHERE contractor=? AND kind=?", (contractor, kind))
            if source and source["enabled"] and (source["path"] or kind == "kits"):
                jobs.append((contractor, kind))
    completed = 0
    if progress:
        progress(processed=0, total=len(jobs), current="Preparando fontes...")
    for contractor in ("ARENA", "PAVIDEZ"):
        changed_for_match = False
        for kind in ("medicao", "qualidade", "kits", "kit_documentos", "certificados", "bv_documentos"):
            s = row("SELECT contractor,kind,path,enabled FROM sources WHERE contractor=? AND kind=?", (contractor, kind))
            if not s or not s["enabled"]:
                continue
            # Kits podem nascer sem caminho: o sync_source tenta descobri-lo
            # automaticamente pela biblioteca SharePoint local da contratada.
            if not s["path"] and kind != "kits":
                continue
            if cancelled:
                cancelled()
            if progress:
                progress(processed=completed, total=len(jobs), current=f"{contractor} / {kind}")
            r = sync_source(contractor, kind, force, recalc=False)
            completed += 1
            if progress:
                progress(processed=completed, total=len(jobs), current=f"{contractor} / {kind}")
            # Se não há planilha de kits local ainda, não transforma o sync-all
            # em falha geral; a fonte continuará configurável no painel ADMIN.
            if kind == "kits" and not r.get("ok") and "Caminho local não encontrado" in str(r.get("message", "")):
                continue
            if r.get("records", 0) and kind in {"medicao", "certificados"}:
                changed_for_match = True
            r.update({"contractor": contractor, "kind": kind})
            results.append(r)
        if changed_for_match:
            recalculate_matches(contractor)
        # Se a sincronização manual/automática reconheceu BI330 antes do monitor
        # de arquivos, reconcilia somente os certificados recém-processados.
        try:
            auto_q = auto_fill_quality_for_recent_certificates(contractor, 300)
            if auto_q.get('candidates') or auto_q.get('written_certificates') or auto_q.get('review') or auto_q.get('errors'):
                results.append({'contractor': contractor, 'kind': 'bd_quali_auto', **auto_q})
        except Exception as exc:
            log_sync(contractor, 'bd_quali_auto', 'ERRO', f'Preenchimento automático: {exc}', 0, '')
    return results


def sync_changed_spreadsheets() -> list[dict[str, Any]]:
    """Sincroniza no ciclo curto somente planilhas cujo arquivo mudou.

    Pastas recursivas são responsabilidade do monitor incremental. Isso evita
    que o ciclo periódico reconstrua a árvore do SharePoint a cada minuto e
    bloqueie por vários minutos a chegada de um PDF novo.
    """
    results: list[dict[str, Any]] = []
    for contractor in ('ARENA', 'PAVIDEZ'):
        changed_for_match = False
        for kind in ('medicao', 'qualidade'):
            if not _source_changed(contractor, kind):
                continue
            result = sync_source(contractor, kind, False, recalc=False)
            result.update({'contractor': contractor, 'kind': kind})
            results.append(result)
            if kind == 'medicao' and result.get('records'):
                changed_for_match = True
        if changed_for_match:
            recalculate_matches(contractor)
    return results


def _setting_value(key: str, default: str = '') -> str:
    found = row("SELECT value FROM settings WHERE key=?", (key,))
    return str(found.get('value') if found else default)


def _setting_bool(key: str, default: bool = False) -> bool:
    return _setting_value(key, '1' if default else '0').strip().lower() in {'1','true','yes','sim','on'}


def monitor_config() -> dict[str, Any]:
    try:
        seconds = int(_setting_value('auto_monitor_seconds', '15') or 15)
    except Exception:
        seconds = 15
    seconds = min(300, max(10, seconds))
    return {
        'enabled': _setting_bool('auto_monitor_enabled', True),
        'bv': _setting_bool('auto_monitor_bv', True),
        'contractor': _setting_bool('auto_monitor_contractor', True),
        'auto_quality': _setting_bool('auto_bdquali_enabled', True),
        'seconds': seconds,
    }


def update_monitor_config(enabled: bool, bv: bool, contractor: bool, seconds: int, auto_quality: bool = True) -> dict[str, Any]:
    seconds = min(300, max(10, int(seconds or 15)))
    values = {
        'auto_monitor_enabled': '1' if enabled else '0',
        'auto_monitor_bv': '1' if bv else '0',
        'auto_monitor_contractor': '1' if contractor else '0',
        'auto_bdquali_enabled': '1' if auto_quality else '0',
        'auto_monitor_seconds': str(seconds),
    }
    with transaction() as con:
        for key, value in values.items():
            con.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
    return monitor_config()


def _scheduled_folder_changes(
    contractor: str,
    kind: str,
    folder: Path,
    base_seconds: int,
    scanner,
):
    """Executa a varredura pesada com intervalo adaptativo.

    Enquanto chegam arquivos, mantém o intervalo configurado. Depois de ciclos
    sem mudança, aumenta gradualmente até dois minutos. Isso preserva o catch-up
    do OneDrive sem manter disco, CPU e banco ocupados continuamente.
    """
    now = time.monotonic()
    base = float(min(120, max(10, int(base_seconds or 15))))
    key = (contractor.upper(), kind, os.path.abspath(str(folder)).lower())
    with _FOLDER_SCAN_LOCK:
        state = _FOLDER_SCAN_STATE.get(key)
        if state and now < state.get("next", 0):
            return []
    changes = scanner(contractor, folder)
    with _FOLDER_SCAN_LOCK:
        previous = _FOLDER_SCAN_STATE.get(key, {})
        interval = base if changes else min(120.0, max(base, previous.get("interval", base)) * 2)
        _FOLDER_SCAN_STATE[key] = {"next": time.monotonic() + interval, "interval": interval}
    return changes


def count_monitor_events() -> int:
    found = row("SELECT COUNT(*) total FROM auto_import_events")
    return int((found or {}).get("total") or 0)


def monitor_events(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    return rows(
        "SELECT * FROM auto_import_events ORDER BY id DESC LIMIT ? OFFSET ?",
        (min(500, max(1, int(limit or 100))), max(0, int(offset))),
    )


def _event_signature(path: Path) -> str:
    try:
        st = path.stat()
        return f'{st.st_mtime_ns}:{st.st_size}'
    except OSError:
        return 'missing'


def _begin_monitor_event(contractor: str, portal: str, kind: str, path: Path, event_type: str, signature: str | None = None) -> int | None:
    signature = signature or _event_signature(path)
    detected = datetime.now().isoformat(timespec='seconds')
    resolved = str(path.resolve()) if path.exists() else str(path)
    with transaction() as con:
        con.execute(
            """INSERT INTO auto_import_events(contractor,portal,kind,file_path,file_name,signature,event_type,status,message,detected_at)
               VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(contractor,kind,file_path,signature,event_type) DO NOTHING""",
            (contractor, portal, kind, resolved, path.name, signature, event_type, 'DETECTADO', '', detected),
        )
        found = con.execute(
            "SELECT id,status,processed_at FROM auto_import_events WHERE contractor=? AND kind=? AND file_path=? AND signature=? AND event_type=?",
            (contractor, kind, resolved, signature, event_type),
        ).fetchone()
        status = str(found['status']).upper() if found else ''
        retry_error = False
        if found and status == 'ERRO':
            try:
                processed = datetime.fromisoformat(str(found['processed_at'] or ''))
                retry_error = (datetime.now() - processed).total_seconds() >= 300
            except (TypeError, ValueError):
                retry_error = True
        if found and (status == 'ADIADO' or retry_error):
            con.execute(
                "UPDATE auto_import_events SET status='DETECTADO',message='',processed_at=NULL,detected_at=? WHERE id=?",
                (detected, found['id']),
            )
            status = 'DETECTADO'
        if not found or status not in {'DETECTADO', 'ADIADO'}:
            return None
        return int(found['id'])


def _finish_monitor_event(event_id: int | None, status: str, message: str = '') -> None:
    if not event_id:
        return
    with transaction() as con:
        con.execute(
            "UPDATE auto_import_events SET status=?,message=?,processed_at=? WHERE id=?",
            (status, message or '', datetime.now().isoformat(timespec='seconds'), event_id),
        )


def _certificate_drop_changes(contractor: str, folder: Path) -> list[tuple[Path,str,str]]:
    # Uma única leitura do banco por ciclo evita N queries quando a pasta já
    # possui centenas/milhares de BI330.
    previous: dict[str, dict[str, Any]] = {}
    for item in rows(
        "SELECT id,file_path,mtime_ns,size FROM certificate_files WHERE contractor=? ORDER BY id DESC",
        (contractor,),
    ):
        previous.setdefault(str(item['file_path']), item)
    changes: list[tuple[Path,str,str]] = []
    pdfs, _ = _scan_tree_files(contractor, 'certificados', folder, {'.pdf'})
    for pdf in pdfs:
        try:
            st = pdf.stat()
        except OSError:
            continue
        resolved = str(pdf.resolve())
        prev = previous.get(resolved)
        sig = f'{st.st_mtime_ns}:{st.st_size}'
        if not prev:
            changes.append((pdf, 'NOVO', sig))
        elif prev.get('mtime_ns') != st.st_mtime_ns or prev.get('size') != st.st_size:
            changes.append((pdf, 'ALTERADO', sig))
    return changes


def _kit_document_drop_changes(contractor: str, folder: Path) -> list[tuple[Path,str,str]]:
    allowed = {'.pdf','.xlsx','.xls','.xlsm','.docx','.doc','.csv','.jpg','.jpeg','.png','.tif','.tiff','.zip','.rar','.7z'}
    previous = {str(r['file_path']): r for r in rows("SELECT file_path,mtime_ns,size FROM kit_documents WHERE contractor=?", (contractor,))}
    current: set[str] = set()
    changes: list[tuple[Path,str,str]] = []
    for f in folder.rglob('*'):
        try:
            if not f.is_file() or f.name.startswith('~$') or f.suffix.lower() not in allowed:
                continue
            st = f.stat()
        except OSError:
            continue
        resolved = str(f.resolve())
        current.add(resolved)
        prev = previous.get(resolved)
        sig = f'{st.st_mtime_ns}:{st.st_size}'
        if not prev:
            changes.append((f, 'NOVO', sig))
        elif prev.get('mtime_ns') != st.st_mtime_ns or prev.get('size') != st.st_size:
            changes.append((f, 'ALTERADO', sig))
    for old_path in sorted(set(previous) - current):
        changes.append((Path(old_path), 'REMOVIDO', 'missing'))
    return changes


def _apply_kit_document_changes(
    contractor: str, folder: Path, changes: list[tuple[Path, str, str]],
) -> dict[str, str]:
    """Atualiza só documentos da contratada detectados pelo monitor."""
    kit_rows = rows("SELECT id,seq FROM kit_rows WHERE contractor=?", (contractor,))
    tokens = []
    for kit in kit_rows:
        token = _normalize_seq_token(kit.get('seq'))
        if token:
            tokens.append((token, int(kit['id']), str(kit.get('seq') or '')))
    tokens.sort(key=lambda item: len(item[0]), reverse=True)
    now = datetime.now().isoformat(timespec='seconds')
    states: dict[str, str] = {}
    with transaction() as con:
        for file_path, event_type, _ in changes:
            raw_path = str(file_path) if event_type == 'REMOVIDO' else str(file_path.resolve())
            con.execute(
                """DELETE FROM kit_documents
                   WHERE contractor=? AND
                         (file_path=? OR SUBSTR(file_path,1,LENGTH(?))=?)""",
                (contractor, raw_path, raw_path + ZIP_ENTRY_SEP, raw_path + ZIP_ENTRY_SEP),
            )
            if event_type == 'REMOVIDO':
                states[raw_path] = 'REMOVIDO'
                continue
            try:
                info = file_path.stat()
                relative = str(file_path.relative_to(folder))
                normalized = _normalize_seq_token(relative)
                kit_id = None
                seq_guess = ''
                for token, candidate_id, raw_seq in tokens:
                    if len(token) >= 3 and token in normalized:
                        kit_id, seq_guess = candidate_id, raw_seq
                        break
                payload = [(
                    contractor, kit_id, raw_path, file_path.name, relative,
                    str(Path(relative).parent), file_path.suffix.lower(), info.st_size,
                    info.st_mtime_ns, seq_guess, now,
                )]
                if file_path.suffix.lower() == '.zip':
                    payload.extend(
                        _zip_entry_payloads(
                            contractor, file_path, relative, info.st_mtime_ns, tokens, now,
                        )
                    )
                con.executemany(
                    """INSERT INTO kit_documents(contractor,kit_id,file_path,file_name,relative_path,folder,extension,size,mtime_ns,seq_guess,synced_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(contractor,file_path) DO UPDATE SET
                         kit_id=excluded.kit_id,file_name=excluded.file_name,relative_path=excluded.relative_path,
                         folder=excluded.folder,extension=excluded.extension,size=excluded.size,
                         mtime_ns=excluded.mtime_ns,seq_guess=excluded.seq_guess,synced_at=excluded.synced_at""",
                    payload,
                )
                states[raw_path] = 'INDEXADO'
            except (OSError, PermissionError, ValueError) as exc:
                states[raw_path] = 'ERRO'
                log_sync(
                    contractor, 'kit_documentos_arquivo', 'AVISO',
                    f'Falha ao indexar {file_path}: {type(exc).__name__}: {exc}', 0, raw_path,
                )
    return states


def _bv_document_drop_changes(contractor: str, folder: Path) -> list[tuple[Path,str,str]]:
    indexed = rows(
        "SELECT file_path,mtime_ns,size,is_active,manual_override FROM bv_documents WHERE contractor=?",
        (contractor,),
    )
    archived = {
        str(item['file_path']): item for item in indexed
        if not int(item.get('is_active') or 0) and int(item.get('manual_override') or 0)
    }
    previous = {
        str(item['file_path']): item for item in indexed
        if str(item['file_path']) not in archived
    }
    current:set[str]=set(); changes=[]
    files, _ = _bv_report_files(contractor, folder)
    for f in files:
        try:
            st=_path_stat(f)
        except (OSError, PermissionError) as exc:
            log_sync(
                contractor, "bv_documentos_arquivo", "AVISO",
                f"Falha ao verificar {f}: {type(exc).__name__}: {exc}", 0, str(f),
            )
            continue
        resolved=_display_path(f)
        archived_item = archived.get(resolved)
        if archived_item:
            if archived_item.get('mtime_ns') != st.st_mtime_ns or archived_item.get('size') != st.st_size:
                changes.append((f, 'ALTERADO', f'{st.st_mtime_ns}:{st.st_size}'))
            continue
        current.add(resolved); prev=previous.get(resolved); sig=f'{st.st_mtime_ns}:{st.st_size}'
        if not prev: changes.append((f,'NOVO',sig))
        elif prev.get('mtime_ns')!=st.st_mtime_ns or prev.get('size')!=st.st_size: changes.append((f,'ALTERADO',sig))
    for old_path in sorted(set(previous)-current): changes.append((Path(old_path),'REMOVIDO','missing'))
    return changes


def _apply_bv_document_changes(contractor: str, folder: Path, changes: list[tuple[Path, str, str]]) -> dict[str, str]:
    """Atualiza apenas os arquivos alterados já encontrados pelo monitor."""
    states: dict[str, str] = {}
    now = datetime.now().isoformat(timespec='seconds')
    root = _bv_report_root(folder)
    with transaction() as con:
        for path, event_type, _ in changes:
            raw_path = str(path) if event_type == 'REMOVIDO' else _display_path(path)
            if event_type == 'REMOVIDO':
                con.execute(
                    "DELETE FROM bv_documents WHERE contractor=? AND file_path=? AND COALESCE(manual_override,0)=0",
                    (contractor, raw_path),
                )
                states[raw_path] = 'REMOVIDO'
                continue
            try:
                stat = _path_stat(path)
                relative = str(path.relative_to(root))
            except (OSError, ValueError):
                states[raw_path] = 'ADIADO'
                continue
            archived = con.execute(
                "SELECT id,mtime_ns,size FROM bv_documents WHERE contractor=? AND file_path=? AND COALESCE(manual_override,0)=1 AND COALESCE(is_active,1)=0",
                (contractor, raw_path),
            ).fetchone()
            if archived:
                changed = archived['mtime_ns'] != stat.st_mtime_ns or archived['size'] != stat.st_size
                if changed:
                    con.execute(
                        """UPDATE bv_documents SET mtime_ns=?,size=?,synced_at=?,is_active=1,manual_override=0
                           WHERE id=?""",
                        (stat.st_mtime_ns, stat.st_size, now, archived['id']),
                    )
                    states[raw_path] = 'INDEXADO'
                else:
                    states[raw_path] = 'ARQUIVADO'
                continue
            parts = Path(relative).parts
            top = parts[0] if len(parts) > 1 else '(raiz)'
            measurement = _measurement_label_from_path(relative)
            con.execute(
                """INSERT INTO bv_documents(contractor,file_path,file_name,relative_path,folder,top_folder,measurement_label,extension,size,mtime_ns,synced_at,is_active,manual_override)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,1,0)
                   ON CONFLICT(contractor,file_path) DO UPDATE SET
                     file_name=excluded.file_name,relative_path=excluded.relative_path,folder=excluded.folder,
                     top_folder=excluded.top_folder,measurement_label=excluded.measurement_label,
                     extension=excluded.extension,size=excluded.size,mtime_ns=excluded.mtime_ns,
                     synced_at=excluded.synced_at,is_active=1""",
                (contractor, raw_path, path.name, relative, str(Path(relative).parent), top,
                 measurement, path.suffix.lower(), stat.st_size, stat.st_mtime_ns, now),
            )
            states[raw_path] = 'INDEXADO'
    return states


def _reset_unreadable_bv_document_metadata(contractor: str) -> int:
    """Mantém no radar PDFs cujo conteúdo ainda não pôde ser processado."""
    pending = rows(
        """SELECT DISTINCT bd.file_path
           FROM bv_documents bd
           JOIN certificate_files cf
             ON cf.contractor=bd.contractor AND cf.file_path=bd.file_path
           WHERE bd.contractor=?
             AND COALESCE(bd.is_active,1)=1
             AND COALESCE(bd.manual_override,0)=0
             AND UPPER(COALESCE(cf.status,'')) IN ('ADIADO','ERRO')""",
        (contractor,),
    )
    paths = [str(item.get('file_path') or '') for item in pending if item.get('file_path')]
    if paths:
        with transaction() as con:
            con.executemany(
                "UPDATE bv_documents SET mtime_ns=-1 WHERE contractor=? AND file_path=?",
                [(contractor, path) for path in paths],
            )
    return len(paths)


def _mark_source_monitor_ok(contractor: str, kind: str) -> None:
    with transaction() as con:
        con.execute(
            "UPDATE sources SET last_sync=?,last_status='OK',last_error='' WHERE contractor=? AND kind=?",
            (datetime.now().isoformat(timespec='seconds'), contractor, kind),
        )


def _source_changed(contractor: str, kind: str) -> tuple[Path,str,str] | None:
    src = row("SELECT * FROM sources WHERE contractor=? AND kind=? AND enabled=1", (contractor, kind))
    if not src or not src.get('path'):
        return None
    p = Path(src['path'])
    if not p.exists() or p.is_dir():
        return None
    try:
        st = p.stat()
    except OSError:
        return None
    sig = f'{st.st_mtime_ns}:{st.st_size}'
    if src.get('last_mtime_ns') != st.st_mtime_ns or src.get('last_size') != st.st_size:
        return p, ('NOVO' if not src.get('last_sync') else 'ALTERADO'), sig
    # Alguns clientes OneDrive preservam tamanho/mtime ao substituir uma planilha.
    # Para d.KIT, confirma também o conteúdo e evita deixar alterações invisíveis.
    if kind == 'kits' and src.get('last_hash'):
        try:
            current_hash = _sha256(p)
        except OSError:
            return None
        if current_hash != src.get('last_hash'):
            return p, 'ALTERADO', f'{sig}:{current_hash[:16]}'
    return None


def _auto_quality_signature(contractor: str, file_hash: str) -> str:
    """Assinatura do preenchimento automático.

    O mesmo PDF só é tentado novamente quando muda o conteúdo do certificado,
    a fonte de medição ou a própria BD_QUALI. Isso evita regravar o Excel a cada
    ciclo de 15 segundos e permite uma nova tentativa quando a base de referência
    realmente mudou.
    """
    med = row("SELECT last_hash,last_mtime_ns,last_size FROM sources WHERE contractor=? AND kind='medicao'", (contractor,)) or {}
    qua = row("SELECT last_hash,last_mtime_ns,last_size FROM sources WHERE contractor=? AND kind='qualidade'", (contractor,)) or {}
    return '|'.join([
        str(file_hash or ''),
        str(med.get('last_hash') or med.get('last_mtime_ns') or ''),
        str(med.get('last_size') or ''),
        str(qua.get('last_hash') or qua.get('last_mtime_ns') or ''),
        str(qua.get('last_size') or ''),
    ])


def auto_fill_quality_for_certificate_paths(contractor: str, paths: list[Path], portal: str = 'BV') -> dict[str, Any]:
    """Preenche automaticamente a BD_QUALI para BI330 recém-detectados.

    Reutiliza exatamente o pipeline da ferramenta PDF → BD_QUALI: 1 CP de rotina
    = 1 linha, matching pela medição, fórmulas do Excel preservadas, backup e troca
    atômica. Só grava certificados cujo plano esteja 100% VINCULADO/PRONTO.
    Casos ambíguos ficam como REVISAR e nunca são escritos automaticamente.
    """
    summary = {'ok': True, 'enabled': _setting_bool('auto_bdquali_enabled', True), 'candidates': 0,
               'written_certificates': 0, 'written_rows': 0, 'already_filled': 0,
               'review': 0, 'errors': 0, 'results': []}
    if not summary['enabled']:
        return summary

    # Import local evita dependência circular no startup.
    from .tools_pdf_quality import analyze_certificates
    from .quality_excel_writer import write_excel_to_main_sources

    # Deduplica por certificate_id: a mesma ocorrência pode estar na pasta
    # certificados e também em Arquivos BV por medição.
    candidates: list[tuple[Path, dict[str, Any]]] = []
    seen_ids: set[int] = set()
    for p in paths:
        try:
            p = Path(p)
            if not p.exists() or p.suffix.lower() != '.pdf' or not _is_bi330_pdf(p):
                continue
            resolved = str(p.resolve())
            cf = row(
                "SELECT certificate_id,file_hash,status,error FROM certificate_files WHERE contractor=? AND file_path=? ORDER BY id DESC LIMIT 1",
                (contractor, resolved),
            )
            if not cf or not cf.get('certificate_id'):
                continue
            status = str(cf.get('status') or '').upper()
            if status in {'DUPLICADO','ERRO','SUBSTITUIDO'}:
                continue
            cid = int(cf['certificate_id'])
            if cid in seen_ids:
                continue
            active = row("SELECT id,is_active FROM certificates WHERE id=? AND contractor=?", (cid, contractor))
            if not active or not int(active.get('is_active') or 0):
                continue
            seen_ids.add(cid)
            candidates.append((p, cf))
        except Exception:
            continue

    summary['candidates'] = len(candidates)
    if not candidates:
        return summary

    parsed: list[tuple[str, Any]] = []
    event_ids: dict[str, int | None] = {}
    event_paths: dict[str, Path] = {}
    event_signatures: dict[str, str] = {}
    parse_errors: dict[str, str] = {}
    for p, cf in candidates:
        key = str(p.resolve())
        signature = _auto_quality_signature(contractor, str(cf.get('file_hash') or ''))
        eid = _begin_monitor_event(contractor, portal, 'bd_quali_auto', p, 'AUTO_PREENCHER', signature)
        event_ids[key] = eid
        event_paths[key] = p
        event_signatures[key] = signature
        # Evento já concluído para a mesma combinação PDF+Medição+BD_QUALI.
        if eid is None:
            continue
        try:
            _wait_file_ready(p)
            cert = parse_pdf(p, contractor)
            parsed.append((key, cert))
        except Exception as exc:
            parse_errors[key] = str(exc)
            _finish_monitor_event(eid, 'ERRO', f'Falha ao analisar para BD_QUALI: {exc}')
            summary['errors'] += 1

    if not parsed:
        summary['ok'] = summary['errors'] == 0
        return summary

    try:
        analysis = analyze_certificates(parsed)
    except Exception as exc:
        for key, _ in parsed:
            eid = event_ids.get(key)
            _finish_monitor_event(eid, 'ERRO', f'Falha na prévia automática da BD_QUALI: {exc}')
        summary['errors'] += len(parsed)
        summary['ok'] = False
        return summary

    ready: list[dict[str, Any]] = []
    ready_keys: set[str] = set()
    for cert in analysis.get('certificates') or []:
        key = str(cert.get('file_name') or '')
        eid = event_ids.get(key)
        expected = int(cert.get('expected_quality_rows') or 0)
        existing = int(cert.get('existing_quality_rows') or 0)
        plan = cert.get('excel_write') or {}
        if expected > 0 and existing == expected and plan.get('mode') == 'ATUALIZAR_EXISTENTE':
            # Arquivo alterado (ex.: contra-prova) pode atualizar os campos já
            # existentes; como a assinatura usa hash, não repete sem mudança real.
            ready.append(cert); ready_keys.add(key)
            continue
        if existing > 0 and existing != expected:
            msg = f'BD_QUALI possui {existing} linha(s), mas o certificado projeta {expected}. Revisão manual necessária.'
            _finish_monitor_event(eid, 'REVISAR', msg)
            summary['review'] += 1
            summary['results'].append({'certificate': cert.get('certificate'), 'status': 'REVISAR', 'message': msg})
            continue
        if existing == 0 and plan.get('ready') and plan.get('mode') == 'ADICIONAR_NOVO':
            ready.append(cert); ready_keys.add(key)
            continue
        if existing >= expected > 0:
            _finish_monitor_event(eid, 'JA_PREENCHIDO', f'BD_QUALI já possui {existing} linha(s) para este certificado.')
            summary['already_filled'] += 1
            summary['results'].append({'certificate': cert.get('certificate'), 'status': 'JA_PREENCHIDO'})
            continue
        msg = str(plan.get('reason') or 'Certificado não está 100% vinculado às medições.')
        _finish_monitor_event(eid, 'REVISAR', msg)
        summary['review'] += 1
        summary['results'].append({'certificate': cert.get('certificate'), 'status': 'REVISAR', 'message': msg})

    if ready:
        write_analysis = {**analysis, 'certificates': ready}
        # Mantém apenas as linhas dos certificados prontos para relatórios/UI.
        ready_names = {str(c.get('file_name') or '') for c in ready}
        write_analysis['lines'] = [x for x in (analysis.get('lines') or []) if str(x.get('file_name') or '') in ready_names]
        try:
            report = write_excel_to_main_sources(write_analysis)
            files = report.get('files') or []
            rows_written = sum(int(x.get('rows_written') or 0) for x in files)
            summary['written_rows'] += rows_written
            summary['written_certificates'] += len(ready)
            # Recarrega a BD_QUALI para que Dashboard/Pendências reflitam a escrita.
            sync_result = sync_source(contractor, 'qualidade', True, recalc=False)
            report['sync_result'] = sync_result
            by_contract = next((x for x in files if str(x.get('contractor') or '').upper() == contractor), None) or {}
            targets = by_contract.get('target_rows') or []
            rows_label = ''
            if targets:
                ordered = sorted(int(x) for x in targets)
                rows_label = f' Linhas Excel: {ordered[0]}-{ordered[-1]}.' if len(ordered) > 1 else f' Linha Excel: {ordered[0]}.'
            for cert in ready:
                key = str(cert.get('file_name') or '')
                eid = event_ids.get(key)
                msg = f'BD_QUALI atualizada automaticamente com {len(cert.get("lines") or [])} linha(s).{rows_label}'
                _finish_monitor_event(eid, 'BD_QUALI_OK', msg)
                # A própria gravação muda o hash da BD_QUALI. Registra também a
                # assinatura pós-gravação para o próximo ciclo não atualizar o
                # mesmo certificado uma segunda vez só por causa dessa mudança.
                try:
                    p = event_paths.get(key)
                    if p is not None:
                        cf_now = row(
                            "SELECT file_hash FROM certificate_files WHERE contractor=? AND file_path=? ORDER BY id DESC LIMIT 1",
                            (contractor, str(p.resolve())),
                        ) or {}
                        post_sig = _auto_quality_signature(contractor, str(cf_now.get('file_hash') or ''))
                        if post_sig != event_signatures.get(key):
                            post_id = _begin_monitor_event(contractor, portal, 'bd_quali_auto', p, 'AUTO_PREENCHER', post_sig)
                            _finish_monitor_event(post_id, 'BD_QUALI_OK', 'Já preenchido automaticamente nesta sincronização.')
                except Exception:
                    pass
                summary['results'].append({'certificate': cert.get('certificate'), 'status': 'BD_QUALI_OK', 'message': msg})
        except Exception as exc:
            for cert in ready:
                key = str(cert.get('file_name') or '')
                _finish_monitor_event(event_ids.get(key), 'ERRO', f'Certificado importado, mas a BD_QUALI não pôde ser atualizada: {exc}')
            summary['errors'] += len(ready)
            summary['results'].append({'status': 'ERRO', 'message': str(exc)})

    summary['ok'] = summary['errors'] == 0
    return summary


def auto_fill_quality_for_recent_certificates(contractor: str, seconds: int = 180) -> dict[str, Any]:
    """Reconcilia certificados recém-processados com a BD_QUALI.

    É usado após Sincronizar tudo/uma fonte, cobrindo o caso em que o usuário
    clica manualmente em Sincronizar antes de o monitor de 15 s detectar o PDF.
    Não faz varredura histórica indiscriminada: considera somente arquivos
    processados nos últimos minutos.
    """
    if not _setting_bool('auto_bdquali_enabled', True):
        return {'ok': True, 'enabled': False, 'candidates': 0, 'written_certificates': 0, 'written_rows': 0, 'already_filled': 0, 'review': 0, 'errors': 0, 'results': []}
    cutoff = (datetime.now() - timedelta(seconds=max(30, int(seconds or 180)))).isoformat(timespec='seconds')
    docs = rows(
        """SELECT file_path FROM certificate_files
           WHERE contractor=? AND COALESCE(parsed_at,'')>=?
             AND UPPER(COALESCE(status,'')) NOT IN ('DUPLICADO','ERRO','SUBSTITUIDO')
           ORDER BY id DESC""",
        (contractor, cutoff),
    )
    paths=[]; seen=set()
    for d in docs:
        raw=str(d.get('file_path') or '')
        if not raw or raw in seen: continue
        p=Path(raw)
        if p.exists() and p.suffix.lower()=='.pdf':
            seen.add(raw); paths.append(p)
    return auto_fill_quality_for_certificate_paths(contractor, paths, 'BV')


def monitor_once() -> dict[str, Any]:
    """Verifica arquivos recém-sincronizados sem depender do botão Sincronizar.

    BV monitora as pastas de certificados BI330. Contratada monitora a d.KIT e
    toda a árvore Entrega Contratada. O loop é por polling leve porque a fonte é
    uma pasta local do OneDrive/SharePoint; ao ligar o servidor, ele também faz
    catch-up de tudo que chegou enquanto o PC estava desligado.
    """
    cfg = monitor_config()
    summary = {'ok': True, 'config': cfg, 'detected': 0, 'processed': 0, 'errors': 0, 'results': []}
    if not cfg['enabled']:
        return summary

    for contractor in ('ARENA','PAVIDEZ'):
        if cfg['bv']:
            src = row("SELECT * FROM sources WHERE contractor=? AND kind='certificados' AND enabled=1", (contractor,))
            folder = Path(src['path']) if src and src.get('path') else None
            if folder and folder.exists() and folder.is_dir():
                changes = _scheduled_folder_changes(
                    contractor, 'certificados', folder, cfg.get('seconds', 15),
                    _certificate_drop_changes,
                )
                if changes:
                    events = [(p, typ, _begin_monitor_event(contractor,'BV','certificados',p,typ,sig)) for p,typ,sig in changes]
                    summary['detected'] += len([1 for _,_,eid in events if eid])
                    changed_paths = [p for p, typ, eid in events if eid and typ != 'REMOVIDO']
                    with SYNC_LOCK:
                        imported, skipped, errors, candidates = _sync_certificate_paths(contractor, changed_paths, False, 'certificados')
                        if imported:
                            recalculate_matches(contractor)
                        _mark_source_monitor_ok(contractor, 'certificados')
                    result = {
                        'ok': errors == 0, 'records': imported, 'skipped_files': skipped, 'errors': errors,
                        'message': f'Monitor incremental: {candidates} PDF(s), {imported} importado(s), {skipped} inalterado(s), {errors} erro(s).',
                    }
                    summary['results'].append({'contractor':contractor,'kind':'certificados',**result})
                    auto_paths = changed_paths
                    if auto_paths and cfg.get('auto_quality', True):
                        queued = _enqueue_auto_quality(contractor, auto_paths)
                        summary['results'].append({
                            'contractor': contractor, 'kind': 'bd_quali_auto', 'ok': True,
                            'queued': queued,
                            'message': f'{queued} certificado(s) agendado(s) para a BD_QUALI sem bloquear o monitor.',
                        })
                    for p, typ, eid in events:
                        if not eid:
                            continue
                        current = row(
                            "SELECT status,error FROM certificate_files WHERE contractor=? AND file_path=? ORDER BY id DESC LIMIT 1",
                            (contractor, str(p.resolve())),
                        )
                        status = str((current or {}).get('status') or ('ERRO' if not result.get('ok') else 'CARREGADO')).upper()
                        ok = status not in {'ERRO'}
                        _finish_monitor_event(eid, status if ok else 'ERRO', (current or {}).get('error') or result.get('message',''))
                        summary['processed'] += 1 if ok else 0
                        summary['errors'] += 0 if ok else 1

            # Árvore de arquivos operacionais da BV, organizada por pastas Mxx.
            bvsrc = row("SELECT * FROM sources WHERE contractor=? AND kind='bv_documentos' AND enabled=1", (contractor,))
            bvfolder = Path(bvsrc['path']) if bvsrc and bvsrc.get('path') else None
            if bvfolder and bvfolder.exists() and bvfolder.is_dir():
                _reset_unreadable_bv_document_metadata(contractor)
                changes = _scheduled_folder_changes(
                    contractor, 'bv_documentos', bvfolder, cfg.get('seconds', 15),
                    _bv_document_drop_changes,
                )
                if changes:
                    events=[(p,typ,_begin_monitor_event(contractor,'BV','bv_documentos',p,typ,sig)) for p,typ,sig in changes]
                    summary['detected'] += len([1 for _,_,eid in events if eid])
                    actionable = [(p, typ, sig) for p, typ, sig in changes if any(ep == p and eid for ep, _, eid in events)]
                    with SYNC_LOCK:
                        # A reconciliação do índice é idempotente e deve ocorrer
                        # mesmo quando o mesmo evento já foi concluído. Assim um
                        # evento antigo nunca mantém mtime/tamanho obsoletos e
                        # não prende o monitor em uma falsa alteração eterna.
                        states = _apply_bv_document_changes(contractor, bvfolder, changes)
                        changed_bi = [
                            p for p, typ, _ in actionable
                            if typ != 'REMOVIDO'
                            and _is_bi330_pdf(p)
                            and states.get(str(p.resolve())) == 'INDEXADO'
                        ]
                        imported, skipped, errors, candidates = _sync_certificate_paths(contractor, changed_bi, False, 'bv_documentos')
                        if imported:
                            recalculate_matches(contractor)
                        _mark_source_monitor_ok(contractor, 'bv_documentos')
                    result = {
                        'ok': errors == 0, 'records': len(actionable),
                        'certificates_imported': imported, 'certificate_candidates': candidates,
                        'certificate_skipped': skipped, 'certificate_errors': errors,
                        'message': f'Monitor incremental: {len(actionable)} arquivo(s) atualizado(s); {candidates} BI330, {imported} importado(s), {errors} erro(s).',
                    }
                    summary['results'].append({'contractor':contractor,'kind':'bv_documentos',**result})
                    auto_paths = changed_bi
                    if auto_paths and cfg.get('auto_quality', True):
                        queued = _enqueue_auto_quality(contractor, auto_paths)
                        summary['results'].append({
                            'contractor': contractor, 'kind': 'bd_quali_auto', 'ok': True,
                            'queued': queued,
                            'message': f'{queued} certificado(s) agendado(s) para a BD_QUALI sem bloquear o monitor.',
                    })
                    for p,typ,eid in events:
                        if not eid:
                            if typ != 'REMOVIDO':
                                resolved = str(p.resolve())
                                signature = next((sig for ep, et, sig in changes if ep == p and et == typ), '')
                                previous_event = row(
                                    """SELECT status FROM auto_import_events
                                       WHERE contractor=? AND kind='bv_documentos' AND file_path=?
                                         AND signature=? AND event_type=?
                                       ORDER BY id DESC LIMIT 1""",
                                    (contractor, resolved, signature, typ),
                                )
                                if str((previous_event or {}).get('status') or '').upper() in {'ADIADO', 'ERRO', 'DETECTADO'}:
                                    with transaction() as con:
                                        con.execute(
                                            "UPDATE bv_documents SET mtime_ns=-1 WHERE contractor=? AND file_path=?",
                                            (contractor, resolved),
                                        )
                            continue
                        if typ=='REMOVIDO':
                            state = states.get(str(p), 'REMOVIDO')
                            ok = state != 'ERRO'
                            message=result.get('message','')
                        else:
                            resolved=str(p.resolve())
                            state = states.get(resolved, 'ADIADO')
                            ok = state != 'ERRO'
                            message=result.get('message','')
                            if state == 'INDEXADO' and _is_bi330_pdf(p):
                                current=row(
                                    "SELECT status,error,certificate_id FROM certificate_files WHERE contractor=? AND file_path=? ORDER BY id DESC LIMIT 1",
                                    (contractor,resolved),
                                )
                                if current:
                                    state=str(current.get('status') or 'CARREGADO').upper()
                                    message=current.get('error') or message
                                    ok=state!='ERRO'
                                if state in {'ADIADO', 'ERRO'}:
                                    # Mantém o documento visível, mas força nova
                                    # tentativa enquanto o placeholder do
                                    # OneDrive/SharePoint não puder ser aberto.
                                    with transaction() as con:
                                        con.execute(
                                            "UPDATE bv_documents SET mtime_ns=-1 WHERE contractor=? AND file_path=?",
                                            (contractor, resolved),
                                        )
                        _finish_monitor_event(eid,state if ok else 'ERRO',message)
                        summary['processed'] += 1 if ok else 0
                        summary['errors'] += 0 if ok else 1

        if cfg['contractor']:
            # A planilha d.KIT também entra automaticamente quando o OneDrive a atualiza.
            kit_change = _source_changed(contractor, 'kits')
            if kit_change:
                p, typ, sig = kit_change
                eid = _begin_monitor_event(contractor,'CONTRATADA','kits',p,typ,sig)
                if eid:
                    summary['detected'] += 1
                    result = sync_source(contractor, 'kits', False, recalc=False)
                    summary['results'].append({'contractor':contractor,'kind':'kits',**result})
                    ok = bool(result.get('ok'))
                    _finish_monitor_event(eid, 'CARREGADO' if ok else 'ERRO', result.get('message',''))
                    summary['processed'] += 1 if ok else 0
                    summary['errors'] += 0 if ok else 1

            src = row("SELECT * FROM sources WHERE contractor=? AND kind='kit_documentos' AND enabled=1", (contractor,))
            folder = Path(src['path']) if src and src.get('path') else None
            if folder and folder.exists() and folder.is_dir():
                changes = _scheduled_folder_changes(
                    contractor, 'kit_documentos', folder, cfg.get('seconds', 15),
                    _kit_document_drop_changes,
                )
                if changes:
                    events = [(p, typ, _begin_monitor_event(contractor,'CONTRATADA','kit_documentos',p,typ,sig)) for p,typ,sig in changes]
                    summary['detected'] += len([1 for _,_,eid in events if eid])
                    with SYNC_LOCK:
                        states = _apply_kit_document_changes(contractor, folder, changes)
                        _mark_source_monitor_ok(contractor, 'kit_documentos')
                    failures = sum(1 for state in states.values() if state == 'ERRO')
                    result = {
                        'ok': failures == 0,
                        'records': sum(1 for state in states.values() if state == 'INDEXADO'),
                        'errors': failures,
                        'message': (
                            f'Monitor incremental: {len(changes)} alteração(ões), '
                            f'{failures} erro(s).'
                        ),
                    }
                    summary['results'].append({'contractor':contractor,'kind':'kit_documentos',**result})
                    for p, typ, eid in events:
                        if not eid:
                            continue
                        raw_path = str(p) if typ == 'REMOVIDO' else str(p.resolve())
                        state = states.get(raw_path, 'ERRO')
                        ok = state != 'ERRO'
                        _finish_monitor_event(eid, state, result.get('message',''))
                        summary['processed'] += 1 if ok else 0
                        summary['errors'] += 0 if ok else 1
    summary['ok'] = summary['errors'] == 0
    return summary


async def auto_monitor_loop(default_seconds: int = 15):
    await asyncio.sleep(2)
    while True:
        cfg = monitor_config()
        try:
            from .runtime_control import JobBusyError, is_paused, job, update
            if cfg['enabled'] and not is_paused():
                try:
                    with job('auto_monitor', 'Monitor automático das pastas', 1):
                        update(current='Procurando arquivos novos...')
                        try:
                            await asyncio.wait_for(asyncio.to_thread(monitor_once), timeout=180)
                        except asyncio.TimeoutError:
                            update(current='Tempo esgotado (arquivo lento/indisponível) — pulando esta rodada.')
                            log_sync(None, 'auto_monitor', 'AVISO', 'Monitor automático excedeu 180s (provável arquivo preso na nuvem/OneDrive) — rodada pulada para não travar o sistema.', 0, '')
                        else:
                            update(processed=1)
                except JobBusyError:
                    pass
        except Exception as exc:
            log_sync(None, 'auto_monitor', 'ERRO', f'Monitor automático: {type(exc).__name__}: {exc}', 0, '')
        await asyncio.sleep(max(10, int(cfg.get('seconds') or default_seconds)))


async def auto_quality_loop(default_seconds: int = 3):
    """Processa a BD_QUALI fora do caminho crítico do monitor do SharePoint."""
    await asyncio.sleep(4)
    _recover_pending_auto_quality_jobs()
    while True:
        from .runtime_control import JobBusyError, is_paused, job, update
        if is_paused():
            await asyncio.sleep(max(2, int(default_seconds or 3)))
            continue
        jobs = _take_auto_quality_jobs()
        for contractor, paths in jobs.items():
            try:
                with job('auto_quality', f'Atualização automática BD_QUALI / {contractor}', 1):
                    update(current=f'{len(paths)} certificado(s) na fila')
                    await asyncio.to_thread(auto_fill_quality_for_certificate_paths, contractor, paths, 'BV')
                    update(processed=1)
            except JobBusyError:
                _enqueue_auto_quality(contractor, paths)
            except Exception as exc:
                # Não perde a fila em uma falha transitória (arquivo em sync,
                # Excel temporariamente bloqueado etc.). As assinaturas dos
                # eventos tornam a repetição segura.
                _enqueue_auto_quality(contractor, paths)
                log_sync(
                    contractor, 'bd_quali_auto', 'ERRO',
                    f'Fila automática da BD_QUALI: {type(exc).__name__}: {exc}', 0, '',
                )
        await asyncio.sleep(max(2, int(default_seconds or 3)))


async def auto_sync_loop(seconds: int = 60):
    # Dá prioridade ao monitor de novos arquivos no startup para registrar a fila
    # de importação antes da sincronização geral das planilhas.
    await asyncio.sleep(6)
    while True:
        try:
            from .runtime_control import JobBusyError, is_paused, job, update
            if not is_paused():
                try:
                    with job('auto_sync', 'Sincronização econômica das planilhas', 1):
                        update(current='Verificando somente planilhas alteradas...')
                        await asyncio.to_thread(sync_changed_spreadsheets)
                        update(processed=1)
                except JobBusyError:
                    pass
        except Exception as exc:
            log_sync(None, 'auto_sync', 'ERRO', f'Sincronização periódica: {type(exc).__name__}: {exc}', 0, '')
        await asyncio.sleep(max(15, seconds))
