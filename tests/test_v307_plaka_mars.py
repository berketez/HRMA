"""V307/PLAKA-MARŞ — enjektör plakası marş/kesme yük durumu (19 Kas 2026).

Model kararı (ana model, Astra danışmasıyla; kanıt
``docs/scofield/raw/OH/V307/plaka-mars/``): iki yük durumu, AYNI işlev
(``injector_plate_structural``):

* çalışma: q = ΔP_inj (Huzel & Huang, NASA SP-125 s. 129, Denk. 4-43);
* marş/kesme: q = P_man − P_amb,min, P_man = P_c + ΔP_inj (Denk. 4-44,
  mutlak), P_amb,min = 0 bar (vakum, HRMA seçimi).

Sıvıda plaka iki gereksinimin büyüğüyle standart levhaya boyutlanır; hüküm
iki durumun en düşük SF'si; motor kuru kütlesi ve CAD aynı kalınlığı okur.
Hibritte kalınlık girdidir: hüküm en düşük SF; pintle yüz plakası yöneten
gereksinime boyutlanır.
"""
import contextlib
import copy
import io
import math
import pathlib
import re

import pytest

from tests.support.kabul import hesap_ucu, post, sayfa_yuku

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAKA_MALZEMESI = 'stainless_steel'


def _cagir(motor, **ek):
    from hrma.app import app
    g = copy.deepcopy(sayfa_yuku(motor))
    g['injector_material'] = PLAKA_MALZEMESI
    for k, v in ek.items():
        if v is None:
            g.pop(k, None)
        else:
            g[k] = v
    with contextlib.redirect_stdout(io.StringIO()):
        d, y, _h, _t = post(app.test_client(), hesap_ucu(motor), g)
    assert d == 200, (d, (y or {}).get('error'), (y or {}).get('message'))
    return g, y


@pytest.fixture(scope='module')
def sivi():
    return _cagir('liquid')


@pytest.fixture(scope='module')
def hibrit():
    return _cagir('hybrid')


def _kahin_kalinlik(b, q_bar):
    """Roark 11.2 / 10b: t = sqrt(0,75 q a² SF / (σ_y η)) [mm]."""
    a = b['plate_diameter_mm'] / 2000.0
    t = math.sqrt(0.75 * q_bar * 1e5 * a ** 2 * b['required_safety_factor']
                  / (b['yield_strength_MPa'] * 1e6 * b['ligament_efficiency']))
    return t * 1000.0


def _kahin_sf(b, q_bar, t_mm):
    a = b['plate_diameter_mm'] / 2000.0
    t = t_mm / 1000.0
    sigma = 0.75 * q_bar * 1e5 * a ** 2 / (t ** 2 * b['ligament_efficiency'])
    return b['yield_strength_MPa'] * 1e6 / sigma


# ---------------------------------------------------------------------------
# Sıvı: iki yük durumu, yöneten durumla standart levha, hüküm en düşük SF
# ---------------------------------------------------------------------------
def test_sivi_iki_yuk_durumu_ayni_islevle_ve_dogru_yukle(sivi):
    g, y = sivi
    b = y['injector_plate_structural']
    assert b['status'] == 'analyzed', b
    det = y['injection_system']['injector_design_detail']
    dp = max(det['ox_circuit']['delta_p_bar'],
             det['fuel_circuit']['delta_p_bar'])
    lc = b['load_cases']
    assert set(lc) == {'operating', 'startup_shutdown'}
    assert lc['operating']['delta_P_bar'] == pytest.approx(dp, abs=5e-5)
    # Marş/kesme: mutlak manifold basıncı (P_c + ΔP) eksi vakum.
    p_man = float(g['chamber_pressure']) + dp
    assert b['manifold_pressure_bar'] == pytest.approx(p_man, rel=1e-12)
    assert b['ambient_pressure_bar'] == 0.0
    assert lc['startup_shutdown']['delta_P_bar'] == pytest.approx(
        p_man - 0.0, abs=5e-5)
    for ad, kayit in lc.items():
        assert kayit['required_thickness_mm'] == pytest.approx(
            _kahin_kalinlik(b, kayit['delta_P_bar']), rel=2e-3), ad
        assert kayit['safety_factor'] == pytest.approx(
            _kahin_sf(b, kayit['delta_P_bar'], b['plate_thickness_mm']),
            rel=2e-3), ad


