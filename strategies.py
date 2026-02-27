"""
strategies.py — Üç ticaret stratejisi, haftalık Cuma güncellemesi
Wesley R. Gray — Quantitative Momentum metodolojisi
"""
import datetime


# ── Yardımcılar ───────────────────────────────────────────────────────────────

def _get_month(s, offset=0):
    m = s['monthly']
    idx = len(m) - 1 - offset
    return m[idx] if 0 <= idx < len(m) else None


def _last_friday(from_date=None):
    d = from_date or datetime.date.today()
    days_back = (d.weekday() - 4) % 7
    return d - datetime.timedelta(days=days_back)


def _next_friday(from_date=None):
    d = from_date or datetime.date.today()
    days_ahead = (4 - d.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return d + datetime.timedelta(days=days_ahead)


def _is_friday(d=None):
    return (d or datetime.date.today()).weekday() == 4


def _update_meta():
    """Güncelleme zamanlaması bilgisi üretir."""
    today      = datetime.date.today()
    last_fri   = _last_friday(today)
    next_fri   = _next_friday(today)
    is_today   = _is_friday(today)

    def date_tr(d):
        MONTHS = ['', 'Ocak','Şubat','Mart','Nisan','Mayıs','Haziran',
                  'Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık']
        DAYS   = ['Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi','Pazar']
        return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month]} {d.year}"

    return {
        'frequency':    'Haftalık — Her Cuma kapanış sonrası',
        'last_update':  last_fri.isoformat(),
        'last_update_tr': date_tr(last_fri),
        'next_update':  next_fri.isoformat(),
        'next_update_tr': date_tr(next_fri),
        'is_update_day': is_today,
        'days_until':   (next_fri - today).days,
    }


# ── Strateji 1: VIOP Long ─────────────────────────────────────────────────────

def score_viop_long(s):
    """
    VIOP LONG — Güçlenen aylık momentum + FIP iyileşmesi
    
    Sinyal:
    · Cari ay momentum > 0
    · ΔMom > 0: bir önceki aya göre ivme artıyor
    · ΔFIP ≤ 0: FIP daha negatife gidiyor = momentum kalitesi artıyor
    
    Risk: 12-1M negatifse trend tersine işlem → YÜKSEK risk olarak işaretlenir.
    """
    if s['type'] != 'VIOP': return None
    m0 = _get_month(s, 0)
    m1 = _get_month(s, 1)
    if not m0 or not m1: return None
    if None in (m0['momentum'], m1['momentum'], m0['fip'], m1['fip']): return None
    if m0['momentum'] <= 0: return None

    delta_mom = m0['momentum'] - m1['momentum']
    delta_fip = m0['fip']      - m1['fip']   # negatif = iyileşme

    score = (m0['momentum'] * 80
             + delta_mom    * 50
             - delta_fip    * 25      # delta_fip negatif ise bonus
             - (s['fip'] or 0) * 15)

    risk = ('YÜKSEK' if (s['mom'] is not None and s['mom'] < -0.05)
            else 'ORTA'   if (s['mom'] is not None and s['mom'] < 0.05)
            else 'NORMAL')

    # İnsan-okunabilir sinyaller
    signals = []
    if delta_mom > 0:       signals.append('ΔMom ↑ İvme güçleniyor')
    if delta_fip < 0:       signals.append('ΔFIP ↓ Kalite artıyor')
    if s['mom'] and s['mom'] > 0: signals.append('12-1M trend uyumlu')
    if risk == 'YÜKSEK':    signals.append('⚠ Trend karşı işlem')

    return {
        'score':      round(score, 4),
        'mom':        m0['momentum'],
        'fip':        m0['fip'],
        'delta_mom':  round(delta_mom, 6),
        'delta_fip':  round(delta_fip, 6),
        'mom_prev':   m1['momentum'],
        'fip_prev':   m1['fip'],
        'mom_12_1':   s['mom'],
        'fip_annual': s['fip'],
        'risk':       risk,
        'signals':    signals,
    }


# ── Strateji 2: VIOP Short ────────────────────────────────────────────────────

