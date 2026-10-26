import hashlib
import html
import hmac
import json
import os
import secrets
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deposits import (deposit_request_hash, deposit_totals, record_deposit_transaction)
from app.ledger import (IdempotencyConflict, LedgerError, allocate_credit, reverse_payment,
                        generate_monthly_rent, record_payment, outstanding_charge)
from app.late_fees import active_late_fee_rule, assess_late_fee, save_late_fee_rule
from app.inspections import inspection_file_extension
from app.exports import build_csv
from app.reports import next_month, period_bounds, trailing_months
from app.models import (AuditLog, Charge, CreditAllocation, LoginSession, MaintenanceRequest, Payment, PaymentAllocation,
                        PaymentReversal, Property, RentTerm, Role, TenantCredit, TenantInvitation, TenantProfile,
                        SecurityDepositTransaction, Tenancy, TenancyDocument, TenancyStatus, TenancyTenant, Unit, User,
                        UtilityBill, UtilityAllocation, PropertyExpense, UtilityMeter, UtilityRate, UtilityMeterReading,
                        Inspection, InspectionItem, InspectionMedia, TenantNotificationPreference,
                        NotificationConsentEvent,
                        LateFeeRule, LateFeeAssessment)
from app.utilities import UtilityError, allocate_utility_bill, record_meter_reading
from app.schemas import PropertyCreate
from app.settings import settings
from app.notifications import (email_provider_enabled, send_payment_receipt,
                               whatsapp_provider_enabled)
from app.file_storage import (PrivateStorageError, delete_private_file, read_private_file,
                              save_private_file)

router = APIRouter(prefix="/api")


password_hasher = PasswordHasher()


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class InvitationCreate(BaseModel):
    email: EmailStr


class InvitationAccept(BaseModel):
    token: str = Field(min_length=30, max_length=128)
    password: str = Field(min_length=8, max_length=1024)
    display_name: str = Field(min_length=1, max_length=160)

    @field_validator("display_name")
    @classmethod
    def display_name_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a display name")
        return value


class TenancyCreate(BaseModel):
    unit_id: UUID
    tenant_id: UUID
    start_date: date
    end_date: date | None = None
    monthly_rent: Decimal = Field(gt=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)
    security_deposit_expected: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)
    due_day: int = Field(ge=1, le=31)
    proration_method: str = Field(default="actual", pattern="^(actual|30_day)$")


class TenancyClose(BaseModel):
    move_out_date: date


class SecurityDepositExpectedUpdate(BaseModel):
    amount: Decimal = Field(ge=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)


class LateFeeRuleUpdate(BaseModel):
    enabled: bool = True
    fee_type: str = Field(default="fixed", pattern="^(fixed|daily|percentage)$")
    amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)
    grace_days: int = Field(default=0, ge=0, le=365)
    cap: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)
    partial_payment_basis: str = Field(default="remaining_principal", pattern="^(remaining_principal|original_principal)$")
    effective_from: date = Field(default_factory=date.today)


class PaymentCreate(BaseModel):
    tenancy_id: UUID
    tenant_id: UUID
    amount: Decimal = Field(gt=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)
    method: str = Field(pattern="^(cash|upi|bank_transfer|other)$")
    received_at: datetime
    reference_code: str | None = Field(default=None, max_length=64, pattern="^[A-Za-z0-9._-]+$")


class CreditAllocationCreate(BaseModel):
    charge_id: UUID
    amount: Decimal = Field(gt=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)


class PaymentReversalCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_nonblank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Enter a reason for the reversal")
        return value


class SecurityDepositTransactionCreate(BaseModel):
    transaction_type: str = Field(pattern="^(receipt|refund|deduction)$")
    amount: Decimal = Field(gt=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)
    method: str | None = Field(default=None, pattern="^(cash|upi|bank_transfer|other)$")
    reference_code: str | None = Field(default=None, max_length=64, pattern="^[A-Za-z0-9._-]+$")
    reason: str | None = Field(default=None, max_length=500)
    occurred_at: datetime

    @field_validator("reason")
    @classmethod
    def reason_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class MaintenanceRequestCreate(BaseModel):
    tenancy_id: UUID
    subject: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=4000)

    @field_validator("subject", "description")
    @classmethod
    def text_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value


class MaintenanceStatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|in_progress|resolved|closed)$")


class UtilityBillCreate(BaseModel):
    property_id: UUID
    unit_id: UUID | None = None
    utility_type: str = Field(pattern="^(electricity|water|gas|internet|other)$")
    period_start: date
    period_end: date
    due_date: date
    supplier: str = Field(min_length=1, max_length=160)
    bill_reference: str | None = Field(default=None, max_length=80)
    amount: Decimal = Field(gt=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("supplier")
    @classmethod
    def supplier_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Supplier cannot be blank")
        return value.strip()


class UtilityAllocationInput(BaseModel):
    tenancy_id: UUID
    amount: Decimal = Field(gt=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)


class UtilityAllocationCreate(BaseModel):
    allocations: list[UtilityAllocationInput] = Field(min_length=1, max_length=300)


class UtilityMeterCreate(BaseModel):
    property_id: UUID
    unit_id: UUID | None = None
    utility_type: str = Field(pattern="^(electricity|water|gas)$")
    meter_name: str = Field(min_length=1, max_length=120)
    serial_number: str | None = Field(default=None, max_length=80)
    unit_of_measure: str = Field(min_length=1, max_length=24)


class UtilityRateCreate(BaseModel):
    property_id: UUID
    unit_id: UUID | None = None
    utility_type: str = Field(pattern="^(electricity|water|gas)$")
    rate_per_unit: Decimal = Field(ge=Decimal("0"), le=Decimal("1000000"), max_digits=12, decimal_places=4)
    fixed_charge: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)
    effective_from: date


class UtilityMeterReadingCreate(BaseModel):
    read_on: date
    reading: Decimal = Field(ge=Decimal("0"), le=Decimal("100000000000"), max_digits=14, decimal_places=3)
    due_date: date


class NotificationPreferenceUpdate(BaseModel):
    email_enabled: bool = False
    whatsapp_enabled: bool = False
    whatsapp_phone: str | None = Field(default=None, max_length=20, pattern=r"^\+[1-9][0-9]{7,14}$")


class PropertyExpenseCreate(BaseModel):
    property_id: UUID
    unit_id: UUID | None = None
    category: str = Field(pattern="^(repairs|tax|insurance|supplies|management|other)$")
    amount: Decimal = Field(gt=Decimal("0"), le=Decimal("100000000"), max_digits=12, decimal_places=2)
    spent_on: date
    vendor: str = Field(min_length=1, max_length=160)
    reference_code: str | None = Field(default=None, max_length=80)
    description: str = Field(min_length=1, max_length=1000)

    @field_validator("vendor", "description")
    @classmethod
    def expense_text_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field cannot be blank")
        return value.strip()


