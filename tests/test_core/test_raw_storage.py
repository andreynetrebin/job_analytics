import os
import re
import json
import pytest
import responses
from core.storage.raw_storage import LocalRawStorage, YandexDiskStorage


def test_local_raw_storage_creates_file(tmp_path):
    """Тест локального сохранения файла."""
    storage = LocalRawStorage(base_dir=str(tmp_path))
    vacancies = [{"id": "1", "name": "Test Job"}]

    filepath = storage.save(query="Data Engineer", vacancies=vacancies)

    assert os.path.exists(filepath)
    # Теперь пробел заменен на '_', поэтому эта проверка пройдет успешно
    assert "vacancies_Data_Engineer_" in filepath
    assert filepath.endswith(".json")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        assert data == vacancies


@responses.activate
def test_yandex_disk_storage_success():
    """Тест загрузки на Яндекс.Диск с мокированием API через регулярные выражения."""
    token = "mock_yandex_token_123"
    storage = YandexDiskStorage(token=token, remote_dir="/test_dir")
    vacancies = [{"id": "1", "name": "Test Job"}]

    # ✅ ИСПОЛЬЗУЕМ re.compile, чтобы совпадать с ЛЮБЫМ динамическим timestamp в URL
    url_pattern = re.compile(
        r"https://cloud-api\.yandex\.net/v1/disk/resources/upload\?path=/test_dir/vacancies_Test_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.json&overwrite=true"
    )

    # 1. Мок получения ссылки для загрузки
    responses.add(
        responses.GET,
        url_pattern,
        json={"href": "https://uploader.yandex.net/upload_url_mock"},
        status=200
    )

    # 2. Мок самой загрузки файла (PUT запрос).
    # responses автоматически сопоставит этот PUT с предыдущим GET, так как href совпадает
    responses.add(
        responses.PUT,
        "https://uploader.yandex.net/upload_url_mock",
        status=201
    )

    filepath = storage.save(query="Test", vacancies=vacancies)

    assert "/test_dir/vacancies_Test_" in filepath
    assert len(responses.calls) == 2
    assert responses.calls[0].request.method == "GET"
    assert responses.calls[1].request.method == "PUT"
    assert b'"name": "Test Job"' in responses.calls[1].request.body