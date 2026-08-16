"""Analiz Merkezi (Analysis Center) ÇERÇEVE sözleşmesi — dalga B, 2026-08-16.

Tasarım belgesi: ``docs/mimari/analiz-merkezi-tasarimi.md``.
Ölçülen katman: ``hrma/static/js/analysis_center.js`` (üç sütun + koşum
geçmişi şeridi) ve onun üç şablona bağlanışı. Mevcut analiz güvertesi
(``analysis_dock.js``) YERİNDE KALIR; buradaki bekçiler onun bozulmadığını
da ayrıca ölçer (tasarım §4: paneller tek tek taşınacak, taşıma
doğrulanmadan eski yeri kaldırılmaz).

Kapsam
------
  1. ŞABLON SÖZLEŞMESİ (test_client, port bağlanmaz): üç motor sayfasında
     ``analysis_center.js`` yüklü, kiracı script'i ONDAN SONRA geliyor,
     ``#analysis-center-anchor`` çapası var ve ``AnalysisCenter.init``
     o çapaya + sayfanın motor tipine bağlı. Güverte sözleşmesi (dock
     script + çapa + init) bozulmadı.
  2. KAYIT SÖZLEŞMESİ: dosya başındaki blok yorum S4 kiracısının yazacağı
     alanları ADIYLA belgeliyor ve register() bu alanları GERÇEKTEN
     okuyor (belge ile kod ayrışamaz).
  3. GRİ SATIR BEYANI (tasarım kural 1): uygulanamayan/henüz taşınmamış
     satır GİZLENMİYOR — gri duruyor ve nedeni yazılı. Neden metinleri
     sözlük ANAHTARINA bağlı (``ac.reason.*``); anahtar kaybolursa bekçi
     düşer.
  4. SAHTE İLERLEME YASAĞI (tasarım kural 3 + ürün felsefesi): kaynakta
     zamanlayıcı/rastgele sayı yok, yüzde çubuğu yok; koşum sırasında
     ekranda YALNIZ gerçek durum beyanı var (rakam/yüzde içermez).
  5. KOŞUM KARTI + GEÇMİŞ: öneri → alan, alan → POST gövdesi, elle
     değiştirilen alanın korunması, zorunlu alan boşken isteğin HİÇ
     gönderilmemesi, geçmiş kaydının saat/bileşen/analiz/hüküm rozeti
     taşıması, eski kaydın "geçmişten" beyanıyla geri gösterilmesi.

Ölçüm yöntemi
-------------
JS grep ile denetlenmez: ``node`` içinde GERÇEK dosya küçük bir DOM
taklidiyle BÜTÜN olarak koşturulur (kalıp: tests/test_fea_panel.py).
Taklit DOM innerHTML'i ayrıştırmaz; bu yüzden form alanları tarayıcıdaki
gibi HTML varsayılanıyla dolu BAŞLAMAZ — "boş zorunlu alan" senaryosu bu
sayede doğal olarak kurulur, ayrıca zorlamaya gerek kalmaz.

Koşum hedeflidir (süit disiplini):
    python3 -m pytest tests/test_analysis_center_contract.py -q
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'

CENTER_JS = STATIC_JS / 'analysis_center.js'
CFD_PANEL_JS = STATIC_JS / 'panels' / 'cfd_panel.js'

CENTER_SRC = '/static/js/analysis_center.js'
CFD_SRC = '/static/js/panels/cfd_panel.js'
DOCK_SRC = '/static/js/analysis_dock.js'

CENTER_ANCHOR_ID = 'analysis-center-anchor'
DOCK_ANCHOR_ID = 'analysis-dock-anchor'

#: sayfa -> Merkez'e verilmesi gereken motor tipi. (Ad bilerek
#: MOTOR_PAGES DEĞİL: o ad depoda "sayfa listesi" anlamında kullanılıyor,
#: burası eşleme; aynı adı farklı biçimde kullanmak tutarlılık bekçisini
#: yanıltır.)
PAGE_MOTOR_TYPE = {'/hybrid': 'hybrid', '/solid': 'solid', '/liquid': 'liquid'}

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: §2 matrisinin v1 satırları (docs/mimari/analiz-merkezi-tasarimi.md §2).
#: Tabloda olan her satır ekranda GÖRÜNMELİ — kiracısı olmasa bile.
MATRIX_ROWS = [
    ('chamber_nozzle_wall', 'structural'),
    ('chamber_nozzle_wall', 'thermal'),
    ('grain_section', 'planar_grain'),
    ('nozzle_flow', 'cfd'),
    ('feed_structure', 'module_cards'),
    ('chamber_acoustics', 'acoustic_modes'),
]

#: Çerçevenin kendi ürettiği gri-satır nedenlerinin sözlük anahtarları.
REASON_KEYS = ['ac.reason.notMoved', 'ac.reason.motorType', 'ac.reason.noResults',
               'ac.reason.unnamed', 'ac.reason.applicabilityError']


def read(path):
    return path.read_text(encoding='utf-8')


def strip_js_comments(text):
    """JS yorumlarını aynı uzunlukta boşlukla değiştirir (ofsetler korunur).

    tests/test_i18n_common.py'deki aynı adlı yardımcının kopyası; oradaki
    modül kapsamı (sözlük ayrıştırma) bu hedefli koşuma girmesin diye
    içe aktarılmıyor. Yorum metni denetimi kirletmemeli: dosyanın BAŞLIK
    yorumu zaten "setInterval ... çağrılmaz" cümlesini içeriyor.
    """
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


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def center_code():
    """analysis_center.js — yorumları silinmiş kod gövdesi."""
    return strip_js_comments(read(CENTER_JS))


# ---------------------------------------------------------------------------
# 1. Şablon sözleşmesi
# ---------------------------------------------------------------------------

class TestTemplateContract:
    @pytest.mark.parametrize('page', sorted(PAGE_MOTOR_TYPE))
    def test_center_script_present(self, client, page):
        html = client.get(page).get_data(as_text=True)
        assert CENTER_SRC in html, f'{page}: {CENTER_SRC} yüklenmiyor'

    @pytest.mark.parametrize('page', sorted(PAGE_MOTOR_TYPE))
    def test_tenant_script_loads_after_core(self, client, page):
        """Kiracı register çağırırken window.AnalysisCenter tanımlı olmalı."""
        html = client.get(page).get_data(as_text=True)
        core = html.find(CENTER_SRC)
        tenant = html.find(CFD_SRC)
        assert core != -1 and tenant != -1, f'{page}: Merkez/kiracı script eksik'
        assert tenant > core, (
            f'{page}: {CFD_SRC} çekirdekten ÖNCE yükleniyor — kiracı '
            'kaydolamaz (window.AnalysisCenter tanımsız)')

    @pytest.mark.parametrize('page', sorted(PAGE_MOTOR_TYPE))
    def test_center_anchor_present_and_distinct(self, client, page):
        html = client.get(page).get_data(as_text=True)
        assert f'id="{CENTER_ANCHOR_ID}"' in html, (
            f'{page}: #{CENTER_ANCHOR_ID} yok — Merkez .container\'a düşer ve '
            'hesap yapılmadan görünür olur')
        assert f'id="{DOCK_ANCHOR_ID}"' in html, (
            f'{page}: güverte çapası kaybolmuş (Merkez onun yerine geçmez)')

    @pytest.mark.parametrize('page,motor', sorted(PAGE_MOTOR_TYPE.items()))
    def test_center_init_wired(self, client, page, motor):
        html = client.get(page).get_data(as_text=True)
        assert 'AnalysisCenter.init' in html, f'{page}: AnalysisCenter.init çağrısı yok'
        idx = html.find('AnalysisCenter.init')
        block = html[idx:idx + 400]
        assert f"anchorId: '{CENTER_ANCHOR_ID}'" in block, (
            f'{page}: AnalysisCenter.init kendi çapasına bağlı değil')
        assert f"motorType: '{motor}'" in block, (
            f'{page}: Merkez motor tipi {motor!r} olmalı (bileşen×analiz '
            'uygulanabilirliği buradan ölçülüyor)')
        assert 'resultsProvider' in block, (
            f'{page}: Merkez sonuç sağlayıcısız kurulmuş — her satır '
            '"sonuç yok" der')

    @pytest.mark.parametrize('page', sorted(PAGE_MOTOR_TYPE))
    def test_existing_dock_untouched(self, client, page):
        """Merkez eklenirken mevcut güverte sözleşmesi bozulmadı."""
        html = client.get(page).get_data(as_text=True)
        assert DOCK_SRC in html
        assert 'AnalysisDock.init' in html
        assert f"anchorId: '{DOCK_ANCHOR_ID}'" in html

    def test_tenant_placeholder_file_is_served(self, client):
        """Script etiketi var ama dosya yoksa her sayfa yüklemesi 404 üretir."""
        resp = client.get(CFD_SRC)
        assert resp.status_code == 200, (
            f'{CFD_SRC} {resp.status_code} döndü — konsol hatası üretir')

    def test_center_file_is_served(self, client):
        assert client.get(CENTER_SRC).status_code == 200


# ---------------------------------------------------------------------------
# 2. Kayıt sözleşmesi: belge ile kod ayrışamaz
# ---------------------------------------------------------------------------

#: S4 kiracısının yazacağı sözleşme alanları.
CONTRACT_FIELDS = ['componentId', 'analysisId', 'title', 'endpoint', 'motorTypes',
                   'applicability', 'fields', 'fromResults', 'render', 'long',
                   'verdict', 'body']


class TestRegisterContract:
    @needs_node
    @pytest.mark.parametrize('path', [CENTER_JS, CFD_PANEL_JS], ids=lambda p: p.name)
    def test_js_syntax_ok(self, path):
        proc = subprocess.run([NODE, '--check', str(path)],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, f'{path.name} sözdizimi hatası:\n{proc.stderr}'

    @pytest.mark.parametrize('field', CONTRACT_FIELDS)
    def test_contract_documented_in_header(self, field):
        """Dosya başı blok yorum sözleşmeyi ADIYLA belgelemeli."""
        head = read(CENTER_JS).split('*/', 1)[0]
        assert field in head, (
            f'{field} kayıt sözleşmesi başlık yorumunda belgelenmemiş — '
            'S4 kiracısı neye yazacağını dosyadan okuyamaz')

    @pytest.mark.parametrize('field', CONTRACT_FIELDS)
    def test_contract_field_used_by_code(self, field, center_code):
        """Belgelenen alan kodda GERÇEKTEN okunmalı (ölü sözleşme yasağı)."""
        assert field in center_code, (
            f'{field} yalnız yorumda var, kodda okunmuyor — sözleşme belgesi '
            'koddan ayrışmış')

    def test_register_validates_required_fields(self, center_code):
        assert re.search(r'function register\s*\(', center_code), \
            'register() yok — kayıt sözleşmesi kurulamaz'
        assert 'AnalysisCenter' in center_code and 'register: register' in center_code, \
            'window.AnalysisCenter.register dışa verilmemiş'

    def test_tenant_registers_itself(self):
        """cfd_panel.js ARTIK kiracıdır (S4, 16 Ağu 2026): kaydını yapar ve
        sözleşme alanlarını verir. Bu bekçi, yer tutucu döneminin
        test_placeholder_has_no_tenant_logic bekçisinin HALEFİDİR (nöbetçi
        sözleşmesi: geçici durumu kilitleyen bekçi, durum değişince halefine
        çevrilir — silinmez). Derinlemesine ölçüm tests/test_cfd_panel.py'de."""
        src = strip_js_comments(read(CFD_PANEL_JS))
        assert 'AnalysisCenter.register' in src, (
            "cfd_panel.js kendini Merkez'e kaydetmiyor — satır gri kalır")
        assert "componentId: 'nozzle_flow'" in src and "analysisId: 'cfd'" in src, (
            'kiracı §2 matrisindeki satıra bağlanmıyor')
        for alan in ('applicability', 'fields', 'fromResults', 'body',
                     'render', 'verdict'):
            assert alan + ':' in src, f'kiracı {alan} sözleşme alanını vermiyor'

    def test_matrix_rows_are_the_design_table(self, center_code):
        """§2 tablosunun her satırı matriste ADIYLA olmalı."""
        for component, analysis in MATRIX_ROWS:
            assert f"'{component}'" in center_code, f'{component} bileşeni matriste yok'
            assert f"'{analysis}'" in center_code, f'{analysis} analizi matriste yok'


