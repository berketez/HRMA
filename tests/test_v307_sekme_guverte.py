"""V307/SEKME-GÜVERTE bekçileri — Analiz Güvertesi'nde motorla çelişen sayı
ve hükümler (3.0.7 hattı, 16 Kas 2026).

Kalemler (bulgular: 3.0.6 son kullanıcı turu NK3, 9 Kas):
  K1 NK3-H-1  BASINÇLI KAP sekmesi motorun cidarını almıyordu (hibrit L1:
              GÜVENLİK 253,4 bar ⟷ BASINÇLI KAP 54,5 bar).
  K2 NK3-K-2  YAPISAL sekmesi "Gereken asgari 5,22 mm · UNSAFE · HIGH"
              satırlarında yük tabanını söylemiyordu (motor 2,5'i MEOP'ta,
              sekme 1,5 × MEOP'ta uygular); ham anahtarlar; motorun
              boyutlandırdığı cidar "user_supplied".
  K3 NK3-S-3  TERMAL sekmesi ablatif motorda "SOĞUTMA: NATURAL · Gereken
              soğutma alanı 266,26 m²".
  K4 NK3-H-7  son hesap başarısızken PERFORMANS (ve aynı desende YAPISAL,
              TERMAL, BASINÇLI KAP) gizli varsayılanlarla başka motor
              çözüyordu.
  K5 NK3-S-9  sıvı motorun ısı yükü (Motor Alt Sistemleri) ⟷ TERMAL
              sekmesinin toplam ısı gücü: iki tanım yan yana, adıyla.

Akış gerçektir: örnek projeden motor ucu → panel ``fromResults`` (node,
gerçek panel dosyası) → güvertenin gövde kuralı → güverte ucu → ``render``.
Ölçüm ve kanıt: docs/scofield/raw/OH/V307/sekme-guverte/ (RAPOR.md).
"""
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import tests.test_v3_yapi_sf as T

REPO = Path(__file__).resolve().parents[1]
STATIC_JS = REPO / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None,
                                  reason='node yok: panel ölçümü koşamaz')

PANEL_DOSYALARI = ['hrma/static/js/panels/vessel_panel.js',
                   'hrma/static/js/panels/structural_panel.js',
                   'hrma/static/js/panels/thermal_panel.js',
                   'hrma/static/js/panels/performance_panel.js',
                   'hrma/static/js/panels/safety_panel.js',
                   'hrma/static/js/panels/joint_panel.js',
                   'hrma/static/js/panels/cooling_panel.js']

#: Vakalar: örnek projeler (depoda) + yalnız gereken alan değişiklikleri.
#: sıvı ablatif = NK3-S L1'in sınıfı (ablatif astar, tek cidar, 304 çelik,
#: cidarı HRMA boyutlandırır).
#: Hibrit vaka: NK3-H L1'in çekirdek girdileri (N2O/HTPB, Pc 20 bar,
#: 300 N × 4,7 s, O/F 7,06; cidar alanı YOK → HRMA boyutlandırır). Örnek
#: hibrit proje yük altında ~170 s sürdüğü için (ölçüldü, 16 Kas) doğrudan
#: gövde; öbür alanlar ucun kendi varsayılanları.
HIBRIT_L1_GOVDE = {'motor_name': 'v307sg-h', 'fuel_type': 'htpb',
                   'oxidizer_type': 'n2o', 'thrust': 300, 'burn_time': 4.7,
                   'chamber_pressure': 20, 'of_ratio': 7.06}

SG_VAKALARI = {
    'hibrit': ('hybrid', {'__govde__': HIBRIT_L1_GOVDE}),
    'kati': ('solid', {}),
    # NK3-S L1'in çekirdeği (800 N, Pc 15 bar, ablatif astar, 304 çelik, cidar
    # boş → HRMA boyutlandırır): örnek sıvı projenin alanları üzerine.
    'sivi_abl': ('liquid', {'mixture_ratio': 2.3, 'engine_cycle': 'pressure_fed',
                            'thrust': 800, 'chamber_pressure': 15,
                            'feed_pressure': 25, 'injector_elements': 12,
                            'injector_pressure_drop': 3,
                            'chamber_wall_thickness': None,
                            'chamber_material': 'steel_304',
                            'cooling_type': 'ablative',
                            'nozzle_expansion_ratio': 3.5,
                            'nozzle_type': 'conical',
                            'max_burn_duration': 7.7}),
}


