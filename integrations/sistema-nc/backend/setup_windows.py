#!/usr/bin/env python3
"""Instalador local: cria usuário/banco PostgreSQL, ambiente Python e tabelas."""
import getpass
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

def ask(label, default=""):
    value = input(f"{label}" + (f" [{default}]" if default else "") + ": ").strip()
    return value or default

def sql_text(value):
    return "'" + value.replace("'", "''") + "'"

def find_psql():
    found = shutil.which("psql")
    if found: return Path(found)
    base = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PostgreSQL"
    candidates = sorted(base.glob("*/bin/psql.exe"), reverse=True)
    return candidates[0] if candidates else None

def run(cmd, env=None, check=True):
    print("  >", " ".join(str(x) for x in cmd[:3]), "...")
    return subprocess.run([str(x) for x in cmd], env=env, check=check)

def psql(psql_exe, host, port, user, password, database, sql, capture=False):
    env=os.environ.copy();env["PGPASSWORD"]=password
    return subprocess.run([str(psql_exe),"-X","-v","ON_ERROR_STOP=1","-h",host,"-p",port,"-U",user,"-d",database,"-tAc",sql],env=env,text=True,capture_output=capture)

def main():
    print("\n=== Sistema de Nao Conformidades - instalacao PostgreSQL ===\n")
    psql_exe=find_psql()
    if not psql_exe:
        print("ERRO: psql.exe nao encontrado. Instale o PostgreSQL Database Server (com Command Line Tools). O pgAdmin 4 sozinho nao cria o servidor.")
        return 1
    host=ask("Servidor PostgreSQL","localhost");port=ask("Porta","5432");admin_user=ask("Usuario administrador do PostgreSQL","postgres")
    admin_password=getpass.getpass("Senha do usuario PostgreSQL: ")
    db_name=ask("Nome do banco da aplicacao","nc_sistema");db_user=ask("Usuario do banco da aplicacao","nc_app")
    if not IDENT.match(db_name) or not IDENT.match(db_user):
        print("ERRO: nomes de banco/usuario devem conter apenas letras, numeros e sublinhado.");return 1
    app_password=getpass.getpass("Senha para o usuario nc_app [Enter para gerar]: ") or secrets.token_urlsafe(18)
    admin_email=ask("E-mail do administrador do sistema","admin@qualimatch.local")
    admin_name=ask("Nome do administrador","Administrador Demo")
    first_password=getpass.getpass("Senha provisoria do sistema [Enter para Demo@2026]: ") or "Demo@2026"
    test=psql(psql_exe,host,port,admin_user,admin_password,"postgres","SELECT 1;",capture=True)
    if test.returncode:
        print("ERRO: nao foi possivel conectar ao PostgreSQL. Confira servidor, porta, usuario e senha.\n"+(test.stderr or ""));return 1
    role_exists=psql(psql_exe,host,port,admin_user,admin_password,"postgres",f"SELECT 1 FROM pg_roles WHERE rolname={sql_text(db_user)};",capture=True).stdout.strip()
    role_sql=(f'ALTER ROLE "{db_user}" LOGIN PASSWORD {sql_text(app_password)};' if role_exists else f'CREATE ROLE "{db_user}" LOGIN PASSWORD {sql_text(app_password)};')
    if psql(psql_exe,host,port,admin_user,admin_password,"postgres",role_sql).returncode:return 1
    db_exists=psql(psql_exe,host,port,admin_user,admin_password,"postgres",f"SELECT 1 FROM pg_database WHERE datname={sql_text(db_name)};",capture=True).stdout.strip()
    if not db_exists and psql(psql_exe,host,port,admin_user,admin_password,"postgres",f'CREATE DATABASE "{db_name}" OWNER "{db_user}";').returncode:return 1
    if psql(psql_exe,host,port,admin_user,admin_password,"postgres",f'ALTER DATABASE "{db_name}" OWNER TO "{db_user}";').returncode:return 1
    env_lines={"PGHOST":host,"PGPORT":port,"PGDATABASE":db_name,"PGUSER":db_user,"PGPASSWORD":app_password,"APP_SECRET_KEY":secrets.token_hex(32),"COOKIE_SECURE":"false","SESSION_LIFETIME_MINUTES":"480","SESSION_ABSOLUTE_MAX_HOURS":"24","LOGIN_MAX_ATTEMPTS":"5","LOGIN_LOCKOUT_MINUTES":"15","MAX_UPLOAD_MB":"15","BOOTSTRAP_ADMIN_EMAIL":admin_email,"BOOTSTRAP_ADMIN_NOME":admin_name}
    env_lines.update({"ADMIN_NOTIFICATION_EMAIL":"admin@qualimatch.local","EMAIL_USE_OUTLOOK":"false"})
    (ROOT/".env").write_text("\n".join(f"{k}={v}" for k,v in env_lines.items())+"\n",encoding="utf-8")
    (ROOT/".postgres-bin").write_text(str(psql_exe.parent),encoding="utf-8")
    venv=ROOT/".venv";run([sys.executable,"-m","venv",venv])
    py=venv/"Scripts"/"python.exe";run([py,"-m","pip","install","--disable-pip-version-check","-r",ROOT/"backend"/"requirements.txt"])
    child=os.environ.copy();child.update(env_lines);child["BOOTSTRAP_ADMIN_PASSWORD"]=first_password;child["PATH"]=str(psql_exe.parent)+os.pathsep+child.get("PATH","")
    run([py,ROOT/"backend"/"migrate.py"],env=child);run([py,ROOT/"backend"/"seed_demo.py"],env=child)
    boot=subprocess.run([str(py),str(ROOT/"backend"/"bootstrap_admin.py")],env=child)
    if boot.returncode not in (0,1):return boot.returncode
    run([py,ROOT/"backend"/"ensure_demo_admin.py"],env=child)
    print("\nInstalacao concluida.")
    print("Banco:",db_name," | Usuario:",db_user)
    print("Login do sistema:",admin_email)
    print("Senha provisoria:",first_password)
    print("Guarde estes dados. A senha sera trocada no primeiro acesso.\n")
    print("Acesso padrao para demonstracao:")
    print("Usuario: admin@qualimatch.local")
    print("Senha: Demo@2026")
    print("A senha de demonstracao tambem deve ser trocada no primeiro acesso.\n")
    return 0

if __name__ == "__main__": raise SystemExit(main())
