"""Fırlatma Sahası uçuş izi: 6-DOF çözümünden tek sözleşmeli zaman serisi.

V307/FS-UÇUŞ (9 Kas 2026, Berke: "import edilen motorun ve roketin
bilgilerine göre uçuş simülasyonu … sadece çizgi şeklinde gidiyor").

ÖLÇÜLDÜ (``~/HRMA-calisma/2026-11-09/FS-UCUS/saha_once.json``): Fırlatma
Sahası 6-DOF yanıtının yalnız seyreltilmiş ``series`` bloğunu küreye
veriyordu; çözücü apojede durduğu için çizilen yol kalkıştan apojeye tek
bir yükseliş koluydu (üç örnek motorda yükseklik / yatay oranı 3,7-5,2:
dik, düz bir çizgi). İniş, enlem/boylam, olay zamanları sayfada hiç yoktu;
yanma sonu işaretçisi girdi süresinden türetiliyordu.

Bu modül ÇÖZÜMÜ DEĞİŞTİRMEZ; yükseliş serisi 6-DOF'un kendisidir. Eklenen:

* ``descent_flight`` — apoje durumundan yere kadar NOKTA-KÜTLE iniş.
  Denklemler yükseliş çözücüsüyle AYNI terimleri kullanır (aynı atmosfer
  USSA 1976, aynı yerel g ve ters-kare düzeltmesi, aynı rüzgâr, aynı
  Coriolis, aynı Mach-bağımlı eksenel katsayı ve referans alanı). İki kol:
  - balistik (kurtarma sistemi yok; HRMA seçimi, ``DESCENT_BASIS``): statik
    kararlı araç akışa döner ve burun önde iner;
  - paraşütlü (V307/FS-UÇUŞ-2, A4; ``PARACHUTE_DESCENT_BASIS``): düzlemsel
    (2B) çözücünün kurtarma modeliyle AYNI kural ve AYNI sabitler — apojeden
    açılma gecikmesine kadar gövde sürüklemesi, sonra paraşüt izdüşüm alanı
    × Cd (gövde sürüklemesinin yerine). İkinci bir iniş modeli açılmaz.
  Kararlı olmayan araçta (yükseliş takla attı ya da statik marj eşikte)
  iniş ÇÖZÜLMEZ ve nedeni adıyla yayımlanır.
* ``flight_track`` — yükseliş (+ varsa iniş) serisini tek örnekli izde
  birleştirir; enlem/boylam/deniz seviyesi irtifası
  ``launch_site.enu_to_geodetic`` (tek kaynak; küre çizimi aynı formülün
  JS kopyasıdır) ile çevrilir.
* ``flight_events`` — kalkış, yanma sonu, en büyük dinamik basınç, apoje,
  paraşüt açılışı, yere iniş; her biri tam çözünürlüklü çözümden ve
  kaynağıyla.
* V307/FS-UÇUŞ-2 (A1/A2) — kanat geometrisi kuralı (``fin_planform_by_rule``,
  ``fly_with_span_rule``, ``fin_geometry_block``) ve kararlılık eşiğinin
  künyesi (``STATIC_MARGIN_SOURCE``).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.integrate import solve_ivp

from hrma.analysis.launch_site import enu_to_geodetic
from hrma.analysis.six_dof_trajectory import (
    _OUTPUT_ROW_ORDER, _atmosphere, _coriolis_acceleration,
    _drag_coefficient_mach, STATIC_MARGIN_MIN_CAL)
# V307/FS-UÇUŞ-2 (A4): paraşüt girdilerinin varsayılanları ve iniş penceresi
# düzlemsel (2B) çözücünün KENDİ sabitleridir — iki iniş modeli açılmaz.
from hrma.analysis.trajectory_analysis import (
    DEFAULT_PARACHUTE_CD, DEFAULT_PARACHUTE_DEPLOY_DELAY_S,
    DESCENT_TIME_LIMIT_S)

#: İz sözleşmesinin adı ve sürümü (istemci ``LaunchSiteFlightResult`` bunu taşır).
TRACK_SCHEMA = 'hrma.six_dof.track/1'

#: İsteğin kabul ettiği iniş modelleri. 'parachute' (V307/FS-UÇUŞ-2, A4):
#: düzlemsel çözücünün kurtarma modeli (bkz. ``PARACHUTE_DESCENT_BASIS``).
DESCENT_MODELS = ('ballistic', 'parachute', 'none')

# ---------------------------------------------------------------------------
# V307/FS-UÇUŞ-2 (A2) — KARARLILIK EŞİĞİNİN KAYNAĞI
#
# Çözücünün eşiği ``STATIC_MARGIN_MIN_CAL`` (1 kalibre, six_dof_trajectory)
# FS-UÇUŞ'ta kaynaksızdı (RAPOR A2). Doğrulanan künye (16 Kas 2026; belge
# ~/HRMA-calisma/2026-11-16/FS-UCUS-2/indirilen/openrocket_techdoc/,
# sha256 cc6fd329…): S. Niskanen, "OpenRocket technical documentation"
# (OpenRocket 13.05, 2013-05-10), §2.4 "Stability of a rocket", s. 12 —
# model roketçilerinin deneyim kuralı: basınç merkezi ağırlık merkezinin
# yaklaşık 1–2 kalibre arkasında olmalı. Aynı paragraf, hücum açısında
# CP'nin öne kaydığını ve 1–2 kalibrelik marjın birkaç derecede
# kaybolabileceğini söyler. HRMA eşiği aralığın ALT ucudur (yeni sayı
# yok); üst uç (2 kalibre) yalnız bilgi olarak yazılır.
# ---------------------------------------------------------------------------
STATIC_MARGIN_BAND_CAL = (STATIC_MARGIN_MIN_CAL, 2.0)
STATIC_MARGIN_SOURCE = (
    'S. Niskanen, OpenRocket technical documentation (for OpenRocket 13.05, '
    '2013-05-10), section 2.4 "Stability of a rocket", p. 12: a rule of '
    'thumb among model rocketeers is that the CP should be approximately '
    '1-2 calibers aft of the CG. HRMA requires the static margin, full and '
    'empty, to be above the lower end of that range (1 caliber); the upper '
    'end is reported for information only. The source calls it a rule of '
    'thumb and notes that the margin can vanish at a few degrees of angle '
    'of attack, which is why the 6-DOF verdict also checks the angle of '
    'attack.')

#: Balistik iniş entegrasyonu: yükseliş çözücüsüyle aynı toleranslar.
_DESCENT_RTOL = 1e-5
_DESCENT_ATOL = 1e-7
_DESCENT_MAX_STEP_S = 0.1
#: Paraşüt altındaki kolun en büyük adımı [s]: düzlemsel çözücünün iniş
#: entegrasyonuyla aynı (trajectory_analysis._calculate_descent_flight,
#: ``max_step=1.0``). Sayısal ayar; fizik sabiti değil.
_PARACHUTE_MAX_STEP_S = 1.0

DESCENT_BASIS = (
    'Descent after the 6-DOF ascent: point-mass ballistic fall from the '
    'ascent end state to the ground, no recovery system deployed. Same '
    'terms as the ascent solver: USSA 1976 atmosphere at absolute altitude, '
    'local gravity with inverse-square correction, wind, Coriolis (when the '
    'site latitude is given), Mach-dependent axial drag coefficient on the '
    'body reference area along the air-relative velocity (nose-first: a '
    'statically stable vehicle turns into the flow). Attitude is not '
    'integrated during the descent. HRMA choice, not a sourced recovery '
    'model.')

PARACHUTE_DESCENT_BASIS = (
    'Descent after the 6-DOF ascent under a parachute, with the SAME '
    'recovery model and the same defaults as the 2-D trajectory solver '
    '(trajectory_analysis._calculate_descent_flight): from apogee until the '
    'deploy delay the vehicle falls with its body drag (Mach-dependent axial '
    'coefficient on the body reference area, nose first); from apogee + '
    'deploy delay the drag is the parachute drag Cd x projected canopy area, '
    'which replaces the body drag. When Cd or the delay is not supplied the '
    '2-D solver defaults are used and flagged as assumed (Cd 1.4 on the '
    'PROJECTED area, Hoerner 1965, hollow hemisphere). Point mass; same '
    'atmosphere, gravity, wind and Coriolis terms as the ascent solver. '
    'Canopy inflation time and opening shock are not modelled. The descent '
    'window is the 2-D solver one (DESCENT_TIME_LIMIT_S).')


def _not_solved(reason: str, model: str = 'ballistic_point_mass',
                basis: str = DESCENT_BASIS, **extra) -> Dict:
    out = {'model': model, 'status': 'not_solved',
           'reason': reason, 'basis': basis}
    out.update(extra)
    return out


# ---------------------------------------------------------------------------
# V307/FS-KÜÇÜK (kalem 3) — PARAŞÜT GİRDİ KURALI TEK YERDE
#
# ÖLÇÜLDÜ (fs-ucus-2 RAPOR §7 DEVİR; fs-kucuk/olcum/api_once_parasut.json):
# düzlemsel uç (``/api/trajectory-analysis``, ``_KURTARMA_ALANLARI``) ile
# Fırlatma Sahası 6-DOF kapısı (``_parasut_alanlari``) AYNI kuralı ve AYNI
# gerekçe kodlarını iki ayrı yerde yazıyordu. Kural artık burada tektir; iki uç
# ``hrma.app._parasut_girdi_kapisi`` ile bu işlevi çağırır, kurtarma tanımı
# (``recovery_inputs``) da aynı işlevle denetler.
# ---------------------------------------------------------------------------
#: Paraşüt girdileri ve tanım kuralı: (alan, pozitif mi). Pozitif değilse
#: "negatif değil" (açılma gecikmesi 0 olabilir). Tanım gereğidir, bant değil.
PARACHUTE_INPUT_FIELDS = (('parachute_area', True), ('parachute_cd', True),
                          ('parachute_deploy_delay', False))
_PARASUT_POZITIF = dict(PARACHUTE_INPUT_FIELDS)


def parachute_input_defect(field: str, value: float) -> Optional[Dict]:
    """Okunmuş bir paraşüt girdisi tanımına uymuyorsa adlı kusur kaydı.

    Alan ve Cd pozitif, açılma gecikmesi negatif değil; ihlalde
    ``{'field', 'reason': 'must_be_positive' | 'must_be_non_negative',
    'value'}``, uyuyorsa ``None``. Okuma (sayı mı, sonlu mu) çağıranındır.
    """
    if _PARASUT_POZITIF[field]:
        if not value > 0.0:
            return {'field': field, 'reason': 'must_be_positive', 'value': value}
    elif value < 0.0:
        return {'field': field, 'reason': 'must_be_non_negative', 'value': value}
    return None


def recovery_inputs(area, cd=None, deploy_delay=None) -> Dict:
    """Paraşüt girdileri -> kurtarma tanımı (düzlemsel çözücünün kuralı).

    ``area`` İZDÜŞÜM alanıdır [m²] ve ZORUNLUDUR (düzlemsel çözücü de alanı
    varsaymaz: ``LANDING_WITHHELD_NO_PARACHUTE``). Cd ve açılma gecikmesi
    verilmezse düzlemsel çözücünün sabitleri kullanılır ve ``assumed``
    bayrağıyla yazılır. Sınırlar tanım gereğidir (alan ve Cd pozitif,
    gecikme negatif değil; ``parachute_input_defect``); ihlal ``ValueError``
    (çağıran adıyla reddeder).
    """
    a = float(area)
    if not math.isfinite(a) or parachute_input_defect('parachute_area', a):
        raise ValueError('parachute_area must be positive')
    out = {'area_m2': a, 'cd': float(DEFAULT_PARACHUTE_CD),
           'deploy_delay_s': float(DEFAULT_PARACHUTE_DEPLOY_DELAY_S),
           'assumed': {'cd': True, 'deploy_delay': True}}
    if cd is not None:
        c = float(cd)
        if not math.isfinite(c) or parachute_input_defect('parachute_cd', c):
            raise ValueError('parachute_cd must be positive')
        out['cd'] = c
        out['assumed']['cd'] = False
    if deploy_delay is not None:
        t = float(deploy_delay)
        if not math.isfinite(t) or parachute_input_defect('parachute_deploy_delay', t):
            raise ValueError('parachute_deploy_delay must not be negative')
        out['deploy_delay_s'] = t
        out['assumed']['deploy_delay'] = False
    return out


def descent_flight(solver, res: Dict, recovery: Optional[Dict] = None,
                   max_duration_s: float = DESCENT_TIME_LIMIT_S) -> Dict:
    """Yükselişin son durumundan yere kadar nokta-kütle iniş.

    ``solver``: ``SixDOFTrajectory`` (çözülmüş); ``res``: ``solve()`` çıktısı;
    ``recovery``: ``recovery_inputs`` çıktısı ya da None (balistik).
    Dönüş: ``status`` 'solved' ise ``time`` (s, mutlak uçuş zamanı),
    ``position`` / ``velocity`` (3×N, satır sırası (K, D, Y) — ``res`` ile
    aynı), ``altitude``, ``speed``, ``mach``, ``dynamic_pressure`` ve
    ``impact``; değilse ``reason`` ile neden.
    """
    model = 'parachute_point_mass' if recovery else 'ballistic_point_mass'
    basis = PARACHUTE_DESCENT_BASIS if recovery else DESCENT_BASIS

    def red(reason, **extra):
        return _not_solved(reason, model=model, basis=basis, **extra)

    if res.get('end_reason') != 'apogee':
        return red('ascent_did_not_end_at_apogee',
                   ascent_end_reason=res.get('end_reason'))
    if res.get('stable') is not True:
        # V307/ONARIM-UÇUŞ (M7-FS-4): ret GERÇEK nedenle adlandırılır
        # (stability_verdict_code tek kural). ÖLÇÜLDÜ (mühendis turu u4,
        # rüzgâr 50 m/s): marj 3,43 / 4,43 kalibre, α 15,39° > 15° iken ret
        # "statik olarak kararlı değil" diyordu.
        from hrma.analysis.six_dof_trajectory import stability_verdict_code
        _hukum = stability_verdict_code(
            res.get('stable'), res.get('static_margin_full'),
            res.get('static_margin_empty'), res.get('max_alpha_deg'))
        if _hukum == 'alpha_above_linear_limit':
            return red('ascent_alpha_above_linear_limit',
                       max_alpha_deg=res.get('max_alpha_deg'))
        if _hukum == 'not_evaluated':
            return red('stability_not_evaluated')
        return red('vehicle_not_statically_stable')
    t_arr = np.asarray(res['time'], dtype=float)
    if t_arr.size < 2:
        return red('ascent_series_empty')
    if not (isinstance(max_duration_s, (int, float))
            and math.isfinite(max_duration_s) and max_duration_s > 0):
        return red('descent_duration_limit_invalid')

    rows = list(_OUTPUT_ROW_ORDER)          # (K,D,Y) ⟷ (D,K,Y) permütasyonu
    pos_ned = np.asarray(res['position'], dtype=float)
    vel_ned = np.asarray(res['velocity'], dtype=float)
    # Çıktı (K,D,Y) → entegrasyon (D,K,Y); permütasyon kendi tersidir.
    r0 = pos_ned[rows, -1].copy()
    v0 = vel_ned[rows, -1].copy()
    t0 = float(t_arr[-1])
    m = float(solver._mass_at(t0))
    if not (m > 0 and math.isfinite(m)):
        return red('vehicle_mass_not_positive')
    S = float(solver.aero.S_ref)
    cd0 = float(solver.cd0)
    wind_i = np.asarray(solver._wind_i, dtype=float)
    g_s = float(solver.g_surface)
    r_site = float(solver._r_site)
    h_site = float(solver.launch_altitude)
    coriolis = bool(solver.coriolis)
    cos_lat, sin_lat = float(solver._cos_lat), float(solver._sin_lat)

    def make_deriv(cd_sabit, alan):
        # cd_sabit None: gövde (Mach-bağımlı eksenel katsayı, gövde kesiti);
        # aksi hâlde paraşüt (sabit Cd, izdüşüm alanı) — gövdenin YERİNE.
        def deriv(t, y):
            r = y[0:3]
            v = y[3:6]
            h_agl = max(r[2], 0.0)
            rho, a_snd = _atmosphere(h_site + h_agl)
            g = g_s * (r_site / (r_site + h_agl)) ** 2
            u = v - wind_i
            um = float(np.linalg.norm(u))
            a = np.array([0.0, 0.0, -g])
            if um > 0.0:
                if cd_sabit is None:
                    cd, ref = _drag_coefficient_mach(um / a_snd, cd0), S
                else:
                    cd, ref = cd_sabit, alan
                a = a - (0.5 * rho * um * cd * ref / m) * u
            if coriolis:
                a = a + _coriolis_acceleration(v, cos_lat, sin_lat)
            return np.concatenate([v, a])
        return deriv

    def ground(t, y):
        return y[2]
    ground.terminal = True
    ground.direction = -1

    t_son = t0 + float(max_duration_s)
    kollar = []          # (t, y) parçaları
    y_bas = np.concatenate([r0, v0])
    t_bas = t0
    acildi = False
    t_acilma = None
    if recovery:
        t_acilma = t0 + float(recovery['deploy_delay_s'])
        if t_acilma > t_bas:
            sol = solve_ivp(make_deriv(None, None), (t_bas, min(t_acilma, t_son)),
                            y_bas, method='RK45', max_step=_DESCENT_MAX_STEP_S,
                            events=[ground], rtol=_DESCENT_RTOL, atol=_DESCENT_ATOL)
            if not sol.success:
                return red('descent_integration_failed',
                           solver_message=str(sol.message))
            kollar.append((sol.t, sol.y))
            y_bas, t_bas = sol.y[:, -1].copy(), float(sol.t[-1])
            if sol.t_events[0].size:
                t_acilma = None            # paraşüt açılmadan yere indi
        if t_acilma is not None and t_bas < t_son:
            acildi = True
            sol = solve_ivp(make_deriv(float(recovery['cd']),
                                       float(recovery['area_m2'])),
                            (t_bas, t_son), y_bas, method='RK45',
                            max_step=_PARACHUTE_MAX_STEP_S, events=[ground],
                            rtol=_DESCENT_RTOL, atol=_DESCENT_ATOL)
            if not sol.success:
                return red('descent_integration_failed',
                           solver_message=str(sol.message))
            kollar.append((sol.t[1:], sol.y[:, 1:]) if kollar else (sol.t, sol.y))
            yere = bool(sol.t_events[0].size)
        else:
            yere = t_acilma is None
    else:
        sol = solve_ivp(make_deriv(None, None), (t0, t_son), y_bas,
                        method='RK45', max_step=_DESCENT_MAX_STEP_S,
                        events=[ground], rtol=_DESCENT_RTOL, atol=_DESCENT_ATOL)
        if not sol.success:
            return red('descent_integration_failed',
                       solver_message=str(sol.message))
        kollar.append((sol.t, sol.y))
        yere = bool(sol.t_events[0].size)
    if not yere:
        return red('ground_not_reached_within_limit', limit_s=float(max_duration_s))
    t = np.concatenate([k[0] for k in kollar])
    y = np.concatenate([k[1] for k in kollar], axis=1)
    pos = y[0:3][rows]
    vel = y[3:6][rows]
    alt = y[2].copy()
    alt[-1] = max(alt[-1], 0.0)             # olay kökü: yer = 0 (sayısal kalıntı)
    speed = np.linalg.norm(y[3:6], axis=0)
    mach, q = [], []
    for k in range(t.size):
        rho, a_snd = _atmosphere(h_site + max(y[2, k], 0.0))
        um = float(np.linalg.norm(y[3:6, k] - wind_i))
        mach.append(um / a_snd)
        q.append(0.5 * rho * um ** 2)
    out = {
        'model': model, 'status': 'solved',
        'basis': basis,
        'time': t, 'position': pos, 'velocity': vel, 'altitude': alt,
        'speed': speed, 'mach': np.asarray(mach),
        'dynamic_pressure': np.asarray(q),
        'mass_kg': m,
        'impact': {
            't_s': float(t[-1]),
            'north_m': float(pos[0, -1]), 'east_m': float(pos[1, -1]),
            'speed_mps': float(speed[-1]),
            'vertical_speed_mps': float(vel[2, -1]),
        },
    }
    if recovery:
        out['recovery'] = {
            'parachute_area_m2': float(recovery['area_m2']),
            'parachute_cd': float(recovery['cd']),
            'parachute_deploy_delay_s': float(recovery['deploy_delay_s']),
            'assumed': dict(recovery['assumed']),
            'deployed': bool(acildi),
            'deploy_t_s': (float(t0 + float(recovery['deploy_delay_s']))
                           if acildi else None),
            'window_s': float(max_duration_s),
        }
        out['impact']['recovery_deployed'] = bool(acildi)
    return out


def ballistic_descent(solver, res: Dict, max_duration_s: float) -> Dict:
    """Balistik iniş (geri uyum adı): ``descent_flight(recovery=None)``."""
    return descent_flight(solver, res, None, max_duration_s)


# ---------------------------------------------------------------------------
# Kanat açıklığı ARAMASI (V307/FS-UÇUŞ önerisi ve V307/FS-UÇUŞ-2 kuralı ortak)
# ---------------------------------------------------------------------------

#: Kanat açıklığı aramasının üst sınırı: gövde çapının katı (HRMA seçimi; yalnız
#: aramayı sınırlar, sonuç değildir), kaba ve ince adım [m] ve Mach ızgarası adımı.
FIN_SPAN_SEARCH_MAX_CALIBERS = 4.0
FIN_SPAN_SEARCH_COARSE_M = 0.01
FIN_SPAN_SEARCH_STEP_M = 0.001
FIN_SIZING_MACH_STEP = 0.05
#: Öneriyi doğrulayan yeniden uçuşların sayı ve süre sınırı (HRMA seçimi).
FIN_SIZING_MAX_FLIGHTS = 3
FIN_SIZING_TIME_BUDGET_S = 20.0

#: V307/FS-UÇUŞ-2 (16 Kas, ana model kararı) — ÖNERİLEN KANADIN HEDEF MARJI
#: [kalibre]. Kuralın ve önerinin açıklığı, uçuş boyunca (dolu ve boş, Mach 0 →
#: en yüksek Mach) en düşük statik marjı bu değere ya da üstüne taşır. HRMA
#: SEÇİMİ: kaynağın "1–2 kalibre" bandının ORTASI (``STATIC_MARGIN_BAND_CAL``,
#: Niskanen 2013 §2.4 s. 12). Bandın alt ucu (eşik) tahmini ağırlık merkezinin
#: ve Barrowman basınç merkezinin belirsizliğine pay bırakmıyordu (ölçüldü:
#: katı örnek kalkışta 1,01 kalibre). Gövdede ``FIN_SPAN_SEARCH_MAX_CALIBERS``·d
#: açıklık içinde sağlanamazsa eşiği (``STATIC_MARGIN_MIN_CAL``) sağlayan en
#: küçük açıklık kullanılır ve bu adıyla yayımlanır. Kararlılık HÜKMÜNÜN eşiği
#: DEĞİŞMEZ (``stability_verdict_code``, 1 kalibre).
FIN_TARGET_MARGIN_CAL = 0.5 * (STATIC_MARGIN_BAND_CAL[0] + STATIC_MARGIN_BAND_CAL[1])
FIN_TARGET_BASIS = (
    'Target of the suggested fin: the lowest static margin over the flight '
    '(full and empty, Mach 0 to the highest Mach) at least %g calibre, the '
    'middle of the 1-2 calibre range of the source (Niskanen, OpenRocket '
    'technical documentation 2013, section 2.4, p. 12). HRMA choice: the lower '
    'end of the range is the stability threshold itself and leaves no room '
    'for the uncertainty of the estimated centre of gravity and of the '
    'Barrowman centre of pressure. If no span up to %g body diameters reaches '
    'the target, the smallest span that keeps the margin above the stability '
    'threshold (%g calibre) is used and this is reported. The stability '
    'verdict threshold is unchanged.' % (
        FIN_TARGET_MARGIN_CAL, FIN_SPAN_SEARCH_MAX_CALIBERS, STATIC_MARGIN_MIN_CAL))

#: V307/ONARIM2-UÇUŞ-ARAÇ (M7-UCUS-11, ana model kararı 20 Kas; Berke "sen
#: karar ver") — KANAT RÜZGÂRSIZ REFERANS UÇUŞTAN BOYUTLANIR. ÖLÇÜLDÜ
#: (mühendis turu): aynı sıvı araçta rüzgâr 5 m/s → açıklık 0,970 m, rüzgâr
#: 0 → 0,983 m; kural uçuşun Mach aralığına bakıyor, rüzgâr uçuşu ve Mach
#: aralığını (3,55 ↔ 3,63) değiştiriyordu. Kanat bir tasarım çıktısıdır,
#: günün rüzgârına bağlı olmaz: boyutlandırma uçuşları rüzgârsız (rüzgâr
#: hızı 0; öbür bütün girdiler aynı) referans uçuşlardır; rüzgâr yalnız
#: yayımlanan uçuşu etkiler. HRMA seçimi (kaynaklı kural değil).
FIN_SIZING_REFERENCE_WIND_MPS = 0.0
FIN_SIZING_REFERENCE_BASIS = (
    'The fin span is a design output, not a function of the day\'s wind: '
    'it is sized on windless reference flights (wind speed 0, every other '
    'input as sent; HRMA choice). The wind changes only the flight that is '
    'published, flown with that span.')


def _reference_solver_args(solver_args: Dict) -> Dict:
    """Kanat boyutlandırmasının rüzgârsız referans uçuş argümanları."""
    return dict(solver_args, wind_speed=FIN_SIZING_REFERENCE_WIND_MPS)


def _wind_of(solver_args: Dict) -> float:
    w = solver_args.get('wind_speed')
    return float(w) if w is not None else 0.0


FIN_SIZING_BASIS = (
    'Smallest fin span, with the fin count, chords and sweep held as sent, '
    'for which the lowest static margin, full and empty, from Mach 0 to the '
    'highest Mach of the windless reference flight reaches the fin target. '
    + FIN_TARGET_BASIS + ' '
    'Same Barrowman model with the solver\'s Mach correction of the fin '
    'term, same centre of gravity (supplied or the declared length-fraction '
    'estimate). ' + FIN_SIZING_REFERENCE_BASIS + ' HRMA then flies the '
    'vehicle with that span on the same inputs (your wind included) and '
    'reports the verdict it gets; if the reference flight is faster, the '
    'span is sized again for its Mach range. A suggestion, not applied.')


def _marj_tutar(aero, x_cg_full, x_cg_empty, machlar, esik, esit_kabul=False):
    """Marj (dolu ve boş) her Mach'ta ``esik``in üstünde mi (``esit_kabul``:
    eşit de kabul — kanat HEDEFİ için; kararlılık EŞİĞİ kesin büyüktür)."""
    for m in machlar:
        a = aero.static_margin(x_cg_full, m)
        b = aero.static_margin(x_cg_empty, m)
        if esit_kabul:
            if not (a >= esik and b >= esik):
                return False
        elif not (a > esik and b > esik):
            return False
    return True


def _mach_izgarasi(mach_max) -> Tuple[float, List[float]]:
    """0, ``FIN_SIZING_MACH_STEP`` adımları ve ``mach_max``'ın kendisi."""
    mm = float(mach_max) if (mach_max and math.isfinite(mach_max)
                             and mach_max > 0) else 0.0
    machlar = [0.0] + [k * FIN_SIZING_MACH_STEP
                       for k in range(1, int(mm / FIN_SIZING_MACH_STEP) + 1)]
    if mm > machlar[-1]:
        machlar.append(mm)
    return mm, machlar


