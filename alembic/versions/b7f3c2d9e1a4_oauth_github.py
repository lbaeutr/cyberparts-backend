"""oauth github

Revision ID: b7f3c2d9e1a4
Revises: fa37b264c347
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f3c2d9e1a4'
down_revision: Union[str, Sequence[str], None] = 'fa37b264c347'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'users',
        'password_hash',
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.create_table(
        'oauth_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('provider_account_id', sa.String(length=64), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'last_login_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'provider',
            'provider_account_id',
            name='uq_oauth_accounts_provider_account',
        ),
        sa.UniqueConstraint(
            'user_id',
            'provider',
            name='uq_oauth_accounts_user_provider',
        ),
    )
    op.create_index(
        op.f('ix_oauth_accounts_user_id'), 'oauth_accounts', ['user_id'], unique=False
    )
    op.create_table(
        'oauth_exchange_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('code_hash', sa.String(length=128), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_oauth_exchange_codes_code_hash'),
        'oauth_exchange_codes',
        ['code_hash'],
        unique=True,
    )
    op.create_index(
        op.f('ix_oauth_exchange_codes_user_id'),
        'oauth_exchange_codes',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_oauth_exchange_codes_user_id'), table_name='oauth_exchange_codes'
    )
    op.drop_index(
        op.f('ix_oauth_exchange_codes_code_hash'), table_name='oauth_exchange_codes'
    )
    op.drop_table('oauth_exchange_codes')
    op.drop_index(op.f('ix_oauth_accounts_user_id'), table_name='oauth_accounts')
    op.drop_table('oauth_accounts')
    op.execute('DELETE FROM users WHERE password_hash IS NULL')
    op.alter_column(
        'users',
        'password_hash',
        existing_type=sa.String(length=255),
        nullable=False,
    )
