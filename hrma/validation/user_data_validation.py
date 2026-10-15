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
# ÖH D26 / OH-D25-14: ``np.trapz`` NumPy 2.0'da ad alanından
# KALDIRILDI (np.trapezoid); ad TEK YERDE çözülür.
from hrma.utils.numeric_compat import trapezoid as _trapezoid

from hrma.constants import G_0
# P10B2-16: bağıl fark yüzdesinin TEK tanım noktası (referans ADIYLA verilir).
from hrma.validation._relative import (
    REFERENCE_MEASUREMENT, relative_difference_pct)

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
# ---------------------------------------------------------------------------
# BİRİM → SI ÇARPANI — TEK KAYNAK (P10B2-05, ÖH D16/app-api)
#
# Önceki davranış iki yerde iki türlüydü: AYRI birim satırı (``s;kgf``)
# görüldüğünde "SI dışı" uyarısı basılıyor ama dönüşüm yapılmıyordu; aynı
# bilgi BAŞLIK PARANTEZİNDE (``Thrust (kgf)``) geldiğinde ise
# ``_normalize_token`` parantezi atıyor ve birim SESSİZCE kayboluyordu —
# 100 kgf tepe veren gerçek eğri 100 N sayılıyor, hüküm "excellent" yerine
# "poor" çıkıyordu (ölçüldü: toplam impuls farkı -%89,8).
#
# Artık İKİ YOL DA aynı tablodan okur ve KULLANICININ BEYAN ETTİĞİ birim
# fiilen SI'ya çevrilir. Beyan tek başına çözüm değildir: sayı düzeltilir,
# künye (``units``) yalnız neyin okunduğunu ve hangi çarpanın uygulandığını
# söyler.
#
# Çarpanlar: NIST SP 811 (lbf = 4,448 221 615 260 5 N tam tanım),
# CGPM 1901 standart yerçekimi g_n = 9,806 65 m/s² (kgf).
# ---------------------------------------------------------------------------
_TIME_UNIT_FACTORS = {
    's': 1.0, 'sec': 1.0, 'secs': 1.0, 'seconds': 1.0,
    'ms': 1e-3,
}
_THRUST_UNIT_FACTORS = {
    'n': 1.0, 'newton': 1.0, 'newtons': 1.0,
    'kn': 1e3,
    'lbf': 4.4482216152605,
    'kgf': G_0,   # kgf TANIMI 1 kg x g_0 (ÖH P10B3-10, tek kaynak)
}
# Birim satırı tespiti için tipik birim tokenları
_UNIT_TOKENS = frozenset(_TIME_UNIT_FACTORS) | frozenset(_THRUST_UNIT_FACTORS)
# SI dışı birim = çarpanı 1 olmayan token (tablodan TÜRETİLİR, ikinci kez
# elle yazılmaz)
_NON_SI_UNIT_TOKENS = frozenset(
    ad for tablo in (_TIME_UNIT_FACTORS, _THRUST_UNIT_FACTORS)
    for ad, carpan in tablo.items() if carpan != 1.0)
# Künyede kullanılan okunur birim adları
_SI_UNIT_NAME = {'time': 's', 'thrust': 'N'}
_UNIT_FACTOR_TABLE = {'time': _TIME_UNIT_FACTORS,
                      'thrust': _THRUST_UNIT_FACTORS}


