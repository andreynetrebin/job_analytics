import logging
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
    if not date_str:
        return None
    try:
        clean_str = date_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(clean_str)
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def get_or_create_employer(session, data: Optional[Dict[str, Any]]) -> Optional[Employer]:
    if not isinstance(data, dict):
        return None

    # ✅ ИСПРАВЛЕНИЕ 1: Безопасная обработка отсутствующего ID работодателя
    raw_id = data.get('id')
    if raw_id is None:
        raw_id = 0  # Запасной ID для анонимных работодателей

    try:
        ext_id = int(raw_id)
    except (ValueError, TypeError):
        ext_id = 0

    employer = session.query(Employer).filter_by(id_external=ext_id).first()
    if not employer:
        area_data = data.get('area')
        area_name = area_data.get('name') if isinstance(area_data, dict) else None

        employer = Employer(
            id_external=ext_id,
            name=data.get('name', 'Неизвестный работодатель'),
            area=area_name,
            accredited_it_employer=data.get('accredited_it_employer', False),
        )
        session.add(employer)
        session.flush()
    return employer


def link_industries(session, employer: Employer, industries_data: List[Dict[str, Any]]):
    if not isinstance(industries_data, list):
        return
    for ind_data in industries_data:
        if not isinstance(ind_data, dict):
            continue
        raw_id = ind_data.get('id')
        if raw_id is None:
            continue

        try:
            ext_id = int(raw_id)
        except (ValueError, TypeError):
            continue

        industry = session.query(Industry).filter_by(id_external=ext_id).first()
        if not industry:
            industry = Industry(id_external=ext_id, name=ind_data.get('name', 'Unknown'))
            session.add(industry)
            session.flush()

        exists = session.query(employer_industries).filter_by(
            employer_id=employer.id, industry_id=industry.id
        ).first()
        if not exists:
            session.execute(employer_industries.insert().values(employer_id=employer.id, industry_id=industry.id))


def get_or_create_ref(session, model, data: Optional[Dict[str, Any]]):
    if not isinstance(data, dict):
        return None
    raw_id = data.get('id')
    if raw_id is None:
        return None

    # Для справочников ID обычно строковые или целые, приводим к строке для универсальности
    ext_id = str(raw_id)

    instance = session.query(model).filter_by(id_external=ext_id).first()
    if not instance:
        instance = model(id_external=ext_id, name=data.get('name', 'Unknown'))
        session.add(instance)
        session.flush()
    return instance


def get_or_create_schedule(session, data: Optional[Dict[str, Any]]) -> Optional[int]:
    if not isinstance(data, dict):
        return None
    raw_id = data.get('id')
    if raw_id is None:
        return None

    ext_id = str(raw_id)
    instance = session.query(WorkSchedule).filter_by(id_external=ext_id).first()
    if not instance:
        instance = WorkSchedule(id_external=ext_id, name=data.get('name', 'Unknown'))
        session.add(instance)
        session.flush()
    return instance.id


def get_or_create_format(session, data: Optional[Dict[str, Any]]) -> Optional[int]:
    if not isinstance(data, dict):
        return None
    raw_id = data.get('id')
    if raw_id is None:
        return None

    ext_id = str(raw_id)
    instance = session.query(WorkFormat).filter_by(id_external=ext_id).first()
    if not instance:
        instance = WorkFormat(id_external=ext_id, name=data.get('name', 'Unknown'))
        session.add(instance)
        session.flush()
    return instance.id


