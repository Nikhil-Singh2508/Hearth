import { useEffect, useState } from 'react'
import { documentsApi, type TenancyDocument } from '../lib/api'

export default function TenantDocuments({ tenancyId }: { tenancyId: string }) {
  const [items, setItems] = useState<TenancyDocument[]>([])
  const [error, setError] = useState('')
  useEffect(() => { documentsApi.list(tenancyId).then(setItems).catch(() => setError('Documents could not be loaded.')) }, [tenancyId])
  if (error || items.length === 0) return null
  return <div className="tenant-documents"><div className="units-heading"><div><b>Agreements &amp; documents</b><span>{items.length} files</span></div></div>
    <div className="tenant-ledger">{items.map(item => <div className="tenant-ledger-row" key={item.id}><span><b>{item.name}</b><small>{(item.byte_size / 1024).toFixed(0)} KB · {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(item.created_at))}</small></span><button className="button secondary" onClick={() => documentsApi.download(item.id, item.name).catch(() => setError('Download failed.'))}>Download</button></div>)}</div>
  </div>
}
