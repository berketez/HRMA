"""
Heat Transfer Analysis Module
Chamber wall temperature and cooling analysis for hybrid rocket motors.

REVISION (2026-06): Gas-side heat transfer rewritten from a tube-flow
Dittus-Boelter correlation to the Bartz throat correlation, which is the
physically correct model for rocket nozzle/throat gas-side convection.
The previous implementation under-predicted the gas-side coefficient by
~4-15x (UNSAFE direction: burn-through risk invisible). See validation in
tests/test_heat_transfer_validation.py.

Key references:
  - Bartz, D.R. (1957), "A Simple Equation for Rapid Estimation of Rocket
    Nozzle Convective Heat Transfer Coefficients", Jet Propulsion 27(1).
  - Bartz, D.R. (1965), "Turbulent Boundary-Layer Heat Transfer from
    Rapidly Accelerating Flow of Rocket Combustion Gases and of Heated Air",
    Advances in Heat Transfer 2 (JPL draft Dec. 1963, NTRS 19650013685),
    Eqs. (48)-(50): (50) is the closed form implemented below, (49) the
    property factor sigma.
  - Sutton & Biblarz, "Rocket Propulsion Elements", 9th ed., Eq. 8-22,
    p. 313: the algebraically equivalent property-ratio form (= Bartz
    Eq. 48; it carries no curvature term).
  - NASA SP-8124, "Liquid Rocket Engine Self-Cooled Combustion Chambers".
  - Huzel & Huang, "Modern Engineering for Design of Liquid-Propellant
    Rocket Engines", AIAA, Chapter 4 (cooling).

IMPORTANT UNITS NOTE (g0 pitfall):
  Sutton 9th ed. Eq. 8-22 is written in US customary units, where the
  (Pc*g0/c*) group uses g0 = 32.174 lbm*ft/(lbf*s^2) as a unit-conversion
  factor between lbf and lbm. In a *consistent SI* system Pc/c* already has
  units of mass flux [kg/(m^2*s)], so g0 must NOT appear. Including g0 in SI
  inflates h_g by g0^0.8 ~ 6.2x. This module uses the SI-consistent form
  (no g0). Dimensional check: kg/s^3/K = W/(m^2*K) exactly (verified).
"""

import numpy as np
import json
import math
import warnings
from typing import Dict, List, Tuple, Optional

from scipy.optimize import brentq

from hrma.constants import G_0, R_UNIVERSAL, STEFAN_BOLTZMANN
from hrma.data.materials_db import build_materials_view, temperature_limits
# Malzeme kaydının YANITA konan biçimi (beyanlarıyla) — yapısal modülle TEK
# ortak kaynak. İki modül aynı kaydı yayımladığı için metin tek yerde durur.
from hrma.analysis.structural_analysis import published_material_record

# Universal gas constant for frozen Cp / R_specific derivation.
# ÖH D18 / altyapi (P10B3-10): yerel 8314.462618 literali KALKTI; değer
# hrma/constants.py'den gelir (CODATA 2018). constants.py "magic-number
# tutarsızlıkları bu modül üzerinden önlenir" diyordu ama bu dosya kendi
# kopyasını taşıyordu — değer aynıydı, yani kusur değil AYRIŞMAYA AÇIK
# KAPIYDI. Birim yorumu korunur: J/(kmol*K) == J/(mol*K)*1000; burada MW
# g/mol cinsinden kullanılır.


#: ÇIPLAK CİDAR kararlı denge kontrolünün KRİTİK kodları (aşağıdaki
#: ``_analyze_gas_side_heat_transfer`` ve ``_analyze_thermal_safety``
#: üretir). v3.0.1 (V301/H-termal): yalnız hibrit motor okur — kamara bölge
#: hükmü (yakıt bloğu koruması + astar) bu kayıtların yerini ancak bütün
#: bölgeler korunduğunda alır (``hybrid_rocket_engine.
#: _chamber_wall_zones_block``). Bu modülün hesabı ve çıktısı DEĞİŞMEZ;
#: tanım burada durur çünkü kodların sahibi bu modüldür (tek kaynak).
BARE_WALL_CRITICAL_CODES = (
    'warn.thermal.wall_exceeds_melting',
    'warn.thermal.wall_exceeds_service',
    'warn.thermal.wall_nonphysical',
    'warn.thermal.wall_pinned_adiabatic',
    'warn.thermal.temp_exceeds_allowable',
    'warn.thermal.max_temp_exceeds_melting',
)


def _mk_warning(code: str, severity: str = 'info', **params) -> Dict:
    """Yapılandırılmış iki-dilli uyarı/öneri kaydı (D-track sözleşmesi).

    Backend dilsiz kalır; frontend ``TF(code, params)`` ile metni kurar.
    Şema: ``{code: 'warn.<subsystem>.<slug>', params: {...}, severity: ...}``.
    f-string içine gömülü sayısal değerler artık ``params`` içinde döner;
    i18n metni ``{yer_tutucu}`` ile aynı değeri gösterir.
    Katalog: docs/v262_specs/D_codes_analysis.md.
    """
    return {'code': code, 'params': params, 'severity': severity}


def _positive_length(value):
    """Sonlu ve pozitifse float döner, değilse ``None``.

    Geometri alanlarında 0 / '' / None hepsi "VERİLMEDİ" demektir; bunları
    sayı sanmak (örn. ``dict.setdefault`` ile 0'ı geçerli kabul etmek) boğaz
    yarıçapını sıfırlar.

    ÖH D30 / termo-ucus a1 · defter OH-D29-06 (OH-D27-11 termo payı) —
    KARAR ARTIK MERKEZDE. Bu ad yalnız modül içi bir takma addır; hüküm
    :func:`hrma.utils.input_guard.finite_positive`'tedir (TEK KAYNAK,
    CLAUDE.md kural #11). D28'de merkezîleştirme ENGELLİYDİ: karşılık
    (``finite_positive``) ihracat kulvarının dalındaydı ve bu ağaçta
    yoktu; engel birleşmeyle kalktı (ölçüldü: ``once.json`` K1).

    ÖLÇÜLEN AYRIŞMA (``once.json`` K3, 18 prob): yerel tanım merkezden
    **2 kararda** ayrışıyordu ve ikisi de aynı delikti — ``float(True)``
    ``1.0``'dir. ``bool`` ve ``numpy.bool_`` bir ÖLÇÜ DEĞİLDİR (P5B4-16
    hükmü). Ürün yüzeyinde ölçülen sonuç (``once.json`` K4): tüm zorunlu
    ısı-analizi alanları ``True`` gönderildiğinde
    ``missing_heat_transfer_inputs`` **5 alanın 5'ini de** "verilmiş"
    sayıyordu — yani ``True`` bir hazne basıncı (1,0 Pa) ve bir hazne
    çapı (1,0 m) yerine geçiyordu. Fail-closed ihlali (doktrin 1).

    İÇE AKTARMA NEDEN GECİKTİRİLİR (ölçüldü, tahmin değil): bu modülü
    ``hrma.engines.__init__`` içe aktarır. Modül düzeyinde ``hrma.utils``
    istenirse paketin ``__init__``i ``hrma.utils.injector_design`` →
    ``hrma.engines.*`` zincirini tetikler, ``hrma.engines.__init__`` de
    YARIM yüklenmiş bu modülden ``HeatTransferAnalyzer``ı ister ve
    ``ImportError`` alır. Ölçüm: ``import hrma.analysis
    .trajectory_analysis`` taban ağacında **0** uyarı verirken modül
    düzeyi içe aktarmayla **1** uyarı veriyordu ("Could not import some
    engine modules") — yani motor paketi sessizce EKSİK yükleniyordu.
    Çağrı anında zincir tamamlanmış olur; maliyet ``sys.modules``
    aramasıdır ve bu kapı sıcak döngüde çağrılmaz.
    """
    from hrma.utils import input_guard
    return input_guard.finite_positive(value)


# ----------------------------------------------------------------------
# Gaz radyasyonu (Leckner) sabitleri
# ----------------------------------------------------------------------
# Yanma ürünü ışıyan tür mol kesri varsayılanları. Hidrokarbon yakıt +
# N2O/LOX oksitleyici sistemlerinde (HTPB/N2O, RP-1/LOX, parafin/N2O)
# denge kompozisyonu tipik olarak ~%20-30 H2O ve ~%10-20 CO2 içerir
# (kalan N2/CO/H2/OH: kızılötesinde ya şeffaf ya ikincil). RocketCEA /
# Cantera kompozisyonu motor_data['x_H2O'] / ['x_CO2'] ile geçilirse
# bu varsayımlar devre dışı kalır.
DEFAULT_X_H2O = 0.25
DEFAULT_X_CO2 = 0.15

# --- Işıyan tür kompozisyonunun KÖKENİ (ÖH D17 / termo-ucus, P4B1-10 ŞARTı)
# Köken etiketi DEĞER eşitliğinden kurulamaz. D15 onarımı etiketi
# ``x == DEFAULT_X_H2O and y == DEFAULT_X_CO2`` karşılaştırmasından
# üretiyordu; bu, kompozisyonu AÇIKÇA veren ama tesadüfen modül
# varsayılanına eşit değer gönderen çağırana "bu senin girdin değil,
# modül varsayılanı" diyordu (ölçüldü: once.json K1,
# ``verildi_varsayilana_esit`` ve ``yalniz_x_H2O_verildi`` vakalarında
# etiket 'module default ... no x_H2O/x_CO2 was supplied' — iki yanlış
# köken). Köken, motor_data'da ANAHTARIN VERİLMİŞ olmasıdır; değeri
# neye eşit olduğu kökeni değiştirmez.
RADIATION_COMPOSITION_SOURCE_DEFAULT = (
    'module default (hydrocarbon/N2O class) — no x_H2O/x_CO2 was '
    'supplied with the motor data')
RADIATION_COMPOSITION_SOURCE_CALLER = 'caller supplied x_H2O / x_CO2'


def radiation_composition_source(has_x_h2o: bool, has_x_co2: bool) -> str:
    """Köken etiketini (yalnız) anahtarların verilip verilmediğinden kurar.

    TEK TANIM NOKTASI: hem ``analyze_heat_transfer`` hem
    ``analyze_axial_profile`` hem de doğrudan çağrılan
    ``_analyze_gas_side_heat_transfer`` bu işlevi kullanır; ikinci bir
    etiket metni yazılmaz.

    Kısmî hâl de dürüstçe adlandırılır: yalnız biri verilmişse etiket
    hangisinin çağırandan, hangisinin modül varsayılanından geldiğini
    ADIYLA söyler (eski etiket bu hâlde "ikisini de sen verdin" diyordu).
    """
    if has_x_h2o and has_x_co2:
        return RADIATION_COMPOSITION_SOURCE_CALLER
    if not has_x_h2o and not has_x_co2:
        return RADIATION_COMPOSITION_SOURCE_DEFAULT
    verilen, eksik = (('x_H2O', 'x_CO2') if has_x_h2o else ('x_CO2', 'x_H2O'))
    return (f'caller supplied {verilen}; module default '
            f'(hydrocarbon/N2O class) for {eksik}')


def resolve_radiation_composition(motor_data: Dict) -> Tuple[float, float, str]:
    """``motor_data`` -> ``(x_H2O, x_CO2, köken etiketi)``.

    Anahtar YOK ya da açıkça ``None`` ise modül varsayılanı kullanılır ve
    etiket bunu söyler; anahtar VARSA değer ne olursa olsun köken
    çağırandır. Sayısal olmayan bir değer sessizce varsayılana DÜŞMEZ —
    ``float()`` hatası çağırana çıkar (fail-closed).
    """
    ham_h2o = motor_data.get('x_H2O') if isinstance(motor_data, dict) else None
    ham_co2 = motor_data.get('x_CO2') if isinstance(motor_data, dict) else None
    var_h2o = ham_h2o is not None
    var_co2 = ham_co2 is not None
    x_h2o = float(ham_h2o) if var_h2o else DEFAULT_X_H2O
    x_co2 = float(ham_co2) if var_co2 else DEFAULT_X_CO2
    return x_h2o, x_co2, radiation_composition_source(var_h2o, var_co2)

# Ortalama ışın uzunluğu katsayısı: L = 0.9 * D (silindirik hazne için
# standart mühendislik yaklaşımı; Hottel ortalama ışın uzunluğu tablosu,
# sonsuz silindir 0.95D, L/D~1 silindir 0.6-0.7D bandının üst-orta değeri).
MEAN_BEAM_LENGTH_FACTOR = 0.9

# Soğutucu tarafı tasarım sıcaklık farkları [K] — mühendislik kabulü,
# literatür formülü DEĞİL (dürüstlük notu: bunlar boyutlandırma
# kabulüdür; her biri A = Q/(h*dT) ifadesinde dT olarak kullanılır).
#
# ÖH Z5S / PK5 (P4B1-06): sözlük SINIFTAN MODÜL DÜZEYİNE taşındı; artık
# "modelin gerçekten çözebildiği soğutma tipleri" listesinin TEK TANIM
# NOKTASI budur ve uç kapıları da (hrma/app.py) buradan okur. Eskiden
# tanınmayan tip sessizce doğal taşınıma düşüyordu: ``film`` /
# ``ablative`` / ``radiation`` HTTP 200 alıyor, ``required_cooling_area =
# 0,0 m²`` yayımlanıyor ve ``design_parameters.cooling_type`` kullanıcının
# seçtiği tipi geri okuyordu — yani yanıt "film soğutma" yazıp doğal
# taşınımın (h = 25 W/m²K) sayılarını basıyordu.
COOLING_DESIGN_DELTA_T = {
    'natural': 50.0,        # K (doğal taşınımda cidar-hava farkı)
    'forced': 100.0,        # K (zorlanmış hava)
    'regenerative': 100.0,  # K (cidar-soğutucu film farkı)
}

#: Modelin ÇÖZEBİLDİĞİ soğutma tipleri. Listede olmayan bir tip için ne
#: soğutucu-tarafı katsayısı ne tasarım ΔT'si vardır; sayı ÜRETİLMEZ.
SUPPORTED_COOLING_TYPES = tuple(COOLING_DESIGN_DELTA_T)

#: Soğutucu akışkanın özgül ısısı [J/kg/K] — YALNIZ akışkanın KİMLİĞİ bu
#: modülce biliniyorsa (ÖH D15, P4B1-05).
#:
#: Zorlanmış taşınımda soğutucu HAVADIR ve cp'si ortam koşullarında iyi
#: bilinir. Rejeneratif soğutmada soğutucu MOTORUN KENDİ PROPELANIDIR
#: (RP-1 ~2000, LH2 ~14300, metan ~3500 J/kg/K); bu modül propelan
#: kimliğini almaz, dolayısıyla burada KAYDI YOKTUR ve uydurulmaz.
#: v2.6.26'ya kadar rejeneratif dal SUYUN cp'sini (4180) varsayıyordu —
#: 60 bar / 3400 K motorda soğutucu debisi propelan debisinin %127'si
#: çıkıyor, künye alanı hiç yayımlanmıyordu.
COOLANT_SPECIFIC_HEAT_J_KGK = {
    'forced': 1005.0,   # kuru hava, 300 K (Incropera, Tablo A.4)
}

#: ``COOLANT_SPECIFIC_HEAT_J_KGK`` kayıtlarının kaynak künyesi.
COOLANT_SPECIFIC_HEAT_SOURCE = {
    'forced': ('dry air at 300 K, 1 atm — Incropera & DeWitt, '
               'Fundamentals of Heat and Mass Transfer, Table A.4'),
}

#: Rejeneratif dalda cp'yi taşıyabilecek çağıran alanı (motor_data anahtarı).
COOLANT_CP_INPUT_FIELD = 'coolant_specific_heat_J_kgK'

#: Soğutma sınıfının BEYANLI sıralama göstergesi (ÖH Z5S / PK5, P4B1-20).
#: Bu bir ÖLÇÜM DEĞİLDİR: ısı yüküne, hazne boyuna, malzemeye ve cidar
#: kalınlığına duyarsızdır; yalnız üç soğutma sınıfını birbirine göre
#: sıralar. Künyesi ``_cooling_efficiency_basis``te yazılıdır ve çıktıda
#: ``cooling_efficiency_basis`` / ``cooling_efficiency_source`` alanlarıyla
#: yayımlanır (kardeşleri ``heat_sink_*_basis`` ile aynı sözleşme).
COOLING_EFFICIENCY_BY_TYPE = {
    'natural': 0.3,
    'forced': 0.6,
    'regenerative': 0.9,
}

#: ``cooling_efficiency``in kaynak künyesi. Sayıların ardında bir literatür
#: korelasyonu YOKTUR; bunu saklamak yerine yazıyoruz (kaynak beyanı).
COOLING_EFFICIENCY_SOURCE = (
    'HRMA internal ordering table (no literature correlation): the three '
    'values 0.3 / 0.6 / 0.9 rank natural, forced and regenerative cooling '
    'against each other and are not derived from a measurement or a '
    'published correlation.')


#: SOĞUTUCU TARAFI FİLM KATSAYISI — BEYAN EDİLEN TİPİK BANT (ÖH D31 / P12bB4-06).
#: Bu üç sayı bir KORELASYON DEĞİLDİR. Soğutma kanalı geometrisi, soğutucu
#: debisi ve soğutucunun kimliği verilmediğinde soğutucu tarafı ÇÖZÜLEMEZ;
#: aşağıdaki değerler o durumda YALNIZ ``method='not_modelled'`` künyesiyle
#: yayımlanır (ne olduğunu söyleyen bir tasarım kabulü, hesap değil).
#: ÖLÇÜLDÜ (``once_p12bb406.json``, taban 9d70e9ed): dört ayrı kanal
#: tasarımında (64x2x3 mm / 16x6x6 mm / aynı kanalda 8 kg/s / RP-1 40x3x4 mm)
#: ürünün döndürdüğü değer 20.000 W/m²K'de SABİT kalıyordu; aynı girdilerde
#: Dittus-Boelter 6.639,7 - 77.412,6 W/m²K veriyor (11,66x yayılım; ürün/DB
#: oranı 0,2584 - 3,0122) ve cidar iç sıcaklığı dört tasarımda da 1062,03 K
#: çıkıyordu — yani kanal tasarımı sonuca HİÇ girmiyordu.
#: Bandın kaynakları:
#:   - Huzel & Huang, "Modern Engineering for Design of Liquid-Propellant
#:     Rocket Engines", AIAA Progress in Astronautics and Aeronautics
#:     Vol. 147, Böl. 4: sıvı rejeneratif kanal tarafı tipik olarak
#:     1e4-5e4 W/m²K.
#:   - Incropera & DeWitt, "Fundamentals of Heat and Mass Transfer", 6. bs.,
#:     Tablo 1.1: gazlarda doğal taşınım 2-25, zorlanmış taşınım
#:     25-250 W/m²K.
COOLANT_SIDE_DECLARED_TYPICAL = {
    'natural': 25.0,
    'forced': 100.0,
    'regenerative': 20000.0,
}

#: ``COOLANT_SIDE_DECLARED_TYPICAL``in kaynak künyesi — çıktıda
#: ``coolant_side_source`` alanıyla yayımlanır (kardeşi
#: ``COOLING_EFFICIENCY_SOURCE`` ile aynı sözleşme).
COOLANT_SIDE_DECLARED_SOURCE = (
    'declared typical band, NOT a correlation: natural/forced from Incropera '
    '& DeWitt 6th ed. Table 1.1 (free convection in gases 2-25, forced '
    'convection in gases 25-250 W/m^2/K), regenerative from Huzel & Huang '
    '(AIAA Vol. 147) Ch. 4 (liquid regenerative channels 1e4-5e4 W/m^2/K). '
    'Channel geometry, coolant flow rate and coolant identity do not enter '
    'this number.')

#: Soğutucu tarafı KORELASYON yolunun istediği alanlar. Adlar kardeş
#: ``hrma.analysis.regen_cooling`` modülünün okuduğu adlarla BİREBİR aynıdır
#: (tek kaynak: aynı kanal iki modülde iki ayrı adla istenmez).
#: ``channel_width`` / ``channel_height`` METRE, ``coolant_mdot`` kg/s.
COOLANT_CHANNEL_REQUIRED_FIELDS = (
    'n_channels', 'channel_width', 'channel_height', 'coolant_mdot',
    'coolant',
)

#: Bu modülün soğutucu-tarafı korelasyonunu kurabildiği akışkanlar: özellik
#: tabloları ``regen_cooling.water_properties`` / ``rp1_properties``
#: (Incropera Tablo A.6 / "Huzel & Huang Ek" — ÖH KU, SP-H1 K50: NASA SP-125
#: 1967'de Ek yok; RP-1 özellikleri Tablo 1-4 (s. 21'den sonra, sayfa no
#: basılı değil) ve Tablo 6-3 s. 188; tablonun gerçek kaynağı sayfa
#: düzeyinde doğrulanmadı). Metan ve hidrojen KRİTİK ÜSTÜ
#: çalışır; orada Dittus-Boelter geçerli değildir (Jackson korelasyonu
#: gerekir) ve o yol ``regen_cooling.RegenCooling`` çözücüsündedir — burada
#: sayı ÜRETİLMEZ, ``not_modelled`` beyan edilir.
COOLANT_SIDE_TABLE_FLUIDS = ('water', 'rp1')


def is_supported_cooling_type(cooling_type) -> bool:
    """``cooling_type`` modelin çözebildiği tiplerden mi?

    Uç kapıları (``hrma/app.py``) bu işlevi çağırır; eşik listesi tek
    yerde durur (parametre tutarlılığı kuralı). Harf büyüklüğü ve baş/son
    boşluğu hoşgörür — ad çözümü kimliği değiştirmez, yalnız yazımı.
    """
    if cooling_type is None:
        return False
    return str(cooling_type).strip().lower() in COOLING_DESIGN_DELTA_T


# Leckner (1972) toplam emisivite korelasyonu katsayı matrisleri.
# Kaynak: B. Leckner, "Spectral and total emissivity of water vapor and
# carbon dioxide", Combustion and Flame 19(1):33-48, 1972; M.F. Modest,
# "Radiative Heat Transfer", 3rd ed., Academic Press, Table 10.4
# (2. baskı Table 11.2) düzeninde:
#
#   eps_0 = exp( sum_i a_i(t) * x^i ),   x = log10(p_a*L / 1 bar*cm),
#   a_i(t) = sum_j C[i][j] * t^j,        t = T / 1000 K.
#
# Satırlar a_0, a_1, a_2; sütunlar t^0, t^1, t^2 (CO2 için t^3 dahil).
_LECKNER_T0 = 1000.0  # K
_LECKNER_H2O = (
    (-2.2118, -1.1987, 0.035596),
    (0.85667, 0.93048, -0.14391),
    (-0.10838, -0.17156, 0.045915),
)
_LECKNER_CO2 = (
    (-3.9893, 2.7669, -2.1081, 0.39163),
    (1.2710, -1.1090, 1.0195, -0.21897),
    (-0.23678, 0.19731, -0.19544, 0.044644),
)
# Korelasyonun fit aralığı dışına taşmayı önleyen kelepçeler (mühendislik
# bekçileri; literatür sınırı değil): sıcaklık Leckner fit aralığında
# tutulur (~300-3000 K). Roket haznesi 3000 K üstünde kalabilir; eps_g
# sıcaklıkla düştüğünden T'yi 3000'de kelepçelemek emisiviteyi hafif
# ABARTIR = muhafazakâr yön (tasarım-yükü felsefesi, codex teyitli).
# Optik derinlik 1e-4..1e3 bar*cm bandında tutulur.
#
# GEÇERLİLİK BEYANI (v2.6.2, fizik denetimi F115): Leckner (1972) toplam
# emisivite fitinin BİLDİRİLEN sıcaklık geçerlilik aralığı ~300-2500 K'dir
# (Modest, Radiative Heat Transfer, Tablo 10.4 geçerlilik notu). Buradaki
# 3000 K kelepçesi bilinçli bir EKSTRAPOLASYONdur: roket haznesi 3000-3600 K
# çalıştığı için korelasyon zaten her çağrıda 2500 K zarfının dışındadır ve
# kelepçe olmadan fit polinomu tanımsız bölgeye gider. Kelepçenin yönü
# muhafazakârdır (eps_g bu bantta T ile düştüğünden 3400 K'lik gazı 3000 K'de
# değerlendirmek eps'i hafif ABARTIR -> radyatif yük fazla, güvenli taraf).
# Bu, q_rad'ın "±%25 mertebesinde belirsizlik taşıyan mühendislik tahmini"
# olduğu anlamına gelir; kesin değer değildir.
_LECKNER_T_MIN = 300.0    # K
_LECKNER_T_MAX = 3000.0   # K (mühendislik kelepçesi — literatür sınırı DEĞİL)
_LECKNER_T_LITERATURE_MAX = 2500.0  # K (Leckner 1972 bildirilen fit üst sınırı)
_LECKNER_PAL_MIN = 1e-4   # bar*cm
_LECKNER_PAL_MAX = 1e3    # bar*cm

#: ÖH Z5S / PK5 (P4B1-20) — RADYASYON MODELİ KÜNYESİ (yayımlanan metin).
#: Yukarıdaki üç bilinçli sapma/kelepçe kod yorumlarında ayrıntılı yazılıydı
#: ama ÇIKTIDA hiç görünmüyordu; radyasyon terimi tasarım akısının içine
#: girdiği için kullanıcının okuduğu sayının bir parçasıdır ve künyesi de
#: onunla birlikte yayımlanmalıdır.
RADIATION_MODEL_BASIS = (
    'Gas radiation uses the Leckner (1972) total-emissivity correlation as '
    'tabulated by Modest, "Radiative Heat Transfer" 3rd ed. Table 10.4 '
    '(Eq. 10.140-10.146). Form note (1): the pressure-correction '
    'denominator is written A+B-1+P_E. This is NOT a departure from the '
    'correlation: Howell\'s online appendix (Eqs. A.5/A.6) gives the same '
    '+P_E denominator in an algebraically identical form; whether the '
    'Modest page prints -P_E (which would put a pole near P_E ~ 2 bar) has '
    'not been page-verified here. Two DELIBERATE departures from the source '
    'are in effect and change the number: (2) the pressure '
    'correction is clamped to the 0.3-2.0 band seen in the Leckner charts, '
    'so far outside the fit it cannot diverge; (3) the gas temperature is '
    f'clamped to {_LECKNER_T_MAX:.0f} K while the reported validity limit '
    f'of the fit is about {_LECKNER_T_LITERATURE_MAX:.0f} K, i.e. a rocket '
    'chamber is ALWAYS evaluated outside the published envelope. The clamp '
    'direction is conservative (emissivity falls with temperature in this '
    'band, so evaluating a hotter gas at the ceiling overstates the '
    'radiative load), but the radiative flux is an engineering estimate '
    'carrying roughly +/-25% uncertainty, not a precise value.')

#: ÖH KU (KC-13, 6 Eki 2026) — GAZ TARAFI MODELİNİN SINIRLARI (BEYAN; sayı
#: değişmez). Yayımlanan alan: ``heat_transfer_coefficients
#: ['gas_side_model_limits']``. Kaynaklar:
#:   * NASA SP-8124 (1977) s. 53: laminerleşme yerel Stanton sayısını 2-3 kat
#:     düşürebilir; tipik olarak P_c·F < ~10^5 lbf²/in² motorlarda; s. 55:
#:     kuramsal ölçüt K ≥ 3,3e-6 (Kays, ref. 98); s. 84: P_c·F < 200 000
#:     lbf²/in² uygulamalarında dikkate alınmalı (yerel metinden doğrulandı).
#:     Bu modülde itki girdisi YOK, bu yüzden P_c·F eleği HESAPLANMAZ.
#:   * Kumakawa vd. 1991 NAL TR-1126T §3.3, §4: Ni kaplama ölçülen akıyı
#:     Bartz'ın 0,7-0,8'ine, karbon birikimi %50'ye düşürüyor (ASYA notu;
#:     bu ajan sayfayı doğrulamadı). KARI odaları ZrO2 TBC'li.
GAS_SIDE_MODEL_LIMITS_BASIS = (
    'Two gas-side effects are NOT modelled and both make the published '
    'flux HIGH (conservative for the wall, misleading for validation): '
    '(1) boundary-layer laminarization under strong acceleration - NASA '
    'SP-8124 (1977) p. 53 reports local Stanton numbers 2-3x below the '
    'turbulent value, typically for chamber pressure x thrust below about '
    '1e5 lbf^2/in^2 (criterion K >= 3.3e-6, p. 55; consider it below 2e5, '
    'p. 84); this module has no thrust input, so that screen is not '
    'evaluated here; (2) wall coating and soot/carbon deposit resistance - '
    'Kumakawa et al. 1991 (NAL TR-1126T) measured Ni-plated walls at '
    '0.7-0.8 of Bartz and carbon deposits halving the flux; comparing this '
    'uncoated result with a coated or sooted test chamber is biased high.')


