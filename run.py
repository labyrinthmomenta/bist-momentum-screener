"""
run.py — Tek komutla her şeyi çalıştırır.
GitHub Actions her gün bunu çağırır.

Circuit breaker: Veri kalitesi yetersizse strateji güncellenmez.
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

# Circuit breaker eşiği — veri coverage bu oranın altındaysa strateji güncellenmez
MIN_COVERAGE = 0.95   # %95


def check_data_quality(raw: dict, expected_date: datetime.date) -> dict:
    """
    Son işlem gününde kaç hissede veri var?
    Döner: {'coverage': float, 'filled': int, 'total': int, 'ok': bool}
    """
    total  = len(raw['daily'])
    filled = sum(1 for daily in raw['daily'].values() if expected_date in daily)
    coverage = filled / total if total > 0 else 0.0
    ok = coverage >= MIN_COVERAGE
    return {
        'coverage':      round(coverage, 4),
        'filled':        filled,
        'total':         total,
        'expected_date': expected_date,
        'ok':            ok,
    }


def main():
    excel = Path(EXCEL_FILE)
    if not excel.exists():
        log.error(f"Excel bulunamadı: {excel}")
        sys.exit(1)

    # 1. Excel'in son dolu gününü bul
    from engine import load_raw_data
    raw       = load_raw_data(excel)
    last_date = raw['last_date']
    log.info(f"Excel son veri: {last_date}")

    # 2. Per-ticker last_date hesapla — eksik veri olan hisseler için doğru başlangıç
    tickers = list(raw['daily'].keys())
    per_ticker_last = {
        t: max(raw['daily'][t].keys())
        for t in tickers if raw['daily'].get(t)
    }

    # 3. Yeni günler var mı?
    from fetch import fetch_missing_days
    fetched = fetch_missing_days(tickers, last_date, per_ticker_last=per_ticker_last)

    # 4. Sanity check — ekstrem getiri değerlerini filtrele
    if fetched:
        from fetch import sanity_check
        fetched, quarantine = sanity_check(fetched)
        if quarantine:
            log.warning(f"Sanity check: {len(quarantine)} şüpheli kayıt tespit edildi.")

    # 5. Yeni veriyi Excel'e yaz
    if fetched:
        from update_excel import write_new_data
        write_new_data(excel, fetched)
        log.info("Excel güncellendi — veri yeniden yükleniyor...")
        raw = load_raw_data(excel)

    # 6. Veri kalitesi kontrolü (circuit breaker)
    _today    = datetime.date.today()
    _is_friday = _today.weekday() == 4
    _strategy_file = Path(OUTPUT_DIR) / 'data' / 'strategies.json'

    last_date_updated = raw['last_date']
    dq = check_data_quality(raw, last_date_updated)

    log.info("─" * 50)
    log.info(f"  Beklenen son işlem günü : {last_date_updated}")
    log.info(f"  Veri coverage           : {dq['filled']}/{dq['total']} = %{dq['coverage']*100:.1f}")
    log.info(f"  Circuit breaker eşiği   : %{MIN_COVERAGE*100:.0f}")
    log.info(f"  Durum                   : {'✅ OK' if dq['ok'] else '❌ VERİ EKSİK — strateji GÜNCELLENMEYECEK'}")
    log.info("─" * 50)

    # 7. Siteyi derle
    from build_site import build
    stocks, meta = build(excel, Path(OUTPUT_DIR))

    # 8. Strateji güncelleme — circuit breaker kontrolü
    if _is_friday or not _strategy_file.exists():
        if dq['ok']:
            from build_site import build_strategies
            build_strategies(stocks, Path(OUTPUT_DIR))
            log.info(f"✅ Strateji listesi güncellendi ({_today})")
        else:
            log.warning(
                f"⚠️  Strateji güncelleme ATILDI — "
                f"Coverage %{dq['coverage']*100:.1f} < eşik %{MIN_COVERAGE*100:.0f} "
                f"({dq['filled']}/{dq['total']} hisse)"
            )
            # meta.json'a circuit breaker durumunu yaz
            import json
            meta_path = Path(OUTPUT_DIR) / 'data' / 'meta.json'
            if meta_path.exists():
                m = json.loads(meta_path.read_text())
                m['circuit_breaker'] = {
                    'triggered': True,
                    'coverage':  dq['coverage'],
                    'filled':    dq['filled'],
                    'total':     dq['total'],
                    'date':      str(_today),
                }
                meta_path.write_text(json.dumps(m, ensure_ascii=False))
    else:
        log.info(f"Strateji korundu — Cuma değil (bugün: {_today.strftime('%A')})")

    log.info("=" * 50)
    log.info(f"  Son veri     : {meta['last_updated']}")
    log.info(f"  Toplam hisse : {meta['total']}")
    log.info(f"  Pozitif mom  : {meta['pos_mom']}")
    log.info(f"  Negatif FIP  : {meta['neg_fip']} (kaliteli)")
    log.info("=" * 50)


if __name__ == '__main__':
    main()
