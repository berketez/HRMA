"""
Regenerative Cooling 1D Station-Marching Module.

Analysis-mode (NOT auto-sizing) one-dimensional regenerative cooling model for
liquid / hybrid rocket thrust chambers and nozzles. The channel geometry
(number of channels, width, height) and the inner-liner thickness are USER
INPUTS — this module solves the coupled gas-side / wall / coolant thermal and
hydraulic problem for the geometry you give it; it does not iterate the channel
dimensions to hit a target (that is a separate design-optimization concern, an
R&D decision left to the engineer).

Physics and references
----------------------
Gas side (hot wall convection):
  - Bartz convective coefficient h_g(x) is IMPORTED from
    ``HeatTransferAnalyzer._bartz_coefficient`` (Bartz 1957; Sutton & Biblarz,
    "Rocket Propulsion Elements", 9th ed., Eq. 8-22, SI-consistent form). The
    correlation is NOT re-implemented here — single source of truth, same
    convention as ``HeatTransferAnalyzer.analyze_axial_profile`` and
    ``nozzle_flow_1d``.
  - Driving temperature is the adiabatic-wall (recovery) temperature Taw(x)
    (``HeatTransferAnalyzer._adiabatic_wall_temperature``), NOT the stagnation
    temperature. Huzel & Huang, "Modern Engineering for Design of
    Liquid-Propellant Rocket Engines", AIAA, Ch. 4 (Eq. 4-10 ff.);
    Sutton & Biblarz 9th ed. Ch. 8.

Coolant side (forced convection in the channels):
  - Dittus-Boelter correlation for turbulent forced convection in ducts,
    HEATING of the fluid (exponent n = 0.4):
        Nu = 0.023 * Re^0.8 * Pr^0.4
    Validity band (Incropera & DeWitt, "Fundamentals of Heat and Mass
    Transfer", 6th ed., Eq. 8.60): fully-developed turbulent flow,
    Re >= 1e4, 0.6 <= Pr <= 160, L/D >= 10. The correlation is applied per
    station with local bulk properties; a warning is raised where Re drops
    below the turbulent floor. Rectangular-channel hydraulic diameter
    D_h = 4*A_c / P_wet = 2*w*h/(w+h) (Incropera Ch. 8).
  - This is the classic first-cut regenerative-cooling coolant correlation
    (Huzel & Huang Ch. 4). For the single-phase LIQUID coolants (water,
    RP-1) the wall-to-bulk viscosity ratio IS applied as the Sieder-Tate
    factor (mu_b/mu_w)^0.14 at the solved coolant-side wall temperature
    (NASA SP-125 Eq. 4-23, p. 106; V301/L-REJ, 26 Oct 2026). Entrance and
    curvature enhancements are NOT applied (conservative).

Wall conduction (radial, thin-liner flat-plate approximation):
  - The inner liner is treated as a flat plate of thickness t_w and
    conductivity k_w (from ``hrma.data.materials_db``). The series thermal
    circuit per unit gas-side area is
        q = (Taw - T_coolant) / ( 1/h_g + t_w/k_w + 1/h_c )
    with the hot- and cold-wall temperatures back-computed from q:
        T_wall_hot  = Taw       - q / h_g
        T_wall_cold = T_coolant + q / h_c
    (Huzel & Huang Ch. 4 one-dimensional wall model; Sutton & Biblarz 9th ed.
    Ch. 8). The thin-wall flat-plate approximation is valid when t_w << r_wall
    The coolant-side heat-transfer area is NOT taken equal to the gas-side
    area: on EVERY coolant path (water, RP-1, methane, hydrogen) the channel
    bottom plus the two side walls (lands as straight fins, ``fin_area_ratio``)
    carry the heat, A_eff/A_gas = (w + 2*eta_f*h)/pitch (V301/L-REJ; before
    26 Oct 2026 the water/RP-1 path assumed A_eff/A_gas = 1).

Coolant temperature march (station-to-station enthalpy balance):
  - Steady thin-wall energy balance: all gas-side heat over a wall segment is
    absorbed by the coolant, dQ = q * dA (dA = local circumference * slant
    length). The coolant bulk temperature is advanced by
        dT = dQ / (mdot * cp(T_bulk)).
    Default flow arrangement is COUNTERFLOW: the coolant enters at the nozzle
    exit and flows toward the throat and chamber (opposite the combustion gas),
    the standard regenerative arrangement (Huzel & Huang Ch. 4). Co-flow is
    also selectable.

Coolant pressure drop (Darcy-Weisbach + Haaland friction factor):
  - dP = f * (ds / D_h) * (rho * V^2 / 2)   (Darcy-Weisbach; White, "Fluid
    Mechanics", 7th ed., Eq. 6.10).
  - Turbulent friction factor from the Haaland (1983) explicit approximation
    to the Colebrook equation:
        1/sqrt(f) = -1.8 * log10[ (6.9/Re) + (eps/D_h/3.7)^1.11 ]
    (White 7th ed. Eq. 6.49; accurate to ~2 % vs Colebrook over the turbulent
    range). Laminar (Re < 2300) uses f = 64/Re (White Eq. 6.12).

Coolant properties:
  - RP-1 and water are supported via small temperature-dependent property
    tables (density, cp, thermal conductivity, viscosity). Water values are
    saturated-liquid data from Incropera & DeWitt 6th ed. Table A.6. RP-1
    values are approximate engineering compilations (Huzel & Huang App.;
    NASA RP-1 property data; NIST). RP-1 numbers carry a stated uncertainty
    band and are tagged 'approximate'.
  - If CoolProp is installed it is used for WATER (fluid 'Water') at the local
    (T, P) state; RP-1 is a multi-component fuel not represented as a single
    CoolProp fluid, so its internal table is always used. Property source is
    selectable and can be forced to the internal table for reproducibility.

Supercritical methane / hydrogen coolants (added 2026-07-22):
  - ``coolant='methane'`` and ``coolant='hydrogen'`` are supported with FULL
    (T, P)-dependent properties from CoolProp (Bell et al. 2014, Ind. Eng.
    Chem. Res. 53(6)): methane EOS Setzmann & Wagner (1991, J. Phys. Chem.
    Ref. Data 20), hydrogen as PARA-hydrogen (Leachman et al. 2009, J. Phys.
    Chem. Ref. Data 38 — rocket-grade LH2 is >99 % para at NBP). CoolProp is
    MANDATORY for these coolants: there is no internal table and no constant
    fallback (fabricated-value guard); an out-of-range state raises an
    explicit ValueError.
  - The coolant march for these fluids is ENTHALPY based:
        h2 = h1 + dQ/mdot,   T = T(P, h)
    instead of dT = dQ/(mdot*cp). Near the pseudo-critical temperature the
    cp(T) peak (e.g. CH4: T_pc ~ 199-252 K for 60-300 bar) makes the cp form
    inaccurate; the enthalpy form is exact for steady single-phase flow.
  - Coolant-side heat transfer at supercritical pressure uses the Jackson
    forced-convection correlation with wall-to-bulk property-ratio
    corrections (Jackson & Hall 1979, in Kakac & Spalding eds., "Turbulent
    Forced Convection in Channels and Bundles", Vol. 2; restated in Jackson
    2013, Nucl. Eng. Des. 264):
        Nu_b = 0.0183 Re_b^0.82 Pr_b^0.5 (rho_w/rho_b)^0.3 (cp_bar/cp_b)^n
    with cp_bar = (h_w - h_b)/(T_w - T_b) and the piecewise n exponent based
    on T_b, T_w and the pseudo-critical temperature T_pc (cp-maximum at the
    local pressure). This correlation family is the standard engineering
    model for supercritical-methane rocket cooling channels (e.g. Urbano &
    Nasuti 2013, J. Thermophys. Heat Transfer 27(2)). Because Nu depends on
    the cold-wall temperature, the station wall balance solves the coupled
    (h_g, h_c, T_wall_hot, T_wall_cold) fixed point with damping.
  - Coolant-side area on this path uses the channel-land EXTENDED-SURFACE
    (fin) model (``fin_area_ratio``, default on via ``fin_effect=True``):
    the two channel side walls act as straight rectangular fins,
    eta_f = tanh(mL)/(mL), m = sqrt(2 h_c/(k_w t_land)) (Incropera &
    DeWitt 6th ed. Ch. 3.6; lands-as-fins treatment per Huzel & Huang
    Ch. 4). V301/L-REJ: the SAME function and the same pitch/land geometry
    are applied on the water/RP-1 path too (one method,
    ``RegenCooling._fin_ratio``).
  - Channel pressure drop adds the ACCELERATION (momentum) term to the
    Darcy-Weisbach friction term:
        dP_acc = G^2 * (1/rho_out - 1/rho_in)
    (1D steady momentum balance, constant-area duct; Collier & Thome,
    "Convective Boiling and Condensation", 3rd ed., Ch. 2).
  - If the local channel pressure is BELOW the coolant critical pressure the
    solver falls back to Dittus-Boelter and checks the local saturation
    temperature: bulk or cold-wall temperatures at/near T_sat raise explicit
    boiling-risk warnings (the model itself remains single phase — boiling
    is NOT modelled, it is flagged).

Integration API (for the liquid-engine chain; kept module-local here):
  - Inputs: coolant + coolant_mdot [kg/s] + coolant_inlet_temp [K] +
    coolant_inlet_pressure [Pa], channel geometry (n_channels, width, height,
    wall_thickness, wall_material, roughness), nozzle geometry (throat/exit
    diameter or expansion ratio) and the gas-side state (chamber P/T, gamma,
    MW or a full ``motor_data`` dict — Bartz flux is computed internally from
    the shared HeatTransferAnalyzer single source).
  - Call ``RegenCooling(...).solve()``. Outputs: ``summary`` block with
    coolant_exit_temp_K (T_out), coolant_exit_pressure_bar (P_out),
    max_wall_hot_K (Twall_max), pressure-drop split
    (friction/acceleration), warnings list; plus per-station arrays
    (x_mm, T_wall_hot_K, T_wall_cold_K, T_coolant_K, P_coolant_bar, q_MW_m2,
    velocity_m_s, coolant enthalpy for methane/hydrogen).

Coking:
  - RP-1 begins to coke (form carbon deposits) when the fuel-side (cold) wall
    temperature exceeds ~561 K. A warning is raised when any station's
    coolant-side wall temperature exceeds this threshold. Huzel & Huang Ch. 4.

Units: SI throughout the class API (Pa, K, m, kg/s). Repo-style ``motor_data``
dictionaries (chamber_pressure in bar) are supported via ``from_motor_data``.
User-visible strings are English; inline comments may be Turkish.
"""

import math
from typing import Dict, List, Optional

import numpy as np

# Tek kaynak: Bartz korelasyonu + gaz özellikleri + alan-Mach çözücü
# heat_transfer_analysis'ten İTHAL edilir (kopya yok — parametre tutarlılığı).
from hrma.analysis.heat_transfer_analysis import (
    HeatTransferAnalyzer, GAMMA_REPO_DEFAULT, _guard_gamma_band)

from hrma.data.materials_db import get_material, temperature_limits
from hrma.utils import input_guard

# CoolProp opsiyoneldir (bundle'da var); yoksa dahili tablolara düşülür.
try:  # pragma: no cover - ortam bağımlı
    from CoolProp.CoolProp import PropsSI as _CP_PropsSI
    _HAS_COOLPROP = True
except Exception:  # pragma: no cover
    _CP_PropsSI = None
    _HAS_COOLPROP = False

__all__ = [
    'RegenCooling',
    'dittus_boelter_nu',
    'hydraulic_diameter_rect',
    'haaland_friction_factor',
    'darcy_weisbach_dp',
    'water_properties',
    'rp1_properties',
    'RP1_COKING_TEMP_K',
    'RP1_COKING_LIMIT_TEMP_K',
    'RP1_COKING_BASIS',
    'jackson_nu',
    'jackson_exponent_n',
    'pseudocritical_temperature',
    'acceleration_dp',
    'fin_area_ratio',
    'sieder_tate_factor',
    'SIEDER_TATE_EXPONENT',
    'SIEDER_TATE_BASIS',
    'SUPERCRITICAL_COOLANT_FLUIDS',
    'BOILING_MARGIN_K',
    'COOLING_CHANNEL_LAND_M',
    'COOLING_CHANNEL_LAND_BASIS',
    'CHANNEL_FIT_BASIS',
    'channel_fit_limit',
    'carbon_deposit_resistance',
    'carbon_deposit_envelope',
    'CARBON_DEPOSIT_BASIS',
    'CARBON_DEPOSIT_SIGMA_TWG_OVER_TC',
]


