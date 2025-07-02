from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DECIMAL, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class ExperienceLevel(Base):
    __tablename__ = 'experience_levels'
    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)


class WorkFormat(Base):
    __tablename__ = 'work_formats'
    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)


class KeySkill(Base):
    __tablename__ = 'key_skills'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)


class Salary(Base):
    __tablename__ = 'salaries'
    id = Column(Integer, primary_key=True)
    salary_from = Column(DECIMAL(10, 2))
    salary_to = Column(DECIMAL(10, 2))
    currency = Column(String(10))  # Код валюты, например, "USD", "EUR"
    vacancy_id = Column(Integer, ForeignKey('vacancies.id'), unique=True)


class Vacancy(Base):
    __tablename__ = 'vacancies'
    id = Column(Integer, primary_key=True)
    external_id = Column(String(255), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    employer = Column(String(255))
    area = Column(String(255))
    experience_id = Column(String(50), ForeignKey('experience_levels.id'))
    status = Column(String(50), nullable=False)  # Статус теперь строка
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_date = Column(DateTime)  # Новая дата создания
    published_date = Column(DateTime)  # Новая дата публикации

    experience = relationship("ExperienceLevel")
    work_formats = relationship("WorkFormat", secondary='vacancy_work_formats', backref='vacancies')
    key_skills = relationship("KeySkill", secondary='vacancy_key_skills', backref='vacancies')
    salary = relationship("Salary", back_populates="vacancy", uselist=False)


# Обновление связи в классе Salary
Salary.vacancy = relationship("Vacancy", back_populates="salary")
