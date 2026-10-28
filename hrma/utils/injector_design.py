import numpy as np
from scipy.optimize import minimize_scalar
# ---------------------------------------------------------------------------
# ÖH D31 / OH-D30-01 — DAİRESEL İÇE AKTARMA SÖKÜLDÜ (modül düzeyi -> işlev içi)
# ---------------------------------------------------------------------------
# Bu iki satır burada MODÜL DÜZEYİNDEYDİ:
#     from hrma.data.external_data_fetcher import data_fetcher, ...
#     from hrma.analysis.tank_blowdown import N2OSaturation
# ve şu halkayı kapatıyordu (ölçüldü, ``once.json`` bölüm A):
#     hrma.data.external_data_fetcher
#       -> hrma.analysis.tank_blowdown -> ... -> trajectory_analysis
#       -> hrma.utils.numeric_compat -> hrma/utils/__init__
#       -> hrma.utils.injector_design -> external_data_fetcher (YARIM)
# Sonuç: ``external_data_fetcher`` ÖNCE yüklenen HER süreçte
# ``hrma.utils.InjectorDesign`` ``IMPORT_ERRORS``a düşüyordu; ürün yolunda
# ``InjectorDesign(...)`` çağrısı "cannot import name 'data_fetcher' from
# partially initialized module" diyerek ImportError veriyordu (ölçüldü:
# ``urun_yolu_ters_sira``). Kusur tabanda da vardı ve yükleme SIRASINA
# bağlıydı — yani sessizdi.
#
# Adlar artık ÇAĞRI ANINDA çözülür. İki yol açık tutulur:
#   * modülün KENDİ kodu işlev içi ``import`` kullanır (aşağıdaki çağrı
#     yerlerinde adıyla görülür);
#   * dışarıdan ``from hrma.utils.injector_design import OxidizerStateError``
#     gibi ESKİ kullanımlar, dosyanın sonundaki modül ``__getattr__``
#     (PEP 562) ile birebir aynı nesneyi almaya devam eder.
# Davranış değişmez; değişen yalnız adın ÇÖZÜLDÜĞÜ andır.
# Giffen–Muraszew basınç-swirl çözücüsü — kardeş (authoritative) modülden
# alınır ki iki modül AYNI katsayı ve aynı zarfı kullansın (F017/F043).
from hrma.engines.injector_design import (
    swirl_solve, swirl_K_from_theta, _SWIRL_K_MIN, _SWIRL_K_MAX,
    _SWIRL_THETA_MIN_DEG, _SWIRL_THETA_MAX_DEG,
    # Z1: yüzey gerilimi tablosu TEK yerde (aşağıdaki SIGMA_OX ondan türer);
    # akışkanı bilinmeyen sıvı için BEYAN EDİLEN jenerik viskozite de öyle.
    SIGMA_LIQUID_REF, MU_GENERIC,
    # v2.6.27 (B3): pintle ucu sentezi TEK kaynaktan — radyal delik dizisi
    # yalnız kardeş modülde modellenmişti, bu modül pintle'ı çıplak anülüs
    # sanıyordu. Artık iki modül de aynı fonksiyonu çağırır.
    pintle_tip_geometry, pintle_spray_angle,
    PINTLE_HYBRID_RADIAL_FRACTION, PINTLE_BF_TARGET_DEFAULT, PINTLE_BF_BAND,
    # V301/E1: kanon pintle geometrisinin TEK çözücüsü + imalat alt sınırı.
    resolve_pintle_geometry, PintleGeometryInputError, ANNULUS_GAP_MIN_MM,
    # ÖH D25 / P16B1-45: plaka çözücüsünün Cd'si artık kendi çıplak
    # varsayılanından değil, devrenin TEK kaynağından gelir.
    default_discharge_coefficient,
    # ÖH D37 A2 hibrit · 5. tur Ş-4: delik çapının bant hükmü (bant dışı /
    # alt kenara yakın) devre çözücüsüyle AYNI sınıflandırıcıdan.
    classify_orifice_d, ORIFICE_D_CLASS_BELOW, ORIFICE_D_CLASS_ABOVE,
    # ÖH D37 A2 hibrit · 7. tur (karar §28-25): kırpılmış planın hedef debi
    # denetimi — tolerans, künyesi, sınıf adı ve doğrulama kaydı TEK yerde.
    CLAMPED_PLAN_TARGET_FLOW_REL_TOL, CLAMPED_PLAN_TARGET_FLOW_TOL_BASIS,
    TARGET_FLOW_NOT_MET, clamped_plan_target_flow_record, band_warning_decimals,
    # V301/E2: çarpışma yarı açısı ve girdap odası oranı TEK kaynaktan.
    IMPINGE_HALF_ANGLE_DEG, SWIRL_CHAMBER_D_OVER_DO)
# Chug ΔP/Pc eşiği: TEK SAYISAL TANIM acoustic_modes'tadır. v2.6.27 (parti 31)
# öncesinde bu modül eşiği İKİ biçimde kopyalıyordu — hesapta çıplak 0.15/0.20
# literalleri, kullanıcıya giden uyarı METNİNDE ise ">=15%" dizesi. Dize
# kopyası en sinsisiydi: sabit değiştiğinde kod yeni eşiğe göre boyutlandırır,
# ekrandaki cümle ESKİ sayıyı savunmaya devam ederdi. Artık ikisi de buradan
# türetilir (yüzde f-string ile sabitin KENDİSİNDEN üretilir).
from hrma.analysis.acoustic_modes import (
    CHUG_DP_RATIO_MINIMUM,
    CHUG_DP_RATIO_RECOMMENDED,
)
# ÖH D29 / P16B1-44: deger katmaninin TEK KAYNAGI (sayi-benzeri dize sayidir,
# bool degildir, NaN/inf degildir).
from hrma.utils.input_guard import finite_number
# ÖH D37 A2 hibrit · F-10: delik çapı bandının TEK kaynağı (künyesi
# ``ORIFICE_D_BAND_SOURCE``, hrma/constants.py).
from hrma.constants import ORIFICE_D_BAND_MM
import math
import warnings

# ---------------------------------------------------------------------------
# Modül sabitleri — tek yerde tanımlı (magic number koruması)
# ---------------------------------------------------------------------------
# Oksitleyici yüzey gerilimi [N/m], referans sıcaklığında.
# Z1: sayılar burada KOPYALANMAZ, kardeş modülün tablosundan (engines/
# injector_design.py::SIGMA_LIQUID_REF) türetilir. Eskiden aynı iki değer iki
# dosyada elle duruyordu ve biri güncellenince diğeri sessizce ayrışıyordu.
#   n2o: 2.058e-3 N/m @ 293.15 K (NIST SRD 69; kritik noktaya yakın olduğu
#        için suyun 1/35'i kadardır)
#   lox: 1.3145e-2 N/m @ 90.19 K (doyma)
SIGMA_OX = {ad: deger for ad, (deger, _t) in SIGMA_LIQUID_REF.items()}
SIGMA_OX_DEFAULT = 0.02          # bilinmeyen oksitleyici için muhafazakar değer

#: Oksitleyici kimliği verilmediğinde kullanılan AÇIK etiket. P10B1-20:
#: eskiden ``str(oxidizer_type or 'n2o')`` ile boş/None sessizce N₂O'ya
#: dönüşüyordu; bir LOX ya da H₂O₂ koşusu adını kaybettiğinde N₂O'nun yüzey
#: gerilimini, buhar basıncını ve yoğunluğunu miras alıyordu.
OXIDIZER_UNSPECIFIED = 'unspecified'

# Basınç düşümü kaynak etiketleri (rapor sözleşmesi — app.js bu stringleri okur)
#: 'auto' etiketi otomatik seçilen ΔP oranını ADIYLA taşır; yüzde eşiğin
#: KENDİSİNDEN üretilir (etiket metni bit-aynı: 'auto (20% of Pc)').
DP_SOURCE_AUTO = f'auto ({CHUG_DP_RATIO_RECOMMENDED * 100:.0f}% of Pc)'
DP_SOURCE_USER = 'user override'
DP_SOURCE_SAT = 'saturation-driven'
#: ÖH D35 / OH-ON-01 — ΔP devre çözücüsünün (``engines/injector_design.py``
#: ``design_injector``) çözdüğü değerdir. Bu etiket, 21 Eylül 2026 görsel
#: turunda ölçülen kusurun kapanışıdır: aynı yanıtta iki enjektör çözümü
#: vardı ve bu modülünki ΔP'yi gizli panelin gönderdiği 4 bar'dan alıp
#: "user override" diye künyeliyordu — kullanıcı o alanı hiç görmemişti.
DP_SOURCE_SOLVER = 'injector circuit solution'

#: Çağıranın beyan edebileceği ΔP kaynakları -> yayımlanan künye.
#: ``None``/tanınmayan beyan eski davranışı korur (geriye uyum): sayı
#: pozitifse ``user override``. YENİ ETİKET İCAT EDİLMEZ; sözlük tek
#: yerdedir ve ``app.js`` bu dizeleri okuyor.
DP_SOURCE_DECLARATIONS = {
    'solver': DP_SOURCE_SOLVER,
    'injector_circuit': DP_SOURCE_SOLVER,
    'user': DP_SOURCE_USER,
    'request': DP_SOURCE_USER,
}


def _dp_kaynagi(beyan):
    """Beyan edilen ΔP kaynağını yayımlanan künyeye çevirir.

    Beyan yoksa (``None``) ya da tanınmıyorsa ``DP_SOURCE_USER`` döner —
    bu modülün v2.6.27 öncesi davranışıdır ve dışarıdaki çağıranlar
    (testler, defter betikleri) bozulmaz.
    """
    if beyan is None:
        return DP_SOURCE_USER
    return DP_SOURCE_DECLARATIONS.get(
        str(beyan).strip().lower(), DP_SOURCE_USER)

# Yoğunluk kaynak etiketleri.
#
# Z1 ONARIMI — künye artık SABİT bir etiket değil, değerin GELDİĞİ yerden
# üretilen bir dizedir (ör. "CoolProp/REFPROP EOS (Lemmon & Span 2006),
# N2O saturated liquid at 293.15 K"). Sebep ölçülüydü: eski kod, sayı gömülü
# yedek tablodan gelse bile ``DENSITY_SOURCE_NIST`` basıyordu; künye bir VERİ
# KAYNAĞI beyanıdır, "doğrulamadan geçti" bayrağı değildir.
#
# ``DENSITY_SOURCE_USER`` hâlâ CANLI ve tek sabit künyedir: kullanıcı bir sayı
# GERÇEKTEN verdiyse basılır (OH-B1-02 / P10B1-09 — eskiden app.py'nin gömülü
# 1220'si de "user input" diye künyeleniyordu).
# Diğer ikisi geriye dönük ad olarak korunuyor: ürün yolunda ARTIK basılmazlar,
# bekçiler bunları "bu etiket görünmemeli" iddiasında çapa olarak kullanıyor.
DENSITY_SOURCE_USER = 'user input'
DENSITY_SOURCE_NIST = 'NIST WebBook'      # artık ürün yolunda BASILMAZ
DENSITY_SOURCE_LOCAL = 'local fallback'   # artık ürün yolunda BASILMAZ

# Impingement (like-on-like doublet) sabitleri — NASA SP-8089 tipik değerleri
# V301/E2: yarı açı devre modülünün sayısıdır (kimlik takma adı, kopya yok).
IMPINGEMENT_HALF_ANGLE_DEG = IMPINGE_HALF_ANGLE_DEG   # 2θ = 60° çarpışma açısı
IMPINGEMENT_DISTANCE_LD = 6.0       # çarpışma noktası ≈ 6·d_j (5-7 bandı ortası)

# --------------------------------------------------------------------------
# ÖH D20 / P15B1-02 (Fable-D18 RET → yeniden atama) — PLAKA KALINLIĞI
# KULLANICI VERİSİDİR.
#
# ÖLÇÜLDÜ (taban 14acd1d, ``docs/scofield/raw/OH/D20/app-api/a1/once.json``):
# hibrit ``/calculate`` yanıtında ``injector.plate_thickness`` = 3,0 mm ve
# ``injector.L_D_ratio`` = 3,2337 duruyordu; kullanıcı hiçbir plaka kalınlığı
# göndermemişti ve yanıtta bunu söyleyen TEK bir künye/uyarı yoktu
# (``plate_thickness_basis``/``l_d_ratio_basis`` yok, ``defaults_applied``
# yok). Üstelik L/D 3-5 bandı denetimi bu uydurma sayıdan geçiyor ve
# SESSİZ KALIYORDU — yani ürün "L/D'niz uygun" hükmünü kimsenin seçmediği
# bir sayıdan veriyordu. Kardeş modül ``hrma/engines/injector_design.py``
# aynı durumda hükmü ALIKOYUYOR ("the caller supplied neither an orifice
# length / plate thickness nor an L/D ... A safety verdict is not published
# from a number nobody chose"). İki modül artık aynı dili konuşur.
#
# Sayı BURADA tek kaynaktan gelir; setter imzasındaki ``None`` "kullanıcı
# vermedi" demektir ve KAZANILMAMIŞLIK bilgisini taşır.
PLATE_THICKNESS_DEFAULT_MM = 3.0            # showerhead plakası
IMPINGEMENT_PLATE_THICKNESS_DEFAULT_MM = 5.0   # çarpışmalı doublet plakası

# V301/HİBRİT-DIŞA (kalem 4; T-ÇAPA-C2 D3 / DEVİR C1-FİZİK (a)) — KAZANILMAMIŞ
# PLAKADA SAYI YAYIMLANMAZ. ÖLÇÜLDÜ (olcum/plaka_once.json): plaka kalınlığı
# verilmeyen hibrit showerhead yanıtı ``injector.plate_thickness`` = 3,0 ve
# ``L_D_ratio`` = 1,5547 yayımlıyordu (``plate_thickness_earned = false``);
# arayüz/rapor "değerlendirilmedi" derken API sayıyı taşıyordu ve plaka yapısal
# denetimi (app.py ``_injector_plate_report``) bu 3,0 mm'yi plaka kalınlığı
# diye okuyordu. Artık kazanılmamışsa ``plate_thickness``, ``L_D_ratio`` ve
# ``l_d_ratio`` ``null``; dayanak ``plate_thickness_basis`` / ``l_d_ratio_basis``
# künyesinde, hüküm alıkonma uyarısında. Modülün iç hesabı (C_d için beyanlı
# L/D) değişmedi; yalnız yayın.
LD_NOT_ISSUED_WARNING = (
    "L/D band check NOT ISSUED: no plate thickness (orifice length) was "
    "supplied, so L/D is not computed for this design; supply plate_thickness "
    "to obtain the 3-5 band verdict.")


def _yayin_plaka_mm(params, kazanildi):
    """Yayımlanan plaka kalınlığı [mm]: yalnız KAZANILMIŞSA sayı, değilse None."""
    return params['t_plate'] * 1000 if kazanildi else None

# Koaksiyel (tek akışkan) sabitleri — V301/H2: TEK tanım devre modülünde
# (``hrma/engines/injector_design.py``): tek akışkanlı koaksiyel eleman
# artık devrenin kanonudur (``design_coaxial_element``) ve bu blok onun
# geometrisini tüketir. Buradaki adlar o sabitlerin KİMLİK takma adlarıdır
# (E2'nin ``SWIRL_CHAMBER_D_RATIO`` deseni); sayılar DEĞİŞMEDİ. V301/E2:
# pay bandın dışındaysa KIRPILMAZ — uçta HTTP 422, setter'da ValueError.
from hrma.engines.injector_design import (  # noqa: E402
    COAX_INNER_FLOW_FRACTION, COAX_INNER_FLOW_FRACTION_BAND,
    COAX_INNER_FLOW_FRACTION_BASIS, COAX_RECESS_LD, COAX_WALL_MIN_MM,
    COAX_RECESS_BASIS, COAX_ELEMENT_COUNT_BASIS, coaxial_element_geometry)

# Yerel yoğunluk yedeği [kg/m³] — Z1 ONARIMI: ARTIK SABİT DEĞİL.
#
# Eski değer 1220'ydi ve N₂O'nun NORMAL KAYNAMA NOKTASI (184,67 K) yoğunluğu
# olduğu ölçüldü: 293,15 K'de +%55,4 hata (gerçeği 785,10), LOX'a
# uygulandığında +%6,9, H₂O₂ %98'e uygulandığında −%15,2. Üstelik yalnız
# "yedek" değildi — ``validate_data``nın [800,1500] bandı N₂O'nun 288 K
# üstündeki TÜM doğru değerlerini reddettiği için bu yedek NORMAL yoldu.
#
# Yerine geçen sözleşme: yoğunluk ya kullanıcıdan gelir, ya akışkana özgü
# referans kaynağından (``oxidizer_reference_density``) gelir, ya da HESAP
# YÜRÜMEZ. Akışkanı bilinmeyen bir sıvı için "tipik bir yoğunluk" yoktur.
#
# Ad geriye dönük uyumluluk için korunuyor ve artık N₂O'nun depolama durumu
# değerini merkezî tablodan okur (elle yazılmış sayı değildir); yalnız
# tanı/karşılaştırma amaçlıdır, hesap yolunda KULLANILMAZ.
# OH-D30-01: hesap modül YÜKÜNDE değil, ADA İLK DOKUNULDUĞUNDA yapılır
# (değer ve ``None`` yedeği birebir aynı; bkz. modül ``__getattr__``).
def _local_density_fallback():
    """N₂O depolama durumu yoğunluğu [kg/m³] — merkezî tablodan, gecikmeli."""
    from hrma.data.external_data_fetcher import (
        oxidizer_reference_density as _ref_yogunluk,
        OxidizerStateError as _DurumHatasi)
    try:
        return _ref_yogunluk('n2o')['density']
    except _DurumHatasi:      # pragma: no cover - bozuk kurulum
        return None

# Pintle anülüs boşluğu imalat bandı [m] (0.3-3.0 mm; HRMA seçimi). Alt
PINTLE_GAP_MIN_M = ANNULUS_GAP_MIN_MM * 1e-3   # sınır kardeş modülden (V301/E1)
PINTLE_GAP_MAX_M = 0.003

# Nurick kavitasyon kriteri (F044): K_c = (P₁−P_v)/(P₁−P₂); K_c < ~1.5 →
# kavitasyon/hidrolik flip riski. Kaynak: Nurick, ASME J. Fluids Eng. 98
# (1976). Kardeş modül (engines/injector_design.py FLIP_KC_LIMIT) ile aynı eşik.
NURICK_KC_LIMIT = 1.5
# v3.0.1 (V301/H3, E2 KARAR-8): kendinden basınçlı N₂O'da enjektör girişi
# doymuş sıvıdır (P₁ = P_v), Nurick K_c = 0 TANIM GEREĞİDİR ve akış iki
# fazlıdır; devre bunu Dyer NHNE ile modeller. "Cavitation risk" / "Flash
# boiling risk detected" metinleri beklenen ve modellenen hâli risk diye
# abartıyordu. Doymuş girişte bu iki uyarı yerine TEK bilgi kaydı basılır;
# kullanıcı tank kipinde (P₁ > P_v) değerlendirme aynen kalır.
SATURATED_INLET_NOTE_CODE = 'info.injector.saturated_inlet_two_phase'
SATURATED_INLET_NOTE = (
    'Saturated N2O inlet (K_c = 0): flashing two-phase flow is expected and '
    'is modelled by Dyer NHNE in the injector circuit; hydraulic-flip '
    'verdict: see the circuit')
# N₂O dışı (depolanabilir) sıvılar için buhar basıncı varsayımı [bar] —
# engines modülüyle aynı politika (~hava basıncı altı).
VAPOR_PRESSURE_ASSUMED_BAR = 0.05
# N₂O buhar basıncı yedeği [bar] — doyma tablosu/EOS erişilemezse.
# 50,525 bar = doyma basıncı @293,15 K (NIST SRD 69, Lemmon & Span 2006).
# (Eski 51,0 değeri kaynaksızdı; +%0,9.)
N2O_PSAT_FALLBACK_BAR = 50.525

