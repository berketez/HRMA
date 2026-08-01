"""Arayüz uydurma sayı bekçisi — v2.6.26 Faz 2.

Berke'nin kuralı tek cümle: **çözücü bir değeri vermediyse arayüz o sayıyı
uyduramaz.** Bu dosya o kuralı üç şablon için (solid / liquid / advanced)
kalıcı olarak kilitler.

Kapatılan kusur sınıfı
----------------------
Ayrıntılı analiz sekmeleri şu kalıpla yazılmıştı::

    ${(caseAnalysis.hoop_stress_mpa || 120).toFixed(1)} MPa

Çözücü ``hoop_stress_mpa`` üretmezse ekran ``120.0 MPa`` basıyordu ve
kullanıcı bunun kendi girdisinden hesaplandığını sanıyordu. Ölçüldüğünde
solid.html'de bu kalıptan **53 benzersiz gösterim erişimi** vardı; 52'si
"latent" (bugünkü yanıtta alan mevcut olduğu için yedek tetiklenmiyor),
1'i canlıydı (``minimum_safe_distance_m`` — çözücü ``None`` + ``NOT_COMPUTED``
derken ekran 30 m yazıyordu). Latent olması güvenli demek değildir: tek bir
kod yolu alanı atladığında ekran sessizce yalan söyler.

Kapsam sınırı — GİRDİ TOPLAYICILARI HARİÇ
-----------------------------------------
``parseFloat(document.getElementById('x').value) || 5`` ayrı bir sınıftır:
kullanıcı alanı boş bıraktığında çözücüye giden **varsayılan tasarım
parametresi**. Bu bir gösterim yalanı değildir ve bu test onlara karışmaz.
Ayrım mekanik olarak yapılır (bkz. :func:`_is_input_collector`).

Testler
-------
1. ``|| SAYI ).toFixed(`` kalıbı üç şablonda da yok.
2. Template literal yerleştirmeleri (``${...}``) içinde sayısal yedek yok.
3. solid.html'in gösterim üreticisi fonksiyonlarında hiç sayısal yedek yok.
4. 3B/CAD geometri çizicileri ölçü eksikse ÇİZMİYOR (sabit motor uydurmuyor).
5. Dürüst biçimlendiriciler node'da ÇALIŞTIRILIP davranışları doğrulanıyor.
6. Negatif kontrol: dedektör kasten bozuk bir örneği gerçekten yakalıyor.

Yanlış pozitif çıkarsa kuralı gevşetmeyin; ya kodu düzeltin ya da
:data:`ALLOWED` listesine **gerekçesiyle** ekleyin.
"""

import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'
#: Bu bekçinin taradığı şablonlar. (Adı bilerek `PAGES` değil:
#: test_i18n_pages.py / inventory.py içinde farklı içerikli bir
#: `PAGES` var, tutarlılık kancası ikisini aynı sabit sanıyordu.)
SCANNED_PAGES = ('solid.html', 'liquid.html', 'advanced.html')


# ---------------------------------------------------------------------------
# İzin listesi
# ---------------------------------------------------------------------------
#: Gösterim bağlamında görünen ama uydurma OLMAYAN kalıplar. Her kayıt
#: "dosya::tam metin parçası" biçiminde tam eşleşmedir; joker yoktur ki
#: liste sessizce genişlemesin.
#:
#: Şu an BOŞ. Bilerek: Faz 2'de solid.html'deki 53 gösterim erişiminin
#: tamamı ``fmtField``/``fmtTextField``e çevrildi, liquid/advanced'daki
#: gösterim yedekleri de kaldırıldı. Buraya bir kayıt eklemek zorunda
#: kalırsanız gerekçeyi yorumda yazın — "test kırmızı oldu" gerekçe değildir.
ALLOWED = frozenset()

#: Sayısal yedek: ``|| 12``, ``?? 0.5``, ``|| -3``. Değişken yedeği
#: (``a || b``) veya metin yedeği bu testin konusu değil.
NUM_FALLBACK = re.compile(r'(?:\|\||\?\?)\s*-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?\b')

