from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator


_lock = threading.Lock()
_state_lock = threading.RLock()
_started_at = time.time()
_paused = False
_cancel_requested = False
_state = {
    "active": False,
    "kind": "",
    "label": "",
    "current": "",
    "processed": 0,
    "total": 0,
    "started_at": None,
    "finished_at": None,
    "last_status": "PRONTO",
    "last_message": "",
}


class JobBusyError(RuntimeError):
    pass


class JobCancelled(RuntimeError):
    pass


def snapshot() -> dict:
    with _state_lock:
        result = dict(_state)
        result["paused"] = _paused
        result["cancel_requested"] = _cancel_requested
        result["uptime_seconds"] = max(0, int(time.time() - _started_at))
        total = int(result.get("total") or 0)
        processed = int(result.get("processed") or 0)
        result["progress_pct"] = round(min(100, processed * 100 / total), 1) if total else 0
        return result


def set_paused(value: bool) -> dict:
    global _paused
    with _state_lock:
        _paused = bool(value)
    return snapshot()


def is_paused() -> bool:
    with _state_lock:
        return _paused


def is_busy() -> bool:
    with _state_lock:
        return bool(_state["active"])


def request_cancel() -> dict:
    global _cancel_requested
    with _state_lock:
        if _state["active"]:
            _cancel_requested = True
    return snapshot()


def check_cancelled() -> None:
    with _state_lock:
        if _cancel_requested:
            raise JobCancelled("Operação cancelada pelo administrador.")


def update(*, processed: int | None = None, total: int | None = None, current: str | None = None) -> None:
    with _state_lock:
        if processed is not None:
            _state["processed"] = max(0, int(processed))
        if total is not None:
            _state["total"] = max(0, int(total))
        if current is not None:
            _state["current"] = str(current)


@contextmanager
def job(kind: str, label: str, total: int = 0) -> Iterator[None]:
    global _cancel_requested
    if not _lock.acquire(blocking=False):
        raise JobBusyError("Já existe uma sincronização ou manutenção em andamento.")
    with _state_lock:
        _cancel_requested = False
        _state.update({
            "active": True,
            "kind": kind,
            "label": label,
            "current": "Preparando...",
            "processed": 0,
            "total": max(0, int(total)),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "last_status": "EM_ANDAMENTO",
            "last_message": "",
        })
    try:
        yield
    except JobCancelled as exc:
        with _state_lock:
            _state["last_status"] = "CANCELADO"
            _state["last_message"] = str(exc)
        raise
    except Exception as exc:
        with _state_lock:
            _state["last_status"] = "ERRO"
            _state["last_message"] = str(exc)
        raise
    else:
        with _state_lock:
            _state["last_status"] = "CONCLUIDO"
            _state["last_message"] = "Operação concluída."
            if _state["total"]:
                _state["processed"] = _state["total"]
    finally:
        with _state_lock:
            _state["active"] = False
            _state["current"] = ""
            _state["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _cancel_requested = False
        _lock.release()
