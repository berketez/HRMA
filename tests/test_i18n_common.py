"""JS katmanının çift dilliliği — i18n_common.js sözlüğü ve kullanım testleri.

Kapsam (T-JS dalgası, 2026-07-19). tests/test_i18n.py çekirdek sözleşmeyi
(register kalıbı, EN/TR anahtar eşitliği, ASCII kaçışı, emoji) kilitler;
bu dosya KULLANIM tarafını kilitler:

  1. Sözdizimi: dokunulan her JS dosyası `node --check` geçer.
  2. İki yönlü tutarlılık:
     - Kodda çağrılan HER anahtar sözlükte VAR (yazım hatası koruması).
     - Sözlükteki HER anahtar kodda KULLANILIYOR (ölü çeviri koruması).
  3. Dil değişimi: güverte ve kendi DOM'unu kuran paneller I18N.onChange
     ile kendini yeniden basıyor (dil değişince ekran anında Türkçeleşir).
  4. Güverte sözleşmesi: panel başlıkları titleKey taşır, alan etiketleri
     5. eleman olarak anahtar taşır, kategori sekmelerinin dock.cat.*
     karşılığı sözlükte vardır.
  5. Kalıntı avı (dar heuristik): panellerde U.sectionTitle / U.listBlock /
     U.statCard çağrılarına DÜZ metin geçilmiş mi.

Heuristikler bilinçli olarak dardır: yanlış pozitif üretmemeleri, gerçek
regresyonu yakalamaları beklenir. Yeni bir yanlış pozitif çıkarsa çağrıyı
düzeltin; heuristiği gevşetmek denetimi kör eder.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANELS_DIR = STATIC_JS / 'panels'
DICT_JS = STATIC_JS / 'i18n_common.js'

# T-JS dalgasının sahiplendiği dosyalar (index.html hariç — o şablon testi
# tests/test_i18n.py içinde).
MODULE_FILES = [
    STATIC_JS / 'app.js',
    STATIC_JS / 'analysis_dock.js',
    STATIC_JS / 'injector_panel.js',
    STATIC_JS / 'injector_schematics.js',
    STATIC_JS / 'sixdof_panel.js',
    STATIC_JS / 'transient_panel.js',
    STATIC_JS / 'update_check.js',
    STATIC_JS / 'chart_captions.js',
    STATIC_JS / 'motor_viz3d.js',
    STATIC_JS / 'motor_viz_deck.js',
    STATIC_JS / 'hud.js',
    STATIC_JS / 'materials_catalog.js',
    STATIC_JS / 'propellant_catalog.js',
    STATIC_JS / 'import_ui.js',
    STATIC_JS / 'project_bar.js',
    STATIC_JS / 'step_import_ui.js',
]
PANEL_FILES = sorted(PANELS_DIR.glob('*.js'))
ALL_FILES = MODULE_FILES + PANEL_FILES

# Güvertenin kategori sekmeleri (panels/*.js `category:` alanları)
DOCK_CATEGORIES = [
    'THERMAL', 'STRUCTURAL', 'SAFETY', 'PERFORMANCE', 'FLOW', 'VALIDATION',
    'PRESSURE VESSEL', 'FEED SYSTEM', 'COMPARE', 'CORRELATION', 'UNCERTAINTY',
]


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def read(path):
    return path.read_text(encoding='utf-8')


def strip_comments(text):
    """JS yorumlarını aynı uzunlukta boşlukla değiştirir (ofsetler korunur)."""
    def blank(match):
        return re.sub(r'[^\n]', ' ', match.group(0))

    text = re.sub(r'/\*.*?\*/', blank, text, flags=re.S)
    out = []
    for line in text.split('\n'):
        quote = None
        cut = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == '\\':
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            else:
                if ch in '\'"`':
                    quote = ch
                elif ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
                    cut = i
                    break
            i += 1
        out.append(line if cut is None else line[:cut] + ' ' * (len(line) - cut))
    return '\n'.join(out)


def dict_block(lang):
    """i18n_common.js içindeki bir dil bloğunun (anahtar -> değer) sözlüğü."""
    source = read(DICT_JS)
    start = source.index('        %s: {' % lang)
    depth = 0
    for idx in range(start + len('        %s: ' % lang), len(source)):
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
            if depth == 0:
                body = source[start:idx]
                break
    else:                                   # pragma: no cover - bozuk dosya
        pytest.fail("i18n_common.js '%s' bloğu kapanmıyor" % lang)
    pairs = re.findall(r"^\s*'((?:[^'\\]|\\.)*)':\s*'((?:[^'\\]|\\.)*)',?\s*$",
                       body, re.M)
    return {k.replace("\\'", "'"): v.replace("\\'", "'") for k, v in pairs}


EN = dict_block('en')
TR = dict_block('tr')

# Kodda anahtar geçebilecek tüm biçimler:
#   T('key', ...) / TF('key', ...) / U.t('key', ...) / U.tf('key', ...)
#   data-i18n="key" / data-i18n-title="key" / data-i18n-placeholder="key"
#   titleKey: 'key' / key: 'key' / labelKey dizisi 5. elemanı / 'dock.cat.' + cat
CALL_RE = re.compile(r"(?:\bT|\bTF|U\.t|U\.tf|window\.I18N\.t|window\.I18N\.tf)"
                     r"\(\s*'([\w. ]+)'")
ATTR_RE = re.compile(r'data-i18n(?:-title|-placeholder)?="([\w. ]+)"')
FIELD_RE = re.compile(r"'((?:common|panel|inj|sixdof|sch|out|uq|tps|vessel|joint|"
                      r"nzl|fuel|fluid|gas|coolant|cool|fac|motor|prop|press|mat|"
                      r"transient|update|app|dock|risk|chartCap)\.[\w.]+)'")


# FIELD_RE yalnız yardımcı bir tarayıcıdır (alan dizilerindeki çıplak anahtar
# metinleri). Aynı desene uyan ama çeviri anahtarı OLMAYAN dizeler burada
# elenir — listeyi dar tutun, gerçek anahtar eklemeyin.
NOT_KEYS = {'motor.eng'}          # app.js: .eng dosya adı


def used_keys():
    """Kodda geçen tüm çeviri anahtarları (dosya adlarıyla birlikte)."""
    found = {}
    for path in ALL_FILES:
        src = strip_comments(read(path))
        for regex in (CALL_RE, ATTR_RE, FIELD_RE):
            for match in regex.finditer(src):
                key = match.group(1)
                if key in NOT_KEYS or key.endswith('.'):
                    continue          # 'dock.cat.' + cat gibi ön ek parçaları
                found.setdefault(key, set()).add(path.name)
    # Güverte kategori sekmeleri dinamik kurulur ('dock.cat.' + cat)
    for cat in DOCK_CATEGORIES:
        found.setdefault('dock.cat.' + cat, set()).add('analysis_dock.js')
    return found


USED = used_keys()


# ---------------------------------------------------------------------------
# 1. Sözdizimi
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which('node') is None, reason='node kurulu değil')
@pytest.mark.parametrize('path', ALL_FILES + [DICT_JS], ids=lambda p: p.name)
def test_js_syntax_ok(path):
    result = subprocess.run([shutil.which('node'), '--check', str(path)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, '%s sözdizimi hatası:\n%s' % (path.name,
                                                                 result.stderr)


def test_dictionary_exists_and_is_registered():
    assert DICT_JS.exists(), 'hrma/static/js/i18n_common.js yok'
    source = read(DICT_JS)
    assert "I18N.register(DICT, 'i18n_common.js')" in source, \
        'i18n_common.js register() çağırmıyor — sözlük hiç yüklenmez'
    assert '__I18N_PENDING' in source, \
        'i18n_common.js yükleme sırası koruması (__I18N_PENDING) içermiyor'
    assert len(EN) > 500, 'EN sözlüğü beklenenden küçük: %d anahtar' % len(EN)


def test_en_tr_key_sets_match_and_values_non_empty():
    assert set(EN) == set(TR), (
        'EN/TR anahtar kümeleri farklı: yalnız EN %s, yalnız TR %s'
        % (sorted(set(EN) - set(TR))[:10], sorted(set(TR) - set(EN))[:10]))
    empty = sorted(k for k in EN if not EN[k].strip() or not TR[k].strip())
    assert not empty, 'Boş çeviri değeri: %s' % empty


def test_english_block_has_no_turkish_letters():
    """EN bloğuna yanlışlıkla Türkçe metin sızmasın (blokların karışması)."""
    turkish = re.compile(r'[çğıİöşüÇĞÖŞÜ]')
    slips = sorted(k for k, v in EN.items()
                   if turkish.search(v) and 'Türkçe' not in v)
    assert not slips, 'EN bloğunda Türkçe karakterli değerler: %s' % slips[:10]


# ---------------------------------------------------------------------------
# 2. İki yönlü tutarlılık
# ---------------------------------------------------------------------------
def test_every_used_key_exists_in_dictionary():
    """Kodda çağrılan anahtarın sözlükte karşılığı olmalı (yazım hatası)."""
    # Ana sayfa sözlüğü (i18n.js çekirdeği) bu dosyanın kapsamı dışında
    core_prefixes = ('lang.', 'page.', 'hero.', 'cap.', 'section.', 'card.',
                     'btn.', 'link.', 'footer.', 'nav.')
    missing = sorted(k for k in USED
                     if k not in EN and not k.startswith(core_prefixes))
    detail = '\n'.join('  %s  (%s)' % (k, ', '.join(sorted(USED[k])))
                       for k in missing[:25])
    assert not missing, 'Sözlükte olmayan anahtarlar (%d):\n%s' % (len(missing),
                                                                   detail)


def test_every_dictionary_key_is_used():
    """Ölü çeviri koruması: sözlükteki her anahtar kodda geçmeli."""
    unused = sorted(k for k in EN if k not in USED)
    assert not unused, ('Kodda kullanılmayan sözlük anahtarları (%d): %s'
                        % (len(unused), unused[:25]))


# ---------------------------------------------------------------------------
# 3. Dil değişiminde yeniden basma
# ---------------------------------------------------------------------------
def test_dock_rerenders_panels_on_language_change():
    """Güverte, saklanan yanıtla panelleri yeniden çizen bir onChange kaydeder."""
    src = read(STATIC_JS / 'analysis_dock.js')
    assert 'I18N.onChange' in src, 'analysis_dock.js dil değişimini dinlemiyor'
    assert 'lastData' in src, \
        'analysis_dock.js son yanıtı saklamıyor — dil değişince panel boşalır'
    assert 'function rerenderAll' in src, \
        'analysis_dock.js rerenderAll() kaybolmuş (dil değişiminde yeniden çizim)'


@pytest.mark.parametrize('name', [
    'app.js', 'injector_panel.js', 'sixdof_panel.js', 'transient_panel.js',
])
def test_self_mounted_modules_listen_for_language_change(name):
    """Kendi DOM'unu kuran modüller dil değişimini dinlemeli."""
    src = read(STATIC_JS / name)
    assert 'I18N.onChange' in src, \
        '%s dil değişiminde kendini yeniden basmıyor' % name


