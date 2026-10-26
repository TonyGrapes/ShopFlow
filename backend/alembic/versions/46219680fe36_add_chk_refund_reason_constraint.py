"""add chk_refund_reason constraint

Revision ID: 46219680fe36
Revises: 92544aea889b
Create Date: 2026-10-26 18:38:40.799706

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46219680fe36'
down_revision: Union[str, Sequence[str], None] = '92544aea889b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "chk_refund_reason",
        "refunds",
        "reason IS NULL OR reason IN "
        "('customer_request', 'defective', 'wrong_item', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "chk_refund_reason", "refunds", type_="check"
    )