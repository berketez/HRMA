"""ÖH Dalga-15 · termo-uçuş kulvarı · aşama 1 — ONARIM BEKÇİLERİ.

Sekiz kalemin her biri için, kusurun TERSİ enjekte edildiğinde kırmızıya
dönen bir iddia. Mutasyon kanıtları:
``docs/scofield/raw/OH/D15/termo-ucus/a1/mutasyon.py`` (+ ``04_mutasyon.txt``).

Kapsanan kalemler:
  P4B2-02 [kritik] boğulmamış lülede negatif itki yayımlanıyordu
  P4B1-04 aynı yanıtta iki tasarım ΔT'si (100 K yayım / 50-20 K hesap)
  P4B1-05 rejeneratif soğutucu debisi SUYUN cp'siyle, künyesiz
  P4B1-07 risk hükmü üç katsayıdan yalnız birini görüyordu
  P4B3-02 6-DOF takla kesmesi APOJE diye yayımlanıyordu
  P4B3-03 grafikteki yanma-sonu/apoje anı metrikten farklıydı
  P4B3-05 altitude_efficiency deniz seviyesi datumuyla şişiyordu
  P4B3-06 /calculate sahayı motora veriyor, yörüngeye vermiyordu
"""
import math

import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
from hrma.analysis.six_dof_trajectory import BarrowmanAero, SixDOFTrajectory
from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer


# ===================================================================== P4B2-02
def _unchoked_cozum():
    """F144'ün ölçtüğü vaka: P_c = 1,0 bar, P_a = 0,9999 bar, eps = 25."""
    return NozzleFlow1D(
        chamber_pressure=1.0e5, chamber_temperature=3000.0, gamma=1.2,
        molecular_weight=24.0, throat_diameter=0.02, expansion_ratio=25.0,
        ambient_pressure=0.9999e5, n_stations=31).solve(include_bartz=False)


class TestP4B202BogulmamisLule:
    """Boğulmamış lülede performans/kayıp SAYISI yayımlanamaz."""

    def test_rejim_gercekten_unchoked(self):
        assert _unchoked_cozum()['regime']['type'] == 'unchoked'

    def test_hicbir_performans_sayisi_yayimlanmaz(self):
        perf = _unchoked_cozum()['performance']
        # Boğazda M < 1 iken alan-Mach bağıntısının süpersonik dalı geçersiz;
        # taban ölçümünde thrust_N = −727,44 N ve CF = −23,155 basılıyordu.
        for alan in ('thrust_N', 'CF', 'CF_ideal', 'mass_flow_kg_s',
                     'c_star_m_s', 'thrust_full_flow_N'):
            assert perf[alan] is None, f'{alan} boğulmamış lülede yayımlandı'
        assert perf['exit']['mach'] is None

    def test_kayip_dokumu_de_geri_cekilir(self):
        los = _unchoked_cozum()['losses']
        for alan in ('thrust_effective_N', 'CF_effective',
                     'momentum_thrust_N', 'pressure_thrust_N'):
            assert los[alan] is None, f'{alan} boğulmamış lülede yayımlandı'

    def test_geri_cekme_gerekcesi_adiyla_yayimlanir(self):
        sol = _unchoked_cozum()
        gerekce = sol.get('performance_withheld_because')
        assert isinstance(gerekce, str) and 'UNCHOKED' in gerekce
        # İstasyon dizileri kalır ama VARSAYIMSAL olduğu yazılıdır.
        assert sol['stations']['x_mm']
        assert 'HYPOTHETICAL' in (sol.get('stations_basis') or '')

    def test_geometrik_oran_geri_cekilmez(self):
        # eps = A_e/A_t saf geometridir, rejimden bağımsızdır.
        assert _unchoked_cozum()['performance']['expansion_ratio'] == \
            pytest.approx(25.0)

    def test_bogulmus_lule_sayilari_aynen_yayimlanir(self):
        """Regresyon kilidi: sağlıklı lülede hiçbir şey geri çekilmez."""
        sol = NozzleFlow1D(
            chamber_pressure=40e5, chamber_temperature=3200.0, gamma=1.2,
            molecular_weight=22.0, throat_diameter=0.05, expansion_ratio=8.0,
            ambient_pressure=101325.0, n_stations=31).solve(
                include_bartz=False)
        assert sol['performance']['thrust_N'] > 0
        assert sol['losses']['thrust_effective_N'] > 0
        assert 'performance_withheld_because' not in sol


