"""Kullanıcının kendi static-fire CSV verisini HRMA tahminiyle karşılaştırma.

ARGE kararı (docs/ANALIZ_PLATFORM_PLANI.md): sentetik "doğrulama veritabanı"
vitrine çıkmaz; onun yerine kullanıcı KENDİ test standı CSV'sini yükler ve
HRMA'nın itki eğrisi tahminiyle nicel olarak karşılaştırılır.

Literatür çapaları (uydurma katsayı yok):
- Toplam impuls tanımı: I_t = ∫ F dt  — Sutton & Biblarz, "Rocket
  Propulsion Elements", 9th ed., Eq. (2-1). Sayısal integral bileşik
  yamuk kuralı (``numpy.trapz``) ile alınır.
- Yanma süresi tanımı: itkinin tepe değerin %5'ini İLK aştığı an ile SON
  düştüğü an arasındaki süre — NFPA 1125 (model/yüksek güçlü roket motoru
  sertifikasyonu) konvansiyonu; NAR/TRA motor sertifikasyon testlerinde ve
  thrustcurve.org veri işlemede aynı %5 eşiği kullanılır.
- Ortalama itki tanımı: F_avg = I_t / t_burn (aynı NFPA 1125 konvansiyonu).
- RMSE: standart kök-ortalama-kare hata; NRMSE burada tahmin edilen tepe
  itkiye normalize edilir (yüzde olarak raporlanır).

Değerlendirme eşikleri (%5/%10/%20) fiziksel sabit DEĞİL, mühendislik
yargısıyla seçilmiş raporlama kovalarıdır; module seviyesinde isimli
sabitler olarak tutulur ve metinde açıkça "agreement" dili kullanılır.

Kullanıcıya görünen tüm metinler İngilizce'dir (UI kuralı).
"""

import re

import numpy as np

# ---------------------------------------------------------------------------
# CSV başlık eşleme tabloları — normalize edilmiş (küçük harf, TR harfleri
# ASCII'ye indirgenmiş, birim parantezleri atılmış) tokenlar
# ---------------------------------------------------------------------------
TIME_ALIASES = frozenset({
    'time', 't', 'zaman', 'sure', 'times', 'ts', 'sec', 'seconds',
    'timesec', 'timeseconds', 'burntime', 'elapsed', 'elapsedtime',
})
THRUST_ALIASES = frozenset({
    'thrust', 'f', 'itki', 'force', 'kuvvet', 'thrustn', 'fn', 'load',
    'forcen', 'thrustforce',
})
# Birim satırı tespiti için tipik birim tokenları
_UNIT_TOKENS = frozenset({
    's', 'sec', 'secs', 'seconds', 'ms', 'n', 'newton', 'newtons',
    'kn', 'lbf', 'kgf',
})
# SI dışı birim uyarısı (dönüşüm YAPILMAZ — kullanıcı bilgilendirilir)
_NON_SI_UNIT_TOKENS = frozenset({'ms', 'kn', 'lbf', 'kgf'})

# Yanma süresi eşiği: tepe itkinin %5'i (NFPA 1125 konvansiyonu, üstte kaynak)
BURN_TIME_THRESHOLD_FRACTION = 0.05

# Karşılaştırma ızgarası çözünürlüğü (ortak zaman aralığında nokta sayısı)
COMPARISON_GRID_POINTS = 200

# Raporlama kovaları — mühendislik yargısı, fiziksel sabit değil
GRADE_THRESHOLDS_PCT = {
    'excellent': 5.0,
    'good': 10.0,
    'fair': 20.0,
}


# ---------------------------------------------------------------------------
# CSV ayrıştırma
# ---------------------------------------------------------------------------
def _normalize_token(field):
    """Başlık/birim alanını karşılaştırılabilir token'a indirger."""
    s = str(field).strip().strip('"\'').lower()
    s = re.sub(r'[\(\[\{].*?[\)\]\}]', '', s)  # birim parantezlerini at
    # TR harflerini ASCII'ye indir (yalnız eşleme için; veri değişmez)
    s = (s.replace('ı', 'i').replace('ü', 'u').replace('ö', 'o')
         .replace('ş', 's').replace('ç', 'c').replace('ğ', 'g')
         .replace('İ', 'i'))
    s = re.sub(r'[^a-z0-9]+', '', s)
    return s


