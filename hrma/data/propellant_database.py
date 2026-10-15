"""
Comprehensive Propellant Database
Fetches real chemical properties from open-source databases
Integrates with NASA CEA, NIST WebBook, and ProPEP databases
"""

import json
import requests
from typing import Dict, Optional, List

# ---------------------------------------------------------------------------
# Hibrit yakıt regresyon katsayıları — TEK TANIM NOKTASI (magic-number kuralı)
#
# Bağıntı (SI birimler): r_dot [m/s] = a * (G_ox [kg/m²·s])^n
#
# Literatür tabloları çoğunlukla r [mm/s], G_ox [g/cm²·s] biriminde verir;
# SI dönüşümü: a_SI = a_tablo * 1e-3 * 10^(-n)   (1 g/cm²·s = 10 kg/m²·s)
#
# Bu tablo hybrid_rocket_engine.py ve regression_analysis.py tarafından
# import edilir; değerleri başka dosyaya KOPYALAMAYIN.
#
# OPUS DENETİM NOTU (2026-07-12, bilinçli karar): Bu katsayılar literatürde
# G_OX bazlı korelasyonlardan gelir; regression_analysis varsayılanı ise
# Marxman G_TOTAL kapanışıdır. G_ox-fit katsayının G_total ile kullanımı
# regresyonu sistematik +%10-18 yükseltir — Rezaei HTPB/N2O ölçümüne göre
# model zaten −%32 DÜŞÜK tahminde olduğundan bu yön doğrulama ile uyumludur
# ve davranış testlerle korunmaktadır (VALIDATION_STATUS.md). G_ox-bazlı
# birebir karşılaştırma gerekirse flux_mode='ox' kullanın; G_total'e özgü
# yeniden fit gelecek iş olarak işaretlidir.
# ---------------------------------------------------------------------------

#: G_ox-fit katsayının G_total kapanışıyla koşturulmasının regresyona
#: getirdiği SİSTEMATİK yükseltme bandı [%] — (alt, üst).
#:
#: Sayı yukarıdaki OPUS DENETİM NOTU'ndan (2026-07-12) BİREBİR alındı;
#: burada YENİ bir ölçüm yoktur, yalnız yorumda duran bir sayı ada
#: kavuşturuldu. TEK TANIM YERİ (CLAUDE.md kural 11): hibrit motorun
#: yayımladığı "iki belirleme neden uzlaşmıyor" gerekçesi
#: (``hybrid_rocket_engine.HTPB_BIAS_UNRECONCILED_REASONS``) bandı artık
#: yorumdan DEĞİL buradan okur — eskiden aynı iki sayı orada İngilizce
#: nesrin içine gömülü duruyordu ve makine tarafı onları hiç göremiyordu.
HYBRID_GOX_FIT_UNDER_GTOTAL_LIFT_PCT = (10, 18)

HYBRID_REGRESSION_COEFFICIENTS = {
    # Doran et al., AIAA 2007-5352 (HTPB/N2O):
    # r[mm/s] = 0.132 * (G_ox[g/cm²·s])^0.555  ->  a_SI = 0.132e-3 * 10^-0.555
    'htpb': {'a': 3.68e-5, 'n': 0.555},
    # Karabeyoglu et al., J. Propulsion and Power 20(6), 2004 (SP-1a parafin);
    # Zilliac & Karabeyoglu, AIAA 2006-4504, Tablo 2: a=0.488, n=0.62
    # (r mm/s, G g/cm²·s)  ->  a_SI = 0.488e-3 * 10^-0.62
    'paraffin': {'a': 1.17e-4, 'n': 0.62},
    # HDPE/O2, Zilliac & Karabeyoglu, AIAA 2006-4504, Tablo 2: a=0.132, n=0.498
    # ->  a_SI = 0.132e-3 * 10^-0.498
    'pe': {'a': 4.19e-5, 'n': 0.498},
    # PMMA/O2 (Greiner & Federick verisi), Zilliac & Karabeyoglu,
    # AIAA 2006-4504, Tablo 2: a=0.087, n=0.615  ->  a_SI = 0.087e-3 * 10^-0.615
    'pmma': {'a': 2.11e-5, 'n': 0.615},
    # ABS/N2O regresyonu HTPB/N2O ile yakın ölçülmüştür (Whitmore & Peterson,
    # J. Propulsion and Power 29(3), 2013) — HTPB/N2O katsayıları kullanılır.
    'abs': {'a': 3.68e-5, 'n': 0.555},
    # Aşağıdaki yakıtlar için yayınlanmış, hakemli bir korelasyon bulunamadı;
    # önceki kod değerleri DOĞRULANMAMIŞ olarak korunur (tasarım için kullanmayın).
    'pla': {'a': 1.2e-4, 'n': 0.52},
    'carbon': {'a': 8.0e-5, 'n': 0.45},
    'aluminum': {'a': 5.0e-5, 'n': 0.40},
    'al2o3': {'a': 3.0e-5, 'n': 0.35},
}


