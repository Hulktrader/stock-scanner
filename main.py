import requests
import statistics
from datetime import datetime, timezone

# ============================================================
# HULKTRADER STOCK SCANNER V2
# USA + EUROPE
# Technical Entry Radar
# ============================================================

USER_AGENT = "Mozilla/5.0 (HulkTrader Stock Scanner)"

# ------------------------------------------------------------
# STOCK UNIVERSE
# ------------------------------------------------------------

STOCKS = {

    # ================= USA =================
    "AAPL.US": "AAPL",
    "MSFT.US": "MSFT",
    "NVDA.US": "NVDA",
    "AMZN.US": "AMZN",
    "GOOGL.US": "GOOGL",
    "META.US": "META",
    "TSLA.US": "TSLA",
    "AVGO.US": "AVGO",
    "AMD.US": "AMD",
    "NFLX.US": "NFLX",
    "ADBE.US": "ADBE",
    "CRM.US": "CRM",
    "ORCL.US": "ORCL",
    "INTC.US": "INTC",
    "QCOM.US": "QCOM",
    "MU.US": "MU",
    "AMAT.US": "AMAT",
    "LRCX.US": "LRCX",
    "NOW.US": "NOW",
    "PLTR.US": "PLTR",
    "PANW.US": "PANW",
    "CRWD.US": "CRWD",
    "UBER.US": "UBER",
    "ABNB.US": "ABNB",
    "COST.US": "COST",
    "WMT.US": "WMT",
    "JPM.US": "JPM",
    "V.US": "V",
    "MA.US": "MA",
    "NFLX.US": "NFLX",

    # ================= ITALIA =================
    "ENI.MI": "ENI",
    "ENEL.MI": "ENEL",
    "ISP.MI": "INTESA",
    "UCG.MI": "UNICREDIT",
    "STLAM.MI": "STELLANTIS",
    "RACE.MI": "FERRARI",
    "LDO.MI": "LEONARDO",
    "STM.MI": "STM",
    "TIT.MI": "TELECOM ITALIA",
    "G.MI": "GENERALI",
    "MONC.MI": "MONCLER",
    "PRY.MI": "PRYSMIAN",
    "ERG.MI": "ERG",
    "BAMI.MI": "BANCO BPM",
    "BMED.MI": "MEDIOBANCA",

    # ================= GERMANIA =================
    "SAP.DE": "SAP",
    "SIE.DE": "SIEMENS",
    "ALV.DE": "ALLIANZ",
    "DTE.DE": "DEUTSCHE TELEKOM",
    "MBG.DE": "MERCEDES",
    "BMW.DE": "BMW",
    "VOW3.DE": "VOLKSWAGEN",
    "AIR.DE": "AIRBUS",
    "ADS.DE": "ADIDAS",
    "DBK.DE": "DEUTSCHE BANK",
    "RWE.DE": "RWE",

    # ================= FRANCIA =================
    "MC.PA": "LVMH",
    "OR.PA": "L'OREAL",
    "TTE.PA": "TOTALENERGIES",
    "AIR.PA": "AIRBUS",
    "SU.PA": "SCHNEIDER",
    "SAN.PA": "SANOFI",
    "BNP.PA": "BNP PARIBAS",
    "AI.PA": "AIR LIQUIDE",
    "DG.PA": "VINCI",
    "CAP.PA": "CAPGEMINI",

    # ================= SPAGNA =================
    "IBE.MC": "IBERDROLA",
    "ITX.MC": "INDITEX",
    "SAN.MC": "SANTANDER",
    "BBVA.MC": "BBVA",
    "REP.MC": "REPSOL",
    "TEF.MC": "TELEFONICA",

    # ================= OLANDA =================
    "ASML.AS": "ASML",
    "ADYEN.AS": "ADYEN",
    "INGA.AS": "ING",
    "PHIA.AS": "PHILIPS",

    # ================= UK =================
    "SHEL.L": "SHELL",
    "AZN.L": "ASTRAZENECA",
    "HSBA.L": "HSBC",
    "BP.L": "BP",
    "ULVR.L": "UNILEVER",
    "RIO.L": "RIO TINTO",

    # ================= SVIZZERA =================
    "NESN.SW": "NESTLE",
    "NOVN.SW": "NOVARTIS",
    "ROG.SW": "ROCHE",
    "UBSG.SW": "UBS",
    "ABBN.SW": "ABB",
}