# ----------------------------------------------------------------------
# Girdi kapısı (bebek-Scofield F4-1)
# ----------------------------------------------------------------------
# ÖLÇÜM (17 Ağustos 2026, HEAD f9d95eb):
#   ``HeatTransferAnalyzer().analyze_heat_transfer(motor_data={})``
#   HTTP 200 karşılığı TAM bir sonuç döndürüyordu: 155 yaprağın hepsi dolu,
#   ``gas_side_analysis.heat_flux = 13 027 380,54 W/m²``,
#   ``safety_analysis.risk_level = 'HIGH'``. Boş girdi ile DOLU girdi
#   arasında FARKLI yaprak sayısı SIFIR idi — yani kullanıcı hiçbir şey
#   vermeden "motorunun" ısı analizini okuyordu.
#
# Kök neden sözleşme kırığıydı: fonksiyonun kendi belgesi bu anahtarları
# "verilmezse FİZİKSEL OLARAK TÜRETİLİR" diye ilan ediyordu, davranış ise
# altısını da SABİTLE dolduruyordu (20 bar / 3000 K / 0,1 m / 0,5 m / 10 s /
# 1 kg/s). Bunların hiçbiri türetilmiyordu; uydurulmuş varsayılanlardı.
#
# Çözüm deponun kendi desenidir: kardeş uçlar (/analyze_safety,
# /analyze_structural_safety) aynı durumda 422 + ``missing_fields`` döner ve
# "A safety assessment cannot be produced from defaults." der. Burada da
# eksik girdi ADIYLA reddedilir.
#: Isı analizinin TÜRETEMEYECEĞİ zorunlu girdiler. Her biri yayımlanan bir
#: sayıyı doğrudan ölçekler: Pc ve Tc Bartz kütle akısını ve kurtarma
#: sıcaklığını, hazne çapı/boyu ıslak yüzeyi (dolayısıyla toplam ısı
#: yükünü), yanma süresi toplam ısı enerjisini kurar.
HEAT_TRANSFER_REQUIRED_FIELDS = (
    'chamber_pressure',     # bar
    'chamber_temperature',  # K
    'chamber_diameter',     # m
    'chamber_length',       # m
    'burn_time',            # s
)

#: Boğaz ölçeği: bunlardan EN AZ BİRİ gerekir. Boğaz alanı verilmediyse
#: ``A_t = mdot * c* / Pc`` (c* tanımı, tıkalı boğazda süreklilik) ile
#: GERÇEKTEN türetilir — bu meşru bir türetimdir, varsayılan değildir.
#: Üçü de yoksa modül eskiden ``A_t = pi*(0,3*D_ch/2)²`` diye bir başparmak
#: kuralına düşüyordu; kaynaksız bir 0,3 katsayısıyla boğaz uydurmak yasak.
HEAT_TRANSFER_THROAT_SCALE_FIELDS = ('throat_diameter', 'throat_area',
                                     'mdot_total')

# --- ÖZGÜL ISI ORANI BANDI (ÖH D21 / P4B1-16, doktrin-4 TEK KAYNAK) ------
# Bu bant v2.6.27'ye kadar ÜÇ dosyada ayrı ayrı yazılıydı:
#   heat_transfer_analysis.py :483   ``if not (1.05 < gamma < 1.67)``
#   nozzle_flow_1d.py         :340   aynı bant, ama ``raise ValueError``
#   regen_cooling.py          :715   aynı bant, ama ``raise ValueError``
# ve ``hrma/cfd/gas_transport.py`` bandın SAHİBİ olarak bu dosyayı
# gösteriyordu. Sayı artık burada bir kez tanımlanır; iki tüketici modül
# onu ithal eder (ikisi de zaten bu modülü ithal ediyor, döngü yok).
#
# Bant, burada kullanılan donmuş-akış Bartz bağıntılarının
# (Pr = 4γ/(9γ−5), cp = γR/(γ−1)) tanımlı kaldığı aralıktır: Pr'nin
# γ = 5/9 ≈ 0,556 kutbu ve cp'nin γ = 1 kutbu alttan, tek atomlu gaz
# sınırı γ = 5/3 ≈ 1,667 üstten sınırlar.
GAMMA_BAND_MIN = 1.05
GAMMA_BAND_MAX = 1.67

#: γ HİÇ verilmediğinde kullanılan depo varsayılanı (tipik hidrokarbon /
#: N2O yanma ürünü karışımı). Bu bir sessiz yedek DEĞİLDİR: çıktı
#: ``gas['gamma_source'] == 'repo_default'`` künyesini taşır, yani
#: çağıran hangi γ'nın nereden geldiğini okur.
GAMMA_REPO_DEFAULT = 1.20
#: Modül varsayılan molekül ağırlığı [g/mol] (çağıran MW ya da gaz sabiti
#: vermezse; ÖH D37 A2-1 termal 7. tur — sabit adlandırıldı, değer aynı).
MW_MODULE_DEFAULT_G_MOL = 24.0

#: Bant dışı γ'nın ortak reddi (üç modül de AYNI cümleyi kurar).
#: ÖLÇÜLDÜ (ÖH D21 / once.json K1, taban 35aa279): bu modül γ=1,02 ve
#: γ=3,00 girdilerinin İKİSİNİ birden sessizce 1,20 yapıyor, üretilen
#: uyarı sayısı 0, dönen sözlükte tek bir kelepçe künyesi yok — kardeş
#: iki modül aynı girdide ValueError atarken.
GAMMA_BAND_REJECTION = (
    'gamma must be within ({lo}, {hi}) — outside that band the frozen '
    'Bartz relations used here (Pr = 4g/(9g-5), cp = g*R/(g-1)) are not '
    'defined. The supplied value {value!r} is NOT clamped to a default: '
    'a heat-transfer verdict computed from a specific-heat ratio the '
    'caller never asked for would be a fabricated number.')


def _guard_gamma_band(value, field_name='gamma'):
    """Bant dışı γ'yı REDDEDER (kelepçelemez) — ÖH D21 / P4B1-16.

    ``nozzle_flow_1d`` ve ``regen_cooling`` bu bandı zaten reddediyordu;
    bu modül aynı girdide sessizce 1,20'ye çekiyordu. Asimetri kalktı.
    """
    g = float(value)
    if not (GAMMA_BAND_MIN < g < GAMMA_BAND_MAX):
        raise ValueError(
            GAMMA_BAND_REJECTION.format(
                lo=GAMMA_BAND_MIN, hi=GAMMA_BAND_MAX, value=value)
            + (" (field: %s)" % field_name))
    return g


class MissingHeatTransferInput(ValueError):
    """Isı analizi zorunlu girdisi eksik — hüküm üretilmedi.

    ``ValueError`` alt sınıfıdır: mevcut çağıranların ``except ValueError`` /
    ``except Exception`` dalları davranışlarını korur. ``missing_fields``
    makine-okur listedir; uç katmanı bunu 422 gövdesine aynen koyabilir.
    """

    def __init__(self, missing_fields):
        self.missing_fields = list(missing_fields)
        super().__init__(
            'A heat transfer analysis cannot be produced from defaults. '
            'Missing required inputs: ' + ', '.join(self.missing_fields)
            + '. These values set the Bartz mass flux, the recovery '
              'temperature and the wetted area; they are not assumed on '
              'your behalf.')


#: ``throat_diameter`` ile ``throat_area`` BİRLİKTE verildiğinde ikisinin
#: aynı ÖLÇÜ sayılabilmesi için bağıl tolerans (ÖH D21 / P4B1-17).
#: Aynı geometriden türeyen iki sayı ~1e-15 bağılda uyuşur; 6 anlamlı
#: haneye yuvarlanmış bir çift ~1e-7'de kalır. Boşaltma katsayısı
#: düzeltilmiş ETKİN alan ile geometrik alan arasındaki fark ise
#: ölçüldüğünde %2,08 (once.json K2) — dört mertebe büyük, yani bu
#: tolerans yuvarlamayı geçirir, iki AYRI ölçüyü geçirmez.
THROAT_AREA_CONSISTENCY_REL_TOL = 1e-6


class ConflictingHeatTransferInput(ValueError):
    """İki girdi AYNI büyüklüğü ÇELİŞKİLİ söylüyor — hüküm üretilmedi.

    ÖH D21 / P4B1-17. ``MissingHeatTransferInput`` ile aynı sözleşme
    (``ValueError`` alt sınıfı, makine-okur alan listesi): uç katmanı
    ``conflicting_fields``i 422 gövdesine aynen koyabilir.

    ÖLÇÜLDÜ (once.json K2, taban 35aa279): ``throat_diameter=0,05`` ve
    ``throat_area = 0,9796·π(d/2)²`` (tipik C_D düzeltmeli etkin alan)
    birlikte verildiğinde modül alanı SESSİZCE geometrik değere yeniden
    yazıyordu — çağıranın gönderdiği etkin alan %2,0825 bağıl kayarak
    yok oluyor, dönen sözlükte hangi sayının kazandığını söyleyen tek bir
    künye bulunmuyordu.
    """

    def __init__(self, conflicting_fields, detail=''):
        self.conflicting_fields = list(conflicting_fields)
        super().__init__(
            'Two inputs describe the same quantity and disagree: '
            + ', '.join(self.conflicting_fields)
            + '. ' + detail
            + ' Neither value is silently preferred: send only the one '
              'that is authoritative for this analysis.')


class UnresolvedMaterial(ValueError):
    """Malzeme adı ``materials_db``de hiçbir kayda çözülmüyor (ÖH Z5S / S4).

    ``MissingHeatTransferInput`` ile aynı sözleşme: ``ValueError`` alt
    sınıfıdır (mevcut ``except ValueError`` / ``except Exception`` dalları
    davranışlarını korur) ve makine-okur alanlar taşır.

    NEDEN İSTİSNA, NEDEN SESSİZ YEDEK DEĞİL — ÖLÇÜLDÜ (28 Ağustos 2026):
    bu sınıf yazılmadan önce satır

        mat_props = self.materials.get(material, self.materials['steel'])

    ham sözlük araması yapıyordu. ``materials_db``nin kendi çözümleyicisi
    (``_resolve``) ``lower()`` uyguladığı için ``'STEEL_4130'`` orada
    çözülüyor, BURADA çözülmüyordu. Sonuç, tek yanıtta iki malzemeydi:

        design_parameters.material     = 'STEEL_4130'
        material_properties.name       = 'Carbon steel (generic, A36-class)'
        safety_analysis.risk_level     = 'HIGH'   (basılıyor)

    ve erime emniyet katsayısı 0,5736 yerine 0,5965 oluyordu. Aynı sessiz
    yedek ``'peynir'`` için de çalışıyor, yani HİÇ VAR OLMAYAN bir malzeme
    için tam bir termal güvenlik hükmü yayımlanıyordu (P16B1-03, P16B3-03).

    Yedek malzeme SEÇMEK bu modülün işi değildir: bu modülün bütün
    sayıları (iletkenlik, erime marjı, termal gerilme) malzemeyle
    ölçeklenir, dolayısıyla başka bir malzemenin sayısını basmak
    kullanıcının sormadığı bir motoru yayımlamaktır.
    """

    def __init__(self, requested, available):
        self.requested = requested
        self.available = list(available)
        super().__init__(
            f"Unknown wall material {requested!r}: it does not resolve to a "
            f'materials_db record. No property was substituted, because '
            f'every heat transfer number scales with the material. '
            f'Available: {", ".join(self.available)}')


def resolve_material_key(material) -> str:
    """Malzeme adını ``materials_db`` kanonik anahtarına çözer.

    ``materials_db.get_material_safe`` ile AYNI kuralı kullanır (küçük
    harfe indirme + ``ALIASES``); yeni takma ad İCAT ETMEZ. Çözülemeyen ad
    ``UnresolvedMaterial`` yükseltir — sessiz yedek yoktur.
    """
    from hrma.data.materials_db import get_material_safe, list_materials
    if material is None:
        raise UnresolvedMaterial(material, list_materials())
    try:
        _rec, key = get_material_safe(str(material).strip())
    except KeyError:
        raise UnresolvedMaterial(material, list_materials()) from None
    return key


def _missing_heat_transfer_inputs(motor_data: Dict) -> List[str]:
    """Eksik zorunlu ısı-analizi girdilerinin ADLARI (yoksa boş liste).

    Ölçü sözleşmesi bu dosyanın ``_positive_length`` hükmüyle AYNIDIR:
    ``None`` / ``''`` / 0 / negatif / NaN hepsi "verilmedi" demektir. Sıfır
    hazne basıncı ya da sıfır yanma süresi bir ölçüm değildir.
    """
    data = motor_data if isinstance(motor_data, dict) else {}
    missing = [key for key in HEAT_TRANSFER_REQUIRED_FIELDS
               if _positive_length(data.get(key)) is None]
    if all(_positive_length(data.get(key)) is None
           for key in HEAT_TRANSFER_THROAT_SCALE_FIELDS):
        missing.append(' or '.join(HEAT_TRANSFER_THROAT_SCALE_FIELDS))
    return missing


def missing_heat_transfer_inputs(motor_data: Dict) -> List[str]:
    """``_missing_heat_transfer_inputs``ın uç katmanına açık adı (ÖH Z3).

    Uç katmanı kapıyı KENDİ yeniden yazmasın diye vardır: ``/analyze_thermal_
    safety`` ve ``/api/advanced-analysis`` isteği reddetmeden ÖNCE eksik alan
    listesini buradan alır (P4B1-01'in kökü, kapının uçta kopyalanmasıydı).
    Aynı listeyi ``MissingHeatTransferInput.missing_fields`` de taşır; tek
    tanım noktası yukarıdaki özel işlevdir.
    """
    return _missing_heat_transfer_inputs(motor_data)