def _motor_yaniti(tur, ek):
    """Örnek projenin GERÇEK motor ucu yanıtı (rotalar literal)."""
    from hrma.app import app
    from tests.test_example_projects import HEADERS, NAMES, calculate_payload
    if '__govde__' in ek:
        yuk = dict(ek['__govde__'])
    else:
        with open(REPO / 'examples' / (NAMES[tur] + '.hrma'),
                  encoding='utf-8') as f:
            fields = json.load(f)['inputs']['fields']
        for anahtar, deger in ek.items():
            if deger is None:
                fields.pop(anahtar, None)
            else:
                fields[anahtar] = deger
        yuk = calculate_payload(tur, fields)
    c = app.test_client()
    if tur == 'hybrid':
        r = c.post('/calculate', json=yuk, headers=HEADERS)
    elif tur == 'solid':
        r = c.post('/calculate_solid', json=yuk, headers=HEADERS)
    else:
        r = c.post('/calculate_liquid', json=yuk, headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return T._json_guvenli(r.get_json())


def _uc(endpoint, yuk):
    """Güverte ucu (rotalar literal)."""
    from hrma.app import app
    c = app.test_client()
    if endpoint == '/api/pressure-vessel-analysis':
        r = c.post('/api/pressure-vessel-analysis', json=yuk)
    elif endpoint == '/analyze_safety':
        r = c.post('/analyze_safety', json=yuk)
    elif endpoint == '/analyze_structural_safety':
        r = c.post('/analyze_structural_safety', json=yuk)
    elif endpoint == '/analyze_thermal_safety':
        r = c.post('/analyze_thermal_safety', json=yuk)
    elif endpoint == '/api/analysis/wall-profile':
        r = c.post('/api/analysis/wall-profile', json=yuk)
    else:
        raise AssertionError('bu bekçide olmayan uç: ' + endpoint)
    return r.status_code, T._json_guvenli(r.get_json(silent=True))


_EV = r"""
var out = {};
body.paneller.forEach(function (pid) {
  var spec = window.AnalysisDock._registry.filter(function (s) {
      return s.id === pid; })[0];
  if (!spec) { out[pid] = {_yok: true}; return; }
  try { window.AnalysisDock.init({motorType: body.motorType,
      resultsProvider: function () { return body.motor; }}); } catch (e) {}
  var r = {fields: spec.fields, required: spec.required || [],
           endpoint: spec.endpoint};
  try { r.suggested = body.motor ? spec.fromResults(body.motor) : null; }
  catch (e) { r._err = String(e.stack || e); }
  if (typeof spec.contextFromResults === 'function' && body.motor) {
    try { r.ctx = spec.contextFromResults(body.motor); } catch (e) { r.ctx = null; }
  }
  if (body.data && body.data[pid]) {
    var root = document.createElement('div');
    try { spec.render(body.data[pid], root); } catch (e) { r._err = String(e.stack || e); }
    var h = '';
    (function walk(n) { h += String(n.innerHTML || '');
      (n.children || []).forEach(walk); })(root);
    r.html = h;
  }
  out[pid] = r;
});
return out;
"""


def _node(tur, motor, paneller, data=None):
    from tests.support.kanit import kanit_gerekli
    if NODE is None:
        pytest.skip('node yok: panel ölçümü koşamaz (gerekçeli atlama)')
    cfg = {'panelId': '_yok', 'panelFiles': PANEL_DOSYALARI,
           'extraFiles': ['hrma/static/js/materials_catalog.js'],
           'dataInline': {'motorType': tur, 'motor': motor,
                          'paneller': paneller, 'data': data},
           'evalFn': _EV}
    p = subprocess.run([NODE, kanit_gerekli(str(T._PANEL_HARNESS))],
                       input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=240)
    assert p.returncode == 0, p.stderr[-2000:]
    ev = json.loads(p.stdout)['evaled']
    for pid in paneller:
        assert not ev[pid].get('_err'), ev[pid].get('_err')
    return ev


def _yuk(spec, sug):
    """analysis_dock.js buildPayload: öneri ezer; seçici aynen; sayı yalnız
    sonluysa; boş zorunlu alan ``eksik``."""
    sug = dict(sug or {})
    sug.pop('__withheld', None)
    out, eksik = {}, []
    beyanli = set(spec.get('required') or [])
    for f in spec['fields']:
        k, var = f[0], f[2]
        v = sug.get(k) if sug.get(k) is not None else var
        if isinstance(f[3], list):
            out[k] = v
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            x = None
        if x is not None and math.isfinite(x):
            out[k] = x
            continue
        if (isinstance(var, (int, float)) and not isinstance(var, bool)) \
                or k in beyanli:
            eksik.append(k)
    for k, v in (spec.get('ctx') or {}).items():
        if k not in out and v is not None:
            out[k] = v
    return out, eksik


def _gorunur(html):
    """Kullanıcının GÖRDÜĞÜ metin: ``hidden`` çapalar ve KAPALI
    ``<details>`` kutularının içeriği (özet satırı kalır) düşer, etiketler
    sökülür. İç içe kutular içten dışa ayıklanır."""
    h = re.sub(r'<span[^>]*\bhidden\b[^>]*>.*?</span>', ' ', html or '',
               flags=re.S)
    ic = re.compile(r'<details(?![^>]*\bopen\b)[^>]*>\s*(<summary.*?</summary>)?'
                    r'(?:(?!<details).)*?</details>', re.S)
    while True:
        yeni = ic.sub(lambda m: ' ' + (m.group(1) or '') + ' ', h)
        if yeni == h:
            break
        h = yeni
    return ' '.join(re.sub(r'<[^>]*>', ' ', h).split())


def _vaka_kur(ad):
    """Bir vakanın tam akışı: motor → dört panel önerisi → uçlar → render."""
    tur, ek = SG_VAKALARI[ad]
    motor = _motor_yaniti(tur, ek)
    ev = _node(tur, motor, ['vessel', 'structural', 'thermal', 'safety'])
    yanit = {}
    for pid in ('vessel', 'structural', 'thermal', 'safety'):
        yuk, eksik = _yuk(ev[pid], ev[pid]['suggested'])
        assert not eksik, (ad, pid, eksik)
        kod, y = _uc(ev[pid]['endpoint'], yuk)
        assert kod == 200, (ad, pid, kod, str(y)[:300])
        yanit[pid] = {'yuk': yuk, 'uc': y, 'oneri': ev[pid]['suggested']}
    ren = _node(tur, motor, ['vessel', 'structural', 'thermal'],
                data={pid: yanit[pid]['uc']
                      for pid in ('vessel', 'structural', 'thermal')})
    for pid in ('vessel', 'structural', 'thermal'):
        yanit[pid]['html'] = ren[pid]['html']
        yanit[pid]['gorunur'] = _gorunur(ren[pid]['html'])
    return {'tur': tur, 'motor': motor, 'panel': yanit}


class _TembelVakalar(dict):
    """Vaka ilk istendiğinde kurulur (modül boyunca bir kez): ``-k`` ile
    seçilen alt küme yalnız gereken motorları hesaplar."""

    def __missing__(self, ad):
        self[ad] = _vaka_kur(ad)
        return self[ad]


@pytest.fixture(scope='module')
def vakalar(tmp_path_factory):
    import os
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('hrma_projeler_v307sg')))
    return _TembelVakalar()


