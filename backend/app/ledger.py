"""Transactional rent posting and owner-controlled payment/credit allocation."""
import calendar
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (AuditLog, Charge, CreditAllocation, Payment, PaymentAllocation, RentTerm,
                        PaymentReversal, Role, TenantCredit, Tenancy, TenancyStatus, TenancyTenant, User)
from app.rent_math import due_date, money, prorated_rent


class LedgerError(ValueError):
    """A request would violate a ledger business rule."""


class IdempotencyConflict(LedgerError):
    """An idempotency key was reused for a different request."""


def payment_credit_balance(payment_amount: Decimal, allocated_amount: Decimal) -> Decimal:
    if payment_amount <= 0 or allocated_amount < 0 or allocated_amount > payment_amount:
        raise LedgerError("Payment allocations must be between zero and the payment amount")
    return money(payment_amount - allocated_amount)


def validate_allocation(amount: Decimal, available: Decimal, outstanding: Decimal) -> Decimal:
    if amount <= 0 or money(amount) != amount:
        raise LedgerError("Allocation must be a positive amount in whole paise")
    if amount > available:
        raise LedgerError("Allocation exceeds the available tenant credit")
    if amount > outstanding:
        raise LedgerError("Allocation exceeds the remaining charge balance")
    return money(amount)


def _charge_allocated(db: Session, charge_id: UUID) -> Decimal:
    paid = db.scalar(select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
        PaymentAllocation.charge_id == charge_id))
    credited = db.scalar(select(func.coalesce(func.sum(CreditAllocation.amount), 0)).where(
        CreditAllocation.charge_id == charge_id))
    return Decimal(paid) + Decimal(credited)


def outstanding_charge(db: Session, charge: Charge) -> Decimal:
    return money(charge.amount - _charge_allocated(db, charge.id))


def available_credit(db: Session, credit: TenantCredit) -> Decimal:
    reversed_payment = db.scalar(select(PaymentReversal.id).where(PaymentReversal.payment_id == credit.payment_id))
    if reversed_payment:
        return Decimal("0.00")
    allocated = db.scalar(select(func.coalesce(func.sum(CreditAllocation.amount), 0)).where(
        CreditAllocation.credit_id == credit.id))
    return money(credit.amount - Decimal(allocated))


def reverse_payment(db: Session, *, payment_id: UUID, actor_id: UUID, reason: str) -> PaymentReversal:
    """Post one full reversal only while the payment credit is entirely unapplied."""
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise LedgerError("Payment not found")
    credit = db.scalar(select(TenantCredit).where(TenantCredit.payment_id == payment.id).with_for_update())
    if credit is None:
        raise LedgerError("Payment credit not found")
    if db.scalar(select(PaymentReversal.id).where(PaymentReversal.payment_id == payment.id)):
        raise LedgerError("Payment has already been reversed")
    credit_allocated = db.scalar(select(func.coalesce(func.sum(CreditAllocation.amount), 0)).where(
        CreditAllocation.credit_id == credit.id))
    payment_allocated = db.scalar(select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
        PaymentAllocation.payment_id == payment.id))
    if Decimal(credit_allocated) != 0 or Decimal(payment_allocated) != 0:
        raise LedgerError("Payment cannot be reversed after any amount has been allocated")
    clean_reason = reason.strip()
    if not clean_reason:
        raise LedgerError("A reason is required for a payment reversal")
    reversal = PaymentReversal(payment_id=payment.id, amount=payment.amount,
                               reason=clean_reason, reversed_by=actor_id)
    db.add(reversal)
    db.add(AuditLog(actor_id=actor_id, action="payment.reversed", target_type="payment",
                    target_id=str(payment.id)))
    db.flush()
    return reversal


