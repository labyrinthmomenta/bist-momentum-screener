"""
engine.py — Momentum & FIP hesaplama motoru v2
Wesley R. Gray — Quantitative Momentum
"""
import math, datetime, openpyxl
from pathlib import Path


def _sf(v):
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except: return None


def _month_window(year, month):
    first = datetime.date(year, month, 1)
    last  = datetime.date(year, month+1, 1) - datetime.timedelta(days=1) if month < 12 \
            else datetime.date(year, 12, 31)
    return first, last


def _prev_month(y, m):
    return (y-1, 12) if m == 1 else (y, m-1)


def load_raw_data(excel_path: Path) -> dict:
    wb  = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws  = wb['BIST D Return Data']

    date_row    = list(ws.iter_rows(min_row=3, max_row=3, values_only=True))[0]
    idx_to_date = {i: v.date() for i, v in enumerate(date_row) if isinstance(v, datetime.datetime)}

    # Meta: trade type, industry, name
    meta = {}
    ws_ms = wb['MOMENTUM SCREENER']
    for row in ws_ms.iter_rows(min_row=5, max_row=650, values_only=True):
        if not row[4]: continue
        t = str(row[4]).strip()
        meta[t] = {
            'type':     str(row[1]).strip() if row[1] else 'Stock',
            'industry': str(row[2]).strip() if row[2] else '',
            'name':     str(row[5]).strip() if row[5] else t,
        }

    # Günlük getiri: {ticker: {date: decimal}}
    daily = {}
    for row in ws.iter_rows(min_row=6, max_row=650, values_only=True):
        t = row[3]
        if not t: continue
        t = str(t).strip()
        d = {}
        for idx, date in idx_to_date.items():
            v = _sf(row[idx]) if idx < len(row) else None
            if v is not None:
                d[date] = v / 100.0
        daily[t] = d

    wb.close()

    filled = [dt for dt in idx_to_date.values()
              if any(dt in daily[t] for t in daily)]
    last_date = max(filled) if filled else None

    return {'tickers': meta, 'daily': daily,
            'dates_sorted': sorted(idx_to_date.values()), 'last_date': last_date}


# ── Momentum ──────────────────────────────────────────────────────────────────

def calc_momentum_12_1(daily, as_of_date):
    y, m    = as_of_date.year, as_of_date.month
    py, pm  = _prev_month(y, m)
    _, wend = _month_window(py, pm)
    sm = pm - 11; sy = py
    while sm <= 0: sm += 12; sy -= 1
    wstart, _ = _month_window(sy, sm)
    prod = 1.0; n = 0
    for dt, r in daily.items():
        if wstart <= dt <= wend:
            prod *= (1.0 + r); n += 1
    return (prod - 1.0) if n >= 10 else None


def calc_monthly_momentum(daily, year, month):
    first, last = _month_window(year, month)
    prod = 1.0; n = 0
    for dt, r in daily.items():
        if first <= dt <= last:
            prod *= (1.0 + r); n += 1
    return (prod - 1.0) if n >= 1 else None


# ── FIP ───────────────────────────────────────────────────────────────────────

def calc_fip_annual(daily, as_of_date):
    y, m    = as_of_date.year, as_of_date.month
    py, pm  = _prev_month(y, m)
    _, wend = _month_window(py, pm)
    sm = pm - 11; sy = py
    while sm <= 0: sm += 12; sy -= 1
    wstart, _ = _month_window(sy, sm)
    rets = [r for dt, r in daily.items() if wstart <= dt <= wend]
    if len(rets) < 10: return None
    mom = calc_momentum_12_1(daily, as_of_date)
    if mom is None: return None
    n   = len(rets)
    neg = sum(1 for r in rets if r < 0) / n
    pos = sum(1 for r in rets if r > 0) / n
    return round((1 if mom >= 0 else -1) * (neg - pos), 6)


def calc_fip_monthly(daily, year, month):
    first, last = _month_window(year, month)
    rets = [r for dt, r in daily.items() if first <= dt <= last]
    if not rets: return None
    mom = calc_monthly_momentum(daily, year, month)
    if mom is None: return None
    n   = len(rets)
    neg = sum(1 for r in rets if r < 0) / n
    pos = sum(1 for r in rets if r > 0) / n
    return round((1 if mom >= 0 else -1) * (neg - pos), 6)


# ── Aylık detay (neg/pos/flat sayıları + günlük kapanışlar) ──────────────────

def monthly_detail(daily, year, month):
    """Bir ayın günlük getiri listesi + istatistik."""
    first, last = _month_window(year, month)
    days = sorted([(dt, r) for dt, r in daily.items() if first <= dt <= last])
    neg  = sum(1 for _, r in days if r < 0)
    pos  = sum(1 for _, r in days if r > 0)
    flat = sum(1 for _, r in days if r == 0)
    return {
        'neg_count':  neg,
        'pos_count':  pos,
        'flat_count': flat,
        'total_days': len(days),
        'days': [{'date': dt.isoformat(), 'ret': round(r, 6)} for dt, r in days],
    }


# ── Ana hesaplama ─────────────────────────────────────────────────────────────

def compute_all(raw: dict) -> list:
    last_date = raw['last_date']
    y, m = last_date.year, last_date.month

    # Son 13 ay listesi
    months = []
    cy, cm = y, m
    for _ in range(13):
        months.append((cy, cm))
        cy, cm = _prev_month(cy, cm)
    months.reverse()

    stocks = []
    for ticker, daily in raw['daily'].items():
        if not daily: continue
        meta = raw['tickers'].get(ticker, {'type': 'Stock', 'industry': '', 'name': ticker})

        mom_12_1   = calc_momentum_12_1(daily, last_date)
        fip_annual = calc_fip_annual(daily, last_date)

        monthly = []
        for (my, mm) in months:
            mom_m   = calc_monthly_momentum(daily, my, mm)
            fip_m   = calc_fip_monthly(daily, my, mm)
            detail  = monthly_detail(daily, my, mm)
            monthly.append({
                'month':      f"{my}-{mm:02d}",
                'momentum':   round(mom_m,   6) if mom_m   is not None else None,
                'fip':        round(fip_m,   6) if fip_m   is not None else None,
                'neg_count':  detail['neg_count'],
                'pos_count':  detail['pos_count'],
                'flat_count': detail['flat_count'],
                'total_days': detail['total_days'],
                'days':       detail['days'],   # günlük kapanışlar
            })

        stocks.append({
            'ticker':   ticker,
            'name':     meta['name'],
            'type':     meta['type'],
            'industry': meta['industry'],
            'mom':      round(mom_12_1,   6) if mom_12_1   is not None else None,
            'fip':      round(fip_annual, 6) if fip_annual is not None else None,
            'monthly':  monthly,
        })

    stocks.sort(key=lambda s: s['mom'] if s['mom'] is not None else -999, reverse=True)
    return stocks
