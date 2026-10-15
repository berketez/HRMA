# -*- coding: utf-8 -*-
"""ÖH Dalga-17 · kulvar **kati** · aşama 1 — onarım bekçileri.

Her sınıf tek bir defter kalemini kilitler. Sayılar
``docs/scofield/raw/OH/D17/kati/a1/once.json`` (kusurlu hâl) ve
``sonra.json`` (onarılmış hâl) dosyalarından gelir; elle yazılmış tek bir
ölçüm yoktur. Ters mutasyon kanıtı: ``mutasyon_sonuc.json``.
"""
import contextlib
import io

import numpy as np
import pytest

from hrma.engines.solid_rocket_engine import (
    SOLID_MIN_DESIGN_EXPANSION_RATIO,
    SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG,
    SOLID_POLYGON_GRAIN_TYPES,
    SolidRocketEngine,
    _c_star_identity_audit,
    _conical_divergence_efficiency,
    _ideal_single_phase_c_star,
)

from tests.test_kitap_p1b import (  # noqa: E402 — APCP kâhini (TEK kaynak)
    CEA_DENGE_GAMMA_S,
    CEA_DENGE_IDEAL_TEK_FAZ_CSTAR_M_S,
    CEA_DENGE_OZDESLIK_SAPMA_YUZDE,
    optimum_genlesme_orani,
)

POLIGON = ('star', 'wagon_wheel', 'slotted')


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(**kw):
    p = dict(grain_type='bates', propellant_type='apcp',
             chamber_diameter=100, grain_length=500, core_diameter=30,
             chamber_pressure=40)
    p.update(kw)
    return _sessiz(SolidRocketEngine, **p)


@pytest.fixture(scope='module')
def apcp_bates_sonuc():
    return _sessiz(_motor().calculate_performance)


# =====================================================================
# P2B2-06 (Fable-D15 ŞART) — poligon port kesiti ayrımı ESKİ eşiği geçer
# =====================================================================
class TestP2B2_06PoligonKesitAyrimi:
    """Bekçi eşiği gereksiz gevşetilmişti; ayrım 1e-2'yi geçiyor."""

    @pytest.mark.parametrize('gt,alt_sinir', (('slotted', 0.017),
                                              ('star', 0.0115),
                                              ('wagon_wheel', 0.0152)))
    def test_ayrim_eski_esigi_geciyor(self, gt, alt_sinir):
        e = _motor(grain_type=gt)
        r0 = e.D_core / 2.0
        webs = np.linspace(0.0, 0.9 * e._max_web_thickness(), 25)
        sapma = max(abs(float(np.sqrt(_sessiz(e._port_flow_area, float(w))
                                      / np.pi)) - r0 - float(w))
                    for w in webs)
        assert sapma > 1e-2, (gt, sapma)
        assert sapma >= alt_sinir, (gt, sapma)

    @pytest.mark.parametrize('gt', ('bates', 'finocyl'))
    def test_dairesel_tipler_hala_ayrilmiyor(self, gt):
        """Eşik geri alınınca ayrım gücü artar, kaybolmaz."""
        e = _motor(grain_type=gt)
        r0 = e.D_core / 2.0
        webs = np.linspace(0.0, 0.9 * e._max_web_thickness(), 25)
        sapma = max(abs(float(np.sqrt(_sessiz(e._port_flow_area, float(w))
                                      / np.pi)) - r0 - float(w))
                    for w in webs)
        assert sapma < 1e-12, (gt, sapma)

    def test_yanma_animasyonu_bekcisi_eski_esikte(self):
        kaynak = open('tests/test_yanma_animasyonu.py',
                      encoding='utf-8').read()
        i = kaynak.index('def test_dairesel_olmayan_kesitler_'
                         'gercek_poligondan_gelir')
        govde = kaynak[i:i + 2200]
        assert 'np.abs(dw - w))) > 1e-2' in govde
        assert '> 1e-3' not in govde