# Basınç-swirl (simplex) tasarım varsayılanları (F017/F043):
# - Hedef sprey YARI açısı: tipik simplex bandının (30-60°) ortası; kardeş
#   modülün (engines) theta_target_deg varsayılanıyla aynı.
# - Girdap odası çapı oranı: D_s = 2.5·d_o (engines: r_s = 2.5·r_o).
# Kaynak: Lefebvre & McDonell, Atomization and Sprays 2. baskı, Böl. 6.
SWIRL_DEFAULT_HALF_ANGLE_DEG = 45.0
SWIRL_CHAMBER_D_RATIO = SWIRL_CHAMBER_D_OVER_DO   # V301/E2: kimlik takma adı

# V301/E2 — iki uyarı bandının KAYNAĞI YOK. Depoda ve kardeş modülde bu
# bantlara atıf aranıp bulunamadı (grep: 20-50 m/s ve L/D 3-5); enjeksiyon
# hızı göstergesinin 20-50 yeşil bandı da aynı gerekçeyle 3 Ağustos 2026'da
# söküldü (visualization.py, T43). L/D için NASA SP-8089 s. 84 (devre
# modülündeki FLIP_SENSITIVE_LD_BAND künyesi) "4-6 arası ara L/D hidrolik
# flip'e özellikle duyarlıdır" der — yani 3-5 bir "optimum" değildir. Bantlar
# HRMA buluşsal eşiği olarak kalır; uyarı metni "optimal" demez.
INJECTION_VELOCITY_HEURISTIC_BAND_M_S = (20.0, 50.0)
ORIFICE_LD_HEURISTIC_BAND = (3.0, 5.0)
# Çarpışma tam açısı bandı [derece]. Uyarı metni bandı "NASA SP-8089"a
# dayandırıyordu; deponun birincil metin okuması (docs/arastirma/
# 2026-10-05/notlar/SP-S1/SP-8089.md, madde 10) SP-8089 s. 78-79'un bant
# DEĞİL tek değer önerdiğini kaydediyor: unlike ve like-impinging için 60°.
# 40-90° HRMA buluşsal eşiğidir; metin kaynağı doğru söyler.
IMPINGEMENT_ANGLE_HEURISTIC_BAND_DEG = (40.0, 90.0)


def _carpisma_acisi_bant_metni(tam_aci):
    lo, hi = IMPINGEMENT_ANGLE_HEURISTIC_BAND_DEG
    return (f"Impingement angle ({tam_aci:.0f} deg) outside the "
            f"{lo:.0f}-{hi:.0f} deg band (HRMA heuristic threshold - no "
            f"literature value; NASA SP-8089 pp. 78-79 recommends 60 deg)")

# N₂O doyma tablosu — determinist (CoolProp'suz), engines modülüyle aynı
# kaynak. OH-D30-01: örnek modül YÜKÜNDE değil, İLK KULLANIMDA kurulur ve
# bir kez önbelleğe alınır (eski modül düzeyi örnekle aynı paylaşım).
_SAT_N2O_ONBELLEK = None


def _sat_n2o():
    """Paylaşılan ``N2OSaturation`` örneği — gecikmeli kurulur."""
    global _SAT_N2O_ONBELLEK
    if _SAT_N2O_ONBELLEK is None:
        from hrma.analysis.tank_blowdown import N2OSaturation as _Doyma
        _SAT_N2O_ONBELLEK = _Doyma(use_coolprop=False)
    return _SAT_N2O_ONBELLEK

