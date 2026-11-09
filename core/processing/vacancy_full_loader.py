import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database.models import (
    Vacancy, Employer, Industry, KeySkill, ProfessionalRole,
    ExperienceLevel, EmploymentForm, WorkingHours, WorkSchedule, WorkFormat,
    SalaryHistory, KeySkillHistory, VacancyStatusHistory, SearchQuery,
    employer_industries, vacancy_work_schedules, vacancy_work_formats, search_query_vacancies
)
from database.models import moscow_tz

logger = logging.getLogger(__name__)


def parse_hh_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str: return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00')).replace(tzinfo=None)
    except:
        return None


def get_or_create(session, model, **kwargs):
    instance = session.query(model).filter_by(**kwargs).first()
    if instance: return instance
    instance = model(**kwargs)
    session.add(instance)
    session.flush()
    return instance


def link_employer_industries(session, employer, industries_data):
    if not industries_data: return
    for ind in industries_data:
        industry = get_or_create(session, Industry, id_external=str(ind['id']), name=ind.get('name'))
        exists = session.query(employer_industries).filter_by(employer_id=employer.id, industry_id=industry.id).first()
        if not exists:
            session.execute(employer_industries.insert().values(employer_id=employer.id, industry_id=industry.id))


def process_full_vacancy(session: Session, vacancy_json: Dict, employer_json: Optional[Dict],
                         search_query_id: Optional[int] = None):
    """Полная обработка одной вакансии со всеми связями (как в job_analytics.py)"""
    try:
        ext_id = str(vacancy_json['id'])

        # 1. Работодатель
        emp_data = vacancy_json.get('employer', {})
        employer = get_or_create(session, Employer, id_external=str(emp_data.get('id')),
                                 name=emp_data.get('name', 'Unknown'))

        # Обновляем детали работодателя, если пришли (из employer_json)
        if employer_json:
            employer.area = employer_json.get('area', {}).get('name')
            employer.accredited_it_employer = employer_json.get('accredited_it_employer', False)
            employer.open_vacancies = employer_json.get('open_vacancies')
            # Отрасли
            if 'industries' in employer_json:
                link_employer_industries(session, employer, employer_json['industries'])

        # 2. Справочники
        exp_data = vacancy_json.get('experience')
        experience = get_or_create(session, ExperienceLevel, id_external=str(exp_data['id']),
                                   name=exp_data['name']) if exp_data else None

        roles = vacancy_json.get('professional_roles', [])
        role = get_or_create(session, ProfessionalRole, id_external=str(roles[0]['id']),
                             name=roles[0]['name']) if roles else None

        form = vacancy_json.get('employment_form')
        emp_form = get_or_create(session, EmploymentForm, id_external=str(form['id']),
                                 name=form['name']) if form else None

        hours = vacancy_json.get('working_hours', [])
        work_hours = get_or_create(session, WorkingHours, id_external=str(hours[0]['id']),
                                   name=hours[0]['name']) if hours else None

        # 3. Вакансия (Upsert)
        vacancy = session.query(Vacancy).filter_by(external_id=ext_id).first()

        is_archived = vacancy_json.get('archived', False)
        common_data = {
            'title': vacancy_json.get('name'),
            'employer_id': employer.id,
            'area': vacancy_json.get('area', {}).get('name'),
            'experience_id': experience.id if experience else None,
            'professional_role_id': role.id if role else None,
            'employment_form_id': emp_form.id if emp_form else None,
            'working_hours_id': work_hours.id if work_hours else None,
            'status': 'Архивный' if is_archived else 'Активный',
            'published_date': parse_hh_date(vacancy_json.get('published_at')),
            'created_date': parse_hh_date(vacancy_json.get('created_at')),  # В деталях может быть
            'updated_at': datetime.now(moscow_tz).replace(tzinfo=None)
        }

        if vacancy:
            # Логика обновления статуса (упрощенная версия revive)
            if vacancy.status == 'Архивный' and not is_archived:
                # Тут можно добавить запись в VacancyStatusHistory о возрождении
                pass
            for k, v in common_data.items(): setattr(vacancy, k, v)
        else:
            vacancy = Vacancy(external_id=ext_id, **common_data)
            session.add(vacancy)
            session.flush()
            # История создания
            session.add(VacancyStatusHistory(
                vacancy_id=vacancy.id, prev_status="Отсутствует", cur_status=common_data['status'],
                type_changed="Первичная загрузка", duration=0,
                created_at_prev_status=common_data['created_date'], created_at_cur_status=common_data['published_date']
            ))

        # 4. M2M Связи (Графики, Форматы)
        # Графики
        schedules = vacancy_json.get('work_schedule_by_days', []) or vacancy_json.get('work_schedule',
                                                                                      [])  # Разные поля в API
        if not isinstance(schedules, list): schedules = [schedules] if schedules else []
        for s in schedules:
            sched_obj = get_or_create(session, WorkSchedule, id_external=str(s['id']), name=s.get('name'))
            if not session.query(vacancy_work_schedules).filter_by(vacancy_id=vacancy.id,
                                                                   work_schedule_id=sched_obj.id).first():
                session.execute(
                    vacancy_work_schedules.insert().values(vacancy_id=vacancy.id, work_schedule_id=sched_obj.id))

        # Форматы
        formats = vacancy_json.get('work_format', [])
        if not isinstance(formats, list): formats = [formats] if formats else []
        for f in formats:
            fmt_obj = get_or_create(session, WorkFormat, id_external=str(f['id']), name=f.get('name'))
            if not session.query(vacancy_work_formats).filter_by(vacancy_id=vacancy.id,
                                                                 work_format_id=fmt_obj.id).first():
                session.execute(vacancy_work_formats.insert().values(vacancy_id=vacancy.id, work_format_id=fmt_obj.id))

        # 5. Зарплата
        sal = vacancy_json.get('salary') or vacancy_json.get('salary_range')
        if sal:
            active_sal = session.query(SalaryHistory).filter_by(vacancy_id=vacancy.id, is_active=True).first()
            curr_from, curr_to, curr_cur = sal.get('from'), sal.get('to'), sal.get('currency', 'RUR')

            if not active_sal or active_sal.salary_from != curr_from or active_sal.currency != curr_cur:
                if active_sal: active_sal.is_active = False
                session.add(SalaryHistory(
                    vacancy_id=vacancy.id, salary_from=curr_from, salary_to=curr_to, currency=curr_cur,
                    mode_id=sal.get('mode', {}).get('id'), mode_name=sal.get('mode', {}).get('name'), is_active=True
                ))

        # 6. Навыки
        for skill_data in vacancy_json.get('key_skills', []):
            skill_name = skill_data.get('name')
            if not skill_name: continue
            skill = get_or_create(session, KeySkill, name=skill_name)
            # Проверка через History
            existing_hist = session.query(KeySkillHistory).filter_by(vacancy_id=vacancy.id, key_skill_id=skill.id,
                                                                     is_active=True).first()
            if not existing_hist:
                # Реактивация или создание
                inactive_hist = session.query(KeySkillHistory).filter_by(vacancy_id=vacancy.id, key_skill_id=skill.id,
                                                                         is_active=False).first()
                if inactive_hist:
                    inactive_hist.is_active = True
                else:
                    session.add(KeySkillHistory(vacancy_id=vacancy.id, key_skill_id=skill.id, is_active=True))

        # 7. Связь с поиском
        if search_query_id:
            if not session.query(search_query_vacancies).filter_by(search_query_id=search_query_id,
                                                                   vacancy_id=vacancy.id).first():
                session.execute(
                    search_query_vacancies.insert().values(search_query_id=search_query_id, vacancy_id=vacancy.id))

    except Exception as e:
        logger.error(f"Ошибка обработки вакансии {vacancy_json.get('id')}: {e}")
        session.rollback()


def upsert_full_batch(session: Session, enriched_data: List[Dict], search_query_id: Optional[int] = None):
    for item in enriched_data:
        process_full_vacancy(session, item['vacancy'], item.get('employer'), search_query_id)
    session.commit()