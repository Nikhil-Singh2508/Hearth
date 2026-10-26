import { inspectionsApi, type InspectionRecord } from '../lib/api'

export default function TenantInspections({ tenancyId, items }: { tenancyId: string; items: InspectionRecord[] }) {
  const records = items.filter(item => item.tenancy_id === tenancyId)
  return <section className="tenant-inspections"><div className="units-heading"><div><b>Inspections</b><span>{records.length} shared records</span></div></div>
    {!records.length ? <p className="units-empty">No inspections have been shared with you.</p> : records.map(record => <article className="tenant-inspection" key={record.id}><div className="tenant-inspection-head"><b>{record.inspection_type.replace('_', ' ')} · {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(`${record.inspected_on}T00:00:00`))}</b><span>{record.status}</span></div>{record.notes && <p>{record.notes}</p>}{record.items.map(item => <div className="tenant-inspection-item" key={item.id}><b>{item.area} · {item.item_name}</b><span>{item.condition.replaceAll('_', ' ')}</span>{item.notes && <small>{item.notes}</small>}{item.evidence.map(file => <Evidence key={file.id} file={file} />)}</div>)}{record.evidence.map(file => <Evidence key={file.id} file={file} />)}</article>)}
  </section>
}

function Evidence({ file }: { file: InspectionRecord['evidence'][number] }) {
  return <div className="tenant-inspection-file"><span>{file.content_type === 'application/pdf' ? 'PDF' : 'PHOTO'}</span><small>{file.name}</small><button className="button secondary" onClick={() => inspectionsApi.download(file.id, file.name).catch(() => {})}>Download</button></div>
}
