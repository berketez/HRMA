"""
OpenRocket Integration Module
Export motor data to OpenRocket .eng format and create flight simulation files
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from hrma.constants import G_0, M_AIR, R_STAR_ICAO, isa_pressure, isa_temperature

# ---------------------------------------------------------------------------
# .eng (RASP) üretim sabitleri — TEK tanım noktası (CLAUDE.md kural 11).
# ---------------------------------------------------------------------------
# RASP formatı eğrinin sıfır itkiyle bitmesini ister. Bu son nokta bir FORMAT
# sonlandırıcısıdır, modellenmiş bir sönme rampası DEĞİLDİR; toplam impulsu
# etkilemesin diye çok kısa tutulur.
ENG_ZERO_TERMINATOR_DT_S = 0.01
# OpenRocket için yeterli çözünürlük (gerçek eğri bundan uzunsa seyreltilir).
ENG_MAX_SAMPLES = 100

# İtki eğrisinin hangi kaynaktan geldiği .eng yorum satırına yazılır; kullanıcı
# dosyanın kendisine bakarak gerçek çözümü mü yoksa sabit itki varsayımını mı
# indirdiğini görebilir (2026-07-19 uydurma denetimi, kritik bulgu).
THRUST_SOURCE_LABELS = {
    'transient': 'transient ballistics solver (time-resolved)',
    # v2.6.26: bu etiket "solid grain burn-back solver" diye SABİTTİ, çünkü
    # `thrust_curve` yalnız katı motorda vardı. Aynı sürümde hibrit motor da
    # zaman-adımlı eğri üretmeye başlayınca hibrit dosyalar KATI çözücüsüyle
    # üretilmiş gibi etiketleniyordu. Motor eğrinin yanında kendi `basis`
    # açıklamasını taşıyorsa o kullanılır (aşağıdaki _thrust_curve_label);
    # buradaki değer yalnız beyansız eski sonuçlar için yedektir.
    'thrust_curve': 'grain burn-back solver (time-resolved)',
    'constant': 'constant-thrust approximation; no transient solution available',
    # Faz 4B: ne eğri ne de (itki, yanma süresi) çifti var. Eskiden burada
    # 1000 N x 10 s uyduruluyordu; artık eğri yoktur ve dosya üretilmez.
    'unavailable': 'NO thrust data available - no curve can be written',
}


def _thrust_curve_label(curve):
    """Eğrinin kendi `basis` beyanını etikete çevirir; yoksa genel etiket.

    Çözücü hangi denklemi kullandığını `basis` alanında yazıyor; dosyayı açan
    kişi bunu görmelidir. Uydurma değil, motorun kendi beyanı taşınır.
    """
    genel = THRUST_SOURCE_LABELS['thrust_curve']
    if not isinstance(curve, dict):
        return genel
    basis = curve.get('basis')
    if not basis:
        return genel
    basis = ' '.join(str(basis).split())
    return f'{genel}; {basis}'

# Yüklü kütle (loaded mass) kaynağı etiketleri.
MASS_SOURCE_LABELS = {
    'structural': 'inert mass from structural analysis (chamber + nozzle + end caps)',
    'reported': 'inert mass reported by solver',
    'none': ('inert (case/structure) mass NOT available in this export; '
             'loaded mass = propellant mass only - enter case mass in OpenRocket'),
}

# ---------------------------------------------------------------------------
# .eng / .ork ÜRETİM KAPISI (Faz 4B, denetim bulgusu A12)
# ---------------------------------------------------------------------------
# Ölçüm (2 Ağustos 2026, HEAD a7ff1e7): BOŞ bir ``motor_data`` sözlüğüyle
# üretilen .eng dosyasının motor satırı şuydu —
#
#     M0-UZAYTEK-HRM-001 0.0 500.0 P 1.000 1.000 UZAYTEK
#
# yani ÇAPI SIFIR, boyu yer tutucu 500 mm, itici kütlesi imza varsayılanı
# 1,000 kg ve sınıf harfi 10000 N·s varsayılanından gelen "M" olan bir motor.
# OpenRocket bu dosyayı sorunsuz yükler; kullanıcı gerçek bir motor sanar.
#
# Kural (fail-closed): kritik alanlar GERÇEK sonuçtan çözülemiyorsa dosya
# ÜRETİLMEZ, açık hata döner. Yer tutucu bir motor yazmak hiç yazmamaktan
# tehlikelidir — çünkü çalıştırılabilir görünür.
#
# Aynı kapı .ork proje şablonuna da uygulanır: o dosya da bir motor tanımı
# taşır ve OpenRocket'ta doğrudan açılır.
#
# Not: "çözülemiyorsa" demek "üst seviyede o adla yoksa" demek DEĞİLDİR.
# Ölçüm, aynı sayının motor tipine göre farklı anahtarda yayımlandığını
# gösterdi (aşağıdaki resolve_* yardımcılarının docstring'lerinde sayılarla
# yazılı). Önce gerçek değer aranır, sonra kapı işletilir.
ENG_REQUIRED_FIELDS = ('case_diameter', 'chamber_length', 'propellant_mass',
                       'total_impulse', 'thrust_curve')


class OpenRocketExportDataError(ValueError):
    """OpenRocket çıktısı üretilemedi: kritik motor alanı yok ya da geçersiz.

    ``ValueError`` alt sınıfıdır; app.py'deki ``except Exception`` sarmalayıcıları
    davranış değiştirmeden mesajı kullanıcıya iletir (uçlar `status: 'error'` +
    `error` metni döner, sayfa bunu gösterir).
    """

    def __init__(self, missing_fields, reasons=None, what='.eng'):
        self.missing_fields = list(missing_fields)
        self.reasons = dict(reasons or {})
        detay = ' '.join(f'[{k}] {v}' for k, v in self.reasons.items())
        super().__init__(
            f'{what} file NOT generated - the motor analysis does not provide '
            f'these required fields: {", ".join(self.missing_fields)}. '
            f'{detay} No placeholder motor is written: a zero-diameter or '
            f'default-mass motor would load in OpenRocket and look real.')


# İtici kütlesinin hangi alandan çözüldüğü .eng yorum satırına yazılır.
PROPELLANT_MASS_SOURCE_LABELS = {
    'propellant_mass_total': 'propellant_mass_total reported by the solver',
    'design_summary': 'design_summary.masses.propellant_mass_kg',
    'propellant_mass': 'propellant_mass reported by the solver',
    'mdot_x_burn_time': ('total_mass_flow x burn_time (the liquid solver '
                         'reports mass flow, not propellant mass)'),
    'none': 'propellant mass NOT available',
}

# Ortalama itkinin kaynağı (sabit-itki yedeği ve toplam impuls için).
AVERAGE_THRUST_SOURCE_LABELS = {
    'thrust': 'thrust reported by the solver',
    'average_thrust': 'average_thrust reported by the solver',
    'curve_mean': 'impulse-weighted mean of the time-resolved thrust curve',
    'none': 'average thrust NOT available',
}

# Toplam impulsun kaynağı; .eng sınıf harfi (A..O) bundan türer.
TOTAL_IMPULSE_SOURCE_LABELS = {
    'total_impulse': 'total_impulse reported by the solver',
    'curve_integral': 'integral of the time-resolved thrust curve',
    'thrust_x_burn_time': 'average thrust x burn time',
    'none': 'total impulse NOT available',
}

# ---------------------------------------------------------------------------
# BİRİM SÖZLEŞMESİ (2026-07-19 Codex denetimi, bulgu 1)
# ---------------------------------------------------------------------------
# Üst seviye motor sonuçları motor tipine göre FARKLI birim kullanır:
#   katı   : throat_diameter = 47.93  -> MİLİMETRE, chamber_length üst seviyede yok
#   sıvı   : throat_diameter = 0.0278 -> METRE,     chamber_length = 97.96 -> MİLİMETRE
#   hibrit : throat_diameter = 0.0305 -> METRE,     chamber_length = 0.882 -> METRE
# Bu dosya eskiden hepsini METRE sanıp 1000 ile çarpıyordu; katı motorda
# .eng başlığına 47927 mm çap yazılıyordu.
#
# Tek doğruluk kaynağı: hrma/export/motor_geometry.py'nin ürettiği normalize
# `motor_geometry` bloğu (HER alanı SI). /calculate_solid ve /calculate_liquid
# yanıtlarında bu blok döner; hibrit sonucu zaten SI'dır. Blok yoksa değer
# BÜYÜKLÜĞÜNDEN çıkarılır ve hangi yolun kullanıldığı .eng yorum satırına ve
# export_motor_summary çıktısına yazılır — sessiz tahmin yok.
GEOMETRY_SOURCE_LABELS = {
    'motor_geometry': 'normalized motor_geometry block (SI, no unit inference)',
    'inferred': 'top-level results; unit inferred from magnitude (see notes)',
    'missing': 'geometry not supplied; exporter placeholders used',
}

# ---------------------------------------------------------------------------
# FIRLATMA KOŞULLARI (simulation_settings) — v2.6.26, ölü girdi denetimi P4.
# ---------------------------------------------------------------------------
# `wind_speed` bu blokta 0 m/s olarak SABİT yazılıyordu. Oysa hibrit sayfasında
# gerçek bir rüzgâr alanı var (advanced.html:1563), istekle gönderiliyor ve
# AYNI isteğin yörünge dalında kullanılıyor (app.py:1117). Kullanıcı 12 m/s
# girse bile dışa aktarım "rüzgârsız" diyordu; varsayılanın da 0 olması kusuru
# gizliyordu (girdiyi oynatınca yaprak kıpırdamadığı fark edilmiyordu).
#
# Kural: fırlatma koşulu ÇAĞIRANDAN gelir. Gelmediyse sayı UYDURULMAZ — alan
# None kalır ve nedeni `simulation_settings_source` içinde yazılı olur; dosyayı
# okuyan kişi hangi sayının kendi girdisi, hangisinin eksik olduğunu görür.
LAUNCH_SETTING_SOURCE_LABELS = {
    'request': 'from the calculation request (user input)',
    'not_supplied': ('NOT supplied by the caller - no value assumed; '
                     'set it in OpenRocket before simulating'),
    'invalid_input': ('supplied value rejected (non-finite or outside its '
                      'physical range) - no value assumed'),
    'exporter_default': ('exporter default; no input field feeds this setting '
                         '- check it in OpenRocket'),
}

# İstekten okunan fırlatma koşulları. Anahtar adları app.py'nin yörünge dalında
# kurduğu `launch_params` sözlüğüyle BİREBİR aynıdır (app.py:1114-1119) ki aynı
# sözlük iki dala birden verilebilsin; tek yanıtta iki farklı fırlatma koşulu
# dolaşmasın.
#
# Kabul bantları: değer bandın dışındaysa YAZILMAZ (uydurma yerine boşluk).
# Açı bandı hibrit sayfasındaki alanın kendi bandıdır (advanced.html:1553,
# min=0 max=90) ve yükseliş açısı tanımıyla uyumludur — trajectory_analysis.py
# başlığı: 90° = dikey yukarı, ufuktan ölçülür.
LAUNCH_SETTING_BOUNDS = {
    'launch_angle': (0.0, 90.0),      # derece, ufuktan (yükseliş açısı)
    'launch_altitude': (0.0, None),   # m
    'wind_speed': (0.0, None),        # m/s (yön işareti wind_direction'da)
    'wind_direction': (None, None),   # derece, rüzgârın GELDİĞİ yön (WMO)
    'launch_rod_length': (0.0, None),  # m
}

# Çağıranın veremeyeceği (arayüzde karşılığı olmayan) ayarların dışa aktarıcı
# varsayılanları — TEK tanım noktası (CLAUDE.md kural 11). XML şablonu da bu
# sözlükten beslenir, sayı iki yerde tekrarlanmaz.
EXPORTER_DEFAULT_SETTINGS = {
    'time_step': 0.01,        # s  — OpenRocket entegrasyon adımı önerisi
    'max_altitude': 50000,    # m  — simülasyon tavanı önerisi
    'launch_rod_length': 3,   # m  — rampa boyu; sayfada karşılığı olan alan yok
}

# ---------------------------------------------------------------------------
# ARAÇ TANIMI (Faz 4B, bulgu A12/b)
# ---------------------------------------------------------------------------
# Ölçüm: ``create_flight_simulation_data`` çağıran araç vermediğinde sessizce
# 5 kg / 0,10 m / 1,5 m'lik bir araç kuruyor, ondan ``estimated_apogee``
# hesaplayıp yanıta koyuyordu; çıktıda bunun bir varsayım olduğunu söyleyen
# HİÇBİR alan yoktu. Gerçek motorlarla bu araç 100 km üstü apojeler üretiyor.
#
# Doğru desen zaten depoda: app.py::_resolve_vehicle_spec aracı çözerken her
# alanın kaynağını ``sources`` sözlüğüne yazıyor ve dışa aktarıcıya
# ``rocket_params['sources']`` olarak geçiriyor (app.py:1247). Dışa aktarıcı
# bu sözlüğü OKUMUYORDU — bayrak yazılıyor, kimse okumuyor deseni. Artık
# okunuyor ve ``rocket_parameters_source`` alanıyla yayımlanıyor.
#
# Örnek araç yalnız BİÇİM zorunluluğu olan yerde kullanılır: .ork XML'i bir
# gövde boyu/çapı yazmak zorundadır (rüzgâr yer tutucusuyla aynı gerekçe).
# Sayısal bir İDDİA olan apoje ise örnek araçtan ÜRETİLMEZ.
EXPORTER_EXAMPLE_VEHICLE = {
    'name': 'EXAMPLE ROCKET (not the user vehicle)',
    'dry_mass': 5.0,          # kg
    'diameter': 0.1,          # m
    'length': 1.5,            # m
    'drag_coefficient': 0.5,
    'fin_count': 4,
}

# Uçuş kestirimi için araçtan ZORUNLU olan alanlar. Boy ve fin sayısı
# kapalı-form kestirime girmez (sürükleme çapı kullanır), bu yüzden listede yok.
VEHICLE_REQUIRED_FIELDS = ('dry_mass', 'diameter')

VEHICLE_SOURCE_LABELS = {
    'request': 'from the calculation request (user input)',
    'not_supplied': ('NOT supplied by the caller - no value assumed; '
                     'enter the vehicle in OpenRocket'),
    'exporter_example': ('EXAMPLE vehicle bundled with the exporter - this is '
                         'NOT your rocket; replace it in OpenRocket'),
    'not_modelled': 'not modelled by this export',
}

# Çıkarım eşikleri. Bu sınıftaki (amatör/üniversite) motorlarda bir çap metre
# cinsinden 1 m'yi, bir boy 5 m'yi geçmez; geçiyorsa değer milimetredir.
# Belirsiz bant (ör. 1.0) çap için mm kabul edilir: 1 m boğaz bu yazılımın
# kapsamı dışında, 1 mm boğaz ise gerçek bir mikro-motor ölçüsüdür.
DIAMETER_SI_MAX_M = 1.0
LENGTH_SI_MAX_M = 5.0
THICKNESS_SI_MAX_M = 0.1

# .eng başlığındaki 2. alanın ne olduğu: RASP formatında motor KASA (gövde)
# çapıdır, boğaz çapı değil. Kasa dış çapı bulunamazsa hangi ölçünün yazıldığı
# dosyaya not düşülür.
CASE_DIAMETER_SOURCE_LABELS = {
    'explicit': 'motor casing outer diameter (from results)',
    'chamber_plus_wall': 'casing outer diameter = chamber inner diameter + 2 x wall thickness',
    'chamber': ('chamber inner diameter (wall thickness not available - '
                'outer diameter is slightly larger)'),
    'exit': ('nozzle exit diameter used as casing placeholder - chamber '
             'diameter NOT available; check the diameter in OpenRocket'),
    'throat': ('WARNING: casing diameter NOT available; throat diameter '
               'written as placeholder - correct it in OpenRocket'),
}


def _length_in_meters(value, si_max: float) -> Tuple[Optional[float], str]:
    """Bir uzunluğu metreye çevirir; birimi büyüklüğünden çıkarır.

    Döner: (metre, 'si' | 'mm' | 'missing'). Üst seviye sonuçlar birimi beyan
    etmediği için başka yol yok; çağıran hangi yolun seçildiğini raporlar.
    """
    f = _finite_positive(value)
    if f is None:
        return None, 'missing'
    if f > si_max:
        return f / 1000.0, 'mm'
    return f, 'si'


def _nested(data, *path):
    """İç içe sözlükten güvenli okuma; ara düğüm sözlük değilse None."""
    node = data
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _finite_positive(value) -> Optional[float]:
    """Sonlu ve pozitif float döndürür; aksi halde None."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if (np.isfinite(f) and f > 0.0) else None


