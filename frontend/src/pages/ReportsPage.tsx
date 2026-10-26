import { useState } from 'react'
import { ApiError, reportsApi } from '../lib/api'
import './reports.css'

const datasets = [
  { id: 'charges', title: 'Rent charges', description: 'Billing periods, due dates, tenant and apartment, and amounts charged.' },
  { id: 'payments', title: 'Payments', description: 'Recorded payments with method, reference and reversed status.' },
  { id: 'expenses', title: 'Property expenses', description: 'Owner costs by property, apartment, vendor and category.' },
  { id: 'utilities', title: 'Utility bills', description: 'Bill totals, allocated amounts, supplier and posting status.' },
  { id: 'deposits', title: 'Security deposits', description: 'Receipts, refunds and deductions with their reasons.' },
]

export default function ReportsPage() {
  const [period, setPeriod] = useState('this_month')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  async function download(dataset: string, title: string) {
    setBusy(dataset); setError(''); setNotice('')
    try { await reportsApi.download(dataset, period); setNotice(`${title} CSV downloaded.`) }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not download this report.') }
    finally { setBusy('') }
  }
  return <div className="content reports-page">
    <div className="page-heading"><div><div className="eyebrow">PORTFOLIO REPORTING</div><h1>Reports &amp; exports</h1><p>Download a period of owner-authorized financial records as CSV.</p></div></div>
    {error && <div className="form-alert" role="alert">{error}</div>}{notice && <div className="success-banner" role="status">{notice}</div>}
    <section className="panel reports-period"><label htmlFor="report-period">Export period</label><select id="report-period" value={period} onChange={event => setPeriod(event.target.value)}><option value="this_month">This month</option><option value="last_month">Last month</option><option value="this_quarter">This quarter</option></select><p>Exports are limited to 10,000 rows. If the limit is exceeded, choose a shorter period.</p></section>
    <div className="reports-grid">{datasets.map((dataset, index) => <article className="panel report-card" key={dataset.id}><span className="report-icon">{['₹', '↗', '▤', '⌁', '₹'][index]}</span><h2>{dataset.title}</h2><p>{dataset.description}</p><button className="button secondary" disabled={Boolean(busy)} onClick={() => void download(dataset.id, dataset.title)}>{busy === dataset.id ? 'Preparing…' : 'Download CSV'}</button></article>)}</div>
    <p className="report-note">Exports include names used to identify tenancies but exclude email addresses, authentication data, private documents and uploaded evidence.</p>
  </div>
}