def fin_span_for_static_margin(aero_args: Dict, x_cg_full: float,
                               x_cg_empty: float, margin_cal: Optional[float] = None,
                               mach_max: float = 0.0, inclusive: bool = False) -> Dict:
    """Statik marj ölçütünü Mach 0 … ``mach_max`` boyunca sağlayan en küçük
    kanat açıklığı (öneri).

    ``aero_args``: ``BarrowmanAero`` kurucu argümanları (uçuşla aynı).
    Açıklık 0 … ``FIN_SPAN_SEARCH_MAX_CALIBERS``·d aralığında yukarıdan aşağı
    taranır (kaba ``FIN_SPAN_SEARCH_COARSE_M``, sonra ince
    ``FIN_SPAN_SEARCH_STEP_M``); dönen değer, kendisinden üst sınıra kadar
    taranan BÜTÜN açıklıklarda ölçütün tuttuğu en küçük açıklıktır (tekdüze
    olmayan bir eğride tek noktalık geçiş öneri sayılmaz). Mach ızgarası
    0, ``FIN_SIZING_MACH_STEP`` adımları ve ``mach_max``'ın kendisi.
    Bulunamazsa ``min_fin_span_m`` None ve ``reason``.
    """
    from hrma.analysis.six_dof_trajectory import BarrowmanAero
    if margin_cal is None:
        margin_cal = STATIC_MARGIN_MIN_CAL

    def aero(acik):
        return BarrowmanAero(**dict(aero_args, fin_span=acik))

    mm, machlar = _mach_izgarasi(mach_max)
    d = float(aero_args['body_diameter'])
    ust = FIN_SPAN_SEARCH_MAX_CALIBERS * d
    simdi = aero(float(aero_args.get('fin_span') or 0.0))
    out = {
        'criterion': ('static_margin_full %s %g cal and static_margin_empty %s %g '
                      'cal for Mach 0 to %.3f' % ('>=' if inclusive else '>', margin_cal,
                                                  '>=' if inclusive else '>', margin_cal, mm)),
        'margin_cal': margin_cal,
        'basis': FIN_SIZING_BASIS,
        'mach_range_max': mm,
        'fin_count': int(aero_args.get('fin_count') or 0),
        'fin_root_chord_m': float(aero_args.get('fin_root_chord') or 0.0),
        'fin_tip_chord_m': float(aero_args.get('fin_tip_chord') or 0.0),
        'fin_sweep_m': float(aero_args.get('fin_sweep') or 0.0),
        'current_fin_span_m': float(aero_args.get('fin_span') or 0.0),
        'current_margin_full_cal': float(simdi.static_margin(x_cg_full)),
        'current_margin_empty_cal': float(simdi.static_margin(x_cg_empty)),
        'search_max_span_m': ust, 'search_max_calibers': FIN_SPAN_SEARCH_MAX_CALIBERS,
        'resolution_m': FIN_SPAN_SEARCH_STEP_M,
        'min_fin_span_m': None,
    }
    if out['fin_count'] <= 0 or out['fin_root_chord_m'] <= 0.0:
        out['reason'] = 'no_fins_to_size'
        return out

    def tutar(acik):
        return _marj_tutar(aero(acik), x_cg_full, x_cg_empty, machlar, margin_cal,
                           esit_kabul=inclusive)

    if not tutar(ust):
        out['reason'] = 'criterion_not_met_within_search_limit'
        return out
    son_gecen = ust
    acik = ust - FIN_SPAN_SEARCH_COARSE_M
    while acik > 0.0 and tutar(acik):
        son_gecen = acik
        acik -= FIN_SPAN_SEARCH_COARSE_M
    acik = son_gecen - FIN_SPAN_SEARCH_STEP_M
    while acik > 0.0 and tutar(acik):
        son_gecen = acik
        acik -= FIN_SPAN_SEARCH_STEP_M
    # İnce adım ızgarasına yukarı yuvarla (öneri ölçütü sağlayan tarafta kalır).
    oneri = math.ceil(round(son_gecen / FIN_SPAN_SEARCH_STEP_M, 6)) * FIN_SPAN_SEARCH_STEP_M
    oneri = round(oneri, 6)
    if not tutar(oneri):
        oneri = round(son_gecen, 6)
    a = aero(oneri)
    out.update(min_fin_span_m=oneri,
               margin_full_at_min_cal=float(a.static_margin(x_cg_full)),
               margin_empty_at_min_cal=float(a.static_margin(x_cg_empty)),
               min_margin_over_mach_range_cal=float(min(
                   min(a.static_margin(x_cg_full, m), a.static_margin(x_cg_empty, m))
                   for m in machlar)))
    return out


