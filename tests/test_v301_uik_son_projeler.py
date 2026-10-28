"""V301/UI-K kalem 3 (NK-26 ek) — ana sayfa "Son Projeler".

Son kullanıcı: "liste kaydetmeden güncelleniyor; hangi koşu, hangi Isp belli
değil". ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ui-k/son_projeler_once.json,
taban 2facae6a0 dosyaları ctx.route ile):
  * kaydetmeden dönünce liste DEĞİŞMİYOR (gözlem açılıştaki örnek
    tazelemesinden), ama kaydedilmemiş son hesap hiçbir yerde görünmüyordu;
  * Isp'nin tabanı (deniz seviyesi / tasarım noktası) ve özetin hangi
    kayıttan geldiği yazmıyordu;
  * katı sayfasından az önce kaydedilen proje "daha eski bir sürümle
    hesaplandı" diye işaretleniyordu (katı/sıvı sayfası window'a sürüm
    yazmıyor, özet damgasız kaydediliyordu).
Bekçi project_bar.js gövdelerini söküp gerçek sözlükle node'da koşar.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')

HARNESS = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[1];
const src = fs.readFileSync(ROOT + '/hrma/static/js/project_bar.js', 'utf8');
function govde(ad) {
    const m = new RegExp('(?:async\\s+)?function\\s+' + ad + '\\s*\\(').exec(src);
    if (!m) throw new Error(ad + ' bulunamadı');
    let d = 0; const j = src.indexOf('{', m.index + m[0].length - 1);
    for (let k = j; k < src.length; k++) {
        if (src[k] === '{') d++;
        else if (src[k] === '}') { d--; if (!d) return src.slice(m.index, k + 1); }
    }
    throw new Error(ad + ' kapanmadı');
}
function dugum(tag) {
    return { tag, cocuk: [], style: { cssText: '' }, attrs: {}, className: '', href: '', id: '',
        textContent: '',
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return this.attrs[k]; },
        addEventListener() {},
        appendChild(c) { this.cocuk.push(c); return c; },
        insertBefore(c) { this.cocuk.push(c); return c; },
        querySelector() { return null; } };
}
function metin(d) { return (d.textContent || '') + d.cocuk.map(metin).join(''); }
async function kos(lang, depoIcerik, surumOzniteligi) {
    const kap = dugum('div');
    const depo = Object.assign({}, depoIcerik);
    const sb = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout,
        JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error, Promise,
        parseFloat, parseInt, isNaN, isFinite };
    sb.window = sb;
    sb.localStorage = { getItem: (k) => (k in depo ? depo[k] : null),
                        setItem: (k, v) => { depo[k] = String(v); },
                        removeItem: (k) => { delete depo[k]; } };
    const surumEl = dugum('section');
    if (surumOzniteligi) surumEl.setAttribute('data-hrma-version', surumOzniteligi);
    sb.document = { readyState: 'loading', documentElement: { setAttribute() {} }, addEventListener() {},
        querySelectorAll: () => [], getElementById: () => null, createElement: dugum,
        querySelector: (s) => (s === '.container' ? kap
                               : (s === '[data-hrma-version]' && surumOzniteligi ? surumEl : null)) };
    vm.createContext(sb);
    for (const f of ['i18n.js', 'i18n_common.js']) {
        vm.runInContext(fs.readFileSync(ROOT + '/hrma/static/js/' + f, 'utf8'), sb, { filename: f }); }
    sb.I18N.setLang(lang);
    const govdeler = ['T', 'TF', 'nf', 'summaryMini', 'serializeResultsSummary', 'buildRecentStrip',
                      'unsavedRunClear', 'unsavedRunRecordOnLeave'].map(govde).join('\n');
    vm.runInContext(
        'var TYPE_PATH = { liquid: "/liquid", solid: "/solid", hybrid: "/hybrid" };\n'
        + 'var UNSAVED_RUN_LS_KEY = "hrma.project.unsavedRun";\n'
        + 'var motorType = "solid";\n'
        + 'var state = { name: "Benim Motorum", savedResults: null };\n'
        + 'function srv(s) { return s; }\n'
        + 'async function apiList() { return [{ name: "a", motor_type: "hybrid",'
        + ' updated_at: "2026-10-14T14:51:51", results_summary: { thrust_N: 3000, isp_s: 236.034 } }]; }\n'
        + govdeler, sb, { filename: 'project_bar_parca.js' });
    const out = {};
    out.mini = {
        hibrit: vm.runInContext('summaryMini({isp_s: 236.034}, "hybrid")', sb),
        kati: vm.runInContext('summaryMini({isp_s: 125.4}, "solid")', sb),
        taban_kayitta: vm.runInContext('summaryMini({isp_s: 125.4, isp_basis: "design_point"}, "solid")', sb),
        bilinmiyor: vm.runInContext('summaryMini({isp_s: 125.4})', sb),
    };
    // Kaydedilmemiş hesap: sonuç var, kaydedilmedi → ayrılırken yazılır.
    vm.runInContext('window.currentResults = { isp_sea_level: 125.43, total_impulse: 2960.3,'
                    + ' thrust_curve: { thrust: [1, 1499.7, 2] } }; unsavedRunRecordOnLeave();', sb);
    out.kayit = depo['hrma.project.unsavedRun'] ? JSON.parse(depo['hrma.project.unsavedRun']) : null;
    await vm.runInContext('buildRecentStrip()', sb);
    const bolum = kap.cocuk[0];
    out.serit_liste = bolum.cocuk[1].cocuk.map(metin);
    out.serit_baslik2 = bolum.cocuk[2] ? bolum.cocuk[2].textContent : null;
    out.serit_kaydedilmemis = bolum.cocuk[3] ? metin(bolum.cocuk[3]) : null;
    // Kaydedilince silinir; kaydedilmiş sonuç ayrılırken yeniden yazılmaz.
    vm.runInContext('state.savedResults = window.currentResults; unsavedRunClear(); unsavedRunRecordOnLeave();', sb);
    out.kayit_sonra = depo['hrma.project.unsavedRun'] || null;
    return out;
}
(async function () {
    const out = {
        en: await kos('en', {}, '3.0.1'),
        tr: await kos('tr', {}, '3.0.1'),
        surumsuz: await kos('en', {}, null),
        bozuk: await kos('en', { 'hrma.project.unsavedRun': '{bozuk' }, '3.0.1'),
    };
    process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""


@pytest.fixture(scope='module')
def olcum():
    if NODE is None:
        pytest.skip('node yok')
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (tests/test_node_cagri_sozlesmesi.py);
    # stdin koşusunda process.argv yalnız [node] — değer 'use strict'
    # önsözünden SONRA aynı konuma yazılır.
    onsoz = "'use strict';"
    assert HARNESS.count(onsoz) == 1
    betik = HARNESS.replace(onsoz, onsoz + '\nprocess.argv = [process.argv[0], %s];'
                            % json.dumps(str(KOK)))
    r = subprocess.run([NODE], input=betik, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout)


def test_isp_tabani_yazilir(olcum):
    en, tr = olcum['en']['mini'], olcum['tr']['mini']
    assert en['hibrit'] == 'Isp 236.0 s (design point)'
    assert en['kati'] == 'Isp 125.4 s (sea level)'
    assert tr['kati'] == 'Isp 125,4 s (deniz seviyesi)'
    assert tr['hibrit'] == 'Isp 236,0 s (tasarım noktası)'
    assert en['taban_kayitta'] == 'Isp 125.4 s (design point)'   # kayıt kazanır
    assert en['bilinmiyor'] == 'Isp 125.4 s'                    # uydurma etiket yok


def test_kaydedilmemis_hesap_ayri_ve_adiyla(olcum):
    for dil, beklenen in (('en', 'not saved'), ('tr', 'kaydedilmedi')):
        o = olcum[dil]
        k = o['kayit']
        assert k['name'] == 'Benim Motorum' and k['motor_type'] == 'solid'
        assert k['summary']['isp_basis'] == 'sea_level'
        assert k['summary']['computed_with_version'] == '3.0.1'
        # Liste YALNIZ kayıtlı proje; kaydedilmemiş hesap ona karışmaz.
        assert len(o['serit_liste']) == 1 and 'Benim Motorum' not in o['serit_liste'][0]
        assert o['serit_kaydedilmemis'].startswith('Benim Motorum [')
        assert o['serit_kaydedilmemis'].endswith(beklenen)
        assert o['kayit_sonra'] is None
    assert olcum['en']['serit_baslik2'] == 'Last calculation (not saved)'
    assert olcum['tr']['serit_baslik2'] == 'Son hesap (kaydedilmedi)'


def test_liste_kaydetme_tarihini_yazar(olcum):
    assert olcum['en']['serit_liste'][0].endswith('· saved 2026-10-14 14:51')
    assert olcum['tr']['serit_liste'][0].endswith('· kayıt: 2026-10-14 14:51')


def test_surum_damgasi_sayfa_ozniteliginden(olcum):
    # Katı/sıvı sayfası window'a sürüm yazmıyor: data-hrma-version'dan okunur;
    # o da yoksa damga UYDURULMAZ.
    assert olcum['en']['kayit']['summary']['computed_with_version'] == '3.0.1'
    assert 'computed_with_version' not in olcum['surumsuz']['kayit']['summary']


def test_bozuk_kayit_listeyi_bozmaz(olcum):
    o = olcum['bozuk']
    assert len(o['serit_liste']) == 1
    # bozuk kayıt okunmadı; ayrılırken yazılan YENİ kayıt gösterilir
    assert o['serit_kaydedilmemis'].endswith('not saved')


def test_iki_dilde_anahtarlar():
    js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(encoding='utf-8')
    for k in ('proj.ispBasisSeaLevel', 'proj.ispBasisDesign', 'proj.savedAt',
              'proj.unsavedRunTitle', 'proj.notSaved', 'proj.unsavedRunNote'):
        assert js.count("'" + k + "':") == 2, k
