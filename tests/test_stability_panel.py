"""stability_panel.js bekçileri — Analiz Merkezi'nin F2c KARARLILIK kiracısı.

KAPATILAN KUSUR
---------------
``hrma/stability/`` çekirdeği ve üç motorun F2b bağlamaları depoda çalışır
hâldeydi ama Merkez'in "Kamara akustiği" satırının kiracısı yoktu: kullanıcı
ne mod haritasını, ne mod başına sönüm bütçesini, ne n-τ nötr eğrisini, ne de
chug kök yer eğrisini görebiliyordu. Bu panel iki satırı birden doldurur;
buradaki bekçiler panelin SÖZLEŞMESİNİ kilitler.

NE KİLİTLENİR
-------------
  1. MATRİS + KOD KANITI: ``chamber_acoustics × acoustic_modes`` satırına
     'liquid' eklendi (parti 27 F2b-2 göçü). Bu ekleme kod kanıtına
     BAĞLIDIR: sıvı çözücünün ``from hrma.analysis.acoustic_modes import``
     satırı kaybolursa buradaki bekçi de kırmızı yanar — matristeki 'liquid'
     çürük bir iddiaya dönüşemez. Yeni satır:
     ``chamber_acoustics × combustion_stability``
     (uç: /api/analysis/combustion-stability, üç motor tipi).
  2. KAYIT SÖZLEŞMESİ: iki kiracı da register() alanlarının tamamını verir;
     hiçbir alanın SONLU VARSAYILANI yoktur (öneri gelmeyen alan boş kalır).
  3. ÖNERİ KAYNAĞI ÖLÇÜLÜ: her önerilen sayı motorun GERÇEKTEN yayımladığı
     alandan gelir ve beklenen değer testte ELLE YAZILMAZ, motorun kendi
     sonucundan türetilir. Sıvı VE hibrit kendi chug_loop.inputs yankısından
     (hibrit chug bağlaması bu partide indi); kaynağı olmayan motor sonucu
     önerisiz kalır (sabit 0,2 yazan bir mutasyon burada kırmızıya düşer).
  4. HÜKÜM DİSİPLİNİ (F2a karar 1): chug hükmü DAİMA verdict_scope kapsam
     etiketiyle basılır; kapsamsız gelen hüküm ekrana hüküm olarak ÇIKMAZ
     (çıplak STABLE/UNSTABLE yasak). Sönüm/akustik yolda hüküm BEYAN
     EDİLMEZ (çerçeve "hüküm beyan edilmedi" der).
  5. SAHTE SAYI TARAMASI: panel gövdesinde sabit sayısal literalle beslenen
     çizim yoktur — izlerin x/y/z alanlarına dizi literali yazan bir
     mutasyon regex bekçisine takılır. Zamanlayıcı/rastgelelik de yok.
  6. ÇİZİM YANITTAN / ANLIK GÖRÜNTÜDEN: nötr eğri, kök yeri ve işletme
     noktası yanıttaki dizilerin KENDİSİDİR; mod haritası ile sönüm
     çubukları koşum ANINDA alınan motor-sonucu anlık görüntüsünden gelir
     ve YALNIZ yanıtın yankısı o görüntüyle ölçülebilir biçimde eşleşince
     çizilir (cfd duvar poliçizgisi disiplini). Eşleşmeyen/eksik veri GRİ +
     gerekçe (``data-stab-grey``).
  7. ŞABLON SÖZLEŞMESİ: stability_panel.js üç motor sayfasında da
     analysis_center.js'ten SONRA yüklenir. NOT: advanced.html include'unu
     A3 ekliyor — o parametre A3 inene kadar kırmızı kalabilir (bu dosyanın
     sahibi advanced.html'e dokunmaz).

ÖLÇÜM YÖNTEMİ
-------------
Motor sonuçları GERÇEK ``/calculate*`` koşularından gelir (tasarım noktaları
tests/test_cfd_panel.py ile TEK kaynak — yeni nokta uydurulmaz). UC yanıtları
(A2 paralel yazdığı için) DONDURULMUŞ UÇ SÖZLEŞMESİNİN biçiminde, sayıları
``hrma.stability`` çekirdeğinin GERÇEK çağrılarından üretilir — uydurma sayı
yok, yalnız zarf test kurgusudur. Uç depoya bağlandığında
``TestCanliUc`` kendiliğinden canlanır (bağlanana dek adıyla skip).

MUTASYON DÜŞÜNCESİ — bağlama geri alınırsa hangi test kırılır
--------------------------------------------------------------
  * Kapsam kapısı kaldırılıp çıplak hüküm basılırsa ->
    test_kapsamsiz_hukum_bastirilir (+ test_hukum_kapsam_etiketiyle).
  * MATRIX'ten 'liquid' düşerse ya da sıvının merkezî akustik import'u
    silinirse -> test_matrix_sivi_kod_kanitina_bagli.
  * İzlere sayısal dizi literali yazılırsa ->
    test_izlerde_sayisal_literal_yok (+ ilgili dizi-eşitliği bekçisi).
  * Chug önerilerine sabit varsayılan konursa ->
    test_kaynaksiz_motor_onerisiz_kalir.
  * body() kapısı kaldırılırsa -> test_eksik_alanla_istek_gonderilmez.

Koşum hedeflidir (süit disiplini):
    python3 -m pytest tests/test_stability_panel.py -q
"""

import copy
import itertools
import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_cfd_endpoint import _sessiz
from tests.test_cfd_panel import HIBRIT_GOVDE, KATI_GOVDE, SIVI_GOVDE

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
CENTER_JS = STATIC_JS / 'analysis_center.js'
PANEL_JS = STATIC_JS / 'panels' / 'stability_panel.js'
LIQUID_ENGINE_PY = REPO_ROOT / 'hrma' / 'engines' / 'liquid_rocket_engine.py'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

UC = '/api/analysis/combustion-stability'

#: Ucun mode='chug' için zorunlu saydığı form alanları.
CHUG_ZORUNLU = ('dp_ratio_j', 'tau_s', 'tau_c_s')
#: Ucun mode='damping' için zorunlu saydığı form alanları.
DAMPING_ZORUNLU = ('sound_speed_m_s', 'chamber_length_m', 'gamma',
                   'nozzle_entrance_mach')

#: Panelin çeviri anahtarı öneki + bilerek PAYLAŞILAN istisnalar
#: (§2 matrisinin satır başlıkları — kiracı kendi başlığını uydurmasın).
STAB_ANAHTAR_ONEKI = 'panel.stab.'
STAB_PAYLASILAN_ANAHTARLAR = {'ac.an.acousticModes',
                              'ac.an.combustionStability'}

#: Sahte ilerlemenin bilinen üretim yolları (çerçeve bekçisiyle aynı liste).
YASAK_CAGRILAR = ['setInterval', 'setTimeout', 'requestAnimationFrame',
                  'Math.random']

#: Sayfa -> Merkez motor tipi (şablon bekçisi). advanced.html include'unu
#: A3 ekliyor; o parametre A3 inene kadar kırmızı kalabilir.
SAYFALAR = {'/hybrid': 'hybrid', '/solid': 'solid', '/liquid': 'liquid'}
STAB_SRC = '/static/js/panels/stability_panel.js'
CENTER_SRC = '/static/js/analysis_center.js'


def read(path):
    return path.read_text(encoding='utf-8')