def _finite_number(value) -> Optional[float]:
    """Sonlu float döndürür — 0 ve negatif DAHİL; aksi halde None.

    Fırlatma koşulları için gerekli: kullanıcının yazdığı 0 m/s rüzgâr geçerli
    bir girdidir ("sakin hava") ve `_finite_positive` onu eleyip "veri yok"
    ile karıştırırdı. İkisi ayrı şeydir: veri yok -> None, kullanıcı 0 yazdı
    -> 0.0.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _air_density(altitude_m: float) -> float:
    """ISA hava yoğunluğu [kg/m^3] — basınç/sıcaklık tek kaynaktan (constants)."""
    h = float(max(0.0, altitude_m))
    T = isa_temperature(h)
    p = isa_pressure(h)
    return float(p * M_AIR / (R_STAR_ICAO * T))


class OpenRocketExporter:
    """Export motor data to OpenRocket compatible formats"""
    
    def __init__(self):
        # Standard motor designations
        self.motor_classes = {
            # Total impulse ranges (N·s)
            'A': (1.26, 2.5),
            'B': (2.51, 5.0),
            'C': (5.01, 10.0),
            'D': (10.01, 20.0),
            'E': (20.01, 40.0),
            'F': (40.01, 80.0),
            'G': (80.01, 160.0),
            'H': (160.01, 320.0),
            'I': (320.01, 640.0),
            'J': (640.01, 1280.0),
            'K': (1280.01, 2560.0),
            'L': (2560.01, 5120.0),
            'M': (5120.01, 10240.0),
            'N': (10240.01, 20480.0),
            'O': (20480.01, 40960.0)
        }
    
    def resolve_eng_inputs(self, motor_data: Dict) -> Dict:
        """.eng / .ork için kritik alanları çözer ve eksikleri raporlar.

        Bu, A12'nin kapısıdır: her kritik alan önce GERÇEK sonuçtan çözülür
        (motor tipine göre farklı anahtarlarda olabilir, bkz. resolve_*),
        çözülemeyen alan ``missing_fields``e yazılır. Hiçbir yer tutucu sayı
        üretilmez.

        Döner: çözülmüş değerler + ``ok`` / ``missing_fields`` / ``reasons``.
        """
        md = motor_data if isinstance(motor_data, dict) else {}

        geometry = self.resolve_geometry(md)
        case_d = _finite_positive(geometry.get('case_diameter'))
        chamber_l = _finite_positive(geometry.get('chamber_length'))
        prop_mass, prop_src = self.resolve_propellant_mass(md)
        impulse, impulse_src = self.resolve_total_impulse(md)
        thrust_curve, thrust_source = self.resolve_thrust_curve(md)

        missing: List[str] = []
        reasons: Dict[str, str] = {}

        if case_d is None:
            missing.append('case_diameter')
            reasons['case_diameter'] = (
                'no casing, chamber, exit or throat diameter could be resolved '
                '(searched motor_geometry, case_outer_diameter, casing_diameter, '
                'case_diameter, cad_design.case_design.outer_diameter, '
                'chamber_diameter, exit_diameter, throat_diameter).')
        if chamber_l is None:
            missing.append('chamber_length')
            reasons['chamber_length'] = (
                'chamber_length is missing, non-finite or non-positive; the '
                'RASP length field would have to be a placeholder.')
        if prop_mass is None:
            missing.append('propellant_mass')
            reasons['propellant_mass'] = (
                'propellant mass could not be resolved (searched '
                'propellant_mass_total, design_summary.masses.'
                'propellant_mass_kg, propellant_mass, total_mass_flow x '
                'burn_time); OpenRocket uses the loaded mass directly in the '
                'apogee calculation.')
        if impulse is None:
            missing.append('total_impulse')
            reasons['total_impulse'] = (
                'total impulse could not be resolved (searched total_impulse, '
                'the thrust curve integral, average thrust x burn time); the '
                'RASP class letter is derived from it.')
        if not thrust_curve:
            missing.append('thrust_curve')
            reasons['thrust_curve'] = (
                'no time-resolved curve and no (thrust, burn_time) pair; a '
                'thrust curve cannot be written without inventing one.')

        return {
            'ok': not missing,
            'missing_fields': missing,
            'reasons': reasons,
            'geometry': geometry,
            'case_diameter': case_d,          # m
            'chamber_length': chamber_l,      # m
            'propellant_mass': prop_mass,     # kg
            'propellant_mass_source': prop_src,
            'total_impulse': impulse,         # N·s
            'total_impulse_source': impulse_src,
            'thrust_curve': thrust_curve,
            'thrust_source': thrust_source,
        }

    def export_motor_file(self, motor_data: Dict, filename: str = None) -> str:
        """
        Export motor data to OpenRocket .eng format

        Kritik alanlar (kasa çapı, kamara boyu, itici kütlesi, toplam impuls,
        itki eğrisi) gerçek sonuçtan çözülemiyorsa dosya ÜRETİLMEZ:
        ``OpenRocketExportDataError`` yükselir (bulgu A12, fail-closed).

        Args:
            motor_data: Complete motor analysis results
            filename: Output filename (optional)

        Returns:
            Generated .eng file content

        Raises:
            OpenRocketExportDataError: kritik alan eksik/geçersiz.
        """

        resolved = self.resolve_eng_inputs(motor_data)
        if not resolved['ok']:
            raise OpenRocketExportDataError(
                resolved['missing_fields'], resolved['reasons'], what='.eng')

        geometry = resolved['geometry']
        # RASP başlığının 2. alanı motor KASA çapıdır (mm), boğaz çapı değil.
        case_diameter = resolved['case_diameter'] * 1000.0
        chamber_length = resolved['chamber_length'] * 1000.0

        # Create motor designation
        motor_designation = self._designation(motor_data, geometry)

        # Generate .eng file content
        eng_content = self._create_eng_file(
            motor_designation, case_diameter, chamber_length,
            resolved['propellant_mass'], resolved['total_impulse'],
            resolved['thrust_curve'], motor_data,
            thrust_source=resolved['thrust_source'], geometry=geometry,
            resolved=resolved
        )

        # Save to file if filename provided
        if filename:
            if not filename.endswith('.eng'):
                filename += '.eng'
            with open(filename, 'w') as f:
                f.write(eng_content)

        return eng_content

    @staticmethod
    def resolve_launch_settings(launch_params: Dict = None) -> Tuple[Dict, Dict]:
        """Fırlatma koşullarını ÇAĞIRANIN sözlüğünden çözer (v2.6.26, P4).

        `launch_params` anahtarları app.py'nin yörünge dalında kurduğu sözlükle
        birebir aynıdır: ``launch_angle``, ``launch_altitude``, ``wind_speed``,
        ``wind_direction`` (+ isteğe bağlı ``launch_rod_length``). Aynı sözlük
        iki dala birden verilebilsin diye ad birliği kasıtlıdır.

        Değer yoksa ya da bandın dışındaysa sayı UYDURULMAZ: alan None kalır,
        nedeni kaynak sözlüğüne yazılır. Kullanıcının yazdığı 0 ile "veri yok"
        birbirinden ayrılır (bkz. _finite_number).

        Döner: (ayarlar, kaynaklar). Kaynaklar LAUNCH_SETTING_SOURCE_LABELS
        anahtarlarıdır.
        """
        params = launch_params if isinstance(launch_params, dict) else {}
        settings: Dict = {}
        sources: Dict[str, str] = {}

        for key, (low, high) in LAUNCH_SETTING_BOUNDS.items():
            default = EXPORTER_DEFAULT_SETTINGS.get(key)
            raw = params.get(key)
            if raw is None:
                # Çağıran vermedi. Arayüzde karşılığı olmayan ayarlar (rampa
                # boyu) dışa aktarıcı varsayılanına düşer ve bunu BEYAN eder;
                # kullanıcının gerçekten girebildiği alanlar boş kalır.
                settings[key] = default
                sources[key] = ('exporter_default' if default is not None
                                else 'not_supplied')
                continue
            value = _finite_number(raw)
            if value is None or (low is not None and value < low) or \
                    (high is not None and value > high):
                settings[key] = None
                sources[key] = 'invalid_input'
                continue
            settings[key] = value
            sources[key] = 'request'

        # Sayısal simülasyon ayarları: fiziksel bir iddia değil, OpenRocket'a
        # önerilen çözücü ayarlarıdır; kaynakları böyle etiketlenir.
        for key in ('time_step', 'max_altitude'):
            settings[key] = EXPORTER_DEFAULT_SETTINGS[key]
            sources[key] = 'exporter_default'

        return settings, sources

    @staticmethod
    def resolve_vehicle(rocket_params: Dict = None) -> Tuple[Dict, Dict, List[str]]:
        """Aracı çözer ve HER alanın kaynağını beyan eder (bulgu A12/b).

        Çağıran kendi kaynak sözlüğünü ``rocket_params['sources']`` içinde
        gönderebilir — app.py::_resolve_vehicle_spec tam olarak bunu yapıyor
        (app.py:1247) ama dışa aktarıcı sözlüğü okumuyordu. Artık okunuyor;
        çağıranın beyanı (ör. ``motor_inert_lower_bound:structural``) aynen
        taşınır, çünkü o beyan ölçülmüş bir sayıya dayanıyor.

        Araç hiç verilmediyse ÖRNEK araç kullanılır ve her alanın kaynağı
        ``exporter_example`` olur; bu, kapalı-form apoje kestirimini kapatmaya
        yeter (uydurma araçtan sayısal iddia üretilmez).

        Döner: (parametreler, kaynaklar, uçuş kestirimi için eksik alanlar)
        """
        if not isinstance(rocket_params, dict):
            params = dict(EXPORTER_EXAMPLE_VEHICLE)
            sources = {k: 'exporter_example' for k in params if k != 'name'}
            return params, sources, list(VEHICLE_REQUIRED_FIELDS)

        params = dict(rocket_params)
        caller_sources = params.pop('sources', None)
        caller_sources = caller_sources if isinstance(caller_sources, dict) else {}

        sources: Dict[str, str] = {}
        for key in ('dry_mass', 'diameter', 'length', 'drag_coefficient'):
            value = _finite_positive(params.get(key))
            beyan = caller_sources.get(key)
            if beyan:
                sources[key] = str(beyan)
            else:
                sources[key] = 'request' if value is not None else 'not_supplied'

        missing = [key for key in VEHICLE_REQUIRED_FIELDS
                   if _finite_positive(params.get(key)) is None
                   or sources.get(key) == 'exporter_example']
        return params, sources, missing

    @staticmethod
    def _vehicle_source_labels(sources: Dict) -> Dict:
        """Kaynak anahtarlarını okunabilir etikete çevirir.

        Çağıranın kendi ürettiği anahtarlar (ör. ``motor_case_lower_bound:
        chamber_plus_wall``) sözlükte yoktur; olduğu gibi taşınır — sessizce
        düşürülmesi beyanı yok ederdi.
        """
        return {k: VEHICLE_SOURCE_LABELS.get(v, v) for k, v in (sources or {}).items()}

    def create_flight_simulation_data(self, motor_data: Dict, rocket_params: Dict = None,
                                      launch_params: Dict = None) -> Dict:
        """
        Create flight simulation parameters for OpenRocket integration

        Args:
            motor_data: Motor analysis results
            rocket_params: Rocket parameters (mass, drag, etc.). Verilmezse
                apoje kestirimi YAPILMAZ (bulgu A12/b): eskiden 5 kg / 0,10 m /
                1,5 m'lik uydurma bir araçtan ``estimated_apogee`` üretiliyor ve
                çıktıda bunun varsayım olduğunu söyleyen hiçbir alan
                bulunmuyordu.
            launch_params: Fırlatma koşulları (launch_angle, wind_speed,
                wind_direction, launch_altitude). Verilmezse ilgili ayarlar
                None kalır ve kaynağı "not_supplied" olarak beyan edilir —
                sıfır rüzgâr / 85° gibi sayılar UYDURULMAZ (v2.6.26, P4).

        Returns:
            Flight simulation data
        """

        vehicle, vehicle_sources, vehicle_missing = self.resolve_vehicle(rocket_params)

        # Uçuş kestirimi ARAÇ + MOTOR ister. İkisinden biri gerçek değilse sayı
        # üretilmez; hangi alanın eksik olduğu çıktıda yazılıdır.
        motor_missing = self._flight_estimate_missing_motor_fields(motor_data)
        missing = list(vehicle_missing) + motor_missing
        if missing:
            flight_data = None
            flight_status = 'not_computed'
            flight_reason = (
                'apogee/trajectory estimate NOT computed: these inputs are not '
                'available from the caller or the solver: '
                + ', '.join(missing)
                + '. No example vehicle is used to produce a number.')
        else:
            flight_data = self._calculate_flight_performance(
                motor_data, vehicle, vehicle_sources)
            flight_status = 'ok'
            flight_reason = None

        settings, sources = self.resolve_launch_settings(launch_params)

        # Generate OpenRocket simulation parameters
        simulation_params = {
            'motor_data': motor_data,
            'rocket_parameters': vehicle,
            # Aracın her alanı kimden geldi: istekten mi, çağıranın türettiği
            # bir alt sınırdan mı, yoksa dışa aktarıcının ÖRNEK aracından mı.
            'rocket_parameters_source': vehicle_sources,
            'rocket_parameters_source_labels':
                self._vehicle_source_labels(vehicle_sources),
            'rocket_parameters_are_exporter_example':
                any(v == 'exporter_example' for v in vehicle_sources.values()),
            'flight_performance': flight_data,
            'flight_performance_status': flight_status,
            'flight_performance_missing_fields': missing,
            'flight_performance_reason': flight_reason,
            'simulation_settings': settings,
            # Hangi ayar kimden geldi: istekten mi, dışa aktarıcı
            # varsayılanından mı, yoksa hiç verilmedi mi.
            'simulation_settings_source': sources,
            'simulation_settings_source_labels': {
                k: LAUNCH_SETTING_SOURCE_LABELS[v] for k, v in sources.items()
            },
        }

        return simulation_params

    @classmethod
    def _flight_estimate_missing_motor_fields(cls, motor_data: Dict) -> List[str]:
        """Kapalı-form apoje kestirimi için motordan eksik olan alanlar.

        Eski kod dördünü de varsayılana düşürüyordu (itici 1 kg, Isp 250 s,
        itki 1000 N, yanma 10 s); apoje bu varsayılanlardan üretilip
        ``estimated_apogee`` adıyla dönüyordu.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        missing: List[str] = []
        if cls.resolve_propellant_mass(md)[0] is None:
            missing.append('propellant_mass')
        if _finite_positive(md.get('burn_time')) is None:
            missing.append('burn_time')
        if cls.resolve_average_thrust(md)[0] is None:
            missing.append('thrust')
        isp = (_finite_positive(md.get('isp'))
               or _finite_positive(md.get('specific_impulse'))
               or _finite_positive(md.get('isp_sea_level')))
        if isp is None:
            missing.append('isp')
        return missing

    def generate_technical_report(self, motor_data: Dict) -> str:
        """Generate technical report for OpenRocket documentation"""
        
        report = []
        
        # Header
        report.append("UZAYTEK HYBRID ROCKET MOTOR")
        report.append("OpenRocket Integration Report")
        report.append("=" * 50)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Motor specifications
        report.append("MOTOR SPECIFICATIONS:")
        report.append("-" * 30)
        total_impulse = motor_data.get('total_impulse', 0)
        motor_class = self._get_motor_class(total_impulse)
        # Geometri TEK yardımcıdan; ham alanlar mm/m karışıktır (bulgu 1)
        geometry = self.resolve_geometry(motor_data)

        report.append(f"Designation: {self._designation(motor_data, geometry)}")
        report.append(f"Motor Class: {motor_class}")
        report.append(f"Total Impulse: {total_impulse:.0f} N·s")
        report.append(f"Average Thrust: {motor_data.get('thrust', 0):.0f} N")
        report.append(f"Burn Time: {motor_data.get('burn_time', 0):.1f} s")
        report.append(f"Specific Impulse: {motor_data.get('isp', 0):.1f} s")
        report.append("")
        
        # Physical dimensions
        report.append("PHYSICAL DIMENSIONS:")
        report.append("-" * 30)
        def dim(label: str, key: str):
            value = geometry.get(key)
            if value is None:
                report.append(f"{label}: not available")
            else:
                report.append(f"{label}: {value * 1000.0:.2f} mm")

        dim("Throat Diameter", 'throat_diameter')
        dim("Exit Diameter", 'exit_diameter')
        dim("Chamber Diameter", 'chamber_diameter')
        dim("Chamber Length", 'chamber_length')
        dim("Case (body) Diameter", 'case_diameter')
        report.append(f"Propellant Mass: {motor_data.get('propellant_mass_total', 0):.2f} kg")
        report.append(f"Geometry source: "
                      f"{GEOMETRY_SOURCE_LABELS.get(geometry.get('source'), 'unknown')}")
        report.append("")
        
        # Performance characteristics
        report.append("PERFORMANCE CHARACTERISTICS:")
        report.append("-" * 30)
        report.append(f"Chamber Pressure: {motor_data.get('chamber_pressure', 0):.1f} bar")
        report.append(f"O/F Ratio: {motor_data.get('of_ratio', 0):.2f}")
        report.append(f"C* Efficiency: {motor_data.get('c_star', 0):.0f} m/s")
        report.append(f"Thrust Coefficient: {motor_data.get('cf', 0):.3f}")
        report.append("")
        
        # OpenRocket compatibility
        report.append("OPENROCKET COMPATIBILITY:")
        report.append("-" * 30)
        report.append("✓ .eng file format supported")
        report.append("✓ Thrust curve data included")
        report.append("✓ Motor mass properties calculated")
        report.append("✓ Burn time profile generated")
        report.append("")
        
        # Usage instructions
        report.append("USAGE INSTRUCTIONS:")
        report.append("-" * 30)
        report.append("1. Export motor as .eng file")
        report.append("2. Copy file to OpenRocket motor directory")
        report.append("3. Load motor in OpenRocket simulation")
        report.append("4. Configure rocket parameters")
        report.append("5. Run flight simulation")
        report.append("")
        
        return "\n".join(report)
    
    def _get_motor_class(self, total_impulse: float) -> str:
        """Determine motor class from total impulse"""
        
        for motor_class, (min_impulse, max_impulse) in self.motor_classes.items():
            if min_impulse <= total_impulse <= max_impulse:
                return motor_class
        
        # For very large motors
        if total_impulse > 40960:
            return 'P+'
        
        return 'A'  # Default
    
    @staticmethod
    def real_thrust_curve(motor_data: Dict):
        """Zaman-çözümlü GERÇEK itki eğrisini bulur.

        Döner: (t[], F[], kaynak_anahtarı) veya (None, None, None).
        Tek yerde tanımlıdır ki eğriyi tüketen üç yol (RASP örnekleme, toplam
        impuls integrali, ortalama itki) aynı eğriyi görsün.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        for key in ('transient', 'thrust_curve'):
            block = md.get(key) or {}
            if not isinstance(block, dict):
                continue
            t_real = block.get('time')
            f_real = block.get('thrust')
            if t_real is None or f_real is None:
                continue
            t_real = np.asarray(t_real, dtype=float)
            f_real = np.asarray(f_real, dtype=float)
            if t_real.size < 4 or t_real.size != f_real.size:
                continue
            if not np.all(np.isfinite(t_real)) or not np.all(np.isfinite(f_real)):
                continue
            return t_real, f_real, key
        return None, None, None

    @staticmethod
    def resolve_propellant_mass(motor_data: Dict) -> Tuple[Optional[float], str]:
        """İtici kütlesini GERÇEK sonuçtan çözer; imza varsayılanı 1 kg YOK.

        Ölçüm (2 Ağustos 2026): aynı sayı motor tipine göre farklı anahtarda
        yayımlanıyor —
          katı  : üst seviyede ``propellant_mass_total`` YOK; ``propellant_mass``
                  = 6,468 kg ve ``design_summary.masses.propellant_mass_kg``
                  aynı sayıyı veriyor.
          sıvı  : kütle hiç yayımlanmıyor; ``total_mass_flow`` = 3,418 kg/s ve
                  ``burn_time`` = 300 s var (sayfanın kendisi de .eng için bu
                  ikisini çarpıyor — liquid.html:4757).
          hibrit: ``propellant_mass_total`` = 8,834 kg doğrudan var.
        Eski kod üçünün ikisinde imza varsayılanı 1,000 kg yazıyordu; OpenRocket
        yüklü kütleyi doğrudan apoje hesabında kullandığı için bu, dosyayı
        sessizce yanlış yapıyordu.

        Döner: (kütle_kg veya None, kaynak_anahtarı)
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        mass = _finite_positive(md.get('propellant_mass_total'))
        if mass is not None:
            return mass, 'propellant_mass_total'

        mass = _finite_positive(
            _nested(md, 'design_summary', 'masses', 'propellant_mass_kg'))
        if mass is not None:
            return mass, 'design_summary'

        mass = _finite_positive(md.get('propellant_mass'))
        if mass is not None:
            return mass, 'propellant_mass'

        mdot = _finite_positive(md.get('total_mass_flow'))
        burn_time = _finite_positive(md.get('burn_time'))
        if mdot is not None and burn_time is not None:
            return mdot * burn_time, 'mdot_x_burn_time'

        return None, 'none'

    @classmethod
    def resolve_average_thrust(cls, motor_data: Dict) -> Tuple[Optional[float], str]:
        """Ortalama itkiyi gerçek sonuçtan çözer; 1000 N varsayılanı YOK.

        Ölçüm: katı çözücü üst seviyede ``thrust`` yayımlamıyor
        (``average_thrust`` = 6704,9 N, ``max_thrust`` ayrı). Eski sabit-itki
        yedeği bu durumda 1000 N yazıyordu.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        for key in ('thrust', 'average_thrust'):
            value = _finite_positive(md.get(key))
            if value is not None:
                return value, key

        t_real, f_real, _src = cls.real_thrust_curve(md)
        if t_real is not None and float(t_real[-1] - t_real[0]) > 0.0:
            span = float(t_real[-1] - t_real[0])
            mean = float(np.trapz(np.clip(f_real, 0.0, None), t_real)) / span
            if np.isfinite(mean) and mean > 0.0:
                return mean, 'curve_mean'
        return None, 'none'

    @classmethod
    def resolve_total_impulse(cls, motor_data: Dict) -> Tuple[Optional[float], str]:
        """Toplam impulsu gerçek sonuçtan çözer; 10000 N·s varsayılanı YOK.

        .eng sınıf harfi (A..O) yalnız bu sayıdan gelir; varsayılan 10000 N·s
        boş bir motoru "M sınıfı" diye etiketliyordu (bulgu A12'nin alıntıladığı
        ``M0-...`` satırının "M"si). Ölçüm: sıvı çözücü ``total_impulse``
        yayımlamıyor; sayfa onu itki x yanma süresi olarak türetiyor
        (liquid.html:4753).
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        value = _finite_positive(md.get('total_impulse'))
        if value is not None:
            return value, 'total_impulse'

        t_real, f_real, _src = cls.real_thrust_curve(md)
        if t_real is not None:
            integral = float(np.trapz(np.clip(f_real, 0.0, None), t_real))
            if np.isfinite(integral) and integral > 0.0:
                return integral, 'curve_integral'

        avg_thrust, _tsrc = cls.resolve_average_thrust(md)
        burn_time = _finite_positive(md.get('burn_time'))
        if avg_thrust is not None and burn_time is not None:
            return avg_thrust * burn_time, 'thrust_x_burn_time'

        return None, 'none'

    def resolve_thrust_curve(self, motor_data: Dict
                             ) -> Tuple[List[Tuple[float, float]], str]:
        """İtki-zaman eğrisini GERÇEK çözüm kaynaklarından çözer.

        Öncelik sırası:
          1. motor_data['transient']    — transient_ballistics (time[], thrust[])
          2. motor_data['thrust_curve'] — katı motor grain burn-back çözücüsü
          3. sabit itki                 — hiçbir zaman-çözümlü eğri yoksa
          4. hiçbiri                    — itki de yanma süresi de yoksa BOŞ liste

        3. seçenekte ŞEKİL UYDURULMAZ: eskiden buraya %15 doğrusal düşüş +
        0.1 s yükselme rampası (x0.8) + 0.5 s sönme (x0.3) ekleniyor ve dosya
        "gerçekçi hibrit itki eğrisi" diye OpenRocket'a gidiyordu (2026-07-19
        denetimi, kritik bulgu). Artık sabit itki yazılır ve bunun bir varsayım
        olduğu .eng yorum satırına düşülür.

        4. seçenek Faz 4B'de eklendi: sabit-itki yedeği de eskiden 1000 N x 10 s
        UYDURUYORDU (ölçüm: boş sözlükle .eng dosyasında ``0.010 1000.0`` ve
        ``10.000 1000.0`` satırları). İtki bilinmiyorsa eğri yoktur; çağıran
        kapıyı işletir.

        Döner: (noktalar, kaynak_anahtarı)
        """
        t_real, f_real, key = self.real_thrust_curve(motor_data)
        if t_real is not None:
            pts: List[Tuple[float, float]] = []
            if t_real[0] > 0.0:
                pts.append((0.0, 0.0))  # RASP: eğri sıfırdan başlar
            idx = np.unique(np.linspace(0, t_real.size - 1,
                                        min(ENG_MAX_SAMPLES, t_real.size)
                                        ).astype(int))
            for i in idx:
                pts.append((float(t_real[i]), max(0.0, float(f_real[i]))))
            if pts[-1][1] > 0.0:  # format gereği sıfırla bitir
                pts.append((pts[-1][0] + ENG_ZERO_TERMINATOR_DT_S, 0.0))
            return pts, key

        # ---- Zaman-çözümlü eğri yok: SABİT itki (uydurma şekil üretilmez) ----
        md = motor_data if isinstance(motor_data, dict) else {}
        burn_time = _finite_positive(md.get('burn_time'))
        avg_thrust, _src = self.resolve_average_thrust(md)
        if burn_time is None or avg_thrust is None:
            # Ne eğri ne de (itki, süre) çifti var: sayı UYDURULMAZ.
            return [], 'unavailable'
        points = [
            (0.0, 0.0),
            (ENG_ZERO_TERMINATOR_DT_S, avg_thrust),
            (burn_time, avg_thrust),
            (burn_time + ENG_ZERO_TERMINATOR_DT_S, 0.0),
        ]
        return points, 'constant'

    def _generate_thrust_curve(self, motor_data: Dict) -> List[Tuple[float, float]]:
        """Geriye dönük uyum: yalnız nokta listesini döndürür."""
        points, _source = self.resolve_thrust_curve(motor_data)
        return points

    @staticmethod
    def resolve_inert_mass(motor_data: Dict) -> Tuple[Optional[float], str]:
        """Motorun kuru (kasa/yapı) kütlesini GERÇEK analizden çözer.

        Eski kod her motorda `prop_mass + 0.5` yazıyordu — 10 kg iticili bir
        motorun kasası 0.5 kg değildir ve OpenRocket yüklü kütleyi doğrudan
        apoje hesabında kullanır (2026-07-19 denetimi).

        Döner: (kütle_kg veya None, kaynak_anahtarı)
        """
        struct = motor_data.get('structural_analysis') or {}
        if isinstance(struct, dict):
            weight = struct.get('weight_analysis') or {}
            if isinstance(weight, dict):
                mass = _finite_positive(weight.get('total_weight'))
                if mass is not None:
                    return mass, 'structural'

        for key in ('dry_mass', 'motor_mass', 'engine_mass', 'total_dry_mass',
                    'inert_mass', 'case_mass'):
            mass = _finite_positive(motor_data.get(key))
            if mass is not None:
                return mass, 'reported'

        return None, 'none'

    # ------------------------------------------------------------------
    # Geometri sözleşmesi — TEK yardımcı (2026-07-19 Codex bulgu 1 ve 2)
    # ------------------------------------------------------------------
    @staticmethod
    def _wall_thickness_m(motor_data: Dict) -> Optional[float]:
        """Kasa cidar kalınlığını [m] gerçek analizlerden çeker.

        Aranan yerler (ilk bulunan kazanır): CAD kasa tasarımı, katı motor
        kasa analizi, sıvı kamara yapısı, hibrit kamara analizi. '_mm' ekli
        anahtarlar birimini beyan eder; diğerlerinde büyüklükten çıkarılır.
        """
        explicit_mm = [
            _nested(motor_data, 'cad_design', 'case_design', 'wall_thickness'),
            _nested(motor_data, 'structural_analysis', 'case_analysis',
                    'wall_thickness_mm'),
            _nested(motor_data, 'structural_analysis', 'case_analysis',
                    'recommended_wall_thickness_mm'),
        ]
        for value in explicit_mm:
            t = _finite_positive(value)
            if t is not None:
                return t / 1000.0

        inferred = [
            _nested(motor_data, 'structural_analysis', 'chamber_structure',
                    'wall_thickness'),
            _nested(motor_data, 'structural_analysis', 'chamber_analysis',
                    'recommended_thickness'),
            _nested(motor_data, 'structural_analysis', 'chamber_analysis',
                    'minimum_thickness'),
            motor_data.get('wall_thickness'),
        ]
        for value in inferred:
            t, _unit = _length_in_meters(value, THICKNESS_SI_MAX_M)
            if t is not None:
                return t
        return None

    def resolve_geometry(self, motor_data: Dict) -> Dict:
        """Motor geometrisini SI [m] olarak çözer ve kaynağını raporlar.

        Öncelik:
          1. `motor_geometry` bloğu — motor_geometry.py'de normalize edilmiş,
             birimi GARANTİ SI. Katı/sıvı yanıtlarında hazır gelir.
          2. Üst seviye alanlar — birim beyan edilmediği için büyüklükten
             çıkarılır (_length_in_meters).

        Döner: throat/exit/chamber çapları, kamara boyu, .eng başlığı için
        kasa dış çapı, `source` (GEOMETRY_SOURCE_LABELS) ve okunan her alanın
        hangi yoldan geldiğini gösteren `fields` + `notes`.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        geo = md.get('motor_geometry')
        geo = geo if isinstance(geo, dict) else None

        fields: Dict[str, str] = {}
        notes: List[str] = []

        def pick(key: str, si_max: float) -> Optional[float]:
            if geo is not None:
                value = _finite_positive(geo.get(key))
                if value is not None:
                    fields[key] = 'motor_geometry'
                    return value
            value, unit = _length_in_meters(md.get(key), si_max)
            fields[key] = unit
            if unit == 'mm':
                notes.append(f'{key} read as mm ({float(md[key]):.4g})')
            return value

        throat_d = pick('throat_diameter', DIAMETER_SI_MAX_M)
        exit_d = pick('exit_diameter', DIAMETER_SI_MAX_M)
        chamber_d = pick('chamber_diameter', DIAMETER_SI_MAX_M)
        chamber_l = pick('chamber_length', LENGTH_SI_MAX_M)

        # --- Kasa (gövde) dış çapı: .eng başlığının 2. alanı --------------
        case_d = None
        case_src = 'throat'
        for key in ('case_outer_diameter', 'casing_diameter', 'case_diameter'):
            value, unit = _length_in_meters(
                (geo or {}).get(key, md.get(key)), DIAMETER_SI_MAX_M)
            if value is not None:
                case_d, case_src = value, 'explicit'
                fields[key] = unit if geo is None else 'motor_geometry'
                break
        if case_d is None:
            outer_mm = _finite_positive(
                _nested(md, 'cad_design', 'case_design', 'outer_diameter'))
            if outer_mm is not None:
                case_d, case_src = outer_mm / 1000.0, 'explicit'
                fields['case_outer_diameter'] = 'cad_design.case_design (mm)'
        if case_d is None and chamber_d is not None:
            wall = self._wall_thickness_m(md)
            if wall is not None:
                case_d, case_src = chamber_d + 2.0 * wall, 'chamber_plus_wall'
            else:
                case_d, case_src = chamber_d, 'chamber'
        if case_d is None and exit_d is not None:
            case_d, case_src = exit_d, 'exit'
        if case_d is None and throat_d is not None:
            case_d, case_src = throat_d, 'throat'

        source = 'motor_geometry' if geo else 'inferred'
        if throat_d is None and chamber_d is None and chamber_l is None:
            source = 'missing'

        return {
            'throat_diameter': throat_d,
            'exit_diameter': exit_d,
            'chamber_diameter': chamber_d,
            'chamber_length': chamber_l,
            'case_diameter': case_d,
            'case_diameter_source': case_src,
            'source': source,
            'fields': fields,
            'notes': notes,
        }

    # NOT (Faz 4B): burada bir `_mm(value, fallback_mm)` yardımcısı vardı ve
    # değer yokken YER TUTUCU bir milimetre döndürüyordu (.eng başlığındaki
    # 0.0 çap ve 500.0 boy tam olarak oradan geliyordu, bulgu A12). Kapı
    # kurulunca tek çağrısı kalmadı ve yardımcı kaldırıldı: elinin altında
    # duran bir "yedek değer üret" fonksiyonu kusurun geri gelme yoludur.

    def _designation(self, motor_data: Dict, geometry: Dict = None) -> str:
        """`<sınıf><kasa çapı mm>-<motor adı>`.

        Sınıf harfi TOPLAM İMPULSTAN gelir. Sayı eskiden boğaz çapıydı ve birim
        karışıklığı yüzünden katı motorda 47927 çıkıyordu; artık ticari motor
        adlandırmasıyla uyumlu olarak kasa çapıdır (mm).

        Faz 4B (bulgu A12): iki girdi de UYDURULMUYOR. Eskiden impuls yoksa
        10000 N·s varsayılıp "M", kasa çapı yoksa 0 yazılıyordu; boş bir
        sözlükten ``M0-UZAYTEK-HRM-001`` çıkıyordu. Değer yoksa ad
        ``UNKNOWN-<motor adı>`` olur — dosya adında da güvenli, sınıf iddiası
        taşımayan bir dize.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        geo = geometry if geometry is not None else self.resolve_geometry(md)
        motor_name = md.get('motor_name', 'UZAYTEK-HRM-001')
        total_impulse, _src = self.resolve_total_impulse(md)
        case_m = _finite_positive(geo.get('case_diameter'))
        if total_impulse is None or case_m is None:
            return f"UNKNOWN-{motor_name}"
        motor_class = self._get_motor_class(total_impulse)
        return f"{motor_class}{int(round(case_m * 1000.0))}-{motor_name}"

    def _create_eng_file(self, designation: str, diameter: float, length: float,
                        prop_mass: float, total_impulse: float,
                        thrust_curve: List[Tuple[float, float]], motor_data: Dict,
                        thrust_source: str = 'constant',
                        geometry: Dict = None, resolved: Dict = None) -> str:
        """Create .eng file content.

        Dosya kendini beyan eder: itki eğrisinin, yüklü kütlenin ve (2026-07-19
        Codex denetiminden sonra) GEOMETRİNİN hangi kaynaktan geldiği yorum
        satırlarına yazılır. `diameter` motor KASA çapıdır (mm), boğaz çapı
        değil — RASP başlığının 2. alanı budur.

        SON KAPI (bulgu A12): bu metot doğrudan çağrılsa bile çapı/boyu/kütlesi
        sıfır ya da sonlu olmayan bir motor satırı YAZILMAZ. "Çapı sıfır motor
        dosyası hiçbir yoldan üretilemez" sözleşmesi burada kilitlidir.
        """

        geometry = geometry or self.resolve_geometry(motor_data)

        gecersiz = {}
        for ad, deger in (('diameter_mm', diameter), ('length_mm', length),
                          ('propellant_mass_kg', prop_mass),
                          ('total_impulse_Ns', total_impulse)):
            if _finite_positive(deger) is None:
                gecersiz[ad] = f'value written to the header would be {deger!r}'
        if not thrust_curve:
            gecersiz['thrust_curve'] = 'no thrust samples to write'
        if gecersiz:
            raise OpenRocketExportDataError(
                sorted(gecersiz), gecersiz, what='.eng')

        lines = []

        # Header comment
        lines.append(f"; {designation}")
        lines.append(f"; UZAYTEK Rocket Motor")
        lines.append(f"; Generated by UZAYTEK Analysis Software")
        lines.append(f"; {datetime.now().strftime('%Y-%m-%d')}")
        _egri_etiketi = (
            _thrust_curve_label(motor_data.get('thrust_curve'))
            if thrust_source == 'thrust_curve'
            else THRUST_SOURCE_LABELS.get(thrust_source, thrust_source))
        lines.append(f"; thrust curve: {_egri_etiketi}")
        lines.append(f"; geometry source: "
                     f"{GEOMETRY_SOURCE_LABELS.get(geometry.get('source'), 'unknown')}")
        for note in geometry.get('notes') or []:
            lines.append(f"; geometry note: {note}")
        lines.append(f"; diameter field = "
                     f"{CASE_DIAMETER_SOURCE_LABELS.get(geometry.get('case_diameter_source'), 'unknown')}")
        if geometry.get('chamber_length') is None:
            lines.append("; length field = exporter placeholder; chamber length "
                         "NOT available in this export - correct it in OpenRocket")
        else:
            lines.append("; length field = chamber length (nozzle not included)")
        throat_m = geometry.get('throat_diameter')
        if throat_m is not None:
            lines.append(f"; throat diameter: {throat_m * 1000.0:.2f} mm "
                         "(not written to the header - reference only)")

        # İtici kütlesi ve toplam impuls hangi alandan çözüldü (bulgu A12):
        # bu iki sayı motor tipine göre farklı anahtarlarda yayımlanıyor ve
        # eskiden bulunamayınca imza varsayılanı (1,000 kg / 10000 N·s)
        # yazılıyordu. Dosyayı açan kişi türetmeyi görmeli.
        resolved = resolved or {}
        prop_src = resolved.get('propellant_mass_source')
        if prop_src:
            lines.append(f"; propellant mass: "
                         f"{PROPELLANT_MASS_SOURCE_LABELS.get(prop_src, prop_src)}")
        if thrust_source == 'constant':
            # Sabit itki yaklaşımında yazılan seviye hangi alandan geldi:
            # katı çözücü `average_thrust`, hibrit/sıvı `thrust` yayımlıyor.
            _avg, avg_src = self.resolve_average_thrust(motor_data)
            lines.append('; constant thrust level: '
                         + AVERAGE_THRUST_SOURCE_LABELS.get(avg_src, avg_src))
        impulse_src = resolved.get('total_impulse_source')
        if impulse_src:
            lines.append(f"; total impulse ({total_impulse:.1f} N-s, sets the "
                         f"class letter): "
                         f"{TOTAL_IMPULSE_SOURCE_LABELS.get(impulse_src, impulse_src)}")
        # Çözücü yanma süresini kendisi varsaydığını beyan ediyorsa (sıvı
        # motorda ölçüldü: `burn_time_source` = "assumed 300 s burn"), o beyan
        # dosyaya taşınır — hem itici kütlesi hem toplam impuls bu süreden
        # türetilmiş olabilir ve okuyan kişi zinciri görmelidir.
        burn_time_src = (motor_data or {}).get('burn_time_source')
        if burn_time_src:
            lines.append('; burn time basis (declared by the solver): '
                         + ' '.join(str(burn_time_src).split()))

        # Motor line format: name diameter length delays prop_mass loaded_mass manufacturer
        inert_mass, mass_source = self.resolve_inert_mass(motor_data)
        # inert_mass None ise yüklü kütle = yalnız itici kütlesi yazılır; bu
        # bir varsayılan DEĞİL, dosyanın beyan ettiği bir eksikliktir. RASP
        # sözdizimi bozulmasın diye uyarı ';' yorum satırı olarak motor
        # satırından ÖNCE eklenir (v2.6.26, ZERO-PAT-8).
        loaded_mass = prop_mass + (inert_mass if inert_mass is not None else 0.0)
        lines.append(f"; loaded mass: {MASS_SOURCE_LABELS[mass_source]}")
        if inert_mass is not None:
            lines.append(f"; inert mass used: {inert_mass:.3f} kg")
        else:
            lines.append("; WARNING: loaded mass EXCLUDES motor case mass "
                         "(no structural analysis in this export) - apogee "
                         "will be overestimated until you set the case mass "
                         "in OpenRocket")
        lines.append(";")
        manufacturer = "UZAYTEK"
        delays = "P"  # RASP: tıpalı motor (ejeksiyon yükü yok); "0" anında ateşleme demekti

        motor_line = f"{designation} {diameter:.1f} {length:.1f} {delays} {prop_mass:.3f} {loaded_mass:.3f} {manufacturer}"
        lines.append(motor_line)
        
        # Thrust curve data (RASP: ilk örnek t>0 ve F>0 olmalı)
        for time, thrust in thrust_curve:
            if time <= 0 and thrust <= 0:
                continue
            lines.append(f"{time:.3f} {thrust:.1f}")
        
        # End marker
        lines.append(";")
        
        return "\n".join(lines)
    
    def _calculate_flight_performance(self, motor_data: Dict, rocket_params: Dict,
                                      vehicle_sources: Dict = None) -> Dict:
        """Closed-form (drag-free) flight estimate.

        Eski kod burnout hızını keyfi bir `efficiency = 0.85` çarpanıyla
        kısaltıyor ve apojeyi bundan türetiyordu; sayı ne yerçekimi kaybını ne
        de sürüklemeyi içeriyordu ama 'estimated_apogee' adıyla dönüyordu
        (2026-07-19 denetimi: aynı yanıttaki zaman-adımlı apoje ile 134 kat
        fark). Artık keyfi çarpan yok:

          Δv_ideal = Isp·g0·ln(m_wet/m_dry)                 (Tsiolkovsky)
          v_bo     = Δv_ideal - g0·t_b                      (dik uçuş, yerçekimi kaybı)
          h_bo     ≈ v_bo·t_b/2                             (yanma fazı, doğrusal hız)
          h_coast  = v_bo²/(2·g0)                           (sürüklemesiz süzülüş)

        Sonuç SÜRÜKLEMESİZ ÜST SINIRDIR ve döndürülen sözlükte böyle
        etiketlenir; gerçek irtifa için generate_flight_profile'ın zaman-adımlı
        (ISA sürüklemeli) çözümü kullanılmalıdır.
        """

        # Faz 4B (bulgu A12/b): buradaki `or <sayı>` yedeklerinin hepsi
        # kalktı. Eskiden itici 1 kg, kuru kütle 5 kg, yanma 10 s, Isp 250 s,
        # itki 1000 N varsayılıyor ve sonuç `estimated_apogee` adıyla
        # dönüyordu. Çağıran (create_flight_simulation_data /
        # generate_flight_profile) alanların gerçekliğini ÖNCEDEN doğrular;
        # yine de burada None kalırsa sessizce sayı üretmek yerine hata verilir.
        prop_mass, _prop_src = self.resolve_propellant_mass(motor_data)
        dry_mass = _finite_positive(rocket_params.get('dry_mass'))
        burn_time = _finite_positive(motor_data.get('burn_time'))
        isp = (_finite_positive(motor_data.get('isp'))
               or _finite_positive(motor_data.get('specific_impulse'))
               or _finite_positive(motor_data.get('isp_sea_level')))
        avg_thrust, _thrust_src = self.resolve_average_thrust(motor_data)
        eksik = [ad for ad, deger in (('propellant_mass', prop_mass),
                                      ('dry_mass', dry_mass),
                                      ('burn_time', burn_time),
                                      ('isp', isp),
                                      ('thrust', avg_thrust))
                 if deger is None]
        if eksik:
            raise OpenRocketExportDataError(
                eksik,
                {ad: 'required for the closed-form apogee estimate'
                 for ad in eksik},
                what='flight estimate')

        # Mass ratio
        wet_mass = dry_mass + prop_mass
        mass_ratio = wet_mass / dry_mass

        # Ideal velocity (rocket equation)
        delta_v = isp * G_0 * np.log(mass_ratio)

        # Burnout velocity after gravity loss (vertical flight)
        burnout_velocity = max(0.0, delta_v - G_0 * burn_time)
        altitude_at_burnout = burnout_velocity * burn_time / 2.0
        coast_height = burnout_velocity ** 2 / (2.0 * G_0)
        apogee = altitude_at_burnout + coast_height

        # Maximum acceleration at burnout (lightest mass, full thrust)
        max_acceleration = avg_thrust / dry_mass - G_0

        time_to_apogee = burn_time + burnout_velocity / G_0

        # Araç ÖRNEK araçsa bu, sayının en önemli niteliğidir; yöntem
        # metninin başına yazılır ki çıktıyı okuyan kişi kaçıramasın.
        sources = vehicle_sources or {}
        ornek = any(v == 'exporter_example' for v in sources.values())
        method = ('closed-form vertical flight: rocket equation minus gravity '
                  'loss, NO drag - upper bound only')
        if ornek:
            method = ('EXAMPLE VEHICLE (not the user rocket) - ' + method)

        return {
            'estimated_apogee': apogee,  # m
            'estimated_apogee_method': method,
            # Araç tanımının kaynağı sayının yanında taşınır (bulgu A12/b).
            'vehicle_parameters_source': dict(sources),
            'vehicle_is_exporter_example': ornek,
            'delta_v': delta_v,  # m/s
            'max_acceleration': max_acceleration,  # m/s^2 (net, at burnout)
            'time_to_apogee': time_to_apogee,  # s
            'mass_ratio': mass_ratio,
            'burnout_velocity': burnout_velocity,  # m/s
            'altitude_at_burnout': altitude_at_burnout  # m
        }
    
    def create_ork_project_template(self, motor_data: Dict, rocket_params: Dict = None,
                                    launch_params: Dict = None) -> str:
        """Create OpenRocket project template XML.

        Fırlatma koşulları (rüzgâr, rampa açısı/boyu) artık `launch_params`
        ile aynı çözücüden beslenir (v2.6.26, P4): JSON'daki
        `simulation_settings` ile XML'deki `<conditions>` bloğu tek kaynaktan
        gelir, iki yerde iki farklı rüzgâr dolaşmaz. XML bir SAYI yazmak
        zorunda olduğu için veri yoksa eski varsayılan yazılır — ama bunun bir
        varsayım olduğu yorum satırında beyan edilir.
        """

        # .ork dosyası da OpenRocket'ta doğrudan açılan, motor tanımı taşıyan
        # bir dosyadır: .eng ile AYNI kapıdan geçer (bulgu A12, madde 3).
        # Eskiden boş bir sözlükten motor yuvası 0,5 m x Ø0,1 m ve
        # `<motor>M0-UZAYTEK-HRM-001</motor>` yazan geçerli bir proje çıkıyordu.
        resolved = self.resolve_eng_inputs(motor_data)
        if not resolved['ok']:
            raise OpenRocketExportDataError(
                resolved['missing_fields'], resolved['reasons'], what='.ork')

        # Araç: verilmediyse ÖRNEK araç kullanılır. XML bir gövde boyu/çapı
        # yazmak ZORUNDA (rüzgâr yer tutucusuyla aynı gerekçe), ama bunun
        # örnek olduğu yorum satırlarında beyan edilir; sayısal bir iddia
        # (apoje) örnek araçtan üretilmez.
        vehicle, vehicle_sources, vehicle_missing = self.resolve_vehicle(rocket_params)
        vehicle_notes = []
        for key, fallback in (('name', EXPORTER_EXAMPLE_VEHICLE['name']),
                              ('diameter', EXPORTER_EXAMPLE_VEHICLE['diameter']),
                              ('length', EXPORTER_EXAMPLE_VEHICLE['length'])):
            if key == 'name':
                if not vehicle.get('name'):
                    vehicle['name'] = fallback
                    vehicle_notes.append(
                        'rocket name: EXAMPLE name - the caller did not supply one')
                continue
            if _finite_positive(vehicle.get(key)) is None:
                vehicle[key] = fallback
                vehicle_sources[key] = 'exporter_example'
                vehicle_notes.append(
                    f'{key}: {fallback} m is an EXAMPLE value written because '
                    f'the XML needs a number - it is NOT your rocket; set it '
                    f'in OpenRocket')
            else:
                vehicle_notes.append(
                    f'{key}: {VEHICLE_SOURCE_LABELS.get(vehicle_sources.get(key), vehicle_sources.get(key))}')
        if vehicle_missing:
            vehicle_notes.append(
                'flight estimate NOT included in this template: missing '
                + ', '.join(vehicle_missing))
        vehicle_notes_xml = '\n        '.join(
            f'<!-- {note} -->' for note in vehicle_notes)

        # Geometri TEK yardımcıdan (birim sözleşmesi): motor yuvası boyu ve
        # yarıçapı eskiden ham alanlardan METRE sanılarak alınıyordu; katı
        # motorda 100 m çaplı, 0.6 m yerine 600 m boyunda bir yuva çıkıyordu.
        geometry = resolved['geometry']
        motor_designation = self._designation(motor_data, geometry)
        # Kapıdan geçtiği için ikisi de gerçek; `or <sayı>` yedeği YOK.
        mount_length_m = resolved['chamber_length']
        mount_radius_m = resolved['case_diameter'] / 2.0
        rocket_params = vehicle

        # --- Fırlatma koşulları: JSON ile AYNI çözücüden (P4) --------------
        settings, sources = self.resolve_launch_settings(launch_params)
        wind_xml = settings.get('wind_speed')
        angle_xml = settings.get('launch_angle')
        rod_xml = settings.get('launch_rod_length')
        cond_notes = []
        if wind_xml is None:
            wind_xml = 0.0
            cond_notes.append(
                'windaverage: NO wind data supplied - 0 m/s written as a '
                'placeholder, NOT a value chosen by the user; set it in '
                'OpenRocket')
        else:
            cond_notes.append(f'windaverage: {LAUNCH_SETTING_SOURCE_LABELS[sources["wind_speed"]]}')
        if angle_xml is None:
            angle_xml = 85.0
            cond_notes.append(
                'launchrodangle: NO launch angle supplied - 85 deg written as '
                'a placeholder; check it in OpenRocket')
        else:
            cond_notes.append(
                'launchrodangle: written as the HRMA launch angle, which is '
                'the ELEVATION angle measured from the horizon (90 deg = '
                'straight up); verify the sign convention in OpenRocket '
                'before running the simulation')
        if rod_xml is None:
            rod_xml = EXPORTER_DEFAULT_SETTINGS['launch_rod_length']
        conditions_notes_xml = '\n        '.join(
            f'<!-- {note} -->' for note in cond_notes)

        # Simplified OpenRocket XML template
        xml_template = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<openrocket version="1.5" creator="UZAYTEK">
    <rocket>
        <name>{rocket_params['name']}</name>
        {vehicle_notes_xml}
        <axialoffset method="absolute">0.0</axialoffset>

        <stage>
            <name>Stage 1</name>
            
            <!-- Nose Cone -->
            <nosecone>
                <name>Nose Cone</name>
                <shape>OGIVE</shape>
                <length>0.3</length>
                <aftradius>{rocket_params['diameter']/2}</aftradius>
                <material type="bulk" density="500.0">Fiberglass</material>
                <thickness>0.003</thickness>
            </nosecone>
            
            <!-- Body Tube -->
            <bodytube>
                <name>Body Tube</name>
                <length>{rocket_params['length']}</length>
                <outerradius>{rocket_params['diameter']/2}</outerradius>
                <material type="bulk" density="700.0">Phenolic</material>
                <thickness>0.005</thickness>
                
                <!-- Motor Mount -->
                <motormount>
                    <name>Motor Mount</name>
                    <length>{mount_length_m}</length>
                    <outerradius>{mount_radius_m}</outerradius>
                    <material type="bulk" density="7850.0">Steel</material>
                    <thickness>0.005</thickness>
                    <motorconfig>
                        <configid>default</configid>
                        <motor>{motor_designation}</motor>
                    </motorconfig>
                </motormount>
                
                <!-- Fins -->
                <finset>
                    <name>Fins</name>
                    <fincount>{rocket_params.get('fin_count', 4)}</fincount>
                    <rootchord>0.15</rootchord>
                    <tipchord>0.05</tipchord>
                    <height>0.1</height>
                    <sweepangle>45.0</sweepangle>
                    <material type="bulk" density="500.0">Fiberglass</material>
                    <thickness>0.003</thickness>
                </finset>
            </bodytube>
        </stage>
        
        <!-- Flight Configuration -->
        <flightconfiguration>
            <configid>default</configid>
            <name>Default Configuration</name>
            <motorconfig>
                <configid>default</configid>
                <motor>{motor_designation}</motor>
            </motorconfig>
        </flightconfiguration>
    </rocket>
    
    <!-- Simulation -->
    <simulation>
        <name>UZAYTEK Motor Test</name>
        <flightconfiguration>default</flightconfiguration>
        <conditions>
            <configid>default</configid>
        {conditions_notes_xml}
            <launchrodlength>{float(rod_xml)}</launchrodlength>
            <launchrodangle>{float(angle_xml)}</launchrodangle>
            <windaverage>{float(wind_xml)}</windaverage>
            <atmosphere model="isa"/>
        </conditions>
    </simulation>
