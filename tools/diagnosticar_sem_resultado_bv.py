"""Diagnóstico somente leitura dos certificados BV em Situação = Sem resultado.

Uso:
    python tools/diagnosticar_sem_resultado_bv.py
    python tools/diagnosticar_sem_resultado_bv.py --parse

Sem --parse, apenas consulta o SQLite em modo read-only.
Com --parse, tenta reler os PDFs vinculados que existirem localmente, também sem
persistir nada no banco. A atualização oficial deve ser feita pelo botão
"Validar sem resultado" no portal ou pela sincronização normal.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qualimatch.certificate_stats import summarize_phase
from qualimatch.pdf_reader import PARSER_VERSION, parse_pdf


def _overall(cert: dict, samples: list[dict]) -> str:
    try:
        raw = json.loads(cert.get("raw_json") or "{}")
    except Exception:
        raw = {}
    printed = raw.get("phase_summaries") or {}
    phases = []
    for phase in ("ROTINA", "CONTRA_PROVA"):
        ps = [x for x in samples if x.get("phase") == phase]
        if not ps:
            continue
        stats = summarize_phase(ps, printed.get(phase) or {})
        stats["phase"] = phase
        printed_overall = cert.get("counterproof_result") if phase == "CONTRA_PROVA" else cert.get("routine_result")
        if printed_overall:
            stats["overall_status"] = printed_overall
        phases.append(stats)
    final = next((x for x in phases if x["phase"] == "CONTRA_PROVA"), None) or (phases[0] if phases else {})
    return str(final.get("overall_status") or "").upper().strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "qualimatch.db"))
    ap.add_argument("--parse", action="store_true", help="Tenta reler os PDFs que existem localmente, sem gravar no banco")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    certs = [dict(r) for r in con.execute("SELECT * FROM certificates WHERE COALESCE(is_active,1)=1")]
    samples_by: dict[int, list[dict]] = defaultdict(list)
    for row in con.execute("SELECT * FROM certificate_samples ORDER BY certificate_id,id"):
        samples_by[int(row["certificate_id"])].append(dict(row))

    sem = [c for c in certs if not _overall(c, samples_by.get(int(c["id"]), []))]
    by_contractor = Counter(str(c.get("contractor") or "") for c in sem)
    print(f"Parser atual: {PARSER_VERSION}")
    print(f"Certificados ativos: {len(certs)}")
    print(f"Situação = Sem resultado: {len(sem)}")
    print("Por contratada: " + ", ".join(f"{k}={v}" for k, v in sorted(by_contractor.items())))

    if not args.parse:
        return 0

    docs_by: dict[int, list[str]] = defaultdict(list)
    for r in con.execute(
        """SELECT certificate_id,file_path,status FROM certificate_files
           WHERE certificate_id IS NOT NULL AND COALESCE(status,'') NOT IN ('SUBSTITUIDO','EXCLUIDO')"""
    ):
        docs_by[int(r["certificate_id"])].append(str(r["file_path"] or ""))

    ok = still_zero = missing = errors = 0
    reasons = Counter()
    for idx, cert in enumerate(sem, 1):
        paths = docs_by.get(int(cert["id"]), []) + [str(cert.get("file_path") or "")]
        pdf = next((Path(p) for p in paths if p and Path(p).is_file()), None)
        if pdf is None:
            missing += 1
            continue
        try:
            parsed = parse_pdf(pdf, str(cert.get("contractor") or ""))
            if parsed.samples:
                ok += 1
            else:
                still_zero += 1
                warnings = (parsed.raw or {}).get("parse_warnings") or []
                reasons[(warnings[0] if warnings else "Nenhum corpo de prova extraído")] += 1
        except Exception as exc:
            errors += 1
            reasons[type(exc).__name__ + ": " + str(exc)] += 1
        if idx % 50 == 0:
            print(f"  {idx}/{len(sem)} analisados...")

    print(f"Relidos com CPs: {ok}")
    print(f"Ainda sem CPs: {still_zero}")
    print(f"PDF local não encontrado: {missing}")
    print(f"Erros de leitura: {errors}")
    if reasons:
        print("Principais motivos:")
        for reason, n in reasons.most_common(20):
            print(f"  {n}x {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
