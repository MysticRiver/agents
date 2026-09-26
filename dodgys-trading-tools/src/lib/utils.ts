export function formatCurrency(amount: number): string {
  const formatted = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(Math.abs(amount))
  
  if (amount < 0) return `-${formatted}`
  return formatted
}

export function formatPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
}

export function getContractValue(instrument: string): { pointValue: number; tickValue: number; ticksPerPoint: number } {
  switch (instrument.toUpperCase()) {
    case 'NQ':
      return { pointValue: 20, tickValue: 5, ticksPerPoint: 4 }
    case 'ES':
      return { pointValue: 50, tickValue: 12.5, ticksPerPoint: 4 }
    case 'MNQ':
      return { pointValue: 2, tickValue: 0.5, ticksPerPoint: 4 }
    default:
      return { pointValue: 20, tickValue: 5, ticksPerPoint: 4 }
  }
}

export function calculatePnl(
  instrument: string,
  direction: 'long' | 'short',
  entryPrice: number,
  exitPrice: number,
  contracts: number
): { pnl: number; pnlPoints: number } {
  const { pointValue } = getContractValue(instrument)
  const pnlPoints = direction === 'long' 
    ? exitPrice - entryPrice 
    : entryPrice - exitPrice
  const pnl = pnlPoints * pointValue * contracts
  
  return { pnl, pnlPoints }
}

export function getTradingSession(date: Date = new Date()): {
  name: string
  isActive: boolean
} {
  const etTime = new Date(date.toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const hours = etTime.getHours()
  const minutes = etTime.getMinutes()
  const time = hours * 60 + minutes
  
  if (time >= 19 * 60 || time < 2 * 60) {
    return { name: 'Asia', isActive: true }
  }
  if (time >= 3 * 60 && time < 4 * 60) {
    return { name: 'London', isActive: true }
  }
  if (time >= 4 * 60 && time < 8 * 60 + 30) {
    return { name: 'Pre-Market', isActive: true }
  }
  if (time >= 8 * 60 + 30 && time < 9 * 60 + 30) {
    return { name: 'Data Release Window', isActive: true }
  }
  if (time >= 9 * 60 + 30 && time < 12 * 60) {
    return { name: 'NY Open', isActive: true }
  }
  if (time >= 12 * 60 && time < 16 * 60) {
    return { name: 'NY Afternoon', isActive: true }
  }
  if (time >= 16 * 60 && time < 19 * 60) {
    return { name: 'After Hours', isActive: true }
  }
  
  return { name: 'Closed', isActive: false }
}

export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ')
}

export const DODGYS_RULES = [
  "It doesn't start with the inversion. It starts with the draw on liquidity.",
  "If it's not a light bulb, skip it.",
  "One bad trade doesn't have to become three.",
  "Grade the setup before you take it. If it's not an A or A+, don't risk your live account.",
  "Know your daily loss limit before the session starts.",
  "If you hit your loss limit, you're done for the day. No exceptions.",
  "Journal every trade. Winners and losers.",
  "The strategy works. Trust the process. Back test, back test, back test.",
  "React, don't predict.",
  "Don't trade your P&L. Trade your plan.",
  "Stop targeting non-engineered liquidity.",
  "Win rate alone will not make you profitable. It's win rate PLUS R:R.",
  "Close-based stops. Not wick-based. Wait for the close."
]
