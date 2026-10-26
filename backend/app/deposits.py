"""Immutable security-deposit accounting for tenancy move-in and move-out."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ledger import IdempotencyConflict, LedgerError
from app.models import (AuditLog, SecurityDepositTransaction, Tenancy, TenancyStatus)
from app.rent_math import money


def deposit_totals(db: Session, tenancy_id: UUID) -> dict[str, Decimal]:
    rows = db.execute(select(SecurityDepositTransaction.transaction_type,
                             func.coalesce(func.sum(SecurityDepositTransaction.amount), 0))
        .where(SecurityDepositTransaction.tenancy_id == tenancy_id)
        .group_by(SecurityDepositTransaction.transaction_type)).all()
    totals = {kind: Decimal(amount) for kind, amount in rows}
    received = totals.get("receipt", Decimal("0.00"))
    refunded = totals.get("refund", Decimal("0.00"))
    deducted = totals.get("deduction", Decimal("0.00"))
    return {"received": money(received), "refunded": money(refunded), "deducted": money(deducted),
            "balance": money(received - refunded - deducted)}


def record_deposit_transaction(db: Session, *, tenancy_id: UUID, actor_id: UUID,
                               transaction_type: str, amount: Decimal, method: str | None,
                               reference_code: str | None, reason: str | None,
                               occurred_at: datetime, idempotency_key: str,
                               request_hash: str) -> tuple[SecurityDepositTransaction, bool]:
    tenancy = db.scalar(select(Tenancy).where(Tenancy.id == tenancy_id).with_for_update())
    if tenancy is None:
        raise LedgerError("Tenancy not found")
    existing = db.scalar(select(SecurityDepositTransaction).where(
        SecurityDepositTransaction.idempotency_key == idempotency_key).with_for_update())
    if existing:
        if existing.request_hash != request_hash:
            raise IdempotencyConflict("Idempotency key was already used for a different deposit transaction")
        if existing.tenancy_id != tenancy_id:
            raise IdempotencyConflict("Idempotency key belongs to a different tenancy")
        return existing, False
    if amount <= 0 or money(amount) != amount:
        raise LedgerError("Deposit transaction must be a positive amount in whole paise")
    if occurred_at.tzinfo is None:
        raise LedgerError("Transaction date must include a timezone")
    totals = deposit_totals(db, tenancy_id)
    if transaction_type == "receipt":
        if tenancy.status is not TenancyStatus.active:
            raise LedgerError("Deposits can only be received for an active tenancy")
        if totals["received"] + amount > tenancy.security_deposit_expected:
            raise LedgerError("Receipt exceeds the agreed security deposit")
    elif transaction_type in {"refund", "deduction"}:
        if tenancy.status is not TenancyStatus.closed:
            raise LedgerError("Refunds and deductions can be recorded after the tenancy is closed")
        if amount > totals["balance"]:
            raise LedgerError("Transaction exceeds the remaining deposit balance")
        if not reason or len(reason.strip()) < 3:
            raise LedgerError("A reason is required for refunds and deductions")
    else:
        raise LedgerError("Unsupported security deposit transaction")
    if transaction_type in {"receipt", "refund"} and method not in {"cash", "upi", "bank_transfer", "other"}:
        raise LedgerError("Choose a valid payment method")
    clean_reason = reason.strip() if reason else None
    transaction = SecurityDepositTransaction(
        tenancy_id=tenancy_id, transaction_type=transaction_type, amount=money(amount),
        method=method if transaction_type in {"receipt", "refund"} else None,
        reference_code=reference_code, reason=clean_reason,
        occurred_at=occurred_at.astimezone(timezone.utc), idempotency_key=idempotency_key,
        request_hash=request_hash, created_by=actor_id,
    )
    db.add(transaction)
    db.flush()
    db.add(AuditLog(actor_id=actor_id, action=f"security_deposit.{transaction_type}",
                    target_type="security_deposit_transaction", target_id=str(transaction.id)))
    db.flush()
    return transaction, True


def deposit_request_hash(data: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