#: ``(x.y || 96).toFixed(1)`` ve ``((x.y || 333) - 273).toFixed(0)``.
FALLBACK_TOFIXED = re.compile(
    r'(?:\|\||\?\?)\s*-?\d+(?:\.\d+)?\s*\)'          # || 96 )
    r'(?:\s*[-+*/]\s*-?\d+(?:\.\d+)?\s*\))*'          # (isteğe bağlı) - 273 )
    r'\s*\.toFixed\s*\(')                             # .toFixed(

#: Template literal yerleştirmesi. İç içe süslü parantez YOK — uydurma
#: kalıbının şekli tam olarak budur: ``${(x.y || 96).toFixed(1)}``.
INTERPOLATION = re.compile(r'\$\{([^{}]*)\}')

#: Girdi toplayıcı imzaları. Bunlardan biri aynı ifadede geçiyorsa yedek
#: kullanıcı girdisinin varsayılanıdır, gösterim yalanı değildir.
INPUT_MARKERS = (
    'getElementById', 'querySelector', '.value', '.checked',
    'FormData', 'localStorage', 'sessionStorage', 'dataset.',
)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def read(page):
    return (TEMPLATES / page).read_text(encoding='utf-8')


def inline_scripts(text):
    """src'siz <script> gövdeleri (offset, gövde)."""
    return [(m.start(1), m.group(1)) for m in
            re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', text, re.S)]


def strip_js_comments(body):
    """// ve /* */ yorumlarını BOŞLUKLA doldurur (offsetler korunur).

    Zorunlu: bu sürümde kaldırılan kalıp, bir daha yazılmasın diye kod
    yorumlarında ÖRNEK olarak duruyor (``// ... `${(x.y || 96).toFixed(1)}`
    kalıbıyla yazılmıştı``). Yorumları temizlemezsek bekçi kendi belgesini
    ihlal sanır.

    Dize ve template literal içindeki ``//`` korunur; regex literalleri
    (``.replace(/"/g, ...)``) da atlanır, yoksa içindeki tırnak dize
    başlangıcı sanılır.
    """
    out = []
    i, n = 0, len(body)
    prev_significant = ''
    while i < n:
        ch = body[i]
        nxt = body[i + 1] if i + 1 < n else ''
        if ch == '/' and nxt == '/':
            j = body.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i))
            i = j
            continue
        if ch == '/' and nxt == '*':
            j = body.find('*/', i + 2)
            j = n if j < 0 else j + 2
            out.append(''.join(c if c == '\n' else ' ' for c in body[i:j]))
            i = j
            continue
        if ch in '"\'`':
            j = i + 1
            while j < n:
                if body[j] == '\\':
                    j += 2
                    continue
                if body[j] == ch:
                    break
                j += 1
            j = min(j + 1, n)
            out.append(body[i:j])
            i = j
            prev_significant = ch
            continue
        if ch == '/' and prev_significant in '(,=:[!&|?{};+-*%~^<>' + 'n':
            # regex literali (önceki anlamlı karakter operatör ya da 'return'un n'si)
            j = i + 1
            in_class = False
            while j < n:
                if body[j] == '\\':
                    j += 2
                    continue
                if body[j] == '[':
                    in_class = True
                elif body[j] == ']':
                    in_class = False
                elif body[j] == '/' and not in_class:
                    break
                elif body[j] == '\n':
                    break
                j += 1
            j = min(j + 1, n)
            out.append(body[i:j])
            i = j
            prev_significant = '/'
            continue
        out.append(ch)
        if not ch.isspace():
            prev_significant = ch
        i += 1
    return ''.join(out)


def code_of(page):
    """Sayfanın inline script'lerinin yorumsuz gövdesi (offsetleriyle)."""
    text = read(page)
    return [(off, strip_js_comments(body)) for off, body in inline_scripts(text)]


def line_of(page, offset):
    return read(page).count('\n', 0, offset) + 1


def _is_input_collector(expr):
    return any(marker in expr for marker in INPUT_MARKERS)


def function_body(code, name):
    """``function NAME(`` ile başlayıp aynı girintideki sonraki bildirime kadar.

    Şablonlardaki tüm sayfa fonksiyonları 8 boşluk girintili tek düzeydedir;
    bu yüzden basit "sonraki `\\n        function ` " ölçütü yeterli ve
    süslü parantez sayımının dize/regex tuzaklarından bağımsızdır.
    """
    start = code.find('function %s(' % name)
    assert start >= 0, 'fonksiyon bulunamadı: %s' % name
    nxt = code.find('\n        function ', start + 1)
    return code[start:nxt if nxt > 0 else len(code)]


