"""content columns become opaque text so they can hold AES-GCM ciphertext

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("documents", "revisions"):
        with op.batch_alter_table(table) as b:
            b.alter_column("content_json", existing_type=sa.JSON(), type_=sa.Text(),
                           postgresql_using="content_json::text")


def downgrade() -> None:
    for table in ("documents", "revisions"):
        with op.batch_alter_table(table) as b:
            b.alter_column("content_json", existing_type=sa.Text(), type_=sa.JSON(),
                           postgresql_using="content_json::json")