class InjectorDesign:
    def __init__(self, mdot_ox, chamber_pressure, oxidizer_phase='liquid',
                 oxidizer_density=None, oxidizer_viscosity=None,
                 tank_pressure=50, pressure_drop=0,
                 pressure_drop_source=None,
                 discharge_coefficient=None,
                 discharge_coefficient_basis=None,
                 injector_type='showerhead', oxidizer_temp=Ellipsis,
                 oxidizer_type='n2o', oxidizer_density_source=None):
        # Z1: ``oxidizer_viscosity`` varsayılanı 0.0002 Pa·s idi. O sayı
        # akışkandan bağımsızdı ve N₂O'nun ~247 K viskozitesine denk düşüyor;
        # 293 K'deki gerçeği 6,817e-5 (2,9 kat), LOX'unki 1,95e-4, H₂O₂'ninki
        # 1,25e-3'tür. Artık None = "verilmedi" demektir ve değer akışkanın
        # kendi referans tablosundan gelir.

        self.mdot_ox = mdot_ox  # kg/s
        self.P_c = chamber_pressure  # bar
        self.ox_phase = oxidizer_phase
        self.P_tank = tank_pressure  # bar
        # --- ÖH D29 / P16B1-44 · DEĞER KATMANI SICAKLIK KAPISININ ÖNÜNDE ---
        # ÖLÇÜLDÜ (``docs/scofield/raw/OH/D29/app-api-dogrulama/a2/once.json``
        # K5, taban ``4dc63c11``): ``oxidizer_temp``in FİZİK kapısı zaten
        # sağlamdı — 14 sarsımın 11'i N₂O doymuş sıvı zarfıyla (182,33-309,52 K,
        # NIST WebBook) ADIYLA reddediliyordu. Kırık olan DEĞER katmanıydı:
        #
        #   oxidizer_temp = null    -> HTTP 500  "unsupported format string
        #                                        passed to NoneType.__format__"
        #   oxidizer_temp = [1, 2]  -> HTTP 500  "float() argument must be a
        #                                        string or a real number,
        #                                        not 'list'"
        #   oxidizer_temp = ""      -> HTTP 400  "Unknown format code 'f' for
        #                                        object of type 'str'"
        #
        # Yani sayı olmayan girdi fizik kapısına VARAMADAN aşağıdaki f-dizesini
        # patlatıyordu ve kullanıcı, hangi alanı yanlış gönderdiğini söyleyen
        # bir cümle yerine Python biçimlendirici metnini görüyordu (deponun
        # kendi teşhis ettiği kusur sınıfı — bkz. ``app.py::_form_band_kapisi``
        # P16B2-11 notu). Kural İCAT EDİLMEDİ: değer katmanının TEK KAYNAĞI
        # ``hrma.utils.input_guard.finite_number``dır ve bu modül zaten onun
        # komşusudur; sayı-benzeri dize onun sözleşmesinde sayıdır
        # (v2.6.26 gerekçesi), ``bool`` ise değildir.
        _ox_T = finite_number(_varsayilan_tank_t() if oxidizer_temp is Ellipsis else oxidizer_temp)
        if _ox_T is None:
            raise ValueError(
                'oxidizer_temp must be a finite number in kelvin (K), '
                f'given: {type(oxidizer_temp).__name__} '
                f'{str(oxidizer_temp)[:40]!r}. No temperature is assumed in '
                'its place: every oxidizer property that sizes the injector '
                '(density, vapour pressure, surface tension) is read at this '
                'temperature.')
        oxidizer_temp = _ox_T
        self.oxidizer_temp = oxidizer_temp  # K
        # Z1 / P10B1-20: kimlik SESSİZCE düşmez. Eskiden ''/None doğrudan
        # 'n2o' oluyordu ve o akışkanın σ, P_v, ρ değerleri adı kaybolmuş
        # sıvıya uygulanıyordu. Artık açık bir etikete ('unspecified')
        # düşer; aşağıdaki kollar bunu görüp beyan eder / fail-closed olur.
        _ox_raw = '' if oxidizer_type is None else str(oxidizer_type).strip().lower()
        self.oxidizer_type = _ox_raw or OXIDIZER_UNSPECIFIED
        # v3.0.1 (V301/H3): doymuş giriş bayrağı (P₁ = P_v). Uç, devrenin
        # besleme kaynağına bakarak kurar; varsayılan kapalıdır (Python API ve
        # kullanıcı tank kipi eski değerlendirmeyi aynen alır).
        self.saturated_inlet = False

        print(f"Fetching oxidizer properties... "
              f"({self.oxidizer_type}, T={oxidizer_temp:.0f}K, P={tank_pressure:.1f} bar)")

        # Termofiziksel özellikler TEK kaynaktan (external_data_fetcher'ın
        # akışkana özgü referans kapısı). Tip artık hardcoded 'n2o' değil.
        # OH-D30-01: içe aktarma İŞLEV İÇİNDE — modül yükü sıraya duyarsız.
        from hrma.data.external_data_fetcher import (
            data_fetcher, OxidizerStateError)
        nist_data = data_fetcher.fetch_nist_oxidizer_properties(
            self.oxidizer_type, oxidizer_temp, tank_pressure)

        # Veri doğrulaması — Z1 sonrası iki kademeli ve akışkana özgü
        # (mutlak fiziksel zarf + ρ_ref(T)'ye %3 durum tutarlılığı).
        is_valid, msg = data_fetcher.validate_data(nist_data, 'oxidizer')

        # ---------------------------------------------------------------
        # YOĞUNLUK KAYNAĞI SÖZLEŞMESİ (Z1 ONARIMI)
        #
        # 1. Kullanıcı bir sayı verdiyse O KAZANIR ve künye 'user input'
        #    olur — ama YALNIZ gerçekten verdiyse (OH-B1-02, P10B1-09).
        #    Eskiden app.py alan yokken gömülü 1220'yi geçiriyordu ve künye
        #    yine "user input" diyordu: kullanıcı hiçbir şey vermemişti.
        # 2. Vermediyse akışkana özgü referans kaynağı kullanılır ve künye
        #    değerin GELDİĞİ yerden üretilir (çağıranın varsayımından
        #    değil). Eski kod, sayı gömülü yedek tablodan gelse bile
        #    'NIST WebBook' basıyordu.
        # 3. Referans çözülemiyorsa SAYI ÜRETİLMEZ (fail-closed): hata
        #    eksik alanın adını söyler. Eski yol burada 1220'ye düşüyordu.
        # ---------------------------------------------------------------
        self.density_state_warning = None
        user_gave_density = oxidizer_density is not None
        if user_gave_density and oxidizer_density_source:
            # V301/E2 (devir madde 9) — YOĞUNLUK ÇAĞIRANIN ÇÖZÜCÜSÜNDEN.
            # Kullanıcı tank basıncı kipinde devre, N₂O'yu enjektör GİRİŞ
            # hâlinde (P₁, T) sıkıştırılmış sıvı olarak çözer; bu blok ise
            # doymuş sıvı yoğunluğuyla hız basıyordu (ölçüldü, N₂O 60 bar:
            # plaka 60,7 ⟷ devre 59,3 m/s). Çağıran (app.py) devrenin
            # yoğunluğunu kaynağıyla verir: künye 'user input' DEĞİL o
            # kaynaktır ve durum sapma ikazı uygulanmaz (değer bir durum
            # denkleminin sonucudur, kullanıcı sayısı değil).
            self.rho_ox = float(oxidizer_density)
            self.density_source = str(oxidizer_density_source)
            self.mu_ox = self._resolve_viscosity(
                oxidizer_viscosity, nist_data if is_valid else {})
        elif user_gave_density:
            self.rho_ox = float(oxidizer_density)  # kg/m³
            self.density_source = DENSITY_SOURCE_USER
            # Viskozite: referans geçerliyse oradan, değilse parametre.
            self.mu_ox = self._resolve_viscosity(
                oxidizer_viscosity, nist_data if is_valid else {})
            # Kullanıcının sayısı EZİLMEZ ama sessizce de kabul edilmez:
            # akışkanın o sıcaklıktaki referansından %3'ten fazla saparsa
            # rapora bir uyarı düşer (hesap yürür — bu bir kapı değil,
            # dürüst bir ikaz).
            self.density_state_warning = self._density_state_warning(
                self.rho_ox, oxidizer_temp)
        elif not is_valid:
            raise OxidizerStateError(
                f"Cannot resolve an oxidizer density for "
                f"'{self.oxidizer_type}' at {float(oxidizer_temp):.2f} K: "
                f"{msg} No substitute value is invented (the previous "
                f"behaviour fell back to 1220 kg/m3, the normal-boiling-point "
                f"density of N2O, regardless of the fluid). Supply the "
                f"'oxidizer_density' field in kg/m3, or correct "
                f"'oxidizer_type'/'oxidizer_temp'.")
        else:
            self.rho_ox = float(nist_data['density'])  # kg/m³
            self.mu_ox = self._resolve_viscosity(oxidizer_viscosity,
                                                 nist_data)  # Pa·s
            self.density_source = nist_data['density_source']
        print(f"Density source: {self.density_source}")
        print(f"   rho = {self.rho_ox:.0f} kg/m³")
        print(f"   mu  = {self.mu_ox:.6f} Pa·s")

        # Buhar basıncı [bar] — Nurick kavitasyon sayısı (F044) ve flaş
        # kaynama denetimi için. N₂O: doyma tablosundan SICAKLIĞA bağlı
        # (eski kod 51 bar @ 293 K sabitini kullanıyordu); diğer sıvılar:
        # depolanabilir sıvı varsayımı (engines modülüyle aynı politika).
        #
        # ÖH Z5S / P10-A (P10B1-21) — ÖLÇÜLDÜ (28 Ağustos 2026): buradaki
        # ``except Exception`` doyma tablosunun FAIL-CLOSED reddini yutuyordu.
        # ``oxidizer_temp=1000 K`` (N₂O kritik sıcaklığı 309,52 K) +
        # kullanıcı yoğunluğu verildiğinde üstteki yoğunluk kapısı da
        # atlanıyor ve sonuç şuydu:
        #
        #     p_vapor_bar = 50,525   (293,15 K'nin DOYMA basıncı)
        #     kullanıcıya giden cümle: "P_v = 50.5 bar at 1000 K"
        #     + "Flash boiling risk detected"
        #
        # Kritik noktanın üstünde doymuş sıvı/buhar ayrımı YOKTUR; o sayı
        # var olmayan bir hâlin sayısıydı ve kullanıcının gördüğü cümleye
        # giriyordu. İki hata sınıfı artık AYRILIR:
        #   * hâl zarfın DIŞINDA (ValueError)  -> sayı üretilmez, hüküm
        #     geri çekilir (p_vapor_bar = None) ve gerekçe adıyla taşınır;
        #   * tablo/EOS ERİŞİLEMİYOR (kurulum)  -> belgeli yedek kullanılır,
        #     ama artık sessiz değil: künye yedeği söyler.
        self.p_vapor_bar = None
        self.p_vapor_basis = None
        self.p_vapor_unavailable_reason = None
        if self.oxidizer_type == 'n2o':
            try:
                # ÖH D22 / P4B4-12 — TABLO BANDI KAPISI (fail-closed).
                # ÖLÇÜLDÜ (taban b84b10a,
                # ``docs/scofield/raw/OH/D22/termo-ucus/a1/once.json``):
                # ``oxidizer_temp=230`` (bandın 10 K altı) için burası
                # ``p_vapor_bar = 11,8777`` yayımlıyor ve künyeye "N2O
                # saturation curve at 230.00 K" yazıyordu. O sayı 230 K'nin
                # değeri DEĞİL, tablonun 240 K kenarının değeriydi;
                # kenetlemeyi bildiren F184 defterini de okuyan yoktu.
                # Kritik nokta üstü zaten reddediliyordu (Z1); band ALTI
                # sessizce geçiyordu. Artık iki zarf da aynı kapıdan geçer.
                _doyma = _sat_n2o()                      # OH-D30-01: gecikmeli
                sicaklik = _doyma.require_table_band(float(oxidizer_temp))
                self.p_vapor_bar = float(_doyma.psat(sicaklik)) / 1e5
                self.p_vapor_basis = (
                    f'N2O saturation curve at {float(oxidizer_temp):.2f} K '
                    f'(hrma.analysis.tank_blowdown.N2OSaturation)')
            except ValueError as durum_hatasi:
                # Fiziksel zarf dışı: SAYI ÜRETİLMEZ.
                self.p_vapor_unavailable_reason = (
                    f'N2O vapour pressure is not defined at '
                    f'{float(oxidizer_temp):.2f} K: {durum_hatasi}')
            except Exception as tablo_hatasi:      # noqa: BLE001
                self.p_vapor_bar = N2O_PSAT_FALLBACK_BAR
                self.p_vapor_basis = (
                    f'documented fallback {N2O_PSAT_FALLBACK_BAR:.3f} bar '
                    f'(N2O saturation at 293.15 K, NIST SRD 69) because the '
                    f'saturation source is unavailable: {tablo_hatasi}')
        else:
            self.p_vapor_bar = VAPOR_PRESSURE_ASSUMED_BAR
            self.p_vapor_basis = (
                f'assumed storable-liquid vapour pressure '
                f'{VAPOR_PRESSURE_ASSUMED_BAR:.2f} bar '
                f"(no saturation model for '{self.oxidizer_type}')")

        # Daha gerçekçi basınç düşümü hesaplaması
        # İnjektör basınç düşümü tipik olarak kamara basıncının %15-25'i olmalı
        # Çok düşükse atomizasyon kötü, çok yüksekse tankaj sistemi ağır.
        # Kaynak raporlanır: kullanıcı override / otomatik %20 / doyma
        # (tank basıncı) sınırlı — kullanıcının "neye göre değişiyor"
        # sorusunun cevabı (pressure_drop_source).
        # Besleme sistemi yetersizliği uyarısı (varsa) — calculate() çıktısındaki
        # 'warnings' listesine eklenir; sessiz kalınmaz.
        self._feed_warning = None
        if pressure_drop > 0:
            self.delta_P_inj = pressure_drop
            # --- ÖH D35 / OH-ON-01 · ΔP'NİN KİMLİĞİ BEYANDAN GELİR --------
            # ÖLÇÜLDÜ (``docs/scofield/raw/OH/D35/onemli-hibrit-fizik/a1/
            # once.json``, koşul ``H1``): ürün yolunda ``pressure_drop``
            # HER koşuda doluydu (``advanced.html:4444``, gizli
            # ``designConfigPanel`` içindeki ``pressure_drop_percent``
            # value="20" → 0,20·Pc) ve bu dal onu koşulsuz
            # ``DP_SOURCE_USER`` diye künyeliyordu. Kullanıcı o alanı
            # EKRANDA GÖRMEMİŞTİ; künye "sizin verdiğiniz" diyordu.
            # Artık kaynak BEYANLA gelir: çağıran ΔP'yi nereden aldığını
            # söyler. Beyan yoksa eski ad korunur (bu modülün tek ürün
            # çağıranı olan ``app.py`` artık her zaman beyan gönderir).
            self.pressure_drop_source = _dp_kaynagi(pressure_drop_source)
        else:
            # NASA SP-8089 standardına göre optimum basınç düşümü
            min_delta_P = CHUG_DP_RATIO_MINIMUM * chamber_pressure   # alt sınır
            optimal_delta_P = CHUG_DP_RATIO_RECOMMENDED * chamber_pressure
            max_delta_P = 0.30 * chamber_pressure  # Maksimum %30

            # Tank basıncına göre optimize et
            available_delta_P = tank_pressure - chamber_pressure
            tank_limited = False
            if available_delta_P < min_delta_P:
                # v2.6.2 DÜZELTMESİ (fizik denetimi F015): eski kod besleme
                # sistemi yetersizken ΔP'yi YİNE 0.15·Pc'ye ZORLUYORDU ve
                # yalnız ekrana yazı basıyordu. Bu, VAR OLMAYAN bir basınç
                # düşümüyle boyutlandırma demektir: A = ṁ/(Cd√(2ρΔP)) küçük
                # çıkar, gerçekte teslim edilen debi hedefin çok altında kalır
                # (ölçüldü: P_tank=31 bar / Pc=30 bar → kod 4.5 bar kullanıyor,
                # mevcut olan 1.0 bar; alan 2.12 kat küçük, teslim debisi
                # hedefin ~%53 altında). Doğrusu: MEVCUT ΔP ile boyutlandır ve
                # SP-8089 kararlılık hedefinin tutmadığını açıkça bildir.
                # Kaynak: süreklilik + besleme basınç dengesi (Huzel & Huang
                # Böl. 4); SP-8089'un ΔP/Pc oranı bir HEDEFTİR, garanti değil.
                if available_delta_P <= 0:
                    raise ValueError(
                        f"Feed pressure ({tank_pressure:.1f} bar) does not "
                        f"exceed chamber pressure ({chamber_pressure:.1f} bar): "
                        "no injector pressure drop is available, so no flow can "
                        "be delivered. Raise the tank pressure or lower Pc.")
                self.delta_P_inj = available_delta_P
                tank_limited = True
                self._feed_warning = (
                    f"Feed system can only supply {available_delta_P:.2f} bar "
                    f"({available_delta_P / chamber_pressure * 100:.1f}% of Pc); "
                    f"NASA SP-8089 recommends "
                    f">={CHUG_DP_RATIO_MINIMUM * 100:.0f}% for chug "
                    f"stability. The injector is sized for the AVAILABLE "
                    f"drop, not the target.")
                print(f"Warning: {self._feed_warning}")
            elif available_delta_P > max_delta_P:
                self.delta_P_inj = optimal_delta_P
            else:
                self.delta_P_inj = min(optimal_delta_P, available_delta_P * 0.8)
                tank_limited = self.delta_P_inj < optimal_delta_P
            # Kendinden basınçlı N₂O'da tankın verebildiği ΔP doyma
            # basıncının sonucudur → 'saturation-driven'
            if tank_limited and self.oxidizer_type == 'n2o':
                self.pressure_drop_source = DP_SOURCE_SAT
            else:
                self.pressure_drop_source = DP_SOURCE_AUTO
        # Enjektör GİRİŞİ (orifisin üstü) — ΔP hangi istasyondan alındıysa
        # P₁ odur: P₁ = Pc + ΔP_inj. Kardeş modülün ``p1_bar`` değişkeniyle
        # aynı büyüklüktür (engines/injector_design.py: ``dp = P₁ − Pc``).
        # Kavitasyon hükmü (P10B1-22) bu istasyondan kurulur; tank basıncı
        # besleme hattı kayıplarını içerdiği için orifisin üstü DEĞİLDİR.
        self.injector_inlet_pressure_bar = self.P_c + self.delta_P_inj
        # --- ÖH D25 / P16B1-45 · DEŞARJ KATSAYISININ KİMLİĞİ -----------
        # ÖNCE (ölçüm: a3/once_A.json, once_BC.json): imza varsayılanı
        # ÇIPLAK ``0.7`` idi ve ``app.py`` onu
        # ``data.get('discharge_coefficient', 0.7)`` ile aynen geçiriyordu.
        # Sonuç, TEK bir /calculate yanıtında AYNI ADI taşıyan İKİ sayı:
        #   ``motor.injector_design.discharge_coefficient`` = 0,78
        #        (devre çözücüsü; kapılı + ``..._basis`` künyeli)
        #   ``injector.discharge_coefficient``              = 0,70
        #        (bu modül; kapısız, künyesiz)
        # Delik sayısı, delik çapı, enjeksiyon alanı ve (v2.6.26'dan beri)
        # CAD/STEP/DXF geometrisi İKİNCİSİNDEN türüyordu. Üstelik 0,70
        # ürünün KENDİ beyanına da aykırıydı: ``advanced.html`` alanının
        # ``placeholder``ı 0,78 ve ipucu metni "Leave empty to use the
        # solver default of 0.78, which is then declared in the results
        # instead of being silently assumed" diyor — yani ürün hem yanlış
        # sayıyı kullanıyor hem de söz verdiği beyanı yazmıyordu.
        #
        # SÖZLEŞME (kardeş ``plate_thickness`` kalemiyle — D20/P15B1-02 —
        # birebir aynı desen): ``None`` = "çağıran vermedi". Sayı o zaman
        # TEK kaynaktan gelir (``engines.injector_design`` Cd tablosunun
        # kendi varsayılan orifis tanımı) ve KAZANILMAMIŞ olduğu yanıtta
        # ``discharge_coefficient_earned`` / ``..._basis`` ile durur.
        # Yeni sayı YAZILMADI; 0,70 literali KALDIRILDI.
        self.C_d_earned = discharge_coefficient is not None
        if self.C_d_earned:
            self.C_d = float(discharge_coefficient)
            self.C_d_basis = (
                discharge_coefficient_basis
                or 'supplied by the caller (no basis text provided)')
        else:
            _cd_var, _cd_why = default_discharge_coefficient()
            self.C_d = float(_cd_var)
            self.C_d_basis = (
                f'module default via the circuit solver Cd table: {_cd_why}'
                f' - NOT earned: neither the request nor the circuit model '
                f'supplied a discharge coefficient for this plate')
        self.injector_type = injector_type

        # Type-specific parameters — varsayılanlar __init__'te doldurulur ki
        # setter çağrılmadan da calculate() çalışsın (test/robustluk)
        self.showerhead_params = {}
        self.pintle_params = {}
        self.swirl_params = {}
        self.impingement_params = {}
        self.coaxial_params = {}
        self.set_showerhead_params()
        self.set_pintle_params()
        self.set_swirl_params()
        self.set_impingement_params()
        self.set_coaxial_params()

    def set_showerhead_params(self, target_velocity=30, n_holes=0,
                            hole_diameter_min=None, hole_diameter_max=None,
                            plate_thickness=None,
                            injection_area_mm2=None,
                            injection_area_basis=None):
        """P15B1-02: ``plate_thickness=None`` = "çağıran vermedi".

        Sayı yine üretilir (modül varsayılanı, tek kaynak
        ``PLATE_THICKNESS_DEFAULT_MM``) ama KAZANILMAMIŞ olduğu taşınır;
        L/D hükmü aşağıda o bayrağa bakar.

        ÖH D37 A2 hibrit · F-10 (= CW-A5): ``hole_diameter_min/max=None`` de
        "çağıran vermedi" demektir → tek kaynaklı tasarım bandı
        (``hrma.constants.ORIFICE_D_BAND_MM``, künye ``ORIFICE_D_BAND_SOURCE``).
        Eski imza varsayılanı 0,3/2,0 mm literaliydi ve kaynağı yoktu;
        ÖLÇÜLDÜ (A2 hibrit a1 once K1): bu yol Ornek-H1'in 3 × Ø2,1115 mm
        kanon planına "outside the manufacturing band (0.30-2.00 mm)" derken
        devre çözücüsü aynı planı 0,5-2,5 içinde buluyordu.
        """
        hole_diameter_min = (ORIFICE_D_BAND_MM[0] if hole_diameter_min is None
                             else hole_diameter_min)
        hole_diameter_max = (ORIFICE_D_BAND_MM[1] if hole_diameter_max is None
                             else hole_diameter_max)
        # --- ÖH D28 a2 / P16B1-46 · DELİK SAYISININ İŞARETİ YUTULMAZ -----
        # ÖLÇÜLDÜ (taban ``7cd08bcc``, ``a2/once.json`` K3): ``n_holes =
        # -12`` gövdesi ``POST /calculate``ta HTTP 200 alıyor ve enjektör
        # 280 delikle boyutlandırılıyordu — ``n_holes = 1e9`` ile BİREBİR
        # AYNI yanıt. Zincir şu: ``d_h = 2*sqrt(A/(n*pi))`` negatif n için
        # NaN üretiyor ("invalid value encountered in sqrt"), ``max(d_min,
        # min(NaN, d_max))`` NaN'ı yutup ``d_min``e düşüyor, sonra delik
        # sayısı imalat bandından YENİDEN ÇÖZÜLÜYOR. Yani kullanıcının
        # işareti bir NaN üzerinden sessizce kayboluyordu.
        #
        # Sözleşme: 0 "sen çöz" demektir (``_calculate_showerhead`` bunu
        # açıkça böyle okur) ve KORUNUR. Negatif ya da tam sayı olmayan
        # delik sayısı ise bir ölçüm değil, imkânsız bir girdidir: sayı
        # uydurulmaz, alan ADIYLA reddedilir (doktrin 1).
        if isinstance(n_holes, bool):
            raise InjectorPlateInputError(
                "'n_holes' must be a whole number of orifices (got bool)")
        try:
            _n_sayi = float(n_holes)
        except (TypeError, ValueError):
            raise InjectorPlateInputError(
                f"'n_holes' must be a number (got {n_holes!r})")
        if not math.isfinite(_n_sayi):
            raise InjectorPlateInputError(
                f"'n_holes' must be a finite number (got {n_holes!r})")
        if _n_sayi < 0:
            raise InjectorPlateInputError(
                f"'n_holes' cannot be negative; got {_n_sayi:g}. An orifice "
                'count is a physical count of holes in the plate. Send 0 to '
                'let the solver choose the hole count.')
        if _n_sayi != int(_n_sayi):
            raise InjectorPlateInputError(
                f"'n_holes' must be a whole number of orifices; got "
                f'{_n_sayi:g}.')
        n_holes = int(_n_sayi)

        # --- ÖH D35 / OH-ON-01 · KANON ORİFİS ALANI ---------------------
        # ÖLÇÜLDÜ (``a1/once.json`` H1): aynı ``/calculate`` yanıtında iki
        # enjektör planı duruyordu — devre çözücüsü 3 × Ø2,1115 mm
        # (toplam 10,5053 mm², ΔP 30,5434 bar), bu modül 32 × Ø0,9055 mm
        # (20,6078 mm², ΔP 4 bar). İkisi AYNI ΔP'de bile eşitlenemez,
        # çünkü devre çözücüsü N₂O'da Dyer NHNE iki-faz debisini, bu
        # modül ise sıkıştırılamaz orifis bağıntısını
        # (``A = ṁ/(Cd·√(2ρΔP))``) kullanır; ölçülen fark %40,9'dur.
        # Geometri TEK KAYNAKTAN gelmek zorundadır: çağıran çözücünün
        # toplam orifis alanını verirse bu modül onu YENİDEN TÜRETMEZ,
        # tüketir — türev büyüklükleri (hız, Weber, Re, L/D, kavitasyon)
        # o geometriden tutarlı biçimde üretir.
        _alan_m2 = None
        if injection_area_mm2 is not None:
            _alan = finite_number(injection_area_mm2)
            if _alan is None or _alan <= 0:
                raise InjectorPlateInputError(
                    f"'injection_area_mm2' must be a finite positive orifice "
                    f'area in mm^2 (got {injection_area_mm2!r})')
            _alan_m2 = float(_alan) * 1e-6

        kazanildi = plate_thickness is not None
        t_mm = (float(plate_thickness) if kazanildi
                else PLATE_THICKNESS_DEFAULT_MM)
        self.showerhead_params = {
            'v_target': target_velocity,
            'n_holes': n_holes,
            'A_inj_canon': _alan_m2,
            'A_inj_canon_basis': (injection_area_basis
                                  if _alan_m2 is not None else None),
            'd_min': hole_diameter_min / 1000,  # Convert mm to m
            'd_max': hole_diameter_max / 1000,
            't_plate': t_mm / 1000,
            't_plate_earned': kazanildi,
            't_plate_basis': (
                'caller-supplied plate thickness (orifice length)'
                if kazanildi else
                f'module default ({PLATE_THICKNESS_DEFAULT_MM:.1f} mm) — the '
                'caller supplied no plate thickness / orifice length'),
        }

    def set_pintle_params(self, outer_diameter=None, pintle_diameter=None,
                          secondary_holes='radial', radial_hole_count=None,
                          radial_hole_diameter=None, annular_gap=None,
                          skip_distance=None, tangential_angle=None,
                          canon_geometry=None, canon_basis=None):
        """Pintle parametreleri (mm / adet / derece; ``None`` = verilmedi).

        V301/E1 — TEK KANONİK GEOMETRİ. ``canon_geometry`` devre çözücüsünün
        (``engines/injector_design.py::design_injector`` →
        ``resolve_pintle_geometry``) yayımladığı ``pintle_geometry``dir;
        verilirse bu blok onu TÜKETİR ve hiçbir ölçüyü yeniden türetmez
        (showerhead ``A_inj_canon`` deseni, ÖH D35 / OH-ON-01). Verilmezse
        (devre çözülemedi ya da modül doğrudan kullanılıyor) AYNI çözücü bu
        modülün kendi sıkıştırılamaz orifis alanıyla çağrılır ve kaynak
        ``pintle_geometry_source`` alanında ADIYLA yazılır.

        Boş ölçü = çözücü boyutlandırır: ``pintle_diameter`` akıştan;
        ``outer_diameter`` (enjektör GÖVDESİNİN dış çapı) HİÇ
        boyutlandırılmaz, beyan edilir. ``secondary_holes``: ``none`` (uçta
        delik yok → eleman anüler enjektördür), ``radial`` (varsayılan),
        ``tangential`` (teğetsel momentum MODELLENMEZ, beyan). v2.6.27'de
        tanınmayan kip sessizce 'radial'e çevriliyordu; artık çözücünün
        kapısından adıyla döner (``PintleGeometryInputError``).
        """
        istek = (('secondary_holes', secondary_holes),
                 ('d_pintle_mm', pintle_diameter),
                 ('annulus_gap_mm', annular_gap),
                 ('n_radial_holes', radial_hole_count),
                 ('radial_hole_d_mm', radial_hole_diameter),
                 ('skip_distance_mm', skip_distance),
                 ('housing_outer_diameter_mm', outer_diameter),
                 ('tangential_angle_deg', tangential_angle))
        self.pintle_params = {
            'pin': {ad: deger for ad, deger in istek if deger is not None},
            'canon': (dict(canon_geometry)
                      if isinstance(canon_geometry, dict) else None),
            'canon_basis': canon_basis,
        }
        self._pintle_onbellek = None

    def pintle_geometry(self):
        """``(geometri, kanon_mu, kaynak)`` — kanon ya da aynı çözücü.

        Önbelleklidir (uç kapısı ve ``calculate`` aynı sonucu kullanır).
        Geçersiz/tutarsız ölçüde ``PintleGeometryInputError`` yükseltir; uç
        onu 422'ye çevirir.
        """
        if getattr(self, '_pintle_onbellek', None) is not None:
            return self._pintle_onbellek
        p = self.pintle_params
        if p.get('canon'):
            sonuc = (dict(p['canon']), True,
                     p.get('canon_basis') or DP_SOURCE_SOLVER)
        else:
            a_toplam = self.mdot_ox / (
                self.C_d * np.sqrt(2 * self.rho_ox * self.delta_P_inj * 1e5))
            sonuc = (resolve_pintle_geometry(a_toplam, p['pin'],
                                             mdot_target_kg_s=self.mdot_ox),
                     False,
                     'incompressible orifice equation A = mdot/(Cd*sqrt('
                     '2*rho*dP)) of this module (no injector circuit '
                     'solution was supplied), sized by the same pintle '
                     'resolver')
        self._pintle_onbellek = sonuc
        return sonuc

    def set_swirl_params(self, n_slots=6, slot_width=0, slot_height=0,
                         chamber_diameter=0, target_half_angle=0,
                         canon_element=None):
        """Swirl parametreleri. chamber_diameter [mm] verilirse D_s olarak
        K = A_p/(D_s·d_o) bağıntısında kullanılır (verilmezse eski
        D_s = 2.5·d_o oranı). target_half_angle [derece] verilirse sentez
        yolunda hedef sprey yarı açısı olur (verilmezse 45°). İkisi de
        v2.6.26'ya kadar arayüzde olup HİÇBİR yere bağlı olmayan ölü
        alanlardı."""
        self.swirl_params = {
            'n_slots': n_slots,
            'w': slot_width / 1000 if slot_width > 0 else None,
            'h': slot_height / 1000 if slot_height > 0 else None,
            'D_s': chamber_diameter / 1000 if chamber_diameter > 0 else None,
            'theta_target': (float(target_half_angle)
                             if target_half_angle and target_half_angle > 0
                             else None),
            # V301/E2: devrenin swirl elemanı (KANON). Verilirse eleman
            # sayısı, çıkış orifis çapı, K/X/Cd/θ, oda çapı ve teğet giriş
            # alanı ondan TÜKETİLİR; bu blok yalnız dikdörtgen yuva ölçüsünü
            # (verilmediyse) aynı giriş alanından türetir.
            'canon': (dict(canon_element) if isinstance(canon_element, dict)
                      else None),
        }

    def set_impingement_params(self, n_pairs=0, impingement_angle=2 * IMPINGEMENT_HALF_ANGLE_DEG,
                               hole_diameter_min=None, hole_diameter_max=None,
                               plate_thickness=None, canon_plan=None):
        """Like-on-like doublet parametreleri (tek akışkan, kendi içinde çarpışan).

        P15B1-02 ikizi: plaka kalınlığı verilmediyse sayı modül
        varsayılanıdır ve L/D hükmü ondan ÜRETİLMEZ (showerhead ile aynı
        sözleşme; ürün yolunda ``app.py`` bu alanı hiç göndermiyor).

        F-10 ikizi (ÖH D37 A2 hibrit): delik çapı bandı verilmediyse tek
        kaynaklı ``ORIFICE_D_BAND_MM`` — eski 0,3/2,0 literali kalktı.
        """
        hole_diameter_min = (ORIFICE_D_BAND_MM[0] if hole_diameter_min is None
                             else hole_diameter_min)
        hole_diameter_max = (ORIFICE_D_BAND_MM[1] if hole_diameter_max is None
                             else hole_diameter_max)
        kazanildi = plate_thickness is not None
        t_mm = (float(plate_thickness) if kazanildi
                else IMPINGEMENT_PLATE_THICKNESS_DEFAULT_MM)
        self.impingement_params = {
            'n_pairs': int(n_pairs),
            'full_angle_deg': impingement_angle,
            # V301/E2: devrenin benzer-akışkan çift planı (KANON). Verilirse
            # delik sayısı, çapı, alanı ve açı ondan TÜKETİLİR; bu blok
            # yeniden boyutlandırmaz (showerhead ``_kanon_plan`` / E1 deseni).
            'canon': (dict(canon_plan) if isinstance(canon_plan, dict)
                      else None),
            'd_min': hole_diameter_min / 1000,
            'd_max': hole_diameter_max / 1000,
            't_plate': t_mm / 1000,
            't_plate_earned': kazanildi,
            't_plate_basis': (
                'caller-supplied plate thickness (orifice length)'
                if kazanildi else
                'module default '
                f'({IMPINGEMENT_PLATE_THICKNESS_DEFAULT_MM:.1f} mm) — the '
                'caller supplied no plate thickness / orifice length'),
        }

    def set_coaxial_params(self, inner_flow_fraction=COAX_INNER_FLOW_FRACTION,
                           wall_thickness=0, inner_flow_fraction_source=None,
                           canon_element=None):
        """Koaksiyel (iç jet + dış anülüs, tek akışkan hibrit ox) parametreleri.

        V301/E2: pay ``COAX_INNER_FLOW_FRACTION_BAND`` dışındaysa SESSİZCE
        kırpılmaz (eskiden ``min(max(f, 0,1), 0,9)``): ``ValueError``. Uç
        (/calculate) aynı bandı 422 ile adıyla reddeder.

        V301/H2: ``canon_element`` devrenin ``coaxial_geometry`` sözlüğüdür
        (``design_coaxial_element``); verilirse blok toplam alanı, payı ve
        geometriyi ONDAN tüketir (ekran = devre)."""
        f = finite_number(inner_flow_fraction)
        lo, hi = COAX_INNER_FLOW_FRACTION_BAND
        if f is None or not (lo <= f <= hi):
            raise ValueError(
                f'inner_flow_fraction must be a finite number in [{lo:g}, '
                f'{hi:g}] (got {inner_flow_fraction!r}); it is not clamped. '
                + COAX_INNER_FLOW_FRACTION_BASIS)
        self.coaxial_params = {
            'f_inner': float(f),
            'f_inner_source': inner_flow_fraction_source,
            't_wall': wall_thickness / 1000 if wall_thickness > 0 else None,
            'canon': (dict(canon_element) if isinstance(canon_element, dict)
                      else None),
        }

    def calculate(self):
        if self.injector_type == 'showerhead':
            return self._calculate_showerhead()
        elif self.injector_type == 'pintle':
            return self._calculate_pintle()
        elif self.injector_type == 'swirl':
            return self._calculate_swirl()
        elif self.injector_type == 'impingement':
            return self._calculate_impingement()
        elif self.injector_type == 'coaxial':
            return self._calculate_coaxial()
        else:
            raise ValueError(f"Unknown injector type: {self.injector_type}")

    # ------------------------------------------------------------------
    # Ortak çıktı sözleşmesi — TÜM tipler bu anahtarları döndürür
    # (discharge_coefficient, l_d_ratio, injection_area, weber_number,
    #  pressure_drop_bar, pressure_drop_source, density_source)
    # ------------------------------------------------------------------
    def _common_outputs(self, injection_area_m2, v_exit, d_char_m, l_d_ratio,
                        l_d_earned=None, l_d_basis=None):
        """d_char_m: atomizasyon karakteristik boyutu (delik çapı, anülüs
        boşluğu veya yuva hidrolik çapı) — Weber sayısında kullanılır.

        ``l_d_earned`` / ``l_d_basis`` (ÖH D20 / P15B1-02): L/D'nin
        kullanıcının plakasından mı yoksa modül varsayılanından mı geldiği
        yanıtta DURUR. L/D'si olmayan dallarda (anülüs, film, swirl) ikisi
        de ``None``'dır — orada L/D tanımlı değildir, kazanılmamış değil."""
        sigma = SIGMA_OX.get(self.oxidizer_type, SIGMA_OX_DEFAULT)
        # Z1 / künye dürüstlüğü: tabloda karşılığı OLMAYAN akışkanda (h2o2,
        # n2o4, unspecified) kullanılan σ bir VARSAYIMDIR ve öyle bildirilir —
        # sessizce N₂O'nun ya da LOX'un değeri verilmez.
        sigma_basis = ('table (%s reference state, NIST SRD 69)'
                       % self.oxidizer_type
                       if self.oxidizer_type in SIGMA_OX else
                       'generic assumption (no surface-tension table entry '
                       'for %r; the value is NOT taken from another fluid)'
                       % self.oxidizer_type)
        weber = self.rho_ox * v_exit ** 2 * d_char_m / sigma
        return {
            'discharge_coefficient': self.C_d,
            # P16B1-45: sayı artık gerekçesiyle YAYIMLANIYOR. Plaka
            # bloğundaki diğer yedi büyüklüğün (yoğunluk, viskozite, σ,
            # P_v, ΔP, L/D, plaka kalınlığı) künyesi vardı; geometriyi
            # doğrudan belirleyen Cd künyesizdi.
            'discharge_coefficient_basis': self.C_d_basis,
            'discharge_coefficient_earned': self.C_d_earned,
            'l_d_ratio': (float(l_d_ratio) if l_d_ratio is not None else None),
            'l_d_ratio_earned': l_d_earned,
            'l_d_ratio_basis': l_d_basis,
            'injection_area': injection_area_m2 * 1e6,  # mm²
            'weber_number': float(weber),
            'surface_tension': sigma,  # N/m (Weber hesabında kullanılan)
            'surface_tension_basis': sigma_basis,
            'viscosity_basis': getattr(self, 'viscosity_basis', None),
            'pressure_drop': self.delta_P_inj,       # bar (eski ad — korunur)
            'pressure_drop_bar': self.delta_P_inj,   # bar (sözleşme adı)
            'pressure_drop_source': self.pressure_drop_source,
            'density_source': self.density_source,
            'oxidizer_type': self.oxidizer_type,
            # ÖH Z5S / P10-A (P10B1-21/-22): kavitasyon hükmünün DAYANAĞI
            # artık raporda durur — kardeş modülün (engines/injector_design.py)
            # 'vapor_pressure_bar' / 'vapor_pressure_basis' anahtarlarıyla
            # AYNI sözleşme. Buhar basıncı çözülemediğinde sayı None'dır ve
            # künye bunun NEDENİNİ söyler (uydurma sayı basılmaz).
            'vapor_pressure_bar': self.p_vapor_bar,
            'vapor_pressure_basis': (self.p_vapor_basis
                                     or self.p_vapor_unavailable_reason),
            # Orifisin ÜSTÜNDEKİ basınç [bar] — K_c bu istasyondan kurulur.
            'injector_inlet_pressure_bar': self.injector_inlet_pressure_bar,
        }

    # ------------------------------------------------------------------
    # Ortak hız tanımı (v2.6.2 fizik denetimi F042)
    # ------------------------------------------------------------------
    @staticmethod
    def _exit_velocity(mdot, rho, area_m2):
        """Süreklilikten ortalama enjeksiyon hızı: v = ṁ/(ρ·A) [m/s].

        Raporlanan alan A = ṁ/(Cd√(2ρΔP)) GEOMETRİK alandır; bu alan üzerinden
        ortalama hız Cd·√(2ΔP/ρ)'dir. Eski kod ideal (vena contracta) hızı
        √(2ΔP/ρ) raporluyordu; bu, 'exit_velocity' ile 'injection_area'yı
        birbiriyle TUTARSIZ yapıyordu (ṁ = ρ·A·v sağlanmıyordu) ve hız 1/Cd
        kat, Weber sayısı 1/Cd² kat (Cd=0.7'de 2.04 kat) şişiyordu. Kardeş
        modül hrma/engines/injector_design.py::_solve_circuit AYNI büyüklük
        için Cd·√(2ΔP/ρ) kullanıyor — iki modül artık aynı tanımda.
        Kaynak: Sutton & Biblarz Böl. 8 (orifis akışı, Cd ve süreklilik).
        """
        return float(mdot / max(rho * area_m2, 1e-12))

    def _calculate_showerhead(self):
        # Correct orifice equation: mdot = Cd * A * sqrt(2 * rho * delta_P)
        delta_P_Pa = self.delta_P_inj * 1e5
        params = self.showerhead_params
        # --- ÖH D35 / OH-ON-01 · GEOMETRİ TEK KAYNAKTAN ------------------
        # Çağıran devre çözücüsünün toplam orifis alanını verdiyse o KANON
        # alandır: burada ikinci bir alan TÜRETİLMEZ (bkz. setter künyesi).
        A_inj_canon = params.get('A_inj_canon')
        kanon_plan = A_inj_canon is not None and A_inj_canon > 0
        if kanon_plan:
            A_inj_required = float(A_inj_canon)
        else:
            A_inj_required = self.mdot_ox / (
                self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))

        # Optimize holes if not specified
        if params['n_holes'] == 0:
            n_holes, d_h = self._optimize_showerhead_holes(A_inj_required, params)
        else:
            n_holes = params['n_holes']
            d_h = 2 * np.sqrt(A_inj_required / (n_holes * np.pi))

        # Check constraints — çapı imalat bandına oturt (denetim bulgusu #118).
        # Çap kırpılırsa SABİT n_holes ile alan hedef debiyi karşılamaz
        # (ṁ = Cd·A·√(2ρΔP)); bu yüzden teslim debisini korumak için delik
        # SAYISI yeniden çözülür: n = ceil(A_gerekli / delik_alanı). Aksi halde
        # gerçek mdot_ox hedeften sapıp O/F ve performans yanlış hesaplanır.
        # --- ÖH D35 / OH-ON-01 · KANON PLAN KIRPILMAZ, BEYAN EDİLİR -----
        # Kanon geometri geldiğinde imalat bandı kırpması bir İKİNCİ plan
        # üretirdi (ölçüldü: 3 × Ø2,1115 mm kanon planı, d_max = 2,0 mm
        # bandına kırpılınca 4 × Ø2,0 mm'ye dönüşüyor) ve kusur adını
        # değiştirerek geri gelirdi. Kanon planda sayı DEĞİŞTİRİLMEZ;
        # bandın dışına düşen çap ADIYLA bildirilir (ürünün kendi
        # varsayılan bandı da bir varsayımdır, geometrinin hakemi değil).
        kanon_bant_kaydi = []
        if kanon_plan:
            # ÖH D37 A2 hibrit · 5. tur Ş-4: "bant dışı" hükmü devre
            # çözücüsüyle aynı işlevden (``classify_orifice_d``); eşik burada
            # yeniden yazılmaz. Ölçüldü (denetim-4): aynı yanıtta devre
            # 0,47 mm için "alt sınıra yakın", bu yol "bant dışı" diyordu.
            # Bu yol yalnız bant DIŞI sınıfı yayımlar (metin ve TR deseni
            # i18n_charts.js'te sabit); "alt kenara yakın" alt sınıfı devre
            # uyarısıyla (``orifice_d_near_manufacturing_min``) gider.
            if classify_orifice_d(d_h, params['d_min'], params['d_max']) in (
                    ORIFICE_D_CLASS_BELOW, ORIFICE_D_CLASS_ABOVE):
                kanon_bant_kaydi.append(
                    f"Solved orifice diameter {d_h * 1000:.{_kanon_cap_ondaligi(d_h, params)}f} mm is outside "
                    f"the manufacturing band "
                    f"({params['d_min'] * 1000:.2f}-"
                    f"{params['d_max'] * 1000:.2f} mm). The hole plan comes "
                    f"from the injector circuit solution and is NOT resized "
                    f"here: resizing would publish a second, different "
                    f"injector in the same answer. Either widen the band or "
                    f"change the feed pressure / orifice count.")
            d_h_clamped = d_h
        else:
            d_h_clamped = max(params['d_min'], min(d_h, params['d_max']))
        # ÖH D28 a2 / P16B1-46 — KIRPMA GEREKÇESİ DOĞRU KANALA GİDER.
        # ÖLÇÜLDÜ (taban ``7cd08bcc``, ``a2/once.json`` K3): bu gerekçe
        # YALNIZ ``warnings.warn`` ile Python uyarı akışına (sunucu
        # günlüğüne) yazılıyordu; ``/calculate`` yanıtındaki
        # ``injector.warnings`` dizisinde bulunmuyordu. Kullanıcı 40 delik
        # istemişken 280 delikli bir plaka okuyor ve NEDENİNİ göremiyordu.
        # Metin TEK yerde kurulur ve İKİ kanala da o metin gider.
        kirpma_kaydi = []
        kirpildi = not np.isclose(d_h_clamped, d_h, rtol=1e-9)
        if kirpildi:
            area_per_hole = np.pi * (d_h_clamped / 2)**2
            n_istenen = n_holes
            n_holes = max(4, int(np.ceil(A_inj_required / area_per_hole)))
            # 9. tur (Devir 36): "preserve target flow rate" iddiası kalktı;
            # metin + teslim cümlesi ``_showerhead_clamp_text`` (modül sonu).
            _kirpma_metni = _showerhead_clamp_text(
                self, params, n_holes, n_istenen, area_per_hole,
                A_inj_required, delta_P_Pa)
            kirpma_kaydi.append(_kirpma_metni)
            warnings.warn(_kirpma_metni)
        d_h = d_h_clamped

        # Recalculate with final values
        A_inj = n_holes * np.pi * (d_h/2)**2
        # Süreklilikten hız (F042): ṁ = ρ·A·v — ideal Bernoulli hızı DEĞİL
        v_exit = self._exit_velocity(self.mdot_ox, self.rho_ox, A_inj)

        # Reynolds number hesaplaması - doğru formül ve birimler
        # Re = ρ * v * D / μ
        # ρ: kg/m³, v: m/s, D: m, μ: Pa·s = kg/(m·s)
        # N2O sıvısı için 20°C'de viskozite: ~0.0002 Pa·s

        # Viskozite (denetim bulgusu #132): self.mu_ox NIST/CoolProp'tan zaten
        # enjeksiyon sıcaklığında (oxidizer_temp) alınıyor, o yüzden EK sıcaklık
        # düzeltmesi uygulanmaz — çift-sayım olur. Eski kod gaz kinetik
        # teorisinin √T ölçeklemesini (μ sıcaklıkla ARTAR) uyguluyordu; oysa
        # sıvılarda viskozite sıcaklıkla AZALIR (Andrade: μ ∝ exp(B/T)) — yön
        # de yanlıştı. Doğru değer doğrudan mu_ox'tur.
        mu_corrected = self.mu_ox

        Re = self.rho_ox * v_exit * d_h / mu_corrected

        # Fiziksel kontrol - Reynolds sayısı 1000-200000 arası olmalı
        if Re < 1000:
            print(f"WARNING: Low Reynolds number ({Re:.0f}), flow may be laminar")
        elif Re > 200000:
            print(f"WARNING: Very high Reynolds number ({Re:.0f}), review the design")

        # L/D ratio
        L_D = params['t_plate'] / d_h
        # ÖH D20 / P15B1-02: L/D bandı hükmü KAZANILMIŞ plakadan verilir.
        # Kazanılmamışsa hüküm alıkonur ve NEDENİ söylenir — sessiz kalmak
        # "L/D'niz uygun" demenin örtülü hâliydi.
        ld_kazanildi = bool(params.get('t_plate_earned'))
        warn_list = self._check_warnings(v_exit, Re,
                                         L_D if ld_kazanildi else None)
        # ÖH D28 a2 / P16B1-46 — imalat bandı kırpması yanıtta da durur.
        warn_list.extend(kirpma_kaydi)
        # ÖH D35 / OH-ON-01 — kanon planın bant ihlali de yanıtta durur.
        warn_list.extend(kanon_bant_kaydi)
        if not ld_kazanildi:
            warn_list.append(LD_NOT_ISSUED_WARNING)
        # Hedef hız girdisi (F129): hız delik sayısıyla DEĞİL, ΔP ve Cd ile
        # belirlenir. Kullanıcının hedefi tutmuyorsa gereken ΔP bildirilir —
        # girdiyi sessizce yutmak yerine ne yapılması gerektiği söylenir.
        v_target = params.get('v_target')
        dp_needed_bar = None
        if v_target and v_target > 0:
            dp_needed_bar = (self.rho_ox * v_target ** 2
                             / (2.0 * self.C_d ** 2)) / 1e5
            if abs(v_exit - v_target) > 0.05 * v_target:
                warn_list.append(
                    f"Target injection velocity ({v_target:.1f} m/s) is not set "
                    f"by hole count: with Cd={self.C_d:.2f} the achieved "
                    f"velocity is {v_exit:.1f} m/s. Reaching the target needs "
                    f"dP = {dp_needed_bar:.2f} bar (currently "
                    f"{self.delta_P_inj:.2f} bar).")

        result = {
            'type': 'showerhead',
            'n_holes': n_holes,
            'hole_diameter': d_h * 1000,  # mm
            'plate_thickness': _yayin_plaka_mm(params, ld_kazanildi),  # mm
            'plate_thickness_earned': ld_kazanildi,
            'plate_thickness_basis': params.get('t_plate_basis'),
            'L_D_ratio': (L_D if ld_kazanildi else None),  # eski ad — geriye dönük uyum için korunur
            'exit_velocity': v_exit,
            'target_velocity': (float(v_target) if v_target else None),
            'pressure_drop_for_target_velocity_bar': (
                float(dp_needed_bar) if dp_needed_bar is not None else None),
            'reynolds_number': Re,
            # ÖH D35 / OH-ON-01: delik planının KİMLİĞİ yanıtta durur.
            # 'injector circuit solution' = geometri devre çözücüsünden
            # tüketildi (tek kaynak); 'incompressible orifice equation' =
            # bu modül kendi bağıntısıyla boyutlandırdı.
            'orifice_plan_source': (
                (params.get('A_inj_canon_basis') or DP_SOURCE_SOLVER)
                if kanon_plan else
                'incompressible orifice equation A = mdot/(Cd*sqrt(2*rho*dP))'),
            'orifice_plan_is_canon': bool(kanon_plan),
            'warnings': warn_list
        }
        result.update(self._common_outputs(
            A_inj, v_exit, d_h, (L_D if ld_kazanildi else None),
            l_d_earned=ld_kazanildi,
            l_d_basis=params.get('t_plate_basis')))
        # ÖH D37 A2 hibrit · 7. tur (karar §28-25): kırpılan kanon DIŞI planın
        # hedef debi sınıfı. Delik sayısı ⌈A/a⌉ ve max(4, …) tabanıyla
        # yeniden çözüldüğü için teslim alanı gerekenden büyük olabilir;
        # kanon plan ve kırpılmayan plan bu denetime HİÇ girmez (bit-aynı).
        if kirpildi:
            hedef_debi = self._target_flow_check(A_inj, A_inj_required,
                                                 delta_P_Pa)
            if hedef_debi is not None:
                result['target_flow_check'] = hedef_debi
        return result

    def _calculate_pintle(self):
        """Pintle enjektör — uç delik sırası + anülüs (tek akışkan, hibrit).

        v2.6.27 (B3) bu dalı çıplak anülüsten radyal delikli modele taşımıştı
        ama ekran bloğu yine KENDİ geometrisini kuruyordu: pintle çapı formun
        boş alanına düşen uç yedeğiydi (25 mm, motor boyutundan bağımsız) ve
        aynı yanıtın devre çözücüsü başka bir çapla başka bir delik planı
        yayımlıyordu. V301/E1 ÖLÇÜMÜ (``docs/scofield/raw/OH/V301/ayberk1/
        enjektor-pintle/once.json``, 1 kN / Pc 20 bar / N2O-HTPB):

            ekran : D_p 25 mm    437 × Ø0,104 mm  anülüs 0,047 mm
            devre : D_p 5,639 mm  16 × Ø0,646 mm  anülüs 0,282 mm
            motor özeti: number_of_orifices = 3 (eşdeğer düz orifis planı)

        Kullanıcı üç sayı görüyordu ve ekrandaki imal edilemezdi.

        Artık geometri ``pintle_geometry()``den gelir: devre çözücüsünün
        kanonu (``resolve_pintle_geometry``) ya da — kanon yoksa — aynı
        çözücü bu modülün alanıyla. Burada HİÇBİR ölçü yeniden türetilmez;
        imalat bandı dışı ölçü KIRPILMAZ, adıyla bildirilir (kırpmak aynı
        yanıtta ikinci bir enjektör yayımlamak olurdu — showerhead kanon
        planının kuralı). Hız süreklilikten, Re anülüs boşluğundan.

        ``outer_diameter`` GÖVDE (housing) dış çapıdır; verilmediyse ``None``
        yayımlanır ve gövde boyutlandırılmaz (``housing_basis``). Kılıf
        deliği D_bore = D_p + 2t her zaman yayımlanır.
        """
        geo, kanon, kaynak = self.pintle_geometry()
        pg = dict(geo)
        secim = pg['secondary_holes']
        gap = pg['annulus_gap_mm'] / 1000.0
        a_inj = pg['total_flow_area_mm2'] * 1e-6
        extra_warnings = []

        if secim == 'none':
            extra_warnings.append(
                "Secondary holes set to 'none': the pintle tip has no radial "
                "jets, so this is an annular injector, not a pintle. TMR and "
                "the pintle spray-cone correlation do not apply and are not "
                "reported.")
        elif secim == 'tangential':
            extra_warnings.append(
                "Secondary holes set to 'tangential': HRMA sizes the holes "
                "(count, diameter, area) but does not model the tangential "
                "momentum component or the swirl it induces. The reported "
                "spray half-angle is the radial-injection value, i.e. a lower "
                "bound for the real cone.")

        # --- İmalat hükümleri: kanon KIRPILMAZ, beyan edilir --------------
        if not (PINTLE_GAP_MIN_M <= gap <= PINTLE_GAP_MAX_M):
            extra_warnings.append(
                f"Annulus gap ({gap * 1e3:.3f} mm) falls outside the "
                f"manufacturing band "
                f"({PINTLE_GAP_MIN_M * 1e3:.1f}-{PINTLE_GAP_MAX_M * 1e3:.1f} mm). "
                f"The pintle geometry is NOT resized here: resizing would "
                f"publish a second, different injector in the same answer. "
                f"Change the pintle diameter or the annular gap.")
        d_delik = pg['radial_hole_d_mm']
        if secim != 'none' and d_delik < PINTLE_GAP_MIN_M * 1e3:
            if pg['sizing_sources'].get('d_pintle_mm') == 'request':
                surucu = (
                    f"The supplied pintle diameter "
                    f"({pg['d_pintle_mm']:.1f} mm) is the driver; the "
                    f"flow-sized diameter for this mass flow is "
                    f"{pg['flow_sized_d_pintle_mm']:.2f} mm "
                    f"({pg['flow_sized_n_radial_holes']} x "
                    f"{pg['flow_sized_radial_hole_d_mm']:.3f} mm).")
            else:
                surucu = ("Fix fewer holes (pintle_radial_hole_count) or a "
                          "larger hole diameter.")
            extra_warnings.append(
                f"Pintle radial holes come out at {d_delik:.3f} mm across "
                f"{pg['n_radial_holes']} holes, below the "
                f"{PINTLE_GAP_MIN_M * 1e3:.2f} mm feature limit this module "
                f"declares for pintle geometry: the tip is not manufacturable "
                f"as drawn. " + surucu)
        elif secim != 'none' and pg.get('radial_hole_d_band_class') in (
                ORIFICE_D_CLASS_BELOW, ORIFICE_D_CLASS_ABOVE):
            lo, hi = pg['radial_hole_d_band_mm']
            extra_warnings.append(
                f"Pintle hole diameter {d_delik:.3f} mm is outside the "
                f"orifice design band ({lo:.2f}-{hi:.2f} mm, "
                f"{pg['radial_hole_d_band_source'].split(':')[0]}); the hole "
                f"plan is NOT resized here.")
        if secim != 'none' and not (
                PINTLE_BF_BAND[0] <= pg['bf'] <= PINTLE_BF_BAND[1]):
            extra_warnings.append(
                f"Pintle blockage factor BF = {pg['bf']:.3f} is outside the "
                f"HRMA design band {PINTLE_BF_BAND[0]:.2f}-"
                f"{PINTLE_BF_BAND[1]:.2f} (band source not verified; it is "
                f"not in Dressler & Bauer, AIAA 2000-3871).")

        # Teslim debisi: aynı ΔP, aynı Cd ve aynı kütle akısı modelinde ṁ ∝ A;
        # kanonun alan oranı (``flow_match.area_ratio``) 1'den yalnız aşırı
        # belirlenmiş ve tolerans içinde kalan geometride ayrılır.
        mdot_delivered = self.mdot_ox * pg['flow_match']['area_ratio']
        # Süreklilikten hız (F042): v = ṁ/(ρ·A) — ideal Bernoulli hızı DEĞİL
        v_exit = self._exit_velocity(mdot_delivered, self.rho_ox, a_inj)
        # Reynolds sayısı — karakteristik boyut anülüs boşluğu
        Re = self.rho_ox * v_exit * gap / self.mu_ox

        result = {
            'type': 'pintle',
            # mm; GÖVDE dış çapı — verilmediyse None (boyutlandırılmadı)
            'outer_diameter': pg['housing_outer_diameter_mm'],
            'pintle_diameter': pg['d_pintle_mm'],          # mm (D_p)
            'gap': pg['annulus_gap_mm'],                   # mm (t)
            'annulus_bore_diameter': pg['annulus_bore_diameter_mm'],  # mm
            'body_wall_thickness': pg['housing_wall_mm'],  # mm ya da None
            'housing_sized': pg['housing_sized'],
            'annular_area': pg['annulus_area_mm2'],        # mm² (eski ad)
            # Uç geometrisi TEK sözlükte: delik sırası, BF, L_s, akış payı,
            # TMR, sprey yarı açısı, gövde ve künyeler (kanonun kendisi).
            'pintle_geometry': pg,
            'pintle_geometry_source': kaynak,
            'pintle_geometry_is_canon': bool(kanon),
            'delivered_mdot': mdot_delivered,  # kg/s (F016 şeffaflık alanı)
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'warnings': self._check_warnings(v_exit, Re) + extra_warnings
        }
        # L/D anüler geçit için tanımsız (plaka kalınlığı modeli yok) → None;
        # Weber karakteristik boyutu = anülüs boşluğu (sıvı tabaka kalınlığı)
        result.update(self._common_outputs(a_inj, v_exit, gap, None))
        return result

    def _calculate_swirl(self):
        """Basınç-swirl (simplex) atomizör — Giffen–Muraszew çözümü.

        v2.6.2 DÜZELTMESİ (fizik denetimi F017 + F043):
        - F017: sprey açısı SABİT 90 yazılıydı — hiçbir geometri/akış
          girdisine bağlı değildi ve yarı açı mı tam koni mi belirsizdi.
          Doğrusu: sinθ = (π/2)·Cd/(K·(1+√X)) (Giffen & Muraszew 1953;
          Lefebvre & McDonell Böl. 6). Artık çözümden gelir; 'spray_angle'
          TAM koni açısıdır (2θ), yarı açı ayrıca 'spray_half_angle_deg'
          alanında verilir.
        - F043: 'A_eff = A_slots·0.6' ve 'exit_orifice_area = A_eff'
          bağıntılarının kaynağı yoktu; çıkış orifis alanı ile teğet giriş
          (yuva) alanı bağımsız büyüklüklerdir ve K = A_p/(D_s·d_o) ile
          ilişkilidir. Artık: exit_orifice_area gerçek orifis alanı
          A_o = ṁ/(Cd_sw·√(2ρΔP)); effective_area = A_o·(1−X) (hava
          çekirdeği düşülmüş sıvı halka alanı — fiziksel anlamı olan tek
          'efektif' alan); yuvalar K tanımından boyutlanır.
        Deşarj katsayısı GM çözümünden gelir (Cd = √((1−X)³/(1+X))) —
        yapıcıdaki düz orifis Cd'si basınç-swirl fiziğiyle tutarsızdır.
        """
        params = self.swirl_params
        if params.get('canon'):
            return self._calculate_swirl_canon(params)
        n_slots = params['n_slots']

        delta_P_Pa = self.delta_P_inj * 1e5
        sqrt_term = np.sqrt(2 * self.rho_ox * delta_P_Pa)
        extra_warnings = []

        # v2.6.26 — iki eski ölü girdi bağlandı:
        # D_s_user: swirl (spin) odası çapı. Verilirse K = A_p/(D_s·d_o)
        #   bağıntısında D_s = 2.5·d_o varsayılan oranının yerini alır.
        # theta_target: hedef sprey YARI açısı. Sentez yolunda
        #   swirl_K_from_theta ile K'yı belirler. Çözücü zarfı
        #   θ ∈ [3.7°, 71.2°] (K ∈ [0.02, 20]); dışı kırpılır ve UYARILIR.
        D_s_user = params.get('D_s')
        theta_target = params.get('theta_target')
        if theta_target is not None and not (
                _SWIRL_THETA_MIN_DEG <= theta_target <= _SWIRL_THETA_MAX_DEG):
            clamped_theta = float(np.clip(
                theta_target, _SWIRL_THETA_MIN_DEG, _SWIRL_THETA_MAX_DEG))
            extra_warnings.append(
                f"Target spray half-angle {theta_target:.1f} deg is outside "
                f"the Giffen-Muraszew solvable envelope "
                f"[{_SWIRL_THETA_MIN_DEG:.1f}, {_SWIRL_THETA_MAX_DEG:.1f}] "
                f"deg; using {clamped_theta:.1f} deg.")
            theta_target = clamped_theta

        if params['h'] is None or params['w'] is None:
            # Tasarım sentezi: hedef yarı açı → K → (X, Cd_sw, θ) → orifis ve
            # yuvalar. (Yalnız biri verilirse de sentez yolu kullanılır —
            # tek boyutla K kapalı sistemi kurulamaz.)
            # Hedef verilmezse 45° (tipik simplex bandının ortası).
            theta_used = (theta_target if theta_target is not None
                          else SWIRL_DEFAULT_HALF_ANGLE_DEG)
            K = swirl_K_from_theta(theta_used)
            sw = swirl_solve(K)
            A_o = self.mdot_ox / (sw['cd'] * sqrt_term)
            d_o = 2.0 * np.sqrt(A_o / np.pi)
            # K = A_p/(D_s·d_o); D_s kullanıcıdan gelir, yoksa 2.5·d_o
            D_s = D_s_user if D_s_user is not None else SWIRL_CHAMBER_D_RATIO * d_o
            A_p = K * D_s * d_o
            A_slot = A_p / n_slots
            h = np.sqrt(A_slot / 2.0)
            w = 2.0 * h
        else:
            # Kullanıcı yuva geometrisi verdi: K kapalı sistemden çözülür.
            # A_p_model(K) = K·D_s·d_o; D_s kullanıcıdan gelirse sabit bir
            # uzunluktur, gelmezse 2.5·d_o(K) oranı kullanılır (o durumda
            # D_s·d_o = 2.5·(4/π)·A_o). A_p_model K'da monoton artar (K/Cd(K)
            # K→0'da sabite, K→∞'da K'ya gider) → bisection yeterli.
            h = params['h']
            w = params['w']
            A_p = n_slots * w * h
            if theta_target is not None:
                # Yuva geometrisi K'yı (dolayısıyla sprey açısını) kendisi
                # belirler; hedef açı bu durumda UYGULANAMAZ. Sessiz yutma
                # yasak — açıkça bildirilir.
                extra_warnings.append(
                    "Slot geometry (width/height) fixes the swirl number, so "
                    "the target spray half-angle input is ignored; clear the "
                    "slot dimensions to design for a target angle.")

            def a_p_model(K_try):
                a_o = self.mdot_ox / (swirl_solve(K_try)['cd'] * sqrt_term)
                if D_s_user is not None:
                    return K_try * D_s_user * 2.0 * np.sqrt(a_o / np.pi)
                return K_try * SWIRL_CHAMBER_D_RATIO * (4.0 * a_o / np.pi)

            if A_p <= a_p_model(_SWIRL_K_MIN):
                K = _SWIRL_K_MIN
                clipped = True
            elif A_p >= a_p_model(_SWIRL_K_MAX):
                K = _SWIRL_K_MAX
                clipped = True
            else:
                lo, hi = _SWIRL_K_MIN, _SWIRL_K_MAX
                for _ in range(200):
                    mid = 0.5 * (lo + hi)
                    if a_p_model(mid) < A_p:
                        lo = mid
                    else:
                        hi = mid
                K = 0.5 * (lo + hi)
                clipped = False
            if clipped:
                extra_warnings.append(
                    "Given tangential slot area is outside the solvable "
                    "swirl envelope (atomizer constant K clipped to "
                    f"{K:.2f}); reported geometry does not match the given "
                    "slots exactly.")
            sw = swirl_solve(K)
            A_o = self.mdot_ox / (sw['cd'] * sqrt_term)
            d_o = 2.0 * np.sqrt(A_o / np.pi)

        X = sw['X']
        theta_half = sw['theta_deg']

        # Kullanılan swirl odası çapı ve GM geçerlilik kontrolü: model spin
        # odasının çıkış orifisini sardığını varsayar (D_s > d_o; pratikte
        # D_s/d_o >= ~1.25, Lefebvre & McDonell Böl. 6 simplex geometrisi).
        D_s_used = D_s_user if D_s_user is not None else SWIRL_CHAMBER_D_RATIO * d_o
        if D_s_user is not None and D_s_user < 1.25 * d_o:
            extra_warnings.append(
                f"Swirl chamber diameter {D_s_user * 1000:.1f} mm is below "
                f"1.25x the exit orifice diameter ({d_o * 1000:.2f} mm); the "
                f"Giffen-Muraszew geometry assumption breaks down. Increase "
                f"the swirl chamber diameter to at least "
                f"{1.25 * d_o * 1000:.1f} mm.")

        # Actual slot area (toplam teğet giriş alanı)
        A_slots = n_slots * w * h
        # Sıvı halka (hava çekirdeği düşülmüş) çıkış alanı ve film kalınlığı
        A_eff = A_o * (1.0 - X)
        film_t = (d_o / 2.0) * sw['film_t_ratio']  # t = r_o·(1−√X)

        # Çıkış film hızı — süreklilik: ṁ = ρ·A_eff·v (F042 ile aynı ilke)
        v_exit = self._exit_velocity(self.mdot_ox, self.rho_ox, A_eff)
        # Yuva (teğet giriş) hızı ve Reynolds — yuva hidrolik çapıyla
        v_slot = self._exit_velocity(self.mdot_ox, self.rho_ox, A_slots)
        D_h = 2 * w * h / (w + h)
        Re = self.rho_ox * v_slot * D_h / self.mu_ox

        result = {
            'type': 'swirl',
            'n_slots': n_slots,
            'slot_width': w * 1000,  # mm
            'slot_height': h * 1000,  # mm
            'total_slot_area': A_slots * 1e6,  # mm² (eski ad — korunur)
            'effective_area': A_eff * 1e6,  # mm² (sıvı halka: A_o·(1−X))
            'exit_orifice_area': A_o * 1e6,  # mm² (gerçek orifis alanı)
            'exit_orifice_diameter': d_o * 1000,  # mm
            'atomizer_constant_K': float(K),
            'air_core_ratio_X': float(X),
            # v2.6.26: kullanılan spin odası çapı ve kaynağı raporlanır —
            # kullanıcı girdisinin sonuca girdiği görünür olmalı.
            'swirl_chamber_diameter': float(D_s_used * 1000),  # mm
            'swirl_chamber_d_source': ('user' if D_s_user is not None
                                       else 'default_ratio'),
            'spray_half_angle_target_deg': (float(theta_target)
                                            if theta_target is not None
                                            else None),
            'film_thickness_mm': film_t * 1000,
            'spray_angle': float(2.0 * theta_half),  # TAM koni açısı [derece]
            'spray_half_angle_deg': float(theta_half),
            'slot_velocity': v_slot,  # m/s (teğet giriş)
            'exit_velocity': v_exit,  # m/s (çıkış filmi, süreklilikten)
            'reynolds_number': Re,
            'warnings': self._check_warnings(v_exit, Re) + extra_warnings
        }
        # Weber karakteristik boyutu = kırılan sıvı film kalınlığı;
        # sözleşmedeki injection_area = ölçüm (metering) alanı olan orifis
        result.update(self._common_outputs(A_o, v_exit, film_t, None))
        # Swirl'de deşarj katsayısı GM çözümünden gelir (düz orifis Cd değil)
        result['discharge_coefficient'] = float(sw['cd'])
        result['discharge_coefficient_basis'] = (
            f"Giffen-Muraszew: K={K:.3f} -> X={X:.3f} -> Cd={sw['cd']:.3f}")
        # Swirl'de Cd bir varsayım DEĞİL, geometriden çözülen bir sonuçtur
        # (bu yüzden çağıranın değeri buraya uygulanmaz — kardeş modül de
        # aynı istisnayı beyanla taşır): kazanılmıştır.
        result['discharge_coefficient_earned'] = True
        return result

    def _calculate_swirl_canon(self, params):
        """Swirl ekran bloğu — devrenin elemanını TÜKETİR (V301/E2).

        ÖLÇÜLDÜ (once.json, 1 kN N₂O): API varsayılanında bu blok TEK eleman
        d_o 5,40 mm (22,89 mm², SPI) yayımlarken devre 7 eleman × d_o 2,42 mm
        (32,23 mm², Dyer NHNE) çözüyordu; form varsayılanında ekran K 0,052 /
        θ 64,4°, devre K 0,326 / θ 45°. Artık eleman sayısı, çıkış orifisi,
        K/X/Cd/θ, girdap odası çapı ve teğet giriş alanı devrenindir
        (``design_swirl_element``). Bu blok yalnız teğet girişi dikdörtgen
        yuva olarak yazar: yuva ölçüsü istekte varsa odur (devre K'yı ondan
        çözdü), yoksa aynı giriş alanından w = 2h (eski sentez oranı).
        Hızlar eleman başına süreklilikten: film çıkış hızı
        ṁ_e/(ρ·A_o·(1−X)), yuva hızı ṁ_e/(ρ·n_yuva·w·h)."""
        k = params['canon']
        n_el = max(int(k['n_elements']), 1)
        n_slots = int(params['n_slots'])
        d_o = float(k['exit_orifice_d_mm']) * 1e-3
        A_o = np.pi * d_o ** 2 / 4.0                     # eleman başına
        K = float(k['K'])
        X = float(k['X'])
        cd_sw = float(k['cd'])
        theta_half = float(k['theta_half_deg'])
        D_s = float(k['swirl_chamber_d_mm']) * 1e-3
        A_p = float(k['tangential_inlet_area_mm2']) * 1e-6   # eleman başına
        mdot_e = self.mdot_ox / n_el
        extra_warnings = []
        if k.get('slot_w_mm') is not None and k.get('slot_h_mm') is not None:
            w = float(k['slot_w_mm']) * 1e-3
            h = float(k['slot_h_mm']) * 1e-3
            yuva_kaynagi = 'request (slot_width x slot_height)'
        else:
            A_slot = A_p / n_slots
            h = np.sqrt(A_slot / 2.0)
            w = 2.0 * h
            yuva_kaynagi = ('derived from the circuit tangential inlet area: '
                            'w = 2h per slot (HRMA proportion, no literature '
                            'value)')
        if D_s < 1.25 * d_o:
            extra_warnings.append(
                f"Swirl chamber diameter {D_s * 1000:.1f} mm is below "
                f"1.25x the exit orifice diameter ({d_o * 1000:.2f} mm); the "
                f"Giffen-Muraszew geometry assumption breaks down. Increase "
                f"the swirl chamber diameter to at least "
                f"{1.25 * d_o * 1000:.1f} mm.")
        A_slots = n_slots * w * h
        A_eff = A_o * (1.0 - X)
        film_t = float(k['film_thickness_mm']) * 1e-3
        v_exit = self._exit_velocity(mdot_e, self.rho_ox, A_eff)
        v_slot = self._exit_velocity(mdot_e, self.rho_ox, A_slots)
        v_orifis = self._exit_velocity(mdot_e, self.rho_ox, A_o)
        D_h = 2 * w * h / (w + h)
        Re = self.rho_ox * v_slot * D_h / self.mu_ox
        result = {
            'type': 'swirl',
            'n_elements': n_el,
            'n_slots': n_slots,
            'slot_width': w * 1000,  # mm
            'slot_height': h * 1000,  # mm
            'slot_size_source': yuva_kaynagi,
            'total_slot_area': A_slots * 1e6,  # mm² (ELEMAN başına)
            'effective_area': A_eff * 1e6,  # mm² (eleman başına sıvı halka)
            'exit_orifice_area': A_o * 1e6,  # mm² (eleman başına)
            'exit_orifice_diameter': d_o * 1000,  # mm
            'atomizer_constant_K': K,
            'air_core_ratio_X': X,
            'swirl_chamber_diameter': D_s * 1000,  # mm
            'swirl_chamber_d_source': k.get('chamber_source'),
            'spray_half_angle_target_deg': k.get('theta_target_deg'),
            'film_thickness_mm': film_t * 1000,
            'spray_angle': float(2.0 * theta_half),  # TAM koni açısı [derece]
            'spray_half_angle_deg': theta_half,
            'slot_velocity': v_slot,  # m/s (teğet giriş)
            'exit_velocity': v_exit,  # m/s (çıkış FİLMİ, süreklilikten)
            'exit_velocity_basis': (
                'liquid-film exit velocity per element: mdot_e/(rho*A_o*(1-X)) '
                '(air core excluded); orifice_mean_velocity is the mean over '
                'the full orifice area, as in the injector circuit table'),
            'orifice_mean_velocity': v_orifis,
            'reynolds_number': Re,
            'swirl_k_source': k.get('k_source'),
            'swirl_plan_source': k.get('basis'),
            'element_plan': (dict(k['element_plan'])
                             if isinstance(k.get('element_plan'), dict)
                             else None),
            'warnings': self._check_warnings(v_exit, Re) + extra_warnings
        }
        # Sözleşmedeki injection_area = ölçüm (metering) alanı: BÜTÜN
        # elemanların orifis alanı (devre tablosunun toplam alanı).
        result.update(self._common_outputs(n_el * A_o, v_exit, film_t, None))
        result['discharge_coefficient'] = cd_sw
        result['discharge_coefficient_basis'] = (
            f"Giffen-Muraszew: K={K:.3f} -> X={X:.3f} -> Cd={cd_sw:.3f}")
        result['discharge_coefficient_earned'] = True
        return result

    def _impingement_clamp_delivery(self, a_teslim, a_gerekli, delta_P_Pa):
        """Kırpılan çarpışmalı planın teslim cümlesi (5. tur Ş-5).

        Hedef ile hesaplanan AYRI yazılır (Astra danışması, §28-18: hız
        düşüşü sabit debi kabulüne dayanır; ΔP sabitken alan büyümesi
        debiyi de değiştirir):

        * oran r = A_teslim / A_gerekli ve alan fazlası yüzde olarak (r − 1)·100;
        * hedef debi ṁ ve bu debide süreklilik hızı v = ṁ/(ρ·A_teslim)
          (yayımlanan ``exit_velocity`` ile AYNI bağıntı, ``_exit_velocity``);
        * yayımlanan ΔP'de orifis bağıntısının verdiği debi
          ṁ_ΔP = C_d·A_teslim·√(2ρΔP) (``A_required`` satırının tersi,
          Sutton & Biblarz Böl. 8) = r·ṁ.

        Çözücü ΔP'yi yeniden çözüp hedef debiyi doğrulamadığı için cümle
        "hedef debi korunur" demez; açıkça doğrulanmadığını söyler.
        """
        oran = a_teslim / a_gerekli
        v_teslim = self._exit_velocity(self.mdot_ox, self.rho_ox, a_teslim)
        mdot_dp = self.C_d * a_teslim * np.sqrt(2 * self.rho_ox * delta_P_Pa)
        return (
            f" Delivered injection area {a_teslim * 1e6:.4g} mm^2 against "
            f"{a_gerekli * 1e6:.4g} mm^2 required: {oran:.2f}x (area "
            f"{(oran - 1.0) * 100:.0f}% larger). Target flow "
            f"{self.mdot_ox:.4g} kg/s; exit velocity at the target flow "
            f"{v_teslim:.4g} m/s. At the published pressure drop "
            f"({self.delta_P_inj:.4g} bar) the orifice equation gives "
            f"{mdot_dp:.4g} kg/s ({oran:.2f}x the target); the target flow "
            f"rate is not verified at this pressure drop.")

    def _target_flow_check(self, a_teslim, a_gerekli, delta_P_Pa):
        """Kırpılmış planın yayımlanan ΔP'de hedef debiyi tutup tutmadığı.

        ÖH D37 A2 hibrit · 7. tur (karar §28-25, Astra şartı: "hedefi
        karşılamayan kırpılmış plan başarı/uygunluk onayı almaz").
        Yalnız çapı imalat bandına KIRPILAN planlar için çağrılır.

        * ṁ_ΔP = C_d·A_teslim·√(2ρΔP): yayımlanan ΔP'de orifis bağıntısının
          verdiği debi (Sutton & Biblarz Böl. 8; ``A_required`` satırının
          tersi). Oran ṁ_ΔP/ṁ = A_teslim/A_gerekli.
        * |oran − 1| ≤ ``CLAMPED_PLAN_TARGET_FLOW_REL_TOL`` → ``None``: alan
          KONMAZ, yanıt bit-aynı kalır (plan hedefi tolerans içinde tutuyor).
        * Aksi → fail-closed sınıf ``target_flow_not_met``; /calculate bu
          sınıfı doğrulama özetine kritik kayıt olarak geçirir
          (``withhold_validation_pass_for_target_flow``).

        Plan DEĞİŞMEZ (n × d, alan, hız aynı); değişen yalnız hükümdür.
        """
        mdot = float(self.mdot_ox)
        if not (math.isfinite(mdot) and mdot > 0.0):
            return None
        mdot_dp = float(self.C_d * a_teslim
                        * np.sqrt(2.0 * self.rho_ox * delta_P_Pa))
        oran = mdot_dp / mdot
        if abs(oran - 1.0) <= CLAMPED_PLAN_TARGET_FLOW_REL_TOL:
            return None
        return {
            'status': TARGET_FLOW_NOT_MET,
            'target_mdot_kg_s': mdot,
            'mdot_at_published_dp_kg_s': mdot_dp,
            'ratio': oran,
            'delivered_area_mm2': float(a_teslim * 1e6),
            'required_area_mm2': float(a_gerekli * 1e6),
            'pressure_drop_bar': float(self.delta_P_inj),
            'relative_tolerance': CLAMPED_PLAN_TARGET_FLOW_REL_TOL,
            'tolerance_basis': CLAMPED_PLAN_TARGET_FLOW_TOL_BASIS,
            'basis': (
                'The hole diameter was clamped to the manufacturing band and '
                'the hole count re-solved, so the delivered injection area '
                'differs from the area required for the target flow at the '
                'published pressure drop. The pressure drop was NOT '
                're-solved: at that pressure drop the orifice equation '
                'mdot = Cd*A*sqrt(2*rho*dP) gives the flow above, not the '
                'target. This plan does not meet the target flow and carries '
                'no positive design verdict.'),
        }

    def _calculate_impingement(self):
        """Like-on-like doublet (tek akışkan): Bernoulli alanı + 2θ=60°
        çarpışma. Karışım notu Rupe (JPL 20-195): like-doublet'te karışım
        çift fanların ara-katmanlanmasıyla sağlanır; unlike MR kriteri
        burada uygulanmaz."""
        params = self.impingement_params
        if params.get('canon'):
            return self._calculate_impingement_canon(params)
        delta_P_Pa = self.delta_P_inj * 1e5
        A_required = self.mdot_ox / (self.C_d * np.sqrt(2 * self.rho_ox * delta_P_Pa))

        # Delik planı: çift sayıda delik (her doublet 2 delik)
        n_pairs = params['n_pairs']
        if n_pairs <= 0:
            # İmalat bandına oturan en küçük çift sayısı
            n_pairs = 2
            while n_pairs < 100:
                d_try = 2 * np.sqrt(A_required / (2 * n_pairs * np.pi))
                if d_try <= params['d_max']:
                    break
                n_pairs += 1
        n_pairs_requested = n_pairs
        n_holes = 2 * n_pairs
        d_h = 2 * np.sqrt(A_required / (n_holes * np.pi))
        d_h_clamped = max(params['d_min'], min(d_h, params['d_max']))
        extra_warnings = []
        hedef_debi = None
        if not np.isclose(d_h_clamped, d_h, rtol=1e-9):
            # Çap imalat bandına kırpıldı → hedef debiyi korumak için çift
            # sayısı yeniden çözülür (showerhead ile aynı ilke)
            area_per_hole = np.pi * (d_h_clamped / 2) ** 2
            n_pairs = max(2, int(np.ceil(A_required / (2 * area_per_hole))))
            n_holes = 2 * n_pairs
            a_teslim = n_holes * area_per_hole
            # ÖH D37 A2 hibrit · 7. tur (karar §28-25): kırpılan planın hedef
            # debi sınıfı — üç kırpma yolunda da (istenen çift değişti /
            # korundu / otomatik) ve kullanıcının sabitlediği çapta
            # (d_min = d_max) aynı denetim. Plan değişmez.
            hedef_debi = self._target_flow_check(a_teslim, A_required,
                                                 delta_P_Pa)
            # ÖH D37 A2 hibrit · 5. tur Ş-5 (ana model kararı (i), Astra
            # danışmalı, §28-18): kırpılan planın TESLİM ölçüleri tek yerde
            # kurulur ve iki kırpma yolunun (istenen çift değişti / değişmedi
            # ya da otomatik) uyarısına AYNI cümleyle eklenir.
            teslim_cumlesi = self._impingement_clamp_delivery(
                a_teslim, A_required, delta_P_Pa)
            # v2.6.26: bu yeniden çözüm SESSİZDİ. Kullanıcının girdiği çift
            # sayısı, çap banda sığmadığında hiçbir iz bırakmadan atılıyordu;
            # ölçüldü: element_pairs 8 ve 12 aynı sonucu veriyor (ikisi de
            # 15'e yeniden çözülüyor), yani kullanıcı alanı değiştirip
            # hiçbir şeyin kımıldamadığını görüyordu. Kardeş dal
            # (_calculate_showerhead) aynı durumda ZATEN uyarıyordu; bu dal
            # o uyarıyı taşımıyordu.
            # ÖH D37 A2 hibrit · 5. tur Ş-5: bu dal "the pair count was
            # re-solved to N to preserve the target flow rate" diyordu.
            # ÖLÇÜLDÜ (denetim-4, 7 Eki; I50 element_pairs 3 ve 4): çift
            # tabanı max(2, …) bağlayınca teslim alanı istenenin 2,076 katı,
            # hız 68,75 → 33,12 m/s; yayımlanan ΔP tasarım değeri kaldığı
            # için o ΔP'de orifis bağıntısı hedefin 2,08 katı debi verir.
            # Çözücü ΔP'yi yeniden çözmüyor, hedef debiyi DOĞRULAMIYOR →
            # "korur" hükmü kaldırıldı; teslim alanı, oran, hedef ve
            # hesaplanan debi ile hız adıyla yayımlanır.
            # 9. tur: Devir 35 çap ondalığı (``band_warning_decimals``) ve
            # Devir 37 sabit çap (d_min = d_max) metni (``_fixed_d_clamp_text``).
            _k = band_warning_decimals(d_h, params['d_min'], params['d_max'])
            if params['d_min'] == params['d_max']:
                extra_warnings.append(_fixed_d_clamp_text(
                    params, n_pairs_requested, n_pairs, d_h, d_h_clamped, _k)
                    + teslim_cumlesi)
            elif params['n_pairs'] > 0 and n_pairs != n_pairs_requested:
                extra_warnings.append(
                    f"Requested {n_pairs_requested} doublet pairs would need "
                    f"{d_h * 1000:.{_k}f} mm holes, outside the manufacturing "
                    f"band ({params['d_min'] * 1000:.{_k}f}-"
                    f"{params['d_max'] * 1000:.{_k}f} mm); the pair count was "
                    f"re-solved to {n_pairs} pairs of "
                    f"{d_h_clamped * 1000:.{_k}f} mm holes." + teslim_cumlesi)
            elif params['d_min'] < params['d_max']:
                # ÖH D37 A2 hibrit · denetçi-3 Ş-4 (i): kırpma bu dalda da
                # SESSİZDİ. Otomatik çift yolunda (n_pairs = 0) ve istenen
                # çiftin değişmediği yolda çap banda kırpılınca çift tabanı
                # max(2, …) yüzünden toplam alan istenenin ÜSTÜNE çıkar;
                # ΔP tasarım değeri yayımlanmaya devam ederken hız v = ṁ/(ρA)
                # aynı oranda düşer. ÖLÇÜLDÜ (denetçi-3, Ornek-H1 çarpışmalı
                # 50 N, bant 0,5-2,5): 4 × 0,347 → 4 × 0,50 mm, A 0,378 →
                # 0,785 mm², v 68,75 → 33,12 m/s ve hiçbir uyarı yok — eski
                # hız uyarısı KALKIYORDU (fail-open). Artık kırpma adıyla ve
                # iki alanıyla yayımlanır; plan (n × d) DEĞİŞMEZ. Kapsam:
                # gerçek bant (d_min < d_max); sabit çap yukarıda (9. tur).
                kaynak = ('Requested' if params['n_pairs'] > 0
                          else 'The auto-selected minimum of')
                extra_warnings.append(
                    f"{kaynak} {n_pairs_requested} doublet pairs would need "
                    f"{d_h * 1000:.{_k}f} mm holes, outside the manufacturing "
                    f"band ({params['d_min'] * 1000:.{_k}f}-"
                    f"{params['d_max'] * 1000:.{_k}f} mm); the holes were "
                    f"clamped to {d_h_clamped * 1000:.{_k}f} mm with "
                    f"{n_pairs} pairs, so the injection area is "
                    f"{a_teslim * 1e6:.4g} mm^2 against the "
                    f"{A_required * 1e6:.4g} mm^2 required for the target "
                    f"flow at the design pressure drop (ratio "
                    f"{a_teslim / A_required:.3f}); the exit velocity is "
                    f"divided by the same ratio." + teslim_cumlesi)
        d_h = d_h_clamped
        A_inj = n_holes * np.pi * (d_h / 2) ** 2
        # Süreklilikten hız (F042 — önceki dalga yalnız showerhead'i düzeltip
        # bu dalı ideal Bernoulli hızında bırakmıştı): v = ṁ/(ρ·A)
        v_exit = self._exit_velocity(self.mdot_ox, self.rho_ox, A_inj)

        half_angle = params['full_angle_deg'] / 2.0
        # Eksenel bileşen: her jet eksene half_angle ile eğik
        v_axial = v_exit * np.cos(np.radians(half_angle))
        impingement_distance = IMPINGEMENT_DISTANCE_LD * d_h  # m

        Re = self.rho_ox * v_exit * d_h / self.mu_ox
        L_D = params['t_plate'] / d_h

        # ÖH D20 / P15B1-02 ikizi — showerhead ile aynı sözleşme.
        ld_kazanildi = bool(params.get('t_plate_earned'))
        warn_list = self._check_warnings(
            v_exit, Re, L_D if ld_kazanildi else None) + extra_warnings
        if not ld_kazanildi:
            warn_list.append(LD_NOT_ISSUED_WARNING)
        if (params['full_angle_deg'] < IMPINGEMENT_ANGLE_HEURISTIC_BAND_DEG[0]
                or params['full_angle_deg'] > IMPINGEMENT_ANGLE_HEURISTIC_BAND_DEG[1]):
            warn_list.append(_carpisma_acisi_bant_metni(params['full_angle_deg']))

        result = {
            'type': 'impingement',
            'n_pairs': int(n_pairs),
            # v2.6.26: kullanicinin istedigi cift sayisi ile cozumun kullandigi
            # ayri raporlanir; yeniden cozuldugunde bu iki alan ayrisir ve
            # kullanici hangi degerin gecerli oldugunu gorur.
            'n_pairs_requested': (int(n_pairs_requested)
                                  if params['n_pairs'] > 0 else None),
            'n_holes': int(n_holes),
            'hole_diameter': d_h * 1000,  # mm
            'plate_thickness': _yayin_plaka_mm(params, ld_kazanildi),  # mm
            'plate_thickness_earned': ld_kazanildi,
            'plate_thickness_basis': params.get('t_plate_basis'),
            'L_D_ratio': (L_D if ld_kazanildi else None),
            'impingement_angle_deg': params['full_angle_deg'],
            'impingement_distance': impingement_distance * 1000,  # mm
            'axial_velocity': v_axial,
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'mixing_note': ('Like-on-like doublet: mixing via interleaved spray '
                            'fans (Rupe, JPL 20-195); no unlike momentum-ratio '
                            'criterion applies'),
            'warnings': warn_list
        }
        result.update(self._common_outputs(
            A_inj, v_exit, d_h, (L_D if ld_kazanildi else None),
            l_d_earned=ld_kazanildi,
            l_d_basis=params.get('t_plate_basis')))
        # ÖH D37 A2 hibrit · 7. tur: alan YALNIZ kırpılmış ve hedefi tolerans
        # dışında kaçıran planda konur (kırpılmayan plan bit-aynı).
        if hedef_debi is not None:
            result['target_flow_check'] = hedef_debi
        return result

    def _calculate_impingement_canon(self, params):
        """Çarpışmalı ekran bloğu — devrenin çift planını TÜKETİR (V301/E2).

        ÖLÇÜLDÜ (once.json, 1 kN N₂O): bu blok kendi tek fazlı SPI alanıyla
        2 çift × Ø1,541 mm (7,456 mm²) yayımlarken devre Dyer NHNE ile
        10,495 mm² çözüyordu — ekran planı iki-fazlı akıda hedef debinin
        ~%71'ini teslim ederdi. Artık delik sayısı, çapı ve toplam alan
        devrenindir (``design_like_doublet``: çift sayıda delik); çarpışma
        açısı da devrenin (istekten). Hız süreklilikten bu bloğun
        yoğunluğuyla basılır (aynı alan, aynı debi)."""
        kanon = params['canon']
        n_holes = int(kanon['n_holes'])
        d_h = float(kanon['hole_diameter_mm']) * 1e-3
        A_inj = n_holes * np.pi * (d_h / 2) ** 2
        v_exit = self._exit_velocity(self.mdot_ox, self.rho_ox, A_inj)
        tam_aci = float(kanon['full_angle_deg'])
        half_angle = tam_aci / 2.0
        v_axial = v_exit * np.cos(np.radians(half_angle))
        impingement_distance = IMPINGEMENT_DISTANCE_LD * d_h  # m
        Re = self.rho_ox * v_exit * d_h / self.mu_ox
        L_D = params['t_plate'] / d_h
        ld_kazanildi = bool(params.get('t_plate_earned'))
        warn_list = self._check_warnings(
            v_exit, Re, L_D if ld_kazanildi else None)
        if not ld_kazanildi:
            warn_list.append(LD_NOT_ISSUED_WARNING)
        if (tam_aci < IMPINGEMENT_ANGLE_HEURISTIC_BAND_DEG[0]
                or tam_aci > IMPINGEMENT_ANGLE_HEURISTIC_BAND_DEG[1]):
            warn_list.append(_carpisma_acisi_bant_metni(tam_aci))
        plan = kanon.get('element_plan') or {}
        result = {
            'type': 'impingement',
            'n_pairs': int(n_holes // 2),
            'n_pairs_requested': plan.get('requested_pairs'),
            'n_holes': n_holes,
            'hole_diameter': d_h * 1000,  # mm
            'hole_diameter_requested': plan.get('requested_hole_d_mm'),
            'plate_thickness': _yayin_plaka_mm(params, ld_kazanildi),  # mm
            'plate_thickness_earned': ld_kazanildi,
            'plate_thickness_basis': params.get('t_plate_basis'),
            'L_D_ratio': (L_D if ld_kazanildi else None),
            'impingement_angle_deg': tam_aci,
            'impingement_angle_basis': kanon.get('angle_basis'),
            'impingement_distance': impingement_distance * 1000,  # mm
            'impingement_distance_basis': (
                f'computed: {IMPINGEMENT_DISTANCE_LD:g} x hole diameter '
                '(free-jet length to the impingement point), inside the upper '
                'limit of 5-7 orifice diameters given by NASA SP-8089 p. 80'),
            'axial_velocity': v_axial,
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'element_pattern': 'like_on_like_doublet',
            'element_pattern_basis': (
                'like-on-like doublet: a hybrid injects ONE liquid stream '
                '(the oxidizer), so each hole pair impinges oxidizer on '
                'oxidizer; unlike (fuel-on-oxidizer) doublets, triplets and '
                'quadlets do not exist here'),
            'impingement_plan_source': kanon.get('basis'),
            'element_plan': dict(plan) if plan else None,
            'mixing_note': ('Like-on-like doublet: mixing via interleaved spray '
                            'fans (Rupe, JPL 20-195); no unlike momentum-ratio '
                            'criterion applies'),
            'warnings': warn_list
        }
        result.update(self._common_outputs(
            A_inj, v_exit, d_h, (L_D if ld_kazanildi else None),
            l_d_earned=ld_kazanildi,
            l_d_basis=params.get('t_plate_basis')))
        return result

    def _calculate_coaxial(self):
        """Koaksiyel eleman (tek akışkan hibrit): iç jet + dış anülüs, her
        ikisi oksitleyici. Debi payı f_inner iç jete gider; kalan dış
        anülüsten enjekte edilir. Girinti (recess) tipik 1·d_inner.

        V301/H2 — TEK KANON. ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/bilinen/
        hibrit/once.json): devrede tek akışkanlı koaksiyel eleman yoktu, bu
        blok kendi ΔP'siyle (istekteki 4 bar) boyutlanıyordu; kendinden
        basınçlı N₂O'da besleme gerçeği 30,54 bar'dır. Artık devre elemanı
        çözer (``design_coaxial_element``) ve bu blok toplam alanı, iç jet
        payını ve geometriyi devreden TÜKETİR (ekran = devre). ΔP istemcice
        AÇIKÇA ezildiyse kanon yoktur: AYNI geometri işlevi
        (``coaxial_element_geometry``) bu bloğun kendi ΔP'siyle çözülen
        alana uygulanır (ALAN ve ΔP AYRILMAZ)."""
        params = self.coaxial_params
        kanon = params.get('canon')
        if kanon:
            f_inner = float(kanon['inner_flow_fraction'])
            f_kaynak = kanon.get('inner_flow_fraction_source')
            A_total = float(kanon['total_flow_area_mm2']) * 1e-6
            d_inner_mm = float(kanon['inner_jet_diameter_mm'])
            D_i_mm = float(kanon['annulus_inner_diameter_mm'])
            D_o_mm = float(kanon['annulus_outer_diameter_mm'])
            gap_mm = float(kanon['annulus_gap_mm'])
            recess_mm = float(kanon['recess_length_mm'])
            devre_cozumu = (
                'consumed: total metering area, inner-jet share and element '
                'geometry are the injector circuit\'s single-fluid coaxial '
                'element (' + str(kanon.get('basis') or 'injector circuit')
                + '); the pressure drop and discharge coefficient are the '
                'circuit\'s (see pressure_drop_source)')
        else:
            f_inner = params['f_inner']
            f_kaynak = params.get('f_inner_source')
            delta_P_Pa = self.delta_P_inj * 1e5
            A_total = self.mdot_ox / (self.C_d * np.sqrt(
                2 * self.rho_ox * delta_P_Pa))
            g = coaxial_element_geometry(A_total, f_inner, params['t_wall'])
            d_inner_mm = g['d_inner'] * 1000
            D_i_mm = g['D_i'] * 1000
            D_o_mm = g['D_o'] * 1000
            gap_mm = g['gap'] * 1000
            recess_mm = g['recess'] * 1000
            devre_cozumu = (
                'not consumed: no circuit geometry was handed to this block '
                '(the client overrode the pressure drop - pressure_drop_'
                'source - or the circuit did not size the element), so the '
                'element is sized here with this block\'s own pressure drop '
                'through the same geometry rule (area and pressure drop are '
                'not separated); the circuit reference design, if any, is in '
                'motor.injector_design_detail.coaxial_geometry')
        # Süreklilikten hız (F042 — önceki dalga yalnız showerhead'i düzeltip
        # bu dalı ideal Bernoulli hızında bırakmıştı): v = ṁ/(ρ·A) = Cd·√(2ΔP/ρ)
        v_exit = self._exit_velocity(self.mdot_ox, self.rho_ox, A_total)
        Re = self.rho_ox * v_exit * (d_inner_mm / 1000) / self.mu_ox

        result = {
            'type': 'coaxial',
            'inner_jet_diameter': d_inner_mm,  # mm
            'annulus_inner_diameter': D_i_mm,  # mm
            'annulus_outer_diameter': D_o_mm,  # mm
            'annulus_gap': gap_mm,  # mm
            'recess_length': recess_mm,  # mm
            'recess_length_basis': COAX_RECESS_BASIS,
            'inner_flow_fraction': f_inner,
            'inner_flow_fraction_source': (
                f_kaynak
                or ('module default ' + COAX_INNER_FLOW_FRACTION_BASIS)),
            'element_count': 1,
            'element_count_basis': COAX_ELEMENT_COUNT_BASIS,
            'circuit_solution': devre_cozumu,
            # create_pintle_cross_section uyumlu takma adlar (kesit çizimi)
            'outer_diameter': D_o_mm,  # mm
            'pintle_diameter': d_inner_mm,  # mm
            'gap': gap_mm,  # mm
            'exit_velocity': v_exit,
            'reynolds_number': Re,
            'warnings': self._check_warnings(v_exit, Re)
        }
        # Weber karakteristik boyutu = dış anülüs boşluğu (kırılan tabaka)
        result.update(self._common_outputs(A_total, v_exit, gap_mm / 1000,
                                           None))
        if kanon:
            # Ölçüm alanı devrenin sayısıdır (mm² gidiş-dönüşü yok).
            result['injection_area'] = float(kanon['total_flow_area_mm2'])
        return result

    def _optimize_showerhead_holes(self, A_required, params):
        """Optimize number of holes for showerhead injector"""
        def objective(N):
            N = int(N)
            if N < 4:
                return 1e6

            d_h = 2 * np.sqrt(A_required / (N * np.pi))

            penalty = 0

            # Diameter constraints
            if d_h < params['d_min']:
                penalty += 100 * (params['d_min'] - d_h) / params['d_min']
            elif d_h > params['d_max']:
                penalty += 100 * (d_h - params['d_max']) / params['d_max']

            # L/D constraint
            L_D = params['t_plate'] / d_h
            if L_D < 3 or L_D > 5:
                penalty += 10 * abs(L_D - 4)

            # v2.6.2 DÜZELTMESİ (fizik denetimi F129): burada bir "hız sapması"
            # ceza terimi vardı. d_h = 2√(A_gerekli/(Nπ)) olduğu için
            # A_actual ≡ A_gerekli, dolayısıyla v = ṁ/(ρA) DELİK SAYISINDAN
            # TAMAMEN BAĞIMSIZ bir sabittir (ölçüldü: N=4..200 aralığında
            # 28.0 m/s, hiç değişmiyor). Terim optimizasyonda ölüydü ve
            # kullanıcının target_velocity girdisi sessizce yutuluyordu.
            # Hız yalnız ΔP ve Cd ile belirlenir (ṁ = ρAv, A = ṁ/(Cd√(2ρΔP))
            # → v = Cd√(2ΔP/ρ)); bu yüzden hedef hız artık ÇAP/SAYI ile değil,
            # _calculate_showerhead içinde gerekli ΔP bildirilerek raporlanır.
            # Kaynak: süreklilik, Sutton & Biblarz Böl. 8.
            return penalty

        # Optimize
        result = minimize_scalar(objective, bounds=(4, 200), method='bounded')
        N_optimal = int(result.x)
        d_h_optimal = 2 * np.sqrt(A_required / (N_optimal * np.pi))

        return N_optimal, d_h_optimal

    def _resolve_viscosity(self, user_value, reference_data):
        """μ [Pa·s]: kullanıcı → akışkan referansı → BEYAN EDİLMİŞ jenerik.

        Z1: akışkandan bağımsız SESSİZ bir varsayılan (eski 0,0002 Pa·s, ki
        o N₂O'nun ~247 K değeridir) yoktur. Sıralama açıktır ve seçilen
        dayanak ``viscosity_basis`` alanıyla rapora girer.

        Neden yoğunluk gibi fail-closed DEĞİL: ρ enjektör alanına doğrudan
        girer (A ∝ 1/√ρ), μ ise yalnız Reynolds üzerinden C_d rejim notuna
        ve ikinci mertebeden atomizasyon ilişkilerine girer. Kullanıcı
        yoğunluğu verip akışkanı adlandırmadıysa hesabı μ yüzünden
        durdurmak orantısız olur — ama varsayım GİZLENMEZ.
        Kardeş modülün deseni budur (engines/injector_design.py::
        liquid_viscosity → basis ∈ {'table', 'generic'}).
        """
        if user_value is not None:
            self.viscosity_basis = 'user input'
            return float(user_value)
        mu = reference_data.get('viscosity')
        if mu is not None:
            self.viscosity_basis = reference_data.get(
                'viscosity_source', 'reference table')
            return float(mu)
        self.viscosity_basis = (
            f'generic assumption {MU_GENERIC:g} Pa.s (no viscosity table '
            f'entry for {self.oxidizer_type!r}; the value is NOT taken from '
            f'another fluid — supply "oxidizer_viscosity" for a real number)')
        return float(MU_GENERIC)

    def _density_state_warning(self, rho_user, temperature):
        """Kullanıcının verdiği ρ, akışkanın o durumundaki değerle uyumlu mu?

        Z1: kullanıcı girdisi EZİLMEZ (sözleşme bu), ama sessizce de kabul
        edilmez. En sık gördüğümüz kullanıcı hatası tam olarak deponun kendi
        hatasıydı: N₂O için el kitabından okunan 1220 kg/m³'ü (normal kaynama
        noktası değeri) oda sıcaklığı alanına yazmak. ρ enjektör alanına
        1/√ρ ile girdiği için %55'lik bir yoğunluk hatası deliği %20 küçük
        deldirir. Uyarı bir kapı değildir; hesap yürür.
        """
        # OH-D30-01: içe aktarma İŞLEV İÇİNDE (dairesel halka söküldü).
        from hrma.data.external_data_fetcher import (
            oxidizer_reference_density, OxidizerStateError,
            OXIDIZER_STATE_TOLERANCE)
        try:
            reference = oxidizer_reference_density(self.oxidizer_type,
                                                   temperature)
        except OxidizerStateError:
            return None
        rho_ref = reference['density']
        sapma = (float(rho_user) - rho_ref) / rho_ref
        if abs(sapma) <= OXIDIZER_STATE_TOLERANCE:
            return None
        return (f"The supplied oxidizer density ({float(rho_user):.1f} kg/m3) "
                f"deviates {100.0 * sapma:+.1f}% from the reference value for "
                f"{self.oxidizer_type} in this state ({rho_ref:.1f} kg/m3; "
                f"{reference['source']}). The supplied value is used as given "
                f"— check whether it belongs to a different temperature "
                f"(injector area scales as 1/sqrt(rho)).")

    def _check_warnings(self, v_exit, Re, L_D=None):
        # Yerel liste adı 'warnings' modül importunu gölgelemesin diye
        # 'warn_list' (önceki dalga temizliği)
        warn_list = []

        # Z1: kullanıcı yoğunluğu durum referansından saptıysa (kapı değil,
        # ikaz) — __init__'te ölçülür, rapora buradan girer.
        if getattr(self, 'density_state_warning', None):
            warn_list.append(self.density_state_warning)

        # Besleme sistemi ΔP kısıtı (F015) — __init__'te tespit edilir;
        # önceki dalga uyarıyı üretmiş ama rapora BAĞLAMAMIŞTI (yalnız
        # ekrana print ediliyordu). Buradan calculate() çıktısına girer.
        if self._feed_warning:
            warn_list.append(self._feed_warning)

        # Pressure drop check — eşik TEK KAYNAKTAN (acoustic_modes).
        # ÖH Z5S / P10-A (P10B1-10): modül başlığı "artık ikisi de buradan
        # türetilir" diyordu ama bu satır kapsam dışı kalmıştı: karar çıplak
        # ``0.2`` literaliyle, cümle ise elle yazılmış "<20%" dizesiyle
        # veriliyordu. Sabit değişseydi kod yeni eşiğe göre boyutlandırır,
        # ekrandaki cümle ESKİ sayıyı savunmaya devam ederdi. Metin bugünkü
        # sabitle BİT-AYNI kalır ('<20% of chamber pressure').
        if self.delta_P_inj < CHUG_DP_RATIO_RECOMMENDED * self.P_c:
            warn_list.append(
                f"Low pressure drop "
                f"(<{CHUG_DP_RATIO_RECOMMENDED * 100:.0f}% of chamber "
                f"pressure)")

        # Exit velocity check — V301/E2: bant kaynaksızdır, HRMA buluşsal
        # eşiği olarak beyan edilir ("optimal" kelimesi kaldırıldı).
        v_lo, v_hi = INJECTION_VELOCITY_HEURISTIC_BAND_M_S
        if v_exit < v_lo or v_exit > v_hi:
            warn_list.append(
                f"Exit velocity ({v_exit:.1f} m/s) outside the "
                f"{v_lo:.0f}-{v_hi:.0f} m/s band (HRMA heuristic threshold - "
                f"no literature value; not a design limit)")

        # Reynolds number check
        if Re < 4000:
            warn_list.append(f"Low Reynolds number ({Re:.0f}) - laminar flow expected")

        # L/D check for showerhead — V301/E2: kaynaksız bant, beyanlı.
        ld_lo, ld_hi = ORIFICE_LD_HEURISTIC_BAND
        if L_D is not None and (L_D < ld_lo or L_D > ld_hi):
            warn_list.append(
                f"L/D ratio ({L_D:.1f}) outside the {ld_lo:.0f}-{ld_hi:.0f} "
                f"band (HRMA heuristic threshold - no literature value; "
                f"NASA SP-8089 p. 84 notes that intermediate L/D of about "
                f"4-6 is susceptible to hydraulic flip)")

        # Kavitasyon (v2.6.2 DÜZELTMESİ, fizik denetimi F044): eski ölçüt
        # 'ΔP > 0.5·P_tank' buhar basıncını HİÇ içermiyordu — doymuş N₂O'da
        # (P₁ ≈ P_v, gerçek K_c ≈ 0, kavitasyon kesin) hiç uyarmıyor, düşük
        # buhar basınçlı sıvıda büyük ΔP'de yanlış-pozitif veriyordu.
        # Doğrusu Nurick kavitasyon sayısı: K_c = (P₁ − P_v)/(P₁ − P₂);
        # K_c < ~1.5 ise kavitasyon/hidrolik flip riski. Kardeş modül
        # (engines/injector_design.py) aynı kriteri uygular.
        # Kaynak: Nurick, ASME J. Fluids Eng. 98 (1976).
        # P_v BELİRSİZKEN HATA GÜVENSİZ TARAFA DÜŞER: K_c, P_v'nin kesin
        # azalan fonksiyonudur; P_v küçük tahmin edilirse K_c büyür ve uyarı
        # basılmaz. Lean ispatı: HRMA.underestimate_can_miss_warning
        # (bkz. docs/BICIMSEL_ISPATLAR.md).
        # v2.6.26 — GAZ FAZI MODELLENMİYOR VE BU SESSİZ KALAMAZ.
        # `oxidizer_phase` alanı yalnız aşağıdaki iki uyarıyı kapılıyordu;
        # 'gas' seçildiğinde delik boyutlandırması yine SIKIŞTIRILAMAZ (SPI)
        # modelle ve SIVI yoğunluğuyla yapılıyordu. Yani kullanıcı fazı
        # değiştiriyor, çıktıda tek bir fiziksel yaprak oynamıyor ve
        # aldığı sonuç sıvı enjeksiyona ait oluyordu — sessiz yanlış cevap.
        # Sıkıştırılabilir orifis çözümü depoda VAR
        # (engines/injector_design.py::compressible_orifice_flow, izentropik,
        # boğulma ayrımlı) ama bu yola bağlı değil. Bağlanana kadar durum
        # açıkça bildirilir.
        if self.ox_phase != 'liquid':
            warn_list.append(
                f"Oxidiser phase '{self.ox_phase}' is NOT modelled here: the "
                "orifice sizing below uses the incompressible (SPI) model with "
                "the liquid density, which is not valid for gas injection. "
                "Treat these hole sizes as liquid-phase values.")

        # ÖH Z5S / P10-A (P10B1-22) — K_c'nin İSTASYONU DÜZELTİLDİ.
        # Eski payda ``P_tank − P_c`` idi, yani orifisin ÜSTÜNDEKİ basınç
        # tank basıncı varsayılıyordu; oysa delik ``delta_P_inj`` ile
        # BOYUTLANDIRILMIŞTI. İki sayı ayrıldığında (kullanıcı ΔP'si ya da
        # otomatik %20 seçimi) hüküm, var olmayan bir orifis için veriliyordu.
        # Ölçüldü (T = 250 K, P_tank = 50, Pc = 20, ΔP = 4 bar):
        #     eski  K_c = (50 − 16,35)/(50 − 20) = 1,12  -> uyarı YANDI
        #     doğru K_c = (24 − 16,35)/4        = 1,91  -> uyarı GEREKMİYOR
        # Kardeş modül (engines/injector_design.py:1055,1162) zaten
        # ``dp = P₁ − Pc`` ve ``K_c = (P₁ − P_v)/(P₁ − Pc)`` ile TEK
        # istasyondan çalışıyor; bu modül artık aynı sözleşmede. Eşik
        # (NURICK_KC_LIMIT) DEĞİŞMEDİ — yeni eşik icat edilmedi.
        #
        # Beslemenin ΔP'yi sınırladığı dalda ``delta_P_inj = P_tank − P_c``
        # olduğu için iki biçim orada ZATEN aynı sayıyı verir.
        doymus_giris = bool(getattr(self, 'saturated_inlet', False))
        if self.ox_phase == 'liquid' and not doymus_giris:
            if self.p_vapor_bar is None:
                # Buhar basıncı yoksa K_c HESAPLANAMAZ. Eski kod burada
                # uydurma bir P_v ile "risk yok" ya da "risk var" diyordu.
                warn_list.append(
                    f"Cavitation margin NOT evaluated: "
                    f"{self.p_vapor_unavailable_reason} No Nurick cavitation "
                    f"number is reported for this state.")
            else:
                p1 = self.injector_inlet_pressure_bar
                k_c = (p1 - self.p_vapor_bar) / max(self.delta_P_inj, 1e-9)
                if k_c < NURICK_KC_LIMIT:
                    warn_list.append(
                        f"Cavitation risk: Nurick cavitation number K_c = "
                        f"{k_c:.2f} < {NURICK_KC_LIMIT:.1f} "
                        f"(injector inlet P_1 = {p1:.1f} bar, "
                        f"dP = {self.delta_P_inj:.1f} bar, "
                        f"P_v = {self.p_vapor_bar:.1f} bar at "
                        f"{self.oxidizer_temp:.0f} K)")

        # Flash boiling risk for N2O — buhar basıncı artık sıcaklığa bağlı
        # doyma tablosundan (eski kod 51 bar @ 293 K sabitini kullanıyordu)
        if (self.ox_phase == 'liquid' and self.oxidizer_type == 'n2o'
                and not doymus_giris):
            if self.p_vapor_bar is None:
                warn_list.append(
                    f"Flash boiling risk NOT evaluated: "
                    f"{self.p_vapor_unavailable_reason}")
            elif self.P_c < self.p_vapor_bar * 0.8:
                warn_list.append("Flash boiling risk detected")

        if doymus_giris:
            warn_list.append({
                'code': SATURATED_INLET_NOTE_CODE,
                'severity': 'info',
                'message': SATURATED_INLET_NOTE,
                'fallback': SATURATED_INLET_NOTE,
            })

        return warn_list


# ---------------------------------------------------------------------------
# Enjektör plakası yapısal değerlendirmesi (v2.6.26)
# ---------------------------------------------------------------------------
# Kullanıcının seçtiği enjektör plakası malzemesi (injector_material) bu
# fonksiyona bağlanır; eskiden alan arayüzde vardı ama hiçbir hesaba
# ulaşmıyordu.
#
#   Eğilme  : Roark's Formulas for Stress and Strain, Tablo 11.2, durum 10b —
#             dairesel plaka, düzgün yayılı yük, kenar ANKASTRE. Kenardaki
#             radyal gerilme yönetir:
#                 sigma_max = 0.75 * q * a^2 / t^2
#             (a = plaka yarıçapı [m], t = kalınlık [m], q = basınç farkı [Pa])
#             Ankastre kabulü enjektör plakasında doğru taraftadır: plaka
#             cıvatalı flanşla sıkıştırılır, serbest mesnetli değildir.
#
#   Delikler: ASME BPVC Bölüm I, PG-52 — ligament verimi. Delikli plakada
#             taşıyan kesit zayıflar, gerilme ligament verimine BÖLÜNÜR:
#                 eta = (p - d) / p
#             Delik düzeni girdi olarak gelmediğinden p, plakaya eşit dağılmış
#             kare düzen kabulüyle p = sqrt(A_plaka / n) alınır. Bu bir
#             KABULDÜR ve raporda 'ligament_basis' ile açıkça beyan edilir.
#
# Eğilme gerilmesi malzemeden BAĞIMSIZDIR (yalnız geometri ve yüke bağlıdır);
# malzemeye bağlı olan emniyet katsayısı ve gereken kalınlıktır. İkisini
# karıştırmak bu modelde kolay bir hata olurdu.
#
# Eksik/geçersiz girdide sayı UYDURULMAZ: rapor 'not_analyzed' döner ve
# nedenini yazar.

# Kullanıcı hedef emniyet katsayısı vermediğinde kullanılan değer. Basınçlı
# kap kabuğu değil, cıvatalı bir kapak plakası olduğu için 2.0 alınır;
# kullanıcı safety_factor girdiğinde onun değeri geçerlidir.
INJECTOR_PLATE_DEFAULT_SF = 2.0
# Ligament verimi bunun altına inerse eğilme modeli fiziksel anlamını yitirir
# (plaka fiilen bir elek hâline gelir).
INJECTOR_PLATE_MIN_LIGAMENT = 0.15


class InjectorPlateInputError(ValueError):
    """Plaka raporunun istemci girdisi hatası — uç katmanı 422'ye çevirir.

    ``hrma.utils.input_guard.InputError`` ile aynı sözleşmede (alan adı
    mesajın içinde tırnaklı geçer) ama bu modülün P4 kulvarının dosyasına
    yazma hakkı olmadığı için yerel olarak tanımlanır.
    """


def _plate_required_sf(value):
    """Hedef emniyet katsayısı sözleşmesi: verilmediyse varsayılan, verildiyse > 0.

    ÖH Z5S / P10-A (P10B1-25) — ÖLÇÜLDÜ (28 Ağustos 2026): bu değer
    istemciden geliyor (``app.py`` ``data.get('safety_factor')``) ve HİÇ
    denetlenmiyordu:

        safety_factor = -1  -> status 'analyzed',
                               required_safety_factor -1.0,
                               required_thickness_mm NaN (JSON'da null),
                               warnings []
        safety_factor =  0  -> ``_plate_num(0) or 2.0`` yüzünden SESSİZCE
                               2,0'a dönüyordu (kullanıcı 0 yazdığını
                               unutuyor, raporda 2,0 görüyordu)

    Negatif SF karekökün içini negatif yapar; sonuç NaN'dır ve "analiz
    edildi" damgasıyla yayımlanır. Artık sayı uydurulmaz ve sessizce
    düzeltilmez: alan ADIYLA reddedilir. Dönüş ``(sf, kaynak)``.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return INJECTOR_PLATE_DEFAULT_SF, 'default'
    if isinstance(value, bool):
        raise InjectorPlateInputError(
            "'safety_factor' must be a number (got bool)")
    try:
        sf = float(value)
    except (TypeError, ValueError):
        raise InjectorPlateInputError(
            f"'safety_factor' must be a number (got {value!r})")
    if sf != sf or sf in (float('inf'), float('-inf')):
        raise InjectorPlateInputError(
            f"'safety_factor' must be a finite number (got {value!r})")
    if sf <= 0:
        raise InjectorPlateInputError(
            f"'safety_factor' must be greater than zero; got {sf:g}. A "
            f"non-positive target safety factor has no meaning for the "
            f"injector plate: the required thickness "
            f"t = sqrt(0.75*q*a^2*SF/(sigma_y*eta)) is not defined for it.")
    return sf, 'user'


def _plate_num(value):
    """Sayıya zorlar; çevrilemezse None döner (string girdide çökme yasağı)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float('inf'), float('-inf')):
        return None
    return v