# ---------------------------------------------------------------------------
# 1) `|| SAYI).toFixed(` kalıbı
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('page', SCANNED_PAGES)
def test_no_numeric_fallback_before_tofixed(page):
    """``(x.y || 96).toFixed(1)`` — bu sürümde kapatılan kusurun ta kendisi."""
    offenders = []
    for off, code in code_of(page):
        for m in FALLBACK_TOFIXED.finditer(code):
            snippet = code[max(0, m.start() - 90):m.end()].strip()
            if snippet in ALLOWED:
                continue
            offenders.append('%s:%d  ...%s'
                             % (page, line_of(page, off + m.start()), snippet[-110:]))
    assert not offenders, (
        '%s: çözücü değeri vermediğinde SAYI UYDURAN gösterim kaldı.\n'
        "Düzeltme: fmtField(nesne, 'anahtar', basamak, birim) kullanın; "
        'sayı yoksa gerekçesiyle "not computed" yazar.\n  %s'
        % (page, '\n  '.join(offenders)))


# ---------------------------------------------------------------------------
# 2) Template literal yerleştirmelerinde sayısal yedek
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('page', SCANNED_PAGES)
def test_no_numeric_fallback_in_interpolations(page):
    """``${...}`` doğrudan ekrana yazılır; içinde uydurma sayı olamaz."""
    offenders = []
    for off, code in code_of(page):
        for m in INTERPOLATION.finditer(code):
            expr = m.group(1)
            if not NUM_FALLBACK.search(expr):
                continue
            if _is_input_collector(expr):
                continue          # girdi toplayıcı — kapsam dışı (bkz. modül belgesi)
            if expr.strip() in ALLOWED:
                continue
            offenders.append('%s:%d  ${%s}'
                             % (page, line_of(page, off + m.start()), expr[:110]))
    assert not offenders, (
        '%s: ekrana yazılan ifadede sayısal yedek var — çözücü alanı '
        'vermezse kullanıcı uydurma sayı görür:\n  %s'
        % (page, '\n  '.join(offenders)))


# ---------------------------------------------------------------------------
# 3) Gösterim üreticisi fonksiyonları tamamen temiz
# ---------------------------------------------------------------------------
#: solid.html'de sonuç sekmelerinin HTML'ini üreten fonksiyonlar. Bunların
#: işi YALNIZCA çözücü çıktısını yazmaktır; içlerinde tek bir sayısal yedek
#: bile olamaz (girdi toplama işi bu fonksiyonlarda yok).
DISPLAY_GENERATORS = (
    'generatePerformanceAnalysisHTML',
    'generateStructuralAnalysisHTML',
    'generateThermalAnalysisHTML',
    'generateManufacturingAnalysisHTML',
    'generateSafetyAnalysisHTML',
    'generateCostAnalysisHTML',
    'generateCADAnalysisHTML',
)


@pytest.mark.parametrize('name', DISPLAY_GENERATORS)
def test_display_generators_have_no_numeric_fallback(name):
    code = '\n'.join(body for _, body in code_of('solid.html'))
    body = function_body(code, name)
    hits = [m.group(0) for m in NUM_FALLBACK.finditer(body)]
    assert not hits, (
        '%s içinde sayısal yedek kaldı: %s\n'
        'Bu fonksiyonlar yalnız çözücü çıktısını yazar; eksik alan için '
        "fmtField/fmtTextField kullanın." % (name, hits))


def test_display_generators_use_honest_formatters():
    """Yedekler silinirken alanların büsbütün kaldırılmadığını doğrular."""
    code = '\n'.join(body for _, body in code_of('solid.html'))
    for name in DISPLAY_GENERATORS:
        body = function_body(code, name)
        assert 'fmtField(' in body or 'fmtPercentOrNA(' in body or 'fmtNum(' in body, (
            '%s hiçbir dürüst biçimlendirici kullanmıyor — alanlar silinmiş '
            'olabilir.' % name)


