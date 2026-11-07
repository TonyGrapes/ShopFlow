"""add case-insensitive unique index on promo_codes.code

Revision ID: 707b2e32f1a4
Revises: 46219680fe36
Create Date: 2026-11-07 18:02:07.893748

CLN-014: lookup was case-sensitive ('summer10' != 'SUMMER10'),
and DB-level UNIQUE on code allowed both to coexist.

This migration:
1. Pre-checks for case-insensitive duplicates (fails with a clear message
   if any exist — manual rename/merge required before applying).
2. Drops the old case-sensitive UNIQUE(code).
3. Creates a functional unique index on lower(code).

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '707b2e32f1a4'
down_revision: Union[str, Sequence[str], None] = '46219680fe36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Pre-check: fail loudly if case-insensitive duplicates exist.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM promo_codes
                GROUP BY lower(code) HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Duplicate promo codes found (case-insensitive). '
                    'Rename or merge them before this migration.';
            END IF;
        END $$;
    """)

    # 2. Drop old case-sensitive unique constraint.
    op.drop_constraint("promo_codes_code_key", "promo_codes", type_="unique")

    # 3. Create functional unique index on lower(code).
    op.create_index(
        "uq_promo_codes_lower_code",
        "promo_codes",
        [sa.text("lower(code)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_promo_codes_lower_code", table_name="promo_codes")
    op.create_unique_constraint("promo_codes_code_key", "promo_codes", ["code"])