def fin_span_for_target(aero_args: Dict, x_cg_full: float, x_cg_empty: float,
                        mach_max: float = 0.0) -> Dict:
    """ÖNERİLEN açıklık: hedef (``FIN_TARGET_MARGIN_CAL``) önce; arama sınırı
    içinde sağlanamazsa eşik (``STATIC_MARGIN_MIN_CAL``). Dönüşte
    ``target_margin_cal``, ``margin_target_used_cal`` ve ``target_met``
    (kanat yoksa None) adıyla yazılır."""
    r = fin_span_for_static_margin(aero_args, x_cg_full, x_cg_empty,
                                   margin_cal=FIN_TARGET_MARGIN_CAL,
                                   mach_max=mach_max, inclusive=True)
    if r['min_fin_span_m'] is not None or r.get('reason') == 'no_fins_to_size':
        r.update(target_margin_cal=FIN_TARGET_MARGIN_CAL,
                 margin_target_used_cal=FIN_TARGET_MARGIN_CAL,
                 target_met=(True if r['min_fin_span_m'] is not None else None))
        return r
    r2 = fin_span_for_static_margin(aero_args, x_cg_full, x_cg_empty,
                                    margin_cal=STATIC_MARGIN_MIN_CAL,
                                    mach_max=mach_max)
    r2.update(target_margin_cal=FIN_TARGET_MARGIN_CAL,
              margin_target_used_cal=STATIC_MARGIN_MIN_CAL, target_met=False,
              target_fallback_reason='target_not_met_within_search_limit')
    return r2


