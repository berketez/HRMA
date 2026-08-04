"""Ateşleyici boyutlandırma çekirdeği — torç ve piroteknik (yol haritası C4).

Sıvı/hibrit kamaralar için iki ateşleyici tipini AYRI yollarla boyutlandırır
ve her ikisini de aynı güvenli ateşleme penceresi ölçütüyle sınar:

    gerekli ateşleme enerjisi (kamara + itici tutuşma sıcaklığı)
        |-- torç: ateşleyici debisi ve süresi (enerji dengesinden)
        |-- piroteknik: şarj kütlesi (serbest hacim basınçlandırmadan)
        `-- güvenli ateşleme penceresi (sert başlangıç/hard start ölçütü)

Fizik ve kaynaklar
------------------
Gerekli ateşleme enerjisi — ateşleme penceresi boyunca kamaraya giren
iticiyi tutuşma sıcaklığına çıkarma enerjisi:

    m_ısıtılan = mdot_ana * t_pencere
    E_gerekli  = m_ısıtılan * cp * (T_tutuşma - T_başlangıç) / eta_aktarım  (1)

  Duyulur ısı dengesi. ``eta_aktarım`` ateşleyici enerjisinin gerçekten
  itici kütlesine geçen kesridir (gerisi cidara, egzoza ve karışmamış
  bölgelere gider); TASARIM SEÇİMİdir, hesaplanmaz, çıktıda adıyla beyan
  edilir.
      Sutton, G.P. & Biblarz, O., "Rocket Propulsion Elements", 9. baskı,
      Böl. 8 (itki odası ateşlemesi) ve Böl. 15 (ateşleyici donanımı).

Torç ateşleyici — küçük bir ön yakıcı sürekli yanar; gücü ana akışa
aktarılan enerjiyi pencere içinde sağlamalıdır:

    mdot_torç = E_gerekli / (eta_yanma * Q_torç * t_pencere)                (2)

  Q_torç torç iticilerinin birim kütle başına ısı salımıdır [J/kg]
  (GİRDİ — burada hesaplanmaz). Torç debisinin ana debiye oranı,
  yayımlanmış torç ateşleyicilerin küçük yüzdelerde çalıştığı pratiğine
  karşı TARANIR (tasarım kuralı değil, akıl sağlığı kontrolü).

Piroteknik ateşleyici — serbest hacim basınçlandırma ölçütü:

    m_gaz  = P_ateş * V_serbest / (R_gaz * T_gaz)                           (3)
    m_şarj = m_gaz / (1 - X_yoğuşmuş)                                       (4)

  Şarjın kütlesinin bir kısmı yoğuşmuş faz (cüruf) olarak kalır ve
  kamarayı basınçlandırmaz; yalnız gaz fazı sayılır.
      NASA SP-8051, "Solid Rocket Motor Igniters" (1971); Sutton &
      Biblarz 9. baskı Böl. 15. P_ateş bir TASARIM SEÇİMİdir (çalışma
      basıncının bir kesri), hesap değildir.
  Not: deponun katı motor yolunda (``solid_rocket_engine``) aynı ölçüt
  kendi katalog kayıtlarıyla zaten uygulanır; bu modül o tabloları İTHAL
  ETMEZ ve KOPYALAMAZ — gaz özellikleri ve yoğuşmuş faz kesri GİRDİdir.

Güvenli ateşleme penceresi — sert başlangıç (hard start) ölçütü:
tutuşma gecikirse kamarada yanmamış itici birikir; birikenin tamamı bir
anda yanarsa oluşacak basınç sınırı aşmamalıdır:

    P_ani = m_birikmiş * R_gaz * T_alev / V_serbest,  m_birikmiş = mdot*t
    t_maks = P_izin * V_serbest / (R_gaz * T_alev * mdot_ana)               (5)

  İdeal gaz, ani (sabit hacimde) yanma kabulüyle üst sınır kestirimidir;
  gerçek sert başlangıç detonasyona kadar gidebilen bir kimyasal-akustik
  olaydır ve burada MODELLENMEZ (bkz. ``NOT_MODELLED``).
      Sutton & Biblarz 9. baskı Böl. 8 (ateşleme ve sert başlangıç);
      NASA SP-8051.

Akışkan/itici özellikleri (cp, R, alev sıcaklığı, tutuşma sıcaklığı,
ısı salımı, yoğuşmuş faz kesri) GİRDİDİR, burada hesaplanmaz; hiçbir
engine modülü ithal edilmez. Kullanıcıya görünen tüm metinler İngilizce,
çıktı JSON-güvenlidir. Geçerlilik aralığı dışında sessiz ekstrapolasyon
yerine açık 'geçersiz aralık' beyanı üretilir.
"""

