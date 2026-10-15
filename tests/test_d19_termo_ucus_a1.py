# -*- coding: utf-8 -*-
"""ÖH Dalga-19 / termo-ucus a1 bekçileri.

Kapsanan kalemler
-----------------
* **P4B3-18 (kalan iki ayak)** — ``launch_site`` kütüphanesinin YEREL
  YERÇEKİMİ yardımcıları bant dışı enlemi sessizce kırpıyordu ve
  ``resolve_launch_site`` kullanıcının verdiği ``elevation_m``i hiç
  sınamıyordu.
* **P4B3-21 (kalan iki ayak)** — 6-DOF ucunun sabit anahtar listesi apoje
  DATUMUNU gövdeden düşürüyordu; küre görselleştirmesi "deniz seviyesi"
  deyip saha rakımını düşey eksende atıyordu.
* **P4B4-11** — ana iddia (adaptör motorun yoğunluğunu iletmiyor) ölçümle
  ÇÜRÜTÜLDÜ; çürütme burada kilitlenir, künye ayağı ayrıca sınanır.
* **P4B4-10 / P4B4-09 / P4B3-16 / P4B3-17 / P4B3-22** — D18 onarımlarının
  bu tabanda hâlâ durduğunun devir denetimi.
* **OH-D16-17** — KAPALI çapa kaydının (boğaz ışıma bacağı) sayısal
  kilidi; kayıt bir daha sessizce bayatlamasın.

Ölçüm kanıtı: ``docs/scofield/raw/OH/D19/termo-ucus/a1/once.json`` ve
``sonra.json``; ters mutasyonlar ``mutasyon.json``.
"""
import contextlib
import io
import math

import pytest

from hrma.analysis import launch_site as ls
from hrma.analysis.launch_site import (
    GRAVITY_ALTITUDE_RANGE_M,
    LATITUDE_RANGE_DEG,
    LaunchSiteInputError,
    SITE_ELEVATION_RANGE_M,
    earth_rotation_speed,
    local_gravity,
    normal_gravity,
    resolve_launch_site,
)


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


# ===========================================================================
# P4B3-18 — SESSİZ KIRPMA YERİNE RET (kütüphane yardımcıları)
# ===========================================================================
class TestP4B318EnlemKirpmasiYardimcilarda:
    """``local_gravity(200, 0)`` 9,832184937859008 döndürüyordu.

    ÖLÇÜLDÜ (taban 60cd341, once.json K18): üç yardımcı da istisna
    ATMADAN kutup/ekvator değerini veriyordu —
    ``normal_gravity(200) = 9.832184937859008``,
    ``earth_rotation_speed(200) = 2.857503442515346e-14`` (yani cos 90°).
    D18 yalnız ``resolve_launch_site``ı kapatmıştı; kütüphaneyi doğrudan
    çağıran yollar (6-DOF ``g_surface``, düzlemsel yörünge, hibrit motorun
    saha bandı) sessiz kırpmayı görmeye devam ediyordu.
    """

    @pytest.mark.parametrize('fn', [normal_gravity, earth_rotation_speed])
    @pytest.mark.parametrize('lat', [200.0, -200.0, 90.001, -90.001])
    def test_bant_disi_enlem_reddedilir(self, fn, lat):
        with pytest.raises(LaunchSiteInputError) as exc:
            fn(lat)
        p = exc.value.problems[0]
        assert p['field'] == 'latitude_deg'
        assert p['reason'] == 'out_of_range'
        assert p['value'] == pytest.approx(lat)
        assert p['accepted_range'] == list(LATITUDE_RANGE_DEG)

    @pytest.mark.parametrize('lat', [200.0, -200.0])
    def test_local_gravity_bant_disi_enlemi_reddeder(self, lat):
        with pytest.raises(LaunchSiteInputError) as exc:
            local_gravity(lat, 0.0)
        assert exc.value.problems[0]['field'] == 'latitude_deg'

    def test_kirpilan_deger_artik_uretilmiyor(self):
        """Kırpmanın ürettiği TAM sayı hiçbir yoldan gelmemeli."""
        kutup = normal_gravity(90.0)
        assert kutup == pytest.approx(9.832184937859008, rel=1e-12)
        for cagri in (lambda: normal_gravity(200.0),
                      lambda: local_gravity(200.0, 0.0),
                      lambda: local_gravity(-200.0, 0.0)):
            with pytest.raises(LaunchSiteInputError):
                cagri()

    def test_bant_ici_enlem_degismedi(self):
        """Regresyon kilidi: meşru enlemlerde sayı AYNI."""
        assert normal_gravity(0.0) == pytest.approx(9.7803253359, abs=1e-6)
        assert normal_gravity(90.0) == pytest.approx(9.8321849378, abs=1e-6)
        assert local_gravity(45.0, 1500.0) == pytest.approx(
            9.801571073012182, rel=1e-12)