# ---------------------------------------------------------------------------
# 3. Sahte ilerleme yasağı — statik
# ---------------------------------------------------------------------------

#: Zamanlayıcı/rastgelelik: sahte ilerlemenin bilinen üretim yolları.
FORBIDDEN_CALLS = ['setInterval', 'setTimeout', 'requestAnimationFrame', 'Math.random']


class TestNoFakeProgress:
    @pytest.mark.parametrize('call', FORBIDDEN_CALLS)
    def test_no_timer_or_random_in_code(self, call, center_code):
        assert call not in center_code, (
            f'{call} kullanılmış — sahte ilerleme/animasyon üretiminin bilinen '
            'yolu. Gerçek iterasyon akışı (SSE/poll) gelene kadar ilerleme '
            'gösterilmez (tasarım kural 3)')

    def test_no_growing_bar_style(self, center_code):
        """Genişliği kodla büyütülen çubuk (yüzde çubuğu) yok."""
        assert not re.search(r'style\.width\s*=', center_code), \
            'style.width ataması var — dolan çubuk şüphesi'
        assert not re.search(r'width:\s*\$\{', center_code), \
            'şablon dizesiyle hesaplanan genişlik var — dolan çubuk şüphesi'

    def test_running_declaration_is_key_bound(self, center_code):
        for key in ('ac.run.running', 'ac.run.runningLong'):
            assert f"'{key}'" in center_code, (
                f'{key} yok — koşum beyanı sözlüğe bağlı değil')

    def test_elapsed_time_is_measured_not_invented(self, center_code):
        """Bitişte gösterilen süre GERÇEK ölçümdür (Date.now farkı)."""
        assert 'Date.now()' in center_code
        assert re.search(r'Date\.now\(\)\s*-\s*t0', center_code), \
            'geçen süre ölçülmüyor — "tamamlandı" süresi uydurma olurdu'


