from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import TenancyStatus
from app.utilities import UtilityError, allocate_utility_bill


class UtilityDb:
    def __init__(self, bill, tenancies, units):
        self.values = [bill, *tenancies]
        self.units = iter(units)
        self.added = []

    def scalar(self, _query):
        return self.values.pop(0)

    def get(self, _model, _identifier):
        return next(self.units)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        pass


def fixtures(amount=Decimal("100.00")):
    bill = SimpleNamespace(id="bill", status="pending", amount=amount, property_id="property",
                           unit_id=None, period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
                           due_date=date(2026, 2, 10), utility_type="electricity", supplier="Power Co",
                           bill_reference="B-1")
    tenancy = SimpleNamespace(id="tenancy", unit_id="unit", start_date=date(2025, 1, 1),
                              end_date=None, status=TenancyStatus.active)
    unit = SimpleNamespace(property_id="property")
    return bill, tenancy, unit


def test_utility_bill_allocation_must_reconcile_exactly():
    bill, tenancy, unit = fixtures()
    db = UtilityDb(bill, [tenancy], [unit])
    with pytest.raises(UtilityError, match="reconcile exactly"):
        allocate_utility_bill(db, bill_id="bill", allocations=[("tenancy", Decimal("99.99"))], actor_id="owner")
    assert not db.added


def test_utility_bill_posts_matching_charge_and_marks_bill_posted():
    bill, tenancy, unit = fixtures()
    db = UtilityDb(bill, [tenancy], [unit])
    allocations = allocate_utility_bill(db, bill_id="bill", allocations=[("tenancy", Decimal("100.00"))], actor_id="owner")
    assert bill.status == "posted"
    assert allocations[0].amount == Decimal("100.00")
    charge = next(row for row in db.added if getattr(row, "charge_type", None) == "utility")
    assert charge.tenancy_id == "tenancy"
    assert charge.amount == Decimal("100.00")
    assert charge.calculation_snapshot["utility_bill_id"] == "bill"


def test_duplicate_tenancy_allocations_rejected():
    bill, _, _ = fixtures()
    db = UtilityDb(bill, [], [])
    with pytest.raises(UtilityError, match="only once"):
        allocate_utility_bill(db, bill_id="bill", allocations=[("tenancy", Decimal("50.00")),
                                                                  ("tenancy", Decimal("50.00"))], actor_id="owner")


def test_charge_model_keeps_monthly_rent_unique_without_blocking_multiple_utilities():
    index = next(index for index in __import__("app.models", fromlist=["Charge"]).Charge.__table__.indexes
                 if index.name == "uq_rent_charge_tenancy_period")
    assert index.unique
    assert "rent" in str(index.dialect_options["postgresql"]["where"])
