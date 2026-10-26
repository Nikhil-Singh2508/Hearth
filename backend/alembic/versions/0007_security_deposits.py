"""Expected security deposit and immutable deposit transactions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_security_deposits"
down_revision = "0006_payment_reversals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenancies", sa.Column("security_deposit_expected", sa.Numeric(12, 2), nullable=False, server_default="0.00"))
    op.create_check_constraint("ck_tenancy_security_deposit_nonnegative", "tenancies", "security_deposit_expected >= 0")
    op.create_table(
        "security_deposit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transaction_type", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(24)),
        sa.Column("reference_code", sa.String(64)),
        sa.Column("reason", sa.String(500)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("transaction_type IN ('receipt', 'refund', 'deduction')", name="ck_deposit_transaction_type"),
        sa.CheckConstraint("amount > 0", name="ck_deposit_transaction_positive_amount"),
        sa.CheckConstraint("(transaction_type = 'deduction' AND method IS NULL) OR (transaction_type IN ('receipt', 'refund') AND method IS NOT NULL AND method IN ('cash', 'upi', 'bank_transfer', 'other'))", name="ck_deposit_transaction_method"),
        sa.CheckConstraint("transaction_type = 'receipt' OR (reason IS NOT NULL AND length(trim(reason)) >= 3)", name="ck_deposit_transaction_reason"),
        sa.UniqueConstraint("idempotency_key", name="uq_deposit_transaction_idempotency"),
    )
    op.create_index("ix_security_deposit_transactions_tenancy_id", "security_deposit_transactions", ["tenancy_id"])
    op.create_index("ix_security_deposit_transactions_created_at", "security_deposit_transactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_security_deposit_transactions_created_at", table_name="security_deposit_transactions")
    op.drop_index("ix_security_deposit_transactions_tenancy_id", table_name="security_deposit_transactions")
    op.drop_table("security_deposit_transactions")
    op.drop_constraint("ck_tenancy_security_deposit_nonnegative", "tenancies", type_="check")
    op.drop_column("tenancies", "security_deposit_expected")
