import React, { useState, useEffect } from 'react'
import {
  Radio,
  Search,
  Server,
  Clock,
  Calendar,
  ArrowDownLeft,
  ArrowUpRight,
  RefreshCw,
  Download,
  Filter,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react'
import { HotspotActiveClient, RouterItem } from '../types'
import { api } from '../api'

interface ActiveClientsTableProps {
  routers: RouterItem[]
  onRefreshOverview?: () => void
}

export const ActiveClientsTable: React.FC<ActiveClientsTableProps> = ({
  routers,
  onRefreshOverview,
}) => {
  const [clients, setClients] = useState<HotspotActiveClient[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [selectedRouter, setSelectedRouter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')

  const loadClients = async () => {
    setLoading(true)
    try {
      const res = await api.getActiveClients(
        selectedRouter === 'all' ? undefined : selectedRouter,
        searchQuery
      )
      setClients(res.clients || [])
    } catch (err) {
      console.error('Failed to load active clients:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadClients()
  }, [selectedRouter])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    loadClients()
  }

  const fmtBytes = (bytes: number) => {
    if (!bytes) return '0 B'
    const mb = bytes / (1024 * 1024)
    if (mb > 1024) return `${(mb / 1024).toFixed(2)} GB`
    return `${mb.toFixed(1)} MB`
  }

  // Export to CSV
  const exportCsv = () => {
    const headers = [
      'Username',
      'RouterBoard',
      'VLAN',
      'Profile',
      'IP Address',
      'MAC Address',
      'Activated At',
      'Expires At',
      'Time Left',
      'Uptime',
      'Download (Bytes)',
      'Upload (Bytes)',
    ]
    const rows = clients.map((c) => [
      c.username,
      c.router_name,
      c.vlan_id || '—',
      c.profile,
      c.ip_address,
      c.mac_address,
      c.activated_at,
      c.expires_at,
      c.time_left,
      c.uptime,
      c.bytes_out,
      c.bytes_in,
    ])
    const csvContent = [headers.join(','), ...rows.map((r) => r.map((cell) => `"${cell}"`).join(','))].join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `active_subscribers_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div id="active-clients-section" className="rounded-2xl bg-slate-900/90 border border-slate-800 overflow-hidden shadow-xl">
      {/* Table Header & Controls */}
      <div className="p-4 sm:p-5 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-cyan-950 border border-cyan-800 flex items-center justify-center">
              <Radio className="w-4 h-4 text-cyan-400 animate-pulse" />
            </div>
            <h3 className="text-base font-bold text-slate-100 font-['Cairo'] flex items-center gap-2">
              <span>زبائن الهوتسبوت المتصلون الآن</span>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-cyan-950 border border-cyan-800 text-cyan-300 font-mono">
                {clients.length} مشترك نشط
              </span>
            </h3>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            عرض مباشر للمشتركين المتصلين، تاريخ التفعيل، تاريخ الانتهاء، والراوتر بورد الخاص بكل مشترك
          </p>
        </div>

        {/* Filters and Actions */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Router select */}
          <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={selectedRouter}
              onChange={(e) => setSelectedRouter(e.target.value)}
              className="bg-transparent text-slate-200 text-xs focus:outline-none cursor-pointer"
            >
              <option value="all">جميع الراوترات ({clients.length})</option>
              {routers.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.hotspot_active ?? 0})
                </option>
              ))}
            </select>
          </div>

          {/* Search form */}
          <form onSubmit={handleSearchSubmit} className="flex items-center gap-1">
            <div className="relative">
              <input
                type="text"
                placeholder="ابحث باليوزر، IP، الماك..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 w-44 sm:w-52"
              />
            </div>
            <button
              type="submit"
              className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition"
              title="بحث"
            >
              <Search className="w-3.5 h-3.5" />
            </button>
          </form>

          {/* Refresh & Export */}
          <button
            onClick={() => {
              loadClients()
              if (onRefreshOverview) onRefreshOverview()
            }}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-cyan-400 transition"
            title="تحديث القائمة"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
          </button>

          <button
            onClick={exportCsv}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-800 text-emerald-300 text-xs font-medium transition"
            title="تصدير كملف CSV"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">تصدير CSV</span>
          </button>
        </div>
      </div>

      {/* Table Content */}
      <div className="overflow-x-auto">
        <table className="w-full text-right text-xs">
          <thead className="bg-slate-950/70 text-slate-400 border-b border-slate-800 font-medium">
            <tr>
              <th className="p-3.5">اسم المشترك / الكود</th>
              <th className="p-3.5">الراوتر بورد (RouterBoard)</th>
              <th className="p-3.5">الباقة / البروفايل</th>
              <th className="p-3.5">تاريخ التفعيل (البداية)</th>
              <th className="p-3.5">تاريخ الانتهاء (النهاية)</th>
              <th className="p-3.5">الوقت المتبقي</th>
              <th className="p-3.5">عنوان IP والماك</th>
              <th className="p-3.5 text-center">البيانات (تنزيل / رفع)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 text-slate-300">
            {clients.length > 0 ? (
              clients.map((c, idx) => (
                <tr key={idx} className="hover:bg-slate-800/30 transition">
                  {/* Username & online status */}
                  <td className="p-3.5">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                      <span className="font-mono font-bold text-slate-100 select-all text-xs">
                        {c.username}
                      </span>
                    </div>
                  </td>

                  {/* RouterBoard & VLAN */}
                  <td className="p-3.5">
                    <div className="flex items-center gap-1.5">
                      <Server className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="font-semibold text-slate-200">{c.router_name}</span>
                    </div>
                    {c.vlan_id && (
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-cyan-300 mt-0.5 inline-block">
                        VLAN {c.vlan_id}
                      </span>
                    )}
                  </td>

                  {/* Profile */}
                  <td className="p-3.5">
                    <span className="px-2 py-0.5 rounded-lg bg-indigo-950/80 border border-indigo-800/60 text-indigo-300 font-mono text-[11px]">
                      {c.profile}
                    </span>
                  </td>

                  {/* Activated At */}
                  <td className="p-3.5">
                    <div className="flex items-center gap-1.5 text-slate-200">
                      <Calendar className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                      <span dir="ltr" className="font-mono text-[11px] inline-block">
                        {c.activated_at}
                      </span>
                    </div>
                    {c.uptime && (
                      <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                        متصل منذ: {c.uptime}
                      </div>
                    )}
                  </td>

                  {/* Expires At */}
                  <td className="p-3.5">
                    <div className="flex items-center gap-1.5 text-slate-200">
                      <Clock className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                      <span dir="ltr" className="font-mono text-[11px] font-semibold text-amber-300 inline-block">
                        {c.expires_at}
                      </span>
                    </div>
                  </td>

                  {/* Time Left Badge */}
                  <td className="p-3.5">
                    <span
                      className={`px-2.5 py-1 rounded-full text-[11px] font-semibold inline-block ${
                        c.is_expired
                          ? 'bg-rose-950 text-rose-400 border border-rose-800'
                          : 'bg-emerald-950 text-emerald-300 border border-emerald-800/80'
                      }`}
                    >
                      {c.time_left}
                    </span>
                  </td>

                  {/* IP & MAC */}
                  <td className="p-3.5">
                    <div dir="ltr" className="font-mono text-cyan-300 text-[11px] text-right">
                      {c.ip_address}
                    </div>
                    <div dir="ltr" className="font-mono text-slate-500 text-[10px] text-right">
                      {c.mac_address}
                    </div>
                  </td>

                  {/* Download / Upload */}
                  <td className="p-3.5 text-center">
                    <div className="flex items-center justify-center gap-3 text-[11px] font-mono">
                      <span className="flex items-center gap-1 text-cyan-400" title="تنزيل">
                        <ArrowDownLeft className="w-3 h-3 text-cyan-400" />
                        <span dir="ltr" className="inline-block">{fmtBytes(c.bytes_out)}</span>
                      </span>
                      <span className="flex items-center gap-1 text-indigo-400" title="رفع">
                        <ArrowUpRight className="w-3 h-3 text-indigo-400" />
                        <span dir="ltr" className="inline-block">{fmtBytes(c.bytes_in)}</span>
                      </span>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={8} className="p-8 text-center text-slate-500">
                  {loading
                    ? 'جاري جلب المشتركين النشطين من الراوترات...'
                    : 'لا يوجد مشتركون نشطون متطابقون مع الفلتر الحالي.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