def _to_float(field, decimal_comma_ok):
    """Alanı float'a çevir; başarısızsa None. TR ondalık virgülü desteği."""
    s = str(field).strip().strip('"\'')
    if not s:
        return None
    if decimal_comma_ok and ',' in s and '.' not in s:
        s = s.replace(',', '.')
    try:
        value = float(s)
    except ValueError:
        return None
    if not np.isfinite(value):
        return None
    return value


def _detect_delimiter(line):
    """Ayraç sezgisi: noktalı virgül > tab > virgül > boşluk."""
    if ';' in line:
        return ';'
    if '\t' in line:
        return '\t'
    if ',' in line:
        return ','
    return None  # whitespace split


def _split(line, delimiter):
    if delimiter is None:
        return line.split()
    return [f.strip() for f in line.split(delimiter)]


def parse_thrust_csv(text):
    """Esnek static-fire CSV ayrıştırıcı.

    Toleranslar:
    - Başlık takma adları: time/t/zaman/süre..., thrust/F/itki/force/kuvvet...
      (büyük/küçük harf ve "(s)" gibi birim ekleri önemsiz).
    - Ayraç: ``;`` / tab / ``,`` / boşluk (otomatik sezilir).
    - TR ondalık virgülü: ``;``, tab veya boşluk ayraçlı dosyalarda ``0,5``
      → 0.5. Virgül ayraçlı dosyada satır alan sayısı beklenenin tam iki
      katıysa alan çiftleri ondalık olarak birleştirilir (Excel TR tuzağı).
    - Başlıktan hemen sonra gelen birim satırı ("s;N" gibi) atlanır;
      SI dışı birim görülürse uyarı üretilir (dönüşüm yapılmaz).
    - Boş satırlar ve sayısal olmayan satırlar uyarıyla atlanır.
    - Başlıksız iki sütunlu sayısal dosya kabul edilir (uyarıyla:
      1. sütun zaman [s], 2. sütun itki [N] varsayılır).

    Parameters
    ----------
    text : str
        CSV dosya içeriği (UTF-8 metin; BOM toleranslı).

    Returns
    -------
    dict
        ``{'time': np.ndarray, 'thrust': np.ndarray, 'warnings': [str],
        'n_points': int}`` — zaman artan sırada, tekrar eden zaman damgaları
        ayıklanmış.

    Raises
    ------
    ValueError
        Ayrıştırılabilir en az 2 (zaman, itki) satırı yoksa; hata mesajı
        kullanıcıya gösterilebilir netliktedir (İngilizce).
    """
    if not isinstance(text, str):
        raise ValueError(
            "CSV content must be text. Please upload a plain-text CSV file.")
    text = text.lstrip('﻿')  # UTF-8 BOM toleransı
    raw_lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in raw_lines if ln]
    if not lines:
        raise ValueError(
            "The uploaded file is empty. Expected a CSV with time and "
            "thrust columns (e.g. 'time,thrust').")

    warnings = []
    delimiter = _detect_delimiter(lines[0])
    # Virgül ayraçta virgül aynı zamanda ondalık olamaz; diğerlerinde olur
    decimal_comma_ok = delimiter != ','

    # --- Başlık arama (ilk 5 satır içinde) ---
    time_col = thrust_col = None
    header_line_idx = None
    data_start = 0
    for idx in range(min(5, len(lines))):
        fields = _split(lines[idx], delimiter)
        norms = [_normalize_token(f) for f in fields]
        # Sayısal satırsa başlık yok demektir
        numeric = [_to_float(f, decimal_comma_ok) for f in fields]
        if sum(v is not None for v in numeric) >= 2:
            break
        t_col = next((i for i, n in enumerate(norms) if n in TIME_ALIASES),
                     None)
        f_col = next((i for i, n in enumerate(norms)
                      if n in THRUST_ALIASES and i != t_col), None)
        if t_col is not None and f_col is not None:
            time_col, thrust_col = t_col, f_col
            header_line_idx = idx
            data_start = idx + 1
            expected_fields = len(fields)
            break
        warnings.append(
            f"Line {idx + 1} ('{lines[idx][:40]}') is neither a recognized "
            "header nor numeric data; skipped.")
        data_start = idx + 1

    if header_line_idx is None:
        # Başlıksız mod: ilk sayısal satırdan itibaren 1. sütun zaman,
        # 2. sütun itki varsayılır
        time_col, thrust_col = 0, 1
        expected_fields = None
        warnings.append(
            "No header row detected; assuming column 1 is time [s] and "
            "column 2 is thrust [N].")

    # --- Birim satırı toleransı (başlıktan hemen sonra) ---
    if header_line_idx is not None and data_start < len(lines):
        fields = _split(lines[data_start], delimiter)
        norms = [_normalize_token(f) for f in fields]
        numeric = [_to_float(f, decimal_comma_ok) for f in fields]
        if all(v is None for v in numeric) and any(n in _UNIT_TOKENS
                                                   for n in norms if n):
            non_si = sorted({n for n in norms if n in _NON_SI_UNIT_TOKENS})
            if non_si:
                warnings.append(
                    f"Unit row suggests non-SI units ({', '.join(non_si)}); "
                    "values are used as-is. Expected seconds and newtons.")
            else:
                warnings.append(
                    f"Unit row ('{lines[data_start]}') skipped.")
            data_start += 1

    # --- Veri satırları ---
    t_values, f_values = [], []
    skipped = 0
    pair_merge_warned = False
    needed = max(time_col, thrust_col) + 1
    for idx in range(data_start, len(lines)):
        fields = _split(lines[idx], delimiter)
        # Excel TR tuzağı: virgül ayraç + ondalık virgül → alan sayısı iki
        # katına çıkar ("0,5,100,2" → 0.5 ve 100.2). Yalnızca alan sayısı
        # beklenenin TAM iki katıysa çiftler birleştirilir.
        if (delimiter == ',' and expected_fields is not None
                and len(fields) == 2 * expected_fields):
            merged = ['.'.join((fields[2 * i], fields[2 * i + 1]))
                      for i in range(expected_fields)]
            if all(_to_float(m, False) is not None for m in merged):
                fields = merged
                if not pair_merge_warned:
                    warnings.append(
                        "Comma-delimited file appears to use commas as "
                        "decimal separators too; adjacent fields were "
                        "merged (e.g. '0,5' read as 0.5).")
                    pair_merge_warned = True
        if len(fields) < needed:
            skipped += 1
            continue
        t = _to_float(fields[time_col], decimal_comma_ok)
        f = _to_float(fields[thrust_col], decimal_comma_ok)
        if t is None or f is None:
            skipped += 1
            continue
        t_values.append(t)
        f_values.append(f)

    if skipped:
        warnings.append(
            f"Skipped {skipped} non-numeric or malformed data row(s).")

    if len(t_values) < 2:
        raise ValueError(
            "Could not parse thrust data: at least 2 numeric (time, thrust) "
            "rows are required. Check that the file is a CSV with columns "
            "like 'time,thrust' (seconds, newtons).")

    t_arr = np.asarray(t_values, dtype=float)
    f_arr = np.asarray(f_values, dtype=float)

    # Zaman sırası ve tekrarlar
    if np.any(np.diff(t_arr) < 0):
        order = np.argsort(t_arr, kind='stable')
        t_arr, f_arr = t_arr[order], f_arr[order]
        warnings.append("Time values were not sorted; rows were re-ordered "
                        "by time.")
    dup_mask = np.concatenate(([True], np.diff(t_arr) > 0))
    if not np.all(dup_mask):
        t_arr, f_arr = t_arr[dup_mask], f_arr[dup_mask]
        warnings.append("Duplicate time stamps removed (first occurrence "
                        "kept).")
    if len(t_arr) < 2:
        raise ValueError(
            "Could not parse thrust data: fewer than 2 distinct time "
            "stamps remain after cleaning.")
    if np.any(f_arr < 0):
        warnings.append("Negative thrust values present — check load-cell "
                        "tare/offset. Values were kept as-is.")

    return {
        'time': t_arr,
        'thrust': f_arr,
        'warnings': warnings,
        'n_points': int(len(t_arr)),
    }


