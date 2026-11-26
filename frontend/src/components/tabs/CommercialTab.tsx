import React, { useState, useEffect } from 'react'
import {
  Users,
  CreditCard,
  PlusCircle,
  DollarSign,
  AlertCircle,
  Building,
  Phone,
  Calendar,
  CheckCircle2,
  X,
} from 'lucide-react'
import { PlanItem, CustomerItem, SubscriptionItem } from '../../types'
import { api } from '../../api'

export const CommercialTab: React.FC = () => {
  const [plans, setPlans] = useState<PlanItem[]>([])
  const [customers, setCustomers] = useState<CustomerItem[]>([])
  const [subscriptions, setSubscriptions] = useState<SubscriptionItem[]>([])
  const [loading, setLoading] = useState(true)

  // Payment modal state
  const [selectedSub, setSelectedSub] = useState<SubscriptionItem | null>(null)
  const [payAmount, setPayAmount] = useState<number>(0)
  const [payNote, setPayNote] = useState<string>('دفعة نقدية')

  // New customer / new sub modals
  const [showNewCust, setShowNewCust] = useState(false)
  const [custName, setCustName] = useState('')
  const [custPhone, setCustPhone] = useState('')
  const [custUnit, setCustUnit] = useState('')

  const loadAll = async () => {
    setLoading(true)
    try {
      const [p, c, s] = await Promise.all([
        api.getPlans(),
        api.getCustomers(),
        api.getSubscriptions(),
      ])
      setPlans(p || [])
      setCustomers(c || [])
      setSubscriptions(s || [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  const handleCreateCustomer = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!custName.trim()) return
    try {
      await api.createCustomer({
        full_name: custName,
        phone: custPhone,
        shop_unit: custUnit,
        notes: '',
      })
      setShowNewCust(false)
      setCustName('')
      setCustPhone('')
      setCustUnit('')
      loadAll()
    } catch (err: any) {
      alert(`خطأ: ${err.message}`)
    }
  }

  const handleAddPayment = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedSub || payAmount <= 0) return
    try {
      await api.addPayment(selectedSub.id, {
        amount_iqd: payAmount,
        method: 'cash',
        note: payNote,
      })
      setSelectedSub(null)
      loadAll()
    } catch (err: any) {
      alert(`خطأ: ${err.message}`)
    }
  }

  return (
    <div className="space-y-6">
      {/* Commercial Header */}
      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-emerald-400" />
            <h2 className="text-base font-bold text-slate-100 font-['Cairo']">
              إدارة المشتركين التجاريين والمبيعات
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            متابعة محلات مجمع كربلاء، تجديد الباقات، تسجيل المقبوضات النقدية، والديون
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowNewCust(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow transition"
          >
            <PlusCircle className="w-4 h-4" />
            <span>إضافة زبون / محل جديد</span>
          </button>
        </div>
      </div>

      {/* Subscriptions Table */}
      <div className="rounded-2xl bg-slate-900/80 border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <CreditCard className="w-4 h-4 text-cyan-400" />
            <span>قائمة الاشتراكات الحالية ({subscriptions.length})</span>
          </h3>
          <button onClick={loadAll} className="text-xs text-cyan-400 hover:underline">
            تحديث
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-right text-xs">
            <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">اسم المشترك / المحل</th>
                <th className="p-3">الباقة</th>
                <th className="p-3">تاريخ التفعيل</th>
                <th className="p-3">تاريخ الانتهاء</th>
                <th className="p-3">المبلغ الإجمالي</th>
                <th className="p-3">الواصل</th>
                <th className="p-3">المتبقي (دين)</th>
                <th className="p-3">الحالة</th>
                <th className="p-3 text-center">إجراءات</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {subscriptions.length > 0 ? (
                subscriptions.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-800/30 transition">
                    <td className="p-3 font-semibold text-slate-100">{s.customer_name}</td>
                    <td className="p-3 font-mono text-cyan-300">{s.plan_name}</td>
                    <td className="p-3 font-mono text-slate-400">
                      {s.activated_at ? new Date(s.activated_at).toLocaleDateString('ar-IQ') : '—'}
                    </td>
                    <td className="p-3 font-mono text-slate-300">
                      {s.expires_at ? new Date(s.expires_at).toLocaleDateString('ar-IQ') : '—'}
                    </td>
                    <td className="p-3 font-mono text-slate-200">
                      {s.price_iqd.toLocaleString('ar-IQ')} د.ع
                    </td>
                    <td className="p-3 font-mono text-emerald-400">
                      {s.paid_iqd.toLocaleString('ar-IQ')} د.ع
                    </td>
                    <td className="p-3 font-mono font-bold text-rose-400">
                      {s.balance_iqd > 0 ? `${s.balance_iqd.toLocaleString('ar-IQ')} د.ع` : 'خالص'}
                    </td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                          s.status === 'active'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : 'bg-rose-950 text-rose-400'
                        }`}
                      >
                        {s.status === 'active' ? 'نشط' : 'منتهي'}
                      </span>
                    </td>
                    <td className="p-3 text-center">
                      <button
                        onClick={() => {
                          setSelectedSub(s)
                          setPayAmount(s.balance_iqd || 5000)
                        }}
                        className="px-2.5 py-1 rounded-lg bg-emerald-950 hover:bg-emerald-900 border border-emerald-800 text-emerald-300 text-[11px] transition"
                      >
                        تسجيل دفعة
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={9} className="p-8 text-center text-slate-500">
                    لا توجد اشتراكات مسجلة حالياً.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Payment Modal */}
      {selectedSub && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-5 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-slate-100">
                تسجيل دفعة نقدية — {selectedSub.customer_name}
              </h3>
              <button
                onClick={() => setSelectedSub(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleAddPayment} className="space-y-4">
              <div>
                <label className="block text-xs text-slate-300 mb-1">المبلغ المطلوب تسديده (د.ع):</label>
                <input
                  type="number"
                  step={1000}
                  value={payAmount}
                  onChange={(e) => setPayAmount(parseInt(e.target.value) || 0)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm font-mono text-emerald-400"
                  required
                />
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">ملاحظة الدفعة:</label>
                <input
                  type="text"
                  value={payNote}
                  onChange={(e) => setPayNote(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setSelectedSub(null)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow"
                >
                  تأكيد الدفعة
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* New Customer Modal */}
      {showNewCust && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-5 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-slate-100">إضافة زبون أو محل جديد</h3>
              <button onClick={() => setShowNewCust(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateCustomer} className="space-y-4">
              <div>
                <label className="block text-xs text-slate-300 mb-1">الاسم الكامل / اسم المحل:</label>
                <input
                  type="text"
                  value={custName}
                  onChange={(e) => setCustName(e.target.value)}
                  placeholder="مثال: كافيه البستان / محل 42"
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200"
                  required
                />
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">رقم الهاتف:</label>
                <input
                  type="text"
                  value={custPhone}
                  onChange={(e) => setCustPhone(e.target.value)}
                  placeholder="0780xxxxxxx"
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-slate-200"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">رقم الوحدة أو الطابق:</label>
                <input
                  type="text"
                  value={custUnit}
                  onChange={(e) => setCustUnit(e.target.value)}
                  placeholder="الطابق الأول - محل 12"
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowNewCust(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs shadow"
                >
                  حفظ الزبون
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