class HeatTransferAnalyzer:
    """Heat transfer analysis for hybrid rocket motor chambers"""

    def __init__(self):
        # v2.6.27: merkezî tanımdan (hrma/constants.py) — yerel kopya kalktı.
        self.stefan_boltzmann = STEFAN_BOLTZMANN  # W/(m^2*K^4), CODATA 2018
        # ÖH D18 / altyapi (P10B3-10): merkezî tanımdan.
        self.g0 = G_0  # m/s^2 (standard gravity; NOT used in SI Bartz)

        # Malzeme veritabanı — MERKEZİ kaynaktan (Dalga 0, 2026-07-14).
        # Eski yerel termal tablo hrma/data/materials_db.py'ye taşındı ve
        # yapısal (mekanik) alanlarla TEK kayıtta birleştirildi (parametre
        # tutarlılığı kuralı). Termal değerler bire bir korunmuştur:
        # steel / steel_4130 / copper / ablative / graphite değişmedi.
        # 'aluminum' ve 'inconel' jenerik anahtarları artık alaşım
        # kayıtlarına (6061-T6, 718) çözülür; ss_304, ss_316, cucrzr ve
        # titanium_6al4v yeni seçilebilir malzemelerdir.
        # 'max_service_temperature': denge cidar sıcaklığı klamp üst sınırı.
        self.materials = build_materials_view()

    # ------------------------------------------------------------------
    # Gas property model (replaces hardcoded k=0.2, mu=5e-5, cp=1200)
    # ------------------------------------------------------------------
    def _get_gas_properties(self, motor_data: Dict, chamber_temperature: float) -> Dict:
        """
        Resolve combustion-gas transport properties for the Bartz correlation.

        Priority order (most authoritative first):
          1. Properties supplied directly in motor_data (e.g. from a prior
             Cantera / RocketCEA equilibrium solve upstream).
          2. Cantera equilibrium of an upstream-provided mechanism/composition
             (motor_data['cantera_gas'] handle), if present.
          3. Bartz-recommended frozen estimates derived from gamma and
             molecular weight, with a temperature-dependent viscosity
             correlation (Bartz 1957 / Sutton & Biblarz).

        Bartz (1957) recommends evaluating cp and Pr in the FROZEN sense:
            Pr = 4*gamma / (9*gamma - 5)              (Sutton & Biblarz Eq. 8-23)
            cp = gamma * R_specific / (gamma - 1)      (calorically-perfect)
        and a viscosity from the kinetic-theory-like correlation:
            mu = 1.184e-7 * (MW)^0.5 * T^0.6   [kg/(m*s)], MW in g/mol, T in K
            (Bartz 1957; reproduced in Sutton & Biblarz 9th ed.)
        """
        # --- gamma / molecular weight / R_specific ---
        #
        # ÖH D21 / P4B1-16 — BANT DIŞI γ ARTIK REDDEDİLİR, KELEPÇELENMEZ.
        # Eski iki satır ``if not (1.05 < gamma < 1.67): gamma = 1.20``
        # idi. ÖLÇÜLDÜ (once.json K1, taban 35aa279): γ=1,02 ve γ=3,00
        # girdilerinin İKİSİ de 1,20 dönüyordu (Pr 0,82759, cp 2078,62
        # J/kgK — yani KULLANICININ VERMEDİĞİ bir gazın Bartz akısı),
        # üretilen uyarı sayısı 0 idi ve dönen sözlükte kelepçeyi anan tek
        # bir alan yoktu. Kardeş iki modül (``nozzle_flow_1d``:340,
        # ``regen_cooling``:715) TAM AYNI girdide ValueError atıyordu:
        # aynı ürün, aynı bant, iki ayrı hüküm. Asimetri kalktı, bandın
        # sayısı da tek kaynağa (:GAMMA_BAND_MIN/MAX) taşındı.
        #
        # ÖH D21 / B3-13(c) — ``gamma_avg`` ADI: üretici
        # ``combustion_analysis._calculate_performance`` bu alana
        # ``thermo_props['stations']['chamber']['gamma']``ı, yani ODA
        # gamma'sını koyar; ortalama DEĞİLDİR (ad↔davranış örtüşmüyor).
        # Adın düzeltilmesi üreticiyi (hibrit kulvarının sahası)
        # gerektirir; burada yapılabilen, hangi alandan okunduğunun
        # künyeye yazılmasıdır (``gamma_source``).
        _gamma_ham = motor_data.get('gamma')
        if _gamma_ham is not None:
            gamma_source = 'gamma'
        else:
            _gamma_ham = motor_data.get('gamma_avg')
            gamma_source = (
                # ÖH D21 / B3-13(c): ad yalan söylüyor, künye söylemesin.
                "gamma_avg (producer: combustion_analysis performance."
                "gamma_avg — this is the CHAMBER gamma, not an average)"
                if _gamma_ham is not None else 'repo_default')
        if _gamma_ham is None:
            gamma = GAMMA_REPO_DEFAULT
        else:
            gamma = _guard_gamma_band(_gamma_ham, gamma_source.split(' ')[0])
        molecular_weight = motor_data.get('molecular_weight', None)  # g/mol
        R_specific = motor_data.get('gas_constant', None)            # J/(kg*K)
        if molecular_weight is None and R_specific is not None:
            molecular_weight = R_UNIVERSAL / R_specific
        if molecular_weight is None:
            molecular_weight = MW_MODULE_DEFAULT_G_MOL  # g/mol, typical hybrid combustion product mix
        if R_specific is None:
            R_specific = R_UNIVERSAL / molecular_weight

        # --- Prandtl number (frozen, Bartz/Sutton Eq. 8-23) ---
        prandtl = motor_data.get('prandtl', None)
        if prandtl is None:
            prandtl = 4.0 * gamma / (9.0 * gamma - 5.0)

        # --- specific heat cp ---
        gas_cp = motor_data.get('gas_cp', None)  # J/(kg*K)
        if gas_cp is None:
            # calorically-perfect frozen cp from gamma, R_specific
            gas_cp = gamma * R_specific / (gamma - 1.0)

        # --- dynamic viscosity mu [Pa*s] ---
        gas_viscosity = motor_data.get('gas_viscosity', None)
        if gas_viscosity is None:
            # Bartz 1957 viscosity correlation (SI):
            #   mu = 1.184e-7 * MW^0.5 * T^0.6   [kg/(m*s)]
            # MW in g/mol, T in K. Validated vs RocketCEA chamber transport
            # (within ~10-20% for typical 13-30 g/mol combustion gases).
            gas_viscosity = 1.184e-7 * (molecular_weight ** 0.5) * (chamber_temperature ** 0.6)

        # --- thermal conductivity k [W/(m*K)] (derived from Pr definition) ---
        gas_conductivity = motor_data.get('gas_conductivity', None)
        if gas_conductivity is None:
            # k = cp * mu / Pr  (consistent with the Prandtl number above)
            gas_conductivity = gas_cp * gas_viscosity / prandtl

        # --- optional Cantera refinement (only if a gas handle is provided) ---
        # We never silently fabricate a mechanism here; only refine if upstream
        # passed a configured Cantera Solution object set to the burned state.
        cantera_gas = motor_data.get('cantera_gas', None)
        if cantera_gas is not None:
            try:
                cp_ct = float(cantera_gas.cp_mass)           # J/(kg*K)
                mu_ct = float(cantera_gas.viscosity)         # Pa*s
                k_ct = float(cantera_gas.thermal_conductivity)  # W/(m*K)
                if cp_ct > 0 and mu_ct > 0 and k_ct > 0:
                    gas_cp = cp_ct
                    gas_viscosity = mu_ct
                    gas_conductivity = k_ct
                    prandtl = cp_ct * mu_ct / k_ct
            except Exception:
                # fall back silently to the analytic estimates above
                pass

        return {
            'gamma': gamma,
            # ÖH D21 / P4B1-16 + B3-13(c): γ'nın GELDİĞİ alan. 'gamma' |
            # 'gamma_avg (...)' | 'repo_default'. Bant dışı bir γ buraya
            # hiç ulaşamaz (yukarıda reddedilir), yani bu künye asla
            # "kelepçelenmiş" bir sayıyı örtmez.
            'gamma_source': gamma_source,
            'molecular_weight': molecular_weight,
            'gas_constant': R_specific,
            'gas_cp': gas_cp,
            'gas_viscosity': gas_viscosity,
            'gas_conductivity': gas_conductivity,
            'prandtl': prandtl,
        }

    # ------------------------------------------------------------------
    # Gaz radyasyonu: Leckner (1972) toplam emisivite / absorptivite
    # ------------------------------------------------------------------
    # Eski model gazı kara cisim sayıyordu (q_rad = eps_w*sigma*(Taw^4-Tw^4)),
    # bu roket haznesi ölçeğinde radyasyonu ~2-6x abartır. Yanma gazı GRİ
    # değil seçici ışıyandır: yalnız H2O ve CO2 bantları önemlidir ve
    # eps_g optik derinliğe (p_i*L) bağlıdır. Aşağıdaki model:
    #   eps_g = eps_H2O + eps_CO2 - delta_eps   (bant örtüşme düzeltmesi)
    # Kaynaklar:
    #   - B. Leckner, "Spectral and total emissivity of water vapor and
    #     carbon dioxide", Combustion and Flame 19(1):33-48, 1972.
    #   - M.F. Modest, "Radiative Heat Transfer", 3rd ed., Academic Press,
    #     Table 10.4 (katsayılar), Eq. (10.140)-(10.145) (basınç ve örtüşme
    #     düzeltmeleri), Eq. (10.146) (absorptivite ölçekleme kuralı).
    #   - Cengel & Ghajar, "Heat and Mass Transfer", 5th ed., Bl. 13-5
    #     (duvar etkin emisivitesi (eps_w+1)/2 yaklaşımı, eps_w > 0.7 için).

    def _species_emissivity(self, species: str, T_g: float, p_total_bar: float,
                            p_partial_bar: float, path_length_cm: float) -> float:
        """
        Tek ışıyan tür (H2O veya CO2) toplam emisivitesi — Leckner (1972).

        eps_0 (1 bar referans) Modest Table 10.4 katsayı matrisiyle,
        basınç düzeltmesi (eps/eps_0) aynı tablonun P_E / (p_a L)_m / A / B / c
        parametreleriyle hesaplanır. Korelasyon fit aralığı dışına taşma
        modül sabitlerindeki kelepçelerle önlenir.

        GEÇERLİLİK (F115): Leckner'in bildirilen fit aralığı ~300-2500 K
        (_LECKNER_T_LITERATURE_MAX). Roket haznesi sıcaklıkları bunun
        üstündedir; _LECKNER_T_MAX = 3000 K bilinçli ve muhafazakâr yönde
        bir ekstrapolasyon kelepçesidir (gerekçe modül sabitlerinde).
        """
        pal = p_partial_bar * path_length_cm  # bar*cm optik derinlik
        if pal < _LECKNER_PAL_MIN:
            return 0.0  # tür yok ya da optik olarak ihmal edilebilir ince
        pal = min(pal, _LECKNER_PAL_MAX)

        T = min(max(T_g, _LECKNER_T_MIN), _LECKNER_T_MAX)
        t = T / _LECKNER_T0
        x = np.log10(pal)

        # eps_0 = exp(sum_i a_i(t) x^i), a_i(t) = sum_j C[i][j] t^j
        if species == 'h2o':
            coeffs = _LECKNER_H2O
        elif species == 'co2':
            coeffs = _LECKNER_CO2
        else:
            raise ValueError(f"Bilinmeyen ışıyan tür: {species}")
        ln_eps0 = 0.0
        for i, row in enumerate(coeffs):
            a_i = sum(c * t ** j for j, c in enumerate(row))
            ln_eps0 += a_i * x ** i
        eps0 = float(np.exp(ln_eps0))

        # Basınç düzeltmesi (Modest Eq. 10.140-10.143, Table 10.4):
        #   eps/eps_0 = 1 - (A-1)(1-P_E)/(A+B-1+P_E)
        #               * exp(-c*(log10((p_a L)_m/(p_a L)))^2)
        # Payda +P_E: -P_E formu P_E ~ A+B-1 (~2 bar) noktasında kutup
        # üretir ve roket haznesi basınçları tam o bölgeden geçer; +P_E
        # kutupsuzdur ve yüksek basınçta eps/eps_0 > 1 verir (çizgi
        # genişlemesi fiziğiyle tutarlı; codex GPT-5.5 çapraz teyitli).
        # ÖH KU H-14 (YANMA Y2): +P_E paydası kaynaktan SAPMA değildir —
        # Howell çevrimiçi ekleri Denk. A.5/A.6'daki Λ biçimi cebirsel olarak
        # aynı +P_E paydasını verir. Modest 3. bs. sayfasının −P_E basıp
        # basmadığı bu depoda sayfa düzeyinde doğrulanmadı.
        if species == 'h2o':
            P_E = p_total_bar + 2.56 * p_partial_bar / np.sqrt(t)
            pal_m = 13.2 * t ** 2
            # Leckner H2O: t < 0.75 için A sabit 2.144 (Modest Table 10.4).
            # Hazne gazında t ~ 3 olduğundan etkisiz; absorptivite duvar
            # sıcaklığında (t ~ 0.6-1.1) değerlendirildiği için orada önemli.
            A = 2.144 if t < 0.75 else 1.888 - 2.053 * np.log10(t)
            B = 1.10 * t ** (-1.4)
            c_damp = 0.5
        else:  # co2
            P_E = p_total_bar + 0.28 * p_partial_bar
            pal_m = 0.054 / t ** 2 if t < 0.7 else 0.225 * t ** 2
            A = 1.0 + 0.1 * t ** (-1.45)
            B = 0.23
            c_damp = 1.47

        denom = A + B - 1.0 + P_E
        if abs(denom) < 1e-6:
            factor = 1.0  # savunmacı bekçi (P_E >= 0 iken erişilmez)
        else:
            factor = 1.0 - ((A - 1.0) * (1.0 - P_E) / denom) * np.exp(
                -c_damp * (np.log10(pal_m / pal)) ** 2
            )
        # Fit aralığı dışındaki uçlarda düzeltme patlamasın: Leckner
        # çizelgelerinde basınç düzeltmesi ~0.3x-2x bandında kalır.
        factor = min(max(factor, 0.3), 2.0)

        return float(min(max(eps0 * factor, 0.0), 0.995))

    def _gas_emissivity(self, T_g: float, p_total_bar: float, beam_length_m: float,
                        x_H2O: float = DEFAULT_X_H2O,
                        x_CO2: float = DEFAULT_X_CO2) -> float:
        """
        Toplam yanma gazı emisivitesi eps_g(T_g, p, L) — Leckner (1972).

            eps_g = eps_H2O + eps_CO2 - delta_eps

        delta_eps: H2O/CO2 bant örtüşme düzeltmesi (Leckner; Modest Eq. 10.145):
            zeta = p_w/(p_w+p_c)
            delta_eps = (zeta/(10.7+101*zeta) - 0.0089*zeta^10.4)
                        * (log10((p_w+p_c)*L))^2.76
        Formül T >= 1000 K bandı için verilmiştir; daha düşük sıcaklıklarda
        (absorptivite değerlendirmesinde duvar sıcaklığı) aynı ifade küçük
        değerler ürettiğinden mühendislik yaklaşımı olarak korunur.

        Args:
            T_g: Gaz (statik) sıcaklığı [K].
            p_total_bar: Toplam basınç [bar].
            beam_length_m: Ortalama ışın uzunluğu L [m]
                (silindirik hazne için L = 0.9*D, modül sabiti).
            x_H2O, x_CO2: Işıyan tür mol kesirleri. Varsayılanlar hidrokarbon
                yakıt + N2O/LOX yanması denge kompozisyonunun tipik bandı
                (modül sabitleri DEFAULT_X_H2O/DEFAULT_X_CO2, gerekçe orada).

        Returns:
            eps_g in [0, 0.995].
        """
        L_cm = max(beam_length_m, 0.0) * 100.0
        p_w = max(x_H2O, 0.0) * p_total_bar
        p_c = max(x_CO2, 0.0) * p_total_bar

        eps_w = self._species_emissivity('h2o', T_g, p_total_bar, p_w, L_cm)
        eps_c = self._species_emissivity('co2', T_g, p_total_bar, p_c, L_cm)

        delta_eps = self._band_overlap_correction(p_w, p_c, L_cm, eps_w, eps_c)

        return float(min(max(eps_w + eps_c - delta_eps, 0.0), 0.995))

    @staticmethod
    def _band_overlap_correction(p_w: float, p_c: float, L_cm: float,
                                 term_w: float, term_c: float) -> float:
        """H2O/CO2 bant örtüşme düzeltmesi delta (Leckner; Modest Eq. 10.145).

            zeta = p_w/(p_w+p_c)
            delta = (zeta/(10.7+101*zeta) - 0.0089*zeta^10.4)
                    * (log10((p_w+p_c)*L))^2.76

        TEK KAYNAK (v2.6.2): aynı düzeltme hem emisivitede hem absorptivitede
        kullanılır; daha önce absorptivite yolu _gas_emissivity'yi çağırdığı
        için düzeltmeyi dolaylı alıyordu. Tür-bazlı absorptivite üsleri
        (F111) ayrıştırılınca ortak yardımcıya çıkarıldı — parametre
        tutarlılığı kuralı (aynı sayı iki yerde ayrı yazılmaz).

        Yalnız iki tür de mevcutken ve toplam optik derinlik > 1 bar*cm iken
        anlamlıdır (log10 tabanı; altında negatif tabanın kesirli kuvveti
        tanımsız olur, örtüşme zaten ~0).
        """
        if term_w <= 0.0 or term_c <= 0.0:
            return 0.0
        pal_sum = (p_w + p_c) * L_cm
        if pal_sum <= 1.0:
            return 0.0
        zeta = p_w / (p_w + p_c)
        delta = (
            zeta / (10.7 + 101.0 * zeta) - 0.0089 * zeta ** 10.4
        ) * np.log10(pal_sum) ** 2.76
        return float(min(max(delta, 0.0), term_w + term_c))

    def _gas_absorptivity(self, T_g: float, T_w: float, p_total_bar: float,
                          beam_length_m: float,
                          x_H2O: float = DEFAULT_X_H2O,
                          x_CO2: float = DEFAULT_X_CO2) -> float:
        """
        Gazın duvar ışınımına karşı absorptivitesi — Hottel/Leckner ölçekleme
        kuralı (Modest, Radiative Heat Transfer, Eq. 10.146):

            alpha_H2O = (T_g/T_w)^0.50 * eps_H2O(T_w, p_w*L*(T_w/T_g))
            alpha_CO2 = (T_g/T_w)^0.65 * eps_CO2(T_w, p_c*L*(T_w/T_g))
            alpha_g   = alpha_H2O + alpha_CO2 - delta(T_w)

        DÜZELTME (v2.6.2, fizik denetimi F111): üs TÜRE GÖRE farklıdır —
        H2O için 0.50, CO2 için 0.65. Eski kod karışımın TAMAMINA 0.50
        uyguluyordu, yani CO2 payının absorptivitesi (T_g/T_w)^0.15 kadar
        eksik hesaplanıyordu (T_g/T_w = 3500/800 için %24). Sayısal etkisi
        küçüktür (alpha yalnız T_w^4 ile çarpılır; q_rad'da <%0.2), ama
        korelasyonun kaynakla birebir olması için düzeltildi.

        Emisiviteler duvar sıcaklığında, optik derinlik T_w/T_g ile
        ölçeklenmiş yol üzerinden değerlendirilir.
        """
        T_g_eff = max(T_g, 1.0)
        T_w_eff = max(T_w, _LECKNER_T_MIN)  # korelasyon alt sınırı
        scale = T_w_eff / T_g_eff
        L_cm = max(beam_length_m, 0.0) * 100.0 * scale
        p_w = max(x_H2O, 0.0) * p_total_bar
        p_c = max(x_CO2, 0.0) * p_total_bar

        ratio = T_g_eff / T_w_eff
        alpha_w = ratio ** 0.50 * self._species_emissivity(
            'h2o', T_w_eff, p_total_bar, p_w, L_cm)
        alpha_c = ratio ** 0.65 * self._species_emissivity(
            'co2', T_w_eff, p_total_bar, p_c, L_cm)

        delta_alpha = self._band_overlap_correction(
            p_w, p_c, L_cm, alpha_w, alpha_c)

        return float(min(max(alpha_w + alpha_c - delta_alpha, 0.0), 0.995))

    def _gas_radiation_flux(self, T_g: float, T_w: float, p_total_bar: float,
                            beam_length_m: float,
                            x_H2O: float = DEFAULT_X_H2O,
                            x_CO2: float = DEFAULT_X_CO2,
                            wall_emissivity: float = 0.8) -> float:
        """
        Gaz-duvar net radyatif ısı akısı [W/m^2]:

            q_rad = sigma * (eps_w+1)/2 * (eps_g*T_g^4 - alpha_g*T_w^4)

        (eps_w+1)/2 etkin duvar emisivitesi, gri duvar (eps_w > ~0.7) ile
        izotermal gaz arasındaki alışveriş için standart mühendislik
        yaklaşımıdır (Hottel; Cengel & Ghajar Bl. 13-5). Eski kara cisim
        modeline göre q_rad DÜŞER — beklenen fiziksel davranış budur
        (roket haznesinde radyasyon toplam akının tipik %5-30'u).
        """
        eps_g = self._gas_emissivity(T_g, p_total_bar, beam_length_m, x_H2O, x_CO2)
        alpha_g = self._gas_absorptivity(T_g, T_w, p_total_bar, beam_length_m,
                                         x_H2O, x_CO2)
        eps_wall_eff = 0.5 * (min(max(wall_emissivity, 0.0), 1.0) + 1.0)
        T_w_pos = max(T_w, 0.0)
        return float(
            eps_wall_eff * self.stefan_boltzmann
            * (eps_g * T_g ** 4 - alpha_g * T_w_pos ** 4)
        )

    # ------------------------------------------------------------------
    # Throat conditions (replaces throat_flux = chamber*1.5 hardcode)
    # ------------------------------------------------------------------
    def _resolve_throat_conditions(self, motor_data: Dict, chamber_pressure: float,
                                   chamber_temperature: float, gas: Dict,
                                   mdot_total: float) -> Dict:
        """
        Compute real throat geometry and stagnation->throat conditions.

        c* (characteristic velocity) from theory if not provided:
            c* = sqrt(gamma * R * Tc) / ( gamma * sqrt( (2/(gamma+1))^((gamma+1)/(gamma-1)) ) )
            (Sutton & Biblarz Eq. 3-32)
        Throat area from continuity at the choked throat if not provided:
            A_t = mdot * c* / Pc          (definition of c*: Pc*A_t = mdot*c*)
        Throat temperature (static) for sigma correction:
            T_t = Tc / (1 + (gamma-1)/2)   (M=1)
        """
        gamma = gas['gamma']
        R = gas['gas_constant']

        # ÖLÇÜ SÖZLEŞMESİ (v2.6.27): 0 / '' / sonsuz bir ölçü DEĞİLDİR,
        # "verilmedi" demektir. Eskiden yalnız ``is not None`` bakılıyordu;
        # throat_diameter=0 taşıyan bir sözlük A_t=0 üretip birkaç satır
        # aşağıda ZeroDivisionError'a düşüyordu (eksenel profil bekçisiyle
        # yakalandı). Sıfırı geçerli sanmak sessiz sıfır yarıçap demektir.
        # characteristic velocity c* [m/s]
        c_star = _positive_length(
            motor_data.get('c_star', motor_data.get('cstar', None)))
        # ÖH D15 / P4B2-08 — c*'IN KAYNAĞI ARTIK KÜNYELİ.
        # ``motor_data['c_star']`` sessizce Bartz akısını değiştiriyordu ve
        # hiçbir tüketici bunu öğrenemiyordu (ölçüldü: NozzleFlow1D'de
        # h_g(boğaz) 15 782,5 -> 16 148,1 W/m²K, +%2,32; RegenCooling'de
        # tepe akı 40,440 -> 41,191 MW/m² ve max_wall_hot_K 882,31 ->
        # 890,47 K, +8,16 K). Kaynak alanı burada üretilir; tüketiciler
        # (nozzle_flow_1d kapısı, regen_cooling özeti) onu okur.
        c_star_source = 'user_supplied'
        c_star_ideal = None
        if c_star is None:
            num = np.sqrt(gamma * R * chamber_temperature)
            den = gamma * np.sqrt((2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0)))
            c_star = num / den
            c_star_source = 'ideal_theory'
            c_star_ideal = float(c_star)
        else:
            num = np.sqrt(gamma * R * chamber_temperature)
            den = gamma * np.sqrt((2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0)))
            c_star_ideal = float(num / den)

        # throat diameter [m]
        throat_diameter = _positive_length(motor_data.get('throat_diameter'))
        throat_area = _positive_length(motor_data.get('throat_area'))
        # ÖH D21 / P4B1-17 — BİRLİKTE VERİLEN ÇAP+ALAN ARTIK SESSİZCE
        # ÇÖZÜLMÜYOR. Eski kod ``if throat_diameter is not None`` diyerek
        # alanı KOŞULSUZ olarak π(d/2)² ile yeniden yazıyordu; çağıranın
        # gönderdiği ``throat_area`` okunmadan atılıyor ve bunu söyleyen
        # tek bir künye üretilmiyordu. Bugün ürün yolunda etkisi yok
        # (hibrit motor geometrik A_t gönderiyor, ikisi tutarlı), ama
        # boşaltma katsayısı düzeltilmiş ETKİN alan gönderen her çağıranda
        # sayı %2,08 sessizce kayıyordu (once.json K2).
        throat_scale_source = None
        if throat_diameter is not None and throat_area is not None:
            _a_geo = float(np.pi * (throat_diameter / 2.0) ** 2)
            _bagil = abs(float(throat_area) - _a_geo) / _a_geo
            if _bagil > THROAT_AREA_CONSISTENCY_REL_TOL:
                raise ConflictingHeatTransferInput(
                    ['throat_diameter', 'throat_area'],
                    detail=(
                        'throat_diameter=%.6g m implies a geometric throat '
                        'area of %.6g m2, but throat_area=%.6g m2 was also '
                        'supplied (relative difference %.4g%%, tolerance '
                        '%.0e). A discharge-coefficient corrected EFFECTIVE '
                        'area and the geometric area are two different '
                        'measurements and the Bartz mass flux scales with '
                        'whichever one is used.'
                        % (throat_diameter, _a_geo, float(throat_area),
                           _bagil * 100.0,
                           THROAT_AREA_CONSISTENCY_REL_TOL)))
            throat_area = _a_geo
            throat_scale_source = (
                'throat_diameter (throat_area supplied too and agreed '
                'within %.0e relative)' % THROAT_AREA_CONSISTENCY_REL_TOL)
        elif throat_diameter is not None:
            throat_area = np.pi * (throat_diameter / 2.0) ** 2
            throat_scale_source = 'throat_diameter'
        elif throat_area is not None:
            throat_diameter = 2.0 * np.sqrt(throat_area / np.pi)
            throat_scale_source = 'throat_area'
        else:
            # A_t = mdot * c* / Pc  (continuity at choked throat)
            if mdot_total > 0 and chamber_pressure > 0:
                throat_area = mdot_total * c_star / chamber_pressure
            else:
                # --- BAŞPARMAK KURALI KALDIRILDI (ÖH D15, P4B1-09) --------
                # Burada ``A_t = pi*(0,3*D_ch/2)^2`` duruyordu; üstelik
                # ``chamber_diameter`` da yoksa İKİNCİ bir uydurmayla
                # (``0,1`` m) tamamlanıyordu. Modülün KENDİ girdi kapısı
                # (bu dosyanın :166-172 beyanı) tam bu kuralı adıyla anıp
                # "kaynaksız bir 0,3 katsayısıyla boğaz uydurmak YASAK"
                # diyordu — beyan yazılmış, tel çekilmemişti.
                #
                # ÖLÇÜLDÜ (31 Ağustos 2026, Python API):
                #   analyze_axial_profile({'chamber_pressure':60,
                #       'chamber_temperature':3400,'mdot_total':0})
                #       -> throat_diameter_m = 0,03   (= 0,3 * 0,1)
                #   aynı gövde + chamber_diameter=0,5 -> 0,15
                # Boğaz çapı bütün profili (Bartz kütle akısı, q(x), h_g,
                # T_wall) belirler; uydurma boğaz uydurma bir termal hüküm
                # demektir. Sayı üretilmez, eksik alan ADIYLA söylenir.
                raise MissingHeatTransferInput([
                    'throat_diameter or throat_area or mdot_total (with a '
                    'positive chamber_pressure) — the throat scale cannot be '
                    'resolved and is NOT approximated from the chamber '
                    'diameter'])
            throat_diameter = 2.0 * np.sqrt(throat_area / np.pi)
            throat_scale_source = (
                'mdot_total * c_star / chamber_pressure (continuity at the '
                'choked throat)')

        # throat radius of curvature (for the (Dt/Rc)^0.1 term).
        # Typical converging-diverging nozzles: Rc ~ 0.5..2 * throat radius.
        # Use Rc = 1.5 * throat_radius if not provided (common Bartz assumption).
        throat_radius = throat_diameter / 2.0
        rc = _positive_length(motor_data.get('throat_radius_curvature'))
        if rc is None:
            rc = 1.5 * throat_radius
        rc_over_dt = max(rc / throat_diameter, 0.25)  # keep correction bounded

        # static throat temperature (M=1)
        throat_temperature = chamber_temperature / (1.0 + (gamma - 1.0) / 2.0)

        return {
            'c_star': c_star,
            # ÖH D15 / P4B2-08: 'user_supplied' -> yukarıdaki sayı
            # motor_data['c_star'] (ya da 'cstar') alanından geldi;
            # 'ideal_theory' -> Sutton & Biblarz Eq. 3-32 ile gamma, R ve
            # T_c'den türetildi. ``c_star_ideal`` her iki hâlde de analitik
            # değerdir (kıyas/kapı için).
            'c_star_source': c_star_source,
            'c_star_ideal': c_star_ideal,
            'throat_diameter': throat_diameter,
            'throat_area': throat_area,
            # ÖH D21 / P4B1-17: boğaz ÖLÇEĞİNİN geldiği alan. Üç değer
            # alır: 'throat_diameter' | 'throat_area' | continuity
            # ifadesi. Çap+alan birlikte gelip UYUŞMAZLARSA buraya hiç
            # ulaşılmaz (ConflictingHeatTransferInput atılır).
            'throat_scale_source': throat_scale_source,
            'throat_radius_curvature': rc,
            'rc_over_dt': rc_over_dt,
            'throat_temperature': throat_temperature,
        }

    # ------------------------------------------------------------------
    # Bartz gas-side coefficient
    # ------------------------------------------------------------------
    def _bartz_coefficient(self, throat_diameter: float, chamber_pressure: float,
                           c_star: float, gas: Dict, chamber_temperature: float,
                           wall_temperature: float, rc_over_dt: float,
                           area_ratio_local: float = 1.0, mach_local: float = 1.0) -> float:
        """
        Bartz convective heat-transfer coefficient (SI-consistent, no g0).

        Bartz closed form, Bartz (1965) Eq. (50) with the property factor
        of Eq. (49) (NTRS 19650013685; first published Bartz 1957, Jet
        Propulsion 27(1):49-51), SI form. Sutton & Biblarz 9th ed. Eq. 8-22
        (p. 313) is the algebraically equivalent property-ratio form
        (= Bartz Eq. 48) without the curvature term:

          h_g = (0.026 / D_t^0.2)
                * (mu^0.2 * cp / Pr^0.6)
                * (Pc / c*)^0.8
                * (D_t / R_c)^0.1
                * (A_t / A)^0.9
                * sigma

        with the boundary-layer property correction (Bartz 1965 Eq. 49; the
        closed form of the Sutton Eq. 8-22 property ratios for mu ~ T^0.6):

          sigma = 1 / { [ 0.5*(Tw/Tc)*(1 + (g-1)/2 * M^2) + 0.5 ]^0.68
                        * [ 1 + (g-1)/2 * M^2 ]^0.12 }

        Returns h_g in W/(m^2*K).  area_ratio_local = A_t/A (=1 at throat).
        """
        mu = gas['gas_viscosity']
        cp = gas['gas_cp']
        Pr = gas['prandtl']
        gamma = gas['gamma']

        # boundary-layer correction factor sigma
        m2 = 1.0 + (gamma - 1.0) / 2.0 * mach_local ** 2
        t_ratio = wall_temperature / chamber_temperature
        sigma = 1.0 / ((0.5 * t_ratio * m2 + 0.5) ** 0.68 * m2 ** 0.12)

        # NO g0 in SI: Pc/c* already has units kg/(m^2*s).
        mass_flux_term = (chamber_pressure / c_star) ** 0.8
        prop_term = (mu ** 0.2) * cp / (Pr ** 0.6)
        curvature_term = (1.0 / rc_over_dt) ** 0.1  # (D_t / R_c)^0.1
        area_term = area_ratio_local ** 0.9

        h_g = (0.026 / throat_diameter ** 0.2) * prop_term * mass_flux_term \
            * curvature_term * area_term * sigma
        return h_g

    def _adiabatic_wall_temperature(self, chamber_temperature: float, gas: Dict,
                                    mach_local: float = 1.0) -> float:
        """
        Adiabatic (recovery) wall temperature — the correct driving temperature
        for q = h_g*(Taw - Tw), NOT the stagnation temperature.

          Taw = Tc * (1 + r*(g-1)/2 * M^2) / (1 + (g-1)/2 * M^2)
          r   = Pr^(1/3)  (turbulent recovery factor; Sutton & Biblarz)
        """
        gamma = gas['gamma']
        Pr = gas['prandtl']
        r = Pr ** (1.0 / 3.0)
        m2 = (gamma - 1.0) / 2.0 * mach_local ** 2
        return chamber_temperature * (1.0 + r * m2) / (1.0 + m2)

    # ==================================================================
    # TASARIM AKISI — TEK TANIM NOKTASI (ÖH Z5S / PK5, P4B1-03)
    # ------------------------------------------------------------------
    # ÖLÇÜLEN KUSUR: aynı boğaz, aynı koşu, İKİ tasarım akısı ve İKİ h_g.
    # ``analyze_heat_transfer`` gaz-yanı katsayıyı wall_guess =
    # min(0,5·Tc, max_service·0,8) cidarında kuruyordu, ``analyze_axial_
    # profile`` ise referans soğutulmuş cidar Tw_ref'te; radyasyon terimi de
    # birinde HAZNE durgunluk koşullarında + hazne çapıyla, ötekinde YEREL
    # statik durumda + yerel çapla hesaplanıyordu. Sapma (test fikstürü):
    # h_g %10,26 (8.105,45 ⟷ 8.937,40 W/m²K), akı %7,03. İki değer İKİ AYRI
    # tüketiciye gidiyordu (PDF + 3B görselleştirme ⟷ /api/analysis/
    # wall-profile → termal FEA). Modülün kendi künyesi ise (analyze_axial_
    # profile docstring'i) "throat-analiziyle AYNI korelasyon ve gaz
    # özellikleri" diyordu.
    #
    # ONARIM: referans cidar sıcaklığı ve tasarım akısı artık AŞAĞIDAKİ İKİ
    # işlevden çıkar; her iki kanal da (ve hazne bacağı da) bunları çağırır.
    # Hangi kanalın "doğru" olduğuna karar verilmedi — YEREL statik durum
    # seçildi, çünkü radyasyonu yayan gaz o istasyondaki gazdır ve boğaz
    # akısının adı "throat_heat_flux"tır.
    # ==================================================================
    @staticmethod
    def _design_reference_wall_temperature(allowable: float, taw: float,
                                           ambient_temp: float) -> float:
        """Tasarım akısının referans SOĞUTULMUŞ cidar sıcaklığı [K].

        Malzemenin izin verilen sıcaklığı, ama Taw'ın ~%80'inden sıcak
        değil (iyi soğutulmuş cidar her zaman Taw'ın altındadır) ve ortam
        sıcaklığından soğuk değil. Daha DÜŞÜK referans cidar => daha
        YÜKSEK (muhafazakâr) akı; bu yüzden akı sıfıra çökemez ve
        yanma-delinme maskelenemez.
        """
        return max(min(float(allowable), 0.8 * float(taw)),
                   float(ambient_temp))

    def _design_heat_flux(self, *, h_gas: float, taw: float, t_wall: float,
                          chamber_temperature: float, chamber_pressure: float,
                          gamma: float, local_diameter: float,
                          emissivity: float, x_H2O: float, x_CO2: float,
                          mach_local: float) -> float:
        """Tasarım ısı akısı q = q_taşınım + q_radyasyon [W/m²].

        Radyasyon Leckner (1972) gaz emisivitesiyle YEREL STATİK durumda
        hesaplanır (T_stat, p_stat izantropik bağıntıdan; ışın uzunluğu
        yerel çaptan). Boğazda ``mach_local=1``, hazne gövdesinde
        ``mach_local`` düşük, eksenel profilde istasyonun kendi Mach'ı.

        Args:
            h_gas: O istasyonun Bartz katsayısı [W/m²K].
            taw: Kurtarma (adyabatik cidar) sıcaklığı [K].
            t_wall: Akının değerlendirildiği cidar sıcaklığı [K].
            chamber_temperature / chamber_pressure: Durgunluk koşulları
                (K / Pa).
            local_diameter: Ortalama ışın uzunluğunun türetildiği yerel çap [m].
        """
        m2 = 0.5 * (gamma - 1.0) * mach_local * mach_local
        t_static = chamber_temperature / (1.0 + m2)
        p_static_bar = (chamber_pressure / 1e5) * (1.0 + m2) ** (
            -gamma / (gamma - 1.0))
        beam_length = MEAN_BEAM_LENGTH_FACTOR * float(local_diameter)
        q_conv = h_gas * (taw - t_wall)
        q_rad = self._gas_radiation_flux(
            t_static, t_wall, p_static_bar, beam_length,
            x_H2O=x_H2O, x_CO2=x_CO2, wall_emissivity=emissivity)
        return q_conv + max(q_rad, 0.0)

    def _coolant_side_coefficient(self, motor_data: Dict, cooling_type: str,
                                  coolant_bulk_temp: Optional[float] = None
                                  ) -> float:
        """
        Soğutucu tarafı film katsayısı [W/(m^2*K)] — TEK merkezi kaynak.

        Sayının KENDİSİ ve NEREDEN geldiği ``_coolant_side_resolution``
        tarafından çözülür; bu işlev yalnız değeri döndüren ince sarmaldır
        (imza korunuyor: ``regen_cooling``, ``visualization`` ve testler
        float bekliyor). Künyeyi (``method`` / ``source``) isteyen çağıran
        doğrudan ``_coolant_side_resolution`` çağırır.
        """
        return self._coolant_side_resolution(
            motor_data, cooling_type, coolant_bulk_temp=coolant_bulk_temp)['value']

    def _coolant_side_resolution(self, motor_data: Dict, cooling_type: str,
                                 coolant_bulk_temp: Optional[float] = None
                                 ) -> Dict:
        """
        Soğutucu tarafı film katsayısı [W/(m^2*K)] + KÖKEN KÜNYESİ.

        ÖH D31 / P12bB4-06 — ÖLÇÜLEN KUSUR: bu işlev soğutma rejimine göre
        ÜÇ SABİT döndürüyordu ve kanal geometrisi, soğutucu debisi, soğutucu
        kimliği sonuca HİÇ girmiyordu. Ölçüldü (``once_p12bb406.json``, taban
        9d70e9ed): dört ayrı kanal tasarımında ürün 20.000 W/m²K'de sabit
        kalırken Dittus-Boelter 6.639,7 - 77.412,6 W/m²K veriyordu (11,66x
        yayılım) ve cidar iç sıcaklığı dördünde de 1062,03 K çıkıyordu.
        ``/formulas`` §5.3 ise okuyucuya Re/Pr korelasyonu gösteriyordu.

        ÜÇ YOL, HER BİRİ KÜNYELİ (sessiz sabit YOK):

        1. ``user_supplied`` — çağıran ``motor_data['coolant_side_coefficient']``
           verdiyse o sayı aynen kullanılır.
        2. ``dittus_boelter`` — rejeneratif soğutmada kanal geometrisi
           (``n_channels``, ``channel_width``, ``channel_height``), soğutucu
           debisi (``coolant_mdot``), soğutucu kimliği (``coolant``) ve yığın
           sıcaklığı çözülebiliyorsa katsayı GERÇEKTEN hesaplanır:

               D_h = 2 w h / (w + h)            (dikdörtgen kanal)
               G   = (mdot / N) / (w h)         [kg/(m^2 s)]
               Re  = G D_h / mu,  Pr = cp mu / k
               Nu  = 0,023 Re^0,8 Pr^0,4        (soğutucu ISINIYOR: n = 0,4)
               h   = Nu k / D_h                 [W/(m^2 K)]

           Kaynak: Incropera & DeWitt, "Fundamentals of Heat and Mass
           Transfer", 6. bs., Eq. 8.60 (Dittus-Boelter); geçerlilik
           Re >= 1e4, 0,6 <= Pr <= 160, L/D >= 10, bildirilen saçılım
           yaklaşık ±%25. Korelasyon, Nusselt sayısı ve geçerlilik zarfı
           kardeş ``regen_cooling`` modülünün TEK kaynağından ithal edilir
           (``dittus_boelter_nu``, ``dittus_boelter_envelope``,
           ``hydraulic_diameter_rect``, ``water_properties``,
           ``rp1_properties``) — ikinci bir kopya yazılmaz.

           BOYUT DENETİMİ: [G D_h / mu] = (kg/m²s · m)/(kg/(m·s)) = 1;
           [cp mu / k] = (J/kgK · kg/(m·s))/(W/mK) = 1; [Nu k / D_h] =
           (W/mK)/m = W/m²K. Üçü de boyutsuz/ doğru birimde.

        3. ``not_modelled`` — yukarıdaki girdiler yoksa (ya da soğutucu
           kritik üstü metan/hidrojen ise; orada Dittus-Boelter geçersizdir,
           Jackson korelasyonu ``regen_cooling.RegenCooling`` çözücüsünde
           durur) BEYAN EDİLEN TİPİK BANT döner
           (``COOLANT_SIDE_DECLARED_TYPICAL``) ve künye bunun bir hesap
           DEĞİL kabul olduğunu, hangi alanların eksik olduğunu ADIYLA
           söyler. Sayı burada uydurulmaz: bandın kaynağı
           ``COOLANT_SIDE_DECLARED_SOURCE``ta yazılıdır.

        Döner: ``{'value': float, 'method': str, 'source': str,
        'missing_fields': [...], 'detail': {...}}``.
        """
        md = motor_data or {}

        # 1) Çağıranın verdiği değer — künyesiyle.
        h_user = md.get('coolant_side_coefficient', None)
        if h_user is not None:
            return {
                'value': float(h_user),
                'method': 'user_supplied',
                'source': 'motor_data["coolant_side_coefficient"] (caller-supplied)',
                'missing_fields': [],
                'detail': {},
            }

        # 2) Korelasyon yolu — YALNIZ rejeneratif (kanal içi zorlanmış
        #    taşınım). 'natural' / 'forced' dış yüzey taşınımıdır; kanal
        #    korelasyonu oraya uygulanmaz, uydurulmaz.
        if cooling_type == 'regenerative':
            cozum, eksik = self._coolant_side_dittus_boelter(
                md, coolant_bulk_temp)
            if cozum is not None:
                return cozum
        else:
            eksik = [
                "cooling_type='regenerative' (the duct-flow correlation "
                'applies to regenerative channels only; natural/forced '
                'convection on the outer surface is not modelled here)']

        # 3) not_modelled — beyan edilen bant, ADIYLA.
        deger = COOLANT_SIDE_DECLARED_TYPICAL.get(
            cooling_type, COOLANT_SIDE_DECLARED_TYPICAL['natural'])
        if cooling_type not in COOLANT_SIDE_DECLARED_TYPICAL:
            eksik = list(eksik) + [
                f'cooling_type={cooling_type!r} is not one of '
                f'{sorted(COOLANT_SIDE_DECLARED_TYPICAL)}; the free-convection '
                'band is reported']
        return {
            'value': float(deger),
            'method': 'not_modelled',
            'source': COOLANT_SIDE_DECLARED_SOURCE,
            'missing_fields': list(eksik),
            'detail': {},
        }

    def _coolant_side_dittus_boelter(self, md: Dict,
                                     coolant_bulk_temp: Optional[float]
                                     ) -> Tuple[Optional[Dict], List[str]]:
        """Kanal-içi Dittus-Boelter çözümü ya da EKSİK ALAN listesi.

        Döner: ``(cozum | None, eksik_alanlar)``. Bir alan eksikse, sıfır ya
        da negatifse sayı ÜRETİLMEZ — çağıran ``not_modelled`` beyan eder.
        """
        # Geç (lazy) içe aktarma: ``regen_cooling`` bu modülü modül
        # düzeyinde içe aktarır (``HeatTransferAnalyzer``, ``_guard_gamma_band``);
        # tepe düzeyinde karşılıklı içe aktarma döngü kurardı.
        from hrma.analysis.regen_cooling import (
            canonical_coolant_name, dittus_boelter_envelope, dittus_boelter_nu,
            hydraulic_diameter_rect, rp1_properties, water_properties,
        )

        eksik: List[str] = []

        def _pozitif(ad):
            ham = md.get(ad, None)
            if ham is None:
                eksik.append(ad)
                return None
            try:
                deger = float(ham)
            except (TypeError, ValueError):
                eksik.append(f'{ad} (not a number: {ham!r})')
                return None
            if not math.isfinite(deger) or deger <= 0.0:
                eksik.append(f'{ad} (must be finite and positive, got {ham!r})')
                return None
            return deger

        n_channels = _pozitif('n_channels')
        width = _pozitif('channel_width')       # m
        height = _pozitif('channel_height')     # m
        mdot = _pozitif('coolant_mdot')         # kg/s

        akiskan_ham = md.get('coolant', md.get('coolant_fluid', None))
        akiskan = (None if akiskan_ham is None
                   else canonical_coolant_name(akiskan_ham))
        if akiskan_ham is None:
            eksik.append('coolant')
        elif akiskan is None:
            eksik.append(f'coolant (unrecognised fluid {akiskan_ham!r})')
        elif akiskan not in COOLANT_SIDE_TABLE_FLUIDS:
            eksik.append(
                f'coolant={akiskan!r} is supercritical here; the Dittus-Boelter '
                'duct correlation is not valid for it. Use '
                'hrma.analysis.regen_cooling.RegenCooling (Jackson '
                'supercritical correlation) for methane/hydrogen channels.')
            akiskan = None

        # Yığın sıcaklığı: soğutucu giriş sıcaklığı (kardeş modülün adı) ya
        # da çağıranın verdiği ortam/soğutucu giriş sıcaklığı.
        t_bulk = md.get('coolant_inlet_temp', None)
        t_bulk_source = 'motor_data["coolant_inlet_temp"]'
        if t_bulk is None:
            t_bulk = coolant_bulk_temp
            t_bulk_source = 'ambient_temp argument (documented as the coolant inlet temperature)'
        if t_bulk is None:
            eksik.append('coolant_inlet_temp')
        else:
            try:
                t_bulk = float(t_bulk)
            except (TypeError, ValueError):
                eksik.append(f'coolant_inlet_temp (not a number: {t_bulk!r})')
                t_bulk = None
            if t_bulk is not None and not (math.isfinite(t_bulk) and t_bulk > 0.0):
                eksik.append('coolant_inlet_temp (must be finite and positive)')
                t_bulk = None

        if eksik or None in (n_channels, width, height, mdot, t_bulk) or akiskan is None:
            return None, eksik

        d_h = hydraulic_diameter_rect(width, height)          # m
        kanal_alani = width * height                          # m^2
        mdot_kanal = mdot / n_channels                        # kg/s
        mass_flux = mdot_kanal / kanal_alani                  # kg/(m^2 s)
        props = (water_properties(t_bulk) if akiskan == 'water'
                 else rp1_properties(t_bulk))
        reynolds = mass_flux * d_h / props['viscosity']
        prandtl = props['cp'] * props['viscosity'] / props['conductivity']
        # Soğutucu ISINIYOR (cidardan akışkana ısı) -> n = 0,4.
        nusselt = dittus_boelter_nu(reynolds, prandtl, heating=True)
        h_coolant = nusselt * props['conductivity'] / d_h     # W/(m^2 K)
        zarf = dittus_boelter_envelope(reynolds, prandtl)

        return {
            'value': float(h_coolant),
            'method': 'dittus_boelter',
            'source': ('Dittus-Boelter turbulent duct correlation, Incropera & '
                       'DeWitt 6th ed. Eq. 8.60 (Nu = 0.023 Re^0.8 Pr^0.4); '
                       'coolant transport properties from '
                       'hrma.analysis.regen_cooling tables (water: Incropera '
                       'Table A.6; RP-1: cited as a Huzel & Huang appendix '
                       'compilation - NASA SP-125 (1967) has no appendix; its '
                       'RP-1 properties are Table 1-4 (after p. 21, page '
                       'number not printed) and Table 6-3, p. 188; table '
                       'provenance not page-verified)'),
            'missing_fields': [],
            'detail': {
                'coolant': akiskan,
                'coolant_bulk_temperature_K': t_bulk,
                'coolant_bulk_temperature_source': t_bulk_source,
                'hydraulic_diameter_m': d_h,
                'channel_mass_flux_kg_m2s': mass_flux,
                'reynolds_number': reynolds,
                'prandtl_number': prandtl,
                'nusselt_number': nusselt,
                'coolant_conductivity_W_mK': props['conductivity'],
                'coolant_viscosity_Pa_s': props['viscosity'],
                'coolant_cp_J_kgK': props['cp'],
                'property_table_clamped': bool(props.get('clamped', False)),
                'envelope': zarf,
            },
        }, []

    @staticmethod
    def _mach_from_area_ratio(area_ratio: float, gamma: float,
                              supersonic: bool) -> float:
        """
        İzantropik alan-Mach bağıntısını çözer (Sutton & Biblarz Eq. 3-14):

          A/A* = (1/M) * [ (2/(g+1)) * (1 + (g-1)/2 * M^2) ]^((g+1)/(2(g-1)))

        area_ratio = A/A_t (>= 1). supersonic=False konverjan (subsonik dal),
        True diverjan (süpersonik dal) içindir; boğazda (A/A_t=1) M=1 döner.
        """
        eps = float(area_ratio)
        if eps <= 1.0 + 1e-9:
            return 1.0
        exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))

        def f(M):
            return (1.0 / M) * ((2.0 / (gamma + 1.0))
                                * (1.0 + (gamma - 1.0) / 2.0 * M * M)) ** exponent - eps

        if supersonic:
            return float(brentq(f, 1.0 + 1e-9, 100.0, xtol=1e-10, maxiter=200))
        return float(brentq(f, 1e-6, 1.0 - 1e-9, xtol=1e-12, maxiter=200))

    # ==================================================================
    # PUBLIC API (signature preserved)
    # ==================================================================
    def analyze_heat_transfer(self, motor_data: Dict, material: str = 'steel',
                            wall_thickness: float = 0.005, ambient_temp: float = 293.15,
                            cooling_type: str = 'natural') -> Dict:
        """
        Complete heat transfer analysis (Bartz-based gas side).

        Args:
            motor_data: Motor performance and geometry data.

                REQUIRED (``HEAT_TRANSFER_REQUIRED_FIELDS``, no default is
                assumed - a missing one raises ``MissingHeatTransferInput``):
                  chamber_pressure [bar], chamber_temperature [K],
                  chamber_diameter [m], chamber_length [m], burn_time [s].
                REQUIRED, one of (``HEAT_TRANSFER_THROAT_SCALE_FIELDS``):
                  mdot_total [kg/s], throat_diameter [m], throat_area [m^2]
                  - the throat area is genuinely derived from mdot and c*
                  when it is not supplied.
                Optional (used when present, otherwise physically derived
                from the required set and declared in the result):
                  gamma, molecular_weight [g/mol],
                  gas_constant [J/kg/K], gas_cp, gas_viscosity, gas_conductivity,
                  prandtl, c_star [m/s],
                  throat_radius_curvature [m], cantera_gas (Cantera Solution).
            material: Wall material key (hrma.data.materials_db: steel,
                steel_4130, ss_304, ss_316, aluminum_6061, titanium_6al4v,
                inconel_718, copper, cucrzr, ablative, graphite; aliases
                aluminum/inconel/titanium resolve to the alloy records).
            wall_thickness: Wall thickness in meters.
            ambient_temp: Ambient / coolant inlet temperature in K.
            cooling_type: 'natural', 'forced', 'regenerative'.

        Returns:
            Heat transfer analysis results (dict). Top-level keys preserved:
            heat_transfer_coefficients, gas_side_analysis, wall_analysis,
            cooling_analysis, safety_analysis, material_properties,
            design_parameters.

        Raises:
            MissingHeatTransferInput: a required input is absent, zero or
                non-finite. No partial result is published: every number in
                the result scales with the missing value, so a default would
                be a fabricated motor, not this one.
        """
        # --- GİRDİ KAPISI (F4-1) — varsayılandan hüküm üretilmez -----------
        missing = _missing_heat_transfer_inputs(motor_data)
        if missing:
            raise MissingHeatTransferInput(missing)

        # Extract motor parameters (hepsi kapıdan geçti: sonlu ve pozitif)
        chamber_pressure = float(motor_data['chamber_pressure']) * 1e5  # Pa
        chamber_temperature = float(motor_data['chamber_temperature'])  # K
        chamber_diameter = float(motor_data['chamber_diameter'])  # m
        chamber_length = float(motor_data['chamber_length'])  # m
        burn_time = float(motor_data['burn_time'])  # s
        # Boğaz ölçeği üçlüsünden biri var; mdot yoksa A_t doğrudan
        # verilmiştir ve _resolve_throat_conditions onu kullanır.
        mdot_total = _positive_length(motor_data.get('mdot_total')) or 0.0  # kg/s

        # --- MALZEME KİMLİĞİ (ÖH Z5S / S4) -------------------------------
        # Eskiden burada ham sözlük araması vardı ve çözülemeyen her ad
        # SESSİZCE ``self.materials['steel']``e (A36 jenerik çelik)
        # düşüyordu. Gerekçe ve ölçüm: ``UnresolvedMaterial`` docstring'i.
        # Anahtar KANONİKLEŞTİRİLİR; ``design_parameters.material`` artık
        # hesabın GERÇEKTEN kullandığı adı yazar, isteğin yankısını değil.
        material_requested = material
        material = resolve_material_key(material)
        mat_props = self.materials[material]

        # Resolve gas properties + throat conditions (no hardcoding)
        gas = self._get_gas_properties(motor_data, chamber_temperature)
        throat = self._resolve_throat_conditions(
            motor_data, chamber_pressure, chamber_temperature, gas, mdot_total
        )

        # Calculate heat transfer coefficients (Bartz gas side)
        heat_transfer_coeffs = self._calculate_heat_transfer_coefficients(
            motor_data, mat_props, cooling_type, gas, throat,
            chamber_pressure, chamber_temperature, ambient_temp=ambient_temp
        )

        # Işıyan tür kesirleri KÖKENİYLE birlikte çözülür (tek tanım
        # noktası ``resolve_radiation_composition``) — eksenel profille AYNI
        # okuma (P4B1-03) ve AYNI köken kuralı (P4B1-10 ŞARTı).
        x_h2o_frac, x_co2_frac, _komp_koken = resolve_radiation_composition(
            motor_data)

        # Gas-side heat transfer (with energy-balance wall temperature)
        gas_side_analysis = self._analyze_gas_side_heat_transfer(
            chamber_pressure, chamber_temperature, chamber_diameter, chamber_length,
            mdot_total, heat_transfer_coeffs, gas, throat, mat_props,
            wall_thickness, ambient_temp,
            x_H2O=x_h2o_frac, x_CO2=x_co2_frac,
            composition_source=_komp_koken
        )

        # F038: toplam ısı yükünü gerçek ıslak yüzey integraliyle değiştir
        # (silindirik gövde + konverjan + boğaz + diverjan). Ayrıntılı
        # gerekçe _apply_wetted_heat_load docstring'inde.
        self._apply_wetted_heat_load(
            gas_side_analysis, motor_data, material, wall_thickness,
            ambient_temp, cooling_type
        )

        # Wall temperature distribution (uses the energy-balance flux)
        wall_analysis = self._analyze_wall_temperature(
            gas_side_analysis['heat_flux'], wall_thickness, mat_props,
            ambient_temp, heat_transfer_coeffs['coolant_side'],
            chamber_temperature, gas_side_analysis
        )

        # Cooling requirements
        cooling_analysis = self._analyze_cooling_requirements(
            gas_side_analysis['total_heat_rate'], burn_time, motor_data,
            cooling_type, mat_props, ambient_temp=ambient_temp
        )

        # Safety analysis — thermal stress from the ACTUAL through-wall
        # gradient of the wall analysis (v2.5.2), not from a hot-face rise.
        wall_gradient = (wall_analysis['inner_temperature']
                         - wall_analysis['outer_temperature'])
        # ÖH P4B1-15: hazne yarıçapı da geçirilir — basınç argümanı artık
        # gerçekten tüketilir (çember gerilmesi sigma = p*r/t).
        safety_analysis = self._analyze_thermal_safety(
            wall_analysis['max_temperature'], mat_props, wall_thickness,
            chamber_pressure, wall_delta_T=wall_gradient,
            chamber_radius_m=(chamber_diameter / 2.0
                              if chamber_diameter else None)
        )
        # Surface energy-balance + wall-clamp warnings.
        safety_analysis['warnings'] = (
            list(safety_analysis.get('warnings', []))
            + gas_side_analysis.get('warnings', [])
            + wall_analysis.get('warnings', [])
        )

        return {
            'heat_transfer_coefficients': heat_transfer_coeffs,
            'gas_side_analysis': gas_side_analysis,
            'wall_analysis': wall_analysis,
            'cooling_analysis': cooling_analysis,
            'safety_analysis': safety_analysis,
            # ÖH D37 A2-1 / F-01 (CW-B3): İKİ TERMAL YOL, İKİ SORU — sözleşme
            # dalga_plani.md A2-1 (faz-c-1 tüketir). Bu zincir yalnız DENGE
            # yarısını doldurur; FEA yarısı /api/fea/thermal koşunca köprü
            # AYNI blok şemasıyla doldurur (fea.thermal_paths_reconciliation)
            # ve gap_K orada ölçülür. Burada FEA alanları None'dır:
            # koşulmamış bir analizin sayısı UYDURULMAZ (fail-closed).
            'thermal_paths_reconciliation': thermal_paths_reconciliation(
                equilibrium_K=wall_analysis['max_temperature'],
                burn_time_s=burn_time, mat_props=mat_props,
                cooling_type=cooling_type,
                coolant_side_h=heat_transfer_coeffs.get('coolant_side')),
            # v2.6.26 — AD CAKISMASI BEYAN EDILIYOR.
            # mat_props['safety_factor'] materials_db'nin bu malzeme icin
            # ONERDIGI tasarim katsayisidir (celik 4,0; inconel 3,0).
            # Kullanicinin girdigi tasarim emniyet katsayisi DEGILDIR ama
            # ayni adi tasiyor: kullanici SF=6 girip bu alanda 4,0 gorunce
            # 'girdim yutuldu' diye okuyor. Deger dogru, sunum yaniltici.
            'material_properties': published_material_record(mat_props),
            'design_parameters': {
                # ÖH Z5S / S4: hesabın GERÇEKTEN kullandığı kanonik anahtar.
                # Eskiden burada isteğin ham yankısı vardı ve yanıt
                # ``material: 'peynir'`` yazarken ``material_properties.name``
                # A36 çeliğini gösteriyordu (tek yanıtta iki malzeme).
                'material': material,
                # İstenen ad kanonik anahtardan FARKLIYSA (harf büyüklüğü ya
                # da takma ad) söylenir; aynıysa alan hiç konmaz, yani
                # sağlıklı yolun gövdesi bit-aynı kalır.
                **({'material_requested': material_requested}
                   if str(material_requested) != material else {}),
                'wall_thickness': wall_thickness * 1000,  # mm
                # ÖH Z5S / PK5 (P4B1-18) — KÜNYE ASİMETRİSİ KAPANDI. Aynı
                # sözlükteki ``ambient_temperature`` alanı, bir GİRDİ YANKISI
                # olduğunu ve çağıran bir şey vermediğinde modülün kendi
                # varsayılanında kaldığını anlatan ayrıntılı bir künyeyle
                # geliyordu; ``wall_thickness`` AYNI yankı sınıfındadır
                # (imza varsayılanı 5,0 mm) ama künyesi YOKTU. Alan panele
                # doğrudan bağlı olduğu için (analysis_dock.js) kullanıcı
                # 5,0 mm'yi kendi girdisi sanıyordu.
                'wall_thickness_basis': (
                    'wall thickness INPUT echoed back in millimetres, not a '
                    'computed or sized thickness: it is the wall_thickness '
                    'argument of the heat transfer analysis (request field '
                    '"wall_thickness"). When the caller supplies nothing this '
                    'module keeps its own default of 5.0 mm, which is why the '
                    'value can be the same in every run. It sets the '
                    'through-wall conduction resistance, so the equilibrium '
                    'wall temperature and every thermal margin scale with it.'),
                'cooling_type': cooling_type,
                'ambient_temperature': ambient_temp,
                # v2.6.26 — SABİT ÇIKTI BEYANI: bu bir GİRDİ YANKISIDIR,
                # hesaplanmış bir sıcaklık değildir. Hibrit formunda karşılık
                # gelen alan (ambient_temp) bulunmadığı için her koşuda
                # modülün varsayılanında kalır ve sabit görünür.
                'ambient_temperature_basis': (
                    'ambient temperature INPUT echoed back in kelvin, not a '
                    'computed result: it is the ambient_temp argument of the '
                    'heat transfer analysis (request field "ambient_temp"). '
                    'When the caller supplies nothing this module keeps its '
                    'own default of 293.15 K, which is why the value can be '
                    'the same in every run. The same number is read back by '
                    'the structural chain so the two modules cannot assume '
                    'different ambient conditions.'),
            }
        }

    # ------------------------------------------------------------------
    # Eksenel istasyonların geometri kaynağı
    # ------------------------------------------------------------------
    @staticmethod
    def _published_contour_mm(motor_data: Dict):
        """``motor_data['nozzle_contour']['points']`` → (z_mm, r_mm) ya da None.

        Motor çözücülerinin YAYIMLADIĞI iç kontur (metre, ``[z, r]`` çiftleri).
        Bu dizi ``sample_nozzle_inner_contour`` çıktısının kendisidir (hibrit:
        hybrid_rocket_engine.py, katı/sıvı: kendi yayım blokları) ve mesh/FEA
        köprüsü (``hrma.fea.bridge._extract_contour_points``) TAM OLARAK bunu
        okur. Profil de bunu okuduğunda iki üretici aynı ekseni tesadüfen
        değil TANIM GEREĞİ üretir.

        Geçersiz/eksik blokta ``None`` döner — çağıran canlı örneklemeye
        düşer; uydurma kontur üretilmez.
        """
        nc = motor_data.get('nozzle_contour')
        if not isinstance(nc, dict):
            return None
        pts = nc.get('points')
        if pts is None or len(pts) < 3:
            return None
        try:
            arr = np.asarray(pts, dtype=float)
        except (TypeError, ValueError):
            return None
        if arr.ndim != 2 or arr.shape[1] != 2 or not np.all(np.isfinite(arr)):
            return None
        z_mm = arr[:, 0] * 1000.0
        r_mm = arr[:, 1] * 1000.0
        # Eksen kesin artan olmalı (istasyon enterpolasyonu tanımlı olsun) ve
        # yarıçap pozitif (eksenel simetrik cidar ekseni kapsamaz).
        if np.any(r_mm <= 0.0) or not np.all(np.diff(z_mm) > 0.0):
            return None
        return z_mm, r_mm

    def _axial_contour(self, motor_data: Dict, throat: Dict) -> Dict:
        """Eksenel istasyonların dayandığı iç kontur — TEK geometri kaynağı.

        İki yol vardır ve ikisi de AYNI örnekleyicinin çıktısıdır:

          1. Motorun yayımladığı ``nozzle_contour.points`` (varsa). FEA köprüsü
             bu diziyi okuduğu için profil ekseni ile mesh ekseni tanım gereği
             çakışır.
          2. Yayımlanmış kontur yoksa ``sample_nozzle_inner_contour`` canlı
             çağrılır — çözücünün KENDİ içinden (kontur henüz yayımlanmadan)
             gelen çağrılarda tek yol budur.

        ÖLÇÜLEN KUSUR (v2.6.27, D2 zinciri): örnekleyici lüle tipini yalnız
        ``nozzle_angles['nozzle_type']`` ya da ``nozzle_contour['divergent']
        ['type']`` alanlarından okur. Çağıranların bir bölümü tipi ÜST DÜZEY
        ``motor_data['nozzle_type']`` anahtarına yazıyordu (hibrit çözücünün
        lüle malzeme analizi, hybrid_rocket_engine.py) ve o anahtarı hiç kimse
        okumuyordu: bell/parabolik motorun profili KONİK varsayılıyor, eksen
        yayımlanan konturdan %96'ya varan farkla ayrışıyordu (2 kN / 30 bar
        bell: profil 171,85 mm, kontur 87,31 mm). Anahtar burada
        örnekleyicinin okuduğu yere taşınır.

        NOT — ``throat_radius_curvature`` BİLEREK taşınmaz: üst düzeydeki alan
        Bartz'ın (D_t/R_c)^0.1 terimine giren boğaz eğrilik yarıçapıdır
        [metre, tipik 1,5·r_t, boğaz ÖNÜ]; örnekleyicinin
        ``convergent['throat_radius_curvature']`` alanı ise boğaz ÇIKIŞ yayının
        Rao yarıçapıdır [mm, varsayılan 0,382·r_t]. Farklı iki büyüklüktür,
        birini diğerine bağlamak konturu bozar.

        Döner: ``{'z_mm', 'r_mm', 'z_throat', 'z_exit', 'r_throat',
        'noz_type', 'basis'}``. ``basis`` hangi kaynağın kullanıldığını ve
        hangi şekil alanının örnekleyicinin GENEL varsayılanına düştüğünü
        adıyla beyan eder (sessiz varsayım yok).
        """
        # Tembel import: hrma.engines.__init__ -> hybrid_rocket_engine ->
        # heat_transfer_analysis zinciri modül-üstü importta döngü yaratır.
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour

        nc = motor_data.get('nozzle_contour')
        nc = nc if isinstance(nc, dict) else {}
        angles_in = motor_data.get('nozzle_angles')
        angles_in = angles_in if isinstance(angles_in, dict) else {}

        # --- 1) Yayımlanmış kontur (köprünün okuduğu dizinin ta kendisi) ---
        yayimlanan = self._published_contour_mm(motor_data)
        if yayimlanan is not None:
            z_mm, r_mm = yayimlanan
            i_t = int(np.argmin(r_mm))
            # Boğaz uçlarda olamaz: konverjan daralır, ıraksak genişler.
            if 0 < i_t < z_mm.size - 1:
                div_in = nc.get('divergent')
                div_in = div_in if isinstance(div_in, dict) else {}
                noz_type = (div_in.get('type')
                            or angles_in.get('nozzle_type')
                            or motor_data.get('nozzle_type'))
                return {
                    'z_mm': z_mm,
                    'r_mm': r_mm,
                    'z_throat': float(z_mm[i_t]),
                    'z_exit': float(z_mm[-1]),
                    'r_throat': float(r_mm[i_t]),
                    'noz_type': noz_type,
                    'basis': {
                        'source': (
                            "motor_results['nozzle_contour']['points'] — the "
                            'inner contour PUBLISHED by the motor solver '
                            '(metres, [z, r]), which is the very array the '
                            'FEA bridge meshes. Taking the stations from it '
                            'makes the gas-side profile and the mesh share '
                            'one axis by construction, not by coincidence. '
                            'The published array is itself the output of '
                            'nozzle_design.sample_nozzle_inner_contour, the '
                            'single geometry source of the 2D section, the 3D '
                            'scene and the STL/STEP exports.'),
                        'contour_points': int(z_mm.size),
                        'throat_station': (
                            'minimum radius of the published contour (the '
                            'convergent ends and the Rao arc begins there); '
                            'no throat position is assumed'),
                        'nozzle_type_source': (
                            "nozzle_contour['divergent']['type']"
                            if div_in.get('type') else
                            ("nozzle_angles['nozzle_type']"
                             if angles_in.get('nozzle_type') else
                             ('top-level motor_data["nozzle_type"]'
                              if motor_data.get('nozzle_type') else
                              'not declared by the motor result'))),
                        'generic_defaults_used': [],
                    },
                }
            # Boğaz bulunamadı (kontur monoton daralıyor/genişliyor):
            # sessizce kabul edilmez, canlı örneklemeye düşülür ve beyan edilir.
            yayimlanan_red = (
                'the published nozzle_contour.points has no interior minimum '
                'radius, so no throat station can be located on it; the '
                'contour was re-sampled from the geometry fields instead')
        else:
            yayimlanan_red = (
                'the motor result carries no usable nozzle_contour.points '
                'block (absent, wrong shape, non-monotonic z or non-positive '
                'radius), so the contour is sampled live from the geometry '
                'fields')

        # --- 2) Canlı örnekleme ------------------------------------------
        md_geo = dict(motor_data)
        genel_varsayilan = []

        # Boğaz çapı: verilmediyse bu koşunun Bartz boğazı (jenerik değil,
        # aynı çözümün kendi boğazı). 0/'' de "verilmedi" sayılır.
        d_t = _positive_length(md_geo.get('throat_diameter'))
        if d_t is None:
            md_geo['throat_diameter'] = throat['throat_diameter']
            bogaz_kaynak = ('resolved from continuity at the choked throat '
                            '(A_t = mdot*c*/Pc) — the same throat the Bartz '
                            'coefficient uses, so area ratios stay consistent')
        else:
            bogaz_kaynak = "motor_data['throat_diameter']"

        # Çıkış çapı: alan → genleşme oranı → (ikisi de yoksa) ÖRNEKLEYİCİNİN
        # GENEL VARSAYILANI. Sonuncusu bu motorun geometrisi DEĞİLDİR ve
        # beyan edilir; sessizce 80 mm'lik jenerik bir lüle çizilmez.
        d_e = _positive_length(md_geo.get('exit_diameter'))
        if d_e is None:
            md_geo.pop('exit_diameter', None)
            eps = _positive_length(motor_data.get('expansion_ratio'))
            if eps is not None and eps > 1.0:
                md_geo['exit_diameter'] = (
                    md_geo['throat_diameter'] * np.sqrt(eps))
                cikis_kaynak = ("derived from motor_data['expansion_ratio'] "
                                '(d_e = d_t*sqrt(eps))')
            else:
                cikis_kaynak = ('NOT GIVEN — neither exit_diameter nor '
                                'expansion_ratio was supplied; the sampler '
                                'falls back to its own generic exit diameter, '
                                'so the divergent extent of this axis is NOT '
                                "this motor's")
                genel_varsayilan.append('exit_diameter')
        else:
            cikis_kaynak = "motor_data['exit_diameter']"

        # Lüle tipi: örnekleyicinin OKUDUĞU yere taşı (üst düzey anahtar
        # hiçbir yerde okunmuyordu — ölçülen kusur, docstring'de).
        div_in = nc.get('divergent')
        div_in = div_in if isinstance(div_in, dict) else {}
        if div_in.get('type'):
            tip_kaynak = "nozzle_contour['divergent']['type']"
        elif angles_in.get('nozzle_type'):
            tip_kaynak = "nozzle_angles['nozzle_type']"
        else:
            ust_tip = motor_data.get('nozzle_type')
            ust_tip = str(ust_tip).strip() if isinstance(ust_tip, str) else ''
            if ust_tip:
                aci_blok = dict(angles_in)
                aci_blok['nozzle_type'] = ust_tip
                md_geo['nozzle_angles'] = aci_blok
                tip_kaynak = (
                    'top-level motor_data["nozzle_type"], moved onto '
                    "nozzle_angles['nozzle_type'] — the only place the "
                    'contour sampler reads the nozzle type from')
            else:
                tip_kaynak = ('NOT GIVEN — the sampler falls back to its own '
                              'generic nozzle type')
                genel_varsayilan.append('nozzle_type')

        pts, meta = sample_nozzle_inner_contour(md_geo)
        z_mm = np.array([p[0] for p in pts], dtype=float)
        r_mm = np.array([p[1] for p in pts], dtype=float)
        return {
            'z_mm': z_mm,
            'r_mm': r_mm,
            'z_throat': float(meta['z_throat']),
            'z_exit': float(meta['z_exit']),
            'r_throat': float(meta['r_throat']),
            'noz_type': meta.get('noz_type'),
            'basis': {
                'source': (
                    'sampled live from hrma.engines.nozzle_design.'
                    'sample_nozzle_inner_contour — the same single geometry '
                    'source the 2D section, the 3D scene and the STL/STEP '
                    'exports consume. Reason the published contour was not '
                    'used: ' + yayimlanan_red),
                'contour_points': int(z_mm.size),
                'throat_diameter_source': bogaz_kaynak,
                'exit_diameter_source': cikis_kaynak,
                'nozzle_type_source': tip_kaynak,
                'divergent_length_source': meta.get('divergent_length_source'),
                # Boş liste = hiçbir şekil alanı jenerik varsayılana düşmedi.
                # Doluysa bu eksen motorun konturuyla ÖRTÜŞMEK ZORUNDA DEĞİL
                # ve tüketici (FEA köprüsü) onu reddedebilir — reddetmesi
                # doğrudur, uydurma geometriye mesh basılmaz.
                'generic_defaults_used': genel_varsayilan,
            },
        }

    #: ÖH D28 a2 / P16B3-20 — EKSENEL PROFİL İSTASYON SAYISI BANDI.
    #:
    #: Bu iki sayı ``analyze_axial_profile`` gövdesinde ÇIPLAK yazılıydı
    #: (``int(max(5, min(int(n_stations), 400)))``) ve dışarıdan okunamıyordu.
    #: ÖLÇÜLDÜ (taban ``7cd08bcc``, ``a2/once.json`` K8): ``POST
    #: /api/analysis/wall-profile`` gövdesine ``n_stations`` 0, −5 ve 3
    #: gönderildiğinde ÜÇÜ DE HTTP 200 + 4 866 baytlık BİT-AYNI yanıt
    #: veriyordu (``wall_profile.n_stations = 5``): alt sınır SESSİZCE
    #: uygulanıyor, üç ayrı niyet tek sonuca çöküyordu.
    #:
    #: Sayılar DEĞİŞMEDİ — yalnız ADLANDIRILDI ki uç kapısı aynı bandı
    #: KOPYALAMADAN uygulayabilsin (doktrin 4: tek kaynak). Kırpma burada
    #: kalır (modülü doğrudan çağıran iç tüketiciler için savunma), ama
    #: HTTP ucu artık bant dışını sessizce kırpmak yerine ADIYLA reddeder.
    N_STATIONS_MIN = 5
    N_STATIONS_MAX = 400

    def analyze_axial_profile(self, motor_data: Dict, n_stations: int = 40,
                              material: str = 'steel',
                              wall_thickness: float = 0.005,
                              ambient_temp: float = 293.15,
                              cooling_type: str = 'natural') -> Dict:
        """
        Eksenel ısı yükü profili: hazne çıkışı -> boğaz -> nozul çıkışı.

        Nozul iç konturu TEK ortak geometri kaynağından gelir (``_axial_contour``:
        motorun yayımladığı ``nozzle_contour.points``, yoksa aynı dizinin
        üreticisi olan ``nozzle_design.sample_nozzle_inner_contour`` — 2D/3D/CAD
        ile aynı kontur; kopya geometri YOK). Eksen konturun KENDİ orijininden
        başlar ve konturun çıkışında biter; böylece bu profili tüketen FEA
        köprüsü ile aynı alan üzerinde çalışılır. Her istasyonda:

          - A(x)/A_t alan oranı (kontur yarıçapından),
          - izantropik M(x) (konverjanda subsonik, diverjanda süpersonik dal),
          - Bartz h_g(x) = _bartz_coefficient(area_ratio_local=A_t/A, M) —
            throat-analiziyle AYNI korelasyon ve gaz özellikleri,
          - kurtarma (recovery/adyabatik cidar) sıcaklığı Taw(x),
          - muhafazakâr tasarım ısı akısı q(x) (taşınım + radyasyon,
            referans soğutulmuş cidarda — modülün 'design flux' felsefesi),
          - belirtilen soğutma için denge cidar sıcaklığı T_wall_eq(x)
            (yüzey enerji dengesi, bisection).

        Args:
            motor_data: analyze_heat_transfer ile aynı şema (chamber_pressure
                [bar], chamber_temperature [K], gamma, molecular_weight,
                mdot_total, throat_diameter/exit_diameter [m], ...).
            n_stations: Toplam istasyon sayısı (boğaz istasyonu garanti dahil).
            material / wall_thickness / ambient_temp / cooling_type:
                analyze_heat_transfer ile aynı cidar girdileri.

        Returns:
            {'x_mm', 'area_ratio', 'mach', 'h_g', 'q_MW', 'T_wall_eq',
             'T_recovery', 'x_throat_mm', 'x_exit_mm', 'throat_index',
             'contour_basis', ...}
            Tüm diziler eşit uzunluktadır; grafik üretilmez (frontend çizer).
            ``contour_basis`` ekseni hangi konturdan aldığını ve hangi şekil
            alanının verilmediğini adıyla beyan eder.
        """
        n_stations = int(max(self.N_STATIONS_MIN,
                             min(int(n_stations), self.N_STATIONS_MAX)))

        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_temperature = motor_data.get('chamber_temperature', 3000)  # K
        mdot_total = motor_data.get('mdot_total', 1.0)  # kg/s

        # ÖH Z5S / S4: kardeş yolla AYNI çözümleyici — sessiz A36 yedeği
        # burada da kalktı (ölçüldü: ``/api/analysis/wall-profile``
        # ``material='inconel718'`` A36 profili basıyordu).
        material_requested = material
        material = resolve_material_key(material)
        mat_props = self.materials[material]
        gas = self._get_gas_properties(motor_data, chamber_temperature)
        throat = self._resolve_throat_conditions(
            motor_data, chamber_pressure, chamber_temperature, gas, mdot_total
        )
        gamma = gas['gamma']

        # --- Kontur: TEK geometri kaynağı (yayımlanan kontur > canlı örnekleme)
        # Ayrıntı ve ölçülen kusur kaydı _axial_contour docstring'inde.
        kontur = self._axial_contour(motor_data, throat)
        z_pts = kontur['z_mm']
        r_pts = kontur['r_mm']
        z_throat = kontur['z_throat']
        z_exit = kontur['z_exit']
        r_throat = kontur['r_throat']
        # Eksen konturun KENDİ orijininden başlar (örnekleyicide 0,0; ama
        # sözleşme "0" değil "konturun ilk noktası"dır — profil ile mesh aynı
        # alanı kapsasın diye başlangıç varsayılmaz, okunur).
        z_start = float(z_pts[0])

        # --- İstasyon ızgarası: boğaz istasyonu KESİN dahil ---
        # Konverjan/diverjan pay dağılımı uzunlukla orantılı; boğaz noktası
        # iki parçanın ortak ucu (q maks ve M=1 tam boğazda yakalanır).
        toplam_boy = z_exit - z_start
        frac_conv = ((z_throat - z_start) / toplam_boy
                     if toplam_boy > 0 else 0.5)
        n_conv_st = int(round(n_stations * frac_conv))
        n_conv_st = min(max(n_conv_st, 2), n_stations - 1)
        n_div_st = n_stations - n_conv_st + 1  # boğaz paylaşılır
        x_conv = np.linspace(z_start, z_throat, n_conv_st)
        x_div = np.linspace(z_throat, z_exit, n_div_st)[1:]
        x_mm = np.concatenate([x_conv, x_div])
        throat_index = n_conv_st - 1

        # Kontur z ekseni monotonik artar (konverjan -> yay -> diverjan);
        # doğrusal interpolasyon güvenlidir ve tüm örnek yarıçaplar >= r_t.
        r_mm = np.interp(x_mm, z_pts, r_pts)
        area_ratio = np.maximum((r_mm / r_throat) ** 2, 1.0)  # A/A_t >= 1
        area_ratio[throat_index] = 1.0  # boğazda kesin 1 (interp toleransı)

        # --- İstasyon döngüsü ---
        throat_d = throat['throat_diameter']
        c_star = throat['c_star']
        rc_over_dt = throat['rc_over_dt']
        emissivity = mat_props.get('emissivity', 0.8)
        # Işıyan tür kesirleri: TEK TANIM NOKTASI
        # (``resolve_radiation_composition``); ``analyze_heat_transfer`` ile
        # aynı işlev, ikinci bir okuma kuralı yok. Köken etiketi BU blokta
        # yayımlanmaz: ``thermal_fea/wall_profile`` bloğunu hiçbir panel
        # okumuyor ve alanı buraya koymak ters-yön dürüstlük borcunu
        # büyütürdü (tests/test_wave4b_contract.py::
        # TestTersYonBorcEnvanteri ile ölçüldü). Künye kardeş blokta
        # (``gas_side_analysis``) duruyor.
        x_h2o_frac, x_co2_frac, _ = resolve_radiation_composition(motor_data)
        k_wall = mat_props['thermal_conductivity']
        allowable = mat_props.get('allowable_temperature', 1073)
        # ÖH D31 / P12bB4-06: soğutucu tarafı künyeli çözülür; boğaz
        # analiziyle AYNI tek tanım (aynı girdide aynı sayı ve aynı köken).
        _coolant = self._coolant_side_resolution(
            motor_data, cooling_type, coolant_bulk_temp=ambient_temp)
        h_coolant = _coolant['value']
        R_out = wall_thickness / k_wall + 1.0 / h_coolant  # m^2*K/W

        mach = np.empty(n_stations)
        h_g = np.empty(n_stations)
        q_flux = np.empty(n_stations)     # W/m^2
        t_recovery = np.empty(n_stations)
        t_wall_eq = np.empty(n_stations)

        for i in range(n_stations):
            supersonic = i > throat_index
            M = self._mach_from_area_ratio(area_ratio[i], gamma, supersonic)
            mach[i] = M

            # Kurtarma (adyabatik cidar) sıcaklığı — q'nun sürücü sıcaklığı.
            Taw = self._adiabatic_wall_temperature(chamber_temperature, gas, M)
            t_recovery[i] = Taw

            # Referans soğutulmuş cidar — TEK TANIM NOKTASI (P4B1-03);
            # throat-analizi de aynı işlevi çağırır.
            Tw_ref = self._design_reference_wall_temperature(
                allowable, Taw, ambient_temp)

            h_i = self._bartz_coefficient(
                throat_d, chamber_pressure, c_star, gas,
                chamber_temperature, Tw_ref, rc_over_dt,
                area_ratio_local=1.0 / area_ratio[i],  # A_t/A (boğazda 1)
                mach_local=M
            )
            h_g[i] = h_i

            # Radyasyon: Leckner gaz emisivitesi (kara cisim DEĞİL). Yayan
            # gaz yerel STATİK sıcaklık/basınçta; ışın uzunluğu yerel çapla.
            # Hesabın kendisi ``_design_heat_flux``tadır — throat-analizi de
            # AYNI işlevi çağırır (P4B1-03 tek tanım noktası).
            d_local = 2.0 * r_mm[i] / 1000.0

            def gas_side_flux(Tw, h_local=None):
                return self._design_heat_flux(
                    h_gas=(h_i if h_local is None else h_local),
                    taw=Taw, t_wall=Tw,
                    chamber_temperature=chamber_temperature,
                    chamber_pressure=chamber_pressure, gamma=gamma,
                    local_diameter=d_local, emissivity=emissivity,
                    x_H2O=x_h2o_frac, x_CO2=x_co2_frac, mach_local=M)

            # Tasarım akısı: referans soğutulmuş cidarda dondurulmuş h_i ile
            # (panelin ana güvenlik sayısı — davranışı korunur).
            q_flux[i] = gas_side_flux(Tw_ref)

            # Denge cidar sıcaklığı: q_in(Tw) = (Tw - T_amb)/R_out, bisection.
            # DÜZELTME (v2.6.2, fizik denetimi F116): Bartz sigma düzeltmesi
            # cidar sıcaklığına bağlıdır (Sutton & Biblarz Eq. 8-22), bu
            # yüzden denge çözümünde h_g de İTERASYONA girmelidir. Eskiden
            # h_g referans cidarda (Tw_ref) donduruluyordu; denge cidarı
            # Tw_ref'ten soğuk çıktığında sigma oranı 1.16'ya kadar çıkıyor,
            # yani h_g %16 EKSİK kullanılıyordu (T_wall_eq düşük tahmin =
            # güvensiz yön). regen_cooling.py::_station_wall_balance zaten
            # bu kuple çözümü yapıyor; iki modül artık aynı yöntemde.
            def gas_side_flux_coupled(Tw):
                h_local = self._bartz_coefficient(
                    throat_d, chamber_pressure, c_star, gas,
                    chamber_temperature, max(Tw, 1.0), rc_over_dt,
                    area_ratio_local=1.0 / area_ratio[i],
                    mach_local=M
                )
                return gas_side_flux(Tw, h_local)

            def q_out(Tw):
                return (Tw - ambient_temp) / R_out

            lo, hi = ambient_temp, Taw
            if (gas_side_flux_coupled(lo) - q_out(lo)) <= 0:
                t_wall_eq[i] = ambient_temp
            elif (gas_side_flux_coupled(hi) - q_out(hi)) >= 0:
                t_wall_eq[i] = hi
            else:
                for _ in range(200):
                    mid = 0.5 * (lo + hi)
                    if (gas_side_flux_coupled(mid) - q_out(mid)) > 0:
                        lo = mid
                    else:
                        hi = mid
                    if hi - lo < 1e-3:
                        break
                t_wall_eq[i] = 0.5 * (lo + hi)

        return {
            # İstenen çekirdek şema — tüm diziler eşit uzunlukta
            'x_mm': x_mm.tolist(),
            # ÖH D15 / termo-ucus (P4B1-08): İSTASYON YARIÇAPI artık
            # YAYIMLANIR. Tüketiciler (ıslak yüzey integrali, FEA köprüsü)
            # yarıçapı ``r = r_t*sqrt(area_ratio)`` ile GERİ KURMAK zorunda
            # kalıyordu; ``area_ratio`` KONTURUN kendi boğazına göre kurulmuş,
            # ``r_t`` ise ÇÖZÜLEN boğaz (A_t = mdot*c*/Pc) olduğu için iki
            # boğaz ayrıştığında yarıçaplar ölçekleniyor, eksen ölçeklenmiyordu.
            'r_mm': r_mm.tolist(),
            'area_ratio': area_ratio.tolist(),      # A(x)/A_t (>= 1)
            'mach': mach.tolist(),
            'h_g': h_g.tolist(),                    # W/(m^2*K)
            'q_MW': (q_flux / 1e6).tolist(),        # MW/m^2 (tasarım yükü)
            'T_wall_eq': t_wall_eq.tolist(),        # K (denge, verilen soğutma)
            # Ek (additive) meta — frontend işaretçileri ve teşhis için
            'T_recovery': t_recovery.tolist(),      # K (adyabatik cidar)
            'x_throat_mm': z_throat,
            'x_exit_mm': z_exit,
            'throat_index': throat_index,
            'throat_diameter_m': throat_d,
            'nozzle_type': kontur['noz_type'],
            'material': material,
            **({'material_requested': material_requested}
               if str(material_requested) != material else {}),
            'cooling_type': cooling_type,
            # P12bB4-06: eksenel dengeye giren soğutucu-tarafı katsayısı ve
            # KÖKENİ. Eskiden bu sayı hiç yayımlanmıyordu; tüketici cidar
            # sıcaklığının hangi soğutma varsayımıyla çıktığını göremiyordu.
            # ÖH D31 / P12bB4-06: soğutucu-tarafı katsayısı ve KÜNYESİ bu
            # blokta YAYIMLANMAZ. Gerekçe kardeş ``resolve_radiation_composition``
            # köken etiketiyle aynı: ``thermal_fea/wall_profile`` bloğunu
            # hiçbir panel tek tek okumuyor (thermal_fea_panel.js bloğu
            # /api/fea/thermal gövdesine AYNEN taşıyor), oraya alan koymak
            # ters-yön dürüstlük borcunu büyütürdü
            # (tests/test_wave4b_contract.py::TestTersYonSozlesmesi ile
            # ölçülü sözleşme). Künye, panellerin okuduğu
            # ``heat_transfer_coefficients`` bloğunda durur; bu eksen aynı
            # ``_coolant_side_resolution`` tek tanımını okur.
            'wall_thickness_mm': wall_thickness * 1000.0,
            'n_stations': n_stations,
            # Eksenin geometri künyesi. Tüketici (FEA köprüsü) bu profili
            # motorun konturuna taşıyacaksa hangi konturdan geldiğini ve
            # hangi şekil alanının VERİLMEDİĞİNİ buradan okur; eksen
            # uyuşmazlığı artık sessiz değil, adlı bir bilgidir.
            'contour_basis': kontur['basis'],
            # ÖH D37 A2-1 termal 7. tur — karar §28-24 §2 (b): h(z)'nin
            # dayandığı γ / MW / c*'ın KÖKENİ. Modül varsayılanına düşülen
            # alan ``assumed_fields``te ADIYLA durur; FEA köprüsü bu listeyi
            # okur ve dolu ise olumlu güvenlik hükmü VERMEZ (jenerik gazla
            # başarı gösterilmez). Panel bloğu künyede okur (sağır değil).
            'gas_properties_basis': axial_profile_gas_basis(
                motor_data, gas, throat),
        }

    def _calculate_heat_transfer_coefficients(self, motor_data: Dict,
                                           mat_props: Dict, cooling_type: str,
                                           gas: Optional[Dict] = None,
                                           throat: Optional[Dict] = None,
                                           chamber_pressure: Optional[float] = None,
                                           chamber_temperature: Optional[float] = None,
                                           ambient_temp: float = 293.15) -> Dict:
        """
        Calculate heat transfer coefficients.

        Gas side now uses the Bartz throat correlation (physically correct for
        rocket nozzles) instead of the Dittus-Boelter pipe-flow correlation,
        which under-predicted h_g by ~4-15x in the unsafe direction.

        ÖH Z5S / PK5 (P4B1-03): gaz-yanı katsayı artık TASARIM AKISININ
        referans cidar sıcaklığında (``_design_reference_wall_temperature``)
        kurulur. Eskiden burada ayrı bir ``wall_guess = min(0,5·Tc,
        max_service·0,8)`` vardı ve eksenel profil aynı boğaz için farklı bir
        h_g yayımlıyordu (ölçülen sapma %10,26). İki kanal artık aynı tek
        tanımı okuyor.
        """
        # Backward-compatible resolution if called without the new args.
        if chamber_pressure is None:
            chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        if chamber_temperature is None:
            chamber_temperature = motor_data.get('chamber_temperature', 3000)  # K
        mdot_total = motor_data.get('mdot_total', 1.0)
        if gas is None:
            gas = self._get_gas_properties(motor_data, chamber_temperature)
        if throat is None:
            throat = self._resolve_throat_conditions(
                motor_data, chamber_pressure, chamber_temperature, gas, mdot_total
            )

        # --- Gas-side: Bartz at the throat (M=1, A_t/A=1) ---
        # Referans SOĞUTULMUŞ cidar sıcaklığı: tasarım akısıyla AYNI tek
        # tanım (P4B1-03). Denge cidarı aşağıdaki yüzey enerji dengesinde
        # ayrıca çözülür ve h_g orada cidara bağlı olarak yeniden kurulur.
        taw_throat = self._adiabatic_wall_temperature(
            chamber_temperature, gas, mach_local=1.0)
        wall_reference = self._design_reference_wall_temperature(
            mat_props.get('allowable_temperature', 1073), taw_throat,
            ambient_temp)
        h_gas = self._bartz_coefficient(
            throat['throat_diameter'], chamber_pressure, throat['c_star'],
            gas, chamber_temperature, wall_reference, throat['rc_over_dt'],
            area_ratio_local=1.0, mach_local=1.0
        )

        # Reynolds / Nusselt reported at the throat for reference/diagnostics.
        throat_d = throat['throat_diameter']
        # Boğaz statik yoğunluğu STATİK boğaz basıncıyla hesaplanmalı: tıkanmış
        # (M=1) boğazda statik basınç P_t = Pc·(2/(γ+1))^(γ/(γ-1)) < Pc'dir.
        # Durgunluk oda basıncı Pc'yi statik boğaz sıcaklığıyla (T_t) eşleştirmek
        # yoğunluğu -ve dolayısıyla raporlanan Reynolds/Nusselt'i- ~1.8x şişirir.
        # Tutarlılık: rho_t·a_t = Pc/c* (boğaz kütle akısı). Yalnız diagnostik
        # (h_gas ayrı Bartz korelasyonuyla hesaplanır, bu değerden etkilenmez).
        throat_static_pressure = chamber_pressure * (2.0 / (gas['gamma'] + 1.0)) ** (
            gas['gamma'] / (gas['gamma'] - 1.0))
        rho_throat = throat_static_pressure / (gas['gas_constant'] * throat['throat_temperature'])
        a_throat = np.sqrt(gas['gamma'] * gas['gas_constant'] * throat['throat_temperature'])
        v_throat = a_throat  # M=1
        reynolds = rho_throat * v_throat * throat_d / gas['gas_viscosity']
        prandtl = gas['prandtl']
        nusselt = h_gas * throat_d / gas['gas_conductivity']

        # --- Coolant side --- (ÖH D31 / P12bB4-06: KÖKEN KÜNYELİ)
        # ``ambient_temp`` bu API'de soğutucu GİRİŞ sıcaklığı olarak
        # belgelidir (bkz. ``analyze_heat_transfer`` docstring'i); korelasyon
        # yolu yığın özelliklerini o sıcaklıkta okur.
        coolant = self._coolant_side_resolution(
            motor_data, cooling_type, coolant_bulk_temp=ambient_temp)
        h_coolant = coolant['value']

        return {
            'gas_side': h_gas,
            'coolant_side': h_coolant,
            # P12bB4-06: h_coolant'ın NASIL kurulduğu ARTIK yayımlanıyor.
            # 'dittus_boelter' = kanal girdileriyle HESAPLANDI;
            # 'not_modelled'   = beyan edilen tipik bant (hesap değil),
            #                    eksik alanlar ``coolant_side_missing_fields``te;
            # 'user_supplied'  = çağıranın verdiği sayı.
            'coolant_side_method': coolant['method'],
            'coolant_side_source': coolant['source'],
            **({'coolant_side_missing_fields': coolant['missing_fields']}
               if coolant['missing_fields'] else {}),
            **({'coolant_side_detail': coolant['detail']}
               if coolant['detail'] else {}),
            # Korelasyon zarfı İHLAL edildiyse (Re < 1e4 gibi) bunu gömme:
            # üst düzeyde adıyla yayımla — kardeş ``regen_cooling`` de aynı
            # ihlali uyarı olarak yayımlar (asimetrik hüküm kurulmaz).
            **({'coolant_side_envelope_violations':
                coolant['detail']['envelope']['violations']}
               if coolant['detail'].get('envelope', {}).get('violations')
               else {}),
            'reynolds_number': reynolds,
            'prandtl_number': prandtl,
            'nusselt_number': nusselt,
            # extra diagnostics (additive, do not break existing consumers)
            'correlation': ('Bartz (Bartz 1965 Eqs. 48-50, closed form of '
                            'Eq. 50; Sutton & Biblarz 9th ed. Eq. 8-22 is the '
                            'equivalent property-ratio form)'),
            # ÖH KU (KC-13 beyanı, sayı değişmez): gaz tarafı modelinin
            # modellemediği iki etki ve yönleri.
            'gas_side_model_limits': GAS_SIDE_MODEL_LIMITS_BASIS,
            'c_star': throat['c_star'],
            'throat_diameter': throat['throat_diameter'],
            'gas_viscosity': gas['gas_viscosity'],
            'gas_conductivity': gas['gas_conductivity'],
            'gas_cp': gas['gas_cp'],
            'gamma': gas['gamma'],
            # P4B1-03: h_g'nin hangi cidar sıcaklığında kurulduğu ARTIK
            # yayımlanıyor; eksenel profil aynı sayıyı okur.
            'gas_side_reference_wall_temperature': wall_reference,
        }

    def _analyze_gas_side_heat_transfer(self, pressure: float, temperature: float,
                                      diameter: float, length: float, mdot: float,
                                      coeffs: Dict, gas: Dict, throat: Dict,
                                      mat_props: Dict, wall_thickness: float,
                                      ambient_temp: float,
                                      x_H2O: Optional[float] = None,
                                      x_CO2: Optional[float] = None,
                                      composition_source: Optional[str] = None
                                      ) -> Dict:
        """
        Analyze gas-side heat transfer.

        Two distinct quantities are computed, and conflating them is exactly the
        bug that previously hid burn-through:

        (A) DESIGN HEAT FLUX (safety-relevant load). The convective+radiative
            heat flux the cooling system MUST remove, evaluated at a conservative
            *reference cooled wall temperature* (the material allowable temp,
            bounded). This is q = h_g*(Taw - Tw_ref) + q_rad(Taw, Tw_ref), where
            q_rad uses the Leckner (1972) H2O/CO2 gas emissivity model (see
            _gas_radiation_flux) instead of the former black-body assumption.
            It must NOT be allowed to collapse to zero — letting the wall float to
            the adiabatic temperature drives q->0 and masks the danger.

        (B) EQUILIBRIUM WALL TEMPERATURE (cooling-adequacy check). The steady
            wall temperature actually reached for the *specified* cooling, from
            the surface energy balance q_in(Tw) = q_out(Tw):
                q_in  = h_g*(Taw - Tw) + q_rad(Taw, Tw)   [Leckner gas radiation]
                q_out = (Tw - T_coolant) / (R_cond + R_coolant)
            If Tw floats near Taw, the cooling is grossly inadequate (warn).

        References: Bartz (1957); Sutton & Biblarz 9th ed. Ch. 8;
        NASA SP-8124; Huzel & Huang Ch. 4; Leckner, Comb. Flame 19:33 (1972).
        """
        warnings_list: List[str] = []

        h_gas = coeffs['gas_side']
        h_coolant = coeffs['coolant_side']
        k_wall = mat_props['thermal_conductivity']
        emissivity = mat_props.get('emissivity', 0.8)
        # ÖH D37 A2-1 / F-01 + M2 — EŞİK MERDİVENİ TEK FONKSİYONDAN.
        # Eski üç satır üç alanı ayrı ayrı okuyordu (max_service_temperature
        # klampı, allowable_temperature, melting_point); uyarı eşiği
        # steel_4130'da 1000 K (allowable) iken termal FEA ve ısı-yutucu
        # 811 K (max_service_temp) diyordu — aynı motor, dört sayı
        # (docs/tasarim/malzeme-tarama/A1_mevcut_durum.md §1.4). Uyarı
        # eşiği artık merdivenin İZİN basamağı (allowable_K = min(allowable,
        # max_service_temp)); kritik eşik min(clamp_K, melting_K) ile
        # BİT-AYNI kalır (klamp 20/24 kayıtta erimeye eşit, P9B4-14).
        _limits = temperature_limits(mat_props)
        max_service = (_limits['clamp_K'] if _limits['clamp_K'] is not None
                       else 2000.0)
        allowable = (_limits['allowable_K'] if _limits['allowable_K']
                     is not None else 1073.0)
        melting_point = float(_limits['melting_K']
                              if _limits['melting_K'] is not None
                              else max_service)

        # Adiabatic wall (recovery) temperature at the throat (M=1).
        Taw = self._adiabatic_wall_temperature(temperature, gas, mach_local=1.0)

        # --- (A) DESIGN HEAT FLUX at a conservative reference cooled wall ---
        # Referans cidar sıcaklığı TEK TANIM NOKTASINDAN gelir (P4B1-03);
        # eksenel profil de aynı işlevi çağırır.
        # F-01/M2 KAPSAM NOTU: Tw_ref bir SINIR DENETİMİ değil, tasarım
        # akısının hesaplandığı referans soğutulmuş cidar sözleşmesidir
        # (``allowable_temperature`` kaydı; eksenel profil aynı alanı okur).
        # Merdivene bağlansaydı her motorun h_g/q_MW'si kayardı (P7B3-30
        # ölçümü: malzemeye göre 4,125 kat) — kilit olcut_kulvar.json K5.
        Tw_ref = self._design_reference_wall_temperature(
            mat_props.get('allowable_temperature', 1073), Taw, ambient_temp)

        # Radyasyon: Leckner gaz emisivitesi (kara cisim DEĞİL), YEREL statik
        # durumda ve yerel çapla (``_design_heat_flux``). ÖH Z5S / PK5
        # (P4B1-03): eskiden bu bacak hazne durgunluk koşullarını ve hazne
        # çapını kullanıyordu (T_g = Taw, p = P_c, L = 0,9·D_hazne), eksenel
        # profil ise boğazda yerel statik durumu — aynı boğazın akısı bu
        # yüzden iki değerle yayımlanıyordu. Işıma yapan gaz, o istasyondaki
        # gazdır; alanın adı da "throat_heat_flux"tır.
        # P4B1-10 ŞARTı: ``None`` = "verilmedi" (modül varsayılanı), bir
        # sayı = "çağıran verdi" — DEĞERİ varsayılana eşit olsa bile. Köken
        # etiketi çağıran katmandan geçirilmişse o kullanılır (motor_data'da
        # anahtarın varlığını YALNIZ orası bilir); geçirilmemişse bu
        # işlevin kendi argümanlarının varlığından kurulur.
        x_h2o_frac = DEFAULT_X_H2O if x_H2O is None else float(x_H2O)
        x_co2_frac = DEFAULT_X_CO2 if x_CO2 is None else float(x_CO2)
        if composition_source is None:
            composition_source = radiation_composition_source(
                x_H2O is not None, x_CO2 is not None)

        def gas_side_flux(Tw, h, *, mach_local=1.0, local_diameter=None):
            return self._design_heat_flux(
                h_gas=h, taw=Taw, t_wall=Tw,
                chamber_temperature=temperature, chamber_pressure=pressure,
                gamma=gas['gamma'],
                local_diameter=(throat['throat_diameter']
                                if local_diameter is None else local_diameter),
                emissivity=emissivity, x_H2O=x_h2o_frac, x_CO2=x_co2_frac,
                mach_local=mach_local)

        throat_heat_flux = gas_side_flux(Tw_ref, h_gas)  # W/m^2 (real design load)

        # --- (B) EQUILIBRIUM WALL TEMPERATURE for the specified cooling ---
        R_cond = wall_thickness / k_wall
        R_coolant = 1.0 / h_coolant
        R_out = R_cond + R_coolant

        def q_out(Tw):
            return (Tw - ambient_temp) / R_out

        # DÜZELTME (v2.6.2, fizik denetimi F116): Bartz sigma düzeltmesi
        # CİDAR SICAKLIĞINA bağlıdır (Sutton & Biblarz Eq. 8-22:
        # sigma = 1/[(0.5*(Tw/Tc)*m2 + 0.5)^0.68 * m2^0.12]). Eskiden denge
        # cidarı çözülürken h_g referans cidarda (Tw_ref) DONDURULMUŞTU;
        # denge cidarı Tw_ref'ten soğuk çıktığında h_g %16'ya kadar EKSİK
        # kullanılıyordu (güvensiz yön: T_wall_eq ve q düşük tahmin). Artık
        # bisection'ın her adımında h_g o deneme cidar sıcaklığında yeniden
        # hesaplanır — regen_cooling.py::_station_wall_balance ile aynı
        # kuple çözüm mantığı (tek yöntem kuralı).
        def gas_side_flux_coupled(Tw):
            h_local = self._bartz_coefficient(
                throat['throat_diameter'], pressure, throat['c_star'], gas,
                temperature, max(Tw, 1.0), throat['rc_over_dt'],
                area_ratio_local=1.0, mach_local=1.0
            )
            return gas_side_flux(Tw, h_local)

        lo, hi = ambient_temp, Taw
        if (gas_side_flux_coupled(lo) - q_out(lo)) <= 0:
            T_wall = ambient_temp
        elif (gas_side_flux_coupled(hi) - q_out(hi)) >= 0:
            T_wall = hi
        else:
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                if (gas_side_flux_coupled(mid) - q_out(mid)) > 0:
                    lo = mid
                else:
                    hi = mid
                if hi - lo < 1e-3:
                    break
            T_wall = 0.5 * (lo + hi)

        # --- Physical clamp / warnings on equilibrium wall temperature ---
        # DÜZELTME (v2.6.2, fizik denetimi F011): kritik yanma-delinme eşiği
        # ERİME NOKTASININ ÜSTÜNDE olamaz. materials_db'de çelik ailesinde
        # max_service_temperature (denge cidarı klamp üst sınırı) erime
        # noktasının ÜSTÜNDEDİR (steel: 2000 K vs 1773 K; ss_304: 1723 vs
        # 1673; ss_316: 1672 vs 1644). Bu yüzden 1773 K < T_wall < 2000 K
        # penceresine düşen gerçek tasarımlarda ERİMİŞ cidar yalnız
        # 'warning' seviyesinde raporlanıyordu — güvensiz yön. Kritik eşik
        # artık min(max_service_temperature, melting_point) ile kurulur ve
        # erime ayrı, daha sert bir kodla bildirilir.
        # F-01/M2: hükmün dayandığı merdiven, yanıtta ADIYLA durur.
        threshold_ladder = {
            'allowable_K': float(allowable),
            'service_K': _limits['service_K'],
            'melting_K': float(melting_point),
            'critical_K': float(min(float(max_service), melting_point)),
            'source': _limits['basis'],
            # V3 KK (§28-31): hükmü veren aday ADIYLA (tek kaynak).
            **allowable_governance(_limits),
        }
        critical_limit = min(float(max_service), melting_point)
        wall_unphysical = False
        mat_name = material_name(mat_props, self.materials)
        if T_wall > melting_point:
            wall_unphysical = True
            warnings_list.append(_mk_warning(
                'warn.thermal.wall_exceeds_melting', 'critical',
                T_wall=round(T_wall), material=mat_name,
                melting=round(melting_point),
                q_MW=round(throat_heat_flux / 1e6, 1)))
        elif T_wall > critical_limit:
            wall_unphysical = True
            warnings_list.append(_mk_warning(
                'warn.thermal.wall_exceeds_service', 'critical',
                T_wall=round(T_wall), material=mat_name,
                limit=round(critical_limit),
                q_MW=round(throat_heat_flux / 1e6, 1)))
        elif T_wall > allowable:
            warnings_list.append(_mk_warning(
                'warn.thermal.wall_exceeds_allowable', 'warning',
                T_wall=round(T_wall), material=mat_name, allowable=round(allowable)))
        if T_wall > 3500:
            warnings_list.append(_mk_warning(
                'warn.thermal.wall_nonphysical', 'critical', T_wall=round(T_wall)))
        if T_wall >= 0.95 * Taw:
            warnings_list.append(_mk_warning(
                'warn.thermal.wall_pinned_adiabatic', 'critical'))

        # The 'heat_flux' key (consumed downstream) is the conservative design
        # load — NEVER the masked near-adiabatic value.
        heat_flux = throat_heat_flux

        # --- Chamber-barrel flux (lower than throat: A_t/A < 1) ---
        throat_area = throat['throat_area']
        surface_area = np.pi * diameter * length + np.pi * (diameter / 2.0) ** 2  # m^2
        chamber_area = np.pi * (diameter / 2.0) ** 2
        area_ratio_chamber = throat_area / chamber_area if chamber_area > 0 else 0.1
        area_ratio_chamber = min(area_ratio_chamber, 1.0)
        h_chamber = self._bartz_coefficient(
            throat['throat_diameter'], pressure, throat['c_star'], gas,
            temperature, Tw_ref, throat['rc_over_dt'],
            area_ratio_local=area_ratio_chamber, mach_local=0.2
        )
        # Hazne bacağı KENDİ yerel durumunda (M~0,2) ve KENDİ çapıyla
        # (silindirik gövde) — aynı tek tanım, farklı istasyon (P4B1-03).
        chamber_heat_flux = gas_side_flux(
            Tw_ref, h_chamber, mach_local=0.2,
            local_diameter=diameter)  # W/m^2 (design load)

        # Total heat rate: chamber flux over barrel area + throat flux over throat.
        # NOT (F038): bu ifade konverjan + diverjan nozul ıslak yüzeyini
        # DIŞARIDA bırakır ve boğaz akısını A_t (KESİT alanı, ıslak alan
        # değil) üzerine uygular. analyze_heat_transfer bu değeri
        # _apply_wetted_heat_load ile kontur integraline yükseltir; burada
        # yalnız kontur örneklenemezse kullanılacak yedek olarak kalır.
        total_heat_rate = chamber_heat_flux * surface_area + throat_heat_flux * throat_area  # W

        return {
            'heat_flux': heat_flux,                  # W/m^2 (conservative design load, throat)
            'total_heat_rate': total_heat_rate,      # W
            'surface_area': surface_area,            # m^2
            'chamber_diameter': diameter,            # m (ıslak alan integrali için)
            'chamber_length': length,                # m
            'throat_heat_flux': throat_heat_flux,    # W/m^2 (real Bartz, not chamber*1.5)
            'chamber_heat_flux': chamber_heat_flux,  # W/m^2 (real Bartz at A_t/A)
            'gas_temperature': temperature,          # K (stagnation/chamber)
            'adiabatic_wall_temperature': Taw,       # K (recovery temperature)
            'reference_wall_temperature': Tw_ref,    # K (cooled wall for design flux)
            # ÖH Z5S / PK5 (P4B1-20, radyasyon ayağı): kaynaktan BİLİNÇLİ
            # sapmalar ve mühendislik kelepçeleri kod yorumlarında yazılıydı
            # ama ÇIKTIDA hiç beyan edilmiyordu. Radyasyon terimi tasarım
            # akısının içine giriyor, yani kullanıcının gördüğü sayının bir
            # parçası; künyesi de onunla birlikte yayımlanır.
            'radiation_model_basis': RADIATION_MODEL_BASIS,
            # ÖH D15 / termo-ucus (P4B1-10 kalıntısı): ışıyan tür mol
            # kesirleri ARTIK YANITTA. Kalemin ana iddiası ("x_H2O/x_CO2 bu
            # yolda SESSİZCE düşüyor, üç kompozisyonda akı bit-bit aynı")
            # ölçümle ÇÜRÜTÜLDÜ — üç kompozisyon üç ayrı akı veriyor
            # (35,5089 / 35,7942 / 35,2639 MW/m2). Ayakta kalan kusur
            # beyandı: kompozisyon verilmediğinde kullanılan modül
            # varsayılanları (DEFAULT_X_H2O / DEFAULT_X_CO2) yanıtta hiç
            # görünmüyordu, yani kullanıcı hangi gazın ışıdığını okuyamıyordu.
            'radiation_x_H2O': float(x_h2o_frac),
            'radiation_x_CO2': float(x_co2_frac),
            # ÖH D17 (P4B1-10 ŞARTı): etiket KÖKENDEN kurulur, değer
            # eşitliğinden DEĞİL — bkz. ``radiation_composition_source``.
            'radiation_composition_source': composition_source,
            'estimated_wall_temperature': T_wall,    # K (equilibrium, given cooling)
            'gas_side_coefficient': h_gas,           # W/m^2/K
            'wall_temperature_unphysical': wall_unphysical,
            # F-01/M2: uyarı/kritik hükmünün dayandığı eşik merdiveni.
            'threshold_ladder': threshold_ladder,
            'warnings': warnings_list,
        }

    def _apply_wetted_heat_load(self, gas_side: Dict, motor_data: Dict,
                                material: str, wall_thickness: float,
                                ambient_temp: float, cooling_type: str,
                                n_stations: int = 41) -> Dict:
        """Toplam ısı yükünü GERÇEK ıslak yüzey integraliyle değiştirir.

        DÜZELTME (v2.6.2, fizik denetimi F038). Eski ifade

            Q = q_hazne * (pi*D*L + pi*(D/2)^2) + q_bogaz * A_t

        iki ayrı kusur taşıyordu:
          (1) konverjan bölüm ve TÜM diverjan nozul ıslak yüzeyi hesaba
              hiç girmiyordu;
          (2) boğaz akısı A_t (boğaz KESİT alanı) üzerine uygulanıyordu —
              A_t bir ıslak yüzey değildir, boğazın ıslak alanı kontur
              üzerindeki 2*pi*r*ds şeridi kadardır.

        Doğrusu, toplam ısı yükünün ıslak yüzey integrali olmasıdır
        (Sutton & Biblarz 9th ed. Ch. 8):

            Q = ∫ q(x) * 2*pi*r(x) * ds   +   q_hazne * A_silindirik

        Kontur, 2D/3D/CAD ile AYNI tek geometri kaynağından örneklenir
        (analyze_axial_profile -> sample_nozzle_inner_contour); kopya
        geometri üretilmez. q(x) aynı Bartz + Leckner tasarım akısıdır.

        Bu değer doğrudan soğutucu debisini ve ısı-yutucu kütlesini
        boyutlandırdığı için eksik tahmin GÜVENSİZ yöndeydi.

        Kontur örneklenemezse (geometri eksik / import hatası) eski yedek
        değer korunur ve sonuçta ``wetted_integral_available=False`` ile
        dürüstçe bildirilir.

        Args:
            gas_side: _analyze_gas_side_heat_transfer çıktısı (YERİNDE
                güncellenir).
            motor_data / material / wall_thickness / ambient_temp /
            cooling_type: analyze_heat_transfer ile aynı girdiler.
            n_stations: kontur integrali istasyon sayısı.

        Returns:
            Aynı ``gas_side`` sözlüğü (zincirleme kolaylığı için).
        """
        diameter = float(gas_side.get('chamber_diameter', 0.1))
        length = float(gas_side.get('chamber_length', 0.5))
        chamber_flux = float(gas_side.get('chamber_heat_flux', 0.0))

        # Silindirik hazne gövdesi + enjektör yüzü (kontur bu bölümü
        # içermez: sample_nozzle_inner_contour z=0'da hazne yarıçapından
        # başlar ve konverjana girer).
        barrel_area = np.pi * diameter * length
        injector_area = np.pi * (diameter / 2.0) ** 2
        q_barrel = chamber_flux * (barrel_area + injector_area)

        gas_side['barrel_wetted_area'] = float(barrel_area + injector_area)
        gas_side['barrel_heat_rate'] = float(q_barrel)

        try:
            profile = self.analyze_axial_profile(
                motor_data, n_stations=n_stations, material=material,
                wall_thickness=wall_thickness, ambient_temp=ambient_temp,
                cooling_type=cooling_type
            )
            x = np.asarray(profile['x_mm'], dtype=float) / 1000.0      # m
            # --- YARIÇAPLAR KONTURDAN OKUNUR (ÖH D15, P4B1-08) -----------
            # ÖLÇÜLEN KUSUR: burada yarıçap ``r = (D_t_çözülen/2) *
            # sqrt(area_ratio)`` ile GERİ KURULUYORDU. ``area_ratio``
            # KONTURUN kendi boğaz yarıçapına göre tanımlıdır; ``D_t_çözülen``
            # ise A_t = mdot*c*/Pc'den gelir. İki boğaz ayrıştığında bütün
            # yarıçaplar ölçekleniyor ama EKSEN (x) ölçeklenmiyordu — yani
            # integral, geometrik olarak var olmayan bir yüzeyde alınıyordu.
            #
            # ÖLÇÜLDÜ (kontur boğaz yarıçapı 30,000 mm, çözülen 26,650 mm,
            # ölçek 0,8883): ıslak lüle alanı modülün kurduğu 0,100876 m2
            # <-> konturun kendisi 0,114891 m2 -> %12,20 EKSİK. Eksik ıslak
            # alan eksik toplam yük, eksik soğutucu debisi ve eksik ısı
            # yutucu kütlesi demektir (GÜVENSİZ yön).
            #
            # Profil artık istasyon yarıçaplarını ``r_mm`` ile YAYIMLIYOR;
            # integral o tek geometri kaynağını okur. Alan başka bir yerde
            # yeniden türetilmez.
            r_pub = profile.get('r_mm')
            if r_pub is None:
                raise ValueError(
                    "eksenel profil istasyon yarıçaplarını (r_mm) "
                    "yayımlamıyor — ıslak yüzey integrali alanı yeniden "
                    "türetmez")
            r = np.asarray(r_pub, dtype=float) / 1000.0                # m
            q = np.asarray(profile['q_MW'], dtype=float) * 1e6         # W/m^2
            if x.size < 2:
                raise ValueError("kontur en az 2 istasyon gerektirir")
            if r.size != x.size:
                raise ValueError(
                    "eksen ve yarıçap dizileri aynı uzunlukta olmalı "
                    f"(x={x.size}, r={r.size})")

            # Yamuk kuralı: eğik (slant) uzunluk ds ve ortalama yarıçap.
            ds = np.hypot(np.diff(x), np.diff(r))
            r_mean = 0.5 * (r[1:] + r[:-1])
            q_mean = 0.5 * (q[1:] + q[:-1])
            dA = 2.0 * np.pi * r_mean * ds
            nozzle_area = float(np.sum(dA))
            q_nozzle = float(np.sum(q_mean * dA))

            gas_side['nozzle_wetted_area'] = nozzle_area
            gas_side['nozzle_heat_rate'] = q_nozzle
            gas_side['surface_area'] = float(barrel_area + injector_area
                                             + nozzle_area)
            gas_side['total_heat_rate'] = float(q_barrel + q_nozzle)
            gas_side['wetted_integral_available'] = True
            gas_side['wetted_integral_stations'] = int(x.size)
            # ISLAK YÜZEYİN GEOMETRİ KÜNYESİ (v2.6.27, D2 zinciri denetimi).
            # Bu integral konturun TAMAMI üzerinde alınır, yani boğaz
            # skalerlerinden farklı olarak ıraksak boya DOĞRUDAN duyarlıdır.
            # Çağıran çıkış çapını / genleşme oranını geçirmezse örnekleyici
            # kendi JENERİK çıkış çapına düşer ve buradan yayımlanan alan bu
            # motorun lülesine ait olmaz. Sayı susturulmaz (çağıran katman
            # düzeltilmeli) ama kaynağı ADIYLA yanına yazılır.
            kontur_kunye = profile.get('contour_basis') or {}
            gas_side['wetted_integral_contour_basis'] = {
                'source': kontur_kunye.get('source'),
                'exit_diameter_source': kontur_kunye.get(
                    'exit_diameter_source'),
                'nozzle_type_source': kontur_kunye.get('nozzle_type_source'),
                'generic_defaults_used': list(
                    kontur_kunye.get('generic_defaults_used') or []),
            }
        except Exception as exc:  # geometri/kontur yoksa dürüst yedek
            gas_side['wetted_integral_available'] = False
            gas_side['wetted_integral_error'] = str(exc)
            gas_side.setdefault('warnings', []).append(_mk_warning(
                'warn.thermal.wetted_integral_unavailable', 'warning'))
        return gas_side

    def _analyze_wall_temperature(self, heat_flux: float, thickness: float,
                                mat_props: Dict, ambient_temp: float, h_coolant: float,
                                chamber_temperature: Optional[float] = None,
                                gas_side: Optional[Dict] = None) -> Dict:
        """
        Analyze wall temperature distribution.

        The hot-side (inner) wall temperature is taken from the gas-side energy
        balance when available; the conduction and coolant-side drops are then
        back-computed from the flux that is CONSISTENT WITH THAT BALANCE.

        FIX (v2.5.2, thermal -3115 K bug): the conduction drop used to be
        computed from the conservative DESIGN flux (the throat load evaluated
        at a reference cooled wall, ~35 MW/m^2 for a 60 bar chamber), while the
        inner wall temperature came from the equilibrium solution. Those two
        quantities belong to different thermal states, so subtracting one from
        the other drove the outer wall far below ambient (a 60 bar / 8 mm steel
        case returned -3076 K). The equilibrium wall temperature already
        satisfies

            q_eq = (T_inner - T_ambient) / (R_conduction + R_coolant)

        so the physically consistent drops are q_eq * R_conduction and
        q_eq * R_coolant, which always leave
        T_ambient <= T_outer <= T_inner. The conservative design flux is
        untouched and still reported as throat/chamber heat flux by
        _analyze_gas_side_heat_transfer.
        """
        k = mat_props['thermal_conductivity']
        warnings_list: List[str] = []

        # Thermal resistance analysis [m^2*K/W]
        R_conduction = thickness / k
        R_convection = 1.0 / h_coolant
        R_total = R_conduction + R_convection

        design_heat_flux = heat_flux  # W/m^2 (conservative cooling-sizing load)

        if gas_side is not None and 'estimated_wall_temperature' in gas_side:
            # Inner hot wall from the surface energy balance; the through-wall
            # flux is the one that balance actually transports.
            T_inner = float(gas_side['estimated_wall_temperature'])
            equilibrium_heat_flux = (
                (T_inner - ambient_temp) / R_total if R_total > 0 else 0.0)
            equilibrium_heat_flux = max(equilibrium_heat_flux, 0.0)
            delta_T_conduction = equilibrium_heat_flux * R_conduction
            delta_T_convection = equilibrium_heat_flux * R_convection
            T_outer = T_inner - delta_T_conduction
        else:
            # Backward-compatible resistance-network estimate (design flux).
            equilibrium_heat_flux = design_heat_flux
            delta_T_conduction = design_heat_flux * R_conduction
            delta_T_convection = design_heat_flux * R_convection
            T_inner = ambient_temp + design_heat_flux * R_total
            T_outer = ambient_temp + design_heat_flux * R_convection

        # Safety clamp: the outer wall can never be colder than the coolant /
        # ambient sink, nor hotter than the hot face.
        T_outer_raw = T_outer
        lower_bound = min(ambient_temp, T_inner)
        T_outer = min(max(T_outer, lower_bound), T_inner)
        if abs(T_outer - T_outer_raw) > 1e-6:
            warnings_list.append(_mk_warning(
                'warn.thermal.outer_wall_clamped', 'warning',
                T_outer_raw=round(T_outer_raw), lower=round(lower_bound),
                upper=round(T_inner), T_outer=round(T_outer)))
            delta_T_conduction = T_inner - T_outer

        T_average = (T_inner + T_outer) / 2.0

        # Temperature gradient through the wall
        temp_gradient = delta_T_conduction / thickness if thickness > 0 else 0.0

        return {
            'inner_temperature': T_inner,
            'outer_temperature': T_outer,
            'average_temperature': T_average,
            'max_temperature': T_inner,
            'temperature_gradient': temp_gradient,
            # Flux actually conducted through the wall at equilibrium (W/m^2);
            # the conservative design load is reported separately.
            'equilibrium_heat_flux': equilibrium_heat_flux,
            'design_heat_flux': design_heat_flux,
            'thermal_resistance': {
                'conduction': R_conduction,
                'convection': R_convection,
                'total': R_total
            },
            'temperature_drops': {
                'conduction': delta_T_conduction,
                'convection': delta_T_convection
            },
            'warnings': warnings_list
        }

    # Soğutucu tarafı tasarım sıcaklık farkları [K] — TEK TANIM NOKTASI
    # modül düzeyindeki ``COOLING_DESIGN_DELTA_T``tır (ÖH Z5S / PK5,
    # P4B1-06). Sınıf niteliği ESKİ ADIN takma adı olarak korunur; iki
    # kopya değil, aynı sözlüktür.
    _COOLING_DESIGN_DELTA_T = COOLING_DESIGN_DELTA_T
    # Isı yutucu (heat-sink) tasarım sıcaklık artışı [K] — YALNIZ malzeme
    # kaydında sıcaklık sınırı bulunamazsa kullanılan yedek. v2.6.26'ya kadar
    # bu değer her malzeme ve her ortam sıcaklığı için SABİTTİ; oysa
    # m = Q/(cp·ΔT) ifadesinde ΔT paydadadır, yani ısı yutucu kütlesi bu
    # sayıyla ters orantılıdır. Aynı satırdaki cp çoktan malzeme kaydından
    # okunuyordu (cp_source='material_record') — fonksiyon malzemeye duyarlı
    # hâle getirilmiş, yalnız izin verilen sıcaklık artışı dışarıda kalmıştı.
    _HEAT_SINK_DELTA_T = 200.0

    def _heat_sink_delta_T(self, mat_props: Optional[Dict],
                           ambient_temp: float) -> Tuple[float, float, str]:
        """İzin verilen ısı yutucu sıcaklık artışı ΔT [K] + sınır + gerekçe.

        Isı yutucu (heat-sink) hazne, yanma boyunca soğurduğu ısıyla ısınır;
        boyutlandırma ölçütü cidarın malzemenin izin verilen sıcaklığını
        aşmamasıdır (Huzel & Huang, NASA SP-125, Böl. 4 — ısı yutucu hazne
        boyutlandırması). Dolayısıyla izin verilen artış
            ΔT = T_sınır − T_başlangıç
        olup, T_sınır merkezi malzeme kaydından gelir. İki aday alan vardır
        (materials_db): ``max_service_temp`` (kısa süreli YAPISAL servis
        sınırı) ve ``allowable_temperature`` (termal emniyet sınırı). Daha
        KONSERVATİF (küçük) olan seçilir; ikisi de yoksa beyan edilen 200 K
        yedeği kullanılır ve bu durum çıktıda bildirilir.
        """
        limits = []
        if mat_props:
            # F-01/M2: merdivenin izin basamağı = min(max_service_temp,
            # allowable_temperature) — eskiden burada satır içi min alınıyordu;
            # sayı BİT-AYNI, kaynak artık tek fonksiyon.
            _tl = temperature_limits(mat_props)
            if _tl['allowable_K'] is not None:
                limits.append((float(_tl['allowable_K']),
                               _tl['source_fields']['allowable_K']))
        t_start = float(ambient_temp) if ambient_temp else 293.15
        if not limits:
            return (self._HEAT_SINK_DELTA_T, float('nan'),
                    'declared default (no temperature limit in material record)')
        limit, key = min(limits)
        delta_t = limit - t_start
        if delta_t <= 0.0:
            # Ortam sıcaklığı malzeme sınırının üstünde: ısı yutucu tasarımı
            # anlamsızdır. Sayı uydurmak yerine yedek beyan edilir.
            return (self._HEAT_SINK_DELTA_T, limit,
                    f'declared default ({key} = {limit:.0f} K is at or below '
                    f'the initial temperature {t_start:.1f} K)')
        return (float(delta_t), limit,
                f'material record {key} ({limit:.0f} K) minus initial '
                f'temperature ({t_start:.1f} K)')

    def _analyze_cooling_requirements(self, heat_rate: float, burn_time: float,
                                    motor_data: Dict, cooling_type: str,
                                    mat_props: Optional[Dict] = None,
                                    ambient_temp: float = 293.15) -> Dict:
        """Analyze cooling requirements.

        DÜZELTME (v2.6.2, fizik denetimi F037) — iki ayrı kusur:

        (1) YANLIŞ KATSAYI: rejeneratif dal gereken soğutma alanını
            A = Q/(2000*100) ile hesaplıyordu. 2000 W/m^2/K değeri eski
            sürümden kalmıştı; modülün MERKEZİ soğutucu-tarafı kaynağı
            _coolant_side_coefficient ile çözülür. Sonuç: kullanıcıya
            gösterilen "gereken soğutma alanı" tam 10x FAZLA raporlanıyordu.
            Artık üç dal da h'yi _coolant_side_coefficient'ten alır —
            tek kaynak kuralı. ÖH D31 / P12bB4-06: o işlev artık kanal
            girdileri verildiğinde Dittus-Boelter ile HESAPLIYOR, girdiler
            yoksa COOLANT_SIDE_DECLARED_TYPICAL bandını 'not_modelled'
            künyesiyle döndürüyor; bu blok h'nin kökenini
            coolant_side_coefficient_method alanıyla yayımlar.

        (2) MALZEMEDEN BAĞIMSIZ cp: ısı yutucu kütlesi
            m = E/(460*200) ile, yani SEÇİLEN MALZEME ne olursa olsun
            çelik cp=460 J/kg/K varsayımıyla hesaplanıyordu. Bakır (385)
            ve alüminyum (896) için 2.3x'e varan hata. Artık cp seçilen
            malzeme kaydından (materials_db 'specific_heat') okunur.

        Args:
            heat_rate: Toplam ısı yükü [W] (ıslak yüzey integrali, F038).
            burn_time: Yanma süresi [s].
            motor_data: Motor sözlüğü (coolant_side_coefficient geçilebilir).
            cooling_type: 'natural' | 'forced' | 'regenerative'.
            mat_props: Seçilen malzeme kaydı (specific_heat için). None ise
                çelik varsayılanına düşülür ve bu çıktıda bildirilir.
        """

        # Total heat energy
        total_heat_energy = heat_rate * burn_time  # J

        # Cooling capacity requirements — h TEK merkezi kaynaktan.
        _cool_res = self._coolant_side_resolution(
            motor_data, cooling_type, coolant_bulk_temp=ambient_temp)
        h_cool = _cool_res['value']
        delta_t = COOLING_DESIGN_DELTA_T.get(cooling_type)
        # ÖH Z5S / PK5 (P4B1-06) — FAIL-CLOSED: tanınmayan soğutma tipinde
        # gerekli soğutma alanı HESAPLANAMAZ. Eskiden burada 0,0 m²
        # yayımlanıyordu ve panel "0,00 m²" stat kartını çiziyordu; 3370 kW
        # yükte "gereken soğutma alanı sıfır" cümlesi, hesabın yapılmadığı
        # bilgisini "hiç soğutma gerekmiyor" hükmüne çeviriyordu. Sıfır bir
        # ÖLÇÜM DEĞİLDİR: alan yayımlanmaz, yerine ADIYLA gerekçe konur.
        cooling_type_recognized = delta_t is not None
        cooling_area_withheld_because = None
        if not cooling_type_recognized or h_cool <= 0.0:
            required_surface_area = None
            cooling_area_withheld_because = (
                "The required cooling area is A = Q / (h * dT_design). This "
                f"model has no design temperature difference for "
                f"cooling_type={cooling_type!r}; supported types are "
                + ', '.join(SUPPORTED_COOLING_TYPES)
                + ". No area is published, because zero area would read as "
                  "'no cooling needed'.")
        else:
            required_surface_area = heat_rate / (h_cool * delta_t)  # m^2

        # --- SOĞUTUCU DEBİSİ (ÖH D15: P4B1-04 + P4B1-05) -----------------
        #
        # ESKİ KOD (ölçüldü, 60 bar / 3400 K / Q = 2121,6 kW):
        #     forced:       mdot = Q / (1000 * 20)   -> 106,08 kg/s
        #     regenerative: mdot = Q / (4180 * 50)   -> 10,15 kg/s
        # İki kusur birlikte:
        #   (P4B1-04) Aynı yanıtta İKİ tasarım ΔT'si vardı: yayımlanan
        #     ``design_delta_T_K`` = COOLING_DESIGN_DELTA_T[tip] = 100 K
        #     iken debi 20 K (zorlanmış) / 50 K (rejeneratif) ile
        #     hesaplanıyordu. ``required_cooling_area`` GERÇEKTEN 100 K ile
        #     hesaplandığı için alan 2×/5× küçük (GÜVENSİZ yön), debi ise
        #     2×/5× büyük çıkıyordu. ΔT artık TEK KAYNAKTAN okunur.
        #   (P4B1-05) cp gömülüydü ve rejeneratif dalda SUYUN cp'siydi
        #     (4180 J/kg/K). Rejeneratif soğutucu motorun kendi propelanıdır
        #     (RP-1 ~2000, LH2 ~14300); su varsayımı ölçülen vakada debiyi
        #     propelan debisinin %127'sine çıkarıyor, üstelik yanıtta ne
        #     akışkan adı ne cp ne de künye alanı bulunuyordu (aynı sözlükte
        #     heat_sink_* kardeşlerinin ÜÇÜ de künyeliyken).
        #
        # FAIL-CLOSED: cp bilinmiyorsa debi YAYIMLANMAZ; hangi alanın
        # eksik olduğu adıyla söylenir. Sıfır bir ölçüm değildir.
        coolant_cp, coolant_cp_source, coolant_fluid = \
            self._coolant_specific_heat(motor_data, cooling_type)
        coolant_flow_withheld_because = None
        if cooling_type == 'natural':
            # Doğal taşınımda dolaşan bir soğutucu YOKTUR: sıfır burada bir
            # ölçümdür, eksik hesabın yerini tutan bir sayı değil.
            coolant_flow_rate = 0.0
        elif not cooling_type_recognized:
            coolant_flow_rate = None
            coolant_flow_withheld_because = (
                "The coolant mass flow is mdot = Q / (cp * dT_design). This "
                f"model has no design temperature difference for "
                f"cooling_type={cooling_type!r}; supported types are "
                + ', '.join(SUPPORTED_COOLING_TYPES) + '.')
        elif coolant_cp is None:
            coolant_flow_rate = None
            coolant_flow_withheld_because = (
                "The coolant mass flow is mdot = Q / (cp * dT_design) and "
                "this model does not know the coolant's specific heat for "
                f"cooling_type={cooling_type!r}: in regenerative cooling the "
                "coolant is the ENGINE'S OWN PROPELLANT (RP-1 ~2000, LH2 "
                "~14300, methane ~3500 J/kg/K), which this analyzer is not "
                "given. Earlier versions assumed WATER (4180 J/kg/K) here "
                "and published a flow rate larger than the propellant flow "
                f"itself. Supply {COOLANT_CP_INPUT_FIELD!r} [J/kg/K] to get "
                "the number; nothing is substituted.")
        else:
            coolant_flow_rate = heat_rate / (coolant_cp * delta_t)  # kg/s

        # Heat sink analysis (for passive cooling) — SEÇİLEN malzemenin cp'si.
        cp_wall = 460.0  # J/kg/K (çelik yedeği; mat_props verilmezse)
        cp_source = 'steel_default'
        if mat_props:
            try:
                cp_candidate = float(mat_props.get('specific_heat', 0.0))
                if cp_candidate > 0.0:
                    cp_wall = cp_candidate
                    cp_source = 'material_record'
            except (TypeError, ValueError):
                pass
        # ΔT artık seçilen malzemenin sıcaklık sınırından ve gerçek başlangıç
        # (ortam) sıcaklığından gelir — bkz. _heat_sink_delta_T.
        heat_sink_delta_t, heat_sink_limit, heat_sink_basis = \
            self._heat_sink_delta_T(mat_props, ambient_temp)
        heat_sink_mass = total_heat_energy / (cp_wall * heat_sink_delta_t)

        return {
            'total_heat_energy': total_heat_energy / 1e6,  # MJ
            'peak_heat_rate': heat_rate / 1000,  # kW
            'required_cooling_area': required_surface_area,  # m²
            'coolant_flow_rate': coolant_flow_rate,  # kg/s
            'heat_sink_mass': heat_sink_mass,  # kg
            # Teşhis (additive): boyutlandırmada kullanılan kabuller açıkta.
            'coolant_side_coefficient': h_cool,           # W/m^2/K
            # P12bB4-06: gereken soğutma alanı bu h ile bölünüyor; h'nin
            # hesap mı yoksa beyan edilen bant mı olduğu artık okunabilir.
            'coolant_side_coefficient_method': _cool_res['method'],
            'coolant_side_coefficient_source': _cool_res['source'],
            'design_delta_T_K': delta_t,                  # K (mühendislik kabulü)
            # ÖH D15 (P4B1-04): debinin KULLANDIĞI ΔT ile yayımlanan ΔT
            # aynı sayıdır — yankı, ikinci bir kabul değil. Alan adı
            # ayrıdır ki tüketici "hangi ΔT ile bölündü?" sorusunu
            # ters çözüm yapmadan sorabilsin.
            'coolant_delta_T_K': delta_t,                 # K
            # ÖH D15 (P4B1-05): soğutucunun kimliği ve cp'si künyeli.
            'coolant_fluid': coolant_fluid,
            'coolant_specific_heat_J_kgK': coolant_cp,    # J/kg/K
            'coolant_specific_heat_source': coolant_cp_source,
            **({'coolant_flow_rate_withheld_because':
                coolant_flow_withheld_because}
               if coolant_flow_withheld_because else {}),
            'heat_sink_specific_heat_J_kgK': cp_wall,     # J/kg/K
            'heat_sink_specific_heat_source': cp_source,
            'heat_sink_delta_T_K': heat_sink_delta_t,
            'heat_sink_delta_T_basis': heat_sink_basis,
            'heat_sink_temperature_limit_K': heat_sink_limit,
            'heat_sink_initial_temperature_K': float(ambient_temp),
            # v2.6.26 — SABİT ÇIKTI BEYANI: ısı kuyusu ΔT'sinin ALT ucu, yani
            # girdinin kendisi. Hesap değil, yankı.
            'heat_sink_initial_temperature_basis': (
                'starting (soak) temperature of the heat-sink mass: the '
                'ambient_temp INPUT of this analysis, echoed back, not a '
                'computed temperature. It is the lower end of '
                'heat_sink_delta_T_K (limit minus initial); the module '
                'default 293.15 K applies when the caller supplies no '
                'ambient temperature.'),
            # ÖH Z5S / PK5 (P4B1-06): tipin TANINIP tanınmadığı adıyla söylenir;
            # yankı alanı (design_parameters.cooling_type) kullanıcının dizesini
            # geri okuduğu için "seçtiğim tip hesaba girdi" yanılsaması bu
            # bayrak olmadan kırılamıyordu.
            'cooling_type_recognized': cooling_type_recognized,
            'supported_cooling_types': list(SUPPORTED_COOLING_TYPES),
            **({'required_cooling_area_withheld_because':
                cooling_area_withheld_because}
               if cooling_area_withheld_because else {}),
            'cooling_efficiency': self._calculate_cooling_efficiency(cooling_type),
            # ÖH Z5S / PK5 (P4B1-20): künye asimetrisi kapandı. Aynı sözlükteki
            # üç kardeş alan (heat_sink_delta_T_basis,
            # heat_sink_initial_temperature_basis,
            # heat_sink_specific_heat_source) künye taşırken bu alanın eşi
            # yoktu; arayüz ise TEK sayıyı "Cooling Effectiveness" olarak
            # çiziyordu. Değerin ne olduğu (ve NE OLMADIĞI) artık yazılı.
            'cooling_efficiency_basis': self._cooling_efficiency_basis(
                cooling_type),
            'cooling_efficiency_source': COOLING_EFFICIENCY_SOURCE,
            'recommendations': self._get_cooling_recommendations(cooling_type, heat_rate)
        }

    @staticmethod
    def _coolant_specific_heat(motor_data: Optional[Dict],
                               cooling_type: str
                               ) -> Tuple[Optional[float], Optional[str],
                                          Optional[str]]:
        """Soğutucunun cp'si [J/kg/K], kaynak künyesi ve akışkan adı.

        Sıra: (1) çağıranın açıkça verdiği ``coolant_specific_heat_J_kgK``,
        (2) akışkan kimliği MODELCE bilinen soğutma tipleri
        (``COOLANT_SPECIFIC_HEAT_J_KGK``; bugün yalnız zorlanmış hava).
        Hiçbiri yoksa ``(None, None, None)`` — çağıran fail-closed davranır.

        Rejeneratif dalda kayıt YOKTUR: soğutucu motorun propelanıdır ve bu
        modül propelan kimliğini almaz. Bir sayı uydurmak (v2.6.26'ya kadar
        SUYUN 4180 J/kg/K'si) debiyi doğrudan ölçekler.
        """
        md = motor_data or {}
        ham = md.get(COOLANT_CP_INPUT_FIELD)
        if ham not in (None, ''):
            try:
                deger = float(ham)
            except (TypeError, ValueError):
                deger = None
            if deger is not None and np.isfinite(deger) and deger > 0.0:
                ad = md.get('coolant_fluid') or md.get('fuel_type')
                return (deger, 'caller_supplied',
                        str(ad) if ad else 'caller_supplied_coolant')
        cp = COOLANT_SPECIFIC_HEAT_J_KGK.get(cooling_type)
        if cp is not None:
            return (float(cp), COOLANT_SPECIFIC_HEAT_SOURCE.get(cooling_type),
                    'air' if cooling_type == 'forced' else cooling_type)
        if cooling_type == 'natural':
            return (None, None, 'ambient air (no circulated coolant)')
        return (None, None, None)

    def _analyze_thermal_safety(self, max_temp: float, mat_props: Dict,
                              thickness: float, pressure: float,
                              wall_delta_T: Optional[float] = None,
                              chamber_radius_m: Optional[float] = None
                              ) -> Dict:
        """Analyze thermal safety margins.

        ÖH ONARIMI (defter P4B1-15) — ``pressure`` ARTIK TÜKETİLİYOR.
        Ölçüldü (2026-08-27, ``ast``): çağıran hazne basıncını dördüncü
        konumlu argüman olarak geçiriyor, imza onu ``pressure`` adıyla
        alıyor, gövde ise adı bir kez bile OKUMUYORDU — buna rağmen
        yayımlanan alanın adı ``stress_safety_factor`` idi, yani AYNI
        cidarın taşıdığı çember (basınç) gerilmesi hiç girmeden "gerilme
        emniyet katsayısı" deniyordu. Makas basınçla açılıyordu (steel_4130,
        5 mm cidar, D=100 mm): Pc 20 bar'da %1,1 → 500 bar'da %15,5 →
        2000 bar'da %59,7 İYİMSER.

        Artık ince-cidar çember gerilmesi sigma_hoop = p*r/t (Barlow /
        Roark 9th ed. Böl. 13) termal gradyan gerilmesine LİNEER SÜPERPOZE
        edilir ve ``stress_safety_factor`` bu BİRLEŞİK gerilmeden türetilir.
        Yarıçap verilmediğinde çember terimi UYDURULMAZ: katsayı yalnız
        termal kalır ve ``stress_safety_factor_basis`` künyesi bunu ADIYLA
        söyler (fail-closed beyan; kardeş desen aynı modülde:
        ``heat_sink_initial_temperature_basis``).

        FIX (v2.5.2): the thermal stress used to be built from hardcoded steel
        constants (alpha=12e-6, E=200e9, yield=250e6) AND from the fully
        restrained form E*alpha*(T_wall - 293). Both were wrong:

          - a copper or Inconel chamber was still evaluated as mild steel;
          - the fully restrained form assumes the whole wall is prevented from
            expanding, which returns absurd stresses (GPa-level) for any hot
            chamber and pinned every design at a safety factor near zero.

        The stress reported here is now the classical through-wall thermal
        gradient stress of a thin cylindrical shell

            sigma_th = E * alpha * dT_wall / (2 * (1 - nu))

        with dT_wall = T_inner - T_outer taken from the wall analysis, and all
        properties resolved from the selected material record
        (hrma.data.materials_db). References: Timoshenko & Goodier, "Theory of
        Elasticity"; Boley & Weiner, "Theory of Thermal Stresses" Ch. 10-11;
        Roark's Formulas for Stress & Strain 9th ed. Ch. 16.
        """

        # F-01/M2: sıcaklık emniyet katsayısı merdivenin İZİN basamağına
        # göre (allowable_K = min(allowable_temperature, max_service_temp));
        # steel_4130'da 1000 → 811 K (ÖNEMLİ, önce/sonra tablosu).
        _tl = temperature_limits(mat_props)
        allowable_temp = (float(_tl['allowable_K']) if _tl['allowable_K']
                          is not None else float(mat_props['allowable_temperature']))
        melting_point = (float(_tl['melting_K']) if _tl['melting_K']
                         is not None else float(mat_props['melting_point']))

        # Safety factors (guard against division by zero / negative temps)
        max_temp_safe = max(max_temp, 1.0)
        temp_safety_factor = allowable_temp / max_temp_safe
        melting_safety_factor = melting_point / max_temp_safe

        # --- Material properties of the SELECTED material (no steel hardcode) ---
        props = self._resolve_mechanical_properties(mat_props)
        thermal_expansion = props['thermal_expansion']   # 1/K
        elastic_modulus = props['elastic_modulus']       # Pa
        poisson_ratio = props['poisson_ratio']           # -
        yield_strength = props['yield_strength']         # Pa

        # Through-wall gradient. If the wall analysis did not supply one, fall
        # back to the hot-face rise above ambient (conservative upper bound).
        if wall_delta_T is None:
            wall_delta_T = max_temp - 293.15
        delta_T_wall = max(float(wall_delta_T), 0.0)

        thermal_stress = (elastic_modulus * thermal_expansion * delta_T_wall
                          / (2.0 * (1.0 - poisson_ratio)))

        # --- ÖH P4B1-15: ÇEMBER (BASINÇ) TERİMİ -------------------------
        # BİRİM ÇAPASI (ölçüldü): `analyze_heat_transfer` motor sözlüğünden
        # bar okuyup ``* 1e5`` ile PASCAL'a çevirir (:840) ve bu argümanı
        # dördüncü konumda PASCAL olarak geçirir. Birim körlüğü bu
        # kampanyanın tescilli tuzağıdır; sayı burada Pa kabul edilir ve
        # künyeye bar olarak da yazılır.
        try:
            pressure_Pa = float(pressure)
        except (TypeError, ValueError):
            pressure_Pa = 0.0
        pressure_bar = pressure_Pa / 1e5
        radius_m = None
        if chamber_radius_m is not None:
            try:
                radius_m = float(chamber_radius_m)
            except (TypeError, ValueError):
                radius_m = None
        thickness_m = float(thickness) if thickness else 0.0

        hoop_stress = 0.0
        if (radius_m is not None and radius_m > 0.0 and thickness_m > 0.0
                and pressure_Pa > 0.0):
            hoop_stress = pressure_Pa * radius_m / thickness_m
            stress_scope = 'thermal_gradient_plus_pressure_hoop'
            stress_basis = (
                'combined wall stress: thermal gradient '
                'E*alpha*dT/(2*(1-nu)) [Timoshenko/Boley-Weiner/Roark Ch.16] '
                'linearly superposed with the thin-wall pressure hoop '
                'sigma = p*r/t [Barlow / Roark 9th ed. Ch.13], evaluated at '
                'p = %.4g bar, r = %.5g m, t = %.5g m. The chamber pressure '
                'this analysis receives IS consumed here; a thermal-only '
                'factor would be optimistic and its name would over-claim.'
                % (pressure_bar, radius_m, thickness_m))
        else:
            stress_scope = 'thermal_gradient_only'
            _eksik = []
            if radius_m is None or radius_m <= 0.0:
                _eksik.append('chamber_radius_m')
            if thickness_m <= 0.0:
                _eksik.append('thickness')
            if pressure_Pa <= 0.0:
                _eksik.append('pressure')
            stress_basis = (
                'THERMAL GRADIENT ONLY: the pressure hoop term sigma = p*r/t '
                'could not be formed because %s was not supplied, so it is '
                'NOT invented. This factor therefore covers only the '
                'through-wall thermal gradient and is OPTIMISTIC for the '
                'same wall under pressure — read it together with the '
                'structural analysis hoop safety factor.'
                % ', '.join(_eksik))

        combined_stress = thermal_stress + hoop_stress
        stress_safety_factor = (yield_strength / combined_stress
                                if combined_stress > 0 else 1e6)

        # --- Risk hükmü (ÖH D15, P4B1-07) --------------------------------
        #
        # ESKİ KOD hükmü YALNIZ ``temp_safety_factor``tan türetiyordu;
        # ``melting_safety_factor`` ve ``stress_safety_factor`` aynı sözlükte
        # YAYIMLANIYOR ama hükme HİÇ girmiyordu. ÖLÇÜLDÜ (ss_316, cidar
        # 5,0 mm, Tc = 1200 K, Pc = 2 bar, D_t = 200 mm, D_ch = 300 mm):
        #   temperature_safety_factor = 2,0388  -> hüküm LOW
        #   stress_safety_factor      = 0,5506  (cidar akmanın 1,82 katında)
        #   melting_safety_factor     = 3,1238
        # Yani akma dayanımının 1,8 katı gerilme altındaki cidara "DÜŞÜK
        # RİSK" rozeti basılıyordu; tek işaret ``severity='warning'`` bir
        # uyarıydı ve safety_panel.js rozet RENGİNİ risk_level'dan alıyor.
        #
        # Hüküm artık ÜÇ katsayının EN KÖTÜSÜNÜ alır (fail-closed): bir
        # cidar hangi mekanizmadan giderse gitsin gider. Eşikler sıcaklık
        # dalında AYNEN korundu (1,5 / 2,0) — sağlıklı motorun hükmü
        # değişmez; erime ve gerilme dalları aynı eşiklerle eklendi
        # (SF < 1 = dayanım aşıldı, SF < 1,5 kritik, < 2,0 marjinal).
        # Kardeş modüldeki doğru desen: tests/test_scofield_kati.py:387.
        _SIRA = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}

        def _seviye(sf):
            if sf is None or not np.isfinite(sf):
                return 'HIGH'
            if sf < 1.5:
                return 'HIGH'
            if sf < 2.0:
                return 'MEDIUM'
            return 'LOW'

        risk_drivers = {
            'temperature_safety_factor': _seviye(temp_safety_factor),
            'melting_safety_factor': _seviye(melting_safety_factor),
            'stress_safety_factor': _seviye(stress_safety_factor),
        }
        risk_level = max(risk_drivers.values(), key=lambda s: _SIRA[s])
        risk_governing = [ad for ad, sv in risk_drivers.items()
                          if sv == risk_level]

        warnings_list = []
        if temp_safety_factor < 1.0:
            warnings_list.append(_mk_warning(
                'warn.thermal.temp_exceeds_allowable', 'critical'))
        # DÜZELTME (v2.6.2, fizik denetimi F011): cidar erime noktasının
        # ÜSTÜNDEYKEN tek uyarı 'erimeye yaklaşıyor' (warning) idi. Erime
        # aşıldığında metin de seviye de yanlıştı; artık ayrı kritik kod.
        if melting_safety_factor < 1.0:
            warnings_list.append(_mk_warning(
                'warn.thermal.max_temp_exceeds_melting', 'critical',
                T_max=round(max_temp), melting=round(melting_point)))
        elif melting_safety_factor < 2.0:
            warnings_list.append(_mk_warning(
                'warn.thermal.approaches_melting', 'warning'))
        if stress_safety_factor < 2.0:
            warnings_list.append(_mk_warning(
                'warn.thermal.high_thermal_stress', 'warning'))

        return {
            'temperature_safety_factor': temp_safety_factor,
            'temperature_safety_factor_basis': (
                'allowable_K / T_max with allowable_K = '
                'materials_db.temperature_limits(rec).allowable_K = '
                'min(allowable_temperature, max_service_temp) (F-01/M2 single '
                'ladder); before this change the bare allowable_temperature '
                'record was used'),
            'threshold_ladder': {
                'allowable_K': allowable_temp,
                'service_K': _tl['service_K'],
                'melting_K': melting_point,
                # V3 KK (§28-31): hükmü veren aday ADIYLA (tek kaynak).
                **allowable_governance(_tl),
            },
            'melting_safety_factor': melting_safety_factor,
            'stress_safety_factor': stress_safety_factor,
            # ÖH P4B1-15 — katsayının KAPSAMI adıyla yayımlanır.
            'stress_safety_factor_scope': stress_scope,
            'stress_safety_factor_basis': stress_basis,
            'pressure_hoop_stress_MPa': hoop_stress / 1e6,
            'combined_stress_MPa': combined_stress / 1e6,
            'stress_chamber_pressure_bar': pressure_bar,
            'stress_chamber_radius_m': radius_m,
            'thermal_stress': thermal_stress / 1e6,  # MPa
            'thermal_stress_delta_T_K': delta_T_wall,
            'thermal_stress_properties': {
                'elastic_modulus_GPa': elastic_modulus / 1e9,
                'thermal_expansion_per_K': thermal_expansion,
                'poisson_ratio': poisson_ratio,
                'yield_strength_MPa': yield_strength / 1e6,
            },
            'risk_level': risk_level,
            # ÖH D15 (P4B1-07): hükmün HANGİ katsayıdan çıktığı okunabilir.
            'risk_level_drivers': risk_drivers,
            'risk_level_governed_by': risk_governing,
            'risk_level_basis': (
                'The verdict is the WORST of the three published safety '
                'factors (temperature, melting, combined thermal+pressure '
                'stress), each graded with the same thresholds: '
                'SF < 1.5 -> HIGH, SF < 2.0 -> MEDIUM, otherwise LOW. Until '
                'v2.6.26 only the temperature factor was read, so a wall at '
                '1.8x its yield stress could be published as LOW risk.'),
            'warnings': warnings_list,
            'recommendations': self._get_safety_recommendations(temp_safety_factor, thickness)
        }

    @staticmethod
    def _resolve_mechanical_properties(mat_props: Dict) -> Dict:
        """Return E, alpha, nu and yield strength of the selected material.

        The material records handed to this analyzer already come from the
        central database (hrma.data.materials_db.build_materials_view), so the
        mechanical fields are normally present. If a caller passes a partial
        record, the values are re-read from materials_db.get_material() using
        the record name before any generic fallback is used.
        """
        required = ('elastic_modulus', 'thermal_expansion',
                    'poisson_ratio', 'yield_strength')
        if all(mat_props.get(f) for f in required):
            return {f: float(mat_props[f]) for f in required}

        record: Dict = {}
        name = mat_props.get('name', '')
        if name:
            try:
                from hrma.data.materials_db import get_material
                record = get_material(name)
            except Exception:
                record = {}

        # Generic structural-steel fallback only if nothing else is available.
        defaults = {
            'elastic_modulus': 200e9,
            'thermal_expansion': 12e-6,
            'poisson_ratio': 0.29,
            'yield_strength': 250e6,
        }
        return {
            f: float(mat_props.get(f) or record.get(f) or defaults[f])
            for f in required
        }

    def _calculate_cooling_efficiency(self, cooling_type: str):
        """Soğutma sınıfının BEYANLI sıralama göstergesi (ölçüm değil).

        ÖH Z5S / PK5 (P4B1-20). Değer ısı yükünden, hazne boyundan,
        malzemeden ve cidar kalınlığından TAMAMEN bağımsızdır: soğutma
        sınıfının kendisine iliştirilmiş bir sıralama sayısıdır. Tanınmayan
        tipte artık doğal taşınımın 0,3'üne DÜŞÜLMEZ (o, sorulmamış bir
        soğutmanın sayısını basmak olurdu); ``None`` döner ve gerekçesi
        ``cooling_efficiency_basis``te yazılıdır.
        """
        return COOLING_EFFICIENCY_BY_TYPE.get(cooling_type)

    @staticmethod
    def _cooling_efficiency_basis(cooling_type: str) -> str:
        """``cooling_efficiency`` künyesi — kardeşleriyle aynı sözleşme."""
        if cooling_type in COOLING_EFFICIENCY_BY_TYPE:
            return (
                'CLASS-LEVEL ORDERING FIGURE, not a computed effectiveness: a '
                'fixed number attached to the cooling class '
                f'({cooling_type}) by this module, independent of the heat '
                'load, chamber length, material and wall thickness. It is a '
                'single chamber-average value; this model resolves NO zonal '
                '(chamber / throat / nozzle) effectiveness, so any per-zone '
                'breakdown built from it would be a copy, not a measurement. '
                'Use required_cooling_area and the wall temperatures for '
                'sizing decisions.')
        return (
            'WITHHELD: this module has no effectiveness figure for '
            f'cooling_type={cooling_type!r}; supported types are '
            + ', '.join(SUPPORTED_COOLING_TYPES)
            + '. The natural-convection value is NOT substituted.')

    def _get_cooling_recommendations(self, cooling_type: str, heat_rate: float) -> List[str]:
        """Get cooling system recommendations"""
        recommendations = []

        if heat_rate > 100000:  # > 100 kW
            recommendations.append(_mk_warning(
                'warn.thermal.high_heat_load_regen', 'warning'))
            recommendations.append(_mk_warning(
                'warn.thermal.high_conductivity_material', 'info'))

        if cooling_type == 'natural' and heat_rate > 10000:
            recommendations.append(_mk_warning(
                'warn.thermal.natural_insufficient', 'warning'))

        recommendations.append(_mk_warning(
            'warn.thermal.heat_sink_short_burns', 'info'))
        recommendations.append(_mk_warning(
            'warn.thermal.monitor_wall_temp', 'info'))

        return recommendations

    def _get_safety_recommendations(self, temp_safety_factor: float, thickness: float) -> List[str]:
        """Get thermal safety recommendations"""
        recommendations = []

        if temp_safety_factor < 1.5:
            recommendations.append(_mk_warning(
                'warn.thermal.increase_wall_thickness', 'warning'))
            recommendations.append(_mk_warning(
                'warn.thermal.improve_cooling', 'warning'))
            recommendations.append(_mk_warning(
                'warn.thermal.higher_temp_material', 'warning'))

        if thickness < 0.003:
            recommendations.append(_mk_warning(
                'warn.thermal.min_wall_thickness_3mm', 'info'))

        recommendations.append(_mk_warning(
            'warn.thermal.thermal_barrier_coating', 'info'))
        recommendations.append(_mk_warning(
            'warn.thermal.implement_temp_monitoring', 'info'))

        return recommendations


