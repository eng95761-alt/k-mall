import React, { useState, useEffect } from 'react'
import { RouterItem } from '../../types'
import { api } from '../../api'
import { Layers, Network, Activity, ArrowDownLeft, ArrowUpRight, ShieldCheck, Server } from 'lucide-react'

interface NetworkTabProps {
  routers: RouterItem[]
  selectedRouterId: string | null
  onSelectRouter: (id: string) => void
}

export const NetworkTab: React.FC<NetworkTabProps> = ({
  routers,
  selectedRouterId,
  onSelectRouter,
}) => {
  const [activeRouterId, setActiveRouterId] = useState<string>(
    selectedRouterId || (routers[0]?.id ?? 'km222-l009')
  )
  const [snapshot, setSnapshot] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (selectedRouterId) {
      setActiveRouterId(selectedRouterId)
    }
  }, [selectedRouterId])

  useEffect(() => {
    if (!activeRouterId) return
    let mounted = true
    setLoading(true)
    api
      .getRouterSnapshot(activeRouterId)
      .then((data) => {
        if (mounted) setSnapshot(data)
      })
      .catch(() => {
        if (mounted) setSnapshot(null)
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [activeRouterId])

  const fmtBytes = (b: number | null) => {
    if (!b) return '0 B'
    const mb = b / (1024 * 1024)
    if (mb > 1024) return `${(mb / 1024).toFixed(2)} GB`
    return `${mb.toFixed(1)} MB`
  }

  return (
    <div className="space-y-6">
      {/* Topology summary banner */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-slate-900 to-slate-900/60 border border-slate-800">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 text-slate-100 font-bold text-sm">
            <Network className="w-5 h-5 text-cyan-400" />
            <span>طوبولوجيا شبكة مجمع كربلاء التجاري ومسار الفيلانات (VLANs)</span>
          </div>
          <span className="text-xs px-2.5 py-1 rounded-full bg-cyan-950 border border-cyan-800 text-cyan-300">
            4 راوترات رئيسية + مزود RB4011
          </span>
        </div>

        {/* Visual Topology Diagram */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {routers.map((r) => {
            const isSelected = r.id === activeRouterId
            return (
              <div
                key={r.id}
                onClick={() => {
                  setActiveRouterId(r.id)
                  onSelectRouter(r.id)
                }}
                className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-cyan-950/40 border-cyan-700 shadow-md shadow-cyan-950/50'
                    : 'bg-slate-950/40 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Server className={`w-4 h-4 ${isSelected ? 'text-cyan-400' : 'text-slate-400'}`} />
                    <span className="text-xs font-bold text-slate-200">{r.name}</span>
                  </div>
                  <span
                    className={`w-2 h-2 rounded-full ${
                      r.online ? 'bg-emerald-400' : 'bg-rose-500'
                    }`}
                  />
                </div>
                <div className="text-[11px] font-mono text-cyan-300 mb-1">
                  {r.vlan_id ? `VLAN ID: ${r.vlan_id}` : 'Direct Interface'}
                </div>
                <div className="text-[11px] font-mono text-slate-400">
                  {r.subnet || '192.168.0.x'}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Selected Router Interfaces Detail */}
      <div className="rounded-2xl bg-slate-900/80 border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-100">
              واجهات وفيلانات الراوتر المختار: {routers.find((r) => r.id === activeRouterId)?.name}
            </h3>
          </div>
          {loading && <span className="text-xs text-cyan-400 animate-pulse font-mono">جاري جلب الواجهات...</span>}
        </div>

        {/* Interfaces Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-right text-xs">
            <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">اسم الواجهة (Interface)</th>
                <th className="p-3">النوع (Type)</th>
                <th className="p-3">الحالة (Status)</th>
                <th className="p-3">عنوان الماك (MAC Address)</th>
                <th className="p-3">حركة التنزيل (RX Traffic)</th>
                <th className="p-3">حركة الرفع (TX Traffic)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {snapshot?.interfaces && snapshot.interfaces.length > 0 ? (
                snapshot.interfaces.map((iface: any, idx: number) => (
                  <tr key={idx} className="hover:bg-slate-800/30 transition">
                    <td className="p-3 font-semibold font-mono text-slate-100 flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full ${
                          iface.running === 'true' || iface.running === true
                            ? 'bg-emerald-400'
                            : 'bg-slate-600'
                        }`}
                      />
                      <span>{iface.name}</span>
                    </td>
                    <td className="p-3 font-mono text-slate-400">{iface.type || 'ether'}</td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                          iface.running === 'true' || iface.running === true
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : 'bg-slate-800 text-slate-500'
                        }`}
                      >
                        {iface.running === 'true' || iface.running === true ? 'RUNNING' : 'DOWN'}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-slate-400">{iface['mac-address'] || '—'}</td>
                    <td className="p-3 font-mono text-cyan-400">
                      <div className="flex items-center gap-1">
                        <ArrowDownLeft className="w-3.5 h-3.5 text-cyan-400" />
                        <span>{fmtBytes(parseInt(iface['rx-byte']) || 0)}</span>
                      </div>
                    </td>
                    <td className="p-3 font-mono text-indigo-400">
                      <div className="flex items-center gap-1">
                        <ArrowUpRight className="w-3.5 h-3.5 text-indigo-400" />
                        <span>{fmtBytes(parseInt(iface['tx-byte']) || 0)}</span>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-slate-500">
                    {loading
                      ? 'جاري فحص الواجهات من المايكروتك...'
                      : 'لا توجد بيانات واجهات مفصلة متاحة حالياً لهذا الجهاز (يتم الفحص الدوري كل 5 دورات)'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