def test_sivi_plaka_yoneten_gereksinimle_standart_levhaya_boyutlanir(sivi):
    from hrma.engines.liquid_rocket_engine import STANDARD_WALL_THICKNESS_MM
    _g, y = sivi
    b = y['injector_plate_structural']
    lc = b['load_cases']
    gerek = max(k['required_thickness_mm'] for k in lc.values())
    assert b['governing_load_case'] == 'startup_shutdown'
    assert b['required_thickness_mm'] == pytest.approx(gerek)
    # Gereksinimin üstündeki İLK standart levha.
    beklenen = min(s for s in STANDARD_WALL_THICKNESS_MM if s >= gerek)
    assert b['plate_thickness_mm'] == pytest.approx(beklenen)
    assert b['plate_thickness_source'] == 'next_standard_plate'
    # Hüküm: iki durumun en düşük SF'si; ikisi de hedefi tutar.
    assert b['safety_factor'] == min(k['safety_factor'] for k in lc.values())
    assert all(k['meets_target'] for k in lc.values())
    assert b['safety_factor'] >= b['required_safety_factor']
    assert b['warnings'] == []
    # Üst düzey satır yöneten durumun satırıdır (ΔP, gerilme, SF aynı yük).
    assert b['delta_P_bar'] == lc['startup_shutdown']['delta_P_bar']
    assert b['bending_stress_MPa'] == lc['startup_shutdown'][
        'bending_stress_MPa']


def test_sivi_kuru_kutle_ve_cad_ayni_plaka(sivi):
    """Tek kalınlık: yanıt = motor kuru kütlesi = CAD (çizim + kütle)."""
    from hrma.data.materials_db import get_material
    from hrma.export.cad_visualization import _injector_plate_design
    _g, y = sivi
    b = y['injector_plate_structural']
    cad = _injector_plate_design(y)
    assert cad['thickness_m'] * 1000.0 == pytest.approx(
        b['plate_thickness_mm'], abs=1e-12)
    rho = float(get_material(b['material_key'])['density'])
    a = b['plate_diameter_mm'] / 2000.0
    d = b['hole_diameter_mm'] / 1000.0
    v = (math.pi * a * a - b['n_holes'] * math.pi * (d / 2.0) ** 2) \
        * b['plate_thickness_mm'] / 1000.0
    cm = y['component_sizing']['component_masses']
    assert cm['injector_assembly'] == pytest.approx(rho * v, rel=1e-4)
    assert cad['mass_kg'] == pytest.approx(cm['injector_assembly'],
                                           rel=1e-6)
    assert b['plate_mass_kg'] == pytest.approx(cm['injector_assembly'],
                                               rel=1e-6)


def test_sivi_kunye_iki_durumu_ve_kaynagi_yazar(sivi):
    _g, y = sivi
    b = y['injector_plate_structural']
    kunye = b['load_cases_basis']
    for parca in ('SP-125', 'p. 129', 'Eq. 4-43', 'Eq. 4-44', 'yield',
                  'hydraulic ram', 'thermal stress', 'fatigue',
                  'dynamic amplification', 'reverse pressure difference',
                  'N2O', 'SP-8089', 'page not verified'):
        assert parca in kunye, parca
    assert 'start/shutdown' in b['model_basis']
    assert 'vacuum' in b['ambient_pressure_basis']


