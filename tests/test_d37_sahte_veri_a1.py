"""A1a sahne-sahte-veri · CM-S1 — 3B sahnede KESİRLE çizilen montaj parçası YOK.

Kapattığı kusur (ölçüldü, taban ``b757cf38``; kanıt
``docs/scofield/raw/OH/A1a/sahne-sahte-veri/a1/``): ``motor_viz3d.js`` montaj
parçalarını çözücünün YAYIMLAMADIĞI ölçülerle, kamara yarıçapının / cidarının
KESRİ olarak çiziyordu. On bir adlı kesir: kapak kalınlığı
``clamp(1.6*cidar, 8, 0.3*rc+8)``, giriş borusu ``0.22*rc`` x ``1.6*kapak``,
grafit boğaz eki ``0.35*rt``, O-ring ``0.16*kapak``, spigot ``0.55*kapak``,
kapak cıvatası ``0.3*cidar``, astar ``rc-0.15``, enjektör plakası
``0.9*kapak``, ateşleyici ``0.09*rc``, lüle cıvatası ``0.05*rc``. Üç örnek
projede (hibrit / katı / sıvı) ekranda ölçekli ve gerçekmiş gibi duruyorlardı.

Kural (kart A1a-5 CM-S1): parça ölçüsü çözücünün YAYIMLADIĞI alandan geliyorsa
o alandan çizilir; gelmiyorsa parça ÇİZİLMEZ (kesirle yedek yok) ve sahne
çipi "montaj planı yok — N parça çizilmedi" der. Cıvata çemberi bir yanıt
ölçüsü sayılmaz (``structural_analysis.py`` sabit +25 mm kuralı): cıvata
YALNIZ ``assumed: fixed +25 mm layout rule`` künyesiyle çizilir.

Bekçiler DAVRANIŞ ölçer: paketlenmiş gerçek Three.js r128 node içinde yüklenir,
``motor_viz3d.js`` kaynağı AYNEN değerlendirilir (yalnız iç sınıf dışa açılır)
ve GERÇEK ``extractDims`` + ``MotorScene.prototype._buildMotor`` koşar; kurulan
mesh'ler, geometri parametreleri ve durum çipleri okunur.

Kalıp: ``tests/test_viz3d_cad_kipi.py`` (node izole) +
``tests/test_viz3d_render_kalite.py`` (gerçek r128).

CM-S2 (``TestCDetailedCAD``, saf Python): sıvı "Engineering CAD View"
(``cad_visualization.DetailedCADGenerator``) hiçbir yanıt alanında olmayan
ölçülerle enjektör kafası (0,05 m), soğutma ceketi (Ø+0,04 m × 0,8·L),
besleme hatları (0,3·L / 0,7·L), iki flanş + 16 cıvata ve iki basınç
sensörü çiziyordu; dış lüle %30/%70 görüntü kesriyle bölünüyor, kesitte
kanallar 3 mm sabit derinlikte (kamara deliğinin içinde) duruyordu. Ölçüldü
(taban, sayfanın gönderdiği gerçek gövdeyle): 419 iz, bunların 24'ü sabit
parça. Artık sabit parça izi YOK, figürde çizilmeyenler adıyla beyan edilir
(katı taslakta da; iz sayısı 0 kalır → uç 501), lüle bölünmesi kesitle aynı
çözücü konturundan, kanal yayımlanan tek yarıçapta (kamara deliği).
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from hrma.constants import MOTOR_TYPES
from tests.support.kanit import kanit_gerekli
from tests.test_viz3d_render_kalite import _strip_comments

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIZ_JS = ROOT / 'hrma/static/js/motor_viz3d.js'
I18N_JS = ROOT / 'hrma/static/js/i18n_common.js'
THREE_VENDOR = ROOT / 'hrma/static/vendor/three-0.128.0.min.js'
NODE = shutil.which('node')

# Node yalnız sahne (motor_viz3d.js) sınıflarına gerekir; (c) DetailedCAD
# ve (d) kesir sayımı saf Python'dur, node yokken atlanmaz.
NODE_GEREKLI = pytest.mark.skipif(NODE is None, reason='node bulunamadi')

# Kanıt yolları (okuma yalnız kanit_gerekli kapısından; desen d34 bekçisi).
SAHNE_KANIT = (ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'A1a'
               / 'sahne-sahte-veri' / 'a1')
KANIT_KESIR_ONCE = SAHNE_KANIT / 'once' / 'kesir_sayim.json'
KANIT_MD = {
    'hybrid': SAHNE_KANIT / 'once' / 'md_hybrid.json',
    'solid': SAHNE_KANIT / 'once' / 'md_solid.json',
    'liquid': SAHNE_KANIT / 'once' / 'md_liquid.json',
}

# Cıvata çemberi künyesi — A2 cm-0-plan ASSUMED tablosuyla birebir (kart).
BOLT_CIRCLE_BASIS = 'assumed: fixed +25 mm layout rule'

# ---------------------------------------------------------------------------
# Üç örnek gövde — ürünle gelen örnek projelerin (examples/*.hrma) sayfada
# hesaplanıp MotorViz3D.mount'a verilen sözlüğünden İNDİRGENMİŞ hâli
# (tam sözlük: KANIT_MD; aşağıdaki TestKanitGovdesi indirgemenin planı
# DEĞİŞTİRMEDİĞİNİ tam sözlükle sınar). Sayılar birebir kopyadır.
# ---------------------------------------------------------------------------
ORNEK_GOVDE = {
    'hybrid': {
        'chamber_diameter': 0.12067709328139589,
        'chamber_length': 1.0095868369554046,
        'throat_diameter': 0.029938527392188084,
        'exit_diameter': 0.06816475090259255,
        'pre_chamber_length': 0.060338546640697946,
        'grain_length': 0.913045162330288,
        'port_diameter_initial': 0.06385216943235099,
        'burn_time': 10,
        'structural_analysis': {
            'end_cap_analysis': {'flat_head_thickness': 13.217267880292841},
            'fastener_analysis': {'num_bolts': 8,
                                  'bolt_circle_radius': 85.33854664069796},
            'chamber_analysis': {'wall_thickness_used_mm': 23.08137416700142,
                                 'wall_thickness_source': 'sized_by_hrma'}},
        'thermal_protection': {
            'chamber_liner': {'thickness': 0.9844547400142576}},
        'injector_design': {'number_of_orifices': 7,
                            'orifice_diameter_mm': 2.4697070015435747,
                            'injector_type': 'showerhead'},
        'grain_design': {'grain_length_mm': 913.045162330288,
                         'grain_outer_diameter_mm': 120.6770932813959,
                         'grain_type': 'cylindrical_bore',
                         'port_diameter_initial_mm': 63.85216943235099},
        'nozzle_geometry': {'wall_thickness': 7.18524657412514},
    },
    'solid': {
        'viz_motor_type': 'solid',
        'chamber_diameter': 0.075,
        'chamber_length': 0.46399999999999997,
        'throat_diameter': 0.018418878815112803,
        'exit_diameter': 0.047568573899812165,
        'grain_length': 0.36,
        'port_diameter_initial': 0.032,
        'burn_time': 2.2771563941946757,
        'structural_analysis': {
            'end_cap_analysis': {'flat_head_thickness': 8.99701825606684},
            'case_analysis': {'wall_thickness_mm': 2,
                              'wall_thickness_source': 'sized_by_hrma'}},
        'grain_design': {'grain_length_mm': 360, 'grain_type': 'bates',
                         'outer_diameter_mm': 75},
    },
    'liquid': {
        'viz_motor_type': 'liquid',
        'chamber_diameter': 0.1094393613941705,
        'chamber_length': 0.2723566304171215,
        'throat_diameter': 0.05471968069708525,
        'exit_diameter': 0.18955453428259522,
        'burn_time': None,
        'structural_analysis': {
            'end_cap_analysis': {'flat_head_thickness': 10.060137256235796}},
        'injector_design': {'number_of_orifices': 100,
                            'orifice_diameter_mm': 0.9432590006471531},
    },
}

# Motor tipine göre sahnenin montaj parçası kataloğu (ürün tablosu
# ASSEMBLY_PARTS ile AYNI olmalı — TestPlan bunu ayrıca sınar).
PARCA_KATALOGU = {
    'hybrid': ['closure_cap', 'closure_seals', 'closure_spigot',
               'closure_bolts', 'feed_inlet', 'injector_plate', 'igniter',
               'chamber_liner', 'throat_insert', 'nozzle_flange',
               'nozzle_seal', 'nozzle_bolts'],
    'liquid': ['closure_cap', 'closure_seals', 'closure_spigot',
               'closure_bolts', 'feed_inlet', 'injector_plate',
               'throat_insert', 'nozzle_flange', 'nozzle_seal',
               'nozzle_bolts'],
    'solid': ['closure_cap', 'closure_seals', 'closure_snap_ring',
              'chamber_liner', 'throat_insert', 'nozzle_flange',
              'nozzle_seal', 'nozzle_bolts'],
}

# Örnek gövdelerde BEKLENEN çizilen parçalar (alanların varlığından —
# yukarıdaki ORNEK_GOVDE'ye bakarak elle yazıldı, ürün kodundan türetilmedi).
BEKLENEN_CIZILEN = {
    'hybrid': {'closure_cap', 'chamber_liner'},
    'solid': {'closure_cap'},
    'liquid': {'closure_cap'},
}

# Etiketsiz olabilecek (montaj parçası OLMAYAN) mesh'ler: gövde tüpü,
# soğutma kanalları (sıvı, cooling_channels), birleşim izi halkaları,
# lüle katısı, tane. (grup, malzeme, geometri) üçlüsü.
ETIKETSIZ_IZINLI = {
    ('casing', 'casing', 'LatheGeometry'),
    ('casing', 'steel', 'BoxGeometry'),
    ('closure', 'bolt', 'TorusGeometry'),
    ('nozzle', 'nozzle', 'LatheGeometry'),
    ('nozzle', 'bolt', 'TorusGeometry'),
    ('grain', 'grain', 'LatheGeometry'),
    ('grain', 'grain', 'ExtrudeGeometry'),
}


# ---------------------------------------------------------------------------
# Node sahne koşumu — GERÇEK r128 + GERÇEK motor_viz3d.js
# ---------------------------------------------------------------------------

SAHNE_ONSOZ = r"""
global.self = global;
const THREE = require(%(three)s);
global.THREE = THREE;
function _ctx() {
  return new Proxy({}, {
    get(t, k) {
      if (k === 'measureText') return (s) => ({ width: String(s).length * 7 });
      // Ş1: kanvasa GERÇEKTEN yazılan metin (yalnız kayıt açıkken tutulur)
      if (k === 'fillText') return (s) => { if (global.__YAZI) global.__YAZI.push(String(s)); };
      if (k in t) return t[k];
      if (/^create(Linear|Radial)Gradient$/.test(k)) return () => ({ addColorStop() {} });
      return (typeof k === 'string' && /^[a-z]/.test(k)) ? function () {} : undefined;
    },
    set(t, k, v) { t[k] = v; return true; } });
}
function _el() { return { style: {}, width: 0, height: 0,
  getContext() { return _ctx(); }, appendChild() {}, setAttribute() {},
  addEventListener() {} }; }