def injector_plate_structural(delta_P_bar, plate_diameter_m, material_props,
                              material_name=None, plate_thickness_m=None,
                              n_holes=0, hole_diameter_m=0.0,
                              required_sf=None):
    """Enjektör plakasının eğilme gerilmesi, emniyet katsayısı ve kütlesi.

    Dönen sözlük ya {'status': 'not_analyzed', 'reason': ...} biçimindedir ya
    da eğilme sonuçlarını taşır. 'not_analyzed' durumunda 'safety_factor'
    anahtarı BULUNMAZ — okuyan taraf eksikliği sıfır sanmasın diye.

    ``required_sf`` geçersizse (bool / sayı değil / sonsuz / <= 0)
    :class:`InjectorPlateInputError` yükselir: geçersiz bir hedefle
    "analiz edildi" damgalı NaN yayımlamak yerine istek reddedilir.
    """
    # İSTEMCİ GİRDİSİ ÖNCE DENETLENİR (P10B1-25): geometri/malzeme eksik
    # olsa bile geçersiz bir SF sessizce geçmemeli.
    hedef_sf, sf_kaynagi = _plate_required_sf(required_sf)

    q_bar = _plate_num(delta_P_bar)
    d_plate = _plate_num(plate_diameter_m)
    t_plate = _plate_num(plate_thickness_m)
    n = int(_plate_num(n_holes) or 0)
    d_hole = _plate_num(hole_diameter_m) or 0.0

    ad = material_name or (material_props or {}).get('name') or 'unknown'

    if not q_bar or q_bar <= 0:
        return {'status': 'not_analyzed',
                'reason': 'injector pressure drop is not available',
                'material': ad}
    if not d_plate or d_plate <= 0:
        return {'status': 'not_analyzed',
                'reason': 'plate diameter (chamber diameter) is not available',
                'material': ad}

    sigma_y = _plate_num((material_props or {}).get('yield_strength'))
    if not sigma_y or sigma_y <= 0:
        return {'status': 'not_analyzed',
                'reason': f"material '{ad}' has no yield strength record",
                'material': ad}

    a = d_plate / 2.0                      # plaka yarıçapı [m]
    q = q_bar * 1e5                        # [bar] -> [Pa]
    area_plate = np.pi * a ** 2            # [m^2]

    # --- ASME PG-52 ligament verimi ---------------------------------------
    eta = 1.0
    ligament_basis = 'solid plate (no hole data)'
    if n > 0 and d_hole > 0:
        pitch = float(np.sqrt(area_plate / n))     # kare düzen kabulü
        eta = (pitch - d_hole) / pitch if pitch > 0 else -1.0
        ligament_basis = ('ASME PG-52, equivalent square pitch '
                          f'p = sqrt(A/n) = {pitch * 1000:.2f} mm')
        if eta <= INJECTOR_PLATE_MIN_LIGAMENT:
            return {
                'status': 'not_analyzed',
                'reason': (f'ligament efficiency {eta:.2f} is below the '
                           f'{INJECTOR_PLATE_MIN_LIGAMENT:.2f} limit: '
                           f'{n} holes of {d_hole * 1000:.2f} mm consume the '
                           f'plate, the bending model no longer applies'),
                'material': ad,
                'ligament_efficiency': round(eta, 4),
                'ligament_basis': ligament_basis,
            }

    # --- Roark 11.2 / 10b --------------------------------------------------
    # SF hedefini tutan kalınlık: sigma_y/SF = 0.75*q*a^2/(t^2*eta)
    t_required = float(np.sqrt(0.75 * q * a ** 2 * hedef_sf / (sigma_y * eta)))

    rapor = {
        'status': 'analyzed',
        'material': ad,
        'model': 'Roark Table 11.2 case 10b (clamped circular plate)',
        'delta_P_bar': round(q_bar, 4),
        'plate_diameter_mm': round(d_plate * 1000, 3),
        'yield_strength_MPa': round(sigma_y / 1e6, 1),
        'ligament_efficiency': round(eta, 4),
        'ligament_basis': ligament_basis,
        # ÖH D35 / OH-ON-01 — DENETLENEN PLAKANIN DELİK PLANI YANITTA DURUR.
        # ÖLÇÜLDÜ (``a1/once.json`` H1): rapor ``ligament_basis`` dizesinin
        # içinde adım (p) veriyordu ama delik SAYISINI ve ÇAPINI hiç
        # yayımlamıyordu; dolayısıyla "hangi plaka denetlendi" sorusu
        # yanıttan makine-okur biçimde cevaplanamıyordu ve denetlenen plaka
        # ile çizilen plakanın ayrıştığı üç sürüm boyunca görülmedi.
        'n_holes': n,
        'hole_diameter_mm': round(d_hole * 1000, 4) if d_hole else 0.0,
        'required_safety_factor': round(hedef_sf, 3),
        # Künye: hedef SF kullanıcıdan mı geldi yoksa modülün belgeli
        # varsayılanı mı — rapor "kimin sayısı" sorusunu cevaplar.
        'required_safety_factor_source': sf_kaynagi,
        'required_thickness_mm': round(t_required * 1000, 3),
        'warnings': [],
    }

    if t_plate and t_plate > 0:
        sigma = 0.75 * q * a ** 2 / (t_plate ** 2 * eta)
        sf = sigma_y / sigma
        rapor['plate_thickness_mm'] = round(t_plate * 1000, 3)
        rapor['bending_stress_MPa'] = round(sigma / 1e6, 3)
        rapor['safety_factor'] = round(sf, 3)
        yogunluk = _plate_num((material_props or {}).get('density'))
        if yogunluk:
            delik_alani = n * np.pi * (d_hole / 2.0) ** 2 if (n and d_hole) else 0.0
            hacim = max(area_plate - delik_alani, 0.0) * t_plate
            rapor['plate_mass_kg'] = round(yogunluk * hacim, 4)
        if sf < hedef_sf:
            rapor['warnings'].append(
                f'Injector plate safety factor {sf:.2f} is below the target '
                f'{hedef_sf:.2f}: {t_required * 1000:.2f} mm required, '
                f'{t_plate * 1000:.2f} mm given ({ad}).')
    else:
        # Kalınlık verilmemiş: boyutlandırma modu. Emniyet katsayısı
        # RAPORLANMAZ — hangi kalınlığa ait olduğu belirsiz olurdu.
        rapor['status'] = 'sized'
        rapor['warnings'].append(
            'Plate thickness was not supplied; the reported thickness is the '
            'minimum that meets the target safety factor.')

    return rapor


