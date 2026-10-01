"""Тесты MinioStorage и make_object_key."""
import io
import uuid
from unittest.mock import Mock

import pytest
from minio.error import S3Error

from app.services.storage_service import MinioStorage, make_object_key


class TestMinioUpload:
    """Тесты для загрузки файлов."""

    @pytest.fixture
    def mock_client(self):
        client = Mock()
        client.put_object = Mock()
        return client

    @pytest.fixture
    def storage(self, mock_client):
        return MinioStorage(
            mock_client,
            "test-bucket",
            endpoint="localhost:9000",
            public_endpoint="localhost:9000",
        )

    @pytest.mark.asyncio
    async def test_upload_calls_put_object_with_correct_arguments(
        self, storage, mock_client
    ):
        """upload вызывает put_object с правильными аргументами."""
        test_key = "products/1/test-file.jpg"
        test_data = b"Hello, MinIO!"
        test_content_type = "image/jpeg"

        await storage.upload(
            key=test_key,
            data=test_data,
            size=len(test_data),
            content_type=test_content_type,
        )

        mock_client.put_object.assert_called_once()
        call_args = mock_client.put_object.call_args

        assert call_args[0][0] == "test-bucket"
        assert call_args[0][1] == test_key

        data_arg = call_args[0][2]
        assert isinstance(data_arg, io.BytesIO)
        assert data_arg.getvalue() == test_data

        assert call_args[0][3] == len(test_data)
        assert call_args[1]["content_type"] == test_content_type

    @pytest.mark.asyncio
    async def test_upload_returns_none(self, storage, mock_client):
        """✅ upload НЕ возвращает URL — только загружает."""
        mock_client.put_object.return_value = None

        result = await storage.upload(
            key="products/1/file.jpg",
            data=b"data",
            size=4,
            content_type="image/jpeg",
        )

        assert result is None       # ✅ контракт: upload → None

    def test_get_url_uses_public_endpoint(self, mock_client):
        """✅ get_url склеивает публичный URL."""
        storage = MinioStorage(
            mock_client,
            "test-bucket",
            endpoint="minio:9000",           # внутренний
            public_endpoint="cdn.example.com",  # публичный
        )

        url = storage.get_url("products/1/file.jpg")

        assert url == "http://cdn.example.com/test-bucket/products/1/file.jpg"
        assert "minio:9000" not in url

    @pytest.mark.asyncio
    async def test_upload_uses_to_thread(self, storage, mock_client, mocker):
        """upload использует asyncio.to_thread."""
        mock_to_thread = mocker.patch("asyncio.to_thread")
        mock_to_thread.return_value = None

        await storage.upload(
            key="products/1/test.jpg",
            data=b"data",
            size=4,
            content_type="image/jpeg",
        )

        mock_to_thread.assert_called_once()
        args = mock_to_thread.call_args[0]
        assert args[0] == mock_client.put_object
        assert args[1] == "test-bucket"
        assert args[2] == "products/1/test.jpg"


class TestMinioDelete:
    """Тесты для удаления файлов."""

    @pytest.fixture
    def mock_client(self):
        client = Mock()
        client.remove_object = Mock()
        return client

    @pytest.fixture
    def storage(self, mock_client):
        return MinioStorage(mock_client, "test-bucket")

    def _create_s3_error(self, code, message, resource):
        return S3Error(
            code=code,
            message=message,
            resource=resource,
            request_id="req-123",
            host_id="host-456",
            response=Mock(),
        )

    @pytest.mark.asyncio
    async def test_delete_swallows_nosuchkey(self, storage, mock_client):
        """delete глотает NoSuchKey (идемпотентность)."""
        mock_client.remove_object.side_effect = self._create_s3_error(
            "NoSuchKey", "Not found", "test-bucket/nonexistent.jpg"
        )

        await storage.delete("nonexistent.jpg")     # не должно упасть

        mock_client.remove_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_propagates_accessdenied(self, storage, mock_client):
        """delete пробрасывает AccessDenied."""
        mock_client.remove_object.side_effect = self._create_s3_error(
            "AccessDenied", "Access Denied", "test-bucket/file.jpg"
        )

        with pytest.raises(S3Error) as exc_info:
            await storage.delete("file.jpg")

        assert exc_info.value.code == "AccessDenied"


class TestMakeObjectKey:
    """Тесты для make_object_key с product_id."""

    def test_make_object_key_with_product_id(self):
        """✅ Ключ вида products/{product_id}/{uuid}.{ext}."""
        key = make_object_key("photo.jpg", product_id=42)

        parts = key.split("/")
        assert len(parts) == 3
        assert parts[0] == "products"
        assert parts[1] == "42"                 # ✅ product_id
        assert parts[2].endswith(".jpg")

        # UUID в имени файла
        uuid_str = parts[2].removesuffix(".jpg")
        uuid.UUID(uuid_str)                     # не должно упасть

    def test_make_object_key_unique(self):
        """Два вызова → разные ключи."""
        key1 = make_object_key("photo.jpg", product_id=1)
        key2 = make_object_key("photo.jpg", product_id=1)
        assert key1 != key2

    def test_make_object_key_normalizes_extension(self):
        """Расширение в нижнем регистре."""
        for filename, expected in [
            ("photo.JPG", ".jpg"),
            ("photo.Jpeg", ".jpeg"),
            ("photo.PNG", ".png"),
        ]:
            key = make_object_key(filename, product_id=1)
            assert key.endswith(expected)

    def test_make_object_key_rejects_exe(self):
        """Опасные расширения отклоняются."""
        with pytest.raises(ValueError, match="not allowed"):
            make_object_key("malware.exe", product_id=1)

        for bad in ["script.sh", "app.bat", "archive.zip", "doc.pdf"]:
            with pytest.raises(ValueError):
                make_object_key(bad, product_id=1)

    def test_make_object_key_accepts_allowed(self):
        """Разрешённые расширения проходят."""
        for allowed in ["image.jpg", "photo.png", "anim.gif", "pic.webp"]:
            key = make_object_key(allowed, product_id=1)
            assert key.startswith("products/1/")