def fin_sizing_flown(aero_args: Dict, solver_args: Dict, t_max: float,
                     x_cg_full: float, x_cg_empty: float,
                     mach_max_now: Optional[float]) -> Dict:
    """Kanat önerisi + öneriyle AYNI girdilerde yeniden uçuşun hükmü.

    Öneri, uçuşun Mach aralığı için boyutlanır; öneriyle uçan araç daha
    hızlıysa (süpersonikte kanat etkinliği düşer) yeni Mach aralığıyla
    yeniden boyutlanır. En çok ``FIN_SIZING_MAX_FLIGHTS`` uçuş ve
    ``FIN_SIZING_TIME_BUDGET_S`` saniye. ``verification`` alanı son uçuşun
    hükmünü (``stability_verdict_code``) ve Mach aralığını taşır.
    """
    import time
    from hrma.analysis.six_dof_trajectory import (
        BarrowmanAero, SixDOFTrajectory, stability_verdict_code)
    t0 = time.monotonic()
    # V307/ONARIM2-UÇUŞ-ARAÇ (M7-UCUS-11): boyutlandırma rüzgârsız referans
    # uçuşlarla; rüzgârlı koşuda başlangıç Mach'ı da mevcut kanatla rüzgârsız
    # referans uçuştan (günün rüzgârı açıklığı değiştirmez).
    ruzgar = _wind_of(solver_args)
    ref_args = _reference_solver_args(solver_args)
    if ruzgar != FIN_SIZING_REFERENCE_WIND_MPS:
        res0 = SixDOFTrajectory(aero=BarrowmanAero(**aero_args),
                                **ref_args).solve(t_max=t_max)
        mach_max_now = res0.get('max_mach')
    mm = float(mach_max_now) if (mach_max_now is not None
                                 and math.isfinite(mach_max_now)) else 0.0
    r = _fin_sizing_loop(aero_args, ref_args, t_max, x_cg_full, x_cg_empty,
                         mm, t0)
    r['reference_flight'] = {'wind_speed_mps': FIN_SIZING_REFERENCE_WIND_MPS,
                             'basis': FIN_SIZING_REFERENCE_BASIS}
    dg = r.get('verification') or {}
    if (ruzgar != FIN_SIZING_REFERENCE_WIND_MPS and dg.get('status') == 'flown'
            and r.get('min_fin_span_m') is not None):
        # Öneri, kullanıcının rüzgârıyla AYNI girdilerde uçurulur; yazılan
        # hüküm bu uçuşun (referans uçuşun hükmü ayrıca saklanır).
        r['reference_flight']['verification'] = dg
        aero = BarrowmanAero(**dict(aero_args, fin_span=r['min_fin_span_m']))
        res = SixDOFTrajectory(aero=aero, **solver_args).solve(t_max=t_max)
        m2 = res.get('max_mach')
        r['verification'] = {
            'status': 'flown', 'flights': dg.get('flights', 0) + 1,
            'verdict': stability_verdict_code(
                res.get('stable'), res['static_margin_full'],
                res['static_margin_empty'], res.get('max_alpha_deg')),
            'end_reason': res.get('end_reason'),
            'max_mach': (float(m2) if m2 is not None else None),
            'apogee_m': res.get('apogee'), 'wind_speed_mps': ruzgar}
    return r