global.document = { createElement: _el, getElementById() { return null; },
  addEventListener() {}, removeEventListener() {} };
global.window = global;
const _SOZ = %(soz)s;
if (_SOZ) global.I18N = { t: (k, fb) => (k in _SOZ ? _SOZ[k] : fb) };
eval(%(kaynak)s);
function _kur(md) {
  const s = Object.create(__MotorScene.prototype);
  s.dims = __extractDims(md);
  s.state = { cutaway: false, time: 0, portShape: 'circular', cadMode: false,
              labels: false, heatMap: false };
  s._perfMode = false; s._explodeF = 0;
  s.scene = new THREE.Scene(); s.model = new THREE.Group();
  s._maxAnisotropy = () => 1;
  s._buildLabels = () => {};
  s._buildMotor();
  const matAd = new Map(Object.keys(s.mats).map(k => [s.mats[k], k]));
  const meshler = [];
  Object.keys(s.parts).forEach(grup => {
    s.parts[grup].traverse(o => {
      if (!(o.isMesh || o.isLine || o.isSprite)) return;
      const g = o.geometry || {};
      const par = g.parameters || {};
      const kayit = { grup, geo: g.type || null, mat: matAd.get(o.material) || null,
        part: o.userData.part || null, basis: o.userData.basis || null,
        sizeMm: (o.userData.sizeMm === undefined) ? null : o.userData.sizeMm,
        pos: [o.position.x, o.position.y, o.position.z] };
      if (g.type === 'LatheGeometry') {
        const pts = par.points || [];
        kayit.rMin = Math.min(...pts.map(p => p.x));
        kayit.rMax = Math.max(...pts.map(p => p.x));
        kayit.zMin = Math.min(...pts.map(p => p.y));
        kayit.zMax = Math.max(...pts.map(p => p.y));
        kayit.rSet = [...new Set(pts.map(p => p.x))].sort((a, b) => a - b);
        kayit.zSet = [...new Set(pts.map(p => p.y))].sort((a, b) => a - b);
      }
      if (g.type === 'CylinderGeometry') {
        kayit.radiusTop = par.radiusTop; kayit.height = par.height;
      }
      meshler.push(kayit);
    });
  });
  const d = s.dims;
  return { meshler,
    plan: d.partPlan,
    cipler: s._statusChipDefs().map(c => ({ text: c.text, kind: c.kind,
      field: c.field || null, parts: c.parts || null, basis: c.basis || null })),
    dims: { capT: d.capT, rc: d.rc, rcOut: d.rcOut, zg0: d.zg0, zg1: d.zg1,
            Lch: d.Lch, nBolts: d.nBolts },
    totalLen: s._totalLen, zExit: s._nozzleInfo.zExit };
}
// Denetçi şartı Ş1: ölçü etiketleri SAPLAMASIZ — GERÇEK _buildLabels iki kez
// koşar. (1) sayfa I18N'i olmadan: kanvasa yazılan düz metin. (2) numTxt'ye
// giren HAM sayı, I18N.number kancasıyla işaretlenerek yakalanır (etiket
// metnindeki yeri ⟦i⟧) — biçimlendirme değil, çizilen değer bit-aynı sınanır.
function _etiketKur(md) {
  const s = Object.create(__MotorScene.prototype);
  s.dims = __extractDims(md);
  s.state = { cutaway: false, time: 0, portShape: 'circular', cadMode: false,
              labels: true, heatMap: false };
  s._perfMode = false; s._explodeF = 0;
  s.scene = new THREE.Scene(); s.model = new THREE.Group();
  s._maxAnisotropy = () => 1;
  s._buildMotor();
  const i18nOnce = global.I18N;
  global.__YAZI = [];
  s._buildLabels();
  const duz = global.__YAZI;
  const sayilar = [];
  global.I18N = {
    t: (k, fb) => ((i18nOnce && i18nOnce.t) ? i18nOnce.t(k, fb) : fb),
    number: (v) => { sayilar.push(v); return '⟦' + (sayilar.length - 1) + '⟧'; } };
  global.__YAZI = [];
  try { s._buildLabels(); } finally { global.I18N = i18nOnce; }
  const isaretli = global.__YAZI;
  global.__YAZI = undefined;
  return { duz, isaretli, sayilar, capT: s.dims.capT,
           zExit: s._nozzleInfo.zExit, totalLen: s._totalLen };
}
"""


def _kaynak(src=None):
    src = VIZ_JS.read_text(encoding='utf-8') if src is None else src
    isaret = 'window.MotorViz3D = {'
    assert src.count(isaret) == 1, 'dışa açık API işareti bulunamadı'
    return src.replace(isaret, 'window.__MotorScene = MotorScene; '
                               'window.__extractDims = extractDims; ' + isaret)


def _sozluk_tr():
    """i18n_common.js TR bloğundan bu kulvarın anahtarları (ikinci eşleşme)."""
    src = I18N_JS.read_text(encoding='utf-8')
    out = {}
    for anahtar in ('viz3d.chip.noAssemblyPlan', 'viz3d.chip.boltCircle'):
        es = re.findall(r"'%s': '([^']*)'" % re.escape(anahtar), src)
        assert len(es) == 2, '%s EN+TR iki kez olmalı: %d' % (anahtar, len(es))
        out[anahtar] = es[1]
    return out


def _kos(govdeler, soz=None, src=None, kurucu='_kur'):
    onsoz = SAHNE_ONSOZ % {'three': json.dumps(str(THREE_VENDOR)),
                           'soz': json.dumps(soz),
                           'kaynak': json.dumps(_kaynak(src))}
    betik = onsoz + '\nprocess.stdout.write(JSON.stringify(%s.map(%s)));\n' \
        % (json.dumps(govdeler), kurucu)
    res = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                         timeout=120)
    assert res.returncode == 0, res.stderr[-1500:]
    return json.loads(res.stdout)


@pytest.fixture(scope='module')
def sahne():
    adlar = MOTOR_TYPES        # tek kaynak (test_sabit_tek_kaynak)
    sonuc = _kos([ORNEK_GOVDE[a] for a in adlar])
    return dict(zip(adlar, sonuc))


def _etiketli(kayit, part):
    return [m for m in kayit['meshler'] if m['part'] == part]


# ===========================================================================
# (a) Alanı olmayan parça için mesh YOK; alanı olanın ölçüsü == alan
# ===========================================================================

@NODE_GEREKLI
class TestAYayimlananOlcu:

    @pytest.mark.parametrize('motor', ['hybrid', 'solid', 'liquid'])
    def test_cizilen_parcalar_beklenen(self, sahne, motor):
        plan = sahne[motor]['plan']
        assert set(plan['drawn']) == BEKLENEN_CIZILEN[motor]
        etiketler = {m['part'] for m in sahne[motor]['meshler'] if m['part']}
        assert etiketler == BEKLENEN_CIZILEN[motor], (
            'çizilen parça etiketleri planla ayrışıyor: %s' % sorted(etiketler))

    @pytest.mark.parametrize('motor', ['hybrid', 'solid', 'liquid'])
    def test_cizilmeyen_parcanin_mesh_i_yok(self, sahne, motor):
        k = sahne[motor]
        for part in k['plan']['undrawn']:
            assert not _etiketli(k, part), '%s çizilmemeli' % part

    @pytest.mark.parametrize('motor', ['hybrid', 'solid', 'liquid'])
    def test_etiketsiz_montaj_parcasi_yok(self, sahne, motor):
        """Kesirle çizilen eski parçalar (O-ring, boğaz eki, ateşleyici, giriş
        borusu, lüle cıvatası ...) ETİKETSİZ mesh olarak geri gelemez."""
        yabanci = sorted({(m['grup'], m['mat'], m['geo'])
                          for m in sahne[motor]['meshler'] if not m['part']}
                         - ETIKETSIZ_IZINLI)
        assert not yabanci, 'plana bağlı olmayan mesh: %s' % yabanci

    @pytest.mark.parametrize('motor', ['hybrid', 'solid', 'liquid'])
    def test_kapak_kalinligi_alanla_bit_ayni(self, sahne, motor):
        alan = ORNEK_GOVDE[motor]['structural_analysis']['end_cap_analysis'][
            'flat_head_thickness']
        kapak = [m for m in _etiketli(sahne[motor], 'closure_cap')
                 if m['geo'] == 'LatheGeometry']
        assert len(kapak) == 1
        m = kapak[0]
        assert m['sizeMm'] == alan
        assert m['zMax'] - m['zMin'] == alan, 'kapak geometrisi alandan değil'
        assert m['zMax'] == 0 and m['rMax'] == sahne[motor]['dims']['rcOut']
        # profil yalnız iki yarıçap ve iki istasyondan: eksen + kasa dışı,
        # kapak dış yüzü + iç yüzü (ara kesir noktası yok)
        assert m['rSet'] == [0, sahne[motor]['dims']['rcOut']]
        assert m['zSet'] == [-alan, 0]
        assert sahne[motor]['dims']['capT'] == alan

    def test_hibrit_astar_alanla_ve_ortulmeyen_kesimde(self, sahne):
        k = sahne['hybrid']
        alan = ORNEK_GOVDE['hybrid']['thermal_protection']['chamber_liner']['thickness']
        astar = sorted(_etiketli(k, 'chamber_liner'), key=lambda m: m['zMin'])
        astar = [m for m in astar if m['geo'] == 'LatheGeometry']
        assert len(astar) == 2, 'astar ön + arka oda kesimi olmalı'
        d = k['dims']
        for m in astar:
            assert m['sizeMm'] == alan
            assert m['rMax'] == d['rc'], 'astar dışı kasa deliği değil (kesir?)'
            assert m['rMax'] - m['rMin'] == pytest.approx(alan, rel=1e-12)
            # profil yalnız iki yarıçaptan: rc - t ve rc (ara kesir yok)
            assert m['rSet'] == [d['rc'] - alan, d['rc']]
        assert (astar[0]['zMin'], astar[0]['zMax']) == (0, d['zg0'])
        assert (astar[1]['zMin'], astar[1]['zMax']) == (d['zg1'], d['Lch'])
        # tanenin yayımlanan ön oda boyu (m -> mm TEK çevrim)
        assert d['zg0'] == ORNEK_GOVDE['hybrid']['pre_chamber_length'] * 1000

    def test_eski_kesir_olculeri_sahnede_yok(self, sahne):
        """Hibritte eski kesirlerin ürettiği sayılar hiçbir mesh'te yok."""
        k = sahne['hybrid']
        rc = k['dims']['rc']
        yasak_yaricap = {0.22 * rc, 0.09 * rc, 0.05 * rc}
        for m in k['meshler']:
            if m['geo'] == 'CylinderGeometry':
                assert m['radiusTop'] not in yasak_yaricap

    def test_toplam_boy_yayimlanan_kapaktan(self, sahne):
        """Kadraj/L etiketi: lüle çıkışı + YAYIMLANAN kapak (giriş borusu yok)."""
        for motor, k in sahne.items():
            assert k['totalLen'] == k['zExit'] + k['dims']['capT'], motor

    @pytest.mark.parametrize('motor', ['hybrid', 'solid', 'liquid'])
    def test_alan_yoksa_parca_yok_yedek_yok(self, motor):
        """Kapak/astar alanı SİLİNİNCE parça çizilmez — kesirle yedek YOK."""
        govde = json.loads(json.dumps(ORNEK_GOVDE[motor]))
        del govde['structural_analysis']['end_cap_analysis']
        govde.pop('thermal_protection', None)
        k = _kos([govde])[0]
        assert k['dims']['capT'] is None
        for part in ('closure_cap', 'chamber_liner', 'closure_bolts'):
            assert not _etiketli(k, part), part
            if part in PARCA_KATALOGU[motor]:
                assert part in k['plan']['undrawn'], part
        assert not k['plan']['drawn']
        # Model önde kamara iç yüzüyle biter (kapak da giriş borusu da yok)
        assert k['totalLen'] == k['zExit']
        cip = _cip(k, 'assembly_plan')
        assert len(cip['parts']) == len(PARCA_KATALOGU[motor])