def test_feed_panel_rerenders_tabs_on_language_change():
    src = read(PANELS_DIR / 'feed_panel.js')
    assert 'I18N.onChange' in src and 'rerenderTabs' in src, \
        'feed_panel.js kendi sekmelerini dil değişiminde yenilemiyor'


# ---------------------------------------------------------------------------
# 4. Güverte sözleşmesi: başlık ve alan etiketleri anahtarlı
# ---------------------------------------------------------------------------
def test_dock_supports_label_keys():
    src = read(STATIC_JS / 'analysis_dock.js')
    assert 'titleKey' in src, 'analysis_dock.js panel başlığı anahtarını okumuyor'
    assert 'i18nAttr(' in src, \
        'analysis_dock.js etiketlere data-i18n basmıyor — dil değişince form İngilizce kalır'


@pytest.mark.parametrize('path', PANEL_FILES, ids=lambda p: p.name)
def test_panel_registers_title_key(path):
    src = strip_comments(read(path))
    if 'AnalysisDock.register(' not in src:
        pytest.skip('%s güverteye panel kaydetmiyor' % path.name)
    assert 'titleKey:' in src, \
        '%s panel başlığı için titleKey vermiyor (başlık çevrilmez)' % path.name
    key = re.search(r"titleKey:\s*'([\w.]+)'", src).group(1)
    assert key in EN, '%s titleKey sözlükte yok: %s' % (path.name, key)


