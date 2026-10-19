from __future__ import annotations

from collections import defaultdict
import json
from datetime import datetime
from .database import transaction


def recalculate_matches(contractor: str | None = None) -> None:
    """Recalcula os vínculos sem fazer uma consulta SQL por linha de medição.

    A versão antiga consultava certificados/amostras milhares de vezes. Aqui todos
    os dados necessários são carregados uma vez e o resultado é gravado em lote.
    """
    with transaction() as con:
        if contractor:
            measurements = con.execute("SELECT * FROM measurements WHERE contractor=?", (contractor,)).fetchall()
            certificates = con.execute("SELECT * FROM certificates WHERE contractor=? AND is_active=1", (contractor,)).fetchall()
        else:
            measurements = con.execute("SELECT * FROM measurements").fetchall()
            certificates = con.execute("SELECT * FROM certificates WHERE is_active=1").fetchall()

        cert_ids = [c["id"] for c in certificates]
        sample_map: dict[int, dict[str, set[str]]] = defaultdict(lambda: {"dirs": set(), "lanes": set()})
        if cert_ids:
            placeholders = ",".join("?" for _ in cert_ids)
            for s in con.execute(
                f"SELECT certificate_id,application_date,direction,lane FROM certificate_samples WHERE certificate_id IN ({placeholders})",
                tuple(cert_ids),
            ).fetchall():
                if s["direction"]:
                    sample_map[s["certificate_id"]]["dirs"].add(s["direction"])
                if s["lane"]:
                    sample_map[s["certificate_id"]]["lanes"].add(s["lane"])
                if s["application_date"]:
                    sample_map[s["certificate_id"]].setdefault("dates", set()).add(s["application_date"])

        # Matching usa exclusivamente datas de EXECUÇÃO. extraction_date é a
        # data principal exibida do certificado, mas não representa quando o serviço
        # foi executado. Inclui todas as Datas ex. serviço do raw e as datas dos CPs.
        by_date: dict[tuple[str, str | None], list] = defaultdict(list)
        for c in certificates:
            covered_dates = {c["service_date"]} if c["service_date"] else set()
            covered_dates.update(sample_map.get(c["id"], {}).get("dates", set()))
            try:
                raw = json.loads(c["raw_json"] or "{}")
            except Exception:
                raw = {}
            covered_dates.update(str(d) for d in (raw.get("service_dates") or []) if d)
            for covered_date in covered_dates:
                by_date[(c["contractor"], covered_date)].append(c)

        now = datetime.now().isoformat(timespec="seconds")
        payload = []
        for m in measurements:
            certs = by_date.get((m["contractor"], m["date"]), [])
            best = None
            best_score = -1
            best_reason = "SEM CERTIFICADO NA DATA"
            for c in certs:
                score = 50
                reasons = ["DATA=OK"]
                if m["road"] and c["road"]:
                    if m["road"] != c["road"]:
                        continue
                    score += 20
                    reasons.append("RODOVIA=OK")
                if None not in (m["kmi"], m["kmf"], c["kmi"], c["kmf"]):
                    lo = max(min(m["kmi"], m["kmf"]), min(c["kmi"], c["kmf"]))
                    hi = min(max(m["kmi"], m["kmf"]), max(c["kmi"], c["kmf"]))
                    if lo <= hi:
                        score += 20
                        reasons.append("SEGMENTO=OK")
                    else:
                        continue
                attrs = sample_map.get(c["id"], {"dirs": set(), "lanes": set()})
                if m["direction"] and m["direction"] in attrs["dirs"]:
                    score += 5
                    reasons.append("SENTIDO=OK")
                if m["lane"] and m["lane"] in attrs["lanes"]:
                    score += 5
                    reasons.append("FAIXA=OK")
                if score > best_score:
                    best_score = score
                    best = c
                    best_reason = " | ".join(reasons)
            payload.append((m["id"], best["id"] if best else None, max(best_score, 0), best_reason, now))

        if contractor:
            con.execute(
                "DELETE FROM matches WHERE measurement_id IN (SELECT id FROM measurements WHERE contractor=?)",
                (contractor,),
            )
        else:
            con.execute("DELETE FROM matches")
        con.executemany(
            "INSERT INTO matches(measurement_id,certificate_id,score,reason,matched_at) VALUES(?,?,?,?,?)",
            payload,
        )
