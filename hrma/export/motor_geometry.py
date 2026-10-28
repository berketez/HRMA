"""Katı ve sıvı motor sonuçlarını ortak motor-geometri sözlüğüne çevirir.

Kesit çizimi (create_improved_motor_cross_section), STEP/STL üreticileri ve
teknik çizimler hibrit-şekilli, METRE bazlı bir motor_data sözlüğü bekler.
Katı motor rotası mm bazlı, sıvı motor rotası KARIŞIK birimli (chamber mm,
throat/exit m) sonuç döndürür — dönüşümler burada tek noktada yapılır.

BİRİM SÖZLEŞMESİ (Faz 5B / H4-2) — bu modül dışa aktarım katmanının TEK
birim otoritesidir. Ölçüldü (HEAD 9d3728e, 3 Ağustos 2026): ``/calculate_solid``
yanıtı doğrudan ``/api/export-dxf``e verilince çizim ``Ø_chamber = 100000.0 mm``
(gerçek 100.0), ``Ø_throat = 47927.25 mm`` (gerçek 47.93), STEP/STL zarfları da
1000× büyük çıkıyordu; sıvıda ``Ø_chamber = 99192.1 mm`` yazarken boğaz/çıkış
DOĞRU idi — yani TEK çizimde kamara lülenin 1000 katıydı. Sebep: üreticilerin
her biri girdiyi koşulsuz METRE kabul edip 1000 ile çarpıyordu
(``drawing_generator._dims_mm``, ``step_export``, ``cad_visualization``), oysa
katı rotası mm, sıvı rotası karışık birim döndürüyor.

Çözüm tek noktada: ``normalise_export_geometry`` gelen sözlüğün birimini
AÇIKÇA çözer ve METRE cinsinden bir kopya döndürür; kopya ``length_units='m'``
beyanını ve alan-başına hangi yoldan çözüldüğünü gösteren
``geometry_unit_resolution`` kaydını taşır. Çözüm sırası:

  1. ``motor_geometry`` alt sözlüğü — bu modülde normalize edilmiştir, SI
     GARANTİLİ (``/calculate_solid`` ve ``/calculate_liquid`` yanıtlarında
     hazır gelir).
  2. ``length_units`` beyanı ('m' / 'mm').
  3. Büyüklük çıkarımı — eşikler aşağıda tek yerde tanımlı.

Hiçbir yolda çözülemeyen alan **uydurulmaz**: değer ``None`` kalır ve
üreticiler "hesaplanmadı" diye beyan eder.
"""

import numpy as np

from hrma.utils.input_guard import (
    finite_number, finite_positive, first_finite_positive)


def _num(v, fb):
    """Sonlu sayı ya da ``fb`` yedeği — kural merkezden (OH-D27-11)."""
    return finite_number(v, fb)


# ---------------------------------------------------------------------------
# Birim çıkarım eşikleri — TEK tanım noktası (CLAUDE.md kural 11).
# ---------------------------------------------------------------------------
# Bu sınıftaki (amatör/üniversite) motorlarda bir çap metre cinsinden 1 m'yi,
# bir boy 5 m'yi geçmez; geçiyorsa değer milimetredir. Eşikler daha önce
# ``openrocket_integration.py`` içinde tanımlıydı ve dışa aktarımın geri
# kalanından habersizdi; artık oradan da buradan içe aktarılır.
#
# ÖH D21 / defter P9B2-18 — BU YORUM KODLA ÇELİŞİYORDU. Eski metin, belirsiz
# banttaki bir çapın (örnek olarak 1,0) MİLİMETRE sayıldığını yazıyordu;
# ÖLÇÜLDÜ (taban ``35aa279``, ``once.json`` bölüm B) ki kod öyle okumuyor:
#
#   length_in_meters_banded(1.0, 'chamber_diameter') -> (1.0, 'si')
#   length_in_meters_banded(1.0, 'throat_diameter')  -> (None, 'ambiguous')
#
# Yani yorumun vaat ettiği 0,001 m ile kodun ürettiği 1,0 m arasında **1000
# kat** fark vardı ve yorum kodun ÜÇÜNCÜ davranışından (ambiguous -> sayı
# üretilmez) hiç söz etmiyordu. Yorum, aşağıdaki İKİ-OKUMA BİRLEŞİM KURALI
# yazılmadan önceki tek-eşikli sezgiyi anlatıyordu ve o kural geldiğinde
# güncellenmemişti. Bugünkü hüküm iki yerde birden yazılı olmasın diye
# eşiklerin yanında SEZGİ değil yalnız EŞİK tanımı durur; hangi okumanın
# seçileceğini ``length_in_meters_banded`` (bandı olan alan) ve
# ``length_in_meters`` (bandı olmayan alan) tanımlar.
# ÖH D31 / defter P7B1-06 (ÖK-16) — ÇAP TAVANI ARTIK ELLE YAZILMIYOR.
# Eski satır ``DIAMETER_SI_MAX_M = 1.0`` idi ve doğrulayıcının kanonik
# ``chamber_diameter`` bandıyla (üst uç 5,0 m) çelişiyordu: aynı fiziksel
# büyüklüğün iki zarfı. Çelişki bandı OLMAYAN çap alanlarında (kasa çapı:
# ``case_outer_diameter`` / ``casing_diameter`` / ``case_diameter``) CANLIYDI —
# 1,5 m'lik meşru bir kasa ``.eng`` başlığına 1,5 mm olarak giriyordu (1000
# kat). Ölçüm ve türetim gerekçesi tek kaynakta:
# ``hrma.validation.motor_validation.DIAMETER_UNIT_INFERENCE_MAX_M``.
# Bandı OLAN alanlar bu tavanı zaten kullanmaz; onlar aşağıdaki iki-okuma
# birleşim kuralıyla kendi kanonik bantlarından çözülür.
# ÖH D32 / aynı kalemin UZUNLUK ayağı — BOY TAVANI DA ELLE YAZILMIYOR.
# Eski satır ``LENGTH_SI_MAX_M = 5.0`` idi; kanonik ``chamber_length`` bandının
# üst ucu 20,0 m'dir. Çelişki bandı OLMAYAN boy alanlarında (``nozzle_length``,
# ``nozzle_convergent_length``, ``nozzle_divergent_length``) CANLIYDI: 6 m'lik
# meşru bir lüle 6 mm olarak okunuyordu (ölçüm: D32 a1 ``once.json`` B3).
# ``THICKNESS_SI_MAX_M`` kasten sabit kaldı — ``wall_thickness`` için kanonik
# bir üst uç YOK, türetilecek sayı da yok (gerekçe tek kaynakta).
from hrma.validation.motor_validation import (
    DIAMETER_UNIT_INFERENCE_MAX_M as _DIAMETER_UNIT_INFERENCE_MAX_M,
    LENGTH_UNIT_INFERENCE_MAX_M as _LENGTH_UNIT_INFERENCE_MAX_M)

DIAMETER_SI_MAX_M = _DIAMETER_UNIT_INFERENCE_MAX_M
LENGTH_SI_MAX_M = _LENGTH_UNIT_INFERENCE_MAX_M
THICKNESS_SI_MAX_M = 0.1


