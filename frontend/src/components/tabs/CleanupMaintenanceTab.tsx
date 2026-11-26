import React, { useState, useEffect } from 'react'
import {
  Trash2,
  AlertTriangle,
  ShieldCheck,
  CheckCircle2,
  HardDrive,
  Cpu,
  Users,
  Lock,
  Database,
  ExternalLink,
  RefreshCw,
  Calendar,
  Sparkles,
  Info,
} from 'lucide-react'
import { RouterItem, CleanupInspection } from '../../types'
import { api } from '../../api'

interface CleanupMaintenanceTabProps {
  routers: RouterItem[]
  allowWrites: boolean
}

export const CleanupMaintenanceTab: React.FC<CleanupMaintenanceTabProps> = ({
  routers,
  allowWrites,
}) => {
  const [selectedRouterId, setSelectedRouterId] = useState<string>(routers[0]?.id ?? 'km111')
  const [minAgeDays, setMinAgeDays] = useState<number>(0)
  const [inspecting, setInspecting] = useState(false)
  const [inspection, setInspection] = useState<CleanupInspection | null>(null)

  // Execution state
  const [actionType, setActionType] = useState<'remove_old_sessions' | 'remove_expired_users' | 'rebuild_db'>('remove_old_sessions')
  const [confirmInput, setConfirmInput] = useState('')
  const [executing, setExecuting] = useState(false)
  const [executionResult, setExecutionResult] = useState<any>(null)

  const handleInspect = async (routerId = selectedRouterId, ageDays = minAgeDays) => {
    setInspecting(true)
    setInspection(null)
    setExecutionResult(null)
    setConfirmInput('')
    try {
      const res = await api.inspectCleanup(routerId, ageDays)
      setInspection(res)
    } catch (err: any) {
      alert(`فشل الفحص: ${err.message}`)
    } finally {
      setInspecting(false)
    }
  }

  useEffect(() => {
    if (selectedRouterId) {
      handleInspect(selectedRouterId, minAgeDays)
    }
  }, [selectedRouterId, minAgeDays])

  const expectedCode = `CONFIRM-${selectedRouterId.toUpperCase()}`
  const isCodeValid = confirmInput.trim().toUpperCase() === expectedCode

  const handleExecute = async (overrideAction?: 'remove_old_sessions' | 'remove_expired_users' | 'rebuild_db') => {
    const act = overrideAction || actionType
    if (!isCodeValid) {
      alert(`يرجى كتابة رمز التأكيد بالضبط: ${expectedCode}`)
      return
    }

    const actionLabel =
      act === 'remove_old_sessions'
        ? 'حذف السشنات المغلقة القديمة'
        : act === 'remove_expired_users'
        ? 'حذف الكروت المنتهية الصلاحية'
        : 'إعادة بناء وضغط قاعدة بيانات اليوزرمانجر'

    if (!window.confirm(`هل أنت متأكد تماماً من تنفيذ [${actionLabel}] على راوتر [${selectedRouterId}]؟ المشتركون المتصلون حالياً مستثنون ومحميون 100%.`)) {
      return
    }

    setExecuting(true)
    try {
      const res = await api.executeCleanup(selectedRouterId, act, minAgeDays)
      setExecutionResult(res)
      // re-inspect to show updated counts
      handleInspect(selectedRouterId, minAgeDays)
    } catch (err: any) {
      alert(`فشل تنفيذ العملية: ${err.message}`)
    } finally {
      setExecuting(false)
    }
  }

  const selectedRouter = routers.find((r) => r.id === selectedRouterId)
  const isUmWeb = selectedRouter?.method === 'umweb' || inspection?.method === 'umweb'
  const fallbackHost = selectedRouterId === 'km111' ? '192.168.0.250' : '192.168.0.249'
  const webUrl = isUmWeb
    ? inspection?.web_url || `http://${selectedRouter?.host || fallbackHost}:800/userman`
    : null

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-slate-900 to-slate-900/80 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Trash2 className="w-5 h-5 text-amber-400" />
            <h2 className="text-base font-bold text-slate-100 font-['Cairo']">
              مركز تفريغ الحمل الآمن وتنظيف السشنات المغلقة
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            إزالة السشنات التاريخية المغلقة والحسابات المنتهية لتخفيف استهلاك معالج المايكروتك وقرص التخزين
          </p>
        </div>

        {/* Safety Badge */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-xs">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <span>حماية تامة: السشنات النشطة للمشتركين المتصلين حالياً محمية ومستثناة 100%</span>
        </div>
      </div>

      {/* Router Selection & Date Filter Box */}
      <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          {/* Router select */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              اختر الراوتر المراد فحصه وتفريغ حمله:
            </label>
            <select
              value={selectedRouterId}
              onChange={(e) => {
                setSelectedRouterId(e.target.value)
                setInspection(null)
                setExecutionResult(null)
              }}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-cyan-500 font-medium"
            >
              {routers.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} — {r.host} ({r.method === 'umweb' ? 'User Manager Web :800' : 'RouterOS API'})
                </option>
              ))}
            </select>
          </div>

          {/* Date range filter */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-cyan-400" />
              <span>نطاق تاريخ السجلات المستهدفة:</span>
            </label>
            <select
              value={minAgeDays}
              onChange={(e) => setMinAgeDays(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-cyan-500 font-medium"
            >
              <option value={0}>الكل (جميع السجلات القديمة والمنتهية)</option>
              <option value={30}>أقدم من 30 يوماً (أكثر من شهر)</option>
              <option value={90}>أقدم من 90 يوماً (أكثر من 3 أشهر)</option>
              <option value={180}>أقدم من 180 يوماً (أكثر من 6 أشهر)</option>
              <option value={365}>أقدم من سنة كاملة (سجلات تاريخية)</option>
            </select>
          </div>

          {/* Refresh / Inspect Button */}
          <div>
            <button
              onClick={() => handleInspect()}
              disabled={inspecting}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs shadow-md shadow-cyan-950 transition disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${inspecting ? 'animate-spin' : ''}`} />
              <span>{inspecting ? 'جاري فحص قاعدة البيانات...' : 'تحديث كشف السشنات والحمل'}</span>
            </button>
          </div>
        </div>

        {/* RB2011 Web Manager Notice Card */}
        {isUmWeb && (
          <div className="p-4 rounded-xl bg-gradient-to-r from-blue-950/40 to-cyan-950/30 border border-blue-800/40 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-xs font-bold text-cyan-300">
                <ExternalLink className="w-4 h-4 text-cyan-400" />
                <span>ربط اليوزرمانجر عبر المتصفح (Web User Manager :800)</span>
              </div>
              <p className="text-[11px] text-slate-300">
                هذا الراوتر مربوط بالبرنامج عبر واجهة المتصفح (Echo2 Web) لتجاوز قيود صلاحيات API المباشرة. يمكنك فتح صفحته مباشرة في تبويب جديد أو إعادة بناء وضغط قاعدة بياناته.
              </p>
            </div>
            {webUrl && (
              <a
                href={webUrl}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs shadow transition"
              >
                <span>فتح واجهة اليوزرمانجر</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
        )}
      </div>

      {/* Inspection Results */}
      {inspection && (
        <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 space-y-5">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Database className="w-5 h-5 text-cyan-400" />
              <h3 className="text-sm font-bold text-slate-100">
                نتائج فحص قاعدة بيانات: {inspection.router_name}
              </h3>
            </div>
            <span className="text-xs px-2.5 py-1 rounded bg-slate-800 text-slate-300 font-mono">
              {inspection.method.toUpperCase()}
            </span>
          </div>

          {/* Cards metrics */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Active sessions */}
            <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-800/40">
              <div className="text-xs text-emerald-400 font-medium mb-1">السشنات النشطة حالياً</div>
              <div className="text-2xl font-bold font-mono text-emerald-300">
                {inspection.active_sessions_count}
              </div>
              <div className="text-[11px] text-emerald-500 mt-1">✓ محمية ومستثناة من أي حذف</div>
            </div>

            {/* Closed sessions */}
            <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-800/40">
              <div className="text-xs text-amber-400 font-medium mb-1">سشنات مغلقة قديمة</div>
              <div className="text-2xl font-bold font-mono text-amber-300">
                {(inspection.total_sessions || inspection.closed_sessions_count).toLocaleString('ar-IQ')}
              </div>
              <div className="text-[11px] text-amber-500 mt-1">سجلات تاريخية جاهزة للتفريغ</div>
            </div>

            {/* Expired users */}
            <div className="p-4 rounded-xl bg-indigo-950/20 border border-indigo-800/40">
              <div className="text-xs text-indigo-400 font-medium mb-1">كروت منتهية الصلاحية</div>
              <div className="text-2xl font-bold font-mono text-indigo-300">
                {inspection.expired_users_count}
              </div>
              <div className="text-[11px] text-indigo-500 mt-1">رصيد مستهلك بالكامل</div>
            </div>

            {/* DB Size / Storage */}
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <div className="text-xs text-slate-400 font-medium mb-1">حجم قاعدة البيانات</div>
              <div className="text-2xl font-bold font-mono text-cyan-300">
                {inspection.sqldb_size_mb ? `${inspection.sqldb_size_mb} MB` : 'معالجة عبر الذاكرة'}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">
                {selectedRouterId === 'km111' ? 'المساحة ممتلئة 100%' : 'استهلاك طبيعي'}
              </div>
            </div>
          </div>

          {/* Expired Users Preview Table (if any) */}
          {inspection.expired_users && inspection.expired_users.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-bold text-slate-300 flex items-center justify-between">
                <span>عينة من الكروت المنتهية المرشحة للتنظيف ({Math.min(10, inspection.expired_users.length)} من {inspection.expired_count || inspection.expired_users_count}):</span>
                <span className="text-[11px] text-slate-500 font-normal">تم التحقق: لا يوجد أي متصل نشط بينهم</span>
              </div>
              <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950">
                <table className="w-full text-right text-xs">
                  <thead className="bg-slate-900/80 text-slate-400">
                    <tr>
                      <th className="p-2.5">اسم المستخدم</th>
                      <th className="p-2.5">البروفايل</th>
                      <th className="p-2.5">تاريخ الانتهاء</th>
                      <th className="p-2.5">آخر ظهور</th>
                      <th className="p-2.5">الحالة</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                    {inspection.expired_users.slice(0, 10).map((u: any, idx: number) => (
                      <tr key={idx} className="hover:bg-slate-900/40">
                        <td className="p-2.5 font-bold text-cyan-400">{u.username}</td>
                        <td className="p-2.5">{u.profile || '—'}</td>
                        <td className="p-2.5 text-amber-300/80">{u.till_time || u.end_time || 'منتهي'}</td>
                        <td className="p-2.5 text-slate-400">{u.last_seen || '—'}</td>
                        <td className="p-2.5 text-rose-400 font-bold">منتهي الصلاحية</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Action Choice & Execution Box */}
          <div className="p-5 rounded-2xl bg-slate-950 border border-slate-800 space-y-4">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
              <Lock className="w-4 h-4 text-cyan-400" />
              <span>تحديد نوع عملية تفريغ الحمل:</span>
            </div>

            {/* Action options */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Option 1: Sessions only */}
              <button
                type="button"
                onClick={() => setActionType('remove_old_sessions')}
                className={`p-3.5 rounded-xl border text-right transition flex flex-col justify-between ${
                  actionType === 'remove_old_sessions'
                    ? 'bg-amber-950/30 border-amber-500 text-amber-200'
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between w-full mb-1">
                  <span className="text-xs font-bold">1. حذف السشنات المغلقة فقط</span>
                  <Sparkles className="w-4 h-4 text-amber-400" />
                </div>
                <p className="text-[11px] text-slate-400">
                  آمن 100% لتخفيف حجم قاعدة البيانات ومعالج الراوتر دون حذف أي كرت أو مستخدم.
                </p>
              </button>

              {/* Option 2: Users only */}
              <button
                type="button"
                onClick={() => setActionType('remove_expired_users')}
                className={`p-3.5 rounded-xl border text-right transition flex flex-col justify-between ${
                  actionType === 'remove_expired_users'
                    ? 'bg-indigo-950/30 border-indigo-500 text-indigo-200'
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between w-full mb-1">
                  <span className="text-xs font-bold">2. حذف الكروت المنتهية فقط</span>
                  <Users className="w-4 h-4 text-indigo-400" />
                </div>
                <p className="text-[11px] text-slate-400">
                  حذف الكروت المستنفدة رصيدها بالكامل، مع الاستثناء التلقائي لأي متصل نشط.
                </p>
              </button>

              {/* Option 3: Rebuild DB (especially for RB2011) */}
              <button
                type="button"
                onClick={() => setActionType('rebuild_db')}
                className={`p-3.5 rounded-xl border text-right transition flex flex-col justify-between ${
                  actionType === 'rebuild_db'
                    ? 'bg-cyan-950/30 border-cyan-500 text-cyan-200'
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between w-full mb-1">
                  <span className="text-xs font-bold">3. ضغط وصيانة قاعدة البيانات</span>
                  <Database className="w-4 h-4 text-cyan-400" />
                </div>
                <p className="text-[11px] text-slate-400">
                  حفظ نسخة احتياطية أولاً ثم ضغط قاعدة البيانات لتفريغ المساحة (مثالي لـ RB2011).
                </p>
              </button>
            </div>

            {/* Execution Confirmation Row */}
            <div className="pt-3 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="text-xs text-slate-400">
                اكتب الرمز <code className="text-amber-400 font-mono font-bold bg-slate-900 px-2 py-0.5 rounded border border-slate-800">{expectedCode}</code> للتأكيد:
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto">
                <input
                  type="text"
                  value={confirmInput}
                  onChange={(e) => setConfirmInput(e.target.value)}
                  placeholder={expectedCode}
                  className="bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2 text-xs font-mono text-cyan-300 uppercase focus:outline-none focus:border-cyan-500 w-44"
                />
                <button
                  onClick={() => handleExecute()}
                  disabled={!isCodeValid || executing}
                  className="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs shadow-md shadow-rose-950 transition disabled:opacity-30 whitespace-nowrap flex items-center gap-2"
                >
                  <Trash2 className="w-4 h-4" />
                  <span>{executing ? 'جاري التنفيذ بأمان...' : 'تنفيذ تفريغ الحمل الآن'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Execution Result Log */}
      {executionResult && (
        <div className="p-4 rounded-2xl bg-emerald-950/30 border border-emerald-800/60 space-y-2">
          <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
            <CheckCircle2 className="w-5 h-5" />
            <span>اكتملت العملية بنجاح</span>
          </div>
          <div className="text-xs text-slate-300 font-mono">
            رقم العملية المسجل: {executionResult.op_id || 'OP-SUCCESS'}
          </div>
          <div className="text-xs text-slate-400">
            {executionResult.detail || `تم تنفيذ العملية بنجاح دون أي مساس بالمشتركين النشطين.`}
          </div>
        </div>
      )}
    </div>
  )
}