"""Arayüz JS bekçisi — şema/panel/birim sözleşmesi (A5 dalgası, 2026-08-09).

Bu dosya DÖRT ölçülmüş kusuru kilitler. Hepsi arayüz tarafındadır ve hiçbiri
Python testleriyle görünmüyordu, çünkü hesap ucu doğru çalışıyordu — kırık
olan, ucun sonucunu kullanıcıya taşıyan yoldu.

1. ŞEMA HESAPTAN KOPUKTU (``injector_schematics.js``)
   Dosya "tip başına beş SABİT çizim" olarak tasarlanmıştı (özgün başlığı:
   *aliases resolve to five canonical drawings*). Panel /api/injector-design
   yanıtından 17 radyal delik hesaplayıp tabloya bassa da çizimde DAİMA iki ok
   vardı; panelin hesabı ile çizimi arasında hiç veri yolu yoktu. Aynı dosya
   sıvı sayfasından da yükleniyor (``liquid.html``) ve sıvı pintle
   YAKIT-MERKEZLİ iki akışkanlı olduğu hâlde hibritin tek akışkanlı çizimiyle
   aynı resim basılıyordu.

2. ATIL DÜĞME (``injector_panel.js``)
   Hibritte kullanıcıya "Pintle TMR target" gösteriliyordu. Oysa tek akışkanlı
   hibrit pintle'da TMR bir ÇIKTIDIR: TMR = f/(1-f), f = radyal akış payı
   (``hrma/engines/injector_design.py:1660``). Çözücünün gerçekten okuduğu alan
   ``pintle.radial_fraction`` idi ve arayüzde HİÇ açılmamıştı — 0,5'te gömülü
   kalıyordu. Aşağıdaki ``TestGercekKolRadyalPay`` bunu hesap ucundan ÖLÇER.

3. YAPISAL PANEL CİDARSIZ ÇAĞIRIYORDU (``panels/structural_panel.js``)
   Alan listesinde ``wall_thickness`` yoktu; panel /analyze_structural_safety'yi
   cidar bilgisi olmadan çağırıyordu. Uç bu durumda cidarı KENDİ boyutlandırıp
   ``design_basis.wall_thickness_source = 'sized_by_hrma'`` diyor ve hükmü geri
   çekiyor — ama panel ``design_basis``i hiç okumadığı için kullanıcı bunu
   kendi cidarının doğrulanmış hükmü sanıyordu.

4. DIŞA AKTARIMDA 100000 KAT BİRİM HATASI (``transient_panel.js``)
   Sütun başlığı 'Chamber pressure (bar)' yazarken hücreye ham PASCAL
   konuyordu (``transient_ballistics.py:498`` diziyi Pa döndürür). Ekrandaki
   ÇİZİM doğru çeviriyordu, yalnız dışa aktarım yanlıştı: kullanıcı CSV/XLSX'te
   20 bar yerine 2000000 görüyordu. Aynı hata tank basıncı sütununda da vardı.
   Bu depoda daha önce birden fazla 1000x birim hatası çıktığı için bu sınıf
   ayrıca ve sayısal olarak kilitlenir.

JS grep ile denetlenmez: ``node`` içinde GERÇEK dosyalar sahte bir DOM ile
yüklenir ve fonksiyonlar GERÇEKTEN çağrılır (``test_panel_units_v2626.py``
deseni).
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANELS_DIR = STATIC_JS / 'panels'

pytestmark = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')


# ---------------------------------------------------------------------------
# node koşum takımı
# ---------------------------------------------------------------------------
#: Modül seviyesinde DOM'a dokunmayan dosyalar için asgari kum havuzu.
SANDBOX_PRELUDE = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.innerHTML = '';
    this._attrs = {};
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.querySelectorAll = function () { return []; };

const documentStub = {
    head: new El('head'),
    body: new El('body'),
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
};

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: setInterval, clearInterval: clearInterval,
    fetch: function () { return Promise.reject(new Error('sandbox: ag yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, isFinite: isFinite,
    parseFloat: parseFloat, parseInt: parseInt, document: documentStub,
    El: El,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

function run(file) {
    vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox, { filename: file });
}
const OUT = {};
"""


