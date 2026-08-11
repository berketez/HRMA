"""Form yerleşimi ve önizleme dürüstlüğü bekçisi (v2.6.27, A6).

Bu dosya, arka uç testlerinin YAPISAL OLARAK göremediği dört kusuru kilitler.
Hepsi Ayberk'in hibrit raporundan ya da aynı sınıfın ölçülmüş kati/sıvı
karşılıklarından geliyor:

1. ALAN SIRASI (Ayberk madde 1). ``of_ratio`` alanı "Basic Parameters"
   panelindeydi, yani sayfada yakıt ve oksitleyici panellerinden ÖNCE
   geliyordu. Yanındaki "Find Optimum" düğmesi ise ``fuel_type`` ve
   ``oxidizer_type`` okuyor: sayfada panel sınırını AŞAN tek denetim budur.
   Kullanıcı seçim yapmadan basınca select varsayılanları sessizce
   kullanılıyor, sonradan seçtiği çiftle İLGİSİZ bir optimum alana
   yazılıyordu. Böyle bir bekçi hiç yoktu; kusur geri gelebilirdi.

2. TEK VARSAYILAN. Aynı alan için sayfada iki ayrı varsayılan vardı
   (alanın ``value`` niteliği ve toplayıcıdaki ``|| x`` yedeği). İkisi
   ayrışırsa kullanıcı gördüğünden başka bir sayı gönderilir.

3. ÖLÜ ALANLARIN İŞARETLENMESİ. Hibritte çözücüye ulaşmayan beş alan
   rozetsizdi; sıvı sayfasında aynı mekanizma vardı. Liste uydurma değil,
   deponun kendi beyanından gelir:
   ``tests/test_field_wiring_layer_a.py`` -> ``DECLARED_UNMODELLED['hybrid']``.
   Bu test iki dosyanın AYNI listeyi taşıdığını kilitler.

4. GRAIN ÖNİZLEMESİ. Kati sayfasındaki yıldız kesiti sabit 5 uçlu bir
   path'ti; form alanının varsayılanı 6, alt sınırı 3. Kullanıcı 8 uç girip
   5 uçlu şekil görüyordu. Önizleme artık form alanlarından üretiliyor ve
   çözücünün geometri tanımını (``_star_port_polygon`` / ``_star_params``)
   izliyor.

Çalıştırılabilir iddialar GERÇEKTEN çalıştırılır: hem hibritteki işaretleme
bloğu hem katideki önizleme bloğu şablondan ayıklanıp küçük bir DOM
taklidiyle node üzerinde koşturulur. Kaynak taraması yalnız koşturulamayan
iddialar için kullanılır.
"""

import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ADVANCED_HTML = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'
SOLID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'solid.html'
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'


@pytest.fixture(scope='module')
def advanced():
    return ADVANCED_HTML.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def solid():
    return SOLID_HTML.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def liquid():
    return LIQUID_HTML.read_text(encoding='utf-8')


def _block(text, start_marker, end_marker):
    assert start_marker in text and end_marker in text, \
        'blok işaretçileri bulunamadı: %s' % start_marker
    start = text.index(start_marker) + len(start_marker)
    return text[start:text.index(end_marker)]


def _run_node(script):
    node = shutil.which('node')
    if not node:                                   # pragma: no cover
        pytest.skip('node yok')
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                     encoding='utf-8') as fh:
        fh.write(script)
        path = fh.name
    try:
        proc = subprocess.run([node, path], capture_output=True, text=True,
                              timeout=60)
    finally:
        pathlib.Path(path).unlink(missing_ok=True)
    assert proc.returncode == 0, 'node hatası:\n%s\n%s' % (proc.stdout, proc.stderr)
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# 1. BÖLÜM SIRASI — O/F oksitleyiciden SONRA
# ---------------------------------------------------------------------------
# Sayfanın girdi formundaki panel başlıkları, bağımlılık sırasıyla.
# "Mixture Ratio" oksitleyiciden SONRA gelmek ZORUNDA (bkz. dosya başlığı).
EXPECTED_SECTIONS = [
    'adv.sec.motorInformation',
    'adv.sec.flightEnvironment',
    'adv.sec.basicParameters',
    'adv.sec.advancedParameters',
    'adv.sec.fuelConfiguration',
    'adv.sec.oxidizerConfiguration',
    'adv.sec.mixtureRatio',
    'adv.sec.injectorConfiguration',
    'adv.sec.analysisType',
]