# ===========================================================================
# V3 KK (KAB devri 5, karar §28-31 tek izin basamağı) — HÜKMÜ VEREN İZİN
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (main fe18664e, /analyze_thermal_safety, örnek katı dock gövdesi):
# 'steel' için aynı yanıtta material_properties.allowable_temperature 1073 K
# ⟷ threshold_ladder.allowable_K 811 K; 'ss_304'te ikisi de 1073 K. İkisi
# AYNI büyüklük DEĞİLDİR: birincisi malzeme kaydının ısıl izin ADAYI, ikincisi
# hükmü veren basamak = min(allowable_temperature, max_service_temp)
# ('steel'de max_service_temp 811 K, yapısal servis sınırı). Kusur, basamağın
# hangi adaydan geldiğini söylememesiydi. Basamak artık adayları ve hükmü
# vereni ADIYLA yayımlar. Tek kaynak materials_db.temperature_limits
# (source_fields); yeni sayı üretilmez, eşik seçimi ve hüküm DEĞİŞMEZ.
# Uzlaştırma bloğunun merdiveni (thermal_paths_reconciliation) sabit şemalı
# sözleşmedir (dalga_plani A2-1) — ona dokunulmaz.
# ===========================================================================
ALLOWABLE_GOVERNANCE_BASIS = (
    'allowable_K is the GOVERNING temperature limit: the lower of the two '
    'candidates in the material record, allowable_temperature (thermal '
    'allowable of the material) and max_service_temp (structural service '
    'temperature). allowable_governed_by names the candidate that gives the '
    'verdict; allowable_candidates_K lists both by name. '
    'material_properties.allowable_temperature is the raw record value of '
    'one candidate, not the verdict limit.')


