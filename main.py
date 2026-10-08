import requests
import statistics
import csv
import io
import os
import math
from datetime import datetime, timezone

# EODHD API KEY
EODHD_API_KEY = os.environ["EODHD_API_KEY"]
# ============================================================
# HULKTRADER USA ENTRY RADAR
# Dynamic NASDAQ + NYSE universe
# ============================================================

USER_AGENT = "HulkTrader-Stock-Scanner/2.0"

MIN_PRICE = 5.0
MIN_AVG_VOLUME = 200000
MIN_HISTORY = 210

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"


# ============================================================
# DOWNLOAD
# ============================================================

def download_text(url):

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=30
    )

    response.raise_for_status()

    return response.text


# ============================================================
# NORMALIZE SYMBOL
# ============================================================

def normalize_symbol(symbol):

    symbol = symbol.strip()

    # Yahoo Finance commonly uses "-" for share classes
    symbol = symbol.replace("/", "-")
    symbol = symbol.replace(".", "-")

    return symbol


# ============================================================
# BUILD USA STOCK UNIVERSE
# ============================================================

def get_us_universe():

    universe = {}

    print()
    print("=" * 70)
    print("BUILDING USA STOCK UNIVERSE")
    print("=" * 70)

    # --------------------------------------------------------
    # NASDAQ
    # --------------------------------------------------------

    print("Downloading NASDAQ listings...")

    text = download_text(NASDAQ_LISTED_URL)

    lines = text.strip().splitlines()

    reader = csv.DictReader(
        lines,
        delimiter="|"
    )

    for row in reader:

        symbol = row.get("Symbol", "").strip()
        name = row.get("Security Name", "").strip()
        etf = row.get("ETF", "").strip().upper()
        test_issue = row.get("Test Issue", "").strip().upper()
        financial_status = row.get("Financial Status", "").strip().upper()

        if not symbol:
            continue

        if etf == "Y":
            continue

        if test_issue == "Y":
            continue

        if financial_status in ["D", "E", "Q"]:
            continue

        # Exclude obvious non-common securities
        bad_words = [
            "WARRANT",
            "RIGHT",
            "UNIT",
            "NOTE",
            "DEBENTURE",
            "PREFERRED"
        ]

        if any(word in name.upper() for word in bad_words):
            continue

        yahoo_symbol = normalize_symbol(symbol)

        universe[yahoo_symbol] = name

    print(f"NASDAQ stocks found: {len(universe)}")

    # --------------------------------------------------------
    # NYSE / NYSE AMERICAN
    # --------------------------------------------------------

    print("Downloading NYSE listings...")

    text = download_text(OTHER_LISTED_URL)

    lines = text.strip().splitlines()

    reader = csv.DictReader(
        lines,
        delimiter="|"
    )

    before = len(universe)

    for row in reader:

        symbol = row.get("ACT Symbol", "").strip()
        name = row.get("Security Name", "").strip()
        exchange = row.get("Exchange", "").strip().upper()
        etf = row.get("ETF", "").strip().upper()
        test_issue = row.get("Test Issue", "").strip().upper()

        # N = NYSE
        # A = NYSE American
        if exchange not in ["N", "A"]:
            continue

        if not symbol:
            continue

        if etf == "Y":
            continue

        if test_issue == "Y":
            continue

        bad_words = [
            "WARRANT",
            "RIGHT",
            "UNIT",
            "NOTE",
            "DEBENTURE",
            "PREFERRED"
        ]

        if any(word in name.upper() for word in bad_words):
            continue

        yahoo_symbol = normalize_symbol(symbol)

        universe[yahoo_symbol] = name

    print(f"NYSE/NYSE American stocks added: {len(universe) - before}")

    print(f"TOTAL USA STOCK UNIVERSE: {len(universe)}")

    return universe


# ============================================================
# DOWNLOAD HISTORICAL DATA
# ============================================================

def get_prices(symbol):

    url = (
        "https://eodhd.com/api/eod/"
        + symbol
        + "?api_token="
        + EODHD_API_KEY
        + "&fmt=json"
        + "&period=d"
    )

    try:

        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, list):
            print(f"DATA ERROR {symbol}: invalid response")
            return None

        prices = []
        vols = []
        highs = []
        lows = []

        for row in data:

            close = row.get("adjusted_close")

            if close is None:
                close = row.get("close")

            high = row.get("high")
            low = row.get("low")
            volume = row.get("volume")

            if (
                close is None
                or high is None
                or low is None
                or volume is None
            ):
                continue

            prices.append(float(close))
            highs.append(float(high))
            lows.append(float(low))
            vols.append(float(volume))

        if len(prices) < MIN_HISTORY:
            print(
                f"DATA ERROR {symbol}: "
                f"only {len(prices)} days"
            )
            return None

        return prices, vols, highs, lows

    except Exception as e:

        print(f"DATA ERROR {symbol}: {e}")

        return None

# ============================================================
# SMA
# ============================================================