# =====================================================================
# P2B2-08 (Fable-D15 ŞART) — "tablo verimi 15 dereceyi İÇERİR" iddiası
# =====================================================================
class TestP2B2_08ReferansKoniBeyani:

    def test_tablo_verimi_referans_koninin_ustunde_olcumu(self):
        """İddianın neden yanlış olduğunu SAYIYLA sabitler."""
        lam = float(_conical_divergence_efficiency(
            SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG))
        assert lam == pytest.approx(0.982963, abs=1e-6)
        eta = float(_motor(propellant_type='apcp').nozzle_efficiency)
        assert eta == pytest.approx(0.985, abs=1e-9)
        artik = 100.0 * (1.0 - eta / lam)
        assert artik < 0.0
        assert artik == pytest.approx(-0.207239, abs=1e-5)

    @pytest.mark.parametrize('aci', (None, 15.0, 45.0))
    def test_kunye_icerir_iddiasini_tasimiyor(self, aci):
        e = _motor()
        if aci is not None:
            e.divergent_half_angle_deg = aci
        k = _sessiz(e._isp_loss_breakdown, 95.0)['divergence_losses_basis']
        assert 'already contains' not in k
        assert 'Divergence is contained in the nozzle efficiency' not in k
        assert 'MODELLING ASSUMPTION' in k

    @pytest.mark.parametrize('aci', (15.0, 45.0))
    def test_kunye_kendi_sayilarini_yaziyor(self, aci):
        e = _motor()
        e.divergent_half_angle_deg = aci
        k = _sessiz(e._isp_loss_breakdown, 95.0)['divergence_losses_basis']
        assert '0.9830' in k or '0.982963' in k
        assert 'eta = 0.9850' in k
        assert '-0.2072%' in k
        assert 'NEGATIVE' in k

    def test_sayilar_degismedi(self):
        """ŞART 'sayı değişmez' diyor: 15 derecede oran tam 1.0."""
        e = _motor()
        e.divergent_half_angle_deg = SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG
        assert e._divergence_efficiency_correction() == pytest.approx(1.0,
                                                                     abs=0.0)
        e45 = _motor()
        e45.divergent_half_angle_deg = 45.0
        assert e45._divergence_efficiency_correction() == pytest.approx(
            0.868348, abs=1e-6)


# =====================================================================
# P2B1-07 (Fable-D15 ŞART) + OH-D16-10 — sıfır port kapısı
# =====================================================================
class TestP2B1_07SifirPortKapisi:

    @pytest.mark.parametrize('gt', ('bates', 'star', 'wagon_wheel',
                                    'finocyl', 'slotted'))
    def test_radyal_tipte_sifir_cekirdek_reddedilir(self, gt):
        from hrma.engines.solid_rocket_engine import SolidGeometryError
        with pytest.raises(SolidGeometryError) as ex:
            _motor(grain_type=gt, core_diameter=0)
        kunye = ex.value.kunye
        assert kunye['field'] == 'core_diameter'
        assert kunye['reason'] == 'zero_port'
        assert kunye['value'] == 0.0
        assert kunye['unit'] == 'mm'
        assert kunye['motor_form'] == 'solid'

    def test_end_burner_sifir_cekirdegi_kabul_eder(self):
        """Eksenel yanan grainde port yoktur; kapı burayı DARALTMAZ."""
        e = _motor(grain_type='end_burner', core_diameter=0)
        r = _sessiz(e.calculate_performance)
        assert r.get('error') is None
        assert r['specific_impulse'] > 0

    def test_saglikli_motor_kapiya_takilmiyor(self):
        r = _sessiz(_motor(core_diameter=30).calculate_performance)
        assert r.get('error') is None

    def test_negatif_cekirdek_ayri_adla_reddedilir(self):
        from hrma.engines.solid_rocket_engine import SolidGeometryError
        with pytest.raises(SolidGeometryError) as ex:
            _motor(core_diameter=-30)
        assert ex.value.kunye['reason'] == 'negative_core'

    def test_uc_yuzunde_sifir_port_sonuc_yayimlamiyor(self):
        """ÖH D16-10 ürün yüzü: /api/uncertainty-analysis core=0 -> 200 'ok'
        idi (aynı uç core=-30'a 400 diyordu)."""
        from hrma.app import app
        app.config['TESTING'] = True
        c = app.test_client()
        yuk = {'motor_type': 'solid', 'level': 'fast',
               'inputs': {'motor_name': 'D17', 'propellant_type': 'apcp',
                          'grain_type': 'bates', 'chamber_pressure': 40.0,
                          'thrust': 5000.0, 'burn_time': 3.0,
                          'chamber_diameter': 100.0, 'grain_length': 500.0,
                          'core_diameter': 0.0, 'expansion_ratio': 8.0}}
        r = _sessiz(c.post, '/api/uncertainty-analysis', json=yuk)
        assert r.status_code != 200, r.get_data(as_text=True)[:200]
        assert 'core_diameter' in r.get_data(as_text=True)


