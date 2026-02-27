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
    from fetch import fetch_missing_days
    tickers  = list(raw['daily'].keys())
    fetched  = fetch_missing_days(tickers, last_date)

    # 3. Yeni veriyi Excel'e yaz
    if fetched:
        from update_excel import write_new_data
        write_new_data(excel, fetched)
        log.info("Excel güncellendi — veri yeniden yükleniyor...")
        raw = load_raw_data(excel)   # güncel veriyle yeniden yükle

    # 4. Siteyi derle
    from build_site import build
    stocks, meta = build(excel, Path(OUTPUT_DIR))

    from build_site import build_strategies
    build_strategies(stocks, Path(OUTPUT_DIR))
    log.info("=" * 50)
    log.info(f"  Son veri     : {meta['last_updated']}")
    log.info(f"  Toplam hisse : {meta['total']}")
    log.info(f"  Pozitif mom  : {meta['pos_mom']}")
    log.info(f"  Negatif FIP  : {meta['neg_fip']} (kaliteli)")
    log.info("=" * 50)


if __name__ == '__main__':
    main()
