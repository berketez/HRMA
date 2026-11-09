"""V306/KATI-MODEL — katı motor mühendis turu hataları (3.0.6) bekçileri.

Kaynak bulgular: ``docs/scofield/raw/OH/V306/muhendis-turu/kati/BULGULAR.md``
(2 Kas mühendis turu). Kanıt ve önce/sonra ölçümü:
``docs/scofield/raw/OH/V306/kati-model/``. Gövdeler turun gerçek API
gövdeleridir (``vakalar/L*.json``), docs'suz ağaçta da koşsun diye burada
gömülüdür.
"""
import copy

import pytest

HEADERS = {'Host': '127.0.0.1:8080'}

# Turun L3 gövdesi (EN arayüz, APCP 5 x BATES Ø250/110, kompozit kasa).
L3_GOVDE = {
    "propellant_name": "APCP - Ammonium Perchlorate Composite (AP/Al/HTPB)",
    "propellant_type": "apcp", "density": 1810, "erosive_m": 0.8,
    "grain_count": 5, "web_thickness": 70, "grain_type": "bates",
    "outer_diameter": 250, "core_diameter": 110, "grain_length": 1750,
    "grain_gap": 4, "insulation_thickness": 3, "inhibit_front": False,
    "inhibit_rear": False, "inhibit_outer": True,
    "grain_support": "cartridge_loaded", "case_material": "composite",
    "yield_strength_source": "material", "safety_factor": 2.5,
    "liner_thickness": 1.5, "liner_density": 1200, "initial_temp": 298,
    "closure_bolt_size": "M8", "closure_bolt_class": "8.8",
    "convergent_angle": 45, "divergent_angle": 15, "nozzle_efficiency": 0.95,
    "nozzle_material": "graphite", "chamber_pressure": 70,
    "burn_rate_a": 0.0022334, "burn_rate_n": 0.35, "burn_rate_preset": "custom",
    "combustion_efficiency": 0.95, "cf_efficiency": 0.98,
    "overall_efficiency": 0.92, "discharge_coeff": 0.98,
    "kinetic_efficiency": 0.97, "ignition_delay": 50,
    "igniter_pressure_fraction": 0.15, "atm_pressure": 101.325,
    "ambient_temp": 298,
}

# Turun L2 gövdesi (APCP 6 x BATES Ø98/56, 6061-T6 kasa, kartuş).
L2_GOVDE = dict(L3_GOVDE, **{
    "grain_count": 6, "web_thickness": 21, "outer_diameter": 98,
    "core_diameter": 56, "grain_length": 1200, "grain_gap": 3,
    "insulation_thickness": 2, "case_material": "aluminum",
    "liner_thickness": 1})

# Turun L1 gövdesi (Nakka KSB-002 kopyası, KNSB, 6061 kasa 1,65 mm).
L1_GOVDE = dict(L3_GOVDE, **{
    "propellant_name": "KNSB - Potassium Nitrate/Sorbitol 65/35",
    "propellant_type": "knsb", "density": 1841, "grain_count": 4,
    "web_thickness": 18.4, "outer_diameter": 55.9, "core_diameter": 19.05,
    "grain_length": 408, "grain_gap": 3.5, "insulation_thickness": 1,
    "chamber_diameter": 60.2, "case_material": "aluminum",
    "liner_thickness": 1, "initial_temp": 273.15, "case_thickness": 1.65,
    "chamber_pressure": 68.95, "burn_rate_a": 0.00114, "burn_rate_n": 0.535,
    "burn_rate_preset": "knsb"})


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


_ONBELLEK = {}


def _kos(client, govde):
    anahtar = repr(sorted(govde.items()))
    if anahtar not in _ONBELLEK:
        y = client.post('/calculate_solid', json=govde, headers=HEADERS)
        assert y.status_code == 200, y.get_json()
        _ONBELLEK[anahtar] = y.get_json()
    return _ONBELLEK[anahtar]


def _dokum(sonuc):
    return sonuc['design_summary']['masses']['inert_breakdown']


def _cad_lule(md):
    from hrma.export.cad_visualization import MotorCADDesigner
    return MotorCADDesigner()._estimate_component_mass('nozzle', md)