def _fin_sizing_loop(aero_args: Dict, solver_args: Dict, t_max: float,
                     x_cg_full: float, x_cg_empty: float, mm: float,
                     t0: float) -> Dict:
    """``fin_sizing_flown``ın boyutlandırma döngüsü (verilen çözücü
    argümanlarıyla — rüzgârsız referans)."""
    import time
    from hrma.analysis.six_dof_trajectory import (
        BarrowmanAero, SixDOFTrajectory, stability_verdict_code)
    r = None
    for k in range(FIN_SIZING_MAX_FLIGHTS):
        r = fin_span_for_target(aero_args, x_cg_full, x_cg_empty, mach_max=mm)
        if r['min_fin_span_m'] is None:
            r['verification'] = {'status': 'not_flown', 'flights': k}
            return r
        if r['min_fin_span_m'] <= r['current_fin_span_m'] + FIN_SPAN_SEARCH_STEP_M:
            # Bugünkü açıklık ölçütü zaten sağlıyor: hüküm kanattan değil
            # (ör. α koşulu) — açıklık önerilmez, nedeni adlı.
            r['min_fin_span_m'] = None
            r['reason'] = 'static_criterion_already_met_at_current_span'
            r['verification'] = {'status': 'not_flown', 'flights': k}
            return r
        if time.monotonic() - t0 > FIN_SIZING_TIME_BUDGET_S:
            r['verification'] = {'status': 'time_budget', 'flights': k}
            return r
        aero = BarrowmanAero(**dict(aero_args, fin_span=r['min_fin_span_m']))
        res = SixDOFTrajectory(aero=aero, **solver_args).solve(t_max=t_max)
        m2 = res.get('max_mach')
        hukum = stability_verdict_code(
            res.get('stable'), res['static_margin_full'],
            res['static_margin_empty'], res.get('max_alpha_deg'))
        r['verification'] = {
            'status': 'flown', 'flights': k + 1, 'verdict': hukum,
            'end_reason': res.get('end_reason'),
            'max_mach': (float(m2) if m2 is not None else None),
            'apogee_m': res.get('apogee')}
        if hukum == 'stable':
            return r
        if m2 is None or not math.isfinite(m2) or m2 <= mm + 1e-9:
            return r
        mm = float(m2)
    return r


# ---------------------------------------------------------------------------
# V307/FS-UÇUŞ-2 (A1) — KANAT GEOMETRİSİ KURALI
#
# ÖLÇÜLDÜ (docs/scofield/raw/OH/V307/fs-ucus-2/olcum/ucus_once.json): sayfa
# kanadı gövdeden bağımsız sabit gönderiyordu (kök 0,20 / uç 0,10 / ok
# 0,08 m, açıklık alanı 0,11 m). Ø0,473 m sıvı ve Ø0,212 m hibrit örnekte
# statik marj −1,86 / 0,45 kalibre → "araç kararsız — oynatma kapalı".
#
# Kural iki parçadır; kullanıcının girdiği alan HER ZAMAN onun değeridir:
#   1. Planform (kök/uç veteri, ok) — HRMA SEÇİMİ, kaynaklı bir tasarım
#      kuralı DEĞİL: örnek aracın planformu (Ø0,15 m gövdede 0,20/0,10/0,08 m;
#      D28'den beri bu sayfanın sabit kanadı) gövde çapıyla ÖLÇEKLENİR
#      (geometrik benzerlik). Yeni sayı yok. Gerekçe: Barrowman kanat
#      normal kuvvet eğimi ve basınç merkezi planformun kalibre cinsinden
#      oranlarına bağlıdır; benzer planform kanat etkinliğini çapla
#      ölçeklenmiş tutar, büyüklüğü açıklık belirler.
#   2. Açıklık — KAYNAKLI BANT + HEDEF: statik marj (dolu ve boş) uçuşun
#      Mach aralığında (0 … en yüksek Mach) en düşük değeri kanat hedefine
#      (``FIN_TARGET_MARGIN_CAL``: Niskanen bandının ortası, HRMA seçimi; 4·d
#      içinde sağlanamazsa eşik ``STATIC_MARGIN_MIN_CAL``, adıyla) ulaşan EN
#      KÜÇÜK açıklık (künye ``STATIC_MARGIN_SOURCE``);
#      aynı Barrowman modeli + çözücünün Mach düzeltmesi (Niskanen eq. 3.40)
#      ve aynı ağırlık merkezi. Açıklık uçuşla doğrulanır: uçuş boyutlandırma
#      aralığından hızlıysa aralık genişletilip yeniden boyutlanır.
# ---------------------------------------------------------------------------

