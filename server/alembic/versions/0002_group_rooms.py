"""add group ownership and history join cursors"""
from alembic import op
import sqlalchemy as sa

revision = "0002_group_rooms"
down_revision = "0001_phase4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_rooms_owner_id_users", "users", ["owner_id"], ["id"])
    op.add_column("memberships", sa.Column("joined_sequence_id", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("memberships", "joined_sequence_id")
    with op.batch_alter_table("rooms") as batch:
        batch.drop_constraint("fk_rooms_owner_id_users", type_="foreignkey")
        batch.drop_column("owner_id")