def _node(files, body):
    """`files` sırayla yüklenir, `body` çalıştırılır, OUT JSON olarak döner."""
    script = SANDBOX_PRELUDE
    for path in files:
        script += 'run(%s);\n' % json.dumps(str(path))
    script += body + '\nconsole.log(JSON.stringify(OUT));\n'
    # console kum havuzunun içinde susturulduğu için dışarıya process.stdout
    # ile yazıyoruz (son satır JSON).
    script = script.replace('console.log(JSON.stringify(OUT));',
                            'process.stdout.write(JSON.stringify(OUT));')
    with tempfile.TemporaryDirectory() as tmp:
        harness = os.path.join(tmp, 'harness.js')
        with open(harness, 'w', encoding='utf-8') as fh:
            fh.write(script)
        proc = subprocess.run(['node', harness], capture_output=True,
                              text=True, timeout=120)
    assert proc.returncode == 0, 'node çöktü:\n' + proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _read(path):
    return path.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# 1. ŞEMA — çizim hesabı görüyor mu?
# ---------------------------------------------------------------------------
#: Sıvı sayfasında ölçülen gerçek pintle geometrisi (yakıt-merkezli,
#: iki akışkanlı): D_p 15,5 mm · 35 x 0,81 mm radyal delik · TMR 0,47.
SIVI_PINTLE = {
    'n_radial_holes': 35, 'radial_hole_d_mm': 0.81, 'd_pintle_mm': 15.5,
    'annulus_gap_mm': 0.78, 'skip_distance_mm': 15.5, 'bf': 0.58,
    'spray_half_angle_deg': 47.0,
}
#: Hibrit tek akışkanlı pintle (ox-merkezli)
HIBRIT_PINTLE = dict(SIVI_PINTLE, single_fluid=True, radial_flow_fraction=0.5,
                     n_radial_holes=17)


@pytest.fixture(scope='module')
def sema():
    """Beş çizimi farklı geometrilerle GERÇEKTEN üretir."""
    body = """
const S = sandbox.window.InjectorSchematics;
OUT.api = { arity: S.svg.length, types: S.types() };
OUT.draw = {};
const cases = {
    genel_pintle:  ['pintle', null],
    hibrit_pintle: ['pintle', %(hyb)s],
    sivi_pintle:   ['pintle', %(liq)s],
    pintle_n4:     ['pintle', {n_radial_holes: 4, single_fluid: true}],
    pintle_n17:    ['pintle', {n_radial_holes: 17, single_fluid: true}],
    genel_swirl:   ['swirl', null],
    swirl_8:       ['swirl', {tangential_inlets: 8, inlet_d_mm: 1.1,
                              spray_half_angle_deg: 18, film_thickness_mm: 0.12,
                              K: 1.4}],
    genel_shower:  ['showerhead', null],
    shower_9:      ['showerhead', {n_orifices: 9, orifice_d_mm: 1.5}],
    genel_imp:     ['impingement', null],
    imp_5:         ['impingement', {n_elements: 5, orifice_d_mm: 0.9,
                                    half_angle_deg: 30}],
    coax_tek:      ['coaxial', {single_fluid: true}],
    coax_ikili:    ['coaxial', {single_fluid: false, orifice_d_mm: 4.2,
                                annulus_gap_mm: 0.6}],
};
Object.keys(cases).forEach(function (k) {
    const markup = S.svg(cases[k][0], cases[k][1]);
    OUT.draw[k] = {
        svg: markup,
        arrows: (markup.match(/marker-end/g) || []).length,
        lines: (markup.match(/<line /g) || []).length,
    };
});
""" % {'hyb': json.dumps(HIBRIT_PINTLE), 'liq': json.dumps(SIVI_PINTLE)}
    return _node([STATIC_JS / 'injector_schematics.js'], body)


def test_svg_geometri_argumani_aliyor(sema):
    """`svg(type)` -> `svg(type, geom)`: veri yolu açıldı mı?"""
    assert sema['api']['arity'] >= 2, (
        'InjectorSchematics.svg hâlâ tek argümanlı — panelin hesabı çizime '
        'hiçbir yoldan ulaşamaz')


