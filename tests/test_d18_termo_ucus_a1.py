"""ÖH D18 / termo-ucus a1 — onarım bekçileri.

Kapsanan defter kalemleri:
  * OH-D15-08 (Fable-D16 ŞART): ``normalize_thrust_curve`` negatif zaman
    kapısı + ṁ(t) ∝ F(t) doktrininin sayısal kilidi.
  * P4B3-16: atış koşullarının sessizce varsayılana düşmesi (fail-closed).
  * P4B3-17: ``launch_site`` beyan çelişkisi (modellenen ⟷ modellenmeyen).
  * P4B3-18: ``resolve_launch_site`` kütüphane düzeyinde sessiz kırpma.
  * P4B3-21: apojenin datumu (deniz seviyesi ⟷ saha üstü).
  * P4B3-22: itkinin irtifa telafisi + beyanı.
  * P4B4-09: çalışma basıncının referans düzlemi (mutlak ⟷ gösterge).
  * P4B4-10: iki debi girdisi, tek hüküm.
  * P4B3-12: 6-DOF dürüstlük alanlarının ÇÜRÜTÜLEN ayakları (kilit).

Her bekçi ters-mutasyonla kırmızıya çevrilmiştir; kanıt
``docs/scofield/raw/OH/D18/termo-ucus/a1/mutasyon.json``.
"""
import contextlib
import io
import pathlib

import numpy as np
import pytest

from hrma.analysis import launch_site as ls
from hrma.analysis.launch_site import (
    LaunchSiteInputError, resolve_launch_site)
from hrma.analysis.trajectory_analysis import (
    TrajectoryAnalyzer, TrajectoryInputError, normalize_thrust_curve)
from hrma.analysis.water_hammer import (
    FLOW_INPUT_REL_TOL, WaterHammerAnalyzer)

# --------------------------------------------------------------------- #
# Ortak fikstürler                                                       #
# --------------------------------------------------------------------- #

#: ÖH D16'dan devralınan eğri: tepe/ortalama = 3,0, toplam impuls 32.000 N·s.
EGRI_T = [0.0, 1.0, 2.0, 4.0, 8.0]
EGRI_F = [12000.0, 12000.0, 4000.0, 2000.0, 1000.0]
EGRI = {'time': EGRI_T, 'thrust': EGRI_F}
EGRI_IMPULS = 32000.0
EGRI_ORTALAMA = EGRI_IMPULS / EGRI_T[-1]

ARAC = {'initial_mass': 50.0, 'final_mass': 35.0, 'drag_coefficient': 0.5,
        'reference_area': 0.01, 'thrust': 4000.0, 'burn_time': 8.0}

SU_HATTI = dict(fluid='water', line_length_m=10.0, line_id_mm=25.4,
                wall_thickness_mm=1.65, working_pressure_bar=10.0,
                pipe_material='ss_304', valve_closure_time_ms=100.0)


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(client, yol, yuk):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return client.post(yol, json=yuk)


# ===================================================================== #
# OH-D15-08 — ŞART (1): negatif zaman kapısı, motor_file ile TEK SÖZLEŞME #
# ===================================================================== #

