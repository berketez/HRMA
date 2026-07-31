"""Sıvı sayfasında bağlanmamış girdilerin dürüst işaretlenmesi (2026-07-19 F2).

Denetimin "sessiz yutulan girdi" sınıfı: kullanıcı 35 alanı dolduruyor,
motor bunları BİLİNÇLİ olarak kullanmıyor ve sayfa bunu söylemiyordu.
LiquidRocketEngine.unwired_inputs() artık üç kategori bildiriyor:

    informational            kayıt/etiket alanı, çözücü girdisi değil
    transient_not_modelled   başlatma/durdurma rejimi modellenmiyor
    reported_for_comparison  çözücü kendi değerini hesaplıyor

liquid.html bu listeyi hesaptan SONRA okuyup her alanın yanına kategorisine
göre farklı bir rozet basar. Bu dosya sözleşmeyi kilitler:

  1. Rozetler YANITTAN üretilir. Şablonda "bağlanmamış alan" sabit listesi
     yoktur (hesap ÖNCESİ statik not ayrı bir mekanizmadır ve
     test_liquid_page_contract.py tarafından kilitlenir). Motor bir alanı
     bağlayıp listeden çıkarınca rozet kendiliğinden kalkar.
  2. Üç kategori üç FARKLI metin alır; tanınmayan kategori sessizce
     yutulmaz, kategori adıyla ekrana basılır.
  3. reported_for_comparison alanlarında çözücünün GERÇEK değeri gösterilir
     ve kullanıcının girdiği değerle arasındaki sapma %20'yi aşarsa görsel
     uyarı çıkar.
  4. Motorun input_warnings listesi uyarı panelinde görünür.
  5. Kullanılan her i18n anahtarının EN ve TR karşılığı vardır.
  6. Hesap yapılmadan hiçbir rozet basılmaz (yanıt yokken bilinmez).

Davranış testleri gerçekten çalıştırılarak yapılır: şablondaki rozet bloğu
işaretçiler arasından ayıklanıp küçük bir DOM taklidiyle node üzerinde
koşturulur (bkz. _run_badges). Kaynak taraması yalnız çalıştırılamayan
iddialar için kullanılır.
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
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'
DICT_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_pages.js'

BLOCK_START = '// >>> LIQUID_UNWIRED_BADGES_START'
BLOCK_END = '// <<< LIQUID_UNWIRED_BADGES_END'

# Yanıttaki kategori adları ve beklenen İngilizce rozet metinleri.
CATEGORY_TEXT = {
    'informational': 'Reference only: not used by the solver',
    'transient_not_modelled': 'Startup/shutdown transients are not modelled yet',
    'reported_for_comparison':
        'Computed by the solver; your value is compared, not used',
}

# Çözücü değeri gösterilen (karşılaştırma) alanlar — değerin yanıttaki yeri
# alan başına farklı olduğu için şablonda bir konum çözümleyicisi vardır.
# v2.6.26: motor 'turbine_inlet_pressure' alanını (öncelik genişleme
# oranında; ima edilen giriş basıncı yalnız karşılaştırılır) ve oda çapı
# öncelik aldığı koşularda 'contraction_ratio' alanını da bu kategoriyle
# beyan etmeye başladı; ikisi de şablonda YALNIZ çözümleyici anahtarı olarak
# geçer (test_comparison_ids_appear_only_as_resolver_keys bunu kilitler).
COMPARISON_IDS = {
    'throat_diameter', 'fuel_injection_velocity', 'oxidizer_injection_velocity',
    'fuel_orifice_diameter', 'oxidizer_orifice_diameter',
    'target_thrust_to_weight', 'turbine_inlet_pressure', 'contraction_ratio',
}


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def html():
    return LIQUID_HTML.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def badge_block(html):
    """Şablondaki rozet bloğunun gövdesi (işaretçiler arası)."""
    assert BLOCK_START in html and BLOCK_END in html, \
        'rozet bloğu işaretçileri bulunamadı'
    start = html.index(BLOCK_START) + len(BLOCK_START)
    return html[start:html.index(BLOCK_END)]


@pytest.fixture(scope='module')
def engine_unwired():
    """Motorun GERÇEK beyanı — şablon testi kod gerçeğine bağlanır."""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    # unwired_inputs() salt sabit döndürür; motor kurmak (CEA) gereksiz pahalı.
    return LiquidRocketEngine.unwired_inputs(None)


def dict_block(lang):
    source = DICT_JS.read_text(encoding='utf-8')
    match = re.search(r'^\s{8}%s:\s*\{$' % lang, source, re.M)
    assert match, "i18n_pages.js içinde '%s' bloğu yok" % lang
    body = source[match.end():]
    return dict(re.findall(r"^\s*'([^']+)':\s*'(.*)',?$",
                           body[:body.index('\n        }')], re.M))


def inline_scripts(text):
    return re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', text, re.S)


# ---------------------------------------------------------------------------
# node koşum ortamı: küçük DOM taklidi + T/TF kaydı
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const FIELDS = __FIELDS__;
const RESPONSES = __RESPONSES__;
const usedKeys = [];

function selMatch(node, sel) {
    const attr = sel.match(/\[([^\]=]+)\]/);
    if (attr) return node.attrs[attr[1]] !== undefined;
    return sel.split('.').filter(Boolean).every(c => node.classes.has(c));
}

function makeNode(tag) {
    const node = {
        tagName: tag, attrs: {}, classes: new Set(), children: [],
        parent: null, textContent: '', value: null,
        classList: {
            add: c => node.classes.add(c),
            remove: c => node.classes.delete(c),
            contains: c => node.classes.has(c)
        },
        setAttribute: (k, v) => { node.attrs[k] = String(v); },
        getAttribute: k => (k in node.attrs ? node.attrs[k] : null),
        appendChild: child => { child.parent = node; node.children.push(child); return child; },
        remove: () => {
            if (!node.parent) return;
            const i = node.parent.children.indexOf(node);
            if (i >= 0) node.parent.children.splice(i, 1);
            node.parent = null;
        },
        closest: sel => {
            let n = node;
            while (n) { if (selMatch(n, sel)) return n; n = n.parent; }
            return null;
        },
        querySelector: sel => descend(node).find(n => selMatch(n, sel)) || null
    };
    Object.defineProperty(node, 'className', {
        get: () => Array.from(node.classes).join(' '),
        set: v => { node.classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
    });
    return node;
}

function descend(node) {
    const out = [];
    (function walk(n) { n.children.forEach(c => { out.push(c); walk(c); }); })(node);
    return out;
}

const root = makeNode('body');
const byId = {};
FIELDS.forEach(spec => {
    const group = makeNode('div');
    group.className = 'form-group' + (spec.staticNote ? ' not-wired' : '');
    if (spec.staticNote) {
        const note = makeNode('small');
        note.className = 'not-wired-note';
        note.textContent = 'Not wired to the solver yet';
        group.appendChild(note);
    }
    const input = makeNode('input');
    input.attrs.id = spec.id;
    input.value = spec.value;
    group.appendChild(input);
    root.appendChild(group);
    byId[spec.id] = input;
});

const document = {
    getElementById: id => (id in byId ? byId[id] : null),
    createElement: makeNode,
    querySelectorAll: sel => descend(root).filter(n => selMatch(n, sel))
};

function T(key, fallback) { usedKeys.push(key); return fallback; }
function TF(key, params, fallback) {
    usedKeys.push(key);
    return String(fallback).replace(/\{(\w+)\}/g, (whole, name) =>
        (params && name in params) ? String(params[name]) : whole);
}

__BLOCK__

function snapshot() {
    return FIELDS.map(spec => {
        const group = byId[spec.id].closest('.form-group');
        return {
            id: spec.id,
            groupClasses: Array.from(group.classes),
            hasStaticNote: !!group.querySelector('.not-wired-note'),
            nodes: group.children
                .filter(c => c.attrs['data-unwired-badge'] !== undefined)
                .map(c => ({
                    kind: c.attrs['data-unwired-badge'],
                    classes: Array.from(c.classes),
                    text: c.textContent
                }))
        };
    });
}

const runs = RESPONSES.map(resp => {
    const missing = applyUnwiredBadges(resp);
    return { missing: missing, fields: snapshot() };
});
console.log(JSON.stringify({ runs: runs, usedKeys: usedKeys }));
"""