def test_radyal_ok_sayisi_hesaptan_gelir(sema):
    """SABİT İKİ OK kalkmalı: delik sayısı arttıkça çizim değişmeli."""
    dort = sema['draw']['pintle_n4']['arrows']
    onyedi = sema['draw']['pintle_n17']['arrows']
    assert onyedi > dort, (
        'pintle çiziminde radyal ok sayısı delik sayısıyla değişmiyor '
        '(n=4 -> %d ok, n=17 -> %d ok). Sabit iki ok kusuru geri gelmiş.'
        % (dort, onyedi))


def test_radyal_delik_sayisi_dongude(sema):
    """Kaynak düzeyinde: sabit iki ok yerine döngü kurulmuş olmalı."""
    src = _read(STATIC_JS / 'injector_schematics.js')
    assert 'n_radial_holes' in src, (
        'injector_schematics.js n_radial_holes okumuyor — çizim hesabı görmüyor')
    assert re.search(r'for\s*\([^)]*nDraw', src), (
        'radyal jetler döngüyle çizilmiyor')


def test_delik_capi_ve_sprey_acisi_cizimde(sema):
    """Delik çapı ve sprey açısı gibi değerler geometriden basılmalı."""
    svg = sema['draw']['sivi_pintle']['svg']
    assert '35' in svg, 'radyal delik sayısı (35) çizimde yok'
    assert '0.81' in svg or '0,81' in svg, 'radyal delik çapı çizimde yok'
    assert '94' in svg, 'sprey konisi tam açısı (2θ = 94°) çizimde yok'
    assert '15.5' in svg or '15,5' in svg, 'pintle çapı D_p çizimde yok'


@pytest.mark.parametrize('case', ['genel_pintle', 'genel_swirl', 'genel_shower',
                                  'genel_imp'])
def test_geometri_yoksa_sayi_uydurulmaz(sema, case):
    """DÜRÜSTLÜK: değer verilmemişse o etiket HİÇ çizilmez.

    Elde yazılmış "~45 derece" türü künyeler bu yüzden kalktı — çizim
    ölçülmemiş bir sayıyı iddia edemez.
    """
    svg = sema['draw'][case]['svg']
    metinler = re.findall(r'>([^<]*)<', svg)
    iddia = [t for t in metinler if re.search(r'(?:⌀|θ\s*=|=\s*[0-9])', t)]
    assert not iddia, (
        '%s: geometri verilmemişken sayısal künye basılıyor: %r' % (case, iddia))


def test_hibrit_ve_sivi_pintle_gorsel_olarak_ayrisir(sema):
    """Hibrit tek akışkanlı, sıvı yakıt-merkezli: aynı resim basılamaz."""
    hyb = sema['draw']['hibrit_pintle']['svg']
    liq = sema['draw']['sivi_pintle']['svg']
    assert hyb != liq, (
        'hibrit (tek akışkanlı, ox-merkezli) pintle ile sıvı (yakıt-merkezli, '
        'iki akışkanlı) pintle AYNI çizimi basıyor')
    # Hibritte radyal akım da oksitleyicidir; sıvıda yakıttır.
    assert 'Fuel' in liq, 'sıvı pintle çiziminde yakıt akımı adlandırılmamış'
    assert 'Fuel' not in hyb, (
        'hibrit pintle çiziminde YAKIT akımı gösteriliyor — hibritte yakıt '
        'grain\'den gelir, pintle yalnız oksitleyiciyi taşır')


def test_swirl_ve_showerhead_da_hesaba_bagli(sema):
    """Kopukluk yalnız pintle'da değildi; diğer tipler de bağlandı."""
    assert sema['draw']['swirl_8']['lines'] > sema['draw']['genel_swirl']['lines'], \
        'swirl teğet giriş sayısı çizime yansımıyor'
    assert '9' in sema['draw']['shower_9']['svg'], \
        'showerhead delik sayısı çizime yansımıyor'
    assert '60' in sema['draw']['imp_5']['svg'], \
        'çarpışma tam açısı (2θ = 60°) çizime yansımıyor'


