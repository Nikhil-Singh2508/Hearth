import pytest
from types import SimpleNamespace
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy.orm import Session

from app.api import (InvitationAccept, MaintenanceRequestCreate, MaintenanceStatusUpdate,
                     PaymentReversalCreate, require_owner, tenancy_document_access)
from app.database import SessionLocal
from app.models import Role
from app.schemas import PropertyCreate
from app.api import UnitCreate


def test_owner_dependency_denies_a_request_without_session_cookie():
    request = Request({"type": "http", "method": "GET", "path": "/api/properties",
                       "headers": [], "query_string": b"", "server": ("localhost", 80),
                       "client": ("127.0.0.1", 1), "scheme": "http"})
    db: Session = SessionLocal()
    try:
        with pytest.raises(HTTPException) as error:
            require_owner(request, db)
        assert error.value.status_code == 401
    finally:
        db.close()


def test_property_input_rejects_invalid_timezone_and_blank_names():
    with pytest.raises(ValueError):
        PropertyCreate(name="  ", address="Street 1")
    with pytest.raises(ValueError):
        PropertyCreate(name="Home", address="Street 1", timezone="Not/A_Timezone")


def test_unit_identifier_rejects_whitespace_only_input():
    with pytest.raises(ValueError):
        UnitCreate(unit_number="   ")


def test_invitation_password_minimum_is_eight_characters():
    accepted = InvitationAccept(token="t" * 30, password="12345678", display_name="Tenant")
    assert accepted.password == "12345678"
    with pytest.raises(ValueError):
        InvitationAccept(token="t" * 30, password="1234567", display_name="Tenant")


def test_maintenance_request_validates_content_and_status():
    body = MaintenanceRequestCreate(tenancy_id="d061413f-3942-4c9a-a813-f6456062c39d",
                                    subject="Leaking tap", description="Water is dripping under the sink.")
    assert body.subject == "Leaking tap"
    with pytest.raises(ValueError):
        MaintenanceRequestCreate(tenancy_id="d061413f-3942-4c9a-a813-f6456062c39d",
                                 subject="  ", description="Water is dripping under the sink.")
    with pytest.raises(ValueError):
        MaintenanceStatusUpdate(status="delete")


def test_tenancy_document_access_is_owner_or_tenant_membership_scoped():
    owner = SimpleNamespace(role=Role.owner, id="owner")
    tenant = SimpleNamespace(role=Role.tenant, id="tenant")
    document = SimpleNamespace(tenancy_id="tenancy", tenant_visible=True)

    class MembershipDb:
        def __init__(self, member):
            self.member = member

        def scalar(self, _query):
            return "membership" if self.member else None

    assert tenancy_document_access(MembershipDb(False), document, owner)
    assert tenancy_document_access(MembershipDb(True), document, tenant)
    assert not tenancy_document_access(MembershipDb(False), document, tenant)
    hidden = SimpleNamespace(tenancy_id="tenancy", tenant_visible=False)
    assert not tenancy_document_access(MembershipDb(True), hidden, tenant)


def test_payment_reversal_requires_a_nonblank_explanation():
    assert PaymentReversalCreate(reason="  Duplicate payment  ").reason == "Duplicate payment"
    with pytest.raises(ValueError):
        PaymentReversalCreate(reason="   ")