def _run_badges(block, fields, responses):
    """Rozet bloğunu node'da çalıştırır; her koşu için DOM görüntüsü döner."""
    node = shutil.which('node')
    script = (HARNESS
              .replace('__FIELDS__', json.dumps(fields))
              .replace('__RESPONSES__', json.dumps(responses))
              .replace('__BLOCK__', block))
    handle = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8')
    handle.write(script)
    handle.close()
    try:
        result = subprocess.run([node, handle.name], capture_output=True,
                                text=True)
    finally:
        os.unlink(handle.name)
    assert result.returncode == 0, 'rozet bloğu node altında çöktü:\n' + result.stderr
    return json.loads(result.stdout)


def badge_of(run_fields, field_id, kind='__category__'):
    entry = next(f for f in run_fields if f['id'] == field_id)
    if kind == '__category__':
        return [n for n in entry['nodes']
                if n['kind'] not in ('solver-value', 'solver-mismatch')]
    return [n for n in entry['nodes'] if n['kind'] == kind]


needs_node = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')


# ---------------------------------------------------------------------------
# 1. Sözdizim
# ---------------------------------------------------------------------------
@needs_node
def test_inline_scripts_parse(html):
    """Eklenen blok hiçbir inline script'i bozmamalı."""
    blocks = inline_scripts(html)
    assert len(blocks) >= 3, 'satır içi script blokları bulunamadı'
    for index, body in enumerate(blocks):
        handle = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                             encoding='utf-8')
        handle.write(body)
        handle.close()
        try:
            result = subprocess.run([shutil.which('node'), '--check', handle.name],
                                    capture_output=True, text=True)
        finally:
            os.unlink(handle.name)
        assert result.returncode == 0, (
            '%d. inline script sözdizimi bozuk:\n%s' % (index, result.stderr[:1200]))