class TestOHD1508NegatifZamanKapisi:
    """ÖLÇÜLDÜ (``once.json`` K1, taban 9071a64): ``normalize_thrust_curve``
    ``{'time': [-0.1, 0.0, 1.0], 'thrust': [0, 100, 100]}`` eğrisini KABUL
    ediyordu; toplam impuls 105,0 N·s çıkıyordu, t >= 0 diliminkinin (100,0)
    %5,0 üstünde. Kardeş RASP/RSE içe aktarıcısı aynı ihlali
    ``negative_time`` adıyla ZATEN reddediyordu."""

    BOZUK = {'time': [-0.1, 0.0, 1.0], 'thrust': [0.0, 100.0, 100.0]}

    def test_normalize_negatif_zamani_reddeder(self):
        with pytest.raises(TrajectoryInputError) as exc:
            normalize_thrust_curve(self.BOZUK)
        sorunlar = exc.value.problems
        assert [p['field'] for p in sorunlar] == ['thrust_curve']
        assert [p['reason'] for p in sorunlar] == ['negative_time']

    def test_gerekce_adi_motor_file_ile_ayni(self):
        """TEK SÖZLEŞME: iki kanal aynı adı kullanır (ŞART maddesi 1)."""
        kaynak = (pathlib.Path(ls.__file__).resolve().parents[1]
                  / 'importers' / 'motor_file.py').read_text(encoding='utf-8')
        assert "'negative_time'" in kaynak, (
            'kardeş içe aktarıcının negatif zaman kapısı kalkmış; iki kanal '
            'artık aynı adı konuşmuyor')

    def test_uc_422_ile_alan_adiyla_reddeder(self, client):
        r = _post(client, '/api/trajectory-analysis',
                  {k: v for k, v in ARAC.items()
                   if k not in ('thrust', 'burn_time')}
                  | {'thrust_curve': self.BOZUK})
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert j['invalid_fields'][0]['field'] == 'thrust_curve'
        assert j['invalid_fields'][0]['reason'] == 'negative_time'

    def test_saglikli_egri_etkilenmez(self):
        t, F, imp = normalize_thrust_curve(EGRI)
        assert imp == pytest.approx(EGRI_IMPULS, rel=1e-12)
        assert float(t[0]) == 0.0


# ===================================================================== #
# OH-D15-08 — ŞART (2): ṁ(t) ∝ F(t) doktrininin SAYISAL kilidi            #
# ===================================================================== #

class TestOHD1508DebiItkiyleOrantili:
    """ŞART METNİ: ``EGRI`` ile ``_calculate_powered_flight`` çıktısında
    t ≈ 2,0 s kütlesi 40,625 kg olmalı (abs 1e-2). Sabit debi 46,25 verir.

    El hesabı: ∫₀² F dt = 12.000·1 + (12.000+4.000)/2·1 = 20.000 N·s;
    tüketilen yakıt = 15 kg · 20.000/32.000 = 9,375 kg; kütle = 50 − 9,375.
    Sabit debi ise 15/8 · 2 = 3,75 kg tüketir -> 46,25 kg.
    """

    KUTLE_T2_EGRI = 40.625
    KUTLE_T2_SABIT = 46.25

    @staticmethod
    def _pf(egri_var):
        a = TrajectoryAnalyzer()
        a.set_vehicle_parameters(mass_dry=35.0, diameter=0.1128,
                                 drag_coefficient=0.5)
        if egri_var:
            a.set_thrust_curve(EGRI)
        with contextlib.redirect_stdout(io.StringIO()):
            return a._calculate_powered_flight(
                EGRI_ORTALAMA, 8.0, 50.0, 15.0, np.radians(85.0), 0.0,
                0.01, (0.0, 0.0),
                thrust_curve=a._thrust_curve if egri_var else None)

    def test_egri_yolunda_t2_kutlesi_egriden_gelir(self):
        pf = self._pf(True)
        m2 = float(np.interp(2.0, pf['time'], pf['mass']))
        assert m2 == pytest.approx(self.KUTLE_T2_EGRI, abs=1e-2), (
            f't = 2,0 s kütlesi {m2:.6f} kg; eğri yolunda '
            f'{self.KUTLE_T2_EGRI} kg olmalı. Sabit debi '
            f'{self.KUTLE_T2_SABIT} kg verir — ṁ(t) ∝ F(t) doktrini '
            f'sökülmüş görünüyor')

    def test_sabit_debi_yolu_ayrisir_ve_degismez(self):
        """Regresyon kilidi: eğri YOKSA eski dikdörtgen davranış aynen."""
        pf = self._pf(False)
        m2 = float(np.interp(2.0, pf['time'], pf['mass']))
        assert m2 == pytest.approx(self.KUTLE_T2_SABIT, abs=1e-2)
        assert abs(self.KUTLE_T2_SABIT - self.KUTLE_T2_EGRI) > 5.0, (
            'iki yol arasındaki fark bu bekçinin ayrım gücüdür')

    def test_kutle_butcesi_kapanir(self):
        pf = self._pf(True)
        assert float(pf['mass'][-1]) == pytest.approx(35.0, abs=1e-4)


# ===================================================================== #
# P4B3-16 — atış koşulu sessizce varsayılana DÜŞMEZ                      #
# ===================================================================== #