</openrocket>"""
        
        return xml_template
    
    def export_eng_file(self, motor_data: Dict, filename: str = None) -> str:
        """Alias for export_motor_file for compatibility"""
        return self.export_motor_file(motor_data, filename)
    
    def export_motor_summary(self, motor_data: Dict) -> Dict:
        """Export motor summary data for OpenRocket integration"""
        
        total_impulse = motor_data.get('total_impulse', 10000)
        motor_class = self._get_motor_class(total_impulse)
        geometry = self.resolve_geometry(motor_data)
        motor_designation = self._designation(motor_data, geometry)
        throat_mm = geometry.get('throat_diameter')
        case_mm = geometry.get('case_diameter')

        return {
            'designation': motor_designation,
            'motor_class': motor_class,
            'total_impulse': total_impulse,
            'average_thrust': motor_data.get('thrust', 0),
            'burn_time': motor_data.get('burn_time', 0),
            'specific_impulse': motor_data.get('isp', 0),
            'propellant_mass': motor_data.get('propellant_mass_total', 0),
            # mm — birim sözleşmesi resolve_geometry'de çözülür
            'throat_diameter': throat_mm * 1000.0 if throat_mm is not None else None,
            'case_diameter': case_mm * 1000.0 if case_mm is not None else None,
            'geometry_source': geometry.get('source'),
            'geometry_notes': geometry.get('notes'),
            'case_diameter_source': geometry.get('case_diameter_source'),
            'chamber_pressure': motor_data.get('chamber_pressure', 0),
            'of_ratio': motor_data.get('of_ratio', 0),
            'manufacturer': 'UZAYTEK',
            'certification_status': 'Experimental'
        }
    
    def generate_flight_profile(self, motor_data: Dict, rocket_params: Dict = None) -> Dict:
        """Generate flight profile data for OpenRocket simulation.

        Araç verilmezse ÖRNEK araç kullanılır; bu durumda sonuç sözlüğü
        ``vehicle_is_exporter_example=True``, ``rocket_parameters_source`` ve
        yöntem metninde büyük harfli "EXAMPLE VEHICLE" uyarısı taşır (bulgu
        A12/b). Bu, önizlemenin bir varsayım olduğunu okuyandan saklamaz;
        sayısal iddianın ne üstünde durduğu çıktının içindedir.
        """

        vehicle, vehicle_sources, _vehicle_missing = self.resolve_vehicle(rocket_params)
        rocket_params = vehicle
        ornek_arac = any(v == 'exporter_example' for v in vehicle_sources.values())

        # Uçuş önizlemesi GERÇEK itici kütlesi ister (v2.6.26, ZERO-PAT-8):
        # eski kod çözülemeyen kütleyi `or 0.0` ile 0 kg yapıyordu — 0 kg
        # itici, itki eğrisi uygulanırken kütlesi hiç azalmayan "yakıtsız"
        # bir araç demektir ve yörünge sessizce anlamsızlaşıyordu. Kütle
        # yoksa simülasyon ATLANIR ve nedeni çıktıda beyan edilir; uydurma
        # varsayılan yok. Anahtarlar başarılı yanıtla aynı tutulur ki çağıran
        # taraf KeyError yemesin (boş listeler grafikte boş eksen çizer).
        #
        # Faz 4B: aynı kapı itki eğrisine de uygulanır. Eski sabit-itki yedeği
        # itki/yanma süresi yokken 1000 N x 10 s uyduruyor, yörünge o uydurma
        # eğriden çiziliyordu.
        prop_mass, _prop_src = self.resolve_propellant_mass(motor_data)
        thrust_curve, thrust_source = self.resolve_thrust_curve(motor_data)
        missing = []
        if prop_mass is None:
            # Ad bilerek `propellant_mass_total`: çağıran tarafın (ve
            # bekçi testlerinin) beklediği alan adı budur.
            missing.append('propellant_mass_total')
        if not thrust_curve:
            missing.append('thrust_curve')
        if missing:
            return {
                'status': 'insufficient_data',
                'error': ('flight profile not computed: these inputs are '
                          'missing, non-finite or non-positive: '
                          + ', '.join(missing)
                          + ' - no default is assumed'),
                'missing_fields': missing,
                'time_data': [],
                'altitude_data': [],
                'velocity_data': [],
                'acceleration_data': [],
                'thrust_data': [],
                'thrust_curve': [],
                'thrust_curve_source': None,
                'performance_summary': None,
                'max_altitude': None,
                'max_altitude_method': None,
                'max_velocity': None,
                'max_acceleration': None,
                'flight_time': None,
                'burnout_time': None,
                'rocket_parameters': vehicle,
                'rocket_parameters_source': vehicle_sources,
                'vehicle_is_exporter_example':
                    any(v == 'exporter_example' for v in vehicle_sources.values()),
            }

        # Calculate flight performance (araç kaynağı sayının yanında taşınır)
        try:
            flight_performance = self._calculate_flight_performance(
                motor_data, rocket_params, vehicle_sources)
        except OpenRocketExportDataError as hata:
            # Kapalı-form kestirim için eksik alan var; zaman-adımlı çözüm
            # yine de koşabilir (Isp'ye ihtiyacı yok). Özet uydurulmaz.
            flight_performance = None
            _flight_performance_error = str(hata)
        else:
            _flight_performance_error = None

        # Generate trajectory points
        burn_time = _finite_positive(motor_data.get('burn_time')) or \
            float(thrust_curve[-1][0])

        # İtki eğrisi ARA-DEĞERLENİR. Eski kod `abs(t_curve - t) < 0.01`
        # toleransıyla eşleşme arıyordu; zaman ızgaraları uyuşmadığı için
        # adımların çoğunda itki 0 alınıyor ve yörünge anlamsız çıkıyordu
        # (2026-07-19 denetimi: 200 adımın yalnız 13'ünde itki eşleşiyordu).
        curve_t = np.array([p[0] for p in thrust_curve], dtype=float)
        curve_f = np.array([p[1] for p in thrust_curve], dtype=float)
        order = np.argsort(curve_t)
        curve_t, curve_f = curve_t[order], curve_f[order]
        curve_end = float(curve_t[-1]) if curve_t.size else 0.0

        # Zaman ızgarası: yanma fazını yeterince örnekle (burnout'a kadar en az
        # 200 adım), sonra süzülüş fazını ekle.
        n_steps = 600
        flight_time = max(burn_time * 3.0, curve_end * 1.5)
        time_points = np.linspace(0.0, flight_time, n_steps)

        altitude_points = []
        velocity_points = []
        acceleration_points = []
        thrust_points = []

        # Araç alanları resolve_vehicle'dan gelir; eksikse ÖRNEK aracın değeri
        # kullanılır ve bu çıktıda beyan edilir (`vehicle_is_exporter_example`).
        dry_mass = (_finite_positive(rocket_params.get('dry_mass'))
                    or EXPORTER_EXAMPLE_VEHICLE['dry_mass'])
        diameter_m = (_finite_positive(rocket_params.get('diameter'))
                      or EXPORTER_EXAMPLE_VEHICLE['diameter'])
        # prop_mass yukarıda çözüldü ve None ise fonksiyon çoktan döndü;
        # burada `or 0.0` yedeği YOK (0 kg itici uydurması ZERO-PAT-8'di).
        current_velocity = 0.0
        current_altitude = 0.0
        mass = dry_mass + prop_mass
        # Kütle akışı gerçek eğrinin toplam impulsuna orantılı tüketilir.
        total_impulse_curve = float(np.trapz(curve_f, curve_t)) if curve_t.size > 1 else 0.0
        ref_area = np.pi * (diameter_m / 2.0) ** 2
        cd = (_finite_positive(rocket_params.get('drag_coefficient'))
              or EXPORTER_EXAMPLE_VEHICLE['drag_coefficient'])
        landed = False

        for i, t in enumerate(time_points):
            thrust = float(np.interp(t, curve_t, curve_f, left=0.0, right=0.0)) \
                if curve_t.size else 0.0

            weight = mass * G_0
            rho = _air_density(current_altitude)
            # Sürükleme HER ZAMAN hareketin tersine etki eder: v*|v| işareti
            # taşır (eski kod v**2 kullandığı için iniş fazında sürükleme
            # aşağı yönde ekleniyordu).
            drag = 0.5 * rho * cd * ref_area * current_velocity * abs(current_velocity)

            net_force = thrust - weight - drag
            acceleration = net_force / mass if mass > 0 else -G_0

            if landed:
                acceleration = 0.0

            if i > 0 and not landed:
                dt = float(time_points[i] - time_points[i - 1])
                current_velocity += acceleration * dt
                current_altitude += current_velocity * dt

                # İtici tüketimi: anlık impuls payıyla orantılı
                if total_impulse_curve > 0.0 and thrust > 0.0:
                    mass = max(dry_mass,
                               mass - prop_mass * (thrust * dt) / total_impulse_curve)

                if current_altitude <= 0.0:
                    current_altitude = 0.0
                    current_velocity = 0.0
                    landed = True

            altitude_points.append(max(0.0, current_altitude))
            velocity_points.append(current_velocity)
            acceleration_points.append(acceleration)
            thrust_points.append(thrust)

        return {
            'status': 'ok',
            'time_data': time_points.tolist(),
            'altitude_data': altitude_points,
            'velocity_data': velocity_points,
            'acceleration_data': acceleration_points,
            'thrust_data': thrust_points,
            'thrust_curve': thrust_curve,
            'thrust_curve_source': THRUST_SOURCE_LABELS.get(thrust_source, thrust_source),
            'performance_summary': flight_performance,
            'performance_summary_error': _flight_performance_error,
            'max_altitude': max(altitude_points),
            # İki apoje sayısı aynı yanıtta dönüyor; hangisinin hangi modelden
            # geldiği artık açıkça yazılı (denetim bulgusu: 134x fark).
            'max_altitude_method': (
                ('EXAMPLE VEHICLE (not the user rocket) - ' if ornek_arac else '')
                + '1-DOF time-marched integration with ISA drag, using the '
                  'thrust curve above'),
            'max_velocity': max(velocity_points),
            'max_acceleration': max(acceleration_points),
            'flight_time': float(time_points[-1]),
            'burnout_time': burn_time,
            # Aracın hangi alanının kimden geldiği sayının yanında taşınır
            # (bulgu A12/b): apoje bir araç iddiasıdır, motor iddiası değil.
            'rocket_parameters': rocket_params,
            'rocket_parameters_source': vehicle_sources,
            'rocket_parameters_source_labels':
                self._vehicle_source_labels(vehicle_sources),
            'vehicle_is_exporter_example': ornek_arac,
        }

    def create_simulation_file(self, motor_data: Dict, rocket_data: Dict = None,
                               launch_params: Dict = None) -> str:
        """Create OpenRocket simulation file content.

        Motor kritik alanları eksikse ``OpenRocketExportDataError`` yükselir —
        .eng ile aynı kapı (bulgu A12, madde 3); çağıran uç bunu hata olarak
        kullanıcıya iletir.
        """

        # Araç varsayılanı BURADA kurulmaz: tek nokta resolve_vehicle'dır,
        # aksi hâlde XML ile JSON iki farklı araç görebilir (v2.6.26'da
        # rüzgârda tam olarak bu olmuştu).

        # Generate XML content for simulation
        simulation_data = self.create_flight_simulation_data(
            motor_data, rocket_data, launch_params)
        ork_template = self.create_ork_project_template(
            motor_data, rocket_data, launch_params)

        return ork_template