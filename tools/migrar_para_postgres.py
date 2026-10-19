from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from qualimatch.config import DB_PATH, BACKUP_DIR
from qualimatch.database import init_db, connect, backend_name

TABLES = [
    'settings', 'sources', 'sync_log', 'measurements', 'quality_rows', 'quality_snapshots',
    'certificates', 'certificate_files', 'certificate_samples', 'matches', 'kit_rows',
]
ID_TABLES = ['sync_log','measurements','quality_rows','quality_snapshots','certificates','certificate_files','certificate_samples','kit_rows']


def sqlite_rows(con: sqlite3.Connection, table: str):
    con.row_factory = sqlite3.Row
    return [dict(x) for x in con.execute(f'SELECT * FROM {table}').fetchall()]


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [x[1] for x in con.execute(f'PRAGMA table_info({table})').fetchall()]


def pg_count(table: str) -> int:
    c = connect()
    try:
        return int(c.execute(f'SELECT COUNT(*) n FROM {table}').fetchone()['n'])
    finally:
        c.close()


def main():
    if backend_name() != 'postgresql':
        raise SystemExit('DATABASE_URL não está configurada para PostgreSQL. Rode configurar_postgres.bat primeiro.')
    if not DB_PATH.exists():
        raise SystemExit(f'Banco SQLite não encontrado: {DB_PATH}')

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / 'sqlite_antes_migracao.db'
    if not backup.exists():
        import shutil
        shutil.copy2(DB_PATH, backup)
        print(f'[OK] Backup do SQLite: {backup.name}')

    src = sqlite3.connect(str(DB_PATH))
    src.row_factory = sqlite3.Row
    init_db()  # cria estrutura e índices PostgreSQL

    existing = {t: pg_count(t) for t in TABLES}
    meaningful = sum(existing[t] for t in TABLES if t not in {'settings','sources'})
    if meaningful:
        print('\nO PostgreSQL já possui dados do QualiMatch:')
        for t, n in existing.items():
            if n:
                print(f'  {t}: {n}')
        raise SystemExit('\nMigração cancelada para evitar duplicidade. Use um banco qualimatch vazio.')

    # settings/sources padrão criados por init_db podem ser substituídos pelos valores reais do SQLite.
    pg = connect()
    try:
        pg.execute('DELETE FROM sources')
        pg.execute('DELETE FROM settings')
        pg.commit()
    finally:
        pg.close()

    source_counts = {}
    for table in TABLES:
        data = sqlite_rows(src, table)
        source_counts[table] = len(data)
        if not data:
            print(f'[--] {table}: 0')
            continue
        cols = table_columns(src, table)
        placeholders = ','.join('?' for _ in cols)
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
        pg = connect()
        try:
            pg.executemany(sql, [tuple(r.get(c) for c in cols) for r in data])
            pg.commit()
        except Exception:
            pg.rollback()
            raise
        finally:
            pg.close()
        print(f'[OK] {table}: {len(data)} registros')

    # Ajusta sequences/identity para os próximos INSERTs não reutilizarem IDs migrados.
    pg = connect()
    try:
        for table in ID_TABLES:
            pg.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}','id'), COALESCE((SELECT MAX(id) FROM {table}),1), (SELECT COUNT(*)>0 FROM {table}))"
            )
        pg.commit()
    finally:
        pg.close()

    print('\n=== Validação ===')
    ok = True
    for table in TABLES:
        target = pg_count(table)
        expected = source_counts[table]
        status = 'OK' if target == expected else 'ERRO'
        if target != expected:
            ok = False
        print(f'{status:4} {table:22} SQLite={expected:6} PostgreSQL={target:6}')

    # Validação adicional importante para o negócio.
    pg = connect()
    try:
        active = pg.execute("SELECT contractor,COUNT(*) n FROM certificates WHERE is_active=1 GROUP BY contractor ORDER BY contractor").fetchall()
        samples = pg.execute("SELECT COUNT(*) n FROM certificate_samples").fetchone()['n']
    finally:
        pg.close()
    print('\nCertificados ativos:', ', '.join(f"{x['contractor']}={x['n']}" for x in active) or '0')
    print('CPs:', samples)

    if not ok:
        raise SystemExit('\nA validação encontrou divergências. O SQLite original continua intacto e não deve ser apagado.')

    marker = ROOT / 'data' / 'MIGRACAO_POSTGRES_OK.txt'
    marker.write_text(
        'Migração SQLite -> PostgreSQL concluída e validada.\n'
        + '\n'.join(f'{t}: {source_counts[t]}' for t in TABLES),
        encoding='utf-8',
    )
    print('\nMIGRAÇÃO CONCLUÍDA COM SUCESSO.')
    print('Agora execute iniciar.bat. O /api/health deverá mostrar database=postgresql.')


if __name__ == '__main__':
    main()
