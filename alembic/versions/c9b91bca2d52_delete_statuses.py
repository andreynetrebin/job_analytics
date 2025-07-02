"""delete statuses

Revision ID: c9b91bca2d52
Revises: 
Create Date: 2025-07-02 23:01:58.369397
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'c9b91bca2d52'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Удалите внешний ключ перед удалением таблицы
    op.drop_constraint('vacancies_ibfk_2', 'vacancies', type_='foreignkey')

    # Удалите столбец, который ссылается на таблицу statuses
    op.drop_column('vacancies', 'status_id')

    # Теперь можно удалить таблицу statuses
    op.drop_table('statuses')

def downgrade() -> None:
    """Downgrade schema."""
    # Восстановите столбец status_id в таблице vacancies
    op.add_column('vacancies', sa.Column('status_id', mysql.INTEGER(), autoincrement=False, nullable=True))

    # Восстановите внешний ключ
    op.create_foreign_key('vacancies_ibfk_2', 'vacancies', 'statuses', ['status_id'], ['id'])

    # Восстановите таблицу statuses
    op.create_table('statuses',
        sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('name', mysql.VARCHAR(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_0900_ai_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
