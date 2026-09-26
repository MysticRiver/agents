'use client'

import { useEffect, useState, useCallback } from 'react'
import { format } from 'date-fns'
import { X, Download, ArrowUp, ArrowDown } from 'lucide-react'
import TopBar from '@/components/TopBar'
import { useAuth } from '@/contexts/AuthContext'
import { formatCurrency, getTradingSession, DODGYS_RULES, cn } from '@/lib/utils'

interface Stats {
  today: { pnl: number; trades: number }
  week: { pnl: number; pnlChange: number; winRate: number | null; trades: number }
  month: { pnl: number; trades: number }
  yesterday: { pnl: number; trades: number; winRate: number | null }
  streaks: { greenDays: number; journal: number; bestJournal: number; validation: number; bestValidation: number }
  rulesCompliance: { rate: number | null; followed: number; total: number; brokenRules: Record<string, number>; hasRules: boolean }
  fundedAccount: {
    firmName: string
    accountSize: number
    profitTarget: number
    maxDrawdown: number
    currentPnl: number
    daysActive: number
  } | null
  weeklyChart: { date: string; day: string; pnl: number }[]
  monthlyCalendar: { date: string; day: number; pnl: number | null; hasTrades: boolean }[]
  recentTrades: {
    id: string
    date: string
    instrument: string
    direction: string
    pnl: number | null
    grade: string | null
  }[]
  totalTrades: number
  unvalidatedCount: number
}

interface Insight {
  type: 'pattern' | 'warning' | 'strength'
  message: string
  confidence: string
}

