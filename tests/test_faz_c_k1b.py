"""A1b faz-c-0 · K1b probe + OH-D37-S7 sahne ayağı — ``motor_viz3d.js`` bekçileri.

Kart: ``docs/scofield/raw/OH/D37/ana-plan/A1b_kartlari.md`` §A1b-4.
Kanıt: ``docs/scofield/raw/OH/A1b/faz-c-0/a1/`` (rapor.md, once/, sonra/).

K1b — PROBE (sözleşme ``docs/tasarim/ui-yeniden/B2_ansys_analiz_sonuc.md``
§4 "Probe" + §7.1 K1b; hakem uygulama B1): fare altındaki CFD hücresinin
değeri, birimi ve hücre künyesi sahnenin kendi kabında yazılır. Kural:

* raycast isabetinin ``faceIndex``'i hücreye ``floor(faceIndex / 4)`` ile
  döner (alan katmanı hücre başına iki kesit düzleminde ikişer üçgen,
  12 köşe kurar); okunan değer yükteki dizinin KENDİ elemanıdır
  (``field[payloadKey][k][j]``, bit-aynı) — ara değer üretilmez;
* birim alan tanımından (``CFD_METRICS``; Mach birimsiz → birim yok);
* ``interpolated`` künyesi yalnız GERÇEKTEN ara değer varsa (CFD hücre
  merkezli düz karo: hiçbir zaman);
* alan yoksa, alan gizliyse ya da isabet opak metalin ARKASINDAYSA probe
  YOKTUR (DOM öğesi de yok — fail-closed; hakem B2: "alansız sahnede alt
  şerit düğümünün DOM'da bulunmadığı");
* ekran sayısı ``I18N`` kanalından (TR virgül), makine özniteliği nokta.

OH-D37-S7 sahne ayağı (SAHTE VERİ): ``extractDims`` itki / Isp / oda basıncı
yayımlanmadığında ``1000`` / ``200`` / ``20`` UYDURUYORDU; artık ``null``,
sahnenin HUD yayını (``onTick``) uydurma sayı taşımaz ve sahne ``missing``
çipiyle "yayımlanmadı" der. Alan varken değerler bit-aynı.

Bekçiler DAVRANIŞ ölçer: paketli gerçek Three.js r128 node içinde yüklenir,
``motor_viz3d.js`` kaynağı AYNEN değerlendirilir (yalnız iç sınıf ve saf
işlevler dışa açılır), GERÇEK ``extractDims`` + ``_buildMotor`` +
``setCfdField`` + ``probeAt`` koşar; ızgara gerçek modülden
(``build_grid_from_wall``), kontur gerçek örnekleyiciden
(``sample_nozzle_inner_contour``) — kalıp ``tests/test_viz3d_cfd_alan.py``
+ ``tests/test_d37_sahte_veri_a1.py``. Alan DEĞERLERİ sentetiktir (her
hücrede FARKLI) — konu değerin kendisi değil, isabet ⟷ hücre eşlemesidir.
"""

import json
import pathlib
import re
import shutil
import subprocess

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NODE = shutil.which('node')

NODE_GEREKLI = pytest.mark.skipif(NODE is None, reason='node bulunamadi')


def yollar(kok=ROOT):
    """Harness'in okuduğu ürün dosyaları (``kok``: depo kopyası)."""
    kok = pathlib.Path(kok).resolve()
    js = kok / 'hrma' / 'static' / 'js'
    return {
        'three': str(kok / 'hrma' / 'static' / 'vendor'
                     / 'three-0.128.0.min.js'),
        'viz': str(js / 'motor_viz3d.js'),
        'i18n': str(js / 'i18n.js'),
        'common': str(js / 'i18n_common.js'),
    }


def _yorumsuz(js):
    """JS kaynağından yorumları atar (dize içi ``//`` yok sayılmaz — yalnız
    bu dosyanın aradığı kısa kalıplar için yeterli; kalıplar dize değil)."""
    js = re.sub(r'/\*.*?\*/', ' ', js, flags=re.S)
    return re.sub(r'(?m)^\s*//[^\n]*$|\s//[^\n]*', ' ', js)


# ---------------------------------------------------------------------------
# Node sahnesi — GERÇEK r128 + GERÇEK motor_viz3d.js + GERÇEK i18n
# ---------------------------------------------------------------------------

