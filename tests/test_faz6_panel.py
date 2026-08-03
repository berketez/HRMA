"""Faz 6 / G3-panel — panel ve şablon bulgularının bekçileri.

3 Ağustos 2026 tarayıcı denetiminin, düzeltme dalgasında dosya sahipliği
sınırına takılan dört kalemi burada kilitlenir. Her test ÖLÇÜLMÜŞ doğru
davranışı sınar; düzeltme geri alınınca test KIRILIR (her testin altında
geri-alma denemesinin sonucu yazılıdır):

  T12  aynı sayfadaki iki panel FARKLI roket uçuruyordu — yörünge paneli
       kuru 25 kg / Ø150 mm / Cd 0,50, 6-DOF paneli kuru 8 kg / Ø100 mm /
       Cd₀ 0,45 (kütlede 3,1 kat, alın kesitinde 2,25 kat fark)
  T48  panel açıklaması "lineer küçük-α (alpha < 15 deg)" diyordu ama bu
       sınır α grafiğinde HİÇ çizilmiyordu
  T65  termal panelin sıcaklık grafiğinde x ekseni başlığı BOŞ DİZEYDİ
       ({"text":"", "font":{...}, "standoff":8}) — "unuttuk" ile "gerekmiyor"
       aynı görünüyordu
  T74  /launch-site sayfasında dil değişince araç rozeti, araç notu ve karo
       göstergesi ESKİ DİLDE kalıyordu (textContent ile bir kez basılıp bir
       daha tazelenmediği için)

Ölçüm yöntemi: JS tarafı gerçek `node` ile koşturulur (Plotly gerekmeyen saf
fonksiyonlar dosyadan kesilir); şablon tarafı yapısal olarak sınanır.
"""

import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'

SIXDOF_JS = STATIC_JS / 'sixdof_panel.js'
THERMAL_JS = STATIC_JS / 'panels' / 'thermal_panel.js'
ADVANCED_HTML = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'
LAUNCH_SITE_HTML = REPO_ROOT / 'hrma' / 'templates' / 'launch_site.html'
SITE_DICT_JS = STATIC_JS / 'i18n_launch_site.js'
COMMON_DICT_JS = STATIC_JS / 'i18n_common.js'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def read(path):
    return path.read_text(encoding='utf-8')


