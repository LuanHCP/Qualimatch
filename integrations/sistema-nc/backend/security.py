"""
Hashing de senha, tokens de sessão e CSRF.

Senhas: bcrypt real (`$2b$`, custo 12). Preferimos o pacote `bcrypt` do
PyPI quando instalado (ambiente com internet normal — ver requirements.txt).
Quando indisponível, usamos `crypt.mksalt(crypt.METHOD_BLOWFISH)` da
biblioteca padrão do Python, que delega para a mesma implementação bcrypt
da libc (libxcrypt) — o hash resultante tem exatamente o mesmo formato
`$2b$<custo>$<salt><hash>` e é 100% compatível/verificável por qualquer
biblioteca bcrypt padrão. `crypt` está descontinuado a partir do Python
3.13; a troca para o pacote `bcrypt` é mecânica (mesmo formato de hash) e
já está preparada por este módulo.

Nunca — em nenhuma hipótese — senhas são armazenadas em texto puro.
"""
import hmac
import hashlib
import secrets

try:
    import bcrypt as _bcrypt_pkg  # type: ignore
    HAVE_BCRYPT_PKG = True
except Exception:
    HAVE_BCRYPT_PKG = False

try:
    import crypt  # stdlib, deprecated a partir do 3.13
    HAVE_CRYPT = True
except Exception:
    HAVE_CRYPT = False

BCRYPT_COST = 12


def hash_password(plain: str) -> str:
    if not plain or len(plain) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    if HAVE_BCRYPT_PKG:
        return _bcrypt_pkg.hashpw(plain.encode("utf-8"), _bcrypt_pkg.gensalt(BCRYPT_COST)).decode("ascii")
    if HAVE_CRYPT:
        # crypt.mksalt espera o número de iterações (2**custo), não o
        # próprio expoente — resulta no mesmo "$2b$<custo>$..." do bcrypt.
        salt = crypt.mksalt(crypt.METHOD_BLOWFISH, rounds=2 ** BCRYPT_COST)
        return crypt.crypt(plain, salt)
    raise RuntimeError("Nenhuma implementação de bcrypt disponível neste ambiente.")


def verify_password(plain: str, stored_hash: str) -> bool:
    if not plain or not stored_hash:
        return False
    try:
        if stored_hash.startswith("$2") and HAVE_BCRYPT_PKG:
            return _bcrypt_pkg.checkpw(plain.encode("utf-8"), stored_hash.encode("ascii"))
        if stored_hash.startswith("$2") and HAVE_CRYPT:
            return hmac.compare_digest(crypt.crypt(plain, stored_hash), stored_hash)
    except Exception:
        return False
    return False


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    if a is None or b is None:
        return False
    return hmac.compare_digest(a, b)
