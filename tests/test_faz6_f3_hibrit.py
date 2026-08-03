"""Faz 6 / F3-hibrit — ``templates/advanced.html`` bekçileri.

Tarayıcı denetiminin ``/hybrid`` sayfasına düşen iki kalemini kalıcı olarak
kilitler. Her testin başında ÖLÇÜLEN değer yazılıdır; hiçbiri "böyle olmalı"
varsayımı değildir.

Kapsanan kalemler
-----------------
T09 (CİDDİ) ``updateCalculatedImpulse`` toplam impulsü ``toLocaleString()``
    ile basıyordu. Argümansız çağrı sayfanın dilini DEĞİL işletim sisteminin
    yerelini kullanır. Ölçüldü (2026-08-03, Playwright ``locale='tr-TR'``,
    ``document.documentElement.lang === 'en'``):

        itki × süre        gerçek        ekranda
        1000 N × 10 s      10000 N·s     "10.000 N⋅s"
        5000 N × 30 s     150000 N·s     "150.000 N⋅s"
         250 N ×  4 s       1000 N·s     "1.000 N⋅s"

    İngilizce okuyan kullanıcı için bunlar 10 / 150 / 1 demektir: toplam
    impuls 1000 KAT yanlış okunur. Nokta binlik ayırıcı kullanan her yerelde
    (tr, de, es, it, nl, pt) yeniden üretilir.

    Düzeltme, projenin kendi politikasını uygular: ``I18N.number`` binlik
    ayırıcıyı BİLEREK kullanmaz (i18n.js:289-291) ve sayfanın tasarım raporu
    da aynı biçimi kullanır (``reportNum(perf.total_impulse_Ns, 0)``,
    app.js:844).

T12 (CİDDİ) Trajectory Analysis paneli, motorun KENDİ özgül itkisini ihlal
    eden bir uçuş simüle ediyordu. Ölçüldü (2026-08-03, /hybrid, varsayılan
    hibrit motor; Calculate ÖNCESİ ve SONRASI alanlar aynı kaldı):

        initial_mass 50 kg, final_mass 25 kg  ->  yörünge itici 25 kg
        motorun raporladığı itici              ->  5,463085 kg
        ima edilen Isp = F/((Δm/t_b)·g0) = 40,79 s
        motorun ilan ettiği Isp               =  185,59 s   (4,55 KAT ihlal)

    Uçtan ölçülen görünür sonuç (POST /api/trajectory-analysis):

        eski girdiler (50/25 kg, 0,1 m²)  -> apoje 1090,2 m, v_max 127,42 m/s
        yeni girdiler (30,463/25, 0,0177) -> apoje 3039,8 m, v_max 228,77 m/s

    1090 m / 127,4 m/s değerleri denetim raporundaki sayılarla birebir aynı,
    yani ölçüm doğru yeri gösteriyor.

    Kök neden: ``initial_mass`` bağımsız bir kullanıcı girdisiydi. Fizik onu
    bağımlı kılar — kalkış kütlesi kuru kütle ile motorun TAŞIDIĞI itici
    kütlesinin toplamıdır. Düzeltme bu ilişkiyi kurar; itici kütlesi
    uydurulmaz, motor sonucundan okunur.

    Referans alan BİLEREK otomatik doldurulmaz: aracın alın kesiti motor
    verisinden hesaplanamaz. Varsayılan, alanın kendi yardım metninde zaten
    belgelenen örneğe çekildi (100000 mm² = Ø356,8 mm -> 17671 mm² = Ø150 mm;
    motorun oda çapı Ø79,87 mm, yani oran 4,47 -> 1,88) ve alanın altına her
    değişiklikte ima edilen gövde çapını ölçen bir not eklendi.

Yöntem
------
Şablonun ``<script>`` blokları gerçekten node içinde, sahte bir DOM ve
GERÇEK ``i18n.js`` ile çalıştırılır. Sınanan şey "kodda yazıyor mu" değil,
"çalışınca ne yapıyor": alanlara hangi değer yazılıyor, uca giden gövde ne
oluyor, hangi metin basılıyor. Metne bakan regex testleri yalnız yerel-bağımsız
bir ikinci hat olarak eklenmiştir.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ADVANCED = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'

NODE = shutil.which('node')

# /calculate'ten ÖLÇÜLEN gerçek motor sonucu (2026-08-03, varsayılan hibrit:
# itki 1000 N, yanma 10 s, O/F 2,5, Pc 20 bar, HTPB/N2O).
MOTOR_ITICI_KG = 5.463085263479914
MOTOR_ISP_S = 185.5938491979431
MOTOR_ODA_CAPI_M = 0.0798694395392226

pytestmark = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


# ===========================================================================
# node koşum düzeneği
# ===========================================================================
#
# advanced.html'in inline JS'i tek parça hâlinde bir vm bağlamında çalıştırılır.
# DOM taklidi asgaridir: düzen değil VERİ AKIŞI sınanır. ``i18n.js`` gerçek
# dosyadan yüklenir — çeviri ve sayı biçimi taklit EDİLMEZ, yoksa test kendi
# uydurduğu biçimi doğrulamış olurdu.
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [repoRoot, senaryo, dil, tplOverride] = process.argv.slice(2);
const TPL = tplOverride || path.join(repoRoot, 'hrma', 'templates', 'advanced.html');
const I18N_JS = path.join(repoRoot, 'hrma', 'static', 'js', 'i18n.js');
const I18N_ADV_JS = path.join(repoRoot, 'hrma', 'static', 'js', 'i18n_advanced.js');

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this._cls = {};
    const self = this;
    this.classList = {
        contains: function (c) { return !!self._cls[c]; },
        add: function (c) { self._cls[c] = true; },
        remove: function (c) { delete self._cls[c]; }
    };
    this._attrs = {};
    this.textContent = '';
    this.innerHTML = '';
    this.value = '';
    this.readOnly = false;
    this.checked = false;
    this.disabled = false;
    this._listeners = {};
    this.parentNode = null;
}
El.prototype.appendChild = function (c) { c.parentNode = this; this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { c.parentNode = this; this.children.push(c); return c; };
El.prototype.remove = function () {};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.hasAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k);
};
El.prototype.removeAttribute = function (k) { delete this._attrs[k]; };
El.prototype.addEventListener = function (t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn);
};
El.prototype.removeEventListener = function () {};
El.prototype.dispatchEvent = function (ev) {
    const l = this._listeners[(ev && ev.type) || ''] || [];
    for (let i = 0; i < l.length; i++) { l[i].call(this, ev); }
    return true;
};
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };

const byId = {};
function getEl(id) {
    if (!byId[id]) {
        byId[id] = new El('div');
        byId[id].id = id;
        byId[id].parentNode = new El('div');   // notun ekleneceği kap
    }
    return byId[id];
}

const tplText = fs.readFileSync(TPL, 'utf8');
function tplValue(id) {
    const m = tplText.match(new RegExp('<input[^>]*id="' + id + '"[^>]*>', 'i'));
    if (!m) { return null; }
    const v = m[0].match(/value="([^"]*)"/i);
    return v ? v[1] : null;
}

// Sayfanın GERÇEK başlangıç değerleri şablondan okunur (test kendi
// varsayılanını uydurmaz).
getEl('initial_mass').value = tplValue('initial_mass') || '';
getEl('final_mass').value = tplValue('final_mass') || '';
getEl('reference_area').value = tplValue('reference_area') || '';
getEl('thrust').value = '5000';
getEl('burn_time').value = '30';
getEl('thrust_time_design').classList.add('active');

const domReady = {};
const documentStub = {
    head: new El('head'),
    body: new El('body'),
    documentElement: new El('html'),
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    createTextNode: function () { return new El('#text'); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementsByTagName: function () { return []; },
    getElementById: function (id) { return getEl(id); },
    addEventListener: function (t, fn) { (domReady[t] = domReady[t] || []).push(fn); },
    removeEventListener: function () {},
    dispatchEvent: function () { return true; },
    cookie: ''
};

const store = {};
const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {},
               info: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: function () { return 0; }, clearInterval: function () {},
    fetch: function () {
        return Promise.resolve({ ok: true, status: 200,
            text: function () { return Promise.resolve('{}'); },
            json: function () { return Promise.resolve({}); } });
    },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, Promise: Promise, Error: Error, Date: Date,
    RegExp: RegExp, Map: Map, Set: Set, WeakMap: WeakMap,
    isFinite: isFinite, isNaN: isNaN, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub,
    navigator: { language: 'tr-TR', languages: ['tr-TR'] },
    localStorage: {
        getItem: function (k) {
            return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null;
        },
        setItem: function (k, v) { store[k] = String(v); },
        removeItem: function (k) { delete store[k]; }
    },
    CustomEvent: function (t, o) { this.type = t; this.detail = o && o.detail; },
    Event: function (t) { this.type = t; },
    addEventListener: function () {},
    Plotly: { newPlot: function () {}, purge: function () {}, react: function () {} }
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.self = sandbox;
vm.createContext(sandbox);

if (dil === 'tr') { store['hrma_lang'] = 'tr'; }
// Gerçek çevirmen ve GERÇEK sayfa sözlüğü yüklenir; çeviri taklit EDİLMEZ.
// Sözlük olmadan her anahtar İngilizce yedeğe düşerdi ve test kendi
// uydurduğu metni doğrulamış olurdu.
vm.runInContext(fs.readFileSync(I18N_JS, 'utf8'), sandbox, { filename: 'i18n.js' });
vm.runInContext(fs.readFileSync(I18N_ADV_JS, 'utf8'), sandbox,
                { filename: 'i18n_advanced.js' });

// app.js bu iki global'i sağlar. Sarmalayıcıların özgün işlevi YUTMADIĞINI
// ölçebilmek için önceden tanımlanır ve çağrıları sayılır.
const ozgunCagri = { display: 0, traj: 0 };
sandbox.displayCalculationResults = function () { ozgunCagri.display++; };
sandbox.calculateTrajectory = function () { ozgunCagri.traj++; return 'ozgun'; };

const bloklar = tplText.match(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g) || [];
const kod = bloklar
    .map(function (b) {
        return b.replace(/^<script[^>]*>/, '').replace(/<\/script>$/, '');
    })
    .join('\n;\n');

const hatalar = [];
try {
    vm.runInContext(kod, sandbox, { filename: 'advanced.html(inline)' });
} catch (e) {
    hatalar.push('inline: ' + String(e && e.message).slice(0, 300));
}
// Panel betikleri (TransientPanel vb.) bu bağlamda yüklü değildir; onların
// DOMContentLoaded dinleyicisi hata verir ve YOK SAYILIR — sınanan blok
// ayrı bir dinleyicidir.
(domReady['DOMContentLoaded'] || []).forEach(function (fn) {
    try { fn(); } catch (e) { hatalar.push('DCL: ' + String(e && e.message).slice(0, 160)); }
});

const cikti = { hatalar: hatalar, lang: sandbox.I18N && sandbox.I18N.lang };

// ---- T09 -----------------------------------------------------------------
if (typeof sandbox.updateCalculatedImpulse !== 'function') {
    cikti.T09_hata = 'updateCalculatedImpulse tanımlı değil';
} else {
    sandbox.updateCalculatedImpulse();
    cikti.T09_5000x30 = getEl('calculated_impulse').textContent;
    getEl('thrust').value = '250'; getEl('burn_time').value = '4';
    sandbox.updateCalculatedImpulse();
    cikti.T09_250x4 = getEl('calculated_impulse').textContent;
    getEl('thrust').value = '1000'; getEl('burn_time').value = '10';
    sandbox.updateCalculatedImpulse();
    cikti.T09_1000x10 = getEl('calculated_impulse').textContent;
}

// ---- T12 -----------------------------------------------------------------
// Motor sonucu: /calculate'ten ÖLÇÜLEN gerçek değerler.
const MOTOR = { propellant_mass_total: 5.463085263479914, thrust: 1000,
                burn_time: 10, isp: 185.5938491979431,
                chamber_diameter: 0.0798694395392226 };

// (a) Motor sonucu YOKKEN alana dokunulmamalı.
cikti.motorsuz = { initial_mass: getEl('initial_mass').value,
                   readOnly: getEl('initial_mass').readOnly,
                   not: getEl('initial_mass_note').textContent,
                   reference_area: getEl('reference_area').value };

if (senaryo !== 'motorsuz') {
    // (b) Hesap sonucu geldi: app.js:176 displayCalculationResults'ı çağırır.
    sandbox.currentResults = { motor: MOTOR };
    sandbox.window.currentResults = sandbox.currentResults;
    try { sandbox.displayCalculationResults({ motor: MOTOR }); }
    catch (e) { hatalar.push('display: ' + String(e && e.message).slice(0, 200)); }

    const mi = parseFloat(getEl('initial_mass').value);
    const mf = parseFloat(getEl('final_mass').value);
    const itici = mi - mf;
    cikti.esitlenmis = {
        initial_mass: getEl('initial_mass').value,
        final_mass: getEl('final_mass').value,
        readOnly: getEl('initial_mass').readOnly,
        not: getEl('initial_mass_note').textContent,
        reference_area: getEl('reference_area').value,
        ref_not: getEl('reference_area_note').textContent,
        ref_renk: getEl('reference_area_note').style.color,
        yorunge_itici_kg: itici,
        ima_edilen_isp_s: MOTOR.thrust / ((itici / MOTOR.burn_time) * 9.80665),
        ozgun_display_cagri: ozgunCagri.display
    };

    // (c) Kuru kütle değişince kalkış kütlesi yeniden türetilmeli.
    getEl('final_mass').value = '12';
    getEl('final_mass').dispatchEvent({ type: 'input' });
    cikti.kuru12_initial = getEl('initial_mass').value;
    getEl('final_mass').value = tplValue('final_mass') || '25';
    getEl('final_mass').dispatchEvent({ type: 'input' });

    // (d) Referans alan tutarlılık eşikleri.
    const refOlc = function (v) {
        getEl('reference_area').value = v;
        getEl('reference_area').dispatchEvent({ type: 'input' });
        return { not: getEl('reference_area_note').textContent,
                 renk: getEl('reference_area_note').style.color,
                 deger: getEl('reference_area').value };
    };
    cikti.ref_100000 = refOlc('100000');
    cikti.ref_3000 = refOlc('3000');
    cikti.ref_varsayilan = refOlc(tplValue('reference_area') || '17671');

    // (e) Yörünge düğmesi: istek gitmeden ÖNCE eşitleme. Alan kirletilir,
    //     sarmalayıcının onu motora göre düzeltmesi beklenir.
    getEl('initial_mass').value = '999';
    cikti.traj_donus = sandbox.calculateTrajectory();
    cikti.traj_ozgun_cagri = ozgunCagri.traj;
    cikti.traj_sonrasi_initial = getEl('initial_mass').value;
}

console.log(JSON.stringify(cikti));
"""