def test_coax_tek_akiskan_notu_kosula_bagli(sema):
    """'same fluid' notu iki devreli sıvı coax'ta YANLIŞ bilgidir."""
    tek = sema['draw']['coax_tek']['svg']
    ikili = sema['draw']['coax_ikili']['svg']
    assert 'same fluid' in tek
    assert 'same fluid' not in ikili, (
        'iki akışkanlı coax çiziminde "same fluid" notu duruyor')


# ---------------------------------------------------------------------------
# 2. PANEL -> ŞEMA veri yolu ve GERÇEK KOL
# ---------------------------------------------------------------------------
#: /api/injector-design yanıtının panelin okuduğu biçimi (kısaltılmış).
TASARIM_YANITI = {
    'ox_circuit': {'n_orifices': 17, 'orifice_d_mm': 1.42},
    'pintle_geometry': {
        'd_pintle_mm': 15.5, 'skip_distance_mm': 15.5, 'ls_over_dp': 1.0,
        'bf': 0.58, 'annulus_gap_mm': 0.78, 'n_radial_holes': 35,
        'radial_hole_d_mm': 0.81, 'radial_flow_fraction': 0.5,
        'single_fluid': True,
    },
    'atomization': {'spray_cone_half_angle_deg': 47.0},
    'pattern': {'n_elements': 1},
}


def test_panel_tasarimi_cizim_geometrisine_ceviriyor():
    """Panel ile şema arasındaki veri yolu GERÇEKTEN çalışıyor mu?"""
    body = """
const P = sandbox.window.InjectorPanel;
OUT.geom = P._schematicGeometry(%s);
OUT.bos = P._schematicGeometry(null);
""" % json.dumps(TASARIM_YANITI)
    out = _node([STATIC_JS / 'injector_schematics.js',
                 STATIC_JS / 'injector_panel.js'], body)
    g = out['geom']
    assert g['n_radial_holes'] == 35
    assert g['radial_hole_d_mm'] == pytest.approx(0.81)
    assert g['d_pintle_mm'] == pytest.approx(15.5)
    assert g['spray_half_angle_deg'] == pytest.approx(47.0)
    assert g['single_fluid'] is True
    assert out['bos'] is None, 'tasarım yokken boş sözlük yerine null dönmeli'


def test_hibrit_pintle_radyal_pay_alani_var():
    """Atıl 'TMR target' yerine gerçek kol açılmış olmalı (hibrit)."""
    src = _read(STATIC_JS / 'injector_panel.js')
    assert 'inj_radial_fraction' in src, (
        'hibritte kullanıcıya radyal akış payı alanı açılmamış')
    assert 'radial_fraction' in src, (
        "buildSpec çözücünün okuduğu 'pintle.radial_fraction' alanını "
        'göndermiyor — kullanıcının çevirdiği kolun karşılığı yok')
    # Hibritte artık TMR hedefi GÖNDERİLMEZ (TMR bir çıktıdır).
    assert re.search(r'if\s*\(isHybrid\)\s*\{[^}]*radial_fraction', src, re.S), (
        'radial_fraction yalnız hibrit kolunda gönderilmiyor')


def test_sivi_tmr_hedefinin_salt_eko_oldugu_beyan_ediliyor():
    """Sonuca girmeyen alan sessiz bırakılamaz (dürüstlük kuralı)."""
    src = _read(STATIC_JS / 'injector_panel.js')
    assert 'inj.tmrEchoNote' in src, (
        "sıvı pintle'da tmr_target'ın geometriyi değiştirmediği kullanıcıya "
        'bildirilmiyor')