# ---------------------------------------------------------------------------
# ÖH D23 / defter OH-D21-04 — REGRESYON KATSAYI ÇİFTİNİN KÜNYESİ (TEK KAYNAK)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` bölümü OH-D21-04): ``htpb`` ve
# ``abs`` yakıtları BİREBİR aynı çifti taşıyor —
#
#     'htpb': {'a': 3.68e-5, 'n': 0.555}
#     'abs' : {'a': 3.68e-5, 'n': 0.555}
#
# Bu eşitlik kasıtlıdır (Whitmore & Peterson, JPP 29(3) 2013, ABS/N2O'yu
# HTPB/N2O'ya YAKIN ölçmüştür) ama ödünç alma YALNIZ bir kaynak yorumunda
# yazılıydı: ürünün yayımladığı ``self.database['abs']`` kaydında ödünç
# olduğunu söyleyen TEK BİR ALAN YOKTU ve ``source`` alanı '3D Printing
# Propulsion Research' diyordu — hangi ölçüm olduğu izlenemez.
#
# D21'in künye onarımının (P5B4-07) veri katmanındaki eşliği budur: bir sayı
# nereden geldiğini kendi kaydında söyler. Buradaki alanlar SAYIYA DOKUNMAZ;
# yalnız her çiftin KÖKENİNİ ve bağımsız bir ölçüm olup olmadığını yayımlar.
#
# ``regression_is_independent = False`` iki ayrı olguyu işaretler:
#   * ``abs``  — başka bir yakıtın (HTPB/N2O) çifti ödünç alınmıştır,
#   * ``pla``/``carbon``/``aluminum``/``al2o3`` — hakemli bir korelasyon
#     bulunamamıştır, önceki kod değerleri DOĞRULANMAMIŞ olarak durur.
# Bu yakıtlar için ayrı, kaynaklı bir çift üretmek bir VERİ kararıdır ve
# yayımlanmış ölçüm olmadan sayı UYDURULMAZ (fail-closed): eksik olan şey
# gizlenmez, adıyla söylenir.
HYBRID_REGRESSION_SOURCES = {
    'htpb': {
        'citation': 'Doran et al., AIAA 2007-5352 (HTPB/N2O)',
        'independent': True,
        'basis': 'G_ox-based fit, r[mm/s] = 0.132 * G_ox[g/cm2.s]^0.555',
    },
    'paraffin': {
        'citation': ('Karabeyoglu et al., J. Propulsion and Power 20(6) 2004 '
                     '(SP-1a paraffin); Zilliac & Karabeyoglu, AIAA 2006-4504 '
                     'Table 2'),
        'independent': True,
        'basis': 'G_ox-based fit, a=0.488, n=0.62 (r mm/s, G g/cm2.s)',
    },
    'pe': {
        'citation': 'Zilliac & Karabeyoglu, AIAA 2006-4504 Table 2 (HDPE/O2)',
        'independent': True,
        'basis': 'G_ox-based fit, a=0.132, n=0.498',
    },
    'pmma': {
        'citation': ('Zilliac & Karabeyoglu, AIAA 2006-4504 Table 2 '
                     '(PMMA/O2, Greiner & Federick data)'),
        'independent': True,
        'basis': 'G_ox-based fit, a=0.087, n=0.615',
    },
    'abs': {
        'citation': ('Whitmore & Peterson, J. Propulsion and Power 29(3), '
                     '2013 (ABS/N2O measured close to HTPB/N2O)'),
        'independent': False,
        'basis': ('BORROWED: this is the HTPB/N2O coefficient pair reused for '
                  'ABS, not an independent ABS regression fit. No separate '
                  'published ABS/N2O (a, n) pair is carried in this '
                  'repository; do not report it as an ABS measurement.'),
    },
}
#: Hakemli korelasyonu bulunamayan yakıtlar — çift DOĞRULANMAMIŞ.
for _yakit in ('pla', 'carbon', 'aluminum', 'al2o3'):
    HYBRID_REGRESSION_SOURCES[_yakit] = {
        'citation': None,
        'independent': False,
        'basis': ('UNVALIDATED: no peer-reviewed correlation was found for '
                  'this fuel; the pair is inherited from earlier code and '
                  'must not be used for design.'),
    }
del _yakit

assert set(HYBRID_REGRESSION_SOURCES) == set(HYBRID_REGRESSION_COEFFICIENTS), (
    'Her regresyon çiftinin bir künyesi olmalı (OH-D21-04): '
    f'{set(HYBRID_REGRESSION_COEFFICIENTS) ^ set(HYBRID_REGRESSION_SOURCES)}')


# ---------------------------------------------------------------------------
# ÖH D17 / P15B2-08 · HİBRİT KATI YAKIT YOĞUNLUKLARI [kg/m³] — TEK KAYNAK
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (docs/scofield/raw/OH/D17/hibrit/a1/once.json, ``P15B2_08``): aynı
# yakıt anahtarının yoğunluğu DÖRT ayrı tabloda ayrı ayrı yazılıydı ve
# ``pe`` (polietilen) için ÜÇ FARKLI SAYI dolaşıyordu:
#
#     kaynak                                   pe     abs    pla
#     ------------------------------------    ----   ----   ----
#     data/propellant_database.py              960   1050    yok
#     analysis/regression_analysis.py          960   1050    yok
#     engines/combustion_analysis.py           940   1050   1240
#     engines/hybrid_rocket_engine.py          950   1040   1250
#
# Zarar ÖLÇÜLDÜ ve bileşiktir: motor ``rho_f``yi kendi tablosundan (950)
# okuyor, yakıt kütle debisi m_f = rho_f * A_b * r_dot oradan çıkıyor, O/F
# ondan, c* O/F'den, Isp c*'tan. 940 <-> 960 arasındaki %2,13'lük fark bu
# zincirin tamamına giriyordu. Aynı anahtar altında İKİ AD da vardı
# ('Polyethylene' <-> yorumlarda 'HDPE'), beyansız.
#
# SEÇİLEN DEĞER ve GEREKÇESİ: bu tablodaki sayı, KAYNAĞI OLAN kayıttır.
# ``pe`` = 960 kg/m³ — ``propellant_database`` kaydının kendi künyesi
# (Sutton & Biblarz) ve regresyon tablosunun HDPE/O2 korelasyonu
# (Zilliac & Karabeyoglu, AIAA 2006-4504) aynı malzemeyi tarif eder.
# 950 ve 940 KAYNAKSIZ literallerdi. HDPE'nin yayın bandı 940-965 kg/m³'tür;
# roket greni olarak dökülen/ekstrüde edilen HDPE bandın üst ucundadır.
#
# ÖH D20 / OH-D19-10 — ``pla`` ARTIK İÇERİDE. D17'de "iki değerin de kaynağı
# yok" diye dışarıda bırakılmıştı ve ayrışma (motor 1250 <-> yanma çözücüsü
# 1240) AÇIK KALEM olarak devredildi; kalem bu dalgada kapatılıyor, çünkü
# ölçülen iki sayıdan BİRİNİN kaynağı var:
#   * 1240 kg/m³ = NatureWorks Ingeo 3D850/4043D teknik veri sayfası
#     (ASTM D792, 1,24 g/cm³) ve Auras ve ark., "Poly(lactic acid)" (Wiley
#     2010, Böl. 6) amorf PLA 1,248 g/cm³. Döküm/ekstrüzyon ile üretilen
#     PLA gren amorf-baskındır.
#   * 1250 kg/m³ hiçbir kaynağa bağlanamadı (yalnız motor tablosunda,
#     yuvarlanmış hâliyle duruyordu).
# Kaynaklı olan kazandı; uydurma uzlaşı sayısı YAZILMADI. Tam kristal PLA
# (1290 kg/m³) gren için temsili değildir, o yüzden alınmadı.
HYBRID_FUEL_DENSITY_KG_M3 = {
    'htpb': 920,      # dört sitede de aynıydı; tek kaynağa taşındı
    'paraffin': 900,  # dört sitede de aynıydı
    'pe': 960,        # AYRIŞIYORDU (960/960/940/950) -> kaynaklı kayıt
    'pmma': 1180,     # dört sitede de aynıydı
    'abs': 1050,      # AYRIŞIYORDU (1050/1050/1050/1040) -> kaynaklı kayıt
    'pla': 1240,      # AYRIŞIYORDU (1250 <-> 1240) -> kaynaklı kayıt
}