# ---------------------------------------------------------------------------
# M-KATI-19 — lüle kütlesi çizilen lülenin kontur integrali
# ---------------------------------------------------------------------------
class TestMKati19LuleKutlesi:

    @pytest.mark.parametrize('govde', [L1_GOVDE, L2_GOVDE, L3_GOVDE,
                                       dict(L3_GOVDE,
                                            nozzle_material='carbon_carbon')],
                             ids=['L1', 'L2', 'L3', 'L3_cc'])
    def test_motor_lule_kutlesi_CAD_ile_bit_ayni(self, client, govde):
        """Döküm kütlesi, CAD paketinin (STEP README: 'aynı kontur, cidar ve
        malzeme') tarttığı lüleyle AYNI sayı; malzeme motor_geometry'de."""
        r = _kos(client, govde)
        mg = r['motor_geometry']
        assert mg['nozzle_material'] == govde['nozzle_material']
        assert _dokum(r)['nozzle_kg'] == pytest.approx(_cad_lule(mg),
                                                        rel=1e-12)
        assert _dokum(r)['nozzle_basis']['status'] == 'computed'

    def test_kasa_malzemesi_luleyi_DEGISTIRMEZ(self, client):
        """Tur: kasayı çelikten kompozite çevirmek lüleyi 5,72 -> 1,79 kg
        yapıyordu (kasa kütlesinin sabit %19,5'i)."""
        celik = _dokum(_kos(client, dict(L3_GOVDE, case_material='steel_4130')))
        komp = _dokum(_kos(client, L3_GOVDE))
        assert celik['case_kg'] > 2.0 * komp['case_kg']
        assert celik['nozzle_kg'] == komp['nozzle_kg']

    def test_buyuyen_lule_AGIRLASIR(self, client):
        """Tur: test irtifası 6000 m'de çıkış 250,6 -> 298,8 mm büyürken lüle
        kütlesi aynı kalıyordu."""
        g = dict(L3_GOVDE)
        g.pop('atm_pressure')
        g['test_altitude'] = 6000
        yuksek = _kos(client, g)
        alcak = _kos(client, L3_GOVDE)
        assert yuksek['exit_diameter'] > 1.1 * alcak['exit_diameter']
        assert _dokum(yuksek)['nozzle_kg'] > 1.2 * _dokum(alcak)['nozzle_kg']

    def test_kuru_kutle_dokumun_toplami(self, client):
        r = _kos(client, L3_GOVDE)
        d = _dokum(r)
        parca = sum(d[k] for k in ('case_kg', 'closure_kg', 'nozzle_kg',
                                   'insulation_kg', 'liner_kg',
                                   'igniter_misc_kg'))
        assert d['total_kg'] == pytest.approx(parca, rel=1e-12)
        assert r['design_summary']['masses']['dry_mass_kg'] == pytest.approx(
            d['total_kg'], rel=1e-12)

    def test_maliyet_ayni_lule_kutlesini_fiyatlar(self, client):
        """Maliyet modeli üçüncü bir lüle kütlesi (0,8 x (d_t/0,05)^2)
        uyduruyordu; artık döküm kütlesini fiyatlar."""
        from hrma.engines.solid_rocket_engine import SOLID_COST_PARAMS
        r = _kos(client, L3_GOVDE)
        fiyat = r['cost_analysis']['material_costs_usd']['nozzle']
        beklenen = round(_dokum(r)['nozzle_kg']
                         * SOLID_COST_PARAMS['nozzle_usd_per_kg'], 1)
        assert fiyat == pytest.approx(beklenen, abs=0.051)

    def test_oran_kurali_SOKULDU(self):
        import inspect
        from hrma.engines import solid_rocket_engine as m
        for ad in ('_dry_mass_breakdown', '_calculate_dry_mass'):
            govde = inspect.getsource(getattr(m.SolidRocketEngine, ad))
            assert 'structural_mass * 0.15' not in govde
            assert 'nozzle_factor = 0.15' not in govde
            assert '_nozzle_drawn_mass' in govde


