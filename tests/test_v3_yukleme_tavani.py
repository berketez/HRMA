"""V3 güvenlik 5. tur bekçileri: yükleme arayüzlerinin boyut tavanı.

KUSUR (``sg2_waitress`` devri 3, 14 Eki): waitress yollarında tavanı aşan
yükleme waitress'in İngilizce DÜZ METİN 413'ünü alıyor. STEP, .ork, motor
dosyası ve CSV arayüzleri dosyayı tavanı bilmeden baştan sona gönderiyor,
413 gelince de ya ``HTTP 413`` ya da makine kodu
(``request_body_too_large``) basıyordu.

Düzeltme ve bu dosyanın ölçtüğü sözleşme:

1. Tavanlar sayfaya SUNUCUDAN gelir: ``app.py::inject_upload_limits`` →
   ``<meta name="hrma-upload-limits">``. Sayılar ucun kendi tek kaynağından
   (``step_api.MAX_UPLOAD_BYTES``, ``importers.api.ORK_MAX_BYTES``,
   ``MOTOR_FILE_MAX_BYTES``, ``body_limit.REQUEST_BODY_MAX_BYTES``); JS'te
   tavan sayısı YOK (CLAUDE.md §11).
2. Aşan dosyada ``fetch`` ÇAĞRILMAZ (node ``vm`` içinde gerçek JS koşulur,
   ``fetch`` ve ``FileReader`` sayılır); ileti i18n'li (EN = TR), boyut ve
   tavan MB olarak.
3. Sunucudan yine de BOYUT 413'ü gelirse (düz metin ya da JSON) ham gövde
   gösterilmez, aynı i18n iletisi basılır. CSV satır bandı 413'ü
   (``limit == 'data_rows'``) boyut reddi DEĞİLDİR, sunucunun iletisi kalır.

Rapor: ``docs/scofield/raw/OH/V3/guvenlik/SG2_rapor.md`` 'Yükleme tavanı
arayüzü (14 Eki)'; ters mutasyon ``.../guvenlik/sgy/mutasyon.md``.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('HRMA_HEADLESS', '1')

import hrma.importers.api as importers_api  # noqa: E402
import hrma.importers.step_api as step_api  # noqa: E402
from hrma.app import app  # noqa: E402
from hrma.security.body_limit import REQUEST_BODY_MAX_BYTES  # noqa: E402

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

JS_DIR = ROOT / 'hrma/static/js'
IMPORT_UI = JS_DIR / 'import_ui.js'
STEP_UI = JS_DIR / 'step_import_ui.js'
SIXDOF = JS_DIR / 'sixdof_panel.js'
VALIDATION = JS_DIR / 'panels/validation_panel.js'
I18N_COMMON = JS_DIR / 'i18n_common.js'
YUKLEME_JS = (IMPORT_UI, STEP_UI, SIXDOF, VALIDATION)

#: Yükleme arayüzü taşıyan sayfalar (yol → şablon).
YUKLEME_SAYFALARI = {'/solid': 'solid.html', '/liquid': 'liquid.html',
            '/hybrid': 'advanced.html'}

META_RE = re.compile(
    r"""<meta name="hrma-upload-limits" content='([^']*)'>""")


def _beklenen_tavanlar():
    """Tek kaynaklar — testte de sayı YAZILMAZ, modüllerden okunur."""
    return {
        'step': step_api.MAX_UPLOAD_BYTES,
        'ork': importers_api.ORK_MAX_BYTES,
        'motor_file': importers_api.MOTOR_FILE_MAX_BYTES,
        'csv': REQUEST_BODY_MAX_BYTES,
    }


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _meta(client, yol):
    r = client.get(yol)
    assert r.status_code == 200, (yol, r.status_code)
    eslesen = META_RE.findall(r.get_data(as_text=True))
    assert len(eslesen) == 1, (yol, eslesen)
    return json.loads(html.unescape(eslesen[0])), html.unescape(eslesen[0])


