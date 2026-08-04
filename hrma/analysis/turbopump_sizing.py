"""Turbopompa boyutlandırma çekirdeği (yol haritası C1).

`cycle_power_balance` çevrim çözücüsü ṁ, ΔP, verim, mil gücü ve TIT verir;
bu modül eksik kalan boyutlandırma zincirini tamamlar:

    NPSH_mevcut -> emme özgül devri (Nss) -> mil devri N üst sınırı ->
    özgül devir (Ns) -> kademe sayısı -> çark çapı D2 (baş katsayısından) ->
    kanat sayısı önerisi + indüser gereksinimi -> NPSH_gerekli ve MARJ ->
    türbin ortalama çapı + kademe sayısı

Fizik ve kaynaklar
------------------
Mevcut net pozitif emme yüksekliği (statik yükseklik ve ivme yükü HARİÇ,
bkz. NOT_MODELLED):

    NPSH_avail = (p_tank - dp_hat - p_buhar) / (rho * g)                    (1)

      Huzel, D.K. & Huang, D.H., "Design of Liquid Propellant Rocket
      Engines", NASA SP-125 (1967; 2. baskı 1971), Böl. 6; aynı yazarların
      AIAA cilt 147 (1992) yeniden basımı Böl. 6 (pompa emme performansı).
      Sutton, G.P. & Biblarz, O., "Rocket Propulsion Elements", 9. baskı,
      Böl. 10 (kavitasyon ve emme özgül devri).

Emme özgül devri ve özgül devir — ABD sanayi birim geleneğiyle
(N: rpm, Q: gpm, H ve NPSH: ft; boyutsuz Omega_s = Ns_US / 2733):

    Nss = N * sqrt(Q) / NPSH^0.75                                           (2)
    Ns  = N * sqrt(Q) / H^0.75                                              (3)

      Huzel & Huang Böl. 6 (pompa tasarım parametreleri); Sutton 9. baskı
      Böl. 10. Aynı bağıntı devri çözersek mil devri üst sınırını verir:
      N_max = Nss_hedef * NPSH_avail^0.75 / sqrt(Q). Tasarım devri, NPSH
      marjı bırakmak için N_max'ın altına indirgenir (varsayılan çarpan
      0.9 -> NPSH_avail/NPSH_gerekli = 0.9^(-4/3) ~= 1.15 marj).

Gerekli NPSH, hedeflenen emme kabiliyetinden geri çözülür:

    NPSH_req = (N * sqrt(Q) / Nss_kabiliyet)^(4/3)                          (4)

Kademe sayısı: kademe başına özgül devir Ns_kademe = Ns_toplam * n^0.75
santrifüj bandın (~500-3000 US) altına düşmeyecek en küçük n seçilir
(Huzel & Huang Böl. 6, özgül devir - pompa tipi seçimi).

Çark çapı, kademe baş katsayısından (psi = g*H_kademe / u2^2):

    u2 = sqrt(g * H_kademe / psi),   D2 = 60 * u2 / (pi * N)                (5)

      Huzel & Huang Böl. 6 (çark tasarım parametreleri); Sutton 9. baskı
      Böl. 10. Tasarım bandı psi ~ 0.40-0.60 (varsayılan 0.50); donanım
      bandın dışına taşabilir (RL10A-3-3A geriye hesap: yakıt 0.60,
      LOX 0.73), bu yüzden sert geçerlilik bandı 0.20-0.75 tutuldu.

Türbin (basınç kademeli aksiyon, eşit iş bölüşümü): püskürtme hızı
c0 = sqrt(2*dh_ideal); tek sıralı aksiyon çarkında en iyi hız oranı
U/C0 = cos(alfa)/2 (klasik aksiyon türbini teorisi; Huzel & Huang Böl. 6
türbin tasarımı; Sutton 9. baskı Böl. 10). n kademede kademe başına
püskürtme hızı c0/sqrt(n) olduğundan optimum çevre hızı:

    U_opt(n) = (cos(alfa)/2) * sqrt(2*dh_ideal/n)                           (6)

U, hem yapısal pratik sınırıyla hem de (aynı mildeyse) pompa çark çevre
hızı zarfıyla sınırlanır; (6)'yı bu sınırın altına indiren en küçük n
kademe sayısı tahminidir. Ortalama çap D_m = 60*U/(pi*N).

Doğrulama çapaları (tests/test_turbopompa.py): RL10A-3-3 tasarım noktası
(PWA FR-1769 Tablo V-I), RL10A-3-3A donanım geometrisi (NASA TM-107318)
ve F-1 (Oefelein & Yang 1993, Tablo 2) — devir, kademe sayısı, çark çapı
ve türbin ortalama çapı mertebeleri yayımlanmış değerlere karşı sınanır.

Akışkan özellikleri (yoğunluk, buhar basıncı) GİRDİDİR, burada
hesaplanmaz; modül motor kodundan bağımsızdır, hiçbir engine modülü
ithal edilmez. Kullanıcıya görünen tüm metinler İngilizce, çıktı
JSON-güvenlidir. Ampirik katsayılar kaynak künyeli ve geçerlilik
aralıklıdır; aralık dışı girdide sessiz ekstrapolasyon yerine açık
'geçersiz aralık' beyanı (ValueError ya da ``validity`` kaydı) üretilir.
"""

import math
from typing import Dict, List, Optional

from hrma.constants import G_0

