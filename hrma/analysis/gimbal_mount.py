"""Gimbal (itki vektör kontrolü) montaj ve aktüatör yükü çekirdeği (C3).

Motorun gimbal noktası etrafında sapma açısıyla, itkiden doğan yük
zincirini çözer:

    itki + gimbal açısı -> eksenel/yanal itki bileşenleri ve itki kaybı ->
    pivot etrafındaki momentler (itki kaçıklığı + esnek hat direnci +
    atalet) -> aktüatör kuvveti ve stroku -> montaj halkası kesit
    zorlamaları -> cıvata dairesi başına yük

Fizik ve kaynaklar
------------------
İtki bileşenleri (sapma açısı delta):

    F_eksenel = F * cos(delta)                                             (1)
    F_yanal   = F * sin(delta)
    kayıp     = F * (1 - cos(delta))

  Sutton, G.P. & Biblarz, O., "Rocket Propulsion Elements", 9. baskı,
  Böl. 18 (Thrust Vector Control). Yanal bileşen aracın kontrol
  kuvvetidir; eksenel bileşendeki azalma sapmanın ödediği bedeldir.

Aktüatör kuvveti — pivot etrafındaki moment dengesi:

    M_toplam = M_kaçıklık + M_hat + M_atalet                               (2)
    F_aktüatör = M_toplam / r_a                                            (3)

  r_a aktüatörün pivot eksenine olan dik uzaklığıdır (moment kolu).
  Bileşenler:
    M_kaçıklık = F * e      (itki vektörünün pivottan yanal kaçıklığı e)
    M_hat      = k_hat * delta_rad   (esnek hat/körük burulma yayı)
    M_atalet   = I * alfa            (açısal ivme)

  Huzel, D.K. & Huang, D.H., "Design of Liquid Propellant Rocket
  Engines", NASA SP-125 (1967) / AIAA cilt 147 (1992), Böl. 9
  (Design of Interconnecting Components and Mounts — gimbal montajı);
  NASA SP-8114, "Solid Rocket Thrust Vector Control" (1974).

  ÖNEMLİ: itki vektörü pivottan TAM geçiyorsa (e = 0), sürtünmesiz ve
  hatsız ideal gimbalde kararlı rejim aktüatör kuvveti SIFIRDIR. Bu bir
  tasarım yükü değil, modelin sonucudur; gerçek yük yatak sürtünmesi,
  esnek hat direnci ve atalet tarafından belirlenir. Hiçbir moment
  kaynağı verilmezse modül bunu açık bir ``validity`` beyanıyla söyler
  (sessizce "0 N aktüatör" verilmez).

Aktüatör stroku — pivot etrafında r_a yarıçapında dönen bağlantı noktası:

    yay boyu = r_a * delta_rad,      kiriş = 2 * r_a * sin(delta/2)        (4)

  İki değer gerçek stroku ALTTAN ve ÜSTTEN sınırlar (kiriş <= yay).
  Kesin strok, aktüatörün gövde ve motor tarafındaki bağlantı
  noktalarının konumuna bağlıdır (dört-çubuk kinematiği) ve burada
  MODELLENMEZ.

Montaj halkası kesit zorlamaları — gimbal düzleminden h kadar yukarıdaki
halka düzleminde serbest cisim dengesi:

    N = F*cos(delta),   V = F*sin(delta),   M_halka = F*sin(delta) * h     (5)

Cıvata dairesi (D çaplı, n adet eşit aralıklı cıvata) üzerinde momentin
doğurduğu en büyük cıvata kuvveti:

    M = sum F_i * y_i,  F_i = F_maks*cos(th_i),  y_i = (D/2)*cos(th_i)
    sum cos^2(th_i) = n/2  (n >= 3)   ->   F_maks = 4*M / (n*D)            (6)

  Shigley's Mechanical Engineering Design, Böl. 8 (eksantrik yüklü cıvata
  bağlantıları; cıvata dairesinde doğrusal gerilme dağılımı). Bekçi testi
  (6)'yı n cıvata üzerinden doğrudan toplayarak bağımsız doğrular.

Bu modül YÜK RESULTANTLARI üretir, GERİLME üretmez: cıvatanın ön yükü,
kapasitesi ve halkanın yapısal kontrolü burada YAPILMAZ — bunun için
deponun ``bolted_joint`` ve ``structural_analysis`` modülleri vardır.
Aktüatör dinamiği ve kontrol döngüsü MODELLENMEZ (bkz. ``NOT_MODELLED``).
Hiçbir engine modülü ithal edilmez. Kullanıcıya görünen tüm metinler
İngilizce, çıktı JSON-güvenlidir. Geçerlilik aralığı dışında sessiz
ekstrapolasyon yerine açık beyan (ValueError ya da ``validity``) üretilir.
"""

