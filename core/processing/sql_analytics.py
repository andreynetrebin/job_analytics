import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models import (
    Vacancy, Employer, KeySkill, KeySkillHistory,
    SalaryHistory, ExperienceLevel
)

logger = logging.getLogger(__name__)


class JobAnalyticsSQL:
    """Класс для получения агрегированных данных из БД для LLM-анализа."""

    def __init__(self, session: Session):
        self.session = session

    def get_top_skills(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Возвращает топ навыков по частоте упоминания в активных вакансиях."""
        query = self.session.query(
            KeySkill.name,
            func.count(KeySkillHistory.key_skill_id).label('count')
        ).join(
            KeySkillHistory, KeySkill.id == KeySkillHistory.key_skill_id
        ).join(
            Vacancy, Vacancy.id == KeySkillHistory.vacancy_id
        ).filter(
            Vacancy.status == 'Активный',
            KeySkillHistory.is_active == True
        ).group_by(
            KeySkill.name
        ).order_by(
            func.count(KeySkillHistory.key_skill_id).desc()
        ).limit(limit).all()

        return [{"skill": row.name, "count": row.count} for row in query]

    def get_salary_by_experience(self) -> List[Dict[str, Any]]:
        """Возвращает среднюю зарплату (от) по уровням опыта для активных вакансий."""
        query = self.session.query(
            ExperienceLevel.name,
            func.avg(SalaryHistory.salary_from).label('avg_salary_from')
        ).join(
            Vacancy, Vacancy.experience_id == ExperienceLevel.id
        ).join(
            SalaryHistory, SalaryHistory.vacancy_id == Vacancy.id
        ).filter(
            Vacancy.status == 'Активный',
            SalaryHistory.is_active == True,
            SalaryHistory.salary_from.isnot(None)
        ).group_by(
            ExperienceLevel.name
        ).all()

        return [
            {"experience": row.name, "avg_salary": round(row.avg_salary_from, 0) if row.avg_salary_from else 0}
            for row in query
        ]

    def get_market_summary(self, query_text: str) -> Dict[str, Any]:
        """Возвращает общую сводку по рынку для переданного поискового запроса."""
        # Упрощенный подсчет: считаем все активные вакансии (в реальном проекте можно фильтровать по search_queries)
        total_active = self.session.query(func.count(Vacancy.id)).filter(Vacancy.status == 'Активный').scalar()

        top_employers = self.session.query(
            Employer.name,
            func.count(Vacancy.id).label('count')
        ).join(
            Vacancy, Vacancy.employer_id == Employer.id
        ).filter(
            Vacancy.status == 'Активный'
        ).group_by(
            Employer.id, Employer.name
        ).order_by(
            func.count(Vacancy.id).desc()
        ).limit(3).all()

        return {
            "total_active_vacancies": total_active,
            "top_employers": [{"name": row.name, "vacancies": row.count} for row in top_employers],
            "search_context": query_text
        }

    def get_full_context_for_llm(self, query_text: str = "Data Engineer") -> str:
        """Собирает весь контекст в один читаемый текстовый блок для промпта LLM."""
        logger.info("📊 Сбор SQL-контекста для LLM...")

        summary = self.get_market_summary(query_text)
        skills = self.get_top_skills(limit=5)
        salaries = self.get_salary_by_experience()

        context = f"АНАЛИЗ РЫНКА ТРУДА ПО ЗАПРОСУ: '{summary['search_context']}'\n"
        context += f"Всего активных вакансий в базе: {summary['total_active_vacancies']}\n\n"

        context += "ТОП-5 КЛЮЧЕВЫХ НАВЫКОВ:\n"
        for s in skills:
            context += f"- {s['skill']}: упоминается в {s['count']} вакансиях\n"
        context += "\n"

        context += "СРЕДНЯЯ ЗАРПЛАТА (ОТ) ПО УРОВНЯМ ОПЫТА:\n"
        for sal in salaries:
            context += f"- {sal['experience']}: {int(sal['avg_salary']):,} руб.\n".replace(',', ' ')
        context += "\n"

        context += "ТОП-3 РАБОТОДАТЕЛЯ ПО КОЛИЧЕСТВУ ВАКАНСИЙ:\n"
        for emp in summary['top_employers']:
            context += f"- {emp['name']} ({emp['vacancies']} вакансий)\n"

        return context