def strip_js_comments(text):
    """JS yorumlarını aynı uzunlukta boşlukla değiştirir (ofsetler korunur).

    tests/test_cfd_panel.py'deki aynı adlı yardımcının kopyası (o desen
    bilerek kopyalanıyor: modül kapsamı hedefli koşuma girmesin). Yorum
    metni denetimi kirletmemeli — panelin başlık yorumu zaten yasaklı
    çağrıların adlarını cümle içinde anıyor.
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
def panel_code():
    return strip_js_comments(read(PANEL_JS))


@pytest.fixture(scope='module')
def center_code():
    return strip_js_comments(read(CENTER_JS))


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GERÇEK veri: motor sonuçları (üç tip) — tasarım noktaları test_cfd_panel
# ile TEK kaynak.
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def motor_hibrit(client):
    r = _sessiz(client.post, '/calculate', json=HIBRIT_GOVDE,
                headers={'Host': '127.0.0.1:8080'})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def motor_kati(client):
    r = _sessiz(client.post, '/calculate_solid', json=KATI_GOVDE)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def motor_sivi(client):
    r = _sessiz(client.post, '/calculate_liquid', json=SIVI_GOVDE)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


def _motor_sozlugu(results):
    m = results.get('motor')
    return m if isinstance(m, dict) else results


def _yol(sozluk, yol):
    cur = sozluk
    for parca in yol.split('.'):
        if not isinstance(cur, dict) or parca not in cur:
            return None
        cur = cur[parca]
    return cur


# ---------------------------------------------------------------------------
# UC SÖZLEŞMESİ biçiminde yanıtlar — sayılar hrma.stability çekirdeğinin
# GERÇEK çağrılarından (A2'nin ucu paralel yazılıyor; zarf donmuş sözleşme).
# ---------------------------------------------------------------------------

def chug_yaniti(dp, tau, tau_c, tau_f=None):
    from hrma.stability.chug import (
        assess_chug,
        chug_neutral_tau_ratio,
        chug_rightmost_root,
    )
    assessment = assess_chug(dp_ratio_j=dp, tau_s=tau, tau_c_s=tau_c,
                             tau_f_s=tau_f)
    n = 60
    j_list = [0.02 + i * (0.48 - 0.02) / (n - 1) for i in range(n)]
    neutral = [chug_neutral_tau_ratio(j) for j in j_list]
    lj, sg, fr, atlanan = [], [], [], []
    for j in j_list:
        try:
            root = chug_rightmost_root(j, tau, tau_c, tau_f or 0.0)
        except ValueError as exc:
            atlanan.append({'dp_ratio_j': j, 'reason': str(exc)})
            continue
        if root is None:
            atlanan.append({'dp_ratio_j': j, 'reason': 'root not polished'})
            continue
        lj.append(j)
        sg.append(float(root.real))
        fr.append(abs(float(root.imag)) / (2.0 * math.pi))
    return {
        'status': 'ok', 'mode': 'chug', 'assessment': assessment,
        'neutral_curve': {'dp_ratio_j': j_list, 'tau_over_tau_c': neutral},
        'root_locus': {'dp_ratio_j': lj, 'sigma_1_s': sg,
                       'frequency_hz': fr},
        'operating_point': {'dp_ratio_j': dp,
                            'tau_over_tau_c': assessment['tau_over_tau_c']},
        'skipped_points': atlanan,
    }


def sonum_yaniti(a, uzunluk, gamma, mach):
    from hrma.stability import damping_budget, nozzle_damping_quasi_steady
    noz = nozzle_damping_quasi_steady(a, uzunluk, gamma, mach)
    return {'status': 'ok', 'mode': 'damping', 'nozzle': noz,
            'budget': damping_budget([noz])}


def sivi_chug_girdileri(motor_sivi):
    """Sıvı motorun kendi chug çevrimi yankısı — testte elle sayı yazılmaz."""
    cevrim = _yol(_motor_sozlugu(motor_sivi),
                  'combustion_analysis.stability_analysis.chug_loop')
    assert cevrim and cevrim.get('status') == 'modelled', (
        'vaka değişmiş: sıvı chug çevrimi çözülmüyor')
    inp = cevrim['inputs']
    return inp['dp_ratio_j'], inp['tau_s'], inp['tau_c_s']


def akustik_blok(results):
    m = _motor_sozlugu(results)
    for yol in ('acoustic_modes',
                'combustion_analysis.stability_analysis.acoustic_modes'):
        blok = _yol(m, yol)
        if isinstance(blok, dict) and blok.get('modes'):
            return blok, yol
    return None, None


def sonum_girdileri(results, mach_yedek=None):
    """Motorun kendi yayınından damping girdileri (uydurma yok)."""
    blok, _ = akustik_blok(results)
    assert blok, 'vaka değişmiş: akustik blok yok'
    m = _motor_sozlugu(results)
    mach = _yol(m, 'combustion_stability.acoustic_response_threshold'
                   '.mean_flow_mach_M_N')
    if mach is None:
        mach = mach_yedek
    assert mach is not None, 'M_N kaynağı yok ve yedek verilmedi'
    return (blok['sound_speed_m_s'], blok['inputs']['chamber_length'],
            blok['inputs']['gamma'], mach)


# ---------------------------------------------------------------------------
# node koşum ortamı — Merkez + kararlılık kiracısı, taklit DOM/Plotly/fetch
# (kalıp: tests/test_cfd_panel.py HARNESS)
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const centerPath = process.argv[3];
const panelPath = process.argv[4];

const nodes = {};
function makeNode(id) {
    return {
        id: id, innerHTML: '', textContent: '', style: {}, attrs: {},
        value: '', disabled: false, options: [], children: [],
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild(c) { this.children.push(c); return c; },
        querySelector() { return null; },
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

const plotly = [];
global.Plotly = {
    react(el, traces, layout) {
        plotly.push({ id: el && el.id, traces: traces, layout: layout });
    },
    purge() {},
};

const fetchCalls = [];
let releaseFetch = null;
global.fetch = function (url, opts) {
    fetchCalls.push({ url: url,
                      body: (opts && opts.body) ? JSON.parse(opts.body) : null });
    const resp = {
        ok: payload.httpOk !== false,
        status: (payload.httpOk === false) ? 422 : 200,
        text: function () {
            return Promise.resolve(JSON.stringify(payload.response || {}));
        },
    };
    return new Promise(function (resolve) {
        releaseFetch = function () { resolve(resp); };
    });
};

require(centerPath);
require(panelPath);
const AC = window.AnalysisCenter;
const SP = window.StabilityPanel;

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
    const out = {};
    if (payload.select) AC.select(payload.select[0], payload.select[1]);
    if (payload.clearFields) {
        payload.clearFields.forEach(function (f) {
            const id = AC._fieldDomId(payload.select[0], payload.select[1], f);
            const el = document.getElementById(id);
            el.value = '';
            el.setAttribute('data-dirty', '1');
        });
    }
    if (payload.editFields) {
        payload.editFields.forEach(function (pair) {
            const id = AC._fieldDomId(payload.select[0], payload.select[1],
                                      pair[0]);
            const el = document.getElementById(id);
            el.value = pair[1];
            el.setAttribute('data-dirty', '1');
        });
    }
    const runCount = payload.runs || 0;
    for (let i = 0; i < runCount; i++) {
        const p = AC.run();
        if (i === 0 && nodes['ac_status']) {
            out.statusDuringRun = nodes['ac_status'].textContent;
        }
        if (releaseFetch) { releaseFetch(); releaseFetch = null; }
        await p;
    }
    // Saf model katmanı ölçümleri (DOM'suz da geçerli)
    out.suggestChug = SP._suggestChug(payload.results || null);
    out.suggestDamping = SP._suggestDamping(payload.results || null);
    out.verdictChug = payload.response ? SP._chugVerdict(payload.response) : null;
    out.verdictDamping = SP._dampingVerdict();
    out.specs = {};
    ['specAcoustic', 'specChug'].forEach(function (name) {
        const s = SP[name];
        out.specs[name] = {
            keys: Object.keys(s),
            componentId: s.componentId, analysisId: s.analysisId,
            endpoint: s.endpoint, motorTypes: s.motorTypes,
            titleKey: s.titleKey, long: s.long,
            fields: s.fields.map(function (f) {
                return { id: f[0], label: f[1], def: f[2], key: f[4] };
            }),
        };
    });
    out.lastSentAcoustic = (function () {
        const snap = SP._lastSentAcoustic();
        if (!snap) return null;
        return { path: snap.path, sound: snap.sound_speed_m_s,
                 length: snap.chamber_length_m,
                 nModes: snap.modes ? snap.modes.length : 0,
                 hasLfi: !!snap.lfi, hasChugLoop: !!snap.chugLoop,
                 hasThreshold: !!(snap.threshold && snap.threshold.block) };
    })();
    out.model = dumpModel();
    out.fetchCalls = fetchCalls;
    out.plotly = plotly.map(function (c) {
        return { id: c.id, traces: c.traces, layout: c.layout };
    });
    out.history = AC.history().map(function (e) {
        return { rowKey: e.rowKey, ok: e.ok, hasVerdict: !!e.verdict,
                 verdict: e.verdict, errorText: e.errorText };
    });
    out.nodes = {};
    Object.keys(nodes).forEach(function (id) {
        out.nodes[id] = { html: nodes[id].innerHTML, text: nodes[id].textContent,
                          value: String(nodes[id].value), attrs: nodes[id].attrs };
    });
    // K1/K2 görsel metrik yüzeyi: testler yerleşimi/ölçümü panelin KENDİ
    // saf fonksiyonlarıyla yeniden hesaplar (Python'da formül kopyası yok).
    out.axisMetrics = SP._axisMetrics;
    if (payload.probes) {
        const pb = payload.probes;
        out.probes = {};
        if (pb.layoutModeLabels) {
            out.probes.layoutModeLabels = SP._layoutModeLabels(
                pb.layoutModeLabels.items, pb.layoutModeLabels.opts);
        }
        if (pb.measure) {
            out.probes.measure = pb.measure.map(function (p) {
                return SP._measureLabelPx(p[0], p[1]);
            });
        }
        if (pb.wrapTitle) {
            out.probes.wrapTitle = SP._wrapAxisTitle(
                pb.wrapTitle.text, pb.wrapTitle.availablePx, pb.wrapTitle.fontPx);
        }
        if (pb.tickWidth) {
            out.probes.tickWidth = SP._maxTickWidthPx(
                pb.tickWidth.values, pb.tickWidth.fontPx);
        }
    }
    process.stdout.write(JSON.stringify(out));
})();
"""


