"""V301 / L-REJ bekçileri — sıvı rejeneratif soğutmada soğutucu tarafı.

Berke (26 Eki 2026): "Modeli bugün düzelt." Kanıt ve önce/sonra tabloları:
``docs/scofield/raw/OH/V301/kati-sivi/L-REJ/RAPOR.md``.

(a) Kanat (fin) oranı RP-1 yolunda uygulanır, > 1'dir (boğazda) ve TEK
    işlevden gelir (``RegenCooling._fin_ratio``; süperkritik yol da onu
    çağırır).
(b) Ürün yolunda RP-1 istasyon marşı, motorun ``cooling_system`` bloğunda
    yayımladığı kanalı çözer (sayı, genişlik, yükseklik, sıcak cidar,
    kaburga, pürüzlülük).
(c) Sieder-Tate (mu_b/mu_w)^0,14 çarpanı sıvı soğutucuda uygulanır
    (NASA SP-125 Eş. 4-23), süperkritik yolda uygulanmaz.
(d) Kamara boyu ceket uzunluğuna girer (marşa giden ``chamber_length`` =
    ``cooling_system.chamber_length``).
(e) Metan/LH2 süperkritik marşı bit-aynı (taban a95ed4b60'ta ölçülen
    çapalar, rel 1e-12); hibrit/katı yolu L-REJ işlevlerine HİÇ uğramaz.
(f) NK-36: besleme bütçesindeki ceket kalemi tank basıncı/çevrim dengesiyle
    aynı sayıdır ve yakıt toplamına girer.
"""

import ast
import contextlib
import io
import json
import os
import pathlib
import warnings

import pytest

KOK = pathlib.Path(__file__).resolve().parent.parent


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **k)


def _rp1(**over):
    """Doğrudan RP-1 marşı (örnek sıvı motora yakın ölçek, bakır alaşımı)."""
    from hrma.analysis.regen_cooling import RegenCooling
    kw = dict(chamber_pressure=70e5, chamber_temperature=3500.0, gamma=1.2,
              molecular_weight=22.0, throat_diameter=0.055,
              expansion_ratio=12.0, coolant='rp1', coolant_mdot=2.8,
              coolant_inlet_temp=300.0, coolant_inlet_pressure=80e5,
              n_channels=38, channel_width=3.0e-3, channel_height=2.0e-3,
              wall_thickness=1.0e-3, wall_material='cucrzr', n_stations=40)
    kw.update(over)
    return RegenCooling(**kw)


# ---------------------------------------------------------------------------
# (a) kanat oranı RP-1 yolunda, tek işlevden
# ---------------------------------------------------------------------------
def test_a_rp1_kanat_orani_bogazda_birden_buyuk():
    r = _rp1().solve()
    ti = r['throat_index']
    assert r['fin_area_ratio'][ti] > 1.0
    assert r['summary']['fin_effect'] is True
    assert r['summary']['fin_area_ratio_max'] == pytest.approx(
        max(r['fin_area_ratio']), rel=0, abs=0)
    # seri devre kanat oranıyla kapanır: q = h_c * A_r * (T_wc - T_b)
    for i in range(r['n_stations']):
        q = r['q_MW_m2'][i] * 1e6
        assert q == pytest.approx(
            r['h_coolant_W_m2K'][i] * r['fin_area_ratio'][i]
            * (r['T_wall_cold_K'][i] - r['T_coolant_K'][i]), rel=1e-4)


def test_a_rp1_kanat_kapaliyken_oran_bir_ve_cidar_daha_sicak():
    acik = _rp1().solve()
    kapali = _rp1(fin_effect=False).solve()
    assert set(kapali['fin_area_ratio']) == {1.0}
    ti = acik['throat_index']
    assert acik['T_wall_hot_K'][ti] < kapali['T_wall_hot_K'][ti]