class TestGercekKolRadyalPay:
    """Hangi kolun GERÇEK olduğunu hesap ucundan ölçer (iddia değil, ölçüm)."""

    @pytest.fixture(scope='class')
    def client(self):
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    BASE = {
        'motor_type': 'hybrid', 'injector_type': 'pintle',
        'mdot_ox': 2.0, 'rho_ox': 786.0, 'Pc_bar': 20.0,
        'fluid_ox': 'generic', 'dp_ratio_ox': 0.20,
        'inlet_ox': 'sharp', 'l_over_d': 4.0,
    }

    def _design(self, client, pintle):
        payload = dict(self.BASE, pintle=pintle)
        resp = client.post('/api/injector-design', json=payload,
                           headers={'Host': '127.0.0.1:8080'})
        assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
        body = resp.get_json()
        assert body['status'] == 'success', body
        return body['design']

    def test_tmr_target_sonuca_girmiyor(self, client):
        """ÖLÇÜM: tmr_target 0,5 ve 2,0 AYNI geometriyi veriyor (salt eko)."""
        a = self._design(client, {'bf_target': 0.58, 'tmr_target': 0.5})
        b = self._design(client, {'bf_target': 0.58, 'tmr_target': 2.0})
        assert a['pintle_geometry'] == b['pintle_geometry'], (
            'tmr_target geometriyi değiştiriyorsa bu testin gerekçesi '
            'geçersizdir — ölçümü yenileyin')
        assert a['momentum']['tmr'] == pytest.approx(b['momentum']['tmr']), (
            'tmr_target ulaşılan TMR\'yi değiştiriyor')

    def test_radial_fraction_sonucu_gercekten_degistiriyor(self, client):
        """Kullanıcıya açılan yeni kolun karşılığı VAR mı?"""
        a = self._design(client, {'bf_target': 0.58, 'radial_fraction': 0.35})
        b = self._design(client, {'bf_target': 0.58, 'radial_fraction': 0.65})
        assert a['momentum']['tmr'] != pytest.approx(b['momentum']['tmr']), (
            'radial_fraction TMR\'yi değiştirmiyor — açılan kol da atıl')
        assert (a['pintle_geometry']['n_radial_holes']
                != b['pintle_geometry']['n_radial_holes']
                or a['pintle_geometry']['radial_hole_d_mm']
                != pytest.approx(b['pintle_geometry']['radial_hole_d_mm'])), (
            'radial_fraction radyal delik geometrisini değiştirmiyor')
        # TMR = f/(1-f) bağıntısı (injector_design.py:1660)
        assert a['momentum']['tmr'] == pytest.approx(0.35 / 0.65, rel=1e-6)
        assert b['momentum']['tmr'] == pytest.approx(0.65 / 0.35, rel=1e-6)


# ---------------------------------------------------------------------------
# 3. YAPISAL PANEL — cidar gönderiliyor mu, hükmün dayanağı basılıyor mu?
# ---------------------------------------------------------------------------
#: Cidar kalınlığı yolları motor tipine göre farklı (analysis_dock.js
#: WALL_THICKNESS_MM_PATHS). Kaynakların hepsi MİLİMETRE.
CIDAR_ORNEK = {
    'hybrid': ({'motor': {'heat_transfer_analysis': {
        'design_parameters': {'wall_thickness': 8.0}}}}, 8.0),
    'solid': ({'structural_analysis': {
        'case_analysis': {'wall_thickness_mm': 3.5}}}, 3.5),
    'liquid': ({'structural_analysis': {
        'chamber_structure': {'wall_thickness': 6.25}}}, 6.25),
}


@pytest.fixture(scope='module')
def yapisal():
    body = """
const D = sandbox.window.AnalysisDock;
const spec = D._registry.filter(function (s) { return s.id === 'structural'; })[0];
OUT.fields = {};
(spec.fields || []).forEach(function (f) { OUT.fields[f[0]] = f[2]; });
OUT.endpoint = spec.endpoint;
OUT.oneriler = {};
const ornek = %s;
Object.keys(ornek).forEach(function (mt) {
    D._setMotorType(mt);
    const sug = spec.fromResults(ornek[mt]);
    OUT.oneriler[mt] = (sug.wall_thickness === undefined) ? null : sug.wall_thickness;
});
// Hükmün dayanağı bloğu gerçekten basılıyor mu?
const root = new El('div');
spec.render(%s, root);
OUT.withheldHtml = root.innerHTML;
const root2 = new El('div');
spec.render(%s, root2);
OUT.issuedHtml = root2.innerHTML;
""" % (json.dumps({k: v[0] for k, v in CIDAR_ORNEK.items()}),
       json.dumps({'structural_analysis': {
           'safety_analysis': {'status': 'NOT_EVALUATED',
                               'minimum_safety_factor': 4.8}},
           'design_basis': {
               'verdict': 'withheld',
               'wall_thickness_source': 'sized_by_hrma',
               'verdict_withheld_reasons': ['safety_factor_is_tautological'],
               'not_evaluated': ['wall_temperature'],
               'message': 'No wall thickness was supplied, so HRMA sized the '
                          'wall itself. This result is a DESIGN PROPOSAL, not '
                          'a verification of a wall you built.'}}),
       json.dumps({'structural_analysis': {
           'safety_analysis': {'status': 'SAFE', 'minimum_safety_factor': 2.1}},
           'design_basis': {
               'verdict': 'issued',
               'wall_thickness_source': 'user_supplied',
               'verdict_withheld_reasons': [], 'not_evaluated': [],
               'message': 'The supplied wall thickness was evaluated against '
                          'the design pressure; this result is a verification.'}}))
    return _node([STATIC_JS / 'analysis_dock.js',
                  PANELS_DIR / 'structural_panel.js'], body)