# ------------------------------------------------------------
# DOWNLOAD DATA
# ------------------------------------------------------------

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

        closes = data["indicators"]["quote"][0]["close"]
        volumes = data["indicators"]["quote"][0]["volume"]

        prices = []
        vols = []

        for price, volume in zip(closes, volumes):

            if price is not None:
                prices.append(float(price))

            if volume is not None:
                vols.append(float(volume))

        if len(prices) < 210:
            return None

        return prices, vols

    except Exception as e:

        print(f"ERRORE {symbol}: {e}")

        return None


# ------------------------------------------------------------
# SIMPLE MOVING AVERAGE
# ------------------------------------------------------------

def sma(values, period):

    if len(values) < period:
        return None

    return sum(values[-period:]) / period


# ------------------------------------------------------------
# RSI
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# ANALYSIS
# ------------------------------------------------------------

def analyze(symbol, name):

    result = get_prices(symbol)

    if result is None:
        return None

    prices, volumes = result

    price = prices[-1]

    sma20 = sma(prices, 20)
    sma50 = sma(prices, 50)
    sma200 = sma(prices, 200)

    rsi = calculate_rsi(prices)

    # Momentum
    momentum_1m = ((price / prices[-22]) - 1) * 100
    momentum_3m = ((price / prices[-66]) - 1) * 100

    # Volume
    avg_volume = statistics.mean(volumes[-20:])
    current_volume = volumes[-1]

    volume_ratio = (
        current_volume / avg_volume
        if avg_volume > 0
        else 0
    )

    # 20 day breakout
    previous_20_high = max(prices[-21:-1])

    breakout = price > previous_20_high

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    score = 0
    signals = []

    # PRICE > SMA20
    if price > sma20:
        score += 1
        signals.append("Price>SMA20")

    # SMA20 > SMA50
    if sma20 > sma50:
        score += 1
        signals.append("SMA20>SMA50")

    # SMA50 > SMA200
    if sma50 > sma200:
        score += 1
        signals.append("SMA50>SMA200")

    # PRICE > SMA200
    if price > sma200:
        score += 1
        signals.append("Long-term trend")

    # Momentum 1 month
    if momentum_1m > 3:
        score += 1
        signals.append("Momentum 1M")

    # Momentum 3 months
    if momentum_3m > 5:
        score += 1
        signals.append("Momentum 3M")

    # RSI
    if 50 <= rsi <= 70:
        score += 1
        signals.append("RSI healthy")

    # Volume
    if volume_ratio >= 1.5:
        score += 1
        signals.append("Volume spike")

    # Breakout
    if breakout:
        score += 1
        signals.append("20D breakout")

    # Distance from SMA200
    distance_sma200 = ((price / sma200) - 1) * 100

    if 0 < distance_sma200 < 25:
        score += 1
        signals.append("Healthy distance")

    # --------------------------------------------------------
    # CLASSIFICATION
    # --------------------------------------------------------

    if score >= 8:
        signal = "🔥 STRONG ENTRY"

    elif score >= 6:
        signal = "🟢 ENTRY WATCH"

    elif score >= 4:
        signal = "🟡 WATCH"

    else:
        signal = "🔴 AVOID"

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


# ------------------------------------------------------------
# MAIN SCANNER
# ------------------------------------------------------------

def main():

    print()
    print("=" * 70)
    print("HULKTRADER ENTRY RADAR V2")
    print(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("=" * 70)

    results = []

    for symbol, name in STOCKS.items():

        print(f"Analizzo {symbol} ...")

        data = analyze(symbol, name)

        if data:
            results.append(data)

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    print()
    print("=" * 70)
    print("ENTRY RADAR")
    print("=" * 70)

    for r in results:

        print(
            f"{r['signal']:18} "
            f"{r['symbol']:12} "
            f"{r['price']:9.2f} "
            f"SCORE {r['score']}/10"
        )

    print()
    print("=" * 70)
    print("TOP 20")
    print("=" * 70)

    for i, r in enumerate(results[:20], 1):

        print(
            f"{i:02d}. "
            f"{r['symbol']:12} "
            f"{r['name'][:20]:20} "
            f"Price {r['price']:9.2f} | "
            f"RSI {r['rsi']:5.1f} | "
            f"Score {r['score']}/10"
        )

        print(
            "    "
            + ", ".join(r["signals"])
        )

    print()
    print("=" * 70)
    print(f"Titoli analizzati: {len(results)}")
    print("=" * 70)


if __name__ == "__main__":
    main()

