"""changed string to integer experience_levels.id, work_formats.id

Revision ID: 18367de2eabb
Revises: c68717d6c3d9
Create Date: 2025-07-03 16:19:30.063914

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '18367de2eabb'
down_revision: Union[str, Sequence[str], None] = 'c68717d6c3d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Удаление внешнего ключа перед изменением типа
    op.drop_constraint('vacancy_work_formats_ibfk_2', 'vacancy_work_formats', type_='foreignkey')

    # Изменение типа столбца id в work_formats
    op.alter_column('work_formats', 'id',
               existing_type=mysql.VARCHAR(length=50),
               type_=sa.Integer(),
               existing_nullable=False,
               autoincrement=True)

    # Изменение типа столбца work_format_id в vacancy_work_formats
    op.alter_column('vacancy_work_formats', 'work_format_id',
               existing_type=mysql.VARCHAR(length=50),
               type_=sa.Integer(),
               existing_nullable=False)

    # Изменение типа столбца id в experience_levels
    op.alter_column('experience_levels', 'id',
               existing_type=mysql.VARCHAR(length=50),
               type_=sa.Integer(),
               existing_nullable=False,
               autoincrement=True)

    # Изменение типа столбца experience_id в vacancies
    op.alter_column('vacancies', 'experience_id',
               existing_type=mysql.VARCHAR(length=50),
               type_=sa.Integer(),
               existing_nullable=True)

    # Восстановление внешнего ключа
    op.create_foreign_key('vacancy_work_formats_ibfk_2', 'vacancy_work_formats', 'work_formats', ['work_format_id'], ['id'])

    # Добавление новых столбцов
    op.create_unique_constraint(None, 'experience_levels', ['id_external'])

    op.add_column('work_formats', sa.Column('id_external', sa.String(length=255), nullable=False))
    op.create_unique_constraint(None, 'work_formats', ['id_external'])

    # Создание новой таблицы
    op.create_table('professional_roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Удаление внешнего ключа перед изменением типа
    op.drop_constraint('vacancy_work_formats_ibfk_2', 'vacancy_work_formats', type_='foreignkey')

    # Восстановление предыдущего состояния
    op.drop_constraint(None, 'work_formats', type_='unique')
    op.alter_column('work_formats', 'id',
               existing_type=sa.Integer(),
               type_=mysql.VARCHAR(length=50),
               existing_nullable=False,
               autoincrement=True)
    op.drop_column('work_formats', 'id_external')

    op.alter_column('vacancy_work_formats', 'work_format_id',
               existing_type=sa.Integer(),
               type_=mysql.VARCHAR(length=50),
               existing_nullable=False)

    op.alter_column('vacancies', 'experience_id',
               existing_type=sa.Integer(),
               type_=mysql.VARCHAR(length=50),
               existing_nullable=True)

    op.drop_constraint(None, 'experience_levels', type_='unique')
    op.alter_column('experience_levels', 'id',
               existing_type=sa.Integer(),
               type_=mysql.VARCHAR(length=50),
               existing_nullable=False,
               autoincrement=True)
    op.drop_column('experience_levels', 'id_external')

    op.drop_table('professional_roles')