def strip_js_comments(src):
    """`//` ve `/* */` yorumlarını siler (dizge içindekilere dokunmadan)."""
    out, i, n = [], 0, len(src)
    quote = None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in '\'"`':
            quote = ch
            out.append(ch)
            i += 1
            continue
        if src.startswith('//', i):
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if src.startswith('/*', i):
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def balanced(src, start):
    """`start` konumundaki `{`/`(` ile eşleşen kapanışın indisini döndürür."""
    opener = src[start]
    closer = {'{': '}', '(': ')', '[': ']'}[opener]
    depth, i, quote = 0, start, None
    while i < len(src):
        ch = src[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in '\'"`':
            quote = ch
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise AssertionError('kapanış bulunamadı')


def cut_function(src, name):
    """Adı verilen `function <ad>(...) { ... }` gövdesini kaynaktan keser."""
    marker = 'function %s(' % name
    start = src.index(marker)
    brace = src.index('{', src.index(')', start))
    end = balanced(src, brace)
    return src[start:end + 1]


def js_number(src, name):
    match = re.search(r'\b%s\s*=\s*([0-9.eE+-]+)' % re.escape(name), src)
    assert match, '%s sabiti kaynakta yok' % name
    return float(match.group(1))


def dict_pairs(path, lang):
    """i18n_*.js dosyasındaki bir dil bloğunun (anahtar, değer) sözlüğü."""
    src = read(path)
    match = re.search(r'\b%s\s*:\s*\{' % re.escape(lang), src)
    assert match, '%s içinde %r bloğu yok' % (path.name, lang)
    end = balanced(src, match.end() - 1)
    body = src[match.end():end]
    pair = re.compile(r"^\s*'((?:\\.|[^'\\])*)'\s*:\s*'((?:\\.|[^'\\])*)'\s*,?\s*$",
                      re.M)
    out = {}
    for key, val in pair.findall(body):
        out[key.replace("\\'", "'")] = (val.replace("\\'", "'")
                                        .encode().decode('unicode_escape'))
    return out


def run_node(script_body, payload=None, tmp_path=None):
    """Verilen JS gövdesini gerçek node'da koşturur, JSON çıktısını döndürür."""
    script = tmp_path / 'kos.js'
    script.write_text(script_body, encoding='utf-8')
    args = [NODE, str(script)]
    if payload is not None:
        data = tmp_path / 'girdi.json'
        data.write_text(json.dumps(payload), encoding='utf-8')
        args.append(str(data))
    proc = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ===========================================================================
# T48 — modelin beyan edilen geçerlilik sınırı α grafiğinde çizilir
# ===========================================================================

def _alpha_harness(tmp_path, payload):
    """`_buildAlphaFigure`'ü dosyadan kesip node'da koşturur.

    (tests/test_faz6_f8_motor.py::_run_alpha_figure ile aynı yöntem — saf
    fonksiyon, Plotly çağrısı içermiyor.)
    """
    src = read(SIXDOF_JS)
    body = cut_function(src, '_buildAlphaFigure')
    prelude = (
        'const ALPHA_VALID_MIN_TIME_S = %r;\n'
        'const ALPHA_VALID_SPEED_FRACTION = %r;\n'
        'const ALPHA_LINEAR_LIMIT_DEG = %r;\n'
        'function T(k, f) { return f; }\n'
        'function TF(k, p, f) { return f; }\n'
        % (js_number(src, 'ALPHA_VALID_MIN_TIME_S'),
           js_number(src, 'ALPHA_VALID_SPEED_FRACTION'),
           js_number(src, 'ALPHA_LINEAR_LIMIT_DEG')))
    tail = (
        '\nconst inp = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));\n'
        'const fig = _buildAlphaFigure(inp.series, inp.summary);\n'
        'console.log(JSON.stringify({\n'
        '  yRange: fig.layout.yaxis.range || null,\n'
        '  shapes: (fig.layout.shapes || []).map(s => s.y0),\n'
        '  annotations: (fig.layout.annotations || []).map(a => a.text),\n'
        '  includedPeak: fig.includedPeak\n'
        '}));\n')
    return run_node(prelude + body + tail, payload, tmp_path)


def _flight(alphas, speed=200.0):
    """Sentetik uçuş serisi: tüm örneklemler geçerlilik penceresi içinde."""
    n = len(alphas)
    return {
        'series': {'time': [round(0.1 * (i + 20), 3) for i in range(n)],
                   'alpha_deg': alphas, 'speed': [speed] * n},
        'summary': {'max_speed': speed, 'apogee_time': 1e9,
                    'max_alpha_deg': max(alphas)},
    }


def test_t48_limit_line_is_declared_once_and_matches_the_panel_text():
    """15° sınırı TEK sabitte durmalı ve panel açıklamasıyla aynı olmalı.

    KUSUR: sınır yalnız `sixdof.intro` metninde ("alpha < 15 deg") yazıyordu;
    kodda karşılığı yoktu, dolayısıyla grafikte de çizilemiyordu. Metin ile
    kod ayrışırsa kullanıcıya yanlış bir sınır gösterilir.
    """
    limit = js_number(read(SIXDOF_JS), 'ALPHA_LINEAR_LIMIT_DEG')
    assert limit == 15, 'sınır değişmiş: %r' % limit

    intro_en = dict_pairs(COMMON_DICT_JS, 'en')['sixdof.intro']
    intro_tr = dict_pairs(COMMON_DICT_JS, 'tr')['sixdof.intro']
    sayi = '%d' % int(limit)
    for lang, metin in (('EN', intro_en), ('TR', intro_tr)):
        assert re.search(r'\b%s\b' % sayi, metin), (
            'sixdof.intro (%s) artık %s° sınırını yazmıyor: %r'
            % (lang, sayi, metin[-120:]))


@needs_node
def test_t48_limit_line_is_drawn_on_the_alpha_chart(tmp_path):
    """Sınır HER koşuda grafiğe eklenmeli (eksen aşmıyorsa Plotly kırpar).

    ÖLÇÜLDÜ (2026-08-03, /hybrid, varsayılan araç):
        ÖNCE : shapes = [1.62]            → sınır çizgisi YOK
        SONRA: shapes = [1.62, 15]        → sınır var, eksen [0 , 2.11]
                                            olduğu için ekranda görünmüyor
    """
    limit = js_number(read(SIXDOF_JS), 'ALPHA_LINEAR_LIMIT_DEG')
    fig = _alpha_harness(tmp_path, _flight([0.5 + 0.01 * i for i in range(200)]))
    assert limit in fig['shapes'], (
        'geçerlilik sınırı grafiğe eklenmiyor: %r' % fig['shapes'])


@needs_node
def test_t48_limit_line_does_not_stretch_the_axis(tmp_path):
    """Sınır çizgisi ekseni ELE GEÇİRMEMELİ (T34 düzeltmesi bozulmasın).

    α ≈ 2,5° olan bir uçuşta eksen tavanı hâlâ verinin ~1,3 katı olmalı;
    15°'e kadar açılırsa gerçek bilgi yine ezilir.
    """
    limit = js_number(read(SIXDOF_JS), 'ALPHA_LINEAR_LIMIT_DEG')
    fig = _alpha_harness(tmp_path, _flight([0.5 + 0.01 * i for i in range(200)]))
    top = fig['yRange'][1]
    assert top < limit, 'eksen sınıra kadar açılmış: %r' % top
    assert top == pytest.approx(1.3 * fig['includedPeak'], rel=1e-9)


@needs_node
def test_t48_limit_label_appears_only_when_the_limit_is_in_view(tmp_path):
    """Etiket havada durmamalı: yalnız çizgi eksene giriyorsa basılır.

    ÖLÇÜLDÜ (2026-08-03, /hybrid, kanatlar 0,02 m + rüzgâr 25 m/s):
        α_max 89,63° → eksen [0 , 116,5] → 'α_lin = 15°' etiketi GÖRÜNÜR.
    Varsayılan araçta (α_max 1,62°) etiket basılmaz.
    """
    limit = js_number(read(SIXDOF_JS), 'ALPHA_LINEAR_LIMIT_DEG')
    etiket = 'α_lin = %d°' % int(limit)

    dusuk = _alpha_harness(tmp_path, _flight([0.5 + 0.01 * i for i in range(200)]))
    assert etiket not in dusuk['annotations'], (
        'sınır görünür değilken etiket basılıyor: %r' % dusuk['annotations'])

    yuksek = _alpha_harness(tmp_path, _flight([0.5 + 0.2 * i for i in range(200)]))
    assert yuksek['includedPeak'] > limit, 'kurgu sınırı aşmıyor, test kör'
    assert etiket in yuksek['annotations'], (
        'sınır aşıldığı hâlde etiket yok: %r' % yuksek['annotations'])


# ===========================================================================
# T12 — tek araç tanımı: 6-DOF paneli yörünge panelinden tohumlanır
# ===========================================================================

def _inline_scripts(path):
    return re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>',
                      read(path), flags=re.S)