#: P10B2-05 ŞARTI (Fable-D16) — parantez içeriği boşluk içeriyorsa ya da
#: harf dışı karakter taşıyorsa birim beyanı sayılmaz
#: (``'Thrust (peak run 3)'`` yanlış alarm üretmesin diye).
#:
#: ÖH D20 / P10B2-05 ŞARTI (Fable-D18) — TAVAN TABLODAN TÜRETİLİR.
#: ÖLÇÜLDÜ (taban 14acd1d, ``docs/scofield/raw/OH/D20/app-api/a1/once.json``):
#: elle yazılmış ``6`` tavanı, tanınan birimlerin en uzunundan
#: (``'newtons'``/``'seconds'``, 7 karakter) KISAYDI ve delik açıyordu —
#: ``'Thrust (kilonewton)'``, ``'Thrust (poundforce)'``, ``'Time (minutes)'``
#: üçünde de ``declared_raw=None``, ``source='assumed (no unit declared)'``,
#: uyarı 0. Yani beyan VARKEN ürün "hiç birim beyan edilmedi" diyordu ve
#: ``'minutes'`` 60× sessiz hataya dönüşüyordu. Boşluk + yalnız-harf kuralı
#: yanlış alarmı zaten kestiği için tavanın tek işi "makul bir birim ADI ne
#: kadar uzun olabilir" sorusudur; bu yüzden tablonun kendi maksimumunun
#: ÜSTÜNDE tutulur ve tablo büyürse kendiliğinden büyür (tek kaynak: tavan
#: bir daha tanınan bir birimin kendi uzunluğunun altına düşemez).
_UNIT_RAW_MAX_LEN = max(16, max(len(_t) for _t in _UNIT_TOKENS) + 1)


def _birim_ham_token(ham):
    """Parantez/hücre içeriğini birim ADAYI alfa token'a indirger.

    Tanınmayan birimi FAIL-CLOSED bildirebilmek için gerekir: kullanıcı
    ``'lbs'`` yazdıysa ürün "hiç birim beyan edilmedi" DİYEMEZ. Birim
    adayı sayılma ölçütü dar tutulur — boşluksuz, yalnız harf, en fazla
    ``_UNIT_RAW_MAX_LEN`` karakter (tavan tablodan türetilir; yukarıya bak).
    """
    if ham is None:
        return None
    s = str(ham).strip()
    if not s or any(ch.isspace() for ch in s):
        return None
    token = _normalize_token(s)
    if not token or not token.isalpha() or len(token) > _UNIT_RAW_MAX_LEN:
        return None
    return token


def _header_unit_beyani(field):
    """``(tanınan token | None, ham birim adayı | None)``.

    ``'Thrust (kgf)'`` -> ``('kgf', 'kgf')`` · ``'Thrust (lbs)'`` ->
    ``(None, 'lbs')`` · ``'Thrust'`` -> ``(None, None)``.
    ``_normalize_token`` bu parantezi ATAR (başlık eşlemesi birimden
    bağımsız kalsın diye); burada aynı parantez OKUNUR.
    """
    if field is None:
        return None, None
    eslesme = re.findall(r'[\(\[\{]([^\)\]\}]*)[\)\]\}]', str(field))
    ham_aday = None
    for ham in eslesme:
        token = _normalize_token(ham)
        if token in _UNIT_TOKENS:
            return token, token
        if ham_aday is None:
            ham_aday = _birim_ham_token(ham)
    return None, ham_aday


