# MNQ Futures Trading Bot

A comprehensive automated trading system for MNQ (Micro E-mini Nasdaq 100) futures with multiple strategy implementations, robust backtesting, and NinjaTrader 8 integration.

## Features

- **Multiple Trading Strategies**: 9+ pre-built strategies across different trading styles
- **Comprehensive Backtesting**: Full backtest engine with realistic cost modeling
- **NinjaTrader Integration**: Connect to NinjaTrader 8 via ATI for live trading
- **Risk Management**: Position sizing, daily limits, and drawdown protection
- **Cloud-Ready**: Docker configuration for containerized deployment
- **Real-time Monitoring**: REST API and Prometheus metrics

## Quick Start

### 1. Installation

```bash
# Clone or navigate to the project
cd trading-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Backtests

```bash
# Run comprehensive strategy backtests
python run_backtest.py
```

This will:
- Test all 19 strategy configurations
- Generate performance metrics for each
- Select the best performing strategy
- Save results to `results/` directory

### 3. Review Results

Check the generated reports in `results/`:
- `backtest_report_*.txt` - Full text report
- `backtest_results_*.json` - Detailed JSON results
- `best_strategy_config.json` - Configuration for the selected strategy

### 4. Live Trading (with NinjaTrader)

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# Start the bot
python main.py
```

## Project Structure

```
trading-bot/
├── src/
│   ├── strategies/          # Trading strategies
│   │   ├── base.py          # Base strategy class
│   │   ├── momentum.py      # MA Crossover, Breakout, MACD
│   │   ├── mean_reversion.py # RSI, Bollinger Bands, Z-Score
│   │   ├── volatility.py    # ATR Breakout, Keltner Channel
│   │   └── time_based.py    # ORB, Session Momentum
│   ├── backtest/            # Backtesting engine
│   │   ├── engine.py        # Main backtest logic
│   │   └── metrics.py       # Performance calculations
│   ├── broker/              # Broker integrations
│   │   └── ninjatrader.py   # NinjaTrader ATI connection
│   ├── risk/                # Risk management
│   │   └── manager.py       # Position sizing, limits
│   ├── data/                # Data handling
│   │   └── data_handler.py  # Data fetching, indicators
│   └── bot.py               # Main bot orchestrator
├── config/
│   └── settings.py          # Configuration management
├── tests/                   # Unit tests
├── docker/                  # Docker configurations
├── logs/                    # Log files
├── results/                 # Backtest results
├── run_backtest.py          # Backtest runner script
├── main.py                  # Live trading entry point
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Trading Strategies

### Momentum/Trend Following

1. **MA Crossover** - EMA crossover with trend filter
   - Fast EMA crosses slow EMA for entries
   - Optional longer-term trend filter
   
2. **Breakout** - Donchian Channel breakout
   - Enters on N-period high/low breaks
   - Volume confirmation optional

3. **MACD Momentum** - MACD signal line crossover
   - Histogram confirmation for stronger signals

### Mean Reversion

4. **RSI Mean Reversion** - RSI oversold/overbought reversals
   - Waits for price confirmation
   - Reversal candle patterns

5. **Bollinger Band** - Band touch reversals
   - RSI confirmation
   - Squeeze filter to avoid low volatility

6. **Statistical Arbitrage** - Z-score based entries
   - Enters at extreme deviations from mean

### Volatility-Based

7. **ATR Breakout** - Volatility expansion entries
   - Breakout beyond ATR multiple
   - Volume confirmation

8. **Range Expansion** - Inside bar breakouts
   - Identifies consolidation patterns
   - Trades expansion moves

9. **Keltner Channel** - EMA + ATR channel breakouts
   - Squeeze detection for timing

### Time-Based

10. **Opening Range Breakout (ORB)** - First 30-min range breakout
    - Classic intraday strategy
    - Volume confirmation

11. **Session Momentum** - First hour momentum continuation
    - VWAP pullback entries
    - Trades with session bias

12. **London Open** - Pre-market momentum into US open
    - Continuation or reversal mode

## Strategy Selection Criteria

The backtester evaluates strategies on:

| Criteria | Requirement |
|----------|-------------|
| Positive Expectancy | Required |
| Max Drawdown | < 25% |
| Sharpe Ratio | > 1.0 preferred |
| Trade Count | > 20 for statistical significance |
| Profit Factor | > 1.2 preferred |
| Win Rate | > 40% preferred |

## NinjaTrader Setup

### Prerequisites

1. NinjaTrader 8 installed and running
2. ATI (Automated Trading Interface) enabled
3. Trading account configured

### Enable ATI in NinjaTrader

1. Open NinjaTrader 8
2. Go to **Tools** → **Options** → **Automated Trading Interface**
3. Enable **AT Interface**
4. Set the **Server Port** (default: 36973)
5. Configure the **Accounts** to allow external access

### Connection Modes

The bot supports two connection modes:

**Socket Mode (Recommended)**
```python
# Default - connects via TCP socket
NT_HOST=127.0.0.1
NT_PORT=36973
```

**File-Based Mode**
```python
# Alternative - uses file system
NT_ATI_FOLDER=C:\Users\<user>\Documents\NinjaTrader 8\incoming
```

### Order Types Supported

- Market orders
- Limit orders
- Stop orders
- Bracket orders (OCO with stop loss and take profit)

## Risk Management

### Configuration Options

```python
# config/settings.py or .env