# =====================================================================
# P2B2-04 (Fable-D15 ŞART) — tükeniş webi paydası
# =====================================================================
class TestP2B2_04TukenisWebiPaydasi:

    @pytest.mark.parametrize('gt', POLIGON + ('finocyl',))
    def test_payda_cozucunun_tukenis_webi(self, gt):
        e = _motor(grain_type=gt)
        tukenis = e._geometric_burnout_web()
        assert tukenis is not None, gt
        assert e._available_web_thickness() == pytest.approx(tukenis,
                                                             rel=1e-12)
        assert _sessiz(e.calculate_burn_area, tukenis * 1.000001) <= 0.0
        assert _sessiz(e.calculate_burn_area, tukenis * 0.999) > 0.0

    @pytest.mark.parametrize('gt,alt', (('star', 98.9), ('wagon_wheel', 98.3),
                                        ('slotted', 98.2), ('finocyl', 99.9)))
    def test_tukenen_grain_tam_kullanim_okur(self, gt, alt):
        r = _sessiz(_motor(grain_type=gt).calculate_performance)
        y = r['detailed_analysis']['grain_regression_analysis'][
            'web_thickness_utilization']
        assert y >= alt, (gt, y)
        assert y <= 100.0

    @pytest.mark.parametrize('gt,beklenen', (('bates', 99.9433),
                                             ('end_burner', 100.0)))
    def test_kapali_formlu_tipler_bozulmadi(self, gt, beklenen):
        r = _sessiz(_motor(grain_type=gt).calculate_performance)
        y = r['detailed_analysis']['grain_regression_analysis'][
            'web_thickness_utilization']
        assert y == pytest.approx(beklenen, abs=0.01), gt

    def test_payda_radyal_etten_kucuk(self):
        """Poligon tipte tükeniş webi (D-d)/2'nin ALTINDA olmalı — kalemin
        ölçtüğü fark tam olarak budur."""
        for gt in POLIGON:
            e = _motor(grain_type=gt)
            assert e._available_web_thickness() < (e.D_chamber - e.D_core) / 2

    def test_payda_yayimlaniyor(self, apcp_bates_sonuc):
        g = apcp_bates_sonuc['detailed_analysis']['grain_regression_analysis']
        assert g['web_consumable_mm'] == pytest.approx(35.0, abs=1e-9)
        assert 'the burning area vanishes' in g[
            'web_thickness_utilization_basis']

    def test_tarama_siniri_ayri_kaldi(self):
        e = _motor(grain_type='star')
        assert e._max_web_thickness() == pytest.approx(e.D_chamber / 2)
        assert e._max_web_thickness() > e._available_web_thickness()

    def test_poligon_kumesi_tek_tanim(self):
        assert SOLID_POLYGON_GRAIN_TYPES == ('star', 'wagon_wheel',
                                             'finocyl', 'slotted')


