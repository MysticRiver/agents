'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { CheckCircle, XCircle, AlertCircle, ArrowLeft } from 'lucide-react'
import TopBar from '@/components/TopBar'
import { cn, getContractValue, calculatePnl } from '@/lib/utils'

interface ValidationResult {
  passed: boolean
  message: string
}

interface Rule {
  id: string
  name: string
  description: string | null
  isActive: boolean
}

export default function ValidatorPage() {
  const [instrument, setInstrument] = useState('NQ')
  const [direction, setDirection] = useState<'long' | 'short'>('long')
  const [entryPrice, setEntryPrice] = useState('')
  const [stopLoss, setStopLoss] = useState('')
  const [takeProfit, setTakeProfit] = useState('')
  const [contracts, setContracts] = useState('1')
  const [grade, setGrade] = useState('')
  const [setupType, setSetupType] = useState('IFVG')
  const [emotionalState, setEmotionalState] = useState('1')
  const [notes, setNotes] = useState('')
  const [rules, setRules] = useState<Rule[]>([])
  const [rulesFollowed, setRulesFollowed] = useState<string[]>([])
  const [rulesBroken, setRulesBroken] = useState<string[]>([])
  const [validated, setValidated] = useState(false)
  const [validationResults, setValidationResults] = useState<ValidationResult[]>([])
  const [saving, setSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)

  useEffect(() => {
    fetch('/api/rules')
      .then(res => res.json())
      .then(data => {
        if (data.rules) {
          setRules(data.rules.filter((r: Rule) => r.isActive))
        }
      })
      .catch(() => {})
  }, [])

  const validateSetup = () => {
    const results: ValidationResult[] = []
    const entry = parseFloat(entryPrice)
    const stop = parseFloat(stopLoss)
    const target = parseFloat(takeProfit)
    const contractCount = parseInt(contracts)
    const { pointValue } = getContractValue(instrument)

    if (!entryPrice || isNaN(entry)) {
      results.push({ passed: false, message: 'Entry price is required' })
    } else {
      results.push({ passed: true, message: 'Entry price set' })
    }

    if (!stopLoss || isNaN(stop)) {
      results.push({ passed: false, message: 'Stop loss is required' })
    } else {
      const stopDistance = Math.abs(entry - stop)
      const maxRisk = entry * 0.02
      if (stopDistance > maxRisk) {
        results.push({ passed: false, message: `Stop loss too wide (${stopDistance.toFixed(2)} points)` })
      } else {
        results.push({ passed: true, message: `Stop loss: ${stopDistance.toFixed(2)} points risk` })
      }
    }

    if (direction === 'long' && stop >= entry) {
      results.push({ passed: false, message: 'Stop loss must be below entry for long positions' })
    } else if (direction === 'short' && stop <= entry) {
      results.push({ passed: false, message: 'Stop loss must be above entry for short positions' })
    }

    if (takeProfit && !isNaN(target)) {
      if (direction === 'long' && target <= entry) {
        results.push({ passed: false, message: 'Take profit must be above entry for long positions' })
      } else if (direction === 'short' && target >= entry) {
        results.push({ passed: false, message: 'Take profit must be below entry for short positions' })
      } else {
        const riskPoints = Math.abs(entry - stop)
        const rewardPoints = Math.abs(target - entry)
        const rr = rewardPoints / riskPoints
        
        if (rr < 1.5) {
          results.push({ passed: false, message: `R:R ratio of ${rr.toFixed(2)} is below 1.5` })
        } else {
          results.push({ passed: true, message: `R:R ratio: ${rr.toFixed(2)}` })
        }
      }
    }

    if (!grade) {
      results.push({ passed: false, message: 'Grade the setup before taking it' })
    } else if (grade === 'B' || grade === 'C') {
      results.push({ passed: false, message: `Grade ${grade} setup - consider skipping on live account` })
    } else {
      results.push({ passed: true, message: `Grade ${grade} setup approved` })
    }

    if (parseInt(emotionalState) >= 3) {
      results.push({ passed: false, message: `Emotional state ${emotionalState}/5 is elevated - consider waiting` })
    } else {
      results.push({ passed: true, message: 'Emotional state is calm' })
    }

    if (contractCount > 0) {
      const riskAmount = Math.abs(entry - stop) * pointValue * contractCount
      results.push({ passed: true, message: `Risk amount: $${riskAmount.toFixed(2)} (${contractCount} contracts)` })
    }

    setValidationResults(results)
    setValidated(true)
  }

  const handleRuleToggle = (ruleId: string, followed: boolean) => {
    if (followed) {
      setRulesFollowed(prev => [...prev.filter(id => id !== ruleId), ruleId])
      setRulesBroken(prev => prev.filter(id => id !== ruleId))
    } else {
      setRulesBroken(prev => [...prev.filter(id => id !== ruleId), ruleId])
      setRulesFollowed(prev => prev.filter(id => id !== ruleId))
    }
  }

  const saveTrade = async () => {
    setSaving(true)
    try {
      const entry = parseFloat(entryPrice)
      const stop = parseFloat(stopLoss)
      const target = takeProfit ? parseFloat(takeProfit) : null

      const validationData = {
        results: validationResults,
        timestamp: new Date().toISOString(),
        allPassed: validationResults.every(r => r.passed)
      }

      await fetch('/api/trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          date: new Date().toISOString(),
          instrument,
          direction,
          entryPrice: entry,
          stopLoss: stop,
          takeProfit: target,
          contracts: parseInt(contracts),
          grade,
          setupType,
          validated: true,
          validationData,
          emotionalState: parseInt(emotionalState),
          notes,
          rulesFollowed,
          rulesBroken
        })
      })

      setSaveSuccess(true)
    } catch (error) {
      console.error('Failed to save trade:', error)
    } finally {
      setSaving(false)
    }
  }

  const resetForm = () => {
    setEntryPrice('')
    setStopLoss('')
    setTakeProfit('')
    setContracts('1')
    setGrade('')
    setNotes('')
    setRulesFollowed([])
    setRulesBroken([])
    setValidated(false)
    setValidationResults([])
    setSaveSuccess(false)
  }

  const passedCount = validationResults.filter(r => r.passed).length
  const totalCount = validationResults.length
  const allPassed = passedCount === totalCount && totalCount > 0

  return (
    <div>
      <TopBar breadcrumb={['Dashboard', 'Trade Validator']} />
      
      <div className="p-4 md:p-6 max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-white text-2xl font-semibold">Trade Validator</h1>
          <p className="text-[#A0A0A0] text-sm mt-1">
            Grade and validate your setup before entry
          </p>
        </div>

        {saveSuccess ? (
          <div className="card text-center py-12">
            <CheckCircle className="w-16 h-16 text-[#22C55E] mx-auto mb-4" />
            <h2 className="text-white text-xl font-semibold mb-2">Trade Validated & Saved</h2>
            <p className="text-[#A0A0A0] mb-6">
              Tell AI Dodgy &apos;Log Trade&apos; to record this setup after execution
            </p>
            <div className="flex items-center justify-center gap-4">
              <button onClick={resetForm} className="btn-primary">
                Validate Another
              </button>
              <Link href="/dashboard" className="btn-secondary flex items-center gap-2">
                <ArrowLeft className="w-4 h-4" />
                Back to Dashboard
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="card">
              <h2 className="text-white font-medium mb-4">Setup Details</h2>
              
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Instrument</label>
                  <select
                    value={instrument}
                    onChange={(e) => setInstrument(e.target.value)}
                    className="input"
                  >
                    <option value="NQ">NQ (Nasdaq)</option>
                    <option value="ES">ES (S&P 500)</option>
                    <option value="MNQ">MNQ (Micro Nasdaq)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Direction</label>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setDirection('long')}
                      className={cn(
                        'flex-1 py-2 rounded-lg font-medium transition-colors',
                        direction === 'long'
                          ? 'bg-[#22C55E] text-white'
                          : 'bg-[#1A1A1A] text-[#A0A0A0] hover:bg-[#222]'
                      )}
                    >
                      Long
                    </button>
                    <button
                      onClick={() => setDirection('short')}
                      className={cn(
                        'flex-1 py-2 rounded-lg font-medium transition-colors',
                        direction === 'short'
                          ? 'bg-[#EF4444] text-white'
                          : 'bg-[#1A1A1A] text-[#A0A0A0] hover:bg-[#222]'
                      )}
                    >
                      Short
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Entry Price</label>
                  <input
                    type="number"
                    value={entryPrice}
                    onChange={(e) => setEntryPrice(e.target.value)}
                    className="input"
                    placeholder="0.00"
                    step="0.25"
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Stop Loss</label>
                  <input
                    type="number"
                    value={stopLoss}
                    onChange={(e) => setStopLoss(e.target.value)}
                    className="input"
                    placeholder="0.00"
                    step="0.25"
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Take Profit (optional)</label>
                  <input
                    type="number"
                    value={takeProfit}
                    onChange={(e) => setTakeProfit(e.target.value)}
                    className="input"
                    placeholder="0.00"
                    step="0.25"
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Contracts</label>
                  <input
                    type="number"
                    value={contracts}
                    onChange={(e) => setContracts(e.target.value)}
                    className="input"
                    placeholder="1"
                    min="1"
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Setup Type</label>
                  <select
                    value={setupType}
                    onChange={(e) => setSetupType(e.target.value)}
                    className="input"
                  >
                    <option value="IFVG">IFVG</option>
                    <option value="FVG">FVG</option>
                    <option value="OB">Order Block</option>
                    <option value="BOS">Break of Structure</option>
                    <option value="Other">Other</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Grade</label>
                  <select
                    value={grade}
                    onChange={(e) => setGrade(e.target.value)}
                    className="input"
                  >
                    <option value="">Select grade...</option>
                    <option value="A+">A+ (Perfect setup)</option>
                    <option value="A">A (Strong setup)</option>
                    <option value="B">B (Decent setup)</option>
                    <option value="C">C (Weak setup)</option>
                  </select>
                </div>

                <div className="md:col-span-2">
                  <label className="block text-[#A0A0A0] text-sm mb-2">
                    Emotional State (1 = Calm, 5 = Very Emotional)
                  </label>
                  <div className="flex gap-2">
                    {[1, 2, 3, 4, 5].map((num) => (
                      <button
                        key={num}
                        onClick={() => setEmotionalState(num.toString())}
                        className={cn(
                          'flex-1 py-2 rounded-lg font-medium transition-colors',
                          emotionalState === num.toString()
                            ? num <= 2 
                              ? 'bg-[#22C55E] text-white' 
                              : num === 3 
                                ? 'bg-yellow-500 text-white'
                                : 'bg-[#EF4444] text-white'
                            : 'bg-[#1A1A1A] text-[#A0A0A0] hover:bg-[#222]'
                        )}
                      >
                        {num}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="md:col-span-2">
                  <label className="block text-[#A0A0A0] text-sm mb-2">Notes</label>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="input min-h-[80px]"
                    placeholder="Any observations about this setup..."
                  />
                </div>
              </div>
            </div>

            {rules.length > 0 && (
              <div className="card">
                <h2 className="text-white font-medium mb-4">Rules Checklist</h2>
                <div className="space-y-3">
                  {rules.map((rule) => (
                    <div key={rule.id} className="flex items-center justify-between p-3 bg-[#1A1A1A] rounded-lg">
                      <span className="text-white text-sm">{rule.name}</span>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleRuleToggle(rule.id, true)}
                          className={cn(
                            'px-3 py-1 rounded text-sm',
                            rulesFollowed.includes(rule.id)
                              ? 'bg-[#22C55E] text-white'
                              : 'bg-[#222] text-[#A0A0A0]'
                          )}
                        >
                          Followed
                        </button>
                        <button
                          onClick={() => handleRuleToggle(rule.id, false)}
                          className={cn(
                            'px-3 py-1 rounded text-sm',
                            rulesBroken.includes(rule.id)
                              ? 'bg-[#EF4444] text-white'
                              : 'bg-[#222] text-[#A0A0A0]'
                          )}
                        >
                          Broken
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {!validated && (
              <button
                onClick={validateSetup}
                className="btn-primary w-full py-3"
              >
                Validate Setup
              </button>
            )}

            {validated && (
              <div className="card">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-white font-medium">Validation Results</h2>
                  <span className={cn(
                    'px-3 py-1 rounded-full text-sm font-medium',
                    allPassed 
                      ? 'bg-[#22C55E]/20 text-[#22C55E]' 
                      : 'bg-[#EF4444]/20 text-[#EF4444]'
                  )}>
                    {passedCount}/{totalCount} Passed
                  </span>
                </div>
                <div className="space-y-2">
                  {validationResults.map((result, i) => (
                    <div
                      key={i}
                      className={cn(
                        'flex items-center gap-3 p-3 rounded-lg',
                        result.passed ? 'bg-[#22C55E]/10' : 'bg-[#EF4444]/10'
                      )}
                    >
                      {result.passed ? (
                        <CheckCircle className="w-5 h-5 text-[#22C55E] flex-shrink-0" />
                      ) : (
                        <XCircle className="w-5 h-5 text-[#EF4444] flex-shrink-0" />
                      )}
                      <span className={cn(
                        'text-sm',
                        result.passed ? 'text-[#22C55E]' : 'text-[#EF4444]'
                      )}>
                        {result.message}
                      </span>
                    </div>
                  ))}
                </div>

                {!allPassed && (
                  <div className="flex items-start gap-3 mt-4 p-3 bg-yellow-500/10 rounded-lg">
                    <AlertCircle className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                    <p className="text-yellow-500 text-sm">
                      Some checks failed. Review your setup or proceed with caution.
                    </p>
                  </div>
                )}

                <div className="flex gap-3 mt-6">
                  <button
                    onClick={saveTrade}
                    disabled={saving}
                    className="btn-primary flex-1"
                  >
                    {saving ? 'Saving...' : 'Save Validated Trade'}
                  </button>
                  <button
                    onClick={resetForm}
                    className="btn-secondary"
                  >
                    Reset
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