def _section_keys(html):
    """Girdi formundaki <h2> anahtarları, sayfadaki sırayla."""
    keys = []
    for match in re.finditer(r'<h2[^>]*>(.*?)</h2>', html, re.S):
        found = re.search(r'data-i18n="(adv\.sec\.[A-Za-z0-9]+)"',
                          match.group(0))
        if found:
            keys.append(found.group(1))
    return keys


def test_panel_sirasi_bagimlilik_sirasiyla_ayni(advanced):
    keys = _section_keys(advanced)
    # Sonuç panelleri de <h2> kullanıyor; girdi formu 'analysisType' ile biter.
    son = keys.index('adv.sec.analysisType')
    assert keys[:son + 1] == EXPECTED_SECTIONS, \
        'panel sırası değişti: %s' % keys[:son + 1]


def test_of_ratio_yakit_ve_oksitleyiciden_sonra(advanced):
    of_pos = advanced.index('id="of_ratio"')
    fuel_pos = advanced.index('id="fuel_type"')
    ox_pos = advanced.index('id="oxidizer_type"')
    assert of_pos > fuel_pos, 'O/F alanı yakıt seçiminden ÖNCE'
    assert of_pos > ox_pos, 'O/F alanı oksitleyici seçiminden ÖNCE'


def test_of_ratio_temel_parametreler_panelinde_degil(advanced):
    """Kusurun tam kendisi: alan Basic Parameters panelinin içindeydi."""
    basic = advanced.index('data-i18n="adv.sec.basicParameters"')
    advanced_params = advanced.index('data-i18n="adv.sec.advancedParameters"')
    of_pos = advanced.index('id="of_ratio"')
    assert not (basic < of_pos < advanced_params), \
        'O/F alanı yeniden Basic Parameters paneline girmiş'


def test_optimum_dugmesi_of_alaniyla_ayni_panelde(advanced):
    """Düğme ile yazdığı alan ayrı panellere düşerse kullanıcı ilişkiyi görmez."""
    of_pos = advanced.index('id="of_ratio"')
    btn_pos = advanced.index('onclick="findOptimumOF()"')
    mixture = advanced.index('data-i18n="adv.sec.mixtureRatio"')
    injector = advanced.index('data-i18n="adv.sec.injectorConfiguration"')
    assert mixture < of_pos < injector
    assert mixture < btn_pos < injector


def test_of_sonuc_kutusu_korundu(advanced):
    """id'ler JS/kaydet-yükle sözleşmesidir; taşıma sırasında değişmemeli."""
    assert 'id="optimum_of_result"' in advanced
    assert "getElementById('optimum_of_result')" in advanced


# ---------------------------------------------------------------------------
# 2. TEK VARSAYILAN
# ---------------------------------------------------------------------------
def test_of_varsayilani_tek_yerde_tutarli(advanced):
    field = re.search(r'<input[^>]*id="of_ratio"[^>]*>', advanced)
    assert field, 'of_ratio alanı bulunamadı'
    value = re.search(r'value="([\d.]+)"', field.group(0))
    assert value, 'of_ratio alanının varsayılanı yok'
    collector = re.search(
        r"of_ratio:\s*parseFloat\(document\.getElementById\('of_ratio'\)\.value"
        r"\s*\|\|\s*([\d.]+)\)", advanced)
    assert collector, 'toplayıcıdaki of_ratio yedeği bulunamadı'
    assert float(value.group(1)) == float(collector.group(1)), (
        'alanın varsayılanı (%s) ile toplayıcının yedeği (%s) ayrışmış'
        % (value.group(1), collector.group(1)))