# ---------------------------------------------------------------------------
# İMALAT PAKETİNİN EKSEN SÖZLEŞMESİ (ÖH D26 / defter P15B4-01)
# ---------------------------------------------------------------------------
# Kusur: aynı ZIP'in içindeki iki katı temsili 90° dönüktü. STEP katıları
# ``step_export._revolve_profile`` ile ``Axis.X`` etrafında dönüyordu; STL
# mesh'leri ``cad_visualization`` tarafından +Z ekseninde kuruluyordu. Montajı
# bu iki dosyadan kuran kullanıcı parçaları çakıştıramaz.
#
# ÖLÇÜLDÜ (taban 7751531, ``docs/scofield/raw/OH/D26/ihracat/a1/once.json``
# -> ``P15B4-01``, üç motor tipinin GERÇEK çözücü sonuçlarıyla):
#
#   ========  ==========  ==========================  ==========================
#   motor     parça       STEP (X, Y, Z) [mm]         STL (X, Y, Z) [mm]
#   ========  ==========  ==========================  ==========================
#   hibrit    chamber     346,837 / 227,815 / 227,815  227,815 / 227,815 / 346,837
#   hibrit    fuel_grain  182,889 / 184,330 / 184,330  184,330 / 184,330 / 182,889
#   katı      chamber     612,168 / 104,800 / 104,800  104,800 / 104,800 / 612,168
#   katı      fuel_grain  500,000 / 100,000 / 100,000  100,000 / 100,000 / 500,000
#   sıvı      chamber     229,667 /  93,604 /  93,604   93,604 /  93,604 / 229,667
#   ========  ==========  ==========================  ==========================
#
# Sayılar birebir aynı, sıra dönük: 5 parça / 3 motor. Paketin hiçbir yerinde
# de eksen adı geçmiyordu (``x-axis`` / ``z-up`` / ``orientation`` sayacı 0).
#
# HÜKÜM: paketin TEK eksen sözleşmesi vardır ve o da imalat tarafının
# (STEP + DXF) zaten kullandığı **+X**'tir. STL'ler bu sözleşmeye çevrilerek
# yazılır (mesh'lerin bellek içi +Z kurulumu — 3B görüntüleyici, kütle dökümü
# ve ``_measured_envelope_length_mm``in "assembly axis is z" ölçümü — aynen
# kalır; çevrim yalnız DOSYAYA yazılan kopyaya uygulanır, birim ölçeklemesiyle
# aynı desen). Sözleşme burada TEK yerde yazılıdır; hem STEP künyesi hem CAD
# paketi buradan okur (CLAUDE.md kural 11).

#: İmalat paketindeki (STEP + STL + DXF) katıların motor ekseni.
EXPORT_AXIS = 'X'

#: Mesh'lerin BELLEK İÇİNDE kurulduğu eksen (görüntüleyici / kütle / zarf).
MESH_BUILD_AXIS = 'Z'

#: Bellek içi mesh'i pakete çevirmek için gereken dönme (derece, +Y ekseni
#: etrafında): ``+Z -> +X``.
MESH_TO_EXPORT_ROTATION_DEG = 90.0

EXPORT_AXIS_NOTE = (
    'axis convention: motor axis = +' + EXPORT_AXIS + ', ' +
    EXPORT_AXIS.lower() + ' = 0 at the injector face. Every solid in this '
    'package (STEP and STL) uses it, so the files can be opened together '
    'without rotating anything.')

#: Birimi KAZANILMAMIŞ çözüm etiketleri (P16B4-02). Bu iki etiketin ortak
#: anlamı şudur: alan GİRDİDE VARDI, sayısı okunabildi, ama hangi birimde
#: yazıldığı kanıtlanamadı. ``normalise_export_geometry`` böyle bir alanı
#: kopyadan DÜŞÜRÜR (fail-closed) — dolayısıyla aşağı akıştaki her tüketici
#: "alan yoktu" ile "alan vardı ama birimi kazanılmadı" durumlarını AYIRT
#: EDEBİLMEK için rapordaki bu etikete bakmak zorundadır. Etiket dizgeleri
#: iki modülde ayrı ayrı yazılıydı; tek tanım noktası burasıdır
#: (CLAUDE.md kural 11).
UNEARNED_UNIT_SOURCES = frozenset({'ambiguous', 'out_of_band'})

#: İhracat sözleşmesinin zaman-çözümlü eğriden GERÇEKTEN OKUDUĞU alanlar.
#:
#: ÖH D25 / OH-D23-14. Bu demet bir "kısaltma listesi" değil, ölçülmüş bir
#: TÜKETİCİ KÜMESİDİR: ``OpenRocketExporter.real_thrust_curve`` yalnız
#: ``time`` + ``thrust`` dizilerini, ``_thrust_curve_label`` yalnız çözücünün
#: ``basis`` beyanını okur. Küme daralmasın diye bekçiye BAĞLANMIŞTIR
#: (tests/test_d25_kati_a1.py::TestOHD2314EgriYinelenmiyor): izdüşümün
#: çözdüğü nokta listesi, kaynak etiketi ve .eng gövdesi TAM sözlükle
#: üretilenle bayt-aynı olmak zorundadır. Tüketici yarın ``pressure``
#: okumaya başlarsa bekçi kırmızıya döner; sessiz bilgi kaybı yok.
THRUST_CURVE_EXPORT_FIELDS = ('time', 'thrust', 'basis')

#: ÖH V3 CAD · CADI D-T6-5 — lüle konturu bloğunun dışa aktarımda
#: GERÇEKTEN OKUNAN alt blokları (``nozzle_design.
#: sample_nozzle_inner_contour``: ``convergent.throat_radius_curvature``,
#: ``divergent.type/throat_angle/exit_angle/half_angle/length``).
#: ÖLÇÜLDÜ (14 Eki, CADI devri): ``solid_/liquid_results_to_motor_geometry``
#: ``nozzle_contour``u HİÇ taşımıyordu; katı/sıvı CAD paketinin lülesi
#: (``/export_solid_cad``, ``/export_liquid_cad``) her zaman Rao 0,382·rt
#: yayıyla ve kayıtlı açılarla çiziliyor, aynı gövdeyi okuyan STEP/DXF uçları
#: ise yayımlanan yayı ve açıları kullanıyordu. Taşıma izdüşümdür
#: (``THRUST_CURVE_EXPORT_FIELDS`` sözleşmesi): çözücünün kendi
#: ``points`` + ``_basis`` dökümü ikinci kez serileştirilmez — katı/sıvı
#: çözücü yalnız onları yayımladığı için ``motor_geometry`` yanıt bloğu
#: değişmez.
NOZZLE_CONTOUR_EXPORT_BLOCKS = ('convergent', 'divergent')

#: ÖH V3 CAD · CADK D-T7-2 (15 Eki; §28-50 (b)) — ihracat yükünde SÖZLÜK
#: olması gereken iç bloklar. Dışa aktarıcılar bunları zincirle okur
#: (``(r.get('design_summary') or {}).get('nozzle')`` gibi); istemci
#: gövdesinde biri metin ya da liste gelirse okuyucu AttributeError ile
#: düşüyor ve uç 500 veriyordu. ÖLÇÜLDÜ (main a61cfddb; örnek katı, sıvı ve
#: hibrit yanıtının her sözlük bloğu derinlik 1-2'de 'x' yapıldı, 16 POST
#: ihracat ucu × 2 taşıyıcı = 10 720 istek): 108 vaka 500, 9 uç, aşağıdaki
#: 17 yolun hepsi. Yolun her ÖNEKİ de sözlük olmalıdır (örneğin
#: ``heat_transfer_analysis``). ``None`` = verilmedi (okuyucular onu boş
#: sayar); sözlük olmayan başka her değer adlı 422 ile reddedilir.
EXPORT_OBJECT_BLOCKS = (
    ('structural_analysis',),
    ('structural_analysis', 'safety_analysis'),
    ('structural_analysis', 'chamber_analysis'),
    ('heat_transfer_analysis', 'wall_analysis'),
    ('heat_transfer_analysis', 'cooling_analysis'),
    ('heat_transfer_analysis', 'gas_side_analysis'),
    ('heat_transfer_analysis', 'safety_analysis'),
    ('design_summary',),
    ('design_summary', 'key_dimensions'),
    ('design_summary', 'nozzle'),
    ('motor_geometry',),
    ('nozzle_angles',),
    ('nozzle_design', 'geometry'),
    ('grain_design',),
    ('injector_design',),
    ('cooling_system',),
    ('cad_design', 'case_design'),
)