class TestP4B316AtisKosuluBantKapisi:
    """ÖLÇÜLDÜ (çapa + ``once.json`` K3, taban 9071a64): üç gövde de
    BİT-AYNI idi (tek uyarı yok):
      launch_angle = -88   -> sha 04c370c1… (açısız istekle aynı)
      wind_direction = -90 -> sha 9048eca5… (yönsüz istekle aynı)
      launch_latitude = -33,9 -> sha 04c370c1… (enlemsiz istekle aynı)
    """

    @pytest.mark.parametrize('alan,deger', [
        ('launch_angle', -88.0),
        ('launch_angle', 400.0),
        ('wind_direction', -90.0),
        ('wind_direction', 361.0),
        ('wind_speed', -3.0),
        ('launch_latitude', 200.0),
        ('launch_longitude', 5000.0),
    ])
    def test_bant_disi_deger_422_ile_adiyla_reddedilir(self, client, alan,
                                                       deger):
        r = _post(client, '/api/trajectory-analysis', dict(ARAC, **{alan: deger}))
        assert r.status_code == 422, (
            f'{alan}={deger} HTTP {r.status_code} ile geçti — sessizce '
            f'varsayılana düşmüş olabilir')
        j = r.get_json()
        assert j['error'] == 'invalid_launch_conditions'
        adlar = [f['field'] for f in j['invalid_fields']]
        assert alan in adlar, adlar
        kayit = next(f for f in j['invalid_fields'] if f['field'] == alan)
        assert kayit['reason'] == 'out_of_range'
        assert kayit['value'] == deger
        assert 'accepted_range' in kayit

    def test_guney_yarikure_sahasi_artik_DUSMUYOR(self, client):
        """Negatif enlem MEŞRUDUR: düşürülmez, yerel g'ye girer."""
        guney = _post(client, '/api/trajectory-analysis',
                      dict(ARAC, launch_latitude=-33.9))
        enlemsiz = _post(client, '/api/trajectory-analysis', dict(ARAC))
        assert guney.status_code == 200, guney.get_data(as_text=True)[:200]
        assert guney.get_data() != enlemsiz.get_data(), (
            'güney yarıküre enlemi gövdeyi hiç değiştirmiyor — sessizce '
            'düşürülüyor demektir (taban davranışı)')

    def test_meşru_bant_ici_degerler_gecer(self, client):
        r = _post(client, '/api/trajectory-analysis',
                  dict(ARAC, launch_angle=80.0, wind_speed=4.0,
                       wind_direction=270.0, launch_latitude=28.5,
                       launch_longitude=-80.6))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]


# ===================================================================== #
# P4B3-17 — beyanın İKİ tarafı da adlandırılmış                          #
# ===================================================================== #

class TestP4B317BeyanCeliskisi:
    """ÖLÇÜLDÜ (``once.json`` K4): ``NOT_MODELLED['earth_rotation']`` metni
    "Coriolis acceleration (2*Omega x v) IS integrated" diyordu ve bu metin
    ``/api/launch-site/resolve`` yanıtında ``not_modelled`` başlığı altında
    yayımlanıyordu."""

    def test_modellenmeyenler_listesinde_MODELLENEN_yok(self):
        for anahtar, metin in ls.NOT_MODELLED.items():
            assert 'IS integrated' not in metin, (
                f"not_modelled['{anahtar}'] metni bir şeyin MODELLENDİĞİNİ "
                f'söylüyor: {metin[:120]}')
            assert ' IS modelled' not in metin.replace(
                'and IS modelled - see the "modelled" block', ''), anahtar

    def test_eski_yaniltici_anahtar_geri_gelmedi(self):
        assert 'earth_rotation' not in ls.NOT_MODELLED
        assert 'earth_rotation_transport_velocity' in ls.NOT_MODELLED

    def test_modellenen_taraf_da_yayimlaniyor(self, client):
        r = _post(client, '/api/launch-site/resolve',
                  {'latitude': 39.9, 'longitude': 32.85})
        assert r.status_code == 200
        saha = r.get_json()['site']
        assert 'earth_rotation_coriolis' in saha['modelled']
        assert 'earth_rotation' not in saha['not_modelled']

    def test_modellenen_beyan_SARTINI_da_soyluyor(self):
        metin = ls.CORIOLIS_MODELLING['earth_rotation_coriolis']
        assert 'only when a launch latitude is supplied' in metin, (
            'Coriolis enlemsiz çağrıda KAPANIYOR; beyan bunu söylemezse '
            '"modelleniyor" ifadesi yine yanıltıcıdır')
        assert 'coriolis_disabled_no_latitude' in metin

    def test_modul_belgesi_koda_uyuyor(self):
        belge = ls.__doc__ or ''
        assert 'düz-Dünya atalet çerçevesinde çalışır' not in belge
        assert 'CORIOLIS_MODELLING' in belge