# ---------------------------------------------------------------------------
# 2. Rozetler yanıttan üretilir (sabit alan listesi yok)
# ---------------------------------------------------------------------------
def test_badges_are_built_from_the_response(badge_block):
    """Blok, kategori listesini yanıttan okur; alan adlarını kendi tutmaz."""
    assert 'unwired_inputs' in badge_block, 'yanıttaki liste hiç okunmuyor'
    assert 'Object.keys(declared)' in badge_block, \
        'kategoriler yanıttan dolaşılmıyor (sabit kategori listesi şüphesi)'


def test_block_holds_no_hardcoded_field_list(badge_block, engine_unwired):
    """Karşılaştırma çözümleyicisi dışında hiçbir alan adı blokta geçmez.

    reported_for_comparison alanları istisnadır: çözücü değerinin yanıttaki
    YERİ alan başına farklıdır, bu yüzden bir konum çözümleyicisi vardır.
    O çözümleyicideki alanlar bile "bağlanmamış" listesi değildir; eşlemesi
    olmayan alan da rozet alır (bkz. test_comparison_without_mapping...).
    """
    declared = [name for names in engine_unwired.values() for name in names]
    assert declared, 'motor hiçbir alan bildirmiyor (test anlamsız)'
    leaked = [name for name in declared
              if name not in COMPARISON_IDS and name in badge_block]
    assert not leaked, (
        'rozet bloğunda sabit kodlanmış alan adları var: %s' % leaked)
    # Alan adlarından oluşan dizi literali (['a', 'b', ...]) olmamalı.
    assert not re.search(r"\[\s*'[a-z][a-z0-9_]{3,}'\s*,", badge_block), \
        'blokta alan adı dizisi literali var'


