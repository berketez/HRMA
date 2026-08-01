"""Katı ve sıvı sayfalarının çift dilli sözleşme testleri (2026-07-19).

Berke: "Ana menüde dil seçeneği; Türkçe seçilirse HER ŞEY Türkçe, İngilizce
seçilirse her şey İngilizce." Bu dosya solid.html + liquid.html için o sözü
kalıcı olarak kilitler:

  1. SÖZDİZİM — iki şablondaki TÜM inline <script> blokları `node --check`
     temiz (node yoksa atlanır). Sayfalar 4000+ satır; T()/TF() sarmaları
     sırasında bozulan tek bir tırnak bütün sayfayı sessizce öldürür.
  2. İKİ YÖNLÜ TUTARLILIK — şablonda geçen her anahtarın sözlükte karşılığı
     var (yazım hatası koruması) ve sözlükteki her solid./liq. anahtarı
     şablonda gerçekten kullanılıyor (ölü çeviri koruması).
  3. EN/TR EŞİTLİĞİ — i18n_pages.js'te iki dilin anahtar kümesi birebir aynı,
     hiçbir değer boş değil.
  4. KAPSAM — şablonların HTML bölümünde işaretlenmemiş serbest metin
     kalmadı; inline script'lerde T() dışında duragan HTML metni kalmadı.
  5. TERİM SÖZLÜĞÜ — mühendislik terimlerinin Türkçe karşılıkları sabit
     (chamber pressure -> oda basıncı, nozzle -> nozul, throat -> boğaz ...)
     ve yerleşik teknik kısaltmalar (Isp, c*, O/F, Kn, L*, BATES) çevrilmiyor.
  6. ALTYAPI — iki sayfa da i18n.js + i18n_pages.js yüklüyor ve dil seçiciyi
     basıyor.

Heuristikler bilinçli olarak dar: yanlış pozitif çıkarsa kuralı gevşetmek
yerine metni işaretleyin — testin amacı tam da bunu zorlamak.
"""

import pathlib
import re
import shutil
import subprocess
import tempfile
import os

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'
DICT_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
CORE_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n.js'

PAGES = {
    'solid.html': 'solid.',
    'liquid.html': 'liq.',
}

HAS_LETTER = re.compile(r'[A-Za-z]')
WORD4 = re.compile(r'[A-Za-z]{4,}')
TURKISH_CHARS = re.compile(r'[çğıİöşüÇĞÖŞÜ]')

# Çeviri gerektirmeyen kısa birim/simge metinleri.
UNIT_WORDS = {'mm', 'cm', 'm', 'kg', 'k', 'l', 'n', 's', 'g', 'bar', 'pa', 'na'}
ENTITIES = {'&times;', '&nbsp;', '&amp;', 'n/a', 'N/A'}

#: Standart gösterimler — birim/simge kategorisinin devamı, çeviri nesnesi
#: DEĞİL. "M8" ya da "A2-70" her dilde aynı yazılır; bunlara sözlük anahtarı
#: açmak, EN ve TR değeri sonsuza dek özdeş kalacak 14 kayıt üretir ve
#: sözlüğün "bu metin çevrilebilir" iddiasını yalanlar.
#: Desen bilerek DAR: 'M' + yalnız rakam (isteğe bağlı diş adımı) ve ISO
#: 3506-1 paslanmaz sınıfı. "Motor", "Malzeme" gibi gerçek metin geçemez.
STANDARD_DESIGNATION = re.compile(
    r'^(?:'
    r'M\d{1,3}(?:[x×]\d+(?:[.,]\d+)?)?'   # ISO 68-1 metrik diş: M8, M12x1.75
    r'|A[24]-\d{2}'                        # ISO 3506-1 paslanmaz: A2-70, A4-80
    r')$')


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def read(path):
    return path.read_text(encoding='utf-8')


def blank(match):
    """Eşleşmeyi aynı uzunlukta boşlukla değiştirir (satır numarası korunur)."""
    return re.sub(r'[^\n]', ' ', match.group(0))


def mask_html_noise(text):
    """HTML yorumlarını ve <style> bloklarını maskeler."""
    text = re.sub(r'<!--.*?-->', blank, text, flags=re.S)
    return re.sub(r'<style\b[^>]*>.*?</style>', blank, text, flags=re.S | re.I)


