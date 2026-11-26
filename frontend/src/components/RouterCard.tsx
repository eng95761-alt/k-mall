import React, { useState } from 'react'
import {
  Server,
  Activity,
  Cpu,
  HardDrive,
  Users,
  Radio,
  ExternalLink,
  RefreshCw,
  AlertTriangle,
  Clock,
  CheckCircle2,
} from 'lucide-react'
import { RouterItem } from '../types'
import { api } from '../api'

interface RouterCardProps {
  router: RouterItem
  onSelectRouter: (routerId: string) => void
  onTestSuccess: () => void
}

export const RouterCard: React.FC<RouterCardProps> = ({
  router,
  onSelectRouter,
  onTestSuccess,
}) => {
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.testRouter(router.id)
      setTestResult(`زمن الاستجابة: ${res.latency_ms} ms`)
      onTestSuccess()
    } catch (e: any) {
      setTestResult(`فشل: ${e.message}`)
    } finally {
      setTesting(false)
    }
  }

  // Format MB
  const fmtMb = (bytes: number | null) => {
    if (bytes === null || bytes === undefined) return '—'
    return `${Math.round(bytes / (1024 * 1024))} MB`
  }

  // Calculate memory percent
  const memPct =
    router.mem_total && router.mem_free !== null
      ? Math.max(0, Math.min(100, Math.round(((router.mem_total - router.mem_free) / router.mem_total) * 100)))
      : null

  // Calculate disk percent
  const diskPct =
    router.hdd_total && router.hdd_free !== null
      ? Math.max(0, Math.min(100, Math.round(((router.hdd_total - router.hdd_free) / router.hdd_total) * 100)))
      : null

  const cpuColor =
    (router.cpu_load || 0) > 85 ? 'bg-rose-500' : (router.cpu_load || 0) > 60 ? 'bg-amber-500' : 'bg-emerald-500'

  return (
    <div
      className={`rounded-2xl border transition-all duration-200 overflow-hidden ${
        router.online
          ? 'bg-slate-900/80 border-slate-800 hover:border-slate-700 shadow-md shadow-slate-950/40'
          : 'bg-rose-950/10 border-rose-900/40'
      }`}
    >
      {/* Card Header */}
      <div className="p-3.5 border-b border-slate-800/80 bg-slate-900/40 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <div
            className={`w-9 h-9 rounded-xl flex items-center justify-center border shrink-0 ${
              router.online
                ? 'bg-slate-800 text-cyan-400 border-slate-700'
                : 'bg-rose-950 text-rose-400 border-rose-900'
            }`}
          >
            <Server className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <h3 className="text-xs font-bold text-slate-100 font-['Cairo'] truncate max-w-[150px]" title={router.name}>
                {router.name}
              </h3>
              {router.vlan_id && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300 font-mono shrink-0 whitespace-nowrap">
                  VLAN {router.vlan_id}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mt-0.5 font-mono flex-wrap">
              <span dir="ltr" className="inline-block">{router.subnet || 'Tunnel'}</span>
              <span>•</span>
              <span className="uppercase text-[9px] text-slate-500">{router.method}</span>
              {router.board && (
                <>
                  <span>•</span>
                  <span dir="ltr" className="text-slate-400 inline-block font-sans">{router.board}</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Online / Offline status badge */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          <div
            className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap ${
              router.online
                ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/60'
                : 'bg-rose-950/80 text-rose-300 border border-rose-800/60'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                router.online ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'
              }`}
            />
            <span>{router.online ? 'متصل' : 'غير متصل'}</span>
          </div>
          {router.latency_ms !== null && (
            <span dir="ltr" className="text-[10px] font-mono text-slate-400 inline-block">
              {router.latency_ms} ms
            </span>
          )}
        </div>
      </div>

      {/* Main Stats Body */}
      <div className="p-4 space-y-3.5">
        {/* CPU load */}
        <div>
          <div className="flex justify-between items-center text-xs mb-1">
            <span className="text-slate-400 flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-slate-400" />
              <span>استهلاك المعالج (CPU)</span>
            </span>
            <span dir="ltr" className="font-mono font-medium text-slate-200 inline-block">
              {router.cpu_load !== null ? `${router.cpu_load}%` : '—'}
            </span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${cpuColor}`}
              style={{ width: `${Math.min(100, Math.max(0, router.cpu_load || 0))}%` }}
            />
          </div>
        </div>

        {/* Memory Usage */}
        <div>
          <div className="flex justify-between items-center text-xs mb-1">
            <span className="text-slate-400 flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-slate-400" />
              <span>الذاكرة (RAM)</span>
            </span>
            <span dir="ltr" className="font-mono text-[11px] text-slate-300 inline-block">
              {router.mem_total
                ? `${fmtMb(router.mem_total - (router.mem_free || 0))} / ${fmtMb(router.mem_total)}`
                : fmtMb(router.mem_free)}
            </span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-cyan-500 h-full rounded-full transition-all duration-500"
              style={{ width: `${memPct || (router.mem_free ? 25 : 0)}%` }}
            />
          </div>
        </div>

        {/* Storage / Hard Drive */}
        {router.hdd_total && (
          <div>
            <div className="flex justify-between items-center text-xs mb-1">
              <span className="text-slate-400 flex items-center gap-1.5">
                <HardDrive className="w-3.5 h-3.5 text-slate-400" />
                <span>التخزين (Storage)</span>
              </span>
              <span dir="ltr" className="font-mono text-[11px] text-slate-300 inline-block">
                {fmtMb(router.hdd_total - (router.hdd_free || 0))} / {fmtMb(router.hdd_total)}
              </span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-indigo-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${diskPct || 0}%` }}
              />
            </div>
          </div>
        )}

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/60">
          <div className="bg-slate-950/40 p-2.5 rounded-xl border border-slate-800/60">
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 mb-1">
              <Radio className="w-3 h-3 text-cyan-400" />
              <span>زبائن الهوتسبوت</span>
            </div>
            <div className="text-base font-bold font-mono text-cyan-300">
              {router.hotspot_active !== null ? router.hotspot_active : '—'}
            </div>
          </div>

          <div className="bg-slate-950/40 p-2.5 rounded-xl border border-slate-800/60">
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 mb-1">
              <Users className="w-3 h-3 text-indigo-400" />
              <span>سشنات / كروت UM</span>
            </div>
            <div className="text-base font-bold font-mono text-indigo-300">
              {router.um_users !== null ? router.um_users : '—'}
              {router.um_sessions !== null && router.um_sessions !== undefined && (
                <span className="text-xs font-normal text-slate-500 mr-1">
                  ({(router.um_sessions ?? 0).toLocaleString('ar-IQ')} سشن)
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Error notice if offline */}
        {!router.online && router.last_error && (
          <div className="p-2 rounded-lg bg-rose-950/40 border border-rose-900/60 text-rose-300 text-[11px] flex items-start gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span className="line-clamp-2">{router.last_error}</span>
          </div>
        )}

        {/* Live Test Result notice */}
        {testResult && (
          <div className="p-2 rounded-lg bg-cyan-950/40 border border-cyan-800/60 text-cyan-300 text-[11px] flex items-center justify-between">
            <span>{testResult}</span>
            <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400" />
          </div>
        )}
      </div>

      {/* Card Footer Actions */}
      <div className="px-4 py-3 bg-slate-900/60 border-t border-slate-800/80 flex items-center justify-between text-xs">
        <button
          onClick={handleTest}
          disabled={testing}
          className="flex items-center gap-1.5 text-slate-300 hover:text-cyan-400 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${testing ? 'animate-spin text-cyan-400' : ''}`} />
          <span>{testing ? 'جاري الفحص...' : 'فحص فوري'}</span>
        </button>

        <button
          onClick={() => onSelectRouter(router.id)}
          className="flex items-center gap-1.5 text-cyan-400 hover:text-cyan-300 font-medium transition"
        >
          <span>التفاصيل والواجهات</span>
          <ExternalLink className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}
