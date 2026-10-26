import { useEffect, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ApiError, propertyApi, type Property, type Unit } from '../lib/api'

const propertySchema = z.object({ name: z.string().trim().min(1, 'Enter a property name.').max(160), address: z.string().trim().min(1, 'Enter an address.').max(2000), timezone: z.string().trim().min(1).max(64) })
const unitSchema = z.object({ unit_number: z.string().trim().min(1, 'Enter an apartment identifier.').max(80) })
type PropertyForm = z.infer<typeof propertySchema>
type UnitForm = z.infer<typeof unitSchema>

export default function PropertiesPage() {
  const [items, setItems] = useState<Property[]>([])
  const [units, setUnits] = useState<Record<string, Unit[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const propertyForm = useForm<PropertyForm>({ resolver: zodResolver(propertySchema), defaultValues: { timezone: 'Asia/Kolkata' } })

  async function refresh() {
    setLoading(true); setError('')
    try {
      const properties = await propertyApi.list()
      setItems(properties)
      const results = await Promise.all(properties.map(async (item) => [item.id, await propertyApi.units(item.id)] as const))
      setUnits(Object.fromEntries(results))
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 401 ? 'Your session expired. Sign out and sign in again.' : 'Could not load properties. Try again.')
    } finally { setLoading(false) }
  }
  useEffect(() => { void refresh() }, [])

  const create = propertyForm.handleSubmit(async (values) => {
    setError(''); setNotice('')
    try {
      await propertyApi.create(values)
      propertyForm.reset({ timezone: 'Asia/Kolkata' }); setShowCreate(false); setNotice('Property added.'); await refresh()
    } catch { setError('Could not save the property. Check the fields and try again.') }
  })

  async function archive(item: Property) {
    if (!window.confirm(`Archive “${item.name}”? It will be hidden from the active property list.`)) return
    try { await propertyApi.archive(item.id); setNotice('Property archived.'); await refresh() }
    catch { setError('Could not archive this property.') }
  }

  return <div className="content properties-page">
    <div className="page-heading"><div><div className="eyebrow">PORTFOLIO</div><h1>Properties</h1><p>Manage buildings and their apartments.</p></div><button className="button primary" onClick={() => setShowCreate(!showCreate)}>＋ <span>Add property</span></button></div>
    {notice&&<div className="success-banner" role="status">{notice}</div>}{error&&<div className="form-alert" role="alert">{error}</div>}
    {showCreate&&<section className="panel create-panel"><div className="panel-head"><div><h3>New property</h3><p>Enter the building details and local timezone.</p></div><button className="dots" onClick={()=>setShowCreate(false)} aria-label="Close form">×</button></div>
      <form className="property-form" onSubmit={create} noValidate>
        <FormField id="property-name" label="Property name" error={propertyForm.formState.errors.name?.message}><input id="property-name" {...propertyForm.register('name')} /></FormField>
        <FormField id="property-address" label="Address" error={propertyForm.formState.errors.address?.message}><input id="property-address" {...propertyForm.register('address')} /></FormField>
        <FormField id="property-timezone" label="IANA timezone" error={propertyForm.formState.errors.timezone?.message}><input id="property-timezone" {...propertyForm.register('timezone')} /></FormField>
        <div className="form-actions"><button type="button" className="button secondary" onClick={()=>setShowCreate(false)}>Cancel</button><button className="button primary" disabled={propertyForm.formState.isSubmitting}>{propertyForm.formState.isSubmitting?'Saving…':'Save property'}</button></div>
      </form></section>}
    {loading?<div className="panel loading-card" role="status">Loading properties…</div>:items.length===0?<div className="panel empty-state"><span>▦</span><h3>No properties yet</h3><p>Add a building to begin managing its apartments.</p><button className="button primary" onClick={()=>setShowCreate(true)}>＋ Add your first property</button></div>:
      <div className="managed-properties">{items.map(item=><PropertyPanel key={item.id} item={item} units={units[item.id]??[]} editing={editing===item.id} onEdit={()=>setEditing(editing===item.id?null:item.id)} onSaved={async()=>{setEditing(null);setNotice('Property updated.');await refresh()}} onArchive={()=>void archive(item)} onError={setError} />)}</div>}
  </div>
}