def _header_unit_token(field):
    """Başlık parantezindeki TANINAN birim; tanınmıyorsa ``None``."""
    return _header_unit_beyani(field)[0]

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
# KANONİK SATIR BANDI (ÖH D32 / P7B4-23 + OH-D31-12)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (D32 app-api-uc a2, ``once.json`` K1-K3; bu makine, taban
# ``dd1dcddc``): ``/api/validation/upload-csv`` satır ekseninde SINIRSIZDI.
# 600 000 satırlık gövde (11,34 MiB) HTTP 200 veriyor, 0,696 s sürüyor ve
# 8,42 MiB yanıt üretiyor; ne uçta ne ayrıştırıcıda okunan bir satır sayısı
# bandı vardı. Tek sınır ``MAX_CONTENT_LENGTH`` (32 MiB) BAYT tavanıdır ve
# ölçülen 18,0 bayt/satır ile ~1,86 MİLYON satıra denk düşer (K3) — yani
# satır ekseninde fiilen koruma yoktu.
#
# ALT UÇ yeni bir karar değildir: ``parse_thrust_csv`` zaten en az 2
# (zaman, itki) satırı istiyordu; sayı gövdenin içinde ve kullanıcı hata
# metninde İKİ yerde yazılıydı, artık YALNIZ burada durur (doktrin 4).
#
# ÜST UÇ bir BÜTÇEDİR, fiziksel sabit değildir — ve deponun kendi bütçe
# yöntemiyle seçilmiştir (``app.py``, XLSX bütçe bloğu: "sınırların dayanağı
# bu makinede ölçüldü", sessiz kırpma yerine açık ret). 100 000 satır:
#
#   * deponun tek yanıtta taşımayı ZATEN kabul ettiği seri uzunluğudur
#     (``XLSX_MAX_ROWS_PER_SHEET``; 50 000 satır × 10 sütun → 1,4 s / 263 MB
#     ölçümüyle seçilmişti). Sayı oradan İTHAL EDİLMEZ: o tavan bir çalışma
#     sayfasının biçim bütçesidir, bu tavan bir ölçüm kaydının uzunluğudur;
#     ikisini tek sabite bağlamak sahte bir tek-kaynak olurdu. Ölçülen
#     maliyetleri ayrı ayrı yazılı: bu uçta 100 000 satır 0,113 s ve
#     1,32 MiB yanıt (K1).
#   * ürünün KENDİ zarfının çok üstündedir: modellenebilen en uzun yanma
#     ``motor_validation.CANONICAL_LIMITS['burn_time']['max']`` = 300 s
#     olduğuna göre bu tavan, 300 s'lik kesintisiz bir ateşlemede ~333 Hz,
#     30 s'lik tipik bir ateşlemede ~3,3 kHz örnekleme demektir. Meşru
#     hiçbir static-fire kaydı kesilmez.
#
# Aşım SESSİZCE KIRPILMAZ (doktrin 1): uç, hangi sınırın hangi değerle
# aşıldığını söyleyen makine-okur bir ret döndürür.
#: Ayrıştırıcının ÇÖZEBİLDİĞİ en az veri satırı (eğri iki noktadan başlar).
THRUST_CSV_MIN_ROWS = 2

#: Tek yükte kabul edilen en çok veri satırı (yukarıdaki ölçüm).
THRUST_CSV_MAX_ROWS = 100_000

#: Bandın kendisi — tüketiciler (uç, bekçi, panel) bunu okur.
THRUST_CSV_ROW_BAND = (THRUST_CSV_MIN_ROWS, THRUST_CSV_MAX_ROWS)

#: Başlık araması bu kadar satır içinde yapılır (``parse_thrust_csv``ın
#: kendi penceresi; sayı orada ikinci kez yazılmaz).
THRUST_CSV_HEADER_SEARCH_LINES = 5

#: Veri OLMAYAN satır payı: başlık penceresi + hemen ardındaki birim satırı.
#: Ayrıştırmadan ÖNCEKİ kaba sayımın bandı yanlışlıkla aşmaması için bu pay
#: düşülür — yani kapı, kesin olarak bandın dışında olan yükleri kapatır.
THRUST_CSV_MAX_NON_DATA_LINES = THRUST_CSV_HEADER_SEARCH_LINES + 1


def candidate_data_rows(text):
    """Ayrıştırmadan ÖNCE veri satırı adayı sayısı (ÜST sınır).

    Boş satırlar sayılmaz; başlık/birim payı düşülür. Gerçek veri satırı
    sayısı (``parse_thrust_csv`` sonrası ``n_points``) bundan KÜÇÜK ya da
    eşittir — sayısal olmayan satırlar ve tekrar eden zaman damgaları
    ayıklandığı için. Kapı bu üst sınıra bakar, dolayısıyla banda sığan
    hiçbir dosya yanlışlıkla reddedilmez.
    """
    if not isinstance(text, str):
        return 0
    dolu = sum(1 for satir in text.splitlines() if satir.strip())
    return max(0, dolu - THRUST_CSV_MAX_NON_DATA_LINES)


