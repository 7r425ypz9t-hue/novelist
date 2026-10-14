"""device sessions: when each signed-in device was last active («أجهزتي»)

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("auth_sessions") as b:
        b.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("auth_sessions") as b:
        b.drop_column("last_seen_at")
