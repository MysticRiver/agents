'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import Sidebar from '@/components/Sidebar'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { user, loading } = useAuth()
  const router = useRouter()
  const [unvalidatedCount, setUnvalidatedCount] = useState(0)

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login')
    }
  }, [user, loading, router])

  useEffect(() => {
    if (user) {
      fetch('/api/stats')
        .then(res => res.json())
        .then(data => {
          if (data.unvalidatedCount !== undefined) {
            setUnvalidatedCount(data.unvalidatedCount)
          }
        })
        .catch(() => {})
    }
  }, [user])

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center">
        <div className="text-[#A0A0A0]">Loading...</div>
      </div>
    )
  }

  if (!user) {
    return null
  }

  return (
    <div className="flex min-h-screen bg-[#0A0A0A]">
      <Sidebar unvalidatedCount={unvalidatedCount} />
      <main className="flex-1 pb-20 md:pb-0 overflow-x-hidden">
        {children}
      </main>
    </div>
  )
}