#: ``pe`` anahtarının TEK adı. Ayrışan ikinci ad ('HDPE') yalnız kod
#: yorumlarında geçiyordu; kullanıcıya dönük ad budur.
HYBRID_FUEL_DISPLAY_NAMES = {
    'pe': 'Polyethylene (HDPE)',
}

# N2O doygun sıvı yoğunluğu [kg/m³] @ 298.15 K (25°C) — NIST WebBook
# (Lemmon & Span 2006 EOS; CoolProp aynı EOS ile 742.9 kg/m³ verir).
# Not: 293.15 K'de (20°C) doygun sıvı ~785 kg/m³'tür; 1220 kg/m³ ise yalnızca
# normal kaynama noktasında (184.7 K, −88.5°C) geçerlidir ve besleme koşulunu
# TEMSİL ETMEZ (denetim bulgusu #2).
N2O_LIQUID_DENSITY_SAT_25C = 745.0

#: Yukarıdaki KATALOG sayısının geçerli olduğu sıcaklık [K] — ÖH D32 /
#: OH-D31-11. Bugüne dek bu bilgi YALNIZ sabitin ADINDA ("_SAT_25C") ve
#: üstündeki yorumda yazılıydı, yani MAKİNE OKUYAMIYORDU. ÖLÇÜLDÜ
#: (``docs/scofield/raw/OH/D32/sivi/a1/once.json`` K2): bu 298,15 K
#: değeri ``/api/get-propellant-properties`` tarafından, künyesi
#: ``state_temperature_K = 293,15`` diyen bir DURUM BEYANIYLA birlikte
#: yayımlanıyordu — sayı kendi künyesini yalanlıyordu (aynı EOS 293,15 K
#: doymuş sıvı için 785,10 kg/m³ verir; %5,37). Künyenin doğruyu
#: söyleyebilmesi için sayının kendi durumu da tek kaynakta yazılı olmalı.
N2O_LIQUID_DENSITY_SAT_25C_T_K = 298.15

# ---------------------------------------------------------------------------
# SU KOÇU / BESLEME AKIŞKAN TABLOSUYLA PAYLAŞILAN SIVI YOĞUNLUKLARI [kg/m³]
#
# ÖH D31 · P4B4-07 + OH-D27-08. ``hrma.analysis.water_hammer.FLUID_PROPERTIES``
# kendi yoğunluk sayısını YAZMAZ, buradan okur. Gerekçe ölçüldü: n2o kaydı iki
# yerde iki kez yazıldığı için ayrışmıştı (su koçu 785,0 ⟷ bu katalog 745,0;
# ÖLÇÜLEN fark 40 kg/m³). Aynı hatanın altı itici için tekrarlanmaması adına
# sayı TEK yerde durur ve iki modül de bu adı kullanır.
#
# Değerler bu kataloğun KENDİ kayıtlarıdır (aşağıdaki ``'density'`` alanları
# bu adlara bağlıdır); yeni bir sayı GİRİLMEDİ, yalnız ada kavuşturuldu.
# ---------------------------------------------------------------------------
LH2_LIQUID_DENSITY_20K = 70.8          # kg/m³ @ 20 K (NIST kriyojenik verisi)
METHANE_LIQUID_DENSITY_NBP = 422.6     # kg/m³ @ 111,7 K (normal kaynama)
MMH_LIQUID_DENSITY_293K = 875.0        # kg/m³ @ 20 °C
UDMH_LIQUID_DENSITY_293K = 791.0       # kg/m³ @ 20 °C
N2O4_LIQUID_DENSITY_293K = 1443.0      # kg/m³ @ 20 °C
H2O2_98_LIQUID_DENSITY_293K = 1438.1   # kg/m³ @ 293,15 K, %98 çözelti


# ---------------------------------------------------------------------------
# N₂O OLUŞUM ENTALPİSİ — TEK TANIM (KU H-2 / B17, 6 Eki 2026)
#
# N₂O(g) ΔfH°(298,15 K). Gaz fazı, standart referans hâli. İŞARET POZİTİFTİR:
# N₂O → N₂ + ½O₂ ayrışması ekzotermiktir. Künye: NIST-JANAF (Chase 1998)
# +82,048 kJ/mol → 82,05 (KARS-TK bulgu 17; JANAF sayfası bu turda ağsız
# yeniden açılmadı). Yerelde doğrulanan bağımsız ayak: RocketCEA'nın NASA CEA
# ``thermo.inp`` N2O kaydı (Gurvich 1989) +81 600 J/mol — aynı işaret.
#
# Bu katalog kaydı ve ``/api/oxidizer-properties`` (``app._OXIDIZER_STATIC_
# PROPS['n2o']``) bu adı okur. ÖLÇÜLDÜ: o uç −82,05 yayımlıyordu (işaret
# hatası; hesaba girmeyen yayın alanı). Yanma çözücüsünün kendi kopyası
# (``combustion_analysis.propellant_specs['n2o']``) aynı +82,05'tir; o
# satır bu kulvarın dosya kümesinde olmadığı için henüz bu ada bağlanmadı
# (devir: KU h-q1 raporu).
N2O_ENTHALPY_FORMATION_GAS_298K_KJ_MOL = 82.05
#: Yukarıdaki sayının durumu — yayında sayıyla birlikte gider.
N2O_ENTHALPY_FORMATION_STATE = 'gas, 298.15 K (standard reference state)'