def test_of_varsayilani_deponun_kanonik_tablosundan(advanced):
    """Varsayılan uydurma bir sayı değil: sayfanın KENDİ varsayılan çifti için
    deponun teorik optimum tablosundaki değerdir."""
    from hrma.utils.optimum_of_ratio import OptimumOFRatioFinder

    field = re.search(r'<input[^>]*id="of_ratio"[^>]*>', advanced)
    value = float(re.search(r'value="([\d.]+)"', field.group(0)).group(1))
    pair = re.search(r'data-default-pair="([a-z0-9]+)\+([a-z0-9]+)"',
                     field.group(0))
    assert pair, 'varsayılanın hangi itici çiftine ait olduğu yazılmamış'
    table = OptimumOFRatioFinder().theoretical_optimums
    key = (pair.group(1), pair.group(2))
    assert key in table, 'beyan edilen çift tabloda yok: %s' % (key,)
    assert value == pytest.approx(table[key]), (
        'varsayılan (%s) tablodaki değerden (%s) farklı' % (value, table[key]))


def test_varsayilan_cift_sayfanin_ilk_secenekleriyle_ayni(advanced):
    """Beyan edilen çift, sayfa açıldığında GERÇEKTEN seçili olan çift olmalı;
    yoksa not doğru, varsayılan yanlış olur."""
    field = re.search(r'<input[^>]*id="of_ratio"[^>]*>', advanced)
    pair = re.search(r'data-default-pair="([a-z0-9]+)\+([a-z0-9]+)"',
                     field.group(0))

    def first_option(select_id):
        block = re.search(r'<select id="%s".*?</select>' % select_id,
                          advanced, re.S)
        assert block, '%s select bulunamadı' % select_id
        options = re.findall(r'<option value="([^"]+)"', block.group(0))
        selected = re.findall(r'<option value="([^"]+)"[^>]*\bselected\b',
                              block.group(0))
        return selected[0] if selected else options[0]

    assert first_option('oxidizer_type') == pair.group(1)
    assert first_option('fuel_type') == pair.group(2)


OF_NOTICE_MARKERS = ('// >>> HYBRID_OF_DEFAULT_NOTICE_START',
                     '// <<< HYBRID_OF_DEFAULT_NOTICE_END')


def _of_notice_script(advanced, cases):
    block = _block(advanced, *OF_NOTICE_MARKERS)
    return """
'use strict';
const CASES = %s;
let formValues = {};
const notice = { textContent: '', style: {} };
const field = { attrs: { 'data-default-pair': 'n2o+htpb' },
                getAttribute: k => field.attrs[k] || null,
                addEventListener: () => {} };
const document = {
    getElementById: id => {
        if (id === 'of_default_notice') return notice;
        if (id === 'of_ratio') return field;
        if (id in formValues) return { value: formValues[id], addEventListener: () => {} };
        return null;
    }
};
function i18nText(key, fallback) { return fallback; }
function i18nFmt(key, params, fallback) {
    return String(fallback).replace(/\\{(\\w+)\\}/g, (w, k) => (k in params ? params[k] : w));
}
%s
const out = [];
CASES.forEach(c => {
    formValues = { fuel_type: c.fuel, oxidizer_type: c.oxidizer };
    ofRatioTouched = !!c.touched;
    notice.textContent = '';
    notice.style.display = '';
    updateOFDefaultNotice();
    out.push({ text: notice.textContent, display: notice.style.display });
});
console.log(JSON.stringify(out));
""" % (json.dumps(cases), block)


def test_koken_notu_gercek_duruma_gore_gorunur(advanced):
    """Davranış testi: not yalnız (a) alan dokunulmamışken görünür ve
    (b) seçili çift varsayılanın çifti değilse BAŞKA metin verir."""
    rows = _run_node(_of_notice_script(advanced, [
        {'fuel': 'htpb', 'oxidizer': 'n2o', 'touched': False},   # varsayılan çift
        {'fuel': 'paraffin', 'oxidizer': 'n2o', 'touched': False},  # başka yakıt
        {'fuel': 'htpb', 'oxidizer': 'lox', 'touched': False},   # başka oksitleyici
        {'fuel': 'htpb', 'oxidizer': 'lox', 'touched': True},    # kullanıcı girdi
    ]))
    assert rows[0]['display'] == 'block' and rows[0]['text']
    assert rows[1]['display'] == 'block'
    assert rows[2]['display'] == 'block'
    assert rows[1]['text'] != rows[0]['text'], \
        'başka çift seçilince not değişmiyor'
    assert 'PARAFFIN' in rows[1]['text'], 'not seçili çifti söylemiyor'
    assert 'LOX' in rows[2]['text']
    assert rows[3]['display'] == 'none' and rows[3]['text'] == '', \
        'kullanıcı değeri girdikten sonra köken notu kalkmalı'