function PropertyPanel({item,units,editing,onEdit,onSaved,onArchive,onError}:{item:Property,units:Unit[],editing:boolean,onEdit:()=>void,onSaved:()=>void,onArchive:()=>void,onError:(message:string)=>void}) {
  const [showUnit, setShowUnit] = useState(false)
  const [unitError, setUnitError] = useState('')
  const form = useForm<PropertyForm>({resolver:zodResolver(propertySchema),defaultValues:{name:item.name,address:item.address,timezone:item.timezone}})
  const unitForm = useForm<UnitForm>({resolver:zodResolver(unitSchema)})
  const save = form.handleSubmit(async (values)=>{try{await propertyApi.update(item.id,values);onSaved()}catch{onError('Could not update property details.')}})
  const addUnit = unitForm.handleSubmit(async ({unit_number})=>{setUnitError('');try{await propertyApi.createUnit(item.id,unit_number);unitForm.reset();setShowUnit(false);onSaved()}catch{setUnitError('That apartment could not be added. Check that its identifier is unique.')}})
  return <article className="panel managed-property">
    <div className="managed-property-head"><div className="property-symbol">⌂</div><div className="managed-title"><h2>{item.name}</h2><p>{item.address}</p><small>Timezone: {item.timezone}</small></div><div className="property-actions"><button className="button secondary" onClick={onEdit}>{editing?'Cancel':'Edit'}</button><button className="button secondary archive-button" onClick={onArchive}>Archive</button></div></div>
    {editing&&<form className="property-form edit-property-form" onSubmit={save} noValidate><FormField id={`name-${item.id}`} label="Property name" error={form.formState.errors.name?.message}><input id={`name-${item.id}`} {...form.register('name')} /></FormField><FormField id={`address-${item.id}`} label="Address" error={form.formState.errors.address?.message}><input id={`address-${item.id}`} {...form.register('address')} /></FormField><FormField id={`timezone-${item.id}`} label="IANA timezone" error={form.formState.errors.timezone?.message}><input id={`timezone-${item.id}`} {...form.register('timezone')} /></FormField><button className="button primary" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting?'Saving…':'Save changes'}</button></form>}
    <div className="units-heading"><div><b>Apartments</b><span>{units.length} {units.length===1?'unit':'units'}</span></div><button className="text-link" onClick={()=>setShowUnit(!showUnit)}>{showUnit?'Cancel':'＋ Add apartment'}</button></div>
    {showUnit&&<form className="unit-form" onSubmit={addUnit} noValidate><label htmlFor={`unit-${item.id}`}>Apartment identifier</label><input id={`unit-${item.id}`} placeholder="e.g. A-101" {...unitForm.register('unit_number')}/><button className="button primary" disabled={unitForm.formState.isSubmitting}>{unitForm.formState.isSubmitting?'Adding…':'Add apartment'}</button>{unitForm.formState.errors.unit_number&&<span className="field-error">{unitForm.formState.errors.unit_number.message}</span>}{unitError&&<span className="field-error">{unitError}</span>}</form>}
    {units.length>0?<div className="unit-list">{units.map(unit=><span key={unit.id} className="unit-chip">⌂ {unit.unit_number}</span>)}</div>:<p className="units-empty">No apartments added yet.</p>}
  </article>
}

function FormField({id,label,error,children}:{id:string,label:string,error?:string,children:React.ReactNode}) {return <div className="form-field"><label htmlFor={id}>{label}</label>{children}{error&&<span className="field-error">{error}</span>}</div>}
