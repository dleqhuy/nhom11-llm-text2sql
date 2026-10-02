import json
import os
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

STORE_PATH = Path(__file__).resolve().parents[1] / "data" / "threads.json"


@contextmanager
def _file_lock(path: Path):
    """Lock a file across server workers on both POSIX and Windows."""
    with path.open("a+b") as lock:
        if os.name == "nt":
            # msvcrt locks one byte starting at the current file position.
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _read(path: Path) -> list[dict[str, str | None]]:
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or any(
        not isinstance(record, dict)
        or not isinstance(record.get("thread_id"), str)
        or not isinstance(record.get("created_at"), str)
        or (record.get("name") is not None and not isinstance(record["name"], str))
        for record in records
    ):
        raise ValueError("Invalid thread store")
    for record in records:
        record.setdefault("name", None)
    return records


def list_threads() -> list[dict[str, str | None]]:
    # Atomic replacement ensures readers always see a complete file.
    return list(reversed(_read(STORE_PATH)))


def save_thread(thread_id: str, name: str | None = None) -> None:
    path = STORE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # File lock also coordinates separate server workers on this machine.
    with _file_lock(path.with_suffix(".lock")):
        records = _read(path)
        if any(record["thread_id"] == thread_id for record in records):
            return
        records.append(
            {
                "thread_id": thread_id,
                "name": name,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        _write(path, records)


def _write(path: Path, records: list[dict[str, str | None]]) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(records, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def delete_thread(thread_id: str) -> None:
    path = STORE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(path.with_suffix(".lock")):
        records = _read(path)
        _write(path, [record for record in records if record["thread_id"] != thread_id])
