# Labyrinth BIST Momentum Screener

Wesley R. Gray — Quantitative Momentum metodolojisi ile BIST hisse takibi.

## Metodoloji
- **12-1M Momentum**: Son 12 ay, cari ay hariç kümülatif getiri
- **FIP (Frog in the Pan)**: `sign(12-1M) × (neg% − pos%)` — negatif = kaliteli smooth momentum
- Her gün 18:30 Türkiye saatinde otomatik güncelleme

## Dosya Yapısı
```
engine.py          # Momentum & FIP hesaplama motoru
fetch.py           # yfinance veri çekme
update_excel.py    # Excel yazma
build_site.py      # Site derleme
run.py             # Ana script (GitHub Actions)
template.html      # Dashboard şablonu
docs/              # Yayınlanan site (GitHub Pages)
  index.html
  data/
    stocks.json    # Tüm hisse verisi
    meta.json      # İstatistikler
    momentum_today.csv  # Manuel kontrol için CSV
```