def thrust_csv_row_band_error(row_count, field='csv_rows'):
    """Satır bandı aşıldıysa makine-okur ret künyesi, aşılmadıysa ``None``.

    Künye biçimi deponun kendi bütçe sözleşmesidir (``app.py``
    ``_xlsx_budget_error``): ``limit`` / ``maximum`` / ``requested``. Uca
    özgü ``field`` + ``reason`` çifti ÖK-21 ret biçimini taşır, ``error``
    ise BU UCUN kendi sözleşmesindeki gibi kullanıcıya gösterilebilir
    İngilizce cümledir (panel ``data.error``’u ekrana basar).
    """
    try:
        n = int(row_count)
    except (TypeError, ValueError):
        return None
    if n <= THRUST_CSV_MAX_ROWS:
        return None
    return {
        'status': 'error',
        'error': (
            f'The uploaded thrust record has more than '
            f'{THRUST_CSV_MAX_ROWS} data rows ({n} counted). This endpoint '
            f'accepts {THRUST_CSV_MIN_ROWS} to {THRUST_CSV_MAX_ROWS} rows '
            f'per upload; nothing was truncated. Decimate or trim the '
            f'record to the firing window and upload it again.'),
        'reason': 'row_band_exceeded',
        'field': field,
        'limit': 'data_rows',
        'minimum': THRUST_CSV_MIN_ROWS,
        'maximum': THRUST_CSV_MAX_ROWS,
        'requested': n,
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
    - Birim beyanı İKİ yoldan okunur ve İKİSİ DE aynı çarpan tablosundan
      geçer (P10B2-05): başlık parantezi ("Thrust (kgf)") ve başlıktan
      hemen sonraki birim satırı ("s;kgf"). SI dışı beyan edilen sütun
      fiilen SI'ya ÇEVRİLİR ve çevrim uyarıyla + ``units`` künyesiyle
      bildirilir. Beyan yoksa çevrim de yoktur (SI varsayılır).
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
        'n_points': int, 'units': dict}`` — zaman artan sırada, tekrar eden
        zaman damgaları ayıklanmış; ``units`` her sütun için beyan edilen
        birimi, uygulanan çarpanı ve beyanın kaynağını taşır.

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

    # --- Başlık arama (pencere: THRUST_CSV_HEADER_SEARCH_LINES) ---
    time_col = thrust_col = None
    header_line_idx = None
    data_start = 0
    # {'time'|'thrust': (token|None, kaynak|None, ham beyan|None)}
    # P10B2-05 (+ ŞARTI): ham beyan, TANINMAYAN birimi bildirmek için.
    birim_beyani = {'time': (None, None, None),
                    'thrust': (None, None, None)}
    for idx in range(min(THRUST_CSV_HEADER_SEARCH_LINES,
                         len(lines))):
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
            # P10B2-05: başlık parantezindeki birim ARTIK okunuyor.
            # `_normalize_token` onu eşleme için atar; burada beyan olarak
            # saklanır ve aşağıda SI'ya çevrilir.
            for _rol, _sutun in (('time', t_col), ('thrust', f_col)):
                _tok, _ham = _header_unit_beyani(fields[_sutun])
                birim_beyani[_rol] = (_tok, 'header', _ham)
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
            # P10B2-05: birim satırı da BAŞLIK PARANTEZİYLE aynı tablodan
            # okunur; satır daha açık bir beyandır, başlık parantezini ezer.
            for rol, sutun in (('time', time_col), ('thrust', thrust_col)):
                if sutun is None or sutun >= len(norms) or not norms[sutun]:
                    continue
                satir_tok = norms[sutun]
                onceki_tok, _onceki_kaynak, onceki_ham = birim_beyani[rol]
                onceki_beyan = onceki_tok or onceki_ham
                if satir_tok in _UNIT_FACTOR_TABLE[rol]:
                    yeni_beyan = (satir_tok, 'unit row', satir_tok)
                else:
                    # P10B2-05 ŞARTI: satırdaki TANINMAYAN birim de bir
                    # beyandır; sessizce "beyan yok"a düşmez.
                    ham = _birim_ham_token(satir_tok)
                    if ham is None:
                        continue
                    yeni_beyan = (None, 'unit row', ham)
                yeni_ad = yeni_beyan[0] or yeni_beyan[2]
                if onceki_beyan and onceki_beyan != yeni_ad:
                    warnings.append(
                        f"{rol.capitalize()} unit is declared twice and the "
                        f"two declarations disagree: header says "
                        f"'{onceki_beyan}', unit row says '{yeni_ad}'. The "
                        f"unit row was used.")
                birim_beyani[rol] = yeni_beyan
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

    if len(t_values) < THRUST_CSV_MIN_ROWS:
        raise ValueError(
            f"Could not parse thrust data: at least {THRUST_CSV_MIN_ROWS} "
            "numeric (time, thrust) rows are required. Check that the file "
            "is a CSV with columns like 'time,thrust' (seconds, newtons).")

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

    # --- P10B2-05: BEYAN EDİLEN BİRİMİ SI'YA ÇEVİR --------------------
    # Kullanıcı birimi başlıkta ya da birim satırında AÇIKÇA yazdıysa sayı
    # düzeltilir; beyan tek başına bırakılmaz. Beyan yoksa hiçbir varsayım
    # yapılmaz (SI kabul edilir — modülün belgelenmiş sözleşmesi) ve künye
    # bunu 'assumed' diye söyler: uydurma çevrim yok.
    birim_kunyesi = {}
    for rol, dizi in (('time', t_arr), ('thrust', f_arr)):
        token, kaynak, ham_beyan = birim_beyani[rol]
        carpan = _UNIT_FACTOR_TABLE[rol].get(token) if token else None
        if carpan is None:
            # P10B2-05 ŞARTI (Fable-D16) — TANINMAYAN BİRİM FAIL-CLOSED.
            # ÖLÇÜLDÜ (taban 9071a64, once_a1.json): "Thrust (lbs)" /
            # "Thrust (lb)" / "Time (min)" başlıklarında künye
            # ``declared: null`` + ``source: 'assumed (no unit declared)'``
            # basıyor ve TEK uyarı bile çıkmıyordu — yani kullanıcı birimi
            # AÇIKÇA yazmışken ürün "hiç birim beyan edilmedi" diyordu.
            # 100 lbs (=444,82 N) sessizce 100 N sayılıyordu (4,45×).
            # Artık beyan varsa sayı çevrilmese bile SUSULMAZ: uyarı basılır
            # ve künye ``declared_raw`` ile neyin okunduğunu söyler.
            beyan_adi = token or ham_beyan
            if beyan_adi is None:
                birim_kunyesi[rol] = {
                    'declared': None,
                    'declared_raw': None,
                    'assumed_si_unit': _SI_UNIT_NAME[rol],
                    'factor_applied': 1.0,
                    'source': 'assumed (no unit declared)',
                }
                continue
            bilinenler = ', '.join(sorted(_UNIT_FACTOR_TABLE[rol]))
            warnings.append(
                f"{(kaynak or 'header').capitalize()} declares "
                f"{rol} unit '{beyan_adi}' — not recognized; known {rol} "
                f"units: {bilinenler}. Values were used as-is (no "
                f"conversion) and are treated as "
                f"{_SI_UNIT_NAME[rol]}.")
            birim_kunyesi[rol] = {
                'declared': None,
                'declared_raw': beyan_adi,
                'assumed_si_unit': _SI_UNIT_NAME[rol],
                'factor_applied': 1.0,
                'source': f'{kaynak or "header"} (unrecognized)',
            }
            continue
        if carpan != 1.0:
            dizi *= carpan
            warnings.append(
                f"{rol.capitalize()} column declared in '{token}' "
                f"({kaynak}); values were converted to "
                f"{_SI_UNIT_NAME[rol]} (x{carpan:g}).")
        birim_kunyesi[rol] = {
            'declared': token,
            'declared_raw': token,
            'assumed_si_unit': _SI_UNIT_NAME[rol],
            'factor_applied': carpan,
            'source': kaynak,
        }

    return {
        'time': t_arr,
        'thrust': f_arr,
        'warnings': warnings,
        'n_points': int(len(t_arr)),
        # Hangi birimin okunduğu ve hangi çarpanın uygulandığı ürün yüzüne
        # taşınır (/api/validation/upload-csv 'parsed.units').
        'units': birim_kunyesi,
    }