class TestP4B318RakimBandi:
    """``local_gravity(45, 1e9)`` = 720.083,96 m/s² üretiyordu.

    Serbest-hava açılımı (NIMA TR8350.2 Denk. 4-3) h/a'da KESİLMİŞ bir
    seridir: karesel terim 84.852 m'de birimin 5,4e-7'si kadarken 1e9
    m'de 73.700 KATIDIR. Bant açılımın kendi geçerlilik bandıdır.
    """

    def test_rakim_bandi_disi_reddedilir(self):
        with pytest.raises(LaunchSiteInputError) as exc:
            local_gravity(45.0, 1.0e9)
        p = exc.value.problems[0]
        assert p['field'] == 'altitude_m'
        assert p['reason'] == 'out_of_range'
        assert p['accepted_range'] == list(GRAVITY_ALTITUDE_RANGE_M)

    def test_bandin_ustu_ISA_tablo_tavani(self):
        from hrma.constants import ISA_TABLE_TOP_M
        assert GRAVITY_ALTITUDE_RANGE_M[1] == pytest.approx(ISA_TABLE_TOP_M)
        assert GRAVITY_ALTITUDE_RANGE_M[0] == pytest.approx(
            SITE_ELEVATION_RANGE_M[0])

    def test_bant_ici_rakim_calisiyor(self):
        g0 = local_gravity(45.0, 0.0)
        g1000 = local_gravity(45.0, 1000.0)
        # serbest-hava gradyanı ≈ −3.086e-6 m/s² per metre
        assert (g0 - g1000) / 1000.0 == pytest.approx(3.086e-6, rel=0.05)


class TestP4B318RakimTekKaynak:
    """Saha rakım bandı İKİ YERDE yazılmaz (CLAUDE.md kural 11)."""

    def test_hibrit_motor_ayni_bandi_ice_aktariyor(self):
        from hrma.engines.hybrid_rocket_engine import (
            LAUNCH_SITE_ELEVATION_RANGE_M)
        assert LAUNCH_SITE_ELEVATION_RANGE_M is SITE_ELEVATION_RANGE_M

    @pytest.mark.parametrize('rakim', [1.0e9, -1.0e6, 9000.001, -500.001])
    def test_resolve_bant_disi_rakimi_reddeder(self, rakim):
        with pytest.raises(LaunchSiteInputError) as exc:
            resolve_launch_site(39.9, 32.85, elevation_m=rakim,
                                use_online=False)
        p = exc.value.problems[0]
        assert p['field'] == 'elevation_m'
        assert p['reason'] == 'out_of_range'
        assert p['accepted_range'] == list(SITE_ELEVATION_RANGE_M)

    def test_bant_ici_rakim_aynen_kullaniliyor(self):
        site = resolve_launch_site(39.9, 32.85, elevation_m=1500.0,
                                   use_online=False)
        assert site['elevation_m'] == pytest.approx(1500.0)
        assert math.isfinite(site['gravity_local_m_s2'])
        assert 9.7 < site['gravity_local_m_s2'] < 9.9


class TestP4B318UcKatmani:
    """Uç, kütüphane reddini enlem kapısıyla AYNI gövde biçiminde yayımlar."""

    def test_rakim_bant_disi_400_ve_alan_adiyla(self, client):
        r = client.post('/api/launch-site/resolve',
                        json={'latitude': 39.9, 'longitude': 32.85,
                              'elevation_m': 1.0e9})
        assert r.status_code == 400
        j = r.get_json()
        assert j['error'] == 'invalid_launch_site_input'
        assert j['field'] == 'elevation_m'
        assert j['reason'] == 'out_of_range'
        assert j['accepted_range'] == list(SITE_ELEVATION_RANGE_M)
        assert j['unit'] == 'm'
        # Sayı UYDURULMADI: yanıtta çözülmüş saha yok.
        assert 'site' not in j

    def test_negatif_buyuk_rakim_da_reddediliyor(self, client):
        r = client.post('/api/launch-site/resolve',
                        json={'latitude': 39.9, 'longitude': 32.85,
                              'elevation_m': -1.0e6})
        assert r.status_code == 400
        assert r.get_json()['field'] == 'elevation_m'

    def test_saglikli_saha_200_kaliyor(self, client):
        r = client.post('/api/launch-site/resolve',
                        json={'latitude': 39.9, 'longitude': 32.85,
                              'elevation_m': 1500.0})
        assert r.status_code == 200
        assert r.get_json()['site']['elevation_m'] == pytest.approx(1500.0)