# =====================================================================
# P2B3-09 — genişleme oranının sessiz kelepçesi
# =====================================================================
class TestP2B3_09GenislemeKelepcesi:

    # ÖH KİTAP p1b-F (B11): eski literaller (5,931748 / 16,354926 /
    # 103,060229 / 1775,378588) geri çözülmüş kaydın γ = 1,1986'sıyla
    # türemişti. Beklenen artık kâhinin denge γ_s'sinden (test_kitap_p1b,
    # CEA) izantropik kapalı biçimle hesaplanır; tolerans aynı (rel 1e-6).
    @pytest.mark.parametrize('pa', (1.01325, 0.26437, 0.025492, 0.00075945))
    def test_optimum_kirpilmiyor(self, pa):
        e = _motor()
        e.ambient_pressure_bar = pa
        if hasattr(e, '_epsilon_cache'):
            del e._epsilon_cache
        beklenen = optimum_genlesme_orani(CEA_DENGE_GAMMA_S, e.P_c / pa)
        assert float(_sessiz(e._estimate_expansion_ratio)) == pytest.approx(
            beklenen, rel=1e-6)

    def test_25km_artik_25_yazmiyor(self):
        e = _motor()
        e.ambient_pressure_bar = 0.025492
        eps = float(_sessiz(e._estimate_expansion_ratio))
        assert eps > 100.0
        assert eps != pytest.approx(25.0, abs=1e-6)

    def test_deniz_seviyesi_degismedi(self, apcp_bates_sonuc):
        # ÖH KİTAP p1b-F: eski 5,931748 γ = 1,1986'dan; beklenen kâhinden.
        pc = _motor().P_c
        assert apcp_bates_sonuc['nozzle_design'][
            'expansion_ratio'] == pytest.approx(
                optimum_genlesme_orani(CEA_DENGE_GAMMA_S, pc / 1.01325),
                rel=1e-6)
        assert apcp_bates_sonuc['nozzle_design'][
            'expansion_ratio_bound'] is None

    def test_alt_sinir_baglandiginda_beyan_ediliyor(self):
        e = _motor(chamber_pressure=2.0)
        e.ambient_pressure_bar = 1.01325
        if hasattr(e, '_epsilon_cache'):
            del e._epsilon_cache
        eps = float(_sessiz(e._estimate_expansion_ratio))
        assert eps == pytest.approx(SOLID_MIN_DESIGN_EXPANSION_RATIO)
        beyan = e._expansion_ratio_bound
        assert beyan is not None
        assert beyan['bound'] in ('minimum', 'no_supersonic_expansion',
                                  'subsonic_exit')
        assert beyan['applied_value'] == pytest.approx(
            SOLID_MIN_DESIGN_EXPANSION_RATIO)
        assert 'minimum design expansion ratio' in beyan['basis']

    def test_supersonik_genisleme_yoksa_beyan_var(self):
        e = _motor()
        e.ambient_pressure_bar = 60.0
        if hasattr(e, '_epsilon_cache'):
            del e._epsilon_cache
        _sessiz(e._estimate_expansion_ratio)
        assert e._expansion_ratio_bound['bound'] == 'no_supersonic_expansion'

    def test_kunye_ust_kelepcenin_kalktigini_soyluyor(self, apcp_bates_sonuc):
        k = apcp_bates_sonuc['nozzle_design']['expansion_ratio_basis']
        assert 'No upper clamp is applied' in k
        assert '103.06' in k


# =====================================================================
# P2B3-10 — yalıtım yoğunluğu tek kaynak
# =====================================================================
class TestP2B3_10YalitimYogunlugu:

    @staticmethod
    def _kur(rho=None):
        ov = {'insulation_thickness': 3.0, 'liner_thickness': 2.0}
        if rho is not None:
            ov['liner_density'] = rho
        return _motor(overrides=ov)

    def test_kullanici_yogunlugu_kutleye_isliyor(self):
        """ÇEVRİLDİ — ÖH D24 (OH-D23-10). Kalemin ölçtüğü şey yoğunluğun
        kütleye işlemesidir (oran testi, aşağıdaki son satır); iki MUTLAK
        sayı ise yanlış katman sırasını (grain→yalıtım→liner) yan etki
        olarak kilitliyordu. Sıra SP-8093/Sutton sırasına
        (grain→liner→yalıtım) çevrilince yalıtım halkasının iç çapı
        D yerine D+2·t_liner oldu ve aynı motorda ölçülen değerler
        0,698942 -> 0,726085 / 1,106657 -> 1,149634 diye kaydı. Oran ve
        yoğunluk-orantısı BOZULMADI (1900/1200 = 1,583333); yalnız
        geometri referansı düzeldi. Gevşetme yok: bağıl tolerans 1e-5
        aynen duruyor."""
        taban = _sessiz(self._kur()._dry_mass_breakdown)['insulation_kg']
        artan = _sessiz(self._kur(1900.0)._dry_mass_breakdown)['insulation_kg']
        assert taban == pytest.approx(0.726085, rel=1e-5)
        assert artan == pytest.approx(1.149634, rel=1e-5)
        assert artan / taban == pytest.approx(1900.0 / 1200.0, rel=1e-9)

    def test_panel_ile_kutle_ayni_sayiyi_kullaniyor(self):
        """Panel, kütle ve ısıl zincir TEK sayıyı okur: kütle yoğunlukla
        tam orantılı olmalı (geometri sabitken)."""
        taban = self._kur()
        m_taban = _sessiz(taban._dry_mass_breakdown)['insulation_kg']
        for rho in (800.0, 1900.0, 2400.0):
            e = self._kur(rho)
            panel = _sessiz(e._design_insulation_system)[
                'thermal_barrier']['density']
            assert panel == pytest.approx(e._insulation_density())
            assert panel == pytest.approx(rho)
            m = _sessiz(e._dry_mass_breakdown)['insulation_kg']
            assert m / m_taban == pytest.approx(rho / 1200.0, rel=1e-9)

    def test_girilmediginde_tablo_tek_kaynak(self):
        from hrma.engines.solid_rocket_engine import SOLID_INSULATION
        assert self._kur()._insulation_density() == pytest.approx(
            SOLID_INSULATION['density_kg_m3'])