__all__ = [
    'npsh_available_m',
    'head_from_pressure_rise_m',
    'm3s_to_gpm',
    'm_to_ft',
    'specific_speed_us',
    'suction_specific_speed_us',
    'npsh_required_m',
    'pump_stage_count',
    'size_pump',
    'size_turbine',
    'size_turbopump',
    'NSS_NO_INDUCER_MARGINAL_US',
    'NSS_NO_INDUCER_MAX_US',
    'NSS_INDUCER_DESIGN_US',
    'NSS_TARGET_VALID_US',
    'NS_CENTRIFUGAL_MIN_US',
    'NS_CENTRIFUGAL_MAX_US',
    'PUMP_STAGES_MAX',
    'HEAD_COEFF_DEFAULT',
    'HEAD_COEFF_DESIGN_BAND',
    'HEAD_COEFF_VALID',
    'IMPELLER_BLADE_COUNT_RANGE',
    'SPEED_DERATE_DEFAULT',
    'TURBINE_NOZZLE_ANGLE_DEG',
    'TURBINE_PITCH_SPEED_LIMIT_M_S',
    'TURBINE_STAGES_MAX',
    'NOT_MODELLED',
]

# ---------------------------------------------------------------------------
# Birim çevrimleri — hepsi TANIM gereği kesin (uluslararası ft = 0.3048 m,
# in = 0.0254 m, ABD galonu = 231 in^3). Ns/Nss ABD birim geleneği bu
# çevrimlerle kurulur; boyutsuz karşılık Omega_s = Ns_US / 2733 (bekçi
# testi bu katsayıyı bağımsız türetir).
# ---------------------------------------------------------------------------
M_PER_FT = 0.3048                          # kesin tanım
M_PER_IN = 0.0254                          # kesin tanım
M3S_PER_GPM = 231.0 * 0.0254 ** 3 / 60.0   # kesin tanım, ~6.30902e-5 m^3/s


def m_to_ft(x_m: float) -> float:
    """Metre -> ft (kesin tanım 1 ft = 0.3048 m)."""
    return float(x_m) / M_PER_FT


def m3s_to_gpm(q_m3_s: float) -> float:
    """m^3/s -> ABD gpm (kesin tanım 1 gal = 231 in^3)."""
    return float(q_m3_s) / M3S_PER_GPM


# ---------------------------------------------------------------------------
# Ampirik tasarım bantları — TEK YERDE tanımlı, kaynak künyeli. Başka
# dosyada bu sayıları tekrar YAZMA; buradan ithal et (parametre
# tutarlılık kuralı). Hepsi 'approximate' mühendislik bandıdır, keskin
# fizik sınırı değildir.
# ---------------------------------------------------------------------------
# Emme özgül devri (US birimleri: rpm, gpm, ft):
# indüsersiz santrifüj çark pratikte ~8000-11000 bandında tükenir;
# roket pompası indüserleri tasarım bandını ~20000-55000'e taşır.
NSS_NO_INDUCER_MARGINAL_US = 8000.0
NSS_NO_INDUCER_MAX_US = 11000.0
NSS_INDUCER_DESIGN_US = 30000.0
NSS_TARGET_VALID_US = (5000.0, 55000.0)
NSS_SOURCE = (
    'Suction specific speed practice bands (US units, '
    'rpm*gpm^0.5/ft^0.75): conventional centrifugal impellers without an '
    'inducer reach roughly Nss 8,000-11,000; rocket-pump inducers extend '
    'the design band to roughly 20,000-55,000 (Huzel & Huang, "Design of '
    'Liquid Propellant Rocket Engines", NASA SP-125, Ch. 6 pump suction '
    'performance; Sutton & Biblarz, "Rocket Propulsion Elements", 9th '
    'ed., Ch. 10). Approximate engineering bands, not sharp physical '
    'limits.')

# Kademe başına özgül devir (US) santrifüj bandı ve kademe üst sınırı.
NS_CENTRIFUGAL_MIN_US = 500.0
NS_CENTRIFUGAL_MAX_US = 3000.0
PUMP_STAGES_MAX = 6
NS_SOURCE = (
    'Per-stage specific speed of centrifugal (radial/Francis-type) pump '
    'impellers spans roughly Ns 500-3000 (US units); below ~500 the '
    'single-stage efficiency collapses and the head is split over more '
    'stages (Huzel & Huang, NASA SP-125, Ch. 6 specific speed and pump '
    'type selection; Sutton 9th ed., Ch. 10). Stage count is the '
    'smallest n with Ns_stage = Ns_overall * n^0.75 >= 500. Approximate '
    'band; above ~3000 the impeller is mixed-flow/axial and this '
    "module's centrifugal head-coefficient sizing leaves its validity "
    'range.')

# Kademe baş katsayısı psi = g*H_kademe/u2^2.
HEAD_COEFF_DEFAULT = 0.50
HEAD_COEFF_DESIGN_BAND = (0.40, 0.60)
HEAD_COEFF_VALID = (0.20, 0.75)
HEAD_COEFF_SOURCE = (
    'Stage head coefficient psi = g*H_stage/u_tip^2 for centrifugal '
    'rocket-pump impellers: design band ~0.40-0.60, default 0.50 (Huzel '
    '& Huang, NASA SP-125, Ch. 6 impeller design parameters; Sutton 9th '
    'ed., Ch. 10). Built hardware can sit outside the design band '
    '(RL10A-3-3A back-calculated: fuel 0.60, LOX 0.73 - low specific '
    'speed geared pump), hence the wider hard validity band 0.20-0.75. '
    'Diameter scales as psi^-0.5, so the design band maps to a diameter '
    'uncertainty band of about +-10%.')