def test_a_kanat_orani_tek_islevden():
    """fin_area_ratio YALNIZ RegenCooling._fin_ratio içinde çağrılır; sıvı
    ve süperkritik denge işlevleri ile solve() _fin_ratio'yu çağırır."""
    from hrma.analysis import regen_cooling as rc
    agac = ast.parse(pathlib.Path(rc.__file__).read_text(encoding='utf-8'))
    sinif = next(n for n in agac.body
                 if isinstance(n, ast.ClassDef) and n.name == 'RegenCooling')

    def cagrilar(dugum, ad):
        return [c for c in ast.walk(dugum) if isinstance(c, ast.Call)
                and ((isinstance(c.func, ast.Name) and c.func.id == ad)
                     or (isinstance(c.func, ast.Attribute)
                         and c.func.attr == ad))]

    yontemler = {f.name: f for f in sinif.body
                 if isinstance(f, ast.FunctionDef)}
    fin_cagiran = sorted(ad for ad, f in yontemler.items()
                         if cagrilar(f, 'fin_area_ratio'))
    assert fin_cagiran == ['_fin_ratio'], fin_cagiran
    for ad in ('_station_wall_balance_sc', '_station_wall_balance_liquid',
               'solve'):
        assert cagrilar(yontemler[ad], '_fin_ratio'), ad


