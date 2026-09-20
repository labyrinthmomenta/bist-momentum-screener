"""
fetch.py — yfinance ile BIST verisi çekme
Sunucuda çalışır (GitHub Actions), Mac bağlantı sorunu yok.
"""
import math, datetime, time, logging
from pathlib import Path

log = logging.getLogger(__name__)

YF_SUFFIX     = ".IS"
BATCH_SIZE    = 50       # yfinance rate limit için sabit tutuldu
RETRY_WAIT    = 10       # 5→10 sn: rate limit sonrası bekleme
MAX_RETRIES   = 5        # 3→5: daha fazla deneme
BATCH_DELAY   = 3.0      # 1.0→3.0 sn: batch arası bekleme (rate limit koruması)
RETRY_BACKOFF = 2.0      # Her denemede bekleme katsayısı (exponential backoff)


def fetch_missing_days(tickers: list, last_filled: datetime.date,
                       per_ticker_last: dict = None) -> dict:
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

    # Per-ticker eksik gün hesabı
    if per_ticker_last:
        ticker_missing = {}
        all_missing    = set()
        for t in tickers:
            t_last   = per_ticker_last.get(t, last_filled)
            t_miss   = list(_business_days(t_last + datetime.timedelta(days=1), today))
            if t_miss:
                ticker_missing[t] = set(t_miss)
                all_missing.update(t_miss)
        missing = sorted(all_missing)
    else:
        ticker_missing = None
        missing = list(_business_days(last_filled + datetime.timedelta(days=1), today))

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
                    # Per-ticker eksik gün seti — yoksa tüm missing günleri kullan
                    t_missing = ticker_missing.get(orig_t, set(missing)) if ticker_missing else set(missing)
                    for dt_idx in pct.index:
                        d = dt_idx.date() if hasattr(dt_idx, "date") else dt_idx
                        if d not in t_missing: continue
                        try:
                            v = float(pct[yf_t].loc[dt_idx])
                            if not (math.isnan(v) or math.isinf(v)):
                                result.setdefault(d, {})[orig_t] = v
                        except: pass
                break
            except Exception as e:
                wait = RETRY_WAIT * (RETRY_BACKOFF ** attempt)  # exponential backoff
                log.warning(f"  Deneme {attempt+1}/{MAX_RETRIES}: {e} — {wait:.0f}sn bekleniyor")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait)

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


# ── Sanity Check ─────────────────────────────────────────────────────────────

SANITY_THRESHOLD = 0.20   # |günlük getiri| > %20 → kontrol et
HARD_CAP         = 0.50   # |günlük getiri| > %50 → her zaman quarantine

def sanity_check(result: dict) -> dict:
    """
    Ekstrem günlük getiri değerlerini tespit eder.

    Kural:
    - |ret| > %50  → kesinlikle quarantine (veri hatası / bölünme gecikmesi)
    - %20 < |ret| ≤ %50 → şüpheli, quarantine olarak işaretle ama kaydet
      (sermaye artırımı, rüçhan gibi meşru durumlar olabilir)

    Döner: Temizlenmiş result dict + quarantine raporu
    """
    quarantine = []   # [(date, ticker, ret, reason)]
    cleaned    = {}

    for date, day_data in result.items():
        cleaned[date] = {}
        for ticker, ret in day_data.items():
            abs_ret = abs(ret)
            if abs_ret > HARD_CAP:
                quarantine.append((date, ticker, ret, 'HARD_CAP >%50'))
                log.warning(f"  🚫 Quarantine: {ticker} {date} ret={ret*100:.1f}% — HARD_CAP")
                # Hard cap: bu günü kaydetme
            elif abs_ret > SANITY_THRESHOLD:
                quarantine.append((date, ticker, ret, 'SOFT_CHECK >%20'))
                log.warning(f"  ⚠️  Şüpheli:    {ticker} {date} ret={ret*100:.1f}% — corporate action olabilir")
                cleaned[date][ticker] = ret   # şüpheli ama kaydet
            else:
                cleaned[date][ticker] = ret

        if not cleaned[date]:
            del cleaned[date]

    if quarantine:
        log.warning(f"Sanity check: {len(quarantine)} şüpheli kayıt "
                    f"({sum(1 for _,_,_,r in quarantine if r=='HARD_CAP >%50')} quarantine)")
    else:
        log.info("Sanity check: Tüm değerler normal aralıkta ✅")

    return cleaned, quarantine
