"""V306/UÇUŞ-2 bekçileri — yörünge (3-DOF) ve 6-DOF aynı itkiyi, aynı fizikle
uçurur; hükümler gerçeği söyler (3.0.6, mühendis turu 2 Kas).

K-L3   sıvı L3: 6-DOF itkiyi irtifaya göre düzeltir (M-SIVI-18): uç A_e'yi
       çözücüye geçirir; uç noktalar motorla bit düzeyinde tutar
K-L5   sıvı L5: itki altında yere çarpan araca "KARARLI" denmez (M-SIVI-25)
K-L4   katı/hibrit L4: havasız bölgedeki α hükme girmez (M-KATI-25, q penceresi)
K3     yük çarpanı algılanan ivmedir (M-KATI-28): sürüklemesiz dikey uçuşta
       tepe değer F/(m_f·g0)
K2     6-DOF yanma sonu kırılma noktası: vakumda dikey uçuş bağımsız ODE ile
K-0    kalkış yok: grafik geri çekilir, hüküm adıyla (M-KATI-29)
K-H    hibrit /calculate 1 atm tasarım ortamında F_ref + p_ref·A_e ==
       motorun thrust_vacuum_n'i (kayıp modeli çapası; HİBRİT-MODEL'in
       1,0 bar ⟷ 101 325 Pa farkı RAPOR'da, burada KİLİTLENMEZ)
K-I    yayımlanan uçuş impulsu uçan eğrinin integrali (örtük ateşleme)

Vakalar mühendis turunun gerçek API gövdeleridir
(docs/scofield/raw/OH/V306/muhendis-turu/*/vakalar/L*.json); gövdeye yalnız
panelin artık gönderdiği A_e + p_ref eklenir (flight_vehicle.
motor_flight_thrust — panelle aynı kaynak). Kanıt ve ters mutasyonlar:
docs/scofield/raw/OH/V306/ucus2/RAPOR.md.
"""
import contextlib
import io
import json
import math
import pathlib
import shutil
import subprocess

import pytest

from hrma.analysis.flight_vehicle import motor_flight_thrust
from tests.support.kanit import kanit_gerekli
from tests.support.esikler import PLATFORM_GURULTU_TABANI_REL

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
VAKA = KOK / 'docs/scofield/raw/OH/V306/muhendis-turu'
NODE = shutil.which('node')
TIP = {'sivi': 'liquid', 'hibrit': 'hybrid', 'kati': 'solid'}


def _vaka(sistem, L):
    yol = kanit_gerekli(VAKA / sistem / 'vakalar' / (L + '.json'))
    return json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))


