"""ÖH D36 · kulvar **sahne-hud** · a2 — bekçi.

Kalemler (kanıt: docs/scofield/raw/OH/D36/sahne-hud/a2/):
  1. OH-P-14 (Three.js ayağı) — 3B güverte TÜRKÇE arayüzde HİÇ kurulmuyordu:
     D35 sayı kanonu alev dokusunun CSS renk dizesini ekran
     biçimlendiricisinden geçiriyordu ('rgba(255,255,255,1,0000)'),
     `addColorStop` SyntaxError atıyor, MotorScene kurucusu çöküyordu.
     Ölçüldü: canlı tarayıcı, /solid, TR, `show3DVisualization()`.
     Renk dizesi makine kanalıdır: NOKTA kalır.
  2. HUD/güverte sayı biçimi taraması (cfd_panel.js) — Merkez CFD
     görünümünün künye tablolarında panelin KENDİ biçimlediği sayılar
     (`fmtExp`, `fmtAuto`, `sig` metne dökülüp birleştirilen yollar) TR'de
     NOKTA basıyordu; aynı hücrede "43442.7 / 5,430" gibi iki ayraç.

ÖLÇÜM YÖNTEMİ: GERÇEK dosyalar node altında koşar (kaynak DOSYADAN
okunur; inspect.getsource YOK); i18n motoru gerçek i18n.js'tir.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

# Tarayıcının kabul ettiği rgba() sözdizimi (alfa: 0..1, nokta ondalık)
CSS_RGBA = re.compile(r'^rgba\(\d{1,3},\d{1,3},\d{1,3},(?:0|1|\d?\.\d+)\)$')


def _node(script, argv=(), timeout=300):
    env = dict(os.environ)
    env['HRMA_ARGS'] = json.dumps([str(a) for a in argv])
    p = subprocess.run([NODE], input=script, env=env,
                       capture_output=True, text=True, timeout=timeout)
    assert p.returncode == 0, 'node çöktü:\n' + p.stderr[-3000:]
    return json.loads(p.stdout)


def _blok(src, baslangic):
    start = src.index(baslangic)
    depth, i = 0, start
    while i < len(src):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError(baslangic + ' kapanmıyor')


def _fn(src, name):
    return _blok(src, 'function %s(' % name)


def _viz_src():
    return (JS / 'motor_viz3d.js').read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# 1) Alev dokusu — CSS renk dizesi makine kanalıdır
# ---------------------------------------------------------------------------
def _alev_renkleri(lang):
    src = _viz_src()
    m = re.search(r'var FLAME_SPRITE_SIGMA = [^;]+;', src)
    assert m
    parcalar = [m.group(0), _fn(src, 'flameSpriteAlpha'), _fn(src, 'flameSpriteStops'),
                _fn(src, 'numTxt'), _fn(src, 'cssAlpha'), _fn(src, 'flameSpriteTexture')]
    script = r"""
global.window = global;
global.document = { documentElement: { lang: 'en', setAttribute() {}, getAttribute() { return null; } },
                    readyState: 'complete', addEventListener() {}, dispatchEvent() {},
                    querySelectorAll() { return []; }, getElementById() { return null; } };
