"""Add utility meters, effective-dated rates and readings."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_utility_meters"
down_revision = "0010_late_fees"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("utility_meters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="RESTRICT")),
        sa.Column("utility_type", sa.String(24), nullable=False), sa.Column("meter_name", sa.String(120), nullable=False),
        sa.Column("serial_number", sa.String(80)), sa.Column("unit_of_measure", sa.String(24), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("utility_type IN ('electricity', 'water', 'gas')", name="ck_utility_meter_type"),
        sa.UniqueConstraint("property_id", "meter_name", name="uq_utility_meter_property_name"))
    op.create_index("ix_utility_meters_property_id", "utility_meters", ["property_id"])
    op.create_index("ix_utility_meters_unit_id", "utility_meters", ["unit_id"])
    op.create_index("ix_utility_meters_created_at", "utility_meters", ["created_at"])
    op.create_table("utility_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="RESTRICT")),
        sa.Column("utility_type", sa.String(24), nullable=False), sa.Column("rate_per_unit", sa.Numeric(12, 4), nullable=False),
        sa.Column("fixed_charge", sa.Numeric(12, 2), nullable=False), sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rate_per_unit >= 0 AND fixed_charge >= 0", name="ck_utility_rate_nonnegative"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_utility_rate_valid_period"),
        sa.CheckConstraint("utility_type IN ('electricity', 'water', 'gas')", name="ck_utility_rate_type"))
    op.create_index("ix_utility_rates_property_id", "utility_rates", ["property_id"])
    op.create_index("ix_utility_rates_unit_id", "utility_rates", ["unit_id"])
    op.create_index("ix_utility_rates_created_at", "utility_rates", ["created_at"])
    op.create_table("utility_meter_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("meter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("utility_meters.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("read_on", sa.Date(), nullable=False), sa.Column("reading", sa.Numeric(14, 3), nullable=False),
        sa.Column("previous_reading_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("utility_meter_readings.id", ondelete="RESTRICT")),
        sa.Column("consumption", sa.Numeric(14, 3), nullable=False),
        sa.Column("rate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("utility_rates.id", ondelete="RESTRICT")),
        sa.Column("calculated_amount", sa.Numeric(12, 2)),
        sa.Column("utility_bill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("utility_bills.id", ondelete="RESTRICT"), unique=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("meter_id", "read_on", name="uq_utility_meter_reading_date"),
        sa.CheckConstraint("reading >= 0 AND consumption >= 0", name="ck_utility_reading_nonnegative"),
        sa.CheckConstraint("calculated_amount IS NULL OR calculated_amount > 0", name="ck_utility_reading_bill_amount"))
    op.create_index("ix_utility_meter_readings_meter_id", "utility_meter_readings", ["meter_id"])
    op.create_index("ix_utility_meter_readings_created_at", "utility_meter_readings", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_utility_meter_readings_created_at", table_name="utility_meter_readings")
    op.drop_index("ix_utility_meter_readings_meter_id", table_name="utility_meter_readings")
    op.drop_table("utility_meter_readings")
    op.drop_index("ix_utility_rates_created_at", table_name="utility_rates")
    op.drop_index("ix_utility_rates_unit_id", table_name="utility_rates")
    op.drop_index("ix_utility_rates_property_id", table_name="utility_rates")
    op.drop_table("utility_rates")
    op.drop_index("ix_utility_meters_created_at", table_name="utility_meters")
    op.drop_index("ix_utility_meters_unit_id", table_name="utility_meters")
    op.drop_index("ix_utility_meters_property_id", table_name="utility_meters")
    op.drop_table("utility_meters")
