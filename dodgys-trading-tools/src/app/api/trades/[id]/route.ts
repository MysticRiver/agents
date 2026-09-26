import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/auth'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { id } = await params

    const trade = await prisma.trade.findFirst({
      where: { id, userId: user.id }
    })

    if (!trade) {
      return NextResponse.json({ error: 'Trade not found' }, { status: 404 })
    }

    return NextResponse.json({ trade })
  } catch (error) {
    console.error('Get trade error:', error)
    return NextResponse.json({ error: 'Failed to fetch trade' }, { status: 500 })
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { id } = await params
    const data = await request.json()

    const existingTrade = await prisma.trade.findFirst({
      where: { id, userId: user.id }
    })

    if (!existingTrade) {
      return NextResponse.json({ error: 'Trade not found' }, { status: 404 })
    }

    const trade = await prisma.trade.update({
      where: { id },
      data: {
        date: data.date ? new Date(data.date) : undefined,
        instrument: data.instrument,
        direction: data.direction,
        entryPrice: data.entryPrice ? parseFloat(data.entryPrice) : undefined,
        exitPrice: data.exitPrice !== undefined ? (data.exitPrice ? parseFloat(data.exitPrice) : null) : undefined,
        stopLoss: data.stopLoss !== undefined ? (data.stopLoss ? parseFloat(data.stopLoss) : null) : undefined,
        takeProfit: data.takeProfit !== undefined ? (data.takeProfit ? parseFloat(data.takeProfit) : null) : undefined,
        contracts: data.contracts ? parseInt(data.contracts) : undefined,
        pnl: data.pnl !== undefined ? (data.pnl ? parseFloat(data.pnl) : null) : undefined,
        pnlPoints: data.pnlPoints !== undefined ? (data.pnlPoints ? parseFloat(data.pnlPoints) : null) : undefined,
        grade: data.grade !== undefined ? data.grade : undefined,
        setupType: data.setupType !== undefined ? data.setupType : undefined,
        validated: data.validated !== undefined ? data.validated : undefined,
        validationData: data.validationData !== undefined ? (data.validationData ? JSON.stringify(data.validationData) : null) : undefined,
        emotionalState: data.emotionalState !== undefined ? (data.emotionalState ? parseInt(data.emotionalState) : null) : undefined,
        notes: data.notes !== undefined ? data.notes : undefined,
        rulesFollowed: data.rulesFollowed !== undefined ? (data.rulesFollowed ? JSON.stringify(data.rulesFollowed) : null) : undefined,
        rulesBroken: data.rulesBroken !== undefined ? (data.rulesBroken ? JSON.stringify(data.rulesBroken) : null) : undefined,
        screenshots: data.screenshots !== undefined ? (data.screenshots ? JSON.stringify(data.screenshots) : null) : undefined
      }
    })

    return NextResponse.json({ trade })
  } catch (error) {
    console.error('Update trade error:', error)
    return NextResponse.json({ error: 'Failed to update trade' }, { status: 500 })
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { id } = await params

    const existingTrade = await prisma.trade.findFirst({
      where: { id, userId: user.id }
    })

    if (!existingTrade) {
      return NextResponse.json({ error: 'Trade not found' }, { status: 404 })
    }

    await prisma.trade.delete({ where: { id } })

    return NextResponse.json({ success: true })
  } catch (error) {
    console.error('Delete trade error:', error)
    return NextResponse.json({ error: 'Failed to delete trade' }, { status: 500 })
  }
}