def _motor_cidari_mm(tur, motor):
    """Motorun cidar sayısı — güvertenin ortak okuyucusunun yolları
    (analysis_dock.js WALL_THICKNESS_MM_PATHS)."""
    m = motor.get('motor') or motor
    if tur == 'hybrid':
        return m['heat_transfer_analysis']['design_parameters']['wall_thickness']
    if tur == 'solid':
        return m['structural_analysis']['case_analysis']['wall_thickness_mm']
    return m['structural_analysis']['chamber_structure']['wall_thickness']


# ===========================================================================
# K1 — NK3-H-1: BASINÇLI KAP motorun cidarını değerlendirir
# ===========================================================================
@node_gerekli
@pytest.mark.parametrize('ad', sorted(SG_VAKALARI))
def test_k1_kap_motorun_cidarini_tohumlar(vakalar, ad):
    v = vakalar[ad]
    oneri = v['panel']['vessel']['oneri']
    assert oneri['wall_thickness_mm'] == _motor_cidari_mm(v['tur'], v['motor'])
    uc = v['panel']['vessel']['uc']
    assert uc['auto_sized'] is False
    assert uc['wall_thickness_used_mm'] == pytest.approx(
        _motor_cidari_mm(v['tur'], v['motor']), rel=1e-12)


@node_gerekli
@pytest.mark.parametrize('ad', sorted(SG_VAKALARI))
def test_k1_capraz_kap_ve_guvenlik_ayni_patlama_basinci(vakalar, ad):
    """Çapraz bekçi: aynı motor, iki sekme, TEK öngörülen patlama basıncı."""
    v = vakalar[ad]
    kap = v['panel']['vessel']['uc']['predicted_burst_pressure_bar']
    guv = v['panel']['safety']['uc']['safety_analysis']['pressure_safety'][
        'predicted_burst_pressure_bar']
    assert kap > 0 and guv > 0
    assert kap == pytest.approx(guv, rel=1e-9), (kap, guv)