# Çark kanat sayısı önerisi (tam kanat; splitter hariç).
IMPELLER_BLADE_COUNT_RANGE = (5, 12)
BLADE_COUNT_SOURCE = (
    'Typical backswept centrifugal rocket-pump impellers carry 5-12 full '
    'blades, often 6-8 plus splitter vanes (Huzel & Huang, NASA SP-125, '
    'Ch. 6 impeller design). A firm count needs blade angles and loading '
    '(Pfleiderer/Stepanoff type criteria), which are NOT modelled here; '
    'the range is an engineering recommendation, not a computed value.')

# Emme sınırlı devirden tasarım devrine inerken uygulanan çarpan.
SPEED_DERATE_DEFAULT = 0.90
SPEED_DERATE_SOURCE = (
    'Design practice holds NPSH margin between available and required '
    'values rather than running at the cavitation limit (Huzel & Huang, '
    'NASA SP-125, Ch. 6 pump suction performance). A factor of 0.90 on '
    'the suction-limited speed gives NPSH_avail/NPSH_req = '
    '0.9^(-4/3) ~= 1.15, i.e. ~15% NPSH margin at the design point.')

# Türbin sabitleri.
TURBINE_NOZZLE_ANGLE_DEG = 20.0
TURBINE_NOZZLE_ANGLE_VALID = (10.0, 35.0)
TURBINE_PITCH_SPEED_LIMIT_M_S = 450.0
TURBINE_STAGES_MAX = 3
TURBINE_SOURCE = (
    'Impulse turbine, pressure-compounded with equal work split. '
    'Optimum single-row velocity ratio U/C0 = cos(alpha)/2 (classical '
    'impulse turbine theory; Huzel & Huang, NASA SP-125, Ch. 6 turbine '
    'design; Sutton 9th ed., Ch. 10); nozzle angle practice band '
    '~15-30 deg, default 20 deg. Pitch speed is bounded by a structural '
    'practice band (~250-450 m/s for uncooled rocket turbines, upper '
    'edge used as the default limit - the real limit is a blade-root '
    'stress analysis, NOT modelled) and, on a common shaft, by the pump '
    'impeller tip speed as a layout/compactness envelope (approximate '
    'heuristic; validated against the RL10 two-stage turbine in the '
    'guard tests). Stage count is the smallest n <= 3 whose per-stage '
    'optimum pitch speed fits under that bound.')

# ---------------------------------------------------------------------------
# Bilinçli olarak MODELLENMEYENLER. Bu sözlük çıktıya aynen konur;
# "sessizce yok sayıldı" durumu oluşmaz (sahte veri yasağı).
# ---------------------------------------------------------------------------
NOT_MODELLED = {
    'cavitation_dynamics': (
        'Cavitation dynamics are NOT modelled: bubble growth, thermodynamic '
        'suppression head, inducer backflow and POGO-type feed-system '
        'coupling are outside this model. The NPSH margin reported here is '
        'a steady design-rule comparison of available vs required NPSH, '
        'not a cavitation stability statement.'),
    'off_design_map': (
        'Off-design performance maps are NOT modelled: no pump H-Q curve, '
        'no turbine map, no throttling behaviour. All outputs are '
        'single-design-point sizing estimates.'),
    'rotordynamics': (
        'Rotordynamics are NOT modelled: shaft critical speeds, bearing '
        'DN limits, seals and axial thrust balance are outside this model. '
        'The shaft speed reported here is bounded only by suction '
        'performance and the optional user speed cap.'),
    'structural': (
        'Structural analysis is NOT modelled: impeller burst/stress '
        'margins and turbine blade-root stress are outside this model. '
        'Tip/pitch speed limits used here are engineering practice bands, '
        'not stress results.'),
    'fluid_properties': (
        'Fluid properties are NOT computed here: density and vapor '
        'pressure are caller-supplied inputs (the cycle/feed model owns '
        'them). Static elevation head between tank and pump inlet and '
        'vehicle acceleration head are NOT included in NPSH - add them to '
        'tank_pressure_Pa/line_pressure_drop_Pa if significant.'),
    'turbine_flow_details': (
        'Turbine flow details are NOT modelled: partial admission, blade '
        'profile/leaving losses and stage reaction are outside this '
        'model; turbine efficiency is a cycle-level input, not computed '
        'here. When the pitch speed is capped below the optimum velocity '
        'ratio, the implied efficiency penalty is declared but not '
        'quantified.'),
}


# ===========================================================================
# Saf yardımcılar (analitik, tek tek test edilebilir)
# ===========================================================================
def npsh_available_m(tank_pressure_Pa: float,
                     vapor_pressure_Pa: float,
                     density_kg_m3: float,
                     line_pressure_drop_Pa: float = 0.0) -> float:
    """Mevcut NPSH [m] — Eş. (1): (p_tank - dp_hat - p_v) / (rho*g).

    Kaynak: Huzel & Huang, NASA SP-125, Böl. 6; Sutton 9. baskı, Böl. 10.
    Statik yükseklik ve ivme yükü DAHİL DEĞİLDİR (NOT_MODELLED).
    """
    p_tank = float(tank_pressure_Pa)
    p_v = float(vapor_pressure_Pa)
    dp = float(line_pressure_drop_Pa)
    rho = float(density_kg_m3)
    if not (rho > 0.0) or not math.isfinite(rho):
        raise ValueError('density_kg_m3 must be positive and finite')
    if not (p_tank > 0.0) or p_v < 0.0 or dp < 0.0:
        raise ValueError('tank pressure must be positive; vapor pressure '
                         'and line pressure drop must be non-negative')
    npsh = (p_tank - dp - p_v) / (rho * G_0)
    if npsh <= 0.0:
        raise ValueError(
            'NPSH_available <= 0: pump inlet total pressure '
            f'({p_tank - dp:.1f} Pa after line loss) does not exceed the '
            f'vapor pressure ({p_v:.1f} Pa); the pump would cavitate at '
            'the inlet. Raise tank pressure or cut line losses.')
    return npsh