def sma(values, period):

    if len(values) < period:
        return None

    return sum(values[-period:]) / period


# ============================================================
# RSI
# ============================================================

def calculate_rsi(prices, period=14):

    if len(prices) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(prices)):

        change = prices[i] - prices[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


# ============================================================
# ATR
# ============================================================

def calculate_atr(prices, highs, lows, period=20):

    if len(prices) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(prices)):

        previous_close = prices[i - 1]

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - previous_close),
            abs(lows[i] - previous_close)
        )

        true_ranges.append(tr)

    return statistics.mean(true_ranges[-period:])


# ============================================================
# ANALYZE STOCK
# ============================================================

def analyze(symbol, name, benchmark_prices=None):

    data = get_prices(symbol)

    if data is None:
        return None

    prices, volumes, highs, lows = data

    price = prices[-1]

    # --------------------------------------------------------
    # BASIC FILTER
    # --------------------------------------------------------

    if price < MIN_PRICE:
        return None

    avg_volume = statistics.mean(volumes[-20:])

    if avg_volume < MIN_AVG_VOLUME:
        return None

    # --------------------------------------------------------
    # INDICATORS
    # --------------------------------------------------------

    sma20 = sma(prices, 20)
    sma50 = sma(prices, 50)
    sma200 = sma(prices, 200)

    rsi = calculate_rsi(prices)

    momentum_1m = ((price / prices[-22]) - 1) * 100
    momentum_3m = ((price / prices[-66]) - 1) * 100

    volume_ratio = (
        volumes[-1] / avg_volume
        if avg_volume > 0
        else 0
    )

    # --------------------------------------------------------
    # TURTLE INDICATORS
    # --------------------------------------------------------

    previous_20_high = max(prices[-21:-1])
    previous_55_high = max(prices[-56:-1])

    breakout_20 = price > previous_20_high
    breakout_55 = price > previous_55_high

    atr20 = calculate_atr(
        prices,
        highs,
        lows,
        20
    )

    atr_pct = (
        (atr20 / price) * 100
        if atr20 is not None and price > 0
        else None
    )

    distance_sma200 = (
        ((price / sma200) - 1) * 100
    )

    # --------------------------------------------------------
    # WEINSTEIN STAGE ANALYSIS
    # --------------------------------------------------------
    # 30-week MA is approximated from 150 trading days.
    # Slope is measured against the value ~4 weeks earlier.

    sma30w = sma(prices, 150)

    sma30w_4w_ago = (
        sma(prices[:-20], 150)
        if len(prices) >= 170
        else None
    )

    stage2_ma_rising = (
        sma30w is not None
        and sma30w_4w_ago is not None
        and sma30w > sma30w_4w_ago
    )

    price_above_30w = (
        sma30w is not None
        and price > sma30w
    )

    previous_30w_high = (
        max(prices[-151:-1])
        if len(prices) >= 151
        else None
    )

    stage2_breakout = (
        previous_30w_high is not None
        and price > previous_30w_high
    )

    # Relative strength versus SPY over roughly 30 weeks.
    relative_strength = None
    relative_strength_positive = False

    if benchmark_prices and len(benchmark_prices) >= 150:
        stock_return_30w = (
            (price / prices[-150]) - 1
        ) * 100

        benchmark_return_30w = (
            (benchmark_prices[-1] / benchmark_prices[-150]) - 1
        ) * 100

        relative_strength = (
            stock_return_30w - benchmark_return_30w
        )

        relative_strength_positive = relative_strength > 0

    # ========================================================
    # TURTLE SCORE — 0 TO 5
    # ========================================================

    turtle_score = 0
    turtle_signals = []

    # 1. Turtle System 1: 20-day breakout
    if breakout_20:
        turtle_score += 1
        turtle_signals.append("20D breakout")

    # 2. Turtle System 2: 55-day breakout
    if breakout_55:
        turtle_score += 1
        turtle_signals.append("55D breakout")

    # 3. Long-term trend filter
    if price > sma200:
        turtle_score += 1
        turtle_signals.append("Above SMA200")

    # 4. Positive momentum
    if momentum_3m > 0:
        turtle_score += 1
        turtle_signals.append("Positive 3M momentum")

    # 5. Volatility in a usable range
    if atr_pct is not None and 1.0 <= atr_pct <= 8.0:
        turtle_score += 1
        turtle_signals.append("Healthy ATR")

    # ========================================================
    # WEINSTEIN SCORE — 0 TO 5
    # ========================================================

    weinstein_score = 0
    weinstein_signals = []

    # 1. Price above 30-week moving average
    if price_above_30w:
        weinstein_score += 1
        weinstein_signals.append("Price>30W MA")

    # 2. 30-week moving average rising
    if stage2_ma_rising:
        weinstein_score += 1
        weinstein_signals.append("30W MA rising")

    # 3. Price above long-term trend
    if price > sma200:
        weinstein_score += 1
        weinstein_signals.append("Above SMA200")

    # 4. Breakout from long consolidation / 30-week range
    if stage2_breakout:
        weinstein_score += 1
        weinstein_signals.append("30W breakout")

    # 5. Relative strength versus SPY
    if relative_strength_positive:
        weinstein_score += 1
        weinstein_signals.append("Relative strength")

    # ========================================================
    # FINAL SCORE — 0 TO 10
    # ========================================================

    score = turtle_score + weinstein_score

    signals = (
        ["TURTLE: " + s for s in turtle_signals]
        + ["WEINSTEIN: " + s for s in weinstein_signals]
    )

    # Strong entry requires both theories to agree.
    if turtle_score >= 4 and weinstein_score >= 4:
        signal = "STRONG ENTRY"

    elif score >= 7 and turtle_score >= 3 and weinstein_score >= 3:
        signal = "ENTRY WATCH"

    elif score >= 5:
        signal = "WATCH"

    else:
        signal = "AVOID"

    return {
        "symbol": symbol,
        "name": name,
        "price": price,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "rsi": rsi,
        "momentum_1m": momentum_1m,
        "momentum_3m": momentum_3m,
        "volume_ratio": volume_ratio,
        "breakout": breakout_20,
        "breakout_20": breakout_20,
        "breakout_55": breakout_55,
        "atr20": atr20,
        "atr_pct": atr_pct,
        "sma30w": sma30w,
        "stage2_ma_rising": stage2_ma_rising,
        "stage2_breakout": stage2_breakout,
        "relative_strength": relative_strength,
        "turtle_score": turtle_score,
        "weinstein_score": weinstein_score,
        "score": score,
        "signal": signal,
        "signals": signals,
        "turtle_signals": turtle_signals,
        "weinstein_signals": weinstein_signals
    }