def _vehicle_spec_source():
    """advanced.html içindeki `window.HRMAVehicleSpec = {...}` bloğu.

    Yorumlar önce silinir: blokta sözleşmeyi ANLATAN bir yorum da
    `window.HRMAVehicleSpec.read() -> {...}` yazıyor, o kod değildir.
    """
    for block in _inline_scripts(ADVANCED_HTML):
        code = strip_js_comments(block)
        idx = code.find('window.HRMAVehicleSpec')
        if idx < 0:
            continue
        brace = code.index('{', idx)
        return code[idx:balanced(code, brace) + 1]
    raise AssertionError('advanced.html araç tanımı yayımlamıyor')


def _template_field_default(field_id):
    """Şablondaki `<input id="...">` alanının value niteliği."""
    match = re.search(r'<input[^>]*id="%s"[^>]*>' % re.escape(field_id),
                      read(ADVANCED_HTML))
    assert match, '%s alanı şablonda yok' % field_id
    value = re.search(r'value="([^"]*)"', match.group(0))
    assert value, '%s alanının varsayılanı yok' % field_id
    return float(value.group(1))


def test_t12_page_publishes_a_single_vehicle_definition():
    """advanced.html araç tanımını ADIYLA yayımlamalı, panel onu okumalı."""
    spec = _vehicle_spec_source()
    for alan in ('dry_mass_kg', 'propellant_mass_kg', 'body_diameter_m', 'cd0'):
        assert alan in spec, 'araç tanımında %s yok' % alan

    panel = strip_js_comments(read(SIXDOF_JS))
    assert 'window.HRMAVehicleSpec' in panel, \
        '6-DOF paneli sayfanın araç tanımını okumuyor'
    assert 'seedFromPageVehicle()' in panel, \
        'tohumlama init içinden çağrılmıyor'


