'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import TopBar from '@/components/TopBar'
import { formatCurrency, getContractValue, cn } from '@/lib/utils'

export default function CalculatorPage() {
  const [instrument, setInstrument] = useState('NQ')
  const [accountSize, setAccountSize] = useState('')
  const [riskPercent, setRiskPercent] = useState('1')
  const [riskDollars, setRiskDollars] = useState('')
  const [entryPrice, setEntryPrice] = useState('')
  const [stopLoss, setStopLoss] = useState('')
  const [takeProfit, setTakeProfit] = useState('')
  const [direction, setDirection] = useState<'long' | 'short'>('long')
  
  const [usePercent, setUsePercent] = useState(true)

  const contractInfo = getContractValue(instrument)
  
  const entry = parseFloat(entryPrice) || 0
  const stop = parseFloat(stopLoss) || 0
  const target = parseFloat(takeProfit) || 0
  const account = parseFloat(accountSize) || 0
  
  const riskAmount = usePercent 
    ? (account * (parseFloat(riskPercent) || 0) / 100)
    : (parseFloat(riskDollars) || 0)
  
  const stopDistancePoints = Math.abs(entry - stop)
  const stopDistanceTicks = stopDistancePoints * contractInfo.ticksPerPoint
  const riskPerContract = stopDistancePoints * contractInfo.pointValue
  
  const targetDistancePoints = target ? Math.abs(target - entry) : 0
  const rewardPerContract = targetDistancePoints * contractInfo.pointValue
  
  const maxContracts = riskPerContract > 0 ? Math.floor(riskAmount / riskPerContract) : 0
  const actualRisk = maxContracts * riskPerContract
  const potentialReward = maxContracts * rewardPerContract
  
  const rrRatio = riskPerContract > 0 && rewardPerContract > 0 
    ? (rewardPerContract / riskPerContract) 
    : 0

  const breakEvenPoints = stopDistancePoints / (rrRatio || 1)

  return (
    <div>
      <TopBar breadcrumb={['Dashboard', 'Position Size & Risk Calculator']} />
      
      <div className="p-4 md:p-6 max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-white text-2xl font-semibold">Position Size & Risk Calculator</h1>
          <p className="text-[#A0A0A0] text-sm mt-1">
            Calculate your position size based on risk tolerance
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          <div className="space-y-6">
            <div className="card">
              <h2 className="text-white font-medium mb-4">Account & Risk</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Account Size ($)</label>
                  <input
                    type="number"
                    value={accountSize}
                    onChange={(e) => setAccountSize(e.target.value)}
                    className="input"
                    placeholder="50000"
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Risk Amount</label>
                  <div className="flex gap-2 mb-2">
                    <button
                      onClick={() => setUsePercent(true)}
                      className={cn(
                        'flex-1 py-2 rounded-lg text-sm font-medium',
                        usePercent 
                          ? 'bg-[#D42A2A] text-white' 
                          : 'bg-[#1A1A1A] text-[#A0A0A0]'
                      )}
                    >
                      Percentage
                    </button>
                    <button
                      onClick={() => setUsePercent(false)}
                      className={cn(
                        'flex-1 py-2 rounded-lg text-sm font-medium',
                        !usePercent 
                          ? 'bg-[#D42A2A] text-white' 
                          : 'bg-[#1A1A1A] text-[#A0A0A0]'
                      )}
                    >
                      Dollars
                    </button>
                  </div>
                  {usePercent ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        value={riskPercent}
                        onChange={(e) => setRiskPercent(e.target.value)}
                        className="input"
                        placeholder="1"
                        step="0.25"
                        min="0"
                        max="100"
                      />
                      <span className="text-[#A0A0A0]">%</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-[#A0A0A0]">$</span>
                      <input
                        type="number"
                        value={riskDollars}
                        onChange={(e) => setRiskDollars(e.target.value)}
                        className="input"
                        placeholder="500"
                      />
                    </div>
                  )}
                </div>

                {riskAmount > 0 && (
                  <div className="p-3 bg-[#1A1A1A] rounded-lg">
                    <p className="text-[#A0A0A0] text-sm">Max Risk Amount</p>
                    <p className="text-white text-xl font-semibold">
                      {formatCurrency(riskAmount)}
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="card">
              <h2 className="text-white font-medium mb-4">Trade Setup</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Instrument</label>
                  <select
                    value={instrument}
                    onChange={(e) => setInstrument(e.target.value)}
                    className="input"
                  >
                    <option value="NQ">NQ - ${contractInfo.pointValue}/point, ${contractInfo.tickValue}/tick</option>
                    <option value="ES">ES - $50/point, $12.50/tick</option>
                    <option value="MNQ">MNQ - $2/point, $0.50/tick</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Direction</label>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setDirection('long')}
                      className={cn(
                        'flex-1 py-2 rounded-lg font-medium',
                        direction === 'long'
                          ? 'bg-[#22C55E] text-white'
                          : 'bg-[#1A1A1A] text-[#A0A0A0]'
                      )}
                    >
                      Long
                    </button>
                    <button
                      onClick={() => setDirection('short')}
                      className={cn(
                        'flex-1 py-2 rounded-lg font-medium',
                        direction === 'short'
                          ? 'bg-[#EF4444] text-white'
                          : 'bg-[#1A1A1A] text-[#A0A0A0]'
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
                    placeholder="18500.00"
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
                    placeholder={direction === 'long' ? '18480.00' : '18520.00'}
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
                    placeholder={direction === 'long' ? '18560.00' : '18440.00'}
                    step="0.25"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="card border-l-2 border-l-[#D42A2A]">
              <h2 className="text-white font-medium mb-4">Position Size</h2>
              
              {entry > 0 && stop > 0 ? (
                <div className="space-y-4">
                  <div className="text-center py-4 bg-[#1A1A1A] rounded-lg">
                    <p className="text-[#A0A0A0] text-sm mb-1">Max Contracts</p>
                    <p className="text-white text-4xl font-bold">{maxContracts}</p>
                    <p className="text-[#A0A0A0] text-xs mt-1">
                      Based on {formatCurrency(riskAmount)} max risk
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 bg-[#1A1A1A] rounded-lg">
                      <p className="text-[#A0A0A0] text-xs">Stop Distance</p>
                      <p className="text-white font-medium">{stopDistancePoints.toFixed(2)} pts</p>
                      <p className="text-[#A0A0A0] text-xs">{stopDistanceTicks.toFixed(0)} ticks</p>
                    </div>
                    <div className="p-3 bg-[#1A1A1A] rounded-lg">
                      <p className="text-[#A0A0A0] text-xs">Risk/Contract</p>
                      <p className="text-[#EF4444] font-medium">{formatCurrency(riskPerContract)}</p>
                    </div>
                    <div className="p-3 bg-[#1A1A1A] rounded-lg">
                      <p className="text-[#A0A0A0] text-xs">Actual Risk</p>
                      <p className="text-[#EF4444] font-medium">{formatCurrency(actualRisk)}</p>
                    </div>
                    {target > 0 && (
                      <div className="p-3 bg-[#1A1A1A] rounded-lg">
                        <p className="text-[#A0A0A0] text-xs">Potential Reward</p>
                        <p className="text-[#22C55E] font-medium">{formatCurrency(potentialReward)}</p>
                      </div>
                    )}
                  </div>

                  {rrRatio > 0 && (
                    <div className={cn(
                      'p-4 rounded-lg text-center',
                      rrRatio >= 1.5 ? 'bg-[#22C55E]/10' : 'bg-[#EF4444]/10'
                    )}>
                      <p className="text-[#A0A0A0] text-sm mb-1">Risk:Reward Ratio</p>
                      <p className={cn(
                        'text-2xl font-bold',
                        rrRatio >= 1.5 ? 'text-[#22C55E]' : 'text-[#EF4444]'
                      )}>
                        1:{rrRatio.toFixed(2)}
                      </p>
                      {rrRatio < 1.5 && (
                        <p className="text-[#EF4444] text-xs mt-2">
                          R:R below 1.5 - consider adjusting
                        </p>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-8">
                  <p className="text-[#A0A0A0]">
                    Enter entry and stop loss to calculate position size
                  </p>
                </div>
              )}
            </div>

            <div className="card">
              <h2 className="text-white font-medium mb-4">Contract Values Reference</h2>
              <div className="space-y-3">
                <div className="flex justify-between items-center p-3 bg-[#1A1A1A] rounded-lg">
                  <div>
                    <p className="text-white font-medium">NQ (Nasdaq)</p>
                    <p className="text-[#A0A0A0] text-xs">E-mini Nasdaq-100</p>
                  </div>
                  <div className="text-right">
                    <p className="text-white text-sm">$20/point</p>
                    <p className="text-[#A0A0A0] text-xs">$5/tick</p>
                  </div>
                </div>
                <div className="flex justify-between items-center p-3 bg-[#1A1A1A] rounded-lg">
                  <div>
                    <p className="text-white font-medium">ES (S&P 500)</p>
                    <p className="text-[#A0A0A0] text-xs">E-mini S&P 500</p>
                  </div>
                  <div className="text-right">
                    <p className="text-white text-sm">$50/point</p>
                    <p className="text-[#A0A0A0] text-xs">$12.50/tick</p>
                  </div>
                </div>
                <div className="flex justify-between items-center p-3 bg-[#1A1A1A] rounded-lg">
                  <div>
                    <p className="text-white font-medium">MNQ (Micro Nasdaq)</p>
                    <p className="text-[#A0A0A0] text-xs">Micro E-mini Nasdaq-100</p>
                  </div>
                  <div className="text-right">
                    <p className="text-white text-sm">$2/point</p>
                    <p className="text-[#A0A0A0] text-xs">$0.50/tick</p>
                  </div>
                </div>
              </div>
            </div>

            {entry > 0 && stop > 0 && maxContracts > 0 && (
              <Link
                href={`/validator?instrument=${instrument}&direction=${direction}&entry=${entryPrice}&stop=${stopLoss}&target=${takeProfit}&contracts=${maxContracts}`}
                className="btn-primary w-full flex items-center justify-center"
              >
                Validate This Setup
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
