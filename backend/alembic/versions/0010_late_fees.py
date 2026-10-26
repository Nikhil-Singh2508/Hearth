"""Add effective-dated late-fee rules and idempotent assessments."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_late_fees"
down_revision = "0009_inspections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "late_fee_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fee_type", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("grace_days", sa.Integer(), nullable=False),
        sa.Column("cap", sa.Numeric(12, 2)),
        sa.Column("partial_payment_basis", sa.String(24), nullable=False, server_default="remaining_principal"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("fee_type IN ('fixed', 'daily', 'percentage')", name="ck_late_fee_rule_type"),
        sa.CheckConstraint("amount >= 0", name="ck_late_fee_rule_nonnegative_amount"),
        sa.CheckConstraint("grace_days BETWEEN 0 AND 365", name="ck_late_fee_rule_grace_days"),
        sa.CheckConstraint("cap IS NULL OR cap >= 0", name="ck_late_fee_rule_nonnegative_cap"),
        sa.CheckConstraint("partial_payment_basis IN ('remaining_principal', 'original_principal')", name="ck_late_fee_rule_basis"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_late_fee_rule_valid_period"),
        sa.UniqueConstraint("tenancy_id", "effective_from", name="uq_late_fee_rule_tenancy_start"),
    )
    op.create_index("ix_late_fee_rules_tenancy_id", "late_fee_rules", ["tenancy_id"])
    op.create_table(
        "late_fee_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("rent_charge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("charges.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("late_fee_rules.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fee_charge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("charges.id", ondelete="RESTRICT"), unique=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("days_past_due", sa.Integer(), nullable=False),
        sa.Column("principal_remaining", sa.Numeric(12, 2), nullable=False),
        sa.Column("calculation_principal", sa.Numeric(12, 2), nullable=False),
        sa.Column("cumulative_target", sa.Numeric(12, 2), nullable=False),
        sa.Column("fee_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("days_past_due > 0", name="ck_late_fee_assessment_days"),
        sa.CheckConstraint("principal_remaining >= 0 AND calculation_principal >= 0", name="ck_late_fee_assessment_principal"),
        sa.CheckConstraint("cumulative_target >= 0 AND fee_amount >= 0", name="ck_late_fee_assessment_amounts"),
        sa.CheckConstraint("fee_amount = 0 OR fee_charge_id IS NOT NULL", name="ck_late_fee_assessment_fee_charge"),
        sa.UniqueConstraint("rent_charge_id", "as_of_date", name="uq_late_fee_assessment_charge_date"),
    )
    op.create_index("ix_late_fee_assessments_rent_charge_id", "late_fee_assessments", ["rent_charge_id"])
    op.create_index("ix_late_fee_assessments_created_at", "late_fee_assessments", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_late_fee_assessments_created_at", table_name="late_fee_assessments")
    op.drop_index("ix_late_fee_assessments_rent_charge_id", table_name="late_fee_assessments")
    op.drop_table("late_fee_assessments")
    op.drop_index("ix_late_fee_rules_tenancy_id", table_name="late_fee_rules")
    op.drop_table("late_fee_rules")
