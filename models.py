from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DECIMAL, DateTime, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

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


class ProfessionalRole(Base):
    __tablename__ = 'professional_roles'
    id = Column(Integer, primary_key=True, autoincrement=True)  # Автоматически генерируемый id
    id_external = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)


class ExperienceLevel(Base):
    __tablename__ = 'experience_levels'
    id = Column(Integer, primary_key=True, autoincrement=True)  # Автоматически генерируемый id
    id_external = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)


class WorkFormat(Base):
    __tablename__ = 'work_formats'
    id = Column(Integer, primary_key=True, autoincrement=True)  # Автоматически генерируемый id
    id_external = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)


class KeySkill(Base):
    __tablename__ = 'key_skills'
    id = Column(Integer, primary_key=True, autoincrement=True)  # Автоматически генерируемый id
    name = Column(String(255), nullable=False, unique=True)


class Salary(Base):
    __tablename__ = 'salaries'
    id = Column(Integer, primary_key=True, autoincrement=True)  # Автоматически генерируемый id
    salary_from = Column(DECIMAL(10, 2))
    salary_to = Column(DECIMAL(10, 2))
    currency = Column(String(10))  # Код валюты, например, "USD", "EUR"
    vacancy_id = Column(Integer, ForeignKey('vacancies.id'), unique=True)


class Vacancy(Base):
    __tablename__ = 'vacancies'
    id = Column(Integer, primary_key=True, autoincrement=True)  # Автоматически генерируемый id
    external_id = Column(String(255), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    employer = Column(String(255))
    area = Column(String(255))
    experience_id = Column(Integer, ForeignKey('experience_levels.id'))  # Изменено на Integer
    professional_role_id = Column(Integer, ForeignKey('professional_roles.id'))
    status = Column(String(50), nullable=False)  # Статус теперь строка
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_date = Column(DateTime)  # Новая дата создания
    published_date = Column(DateTime)  # Новая дата публикации

    experience = relationship("ExperienceLevel")
    professional_role = relationship("ProfessionalRole")
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
    created_at = Column(DateTime, default=datetime.utcnow)


class VacancyStatusHistory(Base):
    __tablename__ = 'vacancy_status_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    vacancy_id = Column(Integer, ForeignKey('vacancies.id'), nullable=False)
    new_status = Column(String(50), nullable=False)  # Новый статус вакансии
    changed_at = Column(DateTime, default=datetime.utcnow)  # Дата и время изменения статуса

    vacancy = relationship("Vacancy", back_populates="status_history")


# Обновление связи в классе Salary
Salary.vacancy = relationship("Vacancy", back_populates="salary")