def withhold_validation_pass_for_target_flow(validation_report,
                                             injector_results):
    """Hedef debiyi tutmayan kırpılmış plan "geçti" hükmü almaz (7. tur).

    ÖH D37 A2 hibrit · 7. tur (karar §28-25, Astra şartı). ÖLÇÜLDÜ
    (Ornek-H1 çarpışmalı 50 N, ``element_pairs`` 3): kırpılmış planın
    yayımlanan ΔP'deki debisi hedefin 2,08 katıyken /calculate doğrulama
    özeti ``validation_passed: True`` basıyordu.

    ``injector_results['target_flow_check']`` fail-closed sınıf taşıyorsa
    (``TARGET_FLOW_NOT_MET``) kayıt (``clamped_plan_target_flow_record``,
    severity ``critical``) ``critical_warnings`` dizisine eklenir,
    ``validation_passed`` False ve durum satırı ``status.critical`` olur —
    ``app.py::_emniyet_uyarilarini_yayimla``nın kritik kayıt kuralının
    aynısı. Sınıf yoksa (plan kırpılmadı ya da hedefi tolerans içinde
    tutuyor) rapor DOKUNULMADAN döner (bit-aynı). Rapor üretilemediyse
    (``status: not_evaluated``; uyarı dizileri bilerek yok) dizi
    uydurulmaz — o raporda hüküm zaten geri çekilmiştir.

    Returns:
        Eklenen kayıt ya da ``None``.
    """
    if not (isinstance(validation_report, dict)
            and isinstance(injector_results, dict)):
        return None
    kayit = clamped_plan_target_flow_record(
        injector_results.get('target_flow_check'))
    if kayit is None or 'critical_warnings' not in validation_report:
        return None
    from hrma.validation.validation_system import _w as _vs_w
    validation_report['critical_warnings'] = (
        list(validation_report.get('critical_warnings') or []) + [kayit])
    validation_report['total_warnings'] = (
        int(validation_report.get('total_warnings') or 0) + 1)
    validation_report['validation_passed'] = False
    validation_report['overall_status'] = _vs_w('status.critical', 'critical')
    return kayit