MAX_POSITION_SIZE=3        # Maximum contracts
RISK_PER_TRADE_PCT=1.0     # Risk per trade (% of account)
MAX_DAILY_LOSS=500         # Daily loss limit ($)
MAX_DAILY_LOSS_PCT=5.0     # Daily loss limit (%)
MAX_TRADES_PER_DAY=10      # Maximum trades per session
MAX_DRAWDOWN_PCT=20.0      # Maximum drawdown before pause
```

### Position Sizing

The bot uses fixed fractional position sizing:

```
Position Size = (Account × Risk%) / (Stop Distance × Point Value)
```

Limited by:
- Maximum position size setting
- Available margin (50% of account max)

### Session Control

- Trading hours: 9:30 AM - 4:00 PM ET (configurable)
- Auto-close positions 15 minutes before session end
- News blackout periods (configurable)

## Docker Deployment

### Build and Run

```bash
# Build the image
docker build -t mnq-trading-bot .

# Run with docker-compose
docker-compose up -d
```

### Services Included

- **trading-bot**: Main trading application
- **redis**: State persistence
- **prometheus**: Metrics collection
- **grafana**: Visualization dashboards

### Access Points

| Service | URL |
|---------|-----|
| Trading Bot API | http://localhost:8080 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API info |
| `/health` | GET | Health check |
| `/status` | GET | Detailed status |
| `/start` | POST | Start trading |
| `/stop` | POST | Stop trading |
| `/pause` | POST | Pause (hold positions) |
| `/resume` | POST | Resume trading |
| `/position` | GET | Current position |
| `/flatten` | POST | Close all positions |
| `/metrics` | GET | Prometheus metrics |
| `/strategy` | GET | Strategy info |

## Backtest Results Interpretation

### Key Metrics

- **Sharpe Ratio**: Risk-adjusted return (>1.0 is good, >2.0 is excellent)
- **Max Drawdown**: Largest peak-to-trough decline
- **Profit Factor**: Gross profit / Gross loss (>1.5 is good)
- **Win Rate**: Percentage of winning trades
- **Expectancy**: Average expected profit per trade

### Example Output

```
MA_Crossover [✓ QUALIFIED]
  Score: 85.0
  Return: 12.45%
  Sharpe: 1.52
  Max DD: -8.23%
  Trades: 67
```

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NT_HOST` | 127.0.0.1 | NinjaTrader host |
| `NT_PORT` | 36973 | NinjaTrader ATI port |
| `NT_ACCOUNT` | Sim101 | Trading account |
| `INSTRUMENT` | MNQ 03-24 | Futures contract |
| `INITIAL_CAPITAL` | 10000 | Starting capital |
| `STRATEGY_NAME` | MA_Crossover | Strategy to use |
| `LOG_LEVEL` | INFO | Logging level |

## Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src

# Run specific test file
pytest tests/test_strategies.py -v
```

## Troubleshooting

### Common Issues

**Can't connect to NinjaTrader**
- Ensure NinjaTrader is running
- Verify ATI is enabled in NinjaTrader settings
- Check firewall settings

**No data returned**
- yfinance may have rate limits
- Synthetic data will be generated automatically

**Strategy not generating signals**
- Check that data has enough bars for indicators
- Verify strategy parameters are valid

### Logs

- Console output: Real-time status
- `logs/trading_bot.log`: Detailed logs
- `logs/backtest_*.log`: Backtest-specific logs

## Disclaimer

This software is for educational purposes only. Trading futures involves substantial risk of loss. Past performance does not guarantee future results. Always test thoroughly in a simulation environment before using with real money.

## License

MIT License - See LICENSE file for details.
