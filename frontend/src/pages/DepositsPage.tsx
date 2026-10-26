import { useEffect, useState } from 'react'
import { ApiError, depositsApi, type DepositSummary, type DepositTransaction } from '../lib/api'

const dateTime = (value: string) => new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
const money = (value: string) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(value))

export default function DepositsPage() {
  const [items, setItems] = useState<DepositSummary[]>([])
  const [transactions, setTransactions] = useState<DepositTransaction[]>([])
  const [selected, setSelected] = useState('')
  const [kind, setKind] = useState('receipt')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const tenancy = items.find(item => item.id === selected)

  async function refresh() {
    const result = await depositsApi.list()
    setItems(result)
    return result
  }
  useEffect(() => { refresh().then(rows => { if (rows[0]) setSelected(rows[0].id) }).catch(() => setError('Could not load deposit accounts.')).finally(() => setLoading(false)) }, [])
  useEffect(() => { if (selected) depositsApi.transactions(selected).then(setTransactions).catch(() => setError('Could not load deposit transactions.')); else setTransactions([]) }, [selected])
  useEffect(() => { if (tenancy) setKind(tenancy.status === 'closed' ? 'refund' : 'receipt') }, [selected, items])

  async function saveExpected(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!tenancy) return
    const form = event.currentTarget
    const data = new FormData(form)
    setError(''); setNotice(''); setBusy(true)
    try { await depositsApi.updateExpected(tenancy.id, String(data.get('expected'))); await refresh(); setNotice('Agreed deposit amount updated.') }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not update the agreed deposit amount.') }
    finally { setBusy(false) }
  }

  async function postTransaction(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!tenancy) return
    const form = event.currentTarget
    const data = new FormData(form)
    const occurredAt = new Date(String(data.get('occurred_at')))
    const transaction = {
      transaction_type: kind, amount: String(data.get('amount')),
      method: kind === 'deduction' ? null : String(data.get('method')),
      reference_code: String(data.get('reference_code') || '') || null,
      reason: String(data.get('reason') || '') || null,
      occurred_at: occurredAt.toISOString(),
    }
    setError(''); setNotice(''); setBusy(true)
    try {
      await depositsApi.record(tenancy.id, transaction, crypto.randomUUID())
      await Promise.all([refresh(), depositsApi.transactions(tenancy.id).then(setTransactions)])
      form.reset()
      setNotice(`${kind === 'receipt' ? 'Deposit receipt' : kind === 'refund' ? 'Deposit refund' : 'Deposit deduction'} recorded.`)
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not record this deposit transaction.') }
    finally { setBusy(false) }
  }

  return <div className="content deposits-page">
    <div className="page-heading"><div><div className="eyebrow">MOVE-IN &amp; MOVE-OUT</div><h1>Security deposits</h1><p>Track agreed deposits, amounts received, and move-out refunds or deductions.</p></div></div>
    {error && <div className="form-alert" role="alert">{error}</div>}{notice && <div className="success-banner" role="status">{notice}</div>}
    {loading ? <div className="panel loading-card">Loading deposits…</div> : !items.length ? <div className="panel empty-state"><span>₹</span><h3>No tenancies available</h3><p>Create a tenancy to start its deposit record.</p></div> : <>
      <section className="panel deposit-picker"><label htmlFor="deposit-tenancy">Tenancy</label><select id="deposit-tenancy" value={selected} onChange={e => setSelected(e.target.value)}>{items.map(item => <option value={item.id} key={item.id}>{item.property} · Apt {item.unit} · {item.tenant} ({item.status})</option>)}</select></section>
      {tenancy && <>
        <div className="deposit-metrics">
          <div className="panel deposit-metric"><small>AGREED DEPOSIT</small><b>{money(tenancy.expected)}</b></div>
          <div className="panel deposit-metric"><small>RECEIVED</small><b>{money(tenancy.received)}</b></div>
          <div className="panel deposit-metric"><small>REFUNDED</small><b>{money(tenancy.refunded)}</b></div>
          <div className="panel deposit-metric"><small>DEDUCTIONS</small><b>{money(tenancy.deducted)}</b></div>
          <div className="panel deposit-metric deposit-balance"><small>REMAINING LIABILITY</small><b>{money(tenancy.balance)}</b></div>
          <div className="panel deposit-metric"><small>STILL TO COLLECT</small><b>{money(String(Math.max(0, Number(tenancy.expected) - Number(tenancy.received))))}</b></div>
        </div>
        <section className="panel deposit-edit"><div className="panel-head"><div><h3>Agreed deposit</h3><p>Current tenancy status: {tenancy.status}</p></div></div><form onSubmit={saveExpected}><label htmlFor="deposit-expected">Expected security deposit (INR)</label><input id="deposit-expected" name="expected" type="number" min={tenancy.received} step="0.01" defaultValue={tenancy.expected} key={`${tenancy.id}-${tenancy.expected}`} required/><button className="button secondary" disabled={busy}>Save amount</button></form></section>
        <section className="panel deposit-edit"><div className="panel-head"><div><h3>Record a deposit transaction</h3><p>Transactions are append-only; each amount is checked against the remaining deposit balance.</p></div></div>
          <form className="deposit-transaction-form" onSubmit={postTransaction}>
            <label htmlFor="deposit-type">Transaction</label><select id="deposit-type" value={kind} onChange={e => setKind(e.target.value)}><option value="receipt" disabled={tenancy.status !== 'active' || Number(tenancy.received) >= Number(tenancy.expected)}>Receive deposit</option><option value="refund" disabled={tenancy.status !== 'closed' || Number(tenancy.balance) <= 0}>Refund tenant</option><option value="deduction" disabled={tenancy.status !== 'closed' || Number(tenancy.balance) <= 0}>Record deduction</option></select>
            <label htmlFor="deposit-amount">Amount (INR)</label><input id="deposit-amount" name="amount" type="number" min="0.01" max={kind === 'receipt' ? Math.max(0, Number(tenancy.expected) - Number(tenancy.received)) : tenancy.balance} step="0.01" required/>
            {kind !== 'deduction' && <><label htmlFor="deposit-method">Method</label><select id="deposit-method" name="method"><option value="upi">UPI</option><option value="bank_transfer">Bank transfer</option><option value="cash">Cash</option><option value="other">Other</option></select></>}
            <label htmlFor="deposit-date">Date</label><input id="deposit-date" name="occurred_at" type="datetime-local" defaultValue={new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)} required/>
            <label htmlFor="deposit-reference">Reference (optional)</label><input id="deposit-reference" name="reference_code" maxLength={64} pattern="[A-Za-z0-9._-]+"/>
            {kind !== 'receipt' && <><label htmlFor="deposit-reason">Reason</label><input id="deposit-reason" name="reason" minLength={3} maxLength={500} required/></>}
            <button className="button primary" disabled={busy || (kind === 'receipt' ? tenancy.status !== 'active' || Number(tenancy.received) >= Number(tenancy.expected) : tenancy.status !== 'closed' || Number(tenancy.balance) <= 0)}>{busy ? 'Saving…' : 'Record transaction'}</button>
          </form>
        </section>
        <section className="panel deposit-history"><div className="panel-head"><div><h3>Transaction history</h3><p>Every receipt, refund, and deduction remains in the record.</p></div></div>
          {transactions.length ? transactions.map(item => <article className="deposit-row" key={item.id}><span className={`deposit-kind ${item.transaction_type}`}>{item.transaction_type}</span><b>{money(item.amount)}</b><span>{item.method?.replace('_', ' ') ?? 'Move-out deduction'}</span><span>{dateTime(item.occurred_at)}</span><small>{item.reason || item.reference_code || '—'}</small></article>) : <p className="quiet">No deposit transactions recorded.</p>}
        </section>
      </>}
    </>}
    <p className="deposit-note">Refunds and deductions are available only after a tenancy is closed. The system records the accounting entry; it does not transfer money to or from a bank.</p>
  </div>
}