import math
from typing import Dict, List, Optional

__all__ = [
    'thrust_components',
    'resultant_gimbal_angle_deg',
    'actuator_stroke',
    'bolt_circle_max_load',
    'slew_angular_acceleration',
    'actuator_load',
    'mount_ring_loads',
    'analyze_gimbal_mount',
    'GIMBAL_ANGLE_PRACTICE_BAND_DEG',
    'GIMBAL_ANGLE_VALID_DEG',
    'BOLT_COUNT_MIN',
    'NOT_MODELLED',
]

# ---------------------------------------------------------------------------
# Geçerlilik bantları — TEK yerde tanımlı, kaynak künyeli.
#
# Uçan donanımın gimbal aralığı tipik olarak birkaç dereceyle ~10-11 derece
# arasındadır (F-1 ~+-6 deg, Merlin ~+-5 deg, SSME +-10.5 deg yunuslama).
# Bant bir FİZİK sınırı değil, mühendislik pratiğidir: modelin trigonometrisi
# her açıda kesindir, ama bant dışında tek eksenli düzlemsel kabul ve esnek
# hat/körük varsayımları sorgulanır.
# ---------------------------------------------------------------------------
GIMBAL_ANGLE_PRACTICE_BAND_DEG = (0.0, 15.0)
GIMBAL_ANGLE_VALID_DEG = (0.0, 45.0)
GIMBAL_ANGLE_SOURCE = (
    'Gimbal deflection practice band: flight liquid engines gimbal over '
    'roughly a few degrees to about +-11 deg (F-1 ~+-6 deg, SSME +-10.5 '
    'deg pitch, Merlin ~+-5 deg); Sutton & Biblarz, "Rocket Propulsion '
    'Elements", 9th ed., Ch. 18 (Thrust Vector Control); NASA SP-8114, '
    '"Solid Rocket Thrust Vector Control" (1974). The band is engineering '
    'practice, not a physical limit: the trigonometry here is exact at any '
    'angle, but beyond the band the single-axis planar assumption and the '
    'flex-duct treatment need review.')

# Cıvata dairesi formülü sum cos^2 = n/2 özdeşliğine dayanır; bu ancak
# eşit aralıklı n >= 3 cıvatada geçerlidir.
BOLT_COUNT_MIN = 3
BOLT_CIRCLE_SOURCE = (
    'Maximum bolt load on a bolt circle under a moment, F_max = 4M/(n*D), '
    'from the linear stress distribution about a neutral axis through the '
    'circle centre (Shigley\'s Mechanical Engineering Design, Ch. 8, '
    'eccentrically loaded bolted joints). The identity sum(cos^2 theta_i) '
    '= n/2 holds only for n >= 3 uniformly spaced bolts, so smaller counts '
    'are rejected rather than silently extrapolated.')