def test_comparison_ids_appear_only_as_resolver_keys(badge_block):
    """Karşılaştırma alanları yalnız değer çözümleyicisinin anahtarlarıdır."""
    resolver = re.search(r'var COMPARISON_SOLVER_VALUE = \{(.*?)\n        \};',
                         badge_block, re.S)
    assert resolver, 'COMPARISON_SOLVER_VALUE çözümleyicisi bulunamadı'
    outside = badge_block.replace(resolver.group(0), '')
    leaked = sorted(i for i in COMPARISON_IDS if i in outside)
    assert not leaked, 'karşılaştırma alanları çözümleyici dışında da sabit: %s' % leaked


@needs_node
def test_unknown_field_id_still_gets_a_badge(badge_block):
    """Şablonda hiç geçmeyen bir alan adı da rozetlenir (kanıt: dinamik)."""
    novel = 'brand_new_solver_field'
    assert novel not in LIQUID_HTML.read_text(encoding='utf-8')
    out = _run_badges(badge_block,
                      [{'id': novel, 'value': '1', 'staticNote': False}],
                      [{'unwired_inputs': {'informational': [novel]}}])
    badges = badge_of(out['runs'][0]['fields'], novel)
    assert len(badges) == 1, 'yanıtta bildirilen yeni alan rozetlenmedi'
    assert badges[0]['text'] == CATEGORY_TEXT['informational']


@needs_node
def test_badge_disappears_when_engine_wires_the_field(badge_block):
    """Alan yanıttan çıkınca rozet de kalkar (kod değişikliği gerekmez)."""
    fields = [{'id': 'min_throttle', 'value': '30', 'staticNote': True}]
    out = _run_badges(badge_block, fields, [
        {'unwired_inputs': {'transient_not_modelled': ['min_throttle']}},
        {'unwired_inputs': {'transient_not_modelled': []}},
    ])
    assert len(badge_of(out['runs'][0]['fields'], 'min_throttle')) == 1
    assert badge_of(out['runs'][1]['fields'], 'min_throttle') == [], \
        'motor alanı bağladıktan sonra eski rozet ekranda kaldı'


# ---------------------------------------------------------------------------
# 3. Üç kategori, üç farklı metin
# ---------------------------------------------------------------------------
@needs_node
def test_three_categories_get_three_distinct_texts(badge_block, engine_unwired):
    """Motorun bildirdiği her kategori kendi metnini alır."""
    assert set(engine_unwired) == set(CATEGORY_TEXT), (
        'motorun kategorileri değişmiş: %s' % sorted(engine_unwired))
    sample = dict((cat, names[:1]) for cat, names in engine_unwired.items())
    fields = [{'id': names[0], 'value': '1', 'staticNote': False}
              for names in sample.values()]
    out = _run_badges(badge_block, fields, [{'unwired_inputs': sample}])

    texts = {}
    for category, names in sample.items():
        badges = badge_of(out['runs'][0]['fields'], names[0])
        assert len(badges) == 1, '%s için rozet yok' % category
        assert badges[0]['kind'] == category
        texts[category] = badges[0]['text']
        assert badges[0]['text'] == CATEGORY_TEXT[category]
    assert len(set(texts.values())) == 3, 'kategoriler aynı metni paylaşıyor'
    # Kategori başına farklı CSS sınıfı (görsel dil farklı olmalı)
    classes = set()
    for names in sample.values():
        classes |= set(badge_of(out['runs'][0]['fields'], names[0])[0]['classes'])
    assert len([c for c in classes if c.startswith('unwired-badge-')]) == 3


@needs_node
def test_unknown_category_is_reported_not_swallowed(badge_block):
    """Motor yeni bir kategori bildirirse adı ekrana basılır."""
    out = _run_badges(badge_block,
                      [{'id': 'some_field', 'value': '1', 'staticNote': False}],
                      [{'unwired_inputs': {'brand_new_category': ['some_field']}}])
    badges = badge_of(out['runs'][0]['fields'], 'some_field')
    assert len(badges) == 1
    assert 'brand_new_category' in badges[0]['text'], \
        'tanınmayan kategori sessizce yutuldu'


