import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/auth'
import { startOfDay, endOfDay, startOfWeek, endOfWeek, subWeeks, startOfMonth, endOfMonth, subDays, format } from 'date-fns'

export async function GET(request: NextRequest) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const now = new Date()
    const todayStart = startOfDay(now)
    const todayEnd = endOfDay(now)
    const weekStart = startOfWeek(now, { weekStartsOn: 1 })
    const weekEnd = endOfWeek(now, { weekStartsOn: 1 })
    const lastWeekStart = startOfWeek(subWeeks(now, 1), { weekStartsOn: 1 })
    const lastWeekEnd = endOfWeek(subWeeks(now, 1), { weekStartsOn: 1 })
    const monthStart = startOfMonth(now)
    const monthEnd = endOfMonth(now)
    const yesterday = subDays(now, 1)
    const yesterdayStart = startOfDay(yesterday)
    const yesterdayEnd = endOfDay(yesterday)

    const todayTrades = await prisma.trade.findMany({
      where: {
        userId: user.id,
        date: { gte: todayStart, lte: todayEnd }
      }
    })

    const weekTrades = await prisma.trade.findMany({
      where: {
        userId: user.id,
        date: { gte: weekStart, lte: weekEnd }
      }
    })

    const lastWeekTrades = await prisma.trade.findMany({
      where: {
        userId: user.id,
        date: { gte: lastWeekStart, lte: lastWeekEnd }
      }
    })

    const monthTrades = await prisma.trade.findMany({
      where: {
        userId: user.id,
        date: { gte: monthStart, lte: monthEnd }
      }
    })

    const yesterdayTrades = await prisma.trade.findMany({
      where: {
        userId: user.id,
        date: { gte: yesterdayStart, lte: yesterdayEnd }
      }
    })

    const allTrades = await prisma.trade.findMany({
      where: { userId: user.id },
      orderBy: { date: 'desc' }
    })

    const todayPnl = todayTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
    const weekPnl = weekTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
    const lastWeekPnl = lastWeekTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
    const monthPnl = monthTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
    const yesterdayPnl = yesterdayTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)

    const weekWins = weekTrades.filter(t => (t.pnl || 0) > 0).length
    const weekTotal = weekTrades.filter(t => t.pnl !== null).length
    const weekWinRate = weekTotal > 0 ? (weekWins / weekTotal) * 100 : null

    const weekPnlChange = lastWeekPnl !== 0 
      ? ((weekPnl - lastWeekPnl) / Math.abs(lastWeekPnl)) * 100 
      : weekPnl !== 0 ? 100 : 0

    let currentStreak = 0
    const dailyPnls = new Map<string, number>()
    
    for (const trade of allTrades) {
      const dateKey = format(trade.date, 'yyyy-MM-dd')
      dailyPnls.set(dateKey, (dailyPnls.get(dateKey) || 0) + (trade.pnl || 0))
    }

    const sortedDates = Array.from(dailyPnls.keys()).sort().reverse()
    for (const date of sortedDates) {
      const pnl = dailyPnls.get(date) || 0
      if (pnl > 0) {
        currentStreak++
      } else {
        break
      }
    }

    let journalStreak = 0
    let bestJournalStreak = 0
    const tradingDays = new Set(allTrades.map(t => format(t.date, 'yyyy-MM-dd')))
    const sortedTradingDays = Array.from(tradingDays).sort().reverse()
    
    for (let i = 0; i < sortedTradingDays.length; i++) {
      journalStreak++
      if (journalStreak > bestJournalStreak) bestJournalStreak = journalStreak
    }

    let validationStreak = 0
    let bestValidationStreak = 0
    let currentValidationStreak = 0
    
    for (const trade of allTrades) {
      if (trade.validated) {
        currentValidationStreak++
        if (currentValidationStreak > bestValidationStreak) {
          bestValidationStreak = currentValidationStreak
        }
      } else {
        currentValidationStreak = 0
      }
    }
    
    for (const trade of allTrades) {
      if (trade.validated) {
        validationStreak++
      } else {
        break
      }
    }

    const settings = await prisma.settings.findUnique({
      where: { userId: user.id }
    })

    const validations = await prisma.validation.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: 'desc' }
    })

    interface TradingRule {
      id: string
      name: string
      enabled: boolean
      value?: number | string
    }

    let tradingRules: TradingRule[] = []
    if (settings?.tradingRules) {
      try {
        tradingRules = JSON.parse(settings.tradingRules)
      } catch {}
    }

    const enabledRules = tradingRules.filter(r => r.enabled)
    let rulesFollowedCount = 0
    let totalRuleChecks = 0
    const brokenRulesCount: Record<string, number> = {}

    for (const rule of enabledRules) {
      let followed = true
      
      switch (rule.id) {
        case 'maxTrades': {
          const maxTrades = (rule.value as number) || 2
          const tradeDays = new Map<string, number>()
          for (const trade of allTrades) {
            const day = format(trade.date, 'yyyy-MM-dd')
            tradeDays.set(day, (tradeDays.get(day) || 0) + 1)
          }
          const violations = Array.from(tradeDays.values()).filter(c => c > maxTrades).length
          if (violations > 0) {
            followed = false
            brokenRulesCount[rule.id] = violations
          }
          break
        }
        case 'onlyASetups': {
          const nonAValidations = validations.filter(v => 
            v.tradeTaken === true && !['A+', 'A'].includes(v.grade)
          ).length
          if (nonAValidations > 0) {
            followed = false
            brokenRulesCount[rule.id] = nonAValidations
          }
          break
        }
        case 'validateEvery': {
          const unvalidatedTrades = allTrades.filter(t => !t.validated).length
          if (unvalidatedTrades > 0) {
            followed = false
            brokenRulesCount[rule.id] = unvalidatedTrades
          }
          break
        }
        case 'journalEvery': {
          followed = true
          break
        }
        case 'noEmotional': {
          const emotionalValidations = validations.filter(v => 
            v.tradeTaken === true && v.emotionalState >= 4
          ).length
          if (emotionalValidations > 0) {
            followed = false
            brokenRulesCount[rule.id] = emotionalValidations
          }
          break
        }
        case 'minRR': {
          break
        }
        case 'onlyInstrument': {
          const targetInstrument = rule.value as string || 'NQ'
          const wrongInstrument = allTrades.filter(t => t.instrument !== targetInstrument).length
          if (wrongInstrument > 0) {
            followed = false
            brokenRulesCount[rule.id] = wrongInstrument
          }
          break
        }
        default:
          break
      }

      totalRuleChecks++
      if (followed) rulesFollowedCount++
    }

    const rulesComplianceRate = totalRuleChecks > 0 
      ? (rulesFollowedCount / totalRuleChecks) * 100 
      : null
    
    const hasRules = enabledRules.length > 0

    const fundedAccount = await prisma.fundedAccount.findUnique({
      where: { userId: user.id }
    })

    const dailyPnlArray = []
    for (let i = 6; i >= 0; i--) {
      const date = subDays(weekEnd, i)
      const dateKey = format(date, 'yyyy-MM-dd')
      dailyPnlArray.push({
        date: dateKey,
        day: format(date, 'EEE'),
        pnl: dailyPnls.get(dateKey) || 0
      })
    }

    const monthlyCalendar = []
    let currentDate = monthStart
    while (currentDate <= monthEnd) {
      const dateKey = format(currentDate, 'yyyy-MM-dd')
      const dayPnl = dailyPnls.get(dateKey)
      monthlyCalendar.push({
        date: dateKey,
        day: currentDate.getDate(),
        pnl: dayPnl !== undefined ? dayPnl : null,
        hasTrades: dayPnl !== undefined
      })
      currentDate = new Date(currentDate.getTime() + 24 * 60 * 60 * 1000)
    }

    const unvalidatedCount = allTrades.filter(t => !t.validated).length

    return NextResponse.json({
      today: {
        pnl: todayPnl,
        trades: todayTrades.length
      },
      week: {
        pnl: weekPnl,
        pnlChange: weekPnlChange,
        winRate: weekWinRate,
        trades: weekTrades.length
      },
      month: {
        pnl: monthPnl,
        trades: monthTrades.length
      },
      yesterday: {
        pnl: yesterdayPnl,
        trades: yesterdayTrades.length,
        winRate: yesterdayTrades.length > 0 
          ? (yesterdayTrades.filter(t => (t.pnl || 0) > 0).length / yesterdayTrades.length) * 100 
          : null
      },
      streaks: {
        greenDays: currentStreak,
        journal: journalStreak,
        bestJournal: bestJournalStreak,
        validation: validationStreak,
        bestValidation: bestValidationStreak
      },
      rulesCompliance: {
        rate: rulesComplianceRate,
        followed: rulesFollowedCount,
        total: totalRuleChecks,
        brokenRules: brokenRulesCount,
        hasRules
      },
      fundedAccount,
      weeklyChart: dailyPnlArray,
      monthlyCalendar,
      recentTrades: allTrades.slice(0, 5),
      totalTrades: allTrades.length,
      unvalidatedCount
    })
  } catch (error) {
    console.error('Get stats error:', error)
    return NextResponse.json({ error: 'Failed to fetch stats' }, { status: 500 })
  }
}