def allowable_governance(limits: Dict) -> Dict:
    """Hükmü veren izin basamağının aday künyesi (tek tanım noktası).

    ``limits`` = ``materials_db.temperature_limits(rec)`` dönüşü. Dönüş:
    ``allowable_governed_by`` (seçilen alan adı ya da ``None``),
    ``allowable_candidates_K`` ({alan: değer}) ve
    ``allowable_governance_basis``. Aday yoksa ``None`` / boş sözlük döner —
    uydurulmaz (fail-closed).
    """
    src = (limits or {}).get('source_fields') or {}
    adaylar = src.get('allowable_candidates_K') or {}
    return {
        'allowable_governed_by': src.get('allowable_K'),
        'allowable_candidates_K': {str(k): float(v)
                                   for k, v in adaylar.items()},
        'allowable_governance_basis': ALLOWABLE_GOVERNANCE_BASIS,
    }


# ===========================================================================
# ÖH D37 A2-1 termal / F-01 — İKİ TERMAL YOLUN UZLAŞTIRMA BLOĞU (tek şema)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (DK kampanyası T7, docs/scofield/raw/OH/D37/dogrulama/termal/
# rapor.md §b "CW-B3 uzlaştırma"): aynı motorda ana zincir 3368 K, termal FEA
# 2582 K. Çelişki DEĞİL — iki sayı iki ayrı soruya cevap: ana zincir t → ∞
# yüzey enerji dengesidir (dış direnç doğal taşınım 25 W/m²K, T_w T_aw'a
# yapışır); FEA t = t_yanma sonundaki GEÇİCİ tepedir (dış yüzey adyabatik).
# Aynı FEA 30/100/300 s'ye uzatılınca 2891/3224/3361 K → dengeye oturur.
# Sınır koşulu eşdeğerliği de ÖLÇÜLDÜ (A2 termal a1, once/t7_ozet.json
# dis_ortam_h25): 10 s'de dış yüzey h = 25 W/m²K ile adyabatik arasındaki
# tepe farkı 0,012 K (Q_dış/Q_iç = 3,8e-4) — iki yolun farkı sınır
# koşulundan DEĞİL, zaman penceresinden gelir.
# Sözleşme (dalga_plani.md A2-1, faz-c-1 tüketir; alan adları SABİT):
#   {equilibrium_K, fea_peak_K, fea_time_s, gap_K, question_equilibrium,
#    question_fea, threshold_ladder{allowable_K, service_K, melting_K}}
# ===========================================================================
THERMAL_PATHS_QUESTION_EQUILIBRIUM = (
    'steady-state (t -> infinity) surface energy balance at the throat: '
    'q_gas(T_w) = (T_w - T_ambient)/(t_wall/k + 1/h_coolant); independent of '
    'burn time; with no active cooling the wall pins to the recovery '
    'temperature (warn.thermal.wall_pinned_adiabatic)')