ONSOZ = r"""
global.self = global;
const fs = require('fs');
const P = %(yollar)s;
const THREE = require(P.three);
global.THREE = THREE;
function _ctx() {
  return new Proxy({}, {
    get(t, k) {
      if (k === 'measureText') return (s) => ({ width: String(s).length * 7 });
      if (k in t) return t[k];
      if (/^create(Linear|Radial)Gradient$/.test(k)) return () => ({ addColorStop() {} });
      return (typeof k === 'string' && /^[a-z]/.test(k)) ? function () {} : undefined;
    },
    set(t, k, v) { t[k] = v; return true; } });
}
function _coz(s) {
  return String(s).replace(/<[^>]*>/g, '').replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&');
}
class El {
  constructor(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.style = {}; this.children = []; this.parentNode = null;
    this.attrs = {}; this._html = ''; this.className = '';
    this.width = 0; this.height = 0; this.offsetHeight = 0;
    this.clientWidth = 0; this.clientHeight = 0; this.handlers = {};
    this.offsetParent = {};
  }
  getContext() { return _ctx(); }
  appendChild(c) {
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this; this.children.push(c); return c;
  }
  removeChild(c) {
    const i = this.children.indexOf(c);
    if (i >= 0) this.children.splice(i, 1);
    c.parentNode = null; return c;
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) {
    return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null;
  }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); }
  removeEventListener(t, f) {
    const a = this.handlers[t] || []; const i = a.indexOf(f);
    if (i >= 0) a.splice(i, 1);
  }
  get innerHTML() { return this._html; }
  set innerHTML(v) { this._html = String(v); }
  get textContent() { return _coz(this._html); }
  set textContent(v) { this._html = String(v).replace(/&/g, '&amp;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  getBoundingClientRect() {
    return { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight };
  }
}
global.document = {
  createElement: (t) => new El(t), getElementById() { return null; },
  querySelector() { return null; }, querySelectorAll() { return []; },
  addEventListener() {}, removeEventListener() {}, dispatchEvent() {},
  readyState: 'complete',
  documentElement: { setAttribute() {}, getAttribute() { return null; } } };
global.window = global;
Object.defineProperty(global, 'localStorage', { configurable: true,
  value: { getItem() { return null; }, setItem() {}, removeItem() {} } });
Object.defineProperty(global, 'navigator', { configurable: true,
  value: { language: 'en' } });
global.requestAnimationFrame = function () { return 0; };
global.cancelAnimationFrame = function () {};
(0, eval)(fs.readFileSync(P.i18n, 'utf8'));
(0, eval)(fs.readFileSync(P.common, 'utf8'));
I18N.lang = %(lang)s;
const _KAYNAK = fs.readFileSync(P.viz, 'utf8');
const _ISARET = 'window.MotorViz3D = {';
if (_KAYNAK.split(_ISARET).length !== 2) throw new Error('dis API isareti yok');
eval(_KAYNAK.replace(_ISARET,
  'window.__MotorScene = MotorScene; window.__extractDims = extractDims; '
  + 'window.__saf = { '
  + 'cfdProbeCell: (typeof cfdProbeCell === "function") ? cfdProbeCell : null, '
  + 'probeLineParts: (typeof probeLineParts === "function") ? probeLineParts : null, '
  + 'probeLineText: (typeof probeLineText === "function") ? probeLineText : null, '
  + 'perfNotPublished: (typeof perfNotPublished === "function") ? perfNotPublished : null }; '
  + _ISARET));

// Sahne: kurucunun WebGL'siz kısmı (renderer/kontrol/rAF yok); geri kalan
// her adım ÜRÜNÜN KENDİ metodu.
function _sahne(md, w, h) {
  const s = Object.create(__MotorScene.prototype);
  s.container = new El('div');
  s.container.clientWidth = w || 1200; s.container.clientHeight = h || 600;
  s.hooks = {};
  s.dims = __extractDims(md);
  s.state = { time: 0, playing: false, speed: 1, cutaway: true,
              labels: false, plume: false, exploded: false,
              autoRotate: false, portShape: 'circular', heatMap: false,
              cadMode: false };
  s._explodeF = 0; s._lastPortR = -1; s._disposed = false;
  s._perfMode = false;
  s._maxAnisotropy = () => 1;
  s.scene = new THREE.Scene();
  s.root = new THREE.Group(); s.root.rotation.z = -Math.PI / 2;
  s.scene.add(s.root);
  s.model = new THREE.Group(); s.root.add(s.model);
  s._buildLabels = () => {};
  s._buildMotor();
  s.camera = new THREE.PerspectiveCamera(40, s.container.clientWidth
    / s.container.clientHeight, 1, 1e6);
  const canvas = new El('canvas');
  canvas.clientWidth = s.container.clientWidth;
  canvas.clientHeight = s.container.clientHeight;
  s.renderer = { domElement: canvas, render() {} };
  s.container.appendChild(canvas);
  return s;
}

// Alan katmanının dünya kutusu → kamerayı ona önden (açık kama yönü +Z)
// ya da arkadan (-Z, metal tarafı) baktırır.
function _kameraKur(s, yon) {
  s.scene.updateMatrixWorld(true);
  const L = s._cfdLayer;
  const kutu = new THREE.Box3().setFromObject(L.mesh);
  const mrk = kutu.getCenter(new THREE.Vector3());
  const boy = kutu.getSize(new THREE.Vector3()).length();
  const D = 8 * boy;
  s.camera.position.set(mrk.x, mrk.y, mrk.z + (yon === 'arka' ? -D : D));
  s.camera.up.set(0, 1, 0);
  s.camera.lookAt(mrk);
  s.camera.updateMatrixWorld(true);
  s.camera.updateProjectionMatrix();
  return { merkez: mrk.toArray(), D: D };
}

// Üçgen t'nin (hücre c = floor(t/4)) ağırlık merkezinin NDC izdüşümü.
function _ucgenNdc(s, t) {
  const L = s._cfdLayer;
  const pos = L.geometry.getAttribute('position');
  const m = new THREE.Vector3();
  for (let v = 0; v < 3; v++) {
    m.add(new THREE.Vector3().fromBufferAttribute(pos, 3 * t + v));
  }
  m.multiplyScalar(1 / 3).applyMatrix4(L.mesh.matrixWorld);
  const n = m.clone().project(s.camera);
  return { x: n.x, y: n.y };
}

function _probeDom(s) {
  const el = s.container.children.find(
    (c) => c.getAttribute && c.getAttribute('data-viz3d-probe') === '1');
  if (!el) return null;
  return { text: el.textContent, className: el.className,
           value: el.getAttribute('data-probe-value'),
           metric: el.getAttribute('data-probe-metric'),
           cell: el.getAttribute('data-probe-cell'),
           display: el.style.display || '' };
}
"""


def onsoz(kok=ROOT, lang='tr'):
    return ONSOZ % {'yollar': json.dumps(yollar(kok)),
                    'lang': json.dumps(lang)}


