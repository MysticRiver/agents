'use client'

import { useState, useEffect, useCallback } from 'react'
import { format } from 'date-fns'
import { Check } from 'lucide-react'
import TopBar from '@/components/TopBar'
import { useAuth } from '@/contexts/AuthContext'
import { formatCurrency, cn, DEFAULT_TRADING_RULES } from '@/lib/utils'

interface TradingRule {
  id: string
  name: string
  enabled: boolean
  value?: number | string
}

interface Settings {
  dailyLossLimit: number | null
  defaultInstrument: string
  timezone: string
  tradingRules: TradingRule[]
}

interface FundedAccount {
  id: string
  firmName: string
  accountSize: number
  profitTarget: number
  maxDrawdown: number
  currentPnl: number
  daysActive: number
  startDate: string
  isActive: boolean
}

export default function SettingsPage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<'general' | 'rules' | 'funded'>('general')
  
  const [settings, setSettings] = useState<Settings>({
    dailyLossLimit: null,
    defaultInstrument: 'NQ',
    timezone: 'America/New_York',
    tradingRules: DEFAULT_TRADING_RULES.map(r => ({ ...r }))
  })
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsSuccess, setSettingsSuccess] = useState(false)
  const [rulesSaving, setRulesSaving] = useState(false)
  const [rulesSuccess, setRulesSuccess] = useState(false)

  const [fundedAccount, setFundedAccount] = useState<FundedAccount | null>(null)
  const [fundedForm, setFundedForm] = useState({
    firmName: '',
    accountSize: '',
    profitTarget: '',
    maxDrawdown: '',
    startDate: format(new Date(), 'yyyy-MM-dd')
  })
  const [fundedSaving, setFundedSaving] = useState(false)

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch('/api/settings')
      const data = await res.json()
      if (data.settings) {
        let tradingRules = DEFAULT_TRADING_RULES.map(r => ({ ...r }))
        if (data.settings.tradingRules) {
          try {
            const savedRules = JSON.parse(data.settings.tradingRules)
            tradingRules = tradingRules.map(rule => {
              const saved = savedRules.find((r: TradingRule) => r.id === rule.id)
              if (saved) {
                return { ...rule, enabled: saved.enabled, value: saved.value ?? rule.value }
              }
              return rule
            })
          } catch {}
        }
        setSettings({
          dailyLossLimit: data.settings.dailyLossLimit,
          defaultInstrument: data.settings.defaultInstrument || 'NQ',
          timezone: data.settings.timezone || 'America/New_York',
          tradingRules
        })
      }
    } catch (error) {
      console.error('Failed to fetch settings:', error)
    }
  }, [])

  const fetchFundedAccount = useCallback(async () => {
    try {
      const res = await fetch('/api/funded-account')
      const data = await res.json()
      if (data.fundedAccount) {
        setFundedAccount(data.fundedAccount)
        setFundedForm({
          firmName: data.fundedAccount.firmName,
          accountSize: data.fundedAccount.accountSize.toString(),
          profitTarget: data.fundedAccount.profitTarget.toString(),
          maxDrawdown: data.fundedAccount.maxDrawdown.toString(),
          startDate: format(new Date(data.fundedAccount.startDate), 'yyyy-MM-dd')
        })
      }
    } catch (error) {
      console.error('Failed to fetch funded account:', error)
    }
  }, [])

  useEffect(() => {
    fetchSettings()
    fetchFundedAccount()
  }, [fetchSettings, fetchFundedAccount])

  const saveSettings = async () => {
    setSettingsSaving(true)
    setSettingsSuccess(false)
    try {
      await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dailyLossLimit: settings.dailyLossLimit,
          defaultInstrument: settings.defaultInstrument,
          timezone: settings.timezone
        })
      })
      setSettingsSuccess(true)
      setTimeout(() => setSettingsSuccess(false), 3000)
    } catch (error) {
      console.error('Failed to save settings:', error)
    } finally {
      setSettingsSaving(false)
    }
  }

  const saveTradingRules = async () => {
    setRulesSaving(true)
    setRulesSuccess(false)
    try {
      await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tradingRules: JSON.stringify(settings.tradingRules)
        })
      })
      setRulesSuccess(true)
      setTimeout(() => setRulesSuccess(false), 3000)
    } catch (error) {
      console.error('Failed to save trading rules:', error)
    } finally {
      setRulesSaving(false)
    }
  }

  const toggleRule = (ruleId: string) => {
    setSettings(prev => ({
      ...prev,
      tradingRules: prev.tradingRules.map(r =>
        r.id === ruleId ? { ...r, enabled: !r.enabled } : r
      )
    }))
  }

  const updateRuleValue = (ruleId: string, value: number | string) => {
    setSettings(prev => ({
      ...prev,
      tradingRules: prev.tradingRules.map(r =>
        r.id === ruleId ? { ...r, value } : r
      )
    }))
  }

  const saveFundedAccount = async (e: React.FormEvent) => {
    e.preventDefault()
    setFundedSaving(true)
    try {
      await fetch('/api/funded-account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          firmName: fundedForm.firmName,
          accountSize: parseFloat(fundedForm.accountSize),
          profitTarget: parseFloat(fundedForm.profitTarget),
          maxDrawdown: parseFloat(fundedForm.maxDrawdown),
          startDate: fundedForm.startDate
        })
      })
      fetchFundedAccount()
    } catch (error) {
      console.error('Failed to save funded account:', error)
    } finally {
      setFundedSaving(false)
    }
  }

  const deleteFundedAccount = async () => {
    if (!confirm('Are you sure you want to delete your funded account?')) return
    try {
      await fetch('/api/funded-account', { method: 'DELETE' })
      setFundedAccount(null)
      setFundedForm({
        firmName: '',
        accountSize: '',
        profitTarget: '',
        maxDrawdown: '',
        startDate: format(new Date(), 'yyyy-MM-dd')
      })
    } catch (error) {
      console.error('Failed to delete funded account:', error)
    }
  }

  const getRuleInput = (rule: TradingRule) => {
    switch (rule.id) {
      case 'maxTrades':
        return (
          <input
            type="number"
            value={rule.value || 2}
            onChange={(e) => updateRuleValue(rule.id, parseInt(e.target.value) || 2)}
            className="w-16 bg-[#0A0A0A] border border-[#1A1A1A] rounded px-2 py-1 text-white text-sm text-center"
            min="1"
            max="10"
          />
        )
      case 'minRR':
        return (
          <div className="flex items-center gap-1">
            <input
              type="number"
              value={rule.value || 2}
              onChange={(e) => updateRuleValue(rule.id, parseFloat(e.target.value) || 2)}
              className="w-16 bg-[#0A0A0A] border border-[#1A1A1A] rounded px-2 py-1 text-white text-sm text-center"
              min="1"
              max="5"
              step="0.5"
            />
            <span className="text-[#A0A0A0] text-sm">:1</span>
          </div>
        )
      case 'onlyInstrument':
        return (
          <select
            value={rule.value || 'NQ'}
            onChange={(e) => updateRuleValue(rule.id, e.target.value)}
            className="bg-[#0A0A0A] border border-[#1A1A1A] rounded px-2 py-1 text-white text-sm"
          >
            <option value="NQ">NQ</option>
            <option value="ES">ES</option>
            <option value="MNQ">MNQ</option>
          </select>
        )
      case 'stopAfterLosses':
        return (
          <input
            type="number"
            value={rule.value || 1}
            onChange={(e) => updateRuleValue(rule.id, parseInt(e.target.value) || 1)}
            className="w-16 bg-[#0A0A0A] border border-[#1A1A1A] rounded px-2 py-1 text-white text-sm text-center"
            min="1"
            max="5"
          />
        )
      default:
        return null
    }
  }

  return (
    <div>
      <TopBar breadcrumb={['Dashboard', 'Settings']} />
      
      <div className="p-4 md:p-6 max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-white text-2xl font-semibold">Settings</h1>
          <p className="text-[#A0A0A0] text-sm mt-1">
            Manage your account and trading preferences
          </p>
        </div>

        <div className="flex gap-2 mb-6 border-b border-[#1A1A1A]">
          <button
            onClick={() => setActiveTab('general')}
            className={cn(
              'px-4 py-3 text-sm font-medium border-b-2 transition-colors',
              activeTab === 'general'
                ? 'border-[#D42A2A] text-white'
                : 'border-transparent text-[#A0A0A0] hover:text-white'
            )}
          >
            General
          </button>
          <button
            onClick={() => setActiveTab('rules')}
            className={cn(
              'px-4 py-3 text-sm font-medium border-b-2 transition-colors',
              activeTab === 'rules'
                ? 'border-[#D42A2A] text-white'
                : 'border-transparent text-[#A0A0A0] hover:text-white'
            )}
          >
            Trading Rules
          </button>
          <button
            onClick={() => setActiveTab('funded')}
            className={cn(
              'px-4 py-3 text-sm font-medium border-b-2 transition-colors',
              activeTab === 'funded'
                ? 'border-[#D42A2A] text-white'
                : 'border-transparent text-[#A0A0A0] hover:text-white'
            )}
          >
            Funded Account
          </button>
        </div>

        {activeTab === 'general' && (
          <div className="space-y-6">
            <div className="card">
              <h2 className="text-white font-medium mb-4">Profile</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Name</label>
                  <input
                    type="text"
                    value={user?.name || ''}
                    className="input bg-[#1A1A1A]"
                    disabled
                  />
                </div>
                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Email</label>
                  <input
                    type="email"
                    value={user?.email || ''}
                    className="input bg-[#1A1A1A]"
                    disabled
                  />
                </div>
              </div>
            </div>

            <div className="card">
              <h2 className="text-white font-medium mb-4">Trading Preferences</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Daily Loss Limit ($)</label>
                  <input
                    type="number"
                    value={settings.dailyLossLimit || ''}
                    onChange={(e) => setSettings({
                      ...settings,
                      dailyLossLimit: e.target.value ? parseFloat(e.target.value) : null
                    })}
                    className="input"
                    placeholder="500"
                  />
                  <p className="text-[#A0A0A0] text-xs mt-1">
                    Set your daily loss limit to get reminders
                  </p>
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Default Instrument</label>
                  <select
                    value={settings.defaultInstrument}
                    onChange={(e) => setSettings({ ...settings, defaultInstrument: e.target.value })}
                    className="input"
                  >
                    <option value="NQ">NQ (Nasdaq)</option>
                    <option value="ES">ES (S&P 500)</option>
                    <option value="MNQ">MNQ (Micro Nasdaq)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[#A0A0A0] text-sm mb-2">Timezone</label>
                  <select
                    value={settings.timezone}
                    onChange={(e) => setSettings({ ...settings, timezone: e.target.value })}
                    className="input"
                  >
                    <option value="America/New_York">Eastern Time (ET)</option>
                    <option value="America/Chicago">Central Time (CT)</option>
                    <option value="America/Denver">Mountain Time (MT)</option>
                    <option value="America/Los_Angeles">Pacific Time (PT)</option>
                    <option value="UTC">UTC</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-3 mt-6">
                <button
                  onClick={saveSettings}
                  disabled={settingsSaving}
                  className="btn-primary"
                >
                  {settingsSaving ? 'Saving...' : 'Save Changes'}
                </button>
                {settingsSuccess && (
                  <span className="text-[#22C55E] text-sm flex items-center gap-1">
                    <Check className="w-4 h-4" />
                    Saved
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'rules' && (
          <div className="space-y-6">
            <div className="card">
              <h2 className="text-white font-medium mb-2">Trading Rules Tracker</h2>
              <p className="text-[#A0A0A0] text-sm mb-4">
                Toggle rules on/off. The app auto-monitors compliance from your logged trades and validations. Results display in the Dashboard Rules Compliance card.
              </p>

              <div className="space-y-2">
                {settings.tradingRules.map((rule) => (
                  <div
                    key={rule.id}
                    className={cn(
                      'flex items-center justify-between p-3 rounded-lg transition-colors',
                      rule.enabled ? 'bg-[#1A1A1A]' : 'bg-[#141414]'
                    )}
                  >
                    <div className="flex items-center gap-3 flex-1">
                      <button
                        onClick={() => toggleRule(rule.id)}
                        className={cn(
                          'w-10 h-6 rounded-full relative transition-colors',
                          rule.enabled ? 'bg-[#D42A2A]' : 'bg-[#333]'
                        )}
                      >
                        <span
                          className={cn(
                            'absolute top-1 w-4 h-4 rounded-full bg-white transition-transform',
                            rule.enabled ? 'left-5' : 'left-1'
                          )}
                        />
                      </button>
                      <span className={cn(
                        'text-sm',
                        rule.enabled ? 'text-white' : 'text-[#A0A0A0]'
                      )}>
                        {rule.name}
                      </span>
                    </div>
                    {rule.enabled && getRuleInput(rule)}
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-3 mt-6">
                <button
                  onClick={saveTradingRules}
                  disabled={rulesSaving}
                  className="btn-primary"
                >
                  {rulesSaving ? 'Saving...' : 'Save Rules'}
                </button>
                {rulesSuccess && (
                  <span className="text-[#22C55E] text-sm flex items-center gap-1">
                    <Check className="w-4 h-4" />
                    Saved
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'funded' && (
          <div className="space-y-6">
            <div className="card">
              <h2 className="text-white font-medium mb-4">Funded Account Tracking</h2>
              <p className="text-[#A0A0A0] text-sm mb-4">
                Track your progress on a funded trading account
              </p>

              <form onSubmit={saveFundedAccount} className="space-y-4">
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[#A0A0A0] text-sm mb-2">Firm Name</label>
                    <input
                      type="text"
                      value={fundedForm.firmName}
                      onChange={(e) => setFundedForm({ ...fundedForm, firmName: e.target.value })}
                      className="input"
                      placeholder="Apex, Topstep, etc."
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-[#A0A0A0] text-sm mb-2">Account Size ($)</label>
                    <input
                      type="number"
                      value={fundedForm.accountSize}
                      onChange={(e) => setFundedForm({ ...fundedForm, accountSize: e.target.value })}
                      className="input"
                      placeholder="50000"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-[#A0A0A0] text-sm mb-2">Profit Target ($)</label>
                    <input
                      type="number"
                      value={fundedForm.profitTarget}
                      onChange={(e) => setFundedForm({ ...fundedForm, profitTarget: e.target.value })}
                      className="input"
                      placeholder="3000"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-[#A0A0A0] text-sm mb-2">Max Drawdown ($)</label>
                    <input
                      type="number"
                      value={fundedForm.maxDrawdown}
                      onChange={(e) => setFundedForm({ ...fundedForm, maxDrawdown: e.target.value })}
                      className="input"
                      placeholder="2500"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-[#A0A0A0] text-sm mb-2">Start Date</label>
                    <input
                      type="date"
                      value={fundedForm.startDate}
                      onChange={(e) => setFundedForm({ ...fundedForm, startDate: e.target.value })}
                      className="input"
                      required
                    />
                  </div>
                </div>

                <div className="flex gap-3">
                  <button
                    type="submit"
                    disabled={fundedSaving}
                    className="btn-primary"
                  >
                    {fundedSaving ? 'Saving...' : fundedAccount ? 'Update Account' : 'Set Up Account'}
                  </button>
                  {fundedAccount && (
                    <button
                      type="button"
                      onClick={deleteFundedAccount}
                      className="btn-secondary text-[#EF4444]"
                    >
                      Delete Account
                    </button>
                  )}
                </div>
              </form>
            </div>

            {fundedAccount && (
              <div className="card">
                <h2 className="text-white font-medium mb-4">Current Status</h2>
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="p-4 bg-[#1A1A1A] rounded-lg">
                    <p className="text-[#A0A0A0] text-sm">Account</p>
                    <p className="text-white font-medium">{fundedAccount.firmName}</p>
                    <p className="text-[#A0A0A0] text-xs">{formatCurrency(fundedAccount.accountSize)}</p>
                  </div>
                  <div className="p-4 bg-[#1A1A1A] rounded-lg">
                    <p className="text-[#A0A0A0] text-sm">Current P&L</p>
                    <p className={cn(
                      'font-medium text-xl',
                      fundedAccount.currentPnl >= 0 ? 'text-[#22C55E]' : 'text-[#EF4444]'
                    )}>
                      {formatCurrency(fundedAccount.currentPnl)}
                    </p>
                  </div>
                  <div className="p-4 bg-[#1A1A1A] rounded-lg">
                    <p className="text-[#A0A0A0] text-sm">Profit Target</p>
                    <p className="text-white font-medium">{formatCurrency(fundedAccount.profitTarget)}</p>
                    <div className="mt-2 h-2 bg-[#222] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#22C55E] rounded-full"
                        style={{
                          width: `${Math.min(100, Math.max(0, (fundedAccount.currentPnl / fundedAccount.profitTarget) * 100))}%`
                        }}
                      />
                    </div>
                  </div>
                  <div className="p-4 bg-[#1A1A1A] rounded-lg">
                    <p className="text-[#A0A0A0] text-sm">Drawdown Remaining</p>
                    <p className="text-white font-medium">
                      {formatCurrency(fundedAccount.maxDrawdown + Math.min(0, fundedAccount.currentPnl))}
                    </p>
                    <div className="mt-2 h-2 bg-[#222] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#EF4444] rounded-full"
                        style={{
                          width: `${Math.max(0, 100 - ((fundedAccount.maxDrawdown + Math.min(0, fundedAccount.currentPnl)) / fundedAccount.maxDrawdown) * 100)}%`
                        }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
