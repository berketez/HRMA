"""ÖH Dalga-24 / termo-ucus aşama-2 bekçileri.

Kalemler:
  * P4B3-16  (ŞART, Fable-D18) — atış koşulu bantları TEK kaynak, iki uç
  * P4B3-22  (ŞART, Fable-D18) — itkinin irtifa telafisi ÜRÜN YOLUNDA
  * P4B4-09  (ŞART, Fable-D18) — su koçu ``verdict_depends_on_reference``
  * P4B3-12  (ŞART, Fable-D18) — çözücünün kullandığı ray boyu yanıtta
  * OH-D23-07 — 0 m altı iki ISA okuması, TEK kaynak
  * OH-Z5-02  — ``wind_model`` uydurma sabit yaprağı
  * P4B3-23   — 6-DOF ölü kod kümesi (üç ayağın bugünkü hâli)

Her bekçi ters-mutasyonla kırmızıya çevrildi:
``docs/scofield/raw/OH/D24/termo-ucus/a2/mutasyon.json``.
"""
import ast
import contextlib
import io
import os

import numpy as np
import pytest

from hrma.analysis.trajectory_analysis import (
    ISA_SEA_LEVEL_SPEED_OF_SOUND,
    LAUNCH_CONDITION_BANDS,
    LAUNCH_PARAM_BAND_KEYS,
    TrajectoryAnalyzer,
    TrajectoryInputError,
)
from hrma.analysis.water_hammer import WaterHammerAnalyzer
from hrma.constants import (
    ISA_LAYERS,
    ISA_TABLE_BOTTOM_M,
    ISA_TABLE_TOP_M,
    isa_pressure,
    isa_temperature,
)

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Fable-D18'in P4B4-09 ölçümünde kullandığı hat (tests/test_d18_termo_ucus_a1)
SU_HATTI = dict(fluid='water', line_length_m=10.0, line_id_mm=25.4,
                wall_thickness_mm=1.65, working_pressure_bar=10.0,
                pipe_material='ss_304', valve_closure_time_ms=100.0)

#: 2B yörünge ucunun tam aracı (eksik-araç kapısını geçer)
ARAC_2B = {
    'thrust': 3000.0, 'burn_time': 4.0, 'total_impulse': 12000.0,
    'initial_mass': 28.0, 'final_mass': 20.0,
    'drag_coefficient': 0.5, 'reference_area': 0.0176715,
}

#: 6-DOF ucunun aynı gövdesi
ARAC_6DOF = {
    'body_diameter': 0.15, 'body_length': 2.5, 'nose_length': 0.45,
    'dry_mass': 20.0, 'propellant_mass': 8.0, 'thrust': 3000.0,
    'burn_time': 4.0, 'cd0': 0.5, 'fin_count': 4,
    'fin_root_chord': 0.30, 'fin_tip_chord': 0.15, 'fin_span': 0.15,
    'fin_sweep': 0.10,
}


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


