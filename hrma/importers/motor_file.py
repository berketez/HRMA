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
itki, kronolojik olmayan zaman, bozuk başlık/XML) ``ValueError``
FIRLATMAZ; ``{"error": "<açıklama>"}`` döner — API katmanı bunu 400'e
çevirir. Uydurma-veri-yasağı: dosyada olmayan alan None kalır, biçim
gereği eklenen örtük (0,0) noktası dahi ``warnings`` içinde bildirilir.

Kullanıcıya görünen tüm metinler İngilizce'dir (UI kuralı).
"""

import re
import xml.etree.ElementTree as ET

import numpy as np

# Yanma süresi eşiği ve pencere hesabı CSV doğrulamasıyla AYNI kaynaktan
# gelir (magic number kuralı): tepe itkinin %5'i — NFPA 1125 konvansiyonu.
from hrma.validation.user_data_validation import (
    BURN_TIME_THRESHOLD_FRACTION, _burn_window)

# Dosyanın beyan ettiği özet (Itot, peakThrust) ile eğriden hesaplanan
# değer arasındaki tutarsızlık uyarı eşiği [%] — raporlama yargısı,
# fiziksel sabit değil.
DECLARED_MISMATCH_WARN_PCT = 5.0

# XML güvenliği: DTD/entity bildirimi içeren belgeler işlenmeden reddedilir
# (billion-laughs / harici entity saldırılarına karşı).
_XML_FORBIDDEN = re.compile(r'<!\s*(?:DOCTYPE|ENTITY)', re.IGNORECASE)

# RASP gecikme alanı deseni: "0", "6-10-14", "P" (tapalı), "5,7" vb.
_DELAYS_PATTERN = re.compile(r'^[0-9pP][0-9pPsS,\-]*$')


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------
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


def _finalize_motor(times, thrusts, meta, warnings,
                    mass_curve=None, cg_curve=None):
    """Ham (t, F) listesini doğrula, özet metrikleri hesapla, motoru paketle.

    Bozuk eğri sınıflarında ``{"error": ...}`` döner (istisna atmaz).
    """
    t = np.asarray(times, dtype=float)
    f = np.asarray(thrusts, dtype=float)
    if t.size == 0:
        return {'error': 'The file contains no thrust data points.'}
    if np.any(f < 0):
        return {'error': ('Negative thrust values found in the motor file; '
                          'a published thrust curve must be non-negative.')}
    if np.any(np.diff(t) < 0):
        return {'error': ('Time values are not chronological; RASP/RSE '
                          'thrust curves must be in increasing time order.')}
    # Eşit ardışık zaman damgaları: ilki tutulur (uyarıyla)
    keep = np.concatenate(([True], np.diff(t) > 0))
    if not np.all(keep):
        t, f = t[keep], f[keep]
        warnings.append('Duplicate time stamps removed (first occurrence '
                        'kept).')
    if t.size < 2:
        return {'error': ('At least 2 distinct (time, thrust) points are '
                          'required to define a thrust curve.')}
    total_impulse = float(np.trapz(f, t))
    peak = float(np.max(f))
    if total_impulse <= 0.0 or peak <= 0.0:
        return {'error': ('Total impulse of the curve is zero; the file '
                          'does not describe a usable motor burn.')}
    if f[-1] > BURN_TIME_THRESHOLD_FRACTION * peak:
        warnings.append(
            f'Final thrust point is {float(f[-1]):.1f} N; a RASP/RSE curve '
            'is expected to end near 0 N (burnout).')
    _, _, burn_time = _burn_window(t, f, BURN_TIME_THRESHOLD_FRACTION)
    if burn_time <= 0.0:
        return {'error': ('Burn time evaluated to zero; the thrust curve '
                          'may be a single spike or corrupted.')}
    computed = {
        'total_impulse_ns': total_impulse,
        'peak_thrust_n': peak,
        'avg_thrust_n': total_impulse / burn_time,
        'burn_time_s': float(burn_time),
    }
    # Dosyanın beyan ettiği özetle çapraz kontrol (yalnız .rse doldurur)
    declared = meta.get('declared') or {}
    for dec_key, comp_key, label in (
            ('total_impulse_ns', 'total_impulse_ns', 'total impulse'),
            ('peak_thrust_n', 'peak_thrust_n', 'peak thrust')):
        dec = declared.get(dec_key)
        if dec and dec > 0:
            diff_pct = abs(computed[comp_key] - dec) / dec * 100.0
            if diff_pct > DECLARED_MISMATCH_WARN_PCT:
                warnings.append(
                    f'Declared {label} ({dec:.1f}) differs from the value '
                    f'computed from the curve ({computed[comp_key]:.1f}) '
                    f'by {diff_pct:.1f}%.')
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
        return {'error': 'RASP .eng content must be plain text.'}
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
                return {'error': (
                    f"Line {lineno} is not a valid RASP header. Expected 7 "
                    "fields: name diameter_mm length_mm delays "
                    f"prop_mass_kg loaded_mass_kg manufacturer; got "
                    f"'{line[:60]}'.")}
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
        return {'error': ('No RASP header line found. The first '
                          'non-comment line must contain 7 fields.')}
    if not points:
        return {'error': 'The file contains no thrust data points.'}
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
            return {'error': 'The .rse file is not valid UTF-8 text.'}
    if not isinstance(text, str):
        return {'error': 'RSE content must be XML text.'}
    text = text.lstrip('﻿')
    if _XML_FORBIDDEN.search(text):
        return {'error': ('XML documents containing DTD or ENTITY '
                          'declarations are rejected for security '
                          'reasons.')}
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return {'error': f'Invalid XML in .rse file: {exc}'}
    if root.tag == 'engine':
        engines = [root]
    else:
        engines = root.findall('.//engine')
    if not engines:
        return {'error': ('No <engine> element found; a RockSim .rse file '
                          'must contain at least one engine definition.')}
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
        return {'error': ('No usable engine definitions in the .rse file. '
                          + detail).strip()}
    if len(engines) > 1:
        file_warnings.append(
            f'File contains {len(engines)} engine definitions; the first '
            'usable one is selected by default.')
    return {'motors': motors, 'default_index': 0, 'warnings': file_warnings}