def kos_panel(tmp_path, **payload):
    """Merkez + kararlılık kiracısını node'da koşturur."""
    script = tmp_path / 'kos_stab_panel.js'
    script.write_text(HARNESS, encoding='utf-8')
    girdi = tmp_path / 'girdi.json'
    girdi.write_text(json.dumps(payload), encoding='utf-8')
    proc = subprocess.run(
        [NODE, str(script), str(girdi), str(CENTER_JS), str(PANEL_JS)],
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, 'panel node altında çöktü:\n' + proc.stderr[-3000:]
    return json.loads(proc.stdout)


def satirlar(out):
    flat = {}
    for comp in out['model']:
        for row in comp['rows']:
            flat[(row['componentId'], row['analysisId'])] = row
    return flat


def akustik_satiri(out):
    return satirlar(out)[('chamber_acoustics', 'acoustic_modes')]


def chug_satiri(out):
    return satirlar(out)[('chamber_acoustics', 'combustion_stability')]


ROZET_RE = re.compile(r'<span data-stab-badge="(\w+)"[^>]*>(.*?)</span>', re.S)


def rozetler(html):
    return [(sinif, re.sub(r'\s+', ' ', metin).strip())
            for sinif, metin in ROZET_RE.findall(html)]


def gorunum(out):
    return out['nodes']['ac_view_root']['html']


def cizim(out, onek):
    for c in out['plotly']:
        if c['id'].startswith(onek):
            return c
    return None


def iz(cagri, ad_parcasi):
    for t in cagri['traces']:
        if ad_parcasi in str(t.get('name') or ''):
            return t
    return None


def yakin(a, b, bagil=1e-9):
    return math.isclose(float(a), float(b), rel_tol=bagil, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 1. Kaynak hijyeni: sahte ilerleme + sahte sayı yasağı, i18n öneki
# ---------------------------------------------------------------------------

class TestKaynakHijyeni:
    @needs_node
    def test_js_sozdizimi(self):
        proc = subprocess.run([NODE, '--check', str(PANEL_JS)],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr

    @pytest.mark.parametrize('cagri', YASAK_CAGRILAR)
    def test_zamanlayici_ve_rastgelelik_yok(self, cagri, panel_code):
        assert cagri not in panel_code, (
            f'{cagri} kullanılmış — gerçek iterasyon akışı gelene kadar '
            'ilerleme gösterilmez (tasarım kural 3)')

    def test_dolan_cubuk_yok(self, panel_code):
        assert not re.search(r'style\.width\s*=', panel_code), \
            'style.width ataması — dolan çubuk şüphesi'
        assert not re.search(r'width:\s*\$\{', panel_code), \
            'şablonla hesaplanan genişlik — dolan çubuk şüphesi'
        assert 'progress' not in panel_code.lower(), \
            'ilerleme göstergesi eklenmiş — koşum ilerlemesi ölçülemiyor'

    def test_izlerde_sayisal_literal_yok(self, panel_code):
        """SAHTE SAYI TARAMASI: hiçbir izin x/y/z alanı sayı literali dizisi
        ile beslenmez — her çizim yanıttan/anlık görüntüden gelir.

        (Yanlış pozitif üretmesin diye yalnız DİZİ literali aranır:
        ``x: [0.1, ...]`` yakalanır, ``x: nc.dp_ratio_j`` ve düzen alanı
        ``y: -0.3`` yakalanmaz.)
        """
        assert re.search(r'\bx:\s*', panel_code), (
            'panelde hiç iz kurulmuyor — tarama boşa düşer (vaka değişmiş)')
        kacak = re.findall(r'\b[xyz]\s*:\s*\[\s*[-+0-9.]', panel_code)
        assert not kacak, (
            f'izlere sayısal dizi literali yazılmış: {kacak} — çizimler '
            'yanıttan/anlık görüntüden beslenmeli, sabitten değil')

    def test_panel_kendini_merkeze_kaydediyor(self, panel_code):
        assert panel_code.count('AnalysisCenter.register(') >= 2, (
            'iki kiracı kaydı bekleniyordu (acoustic_modes + '
            'combustion_stability)')

    def test_ceviri_anahtarlari_panel_stab_onekinde(self, panel_code):
        anahtarlar = set()
        for kalip in (r"\bT\(\s*'([\w.]+)'", r"\bTF\(\s*'([\w.]+)'",
                      r"key:\s*'([\w.]+)'", r'data-i18n="([\w.]+)"'):
            anahtarlar |= set(re.findall(kalip, panel_code))
        anahtarlar = {a for a in anahtarlar if '.' in a}
        assert anahtarlar, 'panelde hiç çeviri anahtarı yok — metinler gömülü'
        yabanci = {a for a in anahtarlar
                   if not a.startswith(STAB_ANAHTAR_ONEKI)} - STAB_PAYLASILAN_ANAHTARLAR
        assert not yabanci, (
            f'panel.stab.* dışında anahtar üretilmiş: {sorted(yabanci)}')


# ---------------------------------------------------------------------------
# 2. Matris + kod kanıtı
# ---------------------------------------------------------------------------

class TestMatris:
    def test_matrix_sivi_kod_kanitina_bagli(self, center_code):
        """MATRIX'teki 'liquid', sıvı çözücünün GERÇEK çağrısına bağlıdır.

        İki iddia AYNI testte: (a) liquid_rocket_engine.py merkezî akustik
        modülü gerçekten içe aktarıyor, (b) matrisin acoustic_modes satırı
        'liquid' taşıyor. Import silinirse bu test kırmızı yanar — yani
        matristeki 'liquid' kanıtsız yaşayamaz (parti 27 F2b-2 göçü).
        """
        kaynak = read(LIQUID_ENGINE_PY)
        assert 'from hrma.analysis.acoustic_modes import' in kaynak, (
            "KOD KANITI DÜŞTÜ: sıvı çözücü merkezî akustik modülü artık "
            "içe aktarmıyor — MATRIX'teki 'liquid' çürük iddia olur, "
            "satırdan da kaldırılmalı")
        # (b) matrisin acoustic_modes satırı (yorumlar temizlenmiş kodda).
        baslangic = center_code.find("analysisId: 'acoustic_modes'")
        assert baslangic != -1, 'acoustic_modes matris satırı kayıp'
        parca = center_code[baslangic:center_code.find('}', baslangic)]
        assert "'liquid'" in parca, (
            "MATRIX acoustic_modes satırında 'liquid' yok — F2b-2 göçüyle "
            'eklenmişti (sıvı da merkezî modülü çağırıyor)')

    def test_matrix_combustion_stability_satiri(self, center_code):
        baslangic = center_code.find("analysisId: 'combustion_stability'")
        assert baslangic != -1, (
            'chamber_acoustics × combustion_stability matris satırı yok')
        parca = center_code[baslangic:center_code.find('}', baslangic)]
        assert "'/api/analysis/combustion-stability'" in parca, (
            'planlanan uç adı matriste yanlış/eksik')
        assert "'ac.an.combustionStability'" in parca, 'titleKey eksik'
        for tip in ('hybrid', 'solid', 'liquid'):
            assert f"'{tip}'" in parca, f'{tip} motor kapsamı eksik'

    @needs_node
    def test_matrix_satirlari_modelde(self, tmp_path, motor_hibrit):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        düz = satirlar(out)
        assert ('chamber_acoustics', 'acoustic_modes') in düz
        assert ('chamber_acoustics', 'combustion_stability') in düz

    @needs_node
    def test_sivi_akustik_satiri_motor_tipiyle_engellenmiyor(
            self, tmp_path, motor_sivi):
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi)
        row = akustik_satiri(out)
        assert row['state'] == 'ready', (
            f'sıvıda akustik satırı gri: {row["reason"]!r} — F2b-2 göçüyle '
            'sıvı da merkezî modülü çağırıyor, satır çalışır olmalı')


# ---------------------------------------------------------------------------
# 3. Kayıt sözleşmesi
# ---------------------------------------------------------------------------

@needs_node
class TestKayitSozlesmesi:
    @pytest.mark.parametrize('spec', ['specAcoustic', 'specChug'])
    @pytest.mark.parametrize('alan', ['componentId', 'analysisId', 'endpoint',
                                      'motorTypes', 'applicability', 'fields',
                                      'fromResults', 'body', 'render',
                                      'verdict', 'long', 'title', 'titleKey'])
    def test_sozlesme_alani_veriliyor(self, tmp_path, motor_hibrit, spec, alan):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        assert alan in out['specs'][spec]['keys'], (
            f'{spec}.{alan} kayıt sözleşmesinde yok')

    def test_iki_kiraci_ayni_uca_bagli(self, tmp_path, motor_hibrit):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        assert out['specs']['specAcoustic']['endpoint'] == UC
        assert out['specs']['specChug']['endpoint'] == UC
        for ad in ('specAcoustic', 'specChug'):
            assert sorted(out['specs'][ad]['motorTypes']) == \
                ['hybrid', 'liquid', 'solid']

    def test_zorunlu_alanlar_uc_sozlesmesiyle_ortusur(self, tmp_path,
                                                     motor_hibrit):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        chug = {f['id'] for f in out['specs']['specChug']['fields']}
        assert set(CHUG_ZORUNLU) <= chug, (
            f'chug zorunlu girdileri forma bağlanmamış: '
            f'{set(CHUG_ZORUNLU) - chug}')
        assert 'tau_f_s' in chug, 'opsiyonel tau_f alanı yok (sözleşmede var)'
        damping = {f['id'] for f in out['specs']['specAcoustic']['fields']}
        assert set(DAMPING_ZORUNLU) <= damping, (
            f'damping zorunlu girdileri forma bağlanmamış: '
            f'{set(DAMPING_ZORUNLU) - damping}')

    def test_hicbir_alanin_sonlu_varsayilani_yok(self, tmp_path, motor_hibrit):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        for ad in ('specAcoustic', 'specChug'):
            sayisal = [f['id'] for f in out['specs'][ad]['fields']
                       if isinstance(f['def'], (int, float))]
            assert not sayisal, (
                f'{ad}: sayısal varsayılanlı alan(lar): {sayisal} — motor o '
                'alanı yayımlamadığında kullanıcıya uydurma sayı gösterilir')

    def test_satirlar_griden_cikti(self, tmp_path, motor_hibrit, motor_sivi):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        assert akustik_satiri(out)['state'] == 'ready'
        assert chug_satiri(out)['state'] == 'ready', (
            'hibritte chug satırı çalışır olmalı (çözücü chug için '
            'uygulanamazlık BEYAN ETMİYOR; yalnız öneriler boş kalır)')
        out2 = kos_panel(tmp_path, motorType='liquid', results=motor_sivi)
        assert chug_satiri(out2)['state'] == 'ready'

    def test_katida_chug_cozucunun_kendi_beyaniyla_gri(self, tmp_path,
                                                       motor_kati):
        """Katı çözücü chug'ın YAPISAL uygulanamazlığını kendisi beyan ediyor
        (acoustic_modes.chug_applicability); satır o beyanla gri durur."""
        m = _motor_sozlugu(motor_kati)
        beyan = _yol(m, 'acoustic_modes.chug_applicability')
        assert beyan and beyan['applicable'] is False, 'vaka değişmiş'
        out = kos_panel(tmp_path, motorType='solid', results=motor_kati)
        row = chug_satiri(out)
        assert row['state'] == 'blocked'
        assert 'injector' in row['reason'] and 'feed system' in row['reason'], (
            f'çözücünün kendi gerekçesi taşınmamış: {row["reason"]!r}')
        # Akustik/sönüm satırı katıda ÇALIŞIR kalır.
        assert akustik_satiri(out)['state'] == 'ready'

    def test_akustik_tablo_yoksa_satir_gri_ve_neden_adli(self, tmp_path,
                                                         motor_hibrit):
        kirpik = copy.deepcopy(motor_hibrit)
        kirpik['motor'].pop('acoustic_modes', None)
        out = kos_panel(tmp_path, motorType='hybrid', results=kirpik)
        row = akustik_satiri(out)
        assert row['state'] == 'blocked'
        assert 'acoustic' in row['reason'], (
            f'eksik blok adlandırılmamış: {row["reason"]!r}')

    def test_uygulanabilirlik_yan_etkisiz(self, tmp_path, motor_hibrit):
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        assert out['fetchCalls'] == [], (
            'uygulanabilirlik ölçümü istek atmış — ağaç her çizildiğinde '
            'sunucuya gider')


# ---------------------------------------------------------------------------
# 4. Öneriler — GERÇEK motor sonuçlarından, ölçülerek
# ---------------------------------------------------------------------------

@needs_node
class TestOneriler:
    def test_sivi_chug_onerileri_cevrimin_yankisindan(self, tmp_path,
                                                      motor_sivi):
        """Sıvıda J/τ/τ_c önerileri chug_loop.inputs yankısına BİT-yakın."""
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi)
        deger = out['suggestChug']['values']
        kaynak = out['suggestChug']['sources']
        m = _motor_sozlugu(motor_sivi)
        for alan in CHUG_ZORUNLU:
            assert alan in deger, f'sıvı: {alan} önerisi yok'
            yol = kaynak[alan]['path']
            ham = _yol(m, yol)
            assert ham is not None, f'beyan edilen yol boş: {yol}'
            assert yakin(deger[alan], ham), (
                f'sıvı: {alan} önerisi {deger[alan]} ama {yol} → {ham}')

    def test_kati_tau_c_onerisi_kendi_blogundan(self, tmp_path, motor_kati):
        out = kos_panel(tmp_path, motorType='solid', results=motor_kati)
        deger = out['suggestChug']['values']
        kaynak = out['suggestChug']['sources']
        m = _motor_sozlugu(motor_kati)
        beklenen = _yol(m, 'combustion_stability.chamber_time_constant.tau_c_s')
        assert beklenen is not None, 'vaka değişmiş: katı τ_c yayımlamıyor'
        assert yakin(deger['tau_c_s'], beklenen)
        assert kaynak['tau_c_s']['path'] == \
            'combustion_stability.chamber_time_constant.tau_c_s'
        # Katıda J ve τ kaynağı yok — önerisiz kalmalı.
        assert 'dp_ratio_j' not in deger and 'tau_s' not in deger

    def test_hibrit_chug_onerileri_cevrimin_yankisindan(self, tmp_path,
                                                        motor_hibrit):
        """Hibrit chug bağlaması (bu partide indi) inputs yankısı yayımlıyor;
        öneriler ORADAN gelmeli (ölçüldü: combustion_stability.chug_loop)."""
        m = _motor_sozlugu(motor_hibrit)
        cevrim = _yol(m, 'combustion_stability.chug_loop')
        assert cevrim and cevrim.get('status') == 'modelled', (
            'vaka değişmiş: hibrit chug çevrimi çözülmüyor')
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit)
        deger = out['suggestChug']['values']
        kaynak = out['suggestChug']['sources']
        for alan in CHUG_ZORUNLU:
            assert alan in deger, f'hibrit: {alan} önerisi yok'
            assert kaynak[alan]['path'] == \
                f'combustion_stability.chug_loop.inputs.{alan}'
            assert yakin(deger[alan], cevrim['inputs'][alan])
        assert chug_satiri(out)['state'] == 'ready'

    def test_kaynaksiz_motor_onerisiz_kalir(self, tmp_path, motor_hibrit):
        """Motor chug çevrimini yayımlamıyorsa öneri YOKTUR.

        Sonuç sözlüğü GERÇEK olandır; yalnız chug_loop bloğu silinir. Sabit
        bir varsayılan (0,2 / 2 ms benzeri) konursa bu bekçi kırmızıya
        döner — alan boş kalır, kullanıcı elle girer.
        """
        kirpik = copy.deepcopy(motor_hibrit)
        (kirpik['motor'].get('combustion_stability') or {}).pop('chug_loop',
                                                               None)
        out = kos_panel(tmp_path, motorType='hybrid', results=kirpik)
        deger = out['suggestChug']['values']
        for alan in ('dp_ratio_j', 'tau_s'):
            assert alan not in deger, (
                f'kaynağı olmayan {alan} için sayı UYDURULMUŞ: '
                f'{deger.get(alan)}')
        # Satır yine de çalıştırılabilir kalır (kullanıcı elle girebilir).
        assert chug_satiri(out)['state'] == 'ready'

    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_akustik_onerileri_motorun_kendi_alanindan(
            self, tmp_path, tip, motor_hibrit, motor_kati, motor_sivi):
        results = {'hybrid': motor_hibrit, 'solid': motor_kati,
                   'liquid': motor_sivi}[tip]
        out = kos_panel(tmp_path, motorType=tip, results=results)
        deger = out['suggestDamping']['values']
        kaynak = out['suggestDamping']['sources']
        m = _motor_sozlugu(results)
        for alan in ('sound_speed_m_s', 'chamber_length_m', 'gamma'):
            assert alan in deger, f'{tip}: {alan} önerisi yok'
            ham = _yol(m, kaynak[alan]['path'])
            assert ham is not None and yakin(deger[alan], ham), (
                f'{tip}: {alan} önerisi motorun yayınından ayrışmış')
        mach = _yol(m, 'combustion_stability.acoustic_response_threshold'
                       '.mean_flow_mach_M_N')
        if tip == 'liquid':
            assert mach is None, 'vaka değişmiş: sıvı M_N yayımlamaya başladı'
            assert 'nozzle_entrance_mach' not in deger, (
                'sıvı: kaynağı olmayan M_N için sayı UYDURULMUŞ')
        else:
            assert mach is not None and \
                yakin(deger['nozzle_entrance_mach'], mach)


