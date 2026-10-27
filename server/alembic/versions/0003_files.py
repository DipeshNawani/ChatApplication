"""add file objects"""
from alembic import op
import sqlalchemy as sa

revision = "0003_files"
down_revision = "0002_group_rooms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("messages", sa.Column("file_id", sa.String(length=64), nullable=True))
    with op.batch_alter_table("messages") as batch:
        batch.create_foreign_key("fk_messages_file_id_files", "files", ["file_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_constraint("fk_messages_file_id_files", type_="foreignkey")
        batch.drop_column("file_id")
    op.drop_table("files")