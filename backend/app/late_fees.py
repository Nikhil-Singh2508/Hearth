"""Effective-dated fee rules and immutable assessments against unpaid rent principal."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ledger import LedgerError, outstanding_charge
from app.models import AuditLog, Charge, LateFeeAssessment, LateFeeRule, Tenancy
from app.rent_math import LateFeeRule as FeeCalculationRule
from app.rent_math import late_fee


def active_late_fee_rule(db: Session, tenancy_id: UUID, as_of_date: date) -> LateFeeRule | None:
    return db.scalar(select(LateFeeRule).where(
        LateFeeRule.tenancy_id == tenancy_id,
        LateFeeRule.effective_from <= as_of_date,
        (LateFeeRule.effective_to.is_(None) | (LateFeeRule.effective_to > as_of_date)),
    ).order_by(LateFeeRule.effective_from.desc()).limit(1))


def save_late_fee_rule(db: Session, *, tenancy_id: UUID, actor_id: UUID, fee_type: str,
                       amount: Decimal, grace_days: int, cap: Decimal | None,
                       partial_payment_basis: str, effective_from: date) -> LateFeeRule:
    if fee_type not in {"fixed", "daily", "percentage"}:
        raise LedgerError("Unsupported late fee type")
    if amount < 0 or grace_days < 0 or grace_days > 365 or (cap is not None and cap < 0):
        raise LedgerError("Invalid late fee amount, grace period, or cap")
    if fee_type == "percentage" and amount > 100:
        raise LedgerError("Percentage late fee cannot exceed 100 percent")
    if partial_payment_basis not in {"remaining_principal", "original_principal"}:
        raise LedgerError("Unsupported partial-payment basis")
    tenancy = db.scalar(select(Tenancy).where(Tenancy.id == tenancy_id).with_for_update())
    if tenancy is None:
        raise LedgerError("Tenancy not found")
    today = date.today()
    if effective_from < today:
        raise LedgerError("Late fee rules cannot be backdated")

    same_start = db.scalar(select(LateFeeRule).where(
        LateFeeRule.tenancy_id == tenancy_id, LateFeeRule.effective_from == effective_from
    ).with_for_update())
    if same_start is not None:
        used = db.scalar(select(LateFeeAssessment.id).where(LateFeeAssessment.rule_id == same_start.id).limit(1))
        if used:
            raise LedgerError("A late fee rule with assessments cannot be edited; choose a later effective date")
        same_start.fee_type = fee_type
        same_start.amount = amount
        same_start.grace_days = grace_days
        same_start.cap = cap
        same_start.partial_payment_basis = partial_payment_basis
        db.add(AuditLog(actor_id=actor_id, action="late_fee.rule_updated", target_type="late_fee_rule",
                        target_id=str(same_start.id)))
        db.flush()
        return same_start

    previous = db.scalar(select(LateFeeRule).where(
        LateFeeRule.tenancy_id == tenancy_id, LateFeeRule.effective_from < effective_from,
        (LateFeeRule.effective_to.is_(None) | (LateFeeRule.effective_to > effective_from)),
    ).order_by(LateFeeRule.effective_from.desc()).limit(1).with_for_update())
    if previous is not None:
        previous.effective_to = effective_from
    following = db.scalar(select(LateFeeRule.effective_from).where(
        LateFeeRule.tenancy_id == tenancy_id, LateFeeRule.effective_from > effective_from
    ).order_by(LateFeeRule.effective_from).limit(1))
    rule = LateFeeRule(tenancy_id=tenancy_id, fee_type=fee_type, amount=amount,
        grace_days=grace_days, cap=cap, partial_payment_basis=partial_payment_basis,
        effective_from=effective_from, effective_to=following, created_by=actor_id)
    db.add(rule)
    db.flush()
    db.add(AuditLog(actor_id=actor_id, action="late_fee.rule_created", target_type="late_fee_rule",
                    target_id=str(rule.id)))
    return rule


def assess_late_fee(db: Session, *, rent_charge_id: UUID, as_of_date: date,
                    actor_id: UUID) -> tuple[LateFeeAssessment, Charge | None, bool]:
    rent_charge = db.scalar(select(Charge).where(
        Charge.id == rent_charge_id, Charge.charge_type == "rent").with_for_update())
    if rent_charge is None:
        raise LedgerError("Unpaid rent charge not found")
    existing = db.scalar(select(LateFeeAssessment).where(
        LateFeeAssessment.rent_charge_id == rent_charge.id,
        LateFeeAssessment.as_of_date == as_of_date))
    if existing is not None:
        fee_charge = db.get(Charge, existing.fee_charge_id) if existing.fee_charge_id else None
        return existing, fee_charge, False
    if as_of_date <= rent_charge.due_date:
        raise LedgerError("Late fees can only be assessed after the rent due date")
    prior_date = db.scalar(select(func.max(LateFeeAssessment.as_of_date)).where(
        LateFeeAssessment.rent_charge_id == rent_charge.id))
    if prior_date is not None and as_of_date < prior_date:
        raise LedgerError("Late fee assessments must be posted in date order")
    tenancy = db.scalar(select(Tenancy).where(Tenancy.id == rent_charge.tenancy_id).with_for_update())
    if tenancy is None:
        raise LedgerError("Tenancy not found")
    rule = active_late_fee_rule(db, tenancy.id, as_of_date)
    if rule is None or rule.amount == 0:
        raise LedgerError("No late fee rule is effective for this date")

    principal = outstanding_charge(db, rent_charge)
    if principal <= 0:
        raise LedgerError("Rent principal has been paid; no late fee is due")
    days_past_due = (as_of_date - rent_charge.due_date).days
    calculation_principal = (rent_charge.amount if rule.partial_payment_basis == "original_principal"
                             else principal)
    calculator_rule = FeeCalculationRule(kind=rule.fee_type, amount=rule.amount,
                                         grace_days=rule.grace_days, cap=rule.cap)
    cumulative_target = late_fee(calculation_principal, days_past_due, calculator_rule)
    assessed_before = db.scalar(select(func.coalesce(func.sum(LateFeeAssessment.fee_amount), 0)).where(
        LateFeeAssessment.rent_charge_id == rent_charge.id)) or Decimal("0.00")
    fee_amount = max(Decimal("0.00"), cumulative_target - Decimal(assessed_before))
    fee_charge = None
    if fee_amount > 0:
        snapshot = {"rent_charge_id": str(rent_charge.id), "late_fee_rule_id": str(rule.id),
                    "fee_type": rule.fee_type, "configured_amount": str(rule.amount),
                    "grace_days": rule.grace_days, "cap": str(rule.cap) if rule.cap is not None else None,
                    "partial_payment_basis": rule.partial_payment_basis,
                    "principal_remaining": str(principal), "calculation_principal": str(calculation_principal),
                    "days_past_due": days_past_due, "cumulative_target": str(cumulative_target),
                    "as_of_date": as_of_date.isoformat(), "currency": rent_charge.currency}
        fee_charge = Charge(tenancy_id=rent_charge.tenancy_id, charge_type="late_fee",
            period_start=rent_charge.period_start, period_end=rent_charge.period_end,
            due_date=as_of_date, amount=fee_amount, currency=rent_charge.currency,
            calculation_snapshot=snapshot, created_by=actor_id)
        db.add(fee_charge)
        db.flush()
    assessment = LateFeeAssessment(rent_charge_id=rent_charge.id, rule_id=rule.id,
        fee_charge_id=fee_charge.id if fee_charge else None, as_of_date=as_of_date,
        days_past_due=days_past_due, principal_remaining=principal,
        calculation_principal=calculation_principal, cumulative_target=cumulative_target,
        fee_amount=fee_amount)
    db.add(assessment)
    db.add(AuditLog(actor_id=actor_id, action="late_fee.assessed", target_type="charge",
                    target_id=str(rent_charge.id)))
    db.flush()
    return assessment, fee_charge, True
