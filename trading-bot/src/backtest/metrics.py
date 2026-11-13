"""Performance metrics calculation"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class PerformanceMetrics:
    """Collection of performance metrics"""
    # Return metrics
    total_return: float
    total_return_pct: float
    annualized_return: float
    
    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    avg_drawdown: float
    max_drawdown_duration: int  # in bars
    
    # Trade metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    avg_trade: float
    avg_holding_period: float
    
    # Risk/Reward
    risk_reward_ratio: float
    expectancy: float
    
    # Consistency
    monthly_returns: Optional[pd.Series] = None
    winning_months: int = 0
    losing_months: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "total_return": self.total_return,
            "total_return_pct": self.total_return_pct,
            "annualized_return": self.annualized_return,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "avg_drawdown": self.avg_drawdown,
            "max_drawdown_duration": self.max_drawdown_duration,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "avg_trade": self.avg_trade,
            "avg_holding_period": self.avg_holding_period,
            "risk_reward_ratio": self.risk_reward_ratio,
            "expectancy": self.expectancy,
            "winning_months": self.winning_months,
            "losing_months": self.losing_months
        }


def calculate_metrics(
    equity_curve: pd.Series,
    trades: List["Trade"],
    initial_capital: float,
    risk_free_rate: float = 0.05,
    periods_per_year: int = None,  # Override if set, otherwise calculated from frequency
    data_frequency: str = "1h"  # "1m", "5m", "1h", "1d"
) -> PerformanceMetrics:
    """
    Calculate comprehensive performance metrics.
    
    Args:
        equity_curve: Series of equity values over time
        trades: List of completed trades
        initial_capital: Starting capital
        risk_free_rate: Annual risk-free rate
        periods_per_year: Number of periods per year for annualization (auto-calculated if None)
        data_frequency: Data frequency for auto-calculating periods_per_year
    """
    # Calculate periods_per_year based on data frequency
    # Assumes ~252 trading days, ~6.5 hours of regular trading per day
    TRADING_DAYS_PER_YEAR = 252
    TRADING_HOURS_PER_DAY = 6.5
    
    if periods_per_year is None:
        if data_frequency == "1m":
            periods_per_year = int(TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY * 60)  # ~98,280
        elif data_frequency == "5m":
            periods_per_year = int(TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY * 12)  # ~19,656
        elif data_frequency == "15m":
            periods_per_year = int(TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY * 4)  # ~6,552
        elif data_frequency == "1h":
            periods_per_year = int(TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY)  # ~1,638
        elif data_frequency == "1d":
            periods_per_year = TRADING_DAYS_PER_YEAR  # 252
        else:
            periods_per_year = int(TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY)  # Default to hourly
    
    # Return calculations
    total_return = equity_curve.iloc[-1] - initial_capital
    total_return_pct = (total_return / initial_capital) * 100
    
    # Calculate returns series
    returns = equity_curve.pct_change().dropna()
    
    # Annualized return
    total_periods = len(equity_curve)
    years = total_periods / periods_per_year
    if years > 0 and equity_curve.iloc[-1] > 0:
        annualized_return = ((equity_curve.iloc[-1] / initial_capital) ** (1 / years) - 1) * 100
    else:
        annualized_return = 0.0
    
    # Sharpe Ratio
    if returns.std() > 0:
        excess_returns = returns - (risk_free_rate / periods_per_year)
        sharpe_ratio = np.sqrt(periods_per_year) * excess_returns.mean() / returns.std()
    else:
        sharpe_ratio = 0.0
    
    # Sortino Ratio (downside deviation)
    negative_returns = returns[returns < 0]
    if len(negative_returns) > 0 and negative_returns.std() > 0:
        downside_std = negative_returns.std()
        sortino_ratio = np.sqrt(periods_per_year) * returns.mean() / downside_std
    else:
        sortino_ratio = sharpe_ratio
    
    # Drawdown calculations
    rolling_max = equity_curve.expanding().max()
    drawdown = equity_curve - rolling_max
    drawdown_pct = (drawdown / rolling_max) * 100
    
    max_drawdown = drawdown.min()
    max_drawdown_pct = drawdown_pct.min()
    avg_drawdown = drawdown_pct[drawdown_pct < 0].mean() if (drawdown_pct < 0).any() else 0.0
    
    # Max drawdown duration
    max_dd_duration = _calculate_max_drawdown_duration(equity_curve)
    
    # Calmar Ratio
    if max_drawdown_pct < 0:
        calmar_ratio = annualized_return / abs(max_drawdown_pct)
    else:
        calmar_ratio = float('inf') if annualized_return > 0 else 0.0
    
    # Trade statistics
    if trades:
        pnls = [t.pnl for t in trades]
        winning_pnls = [p for p in pnls if p > 0]
        losing_pnls = [p for p in pnls if p < 0]
        
        total_trades = len(trades)
        winning_trades = len(winning_pnls)
        losing_trades = len(losing_pnls)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        gross_profit = sum(winning_pnls) if winning_pnls else 0.0
        gross_loss = abs(sum(losing_pnls)) if losing_pnls else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        avg_win = np.mean(winning_pnls) if winning_pnls else 0.0
        avg_loss = np.mean(losing_pnls) if losing_pnls else 0.0
        largest_win = max(winning_pnls) if winning_pnls else 0.0
        largest_loss = min(losing_pnls) if losing_pnls else 0.0
        avg_trade = np.mean(pnls)
        
        holding_periods = [t.holding_period for t in trades]
        avg_holding_period = np.mean(holding_periods) if holding_periods else 0.0
        
        # Risk/Reward ratio
        if avg_loss != 0:
            risk_reward_ratio = abs(avg_win / avg_loss)
        else:
            risk_reward_ratio = float('inf') if avg_win > 0 else 0.0
        
        # Expectancy (average expected profit per trade)
        expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)
    else:
        total_trades = 0
        winning_trades = 0
        losing_trades = 0
        win_rate = 0.0
        profit_factor = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        largest_win = 0.0
        largest_loss = 0.0
        avg_trade = 0.0
        avg_holding_period = 0.0
        risk_reward_ratio = 0.0
        expectancy = 0.0
    
    # Monthly returns
    try:
        monthly_returns = equity_curve.resample('ME').last().pct_change().dropna()
    except ValueError:
        monthly_returns = equity_curve.resample('M').last().pct_change().dropna()
    winning_months = (monthly_returns > 0).sum()
    losing_months = (monthly_returns < 0).sum()
    
    return PerformanceMetrics(
        total_return=total_return,
        total_return_pct=total_return_pct,
        annualized_return=annualized_return,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        avg_drawdown=avg_drawdown,
        max_drawdown_duration=max_dd_duration,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        largest_win=largest_win,
        largest_loss=largest_loss,
        avg_trade=avg_trade,
        avg_holding_period=avg_holding_period,
        risk_reward_ratio=risk_reward_ratio,
        expectancy=expectancy,
        monthly_returns=monthly_returns,
        winning_months=winning_months,
        losing_months=losing_months
    )


def _calculate_max_drawdown_duration(equity_curve: pd.Series) -> int:
    """Calculate maximum drawdown duration in bars"""
    rolling_max = equity_curve.expanding().max()
    in_drawdown = equity_curve < rolling_max
    
    if not in_drawdown.any():
        return 0
    
    # Find consecutive drawdown periods
    drawdown_groups = (in_drawdown != in_drawdown.shift()).cumsum()
    drawdown_groups = drawdown_groups[in_drawdown]
    
    if len(drawdown_groups) == 0:
        return 0
    
    durations = drawdown_groups.groupby(drawdown_groups).size()
    return int(durations.max())


def generate_report(result: "BacktestResult") -> str:
    """Generate a text report of backtest results"""
    m = result.metrics
    
    report = f"""
{'='*60}
BACKTEST REPORT: {result.strategy_name}
{'='*60}

