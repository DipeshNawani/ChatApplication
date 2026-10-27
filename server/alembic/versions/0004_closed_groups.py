"""archive empty groups"""
from alembic import op
import sqlalchemy as sa

revision = "0004_closed_groups"
down_revision = "0003_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.drop_column("is_closed")