# ============================================================ P4B1-04 / -05
MOTOR_ISI = {'chamber_pressure': 60.0, 'chamber_temperature': 3400.0,
             'chamber_diameter': 0.15, 'chamber_length': 0.4,
             'throat_diameter': 0.05, 'burn_time': 10.0, 'mdot_total': 8.0}


def _sogutma(cooling_type, **ek):
    md = dict(MOTOR_ISI)
    md.update(ek)
    res = HeatTransferAnalyzer().analyze_heat_transfer(
        md, material='copper', wall_thickness=0.003,
        cooling_type=cooling_type)
    return res['cooling_analysis']


class TestP4B104TekTasarimDeltaT:
    """Debi, YAYIMLANAN tasarım ΔT'siyle hesaplanmak zorunda."""

    def test_zorlanmis_dalda_debi_yayimlanan_delta_T_ile_tutarli(self):
        ca = _sogutma('forced')
        Q = ca['peak_heat_rate'] * 1000.0                 # kW -> W
        cp = ca['coolant_specific_heat_J_kgK']
        dT = ca['design_delta_T_K']
        assert cp is not None and dT is not None
        # Taban ölçümü: Q/mdot = 20 000 J/kg (cp 1000 × ΔT 20) iken
        # yayımlanan ΔT 100 K idi — beş kat tutarsızlık.
        assert Q / ca['coolant_flow_rate'] == pytest.approx(cp * dT, rel=1e-9)

    def test_debinin_kullandigi_delta_T_ayrica_yayimlanir(self):
        ca = _sogutma('forced')
        assert ca['coolant_delta_T_K'] == pytest.approx(ca['design_delta_T_K'])

    def test_rejeneratifte_cp_verilince_de_ayni_delta_T(self):
        ca = _sogutma('regenerative', coolant_specific_heat_J_kgK=2000.0)
        Q = ca['peak_heat_rate'] * 1000.0
        assert ca['coolant_flow_rate'] == pytest.approx(
            Q / (2000.0 * ca['design_delta_T_K']), rel=1e-9)


class TestP4B105SogutucuOzgulIsisi:
    """Soğutucunun cp'si bilinmiyorsa debi YAYIMLANMAZ (fail-closed)."""

    def test_cp_verilmeden_rejeneratif_debi_yayimlanmaz(self):
        ca = _sogutma('regenerative')
        # Taban ölçümü: SUYUN cp'siyle 10,15 kg/s — propelan debisinin
        # (8,0 kg/s) %126,9'u — künye alanı hiç yok.
        assert ca['coolant_flow_rate'] is None
        gerekce = ca.get('coolant_flow_rate_withheld_because')
        assert isinstance(gerekce, str)
        assert 'coolant_specific_heat_J_kgK' in gerekce
        assert '4180' in gerekce          # geri alınan varsayım adıyla anılır

    def test_su_cp_si_hicbir_dalda_varsayilmaz(self):
        for tip in ('regenerative', 'forced', 'natural'):
            cp = _sogutma(tip)['coolant_specific_heat_J_kgK']
            assert cp != 4180.0, f'{tip} dalında su cp si varsayıldı'

    def test_cp_ve_kaynak_kunyesi_yayimlanir(self):
        ca = _sogutma('forced')
        assert ca['coolant_specific_heat_J_kgK'] == pytest.approx(1005.0)
        assert 'Incropera' in (ca['coolant_specific_heat_source'] or '')
        assert ca['coolant_fluid'] == 'air'

    def test_verilen_cp_kunyesiyle_birlikte_kullanilir(self):
        ca = _sogutma('regenerative', coolant_specific_heat_J_kgK=2000.0)
        assert ca['coolant_specific_heat_J_kgK'] == pytest.approx(2000.0)
        assert ca['coolant_specific_heat_source'] == 'caller_supplied'
        assert ca['coolant_flow_rate'] is not None