def _govde(vaka, uc):
    return dict([r for r in vaka['istekler'] if r['uc'] == uc][-1]['govde'])


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(istemci, uc, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        r = istemci.post(uc, json=govde)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


def _sixdof(istemci, sistem, L, telafi=True):
    """Turun 6-DOF gövdesi + panelin artık gönderdiği A_e/p_ref."""
    v = _vaka(sistem, L)
    u = motor_flight_thrust(TIP[sistem],
                            _govde(v, '/api/flight-vehicle')['results'])
    g = _govde(v, '/api/six-dof-analysis')
    if telafi:
        g['nozzle_exit_area'] = u['nozzle_exit_area_m2']
        g['thrust_reference_pressure'] = u['thrust_reference_pressure_pa']
    return _post(istemci, '/api/six-dof-analysis', g), u


# ---------------------------------------------------------------------------
# K-L3 — 6-DOF itki irtifa düzeltmesi (M-SIVI-18)
# ---------------------------------------------------------------------------
def test_L3_sivi_6dof_itkiyi_irtifaya_gore_duzeltir(istemci):
    j, u = _sixdof(istemci, 'sivi', 'L3')
    tac = j['thrust_altitude_compensation']
    assert tac['modelled'] is True, tac
    # Uç, panelin gönderdiği alanı çözücüye AYNEN geçirir.
    assert tac['nozzle_exit_area_m2'] == u['nozzle_exit_area_m2']
    assert tac['reference_pressure_pa'] == u['thrust_reference_pressure_pa']
    assert tac['vacuum_thrust_increment_n'] == pytest.approx(
        u['thrust_reference_pressure_pa'] * u['nozzle_exit_area_m2'],
        rel=1e-15)
    kodlar = [w.get('code') for w in j['summary'].get('warnings') or []]
    assert 'warn.sixdof.thrust_not_altitude_compensated' not in kodlar
    # A_e verilmeyen gövdede düzeltme YOK ve beyanlı; apoje irtifada eksik
    # itkiyle uçtuğu için belirgin düşük (ölçüldü: 22,1 ⟷ 25,6 km).
    j0, _ = _sixdof(istemci, 'sivi', 'L3', telafi=False)
    assert j0['thrust_altitude_compensation']['modelled'] is False
    assert j['summary']['apogee'] > 1.10 * j0['summary']['apogee']


def test_L3_sivi_itki_uc_noktalari_motorla_bit_duzeyinde():
    """p_a = p_ref → F_ref (bit-eş), p_a = 0 → motorun thrust_vacuum'u."""
    from hrma.analysis.six_dof_trajectory import (BarrowmanAero,
                                                  SixDOFTrajectory)
    res = _govde(_vaka('sivi', 'L3'), '/api/flight-vehicle')['results']
    u = motor_flight_thrust('liquid', res)
    f_ref = res['design_summary']['performance']['thrust_sl_N']
    aero = BarrowmanAero(0.2, 0.6, 3.0, 'ogive', 4, 0.3, 0.15, 0.15, 0.1)
    cz = SixDOFTrajectory(aero, 10.0, 5.0, thrust=f_ref, burn_time=10.0,
                          nozzle_exit_area=u['nozzle_exit_area_m2'],
                          thrust_reference_pressure=u[
                              'thrust_reference_pressure_pa'])
    assert cz._thrust_at_altitude(1.0, u['thrust_reference_pressure_pa']) \
        == f_ref
    assert cz._thrust_at_altitude(1.0, 0.0) == pytest.approx(
        res['thrust_vacuum'], rel=1e-14)


# ---------------------------------------------------------------------------
# K-L5 — itki altında yere çarpma "KARARLI" değildir (M-SIVI-25)
# ---------------------------------------------------------------------------
def _rozet_blogu(summary, data, sayfa_motoru, tmp_path):
    """sixdof_panel.js rozet bloğu GERÇEK dosyadan kesilip node'da koşar
    (tests/test_faz5_ui.py düzeneği)."""
    src = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
    bas = src.index('const numOf = (v) =>')
    son = src.index('badges.innerHTML = html;', bas)
    betik = tmp_path / 'rozet.js'
    betik.write_text(
        "'use strict';\n"
        "const s = " + json.dumps(summary) + ";\n"
        "const data = " + json.dumps(data) + ";\n"
        "const usedCurve = false;\n"
        "const sayfaMotoru = " + json.dumps(sayfa_motoru) + ";\n"
        "const aracKuru = null;\n"
        "function badge(text, kind) { return '[' + kind + ']' + text + '\\n'; }\n"
        "function T(k, f) { return f; }\n"
        "function TF(k, p, f) {\n"
        "  return String(f).replace(/\\{(\\w+)\\}/g,"
        " (w, n) => (p && n in p) ? String(p[n]) : w);\n"
        "}\n" + src[bas:son] + "\nprocess.stdout.write(html);\n",
        encoding='utf-8')
    r = subprocess.run([NODE, str(betik)], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_L5_sivi_itki_altinda_yere_carpma_hukmu(istemci):
    j, _ = _sixdof(istemci, 'sivi', 'L5')
    s = j['summary']
    fv = s['flight_verdict']
    assert s['end_reason'] == 'ground'
    assert fv['flight'] == 'ground_impact_under_power', fv
    assert fv['t_end_s'] < fv['burn_time_s']
    assert s['stable'] is None
    assert fv['stability'] == 'not_evaluated'


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_L5_sivi_rozet_KARARLI_demez(istemci, tmp_path):
    j, _ = _sixdof(istemci, 'sivi', 'L5')
    out = _rozet_blogu(j['summary'], j, None, tmp_path)
    assert 'GROUND IMPACT UNDER POWER' in out, out
    assert '[ok]STABLE' not in out, out
    assert 'END: ' not in out, 'bitiş nedeni hüküm rozetinde; ikinci kez basıldı'
    assert 'GROUND\n' not in out, 'ham bitiş kodu ekranda'


# ---------------------------------------------------------------------------
# K-L4 — havasız bölgedeki α hükme girmez (M-KATI-25, M-HIBRIT-30)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('sistem', ['kati', 'hibrit'])
def test_L4_q_penceresi(istemci, sistem):
    j, _ = _sixdof(istemci, sistem, 'L4')
    s = j['summary']
    pen = j['alpha_window']
    assert pen['dynamic_pressure_fraction'] == pytest.approx(
        pen['speed_fraction'] ** 2, rel=0)
    # Ölçüldü: atmosferde α ~1°, 85 km üstünde 14-41° (önce: KARARSIZ).
    assert s['max_alpha_deg'] < 3.0, s['max_alpha_deg']
    assert s['max_alpha_low_q_deg'] is not None
    assert s['max_alpha_low_q_deg'] > 10.0
    assert s['stable'] is True
    assert s['flight_verdict']['stability'] == 'stable'
    assert s['flight_verdict']['flight'] == 'apogee'
    # Panel grafiği aynı pencereyi uygulayabilsin: q serisi yayımlanıyor.
    assert len(j['series']['dynamic_pressure_pa']) == len(j['series']['time'])


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_L4_tek_hukum_rozeti(istemci, tmp_path):
    """Aynı ekranda 'UNSTABLE' ile 'OVER-STABLE' birlikte olmaz
    (M-HIBRIT-30): hüküm tek rozettir, marj rozeti yalnız sayıdır."""
    j, _ = _sixdof(istemci, 'hibrit', 'L4')
    out = _rozet_blogu(j['summary'], j, None, tmp_path)
    assert 'UNSTABLE' not in out, out
    assert out.count('[ok]STABLE') == 1, out
    assert 'OVER-STABLE' not in out, out


# ---------------------------------------------------------------------------
# K3 — yük çarpanı algılanan ivmedir (M-KATI-28)
# ---------------------------------------------------------------------------
def _duzlemsel_vakum(F=3000.0, tb=6.0, m_kuru=20.0, m_itici=10.0):
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    ta = TrajectoryAnalyzer()
    ta.set_vehicle_parameters(mass_dry=m_kuru, diameter=0.10,
                              drag_coefficient=0.0)
    with contextlib.redirect_stdout(io.StringIO()):
        return ta.calculate_trajectory(
            {'thrust': F, 'burn_time': tb, 'total_impulse': F * tb,
             'propellant_mass_total': m_itici},
            {'launch_angle': 90.0, 'launch_altitude': 0.0,
             'wind_speed': 0.0})


def test_K3_yuk_carpani_algilanan_ivme():
    from hrma.constants import G_0
    r = _duzlemsel_vakum()
    tm = r['performance']['trajectory_metrics']
    n_kapali = 3000.0 / (20.0 * G_0)
    assert tm['max_load_factor_g'] == pytest.approx(n_kapali, rel=1e-5)
    assert tm['max_g_force'] == tm['max_load_factor_g']
    # Kinematik |dv/dt| yerçekimini içerir: yanma sonunda F/m − g(h).
    fark = tm['max_load_factor_g'] - tm['max_kinematic_acceleration_g']
    assert 0.99 < fark < 1.0, fark
    assert 'SENSED' in tm['load_factor_basis']


# ---------------------------------------------------------------------------
# K2 — 6-DOF yanma sonu kırılma noktası (kapalı biçim ⟷ bağımsız ODE)
# ---------------------------------------------------------------------------
def test_K2_vakum_dikey_6dof_bagimsiz_ode_ile():
    import numpy as np
    from scipy.integrate import solve_ivp
    from hrma.analysis.six_dof_trajectory import (BarrowmanAero,
                                                  SixDOFTrajectory)
    from hrma.constants import G_0
    F, tb, mk, mi = 3000.0, 6.0, 20.0, 10.0
    mdot, R = mi / tb, 6_371_000.0

    def f(t, y):
        h, v = y
        m = mk + mi - mdot * min(t, tb)
        return [v, (F if t < tb else 0.0) / m
                - G_0 * (R / (R + max(h, 0.0))) ** 2]

    def tepe(t, y):
        return y[1] if t > tb else 1.0
    tepe.terminal, tepe.direction = True, -1
    h_ode = float(solve_ivp(f, (0, 400), [0.0, 0.0], rtol=1e-10, atol=1e-10,
                            events=tepe, max_step=0.05).y[0].max())
    aero = BarrowmanAero(0.10, 0.30, 2.0, 'ogive', 4, 0.12, 0.06, 0.08, 0.05)
    with contextlib.redirect_stdout(io.StringIO()):
        h6 = float(SixDOFTrajectory(
            aero, mk, mi, thrust=F, burn_time=tb, cd0=0.0,
            launch_elevation_deg=90.0).solve(t_max=400.0)['apogee'])
    # Ölçüldü: bölmeden önce −%0,30 (yanma sonu adımın içinde), sonra
    # −6,7e-5 (çözücünün rtol 1e-5'i). Eşik ikisinin arasında.
    assert abs(h6 - h_ode) / h_ode < 3e-4, (h6, h_ode)
    h2 = _duzlemsel_vakum()['performance']['trajectory_metrics'][
        'max_altitude']
    assert abs(h2 - h_ode) / h_ode < 1e-5
    assert np.isfinite(h6)


# ---------------------------------------------------------------------------
# K-0 — kalkış yok (M-KATI-29)
# ---------------------------------------------------------------------------
def test_kalkis_yok_grafik_geri_cekilir_ve_hukum(istemci):
    j = _post(istemci, '/api/trajectory-analysis', {
        'initial_mass': 50.0, 'final_mass': 40.0, 'thrust': 300.0,
        'burn_time': 5.0, 'drag_coefficient': 0.5,
        'reference_area': 0.01, 'launch_angle': 90.0})
    assert j['plot_data'] is None
    assert j['plot_withheld_because'] == 'no_liftoff'
    tw = j['no_liftoff']['thrust_to_weight_at_ignition']
    assert tw is not None and tw < 1.0
    assert j['trajectory_data']['flight_status']['lifted_off'] is False


def test_kalkis_yok_uc_sayfada_grafik_yerine_hukum():
    """Üç sayfa künyenin ``draw`` kararına uyar (grafik çizilmez)."""
    for yol in ('hrma/templates/solid.html', 'hrma/templates/liquid.html',
                'hrma/static/js/app.js'):
        metin = (KOK / yol).read_text(encoding='utf-8')
        assert 'renderTrajectoryNotes' in metin, yol
        assert '_kunye.draw' in metin, yol


# ---------------------------------------------------------------------------
# K-H — hibrit /calculate 1 atm uç noktası (kayıp modeli çapası)
# ---------------------------------------------------------------------------
def test_hibrit_calculate_1atm_vakum_itkisi_tutar(istemci):
    v = _vaka('hibrit', 'L3')
    g = _govde(v, '/calculate')
    assert g['atmospheric_pressure'] == 1.01325
    j = _post(istemci, '/calculate', g)
    u = motor_flight_thrust('hybrid', j)
    m = j['motor']
    f_vak = m['altitude_performance']['nozzle_loss_model']['thrust_vacuum_n']
    # V306 (6 Kas, ana model): çıplak rel=1e-15 platform gürültü tabanının
    # altındaydı (test_d20_bekci_cevirisi_a1); birim dönüşümü tabanla kilitlenir.
    assert u['thrust_reference_pressure_pa'] == pytest.approx(
        101325.0, rel=PLATFORM_GURULTU_TABANI_REL)
    assert m['thrust'] + u['thrust_reference_pressure_pa'] \
        * u['nozzle_exit_area_m2'] == pytest.approx(f_vak, rel=1e-12)
    # /calculate'in kendi yörüngesi aynı alanı ve aynı p_ref'i uçurur.
    tac = j['trajectory']['thrust_altitude_compensation']
    assert tac['nozzle_exit_area_m2'] == u['nozzle_exit_area_m2']
    assert tac['reference_pressure_pa'] == u['thrust_reference_pressure_pa']


# ---------------------------------------------------------------------------
# K-I — yayımlanan uçuş impulsu uçan eğrinin integrali
# ---------------------------------------------------------------------------
def test_ucus_impulsu_ucan_egrinin_integrali():
    res = _govde(_vaka('hibrit', 'L1'), '/api/flight-vehicle')['results']
    u = motor_flight_thrust('hybrid', res)
    assert u['curve_source'] == 'motor_blowdown'
    t, f = u['thrust_curve']['time'], u['thrust_curve']['thrust']
    assert t[0] > 0.0   # motorun boşalma serisi ilk adımdan başlıyor
    yamuk = sum(0.5 * (f[i] + f[i + 1]) * (t[i + 1] - t[i])
                for i in range(len(t) - 1))
    # Örtük ateşleme kuralı (normalize_thrust_curve): başa (0, F[0]).
    assert u['total_impulse_ns'] == pytest.approx(yamuk + f[0] * t[0],
                                                  rel=1e-12)
    assert u['motor_published_impulse_ns'] == pytest.approx(
        res['motor']['tank_blowdown']['total_impulse_Ns'], rel=0)


def test_parametrik_ucun_atis_acisi_tek_tanimdan():
    from hrma.analysis.trajectory_analysis import DEFAULT_LAUNCH_ANGLE_DEG
    from hrma.app import _PARAMETRIK_UC_VARSAYILANLARI
    assert _PARAMETRIK_UC_VARSAYILANLARI['launch_angle'][0] \
        is DEFAULT_LAUNCH_ANGLE_DEG
    assert not math.isnan(DEFAULT_LAUNCH_ANGLE_DEG)