Object.defineProperty(global, 'localStorage', { value: { getItem() { return null; }, setItem() {} }, configurable: true });
Object.defineProperty(global, 'navigator', { value: { language: 'en' }, configurable: true });
const [i18nPath, lang, rgbaRe] = JSON.parse(process.env.HRMA_ARGS);
require(i18nPath); window.I18N.setLang(lang);
const RE = new RegExp(rgbaRe);
const renkler = [];
// Tarayıcı davranışı: çözülemeyen renk SyntaxError atar (Chrome ölçüldü)
function makeCanvas(w, h) {
    return { width: w, height: h, getContext() { return {
        createRadialGradient() { return { addColorStop(t, c) {
            renkler.push(c);
            if (!RE.test(c)) { const e = new SyntaxError("Failed to execute 'addColorStop' on 'CanvasGradient': The value provided ('" + c + "') could not be parsed as a color."); throw e; }
        } }; },
        fillRect() {}, set fillStyle(v) {} }; } };
}
const THREE = { CanvasTexture: function (c) { this.image = c; }, LinearFilter: 1006 };
""" + '\n'.join(parcalar) + r"""
let hata = null;
try { flameSpriteTexture(); } catch (e) { hata = String(e && e.message || e); }
process.stdout.write(JSON.stringify({ hata: hata, renkler: renkler }));
"""
    return _node(script, [JS / 'i18n.js', lang, CSS_RGBA.pattern])


class TestAlevDokusuMakineKanali:
    @pytest.mark.parametrize('lang', ['tr', 'en'])
    def test_doku_her_dilde_kurulur(self, lang):
        out = _alev_renkleri(lang)
        assert out['hata'] is None, (
            '%s kipinde alev dokusu (dolayısıyla 3B sahne) kurulamıyor: %s'
            % (lang, out['hata']))
        assert len(out['renkler']) == 9, out
        assert all(CSS_RGBA.match(c) for c in out['renkler']), out['renkler']

    def test_kaynakta_renk_dizesine_ekran_bicimleyici_girmez(self):
        """CSS renk dizesi (rgba/rgb/hsl) kuran HİÇBİR ifade ekran sayı
        biçimleyicisinden (numTxt/unitTxt/pctTxt/decTxt/I18N.number/_num/
        fmt*) geçmez — dört kulvar dosyasında."""
        bicimleyici = re.compile(
            r'\b(numTxt|unitTxt|pctTxt|decTxt|_num|fmt|fmtAuto|fmtExp|sig)\(|I18N\.(number|unit|percent|decimalText)')
        ihlal = []
        for ad in ('motor_viz3d.js', 'motor_viz_deck.js', 'hud.js', 'panels/cfd_panel.js'):
            src = (JS / ad).read_text(encoding='utf-8')
            for m in re.finditer(r"""['"](?:rgba?|hsla?)\(""", src):
                ifade = src[m.start():src.find(';', m.start())]
                if bicimleyici.search(ifade):
                    ihlal.append((ad, src.count('\n', 0, m.start()) + 1, ifade[:120]))
        assert not ihlal, 'renk dizesi ekran biçimleyicisinden geçiyor: %r' % ihlal


# ---------------------------------------------------------------------------
# 2) cfd_panel.js — Merkez CFD görünümünde panelin kendi biçimlediği sayılar
# ---------------------------------------------------------------------------
from tests.test_d36_sahne_a1 import _merkez, yukler  # noqa: E402,F401  (fixture)

ONDALIK_NOKTA_TOKEN = re.compile(r'(?<![\w.])[-+]?\d+\.\d+(?:e[-+]?\d+)?(?![\w.])')
KUNYE_SATIRI = re.compile(r'\b[a-z_][a-z0-9_.]*_(?:Pa|m|W|N|K|s)?\s*=\s*$|\b[a-z_]+\.[a-z_]+\s*=\s*$')


def _cfd_gorunum(tmp_path, lang, yukler):
    motor, yanit = yukler
    out = _merkez(tmp_path, lang, motor, yanit)
    metin = re.sub(r'<[^>]+>', ' ', out['nodes']['ac_view_root']['html'] or '')
    metin = (metin.replace('&quot;', '"').replace('&gt;', '>')
             .replace('&lt;', '<').replace('&amp;', '&'))
    return metin, json.dumps(yanit)


def _panel_noktalilari(metin, yanit_json):
    """Yanıtta AYNEN geçmeyen (yani panelin kendi biçimlediği) ve bir künye
    satırının (`alan_adı = değer`) değeri OLMAYAN noktalı ondalıklar."""
    kalan = []
    for m in ONDALIK_NOKTA_TOKEN.finditer(metin):
        t = m.group(0)
        if t in yanit_json:
            continue
        once = metin[max(0, m.start() - 60):m.start()]
        # künye: "threshold_Pa = 5308.1 … 5308.1" — ilk ve ikinci değer
        if re.search(r'[a-z_]+_[A-Za-z]+ = [^=]*$', once):
            continue
        kalan.append((t, metin[max(0, m.start() - 40):m.end() + 10]))
    return kalan


class TestCfdPanelSayiBicimi:
    def test_tr_panel_sayilari_virgullu(self, tmp_path, yukler):
        metin, yj = _cfd_gorunum(tmp_path, 'tr', yukler)
        kalan = _panel_noktalilari(metin, yj)
        assert not kalan, 'TR CFD görünümünde panelin noktalı sayısı: %r' % kalan[:8]
        # Örnek aileler: üstel (kalıntı), sigFig (duvar basıncı), süre
        assert re.search(r'\d,\d+e-\d', metin), 'üstel sayılar virgüllü değil'
        assert 'hücre; en kötü hâl' in metin, 'ızgara seviyesi satırı Türkçe değil'
        assert 'cells; worst case' not in metin

    def test_kunye_satiri_makine_kalir(self, tmp_path, yukler):
        """`alan_adı = değer` künyeleri makinedir: TR'de de NOKTA (D33-3
        fix-38a ayrımı). Ayraç yalnız ekran cümle/hücrelerinde değişir."""
        metin, _ = _cfd_gorunum(tmp_path, 'tr', yukler)
        m = re.search(r'threshold_Pa = (\S+) … (\S+)', metin)
        assert m, 'künye satırı yok'
        assert ',' not in m.group(1) + m.group(2), m.group(0)

    def test_en_kipinde_degismedi(self, tmp_path, yukler):
        metin, yj = _cfd_gorunum(tmp_path, 'en', yukler)
        assert 'cells; worst case' in metin
        # Virgüllü üstel sayı EN'de yalnız ucun KENDİ (Türkçe yazılmış)
        # beyanında geçebilir; panelin biçimlediği hiçbir sayı virgüllü değil.
        panel = [t for t in re.findall(r'\d+,\d+e-\d+', metin) if t not in yj]
        assert not panel, panel[:5]

    def test_kaynak_decTxt_kanali(self):
        src = (JS / 'panels' / 'cfd_panel.js').read_text(encoding='utf-8')
        for ad in ('fmtExp', 'fmtAuto', 'sig'):
            assert 'decTxt(' in _fn(src, ad), '%s ayraç kanalından geçmiyor' % ad
        assert 'decTxt' not in _fn(src, 'sigRaw')
        # künye dökümleri makine yolunda
        assert src.count("sigRaw(bf.") == 4
        assert "kunye.push('criteria_spread.separation_z_m = '\n                           + sigRaw(" in src
        assert "'{ni}x{nj} = {n} cells; worst case {cases}'" in src
        common = (JS / 'i18n_common.js').read_text(encoding='utf-8')
        assert common.count("'panel.cfd.levelRow':") == 2
        assert "'panel.cfd.levelRow': '{ni}x{nj} = {n} hücre; en kötü hâl {cases}'" in common


# ---------------------------------------------------------------------------
# 3) OH-P-08 — Analiz Merkezi'nin kendi İngilizce kalıntıları
# ---------------------------------------------------------------------------
from tests.test_d36_sahne_a1 import _merkez_harness  # noqa: E402

#: Merkez'in yük tavanı (analysis_center.js GECMIS_YUK_TAVANI) — kaynaktan
#: okunur, testte ikinci kopya yazılmaz.
_YUK_TAVANI = int(re.search(r'const GECMIS_YUK_TAVANI = (\d+);',
                            (JS / 'analysis_center.js').read_text(encoding='utf-8')).group(1))


def _merkez_gecmis(tmp_path, lang, yukler):
    """Tavanı aşan sayıda koşum → en eski kaydın yükü bırakılır → o kayıt
    görüntüleyicide açılır. Ekrandaki TÜM düğümlerin metni döner."""
    motor, yanit = yukler
    h = _merkez_harness()
    kanca = '    // ÖH D36: aynı yanıtı yeniden çiz'
    assert h.count(kanca) == 1
    h = h.replace(kanca, "    if (payload.showFirst) { const hh = AC.history();"
                  " AC.showHistoryEntry(hh[0].id); }\n" + kanca)
    betik = tmp_path / ('kos_gecmis_%s.js' % lang)
    betik.write_text(h, encoding='utf-8')
    payload = {'motorType': 'solid', 'results': motor, 'response': yanit,
               'select': ['nozzle_flow', 'cfd'], 'runs': _YUK_TAVANI + 2,
               'showFirst': True, 'lang': lang,
               'i18nPath': str(JS / 'i18n.js'),
               'commonPath': str(JS / 'i18n_common.js'),
               'chartsPath': str(JS / 'i18n_charts.js')}
    girdi = tmp_path / ('girdi_gecmis_%s.json' % lang)
    girdi.write_text(json.dumps(payload), encoding='utf-8')
    p = subprocess.run([NODE, str(betik), str(girdi),
                        str(JS / 'analysis_center.js'),
                        str(JS / 'panels' / 'cfd_panel.js')],
                       capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, p.stderr[-3000:]
    out = json.loads(p.stdout)
    return ' '.join((v.get('html') or '') + ' ' + (v.get('text') or '')
                    for v in out['nodes'].values())


class TestMerkezIngilizceKalintisi:
    def test_tr_yuk_birakildi_ve_gecmis_seridi_turkce(self, tmp_path, yukler):
        metin = _merkez_gecmis(tmp_path, 'tr', yukler)
        assert 'data-ac-payload-released' in metin, 'yük bırakılan kayıt açılmadı'
        assert 'koşum yükü bellekten bırakıldı (GECMIS_YUK_TAVANI = %d)' % _YUK_TAVANI in metin
        assert '(yük bırakıldı)' in metin
        assert 'geçmişi temizle (' in metin
        for en in ('run payload released', '(payload released)', 'clear history ('):
            assert en not in metin, 'TR Merkez ekranında İngilizce: %r' % en

    def test_en_metinler_korunur(self, tmp_path, yukler):
        metin = _merkez_gecmis(tmp_path, 'en', yukler)
        assert 'run payload released (GECMIS_YUK_TAVANI = %d)' % _YUK_TAVANI in metin
        assert '(payload released)' in metin and 'clear history (' in metin

    def test_kaynakta_ciplak_ingilizce_yok(self):
        src = (JS / 'analysis_center.js').read_text(encoding='utf-8')
        kod = re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', src, flags=re.S))
        assert "esc('analysis_center: run payload released" not in kod
        assert "+ '(payload released)</span>'" not in kod
        assert "esc('clear history ('" not in kod
        common = (JS / 'i18n_common.js').read_text(encoding='utf-8')
        for k in ('ac.view.payloadReleased', 'ac.history.released', 'ac.history.clear'):
            assert common.count("'%s':" % k) == 2, k