@node_gerekli
def test_k1_sivi_tek_cidarda_malzeme_motorun(vakalar):
    v = vakalar['sivi_abl']
    mk = v['motor']['structural_analysis']['chamber_structure']['material_key']
    assert v['panel']['vessel']['oneri']['material'] == mk
    assert v['panel']['vessel']['yuk']['material'] == mk


@node_gerekli
def test_k1_baslik_degerlendirilen_cidarin_kimini_soyler(vakalar):
    v = vakalar['hibrit']
    html = v['panel']['vessel']['html']
    assert 'data-vessel-wall-basis="motor"' in html
    mm = _motor_cidari_mm('hybrid', v['motor'])
    assert "EVALUATED WALL — the motor's wall." in v['panel']['vessel']['gorunur']
    assert ("The motor's wall is %.2f mm (HRMA sized it in the motor result)."
            % mm) in v['panel']['vessel']['gorunur']
    # Kullanıcı cidarı boşaltıp otomatik boyutlandırma isterse başlık
    # bunun ÖNERİLEN cidar olduğunu söyler.
    yuk = dict(v['panel']['vessel']['yuk'])
    yuk.pop('wall_thickness_mm')
    kod, oto = _uc('/api/pressure-vessel-analysis', yuk)
    assert kod == 200 and oto['auto_sized'] is True
    ren = _node('hybrid', v['motor'], ['vessel'], data={'vessel': oto})
    gor = _gorunur(ren['vessel']['html'])
    assert 'data-vessel-wall-basis="proposed"' in ren['vessel']['html']
    assert "PROPOSED WALL — this tab sized it" in gor
    assert "it is not the motor's wall" in gor
    assert 'Predicted burst pressure — proposed wall' in gor
    assert 'Proposed wall (this tab)' in gor


# ===========================================================================
# K2 — NK3-K-2: YAPISAL sekme yük tabanı + kaynak + ham anahtar
# ===========================================================================
@node_gerekli
def test_k2_kati_yuk_tabani_ve_motorun_gereken_cidari(vakalar):
    v = vakalar['kati']
    sa = v['panel']['structural']['uc']['structural_analysis']
    dp = sa['design_parameters']
    ca = sa['chamber_analysis']
    blok = v['motor']['structural_analysis']['case_analysis']
    gor = v['panel']['structural']['gorunur']
    html = v['panel']['structural']['html']
    pc = dp['design_pressure'] / dp['design_pressure_factor']
    hedef = ca['design_safety_factor_target']
    # Ön koşul: iki tanım gerçekten farklı (motor MEOP'ta, sekme 1,5 × MEOP).
    assert dp['design_pressure_factor'] == 1.5
    assert ca['minimum_thickness'] > blok['wall_thickness_hoop_required_mm']
    # Tablo başı: sekmenin tabanı, motorun tabanı, manşetin hangisi olduğu.
    assert 'data-structural-load-basis="table"' in html
    assert ('taken at the design pressure %.1f bar = 1.50 × chamber pressure '
            '%.1f bar' % (dp['design_pressure'], pc)) in gor
    assert ('the design SF target %.2f is applied there, which is %.2f on the '
            'chamber pressure' % (hedef, hedef * 1.5)) in gor
    assert ('The motor result applies the same target %.2f at the chamber '
            'pressure %.1f bar (MEOP)' % (hedef, pc)) in gor
    assert "the motor result's own structural verdict" in gor
    # "Gereken asgari" satırı yük tabanını taşır; motorun gereken cidarı
    # yanında, motorun KENDİ sayısıyla.
    i = gor.find('Minimum required')
    assert i >= 0
    assert ('design SF %.2f at the design pressure %.1f bar'
            % (hedef, dp['design_pressure'])) in gor[i:i + 200]
    assert 'data-structural-motor-required="1"' in html
    assert ('Required wall — motor result %.2f mm'
            % blok['wall_thickness_hoop_required_mm']) in gor
    # Ölçülen kesitlerin hükmü (UNSAFE/MARGINAL…) yük tabanıyla.
    if sa['safety_analysis'].get('earned_scope_status'):
        j = gor.find('measured sections:')
        assert j >= 0
        assert 'at the design pressure' in gor[j:j + 160]


