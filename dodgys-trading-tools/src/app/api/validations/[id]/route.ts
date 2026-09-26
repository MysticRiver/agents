import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { getCurrentUser } from '@/lib/auth'

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

    const existingValidation = await prisma.validation.findFirst({
      where: { id, userId: user.id }
    })

    if (!existingValidation) {
      return NextResponse.json({ error: 'Validation not found' }, { status: 404 })
    }

    const validation = await prisma.validation.update({
      where: { id },
      data: {
        tradeTaken: data.tradeTaken !== undefined ? data.tradeTaken : undefined
      }
    })

    return NextResponse.json({ validation })
  } catch (error) {
    console.error('Update validation error:', error)
    return NextResponse.json({ error: 'Failed to update validation' }, { status: 500 })
  }
}