def first_non_object_export_block(payload):
    """İhracat yükünde sözlük olması gerekip olmayan ilk iç blok.

    ``(noktalı_yol, tip_adı)`` döner; sorun yoksa ``None``. Hibrit yanıtı
    blokları ``motor`` altında taşıdığı için o alt sözlük de aynı listeyle
    denetlenir (yol ``motor.`` önekiyle).
    """
    if not isinstance(payload, dict):
        return None
    kokler = [('', payload)]
    if isinstance(payload.get('motor'), dict):
        kokler.append(('motor.', payload['motor']))
    for onek, kok in kokler:
        for yol in EXPORT_OBJECT_BLOCKS:
            cur = kok
            for i, anahtar in enumerate(yol):
                deger = cur.get(anahtar)
                if deger is None:
                    break
                if not isinstance(deger, dict):
                    return onek + '.'.join(yol[:i + 1]), type(deger).__name__
                cur = deger
    return None


#: Birimi çözülen uzunluk alanları ve her birinin SI üst sınırı.
EXPORT_LENGTH_FIELDS = {
    'chamber_diameter': DIAMETER_SI_MAX_M,
    'throat_diameter': DIAMETER_SI_MAX_M,
    'exit_diameter': DIAMETER_SI_MAX_M,
    'port_diameter_initial': DIAMETER_SI_MAX_M,
    'port_diameter_final': DIAMETER_SI_MAX_M,
    'chamber_length': LENGTH_SI_MAX_M,
    'grain_length': LENGTH_SI_MAX_M,
    'nozzle_length': LENGTH_SI_MAX_M,
    'nozzle_convergent_length': LENGTH_SI_MAX_M,
    'nozzle_divergent_length': LENGTH_SI_MAX_M,
}

# ---------------------------------------------------------------------------
# İKİ-OKUMA BİRLEŞİM KURALI (ÖH D16 / P16B4-02, ÖK-16)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (taban 6fde52b, ``once_uc.json`` P16B4-02): ``/api/export-stl``a
# ``chamber_diameter = 1.5`` verildiğinde HTTP 200 + imalata gidebilecek bir
# STL iniyordu; ölçülen zarf 56 x 56 x 348 mm idi. Çünkü tek eşikli sezgi
# (``f > DIAMETER_SI_MAX_M -> mm``) 1,5'i 1,5 MİLİMETRE okuyordu. Aynı
# ölçümde ``0.1`` (m) ile ``100.0`` (mm) girdileri BAYT-AYNI dosya üretti —
# yani girdi sessizce yeniden yorumlanıyordu.
#
# Kök: ``DIAMETER_SI_MAX_M = 1.0`` eşiği, doğrulayıcının KENDİ yazılı bandı
# ``chamber_diameter [0,01; 5,0] m`` ile çelişiyor (ÖK-16'nın adıyla andığı
# çelişki). 1,5 m'lik bir hazne bandın İÇİNDEdir; 1,5 mm'lik hazne bandın
# dışında. Yani "belirsiz" değil, TEK okuması makul olan bir sayı yanlış
# okunuyordu.
#
# Kural (deponun kendi emsali — ``motor_validation.py`` GIRDI_BANT_ESLEME
# 3. tuzağı: *"iki okumanın BİRLEŞİMİ uygulanır, yalnız HER İKİ okumada da
# imkânsız olan değer reddedilir"*):
#
#   metre okuması makul & mm okuması değil  -> METRE
#   mm okuması makul & metre okuması değil  -> MİLİMETRE
#   İKİSİ de makul                          -> BELİRSİZ, sayı üretilmez
#   İKİSİ de imkânsız                       -> BANT DIŞI, sayı üretilmez
#
# Bant YENİDEN YAZILMAZ: doğrulayıcının ``MotorDataValidator.limits``
# sözlüğünden okunur (tek kaynak, CLAUDE.md kural 11). Bandı olmayan alan
# eski tek-eşikli sezgiye düşer ve bunu raporunda ``si``/``mm`` diye söyler.
_BAND_ALAN_TAKMA = {
    'port_diameter_initial': 'port_diameter',
    'port_diameter_final': 'port_diameter',
}


def _plausible_band_m(key):
    """``key`` için doğrulayıcının yazılı METRE bandı, ya da ``None``."""
    try:
        from hrma.validation.motor_validation import MotorDataValidator
    except Exception:      # pragma: no cover - doğrulayıcı yoksa eski yol
        return None
    band = MotorDataValidator().limits.get(_BAND_ALAN_TAKMA.get(key, key))
    if not isinstance(band, dict) or band.get('unit') != 'm':
        return None
    try:
        return float(band['min']), float(band['max'])
    except (KeyError, TypeError, ValueError):
        return None


def length_in_meters_banded(value, key, si_max):
    """Birimi İKİ OKUMANIN BİRLEŞİMİYLE çözer (P16B4-02).

    Döner: ``(metre veya None, kaynak)``; kaynak ``'si'`` / ``'mm'`` /
    ``'ambiguous'`` / ``'out_of_band'`` / ``'missing'``.

    Okuma kapısı merkezden gelir (``input_guard.finite_positive``, ÖH D28 /
    OH-D27-11): bu, ``.eng``/STEP hattının GERÇEK giriş noktasıdır — sekiz
    adlı çevirici bağlandıktan SONRA bile ``True`` buradan 1,0 m olarak
    geçiyordu (ölçüldü, ``once_urun.json``).
    """
    f = finite_positive(value)
    if f is None:
        return None, 'missing'

    band = _plausible_band_m(key)
    if band is None:
        return length_in_meters(f, si_max)

    lo, hi = band
    metre_makul = lo <= f <= hi
    mm_makul = lo <= f / 1000.0 <= hi
    if metre_makul and not mm_makul:
        return f, 'si'
    if mm_makul and not metre_makul:
        return f / 1000.0, 'mm'
    if metre_makul and mm_makul:
        # Sayı her iki birimde de gerçek bir motora karşılık geliyor;
        # hangisi olduğu KAZANILMADI, dolayısıyla yayımlanmaz.
        return None, 'ambiguous'
    return None, 'out_of_band'


#: ``length_units`` beyanında kabul edilen yazımlar.
_DECLARED_METRE = frozenset({'m', 'metre', 'meter', 'metres', 'meters', 'si'})
_DECLARED_MM = frozenset({'mm', 'millimetre', 'millimeter', 'millimetres',
                          'millimeters'})

#: Grain verisi bulunamadığında üreticilerin basacağı gerekçe. Sıvı çift
#: yakıtlı motorda katı yakıt bloğu FİZİKSEL OLARAK yoktur; eski kod bu
#: durumda 240 mm boyunda, Ø30→50 mm portlu bir grain uydurup imalat
#: çizimine, STEP montajına ve STL'e koyuyordu (Faz 5B / H4-1).
GRAIN_NOT_IN_RESULT = (
    'NOT MODELLED: the analysis result carries no solid grain geometry '
    '(no grain_design, grain_length or port diameter). A liquid bipropellant '
    'engine has no grain; nothing is drawn in its place.')