import math
from typing import Dict, List, Optional

from hrma.constants import R_UNIVERSAL

__all__ = [
    'specific_gas_constant',
    'ignition_energy_required',
    'hard_start_pressure',
    'safe_ignition_window_s',
    'torch_propellant_flow',
    'pyrotechnic_charge_mass',
    'size_igniter',
    'IGNITER_TYPES',
    'TRANSFER_EFFICIENCY_DEFAULT',
    'TRANSFER_EFFICIENCY_VALID',
    'TORCH_FLOW_FRACTION_SCREEN',
    'IGNITION_PRESSURE_FRACTION_DEFAULT',
    'IGNITION_PRESSURE_FRACTION_VALID',
    'HARD_START_PRESSURE_FRACTION_DEFAULT',
    'NOT_MODELLED',
]

#: Desteklenen ateşleyici tipleri.
IGNITER_TYPES = ('torch', 'pyrotechnic')

# ---------------------------------------------------------------------------
# Tasarım seçimleri ve geçerlilik bantları — TEK yerde tanımlı, künyeli.
# Bunlar FİZİK SABİTİ DEĞİLDİR; kullanıcı girdisiyle ezilebilir ve çıktıda
# "design choice" olarak beyan edilir.
# ---------------------------------------------------------------------------
TRANSFER_EFFICIENCY_DEFAULT = 0.30
TRANSFER_EFFICIENCY_VALID = (0.01, 1.00)
TRANSFER_EFFICIENCY_SOURCE = (
    'Energy transfer efficiency: the fraction of igniter energy release '
    'that actually heats the incoming propellant, the rest being lost to '
    'the chamber walls, swept out of the nozzle, or deposited in '
    'unmixed regions. It is a DESIGN CHOICE, not a computed or measured '
    'quantity of this model; the 0.30 default is a deliberately '
    'conservative placeholder for concept work. Ignition energy scales as '
    '1/eta, so this single number drives the answer - override it with a '
    'test-derived value before trusting the result (Sutton & Biblarz, '
    '"Rocket Propulsion Elements", 9th ed., Ch. 8 ignition discussion).')

# Torç debisinin ana debiye oranı için AKIL SAĞLIĞI taraması.
TORCH_FLOW_FRACTION_SCREEN = (0.001, 0.10)
TORCH_FLOW_FRACTION_SOURCE = (
    'Screening band only: published torch igniters run at a small '
    'percentage of the main propellant flow (order of one percent). The '
    '0.1%-10% band here is a SANITY SCREEN on the energy balance, not a '
    'design rule and not a published requirement; falling outside it '
    'usually means the ignition window, the transfer efficiency or the '
    'torch heat release is unrealistic (Sutton & Biblarz 9th ed., '
    'Ch. 8).')

# Piroteknik ateşleme basıncının çalışma basıncına oranı.
IGNITION_PRESSURE_FRACTION_DEFAULT = 0.15
IGNITION_PRESSURE_FRACTION_VALID = (0.02, 0.50)
IGNITION_PRESSURE_SOURCE = (
    'The igniter is sized to raise the chamber free volume to a fraction '
    'of the operating pressure (NASA SP-8051, "Solid Rocket Motor '
    'Igniters"; Sutton & Biblarz 9th ed., Ch. 15). That fraction is a '
    'DESIGN CHOICE, not a computed quantity: it is declared by name in '
    'the output and can be overridden.')

