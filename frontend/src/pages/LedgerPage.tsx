import { useEffect, useState } from 'react'
import { API_URL, ApiError, documentsApi, lateFeesApi, paymentsApi, type LateFeeData, type OwnerPayment, type TenancySummary } from '../lib/api'

const receiptDate = (value: string) => new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function LateFeesPanel({ tenancies }: { tenancies: TenancySummary[] }) {
  const [tenancyId, setTenancyId] = useState('')
  const [data, setData] = useState<LateFeeData | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [feeType, setFeeType] = useState<'fixed' | 'daily' | 'percentage'>('fixed')
  const [amount, setAmount] = useState('')
  const [graceDays, setGraceDays] = useState('0')
  const [cap, setCap] = useState('')
  const [basis, setBasis] = useState<'remaining_principal' | 'original_principal'>('remaining_principal')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function load(id: string) {
    if (!id) { setData(null); return }
    const result = await lateFeesApi.get(id)
    setData(result); setEnabled(result.rule.enabled); setFeeType(result.rule.fee_type)
    setAmount(result.rule.amount); setGraceDays(String(result.rule.grace_days))
    setCap(result.rule.cap ?? ''); setBasis(result.rule.partial_payment_basis)
  }
  useEffect(() => { if (tenancyId) void load(tenancyId).catch(() => setError('Could not load late fee details.')) }, [tenancyId])

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy('save'); setError(''); setNotice('')
    try {
      await lateFeesApi.updateRule(tenancyId, { enabled, fee_type: feeType, amount: enabled ? amount : '0',
        grace_days: Number(graceDays), cap: enabled && cap ? cap : null, partial_payment_basis: basis })
      await load(tenancyId); setNotice('Late fee rule saved.')
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not save the late fee rule.') }
    finally { setBusy('') }
  }

  async function assess(chargeId: string) {
    setBusy(chargeId); setError(''); setNotice('')
    try {
      const result = await lateFeesApi.assess(chargeId); await load(tenancyId)
      setNotice(result.created ? `Late fee of ₹${Number(result.fee_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })} posted.` : 'This charge was already assessed today.')
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not assess the late fee.') }
    finally { setBusy('') }
  }

  return <section className="panel late-fees-panel">
    <div className="panel-head"><div><h3>Late fees</h3><p>Configure an effective rule and assess fees against overdue rent.</p></div></div>
    <label className="late-fee-tenancy">Tenancy<select value={tenancyId} onChange={event => { setTenancyId(event.target.value); setError(''); setNotice('') }}><option value="">Select tenancy</option>{tenancies.map(t => <option key={t.id} value={t.id}>{t.property} · Apt {t.unit} · {t.tenant}</option>)}</select></label>
    {error && <div className="form-alert" role="alert">{error}</div>}{notice && <div className="success-banner" role="status">{notice}</div>}
    {tenancyId && <>
      <form className="late-fee-form" onSubmit={save}>
        <label className="late-fee-enable"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} /> Enable late fees</label>
        <label>Fee type<select value={feeType} onChange={event => setFeeType(event.target.value as typeof feeType)}><option value="fixed">One-time fixed</option><option value="daily">Daily</option><option value="percentage">Percentage</option></select></label>
        <label>{feeType === 'percentage' ? 'Percent' : 'Amount (INR)'}<input type="number" min="0" step="0.01" max={feeType === 'percentage' ? 100 : undefined} value={amount} onChange={event => setAmount(event.target.value)} disabled={!enabled} required /></label>
        <label>Grace days<input type="number" min="0" max="365" step="1" value={graceDays} onChange={event => setGraceDays(event.target.value)} disabled={!enabled} required /></label>
        <label>Maximum total fee (optional)<input type="number" min="0" step="0.01" value={cap} onChange={event => setCap(event.target.value)} disabled={!enabled} /></label>
        <label>Partial payment basis<select value={basis} onChange={event => setBasis(event.target.value as typeof basis)} disabled={!enabled}><option value="remaining_principal">Remaining rent balance</option><option value="original_principal">Original rent amount</option></select></label>
        <button className="button primary" disabled={busy === 'save'}>{busy === 'save' ? 'Saving…' : 'Save rule'}</button>
      </form>
      <p className="ledger-note">Daily fees catch up through today when assessed. Fees are calculated on rent only; late fees never accrue on previous fees. Rules apply from today.</p>
      <div className="late-fee-charge-list"><h4>Overdue rent charges</h4>
        {!data ? <p>Loading overdue charges…</p> : data.eligible_charges.length === 0 ? <p>No unpaid rent is overdue for this tenancy.</p> : data.eligible_charges.map(charge => <div className="late-fee-charge" key={charge.id}>
          <div><b>Rent due {receiptDate(charge.due_date + 'T00:00:00')}</b><small>Balance ₹{Number(charge.principal_remaining).toLocaleString('en-IN', { minimumFractionDigits: 2 })} · fees assessed ₹{Number(charge.late_fees_assessed).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</small></div>
          <button className="button secondary" disabled={!data.rule.enabled || charge.assessed_today || busy === charge.id} onClick={() => void assess(charge.id)}>{busy === charge.id ? 'Assessing…' : charge.assessed_today ? 'Assessed today' : 'Assess today'}</button>
        </div>)}
      </div>
    </>}
  </section>
}

export default function LedgerPage() {
  const [payments, setPayments] = useState<OwnerPayment[]>([])
  const [tenancies, setTenancies] = useState<TenancySummary[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  async function refresh() { setPayments(await paymentsApi.list()) }
  useEffect(() => { Promise.all([refresh(), documentsApi.tenancies().then(setTenancies)]).catch(() => setError('Could not load payment records.')).finally(() => setLoading(false)) }, [])

  async function record(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setNotice('')
    const form = event.currentTarget
    const data = new FormData(form)
    const tenancy = tenancies.find(item => item.id === String(data.get('tenancy_id')))
    if (!tenancy?.tenant_id) { setError('Select a tenancy with an assigned tenant.'); return }
    const receivedAt = String(data.get('received_at'))
    const localDate = new Date(receivedAt)
    const input = { tenancy_id: tenancy.id, tenant_id: tenancy.tenant_id,
      amount: String(data.get('amount')), method: String(data.get('method')),
      received_at: localDate.toISOString(), reference_code: String(data.get('reference_code') || '') || null }
    setBusy('record')
    try { await paymentsApi.record(input, crypto.randomUUID()); await refresh(); form.reset(); setNotice('Payment recorded. A tenant receipt is now available.') }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not record this payment.') }
    finally { setBusy('') }
  }

  async function reverse(payment: OwnerPayment) {
    const reason = window.prompt(`Reverse ₹${payment.amount} received from ${payment.tenant}. Enter a reason:`)
    if (reason === null) return
    if (reason.trim().length < 3) { setError('Enter a reason with at least 3 characters.'); return }
    setError(''); setBusy(payment.id)
    try { await paymentsApi.reverse(payment.id, reason.trim()); await refresh() }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not reverse this payment.') }
    finally { setBusy('') }
  }

  return <div className="content ledger-page">
    <div className="page-heading"><div><div className="eyebrow">RENT &amp; PAYMENTS</div><h1>Payment ledger</h1><p>Recorded payments, tenant receipts, and audited reversals.</p></div></div>
    {error && <div className="form-alert" role="alert">{error}</div>}{notice && <div className="success-banner" role="status">{notice}</div>}
    <section className="panel record-payment-panel"><div className="panel-head"><div><h3>Record a payment</h3><p>Record money received outside Hearth and issue a tenant receipt.</p></div></div>
      <form className="record-payment-form" onSubmit={record}>
        <label htmlFor="payment-tenancy">Tenancy</label><select id="payment-tenancy" name="tenancy_id" required defaultValue=""><option value="" disabled>Select tenancy</option>{tenancies.filter(t => t.tenant_id && t.status === 'active').map(t => <option key={t.id} value={t.id} data-tenant-id={t.tenant_id}>{t.property} · Apt {t.unit} · {t.tenant}</option>)}</select>
        <label htmlFor="payment-amount">Amount (INR)</label><input id="payment-amount" name="amount" type="number" min="0.01" step="0.01" required />
        <label htmlFor="payment-method">Method</label><select id="payment-method" name="method"><option value="upi">UPI</option><option value="bank_transfer">Bank transfer</option><option value="cash">Cash</option><option value="other">Other</option></select>
        <label htmlFor="payment-date">Received at</label><input id="payment-date" name="received_at" type="datetime-local" required defaultValue={new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)} />
        <label htmlFor="payment-reference">Reference (optional)</label><input id="payment-reference" name="reference_code" maxLength={64} pattern="[A-Za-z0-9._-]+" />
        <button className="button primary" disabled={busy === 'record' || !tenancies.some(t => t.status === 'active' && t.tenant_id)}>{busy === 'record' ? 'Recording…' : 'Record payment'}</button>
      </form>
    </section>
    <LateFeesPanel tenancies={tenancies} />
    <div className="ledger-section-head"><div><h2>Recent payment history</h2><p>Latest 100 payments across your tenancies.</p></div></div>
    {loading ? <div className="panel loading-card">Loading payments…</div> : payments.length === 0 ? <div className="panel empty-state"><span>₹</span><h3>No payments recorded</h3><p>Payments recorded through the ledger will appear here.</p></div> : <section className="panel payment-table-panel"><div className="payment-table-head"><span>PAYMENT</span><span>TENANT &amp; TENANCY</span><span>STATUS</span><span>ACTIONS</span></div>
      {payments.map(payment => <article className="payment-row" key={payment.id}><div><b>₹{Number(payment.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</b><small>{payment.method.replace('_', ' ')}{payment.reference_code ? ` · Ref ${payment.reference_code}` : ''}</small><small>{receiptDate(payment.received_at)}</small></div><div><b>{payment.tenant}</b><small>{payment.property} · Apt {payment.unit}</small></div><span className={`payment-pill ${payment.status}`}>{payment.status}</span><div className="payment-actions"><a className="button secondary" href={`${API_URL}/api/payments/${payment.id}/receipt`} target="_blank" rel="noreferrer">Receipt</a>{payment.can_reverse && <button className="button secondary reverse-button" disabled={busy === payment.id} onClick={() => void reverse(payment)}>{busy === payment.id ? 'Reversing…' : 'Reverse'}</button>}</div></article>)}
    </section>}
    <p className="ledger-note">Reversals are full-amount corrections for unapplied payments. Payments with allocated credit cannot be reversed.</p>
  </div>
}