def node_kos(govde, kok=ROOT, lang='tr', veri=None):
    """``govde`` JS'ini önsözle koşar; ``veri`` JSON olarak ``VERI``dir.

    Betik stdin ile verilir (argv tavanı — tests/test_viz3d_cfd_alan.py
    ``_run`` notu)."""
    betik = (onsoz(kok, lang)
             + '\nconst VERI = %s;\n' % json.dumps(veri)
             + 'const OUT = {};\n' + govde
             + '\nprocess.stdout.write(JSON.stringify(OUT));\n')
    res = subprocess.run([NODE], input=betik, capture_output=True,
                         text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-2500:]
    return json.loads(res.stdout)


# ---------------------------------------------------------------------------
# Gerçek biçimli motor + CFD yükü
# ---------------------------------------------------------------------------

#: Test motoru — ucun ölçüm ailesinden konik lüle (tests/test_viz3d_cfd_alan
#: MOTORLAR['konik'] ile aynı ölçüler) + sahnenin birincil ölçü kapısı için
#: oda boyu. Performans alanları GERÇEK sayı biçiminde; S7 bekçisi onları
#: siler/korur.
K1B_MOTORU = {
    'viz_motor_type': 'liquid',
    'chamber_diameter': 0.060, 'chamber_length': 0.200,
    'throat_diameter': 0.030, 'exit_diameter': 0.075,
    'burn_time': None,
    'thrust': 4321.5, 'isp': 247.25, 'chamber_pressure': 21.75,
}
K1B_KONTUR_GIRDISI = {
    'chamber_diameter': 0.060, 'throat_diameter': 0.030,
    'exit_diameter': 0.075,
    'nozzle_contour': {'divergent': {'type': 'conical', 'half_angle': 15.0}},
    'nozzle_angles': {'convergent_half_angle_deg': 30.0},
}


def motor_ve_cfd(ni=24, nj=6, kes=None):
    """(md, cfd): md.nozzle_contour ve CFD ızgarası AYNI gerçek konturdan.

    Yeniden örnekleme ucun kuralıdır (linspace + interp; bağ
    ``tests/test_viz3d_cfd_alan.py::_kaynak_bagi_dogrula`` ile kilitli).
    Değerler her hücrede farklıdır: yanlış hücre eşlemesi farklı sayı verir.
    """
    from hrma.cfd.grid_axisym import build_grid_from_wall
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    pts_mm, _meta = sample_nozzle_inner_contour(K1B_KONTUR_GIRDISI)
    pts_m = np.asarray([[z / 1000.0, r / 1000.0] for z, r in pts_mm])
    z_nodes = np.linspace(float(pts_m[0, 0]), float(pts_m[-1, 0]), ni + 1)
    r_nodes = np.interp(z_nodes, pts_m[:, 0], pts_m[:, 1])
    grid = build_grid_from_wall(z_nodes, r_nodes, nj)
    i_bogaz = int(np.argmin(r_nodes))
    kes = list(range(ni)) if kes is None else list(kes)
    mach = [[0.2 + 0.07 * i + 0.0011 * j for j in range(nj)] for i in kes]
    pres = [[2.1e6 - 3.3e4 * i - 717.25 * j for j in range(nj)] for i in kes]
    temp = [[3100.5 - 21.25 * i - 1.5 * j for j in range(nj)] for i in kes]
    cfd = {
        'grid': {
            'ni': ni, 'nj': nj,
            'z_inlet_m': float(z_nodes[0]), 'z_exit_m': float(z_nodes[-1]),
            'r_inlet_m': float(r_nodes[0]),
            'r_throat_m': float(r_nodes[i_bogaz]),
            'r_exit_m': float(r_nodes[-1]),
        },
        'field': {
            'z_m': grid.z_centers[kes].tolist(),
            'r_m': grid.r_centers[kes].tolist(),
            'mach': mach, 'pressure_Pa': pres, 'temperature_K': temp,
            'shape': [len(kes), nj], 'grid_shape': [ni, nj],
            'axial_indices': kes, 'radial_indices': list(range(nj)),
            'n_cells_total': ni * nj, 'n_cells_returned': len(kes) * nj,
            'decimated': len(kes) < ni,
        },
    }
    md = dict(K1B_MOTORU)
    md['nozzle_contour'] = {'points': pts_m.tolist(),
                            '_basis': 'sample_nozzle_inner_contour (test)'}
    md['nozzle_angles'] = dict(K1B_KONTUR_GIRDISI['nozzle_angles'])
    return md, cfd


# ---------------------------------------------------------------------------
# Node yardımcıları (JS) — bekçilerin ortak düzeneği
# ---------------------------------------------------------------------------

YARDIMCI = r"""
function _payload(id) {
  return { mach: 'mach', pressure: 'pressure_Pa',
           temperature: 'temperature_K' }[id];
}
function _alanli(md, cfd) {
  const s = _sahne(md);
  const r = s.setCfdField(cfd);
  if (!r || !r.ok) throw new Error('alan reddedildi: ' + JSON.stringify(r));
  return s;
}
// Her hücrenin her iki düzlemine önden nişan: okunan hücre / değer.
function _tumHucreler(s) {
  const L = s._cfdLayer;
  const arr = L.field[_payload(L.metric)];
  const out = { toplam: 0, okuma: 0, yanlis_hucre: [], bit_farkli: [],
                okumasiz: [] };
  for (let c = 0; c < L.nCells; c++) {
    for (let f = 0; f < 2; f++) {
      out.toplam++;
      const n = _ucgenNdc(s, 4 * c + 2 * f);
      const r = s.probeAt(n.x, n.y);
      const k = Math.floor(c / L.nRad), j = c % L.nRad;
      if (!r) { out.okumasiz.push([c, f]); continue; }
      out.okuma++;
      if (r.cell.k !== k || r.cell.j !== j) out.yanlis_hucre.push([c, f, r.cell]);
      if (r.value !== arr[k][j]) out.bit_farkli.push([c, f, r.value, arr[k][j]]);
    }
  }
  return out;
}
function _tickKur(s) {
  s._clock = { getDelta() { return 0.016; }, elapsedTime: 0 };
  s._introT = 1; s._camHome = s.camera.position.clone();
  s.controls = { update() {}, autoRotate: false };
  s._combLight = new THREE.PointLight(); s._exitLight = new THREE.PointLight();
  s._transient = s._transient || null; s._plume = null; s._autoPerfDone = true;
  s._son = null;
  s.hooks = { onTick(p) { s._son = p; } };
}
"""