def length_in_meters(value, si_max):
    """Bir uzunluğu metreye çevirir; birimi büyüklüğünden çıkarır.

    Döner: ``(metre veya None, 'si' | 'mm' | 'missing')``. Üst seviye motor
    sonuçları birimi beyan etmediği için başka yol yok; çağıran hangi yolun
    seçildiğini raporlar.
    """
    f = finite_positive(value)
    if f is None:
        return None, 'missing'
    if f > si_max:
        return f / 1000.0, 'mm'
    return f, 'si'


def declared_length_unit(motor_results):
    """``length_units`` beyanını çözer: 'm', 'mm' ya da None (beyan yok)."""
    declared = str((motor_results or {}).get('length_units') or '').strip().lower()
    if declared in _DECLARED_METRE:
        return 'm'
    if declared in _DECLARED_MM:
        return 'mm'
    return None


def resolve_length_m(motor_results, key, si_max=None):
    """Tek bir uzunluk alanını METRE olarak çözer; kaynağını da döndürür.

    Döner: ``(metre veya None, kaynak)``. Kaynak değerleri:
    ``motor_geometry`` (normalize blok, SI garantili), ``declared:m``,
    ``declared:mm``, ``si`` / ``mm`` (büyüklük çıkarımı), ``missing``.
    """
    md = motor_results if isinstance(motor_results, dict) else {}
    if si_max is None:
        si_max = EXPORT_LENGTH_FIELDS.get(key, LENGTH_SI_MAX_M)

    # Üç okuma yolunun ÜÇÜ de aynı merkezî kapıdan geçer
    # (``input_guard.finite_positive``, ÖH D28 / OH-D27-11). Bu iki dal
    # eskiden kendi ``float()`` denetimini yazıyordu ve normalize blok yolu
    # ``.eng`` hattının en sık kullanılan yoludur: ölçüldü ki sekiz adlı
    # çevirici bağlandıktan sonra bile ``chamber_length=True`` BURADAN
    # 1,0 m olarak geçiyordu (``once_urun.json``).
    geo = md.get('motor_geometry')
    if isinstance(geo, dict):
        f = finite_positive(geo.get(key))
        if f is not None:
            return f, 'motor_geometry'

    declared = declared_length_unit(md)
    if declared is not None:
        f = finite_positive(md.get(key))
        if f is None:
            return None, 'missing'
        return (f if declared == 'm' else f / 1000.0), f'declared:{declared}'

    # ÖH D16 / P16B4-02: beyan yoksa iki-okuma birleşim kuralı işler.
    value, unit = length_in_meters_banded(md.get(key), key, si_max)
    return value, unit


def resolve_grain_m(motor_results):
    """Grain geometrisini METRE olarak çözer; yoksa ``None`` döner.

    Döner: ``(sözlük veya None, gerekçe)``. Sözlük anahtarları
    ``length``, ``port_initial``, ``port_final`` (metre; sonuncusu None
    olabilir) ve ``source``.

    UYDURMA YOK: boy ya da başlangıç portu çözülemiyorsa grain HİÇ
    döndürülmez — çağıran çizmez ve gerekçeyi basar.
    """
    md = motor_results if isinstance(motor_results, dict) else {}
    # Normalize blok varsa grain de oradan okunur (SI garantili).
    geo = md.get('motor_geometry')
    sources = []
    if isinstance(geo, dict):
        sources.append((geo, 'motor_geometry'))
    sources.append((md, 'motor result'))

    for node, label in sources:
        gd = node.get('grain_design') if isinstance(node, dict) else None
        gd = gd if isinstance(gd, dict) else {}
        # ``*_mm`` ekli anahtarlar birimini BEYAN eder — çıkarım yapılmaz.
        length_mm = _first_positive(gd.get('grain_length_mm'))
        port0_mm = _first_positive(gd.get('port_diameter_initial_mm'),
                                   gd.get('inner_diameter_mm'))
        port1_mm = _first_positive(gd.get('port_diameter_final_mm'),
                                   gd.get('outer_diameter_mm'))
        length_m = length_mm / 1000.0 if length_mm is not None else None
        port0_m = port0_mm / 1000.0 if port0_mm is not None else None
        port1_m = port1_mm / 1000.0 if port1_mm is not None else None
        src = f'{label}.grain_design (mm, declared)'

        if length_m is None or port0_m is None:
            # Beyansız üst seviye alanlar — birim çıkarımı ile.
            lv, lsrc = resolve_length_m(node, 'grain_length')
            p0, p0src = resolve_length_m(node, 'port_diameter_initial')
            p1, _p1src = resolve_length_m(node, 'port_diameter_final')
            if length_m is None and lv is not None:
                length_m, src = lv, f'{label}.grain_length ({lsrc})'
            if port0_m is None and p0 is not None:
                port0_m = p0
                src = f'{src}; port from {label} ({p0src})'
            if port1_m is None and p1 is not None:
                port1_m = p1

        if length_m is not None and port0_m is not None:
            return {'length': length_m, 'port_initial': port0_m,
                    'port_final': port1_m, 'source': src}, None

    return None, GRAIN_NOT_IN_RESULT


def _first_positive(*values):
    """İlk sonlu-pozitif değeri döndürür; yoksa None (uydurma yedek YOK).

    Kural merkezden okunur (``input_guard.first_finite_positive``,
    ÖH D28 / OH-D27-11).
    """
    return first_finite_positive(*values)


def normalise_export_geometry(motor_results):
    """Dışa aktarım üreticileri için girdiyi METRE'ye indirger.

    Döner: ``(kopya, rapor)``.

    * ``kopya`` — girdinin sığ kopyası; çözülebilen uzunluk alanları METRE
      olarak yeniden yazılır, ``length_units='m'`` beyanı eklenir. Çözülemeyen
      alanlar DOKUNULMAZ (uydurma değer yazılmaz) ve raporda ``missing``
      görünür.
    * ``rapor`` — ``{'fields': {alan: kaynak}, 'notes': [...],
      'grain': {...} | None, 'grain_reason': str | None}``.

    Fonksiyon idempotenttir: çıktısını tekrar verirseniz ``declared:m``
    yoluyla aynı değerleri döndürür (ölçüldü, bkz. tests/test_faz5_cizim_birim).
    """
    md = motor_results if isinstance(motor_results, dict) else {}
    out = dict(md)
    fields = {}
    notes = []

    for key, si_max in EXPORT_LENGTH_FIELDS.items():
        if key not in md and not isinstance(md.get('motor_geometry'), dict):
            continue
        value, source = resolve_length_m(md, key, si_max)
        if value is None:
            if key in md:
                fields[key] = (source if source in UNEARNED_UNIT_SOURCES
                               else 'missing')
                if source in UNEARNED_UNIT_SOURCES:
                    # ÖH D16 / P16B4-02 — FAIL-CLOSED: birimi kazanılmamış
                    # sayı kopyada BIRAKILMAZ. Bırakılırsa üreticiler onu
                    # koşulsuz METRE okur ve kusur yeniden doğar (ölçülen
                    # kusurun tam mekanizması buydu).
                    out.pop(key, None)
                    band = _plausible_band_m(key)
                    notes.append(
                        f'{key} = {md[key]!r} could NOT be resolved to a '
                        f'unit: ' + (
                            'both the metre and the millimetre reading fall '
                            'inside the validated band '
                            if source == 'ambiguous' else
                            'neither the metre nor the millimetre reading '
                            'falls inside the validated band ')
                        + (f'[{band[0]:g}; {band[1]:g}] m' if band else '')
                        + '. Declare length_units to resolve it; no value is '
                          'invented.')
            continue
        fields[key] = source
        if source in ('mm', 'declared:mm'):
            notes.append(f'{key} read as mm ({float(md[key]):.6g}) -> '
                         f'{value:.6g} m')
        out[key] = value

    grain, grain_reason = resolve_grain_m(md)
    if grain is not None:
        out['grain_length'] = grain['length']
        out['port_diameter_initial'] = grain['port_initial']
        if grain['port_final'] is not None:
            out['port_diameter_final'] = grain['port_final']
        fields['grain'] = grain['source']

    # Beyan: bundan sonra bu sözlüğü okuyan herkes METRE görür.
    out['length_units'] = 'm'
    report = {
        'fields': fields,
        'notes': notes,
        'grain': grain,
        'grain_reason': grain_reason,
    }
    out['geometry_unit_resolution'] = report
    return out, report


