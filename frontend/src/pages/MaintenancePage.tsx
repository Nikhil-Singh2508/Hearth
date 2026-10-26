import { useEffect, useState } from 'react'
import { ApiError, maintenanceApi, type MaintenanceRequest } from '../lib/api'

const states = ['open', 'in_progress', 'resolved', 'closed'] as const

export default function MaintenancePage() {
  const [items, setItems] = useState<MaintenanceRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  async function refresh() {
    setError('')
    try { setItems(await maintenanceApi.list()) }
    catch (cause) { setError(cause instanceof ApiError && cause.status === 401 ? 'Your session expired. Sign out and sign in again.' : 'Could not load maintenance requests.') }
    finally { setLoading(false) }
  }
  useEffect(() => { void refresh() }, [])
  async function update(item: MaintenanceRequest, status: string) {
    setError(''); setNotice('')
    try {
      await maintenanceApi.updateStatus(item.id, status)
      setNotice(`Request status updated to ${status.replace('_', ' ')}.`)
      await refresh()
    } catch { setError('Could not update this request. Please try again.') }
  }
  return <div className="content">
    <div className="page-heading"><div><div className="eyebrow">OPERATIONS</div><h1>Maintenance</h1><p>Review tenant requests and track their progress.</p></div></div>
    {notice && <div className="success-banner" role="status">{notice}</div>}{error && <div className="form-alert" role="alert">{error}</div>}
    {loading ? <div className="panel loading-card" role="status">Loading requests…</div> : items.length === 0 ? <div className="panel empty-state"><span>⚒</span><h3>No maintenance requests</h3><p>Tenant requests will appear here when submitted.</p></div> : <div className="maintenance-list">{items.map(item => <article className="panel maintenance-card" key={item.id}>
      <div className="maintenance-card-heading"><div><div className="eyebrow">{item.property} · Apartment {item.unit}</div><h2>{item.subject}</h2><p>{item.tenant} · submitted {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(item.created_at))}</p></div>
        <label className="status-control">Status<select value={item.status} onChange={event => void update(item, event.target.value)} aria-label={`Status for ${item.subject}`}>{states.map(state => <option key={state} value={state}>{state.replace('_', ' ')}</option>)}</select></label>
      </div><p className="maintenance-description">{item.description}</p>
    </article>)}</div>}
  </div>
}
