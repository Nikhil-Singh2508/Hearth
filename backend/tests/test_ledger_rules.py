from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.ledger import LedgerError, payment_credit_balance, reverse_payment, validate_allocation


def test_unapplied_payment_remains_positive_credit():
    assert payment_credit_balance(Decimal("1500.00"), Decimal("400.00")) == Decimal("1100.00")
    assert payment_credit_balance(Decimal("1500.00"), Decimal("1500.00")) == Decimal("0.00")


@pytest.mark.parametrize("amount,available,outstanding", [
    (Decimal("0.00"), Decimal("100.00"), Decimal("100.00")),
    (Decimal("100.01"), Decimal("100.00"), Decimal("200.00")),
    (Decimal("100.00"), Decimal("200.00"), Decimal("99.99")),
])
def test_allocation_rejects_zero_or_overdraw(amount, available, outstanding):
    with pytest.raises(LedgerError):
        validate_allocation(amount, available, outstanding)


def test_allocation_accepts_partial_payment_within_both_balances():
    assert validate_allocation(Decimal("60.50"), Decimal("80.00"), Decimal("100.00")) == Decimal("60.50")


class ReversalDb:
    def __init__(self, credit_allocated=Decimal("0"), payment_allocated=Decimal("0")):
        self.values = [SimpleNamespace(id="payment", amount=Decimal("100.00")),
                       SimpleNamespace(id="credit"), None, credit_allocated, payment_allocated]
        self.added = []

    def scalar(self, _query):
        return self.values.pop(0)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        pass


def test_reversal_is_full_amount_and_keeps_reason_auditable():
    db = ReversalDb()
    reversal = reverse_payment(db, payment_id="payment", actor_id="owner", reason=" Duplicate payment ")
    assert reversal.amount == Decimal("100.00")
    assert reversal.reason == "Duplicate payment"
    assert len(db.added) == 2


def test_reversal_rejects_payment_with_any_credit_allocated():
    with pytest.raises(LedgerError, match="allocated"):
        reverse_payment(ReversalDb(credit_allocated=Decimal("0.01")), payment_id="payment",
                        actor_id="owner", reason="Duplicate payment")