# ---------------------------------------------------------------------------
# Hibrit: kalınlık girdi, hüküm en düşük SF; pintle yöneten gereksinime
# ---------------------------------------------------------------------------
def test_hibrit_hukum_iki_durumun_en_dusuk_sf_si(hibrit):
    g, y = hibrit
    inj = y['injector']
    b = inj['plate_structural']
    lc = b['load_cases']
    assert b['status'] == 'analyzed'
    assert b['plate_thickness_mm'] == pytest.approx(g['plate_thickness'])
    # P_besleme: denetlenen çözümün orifis üstü basıncı (tank DEĞİL).
    assert b['manifold_pressure_bar'] == inj['injector_inlet_pressure_bar']
    assert lc['startup_shutdown']['delta_P_bar'] == pytest.approx(
        inj['injector_inlet_pressure_bar'], abs=5e-5)
    assert lc['operating']['delta_P_bar'] == pytest.approx(
        inj['pressure_drop'], abs=5e-5)
    assert b['safety_factor'] == min(k['safety_factor'] for k in lc.values())
    assert b['governing_load_case'] == 'startup_shutdown'
    for ad, kayit in lc.items():
        assert kayit['safety_factor'] == pytest.approx(
            _kahin_sf(b, kayit['delta_P_bar'], b['plate_thickness_mm']),
            rel=2e-3), ad
    # Hedefin altındaki HER durum uyarıda adıyla durur.
    uyarilar = [w for w in inj['warnings'] if 'Injector plate' in w]
    for ad, etiket in (('operating', 'operating'),
                       ('startup_shutdown', 'start/shutdown')):
        if not lc[ad]['meets_target']:
            assert any(f'in the {etiket} load case' in w for w in uyarilar), (
                ad, uyarilar)


def test_hibrit_pintle_yuz_plakasi_yoneten_gereksinime_boyutlanir():
    _g, y = _cagir('hybrid', injector_type='pintle', plate_thickness=None)
    b = y['injector']['plate_structural']
    if b.get('status') != 'analyzed':
        pytest.fail(f'pintle plakası analiz edilmedi: {b.get("reason")}')
    lc = b['load_cases']
    gerek = max(k['required_thickness_mm'] for k in lc.values())
    assert b['plate_thickness_source'] == 'sized_to_target_safety_factor'
    assert b['plate_thickness_mm'] == pytest.approx(gerek, abs=2e-3)
    assert b['safety_factor'] >= b['required_safety_factor']
    assert all(k['meets_target'] for k in lc.values())
    # Motor bloğuna (CAD'in okuduğu) aynı kalınlık iner.
    assert y['motor']['injector_design']['plate_thickness_mm'] == \
        b['plate_thickness_mm']


# ---------------------------------------------------------------------------
# Yardımcının sınır davranışları (doğrudan çağrı)
# ---------------------------------------------------------------------------
def _yardimci_cagir(q_ust=None):
    from hrma.utils.injector_design import injector_plate_structural
    props = {'yield_strength': 240e6, 'density': 8000.0, 'name': 'test'}

    def cagir(q, t):
        return injector_plate_structural(
            delta_P_bar=q, plate_diameter_m=0.13, material_props=props,
            material_name='test', plate_thickness_m=t, n_holes=200,
            hole_diameter_m=0.0013, required_sf=2.5)
    return cagir


def test_manifold_basinci_yoksa_yarim_yukle_hukum_kurulmaz():
    from hrma.app import _enjektor_plaka_iki_durum
    r = _enjektor_plaka_iki_durum(_yardimci_cagir(), 20.0, None, None,
                                  boyutla='standard')
    assert r['status'] == 'not_analyzed'
    assert 'start/shutdown' in r['reason'] and 'safety_factor' not in r


def test_tablonun_ustunde_gereksinim_kendisi_ve_hedef_tutar():
    from hrma.app import _enjektor_plaka_iki_durum
    from hrma.engines.liquid_rocket_engine import STANDARD_WALL_THICKNESS_MM
    # 150 mm tablonun üstüne çıkaran yük (q ∝ t²).
    r = _enjektor_plaka_iki_durum(_yardimci_cagir(), 4000.0, 9000.0, 'test',
                                  boyutla='standard')
    assert r['status'] == 'analyzed'
    assert r['plate_thickness_mm'] > max(STANDARD_WALL_THICKNESS_MM)
    assert r['plate_thickness_source'] == 'governing_requirement'
    assert all(k['meets_target'] for k in r['load_cases'].values())