def head_from_pressure_rise_m(pressure_rise_Pa: float,
                              density_kg_m3: float) -> float:
    """Pompa başı [m]: H = dP / (rho*g) (Sutton 9. baskı, Böl. 10)."""
    dp = float(pressure_rise_Pa)
    rho = float(density_kg_m3)
    if not (dp > 0.0) or not (rho > 0.0):
        raise ValueError('pressure rise and density must be positive')
    return dp / (rho * G_0)


def specific_speed_us(shaft_speed_rpm: float, flow_gpm: float,
                      head_ft: float) -> float:
    """Özgül devir Ns (ABD birimleri) — Eş. (3): N*sqrt(Q)/H^0.75."""
    n = float(shaft_speed_rpm)
    q = float(flow_gpm)
    h = float(head_ft)
    if not (n > 0.0) or not (q > 0.0) or not (h > 0.0):
        raise ValueError('speed, flow and head must be positive')
    return n * math.sqrt(q) / h ** 0.75


def suction_specific_speed_us(shaft_speed_rpm: float, flow_gpm: float,
                              npsh_ft: float) -> float:
    """Emme özgül devri Nss (ABD birimleri) — Eş. (2): N*sqrt(Q)/NPSH^0.75."""
    return specific_speed_us(shaft_speed_rpm, flow_gpm, npsh_ft)


def npsh_required_m(shaft_speed_rpm: float, flow_m3_s: float,
                    nss_capability_us: float) -> float:
    """Gerekli NPSH [m] — Eş. (4): (N*sqrt(Q)/Nss_kabiliyet)^(4/3)."""
    n = float(shaft_speed_rpm)
    q = float(flow_m3_s)
    nss = float(nss_capability_us)
    if not (n > 0.0) or not (q > 0.0) or not (nss > 0.0):
        raise ValueError('speed, flow and Nss capability must be positive')
    q_gpm = m3s_to_gpm(q)
    npsh_ft = (n * math.sqrt(q_gpm) / nss) ** (4.0 / 3.0)
    return npsh_ft * M_PER_FT


def pump_stage_count(ns_overall_us: float) -> int:
    """Kademe sayısı: Ns_kademe = Ns_toplam*n^0.75 >= 500 veren en küçük n.

    Kaynak: Huzel & Huang, NASA SP-125, Böl. 6 (özgül devir - pompa tipi
    seçimi). PUMP_STAGES_MAX üstü kırpılır; çağıran geçerlilik beyanı koyar.
    """
    ns = float(ns_overall_us)
    if not (ns > 0.0):
        raise ValueError('overall specific speed must be positive')
    if ns >= NS_CENTRIFUGAL_MIN_US:
        return 1
    n = math.ceil((NS_CENTRIFUGAL_MIN_US / ns) ** (4.0 / 3.0))
    return int(min(n, PUMP_STAGES_MAX))