@node_gerekli
@pytest.mark.parametrize('ad', sorted(SG_VAKALARI))
def test_k2_motorun_boyutlandirdigi_cidar_user_supplied_degil(vakalar, ad):
    v = vakalar[ad]
    uc = v['panel']['structural']['uc']
    if uc['design_basis'].get('wall_thickness_source') != 'sized_by_hrma':
        pytest.skip('bu vakada cidar motor sonucundan gelmedi')
    ca = uc['structural_analysis']['chamber_analysis']
    assert ca['wall_thickness_source'] == 'sized_by_hrma'
    assert 'user-supplied' not in ca['safety_factor_basis']
    gor = v['panel']['structural']['gorunur']
    html = v['panel']['structural']['html']
    # Bulgunun satırı (NK3-K-2): "wall_thickness_source: user_supplied".
    assert 'wall_thickness_source: user_supplied' not in gor
    assert 'data-structural-wall-source="sized_by_hrma"' in html
    assert 'Evaluated wall' in gor and 'HRMA sized it in the motor result' in gor


#: NK3-K-2 (bulgu metni: "minimum_earned_safety_factor 1,67 · earned_scope_
#: status: UNSAFE · earned_scope_risk_level: HIGH", "design_target_assessment
#: 2,00 · design_safety_factor_target: 2,0", "wall_thickness_source:
#: user_supplied", governing_load_case, hot_soak, thin_wall,
#: applied_axial_stress_pressurized_basis): panelin KENDİ etiket/değer
#: satırlarında makine adı görünmez. (Gerekçe cümlelerinin sonundaki
#: "(kod)" izi ÖK-22 kararıdır — tests/test_d26_arayuz_a2.py; kapalı
#: "değer kaynakları" defteri ve ucun İngilizce cümleleri DİL-KALINTI'ya
#: devredildi, RAPOR.)
K2_HAM_DESEN = (
    r'headline_safety_factor\s+[\d—]', r'minimum_earned_safety_factor\s+[\d—·]',
    r'earned_scope_status:', r'earned_scope_risk_level',
    r'design_target_assessment\s+[\d—]', r'design_safety_factor_target:',
    r'wall_thickness_used_mm\s+\d', r'wall_thickness_source:',
    r'governing_load_case\s+\w', r'applied_axial_stress_pressurized_basis\s*:',
    r'scenario:\s*hot_soak', r'hoop model:\s*thin_wall',
    r'stations_reading_back_target:', r'\bstatus: [A-Z]', r'risk_level: [A-Z]',
    r'\d\s+safety_factor_is_tautological',
    r'binding_safety_factor_is_tautological: true',
)


@node_gerekli
@pytest.mark.parametrize('ad', sorted(SG_VAKALARI))
def test_k2_ham_anahtar_gorunur_metinde_yok(vakalar, ad):
    gor = vakalar[ad]['panel']['structural']['gorunur']
    kalan = [d for d in K2_HAM_DESEN if re.search(d, gor)]
    assert not kalan, [(d, re.search(d, gor).group(0)) for d in kalan]
    # Adres kaybolmadı: makine adı çapada (data-machine-field).
    html = vakalar[ad]['panel']['structural']['html']
    assert 'data-machine-field="minimum_earned_safety_factor"' in html


# ===========================================================================
# K3 — NK3-S-3: TERMAL soğutma tipi motordan; korunan cidarda bütçe yok
# ===========================================================================
@node_gerekli
def test_k3_ablatif_motor_sogutmasi_motordan_butce_yok(vakalar):
    v = vakalar['sivi_abl']
    assert v['motor']['cooling_type'] == 'ablative'
    oneri = v['panel']['thermal']['oneri']
    assert oneri['cooling_type'] == 'ablative'
    assert oneri['wall_protection'] == 'ablative_liner'
    ta = v['panel']['thermal']['uc']['thermal_analysis']
    assert ta['design_parameters']['cooling_type'] == 'ablative'
    assert ta['design_parameters']['bare_wall_outer_cooling'] == 'natural'
    ca = ta['cooling_analysis']
    assert ca['required_cooling_area'] is None
    assert ca['cooling_efficiency'] is None
    assert ca['required_cooling_area_withheld_code'] == 'ablative_cooling_class'
    assert ta['chamber_liner_check']['governs'] is True
    html = v['panel']['thermal']['html']
    gor = v['panel']['thermal']['gorunur']
    assert 'data-thermal-cooling-budget="ablative_cooling_class"' in html
    assert 'COOLING: Ablative Liner' in gor
    assert 'NATURAL' not in gor
    # Alan bütçesi hiçbir yerde m² olarak basılmaz.
    i = gor.find('Required cooling area')
    assert i >= 0 and 'm²' not in gor[i:i + 60]


@node_gerekli
@pytest.mark.parametrize('ad,kod', [('hibrit', 'liner_protected_wall'),
                                    ('kati', 'supplied_wall_temperature')])
