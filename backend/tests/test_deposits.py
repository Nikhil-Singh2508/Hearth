from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.deposits import record_deposit_transaction
from app.ledger import LedgerError
from app.models import TenancyStatus


class DepositDb:
    def __init__(self, tenancy_status=TenancyStatus.active, expected=Decimal("1000.00"), totals=None):
        self.values = [SimpleNamespace(status=tenancy_status, security_deposit_expected=expected), None]
        self.rows = totals or []
        self.added = []

    def scalar(self, _query):
        return self.values.pop(0)

    def execute(self, _query):
        return SimpleNamespace(all=lambda: self.rows)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        pass


def record(db, kind, amount, method="upi", reason=None):
    return record_deposit_transaction(db, tenancy_id="tenancy", actor_id="owner", transaction_type=kind,
        amount=Decimal(amount), method=method, reference_code=None, reason=reason,
        occurred_at=datetime.now(timezone.utc), idempotency_key="deposit-key-1", request_hash="hash")


def test_deposit_receipt_cannot_exceed_agreed_amount():
    db = DepositDb(expected=Decimal("500.00"))
    with pytest.raises(LedgerError, match="agreed security deposit"):
        record(db, "receipt", "500.01")


def test_deposit_receipt_is_an_immutable_positive_transaction():
    transaction, created = record(DepositDb(), "receipt", "250.00")
    assert created
    assert transaction.amount == Decimal("250.00")
    assert transaction.transaction_type == "receipt"
    assert len(transaction.request_hash) == 4


def test_move_out_deduction_requires_closed_tenancy_and_reason():
    closed = DepositDb(TenancyStatus.closed, totals=[("receipt", Decimal("500.00"))])
    with pytest.raises(LedgerError, match="reason"):
        record(closed, "deduction", "100.00", method=None, reason=" ")

    active = DepositDb(TenancyStatus.active, totals=[("receipt", Decimal("500.00"))])
    with pytest.raises(LedgerError, match="after the tenancy is closed"):
        record(active, "deduction", "100.00", method=None, reason="Repairs")


def test_refund_and_deduction_cannot_exceed_remaining_deposit():
    db = DepositDb(TenancyStatus.closed, totals=[("receipt", Decimal("500.00")), ("refund", Decimal("100.00"))])
    with pytest.raises(LedgerError, match="remaining deposit balance"):
        record(db, "deduction", "400.01", method=None, reason="Repairs")
