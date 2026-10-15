"""RASP (.eng) ve RockSim (.rse) motor itki eğrisi dosyalarının ayrıştırılması.

Kaynak biçim tanımları:
- RASP .eng: thrustcurve.org "RASP" biçimi — ``;`` ile başlayan satırlar
  yorumdur; ilk yorum-olmayan satır 7 alanlı başlıktır
  (ad çap_mm boy_mm gecikmeler yakıt_kg yüklü_kg üretici); ardından
  kronolojik (zaman [s], itki [N]) çiftleri gelir. Eğrinin (0 s, 0 N)
  noktası biçim gereği ÖRTÜKTÜR ve son noktanın ~0 N olması beklenir.
- RockSim .rse: XML; ``<engine>`` öznitelikleri (code, mfg, dia [mm],
  len [mm], initWt [g], propWt [g], delays, Type, Itot [N·s], avgThrust,
  peakThrust, burn-time, Isp) ve ``<eng-data t f m cg>`` noktaları
  (m gram, cg mm).

Normalize çıktı şeması (her motor için):
    {"time": [s], "thrust": [N],
     "meta": {"name","mfg","diameter_mm","length_mm","prop_mass_kg",
              "loaded_mass_kg","delays","type","source_format",
              "declared" (yalnız .rse, dosyanın beyan ettiği özet)},
     "computed": {"total_impulse_ns","peak_thrust_n","avg_thrust_n",
                  "burn_time_s"},
     "mass_curve": ops. [{"t","mass_g"}], "cg_curve": ops. [{"t","cg_mm"}],
     "warnings": [str]}

Hata sözleşmesi: bozuk dosya sınıfları (boş eğri, sıfır impuls, negatif
itki, negatif zaman, kronolojik olmayan zaman, tek noktalı eğri, bozuk
başlık/XML) ``ValueError`` FIRLATMAZ;
``{"error": "<açıklama>", "error_code": "<makine-okur ad>"}`` döner — API
katmanı bunu 400'e çevirir ve ``error_code``'u aynen iletir. Uydurma-veri
yasağı: dosyada olmayan alan None kalır, biçim gereği eklenen örtük (0,0)
noktası dahi ``warnings`` içinde bildirilir.

Makulluk kapısı: RASP/RockSim başlığı birimini dosyada BEYAN ETMEZ (çap ve
boy milimetredir). Bant dışı çap/boy ve fizik-dışı tepe itki sessizce
kabul edilmez; değer DEĞİŞTİRİLMEDEN ``warnings`` içinde adıyla bildirilir
(uydurma düzeltme yok — mm/m dönüşümü kendiliğinden YAPILMAZ).

Kullanıcıya görünen tüm metinler İngilizce'dir (UI kuralı).
"""

import math
import re
import xml.etree.ElementTree as ET

import numpy as np
# ÖH D26 / OH-D25-14: ``np.trapz`` NumPy 2.0'da ad alanından
# KALDIRILDI (np.trapezoid); ad TEK YERDE çözülür.
from hrma.utils.numeric_compat import trapezoid as _trapezoid

# Yanma süresi eşiği ve pencere hesabı CSV doğrulamasıyla AYNI kaynaktan
# gelir (magic number kuralı): tepe itkinin %5'i — NFPA 1125 konvansiyonu.
from hrma.validation.user_data_validation import (
    BURN_TIME_THRESHOLD_FRACTION, _burn_window)
# I_sp = I_tot / (m_yakıt · g_0) çapraz denetimi için standart yerçekimi —
# TEK KAYNAK (hrma/constants.py; BIPM 9,80665 m/s²), burada kopyalanmaz.
from hrma.constants import G_0

# Dosyanın beyan ettiği özet (Itot, peakThrust) ile eğriden hesaplanan
# değer arasındaki tutarsızlık uyarı eşiği [%] — raporlama yargısı,
# fiziksel sabit değil.
DECLARED_MISMATCH_WARN_PCT = 5.0

