'use client'

import { useState, useEffect, useCallback } from 'react'
import { format } from 'date-fns'
import { Plus, Trash2, Check, X } from 'lucide-react'
import TopBar from '@/components/TopBar'
import { useAuth } from '@/contexts/AuthContext'
import { formatCurrency, cn } from '@/lib/utils'

interface Rule {
  id: string
  name: string
  description: string | null
  isActive: boolean
}

interface Settings {
  dailyLossLimit: number | null
  defaultInstrument: string
  timezone: string
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
    timezone: 'America/New_York'
  })
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsSuccess, setSettingsSuccess] = useState(false)

  const [rules, setRules] = useState<Rule[]>([])
  const [newRuleName, setNewRuleName] = useState('')
  const [newRuleDescription, setNewRuleDescription] = useState('')
  const [addingRule, setAddingRule] = useState(false)

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
        setSettings({
          dailyLossLimit: data.settings.dailyLossLimit,
          defaultInstrument: data.settings.defaultInstrument || 'NQ',
          timezone: data.settings.timezone || 'America/New_York'
        })
      }
    } catch (error) {
      console.error('Failed to fetch settings:', error)
    }
  }, [])

  const fetchRules = useCallback(async () => {
    try {
      const res = await fetch('/api/rules')
      const data = await res.json()
      setRules(data.rules || [])
    } catch (error) {
      console.error('Failed to fetch rules:', error)
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
    fetchRules()
    fetchFundedAccount()
  }, [fetchSettings, fetchRules, fetchFundedAccount])

  const saveSettings = async () => {
    setSettingsSaving(true)
    setSettingsSuccess(false)
    try {
      await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      })
      setSettingsSuccess(true)
      setTimeout(() => setSettingsSuccess(false), 3000)
    } catch (error) {
      console.error('Failed to save settings:', error)
    } finally {
      setSettingsSaving(false)
    }
  }

  const addRule = async () => {
    if (!newRuleName.trim()) return
    setAddingRule(true)
    try {
      await fetch('/api/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newRuleName,
          description: newRuleDescription || null
        })
      })
      setNewRuleName('')
      setNewRuleDescription('')
      fetchRules()
    } catch (error) {
      console.error('Failed to add rule:', error)
    } finally {
      setAddingRule(false)
    }
  }

  const toggleRule = async (rule: Rule) => {
    try {
      await fetch(`/api/rules/${rule.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ isActive: !rule.isActive })
      })
      fetchRules()
    } catch (error) {
      console.error('Failed to toggle rule:', error)
    }
  }

  const deleteRule = async (id: string) => {
    if (!confirm('Are you sure you want to delete this rule?')) return
    try {
      await fetch(`/api/rules/${id}`, { method: 'DELETE' })
      fetchRules()
    } catch (error) {
      console.error('Failed to delete rule:', error)
    }
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
              <h2 className="text-white font-medium mb-4">Your Trading Rules</h2>
              <p className="text-[#A0A0A0] text-sm mb-4">
                Add rules to track compliance in the Trade Validator and Dashboard
              </p>

              <div className="space-y-3 mb-6">
                {rules.length === 0 ? (
                  <p className="text-[#A0A0A0] text-sm py-4 text-center">
                    No rules defined yet. Add your first trading rule below.
                  </p>
                ) : (
                  rules.map((rule) => (
                    <div
                      key={rule.id}
                      className={cn(
                        'flex items-center justify-between p-3 rounded-lg',
                        rule.isActive ? 'bg-[#1A1A1A]' : 'bg-[#1A1A1A]/50'
                      )}
                    >
                      <div className="flex-1">
                        <p className={cn(
                          'font-medium',
                          rule.isActive ? 'text-white' : 'text-[#A0A0A0]'
                        )}>
                          {rule.name}
                        </p>
                        {rule.description && (
                          <p className="text-[#A0A0A0] text-xs mt-1">{rule.description}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleRule(rule)}
                          className={cn(
                            'p-2 rounded',
                            rule.isActive 
                              ? 'bg-[#22C55E]/20 text-[#22C55E]' 
                              : 'bg-[#A0A0A0]/20 text-[#A0A0A0]'
                          )}
                        >
                          {rule.isActive ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                        </button>
                        <button
                          onClick={() => deleteRule(rule.id)}
                          className="p-2 text-[#A0A0A0] hover:text-[#EF4444]"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="border-t border-[#1A1A1A] pt-4">
                <h3 className="text-white text-sm font-medium mb-3">Add New Rule</h3>
                <div className="space-y-3">
                  <input
                    type="text"
                    value={newRuleName}
                    onChange={(e) => setNewRuleName(e.target.value)}
                    className="input"
                    placeholder="Rule name (e.g., Only trade A+ setups)"
                  />
                  <input
                    type="text"
                    value={newRuleDescription}
                    onChange={(e) => setNewRuleDescription(e.target.value)}
                    className="input"
                    placeholder="Description (optional)"
                  />
                  <button
                    onClick={addRule}
                    disabled={!newRuleName.trim() || addingRule}
                    className="btn-primary flex items-center gap-2"
                  >
                    <Plus className="w-4 h-4" />
                    {addingRule ? 'Adding...' : 'Add Rule'}
                  </button>
                </div>
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