# ---------------------------------------------------------------------------
# ÖH D31 / OH-D30-01 — GERİYE DÖNÜK AD ÇÖZÜMÜ (PEP 562)
# ---------------------------------------------------------------------------
# Yukarıdaki dairesel halka sökülünce şu adlar artık modül YÜKÜNDE tanımlı
# değil. Depoda ve testlerde ``from hrma.utils.injector_design import
# LOCAL_DENSITY_FALLBACK`` gibi ESKİ kullanımlar var; onlar bozulmasın diye
# adlar İLK DOKUNULDUĞUNDA çözülür ve önbelleğe alınır. Değerler birebir
# eskisiyle aynıdır — değişen yalnız çözülme ANIdır.
_GECIKMELI_ADLAR = {
    'data_fetcher': ('hrma.data.external_data_fetcher', 'data_fetcher'),
    'oxidizer_reference_density': ('hrma.data.external_data_fetcher',
                                   'oxidizer_reference_density'),
    'OxidizerStateError': ('hrma.data.external_data_fetcher',
                           'OxidizerStateError'),
    'OXIDIZER_STATE_TOLERANCE': ('hrma.data.external_data_fetcher',
                                 'OXIDIZER_STATE_TOLERANCE'),
    'N2OSaturation': ('hrma.analysis.tank_blowdown', 'N2OSaturation'),
}


