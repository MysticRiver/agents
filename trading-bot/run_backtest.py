#!/usr/bin/env python3
"""
Backtest Runner for MNQ Trading Strategies

Runs comprehensive backtests on multiple strategies and selects the best one.
"""
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from loguru import logger

from src.data.data_handler import DataHandler
from src.backtest.engine import BacktestEngine, BacktestResult
from src.backtest.metrics import generate_report

# Import all strategies
from src.strategies.momentum import MACrossoverStrategy, BreakoutStrategy, MACDMomentumStrategy
from src.strategies.mean_reversion import RSIMeanReversionStrategy, BollingerBandStrategy, StatisticalArbitrageStrategy
from src.strategies.volatility import ATRBreakoutStrategy, RangeExpansionStrategy, KeltnerChannelStrategy
from src.strategies.time_based import OpeningRangeBreakoutStrategy, SessionMomentumStrategy, LondonOpenStrategy

# Configure logging
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")
logger.add("logs/backtest_{time}.log", level="DEBUG")


def get_strategies() -> List:
    """Get all strategies to backtest"""
    return [
        # Momentum strategies
        MACrossoverStrategy(fast_period=9, slow_period=21, use_trend_filter=True),
        MACrossoverStrategy(fast_period=5, slow_period=13, use_trend_filter=False),
        BreakoutStrategy(entry_period=20, exit_period=10),
        MACDMomentumStrategy(fast_period=12, slow_period=26, signal_period=9),
        
        # Mean reversion strategies
        RSIMeanReversionStrategy(rsi_period=14, oversold_level=30, overbought_level=70),
        BollingerBandStrategy(bb_period=20, bb_std=2.0, use_squeeze_filter=True),
        StatisticalArbitrageStrategy(lookback_period=20, entry_z_score=2.0),
        
        # Volatility strategies
        ATRBreakoutStrategy(atr_period=14, atr_multiplier=2.0, require_volume_confirmation=True),
        RangeExpansionStrategy(inside_bar_lookback=3, require_trend_alignment=True),
        KeltnerChannelStrategy(ema_period=20, atr_multiplier=2.0, squeeze_filter=True),
    ]