class InspectionCreate(BaseModel):
    tenancy_id: UUID
    inspection_type: str = Field(pattern="^(move_in|move_out)$")
    inspected_on: date
    notes: str | None = Field(default=None, max_length=2000)
    tenant_visible: bool = True

    @field_validator("notes")
    @classmethod
    def inspection_notes_trimmed(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class InspectionItemCreate(BaseModel):
    area: str = Field(min_length=1, max_length=120)
    item_name: str = Field(min_length=1, max_length=160)
    condition: str = Field(pattern="^(good|fair|needs_attention|not_inspected)$")
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("area", "item_name")
    @classmethod
    def inspection_item_text_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field cannot be blank")
        return value.strip()

    @field_validator("notes")
    @classmethod
    def inspection_item_notes_trimmed(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class PropertyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    address: str | None = Field(default=None, min_length=1, max_length=2000)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("name", "address")
    @classmethod
    def update_text_nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value

    @field_validator("timezone")
    @classmethod
    def update_timezone_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Use a valid IANA timezone") from exc
        return value


class UnitCreate(BaseModel):
    unit_number: str = Field(min_length=1, max_length=80)

    @field_validator("unit_number")
    @classmethod
    def unit_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Apartment identifier cannot be blank")
        return value


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_from_request(request: Request, db: Session) -> LoginSession:
    raw = request.cookies.get("rental_session")
    if not raw:
        raise HTTPException(status_code=401, detail="Authentication required")
    login_session = db.scalar(select(LoginSession).where(LoginSession.token_hash == token_hash(raw)))
    if login_session is None or login_session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Authentication required")
    return login_session


def require_owner(request: Request, db: Session = Depends(get_db)) -> User:
    login_session = session_from_request(request, db)
    user = db.get(User, login_session.user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.role is not Role.owner:
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    login_session = session_from_request(request, db)
    user = db.get(User, login_session.user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def verify_csrf(request: Request, db: Session, login_session: LoginSession) -> None:
    cookie = request.cookies.get("rental_csrf", "")
    header = request.headers.get("x-csrf-token", "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    if not hmac.compare_digest(token_hash(cookie), login_session.csrf_hash):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


@router.post("/auth/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    valid = False
    if user and user.active:
        try:
            valid = password_hasher.verify(user.password_hash, body.password)
        except VerificationError:
            valid = False
    if not valid or user is None:
        # Keep timing similar for unknown accounts and use a generic message.
        if user is None:
            password_hasher.hash(secrets.token_urlsafe(24))
        raise HTTPException(status_code=401, detail="Invalid email or password")
    raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    row = LoginSession(user_id=user.id, token_hash=token_hash(raw), csrf_hash=token_hash(csrf),
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=12))
    db.add(row)
    db.commit()
    response.set_cookie("rental_session", raw, httponly=True, secure=settings.cookie_secure,
                        samesite="strict", max_age=43200, path="/")
    response.set_cookie("rental_csrf", csrf, httponly=False, secure=settings.cookie_secure,
                        samesite="strict", max_age=43200, path="/")
    return {"role": user.role.value, "email": user.email}


@router.get("/auth/me")
def who_am_i(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    session = session_from_request(request, db)
    user = db.get(User, session.user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"role": user.role.value, "email": user.email}


@router.get("/tenant/portal")
def tenant_portal(actor: User = Depends(require_user), db: Session = Depends(get_db)) -> dict[str, object]:
    """Return only records connected to the authenticated tenant account."""
    if actor.role is not Role.tenant:
        raise HTTPException(status_code=403, detail="Forbidden")
    profile = db.get(TenantProfile, actor.id)
    participations = db.execute(
        select(TenancyTenant, Tenancy, Unit, Property)
        .join(Tenancy, Tenancy.id == TenancyTenant.tenancy_id)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .join(Property, Property.id == Unit.property_id)
        .where(TenancyTenant.user_id == actor.id)
        .order_by(Tenancy.start_date.desc())
    ).all()
    tenancies: list[dict[str, object]] = []
    for participation, tenancy, unit, property_row in participations:
        charges = db.scalars(select(Charge).where(Charge.tenancy_id == tenancy.id).order_by(Charge.due_date.desc())).all()
        charge_items = []
        for charge in charges:
            paid = db.scalar(select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
                PaymentAllocation.charge_id == charge.id)) or Decimal("0")
            credited = db.scalar(select(func.coalesce(func.sum(CreditAllocation.amount), 0)).where(
                CreditAllocation.charge_id == charge.id)) or Decimal("0")
            charge_items.append({
                "id": str(charge.id), "type": charge.charge_type,
                "period_start": charge.period_start.isoformat(), "period_end": charge.period_end.isoformat(),
                "due_date": charge.due_date.isoformat(), "amount": str(charge.amount),
                "paid": str(paid + credited), "balance": str(max(Decimal("0"), charge.amount - paid - credited)),
                "currency": charge.currency,
            })
        payments = db.execute(select(Payment, PaymentReversal).outerjoin(
            PaymentReversal, PaymentReversal.payment_id == Payment.id
        ).where(
            Payment.tenancy_id == tenancy.id, Payment.tenant_id == actor.id
        ).order_by(Payment.received_at.desc())).all()
        credits = db.scalars(select(TenantCredit).outerjoin(
            PaymentReversal, PaymentReversal.payment_id == TenantCredit.payment_id
        ).where(
            TenantCredit.tenancy_id == tenancy.id, TenantCredit.tenant_id == actor.id,
            PaymentReversal.id.is_(None),
        ).order_by(TenantCredit.created_at.desc())).all()
        term = db.scalar(select(RentTerm).where(
            RentTerm.tenancy_id == tenancy.id, RentTerm.effective_to.is_(None)
        ).order_by(RentTerm.effective_from.desc()))
        security_deposit_items = db.scalars(select(SecurityDepositTransaction).where(
            SecurityDepositTransaction.tenancy_id == tenancy.id
        ).order_by(SecurityDepositTransaction.occurred_at.desc()).limit(100)).all()
        tenancies.append({
            "id": str(tenancy.id), "status": tenancy.status.value,
            "start_date": tenancy.start_date.isoformat(),
            "end_date": tenancy.end_date.isoformat() if tenancy.end_date else None,
            "unit": unit.unit_number, "property": property_row.name,
            "rent": str(term.monthly_rent) if term else None,
            "rent_currency": term.currency if term else "INR",
            "charges": charge_items,
            "payments": [{"id": str(p.id), "amount": str(p.amount), "currency": p.currency,
                          "method": p.method, "received_at": p.received_at.isoformat(),
                          "status": "reversed" if reversal else "recorded"}
                         for p, reversal in payments],
            "credits": [{
                "id": str(c.id),
                "amount": str(max(Decimal("0"), c.amount - (db.scalar(select(
                    func.coalesce(func.sum(CreditAllocation.amount), 0)
                ).where(CreditAllocation.credit_id == c.id)) or Decimal("0")))),
                "currency": c.currency, "created_at": c.created_at.isoformat(),
            } for c in credits],
            "security_deposit": {"expected": str(tenancy.security_deposit_expected),
                **{key: str(value) for key, value in deposit_totals(db, tenancy.id).items()},
                "transactions": [deposit_transaction_item(item) for item in security_deposit_items]},
        })
    return {"display_name": profile.display_name if profile else actor.email,
            "tenancies": tenancies}


def notification_preferences_response(preference: TenantNotificationPreference | None) -> dict[str, object]:
    return {
        "email_enabled": preference.email_enabled if preference else False,
        "email_consent_at": preference.email_consent_at.isoformat() if preference and preference.email_consent_at else None,
        "whatsapp_enabled": preference.whatsapp_enabled if preference else False,
        "whatsapp_phone": preference.whatsapp_phone if preference else None,
        "whatsapp_consent_at": preference.whatsapp_consent_at.isoformat() if preference and preference.whatsapp_consent_at else None,
        "consent_version": preference.consent_version if preference else "notification-consent-v1",
        "email_provider_enabled": email_provider_enabled(),
        "whatsapp_provider_enabled": whatsapp_provider_enabled(),
    }


@router.get("/tenant/notification-preferences")
def get_notification_preferences(actor: User = Depends(require_user), db: Session = Depends(get_db)) -> dict[str, object]:
    if actor.role is not Role.tenant:
        raise HTTPException(status_code=403, detail="Forbidden")
    return notification_preferences_response(db.get(TenantNotificationPreference, actor.id))


@router.put("/tenant/notification-preferences")
def update_notification_preferences(body: NotificationPreferenceUpdate, request: Request,
                                    actor: User = Depends(require_user), db: Session = Depends(get_db)) -> dict[str, object]:
    if actor.role is not Role.tenant:
        raise HTTPException(status_code=403, detail="Forbidden")
    verify_csrf(request, db, session_from_request(request, db))
    if body.whatsapp_enabled and not body.whatsapp_phone:
        raise HTTPException(status_code=422, detail="Enter a WhatsApp number in international format before opting in")
    if not body.whatsapp_enabled and body.whatsapp_phone:
        raise HTTPException(status_code=422, detail="A WhatsApp number is saved only while WhatsApp consent is enabled")

    preference = db.scalar(select(TenantNotificationPreference).where(
        TenantNotificationPreference.user_id == actor.id).with_for_update())
    if preference is None:
        preference = TenantNotificationPreference(user_id=actor.id)
        db.add(preference)
        db.flush()
    version = "notification-consent-v1"
    now = datetime.now(timezone.utc)

    def record_event(channel: str, action: str) -> None:
        db.add(NotificationConsentEvent(user_id=actor.id, channel=channel, action=action,
                                        consent_version=version))
        db.add(AuditLog(actor_id=actor.id, action=f"notification_consent.{channel}_{action}",
                        target_type="tenant_notification_preference", target_id=str(actor.id)))

    if preference.email_enabled != body.email_enabled:
        record_event("email", "granted" if body.email_enabled else "revoked")
        preference.email_consent_at = now if body.email_enabled else None
    preference.email_enabled = body.email_enabled

    phone_changed = preference.whatsapp_phone != body.whatsapp_phone
    if preference.whatsapp_enabled and (not body.whatsapp_enabled or phone_changed):
        record_event("whatsapp", "revoked")
    if body.whatsapp_enabled and (not preference.whatsapp_enabled or phone_changed):
        record_event("whatsapp", "granted")
        preference.whatsapp_consent_at = now
    elif not body.whatsapp_enabled:
        preference.whatsapp_consent_at = None
    preference.whatsapp_enabled = body.whatsapp_enabled
    preference.whatsapp_phone = body.whatsapp_phone if body.whatsapp_enabled else None
    preference.consent_version = version
    preference.updated_at = now
    db.commit()
    return notification_preferences_response(preference)


@router.get("/tenant/maintenance-requests")
def list_tenant_maintenance_requests(
    actor: User = Depends(require_user), db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    if actor.role is not Role.tenant:
        raise HTTPException(status_code=403, detail="Forbidden")
    rows = db.scalars(select(MaintenanceRequest).where(
        MaintenanceRequest.requester_id == actor.id
    ).order_by(MaintenanceRequest.created_at.desc()).limit(100)).all()
    return [{"id": str(row.id), "tenancy_id": str(row.tenancy_id), "subject": row.subject,
             "description": row.description, "status": row.status,
             "created_at": row.created_at.isoformat()} for row in rows]


@router.post("/tenant/maintenance-requests", status_code=201)
def create_tenant_maintenance_request(
    body: MaintenanceRequestCreate,
    request: Request,
    actor: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if actor.role is not Role.tenant:
        raise HTTPException(status_code=403, detail="Forbidden")
    verify_csrf(request, db, session_from_request(request, db))
    tenancy_location = db.execute(select(Tenancy, Property.timezone)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .join(Property, Property.id == Unit.property_id)
        .where(Tenancy.id == body.tenancy_id)).first()
    if tenancy_location is None:
        raise HTTPException(status_code=404, detail="Active tenancy not found")
    tenancy_row, property_timezone = tenancy_location
    today = datetime.now(timezone.utc).astimezone(ZoneInfo(property_timezone)).date()
    participation = db.scalar(select(TenancyTenant).join(
        Tenancy, Tenancy.id == TenancyTenant.tenancy_id
    ).where(
        TenancyTenant.tenancy_id == body.tenancy_id,
        TenancyTenant.user_id == actor.id,
        TenancyTenant.start_date <= today,
        (TenancyTenant.end_date.is_(None) | (TenancyTenant.end_date >= today)),
        Tenancy.id == tenancy_row.id,
        Tenancy.status == TenancyStatus.active,
    ))
    if participation is None:
        raise HTTPException(status_code=404, detail="Active tenancy not found")
    maintenance = MaintenanceRequest(tenancy_id=body.tenancy_id, requester_id=actor.id,
                                    subject=body.subject, description=body.description)
    db.add(maintenance)
    db.flush()
    db.add(AuditLog(actor_id=actor.id, action="maintenance.request_created",
                    target_type="maintenance_request", target_id=str(maintenance.id)))
    db.commit()
    return {"id": str(maintenance.id), "status": maintenance.status}


@router.get("/maintenance-requests")
def list_owner_maintenance_requests(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    actor: User = Depends(require_owner), db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    rows = db.execute(select(MaintenanceRequest, User, Tenancy, Unit, Property)
        .join(User, User.id == MaintenanceRequest.requester_id)
        .join(Tenancy, Tenancy.id == MaintenanceRequest.tenancy_id)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .join(Property, Property.id == Unit.property_id)
        .order_by(MaintenanceRequest.created_at.desc()).offset(offset).limit(limit)).all()
    result: list[dict[str, object]] = []
    for row, requester, tenancy, unit, property_row in rows:
        profile = db.get(TenantProfile, requester.id)
        result.append({"id": str(row.id), "subject": row.subject, "description": row.description,
            "status": row.status, "created_at": row.created_at.isoformat(),
            "tenant": profile.display_name if profile else requester.email,
            "property": property_row.name, "unit": unit.unit_number})
    return result


@router.patch("/maintenance-requests/{request_id}")
def update_maintenance_status(
    request_id: UUID,
    body: MaintenanceStatusUpdate,
    request: Request,
    actor: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    verify_csrf(request, db, session_from_request(request, db))
    maintenance = db.get(MaintenanceRequest, request_id)
    if maintenance is None:
        raise HTTPException(status_code=404, detail="Maintenance request not found")
    previous = maintenance.status
    maintenance.status = body.status
    db.add(AuditLog(actor_id=actor.id, action=f"maintenance.status_{body.status}",
                    target_type="maintenance_request", target_id=str(maintenance.id)))
    db.commit()
    return {"id": str(maintenance.id), "status": maintenance.status, "previous_status": previous}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    session = session_from_request(request, db)
    verify_csrf(request, db, session)
    db.delete(session)
    db.commit()
    response.delete_cookie("rental_session", path="/")
    response.delete_cookie("rental_csrf", path="/")
    return response


@router.post("/invitations", status_code=201)
def create_invitation(
    body: InvitationCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, str]:
    verify_csrf(request, db, session_from_request(request, db))
    email = str(body.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account already exists for this email")
    now = datetime.now(timezone.utc)
    pending = db.scalar(select(TenantInvitation).where(
        TenantInvitation.email == email, TenantInvitation.accepted_at.is_(None),
        TenantInvitation.revoked_at.is_(None)).with_for_update())
    if pending and pending.expires_at > now:
        raise HTTPException(status_code=409, detail="An invitation is already pending")
    if pending:
        pending.revoked_at = now
    raw_token = secrets.token_urlsafe(32)
    invitation = TenantInvitation(email=email, token_hash=token_hash(raw_token), invited_by=actor.id,
                                  expires_at=now + timedelta(days=7))
    db.add(invitation)
    try:
        db.flush()
        db.add(AuditLog(actor_id=actor.id, action="tenant.invitation_created", target_type="invitation",
                        target_id=str(invitation.id)))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A pending invitation already exists") from exc
    # The secret is returned once to an authenticated owner; only its hash is stored.
    return {"id": str(invitation.id), "email": invitation.email, "token": raw_token,
            "expires_at": invitation.expires_at.isoformat()}


@router.get("/invitations")
def list_invitations(
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> list[dict[str, str]]:
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(TenantInvitation).where(
        TenantInvitation.accepted_at.is_(None), TenantInvitation.revoked_at.is_(None),
        TenantInvitation.expires_at > now).order_by(TenantInvitation.created_at.desc()))
    return [{"id": str(row.id), "email": row.email, "expires_at": row.expires_at.isoformat()} for row in rows]


@router.get("/tenants")
def list_tenants(
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> list[dict[str, str]]:
    rows = db.execute(select(User, TenantProfile).join(TenantProfile, TenantProfile.user_id == User.id)
                      .where(User.role == Role.tenant, User.active.is_(True))
                      .order_by(TenantProfile.display_name, User.email)).all()
    return [{"id": str(user.id), "email": user.email, "display_name": profile.display_name}
            for user, profile in rows]


@router.post("/invitations/accept", status_code=201)
def accept_invitation(body: InvitationAccept, db: Session = Depends(get_db)) -> dict[str, str]:
    invitation = db.scalar(select(TenantInvitation).where(
        TenantInvitation.token_hash == token_hash(body.token)).with_for_update())
    now = datetime.now(timezone.utc)
    if (invitation is None or invitation.accepted_at is not None or invitation.revoked_at is not None
            or invitation.expires_at <= now):
        raise HTTPException(status_code=400, detail="Invitation is invalid or expired")
    user = User(email=invitation.email, password_hash=password_hasher.hash(body.password), role=Role.tenant)
    db.add(user)
    invitation.accepted_at = now
    try:
        db.flush()
        db.add(TenantProfile(user_id=user.id, display_name=body.display_name.strip()))
        db.add(AuditLog(actor_id=user.id, action="tenant.invitation_accepted", target_type="user",
                        target_id=str(user.id)))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invitation is invalid or expired") from exc
    return {"status": "accepted", "email": user.email, "id": str(user.id)}


@router.post("/invitations/{invitation_id}/revoke", status_code=204)
def revoke_invitation(
    invitation_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> Response:
    verify_csrf(request, db, session_from_request(request, db))
    invitation = db.get(TenantInvitation, invitation_id)
    if invitation is None or invitation.accepted_at is not None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    invitation.revoked_at = datetime.now(timezone.utc)
    db.add(AuditLog(actor_id=actor.id, action="tenant.invitation_revoked", target_type="invitation",
                    target_id=str(invitation.id)))
    db.commit()
    return Response(status_code=204)


@router.post("/tenancies", status_code=201)
def create_tenancy(
    body: TenancyCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, str]:
    verify_csrf(request, db, session_from_request(request, db))
    if body.end_date is not None and body.end_date <= body.start_date:
        raise HTTPException(status_code=422, detail="End date must be after start date")
    tenant = db.get(User, body.tenant_id)
    if tenant is None or not tenant.active or tenant.role is not Role.tenant:
        raise HTTPException(status_code=404, detail="Tenant account not found")
    unit = db.get(Unit, body.unit_id)
    if unit is None or not unit.active:
        raise HTTPException(status_code=404, detail="Apartment not found")
    tenancy = Tenancy(unit_id=unit.id, start_date=body.start_date, end_date=body.end_date,
                      security_deposit_expected=body.security_deposit_expected,
                      status=TenancyStatus.active, created_by=actor.id)
    db.add(tenancy)
    try:
        db.flush()
        db.add(TenancyTenant(tenancy_id=tenancy.id, user_id=tenant.id, start_date=body.start_date,
                             end_date=body.end_date, is_primary=True, financially_responsible=True))
        db.add(RentTerm(tenancy_id=tenancy.id, effective_from=body.start_date, effective_to=body.end_date,
                        monthly_rent=body.monthly_rent, currency="INR", due_day=body.due_day,
                        proration_method=body.proration_method))
        db.add(AuditLog(actor_id=actor.id, action="tenancy.created", target_type="tenancy",
                        target_id=str(tenancy.id)))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Apartment has an overlapping tenancy or conflicting terms") from exc
    return {"id": str(tenancy.id), "status": tenancy.status.value}


DOCUMENT_MAX_BYTES = 10 * 1024 * 1024


def tenancy_document_access(db: Session, document: TenancyDocument, actor: User) -> bool:
    if actor.role is Role.owner:
        return True
    if actor.role is not Role.tenant or not document.tenant_visible:
        return False
    return db.scalar(select(TenancyTenant.id).where(
        TenancyTenant.tenancy_id == document.tenancy_id,
        TenancyTenant.user_id == actor.id,
    )) is not None


def document_metadata(document: TenancyDocument) -> dict[str, object]:
    return {"id": str(document.id), "tenancy_id": str(document.tenancy_id),
            "name": document.original_name, "content_type": document.content_type,
            "byte_size": document.byte_size, "created_at": document.created_at.isoformat()}


@router.get("/tenancies")
def list_tenancies(
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> list[dict[str, object]]:
    rows = db.execute(select(Tenancy, Unit, Property, User, TenantProfile)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .join(Property, Property.id == Unit.property_id)
        .outerjoin(TenancyTenant, (TenancyTenant.tenancy_id == Tenancy.id) & TenancyTenant.is_primary.is_(True))
        .outerjoin(User, User.id == TenancyTenant.user_id)
        .outerjoin(TenantProfile, TenantProfile.user_id == User.id)
        .order_by(Tenancy.start_date.desc()).limit(300)).all()
    return [{"id": str(tenancy.id), "tenant_id": str(user.id) if user else None,
             "property_id": str(property_row.id), "unit_id": str(unit.id),
             "property": property_row.name, "unit": unit.unit_number,
             "tenant": (profile.display_name if profile else user.email) if user else "No tenant",
             "status": tenancy.status.value, "start_date": tenancy.start_date.isoformat()}
            for tenancy, unit, property_row, user, profile in rows]


def deposit_transaction_item(transaction: SecurityDepositTransaction) -> dict[str, object]:
    return {"id": str(transaction.id), "tenancy_id": str(transaction.tenancy_id),
            "transaction_type": transaction.transaction_type, "amount": str(transaction.amount),
            "method": transaction.method, "reference_code": transaction.reference_code,
            "reason": transaction.reason, "occurred_at": transaction.occurred_at.isoformat()}


@router.get("/security-deposits")
def list_security_deposits(
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> list[dict[str, object]]:
    rows = db.execute(select(Tenancy, Unit, Property, User, TenantProfile)
        .join(Unit, Unit.id == Tenancy.unit_id).join(Property, Property.id == Unit.property_id)
        .outerjoin(TenancyTenant, (TenancyTenant.tenancy_id == Tenancy.id) & TenancyTenant.is_primary.is_(True))
        .outerjoin(User, User.id == TenancyTenant.user_id).outerjoin(TenantProfile, TenantProfile.user_id == User.id)
        .order_by(Tenancy.start_date.desc()).limit(300)).all()
    result = []
    for tenancy, unit, property_row, tenant, profile in rows:
        result.append({"id": str(tenancy.id), "property": property_row.name, "unit": unit.unit_number,
            "tenant": (profile.display_name if profile else tenant.email) if tenant else "No tenant",
            "status": tenancy.status.value, "expected": str(tenancy.security_deposit_expected),
            **{key: str(value) for key, value in deposit_totals(db, tenancy.id).items()}})
    return result


def utility_bill_item(db: Session, bill: UtilityBill) -> dict[str, object]:
    property_row = db.get(Property, bill.property_id)
    unit = db.get(Unit, bill.unit_id) if bill.unit_id else None
    allocations = db.execute(select(UtilityAllocation, Tenancy, Unit).join(
        Tenancy, Tenancy.id == UtilityAllocation.tenancy_id).join(Unit, Unit.id == Tenancy.unit_id)
        .where(UtilityAllocation.bill_id == bill.id).order_by(Unit.unit_number)).all()
    return {"id": str(bill.id), "property_id": str(bill.property_id),
            "property": property_row.name if property_row else "", "unit_id": str(unit.id) if unit else None,
            "unit": unit.unit_number if unit else None, "utility_type": bill.utility_type,
            "period_start": bill.period_start.isoformat(), "period_end": bill.period_end.isoformat(),
            "due_date": bill.due_date.isoformat(), "supplier": bill.supplier,
            "bill_reference": bill.bill_reference, "amount": str(bill.amount), "notes": bill.notes,
            "status": bill.status,
            "allocations": [{"tenancy_id": str(tenancy.id), "unit": unit_row.unit_number,
                             "amount": str(allocation.amount)}
                            for allocation, tenancy, unit_row in allocations]}


def utility_meter_item(db: Session, meter: UtilityMeter) -> dict[str, object]:
    property_row = db.get(Property, meter.property_id)
    unit = db.get(Unit, meter.unit_id) if meter.unit_id else None
    latest = db.scalar(select(UtilityMeterReading).where(
        UtilityMeterReading.meter_id == meter.id).order_by(UtilityMeterReading.read_on.desc()).limit(1))
    return {"id": str(meter.id), "property_id": str(meter.property_id),
        "property": property_row.name if property_row else "", "unit_id": str(unit.id) if unit else None,
        "unit": unit.unit_number if unit else None, "utility_type": meter.utility_type,
        "meter_name": meter.meter_name, "serial_number": meter.serial_number,
        "unit_of_measure": meter.unit_of_measure, "active": meter.active,
        "latest_reading": str(latest.reading) if latest else None,
        "latest_read_on": latest.read_on.isoformat() if latest else None}


@router.get("/utility-meters")
def list_utility_meters(db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> list[dict[str, object]]:
    return [utility_meter_item(db, meter) for meter in db.scalars(
        select(UtilityMeter).order_by(UtilityMeter.created_at.desc()).limit(300)).all()]


@router.post("/utility-meters", status_code=201)
def create_utility_meter(body: UtilityMeterCreate, request: Request,
                         db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    meter_name = body.meter_name.strip()
    unit_of_measure = body.unit_of_measure.strip()
    if not meter_name or not unit_of_measure:
        raise HTTPException(status_code=422, detail="Meter name and unit of measure cannot be blank")
    if db.get(Property, body.property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found")
    if body.unit_id:
        unit = db.get(Unit, body.unit_id)
        if unit is None or unit.property_id != body.property_id:
            raise HTTPException(status_code=422, detail="Apartment must belong to the selected property")
    meter = UtilityMeter(**body.model_dump(exclude={"meter_name", "unit_of_measure"}),
        meter_name=meter_name, unit_of_measure=unit_of_measure, created_by=actor.id)
    db.add(meter)
    db.flush()
    db.add(AuditLog(actor_id=actor.id, action="utility.meter_created", target_type="utility_meter", target_id=str(meter.id)))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A meter with this name already exists at the property") from exc
    return utility_meter_item(db, meter)


@router.post("/utility-rates", status_code=201)
def create_utility_rate(body: UtilityRateCreate, request: Request,
                        db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    if db.get(Property, body.property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found")
    if body.unit_id:
        unit = db.get(Unit, body.unit_id)
        if unit is None or unit.property_id != body.property_id:
            raise HTTPException(status_code=422, detail="Apartment must belong to the selected property")
    if body.effective_from < date.today():
        raise HTTPException(status_code=422, detail="Utility rates cannot be backdated")
    scope = [UtilityRate.property_id == body.property_id, UtilityRate.utility_type == body.utility_type]
    scope.append(UtilityRate.unit_id == body.unit_id if body.unit_id else UtilityRate.unit_id.is_(None))
    same_start = db.scalar(select(UtilityRate).where(*scope,
        UtilityRate.effective_from == body.effective_from).with_for_update())
    if same_start:
        raise HTTPException(status_code=409, detail="A rate already exists for this effective date")
    previous = db.scalar(select(UtilityRate).where(*scope,
        UtilityRate.effective_from < body.effective_from,
        (UtilityRate.effective_to.is_(None) | (UtilityRate.effective_to > body.effective_from)))
        .order_by(UtilityRate.effective_from.desc()).limit(1).with_for_update())
    if previous:
        previous.effective_to = body.effective_from
    following = db.scalar(select(UtilityRate.effective_from).where(*scope,
        UtilityRate.effective_from > body.effective_from).order_by(UtilityRate.effective_from).limit(1))
    rate = UtilityRate(**body.model_dump(), effective_to=following, created_by=actor.id)
    db.add(rate)
    db.flush()
    db.add(AuditLog(actor_id=actor.id, action="utility.rate_created", target_type="utility_rate", target_id=str(rate.id)))
    db.commit()
    return {"id": str(rate.id), "property_id": str(rate.property_id), "unit_id": str(rate.unit_id) if rate.unit_id else None,
        "utility_type": rate.utility_type, "rate_per_unit": str(rate.rate_per_unit),
        "fixed_charge": str(rate.fixed_charge), "effective_from": rate.effective_from.isoformat(),
        "effective_to": rate.effective_to.isoformat() if rate.effective_to else None}


@router.get("/utility-meters/{meter_id}/readings")
def list_meter_readings(meter_id: UUID, db: Session = Depends(get_db),
                        actor: User = Depends(require_owner)) -> list[dict[str, object]]:
    if db.get(UtilityMeter, meter_id) is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    readings = db.scalars(select(UtilityMeterReading).where(
        UtilityMeterReading.meter_id == meter_id).order_by(UtilityMeterReading.read_on.desc()).limit(100)).all()
    return [{"id": str(row.id), "read_on": row.read_on.isoformat(), "reading": str(row.reading),
        "consumption": str(row.consumption), "calculated_amount": str(row.calculated_amount) if row.calculated_amount is not None else None,
        "utility_bill_id": str(row.utility_bill_id) if row.utility_bill_id else None} for row in readings]


@router.post("/utility-meters/{meter_id}/readings", status_code=201)
def post_meter_reading(meter_id: UUID, body: UtilityMeterReadingCreate, request: Request,
                       db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    try:
        reading, bill = record_meter_reading(db, meter_id=meter_id, read_on=body.read_on,
            reading=body.reading, due_date=body.due_date, actor_id=actor.id)
        db.commit()
    except UtilityError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A reading already exists for this date") from exc
    return {"id": str(reading.id), "read_on": reading.read_on.isoformat(), "reading": str(reading.reading),
        "consumption": str(reading.consumption), "calculated_amount": str(reading.calculated_amount) if reading.calculated_amount is not None else None,
        "utility_bill": utility_bill_item(db, bill) if bill else None}


@router.get("/utility-bills")
def list_utility_bills(db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> list[dict[str, object]]:
    bills = db.scalars(select(UtilityBill).order_by(UtilityBill.created_at.desc()).limit(300)).all()
    return [utility_bill_item(db, bill) for bill in bills]


@router.post("/utility-bills", status_code=201)
def create_utility_bill(body: UtilityBillCreate, request: Request, db: Session = Depends(get_db),
                        actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    if body.period_end <= body.period_start:
        raise HTTPException(status_code=422, detail="Billing period end must be after its start")
    if db.get(Property, body.property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found")
    if body.unit_id is not None:
        unit = db.get(Unit, body.unit_id)
        if unit is None or unit.property_id != body.property_id:
            raise HTTPException(status_code=422, detail="Apartment must belong to the selected property")
    bill = UtilityBill(**body.model_dump(), created_by=actor.id, status="pending")
    db.add(bill)
    db.add(AuditLog(actor_id=actor.id, action="utility.bill_created", target_type="utility_bill",
                    target_id=str(bill.id)))
    db.commit()
    return utility_bill_item(db, bill)


@router.post("/utility-bills/{bill_id}/allocate")
def post_utility_allocations(bill_id: UUID, body: UtilityAllocationCreate, request: Request,
                             db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    try:
        allocate_utility_bill(db, bill_id=bill_id,
                              allocations=[(item.tenancy_id, item.amount) for item in body.allocations],
                              actor_id=actor.id)
        db.commit()
    except UtilityError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utility_bill_item(db, db.get(UtilityBill, bill_id))


@router.get("/expenses")
def list_property_expenses(db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> list[dict[str, object]]:
    rows = db.execute(select(PropertyExpense, Property, Unit)
        .join(Property, Property.id == PropertyExpense.property_id)
        .outerjoin(Unit, Unit.id == PropertyExpense.unit_id)
        .order_by(PropertyExpense.spent_on.desc(), PropertyExpense.created_at.desc()).limit(500)).all()
    return [{"id": str(expense.id), "property_id": str(property_row.id), "property": property_row.name,
             "unit_id": str(unit.id) if unit else None, "unit": unit.unit_number if unit else None,
             "category": expense.category, "amount": str(expense.amount), "spent_on": expense.spent_on.isoformat(),
             "vendor": expense.vendor, "reference_code": expense.reference_code,
             "description": expense.description}
            for expense, property_row, unit in rows]


@router.post("/expenses", status_code=201)
def create_property_expense(body: PropertyExpenseCreate, request: Request, db: Session = Depends(get_db),
                            actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    property_row = db.get(Property, body.property_id)
    if property_row is None:
        raise HTTPException(status_code=404, detail="Property not found")
    unit = db.get(Unit, body.unit_id) if body.unit_id else None
    if body.unit_id and (unit is None or unit.property_id != body.property_id):
        raise HTTPException(status_code=422, detail="Apartment must belong to the selected property")
    expense = PropertyExpense(**body.model_dump(), created_by=actor.id)
    db.add(expense)
    db.flush()
    db.add(AuditLog(actor_id=actor.id, action="property.expense_recorded", target_type="property_expense",
                    target_id=str(expense.id)))
    db.commit()
    return {"id": str(expense.id), "property_id": str(property_row.id), "property": property_row.name,
            "unit_id": str(unit.id) if unit else None, "unit": unit.unit_number if unit else None,
            "category": expense.category, "amount": str(expense.amount), "spent_on": expense.spent_on.isoformat(),
            "vendor": expense.vendor, "reference_code": expense.reference_code,
            "description": expense.description}


@router.get("/reports/dashboard")
def dashboard_report(period: str = Query(default="this_month", pattern="^(this_month|last_month|this_quarter)$"),
                     db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> dict[str, object]:
    today = date.today()
    start, end = period_bounds(period, today)
    active_tenancy = and_(Tenancy.status == TenancyStatus.active, Tenancy.start_date <= today,
                          or_(Tenancy.end_date.is_(None), Tenancy.end_date > today))
    property_rows = db.execute(select(Property.id, Property.name, Property.address,
        func.count(Unit.id), func.count(func.distinct(Tenancy.unit_id)))
        .select_from(Property)
        .outerjoin(Unit, and_(Unit.property_id == Property.id, Unit.active.is_(True)))
        .outerjoin(Tenancy, and_(Tenancy.unit_id == Unit.id, active_tenancy))
        .where(Property.archived.is_(False))
        .group_by(Property.id, Property.name, Property.address).order_by(Property.name).limit(100)).all()
    properties = [{"id": str(row[0]), "name": row[1], "address": row[2],
                   "unit_count": int(row[3]), "occupied_units": int(row[4]),
                   "occupancy_percent": round((int(row[4]) * 100 / int(row[3])) if row[3] else 0, 1)}
                  for row in property_rows]
    total_units = sum(row["unit_count"] for row in properties)
    occupied_units = sum(row["occupied_units"] for row in properties)

    rent_charged = db.scalar(select(func.coalesce(func.sum(Charge.amount), 0)).where(
        Charge.charge_type == "rent", Charge.period_start >= start, Charge.period_start < end)) or Decimal("0")
    cash_received = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0))
        .outerjoin(PaymentReversal, PaymentReversal.payment_id == Payment.id)
        .where(Payment.received_at >= datetime.combine(start, datetime.min.time(), timezone.utc),
               Payment.received_at < datetime.combine(end, datetime.min.time(), timezone.utc),
               PaymentReversal.id.is_(None))) or Decimal("0")

    payment_totals = select(PaymentAllocation.charge_id.label("charge_id"),
                            func.sum(PaymentAllocation.amount).label("amount")).group_by(
                                PaymentAllocation.charge_id).subquery()
    credit_totals = select(CreditAllocation.charge_id.label("charge_id"),
                           func.sum(CreditAllocation.amount).label("amount")).group_by(
                               CreditAllocation.charge_id).subquery()
    outstanding = Charge.amount - func.coalesce(payment_totals.c.amount, 0) - func.coalesce(credit_totals.c.amount, 0)
    overdue_amount, overdue_count = db.execute(select(
        func.coalesce(func.sum(func.greatest(outstanding, 0)), 0), func.count(Charge.id)
    ).outerjoin(payment_totals, payment_totals.c.charge_id == Charge.id)
     .outerjoin(credit_totals, credit_totals.c.charge_id == Charge.id)
     .where(Charge.charge_type == "rent", Charge.due_date < today, outstanding > 0)).one()

    expense_total, expense_count = db.execute(select(func.coalesce(func.sum(PropertyExpense.amount), 0),
        func.count(PropertyExpense.id)).where(PropertyExpense.spent_on >= start,
                                               PropertyExpense.spent_on < end)).one()
    pending_utility_count, pending_utility_total = db.execute(select(func.count(UtilityBill.id),
        func.coalesce(func.sum(UtilityBill.amount), 0)).where(UtilityBill.status == "pending")).one()
    move_outs = db.scalar(select(func.count(Tenancy.id)).where(
        active_tenancy, Tenancy.end_date > today,
        Tenancy.end_date <= today + timedelta(days=30))) or 0
    open_maintenance = db.scalar(select(func.count(MaintenanceRequest.id)).where(
        MaintenanceRequest.status.in_(["open", "in_progress"]))) or 0
    inspections_in_progress = db.scalar(select(func.count(Inspection.id)).where(
        Inspection.status == "in_progress")) or 0

    deposit_receipts = select(SecurityDepositTransaction.tenancy_id.label("tenancy_id"),
        func.sum(SecurityDepositTransaction.amount).label("received")).where(
            SecurityDepositTransaction.transaction_type == "receipt").group_by(
                SecurityDepositTransaction.tenancy_id).subquery()
    deposits_due = db.scalar(select(func.coalesce(func.sum(func.greatest(
        Tenancy.security_deposit_expected - func.coalesce(deposit_receipts.c.received, 0), 0)), 0))
        .outerjoin(deposit_receipts, deposit_receipts.c.tenancy_id == Tenancy.id)
        .where(active_tenancy)) or Decimal("0")

    months = trailing_months(today)
    chart_start, chart_end = months[0], next_month(months[-1])
    chart_charges = db.scalars(select(Charge).where(
        Charge.charge_type == "rent", Charge.period_start >= chart_start, Charge.period_start < chart_end)).all()
    charges_by_month: dict[date, Decimal] = {}
    for charge in chart_charges:
        charges_by_month[charge.period_start.replace(day=1)] = charges_by_month.get(
            charge.period_start.replace(day=1), Decimal("0")) + charge.amount
    chart_payments = db.execute(select(Payment.received_at, Payment.amount)
        .outerjoin(PaymentReversal, PaymentReversal.payment_id == Payment.id)
        .where(Payment.received_at >= datetime.combine(chart_start, datetime.min.time(), timezone.utc),
               Payment.received_at < datetime.combine(chart_end, datetime.min.time(), timezone.utc),
               PaymentReversal.id.is_(None))).all()
    payments_by_month: dict[date, Decimal] = {}
    for received_at, amount in chart_payments:
        month = received_at.date().replace(day=1)
        payments_by_month[month] = payments_by_month.get(month, Decimal("0")) + amount
    collection = [{"month": month.isoformat(), "rent_charged": str(charges_by_month.get(month, Decimal("0"))),
                   "payments_received": str(payments_by_month.get(month, Decimal("0")))} for month in months]

    activity = []
    if overdue_count:
        activity.append({"title": "Overdue rent", "detail": f"{overdue_count} rent charges · ₹{Decimal(overdue_amount):,.2f} outstanding", "count": int(overdue_count), "path": "/ledger", "tone": "orange"})
    if pending_utility_count:
        activity.append({"title": "Utility bills pending", "detail": f"{pending_utility_count} bills · ₹{Decimal(pending_utility_total):,.2f} to allocate", "count": int(pending_utility_count), "path": "/utilities", "tone": "blue"})
    if open_maintenance:
        activity.append({"title": "Open maintenance requests", "detail": f"{open_maintenance} requests need attention", "count": int(open_maintenance), "path": "/maintenance", "tone": "purple"})
    if move_outs:
        activity.append({"title": "Upcoming move-outs", "detail": f"{move_outs} active tenancies end within 30 days", "count": int(move_outs), "path": "/tenants", "tone": "green"})
    if inspections_in_progress:
        activity.append({"title": "Inspections in progress", "detail": f"{inspections_in_progress} checklists need completion", "count": int(inspections_in_progress), "path": "/inspections", "tone": "purple"})

    period_labels = {"this_month": "This month", "last_month": "Last month", "this_quarter": "This quarter"}
    return {"period": period, "period_label": period_labels[period], "period_start": start.isoformat(),
        "period_end": end.isoformat(), "metrics": {"total_units": total_units,
        "occupied_units": occupied_units, "occupancy_percent": round(occupied_units * 100 / total_units, 1) if total_units else 0,
        "rent_charged": str(rent_charged), "payments_received": str(cash_received),
        "overdue_amount": str(overdue_amount), "overdue_count": int(overdue_count),
        "expenses": str(expense_total), "expense_count": int(expense_count),
        "deposits_due": str(deposits_due), "pending_utility_count": int(pending_utility_count),
        "pending_utility_amount": str(pending_utility_total), "upcoming_move_outs": int(move_outs),
        "open_maintenance": int(open_maintenance), "inspections_in_progress": int(inspections_in_progress)},
        "collection": collection, "properties": properties[:6], "attention": activity[:5]}


@router.get("/reports/export.csv")
def export_csv(dataset: str = Query(pattern="^(charges|payments|expenses|utilities|deposits)$"),
               period: str = Query(default="this_month", pattern="^(this_month|last_month|this_quarter)$"),
               db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> Response:
    """Export a bounded period of owner-authorized financial records as formula-safe CSV."""
    start, end = period_bounds(period, date.today())
    max_rows = 10_000
    headers: list[str]
    rows: list[tuple[object, ...]]

    if dataset == "charges":
        primary_user = select(TenancyTenant.user_id).where(
            TenancyTenant.tenancy_id == Tenancy.id, TenancyTenant.is_primary.is_(True),
            TenancyTenant.start_date <= Charge.period_start,
            or_(TenancyTenant.end_date.is_(None), TenancyTenant.end_date > Charge.period_start),
        ).order_by(TenancyTenant.start_date.desc()).limit(1).correlate(Tenancy).scalar_subquery()
        query = select(Charge, Property.name, Unit.unit_number, TenantProfile.display_name).join(
            Tenancy, Tenancy.id == Charge.tenancy_id).join(Unit, Unit.id == Tenancy.unit_id).join(
            Property, Property.id == Unit.property_id).outerjoin(User, User.id == primary_user).outerjoin(
            TenantProfile, TenantProfile.user_id == User.id).where(
                Charge.period_start >= start, Charge.period_start < end
            ).order_by(Charge.period_start, Property.name, Unit.unit_number).limit(max_rows + 1)
        result = db.execute(query).all()
        headers = ["charge_id", "property", "apartment", "tenant", "type", "period_start", "period_end", "due_date", "amount", "currency"]
        rows = [(charge.id, property_name, unit_number, tenant_name or "Tenant", charge.charge_type,
                 charge.period_start, charge.period_end, charge.due_date, charge.amount, charge.currency)
                for charge, property_name, unit_number, tenant_name in result]
    elif dataset == "payments":
        query = select(Payment, Property.name, Unit.unit_number, TenantProfile.display_name,
                       PaymentReversal.id).join(Tenancy, Tenancy.id == Payment.tenancy_id).join(
            Unit, Unit.id == Tenancy.unit_id).join(Property, Property.id == Unit.property_id).join(
            User, User.id == Payment.tenant_id).outerjoin(TenantProfile, TenantProfile.user_id == User.id).outerjoin(
            PaymentReversal, PaymentReversal.payment_id == Payment.id).where(
                Payment.received_at >= datetime.combine(start, datetime.min.time(), timezone.utc),
                Payment.received_at < datetime.combine(end, datetime.min.time(), timezone.utc)
            ).order_by(Payment.received_at, Payment.id).limit(max_rows + 1)
        result = db.execute(query).all()
        headers = ["payment_id", "property", "apartment", "tenant", "status", "received_at", "amount", "currency", "method", "reference_code"]
        rows = [(payment.id, property_name, unit_number, tenant_name or "Tenant",
                 "reversed" if reversal_id else "recorded", payment.received_at, payment.amount,
                 payment.currency, payment.method, payment.reference_code)
                for payment, property_name, unit_number, tenant_name, reversal_id in result]
    elif dataset == "expenses":
        query = select(PropertyExpense, Property.name, Unit.unit_number).join(
            Property, Property.id == PropertyExpense.property_id).outerjoin(
            Unit, Unit.id == PropertyExpense.unit_id).where(
                PropertyExpense.spent_on >= start, PropertyExpense.spent_on < end
            ).order_by(PropertyExpense.spent_on, Property.name, PropertyExpense.id).limit(max_rows + 1)
        result = db.execute(query).all()
        headers = ["expense_id", "property", "apartment", "category", "spent_on", "vendor", "reference_code", "description", "amount", "currency"]
        rows = [(expense.id, property_name, unit_number or "Property-wide", expense.category,
                 expense.spent_on, expense.vendor, expense.reference_code, expense.description,
                 expense.amount, "INR") for expense, property_name, unit_number in result]
    elif dataset == "utilities":
        allocation_totals = select(UtilityAllocation.bill_id.label("bill_id"),
            func.sum(UtilityAllocation.amount).label("allocated")).group_by(
                UtilityAllocation.bill_id).subquery()
        query = select(UtilityBill, Property.name, Unit.unit_number, allocation_totals.c.allocated).join(
            Property, Property.id == UtilityBill.property_id).outerjoin(
            Unit, Unit.id == UtilityBill.unit_id).outerjoin(
            allocation_totals, allocation_totals.c.bill_id == UtilityBill.id).where(
                UtilityBill.period_start >= start, UtilityBill.period_start < end
            ).order_by(UtilityBill.period_start, Property.name, UtilityBill.id).limit(max_rows + 1)
        result = db.execute(query).all()
        headers = ["bill_id", "property", "apartment", "utility_type", "supplier", "bill_reference", "period_start", "period_end", "due_date", "amount", "allocated", "status", "currency"]
        rows = [(bill.id, property_name, unit_number or "Property-wide", bill.utility_type,
                 bill.supplier, bill.bill_reference, bill.period_start, bill.period_end, bill.due_date,
                 bill.amount, allocated or Decimal("0.00"), bill.status, "INR")
                for bill, property_name, unit_number, allocated in result]
    else:
        primary_user = select(TenancyTenant.user_id).where(
            TenancyTenant.tenancy_id == Tenancy.id, TenancyTenant.is_primary.is_(True),
            TenancyTenant.start_date <= func.date(SecurityDepositTransaction.occurred_at),
            or_(TenancyTenant.end_date.is_(None),
                TenancyTenant.end_date > func.date(SecurityDepositTransaction.occurred_at)),
        ).order_by(TenancyTenant.start_date.desc()).limit(1).correlate(Tenancy).scalar_subquery()
        query = select(SecurityDepositTransaction, Property.name, Unit.unit_number,
                       TenantProfile.display_name).join(Tenancy, Tenancy.id == SecurityDepositTransaction.tenancy_id).join(
            Unit, Unit.id == Tenancy.unit_id).join(Property, Property.id == Unit.property_id).outerjoin(
            User, User.id == primary_user).outerjoin(TenantProfile, TenantProfile.user_id == User.id).where(
                SecurityDepositTransaction.occurred_at >= datetime.combine(start, datetime.min.time(), timezone.utc),
                SecurityDepositTransaction.occurred_at < datetime.combine(end, datetime.min.time(), timezone.utc)
            ).order_by(SecurityDepositTransaction.occurred_at, SecurityDepositTransaction.id).limit(max_rows + 1)
        result = db.execute(query).all()
        headers = ["transaction_id", "property", "apartment", "tenant", "transaction_type", "occurred_at", "amount", "method", "reference_code", "reason", "currency"]
        rows = [(transaction.id, property_name, unit_number, tenant_name or "Tenant",
                 transaction.transaction_type, transaction.occurred_at, transaction.amount,
                 transaction.method, transaction.reference_code, transaction.reason, "INR")
                for transaction, property_name, unit_number, tenant_name in result]

    if len(rows) > max_rows:
        raise HTTPException(status_code=413, detail=f"Export exceeds {max_rows} rows; choose a shorter period")
    content = "\ufeff" + build_csv(headers, rows)
    filename = f"hearth-{dataset}-{start.isoformat()}-to-{end.isoformat()}.csv"
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.patch("/tenancies/{tenancy_id}/security-deposit/expected")
def update_security_deposit_expected(
    tenancy_id: UUID,
    body: SecurityDepositExpectedUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, str]:
    amount = body.amount
    verify_csrf(request, db, session_from_request(request, db))
    tenancy = db.scalar(select(Tenancy).where(Tenancy.id == tenancy_id).with_for_update())
    if tenancy is None:
        raise HTTPException(status_code=404, detail="Tenancy not found")
    if tenancy.status is not TenancyStatus.active:
        raise HTTPException(status_code=422, detail="Agreed deposit cannot be changed after the tenancy is closed")
    totals = deposit_totals(db, tenancy.id)
    if amount < totals["received"]:
        raise HTTPException(status_code=422, detail="Expected deposit cannot be less than the amount already received")
    tenancy.security_deposit_expected = amount
    db.add(AuditLog(actor_id=actor.id, action="security_deposit.expected_updated",
                    target_type="tenancy", target_id=str(tenancy.id)))
    db.commit()
    return {"tenancy_id": str(tenancy.id), "expected": str(tenancy.security_deposit_expected)}


@router.get("/tenancies/{tenancy_id}/security-deposit/transactions")
def list_security_deposit_transactions(
    tenancy_id: UUID,
    actor: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    if actor.role is Role.owner:
        authorized = db.get(Tenancy, tenancy_id) is not None
    else:
        authorized = db.scalar(select(TenancyTenant.id).where(
            TenancyTenant.tenancy_id == tenancy_id, TenancyTenant.user_id == actor.id
        )) is not None
    if not authorized:
        raise HTTPException(status_code=404, detail="Tenancy not found")
    rows = db.scalars(select(SecurityDepositTransaction).where(
        SecurityDepositTransaction.tenancy_id == tenancy_id
    ).order_by(SecurityDepositTransaction.occurred_at.desc()).limit(100)).all()
    return [deposit_transaction_item(row) for row in rows]


@router.post("/tenancies/{tenancy_id}/security-deposit/transactions", status_code=201)
def post_security_deposit_transaction(
    tenancy_id: UUID,
    body: SecurityDepositTransactionCreate,
    request: Request,
    idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    payload = body.model_dump(mode="json")
    fingerprint = deposit_request_hash(payload)
    try:
        transaction, created = record_deposit_transaction(db, tenancy_id=tenancy_id, actor_id=actor.id,
            transaction_type=body.transaction_type, amount=body.amount, method=body.method,
            reference_code=body.reference_code, reason=body.reason, occurred_at=body.occurred_at,
            idempotency_key=idempotency_key, request_hash=fingerprint)
        db.commit()
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LedgerError as exc:
        db.rollback()
        status = 404 if str(exc) == "Tenancy not found" else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Deposit transaction conflicts with an existing request") from exc
    result = deposit_transaction_item(transaction)
    result["created"] = created
    return result


@router.get("/tenancies/{tenancy_id}/documents")
def list_tenancy_documents(
    tenancy_id: UUID,
    actor: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    if actor.role is Role.owner:
        if db.get(Tenancy, tenancy_id) is None:
            raise HTTPException(status_code=404, detail="Tenancy not found")
    elif actor.role is not Role.tenant or db.scalar(select(TenancyTenant.id).where(
        TenancyTenant.tenancy_id == tenancy_id, TenancyTenant.user_id == actor.id
    )) is None:
        raise HTTPException(status_code=404, detail="Tenancy not found")
    documents = db.scalars(select(TenancyDocument).where(
        TenancyDocument.tenancy_id == tenancy_id,
        (TenancyDocument.tenant_visible.is_(True) if actor.role is Role.tenant else True),
    ).order_by(TenancyDocument.created_at.desc()).limit(100)).all()
    return [document_metadata(item) for item in documents]


@router.post("/tenancies/{tenancy_id}/documents", status_code=201)
async def upload_tenancy_document(
    tenancy_id: UUID,
    request: Request,
    actor: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    if db.get(Tenancy, tenancy_id) is None:
        raise HTTPException(status_code=404, detail="Tenancy not found")
    filename = request.headers.get("x-document-name", "").replace("\\", "/").split("/")[-1]
    filename = "".join(character for character in filename if character >= " " and character != "\x7f").strip()
    if not filename or len(filename) > 255 or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Choose a PDF file with a valid filename")
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/pdf":
        raise HTTPException(status_code=415, detail="Only PDF documents are accepted")
    temp_path: str | None = None
    stored_key: str | None = None
    total = 0
    header = bytearray()
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix="upload-", suffix=".tmp", delete=False) as target:
            temp_path = target.name
            async for chunk in request.stream():
                total += len(chunk)
                if total > DOCUMENT_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="Document exceeds the 10 MB limit")
                if len(header) < 5:
                    header.extend(chunk[:5 - len(header)])
                target.write(chunk)
        if total == 0 or bytes(header) != b"%PDF-":
            raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF")
        document_id = uuid4()
        storage_key = f"{document_id.hex}.pdf"
        try:
            save_private_file(storage_key, Path(temp_path), "application/pdf")
        except PrivateStorageError as exc:
            raise HTTPException(status_code=502, detail="Could not store the document") from exc
        temp_path = None
        stored_key = storage_key
        document = TenancyDocument(id=document_id, tenancy_id=tenancy_id, uploaded_by=actor.id,
            storage_key=storage_key, original_name=filename, content_type="application/pdf", byte_size=total)
        db.add(document)
        db.add(AuditLog(actor_id=actor.id, action="document.uploaded", target_type="tenancy_document",
                        target_id=str(document.id)))
        db.commit()
        stored_key = None
        return document_metadata(document)
    except HTTPException:
        db.rollback()
        if stored_key:
            delete_private_file(stored_key)
        raise
    except Exception:
        db.rollback()
        if stored_key:
            delete_private_file(stored_key)
        raise
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


@router.get("/documents/{document_id}/download")
def download_tenancy_document(
    document_id: UUID,
    actor: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    document = db.get(TenancyDocument, document_id)
    if document is None or not tenancy_document_access(db, document, actor):
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        content = read_private_file(document.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except PrivateStorageError as exc:
        raise HTTPException(status_code=502, detail="Could not retrieve the document") from exc
    return Response(content=content, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.original_name, safe='')}",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


def inspection_access(db: Session, inspection: Inspection, actor: User) -> bool:
    if actor.role is Role.owner:
        return True
    if actor.role is not Role.tenant or not inspection.tenant_visible:
        return False
    return db.scalar(select(TenancyTenant.id).where(
        TenancyTenant.tenancy_id == inspection.tenancy_id, TenancyTenant.user_id == actor.id
    )) is not None


def inspection_evidence_item(media: InspectionMedia) -> dict[str, object]:
    return {"id": str(media.id), "item_id": str(media.item_id) if media.item_id else None,
            "name": media.original_name, "content_type": media.content_type,
            "byte_size": media.byte_size, "created_at": media.created_at.isoformat()}


def inspection_response(db: Session, inspection: Inspection) -> dict[str, object]:
    items = db.scalars(select(InspectionItem).where(
        InspectionItem.inspection_id == inspection.id
    ).order_by(InspectionItem.created_at, InspectionItem.id)).all()
    media = db.scalars(select(InspectionMedia).where(
        InspectionMedia.inspection_id == inspection.id
    ).order_by(InspectionMedia.created_at.desc()).limit(200)).all()
    media_by_item: dict[str | None, list[dict[str, object]]] = {}
    for attachment in media:
        media_by_item.setdefault(str(attachment.item_id) if attachment.item_id else None, []).append(
            inspection_evidence_item(attachment))
    return {"id": str(inspection.id), "tenancy_id": str(inspection.tenancy_id),
            "inspection_type": inspection.inspection_type, "inspected_on": inspection.inspected_on.isoformat(),
            "notes": inspection.notes, "tenant_visible": inspection.tenant_visible,
            "status": inspection.status, "created_at": inspection.created_at.isoformat(),
            "items": [{"id": str(item.id), "area": item.area, "item_name": item.item_name,
                       "condition": item.condition, "notes": item.notes,
                       "evidence": media_by_item.get(str(item.id), [])} for item in items],
            "evidence": media_by_item.get(None, [])}


@router.get("/inspections")
def list_inspections(db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> list[dict[str, object]]:
    inspections = db.scalars(select(Inspection).order_by(Inspection.inspected_on.desc(),
        Inspection.created_at.desc()).limit(300)).all()
    return [inspection_response(db, inspection) for inspection in inspections]


@router.get("/tenant/inspections")
def list_tenant_inspections(db: Session = Depends(get_db), actor: User = Depends(require_user)) -> list[dict[str, object]]:
    if actor.role is not Role.tenant:
        raise HTTPException(status_code=403, detail="Forbidden")
    inspections = db.scalars(select(Inspection).where(
        Inspection.tenant_visible.is_(True),
        Inspection.tenancy_id.in_(select(TenancyTenant.tenancy_id).where(TenancyTenant.user_id == actor.id)),
    ).order_by(Inspection.inspected_on.desc(), Inspection.created_at.desc()).limit(300)).all()
    return [inspection_response(db, inspection) for inspection in inspections]


@router.post("/inspections", status_code=201)
def create_inspection(body: InspectionCreate, request: Request, db: Session = Depends(get_db),
                      actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    if db.get(Tenancy, body.tenancy_id) is None:
        raise HTTPException(status_code=404, detail="Tenancy not found")
    inspection = Inspection(**body.model_dump(), created_by=actor.id, status="in_progress")
    db.add(inspection)
    db.flush()
    db.add(AuditLog(actor_id=actor.id, action="inspection.created", target_type="inspection",
                    target_id=str(inspection.id)))
    db.commit()
    return inspection_response(db, inspection)


@router.post("/inspections/{inspection_id}/items", status_code=201)
def add_inspection_item(inspection_id: UUID, body: InspectionItemCreate, request: Request,
                        db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    inspection = db.scalar(select(Inspection).where(Inspection.id == inspection_id).with_for_update())
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.status != "in_progress":
        raise HTTPException(status_code=409, detail="Completed inspections cannot be changed")
    item = InspectionItem(inspection_id=inspection.id, **body.model_dump())
    db.add(item)
    db.add(AuditLog(actor_id=actor.id, action="inspection.item_added", target_type="inspection",
                    target_id=str(inspection.id)))
    db.commit()
    return {"id": str(item.id), "inspection_id": str(inspection.id), "area": item.area,
            "item_name": item.item_name, "condition": item.condition, "notes": item.notes,
            "evidence": []}


@router.post("/inspections/{inspection_id}/complete")
def complete_inspection(inspection_id: UUID, request: Request, db: Session = Depends(get_db),
                        actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    inspection = db.scalar(select(Inspection).where(Inspection.id == inspection_id).with_for_update())
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.status == "completed":
        return inspection_response(db, inspection)
    items = db.scalars(select(InspectionItem).where(InspectionItem.inspection_id == inspection.id)).all()
    if not items or any(item.condition == "not_inspected" for item in items):
        raise HTTPException(status_code=422, detail="Inspect every checklist item before completing this inspection")
    inspection.status = "completed"
    db.add(AuditLog(actor_id=actor.id, action="inspection.completed", target_type="inspection",
                    target_id=str(inspection.id)))
    db.commit()
    return inspection_response(db, inspection)


@router.post("/inspections/{inspection_id}/evidence", status_code=201)
async def upload_inspection_evidence(inspection_id: UUID, request: Request, item_id: UUID | None = None,
                                     actor: User = Depends(require_owner), db: Session = Depends(get_db)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    inspection = db.scalar(select(Inspection).where(Inspection.id == inspection_id).with_for_update())
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.status != "in_progress":
        raise HTTPException(status_code=409, detail="Evidence cannot be added to a completed inspection")
    if item_id is not None and db.scalar(select(InspectionItem.id).where(
        InspectionItem.id == item_id, InspectionItem.inspection_id == inspection.id
    )) is None:
        raise HTTPException(status_code=404, detail="Inspection item not found")
    filename = request.headers.get("x-document-name", "").replace("\\", "/").split("/")[-1]
    filename = "".join(ch for ch in filename if ch >= " " and ch != "\x7f").strip()
    if not filename or len(filename) > 255:
        raise HTTPException(status_code=422, detail="Choose a file with a valid filename")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower().strip()
    temp_path: str | None = None
    stored_key: str | None = None
    total = 0
    header = bytearray()
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix="inspection-upload-", suffix=".tmp", delete=False) as target:
            temp_path = target.name
            async for chunk in request.stream():
                total += len(chunk)
                if total > DOCUMENT_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="Evidence file exceeds the 10 MB limit")
                if len(header) < 8:
                    header.extend(chunk[:8 - len(header)])
                target.write(chunk)
        extension = inspection_file_extension(content_type, bytes(header))
        if total == 0 or extension is None:
            raise HTTPException(status_code=415, detail="Evidence must be a valid PDF, JPEG, or PNG file")
        expected_suffix = {"application/pdf": ".pdf", "image/jpeg": (".jpg", ".jpeg"), "image/png": ".png"}[content_type]
        if (filename.lower().endswith(expected_suffix) if isinstance(expected_suffix, str)
            else filename.lower().endswith(expected_suffix)) is False:
            raise HTTPException(status_code=415, detail="File extension does not match its content type")
        media_id = uuid4()
        storage_key = f"inspection_{media_id.hex}{extension}"
        try:
            save_private_file(storage_key, Path(temp_path), content_type)
        except PrivateStorageError as exc:
            raise HTTPException(status_code=502, detail="Could not store inspection evidence") from exc
        temp_path = None
        stored_key = storage_key
        media = InspectionMedia(id=media_id, inspection_id=inspection.id, item_id=item_id,
            uploaded_by=actor.id, storage_key=storage_key, original_name=filename,
            content_type=content_type, byte_size=total)
        db.add(media)
        db.add(AuditLog(actor_id=actor.id, action="inspection.evidence_uploaded", target_type="inspection",
                        target_id=str(inspection.id)))
        db.commit()
        stored_key = None
        return inspection_evidence_item(media)
    except HTTPException:
        db.rollback()
        if stored_key:
            delete_private_file(stored_key)
        raise
    except Exception:
        db.rollback()
        if stored_key:
            delete_private_file(stored_key)
        raise
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


@router.get("/inspection-evidence/{media_id}/download")
def download_inspection_evidence(media_id: UUID, actor: User = Depends(require_user),
                                 db: Session = Depends(get_db)) -> Response:
    media = db.get(InspectionMedia, media_id)
    inspection = db.get(Inspection, media.inspection_id) if media else None
    if media is None or inspection is None or not inspection_access(db, inspection, actor):
        raise HTTPException(status_code=404, detail="Inspection evidence not found")
    try:
        content = read_private_file(media.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Inspection evidence not found")
    except PrivateStorageError as exc:
        raise HTTPException(status_code=502, detail="Could not retrieve inspection evidence") from exc
    return Response(content=content, media_type=media.content_type, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(media.original_name, safe='')}",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.post("/tenancies/{tenancy_id}/close")
def close_tenancy(
    tenancy_id: UUID,
    body: TenancyClose,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, str]:
    verify_csrf(request, db, session_from_request(request, db))
    tenancy = db.get(Tenancy, tenancy_id)
    if tenancy is None or tenancy.status is not TenancyStatus.active:
        raise HTTPException(status_code=404, detail="Active tenancy not found")
    if body.move_out_date <= tenancy.start_date or (tenancy.end_date and body.move_out_date > tenancy.end_date):
        raise HTTPException(status_code=422, detail="Move-out date is outside the active tenancy period")
    tenancy.end_date = body.move_out_date
    tenancy.status = TenancyStatus.closed
    participation = db.scalar(select(TenancyTenant).where(
        TenancyTenant.tenancy_id == tenancy.id, TenancyTenant.end_date.is_(None)))
    if participation:
        participation.end_date = body.move_out_date
    terms = db.scalar(select(RentTerm).where(RentTerm.tenancy_id == tenancy.id, RentTerm.effective_to.is_(None)))
    if terms and body.move_out_date > terms.effective_from:
        terms.effective_to = body.move_out_date
    db.add(AuditLog(actor_id=actor.id, action="tenancy.closed", target_type="tenancy",
                    target_id=str(tenancy.id)))
    db.commit()
    return {"id": str(tenancy.id), "status": tenancy.status.value, "end_date": body.move_out_date.isoformat()}


@router.post("/tenancies/{tenancy_id}/charges/rent/{billing_month}", status_code=201)
def post_monthly_rent(
    tenancy_id: UUID,
    billing_month: date,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    try:
        charge = generate_monthly_rent(db, tenancy_id, billing_month, actor.id)
        db.commit()
    except LedgerError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A rent charge already exists for this billing period") from exc
    return {"id": str(charge.id), "amount": str(charge.amount), "currency": charge.currency,
            "due_date": charge.due_date.isoformat(), "snapshot": charge.calculation_snapshot}


def late_fee_rule_response(rule: LateFeeRule | None) -> dict[str, object]:
    if rule is None:
        return {"enabled": False, "fee_type": "fixed", "amount": "0.00", "grace_days": 0,
                "cap": None, "partial_payment_basis": "remaining_principal", "effective_from": None}
    return {"id": str(rule.id), "enabled": rule.amount > 0, "fee_type": rule.fee_type,
            "amount": str(rule.amount), "grace_days": rule.grace_days,
            "cap": str(rule.cap) if rule.cap is not None else None,
            "partial_payment_basis": rule.partial_payment_basis,
            "effective_from": rule.effective_from.isoformat()}


@router.get("/tenancies/{tenancy_id}/late-fees")
def get_tenancy_late_fees(tenancy_id: UUID, db: Session = Depends(get_db),
                          actor: User = Depends(require_owner)) -> dict[str, object]:
    if db.get(Tenancy, tenancy_id) is None:
        raise HTTPException(status_code=404, detail="Tenancy not found")
    rule = active_late_fee_rule(db, tenancy_id, date.today())
    assessed = select(LateFeeAssessment.rent_charge_id.label("rent_charge_id"),
        func.sum(LateFeeAssessment.fee_amount).label("amount")).group_by(
            LateFeeAssessment.rent_charge_id).subquery()
    charges = db.execute(select(Charge, func.coalesce(assessed.c.amount, 0))
        .outerjoin(assessed, assessed.c.rent_charge_id == Charge.id)
        .where(Charge.tenancy_id == tenancy_id, Charge.charge_type == "rent",
               Charge.due_date < date.today())
        .order_by(Charge.due_date, Charge.period_start).limit(200)).all()
    assessed_today = set(db.scalars(select(LateFeeAssessment.rent_charge_id).where(
        LateFeeAssessment.as_of_date == date.today()
    )).all())
    eligible = []
    for charge, fee_total in charges:
        principal = outstanding_charge(db, charge)
        if principal > 0:
            eligible.append({"id": str(charge.id), "period_start": charge.period_start.isoformat(),
                "due_date": charge.due_date.isoformat(), "amount": str(charge.amount),
                "principal_remaining": str(principal), "late_fees_assessed": str(fee_total),
                "assessed_today": charge.id in assessed_today})
    return {"rule": late_fee_rule_response(rule), "eligible_charges": eligible,
            "assessment_date": date.today().isoformat()}


@router.put("/tenancies/{tenancy_id}/late-fees/rule")
def put_tenancy_late_fee_rule(tenancy_id: UUID, body: LateFeeRuleUpdate, request: Request,
                              db: Session = Depends(get_db), actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    if body.enabled and body.amount <= 0:
        raise HTTPException(status_code=422, detail="Enter a positive late fee amount, or turn late fees off")
    if body.enabled and body.fee_type == "percentage" and body.amount > 100:
        raise HTTPException(status_code=422, detail="Percentage late fee cannot exceed 100 percent")
    amount = body.amount if body.enabled else Decimal("0.00")
    try:
        rule = save_late_fee_rule(db, tenancy_id=tenancy_id, actor_id=actor.id,
            fee_type=body.fee_type, amount=amount, grace_days=body.grace_days,
            cap=body.cap if body.enabled else None,
            partial_payment_basis=body.partial_payment_basis, effective_from=body.effective_from)
        db.commit()
    except LedgerError as exc:
        db.rollback()
        status = 404 if str(exc) == "Tenancy not found" else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Late fee rule conflicts with an existing effective date") from exc
    return late_fee_rule_response(rule)


@router.post("/charges/{rent_charge_id}/late-fee", status_code=201)
def post_late_fee(rent_charge_id: UUID, request: Request, db: Session = Depends(get_db),
                  actor: User = Depends(require_owner)) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    try:
        assessment, fee_charge, created = assess_late_fee(
            db, rent_charge_id=rent_charge_id, as_of_date=date.today(), actor_id=actor.id)
        db.commit()
    except LedgerError as exc:
        db.rollback()
        status = 404 if "not found" in str(exc).lower() else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A late fee has already been assessed for today") from exc
    return {"id": str(assessment.id), "rent_charge_id": str(assessment.rent_charge_id),
            "fee_charge_id": str(fee_charge.id) if fee_charge else None,
            "as_of_date": assessment.as_of_date.isoformat(), "days_past_due": assessment.days_past_due,
            "principal_remaining": str(assessment.principal_remaining),
            "cumulative_target": str(assessment.cumulative_target),
            "fee_amount": str(assessment.fee_amount), "created": created}


@router.post("/payments", status_code=201)
def post_payment(
    body: PaymentCreate,
    request: Request,
    idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, str]:
    verify_csrf(request, db, session_from_request(request, db))
    body_for_hash = body.model_dump(mode="json")
    fingerprint = hashlib.sha256(json.dumps(body_for_hash, sort_keys=True).encode()).hexdigest()
    try:
        payment, created = record_payment(
            db, tenancy_id=body.tenancy_id, tenant_id=body.tenant_id, actor_id=actor.id,
            amount=body.amount, method=body.method, received_at=body.received_at,
            idempotency_key=idempotency_key, request_hash=fingerprint,
            reference_code=body.reference_code)
        db.commit()
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LedgerError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Payment conflicts with an existing request") from exc
    credit = db.scalar(select(TenantCredit).where(TenantCredit.payment_id == payment.id))
    if created:
        tenant = db.get(User, payment.tenant_id)
        preference = db.get(TenantNotificationPreference, payment.tenant_id)
        profile = db.get(TenantProfile, payment.tenant_id)
        if tenant and preference:
            send_payment_receipt(
                email=tenant.email if preference.email_enabled else None,
                whatsapp_phone=preference.whatsapp_phone if preference.whatsapp_enabled else None,
                name=profile.display_name if profile else tenant.email,
                amount=payment.amount,
                method=payment.method,
                received_at=payment.received_at,
                payment_id=str(payment.id),
            )
    return {"id": str(payment.id), "status": "recorded", "amount": str(payment.amount),
            "credit_id": str(credit.id) if credit else "", "created": str(created).lower()}


@router.get("/payments")
def list_payments(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> list[dict[str, object]]:
    rows = db.execute(select(Payment, User, Tenancy, Unit, Property, TenantProfile, PaymentReversal)
        .join(User, User.id == Payment.tenant_id)
        .join(Tenancy, Tenancy.id == Payment.tenancy_id)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .join(Property, Property.id == Unit.property_id)
        .outerjoin(TenantProfile, TenantProfile.user_id == User.id)
        .outerjoin(PaymentReversal, PaymentReversal.payment_id == Payment.id)
        .order_by(Payment.received_at.desc()).offset(offset).limit(limit)).all()
    return [{"id": str(payment.id), "amount": str(payment.amount), "currency": payment.currency,
             "method": payment.method, "reference_code": payment.reference_code,
             "received_at": payment.received_at.isoformat(), "tenant": profile.display_name if profile else tenant.email,
             "property": property_row.name, "unit": unit.unit_number, "tenancy_id": str(tenancy.id),
             "status": "reversed" if reversal else "recorded",
             "can_reverse": reversal is None and not db.scalar(select(TenantCredit.id).join(
                 CreditAllocation, CreditAllocation.credit_id == TenantCredit.id
             ).where(TenantCredit.payment_id == payment.id)) and not db.scalar(select(PaymentAllocation.id).where(
                 PaymentAllocation.payment_id == payment.id))}
            for payment, tenant, tenancy, unit, property_row, profile, reversal in rows]


@router.post("/payments/{payment_id}/reverse", status_code=201)
def post_payment_reversal(
    payment_id: UUID,
    body: PaymentReversalCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, str]:
    verify_csrf(request, db, session_from_request(request, db))
    try:
        reversal = reverse_payment(db, payment_id=payment_id, actor_id=actor.id, reason=body.reason)
        db.commit()
    except LedgerError as exc:
        db.rollback()
        status = 404 if str(exc) == "Payment not found" else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Payment has already been reversed") from exc
    return {"id": str(reversal.id), "payment_id": str(reversal.payment_id),
            "amount": str(reversal.amount), "status": "reversed"}


@router.get("/payments/{payment_id}/receipt", response_class=HTMLResponse)
def payment_receipt(
    payment_id: UUID,
    actor: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    row = db.execute(select(Payment, Tenancy, Unit, Property, User, TenantProfile, PaymentReversal)
        .join(Tenancy, Tenancy.id == Payment.tenancy_id)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .join(Property, Property.id == Unit.property_id)
        .join(User, User.id == Payment.tenant_id)
        .outerjoin(TenantProfile, TenantProfile.user_id == User.id)
        .outerjoin(PaymentReversal, PaymentReversal.payment_id == Payment.id)
        .where(Payment.id == payment_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    payment, tenancy, unit, property_row, tenant, profile, reversal = row
    if actor.role is Role.tenant and payment.tenant_id != actor.id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    tenant_name = profile.display_name if profile else tenant.email
    status = "Reversed" if reversal else "Recorded"
    reversal_detail = f"<p><b>Reversal reason:</b> {esc(reversal.reason)}</p>" if reversal else ""
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Payment receipt</title><style>body{{font:16px system-ui,sans-serif;color:#242733;margin:0;padding:40px;background:#f7f8fa}}main{{max-width:640px;margin:0 auto;background:white;border:1px solid #e5e7ed;border-radius:12px;padding:32px}}h1{{font-size:24px}}.amount{{font-size:30px;font-weight:700;color:#504bb0}}small{{color:#737783}}@media print{{body{{background:white;padding:0}}main{{border:0;max-width:none}}}}</style></head><body><main><small>HEARTH · PAYMENT RECEIPT</small><h1>{esc(property_row.name)} · Apartment {esc(unit.unit_number)}</h1><p class="amount">₹{esc(payment.amount)}</p><p><b>Status:</b> {esc(status)}</p><p><b>Tenant:</b> {esc(tenant_name)}</p><p><b>Received:</b> {esc(payment.received_at.isoformat())}</p><p><b>Method:</b> {esc(payment.method.replace('_', ' '))}</p><p><b>Reference:</b> {esc(payment.reference_code or '—')}</p><p><b>Receipt ID:</b> {esc(payment.id)}</p>{reversal_detail}<small>Keep this receipt with your tenancy records.</small></main></body></html>"""
    return HTMLResponse(body, headers={"Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"})


@router.post("/credits/{credit_id}/allocations", status_code=201)
def post_credit_allocation(
    credit_id: UUID,
    body: CreditAllocationCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, str]:
    verify_csrf(request, db, session_from_request(request, db))
    try:
        allocation = allocate_credit(db, credit_id=credit_id, charge_id=body.charge_id,
                                     amount=body.amount, actor_id=actor.id)
        db.commit()
    except LedgerError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": str(allocation.id), "amount": str(allocation.amount), "status": "allocated"}


@router.get("/properties")
def list_properties(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> list[dict[str, object]]:
    if actor.role is not Role.owner:
        raise HTTPException(status_code=403, detail="Forbidden")
    rows = db.scalars(select(Property).where(Property.archived.is_(False)).offset(offset).limit(limit))
    return [
        {"id": str(row.id), "name": row.name, "address": row.address, "timezone": row.timezone}
        for row in rows
    ]


@router.post("/properties", status_code=201)
def create_property(
    request: Request,
    body: PropertyCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, object]:
    verify_csrf(request, db, session_from_request(request, db))
    if actor.role is not Role.owner:
        raise HTTPException(status_code=403, detail="Forbidden")
    row = Property(**body.model_dump())
    db.add(row)
    db.flush()
    db.add(AuditLog(actor_id=actor.id, action="property.created", target_type="property", target_id=str(row.id)))
    db.commit()
    return {"id": str(row.id), "name": row.name, "address": row.address, "timezone": row.timezone}


@router.patch("/properties/{property_id}")
def update_property(
    property_id: UUID,
    body: PropertyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, str]:
    verify_csrf(request, db, session_from_request(request, db))
    row = db.get(Property, property_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="Property not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, key, value)
    db.add(AuditLog(actor_id=actor.id, action="property.updated", target_type="property",
                    target_id=str(row.id)))
    db.commit()
    return {"id": str(row.id), "name": row.name, "address": row.address, "timezone": row.timezone}


@router.get("/properties/{property_id}/units")
def list_units(
    property_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> list[dict[str, str]]:
    property_row = db.get(Property, property_id)
    if property_row is None or property_row.archived:
        raise HTTPException(status_code=404, detail="Property not found")
    rows = db.scalars(select(Unit).where(Unit.property_id == property_id, Unit.active.is_(True)).order_by(Unit.unit_number))
    return [{"id": str(row.id), "unit_number": row.unit_number} for row in rows]


@router.post("/properties/{property_id}/units", status_code=201)
def create_unit(
    property_id: UUID,
    body: UnitCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> dict[str, str]:
    verify_csrf(request, db, session_from_request(request, db))
    property_row = db.get(Property, property_id)
    if property_row is None or property_row.archived:
        raise HTTPException(status_code=404, detail="Property not found")
    unit = Unit(property_id=property_id, unit_number=body.unit_number.strip())
    db.add(unit)
    try:
        db.flush()
        db.add(AuditLog(actor_id=actor.id, action="unit.created", target_type="unit", target_id=str(unit.id)))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That apartment identifier already exists for this property") from exc
    return {"id": str(unit.id), "unit_number": unit.unit_number}


@router.delete("/properties/{property_id}", status_code=204)
def archive_property(
    request: Request,
    property_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_owner),
) -> Response:
    verify_csrf(request, db, session_from_request(request, db))
    if actor.role is not Role.owner:
        raise HTTPException(status_code=403, detail="Forbidden")
    row = db.get(Property, property_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Property not found")
    row.archived = True
    db.add(AuditLog(actor_id=actor.id, action="property.archived", target_type="property", target_id=str(row.id)))
    db.commit()
    return Response(status_code=204)