# ---------------------------------------------------------------------------
# 1. Tavan sayfaya sunucudan geliyor
# ---------------------------------------------------------------------------

class TestTavanSunucudan:

    @pytest.mark.parametrize('yol', sorted(YUKLEME_SAYFALARI))
    def test_sayfa_tavani_tek_kaynaktan_basiyor(self, client, yol):
        tavan, _ = _meta(client, yol)
        assert tavan == _beklenen_tavanlar()

    @pytest.mark.parametrize('yol', sorted(YUKLEME_SAYFALARI))
    def test_tavan_kaynagi_izliyor(self, client, yol, monkeypatch):
        """Tek kaynak değişince sayfa da değişir: şablonda ya da bağlamda
        kopya literal yok (ters mutasyon M7/M10 bunu ısırır)."""
        monkeypatch.setattr(importers_api, 'ORK_MAX_BYTES', 4096)
        monkeypatch.setattr(importers_api, 'MOTOR_FILE_MAX_BYTES', 2048)
        monkeypatch.setattr(step_api, 'MAX_UPLOAD_BYTES', 8192)
        monkeypatch.setattr('hrma.app.REQUEST_BODY_MAX_BYTES', 16384)
        tavan, _ = _meta(client, yol)
        assert tavan == {'step': 8192, 'ork': 4096, 'motor_file': 2048,
                         'csv': 16384}

    def test_yukleme_js_yukleyen_her_sablonda_meta_var(self):
        """import_ui.js'i yükleyen her şablon tavanı da basar."""
        sablonlar = sorted((ROOT / 'hrma/templates').glob('*.html'))
        yukleyen = [p for p in sablonlar
                    if '/static/js/import_ui.js' in p.read_text(encoding='utf-8')]
        assert {p.name for p in yukleyen} == set(YUKLEME_SAYFALARI.values())
        for p in yukleyen:
            metin = p.read_text(encoding='utf-8')
            assert metin.count("content='{{ upload_limits|tojson }}'") == 1, p.name

    def test_js_dosyalarinda_tavan_sayisi_yok(self):
        """Tavanın bayt değeri, 'N * 1024 * 1024' ifadesi ya da 'N MB'
        yedek metni yükleme JS'lerinde geçmez (CLAUDE.md §11)."""
        tavanlar = set(_beklenen_tavanlar().values())
        mb_degerleri = {v // (1024 * 1024) for v in tavanlar}
        # Birim sabiti (BYTES_PER_MB = 1024 * 1024) serbest; tavanı kuran
        # 'N * 1024 * 1024' ya da 'N * BYTES_PER_MB' yasak.
        carpim = re.compile(r'\b\d+\s*\*\s*(?:1024\s*\*\s*1024|BYTES_PER_MB)\b')
        mb_metin = re.compile(r'\b(\d+)\s*MB\b')
        for yol in YUKLEME_JS:
            kaynak = yol.read_text(encoding='utf-8')
            for v in tavanlar:
                assert str(v) not in kaynak, (yol.name, v)
            assert not carpim.search(kaynak), (yol.name, carpim.findall(kaynak))
            bulunan = {int(m) for m in mb_metin.findall(kaynak)}
            assert not (bulunan & mb_degerleri), (yol.name, bulunan)

    def test_i18n_anahtarlari_en_tr(self):
        """İleti anahtarları EN ve TR sözlüğünde, aynı yer tutucularla."""
        metin = I18N_COMMON.read_text(encoding='utf-8')
        for anahtar in ('imp.tooLarge', 'imp.tooLargeNoLimit'):
            satirlar = re.findall(r"'%s': '([^']*)'" % re.escape(anahtar), metin)
            assert len(satirlar) == 2, (anahtar, satirlar)
            en, tr = satirlar
            assert en != tr
            assert (sorted(re.findall(r'\{\w+\}', en))
                    == sorted(re.findall(r'\{\w+\}', tr))), (en, tr)
            assert '{size}' in en and 'MB' in en and 'MB' in tr


# ---------------------------------------------------------------------------
# 2. node vm koşumu: aşan dosyada fetch yok; 413'te ham gövde yok
# ---------------------------------------------------------------------------
#
# Gerçek JS dosyaları node ``vm`` bağlamında koşulur. DOM en küçük sahteyle
# verilir; ``fetch`` ve ``FileReader`` her çağrıyı sayar. Betik stdin ile
# geçilir (argv DEĞİL: test_node_cagri_sozlesmesi).

_KOSUCU = r"""
const vm = require('vm');
class El {
  constructor(id) { this.id = id || ''; this.style = {}; this.children = [];
    this.dinleyici = {}; this.value = ''; this.textContent = '';
    this.innerHTML = ''; this.disabled = false; this.oznitelik = {}; }
  get firstElementChild() { return new El(); }
  appendChild(c) { this.children.push(c); return c; }
  insertBefore(c) { return c; }
  removeChild() {} remove() {} click() {} dispatchEvent() {}
  setAttribute(k, v) { this.oznitelik[k] = v; }
  getAttribute(k) { return k in this.oznitelik ? this.oznitelik[k] : null; }
  addEventListener(t, f) { (this.dinleyici[t] = this.dinleyici[t] || []).push(f); }
  closest() { return null; } querySelector() { return null; }
  querySelectorAll() { return []; }
}
const kayit = { fetch: [], fileReader: 0, olusan: [] };
const byId = new Map();
for (const id of girdi.idler || []) byId.set(id, new El(id));
const meta = girdi.meta === null ? null : new El('meta');
if (meta) meta.setAttribute('content', girdi.meta);
const document = {
  readyState: 'complete', body: new El('body'),
  createElement() { const e = new El(); kayit.olusan.push(e); return e; },
  getElementById(id) { return byId.get(id) || null; },
  querySelector(s) { return s === 'meta[name="hrma-upload-limits"]' ? meta : null; },
  addEventListener() {},
};
const yanit = girdi.yanit;
async function fetch(url) {
  kayit.fetch.push(url);
  return { status: yanit.status, ok: yanit.status >= 200 && yanit.status < 300,
    async json() { if (yanit.json === null) throw new SyntaxError('Unexpected token H'); return yanit.json; },
    async text() { return yanit.metin; } };
}
class FileReader { constructor() { kayit.fileReader += 1; }
  readAsText(f) { this.result = 'time,thrust\n0,1\n'; setTimeout(() => this.onload && this.onload(), 0); } }
class FormData { append() {} }
const sessiz = { error() {}, warn() {}, log() {} };
const TFyedek = (k, p, fb) => String(fb).replace(/\{(\w+)\}/g, (w, n) =>
  (p && Object.prototype.hasOwnProperty.call(p, n)) ? String(p[n]) : w);
const ctx = { document, fetch, FileReader, FormData, Blob, console: sessiz,
  setTimeout, clearTimeout, setInterval, clearInterval,
  location: { pathname: '/solid' } };
ctx.window = ctx;
if (girdi.dock) {
  ctx.AnalysisDock = { register() {}, ui: { t: (k, fb) => fb, tf: TFyedek,
    purgePlots() {}, listBlock() { return ''; }, motorDict() { return null; },
    readThrust() {}, readBurnTime() {} } };
}
vm.createContext(ctx);
for (const k of girdi.betikler) vm.runInContext(k.kaynak, ctx, { filename: k.ad });
const bekle = () => new Promise(r => setTimeout(r, 5));
(async () => {
  const s = girdi.senaryo; const IU = ctx.HRMAImportUI;
  const sonuc = { hata: null, html: null, durum: null };
  try {
    if (s.tur === 'ork') {
      await IU.postOrk({ size: s.boyut, name: 't.ork' });
    } else if (s.tur === 'motor') {
      await IU.postMotorFile('a'.repeat(s.boyut), 't.eng', null);
    } else if (s.tur === 'step') {
      await ctx.StepImportUI._analyze({ size: s.boyut, name: 't.step' }, null);
      const govde = kayit.olusan.filter(e => e.id === 'stepImportBody').pop();
      sonuc.html = govde ? govde.innerHTML : null;
    } else if (s.tur === 'panel_dosya') {
      const giris = byId.get('vp_csv_file');
      for (const f of giris.dinleyici.change || [])
        f({ target: { files: [{ size: s.boyut, name: s.ad }], value: 'x' } });
      await bekle(); await bekle();
      sonuc.durum = byId.get('ad_status_validation').textContent;
    } else if (s.tur === 'panel_gonder') {
      byId.get('vp_csv_text').value = 'a'.repeat(s.boyut);
      for (const f of byId.get('vp_run').dinleyici.click || []) await f();
      sonuc.durum = byId.get('ad_status_validation').textContent;
    }
  } catch (e) { sonuc.hata = e.message; }
  sonuc.fetch = kayit.fetch; sonuc.fileReader = kayit.fileReader;
  process.stdout.write(JSON.stringify(sonuc));
})();
"""

_PANEL_IDLERI = ['ad_sec_validation', 'ad_status_validation', 'vp_run',
                 'vp_csv_file', 'vp_csv_text', 'ad_root_validation']

#: Sunucu yanıtları (fetch sahtesi). Waitress gövdesi gerçek ölçümdeki
#: biçimdedir (sgw/sonuc/arayuz_metni.json).
YANIT_200 = {'status': 200, 'json': {'status': 'success', 'motors': [],
                                     'motor': None}, 'metin': ''}
YANIT_WAITRESS = {'status': 413, 'json': None,
                  'metin': 'Request Entity Too Large\n\nexceeds max_body\n\n'
                           '(generated by waitress)'}
YANIT_GOVDE_KAPISI = {'status': 413, 'json': {
    'status': 'error', 'error': 'request_body_too_large',
    'limit': 'body_bytes'}, 'metin': ''}
YANIT_SATIR_BANDI = {'status': 413, 'json': {
    'status': 'error', 'error': 'Satir bandi asildi (sunucu iletisi)',
    'reason': 'row_band_exceeded', 'limit': 'data_rows'}, 'metin': ''}


def _kos(senaryo, betikler, yanit=YANIT_200, meta='SUNUCU', dock=False,
         idler=()):
    if meta == 'SUNUCU':
        app.config['TESTING'] = True
        with app.test_client() as c:
            _, meta = _meta(c, '/solid')
    girdi = {'senaryo': senaryo, 'yanit': yanit, 'meta': meta, 'dock': dock,
             'idler': list(idler),
             'betikler': [{'ad': p.name, 'kaynak': p.read_text(encoding='utf-8')}
                          for p in betikler]}
    betik = 'const girdi = JSON.parse(' + json.dumps(json.dumps(girdi)) + ');\n' \
        + _KOSUCU
    out = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


def _ileti(boyut, tavan):
    """Beklenen İngilizce yedek ileti (kâhin: anahtar metni + MB tanımı)."""
    mb = 1024 * 1024
    boyut_mb = '%.1f' % (-(-boyut * 10 // mb) / 10)
    return ('Upload too large: %s MB; the limit for this upload is %d MB.'
            % (boyut_mb, tavan // mb))


@node_gerekli
class TestAsanDosyaGonderilmez:

    @pytest.mark.parametrize('tur,anahtar', [('ork', 'ork'),
                                             ('motor', 'motor_file')])
    def test_import_ui_asan_dosyada_fetch_yok(self, tur, anahtar):
        tavan = _beklenen_tavanlar()[anahtar]
        s = _kos({'tur': tur, 'boyut': tavan + 1}, [IMPORT_UI])
        assert s['fetch'] == [], s
        assert s['hata'] == _ileti(tavan + 1, tavan), s

    @pytest.mark.parametrize('tur,anahtar', [('ork', 'ork'),
                                             ('motor', 'motor_file')])
    def test_import_ui_tavandaki_dosya_gonderilir(self, tur, anahtar):
        """Sınır dahil: tam tavandaki dosya gönderilir (sunucu '>' kuralı)."""
        tavan = _beklenen_tavanlar()[anahtar]
        s = _kos({'tur': tur, 'boyut': tavan}, [IMPORT_UI])
        assert len(s['fetch']) == 1, s
        assert s['hata'] is None, s

    def test_step_asan_dosyada_fetch_yok(self):
        tavan = _beklenen_tavanlar()['step']
        s = _kos({'tur': 'step', 'boyut': tavan + 1}, [IMPORT_UI, STEP_UI])
        assert s['fetch'] == [], s
        assert ('STEP import failed: ' + _ileti(tavan + 1, tavan)) in s['html'], s

    def test_step_tavandaki_dosya_gonderilir(self):
        tavan = _beklenen_tavanlar()['step']
        s = _kos({'tur': 'step', 'boyut': tavan}, [IMPORT_UI, STEP_UI])
        assert s['fetch'] == ['/api/import/step'], s

    @pytest.mark.parametrize('ad,anahtar', [('t.csv', 'csv'),
                                            ('t.eng', 'motor_file')])
    def test_panel_asan_dosya_okunmaz_gonderilmez(self, ad, anahtar):
        tavan = _beklenen_tavanlar()[anahtar]
        s = _kos({'tur': 'panel_dosya', 'boyut': tavan + 1, 'ad': ad},
                 [IMPORT_UI, VALIDATION], dock=True, idler=_PANEL_IDLERI)
        assert s['fetch'] == [] and s['fileReader'] == 0, s
        assert s['durum'] == 'ERROR: ' + _ileti(tavan + 1, tavan), s

    def test_panel_tavan_altindaki_dosya_okunur(self):
        s = _kos({'tur': 'panel_dosya', 'boyut': 10, 'ad': 't.csv'},
                 [IMPORT_UI, VALIDATION], dock=True, idler=_PANEL_IDLERI)
        assert s['fileReader'] == 1, s

    def test_panel_csv_govdesi_tavani_asarsa_gonderilmez(self):
        """Yapıştırılan metin dahil GÖVDE baytı denetlenir."""
        tavan = _beklenen_tavanlar()['csv']
        s = _kos({'tur': 'panel_gonder', 'boyut': tavan},
                 [IMPORT_UI, VALIDATION], dock=True, idler=_PANEL_IDLERI)
        assert s['fetch'] == [], s
        govde = len(json.dumps({'csv_text': 'a' * tavan}, separators=(',', ':')))
        assert s['durum'] == 'ERROR: ' + _ileti(govde, tavan), s

    def test_sixdof_motor_dosyasi_okumadan_once_denetlenir(self):
        """6-DOF paneli (2000+ satır DOM) node'da kurulmaz; denetim çağrısının
        okumadan ÖNCE durduğu kaynaktan ölçülür. .ork yolu postOrk'tan geçer
        (yukarıda koşuldu)."""
        kaynak = SIXDOF.read_text(encoding='utf-8')
        i = kaynak.index('async function onMotorFileChosen(')
        govde = kaynak[i:kaynak.index('async function', i + 10)]
        denetim = govde.find("assertUploadSize('motor_file', file.size)")
        okuma = govde.find('readFileAsText(file)')
        assert 0 <= denetim < okuma, (denetim, okuma)
        j = kaynak.index('async function onOrkFileChosen(')
        assert 'HRMAImportUI.postOrk(file)' in kaynak[j:j + 600]


@node_gerekli
class TestSunucu413HamGovdeYok:

    @pytest.mark.parametrize('yanit', [YANIT_WAITRESS, YANIT_GOVDE_KAPISI],
                             ids=['waitress_duz_metin', 'json_govde_kapisi'])
    @pytest.mark.parametrize('tur,anahtar', [('ork', 'ork'),
                                             ('motor', 'motor_file')])
    def test_import_ui_413_ayni_ileti(self, tur, anahtar, yanit):
        tavan = _beklenen_tavanlar()[anahtar]
        s = _kos({'tur': tur, 'boyut': 100}, [IMPORT_UI], yanit=yanit)
        assert len(s['fetch']) == 1, s
        assert s['hata'] == _ileti(100, tavan), s

    @pytest.mark.parametrize('yanit', [YANIT_WAITRESS, YANIT_GOVDE_KAPISI],
                             ids=['waitress_duz_metin', 'json_govde_kapisi'])
    def test_step_413_ayni_ileti(self, yanit):
        tavan = _beklenen_tavanlar()['step']
        s = _kos({'tur': 'step', 'boyut': 100}, [IMPORT_UI, STEP_UI],
                 yanit=yanit)
        assert s['fetch'] == ['/api/import/step'], s
        assert ('STEP import failed: ' + _ileti(100, tavan)) in s['html'], s
        for ham in ('waitress', 'request_body_too_large', 'HTTP 413'):
            assert ham not in s['html'], (ham, s['html'])

    @pytest.mark.parametrize('yanit', [YANIT_WAITRESS, YANIT_GOVDE_KAPISI],
                             ids=['waitress_duz_metin', 'json_govde_kapisi'])
    def test_panel_csv_413_ayni_ileti(self, yanit):
        tavan = _beklenen_tavanlar()['csv']
        s = _kos({'tur': 'panel_gonder', 'boyut': 10}, [IMPORT_UI, VALIDATION],
                 yanit=yanit, dock=True, idler=_PANEL_IDLERI)
        assert len(s['fetch']) == 1, s
        govde = len(json.dumps({'csv_text': 'a' * 10}, separators=(',', ':')))
        assert s['durum'] == 'ERROR: ' + _ileti(govde, tavan), s

    def test_csv_satir_bandi_413_sunucu_iletisi_kalir(self):
        """Satır bandı boyut reddi değildir: boyut iletisine ÇEVRİLMEZ."""
        s = _kos({'tur': 'panel_gonder', 'boyut': 10}, [IMPORT_UI, VALIDATION],
                 yanit=YANIT_SATIR_BANDI, dock=True, idler=_PANEL_IDLERI)
        assert s['durum'] == 'ERROR: Satir bandi asildi (sunucu iletisi)', s

    def test_tavan_yoksa_on_denetim_yok_413_tavansiz_ileti(self):
        """Meta yoksa ön denetim yapılmaz (asıl kapı sunucu); 413 yine ham
        gövde değil tavansız i18n iletisiyle basılır."""
        s = _kos({'tur': 'ork', 'boyut': 10 ** 9}, [IMPORT_UI],
                 yanit=YANIT_WAITRESS, meta=None)
        assert len(s['fetch']) == 1, s
        assert s['hata'] == 'Upload too large: 953.7 MB.', s

    @pytest.mark.parametrize('bozuk', ['{"ork": "20"}', '{"ork": -1}',
                                       '{"ork": 1.5}', 'bozuk-json', '[]'])
    def test_gecersiz_tavan_okunmaz(self, bozuk):
        """Fail-closed okuma: sayı olmayan/negatif/kesirli tavan yok sayılır."""
        s = _kos({'tur': 'ork', 'boyut': 10}, [IMPORT_UI], meta=bozuk)
        assert len(s['fetch']) == 1 and s['hata'] is None, s
