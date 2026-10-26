import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { ApiError, reportsApi, type DashboardReport } from '../lib/api'
import './dashboard.css'

const currency = (value: string) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value))
const shortMonth = (value: string) => new Intl.DateTimeFormat('en-IN', { month: 'short' }).format(new Date(`${value}T00:00:00`))

export default function DashboardPage({ period, setPeriod }: { period: string; setPeriod: (value: string) => void }) {
  const [report, setReport] = useState<DashboardReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    setLoading(true); setError('')
    reportsApi.dashboard(period).then(setReport).catch((cause: unknown) => {
      setError(cause instanceof ApiError && cause.status === 401 ? 'Your session expired. Sign in again to load portfolio data.' : 'Could not load portfolio reporting data.')
    }).finally(() => setLoading(false))
  }, [period, retry])
  if (loading && !report) return <div className="content"><div className="panel loading-card" role="status">Loading portfolio report…</div></div>
  if (error && !report) return <div className="content"><div className="form-alert" role="alert">{error}</div><button className="button secondary" onClick={() => setRetry(value => value + 1)}>Retry</button></div>
  if (!report) return null
  const { metrics } = report
  const maxChartValue = Math.max(1, ...report.collection.flatMap(row => [Number(row.rent_charged), Number(row.payments_received)]))
  const colors = ['peach', 'sage', 'lavender', 'peach', 'sage', 'lavender']
  return <div className="content dashboard-live">
    <div className="page-heading"><div><div className="eyebrow">PORTFOLIO SNAPSHOT <span className="weather">Live data</span></div><h1>Your portfolio</h1><p>Financial and occupancy activity from your recorded tenancies.</p></div><div className="heading-actions"><NavLink className="button secondary" to="/reports">▥ <span>Reports</span></NavLink><NavLink className="button primary" to="/properties">＋ <span>Add property</span></NavLink></div></div>
    {error && <div className="form-alert" role="alert">{error}</div>}
    <div className="summary-grid">
      <Metric label="ACTIVE UNITS" value={`${metrics.occupied_units} / ${metrics.total_units}`} note={`${metrics.total_units - metrics.occupied_units} currently vacant`} icon="▦" />
      <Metric label="OCCUPANCY" value={`${metrics.occupancy_percent}%`} note="Occupied active apartments" icon="⌂" />
      <Metric label="RENT CHARGED" value={currency(metrics.rent_charged)} note={report.period_label} icon="₹" />
      <Metric label="PAYMENTS RECEIVED" value={currency(metrics.payments_received)} note={report.period_label} icon="↗" />
      <Metric label="OVERDUE RENT" value={currency(metrics.overdue_amount)} note={`${metrics.overdue_count} overdue rent charges`} icon="◷" alert />
      <Metric label="DEPOSITS TO COLLECT" value={currency(metrics.deposits_due)} note="Agreed amount less receipts" icon="₹" />
    </div>
    <div className="section-head"><div><h2>Portfolio activity</h2><p>Live totals for {report.period_label.toLowerCase()} and the latest six billing months.</p></div><select value={period} onChange={event => setPeriod(event.target.value)} aria-label="Select reporting period"><option value="this_month">This month</option><option value="last_month">Last month</option><option value="this_quarter">This quarter</option></select></div>
    <div className="dashboard-grid"><section className="panel collection-panel"><div className="panel-head"><div><h3>Rent charged and paid</h3><p>Rent charge month compared with cash received month</p></div></div><div className="chart-legend"><span><i className="legend-indigo" /> Rent charged</span><span><i className="legend-gray" /> Payments received</span><span className="chart-total">{currency(metrics.rent_charged)} <small>charged</small></span></div>
      {!report.collection.some(row => Number(row.rent_charged) || Number(row.payments_received)) ? <div className="dashboard-chart-empty">Rent and payment activity will appear here when recorded.</div> : <div className="chart live-chart" role="img" aria-label="Rent charged and payments received over the latest six months"><div className="y-axis"><span>100%</span><span>75%</span><span>50%</span><span>25%</span><span>0%</span></div><div className="plot">{report.collection.map(row => <div className="bar-group live-bar-group" key={row.month} title={`${shortMonth(row.month)}: ${currency(row.rent_charged)} charged, ${currency(row.payments_received)} received`}><div className="bar" style={{ height: `${Math.max(1, Number(row.rent_charged) / maxChartValue * 100)}%` }} /><div className="bar pale" style={{ height: `${Math.max(1, Number(row.payments_received) / maxChartValue * 100)}%` }} /><span className="month-label">{shortMonth(row.month)}</span></div>)}</div></div>}
    </section><section className="panel activity-panel"><div className="panel-head"><div><h3>Needs your attention</h3><p>Open items from your records.</p></div></div>{report.attention.length ? report.attention.map(item => <NavLink className="attention attention-link" to={item.path} key={item.title}><span className={`attention-icon ${item.tone}`}>{item.tone === 'orange' ? '₹' : item.tone === 'blue' ? '⌁' : item.tone === 'green' ? '▤' : '⚒'}</span><span className="attention-copy"><b>{item.title}</b><small>{item.detail}</small></span><span className="attention-tag">{item.count}</span><span className="attention-arrow">›</span></NavLink>) : <div className="attention-empty">No open items need attention.</div>}</section></div>
    <div className="section-head property-heading"><div><h2>Your properties</h2><p>Current occupancy across active properties.</p></div><NavLink className="text-link" to="/properties">All properties <span>→</span></NavLink></div>
    {report.properties.length ? <div className="property-grid">{report.properties.map((property, index) => <PropertyCard key={property.id} name={property.name} area={property.address} occupancy={`${property.occupied_units} / ${property.unit_count} units occupied`} rate={`${property.occupancy_percent}%`} color={colors[index % colors.length]} />)}</div> : <div className="panel empty-state"><span>⌂</span><h3>No active properties</h3><p>Add a property and apartments to start tracking portfolio activity.</p></div>}
    <div className="dashboard-foot-metrics"><span>Expenses this period <b>{currency(metrics.expenses)}</b><small>{metrics.expense_count} recorded expenses</small></span><span>Utility bills pending <b>{metrics.pending_utility_count}</b><small>{currency(metrics.pending_utility_amount)} awaiting allocation</small></span><span>Move-outs in 30 days <b>{metrics.upcoming_move_outs}</b><small>Active tenancies with an end date</small></span></div>
    <footer>© 2026 Hearth <span>Figures reflect data currently recorded in Hearth.</span></footer>
  </div>
}

function Metric({ label, value, note, icon, alert = false }: { label: string; value: string; note: string; icon: string; alert?: boolean }) {
  return <div className={`metric ${alert ? 'alert' : ''}`}><div className="metric-top"><span>{label}</span><i className="metric-icon">{icon}</i></div><strong>{value}</strong><div className="metric-note">{note}</div></div>
}

function PropertyCard({ name, area, occupancy, rate, color }: { name: string; area: string; occupancy: string; rate: string; color: string }) {
  const numericRate = Number(rate.replace('%', ''))
  return <article className="property-card"><div className={`property-art ${color}`}><span>⌂</span><i>⌂</i><i>⌂</i><i>⌂</i></div><div className="property-info"><div><h3>{name}</h3><p>⌖ &nbsp;{area}</p></div></div><div className="property-stats"><span>{occupancy}</span><b>{rate}</b></div><div className="property-progress"><i style={{ width: `${Math.max(0, Math.min(100, numericRate))}%` }} /></div></article>
}
