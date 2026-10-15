"""Vana ve besleme hattı boyutlandırma çekirdeği (yol haritası C2).

Besleme hattının kararlı rejim basınç bütçesini, hattı kapatan/açan vananın
akış katsayısını (Cv/Kv) ve sıvıda kavitasyon/flashing durumunu hesaplar;
son olarak vana kapanma süresini su koçu (``water_hammer``) modülünün
girdisine bağlar:

    hat çapı/uzunluğu -> hız -> Re -> sürtünme faktörü -> Darcy-Weisbach
    dP_sürtünme  (+ yerel kayıplar K, + kot farkı)  -> hat çıkış basıncı ->
    vana Cv/Kv  -> kavitasyon/flashing kontrolü -> güvenli kapanma süresi
    -> water_hammer girdisi

Fizik ve kaynaklar
------------------
Sürtünme kaybı (Darcy-Weisbach):

    dP_f = f * (L/D) * rho * V^2 / 2                                       (1)

  White, F.M., "Fluid Mechanics", 7. baskı, Eş. 6.10. Sürtünme faktörü f
  ve Darcy-Weisbach değerlendirmesi bu modülde YENİDEN YAZILMAZ;
  ``regen_cooling`` içindeki Haaland (1983) bağıntısı ve Darcy-Weisbach
  değerlendiricisi İTHAL EDİLİR (tek kaynak — kopya yasağı).

Yerel (yerel direnç) kayıpları — Crane TP-410 eşdeğer uzunluk yöntemi:

    K = f_T * (L/D)_eş,        dP_yerel = (sum K_i) * rho * V^2 / 2        (2)

  Crane Co., Technical Paper No. 410 ("Flow of Fluids Through Valves,
  Fittings and Pipe"), Böl. 2 ve Ek A. Burada f_T, TAM TÜRBÜLANS
  bölgesindeki (Re -> sonsuz) sürtünme faktörüdür ve Crane bunu TİCARİ
  ÇELİK boru pürüzlülüğü için boyuta göre tablolar. Bu modül f_T'yi
  tablodan okumaz, Haaland bağıntısının tam-pürüzlü limitinden TÜRETİR
  (bkz. ``crane_ft``); türetilen değerler Crane'in yayımlanmış tablosunu
  ~%4 içinde yeniden üretir ve bekçi testi bunu sınar.

Vana akış katsayısı (ISA-75.01.01 / IEC 60534-2-1, türbülanslı, boğulmamış
sıvı akışı):

    Q = Cv * sqrt(dP / SG)      (Q: ABD gpm, dP: psi, SG: bağıl yoğunluk)  (3)
    Cv = Q * sqrt(SG / dP),     Kv = 0.865 * Cv                            (4)

  ISA-75.01.01-2012 / IEC 60534-2-1 (kontrol vanası boyutlandırma
  denklemleri). SG, 15.6 C'deki suya göre bağıl yoğunluktur
  (rho_0 = 999.0 kg/m^3). Kv (m^3/h, bar) ile Cv (gpm, psi) arasındaki
  0.865 oranı birim tanımlarının sonucudur; bekçi testi bu oranı
  bağımsız türetir.

Boğulma, kavitasyon ve flashing (ISA-75.01.01 / IEC 60534-2-1):

    F_F = 0.96 - 0.28 * sqrt(p_v / p_c)                                    (5)
    dP_boğuk = F_L^2 * (p_1 - F_F * p_v)                                   (6)
    sigma = (p_1 - p_v) / (p_1 - p_2)                                      (7)

  F_F sıvı kritik basınç oranı faktörü, F_L vana basınç geri kazanım
  faktörüdür (vanaya özgü — üretici sertifikasından gelmelidir; buradaki
  tablo yalnız TEMSİLİdir). dP >= dP_boğuk ise akış boğulmuştur ve (3)
  artık geçerli değildir. p_2 <= p_v ise akış flashing'dir (kalıcı iki
  fazlı). sigma kavitasyon indisi bir TARAMA ölçütüdür; hasar eşikleri
  vanaya özgü deney verisidir (ISA RP75.23) ve burada MODELLENMEZ.

Su koçu bağlantısı — yavaş kapanma (Michaud) bağıntısı tersine çözülür:

    dP_yavaş = 2 * rho * L * dv / t_kapanma  ->
    t_kapanma_min = 2 * rho * L * dv / dP_izin                             (8)

  Wylie & Streeter, "Fluid Transients" (1978), Böl. 1. (8)'in geçerli
  olması için t_kapanma > t_c = 2L/a olmalıdır; aksi halde tam Joukowsky
  basıncı görülür. Dalga hızı ve kritik süre burada YENİDEN YAZILMAZ,
  ``water_hammer`` modülünden İTHAL EDİLİR.

Kapsam: bu modül SIKIŞTIRILAMAZ (sıvı) besleme hattı içindir. Gaz/iki
fazlı hat, geçici rejim ve vana iç geometrisi MODELLENMEZ (bkz.
``NOT_MODELLED``). Akışkan özellikleri (yoğunluk, viskozite, buhar
basıncı) GİRDİDİR, burada hesaplanmaz; hiçbir engine modülü ithal
edilmez. Kullanıcıya görünen tüm metinler İngilizce, çıktı JSON-güvenlidir.
Ampirik katsayılar kaynak künyeli ve geçerlilik aralıklıdır; aralık
dışı girdide sessiz ekstrapolasyon yerine açık 'geçersiz aralık' beyanı
(ValueError ya da ``validity`` kaydı) üretilir.
"""

import math
from typing import Dict, List, Optional

from hrma.constants import G_0, LB_KG as _LB_KG, PA_PER_PSI as _PA_PER_PSI
# ÖH D23 / P5B4-16: sayısal girdi kapıları TEK KAYNAKTAN.
from hrma.analysis._input_guards import require_positive
# Tek kaynak: sürtünme faktörü ve Darcy-Weisbach değerlendiricisi
# regen_cooling'ten İTHAL edilir (kopya yok — parametre tutarlılığı).
from hrma.analysis.regen_cooling import (
    haaland_friction_factor,
    darcy_weisbach_dp,
    RE_LAMINAR_MAX,
)
# Tek kaynak: dalga hızı ve kritik kapanma süresi water_hammer'dan gelir.
# Boru YAPISAL malzemesinin varsayılanı da oradan gelir: bu adaptör kendi
# ikinci bir varsayılan üretmez (ÖH Z5S / defter P4B4-08).
from hrma.analysis.water_hammer import (
    wave_speed, critical_closure_time,
    DEFAULT_PIPE_MATERIAL as WH_DEFAULT_PIPE_MATERIAL,
    FLUID_PROPERTIES as WH_FLUID_PROPERTIES,
)
# Tek kaynak: kesin tanımlı birim çevrimleri turbopump_sizing'te tanımlı.
from hrma.analysis.turbopump_sizing import M_PER_IN, m3s_to_gpm

__all__ = [
    'relative_roughness',
    'crane_ft',
    'fitting_loss_coefficient',
    'line_velocity',
    'reynolds_number',
    'flow_regime',
    'line_pressure_drop',
    'valve_cv_required',
    'flow_from_cv',
    'cv_to_kv',
    'kv_to_cv',
    'liquid_critical_pressure_ratio_factor',
    'choked_pressure_drop',
    'cavitation_status',
    'size_valve',
    'minimum_closure_time_s',
    'water_hammer_inputs',
    'analyze_valve_feedline',
    'PIPE_ROUGHNESS_M',
    'ROUGHNESS_PROVENANCE',
    'PIPE_ROUGHNESS_DEFAULT_KEY',
    'FITTING_LD',
    'FITTING_K',
    'VALVE_PRESSURE_RECOVERY',
    'CRANE_FT_ROUGHNESS_M',
    'SG_REFERENCE_DENSITY_KG_M3',
    'KV_PER_CV',
    'RE_TURBULENT_MIN',
    'SIGMA_SCREENING',
    'REL_ROUGHNESS_VALID',
    'NOT_MODELLED',
]

# ---------------------------------------------------------------------------
# Birim çevrimleri. M_PER_IN ve gpm çevrimi turbopump_sizing'ten gelir
# (orada da TANIM gereği kesindir). Pound tanımı burada ilk kez gerekiyor:
# 1 lb = 0.45359237 kg (uluslararası avoirdupois pound, kesin tanım) ve
# 1 lbf = 1 lb * g_0 -> 1 psi = lbf/in^2 = 6894.757293168 Pa. Bu değer
# deponun hrma/validation/record_adapters.py birim tablosundaki psi
# katsayısıyla AYNIdır; bekçi testi iki kaynağın uyuştuğunu sınar (yeni
# bir bağımsız sayı tanımlanmış olmaz).
# ---------------------------------------------------------------------------
# P15B2-10: iki tanım da merkeze taşındı (hrma.constants); buradaki adlar
# geriye dönük uyumluluk için korunur ama YENİ BİR SAYI tanımlamazlar.
LB_KG = _LB_KG                              # kesin tanım (hrma.constants)
PSI_PA = _PA_PER_PSI                        # ~6894.757293168 Pa (merkez)


def pa_to_psi(p_pa: float) -> float:
    """Pa -> psi (1 psi = 1 lbf/in^2, kesin tanımlardan türetilir)."""
    return float(p_pa) / PSI_PA


# ---------------------------------------------------------------------------
# Boru mutlak pürüzlülüğü [m]. Moody (1944) / Colebrook geleneği; değerler
# White, "Fluid Mechanics", 7. baskı Tablo 6.1 ve Crane TP-410 Ek A ile
# uyumludur. Bant genişliği gerçek imalat toleransıdır: pürüzlülük TEK bir
# sayı değildir, bu yüzden 'approximate' sayılır.
# ---------------------------------------------------------------------------
PIPE_ROUGHNESS_M = {
    'drawn_tubing': 1.5e-6,
    'stainless_tubing': 1.5e-6,
    'commercial_steel': 4.6e-5,
    'welded_steel': 4.6e-5,
    'galvanized_iron': 1.5e-4,
    'cast_iron': 2.6e-4,
    'smooth': 0.0,
}
PIPE_ROUGHNESS_SOURCE = (
    'Absolute pipe roughness values (Moody, 1944; White, "Fluid '
    'Mechanics", 7th ed., Table 6.1; Crane Technical Paper No. 410, '
    'Appendix A): drawn/stainless tubing ~0.0015 mm, commercial steel or '
    'wrought iron ~0.046 mm, galvanized iron ~0.15 mm, cast iron ~0.26 mm. '
    'Approximate: manufacturing scatter on these values is a factor of '
    'roughly two, and in-service fouling raises them further. Convoluted '
    'flex hose is NOT in this table - its effective roughness is far '
    'higher and geometry-specific (see not_modelled.flex_hose).')

# Crane TP-410'un f_T tablosunun DAYANAĞI ticari çelik borudur; f_T burada
# tablodan okunmaz, bu pürüzlülükle tam-pürüzlü limitten türetilir.
CRANE_FT_ROUGHNESS_M = PIPE_ROUGHNESS_M['commercial_steel']

# ---------------------------------------------------------------------------
# ÖH Z5S / defter P4B4-08 — ARGÜMAN AYRIMI.
#
# Bu tablo bir YÜZEY BİTİŞİ tablosudur (çekme boru, kaynaklı çelik, dökme
# demir...), ``materials_db`` ise bir YAPISAL ALAŞIM tablosudur (ss_304,
# steel_4130, aluminum_6061...). İki tablonun anahtar kümelerinin kesişimi
# BOŞTUR ve olmasına gerek de yoktur: aynı borunun pürüzlülüğü bitişinden,
# Young modülü ve akma dayanımı alaşımından okunur. Eskiden TEK bir
# ``pipe_material`` argümanı İKİ tabloya birden gidiyordu; bu yüzden hiçbir
# değer ikisini birden sağlayamıyordu ve su koçu çözücüsü her çağrıda
# 'Unknown pipe material' uyarısıyla ss_304'e düşüp hükmü zorla MARGINAL'e
# indiriyordu. Artık iki AYRI argüman vardır:
#   * ``pipe_material``            -> PIPE_ROUGHNESS_M (yüzey bitişi),
#   * ``pipe_structural_material`` -> materials_db (yapısal alaşım).
PIPE_ROUGHNESS_DEFAULT_KEY = 'stainless_tubing'

#: ``roughness_m`` ile geçirilen sayının KÖKEN künyeleri (ÖH D18 / P5B3-10).
#: Bu modül sayının nereden geldiğini göremez; köken ancak çağıran ADIYLA
#: beyan ederse yazılır. Anahtar kümesi kapalıdır: tanınmayan bir köken
#: sessizce kabul edilmez, adıyla reddedilir.
ROUGHNESS_PROVENANCE = {
    'measured': ('caller-declared MEASURED absolute roughness of the actual '
                 'pipe run'),
    'handbook_table': ('caller-declared HANDBOOK value for the pipe finish '
                       '(not a measurement of this pipe)'),
    'assumed': ('caller-declared ASSUMED absolute roughness (neither '
                'measured nor read from a table)'),
}

