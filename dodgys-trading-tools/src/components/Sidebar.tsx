'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { 
  LayoutGrid, 
  Shield, 
  BookOpen, 
  Calculator, 
  Settings, 
  ChevronLeft,
  ChevronRight,
  LogOut
} from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { cn } from '@/lib/utils'

interface SidebarProps {
  unvalidatedCount?: number
}

export default function Sidebar({ unvalidatedCount = 0 }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)
  const pathname = usePathname()
  const { user, logout } = useAuth()

  const navItems = [
    { href: '/dashboard', icon: LayoutGrid, label: 'Dashboard' },
    { href: '/validator', icon: Shield, label: 'Trade Validator', badge: unvalidatedCount > 0 },
    { href: '/journal', icon: BookOpen, label: 'Trading Journal' },
    { href: '/calculator', icon: Calculator, label: 'Position Size & Risk Cal...' },
    { href: '/settings', icon: Settings, label: 'Settings' },
  ]

  const isActive = (href: string) => pathname === href

  return (
    <>
      <aside 
        className={cn(
          'hidden md:flex flex-col h-screen bg-[#141414] border-r border-[#1A1A1A] transition-all duration-300',
          collapsed ? 'w-[72px]' : 'w-[260px]'
        )}
      >
        <div className="flex items-center justify-between p-4 border-b border-[#1A1A1A]">
          {!collapsed && (
            <div>
              <h1 className="text-white font-bold text-xl">DODGY</h1>
              <p className="text-[#A0A0A0] text-xs">AI Trading Tools</p>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-2 hover:bg-[#1A1A1A] rounded-lg transition-colors ml-auto"
          >
            {collapsed ? (
              <ChevronRight className="w-5 h-5 text-[#A0A0A0]" />
            ) : (
              <ChevronLeft className="w-5 h-5 text-[#A0A0A0]" />
            )}
          </button>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 px-3 py-3 rounded-lg transition-colors relative',
                isActive(item.href)
                  ? 'bg-[#D42A2A]/10 text-[#D42A2A]'
                  : 'text-[#A0A0A0] hover:bg-[#1A1A1A] hover:text-white'
              )}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {!collapsed && (
                <span className="text-sm font-medium truncate">{item.label}</span>
              )}
              {item.badge && (
                <span className="absolute top-2 right-2 w-2 h-2 bg-[#D42A2A] rounded-full" />
              )}
            </Link>
          ))}
        </nav>

        <div className="p-4 border-t border-[#1A1A1A]">
          {!collapsed && (
            <div className="text-xs text-[#A0A0A0] mb-4">
              <span className="text-white font-medium">IFVG</span>
              <span className="mx-1">•</span>
              <span>NQ / ES / MNQ</span>
            </div>
          )}
          
          <div className={cn('flex items-center gap-3', collapsed && 'justify-center')}>
            <div className="w-9 h-9 rounded-full bg-[#D42A2A] flex items-center justify-center flex-shrink-0">
              <span className="text-white font-medium text-sm">
                {user?.name?.charAt(0).toUpperCase() || 'U'}
              </span>
            </div>
            {!collapsed && (
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium text-sm truncate">{user?.name || 'User'}</p>
                <p className="text-[#A0A0A0] text-xs">Trader</p>
              </div>
            )}
          </div>
          
          {!collapsed && (
            <button
              onClick={logout}
              className="flex items-center gap-2 text-[#A0A0A0] hover:text-white text-sm mt-3 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Sign out
            </button>
          )}
        </div>
      </aside>

      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-[#141414] border-t border-[#1A1A1A] z-50">
        <div className="flex items-center justify-around py-2">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex flex-col items-center gap-1 p-2 relative',
                isActive(item.href) ? 'text-[#D42A2A]' : 'text-[#A0A0A0]'
              )}
            >
              <item.icon className="w-5 h-5" />
              {item.badge && (
                <span className="absolute top-1 right-1 w-2 h-2 bg-[#D42A2A] rounded-full" />
              )}
            </Link>
          ))}
        </div>
      </nav>
    </>
  )
}