PERIOD: {result.start_date.date()} to {result.end_date.date()}
INITIAL CAPITAL: ${result.initial_capital:,.2f}
FINAL CAPITAL: ${result.final_capital:,.2f}

--- RETURNS ---
Total Return: ${result.total_return:,.2f} ({result.total_return_pct:.2f}%)
Annualized Return: {m.annualized_return:.2f}%

--- RISK METRICS ---
Sharpe Ratio: {m.sharpe_ratio:.2f}
Sortino Ratio: {m.sortino_ratio:.2f}
Calmar Ratio: {m.calmar_ratio:.2f}
Max Drawdown: ${abs(m.max_drawdown):,.2f} ({m.max_drawdown_pct:.2f}%)
Avg Drawdown: {m.avg_drawdown:.2f}%
Max DD Duration: {m.max_drawdown_duration} bars

--- TRADE STATISTICS ---
Total Trades: {m.total_trades}
Winning Trades: {m.winning_trades} ({m.win_rate:.1f}%)
Losing Trades: {m.losing_trades}
Profit Factor: {m.profit_factor:.2f}

Average Win: ${m.avg_win:.2f}
Average Loss: ${m.avg_loss:.2f}
Largest Win: ${m.largest_win:.2f}
Largest Loss: ${m.largest_loss:.2f}
Average Trade: ${m.avg_trade:.2f}

Risk/Reward Ratio: {m.risk_reward_ratio:.2f}
Expectancy: ${m.expectancy:.2f}
Avg Holding Period: {m.avg_holding_period:.1f} bars

--- STRATEGY PARAMETERS ---
{_format_parameters(result.parameters)}

{'='*60}
"""
    return report


def _format_parameters(params: dict, indent: int = 0) -> str:
    """Format parameters dictionary for display"""
    lines = []
    for key, value in params.items():
        if isinstance(value, dict):
            lines.append(f"{'  '*indent}{key}:")
            lines.append(_format_parameters(value, indent + 1))
        else:
            lines.append(f"{'  '*indent}{key}: {value}")
    return '\n'.join(lines)