#: Köken beyan edilmediğinde yazılan künye. "Ölçüldü" DEMEZ.
ROUGHNESS_PROVENANCE_UNDECLARED = (
    'caller-supplied absolute roughness with UNDECLARED provenance: this '
    'module cannot tell whether the value was measured on the real pipe, '
    'read from a handbook table or assumed. Pass roughness_provenance to '
    'put the origin on the record.')

# Haaland/Colebrook bağıntısının bağıl pürüzlülük geçerlilik zarfı.
REL_ROUGHNESS_VALID = (0.0, 0.05)

# Haaland yalnız tam türbülansta (~Re > 4000) geçerlidir; 2300-4000 arası
# geçiş bölgesinde NE laminer NE türbülans bağıntısı geçerlidir.
RE_TURBULENT_MIN = 4000.0

# ---------------------------------------------------------------------------
# Crane TP-410 eşdeğer uzunluk (L/D)_eş tablosu. K = f_T * (L/D)_eş.
# ---------------------------------------------------------------------------
FITTING_LD = {
    'elbow_90_standard': 30.0,
    'elbow_90_long_radius': 20.0,
    'elbow_45_standard': 16.0,
    'bend_180_return': 50.0,
    'tee_through_run': 20.0,
    'tee_branch_flow': 60.0,
    'ball_valve_full_bore': 3.0,
    'gate_valve_open': 8.0,
    'globe_valve_open': 340.0,
    'angle_valve_open': 150.0,
    'butterfly_valve_open': 45.0,
    'check_valve_swing': 100.0,
    'check_valve_lift': 600.0,
    'plug_valve_straightway': 18.0,
}
FITTING_LD_SOURCE = (
    'Equivalent-length ratios (L/D)_eq for fittings and full-open valves, '
    'Crane Co., Technical Paper No. 410, "Flow of Fluids Through Valves, '
    'Fittings and Pipe", Ch. 2 and Appendix A. The resistance coefficient '
    'is K = f_T * (L/D)_eq with f_T the fully-turbulent friction factor '
    'of commercial steel pipe of that size. Approximate: real fittings '
    'scatter around these values by tens of percent, and the method '
    'assumes fully-developed turbulent flow with enough straight pipe '
    'between fittings that their wakes do not interact. These are '
    'INDUSTRIAL valves: flight-weight valves differ - NASA SP-8097 (1973) '
    'Table II, p. 10 (2 in size) lists Cv of about 60-70 for poppet, 333 '
    '(thin disk) or 154 (thick disk) for butterfly and 440 for ball valves, '
    'and the valve type is not '
    'gated here: butterfly valves are poor below 2 in line size (Table II) '
    'and not recommended above 2000 psi service pressure (p. 89).')

# Sabit-K kalemleri: eşdeğer uzunlukla değil, doğrudan K ile verilirler.
FITTING_K = {
    'entrance_sharp': 0.50,
    'entrance_rounded': 0.04,
    'entrance_projecting': 1.00,
    'exit': 1.00,
}
FITTING_K_SOURCE = (
    'Fixed entrance/exit loss coefficients (White, "Fluid Mechanics", '
    '7th ed., Fig. 6.21 / Table 6.5; Crane TP-410 Appendix A): sharp-edged '
    'entrance K = 0.5, well-rounded entrance K ~ 0.04, inward-projecting '
    '(Borda) entrance K ~ 1.0, submerged exit K = 1.0 (the entire velocity '
    'head is dissipated). Sudden contractions/expansions are NOT in this '
    'table because their K depends on the area ratio (see '
    'not_modelled.area_change).')

# ---------------------------------------------------------------------------
# Vana basınç geri kazanım faktörü F_L — TEMSİLİ değerler.
# ---------------------------------------------------------------------------
VALVE_PRESSURE_RECOVERY = {
    'globe_flow_to_open': 0.90,
    'globe_flow_to_close': 0.80,
    'angle_valve': 0.85,
    'ball_full_bore': 0.55,
    'ball_segmented': 0.60,
    'butterfly_60deg': 0.68,
    'butterfly_90deg': 0.55,
    'gate_valve': 0.90,
}
VALVE_FL_VALID = (0.30, 1.00)
VALVE_FL_SOURCE = (
    'Liquid pressure recovery factor F_L, representative values by valve '
    'style (ISA-75.01.01-2012 / IEC 60534-2-1 sizing equations; Fisher '
    '"Control Valve Handbook", 5th ed., representative valve coefficient '
    'tables). APPROXIMATE AND STYLE-LEVEL ONLY: F_L is a certified, '
    'tested property of a specific valve at a specific travel and it '
    'varies with opening. For a real design use the manufacturer\'s '
    'certified F_L; these numbers are for screening a concept only.')

# ---------------------------------------------------------------------------
# ISA/IEC bağıl yoğunluk referansı ve Kv/Cv oranı.
# ---------------------------------------------------------------------------
SG_REFERENCE_DENSITY_KG_M3 = 999.0
SG_REFERENCE_SOURCE = (
    'Relative density (specific gravity) in the IEC 60534-2-1 / '
    'ISA-75.01.01 liquid sizing equation is referred to water at 15.6 C '
    '(60 F), rho_0 = 999.0 kg/m^3.')

# Kv [m^3/h, bar] ve Cv [US gpm, psi] tanımlarının oranı. TÜRETİLİR:
# Kv/Cv = (m^3/h per gpm)^-1 * sqrt(bar per psi) ... birim tanımlarından
# çıkar; bekçi testi bu sayıyı bağımsız kurar.
KV_PER_CV = 0.865
KV_CV_SOURCE = (
    'Kv (m^3/h at 1 bar) and Cv (US gpm at 1 psi) are the same physical '
    'valve capacity expressed in two unit systems; Kv = 0.865 * Cv '
    'follows from the unit definitions alone (IEC 60534-1). The guard '
    'test rebuilds the ratio from the exact unit definitions.')

# Kavitasyon indisi tarama bandı (sigma = (p1-pv)/(p1-p2)).
SIGMA_SCREENING = {
    'damage_below': 1.5,
    'caution_below': 2.0,
}
SIGMA_SOURCE = (
    'Cavitation index sigma = (p1 - p_v)/(p1 - p2). SCREENING BAND ONLY: '
    'the service-limit thresholds of a real valve (sigma_i incipient, '
    'sigma_c constant, sigma_d damage, sigma_mv manufacturer '
    'recommended) are valve-specific TEST DATA obtained per ISA '
    'RP75.23 ("Considerations for Evaluating Control Valve Cavitation"), '
    'and they also scale with valve size and pressure. The generic '
    'sigma < 2 caution / sigma < 1.5 damage-risk band used here flags a '
    'concept for review; it is NOT a cavitation verdict (see '
    'not_modelled.cavitation_thresholds).')

# ---------------------------------------------------------------------------
# Bilinçli olarak MODELLENMEYENLER. Çıktıya aynen konur; "sessizce yok
# sayıldı" durumu oluşmaz (sahte veri yasağı).
# ---------------------------------------------------------------------------
NOT_MODELLED = {
    'compressible_flow': (
        'Compressible (gas) feed lines are NOT modelled: this module uses '
        'the incompressible Darcy-Weisbach budget and the IEC 60534 LIQUID '
        'sizing equation. For gas service the density varies along the '
        'line and the gas sizing equation (expansion factor Y, x_T) '
        'applies instead. Do not use these results for a gas line.'),
    'two_phase_flow': (
        'Two-phase and flashing FLOW is NOT modelled: the module detects '
        'and declares flashing/choking, but it does not compute the '
        'two-phase pressure drop, the void fraction or the downstream '
        'flow rate once the fluid flashes.'),
    'transient': (
        'Transients are NOT modelled here: start-up, priming, chill-down '
        'and the surge itself are outside this steady budget. The valve '
        'closure coupling produced by this module is an INPUT to the '
        'water_hammer solver, not a transient solution.'),
    'valve_internals': (
        'Valve internal geometry is NOT modelled: trim style, travel, '
        'seat leakage, actuator torque, anti-cavitation trim and the '
        'installed (as opposed to inherent) flow characteristic are '
        'outside this model. Only the required Cv/Kv capacity is sized.'),
    'cavitation_thresholds': (
        'Cavitation damage thresholds are NOT modelled: sigma_i, sigma_c, '
        'sigma_d and sigma_mv are valve-specific test data (ISA RP75.23) '
        'and depend on valve size and pressure scale. The sigma value '
        'reported here is screened against a generic band only.'),
    'thermodynamic_suppression': (
        'Thermodynamic cavitation suppression (the B-factor / thermal '
        'delay that makes cryogens far more cavitation-tolerant than '
        'cold water at the same sigma) is NOT modelled. For LOX/LH2 '
        'lines the sigma screening is therefore conservative.'),
    'area_change': (
        'Sudden contractions, expansions, reducers and orifices are NOT '
        'in the fitting table: their K depends on the area ratio. Supply '
        'them through extra_loss_coefficient if they matter.'),
    'flex_hose': (
        'Convoluted flex hose, braided hose and bellows are NOT in the '
        'roughness table: their effective friction factor is geometry '
        'specific. The pressure drop in a convoluted inner core is 10 to 15 '
        'times that of a comparable-diameter hard tube, and higher still in '
        'convoluted bends (NASA SP-8123, 1977, sec. 2.3.1, p. 85). Supply a '
        'measured roughness or an extra loss coefficient.'),
    'fluid_properties': (
        'Fluid properties are NOT computed here: density, viscosity, '
        'vapour pressure, critical pressure and bulk modulus are '
        'caller-supplied inputs. Temperature dependence, and any change '
        'of properties along the line, are the caller\'s responsibility.'),
    # ÖH KU (KC-11 / SP-F F14): regülatör toleransı beyanı. SP-8080 s. 11
    # yerel metinden doğrulandı; Tablo I tolerans bandı OCR bozuk, sayfa
    # doğrulanmadı (SP-F notunun okuması ±%3-6).
    'regulator_tolerance': (
        'Regulator tolerance is NOT modelled: an upstream (tank or '
        'regulated) pressure is taken as a single value, whereas a pressure '
        'regulator holds a band around its set point (NASA SP-8080, 1973, '
        'Table I; of order +/-3-6% per the SP-F reading, page not verified '
        'here). Supply-pressure and flow-demand error is held to about 25% '
        'of the total allowable regulated-pressure variation (SP-8080 p. '
        '11). Set the regulated pressure so that the LOWER edge of the '
        'regulator band still meets the requirement.'),
    'line_dynamics': (
        'Feed-system dynamics are NOT modelled: POGO coupling, line '
        'acoustics, flow-induced vibration and noise are outside this '
        'model.'),
}


# ===========================================================================
# Saf yardımcılar (analitik, tek tek test edilebilir)
# ===========================================================================
#: ÖH D23 / P5B4-16: TEK KAYNAK. Bu ad üç analiz modülünde birebir
#: kopyalanmıştı; tanım artık ``hrma/analysis/_input_guards.py``tadır ve
#: ``bool``u reddeder (ölçüm ve gerekçe o modülün docstring'inde).
_require_positive = require_positive


def relative_roughness(roughness_m: float, diameter_m: float) -> float:
    """Bağıl pürüzlülük eps/D [-]."""
    d = _require_positive(diameter_m, 'diameter_m', '[m]')
    eps = float(roughness_m)
    if not math.isfinite(eps) or eps < 0.0:
        raise ValueError('roughness_m must be non-negative and finite [m]')
    return eps / d


def crane_ft(diameter_m: float,
             roughness_m: float = CRANE_FT_ROUGHNESS_M) -> float:
    """Crane TP-410 tam-türbülans sürtünme faktörü f_T [-].

    f_T, Re -> sonsuz limitinde Haaland bağıntısının verdiği tam-pürüzlü
    değerdir; Crane bunu TİCARİ ÇELİK boru için boyuta göre tablolar, bu
    yüzden varsayılan pürüzlülük ticari çeliktir (borunun kendi malzemesi
    değil — Crane'in yöntemi bunu böyle tanımlar).

    Kaynak: Crane TP-410, Böl. 2 (f_T tablosu); Haaland (1983) / White
    7. baskı Eş. 6.49 tam-pürüzlü limiti. Bekçi testi bu türetimin
    Crane'in yayımlanmış f_T tablosunu yeniden ürettiğini sınar.
    """
    eps_d = relative_roughness(roughness_m, diameter_m)
    if eps_d <= 0.0:
        raise ValueError(
            'crane_ft needs a positive roughness: a perfectly smooth pipe '
            'has no fully-rough asymptote, so the Crane f_T method does '
            'not apply. Use the commercial-steel default.')
    # Re = 1e12 -> 6.9/Re terimi 1e-11 mertebesinde, tam-pürüzlü limit.
    return haaland_friction_factor(1.0e12, eps_d)