def generate_monthly_rent(db: Session, tenancy_id: UUID, billing_month: date,
                          actor_id: UUID) -> Charge:
    """Post one idempotent monthly rent charge and retain its full calculation snapshot."""
    if billing_month.day != 1:
        raise LedgerError("billing_month must be the first day of a month")
    tenancy = db.scalar(select(Tenancy).where(Tenancy.id == tenancy_id).with_for_update())
    if tenancy is None or tenancy.status is not TenancyStatus.active:
        raise LedgerError("Active tenancy not found")
    existing = db.scalar(select(Charge).where(
        Charge.tenancy_id == tenancy_id, Charge.charge_type == "rent",
        Charge.period_start == billing_month))
    if existing:
        return existing
    next_month = date(billing_month.year + (billing_month.month == 12),
                      1 if billing_month.month == 12 else billing_month.month % 12 + 1, 1)
    active_start = max(tenancy.start_date, billing_month)
    active_end = min(tenancy.end_date or next_month, next_month)
    if active_start >= active_end:
        raise LedgerError("Tenancy is not active during this billing month")
    terms = db.scalars(select(RentTerm).where(
        RentTerm.tenancy_id == tenancy_id,
        RentTerm.effective_from < active_end,
        (RentTerm.effective_to.is_(None) | (RentTerm.effective_to > active_start)),
    ).order_by(RentTerm.effective_from)).all()
    if len(terms) != 1 or terms[0].effective_from > active_start or (
        terms[0].effective_to is not None and terms[0].effective_to < active_end
    ):
        raise LedgerError("A single rent term must cover the billable days in this month")
    term = terms[0]
    billable_days = (active_end - active_start).days
    month_days = calendar.monthrange(billing_month.year, billing_month.month)[1]
    amount, calculation = prorated_rent(term.monthly_rent, billable_days, month_days,
                                         term.proration_method)
    if amount <= 0:
        raise LedgerError("Calculated rent must be positive")
    snapshot = {
        **calculation,
        "tenancy_id": str(tenancy_id),
        "rent_term_id": str(term.id),
        "active_from": active_start.isoformat(),
        "active_to_exclusive": active_end.isoformat(),
        "period_start": billing_month.isoformat(),
        "period_end_exclusive": next_month.isoformat(),
        "due_day": term.due_day,
        "due_date": due_date(billing_month.year, billing_month.month, term.due_day).isoformat(),
        "currency": "INR",
    }
    charge = Charge(tenancy_id=tenancy_id, charge_type="rent", period_start=billing_month,
                    period_end=next_month, due_date=due_date(billing_month.year, billing_month.month,
                                                              term.due_day), amount=amount,
                    currency="INR", calculation_snapshot=snapshot, created_by=actor_id)
    db.add(charge)
    db.flush()
    db.add(AuditLog(actor_id=actor_id, action="rent.charge_posted", target_type="charge",
                    target_id=str(charge.id)))
    return charge


def record_payment(db: Session, *, tenancy_id: UUID, tenant_id: UUID, actor_id: UUID,
                   amount: Decimal, method: str, received_at: datetime,
                   idempotency_key: str, request_hash: str,
                   reference_code: str | None = None) -> tuple[Payment, bool]:
    """Record a manual payment as an unapplied, traceable credit; retries are idempotent."""
    if amount <= 0 or money(amount) != amount:
        raise LedgerError("Payment must be a positive amount in whole paise")
    if method not in {"cash", "upi", "bank_transfer", "other"}:
        raise LedgerError("Unsupported payment method")
    if received_at.tzinfo is None:
        raise LedgerError("received_at must include a timezone")
    tenancy = db.scalar(select(Tenancy).where(Tenancy.id == tenancy_id).with_for_update())
    tenant = db.get(User, tenant_id)
    participation = db.scalar(select(TenancyTenant).where(
        TenancyTenant.tenancy_id == tenancy_id,
        TenancyTenant.user_id == tenant_id,
        TenancyTenant.start_date <= received_at.date(),
        (TenancyTenant.end_date.is_(None) | (TenancyTenant.end_date > received_at.date())),
    ))
    if tenancy is None or tenant is None or tenant.role is not Role.tenant or participation is None:
        raise LedgerError("Tenant is not associated with this tenancy on the payment date")
    existing = db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
    if existing:
        if existing.request_hash != request_hash:
            raise IdempotencyConflict("Idempotency key was already used for a different payment")
        return existing, False
    payment = Payment(tenancy_id=tenancy_id, tenant_id=tenant_id, amount=money(amount),
                      currency="INR", method=method, reference_code=reference_code,
                      idempotency_key=idempotency_key, request_hash=request_hash,
                      received_at=received_at.astimezone(timezone.utc), created_by=actor_id)
    db.add(payment)
    db.flush()
    credit = TenantCredit(payment_id=payment.id, tenancy_id=tenancy_id, tenant_id=tenant_id,
                          amount=money(amount), currency="INR")
    db.add(credit)
    db.add(AuditLog(actor_id=actor_id, action="payment.recorded", target_type="payment",
                    target_id=str(payment.id)))
    db.flush()
    return payment, True


def allocate_credit(db: Session, *, credit_id: UUID, charge_id: UUID, amount: Decimal,
                    actor_id: UUID) -> CreditAllocation:
    """Lock both rows and allocate no more than the credit or charge balance."""
    credit = db.scalar(select(TenantCredit).where(TenantCredit.id == credit_id).with_for_update())
    charge = db.scalar(select(Charge).where(Charge.id == charge_id).with_for_update())
    if credit is None or charge is None or credit.tenancy_id != charge.tenancy_id:
        raise LedgerError("Credit and charge must belong to the same tenancy")
    allocation_amount = validate_allocation(amount, available_credit(db, credit), outstanding_charge(db, charge))
    allocation = CreditAllocation(credit_id=credit_id, charge_id=charge_id, amount=allocation_amount,
                                  created_by=actor_id)
    db.add(allocation)
    db.add(AuditLog(actor_id=actor_id, action="payment.credit_allocated", target_type="credit_allocation",
                    target_id=str(allocation.id)))
    db.flush()
    return allocation
