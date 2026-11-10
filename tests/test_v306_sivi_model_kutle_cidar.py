"""V306/SIVI-MODEL kalem 3-5 — kaynaksız kütle çarpanları, enjektör tek kaynak,
çözülmeyen sıcak cidar sıcaklığı.

Kalem 3 (FİZİK-2 DEVİR 3): tek katmanlı cidarda kamara x 1,20 ve lüle cidarı
x 0,60 (+ 30° koni) kaynaksızdı. ÖLÇÜLDÜ (``docs/scofield/raw/OH/V306/
sivi-model/once.json``, örnek gövde film soğutma): motor kamara 1,197 kg ⟷
CAD 0,998 kg; lüle 0,754 kg ⟷ CAD 1,810 kg (CAD 3 mm üreteç kuralı + grafit
yedeği). Artık iki cidar modeli de çizilen geometriden, CAD'in tek işlevinden;
tek katmanda lüle cidarı = kamara cidarı (künye: ince cidar çember gerilmesi,
tutucu üst sınır), lüle malzemesi = kamara malzemesi, ikisi de yayımlanır.

Kalem 4 (FİZİK-2 DEVİR 3): enjektör motor 1,02 kg (cidar x kaynaksız 1,5,
dolu disk) ⟷ CAD 0. Artık plaka yalnız uçtaki Roark plaka denetimi
boyutlandırdıysa tartılır (motor = CAD = ``plate_mass_kg``); boyutlanmadıysa
ikisi de tartmaz ve adıyla (``not_weighed``).

Kalem 5: ışınımsal soğutmada sıcak cidar ışınım dengesinden ÇÖZÜLÜR (Sutton &
Biblarz Böl. 8.6); film/dump/ablatifte çözülmez, bağlı hükümler geçerlilik
etiketi + uyarıyla.
"""
import contextlib
import copy
import io
import math
import pathlib

import pytest

import hrma.engines.liquid_rocket_engine as LRE
from hrma.export import cad_visualization as CV
from tests.support import kabul