def _kos(tmp_path, senaryo='tam', dil='en', locale_env=None, tpl=None):
    """Düzeneği node ile koşturur, JSON ölçümü döndürür."""
    harness = tmp_path / 'faz6_f3_harness.js'
    harness.write_text(HARNESS_JS, encoding='utf-8')
    argv = [NODE, str(harness), str(REPO_ROOT), senaryo, dil]
    if tpl is not None:
        argv.append(str(tpl))
    env = dict(os.environ)
    if locale_env:
        env['LANG'] = locale_env
        env['LC_ALL'] = locale_env
    r = subprocess.run(argv, capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 0, 'node koşumu hata verdi:\n' + r.stderr
    satirlar = [s for s in r.stdout.strip().splitlines() if s.strip()]
    assert satirlar, 'koşum çıktı üretmedi:\n' + r.stdout + r.stderr
    veri = json.loads(satirlar[-1])
    # Yalnız panel betiklerinin eksikliğinden doğan DCL hatası kabul edilir.
    agir = [h for h in veri.get('hatalar', []) if not h.startswith('DCL: ')]
    assert not agir, 'inline JS çalışırken hata: %r' % (agir,)
    return veri


@pytest.fixture(scope='module')
def olcum(tmp_path_factory):
    return _kos(tmp_path_factory.mktemp('f3'), locale_env='tr_TR.UTF-8')


def _oku():
    return ADVANCED.read_text(encoding='utf-8')


def _yorumsuz(js):
    """Satır yorumlarını atar.

    Bu depoda düzeltmelerin GEREKÇESİ yorumda yazılır; gerekçe çoğu zaman
    kaldırılan çağrının adını anar (ör. "toLocaleString yerine ..."). Yorumu
    ayıklamayan bir iddia denetimi kendi açıklamasını kusur sanır — aynı hata
    7c8a50f'te derleme artığı için düzeltilmişti."""
    return re.sub(r'//[^\n]*', '', js)


# ===========================================================================
# T09 — toplam impuls, işletim sistemi yereline bırakılmaz
# ===========================================================================

@pytest.mark.parametrize('anahtar,beklenen,gercek_Ns', [
    ('T09_1000x10', '10000 N⋅s', 10000),
    ('T09_5000x30', '150000 N⋅s', 150000),
    ('T09_250x4', '1000 N⋅s', 1000),
])
def test_t09_impuls_metni_binlik_ayirici_tasimaz(olcum, anahtar, beklenen, gercek_Ns):
    """Düzeltme öncesi ÖLÇÜLEN (LANG=tr_TR, sayfa dili 'en'):
        10000 -> "10.000 N⋅s" | 150000 -> "150.000 N⋅s" | 1000 -> "1.000 N⋅s"
    Yani gösterilen sayı gerçeğin 1/1000'i gibi okunuyordu. Beklenen davranış
    ayırıcısız gösterimdir — tasarım raporu da (app.js:844) aynı biçimi kullanır.
    """
    assert olcum[anahtar] == beklenen, (
        '%s: %r bekleniyordu, %r ölçüldü' % (anahtar, beklenen, olcum[anahtar]))
    sayi = olcum[anahtar].split(' ')[0]
    assert '.' not in sayi and ',' not in sayi, (
        'toplam impulste ayırıcı var: %r — İngilizce/Türkçe okuyucu için '
        'değer belirsizleşir' % olcum[anahtar])
    assert float(sayi) == float(gercek_Ns)


def test_t09_turkce_modda_da_ayni_rakamlar(tmp_path):
    """Dil değişimi SAYIYI değiştirmemeli; yalnız ondalık ayırıcı dile bağlıdır.
    Ölçüldü (tarayıcı, TR modu): "150000 N⋅s"."""
    tr = _kos(tmp_path, dil='tr', locale_env='tr_TR.UTF-8')
    assert tr['lang'] == 'tr', 'düzenek TR moduna geçemedi: %r' % tr['lang']
    assert tr['T09_5000x30'] == '150000 N⋅s'
    assert tr['T09_250x4'] == '1000 N⋅s'


def test_t09_tolocalestring_geri_gelmedi():
    """Yerel-bağımsız ikinci hat: ``updateCalculatedImpulse`` gövdesinde
    argümansız ``toLocaleString()`` bulunmamalı. Kusurun tam kaynağı buydu."""
    metin = _oku()
    m = re.search(r'function updateCalculatedImpulse\s*\(\)\s*\{(.*?)\n        \}',
                  metin, re.S)
    assert m, 'updateCalculatedImpulse şablonda bulunamadı'
    govde = _yorumsuz(m.group(1))
    assert 'toLocaleString' not in govde, (
        'updateCalculatedImpulse yine toLocaleString kullanıyor — işletim '
        'sistemi yereli sayfanın diline sızar')
    assert 'i18nNumber' in govde, 'sayı biçimi i18nNumber üzerinden geçmiyor'


def test_t09_yardimci_i18n_number_uzerinden_gecer():
    """``i18nNumber`` gerçek çevirmene bağlanmalı; kendi biçimini uydurmamalı."""
    metin = _oku()
    m = re.search(r'function i18nNumber\s*\(value, digits\)\s*\{(.*?)\n        \}',
                  metin, re.S)
    assert m, 'i18nNumber yardımcısı bulunamadı'
    govde = _yorumsuz(m.group(1))
    assert 'window.I18N.number' in govde
    assert 'toLocaleString' not in govde


# ===========================================================================
# T12 — yörünge aracı motorun itici kütlesinden türetilir
# ===========================================================================

def test_t12_kalkis_kutlesi_motorun_iticisinden_turetilir(olcum):
    """Ölçüldü — önce: initial_mass Calculate sonrası da 50 kg kalıyordu
    (yörünge itici 25 kg, motorunki 5,463085 kg). Sonra: 30,463 kg."""
    e = olcum['esitlenmis']
    beklenen = float(e['final_mass']) + MOTOR_ITICI_KG
    assert abs(float(e['initial_mass']) - beklenen) < 1e-3, (
        'kalkış kütlesi kuru + motor itici değil: %r (beklenen %.3f)'
        % (e['initial_mass'], beklenen))
    assert abs(e['yorunge_itici_kg'] - MOTOR_ITICI_KG) < 1e-3, (
        'yörüngenin yaktığı itici motorunkinden farklı: %.4f vs %.4f'
        % (e['yorunge_itici_kg'], MOTOR_ITICI_KG))


def test_t12_ima_edilen_isp_motorun_ispini_ihlal_etmez(olcum):
    """Kalemin çekirdeği. Isp = F/((Δm/t_b)·g0).

    ÖNCE : Δm = 25 kg    -> 40,79 s ile 185,59 s   => 4,55 KAT ihlal
    SONRA: Δm = 5,463 kg -> 186,66 s ile 185,59 s  => %0,57 fark

    Kalan %0,57, motorun kendi ``propellant_mass_total`` ile ``isp`` alanı
    arasındaki iç farktır (5,463 kg ile 5,494 kg) ve bu şablonun konusu
    değildir; eşik oraya değil, 4,55 katlık ihlale karşı konmuştur.
    """
    e = olcum['esitlenmis']
    oran = e['ima_edilen_isp_s'] / MOTOR_ISP_S
    assert abs(oran - 1.0) <= 0.02, (
        'yörünge girdileri motorun Isp değerini %.2f kat ihlal ediyor '
        '(ima edilen %.2f s, motor %.2f s)'
        % (oran, e['ima_edilen_isp_s'], MOTOR_ISP_S))


def test_t12_kalkis_kutlesi_elle_ezilemez(olcum):
    """Kalkış kütlesi bağımlı büyüklüktür; serbest girdi olarak bırakılırsa
    kusur geri gelir. Motor sonucu geldikten sonra alan salt-okunur olmalı."""
    assert olcum['esitlenmis']['readOnly'] is True


def test_t12_kuru_kutle_degisince_yeniden_turetilir(olcum):
    """Kullanıcı kuru kütleyi 25 -> 12 kg yapınca kalkış kütlesi 17,463 olmalı;
    aksi hâlde ilişki bir kez kurulup sonra kopar."""
    beklenen = 12.0 + MOTOR_ITICI_KG
    assert abs(float(olcum['kuru12_initial']) - beklenen) < 1e-3, (
        'kuru kütle değişince kalkış kütlesi güncellenmedi: %r'
        % olcum['kuru12_initial'])


def test_t12_motor_sonucu_yokken_uydurma_kutle_yazilmaz(tmp_path):
    """Hesaplanamayan alana uydurma sayı KONMAZ ve hiçbir künye iddiası
    yazılmaz. Motor sonucu yokken alan şablondaki değerinde, düzenlenebilir
    kalır; not boştur."""
    m = _kos(tmp_path, senaryo='motorsuz', locale_env='tr_TR.UTF-8')
    assert m['motorsuz']['initial_mass'] == '50', (
        'motor sonucu yokken alan değiştirilmiş: %r' % m['motorsuz']['initial_mass'])
    assert m['motorsuz']['readOnly'] is False
    assert m['motorsuz']['not'] == '', (
        'motor yokken kaynaksız künye yazılmış: %r' % m['motorsuz']['not'])
    assert m['motorsuz']['reference_area'] == '17671'


def test_t12_hesap_sarmalayicisi_ozgun_islevi_yutmaz(olcum):
    """Eşitleme app.js'in ``displayCalculationResults`` çağrısını sarmalar.
    Özgün işlev HER koşulda çağrılmalı; yoksa sonuç çizimi kaybolur."""
    assert olcum['esitlenmis']['ozgun_display_cagri'] == 1, (
        'app.js displayCalculationResults bir kez çağrılmadı: %r'
        % olcum['esitlenmis']['ozgun_display_cagri'])


def test_t12_yorunge_dugmesi_istekten_once_esitler(olcum):
    """app.js:2286 alanları DOM'dan okur. Düğmeye basıldığında ekrandaki
    değer ile uca giden gövde AYNI olmalı: alan 999'a kirletildi,
    sarmalayıcının motora göre düzeltmesi beklenir."""
    assert olcum['traj_ozgun_cagri'] == 1, 'özgün calculateTrajectory çağrılmadı'
    assert olcum['traj_donus'] == 'ozgun', 'sarmalayıcı dönüş değerini yuttu'
    beklenen = 25.0 + MOTOR_ITICI_KG
    assert abs(float(olcum['traj_sonrasi_initial']) - beklenen) < 1e-3, (
        'yörünge isteğinden önce eşitleme yapılmadı: %r'
        % olcum['traj_sonrasi_initial'])


# ---------------------------------------------------------------------------
# T12 — referans alan: otomatik DOLDURULMAZ, yalnız ölçülüp bildirilir
# ---------------------------------------------------------------------------

def test_t12_referans_alan_otomatik_doldurulmaz(olcum):
    """Aracın alın kesiti motor verisinden hesaplanamaz. Eşitleme bu alana
    değer YAZMAMALI — yazarsa uydurma bir gövde ilan edilmiş olur."""
    sablon_varsayilani = re.search(
        r'<input[^>]*id="reference_area"[^>]*value="(\d+)"', _oku()).group(1)
    assert olcum['esitlenmis']['reference_area'] == sablon_varsayilani, (
        'eşitleme referans alanı değiştirdi (%r -> %r) — uydurma gövde'
        % (sablon_varsayilani, olcum['esitlenmis']['reference_area']))


def test_t12_referans_alan_varsayilani_oda_capiyla_makul():
    """Ölçüldü — önce: 100000 mm² = Ø356,8 mm gövde, motorun oda çapı
    Ø79,87 mm (4,47 kat). Sürükleme alanla doğru orantılı olduğundan apoje
    tahminini doğrudan bozuyordu. Varsayılan, alanın kendi yardım metnindeki
    örneğe çekildi: 17671 mm² = Ø150 mm (1,88 kat)."""
    metin = _oku()
    deger = int(re.search(
        r'<input[^>]*id="reference_area"[^>]*value="(\d+)"', metin).group(1))
    govde_capi_mm = 2 * (deger / 3.141592653589793) ** 0.5
    oda_capi_mm = MOTOR_ODA_CAPI_M * 1000
    oran = govde_capi_mm / oda_capi_mm
    assert 1.0 <= oran <= 3.0, (
        'referans alan varsayılanı Ø%.1f mm gövde demek; motorun oda çapı '
        'Ø%.1f mm (%.2f kat) — bu oran fiziksel olarak savunulamaz'
        % (govde_capi_mm, oda_capi_mm, oran))
    # Yardım metni hâlâ aynı örneği belgeliyor mu?
    assert '17671' in metin and '150 mm' in metin


@pytest.mark.parametrize('anahtar,uyarilmali', [
    ('ref_100000', True),    # Ø356,8 mm -> odanın 4,47 katı
    ('ref_3000', True),      # Ø61,8 mm  -> odadan KÜÇÜK (0,77) — imkânsız
    ('ref_varsayilan', False),  # Ø150 mm -> 1,88 kat
])
def test_t12_referans_alan_tutarsizsa_uyarilir(olcum, anahtar, uyarilmali):
    """Not, ima edilen gövde çapını ve oda çapına oranını ÖLÇÜP yazar;
    oran 1'in altında (gövde odadan küçük) ya da 3'ün üstündeyse renkle
    uyarır. Ölçülen notlar: 357 mm/4.47x, 62 mm/0.77x, 150 mm/1.88x."""
    kayit = olcum[anahtar]
    assert kayit['not'], 'referans alan notu boş'
    assert bool(kayit['renk']) is uyarilmali, (
        '%s: uyarı beklentisi %r, ölçülen renk %r (not: %r)'
        % (anahtar, uyarilmali, kayit['renk'], kayit['not']))


def test_t12_notlar_dile_bagli_olmayan_parcalardan_kurulur(tmp_path):
    """T57 (karışık dil) kalemini BÜYÜTMEMEK için kural: bu blok şablona yeni
    çevrilmemiş cümle sokmaz. Notlar sayılardan, SI birim simgelerinden ve
    ZATEN çevrilmiş mevcut anahtarlardan kurulur.

    Ölçüldü (tarayıcı, TR modu): kalkış künyesi "25,000 + 5,463 = 30,463 kg
    · Isp 186,7 s", referans alan künyesi "Ø 150 mm · Oda Çapı (mm) 79,9
    · 1,88×" — İngilizce sözcük yok, ondalık ayırıcı Türkçe.
    """
    tr = _kos(tmp_path, dil='tr', locale_env='tr_TR.UTF-8')
    kalkis = tr['esitlenmis']['not']
    ref = tr['esitlenmis']['ref_not']
    assert 'Oda Çapı' in ref, 'oda çapı etiketi çevrilmemiş: %r' % ref
    # TR ondalık ayırıcı virgüldür (i18n.js:299); nokta kalmışsa sayı biçimi
    # dilden kopmuş demektir.
    assert '30,463 kg' in kalkis, 'TR sayı biçimi uygulanmamış: %r' % kalkis
    for ing in ('Derived', 'dry mass', 'diameter body', 'Chamber Diameter',
                'Run Calculate', 'not known'):
        assert ing not in kalkis and ing not in ref, (
            'Türkçe modda İngilizce metin sızdı (%r): %r | %r' % (ing, kalkis, ref))


def test_t12_sablona_sozlukte_olmayan_anahtar_eklenmedi():
    """Depo sözleşmesi: şablonda geçen her ``adv.*`` anahtarının
    ``i18n_advanced.js``'te karşılığı olmalı (test_i18n_advanced.py).
    Bu blok yalnız MEVCUT anahtarları kullanır; yenisini eklemek sözlük
    dosyasını da düzenlemeyi gerektirirdi."""
    dict_js = (REPO_ROOT / 'hrma' / 'static' / 'js' / 'i18n_advanced.js'
               ).read_text(encoding='utf-8')
    metin = _oku()
    bas = metin.index('// ===== Yörünge aracı ile motorun eşitlenmesi')
    son = metin.index('async function generate3DCAD()')
    blok = metin[bas:son]
    kullanilan = set(re.findall(r"i18n(?:Text|Fmt)\('([^']+)'", blok))
    assert kullanilan, 'blok hiç çeviri anahtarı kullanmıyor'
    eksik = sorted(k for k in kullanilan if ("'%s'" % k) not in dict_js)
    assert not eksik, 'i18n_advanced.js sözlüğünde bulunmayan anahtarlar: %s' % eksik
    assert 'I18N.register' not in blok, (
        'şablon kendi sözlüğünü kaydediyor — çeviriler i18n_advanced.js\'te durur')


# ===========================================================================
# Şablon sağlığı
# ===========================================================================

def test_inline_js_sozdizimi_gecerli(tmp_path):
    """Şablonun bütün src'siz <script> blokları birlikte ayrıştırılabilmeli."""
    metin = _oku()
    bloklar = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', metin, re.S)
    assert len(bloklar) >= 3, 'inline blok sayısı beklenenden az: %d' % len(bloklar)
    hedef = tmp_path / 'advanced_inline.js'
    hedef.write_text('\n;\n'.join(bloklar), encoding='utf-8')
    r = subprocess.run([NODE, '--check', str(hedef)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, 'inline JS sözdizimi hatalı:\n' + r.stderr
