"""Cria ou recria a base fictícia da QualiMatch V2."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qualimatch.database import init_db
from qualimatch.demo_seed import DEMO_EMAIL, DEMO_PASSWORD, ensure_demo_data


parser = argparse.ArgumentParser()
parser.add_argument("--reset", action="store_true", help="Recria integralmente os dados fictícios.")
args = parser.parse_args()
init_db()
result = ensure_demo_data(force=args.reset)
print(result)
print(f"Acesso demo: {DEMO_EMAIL} / {DEMO_PASSWORD}")