def inline_scripts(text):
    """src'siz <script> gövdelerinin (başlangıç, gövde) listesi."""
    return [(m.start(1), m.group(1))
            for m in re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>',
                                 text, re.S)]


def is_skippable(raw):
    """Çeviri gerektirmeyen metin mi? (birim, simge, salt sayı)"""
    text = ' '.join(raw.split())
    if not text or not HAS_LETTER.search(text):
        return True
    if text in ENTITIES:
        return True
    if text.startswith('(') and text.endswith(')') and not WORD4.search(text):
        return True          # "(mm)", "(kg/m³)", "(m/s/bar^n)" gibi birimler
    if re.match(r'^[A-Za-z]{1,3}$', text) and text.lower() in UNIT_WORDS:
        return True
    if STANDARD_DESIGNATION.match(text):
        return True          # "M8", "M12x1.75", "A2-70" gibi ISO gösterimleri
    return False


def scan_strings(code):
    """JS kaynağındaki string/template literal gövdelerinin (baş, son, tırnak).

    Yorumları ve regex literallerini atlar; `${...}` içinde kod bağlamına
    döner, böylece şablon literali gövdeleri parça parça raporlanır.
    """
    out = []
    i, n = 0, len(code)
    ctx = [{'kind': 'code', 'depth': 0}]
    prev = ''
    while i < n:
        ch = code[i]
        top = ctx[-1]
        if top['kind'] == 'code':
            if ch == '/' and i + 1 < n and code[i + 1] == '/':
                j = code.find('\n', i)
                i = n if j < 0 else j
                continue
            if ch == '/' and i + 1 < n and code[i + 1] == '*':
                j = code.find('*/', i + 2)
                i = n if j < 0 else j + 2
                continue
            if ch == '/' and prev in ('', '(', ',', '=', ':', '[', '!', '&', '|',
                                      '?', '{', '}', ';', '+', '-', '*', '%',
                                      '~', '^'):
                j, incls = i + 1, False
                while j < n:
                    c = code[j]
                    if c == '\\':
                        j += 2
                        continue
                    if c == '[':
                        incls = True
                    elif c == ']':
                        incls = False
                    elif (c == '/' and not incls) or c == '\n':
                        break
                    j += 1
                i, prev = j + 1, '/'
                continue
            if ch in '\'"`':
                ctx.append({'kind': ch, 'start': i + 1})
                i += 1
                continue
            if ch == '{':
                top['depth'] += 1
            elif ch == '}':
                if top['depth'] == 0 and len(ctx) > 1:
                    ctx.pop()
                    ctx[-1]['start'] = i + 1
                    i += 1
                    continue
                top['depth'] -= 1
            if not ch.isspace():
                prev = ch
            i += 1
            continue

        quote = top['kind']
        if ch == '\\':
            i += 2
            continue
        if quote == '`' and ch == '$' and i + 1 < n and code[i + 1] == '{':
            out.append((top['start'], i, quote))
            ctx.append({'kind': 'code', 'depth': 0})
            i += 2
            continue
        if ch == quote:
            out.append((top['start'], i, quote))
            ctx.pop()
            if ctx and ctx[-1]['kind'] == 'code':
                prev = quote
            i += 1
            continue
        if quote in '\'"' and ch == '\n':
            ctx.pop()                 # bozuk string; tarayıcıyı kurtar
            i += 1
            continue
        i += 1
    return out


def dict_block(lang):
    """i18n_pages.js içindeki bir dil bloğunun (anahtar, değer) listesi."""
    source = read(DICT_JS)
    match = re.search(r'^\s{8}%s:\s*\{$' % lang, source, re.M)
    assert match, "i18n_pages.js içinde '%s' bloğu yok" % lang
    body = source[match.end():]
    end = body.index('\n        }')
    return re.findall(r"^\s*'([^']+)':\s*'(.*)',?$", body[:end], re.M)


@pytest.fixture(scope='module')
def dict_en():
    return dict((k, v.rstrip(',').rstrip("'")) for k, v in dict_block('en'))


@pytest.fixture(scope='module')
def dict_tr():
    return dict((k, v.rstrip(',').rstrip("'")) for k, v in dict_block('tr'))


