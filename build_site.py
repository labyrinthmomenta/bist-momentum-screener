"""
build_site.py — Site derleyici v2
stocks.json   → özet (hızlı yükleme)
detail/        → her hisse için ayrı JSON (detay modal)
"""
import json, datetime, logging, csv
from pathlib import Path
from engine import load_raw_data, compute_all

log = logging.getLogger(__name__)


def build(excel_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir   = output_dir / 'data'
    detail_dir = output_dir / 'data' / 'detail'
    data_dir.mkdir(exist_ok=True)
    detail_dir.mkdir(exist_ok=True)

    log.info("Excel okunuyor...")
    raw    = load_raw_data(excel_path)
    stocks = compute_all(raw)
    log.info(f"{len(stocks)} hisse hesaplandı.")

    last_date = raw['last_date']

    # ── stocks.json: özet (günlük detay hariç) ──────────────────────────────
    summary = []
    for s in stocks:
        monthly_summary = []
        for m in s['monthly']:
            monthly_summary.append({
                'month':      m['month'],
                'momentum':   m['momentum'],
                'fip':        m['fip'],
                'neg_count':  m['neg_count'],
                'pos_count':  m['pos_count'],
                'flat_count': m['flat_count'],
                'total_days': m['total_days'],
            })
        summary.append({
            'ticker':  s['ticker'],
            'name':    s['name'],
            'type':    s['type'],
            'industry':s['industry'],
            'mom':     s['mom'],
            'fip':     s['fip'],
            'monthly': monthly_summary,
        })

    with open(data_dir / 'stocks.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, separators=(',', ':'))

    # ── detail/{TICKER}.json: günlük kapanışlar dahil ───────────────────────
    for s in stocks:
        with open(detail_dir / f"{s['ticker']}.json", 'w', encoding='utf-8') as f:
            json.dump(s, f, ensure_ascii=False, separators=(',', ':'))

    # ── İstatistikler ────────────────────────────────────────────────────────
    pos_mom = sum(1 for s in summary if s['mom'] is not None and s['mom'] > 0)
    neg_mom = sum(1 for s in summary if s['mom'] is not None and s['mom'] <= 0)
    neg_fip = sum(1 for s in summary if s['fip'] is not None and s['fip'] < 0)
    pos_fip = sum(1 for s in summary if s['fip'] is not None and s['fip'] >= 0)
    viop_n  = sum(1 for s in summary if s['type'] == 'VIOP')

    meta = {
        'last_updated':  last_date.isoformat(),
        'total':         len(summary),
        'viop':          viop_n,
        'pos_mom':       pos_mom,
        'neg_mom':       neg_mom,
        'neg_fip':       neg_fip,
        'pos_fip':       pos_fip,
        'generated_at':  datetime.datetime.utcnow().isoformat() + 'Z',
    }
    with open(data_dir / 'meta.json', 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # ── CSV: manuel kontrol ──────────────────────────────────────────────────
    with open(data_dir / 'momentum_today.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['Ticker','Name','Type','Industry',
                    '12-1M_Mom_%','FIP_Annual',
                    'LastMonth','LastMonth_Mom_%','LastMonth_FIP',
                    'LastMonth_Neg','LastMonth_Pos','LastMonth_Flat','LastMonth_Total'])
        for s in summary:
            lm = s['monthly'][-1] if s['monthly'] else {}
            w.writerow([
                s['ticker'], s['name'], s['type'], s['industry'],
                f"{s['mom']*100:.4f}" if s['mom'] is not None else '',
                f"{s['fip']:.6f}"     if s['fip'] is not None else '',
                lm.get('month',''),
                f"{lm['momentum']*100:.4f}" if lm.get('momentum') is not None else '',
                f"{lm['fip']:.6f}"          if lm.get('fip')      is not None else '',
                lm.get('neg_count',''),
                lm.get('pos_count',''),
                lm.get('flat_count',''),
                lm.get('total_days',''),
            ])

    # ── HTML ─────────────────────────────────────────────────────────────────
    stocks_json = json.dumps(summary, ensure_ascii=False, separators=(',', ':'))
    meta_json   = json.dumps(meta,    ensure_ascii=False, separators=(',', ':'))
    template    = Path(__file__).parent / 'template.html'
    html        = template.read_text(encoding='utf-8')
    html        = html.replace('__STOCKS_JSON__', stocks_json)
    html        = html.replace('__META_JSON__',   meta_json)
    (output_dir / 'index.html').write_text(html, encoding='utf-8')

    log.info(f"stocks.json: {(data_dir/'stocks.json').stat().st_size//1024} KB")
    log.info(f"detail/ klasörü: {len(list(detail_dir.iterdir()))} dosya")
    log.info(f"Site → {output_dir}/index.html")
    return summary, meta


if __name__ == '__main__':
    import sys, logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    excel = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('Claude_Momentum_Screener_BIST_Labyrinth.xlsx')
    out   = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('docs')
    build(excel, out)
