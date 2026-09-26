import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/auth'
import { startOfDay, endOfDay } from 'date-fns'

export async function GET(request: NextRequest) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { searchParams } = new URL(request.url)
    const limit = parseInt(searchParams.get('limit') || '20')

    const validations = await prisma.validation.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: 'desc' },
      take: limit
    })

    return NextResponse.json({ validations })
  } catch (error) {
    console.error('Get validations error:', error)
    return NextResponse.json({ error: 'Failed to fetch validations' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const data = await request.json()

    const validation = await prisma.validation.create({
      data: {
        userId: user.id,
        instrument: data.instrument,
        direction: data.direction,
        setupType: data.setupType,
        checklist: JSON.stringify(data.checklist),
        emotionalState: data.emotionalState,
        entryPrice: data.entryPrice ? parseFloat(data.entryPrice) : null,
        stopLoss: data.stopLoss ? parseFloat(data.stopLoss) : null,
        takeProfit: data.takeProfit ? parseFloat(data.takeProfit) : null,
        session: data.session || null,
        isRevengeTrade: data.isRevengeTrade || false,
        isLightBulbTrade: data.isLightBulbTrade || false,
        tradesCountToday: data.tradesCountToday ?? null,
        isInLossToday: data.isInLossToday ?? null,
        screenshot: data.screenshot || null,
        notes: data.notes || null,
        score: data.score,
        grade: data.grade,
        scoreBreakdown: JSON.stringify(data.scoreBreakdown),
        feedback: data.feedback,
        tradeTaken: null
      }
    })

    return NextResponse.json({ validation })
  } catch (error) {
    console.error('Create validation error:', error)
    return NextResponse.json({ error: 'Failed to create validation' }, { status: 500 })
  }
}