# ---------------------------------------------------------------------------
# node koşum ortamı — GERÇEK dosya, taklit DOM
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const centerPath = process.argv[3];

const nodes = {};
function makeNode(id) {
    return {
        id: id, innerHTML: '', textContent: '', style: {}, attrs: {},
        value: '', disabled: false, options: [],
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild(c) { (this.children = this.children || []).push(c); return c; },
        addEventListener(type, fn) { (this.handlers = this.handlers || {})[type] = fn; },
    };
}
global.document = {
    body: makeNode('body'),
    getElementById(id) {
        if (!(id in nodes)) nodes[id] = makeNode(id);
        return nodes[id];
    },
    createElement() { return makeNode(null); },
    querySelector() { return null; },
    addEventListener() {},
};
global.window = global;

const fetchCalls = [];
let releaseFetch = null;
global.fetch = function (url, opts) {
    fetchCalls.push({ url: url,
                      body: (opts && opts.body) ? JSON.parse(opts.body) : null });
    const resp = {
        ok: payload.httpOk !== false,
        status: (payload.httpOk === false) ? 500 : 200,
        text: function () {
            return Promise.resolve(JSON.stringify(
                payload.response || { status: 'success', value: 1 }));
        },
    };
    // Sözü BİLEREK geciktir: koşum sırasındaki ekran durumu ölçülebilsin.
    return new Promise(function (resolve) {
        releaseFetch = function () { resolve(resp); };
    });
};