# ---------------------------------------------------------------------------
# 5. İstek gövdesi ve eksik alan kapıları
# ---------------------------------------------------------------------------

@needs_node
class TestIstekGovdesi:
    def test_chug_govdesi_mode_ve_formdan(self, tmp_path, motor_sivi):
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=chug_yaniti(dp, tau, tau_c),
                        select=['chamber_acoustics', 'combustion_stability'],
                        runs=1)
        assert len(out['fetchCalls']) == 1
        cagri = out['fetchCalls'][0]
        assert cagri['url'] == UC
        govde = cagri['body']
        assert govde['mode'] == 'chug'
        # Form ön dolumu 6 anlamlı basamağa yuvarlar (DOCK_SIGFIG) — gövde
        # formdan okunduğu için karşılaştırma o toleransla yapılır.
        for alan, beklenen in zip(CHUG_ZORUNLU, (dp, tau, tau_c)):
            assert yakin(govde[alan], beklenen, 1e-5), (
                f'{alan}: gövde {govde[alan]}, motorun yankısı {beklenen}')
        assert 'tau_f_s' not in govde, 'boş opsiyonel alan gövdeye konmuş'
        assert 'feed_line' not in govde

    def test_damping_govdesi_mode_ve_formdan(self, tmp_path, motor_hibrit):
        a, L, g, mach = sonum_girdileri(motor_hibrit)
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=sonum_yaniti(a, L, g, mach),
                        select=['chamber_acoustics', 'acoustic_modes'],
                        runs=1)
        govde = out['fetchCalls'][0]['body']
        assert govde['mode'] == 'damping'
        for alan, beklenen in zip(DAMPING_ZORUNLU, (a, L, g, mach)):
            assert yakin(govde[alan], beklenen, 1e-5)

    def test_eksik_alanla_istek_gonderilmez(self, tmp_path, motor_sivi):
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=chug_yaniti(dp, tau, tau_c),
                        select=['chamber_acoustics', 'combustion_stability'],
                        clearFields=['tau_c_s'], runs=1)
        assert out['fetchCalls'] == [], 'eksik zorunlu alanla istek gönderilmiş'
        durum = out['nodes']['ac_status']['text']
        assert 'tau_c' in durum, f'eksik alan adıyla yazılmamış: {durum!r}'
        assert out['history'] == [], 'gönderilmeyen istek geçmişe yazılmış'

    def test_besleme_grubu_yarimsa_gonderilmez(self, tmp_path, motor_sivi):
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=chug_yaniti(dp, tau, tau_c),
                        select=['chamber_acoustics', 'combustion_stability'],
                        editFields=[['feed_line_length_m', 2.5]], runs=1)
        assert out['fetchCalls'] == [], (
            'yarım besleme grubuyla istek gönderilmiş — eksik üyeler '
            'uydurulamaz')
        durum = out['nodes']['ac_status']['text']
        # Parti 28 artçısı: uç sözleşmesi dp_injector_Pa'yı ZORUNLU yaptı,
        # yoğunluğu yankıya düşürdü — eksik listesi de o sözleşmeyi izler.
        assert 'mass_flow' in durum and 'dp_injector' in durum, (
            f'grubun eksik üyeleri adıyla yazılmamış: {durum!r}')
        assert 'density' not in durum, (
            'yoğunluk eksik SAYILMAMALI — uç onu yalnız yankılar; etkisiz '
            f'alanı zorunlu göstermek kullanıcıya sayı uydurtur: {durum!r}')

    def test_tau_f_ile_grup_cakisirsa_gonderilmez(self, tmp_path, motor_sivi):
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=chug_yaniti(dp, tau, tau_c),
                        select=['chamber_acoustics', 'combustion_stability'],
                        editFields=[['tau_f_s', 0.004],
                                    ['feed_line_length_m', 2.5]], runs=1)
        assert out['fetchCalls'] == [], (
            'iki τ_f yolu birden verilmişken istek gönderilmiş — hangisinin '
            'kullanıldığı ekrandan okunamazdı')

    def test_tam_besleme_grubu_gonderilir(self, tmp_path, motor_sivi):
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=chug_yaniti(dp, tau, tau_c, tau_f=0.001),
                        select=['chamber_acoustics', 'combustion_stability'],
                        editFields=[['feed_line_length_m', 2.5],
                                    ['feed_line_diameter_mm', 25],
                                    ['feed_line_mass_flow_kg_s', 3.2],
                                    ['feed_line_dp_injector_Pa', 2.0e6],
                                    ['feed_line_density_kg_m3', 810]],
                        runs=1)
        govde = out['fetchCalls'][0]['body']
        hat = govde.get('feed_line')
        # Parti 28 artçısı: dp_injector_Pa grubun zorunlu üyesi (uç
        # sözleşmesi); yoğunluk isteğe bağlı ve verildiyse yankı için taşınır.
        assert hat == {'length_m': 2.5, 'diameter_mm': 25,
                       'mass_flow_kg_s': 3.2, 'dp_injector_Pa': 2.0e6,
                       'density_kg_m3': 810}, (
            f'besleme grubu sözleşme biçiminde gitmemiş: {hat!r}')
        assert 'tau_f_s' not in govde


# ---------------------------------------------------------------------------
# 6. Hüküm disiplini (F2a karar 1)
# ---------------------------------------------------------------------------

@needs_node
class TestHukum:
    def test_hukum_kapsam_etiketiyle(self, tmp_path, motor_sivi):
        """Bu tasarım noktasında çevrim UNSTABLE (ölçüldü) — rozet hem hükmü
        hem MEKANİZMA KAPSAMINI taşımalı; çıplak hüküm yasak."""
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        yanit = chug_yaniti(dp, tau, tau_c)
        assert yanit['assessment']['verdict'] == 'unstable', (
            'vaka değişmiş: bu noktada çekirdek unstable veriyordu')
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=yanit,
                        select=['chamber_acoustics', 'combustion_stability'],
                        runs=1)
        v = out['history'][0]['verdict']
        assert v and v['kind'] == 'err'
        assert v['params']['scope'] == yanit['assessment']['verdict_scope'], (
            'kapsam etiketi hükümle birlikte taşınmıyor')
        serit = out['nodes']['ac_history']['html']
        assert 'UNSTABLE — feed-coupled chug' in serit, (
            'geçmiş şeridindeki rozet kapsam etiketsiz')
        rz = rozetler(gorunum(out))
        assert any('UNSTABLE — feed-coupled chug' in t for _k, t in rz), (
            'görünümdeki hüküm rozeti kapsam etiketsiz')

    def test_stable_hukum_ok_ve_kapsamli(self, tmp_path, motor_sivi):
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        # Gecikme nötr eğrinin ALTINA çekilir: çekirdek stable verir.
        yanit = chug_yaniti(dp, tau_c * 0.1, tau_c)
        assert yanit['assessment']['verdict'] == 'stable'
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=yanit)
        v = out['verdictChug']
        assert v['kind'] == 'ok'
        assert 'scope' in v['params'] and v['params']['scope'], (
            'stable hüküm kapsamsız basılmış')

    def test_kapsamsiz_hukum_bastirilir(self, tmp_path, motor_sivi):
        """ÇIPLAK HÜKÜM BEKÇİSİ: verdict_scope olmadan gelen hüküm ekrana
        hüküm olarak çıkamaz (karar 1'in sıkılaştırması)."""
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        yanit = chug_yaniti(dp, tau, tau_c)
        yanit['assessment'].pop('verdict_scope', None)
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=yanit)
        v = out['verdictChug']
        assert v is not None, 'kapsamsız hüküm sessizce yutulmuş (beyan yok)'
        metin = (v.get('fallback') or '') + json.dumps(v.get('params') or {})
        assert 'UNSTABLE' not in metin and 'STABLE' not in metin.replace(
            'SUPPRESSED', ''), (
            f'çıplak hüküm ekrana sızmış: {v!r}')
        assert 'SUPPRESSED' in (v.get('fallback') or ''), (
            'bastırma beyanı yok — kullanıcı rozeti neden görmediğini bilemez')

    def test_akustik_yolda_hukum_beyan_edilmez(self, tmp_path, motor_hibrit):
        """Sönüm/eşik yolunda hüküm YOKTUR (forbid_verdict_key ile yapısal);
        çerçeve 'hüküm beyan edilmedi' rozetini basar."""
        a, L, g, mach = sonum_girdileri(motor_hibrit)
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=sonum_yaniti(a, L, g, mach),
                        select=['chamber_acoustics', 'acoustic_modes'],
                        runs=1)
        assert out['verdictDamping'] is None
        assert out['history'][0]['hasVerdict'] is False
        assert 'NO VERDICT DECLARED' in out['nodes']['ac_history']['html']
        # Panel kendi rozet şeridinde de bunu ADIYLA söyler.
        assert any('NO STABILITY VERDICT' in t
                   for _k, t in rozetler(gorunum(out)))


