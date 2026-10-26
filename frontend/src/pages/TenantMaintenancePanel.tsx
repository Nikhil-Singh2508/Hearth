import { useEffect, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ApiError, tenantApi, type MaintenanceRequest } from '../lib/api'

const requestSchema = z.object({
  tenancy_id: z.string().uuid('Choose a tenancy.'),
  subject: z.string().trim().min(3, 'Enter at least 3 characters.').max(160),
  description: z.string().trim().min(10, 'Add at least 10 characters of detail.').max(4000),
})
type RequestForm = z.infer<typeof requestSchema>

export default function TenantMaintenancePanel({ tenancies }: { tenancies: Array<{ id: string; property: string; unit: string; status: string }> }) {
  const active = tenancies.filter(item => item.status === 'active')
  const [items, setItems] = useState<MaintenanceRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const form = useForm<RequestForm>({ resolver: zodResolver(requestSchema), defaultValues: { tenancy_id: active[0]?.id } })
  async function refresh() {
    setError('')
    try { setItems(await tenantApi.maintenanceRequests()) }
    catch (cause) { setError(cause instanceof ApiError && cause.status === 401 ? 'Your session expired. Please sign in again.' : 'Could not load your maintenance requests.') }
    finally { setLoading(false) }
  }
  useEffect(() => { void refresh() }, [])
  const submit = form.handleSubmit(async values => {
    setError(''); setNotice('')
    try {
      await tenantApi.createMaintenanceRequest(values)
      form.reset({ tenancy_id: active[0]?.id, subject: '', description: '' })
      setNotice('Your maintenance request was submitted.')
      await refresh()
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 404 ? 'That active tenancy is unavailable. Refresh and try again.' : 'Could not submit your request. Please try again.')
    }
  })

  return <section className="panel tenant-maintenance">
    <div className="panel-head"><div><h3>Maintenance requests</h3><p>Report an issue to your property manager and follow its status.</p></div></div>
    {notice && <div className="success-banner" role="status">{notice}</div>}{error && <div className="form-alert" role="alert">{error}</div>}
    {active.length > 0 && <form className="maintenance-form" onSubmit={submit} noValidate>
      <label htmlFor="maintenance-tenancy">Apartment</label>
      <select id="maintenance-tenancy" {...form.register('tenancy_id')}>
        {active.map(item => <option key={item.id} value={item.id}>{item.property} · Apartment {item.unit}</option>)}
      </select>
      {form.formState.errors.tenancy_id && <span className="field-error">{form.formState.errors.tenancy_id.message}</span>}
      <label htmlFor="maintenance-subject">What needs attention?</label>
      <input id="maintenance-subject" maxLength={160} {...form.register('subject')} />
      {form.formState.errors.subject && <span className="field-error">{form.formState.errors.subject.message}</span>}
      <label htmlFor="maintenance-description">Details</label>
      <textarea id="maintenance-description" rows={4} maxLength={4000} {...form.register('description')} />
      {form.formState.errors.description && <span className="field-error">{form.formState.errors.description.message}</span>}
      <button className="button primary" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? 'Submitting…' : 'Submit request'}</button>
    </form>}
    {active.length === 0 && <p className="units-empty">A maintenance request can be submitted for an active tenancy.</p>}
    <div className="units-heading"><div><b>Your requests</b><span>{items.length}</span></div></div>
    {loading ? <div className="loading-card" role="status">Loading requests…</div> : items.length ? <div className="tenant-ledger">{items.map(item => <div className="tenant-ledger-row" key={item.id}><span><b>{item.subject}</b><small>{item.description}</small><small>Submitted {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(item.created_at))}</small></span><span className="request-status">{item.status.replace('_', ' ')}</span></div>)}</div> : <p className="units-empty">No maintenance requests yet.</p>}
  </section>
}
