"""
fetch.py — yfinance ile BIST verisi çekme
Sunucuda çalışır (GitHub Actions), Mac bağlantı sorunu yok.
"""
import math, datetime, time, logging
from pathlib import Path

log = logging.getLogger(__name__)

YF_SUFFIX     = ".IS"
BATCH_SIZE    = 50
RETRY_WAIT    = 5
MAX_RETRIES   = 3
BATCH_DELAY   = 1.0


def fetch_missing_days(tickers: list, last_filled: datetime.date) -> dict:
    """
    Son dolu günden bugüne kadar eksik günlerin verisini çeker.
    Döner: {date: {ticker: pct_change_decimal}}
    """
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance kurulu değil: pip install yfinance")
        return {}

    today = datetime.date.today()
    # Sadece hafta içi
    missing = [
        d for d in _business_days(last_filled + datetime.timedelta(days=1), today)
    ]
    if not missing:
        log.info("Güncel — çekilecek gün yok.")
        return {}

    log.info(f"{len(missing)} gün çekilecek: {missing[0]} → {missing[-1]}")

    fetch_start = (missing[0] - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    fetch_end   = (missing[-1] + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    yf_tickers  = [t + YF_SUFFIX for t in tickers]

    result = {}
    total  = (len(yf_tickers) - 1) // BATCH_SIZE + 1

    for bi, bs in enumerate(range(0, len(yf_tickers), BATCH_SIZE)):
        batch       = yf_tickers[bs : bs + BATCH_SIZE]
        batch_names = tickers[bs    : bs + BATCH_SIZE]
        log.info(f"Batch {bi+1}/{total} ({len(batch)} hisse)...")

        for attempt in range(MAX_RETRIES):
            try:
                raw = yf.download(
                    batch, start=fetch_start, end=fetch_end,
                    progress=False, auto_adjust=True, actions=False,
                )
                if raw is None or raw.empty:
                    break

                if len(batch) == 1:
                    close = raw[["Close"]].copy()
                    close.columns = [batch[0]]
                else:
                    close = raw["Close"].copy() if "Close" in raw.columns.get_level_values(0) else raw.copy()

                pct = close.pct_change()   # ondalık (0.01 = %1)

                for yf_t, orig_t in zip(batch, batch_names):
                    if yf_t not in pct.columns: continue
                    for dt_idx in pct.index:
                        d = dt_idx.date() if hasattr(dt_idx, "date") else dt_idx
                        if d not in missing: continue
                        try:
                            v = float(pct[yf_t].loc[dt_idx])
                            if not (math.isnan(v) or math.isinf(v)):
                                result.setdefault(d, {})[orig_t] = v
                        except: pass
                break
            except Exception as e:
                log.warning(f"  Deneme {attempt+1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_WAIT)

        if bs + BATCH_SIZE < len(yf_tickers):
            time.sleep(BATCH_DELAY)

    log.info(f"Veri gelen gün: {len(result)}")
    return result


def _business_days(start: datetime.date, end: datetime.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += datetime.timedelta(days=1)
