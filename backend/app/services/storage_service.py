# app/services/storage_service.py
import asyncio
import logging
import uuid
import json
from abc import ABC, abstractmethod
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_SIZE = 5 * 1024 * 1024
_PUBLIC_READ_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{{bucket}}/*"],
        }
    ],
}

def make_object_key(filename: str, product_id: int, prefix: str = "products") -> str:
    """
    Ключ вида products/{product_id}/{uuid}.{ext}.

    Иерархия с product_id:
    - проще чистить файлы товара (mc rm -r products/123/)
    - видно принадлежность при отладке
    """
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extension '{ext}' is not allowed")
    return f"{prefix}/{product_id}/{uuid.uuid4().hex}{ext}"


class BaseStorage(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes, size: int, content_type: str) -> None:
        """Загрузка. НЕ возвращает URL — только key передаётся между слоями."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    def get_url(self, key: str) -> str: ...

    @abstractmethod
    def ensure_bucket(self) -> None: ...

    @abstractmethod
    async def get_object_info(self, key: str) -> Optional[Dict[str, Any]]: ...


class MinioStorage(BaseStorage):
    def __init__(
        self,
        client: Minio,
        bucket: str,
        secure: bool = False,
        endpoint: str = "localhost:9000",
        public_endpoint: str | None = None,
    ):
        self._client = client
        self._bucket = bucket
        self._secure = secure
        self._endpoint = endpoint.replace("http://", "").replace("https://", "")
        # ✅ Публичный endpoint для URL наружу
        self._public_endpoint = (
            (public_endpoint or endpoint)
            .replace("http://", "")
            .replace("https://", "")
        )

    def ensure_bucket(self) -> None:
        """
        Идемпотентно: создаёт bucket (если нет) + применяет public-read policy.

        Policy — только s3:GetObject. Без ListBucket — публичные URL не дают
        анонимного списка файлов.
        """
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("Bucket '%s' created", self._bucket)

        # ✅ Всегда применяем policy — идемпотентно
        self._set_public_read_policy()

    def _set_public_read_policy(self) -> None:
        """Применяет public-read policy на bucket. Идемпотентно."""
        policy = json.dumps(_PUBLIC_READ_POLICY).replace("{bucket}", self._bucket)
        try:
            self._client.set_bucket_policy(self._bucket, policy)
            logger.info("Public-read policy applied to '%s'", self._bucket)
        except S3Error as e:
            # Не падаем — policy может быть уже применена
            logger.warning(
                "Failed to set policy on '%s': %s. "
                "Проверьте права сервисного пользователя.",
                self._bucket, e,
            )
            raise



    async def upload(
        self,
        key: str,
        data: bytes,
        size: int,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Загрузка без возврата URL — URL склеивается через get_url(key)."""
        if size > MAX_SIZE:
            raise ValueError(f"File size {size} exceeds maximum {MAX_SIZE}")

        data_stream = BytesIO(data)
        await asyncio.to_thread(
            self._client.put_object,
            self._bucket,
            key,
            data_stream,
            size,
            content_type=content_type,
        )

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._client.remove_object, self._bucket, key)
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.info("Object %s already deleted or doesn't exist", key)
                return
            if e.code == "AccessDenied":
                logger.error("Access denied when deleting %s: %s", key, e.message)
                raise
            logger.error("Error deleting object %s: %s - %s", key, e.code, e.message)
            raise
        except Exception:
            logger.exception("Unexpected error deleting %s", key)
            raise

    def get_url(self, key: str) -> str:
        """✅ Публичный URL из MINIO_PUBLIC_ENDPOINT, а не внутреннего."""
        scheme = "https" if self._secure else "http"
        return f"{scheme}://{self._public_endpoint}/{self._bucket}/{key}"

    async def get_object_info(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            stat = await asyncio.to_thread(self._client.stat_object, self._bucket, key)
            return {
                "object_name": stat.object_name,
                "size": stat.size,
                "size_human": self._format_size(stat.size),
                "content_type": stat.content_type,
                "etag": stat.etag,
                "last_modified": (
                    stat.last_modified.isoformat() if stat.last_modified else None
                ),
                "metadata": dict(stat.metadata) if stat.metadata else {},
                "bucket": self._bucket,
            }
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.info("Object %s not found", key)
            else:
                logger.error("Error getting info for %s: %s", key, e)
            return None

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"


def _unwrap_secret(value):
    if hasattr(value, "get_secret_value"):
        return value.get_secret_value()
    return value


@lru_cache
def get_storage() -> MinioStorage:
    settings = get_settings()
    access_key = _unwrap_secret(settings.MINIO_ACCESS_KEY)
    secret_key = _unwrap_secret(settings.MINIO_SECRET_KEY)

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=access_key,
        secret_key=secret_key,
        secure=settings.MINIO_USE_SSL,
    )

    return MinioStorage(
        client,
        settings.MINIO_BUCKET,
        endpoint=settings.MINIO_ENDPOINT,
        public_endpoint=settings.MINIO_PUBLIC_ENDPOINT,   # ✅
        secure=settings.MINIO_USE_SSL,
    )