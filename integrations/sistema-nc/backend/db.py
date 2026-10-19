"""
Camada de acesso a dados (PostgreSQL).

Este módulo tenta usar o driver real `psycopg` (psycopg3) quando ele está
instalado — é o caminho esperado em um ambiente com acesso normal à
internet (`pip install -r requirements.txt`, ver Dockerfile). Quando o
driver não está disponível, cai para um adaptador que fala com o Postgres
através do utilitário de linha de comando `psql`.

Por quê existe o fallback via `psql`
-------------------------------------
Este backend foi desenvolvido e validado dentro de um ambiente sandbox cuja
política de rede bloqueia explicitamente o acesso a registry.npmjs.org,
pypi.org e archive.ubuntu.com (respostas HTTP 403 confirmadas — não é uma
falha transitória). Isso torna impossível instalar `psycopg`/`psycopg2`
nesse ambiente específico. Para ainda assim implementar e *validar de
verdade* o sistema (migrations, autenticação, importação/exportação,
testes) contra um PostgreSQL real, foi escrito este adaptador que usa o
cliente `psql` (já presente no sistema) como transporte, com um esquema de
parametrização seguro (ver `lit()` abaixo — escita por dollar-quoting com
tag aleatória, o que impede injeção de SQL).

Em produção, com acesso normal à internet, `psycopg[binary]` estará
instalado (ver requirements.txt) e será usado automaticamente — o
adaptador via `psql` é só um substituto funcionalmente equivalente para
este ambiente restrito. Nenhuma rota do sistema depende de qual dos dois
caminhos está ativo.
"""
import os
import json
import secrets
import subprocess
import decimal
import datetime
from urllib.parse import quote

try:
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore
    HAVE_PSYCOPG = True
except Exception:
    HAVE_PSYCOPG = False


class DBError(RuntimeError):
    pass


def _dsn_parts():
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
        "dbname": os.environ.get("PGDATABASE", "nc_sistema"),
        "user": os.environ.get("PGUSER", "nc_app"),
        "password": os.environ.get("PGPASSWORD", ""),
    }


def dsn_string():
    p = _dsn_parts()
    user = quote(str(p["user"]), safe="")
    password = quote(str(p["password"]), safe="")
    dbname = quote(str(p["dbname"]), safe="")
    return f"postgresql://{user}:{password}@{p['host']}:{p['port']}/{dbname}"


def lit(value):
    """Formata um valor Python como literal SQL seguro (sem depender de
    parâmetros preparados, que o adaptador psql não oferece).

    - str  -> dollar-quoted com tag aleatória garantidamente ausente do texto
    - bool -> TRUE/FALSE
    - None -> NULL
    - int/float/Decimal -> literal numérico (validado pelo próprio tipo Python)
    - datetime/date -> string ISO, dollar-quoted
    - list/tuple -> ARRAY[...] de literais
    - dict -> jsonb dollar-quoted
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int,)):
        return str(int(value))
    if isinstance(value, (float, decimal.Decimal)):
        return repr(float(value))
    if isinstance(value, (datetime.datetime, datetime.date)):
        return _dollar_quote(value.isoformat())
    if isinstance(value, dict):
        return _dollar_quote(json.dumps(value, ensure_ascii=False)) + "::jsonb"
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return "'{}'"
        return "ARRAY[" + ",".join(lit(v) for v in value) + "]"
    # fallback: string
    return _dollar_quote(str(value))


def json_lit(value):
    """Sempre serializa como jsonb (mesmo listas simples)."""
    return _dollar_quote(json.dumps(value, ensure_ascii=False)) + "::jsonb"


def _dollar_quote(text):
    tag = "q" + secrets.token_hex(6)
    while tag in text:
        tag = "q" + secrets.token_hex(6)
    return f"${tag}${text}${tag}$"


class PsqlAdapter:
    def __init__(self):
        self.dsn = dsn_string()

    def _run(self, sql, timeout=60):
        # SQL é enviado via stdin (não como argumento -c) para não esbarrar
        # no limite de tamanho da linha de comando do sistema operacional
        # em payloads grandes (ex.: prévia de importação com centenas de
        # linhas de planilha serializadas em JSON).
        result = subprocess.run(
            ["psql", self.dsn, "-X", "-q", "-t", "-A",
             "-v", "ON_ERROR_STOP=1", "-f", "-"],
            input=sql, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            raise DBError(result.stderr.strip() or "erro desconhecido no psql")
        return result.stdout

    def fetchall(self, sql):
        inner = sql.strip()
        if inner.endswith(";"):
            inner = inner[:-1]
        first_word = inner.lstrip().split(None, 1)[0].upper() if inner.strip() else ""
        if first_word in ("INSERT", "UPDATE", "DELETE"):
            # DML com RETURNING não pode ir em "FROM (...)", precisa de CTE.
            wrapped = f"WITH t AS ({inner}) SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM t;"
        else:
            wrapped = f"SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM ({inner}) t;"
        out = self._run(wrapped).strip()
        if not out or out == "\\N":
            return []
        return json.loads(out)

    def fetchone(self, sql):
        rows = self.fetchall(sql)
        return rows[0] if rows else None

    def execute(self, sql):
        """DDL/DML sem necessidade de retorno."""
        self._run(sql)

    def execute_script(self, sql_statements, single_transaction=True):
        """Executa uma lista de statements SQL em uma única transação."""
        script = "\n".join(s.rstrip().rstrip(";") + ";" for s in sql_statements)
        args = ["psql", self.dsn, "-X", "-q", "-v", "ON_ERROR_STOP=1"]
        if single_transaction:
            args.append("--single-transaction")
        result = subprocess.run(args + ["-f", "/dev/stdin"], input=script,
                                 capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise DBError(result.stderr.strip() or "erro desconhecido no psql (script)")
        return result.stdout


class PsycopgAdapter:
    def __init__(self):
        self._conn_kwargs = _dsn_parts()

    def _connect(self):
        p = self._conn_kwargs
        return psycopg.connect(
            host=p["host"], port=p["port"], dbname=p["dbname"],
            user=p["user"], password=p["password"], row_factory=dict_row,
        )

    def fetchall(self, sql):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]

    def fetchone(self, sql):
        rows = self.fetchall(sql)
        return rows[0] if rows else None

    def execute(self, sql):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()

    def execute_script(self, sql_statements, single_transaction=True):
        with self._connect() as conn:
            with conn.cursor() as cur:
                for s in sql_statements:
                    cur.execute(s)
            conn.commit()


_adapter = None


def get_adapter():
    global _adapter
    if _adapter is None:
        _adapter = PsycopgAdapter() if HAVE_PSYCOPG else PsqlAdapter()
    return _adapter


def fetchall(sql):
    return get_adapter().fetchall(sql)


def fetchone(sql):
    return get_adapter().fetchone(sql)


def execute(sql):
    return get_adapter().execute(sql)


def execute_script(statements, single_transaction=True):
    return get_adapter().execute_script(statements, single_transaction=single_transaction)
