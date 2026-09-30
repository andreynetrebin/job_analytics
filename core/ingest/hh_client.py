import logging
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Результат сбора данных из API."""
    success: bool
    query: str
    total_found: int
    total_fetched: int
    raw_vacancies: List[Dict[str, Any]]
    error_message: Optional[str] = None


class HHClient:
    """Клиент для получения сырых данных из API HeadHunter."""

    def __init__(self, base_url: str = "https://api.hh.ru", user_agent: str = "JobAnalytics/1.0 (andrew89s@mail.ru)"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        # Токен будет обновляться динамически, если нужно
        self._token: Optional[str] = None

    def set_token(self, token: str):
        """Устанавливает Bearer токен для авторизованных запросов."""
        self._token = token
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        elif "Authorization" in self.session.headers:
            del self.session.headers["Authorization"]

    def fetch_raw_vacancies(self, query: str, per_page: int = 20, max_pages: int = 20) -> FetchResult:
        """
        Собирает сырые данные вакансий по поисковому запросу с учетом пагинации.

        :param query: Поисковый запрос (например, "Data Engineer")
        :param per_page: Количество элементов на странице (макс. 100 для HH API)
        :param max_pages: Максимальное количество страниц для сбора (защита от бесконечного цикла)
        :return: Объект FetchResult с сырыми JSON-данными
        """
        logger.info(f"Начинаем сбор сырых данных для запроса: '{query}'")

        all_vacancies = []
        current_page = 0
        total_found = 0

        while current_page < max_pages:
            params = {
                "text": query,
                "per_page": per_page,
                "page": current_page
            }

            try:
                response = self.session.get(f"{self.base_url}/vacancies", params=params, timeout=15)

                # Обработка 403 Forbidden (неверный User-Agent или блокировка)
                if response.status_code == 403:
                    error_msg = f"403 Forbidden: Проверьте User-Agent или токены. Ответ: {response.text[:200]}"
                    logger.error(error_msg)
                    return FetchResult(
                        success=False,
                        query=query,
                        total_found=0,
                        total_fetched=0,
                        raw_vacancies=[],
                        error_message=error_msg
                    )

                response.raise_for_status()
                data = response.json()

                items = data.get("items", [])
                all_vacancies.extend(items)

                if current_page == 0:
                    total_found = data.get("found", 0)
                    logger.info(f"Всего найдено вакансий: {total_found}")

                # Проверяем, есть ли следующая страница
                pages = data.get("pages", 1)
                if current_page >= pages - 1:
                    break

                current_page += 1

                # Уважительная задержка, чтобы не получить бан по IP (HH рекомендует ~1-2 сек)
                time.sleep(1.5)

            except requests.exceptions.RequestException as e:
                error_msg = f"Ошибка сети при запросе страницы {current_page}: {str(e)}"
                logger.error(error_msg)
                return FetchResult(
                    success=False,
                    query=query,
                    total_found=total_found,
                    total_fetched=len(all_vacancies),
                    raw_vacancies=all_vacancies,
                    error_message=error_msg
                )

        logger.info(f"Успешно собрано {len(all_vacancies)} вакансий из {total_found} найденных.")
        return FetchResult(
            success=True,
            query=query,
            total_found=total_found,
            total_fetched=len(all_vacancies),
            raw_vacancies=all_vacancies
        )