# ---------------------------------------------------------------------------
# M-KATI-20 — "deniz seviyesi Isp" alanı deniz seviyesi Isp'si; test
# ortamının Isp'si ve basıncı ayrı alanda, adıyla
# ---------------------------------------------------------------------------
def _l3_irtifa(h):
    g = dict(L3_GOVDE)
    g.pop('atm_pressure')
    g['test_altitude'] = h
    return g


class TestMKati20IspEtiketi:

    def test_test_irtifasi_lulesinin_deniz_seviyesi_Ispsi_DUSUK(self, client):
        """Tur: 6000 m lülesi (ε 18,61) için 'deniz seviyesi Isp' 245,3 s
        (= 6000 m ortamının Isp'si) basılıyordu; aşırı genişleyen lüle
        deniz seviyesinde 0 m lülesinden düşük olmalı."""
        yuksek = _kos(client, _l3_irtifa(6000))
        alcak = _kos(client, L3_GOVDE)
        assert yuksek['expansion_ratio'] > 1.5 * alcak['expansion_ratio']
        assert yuksek['isp_sea_level'] < alcak['isp_sea_level']
        assert yuksek['isp_design_ambient'] > alcak['isp_sea_level']

    def test_egri_Ispsi_adiyla_ve_ozdeslikle(self, client):
        r = _kos(client, _l3_irtifa(6000))
        assert r['specific_impulse'] == r['isp_design_ambient']
        assert r['isp_design_ambient'] == pytest.approx(
            r['total_impulse'] / (r['propellant_mass'] * 9.80665), rel=1e-9)
        assert r['isp_sea_level'] != r['isp_design_ambient']

    def test_ortam_kunyesi_cozucunun_basinci(self, client):
        from hrma.constants import isa_pressure
        r = _kos(client, _l3_irtifa(6000))
        da = r['design_ambient']
        assert da['source'] == 'test_altitude_isa'
        assert da['altitude_m'] == 6000.0
        assert da['is_sea_level'] is False
        assert da['pressure_kpa'] == pytest.approx(
            float(isa_pressure(6000.0)) / 1e3, rel=1e-12)
        # Ayrılma uyarısının ortam basıncıyla AYNI sayı.
        assert r['nozzle_flow_separation']['ambient_pressure_Pa'] == \
            pytest.approx(da['pressure_kpa'] * 1e3, rel=1e-12)

    def test_deniz_seviyesinde_iki_sayi_BIT_AYNI(self, client):
        r = _kos(client, L3_GOVDE)
        assert r['isp_sea_level'] == r['specific_impulse'] == \
            r['isp_design_ambient']
        assert r['design_ambient']['is_sea_level'] is True
        assert r['design_ambient']['source'] == 'atm_pressure'

    def test_sayfa_yorunge_paneli_egri_Ispsini_gonderir(self):
        """Yörünge ucu Isp'yi itki eğrisiyle kıyaslar (itici bütçesi);
        deniz seviyesi Isp'si artık eğriyle tutmayabilir."""
        from pathlib import Path
        govde = Path('hrma/templates/solid.html').read_text(encoding='utf-8')
        assert "const trIsp = (typeof cr.specific_impulse === 'number'" in govde
        assert 'renderSolverAmbientNote(results);' in govde
        assert "results.isp_design_ambient" in govde