def unearned_unit_fields(unit_report):
    """Birimi kazanılamadığı için kopyadan DÜŞÜRÜLEN alanlar -> etiket.

    ``normalise_export_geometry`` raporunu alır, ``{alan: 'ambiguous' |
    'out_of_band'}`` döndürür. Rapor okunamıyorsa boş sözlük döner.

    NİYE VAR (ÖH D16 birleşme etkileşimi, 1 Eylül 2026 — ÖLÇÜLDÜ):
    P16B4-02'nin fail-closed düşürmesi doğru, ama tek başına bir BİLGİ KAYBI
    yaratıyor. Ölçüm (``_base_motor``, L* = 1,0 m, boğaz Ø25 mm, kamara
    Ø100 mm):

        chamber_length = 0.015  -> alan düşürüldü -> ihracat "boy hiç
                                   yayımlanmamış" sanıp L*'tan 62,5 mm
                                   TÜRETTİ ve çizdi
        chamber_length = 0.001  -> aynı 62,5 mm
        alan HİÇ YOK            -> aynı 62,5 mm, aynı künye dizgesi

    yani kullanıcının GİRDİĞİ bant dışı boy ile GİRDİSİZLİK ayırt edilemez
    hâle geldi — P9B1-05'in kapattığı kusurun ta kendisi (o gün üç yol da
    300 mm çiziyordu; bugün üçü de 62,5 mm çiziyor). Değer yayımlanmamalı
    (P16B4-02 haklı), ama alanın VARLIĞI da yutulmamalı: tüketici bu
    fonksiyonla "vardı, kazanılmadı" durumunu görür ve ADIYLA reddeder.
    """
    if not isinstance(unit_report, dict):
        return {}
    alanlar = unit_report.get('fields')
    if not isinstance(alanlar, dict):
        return {}
    return {k: v for k, v in alanlar.items()
            if v in UNEARNED_UNIT_SOURCES}


def _real_mm(*values):
    """Verilen adaylardan ilk sonlu-pozitif MİLİMETRE değerini döndürür.

    Hiçbiri geçerli değilse None döner — uydurma varsayılan ÜRETİLMEZ.
    """
    return first_finite_positive(*values)


def _put_nozzle_lengths(out, conv_mm, div_mm):
    """Çözücünün lüle uzunluklarını METRE olarak ortak sözlüğe yazar.

    Faz 4B / A5: bu sözlük lüle uzunluğunu HİÇ taşımıyordu; tüketici
    (``nozzle_design.sample_nozzle_inner_contour``) ıraksak boyu yeniden
    türetmek zorunda kalıyor ve bell lülede ``divergent_half_angle_deg``
    alanını (bell'de bu BOĞAZ açısıdır: bell_80 -> 30°, bell_60 -> 34°) konik
    yarı açı sanıyordu. Ölçüldü (HEAD a7ff1e7, 10 kN sıvı motor):
    bell_80 çözücü 107.69 mm / export 62.48 mm (-41.99%),
    bell_60 çözücü 80.77 mm / export 53.48 mm (-33.79%), konik +0.78%.

    Değer yoksa ANAHTAR HİÇ YAZILMAZ — 'hesaplanmadı' hâli, sıfır ya da
    uydurma bir sayı değil, anahtarın yokluğuyla bildirilir.
    """
    if conv_mm is not None:
        out['nozzle_convergent_length'] = conv_mm / 1000.0
    if div_mm is not None:
        out['nozzle_divergent_length'] = div_mm / 1000.0


def _carry_nozzle_contour(out, results):
    """Yayımlanan lüle konturunun dışa aktarımda okunan alt bloklarını
    (``NOZZLE_CONTOUR_EXPORT_BLOCKS``) TEK kaynaktan taşır (CADI D-T6-5).

    Sayı üretilmez, yalnız kopyalanır; blok yoksa anahtar yazılmaz (mevcut
    kural + beyan: örnekleyici Rao 0,382·rt ve kayıtlı açılarla çizer ve
    bunu ``divergent_length_source`` ile söyler). Alt blok sözlük değilse
    de AYNEN taşınır: tekil uçlarla aynı girdi aynı hükmü alır (sessiz
    süzme yok).
    """
    kontur = results.get('nozzle_contour')
    if not isinstance(kontur, dict):
        return
    izdusum = {a: kontur[a] for a in NOZZLE_CONTOUR_EXPORT_BLOCKS
               if a in kontur}
    if izdusum:
        out['nozzle_contour'] = izdusum


