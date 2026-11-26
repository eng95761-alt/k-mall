import React from 'react'
import { Server, Users, Radio, AlertCircle, DollarSign, Database } from 'lucide-react'
import { SystemOverview } from '../types'

interface StatsCardsProps {
  overview: SystemOverview | null
}

export const StatsCards: React.FC<StatsCardsProps> = ({ overview }) => {
  if (!overview) return null

  const items = [
    {
      title: 'الراوترات المتصلة',
      value: `${overview.online_routers ?? 0} / ${overview.total_routers ?? 0}`,
      subtitle: (overview.online_routers ?? 0) === (overview.total_routers ?? 0) ? 'جميع الراوترات تعمل' : 'تنبيه: راوتر غير متصل',
      icon: Server,
      color: (overview.online_routers ?? 0) === (overview.total_routers ?? 0) ? 'emerald' : 'amber',
    },
    {
      title: 'زبائن الهوتسبوت النشطون',
      value: (overview.active_clients ?? 0).toLocaleString('ar-IQ'),
      subtitle: 'اضغط لعرض تفاصيل المشتركين ↓',
      icon: Radio,
      color: 'cyan',
      clickable: true,
    },
    {
      title: 'حسابات User Manager',
      value: (overview.total_um_users ?? 0).toLocaleString('ar-IQ'),
      subtitle: `${(overview.total_um_sessions ?? 0).toLocaleString('ar-IQ')} سشن مسجل`,
      icon: Users,
      color: 'indigo',
    },
    {
      title: 'مبيعات اليوم',
      value: `${(overview.today_sales_iqd ?? 0).toLocaleString('ar-IQ')} د.ع`,
      subtitle: `الديون المستحقة: ${(overview.total_debt_iqd ?? 0).toLocaleString('ar-IQ')} د.ع`,
      icon: DollarSign,
      color: 'emerald',
    },
    {
      title: 'التنبيهات المفتوحة',
      value: (overview.open_alerts ?? 0).toString(),
      subtitle: (overview.open_alerts ?? 0) === 0 ? 'الشبكة مستقرة وآمنة' : 'يرجى مراجعة التنبيهات',
      icon: AlertCircle,
      color: (overview.open_alerts ?? 0) === 0 ? 'slate' : 'rose',
    },
  ]

  const getColorClasses = (color: string) => {
    switch (color) {
      case 'emerald':
        return {
          bg: 'bg-emerald-950/20 border-emerald-800/40',
          text: 'text-emerald-400',
          sub: 'text-emerald-500/80',
          iconBg: 'bg-emerald-900/30 text-emerald-400',
        }
      case 'cyan':
        return {
          bg: 'bg-cyan-950/20 border-cyan-800/40',
          text: 'text-cyan-400',
          sub: 'text-cyan-500/80',
          iconBg: 'bg-cyan-900/30 text-cyan-400',
        }
      case 'indigo':
        return {
          bg: 'bg-indigo-950/20 border-indigo-800/40',
          text: 'text-indigo-400',
          sub: 'text-indigo-500/80',
          iconBg: 'bg-indigo-900/30 text-indigo-400',
        }
      case 'amber':
        return {
          bg: 'bg-amber-950/20 border-amber-800/40',
          text: 'text-amber-400',
          sub: 'text-amber-500/80',
          iconBg: 'bg-amber-900/30 text-amber-400',
        }
      case 'rose':
        return {
          bg: 'bg-rose-950/20 border-rose-800/40',
          text: 'text-rose-400',
          sub: 'text-rose-500/80',
          iconBg: 'bg-rose-900/30 text-rose-400',
        }
      default:
        return {
          bg: 'bg-slate-900/60 border-slate-800',
          text: 'text-slate-300',
          sub: 'text-slate-500',
          iconBg: 'bg-slate-800 text-slate-400',
        }
    }
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
      {items.map((it, idx) => {
        const c = getColorClasses(it.color)
        const Icon = it.icon
        return (
          <div
            key={idx}
            onClick={() => {
              if (it.clickable) {
                const el = document.getElementById('active-clients-section')
                if (el) el.scrollIntoView({ behavior: 'smooth' })
              }
            }}
            className={`p-4 rounded-xl border backdrop-blur-sm transition-all hover:translate-y-[-1px] ${c.bg} ${
              it.clickable ? 'cursor-pointer hover:border-cyan-600/60 ring-1 ring-cyan-500/20' : ''
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-400">{it.title}</span>
              <div className={`p-2 rounded-lg ${c.iconBg}`}>
                <Icon className="w-4 h-4" />
              </div>
            </div>
            <div className={`text-xl font-bold font-mono tracking-tight ${c.text}`}>{it.value}</div>
            <div className={`text-[11px] mt-1 ${c.sub}`}>{it.subtitle}</div>
          </div>
        )
      })}
    </div>
  )
}
