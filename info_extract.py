"""
================================================
  FRAUD DETECTION FINANCE PIPELINE
  FIXED VERSION — All loading problems solved
  SIMPLIFIED SCHEMA — Removed unnecessary columns
================================================

REMOVED COLUMNS (clean_historical_prices):
  - open, high, low (not needed for fraud detection)
  - volume_surge (redundant, can be calculated)
  - created_at (duplicate of date)

KEPT COLUMNS:
  id, symbol, date, close, volume, daily_return,
  volatility_5d, is_suspicious, suspicion_reason, source

SETUP:
  pip install requests yfinance python-dotenv apscheduler

  Run:
    python fraud_pipeline.py
"""

import os
import re
import time
import json
import math
import sqlite3
import logging
import statistics
import threading
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

try:
    import requests
except ImportError:
    raise ImportError("Run: pip install requests")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
except ImportError:
    raise ImportError("Run: pip install apscheduler")

# =========================================================
# 0. CONFIGURATION
# =========================================================
load_dotenv()

ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "H1BQQSK5MSQUR10G")
FINNHUB_KEY       = os.getenv("FINNHUB_KEY",       "d78af81r01qs9virkca0d78af81r01qs9virkcag")
FMP_KEY           = os.getenv("FMP_KEY",           "Ix0Xzv8m9of6Zjb3qpn7A3K393CE0oQe")

DB_NAME  = "fraud_detection_finance.db"
DB_TIMEOUT = 30.0  # Timeout for SQLite connections to handle concurrent access
LOG_FILE = "fraud_pipeline.log"
DATA_DIR = Path("clean_financial_data")
DATA_DIR.mkdir(exist_ok=True)

STOCK_SYMBOLS  = ["AAPL", "TSLA", "GME", "AMC", "NIO",
                  "MRNA", "COIN", "MSTR"]
CRYPTO_SYMBOLS = ["BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD"]

THRESHOLDS = {
    "volume_surge_multiplier": 3.0,
    "price_change_percent":    7.0,
    "z_score_threshold":       2.5,
    "volatility_spike":        15.0,
    "daily_return_limit":      10.0
}

FETCH_INTERVAL_HOURS = 10
ALPHA_VANTAGE_BASE   = "https://www.alphavantage.co/query"
FINNHUB_BASE         = "https://finnhub.io/api/v1"
FMP_BASE             = "https://financialmodelingprep.com/api/v3"

# ── Alpha Vantage daily call quota tracker ───────────────
_av_state = {"count": 0, "date": ""}
_av_lock  = threading.Lock()
AV_DAILY_LIMIT = 24

def av_call_allowed() -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    with _av_lock:
        if _av_state["date"] != today:
            _av_state["count"] = 0
            _av_state["date"]  = today
        return _av_state["count"] < AV_DAILY_LIMIT

def av_increment():
    with _av_lock:
        _av_state["count"] += 1

def av_remaining() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    with _av_lock:
        if _av_state["date"] != today:
            return AV_DAILY_LIMIT
        return max(0, AV_DAILY_LIMIT - _av_state["count"])

# =========================================================
# 1. LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# =========================================================
# 2. RETRY WRAPPER
# =========================================================

def with_retry(func, *args, retries=3, base_delay=5, **kwargs):
    """Call func with exponential backoff. Returns result or None."""
    for attempt in range(retries):
        try:
            result = func(*args, **kwargs)
            if result is not None:
                return result
        except requests.exceptions.Timeout:
            wait = base_delay * (2 ** attempt)
            log.warning(f"  Timeout attempt {attempt+1} — retry in {wait}s")
            time.sleep(wait)
        except requests.exceptions.ConnectionError as e:
            wait = base_delay * (2 ** attempt)
            log.warning(f"  Connection error — retry in {wait}s: {e}")
            time.sleep(wait)
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else 0
            if code in (429, 503):
                log.warning(f"  HTTP {code} rate limit — waiting 65s")
                time.sleep(65)
            else:
                log.error(f"  HTTP {code}: {e}")
                return None
        except Exception as e:
            log.error(f"  Unexpected error in {func.__name__}: {e}")
            return None
    log.error(f"  All {retries} retries failed: {func.__name__}")
    return None