# ===================================================================== P4B1-07
class TestP4B107RiskHukmuUcKatsayiyiGorur:

    @staticmethod
    def _dusuk_gerilme_sf():
        md = {'chamber_pressure': 2.0, 'chamber_temperature': 1200.0,
              'chamber_diameter': 0.3, 'throat_diameter': 0.2,
              'chamber_length': 0.4, 'burn_time': 10.0, 'mdot_total': 1.0}
        return HeatTransferAnalyzer().analyze_heat_transfer(
            md, material='ss_316', wall_thickness=0.005,
            cooling_type='regenerative')['safety_analysis']

    def test_vaka_gercekten_akmanin_ustunde(self):
        sa = self._dusuk_gerilme_sf()
        assert sa['stress_safety_factor'] < 1.0     # ölçüldü: 0,5506
        assert sa['temperature_safety_factor'] > 2.0  # ölçüldü: 2,0388

    def test_akma_ustunde_hukum_LOW_olamaz(self):
        # Kardeş modüldeki doğru desen: tests/test_scofield_kati.py:387
        assert self._dusuk_gerilme_sf()['risk_level'] not in ('LOW', 'VERY LOW')

    def test_hukmun_kaynagi_okunabilir(self):
        sa = self._dusuk_gerilme_sf()
        assert sa['risk_level_drivers']['stress_safety_factor'] == 'HIGH'
        assert 'stress_safety_factor' in sa['risk_level_governed_by']
        assert isinstance(sa.get('risk_level_basis'), str)

    def test_saglikli_katsayilarda_hukum_dokunulmaz(self):
        sa = HeatTransferAnalyzer().analyze_heat_transfer(
            dict(MOTOR_ISI), material='copper', wall_thickness=0.003,
            cooling_type='regenerative')['safety_analysis']
        # Taban ölçümü: üç katsayı da düşük -> HIGH (değişmemeli)
        assert sa['risk_level'] == 'HIGH'


# ===================================================================== P4B3-02
def _takla_cozumu():
    aero = BarrowmanAero(body_diameter=0.10, nose_length=0.30,
                         body_length=2.0, fin_count=4, fin_root_chord=0.15,
                         fin_tip_chord=0.075, fin_span=0.10, fin_sweep=0.05)
    return SixDOFTrajectory(
        aero=aero, dry_mass=20.0, propellant_mass=10.0, thrust=6000.0,
        burn_time=6.0, cd0=0.5, launch_elevation_deg=70.0, rail_length=2.0,
        wind_speed=30.0, wind_direction_deg=0.0, x_cg_full=1.95,
        x_cg_empty=1.95, latitude_deg=None, coriolis=False,
        roll_damping=0.0).solve(t_max=400.0)


class TestP4B302TaklaApojeDegildir:

    def test_vaka_gercekten_takla_ve_arac_tirmaniyor(self):
        r = _takla_cozumu()
        assert r['end_reason'] == 'tumble_detected'
        assert float(r['velocity'][2][-1]) > 50.0   # ölçüldü: +131,59 m/s

    def test_takla_dalinda_apoje_yayimlanmaz(self):
        r = _takla_cozumu()
        # Taban ölçümü: apogee = 449,205 m yayımlanıyordu.
        assert r['apogee'] is None
        assert r['apogee_time'] is None
        assert r['stable'] is None

    def test_tepe_degerleri_alt_sinir_diye_damgalanir(self):
        r = _takla_cozumu()
        assert r['peak_values_are_lower_bounds'] is True
        assert 'TUMBLE' in (r.get('apogee_withheld_because') or '')
        assert r['max_speed'] is not None      # ölçüm korunur, sınıflanır

    def test_saglikli_ucusta_apoje_yayimlanir(self):
        aero = BarrowmanAero(body_diameter=0.15, nose_length=0.4,
                             body_length=2.0, fin_count=4,
                             fin_root_chord=0.2, fin_tip_chord=0.1,
                             fin_span=0.12, fin_sweep=0.08)
        r = SixDOFTrajectory(aero=aero, dry_mass=20.0, propellant_mass=8.0,
                             thrust=3000.0, burn_time=5.0, cd0=0.5,
                             launch_elevation_deg=85.0,
                             rail_length=3.0).solve(t_max=400.0)
        assert r['end_reason'] == 'apogee'
        assert r['apogee'] is not None and r['apogee'] > 0
        assert 'peak_values_are_lower_bounds' not in r


