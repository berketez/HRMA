"""V306/GÜVERTE-HATA bekçileri — güverte panellerinin motorla ve kendi
içinde çelişmesi (3.0.6 bakım hattı, 4 Kas 2026).

Kalem 1 (CI-SÜREÇ DEVİR 1 + K2-P5): Yapısal sekme cidar sıcaklığını motorun
cidar çözümünden alır; motor yayımlamıyorsa gaz sıcaklığından TAHMİN ETMEZ
(adlı "değerlendirilmedi"); dayanım ısı zincirinin ortam referansında
okunur; motorun kendi cidar denetimi sekmenin sayısının yanında, fark
adıyla. Kalem 2 (K2-P2): öneri satırı cidarın gerçek kaynağını söyler.

Ölçüm ve kanıt: docs/scofield/raw/OH/V306/guverte/ (RAPOR.md).
"""
import json
import re

import pytest

import tests.test_v3_yapi_sf as T


def _metin(html):
    return ' '.join(re.sub(r'<[^>]*>', ' ', html or '').split())


@pytest.fixture(scope='module')
def kati(tmp_path_factory):
    import os
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('hrma_projeler_gv')))
    return T._json_guvenli(T._sivi_kati_yanit('solid', {}))


_BAGLAM_EV = (
    "var spec = window.AnalysisDock._registry.filter(function (s) {"
    "  return s.id === 'structural'; })[0];"
    "try { window.AnalysisDock.init({motorType: body.motorType,"
    "  resultsProvider: function () { return body.motor; }}); } catch (e) {}"
    "spec.fromResults(body.motor);"
    "return {ctx: spec.contextFromResults(body.motor)};")