def test_k3_korunan_cidar_yonetirken_butce_yayimlanmaz(vakalar, ad, kod):
    ta = vakalar[ad]['panel']['thermal']['uc']['thermal_analysis']
    ca = ta['cooling_analysis']
    assert ca['required_cooling_area'] is None
    assert ca['required_cooling_area_withheld_code'] == kod
    # Gaz tarafı ısı yükü sayı olarak kalır.
    assert ca['peak_heat_rate'] > 0


def _termal_govde(**ek):
    g = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
         'chamber_diameter': 0.05, 'chamber_length': 0.3, 'burn_time': 5.0,
         'mdot_total': 0.4, 'wall_thickness': 0.002, 'material': 'ss_304',
         'throat_diameter': 0.02}
    g.update(ek)
    return g


def test_k3_ablatif_sinif_astarsiz_adiyla_reddedilir():
    kod, y = _uc('/analyze_thermal_safety',
                 _termal_govde(cooling_type='ablative', wall_protection='none'))
    assert kod == 422, y
    assert y['invalid_fields'][0]['reason'] == 'ablative_cooling_requires_liner'


@pytest.mark.parametrize('sinif', ['natural', 'forced', 'regenerative'])
def test_k3_korumasiz_istekte_butce_degismedi(sinif):
    """Bit-aynılık: korunan cidar yokken bütçe eskisi gibi yayımlanır."""
    kod, y = _uc('/analyze_thermal_safety', _termal_govde(cooling_type=sinif))
    assert kod == 200, y
    ca = y['thermal_analysis']['cooling_analysis']
    assert 'required_cooling_area_withheld_code' not in ca
    from hrma.analysis.heat_transfer_analysis import (
        COOLING_DESIGN_DELTA_T, COOLING_EFFICIENCY_BY_TYPE)
    assert ca['cooling_efficiency'] == COOLING_EFFICIENCY_BY_TYPE[sinif]
    assert ca['required_cooling_area'] == pytest.approx(
        ca['peak_heat_rate'] * 1e3 / (ca['coolant_side_coefficient']
                                      * COOLING_DESIGN_DELTA_T[sinif]),
        rel=1e-12)


def test_k3_duvar_profili_ablatif_cidar_siniri_dogal_disla_ayni():
    g = _termal_govde()
    kod_a, a = _uc('/api/analysis/wall-profile', dict(g, cooling_type='ablative'))
    kod_n, n = _uc('/api/analysis/wall-profile', dict(g, cooling_type='natural'))
    assert kod_a == 200 and kod_n == 200, (a, n)
    assert a['motor_cooling_type'] == 'ablative'
    assert a['bare_wall_outer_cooling'] == 'natural'
    assert a['wall_profile']['T_wall_eq'] == n['wall_profile']['T_wall_eq']
    assert 'motor_cooling_type' not in n


# ===========================================================================
# K4 — NK3-H-7: tohum yoksa analiz koşmaz
# ===========================================================================
#: Motordan gelen büyüklükler: tanım değeri BOŞ ve zorunlu (panel, alanlar).
K4_ZORUNLU = {
    'performance': ['chamber_pressure', 'optimal_of_ratio', 'base_isp',
                    'expansion_ratio', 'throat_area', 'chamber_length',
                    'chamber_temperature', 'gamma', 'chamber_diameter'],
    'performance_solid': ['chamber_pressure', 'expansion_ratio',
                          'throat_area', 'chamber_length',
                          'chamber_temperature', 'gamma', 'chamber_diameter'],
    'structural': ['chamber_pressure', 'chamber_diameter', 'chamber_length',
                   'throat_diameter'],
    'thermal': ['chamber_pressure', 'chamber_temperature', 'chamber_diameter',
                'chamber_length', 'mdot_total', 'wall_thickness', 'burn_time'],
    'vessel': ['meop_bar', 'inner_diameter_mm'],
    # Aynı desenin öbür güverte sekmeleri (aynı kuralla kapatıldı):
    'safety': ['chamber_pressure', 'chamber_temperature', 'thrust',
               'chamber_diameter', 'wall_thickness'],
    'joint': ['pressure_bar', 'seal_diameter_mm'],
    'cooling': ['chamber_pressure', 'chamber_temperature', 'throat_diameter',
                'expansion_ratio', 'gamma', 'molecular_weight', 'coolant_mdot'],
}
#: Eski gizli sabitler (NK3-H-7 ölçümü): tanım değeri olarak geri gelmez.
K4_ESKI_SABITLER = {
    'performance': {'chamber_pressure': 50, 'optimal_of_ratio': 3.5,
                    'base_isp': 300, 'expansion_ratio': 16,
                    'throat_area': 0.001, 'chamber_diameter': 0.1,
                    'base_heat_flux': 2000000, 'critical_heat_flux': 4.0,
                    'mdot_total': 1.0, 'gamma': 1.2,
                    'chamber_temperature': 3000},
}