# ===================================================================== #
# P4B3-18 — kütüphane düzeyinde KIRPMA YOK                               #
# ===================================================================== #

class TestP4B318KutuphaneKirpmasi:
    """ÖLÇÜLDÜ (``once.json`` K5): ``resolve_launch_site(200.0, 5000.0)``
    istisna atmadan lat 90,0 / lon −40,0 ve g = 9,832184937859008 ile TAM
    bir saha döndürüyordu; kırpmayı söyleyen tek alan yoktu. Uç katmanı
    (D15/P7B1-08) bandı kapatmıştı ama kapı YALNIZ UÇTAYDI."""

    @pytest.mark.parametrize('lat', [200.0, -91.0, 90.001])
    def test_bant_disi_enlem_reddedilir(self, lat):
        with pytest.raises(LaunchSiteInputError) as exc:
            resolve_launch_site(lat, 32.85)
        p = exc.value.problems[0]
        assert p['field'] == 'latitude_deg'
        assert p['reason'] == 'out_of_range'
        assert p['accepted_range'] == [-90.0, 90.0]

    def test_hata_ValueError_turevidir(self):
        assert issubclass(LaunchSiteInputError, ValueError)

    def test_bant_ici_enlem_calisir(self):
        s = resolve_launch_site(-33.9, 18.4)
        assert s['latitude_deg'] == pytest.approx(-33.9, rel=1e-12)

    def test_boylam_sarmasi_BEYAN_ediliyor(self):
        s = resolve_launch_site(39.9, 5000.0)
        assert s['longitude_deg'] == pytest.approx(
            ls.normalize_longitude(5000.0), rel=1e-12)
        assert any('wrapped' in w for w in s['warnings']), s['warnings']

    def test_sarma_yoksa_uyari_da_yok(self):
        s = resolve_launch_site(39.9, 32.85)
        assert not any('wrapped' in w for w in s['warnings'])

    def test_uc_hukmu_degismedi(self, client):
        r = _post(client, '/api/launch-site/resolve',
                  {'latitude': 200.0, 'longitude': 5000.0})
        assert r.status_code == 400
        assert r.get_json()['field'] == 'latitude'


# ===================================================================== #
# P4B3-21 — apojenin DATUMU adıyla                                       #
# ===================================================================== #

class TestP4B321ApojeDatumu:
    """ÖLÇÜLDÜ (``once.json`` K6): iki modül de datumunu söylemiyordu;
    2B ``max_altitude`` deniz seviyesinden, 6-DOF ``apogee`` saha üstünden.
    """

    def test_2b_datumunu_soyluyor_ve_saha_ustunu_de_veriyor(self, client):
        r = _post(client, '/api/trajectory-analysis',
                  dict(ARAC, trajectory_start_altitude=1500.0))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        m = r.get_json()['trajectory_data']['performance']['trajectory_metrics']
        assert m['max_altitude_datum'] == 'mean_sea_level'
        assert m['launch_site_elevation_m'] == pytest.approx(1500.0)
        assert m['max_altitude_above_launch_site_m'] == pytest.approx(
            m['max_altitude'] - 1500.0, rel=1e-12)
        assert m['max_altitude'] > 1500.0

    def test_6dof_datumunu_soyluyor(self):
        from hrma.analysis.six_dof_trajectory import SixDOFTrajectory
        from tests.test_d17_termo_ucus_a1 import _aero
        s = SixDOFTrajectory(aero=_aero(), dry_mass=20.0,
                             propellant_mass=10.0, thrust=3000.0,
                             burn_time=4.0, latitude_deg=39.9,
                             launch_altitude=1500.0)
        with contextlib.redirect_stdout(io.StringIO()):
            res = s.solve(t_max=120.0)
        assert res['apogee_datum'] == 'above_launch_site'
        assert res['launch_site_elevation_m'] == pytest.approx(1500.0)
        assert res['apogee_msl_m'] == pytest.approx(
            res['apogee'] + 1500.0, rel=1e-12)