def _showerhead_clamp_text(inj, params, n_holes, n_istenen, area_per_hole,
                           a_required, delta_P_Pa):
    """Kanon DIŞI duş başlığı kırpma metni (``_calculate_showerhead``).

    ÖH D37 A2 hibrit · 9. tur (7. tur Devir 36). Metin "hole count adjusted
    to N to preserve target flow rate" diyordu; oysa 7. turdan beri bu yolun
    hedef debi sınıfı var ve ölçüldü (rapor 9. tur, ``SHu_n4``: 4 → 5 ×
    2,5 mm, teslim alanı gerekenin 1,18 katı → ``target_flow_not_met`` +
    kritik doğrulama) — "korur" iddiası sınıfla çelişiyordu. ΔP yeniden
    çözülmez, hedef debi doğrulanmaz: çarpışmalı kırpma ile AYNI teslim
    cümlesi (``_impingement_clamp_delivery``; 5. tur Ş-5, §28-18) eklenir.
    Plan (n × d) ve sayılar DEĞİŞMEZ. İşlev modül sonundadır: sınıf
    gövdesinin satır numaraları ``formal/registry.json`` Lean çapalarıdır.
    """
    metin = (
        f"Hole diameter clamped to manufacturing band "
        f"({params['d_min']*1000:.2f}-{params['d_max']*1000:.2f} mm); "
        f"hole count adjusted to {n_holes} to cover the injection "
        f"area required for the target flow at the design pressure "
        f"drop.")
    if n_istenen:
        metin += (f" The requested hole count ({n_istenen}) was NOT "
                  f"delivered.")
    return metin + inj._impingement_clamp_delivery(
        n_holes * area_per_hole, a_required, delta_P_Pa)