# ---------------------------------------------------------------------------
# Karşılaştırma
# ---------------------------------------------------------------------------
def _curve_parts(curve, label):
    """Eğri yükünün ham (time, thrust) parçalarını verir — ÇEVİRMEDEN.

    Anahtar çözümü (``time``/``t``/``time_s``, ``thrust``/``F``/
    ``thrust_n``, ya da 2'li dizi) BURADA bir kez yazılıdır; hem
    ``_as_curve`` hem de ``curve_point_count`` bunu okur (doktrin 4).
    """
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
    return t, f


def curve_point_count(curve):
    """Eğri yükünün nokta sayısı (ÜST sınır), çözülemezse ``0``.

    ÖH D32 / P7B4-23 ikinci ayağı: ``/api/validation/upload-csv`` JSON
    biçiminde ``predicted_curve`` dizisi de alıyor ve bu eksende hiçbir
    bant yoktu (ÖLÇÜLDÜ: 300 000 nokta HTTP 200). Sayım diziyi ``numpy``a
    ÇEVİRMEDEN yapılır — korumak istediğimiz belleği ölçüm sırasında
    harcamamak için. Çözülemeyen yük ``0`` döner: bandın işi değildir,
    ``_as_curve`` onu kendi 400'üyle karşılar (fail-closed korunur).
    """
    try:
        t, f = _curve_parts(curve, 'Curve')
    except ValueError:
        return 0
    try:
        return max(len(t), len(f))
    except TypeError:
        return 0