# Sert başlangıç ölçütünde izin verilen basıncın çalışma basıncına oranı.
HARD_START_PRESSURE_FRACTION_DEFAULT = 1.0
HARD_START_SOURCE = (
    'Hard-start criterion: unburnt propellant accumulating during the '
    'ignition delay is assumed to burn AT CONSTANT VOLUME all at once, '
    'and the resulting ideal-gas pressure is capped at a fraction of the '
    'operating pressure (default: the operating pressure itself). This '
    'is an order-of-magnitude UPPER BOUND on the tolerable delay, not a '
    'hard-start model: real hard starts are a chemical-acoustic event '
    'that can reach detonation, and the constant-volume ideal-gas '
    'assumption ignores mixing, vaporisation and heat loss (Sutton & '
    'Biblarz 9th ed., Ch. 8; NASA SP-8051).')

# ---------------------------------------------------------------------------
# Bilinçli olarak MODELLENMEYENLER. Çıktıya aynen konur (sahte veri yasağı).
# ---------------------------------------------------------------------------
NOT_MODELLED = {
    'ignition_chemistry': (
        'Ignition chemistry is NOT modelled: chemical induction time, '
        'ignition delay as a function of temperature and pressure, '
        'hypergolic reaction kinetics and minimum ignition energy of the '
        'actual propellant pair are outside this model. The ignition '
        'temperature used here is a caller-supplied input.'),
    'flame_spreading': (
        'Flame spreading is NOT modelled: how the flame front travels '
        'from the igniter to the whole injector face, the resulting '
        'pressure-rise history, and the ignition overpressure spike are '
        'outside this quasi-static energy budget.'),
    'hard_start_dynamics': (
        'Hard-start dynamics are NOT modelled: deflagration-to-detonation '
        'transition, pressure wave reflection and the structural response '
        'of the chamber are outside this model. The safe window reported '
        'here is a constant-volume ideal-gas bound, not a verdict.'),
    'hypergolic': (
        'Hypergolic ignition is NOT modelled: a hypergolic pair needs no '
        'igniter energy, so the energy path here does not apply. Its '
        'design problem is the start sequence and the fluid lead/lag, '
        'which this module does not address.'),
    'electrical': (
        'The electrical ignition train is NOT modelled: spark energy, '
        'exciter and plug design, bridgewire resistance, no-fire/all-fire '
        'currents and the safe-and-arm device are outside this model.'),
    'torch_internals': (
        'Torch igniter internals are NOT modelled: its own injector, '
        'chamber volume, throat, characteristic velocity, cooling, and '
        'the mixture ratio at which it runs (usually far off the main '
        'engine value) are outside this model. Only the propellant flow '
        'the torch must deliver is sized.'),
    'igniter_hardware': (
        'Igniter hardware is NOT sized: case diameter/length, wall '
        'thickness, nozzle/port area, charge grain geometry and the '
        'mounting are outside this model, because they depend on '
        'loading-density and layout choices this module has no basis to '
        'make.'),
    'restart': (
        'Restart and multiple-start capability is NOT modelled: charge '
        'replenishment, residue from a previous firing, and chill-down '
        'between starts are outside this model.'),
    'propellant_properties': (
        'Propellant properties are NOT computed here: specific heat, '
        'ignition temperature, flame temperature, gas molecular weight, '
        'heat release and condensed-phase fraction are all '
        'caller-supplied inputs.'),
}