# ===================================================================== #
# P4B3-22 — itkinin irtifa telafisi                                      #
# ===================================================================== #

class TestP4B322IrtifaTelafisi:
    """ÖLÇÜLDÜ (``once.json`` K7): 2B yörüngenin uyarı kodları arasında
    irtifa telafisine dair TEK bir şey yoktu ve sonuç sözlüğünde varsayımı
    söyleyen alan da yoktu; kardeş 6-DOF ise aynı varsayımı her koşumda
    ``warn.sixdof.thrust_not_altitude_compensated`` ile söylüyordu."""

    KOD = 'warn.trajectory.thrust_not_altitude_compensated'

    def test_A_e_yokken_BEYAN_var(self, client):
        td = _post(client, '/api/trajectory-analysis',
                   dict(ARAC)).get_json()['trajectory_data']
        assert self.KOD in [u['code'] for u in td['warnings']]
        blok = td['thrust_altitude_compensation']
        assert blok['modelled'] is False
        assert blok['nozzle_exit_area_m2'] is None
        assert 'NOT_MODELLED' in blok['basis']

    def test_A_e_verilince_telafi_KOSAR_ve_itki_degisir(self):
        """Vakumda F(h) − F_ref = P_ref·A_e; apoje ölçülebilir biçimde artar."""
        def _kos(ae):
            a = TrajectoryAnalyzer()
            a.set_vehicle_parameters(mass_dry=35.0, diameter=0.1128,
                                     drag_coefficient=0.5)
            if ae is not None:
                a.set_nozzle_exit(ae)
            md = {'thrust': 4000.0, 'burn_time': 8.0,
                  # ÖH D23 / P4B3-24 — tutarsız 'isp' kaldırıldı (bekçi çevirisi): yük
                  # yanmayı iki kez ve iki farklı biçimde tarif ediyordu; çözücü artık
                  # çelişkiyi reddediyor. Isp bir GİRDİ değil, entegre edilen impuls
                  # bütçesinin türevidir ve anahtar yokken ondan türetilir — bu bekçinin
                  # ölçtüğü sayıların hiçbiri değişmez (ölçüldü: isp 220/1/1e9 -> apoje
                  # BİT-AYNI, once.json P4B3_24).
                  'total_impulse': 32000.0,
                  'propellant_mass_total': 15.0}
            with contextlib.redirect_stdout(io.StringIO()):
                r = a.calculate_trajectory(md, {'initial_mass': 50.0,
                                                'final_mass': 35.0,
                                                'launch_angle': 85.0})
            return r, a
        yok, a0 = _kos(None)
        var, a1 = _kos(0.02)
        assert a1.nozzle_exit_area == pytest.approx(0.02)
        assert self.KOD not in [u['code'] for u in var['warnings']]
        assert var['thrust_altitude_compensation']['modelled'] is True
        h0 = yok['performance']['trajectory_metrics']['max_altitude']
        h1 = var['performance']['trajectory_metrics']['max_altitude']
        assert h1 > h0, (
            f'telafi açıkken apoje {h1:.3f} m, kapalıyken {h0:.3f} m; '
            f'irtifayla artan itki apojeyi YÜKSELTMELİ')

    def test_A_e_verilmezse_davranis_BIT_AYNI(self):
        """Regresyon kilidi: telafi kapalıyken sayı kıpırdamaz."""
        a = TrajectoryAnalyzer()
        a.set_vehicle_parameters(mass_dry=35.0, diameter=0.1128,
                                 drag_coefficient=0.5)
        assert a.nozzle_exit_area is None
        assert a.thrust_reference_pressure is None


# ===================================================================== #
# P4B4-09 — çalışma basıncının REFERANS DÜZLEMİ                          #
# ===================================================================== #