def fitting_loss_coefficient(fitting: str, diameter_m: float,
                             roughness_m: float = CRANE_FT_ROUGHNESS_M
                             ) -> float:
    """Tek bir bağlantı elemanının direnç katsayısı K [-].

    Eşdeğer uzunluk tablosundaki kalemler için K = f_T * (L/D)_eş
    (Crane TP-410); sabit-K tablosundaki kalemler doğrudan döner.
    """
    key = str(fitting).strip().lower()
    if key in FITTING_K:
        return float(FITTING_K[key])
    if key in FITTING_LD:
        return crane_ft(diameter_m, roughness_m) * float(FITTING_LD[key])
    raise ValueError(
        f"unknown fitting '{fitting}'; choose from "
        f'{sorted(set(FITTING_LD) | set(FITTING_K))} or pass the loss '
        'through extra_loss_coefficient')


def line_velocity(mass_flow_kg_s: float, density_kg_m3: float,
                  diameter_m: float) -> float:
    """Hat hızı V = mdot / (rho * A) [m/s]."""
    mdot = _require_positive(mass_flow_kg_s, 'mass_flow_kg_s', '[kg/s]')
    rho = _require_positive(density_kg_m3, 'density_kg_m3', '[kg/m^3]')
    d = _require_positive(diameter_m, 'diameter_m', '[m]')
    area = math.pi * d * d / 4.0
    return mdot / (rho * area)


def reynolds_number(density_kg_m3: float, velocity_m_s: float,
                    diameter_m: float, viscosity_Pa_s: float) -> float:
    """Re = rho * V * D / mu [-]."""
    rho = _require_positive(density_kg_m3, 'density_kg_m3', '[kg/m^3]')
    v = _require_positive(velocity_m_s, 'velocity_m_s', '[m/s]')
    d = _require_positive(diameter_m, 'diameter_m', '[m]')
    mu = _require_positive(viscosity_Pa_s, 'viscosity_Pa_s', '[Pa.s]')
    return rho * v * d / mu


def flow_regime(reynolds: float) -> str:
    """Akış rejimi etiketi: 'laminar' | 'transitional' | 'turbulent'."""
    re = float(reynolds)
    if re < RE_LAMINAR_MAX:
        return 'laminar'
    if re < RE_TURBULENT_MIN:
        return 'transitional'
    return 'turbulent'