# ---------------------------------------------------------------------------
# M-KATI-11 — lüle çıkışı ⟷ gövde uyarısı kasa DIŞ çapıyla
# ---------------------------------------------------------------------------
class TestMKati11CikisGovde:

    def test_uyari_kasa_dis_capini_basar(self, client):
        """Tur L2: '125,9 mm, 98 mm gövdeden geniş (1,28 kat)' — 98 mm
        yakıt bloğu çapıdır, kasa dış çapı 110,6 mm, oran 1,14."""
        r = _kos(client, L2_GOVDE)
        kayit = [w for w in r['warnings'] if isinstance(w, dict)
                 and w.get('code') == 'warn.solid.exit_cone_exceeds_case']
        assert len(kayit) == 1
        par = kayit[0]['params']
        kasa_dis = r['cad_design']['case_design']['outer_diameter']
        assert par['case_diameter_mm'] == pytest.approx(kasa_dis, abs=0.05)
        assert par['case_diameter_mm'] > r['grain_design']['outer_diameter_mm']
        assert par['ratio'] == pytest.approx(
            r['exit_diameter'] / kasa_dis, abs=0.005)

    def test_kasanin_icinde_kalan_cikista_uyari_yok(self, client):
        """Çıkış tane çapından büyük ama kasa dış çapından küçükse uyarı
        ateşlenmez (tur L2-a: 107,96 mm çıkış kasanın içindeydi)."""
        # Ölçüldü: 4 x 200 mm segment -> çıkış 102,38 mm, tane 98, kasa dış
        # 110,62 mm (eski kıyas burada uyarı veriyordu).
        g = dict(L2_GOVDE, grain_count=4, grain_length=800)
        r = _kos(client, g)
        kasa_dis = r['cad_design']['case_design']['outer_diameter']
        tane = r['grain_design']['outer_diameter_mm']
        assert tane < r['exit_diameter'] < kasa_dis, (
            tane, r['exit_diameter'], kasa_dis)
        assert not [w for w in r['warnings'] if isinstance(w, dict)
                    and w.get('code') == 'warn.solid.exit_cone_exceeds_case']


# ---------------------------------------------------------------------------
# M-KATI-2 — tasarım basıncı > patlama basıncı iken hüküm MARGINAL
# ---------------------------------------------------------------------------
class TestMKati2TasarimKatsayisi:

    def test_L1_kullanicinin_katsayisi_saglanmiyor_FAIL(self, client):
        """Tur L1 (bu tabanda yeniden üretildi): tasarım 172 bar, patlama
        165 bar, akma 151 bar, hüküm MARGINAL ('acceptable but thin')."""
        ps = _kos(client, L1_GOVDE)['safety_analysis']['pressure_safety']
        assert ps['design_pressure_bar'] > ps['burst_pressure_bar']
        c = ps['design_factor_check']
        assert c['met'] is False
        assert c['yield_pressure_bar'] == pytest.approx(ps['yield_pressure_bar'])
        assert c['yield_safety_factor'] < c['design_safety_factor'] == 2.5
        assert c['wall_thickness_mm'] == pytest.approx(1.65)
        assert c['hoop_required_mm'] > c['wall_thickness_mm']
        assert ps['vessel_status'] == 'FAIL'

    def test_yeterli_cidar_hukmu_bozmaz(self, client):
        g = dict(L1_GOVDE, case_thickness=2.5)
        ps = _kos(client, g)['safety_analysis']['pressure_safety']
        assert ps['design_factor_check']['met'] is True
        assert ps['vessel_status'] != 'FAIL'

    def test_HRMA_boyutlandirdiysa_kunye_yok(self, client):
        ps = _kos(client, L2_GOVDE)['safety_analysis']['pressure_safety']
        assert ps['design_factor_check'] is None

    def test_guvenlik_sekmesi_kunyeyi_basar(self):
        from pathlib import Path
        s = Path('hrma/templates/solid.html').read_text(encoding='utf-8')
        assert '${designFactorCheckRowHTML(pressureSafety)}' in s
        i18n = Path('hrma/static/js/i18n_pages.js').read_text(encoding='utf-8')
        assert i18n.count("'solid.safety.designFactorNotMet'") == 2