# ===========================================================================
# P4B3-21 — APOJENİN DATUMU UÇTA VE PANELDE
# ===========================================================================
SIXDOF_GOVDE = {
    'dry_mass': 35.0, 'propellant_mass': 15.0, 'thrust': 4000.0,
    'burn_time': 8.0, 'diameter': 0.1128, 'length': 2.0,
    'launch_elevation_deg': 85.0, 'launch_azimuth_deg': 0.0,
    'latitude_deg': 39.9, 'launch_rail_length_m': 5.0,
}


class TestP4B321ApojeDatumuUcta:
    """Çözücü datumu yayımlıyordu, uç onu düşürüyordu.

    ÖLÇÜLDÜ (once.json K21, taban 60cd341):
    ``summary_datum_alanlari = []`` — ``apogee_datum``,
    ``launch_site_elevation_m`` ve ``apogee_msl_m`` uç özetine hiç
    çıkmıyordu, dolayısıyla 6-DOF paneli apojeyi SAHA ÜSTÜ, kardeş 2B
    paneli DENİZ SEVİYESİNDEN gösterip ikisi de datumunu söylemiyordu.
    """

    def test_ozet_datumu_adiyla_tasiyor(self, client):
        r = client.post('/api/six-dof-analysis',
                        json=dict(SIXDOF_GOVDE, launch_altitude=1500.0))
        assert r.status_code == 200
        s = r.get_json()['summary']
        assert s['apogee_datum'] == 'above_launch_site'
        assert s['launch_site_elevation_m'] == pytest.approx(1500.0)

    def test_iki_okuma_birbirine_donusuyor(self, client):
        r = client.post('/api/six-dof-analysis',
                        json=dict(SIXDOF_GOVDE, launch_altitude=1500.0))
        s = r.get_json()['summary']
        if s.get('apogee') is None:            # kesilen koşum: hüküm yok
            pytest.skip('apoje bu koşumda kazanılmadı')
        assert s['apogee_msl_m'] == pytest.approx(
            s['apogee'] + s['launch_site_elevation_m'], rel=1e-12)

    def test_deniz_seviyesindeki_sahada_iki_okuma_ayni(self, client):
        r = client.post('/api/six-dof-analysis', json=dict(SIXDOF_GOVDE))
        s = r.get_json()['summary']
        assert s['launch_site_elevation_m'] == pytest.approx(0.0)
        if s.get('apogee') is not None:
            assert s['apogee_msl_m'] == pytest.approx(s['apogee'])


class TestP4B321PanelDatumuOkuyor:
    """Uca alan eklemek, paneli bağlamadan borç envanterini büyütür."""

    def test_sixdof_paneli_uc_alani_da_okuyor(self):
        src = open('hrma/static/js/sixdof_panel.js', encoding='utf-8').read()
        for ad in ('apogee_datum', 'launch_site_elevation_m', 'apogee_msl_m'):
            assert ad in src, ad

    def test_kure_ucus_yolu_saha_rakimini_dusurmuyor(self):
        """``alt[i] = series.altitude[i]`` h0'ı düşey eksende ATIYORDU."""
        src = open('hrma/static/js/launch_site_globe.js',
                   encoding='utf-8').read()
        assert 'alt[i] = g.alt;' in src
        assert 'alt[i] = series.altitude[i];' not in src
        # ÖH D22 / OH-D18-10 — BEKÇİ ÇEVRİLDİ (kusuru korumuyordu; düz dize
        # arıyordu). Datum sözcükleri artık dosyada TEK tanım: ALT_DATUM_MSL /
        # ALT_DATUM_AGL. Bekçinin iddiası aynen duruyor — çizilen yolun datumu
        # deniz seviyesi olarak ADLANDIRILMIŞ olmalı — ama adı sabitten okur,
        # böylece tek kaynak kuralı ile çakışmaz.
        assert "var ALT_DATUM_MSL = 'mean_sea_level';" in src
        assert 'altDatum: ALT_DATUM_MSL,' in src

    def test_ikinci_apoje_rozeti_ceviri_kanalindan_geciyor(self):
        """ÖH D25 — Fable-D19 ŞARTI (P4B3-21) + OH-D24-15.

        İkinci apoje rozeti ('SITE … m ASL -> APOGEE … km MSL') TF()/i18n
        anahtarsız İngilizce sabit dizeydi: kardeş rozet (badgeApogee)
        çeviriden geçerken bu satır TR kullanıcıya İngilizce sızıyordu ve
        i18n süpürme bekçileri deseni göremiyordu. Anahtar EN ve TR
        sözlüklerin İÇİNDE olmalı; düz dize dosyada KALMAMALI.
        """
        src = open('hrma/static/js/sixdof_panel.js', encoding='utf-8').read()
        assert "badge('SITE '" not in src
        assert 'sixdof.badgeApogeeMsl' in src
        i18n = open('hrma/static/js/i18n_common.js', encoding='utf-8').read()
        # EN + TR: iki sözlükte de tanımlı (tek tanım i18n borcudur).
        assert i18n.count("'sixdof.badgeApogeeMsl':") == 2, (
            i18n.count("'sixdof.badgeApogeeMsl':"))


