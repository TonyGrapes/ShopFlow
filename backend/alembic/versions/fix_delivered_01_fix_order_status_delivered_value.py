"""fix order_status delivered value

Revision ID: fix_delivered_01
Revises: 685f1b95cdef
Create Date: 2026-09-18 18:34:44.820967

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fix_delivered_01'
down_revision: Union[str, Sequence[str], None] = '685f1b95cdef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Убираем пробел из значения enum ' delivered' → 'delivered'."""
    # ✅ PostgreSQL 10+ поддерживает RENAME VALUE
    op.execute("ALTER TYPE order_status RENAME VALUE ' delivered' TO 'delivered'")


def downgrade() -> None:
    """Обратно: 'delivered' → ' delivered'."""
    op.execute("ALTER TYPE order_status RENAME VALUE 'delivered' TO ' delivered'")