@needs_node
def test_missing_field_is_reported(badge_block):
    """Sayfada karşılığı olmayan alan sessizce düşmez, rapora girer."""
    out = _run_badges(badge_block, [],
                      [{'unwired_inputs': {'informational': ['ghost_field']}}])
    assert out['runs'][0]['missing'] == ['ghost_field']


# ---------------------------------------------------------------------------
# 4. Karşılaştırma alanları: gerçek çözücü değeri + %20 sapma uyarısı
# ---------------------------------------------------------------------------
@needs_node
def test_comparison_shows_real_solver_value_and_flags_deviation(badge_block):
    """Çözücü değeri gösterilir; %20 üstü sapma görsel uyarı alır."""
    response = {
        'unwired_inputs': {'reported_for_comparison': [
            'throat_diameter', 'fuel_injection_velocity']},
        'throat_diameter': 0.03936403427826753,          # metre -> 39.36 mm
        'injection_system': {'fuel_injection_velocity': 40.52538400146577},
    }
    fields = [
        # 50 mm girildi, çözücü 39.36 mm -> %27 sapma (eşik %20)
        {'id': 'throat_diameter', 'value': '50', 'staticNote': False},
        # 40 m/s girildi, çözücü 40.53 m/s -> %1.3 sapma (eşik altında)
        {'id': 'fuel_injection_velocity', 'value': '40', 'staticNote': False},
    ]
    out = _run_badges(badge_block, fields, [response])
    run = out['runs'][0]['fields']

    value = badge_of(run, 'throat_diameter', 'solver-value')
    assert len(value) == 1 and '39.36 mm' in value[0]['text'], \
        'çözücünün gerçek boğaz çapı gösterilmiyor: %s' % value
    mismatch = badge_of(run, 'throat_diameter', 'solver-mismatch')
    assert len(mismatch) == 1, '%27 sapma uyarı almadı'
    assert '27' in mismatch[0]['text'] and '50.00 mm' in mismatch[0]['text']
    assert 'solver-value-mismatch' in value[0]['classes']

    close = badge_of(run, 'fuel_injection_velocity', 'solver-value')
    assert len(close) == 1 and '40.5 m/s' in close[0]['text']
    assert badge_of(run, 'fuel_injection_velocity', 'solver-mismatch') == [], \
        'eşik altındaki sapma yanlışlıkla uyarı üretti'
    assert 'solver-value-mismatch' not in close[0]['classes']


@needs_node
def test_comparison_without_solver_value_says_so(badge_block):
    """Çözücü değeri yanıtta yoksa uydurulmaz, açıkça bildirilir."""
    out = _run_badges(
        badge_block,
        [{'id': 'throat_diameter', 'value': '50', 'staticNote': False},
         {'id': 'unmapped_output', 'value': '3', 'staticNote': False}],
        [{'unwired_inputs': {'reported_for_comparison':
                             ['throat_diameter', 'unmapped_output']}}])
    run = out['runs'][0]['fields']
    for field in ('throat_diameter', 'unmapped_output'):
        # Eşlemesi olmayan alan da rozet alır; değer yerine dürüst not çıkar.
        assert len(badge_of(run, field)) == 1
        value = badge_of(run, field, 'solver-value')
        assert len(value) == 1, '%s için not yok' % field
        assert 'not reported' in value[0]['text'], value[0]['text']
        assert badge_of(run, field, 'solver-mismatch') == []


def test_mismatch_threshold_is_a_named_constant(badge_block):
    """Eşik tek yerde tanımlı (sihirli sayı yok)."""
    assert re.search(r'var COMPARISON_MISMATCH_FRACTION = 0\.20;', badge_block)
    assert badge_block.count('0.20') == 1


