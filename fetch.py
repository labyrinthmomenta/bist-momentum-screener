"""
fetch.py — yfinance ile BIST verisi çekme
Sunucuda çalışır (GitHub Actions), Mac bağlantı sorunu yok.

v2: Her hisse kendi son tarihine göre eksik günlerini doldurur.
    Tek bir global last_date yerine per-ticker last_date kullanılır.
"""
import math, datetime, time, logging
from pathlib import Path

log = logging.getLogger(__name__)

YF_SUFFIX     = ".IS"
BATCH_SIZE    = 50
RETRY_WAIT    = 5
MAX_RETRIES   = 3
BATCH_DELAY   = 1.0


def fetch_missing_days(tickers: list, last_filled: datetime.date,
                       per_ticker_last: dict = None) -> dict:
    """
    Her hissenin kendi son tarihinden bugüne kadar eksik günlerin verisini çeker.

    Args:
        tickers:          Hisse listesi
        last_filled:      Global son tarih (fallback — per_ticker_last yoksa kullanılır)
        per_ticker_last:  {ticker: last_date} — her hissenin kendi son tarihi

    Döner: {date: {ticker: pct_change_decimal}}
    """
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance kurulu değil: pip install yfinance")
        return {}

    today = datetime.date.today()

    # Her hisse için eksik olan günleri hesapla
    ticker_missing = {}   # {ticker: [date, ...]}
    all_missing    = set()

    for t in tickers:
        if per_ticker_last and t in per_ticker_last:
            t_last = per_ticker_last[t]
        else:
            t_last = last_filled

        missing_for_t = list(_business_days(
            t_last + datetime.timedelta(days=1), today
        ))
        if missing_for_t:
            ticker_missing[t] = missing_for_t
            all_missing.update(missing_for_t)

    if not all_missing:
        log.info("Güncel — çekilecek gün yok.")
        return {}

    all_missing_sorted = sorted(all_missing)
    log.info(f"Toplam eksik gün aralığı: {all_missing_sorted[0]} → {all_missing_sorted[-1]}")
    log.info(f"Eksik verisi olan hisse sayısı: {len(ticker_missing)}")

    fetch_start = (all_missing_sorted[0]  - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    fetch_end   = (all_missing_sorted[-1] + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
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
                    if yf_t not in pct.columns:
                        continue
                    # Bu hissenin eksik günleri — global all_missing değil, kendi listesi
                    t_missing_set = set(ticker_missing.get(orig_t, []))
                    for dt_idx in pct.index:
                        d = dt_idx.date() if hasattr(dt_idx, "date") else dt_idx
                        if d not in t_missing_set:
                            continue
                        try:
                            v = float(pct[yf_t].loc[dt_idx])
                            if not (math.isnan(v) or math.isinf(v)):
                                result.setdefault(d, {})[orig_t] = v
                        except:
                            pass
                break
            except Exception as e:
                log.warning(f"  Deneme {attempt+1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_WAIT)

        if bs + BATCH_SIZE < len(yf_tickers):
            time.sleep(BATCH_DELAY)

    log.info(f"Veri gelen gün sayısı: {len(result)}")
    return result


def _business_days(start: datetime.date, end: datetime.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += datetime.timedelta(days=1)