def score_viop_short(s):
    """
    VIOP SHORT — Zayıflayan momentum + kötüleşen ivme
    
    Sinyal:
    · Cari ay momentum < 0
    · ΔMom < 0: ivme daha da kötüleşiyor
    · 12-1M negatif zorunlu (trend uyumlu short)
    
    NOT: 12-1M > +5% olan hisseler listelenmez (trend karşı short = çok riskli).
    """
    if s['type'] != 'VIOP': return None
    m0 = _get_month(s, 0)
    m1 = _get_month(s, 1)
    if not m0 or not m1: return None
    if None in (m0['momentum'], m1['momentum'], m0['fip'], m1['fip']): return None
    if m0['momentum'] >= 0: return None
    if s['mom'] is not None and s['mom'] > 0.05: return None  # güçlü yukarı trend = skip

    delta_mom = m0['momentum'] - m1['momentum']
    delta_fip = m0['fip']      - m1['fip']

    score = (-m0['momentum'] * 80
             - delta_mom     * 50
             + delta_fip     * 20
             + (-(s['fip'] or 0)) * 10)

    trend_align = ('TREND İLE'   if (s['mom'] is not None and s['mom'] < -0.05)
                   else 'NÖTR'   if (s['mom'] is not None and s['mom'] < 0.05)
                   else 'DİKKAT')

    signals = []
    if delta_mom < 0:  signals.append('ΔMom ↓ İvme kötüleşiyor')
    if delta_fip > 0:  signals.append('ΔFIP ↑ Kalite bozuluyor')
    if s['mom'] and s['mom'] < 0: signals.append('12-1M trend uyumlu')
    signals.append('⚠ Short: kısa vadeli (1-4 hafta)')

    return {
        'score':       round(score, 4),
        'mom':         m0['momentum'],
        'fip':         m0['fip'],
        'delta_mom':   round(delta_mom, 6),
        'delta_fip':   round(delta_fip, 6),
        'mom_prev':    m1['momentum'],
        'fip_prev':    m1['fip'],
        'mom_12_1':    s['mom'],
        'fip_annual':  s['fip'],
        'trend_align': trend_align,
        'signals':     signals,
    }


# ── Strateji 3: BIST Spot Long ────────────────────────────────────────────────

def score_bist_long(s):
    """
    BIST SPOT LONG — 6-12 aylık periyot, Gray metodolojisi
    
    Kriterler:
    1. VIOP değil (sadece hisseler)
    2. 12-1M momentum pozitif ve yüksek
    3. FIP negatif (smooth momentum)
    4. Son 3 ayda tutarlı pozitif momentum
    5. Cari ay çökmemiş (kırılma yok)
    
    Kalite: S-Tier > A-Tier > B-Tier
    NOT: Her Cuma güncellenir. Ayın son Cumasını beklemeden girilir.
    """
    if s['type'] == 'VIOP': return None
    if s['mom'] is None or s['mom'] <= 0: return None
    if s['fip'] is None or s['fip'] >= 0: return None   # smooth zorunlu

    m0 = _get_month(s, 0)
    m1 = _get_month(s, 1)
    m2 = _get_month(s, 2)
    if not m0 or not m1: return None
    if m0['momentum'] is not None and m0['momentum'] < -0.05:
        return None   # momentum kırılması riski

    recent    = [m for m in [m0, m1, m2] if m and m.get('momentum') is not None]
    pos_count = sum(1 for m in recent if m['momentum'] > 0)
    avg_recent = sum(m['momentum'] for m in recent) / len(recent) if recent else 0

    # ΔMom — son aya göre ivme
    delta_mom = (m0['momentum'] - m1['momentum']) if (m0['momentum'] and m1['momentum']) else None

    score = (s['mom']     * 100
             + avg_recent * 40
             - s['fip']   * 20
             + pos_count  * 3)

    quality = ('S-TİER' if (s['mom'] > 0.5  and s['fip'] < -0.10 and pos_count == 3)
               else 'A-TİER' if (s['mom'] > 0.2  and s['fip'] < -0.05 and pos_count >= 2)
               else 'B-TİER')

    signals = []
    if quality == 'S-TİER': signals.append('✦ En yüksek kalite momentum')
    if s['fip'] < -0.15:    signals.append('FIP çok smooth')
    if pos_count == 3:      signals.append('3 ay üst üste pozitif')
    if delta_mom and delta_mom > 0: signals.append('ΔMom ↑ İvme artıyor')
    if s['mom'] > 1.0:      signals.append('⚠ +%100 üzeri — hacim kontrolü yapın')

    return {
        'score':       round(score, 4),
        'mom_12_1':    s['mom'],
        'fip_annual':  s['fip'],
        'mom_last':    m0['momentum'],
        'fip_last':    m0['fip'],
        'delta_mom':   round(delta_mom, 6) if delta_mom is not None else None,
        'avg_recent':  round(avg_recent, 6),
        'consistency': f"{pos_count}/{len(recent)} ay ↑",
        'quality':     quality,
        'signals':     signals,
    }


# ── Ana hesaplama ─────────────────────────────────────────────────────────────

def compute_strategies(stocks: list) -> dict:
    vl, vs, bl = [], [], []

    for s in stocks:
        for lst, fn in [(vl, score_viop_long), (vs, score_viop_short), (bl, score_bist_long)]:
            r = fn(s)
            if r:
                m0 = _get_month(s, 0)
                lst.append({
                    'ticker':     s['ticker'],
                    'name':       s['name'],
                    'type':       s['type'],
                    'industry':   s['industry'],
                    'signal':     r,
                    'last_month': m0['month'] if m0 else None,
                })

    for lst in (vl, vs, bl):
        lst.sort(key=lambda x: x['signal']['score'], reverse=True)

    timing = _update_meta()

    return {
        'timing':     timing,
        'viop_long':  vl[:25],
        'viop_short': vs[:20],
        'bist_long':  bl[:50],
    }