# ===========================================================================
# Hat basınç bütçesi
# ===========================================================================
def line_pressure_drop(*,
                       mass_flow_kg_s: float,
                       density_kg_m3: float,
                       viscosity_Pa_s: float,
                       line_id_m: float,
                       line_length_m: float,
                       pipe_material: str = 'stainless_tubing',
                       roughness_m: Optional[float] = None,
                       roughness_provenance: Optional[str] = None,
                       fittings: Optional[Dict[str, float]] = None,
                       extra_loss_coefficient: float = 0.0,
                       elevation_gain_m: float = 0.0,
                       inlet_pressure_Pa: Optional[float] = None,
                       vapor_pressure_Pa: Optional[float] = None) -> Dict:
    """Besleme hattı kararlı rejim basınç düşümü bütçesi.

    Args:
        mass_flow_kg_s: Kütle debisi [kg/s].
        density_kg_m3, viscosity_Pa_s: Sıvı özellikleri (GİRDİ).
        line_id_m: Boru iç çapı [m].
        line_length_m: Düz boru uzunluğu [m] (bağlantı elemanları ayrıca).
        pipe_material: ``PIPE_ROUGHNESS_M`` anahtarı.
        roughness_m: Mutlak pürüzlülük [m]; verilirse malzemeyi ezer.
        roughness_provenance: ``roughness_m``in KÖKENİ —
            ``ROUGHNESS_PROVENANCE`` anahtarı (``'measured'`` |
            ``'handbook_table'`` | ``'assumed'``). Verilmezse künye
            kökenin beyan EDİLMEDİĞİNİ söyler; "ölçüldü" hükmü uydurulmaz.
        fittings: ``{'elbow_90_long_radius': 4, 'ball_valve_full_bore': 1}``
            biçiminde eleman -> adet sözlüğü.
        extra_loss_coefficient: Tabloda olmayan kalemler için toplam ek K.
        elevation_gain_m: Çıkışın girişe göre kot FARKI [m] (pozitif =
            yukarı akış = basınç kaybı).
        inlet_pressure_Pa: Verilirse çıkış basıncı hesaplanır.
        vapor_pressure_Pa: Verilirse hat içi kavitasyon kontrolü yapılır.

    Returns:
        JSON-güvenli sözlük; her blok ``_basis`` künyeli, aralık dışı
        durumlar ``validity`` listesinde açık beyanla.
    """
    rho = _require_positive(density_kg_m3, 'density_kg_m3', '[kg/m^3]')
    mu = _require_positive(viscosity_Pa_s, 'viscosity_Pa_s', '[Pa.s]')
    d = _require_positive(line_id_m, 'line_id_m', '[m]')
    length = _require_positive(line_length_m, 'line_length_m', '[m]')
    k_extra = float(extra_loss_coefficient)
    if not math.isfinite(k_extra) or k_extra < 0.0:
        raise ValueError('extra_loss_coefficient must be non-negative')
    dz = float(elevation_gain_m)
    if not math.isfinite(dz):
        raise ValueError('elevation_gain_m must be finite [m]')
    # ------------------------------------------------------------------
    # ÖH D20 / P5B3-15 — KOT FARKI HATTIN GEOMETRİSİNE BAĞLIDIR.
    #
    # ÖLÇÜLDÜ (taban 14acd1d, ``once.json`` P5B3-15; 25 m hat, D 20 mm,
    # mdot 2 kg/s, su, giriş 30 bar): ``elevation_gain_m = -1e9`` ->
    # ``dp_static = -9,80665e+12 Pa``, ``dp_total = -9,806650e+12 Pa``,
    # çıkış basıncı ``+9,806653e+12 Pa`` (98 milyon bar) ve uyarı sayısı
    # SIFIR. ``+1e9`` -> ``dp_total = +9,806650e+12 Pa``.
    #
    # Bant UYDURULMAZ: L uzunluğundaki bir borunun iki ucu arasındaki
    # DÜŞEY fark, borunun kendi uzunluğunu aşamaz (|dz| <= L; eşitlik boru
    # tam düşeyken). Bu bir kalibrasyon değil GEOMETRİ kısıtıdır ve
    # ``line_length_m`` zaten zorunlu pozitif bir argümandır.
    # ------------------------------------------------------------------
    if abs(dz) > length:
        raise ValueError(
            f'elevation_gain_m {dz:.6g} m exceeds the line length '
            f'{length:.6g} m: a pipe of length L cannot span more than L '
            'vertically (|dz| <= L, equality when the run is vertical). '
            'No pressure budget was produced - the static head would not '
            'describe this line.')

    validity: List[Dict] = []
    warnings: List[str] = []

    # --- pürüzlülük ---
    # ÖH D18 / P5B3-10 — KÜNYE YALAN SÖYLÜYORDU. ``roughness_m`` verildiğinde
    # bu modül künyeye koşulsuz "user-supplied MEASURED absolute roughness"
    # yazıyordu. ÖLÇÜLDÜ (taban 9071a64, ``once_valve.json`` B): sıvı motorun
    # altı besleme hattının hepsinde çağıran, ölçüm değil bir EL KİTABI
    # SABİTİ geçiriyor (``liquid_rocket_engine.FEED_LINE_ROUGHNESS_M =
    # 4,5e-05 m``, ticari çelik, White Tablo 6.1) ve aynı JSON'da motorun
    # kendi ``roughness_basis`` künyesi bunu doğru söylüyordu: aynı sayı için
    # iki çelişik künye.
    #
    # Bu modül sayının nereden geldiğini BİLEMEZ. Kazanılmamış bir "ölçüldü"
    # hükmü yayımlanmaz: köken ancak çağıran ADIYLA beyan ederse yazılır,
    # beyan yoksa künye bilinmediğini söyler.
    if roughness_m is not None:
        eps = float(roughness_m)
        if not math.isfinite(eps) or eps < 0.0:
            raise ValueError('roughness_m must be non-negative and finite')
        prov_key = (None if roughness_provenance is None
                    else str(roughness_provenance).strip().lower())
        if prov_key is not None and prov_key not in ROUGHNESS_PROVENANCE:
            raise ValueError(
                f"unknown roughness_provenance '{roughness_provenance}'; "
                f'choose from {sorted(ROUGHNESS_PROVENANCE)}')
        roughness_source = (ROUGHNESS_PROVENANCE_UNDECLARED
                            if prov_key is None
                            else ROUGHNESS_PROVENANCE[prov_key])
    else:
        prov_key = 'handbook_table'
        key = str(pipe_material).strip().lower()
        if key not in PIPE_ROUGHNESS_M:
            raise ValueError(
                f"unknown pipe_material '{pipe_material}'; choose from "
                f'{sorted(PIPE_ROUGHNESS_M)} or pass roughness_m')
        eps = float(PIPE_ROUGHNESS_M[key])
        roughness_source = f'PIPE_ROUGHNESS_M table entry "{key}"'
    eps_d = eps / d
    if eps_d > REL_ROUGHNESS_VALID[1]:
        validity.append({
            'field': 'relative_roughness',
            'status': 'out_of_validity',
            'message': (
                f'relative roughness {eps_d:.4f} exceeds the Colebrook/'
                f'Haaland validity limit {REL_ROUGHNESS_VALID[1]:.2f}; the '
                'friction factor is outside its supported range (invalid '
                'range declared - no silent extrapolation).')})

    # --- hız, Reynolds, rejim ---
    v = line_velocity(mass_flow_kg_s, rho, d)
    re = reynolds_number(rho, v, d, mu)
    regime = flow_regime(re)
    if regime == 'transitional':
        validity.append({
            'field': 'friction_factor',
            'status': 'out_of_validity',
            'message': (
                f'Reynolds number {re:.0f} falls in the transitional band '
                f'({RE_LAMINAR_MAX:.0f}-{RE_TURBULENT_MIN:.0f}) where '
                'neither the laminar f = 64/Re law nor the Haaland '
                'turbulent correlation is valid; the friction pressure '
                'drop below is an interpolation of unknown accuracy '
                '(invalid range declared - no silent extrapolation).')})

    # --- sürtünme kaybı (Darcy-Weisbach, tek kaynak: regen_cooling) ---
    f_darcy = haaland_friction_factor(re, eps_d)
    dp_friction = darcy_weisbach_dp(f_darcy, length, d, rho, v)

    # --- yerel kayıplar (Crane TP-410) ---
    # ÖH D23 / P5B3-19 — ÖLÜ DAL KALDIRILDI.
    # Eski satır ``crane_ft(d) if eps > 0.0 else crane_ft(d,
    # CRANE_FT_ROUGHNESS_M)`` idi; ``crane_ft``in VARSAYILAN pürüzlülüğü
    # zaten ``CRANE_FT_ROUGHNESS_M`` olduğu için iki kol BİREBİR aynı
    # çağrıydı. ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` P5B3-19,
    # D = 0,02 m): her iki kol da 0,02436428212205431 — özdeş. Koşul,
    # okuyucuya "pürüzsüz boruda başka bir şey yapılıyor" izlenimi
    # veriyordu; Crane'in f_T yöntemi TANIM GEREĞİ ticari çelik
    # pürüzlülüğünü kullanır (borunun kendi ``eps``ini DEĞİL), bu yüzden
    # tek çağrı doğrudur ve künye bunu zaten söylüyor.
    f_t = crane_ft(d, CRANE_FT_ROUGHNESS_M)
    dyn_head = 0.5 * rho * v * v
    fitting_rows: List[Dict] = []
    k_total = 0.0
    for name, count in sorted((fittings or {}).items()):
        n = float(count)
        if not math.isfinite(n) or n < 0.0:
            raise ValueError(
                f"fitting count for '{name}' must be non-negative")
        if n == 0.0:
            continue
        k_one = fitting_loss_coefficient(name, d)
        k_sum = k_one * n
        k_total += k_sum
        fitting_rows.append({
            'fitting': str(name),
            'count': n,
            'k_each': float(k_one),
            'k_total': float(k_sum),
            'dp_Pa': float(k_sum * dyn_head),
            'method': ('K = f_T*(L/D)_eq' if str(name).strip().lower()
                       in FITTING_LD else 'fixed K'),
        })
    k_total += k_extra
    if k_extra > 0.0:
        fitting_rows.append({
            'fitting': 'extra_loss_coefficient',
            'count': 1.0,
            'k_each': float(k_extra),
            'k_total': float(k_extra),
            'dp_Pa': float(k_extra * dyn_head),
            'method': 'user-supplied K',
        })
    dp_minor = k_total * dyn_head

    # ------------------------------------------------------------------
    # ÖH D20 / P5B3-14 — CRANE (L/D)_eş YÖNTEMİ TAM TÜRBÜLANS İSTER.
    #
    # ``crane_ft`` f_T'yi Re -> sonsuz (tam-pürüzlü) limitten üretir, yani
    # Reynolds sayısına KÖRDÜR; K = f_T*(L/D)_eş de öyle. Crane TP-410 bu
    # yöntemi açıkça tam gelişmiş TÜRBÜLANS için tanımlar (Böl. 2 ve Ek A;
    # yukarıdaki ``FITTING_LD_SOURCE`` künyesi de "assumes fully-developed
    # turbulent flow" der). Laminer ve geçiş rejiminde yerel kayıp Re ile
    # BÜYÜR (Hooper 2-K / Darby 3-K yöntemlerinde K = K1/Re + ...), yani
    # f_T tabanlı K bir ALT SINIRDIR.
    #
    # ÖLÇÜLDÜ (taban 14acd1d, ``once.json`` P5B3-14; aynı hat, viskozite
    # süpürmesi): Re 12,73 / 127,32 / 1273,24 / 6366,20 / 127 323,95'in
    # HEPSİNDE ``crane_ft = 0,024364282122``, ``k_total = 2,923713855`` ve
    # ``dp_minor = 59 246,829677 Pa`` — BİT-AYNI; ``validity`` listesi
    # laminer kayıtlarda BOŞ, ``warnings`` sayısı 0. Yani modülün kendi
    # "sessiz ekstrapolasyon yasak" politikası (sürtünme faktörü için
    # geçiş bandında uygulanıyor) yerel kayıplarda uygulanmıyordu.
    #
    # SAYI DÜZELTİLMEZ, UYDURULMAZ: laminer yerel-kayıp korelasyonu bu
    # depoda yoktur ve her bağlantı elemanı için yeni K1 katsayıları
    # yazmak bir VERİ kararıdır. Yapılan, yöntemin kendi geçerlilik
    # zarfının ADIYLA beyan edilmesi ve değerin ALT SINIR olduğunun
    # söylenmesidir — sürtünme faktöründeki kardeş kayıtla aynı biçimde.
    # ------------------------------------------------------------------
    _crane_kalemleri = [s['fitting'] for s in fitting_rows
                        if s.get('method') == 'K = f_T*(L/D)_eq']
    if _crane_kalemleri and re < RE_TURBULENT_MIN:
        validity.append({
            'field': 'minor_losses',
            'status': 'out_of_validity',
            'message': (
                f'Reynolds number {re:.0f} is below the fully-turbulent '
                f'threshold {RE_TURBULENT_MIN:.0f}, but the resistance of '
                f'{sorted(_crane_kalemleri)} was taken from the Crane '
                'equivalent-length method K = f_T*(L/D)_eq, whose f_T is '
                'the Re -> infinity fully-rough limit and therefore does '
                'not vary with Reynolds number. Crane TP-410 defines that '
                'method for fully-developed turbulent flow; in the '
                'laminar and transitional regimes the real loss '
                'coefficient GROWS as Re falls (see the Hooper 2-K / '
                'Darby 3-K forms), so the minor-loss pressure drop below '
                'is a LOWER BOUND, not an estimate (invalid range '
                'declared - no silent extrapolation).')})
        warnings.append(
            f'minor losses were computed with the Crane equivalent-length '
            f'method at Re = {re:.0f}, below its fully-turbulent validity '
            f'threshold {RE_TURBULENT_MIN:.0f}: the reported dP_minor '
            f'({dp_minor:.0f} Pa) is a lower bound.')

    # --- kot farkı ---
    dp_static = rho * G_0 * dz

    dp_total = dp_friction + dp_minor + dp_static

    # ------------------------------------------------------------------
    # ÖH D23 / P5B3-17 — NET BASINÇ KAZANCI SESSİZ KALAMAZ.
    #
    # Aşağı doğru inen bir hatta (``dz < 0``) statik yük bir KAZANÇtır;
    # yeterince büyükse sürtünme + yerel kayıpları yener ve ``dp_total``
    # NEGATİF olur. Bütçe aritmetik olarak doğrudur, ama ürün bunu
    # "düşüm" (``dp_Pa``, ``dp_bar``) adıyla yayımlıyor,
    # ``friction_fraction``ı GEREKÇESİZ ``None`` yapıyor ve TEK BİR uyarı
    # bile üretmiyordu.
    #
    # ÖLÇÜLDÜ (taban ``ef527ae``, ``once.json`` P5B3-17; mdot 2 kg/s,
    # rho 1000, D 0,05 m, L 3 m, 2x 90° dirsek, giriş 30 bar):
    #   dz = -2 m -> dp_total = -18 568,774145 Pa
    #                friction_fraction = None
    #                outlet = 3 018 568,774145 Pa (girişten
    #                         +18 568,774145 Pa YÜKSEK)
    #                warnings = 0, validity = []
    #   dz =  0 m -> dp_total = +1 044,525855 Pa, fraction = 0,616954
    #   dz = +2 m -> dp_total = +20 657,825855 Pa, fraction = 0,031195
    # Yani "teslim basıncı girişten yüksek" hükmü sıfır uyarıyla
    # yayımlanıyordu.
    #
    # Sayı DEĞİŞMEZ (fizik doğru: siphon/aşağı akış gerçekten kazanç
    # verir); değişen, hükmün ADIYLA söylenmesidir. ``friction_fraction``
    # negatif/sıfır toplamda TANIMSIZDIR (payda işaret değiştirir), bu
    # yüzden geri çekilir ve geri çekme GEREKÇESİ yayımlanır.
    # ------------------------------------------------------------------
    _friction_fraction_withheld = None
    if dp_total < 0.0:
        _friction_fraction_withheld = (
            'undefined: the net budget is a pressure GAIN '
            f'({-dp_total:.6g} Pa), so there is no total loss for the '
            'friction term to be a fraction of.')
        warnings.append(
            f'Net pressure GAIN: the static head of a downhill run '
            f'(elevation_gain_m = {dz:g} m) exceeds friction plus minor '
            f'losses, so dP_total is negative ({dp_total:.6g} Pa) and the '
            'line outlet sits at a HIGHER pressure than its inlet. The '
            "fields named 'dp_Pa' / 'dp_bar' therefore carry a rise, not "
            'a drop; friction_fraction is withheld because it is '
            'undefined for a non-positive total.')
        validity.append({
            'field': 'elevation_gain_m',
            'status': 'net_pressure_gain',
            'message': (
                f'dP_friction + dP_minor = {dp_friction + dp_minor:.6g} Pa '
                f'is smaller than the static gain '
                f'{-dp_static:.6g} Pa, so the budget nets out to a rise. '
                'Check that the elevation sign convention (positive = '
                'outlet above inlet) matches the intended layout before '
                'using the delivery pressure.')})
    elif dp_total == 0.0:
        _friction_fraction_withheld = (
            'undefined: dP_total is exactly zero (friction and minor '
            'losses are cancelled by the static head), so the friction '
            'share has no denominator.')
        warnings.append(
            'The static head exactly cancels friction plus minor losses '
            '(dP_total = 0 Pa): the line delivers its inlet pressure and '
            'friction_fraction is withheld as undefined.')

    # --- çıkış basıncı ve hat içi kavitasyon ---
    outlet = None
    cavitation_line = None
    if inlet_pressure_Pa is not None:
        p_in = float(inlet_pressure_Pa)
        if not math.isfinite(p_in) or p_in <= 0.0:
            raise ValueError('inlet_pressure_Pa must be positive and finite')
        if vapor_pressure_Pa is not None:
            p_v_gate = float(vapor_pressure_Pa)
            if not math.isfinite(p_v_gate) or p_v_gate < 0.0:
                raise ValueError(
                    'vapor_pressure_Pa must be non-negative and finite')
            # ÖH D20 / P5B3-15: buhar basıncı hattın GİRİŞ basıncını
            # aşamaz. ÖLÇÜLDÜ (once.json): ``vapor_pressure_Pa = 100 bar``
            # (giriş 30 bar) ve ``1e12 Pa`` gövdeleri KABUL ediliyor,
            # bütün sayılar sağlıklı çağrıyla bit-aynı çıkıyordu. Böyle
            # bir hatta sıvı zaten girişte kaynıyordur; bu modülün modeli
            # (kararlı, sıkıştırılamaz, TEK FAZLI akış) uygulanamaz.
            if p_v_gate >= p_in:
                raise ValueError(
                    f'vapor_pressure_Pa {p_v_gate:.6g} Pa is at or above '
                    f'the line inlet pressure {p_in:.6g} Pa: the liquid '
                    'is already boiling where the line starts, so the '
                    'single-phase incompressible budget this function '
                    'computes does not describe it. No budget was '
                    'produced.')
        outlet = p_in - dp_total
        # ------------------------------------------------------------------
        # ÖH D20 / P5B3-15 — MUTLAK BASINÇ NEGATİF OLAMAZ (fail-closed).
        #
        # ÖLÇÜLDÜ (taban 14acd1d, ``once.json`` P5B3-15; 25 m hat):
        #   ``extra_loss_coefficient = 1e9`` -> dp_total 2,0264237e+13 Pa,
        #     yayımlanan ``outlet_pressure_Pa = -2,0264234e+13 Pa``
        #   ``elbow_90_long_radius: 1e6`` adet -> dp_total 9,8749108e+09 Pa,
        #     ``outlet_pressure_Pa = -9,8719108e+09 Pa``
        # Her ikisinde de TEK bir metin uyarısı vardı ama ``validity``
        # BOŞtu ve NEGATİF MUTLAK BASINÇ bir SAYI olarak yayımlanıyordu;
        # aşağıdaki kavitasyon hükmü de o sayıdan üretiliyordu
        # (``status: 'cavitating'``, ``margin_Pa`` negatif).
        #
        # K'ye ya da bağlantı sayısına TAVAN KONMAZ (kısmen kapalı bir
        # vananın K'si gerçekten çok büyük olabilir; yeni bir eşik icat
        # etmek kalibrasyon kararıdır). Kapı SONUCA konur: mutlak basınç
        # sıfırın altına inemez, dolayısıyla hüküm KAZANILMAMIŞTIR ve
        # yayımlanmaz — alan ``None`` olur, gerekçe ``validity``de adıyla
        # durur. Vana ayağı bu davranışı zaten uyguluyordu
        # (``p_valve_in > 0`` kapısı); hat ayağı hizalandı.
        # ------------------------------------------------------------------
        if outlet <= 0.0:
            warnings.append(
                f'the pressure budget consumes the whole inlet pressure: '
                f'outlet static pressure would be {outlet:.0f} Pa '
                '(non-physical). The line is undersized for this flow, or '
                'the inlet pressure is too low.')
            validity.append({
                'field': 'outlet_pressure_Pa',
                'status': 'not_evaluated',
                'message': (
                    f'the outlet static pressure was NOT published: the '
                    f'budget (dP_total = {dp_total:.6g} Pa) exceeds the '
                    f'inlet pressure ({p_in:.6g} Pa), which would put the '
                    'absolute pressure below zero. No number is published '
                    'for a state the fluid cannot reach; the line '
                    'cavitation verdict is withheld for the same reason.')})
            outlet = None
        if outlet is not None and vapor_pressure_Pa is not None:
            p_v = float(vapor_pressure_Pa)
            margin = outlet - p_v
            cavitation_line = {
                'outlet_static_pressure_Pa': float(outlet),
                'vapor_pressure_Pa': float(p_v),
                'margin_Pa': float(margin),
                'status': ('cavitating' if margin <= 0.0 else 'subcooled'),
                '_basis': (
                    'Line-side check only: the static pressure at the line '
                    'outlet is compared with the fluid vapour pressure. '
                    'This is NOT the valve cavitation check (see '
                    'size_valve) and it does not resolve local low-pressure '
                    'spots at bends, restrictions or the pump inlet.'),
            }
            if margin <= 0.0:
                warnings.append(
                    f'line outlet static pressure ({outlet:.0f} Pa) has '
                    f'fallen to or below the vapour pressure ({p_v:.0f} Pa): '
                    'the liquid boils inside the line.')

    return {
        'inputs': {
            'mass_flow_kg_s': float(mass_flow_kg_s),
            'density_kg_m3': rho,
            'viscosity_Pa_s': mu,
            'line_id_m': d,
            'line_length_m': length,
            'roughness_m': float(eps),
            'roughness_source': roughness_source,
            # ÖH D18 / P5B3-10: kökenin makine-okur hâli. ``None`` =
            # çağıran beyan etmedi (künye de bunu söyler).
            'roughness_provenance': prov_key,
            'elevation_gain_m': dz,
            'inlet_pressure_Pa': (None if inlet_pressure_Pa is None
                                  else float(inlet_pressure_Pa)),
        },
        'flow': {
            'velocity_m_s': float(v),
            'volumetric_flow_m3_s': float(mass_flow_kg_s) / rho,
            'reynolds': float(re),
            'regime': regime,
            'relative_roughness': float(eps_d),
            'dynamic_pressure_Pa': float(dyn_head),
            '_basis': (
                'V = mdot/(rho*A); Re = rho*V*D/mu; regime boundaries '
                f'laminar < {RE_LAMINAR_MAX:.0f}, turbulent > '
                f'{RE_TURBULENT_MIN:.0f} (White, "Fluid Mechanics", 7th '
                'ed., Ch. 6).'),
        },
        'friction': {
            'darcy_friction_factor': float(f_darcy),
            'dp_Pa': float(dp_friction),
            'length_over_diameter': float(length / d),
            '_basis': (
                'dP_f = f*(L/D)*rho*V^2/2 (Darcy-Weisbach; White 7th ed., '
                'Eq. 6.10). Friction factor from the Haaland (1983) '
                'explicit correlation, f = 64/Re when laminar - both '
                'imported from hrma.analysis.regen_cooling (single '
                'source, no copy). ' + PIPE_ROUGHNESS_SOURCE),
        },
        'minor_losses': {
            'crane_ft': float(f_t),
            'k_total': float(k_total),
            'dp_Pa': float(dp_minor),
            'items': fitting_rows,
            '_basis': (
                'dP_minor = (sum K)*rho*V^2/2 with K = f_T*(L/D)_eq for '
                'fittings and full-open valves. f_T is derived here as the '
                'fully-rough (Re -> inf) Haaland limit at commercial-steel '
                'roughness, which reproduces the published Crane f_T table '
                'to within about 4%. ' + FITTING_LD_SOURCE + ' '
                + FITTING_K_SOURCE),
        },
        'static_head': {
            'elevation_gain_m': dz,
            'dp_Pa': float(dp_static),
            '_basis': (
                'dP_static = rho*g*dz with g = g_0 (hrma.constants.G_0). '
                'Positive dz means the outlet sits above the inlet, so the '
                'static head is a pressure LOSS. Vehicle acceleration head '
                'is NOT included - pass it through elevation_gain_m scaled '
                'by a/g_0 if it matters.'),
        },
        'total': {
            'dp_Pa': float(dp_total),
            'dp_bar': float(dp_total / 1.0e5),
            'outlet_pressure_Pa': (None if outlet is None else float(outlet)),
            'friction_fraction': (float(dp_friction / dp_total)
                                  if dp_total > 0.0 else None),
            # ÖH D23 / P5B3-17: ``None`` artık gerekçesiyle birlikte.
            'friction_fraction_withheld': _friction_fraction_withheld,
            '_basis': (
                'dP_total = dP_friction + dP_minor + dP_static. Steady, '
                'incompressible, single-phase, isothermal, fully-developed '
                'flow with constant properties.'),
        },
        'line_cavitation': cavitation_line,
        'validity': validity,
        'warnings': warnings,
        'not_modelled': dict(NOT_MODELLED),
    }


