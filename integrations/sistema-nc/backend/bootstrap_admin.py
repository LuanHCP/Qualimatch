#!/usr/bin/env python3
"""Cria o administrador local inicial (perfil admin_geral).

Uso:
    python3 bootstrap_admin.py --email admin@empresa.com --nome "Administrador" --senha "TrocarNoPrimeiroAcesso123"
    (ou defina BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD / BOOTSTRAP_ADMIN_NOME no ambiente e rode sem argumentos)

O usuário criado é obrigado a trocar a senha no primeiro login
(must_change_password = TRUE). Não sobrescreve um admin_geral já
existente com o mesmo e-mail; se já existir algum admin_geral ativo no
sistema, avisa e não faz nada (evita criar administradores duplicados
"silenciosamente" a cada deploy).
"""
import sys
import os
import argparse
import secrets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402
import security  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email")
    ap.add_argument("--nome")
    ap.add_argument("--senha")
    ap.add_argument("--force", action="store_true", help="cria mesmo se já existir um admin_geral ativo")
    args = ap.parse_args()

    email = (args.email or os.environ.get("BOOTSTRAP_ADMIN_EMAIL") or "").strip().lower()
    nome = args.nome or os.environ.get("BOOTSTRAP_ADMIN_NOME") or "Administrador do Sistema"
    senha = args.senha or os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")

    if not email:
        print("Erro: informe --email ou BOOTSTRAP_ADMIN_EMAIL.", file=sys.stderr)
        sys.exit(1)

    gerou_senha = False
    if not senha:
        senha = secrets.token_urlsafe(12)
        gerou_senha = True

    existing = db.fetchone(f"SELECT id, perfil, ativo FROM users WHERE email = {db.lit(email)};")
    if existing:
        print(f"Já existe um usuário com o e-mail {email} (perfil {existing['perfil']}). Nada foi criado.")
        sys.exit(1)

    if not args.force:
        outros = db.fetchone("SELECT count(*) AS n FROM users WHERE perfil = 'admin_geral' AND ativo = TRUE;")
        if int(outros["n"]) > 0:
            print("Já existe pelo menos um administrador geral ativo no sistema. "
                  "Use a tela de Administração para criar outros usuários, ou rode com --force para criar mesmo assim.")
            sys.exit(1)

    senha_hash = security.hash_password(senha)
    row = db.fetchone(f"""
        INSERT INTO users (nome, email, senha_hash, perfil, must_change_password)
        VALUES ({db.lit(nome)}, {db.lit(email)}, {db.lit(senha_hash)}, 'admin_geral', TRUE)
        RETURNING id;
    """)
    print("Administrador local criado com sucesso.")
    print(f"  id:    {row['id']}")
    print(f"  nome:  {nome}")
    print(f"  email: {email}")
    if gerou_senha:
        print(f"  senha provisória (gerada automaticamente): {senha}")
    print("  Senha deve ser trocada obrigatoriamente no primeiro login.")


if __name__ == "__main__":
    main()
