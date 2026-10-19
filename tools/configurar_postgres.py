from __future__ import annotations

import getpass
from pathlib import Path
from urllib.parse import quote
from dotenv import set_key

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / '.env'

print('\n=== QualiMatch - Configuração PostgreSQL ===\n')
host = input('Host [127.0.0.1]: ').strip() or '127.0.0.1'
port = input('Porta [5432]: ').strip() or '5432'
db = input('Banco [qualimatch]: ').strip() or 'qualimatch'
user = input('Usuário [qualimatch_app]: ').strip() or 'qualimatch_app'
password = getpass.getpass('Senha do qualimatch_app: ')
if not password:
    raise SystemExit('Senha vazia. Configuração cancelada.')

url = f'postgresql://{quote(user, safe="")}:{quote(password, safe="")}@{host}:{port}/{quote(db, safe="")}'

try:
    import psycopg
    with psycopg.connect(url, connect_timeout=8) as con:
        with con.cursor() as cur:
            cur.execute('SELECT current_database(), current_user, version()')
            info = cur.fetchone()
except Exception as e:
    raise SystemExit(f'Não foi possível conectar ao PostgreSQL: {e}')

ENV.touch(exist_ok=True)
set_key(str(ENV), 'DATABASE_URL', url, quote_mode='always')
print('\nConexão validada com sucesso.')
print(f'Banco: {info[0]} | usuário: {info[1]}')
print(f'Arquivo criado: {ENV}')
print('A senha ficou somente no arquivo .env local. Não envie esse arquivo ao GitHub.')