# ===========================================================================
# Pompa boyutlandırma
# ===========================================================================
def size_pump(*,
              mass_flow_kg_s: float,
              pressure_rise_Pa: float,
              density_kg_m3: float,
              vapor_pressure_Pa: float,
              tank_pressure_Pa: float,
              line_pressure_drop_Pa: float = 0.0,
              shaft_speed_rpm: Optional[float] = None,
              max_shaft_speed_rpm: Optional[float] = None,
              target_suction_specific_speed_us: Optional[float] = None,
              inducer_allowed: bool = True,
              head_coefficient: float = HEAD_COEFF_DEFAULT,
              speed_derate_factor: float = SPEED_DERATE_DEFAULT) -> Dict:
    """Tek pompanın boyutlandırma zinciri (NPSH -> N -> Ns -> D2 -> marj).

    Parametreler
    ------------
    mass_flow_kg_s, pressure_rise_Pa, density_kg_m3 :
        Çevrim çözümünden gelen debi [kg/s], basınç yükselişi [Pa] ve
        pompa giriş yoğunluğu [kg/m^3].
    vapor_pressure_Pa, tank_pressure_Pa, line_pressure_drop_Pa :
        NPSH_avail girdileri, Eş. (1). Akışkan özellikleri GİRDİDİR
        (NOT_MODELLED['fluid_properties']).
    shaft_speed_rpm :
        Verilirse devir SEÇİLMEZ, verilen değerle zincir yürütülür
        (dişli kutusu / ortak mil senaryosu). Verilmezse devir emme
        sınırından seçilir: N = derate * Nss_hedef*NPSH^0.75/sqrt(Q).
    target_suction_specific_speed_us :
        Pompanın tasarlanacağı emme kabiliyeti (US birimleri). None ->
        indüserli varsayılan 30000, indüsersiz 11000 (NSS_SOURCE).
    head_coefficient :
        Kademe baş katsayısı psi (HEAD_COEFF_SOURCE). Sert geçerlilik
        0.20-0.75 dışı ValueError; tasarım bandı 0.40-0.60 dışı beyanla
        kabul edilir.

    Dönüş: JSON-güvenli sözlük; her blok ``_basis`` künyeli, aralık dışı
    durumlar ``validity`` listesinde açık beyanla.
    """
    mdot = float(mass_flow_kg_s)
    dp = float(pressure_rise_Pa)
    rho = float(density_kg_m3)
    psi = float(head_coefficient)
    derate = float(speed_derate_factor)
    for name, val in (('mass_flow_kg_s', mdot), ('pressure_rise_Pa', dp),
                      ('density_kg_m3', rho)):
        if not (val > 0.0) or not math.isfinite(val):
            raise ValueError(f'{name} must be positive and finite')
    if not (HEAD_COEFF_VALID[0] <= psi <= HEAD_COEFF_VALID[1]):
        raise ValueError(
            f'head_coefficient {psi:g} is outside the supported validity '
            f'range {HEAD_COEFF_VALID} (invalid range - refusing silent '
            f'extrapolation). Source: {HEAD_COEFF_SOURCE}')
    if not (0.5 < derate <= 1.0):
        raise ValueError('speed_derate_factor must be in (0.5, 1.0]')

    warnings: List[str] = []
    validity: List[Dict] = []

    # --- Emme kabiliyeti hedefi -------------------------------------------
    nss_target = target_suction_specific_speed_us
    if nss_target is None:
        nss_target = (NSS_INDUCER_DESIGN_US if inducer_allowed
                      else NSS_NO_INDUCER_MAX_US)
    nss_target = float(nss_target)
    if not (NSS_TARGET_VALID_US[0] <= nss_target <= NSS_TARGET_VALID_US[1]):
        raise ValueError(
            f'target suction specific speed {nss_target:g} (US units) is '
            f'outside the supported validity range {NSS_TARGET_VALID_US} '
            f'(invalid range - refusing silent extrapolation). '
            f'Source: {NSS_SOURCE}')
    if (not inducer_allowed) and nss_target > NSS_NO_INDUCER_MAX_US:
        warnings.append(
            f'target suction specific speed {nss_target:.0f} exceeds the '
            f'no-inducer band (max ~{NSS_NO_INDUCER_MAX_US:.0f}) but '
            'inducer_allowed=False; target capped at the no-inducer '
            'limit.')
        nss_target = NSS_NO_INDUCER_MAX_US
    if not (HEAD_COEFF_DESIGN_BAND[0] <= psi <= HEAD_COEFF_DESIGN_BAND[1]):
        validity.append({
            'field': 'head_coefficient', 'status': 'out_of_design_band',
            'message': (
                f'head coefficient {psi:g} lies outside the design band '
                f'{HEAD_COEFF_DESIGN_BAND} (still inside the hard validity '
                f'band {HEAD_COEFF_VALID}); diameter estimate declared '
                'accordingly.')})

    # --- NPSH, debi, baş ---------------------------------------------------
    npsh_avail = npsh_available_m(tank_pressure_Pa, vapor_pressure_Pa, rho,
                                  line_pressure_drop_Pa)
    q_m3s = mdot / rho
    q_gpm = m3s_to_gpm(q_m3s)
    head_m = head_from_pressure_rise_m(dp, rho)
    head_ft = m_to_ft(head_m)
    npsh_avail_ft = m_to_ft(npsh_avail)

    # --- Devir seçimi ------------------------------------------------------
    n_suction_max = nss_target * npsh_avail_ft ** 0.75 / math.sqrt(q_gpm)
    if shaft_speed_rpm is not None:
        n_sel = float(shaft_speed_rpm)
        if not (n_sel > 0.0):
            raise ValueError('shaft_speed_rpm must be positive')
        mode = 'user_specified'
        rationale = (
            f'Shaft speed {n_sel:.0f} rpm supplied by the caller (gearbox '
            'or shared-shaft scenario); suction-limited maximum at the '
            f'target Nss {nss_target:.0f} is {n_suction_max:.0f} rpm.')
        if n_sel > n_suction_max:
            warnings.append(
                f'supplied shaft speed {n_sel:.0f} rpm exceeds the '
                f'suction-limited maximum {n_suction_max:.0f} rpm for the '
                f'target suction capability Nss {nss_target:.0f}; NPSH '
                'margin will be negative.')
    else:
        n_sel = derate * n_suction_max
        mode = 'suction_limited'
        rationale = (
            f'Shaft speed set by the suction limit: N_max = Nss_target * '
            f'NPSH_avail^0.75 / sqrt(Q) = {n_suction_max:.0f} rpm (Nss '
            f'{nss_target:.0f}, NPSH {npsh_avail_ft:.1f} ft, Q '
            f'{q_gpm:.0f} gpm), derated by {derate:g} for NPSH margin.')
        if max_shaft_speed_rpm is not None:
            n_cap = float(max_shaft_speed_rpm)
            if not (n_cap > 0.0):
                raise ValueError('max_shaft_speed_rpm must be positive')
            if n_sel > n_cap:
                n_sel = n_cap
                mode = 'user_speed_cap'
                rationale = (
                    f'Shaft speed capped at the user limit {n_cap:.0f} rpm '
                    '(below the derated suction-limited speed '
                    f'{derate * n_suction_max:.0f} rpm).')

    # --- Emme özgül devri, NPSH_req, marj ---------------------------------
    nss_req = suction_specific_speed_us(n_sel, q_gpm, npsh_avail_ft)
    npsh_req = npsh_required_m(n_sel, q_m3s, nss_target)
    npsh_margin = npsh_avail - npsh_req
    npsh_margin_ratio = npsh_avail / npsh_req
    if npsh_margin <= 0.0:
        warnings.append(
            f'NPSH margin is non-positive (available {npsh_avail:.2f} m, '
            f'required {npsh_req:.2f} m at Nss capability '
            f'{nss_target:.0f}); reduce shaft speed or raise tank '
            'pressure.')

    # --- İndüser kararı ----------------------------------------------------
    if nss_req > NSS_NO_INDUCER_MAX_US:
        inducer_status = 'required'
    elif nss_req > NSS_NO_INDUCER_MARGINAL_US:
        inducer_status = 'marginal'
    else:
        inducer_status = 'not_required'
    if inducer_status == 'required' and not inducer_allowed:
        warnings.append(
            f'required suction specific speed {nss_req:.0f} exceeds the '
            f'no-inducer band (max ~{NSS_NO_INDUCER_MAX_US:.0f}) but '
            'inducer_allowed=False: this operating point is infeasible '
            'without an inducer; reduce shaft speed or raise tank '
            'pressure.')

    # --- Kademe sayısı ve özgül devir -------------------------------------
    ns_overall = specific_speed_us(n_sel, q_gpm, head_ft)
    n_stages = pump_stage_count(ns_overall)
    ns_stage = ns_overall * n_stages ** 0.75
    if ns_stage < NS_CENTRIFUGAL_MIN_US:
        validity.append({
            'field': 'specific_speed_per_stage_us',
            'status': 'out_of_validity',
            'message': (
                f'per-stage specific speed {ns_stage:.0f} stays below the '
                f'centrifugal band minimum {NS_CENTRIFUGAL_MIN_US:.0f} even '
                f'at the stage cap n={PUMP_STAGES_MAX}; the head-coefficient '
                'diameter estimate is outside its validity range (invalid '
                'range declared - no silent extrapolation).')})
    if ns_stage > NS_CENTRIFUGAL_MAX_US:
        validity.append({
            'field': 'specific_speed_per_stage_us',
            'status': 'out_of_validity',
            'message': (
                f'per-stage specific speed {ns_stage:.0f} exceeds the '
                f'centrifugal band maximum {NS_CENTRIFUGAL_MAX_US:.0f} '
                '(mixed-flow/axial regime); the centrifugal '
                'head-coefficient diameter estimate is outside its '
                'validity range (invalid range declared - no silent '
                'extrapolation).')})

    # --- Çark çapı (baş katsayısından) ------------------------------------
    head_stage_m = head_m / n_stages
    u_tip = math.sqrt(G_0 * head_stage_m / psi)
    d2_m = 60.0 * u_tip / (math.pi * n_sel)
    # Tasarım bandının uçları: psi büyüdükçe D2 küçülür.
    d2_lo = 60.0 * math.sqrt(G_0 * head_stage_m / HEAD_COEFF_DESIGN_BAND[1]) \
        / (math.pi * n_sel)
    d2_hi = 60.0 * math.sqrt(G_0 * head_stage_m / HEAD_COEFF_DESIGN_BAND[0]) \
        / (math.pi * n_sel)

    return {
        'inputs': {
            'mass_flow_kg_s': mdot,
            'pressure_rise_Pa': dp,
            'density_kg_m3': rho,
            'vapor_pressure_Pa': float(vapor_pressure_Pa),
            'tank_pressure_Pa': float(tank_pressure_Pa),
            'line_pressure_drop_Pa': float(line_pressure_drop_Pa),
            'inducer_allowed': bool(inducer_allowed),
        },
        'shaft_speed': {
            'selected_rpm': float(n_sel),
            'mode': mode,
            'suction_limited_max_rpm': float(n_suction_max),
            'derate_factor': (derate if mode == 'suction_limited' else None),
            'rationale': rationale,
            '_basis': (
                'N_max = Nss_target * NPSH_avail^0.75 / sqrt(Q) (US units), '
                'inverted from Eq. Nss = N*sqrt(Q)/NPSH^0.75. '
                + NSS_SOURCE + ' Derate: ' + SPEED_DERATE_SOURCE),
        },
        'npsh': {
            'available_m': float(npsh_avail),
            'available_ft': float(npsh_avail_ft),
            'required_m': float(npsh_req),
            'required_ft': float(m_to_ft(npsh_req)),
            'margin_m': float(npsh_margin),
            'margin_ratio': float(npsh_margin_ratio),
            'suction_specific_speed_required_us': float(nss_req),
            'suction_specific_speed_capability_us': float(nss_target),
            '_basis': (
                'NPSH_avail = (p_tank - dp_line - p_vapor)/(rho*g); '
                'NPSH_req = (N*sqrt(Q)/Nss_capability)^(4/3) (US units); '
                'margin_ratio = NPSH_avail/NPSH_req. ' + NSS_SOURCE
                + ' Elevation and acceleration head NOT included '
                '(see not_modelled.fluid_properties).'),
        },
        'pump': {
            'volumetric_flow_m3_s': float(q_m3s),
            'volumetric_flow_gpm': float(q_gpm),
            'head_m': float(head_m),
            'head_ft': float(head_ft),
            'stage_head_m': float(head_stage_m),
            'specific_speed_overall_us': float(ns_overall),
            'specific_speed_per_stage_us': float(ns_stage),
            'stage_count': int(n_stages),
            'stage_count_max': int(PUMP_STAGES_MAX),
            'stage_count_basis': NS_SOURCE,
            'head_coefficient': float(psi),
            'head_coefficient_design_band': list(HEAD_COEFF_DESIGN_BAND),
            'impeller_tip_speed_m_s': float(u_tip),
            'impeller_diameter_m': float(d2_m),
            'impeller_diameter_in': float(d2_m / M_PER_IN),
            'impeller_diameter_band_m': [float(d2_lo), float(d2_hi)],
            'impeller_diameter_basis': (
                'u_tip = sqrt(g*H_stage/psi), D2 = 60*u_tip/(pi*N); band '
                'endpoints from the psi design band (larger psi -> smaller '
                'D2). ' + HEAD_COEFF_SOURCE),
            'blade_count_range': list(IMPELLER_BLADE_COUNT_RANGE),
            'blade_count_basis': BLADE_COUNT_SOURCE,
            'inducer': {
                'required': inducer_status == 'required',
                'status': inducer_status,
                'thresholds_us': {
                    'marginal_above': NSS_NO_INDUCER_MARGINAL_US,
                    'required_above': NSS_NO_INDUCER_MAX_US,
                },
                '_basis': (
                    'Inducer decision from the suction specific speed the '
                    'pump must actually achieve at the selected speed and '
                    'available NPSH: not required below '
                    f'{NSS_NO_INDUCER_MARGINAL_US:.0f}, marginal to '
                    f'{NSS_NO_INDUCER_MAX_US:.0f}, required above. '
                    + NSS_SOURCE),
            },
            '_basis': (
                'Ns = N*sqrt(Q)/H^0.75 (US units: rpm, gpm, ft; '
                'dimensionless Omega_s = Ns_US/2733); head H = '
                'dP/(rho*g); stage count from the per-stage centrifugal '
                'specific-speed band. ' + NS_SOURCE),
        },
        'validity': validity,
        'warnings': warnings,
        'not_modelled': dict(NOT_MODELLED),
    }