# ---------------------------------------------------------------------------
# Karşılaştırma
# ---------------------------------------------------------------------------
def _as_curve(curve, label):
    """(t, F) çiftine indirger: dict ({'time','thrust'}) veya 2'li dizi."""
    if isinstance(curve, dict):
        t = curve.get('time', curve.get('t', curve.get('time_s')))
        f = curve.get('thrust', curve.get('F', curve.get('thrust_n')))
        if t is None or f is None:
            raise ValueError(
                f"{label} curve dict must contain 'time' and 'thrust' keys.")
    else:
        try:
            t, f = curve[0], curve[1]
        except (TypeError, IndexError, KeyError):
            raise ValueError(
                f"{label} curve must be a dict with 'time'/'thrust' or a "
                "(time, thrust) pair of arrays.")
    t = np.asarray(t, dtype=float)
    f = np.asarray(f, dtype=float)
    if t.ndim != 1 or f.ndim != 1 or len(t) != len(f):
        raise ValueError(
            f"{label} curve time and thrust arrays must be 1-D and of "
            "equal length.")
    if len(t) < 2:
        raise ValueError(f"{label} curve needs at least 2 points.")
    if not (np.all(np.isfinite(t)) and np.all(np.isfinite(f))):
        raise ValueError(f"{label} curve contains non-finite values.")
    if np.any(np.diff(t) < 0):
        order = np.argsort(t, kind='stable')
        t, f = t[order], f[order]
    if np.any(np.diff(t) <= 0):
        raise ValueError(
            f"{label} curve has duplicate time stamps; clean the data "
            "first (parse_thrust_csv does this automatically).")
    return t, f