@pytest.mark.parametrize('path', PANEL_FILES, ids=lambda p: p.name)
def test_panel_field_labels_have_keys(path):
    """`fields: [[id, 'Label', def, step]]` biçiminde anahtarsız alan kalmasın."""
    src = strip_comments(read(path))
    match = re.search(r'fields:\s*\[', src)
    if not match:
        pytest.skip('%s alan listesi tanımlamıyor' % path.name)
    depth = 0
    start = match.end() - 1
    for idx in range(start, len(src)):
        if src[idx] == '[':
            depth += 1
        elif src[idx] == ']':
            depth -= 1
            if depth == 0:
                body = src[start + 1:idx]
                break
    # Yalnız ÜST düzey alan satırları: ['id', 'Label', varsayılan, adım, 'anahtar']
    # (seçenek listeleri iç içe dizidir, ayrı ayrı denetlenmez).
    rows = []
    depth = 0
    row_start = None
    for idx, ch in enumerate(body):
        if ch == '[':
            depth += 1
            if depth == 1:
                row_start = idx
        elif ch == ']':
            depth -= 1
            if depth == 0 and row_start is not None:
                rows.append(body[row_start:idx + 1])
                row_start = None
    rows = [r for r in rows if re.match(r"\[\s*'[\w]+'\s*,\s*'", r)]
    bad = [r for r in rows if not re.search(r",\s*'[\w]+\.[\w.]+'\s*\]\s*$", r, re.S)]
    detail = '\n'.join('  ' + ' '.join(r.split())[:90] for r in bad[:10])
    assert not bad, ('%s içinde çeviri anahtarı olmayan alan etiketi (%d):\n%s'
                     % (path.name, len(bad), detail))