# ===========================================================================
# P4B4-11 — ÇÜRÜTME KİLİDİ + YOĞUNLUK KÜNYESİ
# ===========================================================================
class TestP4B411YogunlukIletimi:
    """Kalem "adaptör motorun yoğunluğunu HİÇ iletmiyor" diyordu.

    ÖLÇÜLDÜ (once.json K11, taban 60cd341): iletiyor. RP-1 hattında tablo
    yoğunluğu 810 kg/m³ iken caller 820 verdiğinde çözücü 820'yi kullanıyor
    ve Joukowsky artışı 47,46675811961261 -> 47,75886400354484 bar oluyor.
    Bu bekçi çürütmeyi KİLİTLER: iletim düşerse kırmızı olur.
    """

    ORTAK = dict(fluid='rp1', line_length_m=6.0, line_id_mm=50.0,
                 wall_thickness_mm=2.0, working_pressure_bar=60.0,
                 pipe_material='ss_304', valve_closure_time_ms=50.0,
                 working_pressure_reference='gauge')

    def _kos(self, **ek):
        from hrma.analysis.water_hammer import WaterHammerAnalyzer
        return WaterHammerAnalyzer().analyze(flow_velocity_m_s=5.0,
                                             **dict(self.ORTAK, **ek))

    def test_caller_yogunlugu_cozume_giriyor(self):
        from hrma.analysis.water_hammer import FLUID_PROPERTIES
        tablo = float(FLUID_PROPERTIES['rp1']['density_kg_m3'])
        yok = self._kos()
        var = self._kos(density_kg_m3=820.0)
        assert yok['fluid_properties']['density_kg_m3'] == pytest.approx(tablo)
        assert var['fluid_properties']['density_kg_m3'] == pytest.approx(820.0)
        # dP = rho*a*dv: yoğunluk çözüme girdiği için tepe DEĞİŞMEK ZORUNDA
        assert (var['joukowsky_pressure_rise_bar']
                != pytest.approx(yok['joukowsky_pressure_rise_bar'],
                                 rel=1e-9))
        assert var['joukowsky_pressure_rise_bar'] > \
            yok['joukowsky_pressure_rise_bar']

    def test_kunye_gonderileni_ve_kullanilani_ayri_soyluyor(self):
        var = self._kos(density_kg_m3=820.0)
        inp = var['inputs']
        assert inp['density_kg_m3_submitted'] == pytest.approx(820.0)
        assert inp['density_kg_m3_used'] == pytest.approx(820.0)
        assert inp['density_source'] == 'caller_override'

    def test_gonderilmediginde_kaynak_tabloyu_soyluyor(self):
        yok = self._kos()
        inp = yok['inputs']
        assert inp['density_kg_m3_submitted'] is None
        assert inp['density_source'] == 'fluid_table'
        assert inp['density_kg_m3_used'] == pytest.approx(
            yok['fluid_properties']['density_kg_m3'])

    def test_adapter_hat_yogunlugunu_gecirir(self):
        from hrma.analysis.valve_feedline import water_hammer_inputs
        a = water_hammer_inputs(
            fluid='rp1', mass_flow_kg_s=10.0, density_kg_m3=820.0,
            line_id_m=0.05, wall_thickness_m=0.002, line_length_m=6.0,
            working_pressure_Pa=60.0e5)
        assert a['analyzer_kwargs']['density_kg_m3'] == pytest.approx(820.0)
        assert a['fluid_label']['density_forwarded_to_solver'] is True
        assert a['fluid_label']['label_status'] == 'density_mismatch'