def kos(govde, veri=None, lang='tr'):
    return node_kos(YARDIMCI + govde, veri=veri, lang=lang)


@pytest.fixture(scope='module')
def yuk():
    md, cfd = motor_ve_cfd()
    return {'md': md, 'cfd': cfd}


# ===========================================================================
# K1b (a) isabet ⟷ hücre eşlemesi GERÇEK geometri üstünde; değer bit-aynı
# ===========================================================================

@NODE_GEREKLI
class TestK1bEsleme:

    def test_on_nisan_her_hucre_dogru_ve_bit_ayni(self, yuk):
        """24x6 ızgaranın 144 hücresinin iki kesit düzlemine de (288 nişan)
        önden bakılır: her nişan okuma üretir, hücre doğru, değer alan
        dizisinin elemanıyla BİT-AYNI (JS ``===``)."""
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
_kameraKur(s, 'on');
OUT.r = _tumHucreler(s);
""", yuk)['r']
        assert out['toplam'] == 2 * 24 * 6
        assert out['yanlis_hucre'] == [], out['yanlis_hucre'][:5]
        assert out['bit_farkli'] == [], out['bit_farkli'][:5]
        assert out['okumasiz'] == [], (
            'önden görünen hücre okunamadı: %r' % out['okumasiz'][:5])

    @pytest.mark.parametrize('metrik,birim', [
        ('pressure', 'Pa'), ('temperature', 'K'), ('mach', '')])
    def test_metrik_degisince_okuma_o_dizisinden(self, yuk, metrik, birim):
        """Metrik değişince imleç altındaki okuma YENİ metriğin dizisinden
        (bit-aynı) ve birimi alan tanımından gelir; Mach birimsiz."""
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
_kameraKur(s, 'on');
const L = s._cfdLayer;
const c = 77, k = Math.floor(c / L.nRad), j = c % L.nRad;
const n = _ucgenNdc(s, 4 * c);
s.probeAt(n.x, n.y);
s.setCfdMetric(VERI.metrik);
const r = s.getProbe();
OUT.r = r;
OUT.bit = r.value === L.field[_payload(VERI.metrik)][k][j];
OUT.kj = [k, j];
""", dict(yuk, metrik=metrik))
        r = out['r']
        assert r['metric'] == metrik
        assert out['bit'] is True
        assert [r['cell']['k'], r['cell']['j']] == out['kj']
        assert r['unit'] == birim

    def test_arkadan_metal_orter_okuma_ve_oge_yok(self, yuk):
        """Metal tarafından (kamera -Z) aynı hücrelere nişan: ilk opak
        isabet metaldir, okuma YOK, DOM'da probe öğesi YOK."""
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
_kameraKur(s, 'arka');
const L = s._cfdLayer;
let okuma = 0, dom = 0;
for (let c = 0; c < L.nCells; c += 5) {
  const n = _ucgenNdc(s, 4 * c);
  if (s.probeAt(n.x, n.y)) okuma++;
  if (_probeDom(s)) dom++;
}
OUT.okuma = okuma; OUT.dom = dom;
""", yuk)
        assert out == {'okuma': 0, 'dom': 0}

    def test_alansiz_sahnede_okuma_ve_oge_yok(self, yuk):
        out = kos(r"""
const s = _sahne(VERI.md);
OUT.okuma = s.probeAt(0, 0);
OUT.dom = _probeDom(s);
""", yuk)
        assert out['okuma'] is None
        assert out['dom'] is None

    def test_alan_kaldirilinca_oge_kalkar(self, yuk):
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
_kameraKur(s, 'on');
const n = _ucgenNdc(s, 4 * 40);
s.probeAt(n.x, n.y);
OUT.once = !!_probeDom(s);
s.clearCfdField();
OUT.sonra = _probeDom(s);
OUT.okuma = s.getProbe();
OUT.tekrar = s.probeAt(n.x, n.y);
""", yuk)
        assert out['once'] is True
        assert out['sonra'] is None
        assert out['okuma'] is None and out['tekrar'] is None

    def test_gizli_alan_okunmaz(self, yuk):
        """Patlatılmış görünümde alan gizlenir (_syncCfdDecor): imleç
        yerinde dursa da okuma DÜŞER, öğe kalkar."""
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
_kameraKur(s, 'on');
const n = _ucgenNdc(s, 4 * 40);
OUT.once = !!s.probeAt(n.x, n.y);
s.state.exploded = true;
s._syncCfdDecor();
OUT.sonra = s.getProbe();
OUT.dom = _probeDom(s);
""", yuk)
        assert out['once'] is True
        assert out['sonra'] is None and out['dom'] is None

    def test_inceltilmis_yukte_cozucu_indeksi_ve_istasyon_beyani(self):
        """Eksenel inceltmede (her 3. istasyon) hücre künyesi çözücünün
        KENDİ indeksidir (axial_indices), satır 'N / M istasyon' beyan eder."""
        kes = list(range(0, 24, 3))
        md, cfd = motor_ve_cfd(kes=kes)
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
_kameraKur(s, 'on');
const L = s._cfdLayer;
const c = 5 * L.nRad + 2;
const n = _ucgenNdc(s, 4 * c);
OUT.r = s.probeAt(n.x, n.y);
OUT.metin = _probeDom(s).text;
""", {'md': md, 'cfd': cfd})
        r = out['r']
        assert r['cell']['k'] == 5 and r['cell']['axial'] == kes[5]
        assert r['decimated'] is True
        assert '%d / 24' % len(kes) in out['metin']
        assert 'hücre (%d, 2)' % kes[5] in out['metin']