@pytest.fixture(scope='module')
def pages():
    return dict((name, read(TEMPLATES / name)) for name in PAGES)


def template_keys(html):
    """Şablonda geçen data-i18n* ve T()/TF() anahtarları."""
    keys = set(re.findall(r'data-i18n(?:-title|-placeholder)?="([^"]+)"', html))
    keys |= set(re.findall(r"\bTF?\('([^']+)'", html))
    return keys


# ---------------------------------------------------------------------------
# 1. Sözdizim
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which('node') is None, reason='node kurulu değil')
@pytest.mark.parametrize('page', sorted(PAGES))
def test_inline_scripts_parse(pages, page):
    """T()/TF() sarmaları hiçbir inline script'i bozmamalı."""
    node = shutil.which('node')
    for index, (_, body) in enumerate(inline_scripts(pages[page])):
        handle = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                             encoding='utf-8')
        handle.write(body)
        handle.close()
        try:
            result = subprocess.run([node, '--check', handle.name],
                                    capture_output=True, text=True)
        finally:
            os.unlink(handle.name)
        assert result.returncode == 0, (
            '%s içindeki %d. inline script sözdizimi bozuk:\n%s'
            % (page, index, result.stderr[:1500]))


@pytest.mark.skipif(shutil.which('node') is None, reason='node kurulu değil')
def test_dictionary_parses():
    result = subprocess.run([shutil.which('node'), '--check', str(DICT_JS)],
                            capture_output=True, text=True)
    assert result.returncode == 0, 'i18n_pages.js sözdizimi hatası:\n' + result.stderr


# ---------------------------------------------------------------------------
# 2. İki yönlü anahtar tutarlılığı
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('page', sorted(PAGES))
def test_every_template_key_is_defined(pages, page, dict_en):
    """Şablondaki her anahtarın sözlükte karşılığı olmalı (yazım hatası)."""
    core = set(re.findall(r"^\s*'([^']+)':", read(CORE_JS), re.M))
    unknown = sorted(k for k in template_keys(pages[page])
                     if k not in dict_en and k not in core)
    assert not unknown, '%s: sözlükte olmayan anahtarlar: %s' % (page, unknown)


def test_every_dictionary_key_is_used(pages, dict_en):
    """Sözlükte kullanılmayan (ölü) çeviri kalmamalı."""
    used = set()
    for html in pages.values():
        used |= template_keys(html)
    dead = sorted(k for k in dict_en if k not in used)
    assert not dead, 'Şablonlarda kullanılmayan sözlük anahtarları: %s' % dead[:25]


@pytest.mark.parametrize('page,prefix', sorted(PAGES.items()))
def test_keys_use_page_prefix(pages, page, prefix, dict_en):
    """Katı sayfası solid.*, sıvı sayfası liq.* öneki kullanır."""
    core = set(re.findall(r"^\s*'([^']+)':", read(CORE_JS), re.M))
    wrong = sorted(k for k in template_keys(pages[page])
                   if k in dict_en and not k.startswith(prefix) and k not in core)
    assert not wrong, '%s içinde yanlış önekli anahtarlar: %s' % (page, wrong)


# ---------------------------------------------------------------------------
# 3. EN / TR eşitliği
# ---------------------------------------------------------------------------
def test_en_tr_key_sets_match(dict_en, dict_tr):
    missing = sorted(set(dict_en) - set(dict_tr))
    extra = sorted(set(dict_tr) - set(dict_en))
    assert not missing, 'TR karşılığı olmayan anahtarlar: %s' % missing[:25]
    assert not extra, "TR'de olup EN'de olmayan anahtarlar: %s" % extra[:25]


def test_no_empty_values(dict_en, dict_tr):
    empty = sorted(k for k in dict_en if not dict_en[k].strip())
    empty += sorted(k for k in dict_tr if not dict_tr[k].strip())
    assert not empty, 'Boş çeviri değerleri: %s' % empty[:25]