def _baglam(tur, motor):
    import shutil
    import subprocess
    from tests.support.kanit import kanit_gerekli
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: bağlam ölçümü koşamaz (gerekçeli atlama)')
    cfg = {'panelId': '_yok',
           'panelFiles': ['hrma/static/js/panels/structural_panel.js'],
           'dataInline': {'motorType': tur, 'motor': motor},
           'evalFn': _BAGLAM_EV}
    p = subprocess.run([node, kanit_gerekli(str(T._PANEL_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=180)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)['evaled']['ctx'] or {}


def _uc(yuk):
    from hrma.app import app
    r = app.test_client().post('/analyze_structural_safety', json=yuk)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return T._json_guvenli(r.get_json())


# ---------------------------------------------------------------------------
# Kalem 1 — sıcaklık tanımı: gaz sıcaklığı tahmini yok
# ---------------------------------------------------------------------------
def test_cozulmus_cift_yokken_gaz_sicakligi_tohumlanmaz(kati):
    ev = T._dock_node('solid', kati)
    sug = ev['suggested']
    # Ön koşul: motor gaz sıcaklığını yayımlıyor ama cidar çifti yok.
    assert isinstance(kati['chamber_temperature'], float)
    assert sug.get('wall_temperature_hot') in (None, '')
    assert sug.get('chamber_temperature') is None
    assert 'chamber_temperature' not in T._dock_yuku(ev['fields'], sug)


def test_cozulmus_cift_varken_gaz_sicakligi_motorunki():
    """Sıvı örnek (rejeneratif, çözülmüş cidar): çift tohumlanır, gaz
    sıcaklığı motorunkiyle aynı sayıdır (etkisizdir: uç çifti önce okur)."""
    motor = T._json_guvenli(T._sivi_kati_yanit('liquid', {}))
    sug = T._dock_node('liquid', motor)['suggested']
    assert isinstance(sug['wall_temperature_hot'], float)
    assert sug['chamber_temperature'] == motor['chamber_temperature']


def test_ornek_kati_sekme_motorun_sicaklik_tanimiyla(kati):
    """Örnek katı (A36, 2 mm, 40 bar): sekme cidarı gaz sıcaklığından
    tahmin etmez; dayanım motorun kasa denetimindekiyle AYNI sayıdır, iki
    SF'nin oranı yalnız tasarım basıncı katsayısıdır."""
    d = T._dock_akisi('solid', kati)
    sa = d['uc']['structural_analysis']
    th, ca = sa['thermal_analysis'], sa['chamber_analysis']
    blok = kati['structural_analysis']['case_analysis']
    assert th['wall_temperature_source'] == 'not_evaluated'
    assert th['strength_reference_temperature_K'] == pytest.approx(293.15)
    assert ca['yield_strength_used_MPa'] == pytest.approx(
        blok['yield_strength_mpa'], rel=1e-12)
    f = sa['design_parameters']['design_pressure_factor']
    assert ca['pressure_hoop_stress'] == pytest.approx(
        blok['hoop_stress_mpa'] * f, rel=1e-9)
    assert ca['hoop_safety_factor'] == pytest.approx(
        blok['safety_factor'] / f, rel=1e-9)
    m = d['metin']
    assert 'ESTIMATED FROM GAS TEMPERATURE' not in m
    assert 'not estimated from the gas temperature' in m


def test_motorun_cidar_denetimi_yan_yana_fark_adiyla(kati):
    d = T._dock_akisi('solid', kati)
    m = d['metin']
    blok = kati['structural_analysis']['case_analysis']
    assert 'Same wall in the motor result' in m
    assert 'Motor result — hoop SF /calculate_solid %.2f' % blok[
        'safety_factor'] in m
    assert ('Load: the motor result takes the hoop stress at the chamber '
            'pressure 40.0 bar; this tab takes it at the design pressure '
            '60.0 bar (1.50 × chamber pressure).') in m
    # Dayanım ve cidar aynı: fark satırı yalnız yük.
    assert 'Strength: motor yield' not in m
    assert 'Wall: motor' not in m


def test_uc_sicaklik_yokken_dayanim_ortam_referansinda():
    """Uç: sıcaklık girdisi yokken dayanım ısı zincirinin ortam
    varsayılanında (293,15 K, düşürme yok); sıcaklık verilince alan yok."""
    from hrma.app import THERMAL_AMBIENT_DEFAULT_K
    from hrma.data.materials_db import build_materials_view
    govde = {'chamber_pressure': 40, 'chamber_diameter': 0.085,
             'chamber_length': 0.4, 'throat_diameter': 0.018,
             'wall_thickness': 0.002, 'material': 'ss_304'}
    uc = _uc(govde)
    sa = uc['structural_analysis']
    kayit = build_materials_view()['ss_304']['yield_strength'] / 1e6
    assert sa['chamber_analysis']['yield_strength_used_MPa'] == (
        pytest.approx(kayit, rel=1e-12))
    assert sa['thermal_analysis']['strength_reference_temperature_K'] == (
        THERMAL_AMBIENT_DEFAULT_K)
    sicak = _uc(dict(govde, wall_temperature_hot=500.0,
                     wall_temperature_cold=490.0))
    assert 'strength_reference_temperature_K' not in sicak[
        'structural_analysis']['thermal_analysis']


# ---------------------------------------------------------------------------
# Kalem 2 — K2-P2: öneri satırı cidarın gerçek kaynağını söyler
# ---------------------------------------------------------------------------
def test_kullanici_cidari_oneri_satiri_kullanilmadi_der(kati):
    ev = T._dock_node('solid', kati)
    yuk = T._dock_yuku(ev['fields'], ev['suggested'])
    yuk['wall_thickness'] = 0.003          # kullanıcı panele 3 mm yazdı
    for k, v in _baglam('solid', kati).items():
        yuk.setdefault(k, v)
    uc = _uc(yuk)
    assert uc['design_basis']['wall_thickness_source'] == 'user_supplied'
    m = _metin(T._dock_node('solid', kati, uc)['html'])
    assert 'not_used · Not used in this run: the wall evaluated (3.000 mm)' in m
    assert "motor result's wall (2.000 mm)" in m
    assert 'where HRMA sized it' not in m
    assert "the motor's own structural verdict" not in m


def test_motor_hukmu_cumlesi_yalniz_benimsenince(kati):
    """Bağlamsız akışta uç hükmü benimsemez → cümle yok; bağlamla (gerçek
    güverte akışı) benimser → cümle var."""
    d = T._dock_akisi('solid', kati)
    assert d['uc']['structural_analysis']['safety_analysis'].get(
        'verdict_source') != 'motor_structural_chain'
    assert "the motor's own structural verdict" not in d['metin']
    ev = T._dock_node('solid', kati)
    yuk = T._dock_yuku(ev['fields'], ev['suggested'])
    for k, v in _baglam('solid', kati).items():
        yuk.setdefault(k, v)
    uc = _uc(yuk)
    assert uc['structural_analysis']['safety_analysis'][
        'verdict_source'] == 'motor_structural_chain'
    m = _metin(T._dock_node('solid', kati, uc)['html'])
    assert ('applied · Wall thickness taken from the motor result, where '
            "HRMA sized it; it is not a wall you supplied. The verdict shown "
            "is the motor's own structural verdict.") in m


# ---------------------------------------------------------------------------
# Kalem 3/5 — ön dolum: gösterim yuvarlanır, hesaba giden değer TAM
# ---------------------------------------------------------------------------
def _js_islev(dosya, ad):
    """Ürün dosyasından tek işlevin kaynağı (gövde yalıtılıp koşar)."""
    kaynak = (T.REPO_ROOT / dosya).read_text(encoding='utf-8')
    bas = kaynak.index('function %s(' % ad)
    derinlik, i = 0, kaynak.index('{', bas)
    while True:
        if kaynak[i] == '{':
            derinlik += 1
        elif kaynak[i] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[bas:i + 1]
        i += 1


@pytest.mark.parametrize('dosya,ad,im', [
    ('hrma/static/js/analysis_dock.js', 'tamOnDolumDegeri', 'suggested'),
    ('hrma/static/js/panels/feed_panel.js', 'tamTohumDegeri', 'seeded')])
def test_on_dolum_tam_degeri_tasir(dosya, ad, im):
    import shutil
    import subprocess
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: işlev ölçümü koşamaz (gerekçeli atlama)')
    betik = _js_islev(dosya, ad) + '''
    function el(value, d) { return {value: value, dataset: d}; }
    const tam = 11798.436198441237, kutu = 11798.4;
    const IM = %s;
    const out = {
      dokunulmadi: %s(el('11798.4', Object.assign({fullValue: String(tam),
          shownValue: '11798.4'}, IM)), kutu),
      elle: %s(el('11798.4', Object.assign({fullValue: String(tam),
          shownValue: '11798.4', dirty: '1'}, IM)), kutu),
      kutu_degisti: %s(el('12000', Object.assign({fullValue: String(tam),
          shownValue: '11798.4'}, IM)), 12000),
      im_yok: %s(el('11798.4', {fullValue: String(tam),
          shownValue: '11798.4'}), kutu),
    };
    process.stdout.write(JSON.stringify(out));
    ''' % ('{%s: "1"}' % im, ad, ad, ad, ad)
    p = subprocess.run([node], input=betik, capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    o = json.loads(p.stdout)
    assert o['dokunulmadi'] == 11798.436198441237
    assert o['elle'] == 11798.4
    assert o['kutu_degisti'] == 12000
    assert o['im_yok'] == 11798.4


def test_on_dolum_tam_deger_baglanti_noktalari():
    """İşlevler gerçekten bağlı: dock buildPayload ve öneri yazımı, besleme
    readForm ve tohum yazımı (gösterim U.sigFig)."""
    dock = (T.REPO_ROOT / 'hrma/static/js/analysis_dock.js').read_text(
        encoding='utf-8')
    bp = dock[dock.index('function buildPayload('):]
    bp = bp[:bp.index('\n    }\n')]
    assert 'payload[key] = tamOnDolumDegeri(el, v);' in bp
    assert 'el.dataset.fullValue = String(v);' in dock
    feed = (T.REPO_ROOT / 'hrma/static/js/panels/feed_panel.js').read_text(
        encoding='utf-8')
    assert 'payload[key] = tamTohumDegeri(el, v);' in feed
    assert 'el.value = gosterimDegeri(v);' in feed
    assert 'el.value = v; el.dataset.seeded' not in feed


# ---------------------------------------------------------------------------
# Kalem 3 — Termal Koruma: sıvıda motorun çifti; hibritte çapraz denetim
# ---------------------------------------------------------------------------
_KORUMA_EV = (
    "var spec = window.AnalysisDock._registry.filter(function (s) {"
    "  return s.id === 'protection'; })[0];"
    "try { window.AnalysisDock.init({motorType: body.motorType,"
    "  resultsProvider: function () { return body.motor; }}); } catch (e) {}"
    "var sug = spec.fromResults(body.motor);"
    "var out = {suggested: sug, fields: spec.fields, html: null};"
    "function topla(n) { var h = n.innerHTML || '';"
    "  (n.children || []).forEach(function (c) { h += topla(c); });"
    "  return h; }"
    "if (body.endpoint) { var root = document.createElement('div');"
    "  spec.render(body.endpoint, root); out.html = topla(root); }"
    "return out;")


def _koruma_node(tur, motor, endpoint=None):
    import shutil
    import subprocess
    from tests.support.kanit import kanit_gerekli
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: panel ölçümü koşamaz (gerekçeli atlama)')
    cfg = {'panelId': '_yok',
           'panelFiles': ['hrma/static/js/panels/protection_panel.js'],
           'dataInline': {'motorType': tur, 'motor': motor,
                          'endpoint': endpoint},
           'evalFn': _KORUMA_EV}
    p = subprocess.run([node, kanit_gerekli(str(T._PANEL_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=180)
    assert p.returncode == 0, p.stderr[-2000:]
    ev = json.loads(p.stdout)['evaled']
    assert not ev.get('_err'), ev.get('_err')
    return ev


def test_sivi_koruma_motorun_bogaz_ciftini_okur():
    motor = T._json_guvenli(T._sivi_kati_yanit('liquid', {}))
    gsa = motor['heat_transfer_analysis']['gas_side_analysis']
    sug = _koruma_node('liquid', motor)['suggested']
    assert sug['h_gas_W_m2K'] == gsa['gas_side_coefficient_throat']
    assert sug['T_recovery_K'] == gsa['T_recovery_K']
    # Aynı istasyon: q = h·(T_r − T_w) motorun kendi akısı.
    cs = motor['cooling_system']
    assert sug['q_net_W_m2'] == pytest.approx(cs['peak_heat_flux'] * 1e3)
    assert sug['h_gas_W_m2K'] * (sug['T_recovery_K'] - cs[
        'wall_temperature_hot']) == pytest.approx(sug['q_net_W_m2'],
                                                   rel=1e-9)


def _koruma_akisi(tur, motor, yuvarla):
    from hrma.app import app
    ev = _koruma_node(tur, motor)
    yuk = T._dock_yuku(ev['fields'], ev['suggested'])
    yuk['mode'] = 'ablative'
    yuk.pop('q_star_MJ_kg', None)
    yuk.pop('emissivity', None)
    if yuvarla:   # eski davranış: alana 6 anlamlı basamak yazılıp gidiyordu
        yuk = {k: (float('%.6g' % v) if isinstance(v, float) else v)
               for k, v in yuk.items()}
    r = app.test_client().post('/api/thermal-protection', json=yuk)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    uc = T._json_guvenli(r.get_json())
    return _metin(_koruma_node(tur, motor, uc)['html'])


@pytest.mark.parametrize('tur', ['hybrid', 'liquid'])
def test_koruma_capraz_denetimi_tam_degerle_kazanilir(tur):
    from tests.test_v3_yapi_sf import _sivi_kati_yanit
    if tur == 'hybrid':
        from tests.test_example_projects import (HEADERS, NAMES,
                                                 calculate_payload)
        from hrma.app import app
        with open(T.REPO_ROOT / 'examples' / (NAMES['hybrid'] + '.hrma'),
                  encoding='utf-8') as f:
            fields = json.load(f)['inputs']['fields']
        motor = app.test_client().post(
            '/calculate', json=calculate_payload('hybrid', fields),
            headers=HEADERS).get_json()
    else:
        motor = _sivi_kati_yanit('liquid', {})
    motor = T._json_guvenli(motor)
    if tur == 'hybrid':
        # Ön koşul (K2-P3 ölçümü): 6 basamağa yuvarlanmış çiftle panelin
        # kendi çapraz denetimi hükmü kazanılmamış sayıyordu.
        assert 'this verdict is not earned' in _koruma_akisi(
            tur, motor, yuvarla=True)
    yeni = _koruma_akisi(tur, motor, yuvarla=False)
    assert 'this verdict is not earned' not in yeni
    assert 'both read from' in yeni


# ---------------------------------------------------------------------------
# Kalem 6 — §5 B-N1: profil ⟷ ağ malzemesi denetimi köprüde (tek yer)
# ---------------------------------------------------------------------------
_HIBRIT_FEA = {
    'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'expansion_ratio': 4.0,
    'nozzle_type': 'conical', 'chamber_material': 'steel_4130',
    'wall_thickness': 5,
}


@pytest.fixture(scope='module')
def fea_motor_ve_profil():
    from hrma.app import app
    c = app.test_client()
    h = {'Host': '127.0.0.1:8080'}
    motor = c.post('/calculate', json=_HIBRIT_FEA, headers=h).get_json()[
        'motor']
    profil = c.post('/api/analysis/wall-profile', json={
        'chamber_pressure': motor['chamber_pressure'],
        'chamber_temperature': motor['chamber_temperature'],
        'chamber_diameter': motor['chamber_diameter'],
        'chamber_length': motor['chamber_length'],
        'burn_time': motor['burn_time'],
        'mdot_total': motor['mdot_total'],
        'throat_diameter': motor['throat_diameter'],
        'exit_diameter': motor['exit_diameter'],
        'expansion_ratio': motor['expansion_ratio'],
        'nozzle_type': 'conical', 'material': 'steel_4130',
        'wall_thickness': 0.005}, headers=h).get_json()['wall_profile']
    return motor, profil


def test_kopru_dogrudan_cagrida_malzeme_uyusmazligini_reddeder(
        fea_motor_ve_profil):
    """Köprü doğrudan çağrılınca (uç yok) da red; girdi çıkarımı reddettiği
    için çözücü hiç çağrılmaz (çıkarım redli sonucu AYNEN döner)."""
    from hrma.fea import bridge
    motor, profil = fea_motor_ve_profil
    assert profil.get('material') == 'steel_4130'
    girdi = bridge.extract_thermal_inputs(motor, axial_profile=profil)
    assert girdi['reason_code'] == (
        bridge.BRIDGE_REASON_PROFILE_MATERIAL_MISMATCH)
    sonuc = bridge.run_thermal_from_motor(
        motor, axial_profile=profil, ambient_temperature_K=293.15,
        n_axial=12, n_radial=4, max_halvings=3)
    assert sonuc['status'] == bridge.BRIDGE_STATUS_NOT_MODELLED
    assert sonuc['reason_code'] == (
        bridge.BRIDGE_REASON_PROFILE_MATERIAL_MISMATCH)
    assert sonuc['profile_material'] == 'steel_4130'
    assert sonuc['expected_material'] != 'steel_4130'
    assert sonuc['missing'] == ['axial_profile.material']
    assert sonuc['warning']['code'] == (
        bridge.WARN_THERMAL_PROFILE_MATERIAL_MISMATCH)
    assert 'T_final_K' not in sonuc and 'mesh' not in sonuc
    # Aynı malzemeyle beyan edilen profil bu kapıdan geçer.
    ayni = dict(profil, material=sonuc['expected_material'])
    assert bridge.extract_thermal_inputs(
        motor, axial_profile=ayni).get('reason_code') is None


def test_uc_ayni_422_sozlesmesini_koprunun_reddinden_kurar(
        fea_motor_ve_profil):
    from hrma.app import app
    motor, profil = fea_motor_ve_profil
    r = app.test_client().post('/api/fea/thermal', json={
        'motor': motor, 'axial_profile': profil,
        'ambient_temperature_K': 293.15, 'n_axial': 12, 'n_radial': 4,
        'max_halvings': 3}, headers={'Host': '127.0.0.1:8080'})
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'axial_profile_material_mismatch'
    assert j['invalid_fields'][0]['value'] == 'steel_4130'
    assert 'fea' not in j


def test_uc_cozumden_sonra_ikinci_denetim_tasimaz():
    kaynak = (T.REPO_ROOT / 'hrma' / 'app.py').read_text(encoding='utf-8')
    bas = kaynak.index('def api_fea_thermal(')
    govde = kaynak[bas:kaynak.index('\n@app.route', bas)]
    # Uyuşmazlık metni yalnız köprünün reddini çeviren dalda (1 kez).
    assert govde.count("'differs_from_mesh_material'") == 1
    assert 'fea_bridge.BRIDGE_REASON_PROFILE_MATERIAL_MISMATCH' in govde


# ---------------------------------------------------------------------------
# Kalem 4 — K2-P21: sıvı güverte malzeme ön dolumu motorun katmanlarından
# ---------------------------------------------------------------------------
_TOHUM_EV = (
    "var out = {}; window.AnalysisDock._registry.forEach(function (s) {"
    "  if (body.ids.indexOf(s.id) < 0) return;"
    "  try { window.AnalysisDock.init({motorType: body.motorType,"
    "    resultsProvider: function () { return body.motor; }}); }"
    "  catch (e) {}"
    "  out[s.id] = s.fromResults(body.motor); });"
    "return out;")


def test_sivi_astar_malzemesi_motorun_katmanindan():
    import shutil
    import subprocess
    from tests.support.kanit import kanit_gerekli
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: tohum ölçümü koşamaz (gerekçeli atlama)')
    motor = T._json_guvenli(T._sivi_kati_yanit('liquid', {}))
    cs = motor['structural_analysis']['chamber_structure']
    astar = [k for k in cs['wall_layers'] if k.get('role') == 'liner'][0]
    cfg = {'panelId': '_yok',
           'panelFiles': ['hrma/static/js/panels/cooling_panel.js',
                          'hrma/static/js/panels/thermal_panel.js'],
           'dataInline': {'motorType': 'liquid', 'motor': motor,
                          'ids': ['cooling', 'thermal']},
           'evalFn': _TOHUM_EV}
    p = subprocess.run([node, kanit_gerekli(str(T._PANEL_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=180)
    assert p.returncode == 0, p.stderr[-2000:]
    ev = json.loads(p.stdout)['evaled']
    # Ön koşul: astar ⟷ kabuk farklı malzeme (örnek: CuCrZr ⟷ Inconel 718).
    assert astar['material_key'] != cs['material_key']
    assert ev['cooling']['wall_material'] == astar['material_key']
    assert ev['thermal']['material'] == astar['material_key']
