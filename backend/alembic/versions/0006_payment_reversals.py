"""Audited full reversals for unallocated tenant payments."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_payment_reversals"
down_revision = "0005_tenancy_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_reversals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("reversed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payment_reversal_positive_amount"),
    )
    op.create_index("ix_payment_reversals_created_at", "payment_reversals", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_payment_reversals_created_at", table_name="payment_reversals")
    op.drop_table("payment_reversals")
