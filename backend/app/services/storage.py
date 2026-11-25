import hashlib
import uuid
from pathlib import Path

from app.core.config import settings


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_upload(data: bytes) -> str:
    """Store the bytes under a random name. The user's filename is never part of the path,
    so names like '../../etc/passwd' cannot write outside the storage folder."""
    root = Path(settings.storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid.uuid4().hex
    path.write_bytes(data)
    return str(path)


def delete_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)