# XML güvenliği: DTD/entity bildirimi içeren belgeler işlenmeden reddedilir
# (billion-laughs / harici entity saldırılarına karşı).
_XML_FORBIDDEN = re.compile(r'<!\s*(?:DOCTYPE|ENTITY)', re.IGNORECASE)

# RASP gecikme alanı deseni: "0", "6-10-14", "P" (tapalı), "5,7" vb.
_DELAYS_PATTERN = re.compile(r'^[0-9pP][0-9pPsS,\-]*$')

# Bir itki eğrisi tanımı için dosyanın KENDİSİNİN vermesi gereken en az
# nokta sayısı. Biçim gereği eklenen örtük (0 s, 0 N) ateşleme noktası bu
# sayıya DAHİL DEĞİLDİR: tek satırlık bir dosya, örtük nokta eklendiğinde
# iki noktaya ulaşıp "kullanılabilir motor" gibi görünür (bir yükseliş
# rampası; yanma sonu yok). ÖLÇÜLDÜ (P16B4-28): "0.1 100.0" tek satırı
# 200 + total_impulse 5,0 N·s üretiyordu.
MIN_CURVE_POINTS_FROM_FILE = 2

# --- Makulluk bantları (UYARI eşikleri; değeri değiştirmez, RET etmez) ---
# RASP .eng ve RockSim .rse başlıkları çapı ve boyu MİLİMETRE yazar ama
# birimi dosyada beyan etmez; metre yazılmış bir değer sessizce mikron
# ölçeğine düşer (ölçülen: 0,054 -> "54 mikron çaplı motor" kabul edildi).
# Bantlar uçan donanımın bilinen sınırlarından alınmıştır, keyfi değildir:
#   alt sınır — seri üretim en küçük motor sınıfı 1/4A "T": 6 mm çap,
#               ~45 mm boy (NAR/Estes katalog sınırı),
#   üst sınır — amatör/deneysel gövde çaplarının üstünde bırakıldı.
MOTOR_DIAMETER_PLAUSIBLE_MM = (6.0, 1000.0)
MOTOR_LENGTH_PLAUSIBLE_MM = (20.0, 10000.0)

# Tepe itki üst makulluk sınırı [N]: uçmuş en güçlü TEK roket motoru
# ~7,9 MN (RD-170, deniz seviyesi), en güçlü ilk kademe demeti ~40 MN.
# 1e8 N (100 MN) üstü hiçbir donanıma karşılık gelmez; eşik birim/ölçek
# hatasını yakalamak içindir (ölçülen: 1e12 N uyarısız kabul ediliyordu).
MOTOR_PEAK_THRUST_PLAUSIBLE_N = 1.0e8

# mm <-> m karışıklığı işareti: sayının 1000 katı bandın içine düşüyorsa
# değer büyük olasılıkla METRE yazılmıştır (dönüşüm YAPILMAZ, bildirilir).
_MM_PER_METRE = 1000.0

