import React, { useState, useEffect } from 'react'
import {
  ShieldCheck,
  Lock,
  FileText,
  UserCheck,
  Clock,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react'
import { AuditRecord, ChangeRecord } from '../../types'
import { api } from '../../api'

export const SecurityAuditTab: React.FC<{ allowWrites: boolean }> = ({ allowWrites }) => {
  const [auditLogs, setAuditLogs] = useState<AuditRecord[]>([])
  const [changeLogs, setChangeLogs] = useState<ChangeRecord[]>([])
  const [loading, setLoading] = useState(true)

  const loadLogs = async () => {
    setLoading(true)
    try {
      const [a, c] = await Promise.all([api.getAudit(50), api.getChanges(50)])
      setAuditLogs(a || [])
      setChangeLogs(c || [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLogs()
  }, [])

  return (
    <div className="space-y-6">
      {/* Security Status Banner */}
      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <h2 className="text-base font-bold text-slate-100 font-['Cairo']">
              مركز الأمان والرقابة وسجل التدقيق
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            توثيق كامل لكل عملية دخول أو تغيير في الشبكة مع خطة رجوع فورية
          </p>
        </div>

        <div className="flex items-center gap-2">
          {allowWrites ? (
            <span className="px-3 py-1.5 rounded-xl bg-amber-950/60 border border-amber-800 text-amber-300 text-xs font-semibold">
              وضع التعديل مقيّد بطلب موافقة صريح
            </span>
          ) : (
            <span className="px-3 py-1.5 rounded-xl bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-xs font-semibold">
              وضع القراءة فقط الصارم (Read-Only) مفعّل
            </span>
          )}
        </div>
      </div>

      {/* Change Logs Table (Critical Changes) */}
      <div className="rounded-2xl bg-slate-900/80 border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <RotateCcw className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-100">
              سجل التغييرات وإجراءات نقاط الرجوع (Change Management)
            </h3>
          </div>
          <button onClick={loadLogs} className="text-xs text-cyan-400 hover:underline">
            تحديث
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-right text-xs">
            <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">رقم العملية (OP-ID)</th>
                <th className="p-3">الراوتر</th>
                <th className="p-3">المشغّل</th>
                <th className="p-3">الإجراء</th>
                <th className="p-3">النتيجة</th>
                <th className="p-3">نقطة الرجوع (Rollback Hint)</th>
                <th className="p-3">الوقت</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {changeLogs.length > 0 ? (
                changeLogs.map((c) => (
                  <tr key={c.op_id} className="hover:bg-slate-800/30 transition">
                    <td className="p-3 font-mono font-bold text-cyan-300">{c.op_id}</td>
                    <td className="p-3 font-mono text-slate-300">{c.router_id}</td>
                    <td className="p-3 text-slate-200">{c.operator}</td>
                    <td className="p-3 font-medium text-slate-200">{c.action}</td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                          c.result === 'success'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : 'bg-rose-950 text-rose-400 border border-rose-800'
                        }`}
                      >
                        {c.result}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-[11px] text-slate-400 max-w-xs truncate">
                      {c.rollback_hint || '—'}
                    </td>
                    <td className="p-3 font-mono text-[11px] text-slate-500">
                      {c.ts ? new Date(c.ts).toLocaleString('ar-IQ') : '—'}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-slate-500">
                    لم يُسجل أي تغيير حتى الآن. المنصة في وضع المراقبة الآمن.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="rounded-2xl bg-slate-900/80 border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-bold text-slate-100">سجل تدقيق الوصول والعمليات (Audit Log)</h3>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-right text-xs">
            <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">الوقت</th>
                <th className="p-3">المستخدم</th>
                <th className="p-3">الإجراء</th>
                <th className="p-3">التفاصيل</th>
                <th className="p-3">عنوان IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {auditLogs.length > 0 ? (
                auditLogs.map((a, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/30 transition">
                    <td className="p-3 font-mono text-[11px] text-slate-400">
                      {a.ts ? new Date(a.ts).toLocaleString('ar-IQ') : '—'}
                    </td>
                    <td className="p-3 font-semibold text-slate-200">{a.username || 'System'}</td>
                    <td className="p-3 font-mono text-cyan-300">{a.action}</td>
                    <td className="p-3 text-slate-300 max-w-sm truncate">{a.detail || '—'}</td>
                    <td className="p-3 font-mono text-slate-500">{a.ip || '—'}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-slate-500">
                    لا توجد سجلات تدقيق متاحة.
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