# ===========================================================================
# Türbin boyutlandırma
# ===========================================================================
def size_turbine(*,
                 shaft_speed_rpm: float,
                 ideal_specific_work_J_kg: Optional[float] = None,
                 power_W: Optional[float] = None,
                 mass_flow_kg_s: Optional[float] = None,
                 efficiency: Optional[float] = None,
                 pump_tip_speed_m_s: Optional[float] = None,
                 pitch_speed_limit_m_s: float = TURBINE_PITCH_SPEED_LIMIT_M_S,
                 nozzle_angle_deg: float = TURBINE_NOZZLE_ANGLE_DEG) -> Dict:
    """Türbin ortalama çapı + kademe sayısı tahmini (aksiyon, eşit iş).

    ``ideal_specific_work_J_kg`` verilmezse üçlü (power_W, mass_flow_kg_s,
    efficiency) zorunludur: dh_ideal = P/(mdot*eta). Kademe sayısı,
    Eş. (6)'daki optimum çevre hızını ``min(pitch_speed_limit_m_s,
    pump_tip_speed_m_s)`` zarfının altına indiren en küçük n'dir
    (TURBINE_SOURCE); n > TURBINE_STAGES_MAX ise hız zarfa kırpılır ve
    geçerlilik beyanı konur.
    """
    n_rpm = float(shaft_speed_rpm)
    if not (n_rpm > 0.0) or not math.isfinite(n_rpm):
        raise ValueError('shaft_speed_rpm must be positive and finite')
    alpha = float(nozzle_angle_deg)
    if not (TURBINE_NOZZLE_ANGLE_VALID[0] <= alpha
            <= TURBINE_NOZZLE_ANGLE_VALID[1]):
        raise ValueError(
            f'nozzle_angle_deg {alpha:g} is outside the supported validity '
            f'range {TURBINE_NOZZLE_ANGLE_VALID} (invalid range - refusing '
            f'silent extrapolation). Source: {TURBINE_SOURCE}')
    u_limit = float(pitch_speed_limit_m_s)
    if not (u_limit > 0.0):
        raise ValueError('pitch_speed_limit_m_s must be positive')

    if ideal_specific_work_J_kg is None:
        if power_W is None or mass_flow_kg_s is None or efficiency is None:
            raise ValueError(
                'turbine inputs incomplete: give ideal_specific_work_J_kg, '
                'or all three of power_W, mass_flow_kg_s and efficiency '
                '(dh_ideal = P/(mdot*eta)).')
        p_w = float(power_W)
        mdot = float(mass_flow_kg_s)
        eta = float(efficiency)
        if not (p_w > 0.0) or not (mdot > 0.0):
            raise ValueError('turbine power and mass flow must be positive')
        if not (0.0 < eta <= 1.0):
            raise ValueError('turbine efficiency must be in (0, 1]')
        dh_ideal = p_w / (mdot * eta)
        dh_source = 'power_W/(mass_flow_kg_s*efficiency)'
    else:
        dh_ideal = float(ideal_specific_work_J_kg)
        if not (dh_ideal > 0.0):
            raise ValueError('ideal_specific_work_J_kg must be positive')
        dh_source = 'caller_supplied'

    warnings: List[str] = []
    validity: List[Dict] = []

    nu_opt = math.cos(math.radians(alpha)) / 2.0
    c0 = math.sqrt(2.0 * dh_ideal)
    if pump_tip_speed_m_s is not None:
        u_env = min(u_limit, float(pump_tip_speed_m_s))
        env_source = ('pump_tip_speed_envelope'
                      if float(pump_tip_speed_m_s) < u_limit
                      else 'structural_practice_limit')
    else:
        u_env = u_limit
        env_source = 'structural_practice_limit'

    # Eş. (6): nu_opt*sqrt(2*dh/n) <= u_env -> n >= 2*dh*nu_opt^2/u_env^2.
    n_needed = max(1, math.ceil(2.0 * dh_ideal * nu_opt ** 2 / u_env ** 2
                                - 1e-12))
    if n_needed > TURBINE_STAGES_MAX:
        n_stages = TURBINE_STAGES_MAX
        u_pitch = u_env
        validity.append({
            'field': 'turbine_stage_count', 'status': 'out_of_validity',
            'message': (
                f'{n_needed} pressure-compounded stages would be needed to '
                f'reach the optimum velocity ratio under the pitch-speed '
                f'bound {u_env:.0f} m/s; capped at {TURBINE_STAGES_MAX}. '
                'The turbine runs below the optimum velocity ratio '
                '(efficiency penalty declared, not quantified - see '
                'not_modelled.turbine_flow_details).')})
        warnings.append(
            'turbine pitch speed capped below the optimum velocity ratio; '
            'stage count estimate is at its validity limit.')
    else:
        n_stages = n_needed
        u_pitch = nu_opt * math.sqrt(2.0 * dh_ideal / n_stages)

    d_mean = 60.0 * u_pitch / (math.pi * n_rpm)
    return {
        'stage_count': int(n_stages),
        'stage_count_max': int(TURBINE_STAGES_MAX),
        'arrangement': 'pressure_compounded_impulse_equal_work',
        'ideal_specific_work_J_kg': float(dh_ideal),
        'ideal_specific_work_source': dh_source,
        'spouting_velocity_m_s': float(c0),
        'pitch_speed_m_s': float(u_pitch),
        'pitch_speed_bound_m_s': float(u_env),
        'pitch_speed_bound_source': env_source,
        'mean_diameter_m': float(d_mean),
        'mean_diameter_in': float(d_mean / M_PER_IN),
        'velocity_ratio_overall': float(u_pitch / c0),
        'velocity_ratio_per_stage': float(
            u_pitch / (c0 / math.sqrt(n_stages))),
        'velocity_ratio_optimum_per_stage': float(nu_opt),
        'nozzle_angle_deg': float(alpha),
        'validity': validity,
        'warnings': warnings,
        '_basis': (
            'C0 = sqrt(2*dh_ideal); optimum per-stage velocity ratio '
            'U/C0_stage = cos(alpha)/2; equal work split -> C0_stage = '
            'C0/sqrt(n); D_mean = 60*U/(pi*N). ' + TURBINE_SOURCE),
    }


