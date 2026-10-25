"""add idempotency to orders

Revision ID: 92544aea889b
Revises: 4df48ea6533e
Create Date: 2026-10-25 19:57:00.927462

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92544aea889b'
down_revision: Union[str, Sequence[str], None] = '4df48ea6533e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("idempotency_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("idempotency_body_hash", sa.Text(), nullable=True),
    )
    op.create_index(
        "uq_orders_user_idempotency_key",
        "orders",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_orders_user_idempotency_key",
        table_name="orders",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_column("orders", "idempotency_body_hash")
    op.drop_column("orders", "idempotency_key")