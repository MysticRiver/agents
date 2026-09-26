import { NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/auth'
import { startOfDay, endOfDay } from 'date-fns'

export async function GET() {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const now = new Date()
    const todayStart = startOfDay(now)
    const todayEnd = endOfDay(now)

    const todayTrades = await prisma.trade.findMany({
      where: {
        userId: user.id,
        date: { gte: todayStart, lte: todayEnd }
      }
    })

    const todayValidations = await prisma.validation.findMany({
      where: {
        userId: user.id,
        createdAt: { gte: todayStart, lte: todayEnd }
      }
    })

    const tradesCount = todayTrades.length
    const todayPnl = todayTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
    const isInLoss = todayPnl < 0

    const settings = await prisma.settings.findUnique({
      where: { userId: user.id }
    })

    const fundedAccount = await prisma.fundedAccount.findUnique({
      where: { userId: user.id }
    })

    return NextResponse.json({
      tradesCount,
      todayPnl,
      isInLoss,
      validationsCount: todayValidations.length,
      defaultInstrument: settings?.defaultInstrument || 'NQ',
      dailyLossLimit: settings?.dailyLossLimit,
      fundedAccount: fundedAccount ? {
        drawdownRemaining: fundedAccount.maxDrawdown + Math.min(0, fundedAccount.currentPnl)
      } : null
    })
  } catch (error) {
    console.error('Get today stats error:', error)
    return NextResponse.json({ error: 'Failed to fetch stats' }, { status: 500 })
  }
}
