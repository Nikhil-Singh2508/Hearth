"""Immutable rent charges, recorded payments and traceable unapplied credits."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_rent_ledger"
down_revision = "0002_tenant_lifecycle"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("charges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("charge_type", sa.String(24), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False), sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False), sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False), sa.Column("calculation_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenancy_id", "charge_type", "period_start", name="uq_charge_tenancy_type_period"),
        sa.CheckConstraint("period_end > period_start", name="ck_charge_valid_period"),
        sa.CheckConstraint("amount > 0", name="ck_charge_positive_amount"),
        sa.CheckConstraint("charge_type IN ('rent', 'late_fee', 'utility', 'other')", name="ck_charge_type"))
    op.create_index("ix_charges_tenancy_id", "charges", ["tenancy_id"])
    op.create_table("payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("method", sa.String(24), nullable=False), sa.Column("reference_code", sa.String(64)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False), sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_idempotency"),
        sa.CheckConstraint("amount > 0", name="ck_payment_positive_amount"),
        sa.CheckConstraint("method IN ('cash', 'upi', 'bank_transfer', 'other')", name="ck_payment_method"),
        sa.CheckConstraint("currency = 'INR'", name="ck_payment_currency"))
    op.create_index("ix_payments_tenancy_id", "payments", ["tenancy_id"])
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"])
    op.create_table("payment_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("charge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("charges.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payment_allocation_positive"))
    op.create_index("ix_payment_allocations_payment_id", "payment_allocations", ["payment_id"])
    op.create_index("ix_payment_allocations_charge_id", "payment_allocations", ["charge_id"])
    op.create_table("tenant_credits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_tenant_credit_positive"))
    op.create_index("ix_tenant_credits_tenancy_id", "tenant_credits", ["tenancy_id"])
    op.create_index("ix_tenant_credits_tenant_id", "tenant_credits", ["tenant_id"])
    op.create_table("credit_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("credit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant_credits.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("charge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("charges.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_credit_allocation_positive"))
    op.create_index("ix_credit_allocations_credit_id", "credit_allocations", ["credit_id"])
    op.create_index("ix_credit_allocations_charge_id", "credit_allocations", ["charge_id"])

def downgrade():
    op.drop_index("ix_credit_allocations_charge_id", table_name="credit_allocations")
    op.drop_index("ix_credit_allocations_credit_id", table_name="credit_allocations")
    op.drop_table("credit_allocations")
    op.drop_index("ix_tenant_credits_tenant_id", table_name="tenant_credits")
    op.drop_index("ix_tenant_credits_tenancy_id", table_name="tenant_credits")
    op.drop_table("tenant_credits")
    op.drop_index("ix_payment_allocations_charge_id", table_name="payment_allocations")
    op.drop_index("ix_payment_allocations_payment_id", table_name="payment_allocations")
    op.drop_table("payment_allocations")
    op.drop_index("ix_payments_tenant_id", table_name="payments")
    op.drop_index("ix_payments_tenancy_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_charges_tenancy_id", table_name="charges")
    op.drop_table("charges")