# ---------------------------------------------------------------------------
# Ürün yolu: örnek sıvı motor, marş kurucusunun argümanları yakalanır
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def urun(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('l_rej_proj')))
    from hrma.analysis import regen_cooling as rc
    from hrma.app import app
    app.config['TESTING'] = True
    istemci = app.test_client()
    alan = json.loads((KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma')
                      .read_text(encoding='utf-8'))['inputs']['fields']
    sonuc = {}
    asil = rc.RegenCooling

    class Yakala(asil):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            sonuc.setdefault('kurulan', []).append(self)

    for ad, ek in (('ornek', {}),
                   ('cucrzr', {'chamber_material': 'cucrzr',
                               'chamber_wall_thickness': 1.0})):
        sonuc['kurulan'] = []
        rc.RegenCooling = Yakala
        try:
            yuk = dict(alan)
            yuk.update(ek)
            r = _sessiz(istemci.post, '/calculate_liquid', json=yuk,
                        headers={'Host': '127.0.0.1:8080'})
        finally:
            rc.RegenCooling = asil
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        sonuc[ad] = (r.get_json(), list(sonuc['kurulan']))
    return sonuc


@pytest.mark.parametrize('ad', ['ornek', 'cucrzr'])
def test_b_mars_motor_kanal_geometrisi_ayni(urun, ad):
    from hrma.engines.liquid_rocket_engine import (
        COOLING_CHANNEL_ROUGHNESS_DEFAULT_M)
    j, kurulan = urun[ad]
    cs = j['cooling_system']
    fit = cs['channel_count_fit']
    assert len(kurulan) == 1          # tek RP-1 marşı
    rc = kurulan[0]
    assert rc.coolant == 'rp1'
    assert rc.n_channels == cs['cooling_channels'] == fit['n_used']
    assert rc.channel_width * 1e3 == pytest.approx(cs['channel_width_mm'],
                                                   rel=1e-12)
    assert rc.channel_height * 1e3 == pytest.approx(cs['channel_height_mm'],
                                                    rel=1e-12)
    assert rc.wall_thickness * 1e3 == pytest.approx(
        fit['hot_wall_thickness_mm'], rel=1e-12)
    assert rc.land_width * 1e3 == pytest.approx(fit['land_width_mm'],
                                                rel=1e-12)
    # pürüzlülük: toplu zincirin ΔP'sine giren değerle aynı (form
    # varsayılanı; eskiden marş modülün 5 µm varsayılanını kullanıyordu)
    assert rc.wall_roughness == COOLING_CHANNEL_ROUGHNESS_DEFAULT_M
    # künye marşın çözdüğü geometriyi adıyla yazar
    not_ = j['thermal_protection']['station_march']['model_note']
    assert f"Channel geometry solved: {cs['cooling_channels']} channels" in not_


def test_c_sieder_tate_sivida_uygulanir():
    from hrma.analysis.regen_cooling import (
        dittus_boelter_nu, rp1_properties, sieder_tate_factor,
        SIEDER_TATE_EXPONENT)
    assert SIEDER_TATE_EXPONENT == 0.14
    rc = _rp1()
    r = rc.solve()
    st = r['sieder_tate_factor']
    assert max(st) > 1.0
    assert r['dittus_boelter_envelope']['sieder_tate_correction_applied'] \
        is True
    assert 'Sieder-Tate wall-viscosity factor' in r['model_note']
    for i in range(r['n_stations']):
        p = rp1_properties(r['T_coolant_K'][i])
        h_db = (dittus_boelter_nu(r['reynolds'][i], p['prandtl'])
                * p['conductivity'] / rc.hydraulic_diameter)
        assert r['h_coolant_W_m2K'][i] == pytest.approx(h_db * st[i],
                                                        rel=1e-9)
    # el çapası: mu_b 1,0e-3 / mu_w 0,42e-3 -> (2,381)^0,14
    assert sieder_tate_factor(1.0e-3, 0.42e-3) == pytest.approx(
        (1.0 / 0.42) ** 0.14, rel=1e-15)
    with pytest.raises(ValueError):
        sieder_tate_factor(1.0e-3, 0.0)


def test_c_sieder_tate_superkritik_yolda_yok():
    from tests.test_regen_cooling_supercritical import make_methane
    r = make_methane().solve()
    assert 'sieder_tate_factor' not in r


def test_d_kamara_boyu_ceket_uzunluguna_girer(urun):
    j, kurulan = urun['ornek']
    cs = j['cooling_system']
    md = kurulan[0].motor_data
    assert md['chamber_length'] * 1e3 == pytest.approx(cs['chamber_length'],
                                                       rel=1e-12)
    not_ = j['thermal_protection']['station_march']['model_note']
    assert 'covers the cylindrical chamber barrel' in not_
    assert 'NOZZLE CONTOUR ONLY' not in not_


def test_d_govde_toplam_isiyi_artirir_bogazi_degistirmez():
    gov = _rp1(motor_data={'chamber_length': 0.25}).solve()
    yok = _rp1().solve()
    assert gov['summary']['total_heat_W'] > 1.5 * yok['summary'][
        'total_heat_W']
    # ters akışta gövde boğazdan SONRA gelir: boğaz tepe cidarı ızgara
    # gürültüsü mertebesinde aynı kalır
    assert gov['T_wall_hot_K'][gov['throat_index']] == pytest.approx(
        yok['T_wall_hot_K'][yok['throat_index']], rel=2e-3)


# ---------------------------------------------------------------------------
# (e) süperkritik yol bit-aynı; hibrit/katı L-REJ işlevlerine uğramaz
# ---------------------------------------------------------------------------
#: Taban a95ed4b60'ta (L-REJ öncesi) ÖLÇÜLDÜ — docs/.../L-REJ/RAPOR.md §md5.
SC_CAPALAR = {
    'methane': (1057.2783005946026, 1344815.3430798522, 174.05437600718602,
                9.135178496834431, 2.115637615786378),
    'raptor': (1081.2408889085796, 53875677.794251345, 255.21958515463328,
               294.38551151855023, 1.5162788260806828),
    'hydrogen': (1196.226485195169, 1233324.1874353616, 191.51127439563462,
                 1.934790740256682, 2.3462329648497326),
}


@pytest.mark.parametrize('ad', sorted(SC_CAPALAR))
def test_e_superkritik_mars_bit_ayni(ad):
    import tests.test_regen_cooling_supercritical as T
    r = {'methane': lambda: T.make_methane(),
         'raptor': lambda: T.make_raptor(),
         'hydrogen': lambda: T.make_methane(
             coolant='hydrogen', coolant_inlet_temp=40.0,
             coolant_inlet_pressure=120e5, coolant_mdot=0.5)}[ad]()
    s = _sessiz(r.solve)['summary']
    olculen = (s['max_wall_hot_K'], s['total_heat_W'],
               s['coolant_exit_temp_K'], s['total_pressure_drop_bar'],
               s['fin_area_ratio_max'])
    for o, c in zip(olculen, SC_CAPALAR[ad]):
        assert o == pytest.approx(c, rel=1e-12)


def test_e_hibrit_ve_kati_l_rej_islevlerine_ugramaz(tmp_path, monkeypatch):
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(tmp_path))
    from hrma.analysis import regen_cooling as rc
    from hrma.engines import liquid_rocket_engine as lre
    from hrma.app import app
    from tests.test_example_projects import (
        ENDPOINTS, HEADERS, calculate_payload, load_example_doc)

    def patla(*a, **k):
        raise AssertionError('L-REJ yolu hibrit/katı koşumunda çağrıldı')

    for sinif, ad in ((rc.RegenCooling, '_fin_ratio'),
                      (rc.RegenCooling, '_station_wall_balance_liquid'),
                      (lre.LiquidRocketEngine, '_feed_budget_jacket_dp'),
                      (lre.LiquidRocketEngine, '_regen_march_channel_inputs'),
                      (lre.LiquidRocketEngine, '_regen_jacket_motor_data')):
        monkeypatch.setattr(sinif, ad, patla)
    monkeypatch.setattr(rc, 'sieder_tate_factor', patla)
    app.config['TESTING'] = True
    istemci = app.test_client()
    for tip in ('hybrid', 'solid'):
        alan = load_example_doc(tip)['inputs']['fields']
        r = _sessiz(istemci.post, ENDPOINTS[tip],
                    json=calculate_payload(tip, alan), headers=HEADERS)
        assert r.status_code == 200, (tip, r.get_data(as_text=True)[:300])