# ---------------------------------------------------------------------------
# M-KATI-10 — Analiz Merkezi "Kamara + nozul" yapısal FEA ağı kasayı kapsar
# ---------------------------------------------------------------------------
class TestMKati10YapisalAg:

    def test_kati_ag_kasa_silindirini_kapsar(self, client):
        """Tur L2: ağ z 0-0,192 m (yalnız lüle); kasa silindiri yoktu."""
        from hrma.fea import bridge
        r = _kos(client, L2_GOVDE)
        g = bridge.extract_structural_inputs(r)
        assert g['status'] == 'ok'
        assert g['chamber_extension_m'] is not None
        kontur = g['contour']
        r_kasa = r['motor_geometry']['chamber_diameter'] / 2.0
        assert float(kontur[0, 0]) < 0.0
        assert float(kontur[0, 1]) == pytest.approx(r_kasa, rel=1e-12)
        assert float(kontur[1, 1]) == pytest.approx(r_kasa, rel=1e-12)
        assert g['load_model']['end_force']['r0_m'] == pytest.approx(r_kasa)
        assert 'kasa iç boyu' in g['_basis']['kamara_uzantisi']['beyan']

    def test_silindir_boyu_saint_venant_bandindan(self, client):
        import numpy as np
        from hrma.fea import bridge
        from hrma.fea.structural_axisym import SAINT_VENANT_KAT
        r = _kos(client, L2_GOVDE)
        g = bridge.extract_structural_inputs(r)
        R = r['motor_geometry']['chamber_diameter'] / 2.0
        t = g['thickness_m']
        d_sv = SAINT_VENANT_KAT * np.sqrt(R * t)
        assert g['chamber_extension_m'] == pytest.approx(
            min(r['motor_geometry']['chamber_length'],
                bridge.KATI_KASA_SILINDIRI_SV_KATI * d_sv), rel=1e-12)

    def test_panel_geri_cekilen_hukmu_SF_mansetiyle_basmaz(self):
        from pathlib import Path
        s = Path('hrma/static/js/fea_panel.js').read_text(encoding='utf-8')
        i = s.index('function acStructuralVerdict')
        govde = s[i:i + 6000]
        assert '!_geriCekildi' in govde
        assert "fea.badgeSfWithheld" in s
        assert "'asme_linearised'" in s
        assert "fea.badgeEngineSfLower" in s


