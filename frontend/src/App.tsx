import React, { useState, useEffect, useCallback } from 'react'
import { Header } from './components/Header'
import { StatsCards } from './components/StatsCards'
import { MonitoringTab } from './components/tabs/MonitoringTab'
import { NetworkTab } from './components/tabs/NetworkTab'
import { VoucherStudioTab } from './components/tabs/VoucherStudioTab'
import { CleanupMaintenanceTab } from './components/tabs/CleanupMaintenanceTab'
import { CommercialTab } from './components/tabs/CommercialTab'
import { SecurityAuditTab } from './components/tabs/SecurityAuditTab'
import { LoginModal } from './components/LoginModal'
import { SystemOverview, AlertItem } from './types'
import { api } from './api'

export const App: React.FC = () => {
  const [overview, setOverview] = useState<SystemOverview | null>(null)
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [activeTab, setActiveTab] = useState<string>('monitoring')
  const [selectedRouterId, setSelectedRouterId] = useState<string | null>(null)
  const [isLoggedIn, setIsLoggedIn] = useState<boolean>(true)
  const [refreshCountdown, setRefreshCountdown] = useState<number>(15)
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false)

  const fetchData = useCallback(async (manual = false) => {
    if (manual) setIsRefreshing(true)
    try {
      const [ovData, alData] = await Promise.all([
        api.getOverview(),
        api.getAlerts().catch(() => []),
      ])
      setOverview(ovData)
      const activeAlerts = (alData || []).filter((a: any) => !a.closed_at)
      setAlerts(activeAlerts)
      setIsLoggedIn(true)
    } catch (err: any) {
      if (
        err.message &&
        (err.message.includes('401') ||
          err.message.includes('تسجيل الدخول') ||
          err.message.includes('الجلسة') ||
          err.message.includes('Unauthorized'))
      ) {
        setIsLoggedIn(false)
      }
    } finally {
      if (manual) setIsRefreshing(false)
      setRefreshCountdown(15)
    }
  }, [])

  // Initial fetch
  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Countdown timer for automatic live refresh
  useEffect(() => {
    if (!isLoggedIn) return
    const timer = setInterval(() => {
      setRefreshCountdown((prev) => {
        if (prev <= 1) {
          fetchData()
          return 15
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [fetchData, isLoggedIn])

  const handleLogout = async () => {
    try {
      await api.logout()
    } finally {
      setIsLoggedIn(false)
      setOverview(null)
    }
  }

  const handleSelectRouter = (routerId: string) => {
    setSelectedRouterId(routerId)
    setActiveTab('network')
  }

  if (!isLoggedIn) {
    return <LoginModal onLoginSuccess={() => fetchData(true)} />
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-['Cairo']">
      <Header
        user={overview?.user ?? null}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onRefresh={() => fetchData(true)}
        onLogout={handleLogout}
        refreshCountdown={refreshCountdown}
        isRefreshing={isRefreshing}
        allowWrites={overview?.allow_router_writes ?? false}
      />

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6">
        <StatsCards overview={overview} />

        {activeTab === 'monitoring' && (
          <MonitoringTab
            routers={overview?.routers ?? []}
            alerts={alerts}
            onSelectRouter={handleSelectRouter}
            onRefresh={() => fetchData(true)}
          />
        )}

        {activeTab === 'network' && (
          <NetworkTab
            routers={overview?.routers ?? []}
            selectedRouterId={selectedRouterId}
            onSelectRouter={(id) => setSelectedRouterId(id)}
          />
        )}

        {activeTab === 'vouchers' && (
          <VoucherStudioTab
            routers={overview?.routers ?? []}
            allowWrites={overview?.allow_router_writes ?? false}
          />
        )}

        {activeTab === 'cleanup' && (
          <CleanupMaintenanceTab
            routers={overview?.routers ?? []}
            allowWrites={overview?.allow_router_writes ?? false}
          />
        )}

        {activeTab === 'commercial' && <CommercialTab />}

        {activeTab === 'security' && (
          <SecurityAuditTab allowWrites={overview?.allow_router_writes ?? false} />
        )}
      </main>
    </div>
  )
}

export default App