def test_placeholders_match(dict_en, dict_tr):
    """tf() yer tutucuları iki dilde aynı olmalı, yoksa değer ekranda kaybolur."""
    problems = []
    for key, en_value in dict_en.items():
        en_holders = set(re.findall(r'\{(\w+)\}', en_value))
        tr_holders = set(re.findall(r'\{(\w+)\}', dict_tr[key]))
        if en_holders != tr_holders:
            problems.append('%s: EN%s TR%s' % (key, sorted(en_holders), sorted(tr_holders)))
    assert not problems, 'Yer tutucu uyuşmazlığı:\n  ' + '\n  '.join(problems)


def test_dictionary_is_substantial(dict_en):
    """İki sayfanın metinleri gerçekten sözlüğe taşınmış olmalı."""
    solid = [k for k in dict_en if k.startswith('solid.')]
    liquid = [k for k in dict_en if k.startswith('liq.')]
    assert len(solid) > 400, 'katı sayfası sözlüğü beklenenden küçük: %d' % len(solid)
    assert len(liquid) > 400, 'sıvı sayfası sözlüğü beklenenden küçük: %d' % len(liquid)


# ---------------------------------------------------------------------------
# 4. Kapsam: işaretlenmemiş metin kalmadı
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('page', sorted(PAGES))
def test_no_unmarked_html_text(pages, page):
    """HTML bölümündeki her görünür metin data-i18n taşıyan bir düğümde."""
    masked = mask_html_noise(pages[page])
    script_spans = [(start, start + len(body))
                    for start, body in inline_scripts(masked)]

    def in_script(offset):
        return any(a <= offset < b for a, b in script_spans)

    unmarked = []
    for match in re.finditer(r'>([^<>]+)<', masked):
        if in_script(match.start(1)) or is_skippable(match.group(1)):
            continue
        tag_start = masked.rfind('<', 0, match.start(1))
        opening = masked[tag_start:match.start(1) + 1]
        if 'data-i18n' in opening:
            continue
        line = masked.count('\n', 0, match.start(1)) + 1
        unmarked.append('%s:%d  %s' % (page, line, ' '.join(match.group(1).split())[:90]))
    assert not unmarked, (
        '%s içinde çeviri için işaretlenmemiş metin kaldı '
        '(data-i18n ekleyin, testi gevşetmeyin):\n  %s'
        % (page, '\n  '.join(unmarked[:25])))


@pytest.mark.parametrize('page', sorted(PAGES))
def test_no_raw_text_in_generated_html(pages, page):
    """Inline script'lerin ürettiği HTML'de T() dışında duragan metin yok."""
    html = pages[page]
    leftovers = []
    for start, body in inline_scripts(html):
        for begin, end, _quote in scan_strings(body):
            chunk = body[begin:end]
            for match in re.finditer(r'>([^<>]+)<', chunk):
                raw = match.group(1)
                if '${' in raw or '\\n' in raw or is_skippable(raw):
                    continue
                line = html.count('\n', 0, start + begin + match.start(1)) + 1
                leftovers.append('%s:%d  %s'
                                 % (page, line, ' '.join(raw.split())[:90]))
    assert not leftovers, (
        "%s: JS ile üretilen HTML'de çevrilmemiş metin kaldı "
        "(T('anahtar', 'English') ile sarın):\n  %s"
        % (page, '\n  '.join(leftovers[:25])))


# ---------------------------------------------------------------------------
# 5. Türkçe kalite ve terim sözlüğü
# ---------------------------------------------------------------------------
def test_turkish_values_use_turkish_letters(dict_tr):
    """TR sözlüğü ASCII'ye kaçmış olmamalı: metinlerin çoğu Türkçe harf taşır."""
    long_values = [v for v in dict_tr.values() if len(v) > 40]
    assert long_values, 'TR sözlüğünde uzun metin yok (sözlük eksik mi?)'
    with_turkish = [v for v in long_values if TURKISH_CHARS.search(v)]
    ratio = len(with_turkish) / float(len(long_values))
    assert ratio > 0.95, (
        'Uzun TR metinlerinin yalnız %%%.1f kadarı Türkçe harf içeriyor; '
        'ASCII\'ye kaçış şüphesi.' % (ratio * 100))


def fold(text):
    """Karşılaştırma için küçült.

    Python'da 'İ'.lower() 'i' + birleşen nokta (U+0307) üretir; bu nokta
    silinmezse 'İtki' metni 'itki' aramasıyla eşleşmez.
    """
    return text.lower().replace('̇', '')