# ---------------------------------------------------------------------------
# Denetçi şartı Ş1 — ekrandaki toplam boy (L) etiketi, _buildLabels SAPLAMASIZ
# ---------------------------------------------------------------------------

def _js_tofixed0(x):
    """JS ``Number.prototype.toFixed(0)`` (x >= 0): kesin ikili değer üzerinde
    en yakın tamsayı, eşitlikte büyüğü — ``numTxt(v, 0)``'ın yedek biçimi."""
    from decimal import ROUND_HALF_UP, Decimal
    assert x >= 0
    return str(Decimal(x).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _l_etiketi(kayit):
    """Toplam boy etiketi: düz metin + numTxt'ye giren HAM sayı."""
    duz = [t for t in kayit['duz'] if t.startswith('L ')]
    isaretli = [t for t in kayit['isaretli'] if t.startswith('L ')]
    assert len(duz) == 1 and len(isaretli) == 1, (kayit['duz'],
                                                   kayit['isaretli'])
    m = re.match('^L ⟦(\\d+)⟧ mm', isaretli[0])
    assert m, isaretli[0]
    return duz[0], kayit['sayilar'][int(m.group(1))]


@pytest.fixture(scope='module')
def etiket():
    """Üç motor × (kapak alanı var / silindi) — tek node koşusu."""
    adlar = MOTOR_TYPES        # tek kaynak (test_sabit_tek_kaynak)
    govdeler = []
    for a in adlar:
        govdeler.append(ORNEK_GOVDE[a])
        alansiz = json.loads(json.dumps(ORNEK_GOVDE[a]))
        del alansiz['structural_analysis']['end_cap_analysis']
        govdeler.append(alansiz)
    sonuc = _kos(govdeler, kurucu='_etiketKur')
    return {a: {'alanli': sonuc[2 * i], 'alansiz': sonuc[2 * i + 1]}
            for i, a in enumerate(adlar)}


@NODE_GEREKLI
class TestAEtiketBoyu:
    """Denetçi şartı Ş1. Eski düzenek ``_buildLabels``'ı saplıyordu; etiket
    satırı (``totalMm = zExit + (capT > 0 ? capT : 0)``) davranışla hiç
    sınanmıyordu ve kapak yokken ``: 0`` → ``: 8`` (uydurma kapak, denetçi
    D1) yeşil kalıyordu. Burada GERÇEK ``_buildLabels`` koşar; etikete giren
    sayı ve kanvasa yazılan metin okunur."""

    @pytest.mark.parametrize('motor', ['hybrid', 'solid', 'liquid'])
    def test_alanli_l_zexit_arti_kapak(self, etiket, motor):
        k = etiket[motor]['alanli']
        alan = ORNEK_GOVDE[motor]['structural_analysis']['end_cap_analysis'][
            'flat_head_thickness']
        duz, L = _l_etiketi(k)
        # mm alan, mm sahne: TEK çevrim yok, toplam bit-aynı
        assert k['capT'] == alan
        assert L == k['zExit'] + alan
        assert L == k['totalLen'], 'etiket ile kadraj boyu ayrışıyor'
        assert duz.split('  •  ')[0] == 'L %s mm' % _js_tofixed0(L)

    @pytest.mark.parametrize('motor', ['hybrid', 'solid', 'liquid'])
    def test_alansiz_l_yalniz_zexit(self, etiket, motor):
        """Kapak alanı SİLİNİNCE etiket lüle çıkışında biter — yedek kapak
        kalınlığı eklenmez."""
        k = etiket[motor]['alansiz']
        duz, L = _l_etiketi(k)
        assert k['capT'] is None
        assert L == k['zExit']
        # Lüle aynı motor: alanın silinmesi yalnız kapağı düşürür
        assert k['zExit'] == etiket[motor]['alanli']['zExit']
        assert L == k['totalLen'], 'etiket ile kadraj boyu ayrışıyor'
        assert duz.split('  •  ')[0] == 'L %s mm' % _js_tofixed0(L)


# ===========================================================================
# (b) Çip: "montaj planı yok — N parça çizilmedi"; alan eklenince N azalır
# ===========================================================================

def _cip(kayit, alan):
    c = [x for x in kayit['cipler'] if x['field'] == alan]
    assert len(c) <= 1
    return c[0] if c else None


@NODE_GEREKLI
class TestBCip:

    @pytest.mark.parametrize('motor', ['hybrid', 'solid', 'liquid'])
    def test_n_cizilmeyen_parca_sayisi(self, sahne, motor):
        k = sahne[motor]
        cip = _cip(k, 'assembly_plan')
        assert cip is not None and cip['kind'] == 'missing'
        n = len(PARCA_KATALOGU[motor]) - len(BEKLENEN_CIZILEN[motor])
        assert len(cip['parts']) == n
        assert cip['text'] == ('no assembly plan — %d parts not drawn '
                               '(layout rule, not a dimension)' % n)
        # N ölçülür: katalogdaki her parça için mesh yoksa çizilmemiştir
        cizilmeyen = [p for p in PARCA_KATALOGU[motor] if not _etiketli(k, p)]
        assert sorted(cizilmeyen) == sorted(cip['parts'])

    def test_tr_metin(self):
        soz = _sozluk_tr()
        k = _kos([ORNEK_GOVDE['hybrid']], soz=soz)[0]
        cip = _cip(k, 'assembly_plan')
        assert cip['text'] == ('montaj planı yok — 10 parça çizilmedi '
                               '(yerleşim kuralı, ölçü değil)')

    def test_plaka_alani_eklenince_cizilir_ve_n_azalir(self, sahne):
        govde = json.loads(json.dumps(ORNEK_GOVDE['hybrid']))
        govde['injector_design']['plate_thickness_mm'] = 3.0
        k = _kos([govde])[0]
        plaka = [m for m in _etiketli(k, 'injector_plate')
                 if m['geo'] == 'LatheGeometry']
        assert len(plaka) == 1
        assert plaka[0]['zMax'] - plaka[0]['zMin'] == 3.0
        assert plaka[0]['zMin'] == 0 and plaka[0]['rMax'] == k['dims']['rc']
        once = len(_cip(sahne['hybrid'], 'assembly_plan')['parts'])
        assert len(_cip(k, 'assembly_plan')['parts']) == once - 1
        # Plaka çizilince delik deseninin kaynağı beyan edilir; çizilmeden
        # beyan edilmez (çizilmeyen şeyin künyesi yok).
        assert _cip(k, 'injector_source') is not None
        assert _cip(sahne['hybrid'], 'injector_source') is None
        # Delik deseni plakanın parçasıdır (etiketi plakanınki)
        assert len([m for m in _etiketli(k, 'injector_plate')
                    if m['mat'] == 'orifice']) > 0

    def test_civata_yalniz_kunyeyle(self, sahne):
        govde = json.loads(json.dumps(ORNEK_GOVDE['hybrid']))
        govde['bolted_joint'] = {'clearance_hole_diameter_mm': 6.6}
        k = _kos([govde])[0]
        fa = ORNEK_GOVDE['hybrid']['structural_analysis']['fastener_analysis']
        civata = _etiketli(k, 'closure_bolts')
        assert len(civata) == fa['num_bolts']
        for m in civata:
            assert m['basis'] == BOLT_CIRCLE_BASIS, 'künyesiz cıvata'
            assert 2 * m['radiusTop'] == 6.6
            assert m['height'] == k['dims']['capT']
            r = (m['pos'][0] ** 2 + m['pos'][2] ** 2) ** 0.5
            assert r == pytest.approx(fa['bolt_circle_radius'], rel=1e-12)
        cip = _cip(k, 'bolt_circle')
        assert cip is not None and cip['kind'] == 'assumed'
        assert cip['basis'] == BOLT_CIRCLE_BASIS
        assert cip['text'].endswith(': ' + BOLT_CIRCLE_BASIS)
        once = len(_cip(sahne['hybrid'], 'assembly_plan')['parts'])
        assert len(_cip(k, 'assembly_plan')['parts']) == once - 1
        # Delik yayımlanmadıysa (örnek gövdeler) cıvata YOK, çip YOK
        assert not _etiketli(sahne['hybrid'], 'closure_bolts')
        assert _cip(sahne['hybrid'], 'bolt_circle') is None

    def test_civata_kunyesi_kaynakta_birebir(self):
        src = VIZ_JS.read_text(encoding='utf-8')
        assert "var BOLT_CIRCLE_BASIS = '%s';" % BOLT_CIRCLE_BASIS in src


# ===========================================================================
# Plan tablosu ve tam sözlük (kanıt)
# ===========================================================================

@NODE_GEREKLI
class TestPlan:

    def test_katalog_urun_tablosuyla_ayni(self, sahne):
        for motor, k in sahne.items():
            assert sorted(k['plan']['drawn'] + k['plan']['undrawn']) == \
                sorted(PARCA_KATALOGU[motor]), motor


@NODE_GEREKLI
class TestKanitGovdesi:
    """İndirgenmiş gövde, tam sözlükle AYNI planı verir (kanıt kapısıyla)."""

    def test_tam_sozluk_ayni_plan(self, sahne):
        tam = [json.loads(kanit_gerekli(KANIT_MD[m]).read_text(encoding='utf-8'))
               for m in ('hybrid', 'solid', 'liquid')]
        sonuc = _kos(tam)
        for m, k in zip(('hybrid', 'solid', 'liquid'), sonuc):
            assert k['plan'] == sahne[m]['plan'], m


# ===========================================================================
# (d) Kesir sayımı — ADLARIYLA (clamp(0\. kaba grep'i KULLANILMAZ)
# ===========================================================================

#: Kartın on bir adlı parça kesri (CM-S1). Taban b757cf38'de her biri TAM
#: BİR kez geçer (kanıt: once/kesir_sayim.json); onarımdan sonra SIFIR.
KESIR_ADLI = {
    'kapak_capT_16cidar': r'clamp\(1\.6 \* casingWall',
    'giris_borusu_inletR_022rc': r'inletR: clamp\(0\.22 \* rc',
    'giris_borusu_inletL_16capT': r'inletL: clamp\(1\.6 \* capT',
    'bogaz_eki_tIns_035rt': r'clamp\(0\.35 \* dims\.rt',
    'o_ring_orr_016capT': r'clamp\(0\.16 \* d\.capT',
    'spigot_sg_055capT': r'clamp\(0\.55 \* d\.capT',
    'kapak_civatasi_cbR_03cidar': r'clamp\(0\.3 \* d\.casingWall',
    'astar_rc_eksi_015': r'r: d\.rc - 0\.15, z: 2',
    'plaka_injT_09capT': r'clamp\(0\.9 \* d\.capT',
    'atesleyici_igR_009rc': r'clamp\(0\.09 \* d\.rc',
    'lule_civatasi_boltR_005rc': r'clamp\(0\.05 \* d\.rc',
}

#: capT'den türeyenler — kapak kararıyla birlikte düşer (onarımdan sonra 0).
KESIR_CAPT_TUREVI = {
    'lule_flansi_flangeT_08capT': r'clamp\(0\.8 \* capT',
    'o_ring_yerleri_065_03capT': r'-0\.65 \* d\.capT|-0\.3 \* d\.capT',
    'o_ring_yiv_gwS_015capT': r'0\.15 \* d\.capT',
    'segman_012capT': r'clamp\(0\.12 \* d\.capT',
    'kapak_civata_boyu_cbH_05capT': r'clamp\(0\.5 \* d\.capT',
    'lule_o_ringi_018flangeT': r'clamp\(0\.18 \* d\.flangeT',
    'lule_civata_boyu_09flangeT': r'd\.flangeT \* 0\.9',
    'kati_tup_uzatmasi_capT_4': r'-d\.capT - 4',
    'kati_kapak_capi_rc_015': r'var cOD = d\.rc - 0\.15',
}

#: Bağımsız ek kesirler — bu kulvarda KAPSAM DIŞI, adıyla DEVİR → A6a
#: cm-3-sahne (kart 27.3 varsayılanı). Sayı DEĞİŞMEZ (ne eklenir ne düşer).
KESIR_EK_DEVIR = {
    'kadraj_flangeLip_010rc': r'clamp\(0\.10 \* rc',
    'tane_baslangic_payi_035': r'0\.35 \* Math\.max\(0, Lch - Lg\)',
    'pintle_capi_022D': r'0\.22 \* Dch',
    'ic_jet_018D': r'0\.18 \* Dch',
    'anulus_boslugu_varsayilan_12': r'annulus_gap_mm, 1\.2\)',
    'carpisma_acisi_varsayilan_60': r'impingement_angle_deg, 60\)',
    'pintle_boyu_25pR_12injT': r'2\.5 \* pR, 1\.2 \* injT',
    'orifis_halka_kesirleri': r'\[0\.35, 0\.6, 0\.85\]',
    'orifis_halka_yaricapi_rc_6': r'var rMaxO = d\.rc - 6',
    'swirl_uzunlugu_030L': r'0\.30 \* d\.Lch',
    'sogutma_kanali_boyu_092L': r'd\.Lch \* 0\.92',
}

#: Denetçi şartı Ş4 — lüle eti: kaynaksız yedek ``max(3, 0,10·d_t)`` ve
#: YAYIMLANAN ``nozzle_geometry.wall_thickness``'e de uygulanan kırpma
#: ``clamp(…, 2,5, 0,25·d_t+6)`` (``extractDims``). Bu kulvarda KAPSAM DIŞI,
#: adıyla DEVİR → A6a cm-3-sahne; sayı DEĞİŞMEZ. Ölçüldü (üç örnek proje,
#: ``a1/sonra/lule_eti_olcum.json``): hibrit yayımlanan 7,185 mm, katı yedek
#: 3 mm, sıvı yedek 5,472 mm — üçü de aralıkta, kırpma bugün etkisiz.
KESIR_EK_DEVIR_DENETCI = {
    'lule_eti_yedegi_max3_010dt': r'Math\.max\(3, 0\.1 \* dt\)',
    'lule_eti_kirpma_25_025dt6': r'2\.5, 0\.25 \* dt \+ 6\)',
}

#: OH-D27-13 künyeli ikincil yedekler — Berke 9 Eyl kararı, sayımdan HARİÇ
#: (adıyla dışlanır; künye kapısı `_kunyeKapisi` ayrı bekçide).
KESIR_OH_D27_13_HARIC = {
    'casing_wall_0045D': r'Math\.max\(4, 0\.045 \* Dch\)',
    'liner_clamp_002D': r'liner = clamp\(0\.02 \* Dch, 1\.5, 5\)',
    'Lg_08Lch': r'0\.8 \* Lch / 1000',
}


def kesir_sayimi(src):
    """Yorumsuz kaynakta her adlı desenin geçiş sayısı (beş tablo)."""
    kod = _strip_comments(src)
    return {tablo: {ad: len(re.findall(desen, kod)) for ad, desen in d.items()}
            for tablo, d in (('adli', KESIR_ADLI),
                             ('capT_turevi', KESIR_CAPT_TUREVI),
                             ('ek_devir', KESIR_EK_DEVIR),
                             ('ek_devir_denetci', KESIR_EK_DEVIR_DENETCI),
                             ('oh_d27_13_haric', KESIR_OH_D27_13_HARIC))}


class TestDKesirSayimi:

    @pytest.fixture(scope='class')
    def sayim(self):
        return kesir_sayimi(VIZ_JS.read_text(encoding='utf-8'))

    @pytest.fixture(scope='class')
    def taban(self):
        return json.loads(kanit_gerekli(KANIT_KESIR_ONCE).read_text(
            encoding='utf-8'))

    def test_tabanda_on_bir_adli_kesir_vardi(self, taban):
        """Bekçinin desenleri gerçek kusuru ölçüyor (taban b757cf38)."""
        assert taban['sayim']['adli'] == {ad: 1 for ad in KESIR_ADLI}
        assert sum(taban['sayim']['adli'].values()) == 11
        assert all(v >= 1 for v in taban['sayim']['capT_turevi'].values())

    def test_adli_kesir_sifir(self, sayim):
        kalan = {a: n for a, n in sayim['adli'].items() if n}
        assert not kalan, 'kesirle çizilen parça geri gelmiş: %s' % kalan

    def test_capT_turevi_sifir(self, sayim):
        kalan = {a: n for a, n in sayim['capT_turevi'].items() if n}
        assert not kalan, 'kapak kesrinden türeyen ölçü kalmış: %s' % kalan

    #: V3.0.5 T-ÇAPA-C1 — ÖDENEN DEVİRLER (bugün CAD-2 kalemleri, ölçüldü:
    #: desen motor_viz3d.js'te 0 kez). Ödenen kalem sayımda 0'a iner ve
    #: ADIYLA burada durur; ödenmeyenler tabanla AYNEN kalmalı (sessiz
    #: artış/azalış yok).
    ODENEN_DEVIRLER = {
        'pintle_boyu_25pR_12injT': 'c8734a5ad (V301/CAD-2 kalem 2-3-4: '
                                   'pintle 3B sahne kanonik geometriden)',
        'lule_eti_kirpma_25_025dt6': 'c6acfb89b (V301/CAD-2, KABUL K4: '
                                     'lüle eti tek kuraldan)',
    }

    def _beklenen(self, taban_sayim):
        return {ad: (0 if ad in self.ODENEN_DEVIRLER else n)
                for ad, n in taban_sayim.items()}

    def test_ek_kesirler_adiyla_devir_ve_sayi_degismedi(self, sayim, taban):
        assert sayim['ek_devir'] == self._beklenen(taban['sayim']['ek_devir'])

    def test_denetci_lule_eti_adiyla_devir_ve_sayi_degismedi(self, sayim,
                                                               taban):
        """Ş4: lüle eti yedeği + kırpması tabanda da tek kez vardı, bu
        kulvarda dokunulmadı (DEVİR A6a cm-3-sahne)."""
        assert sayim['ek_devir_denetci'] == \
            {ad: (0 if ad in self.ODENEN_DEVIRLER else 1)
             for ad in KESIR_EK_DEVIR_DENETCI}
        assert sayim['ek_devir_denetci'] == self._beklenen(
            taban['sayim']['ek_devir_denetci'])

    def test_oh_d27_13_haric_yedekler_yerinde(self, sayim, taban):
        assert sayim['oh_d27_13_haric'] == taban['sayim']['oh_d27_13_haric']
        assert all(v == 1 for v in sayim['oh_d27_13_haric'].values())



# ===========================================================================
# (c) CM-S2 — DetailedCADGenerator: sabit parça izi YOK, beyan satırı VAR
# ===========================================================================

#: Sökülen sabit parça izlerinin adları (taban figüründe ölçüldü:
#: ``once/detailed_cad_python.json``).
SABIT_PARCA_IZLERI = ('Injector Head', 'Cooling Jacket', 'Oxidizer Feed',
                      'Fuel Feed', 'Flange', 'Bolt', 'Chamber Pressure',
                      'Injector Pressure')

#: Figürdeki beyan (ürün sabitinden BAĞIMSIZ yazılır — metin değişirse
#: bekçi görür; kart: "çizilmeyen parçalar: enjektör kafası, ceket, besleme
#: hatları, flanş/cıvata, sensörler (ölçü yayımlanmıyor)").
BEYAN_SIVI = ('Parts not drawn: injector head, cooling jacket, feed lines, '
              'flanges/bolts, sensors (no dimension is published for them)')
BEYAN_SIVI_PARCALAR = ['injector_head', 'cooling_jacket', 'feed_lines',
                       'flanges_bolts', 'sensors']
BEYAN_KATI = ('Parts not drawn: grain pattern, inhibitor, case details '
              '(the detailed solid-motor generator is not modelled)')
BEYAN_ADI = 'not_drawn_declaration'

KANIT_DCAD_GOVDE = SAHNE_KANIT / 'once' / 'detailed_cad_govde_liquid.json'
KANIT_DCAD_ONCE = SAHNE_KANIT / 'once' / 'detailed_cad_python.json'

#: Sentetik sıvı gövde (üreticinin mm sözleşmesi; D25 panel ölçüleri —
#: çözücü konturu bu gövdede boğazı %30'da KOYMAZ) + yayımlanan kanal
#: yüksekliği, eleman sayısı ve cidar.
DCAD_SIVI = {
    'motor_name': 'A1a-SAHTE-VERI', 'chamber_diameter': 120.0,
    'chamber_length': 300.0, 'throat_diameter': 40.0,
    'exit_diameter': 160.0, 'nozzle_length': 220.0,
    'injector_type': 'unlike_impinging', 'chamber_pressure': 100.0,
    'thrust': 10000.0,
    'injector_design': {'number_of_elements': 12,
                        'injector_type': 'unlike_impinging'},
    'cooling_system': {'cooling_channels': 18, 'channel_height_mm': 2.5},
    'structural_analysis': {'chamber_structure': {'wall_thickness': 5.0}},
}
DCAD_KATI = {'motor_type': 'solid', 'chamber_diameter': 100.0,
             'chamber_length': 500.0, 'throat_diameter': 25.0,
             'exit_diameter': 60.0, 'nozzle_length': 150.0,
             'grain_type': 'bates'}


def _dcad(govde, tip='liquid'):
    import contextlib
    import io
    pytest.importorskip('plotly')
    from hrma.export.cad_visualization import DetailedCADGenerator
    g = DetailedCADGenerator()
    fn = (g.generate_liquid_motor_cad if tip == 'liquid'
          else g.generate_solid_motor_cad)
    with contextlib.redirect_stdout(io.StringIO()):
        sonuc = fn(json.loads(json.dumps(govde)))
    return sonuc, json.loads(sonuc['plot_json'])


def _izler(fig, sahne=None):
    return [t for t in (fig.get('data') or [])
            if sahne is None or t.get('scene', 'scene') == sahne]


def _iz(fig, ad):
    bulunan = [t for t in _izler(fig) if t.get('name') == ad]
    assert len(bulunan) == 1, '%s izi %d kez' % (ad, len(bulunan))
    return bulunan[0]


def _beyan(fig):
    return [a for a in ((fig.get('layout') or {}).get('annotations') or [])
            if a.get('name') == BEYAN_ADI]


def _rmax(t):
    import math
    return max(math.hypot(y, z) for y, z in zip(t['y'], t['z']))


def _rmin(t):
    import math
    return min(math.hypot(y, z) for y, z in zip(t['y'], t['z']))


class TestCDetailedCAD:

    @pytest.fixture(scope='class')
    def sivi(self):
        return _dcad(DCAD_SIVI)

    @pytest.fixture(scope='class')
    def gercek(self):
        """Sayfanın GERÇEKTEN gönderdiği gövde (örnek sıvı proje)."""
        govde = json.loads(kanit_gerekli(KANIT_DCAD_GOVDE).read_text(
            encoding='utf-8'))
        return govde, _dcad(govde)

    @pytest.fixture(scope='class')
    def kati(self):
        return _dcad(DCAD_KATI, tip='solid')

    def test_tabanda_sabit_parca_izleri_vardi(self):
        """Bekçi gerçek kusuru ölçüyor: taban figüründe sekiz ad da vardı."""
        once = json.loads(kanit_gerekli(KANIT_DCAD_ONCE).read_text(
            encoding='utf-8'))
        assert set(SABIT_PARCA_IZLERI) <= set(once['sivi']['adli_izler'])
        assert once['sivi']['iz_sayisi'] == 419

    @pytest.mark.parametrize('govde', ['sentetik', 'gercek'])
    def test_sivi_sabit_parca_izi_yok(self, sivi, gercek, govde):
        _s, fig = sivi if govde == 'sentetik' else gercek[1]
        adlar = {str(t.get('name')) for t in _izler(fig)}
        kalan = sorted(adlar & set(SABIT_PARCA_IZLERI))
        assert not kalan, 'sabit parça izi geri gelmiş: %s' % kalan

    def test_gercek_govdede_yalniz_sabit_parcalar_dustu(self, gercek):
        """419 iz → 395: 24 = kafa 1 + ceket 1 + 2 hat + 2×(flanş + 8
        cıvata) + 2 sensör. Başka iz düşmedi, eklenmedi."""
        _g, (sonuc, fig) = gercek
        assert len(_izler(fig)) == 419 - 24

    def test_dis_gorunus_yalniz_yayimlanan_olculer(self, sivi, gercek):
        for _s, fig in (sivi, gercek[1]):
            adlar = sorted({str(t.get('name')) for t in _izler(fig, 'scene')})
            assert adlar == ['Chamber Body', 'Nozzle'], adlar

    def test_kati_sabit_parca_izi_yok_iz_sayisi_sifir(self, kati):
        sonuc, fig = kati
        assert not ({str(t.get('name')) for t in _izler(fig)}
                    & set(SABIT_PARCA_IZLERI))
        # Beyan bir iz DEĞİL: taslak üreticinin ölçümü (0 iz → uç 501)
        # değişmedi.
        assert sonuc['trace_count'] == 0 == len(_izler(fig))
        assert sonuc['error'] == 'solid_detailed_cad_not_modelled'

    @pytest.mark.parametrize('tip', ['liquid', 'solid'])
    def test_beyan_satiri_var(self, sivi, kati, tip):
        sonuc, fig = sivi if tip == 'liquid' else kati
        beklenen = BEYAN_SIVI if tip == 'liquid' else BEYAN_KATI
        notlar = _beyan(fig)
        assert len(notlar) == 1, 'beyan satırı yok ya da çift: %s' % notlar
        assert notlar[0]['text'] == beklenen
        assert sonuc['not_drawn_parts']['declaration'] == beklenen
        assert fig['layout']['meta']['not_drawn_parts'] == \
            sonuc['not_drawn_parts']
        if tip == 'liquid':
            assert sonuc['not_drawn_parts']['parts'] == BEYAN_SIVI_PARCALAR

    def test_kamara_govdesi_alanla(self, sivi):
        sonuc, fig = sivi
        t = _iz(fig, 'Chamber Body')
        L = DCAD_SIVI['chamber_length'] / 1000.0
        # Gövde x = L/2 + (-L/2): IEEE-754'te a + (-a) TAM +0,0 verir (libm
        # yok, her platformda aynı) — tam eşitlik, tabanın altında çıplak
        # literal çapası değildir (test_d20 P13B3-07).
        assert min(t['x']) == 0.0
        assert max(t['x']) == pytest.approx(L, rel=1e-15)
        assert _rmax(t) == pytest.approx(
            DCAD_SIVI['chamber_diameter'] / 2000.0, rel=1e-12)

    @pytest.mark.parametrize('govde', ['sentetik', 'gercek'])
    def test_lule_bogazi_kesitle_ayni_kaynaktan(self, sivi, gercek, govde):
        """Dış lüle: uç noktalar yanıttan, boğaz konumu kesitin
        ``Nozzle Profile``i ile AYNI çözücü kesrinden; yayımlanan boğaz
        çizimde tam görünür (en dar yarıçap == boğaz)."""
        if govde == 'sentetik':
            g, (sonuc, fig) = DCAD_SIVI, sivi
        else:
            g, (sonuc, fig) = gercek
        dis = _iz(fig, 'Nozzle')
        kesit = _iz(fig, 'Nozzle Profile')
        kesir = (dis.get('meta') or {}).get('convergent_fraction')
        assert kesir is not None, 'dış lüle künyesi bölünmeyi taşımıyor'
        assert kesir == (kesit.get('meta') or {}).get('convergent_fraction')
        assert abs(kesir - 0.3) > 1e-3, 'görüntü sabiti %30 geri gelmiş'
        Lc = g['chamber_length'] / 1000.0
        Ln = g['nozzle_length'] / 1000.0
        rt = g['throat_diameter'] / 2000.0
        assert _rmin(dis) == pytest.approx(rt, rel=1e-12)
        assert _rmax(dis) == pytest.approx(g['exit_diameter'] / 2000.0,
                                           rel=1e-12)
        # Boğaz istasyonu: en dar yarıçapın eksenel yeri == kesir × lüle boyu
        import math
        dar = [x for x, y, z in zip(dis['x'], dis['y'], dis['z'])
               if abs(math.hypot(y, z) - rt) <= 1e-12 * rt]
        assert dar and all(abs((x - Lc) / Ln - kesir) < 1e-12 for x in dar)
        # Konverjan kamara yarıçapından başlar
        bas = [math.hypot(y, z) for x, y, z in
               zip(dis['x'], dis['y'], dis['z']) if x == Lc]
        assert bas and max(bas) == pytest.approx(
            g['chamber_diameter'] / 2000.0, rel=1e-12)

    @pytest.mark.parametrize('durum', ['sonuc_yok', 'kontur_orneklenemiyor',
                                       'bogaz_yerlesmiyor'])
    def test_kesir_okunamazsa_konverjan_yok_bogazdan_baslar(self, durum,
                                                            monkeypatch):
        """Denetçi şartı Ş2. Çözücü kesri okunamazsa bölünme UYDURULMAZ:
        dış lüle ``meta.convergent_fraction`` None, konverjan çizilmez,
        profil boğazdan başlar — kesitteki ``Nozzle Profile`` ile aynı
        hüküm, aynı künye. (Eski bekçi yalnız konturu olan gövdeleri
        koşuyordu; denetçi D10 — kesir yokken ``conv_frac = 0.25`` —
        yeşil kalıyordu.)

        sonuc_yok: analiz sonucu hiç verilmedi (``motor_data=None``, iki
        görünüş doğrudan). kontur_orneklenemiyor: örnekleyici çöker
        (``nozzle_contour`` sözlük değil). bogaz_yerlesmiyor: çözücü
        yakınsak boyu 0 → boğaz z = 0'da, kullanılamaz bölünme."""
        import math
        pytest.importorskip('plotly')
        g = json.loads(json.dumps(DCAD_SIVI))
        Lc = g['chamber_length'] / 1000.0
        Ln = g['nozzle_length'] / 1000.0
        rc = g['chamber_diameter'] / 2000.0
        rt = g['throat_diameter'] / 2000.0
        re_ = g['exit_diameter'] / 2000.0
        if durum == 'sonuc_yok':
            from hrma.export.cad_visualization import DetailedCADGenerator
            gen = DetailedCADGenerator()
            dis = gen._create_nozzle_mesh(
                start_pos=(Lc, 0, 0), throat_radius=rt, exit_radius=re_,
                length=Ln, color='#888888', name='Nozzle', motor_data=None,
                chamber_radius=rc).to_plotly_json()
            kesit = gen._create_nozzle_cross_section(
                Lc, 2 * rt, 2 * re_, Ln, chamber_dia=2 * rc,
                motor_data=None).to_plotly_json()
            from plotly.utils import PlotlyJSONEncoder
            dis = json.loads(json.dumps(dis, cls=PlotlyJSONEncoder))
            kesit = json.loads(json.dumps(kesit, cls=PlotlyJSONEncoder))
        else:
            if durum == 'kontur_orneklenemiyor':
                # ÖH 15 Eki (ana model) — dört koşulla çevrildi: (1) eski girdi
                # (nozzle_contour = ['kontur yok']) örnekleyiciyi çökertiyordu;
                # CADK yanlış tipli bloğu 'yok' saydırdı (TestKonturBlokTipi::
                # test_bos_blok_yok_sayilir) ve örnekleyici artık tasarım
                # geometrisinden ölçüyor — vakanın ön koşulu kayboldu; (2) kâhin:
                # vakanın kendi tanımı 'örnekleyici çöker' — çöküş doğrudan
                # kurulur, beklentiler aynen; (3) tolerans yok; (4) rapor
                # docs/scofield/raw/OH/V3/yayin/kapi/birlesik_supurme_15eki.md.
                import hrma.export.cad_visualization as _cv

                def _cokuyor(*_a, **_k):
                    raise ValueError('test: örnekleyici çöktü')
                monkeypatch.setattr(_cv, 'sample_nozzle_inner_contour',
                                    _cokuyor)
                g['nozzle_contour'] = ['kontur yok']
            else:
                g['design_summary'] = {'nozzle': {'convergent_length_mm': 0.0}}
            _s, fig = _dcad(g)
            dis, kesit = _iz(fig, 'Nozzle'), _iz(fig, 'Nozzle Profile')
        m_dis, m_kesit = dis.get('meta') or {}, kesit.get('meta') or {}
        assert m_dis.get('convergent_fraction') is None, (
            'kesir yokken bölünme uydurulmuş: %r' % m_dis)
        assert m_kesit.get('convergent_fraction') is None
        assert m_dis['convergent_fraction_basis'] == \
            m_kesit['convergent_fraction_basis']
        assert m_dis['convergent_fraction_basis'].startswith(
            'convergent/divergent split not drawn')
        # Dış lüle: ilk istasyon (kamara çıkışı) boğaz halkası — en geniş
        # yarıçap = en dar yarıçap = boğaz; kamara yarıçapına çıkılmaz.
        bas = [math.hypot(y, z) for x, y, z in
               zip(dis['x'], dis['y'], dis['z']) if x == Lc]
        assert bas, 'ilk istasyon bulunamadı'
        assert max(bas) == pytest.approx(rt, rel=1e-12)
        assert min(bas) == pytest.approx(rt, rel=1e-12)
        assert _rmin(dis) == pytest.approx(rt, rel=1e-12)
        assert _rmax(dis) == pytest.approx(re_, rel=1e-12)
        assert rc > rt * 1.5, 'gövde konverjanı ayırt edemiyor'
        # Konverjan yok: yarıçap eksen boyunca hiç azalmaz
        istasyon = {}
        for x, y, z in zip(dis['x'], dis['y'], dis['z']):
            istasyon.setdefault(x, []).append(math.hypot(y, z))
        yarimap = [max(istasyon[x]) for x in sorted(istasyon)]
        assert all(b >= a * (1 - 1e-12) for a, b in zip(yarimap, yarimap[1:]))
        # Kesit aynı hüküm: profil boğazdan başlar, boğazdan dar değil
        ust = kesit['y'][:len(kesit['y']) // 2]
        assert ust[0] == pytest.approx(rt, rel=1e-12)
        assert min(ust) == pytest.approx(rt, rel=1e-12)

    @pytest.mark.parametrize('govde', ['sentetik', 'gercek'])
    def test_dis_lule_yuzey_olarak_cizilir(self, sivi, gercek, govde):
        """Kural 13 (görüntü kalitesi; veri DEĞİŞMEZ — noktalar yukarıdaki
        testte bit-aynı sınanıyor): dış lüle 2 px'lik nokta bulutu değil
        yüzeydir. İstasyon × meridyen ızgarasının her dörtgeni iki üçgen;
        üçgenler yalnız var olan noktalara bağlanır."""
        _s, fig = sivi if govde == 'sentetik' else gercek[1]
        dis = _iz(fig, 'Nozzle')
        assert dis['type'] == 'mesh3d', (
            'dış lüle yüzey değil (nokta bulutu geri mi?): %s' % dis['type'])
        assert 'marker' not in dis and 'mode' not in dis
        n = len(dis['x'])
        x0 = dis['x'][0]
        n_meridyen = next(i for i, x in enumerate(dis['x']) if x != x0)
        n_istasyon = n // n_meridyen
        assert n_istasyon * n_meridyen == n
        beklenen = 2 * (n_istasyon - 1) * (n_meridyen - 1)
        assert len(dis['i']) == len(dis['j']) == len(dis['k']) == beklenen
        assert max(max(dis['i']), max(dis['j']), max(dis['k'])) < n

    def test_kanal_kamara_deliginde_sabit_derinlik_yok(self, sivi):
        import math
        sonuc, fig = sivi
        kanallar = [t for t in _izler(fig, 'scene2')
                    if t.get('line', {}).get('color') == '#0077B6'
                    and t.get('mode') == 'lines']
        assert len(kanallar) == 18, 'kanal sayısı çözücüden (18) gelmeli'
        R = DCAD_SIVI['chamber_diameter'] / 2000.0
        for t in kanallar:
            for y, z in zip(t['y'], t['z']):
                assert math.hypot(y, z) == pytest.approx(R, rel=1e-12), (
                    'kanal kamara deliğinde değil (sabit derinlik geri mi?)')
        ad = next(t['name'] for t in kanallar if t.get('name'))
        assert 'on the bore line, depth not drawn' in ad
        assert kanallar[0]['meta']['channel_height_mm'] == 2.5
        assert 'channel height 2.50 mm is published' in \
            kanallar[0]['meta']['channel_depth_basis']

    def test_kanal_yuksekligi_yayimlanmazsa_derinlik_yok_denir(self):
        import math
        govde = json.loads(json.dumps(DCAD_SIVI))
        del govde['cooling_system']['channel_height_mm']
        _s, fig = _dcad(govde)
        kanallar = [t for t in _izler(fig, 'scene2')
                    if str(t.get('name')).startswith('Cooling Channel')]
        assert kanallar and 'depth not drawn' in kanallar[0]['name']
        assert kanallar[0]['meta']['channel_height_mm'] is None
        assert 'no channel height is published' in \
            kanallar[0]['meta']['channel_depth_basis']
        R = DCAD_SIVI['chamber_diameter'] / 2000.0
        assert math.hypot(kanallar[0]['y'][0], kanallar[0]['z'][0]) == \
            pytest.approx(R, rel=1e-12)

    @pytest.mark.parametrize('fonksiyon,yasak', [
        ('_create_nozzle_mesh', (0.3, 0.7)),
        ('_create_cooling_channels_cross_section', (0.003,)),
        ('_create_external_components', (0.05, 0.01, 0.02, 0.8, 0.015,
                                         0.012, 0.03, 0.15)),
    ])
    def test_sokulen_sabitler_govdede_yok(self, fonksiyon, yasak):
        """Kaynak DOSYADAN AST ile (inspect.getsource değil: taban kaydı
        dersi) — sökülen görüntü sabitleri fonksiyon gövdesine dönmedi."""
        import ast
        kaynak = (ROOT / 'hrma/export/cad_visualization.py').read_text(
            encoding='utf-8')
        sinif = next(d for d in ast.walk(ast.parse(kaynak))
                     if isinstance(d, ast.ClassDef)
                     and d.name == 'DetailedCADGenerator')
        fn = next(d for d in sinif.body if isinstance(d, ast.FunctionDef)
                  and d.name == fonksiyon)
        sabitler = [n.value for n in ast.walk(fn)
                    if isinstance(n, ast.Constant)
                    and isinstance(n.value, float)]
        kalan = [v for v in sabitler if any(abs(v - y) < 1e-12
                                             for y in yasak)]
        assert not kalan, '%s gövdesinde sökülen sabit: %s' % (fonksiyon,
                                                               kalan)