# =====================================================================
# P2B1-01 — c* ⟷ (gamma, T_c, M) kimlik denetimi
# =====================================================================
class TestP2B1_01CstarKimlikDenetimi:

    def test_eq332_tek_tanim_noktasi(self):
        # double_base kaydının kendi üçlüsü
        assert _ideal_single_phase_c_star(1.2612, 2789.3, 26.89) == \
            pytest.approx(1406.7742, abs=1e-3)

    @pytest.mark.parametrize('pt,durum,sapma', (
        # ÖH KİTAP p1b-F (B11): eski ('single_phase_consistent', -0,0001)
        # geri çözülmüş dörtlüden; CEA denge dörtlüsü iki fazlıdır.
        ('apcp', 'two_phase_explained', CEA_DENGE_OZDESLIK_SAPMA_YUZDE),
        ('double_base', 'single_phase_consistent', 0.0018),
        ('black_powder', 'two_phase_explained', -16.4676),
        ('knsu', 'two_phase_explained', -5.8971),
    ))
    def test_kayitlarin_hukmu(self, pt, durum, sapma):
        e = _motor(propellant_type=pt)
        a = _c_star_identity_audit(pt, e.gamma, e.T_c, e.mw_exhaust, e.c_star)
        assert a['status'] == durum, (pt, a)
        assert a['deviation_percent'] == pytest.approx(sapma, abs=1e-3)

    def test_eski_double_base_reddediliyor(self):
        """Ölçüt ÖLÜ değil: kalemin ölçülen eski hâli yakalanıyor."""
        a = _c_star_identity_audit('double_base', 1.2612, 2789.3, 26.89,
                                   1186.7)
        assert a['status'] == 'unexplained_deficit'
        assert a['deviation_percent'] == pytest.approx(-15.6439, abs=1e-3)

    def test_ideali_asan_kayit_yakalanir(self):
        a = _c_star_identity_audit('double_base', 1.2612, 2789.3, 26.89,
                                   1600.0)
        assert a['status'] == 'above_single_phase_ideal'

    def test_eksiklik_Xp_ile_sinirli(self):
        """X_p'yi aşan eksiklik AÇIKLANMIŞ sayılmaz (siyah barut X_p=0,55)."""
        a = _c_star_identity_audit('black_powder', 1.251, 2216.4, 33.21,
                                   400.0)
        assert a['status'] == 'unexplained_deficit'

    def test_denetim_yayimlaniyor(self, apcp_bates_sonuc):
        # ÖH KİTAP p1b-F (B11): eski ('single_phase_consistent', 1598,2015)
        # geri çözülmüş dörtlüden; beklenen kâhinin denge dörtlüsünden.
        a = apcp_bates_sonuc['c_star_identity_audit']
        assert a['status'] == 'two_phase_explained'
        assert a['ideal_single_phase_c_star_m_s'] == pytest.approx(
            CEA_DENGE_IDEAL_TEK_FAZ_CSTAR_M_S, abs=1e-3)
        assert a['condensed_mass_fraction'] == pytest.approx(0.340119,
                                                             abs=1e-6)

    def test_hicbir_katalog_kaydi_muaf_degil(self):
        from hrma.data.propellants_db import PROPELLANTS
        kotu = [(k, _c_star_identity_audit(
            k, r['gamma'], r['flame_temperature'], r['molecular_weight'],
            r['c_star'])['status']) for k, r in PROPELLANTS.items()]
        assert [x for x in kotu if x[1] in ('unexplained_deficit',
                                            'above_single_phase_ideal',
                                            'not_evaluable')] == []

    def test_bayat_muafiyet_etiketi_kalkti(self):
        from hrma.data.propellants_db import PROPELLANTS
        assert PROPELLANTS['double_base']['c_star_basis'] == 'eq3-32'
        assert PROPELLANTS['black_powder']['c_star_basis'] == \
            'measured-two-phase'