def test_koken_notu_uydurma_sayi_basmaz(advanced):
    """Not yalnız GERÇEK duruma bakar; "optimumdan %x uzak" gibi hesaplanmamış
    bir sayı basmak yasak (sahte veri kuralı)."""
    block = advanced[advanced.index('function updateOFDefaultNotice'):]
    block = block[:block.index('function bindOFDefaultNotice')]
    assert 'toFixed' not in block, 'köken notu sayı basıyor'
    assert re.search(r'\b\d+\.\d+\b', block) is None, \
        'köken notunda gömülü sayı var'


# ---------------------------------------------------------------------------
# 3. ÖLÜ ALANLARIN ROZETLENMESİ
# ---------------------------------------------------------------------------
HYBRID_MARKERS = ('// >>> HYBRID_UNWIRED_MARKERS_START',
                  '// <<< HYBRID_UNWIRED_MARKERS_END')


def _hybrid_unwired_ids(advanced):
    block = _block(advanced, *HYBRID_MARKERS)
    body = re.search(r'HYBRID_UNWIRED_INPUTS\s*=\s*\{(.*?)\n        \};',
                     block, re.S)
    assert body, 'HYBRID_UNWIRED_INPUTS sözlüğü bulunamadı'
    return dict(re.findall(r"^\s*(\w+):\s*'(\w+)'", body.group(1), re.M))


def test_isaretlenen_liste_deponun_beyaniyla_ayni(advanced):
    """Şablon ile kod-gerçeği tek listede buluşur: biri değişip diğeri
    kalırsa kullanıcı yanlış bilgilendirilir."""
    from tests.test_field_wiring_layer_a import DECLARED_UNMODELLED

    assert set(_hybrid_unwired_ids(advanced)) == set(DECLARED_UNMODELLED['hybrid'])


def test_rozet_kategorileri_taninir(advanced):
    assert set(_hybrid_unwired_ids(advanced).values()) <= {'derived', 'no_model'}


def test_isaretleme_hem_acilista_hem_dinamik_alanlarda_kosar(advanced):
    """Pintle alanları updateInjectorParams tarafından SONRADAN basılıyor;
    yalnız açılışta işaretlemek onları rozetsiz bırakır."""
    assert 'markUnwiredInputs(paramsDiv)' in advanced
    assert 'markUnwiredInputs(document)' in advanced


def test_olu_alanlar_silinmedi(advanced):
    """Enjektör modülleri birleştirilince bağlanacaklar; şimdilik dururlar."""
    for field_id in _hybrid_unwired_ids(advanced):
        assert 'id="%s"' % field_id in advanced, \
            '%s alanı şablondan kaldırılmış' % field_id