def solid_results_to_motor_geometry(results):
    """/calculate_solid sonucundan hibrit-şekilli geometri (m) üretir.

    Katıda 'port' çekirdek (core) deliğidir: başlangıç portu = core çapı.

    Son port için eskiden KOŞULSUZ ``grain_od_mm`` yazılıyordu, gerekçesi de
    "web tamamen yanar" diye not düşülmüştü. Bu yalnız iç yüzeyin yandığı
    (dış yüzey inhibitörlü) durumda doğrudur. Dış yüzey de yanıyorsa cephe
    İKİ taraftan ilerler, tükenme yarı web'te olur ve grain dışı hiçbir zaman
    porta dönüşmez.

    2026-08-03 (Faz 6, T07 kök nedeni) ölçümü: varsayılan Ø100/Ø30 grain'de
    inhibitör açık/kapalı arasında yanma süresi 2,1863 s -> 1,1757 s değişiyor
    ama ``port_diameter_final`` iki koşuda da 100,0 mm dönüyordu — yani
    tükenmenin yarıya indiğini bilen çözücüyle çelişiyordu. Çözücü doğru
    sayıyı zaten yayımlıyor (``grain_design.web_burnout_mm`` +
    ``web_basis``); burada o kullanılır, yoksa eski davranışa düşülür.
    """
    r = results or {}
    gd = r.get('grain_design') or {}
    ks = ((r.get('design_summary') or {}).get('key_dimensions')) or {}
    case = ((r.get('cad_design') or {}).get('case_design')) or {}

    # ÖH D23 / defter P15B4-06 — ÜRETEÇ VARSAYILANLARI KALDIRILDI.
    #
    # ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` P15B4-06):
    # ``solid_results_to_motor_geometry({})`` **18 anahtar** ve **14 sayı**
    # döndürüyordu — kamara Ø100 mm, çekirdek Ø30 mm, boğaz Ø20 mm, çıkış
    # Ø60 mm, tane boyu 500 mm, genleşme 9,0, basınç 40,0 bar — ve künye
    # alanı **0** idi: sözlüğe bakan hiç kimse bu sayıların çözücüden mi
    # yoksa bu fonksiyonun içinden mi geldiğini ayırt edemiyordu.
    #
    # Bunun ürün üzerindeki ölçülen sonucu, ``step_export``in kendi
    # fail-closed kapısının **hiç ateşlenmemesiydi**: kapı
    # (``step_export.py``, 'refusing to emit a manufacturing STEP built from
    # generator defaults') ``chamber_length``/``chamber_diameter``i sonlu ve
    # pozitif diye sınıyor; sabitler kapıdan ÖNCE enjekte edildiği için kapı
    # 'çözülemedi' hâlini görmüyor, imalata giden bir STEP tam da yasakladığı
    # şeyden — üreteç varsayılanlarından — doğuyordu (P7B2-05'in kökü).
    #
    # Kural: çözücünün YAYIMLAMADIĞI ölçü UYDURULMAZ. Anahtar hiç yazılmaz
    # (``_put_nozzle_lengths``in zaten uyguladığı sözleşme) ve hangi alanın
    # neden çözülemediği ``geometry_unresolved`` künyesinde adıyla durur.
    unresolved = {}

    def _coz(ad, *kaynaklar):
        """İlk sonlu değeri döndürür; hiçbiri yoksa None + künye kaydı."""
        for etiket, ham in kaynaklar:
            deger = _num(ham, None)
            if deger is not None:
                return deger
        unresolved[ad] = ('not published by the solver (looked at: %s)'
                          % ', '.join(e for e, _ in kaynaklar))
        return None

    grain_len_mm = _coz('grain_length',
                        ('grain_design.grain_length_mm',
                         gd.get('grain_length_mm')),
                        ('grain_length', r.get('grain_length')))
    chamber_d_mm = _coz('chamber_diameter',
                        ('cad_design.case_design.inner_diameter',
                         case.get('inner_diameter')),
                        ('chamber_diameter', r.get('chamber_diameter')))
    chamber_l_mm = _coz('chamber_length',
                        ('cad_design.case_design.length', case.get('length')),
                        ('design_summary.key_dimensions.motor_length_mm',
                         ks.get('motor_length_mm')),
                        # ÖH D23 / P15B4-14 ölçümü: çözücünün ÜST SEVİYE
                        # ``chamber_length``i bu listede HİÇ yoktu; 500 mm
                        # yayımlayan bir koşumun ``.eng``i 529,4 mm yazıyordu
                        # (türetme ``grain_length / 0,85``ten geliyordu).
                        # Çözücünün kendi sayısı türetmeden ÖNCE gelir.
                        ('chamber_length', r.get('chamber_length')),
                        # Türetme: tane boyu biliniyorsa kamara ondan gelir.
                        ('grain_length / 0.85',
                         None if grain_len_mm is None else grain_len_mm / 0.85))
    if chamber_l_mm is not None and grain_len_mm is not None:
        chamber_l_mm = max(chamber_l_mm, grain_len_mm * 1.05)
    core_d_mm = _coz('port_diameter_initial',
                     ('grain_design.inner_diameter_mm',
                      gd.get('inner_diameter_mm')),
                     ('core_diameter', r.get('core_diameter')))
    grain_od_mm = _coz('grain_outer_diameter',
                       ('grain_design.outer_diameter_mm',
                        gd.get('outer_diameter_mm')),
                       ('chamber_diameter - 4 mm liner',
                        None if chamber_d_mm is None else chamber_d_mm - 4.0))

    # Son port: çözücünün tükenen web'i varsa ondan türetilir (bkz. üstteki
    # açıklama). ``web_burnout_mm`` iç cepheden tüketilen kalınlıktır, port
    # yarıçapı o kadar büyür — yani çap 2× artar.
    web_burnout_mm = _num(gd.get('web_burnout_mm'), None)
    if (web_burnout_mm is not None and web_burnout_mm > 0
            and core_d_mm is not None and grain_od_mm is not None):
        port_final_mm = min(core_d_mm + 2.0 * web_burnout_mm, grain_od_mm)
    else:
        port_final_mm = grain_od_mm  # bilgi yoksa eski (tek cepheli) varsayım

    ang = r.get('nozzle_angles') or {}
    ds_noz = ((r.get('design_summary') or {}).get('nozzle')) or {}
    noz_geo = (r.get('nozzle_design') or {}).get('geometry') or {}

    out = {
        'motor_name': r.get('motor_name') or 'HRMA_SOLID',
        'grain_design': gd,
        'nozzle_angles': ang,
        'structural_analysis': r.get('structural_analysis') or {},
    }
    # Çözülemeyen alan YAZILMAZ (anahtarın yokluğu 'hesaplanmadı' demektir).
    for anahtar, mm in (('chamber_diameter', chamber_d_mm),
                        ('chamber_length', chamber_l_mm),
                        ('grain_length', grain_len_mm),
                        ('port_diameter_initial', core_d_mm),
                        ('port_diameter_final', port_final_mm)):
        if mm is not None:
            out[anahtar] = mm / 1000.0
    for anahtar, ham, kaynak in (
            ('throat_diameter', r.get('throat_diameter'), 'throat_diameter'),
            ('exit_diameter', r.get('exit_diameter'), 'exit_diameter')):
        deger = _num(ham, None)
        if deger is None:
            unresolved[anahtar] = ('not published by the solver (looked at: '
                                   '%s)' % kaynak)
        else:
            out[anahtar] = deger / 1000.0
    for anahtar, ham, kaynak in (
            ('expansion_ratio', r.get('expansion_ratio'), 'expansion_ratio'),
            ('chamber_pressure', r.get('chamber_pressure'), 'chamber_pressure'),
            ('burn_time', r.get('burn_time'), 'burn_time'),
            ('thrust', r.get('average_thrust'), 'average_thrust'),
            ('total_impulse', r.get('total_impulse'), 'total_impulse'),
            ('isp', r.get('specific_impulse'), 'specific_impulse'),
            ('propellant_mass_total', r.get('propellant_mass'),
             'propellant_mass')):
        deger = _num(ham, None)
        if deger is None:
            unresolved[anahtar] = ('not published by the solver (looked at: '
                                   '%s)' % kaynak)
        else:
            out[anahtar] = deger

    # ÖH D23 / defter P15B4-14 — ZAMAN-ÇÖZÜMLÜ EĞRİ TAŞINIR.
    #
    # ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` P15B4-14): AYNI katı motorun
    # ``.eng``i ham çözücü sözlüğünden **1722 bayt** (zaman-çözümlü grain
    # burn-back eğrisi), aynı sözlüğün BU fonksiyondan geçmiş hâlinden
    # **1522 bayt** (sabit-itki yaklaşımı) çıkıyordu — çünkü çözücünün
    # ``thrust_curve`` / ``transient`` blokları kopyaya hiç girmiyordu.
    # ``resolve_thrust_curve`` bu iki anahtarı arar, bulamayınca sabit itkiye
    # düşer ve bunu ``.eng`` yorumunda dürüstçe söyler — ama 'komple paket'
    # adıyla inen dosyanın, aynı koşumun DAHA AZ bilgisini taşıması, kaybın
    # kaçınılmaz olduğu izlenimini verir; oysa eğri elde vardır.
    #
    # ÖH D25 / OH-D23-14 — EĞRİ TAŞINIR AMA İKİ KEZ SERİLEŞTİRİLMEZ.
    # ÖLÇÜLDÜ (taban ``cdf2106``, ``once_ohd2314.json``): D23'ün kör kopyası
    # çözücünün DOKUZ anahtarlı ``thrust_curve`` sözlüğünü olduğu gibi
    # alıyordu; ``/calculate_solid`` yanıtında aynı 37.521 bayt hem üst
    # seviyede hem bu blokta duruyordu (sha256 aynı) — 313.020 baytlık
    # yanıtın **%11,99**'u. Oysa ihracat sözleşmesinin OKUDUĞU alanlar
    # ölçüldü: ``OpenRocketExporter.real_thrust_curve`` yalnız ``time`` ve
    # ``thrust`` dizilerini, ``_thrust_curve_label`` yalnız ``basis``
    # beyanını okur; ``pressure`` / ``burn_area`` / ``port_area`` /
    # ``mass_flow`` / ``sampling`` / ``port_area_basis`` hiçbir ihraç
    # üreticisi tarafından okunmuyor (git grep ile ölçüldü, 0 tüketici).
    # Blok artık sözleşmenin TÜKETTİĞİ izdüşümü taşır: .eng aynı 101
    # noktayı ve aynı ``thrust_curve`` kaynak etiketini üretir (bit-aynı),
    # yanıt ~25,8 KB küçülür. Eğrinin KENDİSİNİ düşürmek YASAK: ölçüldü ki
    # ön yüz ``/api/export-complete-zip``e (templates/solid.html:2773)
    # motor_data olarak YALNIZ bu bloğu gönderiyor; eğri düşerse paketin
    # ``.eng``i 101 noktadan 4 noktalık ``constant`` yaklaşımına iner —
    # yani P15B4-06 gerilemiş olur.
    for anahtar in ('thrust_curve', 'transient'):
        blok = r.get(anahtar)
        if isinstance(blok, dict) and blok:
            izdusum = {a: blok[a] for a in THRUST_CURVE_EXPORT_FIELDS
                       if a in blok}
            out[anahtar] = izdusum if izdusum else blok
        elif isinstance(blok, list) and blok:
            out[anahtar] = blok
    if unresolved:
        out['geometry_unresolved'] = unresolved
    _carry_nozzle_contour(out, r)
    # Katıda üç kaynak da aynı çözümden gelir; ilk gerçek değer kullanılır.
    _put_nozzle_lengths(
        out,
        _real_mm(ang.get('convergent_length_mm'),
                 ds_noz.get('convergent_length_mm'),
                 noz_geo.get('convergent_length')),
        _real_mm(ang.get('divergent_length_mm'),
                 ds_noz.get('divergent_length_mm'),
                 noz_geo.get('divergent_length')))
    return out