require(centerPath);
const AC = window.AnalysisCenter;
const tenantRenders = [];

if (payload.registerTenant) {
    AC.register({
        componentId: payload.tenantComponent || 'nozzle_flow',
        analysisId: payload.tenantAnalysis || 'cfd',
        title: 'CFD (test tenant)',
        endpoint: '/api/cfd/nozzle',
        motorTypes: payload.tenantMotorTypes || ['hybrid', 'solid', 'liquid'],
        long: true,
        applicability: function (r) {
            if (payload.applicable === false) {
                return { ok: false,
                         reason: { key: 'panel.cfd.needsContour',
                                   fallback: 'This result carries no nozzle contour.' } };
            }
            if (payload.applicableUnnamed) return { ok: false };
            return { ok: true };
        },
        fields: [['grid_nx', 'Axial cells', 120, 1, 'panel.cfd.gridNx'],
                 ['grid_ny', 'Radial cells', 24, 1, 'panel.cfd.gridNy']],
        fromResults: (payload.suggest === false) ? null : function (r) {
            return { grid_nx: 128, grid_ny: 32 };
        },
        render: function (data, root) {
            tenantRenders.push(data);
            root.innerHTML = '<div id="tenant_out">' + JSON.stringify(data) + '</div>';
        },
        verdict: (payload.verdict === false) ? null : function (data) {
            return { kind: 'ok', key: 'panel.cfd.converged', fallback: 'CONVERGED' };
        },
    });
}

