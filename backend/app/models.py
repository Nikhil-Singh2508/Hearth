import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    owner = "owner"
    tenant = "tenant"


class TenancyStatus(str, enum.Enum):
    active = "active"
    closed = "closed"
    cancelled = "cancelled"


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), default=Role.tenant)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Property(Base):
    __tablename__ = "properties"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (UniqueConstraint("property_id", "unit_number", name="uq_unit_property_number"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    unit_number: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TenantProfile(Base):
    __tablename__ = "tenant_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(160))


class TenantNotificationPreference(Base):
    __tablename__ = "tenant_notification_preferences"
    __table_args__ = (
        CheckConstraint("NOT email_enabled OR email_consent_at IS NOT NULL", name="ck_notification_email_consent"),
        CheckConstraint("NOT whatsapp_enabled OR (whatsapp_phone IS NOT NULL AND whatsapp_consent_at IS NOT NULL)",
                        name="ck_notification_whatsapp_consent"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    email_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    whatsapp_phone: Mapped[str | None] = mapped_column(String(20))
    whatsapp_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str] = mapped_column(String(32), default="notification-consent-v1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class NotificationConsentEvent(Base):
    __tablename__ = "notification_consent_events"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'whatsapp')", name="ck_notification_consent_channel"),
        CheckConstraint("action IN ('granted', 'revoked')", name="ck_notification_consent_action"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(16))
    consent_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class TenantInvitation(Base):
    __tablename__ = "tenant_invitations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Tenancy(Base):
    __tablename__ = "tenancies"
    __table_args__ = (CheckConstraint("security_deposit_expected >= 0", name="ck_tenancy_security_deposit_nonnegative"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    security_deposit_expected: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    status: Mapped[TenancyStatus] = mapped_column(Enum(TenancyStatus, name="tenancy_status"), default=TenancyStatus.active)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TenancyTenant(Base):
    __tablename__ = "tenancy_tenants"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    financially_responsible: Mapped[bool] = mapped_column(Boolean, default=False)


class RentTerm(Base):
    __tablename__ = "rent_terms"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    due_day: Mapped[int] = mapped_column()
    proration_method: Mapped[str] = mapped_column(String(12), default="actual")


class LateFeeRule(Base):
    __tablename__ = "late_fee_rules"
    __table_args__ = (
        CheckConstraint("fee_type IN ('fixed', 'daily', 'percentage')", name="ck_late_fee_rule_type"),
        CheckConstraint("amount >= 0", name="ck_late_fee_rule_nonnegative_amount"),
        CheckConstraint("grace_days BETWEEN 0 AND 365", name="ck_late_fee_rule_grace_days"),
        CheckConstraint("cap IS NULL OR cap >= 0", name="ck_late_fee_rule_nonnegative_cap"),
        CheckConstraint("partial_payment_basis IN ('remaining_principal', 'original_principal')", name="ck_late_fee_rule_basis"),
        CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_late_fee_rule_valid_period"),
        UniqueConstraint("tenancy_id", "effective_from", name="uq_late_fee_rule_tenancy_start"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    fee_type: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    grace_days: Mapped[int] = mapped_column()
    cap: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    partial_payment_basis: Mapped[str] = mapped_column(String(24), default="remaining_principal")
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Charge(Base):
    __tablename__ = "charges"
    __table_args__ = (
        CheckConstraint("period_end > period_start", name="ck_charge_valid_period"),
        CheckConstraint("amount > 0", name="ck_charge_positive_amount"),
        CheckConstraint("charge_type IN ('rent', 'late_fee', 'utility', 'other')", name="ck_charge_type"),
        Index("uq_rent_charge_tenancy_period", "tenancy_id", "period_start", unique=True,
              postgresql_where=text("charge_type = 'rent'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    charge_type: Mapped[str] = mapped_column(String(24))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    calculation_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class LateFeeAssessment(Base):
    __tablename__ = "late_fee_assessments"
    __table_args__ = (
        UniqueConstraint("rent_charge_id", "as_of_date", name="uq_late_fee_assessment_charge_date"),
        CheckConstraint("days_past_due > 0", name="ck_late_fee_assessment_days"),
        CheckConstraint("principal_remaining >= 0 AND calculation_principal >= 0", name="ck_late_fee_assessment_principal"),
        CheckConstraint("cumulative_target >= 0 AND fee_amount >= 0", name="ck_late_fee_assessment_amounts"),
        CheckConstraint("fee_amount = 0 OR fee_charge_id IS NOT NULL", name="ck_late_fee_assessment_fee_charge"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rent_charge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charges.id", ondelete="RESTRICT"), index=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("late_fee_rules.id", ondelete="RESTRICT"))
    fee_charge_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("charges.id", ondelete="RESTRICT"), unique=True)
    as_of_date: Mapped[date] = mapped_column(Date)
    days_past_due: Mapped[int] = mapped_column()
    principal_remaining: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    calculation_principal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cumulative_target: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payment_idempotency"),
        CheckConstraint("amount > 0", name="ck_payment_positive_amount"),
        CheckConstraint("method IN ('cash', 'upi', 'bank_transfer', 'other')", name="ck_payment_method"),
        CheckConstraint("currency = 'INR'", name="ck_payment_currency"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    method: Mapped[str] = mapped_column(String(24))
    reference_code: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class PaymentReversal(Base):
    __tablename__ = "payment_reversals"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payment_reversal_positive_amount"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(String(500))
    reversed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SecurityDepositTransaction(Base):
    __tablename__ = "security_deposit_transactions"
    __table_args__ = (
        CheckConstraint("transaction_type IN ('receipt', 'refund', 'deduction')", name="ck_deposit_transaction_type"),
        CheckConstraint("amount > 0", name="ck_deposit_transaction_positive_amount"),
        CheckConstraint("(transaction_type = 'deduction' AND method IS NULL) OR (transaction_type IN ('receipt', 'refund') AND method IS NOT NULL AND method IN ('cash', 'upi', 'bank_transfer', 'other'))", name="ck_deposit_transaction_method"),
        CheckConstraint("transaction_type = 'receipt' OR (reason IS NOT NULL AND length(trim(reason)) >= 3)", name="ck_deposit_transaction_reason"),
        UniqueConstraint("idempotency_key", name="uq_deposit_transaction_idempotency"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    transaction_type: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str | None] = mapped_column(String(24))
    reference_code: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class UtilityMeter(Base):
    __tablename__ = "utility_meters"
    __table_args__ = (
        CheckConstraint("utility_type IN ('electricity', 'water', 'gas')", name="ck_utility_meter_type"),
        UniqueConstraint("property_id", "meter_name", name="uq_utility_meter_property_name"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), index=True)
    utility_type: Mapped[str] = mapped_column(String(24))
    meter_name: Mapped[str] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(80))
    unit_of_measure: Mapped[str] = mapped_column(String(24))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class UtilityRate(Base):
    __tablename__ = "utility_rates"
    __table_args__ = (
        CheckConstraint("rate_per_unit >= 0 AND fixed_charge >= 0", name="ck_utility_rate_nonnegative"),
        CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_utility_rate_valid_period"),
        CheckConstraint("utility_type IN ('electricity', 'water', 'gas')", name="ck_utility_rate_type"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), index=True)
    utility_type: Mapped[str] = mapped_column(String(24))
    rate_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    fixed_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class UtilityMeterReading(Base):
    __tablename__ = "utility_meter_readings"
    __table_args__ = (
        UniqueConstraint("meter_id", "read_on", name="uq_utility_meter_reading_date"),
        CheckConstraint("reading >= 0 AND consumption >= 0", name="ck_utility_reading_nonnegative"),
        CheckConstraint("calculated_amount IS NULL OR calculated_amount > 0", name="ck_utility_reading_bill_amount"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utility_meters.id", ondelete="RESTRICT"), index=True)
    read_on: Mapped[date] = mapped_column(Date)
    reading: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    previous_reading_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("utility_meter_readings.id", ondelete="RESTRICT"))
    consumption: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    rate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("utility_rates.id", ondelete="RESTRICT"))
    calculated_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    utility_bill_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("utility_bills.id", ondelete="RESTRICT"), unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class UtilityBill(Base):
    __tablename__ = "utility_bills"
    __table_args__ = (
        CheckConstraint("period_end > period_start", name="ck_utility_bill_valid_period"),
        CheckConstraint("amount > 0", name="ck_utility_bill_positive_amount"),
        CheckConstraint("utility_type IN ('electricity', 'water', 'gas', 'internet', 'other')", name="ck_utility_bill_type"),
        CheckConstraint("status IN ('pending', 'posted')", name="ck_utility_bill_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), index=True)
    utility_type: Mapped[str] = mapped_column(String(24))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    supplier: Mapped[str] = mapped_column(String(160))
    bill_reference: Mapped[str | None] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class UtilityAllocation(Base):
    __tablename__ = "utility_allocations"
    __table_args__ = (
        UniqueConstraint("bill_id", "tenancy_id", name="uq_utility_allocation_bill_tenancy"),
        UniqueConstraint("charge_id", name="uq_utility_allocation_charge"),
        CheckConstraint("amount > 0", name="ck_utility_allocation_positive_amount"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utility_bills.id", ondelete="RESTRICT"), index=True)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    charge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charges.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class PropertyExpense(Base):
    __tablename__ = "property_expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_property_expense_positive_amount"),
        CheckConstraint("category IN ('repairs', 'tax', 'insurance', 'supplies', 'management', 'other')", name="ck_property_expense_category"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), index=True)
    category: Mapped[str] = mapped_column(String(24))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    spent_on: Mapped[date] = mapped_column(Date)
    vendor: Mapped[str] = mapped_column(String(160))
    reference_code: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(1000))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payment_allocation_positive"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), index=True)
    charge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charges.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class TenantCredit(Base):
    __tablename__ = "tenant_credits"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_tenant_credit_positive"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), unique=True)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CreditAllocation(Base):
    __tablename__ = "credit_allocations"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_credit_allocation_positive"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant_credits.id", ondelete="RESTRICT"), index=True)
    charge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charges.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'in_progress', 'resolved', 'closed')", name="ck_maintenance_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    subject: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class TenancyDocument(Base):
    __tablename__ = "tenancy_documents"
    __table_args__ = (
        CheckConstraint("content_type = 'application/pdf'", name="ck_tenancy_document_pdf_only"),
        CheckConstraint("byte_size > 0 AND byte_size <= 10485760", name="ck_tenancy_document_size"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64), default="application/pdf")
    byte_size: Mapped[int] = mapped_column()
    tenant_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint("inspection_type IN ('move_in', 'move_out')", name="ck_inspection_type"),
        CheckConstraint("status IN ('in_progress', 'completed')", name="ck_inspection_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenancies.id", ondelete="RESTRICT"), index=True)
    inspection_type: Mapped[str] = mapped_column(String(16))
    inspected_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(2000))
    tenant_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class InspectionItem(Base):
    __tablename__ = "inspection_items"
    __table_args__ = (
        CheckConstraint("condition IN ('good', 'fair', 'needs_attention', 'not_inspected')", name="ck_inspection_item_condition"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inspection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inspections.id", ondelete="RESTRICT"), index=True)
    area: Mapped[str] = mapped_column(String(120))
    item_name: Mapped[str] = mapped_column(String(160))
    condition: Mapped[str] = mapped_column(String(24))
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class InspectionMedia(Base):
    __tablename__ = "inspection_media"
    __table_args__ = (
        CheckConstraint("content_type IN ('application/pdf', 'image/jpeg', 'image/png')", name="ck_inspection_media_type"),
        CheckConstraint("byte_size > 0 AND byte_size <= 10485760", name="ck_inspection_media_size"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inspection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inspections.id", ondelete="RESTRICT"), index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inspection_items.id", ondelete="RESTRICT"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
