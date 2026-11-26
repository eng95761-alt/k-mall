import React from 'react'
import {
  Activity,
  Layers,
  Ticket,
  Trash2,
  Users,
  ShieldCheck,
  RefreshCw,
  LogOut,
  Radio,
} from 'lucide-react'
import { User } from '../types'

interface HeaderProps {
  user: User | null
  activeTab: string
  setActiveTab: (tab: string) => void
  onRefresh: () => void
  onLogout: () => void
  refreshCountdown: number
  isRefreshing: boolean
  allowWrites: boolean
}

export const Header: React.FC<HeaderProps> = ({
  user,
  activeTab,
  setActiveTab,
  onRefresh,
  onLogout,
  refreshCountdown,
  isRefreshing,
  allowWrites,
}) => {
  const tabs = [
    { id: 'monitoring', label: 'لوحة المراقبة الحية', icon: Activity },
    { id: 'network', label: 'الشبكة والفيلانات', icon: Layers },
    { id: 'vouchers', label: 'User Manager والكروت', icon: Ticket },
    { id: 'cleanup', label: 'تفريغ الحمل والصيانة', icon: Trash2 },
    { id: 'commercial', label: 'الاشتراكات والمبيعات', icon: Users },
    { id: 'security', label: 'الأمان وسجل التدقيق', icon: ShieldCheck },
  ]

  return (
    <header className="bg-slate-900/90 border-b border-slate-800 sticky top-0 z-40 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo & Name */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-emerald-500 flex items-center justify-center shadow-lg shadow-cyan-900/30">
              <Radio className="w-6 h-6 text-white animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold text-slate-100 tracking-wide font-['Cairo']">
                  منصة شبكة مجمع كربلاء التجاري
                </h1>
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-800 text-cyan-400">
                  Enterprise
                </span>
                {allowWrites ? (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-950 border border-amber-800 text-amber-300">
                    تعديل مقيّد
                  </span>
                ) : (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-400">
                    قراءة فقط (آمن)
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">
                مراقبة حية، إدارة الكروت، وتفريغ آمن لحمل المايكروتك
              </p>
            </div>
          </div>

          {/* User Profile & Actions */}
          <div className="flex items-center gap-3">
            {/* Auto refresh counter & manual button */}
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              title="تحديث البيانات فوراً"
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-xs transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-cyan-400' : ''}`} />
              <span className="hidden md:inline font-mono">
                {isRefreshing ? 'جاري التحديث...' : `تحديث (${refreshCountdown} ث)`}
              </span>
            </button>

            {/* User Info */}
            {user && (
              <div className="flex items-center gap-2 pl-2 border-r border-slate-800">
                <div className="text-left hidden lg:block">
                  <div className="text-xs font-semibold text-slate-200">{user.username}</div>
                  <div className="text-[10px] text-slate-400 uppercase font-mono">{user.role}</div>
                </div>
                <button
                  onClick={onLogout}
                  title="تسجيل الخروج"
                  className="p-2 rounded-lg bg-red-950/40 hover:bg-red-900/60 text-red-400 hover:text-red-200 border border-red-900/50 transition"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex space-x-1 space-x-reverse overflow-x-auto py-2 no-scrollbar border-t border-slate-800/60">
          {tabs.map((tab) => {
            const Icon = tab.icon
            const active = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                  active
                    ? 'bg-gradient-to-r from-cyan-900/80 to-slate-800 text-cyan-300 border border-cyan-700/60 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <Icon className={`w-4 h-4 ${active ? 'text-cyan-400' : 'text-slate-500'}`} />
                <span>{tab.label}</span>
              </button>
            )
          })}
        </div>
      </div>
    </header>
  )
}
