"""
OpenRocket Integration Module
Export motor data to OpenRocket .eng format and create flight simulation files
"""

import math
import numpy as np
# ÖH D26 / OH-D25-14: ``np.trapz`` NumPy 2.0'da ad alanından
# KALDIRILDI (np.trapezoid); ad TEK YERDE çözülür.
from hrma.utils.numeric_compat import trapezoid as _trapezoid
import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from hrma.constants import G_0, M_AIR, R_STAR_ICAO, isa_pressure, isa_temperature
from hrma.utils.input_guard import finite_number, finite_positive

# ---------------------------------------------------------------------------
# .eng (RASP) üretim sabitleri — TEK tanım noktası (CLAUDE.md kural 11).
# ---------------------------------------------------------------------------
# RASP formatı eğrinin sıfır itkiyle bitmesini ister. Bu son nokta bir FORMAT
# sonlandırıcısıdır, modellenmiş bir sönme rampası DEĞİLDİR; toplam impulsu
# etkilemesin diye çok kısa tutulur.
ENG_ZERO_TERMINATOR_DT_S = 0.01
# OpenRocket için yeterli çözünürlük (gerçek eğri bundan uzunsa seyreltilir).
ENG_MAX_SAMPLES = 100

# RASP motor satırının YAZILAN alan hassasiyeti — TEK tanım noktası.
# Motor satırı bu ondalıklarla biçimlenir ve A12 kapısı da bunu okur:
# dosyaya giren sayı, YAZILDIĞI HÂLİYLE sıfıra yuvarlanıyorsa o dosya
# kodun kendi yasakladığı yer tutucu motordur (ÖH D16 / P16B4-15).
ENG_HEADER_DECIMALS = {
    'diameter_mm': 1,
    'length_mm': 1,
    'propellant_mass_kg': 3,
    'loaded_mass_kg': 3,
}

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
#     M0-HRMA-001 0.0 500.0 P 1.000 1.000 HRMA
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
    # ÖH Z5S / P9B3-16: hibrit çözücü TESLİM EDİLEN impulsu ayrı bir alanda
    # yayımlıyor (``total_impulse_delivered_Ns`` = kendi eğrisinin integrali)
    # ve bu modülde o alana HİÇ atıf yoktu. Ölçüm (27 Ağustos 2026, gerçek
    # hibrit sonucu): total_impulse = 20000,0 N·s (istenen), delivered =
    # 19950,385 N·s, dosyaya yazılan eğrinin integrali = 19960,339 N·s.
    'total_impulse_delivered_Ns': ('total_impulse_delivered_Ns reported by the '
                                   'solver (the impulse the burn actually '
                                   'produced)'),
    'curve_integral': 'integral of the time-resolved thrust curve',
    'thrust_x_burn_time': 'average thrust x burn time',
    'none': 'total impulse NOT available',
}

# ---------------------------------------------------------------------------
# RASP AD ALANI (ÖH Z5S / P9B3-18)
# ---------------------------------------------------------------------------
# RASP motor satırı BOŞLUKLA ayrılmış 7 alandır ve motor adı doğrudan 1. alana
# giriyordu. ÖLÇÜLDÜ (27 Ağustos 2026, gerçek hibrit sonucu): ``'My Motor'``
# adı satırı 8 alana, ``'HRMA HRM 001'`` 9 alana çıkarıyor; addaki bir
# satır sonu ise dosyaya BAŞIBOŞ bir satır sokup motor satırını 1 alana
# düşürüyordu. OpenRocket böyle bir dosyayı ya reddeder ya da alanları
# kaydırarak okur (çap alanına adın ikinci kelimesi düşer).
#
# Kural: ad SİLİNMEZ ve UYDURULMAZ; yalnız RASP'ın istediği tek parçaya
# indirilir (boşluk -> '_') ve değiştirildiyse .eng yorum satırında BEYAN
# edilir — okuyan kişi dosyadaki adın kendi yazdığı ad olmadığını görür.
MOTOR_NAME_WHITESPACE_REPLACEMENT = '_'

# ---------------------------------------------------------------------------
# GECİKME SONEKİ (UI openrocket-kose 2. tur, devir D2; 7 Ekim 2026)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (kurulu OpenRocket 24.12, kendi RASPMotorLoader'ı, başsız kip):
# varsayılan ad 'HRMA-001' ile yazılan 'O167-HRMA-001' künyesi OpenRocket'te
# 'O167-HRMA' olarak okundu. Neden: OpenRocket künyenin sonundaki
# '-<rakamlar>' ya da '-P' parçasını GECİKME sanıp keser.
#   info.openrocket.core.file.motor.AbstractMotorLoader.removeDelay
#   (OpenRocket-24.12.jar, javap ile okundu): value.matches(".*-([0-9]+|[pP])$")
#   ise value.substring(0, value.lastIndexOf('-')).
# Künye '<sınıf><sayı>-<ad>' olduğu için kural adın kendisine de uygulanır:
# ad '-001' ile bitiyorsa ya da tamamı '001' / 'P' ise OpenRocket o parçayı
# siler. Ad bu yüzden son ayırıcısı '_' olacak biçimde yazılır ve değişiklik
# .eng yorumunda BEYAN edilir (P9B3-18 deseni).
#: Gecikme sanılan sonekin önündeki ayırıcının yerine yazılan karakter.
MOTOR_NAME_DELAY_SEPARATOR_REPLACEMENT = '_'
#: OpenRocket'in gecikme saydığı sonek: yalnız ASCII rakamlar ya da tek 'P'/'p'
#: (Java düzenli ifadesindeki ``[0-9]+|[pP]``).
OPENROCKET_DELAY_DIGITS = '0123456789'
OPENROCKET_DELAY_PLUGGED = ('P', 'p')
#: Ad verilmediğinde yazılan ad. Eski 'HRMA-001' OpenRocket'te 'HRMA'ya
#: kırpılıyordu (yukarıdaki ölçüm); bu ad kırpılmaz.
DEFAULT_MOTOR_NAME = 'HRMA_001'


def _openrocket_delay_suffix(name: str) -> Optional[str]:
    """Künyede adın ardından OpenRocket'in GECİKME diye keseceği parça.

    Künye ``<önek>-<ad>`` biçimindedir; ad '-' içermiyorsa son parça adın
    tamamıdır. Döner: kesilecek parça ya da ``None``.
    """
    son = name.rsplit('-', 1)[-1]
    if son in OPENROCKET_DELAY_PLUGGED:
        return son
    if son and all(c in OPENROCKET_DELAY_DIGITS for c in son):
        return son
    return None


def _sanitize_motor_name(raw) -> Tuple[str, Optional[str]]:
    """Motor adını RASP'ın tek parçalı ad alanına indirger.

    İki kural, ikisi de beyanlı:
      * boşluk -> '_' (RASP ad alanı tek parçadır; P9B3-18);
      * künyenin sonunda OpenRocket'in gecikme sanıp keseceği '-<rakamlar>'
        ya da '-P' kalmaz: son ayırıcı '_' olur, ad '-' içermiyorsa başına
        '_' eklenir (devir D2).

    Döner: ``(temiz_ad, beyan|None)``. Beyan yalnız ad GERÇEKTEN değiştiyse
    doludur; dokunulmayan adlarda dosya bit-aynı kalır.
    """
    metin = '' if raw is None else str(raw)
    temiz = MOTOR_NAME_WHITESPACE_REPLACEMENT.join(metin.split())
    nedenler = []
    if temiz != metin:
        nedenler.append(
            f'the RASP name field is a single whitespace-separated token and '
            f'the supplied name {metin!r} would have split the motor line '
            f'into a different number of fields')
    sonek = _openrocket_delay_suffix(temiz)
    if sonek is not None:
        govde = temiz[:len(temiz) - len(sonek)]
        if govde.endswith('-'):
            kirpilmis = govde[:-1]
            temiz = kirpilmis + MOTOR_NAME_DELAY_SEPARATOR_REPLACEMENT + sonek
        else:
            kirpilmis = ''
            temiz = MOTOR_NAME_DELAY_SEPARATOR_REPLACEMENT + temiz
        nedenler.append(
            f"OpenRocket's motor loader reads a trailing '-<digits>' or '-P' "
            f"in the designation as an ejection delay and cuts it off "
            f"(AbstractMotorLoader.removeDelay, OpenRocket 24.12), so the "
            f"name would have been read as {kirpilmis!r}")
    if not nedenler:
        return temiz, None
    return temiz, f'motor name written as {temiz!r} - ' + '; '.join(nedenler)

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
    # ÖH D15 / harita H1a: beyanla çözülen geometri ile çıkarımla çözülen
    # geometri AYNI künyeyi taşıyamaz. Çıkarım bir tahmindir ve eşiği aşan
    # motorlarda ters döner (ölçüldü: 17,318 m kamara -> 17,3 mm); beyan
    # tahmin değildir. Dosyayı okuyan bunları ayırt edebilmelidir.
    'declared': ('top-level results with a length_units declaration '
                 '(no unit inference)'),
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
# .ork şablonundaki gövde borusu et kalınlığı — TEK tanım noktası
# (CLAUDE.md kural 11). Motor yuvasının gövdeye SIĞIP sığmadığı bu sayıdan
# hesaplanır; iki yerde iki farklı kalınlık dolaşmasın (ÖH Z5S / P9B3-15).
ORK_BODY_TUBE_WALL_M = 0.005

#: .ork şablonunun ÖRNEK yapı geometrisi/malzemeleri — TEK TANIM NOKTASI.
#:
#: ÖH D15 / defter P9B3-14 — ÖLÇÜLEN KUSUR. XML bu 12 sayıyı kullanıcının
#: GERÇEK aracı verildiğinde bile BEYANSIZ yazıyordu: dosyanın adı
#: kullanıcınınkiydi (``<name>BERKE-1</name>``) ve XML'deki yorumlar yalnız
#: çap/boy/rüzgâr/rampa için vardı. OpenRocket ağırlık merkezini, kararlılık
#: payını ve apojeyi tam da bu sayılardan hesaplar; kullanıcı kendi roketini
#: açtığını sanırken uydurma bir burun konisi ve kanat takımıyla uçuş
#: simülasyonu koşuyordu. Modül aynı dosyada çap/boy için
#: ``EXAMPLE value ... it is NOT your rocket`` notunu basmayı ZATEN biliyordu.
#:
#: Sözlük hem değeri hem de XML'e düşecek beyan metnini taşır. Çağıran
#: ``rocket_params`` içinde aynı adla bir değer verirse O KULLANILIR ve o
#: alan için beyan basılmaz (beyan kazanılarak kaldırılabilir).
ORK_EXAMPLE_STRUCTURE = {
    'nose_shape': ('OGIVE', 'nose cone shape'),
    'nose_length': (0.3, 'nose cone length [m]'),
    'nose_material': ('Fiberglass', 'nose cone material'),
    'nose_density': (500.0, 'nose cone material density [kg/m3]'),
    'nose_thickness': (0.003, 'nose cone wall thickness [m]'),
    'body_material': ('Phenolic', 'body tube material'),
    'body_density': (700.0, 'body tube material density [kg/m3]'),
    'mount_material': ('Steel', 'motor mount material'),
    'mount_density': (7850.0, 'motor mount material density [kg/m3]'),
    'mount_thickness': (0.005, 'motor mount wall thickness [m]'),
    'fin_root_chord': (0.15, 'fin root chord [m]'),
    'fin_tip_chord': (0.05, 'fin tip chord [m]'),
    'fin_height': (0.1, 'fin span (height) [m]'),
    'fin_sweep_angle': (45.0, 'fin sweep angle [deg]'),
    'fin_material': ('Fiberglass', 'fin material'),
    'fin_density': (500.0, 'fin material density [kg/m3]'),
    'fin_thickness': (0.003, 'fin thickness [m]'),
}