# ===========================================================================
# Turbopompa (pompa + türbin) orkestrasyonu
# ===========================================================================
def size_turbopump(*,
                   mass_flow_kg_s: float,
                   pressure_rise_Pa: float,
                   density_kg_m3: float,
                   vapor_pressure_Pa: float,
                   tank_pressure_Pa: float,
                   line_pressure_drop_Pa: float = 0.0,
                   shaft_speed_rpm: Optional[float] = None,
                   max_shaft_speed_rpm: Optional[float] = None,
                   target_suction_specific_speed_us: Optional[float] = None,
                   inducer_allowed: bool = True,
                   head_coefficient: float = HEAD_COEFF_DEFAULT,
                   speed_derate_factor: float = SPEED_DERATE_DEFAULT,
                   turbine_power_W: Optional[float] = None,
                   turbine_mass_flow_kg_s: Optional[float] = None,
                   turbine_efficiency: Optional[float] = None,
                   turbine_ideal_specific_work_J_kg: Optional[float] = None,
                   turbine_pitch_speed_limit_m_s: float =
                   TURBINE_PITCH_SPEED_LIMIT_M_S) -> Dict:
    """Tam zincir: pompa boyutlandırması + (girdisi verilmişse) türbin.

    Türbin, pompanın (seçilmiş ya da verilmiş) devrinde ve pompa çark
    çevre hızı zarfında boyutlandırılır (aynı mil varsayımı). Türbin
    girdisi hiç verilmemişse ``turbine`` alanı None döner ve nedeni
    ``turbine_basis`` ile beyan edilir (sahte veri yasağı: hesaplanmayan
    gösterilmez).
    """
    result = size_pump(
        mass_flow_kg_s=mass_flow_kg_s,
        pressure_rise_Pa=pressure_rise_Pa,
        density_kg_m3=density_kg_m3,
        vapor_pressure_Pa=vapor_pressure_Pa,
        tank_pressure_Pa=tank_pressure_Pa,
        line_pressure_drop_Pa=line_pressure_drop_Pa,
        shaft_speed_rpm=shaft_speed_rpm,
        max_shaft_speed_rpm=max_shaft_speed_rpm,
        target_suction_specific_speed_us=target_suction_specific_speed_us,
        inducer_allowed=inducer_allowed,
        head_coefficient=head_coefficient,
        speed_derate_factor=speed_derate_factor)

    turbine_given = any(v is not None for v in (
        turbine_power_W, turbine_mass_flow_kg_s, turbine_efficiency,
        turbine_ideal_specific_work_J_kg))
    if turbine_given:
        turbine = size_turbine(
            shaft_speed_rpm=result['shaft_speed']['selected_rpm'],
            ideal_specific_work_J_kg=turbine_ideal_specific_work_J_kg,
            power_W=turbine_power_W,
            mass_flow_kg_s=turbine_mass_flow_kg_s,
            efficiency=turbine_efficiency,
            pump_tip_speed_m_s=result['pump']['impeller_tip_speed_m_s'],
            pitch_speed_limit_m_s=turbine_pitch_speed_limit_m_s)
        result['validity'].extend(turbine.pop('validity'))
        result['warnings'].extend(turbine.pop('warnings'))
        result['turbine'] = turbine
        result['turbine_basis'] = (
            'Turbine sized on the pump shaft speed with the pump impeller '
            'tip speed as the pitch-speed envelope (common-shaft '
            'assumption). ' + TURBINE_SOURCE)
    else:
        result['turbine'] = None
        result['turbine_basis'] = (
            'NOT_SIZED: no turbine inputs supplied (need '
            'turbine_ideal_specific_work_J_kg, or turbine_power_W + '
            'turbine_mass_flow_kg_s + turbine_efficiency). Nothing is '
            'invented in its place.')
    return result
