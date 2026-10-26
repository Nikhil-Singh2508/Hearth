export const API_URL = import.meta.env.VITE_API_URL ?? (import.meta.env.PROD ? '' : 'http://localhost:8000')

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

function cookie(name: string): string {
  const entry = document.cookie.split('; ').find((value) => value.startsWith(`${name}=`))
  return entry ? decodeURIComponent(entry.slice(name.length + 1)) : ''
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = cookie('rental_csrf')
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }
  const response = await fetch(`${API_URL}${path}`, { ...options, method, headers, credentials: 'include' })
  if (!response.ok) {
    let message = 'The request could not be completed.'
    try { message = (await response.json()).detail ?? message } catch { /* Keep the safe default. */ }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export type AuthUser = { email: string; role: 'owner' | 'tenant' }
export type Property = { id: string; name: string; address: string; timezone: string }
export type Unit = { id: string; unit_number: string }
export type Tenant = { id: string; email: string; display_name: string }
export type Invitation = { id: string; email: string; expires_at: string }
export type TenancySummary = { id: string; tenant_id: string | null; property_id: string; unit_id: string; property: string; unit: string; tenant: string; status: string; start_date: string }
export type TenancyDocument = { id: string; tenancy_id: string; name: string; content_type: string; byte_size: number; created_at: string }
export type DepositTransaction = { id: string; tenancy_id: string; transaction_type: string; amount: string; method: string | null; reference_code: string | null; reason: string | null; occurred_at: string }
export type DepositSummary = { id: string; property: string; unit: string; tenant: string; status: string; expected: string; received: string; refunded: string; deducted: string; balance: string }
export type TenantPortalData = {
  display_name: string
  tenancies: Array<{
    id: string; status: string; start_date: string; end_date: string | null
    unit: string; property: string; rent: string | null; rent_currency: string
    charges: Array<{ id: string; type: string; period_start: string; period_end: string; due_date: string; amount: string; paid: string; balance: string; currency: string }>
    payments: Array<{ id: string; amount: string; currency: string; method: string; received_at: string; status: string }>
    credits: Array<{ id: string; amount: string; currency: string; created_at: string }>
    security_deposit: { expected: string; received: string; refunded: string; deducted: string; balance: string; transactions: DepositTransaction[] }
  }>
}
export type TenantNotificationPreferences = {
  email_enabled: boolean; email_consent_at: string | null; whatsapp_enabled: boolean; whatsapp_phone: string | null
  whatsapp_consent_at: string | null; consent_version: string; email_provider_enabled: boolean; whatsapp_provider_enabled: boolean
}
export type MaintenanceRequest = {
  id: string; tenancy_id?: string; subject: string; description: string; status: string
  created_at: string; tenant?: string; property?: string; unit?: string
}

export const authApi = {
  current: () => api<AuthUser>('/api/auth/me'),
  login: (email: string, password: string) => api<AuthUser>('/api/auth/login', {
    method: 'POST', body: JSON.stringify({ email, password }),
  }),
  logout: () => api<void>('/api/auth/logout', { method: 'POST' }),
  acceptInvitation: (input: { token: string; display_name: string; password: string }) =>
    api<{ status: string; email: string; id: string }>('/api/invitations/accept', { method: 'POST', body: JSON.stringify(input) }),
}

export const onboardingApi = {
  tenants: () => api<Tenant[]>('/api/tenants'),
  invitations: () => api<Invitation[]>('/api/invitations'),
  invite: (email: string) => api<Invitation & { token: string }>('/api/invitations', {
    method: 'POST', body: JSON.stringify({ email }),
  }),
  revoke: (id: string) => api<void>(`/api/invitations/${id}/revoke`, { method: 'POST' }),
  createTenancy: (input: { unit_id: string; tenant_id: string; start_date: string; monthly_rent: string; security_deposit_expected: string; due_day: number; proration_method: string }) =>
    api<{ id: string; status: string }>('/api/tenancies', { method: 'POST', body: JSON.stringify(input) }),
}

export const documentsApi = {
  tenancies: () => api<TenancySummary[]>('/api/tenancies'),
  list: (tenancyId: string) => api<TenancyDocument[]>(`/api/tenancies/${tenancyId}/documents`),
  upload: (tenancyId: string, file: File) => api<TenancyDocument>(`/api/tenancies/${tenancyId}/documents`, {
    method: 'POST', body: file, headers: { 'Content-Type': file.type, 'X-Document-Name': file.name },
  }),
  async download(id: string, filename: string) {
    const response = await fetch(`${API_URL}/api/documents/${id}/download`, { credentials: 'include' })
    if (!response.ok) throw new ApiError(response.status, 'Could not download this document.')
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url; link.download = filename; link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}

export type OwnerPayment = {
  id: string; amount: string; currency: string; method: string; reference_code: string | null
  received_at: string; tenant: string; property: string; unit: string; tenancy_id: string
  status: string; can_reverse: boolean
}
export type LateFeeRuleInfo = {
  id?: string; enabled: boolean; fee_type: 'fixed' | 'daily' | 'percentage'; amount: string
  grace_days: number; cap: string | null; partial_payment_basis: 'remaining_principal' | 'original_principal'
  effective_from: string | null
}
export type LateFeeEligibleCharge = {
  id: string; period_start: string; due_date: string; amount: string; principal_remaining: string
  late_fees_assessed: string; assessed_today: boolean
}
export type LateFeeData = { rule: LateFeeRuleInfo; eligible_charges: LateFeeEligibleCharge[]; assessment_date: string }
export const lateFeesApi = {
  get: (tenancyId: string) => api<LateFeeData>(`/api/tenancies/${tenancyId}/late-fees`),
  updateRule: (tenancyId: string, input: Omit<LateFeeRuleInfo, 'id' | 'effective_from'> & { effective_from?: string }) =>
    api<LateFeeRuleInfo>(`/api/tenancies/${tenancyId}/late-fees/rule`, { method: 'PUT', body: JSON.stringify(input) }),
  assess: (chargeId: string) => api<{ fee_amount: string; created: boolean; cumulative_target: string }>(`/api/charges/${chargeId}/late-fee`, { method: 'POST' }),
}
export const paymentsApi = {
  list: () => api<OwnerPayment[]>('/api/payments'),
  record: (input: { tenancy_id: string; tenant_id: string; amount: string; method: string; received_at: string; reference_code: string | null }, idempotencyKey: string) =>
    api<{ id: string; status: string; amount: string; credit_id: string; created: string }>('/api/payments', {
      method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body: JSON.stringify(input),
    }),
  reverse: (id: string, reason: string) => api<{ id: string; payment_id: string; amount: string; status: string }>(`/api/payments/${id}/reverse`, {
    method: 'POST', body: JSON.stringify({ reason }),
  }),
}

export const depositsApi = {
  list: () => api<DepositSummary[]>('/api/security-deposits'),
  transactions: (tenancyId: string) => api<DepositTransaction[]>(`/api/tenancies/${tenancyId}/security-deposit/transactions`),
  updateExpected: (tenancyId: string, amount: string) => api<{ tenancy_id: string; expected: string }>(`/api/tenancies/${tenancyId}/security-deposit/expected`, {
    method: 'PATCH', body: JSON.stringify({ amount }),
  }),
  record: (tenancyId: string, input: { transaction_type: string; amount: string; method: string | null; reference_code: string | null; reason: string | null; occurred_at: string }, key: string) =>
    api<DepositTransaction & { created: boolean }>(`/api/tenancies/${tenancyId}/security-deposit/transactions`, {
      method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(input),
    }),
}

export const tenantApi = {
  portal: () => api<TenantPortalData>('/api/tenant/portal'),
  notificationPreferences: () => api<TenantNotificationPreferences>('/api/tenant/notification-preferences'),
  updateNotificationPreferences: (input: Pick<TenantNotificationPreferences, 'email_enabled' | 'whatsapp_enabled' | 'whatsapp_phone'>) =>
    api<TenantNotificationPreferences>('/api/tenant/notification-preferences', { method: 'PUT', body: JSON.stringify(input) }),
  maintenanceRequests: () => api<MaintenanceRequest[]>('/api/tenant/maintenance-requests'),
  createMaintenanceRequest: (input: { tenancy_id: string; subject: string; description: string }) =>
    api<{ id: string; status: string }>('/api/tenant/maintenance-requests', { method: 'POST', body: JSON.stringify(input) }),
}

export const maintenanceApi = {
  list: () => api<MaintenanceRequest[]>('/api/maintenance-requests'),
  updateStatus: (id: string, status: string) => api<{ id: string; status: string }>(`/api/maintenance-requests/${id}`, {
    method: 'PATCH', body: JSON.stringify({ status }),
  }),
}

export type UtilityAllocation = { tenancy_id: string; unit: string; amount: string }
export type UtilityBill = {
  id: string; property_id: string; property: string; unit_id: string | null; unit: string | null
  utility_type: string; period_start: string; period_end: string; due_date: string; supplier: string
  bill_reference: string | null; amount: string; notes: string | null; status: string; allocations: UtilityAllocation[]
}
export type UtilityMeter = { id: string; property_id: string; property: string; unit_id: string | null; unit: string | null; utility_type: string; meter_name: string; serial_number: string | null; unit_of_measure: string; active: boolean; latest_reading: string | null; latest_read_on: string | null }
export type UtilityMeterReading = { id: string; read_on: string; reading: string; consumption: string; calculated_amount: string | null; utility_bill_id: string | null }
export type PropertyExpense = {
  id: string; property_id: string; property: string; unit_id: string | null; unit: string | null
  category: string; amount: string; spent_on: string; vendor: string; reference_code: string | null; description: string
}
export type InspectionEvidence = { id: string; item_id: string | null; name: string; content_type: string; byte_size: number; created_at: string }
export type InspectionItem = { id: string; area: string; item_name: string; condition: string; notes: string | null; evidence: InspectionEvidence[] }
export type InspectionRecord = {
  id: string; tenancy_id: string; inspection_type: string; inspected_on: string; notes: string | null
  tenant_visible: boolean; status: string; created_at: string; items: InspectionItem[]; evidence: InspectionEvidence[]
}
export const utilitiesApi = {
  bills: () => api<UtilityBill[]>('/api/utility-bills'),
  meters: () => api<UtilityMeter[]>('/api/utility-meters'),
  createMeter: (input: Record<string, unknown>) => api<UtilityMeter>('/api/utility-meters', { method: 'POST', body: JSON.stringify(input) }),
  createRate: (input: Record<string, unknown>) => api<Record<string, string | null>>('/api/utility-rates', { method: 'POST', body: JSON.stringify(input) }),
  readings: (meterId: string) => api<UtilityMeterReading[]>(`/api/utility-meters/${meterId}/readings`),
  recordReading: (meterId: string, input: { read_on: string; reading: string; due_date: string }) => api<UtilityMeterReading & { utility_bill: UtilityBill | null }>(`/api/utility-meters/${meterId}/readings`, { method: 'POST', body: JSON.stringify(input) }),
  createBill: (input: Record<string, unknown>) => api<UtilityBill>('/api/utility-bills', { method: 'POST', body: JSON.stringify(input) }),
  allocate: (id: string, allocations: Array<{ tenancy_id: string; amount: string }>) => api<UtilityBill>(`/api/utility-bills/${id}/allocate`, { method: 'POST', body: JSON.stringify({ allocations }) }),
  expenses: () => api<PropertyExpense[]>('/api/expenses'),
  createExpense: (input: Record<string, unknown>) => api<PropertyExpense>('/api/expenses', { method: 'POST', body: JSON.stringify(input) }),
}
export const inspectionsApi = {
  list: () => api<InspectionRecord[]>('/api/inspections'),
  tenantList: () => api<InspectionRecord[]>('/api/tenant/inspections'),
  create: (input: { tenancy_id: string; inspection_type: string; inspected_on: string; notes: string | null; tenant_visible: boolean }) =>
    api<InspectionRecord>('/api/inspections', { method: 'POST', body: JSON.stringify(input) }),
  addItem: (id: string, input: { area: string; item_name: string; condition: string; notes: string | null }) =>
    api<InspectionItem>(`/api/inspections/${id}/items`, { method: 'POST', body: JSON.stringify(input) }),
  complete: (id: string) => api<InspectionRecord>(`/api/inspections/${id}/complete`, { method: 'POST' }),
  upload: (id: string, file: File, itemId: string | null) => api<InspectionEvidence>(`/api/inspections/${id}/evidence${itemId ? `?item_id=${encodeURIComponent(itemId)}` : ''}`, {
    method: 'POST', body: file, headers: { 'Content-Type': file.type, 'X-Document-Name': file.name },
  }),
  async download(id: string, filename: string) {
    const response = await fetch(`${API_URL}/api/inspection-evidence/${id}/download`, { credentials: 'include' })
    if (!response.ok) throw new ApiError(response.status, 'Could not download this inspection evidence.')
    const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a')
    link.href = url; link.download = filename; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
export type DashboardReport = {
  period: string; period_label: string; period_start: string; period_end: string
  metrics: { total_units: number; occupied_units: number; occupancy_percent: number; rent_charged: string
    payments_received: string; overdue_amount: string; overdue_count: number; expenses: string; expense_count: number
    deposits_due: string; pending_utility_count: number; pending_utility_amount: string; upcoming_move_outs: number
    open_maintenance: number; inspections_in_progress: number }
  collection: Array<{ month: string; rent_charged: string; payments_received: string }>
  properties: Array<{ id: string; name: string; address: string; unit_count: number; occupied_units: number; occupancy_percent: number }>
  attention: Array<{ title: string; detail: string; count: number; path: string; tone: string }>
}
export const reportsApi = {
  dashboard: (period: string) => api<DashboardReport>(`/api/reports/dashboard?period=${encodeURIComponent(period)}`),
  async download(dataset: string, period: string) {
    const response = await fetch(`${API_URL}/api/reports/export.csv?dataset=${encodeURIComponent(dataset)}&period=${encodeURIComponent(period)}`, { credentials: 'include' })
    if (!response.ok) {
      let message = 'Could not export this report.'
      try { message = (await response.json()).detail ?? message } catch { /* retain safe fallback */ }
      throw new ApiError(response.status, message)
    }
    const disposition = response.headers.get('Content-Disposition') ?? ''
    const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? `hearth-${dataset}.csv`
    const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a')
    link.href = url; link.download = filename; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}

export const propertyApi = {
  list: () => api<Property[]>('/api/properties'),
  create: (input: { name: string; address: string; timezone: string }) => api<Property>('/api/properties', {
    method: 'POST', body: JSON.stringify(input),
  }),
  update: (id: string, input: Partial<Pick<Property, 'name' | 'address' | 'timezone'>>) => api<Property>(`/api/properties/${id}`, {
    method: 'PATCH', body: JSON.stringify(input),
  }),
  archive: (id: string) => api<void>(`/api/properties/${id}`, { method: 'DELETE' }),
  units: (id: string) => api<Unit[]>(`/api/properties/${id}/units`),
  createUnit: (id: string, unit_number: string) => api<Unit>(`/api/properties/${id}/units`, {
    method: 'POST', body: JSON.stringify({ unit_number }),
  }),
}