# ---------------------------------------------------------------------------
# ÖH A2 sivi-sogutma · F-17 (CW-F2b + CW-F3) — KANAL SIĞMA ÖLÇÜTÜNÜN TEK TANIMI
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (docs/scofield/raw/OH/A2/sivi-sogutma/a1/once/olcum.json, taban
# 68c55a27): aynı geometride İKİ ayrı sığma ölçütü vardı —
#   * sıvı motor (``_cooling_channel_geometry``): gaz tarafı İÇ boğaz çevresi
#     pi*d_t, kaburgalı adım (w + s) -> 30,8 mm boğazda n_geom = 21;
#   * bu modül (``solve``): kanal TABANI çevresi 2*pi*(r_t + t_w), kaburgasız
#     (yalnız N*w).
# Biri fazla tutucu (kanalların oturduğu yarıçapı değil gaz yüzeyini
# ölçüyor), öteki fazla gevşek (kaburgayı saymıyor). Formun 80 ön-dolgusu
# ikisini de aşıyordu ve çözücü hesaba 80 ile devam ediyordu.
#
# r_ref HÜKMÜ (birincil kaynakla doğrulandı): frezeli kanallı yapıda kanallar
# sıcak cidarın (iç kabuk / liner) DIŞ yüzüne açılır ve dıştan kapatılır —
# NASA SP-8087 "Liquid Rocket Engine Fluid-Cooled Combustion Chambers"
# (1972): s. 1 rejeneratif soğutma "around the outer surface of the wall to
# be cooled"; s. 26 kanal-cidar yapısında soğutucu geçitleri "integral with
# the inner shell", dış kabuk elektroform nikel; s. 58 "spin liners with
# milled channels ... electroformed or brazed closures". Kanal sayısını
# sınırlayan çevre bu yüzden kanal TABANININ çevresidir:
#     r_ref = r_gaz + t_sıcak_cidar,   N·(w + s) <= 2·pi·r_ref
# (sabit genişlikli kanal + radyal kaburga: kaburga dışa doğru genişler,
# bağlayıcı kesit en küçük yarıçaptır, yani kanal tabanı; eksenel olarak da
# en küçük gaz yarıçapı boğazdır). SP-8087 kanal SAYISI için formül vermez;
# yukarıdaki eşitsizlik yalnız çevre geometrisidir. Huzel & Huang
# (NASA SP-125 / AIAA 1992) Böl. 4 bu kulvarda AÇILAMADI (belge boyutu
# okuma sınırını aştı) -> ondan bir denklem numarası ATFEDİLMEZ.
COOLING_CHANNEL_LAND_M = 1.5e-3

#: Kaburga (land) genişliğinin künyesi — F-10 ilkesi: sayı kaynağıyla durur.
#: Değerin KENDİSİ kaynaklı değil (kaynak doğrulanmadı); kaynaklı olan alt
#: sınırdır: NASA sözleşme raporu NAS8-98042 (Non-Toxic Orbiter OMS Engine
#: Technology Program, Final Report, 6 Ocak 1999, s. 6) geleneksel frezeli
#: tasarım için kanal ve kaburga genişliğini en az 0.035 inç (0,889 mm) ile
#: sınırlıyor. 1,5 mm bu alt sınırın üstünde, yani imalat açısından tutucu
#: tarafta (daha az kanal) bir TASARIM KABULÜDÜR.
COOLING_CHANNEL_LAND_BASIS = (
    'channel land (rib) width 1.5 mm between adjacent channels: an ASSUMED '
    'design value, not taken from a table (source for the value itself: '
    'NOT VERIFIED). The verified bound is the minimum: channel and land '
    'widths of a conventional milled-slot chamber were limited to a minimum '
    'of 0.035 in (0.889 mm) in NASA contract NAS8-98042 (Non-Toxic Orbiter '
    'OMS Engine Technology Program, Final Report, 1999, p. 6); 1.5 mm sits '
    'above that minimum, i.e. on the conservative side (fewer channels)')

#: Sığma ölçütünün künyesi (hangi yarıçap, neden).
CHANNEL_FIT_BASIS = (
    'N * (w + s) <= 2*pi*(r_gas + t_hot_wall): milled channels sit on the '
    'OUTER surface of the hot-gas wall and are closed from outside (NASA '
    'SP-8087, 1972, pp. 1, 26, 58), so the circumference that limits the '
    'channel count is the channel-base circumference at the throat (the '
    'smallest gas-side radius); constant-width channels with radial lands '
    'bind at that smallest radius. w = channel width, s = land width. '
    'SP-8087 gives no channel-count formula: the inequality is the '
    'circumference geometry itself')


def channel_fit_limit(gas_side_radius_m: float, hot_wall_thickness_m: float,
                      channel_width_m: float,
                      land_width_m: float = COOLING_CHANNEL_LAND_M) -> Dict:
    """Kanal sığma sınırı — TEK TANIM (sıvı motor ve bu modül buradan okur).

    Döner: ``{'n_max', 'reference_radius_m', 'reference_circumference_m',
    'pitch_m', 'channel_width_m', 'land_width_m', 'hot_wall_thickness_m',
    'gas_side_radius_m', 'basis'}``. ``n_max`` en büyük N'dir ki
    ``N * (w + s) <= 2*pi*(r_gaz + t_cidar)``; kayan nokta kenarında da bu
    eşitsizlik SAĞLANIR (``n_max·p <= c < (n_max+1)·p`` düzeltmesi —
    Lean ``channelCount_le_floor`` ile aynı önerme).

    Girdi pozitif ve sonlu değilse ``ValueError`` (sayı uydurulmaz).
    """
    degerler = {'gas_side_radius_m': gas_side_radius_m,
                'hot_wall_thickness_m': hot_wall_thickness_m,
                'channel_width_m': channel_width_m,
                'land_width_m': land_width_m}
    for ad, deger in degerler.items():
        try:
            x = float(deger)
        except (TypeError, ValueError):
            raise ValueError(f'{ad} must be a positive finite number [m]; '
                             f'got {deger!r}')
        # t_cidar = 0 anlamlı değil (kanal gaz yüzüne açılmaz); hepsi > 0.
        if not (math.isfinite(x) and x > 0.0):
            raise ValueError(f'{ad} must be a positive finite number [m]; '
                             f'got {deger!r}')
    r_gaz = float(gas_side_radius_m)
    t_w = float(hot_wall_thickness_m)
    w = float(channel_width_m)
    s = float(land_width_m)
    r_ref = r_gaz + t_w
    c_ref = 2.0 * math.pi * r_ref
    p = w + s
    n = int(math.floor(c_ref / p))
    # Kayan nokta kenarı: bölme yuvarlaması tabanı bir kaydırabilir; tanım
    # (n·p <= c) doğrudan sınanarak düzeltilir.
    while n > 0 and n * p > c_ref:
        n -= 1
    while (n + 1) * p <= c_ref:
        n += 1
    return {
        'n_max': n,
        'gas_side_radius_m': r_gaz,
        'hot_wall_thickness_m': t_w,
        'reference_radius_m': r_ref,
        'reference_circumference_m': c_ref,
        'channel_width_m': w,
        'land_width_m': s,
        'pitch_m': p,
        'basis': CHANNEL_FIT_BASIS,
    }

def _ozgul_isi_orani(md):
    """(γ, γ'nın geldiği alan) — ÖH D21 / B3-13(c).

    Okuma sırası ``gamma`` -> ``gamma_avg`` -> depo varsayılanıdır; üç
    tüketici modül (bu dosya, ``regen_cooling``, ``heat_transfer_analysis``)
    aynı sırayı kullanır ve aynı künyeyi üretir.
    """
    ham = md.get('gamma')
    if ham is not None:
        return float(ham), 'gamma'
    ham = md.get('gamma_avg')
    if ham is not None:
        return float(ham), (
            "gamma_avg (producer: combustion_analysis performance.gamma_avg "
            "— this is the CHAMBER gamma, not an average)")
    return GAMMA_REPO_DEFAULT, 'repo_default'


# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
# RP-1 koklaşma (coking) UYARI eşiği — ÖH KU (KU-K5, 6 Eki 2026) künyesi
# düzeltildi; DEĞER DEĞİŞMEDİ, iki kademe BEYAN edilir:
#   * 561 K = birikim BAŞLANGICI (uyarı kademesi): NASA CR-168277 (1983)
#     bakır tüpte RP-1 birikimini 560-750 K'de ölçer (alt uç; SP-S1 notu,
#     PDF s. 6); NASA SP-125 (Huzel & Huang 1967) Örnek 4-4 soğutucu yanı
#     cidarını 1000 °R ≈ 556 K SEÇER (s. 109-110) — kitapta bir "eşik"
#     cümlesi yoktur (SP-H1 K16). Eski künye "H&H Böl. 4" eşik iddiasıydı.
#   * 728 K = SINIR kademesi: NASA SP-8087 (1972) §3.1.1.5.4 s. 62 — RP-1
#     sıvı cidar sıcaklığı 850 °F (728 K) üstünde işletilmez (yerel metinden
#     doğrulandı).
# V301/L-KABUK (ana model kararı, 27 Eki): iki kademe ARTIK KODDA.
#   * ``RP1_COKING_LIMIT_TEMP_K`` = 728 K HÜKÜM eşiğidir: aşılırsa
#     ``coking = True`` ve ileti "SP-8087 RP-1 cidar sıcaklığı tasarım
#     ölçütü aşıldı" (UNSAFE bu ölçüte uygunsuzluk anlamında).
#   * ``RP1_COKING_TEMP_K`` = 561 K yalnız UYARI eşiğidir
#     (``coking_risk = True``): deneysel bulgulara (CR-168277) dayalı
#     yazılım uyarı eşiği; tek başına UNSAFE/CRITICAL üretmez. SP-125
#     Örnek 4-4'ün 556 K'si bir tasarım seçimidir, eşiğin kanıtı değildir.
#   * 728 K altı "birikimsiz" ya da "güvenli" DEMEK DEĞİLDİR (künye).
RP1_COKING_TEMP_K = 561.0
RP1_COKING_LIMIT_TEMP_K = 728.0
RP1_COKING_BASIS = (
    f'RP-1 coolant-side wall temperature, two tiers: {RP1_COKING_LIMIT_TEMP_K:.0f}'
    ' K is the design criterion of NASA SP-8087 (1972) sec. 3.1.1.5.4 p. 62 '
    '("do not operate with liquid-wall temperatures above 850 F (728 K) for '
    'RP-1") - above it the design does not meet that criterion; '
    f'{RP1_COKING_TEMP_K:.0f} K is a deposit-risk WARNING level of this '
    'software, based on experimental findings (NASA CR-168277: deposits in '
    'copper tubes at 560-750 K) that must be validated for the application '
    'conditions; it does not by itself make the design unsafe. Staying below '
    f'{RP1_COKING_LIMIT_TEMP_K:.0f} K does NOT mean the wall stays free of '
    'deposits or is safe.')

# ÖH KU H-11 (KU-30, KARS-IS Bulgu 10) — RP-1 KRİTİK ISI AKISI EKRANI.
# Yalnız kritik-altı istasyonda UYARI (yeni alan devirde); hiçbir çözülen
# sayı değişmez. Kaynaklar:
#   * RP-1 kritik basıncı 2,21 MPa: Huber vd. 2009 (NIST, Energy & Fuels 23)
#     Tablo 3, RP-1 vekil karışımı (KARS-IS notunun okuması; bu ajan sayfayı
#     açmadı). Bağımsız çapraz: Sutton & Biblarz 9. bs. Tablo 8-5 s. 320
#     kerosen 2,0 MPa (yerel metinden doğrulandı; ~%10 uyumlu).
#   * Kerosen çekirdekli kaynama q_max 2,3-6,4 MW/m²: Sutton & Biblarz 9. bs.
#     Tablo 8-5 s. 320 — YALNIZ 0,689-1,38 MPa ve 1-8,5 m/s, 297 K için
#     tablolanmış (yerel metinden doğrulandı). Ekran tablonun EN DÜŞÜK
#     değerini kullanır (muhafazakâr); tablo zarfı dışında hesap yapılmaz.
#   * %80 marjı: NASA SP-8087 (1972) s. 61 — ısı akısı sınırlı sistemleri
#     ortalama burnout akısının %80'inin altında işletmek (yerel metinden
#     doğrulandı).
#   * Süperkritik basınçta kaynama yoktur; klasik burnout uygulanmaz, sınır
#     ısıl bozunma/koklaşmadır (SP-125 s. 105-106; KARS-IS notu).
#   * Zarfın DÖRT kenarı (denetim Ş-1, 6 Eki): Tablo 8-5 kerosen çekirdekli
#     kaynama satırları yalnız 0,689 ve 1,38 MPa basınçta, 1 ve 8,5 m/s
#     hızda verilir (kitap s. 320 = PDF s. 344; yerel metinden yeniden
#     doğrulandı). Alt basınç ve üst hız sınırı da zarfa katılır; bu
#     aralıkların dışındaki istasyonda oran YAZILMAZ (dış değerleme yok).
#   * RP1_CRITICAL_PRESSURE_PA YALNIZ bu uyarıda kullanılır; hiçbir hükme
#     bağlanmaz. water_hammer.py RP-1 'critical_pressure_Pa'yı BİLEREK
#     taşımıyor (ÖH D19 / P5B3-08, parti bağımlı sözde-kritik değer; rejim
#     hükmü fail-closed). İki karar arasındaki gerilim kayıtlıdır; tek kaynak
#     kararı Berke'nindir (bekçi: tests/test_ku_h_q5.py).
RP1_CRITICAL_PRESSURE_PA = 2.21e6
KEROSENE_QMAX_TABLE_MIN_W_M2 = 2.3e6
KEROSENE_QMAX_TABLE_P_MIN_PA = 0.689e6
KEROSENE_QMAX_TABLE_P_MAX_PA = 1.38e6
KEROSENE_QMAX_TABLE_V_MIN_M_S = 1.0
KEROSENE_QMAX_TABLE_V_MAX_M_S = 8.5
BURNOUT_HEAT_FLUX_MARGIN = 0.8

# Laminer/türbülan geçiş Reynolds sayısı (boru akışı, White 7. baskı Böl. 6).
RE_LAMINAR_MAX = 2300.0
# Dittus-Boelter türbülan geçerlilik tabanı (Incropera 6. baskı Eq. 8.60).
RE_TURBULENT_FLOOR = 1.0e4

# Rejeneratif soğutma marşının kendi istasyon klampı (testlerle çapalı 20/50).
# nozzle_flow_1d'nin 30/60 klampından BİLEREK farklı — ayrı modül, ayrı
# ayrıklaştırma politikası; ad çakışması olmasın diye REGEN_ önekiyle.
REGEN_N_STATIONS_MIN = 20
REGEN_N_STATIONS_MAX = 50

#: ÖH A2 sivi-sogutma · 7. tur (F-17 ilkesi: kaynaksız varsayılan ADSIZ
#: kalmaz). ``RegenCooling(n_channels=...)`` Python API'sinin kolaylık
#: varsayılanı. Bir TASARIM DEĞERİ DEĞİLDİR: hiçbir boyutlandırmadan gelmez.
#: HRMA'nın ürün yolları bu sayıyı KULLANMAZ — ``/api/regen-cooling`` ucu
#: n_channels'ı zorunlu ister (adlı 400), sıvı motorun iki marşı kendi
#: boyutlandırdığı N'yi AÇIKÇA geçirir (bekçi: tests/test_d37_sivi_t7.py,
#: AST ile her ürün çağrısında ``n_channels=`` anahtarı). Değer, eski örtük
#: ``n_channels=64`` imzasının aynısıdır; yalnız betik/test kolaylığı için
#: durur ve bu cümleyle adlandırılmıştır.
REGEN_N_CHANNELS_API_DEFAULT = 64

# ÖH Z5S / PK5 (P4B2-11) — ÇÖZÜNÜRLÜK TABANI: her geometrik bölüme (kamara
# gövdesi / konverjan / diverjan) verilen EN AZ aralık sayısı. Fizik sabiti
# DEĞİLDİR: tek aralıklı bir bölüm, akısı tek bir istasyondan gelen tek bir
# şeritle temsil edilir, yani hiç çözülmemiştir.
# ÖLÇÜLEN kusur: ε=25 lülede konverjanın payı (eksenel %5,47, ıslak alan
# %2,68) küçük olduğu için oransal dağıtım throat_index=1 üretiyordu
# (n=20/30/40); konverjan alanın %2,6'sı ısının %9,2'sini taşıdığı hâlde tek
# segmentte kalıyordu. ``throat_index >= 2`` garantisini SAĞLAYAN bu tabandır.
REGEN_MIN_INTERVALS_PER_SEGMENT = 2

# ÖH Z5S / PK5 (P4B2-11) — MARŞ ŞEMASI: segment ısısı q'nun İKİ UÇ
# istasyonunun ortalamasıyla (trapez, ikinci mertebe) alınır; aşağı-akım
# istasyonunun akısı soğutucu sıcaklığına bağlı olduğu için marş bir sabit
# nokta iterasyonuyla kapatılır. İlk geçiş yukarı-akım (öngörü), sonraki
# geçişler düzeltmedir. Yakınsama ölçütü toplam ısıdaki bağıl değişimdir.
REGEN_MARCH_MAX_PASSES = 8
REGEN_MARCH_TOL = 1.0e-10
# İstasyon dengesi sabit nokta iterasyonunun BAŞLANGIÇ tahmini için kaydın
# ham ``allowable_temperature`` alanı yoksa kullanılan yedek (K). HÜKÜM EŞİĞİ
# DEĞİLDİR (hüküm eşikleri ``materials_db.temperature_limits``ten, §28-31
# (c)); bugün 24 kaydın hepsinde alan var, yedek kullanılmıyor.
REGEN_SEED_ALLOWABLE_DEFAULT_K = 1000.0

FLOW_COUNTERFLOW = 'counterflow'  # soğutucu çıkış -> boğaz -> kamara (varsayılan)
FLOW_COFLOW = 'coflow'            # soğutucu kamara -> boğaz -> çıkış

# Süperkritik-yetenekli soğutucular -> CoolProp akışkan adları.
# Metan: Setzmann & Wagner (1991) EOS. Hidrojen: PARA-hidrojen
# (Leachman ve ark. 2009) — roket LH2'si NBP'de >%99 para izomeridir;
# normal (%75 orto) hidrojen değil.
SUPERCRITICAL_COOLANT_FLUIDS = {
    'methane': 'Methane',
    'hydrogen': 'ParaHydrogen',
}

# Kaynama-riski tarama marjı [K]: kritik-altı basınçta yığın sıcaklığı yerel
# Tsat'a bu kadar yaklaşınca uyarı üretilir. Mühendislik tarama eşiğidir
# (fiziksel sabit değil); uyarı metninde açıkça belirtilir.
BOILING_MARGIN_K = 10.0

#: İNCE-CİDAR (düz levha) İLETİM ZARFI — ÖH D15 / P4B2-09.
#: Modül künyesi (:52-55) cidar iletimini "thin flat-plate radial conduction"
#: diye ilan eder ve ``r_cond = wall_thickness / k_wall`` kullanır. Silindirik
#: cidarın doğrusu (sıcak yüzey alanına indirgenmiş) ``r1*ln(r2/r1)/k``'dır;
#: bağıl hata 1 − r1·ln(r2/r1)/t_w ile ölçülür ve YALNIZ t_w/r1 oranına
#: bağlıdır.
#: ÖLÇÜLDÜ (31 Ağustos 2026, taban e88d096; boğaz yarıçapı 50 mm):
#:     t_w =  1 mm ->  %0,99   t_w =  5 mm ->  %4,69
#:     t_w = 20 mm -> %15,88   t_w = 60 mm -> %34,30
#: %2 altı, ısı-transferi korelasyonlarının kendi saçılımının (Bartz ±%20,
#: Dittus-Boelter ±%25) çok altındadır: sessiz kalmak dürüsttür. %10 üstü,
#: cidar sıcaklığını mühendislik hükmünü değiştirecek kadar kaydırır
#: (ölçüldü: t_w 1 -> 20 mm ile T_w,max 882,31 -> 1774,16 K) ve künyenin
#: kendi geçerlilik koşulunun DIŞIDIR — orada sayı yayımlanmaz.
WALL_CURVATURE_WARN_REL = 0.02
WALL_CURVATURE_MAX_REL = 0.10

# Pseudo-kritik sıcaklık önbelleği: (akışkan, 0.5 bar kovalı basınç) -> T_pc.
_PSEUDOCRITICAL_CACHE: Dict = {}

# ---------------------------------------------------------------------------
# Soğutucu özellik tabloları (sıcaklığa bağlı, doğrusal interpolasyon)
# ---------------------------------------------------------------------------
# Su — doymuş sıvı (Incropera & DeWitt 6. baskı, Tablo A.6).
# Sıra: T[K], rho[kg/m^3], cp[J/kg/K], k[W/m/K], mu[Pa*s]
_WATER_TABLE = np.array([
    [280.0, 1000.0, 4198.0, 0.582, 1.422e-3],
    [300.0,  997.0, 4179.0, 0.613, 0.855e-3],
    [320.0,  989.0, 4180.0, 0.640, 0.577e-3],
    [340.0,  979.0, 4188.0, 0.660, 0.420e-3],
    [360.0,  967.0, 4203.0, 0.674, 0.324e-3],
    [380.0,  953.0, 4226.0, 0.683, 0.260e-3],
    [400.0,  937.0, 4256.0, 0.688, 0.217e-3],
])

# RP-1 — YAKLAŞIK mühendislik derlemesi (Huzel & Huang App.; NASA RP-1 veri
# derlemeleri; NIST). Bant: rho +/-2 %, cp +/-8 %, k +/-15 %, mu +/-25 %.
# Tek kaynaklı, kesin değil — 'approximate' etiketli.
_RP1_TABLE = np.array([
    [290.0, 806.0, 1880.0, 0.140, 1.70e-3],
    [320.0, 784.0, 1980.0, 0.135, 1.00e-3],
    [350.0, 762.0, 2075.0, 0.130, 0.68e-3],
    [400.0, 724.0, 2245.0, 0.122, 0.42e-3],
    [450.0, 686.0, 2415.0, 0.114, 0.30e-3],
    [500.0, 648.0, 2585.0, 0.106, 0.23e-3],
])


def _interp_table(table: np.ndarray, temperature: float) -> Dict[str, float]:
    """Bir özellik tablosunda (uçlarda klamplı) doğrusal interpolasyon."""
    t_col = table[:, 0]
    t = float(min(max(temperature, t_col[0]), t_col[-1]))
    rho = float(np.interp(t, t_col, table[:, 1]))
    cp = float(np.interp(t, t_col, table[:, 2]))
    k = float(np.interp(t, t_col, table[:, 3]))
    mu = float(np.interp(t, t_col, table[:, 4]))
    return {
        'density': rho,
        'cp': cp,
        'conductivity': k,
        'viscosity': mu,
        'prandtl': cp * mu / k,
        'clamped': bool(temperature < t_col[0] or temperature > t_col[-1]),
        # DÜZELTME (v2.6.2, fizik denetimi F057): tablo bandı da döndürülür.
        # 'clamped' bayrağı tek başına üretiliyordu ama solve() içinde HİÇ
        # okunmuyordu; klamplanan istasyonlar için uyarı üretilebilsin diye
        # bandın uçları da çağırana taşınıyor.
        'table_t_min_K': float(t_col[0]),
        'table_t_max_K': float(t_col[-1]),
    }


#: Soğutucu adı eşanlamlıları — TEK KAYNAK (ÖH D31 / P12bB4-06). Hem bu
#: modülün kurucusu hem kardeş ``heat_transfer_analysis`` soğutucu adını
#: buradan çözer; iki ayrı eşanlamlı listesi tutulmaz.
_COOLANT_ALIASES = {
    'rp1': 'rp1', 'kerosene': 'rp1', 'rp': 'rp1',
    'water': 'water', 'h2o': 'water',
    'methane': 'methane', 'ch4': 'methane', 'lch4': 'methane',
    'hydrogen': 'hydrogen', 'h2': 'hydrogen', 'lh2': 'hydrogen',
}


def canonical_coolant_name(name) -> Optional[str]:
    """Soğutucu adını kanonikleştirir ('LCH4' -> 'methane').

    Tanınmayan ad için ``None`` döner — çağıran kendi hükmünü kurar
    (bu modülün kurucusu ``ValueError`` atar, kardeş ısı-transferi modülü
    ``not_modelled`` beyan eder). Sessizce bir akışkana DÜŞÜLMEZ.
    """
    if name is None:
        return None
    anahtar = str(name).lower().replace('-', '').replace('_', '').strip()
    return _COOLANT_ALIASES.get(anahtar)


def water_properties(temperature: float) -> Dict[str, float]:
    """Liquid-water transport properties [SI] at ``temperature`` [K].

    Saturated-liquid data, Incropera & DeWitt 6th ed. Table A.6, linearly
    interpolated over 280-400 K and clamped outside that range. Returns
    density [kg/m^3], cp [J/kg/K], conductivity [W/m/K], viscosity [Pa*s],
    Prandtl number and a ``clamped`` flag.
    """
    return _interp_table(_WATER_TABLE, temperature)


def rp1_properties(temperature: float) -> Dict[str, float]:
    """RP-1 transport properties [SI] at ``temperature`` [K] (APPROXIMATE).

    Engineering compilation (Huzel & Huang App.; NASA RP-1 data; NIST),
    interpolated over 290-500 K and clamped outside. Property uncertainty is
    material (see module table banding); use for screening, not certification.
    """
    return _interp_table(_RP1_TABLE, temperature)


# ---------------------------------------------------------------------------
# Modül-düzeyi hidrolik/ısı yardımcıları (analitik, birim testli)
# ---------------------------------------------------------------------------
def dittus_boelter_nu(reynolds: float, prandtl: float,
                      heating: bool = True) -> float:
    """Dittus-Boelter Nusselt number for turbulent duct flow.

        Nu = 0.023 * Re^0.8 * Pr^n,   n = 0.4 (heating) / 0.3 (cooling)

    Incropera & DeWitt 6th ed. Eq. 8.60. Validity: Re >= 1e4,
    0.6 <= Pr <= 160, L/D >= 10 (fully-developed turbulent flow).
    """
    if reynolds <= 0.0:
        raise ValueError("Reynolds number must be positive.")
    if prandtl <= 0.0:
        raise ValueError("Prandtl number must be positive.")
    n = 0.4 if heating else 0.3
    return 0.023 * reynolds ** 0.8 * prandtl ** n


#: Dittus-Boelter geçerlilik zarfı (Incropera & DeWitt 6. baskı Eq. 8.60).
#: Korelasyonun kendi bildirilen saçılımı yaklaşık +/-%25'tir.
DB_RE_MIN = 1.0e4
DB_PR_MIN, DB_PR_MAX = 0.6, 160.0
DB_LD_MIN = 10.0
DB_REPORTED_SCATTER_PCT = 25.0

# ---------------------------------------------------------------------------
# V301 / L-REJ (26 Eki, Berke "Modeli bugün düzelt") — SIEDER-TATE DÜZELTMESİ
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/kati-sivi/L-REJ/once.json): örnek sıvı
# motorda (25 kN LOX/RP-1, Pc 70 bar) bakır 1,0 mm astarda soğutucu tarafı
# cidar 1790 K, yığın ~350 K; sıvı viskozitesi bu aralıkta kat kat düşer ve
# Dittus-Boelter bunu hiç görmüyordu. Sıvı soğutucu kanallarında tasarım
# bağıntısı Sieder-Tate biçimidir: NASA SP-125 (Huzel & Huang 1967) Eş. 4-23,
# s. 106: Nu = C1 Re^0,8 Pr^0,4 (mu/mu_w)^0,14 — "nonboiling subcritical
# temperature regions of both subcritical and supercritical coolant
# pressures" için; mu yığın, mu_w soğutucu tarafı cidar sıcaklığında. Üs
# Sieder & Tate (1936, Ind. Eng. Chem. 28) ve Incropera & DeWitt 6. bs.
# Eş. 8.61 ile aynıdır. HRMA C1'i Dittus-Boelter'in 0,023'ü olarak tutar
# (SP-125'in RP-1 deney sabiti 0,0214 Örnek 4-4'te, s. 111 verilir; o sayı
# bu kulvarda katsayıya ALINMADI — korelasyon sabiti değişikliği ayrı karar).
SIEDER_TATE_EXPONENT = 0.14
SIEDER_TATE_BASIS = (
    'Sieder-Tate wall-viscosity correction (mu_b/mu_w)^0.14 applied to the '
    'Dittus-Boelter Nusselt number for single-phase LIQUID coolants (water, '
    'RP-1): NASA SP-125 (Huzel & Huang 1967) Eq. 4-23, p. 106 '
    '(Nu = C1 Re^0.8 Pr^0.4 (mu/mu_w)^0.14 for the nonboiling region of '
    'liquid coolants, mu_w at the coolant-side wall temperature); exponent '
    'per Sieder & Tate (1936) and Incropera & DeWitt 6th ed. Eq. 8.61. Both '
    'viscosities come from the internal liquid property table of the '
    'coolant; where the coolant-side wall is above the table band, mu_w is '
    'held at the band edge, which UNDER-states the correction (liquid '
    'viscosity falls with temperature), i.e. the coolant-side coefficient '
    'there is a conservative lower bound and the station count is declared')
#: Kuple (Sieder-Tate + kanat) istasyon dengesinin sabit nokta sınırı ve
#: toleransı — HRMA sayısal ayarı (kaynak değil); tolerans süperkritik
#: dengenin 1e-3 K'siyle aynı.
REGEN_LIQUID_WALL_MAX_ITER = 50
REGEN_LIQUID_WALL_TOL_K = 1.0e-3


# ---------------------------------------------------------------------------
# V301/L-KARBON — LOX/RP-1 GAZ TARAFI KARBON BİRİKİMİ ISIL DİRENCİ (TEK TANIM)
# ---------------------------------------------------------------------------
# Kaynak: NASA SP-125 (Huzel & Huang 1967), yerel metin
# HRMA-kaynaklar/metin-nasa/NASA_SP-125_1967_Huzel_Huang_design_of_LPRE.txt
# (satır numaraları kanıt dizininde: docs/scofield/raw/OH/V301/kati-sivi/
# L-KARBON/RAPOR.md §1):
#   * s. 101-102 (satır 7028-7100): "In the case of the LO2/RP-1 combination,
#     carbon solids are deposited on the chamber walls ... This carbon deposit
#     significantly increases the gas-side thermal resistance"; Eş. 4-17
#     q = h_gc (T_aw - T_wg), Eş. 4-18 h_gc = 1 / (1/h_g + R_d);
#   * Şekil 4-25 (s. 102): "Thermal resistance of carbon deposit on chamber
#     walls LO2/RP-1, mixture ratio = 2.35, (Pc)ns = 1000 psia" — TEK eğri,
#     saçılım bandı YOK;
#   * Örnek 4-3 (s. 102-103, satır 7100-7175): R_d = 1670 (yanma odası),
#     1125 (boğaz), 1645 (eps = 5) in²·s·°F/Btu; ve "Since the carbon deposit
#     temperature approaches the gas temperature, a (T_wg/(T_c)ns) value of
#     0.8 is used to determine the sigma values from figure 4-24".
# Eğrinin ara noktaları şekilden sayısallaştırıldı (400 dpi tarama, ızgara
# çizgilerine kalibre; betik ve noktalar kanıt dizininde
# ``fig425_sayisallastirma.py`` / ``fig425_sayisal.json``); metindeki üç
# değer şekille örtüşür (eps 5: şekil ~1646, metin 1645).
#: SP-125 R_d birimi (in²·s·°F/Btu) -> SI (m²·K/W): 1 in = 0,0254 m,
#: 1 °F aralığı = 5/9 K, 1 Btu = 1055,05585262 J (IT).
CARBON_DEPOSIT_RD_US_TO_SI = (0.0254 ** 2) * (5.0 / 9.0) / 1055.05585262
#: Daralma tarafı (A/A_t, R_d [in²·s·°F/Btu]): boğaz 1125 (metin), 1,30 /
#: 1,55 / 1,70 şekilden, 1,71'de eğrinin üst ucu = metindeki yanma odası
#: değeri 1670. A/A_t > 1,71 (silindirik oda ve daralmanın üst kısmı):
#: Örnek 4-3'ün "at the combustion chamber" değeri 1670 tutulur.
CARBON_DEPOSIT_RD_CONTRACTION_US = (
    (1.00, 1125.0), (1.30, 1210.0), (1.55, 1395.0), (1.70, 1555.0),
    (1.71, 1670.0))
#: Genişleme tarafı (A/A_t, R_d): 1 ve 5 metinden, diğerleri şekilden;
#: eğri eps ~ 14,8'de biter (ötesi şekil dışı — uygulanmaz).
CARBON_DEPOSIT_RD_EXPANSION_US = (
    (1.0, 1125.0), (2.0, 1267.0), (3.0, 1405.0), (4.0, 1532.0),
    (5.0, 1645.0), (6.0, 1747.0), (7.0, 1839.0), (8.0, 1915.0),
    (9.0, 1970.0), (10.0, 2003.0), (12.0, 2043.0), (14.0, 2066.0),
    (14.8, 2070.0))
