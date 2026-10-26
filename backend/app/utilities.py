"""Posting manually reconciled utility bills as immutable tenant charges."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (AuditLog, Charge, Tenancy, TenancyStatus, Unit, UtilityAllocation,
                        UtilityBill, UtilityMeter, UtilityMeterReading, UtilityRate)


class UtilityError(ValueError):
    """A utility bill or allocation violates a business rule."""


def record_meter_reading(db: Session, *, meter_id: UUID, read_on: date, reading: Decimal,
                         due_date: date, actor_id: UUID) -> tuple[UtilityMeterReading, UtilityBill | None]:
    meter = db.scalar(select(UtilityMeter).where(UtilityMeter.id == meter_id).with_for_update())
    if meter is None or not meter.active:
        raise UtilityError("Active utility meter not found")
    if reading < 0 or reading.quantize(Decimal("0.001")) != reading:
        raise UtilityError("Meter reading must be nonnegative and have at most three decimal places")
    previous = db.scalar(select(UtilityMeterReading).where(
        UtilityMeterReading.meter_id == meter.id, UtilityMeterReading.read_on < read_on
    ).order_by(UtilityMeterReading.read_on.desc()).limit(1).with_for_update())
    following = db.scalar(select(UtilityMeterReading).where(
        UtilityMeterReading.meter_id == meter.id, UtilityMeterReading.read_on > read_on
    ).order_by(UtilityMeterReading.read_on).limit(1))
    if following:
        raise UtilityError("Meter readings must be recorded in date order")
    if previous and reading < previous.reading:
        raise UtilityError("Meter reading cannot be lower than the previous reading")
    if db.scalar(select(UtilityMeterReading.id).where(
        UtilityMeterReading.meter_id == meter.id, UtilityMeterReading.read_on == read_on
    )):
        raise UtilityError("A meter reading already exists for this date")

    consumption = reading - previous.reading if previous else Decimal("0.000")
    bill = None
    rate = None
    amount = None
    if previous:
        rate = db.scalar(select(UtilityRate).where(
            UtilityRate.property_id == meter.property_id,
            UtilityRate.utility_type == meter.utility_type,
            (UtilityRate.unit_id.is_(None) | (UtilityRate.unit_id == meter.unit_id)),
            UtilityRate.effective_from <= read_on,
            (UtilityRate.effective_to.is_(None) | (UtilityRate.effective_to > read_on)),
        ).order_by(UtilityRate.unit_id.is_not(None).desc(), UtilityRate.effective_from.desc()).limit(1))
        if rate is None:
            raise UtilityError("No utility rate is effective for this meter and reading date")
        amount = (consumption * rate.rate_per_unit + rate.fixed_charge).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        if amount > 0:
            bill = UtilityBill(property_id=meter.property_id, unit_id=meter.unit_id,
            utility_type=meter.utility_type, period_start=previous.read_on, period_end=read_on,
            due_date=due_date, supplier=f"Meter: {meter.meter_name}",
            bill_reference=meter.serial_number, amount=amount,
            notes=f"Consumption {consumption} {meter.unit_of_measure} at {rate.rate_per_unit}/{meter.unit_of_measure}; fixed charge {rate.fixed_charge}.",
            status="pending", created_by=actor_id)
            db.add(bill)
            db.flush()
    current = UtilityMeterReading(meter_id=meter.id, read_on=read_on, reading=reading,
        previous_reading_id=previous.id if previous else None, consumption=consumption,
        rate_id=rate.id if rate else None, calculated_amount=amount if amount and amount > 0 else None,
        utility_bill_id=bill.id if bill else None, created_by=actor_id)
    db.add(current)
    db.flush()
    db.add(AuditLog(actor_id=actor_id, action="utility.meter_reading_recorded",
                    target_type="utility_meter_reading", target_id=str(current.id)))
    if bill:
        db.add(AuditLog(actor_id=actor_id, action="utility.meter_bill_created",
                        target_type="utility_bill", target_id=str(bill.id)))
    return current, bill


def allocate_utility_bill(db: Session, *, bill_id: UUID, allocations: list[tuple[UUID, Decimal]],
                          actor_id: UUID) -> list[UtilityAllocation]:
    bill = db.scalar(select(UtilityBill).where(UtilityBill.id == bill_id).with_for_update())
    if bill is None:
        raise UtilityError("Utility bill not found")
    if bill.status != "pending":
        raise UtilityError("Utility bill has already been posted")
    if not allocations:
        raise UtilityError("At least one tenancy allocation is required")
    if len({tenancy_id for tenancy_id, _ in allocations}) != len(allocations):
        raise UtilityError("Each tenancy can appear only once in an allocation")
    if any(amount <= 0 or amount.quantize(Decimal("0.01")) != amount for _, amount in allocations):
        raise UtilityError("Allocation amounts must be positive whole paise")
    if sum((amount for _, amount in allocations), Decimal("0.00")) != bill.amount:
        raise UtilityError("Allocations must reconcile exactly to the utility bill total")

    results = []
    for tenancy_id, amount in allocations:
        tenancy = db.scalar(select(Tenancy).where(Tenancy.id == tenancy_id).with_for_update())
        if tenancy is None:
            raise UtilityError("Tenancy not found")
        unit = db.get(Unit, tenancy.unit_id)
        if unit is None or unit.property_id != bill.property_id:
            raise UtilityError("Every allocated tenancy must belong to the bill's property")
        if bill.unit_id is not None and tenancy.unit_id != bill.unit_id:
            raise UtilityError("Every allocated tenancy must belong to the bill's apartment")
        tenancy_end = tenancy.end_date or bill.period_end
        if tenancy.start_date >= bill.period_end or tenancy_end <= bill.period_start:
            raise UtilityError("The tenancy must overlap the utility billing period")
        if tenancy.status is TenancyStatus.cancelled:
            raise UtilityError("Cancelled tenancies cannot receive utility charges")

        charge = Charge(
            tenancy_id=tenancy.id, charge_type="utility", period_start=bill.period_start,
            period_end=bill.period_end, due_date=bill.due_date, amount=amount, currency="INR",
            calculation_snapshot={"utility_bill_id": str(bill.id), "utility_type": bill.utility_type,
                                  "supplier": bill.supplier, "bill_reference": bill.bill_reference,
                                  "allocation_amount": str(amount), "period_start": bill.period_start.isoformat(),
                                  "period_end": bill.period_end.isoformat(), "currency": "INR"},
            created_by=actor_id,
        )
        db.add(charge)
        db.flush()
        allocation = UtilityAllocation(bill_id=bill.id, tenancy_id=tenancy.id,
                                       charge_id=charge.id, amount=amount)
        db.add(allocation)
        db.add(AuditLog(actor_id=actor_id, action="utility.bill_allocated",
                        target_type="utility_bill", target_id=str(bill.id)))
        results.append(allocation)
    bill.status = "posted"
    db.flush()
    return results