# =========================================================
# 3. DATABASE (SIMPLIFIED SCHEMA)
# =========================================================

def init_database():
    conn = sqlite3.connect(DB_NAME, timeout=DB_TIMEOUT)
    c    = conn.cursor()

    # Enable WAL mode for better concurrent access (readers don't block writers)
    c.execute("PRAGMA journal_mode=WAL")

    # Real-time quotes table (unchanged)
    c.execute("""CREATE TABLE IF NOT EXISTS clean_realtime_quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL, price REAL NOT NULL,
        open REAL, high REAL, low REAL, volume INTEGER,
        prev_close REAL, change_pct REAL,
        volume_anomaly INTEGER DEFAULT 0,
        price_anomaly  INTEGER DEFAULT 0,
        z_score_price  REAL, z_score_volume REAL,
        source TEXT, fetched_at TEXT NOT NULL,
        UNIQUE(symbol, fetched_at))""")

    # Historical prices table (SIMPLIFIED - removed open, high, low, volume_surge, created_at)
    c.execute("""CREATE TABLE IF NOT EXISTS clean_historical_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        close REAL NOT NULL,
        volume INTEGER,
        daily_return REAL,
        volatility_5d REAL,
        is_suspicious INTEGER DEFAULT 0,
        suspicion_reason TEXT,
        source TEXT,
        UNIQUE(symbol, date))""")

    # Fraud alerts table (unchanged)
    c.execute("""CREATE TABLE IF NOT EXISTS fraud_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL, alert_type TEXT NOT NULL,
        severity INTEGER DEFAULT 50, description TEXT,
        evidence_data TEXT, detected_at TEXT NOT NULL,
        is_investigated INTEGER DEFAULT 0,
        UNIQUE(symbol, alert_type, detected_at))""")

    # Data sync status table (unchanged)
    c.execute("""CREATE TABLE IF NOT EXISTS data_sync_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL, last_sync_date TEXT,
        total_records INTEGER, first_record_date TEXT,
        last_record_date TEXT,
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(symbol))""")

    # Data quality issues table (unchanged)
    c.execute("""CREATE TABLE IF NOT EXISTS data_quality_issues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT, symbol TEXT, issue_type TEXT,
        error_msg TEXT, logged_at TEXT DEFAULT (datetime('now')))""")

    # Cleaning rejections table (unchanged)
    c.execute("""CREATE TABLE IF NOT EXISTS cleaning_rejections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at TEXT, symbol TEXT, data_type TEXT,
        raw_value TEXT, reason TEXT,
        logged_at TEXT DEFAULT (datetime('now')))""")

    # Anomaly thresholds table (unchanged)
    c.execute("""CREATE TABLE IF NOT EXISTS anomaly_thresholds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT UNIQUE NOT NULL,
        threshold_value REAL NOT NULL,
        updated_at TEXT DEFAULT (datetime('now')))""")

    # Pipeline run log table (unchanged)
    c.execute("""CREATE TABLE IF NOT EXISTS pipeline_run_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at TEXT, job_type TEXT, symbols TEXT,
        records_fetched INTEGER DEFAULT 0,
        records_saved INTEGER DEFAULT 0,
        records_rejected INTEGER DEFAULT 0,
        alerts_generated INTEGER DEFAULT 0,
        av_calls_used INTEGER DEFAULT 0,
        duration_sec REAL, errors TEXT,
        created_at TEXT DEFAULT (datetime('now')))""")

    for metric, value in THRESHOLDS.items():
        c.execute("""INSERT OR IGNORE INTO anomaly_thresholds
            (metric_name, threshold_value) VALUES (?,?)""",
            (metric, value))

    conn.commit()
    conn.close()
    log.info("✅ Database ready (simplified schema)")

def log_error_to_db(source, symbol, msg):
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=DB_TIMEOUT)
        conn.execute("""INSERT INTO data_quality_issues
            (source,symbol,issue_type,error_msg) VALUES (?,?,'DATA_ERROR',?)""",
            (source, symbol, str(msg)[:500]))
        conn.commit()
    except Exception:
        pass
    finally:
        if conn:
            conn.close()

# =========================================================
# 4. CLEANING ENGINE
# =========================================================

