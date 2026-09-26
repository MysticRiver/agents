import { NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/auth'
import { startOfMonth, endOfMonth } from 'date-fns'

interface Insight {
  type: 'pattern' | 'warning' | 'strength'
  message: string
  confidence: string
}

export async function GET() {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const allTrades = await prisma.trade.findMany({
      where: { userId: user.id },
      orderBy: { date: 'desc' }
    })

    if (allTrades.length < 10) {
      return NextResponse.json({ 
        insights: [],
        hasEnoughData: false,
        tradesNeeded: 10 - allTrades.length
      })
    }

    const insights: Insight[] = []
    const now = new Date()
    const monthStart = startOfMonth(now)
    const monthEnd = endOfMonth(now)

    const monthTrades = allTrades.filter(t => 
      t.date >= monthStart && t.date <= monthEnd
    )

    const ifvgTrades = monthTrades.filter(t => 
      t.setupType?.toLowerCase().includes('ifvg')
    )
    
    if (ifvgTrades.length >= 5) {
      const ifvgWins = ifvgTrades.filter(t => (t.pnl || 0) > 0).length
      const ifvgWinRate = Math.round((ifvgWins / ifvgTrades.length) * 100)
      
      if (ifvgWinRate >= 60) {
        insights.push({
          type: 'strength',
          message: `Your IFVG setups hit at ${ifvgWinRate}% this month (${ifvgWins} for ${ifvgTrades.length}). That's where your edge is.`,
          confidence: `Based on ${ifvgTrades.length} trades`
        })
      } else if (ifvgWinRate < 50) {
        insights.push({
          type: 'warning',
          message: `IFVG setups at ${ifvgWinRate}% this month (${ifvgWins} for ${ifvgTrades.length}). Review your entry criteria.`,
          confidence: `Based on ${ifvgTrades.length} trades`
        })
      }
    }

    const validatedTrades = allTrades.filter(t => t.validated)
    const unvalidatedTrades = allTrades.filter(t => !t.validated)

    if (validatedTrades.length >= 5 && unvalidatedTrades.length >= 5) {
      const validatedWins = validatedTrades.filter(t => (t.pnl || 0) > 0).length
      const validatedWinRate = Math.round((validatedWins / validatedTrades.length) * 100)
      
      const unvalidatedWins = unvalidatedTrades.filter(t => (t.pnl || 0) > 0).length
      const unvalidatedWinRate = Math.round((unvalidatedWins / unvalidatedTrades.length) * 100)

      if (validatedWinRate > unvalidatedWinRate + 15) {
        const lastThree = allTrades.slice(0, 3)
        const lastThreeUnvalidated = lastThree.filter(t => !t.validated).length
        
        let message = `Validated trades: ${validatedWinRate}% win rate. Unvalidated: ${unvalidatedWinRate}%.`
        if (lastThreeUnvalidated >= 2) {
          message += ` Last ${lastThreeUnvalidated} were unvalidated.`
        }
        
        insights.push({
          type: 'warning',
          message,
          confidence: `Based on ${validatedTrades.length + unvalidatedTrades.length} trades`
        })
      }
    }

    const tradesWithEmotional = allTrades.filter(t => t.emotionalState !== null)
    
    if (tradesWithEmotional.length >= 10) {
      const lowEmotional = tradesWithEmotional.filter(t => (t.emotionalState || 0) <= 2)
      const highEmotional = tradesWithEmotional.filter(t => (t.emotionalState || 0) >= 3)

      if (lowEmotional.length >= 5 && highEmotional.length >= 5) {
        const lowWins = lowEmotional.filter(t => (t.pnl || 0) > 0).length
        const lowWinRate = Math.round((lowWins / lowEmotional.length) * 100)
        
        const highWins = highEmotional.filter(t => (t.pnl || 0) > 0).length
        const highWinRate = Math.round((highWins / highEmotional.length) * 100)

        if (lowWinRate > highWinRate + 20) {
          insights.push({
            type: 'pattern',
            message: `Your win rate drops from ${lowWinRate}% to ${highWinRate}% when emotional state is 3+.`,
            confidence: `Based on ${tradesWithEmotional.length} trades`
          })
        }
      }
    }

    const instrumentStats: Record<string, { wins: number; total: number }> = {}
    for (const trade of allTrades) {
      if (!instrumentStats[trade.instrument]) {
        instrumentStats[trade.instrument] = { wins: 0, total: 0 }
      }
      instrumentStats[trade.instrument].total++
      if ((trade.pnl || 0) > 0) {
        instrumentStats[trade.instrument].wins++
      }
    }

    for (const [instrument, stats] of Object.entries(instrumentStats)) {
      if (stats.total >= 10) {
        const winRate = Math.round((stats.wins / stats.total) * 100)
        if (winRate >= 65) {
          insights.push({
            type: 'strength',
            message: `${instrument} is your strongest instrument at ${winRate}% (${stats.wins} for ${stats.total}).`,
            confidence: `Based on ${stats.total} trades`
          })
        } else if (winRate <= 40) {
          insights.push({
            type: 'warning',
            message: `${instrument} underperforming at ${winRate}% (${stats.wins} for ${stats.total}). Consider reducing size or skipping.`,
            confidence: `Based on ${stats.total} trades`
          })
        }
      }
    }

    const directionStats = { long: { wins: 0, total: 0 }, short: { wins: 0, total: 0 } }
    for (const trade of allTrades) {
      const dir = trade.direction.toLowerCase() as 'long' | 'short'
      if (directionStats[dir]) {
        directionStats[dir].total++
        if ((trade.pnl || 0) > 0) directionStats[dir].wins++
      }
    }

    if (directionStats.long.total >= 10 && directionStats.short.total >= 10) {
      const longRate = Math.round((directionStats.long.wins / directionStats.long.total) * 100)
      const shortRate = Math.round((directionStats.short.wins / directionStats.short.total) * 100)
      
      if (Math.abs(longRate - shortRate) >= 20) {
        const better = longRate > shortRate ? 'long' : 'short'
        const worse = longRate > shortRate ? 'short' : 'long'
        const betterRate = Math.max(longRate, shortRate)
        const worseRate = Math.min(longRate, shortRate)
        
        insights.push({
          type: 'pattern',
          message: `You're ${better} biased: ${betterRate}% vs ${worseRate}% on ${worse}s.`,
          confidence: `Based on ${directionStats.long.total + directionStats.short.total} trades`
        })
      }
    }

    const selectedInsights = insights.slice(0, 3)

    return NextResponse.json({ 
      insights: selectedInsights,
      hasEnoughData: true,
      totalTrades: allTrades.length
    })
  } catch (error) {
    console.error('Get insights error:', error)
    return NextResponse.json({ error: 'Failed to fetch insights' }, { status: 500 })
  }
}
