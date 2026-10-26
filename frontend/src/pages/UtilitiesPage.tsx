import { useEffect, useMemo, useState } from 'react'
import { ApiError, documentsApi, propertyApi, utilitiesApi, type Property, type PropertyExpense, type TenancySummary, type Unit, type UtilityBill, type UtilityMeter, type UtilityMeterReading } from '../lib/api'
import './utilities.css'

const today = () => new Date().toISOString().slice(0, 10)
const money = (amount: string) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(amount))
const types = ['electricity', 'water', 'gas', 'internet', 'other']
const categories = ['repairs', 'tax', 'insurance', 'supplies', 'management', 'other']

export default function UtilitiesPage() {
  const [properties, setProperties] = useState<Property[]>([])
  const [tenancies, setTenancies] = useState<TenancySummary[]>([])
  const [bills, setBills] = useState<UtilityBill[]>([])
  const [meters, setMeters] = useState<UtilityMeter[]>([])
  const [selectedMeterId, setSelectedMeterId] = useState('')
  const [meterReadings, setMeterReadings] = useState<UtilityMeterReading[]>([])
  const [expenses, setExpenses] = useState<PropertyExpense[]>([])
  const [units, setUnits] = useState<Unit[]>([])
  const [propertyId, setPropertyId] = useState('')
  const [billUnitId, setBillUnitId] = useState('')
  const [expensePropertyId, setExpensePropertyId] = useState('')
  const [expenseUnitId, setExpenseUnitId] = useState('')
  const [selectedBillId, setSelectedBillId] = useState('')
  const [allocations, setAllocations] = useState([{ tenancy_id: '', amount: '' }])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const selectedBill = bills.find(bill => bill.id === selectedBillId)
  const billTenancies = useMemo(() => tenancies.filter(item => selectedBill && item.property_id === selectedBill.property_id && (!selectedBill.unit_id || item.unit_id === selectedBill.unit_id)), [tenancies, selectedBill])

  async function refresh() {
    const [nextBills, nextExpenses, nextMeters] = await Promise.all([utilitiesApi.bills(), utilitiesApi.expenses(), utilitiesApi.meters()])
    setBills(nextBills); setExpenses(nextExpenses); setMeters(nextMeters)
    if (!selectedBillId || !nextBills.some(bill => bill.id === selectedBillId)) setSelectedBillId(nextBills.find(bill => bill.status === 'pending')?.id ?? '')
  }
  useEffect(() => {
    Promise.all([propertyApi.list(), documentsApi.tenancies(), utilitiesApi.bills(), utilitiesApi.expenses(), utilitiesApi.meters()])
      .then(([p, t, b, e, m]) => { setProperties(p); setTenancies(t); setBills(b); setExpenses(e); setMeters(m); setSelectedMeterId(m[0]?.id ?? ''); setPropertyId(p[0]?.id ?? ''); setExpensePropertyId(p[0]?.id ?? ''); setSelectedBillId(b.find(row => row.status === 'pending')?.id ?? '') })
      .catch(() => setError('Could not load properties, bills, or expenses.'))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => { if (!propertyId) { setUnits([]); return }; propertyApi.units(propertyId).then(setUnits).catch(() => setError('Could not load apartments.')) }, [propertyId])
  useEffect(() => { if (!expensePropertyId) return; propertyApi.units(expensePropertyId).then(setExpenseUnits).catch(() => setError('Could not load apartments.')) }, [expensePropertyId])
  const [expenseUnits, setExpenseUnits] = useState<Unit[]>([])
  const selectedMeter = meters.find(meter => meter.id === selectedMeterId)
  useEffect(() => { if (!selectedMeterId) { setMeterReadings([]); return }; utilitiesApi.readings(selectedMeterId).then(setMeterReadings).catch(() => setError('Could not load meter readings.')) }, [selectedMeterId])

  async function submit(event: React.FormEvent<HTMLFormElement>, kind: 'bill' | 'expense') {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form)
    setBusy(true); setError(''); setNotice('')
    try {
      if (kind === 'bill') {
        const created = await utilitiesApi.createBill({ property_id: propertyId, unit_id: billUnitId || null,
          utility_type: String(data.get('utility_type')), period_start: data.get('period_start'), period_end: data.get('period_end'),
          due_date: data.get('due_date'), supplier: data.get('supplier'), bill_reference: data.get('bill_reference') || null,
          amount: data.get('amount'), notes: data.get('notes') || null })
        await refresh(); setSelectedBillId(created.id); form.reset(); setNotice('Utility bill saved as pending allocation.')
      } else {
        await utilitiesApi.createExpense({ property_id: expensePropertyId, unit_id: expenseUnitId || null,
          category: data.get('category'), amount: data.get('expense_amount'), spent_on: data.get('spent_on'),
          vendor: data.get('vendor'), reference_code: data.get('reference_code') || null, description: data.get('description') })
        await refresh(); form.reset(); setNotice('Property expense recorded.')
      }
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not save this record.') }
    finally { setBusy(false) }
  }

  async function allocate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selectedBill) return
    setBusy(true); setError(''); setNotice('')
    try { await utilitiesApi.allocate(selectedBill.id, allocations); await refresh(); setNotice('Bill reconciled and utility charges posted to the selected tenancies.') }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not allocate this bill.') }
    finally { setBusy(false) }
  }

  async function saveMeter(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError(''); setNotice('')
    try {
      const meter = await utilitiesApi.createMeter({ property_id: propertyId, unit_id: billUnitId || null,
        utility_type: String(data.get('meter_type')), meter_name: data.get('meter_name'),
        serial_number: data.get('meter_serial') || null, unit_of_measure: data.get('unit_of_measure') })
      const next = await utilitiesApi.meters(); setMeters(next); setSelectedMeterId(meter.id); event.currentTarget.reset(); setNotice('Meter created. Record an initial reading before the first billing reading.')
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not create this meter.') }
    finally { setBusy(false) }
  }

  async function saveRate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError(''); setNotice('')
    try {
      await utilitiesApi.createRate({ property_id: propertyId, unit_id: billUnitId || null,
        utility_type: String(data.get('rate_type')), rate_per_unit: data.get('rate_per_unit'),
        fixed_charge: data.get('fixed_charge') || '0', effective_from: data.get('rate_effective_from') })
      event.currentTarget.reset(); setNotice('Utility rate saved. It applies to readings dated on or after its effective date.')
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not save this utility rate.') }
    finally { setBusy(false) }
  }

  async function saveReading(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selectedMeterId) return
    const data = new FormData(event.currentTarget); setBusy(true); setError(''); setNotice('')
    try {
      const result = await utilitiesApi.recordReading(selectedMeterId, { read_on: String(data.get('read_on')),
        reading: String(data.get('reading')), due_date: String(data.get('reading_due_date')) })
      await refresh(); setMeterReadings(await utilitiesApi.readings(selectedMeterId)); event.currentTarget.reset()
      setNotice(result.utility_bill ? `Reading saved; a pending utility bill for ${money(result.utility_bill.amount)} was created for reconciliation.` : 'Initial meter reading saved as the baseline.')
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not record this meter reading.') }
    finally { setBusy(false) }
  }

  return <div className="content utilities-page">
    <div className="page-heading"><div><div className="eyebrow">PROPERTY FINANCES</div><h1>Utilities &amp; expenses</h1><p>Record utility bills, reconcile tenant allocations, and track property costs.</p></div></div>
    {error && <div className="form-alert" role="alert">{error}</div>}{notice && <div className="success-banner" role="status">{notice}</div>}
    {loading ? <div className="panel loading-card" role="status">Loading bills and expenses…</div> : !properties.length ? <div className="panel empty-state"><span>⌁</span><h3>Add a property first</h3><p>Utility bills and expenses are recorded against a property.</p></div> : <>
      <div className="utilities-grid">
        <section className="panel utility-form"><div className="panel-head"><div><h3>Record a utility bill</h3><p>New bills stay pending until their full amount is allocated.</p></div></div>
          <form onSubmit={event => void submit(event, 'bill')}>
            <label htmlFor="utility-property">Property</label><select id="utility-property" value={propertyId} onChange={event => { setPropertyId(event.target.value); setBillUnitId('') }} required>{properties.map(property => <option key={property.id} value={property.id}>{property.name}</option>)}</select>
            <label htmlFor="utility-unit">Apartment (optional)</label><select id="utility-unit" value={billUnitId} onChange={event => setBillUnitId(event.target.value)}><option value="">Shared / property-wide</option>{units.map(unit => <option key={unit.id} value={unit.id}>{unit.unit_number}</option>)}</select>
            <label htmlFor="utility-type">Utility</label><select id="utility-type" name="utility_type">{types.map(type => <option key={type}>{type}</option>)}</select>
            <label htmlFor="utility-supplier">Supplier</label><input id="utility-supplier" name="supplier" maxLength={160} required />
            <label htmlFor="utility-reference">Bill reference (optional)</label><input id="utility-reference" name="bill_reference" maxLength={80} />
            <label htmlFor="utility-start">Period starts</label><input id="utility-start" name="period_start" type="date" required />
            <label htmlFor="utility-end">Period ends (exclusive)</label><input id="utility-end" name="period_end" type="date" required />
            <label htmlFor="utility-due">Due date</label><input id="utility-due" name="due_date" type="date" defaultValue={today()} required />
            <label htmlFor="utility-amount">Total (INR)</label><input id="utility-amount" name="amount" type="number" min="0.01" step="0.01" required />
            <label htmlFor="utility-notes">Notes (optional)</label><textarea id="utility-notes" name="notes" maxLength={1000} />
            <button className="button primary" disabled={busy}>Save pending bill</button>
          </form>
        </section>
        <section className="panel utility-form"><div className="panel-head"><div><h3>Record a property expense</h3><p>Repairs and other owner costs are kept separate from tenant charges.</p></div></div>
          <form onSubmit={event => void submit(event, 'expense')}>
            <label htmlFor="expense-property">Property</label><select id="expense-property" value={expensePropertyId} onChange={event => { setExpensePropertyId(event.target.value); setExpenseUnitId('') }} required>{properties.map(property => <option key={property.id} value={property.id}>{property.name}</option>)}</select>
            <label htmlFor="expense-unit">Apartment (optional)</label><select id="expense-unit" value={expenseUnitId} onChange={event => setExpenseUnitId(event.target.value)}><option value="">Property-wide</option>{expenseUnits.map(unit => <option key={unit.id} value={unit.id}>{unit.unit_number}</option>)}</select>
            <label htmlFor="expense-category">Category</label><select id="expense-category" name="category">{categories.map(category => <option key={category}>{category}</option>)}</select>
            <label htmlFor="expense-date">Date paid</label><input id="expense-date" name="spent_on" type="date" defaultValue={today()} required />
            <label htmlFor="expense-vendor">Vendor</label><input id="expense-vendor" name="vendor" maxLength={160} required />
            <label htmlFor="expense-amount">Amount (INR)</label><input id="expense-amount" name="expense_amount" type="number" min="0.01" step="0.01" required />
            <label htmlFor="expense-reference">Reference (optional)</label><input id="expense-reference" name="reference_code" maxLength={80} />
            <label htmlFor="expense-description">Description</label><textarea id="expense-description" name="description" maxLength={1000} required />
            <button className="button primary" disabled={busy}>Save expense</button>
          </form>
        </section>
      </div>
      <section className="panel meter-management"><div className="panel-head"><div><h3>Meters, rates &amp; readings</h3><p>Enter an opening reading, then subsequent readings calculate consumption and create a pending bill for allocation.</p></div></div>
        <div className="meter-forms">
          <form onSubmit={event => void saveMeter(event)}><h4>Add a meter</h4>
            <label>Utility<select name="meter_type">{types.filter(type => ['electricity', 'water', 'gas'].includes(type)).map(type => <option key={type}>{type}</option>)}</select></label>
            <label>Meter name<input name="meter_name" maxLength={120} required /></label><label>Serial number (optional)<input name="meter_serial" maxLength={80} /></label>
            <label>Reading unit<input name="unit_of_measure" placeholder="kWh or m³" maxLength={24} required /></label>
            <button className="button secondary" disabled={busy || !propertyId}>Add meter for selected property/apartment</button>
          </form>
          <form onSubmit={event => void saveRate(event)}><h4>Set a utility rate</h4>
            <label>Utility<select name="rate_type">{types.filter(type => ['electricity', 'water', 'gas'].includes(type)).map(type => <option key={type}>{type}</option>)}</select></label>
            <label>Rate per unit (INR)<input name="rate_per_unit" type="number" min="0" step="0.0001" required /></label>
            <label>Fixed charge (INR)<input name="fixed_charge" type="number" min="0" step="0.01" defaultValue="0" /></label>
            <label>Effective from<input name="rate_effective_from" type="date" defaultValue={today()} required /></label>
            <button className="button secondary" disabled={busy || !propertyId}>Save rate for selected property/apartment</button>
          </form>
        </div>
        <form className="meter-reading-form" onSubmit={event => void saveReading(event)}><h4>Record a reading</h4>
          <label>Meter<select value={selectedMeterId} onChange={event => setSelectedMeterId(event.target.value)} required><option value="">Select meter</option>{meters.map(meter => <option key={meter.id} value={meter.id}>{meter.property}{meter.unit ? ` · Apt ${meter.unit}` : ' · Property-wide'} · {meter.utility_type} · {meter.meter_name}</option>)}</select></label>
          <label>Read on<input name="read_on" type="date" defaultValue={today()} required /></label>
          <label>Meter value{selectedMeter?.latest_reading && <small> Previous: {selectedMeter.latest_reading} on {selectedMeter.latest_read_on}</small>}<input name="reading" type="number" min="0" step="0.001" required /></label>
          <label>Bill due date<input name="reading_due_date" type="date" defaultValue={today()} required /></label>
          <button className="button primary" disabled={busy || !selectedMeterId}>Record reading</button>
        </form>
        {selectedMeterId && <div className="meter-history"><h4>Reading history</h4>{meterReadings.length === 0 ? <p>No readings recorded.</p> : meterReadings.map(reading => <div key={reading.id}><span>{reading.read_on}</span><b>{reading.reading} {selectedMeter?.unit_of_measure}</b><small>{reading.consumption} consumed{reading.calculated_amount ? ` · bill ${money(reading.calculated_amount)}` : ' · baseline'}</small></div>)}</div>}
      </section>
      <section className="panel utility-bills"><div className="panel-head"><div><h3>Utility bills</h3><p>Posted bills create rent-ledger utility charges for their allocations.</p></div></div>
        {!bills.length ? <p className="utility-empty">No utility bills recorded yet.</p> : <div className="utility-list">{bills.map(bill => <article className="utility-row" key={bill.id}><div><b>{bill.utility_type} · {bill.property}{bill.unit ? ` · Apt ${bill.unit}` : ''}</b><small>{bill.supplier}{bill.bill_reference ? ` · ${bill.bill_reference}` : ''} · {bill.period_start} to {bill.period_end}</small></div><strong>{money(bill.amount)}</strong><span className={`utility-status ${bill.status}`}>{bill.status}</span><button className="button secondary" disabled={bill.status !== 'pending'} onClick={() => { setSelectedBillId(bill.id); setAllocations([{ tenancy_id: '', amount: bill.amount }]) }}>{bill.status === 'pending' ? 'Allocate' : `${bill.allocations.length} allocations`}</button></article>)}</div>}
      </section>
      {selectedBill?.status === 'pending' && <section className="panel utility-allocation"><div className="panel-head"><div><h3>Allocate {selectedBill.utility_type} bill · {money(selectedBill.amount)}</h3><p>Every allocation must match a tenancy at the bill property and billing period; the total must reconcile exactly.</p></div></div>
        <form onSubmit={event => void allocate(event)}>{allocations.map((row, index) => <div className="utility-allocation-row" key={index}><label htmlFor={`allocation-tenancy-${index}`}>Tenancy</label><select id={`allocation-tenancy-${index}`} required value={row.tenancy_id} onChange={event => setAllocations(rows => rows.map((item, i) => i === index ? { ...item, tenancy_id: event.target.value } : item))}><option value="">Choose tenancy</option>{billTenancies.map(tenancy => <option key={tenancy.id} value={tenancy.id}>Apt {tenancy.unit} · {tenancy.tenant} ({tenancy.status})</option>)}</select><label htmlFor={`allocation-amount-${index}`}>Amount (INR)</label><input id={`allocation-amount-${index}`} type="number" min="0.01" step="0.01" required value={row.amount} onChange={event => setAllocations(rows => rows.map((item, i) => i === index ? { ...item, amount: event.target.value } : item))} />{allocations.length > 1 && <button type="button" className="button secondary" onClick={() => setAllocations(rows => rows.filter((_, i) => i !== index))}>Remove</button>}</div>)}<div className="utility-allocation-actions"><button type="button" className="button secondary" onClick={() => setAllocations(rows => [...rows, { tenancy_id: '', amount: '' }])}>Add tenancy share</button><button className="button primary" disabled={busy || billTenancies.length === 0}>Reconcile and post</button></div></form>
      </section>}
      <section className="panel utility-bills"><div className="panel-head"><div><h3>Property expenses</h3><p>Recorded owner costs by property or apartment.</p></div></div>{!expenses.length ? <p className="utility-empty">No expenses recorded yet.</p> : <div className="utility-list">{expenses.map(expense => <article className="utility-row" key={expense.id}><div><b>{expense.category} · {expense.property}{expense.unit ? ` · Apt ${expense.unit}` : ''}</b><small>{expense.vendor} · {expense.spent_on} · {expense.description}</small></div><strong>{money(expense.amount)}</strong></article>)}</div>}</section>
      <p className="deposit-note">Meter readings calculate pending bills, but tenant charges are posted only after the bill is fully reconciled across eligible tenancies.</p>
    </>}
  </div>
}