# ===================================================================== #
# OH-D23-07 — 0 m ALTI: TEK ISA OKUMASI                                  #
# ===================================================================== #
class TestOHD2307TekISAOkumasi:
    """ÖLÇÜLDÜ (a2/once.json K1, taban 88a29d3): ``_atm_full`` 0 m altını
    0'a kırpıyordu — ``_atm_full(-400) == _atm_full(-500) == _atm_full(0)``
    = 101325,0 Pa iken ``constants.isa_pressure(-400)`` = 106223,74 Pa;
    aynı irtifanın iki ISA okuması −400 m'de %4,61, −5000 m'de %43,0
    ayrışıyordu."""

    @pytest.mark.parametrize('h', [-5000.0, -430.0, -400.0, -154.0, -1.0,
                                   0.0, 1.0, 1000.0, 11000.0, 47000.0,
                                   84000.0])
    def test_iki_ISA_okumasi_AYNI_sayiyi_veriyor(self, h):
        ta = TrajectoryAnalyzer()
        _rho, P, T, _a = ta._atm_full(h)
        H = h * ta.R_geopotential / (ta.R_geopotential + h)
        assert P == pytest.approx(isa_pressure(H), rel=1e-12), (
            'aynı irtifada iki farklı basınç: _atm_full ile '
            'constants.isa_pressure ayrıştı')
        assert T == pytest.approx(isa_temperature(H), rel=1e-12)

    def test_deniz_alti_saha_deniz_seviyesinden_FARKLI(self):
        """Ölüdeniz (−430 m) havası deniz seviyesi havası DEĞİLDİR."""
        ta = TrajectoryAnalyzer()
        p_m430 = ta._atm_full(-430.0)[1]
        p_0 = ta._atm_full(0.0)[1]
        p_m500 = ta._atm_full(-500.0)[1]
        assert p_m430 > p_0, 'deniz altında basınç daha yüksek olmalı'
        assert p_m430 != p_m500, 'iki farklı irtifa aynı sayıyı veriyor'
        # Kalemin kendi cümlesinin TERSİ:
        assert not (ta._atm_full(-400.0) == ta._atm_full(-500.0)
                    == ta._atm_full(0.0))

    def test_tablo_tabani_TEK_SABIT_ve_banda_bagli(self):
        assert ISA_TABLE_BOTTOM_M == -5000.0
        assert LAUNCH_CONDITION_BANDS['altitude'][0] == ISA_TABLE_BOTTOM_M
        assert LAUNCH_CONDITION_BANDS['altitude'][1] == ISA_TABLE_TOP_M

    def test_tablo_altindaki_SAHA_reddedilir_fail_closed(self):
        ta = TrajectoryAnalyzer()
        ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                                  drag_coefficient=0.5)
        md = {'thrust': 3000.0, 'burn_time': 4.0,
              'propellant_mass_total': 8.0, 'isp': 220.0}
        with pytest.raises(TrajectoryInputError) as exc:
            _sessiz(ta.calculate_trajectory, md,
                    {'launch_altitude': -6000.0, 'launch_angle': 85.0})
        alanlar = [p.get('field') for p in (exc.value.problems or [])]
        assert 'launch_params.launch_altitude' in alanlar

    def test_tablo_ici_deniz_alti_sahasi_KABUL_edilir(self):
        ta = TrajectoryAnalyzer()
        ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                                  drag_coefficient=0.5)
        md = {'thrust': 3000.0, 'burn_time': 4.0,
              'propellant_mass_total': 8.0, 'total_impulse': 12000.0,
              'isp': 152.9051987767584}
        r = _sessiz(ta.calculate_trajectory, md,
                    {'launch_altitude': -430.0, 'launch_angle': 85.0})
        assert r['performance']['trajectory_metrics']['max_altitude'] > 0