# ===========================================================================
# Vana akış katsayısı ve kavitasyon
# ===========================================================================
def valve_cv_required(volumetric_flow_m3_s: float, pressure_drop_Pa: float,
                      density_kg_m3: float) -> float:
    """Gerekli Cv [US gpm / psi^0.5] — Eş. (4): Cv = Q*sqrt(SG/dP).

    ISA-75.01.01 / IEC 60534-2-1 türbülanslı, boğulmamış sıvı akışı.
    """
    q = _require_positive(volumetric_flow_m3_s, 'volumetric_flow_m3_s',
                          '[m^3/s]')
    dp = _require_positive(pressure_drop_Pa, 'pressure_drop_Pa', '[Pa]')
    rho = _require_positive(density_kg_m3, 'density_kg_m3', '[kg/m^3]')
    sg = rho / SG_REFERENCE_DENSITY_KG_M3
    return m3s_to_gpm(q) * math.sqrt(sg / pa_to_psi(dp))


def flow_from_cv(cv: float, pressure_drop_Pa: float,
                 density_kg_m3: float) -> float:
    """Verilen Cv ve dP'de hacimsel debi [m^3/s] — Eş. (3)'ün doğrudan hali.

    ``valve_cv_required`` ile tam tersidir; bekçi testi gidiş-dönüş
    tutarlılığını sınar.
    """
    c = _require_positive(cv, 'cv', '[gpm/psi^0.5]')
    dp = _require_positive(pressure_drop_Pa, 'pressure_drop_Pa', '[Pa]')
    rho = _require_positive(density_kg_m3, 'density_kg_m3', '[kg/m^3]')
    sg = rho / SG_REFERENCE_DENSITY_KG_M3
    q_gpm = c * math.sqrt(pa_to_psi(dp) / sg)
    # gpm -> m^3/s: m3s_to_gpm'in tersi (aynı kesin tanım).
    return q_gpm / m3s_to_gpm(1.0)


def cv_to_kv(cv: float) -> float:
    """Cv -> Kv [m^3/h / bar^0.5] (Kv = 0.865*Cv, IEC 60534-1)."""
    return _require_positive(cv, 'cv') * KV_PER_CV


def kv_to_cv(kv: float) -> float:
    """Kv -> Cv (Cv = Kv/0.865, IEC 60534-1)."""
    return _require_positive(kv, 'kv') / KV_PER_CV


def liquid_critical_pressure_ratio_factor(vapor_pressure_Pa: float,
                                          critical_pressure_Pa: float
                                          ) -> float:
    """Sıvı kritik basınç oranı faktörü F_F — Eş. (5).

    F_F = 0.96 - 0.28*sqrt(p_v/p_c)  (IEC 60534-2-1 / ISA-75.01.01).
    """
    p_v = float(vapor_pressure_Pa)
    p_c = _require_positive(critical_pressure_Pa, 'critical_pressure_Pa',
                            '[Pa]')
    if not math.isfinite(p_v) or p_v < 0.0:
        raise ValueError('vapor_pressure_Pa must be non-negative and finite')
    if p_v > p_c:
        raise ValueError(
            f'vapor pressure ({p_v:.0f} Pa) exceeds the critical pressure '
            f'({p_c:.0f} Pa): the fluid is not a subcritical liquid, so the '
            'IEC 60534 liquid sizing equations do not apply (invalid range '
            'declared - no silent extrapolation).')
    return 0.96 - 0.28 * math.sqrt(p_v / p_c)


def choked_pressure_drop(inlet_pressure_Pa: float, vapor_pressure_Pa: float,
                         critical_pressure_Pa: float,
                         pressure_recovery_factor: float) -> float:
    """Boğulma basınç düşümü dP_boğuk [Pa] — Eş. (6).

    dP_boğuk = F_L^2 * (p_1 - F_F*p_v)  (IEC 60534-2-1 / ISA-75.01.01).
    """
    p1 = _require_positive(inlet_pressure_Pa, 'inlet_pressure_Pa', '[Pa]')
    fl = float(pressure_recovery_factor)
    if not (VALVE_FL_VALID[0] <= fl <= VALVE_FL_VALID[1]):
        raise ValueError(
            f'pressure_recovery_factor {fl:g} is outside the supported '
            f'validity range {VALVE_FL_VALID} (invalid range declared - no '
            'silent extrapolation)')
    ff = liquid_critical_pressure_ratio_factor(vapor_pressure_Pa,
                                               critical_pressure_Pa)
    return fl * fl * (p1 - ff * float(vapor_pressure_Pa))


def cavitation_status(inlet_pressure_Pa: float, outlet_pressure_Pa: float,
                      vapor_pressure_Pa: float,
                      choked_dp_Pa: Optional[float] = None) -> Dict:
    """Kavitasyon/flashing durumu ve sigma indisi — Eş. (7).

    Durumlar (öncelik sırasıyla):
      ``flashing``          : p_2 <= p_v (kalıcı iki fazlı çıkış)
      ``choked_cavitating`` : dP >= dP_boğuk (boğulmuş, Cv bağıntısı geçersiz)
      ``cavitation_risk``   : sigma tarama bandının altında
      ``no_cavitation``     : tarama bandının üstünde
    """
    p1 = _require_positive(inlet_pressure_Pa, 'inlet_pressure_Pa', '[Pa]')
    p2 = float(outlet_pressure_Pa)
    p_v = float(vapor_pressure_Pa)
    if not math.isfinite(p2):
        raise ValueError('outlet_pressure_Pa must be finite [Pa]')
    if not math.isfinite(p_v) or p_v < 0.0:
        raise ValueError('vapor_pressure_Pa must be non-negative and finite')
    if p2 >= p1:
        raise ValueError(
            f'outlet pressure ({p2:.0f} Pa) must be below the inlet '
            f'pressure ({p1:.0f} Pa) for a valve pressure drop')

    dp = p1 - p2
    sigma = (p1 - p_v) / dp if dp > 0.0 else float('inf')
    if p2 <= p_v:
        status = 'flashing'
        message = (
            f'outlet pressure {p2:.0f} Pa is at or below the vapour '
            f'pressure {p_v:.0f} Pa: the liquid FLASHES across the valve '
            'and stays two-phase downstream. The liquid sizing equation '
            'does not apply to the downstream line.')
    elif choked_dp_Pa is not None and dp >= float(choked_dp_Pa):
        status = 'choked_cavitating'
        message = (
            f'pressure drop {dp:.0f} Pa reaches the choked limit '
            f'{float(choked_dp_Pa):.0f} Pa: the flow is choked and the '
            'valve is cavitating. Flow no longer rises with further '
            'pressure drop, and the sizing below uses the choked drop.')
    elif sigma < SIGMA_SCREENING['damage_below']:
        status = 'cavitation_risk'
        message = (
            f'cavitation index sigma = {sigma:.2f} is below the generic '
            f'damage-risk screening threshold '
            f'{SIGMA_SCREENING["damage_below"]:.1f}: cavitation damage is '
            'plausible. Screening only - the real limit is valve-specific '
            'test data (ISA RP75.23).')
    elif sigma < SIGMA_SCREENING['caution_below']:
        status = 'cavitation_risk'
        message = (
            f'cavitation index sigma = {sigma:.2f} is below the generic '
            f'caution screening threshold '
            f'{SIGMA_SCREENING["caution_below"]:.1f}: review the valve '
            'selection. Screening only - the real limit is valve-specific '
            'test data (ISA RP75.23).')
    else:
        status = 'no_cavitation'
        message = (
            f'cavitation index sigma = {sigma:.2f} sits above the generic '
            'screening band; no cavitation flagged. Screening only - a '
            'valve-specific sigma limit (ISA RP75.23) can still be '
            'violated.')

    return {
        'status': status,
        'message': message,
        'sigma': float(sigma),
        'pressure_drop_Pa': float(dp),
        'choked_pressure_drop_Pa': (None if choked_dp_Pa is None
                                    else float(choked_dp_Pa)),
        'screening_band': dict(SIGMA_SCREENING),
        '_basis': (
            'sigma = (p1 - p_v)/(p1 - p2); flashing when p2 <= p_v; choked '
            'when dP >= F_L^2*(p1 - F_F*p_v) (IEC 60534-2-1 / '
            'ISA-75.01.01). ' + SIGMA_SOURCE),
    }


