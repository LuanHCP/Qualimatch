#!/usr/bin/env python3
"""Cria, de forma idempotente, o administrador padrão para demonstração."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402
import security  # noqa: E402


DEMO_EMAIL = "admin@qualimatch.local"
DEMO_PASSWORD = "Demo@2026"
DEMO_NAME = "Administrador Demo"


def main():
    existing = db.fetchone(
        f"SELECT id, perfil, ativo, approval_status FROM users WHERE email = {db.lit(DEMO_EMAIL)};"
    )
    if existing:
        print(f"Administrador de teste já existe: {DEMO_EMAIL}. A senha não foi alterada.")
        return 0

    password_hash = security.hash_password(DEMO_PASSWORD)
    row = db.fetchone(f"""
        INSERT INTO users (
            nome, email, senha_hash, perfil, ativo, bloqueado,
            must_change_password, approval_status
        )
        VALUES (
            {db.lit(DEMO_NAME)}, {db.lit(DEMO_EMAIL)}, {db.lit(password_hash)},
            'admin_geral', TRUE, FALSE, TRUE, 'aprovado'
        )
        RETURNING id;
    """)
    print("Administrador padrão de teste criado com sucesso.")
    print(f"  id:      {row['id']}")
    print(f"  usuário: {DEMO_EMAIL}")
    print(f"  senha:   {DEMO_PASSWORD}")
    print("  A troca da senha será exigida no primeiro acesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
