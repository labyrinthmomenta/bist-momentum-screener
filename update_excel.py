"""
update_excel.py — Excel'e yeni günlerin verisini yazar.
Yeni tarihler için otomatik sütun açar.
"""
import datetime, logging
from pathlib import Path
import openpyxl

log = logging.getLogger(__name__)

SHEET_RAW  = "BIST D Return Data"
ROW_DATES  = 3
ROW_START  = 6
COL_TICKER = 4   # D sütunu (1-indexed)


def write_new_data(excel_path: Path, fetched: dict) -> bool:
    """
    fetched: {date: {ticker: pct_decimal}}
    Excel'e yazar. Yeni tarihler için sütun açar.
    """
    if not fetched:
        log.info("Yazılacak veri yok.")
        return True

    # Backup
    ts     = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = excel_path.with_name(f"{excel_path.stem}_backup_{ts}{excel_path.suffix}")
    try:
        import shutil
        shutil.copy2(excel_path, backup)
        log.info(f"Backup: {backup.name}")
    except Exception as e:
        log.warning(f"Backup atlandı: {e}")

    wb  = openpyxl.load_workbook(excel_path)
    ws  = wb[SHEET_RAW]

    # Tarih → sütun haritası (mevcut)
    date_row    = list(ws.iter_rows(min_row=ROW_DATES, max_row=ROW_DATES, values_only=True))[0]
    date_to_col = {}
    max_col     = COL_TICKER

    def _parse_date(v):
        if isinstance(v, datetime.datetime): return v.date()
        if isinstance(v, datetime.date):     return v
        if isinstance(v, str):
            for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%m/%d/%Y'):
                try: return datetime.datetime.strptime(v.strip(), fmt).date()
                except ValueError: pass
        if isinstance(v, (int, float)) and 40000 < v < 60000:
            return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(v)))
        return None

    for i, v in enumerate(date_row, start=1):
        d = _parse_date(v)
        if d is not None:
            date_to_col[d] = i
            if i > max_col:
                max_col = i

    # Ticker → satır haritası
    ticker_to_row = {}
    for ri, row in enumerate(ws.iter_rows(min_row=ROW_START, max_row=700, values_only=True)):
        t = row[COL_TICKER - 1]
        if t:
            ticker_to_row[str(t).strip()] = ri + ROW_START

    # Yeni tarihleri sütun olarak ekle
    new_dates = sorted(d for d in fetched if d not in date_to_col)
    if new_dates:
        log.info(f"{len(new_dates)} yeni tarih sütunu ekleniyor: {new_dates[0]} → {new_dates[-1]}")
        for nd in new_dates:
            max_col += 1
            cell = ws.cell(row=ROW_DATES, column=max_col)
            cell.value = datetime.datetime(nd.year, nd.month, nd.day)
            cell.number_format = 'YYYY-MM-DD'
            date_to_col[nd] = max_col
            log.info(f"  Yeni sütun: {nd} → col {max_col}")

    # Veriyi yaz
    written = skipped_date = skipped_ticker = 0
    for date, day_data in sorted(fetched.items()):
        excel_col = date_to_col.get(date)
        if excel_col is None:
            skipped_date += 1
            continue
        for ticker, val in day_data.items():
            row = ticker_to_row.get(ticker)
            if row is None:
                skipped_ticker += 1
                continue
            # pct_decimal → yüzde (Excel formatı: -1.039 gibi)
            ws.cell(row=row, column=excel_col).value = round(val * 100, 8)
            written += 1

    log.info(f"Yazılan hücre  : {written}")
    if skipped_date:
        log.warning(f"Atlanan tarih  : {skipped_date} (sütun bulunamadı)")
    if skipped_ticker:
        log.warning(f"Atlanan ticker : {skipped_ticker} (satır bulunamadı)")

    wb.save(excel_path)
    wb.close()
    return True