def test_isaretleme_gercekten_rozet_basiyor(advanced):
    """Davranış testi: blok node'da koşturulur."""
    block = _block(advanced, *HYBRID_MARKERS)
    ids = sorted(_hybrid_unwired_ids(advanced))
    script = """
'use strict';
%s
const FIELDS = %s;
function node(tag) {
    const n = {
        tagName: tag, attrs: {}, classes: new Set(), children: [], parent: null,
        textContent: '',
        classList: { add: c => n.classes.add(c), contains: c => n.classes.has(c) },
        setAttribute: (k, v) => { n.attrs[k] = String(v); },
        getAttribute: k => (k in n.attrs ? n.attrs[k] : null),
        appendChild: c => { c.parent = n; n.children.push(c); return c; },
        closest: sel => {
            let cur = n;
            const cls = sel.replace('.', '');
            while (cur) { if (cur.classes.has(cls)) return cur; cur = cur.parent; }
            return null;
        },
        querySelector: sel => {
            const cls = sel.replace('.', '');
            const out = [];
            (function walk(x) { x.children.forEach(c => { out.push(c); walk(c); }); })(n);
            return out.find(c => c.classes.has(cls)) || null;
        }
    };
    Object.defineProperty(n, 'className', {
        get: () => Array.from(n.classes).join(' '),
        set: v => { n.classes = new Set(String(v).split(/\\s+/).filter(Boolean)); }
    });
    return n;
}
const byId = {};
const root = node('div');
FIELDS.forEach(id => {
    const group = node('div');
    group.classes.add('form-group');
    const input = node('input');
    input.attrs.id = id;
    group.appendChild(input);
    root.appendChild(group);
    byId[id] = input;
});
root.querySelectorAll = undefined;
const document = {
    getElementById: id => byId[id] || null,
    createElement: tag => node(tag)
};
root.querySelector = sel => {
    const id = sel.replace('#', '');
    return byId[id] || null;
};
function i18nText(key, fallback) { return fallback; }
function i18nFmt(key, params, fallback) {
    return String(fallback).replace(/\\{(\\w+)\\}/g, (w, k) => (k in params ? params[k] : w));
}
%s
markUnwiredInputs(root);
markUnwiredInputs(root);   // iki kez -> rozet ikilenmemeli
const out = {};
FIELDS.forEach(id => {
    const group = byId[id].parent;
    const notes = group.children.filter(c => c.classes.has('not-wired-note'));
    out[id] = {
        marked: group.classes.has('not-wired'),
        count: notes.length,
        text: notes.length ? notes[0].textContent : '',
        category: notes.length ? notes[0].attrs['data-unwired-category'] : '',
        title: byId[id].attrs.title || ''
    };
});
console.log(JSON.stringify(out));
""" % ('', json.dumps(ids), block)
    result = _run_node(script)
    categories = _hybrid_unwired_ids(advanced)
    for field_id in ids:
        row = result[field_id]
        assert row['marked'], '%s rozetlenmedi' % field_id
        assert row['count'] == 1, '%s rozeti ikilendi' % field_id
        assert row['text'], '%s rozeti boş metin' % field_id
        assert row['title'] == row['text'], '%s ipucu metni eksik' % field_id
        assert row['category'] == categories[field_id]
    derived = [i for i in ids if categories[i] == 'derived']
    no_model = [i for i in ids if categories[i] == 'no_model']
    if derived and no_model:
        assert result[derived[0]]['text'] != result[no_model[0]]['text'], \
            'iki kategori aynı metni alıyor'


# ---------------------------------------------------------------------------
# 4. GRAIN ÖNİZLEMESİ FORM ALANLARINDAN ÜRETİLİR
# ---------------------------------------------------------------------------
PREVIEW_MARKERS = ('// >>> SOLID_GRAIN_PREVIEW_START',
                   '// <<< SOLID_GRAIN_PREVIEW_END')

# Kusurun tam kendisi: 5 uçlu sabit yıldız path'i.
ESKI_SABIT_YILDIZ = 'M90,30 l15,45 h40'


def test_sabit_yildiz_pathi_kaldirildi(solid):
    assert ESKI_SABIT_YILDIZ not in solid, \
        'yıldız önizlemesi yine elde yazılmış sabit path'


def test_onizleme_geometri_alanlarina_bagli(solid):
    block = _block(solid, *PREVIEW_MARKERS)
    for field_id in ('outer_diameter', 'core_diameter', 'star_points',
                     'star_radius', 'fin_count', 'slot_count'):
        assert "'%s'" % field_id in block, \
            '%s önizlemede okunmuyor' % field_id


