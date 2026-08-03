"""Faz 6 — tarayıcı denetiminden kalan çeviri kalemlerinin bekçileri.

Kapsam (G1-i18n, 3 Ağustos 2026). Bu dosya YALNIZ sözlük dosyalarını
kilitler:

  * hrma/static/js/i18n_pages.js  — T49-yan (inhibitör ipuçları), T25
    (yakıt bloğu boyu ipucu)
  * hrma/static/js/i18n_charts.js — T43/T06 (yeni grafik metinlerinin TR
    karşılığı), T64 (yarı çevrili iz adları)

Her testin ölçülmüş bir dayanağı var ve her biri KUSURUN KENDİSİNİ sınar,
"mevcut hâli" değil: düzeltme geri alınırsa test kırmızıya döner (geri alma
denemesi 3 Ağustos 2026'da yapıldı, dördü de kırıldı).

Grafik testleri gerçek i18n.js + i18n_charts.js dosyalarını node içinde
çalıştırır; sözlüğü Python tarafında yeniden ayrıştırmak yerine ÇEVİRİ
MOTORUNU çağırır, çünkü kusur (T64) tam olarak sözlük ile desen kuralları
arasındaki sıralamadaydı — sözlüğe bakan bir test onu göremezdi.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PAGES_JS = STATIC_JS / 'i18n_pages.js'
CHARTS_JS = STATIC_JS / 'i18n_charts.js'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


# ---------------------------------------------------------------------------
# Sözlük ayrıştırma (i18n_pages.js)
# ---------------------------------------------------------------------------
def _lang_block(source, lang):
    """Bir dil bloğunun gövdesi (süslü parantez sayarak, tırnak farkında)."""
    match = re.search(r'\b%s\s*:\s*\{' % lang, source)
    assert match, "'%s' sözlük bloğu bulunamadı" % lang
    idx, depth = match.end() - 1, 0
    quote, escaped = None, False
    while idx < len(source):
        ch = source[idx]
        if quote:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in '\'"`':
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return source[match.end():idx]
        idx += 1
    raise AssertionError("'%s' bloğu kapanmıyor" % lang)


PAIR_RE = re.compile(r"^\s*'([^']+)':\s*'(.*)',?\s*$", re.M)


@pytest.fixture(scope='module')
def pages_dict():
    source = PAGES_JS.read_text(encoding='utf-8')
    out = {}
    for lang in ('en', 'tr'):
        pairs = PAIR_RE.findall(_lang_block(source, lang))
        out[lang] = {k: v.rstrip("',") for k, v in pairs}
    assert out['en'] and out['tr'], 'i18n_pages.js ayrıştırılamadı'
    return out


# ---------------------------------------------------------------------------
# T49-yan — inhibitör ipuçları varsayılanın TERSİNİ önermemeli
# ---------------------------------------------------------------------------
# Ölçüldü (BATES 100/30/500 mm, 3 segment, APCP; calculate_performance):
#   uçlar AÇIK  + dış KAPLI  -> neutral      Kn 160,6 -> 163,8  (+%2,0)
#   uçlar KAPLI + dış KAPLI  -> progressive  Kn 161,9 -> 242,1  (+%49,5)
#   uçlar KAPLI + dış AÇIK   -> regressive   Kn 149,4 -> 113,1  (-%24,3)
# Form kutuları işaretsiz gelir, yani varsayılan BİRİNCİ satırdır; eski ipucu
# metni ise "Usually inhibited" diyerek üçüncü satırı öneriyordu.
INHIBITOR_KEYS = (
    'solid.ui.prevents_burning_on_forward_end_face',
    'solid.ui.prevents_burning_on_aft_end_face',
)


@pytest.mark.parametrize('key', INHIBITOR_KEYS)
def test_t49_inhibitor_ipucu_varsayilani_onermiyor(pages_dict, key):
    """İpucu 'genellikle kaplanır' DEMEMELİ — kutular işaretsiz geliyor."""
    en = pages_dict['en'][key]
    tr = pages_dict['tr'][key]
    assert 'usually inhibited' not in en.lower(), (
        '%s: ipucu hâlâ kaplamayı olağan diye sunuyor, oysa kutu işaretsiz '
        'geliyor ve o düzende yanma nötr değil regresif oluyor:\n  %s'
        % (key, en))
    assert 'genellikle kaplanır' not in tr.lower(), (
        '%s: TR ipucu hâlâ kaplamayı olağan diye sunuyor:\n  %s' % (key, tr))


@pytest.mark.parametrize('key', INHIBITOR_KEYS)
def test_t49_inhibitor_ipucu_acik_uclari_gerekcelendiriyor(pages_dict, key):
    """İpucu, uçların NEDEN açık bırakıldığını söylemeli (nötr yanma)."""
    en = pages_dict['en'][key].lower()
    tr = pages_dict['tr'][key]
    assert 'exposed' in en and 'neutral' in en, (
        '%s: EN ipucu açık uç yüzeylerin nötr yanmayı sağladığını '
        'söylemiyor:\n  %s' % (key, pages_dict['en'][key]))
    # DİKKAT: Türkçe metinde .lower() KULLANILMAZ — Python 'AÇIK' -> 'açik'
    # üretir (I -> i), aranan sözcük hiçbir zaman eşleşmez.
    assert 'AÇIK' in tr and 'nötr' in tr, (
        '%s: TR ipucu açık uç yüzeylerin nötr yanmayı sağladığını '
        'söylemiyor:\n  %s' % (key, tr))


def test_t49_iki_uc_ipucu_ayni_gerekceyi_veriyor(pages_dict):
    """Ön ve arka yüz aynı fizik: gerekçe metni ayrışmamalı."""
    on = pages_dict['tr'][INHIBITOR_KEYS[0]]
    arka = pages_dict['tr'][INHIBITOR_KEYS[1]]
    ortak = 'BATES yığınında uç yüzler AÇIK bırakılır'
    assert ortak in on and ortak in arka, \
        'iki uç ipucu aynı gerekçeyi taşımıyor; biri güncellenmemiş olabilir'


# ---------------------------------------------------------------------------
# T25 — 'Grain Length' ipucu TOPLAM yığın boyunu anlatmalı
# ---------------------------------------------------------------------------
# Davranış zaten düzeltildi (test_faz6_f1a_kati.py::
# test_t25_grain_length_is_treated_as_total_stack): grain_count yakıt
# kütlesini değiştirmiyor. Burada kilitlenen, kullanıcıya GÖRÜNEN metin.
GRAIN_LEN_KEY = 'solid.ui.axial_length_of_individual_propellant_grain'


def test_t25_ipucu_tek_blok_yorumunu_kullanmiyor(pages_dict):
    en = pages_dict['en'][GRAIN_LEN_KEY]
    tr = pages_dict['tr'][GRAIN_LEN_KEY]
    assert 'individual propellant grain' not in en.lower(), (
        'ipucu hâlâ "tek blok" diyor, oysa çözücü alanı toplam yığın sayıp '
        'segment sayısına bölüyor:\n  %s' % en)
    assert 'tek bir yakıt bloğunun' not in tr.lower(), (
        'TR ipucu hâlâ "tek blok" diyor:\n  %s' % tr)


def test_t25_ipucu_toplam_yigin_diyor(pages_dict):
    en = pages_dict['en'][GRAIN_LEN_KEY].lower()
    tr = pages_dict['tr'][GRAIN_LEN_KEY].lower()
    assert 'total axial length' in en and 'segment' in en, (
        'EN ipucu toplam yığın boyunu ve segment bölünmesini anlatmıyor:\n  %s'
        % pages_dict['en'][GRAIN_LEN_KEY])
    assert 'toplam eksenel uzunluğu' in tr and 'segment' in tr, (
        'TR ipucu toplam yığın boyunu ve segment bölünmesini anlatmıyor:\n  %s'
        % pages_dict['tr'][GRAIN_LEN_KEY])


# ---------------------------------------------------------------------------
# Grafik çeviri motoru düzeneği (gerçek dosyalar, node içinde)
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const ROOT = process.argv[2];
const TEXTS = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

function makeDoc() {
    return {
        readyState: 'complete',
        documentElement: { setAttribute() {}, appendChild() {} },
        head: { appendChild() {} },
        createElement: () => ({ setAttribute() {}, appendChild() {}, style: {} }),
        getElementById: () => null,
        querySelector: (sel) => (sel.indexOf('i18n_charts.js') >= 0 ? {} : null),
        querySelectorAll: () => [],
        addEventListener() {},
        dispatchEvent: () => true,
    };
}

const sandbox = {
    console, setTimeout, clearTimeout, setInterval, clearInterval,
    JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error,
};
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.document = makeDoc();
sandbox.localStorage = null;
sandbox.CustomEvent = function (type, init) {
    this.type = type;
    this.detail = (init && init.detail) || null;
};
sandbox.Plotly = { newPlot() {}, react() {} };
vm.createContext(sandbox);
for (const f of ['i18n.js', 'i18n_charts.js', 'plotly_dark.js']) {
    vm.runInContext(fs.readFileSync(ROOT + '/' + f, 'utf8'), sandbox, { filename: f });
}
const out = {};
sandbox.I18N.setLang('tr');
out.tr = TEXTS.map((s) => sandbox.I18N.chartText(s));
sandbox.I18N.setLang('en');
out.en = TEXTS.map((s) => sandbox.I18N.chartText(s));
process.stdout.write(JSON.stringify(out));
"""