#: Kural adları (istek alanı ``fin_geometry_rule``).
FIN_GEOMETRY_RULES = ('static_margin',)

#: Örnek aracın kanat planformu [m]. D28'den bu yana ``launch_site.html``
#: ``LS_FIXED_AIRFRAME``ında duran sabit kanat (HRMA seçimi; gerçek bir
#: roketin verisi değil). 3.0.7'de sayfadan buraya taşındı: tek yer.
#: Her anahtar kendi satırında (V307/KIRMIZI-C): ΔP/Pc bekçileri
#: (test_stability_sivi, test_d27_sivi_a1) sayıyı SATIR bağlamıyla okur;
#: tek satırda 'fin_tip_chord' içindeki 'p_c' alt dizgesi kök veterinin
#: 0,20 m'sini ΔP/Pc sanıyordu. Değerler aynı.
EXAMPLE_FIN_PLANFORM_M = {
    'fin_root_chord': 0.20,
    'fin_tip_chord': 0.10,
    'fin_sweep': 0.08,
}

#: Kuralın uçuş sınırı (HRMA seçimi; Mach aralığı yakınsaması için).
FIN_RULE_MAX_FLIGHTS = 4

#: Kural kaynağı adları (yanıtta her alanın ``source``u).
FIN_SOURCE_SUPPLIED = 'supplied'
FIN_SOURCE_PLANFORM_RULE = 'rule_planform'
FIN_SOURCE_SPAN_RULE = 'rule_static_margin'
FIN_SOURCE_SOLVER_DEFAULT = 'solver_default'

def _example_body_diameter() -> float:
    from hrma.analysis.flight_vehicle import EXAMPLE_VEHICLE
    return float(EXAMPLE_VEHICLE['airframe_resolved']['body_diameter_m'])


FIN_PLANFORM_RULE_BASIS = (
    'HRMA choice, not a sourced design rule: the fin planform of the example '
    'vehicle (root chord %g m, tip chord %g m, leading-edge sweep %g m on its '
    '%g m body) scaled with this body diameter (geometric similarity): root '
    'chord = (%g/%g) x body diameter, tip chord = %g x root chord, sweep = '
    '%g x root chord. A chord you enter is kept, and the missing ones follow '
    'from it. The Barrowman fin normal-force slope and centre of pressure '
    'depend on the planform measured in body calibres, so the size of the '
    'fin is then set by the span (next rule).' % (
        EXAMPLE_FIN_PLANFORM_M['fin_root_chord'],
        EXAMPLE_FIN_PLANFORM_M['fin_tip_chord'],
        EXAMPLE_FIN_PLANFORM_M['fin_sweep'], _example_body_diameter(),
        EXAMPLE_FIN_PLANFORM_M['fin_root_chord'], _example_body_diameter(),
        EXAMPLE_FIN_PLANFORM_M['fin_tip_chord'] / EXAMPLE_FIN_PLANFORM_M['fin_root_chord'],
        EXAMPLE_FIN_PLANFORM_M['fin_sweep'] / EXAMPLE_FIN_PLANFORM_M['fin_root_chord']))

FIN_SPAN_RULE_BASIS = (
    'Smallest fin span for which the lowest static margin, full and empty, '
    'from Mach 0 to the highest Mach of the windless reference flight '
    'reaches the fin target. '
    + FIN_TARGET_BASIS + ' Same Barrowman model with the solver Mach '
    'correction of the fin term (Niskanen eq. 3.40), same centre of gravity '
    '(supplied or the declared length-fraction estimate). The reference '
    'vehicle is flown with that span; if that flight is faster than the Mach '
    'range the span was sized for, the span is sized again and flown again. '
    + FIN_SIZING_REFERENCE_BASIS + ' Threshold source: ' + STATIC_MARGIN_SOURCE)


def fin_planform_ratios() -> Dict[str, float]:
    """Kuralın oranları: kök/çap, uç/kök, ok/kök (örnek planformdan)."""
    p = EXAMPLE_FIN_PLANFORM_M
    return {'root_per_diameter': p['fin_root_chord'] / _example_body_diameter(),
            'tip_per_root': p['fin_tip_chord'] / p['fin_root_chord'],
            'sweep_per_root': p['fin_sweep'] / p['fin_root_chord']}


def fin_planform_by_rule(body_diameter: float, root: Optional[float] = None,
                         tip: Optional[float] = None,
                         sweep: Optional[float] = None) -> Dict[str, Tuple[float, str]]:
    """Eksik planform alanları kuraldan; verilenler aynen.

    Dönüş: ``{'fin_root_chord': (değer, kaynak), 'fin_tip_chord': …,
    'fin_sweep': …}``; kaynak ``FIN_SOURCE_SUPPLIED`` ya da
    ``FIN_SOURCE_PLANFORM_RULE``.
    """
    o = fin_planform_ratios()
    d = float(body_diameter)
    out = {}
    if root is None:
        out['fin_root_chord'] = (o['root_per_diameter'] * d, FIN_SOURCE_PLANFORM_RULE)
    else:
        out['fin_root_chord'] = (float(root), FIN_SOURCE_SUPPLIED)
    kok = out['fin_root_chord'][0]
    out['fin_tip_chord'] = ((float(tip), FIN_SOURCE_SUPPLIED) if tip is not None
                            else (o['tip_per_root'] * kok, FIN_SOURCE_PLANFORM_RULE))
    out['fin_sweep'] = ((float(sweep), FIN_SOURCE_SUPPLIED) if sweep is not None
                        else (o['sweep_per_root'] * kok, FIN_SOURCE_PLANFORM_RULE))
    return out


#: V307/FS-KÜÇÜK (kalem 5): çalkantı bloğu verilmiş uçuşta kuralın son uçuşu.
FIN_RULE_COUPLED_FINAL_BASIS = (
    'The fin span is sized on rigid-body flights: the static-margin criterion '
    'is a property of the rigid airframe (centre of pressure and centre of '
    'gravity), which slosh does not change. The vehicle is then flown once '
    'with that span and the propellant tanks coupled (the slosh block of the '
    'request); that coupled flight is the one published. Its Mach range is '
    'checked against the fin criterion in fin_geometry.')


