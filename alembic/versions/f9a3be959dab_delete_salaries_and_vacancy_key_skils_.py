"""Delete salaries and vacancy_key_skils tables

Revision ID: f9a3be959dab
Revises: 590786322ca8
Create Date: 2025-07-16 20:08:02.887168

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'f9a3be959dab'
down_revision: Union[str, Sequence[str], None] = '590786322ca8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # Проверяем существование таблицы vacancy_key_skills
    if conn.dialect.has_table(conn, 'vacancy_key_skills'):
        op.drop_constraint('vacancy_key_skills_ibfk_1', 'vacancy_key_skills', type_='foreignkey')
        op.drop_constraint('vacancy_key_skills_ibfk_2', 'vacancy_key_skills', type_='foreignkey')
        op.drop_table('vacancy_key_skills')

    # Проверяем существование таблицы salaries
    if conn.dialect.has_table(conn, 'salaries'):
        op.drop_constraint('salaries_ibfk_1', 'salaries', type_='foreignkey')
        op.drop_index(op.f('vacancy_id'), table_name='salaries')
        op.drop_table('salaries')

    # Обновляем таблицы истории
    op.add_column('key_skill_history', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.drop_column('key_skill_history', 'is_active')
    op.add_column('salary_history', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.drop_column('salary_history', 'is_active')
    op.drop_column('salary_history', 'salary_id')


def downgrade() -> None:
    """Downgrade schema."""
    # Восстанавливаем таблицы и ограничения
    op.add_column('salary_history', sa.Column('salary_id', mysql.INTEGER(), autoincrement=False, nullable=False))
    op.add_column('salary_history', sa.Column('is_active', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.create_foreign_key('salary_history_ibfk_1', 'salary_history', 'salaries', ['salary_id'], ['id'])
    op.drop_column('salary_history', 'updated_at')

    op.add_column('key_skill_history', sa.Column('is_active', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.drop_column('key_skill_history', 'updated_at')

    op.create_table('salaries',
        sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('salary_from', mysql.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('salary_to', mysql.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('currency', mysql.VARCHAR(length=10), nullable=True),
        sa.Column('mode_id', mysql.VARCHAR(length=50), nullable=True),
        sa.Column('mode_name', mysql.VARCHAR(length=50), nullable=True),
        sa.Column('vacancy_id', mysql.INTEGER(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(['vacancy_id'], ['vacancies.id'], name=op.f('salaries_ibfk_1')),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_0900_ai_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    op.create_index(op.f('vacancy_id'), 'salaries', ['vacancy_id'], unique=True)

    op.create_table('vacancy_key_skills',
        sa.Column('vacancy_id', mysql.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('key_skill_id', mysql.INTEGER(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['key_skill_id'], ['key_skills.id'], name=op.f('vacancy_key_skills_ibfk_2')),
        sa.ForeignKeyConstraint(['vacancy_id'], ['vacancies.id'], name=op.f('vacancy_key_skills_ibfk_1')),
        sa.PrimaryKeyConstraint('vacancy_id', 'key_skill_id'),
        mysql_collate='utf8mb4_0900_ai_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