def size_valve(*,
               mass_flow_kg_s: float,
               density_kg_m3: float,
               inlet_pressure_Pa: float,
               pressure_drop_Pa: float,
               vapor_pressure_Pa: Optional[float] = None,
               critical_pressure_Pa: Optional[float] = None,
               valve_style: str = 'ball_full_bore',
               pressure_recovery_factor: Optional[float] = None) -> Dict:
    """Vana Cv/Kv boyutlandırma + kavitasyon/flashing kontrolü.

    Kavitasyon/flashing TARAMASI için ``vapor_pressure_Pa`` yeterlidir
    (sigma indisi ve p2 <= p_v ölçütü yalnız onu ister). ``critical_
    pressure_Pa`` YALNIZ boğulma sınırının F_F katsayısına girer: verilmezse
    tarama yine koşar ama boğulma sınırı hesaplanmaz, rejim hükmü
    ``capacity.regime_verified = False`` ile geri çekilir ve ``cv_required``
    bir ALT SINIR olarak beyan edilir (ÖH D18 / P5B3-08, P5B3-09).

    Hiçbir eksik girdide sessiz 'güvenli' hükmü verilmez; eksik olan alan
    ``validity`` listesinde ADIYLA söylenir.
    """
    rho = _require_positive(density_kg_m3, 'density_kg_m3', '[kg/m^3]')
    mdot = _require_positive(mass_flow_kg_s, 'mass_flow_kg_s', '[kg/s]')
    p1 = _require_positive(inlet_pressure_Pa, 'inlet_pressure_Pa', '[Pa]')
    dp = _require_positive(pressure_drop_Pa, 'pressure_drop_Pa', '[Pa]')
    if dp >= p1:
        raise ValueError(
            f'valve pressure drop ({dp:.0f} Pa) must stay below the inlet '
            f'pressure ({p1:.0f} Pa)')

    validity: List[Dict] = []
    warnings: List[str] = []

    # --- F_L ---
    if pressure_recovery_factor is not None:
        fl = float(pressure_recovery_factor)
        fl_source = 'user-supplied F_L (use the certified valve value)'
    else:
        key = str(valve_style).strip().lower()
        if key not in VALVE_PRESSURE_RECOVERY:
            raise ValueError(
                f"unknown valve_style '{valve_style}'; choose from "
                f'{sorted(VALVE_PRESSURE_RECOVERY)} or pass '
                'pressure_recovery_factor')
        fl = float(VALVE_PRESSURE_RECOVERY[key])
        fl_source = f'representative F_L for valve style "{key}"'
    if not (VALVE_FL_VALID[0] <= fl <= VALVE_FL_VALID[1]):
        raise ValueError(
            f'pressure_recovery_factor {fl:g} is outside the supported '
            f'validity range {VALVE_FL_VALID} (invalid range declared - no '
            'silent extrapolation)')

    q = mdot / rho
    p2 = p1 - dp

    # --- kavitasyon/boğulma ---
    #
    # ÖH D18 / P5B3-09 — TARAMA GEREKSİZ YERE ``critical_pressure_Pa``a
    # BAĞLIYDI. Sigma indisi sigma = (p1 - p_v)/(p1 - p2) ve flashing ölçütü
    # p2 <= p_v YALNIZ buhar basıncını ister; kritik basınç SADECE boğulma
    # sınırının F_F katsayısına girer. Eski ``VE`` koşulu yüzünden p_c
    # verilmeyen her çağrıda tarama HİÇ koşmuyordu. ÖLÇÜLDÜ (taban 9071a64,
    # ``once_valve.json`` A) — LOX ana vanası p1 = 60 bar, aynı gövde:
    #
    #   ==========  ==================  =========================
    #   vana dP     p_v + p_c verildi   YALNIZ p_v verildi (eski)
    #   ==========  ==================  =========================
    #   30 bar      choked_cavitating   None, 0 uyarı  (sigma 1,966)
    #   50 bar      choked_cavitating   None, 0 uyarı  (sigma 1,180)
    #   ==========  ==================  =========================
    #
    # Sıvı motorun altı besleme hattı çözücüye p_v geçirir ama p_c geçirmez,
    # yani ürün yüzünde tarama hiç koşmuyordu.
    #
    # ÖH D18 / P5B3-08 — ``sizing_note`` KAZANILMAMIŞ REJİM BEYAN EDİYORDU.
    # Not koşulsuz "non-choked turbulent liquid flow" yazıyordu; oysa p_c
    # yokken boğulma sınırı HESAPLANAMAZ, dolayısıyla akışın boğulmuş olup
    # olmadığı BİLİNMEZ. Aynı ölçümde Cv 28,469 ⟷ 36,888 (dP 30 bar, %22,8
    # eksik) ve 22,052 ⟷ 36,888 (dP 50 bar, %40,2 eksik) çıkıyordu. Rejim
    # hükmü artık ancak KAZANILDIĞINDA yazılır; kazanılmadıysa Cv'nin ALT
    # SINIR olduğu adıyla söylenir.
    cav = None
    dp_choked = None
    dp_sizing = dp
    regime_verified = False
    sizing_note = ('non-choked turbulent liquid flow: the full valve '
                   'pressure drop is used in the sizing equation.')
    if vapor_pressure_Pa is not None:
        if critical_pressure_Pa is not None:
            dp_choked = choked_pressure_drop(p1, vapor_pressure_Pa,
                                             critical_pressure_Pa, fl)
            regime_verified = True
        else:
            validity.append({
                'field': 'choked_pressure_drop',
                'status': 'not_evaluated',
                'message': (
                    'the choked pressure drop dP = F_L^2*(p1 - F_F*p_v) was '
                    'NOT computed because critical_pressure_Pa was not '
                    'supplied (the liquid critical pressure ratio factor F_F '
                    'needs it). Cavitation and flashing WERE screened from '
                    'the vapour pressure alone; only the choked limit is '
                    'missing.')})
        cav = cavitation_status(p1, p2, vapor_pressure_Pa, dp_choked)
        if cav['status'] in ('choked_cavitating', 'flashing'):
            warnings.append(cav['message'])
            if dp_choked is not None:
                dp_sizing = min(dp, dp_choked)
                sizing_note = (
                    'choked/flashing service: the sizing equation is '
                    'evaluated at the choked pressure drop dP = F_L^2*(p1 - '
                    'F_F*p_v), because flow stops rising beyond it '
                    '(IEC 60534-2-1).')
            else:
                sizing_note = (
                    'flashing service was detected from the vapour pressure, '
                    'but the sizing equation could NOT be moved to the '
                    'choked pressure drop because critical_pressure_Pa was '
                    'not supplied. The Cv below is evaluated at the FULL '
                    'valve pressure drop and is therefore a LOWER BOUND on '
                    'the required capacity, not a verified non-choked '
                    'sizing.')
                warnings.append(sizing_note)
        elif cav['status'] == 'cavitation_risk':
            warnings.append(cav['message'])
        if not regime_verified and cav['status'] not in ('flashing',):
            sizing_note = (
                'the flow regime was NOT verified: without '
                'critical_pressure_Pa the choked limit dP = F_L^2*(p1 - '
                'F_F*p_v) cannot be evaluated, so this sizing is not known '
                'to be non-choked. The Cv below uses the full valve pressure '
                'drop and is a LOWER BOUND on the required capacity if the '
                'valve turns out to be choked.')
    else:
        validity.append({
            'field': 'cavitation',
            'status': 'not_evaluated',
            'message': (
                'cavitation and flashing were NOT evaluated because '
                'vapor_pressure_Pa was not supplied. No safe/unsafe '
                'verdict is implied - supply the fluid properties to get '
                'one.')})
        sizing_note = (
            'the flow regime was NOT verified: without vapor_pressure_Pa '
            'neither the cavitation index nor the choked limit can be '
            'evaluated, so this sizing is not known to be non-choked. The Cv '
            'below uses the full valve pressure drop and is a LOWER BOUND on '
            'the required capacity if the valve turns out to be choked.')

    cv = valve_cv_required(q, dp_sizing, rho)
    kv = cv_to_kv(cv)

    # Aynı Cv'nin tam açıklıkta oluşturduğu eşdeğer direnç katsayısı,
    # hat bütçesine geri beslenebilsin diye rapor edilir.
    return {
        'inputs': {
            'mass_flow_kg_s': mdot,
            'density_kg_m3': rho,
            'volumetric_flow_m3_s': float(q),
            'inlet_pressure_Pa': p1,
            'outlet_pressure_Pa': float(p2),
            'pressure_drop_Pa': dp,
            'valve_style': str(valve_style),
        },
        'capacity': {
            'cv_required': float(cv),
            'kv_required': float(kv),
            'sizing_pressure_drop_Pa': float(dp_sizing),
            'specific_gravity': float(rho / SG_REFERENCE_DENSITY_KG_M3),
            'sizing_note': sizing_note,
            # ÖH D18 / P5B3-08: rejim hükmü KAZANILDI mı? ``False`` iken
            # ``cv_required`` bir ALT SINIRDIR, doğrulanmış bir boyut değil.
            'regime_verified': bool(regime_verified),
            '_basis': (
                'Cv = Q[gpm]*sqrt(SG/dP[psi]); Kv = 0.865*Cv '
                '(ISA-75.01.01-2012 / IEC 60534-2-1 turbulent '
                'non-choked liquid sizing equation). ' + SG_REFERENCE_SOURCE
                + ' ' + KV_CV_SOURCE + ' The result is a REQUIRED CAPACITY: '
                'select a valve whose rated Cv at the intended travel '
                'exceeds it, with the usual margin. Valve travel, the '
                'installed characteristic and Reynolds-number correction '
                'F_R for viscous service are NOT applied (see '
                'not_modelled.valve_internals).'),
        },
        'pressure_recovery': {
            'factor_FL': float(fl),
            'source': fl_source,
            '_basis': VALVE_FL_SOURCE,
        },
        'cavitation': cav,
        'choked_pressure_drop_Pa': (None if dp_choked is None
                                    else float(dp_choked)),
        'validity': validity,
        'warnings': warnings,
        'not_modelled': dict(NOT_MODELLED),
    }


# ===========================================================================
# Su koçu bağlantısı (water_hammer modülünün girdisi)
# ===========================================================================
def minimum_closure_time_s(*,
                           density_kg_m3: float,
                           line_length_m: float,
                           delta_velocity_m_s: float,
                           allowable_pressure_rise_Pa: float) -> float:
    """İzin verilen surge için en kısa kapanma süresi [s] — Eş. (8).

    t_min = 2*rho*L*dv / dP_izin (Michaud yavaş kapanma bağıntısının
    tersi; Wylie & Streeter, "Fluid Transients", Böl. 1). Sonuç kritik
    süre t_c = 2L/a'dan KISA çıkarsa yavaş kapanma rejimine hiç
    girilmiyor demektir; çağıran bunu ayrıca kontrol etmelidir
    (``water_hammer_inputs`` kontrol eder).
    """
    rho = _require_positive(density_kg_m3, 'density_kg_m3', '[kg/m^3]')
    length = _require_positive(line_length_m, 'line_length_m', '[m]')
    dv = _require_positive(delta_velocity_m_s, 'delta_velocity_m_s', '[m/s]')
    dp_allow = _require_positive(allowable_pressure_rise_Pa,
                                 'allowable_pressure_rise_Pa', '[Pa]')
    return 2.0 * rho * length * dv / dp_allow