def fly_with_span_rule(aero_args: Dict, solver_args: Dict, t_max: float,
                       x_cg_full: float, x_cg_empty: float,
                       coupled_solver_args: Optional[Dict] = None):
    """Açıklığı kuralla boyutla ve uçur: ``(aero, solver, res, kayıt)``.

    Boyutlandırma Mach 0 ile başlar; her uçuştan sonra uçuşun en yüksek
    Mach'ı boyutlandırma aralığını aşıyorsa aralık o Mach'a genişletilir ve
    yeniden boyutlanıp uçulur (en çok ``FIN_RULE_MAX_FLIGHTS``). Ölçüt
    sağlanamazsa ``aero``/``solver``/``res`` None ve ``kayıt['status']``
    'not_met' (neden adıyla) — çağıran uçuşu adıyla reddeder.

    V307/FS-KÜÇÜK (kalem 5): ``coupled_solver_args`` (çalkantı tanklarıyla
    çözücü argümanları) verilirse boyutlandırma uçuşları RİJİT kalır (statik
    marj ölçütü rijit gövdenin özelliğidir), boyutlanan açıklıkla araç BİR kez
    bağlaşık uçurulur ve yayımlanan o uçuştur (``kayıt['final_flight']``).
    Ölçüldü (fs-kucuk/olcum): her uçuş bağlaşık olunca örnek sıvıda 56,8 s
    (bütçe 60 s); motor sayfasının tek bağlaşık uçuşu 18,6 s.
    """
    from hrma.analysis.six_dof_trajectory import SixDOFTrajectory
    # V307/ONARIM2-UÇUŞ-ARAÇ (M7-UCUS-11): açıklık rüzgârsız referans
    # uçuşlarla boyutlanır; rüzgârlı koşuda yayımlanan uçuş, boyutlanan
    # açıklıkla kullanıcının rüzgârında BİR kez daha uçulur. Rüzgâr 0 ise
    # referans uçuş yayımlanan uçuştur (bugünküyle bit-aynı).
    ruzgar = _wind_of(solver_args)
    sonuc = _fly_with_span_rule_rigid(aero_args,
                                      _reference_solver_args(solver_args),
                                      t_max, x_cg_full, x_cg_empty)
    aero, solver, res, kayit = sonuc
    if kayit is not None:
        kayit['reference_flight'] = {
            'wind_speed_mps': FIN_SIZING_REFERENCE_WIND_MPS,
            'basis': FIN_SIZING_REFERENCE_BASIS}
    if aero is None:
        return sonuc
    if coupled_solver_args is None:
        if ruzgar == FIN_SIZING_REFERENCE_WIND_MPS:
            return sonuc
        solver = SixDOFTrajectory(aero=aero, **solver_args)
        res = solver.solve(t_max=t_max)
        m2 = res.get('max_mach')
        kayit['final_flight'] = {
            'model': 'rigid', 'wind_speed_mps': ruzgar,
            'fin_span_m': float(kayit['flights'][-1]['fin_span_m']),
            'flight_max_mach': (float(m2) if m2 is not None else None),
            'basis': FIN_SIZING_REFERENCE_BASIS}
        return aero, solver, res, kayit
    solver = SixDOFTrajectory(aero=aero, **coupled_solver_args)
    res = solver.solve(t_max=t_max)
    m2 = res.get('max_mach')
    kayit['final_flight'] = {
        'model': 'coupled_slosh', 'wind_speed_mps': _wind_of(coupled_solver_args),
        'fin_span_m': float(kayit['flights'][-1]['fin_span_m']),
        'flight_max_mach': (float(m2) if m2 is not None else None),
        'basis': FIN_RULE_COUPLED_FINAL_BASIS}
    return aero, solver, res, kayit


def _fly_with_span_rule_rigid(aero_args: Dict, solver_args: Dict, t_max: float,
                              x_cg_full: float, x_cg_empty: float):
    """``fly_with_span_rule``ın boyutlandırma döngüsü (verilen çözücü
    argümanlarıyla; değişmedi)."""
    from hrma.analysis.six_dof_trajectory import BarrowmanAero, SixDOFTrajectory
    mm = 0.0
    ucuslar = []
    aero = solver = res = None
    for k in range(FIN_RULE_MAX_FLIGHTS):
        r = fin_span_for_target(aero_args, x_cg_full, x_cg_empty, mach_max=mm)
        hedef = {'target_margin_cal': r['target_margin_cal'],
                 'margin_target_used_cal': r['margin_target_used_cal'],
                 'target_met': r['target_met']}
        if r['min_fin_span_m'] is None:
            return None, None, None, dict(
                hedef, status='not_met', reason=r.get('reason'),
                mach_range_max=mm, search_max_span_m=r['search_max_span_m'],
                flights=ucuslar)
        if ucuslar and r['min_fin_span_m'] == ucuslar[-1]['fin_span_m']:
            # Genişletilen aralık aynı açıklığı verdi: o açıklıkla uçuş zaten
            # yapıldı ve en yüksek Mach'ı bu aralığın içinde — yeniden uçmaya
            # gerek yok (aynı girdi aynı çözümü verir).
            return aero, solver, res, dict(hedef, status='sized', mach_range_max=mm,
                                           flights=ucuslar)
        args = dict(aero_args, fin_span=r['min_fin_span_m'])
        aero = BarrowmanAero(**args)
        solver = SixDOFTrajectory(aero=aero, **solver_args)
        res = solver.solve(t_max=t_max)
        m2 = res.get('max_mach')
        ucuslar.append({'fin_span_m': r['min_fin_span_m'], 'sized_for_mach_max': mm,
                        'margin_target_used_cal': r['margin_target_used_cal'],
                        'flight_max_mach': (float(m2) if m2 is not None else None)})
        if m2 is None or not math.isfinite(m2) or m2 <= mm + 1e-9:
            return aero, solver, res, dict(hedef, status='sized', mach_range_max=mm,
                                           flights=ucuslar)
        mm = float(m2)
    return aero, solver, res, dict(hedef, status='mach_range_not_covered',
                                   mach_range_max=ucuslar[-1]['sized_for_mach_max'],
                                   flights=ucuslar)


def fin_geometry_block(aero, x_cg_full: float, x_cg_empty: float,
                       sources: Dict[str, str], sizing: Optional[Dict],
                       flight_max_mach: Optional[float]) -> Dict:
    """Yanıtın ``fin_geometry`` bloğu: alan, değer, kaynak + ölçüt durumu.

    Marjlar uçan aracın Barrowman modelinden: Mach 0'da (dolu/boş; çözücünün
    ``static_margin_full/empty``iyle aynı tanım) ve uçuşun Mach aralığında
    en küçük değer.
    """
    _mm, machlar = _mach_izgarasi(flight_max_mach)
    tam = float(aero.static_margin(x_cg_full))
    bos = float(aero.static_margin(x_cg_empty))
    en_kucuk = float(min(min(aero.static_margin(x_cg_full, m),
                             aero.static_margin(x_cg_empty, m)) for m in machlar))
    alt, ust = STATIC_MARGIN_BAND_CAL
    # V307/ONARIM2-UÇUŞ-ARAÇ (M7-UCUS-11): açıklığın boyutlandığı rüzgârsız
    # referans uçuşun Mach aralığı ve orada en düşük marj (kural notu bu
    # sayıyı yazar; yukarıdaki alanlar yayımlanan uçuşun aralığındadır).
    ref_mm = (sizing or {}).get('mach_range_max') if (sizing or {}).get(
        'reference_flight') else None
    ref_min = None
    if ref_mm is not None and math.isfinite(float(ref_mm)):
        _rm, ref_machlar = _mach_izgarasi(float(ref_mm))
        ref_mm = _rm
        ref_min = float(min(min(aero.static_margin(x_cg_full, m),
                                aero.static_margin(x_cg_empty, m))
                            for m in ref_machlar))
    return {
        'rule': 'static_margin',
        'reference_mach_range_max': ref_mm,
        'min_margin_over_reference_mach_range_cal': ref_min,
        'fields': sources,
        'status': (sizing or {}).get('status', 'not_sized'),
        'sizing': sizing,
        'criterion': {
            'threshold_cal': alt, 'band_cal': [alt, ust],
            'source': STATIC_MARGIN_SOURCE,
            'mach_range_max': _mm,
            # Önerilen kanadın hedefi (HRMA seçimi) ve bu uçuşta kullanılan
            # (hedef ya da, 4·d içinde sağlanamadıysa, eşik).
            'target_cal': FIN_TARGET_MARGIN_CAL,
            'target_used_cal': (sizing or {}).get('margin_target_used_cal'),
            'target_met': (sizing or {}).get('target_met'),
            'search_max_calibers': FIN_SPAN_SEARCH_MAX_CALIBERS,
            'target_basis': FIN_TARGET_BASIS,
        },
        'margin_full_cal': tam, 'margin_empty_cal': bos,
        'min_margin_over_mach_range_cal': en_kucuk,
        'criterion_met_over_mach_range': bool(en_kucuk > alt),
        'target_met_over_mach_range': bool(en_kucuk >= FIN_TARGET_MARGIN_CAL),
        'above_band_upper': bool(max(tam, bos) > ust),
        'planform_rule': dict(
            example_root_chord_m=EXAMPLE_FIN_PLANFORM_M['fin_root_chord'],
            example_tip_chord_m=EXAMPLE_FIN_PLANFORM_M['fin_tip_chord'],
            example_sweep_m=EXAMPLE_FIN_PLANFORM_M['fin_sweep'],
            example_body_diameter_m=_example_body_diameter(),
            **fin_planform_ratios()),
        'planform_basis': FIN_PLANFORM_RULE_BASIS,
        'span_basis': FIN_SPAN_RULE_BASIS,
    }