class TestP4B409ReferansDuzlemi:
    """ÖLÇÜLDÜ (``once.json`` K8): yanıtta ``reference`` içeren tek alan
    yoktu, ama modül aynı sayıyı iki ZIT sözleşmeyle kullanıyordu.
    Ayrışma penceresi TAM 1 atm genişliğindedir (ölçüldü: ss_304 hattında
    184,25–185,25 bar arası ret, dışı hüküm)."""

    def test_hukum_duzleme_bagli_degilse_yayimlanir_ve_beyan_edilir(self):
        r = WaterHammerAnalyzer().analyze(mdot_kg_s=0.5, **SU_HATTI)
        ref = r['working_pressure_reference']
        assert ref['supplied'] is None
        assert ref['verdict_depends_on_reference'] is False
        assert set(ref['verdict_by_reading']) == {'absolute', 'gauge'}
        hukumler = {(h['status'], h['column_separation'])
                    for h in ref['verdict_by_reading'].values()}
        assert len(hukumler) == 1
        assert ref['ambient_pressure_Pa'] == pytest.approx(101325.0)

    def test_hukum_duzleme_BAGLIYSA_yayimlanmaz(self):
        """1 atm'lik yorum farkı hükmü çeviriyorsa sayı seçilmez."""
        with pytest.raises(ValueError) as exc:
            WaterHammerAnalyzer().analyze(
                mdot_kg_s=0.5,
                **dict(SU_HATTI, working_pressure_bar=185.0))
        m = str(exc.value)
        assert 'working_pressure_reference' in m
        assert 'ABSOLUTE' in m and 'GAUGE' in m

    @pytest.mark.parametrize('pw,bekleme', [(184.0, 'gecer'),
                                            (184.25, 'red'),
                                            (185.25, 'red'),
                                            (185.5, 'gecer')])
    def test_ayrisma_penceresi_bir_atmosfer_genisliginde(self, pw, bekleme):
        cagri = dict(SU_HATTI, working_pressure_bar=pw)
        if bekleme == 'red':
            with pytest.raises(ValueError):
                WaterHammerAnalyzer().analyze(mdot_kg_s=0.5, **cagri)
        else:
            assert WaterHammerAnalyzer().analyze(
                mdot_kg_s=0.5, **cagri)['status']

    def test_duzlem_verilirse_iki_karsilastirma_da_TUTARLI(self):
        for okuma in ('absolute', 'gauge'):
            r = WaterHammerAnalyzer().analyze(
                mdot_kg_s=0.5,
                **dict(SU_HATTI, working_pressure_bar=185.0,
                       working_pressure_reference=okuma))
            ref = r['working_pressure_reference']
            assert ref['supplied'] == okuma
            # ÖH D24 / termo-ucus a2 (P4B4-09, Fable-D18 ŞART) — BEKÇİ
            # ÇEVRİLDİ. Eski satır ``assert list(ref['verdict_by_reading'])
            # == [okuma]`` idi ve KUSURU KORUYORDU: düzlem verildiğinde
            # yalnız o okuma değerlendiriliyor, künye ise
            # ``verdict_depends_on_reference: False`` (kod sabiti) basıyordu
            # — 185 bar ayrışma penceresinin İÇİNDE olmasına rağmen
            # (ölçüldü: 'absolute' -> SAFE, 'gauge' -> MARGINAL). Artık iki
            # okuma da HER ÇAĞRIDA yayımlanır ve bayrak hesaplanır.
            assert set(ref['verdict_by_reading']) == {'absolute', 'gauge'}
            assert r['status'] == ref['verdict_by_reading'][okuma]['status']
            assert ref['verdict_depends_on_reference'] is True

    def test_gecersiz_duzlem_adi_reddedilir(self):
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(
                mdot_kg_s=0.5,
                **dict(SU_HATTI, working_pressure_reference='msl'))


# ===================================================================== #
# P4B4-10 — iki debi girdisi, TEK hüküm                                  #
# ===================================================================== #

