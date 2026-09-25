# TradeHub

AI micro-scalping trading bot for Pocket Option.

## Status

Foundation stage. The project is isolated from other trading projects.

## Architecture

- market: realtime market data
- strategy: signal and strategy logic
- signals: signal normalization and validation
- risk: position/risk controls
- execution: order execution abstraction
- broker: Pocket Option adapter
- monitoring: 24/7 runtime health
- core: application orchestration

## Safety

The initial runtime is designed for simulation / dry-run operation. Live execution must be explicitly enabled after broker connectivity and execution logic are validated.

## Configuration

Secrets and broker credentials belong in environment variables. Never commit tokens, cookies, session data, or API secrets.