#: Ölçülen kusurlar (3 Ağustos 2026, düzeltme ÖNCESİ TR çıktısı yanda):
#:   'Impinging pairs (angle not reported)' -> 'Çarpışmalı çiftler (angle not reported)'
#:   'Spray cone (angle not reported)'      -> aynen İngilizce
#:   'Final port ... (web fully consumed)'  -> 'Son port ... (web fully consumed)'
#:   'Liner / annulus', 'Injection Velocity', 'Circuit', 'Inj. inlet' ...
#:                                          -> aynen İngilizce (sözlükte yoktu)
BEKLENEN_TR = {
    # T64 — sözlük/desen sıralaması
    'Impinging pairs (angle not reported)': 'Çarpışmalı çiftler (açı bildirilmedi)',
    'Spray cone (angle not reported)': 'Püskürtme konisi (açı bildirilmedi)',
    'Annulus gap (not reported)': 'Halka boşluğu (bildirilmedi)',
    # T64 — efsane adının HOVER karşılığı: biri Türkçe biri İngilizce kalırsa
    # kusur yarı yarıya sürüyor demektir (aynı iz, aynı ekran).
    'Hollow-cone spray<br>Cone angle not reported by the solver '
    '(drawn schematically)<extra></extra>':
        'İçi boş konik püskürtme<br>Koni açısı çözücü tarafından bildirilmedi '
        '(şematik çizim)<extra></extra>',
    'Hollow-cone spray<br>Full angle: 60.0 deg<extra></extra>':
        'İçi boş konik püskürtme<br>Tam açı: 60.0 derece<extra></extra>',
    'Like-on-like doublet<br>Included angle not reported by the solver '
    '(drawn schematically)<extra></extra>':
        'Benzer-benzere çift jet<br>Kesişme açısı çözücü tarafından '
        'bildirilmedi (şematik çizim)<extra></extra>',
    'Tangential slots': 'Teğetsel yarıklar',
    'Tangential slot (swirl generator)<extra></extra>':
        'Teğetsel yarık (girdap üreteci)<extra></extra>',
    # Açı GERÇEKTEN bildirildiğinde desen kuralı çalışmaya devam etmeli
    'Impinging pairs (2θ=60°)': 'Çarpışmalı çiftler (2θ=60°)',
    'Spray cone 2θ=60°': 'Püskürtme konisi 2θ=60°',
    # T43 — yeni/değişmiş üretici metinler
    'Liner / annulus': 'Astar / halka boşluğu',
    'Injection Velocity': 'Enjeksiyon Hızı',
    'Injection Velocity (m/s)': 'Enjeksiyon Hızı (m/s)',
    'Oxidizer Injection Velocity': 'Oksitleyici Enjeksiyon Hızı',
    'Circuit': 'Devre',
    'Inj. inlet': 'Enj. girişi',
    # T43 — 'Final port' sonek kuralı GENEL kuraldan önce gelmeli
    'Final port Ø99.8 mm (web fully consumed)': 'Son port Ø99.8 mm (web tamamen tükendi)',
    'Final port Ø42.0 mm': 'Son port Ø42.0 mm',
}