def hybrid_results_to_motor_geometry(results):
    """``/calculate`` (hibrit) sonucundan normalize geometri (m) üretir.

    ÖH D24 / defter P15B2-03 — ÜÇ MOTORUN ÜÇÜNCÜSÜNDE BLOK HİÇ YOKTU.

    ÖLÇÜLDÜ (taban ``88a29d3``, ``docs/scofield/raw/OH/D24/hibrit/a1/
    once.json`` bölüm B): ``/calculate_solid`` yanıtı 21 anahtarlı,
    ``/calculate_liquid`` yanıtı 16 anahtarlı bir ``motor_geometry`` bloğu
    taşırken hibrit yanıtta blok **HİÇ YOKTU** (``motor_geometry_var =
    false``). Yani birimi gerçekten METRE olan tek motor, dışa aktarım
    katmanının "SI garantili" okuma yolunu (``resolve_length_m`` -> kaynak
    ``motor_geometry``) hiç kullanamıyor; her tüketici ya üst seviyedeki
    ``length_units`` beyanını kendi çözmek ya da büyüklükten çıkarım yapmak
    zorunda kalıyordu. ``app.py``de ``chamber_diameter`` 121 kez geçiyor ve
    çoğu geçiş motor tipini bilmiyor.

    Bu fonksiyon YENİ BİR BİRİM SÖZLEŞMESİ KURMAZ: her alanı bu modülün
    kendi otoritesinden (``resolve_length_m``) geçirir, yani hibritte
    ``declared:m`` yolunu izler. Çözülemeyen alan UYDURULMAZ — anahtar hiç
    yazılmaz ve ``geometry_unresolved`` künyesinde NEREYE bakıldığı söylenir
    (katı koldaki sözleşmenin aynısı).

    Katı/sıvı kardeşlerinden tek farkı ``structural_analysis``ı KOPYALAMAMASI:
    hibrit sonucunda o blok zaten AYNI sözlüğün üst seviyesindedir ve
    referansı buraya da koymak yanıtı ikinci kez şişirirdi (ölçülen yanıt
    gövdesi hâlihazırda yüz kilobayt mertebesinde). Tüketici onu motor
    sözlüğünün kendisinden okur.
    """
    r = results or {}
    if isinstance(r.get('motor'), dict):
        r = r['motor']
    unresolved = {}

    out = {
        'motor_name': r.get('motor_name') or 'HRMA_HYBRID',
        # Blok BEYANLIDIR: aşağıdaki uzunluklar metredir. Beyan, tüketicinin
        # büyüklük çıkarımına düşmesini engeller (P15B2-03'ün adını verdiği
        # ``length_units = None`` hâli).
        'length_units': 'm',
        'grain_design': r.get('grain_design') or {},
        'nozzle_angles': r.get('nozzle_angles') or {},
    }

    for anahtar in ('chamber_diameter', 'chamber_length', 'grain_length',
                    'port_diameter_initial', 'port_diameter_final',
                    'throat_diameter', 'exit_diameter'):
        deger, kaynak = resolve_length_m(r, anahtar)
        if deger is None:
            unresolved[anahtar] = ('not resolved to metres (looked at: '
                                   '%s; unit source: %s)' % (anahtar, kaynak))
        else:
            out[anahtar] = deger

    for anahtar, ham, kaynak in (
            ('expansion_ratio', r.get('expansion_ratio'), 'expansion_ratio'),
            ('chamber_pressure', r.get('chamber_pressure'), 'chamber_pressure'),
            ('burn_time', r.get('burn_time'), 'burn_time'),
            ('thrust', r.get('thrust'), 'thrust'),
            ('total_impulse', r.get('total_impulse'), 'total_impulse'),
            ('isp', r.get('isp'), 'isp'),
            ('propellant_mass_total', r.get('propellant_mass_total'),
             'propellant_mass_total')):
        deger = _num(ham, None)
        if deger is None:
            unresolved[anahtar] = ('not published by the solver (looked at: '
                                   '%s)' % kaynak)
        else:
            out[anahtar] = deger

    # Zaman-çözümlü eğri taşınır (katı koldaki P15B4-14 sözleşmesinin aynısı).
    for anahtar in ('thrust_curve', 'transient'):
        if isinstance(r.get(anahtar), (dict, list)) and r.get(anahtar):
            out[anahtar] = r[anahtar]

    if unresolved:
        out['geometry_unresolved'] = unresolved

    ang = r.get('nozzle_angles') or {}
    ds_noz = ((r.get('design_summary') or {}).get('nozzle')) or {}
    noz_geo = (r.get('nozzle_design') or {}).get('geometry') or {}
    _put_nozzle_lengths(
        out,
        _real_mm(ang.get('convergent_length_mm'),
                 ds_noz.get('convergent_length_mm'),
                 noz_geo.get('convergent_length')),
        _real_mm(ang.get('divergent_length_mm'),
                 ds_noz.get('divergent_length_mm'),
                 noz_geo.get('divergent_length')))
    return out