def test_yapisal_panel_cidar_alani_var(yapisal):
    """Panel /analyze_structural_safety'yi cidar bilgisiyle çağırmalı."""
    assert 'wall_thickness' in yapisal['fields'], (
        'structural_panel alan listesinde wall_thickness YOK — panel yapısal '
        'hükmü cidar bilgisi olmadan istiyor')


def test_yapisal_panel_cidar_varsayilani_enjekte_etmiyor(yapisal):
    """DÜRÜSTLÜK: verilmeyen cidar 'verilmiş gibi' gönderilemez.

    0 = "sen boyutlandır" (app.py `actual_wall_thickness <= 0` -> None);
    5 mm gibi bir varsayılan gönderilseydi uç sonucu 'doğrulama' diye
    damgalardı ve kullanıcı hiç vermediği bir cidarın onayını okurdu.
    """
    assert yapisal['fields']['wall_thickness'] == 0, (
        'wall_thickness varsayılanı %r — kullanıcının vermediği bir cidar '
        'enjekte ediliyor' % (yapisal['fields']['wall_thickness'],))


@pytest.mark.parametrize('motor_type', sorted(CIDAR_ORNEK))
def test_yapisal_panel_cidari_metreye_ceviriyor(yapisal, motor_type):
    """Alan METRE etiketli; çözücü kaynaklarının hepsi MİLİMETRE."""
    beklenen_mm = CIDAR_ORNEK[motor_type][1]
    value = yapisal['oneriler'][motor_type]
    assert value is not None, (
        '%s: structural paneli wall_thickness önermiyor' % motor_type)
    assert value == pytest.approx(beklenen_mm / 1000.0), (
        '%s: wall_thickness %r m, çözücü %r mm' % (motor_type, value,
                                                   beklenen_mm))


def test_yapisal_panel_hukmun_dayanagini_basiyor(yapisal):
    """Aynı sayfada iki çelişen hüküm varsa hangisinin ne olduğu yazmalı."""
    withheld = yapisal['withheldHtml']
    issued = yapisal['issuedHtml']
    assert 'DESIGN PROPOSAL' in withheld, (
        'cidar HRMA tarafından boyutlandırıldığında uç bunu söylüyor ama '
        'panel basmıyor — kullanıcı öneriyi doğrulama sanıyor')
    assert 'safety_factor_is_tautological' in withheld, (
        'hükmün neden geri çekildiği kullanıcıya gösterilmiyor')
    assert 'wall_temperature' in withheld, (
        'koşmayan değerlendirmeler (not_evaluated) gösterilmiyor')
    assert 'verification' in issued, (
        'kullanıcı kendi cidarını verdiğinde bunun bir doğrulama olduğu '
        'yazılmıyor')
    assert withheld != issued, 'iki farklı dayanak aynı çıktıyı üretiyor'


