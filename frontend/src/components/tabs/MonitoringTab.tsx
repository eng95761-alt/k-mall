import React from 'react'
import { RouterItem, AlertItem } from '../../types'
import { RouterCard } from '../RouterCard'
import { ActiveClientsTable } from '../ActiveClientsTable'
import { AlertCircle, CheckCircle2, ShieldCheck } from 'lucide-react'
import { api } from '../../api'

interface MonitoringTabProps {
  routers: RouterItem[]
  alerts: AlertItem[]
  onSelectRouter: (routerId: string) => void
  onRefresh: () => void
}

export const MonitoringTab: React.FC<MonitoringTabProps> = ({
  routers,
  alerts,
  onSelectRouter,
  onRefresh,
}) => {
  const handleAck = async (id: number) => {
    try {
      await api.ackAlert(id)
      onRefresh()
    } catch (e: any) {
      alert(`خطأ: ${e.message}`)
    }
  }

  return (
    <div className="space-y-6">
      {/* Alerts notification banner */}
      {alerts && alerts.length > 0 && (
        <div className="p-4 rounded-2xl bg-amber-950/20 border border-amber-800/50 space-y-2">
          <div className="flex items-center gap-2 text-amber-400 font-bold text-sm">
            <AlertCircle className="w-5 h-5" />
            <span>تنبيهات النظام النشطة ({alerts.length})</span>
          </div>
          <div className="space-y-1.5">
            {alerts.map((al) => (
              <div
                key={al.id}
                className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-300"
              >
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  <span className="font-semibold text-amber-300">[{al.router_id}]</span>
                  <span>{al.message}</span>
                </div>
                <button
                  onClick={() => handleAck(al.id)}
                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition text-[11px]"
                >
                  إغلاق التنبيه
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Routers Grid */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <span>راوترات المجمع التجارية</span>
            <span className="text-xs font-normal text-slate-400 font-mono">
              ({routers.filter((r) => r.online).length} متصل / {routers.length} إجمالي)
            </span>
          </h2>
          <div className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-950/40 px-2.5 py-1 rounded-lg border border-emerald-900/40">
            <ShieldCheck className="w-4 h-4" />
            <span>اتصال محمي ومشفر WireGuard</span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {routers.map((r) => (
            <RouterCard
              key={r.id}
              router={r}
              onSelectRouter={onSelectRouter}
              onTestSuccess={onRefresh}
            />
          ))}
        </div>
      </div>

      {/* Active Hotspot Clients Live Table */}
      <ActiveClientsTable routers={routers} onRefreshOverview={onRefresh} />

      {/* Footer Info */}
      <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 text-xs text-slate-400 flex flex-col sm:flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>تُحدّث البيانات تلقائياً كل 15 ثانية. أوامر MikroTik API مقيدة بقائمة القراءة فقط لحماية الشبكة.</span>
        </div>
        <div className="text-[11px] text-slate-500 font-mono">
          K-Mall Enterprise • Iraq / Karbala
        </div>
      </div>
    </div>
  )
}
