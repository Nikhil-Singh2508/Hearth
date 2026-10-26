"""Tenant-submitted maintenance requests."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_maintenance_requests"
down_revision = "0003_rent_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maintenance_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'resolved', 'closed')", name="ck_maintenance_status"),
    )
    op.create_index("ix_maintenance_requests_tenancy_id", "maintenance_requests", ["tenancy_id"])
    op.create_index("ix_maintenance_requests_requester_id", "maintenance_requests", ["requester_id"])
    op.create_index("ix_maintenance_requests_created_at", "maintenance_requests", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_maintenance_requests_created_at", table_name="maintenance_requests")
    op.drop_index("ix_maintenance_requests_requester_id", table_name="maintenance_requests")
    op.drop_index("ix_maintenance_requests_tenancy_id", table_name="maintenance_requests")
    op.drop_table("maintenance_requests")
