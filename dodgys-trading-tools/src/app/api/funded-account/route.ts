import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/auth'

export async function GET() {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const fundedAccount = await prisma.fundedAccount.findUnique({
      where: { userId: user.id }
    })

    return NextResponse.json({ fundedAccount })
  } catch (error) {
    console.error('Get funded account error:', error)
    return NextResponse.json({ error: 'Failed to fetch funded account' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const data = await request.json()

    const fundedAccount = await prisma.fundedAccount.upsert({
      where: { userId: user.id },
      create: {
        userId: user.id,
        firmName: data.firmName,
        accountSize: parseFloat(data.accountSize),
        profitTarget: parseFloat(data.profitTarget),
        maxDrawdown: parseFloat(data.maxDrawdown),
        currentPnl: data.currentPnl ? parseFloat(data.currentPnl) : 0,
        daysActive: data.daysActive ? parseInt(data.daysActive) : 0,
        startDate: new Date(data.startDate),
        isActive: true
      },
      update: {
        firmName: data.firmName,
        accountSize: parseFloat(data.accountSize),
        profitTarget: parseFloat(data.profitTarget),
        maxDrawdown: parseFloat(data.maxDrawdown),
        currentPnl: data.currentPnl !== undefined ? parseFloat(data.currentPnl) : undefined,
        daysActive: data.daysActive !== undefined ? parseInt(data.daysActive) : undefined,
        startDate: data.startDate ? new Date(data.startDate) : undefined,
        isActive: data.isActive !== undefined ? data.isActive : undefined
      }
    })

    return NextResponse.json({ fundedAccount })
  } catch (error) {
    console.error('Create/update funded account error:', error)
    return NextResponse.json({ error: 'Failed to save funded account' }, { status: 500 })
  }
}

export async function DELETE() {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    await prisma.fundedAccount.deleteMany({
      where: { userId: user.id }
    })

    return NextResponse.json({ success: true })
  } catch (error) {
    console.error('Delete funded account error:', error)
    return NextResponse.json({ error: 'Failed to delete funded account' }, { status: 500 })
  }
}