# ---------------------------------------------------------------------------
# BUHAR BASINCI — TEK BİRİM (KU H-3 / B18, 6 Eki 2026)
#
# ÖLÇÜLDÜ (taban 9842af22, ağ kapalı): ``/api/get-propellant-properties``
# aynı ``vapor_pressure`` anahtarını üç farklı birimle yayımlıyordu ve
# hiçbirini yazmıyordu:
#   n2o / 'oxidizer'          -> 5 651 798,9   (CoolProp, Pa)
#   n2o / 'hybrid_oxidizer'   -> 5,15          (bu katalog, MPa)
#   rp1 / 'liquid_fuel'       -> 0,7           (bu katalog, kPa)
# Kataloğun birimi artık Pa'dır (CoolProp kolu ve ``/api/oxidizer-
# properties`` zaten Pa) ve uç birimi bu addan okuyup yayımlar.
VAPOR_PRESSURE_UNIT = 'Pa'


def n2o_catalogue_vapor_pressure() -> Optional[Dict]:
    """N₂O kaydının doyma basıncı [Pa] — hâl denkleminden TÜRETİLİR.

    KU H-3 (B18). Eski kayıt elle yazılmış ``5.15  # MPa at 20°C`` idi ve
    künyesi kaydın ortak ``'NIST WebBook'`` etiketiydi. ÖLÇÜLDÜ (KARS-TK
    bulgu 18; CoolProp 6.8.0, Lemmon & Span 2006 EOS): 293,15 K'de
    5,0525 MPa; 5,15 MPa 293,99 K'nin değeridir (+%1,9). NIST'in kullandığı
    EOS da 5,05 verdiği için künye ile sayı tutmuyordu.

    Sayı artık deponun N₂O doyma kapısından (``tank_blowdown.N2OSaturation``
    — CoolProp varsa EOS, yoksa aynı EOS'tan üretilmiş gömülü tablo) ve
    açık kaynak katmanının N₂O depolama sıcaklığında
    (``OpenSourcePropellantAPI.DEFAULT_STORAGE_STATE['NitrousOxide']``)
    çözülür; ikinci bir sayı yazılmaz.

    Döner: ``vapor_pressure`` (Pa), ``vapor_pressure_reference_temperature_K``,
    ``vapor_pressure_source`` alanları; çözülemezse ``None`` (alan yayımlanmaz,
    yerine sayı uydurulmaz).
    """
    try:
        from hrma.analysis.tank_blowdown import N2OSaturation
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        T_ref = float(
            OpenSourcePropellantAPI.DEFAULT_STORAGE_STATE['NitrousOxide']['T'])
        sat = N2OSaturation()
        p_sat = float(sat.psat(T_ref))
    except Exception:  # noqa: BLE001 — veri katmanı arızası sayı üretmez
        return None
    if not (p_sat > 0.0 and p_sat < float('inf')):
        return None
    yol = ('CoolProp EOS (Lemmon & Span 2006)' if sat.use_coolprop else
           'embedded saturation table generated from the Lemmon & Span '
           '2006 EOS')
    return {
        'vapor_pressure': p_sat,
        'vapor_pressure_reference_temperature_K': T_ref,
        'vapor_pressure_source': (
            f'saturation pressure solved by hrma.analysis.tank_blowdown.'
            f'N2OSaturation at {T_ref:.2f} K ({yol}); unit '
            f'{VAPOR_PRESSURE_UNIT}'),
    }


#: Kayıt alanı elle yazılmayıp ERİŞİMDE türetilen itici adları -> üretici.
_DERIVED_RECORD_FIELDS = {
    'n2o': n2o_catalogue_vapor_pressure,
}


# ---------------------------------------------------------------------------
# BEYAN EDİLMİŞ KATALOG BOŞLUKLARI — ÖH Z5S / P9B4-17
# ---------------------------------------------------------------------------
# Çözücünün desteklediği, ama bu kataloğun (ve propellants_db'nin) kaydı
# OLMAYAN adlar. Amaç: sessiz None ile 'yazım hatası' arasındaki farkı
# okunur kılmak. Buraya UYDURMA ÖZELLİK YAZILMAZ — yalnız boşluğun kendisi
# ve nedeni beyan edilir. Bir ada gerçek, kaynaklı bir kayıt eklendiğinde
# satırı buradan SİLİNİR (aksi hâlde beyan ile katalog çelişir; bekçi bunu
# sınar: tests/test_z5s_katalog_kapilari.py).
SOLVER_SUPPORTED_NOT_CATALOGUED: Dict[str, Dict[str, str]] = {
    'gox': {
        'reason': (
            'Gaseous oxygen is a first-class oxidizer in the solver but has '
            'no record here: this catalogue keys an oxidizer on a single '
            "'density' value, and a gas has no single density (it follows "
            'pressure and temperature). Borrowing the liquid sibling '
            "value (lox, 1141 kg/m3 at 90 K) would be plainly wrong, so the "
            'gap is declared instead of invented. Use an equation-of-state '
            'call for gas-phase properties.'),
        'supported_in': (
            'hrma/engines/combustion_analysis.py (elemental oxidizer '
            "branch, 'lox'/'gox'/'o2'/'oxygen'); "
            'hrma/engines/cea_bridge.py OX_CARD_MAP; '
            'hrma/stability/hybrid_lfi.py oxidizer families; '
            'hrma/constants.py C_STAR_PLAUSIBLE_BAND_MPS'),
        'used_by_validation_records': (
            '46 records in hrma/data/validation_records/ carry '
            "propellants.oxidizer == 'gox'"),
    },
    'air': {
        'reason': (
            'Air is accepted by the combustion elemental balance (air-'
            'breathing academic cases) but is not a catalogued propellant; '
            'it has no density/heat-of-formation record here. Declared so '
            'the missing record is not mistaken for a typo.'),
        'supported_in': (
            'hrma/engines/combustion_analysis.py (air branch, '
            'AIR_O2_MASS_FRACTION / AIR_N2_MASS_FRACTION); '
            'hrma/constants.py C_STAR_PLAUSIBLE_BAND_MPS'),
        'used_by_validation_records': 'none measured',
    },
}


