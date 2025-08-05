from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DECIMAL, DateTime, Table, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import pytz

Base = declarative_base()
moscow_tz = pytz.timezone('Europe/Moscow')

# Определение промежуточных таблиц
vacancy_work_formats = Table(
    'vacancy_work_formats', Base.metadata,
    Column('vacancy_id', Integer, ForeignKey('vacancies.id'), primary_key=True),
    Column('work_format_id', Integer, ForeignKey('work_formats.id'), primary_key=True)
)

employer_industries = Table(
    'employer_industries', Base.metadata,
    Column('employer_id', Integer, ForeignKey('employers.id'), primary_key=True),
    Column('industry_id', Integer, ForeignKey('industries.id'), primary_key=True)
)

vacancy_work_schedules = Table(
    'vacancy_work_schedules', Base.metadata,
    Column('vacancy_id', Integer, ForeignKey('vacancies.id'), primary_key=True),
    Column('work_schedule_id', Integer, ForeignKey('work_schedules.id'), primary_key=True)
)

search_query_vacancies = Table(
    'search_query_vacancies', Base.metadata,
    Column('search_query_id', Integer, ForeignKey('search_queries.id'), primary_key=True),
    Column('vacancy_id', Integer, ForeignKey('vacancies.id'), primary_key=True)
)


class Industry(Base):
    __tablename__ = 'industries'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)

    # Определение отношений
    employers = relationship("Employer", secondary=employer_industries, backref='industries_linked',
                             overlaps="industries_linked")


class Employer(Base):
    __tablename__ = 'employers'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    area = Column(String(255))
    accredited_it_employer = Column(Boolean, default=False)
    open_vacancies = Column(Integer)
    total_rating = Column(Float, nullable=True, default=0.0)
    reviews_count = Column(Integer, nullable=True, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(moscow_tz))
    updated_at = Column(DateTime, default=lambda: datetime.now(moscow_tz), onupdate=lambda: datetime.now(moscow_tz))

    # Определение отношений
    industries = relationship("Industry", secondary=employer_industries, backref='employers_linked',
                              overlaps="employers")


class ProfessionalRole(Base):
    __tablename__ = 'professional_roles'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)


class ExperienceLevel(Base):
    __tablename__ = 'experience_levels'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)


class WorkFormat(Base):
    __tablename__ = 'work_formats'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)


class KeySkill(Base):
    __tablename__ = 'key_skills'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)


class EmploymentForm(Base):
    __tablename__ = 'employment_forms'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)


class WorkingHours(Base):
    __tablename__ = 'working_hours'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)


class WorkSchedule(Base):
    __tablename__ = 'work_schedules'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)

class Vacancy(Base):
    __tablename__ = 'vacancies'
    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(255), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    employer_id = Column(Integer, ForeignKey('employers.id'))
    area = Column(String(255))
    experience_id = Column(Integer, ForeignKey('experience_levels.id'))
    professional_role_id = Column(Integer, ForeignKey('professional_roles.id'))
    employment_form_id = Column(Integer, ForeignKey('employment_forms.id'))
    working_hours_id = Column(Integer, ForeignKey('working_hours.id'))
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(moscow_tz))
    updated_at = Column(DateTime, default=lambda: datetime.now(moscow_tz), onupdate=lambda: datetime.now(moscow_tz))
    created_date = Column(DateTime)
    published_date = Column(DateTime)
    # Определение отношений
    employer = relationship("Employer")
    experience = relationship("ExperienceLevel")
    professional_role = relationship("ProfessionalRole")
    employment_form = relationship("EmploymentForm")
    working_hours = relationship("WorkingHours")
    work_schedules = relationship("WorkSchedule", secondary=vacancy_work_schedules, backref='vacancies')
    work_formats = relationship("WorkFormat", secondary=vacancy_work_formats, backref='vacancies')
    # Связь с KeySkillHistory
    key_skill_history = relationship("KeySkillHistory", back_populates="vacancy")  # Связь с историей ключевых навыков
    status_history = relationship("VacancyStatusHistory", back_populates="vacancy")
    search_queries = relationship("SearchQuery", secondary=search_query_vacancies,
                                  back_populates="vacancies")  # Обновленная связь с таблицей поисковых запросов
    salary_history = relationship("SalaryHistory", back_populates="vacancy")  # Связь с таблицей истории зарплат


class SalaryHistory(Base):
    __tablename__ = 'salary_history'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    vacancy_id = Column(Integer, ForeignKey('vacancies.id'), nullable=False)
    salary_from = Column(DECIMAL(10, 2))
    salary_to = Column(DECIMAL(10, 2))
    currency = Column(String(10))
    mode_id = Column(String(50))
    mode_name = Column(String(50))
    created_at = Column(DateTime, default=lambda: datetime.now(moscow_tz))  # Дата создания записи
    updated_at = Column(DateTime, default=lambda: datetime.now(moscow_tz),
                        onupdate=lambda: datetime.now(moscow_tz))  # Дата обновления записи
    is_active = Column(Boolean, default=True)  # Статус активности записи
    # Определение отношений
    vacancy = relationship("Vacancy", back_populates="salary_history")


class VacancyStatusHistory(Base):
    __tablename__ = 'vacancy_status_history'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    vacancy_id = Column(Integer, ForeignKey('vacancies.id'), nullable=False)
    prev_status = Column(String(50), nullable=False)
    cur_status = Column(String(50), nullable=False)
    created_at_prev_status = Column(DateTime, default=lambda: datetime.now(moscow_tz))
    created_at_cur_status = Column(DateTime, default=lambda: datetime.now(moscow_tz))
    duration = Column(Integer)
    type_changed = Column(String(50))

    # Определение отношений
    vacancy = relationship("Vacancy", back_populates="status_history")


class SearchQuery(Base):
    __tablename__ = 'search_queries'
    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(moscow_tz))
    updated_at = Column(DateTime, default=lambda: datetime.now(moscow_tz), onupdate=lambda: datetime.now(moscow_tz))
    initiator = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    # Определение отношений
    vacancies = relationship("Vacancy", secondary=search_query_vacancies, back_populates="search_queries")


class KeySkillHistory(Base):
    __tablename__ = 'key_skill_history'

    # Определение колонок
    id = Column(Integer, primary_key=True, autoincrement=True)
    vacancy_id = Column(Integer, ForeignKey('vacancies.id'), nullable=False)
    key_skill_id = Column(Integer, ForeignKey('key_skills.id'), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(moscow_tz))  # Дата создания записи
    updated_at = Column(DateTime, default=lambda: datetime.now(moscow_tz),
                        onupdate=lambda: datetime.now(moscow_tz))  # Дата обновления записи
    is_active = Column(Boolean, default=True)  # Статус активности записи

    # Определение отношений
    key_skill = relationship("KeySkill")
    vacancy = relationship("Vacancy", back_populates="key_skill_history")