def evaluate_strategy(result: BacktestResult) -> Dict[str, Any]:
    """
    Evaluate a strategy based on multiple criteria.
    
    Selection criteria:
    1. Positive expectancy (must have)
    2. Max drawdown < 20%
    3. Sharpe ratio > 1.0 (preferred)
    4. Sufficient trade frequency (>20 trades)
    5. Profit factor > 1.2
    """
    metrics = result.metrics
    
    score = 0.0
    reasons = []
    warnings = []
    
    # Must have positive expectancy
    if metrics.expectancy > 0:
        score += 20
        reasons.append(f"Positive expectancy: ${metrics.expectancy:.2f}")
    else:
        warnings.append(f"Negative expectancy: ${metrics.expectancy:.2f}")
        
    # Total return
    if result.total_return_pct > 0:
        score += min(30, result.total_return_pct)
        reasons.append(f"Positive return: {result.total_return_pct:.2f}%")
    else:
        warnings.append(f"Negative return: {result.total_return_pct:.2f}%")
        
    # Sharpe ratio
    if metrics.sharpe_ratio > 1.5:
        score += 25
        reasons.append(f"Excellent Sharpe: {metrics.sharpe_ratio:.2f}")
    elif metrics.sharpe_ratio > 1.0:
        score += 15
        reasons.append(f"Good Sharpe: {metrics.sharpe_ratio:.2f}")
    elif metrics.sharpe_ratio > 0.5:
        score += 5
        reasons.append(f"Acceptable Sharpe: {metrics.sharpe_ratio:.2f}")
    else:
        warnings.append(f"Poor Sharpe: {metrics.sharpe_ratio:.2f}")
        
    # Max drawdown
    if abs(metrics.max_drawdown_pct) < 10:
        score += 20
        reasons.append(f"Low drawdown: {abs(metrics.max_drawdown_pct):.2f}%")
    elif abs(metrics.max_drawdown_pct) < 20:
        score += 10
        reasons.append(f"Acceptable drawdown: {abs(metrics.max_drawdown_pct):.2f}%")
    else:
        warnings.append(f"High drawdown: {abs(metrics.max_drawdown_pct):.2f}%")
        
    # Trade frequency
    if metrics.total_trades >= 50:
        score += 15
        reasons.append(f"Good sample size: {metrics.total_trades} trades")
    elif metrics.total_trades >= 20:
        score += 8
        reasons.append(f"Adequate sample: {metrics.total_trades} trades")
    else:
        warnings.append(f"Low sample size: {metrics.total_trades} trades")
        
    # Win rate
    if metrics.win_rate >= 50:
        score += 10
        reasons.append(f"Good win rate: {metrics.win_rate:.1f}%")
    elif metrics.win_rate >= 40:
        score += 5
        reasons.append(f"Acceptable win rate: {metrics.win_rate:.1f}%")
    else:
        warnings.append(f"Low win rate: {metrics.win_rate:.1f}%")
        
    # Profit factor
    if metrics.profit_factor > 2.0:
        score += 15
        reasons.append(f"Excellent profit factor: {metrics.profit_factor:.2f}")
    elif metrics.profit_factor > 1.5:
        score += 10
        reasons.append(f"Good profit factor: {metrics.profit_factor:.2f}")
    elif metrics.profit_factor > 1.2:
        score += 5
        reasons.append(f"Acceptable profit factor: {metrics.profit_factor:.2f}")
    else:
        warnings.append(f"Poor profit factor: {metrics.profit_factor:.2f}")
        
    # Risk/Reward
    if metrics.risk_reward_ratio > 2.0:
        score += 10
        reasons.append(f"Good R:R ratio: {metrics.risk_reward_ratio:.2f}")
    elif metrics.risk_reward_ratio > 1.5:
        score += 5
        reasons.append(f"Acceptable R:R ratio: {metrics.risk_reward_ratio:.2f}")
        
    # Disqualifications
    is_qualified = (
        metrics.expectancy > 0 and
        abs(metrics.max_drawdown_pct) < 25 and
        metrics.total_trades >= 10
    )
    
    return {
        "score": score,
        "qualified": is_qualified,
        "reasons": reasons,
        "warnings": warnings,
        "metrics_summary": {
            "total_return_pct": result.total_return_pct,
            "sharpe_ratio": metrics.sharpe_ratio,
            "max_drawdown_pct": metrics.max_drawdown_pct,
            "win_rate": metrics.win_rate,
            "profit_factor": metrics.profit_factor,
            "total_trades": metrics.total_trades,
            "expectancy": metrics.expectancy
        }
    }


def run_backtests(
    start_date: str = "2024-01-01",
    end_date: str = None,
    initial_capital: float = 10000.0,
    data_interval: str = "5m"
) -> List[Dict]:
    """Run backtests for all strategies"""
    
    # Setup data handler
    data_handler = DataHandler()
    
    logger.info(f"Fetching data from {start_date} to {end_date or 'now'}")
    
    # Get data
    data = data_handler.get_data(start_date, end_date, data_interval)
    data = data_handler.add_indicators(data)
    
    logger.info(f"Data loaded: {len(data)} bars from {data.index[0]} to {data.index[-1]}")
    
    # Setup backtest engine
    engine = BacktestEngine(
        initial_capital=initial_capital,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0  # Lower margin for MNQ
    )
    
    # Get strategies
    strategies = get_strategies()
    results = []
    
    logger.info(f"Running backtests for {len(strategies)} strategies...")
    print("\n" + "="*80)
    
    for i, strategy in enumerate(strategies):
        logger.info(f"[{i+1}/{len(strategies)}] Testing {strategy.name} with params: {strategy.parameters}")
        
        try:
            result = engine.run(data, strategy, verbose=False)
            evaluation = evaluate_strategy(result)
            
            results.append({
                "strategy_name": strategy.name,
                "parameters": strategy.parameters,
                "result": result,
                "evaluation": evaluation
            })
            
            # Print summary
            status = "✓ QUALIFIED" if evaluation["qualified"] else "✗ NOT QUALIFIED"
            print(f"\n{strategy.name} [{status}]")
            print(f"  Score: {evaluation['score']:.1f}")
            print(f"  Return: {result.total_return_pct:.2f}%")
            print(f"  Sharpe: {result.metrics.sharpe_ratio:.2f}")
            print(f"  Max DD: {result.metrics.max_drawdown_pct:.2f}%")
            print(f"  Trades: {result.metrics.total_trades}")
            
        except Exception as e:
            logger.error(f"Error testing {strategy.name}: {e}")
            continue
            
    return results