# ============================================================
# MAIN
# ============================================================

def main():

    start = datetime.now(timezone.utc)

    print()
    print("=" * 70)
    print("HULKTRADER USA ENTRY RADAR")
    print(start.strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("=" * 70)

    # --------------------------------------------------------
    # BUILD UNIVERSE
    # --------------------------------------------------------

    universe = get_us_universe()

    # --------------------------------------------------------
    # MARKET BENCHMARK FOR WEINSTEIN RELATIVE STRENGTH
    # --------------------------------------------------------

    benchmark_data = get_prices("SPY")
    benchmark_prices = (
        benchmark_data[0]
        if benchmark_data is not None
        else None
    )

    print()
    print("=" * 70)
    print("STARTING TECHNICAL SCAN")
    print("=" * 70)

    results = []

    total = len(universe)

    for counter, (symbol, name) in enumerate(
        universe.items(),
        start=1
    ):

        print(
            f"[{counter}/{total}] "
            f"Analizzo {symbol}"
        )

        result = analyze(symbol, name, benchmark_prices)

        if result is not None:
            results.append(result)

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("HULKTRADER ENTRY RADAR")
    print("=" * 70)

    for result in results[:50]:

        print(
            f"{result['symbol']:10} "
            f"{result['price']:10.2f} "
            f"T {result['turtle_score']}/5 "
            f"W {result['weinstein_score']}/5 "
            f"TOTAL {result['score']:2}/10 "
            f"{result['signal']}"
        )

    # --------------------------------------------------------
    # TOP 20 DETAIL
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("TOP 20 OPPORTUNITIES")
    print("=" * 70)

    for i, result in enumerate(results[:20], start=1):

        print()
        print(
            f"{i:02d}. "
            f"{result['symbol']} - "
            f"{result['name']}"
        )

        print(
            f"    Price: {result['price']:.2f}"
        )

        print(
            f"    RSI: {result['rsi']:.1f}"
        )

        print(
            f"    Momentum 1M: "
            f"{result['momentum_1m']:.2f}%"
        )

        print(
            f"    Momentum 3M: "
            f"{result['momentum_3m']:.2f}%"
        )

        print(
            f"    Turtle Score: "
            f"{result['turtle_score']}/5"
        )

        print(
            f"    Weinstein Score: "
            f"{result['weinstein_score']}/5"
        )

        print(
            f"    Total Score: "
            f"{result['score']}/10"
        )

        print(
            f"    Signal: "
            f"{result['signal']}"
        )

        print(
            "    Turtle: "
            + ", ".join(result["turtle_signals"])
        )

        print(
            "    Weinstein: "
            + ", ".join(result["weinstein_signals"])
        )

        if result["relative_strength"] is not None:
            print(
                f"    Relative Strength vs SPY: "
                f"{result['relative_strength']:.2f}%"
            )

        if result["atr_pct"] is not None:
            print(
                f"    ATR20: "
                f"{result['atr_pct']:.2f}%"
            )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    elapsed = (
        datetime.now(timezone.utc) - start
    ).total_seconds()

    print()
    print("=" * 70)
    print("SCAN COMPLETE")
    print("=" * 70)

    print(
        f"Universe: {len(universe)}"
    )

    print(
        f"Valid stocks: {len(results)}"
    )

    print(
        f"Execution time: {elapsed:.1f} seconds"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