# ============================================================ P4B3-03 / -05
def _yorunge(launch_altitude):
    an = TrajectoryAnalyzer()
    an.set_vehicle_parameters(mass_dry=20.0, diameter=0.10,
                              drag_coefficient=0.5)
    # ÖH D23 / P4B3-24: tutarsız 'isp' kaldırıldı (bekçi çevirisi). Yük
    # yanmayı iki kez ve iki farklı biçimde tarif ediyordu (impuls
    # bütçesinden türeyen Isp ile yazılı isp %1'den fazla ayrışıyor);
    # çözücü artık çelişkiyi reddediyor. Isp bir GİRDİ değil, bütçenin
    # türevidir ve anahtar yokken ondan türetilir — ölçülen sayılar
    # değişmez (once.json P4B3_24: isp 220/1/1e9 -> apoje BİT-AYNI).
    md = {'thrust': 3000.0, 'burn_time': 6.0, 'total_impulse': 18000.0,
          'propellant_mass_total': 8.0}
    lp = {'launch_angle': 88.0, 'launch_altitude': launch_altitude,
          'launch_rail_length': 5.0, 'parachute_area': 2.0,
          'parachute_cd': 1.4, 'parachute_deploy_delay': 2.0}
    return an, an.calculate_trajectory(md, lp)


def _izler(an, r):
    fig = an.create_trajectory_plots(r)
    if isinstance(fig, str):
        import json as _json
        fig = _json.loads(fig)
    if 'data' not in fig:
        ham = fig.get('trajectory_plot')
        import json as _json
        fig = _json.loads(ham) if isinstance(ham, str) else ham
    return {tr.get('name'): tr for tr in fig['data']}


class TestP4B303GrafikMetrikleAyniSayiyiCizer:

    def test_burnout_isaretcisi_metrikle_ayni(self):
        an, r = _yorunge(1500.0)
        izler = _izler(an, r)
        grafik_m = float(izler['Motor Burnout']['y'][0]) * 1000.0
        metrik_m = float(
            r['performance']['motor_performance']['burnout_altitude'])
        # Taban ölçümü: 4491,98 m (grafik) ⟷ 3348,64 m (metrik), +%34,1
        assert grafik_m == pytest.approx(metrik_m, abs=1e-6)

    def test_faz_apoje_ani_metrikle_ayni(self):
        an, r = _yorunge(1500.0)
        fp = _izler(an, r)['Flight Phases']
        metrik_s = float(r['performance']['phase_breakdown']['apogee_time'])
        # Taban ölçümü: grafik tam 2,0000 s (POWERED_PHASE_MARGIN_S) erkendi.
        assert float(fp['x'][2]) == pytest.approx(metrik_s, abs=1e-9)

    def test_kalkis_ve_inis_saha_kotunda_cizilir(self):
        an, r = _yorunge(1500.0)
        fp = _izler(an, r)['Flight Phases']
        # Taban ölçümü: [0.0, 4.417, 10.929, 0.0] km — 1500 m sahada araç
        # deniz seviyesinden kalkıp deniz seviyesine iniyor gibi çiziliyordu.
        assert float(fp['y'][0]) == pytest.approx(1.5, abs=1e-9)
        assert float(fp['y'][-1]) == pytest.approx(
            float(r['trajectory']['altitude'][-1]) / 1000.0, abs=1e-9)