def _fixed_d_clamp_text(params, n_pairs_requested, n_pairs, d_h, d_h_clamped,
                        k):
    """Kullanıcının sabitlediği çarpışmalı çapta kırpma metni (gövde).

    ÖH D37 A2 hibrit · 9. tur (7. tur Devir 37). Kullanıcı ``orifice_diameter``
    verince app.py bandı o değere kilitler (d_min = d_max). Kırpma bu yolda
    da olur ve 7. turdan beri hedef debi sınıfı ile kritik doğrulama kaydı
    uygulanır, ama METİN yoktu (otomatik çiftte hiç; istenen çift değişince
    "manufacturing band (1.00-1.00 mm)" diye YANLIŞ adla). ÖLÇÜLDÜ (rapor
    9. tur, ``I50od1`` 2 × 2 × 1,0 mm, oran 8,22; ``I50od1e3``). Sabit çap
    adıyla yayımlanır; teslim cümlesini çağıran ekler. ``k``: çap ondalığı
    (``band_warning_decimals``, Devir 35). Plan (n × d) DEĞİŞMEZ.
    """
    kaynak = ('the requested' if params['n_pairs'] > 0
              else 'the auto-selected minimum of')
    return (f"Hole diameter fixed by the request at "
            f"{d_h_clamped * 1000:.{k}f} mm (orifice_diameter): "
            f"{kaynak} {n_pairs_requested} doublet pairs would need "
            f"{d_h * 1000:.{k}f} mm holes for the target flow at the "
            f"design pressure drop, so the plan uses {n_pairs} pairs "
            f"of {d_h_clamped * 1000:.{k}f} mm holes.")


def __getattr__(ad):
    """Gecikmeli çözülen modül öznitelikleri (OH-D30-01)."""
    if ad in _GECIKMELI_ADLAR:
        import importlib
        modul_adi, oznitelik = _GECIKMELI_ADLAR[ad]
        deger = getattr(importlib.import_module(modul_adi), oznitelik)
        globals()[ad] = deger          # bir kez çözülür
        return deger
    if ad == 'LOCAL_DENSITY_FALLBACK':
        deger = _local_density_fallback()
        globals()[ad] = deger
        return deger
    if ad == '_SAT_N2O':
        return _sat_n2o()
    raise AttributeError(
        f'module {__name__!r} has no attribute {ad!r}')


def __dir__():
    return sorted(set(globals()) | set(_GECIKMELI_ADLAR)
                  | {'LOCAL_DENSITY_FALLBACK', '_SAT_N2O'})


# ---------------------------------------------------------------------------
# ÖH D37 A2 hibrit · 10. tur (HB9 devir 48) — kanon bant metninin çap ondalığı.
# Bu blok BİLEREK modül sonundadır (sınıf gövdesinin satır numaraları
# ``formal/registry.json`` Lean çapalarıdır).
# ---------------------------------------------------------------------------
#: Kanon plaka bant metninin ("Solved orifice diameter … is outside the
#: manufacturing band") çap ondalığı — eski ``:.4f`` biçimi. Gösterim hükümle
#: çelişmedikçe metin bit-aynı kalır.
KANON_BANT_METNI_CAP_ONDALIGI = 4


def _kanon_cap_ondaligi(d_h, params):
    """Kanon bant metninde çapın ondalık sayısı.

    ÖLÇÜLDÜ (HB9 devir 48): ``:.4f`` biçimi d ∈ [0,49995; 0,5) mm'de
    "0.5000 mm is outside the manufacturing band (0.50-2.50 mm)" basıyordu —
    gösterilen çap gösterilen kenara EŞİT, metin kendi hükmüyle çelişiyordu
    (Devir 35'in kardeşi; üst kenarda [2,5; 2,50005) aynı). Ondalık,
    ``band_warning_decimals`` kuralıyla (yuvarlanmış çapın kenarlara göre
    konumu gerçeğiyle aynı olana dek) artırılır; en az
    ``KANON_BANT_METNI_CAP_ONDALIGI``. Pencere dışında metin bit-aynı.
    """
    return max(KANON_BANT_METNI_CAP_ONDALIGI,
               band_warning_decimals(d_h, params['d_min'], params['d_max']))


def _varsayilan_tank_t():
    """``InjectorDesign(oxidizer_temp=…)`` VERİLMEDİĞİNDE kullanılan sıcaklık.

    ÖH D37 A2 hibrit · 10. tur (HB9 devir 45, CLAUDE.md §11): sınıfın
    varsayılanı ``293`` literaliydi; motor, devre giriş durumu ve uç yedeği
    293,15 K (``TANK_TEMPERATURE_DEFAULT_K``) kullanıyordu. Sayı artık tek
    kaynaktan, gecikmeli okunur (``oxidizer_inlet.default_inlet_temperature_k``;
    modül düzeyinde içe aktarım döngü kurardı). Varsayılan ``Ellipsis``
    nöbetçisidir: açıkça ``None`` veren çağıran eskisi gibi ADIYLA reddedilir
    (sıcaklık sessizce varsayılmaz). Blok modül sonundadır (Lean çapaları).
    """
    from hrma.engines.oxidizer_inlet import default_inlet_temperature_k
    return default_inlet_temperature_k()