def select_best_strategy(results: List[Dict]) -> Dict:
    """Select the best strategy based on evaluation scores"""
    
    qualified = [r for r in results if r["evaluation"]["qualified"]]
    
    if not qualified:
        logger.warning("No strategies qualified. Selecting best from all.")
        qualified = results
        
    if not qualified:
        raise ValueError("No backtest results available")
        
    # Sort by score
    qualified.sort(key=lambda x: x["evaluation"]["score"], reverse=True)
    
    return qualified[0]


def generate_summary_report(results: List[Dict], best: Dict) -> str:
    """Generate a summary report of all backtests"""
    
    report = []
    report.append("="*80)
    report.append("MNQ TRADING BOT - BACKTEST SUMMARY REPORT")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("="*80)
    report.append("")
    
    # Summary table
    report.append("STRATEGY COMPARISON")
    report.append("-"*80)
    report.append(f"{'Strategy':<30} {'Return %':>10} {'Sharpe':>8} {'MaxDD %':>10} {'Trades':>8} {'Score':>8}")
    report.append("-"*80)
    
    for r in sorted(results, key=lambda x: x["evaluation"]["score"], reverse=True):
        m = r["evaluation"]["metrics_summary"]
        status = "*" if r == best else " "
        report.append(
            f"{status}{r['strategy_name']:<29} {m['total_return_pct']:>10.2f} "
            f"{m['sharpe_ratio']:>8.2f} {m['max_drawdown_pct']:>10.2f} "
            f"{m['total_trades']:>8} {r['evaluation']['score']:>8.1f}"
        )
    
    report.append("-"*80)
    report.append("* = Selected strategy")
    report.append("")
    
    # Best strategy details
    report.append("="*80)
    report.append("SELECTED STRATEGY DETAILS")
    report.append("="*80)
    report.append("")
    report.append(f"Strategy: {best['strategy_name']}")
    report.append(f"Score: {best['evaluation']['score']:.1f}")
    report.append("")
    report.append("Parameters:")
    for k, v in best['parameters'].items():
        report.append(f"  {k}: {v}")
    report.append("")
    
    report.append("Strengths:")
    for reason in best['evaluation']['reasons']:
        report.append(f"  + {reason}")
    report.append("")
    
    if best['evaluation']['warnings']:
        report.append("Concerns:")
        for warning in best['evaluation']['warnings']:
            report.append(f"  - {warning}")
        report.append("")
    
    # Detailed metrics
    report.append("Detailed Metrics:")
    m = best['result'].metrics
    report.append(f"  Total Return: ${best['result'].total_return:,.2f} ({best['result'].total_return_pct:.2f}%)")
    report.append(f"  Annualized Return: {m.annualized_return:.2f}%")
    report.append(f"  Sharpe Ratio: {m.sharpe_ratio:.2f}")
    report.append(f"  Sortino Ratio: {m.sortino_ratio:.2f}")
    report.append(f"  Calmar Ratio: {m.calmar_ratio:.2f}")
    report.append(f"  Max Drawdown: ${abs(m.max_drawdown):,.2f} ({m.max_drawdown_pct:.2f}%)")
    report.append(f"  Total Trades: {m.total_trades}")
    report.append(f"  Winning Trades: {m.winning_trades} ({m.win_rate:.1f}%)")
    report.append(f"  Profit Factor: {m.profit_factor:.2f}")
    report.append(f"  Average Win: ${m.avg_win:.2f}")
    report.append(f"  Average Loss: ${m.avg_loss:.2f}")
    report.append(f"  Risk/Reward Ratio: {m.risk_reward_ratio:.2f}")
    report.append(f"  Expectancy: ${m.expectancy:.2f}")
    report.append(f"  Avg Holding Period: {m.avg_holding_period:.1f} bars")
    report.append("")
    
    report.append("="*80)
    report.append("RECOMMENDATION")
    report.append("="*80)
    report.append("")
    
    if best['evaluation']['qualified']:
        report.append(f"The {best['strategy_name']} strategy is RECOMMENDED for live trading.")
        report.append("")
        report.append("Reasons for selection:")
        for reason in best['evaluation']['reasons'][:5]:
            report.append(f"  - {reason}")
    else:
        report.append("WARNING: No strategy fully qualified based on the criteria.")
        report.append(f"The {best['strategy_name']} is the best available option but use caution.")
        report.append("")
        report.append("Consider:")
        report.append("  - Paper trading for an extended period")
        report.append("  - Further parameter optimization")
        report.append("  - Additional strategy development")
    
    report.append("")
    report.append("="*80)
    
    return "\n".join(report)


