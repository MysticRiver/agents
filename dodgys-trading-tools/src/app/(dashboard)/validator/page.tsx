'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { format } from 'date-fns'
import { Shield, ChevronDown, ChevronUp, ArrowLeft, Check } from 'lucide-react'
import TopBar from '@/components/TopBar'
import { cn, getTradingSession, calculateValidationScore, formatCurrency } from '@/lib/utils'

interface TodayStats {
  tradesCount: number
  todayPnl: number
  isInLoss: boolean
  defaultInstrument: string
  fundedAccount: { drawdownRemaining: number } | null
}

interface Validation {
  id: string
  date: string
  instrument: string
  direction: string
  grade: string
  tradeTaken: boolean | null
}

export default function ValidatorPage() {
  const [instrument, setInstrument] = useState('NQ')
  const [direction, setDirection] = useState<'LONG' | 'SHORT' | ''>('')
  const [setupType, setSetupType] = useState('IFVG')
  const [checklist, setChecklist] = useState({
    clearDrawOnLiquidity: false,
    structureAligned: false,
    candleClosureConfirmed: false,
    higherTimeframeBias: false
  })
  const [emotionalState, setEmotionalState] = useState(2)
  const [showOptional, setShowOptional] = useState(false)
  const [entryPrice, setEntryPrice] = useState('')
  const [stopLoss, setStopLoss] = useState('')
  const [takeProfit, setTakeProfit] = useState('')
  const [sessionOverride, setSessionOverride] = useState('')
  const [isRevengeTrade, setIsRevengeTrade] = useState(false)
  const [isLightBulbTrade, setIsLightBulbTrade] = useState(false)
  const [tradesOverride, setTradesOverride] = useState('')
  const [isInLossOverride, setIsInLossOverride] = useState<boolean | null>(null)
  const [notes, setNotes] = useState('')
  
  const [todayStats, setTodayStats] = useState<TodayStats | null>(null)
  const [validations, setValidations] = useState<Validation[]>([])
  const [loading, setLoading] = useState(true)
  const [validating, setValidating] = useState(false)
  const [result, setResult] = useState<{
    score: number
    grade: string
    scoreBreakdown: { setupQuality: number; riskManagement: number; emotional: number }
    feedback: string
  } | null>(null)

  const session = getTradingSession()

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, validationsRes] = await Promise.all([
        fetch('/api/validations/today-stats'),
        fetch('/api/validations?limit=20')
      ])
      
      const statsData = await statsRes.json()
      const validationsData = await validationsRes.json()
      
      setTodayStats(statsData)
      setValidations(validationsData.validations || [])
      
      if (statsData.defaultInstrument) {
        setInstrument(statsData.defaultInstrument)
      }
    } catch (error) {
      console.error('Failed to fetch data:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleValidate = async () => {
    if (!direction) return
    
    setValidating(true)
    
    const tradesCount = tradesOverride ? parseInt(tradesOverride) : (todayStats?.tradesCount || 0)
    const isInLoss = isInLossOverride !== null ? isInLossOverride : (todayStats?.isInLoss || false)
    
    const validationResult = calculateValidationScore({
      instrument,
      direction,
      setupType,
      checklist,
      emotionalState,
      entryPrice: entryPrice ? parseFloat(entryPrice) : undefined,
      stopLoss: stopLoss ? parseFloat(stopLoss) : undefined,
      takeProfit: takeProfit ? parseFloat(takeProfit) : undefined,
      session: sessionOverride || undefined,
      tradesCountToday: tradesCount,
      isInLossToday: isInLoss
    })

    try {
      await fetch('/api/validations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instrument,
          direction,
          setupType,
          checklist,
          emotionalState,
          entryPrice: entryPrice ? parseFloat(entryPrice) : null,
          stopLoss: stopLoss ? parseFloat(stopLoss) : null,
          takeProfit: takeProfit ? parseFloat(takeProfit) : null,
          session: sessionOverride || session.name,
          isRevengeTrade,
          isLightBulbTrade,
          tradesCountToday: tradesCount,
          isInLossToday: isInLoss,
          notes,
          score: validationResult.score,
          grade: validationResult.grade,
          scoreBreakdown: validationResult.scoreBreakdown,
          feedback: validationResult.feedback
        })
      })

      setResult(validationResult)
      fetchData()
    } catch (error) {
      console.error('Failed to save validation:', error)
    } finally {
      setValidating(false)
    }
  }

  const resetForm = () => {
    setDirection('')
    setSetupType('IFVG')
    setChecklist({
      clearDrawOnLiquidity: false,
      structureAligned: false,
      candleClosureConfirmed: false,
      higherTimeframeBias: false
    })
    setEmotionalState(2)
    setShowOptional(false)
    setEntryPrice('')
    setStopLoss('')
    setTakeProfit('')
    setSessionOverride('')
    setIsRevengeTrade(false)
    setIsLightBulbTrade(false)
    setTradesOverride('')
    setIsInLossOverride(null)
    setNotes('')
    setResult(null)
  }

  const markTradeTaken = async (id: string, taken: boolean) => {
    try {
      await fetch(`/api/validations/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tradeTaken: taken })
      })
      fetchData()
    } catch (error) {
      console.error('Failed to update validation:', error)
    }
  }

  const getGradeColor = (grade: string) => {
    switch (grade) {
      case 'A+':
      case 'A':
        return 'bg-[#22C55E]'
      case 'B':
        return 'bg-yellow-500'
      case 'C':
        return 'bg-orange-500'
      default:
        return 'bg-[#EF4444]'
    }
  }

  if (loading) {
    return (
      <div>
        <TopBar breadcrumb={['Dashboard', 'Trade Validator']} />
        <div className="flex items-center justify-center h-64">
          <p className="text-[#A0A0A0]">Loading...</p>
        </div>
      </div>
    )
  }

  if (result) {
    return (
      <div>
        <TopBar breadcrumb={['Dashboard', 'Trade Validator']} />
        <div className="p-4 md:p-6 max-w-xl mx-auto">
          <div className="card text-center">
            <div className={cn(
              'inline-flex items-center justify-center w-24 h-24 rounded-full text-white text-4xl font-bold mb-4',
              getGradeColor(result.grade)
            )}>
              {result.grade}
            </div>
            
            <p className="text-white text-lg mb-2">Score: {result.score}/100</p>
            
            <div className="flex justify-center gap-4 mb-4 text-sm">
              <div>
                <p className="text-[#A0A0A0]">Setup Quality</p>
                <p className="text-white font-medium">{result.scoreBreakdown.setupQuality}/40</p>
              </div>
              <div>
                <p className="text-[#A0A0A0]">Risk Management</p>
                <p className="text-white font-medium">{result.scoreBreakdown.riskManagement}/30</p>
              </div>
              <div>
                <p className="text-[#A0A0A0]">Emotional</p>
                <p className="text-white font-medium">{result.scoreBreakdown.emotional}/30</p>
              </div>
            </div>

            <p className={cn(
              'text-lg font-medium mb-4',
              result.grade === 'F' ? 'text-[#EF4444]' : 
              result.grade === 'C' ? 'text-orange-500' :
              result.grade === 'B' ? 'text-yellow-500' : 'text-[#22C55E]'
            )}>
              {result.feedback}
            </p>

            {todayStats?.fundedAccount && (
              <p className="text-[#A0A0A0] text-sm mb-4">
                You have {formatCurrency(todayStats.fundedAccount.drawdownRemaining)} drawdown remaining.
              </p>
            )}

            <p className="text-[#A0A0A0] text-sm mb-6">
              To log this trade, tell AI Dodgy &apos;Log Trade&apos; in your agent chat.
            </p>

            <div className="flex gap-3">
              <button onClick={resetForm} className="btn-primary flex-1">
                Validate Another
              </button>
              <Link href="/dashboard" className="btn-secondary flex items-center justify-center gap-2">
                <ArrowLeft className="w-4 h-4" />
                Dashboard
              </Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <TopBar breadcrumb={['Dashboard', 'Trade Validator']} />
      
      <div className="p-4 md:p-6 max-w-xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Shield className="w-7 h-7 text-[#D42A2A]" />
            <h1 className="text-white text-2xl font-bold">Validator</h1>
          </div>
          <div className="flex items-center gap-2">
            <span className="px-3 py-1 bg-[#1A1A1A] text-[#A0A0A0] text-xs rounded-full">
              {session.name}
            </span>
            <span className="px-3 py-1 bg-[#1A1A1A] text-[#A0A0A0] text-xs rounded-full">
              Trade #{(todayStats?.tradesCount || 0) + 1} today
            </span>
          </div>
        </div>

        <div className="card space-y-4">
          <div className="flex gap-3">
            <div className="flex gap-1">
              {['NQ', 'ES', 'MNQ'].map((inst) => (
                <button
                  key={inst}
                  onClick={() => setInstrument(inst)}
                  className={cn(
                    'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                    instrument === inst
                      ? 'bg-[#D42A2A] text-white'
                      : 'bg-[#141414] text-[#A0A0A0] border border-[#1A1A1A]'
                  )}
                >
                  {inst}
                </button>
              ))}
            </div>
            <div className="flex gap-1 ml-auto">
              <button
                onClick={() => setDirection('LONG')}
                className={cn(
                  'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                  direction === 'LONG'
                    ? 'bg-[#22C55E] text-white'
                    : 'bg-[#141414] text-[#A0A0A0] border border-[#1A1A1A]'
                )}
              >
                LONG
              </button>
              <button
                onClick={() => setDirection('SHORT')}
                className={cn(
                  'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                  direction === 'SHORT'
                    ? 'bg-[#EF4444] text-white'
                    : 'bg-[#141414] text-[#A0A0A0] border border-[#1A1A1A]'
                )}
              >
                SHORT
              </button>
            </div>
          </div>

          <div className="flex flex-wrap gap-1">
            {['IFVG', 'Structure Break', 'Liquidity Sweep', 'V-Shape Recovery', 'Other'].map((type) => (
              <button
                key={type}
                onClick={() => setSetupType(type)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  setupType === type
                    ? 'bg-[#D42A2A] text-white'
                    : 'bg-[#141414] text-[#A0A0A0] border border-[#1A1A1A]'
                )}
              >
                {type}
              </button>
            ))}
          </div>

          <div>
            <p className="text-[#A0A0A0] text-sm mb-2">Setup Checklist</p>
            <div className="space-y-2">
              {[
                { key: 'clearDrawOnLiquidity', label: 'Clear draw on liquidity' },
                { key: 'structureAligned', label: 'Structure aligned with bias' },
                { key: 'candleClosureConfirmed', label: 'Candle closure confirmed' },
                { key: 'higherTimeframeBias', label: 'Higher timeframe bias checked' }
              ].map((item) => (
                <label
                  key={item.key}
                  className="flex items-center gap-3 cursor-pointer"
                >
                  <div
                    className={cn(
                      'w-5 h-5 rounded border flex items-center justify-center transition-colors',
                      checklist[item.key as keyof typeof checklist]
                        ? 'bg-[#D42A2A] border-[#D42A2A]'
                        : 'border-[#1A1A1A] bg-[#141414]'
                    )}
                    onClick={() => setChecklist(prev => ({
                      ...prev,
                      [item.key]: !prev[item.key as keyof typeof prev]
                    }))}
                  >
                    {checklist[item.key as keyof typeof checklist] && (
                      <Check className="w-3 h-3 text-white" />
                    )}
                  </div>
                  <span className="text-white text-sm">{item.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <p className="text-[#A0A0A0] text-sm">Emotional state</p>
              <p className="text-white text-sm font-medium">{emotionalState}/5</p>
            </div>
            <div className="relative">
              <input
                type="range"
                min="1"
                max="5"
                value={emotionalState}
                onChange={(e) => setEmotionalState(parseInt(e.target.value))}
                className="w-full h-2 rounded-lg appearance-none cursor-pointer"
                style={{
                  background: `linear-gradient(to right, #D42A2A ${((emotionalState - 1) / 4) * 100}%, #1A1A1A ${((emotionalState - 1) / 4) * 100}%)`
                }}
              />
            </div>
          </div>

          <button
            onClick={handleValidate}
            disabled={!direction || validating}
            className="btn-primary w-full py-3 flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Shield className="w-5 h-5" />
            {validating ? 'Validating...' : 'Validate This Setup'}
          </button>

          <button
            onClick={() => setShowOptional(!showOptional)}
            className="flex items-center justify-center gap-2 w-full py-2 text-[#A0A0A0] text-sm hover:text-white transition-colors"
          >
            Add details (optional)
            {showOptional ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {showOptional && (
            <div className="space-y-3 pt-2 border-t border-[#1A1A1A]">
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-[#A0A0A0] text-xs mb-1">Entry Price</label>
                  <input
                    type="number"
                    value={entryPrice}
                    onChange={(e) => setEntryPrice(e.target.value)}
                    className="input text-sm py-2"
                    placeholder="0.00"
                    step="0.25"
                  />
                </div>
                <div>
                  <label className="block text-[#A0A0A0] text-xs mb-1">Stop Loss</label>
                  <input
                    type="number"
                    value={stopLoss}
                    onChange={(e) => setStopLoss(e.target.value)}
                    className="input text-sm py-2"
                    placeholder="0.00"
                    step="0.25"
                  />
                </div>
                <div>
                  <label className="block text-[#A0A0A0] text-xs mb-1">Take Profit</label>
                  <input
                    type="number"
                    value={takeProfit}
                    onChange={(e) => setTakeProfit(e.target.value)}
                    className="input text-sm py-2"
                    placeholder="0.00"
                    step="0.25"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[#A0A0A0] text-xs mb-1">Session (override)</label>
                <select
                  value={sessionOverride}
                  onChange={(e) => setSessionOverride(e.target.value)}
                  className="input text-sm py-2"
                >
                  <option value="">Auto-detect ({session.name})</option>
                  <option value="Asia">Asia</option>
                  <option value="London">London</option>
                  <option value="Pre-Market">Pre-Market</option>
                  <option value="Data Release Window">Data Release Window</option>
                  <option value="NY Open">NY Open</option>
                  <option value="NY Afternoon">NY Afternoon</option>
                  <option value="After Hours">After Hours</option>
                </select>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => setIsRevengeTrade(!isRevengeTrade)}
                  className={cn(
                    'flex-1 py-2 rounded-lg text-xs font-medium transition-colors',
                    isRevengeTrade
                      ? 'bg-[#EF4444] text-white'
                      : 'bg-[#141414] text-[#A0A0A0] border border-[#1A1A1A]'
                  )}
                >
                  Revenge trade? {isRevengeTrade ? 'Yes' : 'No'}
                </button>
                <button
                  onClick={() => setIsLightBulbTrade(!isLightBulbTrade)}
                  className={cn(
                    'flex-1 py-2 rounded-lg text-xs font-medium transition-colors',
                    isLightBulbTrade
                      ? 'bg-[#22C55E] text-white'
                      : 'bg-[#141414] text-[#A0A0A0] border border-[#1A1A1A]'
                  )}
                >
                  Light bulb? {isLightBulbTrade ? 'Yes' : 'No'}
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[#A0A0A0] text-xs mb-1">Trades today</label>
                  <input
                    type="number"
                    value={tradesOverride}
                    onChange={(e) => setTradesOverride(e.target.value)}
                    className="input text-sm py-2"
                    placeholder={`Auto: ${todayStats?.tradesCount || 0}`}
                    min="0"
                  />
                </div>
                <div>
                  <label className="block text-[#A0A0A0] text-xs mb-1">In loss today?</label>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setIsInLossOverride(isInLossOverride === false ? null : false)}
                      className={cn(
                        'flex-1 py-2 rounded-lg text-xs font-medium',
                        isInLossOverride === false
                          ? 'bg-[#22C55E] text-white'
                          : 'bg-[#141414] text-[#A0A0A0] border border-[#1A1A1A]'
                      )}
                    >
                      No
                    </button>
                    <button
                      onClick={() => setIsInLossOverride(isInLossOverride === true ? null : true)}
                      className={cn(
                        'flex-1 py-2 rounded-lg text-xs font-medium',
                        isInLossOverride === true
                          ? 'bg-[#EF4444] text-white'
                          : 'bg-[#141414] text-[#A0A0A0] border border-[#1A1A1A]'
                      )}
                    >
                      Yes
                    </button>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-[#A0A0A0] text-xs mb-1">Why are you taking this trade?</label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="input text-sm py-2 min-h-[60px]"
                  placeholder="Notes..."
                />
              </div>
            </div>
          )}
        </div>

        <div className="mt-8">
          <h2 className="text-[#A0A0A0] text-xs uppercase tracking-wider mb-4">Recent Validations</h2>
          
          {validations.length === 0 ? (
            <div className="card text-center py-8">
              <p className="text-[#A0A0A0] text-sm">
                No validations yet. Grade your first setup above.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {validations.map((v) => (
                <div
                  key={v.id}
                  className="card py-3 px-4 flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    <span className={cn(
                      'w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold',
                      getGradeColor(v.grade)
                    )}>
                      {v.grade}
                    </span>
                    <div>
                      <p className="text-white text-sm">
                        {v.instrument} {v.direction}
                      </p>
                      <p className="text-[#A0A0A0] text-xs">
                        {format(new Date(v.date), 'MMM d, h:mm a')}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {v.tradeTaken === null ? (
                      <>
                        <button
                          onClick={() => markTradeTaken(v.id, true)}
                          className="px-2 py-1 bg-[#22C55E]/20 text-[#22C55E] text-xs rounded hover:bg-[#22C55E]/30"
                        >
                          Took it
                        </button>
                        <button
                          onClick={() => markTradeTaken(v.id, false)}
                          className="px-2 py-1 bg-[#1A1A1A] text-[#A0A0A0] text-xs rounded hover:bg-[#222]"
                        >
                          Skipped
                        </button>
                      </>
                    ) : (
                      <span className={cn(
                        'px-2 py-1 text-xs rounded',
                        v.tradeTaken
                          ? 'bg-[#22C55E]/20 text-[#22C55E]'
                          : 'bg-[#1A1A1A] text-[#A0A0A0]'
                      )}>
                        {v.tradeTaken ? 'Took it' : 'Skipped'}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