def water_hammer_inputs(*,
                        fluid: str,
                        mass_flow_kg_s: float,
                        density_kg_m3: float,
                        line_id_m: float,
                        wall_thickness_m: float,
                        line_length_m: float,
                        working_pressure_Pa: float,
                        bulk_modulus_Pa: Optional[float] = None,
                        pipe_youngs_modulus_Pa: Optional[float] = None,
                        valve_closure_time_s: Optional[float] = None,
                        allowable_pressure_rise_Pa: Optional[float] = None,
                        vapor_pressure_Pa: Optional[float] = None,
                        pipe_material: Optional[str] = None) -> Dict:
    """``WaterHammerAnalyzer.analyze`` için hazır girdi + kapanma süresi önerisi.

    Bu fonksiyon su koçu FİZİĞİNİ ÇÖZMEZ; hattan gelen hızı ve geometriyi
    su koçu çözücüsünün beklediği anahtarlara ve birimlere çevirir, ayrıca
    izin verilen surge'den en kısa güvenli kapanma süresini türetir.
    Dönen ``analyzer_kwargs`` sözlüğü doğrudan ``analyze(**kwargs)``
    çağrısına verilebilir.

    Dalga hızı ve kritik süre — verilebiliyorsa — ``water_hammer``
    modülünün KENDİ fonksiyonlarıyla hesaplanır (kopya yok). Boru Young
    modülü verilmezse dalga hızı hesaplanmaz ve bu açıkça beyan edilir;
    uydurma bir değer konmaz.
    """
    if fluid is None or not str(fluid).strip():
        # Akışkan etiketi UYDURULMAZ (ÖH Z5S / defter P4B4-07): eskiden
        # çağıranlar etiketi veremediğinde sessizce 'water' konuyordu.
        raise ValueError(
            'fluid is required: the water-hammer coupling needs a named fluid '
            'whose bulk modulus is tabulated. No default label is substituted '
            "- pass the propellant's own key, or skip the coupling.")
    rho = _require_positive(density_kg_m3, 'density_kg_m3', '[kg/m^3]')
    d = _require_positive(line_id_m, 'line_id_m', '[m]')
    t_wall = _require_positive(wall_thickness_m, 'wall_thickness_m', '[m]')
    length = _require_positive(line_length_m, 'line_length_m', '[m]')
    p_work = _require_positive(working_pressure_Pa, 'working_pressure_Pa',
                               '[Pa]')

    v = line_velocity(mass_flow_kg_s, rho, d)

    notes: List[str] = []
    a = None
    a_rigid = None
    t_critical_s = None
    if bulk_modulus_Pa is not None and pipe_youngs_modulus_Pa is not None:
        # water_hammer.wave_speed (a_elastik, a_rijit) döndürür; su koçu
        # zamanlaması ESNEK borudaki hızla belirlenir.
        a, a_rigid = wave_speed(float(bulk_modulus_Pa), rho, d, t_wall,
                                float(pipe_youngs_modulus_Pa))
        t_critical_s = critical_closure_time(length, a)
    else:
        notes.append(
            'Wave speed and critical closure time were NOT computed: they '
            'need both bulk_modulus_Pa and pipe_youngs_modulus_Pa. The '
            'water_hammer solver resolves them from its own fluid and '
            'material tables when you call it with the kwargs below.')

    closure = None
    if allowable_pressure_rise_Pa is not None:
        t_min = minimum_closure_time_s(
            density_kg_m3=rho, line_length_m=length,
            delta_velocity_m_s=v,
            allowable_pressure_rise_Pa=float(allowable_pressure_rise_Pa))
        closure = {
            'minimum_closure_time_s': float(t_min),
            'allowable_pressure_rise_Pa': float(allowable_pressure_rise_Pa),
            'critical_closure_time_s': (None if t_critical_s is None
                                        else float(t_critical_s)),
            '_basis': (
                't_min = 2*rho*L*dv/dP_allow, the Michaud slow-closure '
                'relation inverted for the closure time that keeps the '
                'surge under the allowance (Wylie & Streeter, "Fluid '
                'Transients", 1978, Ch. 1). Valid only while t_min > '
                't_c = 2L/a; below t_c the closure is effectively '
                'instantaneous and the full Joukowsky rise dP = rho*a*dv '
                'applies no matter how the valve is scheduled.'),
        }
        # ------------------------------------------------------------------
        # ÖH D15 / P5B3-03 — HÜKÜM TERSİNE ÇEVRİLMİŞTİ.
        #
        # Cebir: t_min = 2*rho*L*dv/dP_izin ve t_c = 2L/a olduğundan
        #     t_min <= t_c  <=>  rho*a*dv <= dP_izin  <=>  dP_Joukowsky <= dP_izin
        # yani ``t_min <= t_c`` dalı tam olarak Joukowsky yükselişinin payın
        # ALTINDA kaldığı, dolayısıyla HİÇBİR kapanma kısıtının gerekmediği
        # durumdur. Eski kod bu dalda "unreachable_by_scheduling" basıyor ve
        # kullanıcıya gerekmeyen donanımı (surge akümülatörü) eklemesini,
        # hattı kısaltmasını ya da hızı düşürmesini söylüyordu.
        #
        # ÖLÇÜLDÜ — ÖH D17 / P5B3-03 (Fable-D15 ŞARTI ile DÜZELTİLDİ).
        #
        # Bu tablonun D15'te yazılan hâli KOŞMAMIŞ bir ölçümden geliyordu:
        # a2/olcum.py çağrısı ``working_pressure_Pa`` diye var olmayan bir
        # parametre veriyordu, bütün kayıtlar TypeError'dı ve tabloya
        # yazılan a = 840,5 m/s / t_c = 14,277 ms / J = 171,22 bar sayıları
        # bu koddan ÜRETİLEMİYORDU. Aşağıdaki sayılar aynı hattın GERÇEK
        # ölçümüdür (LOX hattı rho 1141, L 6 m, D 50 mm, t 2 mm,
        # mdot 40 kg/s, giriş 60 bar, vana dP 3 bar, mu 1,9e-4):
        #   v = 17,854367 m/s, a = 1224,9584 m/s, t_c = 2L/a = 9,7963 ms,
        #   Joukowsky dP = rho*a*v = 249,5465 bar.
        #
        # "eski hüküm" sütunu, aşağıdaki dalların D15 ÖNCESİ (ters) hâlinin
        # ters-mutasyonla yeniden koşulmasıyla alınmıştır
        # (docs/scofield/raw/OH/D17/yapisal-sistem/a1/mutasyon.json,
        #  'P5B3-03/eski-hukum'):
        #
        #   ==========  ==========  ======================  ===============
        #   izin [bar]  t_min [ms]  ESKİ (ters) hüküm       ŞİMDİKİ hüküm
        #   ==========  ==========  ======================  ===============
        #     2,00      1222,3100   achievable              achievable
        #    20,00       122,2310   achievable              achievable
        #   171,05        14,2918   achievable              achievable
        #   171,39        14,2635   achievable              achievable
        #   249,50         9,7981   achievable              achievable
        #   249,60         9,7942   unreachable_by_sched.   no_scheduling_c.
        #   400,00         6,1115   unreachable_by_sched.   no_scheduling_c.
        #   ==========  ==========  ======================  ===============
        #
        # Yani kusur t_min <= t_c dalındadır ve sınır J = 249,5465 bar'da
        # geçilir (171,39 bar DEĞİL — o sayı yanlış dalga hızından geliyordu).
        #
        # Michaud bağıntısında dP -> 0 (t -> sonsuz) olduğundan "zamanlamayla
        # ULAŞILAMAZ" diye bir dal FİZİKSEL OLARAK YOKTUR; hüküm sözcüğü
        # kaldırıldı. Ayrı olan şey, kısıtın BAĞLAYIP bağlamadığıdır.
        joukowsky_rise_Pa = None if a is None else rho * a * v
        if joukowsky_rise_Pa is not None:
            closure['joukowsky_rise_Pa'] = float(joukowsky_rise_Pa)
        if t_critical_s is None:
            # Hangi rejimde olduğumuz t_c olmadan BİLİNEMEZ. Eski kod bu
            # dalda hükmü koşulsuz 'achievable_by_scheduling' basıyordu,
            # yani hüküm hiç SINANMADAN yayımlanıyordu. Kazanılmamış hüküm
            # yayımlanmaz.
            closure['status'] = 'not_evaluated'
            closure['message'] = (
                'the closure verdict was NOT evaluated: deciding whether a '
                'closure schedule is needed at all requires the pipe period '
                't_c = 2L/a, which needs both bulk_modulus_Pa and '
                'pipe_youngs_modulus_Pa. The Michaud minimum closure time '
                f'({t_min * 1e3:.1f} ms) is reported as an estimate only.')
            notes.append(closure['message'])
        elif t_min <= t_critical_s:
            closure['status'] = 'no_scheduling_constraint'
            closure['message'] = (
                f'the allowance ({float(allowable_pressure_rise_Pa) / 1e5:.2f} '
                f'bar) is at or above the full Joukowsky rise '
                f'({joukowsky_rise_Pa / 1e5:.2f} bar), so the line stays '
                'under the allowance for ANY closure schedule, instantaneous '
                'closure included. No closure-time constraint applies; the '
                f'Michaud time {t_min * 1e3:.1f} ms is below the pipe period '
                f't_c = {t_critical_s * 1e3:.1f} ms and is not binding.')
        else:
            closure['status'] = 'achievable_by_scheduling'
            closure['message'] = (
                f'closing no faster than {t_min * 1e3:.1f} ms keeps the '
                'surge under the allowance by the Michaud estimate '
                f'(pipe period t_c = {t_critical_s * 1e3:.1f} ms). '
                'Confirm with the water_hammer solver.')

    # ------------------------------------------------------------------
    # ÖH Z5S / defter P5B3-02 + P4B4-07 — AKIŞKAN ETİKETİ ⟷ HAT YOĞUNLUĞU.
    #
    # Bu fonksiyon hattın GERÇEK yoğunluğunu (hız hesabı için) ve ayrıca bir
    # akışkan ETİKETİ alır. Eskiden yoğunluk çözücüye yalnız bulk modülüyle
    # BİRLİKTE iletiliyordu; etiket tek başına gittiğinde çözücü etiketin
    # TABLO yoğunluğunu kullanıyor ve aynı hattın debisi iki modülde iki
    # farklı sayı oluyordu. ÖLÇÜLDÜ (LH2 hattı, deponun kendi
    # PropellantDatabase kaydı rho = 70,8 kg/m3, ṁ = 2,0 kg/s, etiket
    # 'water'): çözücü hattın debisini 28,192 kg/s okuyor (14,096 kat) ve
    # Joukowsky artışını su yoğunluğuyla 754,85 bar veriyor.
    #
    # Onarım iki ayaklıdır: (i) hattın yoğunluğu HER ZAMAN çözücüye iletilir
    # (tek kaynak: hattın kendi yoğunluğu), (ii) etiketin tablo yoğunluğu ile
    # hattın yoğunluğu ayrışıyorsa bu SESSİZ kalmaz, yapısal bir alanla
    # beyan edilir.
    label_key = None if fluid is None else str(fluid).lower()
    label_rec = (None if label_key is None
                 else WH_FLUID_PROPERTIES.get(label_key))
    fluid_label = {
        'key': label_key,
        'line_density_kg_m3': float(rho),
        'table_density_kg_m3': (None if label_rec is None
                                else float(label_rec['density_kg_m3'])),
        'density_forwarded_to_solver': True,
        '_basis': (
            'The solver is always given the LINE density, so the reported '
            'mass flow and velocity cannot diverge from the line budget. The '
            'fluid label only selects the tabulated bulk modulus and vapour '
            'pressure.'),
    }
    if label_rec is None:
        fluid_label['represents_line_density'] = None
        fluid_label['label_status'] = (
            'not_tabulated' if label_key is not None else 'not_supplied')
    else:
        oran = float(rho) / float(label_rec['density_kg_m3'])
        fluid_label['density_ratio'] = oran
        fluid_label['represents_line_density'] = bool(abs(oran - 1.0) <= 1e-3)
        fluid_label['label_status'] = ('consistent'
                                       if fluid_label['represents_line_density']
                                       else 'density_mismatch')
        if not fluid_label['represents_line_density']:
            notes.append(
                f"Fluid label '{label_key}' does NOT represent this line: the "
                f"line density is {rho:.4g} kg/m3 but the tabulated density "
                f"of '{label_key}' is "
                f"{float(label_rec['density_kg_m3']):.4g} kg/m3 "
                f"({oran:.3f}x). The solver is given the LINE density, but "
                "the bulk modulus and vapour pressure still come from that "
                "label's table — supply bulk_modulus_Pa and "
                "vapor_pressure_Pa for the actual fluid.")

    kwargs = {
        'fluid': str(fluid),
        'line_length_m': float(length),
        'line_id_mm': float(d * 1000.0),
        'wall_thickness_mm': float(t_wall * 1000.0),
        'working_pressure_bar': float(p_work / 1.0e5),
        'flow_velocity_m_s': float(v),
        'valve_closure_time_ms': (None if valve_closure_time_s is None
                                  else float(valve_closure_time_s) * 1e3),
        # Hattın KENDİ yoğunluğu (etiketin tablo yoğunluğu değil).
        'density_kg_m3': rho,
    }
    if pipe_material is not None:
        kwargs['pipe_material'] = str(pipe_material)
    if bulk_modulus_Pa is not None:
        kwargs['bulk_modulus_Pa'] = float(bulk_modulus_Pa)
    if vapor_pressure_Pa is not None:
        kwargs['vapor_pressure_Pa'] = float(vapor_pressure_Pa)

    return {
        'analyzer_kwargs': kwargs,
        'fluid_label': fluid_label,
        'flow_velocity_m_s': float(v),
        'wave_speed_m_s': (None if a is None else float(a)),
        'wave_speed_rigid_m_s': (None if a_rigid is None
                                 else float(a_rigid)),
        'critical_closure_time_s': (None if t_critical_s is None
                                    else float(t_critical_s)),
        'closure_time': closure,
        'notes': notes,
        '_basis': (
            'This is an INPUT ADAPTER, not a transient solution: it '
            'converts the steady line result into the units and keys '
            'hrma.analysis.water_hammer.WaterHammerAnalyzer.analyze '
            'expects, and inverts the Michaud slow-closure relation for a '
            'minimum closure time. Wave speed and critical closure time, '
            'when reported, come from the water_hammer module\'s own '
            'functions (single source, no copy). Pass analyzer_kwargs '
            'straight into analyze() for the actual surge verdict.'),
        'not_modelled': dict(NOT_MODELLED),
    }


# ===========================================================================
# Uçtan uca
# ===========================================================================
def _hat_adiyla_isaretle(kayitlar, onek):
    """``validity`` kayıtlarının mesajına hat adı ön ekini koyar.

    Kayıtlar KOPYALANIR: üst düzey ``validity`` listesi ``valve`` alt
    sözlüğünün kayıtlarıyla AYNI nesneleri taşır (``list.extend``), yerinde
    değiştirmek aynı mesajı iki kez öneklerdi.
    """
    out = []
    for kayit in kayitlar:
        if (isinstance(kayit, dict) and isinstance(kayit.get('message'), str)
                and not kayit['message'].startswith(onek)):
            kayit = dict(kayit)
            kayit['message'] = onek + kayit['message']
        out.append(kayit)
    return out


def _hat_adiyla_isaretle_metin(metinler, onek):
    """``warnings`` düz metin listesine aynı ön eki koyar."""
    return [(onek + m) if (isinstance(m, str) and not m.startswith(onek))
            else m for m in metinler]


