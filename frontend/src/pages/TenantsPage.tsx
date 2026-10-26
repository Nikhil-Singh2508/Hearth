import { useEffect, useState } from 'react'
import { ApiError, onboardingApi, propertyApi, type Invitation, type Property, type Tenant, type Unit } from '../lib/api'

type IssuedInvite = Invitation & { token: string }

export default function TenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [properties, setProperties] = useState<Property[]>([])
  const [units, setUnits] = useState<Unit[]>([])
  const [propertyId, setPropertyId] = useState('')
  const [issued, setIssued] = useState<IssuedInvite | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  async function refresh() {
    const [tenantRows, invitationRows, propertyRows] = await Promise.all([
      onboardingApi.tenants(), onboardingApi.invitations(), propertyApi.list(),
    ])
    setTenants(tenantRows); setInvitations(invitationRows); setProperties(propertyRows)
  }
  useEffect(() => { refresh().catch(() => setError('Could not load tenant information.')) }, [])
  useEffect(() => {
    setUnits([])
    if (propertyId) propertyApi.units(propertyId).then(setUnits).catch(() => setError('Could not load apartments for this property.'))
  }, [propertyId])

  async function invite(form: HTMLFormElement) {
    const email = new FormData(form).get('email')?.toString().trim() ?? ''
    setError(''); setNotice(''); setBusy(true); setIssued(null)
    try { setIssued(await onboardingApi.invite(email)); form.reset(); await refresh() }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not create the invitation.') }
    finally { setBusy(false) }
  }
  async function revoke(id: string) {
    setError(''); setNotice(''); setBusy(true)
    try { await onboardingApi.revoke(id); setNotice('Invitation revoked.'); await refresh() }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not revoke the invitation.') }
    finally { setBusy(false) }
  }
  async function createTenancy(form: HTMLFormElement) {
    const data = new FormData(form)
    setError(''); setNotice(''); setBusy(true)
    try {
      await onboardingApi.createTenancy({
        unit_id: String(data.get('unit_id')), tenant_id: String(data.get('tenant_id')),
        start_date: String(data.get('start_date')), monthly_rent: String(data.get('monthly_rent')),
        security_deposit_expected: String(data.get('security_deposit_expected') || '0'),
        due_day: Number(data.get('due_day')), proration_method: String(data.get('proration_method')),
      })
      setNotice('Tenancy created and rent terms recorded.'); form.reset()
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not create the tenancy.') }
    finally { setBusy(false) }
  }

  return <div className="content tenants-page">
    <div className="page-heading"><div><div className="eyebrow">PEOPLE &amp; LEASES</div><h1>Tenants</h1><p>Invite tenant accounts and connect them to an apartment and rent terms.</p></div></div>
    {error && <div className="form-alert" role="alert">{error}</div>}{notice && <div className="success-banner" role="status">{notice}</div>}
    <div className="tenant-admin-grid">
      <section className="panel"><div className="panel-head"><div><h3>Invite a tenant</h3><p>The invitation token is shown once. Share it with the tenant securely.</p></div></div>
        <form className="onboarding-form" onSubmit={e => { e.preventDefault(); void invite(e.currentTarget) }}>
          <label htmlFor="invite-email">Tenant email</label><input id="invite-email" name="email" type="email" autoComplete="email" required />
          <button className="button primary" disabled={busy}>Create invitation</button>
        </form>
        {issued && <div className="issued-invite"><b>Invitation token · expires {new Date(issued.expires_at).toLocaleDateString()}</b><code>{issued.token}</code><button className="button secondary" onClick={() => void navigator.clipboard?.writeText(issued.token)}>Copy token</button><small>Send the tenant the token and this link: {`${window.location.origin}/accept-invitation`}</small></div>}
        <div className="subsection"><h4>Pending invitations</h4>{invitations.length === 0 ? <p className="quiet">No pending invitations.</p> : invitations.map(item => <div className="tenant-row" key={item.id}><span><b>{item.email}</b><small>Expires {new Date(item.expires_at).toLocaleDateString()}</small></span><button className="button secondary" disabled={busy} onClick={() => void revoke(item.id)}>Revoke</button></div>)}</div>
      </section>
      <section className="panel"><div className="panel-head"><div><h3>Active tenant accounts</h3><p>{tenants.length} tenant{tenants.length === 1 ? '' : 's'} have accepted an invitation.</p></div></div>
        {tenants.length === 0 ? <p className="quiet">Accepted tenant accounts will appear here.</p> : tenants.map(t => <div className="tenant-row" key={t.id}><span><b>{t.display_name}</b><small>{t.email}</small></span><i className="request-status">Active account</i></div>)}
      </section>
    </div>
    <section className="panel tenancy-create"><div className="panel-head"><div><h3>Link a tenant to an apartment</h3><p>Create the tenancy and set its initial rent terms.</p></div></div>
      {tenants.length === 0 ? <p className="quiet">Invite a tenant and have them accept before creating a tenancy.</p> : <form className="onboarding-form tenancy-form" onSubmit={e => { e.preventDefault(); void createTenancy(e.currentTarget) }}>
        <label htmlFor="tenant-id">Tenant</label><select id="tenant-id" name="tenant_id" required defaultValue=""><option value="" disabled>Select a tenant</option>{tenants.map(t => <option key={t.id} value={t.id}>{t.display_name} · {t.email}</option>)}</select>
        <label htmlFor="property-id">Property</label><select id="property-id" value={propertyId} onChange={e => setPropertyId(e.target.value)} required><option value="">Select a property</option>{properties.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <label htmlFor="unit-id">Apartment</label><select id="unit-id" name="unit_id" required defaultValue=""><option value="" disabled>Select an apartment</option>{units.map(u => <option key={u.id} value={u.id}>{u.unit_number}</option>)}</select>
        <label htmlFor="start-date">Start date</label><input id="start-date" name="start_date" type="date" required />
        <label htmlFor="monthly-rent">Monthly rent (INR)</label><input id="monthly-rent" name="monthly_rent" type="number" min="0.01" step="0.01" required />
        <label htmlFor="security-deposit">Agreed security deposit (INR)</label><input id="security-deposit" name="security_deposit_expected" type="number" min="0" step="0.01" defaultValue="0" />
        <label htmlFor="due-day">Rent due day</label><input id="due-day" name="due_day" type="number" min="1" max="31" defaultValue="1" required />
        <label htmlFor="proration">Proration</label><select id="proration" name="proration_method"><option value="actual">Actual days in month</option><option value="30_day">30-day month</option></select>
        <button className="button primary" disabled={busy || units.length === 0}>Create tenancy</button>
      </form>}
    </section>
  </div>
}