def test_geometri_alanlari_onizlemeyi_yeniler(solid):
    """Alan değişince yeniden çizilmezse ekran kullanıcının girdiğinden
    BAŞKA bir geometriyi gösterir."""
    listeners = re.search(
        r"\['outer_diameter', 'core_diameter',(.*?)\]\.forEach", solid, re.S)
    assert listeners, 'geometri alanları için dinleyici bağlanmamış'
    for field_id in ('star_points', 'star_radius', 'fin_count', 'fin_width',
                     'fin_length', 'slot_count', 'slot_width', 'slot_depth'):
        assert "'%s'" % field_id in listeners.group(1), \
            '%s değişince önizleme yenilenmiyor' % field_id


def _preview_script(solid, cases):
    block = _block(solid, *PREVIEW_MARKERS)
    return """
'use strict';
const CASES = %s;
function T(key, fallback) { return fallback; }
function TF(key, params, fallback) {
    return String(fallback).replace(/\\{(\\w+)\\}/g, (w, k) => (k in params ? params[k] : w));
}
let FIELDS = {};
const preview = { innerHTML: '' };
const configs = {
    star_config: { style: {} },
    finocyl_config: { style: {} },
    slotted_config: { style: {} }
};
const document = {
    getElementById: id => {
        if (id === 'grain_preview') return preview;
        if (id in configs) return configs[id];
        if (id in FIELDS) return { value: FIELDS[id] };
        return null;
    }
};
%s
const out = [];
CASES.forEach(c => {
    FIELDS = c;
    preview.innerHTML = '';
    updateGrainPreview();
    out.push(preview.innerHTML);
});
console.log(JSON.stringify(out));
""" % (json.dumps(cases), block)


BASE_GRAIN = {'outer_diameter': '100', 'core_diameter': '30',
              'grain_length': '500', 'star_radius': '15', 'star_fillet': '2',
              'fin_count': '4', 'fin_width': '8', 'fin_length': '20',
              'slot_count': '6', 'slot_width': '4', 'slot_depth': '25'}


def _case(**kw):
    case = dict(BASE_GRAIN)
    case.update({k: str(v) for k, v in kw.items()})
    return case


def test_yildiz_onizlemesi_uc_sayisini_izler(solid):
    cases = [_case(grain_type='star', star_points=n) for n in (3, 5, 6, 8, 12)]
    svgs = _run_node(_preview_script(solid, cases))
    for n, svg in zip((3, 5, 6, 8, 12), svgs):
        path = re.search(r'<path d="M([^"]+)"', svg)
        assert path, '%d uçlu yıldız için path yok' % n
        # 2N köşe: her uç için bir tepe + bir vadi.
        assert len(path.group(1).split(' L')) == 2 * n, \
            '%d uç istendi, %d köşe çizildi' % (n, len(path.group(1).split(' L')))
    assert len(set(svgs)) == len(svgs), 'farklı uç sayıları aynı şekli veriyor'


def test_yildiz_uc_yaricapi_sekli_degistirir(solid):
    svgs = _run_node(_preview_script(solid, [
        _case(grain_type='star', star_points=6, star_radius=8),
        _case(grain_type='star', star_points=6, star_radius=20),
    ]))
    assert svgs[0] != svgs[1]


def test_yildiz_derinligi_cozucudeki_gibi_kirpilir_ve_beyan_edilir(solid):
    """Çözücü derinliği 0,8·web ile kırpıyor (_star_params). Önizleme
    HESAPLANACAK şekli göstermeli ve kırpmayı söylemeli."""
    # web = (100-30)/2 = 35 mm -> üst sınır 28 mm.
    svg = _run_node(_preview_script(solid, [
        _case(grain_type='star', star_points=6, star_radius=50)]))[0]
    assert 'clipped' in svg.lower(), 'kırpma kullanıcıya bildirilmiyor'
    kirpilmis = _run_node(_preview_script(solid, [
        _case(grain_type='star', star_points=6, star_radius=28)]))[0]
    yol_a = re.search(r'<path d="([^"]+)"', svg).group(1)
    yol_b = re.search(r'<path d="([^"]+)"', kirpilmis).group(1)
    assert yol_a == yol_b, 'kırpılmış şekil çözücünün kullanacağı şekil değil'


