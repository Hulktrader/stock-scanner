import requests
import statistics
import csv
import io
from datetime import datetime, timezone

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
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + symbol
        + "?range=1y&interval=1d&events=history"
    )

    try:

        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=15
        )

        response.raise_for_status()

        data = response.json()["chart"]["result"][0]

        quote = data["indicators"]["quote"][0]

        closes = quote["close"]
        volumes = quote["volume"]

        prices = []
        vols = []

        for price, volume in zip(closes, volumes):

            if price is not None:
                prices.append(float(price))

            if volume is not None:
                vols.append(float(volume))

        if len(prices) < MIN_HISTORY:
            return None

        return prices, vols

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
# ANALYZE STOCK
# ============================================================

def analyze(symbol, name):

    data = get_prices(symbol)

    if data is None:
        return None

    prices, volumes = data

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

    previous_20_high = max(prices[-21:-1])

    breakout = price > previous_20_high

    distance_sma200 = (
        ((price / sma200) - 1) * 100
    )

    # ========================================================
    # SCORE
    # ========================================================

    score = 0
    signals = []

    # 1
    if price > sma20:
        score += 1
        signals.append("Price>SMA20")

    # 2
    if sma20 > sma50:
        score += 1
        signals.append("SMA20>SMA50")

    # 3
    if sma50 > sma200:
        score += 1
        signals.append("SMA50>SMA200")

    # 4
    if price > sma200:
        score += 1
        signals.append("Above SMA200")

    # 5
    if momentum_1m > 3:
        score += 1
        signals.append("Momentum 1M")

    # 6
    if momentum_3m > 5:
        score += 1
        signals.append("Momentum 3M")

    # 7
    if rsi is not None and 50 <= rsi <= 70:
        score += 1
        signals.append("Healthy RSI")

    # 8
    if volume_ratio >= 1.5:
        score += 1
        signals.append("Volume spike")

    # 9
    if breakout:
        score += 1
        signals.append("20D breakout")

    # 10
    if 0 < distance_sma200 < 25:
        score += 1
        signals.append("Healthy distance")

    # ========================================================
    # CLASSIFICATION
    # ========================================================

    if score >= 8:
        signal = "STRONG ENTRY"

    elif score >= 6:
        signal = "ENTRY WATCH"

    elif score >= 4:
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
        "breakout": breakout,
        "score": score,
        "signal": signal,
        "signals": signals
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

        result = analyze(symbol, name)

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
            f"SCORE {result['score']:2}/10 "
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
            f"    Score: "
            f"{result['score']}/10"
        )

        print(
            f"    Signal: "
            f"{result['signal']}"
        )

        print(
            "    Signals: "
            + ", ".join(result["signals"])
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