def upsert_vacancies_to_db(session: Session, raw_vacancies: List[Dict[str, Any]],
                           search_query_id: Optional[int] = None) -> Dict[str, int]:
    stats = {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

    for v_data in raw_vacancies:
        try:
            ext_id = str(v_data.get('id'))
            if not ext_id or ext_id == 'None':
                continue

            # 1. Работодатель
            employer = get_or_create_employer(session, v_data.get('employer'))
            if not employer:
                continue

            if 'industries' in v_data.get('employer', {}):
                link_industries(session, employer, v_data['employer']['industries'])

            # 2. Справочники
            experience = get_or_create_ref(session, ExperienceLevel, v_data.get('experience'))

            roles = v_data.get('professional_roles', [])
            prof_role = get_or_create_ref(session, ProfessionalRole, roles[0]) if roles and isinstance(roles,
                                                                                                       list) else None

            emp_form = get_or_create_ref(session, EmploymentForm, v_data.get('employment_form'))

            work_hours_data = v_data.get('working_hours')
            if isinstance(work_hours_data, list) and len(work_hours_data) > 0:
                work_hours_data = work_hours_data[0]
            work_hours = get_or_create_ref(session, WorkingHours, work_hours_data)

            # 3. Сама Вакансия
            vacancy = session.query(Vacancy).filter_by(external_id=ext_id).first()
            is_new = vacancy is None

            common_data = {
                'title': v_data.get('name', 'Без названия'),
                'employer_id': employer.id,
                'area': v_data.get('area', {}).get('name') if isinstance(v_data.get('area'), dict) else None,
                'experience_id': experience.id if experience else None,
                'professional_role_id': prof_role.id if prof_role else None,
                'employment_form_id': emp_form.id if emp_form else None,
                'working_hours_id': work_hours.id if work_hours else None,
                'status': 'Архивный' if v_data.get('archived') else 'Активный',
                'created_date': parse_hh_date(v_data.get('created_at') or v_data.get('initial_created_at')),
                'published_date': parse_hh_date(v_data.get('published_at')),
                'updated_at': datetime.now(moscow_tz).replace(tzinfo=None)
            }

            if is_new:
                vacancy = Vacancy(external_id=ext_id, **common_data)
                session.add(vacancy)
                session.flush()
                stats['inserted'] += 1

                status_hist = VacancyStatusHistory(
                    vacancy_id=vacancy.id,
                    prev_status="Отсутствует",
                    cur_status=common_data['status'],
                    type_changed="Первичная загрузка",
                    duration=0,
                    created_at_prev_status=common_data['created_date'],
                    created_at_cur_status=common_data['published_date']
                )
                session.add(status_hist)
            else:
                for key, val in common_data.items():
                    setattr(vacancy, key, val)
                stats['updated'] += 1

            # 4. M2M связи
            sched_data = v_data.get('work_schedule')
            if sched_data:
                schedules = sched_data if isinstance(sched_data, list) else [sched_data]
                for sched in schedules:
                    sched_id = get_or_create_schedule(session, sched)
                    if sched_id:
                        exists = session.query(vacancy_work_schedules).filter_by(vacancy_id=vacancy.id,
                                                                                 work_schedule_id=sched_id).first()
                        if not exists:
                            session.execute(vacancy_work_schedules.insert().values(vacancy_id=vacancy.id,
                                                                                   work_schedule_id=sched_id))

            fmt_data = v_data.get('work_format')
            if fmt_data:
                formats = fmt_data if isinstance(fmt_data, list) else [fmt_data]
                for fmt in formats:
                    fmt_id = get_or_create_format(session, fmt)
                    if fmt_id:
                        exists = session.query(vacancy_work_formats).filter_by(vacancy_id=vacancy.id,
                                                                               work_format_id=fmt_id).first()
                        if not exists:
                            session.execute(
                                vacancy_work_formats.insert().values(vacancy_id=vacancy.id, work_format_id=fmt_id))

            # 5. Зарплата
            salary_data = v_data.get('salary') or v_data.get('salary_range')
            if isinstance(salary_data, dict):
                curr_from = salary_data.get('from')
                curr_to = salary_data.get('to')
                curr_curr = salary_data.get('currency', 'RUR')

                active_sal = session.query(SalaryHistory).filter_by(vacancy_id=vacancy.id, is_active=True).first()

                change_detected = False
                if not active_sal:
                    change_detected = True
                elif (active_sal.salary_from != curr_from or
                      active_sal.salary_to != curr_to or
                      active_sal.currency != curr_curr):
                    change_detected = True
                    active_sal.is_active = False
                    session.flush()

                if change_detected:
                    new_sal = SalaryHistory(
                        vacancy_id=vacancy.id,
                        salary_from=curr_from,
                        salary_to=curr_to,
                        currency=curr_curr,
                        mode_name=salary_data.get('mode', {}).get('name') if isinstance(salary_data.get('mode'),
                                                                                        dict) else None,
                        is_active=True
                    )
                    session.add(new_sal)

            # 6. Ключевые навыки
            skills_data = v_data.get('key_skills', [])
            if isinstance(skills_data, list):
                for skill_d in skills_data:
                    if not isinstance(skill_d, dict):
                        continue
                    s_name = skill_d.get('name')
                    if not s_name:
                        continue

                    skill = session.query(KeySkill).filter_by(name=s_name).first()
                    if not skill:
                        skill = KeySkill(name=s_name)
                        session.add(skill)
                        session.flush()

                    ksh = session.query(KeySkillHistory).filter_by(vacancy_id=vacancy.id, key_skill_id=skill.id,
                                                                   is_active=True).first()
                    if not ksh:
                        inactive_ksh = session.query(KeySkillHistory).filter_by(vacancy_id=vacancy.id,
                                                                                key_skill_id=skill.id,
                                                                                is_active=False).first()
                        if inactive_ksh:
                            inactive_ksh.is_active = True
                        else:
                            new_ksh = KeySkillHistory(vacancy_id=vacancy.id, key_skill_id=skill.id, is_active=True)
                            session.add(new_ksh)

            # 7. Привязка к поисковому запросу
            if search_query_id:
                link_exists = session.query(search_query_vacancies).filter_by(search_query_id=search_query_id,
                                                                              vacancy_id=vacancy.id).first()
                if not link_exists:
                    session.execute(
                        search_query_vacancies.insert().values(search_query_id=search_query_id, vacancy_id=vacancy.id))

        except Exception as e:
            logger.error(f"Ошибка обработки вакансии {v_data.get('id')}: {e}")
            stats['errors'] += 1
            # ✅ ИСПРАВЛЕНИЕ 2: Откатываем транзакцию, чтобы следующая вакансия не падала с ошибкой "Session is rolled back"
            session.rollback()
            continue

    # Финальный коммит всех успешных операций
    try:
        session.commit()
        logger.info(
            f"✅ Пакетная загрузка завершена: {stats['inserted']} новых, {stats['updated']} обновлено, {stats['errors']} ошибок")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при коммите в БД: {e}")
        session.rollback()
        raise

    return stats