#: ``ORK_BODY_TUBE_WALL_M`` de beyan edilir; değeri yukarıdaki tabloda
#: TEKRARLANMAZ, sabitin kendisinden okunur.
ORK_EXAMPLE_BODY_WALL_LABEL = 'body tube wall thickness [m]'

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
#
# Faz 5B / H4-2: eşikler burada tanımlıydı ve dışa aktarımın geri kalanı
# (DXF, teknik çizim PDF'i, STEP, STL, rapor PDF'i) bu çözümden habersizdi —
# her biri kendi varsayımıyla çalışıyordu. Tek tanım noktası artık
# ``motor_geometry`` (CLAUDE.md kural 11); buradaki adlar geri uyum için
# korunur ve oradan içe aktarılır.
from hrma.export.motor_geometry import (  # noqa: E402
    DIAMETER_SI_MAX_M, LENGTH_SI_MAX_M, THICKNESS_SI_MAX_M,
    length_in_meters as _length_in_meters_shared,
    resolve_length_m as _resolve_length_m_shared)
# ÖH D15 / P9B3-11: itici yoğunluk bandı deponun katalog doğrulayıcısıyla
# AYNI demettir; ikinci bir sayı yazılmaz.
from hrma.data.propellants_db import (  # noqa: E402
    PROPELLANT_DENSITY_RANGE_KG_M3)

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
    Gövde ``motor_geometry.length_in_meters``tir — TEK tanım noktası.
    """
    return _length_in_meters_shared(value, si_max)


def _nested(data, *path):
    """İç içe sözlükten güvenli okuma; ara düğüm sözlük değilse None."""
    node = data
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


# ---------------------------------------------------------------------------
# İKİ-FAZ (PARTİKÜL GECİKMESİ) DÜZELTME DURUMU — ÖH D33 / OH-D32-10
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (``docs/scofield/raw/OH/D33/ihracat/a1/once.json`` K2, taban
# ``56f88e70``): katı motorun ``/calculate_solid`` gövdesi iki-faz düzeltme
# DURUMUNU iki yerde yayımlıyor
# (``detailed_analysis.performance_metrics.theoretical_vs_actual_isp`` ve
# ``two_phase_loss``, değer ``not_applied_unverified``), ama AYNI yanıtın
# ihracat ucu teslim Isp'sini (243,68589734650317 s) hiçbir durum alanı
# olmadan aktarıyordu: ``export_motor_summary`` 0 alan, ``.eng`` künyesi
# 0 satır, ``create_flight_simulation_data`` 0 alan. Hibrit ve sıvıda ise
# çözücü hiç durum yayımlamıyor ve ihracat yine Isp teslim ediyordu
# (226,0777826151255 s / 259,79323443105085 s).
#
# Durumun TANIM NOKTASI çözücüdedir
# (``hrma.engines.solid_rocket_engine._two_phase_correction_state``, ÖH D32 /
# OH-D31-17); burada İKİNCİ bir durum TÜRETİLMEZ — yalnız OKUNUR ve teslim
# yüzeyine taşınır. Okunamıyorsa sessizce "düzeltme uygulanmış" ya da
# "gerekmiyor" VARSAYILMAZ: eksikliğin kendisi adıyla beyan edilir
# (fail-closed, doktrin 1).

#: Çözücünün durumu yayımladığı yollar — TEK arama listesi. ``.eng``
#: künyesi, motor özeti ve uçuş verisi AYNI listeden okur (doktrin 4).
TWO_PHASE_STATE_PATHS = (
    ('detailed_analysis', 'performance_metrics', 'theoretical_vs_actual_isp'),
    ('two_phase_loss',),
    ('performance_metrics', 'theoretical_vs_actual_isp'),
    ('results', 'two_phase_loss'),
    ('results', 'detailed_analysis', 'performance_metrics',
     'theoretical_vs_actual_isp'),
)

#: Durum sözlüğünün alan adları — çözücüyle AYNI adlar (yeniden adlandırma
#: yok; panel/PDF/API ile ihracat aynı anahtarı okur).
TWO_PHASE_STATUS_FIELD = 'two_phase_correction_status'
TWO_PHASE_VERIFIED_FIELD = 'two_phase_correction_verified'
TWO_PHASE_BASIS_FIELD = 'two_phase_correction_status_basis'

#: Çözücü hiçbir durum yayımlamadığında ihracat yüzeyinin BEYANI. Bu bir
#: "sorun yok" hâli DEĞİLDİR: teslim edilen Isp'nin iki-faz düzeltmesi
#: taşıyıp taşımadığı BİLİNMİYOR demektir (panelin 'NOT PUBLISHED BY THE
#: SOLVER' bandıyla aynı hüküm).
TWO_PHASE_STATUS_NOT_PUBLISHED = 'not_published_by_the_solver'


def _two_phase_path_label(path) -> str:
    return '.'.join(path)


#: RASP başlığının ima ettiği bulk itici yoğunluğunun fiziksel ÜST sınırı
#: (kg/m^3). Sayı burada YENİDEN YAZILMAZ: deponun itici katalog
#: doğrulayıcısının kullandığı bandın üst ucudur (ÖH D15 / P9B3-11).
PROPELLANT_DENSITY_MAX_KG_M3 = PROPELLANT_DENSITY_RANGE_KG_M3[1]


def _finite_positive(value) -> Optional[float]:
    """Sonlu ve pozitif float döndürür; aksi halde None.

    Kural merkezden okunur (``input_guard.finite_positive``, ÖH D28 /
    OH-D27-11). Eski gövde ``bool``u eliyemiyordu ve ölçüldü ki
    ``resolve_eng_inputs({'case_diameter': True})`` alanı "eksik" saymak
    yerine ``.eng`` künyesine uydurma **1,0 m** gövde çapı yazıyordu.
    """
    return finite_positive(value)


def _finite_number(value) -> Optional[float]:
    """Sonlu float döndürür — 0 ve negatif DAHİL; aksi halde None.

    Fırlatma koşulları için gerekli: kullanıcının yazdığı 0 m/s rüzgâr geçerli
    bir girdidir ("sakin hava") ve `_finite_positive` onu eleyip "veri yok"
    ile karıştırırdı. İkisi ayrı şeydir: veri yok -> None, kullanıcı 0 yazdı
    -> 0.0.
    """
    return finite_number(value)


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
    
    @staticmethod
    def resolve_two_phase_correction(motor_data: Dict) -> Dict:
        """Teslim edilen Isp'nin iki-faz düzeltme DURUMU — okunur, türetilmez.

        ÖH D33 / OH-D32-10. Çözücünün yayımladığı durum
        (``hrma.engines.solid_rocket_engine._two_phase_correction_state``,
        tek tanım noktası) :data:`TWO_PHASE_STATE_PATHS` sırasıyla aranır ve
        BULUNDUĞU YOL adıyla döner. Hiçbir yolda yoksa durum
        :data:`TWO_PHASE_STATUS_NOT_PUBLISHED` olur ve künye hangi yolların
        arandığını ADIYLA söyler — "düzeltme uygulandı" ya da "gerekmiyor"
        SESSİZCE varsayılmaz (fail-closed, doktrin 1).

        ``two_phase_correction_verified`` yalnız çözücü ``True`` yayımlarsa
        ``True``dur; okunamayan durumda ``False``tur ("bilinmiyor" bir
        doğrulama değildir).
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        for path in TWO_PHASE_STATE_PATHS:
            blok = _nested(md, *path)
            if not isinstance(blok, dict):
                continue
            durum = blok.get(TWO_PHASE_STATUS_FIELD)
            if not isinstance(durum, str) or not durum:
                continue
            kunye = blok.get(TWO_PHASE_BASIS_FIELD)
            return {
                TWO_PHASE_STATUS_FIELD: durum,
                TWO_PHASE_VERIFIED_FIELD: bool(
                    blok.get(TWO_PHASE_VERIFIED_FIELD) is True),
                TWO_PHASE_BASIS_FIELD: (
                    kunye if isinstance(kunye, str) and kunye else
                    'the solver published the status but no basis text'),
                'two_phase_correction_source': _two_phase_path_label(path),
            }
        aranan = ', '.join(_two_phase_path_label(p)
                           for p in TWO_PHASE_STATE_PATHS)
        return {
            TWO_PHASE_STATUS_FIELD: TWO_PHASE_STATUS_NOT_PUBLISHED,
            TWO_PHASE_VERIFIED_FIELD: False,
            TWO_PHASE_BASIS_FIELD: (
                'This result publishes NO two-phase (particle-lag) correction '
                'status, so the specific impulse handed over by this export '
                'carries an UNKNOWN two-phase correction state: it is not '
                'known whether a correction was applied, and no correction is '
                'assumed here. Do not read the exported Isp (or the total '
                'impulse / propellant mass pair that implies it) as a '
                'verified delivered-performance claim. searched: '
                + aranan + '.'),
            'two_phase_correction_source': None,
        }

    @classmethod
    def _two_phase_comment_lines(cls, motor_data: Dict) -> List[str]:
        """``.eng`` künyesinin iki-faz satırları — özetle AYNI çözücüden.

        RASP tüketicileri yorum satırını yok sayar; bu yüzden aynı hüküm
        ``motor_summary`` ve ``flight_profile`` içinde MAKİNE-OKUR olarak da
        durur (``eng_envelope_warning`` için verilen kararın aynısı).
        """
        durum = cls.resolve_two_phase_correction(motor_data)
        satir = [
            '; two-phase (particle-lag) correction of the delivered Isp: '
            '%s (verified=%s)' % (durum[TWO_PHASE_STATUS_FIELD],
                                  durum[TWO_PHASE_VERIFIED_FIELD])]
        kaynak = durum.get('two_phase_correction_source')
        if kaynak:
            satir.append(';   status read from: %s' % kaynak)
        # RASP yorumu TEK SATIRDIR: künye metnindeki bir satır sonu ikinci
        # satırı ';' ile başlamayan bir gövde satırına çevirirdi ve dosyayı
        # ayrıştırılamaz yapardı. Metin sıkıştırılır, kırpılmaz.
        kunye = ' '.join(str(durum[TWO_PHASE_BASIS_FIELD]).split())
        satir.append(';   %s' % kunye)
        return satir

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

        # ÖH D36 / LU-1 + LU-2: sıvı çözücü yanma süresi verilmediğinde
        # ``burn_time`` / ``propellant_mass_kg`` YAYIMLAMAZ ve bunu
        # ``burn_time_source = 'not_supplied'`` ile ADIYLA söyler. Üç eksik
        # alanın ortak kökü o zaman bu beyandır; kullanıcı "itici kütlesi
        # çözülemedi" okuyup nedenini tahmin etmek zorunda kalmasın diye kök
        # alan listenin başına kendi gerekçesiyle konur. Sayı üretilmez;
        # yalnız neden adlandırılır (kapı zaten kapalıdır).
        if (missing and str(md.get('burn_time_source') or '') == 'not_supplied'
                and set(missing) & {'propellant_mass', 'total_impulse',
                                    'thrust_curve'}):
            missing.insert(0, 'burn_time')
            reasons['burn_time'] = (
                'the solver declared burn_time_source = "not_supplied": no '
                'burn time was entered (max_burn_duration is empty) and none '
                'is assumed, so the propellant mass, the total impulse and '
                'the constant-thrust curve cannot be derived. Enter the '
                'burn time and recalculate.')

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

    def export_motor_file(self, motor_data: Dict, filename: str = None,
                          report: Dict = None) -> str:
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
            resolved=resolved, report=report
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

    @staticmethod
    def motor_mount_fit(mount_radius_m, vehicle: Dict,
                        vehicle_sources: Dict = None) -> Dict:
        """Motor yuvası gövde borusuna SIĞIYOR MU? (ÖH Z5S / P9B3-15)

        ÖLÇÜLDÜ (27 Ağustos 2026, üç gerçek sonuç): .ork şablonu motor
        yuvasının dış yarıçapını kasa çapından yazıyor, gövde borusunu ise
        araçtan (araç verilmediyse ÖRNEK araçtan, Ø0,10 m) — ve ikisini
        karşılaştıran hiçbir kapı yoktu:

            hibrit yuva R = 0,0623 m,  gövde iç R = 0,0450 m -> SIĞMIYOR
            katı   yuva R = 0,0822 m,  gövde iç R = 0,0450 m -> SIĞMIYOR
            sıvı   yuva R = 0,0747 m,  gövde iç R = 0,0450 m -> SIĞMIYOR

        OpenRocket böyle bir projeyi açar ve motoru gövdenin içindeymiş gibi
        simüle eder. Sayı DEĞİŞTİRİLMEZ (gövdeyi büyütmek kullanıcının aracını
        UYDURMAK olurdu); çelişki ADIYLA beyan edilir.

        Döner: ölçüm sözlüğü (``fits`` çözülemiyorsa None).
        """
        sources = vehicle_sources or {}
        mount_r = _finite_positive(mount_radius_m)
        body_r = _finite_positive((vehicle or {}).get('diameter'))
        body_r = body_r / 2.0 if body_r is not None else None
        body_inner_r = (body_r - ORK_BODY_TUBE_WALL_M
                        if body_r is not None else None)
        fits = None
        if mount_r is not None and body_inner_r is not None:
            fits = bool(mount_r <= body_inner_r)
        return {
            'fits': fits,
            'mount_outer_radius_m': mount_r,
            'body_tube_outer_radius_m': body_r,
            'body_tube_wall_m': ORK_BODY_TUBE_WALL_M,
            'body_tube_inner_radius_m': body_inner_r,
            'clearance_m': (None if fits is None else body_inner_r - mount_r),
            'body_tube_source': sources.get('diameter'),
            'body_tube_is_exporter_example':
                sources.get('diameter') == 'exporter_example',
        }

    @classmethod
    def _motor_mount_fit_notes(cls, fit: Dict) -> List[str]:
        """Yuva/gövde ölçümünü .ork yorum satırlarına çevirir."""
        if fit.get('fits') is None:
            return ['motor mount fit NOT checked: the mount radius or the body '
                    'tube diameter could not be resolved']
        olcu = (f'motor mount outer radius {fit["mount_outer_radius_m"]:.4f} m '
                f'vs body tube inner radius {fit["body_tube_inner_radius_m"]:.4f} m '
                f'(outer {fit["body_tube_outer_radius_m"]:.4f} m minus '
                f'{fit["body_tube_wall_m"]:.4f} m wall)')
        if fit['fits']:
            return [f'motor mount FITS the body tube: {olcu}']
        notlar = [f'WARNING: THE MOTOR DOES NOT FIT THE BODY TUBE - {olcu}; '
                  f'the mount sticks out by '
                  f'{-fit["clearance_m"] * 1000.0:.1f} mm of radius']
        if fit['body_tube_is_exporter_example']:
            notlar.append('the body tube above is the EXAMPLE vehicle bundled '
                          'with the exporter, not your rocket - size the '
                          'airframe around the motor in OpenRocket')
        else:
            notlar.append('the body tube above is YOUR vehicle as supplied to '
                          'this export - this template is geometrically '
                          'inconsistent until one of the two is corrected')
        return notlar

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
            # ÖH D33 / OH-D32-10 — apoje/Δv kestirimi Isp ile yapılır
            # (``_calculate_flight_performance``); o Isp'nin iki-faz düzeltme
            # durumu uçuş verisinde de MAKİNE-OKUR olarak durur.
            'two_phase_correction': self.resolve_two_phase_correction(
                motor_data),
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

    # --- ÖH D24 / defter P9B3-24: ÖLÜ İKİZ SİLİNDİ -------------------------
    #
    # Burada 93 satırlık bir ``generate_technical_report(motor_data)`` vardı.
    # ÖLÇÜLDÜ (``a2/once.json`` -> ``M1_P9B3_24``, taban 88a29d3):
    #
    #   ürün kodunda çağıran        : 0
    #   uydurma varsayılan          : 4  (chamber_pressure, of_ratio,
    #                                     c_star, cf -> ``get(ad, 0)``)
    #   koşulsuz "✓" onayı          : 4
    #
    # Boş bir gövdeyle çağrıldığında bastığı satırlar (ölçülen çıktı)::
    #
    #     Chamber Pressure: 0.0 bar
    #     O/F Ratio: 0.00
    #     C* Efficiency: 0 m/s          <- KARAKTERİSTİK HIZ, VERİM DEĞİL
    #     Thrust Coefficient: 0.000
    #     ✓ .eng file format supported  (dördü de koşulsuz)
    #
    # İki ayrı yalan taşıyordu:
    #   1. ``c_star`` [m/s] "C* Efficiency" başlığıyla basılıyordu. Deponun
    #      CANLI yüzü (``templates/solid.html``) bu adı doğru büyüklüğe
    #      bağlıyor: ``c_star_efficiency_percent`` [%]. Aynı ad, iki farklı
    #      büyüklük.
    #   2. Dört uyumluluk satırı, .eng üretimi hiç denenmeden "✓" işaretliydi.
    #
    # Ad, ``pdf_generator.PDFReportGenerator.generate_technical_report``
    # (CANLI, ``/api/generate-report`` üzerinden çağrılan) ile aynı olduğu
    # için tarama yaparken maskeleniyordu — savcının "ölü ikiz / ikiz ad
    # maskesi" hükmü. Sembolün 0 ürün çağıranı olduğu için düzeltmek yerine
    # SİLİNDİ: yalnız bekçisinin ayakta tuttuğu bir sembol kanıt üretmez
    # (aynı gerekçe: D24 a1 / P9B1-28, P9B1-30).
    #
    # Bekçi: tests/test_d24_ihracat_a2.py::TestP9B324OluIkiz
    # -----------------------------------------------------------------------

    def _get_motor_class(self, total_impulse) -> Optional[str]:
        """Toplam impulstan sınıf harfi. Aralık boşluğu ve sessiz 'A' YOK.

        ÖLÇÜLDÜ (ÖH Z5S / P9B3-17, onarım öncesi koşum): tablodaki aralıklar
        birbirine DEĞMİYOR — A (1,26–2,50), B (2,51–5,00), ... arasındaki her
        boşluğa düşen impuls metodun son satırındaki ``return 'A'`` ile
        sessizce A sınıfı oluyordu:

            2,505 N·s -> 'A'      5,005 N·s -> 'A'      20 480,005 N·s -> 'A'
            0,0 N·s   -> 'A'     -5,0 N·s   -> 'A'      NaN            -> 'A'

        Yani 20 kN·s'lik bir motor 2,5 N·s'lik bir oyuncakla aynı harfi
        alıyordu ve bu harf hem ``_designation`` üzerinden .eng/.ork dosya
        adına hem de API yanıtındaki ``motor_class`` alanına gidiyordu.

        Onarım YENİ SAYI ÜRETMEZ: boşluklar tablonun KENDİ üst sınırlarıyla
        kapatılır. Üst sınırlar tam ikiye katlanan 2,5·2ⁿ dizisidir; alt
        sınırlar ise bunların 0,01'lik yuvarlama gösterimidir (2,51 = 2,50'nin
        "hemen üstü"). Bu yüzden sınıflandırma yarı açık aralıkla yapılır:
        ``önceki_üst < I <= üst``.

        Tablonun KAPSAMADIĞI yerde harf iddia edilmez (fail-closed):
          * sonlu olmayan / tablonun A alt sınırının altındaki impuls -> None
            (NAR'ın 1/2A, 1/4A sınıfları bu tabloda taşınmıyor; "A" demek
            ölçülmemiş bir iddiadır),
          * O'nun üstü -> 'P+' ("P ve üzeri"; tablo orada bitiyor, tek bir
            harf uydurulmaz — bu davranış değişmedi).
        """
        impulse = _finite_number(total_impulse)
        if impulse is None:
            return None
        taban = min(low for low, _high in self.motor_classes.values())
        if impulse < taban:
            return None
        for motor_class, (_low, high) in sorted(self.motor_classes.items(),
                                                key=lambda kv: kv[1][1]):
            if impulse <= high:
                return motor_class
        return 'P+'

    def motor_class_range(self, motor_class: Optional[str]):
        """Bir sınıf harfinin tablodaki aralığı; bilinmeyen harfte ``None``.

        Sınıf harfi .eng dosyasında bir İDDİADIR; okuyan kişi harfin hangi
        impuls aralığını temsil ettiğini dosyanın içinde görebilmeli.
        """
        aralik = self.motor_classes.get(motor_class or '')
        return tuple(aralik) if aralik else None

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
            mean = float(_trapezoid(np.clip(f_real, 0.0, None), t_real)) / span
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

        # ÖH Z5S / P9B3-16: çözücünün TESLİM EDİLEN impulsu. Bu alan modülde
        # hiç okunmuyordu; eğri integralinden ÖNCE gelir, çünkü çözücünün
        # kendi zaman-adımlı çözümünden gelir (RASP için seyreltilmiş
        # örneklemenin integralinden daha doğrudur).
        delivered = _finite_positive(md.get('total_impulse_delivered_Ns'))
        if delivered is not None:
            return delivered, 'total_impulse_delivered_Ns'

        t_real, f_real, _src = cls.real_thrust_curve(md)
        if t_real is not None:
            integral = float(_trapezoid(np.clip(f_real, 0.0, None), t_real))
            if np.isfinite(integral) and integral > 0.0:
                return integral, 'curve_integral'

        avg_thrust, _tsrc = cls.resolve_average_thrust(md)
        burn_time = _finite_positive(md.get('burn_time'))
        if avg_thrust is not None and burn_time is not None:
            return avg_thrust * burn_time, 'thrust_x_burn_time'

        return None, 'none'

    def impulse_audit(self, motor_data: Dict,
                      thrust_curve: List[Tuple[float, float]] = None) -> Dict:
        """Başlığa yazılan impuls ile DOSYAYA YAZILAN eğriyi karşılaştırır.

        İki kalemin ortak ölçüm noktası (ÖH Z5S):

        * **P9B3-16** — sınıf harfi ``total_impulse``tan geliyor, OpenRocket
          ise dosyanın ALTINDAKİ eğriyi simüle ediyor. Ölçüldü (gerçek hibrit
          sonucu, 27 Ağustos 2026): başlık 20 000,0 N·s, çözücünün teslim
          ettiği 19 950,385 N·s, yazılan eğrinin integrali 19 960,339 N·s.
          Üçü de dosyada yoktu; yalnız birincisi vardı.
        * **P9B3-27** — negatif itki örnekleri hem eğriye hem integrale
          BEYANSIZ sıfır olarak giriyordu (``np.clip(f, 0, None)`` ve
          ``max(0.0, ...)``), dosya yine de kaynağını "integral of the
          time-resolved thrust curve" diye yazıyordu. Ölçüldü (aynı motor,
          son 12 örnek bilerek negatife çevrildi): ham integral 17 631,934
          N·s, kenetlenmiş integral 19 960,339 N·s.

        SAYI DEĞİŞTİRİLMEZ: kenetleme RASP biçiminin zorunluluğudur (negatif
        itki yazılamaz), integral de değiştirilmez. Değişen tek şey dosyanın
        SUSMASI: üç sayı da adıyla yazılır. EŞİK DE ÜRETİLMEZ — farklar her
        zaman yüzdesiyle basılır, UYARI ise yalnız KATEGORİK bir çelişkide
        (iki sayı farklı sınıf harfine düşüyorsa ya da negatif örnek
        kenetlendiyse) çıkar.

        Döner: ölçüm sözlüğü (hiçbir alan uydurulmaz; çözülemeyen None).
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        header, header_src = self.resolve_total_impulse(md)
        if thrust_curve is None:
            thrust_curve, _src = self.resolve_thrust_curve(md)

        t_real, f_real, curve_key = self.real_thrust_curve(md)
        negatif, en_negatif, ham, kenetli, ornek = 0, None, None, None, None
        if t_real is not None:
            maske = f_real < 0.0
            negatif = int(maske.sum())
            ornek = int(f_real.size)
            if negatif:
                en_negatif = float(f_real[maske].min())
            ham = float(_trapezoid(f_real, t_real))
            kenetli = float(_trapezoid(np.clip(f_real, 0.0, None), t_real))

        yazilan = None
        if thrust_curve:
            yazilan = float(_trapezoid([p[1] for p in thrust_curve],
                                     [p[0] for p in thrust_curve]))

        harf_baslik = self._get_motor_class(header)
        harf_yazilan = self._get_motor_class(yazilan)

        def _sapma(deger):
            if deger is None or header is None or header == 0.0:
                return None
            return (deger / header - 1.0) * 100.0

        basis = md.get('total_impulse_basis')
        return {
            'header_Ns': header,
            'header_source': header_src,
            'class_letter_header': harf_baslik,
            'class_letter_range_Ns': self.motor_class_range(harf_baslik),
            'delivered_Ns': _finite_positive(md.get('total_impulse_delivered_Ns')),
            'delivered_basis': (' '.join(str(basis).split()) if basis else None),
            'delivered_percent_vs_header':
                _sapma(_finite_positive(md.get('total_impulse_delivered_Ns'))),
            'written_curve_Ns': yazilan,
            'written_curve_percent_vs_header': _sapma(yazilan),
            'class_letter_written_curve': harf_yazilan,
            'class_letters_agree': (harf_baslik is not None
                                    and harf_baslik == harf_yazilan),
            'raw_curve_Ns': ham,
            'clamped_curve_Ns': kenetli,
            'curve_source': curve_key,
            'curve_samples': ornek,
            'negative_samples': negatif,
            'most_negative_N': en_negatif,
            'negative_samples_clamped': bool(negatif),
        }

    def _impulse_audit_lines(self, audit: Dict) -> List[str]:
        """``impulse_audit`` ölçümünü .eng yorum satırlarına çevirir."""
        lines: List[str] = []
        harf = audit.get('class_letter_header')
        aralik = audit.get('class_letter_range_Ns')
        if harf and aralik:
            lines.append(f'; class letter {harf} covers '
                         f'{aralik[0]:.2f}..{aralik[1]:.2f} N-s')
        elif audit.get('header_Ns') is not None:
            lines.append('; class letter NOT asserted: the resolved impulse is '
                         'outside this exporter\'s class table (it starts at '
                         'A and ends at O)')

        delivered = audit.get('delivered_Ns')
        if delivered is not None and audit.get('header_source') != \
                'total_impulse_delivered_Ns':
            sapma = audit.get('delivered_percent_vs_header')
            ek = f' ({sapma:+.3f}% vs the value above)' if sapma is not None else ''
            lines.append(f'; solver-reported delivered impulse = '
                         f'{delivered:.3f} N-s{ek}')
        if audit.get('delivered_basis'):
            lines.append('; delivered impulse basis (declared by the solver): '
                         + audit['delivered_basis'][:240])

        yazilan = audit.get('written_curve_Ns')
        if yazilan is not None:
            sapma = audit.get('written_curve_percent_vs_header')
            ek = f' ({sapma:+.3f}% vs the value above)' if sapma is not None else ''
            harf_y = audit.get('class_letter_written_curve')
            lines.append(f'; the thrust curve written below integrates to '
                         f'{yazilan:.3f} N-s{ek}'
                         + (f' -> class {harf_y}' if harf_y else ''))
            if not audit.get('class_letters_agree'):
                lines.append(
                    f'; WARNING: the class letter in the motor name comes from '
                    f'the header impulse ({harf or "none"}), but the curve '
                    f'written below falls in a DIFFERENT class '
                    f'({harf_y or "none"}) - OpenRocket simulates the CURVE, '
                    f'not the header value')

        if audit.get('negative_samples'):
            ham = audit.get('raw_curve_Ns')
            kenetli = audit.get('clamped_curve_Ns')
            lines.append(
                f'; WARNING: {audit["negative_samples"]} of the '
                f'{audit.get("curve_samples")} solved thrust samples are '
                f'NEGATIVE (most negative {audit["most_negative_N"]:.1f} N). '
                f'RASP cannot express negative thrust, so they are written as '
                f'0.0 N: the curve below is CLAMPED, not the raw solution')
            if ham is not None and kenetli is not None:
                lines.append(
                    f';   raw (unclamped) curve integral = {ham:.3f} N-s; '
                    f'clamped curve integral = {kenetli:.3f} N-s')
        return lines

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
    def dry_mass_reconciliation(motor_data: Dict) -> Optional[Dict]:
        """İki ayrı "kuru kütle" toplamını karşılaştırır, otoriteyi BEYAN eder.

        Faz 5B / H4-7. ÖLÇÜLDÜ (HEAD 9d3728e, 2 kN N2O/HTPB hibrit): aynı
        motor sonucunda iki toplam birden "kuru kütle" adıyla yayımlanıyor ve
        aralarında %22,8 fark var; ayrıca ÜÇ ayrı lüle kütlesi dolaşıyor
        (24,5× fark):

          yol                                         değer      kapsam
          structural...weight_analysis.total_weight   16,8366 kg kamara+kapaklar
                                                                 +%30-kuralı lüle,
                                                                 ENJEKTÖR YOK
          cad_design...mass_breakdown.total_dry_mass  13,7130 kg kamara+çizilen
                                                                 lüle+enjektör,
                                                                 KAPAKLAR YOK
          structural...weight_analysis.nozzle_weight   3,8362 kg %30 başparmak
                                                                 kuralı (beyanlı)
          cad_design...mass_breakdown.nozzle_mass      0,2003 kg ÇİZİLEN KATI
          nozzle_design.geometry.estimated_mass        0,1567 kg yalnız diverjan

        OTORİTE: lüle kütlesi için ÇİZİLEN KATI (``cad_design`` dökümü).
        Hacim modeli ``V = π(2·t·r_ort + t²)·L`` kesik koni halkası formülüdür
        ve Faz 4'te Lean ile ispatlandı (docs/BICIMSEL_ISPATLAR.md,
        ``HRMA.frustumAnnulusVolume_eq_integral``); %30 kuralı ise kaynağında
        "ESTIMATE ... not a geometry calculation" diye beyanlıdır.

        Bu metot HİÇBİR kütleyi değiştirmez — hangi sayının dosyaya gittiğini,
        hangisinin yaklaşım olduğunu ve iki toplamın neyi dışarıda bıraktığını
        yazar. ``.eng`` başlığına bu satırlar düşülür ki dosyayı açan kişi
        16,8366 kg ile 13,7130 kg arasındaki farkı görsün.

        Döner: karşılaştırma sözlüğü, ya da karşılaştıracak ikinci bir kaynak
        yoksa ``None``.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        weight = _nested(md, 'structural_analysis', 'weight_analysis') or {}
        breakdown = (_nested(md, 'cad_design', 'performance_summary',
                             'mass_breakdown')
                     or _nested(md, 'performance_summary', 'mass_breakdown')
                     or {})
        if not isinstance(weight, dict) or not isinstance(breakdown, dict):
            return None

        struct_total = _finite_positive(weight.get('total_weight'))
        cad_total = _finite_positive(breakdown.get('total_dry_mass'))
        if struct_total is None or cad_total is None:
            return None

        drawn_nozzle = _finite_positive(breakdown.get('nozzle_mass'))
        rule_nozzle = _finite_positive(weight.get('nozzle_weight'))
        solver_nozzle = _finite_positive(
            _nested(md, 'nozzle_design', 'geometry', 'estimated_mass'))
        end_caps = _finite_positive(weight.get('end_caps_weight'))
        injector = _finite_positive(breakdown.get('injector_mass'))

        lines = [
            '; NOTE - two dry masses exist for this motor and they do not '
            'agree:',
            f';   .eng loaded mass uses structural_analysis total = '
            f'{struct_total:.3f} kg '
            '(chamber + closures + rule-of-thumb nozzle; injector NOT included)',
            f';   CAD mass breakdown total = {cad_total:.3f} kg '
            '(chamber + as-drawn nozzle + injector; closures NOT included)',
            f';   difference = {abs(struct_total - cad_total):.3f} kg '
            f'({abs(struct_total - cad_total) / struct_total * 100.0:.1f}% of '
            'the value written above)',
        ]
        if drawn_nozzle is not None:
            lines.append(
                f';   AUTHORITATIVE nozzle mass = {drawn_nozzle:.4f} kg - the '
                'as-drawn solid (frustum-annulus volume, formally verified: '
                'docs/BICIMSEL_ISPATLAR.md)')
        if rule_nozzle is not None:
            basis = str(weight.get('nozzle_weight_basis') or
                        'declared estimate').strip()
            lines.append(
                f';   APPROXIMATION in the .eng total: nozzle = '
                f'{rule_nozzle:.4f} kg - {" ".join(basis.split())[:120]}')
        if solver_nozzle is not None:
            lines.append(
                f';   APPROXIMATION (not used by any export): nozzle = '
                f'{solver_nozzle:.4f} kg - divergent cone only')

        return {
            'eng_total_kg': struct_total,
            'eng_total_scope': ('chamber + closures + rule-of-thumb nozzle; '
                                'injector not included'),
            'cad_total_kg': cad_total,
            'cad_total_scope': ('chamber + as-drawn nozzle + injector; '
                                'closures not included'),
            'difference_kg': abs(struct_total - cad_total),
            'difference_percent': (abs(struct_total - cad_total)
                                   / struct_total * 100.0),
            'nozzle_authoritative_kg': drawn_nozzle,
            'nozzle_authoritative_basis': (
                'as-drawn solid; frustum-annulus volume V = pi(2*t*r_mid + '
                't^2)*L, formally verified (docs/BICIMSEL_ISPATLAR.md)'),
            'nozzle_approximations_kg': {
                'structural_rule_of_thumb': rule_nozzle,
                'solver_divergent_cone_only': solver_nozzle,
            },
            'end_caps_kg': end_caps,
            'injector_kg': injector,
            'comment_lines': lines,
        }

    #: ``resolve_inert_mass``ın aradığı alanlar — .eng beyanında ADIYLA
    #: sayılır (CLAUDE.md kural 11: liste tek yerde tanımlı).
    INERT_MASS_SEARCH_PATH = ('structural_analysis.weight_analysis.'
                              'total_weight', 'dry_mass', 'motor_mass',
                              'engine_mass', 'total_dry_mass', 'inert_mass',
                              'case_mass')

    @classmethod
    def _structural_presence_lines(cls, motor_data: Dict) -> List[str]:
        """Kuru kütle çözülemediğinde NEYİN eksik olduğunu ADIYLA yazar.

        ÖH Z5S / P9B3-20. Eski metin "bu dışa aktarımda yapısal analiz yok"
        diyordu; ölçüm bunun yanlış olduğunu gösterdi (katı ve sıvı gerçek
        sonuçlarında yapısal analiz bloğu VAR). Yanlış beyan yerine ölçülen
        durum yazılır: analiz var mı, hangi alt bloklarla, cidar çözülüyor mu
        ve eksik olan hangi alan.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        struct = md.get('structural_analysis')
        lines = [';   searched: ' + ', '.join(cls.INERT_MASS_SEARCH_PATH)]
        if not isinstance(struct, dict) or not struct:
            lines.append(';   NOTE: this result carries no structural analysis '
                         'block either - the case mass has not been computed '
                         'anywhere in this export')
            return lines
        bloklar = ', '.join(sorted(k for k in struct if isinstance(k, str))[:6])
        lines.append(f';   NOTE: a structural analysis IS present in this '
                     f'result (blocks: {bloklar}) - what is missing is the '
                     f'total mass it does not publish, not the analysis')
        wall_m = cls._wall_thickness_m(md)
        if wall_m is not None:
            lines.append(f';   it does resolve a case wall thickness of '
                         f'{wall_m * 1000.0:.2f} mm, but a wall alone is not a '
                         f'mass (length and material density are needed)')
        return lines

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
    #: İmalat çizimleri cidarı çözemediğinde ``.eng``in indiği eski merdiven.
    #: Künye satırı bunu ADIYLA söyler — sessiz yedek yok.
    _WALL_FALLBACK_LADDER_LABEL = (
        'fallback ladder (cad_design.case_design / case_analysis / '
        'chamber_structure / chamber_analysis recommendation) - the '
        'manufacturing drawings could not resolve a drawn wall')

    @staticmethod
    def _drawn_wall(motor_data: Dict):
        """İmalat çizimlerinin ÇİZDİĞİ cidar: ``(kalınlık_m|None, künye|None)``.

        İçe aktarma fonksiyon içinde: ``cad_visualization`` plotly/trimesh
        yükler ve ``.eng`` yolu bunu modül açılışında ödemek zorunda değildir
        (``drawing_generator`` ve ``step_export`` de aynı deseni kullanır).
        Modül yoksa (None, None) döner — çağıran kendi merdivenine iner, ama
        SESSİZ bir yedek DEĞİL: sıra künyede adıyla yazılıdır.
        """
        try:
            from hrma.export.cad_visualization import _chamber_wall_design
            design = _chamber_wall_design(motor_data)
        except Exception:
            return None, None
        if not isinstance(design, dict):
            return None, None
        thickness = _finite_positive(design.get('thickness_m'))
        if thickness is None:
            return None, None
        return thickness, str(design.get('source') or '')

    @staticmethod
    def _wall_thickness_source(motor_data: Dict) -> str:
        """``.eng`` yorum satırına düşecek cidar künyesi (P17S1-01)."""
        _t, source = OpenRocketExporter._drawn_wall(motor_data)
        return source or OpenRocketExporter._WALL_FALLBACK_LADDER_LABEL

    @staticmethod
    def _wall_thickness_m(motor_data: Dict) -> Optional[float]:
        """Kasa cidar kalınlığını [m] gerçek analizlerden çeker.

        ÖH Z2 (defter P17S1-01, yüksek). Bu aday listesi ÇİZİLEN cidarı
        (``wall_thickness_used_mm``) hiç tanımıyordu; hibritte doğrudan
        ``chamber_analysis.recommended_thickness``e düşüyordu. Ölçüldü
        (P17 turu, aynı oturumun iki dosyası): ``.eng`` başlığı kasa çapını
        **97,9 mm**, aynı paketin STEP'i **90,03 mm** yazıyordu — ima edilen
        cidarlar 8,935 ⟷ 5,000 mm. 27 Ağustos 2026'da yeniden ölçüldü:
        ``.eng`` 184,3656 mm (öneri 15,9165 mm) ⟷ STEP 162,5327 mm
        (as-designed 5,00 mm). Aynı motorun iki dosyası iki farklı motor
        anlatıyordu.

        Artık ÖNCE imalat zincirinin tek çözümleyicisi sorulur
        (``cad_visualization._chamber_wall_design`` — DXF, STEP, STL, kesit
        ve kütle dökümü aynı sayıyı oradan okur). O sayı yoksa aşağıdaki
        eski merdiven yedek kalır.
        """
        drawn, _source = OpenRocketExporter._drawn_wall(motor_data)
        if drawn is not None:
            return drawn

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
          2. ``length_units`` BEYANI ('m' / 'mm') — üretici birimini
             söylüyorsa çıkarım YAPILMAZ (ÖH D15 / harita H1a).
          3. Beyan da yoksa üst seviye alanlar büyüklükten çıkarılır
             (_length_in_meters).

        ÖH D15 / harita H1a — bu metot 2. adımı ATLIYORDU: ``length_units``
        deponun her yerinde (motor_geometry, pdf_generator, step_export,
        drawing_generator) okunan beyandır, yalnız burada okunmuyordu ve
        çıkarım eşiği (LENGTH_SI_MAX_M = 5 m) tek otoriteydi. ÖLÇÜLDÜ
        (once.json, HYBRID_BASE tek alan sarsımı): kamara boyu 5 m'yi aşan
        tamamen geçerli hibrit tasarımlarda (of_ratio 1,25 -> 6,733 m;
        fuel_density 460 -> 6,897 m; regression_n 0,2775 -> 17,318 m) uzunluk
        "demek ki mm" sayılıp 1000'e bölünüyor, .eng RASP zarfı 17,3 mm
        oluyor ve P9B3-11 yoğunluk kapısı 100.082 kg/m3 ima ettiği için
        (doğru olarak) reddediyordu. Kusur kapıda değil, kapıya verilen
        uzunluktaydı. Gövde tek kaynaktır: ``motor_geometry.resolve_length_m``
        üç adımı da o modülde uygular; burada ikinci kez yazılmaz.

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
            # Üç adımlı çözüm (motor_geometry -> length_units beyanı ->
            # büyüklük çıkarımı) TEK yerde durur: motor_geometry modülü.
            value, unit = _resolve_length_m_shared(md, key, si_max)
            fields[key] = unit
            if unit in ('mm', 'declared:mm'):
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

        if geo:
            source = 'motor_geometry'
        elif any(str(u).startswith('declared:') for u in fields.values()):
            source = 'declared'
        else:
            source = 'inferred'
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
        """`<sınıf><ortalama itki N>-<motor adı>`.

        Sınıf harfi TOPLAM İMPULSTAN gelir. Sayı ORTALAMA İTKİDİR (N, tamsayıya
        yuvarlanmış): ortalama itki = toplam impuls / yanma süresi.

        Kaynak (7 Ekim 2026'da web'den okundu):
          * thrustcurve.org, "RASP Engine File Format", "The Header Line"
            bölümü (https://www.thrustcurve.org/info/raspformat.html): ad
            alanı "the common name of the motor; just the impulse class and
            average thrust"; çap alanı ayrıca "the casing diameter in
            millimeters".
          * thrustcurve.org, "Motor Statistics" (https://www.thrustcurve.org/
            info/motorstats.html): ortak ad "total impulse, represented by
            the impulse class, and the average thrust" ile kurulur.
        UI openrocket-kose 2. tur, devir D1 (ana model kararı, §28-18): sayı
        eskiden KASA ÇAPIYDI (mm). Kasa çapı RASP başlığının kendi çap
        alanında zaten yazılıdır; künyede iki kez durmaz. ÖLÇÜLDÜ: OpenRocket
        24.12 katı örneği 'L85' gösteriyordu, ortalama itkisi ise 1300 N.

        Değerler yanıtın kendi alanlarından gelir, uydurulmaz:
          * toplam impuls: ``resolve_total_impulse`` (sınıf harfiyle AYNI
            sayı; kaynağı .eng yorumunda "total impulse ... sets the class
            letter" satırında yazılı);
          * yanma süresi: çözücünün ``burn_time`` alanı; yoksa yazılan
            zaman-çözümlü itki eğrisinin süresi (``real_thrust_curve``).
        İkisinden biri yoksa ya da sayı 1 N'un altına yuvarlanıyorsa künye
        ``UNKNOWN-<motor adı>`` olur (fail-closed; Faz 4B, bulgu A12: boş bir
        sözlükten eskiden ``M0-HRMA-001`` çıkıyordu).

        ``geometry`` parametresi çağıranlarla uyum için durur; künye artık
        geometriye bakmaz.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        # ÖH Z5S / P9B3-18 + devir D2: ad RASP'ın tek parçalı ad alanına
        # indirilir ve OpenRocket'in gecikme sanıp keseceği sonek bırakılmaz.
        # Değişiklik .eng yorumunda beyan edilir.
        motor_name, _beyan = _sanitize_motor_name(
            md.get('motor_name', DEFAULT_MOTOR_NAME))
        total_impulse, _src = self.resolve_total_impulse(md)
        if total_impulse is None:
            return f"UNKNOWN-{motor_name}"
        motor_class = self._get_motor_class(total_impulse)
        if motor_class is None:
            # ÖH Z5S / P9B3-17: impuls tablonun dışında; harf UYDURULMAZ.
            # Eskiden sessizce "A" yazılıyordu.
            return f"UNKNOWN-{motor_name}"
        burn_time = _finite_positive(md.get('burn_time'))
        if burn_time is None:
            t_real, _f_real, _key = self.real_thrust_curve(md)
            if t_real is not None:
                burn_time = _finite_positive(float(t_real[-1] - t_real[0]))
        if burn_time is None:
            return f"UNKNOWN-{motor_name}"
        # Yarım yukarı yuvarlama (Python round() yarımları çifte yuvarlar).
        average_thrust_n = int(math.floor(total_impulse / burn_time + 0.5))
        if average_thrust_n < 1:
            return f"UNKNOWN-{motor_name}"
        return f"{motor_class}{average_thrust_n}-{motor_name}"

    #: Beyan edilen tank hacminin ``system_summary`` toplamı ile tank
    #: GEOMETRİSİNDEN hesaplanan toplamın uyuşması gereken bağıl pay.
    #: İki temsil bu payın dışında ayrışıyorsa hacmin BİRİMİ okunamamış
    #: demektir ve kapı fail-closed davranır (sayı yorumlanmaz).
    TANK_VOLUME_CROSSCHECK_REL = 0.05

    @classmethod
    def _declared_propellant_volume_m3(cls, motor_data):
        """İticiyi TUTTUĞU BEYAN EDİLEN hacim [m^3] — çözücünün kendi bloğu.

        Döner: ``(hacim_m3|None, künye|None)``.

        ÖH D15 birleşme etkileşimi (1 Eylül 2026). ``_eng_implied_bulk_density``
        RASP başlığının zarfını ölçer; sıvı motorda o zarf KAMARADIR ve iticiyi
        TUTMAZ (dosyanın kendi satırı da öyle diyor: "length field = chamber
        length"). İticinin gerçekten durduğu hacmi çözücü ayrı bir blokta
        BEYAN EDİYOR: ``propellant_tanks``. Bu metot o beyanı okur.

        BİRİM VARSAYILMAZ, ÖLÇÜLÜR. ``system_summary.total_volume`` litre gibi
        görünüyor; doğrulaması, aynı bloğun tank tank yayımladığı
        ``dimensions.diameter`` / ``dimensions.length`` (mm) silindir
        hacimleriyle karşılaştırmaktır. İki bağımsız temsil
        ``TANK_VOLUME_CROSSCHECK_REL`` payı içinde uyuşmuyorsa None döner ve
        çağıran fail-closed davranır.

        ÖLÇÜLDÜ (1 Eylül 2026, /calculate_liquid 10 kN RP-1/LOX):
          system_summary.total_volume = 1211,598534 L
          geometri toplamı = pi/4(0,605138^2 x 1,512845)
                           + pi/4(0,734012^2 x 1,835029) = 1,211599 m^3
          bağıl fark 4e-7 -> litre okuması DOĞRULANDI.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        tanks = md.get('propellant_tanks')
        if not isinstance(tanks, dict):
            return None, None

        # (a) Tank tank GEOMETRİ toplamı — birimden bağımsız çapa.
        geo_m3, adlar = 0.0, []
        for ad in sorted(tanks):
            blok = tanks.get(ad)
            if not isinstance(blok, dict):
                continue
            dim = blok.get('dimensions')
            if not isinstance(dim, dict):
                continue
            d_mm = _finite_positive(dim.get('diameter'))
            l_mm = _finite_positive(dim.get('length'))
            if d_mm is None or l_mm is None:
                continue
            geo_m3 += math.pi / 4.0 * (d_mm / 1000.0) ** 2 * (l_mm / 1000.0)
            adlar.append(ad)
        if not adlar or geo_m3 <= 0.0:
            return None, None

        # (b) Özetin toplamı litre okunur ve (a) ile ÇAPRAZLANIR.
        ozet = tanks.get('system_summary')
        if isinstance(ozet, dict):
            v_l = _finite_positive(ozet.get('total_volume'))
            if v_l is not None:
                v_m3 = v_l / 1000.0
                if abs(v_m3 - geo_m3) <= cls.TANK_VOLUME_CROSSCHECK_REL * geo_m3:
                    return v_m3, (
                        'propellant_tanks.system_summary.total_volume '
                        f'({v_l:,.1f} L; cross-checked against the per-tank '
                        f'cylinder geometry, relative difference '
                        f'{abs(v_m3 - geo_m3) / geo_m3:.2e})')
                # İki temsil ayrışıyor: birim okunamadı -> fail-closed.
                return None, None
        return geo_m3, ('propellant_tanks.' + '+'.join(adlar)
                        + '.dimensions (cylinder geometry)')

    @staticmethod
    def _eng_implied_bulk_density(diameter_mm, length_mm, prop_mass_kg):
        """RASP başlığının ima ettiği bulk itici yoğunluğu (kg/m^3).

        Zarf = ``pi/4 * d^2 * L`` (RASP'ın 2. ve 3. alanları, mm). Alanların
        biri sonlu-pozitif değilse ``None`` döner — o durumu zaten alan
        bazlı kapı yakalar (ÖH D15 / P9B3-11).
        """
        d = _finite_positive(diameter_mm)
        l = _finite_positive(length_mm)
        m = _finite_positive(prop_mass_kg)
        if d is None or l is None or m is None:
            return None
        hacim_m3 = math.pi / 4.0 * (d / 1000.0) ** 2 * (l / 1000.0)
        if hacim_m3 <= 0:
            return None
        return m / hacim_m3

    def _create_eng_file(self, designation: str, diameter: float, length: float,
                        prop_mass: float, total_impulse: float,
                        thrust_curve: List[Tuple[float, float]], motor_data: Dict,
                        thrust_source: str = 'constant',
                        geometry: Dict = None, resolved: Dict = None,
                        report: Dict = None) -> str:
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
                continue
            # ÖH D16 / P16B4-15 — YUVARLAMA KAPISI.
            # ÖLÇÜLDÜ (taban 6fde52b): ``propellant_mass = 1e-9`` kg ile uç
            # HTTP 200 veriyor ve dosyaya şu satır giriyordu:
            #     L100-FUZZBASE 100.0 300.0 P 0.000 0.000 HRMA
            # Yani alan bazlı "sonlu ve pozitif" kapısı geçiliyor ama RASP
            # başlığına YAZILAN sayı 0.000 oluyor — tam olarak bu modülün
            # ret metninin yasakladığı ("a zero-diameter or default-mass
            # motor would load in OpenRocket and look real") dosya. Kapı
            # değeri kendi başına değil, YAZILDIĞI HÂLİYLE sınar.
            basamak = ENG_HEADER_DECIMALS.get(ad)
            if basamak is not None and round(float(deger), basamak) <= 0.0:
                gecersiz[ad] = (
                    f'the RASP header field is written with {basamak} '
                    f'decimals, so {float(deger)!r} would appear in the file '
                    f'as {float(deger):.{basamak}f} - a zero value in the '
                    f'motor line. The header is the file: a field that is '
                    f'zero as written IS a placeholder motor, regardless of '
                    f'the unrounded value')
        if not thrust_curve:
            gecersiz['thrust_curve'] = 'no thrust samples to write'

        # ÖH D15 / defter P9B3-11 — ZARF ile KÜTLE BİRBİRİNE BAKMIYORDU.
        # Yukarıdaki kapı her alanı TEK BAŞINA "sonlu ve pozitif" diye
        # sınıyor; oysa RASP başlığı çapı, boyu ve yüklü itici kütlesini
        # AYNI SATIRA yazar ve üçü birlikte bir ima edilen bulk yoğunluk
        # üretir. Kapı olmadığı için sıvı motorda ölçülen satır şuydu:
        #
        #   P+149-P9-LIQUID 149.3 98.0 P 1103.056 1103.056 HRMA
        #   -> pi/4 * 0,1493^2 * 0,098 = 0,0017156 m^3
        #   -> 1103,056 / 0,0017156 = 642.927 kg/m^3  (osmiyumun ~28 katı)
        #
        # Kök: ``length`` alanı KAMARA boyudur (bir alt satırda öyle
        # beyan ediliyor), itici kütlesi ise TANK içeriğidir; sıvı motorda
        # ikisi aynı hacme ait değildir. Dosya OpenRocket'a yüklenince bu
        # kütle doğrudan apoje hesabına girer.
        #
        # Fail-closed: fiziksel olarak imkânsız bir motor satırı YAZILMAZ.
        # Üst sınır uydurulmaz, deponun kendi itici yoğunluk bandının üst
        # ucudur (``propellants_db.PROPELLANT_DENSITY_RANGE_KG_M3``, aynı
        # demet katalog doğrulayıcısının kullandığı banttır). ALT sınır
        # kapı DEĞİLDİR: kısmen dolu bir kasa fiziksel olarak mümkündür,
        # imkânsız olan zarfın ALDIĞINDAN ÇOK itici taşımaktır.
        #
        # ÖH D15 BİRLEŞME ETKİLEŞİMİ (1 Eylül 2026) — KAPI DOĞRU HACME
        # SORULUYOR. Yukarıdaki gerekçenin son cümlesi kapının kendi
        # ölçümünü çürütüyordu: "RASP boyu KAMARA boyudur, itici kütlesi
        # TANK içeriğidir, ikisi aynı hacme ait DEĞİLDİR". Karşılaştırılamaz
        # olduğu SÖYLENEN iki büyüklüğün oranı, dosyanın yalan söylediğinin
        # kanıtı olamaz.
        #
        # ÖLÇÜLDÜ (/calculate_liquid, 10 kN RP-1/LOX): kapıyı geçebilmek
        # için RASP boyu alanının 40,86 m olması gerekiyordu — gerçek kamara
        # boyunun 584 katı ve dosyanın kendi fiziksel boy bandının (50 mm -
        # 5 m, tests/test_unit_contract.py) 8 katı dışında. Yani bu kapıyı
        # HİÇBİR sıvı motor geçemez: fizik denetimi değil, sıvı .eng
        # ihracatının toptan kaldırılmasıdır. Birleşmede ölçüldü: 15
        # kazanılmış bekçi (kasa çapı = STEP çapı P17S1-01, RASP başlığı
        # fiziksel bantta, geometri künyesi beyanlı, yer-tutucu beyanı,
        # atıl kütle uyarısı) bu yüzden kırmızıya döndü.
        #
        # ONARIM (gevşetme DEĞİL): eşik AYNI (3.000 kg/m3, aynı tek kaynak),
        # sorulan hacim düzeltildi. Üç durum ayrılır:
        #   1. Zarf iticiyi TUTUYOR (katı/hibrit, gerçek kasa çapı) ->
        #      eski davranış AYNEN: imkânsız yoğunluk -> DOSYA YAZILMAZ.
        #   2. İtici AYRI TANKLARDA (çözücü ``propellant_tanks`` yayımlıyor)
        #      -> yoğunluk BEYAN EDİLEN tank hacmine karşı ölçülür. O da
        #      bandı aşarsa DOSYA YAZILMAZ (fail-closed korunur). Geçerse
        #      dosya yazılır ve zarfın iticiyi tutMADIĞI, OpenRocket'ın
        #      ağırlık merkezini/apojeyi bu yüzden YANLIŞ hesaplayacağı
        #      sayılarıyla BEYAN EDİLİR.
        #   3. Zarfın kendisi BEYAN EDİLMİŞ YER TUTUCU (kasa çapı yok, boğaz
        #      /çıkış çapı yazılmış ya da kamara boyu yok) -> oran zaten yer
        #      tutucuyu ölçer, iticiyi değil; dosya yazılır ve oran adıyla
        #      not düşülür. Yer tutucu beyanı zaten başlıkta duruyor.
        #
        # ÖLÇÜM (aynı gün, üç motor + yalın gövde):
        #   katı   Ø104,80 x 600,00 mm, 6,468 kg   -> 1.249,7 kg/m3  (geçer)
        #   hibrit Ø127,46 x 959,05 mm, 8,834 kg   ->   721,9 kg/m3  (geçer)
        #   sıvı   Ø103,19 x  69,99 mm, 1025,28 kg -> 1.751.494 kg/m3 zarfta,
        #          tanklarda (1.211,60 L) 846,2 kg/m3 -> GEÇER, beyanlı
        #   yalın  Ø20,00 x 300,00 mm, 2,000 kg    -> 21.220,7 kg/m3, çap
        #          BEYAN EDİLMİŞ yer tutucudur (boğaz çapı) -> beyanlı
        _yogunluk = self._eng_implied_bulk_density(diameter, length,
                                                   prop_mass)
        _zarf_beyani: List[str] = []
        _zarf_kaydi = None
        if _yogunluk is not None and _yogunluk > PROPELLANT_DENSITY_MAX_KG_M3:
            _cap_kaynagi = geometry.get('case_diameter_source')
            _yer_tutucu = (_cap_kaynagi in ('throat', 'exit')
                           or geometry.get('chamber_length') is None)
            _tank_m3, _tank_kunye = self._declared_propellant_volume_m3(
                motor_data)
            _tank_yogunluk = (prop_mass / _tank_m3
                              if _tank_m3 is not None else None)
            # SIRA ÖNEMLİ: tank beyanı VARSA hüküm ONA aittir. Tanklara
            # da sığmayan kütle, çap yer tutucu olsa bile imkânsızdır ve
            # dosya YAZILMAZ (yer tutucu dalı onu affetmemeli).
            if _tank_m3 is not None and _tank_yogunluk is not None and \
                    _tank_yogunluk <= PROPELLANT_DENSITY_MAX_KG_M3:
                # (2) İtici ayrı tanklarda ve TANKLARA sığıyor: dosya yazılır,
                # zarf-kütle ayrışması sayılarıyla BEYAN edilir. Susmak da
                # yazmamak da okuyanı yanıltırdı; RASP biçiminde "itici
                # başka yerde" diyecek bir alan yoktur, o yüzden yorum satırı.
                # ÖH D17 / P9B3-11 (Fable-D15 ŞART) — MAKİNE-OKUR KAYIT.
                # Aşağıdaki yorum satırları RASP tüketicileri tarafından yok
                # sayılır; arayüz de onları okuyamaz. ÖLÇÜLDÜ (taban
                # ``2426b4d``): ürün ağacında ``eng_envelope_warning`` adı
                # HİÇ geçmiyordu (``git grep -c ... hrma/`` -> boş), yani
                # zarf-kütle ayrışması yalnız .eng'in içinde, insan gözüne
                # bakan bir cümle olarak duruyordu. Kayıt ``eng_error`` ile
                # AYNI şemayı taşır (error/message + alan adları) ki iki uç
                # tek biçim okusun; sayılar İKİNCİ KEZ HESAPLANMAZ, buradaki
                # yerel değişkenlerden gelir.
                _zarf_kaydi = {
                    'error': 'propellant_outside_envelope',
                    'message': (
                        'The loaded propellant is not inside the envelope '
                        'written on the RASP motor line; OpenRocket will '
                        'place the mass inside the motor and compute the '
                        'centre of gravity, the stability margin and the '
                        'apogee from the wrong position.'),
                    'envelope_diameter_mm': float(diameter),
                    'envelope_length_mm': float(length),
                    'propellant_mass_kg': float(prop_mass),
                    'envelope_bulk_density_kg_m3': float(_yogunluk),
                    'declared_tank_volume_m3': float(_tank_m3),
                    'declared_tank_bulk_density_kg_m3': float(_tank_yogunluk),
                    'declared_tank_source': _tank_kunye,
                    'propellant_density_upper_bound_kg_m3': float(
                        PROPELLANT_DENSITY_MAX_KG_M3),
                    'case_diameter_source': _cap_kaynagi,
                }
                _zarf_beyani = [
                    '; WARNING: the loaded propellant is NOT inside the '
                    'envelope written on the motor line.',
                    f';   RASP envelope {diameter:.1f} x {length:.1f} mm '
                    f'would imply {_yogunluk:,.0f} kg/m3 for '
                    f'{prop_mass:.3f} kg - physically impossible '
                    f'(propellant band upper bound '
                    f'{PROPELLANT_DENSITY_MAX_KG_M3:,.0f} kg/m3).',
                    f';   The propellant is held in the tanks this analysis '
                    f'sized: {_tank_kunye}',
                    f';   -> {_tank_yogunluk:,.1f} kg/m3 in the declared tank '
                    f'volume, which IS inside the band.',
                    ';   OpenRocket places the loaded mass INSIDE the motor '
                    'envelope, so the centre of gravity, the stability '
                    'margin and the apogee it computes from this file are '
                    'WRONG until you model the tanks as separate components.',
                ]
            elif _yer_tutucu and _tank_m3 is None:
                # (3) Zarf beyan edilmiş yer tutucu: oran yer tutucuyu ölçer.
                # (3) Yer tutucu dalı — aynı şema, farklı kod.
                _zarf_kaydi = {
                    'error': 'envelope_is_declared_placeholder',
                    'message': (
                        'The envelope written on the RASP motor line is a '
                        'declared placeholder, not the measured case: the '
                        'implied bulk density measures the placeholder, not '
                        'the propellant.'),
                    'envelope_diameter_mm': float(diameter),
                    'envelope_length_mm': float(length),
                    'propellant_mass_kg': float(prop_mass),
                    'envelope_bulk_density_kg_m3': float(_yogunluk),
                    'declared_tank_volume_m3': None,
                    'declared_tank_bulk_density_kg_m3': None,
                    'declared_tank_source': None,
                    'propellant_density_upper_bound_kg_m3': float(
                        PROPELLANT_DENSITY_MAX_KG_M3),
                    'case_diameter_source': _cap_kaynagi,
                }
                _zarf_beyani = [
                    f'; NOTE: the envelope written above implies '
                    f'{_yogunluk:,.0f} kg/m3 for {prop_mass:.3f} kg, above '
                    f'the {PROPELLANT_DENSITY_MAX_KG_M3:,.0f} kg/m3 '
                    f'propellant band.',
                    ';   That ratio measures the DECLARED PLACEHOLDER above, '
                    'not the propellant mass: correct the envelope in '
                    'OpenRocket and the ratio goes with it.',
                ]
            else:
                # (1) Zarf iticiyi tutuyor (ya da tank beyanı okunamadı):
                # eski fail-closed davranış AYNEN.
                _tank_notu = ('' if _tank_m3 is None else
                              f' The declared tank volume gives '
                              f'{_tank_yogunluk:,.0f} kg/m3, still above the '
                              f'band.')
                gecersiz['propellant_mass_kg'] = (
                    f'the RASP header would imply a bulk propellant density '
                    f'of {_yogunluk:,.0f} kg/m3 (loaded propellant '
                    f'{prop_mass:.3f} kg inside the declared envelope '
                    f'{diameter:.1f} x {length:.1f} mm); the physical upper '
                    f'bound for rocket propellants is '
                    f'{PROPELLANT_DENSITY_MAX_KG_M3:,.0f} kg/m3. This run '
                    f'declares no separate propellant tanks and the casing '
                    f'diameter is not a placeholder, so the envelope IS the '
                    f'volume that should hold this mass and the numbers '
                    f'contradict each other; no motor file is written.'
                    + _tank_notu)

        # ÖH D17 / P9B3-11: kayıt ÇAĞIRANA taşınır. Paylaşılan bir
        # örnek niteliği (``self.…``) KULLANILMAZ — bu modülün kendi notu
        # istekler arasında durum taşımayı sızıntı sayar; ``report`` her
        # istekte çağıranın açtığı TAZE sözlüktür.
        if isinstance(report, dict):
            report['eng_envelope_warning'] = _zarf_kaydi

        if gecersiz:
            raise OpenRocketExportDataError(
                sorted(gecersiz), gecersiz, what='.eng')

        lines = []

        # Header comment
        lines.append(f"; {designation}")
        lines.append(f"; HRMA Rocket Motor")
        lines.append(f"; Generated by HRMA - Rocket Motor Analysis")
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
        # Cidar KÜNYESİ dosyanın içinde durur (P17S1-01): kasa çapı
        # "oda + 2 x cidar" ile kurulduğunda hangi cidarın kullanıldığı
        # okunmadan .eng ile STEP karşılaştırılamıyordu.
        if geometry.get('case_diameter_source') == 'chamber_plus_wall':
            wall_m = self._wall_thickness_m(motor_data)
            if wall_m is not None:
                lines.append(f"; wall used in the diameter field = "
                             f"{wall_m * 1000.0:.2f} mm; "
                             f"{self._wall_thickness_source(motor_data)}")
        if geometry.get('chamber_length') is None:
            lines.append("; length field = exporter placeholder; chamber length "
                         "NOT available in this export - correct it in OpenRocket")
        else:
            lines.append("; length field = chamber length (nozzle not included)")
        # Zarf ⟷ yüklü kütle ayrışmasının BEYANI (ÖH D15 birleşme
        # etkileşimi): sayılar zarf ve boy künyelerinin hemen ardında durur.
        lines.extend(_zarf_beyani)
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
        # ÖH Z5S / P9B3-16 + P9B3-27: başlıktaki impuls, çözücünün teslim
        # ettiği impuls ve DOSYAYA YAZILAN eğrinin integrali aynı sayı değil.
        # Üçü de adıyla yazılır; negatif örnek kenetlendiyse bu da beyan
        # edilir (eskiden dosya yalnız birinciyi yazıp susuyordu).
        lines.extend(self._impulse_audit_lines(
            self.impulse_audit(motor_data, thrust_curve)))
        # ÖH Z5S / P9B3-18: ad RASP'ın tek parçalı alanına indirildiyse
        # dosyadaki adın kullanıcının yazdığı ad OLMADIĞI söylenir.
        _ad, ad_beyani = _sanitize_motor_name(
            (motor_data or {}).get('motor_name', DEFAULT_MOTOR_NAME))
        if ad_beyani:
            lines.append('; ' + ad_beyani)
        # Çözücünün yanma süresi künyesi dosyaya taşınır — hem itici kütlesi
        # hem toplam impuls bu süreden türetilmiş olabilir ve okuyan kişi
        # zinciri görmelidir. (ÖH D36 / LU-1: sıvı çözücü artık süreyi
        # VARSAYMAZ; künye "user input (max burn duration)" ya da öğretici
        # kipte "tutorial default (300 s, use_tutorial_defaults)" olur. Süre
        # yoksa bu satıra hiç gelinmez: yukarıdaki kapı .eng'i adıyla reddeder.)
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
            # ÖH Z5S / P9B3-20: bu satır eskiden "(no structural analysis in
            # this export)" diyordu. ÖLÇÜLDÜ (27 Ağustos 2026, gerçek katı ve
            # sıvı sonuçları): yapısal analiz VAR (katıda case_analysis +
            # grain_structural, sıvıda chamber_structure + closure_joint) ve
            # cidar kalınlığı bile çözülüyor (4,65 mm / 2,00 mm) — eksik olan
            # ANALİZ değil, o analizin yayımladığı TOPLAM KÜTLE. Dosya artık
            # neyin eksik olduğunu doğru söylüyor.
            lines.append("; WARNING: loaded mass EXCLUDES motor case mass "
                         "- the inert (case/structure) mass could NOT be "
                         "resolved from this result; apogee will be "
                         "overestimated until you set the case mass in "
                         "OpenRocket")
            lines.extend(self._structural_presence_lines(motor_data))
        # H4-7: aynı sonuçta ikinci bir "kuru kütle" varsa fark dosyada yazar;
        # okuyan kişi hangi sayının OpenRocket'a gittiğini ve hangi kalemin
        # yaklaşım olduğunu görmeli (sessiz ayrışma yasak).
        reconciliation = self.dry_mass_reconciliation(motor_data)
        if reconciliation:
            lines.extend(reconciliation['comment_lines'])
        # ÖH D33 / OH-D32-10: dosyanın taşıdığı toplam impuls / itici kütlesi
        # çifti bir teslim Isp'si İMA EDER; o Isp'nin iki-faz düzeltme durumu
        # burada YAZILI durur (yalnız API'de değil).
        lines.extend(self._two_phase_comment_lines(motor_data))
        lines.append(";")
        manufacturer = "HRMA"
        delays = "P"  # RASP: tıpalı motor (ejeksiyon yükü yok); "0" anında ateşleme demekti

        # NOT (ÖH D16 / P16B4-15): buraya ikinci bir "yüklü kütle sıfır
        # olamaz" kapısı yazılmıştı ve ÖLÇÜLDÜ Kİ ULAŞILAMAZ —
        # ``loaded_mass = prop_mass + inert`` ve ``resolve_inert_mass``
        # negatif değer yayımlamıyor (``dry_mass = -1.0`` ile denendi: uç
        # 200 + ``P 1.000 1.000`` verdi, yani inert yutuldu). Ulaşılamayan
        # kapı, mutasyonla kanıtlanamayan bir koruma iddiasıdır; bu yüzden
        # SÖKÜLDÜ. Koruma tek yerdedir: yukarıdaki alan kapısı, ve o kapı
        # bu tablodan (ENG_HEADER_DECIMALS) beslendiği için yüklü kütle
        # alanını da aynı hassasiyetle yazar.
        _d = ENG_HEADER_DECIMALS
        motor_line = (
            f"{designation} "
            f"{diameter:.{_d['diameter_mm']}f} "
            f"{length:.{_d['length_mm']}f} {delays} "
            f"{prop_mass:.{_d['propellant_mass_kg']}f} "
            f"{loaded_mass:.{_d['loaded_mass_kg']}f} {manufacturer}")
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
    
    @classmethod
    def resolve_ork_structure(cls, rocket_params: Dict = None):
        """.ork yapı alanlarını çözer ve ÖRNEK olanları BEYAN listesine yazar.

        ÖH D15 / P9B3-14. ``(değerler, beyan_satırları)`` döner. Çağıran bir
        alanı verdiyse o alan beyan listesine GİRMEZ (sayı artık kullanıcının
        kendisidir); vermediyse XML bir sayı yazmak zorunda olduğu için örnek
        yazılır ama örnek olduğu ADIYLA söylenir.
        """
        gelen = rocket_params if isinstance(rocket_params, dict) else {}
        degerler = {}
        beyanlar = []
        ornek_alanlar = []
        for ad, (varsayilan, etiket) in ORK_EXAMPLE_STRUCTURE.items():
            verilen = gelen.get(ad)
            if verilen not in (None, ''):
                degerler[ad] = verilen
                beyanlar.append(f'{ad}: {etiket} = {verilen} '
                                f'(from the export request - user input)')
            else:
                degerler[ad] = varsayilan
                ornek_alanlar.append(f'{ad} = {varsayilan}')
        ornek_alanlar.append(
            f'body_wall_thickness = {ORK_BODY_TUBE_WALL_M}')
        beyanlar.append(
            'EXAMPLE STRUCTURE - the following '
            f'{len(ornek_alanlar)} airframe values are EXAMPLE values written '
            'by the exporter because no value was supplied for them; they are '
            'NOT your rocket. OpenRocket computes the centre of gravity, the '
            'stability margin and the apogee FROM THEM, so replace them with '
            'your own build before running a simulation: '
            + '; '.join(ornek_alanlar))
        return degerler, beyanlar

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
        # `<motor>M0-HRMA-001</motor>` yazan geçerli bir proje çıkıyordu.
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

        # ÖH Z5S / P9B3-15: motor yuvası gövde borusuna sığıyor mu? Üç gerçek
        # motorda da sığmıyordu ve şablonda bunu söyleyen tek satır yoktu.
        mount_fit = self.motor_mount_fit(mount_radius_m, vehicle,
                                         vehicle_sources)
        mount_notes_xml = '\n                    '.join(
            f'<!-- {note} -->' for note in self._motor_mount_fit_notes(mount_fit))

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

        # ÖH D15 / P9B3-14: gövde yapısının hangi sayısı kullanıcının, hangisi
        # ihraç edicinin ÖRNEĞİ — XML'in kendi içinde yazılır.
        yapi, yapi_notlari = self.resolve_ork_structure(rocket_params)
        structure_notes_xml = '\n            '.join(
            '<!-- ' + note.replace('--', '-') + ' -->' for note in yapi_notlari)

        # Simplified OpenRocket XML template
        xml_template = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<openrocket version="1.5" creator="HRMA">
    <rocket>
        <name>{rocket_params['name']}</name>
        {vehicle_notes_xml}
        <axialoffset method="absolute">0.0</axialoffset>

        <stage>
            <name>Stage 1</name>
            
            <!-- Nose Cone -->
            {structure_notes_xml}
            <nosecone>
                <name>Nose Cone</name>
                <shape>{yapi['nose_shape']}</shape>
                <length>{yapi['nose_length']}</length>
                <aftradius>{rocket_params['diameter']/2}</aftradius>
                <material type="bulk" density="{yapi['nose_density']}">{yapi['nose_material']}</material>
                <thickness>{yapi['nose_thickness']}</thickness>
            </nosecone>
            
            <!-- Body Tube -->
            <bodytube>
                <name>Body Tube</name>
                <length>{rocket_params['length']}</length>
                <outerradius>{rocket_params['diameter']/2}</outerradius>
                <material type="bulk" density="{yapi['body_density']}">{yapi['body_material']}</material>
                <thickness>{ORK_BODY_TUBE_WALL_M}</thickness>

                <!-- Motor Mount -->
                <motormount>
                    {mount_notes_xml}
                    <name>Motor Mount</name>
                    <length>{mount_length_m}</length>
                    <outerradius>{mount_radius_m}</outerradius>
                    <material type="bulk" density="{yapi['mount_density']}">{yapi['mount_material']}</material>
                    <thickness>{yapi['mount_thickness']}</thickness>
                    <motorconfig>
                        <configid>default</configid>
                        <motor>{motor_designation}</motor>
                    </motorconfig>
                </motormount>
                
                <!-- Fins -->
                <finset>
                    <name>Fins</name>
                    <fincount>{rocket_params.get('fin_count', 4)}</fincount>
                    <rootchord>{yapi['fin_root_chord']}</rootchord>
                    <tipchord>{yapi['fin_tip_chord']}</tipchord>
                    <height>{yapi['fin_height']}</height>
                    <sweepangle>{yapi['fin_sweep_angle']}</sweepangle>
                    <material type="bulk" density="{yapi['fin_density']}">{yapi['fin_material']}</material>
                    <thickness>{yapi['fin_thickness']}</thickness>
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
        <name>HRMA Motor Test</name>
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
    
    def export_eng_file(self, motor_data: Dict, filename: str = None,
                        report: Dict = None) -> str:
        """Alias for export_motor_file for compatibility.

        ÖH D17 / P9B3-11: ``report`` OLDUĞU GİBİ geçirilir; takma ad,
        asıl metodun sözleşmesini daraltmaz (daraltsaydı ``/api/export-eng``
        zarf beyanını hiç göremezdi — ölçüldü).
        """
        return self.export_motor_file(motor_data, filename, report=report)
    
    def export_motor_summary(self, motor_data: Dict) -> Dict:
        """API yanıtındaki motor özeti — imza varsayılanları KALDIRILDI.

        ÖH Z5S / P9B3-10. Modülün kendi belgesi "10000 N·s varsayılanı YOK"
        diyor (bkz. ``resolve_total_impulse``), ama AYNI yanıtı üreten bu
        metotta varsayılan hâlâ canlıydı. ÖLÇÜLDÜ (27 Ağustos 2026, onarım
        öncesi): ``export_motor_summary({})`` ->

            total_impulse = 10000, motor_class = 'M', average_thrust = 0,
            burn_time = 0, propellant_mass = 0

        Aynı istekte ``.eng`` yolu kapıyı işletip dosyayı ÜRETMİYOR
        (``OpenRocketExportDataError``), özet ise 'M' sınıfı bir motor
        bildiriyordu — tek yanıtın iki ucu birbiriyle çelişiyordu.

        Artık her sayı .eng ile AYNI çözücülerden gelir; çözülemeyen alan
        ``None`` kalır (0 N·s itki ya da 0 bar kamara basıncı da bir
        İDDİADIR, "veri yok" değil) ve hangi alandan çözüldüğü ``*_source``
        alanlarında yazar. Anahtar kümesi korunur: çağıran taraf KeyError
        yemez.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        total_impulse, impulse_source = self.resolve_total_impulse(md)
        motor_class = self._get_motor_class(total_impulse)
        average_thrust, thrust_source = self.resolve_average_thrust(md)
        propellant_mass, prop_source = self.resolve_propellant_mass(md)
        isp = (_finite_positive(md.get('isp'))
               or _finite_positive(md.get('specific_impulse'))
               or _finite_positive(md.get('isp_sea_level')))
        geometry = self.resolve_geometry(motor_data)
        motor_designation = self._designation(motor_data, geometry)
        throat_mm = geometry.get('throat_diameter')
        case_mm = geometry.get('case_diameter')

        return {
            'designation': motor_designation,
            'motor_class': motor_class,
            'motor_class_range_Ns': self.motor_class_range(motor_class),
            'total_impulse': total_impulse,
            'total_impulse_source': impulse_source,
            'average_thrust': average_thrust,
            'average_thrust_source': thrust_source,
            'burn_time': _finite_positive(md.get('burn_time')),
            'specific_impulse': isp,
            'propellant_mass': propellant_mass,
            'propellant_mass_source': prop_source,
            # mm — birim sözleşmesi resolve_geometry'de çözülür
            'throat_diameter': throat_mm * 1000.0 if throat_mm is not None else None,
            'case_diameter': case_mm * 1000.0 if case_mm is not None else None,
            'geometry_source': geometry.get('source'),
            'geometry_notes': geometry.get('notes'),
            'case_diameter_source': geometry.get('case_diameter_source'),
            # 0 bar / 0 O-F de bir iddiadır: çözülemiyorsa alan boş kalır.
            'chamber_pressure': _finite_positive(md.get('chamber_pressure')),
            'of_ratio': _finite_positive(md.get('of_ratio')),
            'manufacturer': 'HRMA',
            'certification_status': 'Experimental',
            # ÖH D33 / OH-D32-10 — teslim edilen ``specific_impulse``in
            # iki-faz düzeltme DURUMU. Çözücüden OKUNUR (tek tanım noktası);
            # yayımlanmamışsa eksiklik adıyla beyan edilir, sessizce
            # "düzeltilmiş" sayılmaz.
            **self.resolve_two_phase_correction(md),
        }
    
    #: Pencere apojeye yetmediğinde AYNI entegrasyonun (aynı dt, aynı fizik)
    #: kaç adım daha sürdürülebileceği. Adlandırılmış tavan: aşılırsa apoje
    #: İDDİA EDİLMEZ (ÖH Z5S / P9B3-19).
    APOGEE_CONTINUATION_MAX_STEPS = 20000

    def _continue_to_apogee(self, dt, t0, state, curve_t, curve_f,
                            dry_mass, prop_mass, ref_area, cd,
                            total_impulse_curve):
        """Pencere bittiğinde AYNI 1-DOF çözümü apojeye kadar sürdürür.

        Yeni bir model DEĞİLDİR: adım büyüklüğü, ISA sürükleme yasası, kütle
        tüketimi ve itki ara-değerlemesi ``generate_flight_profile``in ana
        döngüsüyle birebir aynıdır; yalnız zaman ekseni uzar. Döndürülen
        diziler DEĞİŞMEZ — bu yüzden apoje yakalanan koşumlarda çıktı
        bit-aynı kalır.

        Döner: ``(apoje_irtifa|None, apoje_zamani|None, adım, tavan_aşıldı)``
        """
        alt, vel, mass, _landed = state
        t = float(t0)
        for adim in range(1, int(self.APOGEE_CONTINUATION_MAX_STEPS) + 1):
            t += dt
            thrust = (float(np.interp(t, curve_t, curve_f, left=0.0, right=0.0))
                      if curve_t.size else 0.0)
            weight = mass * G_0
            rho = _air_density(alt)
            drag = 0.5 * rho * cd * ref_area * vel * abs(vel)
            acceleration = (thrust - weight - drag) / mass if mass > 0 else -G_0
            vel += acceleration * dt
            alt += vel * dt
            if total_impulse_curve > 0.0 and thrust > 0.0:
                mass = max(dry_mass,
                           mass - prop_mass * (thrust * dt) / total_impulse_curve)
            if alt <= 0.0:
                return 0.0, t, adim, False
            if vel <= 0.0:
                return alt, t, adim, False
        return None, None, int(self.APOGEE_CONTINUATION_MAX_STEPS), True

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
                # ÖH Z5S / P9B3-19: apoje alanları başarılı yanıtla aynı
                # şekilde taşınır (çağıran taraf KeyError yemesin).
                'apogee_altitude': None,
                'apogee_time': None,
                'apogee_status': 'not_computed',
                'max_altitude_is_apogee': False,
                'apogee_continuation_steps': 0,
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
        total_impulse_curve = float(_trapezoid(curve_f, curve_t)) if curve_t.size > 1 else 0.0
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

        # ------------------------------------------------------------------
        # APOJE GERÇEKTEN YAKALANDI MI? (ÖH Z5S / P9B3-19)
        # ------------------------------------------------------------------
        # ÖLÇÜLDÜ (27 Ağustos 2026, gerçek katı motor + 12 kg'lık araç):
        # pencere 0..15,267 s (600 adım), tepe SON adımda (599/599) ve son
        # adımdaki dikey hız hâlâ +111,81 m/s. Yani araç tırmanmaya devam
        # ederken kesilen pencerenin son noktası ``max_altitude`` adıyla
        # dönüyordu; yanıtın hiçbir yerinde apoje sözcüğü geçmiyordu.
        #
        # Onarım UYDURMA SAYI ÜRETMEZ: döndürülen diziler AYNEN kalır (apoje
        # pencerede yakalandığında çıktı bit-aynıdır) ve apoje iddiası ayrı
        # bir alanda, AYNI entegrasyon sürdürülerek ölçülür. Tavan aşılırsa
        # apoje None kalır ve bu beyan edilir.
        tirmandi = any(v > 0.0 for v in velocity_points)
        zirve_idx = int(np.argmax(altitude_points))
        apogee_altitude = None
        apogee_time = None
        apogee_steps = 0
        if not tirmandi:
            apogee_status = 'no_liftoff'
            apogee_altitude = float(altitude_points[zirve_idx])
            apogee_time = float(time_points[zirve_idx])
        elif landed or velocity_points[-1] <= 0.0:
            apogee_status = 'reached_in_window'
            apogee_altitude = float(altitude_points[zirve_idx])
            apogee_time = float(time_points[zirve_idx])
        else:
            dt_son = float(time_points[-1] - time_points[-2]) \
                if time_points.size > 1 else 0.0
            apogee_altitude, apogee_time, apogee_steps, tavan = \
                self._continue_to_apogee(
                    dt_son, float(time_points[-1]),
                    (current_altitude, current_velocity, mass, landed),
                    curve_t, curve_f, dry_mass, prop_mass, ref_area, cd,
                    total_impulse_curve)
            apogee_status = 'not_reached' if tavan else 'reached_after_window'

        max_altitude_is_apogee = (apogee_status in ('reached_in_window',
                                                    'no_liftoff'))

        method = (
            ('EXAMPLE VEHICLE (not the user rocket) - ' if ornek_arac else '')
            + '1-DOF time-marched integration with ISA drag, using the '
              'thrust curve above')
        if apogee_status == 'reached_after_window':
            method += (
                f' - NOTE: the vehicle is still climbing at the last sample '
                f'(v = {velocity_points[-1]:+.1f} m/s), so max_altitude is the '
                f'highest point INSIDE the simulated window, NOT the apogee; '
                f'continuing the same integration reaches apogee at '
                f'{apogee_altitude:.1f} m (t = {apogee_time:.1f} s)')
        elif apogee_status == 'not_reached':
            method += (
                f' - WARNING: the vehicle is still climbing at the last sample '
                f'(v = {velocity_points[-1]:+.1f} m/s) and the apogee was NOT '
                f'reached within {self.APOGEE_CONTINUATION_MAX_STEPS} further '
                f'integration steps: max_altitude is a truncated window value, '
                f'NOT the apogee, and no apogee is claimed')
        elif apogee_status == 'no_liftoff':
            method += (' - NOTE: the vehicle never leaves the pad in this '
                       'model (thrust never exceeds weight)')

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
            # geldiği artık açıkça yazılı (denetim bulgusu: 134x fark). Üçüncü
            # bir soru daha yanıtlanıyor (P9B3-19): bu sayı apoje MI?
            'max_altitude_method': method,
            'apogee_altitude': apogee_altitude,
            'apogee_time': apogee_time,
            'apogee_status': apogee_status,
            'max_altitude_is_apogee': max_altitude_is_apogee,
            'apogee_continuation_steps': apogee_steps,
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