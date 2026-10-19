from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qualimatch.database import rows  # noqa: E402
from qualimatch.local_sync import monitor_config, monitor_events  # noqa: E402


def build_report() -> dict:
    sources = []
    configured = rows(
        "SELECT contractor,kind,path,enabled,last_status,last_error,last_sync "
        "FROM sources WHERE kind='certificados' ORDER BY contractor"
    )
    for source in configured:
        item = {
            key: source.get(key)
            for key in ("contractor", "kind", "path", "enabled", "last_status", "last_error", "last_sync")
        }
        path = Path(source["path"]) if source.get("path") else None
        item["exists"] = bool(path and path.is_dir())
        item["recent_indexed_pdfs"] = rows(
            "SELECT file_name,status,error,parsed_at,size FROM certificate_files "
            "WHERE contractor=? ORDER BY parsed_at DESC,id DESC LIMIT 12",
            (source["contractor"],),
        )
        sources.append(item)
    return {"monitor": monitor_config(), "sources": sources, "recent_events": monitor_events(30)}


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, default=str))