class CleaningReport:
    def __init__(self):
        self.received = 0
        self.passed   = 0
        self.rejected = 0
        self.items    = []

    def reject(self, symbol, dtype, raw_val, reason):
        self.rejected += 1
        self.items.append({"symbol": symbol, "data_type": dtype,
                           "raw_value": str(raw_val)[:200],
                           "reason": reason})

    def accept(self):
        self.passed += 1

    def summary(self):
        return (f"rcv={self.received} ok={self.passed} "
                f"rej={self.rejected}")

    def save_to_db(self, run_at):
        if not self.items:
            return
        conn = sqlite3.connect(DB_NAME, timeout=DB_TIMEOUT)
        for it in self.items:
            try:
                conn.execute("""INSERT INTO cleaning_rejections
                    (run_at,symbol,data_type,raw_value,reason)
                    VALUES (?,?,?,?,?)""",
                    (run_at, it["symbol"], it["data_type"],
                     it["raw_value"], it["reason"]))
            except Exception:
                pass
        conn.commit()
        conn.close()


def is_valid_price(v) -> bool:
    try:
        f = float(v)
        return math.isfinite(f) and 0 < f < 1_000_000
    except (TypeError, ValueError):
        return False

def is_valid_volume(v) -> bool:
    try:
        return int(float(v)) >= 0
    except (TypeError, ValueError):
        return False

def is_valid_date(s) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(s)))


