import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/auth'

export async function GET() {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    let settings = await prisma.settings.findUnique({
      where: { userId: user.id }
    })

    if (!settings) {
      settings = await prisma.settings.create({
        data: {
          userId: user.id,
          dailyLossLimit: null,
          defaultInstrument: 'NQ',
          timezone: 'America/New_York'
        }
      })
    }

    return NextResponse.json({ settings })
  } catch (error) {
    console.error('Get settings error:', error)
    return NextResponse.json({ error: 'Failed to fetch settings' }, { status: 500 })
  }
}

export async function PUT(request: NextRequest) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const data = await request.json()

    const settings = await prisma.settings.upsert({
      where: { userId: user.id },
      create: {
        userId: user.id,
        dailyLossLimit: data.dailyLossLimit ? parseFloat(data.dailyLossLimit) : null,
        defaultInstrument: data.defaultInstrument || 'NQ',
        timezone: data.timezone || 'America/New_York',
        briefingDismissedDate: data.briefingDismissedDate || null
      },
      update: {
        dailyLossLimit: data.dailyLossLimit !== undefined ? (data.dailyLossLimit ? parseFloat(data.dailyLossLimit) : null) : undefined,
        defaultInstrument: data.defaultInstrument !== undefined ? data.defaultInstrument : undefined,
        timezone: data.timezone !== undefined ? data.timezone : undefined,
        briefingDismissedDate: data.briefingDismissedDate !== undefined ? data.briefingDismissedDate : undefined
      }
    })

    return NextResponse.json({ settings })
  } catch (error) {
    console.error('Update settings error:', error)
    return NextResponse.json({ error: 'Failed to update settings' }, { status: 500 })
  }
}
