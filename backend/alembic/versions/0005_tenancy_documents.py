"""Private PDF documents attached to tenancies."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_tenancy_documents"
down_revision = "0004_maintenance_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenancy_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False, unique=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False, server_default="application/pdf"),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("tenant_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("content_type = 'application/pdf'", name="ck_tenancy_document_pdf_only"),
        sa.CheckConstraint("byte_size > 0 AND byte_size <= 10485760", name="ck_tenancy_document_size"),
    )
    op.create_index("ix_tenancy_documents_tenancy_id", "tenancy_documents", ["tenancy_id"])
    op.create_index("ix_tenancy_documents_created_at", "tenancy_documents", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_tenancy_documents_created_at", table_name="tenancy_documents")
    op.drop_index("ix_tenancy_documents_tenancy_id", table_name="tenancy_documents")
    op.drop_table("tenancy_documents")
