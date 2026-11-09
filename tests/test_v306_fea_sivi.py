"""V306/FEA-SIVI — yapısal FEA hataları (3.0.6) bekçileri.

Kalem 1: sıvı rejeneratif cidarın iki malzemeli termo-elastik FEA'sı.
Kalem 3: motor türü başına fiziksel mesnet kipi (katı L2 hükmü).
Kalem 2/4/5: panel metinleri, Basınçlı Kap katmanı, renk çubuğu.

Kanıt ve önce/sonra ölçümü: ``docs/scofield/raw/OH/V306/fea-sivi/``.
Gövdeler mühendis turunun gerçek API gövdeleridir; docs'suz ağaçta da
koşsun diye burada gömülüdür.
"""
import json
from pathlib import Path

import numpy as np
import pytest

HEADERS = {'Host': '127.0.0.1:8080'}

# Katı tur L2 gövdesi (APCP 6 x BATES Ø98/56, 6061-T6 kasa, kartuş).
KATI_L2 = {
    "propellant_name": "APCP - Ammonium Perchlorate Composite (AP/Al/HTPB)",
    "propellant_type": "apcp", "density": 1810, "erosive_m": 0.8,
    "grain_count": 6, "web_thickness": 21, "grain_type": "bates",
    "outer_diameter": 98, "core_diameter": 56, "grain_length": 1200,
    "grain_gap": 3, "insulation_thickness": 2, "inhibit_front": False,
    "inhibit_rear": False, "inhibit_outer": True,
    "grain_support": "cartridge_loaded", "case_material": "aluminum",
    "yield_strength_source": "material", "safety_factor": 2.5,
    "liner_thickness": 1, "liner_density": 1200, "initial_temp": 298,
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

ORNEK_SIVI = Path('examples/Example Liquid LOX-RP1 25kN.hrma')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


_ONBELLEK = {}


def _motor(client, uc, govde):
    anahtar = (uc, repr(sorted(govde.items())))
    if anahtar not in _ONBELLEK:
        y = client.post(uc, json=govde, headers=HEADERS)
        assert y.status_code == 200, y.get_json()
        j = y.get_json()
        _ONBELLEK[anahtar] = j.get('results') or j
    return _ONBELLEK[anahtar]


def _fea(client, motor):
    y = client.post('/api/fea/structural', json={'motor_results': motor},
                    headers=HEADERS)
    assert y.status_code == 200, y.get_json()
    return y.get_json()['fea']


@pytest.fixture(scope='module')
def sivi_motor(client):
    govde = json.loads(ORNEK_SIVI.read_text(encoding='utf-8'))
    return _motor(client, '/calculate_liquid', dict(govde['inputs']['fields']))


@pytest.fixture(scope='module')
def sivi_fea(client, sivi_motor):
    return _fea(client, sivi_motor)


# ---------------------------------------------------------------------------
# Kalem 3 — fiziksel mesnet kipi
# ---------------------------------------------------------------------------
def _koni_kontur():
    z = np.concatenate([np.linspace(-0.1, 0.0, 30),
                        np.linspace(0.002, 0.06, 30)])
    r = np.where(z <= 0.0, 0.05, 0.05 - 0.4 * z)
    return np.stack([z, r], axis=1)


class TestKalem3MesnetKipi:

    def test_on_govde_z_min_ile_bit_ayni(self):
        from hrma.fea.mesh_axisym import build_wall_mesh
        from hrma.fea.structural_axisym import (
            InnerPressureLoad, Material, solve_pressure)
        m = build_wall_mesh(_koni_kontur(), 0.003, 64, 4)
        mat = Material(E=200e9, nu=0.3, yield_strength=500e6)
        yuk = InnerPressureLoad(p_ref_pa=5e6,
                                end_force_n=5e6 * np.pi * 0.05 ** 2)
        a = solve_pressure(m, mat, yuk, axial_fix='z_min')
        b = solve_pressure(m, mat, yuk, axial_fix='on_govde')
        assert np.array_equal(a.stress_nodal, b.stress_nodal)
        assert a.min_safety_factor == b.min_safety_factor

    def test_arka_govde_silindirin_son_istasyonu(self):
        from hrma.fea.mesh_axisym import build_wall_mesh
        from hrma.fea.structural_axisym import arka_govde_istasyonu
        m = build_wall_mesh(_koni_kontur(), 0.003, 64, 4)
        i = arka_govde_istasyonu(m)
        g = m.node_index_grid
        assert m.nodes[g[i, 0], 1] == pytest.approx(0.05, rel=1e-9)
        assert m.nodes[g[i + 1, 0], 1] < 0.05 * (1 - 1e-6)
        # Önde silindir yoksa kip TANIMSIZ (uydurma konum yok).
        z = np.linspace(0.0, 0.06, 30)
        koni = np.stack([z, 0.05 - 0.4 * z], axis=1)
        with pytest.raises(ValueError):
            arka_govde_istasyonu(build_wall_mesh(koni, 0.003, 32, 4))

    def test_politika_tek_yerde_ve_lule_cikisi_hukme_girmez(self):
        from hrma.fea.structural_axisym import (
            AXIAL_FIX_MODES, FIZIKSEL_MESNET_KIPLERI, MESNET_KIPI_POLITIKASI,
            mesnet_kipi_politikasi)
        assert set(MESNET_KIPI_POLITIKASI) == {'solid', 'liquid', 'hybrid'}
        for tur, p in MESNET_KIPI_POLITIKASI.items():
            assert p['birincil'] in FIZIKSEL_MESNET_KIPLERI
            assert p['ayrisma'] in FIZIKSEL_MESNET_KIPLERI
            assert p['karsilastirma'] == 'z_max'
            assert p['_basis']
        # Köprünün yapay iki-kip zarfı değişmedi.
        assert AXIAL_FIX_MODES == ('both_ends', 'z_min', 'z_max')
        with pytest.raises(ValueError):
            mesnet_kipi_politikasi('ion')

    def test_kati_L2_hukmu_fiziksel_kiple_verilir(self, client):
        """Tur L2: iki kip %46 ayrışıyor, hüküm geri çekiliyordu."""
        f = _fea(client, _motor(client, '/calculate_solid', KATI_L2))
        hk = f['meta']['hukum']
        kd = f['meta']['kisit_duyarliligi']
        assert kd['yayimlanan_kip'] == 'on_govde'
        kapi = hk['kisit_yeri_duyarliligi']
        assert kapi['olculdu'] is True
        assert kapi['ayrisma_kipi'] == 'arka_govde'
        assert kapi['bagil_fark'] < kapi['esik']
        assert hk['verildi'] is True
        assert 'kisit_yeri_duyarliligi_yuksek' not in \
            hk['geri_cekme_gerekceleri']
        # Lüle çıkışı mesnetli çözüm BEYANLI karşılaştırmadır, manşet değil.
        k = kapi['karsilastirma']
        assert k['kip'] == 'z_max'
        assert k['min_safety_factor'] < f['scalars']['min_safety_factor']

    def test_ayrisma_esigi_asilirsa_hukum_geri_cekilir(self, client,
                                                      monkeypatch):
        import hrma.fea.structural_axisym as sa
        monkeypatch.setattr(sa, 'kisit_yeri_duyarlilik_esigi',
                            lambda nu: 0.0)
        f = _fea(client, _motor(client, '/calculate_solid', KATI_L2))
        hk = f['meta']['hukum']
        assert hk['verildi'] is False
        assert 'kisit_yeri_duyarliligi_yuksek' in hk['geri_cekme_gerekceleri']


# ---------------------------------------------------------------------------
# Kalem 1 — iki malzemeli termo-elastik FEA
# ---------------------------------------------------------------------------
class TestKalem1IkiKatman:

    def test_iki_katmanli_silindir_isil_kapali_bicim(self):
        """Sabit ΔT, bağlı iki katman: FE ⟷ kapalı biçim (Lamé +
        genelleştirilmiş düzlem şekil değiştirme)."""
        from hrma.fea.mesh_axisym import build_layered_wall_mesh
        from hrma.fea.structural_axisym import (
            CidarKatmani, InnerPressureLoad, Material, _katman_hukmu,
            _katmanli_coz, kalin_iki_katmanli_silindir_isil)
        a, b, c = 0.05, 0.051, 0.0535
        z = np.linspace(0.0, 0.4, 50)
        kontur = np.stack([z, np.full_like(z, a)], axis=1)
        Tr = 293.15
        k1 = CidarKatmani('liner', Material(120e9, 0.33, 300e6), 17e-6,
                          b - a, 2, Tr + 280, Tr + 280)
        k2 = CidarKatmani('closeout', Material(200e9, 0.29, 900e6), 13e-6,
                          c - b, 2, Tr + 60, Tr + 60)
        m = build_layered_wall_mesh(kontur, [b - a, c - b], 400, [4, 4])
        sin = [(d['j0'], d['j1']) for d in m.meta['katmanlar']]
        cz = _katmanli_coz(m, [k1, k2], sin, 'on_govde',
                           InnerPressureLoad(p_ref_pa=0.0), 0.0, Tr, True)
        g, _ = kalin_iki_katmanli_silindir_isil(
            a, b, c, 120e9, 0.33, 17e-6, 280.0, 200e9, 0.29, 13e-6, 60.0)
        i = m.n_axial // 2
        olcek = 0.0
        hata = 0.0
        for kt, (j0, j1) in zip((k1, k2), sin):
            S = _katman_hukmu(m, kt, j0, j1, cz,
                              np.ones(m.n_nodes, bool))['stress_nodal']
            for j in (j0, j1):
                n = m.node_index_grid[i, j]
                r = m.nodes[n, 1]
                r_an = r - 1e-12 if (kt.ad == 'liner' and j == j1) else (
                    r + 1e-12 if (kt.ad == 'closeout' and j == j0) else r)
                sr, st, sz = g(np.array([r_an]))
                olcek = max(olcek, abs(st[0]), abs(sz[0]))
                hata = max(hata, abs(S[n, 2] - st[0]), abs(S[n, 0] - sz[0]),
                           abs(S[n, 1] - sr[0]))
        assert hata / olcek < 1e-3

    def test_tek_malzeme_sinirinda_eski_cozumle_ayni(self):
        """Astar = kabuk malzemesi, ısıl yük yok: katmanlı çözücü tek
        malzemeli ``solve_pressure`` ile aynı yer değiştirmeyi verir."""
        from hrma.fea.mesh_axisym import (
            build_layered_wall_mesh, build_wall_mesh)
        from hrma.fea.structural_axisym import (
            CidarKatmani, InnerPressureLoad, Material, _katmanli_coz,
            solve_pressure)
        mat = Material(200e9, 0.29, 1.0e9)
        kontur = _koni_kontur()
        tek = build_wall_mesh(kontur, 0.003, 64, 6)
        kat = build_layered_wall_mesh(kontur, [0.001, 0.002], 64, [2, 4])
        assert np.allclose(tek.nodes, kat.nodes, rtol=0, atol=1e-15)
        yuk = InnerPressureLoad(p_ref_pa=5e6,
                                end_force_n=5e6 * np.pi * 0.05 ** 2)
        eski = solve_pressure(tek, mat, yuk, axial_fix='on_govde')
        ks = [CidarKatmani('liner', mat, 13e-6, 0.001, 2, 300.0, 300.0),
              CidarKatmani('closeout', mat, 13e-6, 0.002, 2, 300.0, 300.0)]
        sin = [(d['j0'], d['j1']) for d in kat.meta['katmanlar']]
        yeni = _katmanli_coz(kat, ks, sin, 'on_govde', yuk, 0.0, 293.15,
                             termal=False)
        assert np.allclose(yeni['u'], eski.displacement, rtol=1e-9,
                           atol=1e-15 * np.abs(eski.displacement).max())

    def test_ornek_sivi_iki_katman_cozulur_ve_hukum_katmanlardan(
            self, sivi_fea, sivi_motor):
        from hrma.analysis.pressure_vessel import (
            CODE_PRESSURE_FACTORS, LIQUID_ENGINE_HARDWARE_CODE)
        t = sivi_fea['two_layer']
        assert t['solved'] is True
        roller = [k['role'] for k in t['layers']]
        assert roller == ['liner', 'channels', 'closeout']
        hukumlu = [k for k in t['layers'] if k['judged']]
        assert [k['role'] for k in hukumlu] == ['liner', 'closeout']
        sf = {k['role']: k['primary']['safety_factor'] for k in hukumlu}
        assert sivi_fea['scalars']['min_safety_factor'] == pytest.approx(
            min(sf.values()), rel=1e-12)
        assert sivi_fea['scalars']['governing_layer'] == min(sf, key=sf.get)
        # Her katman KENDİ malzemesi ve akmasıyla.
        cs = sivi_motor['structural_analysis']['chamber_structure']
        kayit = {k['role']: k for k in cs['wall_layers']}
        for k in hukumlu:
            assert k['yield_pa'] == pytest.approx(
                kayit[k['role']]['yield_at_temperature_MPa'] * 1e6)
        assert t['layers'][0]['material'] != t['layers'][2]['material']
        # 5012C kabul katsayısı CODE_PRESSURE_FACTORS'tan.
        assert t['proof_factor'] == CODE_PRESSURE_FACTORS[
            LIQUID_ENGINE_HARDWARE_CODE]['proof']
        hk = sivi_fea['meta']['hukum']
        assert hk['verildi'] is True, hk['geri_cekme_gerekceleri']
        assert sivi_fea['convergence']['converged'] is True
        n = sivi_fea['mesh']['n_nodes']
        assert len(sivi_fea['fields']['von_mises_pa']) == n
        assert [d['role'] for d in sivi_fea['mesh']['layers']] == roller
        # Isıl gerilme ikincil: P+Q sınırı 2·akma ile ayrı yayımlanır.
        for k in hukumlu:
            pq = k['primary_plus_secondary']
            assert pq['S_PS_pa'] == pytest.approx(2.0 * k['yield_pa'])
            assert pq['shakedown_factor'] == pytest.approx(
                pq['S_PS_pa'] / pq['P_L_Pb_Q_max_pa'])

    def test_katman_girdisi_eksikse_adiyla(self, client, sivi_motor):
        import copy
        m = copy.deepcopy(sivi_motor)
        m.pop('cooling_channels', None)
        f = _fea(client, m)
        t = f['two_layer']
        assert t['solved'] is False
        assert 'cooling_channels.n_channels' in t['missing']
        # İki katmanlı çözüm kurulamadı: köprünün dış kabuk çözümü kalır.
        assert f['scalars']['material_key'] == 'inconel_718'


# ---------------------------------------------------------------------------
# Kalem 2 — M-SIVI-15: tek tanım, oran yönü, nozul cidarı beyanı
# ---------------------------------------------------------------------------
# Sıvı tur L2 gövdesi (2 kN CH4/LOX, ablatif, tek cidar SS316).
SIVI_L2 = {
    "fuel_type": "methane", "oxidizer_type": "lox", "fuel_density": 422.352,
    "oxidizer_density": 1141.16, "fuel_viscosity": 0.0001169,
    "oxidizer_viscosity": 0.0001947, "mixture_ratio": 3, "of_min": 2,
    "of_max": 3.2, "combustion_efficiency": 97, "engine_cycle": "pressure_fed",
    "thrust": 2000, "chamber_pressure": 35, "feed_pressure": 55,
    "injector_type": "coaxial", "injector_pressure_drop": 7,
    "discharge_coefficient": 0.7, "injector_elements": 18,
    "characteristic_length": 1.2, "contraction_ratio": 4,
    "chamber_material": "steel_316", "chamber_roughness": 3.2,
    "cooling_type": "ablative", "nozzle_expansion_ratio": 6,
    "nozzle_type": "bell_80", "coolant_flow_percent": 100,
    "film_cooling_percent": 0, "coolant_inlet_temp": 300, "max_wall_temp": 800,
    "min_throttle": 40, "max_burn_duration": 18, "safety_factor": 2.5,
    "engine_life_cycles": 10,
}


def _i18n():
    return Path('hrma/static/js/i18n_common.js').read_text(encoding='utf-8')


def _panel():
    return Path('hrma/static/js/fea_panel.js').read_text(encoding='utf-8')


class TestKalem2MSivi15:

    def test_yuksek_dalinin_nedeni_dayanim_bayragindan(self):
        s = _panel()
        i = s.index("TF('fea.badgeEngineSf',")
        govde = s[i:i + 1600]
        assert 'why: (derate === true)' in govde
        assert "'fea.engineWhyNoThermal'" in govde
        assert "'fea.engineWhyNoThermalNoDerate'" in govde
        t = _i18n()
        assert t.count("'fea.badgeEngineSf':") == 2
        for satir in t.splitlines():
            if "'fea.badgeEngineSf':" in satir:
                assert '{why}' in satir
                # Eski çelişen beyan ('derate edildi' rozetinin yanında
                # 'dayanım düşürme modellenmiyor') kalktı.
                assert 'strength derating are not modelled' not in satir
                assert 'dayanım düşüşü burada modellenmiyor' not in satir

    def test_L2_oran_dusuk_ve_derate_ayni_tanim(self, client):
        f = _fea(client, _motor(client, '/calculate_liquid', SIVI_L2))
        mk = f['meta']['motor_sf_karsilastirmasi']
        assert mk['kopru_akma_derate_edildi'] is True
        # FEA motorun altında: rozet 'düşük' dalına girer (oran < 1).
        assert mk['oran_kopru_bolu_motor'] < 1.0

    def test_L2_nozul_cidari_adiyla(self, client):
        from hrma.export.cad_visualization import (
            NOZZLE_WALL_MIN_MM, NOZZLE_WALL_THROAT_FRACTION)
        f = _fea(client, _motor(client, '/calculate_liquid', SIVI_L2))
        n = f['nozzle_wall']
        # V306/UÇUŞ-FEA (ek kalem 7): V306/SIVI-MODEL kalem 3 (055365567,
        # 4 Kas) tek katmanlı sıvı cidarda nozul cidarını motorun kamara
        # cidarı olarak YAYIMLIYOR (``nozzle_geometry.wall_thickness``,
        # künye SINGLE_WALL_NOZZLE_WALL_BASIS) ki CAD aynı nozulu çizsin.
        # Eski beklenti CAD'in 3 mm üreteç kuralına düştüğü hâli
        # (``drawing_rule``, iki sayı) kilitliyordu. Artık FEA ağı ile CAD
        # nozul cidarı TEK sayı: kaynak 'published', iki kalınlık eşit.
        # Bekçinin sorusu (nozul cidarı adıyla; kaynak ve sayı rozette)
        # değişmedi; iki rozet anahtarı da panelde duruyor.
        assert n['resolved'] is True and n['same'] is True
        assert n['cad_source'] == 'published'
        assert n['fea_thickness_m'] == pytest.approx(
            f['scalars']['wall_thickness_m'])
        assert n['cad_thickness_m'] == pytest.approx(n['fea_thickness_m'])
        assert n['rule_min_mm'] == NOZZLE_WALL_MIN_MM
        assert n['rule_throat_fraction'] == NOZZLE_WALL_THROAT_FRACTION
        s = _panel()
        assert "'fea.badgeNozzleWallRule'" in s
        assert "'fea.badgeNozzleWallPublished'" in s

    def test_iki_katmanda_nozul_cidari_ayni(self, sivi_fea):
        n = sivi_fea['nozzle_wall']
        assert n['cad_source'] == 'two_layer_stack' and n['same'] is True


# ---------------------------------------------------------------------------
# Kalem 4 — Basınçlı Kap paneli iki katmanlı sıvıda dış kabuk katmanı
# ---------------------------------------------------------------------------
class TestKalem4KapPaneli:

    def test_tohum_dis_kabuk_katmanindan(self):
        s = Path('hrma/static/js/panels/vessel_panel.js').read_text(
            encoding='utf-8')
        i = s.index('function basincKatmani')
        govde = s[i:i + 1600]
        for alan in ('mdp_bar', 'inner_radius_mm', 'thickness_mm',
                     'mean_temperature_K', 'material_key'):
            assert alan in govde
        assert "x.role === 'closeout'" in govde
        j = s.index('fromResults: function')
        fr = s[j:j + 4000]
        assert 'out.meop_bar = kat.mdp_bar;' in fr
        assert 'out.inner_diameter_mm = kat.inner_diameter_mm;' in fr
        assert "'NASA-STD-5012C'" in s

    def test_ipuclari_tohumu_soyluyor(self):
        t = _i18n()
        for anahtar in ('meop_bar', 'inner_diameter_mm', 'wall_thickness_mm',
                        'material', 'temperature_K'):
            satirlar = [x for x in t.splitlines()
                        if f"'panel.vessel.help.{anahtar}':" in x]
            assert len(satirlar) == 2
            assert any('two-layer' in x for x in satirlar)
            assert any('katmanlı rejeneratif' in x for x in satirlar)
        assert 'auto_sized in the result' not in t


# ---------------------------------------------------------------------------
# Kalem 5 — SF renk çubuğu başlığı çizim alanını ezmez
# ---------------------------------------------------------------------------
class TestKalem5RenkCubugu:

    def test_cubukta_kisa_etiket_not_grafigin_altinda(self):
        s = _panel()
        i = s.index("const cbar = T('fea.cbarSf', 'Safety factor [-]');")
        govde = s[i:i + 700]
        assert "els.sfNote.textContent = TF('fea.cbarSfAnchored'" in govde
        assert 'id="fea_sf_note"' in s
        assert "sfNote: document.getElementById('fea_sf_note')" in s
        t = _i18n()
        assert "'fea.cbarSf': 'Safety factor [-]'" in t
        assert "'fea.cbarSf': 'Emniyet katsayısı [-]'" in t
