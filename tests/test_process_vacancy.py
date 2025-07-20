import json
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import process_vacancy, revive_vacancy, update_salary_history, update_key_skills
from models import Vacancy, SalaryHistory, KeySkill, KeySkillHistory, VacancyStatusHistory

class TestProcessVacancy(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Настройка базы данных для тестирования
        cls.engine = create_engine('sqlite:///:memory:')  # Используем in-memory SQLite для тестов
        cls.Session = sessionmaker(bind=cls.engine)
        cls.session = cls.Session()

        # Создаем все таблицы
        from models import Base
        Base.metadata.create_all(cls.engine)

        # Загружаем данные из JSON файлов
        with open('data/vacancy_data.json') as f:
            cls.new_vacancy_data = json.load(f)

        with open('data/existing_vacancy_data.json') as f:
            cls.existing_vacancy_data = json.load(f)

        # Создаем существующую вакансию в базе данных
        cls.existing_vacancy = Vacancy(
            external_id=cls.existing_vacancy_data['id'],
            title=cls.existing_vacancy_data['name'],
            status="Архивный",
            published_date=cls.existing_vacancy_data['published_at']
        )
        cls.session.add(cls.existing_vacancy)
        cls.session.commit()

    def test_process_vacancy_revive(self):
        """Тест на возобновление архивной вакансии."""
        process_vacancy(self.new_vacancy_data, self.session, query=None)

        # Проверяем, что статус вакансии обновился
        revived_vacancy = self.session.query(Vacancy).filter_by(external_id=self.new_vacancy_data['id']).first()
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