# ---------------------------------------------------------------------------
# 4. DIŞA AKTARIM BİRİMİ — başlık 'bar' diyorsa hücre de bar olmalı
# ---------------------------------------------------------------------------
#: /api/transient-analysis'in gerçekten döndürdüğü biçim: basınçlar PASCAL
#: (hrma/analysis/transient_ballistics.py:498 ve :517).
TRANSIENT_PA = {
    'time': [0.0, 0.5, 1.0],
    'thrust': [0.0, 980.0, 1000.0],
    'chamber_pressure': [1.0e5, 19.0e5, 20.0e5],     # Pa
    'tank_pressure': [50.0e5, 44.0e5, 38.0e5],       # Pa
    'tank_temperature': [293.15, 288.0, 282.5],
    'port_diameter': [0.05, 0.052, 0.054],           # m
}


@pytest.fixture(scope='module')
def disa_aktarim():
    body = """
const TP = sandbox.window.TransientPanel;
OUT.table = TP._buildExportTable(%s);
OUT.bos = TP._buildExportTable(null);
""" % json.dumps(TRANSIENT_PA)
    return _node([STATIC_JS / 'transient_panel.js'], body)


def _sutun(table, basligin_parcasi):
    idx = [i for i, h in enumerate(table['headers'])
           if basligin_parcasi.lower() in h.lower()]
    assert idx, 'sütun bulunamadı: %s (başlıklar: %s)' % (basligin_parcasi,
                                                          table['headers'])
    return [row[idx[0]] for row in table['rows']]


def test_oda_basinci_sutunu_bar(disa_aktarim):
    """20 bar'lık motor CSV'de 20 yazmalı, 2000000 değil (100000 kat hata)."""
    values = _sutun(disa_aktarim['table'], 'Chamber pressure')
    assert values == pytest.approx([1.0, 19.0, 20.0]), (
        'oda basıncı sütununda ham Pascal var: %r — başlık (bar) diyor'
        % (values,))
    assert max(values) < 1000, (
        'oda basıncı %r: bar etiketli sütunda 1000\'den büyük değer, '
        'neredeyse kesinlikle çevrilmemiş Pascal' % (max(values),))


def test_tank_basinci_sutunu_bar(disa_aktarim):
    values = _sutun(disa_aktarim['table'], 'Tank pressure')
    assert values == pytest.approx([50.0, 44.0, 38.0]), (
        'tank basıncı sütununda ham Pascal var: %r' % (values,))


def test_cevrilmemesi_gereken_sutunlar_bozulmadi(disa_aktarim):
    """Aşırı düzeltme kontrolü: itki N, sıcaklık K, port mm kalmalı."""
    table = disa_aktarim['table']
    assert _sutun(table, 'Thrust') == pytest.approx([0.0, 980.0, 1000.0])
    assert _sutun(table, 'Tank temperature') == pytest.approx(
        [293.15, 288.0, 282.5])
    assert _sutun(table, 'Port diameter') == pytest.approx([50.0, 52.0, 54.0])
    assert _sutun(table, 'Time') == pytest.approx([0.0, 0.5, 1.0])


def test_bos_sonuc_cokmuyor(disa_aktarim):
    """`Math.max.apply(null, [])` -Infinity döndürüyordu."""
    assert disa_aktarim['bos']['rows'] == []


def test_cizim_ve_disa_aktarim_ayni_cevrimi_kullanir():
    """Bir daha ayrışmasınlar: çevrim TEK yerde tanımlı olmalı."""
    src = _read(STATIC_JS / 'transient_panel.js')
    assert 'function toBar' in src, (
        'basınç çevrimi ortak bir yardımcıya alınmamış — çizim ile dışa '
        'aktarım yeniden ayrışabilir')
    assert not re.search(r'\.map\(p\s*=>\s*p\s*/\s*1e5\)', src), (
        'çizimde elle 1e5 bölmesi kalmış (ortak yardımcı kullanılmıyor)')
    assert src.count('toBar(') >= 4, (
        'toBar() hem iki grafikte hem iki dışa aktarım sütununda '
        'kullanılmalı')


# ---------------------------------------------------------------------------
# 5. Sözdizimi — dosyalar hâlâ yüklenebiliyor mu?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('rel', [
    'injector_schematics.js', 'injector_panel.js', 'transient_panel.js',
    'panels/structural_panel.js',
])
def test_sozdizimi(rel):
    proc = subprocess.run(['node', '--check', str(STATIC_JS / rel)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr


if __name__ == '__main__':                  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, '-v']))