TERMS = {
    'chamber pressure': 'oda basınc',
    'thrust': 'itki',
    'nozzle': 'nozul',
    'throat': 'boğaz',
    'burn time': 'yanma süre',
    'specific impulse': 'özgül itki',
    'mass flow': 'kütle debi',
    'safety factor': 'emniyet katsayı',
    'wall thickness': 'cidar kalınlığ',
}


@pytest.mark.parametrize('english,turkish', sorted(TERMS.items()))
def test_engineering_terms_are_consistent(dict_en, dict_tr, english, turkish):
    """Yerleşik Türkçe karşılığı olan terimler her yerde aynı çevrilir."""
    hits = [k for k, v in dict_en.items() if fold(v).startswith(english)]
    assert hits, 'Sözlükte "%s" ile başlayan değer yok' % english
    wrong = [k for k in hits if turkish not in fold(dict_tr[k])]
    assert not wrong, (
        '"%s" için beklenen karşılık "%s" değil:\n  %s'
        % (english, turkish,
           '\n  '.join('%s = %r' % (k, dict_tr[k]) for k in wrong[:10])))


# Yerleşik Türkçe karşılığı OLMAYAN teknik kısaltmalar: olduğu gibi kalmalı.
KEEP_AS_IS = ('Isp', 'c*', 'O/F', 'Kn', 'L*', 'BATES', 'Cf')


@pytest.mark.parametrize('token', KEEP_AS_IS)
def test_technical_tokens_are_not_translated(dict_en, dict_tr, token):
    hits = [k for k, v in dict_en.items() if token in v]
    assert hits, 'Sözlükte "%s" geçen değer yok' % token
    lost = [k for k in hits if token not in dict_tr[k]]
    assert not lost, (
        '"%s" kısaltması TR değerinde kaybolmuş:\n  %s'
        % (token, '\n  '.join('%s = %r' % (k, dict_tr[k]) for k in lost[:10])))


def test_no_emoji_in_dictionary(dict_en, dict_tr):
    """Berke kuralı: arayüz metinlerinde emoji yok."""
    emoji = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF]')
    found = [k for k, v in list(dict_en.items()) + list(dict_tr.items())
             if emoji.search(v)]
    assert not found, 'Sözlükte emoji: %s' % found[:10]


# ---------------------------------------------------------------------------
# 6. Altyapı: sözlük yükleniyor, dil seçici basılıyor
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('page', sorted(PAGES))
def test_page_loads_core_and_dictionary(pages, page):
    html = pages[page]
    core = html.index('/static/js/i18n.js')
    pack = html.index('/static/js/i18n_pages.js')
    assert core < pack, '%s: çekirdek i18n.js sözlükten sonra yükleniyor' % page


@pytest.mark.parametrize('page', sorted(PAGES))
def test_page_mounts_language_switcher(pages, page):
    html = pages[page]
    assert 'id="langSwitchHost"' in html, '%s: dil seçici yuvası yok' % page
    assert "I18N.mountSwitcher('#langSwitchHost')" in html, \
        '%s: dil seçici basılmıyor' % page


@pytest.mark.parametrize('page', sorted(PAGES))
def test_page_redraws_generated_blocks_on_language_change(pages, page):
    """T() ile üretilen bloklar dil değişince yeniden basılmalı."""
    html = pages[page]
    assert 'I18N.onChange(' in html, '%s: dil değişimi geri çağrısı yok' % page
    assert 'displayResults(window.currentResults)' in html, \
        '%s: sonuç panelleri dil değişiminde yeniden çizilmiyor' % page


@pytest.mark.parametrize('page', sorted(PAGES))
def test_helpers_come_from_dictionary_file(pages, page):
    """T/TF şablonda yeniden tanımlanmaz — katalog script sırası bozulmasın."""
    assert 'function T(key' not in pages[page], \
        '%s: T() şablonda tanımlanmış; i18n_pages.js sürümü kullanılmalı' % page
    assert 'global.T = function' in read(DICT_JS), 'i18n_pages.js T() sunmuyor'
    assert 'global.TF = function' in read(DICT_JS), 'i18n_pages.js TF() sunmuyor'
