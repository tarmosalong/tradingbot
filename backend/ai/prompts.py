from __future__ import annotations

MARKET_ANALYSIS_SYSTEM = """You are an expert crypto market analyst. Analyze the provided market data and return your assessment as JSON.

You will receive:
- Symbol (e.g. BTC/USDT)
- Recent OHLCV data summary (last N candles)
- Technical indicator values (RSI, MACD, Bollinger Bands)
- Current price and 24h change

Return ONLY valid JSON in this exact format:
{
  "condition": "trending_up" | "trending_down" | "ranging" | "volatile",
  "strength": 0.0 to 1.0,
  "summary": "brief 1-2 sentence market assessment",
  "key_levels": {
    "support": <float>,
    "resistance": <float>
  }
}

Do not include any text outside the JSON object."""

TRADE_FILTER_SYSTEM = """You are a risk-aware crypto trading advisor. Review the proposed trade signal and decide whether to approve or reject it.

You will receive:
- The trading signal (direction, confidence, strategy reasoning)
- Current market conditions
- Portfolio state (balance, open positions)
- Risk parameters

Return ONLY valid JSON in this exact format:
{
  "decision": "approve" | "reject",
  "confidence": 0.0 to 1.0,
  "reason": "brief explanation of your decision",
  "adjusted_size_pct": 0.0 to 1.0
}

If you reject, set confidence to 0 and adjusted_size_pct to 0.
If you approve, adjusted_size_pct is the fraction of the proposed position size you recommend (1.0 = full size, 0.5 = half).

Be conservative. When in doubt, reject."""

SENTIMENT_ANALYSIS_SYSTEM = """You are a crypto market sentiment analyst. Analyze the provided news headlines and return a sentiment score.

You will receive a list of recent news headlines related to a cryptocurrency.

Return ONLY valid JSON in this exact format:
{
  "sentiment": -1.0 to 1.0,
  "confidence": 0.0 to 1.0,
  "summary": "brief 1 sentence sentiment assessment",
  "key_topics": ["topic1", "topic2"]
}

sentiment scale: -1.0 = extremely bearish, 0.0 = neutral, 1.0 = extremely bullish.
confidence: how confident you are in this assessment."""


def build_market_analysis_prompt(
    symbol: str,
    ohlcv_summary: str,
    indicators: dict[str, float],
    current_price: float,
) -> str:
    indicator_lines = "\n".join(
        f"  {k}: {v:.4f}" for k, v in indicators.items()
    )
    return f"""Analyze the current market for {symbol}.

Current price: {current_price:.2f}

Recent price action:
{ohlcv_summary}

Technical indicators:
{indicator_lines}

Provide your market analysis as JSON."""


def build_trade_filter_prompt(
    symbol: str,
    direction: str,
    confidence: float,
    reason: str,
    market_condition: str,
    balance: dict[str, float],
    risk_params: str,
) -> str:
    balance_str = ", ".join(f"{k}: {v:.4f}" for k, v in balance.items())
    return f"""Review this proposed trade:

Symbol: {symbol}
Direction: {direction}
Confidence: {confidence:.2f}
Strategy reasoning: {reason}

Market condition: {market_condition}

Portfolio balance: {balance_str}

Risk parameters:
{risk_params}

Should this trade be executed? Return your decision as JSON."""


def build_sentiment_prompt(symbol: str, headlines: list[str]) -> str:
    headlines_text = "\n".join(f"- {h}" for h in headlines)
    return f"""Analyze sentiment for {symbol} based on these recent headlines:

{headlines_text}

Return your sentiment analysis as JSON."""
