import logging
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

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
        return datetime.fromisoformat(str(date_str).replace('Z', '+00:00')).replace(tzinfo=None)
    except:
        return None


def get_or_create(session, model, **kwargs):
    # Фильтруем None значения из kwargs, чтобы filter_by работал корректно
    clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}
    instance = session.query(model).filter_by(**clean_kwargs).first()
    if instance: return instance
    instance = model(**kwargs)
    session.add(instance)
    session.flush()
    return instance


def link_employer_industries(session, employer, industries_data):
    if not isinstance(industries_data, list): return
    for ind in industries_data:
        if not isinstance(ind, dict): continue
        raw_id = ind.get('id')
        if raw_id is None: continue

        industry = get_or_create(session, Industry, id_external=str(raw_id), name=ind.get('name', 'Unknown'))
        exists = session.query(employer_industries).filter_by(employer_id=employer.id, industry_id=industry.id).first()
        if not exists:
            session.execute(employer_industries.insert().values(employer_id=employer.id, industry_id=industry.id))


def process_full_vacancy(session: Session, vacancy_json: Dict, employer_json: Optional[Dict],
                         search_query_id: Optional[int] = None):
    try:
        if not isinstance(vacancy_json, dict):
            logger.error(f"vacancy_json не является словарем: {type(vacancy_json)}")
            return

        ext_id = str(vacancy_json.get('id'))
        if not ext_id or ext_id == 'None':
            return

        # 1. Работодатель (ультра-защита от None)
        emp_data = vacancy_json.get('employer')
        if not isinstance(emp_data, dict): emp_data = {}
        emp_id = emp_data.get('id')

        employer = get_or_create(
            session, Employer,
            id_external=str(emp_id) if emp_id is not None else "0",
            name=emp_data.get('name', 'Неизвестный работодатель')
        )

        if employer_json and isinstance(employer_json, dict):
            area_data = employer_json.get('area')
            employer.area = area_data.get('name') if isinstance(area_data, dict) else None
            employer.accredited_it_employer = employer_json.get('accredited_it_employer', False)
            employer.open_vacancies = employer_json.get('open_vacancies')

            industries = employer_json.get('industries')
            if isinstance(industries, list):
                link_employer_industries(session, employer, industries)

        # 2. Справочники (проверка типов перед доступом к ключам)
        exp_data = vacancy_json.get('experience')
        experience = get_or_create(session, ExperienceLevel, id_external=str(exp_data.get('id')),
                                   name=exp_data.get('name')) if isinstance(exp_data, dict) and exp_data.get(
            'id') else None

        roles = vacancy_json.get('professional_roles')
        role_data = roles[0] if isinstance(roles, list) and len(roles) > 0 and isinstance(roles[0], dict) else {}
        role = get_or_create(session, ProfessionalRole, id_external=str(role_data.get('id')),
                             name=role_data.get('name')) if role_data.get('id') else None

        form_data = vacancy_json.get('employment_form')
        emp_form = get_or_create(session, EmploymentForm, id_external=str(form_data.get('id')),
                                 name=form_data.get('name')) if isinstance(form_data, dict) and form_data.get(
            'id') else None

        hours_raw = vacancy_json.get('working_hours')
        hours_data = hours_raw[0] if isinstance(hours_raw, list) and len(hours_raw) > 0 and isinstance(hours_raw[0],
                                                                                                       dict) else (
            hours_raw if isinstance(hours_raw, dict) else {})
        work_hours = get_or_create(session, WorkingHours, id_external=str(hours_data.get('id')),
                                   name=hours_data.get('name')) if hours_data.get('id') else None

        # 3. Вакансия
        vacancy = session.query(Vacancy).filter_by(external_id=ext_id).first()
        is_archived = bool(vacancy_json.get('archived', False))

        area_data = vacancy_json.get('area')
        area_name = area_data.get('name') if isinstance(area_data, dict) else None

        common_data = {
            'title': vacancy_json.get('name', 'Без названия'),
            'employer_id': employer.id,
            'area': area_name,
            'experience_id': experience.id if experience else None,
            'professional_role_id': role.id if role else None,
            'employment_form_id': emp_form.id if emp_form else None,
            'working_hours_id': work_hours.id if work_hours else None,
            'status': 'Архивный' if is_archived else 'Активный',
            'published_date': parse_hh_date(vacancy_json.get('published_at')),
            'created_date': parse_hh_date(vacancy_json.get('created_at') or vacancy_json.get('initial_created_at')),
            'updated_at': datetime.now(moscow_tz).replace(tzinfo=None)
        }

        if vacancy:
            for k, v in common_data.items():
                setattr(vacancy, k, v)
        else:
            vacancy = Vacancy(external_id=ext_id, **common_data)
            session.add(vacancy)
            session.flush()
            session.add(VacancyStatusHistory(
                vacancy_id=vacancy.id, prev_status="Отсутствует", cur_status=common_data['status'],
                type_changed="Первичная загрузка", duration=0,
                created_at_prev_status=common_data['created_date'], created_at_cur_status=common_data['published_date']
            ))

        # 4. M2M Связи
        schedules = vacancy_json.get('work_schedule') or vacancy_json.get('work_schedule_by_days') or []
        if not isinstance(schedules, list): schedules = [schedules] if schedules else []
        for s in schedules:
            if not isinstance(s, dict) or not s.get('id'): continue
            sched_obj = get_or_create(session, WorkSchedule, id_external=str(s['id']), name=s.get('name'))
            if not session.query(vacancy_work_schedules).filter_by(vacancy_id=vacancy.id,
                                                                   work_schedule_id=sched_obj.id).first():
                session.execute(
                    vacancy_work_schedules.insert().values(vacancy_id=vacancy.id, work_schedule_id=sched_obj.id))

        formats = vacancy_json.get('work_format') or []
        if not isinstance(formats, list): formats = [formats] if formats else []
        for f in formats:
            if not isinstance(f, dict) or not f.get('id'): continue
            fmt_obj = get_or_create(session, WorkFormat, id_external=str(f['id']), name=f.get('name'))
            if not session.query(vacancy_work_formats).filter_by(vacancy_id=vacancy.id,
                                                                 work_format_id=fmt_obj.id).first():
                session.execute(vacancy_work_formats.insert().values(vacancy_id=vacancy.id, work_format_id=fmt_obj.id))

        # 5. Зарплата
        sal = vacancy_json.get('salary') or vacancy_json.get('salary_range')
        if isinstance(sal, dict) and sal.get('from') is not None:
            active_sal = session.query(SalaryHistory).filter_by(vacancy_id=vacancy.id, is_active=True).first()
            curr_from, curr_to, curr_cur = sal.get('from'), sal.get('to'), sal.get('currency', 'RUR')

            mode_data = sal.get('mode')
            mode_id = mode_data.get('id') if isinstance(mode_data, dict) else None
            mode_name = mode_data.get('name') if isinstance(mode_data, dict) else None

            if not active_sal or active_sal.salary_from != curr_from or active_sal.currency != curr_cur:
                if active_sal: active_sal.is_active = False
                session.add(SalaryHistory(
                    vacancy_id=vacancy.id, salary_from=curr_from, salary_to=curr_to, currency=curr_cur,
                    mode_id=mode_id, mode_name=mode_name, is_active=True
                ))

        # 6. Навыки
        skills = vacancy_json.get('key_skills')
        if isinstance(skills, list):
            for skill_data in skills:
                if not isinstance(skill_data, dict) or not skill_data.get('name'): continue
                skill_name = skill_data.get('name')
                skill = get_or_create(session, KeySkill, name=skill_name)

                existing_hist = session.query(KeySkillHistory).filter_by(vacancy_id=vacancy.id, key_skill_id=skill.id,
                                                                         is_active=True).first()
                if not existing_hist:
                    inactive_hist = session.query(KeySkillHistory).filter_by(vacancy_id=vacancy.id,
                                                                             key_skill_id=skill.id,
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
        # Добавляем полный traceback для точной диагностики
        logger.error(f"❌ Ошибка обработки вакансии {vacancy_json.get('id')}: {e}\n{traceback.format_exc()}")
        session.rollback()


def upsert_full_batch(session: Session, enriched_data: List[Dict], search_query_id: Optional[int] = None):
    stats = {'inserted': 0, 'updated': 0, 'errors': 0}
    for item in enriched_data:
        try:
            # Простой способ посчитать: если вакансии не было, она вставится, иначе обновится
            ext_id = str(item['vacancy'].get('id'))
            exists = session.query(Vacancy).filter_by(external_id=ext_id).first()
            if exists:
                stats['updated'] += 1
            else:
                stats['inserted'] += 1

            process_full_vacancy(session, item['vacancy'], item.get('employer'), search_query_id)
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"❌ Критическая ошибка в пакете: {e}")
            session.rollback()

    session.commit()
    return stats