#: Birikim varken Bartz sigma'sının değerlendirildiği T_wg/T_c oranı
#: (SP-125 Örnek 4-3, s. 102-103: birikim yüzeyi gaz sıcaklığına yaklaşır).
CARBON_DEPOSIT_SIGMA_TWG_OVER_TC = 0.8
#: Uygulama zarfı. İtici: LOX/RP-1 (SP-125 Şekil 4-25; NASA TP-2862 1988).
#: O/F ve P_c: birikimin DENEYLE gözlendiği aralık — NASA TP-2862 (Masters,
#: Armstrong & Price 1988, LOX/RP-1 kalorimetre) Özet: "nominal chamber
#: pressures of 4.1, 8.3, and 13.8 MPa abs", "mixture ratios ranging from
#: 1.77 to 3.32", "development of carbon deposits (soot) ... over the mixture
#: ratio range tested". Direncin BÜYÜKLÜĞÜ yalnız SP-125'in tek noktasından
#: (O/F 2,35, P_c 6,89 MPa) gelir; zarfın geri kalanında bu bir dış değer
#: atamasıdır ve künyede yazar.
CARBON_DEPOSIT_OXIDIZERS = ('lox',)
CARBON_DEPOSIT_FUELS = ('rp1', 'rp-1')
CARBON_DEPOSIT_MIXTURE_RATIO_BAND = (1.77, 3.32)
CARBON_DEPOSIT_CHAMBER_PRESSURE_BAND_PA = (4.1e6, 13.8e6)
CARBON_DEPOSIT_BASIS = (
    'NASA SP-125 (Huzel & Huang 1967) Eq. 4-17/4-18 (p. 101-102: '
    'q = h_gc (T_aw - T_wg), h_gc = 1/(1/h_g + R_d)), Fig. 4-25 (p. 102: '
    'experimental thermal resistance of the carbon deposit, LO2/RP-1, '
    'mixture ratio 2.35, Pc 1000 psia; a single curve, no scatter band) and '
    'Sample Calculation 4-3 (p. 102-103: R_d = 1670 / 1125 / 1645 '
    'in^2 s F/Btu at the chamber / throat / eps 5; Bartz sigma evaluated at '
    'T_wg/T_c = 0.8 because the deposit surface approaches the gas '
    'temperature). Application envelope: LOX/RP-1, O/F 1.77-3.32 and Pc '
    '4.1-13.8 MPa, the range over which NASA TP-2862 (Masters, Armstrong & '
    'Price 1988) observed the deposit; the magnitude is the SP-125 point '
    '(O/F 2.35, 6.89 MPa) everywhere in that envelope. Literature scatter: '
    'SP-125 lowers the throat conductance by about 75 %, TP-2862 reports '
    'about 40 % (4.1 MPa) and 60 % (13.8 MPa, zoned injector), so the '
    'SP-125 curve is the optimistic end of the local literature. Local '
    'spalling: NASA SP-8087 (1972) sec. 3.4.1, p. 98, "localized spalling '
    'of the insulation coating in a chamber shall not result in chamber '
    'failure ... local cooling at all stations within the coated area must '
    'be sufficient even in the absence of the coating"; the no-deposit wall '
    'at the same coolant state is therefore solved too and published as the '
    'conservative end of the band')
#: Durum kodları (yayımlanan ``carbon_deposit.status``).
CARBON_DEPOSIT_STATUS_APPLIED = 'applied'
CARBON_DEPOSIT_STATUS_OUT_OF_ENVELOPE = 'out_of_envelope'
CARBON_DEPOSIT_STATUS_NOT_APPLICABLE = 'not_applicable'
CARBON_DEPOSIT_STATUS_NOT_EVALUATED = 'not_evaluated'


def carbon_deposit_resistance(area_ratio: float,
                              supersonic: bool) -> Optional[float]:
    """Karbon birikimi ısıl direnci R_d [m²·K/W] — TEK işlev (SP-125 Şk. 4-25).

    ``area_ratio`` = A/A_t (>= 1). Daralma tarafında (``supersonic=False``)
    A/A_t şeklin üst ucundan (1,71) büyükse yanma odası değeri (1670) döner.
    Genişleme tarafında şeklin bittiği eps 14,8'in ötesi ŞEKİL DIŞIDIR:
    ``None`` döner (çağıran R_d = 0 kullanır ve istasyonu sayıp beyan eder —
    birikimsiz cidar daha sıcaktır, yani yön tutucudur).
    """
    ar = float(area_ratio)
    if not math.isfinite(ar) or ar <= 0.0:
        raise ValueError(f'area_ratio must be positive and finite; got '
                         f'{area_ratio!r}')
    ar = max(ar, 1.0)
    tablo = (CARBON_DEPOSIT_RD_EXPANSION_US if supersonic
             else CARBON_DEPOSIT_RD_CONTRACTION_US)
    xs = [p[0] for p in tablo]
    ys = [p[1] for p in tablo]
    if ar > xs[-1]:
        if supersonic:
            return None
        return ys[-1] * CARBON_DEPOSIT_RD_US_TO_SI
    return float(np.interp(ar, xs, ys)) * CARBON_DEPOSIT_RD_US_TO_SI


def carbon_deposit_envelope(oxidizer, fuel, mixture_ratio,
                            chamber_pressure_pa) -> Dict:
    """Karbon birikimi modeli bu koşuya uygulanır mı? (fail-closed).

    Döner: ``{'status', 'applied', 'reason'}``. ``status``:
    ``applied`` | ``out_of_envelope`` (LOX/RP-1 ama O/F ya da P_c bandın
    dışında — direnç UYGULANMAZ ve sonuç bunu söyler) |
    ``not_applicable`` (itici LOX/RP-1 değil: metan, LH2 ... — kaynak yok).
    """
    ox = str(oxidizer or '').strip().lower()
    fu = str(fuel or '').strip().lower()
    if ox not in CARBON_DEPOSIT_OXIDIZERS or fu not in CARBON_DEPOSIT_FUELS:
        return {'status': CARBON_DEPOSIT_STATUS_NOT_APPLICABLE,
                'applied': False,
                'reason': (f'propellant {fu or "?"}/{ox or "?"} is not '
                           'LOX/RP-1: the source data (SP-125 Fig. 4-25, '
                           'NASA TP-2862) cover LOX/RP-1 only; no carbon '
                           'deposit resistance is modelled')}
    try:
        mr = float(mixture_ratio)
        pc = float(chamber_pressure_pa)
    except (TypeError, ValueError):
        mr = pc = float('nan')
    sorun = []
    lo, hi = CARBON_DEPOSIT_MIXTURE_RATIO_BAND
    if not (math.isfinite(mr) and lo <= mr <= hi):
        sorun.append(f'O/F {mr:.3g} outside {lo:g}-{hi:g}')
    plo, phi = CARBON_DEPOSIT_CHAMBER_PRESSURE_BAND_PA
    if not (math.isfinite(pc) and plo <= pc <= phi):
        sorun.append(f'Pc {pc / 1e5:.3g} bar outside {plo / 1e5:.0f}-'
                     f'{phi / 1e5:.0f} bar')
    if sorun:
        return {'status': CARBON_DEPOSIT_STATUS_OUT_OF_ENVELOPE,
                'applied': False,
                'reason': ('carbon deposit not modelled (out of envelope): '
                           + '; '.join(sorun)
                           + ' (the deposit was observed experimentally only '
                           'in that range, NASA TP-2862)')}
    return {'status': CARBON_DEPOSIT_STATUS_APPLIED, 'applied': True,
            'reason': (f'LOX/RP-1, O/F {mr:.3g}, Pc {pc / 1e5:.4g} bar inside '
                       'the envelope; SP-125 Fig. 4-25 resistance applied')}


def sieder_tate_factor(mu_bulk: float, mu_wall: float) -> float:
    """Sieder-Tate viskozite oranı çarpanı (mu_b/mu_w)^0,14.

    NASA SP-125 Eş. 4-23 (s. 106); Sieder & Tate (1936); Incropera Eş. 8.61.
    Girdiler pozitif ve sonlu olmalı; değilse ``ValueError`` (sayı
    uydurulmaz).
    """
    for ad, deger in (('mu_bulk', mu_bulk), ('mu_wall', mu_wall)):
        if (isinstance(deger, bool) or not isinstance(deger, (int, float))
                or not math.isfinite(deger) or not deger > 0.0):
            raise ValueError(f'{ad} must be a positive finite viscosity '
                             f'[Pa*s]; got {deger!r}')
    return (float(mu_bulk) / float(mu_wall)) ** SIEDER_TATE_EXPONENT


def dittus_boelter_envelope(reynolds: float, prandtl: float,
                            length_over_diameter: float = None,
                            sieder_tate_applied: bool = False) -> dict:
    """Dittus-Boelter geçerlilik zarfını tarar (v2.6.2 fizik denetimi, F154).

    Kodda yalnız Reynolds taranıyordu; Prandtl bandı ve giriş-uzunluğu
    (L/D >= 10, tam gelişmiş türbülanslı akış) koşulu hiç denetlenmiyordu.
    Zarf dışında korelasyon hâlâ bir sayı üretir ama o sayının bildirilen
    +/-%25 saçılımı geçerli değildir — kullanıcı bunu bilmeden ısı akısına
    güvenemez.

    Büyük cidar/yığın özellik farkı için Sieder-Tate (mu_b/mu_w)^0.14
    düzeltmesinin uygulanıp uygulanmadığı ``sieder_tate_applied`` ile
    beyan edilir (V301/L-REJ: sıvı tablo soğutucularında UYGULANIR; metan/
    hidrojenin kritik-altı Dittus-Boelter yedeğinde UYGULANMAZ).

    Dönüş: ``{'in_envelope': bool, 'violations': [...], 'scatter_pct': 25.0}``
    """
    violations = []
    if reynolds < DB_RE_MIN:
        violations.append(
            f'Re={reynolds:.3g} < {DB_RE_MIN:.0g} (tam türbülanslı değil; '
            'geçiş rejiminde korelasyon geçersizdir)')
    if not (DB_PR_MIN <= prandtl <= DB_PR_MAX):
        violations.append(
            f'Pr={prandtl:.3g} bandın [{DB_PR_MIN}, {DB_PR_MAX}] dışında')
    if length_over_diameter is not None and length_over_diameter < DB_LD_MIN:
        violations.append(
            f'L/D={length_over_diameter:.3g} < {DB_LD_MIN:.0f} (giriş bölgesi; '
            'yerel Nu tam gelişmiş değerin üzerindedir)')
    return {
        'in_envelope': not violations,
        'violations': violations,
        'scatter_pct': DB_REPORTED_SCATTER_PCT,
        'sieder_tate_correction_applied': bool(sieder_tate_applied),
        'note': ('Dittus-Boelter reported scatter is about '
                 f'+/-{DB_REPORTED_SCATTER_PCT:.0f}%; the Sieder-Tate '
                 '(mu_b/mu_w)^0.14 correction for large wall-to-bulk property '
                 'differences is '
                 + ('APPLIED (NASA SP-125 Eq. 4-23).' if sieder_tate_applied
                    else 'NOT applied.')),
    }


def hydraulic_diameter_rect(width: float, height: float) -> float:
    """Hydraulic diameter of a rectangular channel [m].

        D_h = 4*A_c / P_wet = 2*w*h/(w+h)

    Incropera & DeWitt 6th ed. Ch. 8 (non-circular ducts).
    """
    if width <= 0.0 or height <= 0.0:
        raise ValueError("Channel width and height must be positive [m].")
    return 2.0 * width * height / (width + height)


def haaland_friction_factor(reynolds: float, rel_roughness: float) -> float:
    """Darcy friction factor from the Haaland explicit approximation.

        1/sqrt(f) = -1.8 * log10[ (6.9/Re) + (eps/D/3.7)^1.11 ]   (turbulent)
        f = 64/Re                                                  (laminar)

    Haaland (1983); White, "Fluid Mechanics", 7th ed., Eqs. 6.12, 6.49.
    Accurate to ~2 % vs the implicit Colebrook equation for Re > ~4000.
    """
    if reynolds <= 0.0:
        raise ValueError("Reynolds number must be positive.")
    if rel_roughness < 0.0:
        raise ValueError("Relative roughness must be non-negative.")
    if reynolds < RE_LAMINAR_MAX:
        return 64.0 / reynolds
    inv_sqrt_f = -1.8 * math.log10((6.9 / reynolds)
                                   + (rel_roughness / 3.7) ** 1.11)
    return 1.0 / (inv_sqrt_f * inv_sqrt_f)


def darcy_weisbach_dp(friction_factor: float, length: float,
                      hydraulic_diameter: float, density: float,
                      velocity: float) -> float:
    """Darcy-Weisbach pressure drop [Pa] over a duct length.

        dP = f * (L / D_h) * (rho * V^2 / 2)

    White, "Fluid Mechanics", 7th ed., Eq. 6.10.
    """
    if hydraulic_diameter <= 0.0:
        raise ValueError("Hydraulic diameter must be positive [m].")
    return (friction_factor * (length / hydraulic_diameter)
            * 0.5 * density * velocity * velocity)


def fin_area_ratio(channel_width: float, channel_height: float,
                   pitch: float, land_thickness: float,
                   h_coolant: float, k_wall: float) -> float:
    """Coolant-side extended-surface (fin) area ratio A_eff/A_gas.

    Milled-channel regen liners expose the channel bottom PLUS the two side
    walls (lands) to the coolant; the lands act as straight rectangular fins
    of thickness t_land and height h_ch. Standard treatment (Huzel & Huang,
    "Modern Engineering for Design of Liquid-Propellant Rocket Engines",
    Ch. 4 — channel lands as fins; Incropera & DeWitt 6th ed. Ch. 3.6):

        eta_f = tanh(m*h_ch) / (m*h_ch),   m = sqrt(2*h_c / (k_w * t_land))
        A_eff/A_gas = (w + 2*eta_f*h_ch) / pitch

    (adiabatic fin tip, Incropera Eq. 3.86; m from Eq. 3.85 with
    P/A_c ~ 2/t for a thin rectangular fin). Each land is shared by two
    neighbouring channels, so per channel-pitch exactly one land (two half
    sides) is counted: w + 2*eta*h over the pitch.
    """
    if pitch <= 0.0 or channel_width <= 0.0 or channel_height <= 0.0:
        raise ValueError("pitch, channel width and height must be positive.")
    if h_coolant <= 0.0 or k_wall <= 0.0:
        raise ValueError("h_coolant and k_wall must be positive.")
    t_land = max(land_thickness, 1.0e-5)   # sayısal taban (kanallar sığmıyorsa
    #                                        ayrı GEOMETRY uyarısı zaten var)
    m_fin = math.sqrt(2.0 * h_coolant / (k_wall * t_land))
    m_l = m_fin * channel_height
    eta_f = math.tanh(m_l) / m_l if m_l > 1.0e-9 else 1.0
    return (channel_width + 2.0 * eta_f * channel_height) / pitch


def acceleration_dp(mass_flux: float, rho_in: float, rho_out: float) -> float:
    """Acceleration (momentum) pressure drop [Pa] in a constant-area duct.

        dP_acc = G^2 * (1/rho_out - 1/rho_in),   G = mdot/A_c  [kg/m^2/s]

    One-dimensional steady momentum balance for a constant-area channel
    (Collier & Thome, "Convective Boiling and Condensation", 3rd ed., Ch. 2,
    acceleration pressure-gradient term). Positive when the heated fluid
    expands (rho_out < rho_in) — significant for supercritical coolants whose
    density changes strongly along the channel.
    """
    if rho_in <= 0.0 or rho_out <= 0.0:
        raise ValueError("Densities must be positive [kg/m^3].")
    return mass_flux * mass_flux * (1.0 / rho_out - 1.0 / rho_in)


def jackson_exponent_n(t_bulk: float, t_wall: float, t_pc: float) -> float:
    """Jackson property-ratio exponent n for the (cp_bar/cp_b)^n term.

    Piecewise form (Jackson & Hall 1979; Jackson 2013, Nucl. Eng. Des. 264):

        n = 0.4                                    T_w <= T_pc  or  T_b >= 1.2*T_pc
        n = 0.4 + 0.2*(T_w/T_pc - 1)               T_b <= T_pc < T_w
        n = 0.4 + 0.2*(T_w/T_pc - 1)
                * (1 - 5*(T_b/T_pc - 1))           T_pc < T_b < 1.2*T_pc, T_b < T_w

    Continuous across the regime boundaries (checked in tests).
    """
    if t_pc <= 0.0 or t_bulk <= 0.0 or t_wall <= 0.0:
        raise ValueError("Temperatures must be positive [K].")
    if t_wall <= t_pc or t_bulk >= 1.2 * t_pc:
        return 0.4
    if t_bulk <= t_pc:
        return 0.4 + 0.2 * (t_wall / t_pc - 1.0)
    return (0.4 + 0.2 * (t_wall / t_pc - 1.0)
            * (1.0 - 5.0 * (t_bulk / t_pc - 1.0)))


def jackson_nu(reynolds: float, prandtl: float, rho_wall_over_bulk: float,
               cp_bar_over_bulk: float, n_exponent: float) -> float:
    """Jackson supercritical forced-convection Nusselt number.

        Nu_b = 0.0183 * Re_b^0.82 * Pr_b^0.5
               * (rho_w/rho_b)^0.3 * (cp_bar/cp_b)^n

    Jackson & Hall (1979), in Kakac & Spalding (eds.), "Turbulent Forced
    Convection in Channels and Bundles", Vol. 2; restated in Jackson (2013),
    Nucl. Eng. Des. 264. cp_bar = (h_w - h_b)/(T_w - T_b) is the integrated
    mean specific heat between bulk and wall. Standard engineering model for
    supercritical-pressure cooling channels (applied to CH4 rocket cooling in
    e.g. Urbano & Nasuti 2013, J. Thermophys. Heat Transfer 27(2)).
    """
    if reynolds <= 0.0:
        raise ValueError("Reynolds number must be positive.")
    if prandtl <= 0.0:
        raise ValueError("Prandtl number must be positive.")
    if rho_wall_over_bulk <= 0.0 or cp_bar_over_bulk <= 0.0:
        raise ValueError("Property ratios must be positive.")
    return (0.0183 * reynolds ** 0.82 * prandtl ** 0.5
            * rho_wall_over_bulk ** 0.3 * cp_bar_over_bulk ** n_exponent)


def pseudocritical_temperature(fluid: str, pressure: float) -> float:
    """Pseudo-critical temperature T_pc(P) [K] at a supercritical pressure.

    Defined as the temperature of the isobaric cp maximum at P > P_crit
    (standard definition; Jackson 2013, Nucl. Eng. Des. 264), searched over
    the band [T_crit, min(2*T_crit, T_max)]: a coarse grid locates the
    maximum (cp(T) is NOT globally unimodal — the ideal-gas cp rise at high
    T creates a second branch, so a bare golden-section can walk to the
    wrong side), then a golden-section refinement narrows it to ~0.05 K.
    If the maximum sits at the band edge the edge value is returned: at very
    high reduced pressures the pseudo-critical line fades out and the
    Jackson regime classification then degenerates to the plain n = 0.4
    form — a bounded, documented behaviour. Results are cached per (fluid,
    0.5-bar pressure bin). Raises for P <= P_crit (pseudo-critical
    temperature is undefined there; use T_sat) and without CoolProp.
    """
    if not _HAS_COOLPROP:
        raise RuntimeError("CoolProp is required for "
                           "pseudocritical_temperature().")
    p_crit = float(_CP_PropsSI('Pcrit', fluid))
    if pressure <= p_crit:
        raise ValueError(
            f"Pseudo-critical temperature is defined only above the critical "
            f"pressure ({p_crit / 1e5:.2f} bar for {fluid}); "
            f"got {pressure / 1e5:.2f} bar.")
    key = (fluid, int(round(pressure / 5.0e4)))  # 0.5 bar kova
    if key in _PSEUDOCRITICAL_CACHE:
        return _PSEUDOCRITICAL_CACHE[key]
    t_crit = float(_CP_PropsSI('Tcrit', fluid))
    t_max = float(_CP_PropsSI('Tmax', fluid))
    lo = t_crit
    hi = min(2.0 * t_crit, t_max)

    def _cp(t: float) -> float:
        return float(_CP_PropsSI('C', 'T', t, 'P', pressure, fluid))

    # 1) Kaba ızgara: global maksimumun komşuluğunu bul (bimodal koruması).
    grid = np.linspace(lo, hi, 96)
    cp_grid = np.array([_cp(t) for t in grid])
    i_max = int(np.argmax(cp_grid))
    if i_max == 0 or i_max == len(grid) - 1:
        # İç maksimum yok — pseudo-kritik çizgi bu basınçta silinmiş.
        t_pc = float(grid[i_max])
        _PSEUDOCRITICAL_CACHE[key] = t_pc
        return t_pc
    a = float(grid[i_max - 1])
    b = float(grid[i_max + 1])

    # 2) Altın-oran incelmesi (~0.05 K hassasiyet), tek tepeli aralıkta.
    invphi = (math.sqrt(5.0) - 1.0) / 2.0
    c = b - invphi * (b - a)
    d = a + invphi * (b - a)
    fc, fd = _cp(c), _cp(d)
    while (b - a) > 0.05:
        if fc > fd:
            b, d, fd = d, c, fc
            c = b - invphi * (b - a)
            fc = _cp(c)
        else:
            a, c, fc = c, d, fd
            d = a + invphi * (b - a)
            fd = _cp(d)
    t_pc = 0.5 * (a + b)
    _PSEUDOCRITICAL_CACHE[key] = t_pc
    return t_pc


