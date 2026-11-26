export interface User {
  id: number
  username: string
  role: 'owner' | 'staff' | 'viewer'
  active?: boolean
}

export interface RouterItem {
  id: string
  name: string
  host?: string | null
  method: 'api' | 'umweb' | 'tcp'
  vlan_id: number | null
  subnet: string | null
  note: string | null
  online: boolean
  fail_count: number
  last_seen: string | null
  last_check: string | null
  last_error: string | null
  latency_ms: number | null
  identity: string | null
  version: string | null
  board: string | null
  uptime: string | null
  cpu_load: number | null
  mem_free: number | null
  mem_total: number | null
  hdd_free: number | null
  hdd_total: number | null
  hotspot_active: number | null
  um_users: number | null
  um_sessions: number | null
  rx_bytes: number | null
  tx_bytes: number | null
}

export interface HotspotActiveClient {
  username: string
  router_id: string
  router_name: string
  vlan_id: number | null
  ip_address: string
  mac_address: string
  server: string
  profile: string
  uptime: string
  activated_at: string
  expires_at: string
  time_left: string
  is_expired: boolean
  bytes_in: number
  bytes_out: number
}

export interface SystemOverview {
  user: User
  system_name: string
  allow_router_writes: boolean
  total_routers: number
  online_routers: number
  active_clients: number
  total_um_users: number
  total_um_sessions: number
  open_alerts: number
  today_sales_iqd: number
  total_debt_iqd: number
  routers: RouterItem[]
}

export interface AlertItem {
  id: number
  router_id: string
  kind: string
  level: 'info' | 'warning' | 'critical'
  message: string
  opened_at: string
}

export interface UMProfile {
  name: string
  price: number
  validity?: string
  rate_limit?: string
  starts_at?: string
  shared_users?: number | string
  raw?: Record<string, any>
}

export interface VoucherBatch {
  id: number
  batch_code: string
  router_id: string
  um_version: string
  profile_name: string
  count: number
  price_iqd: number
  status: 'draft' | 'pushed' | 'partial' | 'failed'
  created_by: string
  created_at: string
  notes: string
}

export interface VoucherCard {
  id: number
  batch_id: number
  router_id: string
  username: string
  password?: string
  profile_name: string
  price_iqd: number
  pushed_to_router: boolean
  router_item_id?: string | null
  sold: boolean
  created_at: string
}

export interface PlanItem {
  id: number
  name: string
  speed_label: string
  duration_days: number
  price_iqd: number
  router_scope: string
  notes: string
  active: boolean
}

export interface CustomerItem {
  id: number
  full_name: string
  phone: string
  shop_unit: string
  notes: string
  created_at: string
}

export interface SubscriptionItem {
  id: number
  customer_id: number
  customer_name: string
  plan_id: number
  plan_name: string
  router_id: string
  voucher_code: string
  activated_at: string
  expires_at: string
  price_iqd: number
  paid_iqd: number
  balance_iqd: number
  status: 'active' | 'expired' | 'canceled'
  notes: string
}

export interface CleanupInspection {
  router_id: string
  router_name: string
  method: string
  total_sessions?: number
  closed_sessions_count: number
  active_sessions_count: number
  expired_users_count: number
  expired_count?: number
  sqldb_size_mb?: number | null
  estimated_reclaimed_kb?: number
  details?: string
  web_url?: string | null
  expired_users?: any[]
}

export interface AuditRecord {
  ts: string
  username: string | null
  action: string
  detail: string | null
  ip: string | null
}

export interface ChangeRecord {
  op_id: string
  ts: string
  router_id: string
  operator: string
  action: string
  proposal: string
  approval_record: string
  result: 'success' | 'failed' | 'blocked'
  detail: string
  rollback_hint: string
}
