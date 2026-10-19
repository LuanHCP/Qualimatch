from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qualimatch.doctor import doctor_exit_code, format_doctor_report, run_doctor


def main() -> int:
    report = run_doctor(ROOT)
    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_doctor_report(report))
    return doctor_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