# ---------------------------------------------------------------------------
# 7. Çizimler: her sayı yanıttan / koşum anlık görüntüsünden
# ---------------------------------------------------------------------------

@needs_node
class TestCizim:
    @pytest.fixture(scope='class')
    def chug_cizilmis(self, tmp_path_factory, motor_sivi):
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        yanit = chug_yaniti(dp, tau, tau_c)
        out = kos_panel(tmp_path_factory.mktemp('chug'), motorType='liquid',
                        results=motor_sivi, response=yanit,
                        select=['chamber_acoustics', 'combustion_stability'],
                        runs=1)
        return out, yanit

    def test_notr_egri_yanittaki_dizinin_kendisi(self, chug_cizilmis):
        out, yanit = chug_cizilmis
        cagri = cizim(out, 'stab_neutral')
        assert cagri, 'nötr eğri grafiği kurulmamış'
        egri = iz(cagri, 'Neutral curve')
        assert egri is not None
        assert egri['x'] == yanit['neutral_curve']['dp_ratio_j']
        assert egri['y'] == yanit['neutral_curve']['tau_over_tau_c'], (
            'nötr eğri yeniden hesaplanmış/örneklenmiş — yanıtın kendisi '
            'çizilmeli')

    def test_isletme_noktasi_yanittan(self, chug_cizilmis):
        out, yanit = chug_cizilmis
        nokta = iz(cizim(out, 'stab_neutral'), 'Operating point')
        assert nokta is not None, 'işletme noktası imi yok'
        op = yanit['operating_point']
        assert yakin(nokta['x'][0], op['dp_ratio_j'])
        assert yakin(nokta['y'][0], op['tau_over_tau_c'])

    def test_kok_yeri_yanittaki_dizinin_kendisi(self, chug_cizilmis):
        out, yanit = chug_cizilmis
        cagri = cizim(out, 'stab_locus')
        assert cagri, 'kök yer grafiği kurulmamış'
        t = iz(cagri, 'Dominant root vs')
        assert t['x'] == yanit['root_locus']['sigma_1_s']
        assert t['y'] == yanit['root_locus']['frequency_hz']
        # İşletme J'sindeki baskın kök (çekirdek yayımladıysa) imlenir.
        a = yanit['assessment']
        if a['growth_rate_1_s'] is not None:
            im = iz(cagri, 'operating J')
            assert im is not None
            assert yakin(im['x'][0], a['growth_rate_1_s'])
            assert yakin(im['y'][0], a['frequency_hz'])

    def test_atlanan_noktalar_beyanli(self, tmp_path, motor_sivi):
        """UC bir örnekleme noktasını atlarsa panel bunu SAYAR ve LİSTELER.

        (Çekirdek ataletsiz taramada nokta atlamıyor — ölçüldü; bu yüzden
        atlanan kalem yanıt zarfına test kurgusu olarak eklenir: panelin
        görevi sözleşme alanını sessizce yutmamaktır.)
        """
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        yanit = chug_yaniti(dp, tau, tau_c)
        yanit['skipped_points'] = [{'dp_ratio_j': 0.02,
                                    'reason': 'core refused this sample'}]
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=yanit,
                        select=['chamber_acoustics', 'combustion_stability'],
                        runs=1)
        html = gorunum(out)
        assert 'data-stab-block="skipped"' in html
        assert 'core refused this sample' in html

    # --- akustik/sönüm kiracısı ---------------------------------------

    def test_mod_haritasi_anlik_goruntunun_kendisi(self, tmp_path,
                                                   motor_hibrit):
        a, L, g, mach = sonum_girdileri(motor_hibrit)
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=sonum_yaniti(a, L, g, mach),
                        select=['chamber_acoustics', 'acoustic_modes'],
                        runs=1)
        blok, _ = akustik_blok(motor_hibrit)
        cagri = cizim(out, 'stab_map')
        assert cagri, 'mod haritası çizilmemiş'
        modlar = iz(cagri, 'Cavity modes')
        assert modlar['x'] == [m['frequency_hz'] for m in blok['modes']], (
            'mod frekansları motorun tablosundan ayrışmış')
        assert modlar['y'] == [m['band'] for m in blok['modes']], (
            'bant sınıfları veriden gelmiyor')
        assert modlar['text'] == [m['label'] for m in blok['modes']]

    def test_hibrit_lfi_isareti_motorun_kendi_frekansinda(self, tmp_path,
                                                          motor_hibrit):
        m = _motor_sozlugu(motor_hibrit)
        lfi_f = _yol(m, 'combustion_stability.lfi.frequency_hz')
        assert lfi_f, 'vaka değişmiş: hibrit LFI çözülmüyor'
        a, L, g, mach = sonum_girdileri(motor_hibrit)
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=sonum_yaniti(a, L, g, mach),
                        select=['chamber_acoustics', 'acoustic_modes'],
                        runs=1)
        im = iz(cizim(out, 'stab_map'), 'LFI')
        assert im is not None, 'LFI imi çizilmemiş'
        assert yakin(im['x'][0], lfi_f)
        # Hibrit chug çevrimi f = 0 yayımlıyor (ölçüldü: J = 1,53 ≥ 0,5 →
        # koşulsuz kararlı, gerçel kök): sıfır frekans log eksene KONMAZ,
        # im çizilmez; sayı chug kiracısının kendi tablosunda durur.
        f_loop = _yol(m, 'combustion_stability.chug_loop.frequency_hz')
        assert f_loop == 0.0, 'vaka değişmiş: hibrit çevrim frekansı artık ' \
            f'{f_loop!r} — imin çizilip çizilmeyeceği yeniden ölçülmeli'
        assert iz(cizim(out, 'stab_map'), 'chug_loop') is None, (
            'sıfır frekanslı (salınımsız) kök log frekans eksenine çizilmiş')

    def test_sivi_chug_isareti_cevrimin_frekansinda(self, tmp_path,
                                                    motor_sivi):
        m = _motor_sozlugu(motor_sivi)
        f_chug = _yol(m, 'combustion_analysis.stability_analysis'
                         '.chug_loop.frequency_hz')
        assert f_chug, 'vaka değişmiş: sıvı chug frekansı yayımlanmıyor'
        blok, _ = akustik_blok(motor_sivi)
        # Sıvı M_N yayımlamıyor: kullanıcı elle girer (test girdisi).
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=sonum_yaniti(
                            blok['sound_speed_m_s'],
                            blok['inputs']['chamber_length'],
                            blok['inputs']['gamma'], 0.2),
                        select=['chamber_acoustics', 'acoustic_modes'],
                        editFields=[['nozzle_entrance_mach', 0.2]], runs=1)
        harita = cizim(out, 'stab_map')
        assert harita, 'sıvıda mod haritası çizilmemiş'
        im = iz(harita, 'chug_loop')
        assert im is not None and yakin(im['x'][0], f_chug)
        assert iz(harita, 'LFI') is None, 'sıvıda LFI imi uydurulmuş'

    def test_sonum_cubuklari_katinin_kendi_terimleri(self, tmp_path,
                                                     motor_kati):
        a, L, g, mach = sonum_girdileri(motor_kati)
        out = kos_panel(tmp_path, motorType='solid', results=motor_kati,
                        response=sonum_yaniti(a, L, g, mach),
                        select=['chamber_acoustics', 'acoustic_modes'],
                        runs=1)
        esik = _yol(_motor_sozlugu(motor_kati),
                    'combustion_stability.acoustic_response_threshold')
        cagri = cizim(out, 'stab_bars')
        assert cagri, 'katıda sönüm bütçesi çubukları çizilmemiş'
        cubuk = [t for t in cagri['traces'] if t.get('type') == 'bar'
                 and t.get('name') == 'nozzle']
        assert cubuk, 'lüle terimi çubuğu yok'
        assert cubuk[0]['x'] == [m['label'] for m in esik['modes']]
        beklenen = [m['damping']['nozzle'] for m in esik['modes']]
        assert all(yakin(g1, g2) for g1, g2 in zip(cubuk[0]['y'], beklenen)), (
            'çubuk değerleri motorun kendi sönüm terimlerinden ayrışmış')

    def test_sivi_sonum_cubuklari_gri_ve_gerekceli(self, tmp_path,
                                                   motor_sivi):
        """Sıvı bağlaması eşik bloğu yayımlamıyor (ölçüldü) → çubuk bölümü
        GRİ + gerekçe; sayı uydurulmaz."""
        assert _yol(_motor_sozlugu(motor_sivi), 'combustion_stability') is None
        blok, _ = akustik_blok(motor_sivi)
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=sonum_yaniti(
                            blok['sound_speed_m_s'],
                            blok['inputs']['chamber_length'],
                            blok['inputs']['gamma'], 0.2),
                        select=['chamber_acoustics', 'acoustic_modes'],
                        editFields=[['nozzle_entrance_mach', 0.2]], runs=1)
        assert cizim(out, 'stab_bars') is None, (
            'sıvıda çubuk çizilmiş — terimlerin kaynağı yok')
        html = gorunum(out)
        assert 'data-stab-grey="damping-bars"' in html, 'gri beyan yok'
        assert 'acoustic_response_threshold' in html, (
            'gerekçe eksik bloğu ADIYLA anmıyor')

    def test_yanki_uyusmayinca_harita_gri(self, tmp_path, motor_hibrit):
        """Saklanan koşunun yankısı eldeki tabloyla eşleşmiyorsa mod haritası
        ÇİZİLMEZ (geçmiş koşuya bugünkü tablo giydirilmez)."""
        a, L, g, mach = sonum_girdileri(motor_hibrit)
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=sonum_yaniti(a * 1.07, L, g, mach),
                        select=['chamber_acoustics', 'acoustic_modes'],
                        editFields=[['sound_speed_m_s', a * 1.07]], runs=1)
        assert cizim(out, 'stab_map') is None, (
            'yankı uyuşmazken mod haritası çizilmiş')
        html = gorunum(out)
        assert 'data-stab-grey="mode-map"' in html
        assert 'data-stab-grey="damping-bars"' in html, (
            'çubuklar da aynı kimlik kuralına bağlı olmalı')
        # Ucun kendi sönüm sözlükleri YİNE DE basılır (onlar yanıtın malı).
        assert 'data-stab-block="budget"' in html

    def test_plotly_yokken_cizim_yerine_beyan(self, tmp_path, motor_sivi):
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        harness = HARNESS.replace('global.Plotly = {', 'global._Plotly = {')
        script = tmp_path / 'kos_noplotly.js'
        script.write_text(harness, encoding='utf-8')
        girdi = tmp_path / 'girdi.json'
        girdi.write_text(json.dumps({
            'motorType': 'liquid', 'results': motor_sivi,
            'response': chug_yaniti(dp, tau, tau_c),
            'select': ['chamber_acoustics', 'combustion_stability'],
            'runs': 1}), encoding='utf-8')
        proc = subprocess.run(
            [NODE, str(script), str(girdi), str(CENTER_JS), str(PANEL_JS)],
            capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[-2000:]
        out = json.loads(proc.stdout)
        assert out['plotly'] == []
        assert 'data-stab-badge' in gorunum(out), (
            'grafik yokken sayılar da kaybolmuş')


# ---------------------------------------------------------------------------
# 8. Şablon sözleşmesi (advanced.html: A3 bekleniyor — o parametre A3 inene
#    kadar kırmızı kalabilir; bu dosyanın sahibi advanced.html'e dokunmaz)
# ---------------------------------------------------------------------------

class TestSablonlar:
    @pytest.mark.parametrize('sayfa', sorted(SAYFALAR))
    def test_include_var_ve_cekirdekten_sonra(self, client, sayfa):
        html = client.get(sayfa).get_data(as_text=True)
        core = html.find(CENTER_SRC)
        tenant = html.find(STAB_SRC)
        assert core != -1, f'{sayfa}: {CENTER_SRC} yüklenmiyor'
        assert tenant != -1, (
            f'{sayfa}: {STAB_SRC} yüklenmiyor'
            + (' (advanced.html include’u A3’ün işi — A3 bekleniyor)'
               if sayfa == '/hybrid' else ''))
        assert tenant > core, (
            f'{sayfa}: {STAB_SRC} çekirdekten ÖNCE yükleniyor — kiracı '
            'kaydolamaz (window.AnalysisCenter tanımsız)')

    def test_panel_dosyasi_sunuluyor(self, client):
        resp = client.get(STAB_SRC)
        assert resp.status_code == 200, (
            f'{STAB_SRC} {resp.status_code} döndü — konsol hatası üretir')


# ---------------------------------------------------------------------------
# 9. Canlı uç (A2 paralel yazıyor — bağlanana dek adıyla skip; bağlanınca
#    bu sınıf kendiliğinden uçtan uca ölçmeye başlar)
# ---------------------------------------------------------------------------

def _uc_bagli():
    from hrma.app import app
    return UC in {r.rule for r in app.url_map.iter_rules()}


class TestCanliUc:
    def test_gercek_ucla_uctan_uca(self, client, motor_sivi, tmp_path):
        if not _uc_bagli():
            pytest.skip('A2 bekleniyor: /api/analysis/combustion-stability '
                        'henüz app.py’ye bağlanmadı')
        if NODE is None:
            pytest.skip('node kurulu değil')
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        r = _sessiz(client.post, UC, json={'mode': 'chug', 'dp_ratio_j': dp,
                                           'tau_s': tau, 'tau_c_s': tau_c})
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        yanit = r.get_json()
        assert yanit['mode'] == 'chug'
        assert yanit['assessment'].get('verdict_scope'), (
            'UC hükmü kapsam etiketsiz yayımlıyor — sözleşme ihlali')
        assert len(yanit['neutral_curve']['dp_ratio_j']) >= 60
        out = kos_panel(tmp_path, motorType='liquid', results=motor_sivi,
                        response=yanit,
                        select=['chamber_acoustics', 'combustion_stability'],
                        runs=1)
        assert out['history'][0]['ok'] is True
        assert cizim(out, 'stab_neutral') is not None


# ===========================================================================
# Parti 28 artçısı — panel feed grubu ↔ uç sözleşmesi SÜRÜKLENME bekçisi.
#
# ÖLÇÜLEN sınıf: dalga içinde uç sözleşmesi gerekçeyle değişti
# (dp_injector_Pa zorunlu oldu, yoğunluk yankıya düştü) ama workflow
# ajanına SendMessage ulaşmadığı için panel eski sözleşmeyle indi — feed
# grubu yolu her koşuda 422 yiyecekti. El birleştirmesi kapattı; bu iki
# bekçi aynı sürüklenmenin bir daha SESSİZ kalmamasını sağlar.
# ===========================================================================
APP_PY = REPO_ROOT / 'hrma' / 'app.py'


def _uc_feed_zorunlulari():
    """app.py'nin feed_line ayrıştırıcısındaki missing.append adları."""
    kaynak = read(APP_PY)
    adlar = set(re.findall(r"missing\.append\('feed_line\.([^']+)'\)", kaynak))
    assert adlar, 'app.py feed_line zorunlu üye listesi bulunamadı — bekçi kör'
    return adlar


def _panel_feed_zorunlulari():
    """Panelin groupMissing.push adları (feed_line_ öneki düşürülmüş)."""
    kaynak = strip_js_comments(read(PANEL_JS))
    adlar = set(re.findall(r"groupMissing\.push\('feed_line_([^']+)'\)",
                           kaynak))
    assert adlar, 'panel groupMissing listesi bulunamadı — bekçi kör'
    return adlar


def test_panel_feed_grubu_uc_zorunlulariyla_ayni():
    """Ucun zorunlu saydığı her feed alt alanı panelde de zorunlu olmalı.

    Normalizasyon: uç 'length_m' der, panel 'feed_line_length_m' toplar;
    alternatifli üye (area_m2 | diameter_mm) iki tarafta da tek kayıttır.
    """
    uc = {a.replace(' | feed_line.', ' | ') for a in _uc_feed_zorunlulari()}
    panel = {a.replace(' | feed_line_', ' | ')
             for a in _panel_feed_zorunlulari()}
    assert uc == panel, (
        'Panel feed grubu uç sözleşmesinden SÜRÜKLENMİŞ:\n'
        f'  uç zorunluları : {sorted(uc)}\n'
        f'  panel zorunluları: {sorted(panel)}\n'
        'İki taraftan biri değiştiyse diğeri AYNI kalemde güncellenir.')


def test_panel_gibi_kurulan_feed_istegi_ucta_200(client):
    """CANLI kanıt: panelin kurduğu biçimdeki feed_line gövdesi 200 alır.

    Gövde stability_panel.js buildChugBody'nin ürettiği ŞEKİLDE kurulur
    (length_m + diameter_mm + mass_flow_kg_s + dp_injector_Pa; yoğunluk
    bilerek YOK — uçta yalnız yankı). 200 + inertance_included beklenir.
    """
    yanit = client.post(UC, json={
        'mode': 'chug', 'dp_ratio_j': 0.2, 'tau_s': 0.002, 'tau_c_s': 0.004,
        'feed_line': {'length_m': 1.5, 'diameter_mm': 12.0,
                      'mass_flow_kg_s': 3.4, 'dp_injector_Pa': 2.0e6},
    })
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    govde = yanit.get_json()
    assert govde['assessment']['inertance_included'] is True
    assert isinstance(govde['assessment']['tau_f_s'], float)


def test_dp_eksikken_uc_422_ve_alan_adiyla(client):
    """Negatif kanıt: dp_injector_Pa'sız grup (SÜRÜKLENMENİN ta kendisi)
    422 + makine-okur alan adı döner — panel bu alana sahip olmasaydı bu
    istek kullanıcı yolunda her seferinde patlardı."""
    yanit = client.post(UC, json={
        'mode': 'chug', 'dp_ratio_j': 0.2, 'tau_s': 0.002, 'tau_c_s': 0.004,
        'feed_line': {'length_m': 1.5, 'diameter_mm': 12.0,
                      'mass_flow_kg_s': 3.4},
    })
    assert yanit.status_code == 422
    assert 'feed_line.dp_injector_Pa' in yanit.get_json()['missing_fields']


# ===========================================================================
# 10. KULLANILABİLİRLİK BEKÇİLERİ (parti 29 A1) — ekran görüntüsünden
#     ölçülen dört kusur bir daha SESSİZ dönemesin:
#       K1 mod haritası etiket/im çakışması ("2134567T8L" yığını),
#       K2 kırpılmalar (y-ekseni başlığı + R_crit satır başları),
#       K3 varsayılan açık metin duvarları (~2400px panel),
#       K4 düşük kontrast (veri metnine dim/faint sınıfları).
#     Ölçüm yöntemi: yerleşim/marj/metin genişliği panelin KENDİ saf
#     fonksiyonlarıyla (harness probe yüzeyi) yeniden hesaplanır — Python'da
#     formül kopyası tutulmaz, sürüklenme yapısal olarak imkânsız.
# ===========================================================================
THEME_CSS = REPO_ROOT / 'hrma' / 'static' / 'css' / 'theme.css'

DETAILS_RE = re.compile(r'<details\b[^>]*>.*?</details>', re.S)
FOLD_AD_RE = re.compile(r'<details\b[^>]*data-stab-fold="([^"]+)"')


def _theme_token(ad):
    """theme.css'ten HEX jeton değeri — renkler TEK kaynaktan okunur."""
    kaynak = read(THEME_CSS)
    e = re.search(r'--' + re.escape(ad) + r':\s*(#[0-9a-fA-F]{6})', kaynak)
    assert e, f'theme.css --{ad} jetonu bulunamadı'
    return e.group(1).lower()


def _dogrusal(c):
    """sRGB kanalı → doğrusal parlaklık bileşeni (WCAG 2.x tanımı)."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _parlaklik(hexrenk):
    h = hexrenk.lstrip('#')
    r, g, b = (_dogrusal(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _kontrast(renk1, renk2):
    """WCAG kontrast oranı (L1+0.05)/(L2+0.05), L1 >= L2."""
    l1, l2 = sorted((_parlaklik(renk1), _parlaklik(renk2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _js_fonksiyon(code, ad):
    """Panel kodundan bir fonksiyonun gövdesini kabaca keser (girinti
    sözleşmesi: modül fonksiyonları 4 boşlukta başlar)."""
    b = code.find('function ' + ad + '(')
    assert b != -1, f'{ad} fonksiyonu panelde yok'
    s = code.find('\n    function ', b + 1)
    return code[b:s if s != -1 else len(code)]


def _katlar(html):
    """data-stab-fold adlarının listesi (details blokları)."""
    return FOLD_AD_RE.findall(html)


def _kat_disi(html):
    """details bloklarının DIŞINDA kalan görünüm (ana bilgi katmanı)."""
    return DETAILS_RE.sub('', html)


def _kutu(ann_x, lo, span, plot_w, genislik):
    """Bir etiketin yatay piksel kutusu (panelin yerleşim eşlemesiyle aynı:
    log10 konum → doğrusal piksel)."""
    x_px = (ann_x - lo) / span * plot_w
    return x_px - genislik / 2.0, x_px + genislik / 2.0


@needs_node
class TestKullanilabilirlikK1:
    """K1 — mod haritası etiket yerleşimi: kutular ÖLÇÜLEN metin
    genişliğiyle hesaplanır ve kesişmez (göz kararı yok)."""

    def test_yerlesim_saf_fonksiyon_cakisma_kumesinde_kesisimsiz(
            self, tmp_path, motor_hibrit):
        """Ekrandaki yığının birebir kurgusu: log eksende %3 aralıklarla
        dizilmiş '2L'..'6L','1T' + uzakta bir '1L'. Yerleşim fonksiyonu
        aynı satır + aynı kademedeki HER kutu çiftini ayrık bırakmalı ve
        çakışan küme için EN AZ bir üst kademe açmalı."""
        etiketler = ['2L', '3L', '4L', '5L', '6L', '1T']
        items = [{'x': 3000.0 * (1.03 ** i), 'row': 'screech_range',
                  'label': ad} for i, ad in enumerate(etiketler)]
        items.insert(0, {'x': 500.0, 'row': 'chug_range', 'label': '1L'})
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        probes={'layoutModeLabels': {
                            'items': items,
                            'opts': {'plotWidthPx': 420, 'fontPx': 10}}})
        yer = out['probes']['layoutModeLabels']
        assert len(yer) == len(items), 'yerleşim öğe düşürdü'
        for a, b in itertools.combinations(yer, 2):
            if a['row'] == b['row'] and a['tier'] == b['tier']:
                ayrik = (a['rightPx'] <= b['leftPx']
                         or b['rightPx'] <= a['leftPx'])
                assert ayrik, (
                    f"etiket kutuları KESİŞİYOR: {a['label']} "
                    f"[{a['leftPx']:.1f},{a['rightPx']:.1f}] ile {b['label']} "
                    f"[{b['leftPx']:.1f},{b['rightPx']:.1f}] aynı kademede")
        assert max(p['tier'] for p in yer) >= 1, (
            'çakışma kümesi tek kademede kalmış — ekrandaki yığın kusuru '
            'geri dönerdi')
        # Kademeler dikeyde de ayrık: ofset farkı en az punto + 2 px.
        kademe_ay = {}
        for p in yer:
            kademe_ay.setdefault(p['tier'], p['ayPx'])
            assert kademe_ay[p['tier']] == p['ayPx'], (
                'aynı kademeye iki farklı dikey ofset — yerleşim tutarsız')
        sirali = sorted(kademe_ay)
        for t1, t2 in zip(sirali, sirali[1:]):
            assert kademe_ay[t2] - kademe_ay[t1] >= 10 + 2, (
                'kademeler dikeyde punto kadar ayrılmıyor — etiketler '
                'düşeyde üst üste biner')

    def test_ayni_noktaya_dusen_imlerin_etiketleri_ayrisir(
            self, tmp_path, motor_hibrit):
        """İmler AYNI (bant, frekans) noktasına düşerse etiket kutuları tam
        örtüşür → yerleşim onları zorunlu olarak farklı kademelere atar.
        (İmin kendisi frekans ekseninde OYNATILMAZ: im konumu veridir,
        jitter sahte veri olurdu — ayrışma etiket katmanında.)"""
        items = [{'x': 4000.0, 'row': 'screech_range', 'label': '7L'},
                 {'x': 4000.0, 'row': 'screech_range', 'label': '1T'},
                 {'x': 800.0, 'row': 'buzz_range', 'label': '1L'}]
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        probes={'layoutModeLabels': {
                            'items': items,
                            'opts': {'plotWidthPx': 420, 'fontPx': 10}}})
        yer = {p['label']: p for p in out['probes']['layoutModeLabels']}
        assert yer['7L']['tier'] != yer['1T']['tier'], (
            'tam örtüşen imlerin etiketleri aynı kademede — okunmaz yığın')
        assert yer['7L']['ayPx'] != yer['1T']['ayPx']

    def test_gercek_mod_haritasi_etiketleri_kesisimsiz(self, tmp_path,
                                                       motor_hibrit):
        """GERÇEK hibrit koşumunun mod haritası: etiketler artık iz metni
        değil, yönlendirme çizgili Plotly notları; ölçülen kutularla
        yeniden hesaplanan kesişim testi — yatayda kesişen her çift farklı
        dikey ofsette olmalı."""
        a, L, g, mach = sonum_girdileri(motor_hibrit)
        out = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        response=sonum_yaniti(a, L, g, mach),
                        select=['chamber_acoustics', 'acoustic_modes'],
                        runs=1)
        harita = cizim(out, 'stab_map')
        assert harita, 'mod haritası çizilmemiş'
        lay = harita['layout']
        ann = lay.get('annotations') or []
        blok, _ = akustik_blok(motor_hibrit)
        assert len(ann) == len(blok['modes']), (
            'her modun bir etiket notu olmalı (ne eksik ne uydurma)')
        assert [n['text'] for n in ann] == \
            [str(m['label']) for m in blok['modes']]
        # Ana iz çift etiket ÇİZMİYOR (etiket yalnız not katmanında; iz
        # 'text' alanı hover/bekçi için motor tablosunun kendisi kalır).
        modlar = iz(harita, 'Cavity modes')
        assert modlar['mode'] == 'markers', (
            "iz 'markers+text'e dönmüş — etiketler yeniden üst üste "
            'binerdi (K1 kusuru geri geldi)')
        m = out['axisMetrics']
        plot_w = max(m['defaultPlotWidthPx'] - lay['margin']['l']
                     - lay['margin']['r'], 60)
        gen = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                        probes={'measure': [[n['text'], m['labelFontPx']]
                                            for n in ann]})['probes']['measure']
        xs = [n['x'] for n in ann]
        lo = min(xs)
        span = (max(xs) - lo) or 1
        for (i, ni), (j, nj) in itertools.combinations(enumerate(ann), 2):
            if ni['y'] != nj['y']:
                continue
            l1, r1 = _kutu(ni['x'], lo, span, plot_w, gen[i])
            l2, r2 = _kutu(nj['x'], lo, span, plot_w, gen[j])
            if min(r1, r2) - max(l1, l2) > 0:  # yatayda kesişiyorlar
                assert ni['ay'] != nj['ay'], (
                    f"{ni['text']} ile {nj['text']} yatayda kesişiyor ama "
                    'aynı dikey ofsette — okunmaz yığın geri döndü')
                assert abs(ni['ay'] - nj['ay']) >= m['labelFontPx'], (
                    'dikey ayrışma punto altında — etiketler yine değer')
        for n in ann:
            assert n['ay'] < 0, 'etiket imin üstünde durmalı (ay negatif)'
            assert n.get('showarrow') is True, (
                'yönlendirme çizgisi kalkmış — kademeli etiket imiyle '
                'eşleştirilemez')


@needs_node
class TestKullanilabilirlikK2:
    """K2 — kırpılmalar: marjlar/sütunlar ölçülen metinden türetilir."""

    @pytest.fixture(scope='class')
    def sonum_gorunumu(self, tmp_path_factory, motor_hibrit):
        a, L, g, mach = sonum_girdileri(motor_hibrit)
        yanit = sonum_yaniti(a, L, g, mach)
        out = kos_panel(tmp_path_factory.mktemp('k2_sonum'),
                        motorType='hybrid', results=motor_hibrit,
                        response=yanit,
                        select=['chamber_acoustics', 'acoustic_modes'],
                        runs=1)
        return out, yanit

    def _marj_dogrula(self, tmp_path, motor_hibrit, cagri, eksen='yaxis'):
        """Bir çizimin y-marjını panelin KENDİ fonksiyonlarıyla yeniden
        hesaplar: sarılmış başlık satırları sığmalı, margin.l birebir
        formülden çıkmalı."""
        lay = cagri['layout']
        m_ = cagri.get('axisMetrics')
        baslik = lay[eksen]['title']
        assert isinstance(baslik, dict), (
            'y-başlığı ölçülü sarma nesnesi değil — kırpılma bekçisi kör')
        satirlar_ = baslik['text'].split('<br>')
        avail = lay['height'] - lay['margin']['t'] - lay['margin']['b']
        y_degerleri = []
        for t in cagri['traces']:
            for v in (t.get('y') or []):
                if isinstance(v, (int, float)):
                    y_degerleri.append(v)
        probe = kos_panel(tmp_path, motorType='hybrid', results=motor_hibrit,
                          probes={
                              'wrapTitle': {
                                  'text': ' '.join(satirlar_),
                                  'availablePx': avail,
                                  'fontPx': m_['titleFontPx']},
                              'measure': [[s, m_['titleFontPx']]
                                          for s in satirlar_],
                              'tickWidth': {'values': y_degerleri,
                                            'fontPx': m_['tickFontPx']}})
        p = probe['probes']
        assert p['wrapTitle'] == satirlar_, (
            'çizimdeki satırlar panelin kendi sarma fonksiyonundan '
            'ayrışmış — formül iki yerde yaşayamaz')
        for s, gen in zip(satirlar_, p['measure']):
            assert gen <= avail, (
                f'başlık satırı {s!r} ölçülen genişliğiyle ({gen:.0f}px) '
                f'kullanılabilir yüksekliğe ({avail}px) sığmıyor — kırpılır')
        beklenen = math.ceil(p['tickWidth'] + m_['tickPadPx']
                             + len(satirlar_) * m_['titleFontPx']
                             * m_['lineHeight'] + m_['padPx'])
        assert lay['margin']['l'] == beklenen, (
            f"margin.l={lay['margin']['l']} ölçülen formülden ({beklenen}) "
            'ayrışmış — sabit piksel tahmini geri gelmiş olabilir')

    def test_sonum_cubugu_y_basligi_sarili_ve_marj_olculu(
            self, tmp_path, motor_hibrit, sonum_gorunumu):
        """K2a kusurunun bekçisi: '...alpha [1/s] (negative = damping)'
        başlığı eskiden tek satırda plot yüksekliğini aşıp kırpılıyordu."""
        out, _yanit = sonum_gorunumu
        cagri = cizim(out, 'stab_bars')
        assert cagri, 'sönüm çubukları çizilmemiş'
        cagri = dict(cagri, axisMetrics=out['axisMetrics'])
        baslik = cagri['layout']['yaxis']['title']
        assert '<br>' in baslik['text'], (
            'uzun y-başlığı sarılmamış — 180px kullanılabilir yüksekliğe '
            '~380px ölçülen metin sığmaz, kırpılma (K2a) geri döner')
        self._marj_dogrula(tmp_path, motor_hibrit, cagri)

    def test_notr_egri_y_basligi_sarili_ve_marj_olculu(self, tmp_path,
                                                       motor_hibrit,
                                                       motor_sivi):
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        out = kos_panel(tmp_path, motorType='liquid',
                        results=motor_sivi,
                        response=chug_yaniti(dp, tau, tau_c),
                        select=['chamber_acoustics', 'combustion_stability'],
                        runs=1)
        cagri = cizim(out, 'stab_neutral')
        assert cagri, 'nötr eğri çizilmemiş'
        cagri = dict(cagri, axisMetrics=out['axisMetrics'])
        assert '<br>' in cagri['layout']['yaxis']['title']['text']
        # Aynı tmp_path yeniden kullanılabilir: kos_panel dosyaları sıralı
        # koşumda üstüne yazar, çakışma yok.
        self._marj_dogrula(tmp_path, motor_hibrit, cagri)

    def test_rcrit_satir_baslari_olculu_min_genislik_ile_kirpilmaz(
            self, tmp_path, motor_hibrit, sonum_gorunumu):
        """K2b kusurunun bekçisi: '1L @ 959.391 Hz' satır başları dar
        sütunda kırpılıyor/taşıyordu. Sol sütun artık en uzun başlığın
        ÖLÇÜLEN genişliği kadar yer ayırıp tek satırda kalır."""
        out, _yanit = sonum_gorunumu
        html = gorunum(out)
        blok = re.search(r'<div data-stab-block="rcrit-table">(.*?)</div>',
                         html, re.S)
        assert blok, 'R_crit tablosu kayıp'
        hucreler = re.findall(r'<tr><td style="([^"]*)">([^<]*)</td>',
                              blok.group(1))
        assert hucreler, 'R_crit satır başı hücresi yok'
        genislikler = set()
        etiketler = []
        for stil, metin in hucreler:
            assert 'white-space:nowrap' in stil, (
                f'satır başı {metin!r} sarılabilir kalmış — dar sütunda '
                'kırpılma/karışma (K2b) geri döner')
            e = re.search(r'min-width:(\d+)px', stil)
            assert e, f'satır başı {metin!r} ölçülü min-width taşımıyor'
            genislikler.add(int(e.group(1)))
            etiketler.append(metin)
            assert ' @ ' in metin and metin.endswith(' Hz')
        assert len(genislikler) == 1, 'sütun tek genişlikte olmalı'
        m = out['axisMetrics']
        olcumler = kos_panel(tmp_path, motorType='hybrid',
                             results=motor_hibrit,
                             probes={'measure': [[t, m['kvFontPx']]
                                                 for t in etiketler]}
                             )['probes']['measure']
        assert genislikler.pop() == math.ceil(max(olcumler)), (
            'min-width en uzun başlığın ölçülen genişliğinden ayrışmış — '
            'sabit piksel tahmini yasak')


@needs_node
class TestKullanilabilirlikK3:
    """K3 — metin duvarları varsayılan KAPALI <details> içinde; içerik
    DOM'da AYNEN durur, ana bilgi (rozet + sayı tabloları) katlanmaz."""

    @pytest.fixture(scope='class')
    def chug_gorunumu(self, tmp_path_factory, motor_sivi):
        dp, tau, tau_c = sivi_chug_girdileri(motor_sivi)
        yanit = chug_yaniti(dp, tau, tau_c)
        out = kos_panel(tmp_path_factory.mktemp('k3_chug'),
                        motorType='liquid', results=motor_sivi,
                        response=yanit,
                        select=['chamber_acoustics', 'combustion_stability'],
                        runs=1)
        return out, yanit

    @pytest.fixture(scope='class')
    def sonum_gorunumu(self, tmp_path_factory, motor_hibrit):
        a, L, g, mach = sonum_girdileri(motor_hibrit)
        yanit = sonum_yaniti(a, L, g, mach)
        out = kos_panel(tmp_path_factory.mktemp('k3_sonum'),
                        motorType='hybrid', results=motor_hibrit,
                        response=yanit,
                        select=['chamber_acoustics', 'acoustic_modes'],
                        runs=1)
        return out, yanit

    def test_chug_metin_duvarlari_varsayilan_kapali(self, chug_gorunumu):
        out, yanit = chug_gorunumu
        html = gorunum(out)
        adlar = set(_katlar(html))
        beklenen = {'not-modelled', 'assumptions', 'inputs', 'basis',
                    'suggestions'}
        if yanit['assessment'].get('classical_rule_cross_check'):
            beklenen.add('classical-basis')
        assert beklenen <= adlar, (
            f'katlanması gereken beyan blokları eksik: {beklenen - adlar}')
        assert not re.search(r'<details\b[^>]*\bopen\b', html), (
            'details AÇIK basılmış — metin duvarı (K3) geri döndü')
        # İçerik DOM'da AYNEN duruyor (beyan disiplini bozulmadı).
        for isaret in ('data-stab-block="not-modelled"',
                       'data-stab-block="assumptions"',
                       'data-stab-block="inputs"'):
            assert isaret in html, f'katlama içeriği düşürmüş: {isaret}'

    def test_chug_ana_bilgi_katlanmaz(self, chug_gorunumu):
        out, yanit = chug_gorunumu
        html = gorunum(out)
        dis = _kat_disi(html)
        assert 'data-stab-badges' in dis, 'rozet şeridi katlanmış'
        assert 'data-stab-block="assessment"' in dis, (
            'assessment sayı tablosu katlanmış — ana bilgi görünür kalmalı')
        assert 'data-stab-block="classical"' in dis, (
            'klasik kural SAYI tablosu katlanmış (yalnız yorumu katlanır)')
        # Hüküm rozeti katlanmamış görünümde kapsamıyla duruyor.
        assert any('UNSTABLE — feed-coupled chug' in t
                   for _k, t in rozetler(dis))
        if yanit['skipped_points']:
            assert 'data-stab-block="skipped"' in dis, (
                'atlanan nokta beyanı katlanmış — dürüstlük beyanı görünür '
                'kalmalı')

    def test_damping_metin_duvarlari_varsayilan_kapali(self, sonum_gorunumu):
        out, _yanit = sonum_gorunumu
        html = gorunum(out)
        adlar = set(_katlar(html))
        assert {'nozzle-basis', 'budget-basis', 'not-modelled',
                'threshold-basis'} <= adlar, (
            f'sönüm görünümünde katlanmamış beyan kalmış: {adlar}')
        assert not re.search(r'<details\b[^>]*\bopen\b', html)
        dis = _kat_disi(html)
        for isaret in ('data-stab-block="nozzle"', 'data-stab-block="budget"',
                       'data-stab-block="rcrit-table"'):
            assert isaret in dis, f'sayı tablosu katlanmış: {isaret}'
        assert 'R_crit' in dis, 'R_crit değerleri ana katmandan düşmüş'

    def test_katlama_ozetleri_veriden(self, sonum_gorunumu):
        """<summary> özeti UYDURMA değil: kalem sayısı ve ilk adlar yanıtın
        not_modelled sözlüğünün kendisinden."""
        out, yanit = sonum_gorunumu
        html = gorunum(out)
        kat = re.search(r'<details\b[^>]*data-stab-fold="not-modelled"[^>]*>'
                        r'\s*<summary\b[^>]*>(.*?)</summary>', html, re.S)
        assert kat, 'not-modelled katlama bloğu yok'
        ozet = kat.group(1)
        kalemler = list(yanit['budget']['not_modelled'])
        assert f'{len(kalemler)} item(s):' in ozet, (
            'özet kalem sayısını veriden taşımıyor')
        for ad in kalemler[:3]:
            kisa = ad if len(ad) <= 42 else ad[:42] + '…'
            assert kisa in ozet, f'özet ilk kalemleri adıyla saymıyor: {ad}'


class TestKontrastK4:
    """K4 — WCAG kontrastı theme.css jetonlarından HESAPLANIR (göz kararı
    yasak): veri metni çifti >= 7:1, açıklama çifti >= 4.5:1."""

    def test_wcag_kontrast_theme_jetonlarindan(self):
        zemin = _theme_token('hd-bg1')       # panel zemini #0a1322
        veri = _theme_token('hd-ink')        # veri metni
        aciklama = _theme_token('hd-ink-dim')  # ikincil açıklama
        k_veri = _kontrast(veri, zemin)
        k_aciklama = _kontrast(aciklama, zemin)
        assert k_veri >= 7.0, (
            f'veri metni kontrastı {k_veri:.2f} < 7:1 ({veri} / {zemin})')
        assert k_aciklama >= 4.5, (
            f'açıklama kontrastı {k_aciklama:.2f} < 4.5:1 '
            f'({aciklama} / {zemin})')

    def test_veri_metni_ink_aciklama_dim(self, panel_code):
        """K4 kusurunun bekçisi: R_crit/assessment tablolarının hücreleri
        (kvTable) --hd-ink-dim ile basılıyordu (5.9:1). Veri hücrelerine
        artık yalnız --hd-ink; dim yalnız açıklama metninde (basisText)."""
        kv = _js_fonksiyon(panel_code, 'kvTable')
        assert kv.count('var(--hd-ink, #cfe8f2)') >= 2, (
            'kvTable hücreleri --hd-ink değil — veri metni soluklaştı')
        assert '--hd-ink-dim' not in kv and '--hd-ink-faint' not in kv, (
            'veri hücresine soluk sınıf dönmüş (K4 kusuru geri geldi)')
        bt = _js_fonksiyon(panel_code, 'basisText')
        assert '--hd-ink-dim' in bt, (
            'açıklama metni dim olmalı (hiyerarşi: veri > açıklama)')
        # Çizim içi HEX ikizleri theme jetonlarıyla birebir (Plotly CSS
        # var() çözmediği için paneldeki kopyalar buradan kilitlenir).
        assert _theme_token('hd-ink') == '#cfe8f2'
        assert _theme_token('hd-ink-dim') == '#7d97a5'
        assert "INK_HEX = '#cfe8f2'" in panel_code
        assert "INK_DIM_HEX = '#7d97a5'" in panel_code


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
