import React, { useState, useEffect } from 'react'
import {
  Ticket,
  Printer,
  Download,
  PlusCircle,
  Eye,
  CheckCircle2,
  AlertTriangle,
  QrCode,
  Sparkles,
  Layers,
  Send,
  X,
} from 'lucide-react'
import { RouterItem, UMProfile, VoucherBatch, VoucherCard } from '../../types'
import { api } from '../../api'
import QRCode from 'qrcode'

interface VoucherStudioTabProps {
  routers: RouterItem[]
  allowWrites: boolean
}

export const VoucherStudioTab: React.FC<VoucherStudioTabProps> = ({
  routers,
  allowWrites,
}) => {
  const [selectedRouterId, setSelectedRouterId] = useState<string>(routers[0]?.id ?? 'km222-l009')
  const [profiles, setProfiles] = useState<UMProfile[]>([])
  const [umVersion, setUmVersion] = useState<string>('')
  const [loadingProfiles, setLoadingProfiles] = useState(false)

  // Batches state
  const [batches, setBatches] = useState<VoucherBatch[]>([])
  const [loadingBatches, setLoadingBatches] = useState(false)

  // Form state
  const [selectedProfile, setSelectedProfile] = useState<string>('')
  const [cardCount, setCardCount] = useState<number>(20)
  const [prefix, setPrefix] = useState<string>('KM')
  const [priceIqd, setPriceIqd] = useState<number>(5000)
  const [digitsOnly, setDigitsOnly] = useState<boolean>(true)
  const [userLen, setUserLen] = useState<number>(6)
  const [passLen, setPassLen] = useState<number>(6)
  const [generating, setGenerating] = useState(false)

  // Modal state for viewing cards & printing
  const [viewBatch, setViewBatch] = useState<VoucherBatch | null>(null)
  const [viewCards, setViewCards] = useState<VoucherCard[]>([])
  const [qrCodes, setQrCodes] = useState<Record<number, string>>({})
  const [showPrintModal, setShowPrintModal] = useState(false)

  // Load profiles when router changes
  useEffect(() => {
    if (!selectedRouterId) return
    setLoadingProfiles(true)
    api
      .getProfiles(selectedRouterId)
      .then((data) => {
        setProfiles(data.profiles || [])
        setUmVersion(data.um_version || '')
        if (data.profiles && data.profiles.length > 0) {
          setSelectedProfile(data.profiles[0].name)
          if (data.profiles[0].price) {
            setPriceIqd(data.profiles[0].price)
          }
        } else {
          setSelectedProfile('')
        }
      })
      .catch((err) => {
        console.error('Failed to load profiles:', err)
        setProfiles([])
      })
      .finally(() => {
        setLoadingProfiles(false)
      })
  }, [selectedRouterId])

  // Load batches list
  const loadBatches = () => {
    setLoadingBatches(true)
    api
      .getBatches()
      .then((data) => {
        setBatches(data.batches || [])
      })
      .catch((err) => console.error('Failed to load batches:', err))
      .finally(() => setLoadingBatches(false))
  }

  useEffect(() => {
    loadBatches()
  }, [])

  // Generate batch
  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedProfile) {
      alert('يرجى اختيار بروفايل من القائمة')
      return
    }
    setGenerating(true)
    try {
      const res = await api.generateBatch({
        router_id: selectedRouterId,
        profile_name: selectedProfile,
        count: cardCount,
        prefix,
        user_len: userLen,
        pass_len: passLen,
        digits_only: digitsOnly,
        price_iqd: priceIqd,
        notes: `دفعة بروفايل ${selectedProfile} عبر منصة K-Mall`,
      })
      alert(`تم توليد ${res.count} كرت بنجاح برمز الدفعة: ${res.batch_code}`)
      loadBatches()
      handleViewCards(res.batch_id)
    } catch (err: any) {
      alert(`فشل التوليد: ${err.message}`)
    } finally {
      setGenerating(false)
    }
  }

  // View cards modal & generate QR codes
  const handleViewCards = async (batchId: number, forPrint = false) => {
    try {
      const res = await api.getBatchCards(batchId)
      setViewBatch(res.batch)
      setViewCards(res.cards || [])

      // Generate QR codes for all cards
      const qrMap: Record<number, string> = {}
      for (const card of res.cards) {
        try {
          const qrUrl = await QRCode.toDataURL(
            `http://kmall.wifi/login?username=${encodeURIComponent(card.username)}&password=${encodeURIComponent(
              card.password || ''
            )}`,
            { width: 120, margin: 1 }
          )
          qrMap[card.id] = qrUrl
        } catch {
          // ignore
        }
      }
      setQrCodes(qrMap)

      if (forPrint) {
        setShowPrintModal(true)
      } else {
        setShowPrintModal(false)
      }
    } catch (err: any) {
      alert(`فشل جلب الكروت: ${err.message}`)
    }
  }

  const triggerPrint = () => {
    window.print()
  }

  return (
    <div className="space-y-6">
      {/* Top Banner & Router Selector */}
      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Ticket className="w-5 h-5 text-cyan-400" />
            <h2 className="text-base font-bold text-slate-100 font-['Cairo']">
              استوديو توليد وطباعة كروت User Manager
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            سحب البروفايلات الحقيقية من المايكروتك، توليد كروت آمنة، وطباعة حرارية وA4 مع QR Code
          </p>
        </div>

        {/* Router Selector */}
        <div className="flex items-center gap-2">
          <label className="text-xs font-semibold text-slate-300 whitespace-nowrap">الراوتر المستهدف:</label>
          <select
            value={selectedRouterId}
            onChange={(e) => setSelectedRouterId(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-cyan-300 font-medium focus:outline-none focus:border-cyan-500"
          >
            {routers.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} ({r.vlan_id ? `VLAN ${r.vlan_id}` : r.method})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Profiles & Generator Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Real Profiles Column (1 col) */}
        <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold text-slate-200">
                بروفايلات الراوتر الحقيقية ({profiles.length})
              </h3>
            </div>
            {umVersion && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                {umVersion}
              </span>
            )}
          </div>

          {loadingProfiles ? (
            <div className="p-8 text-center text-xs text-cyan-400 animate-pulse">
              جاري فحص بروفايلات User Manager من الراوتر...
            </div>
          ) : profiles.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-500">
              لم يتم العثور على بروفايلات في هذا الراوتر أو تم تعطيل API.
            </div>
          ) : (
            <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
              {profiles.map((p, idx) => {
                const isSelected = selectedProfile === p.name
                return (
                  <div
                    key={idx}
                    onClick={() => {
                      setSelectedProfile(p.name)
                      if (p.price) setPriceIqd(p.price)
                    }}
                    className={`p-3 rounded-xl border cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-cyan-950/40 border-cyan-600 shadow-sm'
                        : 'bg-slate-950/40 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span dir="ltr" className="inline-block text-xs font-bold font-mono text-slate-100">{p.name}</span>
                      <span className="text-xs font-bold font-mono text-emerald-400">
                        {p.price ? `${p.price.toLocaleString('ar-IQ')} د.ع` : 'مجاني'}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-slate-400 font-mono">
                      {p.validity && <span>المدة: {p.validity}</span>}
                      {p.rate_limit && <span>السرعة: {p.rate_limit}</span>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Voucher Batch Generator Form (2 cols) */}
        <div className="lg:col-span-2 rounded-2xl bg-slate-900/80 border border-slate-800 p-5">
          <div className="flex items-center gap-2 pb-3 mb-4 border-b border-slate-800">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-100">
              توليد دفعة كروت جديدة
            </h3>
          </div>

          <form onSubmit={handleGenerate} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  البروفايل المختار:
                </label>
                <input
                  type="text"
                  readOnly
                  value={selectedProfile || 'يرجى اختيار بروفايل من القائمة'}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs font-mono text-cyan-300 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  عدد الكروت المطلوبة:
                </label>
                <select
                  value={cardCount}
                  onChange={(e) => setCardCount(parseInt(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                >
                  <option value={10}>10 كروت</option>
                  <option value={20}>20 كرت</option>
                  <option value={50}>50 كرت</option>
                  <option value={100}>100 كرت</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  بادئة الكود (Prefix):
                </label>
                <input
                  type="text"
                  maxLength={8}
                  value={prefix}
                  onChange={(e) => setPrefix(e.target.value.toUpperCase())}
                  placeholder="KM"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs font-mono text-slate-200 uppercase focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  سعر البيع المقترح (د.ع):
                </label>
                <input
                  type="number"
                  step={500}
                  value={priceIqd}
                  onChange={(e) => setPriceIqd(parseInt(e.target.value) || 0)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs font-mono text-emerald-400 focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            {/* Checkbox settings */}
            <div className="flex flex-wrap items-center gap-6 pt-2">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={digitsOnly}
                  onChange={(e) => setDigitsOnly(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-950 text-cyan-500 focus:ring-0"
                />
                <span>أرقام فقط (أسهل للإدخال في الهواتف)</span>
              </label>

              <div className="flex items-center gap-3 text-xs text-slate-400">
                <span>طول اسم المستخدم:</span>
                <select
                  value={userLen}
                  onChange={(e) => setUserLen(parseInt(e.target.value))}
                  className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-slate-200"
                >
                  <option value={5}>5 خانات</option>
                  <option value={6}>6 خانات</option>
                  <option value={8}>8 خانات</option>
                </select>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                type="submit"
                disabled={generating || !selectedProfile}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-emerald-600 hover:from-cyan-500 hover:to-emerald-500 text-white font-semibold text-xs shadow-lg shadow-cyan-900/30 transition disabled:opacity-50"
              >
                <PlusCircle className="w-4 h-4" />
                <span>{generating ? 'جاري التوليد...' : 'توليد الدفعة محلياً'}</span>
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Batches History Table */}
      <div className="rounded-2xl bg-slate-900/80 border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Ticket className="w-5 h-5 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-100">سجل دفعات الكروت السابقة</h3>
          </div>
          <button
            onClick={loadBatches}
            className="text-xs text-cyan-400 hover:underline"
          >
            تحديث القائمة
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-right text-xs">
            <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">رمز الدفعة</th>
                <th className="p-3">الراوتر</th>
                <th className="p-3">البروفايل</th>
                <th className="p-3">العدد</th>
                <th className="p-3">سعر الكرت</th>
                <th className="p-3">الحالة</th>
                <th className="p-3">تاريخ الإنشاء</th>
                <th className="p-3 text-center">الإجراءات والطباعة</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {batches.length > 0 ? (
                batches.map((b) => (
                  <tr key={b.id} className="hover:bg-slate-800/30 transition">
                    <td className="p-3 font-mono font-bold text-cyan-300">{b.batch_code}</td>
                    <td className="p-3 font-mono text-slate-400">{b.router_id}</td>
                    <td className="p-3 font-semibold text-slate-200">{b.profile_name}</td>
                    <td className="p-3 font-mono text-slate-300">{b.count} كرت</td>
                    <td className="p-3 font-mono text-emerald-400">
                      {b.price_iqd ? `${b.price_iqd.toLocaleString('ar-IQ')} د.ع` : '—'}
                    </td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                          b.status === 'pushed'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {b.status === 'pushed' ? 'تم الرفع للراوتر' : 'مسودة محلية'}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-[11px] text-slate-500">
                      {b.created_at ? new Date(b.created_at).toLocaleString('ar-IQ') : '—'}
                    </td>
                    <td className="p-3">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          onClick={() => handleViewCards(b.id, false)}
                          className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 text-[11px] flex items-center gap-1 transition"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>عرض</span>
                        </button>

                        <button
                          onClick={() => handleViewCards(b.id, true)}
                          className="px-2.5 py-1 rounded-lg bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-800 text-emerald-300 text-[11px] flex items-center gap-1 transition"
                        >
                          <Printer className="w-3.5 h-3.5" />
                          <span>طباعة كروت وQR</span>
                        </button>

                        <a
                          href={`/api/export/vouchers/${b.id}.csv`}
                          download
                          className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] flex items-center gap-1 transition"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>CSV</span>
                        </a>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8} className="p-8 text-center text-slate-500">
                    لم يتم توليد أي دفعات كروت حتى الآن. يمكنك توليد أول دفعة من النموذج أعلاه.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cards View Modal */}
      {viewBatch && !showPrintModal && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-4xl w-full max-h-[85vh] flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-100">
                  كروت الدفعة: {viewBatch.batch_code} ({viewCards.length} كرت)
                </h3>
                <span className="text-xs text-slate-400">
                  بروفايل: {viewBatch.profile_name} • راوتر: {viewBatch.router_id}
                </span>
              </div>
              <button
                onClick={() => setViewBatch(null)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {viewCards.map((c) => (
                <div
                  key={c.id}
                  className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between"
                >
                  <div>
                    <div className="text-xs text-slate-400">اسم المستخدم:</div>
                    <div className="text-sm font-mono font-bold text-cyan-300 select-all">{c.username}</div>
                    <div className="text-xs text-slate-400 mt-1">كلمة المرور:</div>
                    <div className="text-sm font-mono font-bold text-emerald-400 select-all">
                      {c.password || '—'}
                    </div>
                  </div>
                  {qrCodes[c.id] && (
                    <img
                      src={qrCodes[c.id]}
                      alt="QR"
                      className="w-16 h-16 rounded border border-slate-800 bg-white p-0.5"
                    />
                  )}
                </div>
              ))}
            </div>

            <div className="p-4 border-t border-slate-800 flex justify-between items-center bg-slate-950/40">
              <button
                onClick={() => setShowPrintModal(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs"
              >
                <Printer className="w-4 h-4" />
                <span>معاينة الطباعة (A4 / حراري)</span>
              </button>
              <button
                onClick={() => setViewBatch(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs"
              >
                إغلاق
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Printable Sheet View (Print dialog) */}
      {viewBatch && showPrintModal && (
        <div className="fixed inset-0 z-50 bg-black/90 flex flex-col p-4 overflow-y-auto">
          <div className="no-print max-w-5xl mx-auto w-full p-4 mb-4 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-slate-100">
                جاهز للطباعة — {viewCards.length} كرت لدفعة {viewBatch.batch_code}
              </h3>
              <p className="text-xs text-slate-400">
                يمكنك الطباعة على طابعة ورق عادية A4 أو طابعة إيصالات حرارية
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={triggerPrint}
                className="flex items-center gap-2 px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs"
              >
                <Printer className="w-4 h-4" />
                <span>طباعة الآن (Ctrl + P)</span>
              </button>
              <button
                onClick={() => setShowPrintModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs"
              >
                رجوع
              </button>
            </div>
          </div>

          {/* Actual Printable Grid */}
          <div className="max-w-5xl mx-auto w-full grid grid-cols-2 md:grid-cols-3 gap-4 p-4 bg-white text-black rounded-xl shadow-2xl printable-voucher-grid">
            {viewCards.map((c) => (
              <div
                key={c.id}
                className="border-2 border-dashed border-slate-400 p-3 rounded-lg flex flex-col justify-between printable-card"
              >
                <div className="flex items-center justify-between border-b pb-1.5 mb-2 border-slate-300">
                  <span className="text-xs font-bold text-slate-800">مجمع كربلاء التجاري</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 border text-slate-700">
                    {c.profile_name}
                  </span>
                </div>

                <div className="flex items-center justify-between gap-2">
                  <div className="space-y-1">
                    <div className="text-[11px] text-slate-600 font-mono">
                      اليوزر: <strong className="text-xs text-black font-mono">{c.username}</strong>
                    </div>
                    <div className="text-[11px] text-slate-600 font-mono">
                      الباسورد: <strong className="text-xs text-black font-mono">{c.password}</strong>
                    </div>
                    {c.price_iqd > 0 && (
                      <div className="text-[11px] font-bold text-emerald-800 font-mono">
                        السعر: {c.price_iqd.toLocaleString('ar-IQ')} د.ع
                      </div>
                    )}
                  </div>

                  {qrCodes[c.id] && (
                    <img
                      src={qrCodes[c.id]}
                      alt="QR"
                      className="w-16 h-16 shrink-0 border border-slate-300 p-0.5 rounded"
                    />
                  )}
                </div>

                <div className="text-[9px] text-slate-500 text-center mt-2 border-t pt-1 border-slate-200">
                  امسح الرمز أو ادخل عبر: kmall.wifi
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