# ===========================================================================
# K1b (b) fare olayı yolu + bayat okuma yok
# ===========================================================================

@NODE_GEREKLI
class TestK1bFareVeTazeleme:

    def test_pointermove_probe_yolundan_gecer(self, yuk):
        """Gerçek dinleyici (``_bindProbe``) istemci koordinatını NDC'ye
        çevirir; okuma ``probeAt``ın aynısı. Sürükleme (buttons) ve imlecin
        tuvalden çıkışı okumayı ve öğeyi kaldırır."""
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
s._bindProbe();
_kameraKur(s, 'on');
const cv = s.renderer.domElement;
const n = _ucgenNdc(s, 4 * 60);
const cx = (n.x + 1) / 2 * cv.clientWidth, cy = (1 - n.y) / 2 * cv.clientHeight;
const beklenen = s.probeAt(n.x, n.y);
s._probeClear();
const hm = cv.handlers['pointermove'] || [], hl = cv.handlers['pointerleave'] || [];
OUT.dinleyici = [hm.length, hl.length];
hm.forEach(f => f({ clientX: cx, clientY: cy, buttons: 0 }));
OUT.ayni = JSON.stringify(s.getProbe()) === JSON.stringify(beklenen);
OUT.dom1 = !!_probeDom(s);
hm.forEach(f => f({ clientX: cx, clientY: cy, buttons: 1 }));
OUT.surukle = [s.getProbe(), _probeDom(s)];
hm.forEach(f => f({ clientX: cx, clientY: cy, buttons: 0 }));
hl.forEach(f => f({}));
OUT.cikis = [s.getProbe(), _probeDom(s)];
""", yuk)
        assert out['dinleyici'] == [1, 1]
        assert out['ayni'] is True and out['dom1'] is True
        assert out['surukle'] == [None, None]
        assert out['cikis'] == [None, None]

    def test_kurucu_dinleyiciyi_baglar(self):
        """``MotorScene`` kurucusu (WebGL'siz koşturulamaz) ``_bindProbe``u
        çağırır; ``dispose`` iki dinleyiciyi de bırakır."""
        src = _yorumsuz(pathlib.Path(yollar()['viz']).read_text(
            encoding='utf-8'))
        kurucu = src[src.index('function MotorScene('):
                     src.index('MotorScene.prototype._initRenderer')]
        assert 'this._bindProbe();' in kurucu
        disp = src[src.index('MotorScene.prototype.dispose = function'):]
        disp = disp[:disp.index('window.MotorViz3D = {')]
        assert "removeEventListener('pointermove'" in disp
        assert "removeEventListener('pointerleave'" in disp

    def test_dispose_oge_ve_dinleyicileri_birakir(self, yuk):
        """GERÇEK ``dispose``: katman sökümü probe öğesini kabdan kaldırır
        (dispose'da süs eşitlemesi yok — öğeyi yalnız katman sökümü
        kaldırabilir) ve tuval dinleyicileri bırakılır."""
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
s._bindProbe();
_kameraKur(s, 'on');
const n = _ucgenNdc(s, 4 * 50);
s.probeAt(n.x, n.y);
OUT.once = !!_probeDom(s);
s.renderer.dispose = function () {};
s.controls = { dispose() {} };
s.dispose();
OUT.sonra = _probeDom(s);
const cv = s.renderer.domElement;
OUT.dinleyici = [(cv.handlers['pointermove'] || []).length,
                 (cv.handlers['pointerleave'] || []).length];
""", yuk)
        assert out['once'] is True
        assert out['sonra'] is None
        assert out['dinleyici'] == [0, 0]

    def test_kamera_kipirdayinca_tick_okumayi_tazeler(self, yuk):
        """İmleç yerinde, kamera döner (yörünge/otomatik dönüş): GERÇEK
        ``_tick`` okumayı aynı nişandan tazeler — ekrandaki sayı, imlecin
        ŞU AN altındaki hücrenindir (bayat okuma kalmaz)."""
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
_kameraKur(s, 'on');
_tickKur(s);
const L = s._cfdLayer;
const n = _ucgenNdc(s, 4 * 30);
const r1 = s.probeAt(n.x, n.y);
// Kamerayı hücre boyu kadar kaydır: aynı nişanın altı başka hücre olur
s.camera.position.x += 25; s.camera.updateMatrixWorld(true);
s._tick();
const r2 = s.getProbe();
// Bağımsız ölçüm: aynı nişan, aynı kamera, doğrudan probeAt
const r3 = s.probeAt(n.x, n.y);
OUT.farkli = JSON.stringify(r1.cell) !== JSON.stringify(r2 && r2.cell);
OUT.ayni = JSON.stringify(r2) === JSON.stringify(r3);
""", yuk)
        assert out['farkli'] is True, 'kamera kaydı hücreyi değiştirmedi (test kurgusu)'
        assert out['ayni'] is True, 'tick okumayı yeni kameraya göre tazelemedi'


# ===========================================================================
# K1b (c) ekran metni: I18N kanalı, birim, interpolated künyesi
# ===========================================================================

@NODE_GEREKLI
class TestK1bMetin:

    def _satir(self, yuk, lang, metrik):
        return kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
_kameraKur(s, 'on');
s.setCfdMetric(VERI.metrik);
const n = _ucgenNdc(s, 4 * 77);
const r = s.probeAt(n.x, n.y);
OUT.r = r; OUT.dom = _probeDom(s);
OUT.interp = __saf.probeLineText(Object.assign({}, r, { interpolated: true }));
""", dict(yuk, metrik=metrik), lang=lang)

    def test_tr_virgul_en_nokta_makine_kanali_nokta(self, yuk):
        tr = self._satir(yuk, 'tr', 'temperature')
        en = self._satir(yuk, 'en', 'temperature')
        deger = tr['r']['value']
        assert deger == en['r']['value']
        metin_tr = str(deger).replace('.', ',')
        assert metin_tr in tr['dom']['text'] and '\u00a0K' in tr['dom']['text']
        assert str(deger) in en['dom']['text']
        # makine kanalı dilden bağımsız, nokta ondalık, değerin kendisi
        assert tr['dom']['value'] == en['dom']['value']
        assert ',' not in tr['dom']['value']
        assert float(tr['dom']['value']) == deger
        # hücre merkezi mm: TR virgüllü tek basamak
        assert re.search(r'z = \d+,\d mm, r = \d+,\d mm', tr['dom']['text'])
        assert re.search(r'z = \d+\.\d mm, r = \d+\.\d mm', en['dom']['text'])

    def test_mach_birimsiz(self, yuk):
        out = self._satir(yuk, 'tr', 'mach')
        assert out['r']['unit'] == ''
        v = out['dom']['text'].split(' \u00b7 ')[1]
        assert re.fullmatch(r'\d+,\d+', v), v          # birimsiz, TR virgül
        assert float(v.replace(',', '.')) == pytest.approx(out['r']['value'],
                                                           rel=1e-5)

    def test_interpolated_yalniz_ara_degerde(self, yuk):
        """CFD okuması ara değer değildir (hücre merkezli düz karo): künye
        yok. Biçimleyici künyeyi YALNIZ interpolated=true okumada basar."""
        for lang, kunye in (('tr', 'ara değer'), ('en', 'interpolated')):
            out = self._satir(yuk, lang, 'pressure')
            assert out['r']['interpolated'] is False
            assert kunye not in out['dom']['text']
            assert out['interp'].endswith(' \u00b7 ' + kunye)

    def test_css_siniflari_temada_var(self):
        """Satırın bastığı her sınıf ``theme.css``te tanımlı (yerleşim ve
        renk token'dan); taşma üç noktayla kırpılmaz."""
        css = (ROOT / 'hrma/static/css/theme.css').read_text(encoding='utf-8')
        src = pathlib.Path(yollar()['viz']).read_text(encoding='utf-8')
        govde = src[src.index('function probeLineParts('):
                    src.index('function probeLineText(')]
        siniflar = set(re.findall(r"cls: '(\w+)'", govde)) | {'sep'}
        assert siniflar == {'metric', 'value', 'meta', 'decl', 'sep'}
        assert re.search(r'\.viz3d-probe\s*\{[^}]*position:\s*absolute', css)
        for c in siniflar:
            assert '.viz3d-probe-%s' % c in css, c
        blok = css[css.index('.viz3d-probe {'):]
        blok = blok[:blok.index('}')]
        assert 'ellipsis' not in blok and 'nowrap' not in blok