def test_sicak_yol_yuk_yuvarlanmis_yapraktan_kurulmaz():
    """Marş yükü girdinin kendisinden: P_man − 0 (yuvarlama zinciri yok)."""
    from hrma.app import _enjektor_plaka_iki_durum
    r = _enjektor_plaka_iki_durum(_yardimci_cagir(), 20.123456, 70.123456,
                                  'test', plaka_m=0.01)
    assert r['manifold_pressure_bar'] == 70.123456
    assert r['injector_pressure_drop_bar'] == 20.123456
    assert r['load_cases']['startup_shutdown']['delta_P_bar'] == round(
        70.123456, 4)


# ---------------------------------------------------------------------------
# Ekran: sıvı sayfası iki durumu EN + TR gösterir
# ---------------------------------------------------------------------------
PLAKA_MARS_ANAHTARLARI = ('liq.ui.injplate_analyzed', 'liq.ui.injplate_case_startup',
                   'liq.ui.injplate_case_operating', 'liq.ui.injplate_src_std',
                   'liq.ui.injplate_src_req')


def test_sivi_sayfasi_analiz_dalini_iki_durumla_basar():
    html = (ROOT / 'hrma' / 'templates' / 'liquid.html').read_text(
        encoding='utf-8')
    blok = html[html.index('function showLiquidInjectorPlate'):]
    blok = blok[:blok.index('function liqOptNum')]
    assert "b.status === 'analyzed'" in blok
    for alan in ('load_cases.operating', 'load_cases.startup_shutdown',
                 'manifold_pressure_bar', 'governing_load_case',
                 'plate_thickness_mm', 'plate_thickness_source'):
        assert alan in blok, alan
    for anahtar in PLAKA_MARS_ANAHTARLARI:
        assert f"'{anahtar}'" in blok, anahtar


def test_yeni_anahtarlar_en_ve_tr_sozlukte_ve_yer_tutucular_esit():
    js = (ROOT / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
        encoding='utf-8')
    for anahtar in PLAKA_MARS_ANAHTARLARI:
        degerler = re.findall(r"'" + re.escape(anahtar) + r"': '((?:[^'\\]|\\.)*)'",
                              js)
        assert len(degerler) == 2, (anahtar, len(degerler))
        en, tr = degerler
        assert en != tr, anahtar
        assert sorted(re.findall(r'\{\w+\}', en)) == sorted(
            re.findall(r'\{\w+\}', tr)), anahtar
    tr_metin = re.findall(r"'liq.ui.injplate_analyzed': '((?:[^'\\]|\\.)*)'",
                          js)[1]
    assert 'Marş/kesme' in tr_metin and 'çalışma' in tr_metin.lower()


# ---------------------------------------------------------------------------
# PDF: sıvı ve hibrit plaka tablosu (yanıtın bloğundan; yeniden hesap yok)
# ---------------------------------------------------------------------------
def _pdf_metinleri(parcalar):
    return ' '.join(str(getattr(p, 'text', '') or '') for p in parcalar)


def test_pdf_plaka_bolumleri_yalniz_iki_durumlu_blokta(sivi, hibrit):
    from hrma.export.pdf_generator import PDFReportGenerator
    gen = PDFReportGenerator()
    _g, ys = sivi
    _g, yh = hibrit
    s = gen._liquid_injector_plate_rows(ys)
    h = gen._create_hybrid_injector_plate_section(yh)
    assert s and h
    assert 'two load cases' in _pdf_metinleri(s)
    assert 'design input' in _pdf_metinleri(h)
    # Blok yoksa (malzeme seçilmedi) bölüm basılmaz.
    assert gen._liquid_injector_plate_rows({}) == []
    assert gen._create_hybrid_injector_plate_section({'injector': {}}) == []


def test_pdf_plaka_anahtarlari_en_ve_tr_rapor_sozlugunde():
    js = (ROOT / 'hrma' / 'static' / 'js' / 'i18n_report.js').read_text(
        encoding='utf-8')
    anahtarlar = sorted(set(re.findall(r"'(report\.inj\.plate_[a-z_]+)':", js)))
    assert len(anahtarlar) >= 18, anahtarlar
    for anahtar in anahtarlar:
        assert js.count(f"'{anahtar}':") == 2, anahtar
