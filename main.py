import os
import requests
from datetime import datetime

API_KEY = os.getenv("EODHD_API_KEY")

if not API_KEY:
    raise RuntimeError("EODHD_API_KEY non configurata")

SYMBOLS = [
    "AAPL.US",
    "MSFT.US",
    "NVDA.US",
    "AMZN.US",
    "GOOGL.US",
    "META.US",
    "TSLA.US",
]

BASE_URL = "https://eodhd.com/api/eod"


def get_history(symbol):
    params = {
        "api_token": API_KEY,
        "fmt": "json",
        "period": "d",
        "order": "a",
    }

    response = requests.get(
        f"{BASE_URL}/{symbol}",
        params=params,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def analyze(symbol, data):
    if not data:
        return None

    closes = [float(x["close"]) for x in data if x.get("close") is not None]

    if len(closes) < 200:
        return None

    price = closes[-1]

    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50
    sma200 = sum(closes[-200:]) / 200

    score = 0

    if price > sma20:
        score += 1

    if price > sma50:
        score += 1

    if price > sma200:
        score += 2

    if sma50 > sma200:
        score += 2

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "sma20": round(sma20, 2),
        "sma50": round(sma50, 2),
        "sma200": round(sma200, 2),
        "score": score,
    }


def main():
    print("=" * 60)
    print("HULKTRADER STOCK SCANNER")
    print(datetime.now().isoformat())
    print("=" * 60)

    results = []

    for symbol in SYMBOLS:
        try:
            print(f"Analizzo {symbol}...")

            data = get_history(symbol)
            result = analyze(symbol, data)

            if result:
                results.append(result)

        except Exception as e:
            print(f"ERRORE {symbol}: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)

    print("\nRISULTATI")
    print("-" * 60)

    for r in results:
        print(
            f'{r["symbol"]:10} '
            f'Price {r["price"]:8.2f} | '
            f'SMA20 {r["sma20"]:8.2f} | '
            f'SMA50 {r["sma50"]:8.2f} | '
            f'SMA200 {r["sma200"]:8.2f} | '
            f'SCORE {r["score"]}'
        )


if __name__ == "__main__":
    main()