def main():
    """Main entry point"""
    
    # Configuration
    START_DATE = "2024-06-01"  # Shorter period for faster testing
    END_DATE = "2024-12-31"
    INITIAL_CAPITAL = 25000.0  # Higher capital for better margin coverage
    DATA_INTERVAL = "5m"
    
    print("\n" + "="*80)
    print("MNQ TRADING BOT - STRATEGY BACKTEST")
    print("="*80 + "\n")
    
    # Create output directory
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    
    # Run backtests
    results = run_backtests(
        start_date=START_DATE,
        end_date=END_DATE,
        initial_capital=INITIAL_CAPITAL,
        data_interval=DATA_INTERVAL
    )
    
    if not results:
        logger.error("No backtest results. Exiting.")
        return
        
    # Select best strategy
    best = select_best_strategy(results)
    
    # Generate report
    report = generate_summary_report(results, best)
    print("\n" + report)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save report
    report_path = output_dir / f"backtest_report_{timestamp}.txt"
    with open(report_path, 'w') as f:
        f.write(report)
    logger.info(f"Report saved to {report_path}")
    
    # Save detailed results as JSON
    def make_serializable(obj):
        """Convert numpy types to Python native types"""
        import numpy as np
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serializable(v) for v in obj]
        elif isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj
    
    results_json = []
    for r in results:
        results_json.append(make_serializable({
            "strategy_name": r["strategy_name"],
            "parameters": r["parameters"],
            "evaluation": r["evaluation"]
        }))
    
    json_path = output_dir / f"backtest_results_{timestamp}.json"
    with open(json_path, 'w') as f:
        json.dump(results_json, f, indent=2)
    logger.info(f"Results saved to {json_path}")
    
    # Save best strategy config
    config_path = output_dir / "best_strategy_config.json"
    with open(config_path, 'w') as f:
        json.dump(make_serializable({
            "strategy_name": best["strategy_name"],
            "parameters": best["parameters"],
            "evaluation": best["evaluation"]
        }), f, indent=2)
    logger.info(f"Best strategy config saved to {config_path}")
    
    print(f"\n✓ Backtest complete. Best strategy: {best['strategy_name']}")
    print(f"  See {report_path} for full details")


if __name__ == "__main__":
    main()