def test_bates_port_capi_form_alanindan(solid):
    svgs = _run_node(_preview_script(solid, [
        _case(grain_type='bates', core_diameter=20),
        _case(grain_type='bates', core_diameter=60),
    ]))
    yaricaplar = [float(re.findall(r'<circle[^>]*r="([\d.]+)"', s)[1])
                  for s in svgs]
    # Dış yarıçap 80 px = D_dis/2; port yarıçapı oranla ölçeklenmeli.
    assert yaricaplar[0] == pytest.approx(80 * 20 / 100, abs=0.01)
    assert yaricaplar[1] == pytest.approx(80 * 60 / 100, abs=0.01)


def test_finocyl_ve_slotted_sayilari_izler(solid):
    svg4 = _run_node(_preview_script(solid, [
        _case(grain_type='finocyl', fin_count=4)]))[0]
    svg7 = _run_node(_preview_script(solid, [
        _case(grain_type='finocyl', fin_count=7)]))[0]
    assert svg4.count('<path') == 4
    assert svg7.count('<path') == 7
    svg9 = _run_node(_preview_script(solid, [
        _case(grain_type='slotted', slot_count=9)]))[0]
    assert svg9.count('<path') == 9


def test_wagon_wheel_delikleri_capa_bagli(solid):
    svgs = _run_node(_preview_script(solid, [
        _case(grain_type='wagon_wheel', core_diameter=30),
        _case(grain_type='wagon_wheel', core_diameter=50),
    ]))
    for svg in svgs:
        assert svg.count('<circle') == 8      # dış kabuk + 7 delik
    r30 = float(re.findall(r'<circle[^>]*r="([\d.]+)"', svgs[0])[1])
    r50 = float(re.findall(r'<circle[^>]*r="([\d.]+)"', svgs[1])[1])
    # r_delik = D_core/4 (çözücü: _wagon_port_polygon)
    assert r30 == pytest.approx(80 * (30 / 4) / 50, abs=0.01)
    assert r50 == pytest.approx(80 * (50 / 4) / 50, abs=0.01)


def test_okunamayan_geometride_yanlis_sekil_cizilmez(solid):
    cases = [
        _case(grain_type='star', outer_diameter=''),          # dış çap yok
        _case(grain_type='star', core_diameter=120),          # port dışı deler
        _case(grain_type='star', star_points=2),              # yıldız olamaz
        _case(grain_type='slotted', slot_depth=200),          # yuva webi aşıyor
    ]
    for svg in _run_node(_preview_script(solid, cases)):
        assert 'Preview unavailable' in svg
        assert '<path' not in svg, 'geçersiz girdide yine de şekil çizilmiş'


# ---------------------------------------------------------------------------
# 5. SIVI: SEKME ADI İÇERİĞİYLE UYUŞSUN
# ---------------------------------------------------------------------------
def test_sivi_sekmesi_zaman_vaat_etmiyor(liquid):
    block = re.search(
        r'<div class="analysis-subtabs">(.*?)</div>', liquid, re.S)
    assert block, 'alt sekme çubuğu bulunamadı'
    button = re.search(r"showSubTab\('thrust_time'\)[^>]*>([^<]+)<",
                       block.group(1))
    assert button, "thrust_time sekmesi bulunamadı"
    label = button.group(1).strip()
    assert 'Time' not in label, \
        'sekme adı zaman vaat ediyor ama içerikte zaman ekseni yok: %r' % label


def test_sivi_sekmesinin_icerigi_hala_zamansiz(liquid):
    """Ad değişikliği ancak içerik gerçekten zamansızsa doğrudur. İçeriğe
    zaman-çözümlü bir grafik eklenirse bu test kırılır ve ad yeniden
    gözden geçirilir."""
    content = re.search(
        r'<div id="thrust_time_content".*?>(.*?)\n                    </div>',
        liquid, re.S)
    assert content, 'thrust_time içeriği bulunamadı'
    assert 'plot' not in content.group(1).lower()
    assert 'chart' not in content.group(1).lower()


def test_sekme_kimlikleri_korundu(liquid):
    """Ad değişti, KİMLİK değişmedi: showSubTab ve içerik div'i eşleşmeli."""
    assert "showSubTab('thrust_time')" in liquid
    assert 'id="thrust_time_content"' in liquid