# --- Zarf-ortalama yoğunluk bandı [kg/m³] (P9B5-19) ---
# RASP .eng ve RockSim .rse başlıkları KÜTLEYİ de birimsiz yazar: .eng
# alanları kilogram, .rse ``initWt``/``propWt`` gramdır ve dosya bunu beyan
# etmez. ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` bölümü P9B5-19):
#
#     "M1 18 70 0 3.7 4.2 HRMA"  -> 18 mm x 70 mm gövdeye 3,7 kg yakıt
#         zarf hacmi 1,7813e-05 m³ -> ima edilen yoğunluk 235 785 kg/m³
#     "M1 54 410 0 700 1200 HRMA" (gram yazılmış kilogram alanı)
#         -> ima edilen yoğunluk 1 277 968 kg/m³
#     "M1 54 410 0 0.700 1.200 HRMA" (doğru)
#         -> ima edilen yoğunluk 1 278 kg/m³
#
# Üçü de UYARISIZ kabul ediliyordu. Çap ve boy için zaten kurulu olan
# makulluk kapısının kütle eksenindeki eşliği budur; band donanımın kendi
# sınırlarından gelir, keyfi değildir:
#   üst sınır — bir motorun zarf-ortalama yoğunluğu EN YOĞUN bileşeninden
#               büyük olamaz. Depodaki en yoğun malzeme kaydı tungstendir
#               (``materials_db['tungsten']['density'] = 19300 kg/m³``, lüle
#               göbeği/balast); eşik onun ÜSTÜNE, yuvarlak bir SINIR olarak
#               konur (malzeme sayısının ikinci kopyası DEĞİLDİR),
#   alt sınır — deniz seviyesinde hava 1,225 kg/m³'tür (ICAO 1993); bir
#               motor yerini aldığı havadan hafif olamaz. Eşik onun ALTINA,
#               yuvarlak bir sınır olarak konur.
# Değer DEĞİŞTİRİLMEZ, dönüşüm YAPILMAZ: yalnız adıyla bildirilir.
MOTOR_ENVELOPE_DENSITY_PLAUSIBLE_KG_M3 = (1.0, 20000.0)


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------
def error_result(code, message):
    """İçe aktarma ayrıştırıcılarının ORTAK hata sözleşmesi.

    ``{"error": <insan metni>, "error_code": <makine-okur ad>}``. Kod,
    bekçilerin ve uçların metne bağlanmadan hata SINIFINI ayırt etmesi
    içindir; ``ork_import`` da bu yardımcıyı kullanır (tek tanım).
    """
    return {'error': message, 'error_code': code}