export default function DashboardPage() {
  const { user } = useAuth()
  const [stats, setStats] = useState<Stats | null>(null)
  const [insights, setInsights] = useState<Insight[]>([])
  const [hasEnoughData, setHasEnoughData] = useState(true)
  const [tradesNeeded, setTradesNeeded] = useState(0)
  const [briefingDismissed, setBriefingDismissed] = useState(false)
  const [currentRule, setCurrentRule] = useState(0)
  const [loading, setLoading] = useState(true)

  const session = getTradingSession()

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, insightsRes, settingsRes] = await Promise.all([
        fetch('/api/stats'),
        fetch('/api/insights'),
        fetch('/api/settings')
      ])

      const statsData = await statsRes.json()
      const insightsData = await insightsRes.json()
      const settingsData = await settingsRes.json()

      setStats(statsData)
      setInsights(insightsData.insights || [])
      setHasEnoughData(insightsData.hasEnoughData ?? true)
      setTradesNeeded(insightsData.tradesNeeded || 0)

      const today = format(new Date(), 'yyyy-MM-dd')
      if (settingsData.settings?.briefingDismissedDate === today) {
        setBriefingDismissed(true)
      }
    } catch (error) {
      console.error('Failed to fetch data:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentRule((prev) => (prev + 1) % DODGYS_RULES.length)
    }, 10000)
    return () => clearInterval(interval)
  }, [])

  const dismissBriefing = async () => {
    setBriefingDismissed(true)
    const today = format(new Date(), 'yyyy-MM-dd')
    await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ briefingDismissedDate: today })
    })
  }

  const getInsightTag = (type: string) => {
    switch (type) {
      case 'strength':
        return <span className="px-2 py-0.5 bg-[#22C55E]/20 text-[#22C55E] text-xs rounded">Strength</span>
      case 'warning':
        return <span className="px-2 py-0.5 bg-orange-500/20 text-orange-500 text-xs rounded">Warning</span>
      case 'pattern':
        return <span className="px-2 py-0.5 bg-blue-500/20 text-blue-500 text-xs rounded">Pattern</span>
      default:
        return null
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-[#A0A0A0]">Loading...</div>
      </div>
    )
  }

  const maxChartValue = Math.max(...(stats?.weeklyChart.map(d => Math.abs(d.pnl)) || [1]), 1)

  return (
    <div>
      <TopBar breadcrumb={['Dashboard']} />
      
      <div className="p-4 md:p-6 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
          <div>
            <h1 className="text-white text-2xl font-semibold">
              Welcome back, {user?.name || 'Trader'}.
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[#A0A0A0] text-sm">
              {format(new Date(), 'EEEE, MMMM d, yyyy')}
            </span>
            <span className={cn(
              'px-3 py-1 rounded-full text-xs font-medium flex items-center gap-1.5',
              session.isActive ? 'bg-[#22C55E]/20 text-[#22C55E]' : 'bg-[#1A1A1A] text-[#A0A0A0]'
            )}>
              {session.isActive && <span className="w-1.5 h-1.5 bg-[#22C55E] rounded-full" />}
              {session.name}
            </span>
          </div>
        </div>

        {!briefingDismissed && (
          <div className="card relative">
            <button
              onClick={dismissBriefing}
              className="absolute top-4 right-4 text-[#A0A0A0] hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
            <h3 className="text-white font-medium mb-3">Today&apos;s Briefing</h3>
            {stats?.totalTrades === 0 ? (
              <p className="text-[#A0A0A0] text-sm">
                Welcome to Dodgy&apos;s AI Trading Tools. Start by validating your first setup.
              </p>
            ) : (
              <div className="space-y-2 text-sm">
                <p className="text-[#A0A0A0]">
                  {stats?.yesterday.trades === 0 
                    ? "No trades yesterday."
                    : `Yesterday: ${stats?.yesterday.trades} trades, ${formatCurrency(stats?.yesterday.pnl || 0)}, ${stats?.yesterday.winRate?.toFixed(0) || 0}% win rate`
                  }
                </p>
                <p className="text-[#A0A0A0]">
                  {stats?.fundedAccount 
                    ? `${stats.fundedAccount.firmName}: ${formatCurrency(stats.fundedAccount.currentPnl)} P&L`
                    : "Funded account not set up."
                  }
                </p>
                <p className="text-[#A0A0A0]">
                  Current streak: {stats?.streaks.greenDays || 0} green days
                </p>
              </div>
            )}
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="card">
            <p className="text-[#A0A0A0] text-sm mb-1">Today&apos;s P&L</p>
            <p className={cn(
              'text-2xl font-semibold',
              stats?.today.pnl === 0 ? 'text-[#A0A0A0]' :
              (stats?.today.pnl || 0) > 0 ? 'text-[#22C55E]' : 'text-[#EF4444]'
            )}>
              {formatCurrency(stats?.today.pnl || 0)}
            </p>
          </div>
          <div className="card">
            <p className="text-[#A0A0A0] text-sm mb-1">Weekly P&L</p>
            <p className={cn(
              'text-2xl font-semibold',
              stats?.week.pnl === 0 ? 'text-[#A0A0A0]' :
              (stats?.week.pnl || 0) > 0 ? 'text-[#22C55E]' : 'text-[#EF4444]'
            )}>
              {formatCurrency(stats?.week.pnl || 0)}
            </p>
            {stats?.week.pnlChange !== 0 && stats?.week.pnlChange !== undefined && (
              <p className={cn(
                'text-xs mt-1',
                stats.week.pnlChange > 0 ? 'text-[#22C55E]' : 'text-[#EF4444]'
              )}>
                {stats.week.pnlChange > 0 ? '+' : ''}{stats.week.pnlChange.toFixed(1)}% vs last week
              </p>
            )}
          </div>
          <div className="card">
            <p className="text-[#A0A0A0] text-sm mb-1">Win Rate</p>
            <p className="text-2xl font-semibold text-white">
              {stats?.week.winRate !== null && stats?.week.winRate !== undefined ? `${stats.week.winRate.toFixed(0)}%` : '- -'}
            </p>
            <p className="text-xs text-[#A0A0A0] mt-1">Current week</p>
          </div>
          <div className="card">
            <p className="text-[#A0A0A0] text-sm mb-1">Current Streak</p>
            <p className="text-2xl font-semibold text-white">
              {stats?.streaks.greenDays || 0} days
            </p>
            <p className="text-xs text-[#A0A0A0] mt-1">Consecutive green</p>
          </div>
        </div>

        <div className="card border-l-2 border-l-[#D42A2A]">
          <h3 className="text-white font-medium mb-3">Dodgy&apos;s AI Insights</h3>
          {!hasEnoughData ? (
            <p className="text-[#A0A0A0] text-sm">
              Log at least {tradesNeeded > 0 ? tradesNeeded + ' more ' : '10 '}trades to unlock AI insights. Dodgy needs data to find your patterns.
            </p>
          ) : insights.length === 0 ? (
            <p className="text-[#A0A0A0] text-sm">
              Log at least 10 trades to unlock AI insights. Dodgy needs data to find your patterns.
            </p>
          ) : (
            <div className="space-y-3">
              {insights.map((insight, i) => (
                <div key={i} className="flex items-start gap-3">
                  {getInsightTag(insight.type)}
                  <div>
                    <p className="text-white text-sm">{insight.message}</p>
                    <p className="text-[#A0A0A0] text-xs mt-1">{insight.confidence}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="grid md:grid-cols-3 gap-4">
          <div className="card">
            <h3 className="text-white font-medium mb-4">Streaks</h3>
            <div className="space-y-4">
              <div>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-[#A0A0A0] text-sm">Journal Streak</span>
                  <span className="text-white font-medium">{stats?.streaks.journal || 0} days</span>
                </div>
                <p className="text-[#A0A0A0] text-xs">Best: {stats?.streaks.bestJournal || 0} days</p>
              </div>
              <div>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-[#A0A0A0] text-sm">Validation Streak</span>
                  <span className="text-white font-medium">{stats?.streaks.validation || 0} trades</span>
                </div>
                <p className="text-[#A0A0A0] text-xs">Best: {stats?.streaks.bestValidation || 0} trades</p>
              </div>
            </div>
          </div>

          <div className="card">
            <h3 className="text-white font-medium mb-4">Rules Compliance</h3>
            {!stats?.rulesCompliance.hasRules ? (
              <p className="text-[#A0A0A0] text-sm">
                Set up your rules in Settings to start tracking.
              </p>
            ) : stats?.rulesCompliance.rate === null ? (
              <p className="text-[#A0A0A0] text-sm">
                No rule data yet. Log trades with rules followed/broken.
              </p>
            ) : (
              <div>
                <p className={cn(
                  'text-2xl font-semibold mb-2',
                  (stats.rulesCompliance.rate || 0) >= 90 ? 'text-[#22C55E]' :
                  (stats.rulesCompliance.rate || 0) >= 70 ? 'text-yellow-500' : 'text-[#EF4444]'
                )}>
                  {stats.rulesCompliance.rate?.toFixed(0)}%
                </p>
                <p className="text-[#A0A0A0] text-sm">
                  {stats.rulesCompliance.followed} of {stats.rulesCompliance.total} rules followed
                </p>
              </div>
            )}
          </div>

          <div className="card">
            <h3 className="text-white font-medium mb-4">Funded Account</h3>
            {!stats?.fundedAccount ? (
              <div>
                <p className="text-[#A0A0A0] text-sm mb-3">
                  Track drawdown and progress toward your payout target.
                </p>
                <a
                  href="/settings"
                  className="text-[#D42A2A] text-sm hover:underline"
                >
                  Set up your funded account
                </a>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-white text-sm">{stats.fundedAccount.firmName}</p>
                <p className="text-[#A0A0A0] text-xs">
                  {formatCurrency(stats.fundedAccount.accountSize)} account
                </p>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[#A0A0A0]">P&L Progress</span>
                    <span className="text-white">{formatCurrency(stats.fundedAccount.currentPnl)}</span>
                  </div>
                  <div className="h-2 bg-[#1A1A1A] rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-[#22C55E] rounded-full"
                      style={{ 
                        width: `${Math.min(100, Math.max(0, (stats.fundedAccount.currentPnl / stats.fundedAccount.profitTarget) * 100))}%` 
                      }}
                    />
                  </div>
                  <p className="text-[#A0A0A0] text-xs mt-1">
                    Target: {formatCurrency(stats.fundedAccount.profitTarget)}
                  </p>
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[#A0A0A0]">Drawdown Remaining</span>
                    <span className="text-white">
                      {formatCurrency(stats.fundedAccount.maxDrawdown + Math.min(0, stats.fundedAccount.currentPnl))}
                    </span>
                  </div>
                  <div className="h-2 bg-[#1A1A1A] rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-[#EF4444] rounded-full"
                      style={{ 
                        width: `${Math.max(0, 100 - ((stats.fundedAccount.maxDrawdown + Math.min(0, stats.fundedAccount.currentPnl)) / stats.fundedAccount.maxDrawdown) * 100)}%` 
                      }}
                    />
                  </div>
                </div>
                <p className="text-[#A0A0A0] text-xs">
                  {stats.fundedAccount.daysActive} days active
                </p>
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <h3 className="text-white font-medium mb-4">Recent Trades</h3>
          {!stats?.recentTrades.length ? (
            <p className="text-[#A0A0A0] text-sm">
              No trades logged yet. Tell AI Dodgy &apos;Log Trade&apos; in your agent chat to get started.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-[#A0A0A0] text-sm text-left">
                    <th className="pb-3 font-medium">Date</th>
                    <th className="pb-3 font-medium">Instrument</th>
                    <th className="pb-3 font-medium">Direction</th>
                    <th className="pb-3 font-medium">P&L</th>
                    <th className="pb-3 font-medium">Grade</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recentTrades.map((trade) => (
                    <tr key={trade.id} className="border-t border-[#1A1A1A]">
                      <td className="py-3 text-white text-sm">
                        {format(new Date(trade.date), 'MMM d')}
                      </td>
                      <td className="py-3 text-white text-sm">{trade.instrument}</td>
                      <td className="py-3">
                        <span className={cn(
                          'flex items-center gap-1 text-sm',
                          trade.direction.toLowerCase() === 'long' ? 'text-[#22C55E]' : 'text-[#EF4444]'
                        )}>
                          {trade.direction.toLowerCase() === 'long' ? (
                            <ArrowUp className="w-3 h-3" />
                          ) : (
                            <ArrowDown className="w-3 h-3" />
                          )}
                          {trade.direction}
                        </span>
                      </td>
                      <td className={cn(
                        'py-3 text-sm font-medium',
                        (trade.pnl || 0) > 0 ? 'text-[#22C55E]' : 
                        (trade.pnl || 0) < 0 ? 'text-[#EF4444]' : 'text-[#A0A0A0]'
                      )}>
                        {trade.pnl !== null ? formatCurrency(trade.pnl) : '-'}
                      </td>
                      <td className="py-3 text-white text-sm">
                        {trade.grade || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <div className="card">
            <h3 className="text-white font-medium mb-4">Weekly Performance</h3>
            <div className="h-48 flex items-end justify-between gap-2">
              {stats?.weeklyChart.map((day) => (
                <div key={day.date} className="flex-1 flex flex-col items-center">
                  <div className="flex-1 w-full flex items-end justify-center">
                    {day.pnl !== 0 && (
                      <div
                        className={cn(
                          'w-full max-w-[40px] rounded-t',
                          day.pnl > 0 ? 'bg-[#22C55E]' : 'bg-[#EF4444]'
                        )}
                        style={{
                          height: `${Math.max(4, (Math.abs(day.pnl) / maxChartValue) * 140)}px`
                        }}
                      />
                    )}
                  </div>
                  <span className="text-[#A0A0A0] text-xs mt-2">{day.day}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h3 className="text-white font-medium mb-4">Dodgy&apos;s Rules</h3>
            <div className="h-48 flex items-center justify-center">
              <p className="text-[#A0A0A0] text-center text-sm italic px-4">
                &quot;{DODGYS_RULES[currentRule]}&quot;
              </p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-white font-medium">Monthly Overview</h3>
            <button className="btn-secondary text-sm py-1.5 px-3 flex items-center gap-2">
              <Download className="w-4 h-4" />
              Report
            </button>
          </div>
          <div className="grid grid-cols-7 gap-1 mb-4">
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day) => (
              <div key={day} className="text-center text-[#A0A0A0] text-xs py-1">
                {day}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {(() => {
              const firstDay = stats?.monthlyCalendar[0]
              const startPadding = firstDay 
                ? (new Date(firstDay.date).getDay() + 6) % 7 
                : 0
              
              return (
                <>
                  {Array.from({ length: startPadding }).map((_, i) => (
                    <div key={`pad-${i}`} className="aspect-square" />
                  ))}
                  {stats?.monthlyCalendar.map((day) => (
                    <div
                      key={day.date}
                      className={cn(
                        'aspect-square rounded flex items-center justify-center text-xs',
                        !day.hasTrades && 'bg-[#1A1A1A] text-[#A0A0A0]',
                        day.hasTrades && (day.pnl || 0) > 0 && 'bg-[#22C55E]/20 text-[#22C55E]',
                        day.hasTrades && (day.pnl || 0) < 0 && 'bg-[#EF4444]/20 text-[#EF4444]',
                        day.hasTrades && day.pnl === 0 && 'bg-[#1A1A1A] text-white'
                      )}
                    >
                      {day.day}
                    </div>
                  ))}
                </>
              )
            })()}
          </div>
          <div className="flex items-center justify-center gap-6 mt-4 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded bg-[#22C55E]/20" />
              <span className="text-[#A0A0A0]">Profit</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded bg-[#EF4444]/20" />
              <span className="text-[#A0A0A0]">Loss</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded bg-[#1A1A1A]" />
              <span className="text-[#A0A0A0]">No trades</span>
            </div>
          </div>
          <div className="text-center mt-4">
            <span className="text-[#A0A0A0] text-sm">Monthly P&L: </span>
            <span className={cn(
              'font-medium',
              (stats?.month.pnl || 0) > 0 ? 'text-[#22C55E]' :
              (stats?.month.pnl || 0) < 0 ? 'text-[#EF4444]' : 'text-[#A0A0A0]'
            )}>
              {formatCurrency(stats?.month.pnl || 0)}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