def _burn_window(t, f, threshold_fraction):
    """NFPA 1125 tarzı yanma penceresi: tepe*%eşik kesişimleri.

    Kesişim anları komşu örnekler arasında doğrusal interpolasyonla
    bulunur. Dönen değer (t_start, t_end, burn_time).
    """
    peak = float(np.max(f))
    if peak <= 0.0:
        raise ValueError(
            "Thrust curve peak is not positive; cannot determine burn time.")
    thr = threshold_fraction * peak
    above = np.nonzero(f >= thr)[0]
    i0, i1 = int(above[0]), int(above[-1])

    if i0 == 0:
        t_start = float(t[0])
    else:
        df = f[i0] - f[i0 - 1]
        t_start = float(t[i0]) if df == 0 else float(
            t[i0 - 1] + (thr - f[i0 - 1]) * (t[i0] - t[i0 - 1]) / df)
    if i1 == len(t) - 1:
        t_end = float(t[-1])
    else:
        df = f[i1 + 1] - f[i1]
        t_end = float(t[i1]) if df == 0 else float(
            t[i1] + (thr - f[i1]) * (t[i1 + 1] - t[i1]) / df)
    return t_start, t_end, t_end - t_start


def _pct_diff(user_value, predicted_value):
    """Tahmine göre yüzde fark: (user - predicted) / predicted * 100."""
    return (user_value - predicted_value) / predicted_value * 100.0