class TestP4B305IrtifaVerimiSahaDatumu:

    def test_saha_kotunda_verim_sismez(self):
        _an, r = _yorunge(1500.0)
        mp = r['performance']['motor_performance']
        tm = r['performance']['trajectory_metrics']
        gercek = ((mp['burnout_altitude'] - 1500.0)
                  / (tm['max_altitude'] - 1500.0) * 100.0)
        # Taban ölçümü: yayımlanan %27,255 ⟷ gerçek %17,139 (1,59 kat).
        assert mp['altitude_efficiency'] == pytest.approx(gercek, rel=1e-9)

    def test_datum_kunyesi_yayimlanir(self):
        _an, r = _yorunge(1500.0)
        kunye = r['performance']['motor_performance'].get(
            'altitude_efficiency_basis')
        assert isinstance(kunye, str) and 'above the launch site' in kunye

    def test_deniz_seviyesinde_sayi_degismez(self):
        """Regresyon kilidi: datum 0 iken eski sayı birebir korunur."""
        _an, r = _yorunge(0.0)
        mp = r['performance']['motor_performance']
        tm = r['performance']['trajectory_metrics']
        assert mp['altitude_efficiency'] == pytest.approx(
            mp['burnout_altitude'] / tm['max_altitude'] * 100.0, rel=1e-12)


# ===================================================================== P4B3-06
TABAN_MOTOR = {'thrust': 3000, 'burn_time': 10, 'of_ratio': 6.0,
               'chamber_pressure': 20.0, 'fuel_type': 'htpb',
               'oxidizer_type': 'n2o'}
SAHA = {'elevation_m': 2000.0, 'latitude_deg': 38.0, 'longitude_deg': 35.0}


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _hesap(istemci, **ek):
    return istemci.post('/calculate',
                        json=dict(TABAN_MOTOR, **ek)).get_json()


class TestP4B306SahaYorungeyeDeGirer:

    def test_yorunge_blogu_sahayi_gorur(self, istemci):
        j = _hesap(istemci, launch_site=dict(SAHA))
        # Taban ölçümü: motor bloğu elevation_m = 2000 yayımlarken aynı
        # yanıtın yörünge bloğunda 'launch_site' anahtarı YOKTU.
        assert j['motor']['launch_site_performance']['elevation_m'] == \
            pytest.approx(2000.0)
        assert j['trajectory'].get('launch_site')

    def test_yerel_g_iki_blokta_ayni(self, istemci):
        sahasiz = _hesap(istemci)
        sahali = _hesap(istemci, launch_site=dict(SAHA))
        g0 = 9.80665
        tw0 = sahasiz['trajectory']['performance'][
            'motor_performance']['thrust_to_weight_ratio']
        tw1 = sahali['trajectory']['performance'][
            'motor_performance']['thrust_to_weight_ratio']
        g_yorunge = tw0 / tw1 * g0
        g_motor = sahali['motor']['launch_site_performance'][
            'gravity_local_m_s2']
        # Taban ölçümü: motor 9,793759 m/s² yayımlarken yörünge T/W'si
        # standart 9,80665 ile hesaplanıyordu.
        assert g_yorunge == pytest.approx(g_motor, abs=1e-6)
        assert not math.isclose(g_motor, g0, abs_tol=1e-6)

    def test_sahasiz_kosu_standart_g0_ile_kurulur(self, istemci):
        """Regresyon kilidi: saha gönderilmezse yörünge T/W'si standart g0 ile
        kurulur — kendi yanıtından türetilir.

        ÖH D15 birleştirme (ana model, 1 Eyl 2026): eski hâli T/W = 3,94873…
        MUTLAK çıpasıydı; hibrit kulvarı (a1 P1B3-03 LOX entalpisi, a2/a3)
        motor fiziğini değiştirince 3,52851 oldu ve çıpa yalancı kırmızıya
        düştü. İddia aynı — 'sahasız koşuda yerel g DEĞİL g0 kullanılır' —
        ama artık yanıtın kendi itki ve yüklü kütlesinden ölçülür.
        """
        j = _hesap(istemci)
        assert j['trajectory'].get('launch_site') in (None, {})
        g0 = 9.80665
        tw = j['trajectory']['performance']['motor_performance'][
            'thrust_to_weight_ratio']
        itki = float(j['motor']['thrust'])
        kutle = float(j['trajectory']['vehicle_parameters']['mass_loaded'])
        assert tw == pytest.approx(itki / (kutle * g0), rel=1e-9)