def liquid_results_to_motor_geometry(results):
    """/calculate_liquid sonucundan hibrit-şekilli geometri (m) üretir.

    Dikkat — sıvı rotasının birimleri karışıktır: chamber_diameter ve
    chamber_length MM, throat_diameter ve exit_diameter METRE döner.
    """
    r = results or {}
    inj = r.get('injector_design') or {}
    ang = r.get('nozzle_angles') or {}
    cooling = r.get('cooling_system') or {}
    n_elem = _first_positive(inj.get('number_of_elements'))

    # ÖH D33-2 / defter OH-UC-09 — ÜRETEÇ VARSAYILANLARI KALDIRILDI
    # (P15B4-06'nın katı, P15B2-03'ün hibrit kardeşinde kapattığı sınıf).
    #
    # ÖLÇÜLDÜ (taban ``5e0714c1``, ``docs/scofield/raw/OH/D33-2/ihracat-cad/
    # a1/once.json`` bölüm B1): ``liquid_results_to_motor_geometry({})``
    # **14 anahtar / 10 sayı** döndürüyordu — kamara Ø150 mm, boy 300 mm,
    # boğaz Ø30 mm, çıkış Ø90 mm, genleşme 9,0, basınç 50,0 bar — ve
    # ``geometry_unresolved`` künyesi **HİÇ YOKTU**. Aynı çağrı katı
    # kardeşte 5 anahtar / 0 sayı / 14 künye, hibrit kardeşte 5 anahtar /
    # 0 sayı / 14 künye veriyordu: üç motorun üçüncüsü sessizce sayı
    # uyduruyordu.
    #
    # ``burn_time`` / ``thrust`` / ``isp`` / ``of_ratio`` için yedek 0,0 idi;
    # bu da "hesaplanmadı" hâlini SIFIR diye yayımlayan sessiz sıfırdır
    # (ölçüldü: dördü de 0,0 ile dönüyordu).
    #
    # Kural katı koldakinin aynısı: çözücünün YAYIMLAMADIĞI ölçü
    # UYDURULMAZ; anahtar hiç yazılmaz ve NEREYE bakıldığı
    # ``geometry_unresolved`` künyesinde adıyla durur.
    unresolved = {}

    def _coz(ad, kaynak, ham, olcek=1.0):
        """Sonlu değeri döndürür; yoksa None + künye kaydı."""
        deger = _num(ham, None)
        if deger is None:
            unresolved[ad] = ('not published by the solver (looked at: %s)'
                              % kaynak)
            return None
        return deger * olcek

    out = {
        'motor_name': r.get('motor_name') or 'HRMA_LIQUID',
        'nozzle_angles': ang,
        'injector_design': {
            'injector_type': inj.get('injector_type'),
            # v2.6.27: "12 delik / Ø1,5 mm" ikinci-katman uydurmaları
            # KALDIRILDI. Sıvı motor bu değerleri her başarılı koşuda kendisi
            # yayımlar (liquid_rocket_engine: number_of_elements /
            # fuel_orifice_diameter_mm); yayımlamadıysa None taşınır ve
            # imalat çıktısı (step_export) uydurmak yerine REDDEDER; çizim
            # katmanı da 'hesaplanmadı' beyan eder (uydurma yedek YOK).
            'number_of_orifices': (int(round(n_elem))
                                   if n_elem is not None else None),
            'orifice_diameter_mm': _real_mm(inj.get('fuel_orifice_diameter_mm')),
            # ÖH D33-2 / OH-UC-09: yedek 0,0 idi — "hesaplanmadı" hâlini
            # SIFIR bar diye yayımlıyordu (kardeş alanlar zaten None taşır).
            'injection_pressure_drop_bar':
                _num(inj.get('injection_pressure_drop_fuel_bar'), None),
        },
        # A8: imalata giden STEP cidar kalınlığını buradan okur. Bu anahtar
        # eskiden hiç taşınmıyordu; STEP 'chamber_analysis' arayıp bulamayınca
        # 0.045·D geometrik yedeğine düşüyordu. Sıvı motor cidarı
        # 'chamber_structure' bloğunda yayımlanır.
        'structural_analysis': r.get('structural_analysis') or {},
    }
    # V301 bilinen C2 — KANONİK PINTLE GEOMETRİSİ dışa aktarım gövdesine
    # AYNEN taşınır (sayı üretilmez, kopyalanır). Sıvı çözücü onu devre
    # ayrıntısında yayımlar (``injection_system.injector_design_detail
    # .pintle_geometry``); bu gövde onu taşımadığı için STEP/STL pintle'ı
    # çizemiyordu. CAD (``cad_visualization.pintle_cad_geometry``) onu
    # ``injector_design.pintle_geometry``den okur — hibritteki yerle aynı.
    _sistem = r.get('injection_system')
    _ayrinti = (_sistem.get('injector_design_detail')
                if isinstance(_sistem, dict) else None)
    _pintle = (_ayrinti.get('pintle_geometry')
               if isinstance(_ayrinti, dict) else None)
    if isinstance(_pintle, dict):
        out['injector_design']['pintle_geometry'] = dict(_pintle)
    # V301 CAD-2 kalem 8 — İKİ KATMANLI CİDARIN KANAL SAYISI dışa aktarım
    # gövdesine AYNEN taşınır (sayı üretilmez). CAD kanal/kaburga katmanını
    # bu sayıyla tartar (``cad_visualization.two_layer_rib_fraction``);
    # gövde onu taşımadığı için kütle tek malzemeli yedeğe düşüyordu. Yalnız
    # iki katmanlı rejeneratif cidarda yazılır (öteki yollar bit-aynı).
    from hrma.export.cad_visualization import TWO_LAYER_WALL_MODEL
    _cs = ((r.get('structural_analysis') or {}).get('chamber_structure')
           if isinstance(r.get('structural_analysis'), dict) else None)
    if (isinstance(_cs, dict)
            and _cs.get('wall_model') == TWO_LAYER_WALL_MODEL
            and isinstance(cooling.get('cooling_channels'), (int, float))
            and not isinstance(cooling.get('cooling_channels'), bool)):
        out['cooling_system'] = {
            'cooling_channels': cooling['cooling_channels'],
            'cooling_channels_source': (
                'cooling_system.cooling_channels of /calculate_liquid '
                '(copied for the CAD export)')}
    # Ölçüler: çözülen yazılır, çözülemeyen KÜNYEYE düşer (anahtar yazılmaz).
    # Birim uyarısı yukarıdaki docstring'de: chamber_* MM gelir, boğaz/çıkış
    # zaten METRE gelir.
    for anahtar, kaynak, ham, olcek in (
            ('chamber_diameter', 'chamber_diameter',
             r.get('chamber_diameter'), 0.001),
            ('chamber_length', 'chamber_length',
             r.get('chamber_length'), 0.001),
            ('throat_diameter', 'throat_diameter',
             r.get('throat_diameter'), 1.0),
            ('exit_diameter', 'exit_diameter', r.get('exit_diameter'), 1.0),
            ('expansion_ratio', 'expansion_ratio',
             r.get('expansion_ratio'), 1.0),
            ('chamber_pressure', 'chamber_pressure',
             r.get('chamber_pressure'), 1.0),
            ('burn_time', 'burn_time', r.get('burn_time'), 1.0),
            ('thrust', 'thrust', r.get('thrust'), 1.0),
            ('isp', 'isp_sea_level', r.get('isp_sea_level'), 1.0),
            ('of_ratio', 'mixture_ratio', r.get('mixture_ratio'), 1.0)):
        deger = _coz(anahtar, kaynak, ham, olcek)
        if deger is not None:
            out[anahtar] = deger
    if unresolved:
        out['geometry_unresolved'] = unresolved
    _carry_nozzle_contour(out, r)
    # Sıvıda nozzle_angles['nozzle_length_mm'] IRAKSAK boyudur (boğaz→çıkış,
    # calculate_nozzle_geometry içinde L_nozzle); yakınsak koni soğutma
    # bloğunda ayrı raporlanır. Ölçüldü: ikisi cooling_system'deki
    # convergent_length / divergent_length ile bit-aynı.
    _put_nozzle_lengths(
        out,
        _real_mm(cooling.get('convergent_length')),
        _real_mm(cooling.get('divergent_length'),
                 ang.get('nozzle_length_mm')))
    return out
