"""add money check constraints

Revision ID: 4df48ea6533e
Revises: ccdfc71631df
Create Date: 2026-10-25 19:34:26.513482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4df48ea6533e'
down_revision: Union[str, Sequence[str], None] = 'ccdfc71631df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # orders
    op.create_check_constraint(
        "chk_orders_total_non_negative",
        "orders",
        "total >= 0",
    )

    # order_items (product_count > 0 уже есть)
    op.create_check_constraint(
        "chk_order_items_cost_non_negative",
        "order_items",
        "product_cost >= 0",
    )

    # payments
    op.create_check_constraint(
        "chk_payments_amount_positive",
        "payments",
        "amount > 0",
    )

    # refunds
    op.create_check_constraint(
        "chk_refunds_amount_positive",
        "refunds",
        "amount > 0",
    )

    # promo_codes: percentage 1..100
    op.create_check_constraint(
        "chk_promo_percentage_range",
        "promo_codes",
        "discount_type != 'percentage' "
        "OR (discount_value >= 1 AND discount_value <= 100)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "chk_promo_percentage_range", "promo_codes", type_="check"
    )
    op.drop_constraint(
        "chk_refunds_amount_positive", "refunds", type_="check"
    )
    op.drop_constraint(
        "chk_payments_amount_positive", "payments", type_="check"
    )
    op.drop_constraint(
        "chk_order_items_cost_non_negative", "order_items", type_="check"
    )
    op.drop_constraint(
        "chk_orders_total_non_negative", "orders", type_="check"
    )
