import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/auth'

export async function GET() {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const rules = await prisma.rule.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: 'asc' }
    })

    return NextResponse.json({ rules })
  } catch (error) {
    console.error('Get rules error:', error)
    return NextResponse.json({ error: 'Failed to fetch rules' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const user = await getCurrentUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const data = await request.json()

    const rule = await prisma.rule.create({
      data: {
        userId: user.id,
        name: data.name,
        description: data.description || null,
        isActive: data.isActive !== undefined ? data.isActive : true
      }
    })

    return NextResponse.json({ rule })
  } catch (error) {
    console.error('Create rule error:', error)
    return NextResponse.json({ error: 'Failed to create rule' }, { status: 500 })
  }
}
