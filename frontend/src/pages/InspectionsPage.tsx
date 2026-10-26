import { useEffect, useState } from 'react'
import { ApiError, documentsApi, inspectionsApi, type InspectionRecord, type TenancySummary } from '../lib/api'
import './inspections.css'

const conditions = ['good', 'fair', 'needs_attention', 'not_inspected']
const pretty = (value: string) => value.replaceAll('_', ' ')

export default function InspectionsPage() {
  const [tenancies, setTenancies] = useState<TenancySummary[]>([])
  const [inspections, setInspections] = useState<InspectionRecord[]>([])
  const [selectedTenancy, setSelectedTenancy] = useState('')
  const [selectedInspectionId, setSelectedInspectionId] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const selected = inspections.find(item => item.id === selectedInspectionId)

  async function refresh() { const result = await inspectionsApi.list(); setInspections(result); return result }
  useEffect(() => {
    Promise.all([documentsApi.tenancies(), inspectionsApi.list()]).then(([rows, records]) => {
      setTenancies(rows); setSelectedTenancy(rows[0]?.id ?? ''); setInspections(records)
      setSelectedInspectionId(records.find(item => item.status === 'in_progress')?.id ?? '')
    }).catch(() => setError('Could not load inspections and tenancies.')).finally(() => setLoading(false))
  }, [])

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form)
    setBusy(true); setError(''); setNotice('')
    try {
      const record = await inspectionsApi.create({ tenancy_id: selectedTenancy, inspection_type: String(data.get('inspection_type')),
        inspected_on: String(data.get('inspected_on')), notes: String(data.get('notes') || '') || null,
        tenant_visible: data.get('tenant_visible') === 'on' })
      await refresh(); setSelectedInspectionId(record.id); form.reset(); setNotice('Inspection started. Add checklist items and evidence before completing it.')
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not create this inspection.') }
    finally { setBusy(false) }
  }

  async function addItem(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected) return
    const form = event.currentTarget; const data = new FormData(form)
    setBusy(true); setError(''); setNotice('')
    try { await inspectionsApi.addItem(selected.id, { area: String(data.get('area')), item_name: String(data.get('item_name')),
      condition: String(data.get('condition')), notes: String(data.get('notes') || '') || null }); await refresh(); form.reset(); setNotice('Checklist item added.') }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not add the checklist item.') }
    finally { setBusy(false) }
  }

  async function uploadEvidence(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected) return
    const form = event.currentTarget; const data = new FormData(form); const file = data.get('evidence')
    if (!(file instanceof File) || file.size === 0) return
    setBusy(true); setError(''); setNotice('')
    try { await inspectionsApi.upload(selected.id, file, String(data.get('item_id') || '') || null); await refresh(); form.reset(); setNotice('Evidence uploaded to private storage.') }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not upload evidence.') }
    finally { setBusy(false) }
  }

  async function complete() {
    if (!selected) return
    setBusy(true); setError(''); setNotice('')
    try { await inspectionsApi.complete(selected.id); await refresh(); setNotice('Inspection completed. Its checklist and evidence are now locked.') }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not complete this inspection.') }
    finally { setBusy(false) }
  }

  return <div className="content inspections-page">
    <div className="page-heading"><div><div className="eyebrow">MOVE-IN &amp; MOVE-OUT</div><h1>Inspections</h1><p>Document property condition with a checklist and private supporting evidence.</p></div></div>
    {error && <div className="form-alert" role="alert">{error}</div>}{notice && <div className="success-banner" role="status">{notice}</div>}
    {loading ? <div className="panel loading-card" role="status">Loading inspections…</div> : !tenancies.length ? <div className="panel empty-state"><span>☷</span><h3>No tenancies available</h3><p>Create a tenancy before starting an inspection.</p></div> : <>
      <section className="panel inspection-create"><div className="panel-head"><div><h3>Start an inspection</h3><p>Create a move-in or move-out record for a tenancy.</p></div></div><form onSubmit={event => void create(event)}>
        <label htmlFor="inspection-tenancy">Tenancy</label><select id="inspection-tenancy" value={selectedTenancy} onChange={event => setSelectedTenancy(event.target.value)} required>{tenancies.map(item => <option key={item.id} value={item.id}>{item.property} · Apt {item.unit} · {item.tenant}</option>)}</select>
        <label htmlFor="inspection-type">Type</label><select id="inspection-type" name="inspection_type"><option value="move_in">Move-in</option><option value="move_out">Move-out</option></select>
        <label htmlFor="inspection-date">Inspection date</label><input id="inspection-date" name="inspected_on" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required />
        <label htmlFor="inspection-notes">Overview notes</label><textarea id="inspection-notes" name="notes" maxLength={2000} />
        <label htmlFor="inspection-visible">Tenant access</label><span className="inspection-visible"><input id="inspection-visible" name="tenant_visible" type="checkbox" defaultChecked /> Share this inspection with the associated tenant</span>
        <button className="button primary" disabled={busy}>Start inspection</button>
      </form></section>
      <section className="panel inspection-work"><div className="panel-head"><div><h3>Inspection record</h3><p>Items and evidence are locked after completion.</p></div></div>
        {!inspections.length ? <p className="inspection-empty">No inspections have been started.</p> : <>
          <div className="inspection-picker"><label htmlFor="inspection-picker">Select record</label><select id="inspection-picker" value={selectedInspectionId} onChange={event => setSelectedInspectionId(event.target.value)}>{inspections.map(item => { const tenancy = tenancies.find(row => row.id === item.tenancy_id); return <option key={item.id} value={item.id}>{item.inspection_type.replace('_', ' ')} · {tenancy ? `${tenancy.property} Apt ${tenancy.unit} · ${tenancy.tenant}` : 'Tenancy'} · {item.inspected_on} ({item.status})</option> })}</select></div>
          {selected && <><div className="inspection-overview"><div><span className="eyebrow">{pretty(selected.inspection_type)} · {selected.inspected_on}</span><p>{selected.notes || 'No overview notes.'}</p></div><span className={`utility-status ${selected.status === 'completed' ? 'posted' : ''}`}>{selected.status}</span><span className="inspection-visibility">{selected.tenant_visible ? 'Visible to tenant' : 'Owner only'}</span></div>
            {selected.items.map(item => <article className="inspection-item" key={item.id}><div className="inspection-item-title"><span><b>{item.area} · {item.item_name}</b><small>{item.notes || 'No notes'}</small></span><span className={`inspection-condition ${item.condition}`}>{pretty(item.condition)}</span></div>{item.evidence.map(file => <Evidence key={file.id} file={file} />)}</article>)}
            {selected.evidence.map(file => <Evidence key={file.id} file={file} />)}
            {selected.status === 'in_progress' && <div className="inspection-edit-grid"><form onSubmit={event => void addItem(event)}><h4>Add checklist item</h4><label htmlFor="inspection-area">Area</label><input id="inspection-area" name="area" maxLength={120} placeholder="Kitchen" required /><label htmlFor="inspection-item">Item</label><input id="inspection-item" name="item_name" maxLength={160} placeholder="Sink and tap" required /><label htmlFor="inspection-condition">Condition</label><select id="inspection-condition" name="condition">{conditions.map(condition => <option key={condition} value={condition}>{pretty(condition)}</option>)}</select><label htmlFor="inspection-item-notes">Notes</label><textarea id="inspection-item-notes" name="notes" maxLength={1000} /><button className="button secondary" disabled={busy}>Add item</button></form>
              <form onSubmit={event => void uploadEvidence(event)}><h4>Attach private evidence</h4><label htmlFor="evidence-item">Checklist item (optional)</label><select id="evidence-item" name="item_id"><option value="">Inspection overview</option>{selected.items.map(item => <option key={item.id} value={item.id}>{item.area} · {item.item_name}</option>)}</select><label htmlFor="evidence-file">Photo or PDF (max 10 MB)</label><input id="evidence-file" name="evidence" type="file" accept="image/jpeg,image/png,application/pdf,.jpg,.jpeg,.png,.pdf" required /><button className="button secondary" disabled={busy}>Upload evidence</button></form></div>}
            {selected.status === 'in_progress' && <div className="inspection-complete"><p>Every checklist item needs a recorded condition before completion.</p><button className="button primary" disabled={busy || !selected.items.length || selected.items.some(item => item.condition === 'not_inspected')} onClick={() => void complete()}>Complete inspection</button></div>}
          </>}
        </>}
      </section>
    </>}
  </div>
}

function Evidence({ file }: { file: InspectionRecord['evidence'][number] }) {
  return <div className="inspection-evidence"><span className="document-icon">{file.content_type === 'application/pdf' ? 'PDF' : 'IMG'}</span><span><b>{file.name}</b><small>{Math.ceil(file.byte_size / 1024)} KB</small></span><button className="button secondary" onClick={() => inspectionsApi.download(file.id, file.name).catch(() => {})}>Download</button></div>
}