# ===================================================================== #
# P4B3-16 — ATIŞ KOŞULU BANTLARI TEK KAYNAK, İKİ UÇ AYNI HÜKÜM           #
# ===================================================================== #
class TestP4B316BantTekKaynak:
    """ÖLÇÜLDÜ (a2/once.json K2, taban 88a29d3): bant tablosu
    ``hrma/app.py`` içinde ``_LP_BANTLAR`` adıyla YEREL yazılıydı; kardeş
    6-DOF ucu kendi ``ranges=``ını ayrıca yazıyor, kütüphane hiç bant
    görmüyordu. Aynı gövde iki uca gönderildiğinde ``wind_speed = 400``,
    ``wind_direction = 400`` ve ``launch_altitude = 90000`` 6-DOF'ta HTTP
    200, 2B'de 422 alıyordu."""

    def test_tablo_tek_yerde_ve_app_py_kendi_tablosunu_yazmiyor(self):
        with open(os.path.join(KOK, 'hrma', 'app.py'), encoding='utf-8') as f:
            metin = f.read()
        assert '_LP_BANTLAR = {' not in metin, (
            'app.py yeniden kendi bant tablosunu yazmış (ikinci tanım)')
        assert 'LAUNCH_CONDITION_BANDS' in metin

    def test_bandin_her_ucunun_dayanagi_YAZILI(self):
        for ad, kayit in LAUNCH_CONDITION_BANDS.items():
            alt, ust, birim, dayanak = kayit
            assert alt < ust, ad
            assert isinstance(birim, str) and birim, ad
            assert isinstance(dayanak, str) and len(dayanak) > 20, (
                '%s bandının dayanağı yazılı değil' % ad)

    def test_ruzgar_ust_ucu_TURETILIR_yazilmaz(self):
        """150 m/s'nin dayanağı yoktu; yenisi ISA ses hızıdır."""
        beklenen = float(np.sqrt(1.4 * (8.31432 / 0.0289644)
                                 * ISA_LAYERS[0][1]))
        assert ISA_SEA_LEVEL_SPEED_OF_SOUND == pytest.approx(beklenen,
                                                             rel=1e-9)
        assert LAUNCH_CONDITION_BANDS['wind_speed'][1] == \
            ISA_SEA_LEVEL_SPEED_OF_SOUND
        assert LAUNCH_CONDITION_BANDS['wind_speed'][1] != 150.0

    @pytest.mark.parametrize('ad2b,ad6d,deger', [
        ('launch_angle', 'launch_elevation_deg', -88.0),
        ('launch_angle', 'launch_elevation_deg', 120.0),
        ('wind_speed', 'wind_speed', 400.0),
        ('wind_direction', 'wind_direction_deg', 400.0),
        ('launch_latitude', 'latitude_deg', 120.0),
        ('trajectory_start_altitude', 'launch_altitude', 90000.0),
        ('trajectory_start_altitude', 'launch_altitude', -6000.0),
    ])
    def test_iki_uc_AYNI_govdeye_AYNI_hukmu_veriyor(self, client, ad2b,
                                                    ad6d, deger):
        r2 = _sessiz(client.post, '/api/trajectory-analysis',
                     json=dict(ARAC_2B, **{ad2b: deger}))
        r6 = _sessiz(client.post, '/api/six-dof-analysis',
                     json=dict(ARAC_6DOF, **{ad6d: deger}))
        assert r2.status_code == 422, (ad2b, deger, r2.status_code)
        assert r6.status_code == 422, (ad6d, deger, r6.status_code)

    @pytest.mark.parametrize('ad2b,ad6d,deger', [
        ('launch_angle', 'launch_elevation_deg', 45.0),
        ('wind_speed', 'wind_speed', 12.0),
        ('launch_latitude', 'latitude_deg', -33.9),
        ('trajectory_start_altitude', 'launch_altitude', -430.0),
    ])
    def test_bant_ICI_deger_iki_ucta_da_gecer(self, client, ad2b, ad6d,
                                              deger):
        r2 = _sessiz(client.post, '/api/trajectory-analysis',
                     json=dict(ARAC_2B, **{ad2b: deger}))
        r6 = _sessiz(client.post, '/api/six-dof-analysis',
                     json=dict(ARAC_6DOF, **{ad6d: deger}))
        assert r2.status_code == 200, (ad2b, deger,
                                       r2.get_data(as_text=True)[:200])
        assert r6.status_code == 200, (ad6d, deger,
                                       r6.get_data(as_text=True)[:200])

    def test_bant_disi_yanit_DAYANAGI_da_soyluyor(self, client):
        r = _sessiz(client.post, '/api/trajectory-analysis',
                    json=dict(ARAC_2B, wind_speed=400.0))
        j = r.get_json()
        assert j['error'] == 'invalid_launch_conditions'
        alan = j['invalid_fields'][0]
        assert alan['field'] == 'wind_speed'
        assert alan['accepted_range'][1] == ISA_SEA_LEVEL_SPEED_OF_SOUND
        assert 'band_basis' in alan and 'speed of sound' in alan['band_basis']

    def test_cozucu_KENDISI_de_bandi_uyguluyor(self):
        """/calculate kütüphaneyi doğrudan çağırır; kapı orada da var."""
        ta = TrajectoryAnalyzer()
        ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                                  drag_coefficient=0.5)
        md = {'thrust': 3000.0, 'burn_time': 4.0,
              'propellant_mass_total': 8.0, 'isp': 220.0}
        with pytest.raises(TrajectoryInputError) as exc:
            _sessiz(ta.calculate_trajectory, md, {'launch_angle': -88.0})
        alanlar = [p.get('field') for p in (exc.value.problems or [])]
        assert 'launch_params.launch_angle' in alanlar
        assert set(LAUNCH_PARAM_BAND_KEYS.values()) <= set(
            LAUNCH_CONDITION_BANDS)