@pytest.fixture(scope='module')
def chart_ceviri(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    workdir = tmp_path_factory.mktemp('faz6_i18n')
    harness = workdir / 'harness.js'
    harness.write_text(HARNESS, encoding='utf-8')
    texts = workdir / 'texts.json'
    metinler = sorted(BEKLENEN_TR)
    texts.write_text(json.dumps(metinler), encoding='utf-8')
    proc = subprocess.run([NODE, str(harness), str(STATIC_JS), str(texts)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, 'node düzeneği düştü:\n%s' % proc.stderr
    data = json.loads(proc.stdout)
    return {
        'tr': dict(zip(metinler, data['tr'])),
        'en': dict(zip(metinler, data['en'])),
    }


@needs_node
@pytest.mark.parametrize('kaynak', sorted(BEKLENEN_TR))
def test_grafik_metni_turkceye_cevriliyor(chart_ceviri, kaynak):
    """T43 + T64: bu metinlerin TR karşılığı birebir tutmalı."""
    assert chart_ceviri['tr'][kaynak] == BEKLENEN_TR[kaynak], (
        '%r yanlış çevrildi:\n  beklenen: %r\n  gelen    : %r'
        % (kaynak, BEKLENEN_TR[kaynak], chart_ceviri['tr'][kaynak]))


@needs_node
@pytest.mark.parametrize('kaynak', sorted(BEKLENEN_TR))
def test_grafik_metninde_ingilizce_kalinti_yok(chart_ceviri, kaynak):
    """Yarı çeviri yasağı — T64 kusurunun tam olarak bu yüzü kırılmıştı.

    Desen kuralı parantez içini olduğu gibi kopyaladığı için TR ekranda
    'Çarpışmalı çiftler (angle not reported)' görünüyordu.
    """
    cikti = chart_ceviri['tr'][kaynak]
    for kalinti in ('angle not reported', 'not reported', 'web fully consumed'):
        assert kalinti not in cikti, (
            '%r çevirisinde İngilizce kalıntı var (%r):\n  %s'
            % (kaynak, kalinti, cikti))


@needs_node
@pytest.mark.parametrize('kaynak', sorted(BEKLENEN_TR))
def test_ingilizce_dilinde_metne_dokunulmuyor(chart_ceviri, kaynak):
    """EN sözleşmesi: chartText İngilizcede metni AYNEN döndürür."""
    assert chart_ceviri['en'][kaynak] == kaynak, (
        'EN dilinde metin değişti: %r -> %r'
        % (kaynak, chart_ceviri['en'][kaynak]))


# ---------------------------------------------------------------------------
# Sıralama sözleşmesi (kaynak düzeyi) — davranış testinin gerekçesi
# ---------------------------------------------------------------------------
def test_final_port_sonek_kurali_genel_kuraldan_once():
    """applyPatterns ilk eşleşmeyi uygular; özel kural önde durmalı.

    Bu kaynak testi davranış testini TEKRARLAMAZ: davranış testi yanlış
    çıktıyı yakalar, bu test NEDENİ (sıra) bozulduğunda parmak basar.
    """
    src = CHARTS_JS.read_text(encoding='utf-8')
    ozel = src.find(r'/^Final port (.+) \(web fully consumed\)$/')
    genel = src.find(r'/^Final port (.+)$/')
    assert ozel != -1, 'web tamamen tükendi kuralı kaldırılmış'
    assert genel != -1, 'genel Final port kuralı kaldırılmış'
    assert ozel < genel, \
        'özel kural genel kuraldan SONRA geliyor; sonek İngilizce kalır'


def test_olu_grafik_kayitlari_geri_gelmedi():
    """Artık üretilmeyen iki kayıt sözlükten çıkarıldı, geri gelmemeli.

    'Liner (insulation)' yerine visualization.py:3669 artık
    'Liner / annulus' üretiyor; 'Injector Performance' iz adını hiçbir
    üretici üretmiyor (3 Ağustos 2026 taraması).
    """
    src = CHARTS_JS.read_text(encoding='utf-8')
    for olu in ("'Liner (insulation)'", "'Injector Performance'"):
        assert olu not in src, '%s ölü kaydı geri gelmiş' % olu
