from __future__ import annotations

from pathlib import Path
from typing import Protocol


DEFAULT_CHUNK_SIZE = 1024 * 1024


class AsyncUpload(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class UploadTooLarge(ValueError):
    def __init__(self, max_bytes: int):
        self.max_bytes = int(max_bytes)
        super().__init__(f"Arquivo acima do limite de {self.max_bytes // (1024 * 1024)} MB.")


async def read_upload_limited(
    upload: AsyncUpload,
    max_bytes: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> bytes:
    """Read an upload without allowing an unbounded allocation."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLarge(max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


async def save_upload_limited(
    upload: AsyncUpload,
    target: Path,
    max_bytes: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> int:
    """Stream an upload to disk and remove partial output when it exceeds the limit."""
    total = 0
    try:
        with target.open("wb") as handle:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLarge(max_bytes)
                handle.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return total
