"""Invitation-only tenant onboarding and effective-dated tenancy terms."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_tenant_lifecycle"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    tenancy_status = postgresql.ENUM("active", "closed", "cancelled", name="tenancy_status", create_type=False)
    tenancy_status.create(op.get_bind())
    op.create_table("tenant_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_tenant_invitations_email", "tenant_invitations", ["email"])
    op.create_index("uq_pending_tenant_invitation_email", "tenant_invitations", [sa.text("lower(email)")], unique=True,
                    postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"))
    op.create_table("tenancies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False), sa.Column("end_date", sa.Date()),
        sa.Column("status", tenancy_status, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("end_date IS NULL OR start_date < end_date", name="ck_tenancy_valid_period"))
    op.create_index("ix_tenancies_unit_id", "tenancies", ["unit_id"])
    op.execute("ALTER TABLE tenancies ADD CONSTRAINT ex_active_tenancy_unit_period EXCLUDE USING gist (unit_id WITH =, daterange(start_date, end_date, '[)') WITH &&) WHERE (status = 'active')")
    op.create_table("tenancy_tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False), sa.Column("end_date", sa.Date()),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("financially_responsible", sa.Boolean(), nullable=False),
        sa.CheckConstraint("end_date IS NULL OR start_date < end_date", name="ck_participation_valid_period"))
    op.create_index("ix_tenancy_tenants_tenancy_id", "tenancy_tenants", ["tenancy_id"])
    op.create_index("ix_tenancy_tenants_user_id", "tenancy_tenants", ["user_id"])
    op.create_index("uq_current_primary_tenant", "tenancy_tenants", ["tenancy_id"], unique=True,
                    postgresql_where=sa.text("is_primary AND end_date IS NULL"))
    op.create_table("rent_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenancies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False), sa.Column("effective_to", sa.Date()),
        sa.Column("monthly_rent", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False), sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("proration_method", sa.String(12), nullable=False),
        sa.CheckConstraint("monthly_rent >= 0", name="ck_rent_nonnegative"),
        sa.CheckConstraint("due_day BETWEEN 1 AND 31", name="ck_rent_due_day"),
        sa.CheckConstraint("proration_method IN ('actual', '30_day')", name="ck_rent_proration_method"),
        sa.CheckConstraint("effective_to IS NULL OR effective_from < effective_to", name="ck_rent_term_valid_period"))
    op.create_index("ix_rent_terms_tenancy_id", "rent_terms", ["tenancy_id"])
    op.execute("ALTER TABLE rent_terms ADD CONSTRAINT ex_rent_term_period EXCLUDE USING gist (tenancy_id WITH =, daterange(effective_from, effective_to, '[)') WITH &&)")

def downgrade():
    op.drop_table("rent_terms")
    op.drop_index("uq_current_primary_tenant", table_name="tenancy_tenants")
    op.drop_index("ix_tenancy_tenants_user_id", table_name="tenancy_tenants")
    op.drop_index("ix_tenancy_tenants_tenancy_id", table_name="tenancy_tenants")
    op.drop_table("tenancy_tenants")
    op.drop_constraint("ex_active_tenancy_unit_period", "tenancies", type_="exclude")
    op.drop_index("ix_tenancies_unit_id", table_name="tenancies")
    op.drop_table("tenancies")
    op.drop_index("uq_pending_tenant_invitation_email", table_name="tenant_invitations")
    op.drop_index("ix_tenant_invitations_email", table_name="tenant_invitations")
    op.drop_table("tenant_invitations")
    sa.Enum(name="tenancy_status").drop(op.get_bind())
