import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/auth'

export async function GET(request: NextRequest) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { searchParams } = new URL(request.url)
    const limit = parseInt(searchParams.get('limit') || '50')
    const offset = parseInt(searchParams.get('offset') || '0')
    const startDate = searchParams.get('startDate')
    const endDate = searchParams.get('endDate')

    const where: Record<string, unknown> = { userId: user.id }
    
    if (startDate || endDate) {
      where.date = {}
      if (startDate) (where.date as Record<string, Date>).gte = new Date(startDate)
      if (endDate) (where.date as Record<string, Date>).lte = new Date(endDate)
    }

    const trades = await prisma.trade.findMany({
      where,
      orderBy: { date: 'desc' },
      take: limit,
      skip: offset
    })

    const total = await prisma.trade.count({ where })

    return NextResponse.json({ trades, total })
  } catch (error) {
    console.error('Get trades error:', error)
    return NextResponse.json({ error: 'Failed to fetch trades' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const data = await request.json()

    const trade = await prisma.trade.create({
      data: {
        userId: user.id,
        date: new Date(data.date),
        instrument: data.instrument,
        direction: data.direction,
        entryPrice: parseFloat(data.entryPrice),
        exitPrice: data.exitPrice ? parseFloat(data.exitPrice) : null,
        stopLoss: data.stopLoss ? parseFloat(data.stopLoss) : null,
        takeProfit: data.takeProfit ? parseFloat(data.takeProfit) : null,
        contracts: parseInt(data.contracts) || 1,
        pnl: data.pnl ? parseFloat(data.pnl) : null,
        pnlPoints: data.pnlPoints ? parseFloat(data.pnlPoints) : null,
        grade: data.grade || null,
        setupType: data.setupType || null,
        validated: data.validated || false,
        validationData: data.validationData ? JSON.stringify(data.validationData) : null,
        emotionalState: data.emotionalState ? parseInt(data.emotionalState) : null,
        notes: data.notes || null,
        rulesFollowed: data.rulesFollowed ? JSON.stringify(data.rulesFollowed) : null,
        rulesBroken: data.rulesBroken ? JSON.stringify(data.rulesBroken) : null,
        screenshots: data.screenshots ? JSON.stringify(data.screenshots) : null
      }
    })

    return NextResponse.json({ trade })
  } catch (error) {
    console.error('Create trade error:', error)
    return NextResponse.json({ error: 'Failed to create trade' }, { status: 500 })
  }
}
