'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Plus, X } from 'lucide-react'

interface TopBarProps {
  breadcrumb?: string[]
}

export default function TopBar({ breadcrumb = ['Dashboard'] }: TopBarProps) {
  const [fabOpen, setFabOpen] = useState(false)

  return (
    <>
      <header className="sticky top-0 z-40 bg-[#0A0A0A]/95 backdrop-blur-sm border-b border-[#1A1A1A]">
        <div className="flex items-center justify-between px-4 md:px-6 py-3">
          <nav className="text-sm text-[#A0A0A0]">
            {breadcrumb.map((item, i) => (
              <span key={i}>
                {i > 0 && <span className="mx-2">&gt;</span>}
                <span className={i === breadcrumb.length - 1 ? 'text-white' : ''}>
                  {item}
                </span>
              </span>
            ))}
          </nav>

          <div className="hidden md:flex items-center gap-2">
            <Link
              href="/validator"
              className="px-4 py-2 bg-[#D42A2A] text-white text-sm font-medium rounded-full hover:bg-[#D42A2A]/90 transition-colors"
            >
              Validate
            </Link>
            <Link
              href="/calculator"
              className="px-4 py-2 bg-[#141414] text-white text-sm font-medium rounded-full border border-[#1A1A1A] hover:bg-[#1A1A1A] transition-colors"
            >
              Calculator
            </Link>
          </div>
        </div>
      </header>

      <div className="md:hidden fixed bottom-20 right-4 z-50">
        {fabOpen && (
          <div className="absolute bottom-14 right-0 flex flex-col gap-2 mb-2">
            <Link
              href="/validator"
              className="px-4 py-2 bg-[#D42A2A] text-white text-sm font-medium rounded-full shadow-lg whitespace-nowrap"
              onClick={() => setFabOpen(false)}
            >
              Validate
            </Link>
            <Link
              href="/calculator"
              className="px-4 py-2 bg-[#141414] text-white text-sm font-medium rounded-full border border-[#1A1A1A] shadow-lg whitespace-nowrap"
              onClick={() => setFabOpen(false)}
            >
              Calculator
            </Link>
          </div>
        )}
        <button
          onClick={() => setFabOpen(!fabOpen)}
          className="w-14 h-14 bg-[#D42A2A] text-white rounded-full shadow-lg flex items-center justify-center transition-transform hover:scale-105"
        >
          {fabOpen ? <X className="w-6 h-6" /> : <Plus className="w-6 h-6" />}
        </button>
      </div>
    </>
  )
}