def _to_float(value):
    """Metni float'a çevir; başarısızsa None. TR ondalık virgülü toleransı
    (``0,5`` → 0.5; yalnız noktasız metinde) — CSV ayrıştırıcıyla aynı
    esneklik (hrma/validation/user_data_validation.py)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if ',' in s and '.' not in s:
        s = s.replace(',', '.')
    try:
        v = float(s)
    except ValueError:
        return None
    return v if np.isfinite(v) else None


def _empty_meta(source_format):
    """Normalize meta iskeleti — dosyada olmayan alan None KALIR."""
    return {
        'name': None, 'mfg': None, 'diameter_mm': None, 'length_mm': None,
        'prop_mass_kg': None, 'loaded_mass_kg': None, 'delays': None,
        'type': None, 'source_format': source_format,
    }


def _dimension_plausibility_warning(value_mm, label, band):
    """Bant dışı başlık ölçüsü için uyarı metni; bant içindeyse None.

    Değer DEĞİŞTİRİLMEZ. Sayının 1000 katı bandın içine düşüyorsa metrik
    birim çelişkisi (metre yazılmış milimetre alanı) adıyla bildirilir.
    """
    if value_mm is None:
        return None
    low, high = band
    if low <= value_mm <= high:
        return None
    span = f'{low:g}-{high:g} mm'
    if value_mm > 0 and low <= value_mm * _MM_PER_METRE <= high:
        return (f'Header {label} is {value_mm:g} mm, outside the plausible '
                f'range ({span}); {value_mm * _MM_PER_METRE:g} mm would be '
                'plausible, so the file may state the value in METRES. '
                'RASP/RSE headers use millimetres; the value was imported '
                'unchanged.')
    return (f'Header {label} is {value_mm:g} mm, outside the plausible range '
            f'for a rocket motor ({span}); the value was imported unchanged '
            '- check the file.')


def _envelope_density_warning(meta):
    """Başlık kütlesi/geometrisi ima edilen yoğunluk bandında mı? (P9B5-19)

    Silindirik zarf hacmi V = pi/4 · d² · L üzerinden YÜKLÜ kütlenin ima
    ettiği ortalama yoğunluk hesaplanır. Band dışıysa değer DEĞİŞTİRİLMEDEN
    bildirilir; kütle birimi (kg <-> g) kendiliğinden ÇEVRİLMEZ.

    Ölçü ya da kütle eksikse denetim yapılmaz (uydurma tamamlama yok) —
    None döner.
    """
    d_mm = meta.get('diameter_mm')
    l_mm = meta.get('length_mm')
    m_kg = meta.get('loaded_mass_kg')
    if not d_mm or not l_mm or not m_kg or d_mm <= 0 or l_mm <= 0 or m_kg <= 0:
        return None
    volume_m3 = math.pi / 4.0 * (d_mm / 1000.0) ** 2 * (l_mm / 1000.0)
    if volume_m3 <= 0:
        return None
    rho = m_kg / volume_m3
    low, high = MOTOR_ENVELOPE_DENSITY_PLAUSIBLE_KG_M3
    if low <= rho <= high:
        return None
    base = (f'Header loaded mass ({m_kg:g} kg) over the envelope volume of a '
            f'{d_mm:g} x {l_mm:g} mm motor implies a mean density of '
            f'{rho:.4g} kg/m3, outside the physically plausible range '
            f'({low:g}-{high:g} kg/m3; tungsten, the densest rocket-hardware '
            'metal, is 19300 kg/m3 and sea-level air is 1.225 kg/m3).')
    # Birim karışıklığı işareti: 1/1000 ya da 1000 katı banda düşüyorsa
    # kütle alanı büyük olasılıkla gram/kilogram karışmıştır.
    if low <= rho / 1000.0 <= high:
        return (base + ' Dividing the mass by 1000 would be plausible, so '
                'the file may state the RASP mass fields in GRAMS; RASP .eng '
                'headers use KILOGRAMS. The value was imported unchanged.')
    if low <= rho * 1000.0 <= high:
        return (base + ' Multiplying the mass by 1000 would be plausible, so '
                'the file may state the RASP mass fields in TONNES or the '
                'geometry in the wrong unit. The value was imported '
                'unchanged.')
    return base + ' The value was imported unchanged - check the file.'


def _plausibility_warnings(meta, peak_thrust_n):
    """Başlık ölçüsü, kütlesi ve tepe itki için makulluk uyarıları (liste)."""
    messages = []
    for key, label, band in (
            ('diameter_mm', 'diameter', MOTOR_DIAMETER_PLAUSIBLE_MM),
            ('length_mm', 'length', MOTOR_LENGTH_PLAUSIBLE_MM)):
        message = _dimension_plausibility_warning(meta.get(key), label, band)
        if message is not None:
            messages.append(message)
    if peak_thrust_n is not None and \
            peak_thrust_n > MOTOR_PEAK_THRUST_PLAUSIBLE_N:
        messages.append(
            f'Peak thrust computed from the curve is {peak_thrust_n:.3g} N, '
            f'above the plausible limit ({MOTOR_PEAK_THRUST_PLAUSIBLE_N:.3g} '
            'N; the most powerful rocket engine ever flown produces about '
            '7.9e+06 N). Check the thrust column units; the value was '
            'imported unchanged.')
    envelope = _envelope_density_warning(meta)
    if envelope is not None:
        messages.append(envelope)
    return messages


def _finalize_motor(times, thrusts, meta, warnings,
                    mass_curve=None, cg_curve=None):
    """Ham (t, F) listesini doğrula, özet metrikleri hesapla, motoru paketle.

    Bozuk eğri sınıflarında ``{"error": ..., "error_code": ...}`` döner
    (istisna atmaz).
    """
    t = np.asarray(times, dtype=float)
    f = np.asarray(thrusts, dtype=float)
    if t.size == 0:
        return error_result('no_data_points',
                            'The file contains no thrust data points.')
    if np.any(f < 0):
        return error_result(
            'negative_thrust',
            'Negative thrust values found in the motor file; a published '
            'thrust curve must be non-negative.')
    # Negatif zaman: yayımlanmış bir itki eğrisi t < 0'da başlayamaz.
    # ÖLÇÜLDÜ (P16B4-13): t=-0,1 s ile aynı eğri 190 yerine 205 N·s
    # (%7,9 fazla) impuls üretiyor ve örtük ateşleme noktası kuralını da
    # devre dışı bırakıyordu. Kardeş ihlaller (negatif itki, kronolojik
    # olmayan zaman) zaten reddediliyordu; kapı bu eksene de kuruldu.
    if np.any(t < 0):
        return error_result(
            'negative_time',
            f'Negative time value ({float(np.min(t)):g} s) found in the '
            'motor file; a thrust curve must start at or after t = 0 s.')
    if np.any(np.diff(t) < 0):
        return error_result(
            'non_chronological_time',
            'Time values are not chronological; RASP/RSE thrust curves must '
            'be in increasing time order.')
    # Eşit ardışık zaman damgaları: ilki tutulur (uyarıyla)
    keep = np.concatenate(([True], np.diff(t) > 0))
    if not np.all(keep):
        t, f = t[keep], f[keep]
        warnings.append('Duplicate time stamps removed (first occurrence '
                        'kept).')
    if t.size < 2:
        return error_result(
            'too_few_points',
            'At least 2 distinct (time, thrust) points are required to '
            'define a thrust curve.')
    total_impulse = float(_trapezoid(f, t))
    peak = float(np.max(f))
    if total_impulse <= 0.0 or peak <= 0.0:
        return error_result(
            'zero_impulse',
            'Total impulse of the curve is zero; the file does not describe '
            'a usable motor burn.')
    if f[-1] > BURN_TIME_THRESHOLD_FRACTION * peak:
        warnings.append(
            f'Final thrust point is {float(f[-1]):.1f} N; a RASP/RSE curve '
            'is expected to end near 0 N (burnout).')
    _, _, burn_time = _burn_window(t, f, BURN_TIME_THRESHOLD_FRACTION)
    if burn_time <= 0.0:
        return error_result(
            'zero_burn_time',
            'Burn time evaluated to zero; the thrust curve may be a single '
            'spike or corrupted.')
    warnings.extend(_plausibility_warnings(meta, peak))
    computed = {
        'total_impulse_ns': total_impulse,
        'peak_thrust_n': peak,
        'avg_thrust_n': total_impulse / burn_time,
        'burn_time_s': float(burn_time),
    }
    # ------------------------------------------------------------------
    # Dosyanın beyan ettiği özetle çapraz kontrol (yalnız .rse doldurur)
    #
    # ÖH D23 / defter P9B5-18 — BEŞ BEYANDAN ÜÇÜ DENETLENMİYORDU.
    #
    # ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` bölümü P9B5-18; ``Itot=1000``,
    # ``avgThrust=500``, ``peakThrust=700``, ``burn-time=2.0``, ``Isp=145.6``
    # beyan eden bir .rse):
    #
    #     beyan edilen alan sayısı .......... 5
    #     çapraz denetlenen alan sayısı ..... 2  (yalnız Itot ve peakThrust)
    #     avgThrust  beyan 500,0  / eğriden 461,5  (-%7,7)  -> UYARI YOK
    #     burn-time  beyan   2,0  / eğriden   1,95 (-%2,5)  -> UYARI YOK
    #     Isp        beyan 145,6  / hiç hesaplanmıyordu     -> UYARI YOK
    #
    # ``_parse_rse_engine`` beşini de ayrıştırıp ``meta['declared']`` içine
    # koyuyordu; ikisi okunuyor, üçü ölü veri olarak duruyordu. Beyanla eğri
    # arasındaki çelişki tam olarak "dosyaya güvenilir mi" sorusunun kanıtı
    # olduğu için üçü de aynı eşiğe bağlandı.
    #
    # I_sp'nin eğriden karşılığı tanım gereği I_tot / (m_yakıt · g_0)'dır;
    # ``G_0`` ``hrma.constants``ten gelir (tek kaynak, 9,80665 m/s²).
    # Yakıt kütlesi beyan edilmemişse I_sp KARŞILAŞTIRILMAZ — uydurma bir
    # kütleyle sahte bir I_sp üretilmez (fail-closed).
    # ------------------------------------------------------------------
    declared = meta.get('declared') or {}
    if declared.get('isp_s') and meta.get('prop_mass_kg'):
        _prop = float(meta['prop_mass_kg'])
        if _prop > 0:
            computed['isp_s'] = total_impulse / (_prop * G_0)
    for dec_key, comp_key, label, birim in (
            ('total_impulse_ns', 'total_impulse_ns', 'total impulse', 'N.s'),
            ('peak_thrust_n', 'peak_thrust_n', 'peak thrust', 'N'),
            ('avg_thrust_n', 'avg_thrust_n', 'average thrust', 'N'),
            ('burn_time_s', 'burn_time_s', 'burn time', 's'),
            ('isp_s', 'isp_s', 'specific impulse', 's')):
        dec = declared.get(dec_key)
        comp = computed.get(comp_key)
        if dec and dec > 0 and comp is not None:
            diff_pct = abs(comp - dec) / dec * 100.0
            if diff_pct > DECLARED_MISMATCH_WARN_PCT:
                warnings.append(
                    f'Declared {label} ({dec:.1f} {birim}) differs from the '
                    f'value computed from the curve ({comp:.1f} {birim}) '
                    f'by {diff_pct:.1f}%.')
    # Beyan edilmiş ama karşılaştırılamamış alanlar SESSİZ KALMAZ: hangi
    # alanın neden denetlenemediği adıyla söylenir (P9B5-18).
    if declared.get('isp_s') and 'isp_s' not in computed:
        warnings.append(
            'Declared specific impulse (' f"{declared['isp_s']:.1f} s) could "
            'not be cross-checked: the file declares no usable propellant '
            'mass (propWt), and no substitute mass is assumed.')
    motor = {
        'time': t.tolist(),
        'thrust': f.tolist(),
        'meta': meta,
        'computed': computed,
        'warnings': warnings,
    }
    if mass_curve:
        motor['mass_curve'] = mass_curve
    if cg_curve:
        motor['cg_curve'] = cg_curve
    return motor


# ---------------------------------------------------------------------------
# RASP .eng
# ---------------------------------------------------------------------------
def _parse_eng_header(fields):
    """7 alanlı RASP başlığını dener; uymuyorsa None.

    Alanlar: ad çap_mm boy_mm gecikmeler yakıt_kg yüklü_kg üretici.
    """
    if len(fields) != 7:
        return None
    name, dia_s, len_s, delays, prop_s, loaded_s, mfg = fields
    dia = _to_float(dia_s)
    length = _to_float(len_s)
    prop = _to_float(prop_s)
    loaded = _to_float(loaded_s)
    if None in (dia, length, prop, loaded):
        return None
    if dia <= 0 or length <= 0 or prop < 0 or loaded < 0:
        return None
    if not _DELAYS_PATTERN.match(delays):
        return None
    header_warnings = []
    if prop > loaded > 0:
        header_warnings.append(
            f'Header propellant mass ({prop} kg) exceeds loaded mass '
            f'({loaded} kg); check the file.')
    header = {
        'name': name, 'mfg': mfg, 'diameter_mm': dia, 'length_mm': length,
        'delays': delays, 'prop_mass_kg': prop, 'loaded_mass_kg': loaded,
    }
    return header, header_warnings


def parse_eng(text):
    """RASP .eng metnini normalize motor şemasına ayrıştır.

    Kurallar: ``;`` satırları yorum; ilk yorum-olmayan satır 7 alanlı
    başlık; ardından (t, F) çiftleri (satırda birden çok çift olabilir).
    (0, 0) örtük başlangıç noktası eksikse eklenir ve ``warnings`` ile
    bildirilir. Dosyada birden çok motor bloğu varsa yalnız İLKİ
    ayrıştırılır (uyarıyla).

    Returns
    -------
    dict
        Normalize motor şeması ya da ``{"error": str}``.
    """
    if not isinstance(text, str):
        return error_result('not_text',
                            'RASP .eng content must be plain text.')
    text = text.lstrip('﻿')
    warnings = []
    header = None
    points = []
    has_extra_motor = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(';'):
            continue
        fields = line.split()
        if header is None:
            parsed = _parse_eng_header(fields)
            if parsed is None:
                return error_result('invalid_header', (
                    f"Line {lineno} is not a valid RASP header. Expected 7 "
                    "fields: name diameter_mm length_mm delays "
                    f"prop_mass_kg loaded_mass_kg manufacturer; got "
                    f"'{line[:60]}'."))
            header, header_warnings = parsed
            warnings.extend(header_warnings)
            continue
        numbers = [_to_float(fld) for fld in fields]
        if numbers and all(v is not None for v in numbers) \
                and len(numbers) % 2 == 0:
            for i in range(0, len(numbers), 2):
                points.append((numbers[i], numbers[i + 1]))
        elif points and _parse_eng_header(fields) is not None:
            # İkinci motor bloğu başladı — yalnız ilk motor ayrıştırılır
            has_extra_motor = True
            break
        else:
            warnings.append(
                f"Line {lineno} skipped (not numeric time/thrust data): "
                f"'{line[:40]}'.")
    if header is None:
        return error_result(
            'no_header',
            'No RASP header line found. The first non-comment line must '
            'contain 7 fields.')
    if not points:
        return error_result('no_data_points',
                            'The file contains no thrust data points.')
    # Tek noktalı eğri: örtük (0,0) ateşleme noktası eklenince nokta sayısı
    # ikiye çıkıp eğri "kullanılabilir motor" gibi görünüyordu
    # (P16B4-28: "0.1 100.0" tek satırı -> 200, total_impulse 5,0 N·s).
    # Örtük nokta biçim kuralıdır, VERİ DEĞİLDİR: yanma sonunu dosyanın
    # kendisi göstermek zorunda.
    if len(points) < MIN_CURVE_POINTS_FROM_FILE:
        return error_result(
            'single_point_curve',
            f'The file defines only {len(points)} (time, thrust) point; at '
            f'least {MIN_CURVE_POINTS_FROM_FILE} points must come from the '
            'file itself. The implicit RASP ignition point (t=0 s, F=0 N) '
            'is a format convention, not measured data, and does not make a '
            'single-point file a usable motor curve.')
    if has_extra_motor:
        warnings.append('File contains more than one motor definition; '
                        'only the first motor was parsed.')
    # Örtük ateşleme noktası (RASP biçim tanımı) — şeffaf biçimde bildirilir
    if points[0][0] > 0.0:
        points.insert(0, (0.0, 0.0))
        warnings.append('Implicit RASP ignition point (t=0 s, F=0 N) '
                        'prepended per format definition.')
    elif points[0][0] == 0.0 and points[0][1] != 0.0:
        warnings.append(
            f'Thrust at t=0 is {points[0][1]:.1f} N; RASP curves normally '
            'start from 0 N.')
    meta = _empty_meta('rasp_eng')
    meta.update(header)
    return _finalize_motor([p[0] for p in points], [p[1] for p in points],
                           meta, warnings)


# ---------------------------------------------------------------------------
# RockSim .rse
# ---------------------------------------------------------------------------
def _parse_rse_engine(engine):
    """Tek ``<engine>`` elemanını normalize motor şemasına çevir."""
    warnings = []
    meta = _empty_meta('rse')
    meta['name'] = engine.get('code')
    meta['mfg'] = engine.get('mfg')
    meta['diameter_mm'] = _to_float(engine.get('dia'))
    meta['length_mm'] = _to_float(engine.get('len'))
    init_wt_g = _to_float(engine.get('initWt'))
    prop_wt_g = _to_float(engine.get('propWt'))
    meta['loaded_mass_kg'] = (init_wt_g / 1000.0
                              if init_wt_g is not None else None)
    meta['prop_mass_kg'] = (prop_wt_g / 1000.0
                            if prop_wt_g is not None else None)
    meta['delays'] = engine.get('delays')
    meta['type'] = engine.get('Type')
    declared = {}
    for attr, key in (('Itot', 'total_impulse_ns'),
                      ('avgThrust', 'avg_thrust_n'),
                      ('peakThrust', 'peak_thrust_n'),
                      ('burn-time', 'burn_time_s'),
                      ('Isp', 'isp_s')):
        value = _to_float(engine.get(attr))
        if value is not None:
            declared[key] = value
    if declared:
        meta['declared'] = declared

    points = engine.findall('.//eng-data')
    times, thrusts, mass_curve, cg_curve = [], [], [], []
    for point in points:
        t = _to_float(point.get('t'))
        f = _to_float(point.get('f'))
        if t is None or f is None:
            warnings.append('An <eng-data> point without numeric t/f '
                            'attributes was skipped.')
            continue
        times.append(t)
        thrusts.append(f)
        m = _to_float(point.get('m'))
        if m is not None:
            mass_curve.append({'t': t, 'mass_g': m})
        cg = _to_float(point.get('cg'))
        if cg is not None:
            cg_curve.append({'t': t, 'cg_mm': cg})
    return _finalize_motor(times, thrusts, meta, warnings,
                           mass_curve=mass_curve or None,
                           cg_curve=cg_curve or None)


def parse_rse(text):
    """RockSim .rse metnini ayrıştır; TÜM motorları döndür.

    Returns
    -------
    dict
        ``{"motors": [normalize motor, ...], "default_index": 0,
        "warnings": [dosya düzeyi uyarılar]}`` ya da ``{"error": str}``.
        Birden çok ``<engine>`` varsa hepsi listede, ilki varsayılandır;
        bozuk motorlar dosya düzeyi uyarıyla atlanır.
    """
    if isinstance(text, (bytes, bytearray)):
        try:
            text = bytes(text).decode('utf-8')
        except UnicodeDecodeError:
            return error_result('not_utf8',
                                'The .rse file is not valid UTF-8 text.')
    if not isinstance(text, str):
        return error_result('not_text', 'RSE content must be XML text.')
    text = text.lstrip('﻿')
    if _XML_FORBIDDEN.search(text):
        return error_result(
            'xml_security',
            'XML documents containing DTD or ENTITY declarations are '
            'rejected for security reasons.')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return error_result('invalid_xml',
                            f'Invalid XML in .rse file: {exc}')
    if root.tag == 'engine':
        engines = [root]
    else:
        engines = root.findall('.//engine')
    if not engines:
        return error_result(
            'no_engine_element',
            'No <engine> element found; a RockSim .rse file must contain at '
            'least one engine definition.')
    motors, file_warnings = [], []
    for index, engine in enumerate(engines):
        motor = _parse_rse_engine(engine)
        if 'error' in motor:
            label = engine.get('code') or f'#{index + 1}'
            file_warnings.append(
                f"Engine '{label}' skipped: {motor['error']}")
            continue
        motors.append(motor)
    if not motors:
        detail = ' '.join(file_warnings) if file_warnings else ''
        return error_result(
            'no_usable_engine',
            ('No usable engine definitions in the .rse file. '
             + detail).strip())
    if len(engines) > 1:
        file_warnings.append(
            f'File contains {len(engines)} engine definitions; the first '
            'usable one is selected by default.')
    return {'motors': motors, 'default_index': 0, 'warnings': file_warnings}
