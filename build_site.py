"""
build_site.py — Hesaplamaları yapar, JSON üretir, index.html'i derler.
"""
import json, datetime, logging
from pathlib import Path
from engine import load_raw_data, compute_all

log = logging.getLogger(__name__)


def build(excel_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("Excel okunuyor...")
    raw    = load_raw_data(excel_path)
    stocks = compute_all(raw)
    log.info(f"{len(stocks)} hisse hesaplandı.")

    # İstatistikler
    last_date  = raw['last_date']
    pos_mom    = sum(1 for s in stocks if s['mom'] is not None and s['mom'] > 0)
    neg_mom    = sum(1 for s in stocks if s['mom'] is not None and s['mom'] <= 0)
    neg_fip    = sum(1 for s in stocks if s['fip'] is not None and s['fip'] < 0)
    pos_fip    = sum(1 for s in stocks if s['fip'] is not None and s['fip'] >= 0)
    viop_count = sum(1 for s in stocks if s['type'] == 'VIOP')

    meta = {
        'last_updated': last_date.isoformat(),
        'total':        len(stocks),
        'viop':         viop_count,
        'pos_mom':      pos_mom,
        'neg_mom':      neg_mom,
        'neg_fip':      neg_fip,
        'pos_fip':      pos_fip,
        'generated_at': datetime.datetime.utcnow().isoformat() + 'Z',
    }

    # JSON dosyaları (kullanıcı indirme için de kullanılır)
    data_path = output_dir / 'data'
    data_path.mkdir(exist_ok=True)

    with open(data_path / 'stocks.json', 'w', encoding='utf-8') as f:
        json.dump(stocks, f, ensure_ascii=False, separators=(',', ':'))

    with open(data_path / 'meta.json', 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # CSV (manuel kontrol için)
    _write_csv(stocks, data_path / 'momentum_today.csv', last_date)

    # HTML
    _build_html(stocks, meta, output_dir / 'index.html')

    log.info(f"Site hazır → {output_dir}/index.html")
    return stocks, meta


def _write_csv(stocks, path, last_date):
    import csv
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['Ticker','Name','Type','Industry',
                    '12-1M_Mom','12-1M_FIP',
                    'LastMonth_Mom','LastMonth_FIP'])
        for s in stocks:
            lm  = s['monthly'][-1] if s['monthly'] else {}
            w.writerow([
                s['ticker'], s['name'], s['type'], s['industry'],
                s['mom'], s['fip'],
                lm.get('momentum'), lm.get('fip'),
            ])


def _build_html(stocks, meta, out_path):
    stocks_json = json.dumps(stocks,  ensure_ascii=False, separators=(',',':'))
    meta_json   = json.dumps(meta,    ensure_ascii=False, separators=(',',':'))
    template    = Path(__file__).parent / 'template.html'
    html        = template.read_text(encoding='utf-8')
    html        = html.replace('__STOCKS_JSON__', stocks_json)
    html        = html.replace('__META_JSON__',   meta_json)
    out_path.write_text(html, encoding='utf-8')


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    excel = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('Claude_Momentum_Screener_BIST_Labyrinth.xlsx')
    out   = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('docs')
    build(excel, out)
