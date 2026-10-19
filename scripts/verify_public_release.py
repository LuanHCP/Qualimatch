"""Falha se a cópia pública contiver artefatos ou identificadores locais."""

from __future__ import annotations

import re
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git", ".venv", "node_modules", "data", "uploads", "dist", ".next",
    ".vinext", ".wrangler", "__pycache__", ".pytest_cache", ".test-tmp",
}
FORBIDDEN_FILES = {".env", ".env.local", "qualimatch.db", "sessions.json", "qualimatch-sso.key"}
PATTERNS = {
    "caminho pessoal do Windows": re.compile(r"[A-Za-z]:\\Users\\", re.I),
    "identificador da instalação original": re.compile(r"67-103761|luan\.carvalho@motiva\.com\.br", re.I),
    "senha em URL PostgreSQL": re.compile(r"postgres(?:ql)?://[^\s:/]+:[^\s/@]+@", re.I),
}
TEXT_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".html", ".css", ".md",
    ".txt", ".sql", ".json", ".toml", ".yml", ".yaml", ".bat", ".ps1",
    ".example", ".gitignore",
}


def main() -> int:
    problems: list[str] = []
    paths: list[Path] = []
    for current, directories, files in os.walk(ROOT):
        directories[:] = [name for name in directories if name not in SKIP_DIRS]
        paths.extend(Path(current) / name for name in files)
    for path in paths:
        if path.resolve() == Path(__file__).resolve():
            continue
        relative = path.relative_to(ROOT)
        if path.name in FORBIDDEN_FILES:
            problems.append(f"arquivo local proibido: {relative}")
            continue
        if not path.is_file() or (path.suffix.lower() not in TEXT_SUFFIXES and not path.name.startswith(".env")):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in PATTERNS.items():
            match = pattern.search(content)
            dynamic_or_example = (
                label == "senha em URL PostgreSQL"
                and ("SUA_SENHA" in match.group(0) or any(ch in match.group(0) for ch in "%${"))
            ) if match else False
            if match and not dynamic_or_example:
                problems.append(f"{label}: {relative}")
    if problems:
        print("Publicação bloqueada:")
        for problem in sorted(set(problems)):
            print(f" - {problem}")
        return 1
    print("OK: nenhum banco, segredo, sessão ou caminho pessoal foi encontrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
