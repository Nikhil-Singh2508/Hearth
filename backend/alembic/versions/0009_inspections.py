"""Add tenancy inspections, checklist items and private evidence metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_inspections"
down_revision = "0008_utilities_expenses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inspections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inspection_type", sa.String(16), nullable=False),
        sa.Column("inspected_on", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(2000)),
        sa.Column("tenant_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(16), nullable=False, server_default="in_progress"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("inspection_type IN ('move_in', 'move_out')", name="ck_inspection_type"),
        sa.CheckConstraint("status IN ('in_progress', 'completed')", name="ck_inspection_status"),
    )
    op.create_index("ix_inspections_tenancy_id", "inspections", ["tenancy_id"])
    op.create_index("ix_inspections_created_at", "inspections", ["created_at"])
    op.create_table(
        "inspection_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("area", sa.String(120), nullable=False),
        sa.Column("item_name", sa.String(160), nullable=False),
        sa.Column("condition", sa.String(24), nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("condition IN ('good', 'fair', 'needs_attention', 'not_inspected')", name="ck_inspection_item_condition"),
    )
    op.create_index("ix_inspection_items_inspection_id", "inspection_items", ["inspection_id"])
    op.create_table(
        "inspection_media",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspection_items.id", ondelete="RESTRICT")),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False, unique=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("content_type IN ('application/pdf', 'image/jpeg', 'image/png')", name="ck_inspection_media_type"),
        sa.CheckConstraint("byte_size > 0 AND byte_size <= 10485760", name="ck_inspection_media_size"),
    )
    op.create_index("ix_inspection_media_inspection_id", "inspection_media", ["inspection_id"])
    op.create_index("ix_inspection_media_item_id", "inspection_media", ["item_id"])
    op.create_index("ix_inspection_media_created_at", "inspection_media", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_inspection_media_created_at", table_name="inspection_media")
    op.drop_index("ix_inspection_media_item_id", table_name="inspection_media")
    op.drop_index("ix_inspection_media_inspection_id", table_name="inspection_media")
    op.drop_table("inspection_media")
    op.drop_index("ix_inspection_items_inspection_id", table_name="inspection_items")
    op.drop_table("inspection_items")
    op.drop_index("ix_inspections_created_at", table_name="inspections")
    op.drop_index("ix_inspections_tenancy_id", table_name="inspections")
    op.drop_table("inspections")