def compare(user_curve, predicted_curve,
            threshold_fraction=BURN_TIME_THRESHOLD_FRACTION,
            n_grid=COMPARISON_GRID_POINTS):
    """Kullanıcı static-fire eğrisini HRMA tahminiyle karşılaştır.

    Parameters
    ----------
    user_curve, predicted_curve : dict veya (t, F) çifti
        ``{'time': ..., 'thrust': ...}`` (parse_thrust_csv çıktısı doğrudan
        verilebilir) ya da (zaman [s], itki [N]) dizisi çifti.
    threshold_fraction : float
        Yanma süresi eşiği (tepe itkinin oranı; varsayılan 0.05 = NFPA 1125).
    n_grid : int
        RMSE için ortak zaman ızgarası nokta sayısı.

    Returns
    -------
    dict
        ``'metrics'`` (sayısal karşılaştırma), ``'grade'``
        (excellent/good/fair/poor), ``'assessment'`` (İngilizce metin),
        ``'overlap'`` (ortak zaman penceresi).

    Notes
    -----
    - Toplam impuls her eğrinin KENDİ zaman aralığında yamuk kuralıyla
      alınır (Sutton Eq. 2-1); RMSE ise iki eğrinin ÖRTÜŞEN aralığında
      ortak ızgaraya ``numpy.interp`` ile indirgenerek hesaplanır.
    - Yüzde farklar HRMA tahminine görelidir (pozitif = kullanıcı verisi
      tahminden büyük).
    """
    t_u, f_u = _as_curve(user_curve, 'User')
    t_p, f_p = _as_curve(predicted_curve, 'Predicted')

    # Örtüşen zaman penceresi (RMSE için)
    t0 = max(float(t_u[0]), float(t_p[0]))
    t1 = min(float(t_u[-1]), float(t_p[-1]))
    if t1 <= t0:
        raise ValueError(
            "User and predicted thrust curves do not overlap in time; "
            "check the time units/offset of the uploaded data.")

    grid = np.linspace(t0, t1, int(n_grid))
    fu_i = np.interp(grid, t_u, f_u)
    fp_i = np.interp(grid, t_p, f_p)
    rmse = float(np.sqrt(np.mean((fu_i - fp_i) ** 2)))

    # Tekil eğri metrikleri
    impulse_u = float(np.trapz(f_u, t_u))
    impulse_p = float(np.trapz(f_p, t_p))
    peak_u = float(np.max(f_u))
    peak_p = float(np.max(f_p))
    if impulse_p <= 0 or peak_p <= 0:
        raise ValueError(
            "Predicted curve has non-positive total impulse or peak "
            "thrust; comparison is not meaningful.")
    _, _, burn_u = _burn_window(t_u, f_u, threshold_fraction)
    _, _, burn_p = _burn_window(t_p, f_p, threshold_fraction)
    if burn_u <= 0 or burn_p <= 0:
        raise ValueError(
            "Burn time evaluated to zero; the thrust curve may be a "
            "single spike or corrupted.")
    # Ortalama itki = I_t / t_burn (NFPA 1125 konvansiyonu)
    mean_u = impulse_u / burn_u
    mean_p = impulse_p / burn_p

    nrmse_pct = rmse / peak_p * 100.0
    metrics = {
        'mean_thrust_user_n': mean_u,
        'mean_thrust_predicted_n': mean_p,
        'mean_thrust_diff_pct': _pct_diff(mean_u, mean_p),
        'peak_thrust_user_n': peak_u,
        'peak_thrust_predicted_n': peak_p,
        'peak_thrust_diff_pct': _pct_diff(peak_u, peak_p),
        'total_impulse_user_ns': impulse_u,
        'total_impulse_predicted_ns': impulse_p,
        'total_impulse_diff_pct': _pct_diff(impulse_u, impulse_p),
        'burn_time_user_s': burn_u,
        'burn_time_predicted_s': burn_p,
        'burn_time_diff_s': burn_u - burn_p,
        'burn_time_diff_pct': _pct_diff(burn_u, burn_p),
        'rmse_n': rmse,
        'nrmse_pct': nrmse_pct,
    }

    # Not: puanlama iki gösterge üzerinden — impuls farkı (enerji bütçesi)
    # ve NRMSE (eğri şekli). Kovalar mühendislik yargısıdır (üst docstring).
    score = max(abs(metrics['total_impulse_diff_pct']), nrmse_pct)
    if score <= GRADE_THRESHOLDS_PCT['excellent']:
        grade = 'excellent'
        advice = ("The HRMA prediction closely reproduces the measured "
                  "curve; no model adjustment is indicated.")
    elif score <= GRADE_THRESHOLDS_PCT['good']:
        grade = 'good'
        advice = ("The prediction is within typical hybrid-motor test "
                  "scatter; review regression-rate coefficients if tighter "
                  "agreement is needed.")
    elif score <= GRADE_THRESHOLDS_PCT['fair']:
        grade = 'fair'
        advice = ("Noticeable deviation; check propellant regression-rate "
                  "coefficients (a, n), nozzle efficiency, and the oxidizer "
                  "feed model against test conditions.")
    else:
        grade = 'poor'
        advice = ("Large deviation; verify the test data units (seconds, "
                  "newtons), load-cell calibration, and the motor "
                  "configuration used for the prediction.")

    assessment = (
        f"{grade.capitalize()} agreement: total impulse differs by "
        f"{metrics['total_impulse_diff_pct']:+.1f}% "
        f"({impulse_u:.1f} vs {impulse_p:.1f} N·s), peak thrust by "
        f"{metrics['peak_thrust_diff_pct']:+.1f}%, burn time by "
        f"{metrics['burn_time_diff_s']:+.2f} s. RMSE over the common time "
        f"window is {rmse:.1f} N ({nrmse_pct:.1f}% of predicted peak). "
        + advice)

    return {
        'metrics': metrics,
        'grade': grade,
        'assessment': assessment,
        'overlap': {'t_start': t0, 't_end': t1},
    }