# ---------------------------------------------------------------------------
# Bilinçli olarak MODELLENMEYENLER. Çıktıya aynen konur (sahte veri yasağı).
# ---------------------------------------------------------------------------
NOT_MODELLED = {
    'actuator_dynamics': (
        'Actuator dynamics are NOT modelled: hydraulic/electromechanical '
        'actuator bandwidth, compliance, backlash, stall force, slew rate '
        'limits, servo-valve flow and power supply sizing are outside this '
        'model. The force reported here is the QUASI-STATIC load the '
        'actuator must react, not a sized actuator.'),
    'control_loop': (
        'The TVC control loop is NOT modelled: no gain, no phase margin, '
        'no actuator-vehicle-slosh-structure coupling, no tail-wags-dog '
        'effect. The slew acceleration used here is a caller-supplied '
        'input, not a control-system result.'),
    'bearing_friction': (
        'Gimbal bearing friction is NOT modelled: spherical/flex bearing '
        'break-away and running friction depend on the bearing type, '
        'preload and thrust load, and they can dominate the actuator load '
        'at small deflections. Supply it through '
        'bearing_friction_moment_N_m if you have it.'),
    'flex_duct': (
        'Flexible propellant duct and bellows resistance is NOT computed: '
        'the torsional spring rate, pressure-induced stiffening (a '
        'pressurised bellows resists deflection much harder than an '
        'unpressurised one) and hysteresis are hardware-specific. Supply '
        'a measured rate through duct_torsional_stiffness_N_m_rad; without '
        'it, this moment source is simply absent from the budget.'),
    'structural_capacity': (
        'Structural capacity is NOT evaluated: this module reports LOAD '
        'RESULTANTS (forces, moments, per-bolt loads) only. Bolt preload, '
        'thread and joint capacity, ring buckling, weld and lug stresses '
        'need the bolted_joint and structural_analysis modules and a '
        'material allowable.'),
    'aerodynamic_and_inertial_vehicle_loads': (
        'Vehicle-level loads are NOT included: aerodynamic side loads on '
        'the nozzle, base drag, vehicle lateral acceleration acting on the '
        'engine mass, and launch/transport loads are outside this model. '
        'Only the thrust-driven and commanded-slew loads are counted.'),
    'nozzle_side_loads': (
        'Nozzle flow side loads are NOT modelled: separated-flow side '
        'loads during start-up and shutdown of an overexpanded nozzle can '
        'exceed the steady gimbal loads and are a separate analysis.'),
    'thermal': (
        'Thermal effects are NOT modelled: differential expansion of the '
        'mount, bearing clearance change and hot-structure stiffness loss '
        'are outside this model.'),
    'gyroscopic': (
        'Gyroscopic coupling is NOT modelled: turbopump rotor angular '
        'momentum crossed with the gimbal rate produces a moment about the '
        'orthogonal axis, which this single-axis model does not carry.'),
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


def _require_non_negative(value, name: str, unit: str = '') -> float:
    """Negatif olmama şartı; değilse İngilizce ValueError."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a non-negative finite number {unit}')
    if not math.isfinite(v) or v < 0.0:
        raise ValueError(
            f'{name} must be a non-negative finite number {unit}; '
            f'got {value!r}')
    return v


def _check_gimbal_angle(angle_deg: float) -> float:
    """Gimbal açısı geçerlilik kontrolü; sert aralık dışı ValueError."""
    a = float(angle_deg)
    if not math.isfinite(a):
        raise ValueError('gimbal_angle_deg must be finite [deg]')
    lo, hi = GIMBAL_ANGLE_VALID_DEG
    if a < lo or a > hi:
        raise ValueError(
            f'gimbal_angle_deg {a:g} is outside the supported validity '
            f'range {GIMBAL_ANGLE_VALID_DEG} deg (invalid range declared - '
            'no silent extrapolation). ' + GIMBAL_ANGLE_SOURCE)
    return a


def thrust_components(thrust_N: float, gimbal_angle_deg: float) -> Dict:
    """İtki bileşenleri ve sapmanın itki kaybı — Eş. (1)."""
    f = _require_positive(thrust_N, 'thrust_N', '[N]')
    a = _check_gimbal_angle(gimbal_angle_deg)
    rad = math.radians(a)
    axial = f * math.cos(rad)
    side = f * math.sin(rad)
    return {
        'thrust_N': f,
        'gimbal_angle_deg': a,
        'axial_N': float(axial),
        'side_N': float(side),
        'thrust_loss_N': float(f - axial),
        'thrust_loss_fraction': float(1.0 - math.cos(rad)),
        'side_force_fraction': float(math.sin(rad)),
        '_basis': (
            'F_axial = F*cos(delta), F_side = F*sin(delta), loss = '
            'F*(1 - cos(delta)) (Sutton & Biblarz, "Rocket Propulsion '
            'Elements", 9th ed., Ch. 18). The thrust magnitude is assumed '
            'unchanged by gimballing - nozzle flow is not re-solved.'),
    }


def resultant_gimbal_angle_deg(pitch_deg: float, yaw_deg: float) -> float:
    """İki eksenin bileşke sapma açısı [deg] — kesin bileşim.

    x ekseni boyunca duran itki vektörü önce y ekseni etrafında
    ``pitch_deg``, sonra z ekseni etrafında ``yaw_deg`` döndürülürse
    bileşke açı cos(theta) = cos(pitch)*cos(yaw) ile verilir. Küçük
    açılarda sqrt(pitch^2 + yaw^2)'ye indirgenir. Dönme sırasının etkisi
    ikinci mertebedendir.
    """
    p = math.radians(_check_gimbal_angle(abs(float(pitch_deg))))
    y = math.radians(_check_gimbal_angle(abs(float(yaw_deg))))
    cos_theta = min(1.0, max(-1.0, math.cos(p) * math.cos(y)))
    return math.degrees(math.acos(cos_theta))


def actuator_stroke(actuator_arm_m: float, gimbal_angle_deg: float) -> Dict:
    """Aktüatör strok tahmini — Eş. (4); yay ve kiriş sınırlarıyla."""
    r = _require_positive(actuator_arm_m, 'actuator_arm_m', '[m]')
    a = _check_gimbal_angle(gimbal_angle_deg)
    rad = math.radians(a)
    arc = r * rad
    chord = 2.0 * r * math.sin(rad / 2.0)
    return {
        'actuator_arm_m': r,
        'gimbal_angle_deg': a,
        'stroke_chord_m': float(chord),
        'stroke_arc_m': float(arc),
        'stroke_full_travel_chord_m': float(2.0 * chord),
        'stroke_full_travel_arc_m': float(2.0 * arc),
        '_basis': (
            'Attachment point on radius r_a about the pivot: arc length = '
            'r_a*delta, chord = 2*r_a*sin(delta/2); chord <= arc, so the '
            'pair BRACKETS the true stroke. Full travel is the +delta to '
            '-delta excursion (twice the one-sided value). The exact '
            'stroke depends on where the actuator is anchored on the '
            'vehicle and on the engine (a four-bar linkage) and is NOT '
            'modelled here.'),
    }


def bolt_circle_max_load(moment_N_m: float, bolt_circle_diameter_m: float,
                         bolt_count: int) -> float:
    """Momentin cıvata dairesinde doğurduğu en büyük cıvata kuvveti [N].

    F_maks = 4*M / (n*D) — Eş. (6), Shigley Böl. 8. n >= 3 şarttır.
    """
    m = _require_non_negative(moment_N_m, 'moment_N_m', '[N.m]')
    d = _require_positive(bolt_circle_diameter_m,
                          'bolt_circle_diameter_m', '[m]')
    try:
        n = int(bolt_count)
    except (TypeError, ValueError):
        raise ValueError('bolt_count must be an integer')
    if n < BOLT_COUNT_MIN:
        raise ValueError(
            f'bolt_count {n} is below the minimum {BOLT_COUNT_MIN}: the '
            'bolt-circle formula relies on sum(cos^2) = n/2 for uniformly '
            'spaced bolts, which does not hold for fewer (invalid range '
            'declared - no silent extrapolation). ' + BOLT_CIRCLE_SOURCE)
    return 4.0 * m / (n * d)


def slew_angular_acceleration(*,
                              slew_acceleration_deg_s2: Optional[
                                  float] = None,
                              slew_rate_deg_s: Optional[float] = None,
                              slew_reversal_time_s: Optional[float] = None
                              ) -> Dict:
    """Açısal ivme [rad/s^2] — doğrudan ya da hız tersinmesinden.

    İki yol vardır ve ikisi de GİRDİye dayanır (uydurma yok):
      * ``slew_acceleration_deg_s2`` doğrudan verilir;
      * ``slew_rate_deg_s`` + ``slew_reversal_time_s``: +omega'dan
        -omega'ya tersinme dolayısıyla d(omega) = 2*omega ->
        alfa = 2*omega / t_tersinme.
    Hiçbiri verilmezse ivme HESAPLANMAZ (None döner) ve bu açıkça
    beyan edilir; atalet momenti bütçeye eklenmez.
    """
    if slew_acceleration_deg_s2 is not None:
        alpha = math.radians(_require_positive(
            slew_acceleration_deg_s2, 'slew_acceleration_deg_s2',
            '[deg/s^2]'))
        return {
            'angular_acceleration_rad_s2': float(alpha),
            'source': 'user-supplied slew_acceleration_deg_s2',
            'status': 'computed',
        }
    if slew_rate_deg_s is not None and slew_reversal_time_s is not None:
        omega = math.radians(_require_positive(
            slew_rate_deg_s, 'slew_rate_deg_s', '[deg/s]'))
        t_rev = _require_positive(slew_reversal_time_s,
                                  'slew_reversal_time_s', '[s]')
        return {
            'angular_acceleration_rad_s2': float(2.0 * omega / t_rev),
            'angular_rate_rad_s': float(omega),
            'source': ('derived from slew_rate_deg_s and '
                       'slew_reversal_time_s: reversing from +rate to '
                       '-rate is a rate change of 2*omega, so alpha = '
                       '2*omega/t_reversal'),
            'status': 'computed',
        }
    return {
        'angular_acceleration_rad_s2': None,
        'angular_rate_rad_s': (None if slew_rate_deg_s is None else
                               float(math.radians(float(slew_rate_deg_s)))),
        'source': None,
        'status': 'not_computed',
        'message': (
            'Angular acceleration was NOT computed: supply either '
            'slew_acceleration_deg_s2, or both slew_rate_deg_s and '
            'slew_reversal_time_s. A slew rate ALONE does not determine an '
            'acceleration, so no inertia moment is added to the budget '
            '(no value is invented).'),
    }


# ===========================================================================
# Aktüatör yükü
# ===========================================================================
def actuator_load(*,
                  thrust_N: float,
                  gimbal_angle_deg: float,
                  actuator_arm_m: float,
                  thrust_offset_m: float = 0.0,
                  duct_torsional_stiffness_N_m_rad: Optional[float] = None,
                  bearing_friction_moment_N_m: Optional[float] = None,
                  engine_inertia_kg_m2: Optional[float] = None,
                  slew_acceleration_deg_s2: Optional[float] = None,
                  slew_rate_deg_s: Optional[float] = None,
                  slew_reversal_time_s: Optional[float] = None,
                  actuators_per_axis: int = 1) -> Dict:
    """Aktüatör kuvveti ve stroku — Eş. (2)-(4).

    Moment kaynakları yalnız VERİLDİKLERİ ölçüde bütçeye girer; hiçbiri
    verilmezse toplam moment sıfır çıkar ve bu durum açık bir ``validity``
    beyanıyla bildirilir (sessizce "0 N aktüatör" verilmez).
    """
    f = _require_positive(thrust_N, 'thrust_N', '[N]')
    a = _check_gimbal_angle(gimbal_angle_deg)
    r_a = _require_positive(actuator_arm_m, 'actuator_arm_m', '[m]')
    e = _require_non_negative(thrust_offset_m, 'thrust_offset_m', '[m]')
    try:
        n_act = int(actuators_per_axis)
    except (TypeError, ValueError):
        raise ValueError('actuators_per_axis must be an integer')
    if n_act < 1:
        raise ValueError('actuators_per_axis must be at least 1')

    rad = math.radians(a)
    validity: List[Dict] = []
    warnings: List[str] = []
    terms: List[Dict] = []

    # --- itki kaçıklığı momenti ---
    m_offset = f * e
    if e > 0.0:
        terms.append({
            'source': 'thrust_offset',
            'moment_N_m': float(m_offset),
            '_basis': (
                'M = F * e, the moment of the thrust vector about the '
                'pivot when its line of action misses the gimbal centre '
                'by e. Alignment tolerance, thrust vector misalignment '
                'and engine weight offset all feed this term.'),
        })

    # --- esnek hat/körük burulma direnci ---
    m_duct = 0.0
    if duct_torsional_stiffness_N_m_rad is not None:
        k_duct = _require_non_negative(duct_torsional_stiffness_N_m_rad,
                                       'duct_torsional_stiffness_N_m_rad',
                                       '[N.m/rad]')
        m_duct = k_duct * rad
        terms.append({
            'source': 'flex_duct',
            'moment_N_m': float(m_duct),
            '_basis': (
                'M = k_duct * delta, a linear torsional spring standing in '
                'for the flexible propellant ducts and bellows. The rate '
                'is a CALLER-SUPPLIED measured value; it is strongly '
                'pressure dependent and generally non-linear (see '
                'not_modelled.flex_duct).'),
        })

    # --- yatak sürtünmesi ---
    m_friction = 0.0
    if bearing_friction_moment_N_m is not None:
        m_friction = _require_non_negative(bearing_friction_moment_N_m,
                                           'bearing_friction_moment_N_m',
                                           '[N.m]')
        terms.append({
            'source': 'bearing_friction',
            'moment_N_m': float(m_friction),
            '_basis': (
                'Caller-supplied gimbal bearing friction moment, added '
                'directly. It is NOT computed from the thrust load (see '
                'not_modelled.bearing_friction).'),
        })

    # --- atalet momenti ---
    slew = slew_angular_acceleration(
        slew_acceleration_deg_s2=slew_acceleration_deg_s2,
        slew_rate_deg_s=slew_rate_deg_s,
        slew_reversal_time_s=slew_reversal_time_s)
    alpha = slew['angular_acceleration_rad_s2']
    m_inertia = 0.0
    inertia_block: Dict = {'status': 'not_computed'}
    if engine_inertia_kg_m2 is not None and alpha is not None:
        inertia = _require_positive(engine_inertia_kg_m2,
                                    'engine_inertia_kg_m2', '[kg.m^2]')
        m_inertia = inertia * alpha
        omega = slew.get('angular_rate_rad_s')
        inertia_block = {
            'status': 'computed',
            'engine_inertia_kg_m2': float(inertia),
            'angular_acceleration_rad_s2': float(alpha),
            'angular_momentum_kg_m2_s': (None if omega is None
                                         else float(inertia * omega)),
            'moment_N_m': float(m_inertia),
            'acceleration_source': slew['source'],
            '_basis': (
                'M_inertia = I * alpha about the gimbal axis. I is the '
                'CALLER-SUPPLIED mass moment of inertia of the gimballed '
                'mass about that axis (engine, its share of ducts and '
                'trapped propellant); it is not computed here. The '
                'angular momentum I*omega is reported for gyroscopic '
                'cross-axis checks, which this single-axis model does not '
                'perform (see not_modelled.gyroscopic).'),
        }
        terms.append({
            'source': 'inertia',
            'moment_N_m': float(m_inertia),
            '_basis': inertia_block['_basis'],
        })
    else:
        missing = []
        if engine_inertia_kg_m2 is None:
            missing.append('engine_inertia_kg_m2')
        if alpha is None:
            missing.append('an angular acceleration '
                           '(slew_acceleration_deg_s2, or slew_rate_deg_s '
                           'with slew_reversal_time_s)')
        inertia_block = {
            'status': 'not_computed',
            'message': (
                'The inertia moment was NOT computed because '
                + ' and '.join(missing) + ' was not supplied; it is absent '
                'from the moment budget below rather than assumed zero on '
                'physical grounds.'),
            'slew': slew,
        }
        validity.append({
            'field': 'inertia_moment',
            'status': 'not_evaluated',
            'message': inertia_block['message']})

    m_total = m_offset + m_duct + m_friction + m_inertia
    if m_total <= 0.0:
        validity.append({
            'field': 'actuator_force_N',
            'status': 'not_evaluated',
            'message': (
                'No moment source was supplied (thrust offset, duct '
                'stiffness, bearing friction and inertia are all absent or '
                'zero), so the moment budget is zero and the steady '
                'actuator force computes as zero. That is the IDEAL '
                'frictionless result for a thrust vector passing exactly '
                'through the pivot - it is NOT a design load. Supply at '
                'least a thrust offset and a duct rate before using this '
                'number.')})
        warnings.append(
            'actuator force is zero because no moment source was supplied; '
            'this is a model artefact, not a design load.')

    f_act_total = m_total / r_a
    f_act_each = f_act_total / n_act

    stroke = actuator_stroke(r_a, a)

    if a > GIMBAL_ANGLE_PRACTICE_BAND_DEG[1]:
        validity.append({
            'field': 'gimbal_angle_deg',
            'status': 'outside_practice_band',
            'message': (
                f'gimbal angle {a:g} deg exceeds the practice band '
                f'{GIMBAL_ANGLE_PRACTICE_BAND_DEG} deg (still inside the '
                f'hard validity range {GIMBAL_ANGLE_VALID_DEG} deg). The '
                'trigonometry stays exact, but the single-axis planar '
                'treatment and the linear duct spring need review at this '
                'deflection. ' + GIMBAL_ANGLE_SOURCE)})

    return {
        'thrust': thrust_components(f, a),
        'moment_budget': {
            'thrust_offset_N_m': float(m_offset),
            'flex_duct_N_m': float(m_duct),
            'bearing_friction_N_m': float(m_friction),
            'inertia_N_m': float(m_inertia),
            'total_N_m': float(m_total),
            'terms': terms,
            '_basis': (
                'M_total = M_offset + M_duct + M_friction + M_inertia, all '
                'taken about the gimbal pivot axis and summed as '
                'worst-case co-directional (they are treated as acting '
                'together, which is conservative for actuator sizing). '
                'Only supplied sources appear; nothing is assumed.'),
        },
        'actuator': {
            'arm_m': r_a,
            'actuators_per_axis': n_act,
            'force_total_N': float(f_act_total),
            'force_each_N': float(f_act_each),
            'stroke_chord_m': stroke['stroke_chord_m'],
            'stroke_arc_m': stroke['stroke_arc_m'],
            'stroke_full_travel_chord_m': stroke['stroke_full_travel_chord_m'],
            'stroke_full_travel_arc_m': stroke['stroke_full_travel_arc_m'],
            '_basis': (
                'F_actuator = M_total / r_a, shared equally by '
                'actuators_per_axis units on the same axis. QUASI-STATIC: '
                'no actuator dynamics, no rate limit, no stall margin '
                '(see not_modelled.actuator_dynamics). ' + stroke['_basis']),
        },
        'inertia': inertia_block,
        'validity': validity,
        'warnings': warnings,
        'not_modelled': dict(NOT_MODELLED),
    }


# ===========================================================================
# Montaj halkası yükleri
# ===========================================================================
def mount_ring_loads(*,
                     thrust_N: float,
                     gimbal_angle_deg: float,
                     ring_offset_m: float,
                     bolt_circle_diameter_m: Optional[float] = None,
                     bolt_count: Optional[int] = None) -> Dict:
    """Montaj halkası kesit zorlamaları ve cıvata yükleri — Eş. (5)-(6)."""
    f = _require_positive(thrust_N, 'thrust_N', '[N]')
    a = _check_gimbal_angle(gimbal_angle_deg)
    h = _require_non_negative(ring_offset_m, 'ring_offset_m', '[m]')
    rad = math.radians(a)

    n_axial = f * math.cos(rad)
    v_shear = f * math.sin(rad)
    m_ring = v_shear * h

    bolts = None
    if bolt_circle_diameter_m is not None and bolt_count is not None:
        d_bc = _require_positive(bolt_circle_diameter_m,
                                 'bolt_circle_diameter_m', '[m]')
        n = int(bolt_count)
        f_moment = bolt_circle_max_load(m_ring, d_bc, n)
        f_axial_share = n_axial / n
        v_share = v_shear / n
        bolts = {
            'bolt_count': n,
            'bolt_circle_diameter_m': float(d_bc),
            'moment_induced_max_N': float(f_moment),
            'axial_share_per_bolt_N': float(f_axial_share),
            'shear_per_bolt_N': float(v_share),
            'max_tension_if_axial_is_tensile_N': float(f_moment
                                                       + f_axial_share),
            'max_tension_if_axial_is_compressive_N': float(f_moment
                                                           - f_axial_share),
            '_basis': (
                'Moment share: F_max = 4*M/(n*D) (Shigley Ch. 8). Axial '
                'and shear are divided equally over the bolts. SIGN '
                'CONVENTION MATTERS: whether the thrust puts the ring in '
                'tension or compression depends on the installation, so '
                'BOTH combinations are reported and the caller must pick '
                'the one matching the load path. Bolt preload, joint '
                'stiffness and capacity are NOT evaluated here - feed '
                'these loads into the bolted_joint module. '
                + BOLT_CIRCLE_SOURCE),
        }

    return {
        'section_loads': {
            'axial_N': float(n_axial),
            'shear_N': float(v_shear),
            'bending_moment_N_m': float(m_ring),
            'ring_offset_m': h,
            '_basis': (
                'Free-body of the gimballed engine cut at the mount ring '
                'plane, h above the pivot: N = F*cos(delta), V = '
                'F*sin(delta), M = F*sin(delta)*h (Huzel & Huang, NASA '
                'SP-125 / AIAA 147, Ch. 9, engine mounts; NASA SP-8114). '
                'The thrust vector is assumed to pass through the pivot, '
                'so the pivot carries the full thrust vector and the ring '
                'moment comes from the side force acting on the offset '
                'arm. Engine weight, vehicle acceleration and aerodynamic '
                'loads are NOT included (see '
                'not_modelled.aerodynamic_and_inertial_vehicle_loads).'),
        },
        'bolts': bolts,
        'not_modelled': dict(NOT_MODELLED),
    }


# ===========================================================================
# Uçtan uca
# ===========================================================================
def analyze_gimbal_mount(*,
                         thrust_N: float,
                         gimbal_angle_deg: float,
                         actuator_arm_m: float,
                         ring_offset_m: float = 0.0,
                         thrust_offset_m: float = 0.0,
                         duct_torsional_stiffness_N_m_rad: Optional[
                             float] = None,
                         bearing_friction_moment_N_m: Optional[float] = None,
                         engine_inertia_kg_m2: Optional[float] = None,
                         slew_acceleration_deg_s2: Optional[float] = None,
                         slew_rate_deg_s: Optional[float] = None,
                         slew_reversal_time_s: Optional[float] = None,
                         actuators_per_axis: int = 1,
                         bolt_circle_diameter_m: Optional[float] = None,
                         bolt_count: Optional[int] = None,
                         yaw_angle_deg: Optional[float] = None) -> Dict:
    """Gimbal montajının tam yük zinciri: aktüatör + halka + cıvata.

    ``yaw_angle_deg`` verilirse iki eksenin bileşke sapma açısı da
    raporlanır (köşe durumu); yük hesabı yine tek eksen üzerinden
    yapılır ve bu açıkça beyan edilir.
    """
    act = actuator_load(
        thrust_N=thrust_N,
        gimbal_angle_deg=gimbal_angle_deg,
        actuator_arm_m=actuator_arm_m,
        thrust_offset_m=thrust_offset_m,
        duct_torsional_stiffness_N_m_rad=duct_torsional_stiffness_N_m_rad,
        bearing_friction_moment_N_m=bearing_friction_moment_N_m,
        engine_inertia_kg_m2=engine_inertia_kg_m2,
        slew_acceleration_deg_s2=slew_acceleration_deg_s2,
        slew_rate_deg_s=slew_rate_deg_s,
        slew_reversal_time_s=slew_reversal_time_s,
        actuators_per_axis=actuators_per_axis)

    ring = mount_ring_loads(
        thrust_N=thrust_N,
        gimbal_angle_deg=gimbal_angle_deg,
        ring_offset_m=ring_offset_m,
        bolt_circle_diameter_m=bolt_circle_diameter_m,
        bolt_count=bolt_count)

    validity = list(act['validity'])
    warnings = list(act['warnings'])

    two_axis = None
    if yaw_angle_deg is not None:
        resultant = resultant_gimbal_angle_deg(gimbal_angle_deg,
                                               yaw_angle_deg)
        two_axis = {
            'pitch_deg': float(gimbal_angle_deg),
            'yaw_deg': float(yaw_angle_deg),
            'resultant_angle_deg': float(resultant),
            '_basis': (
                'cos(resultant) = cos(pitch)*cos(yaw) for a rotation about '
                'the pitch axis followed by one about the yaw axis; the '
                'small-angle limit is sqrt(pitch^2 + yaw^2). Rotation '
                'ORDER changes the result only at second order.'),
        }
        validity.append({
            'field': 'two_axis',
            'status': 'informational',
            'message': (
                f'the resultant of pitch {float(gimbal_angle_deg):g} deg '
                f'and yaw {float(yaw_angle_deg):g} deg is '
                f'{resultant:.2f} deg, but the actuator and ring loads '
                'above are computed for the SINGLE-AXIS deflection you '
                'passed as gimbal_angle_deg. Re-run with the resultant '
                'angle if the corner case governs.')})

    if ring['bolts'] is None:
        validity.append({
            'field': 'bolts',
            'status': 'not_evaluated',
            'message': (
                'Per-bolt loads were NOT computed: both '
                'bolt_circle_diameter_m and bolt_count are required.')})

    return {
        'actuator': act['actuator'],
        'thrust': act['thrust'],
        'moment_budget': act['moment_budget'],
        'inertia': act['inertia'],
        'mount_ring': ring['section_loads'],
        'bolts': ring['bolts'],
        'two_axis': two_axis,
        'validity': validity,
        'warnings': warnings,
        'not_modelled': dict(NOT_MODELLED),
    }
