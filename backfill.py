"""
backfill.py — BIST takvimi ile JSON verilerini karşılaştırır,
eksik günleri tespit eder ve yfinance'ten çekerek Excel'e yazar.

Kullanım:
    python backfill.py              # Sadece rapor — eksik günleri göster
    python backfill.py --fix        # Eksik günleri çek ve Excel'e yaz
    python backfill.py --fix --verbose  # Detaylı log
"""

import argparse
import datetime
import logging
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

EXCEL_FILE = 'Claude_Momentum_Screener_BIST_Labyrinth.xlsx'
YF_SUFFIX  = '.IS'

# ── BIST Tatil Günleri ──────────────────────────────────────────────────────
# Yarım gün tatiller (piyasa saat 13:00'e kadar açık) tam tatil sayılmaz —
# o günler için kapanış verisi gelir, listeye eklenmedi.
BIST_HOLIDAYS = {
    # 2025
    datetime.date(2025,  1,  1),   # Yeni Yıl
    datetime.date(2025,  3, 31),   # Ramazan Bayramı
    datetime.date(2025,  4,  1),   # Ramazan Bayramı
    datetime.date(2025,  4,  2),   # Ramazan Bayramı (Salı — 1 Nisan Salı)
    datetime.date(2025,  4, 23),   # Ulusal Egemenlik
    datetime.date(2025,  5,  1),   # Emek Günü
    datetime.date(2025,  5, 19),   # Gençlik ve Spor
    datetime.date(2025,  6,  6),   # Kurban Bayramı
    datetime.date(2025,  6,  9),   # Kurban Bayramı (Pazartesi)
    datetime.date(2025,  7, 15),   # Demokrasi Günü
    datetime.date(2025, 10, 29),   # Cumhuriyet Bayramı
    # 2026
    datetime.date(2026,  1,  1),   # Yeni Yıl
    datetime.date(2026,  3, 20),   # Ramazan Bayramı
    datetime.date(2026,  3, 21),   # Ramazan Bayramı
    datetime.date(2026,  3, 22),   # Ramazan Bayramı
    datetime.date(2026,  4, 23),   # Ulusal Egemenlik
    datetime.date(2026,  5,  1),   # Emek Günü
    datetime.date(2026,  5, 19),   # Gençlik ve Spor
    datetime.date(2026,  5, 27),   # Kurban Bayramı
    datetime.date(2026,  5, 28),   # Kurban Bayramı
    datetime.date(2026,  5, 29),   # Kurban Bayramı
    datetime.date(2026,  7, 15),   # Demokrasi Günü
    datetime.date(2026, 10, 29),   # Cumhuriyet Bayramı
}


def bist_trading_days(start: datetime.date, end: datetime.date):
    """start-end aralığındaki BIST iş günlerini üretir (hafta sonu + tatil hariç)."""
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in BIST_HOLIDAYS:
            yield d
        d += datetime.timedelta(days=1)


def find_gaps(raw: dict) -> dict:
    """
    Her hisse için kayıtta olması gereken ama olmayan günleri bulur.
    Döner: {ticker: [missing_date, ...]}
    """
    today     = datetime.date.today()
    gaps      = {}

    for ticker, daily in raw['daily'].items():
        if not daily:
            continue
        first_date = min(daily.keys())
        last_date  = max(daily.keys())

        # Son tarihten bugüne kadar olan gelecek eksikler
        check_end = min(today - datetime.timedelta(days=1), last_date)
        # Tüm aralık: ilk kayıttan son kayda kadar + son kayıttan dünkü güne kadar
        check_end = today - datetime.timedelta(days=1)

        expected = list(bist_trading_days(first_date, check_end))
        missing  = [d for d in expected if d not in daily]

        if missing:
            gaps[ticker] = missing

    return gaps


def print_gap_report(gaps: dict):
    """Eksik günleri aylara göre özetler."""
    if not gaps:
        log.info("✅ Hiç eksik gün bulunamadı.")
        return

    # Ay bazında kaç hissede eksik var
    month_summary = defaultdict(set)
    for ticker, dates in gaps.items():
        for d in dates:
            month_summary[d.strftime('%Y-%m')].add(ticker)

    total_gaps = sum(len(v) for v in gaps.values())
    log.info(f"\n{'='*60}")
    log.info(f"  EKSIK GÜN RAPORU — Toplam {len(gaps)} hisse, {total_gaps} eksik kayıt")
    log.info(f"{'='*60}")

    for month in sorted(month_summary.keys()):
        tickers_with_gap = sorted(month_summary[month])
        log.info(f"\n  📅 {month} — {len(tickers_with_gap)} hissede eksik:")
        # Her ay için hangi günler eksik
        month_dates = set()
        for t in tickers_with_gap:
            for d in gaps[t]:
                if d.strftime('%Y-%m') == month:
                    month_dates.add(d)
        for d in sorted(month_dates):
            affected = [t for t in tickers_with_gap if d in gaps[t]]
            log.info(f"    {d} ({d.strftime('%A')[:3]}) — {len(affected)} hisse: {', '.join(affected[:8])}{'...' if len(affected)>8 else ''}")

    log.info(f"\n{'='*60}\n")