@needs_node
def test_t12_both_panels_describe_the_same_vehicle(tmp_path):
    """Yörünge panelinin alanları 6-DOF alanlarına DEĞİŞMEDEN geçmeli.

    ÖLÇÜLDÜ (2026-08-03, /hybrid, sayfa açılışı):
        ÖNCE : yörünge  kuru 25,00 kg | itici 25,00 kg | Ø0,150 m | Cd 0,50
               6-DOF    kuru  8,00 kg | itici  4,00 kg | Ø0,100 m | Cd₀ 0,45
        SONRA: iki panel de 25,00 / 25,00 / 0,150 / 0,50
    """
    spec = _vehicle_spec_source()
    varsayilan = {fid: _template_field_default(fid) for fid in
                  ('initial_mass', 'final_mass', 'reference_area',
                   'drag_coefficient')}

    # Okuyucuyu DOM taklidiyle gerçek node'da koşturur: sayı gerçekten
    # kaynaktaki formülden çıkıyor mu, elle yazılmış bir sabit mi?
    script = (
        'const MM2_PER_M2 = 1e6;\n'
        'const alanlar = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));\n'
        'global.document = { getElementById: (id) => (id in alanlar)'
        ' ? { value: String(alanlar[id]) } : null };\n'
        'const window = {};\n'
        + spec.replace('window.HRMAVehicleSpec', 'window.HRMAVehicleSpec', 1)
        + ';\nconsole.log(JSON.stringify(window.HRMAVehicleSpec.read()));\n')
    okunan = run_node(script, varsayilan, tmp_path)

    assert okunan['dry_mass_kg'] == varsayilan['final_mass']
    assert okunan['propellant_mass_kg'] == (varsayilan['initial_mass']
                                            - varsayilan['final_mass'])
    assert okunan['cd0'] == varsayilan['drag_coefficient']
    beklenen_cap = math.sqrt(4 * (varsayilan['reference_area'] / 1e6) / math.pi)
    assert okunan['body_diameter_m'] == pytest.approx(beklenen_cap, rel=1e-12), \
        'gövde çapı yörünge panelinin alın kesitinden gelmiyor'

    # Panel bu değerleri hangi alanlara yazıyor?
    seed = cut_function(strip_js_comments(read(SIXDOF_JS)), 'seedFromPageVehicle')
    for hedef, kaynak in (('sd_dry_m', 'dry_mass_kg'),
                          ('sd_body_d', 'body_diameter_m'),
                          ('sd_cd0', 'cd0')):
        assert re.search(r"put\('%s',\s*'%s'" % (hedef, kaynak), seed), \
            '%s alanı %s ile tohumlanmıyor' % (hedef, kaynak)