# ===========================================================================
# Ana sınıf
# ===========================================================================
class RegenCooling:
    """1D regenerative-cooling station-marching solver (analysis mode).

    The nozzle inner contour is sampled from the single shared sampler
    (``hrma.engines.nozzle_design.sample_nozzle_inner_contour``) and split into
    20-50 axial stations with the throat station always on the grid. At each
    station the gas-side Bartz coefficient and the coolant-side Dittus-Boelter
    coefficient are combined through the liner conduction resistance to give
    the local heat flux and the hot / cold wall temperatures. The coolant bulk
    temperature and pressure are marched station-to-station.

    Parameters
    ----------
    chamber_pressure : float
        Chamber (stagnation) pressure [Pa].
    chamber_temperature : float
        Chamber (stagnation) temperature [K].
    gamma : float
        Ratio of specific heats (frozen). The accepted band is the
        single-source ``GAMMA_BAND_MIN`` / ``GAMMA_BAND_MAX`` pair
        exported by ``heat_transfer_analysis`` (do not restate the
        numbers here — ÖH D21 / P4B1-16, doctrine 4).
    molecular_weight : float
        Combustion-gas molecular weight [g/mol] (default 24, typical hybrid).
    throat_diameter : float
        Nozzle throat diameter [m].
    exit_diameter, expansion_ratio : float, optional
        Nozzle exit diameter [m], or the area expansion ratio (>1) instead.
    coolant : str
        'water', 'rp1', 'methane' (aliases ch4/lch4) or 'hydrogen' (aliases
        h2/lh2). Methane/hydrogen REQUIRE CoolProp and use full
        (T, P)-dependent properties with an enthalpy-based march and the
        Jackson supercritical coolant-side correlation (module docstring).
    coolant_mdot : float
        Total coolant mass flow rate through all channels [kg/s].
    coolant_inlet_temp : float
        Coolant inlet (bulk) temperature [K].
    coolant_inlet_pressure : float
        Coolant inlet static pressure [Pa].
    n_channels : int
        Number of parallel cooling channels (>= 1).
    channel_width, channel_height : float
        Rectangular channel width and height [m] (constant along the length —
        analysis mode, no tapering).
    wall_thickness : float
        Inner-liner (hot wall) thickness [m].
    wall_material : str
        Liner material key (``hrma.data.materials_db``: copper, cucrzr,
        steel, inconel_718, ...). Sets k_w and the temperature limits.
    n_stations : int
        Number of axial stations, clamped to [20, 50].
    flow_direction : str
        'counterflow' (default, coolant enters at the exit) or 'coflow'
        (coolant enters at the chamber).
    wall_roughness : float
        Channel absolute surface roughness [m] (default 5e-6, machined metal;
        'approximate'). Only affects the turbulent friction factor.
    coolant_props_source : str
        'auto' (default: CoolProp for water if available, else table; table
        for RP-1), 'table' (force internal tables), or 'coolprop'. 'table'
        is INVALID for methane/hydrogen (no table exists).
    fin_effect : bool
        Apply the coolant-side extended-surface (channel-land fin) area model
        (``fin_area_ratio``; Huzel & Huang Ch. 4, Incropera Ch. 3.6) on
        EVERY coolant path (V301/L-REJ, 26 Oct 2026: before that the
        water/RP-1 path ignored it). False = coolant-side area equals the
        gas-side area (ratio 1).
    motor_data : dict, optional
        Repo-style motor dictionary forwarded to the contour sampler and the
        gas-property resolver (chamber diameter, nozzle type, bell angles,
        transport-property overrides).
    """

    def __init__(self,
                 chamber_pressure: float,
                 chamber_temperature: float,
                 gamma: float = 1.2,
                 molecular_weight: float = 24.0,
                 throat_diameter: Optional[float] = None,
                 exit_diameter: Optional[float] = None,
                 expansion_ratio: Optional[float] = None,
                 coolant: str = 'water',
                 coolant_mdot: float = 1.0,
                 coolant_inlet_temp: float = 300.0,
                 coolant_inlet_pressure: float = 30.0e5,
                 n_channels: int = REGEN_N_CHANNELS_API_DEFAULT,
                 channel_width: float = 2.0e-3,
                 channel_height: float = 3.0e-3,
                 wall_thickness: float = 1.0e-3,
                 wall_material: str = 'copper',
                 n_stations: int = 40,
                 flow_direction: str = FLOW_COUNTERFLOW,
                 wall_roughness: float = 5.0e-6,
                 coolant_props_source: str = 'auto',
                 fin_effect: bool = True,
                 motor_data: Optional[Dict] = None):
        # --- doğrulamalar (İngilizce hata metinleri: kullanıcıya görünür) ---
        if not (chamber_pressure > 0.0):
            raise ValueError("chamber_pressure must be positive [Pa].")
        if not (chamber_temperature > 0.0):
            raise ValueError("chamber_temperature must be positive [K].")
        # ÖH D21 / P4B1-16 (doktrin-4 TEK KAYNAK): bandın sayısı artık
        # ısı-transferi modülünden İTHAL EDİLİR, burada yeniden yazılmaz.
        # Reddin cümlesi de ortaktır — üç modül aynı girdide aynı hükmü
        # kurar (kardeş ısı-transferi modülü v2.6.27'ye kadar aynı girdiyi
        # sessizce 1,20'ye kelepçeliyordu).
        _guard_gamma_band(gamma)
        if not (molecular_weight > 0.0):
            raise ValueError("molecular_weight must be positive [g/mol].")

        # ÖH D31 / P12bB4-06 (doktrin-4 TEK KAYNAK): ad çözümü artık modül
        # düzeyindeki ``canonical_coolant_name``de durur; kardeş ısı-transferi
        # modülü de soğutucu adını AYNI kuralla çözer (iki ayrı eşanlamlı
        # listesi tutulmaz). Reddin cümlesi değişmedi.
        coolant = canonical_coolant_name(coolant)
        if coolant is None:
            raise ValueError("coolant must be 'water', 'rp1', 'methane' or "
                             "'hydrogen'.")
        self.coolant = coolant

        # Metan/hidrojen: CoolProp ZORUNLU — dahili tablo yok, sabit değere
        # sessiz düşüş yok (uydurma-veri bekçisiyle uyumlu açık politika).
        if coolant in SUPERCRITICAL_COOLANT_FLUIDS:
            if coolant_props_source == 'table':
                raise ValueError(
                    f"coolant='{coolant}' has no internal property table — "
                    "CoolProp is mandatory (coolant_props_source must be "
                    "'auto' or 'coolprop'). Refusing to substitute constant "
                    "properties.")
            if not _HAS_COOLPROP:
                raise ValueError(
                    f"coolant='{coolant}' requires CoolProp for (T, P)-"
                    "dependent properties, but CoolProp is not installed.")

        if not (coolant_mdot > 0.0):
            raise ValueError("coolant_mdot must be positive [kg/s].")
        if not (coolant_inlet_temp > 0.0):
            raise ValueError("coolant_inlet_temp must be positive [K].")
        if not (coolant_inlet_pressure > 0.0):
            raise ValueError("coolant_inlet_pressure must be positive [Pa].")
        if int(n_channels) < 1:
            raise ValueError("n_channels must be a positive integer.")
        if not (channel_width > 0.0) or not (channel_height > 0.0):
            raise ValueError("channel_width and channel_height must be "
                             "positive [m].")
        if not (wall_thickness > 0.0):
            raise ValueError("wall_thickness must be positive [m].")
        if wall_roughness < 0.0:
            raise ValueError("wall_roughness must be non-negative [m].")
        if flow_direction not in (FLOW_COUNTERFLOW, FLOW_COFLOW):
            raise ValueError("flow_direction must be 'counterflow' or "
                             "'coflow'.")
        if coolant_props_source not in ('auto', 'table', 'coolprop'):
            raise ValueError("coolant_props_source must be 'auto', 'table' "
                             "or 'coolprop'.")

        # --- malzeme (merkezi DB — kopya döner) ---
        try:
            self.material = get_material(wall_material)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        self.wall_material = wall_material
        # Karar §28-31 (c) — TEK EŞİK (v3.0 bloklayıcı, ÖNEMLİ). Cidar
        # hükmü eşikleri artık kaydın HAM
        # ``allowable_temperature`` / ``max_service_temperature`` alanlarından
        # DEĞİL, termal kulvarın kanonik merdiveninden
        # (``materials_db.temperature_limits``) okunur. Ölçülen çelişki
        # (termal yeniden denetim-7/8): copper ve steel_4130'da ham izin
        # 1000 K ⟷ kanonik izin 723 / 811 K; 'service limit' diye ERİME
        # (max_service_temperature = melting_point, 24 kaydın hepsinde)
        # yayımlanıyordu ve UNSAFE dalı bu yüzden ERİŞİLEMEZDİ (önce erime
        # dalı yakalıyordu). Aynı motorun ısıl koruma künyesi
        # (liquid_rocket_engine ablatif/ışınım dalı) ve güvenlik analizi
        # 'service limit' adıyla İZİN basamağını taşıyor; bu modül de aynı
        # sayıyı taşır. Basamak yoksa hüküm uydurulmaz (fail-closed).
        # İterasyon BAŞLANGICI ayrı (``_seed_allowable_K``; hüküm değil).
        self.temperature_ladder = temperature_limits(self.material)
        for _basamak in ('allowable_K', 'melting_K'):
            if self.temperature_ladder.get(_basamak) is None:
                raise ValueError(
                    f"wall material '{wall_material}' has no "
                    f"{_basamak} in materials_db.temperature_limits — no "
                    "wall-temperature verdict without a sourced limit")

        self.motor_data = dict(motor_data or {})

        # --- geometri: boğaz/çıkış çapı veya genişleme oranı ---
        if throat_diameter is None:
            throat_diameter = self.motor_data.get('throat_diameter')
        if throat_diameter is None or not (float(throat_diameter) > 0.0):
            raise ValueError("throat_diameter must be provided and positive [m].")
        throat_diameter = float(throat_diameter)

        if exit_diameter is None:
            if expansion_ratio is not None:
                if not (float(expansion_ratio) > 1.0):
                    raise ValueError("expansion_ratio must be > 1.")
                exit_diameter = throat_diameter * math.sqrt(float(expansion_ratio))
            else:
                exit_diameter = self.motor_data.get('exit_diameter')
        if exit_diameter is None or not (float(exit_diameter) > throat_diameter):
            raise ValueError("exit_diameter must exceed throat_diameter "
                             "(supersonic nozzle, expansion ratio > 1).")
        exit_diameter = float(exit_diameter)

        self.chamber_pressure = float(chamber_pressure)
        self.chamber_temperature = float(chamber_temperature)
        self.gamma = float(gamma)
        self.molecular_weight = float(molecular_weight)
        self.throat_diameter = throat_diameter
        self.exit_diameter = exit_diameter
        self.coolant_mdot = float(coolant_mdot)
        self.coolant_inlet_temp = float(coolant_inlet_temp)
        self.coolant_inlet_pressure = float(coolant_inlet_pressure)
        self.n_channels = int(n_channels)
        self.channel_width = float(channel_width)
        self.channel_height = float(channel_height)
        self.wall_thickness = float(wall_thickness)
        # ÖH A2 sivi-sogutma · F-17 + denetçi Ş4(iii): sığma ölçütünün kaburga
        # genişliği modülün TEK sabitidir (``COOLING_CHANNEL_LAND_M``; künye
        # ``COOLING_CHANNEL_LAND_BASIS``). Kurucu parametresi DEĞİLDİR: imzada
        # olsaydı /api/regen-cooling ucunda bağlı olmayan bir girdi olurdu
        # (test_d29 KurucuParametreleri sözleşmesi). Uç bu sayıyı kullanıcıdan
        # almaz; sığmama durumunda GEOMETRY uyarısı kaburga genişliğini mm
        # olarak adıyla yazar.
        self.land_width = float(COOLING_CHANNEL_LAND_M)
        #: F-17: son ``solve()`` çağrısının sığma hükmü (tek tanımdan).
        self.channel_fit = None
        self.n_stations = int(min(max(int(n_stations), REGEN_N_STATIONS_MIN),
                                  REGEN_N_STATIONS_MAX))
        self.flow_direction = flow_direction
        self.wall_roughness = float(wall_roughness)
        self.coolant_props_source = coolant_props_source
        #: ÖH D15 / P4B2-07 — marş boyunca FİİLEN kullanılan özellik
        #: kaynakları. ``_coolant_properties`` her dönüşte buraya yazar;
        #: özet bunu ``coolant_props_source_used`` olarak yayımlar.
        self._props_sources_seen = set()

        # --- ÖH D15 / P4B2-09 — GEOMETRİ ZARFI KAPILARI -------------------
        # Kurucu bloğu yalnız POZİTİFLİĞE bakıyordu; künyenin kendi
        # geçerlilik koşulu ("thin flat-plate radial conduction", :52-55)
        # hiç denetlenmiyordu.
        #
        # (1) İNCE CİDAR. İletim direnci ``r_cond = wall_thickness / k_wall``
        #     DÜZ LEVHA formülüdür; silindirik cidarın doğrusu (sıcak yüzey
        #     alanına indirgenmiş) ``r1*ln(r2/r1)/k``'dır. ÖLÇÜLDÜ
        #     (31 Ağustos 2026, taban e88d096; boğaz yarıçapı 50 mm) —
        #     düz levhanın bağıl hatası ve ürünün kabul ettiği sonuç:
        #        t_w =  1 mm -> hata  %0,99 | max_wall_hot_K =  882,31
        #        t_w =  5 mm -> hata  %4,69 | max_wall_hot_K = 1158,24
        #        t_w = 20 mm -> hata %15,88 | max_wall_hot_K = 1774,16
        #        t_w = 60 mm -> hata %34,30 | max_wall_hot_K = 2442,79
        #     Dördünde de ince-cidar uyarısı ÜRETİLMİYORDU (0 uyarı).
        #     Eşikler ``WALL_CURVATURE_WARN_REL`` / ``..._MAX_REL``.
        # (2) KANAL DERİNLİĞİ. Kanal yüksekliği boğaz yarıçapının 4 katı
        #     (200 mm ⟷ 50 mm) KABUL ediliyordu; ölçüldü: T_w,max = 2827,73 K,
        #     iki uyarı, hiçbiri derinliği söylemiyor. Boğaz kesitini
        #     çevreleyen bir ceket kanalı boğaz yarıçapından derin olamaz —
        #     bu bir model zarfı değil, GEOMETRİK imkânsızlıktır.
        _r_throat = self.throat_diameter / 2.0
        if self.channel_height >= _r_throat:
            raise ValueError(
                "channel_height ({h:.1f} mm) must be smaller than the throat "
                "radius ({r:.1f} mm): a cooling channel wrapped around the "
                "throat cannot be deeper than the throat radius itself. This "
                "is a geometric impossibility, not a modelling assumption; "
                "no station values are published.".format(
                    h=self.channel_height * 1e3, r=_r_throat * 1e3))
        _r_dis = _r_throat + self.wall_thickness
        # düz levha ⟷ silindirik iletim direnci bağıl hatası (sıcak yüzey
        # referanslı): 1 − r1·ln(r2/r1)/t_w
        self.wall_curvature_error_rel = abs(
            1.0 - _r_throat * math.log(_r_dis / _r_throat)
            / self.wall_thickness)
        if self.wall_curvature_error_rel > WALL_CURVATURE_MAX_REL:
            raise ValueError(
                "wall_thickness ({t:.1f} mm) is outside the thin-wall "
                "envelope of this model at the throat (radius {r:.1f} mm): "
                "the flat-plate conduction resistance used here "
                "(r_cond = wall_thickness / k_wall) differs from the "
                "cylindrical solution r1*ln(r2/r1)/k_wall by "
                "{e:.1%}, above the {m:.0%} limit. The model note states "
                "'thin flat-plate radial conduction' and that claim is now "
                "enforced: no wall temperature is published outside it. "
                "Reduce wall_thickness or increase the throat "
                "diameter.".format(
                    t=self.wall_thickness * 1e3, r=_r_throat * 1e3,
                    e=self.wall_curvature_error_rel,
                    m=WALL_CURVATURE_MAX_REL))
        # Fin (kanal sırtı) genişletilmiş-yüzey modeli. V301/L-REJ (26 Eki,
        # Berke "Modeli bugün düzelt"): artık HER soğutucu yolunda uygulanır.
        # Eskiden yalnız metan/hidrojen süperkritik yolundaydı; su/RP-1 yolu
        # soğutucu alanını gaz alanına eşit sayıyordu ("fin efficiency ~1").
        # ÖLÇÜLDÜ (L-REJ/once.json, örnek sıvı motor, bakır 1,0 mm): etkin
        # h_c ≈ 22 000 W/m²K ve soğutucu tarafı cidar 1790 K. Tek işlev:
        # ``_fin_ratio`` (iki yol aynı geometri ve aynı formül).
        self.fin_effect = bool(fin_effect)

        # --- süperkritik-yetenekli soğutucu: EOS sınırları + giriş durumu ---
        self._cp_fluid = SUPERCRITICAL_COOLANT_FLUIDS.get(self.coolant)
        if self._cp_fluid is not None:
            self.coolant_pcrit = float(_CP_PropsSI('Pcrit', self._cp_fluid))
            self.coolant_tcrit = float(_CP_PropsSI('Tcrit', self._cp_fluid))
            self._fluid_tmin = float(_CP_PropsSI('Tmin', self._cp_fluid))
            self._fluid_tmax = float(_CP_PropsSI('Tmax', self._cp_fluid))
            self._fluid_pmax = float(_CP_PropsSI('pmax', self._cp_fluid))
            if not (self._fluid_tmin <= self.coolant_inlet_temp
                    <= self._fluid_tmax):
                raise ValueError(
                    f"coolant_inlet_temp {self.coolant_inlet_temp:.1f} K is "
                    f"outside the {self._cp_fluid} EOS range "
                    f"[{self._fluid_tmin:.1f}, {self._fluid_tmax:.1f}] K.")
            if self.coolant_inlet_pressure > self._fluid_pmax:
                raise ValueError(
                    f"coolant_inlet_pressure {self.coolant_inlet_pressure/1e5:.1f} "
                    f"bar exceeds the {self._cp_fluid} EOS limit "
                    f"{self._fluid_pmax/1e5:.0f} bar.")
            # Giriş durumunu hemen çöz — aralık dışıysa AÇIK hata (erken).
            self._coolant_properties(self.coolant_inlet_temp,
                                     self.coolant_inlet_pressure)
        else:
            self.coolant_pcrit = None
            self.coolant_tcrit = None
            self._fluid_tmin = None
            self._fluid_tmax = None
            self._fluid_pmax = None

        # Türetilmiş kanal büyüklükleri
        self.channel_area = self.channel_width * self.channel_height  # m^2
        self.hydraulic_diameter = hydraulic_diameter_rect(
            self.channel_width, self.channel_height)                  # m
        self.mdot_per_channel = self.coolant_mdot / self.n_channels   # kg/s

        # Isı transferi yardımcıları (Bartz + gaz özellikleri) — tek kaynak.
        self._hta = HeatTransferAnalyzer()

        # motor_data'yı Bartz için tutarlı boğaz/çıkış çapıyla besle.
        self._md_gas = dict(self.motor_data)
        self._md_gas['chamber_pressure'] = self.chamber_pressure / 1e5  # bar
        self._md_gas['chamber_temperature'] = self.chamber_temperature
        self._md_gas['gamma'] = self.gamma
        self._md_gas['molecular_weight'] = self.molecular_weight
        self._md_gas['throat_diameter'] = self.throat_diameter
        self._md_gas.setdefault('exit_diameter', self.exit_diameter)

        # V301/L-KARBON — gaz tarafı karbon birikimi: itici bağlamı
        # ``motor_data['carbon_deposit_context']`` = ``{'oxidizer', 'fuel',
        # 'mixture_ratio'}`` (motor sözlüğüyle gelir; kurucu imzası
        # değişmez — uç sözleşmesi test_d29). Verilmezse model
        # DEĞERLENDİRİLMEZ ve bu adıyla yayımlanır (bağımsız API çağrısı
        # gazın hangi iticiden geldiğini bilmez; uydurulmaz).
        carbon_deposit = self.motor_data.get('carbon_deposit_context')
        if carbon_deposit is None:
            self.carbon_deposit_envelope = {
                'status': CARBON_DEPOSIT_STATUS_NOT_EVALUATED,
                'applied': False,
                'reason': ('no propellant context (oxidizer, fuel, O/F) was '
                           'supplied to the station march, so the carbon '
                           'deposit envelope cannot be checked; no deposit '
                           'resistance is modelled')}
        else:
            cd = dict(carbon_deposit)
            self.carbon_deposit_envelope = carbon_deposit_envelope(
                cd.get('oxidizer'), cd.get('fuel'), cd.get('mixture_ratio'),
                self.chamber_pressure)
        if (self.carbon_deposit_envelope['applied']
                and self.coolant in SUPERCRITICAL_COOLANT_FLUIDS):
            # Süperkritik soğutucu yolu (metan/hidrojen ceketi) birikim
            # modelini taşımaz — bit-aynı sözleşmesi (L-REJ), beyanlı.
            self.carbon_deposit_envelope = {
                'status': CARBON_DEPOSIT_STATUS_NOT_APPLICABLE,
                'applied': False,
                'reason': ('the supercritical (methane/hydrogen) coolant '
                           'path does not carry the carbon deposit model')}
        self.carbon_deposit_applied = bool(
            self.carbon_deposit_envelope['applied'])

    # ------------------------------------------------------------------
    @classmethod
    def from_motor_data(cls, motor_data: Dict, **kwargs) -> 'RegenCooling':
        """Build from a repo-style motor dictionary (chamber_pressure in bar)."""
        md = dict(motor_data or {})
        params = dict(
            chamber_pressure=float(md.get('chamber_pressure', 20.0)) * 1e5,
            chamber_temperature=float(md.get('chamber_temperature', 3000.0)),
            # ÖH D21 / B3-13(c) — SESSİZ 1,2 YEDEĞİ KALKTI, KÜNYE GELDİ.
            # Eski satır ``float(md.get('gamma', md.get('gamma_avg',
            # 1.2)))`` idi: γ hiç yokken 1,2 sessizce konuyor, üstelik
            # sayı kardeş iki modülde ayrı ayrı yazılıyordu. Sayı artık
            # ``GAMMA_REPO_DEFAULT`` tek kaynağından gelir ve nereden
            # geldiği ``gamma_source`` ile taşınır. ``gamma_avg`` adının
            # kendisi yalan söylüyor (üretici ``combustion_analysis``
            # oraya ODA gamma'sını koyar, ortalama değil); adın
            # düzeltilmesi üretici dosyayı gerektirir (hibrit kulvarı).
            gamma=_ozgul_isi_orani(md)[0],
            molecular_weight=float(md.get('molecular_weight', 24.0)),
            throat_diameter=md.get('throat_diameter'),
            exit_diameter=md.get('exit_diameter'),
            expansion_ratio=md.get('expansion_ratio'),
            motor_data=md,
        )
        params.update(kwargs)
        return cls(**params)

    # ------------------------------------------------------------------
    # Soğutucu özellik çözümü (CoolProp veya tablo)
    # ------------------------------------------------------------------
    def _cp_call(self, output: str, name1: str, value1: float,
                 name2: str, value2: float) -> float:
        """CoolProp PropsSI wrapper for the supercritical coolant fluid.

        Raises an EXPLICIT ValueError on any failure or non-finite result —
        no silent fallback to constants (fabricated-value guard policy).
        """
        try:
            val = float(_CP_PropsSI(output, name1, value1, name2, value2,
                                    self._cp_fluid))
        except Exception as exc:
            raise ValueError(
                f"CoolProp evaluation failed for {self._cp_fluid} "
                f"({output} at {name1}={value1:.6g}, {name2}={value2:.6g}): "
                f"{exc}. Coolant state is outside the EOS range — the model "
                "does not substitute constant values.") from exc
        if not math.isfinite(val):
            raise ValueError(
                f"CoolProp returned a non-finite {output} for "
                f"{self._cp_fluid} at {name1}={value1:.6g}, "
                f"{name2}={value2:.6g}.")
        return val

    def _saturation_temperature(self, pressure: float) -> float:
        """T_sat [K] at ``pressure`` (valid only below the critical pressure)."""
        return self._cp_call('T', 'P', pressure, 'Q', 0.0)

    def _coolant_properties(self, temperature: float,
                            pressure: float) -> Dict[str, float]:
        """Local coolant transport properties at (T, P).

        Water may use CoolProp (single-phase liquid); RP-1 always uses the
        internal table (no single CoolProp fluid). Falls back to the table on
        any CoolProp failure (e.g. two-phase state) with a flag.

        Methane / hydrogen ALWAYS use CoolProp (density, cp, conductivity,
        viscosity AND mass enthalpy at the local (T, P)); any failure raises
        an explicit error — there is no table and no constant fallback.
        """
        if self.coolant in SUPERCRITICAL_COOLANT_FLUIDS:
            rho = self._cp_call('D', 'T', temperature, 'P', pressure)
            cp = self._cp_call('C', 'T', temperature, 'P', pressure)
            k = self._cp_call('L', 'T', temperature, 'P', pressure)
            mu = self._cp_call('V', 'T', temperature, 'P', pressure)
            h = self._cp_call('Hmass', 'T', temperature, 'P', pressure)
            if rho <= 0.0 or cp <= 0.0 or k <= 0.0 or mu <= 0.0:
                raise ValueError(
                    f"Non-physical CoolProp properties for {self._cp_fluid} "
                    f"at T={temperature:.1f} K, P={pressure/1e5:.1f} bar.")
            self._props_sources_seen.add('coolprop')
            return {
                'density': rho, 'cp': cp, 'conductivity': k,
                'viscosity': mu, 'prandtl': cp * mu / k,
                'enthalpy': h, 'clamped': False, 'source': 'coolprop',
            }
        want_cp = (self.coolant_props_source == 'coolprop'
                   or (self.coolant_props_source == 'auto'))
        # ÖH D15 / P4B2-07: AÇIKÇA 'coolprop' istendiğinde tabloya SESSİZ
        # düşüş yok. Aşağıdaki ``except Exception: pass`` bunu yapıyordu:
        # CoolProp kurulu değilse ya da çağrı hata verirse aynı istek
        # farklı sayılarla (ölçüldü: ΔP +%0,22, hız −%0,79, kırpılan
        # istasyon 0 ⟷ 3, uyarı 0 ⟷ 1) ve hiçbir beyanla dönüyordu.
        # 'auto' kipinde düşüş MEŞRUDUR (kip zaten "varsa kullan" demektir)
        # ve fiilen kullanılan kaynak özette yayımlanır.
        acik_coolprop = (self.coolant_props_source == 'coolprop')
        if self.coolant == 'water' and want_cp:
            neden = None
            if not _HAS_COOLPROP:
                neden = 'CoolProp is not installed'
            else:
                try:  # pragma: no cover - ortam bağımlı
                    rho = float(_CP_PropsSI('D', 'T', temperature, 'P', pressure, 'Water'))
                    cp = float(_CP_PropsSI('C', 'T', temperature, 'P', pressure, 'Water'))
                    k = float(_CP_PropsSI('L', 'T', temperature, 'P', pressure, 'Water'))
                    mu = float(_CP_PropsSI('V', 'T', temperature, 'P', pressure, 'Water'))
                    if rho > 0 and cp > 0 and k > 0 and mu > 0:
                        self._props_sources_seen.add('coolprop')
                        return {
                            'density': rho, 'cp': cp, 'conductivity': k,
                            'viscosity': mu, 'prandtl': cp * mu / k,
                            'clamped': False, 'source': 'coolprop',
                        }
                    neden = ('CoolProp returned non-physical water '
                             'properties')
                except Exception as exc:
                    neden = 'CoolProp evaluation failed (%s)' % exc
            if acik_coolprop:
                raise ValueError(
                    "coolant_props_source='coolprop' was requested but the "
                    f"CoolProp path is unusable at T={temperature:.1f} K, "
                    f"P={pressure/1e5:.1f} bar: {neden}. The internal water "
                    "table is NOT substituted silently — it produces "
                    "different numbers and a different warning set for the "
                    "same request. Use coolant_props_source='auto' to accept "
                    "the table, or 'table' to request it explicitly.")
        props = (water_properties(temperature) if self.coolant == 'water'
                 else rp1_properties(temperature))
        props['source'] = 'table'
        self._props_sources_seen.add('table')
        return props

    # ------------------------------------------------------------------
    # Geometri: ortak kontur örnekleyiciden istasyon ızgarası
    # ------------------------------------------------------------------
    def _build_stations(self):
        """Sample the shared contour and build the x-ascending station grid.

        Returns ``x_mm``, ``r_mm`` (gas-side inner radius) and the throat index;
        the throat station is guaranteed on the grid (M=1 anchored exactly).

        ÖH Z5S / PK5 — İKİ ONARIM:

        **(1) P4B2-01 — SİLİNDİRİK KAMARA GÖVDESİ.** Izgara YALNIZ
        ``sample_nozzle_inner_contour`` üstünde kuruluyordu; o konturun z=0'ı
        KAMARA ÇIKIŞIDIR (``nozzle_design.py``), yani ceketin ısıttığı
        yüzeyin silindirik gövde kısmı modelde HİÇ YOKTU ve hiçbir girdiyle
        eklenemiyordu. ÖLÇÜLDÜ: ``chamber_length`` 0,10 m ⟷ 0,40 m ile
        ``total_heat_W`` BİT BİREBİR AYNI (126.913,760323 W) ve ızgara
        açıklığı iki durumda da 94,89 mm. Rapor ölçümü: gövde eklenirse ısı
        +%57,8..+89,5, T_out +142,6..+220,6 K, ceket ΔP +%45..56 — üç sayı da
        AŞAĞI yönde yanlıştı. Gövde artık ``motor_data['chamber_length']``
        verildiğinde konturun BAŞINA sabit yarıçaplı bir bölüm olarak eklenir
        (yarıçap konturun kendi ilk noktasıdır, ikinci bir geometri kaynağı
        uydurulmaz). Kamara boyu verilmezse davranış BİT-AYNI kalır.

        **(2) P4B2-11 — İSTASYON DAĞITIMI.** ÖLÇÜLEN kusur: ε=25 lülede
        konverjan bölüm TEK segmente sıkışıyordu (``throat_index=1``,
        n=20/30/40) ve birinci mertebe yukarı-akım entegrali o tek segmentin
        tamamını boğaz akısıyla dolduruyordu (raporda +%22,4 fazla sayım).
        İKİ ayrı değişiklik var; etkileri KARIŞTIRILMAMALIDIR:

        * **Çözünürlük tabanı** (``REGEN_MIN_INTERVALS_PER_SEGMENT``):
          ``throat_index >= 2`` garantisini SAĞLAYAN budur. Tek aralıklı bir
          bölüm hiç çözülmemiş demektir; taban bir fizik sabiti değil,
          ayrıklaştırma kuralıdır.
        * **Pay ölçüsü**: kalan aralıklar artık EKSENEL UZUNLUK yerine ISLAK
          YÜZEY ALANIYLA (∫2πr ds) dağıtılır — dağıtılan şey bir yüzey
          integrali olduğu için ölçünün doğrusu budur. Bu ölçü konverjanı
          BÜYÜTMEZ: ε=25 devresinde alan payı (%2,68) eksenel paydan
          (%5,47) daha KÜÇÜKTÜR. Isı yükünü ızgaradan bağımsız kılan asıl
          onarım, ``solve`` içindeki trapez marş şemasıdır.
        """
        # Tembel import: engines paketi -> analysis zinciri modül-üstü importta
        # döngü riski taşır (aynı gerekçe analyze_axial_profile'de belgelidir).
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour

        md_geo = dict(self.motor_data)
        md_geo['throat_diameter'] = self.throat_diameter
        md_geo['exit_diameter'] = self.exit_diameter
        md_geo.setdefault('chamber_diameter', 1.5 * self.throat_diameter)

        pts, meta = sample_nozzle_inner_contour(md_geo)
        z_pts = np.array([p[0] for p in pts], dtype=float)  # mm
        r_pts = np.array([p[1] for p in pts], dtype=float)  # mm
        z_throat = float(meta['z_throat'])
        z_exit = float(meta['z_exit'])
        r_throat = float(meta['r_throat'])

        # --- (1) Kamara gövdesi: konturun başına sabit yarıçaplı bölüm ----
        z_chamber_exit = float(z_pts[0])
        barrel_mm = self._barrel_length_mm()
        if barrel_mm > 0.0:
            z_pts = np.concatenate([[z_chamber_exit - barrel_mm], z_pts])
            r_pts = np.concatenate([[float(r_pts[0])], r_pts])
        z_start = float(z_pts[0])

        # --- (2) Bölüm sınırları ve ıslak-alan ağırlıkları ----------------
        sinirlar = [z_start]
        for kenar in (z_chamber_exit, z_throat, z_exit):
            if kenar > sinirlar[-1] + 1e-9:
                sinirlar.append(kenar)
        bolumler = list(zip(sinirlar[:-1], sinirlar[1:]))

        n = self.n_stations
        toplam_aralik = n - 1
        taban = REGEN_MIN_INTERVALS_PER_SEGMENT
        if toplam_aralik < taban * len(bolumler):
            # Izgara tabanları karşılanamıyorsa taban 1'e iner (kırpma sınırı
            # 20 istasyonda üç bölüm için bu dal ÇALIŞMAZ; savunma amaçlı).
            taban = max(1, toplam_aralik // max(len(bolumler), 1))

        agirliklar = [self._wetted_area_mm2(z_pts, r_pts, a, b)
                      for a, b in bolumler]
        agirlik_toplam = sum(agirliklar) or 1.0
        araliklar = [taban] * len(bolumler)
        kalan = toplam_aralik - taban * len(bolumler)
        if kalan > 0:
            paylar = [kalan * w / agirlik_toplam for w in agirliklar]
            tam = [int(math.floor(p)) for p in paylar]
            artik = kalan - sum(tam)
            # Kalan aralıklar en büyük ondalık paya sahip bölümlere gider
            # (Hamilton/en büyük artık yöntemi — deterministik).
            sira = sorted(range(len(paylar)), key=lambda i: -(paylar[i] - tam[i]))
            for i in sira[:artik]:
                tam[i] += 1
            araliklar = [araliklar[i] + tam[i] for i in range(len(bolumler))]

        parcalar = []
        for (a, b), adet in zip(bolumler, araliklar):
            dilim = np.linspace(a, b, adet + 1)
            parcalar.append(dilim if not parcalar else dilim[1:])
        x_mm = np.concatenate(parcalar)

        # Boğaz istasyonunun indeksi: boğaza kadar biriken aralık sayısı.
        throat_index = 0
        for (a, b), adet in zip(bolumler, araliklar):
            throat_index += adet
            if abs(b - z_throat) <= 1e-9:
                break

        r_mm = np.interp(x_mm, z_pts, r_pts)
        area_ratio = np.maximum((r_mm / r_throat) ** 2, 1.0)
        area_ratio[throat_index] = 1.0

        return {
            'x_mm': x_mm, 'r_mm': r_mm, 'area_ratio': area_ratio,
            'throat_index': throat_index, 'r_throat_mm': r_throat,
            'z_throat_mm': z_throat, 'z_exit_mm': z_exit,
            'chamber_barrel_length_mm': barrel_mm,
            'nozzle_type': meta.get('noz_type'),
        }

    def _barrel_length_mm(self) -> float:
        """Silindirik kamara gövdesinin eksenel boyu [mm]; yoksa 0,0.

        Kaynak TEK: ``motor_data['chamber_length']`` (m). Değer yoksa,
        sayı değilse ya da pozitif değilse gövde eklenmez — uydurma bir
        kamara boyu ÜRETİLMEZ (P4B2-01).
        """
        # ÖH D31 / P15B2-01 (OH-D30-08 dağıtımı, termo-ucus satırı): bu
        # YEREL değer kapısı merkeze BAĞLANDI. Eski gövde ``isinstance(ham,
        # bool)`` ile yalnız Python ``bool``unu eliyordu; ``numpy.bool_``
        # onun alt sınıfı DEĞİLDİR ve ``float(np.True_) == 1.0`` olduğu için
        # çözücüden dönen bir numpy doğruluk değeri buradan 1000,0 mm'lik
        # bir kamara gövdesi olarak geçiyordu. Merkez kapı
        # (``input_guard.finite_positive`` -> ``_is_bool``) dtype.kind='b'
        # ördek denetimiyle onu da eler; sonlu/pozitif kuralı aynıdır.
        deger_m = input_guard.finite_positive(
            self.motor_data.get('chamber_length'))
        if deger_m is None:
            return 0.0
        return float(deger_m) * 1000.0

    @staticmethod
    def _wetted_area_mm2(z_pts, r_pts, z_a: float, z_b: float) -> float:
        """[z_a, z_b] aralığının ıslak yüzey alanı ∫2πr ds [mm²].

        İstasyon paylarının ağırlığıdır: ısı entegralinin kendi ölçüsü
        budur (uzunluk değil), bu yüzden dağıtım da bununla yapılır.
        """
        kenarlar = np.unique(np.concatenate([
            [z_a, z_b], z_pts[(z_pts > z_a) & (z_pts < z_b)]]))
        r_kenar = np.interp(kenarlar, z_pts, r_pts)
        ds = np.hypot(np.diff(kenarlar), np.diff(r_kenar))
        r_ort = 0.5 * (r_kenar[:-1] + r_kenar[1:])
        return float(np.sum(2.0 * math.pi * r_ort * ds))

    def _seed_allowable_K(self):
        """Sabit nokta iterasyonunun BAŞLANGIÇ tahmini (K) — hüküm eşiği
        DEĞİL; yalnız ``min(bu, 0,8·T_aw)`` başlangıcını kurar.

        §28-31 (c) ölçümü (5. tur, 14 Eki): başlangıcı kanonik izin
        basamağına çekmek yakınsamış sonucu yakınsama toleransı içinde
        kaydırıyor (copper ceketi, t_w 1 mm: T_w,max 882,3096781 → 882,3096508
        K, bağıl 3,1e-8) ve bit-çapalı mevcut bekçiyi
        (test_d15_termo_ucus_a3::TestP4B2_09GeometriZarfi::
        test_ince_cidar_bandinda_sessiz, rel 1e-12) kırıyor. Hüküm eşikleri
        tek kaynağa bağlandı; başlangıç bayt-aynı kaldı ve ham alan okuması
        YALNIZ burada (AST bekçisi: tests/test_d37_sivi_a1.py
        test_28_31c_regen_ham_esik_alani_okunmaz). Başlangıcın da taşınması
        ana model kararı (devir).
        """
        return self.material.get('allowable_temperature',
                                 REGEN_SEED_ALLOWABLE_DEFAULT_K)

    # ------------------------------------------------------------------
    # Bir istasyonda kuple gaz-cidar dengesi (sabit nokta iterasyonu)
    # ------------------------------------------------------------------
    def _station_wall_balance(self, taw: float, t_coolant: float, h_c: float,
                              throat_d: float, c_star: float, rc_over_dt: float,
                              gas: Dict, area_ratio_local: float, mach: float,
                              k_wall: float, r_deposit: float = 0.0):
        """Solve the local (h_g, q, T_wall_hot, T_wall_cold) fixed point.

        ``h_g`` depends on the hot-wall temperature through the Bartz sigma
        correction; iterate until the wall temperature is self-consistent.
        Series circuit per unit gas-side area:
            q = (Taw - T_coolant) / (1/h_g + R_d + t_w/k_w + 1/h_c).

        V301/L-KARBON: ``r_deposit`` = carbon-deposit resistance R_d
        (``carbon_deposit_resistance``; NASA SP-125 Eq. 4-18). With
        R_d > 0 the Bartz sigma is evaluated at T_wg/T_c = 0.8 (SP-125
        Sample Calc. 4-3: the deposit surface approaches the gas
        temperature) and the returned hot-wall temperature is the METAL
        surface under the deposit, T_metal = Taw - q*(1/h_g + R_d).
        With R_d = 0 the arithmetic is the pre-L-KARBON one bit for bit.
        """
        r_cond = self.wall_thickness / k_wall     # m^2*K/W
        r_cool = 1.0 / h_c                          # m^2*K/W
        if r_deposit > 0.0:
            # Birikim: sigma sabit oranda (SP-125), yineleme gerekmez.
            h_g = self._hta._bartz_coefficient(
                throat_d, self.chamber_pressure, c_star, gas,
                self.chamber_temperature,
                CARBON_DEPOSIT_SIGMA_TWG_OVER_TC * self.chamber_temperature,
                rc_over_dt, area_ratio_local=area_ratio_local,
                mach_local=mach)
            q = (taw - t_coolant) / (1.0 / h_g + r_deposit + r_cond + r_cool)
            t_wall_hot = taw - q * (1.0 / h_g + r_deposit)
            t_wall_cold = t_coolant + q * r_cool
            return h_g, q, t_wall_hot, t_wall_cold
        allowable = self._seed_allowable_K()      # başlangıç; hüküm değil
        t_wall_hot = max(min(allowable, 0.8 * taw), t_coolant)
        h_g = 0.0
        q = 0.0
        for _ in range(60):
            h_g = self._hta._bartz_coefficient(
                throat_d, self.chamber_pressure, c_star, gas,
                self.chamber_temperature, t_wall_hot, rc_over_dt,
                area_ratio_local=area_ratio_local, mach_local=mach)
            r_total = 1.0 / h_g + r_cond + r_cool
            q = (taw - t_coolant) / r_total
            new_hot = taw - q / h_g
            if abs(new_hot - t_wall_hot) < 1e-3:
                t_wall_hot = new_hot
                break
            t_wall_hot = new_hot
        t_wall_cold = t_coolant + q * r_cool
        return h_g, q, t_wall_hot, t_wall_cold

    # ------------------------------------------------------------------
    # V301/L-REJ — kanat (fin) alan oranı: TEK işlev, her soğutucu yolu
    # ------------------------------------------------------------------
    def _channel_pitch_land(self, r_local: float):
        """(adım, kaburga genişliği) [m] — yerel gaz yarıçapında.

        Adım kanal TABANI çevresinden (r_gaz + t_cidar; ``channel_fit_limit``
        ile aynı yarıçap tanımı) kanal sayısına bölünür; kaburga = adım − w.
        """
        pitch = (2.0 * math.pi * (r_local + self.wall_thickness)
                 / self.n_channels)
        return pitch, pitch - self.channel_width

    def _fin_ratio(self, r_local: float, h_c: float, k_wall: float) -> float:
        """Soğutucu tarafı genişletilmiş yüzey oranı A_eff/A_gaz.

        ``fin_effect`` kapalıysa 1 (soğutucu alanı = gaz alanı). Açıksa
        ``fin_area_ratio`` (Incropera Böl. 3.6, uç adyabatik; kaburgalar
        kanat, Huzel & Huang Böl. 4). İletkenlik astarın
        ``thermal_conductivity`` değeridir — cidar iletim direnciyle AYNI
        sayı (tek kaynak); malzeme veritabanının sıcaklığa bağlı ``k_curve``
        alanı yalnız cucrzr'de var ve bu modelde kullanılmaz (künyede
        beyanlı).
        """
        if not self.fin_effect:
            return 1.0
        pitch, land = self._channel_pitch_land(r_local)
        return fin_area_ratio(self.channel_width, self.channel_height, pitch,
                              land, h_c, k_wall)

    def _liquid_wall_viscosity_ratio(self, t_bulk: float, t_wall: float):
        """(mu_b, mu_w, mu_w tablo kenarında mı) — Sieder-Tate oranı için.

        İki viskozite de soğutucunun İÇ sıvı tablosundan okunur (oran tek
        kaynaktan; su CoolProp'la sürülse bile cidar tarafı buhar özelliğine
        kaymaz). Cidar tablo bandının üstündeyse mu_w bant kenarındaki
        değerde tutulur ve bu ``True`` olarak döner (çağıran sayar, beyan
        eder).
        """
        tablo = _WATER_TABLE if self.coolant == 'water' else _RP1_TABLE
        mu_b = _interp_table(tablo, t_bulk)['viscosity']
        duvar = _interp_table(tablo, t_wall)
        return mu_b, duvar['viscosity'], bool(t_wall > duvar['table_t_max_K'])

    def _station_wall_balance_liquid(self, taw: float, t_coolant: float,
                                     h_db: float, throat_d: float,
                                     c_star: float, rc_over_dt: float,
                                     gas: Dict, area_ratio_local: float,
                                     mach: float, k_wall: float,
                                     r_local: float, r_deposit: float = 0.0):
        """Sıvı (su/RP-1) istasyon dengesi: Sieder-Tate + kanat kuple.

        ``r_deposit``: karbon birikimi direnci (V301/L-KARBON; 0 = yok).

        h_c = h_DB · (mu_b/mu_w(T_wc))^0,14 (NASA SP-125 Eş. 4-23) ve
        h_etkin = h_c · A_eff/A_gaz (``_fin_ratio``). İkisi de soğutucu
        tarafı cidar sıcaklığına bağlıdır; sabit nokta T_wc üzerinden
        kurulur (başlangıç T_wc = T_yığın, yani çarpan 1).

        Döner: (h_g, q, T_hot, T_cold, h_c, a_ratio, st_factor,
        mu_w_clamped, converged).
        """
        t_wc = float(t_coolant)
        h_g = q = tw_hot = tw_cold = 0.0
        h_c = h_db
        a_ratio = 1.0
        st = 1.0
        kenar = False
        yakinsadi = False
        for _ in range(REGEN_LIQUID_WALL_MAX_ITER):
            mu_b, mu_w, kenar = self._liquid_wall_viscosity_ratio(
                t_coolant, t_wc)
            st = sieder_tate_factor(mu_b, mu_w)
            h_c = h_db * st
            a_ratio = self._fin_ratio(r_local, h_c, k_wall)
            h_g, q, tw_hot, tw_cold = self._station_wall_balance(
                taw, t_coolant, h_c * a_ratio, throat_d, c_star, rc_over_dt,
                gas, area_ratio_local=area_ratio_local, mach=mach,
                k_wall=k_wall, r_deposit=r_deposit)
            if abs(tw_cold - t_wc) < REGEN_LIQUID_WALL_TOL_K:
                yakinsadi = True
                break
            t_wc = tw_cold
        return (h_g, q, tw_hot, tw_cold, h_c, a_ratio, st, kenar, yakinsadi)

    # ------------------------------------------------------------------
    # Süperkritik istasyon dengesi (Jackson — cidar özellik oranlı)
    # ------------------------------------------------------------------
    def _station_wall_balance_sc(self, taw: float, t_bulk: float,
                                 p_bulk: float, bulk: Dict, reynolds: float,
                                 throat_d: float, c_star: float,
                                 rc_over_dt: float, gas: Dict,
                                 area_ratio_local: float, mach: float,
                                 k_wall: float, t_pc: float,
                                 r_local: float):
        """Coupled wall balance with the Jackson supercritical coolant Nu.

        Unlike the Dittus-Boelter path, the coolant-side coefficient depends
        on the COLD-wall temperature through the (rho_w/rho_b) and
        (cp_bar/cp_b) property ratios (Jackson & Hall 1979). The fixed point
        over (T_wall_hot, T_wall_cold) is solved with damped iteration:

            q = (Taw - T_bulk) / (1/h_g(T_hot) + t_w/k_w + 1/(h_c*A_r))
            T_hot  <- Taw   - q/h_g,    T_cold <- T_bulk + q/(h_c*A_r)

        where A_r is the coolant-side extended-surface (channel-land fin)
        area ratio (``fin_area_ratio``; = 1 when ``fin_effect`` is False).
        Wall-side properties are evaluated at (min(T_cold, T_max_EOS), P);
        clamping at the EOS limit is COUNTED and reported as an explicit
        warning (the wall-limit warnings fire independently).

        ``r_local`` is the local gas-side inner radius [m] (sets the channel
        pitch for the fin geometry).

        Returns (h_g, q, T_wall_hot, T_wall_cold, h_c, nu, a_ratio,
        converged, wall_props_clamped).
        """
        r_cond = self.wall_thickness / k_wall       # m^2*K/W
        allowable = self._seed_allowable_K()        # başlangıç; hüküm değil
        t_wall_hot = max(min(allowable, 0.8 * taw), t_bulk)
        t_wall_cold = t_bulk + 30.0
        rho_b = bulk['density']
        cp_b = bulk['cp']
        h_b = bulk['enthalpy']
        k_b = bulk['conductivity']
        pr_b = bulk['prandtl']
        # Kanat geometrisi (adım/kaburga) ``_fin_ratio`` içinde — tek işlev.
        damping = 0.6            # sabit nokta sönümü (cp_bar hassasiyeti için)
        tol = 1.0e-3             # K
        h_g = 0.0
        h_c = 0.0
        q = 0.0
        nu = 0.0
        a_ratio = 1.0
        converged = False
        wall_props_clamped = False
        for _ in range(100):
            # Cidar tarafı özellik değerlendirme sıcaklığı (EOS içinde tut).
            t_eval = min(max(t_wall_cold, self._fluid_tmin), self._fluid_tmax)
            if t_eval != t_wall_cold:
                wall_props_clamped = True
            rho_w = self._cp_call('D', 'T', t_eval, 'P', p_bulk)
            h_w = self._cp_call('Hmass', 'T', t_eval, 'P', p_bulk)
            if abs(t_eval - t_bulk) > 0.1:
                # cp_bar = (h_w - h_b)/(T_w - T_b): entegre ortalama özgül ısı
                cp_bar = (h_w - h_b) / (t_eval - t_bulk)
            else:
                cp_bar = cp_b
            if cp_bar <= 0.0:
                cp_bar = cp_b  # h(T) monoton — negatif çıkamaz; sayısal koruma
            n_exp = jackson_exponent_n(t_bulk, t_eval, t_pc)
            nu = jackson_nu(reynolds, pr_b, rho_w / rho_b,
                            cp_bar / cp_b, n_exp)
            h_c = nu * k_b / self.hydraulic_diameter
            a_ratio = self._fin_ratio(r_local, h_c, k_wall)
            h_g = self._hta._bartz_coefficient(
                throat_d, self.chamber_pressure, c_star, gas,
                self.chamber_temperature, t_wall_hot, rc_over_dt,
                area_ratio_local=area_ratio_local, mach_local=mach)
            r_cool = 1.0 / (h_c * a_ratio)
            r_total = 1.0 / h_g + r_cond + r_cool
            q = (taw - t_bulk) / r_total
            new_hot = taw - q / h_g
            new_cold = t_bulk + q * r_cool
            if (abs(new_hot - t_wall_hot) < tol
                    and abs(new_cold - t_wall_cold) < tol):
                t_wall_hot, t_wall_cold = new_hot, new_cold
                converged = True
                break
            t_wall_hot += damping * (new_hot - t_wall_hot)
            t_wall_cold += damping * (new_cold - t_wall_cold)
        return (h_g, q, t_wall_hot, t_wall_cold, h_c, nu, a_ratio, converged,
                wall_props_clamped)

    # ------------------------------------------------------------------
    # Ana çözüm: istasyon marşı
    # ------------------------------------------------------------------
    def solve(self) -> Dict:
        """Run the 1D station march and return station arrays + summary.

        Returns a dict with per-station arrays (``x_mm``, ``T_wall_hot_K``,
        ``T_wall_cold_K``, ``T_coolant_K``, ``P_coolant_bar``, ``q_MW_m2``,
        ``velocity_m_s`` and diagnostic companions), a ``summary`` block
        (peak wall temperature, material-limit comparison, total pressure
        drop, coolant exit temperature, coking status, warnings) and a
        ``model_note`` describing assumptions and validity.
        """
        # ÖH D15 / P4B2-07: kaynak künyesi HER koşuma özgüdür (aynı nesne
        # ikinci kez çözülürse önceki koşumun kaynağı taşınmaz).
        self._props_sources_seen = set()
        geo = self._build_stations()
        x_mm = geo['x_mm']
        r_mm = geo['r_mm']
        area_ratio = geo['area_ratio']
        throat_index = geo['throat_index']
        n = self.n_stations

        # Gaz özellikleri + boğaz koşulları (tek kaynak).
        mdot_total = self.motor_data.get('mdot_total', 1.0)
        gas = self._hta._get_gas_properties(self._md_gas, self.chamber_temperature)
        throat = self._hta._resolve_throat_conditions(
            self._md_gas, self.chamber_pressure, self.chamber_temperature,
            gas, mdot_total)
        throat_d = throat['throat_diameter']
        c_star = throat['c_star']
        # ÖH D15 / P4B2-08 — BARTZ'I SÜREN c* ARTIK ÇIKTIDA BEYAN EDİLİYOR.
        # ÖLÇÜLDÜ (31 Ağustos 2026, taban e88d096; Pc = 70 bar, Tc = 3500 K,
        # Dt = 0,10 m, eps = 25, su, mdot = 12 kg/s):
        #   motor_data c*'sız         -> tepe akı 40,4402 MW/m²,
        #                                max_wall_hot_K = 882,3097
        #   motor_data={'c_star':1650}-> tepe akı 41,1908 MW/m² (+%1,86),
        #                                max_wall_hot_K = 890,4676 (+8,16 K)
        # ve özet sözlüğünde c*'ı adlandıran HİÇBİR alan yoktu
        # ([k for k in summary if 'c_star' in k] -> []). Bu modül —
        # kardeş NozzleFlow1D'nin aksine — kendi analitik c*'ını yayımlamaz
        # ve debiyi c*'tan kurmaz, dolayısıyla kullanıcının ölçtüğü c*
        # burada TUTARLIDIR; eksik olan tek şey BEYANDI. Sayı ve kaynağı
        # özette yayımlanır (aşağıya bkz.).
        c_star_source = throat.get('c_star_source')
        rc_over_dt = throat['rc_over_dt']
        k_wall = self.material['thermal_conductivity']

        # Her istasyonda Mach + recovery sıcaklığı (soğutmadan bağımsız).
        mach = np.empty(n)
        taw = np.empty(n)
        for i in range(n):
            supersonic = i > throat_index
            m = self._hta._mach_from_area_ratio(area_ratio[i], self.gamma, supersonic)
            mach[i] = m
            taw[i] = self._hta._adiabatic_wall_temperature(
                self.chamber_temperature, gas, m)

        # Marş sırası: geometrik indeks listesi (soğutucu akış yönünde).
        if self.flow_direction == FLOW_COUNTERFLOW:
            order = list(range(n - 1, -1, -1))   # çıkış -> kamara
        else:
            order = list(range(n))               # kamara -> çıkış

        # V301/L-KARBON — istasyon başına karbon birikimi direnci (TEK
        # işlev ``carbon_deposit_resistance``). Şekil 4-25'in genişleme
        # ucunun (eps 14,8) ötesindeki istasyonlarda direnç UYGULANMAZ
        # (R_d = 0, tutucu yön) ve sayısı beyan edilir.
        r_dep = np.zeros(n)
        rd_figure_out = 0
        if self.carbon_deposit_applied:
            for i in range(n):
                rd = carbon_deposit_resistance(area_ratio[i],
                                               supersonic=i > throat_index)
                if rd is None:
                    rd_figure_out += 1
                else:
                    r_dep[i] = rd
        # Birikimsiz (dökülmüş) yerel cidar — SP-8087 §3.4.1 denetimi; aynı
        # soğutucu durumunda R_d = 0 ile çözülür (yalnız birikim varsa).
        t_wall_hot_spall = np.full(n, np.nan)
        t_wall_cold_spall = np.full(n, np.nan)
        q_spall = np.full(n, np.nan)

        # Çıktı dizileri (geometrik indekse göre doldurulur).
        t_coolant = np.empty(n)
        p_coolant = np.empty(n)
        t_wall_hot = np.empty(n)
        t_wall_cold = np.empty(n)
        q_flux = np.empty(n)          # W/m^2
        velocity = np.empty(n)
        reynolds = np.empty(n)
        h_gas = np.empty(n)
        h_cool = np.empty(n)

        r_m = r_mm / 1000.0           # m
        x_m = x_mm / 1000.0           # m

        # ================================================================
        # ÖH Z5S / PK5 (P4B2-11) — MARŞ ŞEMASI SABİT NOKTASI
        # ----------------------------------------------------------------
        # ÖLÇÜLEN KUSUR: segment ısısı dQ = q·dA'da q YALNIZ YUKARI-AKIM
        # istasyonundan alınıyordu (birinci mertebe). Sonuç, yayımlanan
        # ``q_MW_m2`` dizisinin BAĞIMSIZ trapez entegraliyle yayımlanan
        # ``total_heat_W``in çelişmesiydi: taban devrede 127.393,47 W ⟷
        # 126.913,76 W (%0,378), ε=25 devrede 4.618.774,0 W ⟷ 4.545.511,6 W
        # (%1,61). Aynı fiziksel büyüklük iki kanaldan iki sayıyla
        # yayımlanamaz; ayrıca toplam IZGARAYA bağımlıydı (Q(20)=4.429.234 W
        # ⟷ Q(50)=4.545.512 W, %2,56 salınım).
        #
        # ONARIM: segment ısısı iki uç istasyonun akı ORTALAMASIYLA alınır
        # (trapez, ikinci mertebe). Aşağı-akım istasyonunun akısı soğutucu
        # sıcaklığına bağlı olduğundan şema örtüktür; marş bir SABİT NOKTA
        # iterasyonuyla kapatılır: ilk geçiş yukarı-akım (öngörü), sonraki
        # geçişler bir önceki geçişin akı dizisiyle düzeltme yapar.
        # Yakınsadığında yayımlanan dizi ile yayımlanan toplam AYNI trapez
        # kuralından çıkar, yani ``independent_wetted_integral`` ile
        # sayısal gürültü mertebesinde örtüşürler.
        #
        # KIRILAN BEKÇİ (bilinçli, raporlanır):
        # ``test_energy_balance_surface_integral`` toplamı YUKARI-AKIM
        # şemasıyla yeniden kuruyor ve rel=1e-9 istiyordu; o kilit şemanın
        # KENDİSİNE çakılıydı. İddiası ("toplam, yayımlanan dizilerle aynı
        # şemadan çıkar") kardeş bekçi
        # ``test_energy_balance_independent_quadrature`` tarafından — ve
        # şemadan bağımsız olarak — kapsanır.
        # ================================================================
        q_onceki = None
        toplam_onceki = None
        marş_gecisi = 0
        for marş_gecisi in range(1, REGEN_MARCH_MAX_PASSES + 1):
            # Marş durumu
            t_c = self.coolant_inlet_temp
            p_c = self.coolant_inlet_pressure
            total_heat_W = 0.0
            enthalpy_rise = 0.0           # J/kg (cp*dT integrali / h marşı)
            min_re = np.inf
            # ÖH D22 / P4B2-10 — DITTUS-BOELTER ZARFININ TARANDIĞI GİRDİLER.
            # ``dittus_boelter_envelope`` (F154) yazılmıştı ama ÇAĞIRANI
            # YOKTU: ölçüldü (taban b84b10a, ``once.json`` P4B2-10),
            # modülde tanım dışında 0 çağrı; solve() yalnız Reynolds'u
            # tarıyordu (``min_re < RE_TURBULENT_FLOOR``). Pr bandı ve
            # giriş-uzunluğu (L/D) koşulu hiç denetlenmiyordu.
            db_pr_min = np.inf
            db_pr_max = -np.inf
            db_stations = 0
            channel_len_m = 0.0

            # --- süperkritik (metan/hidrojen) marş durumu: entalpi tabanlı ---
            sc_mode = self.coolant in SUPERCRITICAL_COOLANT_FLUIDS
            h_bulk = 0.0
            h_inlet = 0.0
            coolant_h = np.full(n, np.nan)   # J/kg (yalnız sc modda dolar)
            fin_ratio = np.ones(n)           # A_eff/A_gas (V301/L-REJ: her yol)
            # V301/L-REJ: Sieder-Tate çarpanı (yalnız su/RP-1; diğerlerinde 1)
            # ve mu_w'nun tablo kenarında tutulduğu istasyon sayısı.
            st_factor = np.ones(n)
            st_wall_edge_stations = 0
            dp_friction_total = 0.0
            dp_accel_total = 0.0
            n_jackson = 0                    # Jackson kullanılan istasyon sayısı
            n_db_subcritical = 0             # kritik-altı Dittus-Boelter istasyonu
            wall_balance_unconverged = 0
            jackson_wall_clamped = 0
            # F057: tablo bandı dışına taşan (özellikleri donmuş) istasyon sayacı
            table_clamped_stations = 0
            table_clamp_t_min = math.inf
            table_clamp_t_max = -math.inf
            table_band: Optional[tuple] = None
            bulk_boiling_stations = 0
            near_boiling_stations = 0
            wall_boiling_stations = 0
            if sc_mode:
                h_inlet = self._coolant_properties(t_c, p_c)['enthalpy']
                h_bulk = h_inlet

            for step, idx in enumerate(order):
                # --- soğutucu tarafı katsayısı (yerel yığın özellikleriyle) ---
                props = self._coolant_properties(t_c, p_c)
                rho = props['density']
                cp = props['cp']
                k_c = props['conductivity']
                mu = props['viscosity']
                pr = props['prandtl']

                # F057: tablo yolunda banda klamplanan istasyonları kaydet.
                # Klamp, özellikleri banda DONDURUR (rho/mu/Pr sabit kalır) —
                # sessizce yapılırsa kullanıcı geçerlilik zarfı dışına çıktığını
                # göremez. Uyarı marş sonunda toplu üretilir.
                if props.get('clamped'):
                    table_clamped_stations += 1
                    table_clamp_t_min = min(table_clamp_t_min, t_c)
                    table_clamp_t_max = max(table_clamp_t_max, t_c)
                    table_band = (props['table_t_min_K'], props['table_t_max_K'])

                v = self.mdot_per_channel / (rho * self.channel_area)  # m/s
                re = rho * v * self.hydraulic_diameter / mu

                if sc_mode and p_c > self.coolant_pcrit:
                    # --- süperkritik bölge: Jackson + kuple cidar dengesi ---
                    t_pc_local = pseudocritical_temperature(self._cp_fluid, p_c)
                    (h_g, q, tw_hot, tw_cold, h_c, nu, a_ratio, converged,
                     clamped) = self._station_wall_balance_sc(
                        taw[idx], t_c, p_c, props, re, throat_d, c_star,
                        rc_over_dt, gas, area_ratio_local=1.0 / area_ratio[idx],
                        mach=mach[idx], k_wall=k_wall, t_pc=t_pc_local,
                        r_local=r_m[idx])
                    fin_ratio[idx] = a_ratio
                    n_jackson += 1
                    if not converged:
                        wall_balance_unconverged += 1
                    if clamped:
                        jackson_wall_clamped += 1
                else:
                    nu = dittus_boelter_nu(re, pr, heating=True)
                    h_c = nu * k_c / self.hydraulic_diameter           # W/m^2/K
                    # P4B2-10: korelasyonun FİİLEN kullanıldığı istasyonların
                    # Prandtl uçları (zarf taraması bunlardan kurulur).
                    db_stations += 1
                    db_pr_min = min(db_pr_min, pr)
                    db_pr_max = max(db_pr_max, pr)

                    if sc_mode:
                        # Metan/hidrojen kritik-altı yedeği: kanat oranı
                        # (h_c cidara bağlı değil -> kapalı form); Sieder-
                        # Tate bu yedekte UYGULANMAZ (sıvı tablosu yok;
                        # süperkritik yol bit-aynı kalır — L-REJ sınırı).
                        a_ratio = self._fin_ratio(r_m[idx], h_c, k_wall)
                        fin_ratio[idx] = a_ratio
                        h_g, q, tw_hot, tw_cold = self._station_wall_balance(
                            taw[idx], t_c, h_c * a_ratio, throat_d, c_star,
                            rc_over_dt, gas,
                            area_ratio_local=1.0 / area_ratio[idx],
                            mach=mach[idx], k_wall=k_wall)
                    else:
                        # V301/L-REJ: su/RP-1 — Sieder-Tate + kanat, kuple
                        # (yayımlanan h_c Sieder-Tate düzeltmeli konveksiyon
                        # katsayısıdır; kanat oranı fin_area_ratio dizisinde,
                        # süperkritik yolla aynı yayım biçimi).
                        h_db = h_c
                        (h_g, q, tw_hot, tw_cold, h_c, a_ratio, st_carpan,
                         st_kenar, st_yakinsadi) = \
                            self._station_wall_balance_liquid(
                                taw[idx], t_c, h_db, throat_d, c_star,
                                rc_over_dt, gas,
                                area_ratio_local=1.0 / area_ratio[idx],
                                mach=mach[idx], k_wall=k_wall,
                                r_local=r_m[idx], r_deposit=r_dep[idx])
                        if r_dep[idx] > 0.0:
                            # V301/L-KARBON — SP-8087 §3.4.1: aynı yığın
                            # durumunda birikim dökülmüş yerel cidar.
                            _sp = self._station_wall_balance_liquid(
                                taw[idx], t_c, h_db, throat_d, c_star,
                                rc_over_dt, gas,
                                area_ratio_local=1.0 / area_ratio[idx],
                                mach=mach[idx], k_wall=k_wall,
                                r_local=r_m[idx], r_deposit=0.0)
                            q_spall[idx] = _sp[1]
                            t_wall_hot_spall[idx] = _sp[2]
                            t_wall_cold_spall[idx] = _sp[3]
                        fin_ratio[idx] = a_ratio
                        st_factor[idx] = st_carpan
                        if st_kenar:
                            st_wall_edge_stations += 1
                        if not st_yakinsadi:
                            wall_balance_unconverged += 1

                    if sc_mode:
                        # Kritik-altı basınç: kaynama riski denetimi (yerel Tsat).
                        n_db_subcritical += 1
                        t_sat = self._saturation_temperature(p_c)
                        if t_c >= t_sat:
                            bulk_boiling_stations += 1
                        elif t_c > t_sat - BOILING_MARGIN_K:
                            near_boiling_stations += 1
                        if tw_cold > t_sat:
                            wall_boiling_stations += 1

                # istasyon çıktıları
                t_coolant[idx] = t_c
                p_coolant[idx] = p_c
                t_wall_hot[idx] = tw_hot
                t_wall_cold[idx] = tw_cold
                q_flux[idx] = q
                velocity[idx] = v
                reynolds[idx] = re
                h_gas[idx] = h_g
                h_cool[idx] = h_c
                min_re = min(min_re, re)
                if sc_mode:
                    coolant_h[idx] = h_bulk

                # --- segment (idx -> sonraki marş istasyonu): ısı + basınç ---
                if step < len(order) - 1:
                    nxt = order[step + 1]
                    # eğik (slant) uzunluk ve ortalama gaz-tarafı yarıçapı
                    ds = math.hypot(x_m[nxt] - x_m[idx], r_m[nxt] - r_m[idx])  # m
                    channel_len_m += ds   # P4B2-10: L/D için toplam kanal boyu
                    r_mean = 0.5 * (r_m[idx] + r_m[nxt])
                    dA = 2.0 * math.pi * r_mean * ds                          # m^2
                    # P4B2-11: segment akısı İKİ UÇ istasyonun ortalamasıdır
                    # (trapez). İlk geçişte aşağı-akım akısı henüz yoktur;
                    # o geçiş yukarı-akım ÖNGÖRÜSÜDÜR ve sonraki geçişlerde
                    # düzeltilir.
                    if q_onceki is None:
                        q_seg = q
                    else:
                        q_seg = 0.5 * (q + float(q_onceki[nxt]))
                    dQ = q_seg * dA                                           # W
                    total_heat_W += dQ
                    # basınç düşümü (Darcy-Weisbach + Haaland), kanal eğik uzunluğu
                    f = haaland_friction_factor(re, self.wall_roughness / self.hydraulic_diameter)
                    dP = darcy_weisbach_dp(f, ds, self.hydraulic_diameter, rho, v)
                    if sc_mode:
                        # ENTALPİ marşı: h2 = h1 + dQ/mdot, T = T(P, h).
                        # Pseudo-kritik cp tepesinde dT = dQ/(m*cp) formunun
                        # sıcaklık hatasını önler (modül üst dokümantasyonu).
                        dh = dQ / self.coolant_mdot
                        h_next = h_bulk + dh
                        p_tmp = p_c - dP
                        if p_tmp <= 0.0:
                            raise ValueError(
                                "Coolant pressure fell to zero during the march "
                                "(friction) — channel geometry/mdot infeasible.")
                        # İvmelenme (momentum) terimi: yoğunluk değişimi.
                        rho_next = self._cp_call('D', 'P', p_tmp, 'Hmass', h_next)
                        g_flux = self.mdot_per_channel / self.channel_area
                        dP_acc = acceleration_dp(g_flux, rho, rho_next)
                        p_next = p_tmp - dP_acc
                        if p_next <= 0.0:
                            raise ValueError(
                                "Coolant pressure fell to zero during the march "
                                "(acceleration) — channel geometry/mdot "
                                "infeasible.")
                        t_next = self._cp_call('T', 'P', p_next, 'Hmass', h_next)
                        dp_friction_total += dP
                        dp_accel_total += dP_acc
                        enthalpy_rise += dh
                        t_c, p_c, h_bulk = t_next, p_next, h_next
                    else:
                        # soğutucu sıcaklık artışı (yerel cp ile) — su/RP-1
                        # davranışı BİREBİR korunur (regresyon sözleşmesi).
                        dT = dQ / (self.coolant_mdot * cp)
                        enthalpy_rise += cp * dT
                        dp_friction_total += dP
                        # marş: bir sonraki istasyona taşı
                        t_c = t_c + dT
                        p_c = p_c - dP

                    # ÖH Z5S / PK5 (P4B2-03) — FİZİK KAPISI, FAIL-CLOSED.
                    # ÖLÇÜLEN KUSUR: marşta sıcaklığın fizikselliği HİÇ
                    # sorulmuyordu. mdot = 1e-9 kg/s ile T_coolant_K min
                    # −3.178.605 K, max +2.028.370 K, MUTLAK SIFIRIN ALTINDA
                    # 14 istasyon ve coolant_exit_temp_K = 3510,25 K
                    # yayımlanıyordu; üretilen 4 uyarının hiçbiri negatifliği
                    # ADLANDIRMIYORDU (PROPERTY RANGE uyarısı sayıyı metnine
                    # basıyor ama kusur demiyordu). Mutlak sıcaklık ölçeğinin
                    # altına inen bir marş artık SAYI YAYIMLAMAZ: durur ve
                    # nedenini söyler. Kardeş modülün deseni budur
                    # (``thermal_protection``: zarf dışında sayı üretmek
                    # yerine 'MODEL OUT OF ENVELOPE' + NOT_MODELLED).
                    if not (math.isfinite(t_c) and t_c > 0.0):
                        raise ValueError(
                            "Coolant bulk temperature left the absolute "
                            f"temperature scale during the march (T = {t_c!r} "
                            f"K at station {nxt}). A regenerative circuit "
                            "cannot be evaluated from a non-physical state, "
                            "so no station values are published. Check "
                            "coolant_mdot, the channel count and the channel "
                            "cross-section: an almost-zero flow rate makes "
                            "dT = dQ/(mdot*cp) diverge.")
                    if not (math.isfinite(p_c) and p_c > 0.0):
                        raise ValueError(
                            "Coolant pressure fell to zero or below during "
                            f"the march (P = {p_c!r} Pa at station {nxt}) — "
                            "channel geometry/mdot infeasible.")

            # Sabit nokta ölçütü: yayımlanan toplam ısıdaki bağıl değişim.
            if toplam_onceki is not None and total_heat_W > 0.0:
                if abs(total_heat_W - toplam_onceki) <= \
                        REGEN_MARCH_TOL * abs(total_heat_W):
                    break
            toplam_onceki = total_heat_W
            q_onceki = q_flux.copy()


        # --- özet ---
        t_out = t_c                     # marş sonundaki soğutucu sıcaklığı
        t_in = self.coolant_inlet_temp
        dT_total = t_out - t_in
        cp_mean = enthalpy_rise / dT_total if abs(dT_total) > 1e-12 else 0.0
        total_dP = self.coolant_inlet_pressure - p_c
        p_out = p_c

        max_wall_hot = float(np.max(t_wall_hot))
        max_wall_hot_idx = int(np.argmax(t_wall_hot))
        max_wall_cold = float(np.max(t_wall_cold))
        # Karar §28-31 (c): TEK EŞİK — kanonik izin basamağı. Eski hâlde
        # WARNING ham izinden (copper/4130 1000 K), UNSAFE 'service limit'
        # diye ERİMEDEN (erişilemez dal), CRITICAL erimeden okunuyordu.
        # Artık iki basamak: izin (= yayımlanan 'service limit', aynı
        # motorun ısıl koruma künyesiyle AYNI sayı) ve erime. İzin ile servis
        # arasında ayrı bir 'WARNING' basamağı YOK: tek eşikte o dal
        # tanım gereği erişilemezdi (ölü dal bırakılmadı).
        allowable = float(self.temperature_ladder['allowable_K'])
        max_service = allowable
        melting = float(self.temperature_ladder['melting_K'])

        warnings_list: List[str] = []

        # malzeme limiti kıyası
        if max_wall_hot > melting:
            warnings_list.append(
                f"CRITICAL: peak hot-wall temperature {max_wall_hot:.0f} K "
                f"exceeds {self.material.get('name', self.wall_material)} melting "
                f"point {melting:.0f} K — liner failure.")
        elif max_wall_hot > max_service:
            warnings_list.append(
                f"UNSAFE: peak hot-wall temperature {max_wall_hot:.0f} K exceeds "
                f"{self.material.get('name', self.wall_material)} service limit "
                f"{max_service:.0f} K.")

        # V301/L-KARBON — birikim beyanı ve SP-8087 §3.4.1 dökülme denetimi.
        # Yayımlanan tepe cidar (max_wall_hot) birikimin ALTINDAKİ metaldir
        # (nominal, SP-125). Bandın tutucu ucu aynı soğutucu durumunda
        # birikimsiz yerel cidardır; o ERİMEYİ aşarsa hüküm KRİTİK'tir
        # ("localized spalling ... shall not result in chamber failure").
        cd_env = self.carbon_deposit_envelope
        cd_block = {
            'status': cd_env['status'],
            'applied': bool(cd_env['applied']),
            'reason': cd_env['reason'],
            'basis': CARBON_DEPOSIT_BASIS,
        }
        if self.carbon_deposit_applied:
            _ti = int(throat_index)
            spall_peak = float(np.nanmax(t_wall_hot_spall))
            spall_cold_peak = float(np.nanmax(t_wall_cold_spall))
            cd_block.update({
                'resistance_throat_m2K_W': float(r_dep[_ti]),
                'resistance_throat_in2sF_Btu': float(
                    r_dep[_ti] / CARBON_DEPOSIT_RD_US_TO_SI),
                'resistance_max_m2K_W': float(np.max(r_dep)),
                'sigma_twg_over_tc': CARBON_DEPOSIT_SIGMA_TWG_OVER_TC,
                'stations_with_deposit': int(np.count_nonzero(r_dep > 0.0)),
                'stations_beyond_figure_not_applied': int(rd_figure_out),
                'deposit_surface_temperature_throat_K': float(
                    taw[_ti] - q_flux[_ti] / h_gas[_ti]),
                'band': {
                    'nominal': {
                        'source': 'SP-125 Fig. 4-25 (with deposit)',
                        'peak_wall_hot_K': max_wall_hot,
                        'peak_wall_cold_K': max_wall_cold,
                        'peak_heat_flux_MW_m2': float(np.max(q_flux)) / 1e6,
                    },
                    'conservative': {
                        'source': ('no deposit / locally spalled, same '
                                   'coolant state (SP-8087 sec. 3.4.1)'),
                        'peak_wall_hot_K': spall_peak,
                        'peak_wall_cold_K': spall_cold_peak,
                        'peak_heat_flux_MW_m2': float(
                            np.nanmax(q_spall)) / 1e6,
                    },
                    'optimistic': None,
                    'optimistic_note': (
                        'no source gives a deposit more insulating than '
                        'SP-125 Fig. 4-25 (single curve, no band); NASA '
                        'TP-2862 measured smaller reductions, so no '
                        'optimistic end is published'),
                },
                'spalled_above_melting': bool(spall_peak > melting),
                'spalled_above_allowable': bool(spall_peak > allowable),
            })
            warnings_list.append(
                f"CARBON DEPOSIT: LOX/RP-1 gas-side carbon deposit resistance "
                f"applied (NASA SP-125 Fig. 4-25; throat R_d "
                f"{r_dep[_ti] * 1e4:.2f}e-4 m2K/W). Peak hot wall "
                f"{max_wall_hot:.0f} K with the deposit, {spall_peak:.0f} K "
                f"where it spalls (no deposit, same coolant state).")
            if spall_peak > melting:
                warnings_list.append(
                    f"CRITICAL: where the carbon deposit spalls the hot wall "
                    f"reaches {spall_peak:.0f} K, above the "
                    f"{self.material.get('name', self.wall_material)} melting "
                    f"point {melting:.0f} K — local liner failure (NASA "
                    f"SP-8087 sec. 3.4.1: spalling shall not cause failure).")
        elif cd_env['status'] == CARBON_DEPOSIT_STATUS_OUT_OF_ENVELOPE:
            warnings_list.append(
                "CARBON DEPOSIT: " + cd_env['reason'] + ".")

        # koklaşma (yalnız RP-1): yakıt tarafı cidar sıcaklığı — İKİ KADEME
        # (V301/L-KABUK; ``RP1_COKING_BASIS``): 728 K hüküm, 561 K uyarı.
        coking = False
        coking_risk = False
        if self.coolant == 'rp1' and max_wall_cold > RP1_COKING_LIMIT_TEMP_K:
            coking = True
            coking_risk = True
            warnings_list.append(
                f"COKING LIMIT: RP-1 coolant-side wall temperature reaches "
                f"{max_wall_cold:.0f} K, above the "
                f"{RP1_COKING_LIMIT_TEMP_K:.0f} K design criterion of NASA "
                f"SP-8087 sec. 3.1.1.5.4 for RP-1 liquid-wall temperature — "
                f"the design does not meet this criterion.")
        elif self.coolant == 'rp1' and max_wall_cold > RP1_COKING_TEMP_K:
            coking_risk = True
            warnings_list.append(
                f"COKING RISK: RP-1 coolant-side wall temperature reaches "
                f"{max_wall_cold:.0f} K, above the {RP1_COKING_TEMP_K:.0f} K "
                f"deposit-risk warning level (software warning based on NASA "
                f"CR-168277 copper-tube deposits at 560-750 K; validate for "
                f"the application) and below the "
                f"{RP1_COKING_LIMIT_TEMP_K:.0f} K NASA SP-8087 criterion — "
                f"not a statement that the wall stays deposit-free.")

        # DÜZELTME (v2.6.2, fizik denetimi F057): soğutucu özellik TABLOSUNUN
        # geçerlilik zarfı dışına taşan istasyonlar artık bildiriliyor.
        # Önceki davranışta _interp_table'ın 'clamped' bayrağı üretiliyor ama
        # hiç okunmuyordu; RP-1 tablosu 500 K'de, su tablosu 400 K'de bittiği
        # için tipik bir RP-1 devresinde 500 K üstü her istasyon sessizce
        # DONMUŞ özellik kullanıyordu. Ölçüm (su, 459 K / 80 bar, CoolProp
        # referanslı): klamplı tablo mu=2.17e-4 verir (gerçek 1.47e-4, %48
        # yüksek), Pr=1.342 (gerçek 0.960); sabit mdot'ta h_c oranı 0.856 —
        # yani h_c %14 EKSİK çıkar. RP-1 için referans veri olmadığından
        # sapma ölçülemez, bu yüzden uyarı sayısal düzeltme değil zarf
        # bildirimi yapar. Kaynak: Incropera & DeWitt 6th ed. Table A.6 (su,
        # 280-400 K bandı); RP-1 tablosu 'approximate' mühendislik derlemesi.
        if table_clamped_stations > 0 and table_band is not None:
            warnings_list.append(
                f"PROPERTY RANGE: {self.coolant} bulk temperature leaves the "
                f"internal property table band "
                f"({table_band[0]:.0f}-{table_band[1]:.0f} K) at "
                f"{table_clamped_stations} station(s) "
                f"(T_bulk {table_clamp_t_min:.0f}-{table_clamp_t_max:.0f} K); "
                f"properties there are FROZEN at the nearest band edge — "
                f"transport properties and the coolant-side coefficient are "
                f"an extrapolation outside the source validity envelope.")

        # ÖH Z5S / PK5 (P4B2-03) — MODEL ZARFI BEYANI.
        # Bant KENARINDA donmuş özellikler bir DOĞRULUK sorunudur ve yukarıdaki
        # PROPERTY RANGE uyarısı onu dürüstçe bildirir. Tablo tavanının
        # KATLARINA çıkan bir "soğutucu sıcaklığı" ise artık bir doğruluk
        # sorunu değil, model zarfının terk edilmesidir: RP-1 o sıcaklıkta
        # sıvı değildir, cp/rho tablosunun uzantısı diye bir şey yoktur.
        # ÖLÇÜLDÜ (Dt=60 mm, ε=25, RP-1, bakır): mdot=0,05 → çıkış 2044,6 K,
        # mdot=0,02 → 2448,0 K, mdot=0,01 → 2697,6 K; tablo tavanı 500 K
        # (4,1× / 4,9× / 5,4×) ve dört uyarının hiçbiri sonucu geçersiz
        # saymıyordu.
        #
        # EŞİK UYDURULMADI, TABLONUN KENDİSİNDEN TÜRETİLDİ: sıcaklık, tavanı
        # bandın KENDİ GENİŞLİĞİ kadar aşarsa donmuş-özellik ekstrapolasyonu
        # verinin kapsadığı aralıktan daha uzun bir mesafeye yayılmış demektir
        # (RP-1: 290-500 K bandı, eşik 710 K; su: 280-400 K, eşik 520 K).
        # Fizik sabiti değil, VERİNİN KAPSAMI ölçütüdür.
        coolant_envelope_max_K = None
        coolant_out_of_envelope = False
        if table_band is not None:
            bant_alt, bant_ust = float(table_band[0]), float(table_band[1])
            coolant_envelope_max_K = bant_ust + (bant_ust - bant_alt)
            t_bulk_max = max(float(np.max(t_coolant)), float(t_out))
            if t_bulk_max > coolant_envelope_max_K:
                coolant_out_of_envelope = True
                warnings_list.append(
                    f"MODEL OUT OF ENVELOPE: {self.coolant} bulk temperature "
                    f"reaches {t_bulk_max:.0f} K, beyond "
                    f"{coolant_envelope_max_K:.0f} K — the frozen-property "
                    f"extrapolation now spans more than the width of the "
                    f"source table itself "
                    f"({bant_alt:.0f}-{bant_ust:.0f} K). The coolant is not a "
                    f"single-phase liquid there and the property table has no "
                    f"continuation, so the station temperatures, the wall "
                    f"temperatures and the pressure drop past that point are "
                    f"NOT MODELLED results; they must not be read as a "
                    f"prediction.")

        # akış rejimi uyarısı (Dittus-Boelter türbülan geçerliliği)
        if min_re < RE_TURBULENT_FLOOR:
            warnings_list.append(
                f"NOTE: minimum channel Reynolds number {min_re:.0f} is below "
                f"the Dittus-Boelter turbulent floor (~1e4); the coolant-side "
                f"coefficient there is an extrapolation.")

        # --- ÖH D22 / P4B2-10: DITTUS-BOELTER ZARFI ARTIK TARANIYOR --------
        # ``dittus_boelter_envelope`` F154 düzeltmesi olarak yazılmış, ama
        # ürün yolunda HİÇ çağrılmamıştı (ölü kod) ve künyesindeki iki
        # dürüstlük beyanı (+/-%25 saçılım, Sieder-Tate uygulanmıyor)
        # kullanıcıya hiç ulaşmıyordu. ÖLÇÜLDÜ (taban b84b10a,
        # ``once.json`` P4B2-10): çağrı sayısı 0, ``model_note`` içinde
        # 'scatter' ve 'sieder' geçmiyor, çıktıda zarf alanı yok.
        # Zarf artık korelasyonun FİİLEN uygulandığı istasyonlardan
        # kurulur; süperkritik (Jackson) istasyonlar Dittus-Boelter
        # kullanmadığı için sayıma girmez.
        db_zarf = None
        if db_stations > 0:
            l_over_d = (channel_len_m / self.hydraulic_diameter
                        if self.hydraulic_diameter > 0.0 else None)
            # En kötü hâl taranır: Prandtl bandının hangi ucu ihlal
            # ediyorsa o, ve marşın en düşük Reynolds'u.
            pr_worst = (db_pr_min if db_pr_min < DB_PR_MIN
                        else (db_pr_max if db_pr_max > DB_PR_MAX
                              else db_pr_min))
            db_zarf = dittus_boelter_envelope(
                float(min_re), float(pr_worst), l_over_d,
                sieder_tate_applied=not sc_mode)
            db_zarf['stations_using_dittus_boelter'] = int(db_stations)
            db_zarf['prandtl_min'] = float(db_pr_min)
            db_zarf['prandtl_max'] = float(db_pr_max)
            db_zarf['reynolds_min'] = float(min_re)
            db_zarf['length_over_diameter'] = (
                None if l_over_d is None else float(l_over_d))
            db_zarf['channel_length_m'] = float(channel_len_m)
            if not db_zarf['in_envelope']:
                warnings_list.append(
                    "DITTUS-BOELTER ENVELOPE: the coolant-side correlation "
                    "is used outside its stated validity envelope at "
                    f"{db_stations} station(s) — "
                    + "; ".join(db_zarf['violations'])
                    + ". The reported +/-"
                    f"{db_zarf['scatter_pct']:.0f}% scatter does NOT apply "
                    "there.")

        # V301/L-REJ — Sieder-Tate cidar viskozitesi tablo bandı dışında:
        # sessiz sayı yok; çarpanın bant kenarında tutulduğu (düzeltmenin
        # EKSİK sayıldığı, yani h_c'nin alt sınır olduğu) istasyonlar adıyla.
        if not sc_mode and st_wall_edge_stations > 0:
            _tablo = _WATER_TABLE if self.coolant == 'water' else _RP1_TABLE
            warnings_list.append(
                f"PROPERTY RANGE (WALL): the {self.coolant} coolant-side wall "
                f"temperature is above the internal property table band "
                f"({_tablo[0, 0]:.0f}-{_tablo[-1, 0]:.0f} K) at "
                f"{st_wall_edge_stations} station(s); the Sieder-Tate wall "
                f"viscosity there is held at the band edge, so the "
                f"(mu_b/mu_w)^0.14 correction is UNDER-stated and the "
                f"coolant-side coefficient is a conservative lower bound "
                f"(peak correction factor used {float(np.max(st_factor)):.3f}).")
        if not sc_mode and wall_balance_unconverged > 0:
            warnings_list.append(
                f"CONVERGENCE: the coupled Sieder-Tate/fin wall balance did "
                f"not converge to {REGEN_LIQUID_WALL_TOL_K:g} K at "
                f"{wall_balance_unconverged} station(s) — wall temperatures "
                f"there carry iteration residual.")

        # ÖH D15 / P4B2-09 — ince-cidar zarfının UYARI bandı (%2..%10).
        # Reddin altındaki bant sessiz kalmaz: düz-levha yaklaşımının kendi
        # hatası sayılır ve yönü söylenir (düz levha direnci FAZLA tahmin
        # eder, yani cidar sıcaklığı YUKARI yönde yanlıdır).
        if self.wall_curvature_error_rel > WALL_CURVATURE_WARN_REL:
            warnings_list.append(
                f"THIN-WALL ENVELOPE: the flat-plate conduction resistance "
                f"used here differs from the cylindrical solution by "
                f"{self.wall_curvature_error_rel:.1%} at the throat "
                f"(wall_thickness {self.wall_thickness * 1e3:.1f} mm vs "
                f"throat radius {self.throat_diameter * 500.0:.1f} mm); the "
                f"published hot-wall temperature is biased HIGH by that "
                f"order. Model note assumes t_w << r_wall.")

        # kanal yerleşim uygunluğu — ÖH A2 sivi-sogutma · F-17: ölçüt artık
        # TEK TANIMDAN (``channel_fit_limit``); eskiden burada kaburgasız
        # ``N·w <= 2·pi·(r_t + t_w)`` ayrı bir kopya olarak duruyordu ve sıvı
        # motorun iç-çevre ölçütüyle aynı geometride farklı hüküm veriyordu.
        uygunluk = channel_fit_limit(geo['r_throat_mm'] / 1000.0,
                                     self.wall_thickness, self.channel_width,
                                     self.land_width)
        self.channel_fit = dict(uygunluk, n_channels=int(self.n_channels),
                                fits=bool(self.n_channels
                                          <= uygunluk['n_max']))
        if not self.channel_fit['fits']:
            warnings_list.append(
                f"GEOMETRY: {self.n_channels} channels of width "
                f"{self.channel_width * 1e3:.2f} mm with "
                f"{self.land_width * 1e3:.2f} mm lands need "
                f"{self.n_channels * uygunluk['pitch_m'] * 1e3:.1f} mm of "
                f"circumference, but the channel-base circumference at the "
                f"throat, 2*pi*(r_throat + wall_thickness), is "
                f"{uygunluk['reference_circumference_m'] * 1e3:.1f} mm — "
                f"channels do not physically fit; at most "
                f"{uygunluk['n_max']} fit (reduce count/width).")

        # su kaynaması (kaba): yerel P'de doymuş sıcaklığın üstüne çıkış
        if self.coolant == 'water' and _HAS_COOLPROP and \
                self.coolant_props_source in ('auto', 'coolprop'):
            try:  # pragma: no cover - ortam bağımlı
                t_sat = float(_CP_PropsSI('T', 'P', max(p_out, 1e3), 'Q', 0, 'Water'))
                if t_out > t_sat:
                    warnings_list.append(
                        f"BOILING: water exit temperature {t_out:.0f} K exceeds "
                        f"the saturation temperature {t_sat:.0f} K at the outlet "
                        f"pressure — single-phase assumption violated.")
            except Exception:
                pass

        # --- süperkritik soğutucu (metan/hidrojen) sınır denetimleri ---
        t_pc_inlet = None
        if sc_mode:
            fluid_label = self._cp_fluid
            if self.coolant_inlet_pressure <= self.coolant_pcrit:
                warnings_list.append(
                    f"SUBCRITICAL PRESSURE: {fluid_label} inlet pressure "
                    f"{self.coolant_inlet_pressure/1e5:.1f} bar is below the "
                    f"critical pressure {self.coolant_pcrit/1e5:.1f} bar — "
                    f"boiling is possible; the model stays single phase and "
                    f"only FLAGS the risk (no two-phase model).")
            else:
                t_pc_inlet = pseudocritical_temperature(
                    self._cp_fluid, self.coolant_inlet_pressure)
                t_cool_min = float(np.min(t_coolant))
                t_cool_max = float(np.max(t_coolant))
                if t_cool_min < t_pc_inlet < t_cool_max:
                    warnings_list.append(
                        f"NOTE: coolant bulk temperature crosses the "
                        f"pseudo-critical temperature "
                        f"({t_pc_inlet:.0f} K at inlet pressure) along the "
                        f"channel — strong property variation; the enthalpy "
                        f"march and Jackson property-ratio corrections "
                        f"account for it to first order.")
            if bulk_boiling_stations > 0:
                warnings_list.append(
                    f"BOILING: coolant bulk temperature reaches/exceeds the "
                    f"local saturation temperature at "
                    f"{bulk_boiling_stations} station(s) (subcritical "
                    f"pressure) — single-phase assumption violated; results "
                    f"there are not valid.")
            elif near_boiling_stations > 0:
                warnings_list.append(
                    f"BOILING RISK: coolant bulk temperature is within "
                    f"{BOILING_MARGIN_K:.0f} K (screening margin) of the "
                    f"local saturation temperature at "
                    f"{near_boiling_stations} station(s).")
            if wall_boiling_stations > 0:
                warnings_list.append(
                    f"NUCLEATE BOILING RISK: coolant-side wall temperature "
                    f"exceeds the local saturation temperature at "
                    f"{wall_boiling_stations} station(s) (subcritical "
                    f"pressure) — wall boiling not modelled.")
            if wall_balance_unconverged > 0:
                warnings_list.append(
                    f"CONVERGENCE: the coupled wall balance did not converge "
                    f"to 1e-3 K at {wall_balance_unconverged} station(s) — "
                    f"wall temperatures there carry iteration residual.")
            if jackson_wall_clamped > 0:
                warnings_list.append(
                    f"NOTE: Jackson wall-side property ratios evaluated at "
                    f"the {fluid_label} EOS temperature limit "
                    f"({self._fluid_tmax:.0f} K) at {jackson_wall_clamped} "
                    f"station(s) — the coolant-side coefficient there is an "
                    f"extrapolation (wall-limit warnings apply "
                    f"independently).")

        # --- ÖH KU H-11: RP-1 kritik ısı akısı ekranı (YALNIZ UYARI) ---
        # Kritik-altı istasyon varsa uyarı; Sutton Tablo 8-5 zarfı içindeyse
        # tepe q/q_max (en düşük tablo değeriyle, muhafazakâr) ve SP-8087 %80
        # marjı uyarı metninde. Zarf dışında oran YAZILMAZ (uydurma oran yok).
        # Zarf dört kenarlıdır: 0,689 ≤ p ≤ 1,38 MPa ve 1 ≤ v ≤ 8,5 m/s
        # (denetim Ş-1: önceki sürüm alt basınç ve üst hız sınırını
        # uygulamıyordu; 5 bar girişte zarf içi oran yazıyordu).
        # YENİ ALAN (istasyon başına p/p_kr, süperkritik beyanı) BİLEREK
        # YAYIMLANMADI: soğutma yanıtına eklenen her yeni anahtar
        # tests/test_wave4b_contract.py ters yön sözleşmesinde (panel basmıyor,
        # muafiyet yok) KIRMIZI oluyor; panel ve test bu kulvarın dosyası
        # değil → devir. Ölçüldü: 'rp1_burnout_screen' alanı iki testi
        # kırdı (kozmetik_kalan_gerekceli_izinli[cooling/summary],
        # sagir_alt_bloklar_buyumez).
        if self.coolant == 'rp1':
            alt = (p_coolant / RP1_CRITICAL_PRESSURE_PA) <= 1.0
            n_alt = int(np.sum(alt))
            if n_alt > 0:
                zarf = (alt
                        & (p_coolant >= KEROSENE_QMAX_TABLE_P_MIN_PA)
                        & (p_coolant <= KEROSENE_QMAX_TABLE_P_MAX_PA)
                        & (velocity >= KEROSENE_QMAX_TABLE_V_MIN_M_S)
                        & (velocity <= KEROSENE_QMAX_TABLE_V_MAX_M_S))
                if np.any(zarf):
                    tepe = float(np.max(q_flux[zarf])
                                 / KEROSENE_QMAX_TABLE_MIN_W_M2)
                    oran_metni = (
                        f"peak q/q_max {tepe:.2f} against the lowest "
                        f"tabulated kerosene q_max "
                        f"({KEROSENE_QMAX_TABLE_MIN_W_M2 / 1e6:.1f} MW/m2, "
                        f"Sutton & Biblarz Table 8-5) at "
                        f"{int(np.sum(zarf))} station(s) inside the table "
                        f"envelope; NASA SP-8087 keeps q below "
                        f"{BURNOUT_HEAT_FLUX_MARGIN:.0%} of burnout")
                else:
                    oran_metni = (
                        f"q/q_max not evaluated: no subcritical station lies "
                        f"inside the tabulated envelope "
                        f"({KEROSENE_QMAX_TABLE_P_MIN_PA / 1e6:.3f}-"
                        f"{KEROSENE_QMAX_TABLE_P_MAX_PA / 1e6:.2f} MPa, "
                        f"{KEROSENE_QMAX_TABLE_V_MIN_M_S:g}-"
                        f"{KEROSENE_QMAX_TABLE_V_MAX_M_S:g} m/s; no "
                        f"extrapolation)")
                warnings_list.append(
                    f"SUBCRITICAL RP-1: coolant pressure is below the RP-1 "
                    f"critical pressure "
                    f"({RP1_CRITICAL_PRESSURE_PA / 1e5:.1f} bar) at {n_alt} "
                    f"station(s) — nucleate boiling and a burnout (critical "
                    f"heat flux) limit apply; HRMA has no validated RP-1 "
                    f"burnout correlation; {oran_metni}.")

        if sc_mode:
            if n_jackson > 0 and n_db_subcritical > 0:
                coolant_correlation = 'jackson+dittus_boelter(subcritical)'
            elif n_jackson > 0:
                coolant_correlation = 'jackson'
            else:
                coolant_correlation = 'dittus_boelter(subcritical)'
        else:
            coolant_correlation = 'dittus_boelter'

        summary = {
            'coolant': self.coolant,
            'wall_material': self.wall_material,
            'wall_material_name': self.material.get('name', self.wall_material),
            'coolant_inlet_temp_K': t_in,
            'coolant_exit_temp_K': t_out,
            'coolant_dT_K': dT_total,
            'coolant_cp_mean_J_kgK': cp_mean,
            'total_heat_W': total_heat_W,
            'total_heat_kW': total_heat_W / 1e3,
            'total_pressure_drop_bar': total_dP / 1e5,
            'coolant_exit_pressure_bar': p_out / 1e5,
            'max_wall_hot_K': max_wall_hot,
            'max_wall_hot_x_mm': float(x_mm[max_wall_hot_idx]),
            'max_wall_cold_K': max_wall_cold,
            'peak_heat_flux_MW_m2': float(np.max(q_flux)) / 1e6,
            'max_coolant_velocity_m_s': float(np.max(velocity)),
            'min_reynolds': float(min_re),
            'material_allowable_temp_K': allowable,
            'material_service_limit_K': max_service,
            'material_melting_K': melting,
            'wall_temp_margin_K': allowable - max_wall_hot,
            # V301/L-KABUK: ``coking`` = SP-8087 hüküm kademesi (728 K) aşıldı;
            # ``coking_risk`` = uyarı kademesi (561 K) aşıldı. İki eşik de
            # sayı olarak çıkar; künye RP1_COKING_BASIS.
            'coking': coking,
            'coking_threshold_K': (RP1_COKING_LIMIT_TEMP_K
                                   if self.coolant == 'rp1' else None),
            'coking_risk': coking_risk,
            'coking_warning_threshold_K': (RP1_COKING_TEMP_K
                                           if self.coolant == 'rp1' else None),
            'coking_basis': (RP1_COKING_BASIS if self.coolant == 'rp1'
                             else None),
            'flow_direction': self.flow_direction,
            'coolant_correlation': coolant_correlation,
            'pressure_drop_friction_bar': dp_friction_total / 1e5,
            'pressure_drop_acceleration_bar': dp_accel_total / 1e5,
            'coolant_critical_pressure_bar': (
                self.coolant_pcrit / 1e5 if sc_mode else None),
            'coolant_critical_temperature_K': (
                self.coolant_tcrit if sc_mode else None),
            'coolant_pseudocritical_T_K': t_pc_inlet,
            'coolant_inlet_enthalpy_J_kg': h_inlet if sc_mode else None,
            'coolant_exit_enthalpy_J_kg': h_bulk if sc_mode else None,
            'supercritical_pressure': (
                bool(self.coolant_inlet_pressure > self.coolant_pcrit)
                if sc_mode else None),
            # V301/L-REJ: kanat modeli her yolda — iki alan artık su/RP-1'de
            # de dolu (eskiden None; yeni anahtar EKLENMEDİ, ters yön
            # sözleşmesi tests/test_wave4b_contract.py).
            'fin_effect': self.fin_effect,
            'fin_area_ratio_max': float(np.max(fin_ratio)),
            # NOT (ÖH D15) — P4B2-07 (özellik kaynağı), P4B2-08 (Bartz'ı
            # süren c*) ve P4B2-09 (ince-cidar zarfı ölçüsü) beyanları
            # ``summary``ye YENİ ALAN olarak EKLENMEDİ; PK5'in aynı gerekçesi
            # burada da geçerlidir ve ÖLÇÜLEREK doğrulandı: bu blok panelin
            # okuma envanterine ters yönde kilitlidir
            # (``tests/test_wave4b_contract.py::TestTersYonSozlesmesi`` +
            # ``TestTersYonBorcEnvanteri``), yani buraya eklenen her ad ya
            # ``cooling_panel.js`` içinde basılmak (dürüstlük alanı) ya da
            # gerekçeli muafiyet listesine yazılmak zorundadır — ikisi de bu
            # paketin sahasının dışındaki dosyalar. ÖLÇÜLDÜ: beş alan
            # eklendiğinde ``test_durustluk_borcu_buyumez`` ve
            # ``test_kozmetik_kalan_gerekceli_izinli[cooling/summary]``
            # kırmızıya döndü. Bilgi kaybı yok: üç beyan da ``model_note``
            # (panelin bastığı kanal) içinden, ince-cidar zarf ihlali ayrıca
            # ``warnings`` üzerinden yayımlanır; ONARIMLARIN KENDİSİ
            # (uçtan kaynak seçimi, sessiz düşüşün reddi, geometri kapıları)
            # beyandan bağımsız olarak davranıştadır.
            # F057: tablo geçerlilik zarfı denetimi (panel/rapor görünürlüğü)
            'property_table_clamped_stations': table_clamped_stations,
            'property_table_band_K': (list(table_band) if table_band is not None
                                      else None),
            # NOT (ÖH Z5S / PK5): zarf hükmü ve marş şeması BİLİNÇLİ olarak
            # ``summary``ye YENİ ALAN olarak eklenmedi. Bu blok panelin okuma
            # envanterine kilitlidir (tests/test_wave4b_contract.py ters-yön
            # sözleşmesi): buraya eklenen her ad ya panelde basılmak zorunda
            # (dürüstlük alanı) ya da gerekçeli muafiyet listesine yazılmak
            # zorunda — ikisi de bu paketin sahasının dışındaki dosyalar.
            # Bilgi kaybı yok: zarf hükmü ``warnings`` üzerinden (panelin
            # bastığı kanal), kuadratür künyesi ``model_note`` içinden
            # yayımlanır.
            'warnings': warnings_list,
        }

        if sc_mode:
            model_note = (
                "1D regenerative-cooling station march (analysis mode), "
                "supercritical-coolant path. Gas side: Bartz correlation "
                "(Sutton & Biblarz 9th ed. Eq. 8-22) driven by the "
                "adiabatic-wall temperature. Coolant side: Jackson "
                "supercritical correlation Nu=0.0183 Re^0.82 Pr^0.5 "
                "(rho_w/rho_b)^0.3 (cp_bar/cp_b)^n (Jackson & Hall 1979; "
                "Jackson 2013, Nucl. Eng. Des. 264) above the critical "
                "pressure, Dittus-Boelter (Incropera Eq. 8.60) below it with "
                "explicit boiling-risk flags. Coolant properties: CoolProp "
                f"(T,P)-dependent for {self._cp_fluid} (Bell et al. 2014); "
                "no internal table, out-of-range states raise. Coolant march "
                "is ENTHALPY based (h2=h1+dQ/mdot, T=T(P,h)) — exact through "
                "the pseudo-critical cp peak. Wall: thin flat-plate radial "
                "conduction; coolant-side area uses the channel-land "
                "extended-surface (fin) model when fin_effect=True "
                "(eta=tanh(mL)/mL, Incropera Ch. 3.6; lands-as-fins per "
                "Huzel & Huang Ch. 4), else area = gas-side area; the "
                "coupled gas/wall/coolant balance is solved per station "
                "(damped fixed point). Pressure drop: Darcy-Weisbach with the "
                "Haaland friction factor PLUS the acceleration term "
                "G^2*d(1/rho) (Collier & Thome 3rd ed. Ch. 2). Two-phase "
                "boiling is NOT modelled (flagged only). Channel dimensions "
                "are user inputs (no auto-sizing)."
            )
        else:
            model_note = (
                "1D regenerative-cooling station march (analysis mode). Gas side: "
                "Bartz correlation (Sutton & Biblarz 9th ed. Eq. 8-22) driven by the "
                "adiabatic-wall temperature. Coolant side: Dittus-Boelter "
                "Nu=0.023 Re^0.8 Pr^0.4 (Incropera Eq. 8.60; valid Re>=1e4, "
                "0.6<=Pr<=160) times the Sieder-Tate wall-viscosity factor "
                "(mu_b/mu_w)^0.14 evaluated at the solved coolant-side wall "
                "temperature (NASA SP-125 Eq. 4-23, p. 106; peak factor "
                f"{float(np.max(st_factor)):.3f}; mu_w held at the property-"
                f"table edge at {st_wall_edge_stations} station(s), where the "
                "correction is under-stated). Wall: thin flat-plate radial "
                "conduction; coolant-side area uses the channel-land "
                "extended-surface (fin) model "
                + ("(eta=tanh(mL)/mL with an adiabatic fin tip, Incropera Ch. "
                   "3.6; lands-as-fins per Huzel & Huang Ch. 4; "
                   "A_eff/A_gas = (w + 2*eta*h)/pitch, peak "
                   f"{float(np.max(fin_ratio)):.3f}, minimum "
                   f"{float(np.min(fin_ratio)):.3f}; the fin conductivity is "
                   "the same constant liner conductivity as the wall "
                   "resistance)" if self.fin_effect else
                   "switched OFF (fin_effect=False: coolant-side area = "
                   "gas-side area)")
                + ". Pressure "
                "drop: Darcy-Weisbach with the Haaland friction factor. RP-1 "
                "properties are approximate engineering values; coking: "
                f"{RP1_COKING_LIMIT_TEMP_K:.0f} K NASA SP-8087 design "
                f"criterion, {RP1_COKING_TEMP_K:.0f} K deposit-risk warning "
                "level (NASA CR-168277). Single-phase "
                "coolant assumed; no boiling / supercritical model. Channel "
                "dimensions are user inputs (no auto-sizing)."
            )

        # ÖH Z5S / PK5 — KUADRATÜR VE IZGARA KÜNYESİ (P4B2-11, P4B2-01).
        # Yayımlanan total_heat_W'nin hangi kuraldan çıktığı ve ceketin
        # hangi yüzeyi kapsadığı model künyesinde YAZILI olur; kullanıcı
        # toplamı kendi q(x) dizisinden yeniden kurabilsin diye.
        model_note += (
            " Heat integration: the segment flux is the TRAPEZOIDAL mean of "
            "its two station fluxes and the march is closed as a fixed point "
            f"({marş_gecisi} pass(es)), so the published total_heat_W is the "
            "trapezoidal integral of the published q(x) over the published "
            "grid. Stations are distributed by WETTED AREA over the "
            "barrel/convergent/divergent segments, with at least "
            f"{REGEN_MIN_INTERVALS_PER_SEGMENT} intervals per segment."
        )
        # ÖH D15 / P4B2-07 — künye ARTIK kaynağı söylüyor. Eski hâlde su ve
        # RP-1 metninde 'CoolProp' kelimesi hiç geçmiyordu ve iki kaynağın
        # ürettiği metin BİT-AYNIYDI (md5 57f3da3314b9), yani okuyucu farklı
        # sayıların nereden geldiğini metinden ÖĞRENEMİYORDU.
        _kaynak_kullanilan = ('+'.join(sorted(self._props_sources_seen))
                              if self._props_sources_seen else 'unknown')
        model_note += (
            " Coolant property source: requested "
            f"'{self.coolant_props_source}', actually used "
            f"'{_kaynak_kullanilan}' (CoolProp = Bell et al. 2014 REFPROP-"
            "class EOS; 'table' = the internal engineering table of this "
            "module). The two do not produce identical numbers: measured on "
            "the same water case, the pressure drop differs by 0.22 % and "
            "the peak coolant velocity by 0.79 %, and the table path raises "
            "a PROPERTY RANGE warning the CoolProp path does not."
            # ÖH D15 / P4B2-08 — Bartz'ı süren c* künyede ADIYLA duruyor.
            f" Bartz driving c* = {float(c_star):.2f} m/s "
            f"(source: {c_star_source}; 'user_supplied' means it came from "
            "motor_data['c_star'] and it is the value the gas-side "
            "coefficient was built on)."
            # ÖH D15 / P4B2-09 — düz-levha iletiminin kendi hatası.
            " Flat-plate wall conduction departs from the cylindrical "
            f"solution by {self.wall_curvature_error_rel:.2%} at the throat "
            f"(wall_thickness {self.wall_thickness * 1e3:.2f} mm vs throat "
            f"radius {self.throat_diameter * 500.0:.2f} mm); above "
            f"{WALL_CURVATURE_WARN_REL:.0%} a THIN-WALL ENVELOPE warning is "
            f"raised and above {WALL_CURVATURE_MAX_REL:.0%} no result is "
            "published at all."
        )
        # Karar §28-31 (c) — eşik künyesi (summary ters yön sözleşmesine
        # kilitli olduğu için yeni alan değil, künye cümlesi).
        _tl = self.temperature_ladder
        model_note += (
            " Wall-temperature verdict: single threshold from "
            "materials_db.temperature_limits(rec) — allowable_K = "
            f"{_tl['allowable_K']:.0f} K (published as both "
            "material_allowable_temp_K and material_service_limit_K; "
            f"selected field: {_tl['source_fields']['allowable_K']}) and "
            f"melting_K = {_tl['melting_K']:.0f} K; above the allowable the "
            "verdict is UNSAFE, above the melting point CRITICAL."
        )
        # V301/L-KARBON — birikim künyesi (yalnız LOX/RP-1 bağlamında).
        if self.carbon_deposit_applied:
            model_note += (
                " Gas side includes the LOX/RP-1 carbon deposit resistance in "
                "series, q = (T_aw - T_c)/(1/h_g + R_d + t_w/k_w + 1/h_c) "
                "(NASA SP-125 Eq. 4-18, Fig. 4-25, Sample Calc. 4-3; Bartz "
                f"sigma at T_wg/T_c = {CARBON_DEPOSIT_SIGMA_TWG_OVER_TC:g}); "
                "the published hot wall is the metal under the deposit, and "
                "the no-deposit (spalled) wall at the same coolant state is "
                "published as the conservative end (NASA SP-8087 sec. 3.4.1).")
        elif cd_env['status'] == CARBON_DEPOSIT_STATUS_OUT_OF_ENVELOPE:
            model_note += (" Carbon deposit: " + cd_env['reason'] + ".")
        if not sc_mode:
            # V301/L-REJ (b): marşın FİİLEN çözdüğü kanal geometrisi künyede
            # (motorun cooling_system bloğuyla aynı olduğu bekçiyle
            # sınanır: tests/test_v301_l_rej.py).
            _p_bogaz, _s_bogaz = self._channel_pitch_land(
                geo['r_throat_mm'] / 1000.0)
            model_note += (
                f" Channel geometry solved: {self.n_channels} channels, "
                f"width {self.channel_width * 1e3:.2f} mm, height "
                f"{self.channel_height * 1e3:.2f} mm, roughness "
                f"{self.wall_roughness * 1e6:.2f} um, hot wall "
                f"{self.wall_thickness * 1e3:.2f} mm; land between channels "
                f"{_s_bogaz * 1e3:.2f} mm at the throat (pitch "
                f"{_p_bogaz * 1e3:.2f} mm), wider downstream (constant "
                "channel width)."
            )
        barrel_mm = float(geo.get('chamber_barrel_length_mm') or 0.0)
        if barrel_mm > 0.0:
            model_note += (
                f" The jacket covers the cylindrical chamber barrel "
                f"({barrel_mm:.1f} mm, from motor_data['chamber_length']) "
                "as well as the nozzle contour."
            )
        else:
            model_note += (
                " The jacket covers the NOZZLE CONTOUR ONLY: no chamber "
                "length was supplied (motor_data['chamber_length']), so the "
                "cylindrical barrel is not part of the heated surface and "
                "the total heat load is a lower bound for a real chamber."
            )

        if db_zarf is not None:
            # P4B2-10: iki dürüstlük beyanı artık model_note'tan da geçiyor
            # (kullanıcının okuduğu tek metin orasıdır).
            model_note += (
                f" Coolant-side Dittus-Boelter: reported scatter about "
                f"+/-{db_zarf['scatter_pct']:.0f}%, and the Sieder-Tate "
                f"(mu_b/mu_w)^0.14 correction for large wall-to-bulk "
                f"property differences is "
                + ("APPLIED (see above)" if not sc_mode else
                   "NOT applied on this subcritical fallback")
                + f". Validity envelope "
                f"(Re >= {DB_RE_MIN:.0g}, {DB_PR_MIN} <= Pr <= {DB_PR_MAX}, "
                f"L/D >= {DB_LD_MIN:.0f}) was scanned over the "
                f"{db_zarf['stations_using_dittus_boelter']} station(s) that "
                f"use it: "
                + ("satisfied." if db_zarf['in_envelope']
                   else "VIOLATED — " + "; ".join(db_zarf['violations'])
                   + ".")
            )

        result = {
            # --- istenen çekirdek istasyon dizileri (x artan sırada) ---
            'x_mm': x_mm.tolist(),
            'T_wall_hot_K': t_wall_hot.tolist(),
            'T_wall_cold_K': t_wall_cold.tolist(),
            'T_coolant_K': t_coolant.tolist(),
            'P_coolant_bar': (p_coolant / 1e5).tolist(),
            'q_MW_m2': (q_flux / 1e6).tolist(),
            'velocity_m_s': velocity.tolist(),
            # --- ek teşhis dizileri ---
            'r_mm': r_mm.tolist(),          # gaz-tarafı iç yarıçap (mm)
            'reynolds': reynolds.tolist(),
            'h_gas_W_m2K': h_gas.tolist(),
            'h_coolant_W_m2K': h_cool.tolist(),
            'area_ratio': area_ratio.tolist(),
            'mach': mach.tolist(),
            'T_recovery_K': taw.tolist(),
            'throat_index': throat_index,
            'x_throat_mm': geo['z_throat_mm'],
            'x_exit_mm': geo['z_exit_mm'],
            'nozzle_type': geo['nozzle_type'],
            'n_stations': n,
            'hydraulic_diameter_mm': self.hydraulic_diameter * 1e3,
            'channel_area_mm2': self.channel_area * 1e6,
            'mdot_per_channel_kg_s': self.mdot_per_channel,
            'summary': summary,
            'model_note': model_note,
            # P4B2-10: zarf taramasının sayısal dökümü (ölü kod artık ürün
            # yolunda). Dittus-Boelter hiç kullanılmadıysa (tamamı Jackson)
            # alan None döner — uydurma zarf yayımlanmaz.
            'dittus_boelter_envelope': db_zarf,
        }
        # V301/L-REJ: kanat alan oranı dizisi artık HER yolda yayımlanır
        # (kanat modeli her yolda); Sieder-Tate çarpanı yalnız su/RP-1'de.
        if sc_mode:
            # İstasyon yığın entalpisi [kJ/kg] — yalnız metan/hidrojen
            # yolunda (JSON'a NaN sızdırmayız). Anahtar sırası eskisiyle aynı.
            result['coolant_enthalpy_kJ_kg'] = (coolant_h / 1e3).tolist()
            result['fin_area_ratio'] = fin_ratio.tolist()
        else:
            result['fin_area_ratio'] = fin_ratio.tolist()
            result['sieder_tate_factor'] = st_factor.tolist()
        # V301/L-KARBON — birikim beyanı (her yolda; dizi yalnız uygulandıysa).
        result['carbon_deposit'] = cd_block
        if self.carbon_deposit_applied:
            result['carbon_deposit_resistance_m2K_W'] = r_dep.tolist()
            result['T_wall_hot_no_deposit_K'] = [
                (float(v) if math.isfinite(v) else None)
                for v in t_wall_hot_spall]
        return result
