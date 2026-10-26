import { useEffect, useState } from 'react'
import { ApiError, documentsApi, type TenancyDocument, type TenancySummary } from '../lib/api'

const displayDate = (value: string) => new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(value))

export default function AgreementsPage() {
  const [tenancies, setTenancies] = useState<TenancySummary[]>([])
  const [selected, setSelected] = useState('')
  const [documents, setDocuments] = useState<TenancyDocument[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    documentsApi.tenancies().then(rows => { setTenancies(rows); if (rows[0]) setSelected(rows[0].id) })
      .catch(() => setError('Could not load tenancies.')).finally(() => setLoading(false))
  }, [])
  useEffect(() => {
    if (!selected) { setDocuments([]); return }
    documentsApi.list(selected).then(setDocuments).catch(() => setError('Could not load tenancy documents.'))
  }, [selected])

  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setNotice('')
    const input = event.currentTarget.elements.namedItem('document') as HTMLInputElement
    const file = input.files?.[0]
    if (!file || !selected) return
    if (file.size > 10 * 1024 * 1024) { setError('PDF files must be 10 MB or smaller.'); return }
    if (file.type !== 'application/pdf' || !file.name.toLowerCase().endsWith('.pdf')) { setError('Choose a PDF document.'); return }
    setBusy(true)
    try { await documentsApi.upload(selected, file); setDocuments(await documentsApi.list(selected)); setNotice('Document uploaded securely.'); input.value = '' }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not upload this document.') }
    finally { setBusy(false) }
  }

  return <div className="content agreements-page">
    <div className="page-heading"><div><div className="eyebrow">PRIVATE FILES</div><h1>Agreements &amp; documents</h1><p>Store tenancy PDFs privately and share them with the tenants on that tenancy.</p></div></div>
    {error && <div className="form-alert" role="alert">{error}</div>}{notice && <div className="success-banner" role="status">{notice}</div>}
    <section className="panel agreement-panel"><div className="agreement-toolbar">
      <label htmlFor="agreement-tenancy">Tenancy</label><select id="agreement-tenancy" value={selected} onChange={e => setSelected(e.target.value)} disabled={!tenancies.length}><option value="">Select a tenancy</option>{tenancies.map(t => <option key={t.id} value={t.id}>{t.property} · Apt {t.unit} · {t.tenant} ({t.status})</option>)}</select>
      {selected && <form className="agreement-upload" onSubmit={upload}><input name="document" type="file" accept="application/pdf,.pdf" required aria-label="PDF agreement or document"/><button className="button primary" disabled={busy}>{busy ? 'Uploading…' : 'Upload PDF'}</button></form>}
    </div>
    {loading ? <div className="loading-card">Loading tenancies…</div> : !tenancies.length ? <div className="empty-state"><span>▤</span><h3>No tenancies yet</h3><p>Create a tenancy before adding its agreements.</p></div> : !documents.length ? <div className="empty-state"><span>▤</span><h3>No documents for this tenancy</h3><p>Upload a PDF to make it available to this tenant.</p></div> : <div className="document-list">{documents.map(item => <article className="document-row" key={item.id}><span className="document-icon">PDF</span><span className="document-copy"><b>{item.name}</b><small>{(item.byte_size / 1024).toFixed(0)} KB · added {displayDate(item.created_at)} · tenant can view</small></span><button className="button secondary" onClick={() => documentsApi.download(item.id, item.name).catch(() => setError('Could not download this document.'))}>Download</button></article>)}</div>}
    </section>
    <p className="document-note">PDF only · Maximum 10 MB · Files are stored outside the public web directory.</p>
  </div>
}
