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

# ============================================================
# TELEGRAM REPORT
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_message(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return False

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_BOT_TOKEN
        + "/sendMessage"
    )

    try:
        response = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "disable_web_page_preview": True
            },
            timeout=15
        )

        response.raise_for_status()

        payload = response.json()

        if not payload.get("ok"):
            print(f"TELEGRAM ERROR: {payload}")
            return False

        return True

    except Exception as e:
        print(f"TELEGRAM ERROR: {e}")
        return False


def send_telegram_report(results, universe_size, elapsed):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM: report not sent - configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return

    # --------------------------------------------------------
    # EARLY TREND candidates
    # --------------------------------------------------------

    early_candidates = [
        r for r in results
        if r["signal"] in ("EARLY STRONG TREND", "EARLY TREND WATCH")
    ]

    early_candidates.sort(
        key=lambda x: (
            x["early_score"],
            x["score"],
            x["turtle_early_score"],
            x["weinstein_early_score"]
        ),
        reverse=True
    )

    confirmed = [
        r for r in results
        if r["score"] >= 7
    ]

    confirmed.sort(
        key=lambda x: (x["score"], -x["rsi"] if x["rsi"] is not None else 0),
        reverse=True
    )

    lines = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("HULKTRADER ENTRY RADAR")
    lines.append("USA | " + now)
    lines.append("")
    lines.append(f"Universe: {universe_size:,}")
    lines.append(f"Valid stocks: {len(results):,}")
    lines.append(f"Scan time: {elapsed / 60:.1f} min")
    lines.append("")

    # --------------------------------------------------------
    # EARLY TREND
    # --------------------------------------------------------

    lines.append("EARLY TREND / PRE-BREAKOUT")
    lines.append(f"Candidates: {len(early_candidates)}")

    if early_candidates:
        for i, r in enumerate(early_candidates[:10], start=1):
            d20 = (
                f"{r['distance_to_20d_high']:.1f}%"
                if r["distance_to_20d_high"] is not None
                else "n/a"
            )
            d55 = (
                f"{r['distance_to_55d_high']:.1f}%"
                if r["distance_to_55d_high"] is not None
                else "n/a"
            )
            d30 = (
                f"{r['distance_to_30w_high']:.1f}%"
                if r["distance_to_30w_high"] is not None
                else "n/a"
            )

            lines.append(
                f"{i}. {r['symbol']} ${r['price']:.2f} | "
                f"Early {r['early_score']}/10 | "
                f"T {r['turtle_early_score']}/5 W {r['weinstein_early_score']}/5"
            )
            lines.append(f"   {r['signal']} | {r['entry_status']}")
            lines.append(
                f"   20D {d20} | 55D {d55} | 30W {d30} | RSI {r['rsi']:.1f}"
                if r['rsi'] is not None
                else f"   20D {d20} | 55D {d55} | 30W {d30} | RSI n/a"
            )
    else:
        lines.append("No strong early candidates in this scan.")

    lines.append("")

    # --------------------------------------------------------
    # CONFIRMED TREND
    # --------------------------------------------------------

    lines.append("CONFIRMED TREND / BREAKOUT")
    lines.append("")

    if confirmed:
        for i, r in enumerate(confirmed[:10], start=1):
            rsi_text = f"RSI {r['rsi']:.1f}" if r['rsi'] is not None else "RSI n/a"
            lines.append(
                f"{i}. {r['symbol']} ${r['price']:.2f} | "
                f"{r['score']}/10 | T {r['turtle_score']}/5 W {r['weinstein_score']}/5"
            )
            lines.append(f"   {r['signal']} | {r['entry_status']} | {rsi_text}")
    else:
        lines.append("No confirmed candidates with score >= 7.")

    lines.append("")
    lines.append("HulkTrader: Turtle + Weinstein + Early Trend")

    message = "\n".join(lines)

    # Telegram sendMessage has a message-size limit; split safely.
    max_chars = 3900
    chunks = []
    current = ""

    for block in message.split("\n\n"):
        candidate = block if not current else current + "\n\n" + block
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = block

    if current:
        chunks.append(current)

    for chunk in chunks:
        send_telegram_message(chunk)


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

    ticker = (
        symbol
        if symbol.endswith(".US")
        else symbol + ".US"
    )

    url = (
        "https://eodhd.com/api/eod/"
        + ticker
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
            print(f"DATA ERROR {ticker}: invalid response")
            return None

        prices = []
        vols = []
        highs = []
        lows = []

        for row in data:
            close = row.get("close")
            adjusted_close = row.get("adjusted_close")
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

            close = float(close)
            high = float(high)
            low = float(low)

            if close <= 0:
                continue

            adjusted_close = (
                float(adjusted_close)
                if adjusted_close is not None
                else close
            )

            # Mantiene prezzi, massimi e minimi
            # sulla stessa base di rettifica.
            adjustment_factor = adjusted_close / close

            prices.append(adjusted_close)
            highs.append(high * adjustment_factor)
            lows.append(low * adjustment_factor)
            vols.append(float(volume))

        if len(prices) < MIN_HISTORY:
            print(
                f"DATA ERROR {ticker}: "
                f"only {len(prices)} days"
            )
            return None

        return prices, vols, highs, lows

    except Exception as e:
        print(f"DATA ERROR {ticker}: {e}")
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

    
    distance_to_sma20_pct = (
        ((price / sma20) - 1) * 100
        if sma20 is not None and sma20 > 0
        else None
    )

    early_not_extended = (
        distance_to_sma20_pct is not None
        and distance_to_sma20_pct <= 8.0
    )

    rsi = calculate_rsi(prices)
    early_rsi_ok = (
        rsi is not None
        and rsi < 70
    )
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
    # EARLY TREND / PRE-BREAKOUT DETECTION
    # --------------------------------------------------------
    # The classic Turtle trigger is a breakout. That is useful,
    # but it is deliberately late. We therefore keep the strict
    # Turtle score AND calculate a separate pre-breakout setup.
    #
    # The setup looks for price approaching the breakout level,
    # rising short/medium-term averages and positive momentum.
    # It does NOT call a stock a breakout before the breakout.

    sma20_1m_ago = (
        sma(prices[:-20], 20)
        if len(prices) >= 40
        else None
    )

    sma50_1m_ago = (
        sma(prices[:-20], 50)
        if len(prices) >= 70
        else None
    )

    sma20_rising = (
        sma20 is not None
        and sma20_1m_ago is not None
        and sma20 > sma20_1m_ago
    )

    sma50_rising = (
        sma50 is not None
        and sma50_1m_ago is not None
        and sma50 > sma50_1m_ago
    )

    
    distance_to_20d_high = (
        ((price / previous_20_high) - 1) * 100
        if previous_20_high > 0
        else None
    )

    distance_to_55d_high = (
        ((price / previous_55_high) - 1) * 100
        if previous_55_high > 0
        else None
    )

    range_20d_pct = (
        ((max(prices[-20:]) - min(prices[-20:])) / price) * 100
        if price > 0
        else None
    )

    
    near_20d_breakout = (
        distance_to_20d_high is not None
        and 0 <= distance_to_20d_high <= 3.0
        and not breakout_20
    )

    near_55d_breakout = (
        distance_to_55d_high is not None
        and 0 <= distance_to_55d_high <= 7.0
        and not breakout_55
    )


    tight_base = (
        range_20d_pct is not None
        and range_20d_pct <= 15.0
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
    # EARLY TURTLE SETUP — 0 TO 5
    # ========================================================
    # These are pre-breakout conditions. They are intentionally
    # separate from the classic Turtle breakout score.

    turtle_early_score = 0
    turtle_early_signals = []

    if near_20d_breakout and not breakout_20:
        turtle_early_score += 1
        turtle_early_signals.append("Within 3% of 20D breakout")

    if near_55d_breakout and not breakout_55:
        turtle_early_score += 1
        turtle_early_signals.append("Within 7% of 55D breakout")

    if sma20_rising:
        turtle_early_score += 1
        turtle_early_signals.append("SMA20 rising")

    if price > sma50:
        turtle_early_score += 1
        turtle_early_signals.append("Above SMA50")

    if momentum_3m > 5:
        turtle_early_score += 1
        turtle_early_signals.append("Positive 3M momentum")

    # ========================================================
    # EARLY WEINSTEIN SETUP — 0 TO 5
    # ========================================================
    # Weinstein's Stage 2 is fundamentally a trend condition.
    # We also look for price close to the 30-week breakout level
    # and a strengthening intermediate trend.

    weinstein_early_score = 0
    weinstein_early_signals = []

    if price_above_30w:
        weinstein_early_score += 1
        weinstein_early_signals.append("Price>30W MA")

    if stage2_ma_rising:
        weinstein_early_score += 1
        weinstein_early_signals.append("30W MA rising")

    if sma50_rising:
        weinstein_early_score += 1
        weinstein_early_signals.append("SMA50 rising")

    if relative_strength_positive:
        weinstein_early_score += 1
        weinstein_early_signals.append("Relative strength improving")

    distance_to_30w_high = (
        ((price / previous_30w_high) - 1) * 100
        if previous_30w_high is not None
        and previous_30w_high > 0
        else None
    )

    
    near_30w_breakout = (
        distance_to_30w_high is not None
        and 0 <= distance_to_30w_high <= 8.0
        and not stage2_breakout
    )



    if near_30w_breakout and not stage2_breakout:
        weinstein_early_score += 1
        weinstein_early_signals.append("Within 8% of 30W breakout")

    # ========================================================
    # FINAL SCORE — 0 TO 10
    # ========================================================

    score = turtle_score + weinstein_score
    early_score = turtle_early_score + weinstein_early_score

    signals = (
        ["TURTLE: " + s for s in turtle_signals]
        + ["WEINSTEIN: " + s for s in weinstein_signals]
    )

    early_signals = (
        ["TURTLE EARLY: " + s for s in turtle_early_signals]
        + ["WEINSTEIN EARLY: " + s for s in weinstein_early_signals]
    )

    # --------------------------------------------------------
    # ENTRY STATUS
    # Trend quality and entry timing are deliberately separated.
    # EARLY TREND SETUP is used when the stock is building the
    # conditions for a breakout but has not broken out yet.
    # --------------------------------------------------------

    if score >= 9:
        if rsi is not None and rsi >= 75:
            signal = "STRONG TREND - WAIT"
            entry_status = "WAIT FOR PULLBACK"
        elif rsi is not None and rsi >= 70:
            signal = "STRONG TREND - CAUTION"
            entry_status = "CAUTION"
        else:
            signal = "STRONG ENTRY"
            entry_status = "ENTRY NOW"

    elif (
        early_score >= 8
        and turtle_score >= 2
        and weinstein_score >= 3
        and not breakout_20
        and not breakout_55
        and not stage2_breakout
        and early_rsi_ok
        and early_not_extended
    ):
        signal = "EARLY STRONG TREND"
        entry_status = "PRE-BREAKOUT WATCH"

    elif score >= 7:
        if rsi is not None and rsi >= 75:
            signal = "ENTRY WATCH - EXTENDED"
            entry_status = "WAIT FOR PULLBACK"
        else:
            signal = "ENTRY WATCH"
            entry_status = "WATCH FOR ENTRY"

    elif (
        early_score >= 6
        and tight_base
        and early_not_extended
        and early_rsi_ok
        and not breakout_20
        and not breakout_55
        and not stage2_breakout
    ):
        signal = "EARLY TREND WATCH"
        entry_status = "WATCH BREAKOUT"

    elif score >= 5:
        signal = "WATCH"
        entry_status = "WAIT"

    else:
        signal = "AVOID"
        entry_status = "NO ENTRY"

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
        "distance_to_20d_high": distance_to_20d_high,
        "distance_to_55d_high": distance_to_55d_high,
        "distance_to_30w_high": distance_to_30w_high,
        "range_20d_pct": range_20d_pct,
        "sma20_rising": sma20_rising,
        "sma50_rising": sma50_rising,
        "turtle_score": turtle_score,
        "weinstein_score": weinstein_score,
        "score": score,
        "turtle_early_score": turtle_early_score,
        "weinstein_early_score": weinstein_early_score,
        "early_score": early_score,
        "signal": signal,
        "entry_status": entry_status,
        "signals": signals,
        "early_signals": early_signals,
        "turtle_signals": turtle_signals,
        "weinstein_signals": weinstein_signals,
        "turtle_early_signals": turtle_early_signals,
        "weinstein_early_signals": weinstein_early_signals
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
        key=lambda x: (x["score"], x["early_score"]),
        reverse=True
    )

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("HULKTRADER ENTRY RADAR")
    print("=" * 70)

    for result in results[:10]:

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
    print("TOP 10 OPPORTUNITIES")
    print("=" * 70)

    for i, result in enumerate(results[:10], start=1):

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
            f"    Early Trend Score: "
            f"{result['early_score']}/10 "
            f"(T {result['turtle_early_score']}/5, "
            f"W {result['weinstein_early_score']}/5)"
        )

        print(
            f"    Signal: "
            f"{result['signal']}"
        )

        print(
            f"    Entry Status: "
            f"{result['entry_status']}"
        )

        print(
            "    Turtle: "
            + ", ".join(result["turtle_signals"])
        )

        print(
            "    Weinstein: "
            + ", ".join(result["weinstein_signals"])
        )

        if result["early_signals"]:
            print(
                "    Early setup: "
                + ", ".join(result["early_signals"])
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

    # --------------------------------------------------------
    # TELEGRAM REPORT
    # --------------------------------------------------------

    send_telegram_report(
        results,
        len(universe),
        elapsed
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