def _as_curve(curve, label):
    """(t, F) çiftine indirger: dict ({'time','thrust'}) veya 2'li dizi."""
    t, f = _curve_parts(curve, label)
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


#: Bu modülün yüzde farklarında PAYDA rolü — **KANON: ÖLÇÜM**.
#:
#: ÖH D30 / defter OH-D28-12 + P10B2-16 (ana model kararı, hüküm-18,
#: 9 Eylül 2026). D29'da formül tek tanım noktasına alınmış ama İKİ payda
#: yan yana bırakılmıştı: kardeş modül ``correlation_runner`` ÖLÇÜME,
#: bu modül TAHMİNE bölüyordu. ÖLÇÜLDÜ (``once.json`` ->
#: ``OH-D28-12+P10B2-16``, taban ``ab7cf68b``): aynı çift (ölçülen 1000,
#: tahmin 1100) koşucuda ``+10,0000 %``, burada ``-9,0909 %`` veriyordu —
#: İŞARET ZIT, büyüklük 0,909 puan farklı. Bir kullanıcı aynı iki sayıyı
#: aynı ürünün iki ekranında görüp iki farklı cevap alıyordu.
#:
#: KANON ÖLÇÜMDÜR: ASME V&V 20-2009 Böl. 2 karşılaştırma hatasını
#: ``E = S - D`` tanımlar ve deneysel veriye (``D``) normalize eder; burada
#: ``D`` kullanıcının static-fire ölçümü, ``S`` HRMA tahminidir. Metroloji
#: geleneğinde payda BİLİNEN büyüklüktür, modelin çıktısı değil.
#:
#: BU BİR SÖZLEŞME DEĞİŞİKLİĞİDİR (sürüm notuna girer): yayımlanan
#: ``*_diff_pct`` alanlarının İŞARETİ ve büyüklüğü kayar. Alanların ANLAMI
#: da netleşir: "tahmin ölçümden ne kadar sapıyor" (pozitif = tahmin
#: ölçümden büyük). Payda rolü ``diff_pct_reference`` künyesiyle
#: yayımlandığı için tüketici bunu koddan değil VERİDEN okur.
PCT_DIFF_REFERENCE = REFERENCE_MEASUREMENT