# ---------------------------------------------------------------------------
# M-KATI-21 — kompozit kasa güvenlik sekmesinde ham Python hatası yok
# ---------------------------------------------------------------------------
class TestMKati21Kompozit:

    def test_kompozit_patlama_basinci_bilinmez_ve_adiyla(self, client):
        ps = _kos(client, L3_GOVDE)['safety_analysis']['pressure_safety']
        assert ps['burst_pressure_bar'] is None
        assert ps['burst_pressure_status'] == 'not_evaluated_generic_composite'
        assert ps['burst_margin'] is None
        assert ps['vessel_status'] == 'NOT_EVALUATED'
        assert not any('Unknown material' in str(w)
                       for w in ps['vessel_warnings'])

    def test_metal_kasa_patlama_basinci_degismez(self, client):
        ps = _kos(client, L2_GOVDE)['safety_analysis']['pressure_safety']
        assert isinstance(ps['burst_pressure_bar'], float)
        assert ps['burst_pressure_status'] is None

    def test_guverte_mesaji_kullanici_dilinde(self):
        from pathlib import Path
        s = Path('hrma/static/js/analysis_dock.js').read_text(encoding='utf-8')
        assert "', the form would send \"' + engel[k].sent" not in s
        assert 'dock.materialNotInListField' in s
        i18n = Path('hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
        assert i18n.count("'dock.materialCompositeNoRecord'") == 2


# ---------------------------------------------------------------------------
# M-KATI-30 — PBAN/AP/Al kaydı kendi sınıfının kaynağıyla tutarlı
# ---------------------------------------------------------------------------
class TestMKati30Pban:

    def test_kayit_sutton_tablo_13_1_ile(self):
        import math
        from hrma.data.propellants_db import get_propellant
        k = get_propellant('pban_ap_al')
        assert k['flame_temperature'] == 3500.0
        assert k['density'] == 1780.0
        assert k['burn_rate_n'] == 0.33
        g, T, M = k['gamma'], k['flame_temperature'], k['molecular_weight']
        gam = math.sqrt(g * (2 / (g + 1)) ** ((g + 1) / (g - 1)))
        ideal = math.sqrt(8314.462618 * T / M) / gam
        assert k['c_star'] == pytest.approx(ideal, abs=0.05)
        cf = math.sqrt(2 * g * g / (g - 1) * (2 / (g + 1)) ** (
            (g + 1) / (g - 1)) * (1 - (14.7 / 1000.0) ** ((g - 1) / g)))
        isp = k['c_star'] * cf / 9.80665
        assert 260.0 <= isp <= 263.0, isp
        assert k['c_star_basis'] == 'eq3-32'
        assert 'Table 13-1' in k['source']


# ---------------------------------------------------------------------------
# M-KATI-16 — kartuş yüklü vakada Yapısal sekme ⟷ Tane kesiti FEA
# ---------------------------------------------------------------------------
def _tane_govdesi(r):
    """fea_panel.js grainParamsFromResults'un kurduğu gövde (BATES)."""
    gd = r['grain_design']
    gs = r['structural_analysis']['grain_structural']
    p = {'grain_type': gd['grain_type'],
         'propellant_type': r['propellant_type'],
         'outer_diameter_mm': gd['outer_diameter_mm'],
         'core_diameter_mm': gd['inner_diameter_mm'],
         'chamber_pressure_bar': r['chamber_pressure'],
         'grain_length_mm': gd['grain_length_mm'],
         'ambient_temp': gs['storage_temperature_k'],
         'case_radial_expansion_mm': gs['case_radial_expansion_mm']}
    if gs.get('grain_support_source') == 'user input':
        p['grain_support'] = gs['grain_support']
    return p


class TestMKati16TaneKesiti:

    @pytest.mark.parametrize('govde', [
        L2_GOVDE, L1_GOVDE, dict(L2_GOVDE, grain_support='case_bonded')],
        ids=['L2_kartus', 'L1_kartus', 'L2_yapistirilmis'])
    def test_fea_ve_analitik_ayni_port_gerinimi(self, client, govde):
        """Tur L2 (kartuş): Yapısal sekme %0,819 ⟷ tane FEA %0,36 (FEA kasayı
        rijit tutuyordu). Aynı dış sınır koşuluyla (kasa esnemesi) BATES
        kesitinde (Kt = 1) iki yol AYNI kalın cidarlı silindir problemidir."""
        r = _kos(client, govde)
        gs = r['structural_analysis']['grain_structural']
        assert gs['stress_concentration_factor'] == 1.0
        y = client.post('/api/fea/planar-grain', json=_tane_govdesi(r),
                        headers=HEADERS)
        assert y.status_code == 200, y.get_json()
        f = y.get_json()['fea']
        assert f['loads']['case_expansion_under_pressure'] is True
        assert f['loads']['case_radial_expansion_mm'] == pytest.approx(
            gs['case_radial_expansion_mm'], rel=1e-12)
        assert 100.0 * f['scalars']['max_bore_strain'] == pytest.approx(
            gs['bore_strain_percent'], rel=2e-3)

    def test_kasa_esnemesi_verilmezse_rijit_ve_beyanli(self, client):
        r = _kos(client, L2_GOVDE)
        g = _tane_govdesi(r)
        g.pop('case_radial_expansion_mm')
        f = client.post('/api/fea/planar-grain', json=g,
                        headers=HEADERS).get_json()['fea']
        assert f['loads']['case_expansion_under_pressure'] is False
        assert f['loads']['outer_surface'] == 'rigid case (u = 0)'

    @pytest.mark.parametrize('deger', [-0.1, 'abc', True, 1e9])
    def test_kasa_esnemesi_kapisi_adli_422(self, client, deger):
        r = _kos(client, L2_GOVDE)
        g = dict(_tane_govdesi(r), case_radial_expansion_mm=deger)
        y = client.post('/api/fea/planar-grain', json=g, headers=HEADERS)
        assert y.status_code == 422
        assert y.get_json()['error'] == 'case_radial_expansion_out_of_range'

    def test_sayfa_kasa_esnemesini_gonderir(self):
        from pathlib import Path
        s = Path('hrma/static/js/fea_panel.js').read_text(encoding='utf-8')
        assert 'p.case_radial_expansion_mm = gs.case_radial_expansion_mm;' in s


def test_m_kati_2_fail_ile_acceptable_cumlesi_ayni_listede_durmaz(client):
    """Ekranda ölçüldü (L1): FAIL rozeti altında kap modülünün 'Burst
    margin 1.20 is below 1.2 — acceptable but thin' cümlesi kalıyordu."""
    ps = _kos(client, L1_GOVDE)['safety_analysis']['pressure_safety']
    assert ps['vessel_status'] == 'FAIL'
    assert not any('acceptable' in str(u) for u in ps['vessel_warnings'])
    assert any('acceptable but thin' in u for u in
               ps['design_factor_check']['superseded_vessel_warnings'])
