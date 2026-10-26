import { useEffect, useState } from 'react'
import { API_URL, ApiError, inspectionsApi, tenantApi, type InspectionRecord, type TenantPortalData, type TenantNotificationPreferences } from '../lib/api'
import TenantMaintenancePanel from './TenantMaintenancePanel'
import TenantDocuments from './TenantDocuments'
import TenantInspections from './TenantInspections'

const money = (amount: string, currency: string) => new Intl.NumberFormat('en-IN', { style: 'currency', currency }).format(Number(amount))
const date = (value: string) => new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(`${value.slice(0, 10)}T00:00:00`))

export default function TenantPortalPage({ onSignOut }: { onSignOut: () => void }) {
  const [data, setData] = useState<TenantPortalData | null>(null)
  const [inspections, setInspections] = useState<InspectionRecord[]>([])
  const [preferences, setPreferences] = useState<TenantNotificationPreferences | null>(null)
  const [emailEnabled, setEmailEnabled] = useState(false)
  const [whatsappEnabled, setWhatsappEnabled] = useState(false)
  const [whatsappPhone, setWhatsappPhone] = useState('')
  const [savingPreferences, setSavingPreferences] = useState(false)
  const [preferenceNotice, setPreferenceNotice] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    Promise.all([tenantApi.portal(), inspectionsApi.tenantList(), tenantApi.notificationPreferences()]).then(([portal, rows, prefs]) => {
      setData(portal); setInspections(rows); setPreferences(prefs); setEmailEnabled(prefs.email_enabled)
      setWhatsappEnabled(prefs.whatsapp_enabled); setWhatsappPhone(prefs.whatsapp_phone ?? '')
    }).catch((cause: unknown) => setError(cause instanceof ApiError && cause.status === 401 ? 'Your session expired. Please sign in again.' : 'We could not load your tenancy information. Try again later.')).finally(() => setLoading(false))
  }, [])

  async function savePreferences(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSavingPreferences(true); setError(''); setPreferenceNotice('')
    try {
      const saved = await tenantApi.updateNotificationPreferences({ email_enabled: emailEnabled,
        whatsapp_enabled: whatsappEnabled, whatsapp_phone: whatsappEnabled ? whatsappPhone : null })
      setPreferences(saved); setWhatsappPhone(saved.whatsapp_phone ?? '')
      setPreferenceNotice('Your notification preferences and consent choices have been saved.')
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not save notification preferences.') }
    finally { setSavingPreferences(false) }
  }

  return <main className="content properties-page tenant-portal">
    <div className="page-heading"><div><div className="eyebrow">TENANT PORTAL</div><h1>Welcome, {data?.display_name ?? 'tenant'}</h1><p>Your tenancy and account activity.</p></div><div className="tenant-portal-actions"><a className="button secondary" href="/help">Help guide</a><button className="button secondary" onClick={onSignOut}>Sign out</button></div></div>
    {loading && <div className="panel loading-card" role="status">Loading your account…</div>}
    {error && <div className="form-alert" role="alert">{error}</div>}
    {!loading && !error && data?.tenancies.length === 0 && <div className="panel empty-state"><span>⌂</span><h3>No tenancy is linked to this account</h3><p>Contact your property manager if you think this is an error.</p></div>}
    {data?.tenancies.map((tenancy) => <section className="panel managed-property tenant-tenancy" key={tenancy.id}>
      <div className="managed-property-head"><div className="property-symbol">⌂</div><div className="managed-title"><h2>{tenancy.property} · Apartment {tenancy.unit}</h2><p>{date(tenancy.start_date)}{tenancy.end_date ? ` – ${date(tenancy.end_date)}` : ' · Current tenancy'}</p><small>{tenancy.rent ? `Monthly rent ${money(tenancy.rent, tenancy.rent_currency)}` : 'Rent details unavailable'}</small></div><span className="unit-chip">{tenancy.status}</span></div>
      <div className="units-heading"><div><b>Rent charges</b><span>{tenancy.charges.length} records</span></div></div>
      {tenancy.charges.length ? <div className="tenant-ledger">{tenancy.charges.map(charge => <div className="tenant-ledger-row" key={charge.id}><span><b>{charge.type.replace('_', ' ')}</b><small>{date(charge.period_start)} – {date(charge.period_end)} · due {date(charge.due_date)}</small></span><span><b>{money(charge.amount, charge.currency)}</b><small>{Number(charge.balance) > 0 ? `${money(charge.balance, charge.currency)} outstanding` : 'Paid'}</small></span></div>)}</div> : <p className="units-empty">No charges have been posted.</p>}
      <div className="units-heading"><div><b>Payments</b><span>{tenancy.payments.length} records</span></div></div>
      {tenancy.payments.length ? <div className="tenant-ledger">{tenancy.payments.map(payment => <div className="tenant-ledger-row" key={payment.id}><span><b>{money(payment.amount, payment.currency)}</b><small>{payment.method.replace('_', ' ')} · received {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(payment.received_at))}</small></span><span className="tenant-payment-actions"><span className={payment.status === 'reversed' ? 'request-status reversed' : 'payment-status'}>{payment.status === 'reversed' ? 'Reversed' : 'Recorded'}</span><a className="button secondary" href={`${API_URL}/api/payments/${payment.id}/receipt`} target="_blank" rel="noreferrer">Receipt</a></span></div>)}</div> : <p className="units-empty">No payments have been recorded.</p>}
      {tenancy.credits.length > 0 && <><div className="units-heading"><div><b>Unallocated account credits</b><span>{tenancy.credits.length} records</span></div></div><div className="tenant-ledger">{tenancy.credits.map(credit => <div className="tenant-ledger-row" key={credit.id}><span><b>{money(credit.amount, credit.currency)}</b><small>Available credit · {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(credit.created_at))}</small></span></div>)}</div></>}
      <div className="tenant-deposit"><div className="units-heading"><div><b>Security deposit</b><span>INR</span></div></div><div className="deposit-tenant-summary"><span>Agreed <b>{money(tenancy.security_deposit.expected, 'INR')}</b></span><span>Received <b>{money(tenancy.security_deposit.received, 'INR')}</b></span><span>Refunded <b>{money(tenancy.security_deposit.refunded, 'INR')}</b></span><span>Deductions <b>{money(tenancy.security_deposit.deducted, 'INR')}</b></span><span>Remaining balance <b>{money(tenancy.security_deposit.balance, 'INR')}</b></span></div>{tenancy.security_deposit.transactions.map(transaction => <div className="tenant-deposit-row" key={transaction.id}><span>{transaction.transaction_type}</span><b>{money(transaction.amount, 'INR')}</b><small>{transaction.reason || transaction.method?.replace('_', ' ') || '—'} · {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(transaction.occurred_at))}</small></div>)}</div>
      <TenantDocuments tenancyId={tenancy.id} />
      <TenantInspections tenancyId={tenancy.id} items={inspections} />
    </section>)}
    {data && <TenantMaintenancePanel tenancies={data.tenancies.map(({ id, property, unit, status }) => ({ id, property, unit, status }))} />}
    {preferences && <section className="panel notification-settings"><div className="panel-head"><div><h3>Notification preferences</h3><p>Choose whether Hearth may contact you through these channels. You can change your choices at any time.</p></div></div>
      {preferenceNotice && <div className="success-banner" role="status">{preferenceNotice}</div>}
      <form onSubmit={event => void savePreferences(event)}>
        <label className="notification-choice"><input type="checkbox" checked={emailEnabled} onChange={event => setEmailEnabled(event.target.checked)} /><span><b>Email notifications</b><small>Rent reminders, payment receipts, and maintenance updates to your account email.</small><em>{preferences.email_provider_enabled ? 'Email provider enabled' : 'Email provider not configured; no email will be sent yet'}</em></span></label>
        <label className="notification-choice"><input type="checkbox" checked={whatsappEnabled} onChange={event => { setWhatsappEnabled(event.target.checked); if (!event.target.checked) setWhatsappPhone('') }} /><span><b>WhatsApp notifications (optional)</b><small>Opt in to tenancy and maintenance updates on WhatsApp. Message or data charges may apply.</small><em>{preferences.whatsapp_provider_enabled ? 'WhatsApp provider enabled' : 'WhatsApp provider not configured; no message will be sent yet'}</em></span></label>
        {whatsappEnabled && <label className="notification-phone">WhatsApp phone number<input type="tel" autoComplete="tel" placeholder="+919876543210" pattern="\+[1-9][0-9]{7,14}" value={whatsappPhone} onChange={event => setWhatsappPhone(event.target.value)} required /><small>Use international format, including country code.</small></label>}
        <p className="notification-consent-copy">Saving an enabled channel records your consent. Disabling it withdraws consent and removes the saved WhatsApp number. Preferences are stored even while a delivery provider is unavailable; messages are not sent until a provider is configured.</p>
        <button className="button primary" disabled={savingPreferences}>{savingPreferences ? 'Saving…' : 'Save preferences'}</button>
      </form>
    </section>}
    <footer>For questions about a charge or payment, contact your property manager.</footer>
  </main>
}