def test_t12_propellant_mass_is_deliberately_not_seeded():
    """İtici kütlesi tohumlanmamalı — itki/yanma süresiyle BÜTÜNDÜR.

    ÖLÇÜLDÜ (2026-08-03, /hybrid varsayılanları, sabit itki 1200 N × 6 s):
        itici de tohumlanınca  m0 = 50,0 kg, T/W = 2,45,
                               ima edilen Isp = 7200/(25·g0) = 29,4 s — saçma;
                               panel 'UNSTABLE' rozeti basıyordu
        yalnız gövde tohumlanınca m0 = 29,0 kg, T/W = 4,22, Isp = 183,5 s
    Yörünge paneli itkiyi BİLMEZ; itici kütlesi motor hesabından
    (thrustProvider) ya da içe aktarılan motor dosyasından gelir.
    """
    seed = cut_function(strip_js_comments(read(SIXDOF_JS)), 'seedFromPageVehicle')
    assert "put('sd_prop_m'" not in seed, (
        'itici kütlesi tohumlanıyor — itki/yanma süresiyle tutarsız bir '
        'varsayılan araç üretir (ima edilen Isp 29 s)')


def test_t12_seeding_is_one_way_and_happens_once():
    """Bağ TEK YÖNLÜ: panel kaynak alanlara geri yazmamalı, çevrim olmamalı."""
    panel = strip_js_comments(read(SIXDOF_JS))
    for kaynak in ('initial_mass', 'final_mass', 'reference_area',
                   'drag_coefficient'):
        assert not re.search(r"\$\('%s'\)\s*\.\s*value\s*=" % kaynak, panel), \
            '6-DOF paneli #%s alanına geri yazıyor (çevrim riski)' % kaynak

    init_body = cut_function(panel, 'init')
    assert init_body.count('seedFromPageVehicle()') == 1, \
        'tohumlama init içinde tam bir kez çağrılmalı'
    # Tanım satırı (`function seedFromPageVehicle()`) sayımdan düşülür:
    # geriye yalnız ÇAĞRI yerleri kalır.
    cagri = panel.count('seedFromPageVehicle()') - panel.count(
        'function seedFromPageVehicle()')
    assert cagri == 1, \
        'tohumlama %d yerden çağrılıyor — elle girilen değer ezilebilir' % cagri


def test_t12_seed_note_is_hidden_when_nothing_was_seeded():
    """Hiçbir alan tohumlanmadıysa "kaynak" iddiası GÖSTERİLMEMELİ.

    /solid ve /liquid sayfaları araç tanımı yayımlamıyor; ölçüldü
    (2026-08-03): not satırı display:none, alanlar 8 / 4 / 0,1 / 0,45.
    """
    seed = cut_function(strip_js_comments(read(SIXDOF_JS)), 'seedFromPageVehicle')
    assert "parts.length ? '' : 'none'" in seed.replace('\n', ' ').replace(
        '  ', ' ') or "parts.length ? '' : 'none'" in seed, \
        'not satırı boşken gizlenmiyor'
    assert 'if (!api || typeof api.read' in seed, \
        'sayfa araç tanımı yayımlamazsa panel yine de tohumlamaya çalışıyor'


# ===========================================================================
# T65 — boş eksen başlığı: "unuttuk" ile "gerekmiyor" ayrışsın
# ===========================================================================

def test_t65_thermal_charts_have_no_empty_axis_title():
    """Metinsiz başlık NESNESİ kurulmamalı.

    ÖLÇÜLDÜ (2026-08-03, /hybrid, analiz güvertesi termal paneli):
        ÖNCE : layout.xaxis.title = {"text":"", "font":{...}, "standoff":8}
        SONRA: layout.xaxis yok; SVG'de g-xtitle boş, ekranda değişiklik yok
    plotly_dark.js:92 boş dizgeyi de nesneye çevirdiği için `title: ''`
    yazmak `title: {text: ''}` yazmakla aynı sonucu verir.
    """
    src = strip_js_comments(read(THERMAL_JS))
    bos = re.findall(r"title:\s*(''|\"\"|``|\{\s*text:\s*(?:''|\"\"|``)\s*\})", src)
    assert not bos, 'boş eksen/grafik başlığı kalmış: %r' % bos