# ===================================================================== #
# P4B3-22 — İTKİNİN İRTİFA TELAFİSİ ÜRÜN YOLUNDA                          #
# ===================================================================== #
class TestP4B322IrtifaTelafisiUrunYolunda:
    """ÖLÇÜLDÜ (a2/once.json K3, taban 88a29d3): ``hrma/app.py`` içinde
    ``nozzle_exit_area`` dizgisi SIFIR kez geçiyordu; uca alan gönderilse
    bile yanıt ``thrust_altitude_compensation.modelled = False`` basıyordu.
    """

    def test_uc_alani_OKUYOR_ve_telafiyi_modelliyor(self, client):
        r = _sessiz(client.post, '/api/trajectory-analysis',
                    json=dict(ARAC_2B, nozzle_exit_area=0.01,
                              thrust_reference_pressure=101325.0))
        assert r.status_code == 200
        tac = r.get_json()['trajectory_data'][
            'thrust_altitude_compensation']
        assert tac['modelled'] is True
        assert tac['nozzle_exit_area_m2'] == pytest.approx(0.01)
        assert tac['reference_pressure_pa'] == pytest.approx(101325.0)

    def test_alan_verilmezse_fail_closed_BEYAN_surer(self, client):
        r = _sessiz(client.post, '/api/trajectory-analysis', json=ARAC_2B)
        tac = r.get_json()['trajectory_data'][
            'thrust_altitude_compensation']
        assert tac['modelled'] is False
        assert tac['nozzle_exit_area_m2'] is None
        assert 'NOT_MODELLED' in tac['basis']

    def test_telafi_apojeyi_YUKSELTIYOR_isaret_dogru(self, client):
        """P_amb irtifayla düştüğü için ek impuls POZİTİF olmalı."""
        def _apoje(**ek):
            r = _sessiz(client.post, '/api/trajectory-analysis',
                        json=dict(ARAC_2B, **ek))
            return (r.get_json()['trajectory_data']['performance']
                    ['trajectory_metrics']['max_altitude'])
        yok = _apoje()
        var = _apoje(nozzle_exit_area=0.01,
                     thrust_reference_pressure=101325.0)
        assert var > yok, (yok, var)

    @pytest.mark.parametrize('alan,deger', [
        ('nozzle_exit_area', -0.01),
        ('nozzle_exit_area', 0.0),
        ('thrust_reference_pressure', -1.0),
        ('thrust_reference_pressure', 1e9),
    ])
    def test_gecersiz_telafi_girdisi_ADIYLA_reddedilir(self, client, alan,
                                                       deger):
        r = _sessiz(client.post, '/api/trajectory-analysis',
                    json=dict(ARAC_2B, **{alan: deger}))
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'invalid_thrust_altitude_compensation_input'
        assert [a['field'] for a in j['invalid_fields']] == [alan]

    def test_calculate_zinciri_motorun_cikis_alanini_TASIYOR(self, client):
        """Hibrit /calculate: motor bloğu A_e yayımlıyor, yörünge kullanıyor."""
        r = _sessiz(client.post, '/calculate', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o'})
        assert r.status_code == 200
        j = r.get_json()
        ae = j['motor']['exit_area']
        assert ae > 0.0
        tac = j['trajectory']['thrust_altitude_compensation']
        assert tac['modelled'] is True, 'ürün yolu telafiyi taşımıyor'
        assert tac['nozzle_exit_area_m2'] == pytest.approx(ae, rel=1e-12), (
            'yörünge motorunkinden BAŞKA bir çıkış alanı kullanıyor')
        assert tac['reference_pressure_pa'] > 0.0


# ===================================================================== #
# P4B4-09 — SU KOÇU: BAYRAK HESAPLANIR                                    #
# ===================================================================== #
class TestP4B409BayrakHesaplanir:
    """Fable-D18 ŞART. ÖLÇÜLDÜ (a2/once.json K4): düzlem verildiğinde
    ``verdict_by_reading`` TEK anahtarlı kalıyor ve
    ``verdict_depends_on_reference`` kod sabiti ``False`` yayımlanıyordu —
    185 bar ayrışma penceresinin içindeyken bile."""

    def test_185bar_absolute_bayrak_TRUE_ve_iki_anahtar(self):
        r = WaterHammerAnalyzer().analyze(
            mdot_kg_s=0.5,
            **dict(SU_HATTI, working_pressure_bar=185.0,
                   working_pressure_reference='absolute'))
        ref = r['working_pressure_reference']
        assert ref['verdict_depends_on_reference'] is True
        assert set(ref['verdict_by_reading']) == {'absolute', 'gauge'}
        assert r['status'] == ref['verdict_by_reading']['absolute']['status']

    def test_185bar_iki_duzlem_GERCEKTEN_ayrisiyor(self):
        hukumler = {}
        for okuma in ('absolute', 'gauge'):
            r = WaterHammerAnalyzer().analyze(
                mdot_kg_s=0.5,
                **dict(SU_HATTI, working_pressure_bar=185.0,
                       working_pressure_reference=okuma))
            hukumler[okuma] = r['status']
        assert hukumler['absolute'] != hukumler['gauge'], hukumler

    def test_10bar_gauge_bayrak_FALSE(self):
        r = WaterHammerAnalyzer().analyze(
            mdot_kg_s=0.5,
            **dict(SU_HATTI, working_pressure_reference='gauge'))
        ref = r['working_pressure_reference']
        assert ref['verdict_depends_on_reference'] is False
        assert set(ref['verdict_by_reading']) == {'absolute', 'gauge'}

    def test_duzlemsiz_ayrisma_hala_FAIL_CLOSED(self):
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(
                mdot_kg_s=0.5,
                **dict(SU_HATTI, working_pressure_bar=185.0))

    def test_kunye_blogunun_cocuk_sayisi_DEGISMEDI(self):
        """test_wave4b_contract SAGIR_ALT_BLOKLAR sayısı (6) korunur."""
        r = WaterHammerAnalyzer().analyze(mdot_kg_s=0.5, **SU_HATTI)
        assert len(r['working_pressure_reference']) == 6


# ===================================================================== #
# P4B3-12 — ÇÖZÜCÜNÜN KULLANDIĞI RAY BOYU YANITTA                        #
# ===================================================================== #
class TestP4B312RayBoyu:
    """Fable-D18 ŞART. ÖLÇÜLDÜ (a2/once.json K5, taban 88a29d3): D23'ün
    P4B3-29 onarımı ray boyunu ``summary.rail_length_m`` +
    ``summary.rail_length_source`` olarak zaten yayımlıyor ve
    ``sixdof_panel.js`` İKİSİNİ DE okuyor. ŞART'ın önerdiği
    ``stability_basis.rail_length_m_used`` adı AYNI SAYININ ikinci adı
    olurdu (doktrin-4 ihlali); bu bekçi ŞART'ın SORUSUNU sorar."""

    def test_verilen_ray_boyu_yanitta_OKUNUR(self, client):
        r = _sessiz(client.post, '/api/six-dof-analysis',
                    json=dict(ARAC_6DOF, rail_length=7.5))
        oz = r.get_json()['summary']
        assert oz['rail_length_m'] == pytest.approx(7.5)
        assert oz['rail_length_source'] == 'supplied'

    def test_verilmeyen_ray_boyu_VARSAYILAN_diye_isaretlenir(self, client):
        r = _sessiz(client.post, '/api/six-dof-analysis', json=ARAC_6DOF)
        oz = r.get_json()['summary']
        assert oz['rail_length_source'] == 'default'
        assert oz['rail_length_m'] > 0.0

    def test_sayi_TEK_ADLA_yayimlaniyor(self, client):
        r = _sessiz(client.post, '/api/six-dof-analysis',
                    json=dict(ARAC_6DOF, rail_length=7.5))
        j = r.get_json()
        assert 'rail_length_m_used' not in (j.get('stability_basis') or {}), (
            'aynı sayı ikinci bir adla da yayımlanmış (doktrin-4)')

    def test_panel_iki_alani_da_BAGLI(self):
        yol = os.path.join(KOK, 'hrma', 'static', 'js', 'sixdof_panel.js')
        with open(yol, encoding='utf-8') as f:
            metin = f.read()
        assert 'rail_length_m' in metin
        assert 'rail_length_source' in metin

    def test_durustluk_alanlari_ozette(self, client):
        r = _sessiz(client.post, '/api/six-dof-analysis',
                    json=dict(ARAC_6DOF, t_max=3.0))
        oz = r.get_json()['summary']
        assert oz.get('peak_values_are_lower_bounds') is True
        assert oz.get('t_max_s') == pytest.approx(3.0)
        sb = r.get_json()['stability_basis']
        assert 'solver_converged' in sb and 'solver_message' in sb


# ===================================================================== #
# OH-Z5-02 — UYDURMA SABİT YAPRAK (termo yaprağı)                        #
# ===================================================================== #
class TestOHZ502RuzgarYapragi:
    """ÖLÇÜLDÜ (a2/once.json K6, taban 88a29d3): beş (hız, yön) çiftinde
    ``trajectory.wind_model.vertical_component_m_s`` HEP 0,0 — çünkü
    ``_wind_vector`` düşey bileşeni hesaplamaz, YATAY RÜZGÂR KABULÜNÜ
    uygular. Sayı bir ölçümün sonucu değildi."""

    def test_uydurma_sayi_YOK_kabul_YAYIMLANIYOR(self):
        for v, yon in ((0.0, 0.0), (12.0, 90.0), (30.0, 210.0)):
            w = TrajectoryAnalyzer._wind_components(v, np.radians(yon))
            assert 'vertical_component_m_s' not in w
            assert w['vertical_component_modelled'] is False

    def test_kunye_eksikligi_ADIYLA_soyluyor(self):
        w = TrajectoryAnalyzer._wind_components(12.0, 0.0)
        assert 'vertical_component_modelled' in w['basis'] or \
            'VERTICAL' in w['basis']

    def test_urun_yanitinda_da_yok(self, client):
        r = _sessiz(client.post, '/api/trajectory-analysis',
                    json=dict(ARAC_2B, wind_speed=12.0,
                              wind_direction=90.0))
        wm = r.get_json()['trajectory_data']['wind_model']
        assert 'vertical_component_m_s' not in wm
        assert wm['vertical_component_modelled'] is False

    def test_YASAYAN_kardes_yaprak_hala_CANLI(self):
        """Çapraz bileşen bir ÖLÇÜMDÜR; onu susturmadık."""
        a = TrajectoryAnalyzer._wind_components(12.0, np.radians(90.0))
        b = TrajectoryAnalyzer._wind_components(12.0, np.radians(0.0))
        assert a['cross_plane_component_m_s'] != \
            b['cross_plane_component_m_s']


# ===================================================================== #
# P4B3-23 — 6-DOF ÖLÜ KOD KÜMESİ (üç ayak)                               #
# ===================================================================== #
class TestP4B323OluKodKumesi:
    """Kalemin üç ayağı: ``at_mach`` (a1'de bağlandı), ``_mdot_at``
    (D23'te bağlandı), ``_alpha_deg_series`` (D23'te ölçümle çürütüldü —
    ürün yolunda ``alpha_deg`` serisi zaten yayımlanıyor)."""

    @staticmethod
    def _turev_adlari():
        yol = os.path.join(KOK, 'hrma', 'analysis', 'six_dof_trajectory.py')
        with open(yol, encoding='utf-8') as f:
            agac = ast.parse(f.read())
        adlar = set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.FunctionDef) and \
                    dugum.name == '_derivatives':
                for alt in ast.walk(dugum):
                    if isinstance(alt, ast.Attribute):
                        adlar.add(alt.attr)
                    elif isinstance(alt, ast.Name):
                        adlar.add(alt.id)
        return adlar

    def test_at_mach_dinamige_BAGLI(self):
        assert 'at_mach' in self._turev_adlari(), (
            'süpersonik kararlılık hükmü yine M->0 Barrowman ile veriliyor')

    def test_jet_sonumu_dinamige_BAGLI(self):
        assert '_mdot_at' in self._turev_adlari()

    def test_alpha_serisi_URUN_yolunda(self, client):
        r = _sessiz(client.post, '/api/six-dof-analysis', json=ARAC_6DOF)
        seri = r.get_json()['series']['alpha_deg']
        assert len(seri) > 10
        assert max(seri) > 0.0