# ---------------------------------------------------------------------------
# (f) NK-36: besleme bütçesinde ceket kalemi
# ---------------------------------------------------------------------------
def test_f_butce_ceket_kalemi_tek_sayi_ve_toplamda(urun):
    j, _ = urun['ornek']
    dr = j['feed_system']['pressure_drops']
    cs = j['cooling_system']
    assert dr['regen_jacket_drop_status'] == 'computed'
    ceket = dr['fuel_line']['regen_jacket']
    assert ceket == cs['cooling_pressure_drop']
    assert 'regen_jacket' not in dr['oxidizer_line']
    kalemler = ('tank_outlet', 'main_valve', 'filters', 'feed_lines',
                'injector', 'regen_jacket')
    assert dr['total_fuel'] == pytest.approx(
        sum(dr['fuel_line'][k] for k in kalemler), rel=1e-12)
    assert dr['pump_discharge_pressure_fuel'] == pytest.approx(
        j['chamber_pressure'] + dr['total_fuel'], rel=1e-12)
    # çevrim panelinin yakıt pompa çıkışı aynı sayı (iki panel, tek sayı)
    cyc = j['detailed_feed_system']['engine_cycle_solution']
    assert cyc['status'] == 'converged'
    assert cyc['pump_discharge_fuel_bar'] == pytest.approx(
        dr['pump_discharge_pressure_fuel'], rel=1e-9)


def test_f_ceketsiz_tipte_kalem_yok():
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    m = _sessiz(LiquidRocketEngine, thrust=10000.0, chamber_pressure=60.0,
                mixture_ratio=2.4, fuel_type='rp1', oxidizer_type='lox',
                cooling_type='ablative', overrides={})
    _sessiz(m.calculate_nozzle_geometry)
    d = _sessiz(m._calculate_feed_system_pressure_drops)
    assert d['regen_jacket_drop_status'] == 'not_applicable'
    assert 'regen_jacket' not in d['fuel_line']