def test_t65_temperature_chart_axes_are_still_labelled_where_needed():
    """Anlamı taşıyan eksen başlığı SİLİNMEMELİ (aşırı düzeltme koruması).

    Sıcaklık ekseni ölçülen büyüklüğü söylemek zorunda; kaldırılan yalnız
    kategorik x ekseninin BOŞ başlığıydı.
    """
    src = strip_js_comments(read(THERMAL_JS))
    assert "common.axis.temperatureK" in src, \
        'sıcaklık ekseni başlığı da kaldırılmış'
    for anahtar in ('common.axis.axialX', 'common.axis.heatFlux',
                    'common.axis.machNumber', 'common.axis.wallTemp'):
        assert anahtar in src, 'eksenel profil başlığı kaybolmuş: %s' % anahtar


# ===========================================================================
# T74 — dil değişince dinamik metinler yeniden basılır
# ===========================================================================

def _onchange_body():
    src = read(LAUNCH_SITE_HTML)
    idx = src.index('I18N.onChange(function ()')
    return src[idx:balanced(src, src.index('{', idx)) + 1]


def test_t74_language_change_rerenders_the_runtime_written_texts():
    """Dil değişince araç metinleri ve karo göstergesi yeniden basılmalı.

    ÖLÇÜLDÜ (2026-08-03, /launch-site, EN açılıp TR'ye çevrildi):
        ÖNCE : rozet 'Example vehicle (example, not calculated)',
               not 'No motor calculated in this session yet — ...' (İngilizce)
        SONRA: rozet 'Örnek araç (örnek, hesaplanmış değil)',
               not 'Bu oturumda henüz motor hesaplanmadı — ...'
    Bu üç düğüm data-i18n TAŞIMAZ (metin çalışma anında birleşiyor), yani
    I18N.apply onlara erişemez; elle tazelenmeleri gerekir.
    """
    body = _onchange_body()
    for cagri in ('renderVehicleText()', 'renderTileUsage()', 'relabelPresets()'):
        assert cagri in body, 'dil değişiminde %s çağrılmıyor' % cagri


def test_t74_vehicle_texts_are_written_from_a_single_render_function():
    """Rozet/not YALNIZ renderVehicleText içinde basılmalı.

    İkinci bir yazım noktası kalırsa dil değişiminde yine ayrışırlar.
    """
    src = read(LAUNCH_SITE_HTML)
    render = cut_function(src, 'renderVehicleText')
    tum = [m.start() for m in re.finditer(r"ls-vehicle-name'\)", src)]
    disarda = [p for p in tum if not (src.index(render) <= p
                                      < src.index(render) + len(render))]
    assert not disarda, 'araç rozeti renderVehicleText dışında da yazılıyor'
    assert 'currentVehicleNote' in render, \
        'not metni saklanmıyor — dil değişince yeniden üretilemez'


def test_t74_example_vehicle_name_is_a_translated_placeholder():
    """Örnek aracın adı VERİ değil YER TUTUCUDUR; sözlükten gelmeli.

    ÖLÇÜLDÜ (2026-08-03, /launch-site TR): rozet 'Example vehicle (örnek,
    hesaplanmış değil)' — yarısı İngilizce. Anahtar eklendikten sonra
    'Örnek araç (örnek, hesaplanmış değil)'.
    Gerçek motor adları (kullanıcı verisi) çevrilmez: name_key yalnız örnek
    araçta bulunur.
    """
    src = read(LAUNCH_SITE_HTML)
    match = re.search(r"name_key:\s*'([\w.]+)'", src)
    assert match, 'örnek aracın adı hâlâ sabit İngilizce veri'
    key = match.group(1)

    en = dict_pairs(SITE_DICT_JS, 'en')
    tr = dict_pairs(SITE_DICT_JS, 'tr')
    assert key in en and key in tr, 'name_key sözlükte yok: %s' % key
    assert en[key] != tr[key], '%s çevrilmemiş' % key

    render = cut_function(src, 'renderVehicleText')
    assert 'name_key' in render, 'rozet name_key\'i kullanmıyor'
    assert src.count("name_key:") == 1, \
        'name_key birden çok araca konmuş — kullanıcı motor adları çevrilmemeli'


