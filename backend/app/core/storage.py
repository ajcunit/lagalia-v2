"""Emmagatzematge d'objectes: backend intercanviable per configuració.

Resol B-003: la tria MinIO/S3 vs disc és STORAGE_BACKEND, no codi.
boto3 és síncron: les crides van a un thread per no bloquejar el loop.
"""

import asyncio
import re
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(value: str, max_length: int = 80) -> str:
    cleaned = _SAFE_RE.sub("-", value).strip("-")
    return cleaned[:max_length] or "document"


class Storage(Protocol):
    async def put(self, key: str, content: bytes, content_type: str) -> None: ...

    async def exists(self, key: str) -> bool: ...


class FilesystemStorage:
    def __init__(self, base_path: str) -> None:
        self._base = Path(base_path)

    def _path(self, key: str) -> Path:
        path = (self._base / key).resolve()
        if not path.is_relative_to(self._base.resolve()):
            raise ValueError(f"Clau d'emmagatzematge fora de la base: {key!r}")
        return path

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).exists)


class S3Storage:
    def __init__(self) -> None:
        import boto3

        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        )
        self._bucket = settings.s3_bucket

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )

    async def exists(self, key: str) -> bool:
        def _head() -> bool:
            try:
                self._client.head_object(Bucket=self._bucket, Key=key)
            except Exception:
                return False
            return True

        return await asyncio.to_thread(_head)


def get_storage() -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage()
    return FilesystemStorage(settings.storage_local_path)
