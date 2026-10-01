# scripts/upload_test.py
"""
Ручной smoke-тест: загрузка фото в MinIO через storage_service.

Запуск:
    cd ~/ShopFlow/backend
    uv run python scripts/upload_test.py /path/to/photo.jpg

Что делает:
    1. Читает файл с диска
    2. Проверяет, что bucket существует (ensure_bucket)
    3. Загружает файл в MinIO
    4. Возвращает публичный URL
    5. Проверяет, что объект доступен через get_object_info
"""
import asyncio
import sys
from pathlib import Path

from app.services.storage_service import get_storage, make_object_key


async def main():
    # 1. Проверяем аргументы
    if len(sys.argv) < 2:
        print("Использование: uv run python scripts/upload_test.py <путь_к_файлу>")
        print("Пример:        uv run python scripts/upload_test.py ~/Pictures/photo.jpg")
        sys.exit(1)

    local_path = Path(sys.argv[1]).expanduser().resolve()

    if not local_path.exists():
        print(f"❌ Файл не найден: {local_path}")
        sys.exit(1)

    if not local_path.is_file():
        print(f"❌ Не файл: {local_path}")
        sys.exit(1)

    print(f"📁 Локальный файл: {local_path}")
    print(f"📦 Размер:        {local_path.stat().st_size} байт")

    # 2. Получаем storage (синглтон через lru_cache)
    storage = get_storage()
    print(f"🗂  Bucket:        {storage._bucket}")
    print(f"🔗 Endpoint:      {storage._endpoint}")

    # 3. Убеждаемся, что bucket существует
    print("\n🔧 ensure_bucket()...")
    storage.ensure_bucket()
    print("   ✅ Bucket готов")

    # 4. Генерируем ключ объекта
    object_key = make_object_key(local_path.name)
    print(f"\n🔑 Ключ объекта:   {object_key}")

    # 5. Читаем данные
    data = local_path.read_bytes()
    print(f"📄 Данные:         {len(data)} байт")

    # 6. Определяем content_type
    import mimetypes
    content_type, _ = mimetypes.guess_type(local_path.name)
    content_type = content_type or "application/octet-stream"
    print(f"🎨 Content-Type:   {content_type}")

    # 7. Загружаем
    print("\n⬆️  upload()...")
    try:
        url = await storage.upload(
            key=object_key,
            data=data,
            size=len(data),
            content_type=content_type,
        )
    except ValueError as e:
        print(f"❌ Ошибка валидации: {e}")
        sys.exit(1)

    print(f"   ✅ Загружено")
    print(f"\n🌐 URL объекта:\n   {url}")

    # 8. Проверяем через get_object_info
    print("\n🔍 get_object_info()...")
    info = await storage.get_object_info(object_key)

    if info is None:
        print("   ❌ Не удалось получить информацию")
        sys.exit(1)

    print(f"   ✅ Информация:")
    for k, v in info.items():
        print(f"      {k}: {v}")

    # 9. Итог
    print("\n" + "=" * 60)
    print("✅ Файл успешно загружен в MinIO")
    print("=" * 60)
    print(f"\n📌 Проверить в консоли MinIO:")
    print(f"   http://localhost:9001")
    print(f"   Bucket: {storage._bucket}")
    print(f"   Object: {object_key}")
    print(f"\n📌 Ключ для удаления:")
    print(f"   {object_key}")


if __name__ == "__main__":
    asyncio.run(main())