def test_t74_tile_unit_goes_through_the_dictionary():
    """Karo birimi ('tile') çeviri katmanından geçmeli.

    ÖLÇÜLDÜ (2026-08-03, /launch-site): sunucudan 9 karo / 0,2 MB gelirken
    gösterge iki dilde de '0.2 MB · 9 tile' basıyordu. Anahtar çalışma anında
    sözlüğe eklenince TR'de '0.2 MB · 9 karo' oldu — kanal bağlı, sözlük
    kaydı eksik (i18n_launch_site.js bu turda başka bir sahipte).
    """
    src = read(LAUNCH_SITE_HTML)
    render = cut_function(src, 'renderTileUsage')
    assert "t('site.tileUnit'" in render, \
        'karo birimi hâlâ sabit metin'
    assert "' tile'" not in strip_js_comments(render), \
        'çevrilmeyen tile birimi kalmış'


@needs_node
def test_t74_tile_indicator_never_invents_a_number(tmp_path):
    """Sunucudan veri gelmediyse gösterge BOŞ kalmalı, sıfır UYDURMAMALI.

    Gösterge fonksiyonu DOM taklidiyle gerçek node'da koşturulur:
      - `lastTileStatus` yokken çıktı boş dize olmalı
      - sunucu yanıtı varken çıktı o yanıttan üretilmeli ve birim
        sözlükten gelmeli (TR sözlüğü verilince 'karo' yazmalı)
    """
    src = read(LAUNCH_SITE_HTML)
    body = (cut_function(src, 'fmtBytes') + '\n'
            + cut_function(src, 'renderTileUsage'))
    script = (
        'const dugum = {textContent: null};\n'
        'let lastTileStatus = null;\n'
        'let sozluk = {};\n'
        "function el(id) { return id === 'ls-tile-usage' ? dugum : null; }\n"
        'function t(k, fb) { return (k in sozluk) ? sozluk[k] : fb; }\n'
        + body +
        '\nconst cikti = {};\n'
        'renderTileUsage(); cikti.veri_yok = dugum.textContent;\n'
        'lastTileStatus = {bytes: 209715, tiles: 9};\n'
        'renderTileUsage(); cikti.en = dugum.textContent;\n'
        "sozluk = {'site.tileUnit': 'karo'};\n"
        'renderTileUsage(); cikti.tr = dugum.textContent;\n'
        'console.log(JSON.stringify(cikti));\n')
    out = run_node(script, None, tmp_path)

    assert out['veri_yok'] == '', \
        'veri yokken uydurma gösterge basılıyor: %r' % out['veri_yok']
    # 209715 B = 0,2 MB — sayı sunucu yanıtından gelir, sabit değil
    assert out['en'] == '0.2 MB · 9 tile', out['en']
    assert out['tr'] == '0.2 MB · 9 karo', \
        'birim sözlükten gelmiyor: %r' % out['tr']


@needs_node
def test_launch_site_inline_scripts_still_parse():
    """Şablonun satır içi script'leri sözdizimi olarak geçerli kalmalı."""
    for i, block in enumerate(_inline_scripts(LAUNCH_SITE_HTML)):
        proc = subprocess.run([NODE, '--check', '-'], input=block,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, 'launch_site.html script #%d: %s' % (
            i, proc.stderr[:400])


@needs_node
def test_advanced_inline_scripts_still_parse():
    """advanced.html satır içi script'leri sözdizimi olarak geçerli kalmalı."""
    for i, block in enumerate(_inline_scripts(ADVANCED_HTML)):
        proc = subprocess.run([NODE, '--check', '-'], input=block,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, 'advanced.html script #%d: %s' % (
            i, proc.stderr[:400])