class TestP4B410IkiDebiTekHukum:
    """ÖLÇÜLDÜ (``once.json`` K8): ``mdot_kg_s=0,5`` + ``flow_velocity_m_s=
    0,979784`` birlikte gönderildiğinde ``inputs`` bloğu ikisini de
    yankılıyor, hangisinin çözüme girdiğini söyleyen alan yoktu."""

    def test_otorite_adiyla_yayimlaniyor(self):
        a = WaterHammerAnalyzer().analyze(mdot_kg_s=0.5, **SU_HATTI)
        assert a['flow_source'] == 'mdot_kg_s'
        assert a['flow_cross_check'] is None
        b = WaterHammerAnalyzer().analyze(flow_velocity_m_s=1.0, **SU_HATTI)
        assert b['flow_source'] == 'flow_velocity_m_s'

    def test_uyusan_iki_girdi_capraz_kontrolle_gecer(self):
        rho = 998.2
        alan = np.pi * (0.0254 ** 2) / 4.0
        v = 0.5 / (rho * alan)
        r = WaterHammerAnalyzer().analyze(mdot_kg_s=0.5,
                                          flow_velocity_m_s=v, **SU_HATTI)
        cc = r['flow_cross_check']
        assert cc['relative_disagreement'] < FLOW_INPUT_REL_TOL
        assert cc['accepted_relative_disagreement'] == FLOW_INPUT_REL_TOL
        assert r['flow_source'] == 'flow_velocity_m_s'

    def test_celisen_iki_girdi_REDDEDILIR(self):
        with pytest.raises(ValueError) as exc:
            WaterHammerAnalyzer().analyze(mdot_kg_s=0.5,
                                          flow_velocity_m_s=2.0, **SU_HATTI)
        m = str(exc.value)
        assert 'mdot_kg_s' in m and 'flow_velocity_m_s' in m
        assert 'described twice' in m

    def test_girdi_kunyesi_ISTENEN_malzemeyi_yankiliyor(self):
        """P4B4-10'un ikinci ayağı ÖLÇÜMLE geçersiz: künye zaten doğru."""
        r = WaterHammerAnalyzer().analyze(
            mdot_kg_s=0.5, **dict(SU_HATTI, pipe_material='bulunmayan'))
        assert r['inputs']['pipe_material'] == 'bulunmayan'
        assert r['inputs']['pipe_material_submitted'] == 'bulunmayan'
        assert r['inputs']['pipe_material_used'] == 'ss_304'


# ===================================================================== #
# P4B3-12 — ÇÜRÜTÜLEN ayakların kilidi                                   #
# ===================================================================== #

class TestP4B312DurustlukAlanlariZatenYayimlaniyor:
    """Kalem "hiçbir dürüstlük alanı yanıta konmuyor" diyordu; ölçüm
    (``once.json`` / çapa C1) tersini gösteriyor. Bu bekçi ÇÜRÜTMEYİ
    kilitler: alanlar geri düşerse kırmızı olur."""

    SIXDOF_D18 = {'dry_mass': 35.0, 'propellant_mass': 15.0, 'thrust': 4000.0,
              'burn_time': 8.0, 'body_diameter': 0.1128, 'body_length': 2.0,
              'launch_elevation_deg': 85.0, 'latitude_deg': 39.9,
              'rail_length': 5.0}

    def test_uyarilar_ve_cozucu_kunyesi_yanitta(self, client):
        g = _post(client, '/api/six-dof-analysis', self.SIXDOF_D18).get_json()
        assert g['summary'].get('warnings'), 'çözücü uyarıları düşüyor'
        assert g['stability_basis']['solver_converged'] is True
        assert g['stability_basis']['solver_message'] is not None
        assert 'lifted_off' in g['summary']

    def test_kesilen_kosumda_tepe_ALT_SINIR_oldugu_soyleniyor(self, client):
        g = _post(client, '/api/six-dof-analysis',
                  dict(self.SIXDOF_D18, t_max=3.0)).get_json()
        ozet = g['summary']
        assert ozet.get('peak_values_are_lower_bounds') is True, (
            'ufuk kesilmiş koşumda max_speed bir TEPE gibi okunuyor')
        assert ozet.get('t_max_s') == pytest.approx(3.0)

    def test_ray_boyu_ikamesi_BEYAN_ediliyor(self, client):
        g = _post(client, '/api/six-dof-analysis',
                  {k: v for k, v in self.SIXDOF_D18.items()
                   if k != 'rail_length'}).get_json()
        ikame = g['stability_basis']['input_defaults_substituted']
        assert 'rail_length' in ikame
        assert ikame['rail_length'] == 5.0
