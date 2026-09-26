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

export interface ValidationInput {
  instrument: string
  direction: string
  setupType: string
  checklist: {
    clearDrawOnLiquidity: boolean
    structureAligned: boolean
    candleClosureConfirmed: boolean
    higherTimeframeBias: boolean
  }
  emotionalState: number
  entryPrice?: number
  stopLoss?: number
  takeProfit?: number
  session?: string
  tradesCountToday: number
  isInLossToday: boolean
}

export interface ScoreBreakdown {
  setupQuality: number
  riskManagement: number
  emotional: number
}

export interface ValidationResult {
  score: number
  grade: string
  scoreBreakdown: ScoreBreakdown
  feedback: string
  override?: string
}

export function calculateValidationScore(input: ValidationInput): ValidationResult {
  let setupQuality = 0
  let riskManagement = 0
  let emotional = 0
  let override: string | undefined

  if (input.emotionalState === 5) {
    override = "You're trading your emotions, not your plan. Close the charts."
  }

  if (input.tradesCountToday >= 4 && input.isInLossToday) {
    override = "You're revenge trading. Every trader who blows an account says 'just one more.' Stop."
  }

  if (input.setupType === 'IFVG' || input.setupType === 'V-Shape Recovery') {
    setupQuality += 15
  } else if (input.setupType === 'Structure Break' || input.setupType === 'Liquidity Sweep') {
    setupQuality += 10
  } else {
    setupQuality += 5
  }

  if (input.checklist.clearDrawOnLiquidity) setupQuality += 10
  if (input.checklist.structureAligned) setupQuality += 10
  if (input.checklist.candleClosureConfirmed) setupQuality += 5

  if (input.entryPrice && input.stopLoss && input.takeProfit) {
    const risk = Math.abs(input.entryPrice - input.stopLoss)
    const reward = Math.abs(input.takeProfit - input.entryPrice)
    const rr = risk > 0 ? reward / risk : 0

    if (rr < 1) {
      override = "The math doesn't work. No setup is good enough to justify negative R:R."
      riskManagement += 0
    } else if (rr >= 2) {
      riskManagement += 15
    } else if (rr >= 1.5) {
      riskManagement += 10
    } else {
      riskManagement += 5
    }
  } else {
    riskManagement += 10
  }

  if (input.checklist.higherTimeframeBias) riskManagement += 10

  const session = input.session || getTradingSession().name
  if (session === 'NY Open' || session === 'Data Release Window') {
    riskManagement += 5
  }

  if (input.emotionalState <= 2) {
    emotional += 15
  } else if (input.emotionalState === 3) {
    emotional += 10
  } else if (input.emotionalState === 4) {
    emotional += 5
  }

  if (input.tradesCountToday <= 1) {
    emotional += 10
  } else if (input.tradesCountToday === 2) {
    emotional += 7
  } else if (input.tradesCountToday === 3) {
    emotional += 3
  }

  if (!input.isInLossToday) {
    emotional += 5
  } else if (input.emotionalState <= 2) {
    emotional += 3
  }

  const totalScore = setupQuality + riskManagement + emotional

  let grade: string
  let feedback: string

  if (override) {
    grade = 'F'
    feedback = override
  } else if (totalScore >= 85) {
    grade = 'A+'
    feedback = 'Clean setup. Execute your plan.'
  } else if (totalScore >= 70) {
    grade = 'A'
    feedback = 'Solid. The edge is there.'
  } else if (totalScore >= 55) {
    grade = 'B'
    feedback = "Something's off. Check what scored low."
  } else if (totalScore >= 40) {
    grade = 'C'
    feedback = 'More wrong than right. Sit this one out.'
  } else {
    grade = 'F'
    feedback = 'No. Step away.'
  }

  return {
    score: override ? 0 : totalScore,
    grade,
    scoreBreakdown: {
      setupQuality: Math.min(setupQuality, 40),
      riskManagement: Math.min(riskManagement, 30),
      emotional: Math.min(emotional, 30)
    },
    feedback,
    override
  }
}

export const DEFAULT_TRADING_RULES = [
  { id: 'maxTrades', name: 'Maximum trades per day', enabled: false, value: 2 },
  { id: 'onlyASetups', name: 'Only take A or A+ validated setups', enabled: false },
  { id: 'nyOpenOnly', name: 'Only trade during NY Open (9:30-12:00) or Data Release (8:30)', enabled: false },
  { id: 'stopAtLossLimit', name: 'Stop trading after hitting daily loss limit', enabled: false },
  { id: 'validateEvery', name: 'Validate every trade before entry', enabled: false },
  { id: 'journalEvery', name: 'Journal every trade', enabled: false },
  { id: 'noEmotional', name: "Don't trade when emotional state is 4+", enabled: false },
  { id: 'minRR', name: 'Minimum risk/reward', enabled: false, value: 2 },
  { id: 'onlyInstrument', name: 'Only trade instrument', enabled: false, value: 'NQ' },
  { id: 'stopAfterLosses', name: 'No trading after consecutive losses', enabled: false, value: 1 },
  { id: 'engineeredLiquidity', name: 'Only target engineered liquidity', enabled: false },
  { id: 'closeBasedStops', name: 'Use close-based stops, not wick-based', enabled: false },
  { id: 'breakEvenFirst', name: 'Move to break-even at first internal level', enabled: false },
  { id: 'noReEntry', name: "Don't re-enter after break-even stop", enabled: false },
  { id: 'lightBulbOnly', name: 'Only trade light bulb setups on live account', enabled: false }
]