# ===========================================================================
# OH-D37-S7 sahne ayağı — performans büyüklükleri uydurulmaz
# ===========================================================================

S7_JS = r"""
function _durum(md) {
  const s = _sahne(md);
  _tickKur(s);
  s._tick();
  const d = s.dims;
  return { dims: { thrust: d.thrust, isp: d.isp, pc: d.pc },
           tick: { thrust: s._son.thrust, isp: s._son.isp },
           cip: s._statusChipDefs().filter(c => c.field === 'performance')
             .map(c => ({ text: c.text, kind: c.kind, fields: c.fields })) };
}
OUT.durum = VERI.govdeler.map(_durum);
"""


def _s7(govdeler, lang='tr'):
    md, _cfd = motor_ve_cfd()
    tam = []
    for sil in govdeler:
        g = dict(md)
        for alan in sil:
            g.pop(alan, None)
        tam.append(g)
    return kos(S7_JS, {'govdeler': tam}, lang=lang)['durum'], md


@NODE_GEREKLI
class TestS7Sahne:

    def test_yayimlanmayinca_null_hud_uydurmaz_cip_adiyla(self):
        (d,), _md = _s7([('thrust', 'isp', 'chamber_pressure')])
        assert d['dims'] == {'thrust': None, 'isp': None, 'pc': None}
        assert d['tick'] == {'thrust': None, 'isp': None}
        # ÖH V3 taban-v (14 Eki 2026) — beklenti ÇEVRİLDİ (dört koşul):
        # 'Isp' çıplak etiket bekçisine takılıyordu; kâhin güvertenin aynı
        # durum metni (motor_viz_deck.js ISP_REFERANSSIZ_ETIKET + TR kaydı
        # i18n_charts.js 'Isp (referans beyan edilmedi)').
        assert d['cip'] == [{'text': 'çözücü yayımlamadı: itki, '
                             'Isp (referans beyan edilmedi), oda basıncı',
                             'kind': 'missing',
                             'fields': ['thrust', 'isp', 'pc']}]

    def test_kismi_eksik_yalniz_eksigi_soyler(self):
        (d,), md = _s7([('isp',)], lang='en')
        assert d['dims'] == {'thrust': md['thrust'], 'isp': None,
                             'pc': md['chamber_pressure']}
        assert d['cip'] == [{'text': 'not published by the solver: '
                             'Isp (reference not declared)',
                             'kind': 'missing', 'fields': ['isp']}]

    def test_yayimlaninca_bit_ayni_cip_yok(self):
        (d,), md = _s7([()])
        assert d['dims'] == {'thrust': md['thrust'], 'isp': md['isp'],
                             'pc': md['chamber_pressure']}
        assert d['tick'] == {'thrust': md['thrust'], 'isp': md['isp']}
        assert d['cip'] == []

    def test_kaynakta_uydurma_yedek_yok(self):
        """``extractDims``in performans satırlarında sayısal yedek YOK
        (yorumlar hariç kod)."""
        src = _yorumsuz(pathlib.Path(yollar()['viz']).read_text(
            encoding='utf-8'))
        govde = src[src.index('function extractDims('):]
        govde = govde[:govde.index('\n    }\n')]
        for alan, anahtar in (('thrust', 'thrust'), ('isp', 'isp'),
                              ('chamber_pressure', 'pc')):
            m = re.search(r'\b%s:\s*num\(md\.%s,\s*([^)]+)\)' % (anahtar, alan),
                          govde)
            assert m, '%s satırı bulunamadı' % anahtar
            assert m.group(1).strip() == 'null', (
                '%s yedeği sayı: %s' % (anahtar, m.group(1)))


