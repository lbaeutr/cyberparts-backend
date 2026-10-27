"""refresh token families

Revision ID: d019e0cc2f28
Revises: b7f3c2d9e1a4
Create Date: 2026-10-27 21:51:29.990391

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d019e0cc2f28"
down_revision: Union[str, Sequence[str], None] = "b7f3c2d9e1a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("refresh_tokens", sa.Column("family_id", sa.String(length=64), nullable=True))
    op.add_column(
        "refresh_tokens",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Cada token existente pasa a ser su propia familia (sesion independiente).
    op.execute(
        "UPDATE refresh_tokens SET family_id = md5(id::text || random()::text)"
    )
    op.execute(
        "UPDATE refresh_tokens SET revoked_at = created_at WHERE revoked IS TRUE"
    )

    op.alter_column("refresh_tokens", "family_id", nullable=False)
    op.create_index(
        op.f("ix_refresh_tokens_family_id"), "refresh_tokens", ["family_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "revoked_at")
    op.drop_column("refresh_tokens", "family_id")
