from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv, set_key

load_dotenv(ROOT / '.env', override=True)

from qualimatch.database import init_db, backend_name
from qualimatch.auth import create_or_update_admin

ENV = ROOT / '.env'
ENV.touch(exist_ok=True)


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = ' [S/n]: ' if default else ' [s/N]: '
    value = input(prompt + suffix).strip().lower()
    if not value:
        return default
    return value in {'s', 'sim', 'y', 'yes'}


print('\n=== QualiMatch v3.2 - Administrador e e-mail ===\n')
init_db()
print(f'Banco ativo: {backend_name()}')
if backend_name() != 'postgresql':
    print('AVISO: DATABASE_URL não está apontando para PostgreSQL. O administrador será criado no SQLite atual.')

name = input('Nome do administrador: ').strip()
email = input('E-mail do administrador: ').strip()
password = getpass.getpass('Senha do administrador: ')
confirm = getpass.getpass('Confirme a senha: ')
if password != confirm:
    raise SystemExit('As senhas não conferem. Configuração cancelada.')

try:
    admin = create_or_update_admin(name, email, password)
except Exception as exc:
    raise SystemExit(f'Não foi possível criar o administrador: {exc}')

print(f"\n[OK] Administrador: {admin['name']} <{admin['email']}>")

if ask_yes_no('\nConfigurar agora o envio de e-mails de cadastro e recuperação de senha?', True):
    print('\nProvedor sugerido:')
    print('  1 - Gmail / Google Workspace')
    print('  2 - Outlook / Microsoft 365 (SMTP AUTH precisa estar habilitado)')
    print('  3 - Outro SMTP')
    provider = input('Escolha [1]: ').strip() or '1'
    if provider == '1':
        host, port, tls, ssl = 'smtp.gmail.com', '587', 'true', 'false'
    elif provider == '2':
        host, port, tls, ssl = 'smtp.office365.com', '587', 'true', 'false'
    else:
        host = input('SMTP host: ').strip()
        port = input('SMTP porta [587]: ').strip() or '587'
        tls = 'true' if ask_yes_no('Usar STARTTLS?', True) else 'false'
        ssl = 'false'

    smtp_user = input(f'Usuário SMTP [{admin["email"]}]: ').strip() or admin['email']
    print('Para Gmail, use uma Senha de App; não use a senha comum se a conta tiver verificação em duas etapas.')
    smtp_password = getpass.getpass('Senha / Senha de App SMTP: ')
    smtp_from = input(f'Remetente [{smtp_user}]: ').strip() or smtp_user
    app_base = input('Endereço do QualiMatch na rede [deixe vazio para usar o endereço acessado pelo usuário]: ').strip()

    for key, value in {
        'SMTP_HOST': host,
        'SMTP_PORT': port,
        'SMTP_USER': smtp_user,
        'SMTP_PASSWORD': smtp_password,
        'SMTP_FROM': smtp_from,
        'SMTP_STARTTLS': tls,
        'SMTP_SSL': ssl,
        'APP_BASE_URL': app_base,
    }.items():
        set_key(str(ENV), key, value, quote_mode='always')
    print('[OK] Configuração SMTP salva no .env local.')
else:
    print('\nE-mail ficou desativado por enquanto. Solicitações continuarão aparecendo no painel de Administração.')

print('\nConfiguração concluída.')
print('Agora execute iniciar.bat (ou migrar_para_postgres.bat antes, se ainda não migrou o SQLite).')
