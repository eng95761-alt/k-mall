import {
  AuditRecord,
  ChangeRecord,
  CleanupInspection,
  CustomerItem,
  HotspotActiveClient,
  PlanItem,
  SubscriptionItem,
  SystemOverview,
  UMProfile,
  VoucherBatch,
  VoucherCard,
} from './types'

const API_BASE = '/api'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  headers.set('x-kmall', '1')
  if (options.body && typeof options.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  if (res.status === 401 && !path.startsWith('/login')) {
    window.location.hash = '#login'
    throw new Error('انتهت الجلسة، يرجى تسجيل الدخول مجدداً')
  }

  if (!res.ok) {
    let msg = `خطأ ${res.status}`
    try {
      const data = await res.json()
      msg = data.detail || data.message || msg
    } catch {
      // ignore
    }
    throw new Error(msg)
  }

  return res.json()
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    request<{ username: string; role: string }>('/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ ok: boolean }>('/logout', { method: 'POST' }),
  me: () => request<{ id: number; username: string; role: string }>('/me'),

  // Overview
  getOverview: async (): Promise<SystemOverview> => {
    const data = await request<any>('/overview')
    const totals = data.totals || {}
    const routers = (data.routers || []).map((r: any) => {
      const lat = r.latest || r.latest_full || {}
      return {
        id: r.id,
        name: r.name,
        method: r.method,
        vlan_id: r.vlan_id ?? null,
        subnet: r.subnet ?? null,
        note: r.note ?? null,
        online: Boolean(r.online),
        fail_count: r.fail_count || 0,
        last_seen: r.last_seen ?? null,
        last_check: r.last_check ?? null,
        last_error: r.last_error ?? null,
        latency_ms: lat.latency_ms ?? null,
        identity: lat.identity ?? null,
        version: lat.version ?? null,
        board: lat.board ?? null,
        uptime: lat.uptime ?? null,
        cpu_load: lat.cpu_load ?? null,
        mem_free: lat.mem_free ?? null,
        mem_total: lat.mem_total ?? null,
        hdd_free: lat.hdd_free ?? null,
        hdd_total: lat.hdd_total ?? null,
        hotspot_active: lat.hotspot_active ?? null,
        um_users: lat.um_users ?? null,
        um_sessions: lat.um_sessions ?? null,
        rx_bytes: lat.rx_bytes ?? null,
        tx_bytes: lat.tx_bytes ?? null,
      }
    })

    return {
      user: data.user || { id: 1, username: 'owner', role: 'owner' },
      system_name: 'شبكة مجمع كربلاء التجاري',
      allow_router_writes: Boolean(data.allow_router_writes),
      total_routers: totals.routers ?? routers.length,
      online_routers: totals.online ?? routers.filter((r: any) => r.online).length,
      active_clients: totals.hotspot_active ?? 0,
      total_um_users: totals.um_users ?? 0,
      total_um_sessions: routers.reduce((acc: number, r: any) => acc + (r.um_sessions || 0), 0),
      open_alerts: (data.alerts || []).length,
      today_sales_iqd: totals.sales_today_iqd ?? 0,
      total_debt_iqd: totals.outstanding_iqd ?? 0,
      routers,
    }
  },
  getSummary: () => request<any>('/summary'),

  // Hotspot Active Clients
  getActiveClients: (routerId?: string, q = '') =>
    request<{ count: number; clients: HotspotActiveClient[] }>(
      `/hotspot/active?${routerId && routerId !== 'all' ? `router_id=${routerId}&` : ''}q=${encodeURIComponent(q)}`
    ),

  // Routers
  getRouter: (id: string) => request<any>(`/routers/${id}`),
  getRouterSnapshot: (id: string) => request<any>(`/routers/${id}/snapshot`),
  getRouterHistory: (id: string, hours = 24) =>
    request<any[]>(`/routers/${id}/history?hours=${hours}`),
  testRouter: (id: string) => request<any>(`/routers/${id}/test`, { method: 'POST' }),

  // Alerts
  getAlerts: () => request<any[]>('/alerts'),
  ackAlert: (id: number) => request<any>(`/alerts/${id}/ack`, { method: 'POST' }),

  // Settings
  getSettings: () => request<any>('/settings'),
  updateSettings: (data: any) =>
    request<any>('/settings', { method: 'POST', body: JSON.stringify(data) }),

  // Vouchers & Profiles
  getProfiles: (routerId: string) =>
    request<{ profiles: UMProfile[]; um_version: string }>(`/vouchers/profiles/${routerId}`),
  getBatches: () =>
    request<{ batches: VoucherBatch[]; allow_router_writes: boolean }>('/vouchers/batches'),
  getBatchCards: async (batchId: number) => {
    const res = await request<any>(`/vouchers/batches/${batchId}`)
    return { batch: res.batch || res, cards: res.cards || [] }
  },
  generateBatch: async (data: {
    router_id: string
    profile_name: string
    count: number
    prefix: string
    user_len: number
    pass_len: number
    digits_only: boolean
    price_iqd: number
    notes: string
  }) => {
    const res = await request<{ id: number; batch_code: string }>('/vouchers/batches', {
      method: 'POST',
      body: JSON.stringify(data),
    })
    return { batch_id: res.id, batch_code: res.batch_code, count: data.count }
  },
  getBatchProposal: (batchId: number) =>
    request<{ proposal: any; allow_writes: boolean }>(`/vouchers/proposals/${batchId}`),
  pushBatch: (batchId: number, confirmRouterId: string) =>
    request<any>(`/vouchers/batches/${batchId}/push`, {
      method: 'POST',
      body: JSON.stringify({ approved: true, confirm_router_id: confirmRouterId }),
    }),

  // Cleanup & Pruning
  inspectCleanup: async (routerId: string, minAgeDays = 0): Promise<CleanupInspection> => {
    const data = await request<any>(`/cleanup/${routerId}/preview?min_age_days=${minAgeDays}`)
    const totalSess = data.total_sessions || 0
    const activeCount = data.active_sessions ?? 0
    const closedCount = (data.old_closed_sessions || []).length || Math.max(0, totalSess - activeCount)
    let dbSizeMb: number | null = null
    if (Array.isArray(data.db_info)) {
      const match = data.db_info.find((item: any) => item.address === 'Database size')
      if (match && match.interface) {
        const num = parseFloat(match.interface)
        if (!isNaN(num)) dbSizeMb = num
      }
    }
    return {
      router_id: data.router_id,
      router_name: data.router_name,
      method: data.method,
      total_sessions: totalSess,
      closed_sessions_count: closedCount,
      active_sessions_count: activeCount,
      expired_users_count: data.expired_count || 0,
      sqldb_size_mb: dbSizeMb || data.sqldb_size_mb || null,
      estimated_reclaimed_kb: Math.round(closedCount * 0.25),
      details: `${data.router_name} (${data.method.toUpperCase()}) • السشنات النشطة محمية`,
      web_url: data.web_url,
      expired_users: data.expired_users || [],
    }
  },
  executeCleanup: (routerId: string, action: string, minAgeDays = 0) =>
    request<any>(`/cleanup/${routerId}/execute`, {
      method: 'POST',
      body: JSON.stringify({
        approved: true,
        confirm_router_id: routerId,
        action: action,
        ids: ['all_expired'],
        min_age_days: minAgeDays,
      }),
    }),

  // Commercial
  getPlans: () => request<PlanItem[]>('/plans'),
  createPlan: (data: any) =>
    request<PlanItem>('/plans', { method: 'POST', body: JSON.stringify(data) }),
  getCustomers: () => request<CustomerItem[]>('/customers'),
  createCustomer: (data: any) =>
    request<CustomerItem>('/customers', { method: 'POST', body: JSON.stringify(data) }),
  getSubscriptions: () => request<SubscriptionItem[]>('/subscriptions'),
  createSubscription: (data: any) =>
    request<{ id: number }>('/subscriptions', { method: 'POST', body: JSON.stringify(data) }),
  addPayment: (subId: number, data: { amount_iqd: number; method: string; note: string }) =>
    request<any>(`/subscriptions/${subId}/payments`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Audit & Changes
  getAudit: (limit = 100) => request<AuditRecord[]>(`/audit?limit=${limit}`),
  getChanges: (limit = 100) => request<ChangeRecord[]>(`/changes?limit=${limit}`),
}
