import bcrypt from 'bcryptjs'
import jwt from 'jsonwebtoken'
import { cookies } from 'next/headers'
import { prisma } from './prisma'

const JWT_SECRET = process.env.JWT_SECRET || 'dodgys-trading-tools-secret'

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, 12)
}

export async function verifyPassword(password: string, hashedPassword: string): Promise<boolean> {
  return bcrypt.compare(password, hashedPassword)
}

export function generateToken(userId: string): string {
  return jwt.sign({ userId }, JWT_SECRET, { expiresIn: '7d' })
}

export function verifyToken(token: string): { userId: string } | null {
  try {
    return jwt.verify(token, JWT_SECRET) as { userId: string }
  } catch {
    return null
  }
}

export async function getCurrentUser() {
  const cookieStore = await cookies()
  const token = cookieStore.get('auth_token')?.value
  
  if (!token) return null
  
  const payload = verifyToken(token)
  if (!payload) return null
  
  const session = await prisma.session.findFirst({
    where: {
      token,
      expiresAt: { gt: new Date() }
    },
    include: { user: true }
  })
  
  if (!session) return null
  
  return session.user
}

export async function createSession(userId: string): Promise<string> {
  const token = generateToken(userId)
  const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000) // 7 days
  
  await prisma.session.create({
    data: {
      userId,
      token,
      expiresAt
    }
  })
  
  return token
}

export async function deleteSession(token: string) {
  await prisma.session.deleteMany({
    where: { token }
  })
}
