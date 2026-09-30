import json
import unittest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch
from job_analytics import process_vacancy, revive_vacancy, update_salary_history, update_key_skills
from database.models import (
    Base, Vacancy, SalaryHistory, KeySkill, KeySkillHistory, VacancyStatusHistory, SearchQuery
)
class TestVacancyProcessing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Настройка базы данных для тестирования (in-memory SQLite)
        cls.engine = create_engine('sqlite:///:memory:')
        cls.Session = sessionmaker(bind=cls.engine)
        cls.session = cls.Session()

        # ✅ Создаем все таблицы из правильного места
        Base.metadata.create_all(cls.engine)

        # Загружаем данные из JSON файлов (убедитесь, что папка data/ существует,
        # или закомментируйте эти строки, если файлов пока нет, и используйте словари напрямую)
        try:
            with open('tests/data/vacancy_data.json', 'r', encoding='utf-8') as f:
                cls.new_vacancy_data = json.load(f)
            with open('tests/data/existing_vacancy_data.json', 'r', encoding='utf-8') as f:
                cls.existing_vacancy_data = json.load(f)

        except FileNotFoundError:
            cls.new_vacancy_data = {
                "id": "999999", "name": "Test Vacancy", "published_at": "2026-09-25T10:00:00+03:00",
                "archived": False, "salary_range": {"from": 100000, "to": 150000, "currency": "RUB"},
                "experience": {"id": "1", "name": "Опыт"}, "professional_roles": [{"id": "1", "name": "Роль"}],
                "employment_form": {"id": "1", "name": "Форма"}, "working_hours": [{"id": "1", "name": "Часы"}],
                "key_skills": [{"name": "Python"}]
            }
            cls.existing_vacancy_data = cls.new_vacancy_data.copy()

            pub_date_str = cls.existing_vacancy_data.get('published_at', '2026-09-25T10:00:00+03:00')
            try:
                published_date_obj = datetime.fromisoformat(pub_date_str)
            except ValueError:
                published_date_obj = datetime.now()  # Fallback

        # ✅ ВАЖНО: Передаем именно published_date_obj (объект datetime), а не строку!
        cls.existing_vacancy = Vacancy(
            external_id=cls.existing_vacancy_data.get('id', '999999'),
            title=cls.existing_vacancy_data.get('name', 'Test Vacancy'),
            status="Архивный",
            published_date=published_date_obj  # <--- ИСПРАВЛЕНИЕ ЗДЕСЬ
        )
        cls.session.add(cls.existing_vacancy)
        cls.session.commit()


    @patch('job_analytics.hh_api.get')
    def test_process_vacancy_revive(self, mock_hh_get):
        """Тест на возобновление архивной вакансии."""
        # Настраиваем мок так, чтобы он возвращал данные активной вакансии
        mock_hh_get.return_value = {
            "id": "999999",
            "name": "Test Vacancy",
            "archived": False,
            "experience": {"id": "1", "name": "Опыт"},
            "professional_roles": [{"id": "1", "name": "Роль"}],
            "employment_form": {"id": "1", "name": "Форма"},
            "working_hours": [{"id": "1", "name": "Часы"}],
            "key_skills": [{"name": "Python"}],
            "published_at": "2026-09-25T10:00:00+03:00",
            "initial_created_at": "2026-09-25T09:00:00+03:00",
            "salary_range": {"from": 100000, "to": 150000, "currency": "RUB"}
        }

        # Вызываем функцию (query=None, как в оригинальном тесте)
        process_vacancy(self.new_vacancy_data, self.session, query=None)

        # Проверяем, что статус вакансии обновился
        revived_vacancy = self.session.query(Vacancy).filter_by(external_id="999999").first()
        self.assertIsNotNone(revived_vacancy)
        self.assertEqual(revived_vacancy.status, "Активный")

        # Проверяем, что запись в VacancyStatusHistory была создана
        status_history = self.session.query(VacancyStatusHistory).filter_by(vacancy_id=revived_vacancy.id).first()
        self.assertIsNotNone(status_history)
        self.assertEqual(status_history.prev_status, "Архивный")
        self.assertEqual(status_history.cur_status, "Активный")

    def test_update_salary_history(self):
        """Тест на обновление истории зарплаты."""
        update_salary_history(self.existing_vacancy, self.new_vacancy_data, self.session)

        # Проверяем, что новая запись в SalaryHistory была создана
        salary_history = self.session.query(SalaryHistory).filter_by(vacancy_id=self.existing_vacancy.id, is_active=True).first()
        self.assertIsNotNone(salary_history)
        self.assertEqual(salary_history.salary_from, self.new_vacancy_data['salary_range']['from'])
        self.assertEqual(salary_history.salary_to, self.new_vacancy_data['salary_range']['to'])

    def test_update_key_skills(self):
        """Тест на обновление ключевых навыков."""
        update_key_skills(self.existing_vacancy, self.new_vacancy_data, self.session)

        # Проверяем, что новые ключевые навыки были добавлены
        key_skills = self.session.query(KeySkill).all()
        self.assertGreater(len(key_skills), 0)

        # Проверяем, что запись в KeySkillHistory была создана
        key_skill_history = self.session.query(KeySkillHistory).filter_by(vacancy_id=self.existing_vacancy.id).all()
        self.assertGreater(len(key_skill_history), 0)

if __name__ == '__main__':
    unittest.main()