@node_gerekli
@pytest.mark.parametrize('pid', sorted(K4_ZORUNLU))
def test_k4_motor_buyuklugunun_tanim_degeri_yok(pid):
    tur = ('solid' if pid == 'performance_solid'
           else ('liquid' if pid == 'cooling' else 'hybrid'))
    ev = _node(tur, None, [pid])
    spec = ev[pid]
    alanlar = {f[0]: f for f in spec['fields']}
    for k in K4_ZORUNLU[pid]:
        assert alanlar[k][2] == '', (pid, k, alanlar[k][2])
        assert k in spec['required'], (pid, k)
    for k, eski in K4_ESKI_SABITLER.get(pid, {}).items():
        assert alanlar[k][2] != eski, (pid, k)
    # Bayat sonuç (motor yok): güverte gövdesi eksikleri adıyla durdurur.
    yuk, eksik = _yuk(spec, None)
    assert set(K4_ZORUNLU[pid]) <= set(eksik), (pid, eksik)


_DOCK_VM = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const girdi = __GIRDI__;
function El(tag) {
  this.tagName = String(tag || 'div').toUpperCase(); this.children = [];
  this.style = {}; this.dataset = {}; this._attrs = {}; this.textContent = '';
  this.innerHTML = ''; this.disabled = false; this.value = ''; this.options = [];
  this._listeners = {};
  this.classList = { contains: function () { return false; }, add: function () {},
                     remove: function () {}, toggle: function () {} };
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { this.children.push(c); return c; };
El.prototype.insertAdjacentHTML = function () {};
El.prototype.remove = function () {};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.removeAttribute = function (k) { delete this._attrs[k]; };
El.prototype.getAttribute = function (k) {
  return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; };
El.prototype.hasAttribute = function (k) { return Object.prototype.hasOwnProperty.call(this._attrs, k); };
El.prototype.addEventListener = function (t, fn) {
  (this._listeners[t] = this._listeners[t] || []).push(fn); };
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.closest = function () { return null; };
const byId = {};
function getEl(id) { if (!byId[id]) byId[id] = new El('div'); return byId[id]; }
const documentStub = { head: new El('head'), body: new El('body'),
  readyState: 'complete', createElement: function (t) { return new El(t); },
  querySelector: function () { return null; }, querySelectorAll: function () { return []; },
  getElementById: getEl, addEventListener: function () {} };
let fetchSayisi = 0;
const sandbox = { console: { log: function () {}, warn: function () {}, error: function () {} },
  setTimeout: setTimeout, clearTimeout: clearTimeout, requestAnimationFrame: function (f) { f(0); },
  fetch: function () { fetchSayisi += 1;
    const govde = JSON.stringify(girdi.yanit || { status: 'success' });
    return Promise.resolve({ ok: true, status: 200,
      text: function () { return Promise.resolve(govde); },
      json: function () { return Promise.resolve(JSON.parse(govde)); } }); },
  document: documentStub, localStorage: { getItem: function () { return null; }, setItem: function () {} } };
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(girdi.kok, 'hrma/static/js/analysis_dock.js'), 'utf8'), sandbox);
vm.runInContext(fs.readFileSync(path.join(girdi.kok, girdi.panelDosyasi), 'utf8'), sandbox);
let sonuc = girdi.motor;
sandbox.window.AnalysisDock.init({ motorType: girdi.motorType,
  resultsProvider: function () { return sonuc; } });
const spec = sandbox.window.AnalysisDock._registry.filter(function (s) {
  return s.id === girdi.panelId; })[0];
// Sayfanın işaretlemesi: her alan öğesi tanım değeriyle başlar.
const ogeler = spec.fields.map(function (f) {
  const e = getEl('ad_f_' + spec.id + '_' + f[0]);
  e.tagName = Array.isArray(f[3]) ? 'SELECT' : 'INPUT';
  if (Array.isArray(f[3])) e.options = f[3].map(function (o) { return { value: String(o[0]) }; });
  e.value = (f[2] === '' || f[2] == null) ? '' : String(f[2]);
  e._attrs['data-field'] = f[0];
  return e;
});
getEl('ad_sec_' + spec.id).querySelectorAll = function (s) {
  return s === '[data-field]' ? ogeler : []; };