@pytest.mark.parametrize('cat', DOCK_CATEGORIES)
def test_dock_category_labels_translated(cat):
    key = 'dock.cat.' + cat
    assert key in EN, 'Kategori sekmesi çevirisi yok: %s' % key
    assert TR[key] != EN[key] or not re.search(r'[A-Za-z]{3,}', EN[key]), \
        '%s sekmesi Türkçeye çevrilmemiş' % cat


# ---------------------------------------------------------------------------
# 5. Kalıntı avı — düz metin geçen ortak UI çağrıları
# ---------------------------------------------------------------------------
LITERAL_CALLS = (
    # (çağrı, açıklama) — ilk argümanı düz tırnaklı metin olan kullanım
    (re.compile(r"U\.sectionTitle\(\s*'"), 'U.sectionTitle'),
    (re.compile(r"U\.listBlock\(\s*'"), 'U.listBlock'),
    (re.compile(r"U\.statCard\(\s*'(?![A-Za-z_]*'\s*\))"), 'U.statCard'),
)


@pytest.mark.parametrize('path', PANEL_FILES, ids=lambda p: p.name)
def test_no_hardcoded_section_titles(path):
    """Bölüm başlığı / uyarı kutusu başlığı doğrudan metinle çağrılmamalı."""
    src = strip_comments(read(path))
    hits = []
    for regex, label in LITERAL_CALLS[:2]:
        for match in regex.finditer(src):
            line = src.count('\n', 0, match.start()) + 1
            hits.append('%s:%d %s(...)' % (path.name, line, label))
    assert not hits, ('Çeviriden geçmeyen başlık çağrıları:\n  '
                      + '\n  '.join(hits))


@pytest.mark.parametrize('path', PANEL_FILES, ids=lambda p: p.name)
def test_status_messages_go_through_translation(path):
    """`status.textContent = 'metin'` gibi düz durum mesajı kalmamalı."""
    src = strip_comments(read(path))
    pattern = re.compile(r"(?:status|note|plotEl|el)\.textContent\s*=\s*'"
                         r"(?![A-Z_]{0,3}')([^']{4,})'")
    hits = []
    for match in pattern.finditer(src):
        line = src.count('\n', 0, match.start()) + 1
        hits.append('%s:%d  %r' % (path.name, line, match.group(1)[:60]))
    assert not hits, ('Çevrilmemiş durum mesajı:\n  ' + '\n  '.join(hits))


def test_no_emoji_in_dictionary():
    """Berke kuralı: arayüz metinlerinde emoji yok."""
    emoji = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF]')
    found = [k for k in EN if emoji.search(EN[k]) or emoji.search(TR[k])]
    assert not found, 'Sözlükte emoji: %s' % found[:10]


def test_placeholders_match_between_languages():
    """{yer_tutucu} kümesi EN ve TR'de aynı olmalı (eksik parametre = bozuk metin)."""
    ph = re.compile(r'\{(\w+)\}')
    bad = []
    for key in EN:
        if set(ph.findall(EN[key])) != set(ph.findall(TR[key])):
            bad.append('%s: EN %s vs TR %s' % (key, sorted(set(ph.findall(EN[key]))),
                                               sorted(set(ph.findall(TR[key])))))
    assert not bad, 'Yer tutucu uyuşmazlığı:\n  ' + '\n  '.join(bad[:15])


if __name__ == '__main__':                  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, '-v']))