# ---------------------------------------------------------------------------
# 4) 3B / CAD geometri çizicileri
# ---------------------------------------------------------------------------
def test_solid_3d_view_refuses_to_draw_without_geometry():
    """Ölçü yoksa 116/100/600 mm'lik hayalî motor çizilmez."""
    code = '\n'.join(body for _, body in code_of('solid.html'))
    body = function_body(code, 'create3DMotorVisualization')
    assert not NUM_FALLBACK.search(body), (
        'create3DMotorVisualization yine sabit ölçü yedeği taşıyor: %s'
        % NUM_FALLBACK.findall(body))
    assert 'missing' in body and 'isFinite' in body, (
        'create3DMotorVisualization eksik ölçüyü denetlemiyor; ölçü yoksa '
        'çizim YAPILMAMALI.')
    for key in ('case_design.outer_diameter', 'grain_geometry.core_diameter',
                'nozzle_design.total_length'):
        assert key in body, 'eksik alan raporunda %s yok' % key


def test_liquid_cad_view_refuses_to_draw_without_geometry():
    code = '\n'.join(body for _, body in code_of('liquid.html'))
    body = function_body(code, 'generateCADVisualizationPlotly')
    assert not NUM_FALLBACK.search(body), (
        'generateCADVisualizationPlotly sabit ölçü yedeği taşıyor: %s'
        % NUM_FALLBACK.findall(body))
    assert 'missingDims' in body, (
        'sıvı CAD görünümü eksik ölçüyü denetlemiyor.')


def test_advanced_design_sliders_refuse_fabricated_motor():
    """advanced.html tasarım paneli 100 mm / eps=8 uydurmasın."""
    code = '\n'.join(body for _, body in code_of('advanced.html'))
    body = function_body(code, 'vizDesignInit')
    # l_star KULLANICI GİRDİSİ (getElementById ile okunur) — kapsam dışı.
    for m in NUM_FALLBACK.finditer(body):
        line_start = body.rfind('\n', 0, m.start()) + 1
        line = body[line_start:body.find('\n', m.start())]
        assert _is_input_collector(line), (
            'vizDesignInit içinde girdi olmayan sayısal yedek: %s' % line.strip())
    assert 'vizDesignBase = null' in body, (
        'ölçü yoksa panel kurulmamalı (vizDesignBase = null + erken dönüş).')


# ---------------------------------------------------------------------------
# 5) Biçimlendiricilerin GERÇEK davranışı (node)
# ---------------------------------------------------------------------------
HELPERS_BEGIN = '>>> HRMA-HONEST-FORMATTERS-BEGIN <<<'
HELPERS_END = '>>> HRMA-HONEST-FORMATTERS-END <<<'


def honest_formatter_source():
    text = read('solid.html')
    a = text.index(HELPERS_BEGIN) + len(HELPERS_BEGIN)
    b = text.index(HELPERS_END)
    assert b > a
    return text[a:b]


@pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
def test_honest_formatters_behaviour():
    """Yardımcılar node'da çalıştırılır: eksik alan için SAYI çıkmamalı."""
    harness = """
const T = (key, en) => en;
%s

const fail = [];
const ok = (cond, msg) => { if (!cond) fail.push(msg); };

// 1) Alan yoksa çıktıda RAKAM olmaz.
['fmtField'].forEach(() => {
    const out = fmtField({}, 'hoop_stress_mpa', 1, 'MPa');
    ok(!/[0-9]/.test(out), 'eksik alan rakam üretti: ' + out);
    ok(out.indexOf('not computed') >= 0, 'gerekçe metni yok: ' + out);
});

// 2) Alan varsa birebir eski biçim.
ok(fmtField({v: 3.24}, 'v', 1, 'MPa') === '3.2 MPa', 'MPa biçimi bozuldu');
ok(fmtField({v: 96}, 'v', 1, '%%') === '96.0%%', 'yüzde biçimi bozuldu');
ok(fmtField({v: 25}, 'v', 0, ':1') === '25:1', 'oran biçimi bozuldu');
ok(fmtField({v: 0.65}, 'v', 0, 'mm', x => x * 1000) === '650 mm', 'dönüşüm bozuldu');
ok(fmtField({v: 333}, 'v', 0, '\\u00B0C', x => x - 273) === '60\\u00B0C', 'sıcaklık bozuldu');

// 3) Sıfır MEŞRU değerdir, yedek tetiklememeli (eski `|| 0` kusuru).
ok(fmtField({v: 0}, 'v', 1, 'MPa') === '0.0 MPa', 'sıfır yutuldu');

// 4) null / NaN / metin -> sayı uydurulmaz.
[null, undefined, NaN, Infinity, 'n/a'].forEach(bad => {
    const out = fmtField({v: bad}, 'v', 2, 'kg');
    ok(!/[0-9]/.test(out), 'bozuk değer sayı üretti: ' + JSON.stringify(bad) + ' -> ' + out);
});

// 5) Gerekçe title'a taşınır ve tırnak kaçırılır.
const withBasis = fmtField({v_basis: 'sized from Barlow "hoop" stress'}, 'v', 1, 'mm');
ok(withBasis.indexOf('title="sized from Barlow &quot;hoop&quot; stress"') >= 0,
   'gerekçe title\\'a yazılmadı: ' + withBasis);

// 6) Gerekçe önceliği: _basis > _source > _status > nesne basis.
ok(missingReason({v_basis: 'A', v_source: 'B', basis: 'C'}, 'v') === 'A', 'öncelik bozuk');
ok(missingReason({v_status: 'NOT_COMPUTED'}, 'v') === 'NOT_COMPUTED', 'status okunmadı');
ok(missingReason({}, 'v') === '', 'boş nesne gerekçe uydurdu');

// 7) Metin alanı: niteleme uydurulmaz.
ok(fmtTextField({}, 'rating').indexOf('not classified') >= 0, 'metin yedeği uyduruldu');
ok(fmtTextField({rating: 'Adequate'}, 'rating') === 'Adequate', 'gerçek metin bozuldu');
ok(fmtTextField({rating: '   '}, 'rating').indexOf('not classified') >= 0,
   'boşluktan ibaret metin kabul edildi');

// 8) Eski yardımcılar korunuyor (üçüncü kopya üretilmedi).
ok(fmtNum(undefined, 2) === '\\u2014', 'fmtNum bozuldu');
ok(fmtPercentOrNA(undefined) === 'not tabulated', 'fmtPercentOrNA bozuldu');
ok(fmtPercentOrNA(68) === '68%%', 'fmtPercentOrNA sayı biçimi bozuldu');

if (fail.length) { console.log(fail.join('\\n')); process.exit(1); }
console.log('OK');
""" % honest_formatter_source()

    fd, path = tempfile.mkstemp(suffix='.js')
    os.write(fd, harness.encode('utf-8'))
    os.close(fd)
    try:
        proc = subprocess.run(['node', path], capture_output=True, text=True)
    finally:
        os.unlink(path)
    assert proc.returncode == 0, (
        'dürüst biçimlendiriciler beklendiği gibi davranmıyor:\n%s\n%s'
        % (proc.stdout, proc.stderr))


# ---------------------------------------------------------------------------
# 6) Negatif kontrol — dedektör gerçekten yakalıyor mu?
# ---------------------------------------------------------------------------
def test_detector_catches_a_fabricated_sample():
    """Bekçinin kendisi çalışmıyorsa yeşil renk yalandır."""
    bad = "html += `<td>${(caseAnalysis.hoop_stress_mpa || 120).toFixed(1)} MPa</td>`;"
    assert FALLBACK_TOFIXED.search(bad), 'toFixed dedektörü kör'
    assert NUM_FALLBACK.search(INTERPOLATION.search(bad).group(1)), \
        'yerleştirme dedektörü kör'

    tricky = "const c = ((p.curing?.temperature_k || 333) - 273).toFixed(0);"
    assert FALLBACK_TOFIXED.search(tricky), 'iki aşamalı kalıp kaçtı'

    # Girdi toplayıcı YAKALANMAMALI (kapsam sınırı korunuyor mu?).
    good_input = "burn_time: parseFloat(document.getElementById('bt').value) || 2"
    assert _is_input_collector(good_input), 'girdi toplayıcı yanlışlıkla kapsama girdi'

    # Yorum içindeki tarihsel örnek YAKALANMAMALI.
    commented = "        // eski kalıp: ${(x.y || 96).toFixed(1)} idi\n        const a = 1;"
    assert not FALLBACK_TOFIXED.search(strip_js_comments(commented)), \
        'yorum temizleyici çalışmıyor'
