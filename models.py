from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DECIMAL, DateTime, Table, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import pytz

Base = declarative_base()
moscow_tz = pytz.timezone('Europe/Moscow')

# Определение промежуточной таблицы для работы с форматами вакансий
vacancy_work_formats = Table(
    'vacancy_work_formats', Base.metadata,
    Column('vacancy_id', Integer, ForeignKey('vacancies.id'), primary_key=True),
    Column('work_format_id', Integer, ForeignKey('work_formats.id'), primary_key=True)
)

# Определение промежуточной таблицы для ключевых навыков
vacancy_key_skills = Table(
    'vacancy_key_skills', Base.metadata,
    Column('vacancy_id', Integer, ForeignKey('vacancies.id'), primary_key=True),
    Column('key_skill_id', Integer, ForeignKey('key_skills.id'), primary_key=True)
)

# Определение промежуточной таблицы для отраслей
employer_industries = Table(
    'employer_industries', Base.metadata,
    Column('employer_id', Integer, ForeignKey('employers.id'), primary_key=True),
    Column('industry_id', Integer, ForeignKey('industries.id'), primary_key=True)
)

# Определение промежуточной таблицы для графика работы
vacancy_work_schedules = Table(
    'vacancy_work_schedules', Base.metadata,
    Column('vacancy_id', Integer, ForeignKey('vacancies.id'), primary_key=True),
    Column('work_schedule_id', Integer, ForeignKey('work_schedules.id'), primary_key=True)
)

class Industry(Base):
    __tablename__ = 'industries'
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)

class Employer(Base):
    __tablename__ = 'employers'
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    area = Column(String(255))
    accredited_it_employer = Column(Boolean, default=False)
    open_vacancies = Column(Integer)
    industries = relationship("Industry", secondary=employer_industries, backref='employers')

class ProfessionalRole(Base):
    __tablename__ = 'professional_roles'
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)

class ExperienceLevel(Base):
    __tablename__ = 'experience_levels'
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)

class WorkFormat(Base):
    __tablename__ = 'work_formats'
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)

class KeySkill(Base):
    __tablename__ = 'key_skills'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)

class Salary(Base):
    __tablename__ = 'salaries'
    id = Column(Integer, primary_key=True, autoincrement=True)
    salary_from = Column(DECIMAL(10, 2))
    salary_to = Column(DECIMAL(10, 2))
    currency = Column(String(10))
    mode_id = Column(String(50))
    mode_name = Column(String(50))
    vacancy_id = Column(Integer, ForeignKey('vacancies.id'), unique=True)

class EmploymentForm(Base):
    __tablename__ = 'employment_forms'
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)

class WorkingHours(Base):
    __tablename__ = 'working_hours'
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)

class WorkSchedule(Base):
    __tablename__ = 'work_schedules'
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_external = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)

class Vacancy(Base):
    __tablename__ = 'vacancies'
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

    employer = relationship("Employer")
    experience = relationship("ExperienceLevel")
    professional_role = relationship("ProfessionalRole")
    employment_form = relationship("EmploymentForm")
    working_hours = relationship("WorkingHours")
    work_schedules = relationship("WorkSchedule", secondary=vacancy_work_schedules, backref='vacancies')
    work_formats = relationship("WorkFormat", secondary=vacancy_work_formats, backref='vacancies')
    key_skills = relationship("KeySkill", secondary=vacancy_key_skills, backref='vacancies')
    salary = relationship("Salary", back_populates="vacancy", uselist=False)
    status_history = relationship("VacancyStatusHistory", back_populates="vacancy")

class TemporaryVacancy(Base):
    __tablename__ = 'temporary_vacancies'
    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(255), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    employer = Column(String(255))
    status = Column(String(50), nullable=False)
    professional_role = Column(String(255))
    created_at = Column(DateTime, default=lambda: datetime.now(moscow_tz))

class VacancyStatusHistory(Base):
    __tablename__ = 'vacancy_status_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    vacancy_id = Column(Integer, ForeignKey('vacancies.id'), nullable=False)
    prev_status = Column(String(50), nullable=False)
    cur_status = Column(String(50), nullable=False)
    created_at_prev_status = Column(DateTime, default=lambda: datetime.now(moscow_tz))
    created_at_cur_status = Column(DateTime, default=lambda: datetime.now(moscow_tz))
    duration = Column(Integer)
    type_changed = Column(String(50))

    vacancy = relationship("Vacancy", back_populates="status_history")

# Новая модель для хранения поисковых запросов
class SearchQuery(Base):
    __tablename__ = 'search_queries'
    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String(255), nullable=False)  # Поисковый запрос
    is_active = Column(Boolean, default=False)  # Состояние (включено/выключено)
    created_at = Column(DateTime, default=lambda: datetime.now(moscow_tz))  # Дата создания
    updated_at = Column(DateTime, default=lambda: datetime.now(moscow_tz), onupdate=lambda: datetime.now(moscow_tz))  # Дата изменения
    initiator = Column(String(255), nullable=False)  # Инициатор
    email = Column(String(255), nullable=False)  # Email инициатора
    vacancies = relationship("Vacancy", back_populates="search_query")  # Связь с таблицей вакансий

# Обновление связи в классе Vacancy
Vacancy.search_query_id = Column(Integer, ForeignKey('search_queries.id'))  # Добавление внешнего ключа
Vacancy.search_query = relationship("SearchQuery", back_populates="vacancies")  # Связь с таблицей поисковых запросов

# Обновление связи в классе Salary
Salary.vacancy = relationship("Vacancy", back_populates="salary")