AC.init({
    anchorId: 'analysis-center-anchor',
    motorType: payload.motorType || 'hybrid',
    resultsProvider: function () { return payload.results || null; },
});

function dumpModel() {
    return AC._model().map(function (c) {
        return { id: c.id, rows: c.rows.map(function (r) {
            return { componentId: r.componentId, analysisId: r.analysisId,
                     state: r.state, reason: AC._reasonText(r.reason),
                     hasSpec: !!r.spec, endpoint: r.endpoint, title: r.title };
        }) };
    });
}

(async function () {
    const out = { statusDuringRun: null, runs: [] };
    if (payload.select) AC.select(payload.select[0], payload.select[1]);

    if (payload.dirtyField) {
        const id = AC._fieldDomId(payload.select[0], payload.select[1],
                                  payload.dirtyField);
        const el = document.getElementById(id);
        el.value = payload.dirtyValue;
        el.setAttribute('data-dirty', '1');
        AC.refresh();
        out.dirtyFieldId = id;
        out.dirtyFieldValue = String(el.value);
    }

    const runCount = payload.runs || 0;
    for (let i = 0; i < runCount; i++) {
        const p = AC.run();
        if (i === 0 && nodes['ac_status']) {
            out.statusDuringRun = nodes['ac_status'].textContent;
            out.runButtonDisabled = !!(nodes['ac_run'] && nodes['ac_run'].disabled);
        }
        if (releaseFetch) { releaseFetch(); releaseFetch = null; }
        await p;
    }
    if (payload.showHistoryEntry) AC.showHistoryEntry(payload.showHistoryEntry);

    out.model = dumpModel();
    out.selection = AC.getSelection();
    out.fetchCalls = fetchCalls;
    out.tenantRenders = tenantRenders.length;
    out.history = AC.history().map(function (e) {
        return { id: e.id, rowKey: e.rowKey, ok: e.ok, seconds: e.seconds,
                 at: e.at, hasVerdict: !!e.verdict, errorText: e.errorText,
                 componentTitle: e.componentTitle, title: e.title };
    });
    out.nodes = {};
    Object.keys(nodes).forEach(function (id) {
        out.nodes[id] = { html: nodes[id].innerHTML, text: nodes[id].textContent,
                          value: String(nodes[id].value), attrs: nodes[id].attrs,
                          disabled: !!nodes[id].disabled };
    });
    process.stdout.write(JSON.stringify(out));
})();
"""


def run_center(tmp_path, **payload):
    """Merkez'i node'da koşturur; model + DOM görüntüsü + geçmiş döner."""
    script = tmp_path / 'kos_center.js'
    script.write_text(HARNESS, encoding='utf-8')
    data = tmp_path / 'girdi.json'
    data.write_text(json.dumps(payload), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(data), str(CENTER_JS)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, 'Merkez node altında çöktü:\n' + proc.stderr
    return json.loads(proc.stdout)


def rows_of(out):
    """{(bileşen, analiz): satır} — model düzleştirilmiş hâli."""
    flat = {}
    for comp in out['model']:
        for row in comp['rows']:
            flat[(row['componentId'], row['analysisId'])] = row
    return flat


SONUC = {'motor': {'chamber_pressure': 20.0, 'throat_diameter': 0.03}}


# ---------------------------------------------------------------------------
# 4. Gri satır beyanı (tasarım kural 1)
# ---------------------------------------------------------------------------

@needs_node
class TestGreyRowsAreDeclared:
    def test_all_matrix_rows_are_visible(self, tmp_path):
        """Kiracı hiç yokken bile §2'nin altı satırı da EKRANDA."""
        out = run_center(tmp_path, motorType='hybrid', results=SONUC)
        flat = rows_of(out)
        for key in MATRIX_ROWS:
            assert key in flat, f'{key} satırı modelde yok — satır gizlenmiş'
        tree = out['nodes']['ac_tree']['html']
        for component, analysis in MATRIX_ROWS:
            assert f'data-ac-row="{component}.{analysis}"' in tree, (
                f'{component}.{analysis} ağaçta çizilmemiş')

    def test_rows_without_tenant_are_absent_with_reason(self, tmp_path):
        out = run_center(tmp_path, motorType='hybrid', results=SONUC)
        flat = rows_of(out)
        row = flat[('nozzle_flow', 'cfd')]
        assert row['state'] == 'absent', 'kiracısız satır çalıştırılabilir görünüyor'
        assert row['reason'].strip(), 'gri satırın nedeni BOŞ — beyan yok'
        assert 'Center' in row['reason'] or 'Merkez' in row['reason'], (
            f'neden metni taşınmamışlığı adlandırmıyor: {row["reason"]!r}')
        tree = out['nodes']['ac_tree']['html']
        assert 'data-ac-reason="nozzle_flow.cfd"' in tree, (
            'neden ağaçta yazılmamış — kullanıcı niçin gri olduğunu göremez')

    @pytest.mark.parametrize('key', REASON_KEYS)
    def test_reason_texts_are_dictionary_keys(self, key, center_code):
        """Gri satır beyanı sözlük anahtarına bağlı (metin gömülü değil)."""
        assert f"'{key}'" in center_code, (
            f'{key} anahtarı kaybolmuş — beyan metni çeviriden geçmez')

    def test_motor_type_reason_names_the_motor(self, tmp_path):
        """Sıvı motorda katı tane satırı motor tipi nedeniyle gri."""
        out = run_center(tmp_path, motorType='liquid', results=SONUC)
        row = rows_of(out)[('grain_section', 'planar_grain')]
        assert row['state'] == 'blocked'
        assert 'liquid' in row['reason'], (
            f'motor tipi nedeni motoru adlandırmıyor: {row["reason"]!r}')

    def test_tenant_row_blocked_without_results(self, tmp_path):
        out = run_center(tmp_path, motorType='hybrid', results=None,
                         registerTenant=True)
        row = rows_of(out)[('nozzle_flow', 'cfd')]
        assert row['state'] == 'blocked'
        assert 'calculation' in row['reason'] or 'hesap' in row['reason'], (
            f'sonuç yokluğu adlandırılmamış: {row["reason"]!r}')

    def test_tenant_applicability_reason_is_shown_verbatim(self, tmp_path):
        """Kiracının "bu sonuç X alanını taşımıyor" cümlesi ekrana AYNEN çıkar."""
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, applicable=False)
        row = rows_of(out)[('nozzle_flow', 'cfd')]
        assert row['state'] == 'blocked'
        assert row['reason'] == 'This result carries no nozzle contour.'
        assert 'no nozzle contour' in out['nodes']['ac_tree']['html']

    def test_unnamed_rejection_is_flagged_not_swallowed(self, tmp_path):
        """Kiracı nedensiz "uygulanamaz" derse beyansızlık YAZILIR."""
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, applicableUnnamed=True)
        row = rows_of(out)[('nozzle_flow', 'cfd')]
        assert row['state'] == 'blocked'
        assert 'no reason' in row['reason'] or 'neden' in row['reason'], (
            f'beyansız ret sessizce yutulmuş: {row["reason"]!r}')

    def test_ready_row_when_tenant_and_results_exist(self, tmp_path):
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True)
        row = rows_of(out)[('nozzle_flow', 'cfd')]
        assert row['state'] == 'ready'
        assert row['endpoint'] == '/api/cfd/nozzle'
        assert not row['reason'], 'çalıştırılabilir satıra gerekçe yazılmış'


