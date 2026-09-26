'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'

export default function Home() {
  const { user, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading) {
      if (user) {
        router.push('/dashboard')
      } else {
        router.push('/login')
      }
    }
  }, [user, loading, router])

  return (
    <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-white font-bold text-3xl mb-2">DODGY</h1>
        <p className="text-[#A0A0A0] text-sm">AI Trading Tools</p>
        <p className="text-[#A0A0A0] text-sm mt-4">Loading...</p>
      </div>
    </div>
  )
}