# ===========================================================================
# DEVİR DENETİMİ — D18 onarımları bu tabanda duruyor mu?
# ===========================================================================
class TestD18OnarimlariDuruyor:
    """Devraldığım kalemlerin önceki onarımı dosyada hâlâ duruyor mu?"""

    def test_P4B3_16_bant_kapisi_duruyor(self, client):
        r = client.post('/api/trajectory-analysis',
                        json={'initial_mass': 50.0, 'final_mass': 35.0,
                              'drag_coefficient': 0.5, 'reference_area': 0.01,
                              'thrust': 4000.0, 'burn_time': 8.0,
                              'launch_angle': -88.0})
        assert r.status_code == 422

    def test_P4B3_17_beyan_celiskisi_duruyor(self):
        assert 'earth_rotation' not in ls.NOT_MODELLED
        assert 'earth_rotation_transport_velocity' in ls.NOT_MODELLED
        assert 'integrated' not in ls.NOT_MODELLED[
            'earth_rotation_transport_velocity'].lower()

    def test_P4B3_22_irtifa_telafisi_duruyor(self):
        from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
        assert hasattr(TrajectoryAnalyzer, 'set_nozzle_exit')

    def test_P4B4_09_referans_duzlemi_duruyor(self):
        from hrma.analysis.water_hammer import WORKING_PRESSURE_REFERENCES
        assert set(WORKING_PRESSURE_REFERENCES) == {'absolute', 'gauge'}

    def test_P4B4_10_iki_debi_celiskisi_fail_closed(self):
        from hrma.analysis.water_hammer import WaterHammerAnalyzer
        with pytest.raises(ValueError, match='described twice'):
            WaterHammerAnalyzer().analyze(
                fluid='water', line_length_m=10.0, line_id_mm=25.4,
                wall_thickness_mm=1.65, working_pressure_bar=10.0,
                pipe_material='ss_304', mdot_kg_s=0.5,
                flow_velocity_m_s=0.5, valve_closure_time_ms=100.0)

    def test_P4B4_10_ikinci_ayak_curutulmus_kaliyor(self):
        """``inputs`` bloğu GÖNDERİLEN malzeme adını yankılıyor."""
        from hrma.analysis.water_hammer import WaterHammerAnalyzer
        r = WaterHammerAnalyzer().analyze(
            fluid='water', line_length_m=10.0, line_id_mm=25.4,
            wall_thickness_mm=1.65, working_pressure_bar=10.0,
            pipe_material='bulunmayan_alasim', mdot_kg_s=0.5,
            valve_closure_time_ms=100.0)
        inp = r['inputs']
        assert inp['pipe_material'] == 'bulunmayan_alasim'
        assert inp['pipe_material_submitted'] == 'bulunmayan_alasim'
        assert inp['pipe_material_used'] == 'ss_304'
        assert r['flow_source'] == 'mdot_kg_s'


# ===========================================================================
# OH-D16-17 — KAPALI ÇAPA KAYDININ SAYISAL KİLİDİ
# ===========================================================================
class TestOHD1617BogazIsimaCapasi:
    """Boğaz ışıma bacağı yerel statik duruma geçtiğinde çapalar bayatlamıştı.

    D16'da ölçülüp fix-3'te yenilenen KAPALI kayıt bugüne kadar hiçbir
    bekçiyle bağlanmamıştı; D18 kaydı elle yeniden ölçtü. Kayıt artık
    testle kilitli: aynı işletme noktasında sayı sessizce kayarsa kırmızı.
    Sayılar: docs/scofield/raw/OH/D19/termo-ucus/a1/once.json (KD1617),
    taban 60cd341 ile bit-aynı.
    """

    ISLETME = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
               'chamber_diameter': 0.1, 'chamber_length': 0.3,
               'throat_diameter': 0.03, 'burn_time': 10.0,
               'mdot_total': 1.0}

    @pytest.fixture(scope='class')
    def sonuc(self):
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        return HeatTransferAnalyzer().analyze_heat_transfer(
            self.ISLETME, material='steel_4130', wall_thickness=0.005,
            cooling_type='regenerative')

    def test_bogaz_ve_kamara_akisi_capada(self, sonuc):
        g = sonuc['gas_side_analysis']
        assert g['throat_heat_flux'] == pytest.approx(
            15891841.845865484, rel=1e-9)
        assert g['chamber_heat_flux'] == pytest.approx(
            2442115.834506533, rel=1e-9)

    def test_denge_akisi_capada(self, sonuc):
        assert sonuc['wall_analysis']['equilibrium_heat_flux'] == \
            pytest.approx(8961281.708865134, rel=1e-9)

    def test_isima_kompozisyonunun_kaynagi_beyanli(self, sonuc):
        g = sonuc['gas_side_analysis']
        assert g['radiation_x_H2O'] == pytest.approx(0.25)
        assert g['radiation_x_CO2'] == pytest.approx(0.15)
        assert 'module default' in g['radiation_composition_source']