class PropellantDatabase:
    """Central database for all propellant properties"""
    
    def __init__(self):
        # Comprehensive propellant properties database
        self.database = {
            # HYBRID FUELS
            'htpb': {
                'name': 'HTPB (Hydroxyl-terminated polybutadiene)',
                'formula': 'C7H10O2',
                'density': 920,  # kg/m³
                'heat_of_formation': -105.0,  # kJ/mol
                # Doran et al., AIAA 2007-5352 (HTPB/N2O), SI — merkezi tablodan
                'regression_a': HYBRID_REGRESSION_COEFFICIENTS['htpb']['a'],
                'regression_n': HYBRID_REGRESSION_COEFFICIENTS['htpb']['n'],
                # OH-D21-04: çiftin kökeni kaydın KENDİSİNDE.
                'regression_source':
                    HYBRID_REGRESSION_SOURCES['htpb']['citation'],
                'regression_is_independent':
                    HYBRID_REGRESSION_SOURCES['htpb']['independent'],
                'regression_basis':
                    HYBRID_REGRESSION_SOURCES['htpb']['basis'],
                'combustion_temp': 3200,  # K
                'molecular_weight': 54.09,  # g/mol
                'specific_heat': 1.8,  # kJ/kg·K
                'thermal_conductivity': 0.2,  # W/m·K
                'elastic_modulus': 2.8,  # MPa
                'poisson_ratio': 0.495,
                'max_operating_temp': 350,  # K
                'source': 'NASA SP-8075'
            },
            'paraffin': {
                'name': 'Paraffin Wax',
                'formula': 'CnH2n+2 (n≈25)',
                'density': 900,
                'heat_of_formation': -300.0,
                # Karabeyoglu et al., JPP 20(6) 2004 (SP-1a), SI — merkezi tablodan
                'regression_a': HYBRID_REGRESSION_COEFFICIENTS['paraffin']['a'],
                'regression_n': HYBRID_REGRESSION_COEFFICIENTS['paraffin']['n'],
                # OH-D21-04: çiftin kökeni kaydın KENDİSİNDE.
                'regression_source':
                    HYBRID_REGRESSION_SOURCES['paraffin']['citation'],
                'regression_is_independent':
                    HYBRID_REGRESSION_SOURCES['paraffin']['independent'],
                'regression_basis':
                    HYBRID_REGRESSION_SOURCES['paraffin']['basis'],
                'combustion_temp': 3100,
                'molecular_weight': 352,
                'specific_heat': 2.14,
                'thermal_conductivity': 0.25,
                'melting_point': 337,  # K
                'liquefying_fuel': True,
                'source': 'Stanford University Research'
            },
            'pe': {
                # ÖH D17 / P15B2-08: ad ve yoğunluk tek kaynaktan.
                'name': HYBRID_FUEL_DISPLAY_NAMES['pe'],
                'formula': '(C2H4)n',
                'density': HYBRID_FUEL_DENSITY_KG_M3['pe'],
                'heat_of_formation': -84.7,
                # HDPE/O2, Zilliac & Karabeyoglu AIAA 2006-4504, SI — merkezi tablodan
                'regression_a': HYBRID_REGRESSION_COEFFICIENTS['pe']['a'],
                'regression_n': HYBRID_REGRESSION_COEFFICIENTS['pe']['n'],
                # OH-D21-04: çiftin kökeni kaydın KENDİSİNDE.
                'regression_source':
                    HYBRID_REGRESSION_SOURCES['pe']['citation'],
                'regression_is_independent':
                    HYBRID_REGRESSION_SOURCES['pe']['independent'],
                'regression_basis':
                    HYBRID_REGRESSION_SOURCES['pe']['basis'],
                'combustion_temp': 3150,
                'molecular_weight': 28.05,
                'specific_heat': 1.9,
                'thermal_conductivity': 0.33,
                'melting_point': 408,
                'source': 'Sutton & Biblarz'
            },
            'pmma': {
                'name': 'Polymethyl Methacrylate (Plexiglass)',
                'formula': 'C5H8O2',
                'density': 1180,
                'heat_of_formation': -360.0,
                # PMMA/O2, Zilliac & Karabeyoglu AIAA 2006-4504, SI — merkezi tablodan
                'regression_a': HYBRID_REGRESSION_COEFFICIENTS['pmma']['a'],
                'regression_n': HYBRID_REGRESSION_COEFFICIENTS['pmma']['n'],
                # OH-D21-04: çiftin kökeni kaydın KENDİSİNDE.
                'regression_source':
                    HYBRID_REGRESSION_SOURCES['pmma']['citation'],
                'regression_is_independent':
                    HYBRID_REGRESSION_SOURCES['pmma']['independent'],
                'regression_basis':
                    HYBRID_REGRESSION_SOURCES['pmma']['basis'],
                'combustion_temp': 3000,
                'molecular_weight': 100.12,
                'specific_heat': 1.42,
                'thermal_conductivity': 0.19,
                'glass_transition_temp': 378,
                'source': 'AIAA Database'
            },
            'abs': {
                'name': 'ABS Plastic',
                'formula': 'C15H17N',
                'density': 1050,
                'heat_of_formation': -200.0,
                # ABS/N2O ≈ HTPB/N2O (Whitmore & Peterson, JPP 2013) — merkezi tablodan
                'regression_a': HYBRID_REGRESSION_COEFFICIENTS['abs']['a'],
                'regression_n': HYBRID_REGRESSION_COEFFICIENTS['abs']['n'],
                # OH-D21-04: çiftin kökeni kaydın KENDİSİNDE.
                'regression_source':
                    HYBRID_REGRESSION_SOURCES['abs']['citation'],
                'regression_is_independent':
                    HYBRID_REGRESSION_SOURCES['abs']['independent'],
                'regression_basis':
                    HYBRID_REGRESSION_SOURCES['abs']['basis'],
                'combustion_temp': 2950,
                'molecular_weight': 211.3,
                'specific_heat': 1.3,
                'thermal_conductivity': 0.17,
                'source': '3D Printing Propulsion Research'
            },
            
            # LIQUID FUELS
            'rp1': {
                'name': 'RP-1 (Refined Petroleum-1)',
                'formula': 'C12H26 (average)',
                'density': 810,  # kg/m³ at 20°C
                'heat_of_formation': -250.0,
                'boiling_point': 489,  # K
                'viscosity': 0.0016,  # Pa·s at 20°C
                'surface_tension': 0.024,  # N/m
                # Pa @ 20 °C. KU H-3: eski yazım 0,7 (kPa, birimsiz
                # yayımlanıyordu); fiziksel değer AYNI, birim tekleşti.
                'vapor_pressure': 0.7e3,
                'combustion_temp': 3700,  # K with LOX
                'molecular_weight': 170.33,
                'specific_heat': 2.1,
                'thermal_conductivity': 0.15,
                'source': 'NASA RP-1 Specification'
            },
            'lh2': {
                'name': 'Liquid Hydrogen',
                'formula': 'H2',
                'density': LH2_LIQUID_DENSITY_20K,  # kg/m³ at 20K
                'heat_of_formation': 0.0,
                'boiling_point': 20.28,  # K
                'viscosity': 0.000013,  # Pa·s at 20K
                'critical_temp': 33.145,  # K
                'critical_pressure': 1.297,  # MPa
                'combustion_temp': 3600,  # K with LOX
                'molecular_weight': 2.016,
                'specific_heat': 14.3,  # kJ/kg·K at 20K
                'thermal_conductivity': 0.1,
                'source': 'NIST Cryogenic Data'
            },
            'methane': {
                'name': 'Liquid Methane',
                'formula': 'CH4',
                'density': METHANE_LIQUID_DENSITY_NBP,  # kg/m³ at 111K
                'heat_of_formation': -74.6,
                'boiling_point': 111.7,  # K
                'viscosity': 0.00011,  # Pa·s at 111K
                'critical_temp': 190.6,  # K
                'critical_pressure': 4.6,  # MPa
                'combustion_temp': 3500,  # K with LOX
                'molecular_weight': 16.04,
                'specific_heat': 3.48,  # kJ/kg·K
                'thermal_conductivity': 0.2,
                'source': 'SpaceX Raptor Engine Data'
            },
            'mmh': {
                'name': 'Monomethylhydrazine',
                'formula': 'CH6N2',
                'density': MMH_LIQUID_DENSITY_293K,  # kg/m³ at 20°C
                'heat_of_formation': 54.2,
                'boiling_point': 361,  # K
                'viscosity': 0.00078,  # Pa·s
                'flash_point': 291,  # K
                'combustion_temp': 3400,  # K with N2O4
                'molecular_weight': 46.07,
                'specific_heat': 3.13,
                'thermal_conductivity': 0.25,
                'toxic': True,
                'hypergolic': True,
                'source': 'Aerojet Rocketdyne'
            },
            'udmh': {
                'name': 'Unsymmetrical Dimethylhydrazine',
                'formula': 'C2H8N2',
                'density': UDMH_LIQUID_DENSITY_293K,  # kg/m³ at 20°C
                'heat_of_formation': 48.3,
                'boiling_point': 336,  # K
                'viscosity': 0.00049,  # Pa·s
                'combustion_temp': 3350,  # K with N2O4
                'molecular_weight': 60.1,
                'specific_heat': 2.95,
                'toxic': True,
                'hypergolic': True,
                'source': 'Russian Space Program'
            },
            
            # SOLID PROPELLANTS
            'apcp': {
                'name': 'Ammonium Perchlorate Composite Propellant',
                'formula': 'NH4ClO4 + Al + HTPB',
                'density': 1800,  # kg/m³
                'heat_of_formation': -295.8,
                'combustion_temp': 3200,  # K
                'molecular_weight': 117.49,  # AP only
                'burn_rate_a': 0.005,  # at 1 MPa
                'burn_rate_n': 0.35,
                'pressure_exponent': 0.35,
                'specific_impulse': 265,  # s (vacuum)
                'aluminum_content': 16,  # %
                'binder_content': 12,  # %
                'oxidizer_content': 72,  # %
                'source': 'ATK Solid Rocket Motors'
            },
            'kndx': {
                'name': 'Potassium Nitrate/Dextrose',
                'formula': 'KNO3 + C6H12O6',
                'density': 1850,
                'heat_of_formation': -494.6,
                'combustion_temp': 1800,  # K (lower than APCP)
                'molecular_weight': 101.1,  # KNO3
                # DİKKAT (2026-07-18 fizik incelemesi): bu a-n çifti birim
                # etiketsizdir ve Nakka'nın yayımlanmış rejim fitleriyle hiçbir
                # birim yorumunda uyuşmaz (bar yorumu +308%, MPa yorumu +45%
                # sapma) — kaynağı doğrulanamadı, yalnız kaba gösterim değeri.
                # Doğrulanmış, birim-açık rejim fitleri: hrma/data/burn_rate_db.py
                'burn_rate_a': 0.008,
                'burn_rate_n': 0.45,
                'specific_impulse': 130,  # s (lower performance)
                'oxidizer_ratio': 65,  # % KNO3
                'fuel_ratio': 35,  # % Dextrose
                'amateur_friendly': True,
                'source': 'Richard Nakka Experimental Rocketry'
            },
            'knsu': {
                'name': 'Potassium Nitrate/Sugar (Sucrose)',
                'formula': 'KNO3 + C12H22O11',
                'density': 1840,
                'heat_of_formation': -485.0,
                # NASA CEA (KNO3/sakaroz 65/35) + Nakka ~1720 K ile tutarlı;
                # solid_rocket_engine.py 'knsu' (T_c=1719) ile aynı kaynak.
                'combustion_temp': 1719,
                'molecular_weight': 101.1,  # KNO3 ham madde (egzoz MW ~37, motor modülü)
                'burn_rate_a': 0.009,
                'burn_rate_n': 0.5,
                'specific_impulse': 135,
                'oxidizer_ratio': 60,
                'fuel_ratio': 40,
                'melting_point': 403,  # K (sugar melts first)
                'source': 'Amateur Rocketry'
            },
            'pban': {
                'name': 'Polybutadiene Acrylonitrile',
                'formula': 'Complex polymer with AP',
                'density': 1790,
                'combustion_temp': 3100,
                'burn_rate_a': 0.004,
                'burn_rate_n': 0.32,
                'specific_impulse': 260,
                'elastic_modulus': 4.5,  # MPa
                'elongation': 40,  # %
                'source': 'NASA Space Shuttle SRB'
            },
            
            # OXIDIZERS
            'n2o': {
                'name': 'Nitrous Oxide',
                'formula': 'N2O',
                # Doygun sıvı, 298.15 K (25°C) — NIST WebBook (Lemmon & Span 2006 EOS).
                # Eski 1220 kg/m³ değeri NBP (−88.5°C) yoğunluğuydu (denetim bulgusu #2).
                'density': N2O_LIQUID_DENSITY_SAT_25C,  # kg/m³
                # kJ/mol, gaz 298,15 K — TEK TANIM (bkz. modül başı, KU H-2)
                'heat_of_formation': N2O_ENTHALPY_FORMATION_GAS_298K_KJ_MOL,
                'boiling_point': 184.7,  # K at 1 atm
                'critical_temp': 309.6,  # K
                'critical_pressure': 7.245,  # MPa
                # 'vapor_pressure' BURADA YAZILMAZ: erişimde hâl
                # denkleminden türetilir (n2o_catalogue_vapor_pressure,
                # KU H-3). Eski elle yazılmış 5,15 MPa kaldırıldı.
                'viscosity': 0.00014,  # Pa·s (liquid)
                'self_pressurizing': True,
                'molecular_weight': 44.01,
                'source': 'NIST WebBook'
            },
            'lox': {
                'name': 'Liquid Oxygen',
                'formula': 'O2',
                'density': 1141,  # kg/m³ at 90K
                'heat_of_formation': 0.0,
                'boiling_point': 90.2,  # K
                'critical_temp': 154.6,  # K
                'critical_pressure': 5.043,  # MPa
                'viscosity': 0.00019,  # Pa·s at 90K
                'molecular_weight': 32.0,
                'cryogenic': True,
                'source': 'NASA Glenn Research Center'
            },
            'h2o2': {
                'name': 'Hydrogen Peroxide (98%)',
                'formula': 'H2O2',
                # ETİKET DÜRÜSTLÜĞÜ (karar 28 Ağu). Buradaki sayı 1450 idi;
                # 1450 kg/m³ %100 SAF H₂O₂'nin 20 °C değeridir (1449,9) —
                # kaydın taşıdığı '%98' etiketinin değeri DEĞİL. Sayı gerçekti,
                # etiket yanlıştı: kayıt kendi künyesini yalanlıyordu, çünkü
                # ``oxidizer_reference_density`` bu değeri AFRPL'in %98 künyesiyle
                # damgalayıp dışarı veriyor. %98 çözeltinin 293,15 K değeri 1438,1.
                # Kaynak: AFRPL-TR-67-144 (Rocketdyne 1967) Böl. 2.2.2.1 — künye
                # zaten external_data_fetcher.OXIDIZER_REFERENCE_STATE'te kayıtlı.
                'density': H2O2_98_LIQUID_DENSITY_293K,  # kg/m³ @ 293,15 K, %98
                'heat_of_formation': -187.8,
                'boiling_point': 423,  # K
                'decomposition_temp': 373,  # K (starts decomposing)
                'viscosity': 0.00125,  # Pa·s
                'molecular_weight': 34.01,
                'concentration': 98,  # %
                'catalytic_decomposition': True,
                'source': 'Soyuz U2 Upper Stage'
            },
            'n2o4': {
                'name': 'Nitrogen Tetroxide',
                'formula': 'N2O4',
                'density': N2O4_LIQUID_DENSITY_293K,  # kg/m³ at 20°C
                'heat_of_formation': 9.16,
                'boiling_point': 294.3,  # K
                'viscosity': 0.00042,  # Pa·s
                'molecular_weight': 92.01,
                'toxic': True,
                'hypergolic': True,
                'storable': True,
                'source': 'Ariane 5 Upper Stage'
            }
        }
        
        # Chemical additives and modifiers
        self.additives = {
            'al': {
                'name': 'Aluminum Powder',
                'formula': 'Al',
                'density': 2700,
                'heat_of_formation': 0.0,
                'combustion_enthalpy': -31.0,  # MJ/kg
                'particle_size': 30,  # μm typical
                'effect': 'Increases combustion temperature and specific impulse'
            },
            'al2o3': {
                'name': 'Aluminum Oxide',
                'formula': 'Al2O3',
                'density': 3950,
                'heat_of_formation': -1675.7,
                'melting_point': 2345,  # K
                'effect': 'Combustion product, affects two-phase flow losses'
            },
            'carbon': {
                'name': 'Carbon Black',
                'formula': 'C',
                'density': 2200,
                'heat_of_formation': 0.0,
                'effect': 'Opacifier, reduces radiation losses'
            },
            'fe2o3': {
                'name': 'Iron Oxide (Burn Rate Catalyst)',
                'formula': 'Fe2O3',
                'density': 5240,
                'effect': 'Increases burn rate in solid propellants'
            }
        }
    
    def get_propellant_properties(self, propellant_name: str) -> Optional[Dict]:
        """Get all properties for a specific propellant.

        None dönüşü İKİ ayrı durumu kapsar ve tek başına ayırt edilemez:
        (a) ad hatalı/bilinmiyor, (b) ad çözücünün DESTEKLEDİĞİ bir
        yakıt/oksitleyici ama bu kataloğun kaydı yok. Ayrımı okumak için
        ``get_propellant_status`` kullanılır (ÖH Z5S / P9B4-17).
        """
        name_lower = propellant_name.lower()

        # Check main database
        if name_lower in self.database:
            kayit = self.database[name_lower].copy()
            # KU H-3: elle yazılmayıp türetilen alanlar (çözülemezse alan
            # hiç konmaz — fail-closed).
            uretici = _DERIVED_RECORD_FIELDS.get(name_lower)
            if uretici is not None:
                kayit.update(uretici() or {})
            return kayit

        # Check additives
        if name_lower in self.additives:
            return self.additives[name_lower].copy()

        # Try to fetch from online databases
        online_data = self._fetch_from_online_database(propellant_name)
        if online_data:
            # Cache it for future use
            self.database[name_lower] = online_data
            return online_data

        return None

    def get_propellant_status(self, propellant_name: str) -> Dict:
        """Bir adın bu katalogdaki durumu — sessiz None yerine ADLI cevap.

        ÖH Z5S / P9B4-17. Bulgu: 'gox' (gaz oksijen) çözücünün birinci
        sınıf desteklediği bir oksitleyici (combustion_analysis elemental
        dalı, cea_bridge OX_CARD_MAP, hybrid_lfi oksitleyici ailesi) ve
        depodaki doğrulama kayıtlarının 46'sı onu kullanıyor; buna karşın
        İKİ veri kataloğunda da hiç kaydı yok. ``get_propellant_properties
        ('gox')`` sadece None dönüyordu — yazım hatasından ayırt edilemeyen,
        gerekçesiz bir sessizlik.

        Neden kayıt EKLENMEDİ (fail-closed, uydurma özellik yazılmaz):
        katalogtaki oksitleyici kayıtlarının omurgası tek bir 'density'
        sayısıdır; gaz fazındaki oksijenin tek bir yoğunluğu YOKTUR
        (basınç ve sıcaklıkla değişir). Sıvı kardeşinin (lox, 1141 kg/m³
        @90 K) sayısını 'gox' kaydına koymak doğrudan yanlış olurdu.
        Doğru sayı çalışma koşuluna bağlı bir hâl denklemi çağrısıdır;
        bu kataloğun şeması onu taşıyamaz. Bu yüzden boşluk UYDURULMADI,
        BEYAN EDİLDİ.
        """
        name_lower = str(propellant_name).lower()
        catalogued = (name_lower in self.database
                      or name_lower in self.additives)
        gap = SOLVER_SUPPORTED_NOT_CATALOGUED.get(name_lower)
        return {
            'name': name_lower,
            'catalogued': catalogued,
            'solver_supported': catalogued or gap is not None,
            'record_available': catalogued,
            'gap_reason': None if catalogued else (
                gap['reason'] if gap else 'unknown_propellant_name'),
            'gap_declared_by': None if catalogued else (
                gap['supported_in'] if gap else None),
            'catalogued_names': sorted(
                list(self.database) + list(self.additives)),
        }

    def list_declared_gaps(self) -> Dict[str, Dict]:
        """Çözücünün desteklediği ama katalogda kaydı OLMAYAN adlar."""
        return {k: dict(v) for k, v in
                sorted(SOLVER_SUPPORTED_NOT_CATALOGUED.items())}

    def _fetch_from_online_database(self, propellant_name: str) -> Optional[Dict]:
        """Çevrimiçi kaynak çekimi UYGULANMADI — her zaman None döner.

        Uygulama çevrimdışı-öncelikli (masaüstü paket); yakıt verileri bu
        modüldeki yerel, kaynak-atıflı tablodan gelir. None dönüşü
        get_propellant'ı yerel tabloya düşürür (tasarlanan davranış).
        """
        return None

    def _fetch_from_nist(self, chemical_name: str) -> Optional[Dict]:
        """Çevrimiçi NIST WebBook çekimi UYGULANMADI — her zaman None döner.

        Yerel doğrulanmış tabloya düşülür; ayrıntı için
        _fetch_from_online_database docstring'ine bak.
        """
        return None
    
    def get_propellant_list(self, category: str = 'all') -> List[str]:
        """Get list of available propellants by category"""
        if category == 'all':
            return list(self.database.keys())
        
        categories = {
            'hybrid_fuels': ['htpb', 'paraffin', 'pe', 'pmma', 'abs'],
            'liquid_fuels': ['rp1', 'lh2', 'methane', 'mmh', 'udmh'],
            'solid_propellants': ['apcp', 'kndx', 'knsu', 'pban'],
            'oxidizers': ['n2o', 'lox', 'h2o2', 'n2o4']
        }
        
        return categories.get(category, [])
    
    def calculate_mixture_properties(self, components: Dict[str, float]) -> Dict:
        """Calculate properties of propellant mixtures"""
        total_mass = sum(components.values())
        if total_mass == 0:
            return {}
        
        mixture = {
            'density': 0,
            'molecular_weight': 0,
            'combustion_temp': 0,
            'components': components
        }
        
        # Mass-weighted averages
        for component, fraction in components.items():
            if component in self.database:
                props = self.database[component]
                weight = fraction / total_mass
                
                mixture['density'] += props.get('density', 0) * weight
                mixture['molecular_weight'] += props.get('molecular_weight', 0) * weight
                mixture['combustion_temp'] += props.get('combustion_temp', 0) * weight
        
        return mixture
    
    def export_to_json(self, filename: str = 'propellant_database.json'):
        """Export database to JSON file"""
        with open(filename, 'w') as f:
            json.dump({
                'propellants': self.database,
                'additives': self.additives
            }, f, indent=2)
    
    def search_by_property(self, property_name: str, min_value: float, max_value: float) -> List[Dict]:
        """Search propellants by property range"""
        results = []
        
        for name, props in self.database.items():
            if property_name in props:
                value = props[property_name]
                if min_value <= value <= max_value:
                    results.append({
                        'name': name,
                        'full_name': props.get('name', name),
                        property_name: value
                    })
        
        return sorted(results, key=lambda x: x[property_name])

# Global instance
propellant_db = PropellantDatabase()