# ---------------------------------------------------------------------------
# 5. Uyarı paneli: input_warnings
# ---------------------------------------------------------------------------
def test_input_warnings_reach_the_warnings_panel(html):
    """Motorun girdi uyarıları panelde listelenir."""
    block = html[html.index('function displayLiquidWarnings'):]
    block = block[:block.index('// ==================================================================',
                               block.index('panel.style.display = \'block\';'))]
    assert 'r.input_warnings' in block, 'input_warnings hiç okunmuyor'
    assert 'inputs.forEach' in block, 'input_warnings listelenmiyor'
    assert '!inputs.length' in block, \
        'panel gizleme koşulu input_warnings ile güncellenmemiş'
    assert 'unwiredFieldsNotOnPage' in block, \
        'sayfada bulunmayan alanlar panele girmiyor'
    assert "T('liq.msg.input_warning_tag'" in block, 'uyarı etiketi çevrilmiyor'


def test_warnings_panel_is_hidden_until_there_is_something_to_say(html):
    match = re.search(r'<div id="warningsPanel"[^>]*>', html)
    assert match and 'display: none' in match.group(0)


# Uyarı panelindeki etiketler ve karşılıkları. app.js (hibrit sayfa) aynı
# karşılıkları kullanır; TR seçiliyken panelin tamamı Türkçe olmalıdır.
PANEL_LABEL_KEYS = {
    'liq.msg.critical_warning_tag': ('CRITICAL', 'KRİTİK'),
    'liq.msg.warning_tag': ('WARNING', 'UYARI'),
    'liq.msg.validation_status_label': ('Validation status:', 'Doğrulama durumu:'),
}


def test_warning_panel_labels_come_from_the_dictionary(html):
    """Panel etiketleri şablona gömülü İngilizce olmamalı.

    test_i18n_pages.py'nin serbest metin taraması, içinde `${...}` geçen
    şablon literallerini atlar; bu yüzden `>Validation status: ${...}<`
    kalıbı oradan kaçabiliyordu. Burada doğrudan kilitleniyor.
    """
    start = html.index('function displayLiquidWarnings')
    block = html[start:html.index('function _liquidExportStatus', start)]
    for key in PANEL_LABEL_KEYS:
        assert "T('%s'" % key in block, '%s panelde kullanılmıyor' % key
    for literal in ("item('CRITICAL'", "item('WARNING'", '>Validation status:'):
        assert literal not in block, \
            'panelde çevrilmemiş sabit metin kaldı: %s' % literal


def test_warning_panel_labels_are_translated_both_ways():
    en, tr = dict_block('en'), dict_block('tr')
    for key, (en_value, tr_value) in PANEL_LABEL_KEYS.items():
        assert en.get(key) == en_value, '%s EN karşılığı: %r' % (key, en.get(key))
        assert tr.get(key) == tr_value, '%s TR karşılığı: %r' % (key, tr.get(key))


# ---------------------------------------------------------------------------
# 6. i18n: kullanılan her anahtarın EN + TR karşılığı var
# ---------------------------------------------------------------------------
@needs_node
def test_every_key_used_by_the_badges_is_translated(badge_block):
    """Rozet üretimi sırasında istenen anahtarlar iki dilde de tanımlı."""
    response = {
        'unwired_inputs': {
            'informational': ['stability_margin'],
            'transient_not_modelled': ['min_throttle'],
            'reported_for_comparison': ['throat_diameter', 'unmapped_output'],
            'brand_new_category': ['some_field'],
        },
        'throat_diameter': 0.03936403427826753,
    }
    fields = [{'id': name, 'value': '50', 'staticNote': False}
              for name in ('stability_margin', 'min_throttle', 'throat_diameter',
                           'unmapped_output', 'some_field')]
    out = _run_badges(badge_block, fields, [response])
    used = sorted(set(out['usedKeys']))
    assert used, 'hiç i18n anahtarı kullanılmamış'

    en, tr = dict_block('en'), dict_block('tr')
    missing_en = [k for k in used if k not in en]
    missing_tr = [k for k in used if k not in tr]
    assert not missing_en, 'EN karşılığı olmayan anahtarlar: %s' % missing_en
    assert not missing_tr, 'TR karşılığı olmayan anahtarlar: %s' % missing_tr
    # Türkçe metinler gerçekten çevrilmiş olmalı (ASCII kopya değil)
    same = [k for k in used if len(en[k]) > 20 and en[k] == tr[k]]
    assert not same, 'çevrilmemiş (EN kopyası) TR değerleri: %s' % same