THERMAL_PATHS_QUESTION_FEA = (
    'transient peak wall temperature at the end of the burn (t = burn_time) '
    'from the axisymmetric conduction FEA (/api/fea/thermal), outer surface '
    'adiabatic unless outer_ambient is supplied; extending the burn drives '
    'this number towards the equilibrium answer')


def thermal_paths_reconciliation(equilibrium_K=None, fea_peak_K=None,
                                 fea_time_s=None, burn_time_s=None,
                                 mat_props=None, cooling_type=None,
                                 coolant_side_h=None, fea_status=None,
                                 equilibrium_source=None,
                                 fea_source=None) -> Dict:
    """F-01 uzlaştırma bloğu — her iki üretici (ana zincir + FEA köprüsü)
    AYNI fonksiyonla yazar; alan kümesi ikisinde de birebirdir.

    Bilinmeyen yarı ``None`` kalır ve ``fea_status`` / ``equilibrium_source``
    nedenini adıyla söyler; ``gap_K`` yalnız iki sayı da varken ölçülür.
    """
    def _f(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if math.isfinite(f) else None

    eq = _f(equilibrium_K)
    fe = _f(fea_peak_K)
    ladder = None
    if isinstance(mat_props, dict):
        _tl = temperature_limits(mat_props)
        ladder = {'allowable_K': _tl['allowable_K'],
                  'service_K': _tl['service_K'],
                  'melting_K': _tl['melting_K'],
                  '_basis': _tl['basis']}
    return {
        'equilibrium_K': eq,
        'equilibrium_source': (
            equilibrium_source or
            ('heat_transfer_analysis.wall_analysis.max_temperature (= '
             'gas_side_analysis.estimated_wall_temperature, surface energy '
             'balance)' if eq is not None else
             'equilibrium wall temperature not available in this producer')),
        'fea_peak_K': fe,
        'fea_time_s': _f(fea_time_s),
        'fea_status': (fea_status or ('ok' if fe is not None else
                                      'not_run_in_this_chain')),
        'fea_source': (fea_source or
                       ('/api/fea/thermal (hrma.fea.bridge.run_thermal_from_'
                        'motor)' if fe is not None else
                        'the transient FEA is a separate run '
                        '(/api/fea/thermal); its peak is filled by the FEA '
                        'bridge into the same block, never here')),
        'gap_K': (eq - fe) if (eq is not None and fe is not None) else None,
        # Denetçi Ş7: künye SAYI taşımaz — eski metindeki '2582 K' F-02
        # öncesi 16×4 sayısıydı ve yayımlanan tepe değişince bayatladı
        # (ölçüm kanıtı rapor.md §B4'te durur, künyede değil).
        'gap_basis': ('equilibrium_K - fea_peak_K; positive means the '
                      'transient peak has not yet reached the steady-state '
                      'balance within the burn; extending the FEA burn '
                      'drives the gap towards zero (measured on the example '
                      'hybrids)'),
        'burn_time_s': _f(burn_time_s),
        'question_equilibrium': THERMAL_PATHS_QUESTION_EQUILIBRIUM,
        'question_fea': THERMAL_PATHS_QUESTION_FEA,
        'boundary_conditions': {
            'equilibrium_outer': (
                f'coolant/outer side h = {coolant_side_h:g} W/m2K '
                f'({cooling_type})' if _f(coolant_side_h) is not None else
                'coolant/outer side coefficient of the equilibrium chain'),
            'fea_outer': 'adiabatic unless outer_ambient is supplied',
            'equivalence': (
                'measured (A2 termal a1, T7 example, 10 s, 16x4 mesh): outer '
                'h = 25 W/m2K vs adiabatic changes the FEA peak by 0.012 K '
                '(Q_outer/Q_inner = 3.8e-4); the two paths differ by their '
                'time window, not by the outer boundary condition'),
        },
        'threshold_ladder': ladder,
        '_basis': ('F-01 (CW-B3): two thermal paths answer two different '
                   'questions; both are published side by side with the '
                   'single temperature-limit ladder (materials_db.'
                   'temperature_limits). No number is substituted for a path '
                   'that was not run.'),
    }


# ===========================================================================
# ÖH D37 A2-1 termal / F-03 — BARTZ EKSENEL PROFİL GİRDİSİ MOTOR-AGNOSTİK
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (A2 termal a1 once/ozet.json, taban 68c55a27): /api/analysis/
# wall-profile katı ve sıvı /calculate* çıktısıyla çağrılınca 422
# incomplete_wall_profile_input (chamber_pressure, chamber_temperature,
# chamber_diameter, chamber_length, burn_time, throat_diameter ... eksik) —
# alanlar motor sözlüğünde VAR ama başka adla/başka birimle (sıvı düz
# uzunluklar mm, katı düz uzunluklar mm; motor_geometry bloğu SI). Bartz
# kontur boyunca motor-agnostiktir (Pc, c*, γ, MW, D_t, kontur); engel
# fizik değil, girdinin motor tipine göre kurulmasıydı. Aşağıdaki kurucu
# köprünün (hrma.fea.bridge) okuduğu AYNI yolları okur: malzeme ve cidar
# kalınlığı FEA meshinin kullandığı alanlardan gelir (P7B3-30 zincir
# uyuşması), uzunluklar motor_geometry SI bloğundan (birim tahmini yok).
# Bulunamayan çekirdek alan UYDURULMAZ: ``missing`` doludur ve uç 422 verir.
# ===========================================================================
#: Kurucunun okuduğu yollar — motor tipi başına, ÖNCELİK sırasıyla.
#: Değer (yol_demeti, ölçek): ölçek 1e-3 = mm → m.
WALL_PROFILE_MOTOR_PATHS = {
    'hybrid': {
        'chamber_pressure': [(('chamber_pressure',), 1.0)],            # bar
        'chamber_temperature': [(('chamber_temperature',), 1.0)],      # K
        'chamber_diameter': [(('motor_geometry', 'chamber_diameter'), 1.0),
                             (('chamber_diameter',), 1.0)],            # m
        'chamber_length': [(('motor_geometry', 'chamber_length'), 1.0),
                           (('chamber_length',), 1.0)],                # m
        'burn_time': [(('burn_time',), 1.0)],                          # s
        'mdot_total': [(('mdot_total',), 1.0)],                        # kg/s
        'throat_diameter': [(('motor_geometry', 'throat_diameter'), 1.0),
                            (('throat_diameter',), 1.0)],              # m
        'exit_diameter': [(('motor_geometry', 'exit_diameter'), 1.0),
                          (('exit_diameter',), 1.0)],                  # m
        'expansion_ratio': [(('expansion_ratio',), 1.0)],
        'gamma': [(('gamma',), 1.0)],
        'molecular_weight': [(('molecular_weight',), 1.0)],
        'c_star': [(('c_star',), 1.0)],
        'material': [(('structural_analysis', 'design_parameters',
                       'material'), None)],
        'wall_thickness': [(('structural_analysis', 'chamber_analysis',
                             'wall_thickness_used_mm'), 1e-3)],
    },
    'liquid': {
        'chamber_pressure': [(('chamber_pressure',), 1.0)],
        'chamber_temperature': [(('chamber_temperature',), 1.0)],
        'chamber_diameter': [(('motor_geometry', 'chamber_diameter'), 1.0),
                             (('chamber_diameter_mm',), 1e-3)],
        'chamber_length': [(('motor_geometry', 'chamber_length'), 1.0),
                           (('chamber_length_mm',), 1e-3)],
        'burn_time': [(('burn_time',), 1.0)],
        'mdot_total': [(('total_mass_flow',), 1.0)],
        'throat_diameter': [(('motor_geometry', 'throat_diameter'), 1.0),
                            (('throat_diameter_mm',), 1e-3)],
        'exit_diameter': [(('motor_geometry', 'exit_diameter'), 1.0),
                          (('exit_diameter_mm',), 1e-3)],
        'expansion_ratio': [(('expansion_ratio',), 1.0)],
        'gamma': [(('gamma',), 1.0)],
        'molecular_weight': [(('molecular_weight',), 1.0)],
        'c_star': [(('c_star',), 1.0)],
        'material': [(('structural_analysis', 'chamber_structure',
                       'material_key'), None)],
        'wall_thickness': [(('structural_analysis', 'chamber_structure',
                             'wall_thickness'), 1e-3)],
    },
    'solid': {
        'chamber_pressure': [(('chamber_pressure',), 1.0)],
        'chamber_temperature': [(('chamber_temperature',), 1.0)],
        'chamber_diameter': [(('motor_geometry', 'chamber_diameter'), 1.0)],
        'chamber_length': [(('motor_geometry', 'chamber_length'), 1.0)],
        'burn_time': [(('burn_time',), 1.0)],
        'mdot_total': [],                     # katı motor mdot yayımlamaz
        'throat_diameter': [(('motor_geometry', 'throat_diameter'), 1.0)],
        'exit_diameter': [(('motor_geometry', 'exit_diameter'), 1.0)],
        'expansion_ratio': [(('expansion_ratio',), 1.0)],
        # ÖH KİTAP p1b 3. tur (karar §28-47 Ş2-1 / D-F3; §28-36 Ş-7): katı
        # yanıtın üst düzey ``gamma``sı GENLEŞME (denge) gamma'sıdır. Kayıt
        # donmuş oda gamma'sı taşıdığında motorun Bartz zinciri o gazı
        # kullanır ve yanıt çifti ``heat_transfer_analysis.
        # bartz_gas_properties.axial_profile_gas`` altında yayımlar; profil
        # Bartz'ı motorla AYNI (γ, M) çiftiyle kurar (R = R_u/M). Çift
        # yoksa (None: Bartz gazı = genleşme gazı) önceki yol: yayımlanan
        # gamma ve c* özdeşliğinden R. Yalnız gamma'yı yönlendirmek R'yi
        # donmuş gamma'lı c* özdeşliğinden türetirdi (≈ +%3,3) — o yüzden
        # iki alan birlikte okunur.
        'gamma': [(('heat_transfer_analysis', 'bartz_gas_properties',
                    'axial_profile_gas', 'gamma'), 1.0),
                  (('gamma',), 1.0)],
        'molecular_weight': [(('heat_transfer_analysis',
                               'bartz_gas_properties', 'axial_profile_gas',
                               'molecular_weight'), 1.0),
                             (('molecular_weight',), 1.0)],
        'c_star': [(('c_star',), 1.0)],
        'material': [(('structural_analysis', 'case_analysis',
                       'case_material'), None)],
        'wall_thickness': [(('structural_analysis', 'case_analysis',
                             'wall_thickness_mm'), 1e-3)],
    },
}
#: Bartz için zorunlu çekirdek (uç kapısıyla aynı küme + boğaz ölçeği).
WALL_PROFILE_CORE_FIELDS = HEAT_TRANSFER_REQUIRED_FIELDS
WALL_PROFILE_THROAT_SCALE_FIELDS = ('throat_diameter', 'mdot_total')


def _yol_oku(motor: Dict, yol):
    cur = motor
    for k in yol:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


#: ÖH D37 A2-1 termal 7. tur (karar §28-24 §2 b) — gaz özelliği kökeni
#: sınıfları. ``GAS_SOURCE_ASSUMED`` sınıfındaki her alan modül
#: varsayılanıdır: motorun hesap durumundan gelmez.
GAS_SOURCE_SUPPLIED = 'supplied_by_caller'
GAS_SOURCE_DERIVED = 'derived_from_supplied_gas_constant'
GAS_SOURCE_ASSUMED = 'module_default'
GAS_SOURCE_IDEAL = 'ideal_theory_from_gamma_mw_tc'


def axial_profile_gas_basis(motor_data: Dict, gas: Dict,
                            throat: Dict) -> Dict:
    """Eksenel profilin γ / MW / c* kökeni (ÖH D37 A2-1 termal 7. tur).

    Karar §28-24 §2 (A): termal FEA sınır koşulu motorun KENDİ gazından
    kurulur; panel gönderemiyorsa (motor yayımlamıyorsa) sonuç jenerik
    gazla BAŞARI göstermez. Bu işlev hangi alanın çağırandan geldiğini,
    hangisinin modül varsayılanına düştüğünü ADIYLA yazar; sayı ÜRETMEZ,
    yalnız ``_get_gas_properties`` / ``_resolve_throat_conditions``in
    gerçekten kullandığı değerleri ve kökenlerini aynalar.

    c* çağırandan gelmediyse ideal teoriden (γ, MW, T_c) türetilir; bu
    motorun yayımladığı c* değildir (verim içermez) ve ``assumed_fields``
    listesine girer — FEA hükmü verilmez (fail-closed).
    """
    gamma_src_ham = str(gas.get('gamma_source') or '')
    if gamma_src_ham == 'repo_default':
        gamma_src = GAS_SOURCE_ASSUMED
    else:
        gamma_src = GAS_SOURCE_SUPPLIED
    if motor_data.get('molecular_weight') is not None:
        mw_src = GAS_SOURCE_SUPPLIED
    elif motor_data.get('gas_constant') is not None:
        mw_src = GAS_SOURCE_DERIVED
    else:
        mw_src = GAS_SOURCE_ASSUMED
    # c* çözümlemesiyle AYNI kural (``_resolve_throat_conditions``):
    # çağıranın pozitif c_star / cstar alanı varsa o kullanılır.
    cstar_src = (GAS_SOURCE_SUPPLIED
                 if _positive_length(motor_data.get(
                     'c_star', motor_data.get('cstar', None))) is not None
                 else GAS_SOURCE_IDEAL)
    kaynaklar = {'gamma': gamma_src, 'molecular_weight': mw_src,
                 'c_star': cstar_src}
    varsayilan = [ad for ad, k in kaynaklar.items()
                  if k in (GAS_SOURCE_ASSUMED, GAS_SOURCE_IDEAL)]
    return {
        'gamma': {'value': float(gas['gamma']), 'source': gamma_src,
                  'source_field': gamma_src_ham or None},
        'molecular_weight': {'value': float(gas['molecular_weight']),
                             'unit': 'g/mol', 'source': mw_src},
        'c_star': {'value': float(throat['c_star']), 'unit': 'm/s',
                   'source': cstar_src},
        'assumed_fields': varsayilan,
        'all_from_caller': not varsayilan,
        '_basis': (
            'gas properties that set the Bartz h_g(z) of this profile: '
            "'supplied_by_caller' = taken verbatim from the request (the "
            "motor's own computed state when the request is built from a "
            "motor result); 'derived_from_supplied_gas_constant' = MW from "
            "the supplied gas constant; 'module_default' = generic module "
            f"value (gamma {GAMMA_REPO_DEFAULT:g}, MW "
            f"{MW_MODULE_DEFAULT_G_MOL:g} g/mol); 'ideal_theory_from_gamma_"
            "mw_tc' = ideal c* computed from gamma, MW and T_c, not the "
            "motor's published c*. A non-empty assumed_fields list means "
            "the profile does not describe the motor's own gas; the thermal "
            'FEA bridge then withholds its positive safety verdict (ÖH D37 '
            'A2-1, decision §28-24 §2 b).'),
    }


def wall_profile_inputs_from_motor(motor_results: Dict) -> Dict:
    """Motor sonuç sözlüğünden ``/api/analysis/wall-profile`` gövdesi (F-03).

    Dönüş::

        {'layout': 'hybrid'|'liquid'|'solid'|None,
         'inputs': {...düz gövde (SI; basınç bar)...},
         'basis': {alan: 'yol [birim] (ölçek)'},        # okunan yol
         'derived': {alan: '...'},                         # türetilenler
         'missing': [...],                                # çekirdek eksik
         'left_to_endpoint': [...]}                       # ucun varsayılanı

    Uydurma yok: çekirdek alan bulunamazsa ``missing`` dolar ve çağıran
    (uç) 422 verir. Malzeme ve cidar kalınlığı FEA köprüsünün mesh'i
    kurduğu AYNI alanlardan okunur (zincirin iki ucu aynı cidar,
    P7B3-30). Gaz molekül ağırlığı yayımlanmamışsa ``gas_constant`` c*
    özdeşliğinden TÜRETİLİR (c* = √(R T_c/γ)·((γ+1)/2)^((γ+1)/(2(γ−1))) —
    Sutton & Biblarz 9. bs. Eş. 3-32) ve bu ``derived`` altında yazılır.
    """
    from hrma.fea.bridge import detect_engine_layout   # tembel: döngü yok
    out = {'layout': None, 'inputs': {}, 'basis': {}, 'derived': {},
           'missing': [], 'left_to_endpoint': []}
    if not isinstance(motor_results, dict):
        out['missing'] = list(WALL_PROFILE_CORE_FIELDS) + [
            ' or '.join(WALL_PROFILE_THROAT_SCALE_FIELDS)]
        out['reason'] = 'motor_results is not a dict'
        return out
    layout = detect_engine_layout(motor_results)
    out['layout'] = layout
    if layout not in WALL_PROFILE_MOTOR_PATHS:
        out['missing'] = list(WALL_PROFILE_CORE_FIELDS) + [
            ' or '.join(WALL_PROFILE_THROAT_SCALE_FIELDS)]
        out['reason'] = ('engine layout not recognised (no structural_analysis '
                         'signature: chamber_analysis / chamber_structure / '
                         'case_analysis)')
        # Aranan yollar üç düzenin BİRLEŞİMİ — çağıran hangi alanı nereye
        # koyacağını görsün (uydurma yok, yalnız adres).
        out['searched_paths'] = {
            alan: sorted({'.'.join(y) for hm in WALL_PROFILE_MOTOR_PATHS.values()
                          for y, _ in hm.get(alan, [])})
            for alan in set().union(*[set(hm) for hm in
                                      WALL_PROFILE_MOTOR_PATHS.values()])}
        return out
    harita = WALL_PROFILE_MOTOR_PATHS[layout]
    for alan, adaylar in harita.items():
        for yol, olcek in adaylar:
            v = _yol_oku(motor_results, yol)
            if olcek is None:                      # metin alanı (malzeme)
                if isinstance(v, str) and v.strip():
                    out['inputs'][alan] = v.strip()
                    out['basis'][alan] = '.'.join(yol)
                    break
                continue
            f = _positive_length(v)
            if f is None:
                continue
            out['inputs'][alan] = f * olcek
            out['basis'][alan] = ('.'.join(yol)
                                  + (' [mm] * 1e-3 -> m' if olcek == 1e-3
                                     else ''))
            break
    # Lüle tipi ve yayımlanan kontur AYNEN (panelin yaptığı gibi).
    na = motor_results.get('nozzle_angles')
    nt = (na.get('nozzle_type') if isinstance(na, dict) else None) \
        or motor_results.get('nozzle_type')
    if isinstance(nt, str) and nt.strip():
        out['inputs']['nozzle_type'] = nt.strip()
        out['basis']['nozzle_type'] = ('nozzle_angles.nozzle_type'
                                       if isinstance(na, dict)
                                       and na.get('nozzle_type') else
                                       'nozzle_type')
    nc = motor_results.get('nozzle_contour')
    if (isinstance(nc, dict) and isinstance(nc.get('points'), list)
            and len(nc['points']) >= 2):
        out['inputs']['nozzle_contour'] = nc
        out['basis']['nozzle_contour'] = ('nozzle_contour (published, passed '
                                          'verbatim — axis matches the FEA '
                                          'bridge contour by construction)')
    # Molekül ağırlığı yoksa c* özdeşliğinden R_specific.
    inp = out['inputs']
    if ('molecular_weight' not in inp and 'gas_constant' not in inp
            and all(k in inp for k in ('c_star', 'gamma',
                                       'chamber_temperature'))):
        g = float(inp['gamma'])
        if g > 1.0:
            cs = float(inp['c_star'])
            Tc = float(inp['chamber_temperature'])
            gamma_term = ((g + 1.0) / 2.0) ** ((g + 1.0) / (g - 1.0))
            R = g * cs * cs / (Tc * gamma_term)
            if math.isfinite(R) and R > 0.0:
                inp['gas_constant'] = R
                out['derived']['gas_constant'] = (
                    f'R_specific = gamma*c*^2/(T_c*((gamma+1)/2)^((gamma+1)/'
                    f'(gamma-1))) from c_star={cs:g}, gamma={g:g}, T_c={Tc:g} '
                    f'(c* identity, Sutton & Biblarz 9th ed. Eq. 3-32) = '
                    f'{R:.4f} J/(kg K) -> MW = {R_UNIVERSAL / R:.4f} g/mol; '
                    'the motor dict publishes no molecular_weight')
    if 'molecular_weight' not in inp and 'gas_constant' not in inp:
        out['left_to_endpoint'].append('molecular_weight')
    for alan in ('material', 'wall_thickness'):
        if alan not in inp:
            out['left_to_endpoint'].append(alan)
    out['missing'] = [k for k in WALL_PROFILE_CORE_FIELDS
                      if _positive_length(inp.get(k)) is None]
    if all(_positive_length(inp.get(k)) is None
           for k in WALL_PROFILE_THROAT_SCALE_FIELDS):
        out['missing'].append(' or '.join(WALL_PROFILE_THROAT_SCALE_FIELDS))
    out['searched_paths'] = {alan: ['.'.join(y) for y, _ in adaylar]
                             for alan, adaylar in harita.items()}
    return out


def material_name(mat_props: Dict, materials_db: Dict) -> str:
    """Reverse-lookup a material name from its property dict (best effort)."""
    for name, props in materials_db.items():
        if props is mat_props:
            return name
    return 'material'
