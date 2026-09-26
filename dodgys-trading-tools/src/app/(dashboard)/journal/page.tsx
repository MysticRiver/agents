'use client'

import { useState, useEffect, useCallback } from 'react'
import { format } from 'date-fns'
import { ArrowUp, ArrowDown, Filter, Plus, X, Trash2, Edit2, Check, Shield, ShieldOff } from 'lucide-react'
import TopBar from '@/components/TopBar'
import { formatCurrency, cn, calculatePnl, getContractValue } from '@/lib/utils'

interface Trade {
  id: string
  date: string
  instrument: string
  direction: string
  entryPrice: number
  exitPrice: number | null
  stopLoss: number | null
  takeProfit: number | null
  contracts: number
  pnl: number | null
  pnlPoints: number | null
  grade: string | null
  setupType: string | null
  validated: boolean
  emotionalState: number | null
  notes: string | null
}

export default function JournalPage() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingTrade, setEditingTrade] = useState<Trade | null>(null)
  const [filterInstrument, setFilterInstrument] = useState('')
  const [filterDirection, setFilterDirection] = useState('')
  const [filterValidated, setFilterValidated] = useState('')
  const [showFilters, setShowFilters] = useState(false)

  const [formData, setFormData] = useState({
    date: format(new Date(), 'yyyy-MM-dd'),
    instrument: 'NQ',
    direction: 'long',
    entryPrice: '',
    exitPrice: '',
    stopLoss: '',
    takeProfit: '',
    contracts: '1',
    grade: '',
    setupType: 'IFVG',
    emotionalState: '1',
    notes: '',
    validated: false
  })

  const fetchTrades = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/trades?limit=100')
      const data = await res.json()
      setTrades(data.trades || [])
    } catch (error) {
      console.error('Failed to fetch trades:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchTrades()
  }, [fetchTrades])

  const resetForm = () => {
    setFormData({
      date: format(new Date(), 'yyyy-MM-dd'),
      instrument: 'NQ',
      direction: 'long',
      entryPrice: '',
      exitPrice: '',
      stopLoss: '',
      takeProfit: '',
      contracts: '1',
      grade: '',
      setupType: 'IFVG',
      emotionalState: '1',
      notes: '',
      validated: false
    })
    setEditingTrade(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    const entry = parseFloat(formData.entryPrice)
    const exit = formData.exitPrice ? parseFloat(formData.exitPrice) : null
    const contracts = parseInt(formData.contracts)
    
    let pnl = null
    let pnlPoints = null
    
    if (exit !== null) {
      const result = calculatePnl(
        formData.instrument,
        formData.direction as 'long' | 'short',
        entry,
        exit,
        contracts
      )
      pnl = result.pnl
      pnlPoints = result.pnlPoints
    }

    const tradeData = {
      date: new Date(formData.date).toISOString(),
      instrument: formData.instrument,
      direction: formData.direction,
      entryPrice: entry,
      exitPrice: exit,
      stopLoss: formData.stopLoss ? parseFloat(formData.stopLoss) : null,
      takeProfit: formData.takeProfit ? parseFloat(formData.takeProfit) : null,
      contracts,
      pnl,
      pnlPoints,
      grade: formData.grade || null,
      setupType: formData.setupType,
      emotionalState: parseInt(formData.emotionalState),
      notes: formData.notes || null,
      validated: formData.validated
    }

    try {
      if (editingTrade) {
        await fetch(`/api/trades/${editingTrade.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(tradeData)
        })
      } else {
        await fetch('/api/trades', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(tradeData)
        })
      }
      
      setShowAddModal(false)
      resetForm()
      fetchTrades()
    } catch (error) {
      console.error('Failed to save trade:', error)
    }
  }

  const deleteTrade = async (id: string) => {
    if (!confirm('Are you sure you want to delete this trade?')) return
    
    try {
      await fetch(`/api/trades/${id}`, { method: 'DELETE' })
      fetchTrades()
    } catch (error) {
      console.error('Failed to delete trade:', error)
    }
  }

  const editTrade = (trade: Trade) => {
    setEditingTrade(trade)
    setFormData({
      date: format(new Date(trade.date), 'yyyy-MM-dd'),
      instrument: trade.instrument,
      direction: trade.direction,
      entryPrice: trade.entryPrice.toString(),
      exitPrice: trade.exitPrice?.toString() || '',
      stopLoss: trade.stopLoss?.toString() || '',
      takeProfit: trade.takeProfit?.toString() || '',
      contracts: trade.contracts.toString(),
      grade: trade.grade || '',
      setupType: trade.setupType || 'IFVG',
      emotionalState: trade.emotionalState?.toString() || '1',
      notes: trade.notes || '',
      validated: trade.validated
    })
    setShowAddModal(true)
  }

  const filteredTrades = trades.filter(trade => {
    if (filterInstrument && trade.instrument !== filterInstrument) return false
    if (filterDirection && trade.direction !== filterDirection) return false
    if (filterValidated === 'yes' && !trade.validated) return false
    if (filterValidated === 'no' && trade.validated) return false
    return true
  })

  const totalPnl = filteredTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
  const winCount = filteredTrades.filter(t => (t.pnl || 0) > 0).length
  const lossCount = filteredTrades.filter(t => (t.pnl || 0) < 0).length

  return (
    <div>
      <TopBar breadcrumb={['Dashboard', 'Trading Journal']} />
      
      <div className="p-4 md:p-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
          <div>
            <h1 className="text-white text-2xl font-semibold">Trading Journal</h1>
            <p className="text-[#A0A0A0] text-sm mt-1">
              Track and review all your trades
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={cn(
                'btn-secondary flex items-center gap-2',
                showFilters && 'bg-[#1A1A1A]'
              )}
            >
              <Filter className="w-4 h-4" />
              Filters
            </button>
            <button
              onClick={() => {
                resetForm()
                setShowAddModal(true)
              }}
              className="btn-primary flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Add Trade
            </button>
          </div>
        </div>

        {showFilters && (
          <div className="card mb-6">
            <div className="grid md:grid-cols-4 gap-4">
              <div>
                <label className="block text-[#A0A0A0] text-sm mb-2">Instrument</label>
                <select
                  value={filterInstrument}
                  onChange={(e) => setFilterInstrument(e.target.value)}
                  className="input"
                >
                  <option value="">All</option>
                  <option value="NQ">NQ</option>
                  <option value="ES">ES</option>
                  <option value="MNQ">MNQ</option>
                </select>
              </div>
              <div>
                <label className="block text-[#A0A0A0] text-sm mb-2">Direction</label>
                <select
                  value={filterDirection}
                  onChange={(e) => setFilterDirection(e.target.value)}
                  className="input"
                >
                  <option value="">All</option>
                  <option value="long">Long</option>
                  <option value="short">Short</option>
                </select>
              </div>
              <div>
                <label className="block text-[#A0A0A0] text-sm mb-2">Validated</label>
                <select
                  value={filterValidated}
                  onChange={(e) => setFilterValidated(e.target.value)}
                  className="input"
                >
                  <option value="">All</option>
                  <option value="yes">Validated</option>
                  <option value="no">Not Validated</option>
                </select>
              </div>
              <div className="flex items-end">
                <button
                  onClick={() => {
                    setFilterInstrument('')
                    setFilterDirection('')
                    setFilterValidated('')
                  }}
                  className="btn-secondary w-full"
                >
                  Clear Filters
                </button>
              </div>
            </div>
          </div>
        )}

        {trades.length > 0 && (
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="card">
              <p className="text-[#A0A0A0] text-sm">Total P&L</p>
              <p className={cn(
                'text-xl font-semibold',
                totalPnl > 0 ? 'text-[#22C55E]' : totalPnl < 0 ? 'text-[#EF4444]' : 'text-white'
              )}>
                {formatCurrency(totalPnl)}
              </p>
            </div>
            <div className="card">
              <p className="text-[#A0A0A0] text-sm">Wins</p>
              <p className="text-xl font-semibold text-[#22C55E]">{winCount}</p>
            </div>
            <div className="card">
              <p className="text-[#A0A0A0] text-sm">Losses</p>
              <p className="text-xl font-semibold text-[#EF4444]">{lossCount}</p>
            </div>
          </div>
        )}

        <div className="card">
          {loading ? (
            <div className="text-center py-12">
              <p className="text-[#A0A0A0]">Loading trades...</p>
            </div>
          ) : filteredTrades.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-[#A0A0A0]">
                {trades.length === 0 
                  ? "No trades logged yet. Click 'Add Trade' to record your first trade."
                  : "No trades match your filters."
                }
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-[#A0A0A0] text-sm text-left border-b border-[#1A1A1A]">
                    <th className="pb-3 font-medium">Date</th>
                    <th className="pb-3 font-medium">Instrument</th>
                    <th className="pb-3 font-medium">Direction</th>
                    <th className="pb-3 font-medium">Entry</th>
                    <th className="pb-3 font-medium">Exit</th>
                    <th className="pb-3 font-medium">P&L</th>
                    <th className="pb-3 font-medium">Grade</th>
                    <th className="pb-3 font-medium">Validated</th>
                    <th className="pb-3 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTrades.map((trade) => (
                    <tr key={trade.id} className="border-t border-[#1A1A1A]">
                      <td className="py-3 text-white text-sm">
                        {format(new Date(trade.date), 'MMM d, yyyy')}
                      </td>
                      <td className="py-3 text-white text-sm">{trade.instrument}</td>
                      <td className="py-3">
                        <span className={cn(
                          'flex items-center gap-1 text-sm',
                          trade.direction === 'long' ? 'text-[#22C55E]' : 'text-[#EF4444]'
                        )}>
                          {trade.direction === 'long' ? (
                            <ArrowUp className="w-3 h-3" />
                          ) : (
                            <ArrowDown className="w-3 h-3" />
                          )}
                          {trade.direction}
                        </span>
                      </td>
                      <td className="py-3 text-white text-sm">{trade.entryPrice.toFixed(2)}</td>
                      <td className="py-3 text-white text-sm">
                        {trade.exitPrice?.toFixed(2) || '-'}
                      </td>
                      <td className={cn(
                        'py-3 text-sm font-medium',
                        (trade.pnl || 0) > 0 ? 'text-[#22C55E]' : 
                        (trade.pnl || 0) < 0 ? 'text-[#EF4444]' : 'text-[#A0A0A0]'
                      )}>
                        {trade.pnl !== null ? formatCurrency(trade.pnl) : '-'}
                      </td>
                      <td className="py-3 text-white text-sm">{trade.grade || '-'}</td>
                      <td className="py-3">
                        {trade.validated ? (
                          <Shield className="w-4 h-4 text-[#22C55E]" />
                        ) : (
                          <ShieldOff className="w-4 h-4 text-[#A0A0A0]" />
                        )}
                      </td>
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => editTrade(trade)}
                            className="p-1 text-[#A0A0A0] hover:text-white"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => deleteTrade(trade.id)}
                            className="p-1 text-[#A0A0A0] hover:text-[#EF4444]"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="card w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-white text-xl font-semibold">
                {editingTrade ? 'Edit Trade' : 'Add Trade'}
              </h2>
              <button
                onClick={() => {
                  setShowAddModal(false)
                  resetForm()
                }}
                className="text-[#A0A0A0] hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Date</label>
                  <input
                    type="date"
                    value={formData.date}
                    onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                    className="input"
                    required
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Instrument</label>
                  <select
                    value={formData.instrument}
                    onChange={(e) => setFormData({ ...formData, instrument: e.target.value })}
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
                      type="button"
                      onClick={() => setFormData({ ...formData, direction: 'long' })}
                      className={cn(
                        'flex-1 py-2 rounded-lg font-medium transition-colors',
                        formData.direction === 'long'
                          ? 'bg-[#22C55E] text-white'
                          : 'bg-[#1A1A1A] text-[#A0A0A0]'
                      )}
                    >
                      Long
                    </button>
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, direction: 'short' })}
                      className={cn(
                        'flex-1 py-2 rounded-lg font-medium transition-colors',
                        formData.direction === 'short'
                          ? 'bg-[#EF4444] text-white'
                          : 'bg-[#1A1A1A] text-[#A0A0A0]'
                      )}
                    >
                      Short
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Contracts</label>
                  <input
                    type="number"
                    value={formData.contracts}
                    onChange={(e) => setFormData({ ...formData, contracts: e.target.value })}
                    className="input"
                    min="1"
                    required
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Entry Price</label>
                  <input
                    type="number"
                    value={formData.entryPrice}
                    onChange={(e) => setFormData({ ...formData, entryPrice: e.target.value })}
                    className="input"
                    step="0.25"
                    required
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Exit Price</label>
                  <input
                    type="number"
                    value={formData.exitPrice}
                    onChange={(e) => setFormData({ ...formData, exitPrice: e.target.value })}
                    className="input"
                    step="0.25"
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Stop Loss</label>
                  <input
                    type="number"
                    value={formData.stopLoss}
                    onChange={(e) => setFormData({ ...formData, stopLoss: e.target.value })}
                    className="input"
                    step="0.25"
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Take Profit</label>
                  <input
                    type="number"
                    value={formData.takeProfit}
                    onChange={(e) => setFormData({ ...formData, takeProfit: e.target.value })}
                    className="input"
                    step="0.25"
                  />
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Setup Type</label>
                  <select
                    value={formData.setupType}
                    onChange={(e) => setFormData({ ...formData, setupType: e.target.value })}
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
                    value={formData.grade}
                    onChange={(e) => setFormData({ ...formData, grade: e.target.value })}
                    className="input"
                  >
                    <option value="">No grade</option>
                    <option value="A+">A+</option>
                    <option value="A">A</option>
                    <option value="B">B</option>
                    <option value="C">C</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Emotional State (1-5)</label>
                  <select
                    value={formData.emotionalState}
                    onChange={(e) => setFormData({ ...formData, emotionalState: e.target.value })}
                    className="input"
                  >
                    <option value="1">1 - Calm</option>
                    <option value="2">2 - Slightly anxious</option>
                    <option value="3">3 - Moderate</option>
                    <option value="4">4 - Elevated</option>
                    <option value="5">5 - Very emotional</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Validated</label>
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, validated: !formData.validated })}
                    className={cn(
                      'w-full py-2 rounded-lg font-medium flex items-center justify-center gap-2',
                      formData.validated
                        ? 'bg-[#22C55E] text-white'
                        : 'bg-[#1A1A1A] text-[#A0A0A0]'
                    )}
                  >
                    {formData.validated ? <Check className="w-4 h-4" /> : null}
                    {formData.validated ? 'Validated' : 'Not Validated'}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-[#A0A0A0] text-sm mb-2">Notes</label>
                <textarea
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  className="input min-h-[80px]"
                  placeholder="Trade notes..."
                />
              </div>

              <div className="flex gap-3">
                <button type="submit" className="btn-primary flex-1">
                  {editingTrade ? 'Update Trade' : 'Add Trade'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowAddModal(false)
                    resetForm()
                  }}
                  className="btn-secondary"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