def analyze_valve_feedline(*,
                           mass_flow_kg_s: float,
                           density_kg_m3: float,
                           viscosity_Pa_s: float,
                           line_id_m: float,
                           line_length_m: float,
                           inlet_pressure_Pa: float,
                           valve_pressure_drop_Pa: float,
                           wall_thickness_m: Optional[float] = None,
                           fluid: Optional[str] = None,
                           pipe_material: str = PIPE_ROUGHNESS_DEFAULT_KEY,
                           pipe_structural_material: str
                           = WH_DEFAULT_PIPE_MATERIAL,
                           roughness_m: Optional[float] = None,
                           roughness_provenance: Optional[str] = None,
                           fittings: Optional[Dict[str, float]] = None,
                           extra_loss_coefficient: float = 0.0,
                           elevation_gain_m: float = 0.0,
                           vapor_pressure_Pa: Optional[float] = None,
                           critical_pressure_Pa: Optional[float] = None,
                           valve_style: str = 'ball_full_bore',
                           pressure_recovery_factor: Optional[float] = None,
                           bulk_modulus_Pa: Optional[float] = None,
                           pipe_youngs_modulus_Pa: Optional[float] = None,
                           valve_closure_time_s: Optional[float] = None,
                           allowable_pressure_rise_Pa: Optional[float] = None,
                           line_label: Optional[str] = None
                           ) -> Dict:
    """Hat bütçesi + vana boyutlandırma + su koçu girdisini tek çağrıda üretir.

    Vana, hattın SONUNDA kabul edilir: vana giriş basıncı hat çıkış
    basıncıdır. Su koçu girdisi yalnız ``wall_thickness_m`` VE ``fluid``
    birlikte verilirse üretilir (boru cidarı olmadan dalga hızı, akışkan
    etiketi olmadan hacimsel modül tanımsızdır).

    İKİ MALZEME ARGÜMANI, İKİ SÖZLÜK (ÖH Z5S / defter P4B4-08)
    ---------------------------------------------------------
    * ``pipe_material``            : yüzey bitişi -> ``PIPE_ROUGHNESS_M``
      (sürtünme faktörü). ``roughness_m`` verilirse bu argüman okunmaz.
    * ``pipe_structural_material`` : yapısal alaşım -> ``materials_db``
      (Young modülü + hoop dayanımı) ve su koçu çözücüsüne bu ad gider.

    Eskiden tek bir ``pipe_material`` argümanı ikisine birden gidiyordu ve
    iki sözlüğün kesişimi BOŞ olduğu için hiçbir değer ikisini birden
    sağlayamıyordu: varsayılan 'stainless_tubing' su koçu tarafında her
    çağrıda 'Unknown pipe material' uyarısıyla ss_304'e düşüyor ve hükmü
    fail-closed kuralı gereği zorla MARGINAL'e indiriyordu.

    ``fluid`` verilmezse su koçu bloğu ÜRETİLMEZ ve sebebi ``validity``
    listesinde adıyla söylenir; sessizce 'water' etiketi konmaz (P4B4-07).

    HAT ADI (ÖH D35 / OH-GT-19)
    ---------------------------
    ``line_label`` verilirse yayımlanan her ``validity[].message`` ve her
    ``warnings[]`` metni ``'[<etiket>] '`` ön ekiyle başlar. Sebep ÖLÇÜLDÜ
    (``raw/OH/D35/dil-safligi/a1/once.json``, gerçek ``/calculate_liquid``
    yanıtı): sıvı motor bu modülü İKİ kez çağırıyor (yakıt + oksitleyici)
    ve panel dört ``validity`` adresini tek listede topluyor; su koçu
    mesajı iki hattan da AYNI cümleyle geliyordu, yani kullanıcı aynı
    uyarıyı iki kez görüyor ve hangi hatta ait olduğunu okuyamıyordu.

    FAIL-CLOSED: ``line_label`` verilmezse mesaj AYNEN kalır — modülün tek
    başına çağrıldığı yerlerde (testler, doğrudan API) uydurma bir hat adı
    yazılmaz. Ön ek yalnız KULLANICIYA DÖNÜK metne girer; alan adları,
    ``status`` değerleri ve sayıların hiçbiri değişmez.
    """
    line = line_pressure_drop(
        mass_flow_kg_s=mass_flow_kg_s,
        density_kg_m3=density_kg_m3,
        viscosity_Pa_s=viscosity_Pa_s,
        line_id_m=line_id_m,
        line_length_m=line_length_m,
        pipe_material=pipe_material,
        roughness_m=roughness_m,
        roughness_provenance=roughness_provenance,
        fittings=fittings,
        extra_loss_coefficient=extra_loss_coefficient,
        elevation_gain_m=elevation_gain_m,
        inlet_pressure_Pa=inlet_pressure_Pa,
        vapor_pressure_Pa=vapor_pressure_Pa)

    p_valve_in = line['total']['outlet_pressure_Pa']
    warnings = list(line['warnings'])
    validity = list(line['validity'])

    # ------------------------------------------------------------------
    # ÖH D19 / P5B3-08 — REJİM HÜKMÜ ARTIK ETİKETTEN KAZANILIYOR.
    #
    # D18, ``critical_pressure_Pa`` yokken rejim hükmünü ADIYLA geri çekti
    # (``capacity.regime_verified = False``, Cv bir ALT SINIR). Doğru ama
    # EKSİK bir onarımdı: beyan çözüm değildir. Kritik basınç, akışkan
    # ETİKETİ verildiğinde bilinen bir madde özelliğidir ve modülün kendi
    # tek kaynağında (``water_hammer.FLUID_PROPERTIES`` — buhar basıncının
    # da geldiği tablo) durur. Çağıran ayrıca vermediyse etiketten okunur
    # ve KÖKENİ künyeye yazılır.
    #
    # ÖLÇÜLDÜ (01_capa_ONCE.json, /calculate_liquid): iki besleme hattının
    # ikisinde de ``regime_verified = False`` ve ``choked_pressure_drop_Pa
    # = None`` idi. Oksitleyici hattı (lox) artık hükmü KAZANIYOR. Yakıt
    # hattı (rp1) kazanamıyor: RP-1 bir kerosen kesitidir, kritik noktası
    # parti bağımlı bir sözde-kritik kestirimdir ve tabloda BİLEREK yoktur
    # — o hatta D18'in geri çekme beyanı yürürlükte kalır (fail-closed,
    # uydurma değer yazılmaz).
    # ------------------------------------------------------------------
    critical_provenance = ('caller_supplied'
                           if critical_pressure_Pa is not None else None)
    if critical_pressure_Pa is None and fluid is not None:
        _pc_kayit = WH_FLUID_PROPERTIES.get(str(fluid).lower())
        _pc = (None if _pc_kayit is None
               else _pc_kayit.get('critical_pressure_Pa'))
        if _pc is not None:
            critical_pressure_Pa = float(_pc)
            critical_provenance = 'fluid_table:%s' % str(fluid).lower()

    valve = None
    if p_valve_in is not None and p_valve_in > 0.0:
        valve = size_valve(
            mass_flow_kg_s=mass_flow_kg_s,
            density_kg_m3=density_kg_m3,
            inlet_pressure_Pa=p_valve_in,
            pressure_drop_Pa=valve_pressure_drop_Pa,
            vapor_pressure_Pa=vapor_pressure_Pa,
            critical_pressure_Pa=critical_pressure_Pa,
            valve_style=valve_style,
            pressure_recovery_factor=pressure_recovery_factor)
        warnings.extend(valve['warnings'])
        validity.extend(valve['validity'])
    else:
        validity.append({
            'field': 'valve',
            'status': 'not_evaluated',
            'message': (
                'the valve was NOT sized: the line budget leaves no usable '
                'inlet pressure at the valve. Fix the line sizing first.')})

    hammer = None
    if (wall_thickness_m is not None and fluid is not None
            and (p_valve_in is None or p_valve_in <= 0.0)):
        # ÖH D20 / P5B3-13 (ikinci ayak): vana ayağı zaten bu koşulda
        # boyutlandırma YAPMIYOR; su koçu bağlaması ise ÜRETİLİYORDU.
        # ÖLÇÜLDÜ (taban 14acd1d, ``once.json`` P5B3-13 ``cikisi_negatif_hat``;
        # 200 m hat): ``hat_cikis_bar = -5,741082``, ``vana_var = False``,
        # ama ``hammer_var = True`` ve bağlamanın çalışma basıncı 30,0 bar.
        # Vananın önünde basınç yoksa vanaya bağlı su koçu olayı da yoktur.
        validity.append({
            'field': 'water_hammer_inputs',
            'status': 'not_evaluated',
            'message': (
                'the water-hammer coupling was NOT produced: the line '
                'budget leaves no usable pressure at the valve, which is '
                'where the surge originates. Fix the line sizing first '
                '(the valve was not sized either, for the same reason).')})
    elif wall_thickness_m is not None and fluid is not None:
        hammer = water_hammer_inputs(
            fluid=fluid,
            mass_flow_kg_s=mass_flow_kg_s,
            density_kg_m3=density_kg_m3,
            line_id_m=line_id_m,
            wall_thickness_m=wall_thickness_m,
            line_length_m=line_length_m,
            # ------------------------------------------------------------
            # ÖH D20 / P5B3-13 — VANA HATTIN SONUNDADIR.
            #
            # Bu fonksiyonun kendi docstring'i "Vana, hattın SONUNDA kabul
            # edilir: vana giriş basıncı hat çıkış basıncıdır" der ve
            # ``size_valve`` çağrısı gerçekten ``p_valve_in``i kullanır.
            # Su koçu bağlaması ise hattın GİRİŞ basıncını çalışma basıncı
            # diye geçiriyordu. ÖLÇÜLDÜ (taban 14acd1d, ``once.json``
            # P5B3-13; su, D 20 mm, mdot 2 kg/s, giriş 30 bar, 6 dirsek +
            # 1 küresel vana):
            #   25 m hat -> hat çıkışı 25,000995 bar, bağlamaya giden
            #               ``working_pressure_bar`` 30,0 (+%19,996)
            #   1 m hat  -> çıkış 29,217051 bar, bağlama yine 30,0 (+%2,68)
            # Çalışma basıncı su koçu çözücüsünde cidar gerilmesi ve
            # kavitasyon/sütun-ayrılması hükmünün TABANIDIR; girişin
            # değeri verilince surge sonrası tepe basınç ve emniyet payı
            # sistematik olarak İYİMSER yönde kayar.
            # ------------------------------------------------------------
            working_pressure_Pa=p_valve_in,
            bulk_modulus_Pa=bulk_modulus_Pa,
            pipe_youngs_modulus_Pa=pipe_youngs_modulus_Pa,
            valve_closure_time_s=valve_closure_time_s,
            allowable_pressure_rise_Pa=allowable_pressure_rise_Pa,
            vapor_pressure_Pa=vapor_pressure_Pa,
            # materials_db anahtarı — pürüzlülük anahtarı DEĞİL (P4B4-08).
            pipe_material=pipe_structural_material)
    elif wall_thickness_m is None:
        validity.append({
            'field': 'water_hammer_inputs',
            'status': 'not_evaluated',
            'message': (
                'the water-hammer coupling was NOT produced: '
                'wall_thickness_m is required, because the wave speed '
                'depends on the pipe wall elasticity.')})
    else:
        validity.append({
            'field': 'water_hammer_inputs',
            'status': 'not_evaluated',
            'message': (
                'the water-hammer coupling was NOT produced: no fluid key '
                'was supplied, and no default fluid label is substituted. '
                'The wave speed needs a tabulated liquid bulk modulus; pass '
                "the propellant's own key (or bulk_modulus_Pa with a custom "
                'label) to get the coupling.')})

    total_dp = line['total']['dp_Pa']
    if valve is not None:
        total_dp += valve['inputs']['pressure_drop_Pa']

    # --- ÖH D35 / OH-GT-19: HAT ADI ÖN EKİ (yalnız istenirse) -----------
    # Panel dört ayrı adresten (hat + vana, iki hat) tek liste topluyor;
    # ön ek olmadan aynı cümle iki kez ve sahipsiz görünüyordu.
    if line_label:
        _onek = '[%s] ' % str(line_label)
        validity = _hat_adiyla_isaretle(validity, _onek)
        warnings = _hat_adiyla_isaretle_metin(warnings, _onek)
        if valve is not None:
            valve = dict(valve)
            valve['validity'] = _hat_adiyla_isaretle(
                valve.get('validity') or [], _onek)
            valve['warnings'] = _hat_adiyla_isaretle_metin(
                valve.get('warnings') or [], _onek)

    return {
        'line': line,
        'valve': valve,
        'water_hammer': hammer,
        # İKİ AYRI MALZEME KÜNYESİ (P4B4-08): hangi ad hangi tabloya gitti.
        'pipe_materials': {
            'roughness_key': (None if roughness_m is not None
                              else str(pipe_material)),
            'roughness_key_table': 'PIPE_ROUGHNESS_M (surface finish)',
            # ÖH D18 / P5B3-10: ölçülmüş pürüzlülük geçirildiyse KÖKENİ.
            'roughness_provenance': line['inputs']['roughness_provenance'],
            'structural_key': str(pipe_structural_material),
            'structural_key_table': 'materials_db (structural alloy)',
            # ÖH D19 / P5B3-08: boğulma sınırının kritik basıncı NEREDEN
            # geldi. None = hiçbir yerden (etiket yok ya da etiketin
            # tabloda kritik basıncı yok) -> rejim hükmü geri çekilir.
            'critical_pressure_provenance': critical_provenance,
            'critical_pressure_Pa': (None if critical_pressure_Pa is None
                                     else float(critical_pressure_Pa)),
            '_basis': (
                'Surface finish and structural alloy are DIFFERENT properties '
                'of the same pipe and live in different tables; one argument '
                'cannot satisfy both. The roughness key feeds the friction '
                'factor, the structural key feeds the wave speed and the hoop '
                'pressure rating. A measured roughness_m overrides the '
                'roughness key entirely.'),
        },
        'budget': {
            'line_dp_Pa': float(line['total']['dp_Pa']),
            'valve_dp_Pa': (None if valve is None
                            else float(valve['inputs']['pressure_drop_Pa'])),
            'total_dp_Pa': float(total_dp),
            'inlet_pressure_Pa': float(inlet_pressure_Pa),
            'delivery_pressure_Pa': (None if valve is None else
                                     float(valve['inputs']
                                           ['outlet_pressure_Pa'])),
            '_basis': (
                'The valve is placed at the END of the line: its inlet '
                'pressure is the line outlet pressure, and the delivery '
                'pressure is what remains after the valve drop. Steady, '
                'incompressible, single-phase budget.'),
        },
        'validity': validity,
        'warnings': warnings,
        'not_modelled': dict(NOT_MODELLED),
    }