# ===========================================================================
# +k — yeni anahtarlar çapa arasında, EN = TR, kodda kullanılıyor
# ===========================================================================

YENI_ANAHTARLAR = (
    'viz3d.probe.cell', 'viz3d.probe.centre', 'viz3d.probe.interpolated',
    'viz3d.chip.perfNotPublished', 'viz3d.perf.thrust', 'viz3d.perf.isp',
    'viz3d.perf.pc')


def test_yeni_anahtarlar_capa_arasinda_en_tr_ve_kullaniliyor():
    src = (ROOT / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
    bloklar = re.findall(r'// A1b faz-c-0 \+k ↓\n(.*?)// A1b faz-c-0 \+k ↑',
                         src, re.S)
    assert len(bloklar) == 2, 'faz-c-0 çapa çifti EN + TR iki kez olmalı'
    en = re.findall(r"'([\w.]+)':", bloklar[0])
    tr = re.findall(r"'([\w.]+)':", bloklar[1])
    assert en == tr == list(YENI_ANAHTARLAR)
    viz = _yorumsuz(pathlib.Path(yollar()['viz']).read_text(encoding='utf-8'))
    for k in YENI_ANAHTARLAR:
        assert src.count("'%s':" % k) == 2, k
        assert "'%s'" % k in viz, 'kodda kullanılmıyor: %s' % k


# ===========================================================================
# A1b şart toplayıcı — faz-c-0 denetçi Ş2 (X5 / X9 / X6 / X7)
#
# Denetçinin kaçan dört ters mutasyonu (scratchpad denetim-faz-c-0/mut.py,
# mut_sonuc.json: X5, X6, X7, X9 YEŞİL kaldı) bu düğümlerle kırmızıya döner.
# Kanıt: docs/scofield/raw/OH/A1b/sart-toplayici/ (mutasyon.md).
# ===========================================================================

#: Probe satırındaki hücre merkezi şablonu (i18n_common.js, iki dil). Ekran
#: sayıları şablona I18N kanalından (numTxt → I18N.number) girer.
MERKEZ_SABLONU = {'tr': 'hücre merkezi z = {z} mm, r = {r} mm',
                  'en': 'cell centre z = {z} mm, r = {r} mm'}


@NODE_GEREKLI
class TestSartFazC0:

    @pytest.mark.parametrize('lang', ['tr', 'en'])
    @pytest.mark.parametrize('hucre', [77, 5 * 6 + 2, 140])
    def test_x5_merkez_metninde_z_ve_r_kendi_sayisiyla(self, yuk, lang, hucre):
        """(X5) Merkez parçasındaki ``z`` sayısı hücrenin YÜKTEKİ ``z_m``'inin
        ``numTxt(z_m·1000, 1)``'i, ``r`` sayısı ``r_m``'ninki — beklenen
        değerler yükün kendi dizisinden (okumadan değil) üretilir. z ile r
        yer değiştirirse (denetçi X5) parça eşleşmez."""
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
_kameraKur(s, 'on');
const L = s._cfdLayer;
const c = VERI.hucre, k = Math.floor(c / L.nRad), j = c % L.nRad;
const n = _ucgenNdc(s, 4 * c);
const r = s.probeAt(n.x, n.y);
OUT.kj = [k, j];
OUT.okunan = r ? [r.cell.k, r.cell.j] : null;
OUT.dom = _probeDom(s);
OUT.z_mm = VERI.cfd.field.z_m[k][j] * 1000;
OUT.r_mm = VERI.cfd.field.r_m[k][j] * 1000;
OUT.bek = { z: I18N.number(OUT.z_mm, 1), r: I18N.number(OUT.r_mm, 1) };
""", dict(yuk, hucre=hucre), lang=lang)
        assert out['okunan'] == out['kj'], 'nişan başka hücreye düştü (kurgu)'
        bek = out['bek']
        # Kurgu bekçisi: z ile r'nin ekran metni farklı olmalı (aksi hâlde
        # yer değiştirme görünmez).
        assert bek['z'] != bek['r'], bek
        # Bağımsız ikinci yol: ekran metni sayının kendisine 0,05 mm içinde.
        ayrac = ',' if lang == 'tr' else '.'
        for anahtar, mm in (('z', out['z_mm']), ('r', out['r_mm'])):
            assert re.fullmatch(r'-?\d+%s\d' % re.escape(ayrac), bek[anahtar])
            assert abs(float(bek[anahtar].replace(',', '.')) - mm) <= 0.05 + 1e-9
        parcalar = out['dom']['text'].split(' · ')
        beklenen = MERKEZ_SABLONU[lang].format(z=bek['z'], r=bek['r'])
        assert beklenen in parcalar, (beklenen, parcalar)

    @pytest.mark.parametrize('lang', ['tr', 'en'])
    @pytest.mark.parametrize('metrik', ['mach', 'pressure'])
    def test_x9_makine_kanali_tam_sayi_olmayan_degerde_virgulsuz(
            self, yuk, lang, metrik):
        """(X9) ``data-probe-value`` makine kanalıdır: tam sayı OLMAYAN
        değerde (Mach 1,0455 / basınç 1 700 413,75 Pa) ondalık ayraç
        nokta, ekran basamağına yuvarlanmaz — ``float(öznitelik) ==
        okunan değer``. Ekran biçimleyiciyle yazılırsa (denetçi X9) TR'de
        virgül, basınçta ekran yuvarlaması çıkar."""
        out = kos(r"""
const s = _alanli(VERI.md, VERI.cfd);
_kameraKur(s, 'on');
s.setCfdMetric(VERI.metrik);
const L = s._cfdLayer;
const c = 77, k = Math.floor(c / L.nRad), j = c % L.nRad;
const n = _ucgenNdc(s, 4 * c);
const r = s.probeAt(n.x, n.y);
OUT.deger = r.value;
OUT.yuk = L.field[_payload(VERI.metrik)][k][j];
OUT.dom = _probeDom(s);
""", dict(yuk, metrik=metrik), lang=lang)
        deger = out['deger']
        assert deger == out['yuk']
        # Kurgu bekçisi: değer tam sayı değil (ayraç ve yuvarlama görünür).
        assert deger != int(deger), deger
        makine = out['dom']['value']
        assert ',' not in makine, makine
        assert float(makine) == deger, (makine, deger)

    def test_x6_dil_degisince_probe_metni_dil_degistirir(self, yuk):
        """(X6) GERÇEK ``_bindLangChange`` dinleyicisi + GERÇEK
        ``I18N.setLang``: imleç yerinde, dil TR → EN değişince probe
        satırı YENİ dilde yeniden basılır (sözcükler ve ondalık ayraç).
        Dinleyici probe'u tazelemezse (denetçi X6) DOM TR'de kalır."""
        out = kos(r"""
const _dinle = {};
document.addEventListener = (t, f) => { (_dinle[t] = _dinle[t] || []).push(f); };
document.removeEventListener = (t, f) => {
  const a = _dinle[t] || []; const i = a.indexOf(f); if (i >= 0) a.splice(i, 1); };
document.dispatchEvent = (e) => {
  (_dinle[e.type] || []).slice().forEach(f => f(e)); return true; };
const s = _alanli(VERI.md, VERI.cfd);
s._bindLangChange();
_kameraKur(s, 'on');
s.setCfdMetric('mach');
const n = _ucgenNdc(s, 4 * 77);
s.probeAt(n.x, n.y);
OUT.dinleyici = (_dinle['hrma:langchange'] || []).length;
OUT.tr = _probeDom(s).text;
OUT.tr_bek = __saf.probeLineText(s.getProbe());
OUT.lang0 = I18N.lang;
I18N.setLang('en');
OUT.lang1 = I18N.lang;
OUT.en = _probeDom(s) && _probeDom(s).text;
OUT.en_bek = __saf.probeLineText(s.getProbe());
OUT.okuma_ayni = s.getProbe() && s.getProbe().value;
""", yuk, lang='tr')
        assert out['dinleyici'] == 1
        assert (out['lang0'], out['lang1']) == ('tr', 'en')
        assert out['tr'] == out['tr_bek']
        assert 'hücre (' in out['tr'] and 'hücre merkezi' in out['tr']
        assert out['en_bek'] != out['tr_bek']
        assert out['en'] == out['en_bek'], (out['en'], out['en_bek'])
        assert 'cell (' in out['en'] and 'cell centre' in out['en']
        assert 'hücre' not in out['en']
        # Ondalık ayraç da dile uyar (değer: Mach, tam sayı değil)
        v = out['okuma_ayni']
        assert str(v) in out['en'] and str(v).replace('.', ',') in out['tr']

    @pytest.mark.parametrize('sil', [('thrust', 'isp', 'chamber_pressure'),
                                     ('isp',)])
    def test_x7_performans_cipi_son_eleman_onceki_sira_tabanla_ayni(self, sil):
        """(X7) Performans çipi ``_statusChipDefs``in SON elemanıdır;
        önündeki çiplerin sırası, performans alanları YAYIMLANMIŞ aynı
        motorun (taban) çip listesiyle birebir aynı. Çip başa eklenirse
        (denetçi X7: ``unshift``) mevcut çiplerin yeri kayar."""
        md, _cfd = motor_ve_cfd()
        eksik = {k: v for k, v in md.items() if k not in sil}
        out = kos(r"""
function _cipler(md) {
  const s = _sahne(md);
  return s._statusChipDefs().map(c => ({ text: c.text, kind: c.kind,
                                         field: c.field || null }));
}
OUT.taban = _cipler(VERI.tam);
OUT.eksik = _cipler(VERI.eksik);
""", {'tam': md, 'eksik': eksik})
        taban, eks = out['taban'], out['eksik']
        # Kurgu bekçisi: sıra karşılaştırması anlamlı olsun (≥2 çip) ve
        # tabanda performans çipi yok.
        assert len(taban) >= 2, taban
        assert all(c['field'] != 'performance' for c in taban)
        assert len(eks) == len(taban) + 1
        assert eks[-1]['field'] == 'performance'
        assert eks[-1]['kind'] == 'missing'
        assert eks[:-1] == taban
