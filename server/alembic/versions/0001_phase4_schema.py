"""create Phase 4 account and chat schema

Revision ID: 0001_phase4
Revises:
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0001_phase4"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_table(
        "rooms",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("direct_key", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("direct_key"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.String(length=64), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("room_id", "user_id"),
    )
    op.create_index("ix_memberships_room_id", "memberships", ["room_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "messages",
        sa.Column("sequence_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("room_id", sa.String(length=64), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_message_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id"),
        sa.UniqueConstraint("sender_user_id", "client_message_id"),
    )
    op.create_index("ix_messages_room_id", "messages", ["room_id"])
    rooms = sa.table(
        "rooms",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("kind", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(rooms, [{"id": "general", "name": "general", "kind": "general", "created_at": datetime.now(timezone.utc)}])


def downgrade() -> None:
    op.drop_index("ix_messages_room_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index("ix_memberships_room_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("rooms")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