def test_template_uses_the_new_keys(html):
    """Rozet metinleri sözlükten okunur, şablona gömülü değil."""
    for key in ('liq.msg.unwired_informational', 'liq.msg.unwired_transient',
                'liq.msg.unwired_comparison', 'liq.msg.unwired_other',
                'liq.msg.solver_value', 'liq.msg.solver_value_unavailable',
                'liq.msg.entry_deviation', 'liq.msg.input_warning_tag',
                'liq.msg.unwired_fields_not_on_page'):
        assert "'%s'" % key in html, '%s şablonda kullanılmıyor' % key


def test_new_turkish_values_keep_turkish_letters():
    """TDK imlası: yeni TR metinleri ASCII'ye kaçmamış."""
    tr = dict_block('tr')
    for key in ('liq.msg.unwired_informational', 'liq.msg.unwired_transient',
                'liq.msg.unwired_comparison', 'liq.ui.solver_scope_rest',
                'liq.ui.solver_scope_core_inputs'):
        assert re.search(r'[çğıİöşüÇĞÖŞÜ]', tr[key]), \
            '%s Türkçe karakter içermiyor: %r' % (key, tr[key])


# ---------------------------------------------------------------------------
# 7. Hesap öncesi rozet yok
# ---------------------------------------------------------------------------
def test_badges_are_only_applied_after_a_calculation(html):
    """Rozet üreteci yalnız sonuç gösteriminden çağrılır."""
    calls = re.findall(r'\n\s*applyUnwiredBadges\(([^)]*)\)', html)
    assert calls, 'applyUnwiredBadges hiç çağrılmıyor'
    assert all(arg.strip() == 'results' for arg in calls), \
        'rozet üreteci sonuçsuz çağrılıyor: %s' % calls
    init = html[html.index('// Initialize'):]
    assert 'applyUnwiredBadges' not in init, \
        'sayfa açılışında rozet basılıyor (yanıt yokken bilinemez)'
    # displayResults içinden, uyarı panelinden ÖNCE çağrılır (panel raporu okur)
    body = html[html.index('function displayResults(results)'):]
    body = body[:body.index('const metricsDiv')]
    assert body.index('applyUnwiredBadges(results);') < \
        body.index('displayLiquidWarnings(results);')


@needs_node
def test_no_badges_without_a_response(badge_block):
    """Yanıt yoksa hiçbir rozet basılmaz; sayfa açılış notu korunur."""
    fields = [{'id': 'min_throttle', 'value': '30', 'staticNote': True}]
    out = _run_badges(badge_block, fields, [{}, None])
    for run in out['runs']:
        entry = run['fields'][0]
        assert entry['nodes'] == [], 'yanıt yokken rozet basıldı'
        assert entry['hasStaticNote'], 'açılıştaki dürüst not silindi'
        assert 'has-unwired-badge' not in entry['groupClasses']
        assert run['missing'] == []


@needs_node
def test_static_note_is_replaced_by_the_category_badge(badge_block):
    """Yanıt gelince genel not yerini kategorili rozete bırakır."""
    fields = [{'id': 'min_throttle', 'value': '30', 'staticNote': True}]
    out = _run_badges(badge_block, fields, [
        {'unwired_inputs': {'transient_not_modelled': ['min_throttle']}}])
    entry = out['runs'][0]['fields'][0]
    assert not entry['hasStaticNote'], 'genel not ile rozet birlikte gösteriliyor'
    assert 'has-unwired-badge' in entry['groupClasses']
    assert badge_of(out['runs'][0]['fields'], 'min_throttle')[0]['text'] == \
        CATEGORY_TEXT['transient_not_modelled']
