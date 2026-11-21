import logging
import time
import urllib3
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import requests

# Отключаем предупреждения о небезопасном SSL (для корпоративных прокси)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
    """Клиент для получения данных из API HeadHunter."""

    def __init__(self, base_url: str = "https://api.hh.ru", user_agent: str = "JobAnalytics/1.0 (dev@example.com)"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        self._token: Optional[str] = None

    def set_token(self, token: str):
        """Устанавливает Bearer токен для авторизованных запросов."""
        self._token = token
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        elif "Authorization" in self.session.headers:
            del self.session.headers["Authorization"]

    def fetch_raw_vacancies(self, query: str, per_page: int = 50, max_pages: int = 20) -> FetchResult:
        """Собирает сырые данные вакансий по поисковому запросу с учетом пагинации."""
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
                # verify=False добавлен для обхода корпоративных SSL-прокси
                response = self.session.get(f"{self.base_url}/vacancies", params=params, timeout=15, verify=False)

                if response.status_code in (400, 403):
                    error_msg = f"{response.status_code} Error: Проверьте User-Agent (email должен совпадать с dev.hh.ru) или токен. Детали от HH: {response.text}"
                    logger.error(error_msg)
                    return FetchResult(success=False, query=query, total_found=0, total_fetched=0, raw_vacancies=[],
                                       error_message=error_msg)

                response.raise_for_status()
                data = response.json()

                items = data.get("items", [])
                all_vacancies.extend(items)

                if current_page == 0:
                    total_found = data.get("found", 0)
                    logger.info(f"Всего найдено вакансий: {total_found}")

                pages = data.get("pages", 1)
                if current_page >= pages - 1:
                    break

                current_page += 1
                time.sleep(1.0)  # Rate limiting

            except requests.exceptions.RequestException as e:
                error_msg = f"Ошибка сети при запросе страницы {current_page}: {str(e)}"
                logger.error(error_msg)
                return FetchResult(success=False, query=query, total_found=total_found,
                                   total_fetched=len(all_vacancies), raw_vacancies=all_vacancies,
                                   error_message=error_msg)

        logger.info(f"Успешно собрано {len(all_vacancies)} вакансий из {total_found} найденных.")
        return FetchResult(success=True, query=query, total_found=total_found, total_fetched=len(all_vacancies),
                           raw_vacancies=all_vacancies)

    def get_vacancy_details(self, vacancy_id: str) -> Dict[str, Any]:
        """Получает полные детали одной вакансии по ID."""
        try:
            response = self.session.get(f"{self.base_url}/vacancies/{vacancy_id}", timeout=15, verify=False)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения деталей вакансии {vacancy_id}: {e}")
            return {}

    def get_employer_details(self, employer_id: str) -> Dict[str, Any]:
        """Получает полные детали работодателя (включая отрасли)."""
        try:
            response = self.session.get(f"{self.base_url}/employers/{employer_id}", timeout=15, verify=False)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения деталей работодателя {employer_id}: {e}")
            return {}