def fetch_and_fill(gaps: dict, excel: Path):
    """Eksik günleri yfinance'ten çeker ve Excel'e yazar."""
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance kurulu değil: pip install yfinance")
        return

    # Tüm eksik günleri ve hangi hisseler için gerektiğini topla
    date_to_tickers = defaultdict(list)
    for ticker, dates in gaps.items():
        for d in dates:
            date_to_tickers[d].append(ticker)

    all_dates = sorted(date_to_tickers.keys())
    if not all_dates:
        return

    fetch_start = (all_dates[0]  - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
    fetch_end   = (all_dates[-1] + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    all_tickers = sorted(set(t for tl in date_to_tickers.values() for t in tl))
    yf_tickers  = [t + YF_SUFFIX for t in all_tickers]
    ticker_map  = {t + YF_SUFFIX: t for t in all_tickers}

    log.info(f"yfinance'ten çekiliyor: {fetch_start} → {fetch_end}, {len(all_tickers)} hisse")

    BATCH = 50
    result = {}   # {date: {ticker: ret}}

    for bi in range(0, len(yf_tickers), BATCH):
        batch_yf   = yf_tickers[bi:bi+BATCH]
        batch_orig = all_tickers[bi:bi+BATCH]
        log.info(f"  Batch {bi//BATCH+1}/{(len(yf_tickers)-1)//BATCH+1} ({len(batch_yf)} hisse)...")

        for attempt in range(3):
            try:
                raw_df = yf.download(
                    batch_yf, start=fetch_start, end=fetch_end,
                    progress=False, auto_adjust=True, actions=False,
                )
                if raw_df is None or raw_df.empty:
                    break

                if len(batch_yf) == 1:
                    close = raw_df[['Close']].copy()
                    close.columns = [batch_yf[0]]
                else:
                    close = raw_df['Close'].copy()

                pct = close.pct_change()

                for yf_t, orig_t in zip(batch_yf, batch_orig):
                    if yf_t not in pct.columns:
                        continue
                    for dt_idx in pct.index:
                        d = dt_idx.date() if hasattr(dt_idx, 'date') else dt_idx
                        # Sadece bu hisse için eksik olan günleri al
                        if d not in gaps.get(orig_t, []):
                            continue
                        try:
                            v = float(pct[yf_t].loc[dt_idx])
                            if not (math.isnan(v) or math.isinf(v)):
                                result.setdefault(d, {})[orig_t] = v
                        except:
                            pass
                break
            except Exception as e:
                log.warning(f"    Deneme {attempt+1}: {e}")
                if attempt < 2:
                    time.sleep(5)

        if bi + BATCH < len(yf_tickers):
            time.sleep(1.0)

    filled = sum(len(v) for v in result.values())
    log.info(f"Çekilen veri: {len(result)} gün, {filled} hisse-gün kaydı")

    if result:
        from update_excel import write_new_data
        write_new_data(excel, result)
        log.info(f"✅ Excel güncellendi: {excel}")
    else:
        log.warning("⚠️  Hiç veri çekilemedi — Excel değiştirilmedi.")


def main():
    parser = argparse.ArgumentParser(description='BIST veri bütünlüğü kontrolü ve backfill')
    parser.add_argument('--fix',     action='store_true', help='Eksik günleri yfinance\'ten çek ve yaz')
    parser.add_argument('--verbose', action='store_true', help='Detaylı log')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    excel = Path(EXCEL_FILE)
    if not excel.exists():
        log.error(f"Excel bulunamadı: {excel}")
        sys.exit(1)

    log.info(f"Excel yükleniyor: {excel}")
    from engine import load_raw_data
    raw = load_raw_data(excel)
    log.info(f"Yüklendi — {len(raw['daily'])} hisse, son tarih: {raw['last_date']}")

    log.info("Eksik günler taranıyor...")
    gaps = find_gaps(raw)

    print_gap_report(gaps)

    if not gaps:
        return

    if args.fix:
        log.info("--fix modu: Eksik günler çekiliyor...")
        fetch_and_fill(gaps, excel)
        log.info("Tamamlandı. Siteyi yeniden derlemek için: python run.py")
    else:
        log.info("Rapor modu — eksikleri doldurmak için: python backfill.py --fix")


if __name__ == '__main__':
    main()