KOK = pathlib.Path(__file__).resolve().parents[1]
H = {'Host': '127.0.0.1:8080'}
I18N_C = (KOK / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
I18N_P = (KOK / 'hrma/static/js/i18n_pages.js').read_text(encoding='utf-8')


def _sessiz(fn, *a, **k):
    t = io.StringIO()
    with contextlib.redirect_stdout(t), contextlib.redirect_stderr(t):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _sivi(client, **ek):
    govde = dict(kabul.sayfa_yuku('liquid'), **ek)
    r = _sessiz(client.post, '/calculate_liquid', json=govde, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _cad(s):
    r = _sessiz(CV.MotorCADDesigner().generate_3d_motor_assembly,
                copy.deepcopy(s))
    return r['performance_summary']['mass_breakdown']


@pytest.fixture(scope='module')
def film(client):
    return _sivi(client, cooling_type='film_cooling', film_cooling_percent=10)


@pytest.fixture(scope='module')
def ornek(client):
    return _sivi(client)


@pytest.fixture(scope='module')
def ornek_plaka(client):
    return _sivi(client, injector_material='stainless_steel')


@pytest.fixture(scope='module')
def radyatif(client):
    return _sivi(client, cooling_type='radiative')


@pytest.fixture(scope='module')
def ablatif_hedefsiz(client):
    return _sivi(client, cooling_type='ablative', max_wall_temp=None)


# ---------------------------------------------------------------- kalem 3
def test_kaynaksiz_carpanlar_kalkti():
    for ad in ('CHAMBER_MASS_JOINT_FACTOR', 'NOZZLE_WALL_THICKNESS_RATIO',
               'INJECTOR_PLATE_THICKNESS_RATIO'):
        assert not hasattr(LRE, ad), ad


def test_tek_katman_dokum_cad_ile_ayni(film):
    cs = film['component_sizing']
    assert cs['drawn_mass_single_source']['status'] == 'applied'
    cm = cs['component_masses']
    mb = _cad(film)
    assert cm['combustion_chamber'] == pytest.approx(mb['chamber_mass'],
                                                     rel=1e-12)
    assert cm['nozzle_assembly'] == pytest.approx(mb['nozzle_mass'],
                                                  rel=1e-12)


def test_tek_katman_kamara_bagimsiz_halka_hacmi(film):
    """Kâhin: π·L·((r+t)² − r²)·ρ, flanş/çarpan YOK."""
    from hrma.export.motor_geometry import normalise_export_geometry
    md, _ = normalise_export_geometry(copy.deepcopy(film))
    d = float(md['chamber_diameter'])
    L = float(md['chamber_length'])
    t = CV._chamber_wall_design(md)['thickness_m']
    _k, _n, rho, _s = CV._chamber_material_resolved(md)
    beklenen = math.pi * L * ((d / 2 + t) ** 2 - (d / 2) ** 2) * rho
    assert film['component_sizing']['component_masses'][
        'combustion_chamber'] == pytest.approx(beklenen, rel=1e-9)


def test_tek_katman_lule_cidari_kamara_cidari_ve_malzemesi(film):
    from hrma.export.motor_geometry import normalise_export_geometry
    md, _ = normalise_export_geometry(copy.deepcopy(film))
    t_kamara_mm = CV._chamber_wall_design(md)['thickness_m'] * 1000.0
    ng = film['nozzle_geometry']
    assert ng['wall_thickness'] == pytest.approx(t_kamara_mm, rel=1e-12)
    assert 'sigma = p*r/t' in ng['wall_thickness_basis']
    assert film['nozzle_material'] == 'cucrzr'
    # CAD artık üreteç kuralı / grafit yedeğiyle değil, bu cidarla tartar.
    noz = CV._nozzle_wall_design(md)
    assert noz['published'] is True
    rho, kaynak = CV._nozzle_density_resolved(md)
    assert 'as selected by this run' in kaynak


def test_iki_katman_degismedi_tek_kaynak(ornek):
    cs = ornek['component_sizing']
    assert cs['two_layer_mass_single_source']['status'] == 'applied'
    assert 'drawn_mass_single_source' not in cs
    assert 'nozzle_geometry' not in ornek or not ornek['nozzle_geometry']


# ---------------------------------------------------------------- kalem 4
def test_plaka_yoksa_motor_ve_cad_tartmaz(ornek):
    cs = ornek['component_sizing']
    cm = cs['component_masses']
    assert cm['injector_assembly'] is None
    kayit = [k for k in cs['not_weighed'] if k['key'] == 'injector_assembly']
    assert len(kayit) == 1 and 'Roark' in kayit[0]['basis']
    # Uçuş aracı kalemi DEĞİL: araç listesine girmez.
    assert [k['key'] for k in cs['not_in_engine_dry_mass']] == [
        'controls_avionics']
    assert _cad(ornek)['injector_mass'] == 0.0
    parca = sum(cm[k] for k in ('combustion_chamber', 'nozzle_assembly',
                                'turbopump_assembly', 'feed_system'))
    assert cm['total_dry_mass'] == pytest.approx(parca, rel=1e-12)
    assert ornek['engine_mass_estimate'] == cm['total_dry_mass']


def test_plaka_boyutlaninca_motor_cad_ve_plaka_ayni_sayi(ornek_plaka):
    ps = ornek_plaka['injector_plate_structural']
    assert ps['status'] == 'sized'
    cm = ornek_plaka['component_sizing']['component_masses']
    assert cm['injector_assembly'] == pytest.approx(ps['plate_mass_kg'],
                                                    rel=1e-6)
    assert _cad(ornek_plaka)['injector_mass'] == pytest.approx(
        ps['plate_mass_kg'], rel=1e-12)
    # Bağımsız: ρ·(π·a² − n·π·(d/2)²)·t.
    from hrma.data.materials_db import get_material
    rho = get_material(ps['material_key'])['density']
    a = ps['plate_diameter_mm'] / 2000.0
    n = ps['n_holes']
    dh = ps['hole_diameter_mm'] / 1000.0
    t = ps['required_thickness_mm'] / 1000.0
    beklenen = rho * (math.pi * a * a - n * math.pi * (dh / 2) ** 2) * t
    assert cm['injector_assembly'] == pytest.approx(beklenen, rel=1e-9)
    assert ornek_plaka['component_sizing']['not_weighed'] == []
    g0 = 9.80665
    assert ornek_plaka['thrust_to_weight'] == pytest.approx(
        ornek_plaka['thrust'] / (cm['total_dry_mass'] * g0), rel=1e-9)


def test_tartilmayan_enjektor_satiri_iki_dilde():
    html = (KOK / 'hrma/templates/liquid.html').read_text(encoding='utf-8')
    assert "T('liq.msg.injector_not_weighed'" in html
    assert I18N_P.count("'liq.msg.injector_not_weighed':") == 2


# ---------------------------------------------------------------- kalem 5
def test_isinimsal_cidar_cozulur(radyatif):
    cool = radyatif['cooling_system']
    rad = radyatif['thermal_protection']['passive_thermal_protection'][
        'radiation_equilibrium']
    assert cool['wall_temperature_solved_K'] == rad['T_wall_eq_K']
    assert cool['wall_temperature_solved_status'] == 'SOLVED'
    assert 'radiation equilibrium' in cool['wall_temperature_solved_source']
    # Hedef 800 K, denge ~2745 K: limit hükmü çözülen sayıyla.
    assert cool['wall_temperature_limit_status'] == 'EXCEEDED'
    yapi = radyatif['structural_analysis']['chamber_structure']
    assert 'radiation equilibrium' in str(yapi.get('wall_temperature_source'))
    kodlar = {w.get('code') for w in radyatif.get('input_warnings') or []
              if isinstance(w, dict)}
    assert 'warn.liquid.radiative_wall_above_melting' in kodlar
    assert 'warn.liquid.solved_wall_above_melting' not in kodlar
    assert 'warn.liquid.wall_temperature_assumed_target' not in kodlar


def test_ablatif_hedefsiz_gecerlilik_etiketi(ablatif_hedefsiz):
    cool = ablatif_hedefsiz['cooling_system']
    v = cool['wall_temperature_validity']
    assert v['status'] == 'ASSUMED_NOT_SOLVED'
    assert v['temperature_source'] == 'cooling_type_default'
    assert v['temperature_K'] == LRE.WALL_TEMP_DEFAULT_K['ablative']
    assert cool['wall_temperature_solved_K'] is None
    kodlar = [w.get('code') for w in ablatif_hedefsiz.get('input_warnings')
              or [] if isinstance(w, dict)]
    assert kodlar.count('warn.liquid.wall_temperature_assumed_default') == 1


def test_rejeneratifte_etiket_ve_uyari_yok(ornek):
    assert 'wall_temperature_validity' not in ornek['cooling_system']
    kodlar = {w.get('code') for w in ornek.get('input_warnings') or []
              if isinstance(w, dict)}
    assert not {c for c in kodlar if 'wall_temperature_assumed' in str(c)}


@pytest.mark.parametrize('kod', [
    'warn.liquid.wall_temperature_assumed_target',
    'warn.liquid.wall_temperature_assumed_default',
    'warn.liquid.radiative_wall_above_melting',
    'warn.liquid.radiative_wall_above_allowable'])
def test_uyari_metinleri_iki_dilde(kod):
    assert I18N_C.count("'%s':" % kod) == 2


# ---------------------------------------------------------------- kalem 6
#: K2-P4: örnek O/F 2,1'de dökülme yerinde KRİTİK olgu uyarı listesinde iki
#: kez (kodlu input_warnings + marşın düz metni; TR iki farklı cümle).
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

NODE = shutil.which('node')


@pytest.fixture(scope='module')
def of21(client):
    return _sivi(client, mixture_ratio=2.1)


def _js_blok(kaynak, bas):
    i = kaynak.index(bas)
    ac = '[' if bas.lstrip().startswith('const ') and '= [' in \
        kaynak[i:i + 200] else '{'
    kap = ']' if ac == '[' else '}'
    j = kaynak.index(ac, i)
    d = 0
    for k in range(j, len(kaynak)):
        if kaynak[k] == ac:
            d += 1
        elif kaynak[k] == kap:
            d -= 1
            if d == 0:
                return kaynak[i:k + 1]
    raise AssertionError(bas)


def _derin(results):
    html = (KOK / 'hrma/templates/liquid.html').read_text(encoding='utf-8')
    blok = (_js_blok(html, 'const LIQUID_DEEP_WARNING_PATHS') + '\n'
            + _js_blok(html, 'function liquidDeepWarnings(results)'))
    betik = ("function T(k, f) { return f; }\nfunction TF(k, p, f) "
             "{ return f; }\nfunction numTxt(v) { return String(v); }\n"
             "const window = {};\n%s\nprocess.stdout.write("
             "JSON.stringify(liquidDeepWarnings(%s)));\n"
             % (blok, json.dumps(results)))
    out = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


def test_dokulme_olgusu_kodlu_tek_uyari(of21):
    kodlu = [w for w in of21['input_warnings'] if isinstance(w, dict)
             and w.get('code') == 'warn.liquid.deposit_spall_above_melting']
    assert len(kodlu) == 1
    march = of21['thermal_protection']['station_march']
    yk = [k for k in march['promoted_warnings']
          if k['code'] == 'warn.liquid.deposit_spall_above_melting']
    assert len(yk) == 1
    assert yk[0]['params'] == kodlu[0]['params']
    assert yk[0]['text'] in march['warnings']   # kart kaydı korunur


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_liste_yukseltilen_mars_metnini_tekrar_basmaz(of21):
    derin = _derin(of21)
    yk = {k['text'] for k in of21['thermal_protection']['station_march'][
        'promoted_warnings']}
    assert not [w for w in derin if isinstance(w, str) and w in yk]
    # Yükseltilmeyen marş notları (ör. KARBON BİRİKİMİ beyanı) kalır.
    assert any(isinstance(w, str) and w.startswith('CARBON DEPOSIT')
               for w in derin)


def test_kart_yukseltilen_hukmu_kodlu_cumleyle_basar():
    html = (KOK / 'hrma/templates/liquid.html').read_text(encoding='utf-8')
    i = html.index('const kodluEs = Object.create(null);')
    blok = html[i:i + 1500]
    assert 'liquidWarnText({ code: es.code, params: es.params || {} })' in blok