def _sample_index(n: int, max_points: int) -> np.ndarray:
    return np.linspace(0, n - 1, min(int(max_points), n)).astype(int)


def flight_events(solver, res: Dict, descent: Optional[Dict]) -> List[Dict]:
    """Tam çözünürlüklü çözümden olaylar (her biri kaynağıyla).

    ``t_s`` mutlak uçuş zamanı; konum alanları (K, D, saha üstü irtifa) o
    andaki çözüm değeridir (örnek aralarında doğrusal ara değer).

    V307/FS-UÇUŞ-2 (A5) — YANMA SONU TEK TANIM: uçurulan itki girdisinin
    bittiği an (``solver.t_burn``: itki eğrisinin son zamanı ya da sabit
    itkide yanma süresi; çözücü itkiyi o anda sıfırlar). Bu sayı aracın
    "Yanma süresi" alanıyla (``vehicle.burn_time`` = uçuş itkisinin
    ``flight_thrust.burn_time``i) aynıdır; ölçüldü (fs-ucus-2/olcum/
    ucus_once.json): katı 2,2771 s (motor itki eğrisi), sıvı 30 s (sıvı
    sayfasında girilen yanma süresi, sabit itki), hibrit 10,4143 s (N₂O
    boşalma eğrisi) — üçünde de alan = olay = çözücü.
    """
    t = np.asarray(res['time'], dtype=float)
    pos = np.asarray(res['position'], dtype=float)
    alt = np.asarray(res['altitude'], dtype=float)
    spd = np.asarray(res['speed'], dtype=float)
    q = np.asarray(res['dynamic_pressure'], dtype=float)
    mach = np.asarray(res['mach'], dtype=float)
    seg_t, seg = [t], [(pos, alt, spd, mach, q)]
    if descent and descent.get('status') == 'solved':
        seg_t.append(np.asarray(descent['time'], dtype=float))
        seg.append((descent['position'], descent['altitude'], descent['speed'],
                    descent['mach'], descent['dynamic_pressure']))
    T = np.concatenate([s for s in seg_t])
    P = np.concatenate([s[0] for s in seg], axis=1)
    A = np.concatenate([s[1] for s in seg])
    V = np.concatenate([s[2] for s in seg])
    M = np.concatenate([s[3] for s in seg])
    Q = np.concatenate([s[4] for s in seg])

    def at(key, tt, source, **extra):
        ev = {'key': key, 't_s': float(tt), 'source': source,
              'north_m': float(np.interp(tt, T, P[0])),
              'east_m': float(np.interp(tt, T, P[1])),
              'altitude_agl_m': float(np.interp(tt, T, A)),
              'speed_mps': float(np.interp(tt, T, V)),
              'mach': float(np.interp(tt, T, M)),
              'dynamic_pressure_pa': float(np.interp(tt, T, Q))}
        ev.update(extra)
        return ev

    out = [at('liftoff', T[0], 'solver_start')]
    t_burn = float(solver.t_burn)
    if T[0] < t_burn <= t[-1]:
        out.append(at('burnout', t_burn, 'thrust_input_end'))
    if Q.size:
        i = int(np.argmax(Q))
        out.append(at('max_q', T[i], 'solver_series_max'))
    if res.get('end_reason') == 'apogee' and res.get('apogee_time') is not None:
        out.append(at('apogee', res['apogee_time'], 'solver_apogee'))
    if descent and descent.get('status') == 'solved':
        kurtarma = descent.get('recovery') or {}
        if kurtarma.get('deployed') and kurtarma.get('deploy_t_s') is not None:
            out.append(at('deploy', kurtarma['deploy_t_s'], 'apogee_plus_deploy_delay'))
        out.append(at('landing', descent['impact']['t_s'], 'descent_ground_contact'))
    out.sort(key=lambda e: e['t_s'])
    return out


def flight_track(solver, res: Dict, descent: Optional[Dict], *,
                 lat0: Optional[float], lon0: Optional[float],
                 max_points: int) -> Dict:
    """Yükseliş (+ iniş) serisini tek izde birleştirir; enlem/boylam ekler.

    Yükseliş kolu ``max_points`` örneğe, iniş kolu en fazla ``max_points``
    örneğe seyreltilir (ikisi de uç noktaları korur). ``lat0``/``lon0``
    verilmezse enlem/boylam dizileri YAYIMLANMAZ (adıyla belirtilir).
    """
    h0 = float(solver.launch_altitude)
    n = len(res['time'])
    ia = _sample_index(n, max_points)
    t = [np.asarray(res['time'], dtype=float)[ia]]
    pos = [np.asarray(res['position'], dtype=float)[:, ia]]
    alt = [np.asarray(res['altitude'], dtype=float)[ia]]
    spd = [np.asarray(res['speed'], dtype=float)[ia]]
    mach = [np.asarray(res['mach'], dtype=float)[ia]]
    q = [np.asarray(res['dynamic_pressure'], dtype=float)[ia]]
    t_burn = float(solver.t_burn)
    phase = ['powered' if tt < t_burn else 'coast' for tt in t[0]]
    descent_n = 0
    if descent and descent.get('status') == 'solved':
        nd = len(descent['time'])
        idd = _sample_index(nd, max_points)[1:]      # ilk örnek = apoje (yinelenmez)
        descent_n = int(idd.size)
        t.append(np.asarray(descent['time'])[idd])
        pos.append(np.asarray(descent['position'])[:, idd])
        alt.append(np.asarray(descent['altitude'])[idd])
        spd.append(np.asarray(descent['speed'])[idd])
        mach.append(np.asarray(descent['mach'])[idd])
        q.append(np.asarray(descent['dynamic_pressure'])[idd])
        phase += ['descent'] * descent_n
    T = np.concatenate(t)
    P = np.concatenate(pos, axis=1)
    A = np.concatenate(alt)
    samples = {
        'time_s': T.tolist(),
        'phase': phase,
        'north_m': P[0].tolist(),
        'east_m': P[1].tolist(),
        'altitude_agl_m': A.tolist(),
        'altitude_msl_m': (A + h0).tolist(),
        'downrange_m': np.hypot(P[0], P[1]).tolist(),
        'speed_mps': np.concatenate(spd).tolist(),
        'mach': np.concatenate(mach).tolist(),
        'dynamic_pressure_pa': np.concatenate(q).tolist(),
    }
    geodetic = {'status': 'not_published',
                'reason': 'site_latitude_or_longitude_not_supplied'}
    if (lat0 is not None and lon0 is not None
            and math.isfinite(lat0) and math.isfinite(lon0)):
        la, lo, hm = enu_to_geodetic(lat0, lon0, h0, P[0], P[1], A)
        samples['latitude_deg'] = np.asarray(la, dtype=float).tolist()
        samples['longitude_deg'] = np.asarray(lo, dtype=float).tolist()
        geodetic = {'status': 'published', 'function': 'launch_site.enu_to_geodetic',
                    'site': {'latitude_deg': float(lat0), 'longitude_deg': float(lon0),
                             'elevation_m': h0}}
    return {
        'schema': TRACK_SCHEMA,
        'frame': {'north_east': 'flat-Earth local frame anchored at the pad '
                                '(6-DOF solver frame)',
                  'altitude_agl': 'above_launch_site',
                  'altitude_msl': 'above_launch_site + launch site elevation'},
        'samples': samples,
        'sampling': {'ascent_points_solved': int(n), 'ascent_points': int(ia.size),
                     'descent_points': descent_n},
        'geodetic': geodetic,
        'events': flight_events(solver, res, descent),
    }
