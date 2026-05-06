"""
run.py — Tek komutla her şeyi çalıştırır.
GitHub Actions her gün bunu çağırır.
"""
import logging, sys, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('run.log', encoding='utf-8'),
    ]
)
log = logging.getLogger(__name__)

EXCEL_FILE = 'Claude_Momentum_Screener_BIST_Labyrinth.xlsx'
OUTPUT_DIR = 'docs'


def main():
    from pathlib import Path
    excel = Path(EXCEL_FILE)
    if not excel.exists():
        log.error(f"Excel bulunamadı: {excel}")
        sys.exit(1)

    # 1. Excel'in son dolu gününü bul
    from engine import load_raw_data
    raw       = load_raw_data(excel)
    last_date = raw['last_date']
    log.info(f"Excel son veri: {last_date}")

    # 2. Yeni günler var mı?
    # Her hissenin kendi son tarihini hesapla — genel last_date değil
    from fetch import fetch_missing_days
    tickers = list(raw['daily'].keys())
    per_ticker_last = {}
    for t in tickers:
        days = raw['daily'].get(t, {})
        if days:
            per_ticker_last[t] = max(days.keys())
        else:
            per_ticker_last[t] = last_date
    log.info(f"Per-ticker last_date hesaplandı — {len(per_ticker_last)} hisse")
    fetched = fetch_missing_days(tickers, last_date, per_ticker_last=per_ticker_last)

    # 3. Yeni veriyi Excel'e yaz
    if fetched:
        from update_excel import write_new_data
        write_new_data(excel, fetched)
        log.info("Excel güncellendi — veri yeniden yükleniyor...")
        raw = load_raw_data(excel)   # güncel veriyle yeniden yükle

    # 4. Siteyi derle
    from build_site import build
    stocks, meta = build(excel, Path(OUTPUT_DIR))

    # Strateji listesi yalnızca Cuma kapanış sonrası güncellenir
    import datetime as _dt
    _today = _dt.date.today()
    _is_friday = _today.weekday() == 4   # 0=Pazartesi, 4=Cuma
    _strategy_file = Path(OUTPUT_DIR) / 'data' / 'strategies.json'
    if _is_friday or not _strategy_file.exists():
        from build_site import build_strategies
        build_strategies(stocks, Path(OUTPUT_DIR))
        log.info(f"Strateji listesi güncellendi ({_today})")
    else:
        log.info(f"Strateji listesi korundu — güncelleme günü değil (bugün: {_today.strftime('%A')})")
    log.info("=" * 50)
    log.info(f"  Son veri     : {meta['last_updated']}")
    log.info(f"  Toplam hisse : {meta['total']}")
    log.info(f"  Pozitif mom  : {meta['pos_mom']}")
    log.info(f"  Negatif FIP  : {meta['neg_fip']} (kaliteli)")
    log.info("=" * 50)


if __name__ == '__main__':
    main()
