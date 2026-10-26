"""Persist tenant notification preferences and consent events."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_notification_preferences"
down_revision = "0011_utility_meters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_notification_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("email_enabled", sa.Boolean(), nullable=False),
        sa.Column("email_consent_at", sa.DateTime(timezone=True)),
        sa.Column("whatsapp_enabled", sa.Boolean(), nullable=False),
        sa.Column("whatsapp_phone", sa.String(20)),
        sa.Column("whatsapp_consent_at", sa.DateTime(timezone=True)),
        sa.Column("consent_version", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("NOT email_enabled OR email_consent_at IS NOT NULL", name="ck_notification_email_consent"),
        sa.CheckConstraint("NOT whatsapp_enabled OR (whatsapp_phone IS NOT NULL AND whatsapp_consent_at IS NOT NULL)",
                           name="ck_notification_whatsapp_consent"),
    )
    op.create_table(
        "notification_consent_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("consent_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("channel IN ('email', 'whatsapp')", name="ck_notification_consent_channel"),
        sa.CheckConstraint("action IN ('granted', 'revoked')", name="ck_notification_consent_action"),
    )
    op.create_index("ix_notification_consent_events_user_id", "notification_consent_events", ["user_id"])
    op.create_index("ix_notification_consent_events_created_at", "notification_consent_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_consent_events_created_at", table_name="notification_consent_events")
    op.drop_index("ix_notification_consent_events_user_id", table_name="notification_consent_events")
    op.drop_table("notification_consent_events")
    op.drop_table("tenant_notification_preferences")