(async function () {
  const dugme = getEl('ad_run_' + spec.id);
  const tik = (dugme._listeners.click || [])[0];
  if (!tik) { process.stdout.write(JSON.stringify({ hata: 'dugme_yok' })); return; }
  tik(); await new Promise(function (r) { setTimeout(r, 200); });
  const tohumlu = { fetch: fetchSayisi, durum: getEl('ad_status_' + spec.id).textContent };
  sonuc = null;                      // son hesap başarısız: sonuç düşürüldü
  tik(); await new Promise(function (r) { setTimeout(r, 200); });
  process.stdout.write(JSON.stringify({ tohumlu: tohumlu,
    bayat: { fetch: fetchSayisi, durum: getEl('ad_status_' + spec.id).textContent } }));
})();
"""


@node_gerekli
@pytest.mark.parametrize('pid,dosya,eksik_etiket', [
    ('performance', 'hrma/static/js/panels/performance_panel.js',
     'Chamber Pressure (bar)'),
    ('vessel', 'hrma/static/js/panels/vessel_panel.js', 'MEOP (bar)'),
    ('thermal', 'hrma/static/js/panels/thermal_panel.js',
     'Chamber Temperature (K)'),
    ('structural', 'hrma/static/js/panels/structural_panel.js',
     'Throat Diameter (m)'),
])
def test_k4_bayat_sonucta_gercek_dugme_istek_gondermez(vakalar, pid, dosya,
                                                        eksik_etiket):
    """Gerçek güverte yolu (Çalıştır → runPanel): motor sonucuyla istek
    GİDER; sonuç düşünce (son hesap başarısız) istek GİTMEZ ve eksik alanlar
    adıyla söylenir."""
    # Sıvı ablatif motor (hibrit /calculate yük altında ~140 s; dört panel
    # sıvıda da kayıtlı).
    girdi = {'kok': str(REPO), 'panelDosyasi': dosya, 'panelId': pid,
             'motorType': 'liquid', 'motor': vakalar['sivi_abl']['motor']}
    # Betik stdin'den (test_node_cagri_sozlesmesi: argv ile betik yok);
    # girdi betiğe JSON değişmezi olarak gömülür.
    betik = _DOCK_VM.replace('__GIRDI__', json.dumps(girdi))
    p = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    r = json.loads(p.stdout)
    assert 'hata' not in r, r
    # Tohumlu koşu uca gitti (performans paneli iki ek figürü de ayrıca
    # çeker: 1 + 2 istek); bayat tıklama HİÇ istek göndermedi.
    assert r['tohumlu']['fetch'] >= 1, r
    assert r['bayat']['fetch'] == r['tohumlu']['fetch'], r
    assert 'Required fields are empty' in r['bayat']['durum'], r
    assert eksik_etiket in r['bayat']['durum'], r


# ===========================================================================
# K5 — NK3-S-9: sıvı motorun ısı yükü ⟷ TERMAL toplam ısı gücü
# ===========================================================================
@node_gerekli
def test_k5_sivi_iki_isi_yuku_yan_yana_adiyla(vakalar):
    v = vakalar['sivi_abl']
    cs = v['motor']['cooling_system']
    gsa = v['panel']['thermal']['uc']['thermal_analysis']['gas_side_analysis']
    gor = v['panel']['thermal']['gorunur']
    assert 'data-thermal-motor-heat-load="1"' in v['panel']['thermal']['html']
    assert ('Heat load — motor result (engine subsystems) %.1f kW (chamber '
            '%.1f + nozzle %.1f kW)' % (cs['total_heat_load'],
                                        cs['chamber_heat_load'],
                                        cs['nozzle_heat_load'])) in gor
    assert ('the motor result takes the heat load at %.1f K'
            % cs['wall_temperature_hot']) in gor
    assert ('this tab at the reference cooled wall %.1f K'
            % gsa['reference_wall_temperature']) in gor
    assert 'adds gas radiation (Leckner)' in gor


@node_gerekli
def test_k5_hibrit_isi_yuku_tek_sayi(vakalar):
    """Hibrit motor ısı yükünü bu sekmeyle aynı modülden yayımlar: aynı
    büyüklük, aynı sayı (motor satırı basılmaz)."""
    v = vakalar['hibrit']
    m = v['motor'].get('motor') or v['motor']
    motor_q = m['heat_transfer_analysis']['gas_side_analysis']['total_heat_rate']
    sekme_q = v['panel']['thermal']['uc']['thermal_analysis'][
        'gas_side_analysis']['total_heat_rate']
    assert sekme_q == pytest.approx(motor_q, rel=1e-9)
    assert 'data-thermal-motor-heat-load' not in v['panel']['thermal']['html']