def clean_quote(raw: dict, symbol: str,
                report: CleaningReport) -> dict | None:
    report.received += 1
    price = raw.get("price") or raw.get("c")

    if not is_valid_price(price):
        report.reject(symbol, "quote", price,
                      f"Invalid/missing price: {price}")
        return None
    price = float(price)
    if price > 100_000:
        report.reject(symbol, "quote", price, "Price ceiling $100k breached")
        return None

    high  = float(raw.get("high") or raw.get("h") or 0)
    low   = float(raw.get("low")  or raw.get("l") or 0)
    if high > 0 and low > 0 and high < low:
        report.reject(symbol, "quote", f"h={high} l={low}",
                      "High < Low — corrupt")
        return None

    try:
        chg_p = float(raw.get("change_pct") or
                      raw.get("dp") or 0)
    except (TypeError, ValueError):
        chg_p = 0.0
    if abs(chg_p) > 50:
        report.reject(symbol, "quote", chg_p,
                      f"Change% unrealistic: {chg_p}")
        return None

    report.accept()
    return {
        "symbol":     symbol,
        "price":      round(price, 6),
        "open":       round(float(raw.get("open") or
                                   raw.get("o") or price), 6),
        "high":       round(high, 6) if high > 0 else None,
        "low":        round(low,  6) if low  > 0 else None,
        "volume":     int(float(raw.get("volume") or
                                 raw.get("v") or 0)),
        "prev_close": round(float(raw.get("prev_close") or
                                   raw.get("pc") or 0), 6),
        "change_pct": round(chg_p, 4),
        "source":     raw.get("source", "Unknown"),
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def clean_ohlcv_batch(records: list, symbol: str,
                       report: CleaningReport) -> list:
    if not records:
        return []

    closes = []
    for r in records:
        try:
            v = float(r.get("close", 0) or 0)
            if v > 0:
                closes.append(v)
        except (TypeError, ValueError):
            pass
    median_close = statistics.median(closes) if closes else 0

    cleaned = []
    for row in records:
        report.received += 1
        date_val = str(row.get("date", ""))[:10]

        if not is_valid_date(date_val):
            report.reject(symbol, "ohlcv", date_val, f"Bad date: {date_val}")
            continue

        close = row.get("close")
        if not is_valid_price(close):
            report.reject(symbol, "ohlcv", date_val, f"Bad close: {close}")
            continue
        close = float(close)

        volume = int(float(row["volume"])) if is_valid_volume(row.get("volume")) else 0

        if median_close > 0:
            if close > median_close * 8:
                report.reject(symbol, "ohlcv", f"{date_val} c={close}",
                              f"Outlier > 8x median {median_close:.2f}")
                continue
            if close < median_close * 0.05:
                report.reject(symbol, "ohlcv", f"{date_val} c={close}",
                              f"Outlier < 5% of median {median_close:.2f}")
                continue

        if volume < 0:
            report.reject(symbol, "ohlcv", f"{date_val} vol={volume}",
                          "Negative volume")
            continue

        report.accept()
        # SIMPLIFIED: removed open, high, low
        cleaned.append({"symbol": symbol, "date": date_val,
                        "close": round(close, 6),
                        "volume": volume, "source": row.get("source", "Unknown")})

    # Deduplicate — keep highest-volume row per date
    before = len(cleaned)
    seen   = {}
    for row in cleaned:
        d = row["date"]
        if d not in seen or row["volume"] > seen[d]["volume"]:
            seen[d] = row
    cleaned = sorted(seen.values(), key=lambda x: x["date"])

    dupes = before - len(cleaned)
    if dupes:
        report.rejected += dupes

    removed = len(records) - len(cleaned)
    if removed > 0:
        log.info(f"    {symbol}: {removed}/{len(records)} rows removed "
                 f"→ {len(cleaned)} clean rows remain")
    return cleaned

# =========================================================
# 5. ANOMALY DETECTION
# =========================================================

def calc_z(value, mean, std) -> float:
    if not std or std == 0:
        return 0.0
    return abs(float(value) - float(mean)) / float(std)

def detect_volume_anomaly(vol, hist_vols, threshold=3.0):
    if not hist_vols or len(hist_vols) < 5:
        return False, 0.0
    valid = [v for v in hist_vols if v > 0]
    if not valid:
        return False, 0.0
    avg = sum(valid) / len(valid)
    if avg == 0:
        return False, 0.0
    ratio = float(vol) / avg
    return ratio > threshold, ratio

def detect_price_manipulation(price, hist_prices, threshold=7.0):
    if not hist_prices or len(hist_prices) < 5:
        return False, 0.0
    recent_avg = sum(hist_prices[-5:]) / 5
    if recent_avg == 0:
        return False, 0.0
    chg = abs((float(price) - recent_avg) / recent_avg) * 100
    return chg > threshold, chg

def get_historical_context(symbol, days=10):
    try:
        conn    = sqlite3.connect(DB_NAME, timeout=DB_TIMEOUT)
        prices  = conn.execute("""SELECT close FROM clean_historical_prices
            WHERE symbol=? AND close IS NOT NULL
            ORDER BY date DESC LIMIT ?""", (symbol, days)).fetchall()
        volumes = conn.execute("""SELECT volume FROM clean_historical_prices
            WHERE symbol=? AND volume>0
            ORDER BY date DESC LIMIT ?""", (symbol, days)).fetchall()
        conn.close()
        return ([p[0] for p in prices], [v[0] for v in volumes])
    except Exception:
        return [], []

# =========================================================
# 6. REAL-TIME API FETCHERS
# =========================================================

def _finnhub_quote(symbol: str) -> dict:
    r = requests.get(f"{FINNHUB_BASE}/quote",
                     params={"symbol": symbol, "token": FINNHUB_KEY},
                     timeout=10)
    r.raise_for_status()
    d = r.json()
    if not d:
        log.warning(f"    [Finnhub] {symbol}: Empty response")
        return {}
    if not d.get("c"):
        log.warning(f"    [Finnhub] {symbol}: No current price in response")
        return {}
    if d.get("c") == 0:
        log.warning(f"    [Finnhub] {symbol}: Price is 0 (market closed or no data)")
        return {}
    return {"price": d["c"], "open": d.get("o"), "high": d.get("h"),
            "low": d.get("l"), "volume": d.get("v", 0),
            "prev_close": d.get("pc"), "change_pct": d.get("dp", 0),
            "source": "Finnhub"}

def _fmp_quote(symbol: str) -> dict:
    try:
        r = requests.get(f"{FMP_BASE}/quote/{symbol}",
                         params={"apikey": FMP_KEY}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data or not isinstance(data, list) or len(data) == 0:
            log.warning(f"    [FMP] {symbol}: Empty or invalid response")
            return {}
        q = data[0]
        if not q.get("price"):
            log.warning(f"    [FMP] {symbol}: No price in response")
            return {}
        return {"price": q["price"], "open": q.get("open"),
                "high": q.get("dayHigh"), "low": q.get("dayLow"),
                "volume": q.get("volume", 0),
                "prev_close": q.get("previousClose"),
                "change_pct": q.get("changesPercentage", 0),
                "source": "FMP"}
    except requests.exceptions.HTTPError as e:
        log.warning(f"    [FMP] {symbol}: HTTP error {e.response.status_code if e.response else 'unknown'}")
        return {}
    except Exception as e:
        log.warning(f"    [FMP] {symbol}: Error - {e}")
        return {}

def _yfinance_quote(symbol: str) -> dict:
    if not YFINANCE_AVAILABLE:
        log.warning(f"    [yfinance] {symbol}: yfinance not installed")
        return {}
    try:
        ticker = yf.Ticker(symbol)
        info   = ticker.fast_info
        price  = getattr(info, "last_price", None)
        if not price:
            log.info(f"    [yfinance] {symbol}: No fast_info price, trying history...")
            hist = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                log.info(f"    [yfinance] {symbol}: Got price from 1m history")
            else:
                log.warning(f"    [yfinance] {symbol}: No 1m history available")
        if not price:
            log.warning(f"    [yfinance] {symbol}: Could not get price")
            return {}
        return {"price": price,
                "open":       getattr(info, "open", None),
                "high":       getattr(info, "day_high", None),
                "low":        getattr(info, "day_low", None),
                "volume":     getattr(info, "last_volume", 0),
                "prev_close": getattr(info, "previous_close", None),
                "change_pct": 0.0,
                "source":     "yfinance"}
    except Exception as e:
        log.warning(f"    [yfinance] {symbol}: Error - {e}")
        return {}


def fetch_realtime(symbol: str) -> dict:
    log.info(f"    [{symbol}] Trying Finnhub...")
    result = with_retry(_finnhub_quote, symbol, retries=2, base_delay=3)
    if result:
        log.info(f"    [{symbol}] ✅ Finnhub: ${result['price']}")
        return result
    else:
        log.info(f"    [{symbol}] Finnhub returned no valid data")

    log.info(f"    [{symbol}] Trying FMP...")
    result = with_retry(_fmp_quote, symbol, retries=2, base_delay=3)
    if result:
        log.info(f"    [{symbol}] ✅ FMP: ${result['price']}")
        return result
    else:
        log.info(f"    [{symbol}] FMP returned no valid data")

    log.info(f"    [{symbol}] Trying yfinance...")
    result = _yfinance_quote(symbol)
    if result:
        log.info(f"    [{symbol}] ✅ yfinance: ${result['price']}")
        return result
    else:
        log.info(f"    [{symbol}] yfinance returned no valid data")

    log.error(f"    [{symbol}] ❌ All 3 real-time sources failed")
    return {}

# =========================================================
# 7. HISTORICAL API FETCHERS
# =========================================================

def _yfinance_history(symbol: str,
                       start: str = "2010-01-01") -> list:
    if not YFINANCE_AVAILABLE:
        return []
    try:
        log.info(f"    [yfinance] Fetching history for {symbol}...")
        df = yf.Ticker(symbol).history(start=start, auto_adjust=True)
        if df.empty:
            return []
        records = []
        for idx, row in df.iterrows():
            records.append({
                "symbol": symbol,
                "date":   idx.strftime("%Y-%m-%d"),
                "close":  row.get("Close"),
                "volume": row.get("Volume"),
                "source": "yfinance"
            })
        log.info(f"    [yfinance] {symbol}: {len(records)} rows")
        return records
    except Exception as e:
        log.error(f"    [yfinance] {symbol}: {e}")
        return []


def _av_history(symbol: str) -> list:
    if not av_call_allowed():
        log.warning(f"    [AV] Quota exhausted — skipping {symbol}")
        return []
    try:
        log.info(f"    [AV] {symbol} "
                 f"(calls left: {av_remaining()})...")
        r = requests.get(
            ALPHA_VANTAGE_BASE,
            params={"function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "outputsize": "compact",
                    "apikey": ALPHA_VANTAGE_KEY},
            timeout=20)
        r.raise_for_status()
        av_increment()
        data = r.json()

        if "Note" in data:
            log.warning(f"    [AV] Rate limit hit — waiting 65s")
            time.sleep(65)
            return []
        if "Information" in data:
            log.warning(f"    [AV] API message: "
                        f"{data['Information'][:80]}")
            return []
        if "Error Message" in data:
            log.error(f"    [AV] Error: {data['Error Message'][:80]}")
            return []

        ts = data.get("Time Series (Daily)", {})
        if not ts:
            return []

        records = []
        for date_str, vals in ts.items():
            records.append({
                "symbol": symbol, "date": date_str,
                "close":  vals.get("4. close"),
                "volume": vals.get("5. volume"),
                "source": "Alpha Vantage"
            })
        log.info(f"    [AV] {symbol}: {len(records)} rows")
        return records

    except requests.exceptions.Timeout:
        log.error(f"    [AV] Timeout {symbol}")
        return []
    except Exception as e:
        log.error(f"    [AV] {symbol}: {e}")
        return []


def _fmp_history(symbol: str) -> list:
    try:
        log.info(f"    [FMP] Fetching history for {symbol}...")
        r = requests.get(
            f"{FMP_BASE}/historical-price-full/{symbol}",
            params={"apikey": FMP_KEY, "from": "2010-01-01"},
            timeout=20)
        r.raise_for_status()
        data = r.json()

        if not isinstance(data, dict) or "historical" not in data:
            log.warning(f"    [FMP] No 'historical' key for {symbol}")
            return []

        records = []
        for d in reversed(data["historical"]):
            records.append({
                "symbol": symbol, "date": d.get("date"),
                "close": d.get("close"),
                "volume": d.get("volume"), "source": "FMP"
            })
        log.info(f"    [FMP] {symbol}: {len(records)} rows")
        return records

    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else 0
        if code == 403:
            log.warning(f"    [FMP] 403 — plan may not include {symbol}")
        else:
            log.error(f"    [FMP] HTTP {code} {symbol}: {e}")
        return []
    except Exception as e:
        log.error(f"    [FMP] {symbol}: {e}")
        return []


def fetch_historical(symbol: str) -> list:
    all_records = []

    # Tier 1: yfinance (primary)
    yf_recs = _yfinance_history(symbol)
    if yf_recs:
        all_records.extend(yf_recs)

    # Tier 2: AV (supplement)
    if av_call_allowed():
        av_recs = _av_history(symbol)
        if av_recs:
            all_records.extend(av_recs)
        time.sleep(12)

    # Tier 3: FMP (backup)
    if not all_records:
        fmp_recs = _fmp_history(symbol)
        all_records.extend(fmp_recs)

    if not all_records:
        log.error(f"    {symbol}: ❌ All 3 historical sources failed")
        return []

    # Merge + deduplicate
    merged = {}
    for row in all_records:
        d = str(row.get("date", ""))[:10]
        if not d:
            continue
        if d not in merged:
            merged[d] = row
        else:
            src_new = row.get("source", "")
            src_old = merged[d].get("source", "")
            new_vol = int(float(row.get("volume") or 0))
            old_vol = int(float(merged[d].get("volume") or 0))
            if src_new == "yfinance" and src_old != "yfinance":
                merged[d] = row
            elif src_new == src_old and new_vol > old_vol:
                merged[d] = row

    final = sorted(merged.values(), key=lambda x: x["date"])
    log.info(f"    {symbol}: {len(final)} unique rows "
             f"(from {len(all_records)} total across all sources)")
    return final

# =========================================================
# 8. FRAUD ALERT
# =========================================================

def generate_fraud_alert(symbol, record, price_chg, vol_surge):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=DB_TIMEOUT)
        if record.get("price_anomaly"):
            atype = "PRICE_MANIPULATION"
            sev   = max(10, min(100, int(price_chg * 8)))
            desc  = f"Price moved {price_chg:.2f}% vs recent avg"
        elif record.get("volume_anomaly"):
            atype = "VOLUME_ANOMALY"
            sev   = max(10, min(100, int(vol_surge * 12)))
            desc  = f"Volume {vol_surge:.1f}x average"
        else:
            conn.close()
            return

        conn.execute("""INSERT OR IGNORE INTO fraud_alerts
            (symbol,alert_type,severity,description,
             evidence_data,detected_at)
            VALUES (?,?,?,?,?,?)""",
            (symbol, atype, sev, desc,
             json.dumps({"price": record["price"],
                         "volume": record["volume"],
                         "z": record.get("z_score_price", 0),
                         "ts": record["fetched_at"],
                         "src": record.get("source")}),
             record["fetched_at"]))
        conn.commit()
        conn.close()
        log.warning(f"🚨 {symbol} {atype} sev={sev}")
    except Exception as e:
        log.error(f"Alert error: {e}")

# =========================================================
# 9. SAVE FUNCTIONS
# =========================================================

def save_realtime(record: dict) -> str:
    if not record:
        return "ERROR"
    try:
        conn = sqlite3.connect(DB_NAME, timeout=DB_TIMEOUT)
        last = conn.execute("""SELECT price, volume
            FROM clean_realtime_quotes
            WHERE symbol=? ORDER BY fetched_at DESC LIMIT 1""",
            (record["symbol"],)).fetchone()

        if last and last[0] == record["price"] \
                and last[1] == record["volume"]:
            conn.close()
            return "UNCHANGED"

        conn.execute("""INSERT OR REPLACE INTO clean_realtime_quotes
            (symbol,price,open,high,low,volume,prev_close,change_pct,
             volume_anomaly,price_anomaly,z_score_price,z_score_volume,
             source,fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record["symbol"], record["price"],
             record.get("open"), record.get("high"),
             record.get("low"), record.get("volume", 0),
             record.get("prev_close"),
             record.get("change_pct", 0),
             record.get("volume_anomaly", 0),
             record.get("price_anomaly",  0),
             record.get("z_score_price",  0.0),
             record.get("z_score_volume", 0.0),
             record.get("source", "Unknown"),
             record["fetched_at"]))
        conn.commit()
        conn.close()
        return "SAVED"
    except Exception as e:
        log_error_to_db("save_realtime", record.get("symbol"), str(e))
        return "ERROR"


def save_historical_batch(records: list, symbol: str) -> int:
    if not records:
        return 0

    conn    = sqlite3.connect(DB_NAME, timeout=DB_TIMEOUT)
    saved   = 0
    prices  = []
    volumes = []

    for record in records:
        try:
            close  = record["close"]
            volume = record["volume"]

            daily_return = None
            if prices and prices[-1] and prices[-1] > 0:
                daily_return = ((close - prices[-1]) / prices[-1]) * 100

            volatility_5d = None
            if len(prices) >= 5:
                last5 = prices[-5:]
                rets  = [(last5[j]-last5[j-1])/last5[j-1]*100
                         for j in range(1, len(last5))
                         if last5[j-1] > 0]
                if len(rets) > 1:
                    volatility_5d = statistics.stdev(rets)

            is_susp  = 0
            susp_why = None
            if daily_return and abs(daily_return) > \
                    THRESHOLDS["daily_return_limit"]:
                is_susp  = 1
                susp_why = f"Extreme: {daily_return:.2f}%"

            # SIMPLIFIED INSERT: removed open, high, low, volume_surge
            conn.execute("""INSERT OR REPLACE INTO clean_historical_prices
                (symbol, date, close, volume, daily_return,
                 volatility_5d, is_suspicious, suspicion_reason, source)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (symbol, record["date"],
                 close, volume,
                 round(daily_return,  4) if daily_return  else None,
                 round(volatility_5d, 4) if volatility_5d else None,
                 is_susp, susp_why,
                 record.get("source", "Unknown")))
            saved += 1
            prices.append(close)
            volumes.append(volume)

        except Exception as e:
            log.warning(f"  {symbol} {record.get('date','?')}: {e}")

    if records:
        dates = [r["date"] for r in records if r.get("date")]
        if dates:
            conn.execute("""INSERT OR REPLACE INTO data_sync_status
                (symbol, last_sync_date, total_records,
                 first_record_date, last_record_date)
                VALUES (?,?,?,?,?)""",
                (symbol, datetime.now().strftime("%Y-%m-%d"),
                 len(records), min(dates), max(dates)))

    conn.commit()
    conn.close()
    log.info(f"    💾 {symbol}: {saved} historical rows saved")
    return saved