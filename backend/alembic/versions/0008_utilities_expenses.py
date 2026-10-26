"""Track utility bills, reconciled allocations and property expenses."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_utilities_expenses"
down_revision = "0007_security_deposits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_charge_tenancy_type_period", "charges", type_="unique")
    op.create_index("uq_rent_charge_tenancy_period", "charges", ["tenancy_id", "period_start"],
                    unique=True, postgresql_where=sa.text("charge_type = 'rent'"))
    op.create_table(
        "utility_bills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="RESTRICT")),
        sa.Column("utility_type", sa.String(24), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("supplier", sa.String(160), nullable=False),
        sa.Column("bill_reference", sa.String(80)),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("period_end > period_start", name="ck_utility_bill_valid_period"),
        sa.CheckConstraint("amount > 0", name="ck_utility_bill_positive_amount"),
        sa.CheckConstraint("utility_type IN ('electricity', 'water', 'gas', 'internet', 'other')", name="ck_utility_bill_type"),
        sa.CheckConstraint("status IN ('pending', 'posted')", name="ck_utility_bill_status"),
    )
    op.create_index("ix_utility_bills_property_id", "utility_bills", ["property_id"])
    op.create_index("ix_utility_bills_unit_id", "utility_bills", ["unit_id"])
    op.create_index("ix_utility_bills_created_at", "utility_bills", ["created_at"])
    op.create_table(
        "utility_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("bill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("utility_bills.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("charge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("charges.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint("bill_id", "tenancy_id", name="uq_utility_allocation_bill_tenancy"),
        sa.UniqueConstraint("charge_id", name="uq_utility_allocation_charge"),
        sa.CheckConstraint("amount > 0", name="ck_utility_allocation_positive_amount"),
    )
    op.create_index("ix_utility_allocations_bill_id", "utility_allocations", ["bill_id"])
    op.create_index("ix_utility_allocations_tenancy_id", "utility_allocations", ["tenancy_id"])
    op.create_table(
        "property_expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="RESTRICT")),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("vendor", sa.String(160), nullable=False),
        sa.Column("reference_code", sa.String(80)),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_property_expense_positive_amount"),
        sa.CheckConstraint("category IN ('repairs', 'tax', 'insurance', 'supplies', 'management', 'other')", name="ck_property_expense_category"),
    )
    op.create_index("ix_property_expenses_property_id", "property_expenses", ["property_id"])
    op.create_index("ix_property_expenses_unit_id", "property_expenses", ["unit_id"])
    op.create_index("ix_property_expenses_created_at", "property_expenses", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_property_expenses_created_at", table_name="property_expenses")
    op.drop_index("ix_property_expenses_unit_id", table_name="property_expenses")
    op.drop_index("ix_property_expenses_property_id", table_name="property_expenses")
    op.drop_table("property_expenses")
    op.drop_index("ix_utility_allocations_tenancy_id", table_name="utility_allocations")
    op.drop_index("ix_utility_allocations_bill_id", table_name="utility_allocations")
    op.drop_table("utility_allocations")
    op.drop_index("ix_utility_bills_created_at", table_name="utility_bills")
    op.drop_index("ix_utility_bills_unit_id", table_name="utility_bills")
    op.drop_index("ix_utility_bills_property_id", table_name="utility_bills")
    op.drop_table("utility_bills")
    op.drop_index("uq_rent_charge_tenancy_period", table_name="charges")
    op.create_unique_constraint("uq_charge_tenancy_type_period", "charges",
                                 ["tenancy_id", "charge_type", "period_start"])