# ---------------------------------------------------------------------------
# 5. Koşum kartı, gerçek durum beyanı ve geçmiş şeridi
# ---------------------------------------------------------------------------

@needs_node
class TestRunCardAndHistory:
    def test_suggestions_fill_fields_and_payload_comes_from_form(self, tmp_path):
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, select=['nozzle_flow', 'cfd'], runs=1)
        assert len(out['fetchCalls']) == 1
        call = out['fetchCalls'][0]
        assert call['url'] == '/api/cfd/nozzle'
        # Gövde FORMDAN okunur: fromResults'ın yazdığı değerler geri gelmeli
        assert call['body'] == {'grid_nx': 128, 'grid_ny': 32}

    def test_user_edited_field_is_not_overwritten(self, tmp_path):
        """data-dirty alanı yeni sonuç tazelemesinde EZİLMEZ."""
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, select=['nozzle_flow', 'cfd'],
                         dirtyField='grid_nx', dirtyValue=200, runs=1)
        assert out['dirtyFieldValue'] == '200', (
            'kullanıcının yazdığı değer öneriyle ezilmiş')
        assert out['fetchCalls'][0]['body']['grid_nx'] == 200, (
            'POST gövdesi formdan değil öneriden kurulmuş — ekranda görünen '
            'değer ile gönderilen değer ayrışıyor')

    def test_missing_required_field_blocks_the_request(self, tmp_path):
        """Zorunlu alan boşken istek HİÇ gönderilmez, eksik ADIYLA yazılır."""
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, suggest=False,
                         select=['nozzle_flow', 'cfd'], runs=1)
        assert out['fetchCalls'] == [], 'boş zorunlu alanla istek gönderilmiş'
        status = out['nodes']['ac_status']['text']
        assert 'Axial cells' in status and 'Radial cells' in status, (
            f'eksik alanlar adıyla yazılmamış: {status!r}')
        assert out['history'] == [], 'gönderilmeyen istek geçmişe yazılmış'

    def test_running_status_is_a_real_declaration(self, tmp_path):
        """Koşarken ekranda yüzde/rakam YOK, yalnız durum beyanı var."""
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, select=['nozzle_flow', 'cfd'], runs=1)
        running = out['statusDuringRun']
        assert running, 'koşum sırasında hiçbir durum beyanı yok'
        assert 'RUNNING' in running.upper(), f'durum beyanı değil: {running!r}'
        assert '%' not in running, f'yüzde göstergesi basılmış: {running!r}'
        assert not re.search(r'\d', running), (
            f'koşum beyanında sayı var — sahte ilerleme şüphesi: {running!r}')
        assert out['runButtonDisabled'] is True, (
            'koşum sürerken düğme etkin kalmış (ikinci istek gönderilebilir)')

    def test_completion_reports_measured_seconds(self, tmp_path):
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, select=['nozzle_flow', 'cfd'], runs=1)
        assert len(out['history']) == 1
        entry = out['history'][0]
        assert isinstance(entry['seconds'], (int, float)) and entry['seconds'] >= 0
        assert 'Completed' in out['nodes']['ac_status']['text']

    def test_history_entry_carries_time_component_analysis_verdict(self, tmp_path):
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, select=['nozzle_flow', 'cfd'], runs=1)
        entry = out['history'][0]
        assert entry['rowKey'] == 'nozzle_flow.cfd'
        assert entry['hasVerdict'] is True
        strip = out['nodes']['ac_history']['html']
        assert re.search(r'\d\d:\d\d:\d\d', strip), 'geçmişte koşum saati yok'
        assert 'Nozzle internal flow' in strip, 'geçmişte bileşen adı yok'
        assert 'CFD' in strip, 'geçmişte analiz adı yok'
        assert 'CONVERGED' in strip, 'geçmişte hüküm rozeti yok'

    def test_viewer_draws_tenant_output(self, tmp_path):
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, select=['nozzle_flow', 'cfd'], runs=1,
                         response={'status': 'success', 'iterations': 4321})
        assert out['tenantRenders'] == 1, 'kiracının render() çağrısı yapılmamış'
        # Kiracıya verilen kap görüntüleyicinin İÇİNDEDİR (#ac_view_root);
        # taklit DOM innerHTML'i ayrıştırmadığı için kabın kendisi okunur.
        assert '4321' in out['nodes']['ac_view_root']['html'], (
            'kiracının çizdiği veri görüntüleyici kabında yok')

    def test_history_replay_shows_stored_result_with_declaration(self, tmp_path):
        """Eski kayda dönüldüğünde "geçmişten" olduğu YAZILIR."""
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, select=['nozzle_flow', 'cfd'],
                         runs=2, showHistoryEntry=1)
        assert len(out['history']) == 2
        view = out['nodes']['ac_view']['html']
        assert 'ac.history.stale' in view, (
            'eski koşum tazeymiş gibi gösteriliyor — beyan yok')
        assert out['tenantRenders'] >= 3, (
            'geçmişteki kayıt yeniden çizilmemiş (render sayısı: %s)'
            % out['tenantRenders'])

    def test_undeclared_verdict_is_named_not_invented(self, tmp_path):
        """Kiracı hüküm vermezse "beyan edilmedi" yazılır, "başarılı" DEĞİL."""
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, verdict=False,
                         select=['nozzle_flow', 'cfd'], runs=1)
        strip = out['nodes']['ac_history']['html']
        assert 'NO VERDICT DECLARED' in strip, (
            'beyansız koşuma hüküm rozeti uydurulmuş')
        assert 'ac.verdict.undeclared' in strip, 'rozet sözlük anahtarına bağlı değil'

    def test_failed_run_is_recorded_with_real_message(self, tmp_path):
        out = run_center(tmp_path, motorType='hybrid', results=SONUC,
                         registerTenant=True, select=['nozzle_flow', 'cfd'],
                         runs=1, httpOk=False,
                         response={'status': 'error', 'error': 'grid too coarse'})
        entry = out['history'][0]
        assert entry['ok'] is False
        assert entry['errorText'] == 'grid too coarse'
        assert 'grid too coarse' in out['nodes']['ac_view']['html'], (
            'hata görüntüleyicide görünmüyor — kullanıcı boş ekran görür')
        assert 'RUN FAILED' in out['nodes']['ac_history']['html']


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