# ===========================================================================
# Saf yardımcılar (analitik, tek tek test edilebilir)
# ===========================================================================
def _require_positive(value, name: str, unit: str = '') -> float:
    """Pozitif ve sonlu olma şartı; değilse İngilizce ValueError."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a positive finite number {unit}')
    if not math.isfinite(v) or v <= 0.0:
        raise ValueError(
            f'{name} must be a positive finite number {unit}; got {value!r}')
    return v


def specific_gas_constant(molecular_weight_g_mol: float) -> float:
    """Özgül gaz sabiti R = R_evrensel / MW [J/(kg.K)].

    ``hrma.constants.R_UNIVERSAL`` J/(kmol.K) birimindedir; molekül
    ağırlığı kg/kmol (= g/mol) alınır. Merkezî sabit kullanılır, yeni bir
    sayı tanımlanmaz (CODATA 2018).
    """
    mw = _require_positive(molecular_weight_g_mol,
                           'molecular_weight_g_mol', '[g/mol]')
    return R_UNIVERSAL / mw


def ignition_energy_required(*,
                             main_mass_flow_kg_s: float,
                             ignition_window_s: float,
                             specific_heat_J_kg_K: float,
                             ignition_temperature_K: float,
                             initial_temperature_K: float,
                             transfer_efficiency: float =
                             TRANSFER_EFFICIENCY_DEFAULT) -> Dict:
    """Gerekli ateşleme enerjisi [J] — Eş. (1)."""
    mdot = _require_positive(main_mass_flow_kg_s, 'main_mass_flow_kg_s',
                             '[kg/s]')
    t_win = _require_positive(ignition_window_s, 'ignition_window_s', '[s]')
    cp = _require_positive(specific_heat_J_kg_K, 'specific_heat_J_kg_K',
                           '[J/(kg.K)]')
    t_ign = _require_positive(ignition_temperature_K,
                              'ignition_temperature_K', '[K]')
    t_0 = _require_positive(initial_temperature_K, 'initial_temperature_K',
                            '[K]')
    eta = float(transfer_efficiency)
    lo, hi = TRANSFER_EFFICIENCY_VALID
    if not (lo <= eta <= hi):
        raise ValueError(
            f'transfer_efficiency {eta:g} is outside the supported '
            f'validity range {TRANSFER_EFFICIENCY_VALID} (invalid range '
            'declared - no silent extrapolation)')
    if t_ign <= t_0:
        raise ValueError(
            f'ignition_temperature_K ({t_ign:g}) must exceed '
            f'initial_temperature_K ({t_0:g}): with no temperature rise '
            'to achieve there is no ignition energy to compute')

    m_heated = mdot * t_win
    delta_t = t_ign - t_0
    e_ideal = m_heated * cp * delta_t
    return {
        'energy_J': float(e_ideal / eta),
        'energy_ideal_J': float(e_ideal),
        'heated_mass_kg': float(m_heated),
        'temperature_rise_K': float(delta_t),
        'transfer_efficiency': eta,
        'ignition_window_s': t_win,
        '_basis': (
            'E = mdot_main * t_window * cp * (T_ign - T_0) / eta_transfer '
            '(sensible-heat balance on the propellant entering the chamber '
            'during the ignition window). Latent heat of vaporisation for '
            'a liquid propellant is NOT included - supply an effective cp '
            'that carries it if it matters. ' + TRANSFER_EFFICIENCY_SOURCE),
    }


def hard_start_pressure(*,
                        main_mass_flow_kg_s: float,
                        ignition_delay_s: float,
                        free_volume_m3: float,
                        gas_molecular_weight_g_mol: float,
                        flame_temperature_K: float) -> float:
    """Birikmiş iticinin ani yanmasıyla oluşacak basınç [Pa] — Eş. (5)."""
    mdot = _require_positive(main_mass_flow_kg_s, 'main_mass_flow_kg_s',
                             '[kg/s]')
    t_delay = _require_positive(ignition_delay_s, 'ignition_delay_s', '[s]')
    v_free = _require_positive(free_volume_m3, 'free_volume_m3', '[m^3]')
    t_flame = _require_positive(flame_temperature_K, 'flame_temperature_K',
                                '[K]')
    r_gas = specific_gas_constant(gas_molecular_weight_g_mol)
    m_accum = mdot * t_delay
    return m_accum * r_gas * t_flame / v_free


def safe_ignition_window_s(*,
                           main_mass_flow_kg_s: float,
                           free_volume_m3: float,
                           gas_molecular_weight_g_mol: float,
                           flame_temperature_K: float,
                           allowable_pressure_Pa: float) -> float:
    """Güvenli ateşleme penceresi üst sınırı [s] — Eş. (5) tersine çözülür."""
    mdot = _require_positive(main_mass_flow_kg_s, 'main_mass_flow_kg_s',
                             '[kg/s]')
    v_free = _require_positive(free_volume_m3, 'free_volume_m3', '[m^3]')
    t_flame = _require_positive(flame_temperature_K, 'flame_temperature_K',
                                '[K]')
    p_allow = _require_positive(allowable_pressure_Pa,
                                'allowable_pressure_Pa', '[Pa]')
    r_gas = specific_gas_constant(gas_molecular_weight_g_mol)
    return p_allow * v_free / (r_gas * t_flame * mdot)


def torch_propellant_flow(*,
                          required_energy_J: float,
                          ignition_window_s: float,
                          torch_heat_release_J_kg: float,
                          combustion_efficiency: float = 1.0) -> float:
    """Torç ateşleyici itici debisi [kg/s] — Eş. (2)."""
    e_req = _require_positive(required_energy_J, 'required_energy_J', '[J]')
    t_win = _require_positive(ignition_window_s, 'ignition_window_s', '[s]')
    q = _require_positive(torch_heat_release_J_kg,
                          'torch_heat_release_J_kg', '[J/kg]')
    eta = float(combustion_efficiency)
    if not (0.0 < eta <= 1.0):
        raise ValueError(
            f'combustion_efficiency {eta:g} must lie in (0, 1] (invalid '
            'range declared - no silent extrapolation)')
    return e_req / (eta * q * t_win)


def pyrotechnic_charge_mass(*,
                            ignition_pressure_Pa: float,
                            free_volume_m3: float,
                            gas_molecular_weight_g_mol: float,
                            gas_temperature_K: float,
                            condensed_mass_fraction: float) -> Dict:
    """Piroteknik şarj kütlesi [kg] — Eş. (3)-(4), NASA SP-8051."""
    p_ign = _require_positive(ignition_pressure_Pa, 'ignition_pressure_Pa',
                              '[Pa]')
    v_free = _require_positive(free_volume_m3, 'free_volume_m3', '[m^3]')
    t_gas = _require_positive(gas_temperature_K, 'gas_temperature_K', '[K]')
    x_cond = float(condensed_mass_fraction)
    if not (0.0 <= x_cond < 1.0):
        raise ValueError(
            f'condensed_mass_fraction {x_cond:g} must lie in [0, 1) '
            '(invalid range declared - no silent extrapolation)')
    r_gas = specific_gas_constant(gas_molecular_weight_g_mol)
    m_gas = p_ign * v_free / (r_gas * t_gas)
    gas_fraction = 1.0 - x_cond
    return {
        'charge_mass_kg': float(m_gas / gas_fraction),
        'gas_mass_kg': float(m_gas),
        'gas_mass_fraction': float(gas_fraction),
        'specific_gas_constant_J_kg_K': float(r_gas),
        'ignition_pressure_Pa': p_ign,
        '_basis': (
            'Free-volume pressurisation criterion: m_gas = '
            'P_ign*V_free/(R*T_gas), m_charge = m_gas/(1 - X_condensed) '
            '(NASA SP-8051, "Solid Rocket Motor Igniters"; Sutton & '
            'Biblarz 9th ed., Ch. 15). Only the gas phase pressurises the '
            'chamber; the condensed fraction is slag. Quasi-static ideal '
            'gas: it does NOT model the pressure-rise history, flame '
            'spreading or heat loss to the walls. ' + IGNITION_PRESSURE_SOURCE),
    }


# ===========================================================================
# Uçtan uca boyutlandırma
# ===========================================================================
def size_igniter(*,
                 igniter_type: str,
                 chamber_free_volume_m3: float,
                 main_mass_flow_kg_s: float,
                 ignition_window_s: float,
                 propellant_specific_heat_J_kg_K: float,
                 propellant_ignition_temperature_K: float,
                 initial_temperature_K: float = 293.15,
                 transfer_efficiency: float = TRANSFER_EFFICIENCY_DEFAULT,
                 chamber_pressure_Pa: Optional[float] = None,
                 main_gas_molecular_weight_g_mol: Optional[float] = None,
                 main_flame_temperature_K: Optional[float] = None,
                 hard_start_pressure_fraction: float =
                 HARD_START_PRESSURE_FRACTION_DEFAULT,
                 torch_heat_release_J_kg: Optional[float] = None,
                 torch_combustion_efficiency: float = 1.0,
                 ignition_pressure_fraction: Optional[float] = None,
                 charge_gas_molecular_weight_g_mol: Optional[float] = None,
                 charge_flame_temperature_K: Optional[float] = None,
                 charge_condensed_mass_fraction: Optional[float] = None,
                 charge_heat_of_explosion_J_kg: Optional[float] = None,
                 charge_density_kg_m3: Optional[float] = None,
                 charge_burn_time_s: Optional[float] = None) -> Dict:
    """Torç ya da piroteknik ateşleyiciyi boyutlandırır.

    Ortak yol: gerekli ateşleme enerjisi (1) ve — ana gaz özellikleri
    verilirse — güvenli ateşleme penceresi (5).

    ``igniter_type='torch'``    -> ``torch_heat_release_J_kg`` ZORUNLU.
    ``igniter_type='pyrotechnic'`` -> şarj gaz özellikleri ve
    ``charge_condensed_mass_fraction`` ZORUNLU; ateşleme basıncı için
    ``chamber_pressure_Pa`` gerekir.

    Zorunlu girdi eksikse sayı UYDURULMAZ: ilgili blok
    ``status='not_modelled'`` ile döner ya da ValueError yükselir.
    """
    kind = str(igniter_type).strip().lower()
    if kind not in IGNITER_TYPES:
        raise ValueError(
            f"unknown igniter_type '{igniter_type}'; choose from "
            f'{list(IGNITER_TYPES)}')

    v_free = _require_positive(chamber_free_volume_m3,
                               'chamber_free_volume_m3', '[m^3]')
    validity: List[Dict] = []
    warnings: List[str] = []

    # --- ortak: gerekli enerji ---
    energy = ignition_energy_required(
        main_mass_flow_kg_s=main_mass_flow_kg_s,
        ignition_window_s=ignition_window_s,
        specific_heat_J_kg_K=propellant_specific_heat_J_kg_K,
        ignition_temperature_K=propellant_ignition_temperature_K,
        initial_temperature_K=initial_temperature_K,
        transfer_efficiency=transfer_efficiency)

    # --- ortak: güvenli ateşleme penceresi ---
    window: Dict
    if (main_gas_molecular_weight_g_mol is not None
            and main_flame_temperature_K is not None
            and chamber_pressure_Pa is not None):
        frac = float(hard_start_pressure_fraction)
        if not (frac > 0.0) or not math.isfinite(frac):
            raise ValueError(
                'hard_start_pressure_fraction must be positive and finite')
        p_allow = float(chamber_pressure_Pa) * frac
        t_max = safe_ignition_window_s(
            main_mass_flow_kg_s=main_mass_flow_kg_s,
            free_volume_m3=v_free,
            gas_molecular_weight_g_mol=main_gas_molecular_weight_g_mol,
            flame_temperature_K=main_flame_temperature_K,
            allowable_pressure_Pa=p_allow)
        p_at_window = hard_start_pressure(
            main_mass_flow_kg_s=main_mass_flow_kg_s,
            ignition_delay_s=ignition_window_s,
            free_volume_m3=v_free,
            gas_molecular_weight_g_mol=main_gas_molecular_weight_g_mol,
            flame_temperature_K=main_flame_temperature_K)
        margin = t_max / float(ignition_window_s)
        window = {
            'status': 'computed',
            'max_delay_s': float(t_max),
            'requested_window_s': float(ignition_window_s),
            'margin_ratio': float(margin),
            'allowable_pressure_Pa': float(p_allow),
            'hard_start_pressure_fraction': frac,
            'accumulated_mass_at_window_kg': float(
                float(main_mass_flow_kg_s) * float(ignition_window_s)),
            'constant_volume_pressure_at_window_Pa': float(p_at_window),
            'verdict': ('within_window' if margin >= 1.0
                        else 'exceeds_window'),
            '_basis': (
                't_max = P_allow*V_free/(R*T_flame*mdot_main): the '
                'ignition delay at which propellant accumulated in the '
                'free volume would, burning at constant volume as an '
                'ideal gas, reach the allowable pressure. '
                + HARD_START_SOURCE),
        }
        if margin < 1.0:
            warnings.append(
                f'the requested ignition window '
                f'({float(ignition_window_s) * 1e3:.0f} ms) exceeds the '
                f'hard-start bound ({t_max * 1e3:.0f} ms): propellant '
                'accumulating over that delay could, if it ignited all at '
                f'once, reach {p_at_window / 1e5:.0f} bar against an '
                f'allowance of {p_allow / 1e5:.0f} bar. Shorten the '
                'window or reduce the propellant lead.')
    else:
        missing = [n for n, v in (
            ('main_gas_molecular_weight_g_mol',
             main_gas_molecular_weight_g_mol),
            ('main_flame_temperature_K', main_flame_temperature_K),
            ('chamber_pressure_Pa', chamber_pressure_Pa)) if v is None]
        window = {
            'status': 'not_modelled',
            'reason': (
                'The safe ignition window was NOT evaluated because '
                + ', '.join(missing) + ' was not supplied. No safe/unsafe '
                'verdict is implied.'),
        }
        validity.append({
            'field': 'safe_ignition_window',
            'status': 'not_evaluated',
            'message': window['reason']})

    # --- tipe özgü yol ---
    torch = None
    pyro = None

    if kind == 'torch':
        if torch_heat_release_J_kg is None:
            raise ValueError(
                'torch_heat_release_J_kg is required for a torch igniter: '
                'the torch propellant heat release [J/kg] sets the flow '
                'needed to deliver the ignition energy. No default is '
                'assumed (no invented value).')
        mdot_torch = torch_propellant_flow(
            required_energy_J=energy['energy_J'],
            ignition_window_s=ignition_window_s,
            torch_heat_release_J_kg=torch_heat_release_J_kg,
            combustion_efficiency=torch_combustion_efficiency)
        fraction = mdot_torch / float(main_mass_flow_kg_s)
        torch = {
            'mass_flow_kg_s': float(mdot_torch),
            'total_propellant_kg': float(mdot_torch
                                         * float(ignition_window_s)),
            'burn_time_s': float(ignition_window_s),
            'power_W': float(energy['energy_J'] / float(ignition_window_s)),
            'flow_fraction_of_main': float(fraction),
            'flow_fraction_screen': list(TORCH_FLOW_FRACTION_SCREEN),
            'combustion_efficiency': float(torch_combustion_efficiency),
            'heat_release_J_kg': float(torch_heat_release_J_kg),
            '_basis': (
                'mdot_torch = E_required/(eta_combustion * Q_torch * '
                't_window); the torch runs for the whole ignition window. '
                'Only the propellant FLOW is sized - the torch injector, '
                'chamber, throat and its own mixture ratio are NOT '
                'modelled (see not_modelled.torch_internals). '
                + TORCH_FLOW_FRACTION_SOURCE),
        }
        lo, hi = TORCH_FLOW_FRACTION_SCREEN
        if not (lo <= fraction <= hi):
            validity.append({
                'field': 'torch.flow_fraction_of_main',
                'status': 'outside_screening_band',
                'message': (
                    f'torch flow is {fraction * 100.0:.2f}% of the main '
                    f'flow, outside the sanity screen '
                    f'{lo * 100.0:g}%-{hi * 100.0:g}%. The energy balance '
                    'itself is unchanged, but one of the inputs (ignition '
                    'window, transfer efficiency or torch heat release) is '
                    'likely unrealistic. ' + TORCH_FLOW_FRACTION_SOURCE)})
            warnings.append(
                f'torch flow fraction {fraction * 100.0:.2f}% of main flow '
                'falls outside the sanity screening band; check the '
                'ignition window and transfer efficiency.')

    else:  # pyrotechnic
        missing = [n for n, v in (
            ('charge_gas_molecular_weight_g_mol',
             charge_gas_molecular_weight_g_mol),
            ('charge_flame_temperature_K', charge_flame_temperature_K),
            ('charge_condensed_mass_fraction',
             charge_condensed_mass_fraction),
            ('chamber_pressure_Pa', chamber_pressure_Pa)) if v is None]
        if missing:
            pyro = {
                'status': 'not_modelled',
                'reason': (
                    'The pyrotechnic charge was NOT sized because '
                    + ', '.join(missing) + ' was not supplied. The charge '
                    'gas properties and condensed-phase fraction are '
                    'inputs: this module does not carry a charge '
                    'catalogue and will not invent one.'),
            }
            validity.append({
                'field': 'pyrotechnic.charge_mass_kg',
                'status': 'not_evaluated',
                'message': pyro['reason']})
        else:
            frac_p = (IGNITION_PRESSURE_FRACTION_DEFAULT
                      if ignition_pressure_fraction is None
                      else float(ignition_pressure_fraction))
            lo, hi = IGNITION_PRESSURE_FRACTION_VALID
            if not (lo <= frac_p <= hi):
                raise ValueError(
                    f'ignition_pressure_fraction {frac_p:g} is outside the '
                    f'supported validity range '
                    f'{IGNITION_PRESSURE_FRACTION_VALID} (invalid range '
                    'declared - no silent extrapolation)')
            frac_source = ('user-supplied ignition_pressure_fraction'
                           if ignition_pressure_fraction is not None
                           else 'default design choice (no '
                                'ignition_pressure_fraction supplied)')
            p_ign = float(chamber_pressure_Pa) * frac_p
            pyro = pyrotechnic_charge_mass(
                ignition_pressure_Pa=p_ign,
                free_volume_m3=v_free,
                gas_molecular_weight_g_mol=(
                    charge_gas_molecular_weight_g_mol),
                gas_temperature_K=charge_flame_temperature_K,
                condensed_mass_fraction=charge_condensed_mass_fraction)
            pyro['status'] = 'sized'
            pyro['ignition_pressure_fraction'] = frac_p
            pyro['ignition_pressure_source'] = frac_source
            if charge_density_kg_m3 is not None:
                rho_c = _require_positive(charge_density_kg_m3,
                                          'charge_density_kg_m3',
                                          '[kg/m^3]')
                pyro['charge_volume_m3'] = float(pyro['charge_mass_kg']
                                                 / rho_c)
            if charge_burn_time_s is not None:
                t_burn = _require_positive(charge_burn_time_s,
                                           'charge_burn_time_s', '[s]')
                pyro['burn_time_s'] = t_burn
                pyro['gas_generation_rate_kg_s'] = float(
                    pyro['gas_mass_kg'] / t_burn)
            if charge_heat_of_explosion_J_kg is not None:
                q_ex = _require_positive(charge_heat_of_explosion_J_kg,
                                         'charge_heat_of_explosion_J_kg',
                                         '[J/kg]')
                e_released = pyro['charge_mass_kg'] * q_ex
                pyro['energy_released_J'] = float(e_released)
                pyro['energy_margin_ratio'] = float(e_released
                                                    / energy['energy_J'])
                pyro['energy_basis'] = (
                    'Energy released = m_charge * heat_of_explosion, '
                    'compared with the ignition energy required by the '
                    'sensible-heat balance. A ratio above 1 means the '
                    'charge sized by the free-volume criterion also '
                    'carries enough energy; the two criteria are '
                    'INDEPENDENT and the governing one is whichever '
                    'demands more.')
                if e_released < energy['energy_J']:
                    warnings.append(
                        'the charge sized by the free-volume criterion '
                        f'releases {e_released:.0f} J, less than the '
                        f'{energy["energy_J"]:.0f} J the heating balance '
                        'requires: the energy criterion governs, so size '
                        'the charge from energy instead.')
            else:
                validity.append({
                    'field': 'pyrotechnic.energy_released_J',
                    'status': 'not_evaluated',
                    'message': (
                        'The charge energy release was NOT checked against '
                        'the required ignition energy because '
                        'charge_heat_of_explosion_J_kg was not supplied. '
                        'The charge mass above satisfies the free-volume '
                        'pressurisation criterion ONLY.')})

    return {
        'igniter_type': kind,
        'inputs': {
            'chamber_free_volume_m3': v_free,
            'main_mass_flow_kg_s': float(main_mass_flow_kg_s),
            'ignition_window_s': float(ignition_window_s),
            'initial_temperature_K': float(initial_temperature_K),
            'chamber_pressure_Pa': (None if chamber_pressure_Pa is None
                                    else float(chamber_pressure_Pa)),
        },
        'energy': energy,
        'safe_window': window,
        'torch': torch,
        'pyrotechnic': pyro,
        'validity': validity,
        'warnings': warnings,
        'not_modelled': dict(NOT_MODELLED),
    }