def _pct_diff(measured_value, predicted_value):
    """Kanonik bağıl fark: ``(tahmin - ölçüm) / ölçüm * 100``.

    Argüman sırası çağıranların okunabilirliği için (ölçülen, tahmin)
    olarak KORUNDU; payda rolünü :data:`PCT_DIFF_REFERENCE` belirler ve
    merkeze anahtar sözcükle verilir, yani sıra bir sözleşme taşımaz.
    """
    return relative_difference_pct(predicted_value, measured_value,
                                   reference=PCT_DIFF_REFERENCE)


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
    - Yüzde farklar ÖLÇÜME görelidir (ASME V&V 20-2009 kanonu; pozitif =
      HRMA tahmini ölçülen değerden büyük). Payda rolü yanıtta
      ``diff_pct_reference`` künyesiyle yayımlanır.
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
    impulse_u = float(_trapezoid(f_u, t_u))
    impulse_p = float(_trapezoid(f_p, t_p))
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
        f"{grade.capitalize()} agreement: the predicted total impulse "
        f"differs from the measured value by "
        f"{metrics['total_impulse_diff_pct']:+.1f}% "
        f"(measured {impulse_u:.1f} vs predicted {impulse_p:.1f} "
        f"N·s), peak thrust by "
        f"{metrics['peak_thrust_diff_pct']:+.1f}%, burn time by "
        f"{metrics['burn_time_diff_s']:+.2f} s. RMSE over the common time "
        f"window is {rmse:.1f} N ({nrmse_pct:.1f}% of predicted peak). "
        + advice)

    return {
        'metrics': metrics,
        'grade': grade,
        'assessment': assessment,
        'overlap': {'t_start': t0, 't_end': t1},
        # ÖH D27 / P11B4-24 — EŞİK TABLOSU UÇTAN YAYIMLANIR.
        # ÖLÇÜLDÜ (docs/scofield/raw/OH/D27/arayuz/a3/once.json): panelin
        # `diffKind`'ı 5/10/20 bandını KENDİ içinde tutuyordu; uç aynı
        # sayıları yayımlamıyordu. İki kaynak bugün eşit, ama buradaki eşik
        # değişince rozetin hükmü ile kartların rengi sessizce ayrışırdı.
        # `scored_metrics` ise skorun NEYE baktığını söyler: puan yalnız
        # max(|impuls farkı|, NRMSE) — tepe/ortalama itki ve yanma süresi
        # farkları skora GİRMEZ, o yüzden aynı bantla renklendirilemez.
        'grade_thresholds_pct': dict(GRADE_THRESHOLDS_PCT),
        'scored_metrics': ['total_impulse_diff_pct', 'nrmse_pct'],
        # OH-D28-12 + P10B2-16: '*_diff_pct' alanlarının PAYDASI.
        # D30'dan itibaren KANON tektir: payda ÖLÇÜMdür ve kardeş uç
        # (korelasyon koşucusu) ile AYNI roldür. Alan yayımlanmaya devam
        # eder ki tüketici hangi sözleşmeyi okuduğunu koddan değil VERİDEN
        # bilsin — künyenin kaybolması, kanonun sessizce geri kaymasına
        # kapı açardı.
        'diff_pct_reference': PCT_DIFF_REFERENCE,
    }
