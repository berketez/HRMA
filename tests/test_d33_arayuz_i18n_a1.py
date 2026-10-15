# -*- coding: utf-8 -*-
"""ÖH Dalga-33-3 · kulvar ``arayuz-i18n`` · aşama 1 — bekçiler.

Her bekçi ters-mutasyonla (onarımı geçici geri al → KIRMIZI) kanıtlanmıştır;
kanıt ``docs/scofield/raw/OH/D33-3/arayuz-i18n/a1/mutasyon.json``.

Kapsanan kalemler
-----------------
* **OH-D33-12** — Türkçe arayüzde ondalık ayracı karışık: AYNI EKRANDA
  (``docs/user_guide/img/tr-02-results.png``) gösterge kartları NOKTA
  (``222.8`` / ``20.0`` / ``0.458`` / ``0.81``), hemen altındaki Uyarılar
  paneli VİRGÜL (``7,5`` / ``0,5-6`` / ``3,87``) basıyordu. ÖH D30 /
  P12aB1-01 ayraç seçimini ``i18n.js::ondalikAyraci`` tek kaynağına
  bağlamıştı; kart yolu (``hud.js::countUp`` ve ``app.js`` HUD'suz
  yedeği) o kanaldan HİÇ geçmiyordu — ``toFixed`` ECMA-262 gereği her
  zaman nokta basar. Ölçüm: ``a1/once.json`` bölüm ``M1``
  (TR kipte 5 kartın 4'ü nokta, virgül basan kart 0).

* **OH-D33-13** — Türkçe sonuç panelinde yapısal hüküm bloğu İngilizce
  cümle taşıyordu (aynı blokta iki dil). İKİ kök ölçüldü (``a1/once.json``
  bölüm ``M2``, gerçek ``/calculate`` yanıtı):
  1. ``app.py::_carry_structural_verdict_outcome`` cidar kapısının
     ``message`` gövdesinin SONUNA bir cümle ekliyor; ``i18n_charts.js``
     desenleri ``$`` ile çıpalı olduğu için kuyruklu gövde artık
     eşleşmiyordu (6 gerçek gövdenin 5'i İngilizce).
  2. ``safety_analysis.verdict_basis``in iki dalı (``app.py:20487`` ve
     ``:20496``) hiçbir desene girmemişti.
  Mevcut bekçi (``test_z5i18n_kalan.py``) kusuru GÖRMÜYORDU: kapı
  fonksiyonunu doğrudan çağırıyor, kuyruğun eklendiği yoldan geçmiyor.

* **OH-D33-33** (defter kimliği ``OH-D33-23``) — ``formulas.html`` §8.2
  model notunun EN metni "a factor of 4.75" oranını ATIFSIZ/GENEL yazıyordu;
  kampanyanın kendi hükmü (``raw/P12B/H2-hukum.md:311-318``) oranı motora
  bağlı bulup "genel davranış olarak yazılamaz" demişti. TR karşılığı
  fix-37c ile beyanı almıştı, EN (şablon + sözlük) hâlâ beyansızdı.

Node çağrıları ``tests/test_node_cagri_sozlesmesi.py`` sözleşmesine uyar:
betik argv'ye değil DOSYA yoluyla verilir.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from tests.support.kanit import kanit_gerekli

# ÖH D33-3 / fix-38d (ana model, 16 Eylül 2026): modül düzeyinde
# ``warnings.filterwarnings('ignore')`` YOKTUR. Bu dosya onunla doğdu ve
# tests/test_d32_altyapi_a1.py::TestOHD3119WarningsSusturmasi tavanını
# 35'ten 36'ya çıkardı; o bekçinin kuralı açık: sayı YALNIZ KÜÇÜLEBİLİR,
# envanter gevşetilmez (ÖK-22). Susturma süreç genelinde etkilidir — bu
# dosya tek başına koşmasa bile aynı süreçteki başka testlerin uyarılarını
# yutar. Bu dosyanın uyarıya ihtiyacı da yoktu: ölçümler alt süreçte
# (node sondası) ve dosya okumasıyla yapılıyor.

KOK = Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
HUD = JS / 'hud.js'
APPJS = JS / 'app.js'
CHARTS = JS / 'i18n_charts.js'
FORMULAS_JS = JS / 'i18n_formulas.js'
FORMULAS_TPL = KOK / 'hrma' / 'templates' / 'formulas.html'
KANIT = (KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D33-3'
         / 'arayuz-i18n' / 'a1')

NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

# ---------------------------------------------------------------------------
# OH-D33-12 — ölçülen kart değerleri (TEK KAYNAK)
# ---------------------------------------------------------------------------
#: ``raw/OH/KILAVUZ/ekran/kayit.json`` (tr-02-results) turunda ekranda
#: okunan beş kart: (ad, hedef, basamak, TR beklenen, EN beklenen).
#: Sayılar o kaydın ``olculen_sonuc`` alanından; burada YENİDEN hesap yok.
KART_DEGERLERI = [
    ('isp', 222.8039728187441, 1, '222,8', '222.8'),
    ('thrust', 1000, 0, '1000', '1000'),
    ('pc', 20.0, 1, '20,0', '20.0'),
    ('mdot', 0.45767416086762946, 3, '0,458', '0.458'),
    ('minSf', 0.81, 2, '0,81', '0.81'),
]

SAYAC_SONDA = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
function El() { this.dataset = {}; this.textContent = ''; }
const depo = {};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    document: { readyState: 'complete', addEventListener: function () {},
                querySelectorAll: function () { return []; },
                querySelector: function () { return null; },
                documentElement: { setAttribute: function () {} },
                createElement: function () { return { style: {} }; } },
    localStorage: {
        getItem: function (k) { return (k in depo) ? depo[k] : null; },
        setItem: function (k, v) { depo[k] = String(v); },
        removeItem: function (k) { delete depo[k]; } },
    navigator: { language: 'en-US' },
    /* reduced-motion AÇIK: animasyon değil SON metin ölçülür. */
    matchMedia: function () { return { matches: true }; },
    performance: { now: function () { return 0; } },
    requestAnimationFrame: null,
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
function kos(f) {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
kos(path.join(staticDir, 'i18n.js'));
kos(path.join(staticDir, 'i18n_common.js'));
kos(path.join(staticDir, 'i18n_charts.js'));
kos(path.join(staticDir, 'hud.js'));
const OUT = { sayac: {}, srv: {} };
['en', 'tr'].forEach(function (dil) {
    sb.window.I18N.setLang(dil);
    OUT.sayac[dil] = (P.sayaclar || []).map(function (s) {
        const el = new El();
        el.dataset.target = String(s.target);
        el.dataset.decimals = String(s.decimals);
        sb.window.HRMAHud.countUp(el);
        return el.textContent;
    });
    OUT.srv[dil] = (P.metinler || []).map(function (m) {
        return sb.window.I18N.serverText(m); });
});
process.stdout.write(JSON.stringify(OUT));
"""

#: HUD'suz yol + `aria-label`: ürünün KENDİ `displayPerformanceMetrics`i
#: çizer (kopya değil).
KART_SONDA = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this._a = {};
    this.innerHTML = ''; this.dataset = {}; this.id = ''; this.textContent = '';
}
El.prototype.appendChild = function (x) { this.children.push(x); return x; };
El.prototype.setAttribute = function (k, v) { this._a[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._a, k) ? this._a[k] : null; };
El.prototype.removeAttribute = function (k) { delete this._a[k]; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.querySelector = function () { return null; };
El.prototype.addEventListener = function () {};
const depo = {};
const doc = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    documentElement: new El('html'),
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: function () {}, clearInterval: clearInterval,
    fetch: function () { return Promise.reject(new Error('ag yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    alert: function () {}, document: doc,
    localStorage: {
        getItem: function (k) { return (k in depo) ? depo[k] : null; },
        setItem: function (k, v) { depo[k] = String(v); },
        removeItem: function (k) { delete depo[k]; } },
    navigator: { language: 'en-US' },
    matchMedia: function () { return { matches: true }; },
    performance: { now: function () { return 0; } },
    requestAnimationFrame: null,
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
function kos(f) {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
kos(path.join(staticDir, 'i18n.js'));
kos(path.join(staticDir, 'i18n_common.js'));
kos(path.join(staticDir, 'i18n_charts.js'));
kos(path.join(staticDir, 'hud.js'));
kos(path.join(staticDir, 'analysis_dock.js'));
kos(path.join(staticDir, 'panels', 'structural_panel.js'));
kos(path.join(staticDir, 'app.js'));
const motor = (P.yanit && P.yanit.motor) ? P.yanit.motor : P.yanit;
function ciz(dil, hudVar) {
    sb.window.I18N.setLang(dil);
    const kutu = new El('div'); kutu.id = 'performanceMetrics';
    const eski = doc.getElementById;
    doc.getElementById = function (id) {
        return (id === 'performanceMetrics') ? kutu : null; };
    const yedek = sb.window.HRMAHud;
    if (!hudVar) { delete sb.window.HRMAHud; }
    let hata = '';
    try { sb.displayPerformanceMetrics(motor, P.yanit); }
    catch (e) { hata = String(e && e.message); }
    doc.getElementById = eski;
    if (!hudVar) { sb.window.HRMAHud = yedek; }
    return { html: kutu.innerHTML, hata: hata };
}
const OUT = { kart: {}, serit: {} };
['en', 'tr'].forEach(function (dil) {
    OUT.kart[dil] = { hud: ciz(dil, true), duz: ciz(dil, false) };
    sb.window.I18N.setLang(dil);
    OUT.serit[dil] = sb.structuralVerdictBlock(motor, P.yanit) || '';
});
process.stdout.write(JSON.stringify(OUT));
"""


def _node(betik_govdesi, girdi, static_dir=None):
    sdir = str(static_dir or JS)
    with tempfile.TemporaryDirectory() as tmp:
        betik = os.path.join(tmp, 'sonda.js')
        with open(betik, 'w', encoding='utf-8') as fh:
            fh.write(betik_govdesi)
        veri = os.path.join(tmp, 'girdi.json')
        with open(veri, 'w', encoding='utf-8') as fh:
            json.dump(girdi, fh)
        p = subprocess.run([NODE, betik, sdir, veri],
                           capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, 'node çöktü:\n' + p.stderr[-3000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


SUNUCU_METNI_SONDA = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
const depo = {};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    document: { readyState: 'complete', addEventListener: function () {},
                querySelectorAll: function () { return []; },
                querySelector: function () { return null; },
                documentElement: { setAttribute: function () {} },
                createElement: function () { return { style: {} }; } },
    localStorage: {
        getItem: function (k) { return (k in depo) ? depo[k] : null; },
        setItem: function (k, v) { depo[k] = String(v); },
        removeItem: function (k) { delete depo[k]; } },
    navigator: { language: P.dil === 'tr' ? 'tr-TR' : 'en-US' },
    matchMedia: function () { return { matches: true }; },
    performance: { now: function () { return 0; } },
    requestAnimationFrame: null,
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
function kos(f) {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
kos(path.join(staticDir, 'i18n.js'));
kos(path.join(staticDir, 'i18n_common.js'));
kos(path.join(staticDir, 'i18n_charts.js'));
if (sb.I18N.setLang) { sb.I18N.setLang(P.dil); } else { sb.I18N.lang = P.dil; }
console.log(JSON.stringify(P.metinler.map(function (m) {
    return sb.I18N.serverText(m);
})));
"""

#: fix-38a'nın AÇIK BIRAKTIĞI iki sunucu mesajı (OH-D33-43).
#: Girdi metinleri ürünün İngilizce gövdeleridir; birebir bu biçimde
#: yayımlanıyorlar (hrma/engines/injector_design.py kaynaklı).
ACIK_KALAN_MESAJLAR = [
    ('Cavitation risk: Nurick cavitation number K_c = -6.59 < 1.5 '
     '(injector inlet P_1 = 24.0 bar, dP = 4.0 bar, P_v = 50.4 bar at 293 K)'),
    ('Target injection velocity (30.0 m/s) is not set by hole count: '
     'with Cd=0.78 the achieved velocity is 24.9 m/s. Reaching the target '
     'needs dP = 5.82 bar (currently 4.00 bar).'),
]


@node_gerek
def test_ondalik_ayraci_ACIK_KALAN_IKI_MESAJDA_DA_yerellesir():
    """TR panelde aynı ekranda hem virgül hem nokta duramaz (OH-D33-43).

    ÖLÇÜLDÜ (tr-07-warnings karesi, Türkçe kılavuzda YAYIMLANDI): panelin
    bir kısmı virgüllüydü ('Genleşme oranı 3,9', 'q=20,7 MW/m2', 'medyan
    sapma %-39,5'), bu iki mesaj ise noktalı kalıyordu ('K_c = -6.59 < 1.5',
    'Cd=0.78 ile ulaşılan hız 24.9 m/s'). Kök: desenler sayıları $1/$2
    olarak AYNEN geçiriyordu, ``I18N.decimalText``ten geçmiyordu — fix-38a
    (OH-D33-34) aynı sınıfı tek desende kapatmıştı, bu ikisi açık kalmıştı.

    Kavitasyon mesajının parantez içi ayrıca TAMAMEN İngilizceydi
    ('injector inlet P_1 = ... at 293 K') ve Türkçe ekranda öyle duruyordu.
    """
    cikti = _node(SUNUCU_METNI_SONDA,
                  {'dil': 'tr', 'metinler': ACIK_KALAN_MESAJLAR})
    for ham, tr in zip(ACIK_KALAN_MESAJLAR, cikti):
        assert tr != ham, 'mesaj hiç çevrilmemiş: ' + ham[:60]
        # Cümle içinde NOKTALI ondalık kalmamalı (cümle sonu noktası hariç).
        kalan = re.findall(r'\d+\.\d+', tr)
        assert not kalan, ('TR cümlede noktalı ondalık kaldı: %r içinde %s'
                           % (tr, kalan))
        assert re.search(r'\d+,\d+', tr), 'TR cümlede virgüllü ondalık yok: ' + tr

    # Kavitasyon parantezi Türkçeleşmeli: İngilizce iskelet kalmamalı.
    kav = cikti[0]
    for ingilizce in ('injector inlet', ' at 293 K', 'Cavitation risk'):
        assert ingilizce not in kav, ('İngilizce parça Türkçe ekranda: %r'
                                      % ingilizce)


@node_gerek
def test_EN_arayuzde_ayni_mesajlar_NOKTALI_kalir():
    """Karşı yön: İngilizce arayüzde sayı yerelleşmez (nokta korunur)."""
    cikti = _node(SUNUCU_METNI_SONDA,
                  {'dil': 'en', 'metinler': ACIK_KALAN_MESAJLAR})
    for ham, en in zip(ACIK_KALAN_MESAJLAR, cikti):
        assert ',' not in en.replace(', dP', '').replace(', P_v', ''), (
            'EN metinde virgüllü ondalık: ' + en)


# ===========================================================================
# OH-D33-12 — ondalık ayracı TEK KAYNAK, kart yolu dâhil
# ===========================================================================
@pytest.fixture(scope='module')
def sayac_metni():
    return _node(SAYAC_SONDA, {
        'sayaclar': [{'target': t, 'decimals': d}
                     for _, t, d, _, _ in KART_DEGERLERI],
        'metinler': [],
    })


@node_gerek
def test_kart_sayaci_turkce_kipte_virgul_basar(sayac_metni):
    """TR kipte kart değerleri Uyarılar paneliyle AYNI ayracı kullanır."""
    olculen = sayac_metni['sayac']['tr']
    hatali = []
    for i, (ad, _, _, tr_beklenen, _) in enumerate(KART_DEGERLERI):
        if olculen[i] != tr_beklenen:
            hatali.append('%s: %r (beklenen %r)' % (ad, olculen[i],
                                                    tr_beklenen))
    assert not hatali, (
        'Türkçe kipte gösterge kartı NOKTA basıyor — aynı ekrandaki Uyarılar '
        'paneli VİRGÜL basar (OH-D33-12, tr-02-results.png):\n  '
        + '\n  '.join(hatali))
    # Ayraç ikinci bir yerde SEÇİLMEZ: nokta taşıyan kart kalmamalı.
    assert not [v for v in olculen if '.' in v], (
        'TR kipte nokta taşıyan kart değeri kaldı: %r' % (olculen,))


@node_gerek
def test_kart_sayaci_ingilizce_kipte_nokta_basar(sayac_metni):
    """EN kipte davranış DEĞİŞMEZ (onarım yalnız ayracı yerelleştirir)."""
    olculen = sayac_metni['sayac']['en']
    beklenen = [en for _, _, _, _, en in KART_DEGERLERI]
    assert olculen == beklenen, (
        'EN kipte kart metni değişti — onarım ayraç dışında bir şeye '
        'dokunmuş olmalı:\n  ölçülen %r\n  beklenen %r'
        % (olculen, beklenen))


@node_gerek
def test_sayac_basamak_sayisini_degistirmez(sayac_metni):
    """Basamağa `toFixed` karar verir; çeviri yuvarlama YAPMAZ."""
    for dil in ('en', 'tr'):
        for i, (ad, _, dec, _, _) in enumerate(KART_DEGERLERI):
            metin = sayac_metni['sayac'][dil][i]
            kesir = re.split(r'[.,]', metin)
            uzunluk = len(kesir[1]) if len(kesir) > 1 else 0
            assert uzunluk == dec, (
                '%s/%s: basamak sayısı %d, beklenen %d (%r) — ayraç '
                'çevirisi duyarlık DEĞİŞTİRMEZ'
                % (dil, ad, uzunluk, dec, metin))


@pytest.fixture(scope='module')
def yanit():
    """Ekran kaydının girdileriyle koşulmuş GERÇEK ``/calculate`` yanıtı."""
    yol = KANIT / 'calculate_yanit_cidarli.json'
    if not kanit_gerekli(yol).exists():
        pytest.skip('kanıt yanıtı yok: %s' % yol)
    return json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def ekran(yanit):
    return _node(KART_SONDA, {'yanit': yanit})


@node_gerek
def test_hudsuz_yol_da_ayraci_yerellestirir(ekran):
    """HUD katmanı yoksa (ve `aria-label`da) da ayraç TR'de virgüldür."""
    duz = ekran['kart']['tr']['duz']
    assert not duz['hata'], 'HUD\'suz yol patladı: %s' % duz['hata']
    metin = re.sub(r'<[^>]+>', ' ', duz['html'])
    # Künye satırı bilerek makine biçimindedir (alan adresleri + değerleri);
    # ölçüm yalnız kullanıcı cümlesinin sayılarına bakar.
    kullanici = metin.split('/calculate')[0]
    assert re.search(r'\d,\d', kullanici), (
        'HUD\'suz yolda TR kipte virgüllü sayı yok: %r' % kullanici[:300])
    assert not re.search(r'\d\.\d', kullanici), (
        'HUD\'suz yolda TR kipte NOKTALI sayı kaldı (OH-D33-12): %r'
        % kullanici[:300])


@node_gerek
def test_makine_ozniteligi_ayracla_bozulmaz(ekran):
    """`data-target` MAKİNE alanıdır: `parseFloat` okur, nokta bekler."""
    html = ekran['kart']['tr']['hud']['html']
    hedefler = re.findall(r'data-target="([^"]+)"', html)
    assert hedefler, 'kartta data-target bulunamadı'
    for h in hedefler:
        assert ',' not in h, (
            'data-target virgül taşıyor — parseFloat onu keser ve kart '
            'yanlış sayı gösterir: %r' % h)
        assert h == h.strip() and float(h) == float(h), h


# ===========================================================================
# OH-D33-13 — sunucu hüküm cümleleri Türkçe kipte Türkçe
# ===========================================================================
def _kuyruklu_govdeler():
    """``app.py``nin KENDİ ürettiği gövdeler (şablon-körlüğüne karşı).

    Kapı gövdesi + ``_carry_structural_verdict_outcome`` kuyruğu BİRLİKTE
    üretilir: kuyruk metni değişirse bu bekçi kırmızı verir.
    """
    from hrma import app as appmod
    kapi = appmod._classify_wall_thickness_gate
    tasi = appmod._carry_structural_verdict_outcome

    def _govde(kapi_args, safety):
        basis = dict(kapi(*kapi_args))
        basis['verdict'] = 'issued'
        basis.setdefault('verdict_withheld_reasons', [])
        return tasi(basis, {'safety_analysis': safety})['message']

    user = (0.003, 0.003, appmod.WALL_INPUT_OK, 'm')
    sized = (None, 0.0159, appmod.WALL_INPUT_NOT_SUPPLIED, 'm')
    return {
        'user+durum+risk+sf': _govde(user, {
            'status': 'UNSAFE', 'risk_level': 'HIGH',
            'verdict_safety_factor': 1.3997561905898435}),
        'user+durum': _govde(user, {'status': 'SAFE'}),
        'sized+durum+risk+sf': _govde(sized, {
            'status': 'UNSAFE', 'risk_level': 'HIGH',
            'verdict_safety_factor': 1.6172008764854071}),
        'sized+yayimlanmadi': _govde(sized, {}),
        'user+kuyruksuz': dict(kapi(*user))['message'],
    }


def _verdict_basis_dallari():
    """``safety_analysis.verdict_basis``in ekrana çıkan iki dalı.

    Metinler BURAYA YAZILMAZ, ``app.py``nin kendi kapısından ÜRETİLİR
    (``_withhold_unearned_structural_verdict``, :20487 / :20496) — aksi
    hâlde bu bekçi de sunucu cümlesi değişince kör kalırdı (D33'ün
    "şablon-körü bekçi" dersi).
    """
    from hrma import app as appmod

    def _dal(dis_istasyonlar):
        sr = {
            'chamber_analysis': {'design_mode': 'verify',
                                 'safety_factor_is_tautological': False},
            'safety_analysis': {'status': 'UNSAFE', 'risk_level': 'HIGH',
                                'stations_not_verified': list(dis_istasyonlar)},
        }
        appmod._withhold_unearned_structural_verdict(sr, True)
        return sr['safety_analysis']['verdict_basis']

    return {
        'verdict_basis/dis_istasyonlar': _dal(['end_cap', 'nozzle']),
        'verdict_basis/tam_dogrulama': _dal([]),
    }


@pytest.fixture(scope='module')
def sunucu_govdeleri():
    govde = _kuyruklu_govdeler()
    govde.update(_verdict_basis_dallari())
    return govde


@node_gerek
def test_hukum_govdeleri_turkce_kipte_turkcedir(sunucu_govdeleri):
    """Kuyruk eklendiğinde de gövde Türkçeleşir (OH-D33-13)."""
    adlar = sorted(sunucu_govdeleri)
    metinler = [sunucu_govdeleri[a] for a in adlar]
    cikti = _node(SAYAC_SONDA, {'sayaclar': [], 'metinler': metinler})
    kalan = []
    for i, ad in enumerate(adlar):
        if cikti['srv']['tr'][i] == metinler[i]:
            kalan.append('%s: %r' % (ad, metinler[i][:110]))
    assert not kalan, (
        'Türkçe kipte İNGİLİZCE kalan hüküm gövdesi (%d/%d) — sunucu metni '
        'mi değişti, desen mi eksik?\n  %s'
        % (len(kalan), len(adlar), '\n  '.join(kalan)))
    # EN kipte metin AYNEN kalır (çeviri kanalı EN'e dokunmaz).
    assert cikti['srv']['en'] == metinler


@node_gerek
def test_kuyruk_cevirisi_sayi_ve_makine_adini_tasir(sunucu_govdeleri):
    """Kuyruk çevirisi sayının DEĞERİNİ ve durum belirtecini KAYBETMEZ.

    ÖLÇÜT ÇEVRİLDİ (fix-38a, ana model, 16 Eylül 2026) — gerekçesiyle:
    bu düğüm önce sayının ``'1.4'`` diye NOKTAYLA taşındığını istiyordu
    ("sayılar makinedir, aynen taşınır"). Kılavuz ekran tazeleme turu o
    kuralın Türkçe kullanıcıda ne ürettiğini ÖLÇTÜ (tr-02-results):
    gösterge kartı ``0,81`` derken aynı ekrandaki cümle ``Hüküm emniyet
    katsayısı 0.8058.`` diyordu — tek ekranda iki ayraç.

    Ayrım MAKİNE ⟷ NESİR değil, KÜNYE ⟷ CÜMLEDİR. Künye dökümündeki
    ``verdict_safety_factor: 0.805757`` makinedir ve noktayla kalır;
    cümlenin içinde okunan sayı nesirdir ve ``I18N.decimalText``
    kanonundan geçer (OH-D33-12 kartlarda bunu zaten yapıyordu).
    Durum belirteçleri (UNSAFE / HIGH) ve istasyon adları MAKİNEDİR,
    aynen taşınmaya devam eder — bu düğümün asıl iddiası odur ve
    korunmuştur.
    """
    ad = 'user+durum+risk+sf'
    cikti = _node(SAYAC_SONDA,
                  {'sayaclar': [], 'metinler': [sunucu_govdeleri[ad]]})
    tr = cikti['srv']['tr'][0]
    for im in ('UNSAFE', 'HIGH'):
        assert im in tr, (
            '%r kuyruk çevirisinde kayboldu: %r' % (im, tr))
    assert '1,4' in tr, (
        'sayının DEĞERİ kayboldu ya da TR kipte hâlâ nokta basılıyor: %r' % tr)
    assert '1.4' not in tr, (
        'TR cümlede nokta ayracı kaldı (kartlar virgül basıyor): %r' % tr)
    en = cikti['srv']['en'][0]
    assert '1.4' in en and '1,4' not in en, (
        'EN kipte ayraç bozuldu: %r' % en)
    # İstasyon adları da makinedir.
    disi = _node(SAYAC_SONDA, {
        'sayaclar': [],
        'metinler': [sunucu_govdeleri['verdict_basis/dis_istasyonlar']]})
    assert 'end_cap, nozzle' in disi['srv']['tr'][0]


@node_gerek
def test_yarim_turkce_cumle_uretilmez():
    """FAIL-CLOSED: gövde çevrilemiyorsa kuyruk TEK BAŞINA çevrilmez."""
    uydurma = ('Some sentence that no dictionary or pattern knows about at '
               'all. Outcome of that verification: SAFE.')
    cikti = _node(SAYAC_SONDA, {'sayaclar': [], 'metinler': [uydurma]})
    assert cikti['srv']['tr'][0] == uydurma, (
        'Bilinmeyen gövdeye Türkçe kuyruk eklenmiş (yarı Türkçe cümle): %r'
        % cikti['srv']['tr'][0])


@node_gerek
def test_hukum_seridinde_ingilizce_cumle_kalmaz(ekran, sunucu_govdeleri):
    """Ekranda çizilen şeritte İngilizce gövde bulunmamalı."""
    serit = re.sub(r'<[^>]+>', ' ', ekran['serit']['tr'])
    serit = ' '.join(serit.split())
    bulunan = [ad for ad, metin in sunucu_govdeleri.items()
               if ' '.join(metin.split())[:70] in serit]
    assert not bulunan, (
        'TR hüküm şeridi İngilizce cümle taşıyor (aynı blokta iki dil): %r'
        % bulunan)


# ===========================================================================
# OH-D33-33 (defter: OH-D33-23) — §8.2 oranının EN beyanı
# ===========================================================================
def _s82_kayitlari():
    src = FORMULAS_JS.read_text(encoding='utf-8')
    return [m.group(1) for m in re.finditer(
        r"'fx\.s8_2\.model_note':\s*'((?:[^'\\]|\\.)*)'", src)]


def test_s82_orani_EN_metninde_de_ornege_baglanir():
    kayit = _s82_kayitlari()
    assert len(kayit) == 2, 'fx.s8_2.model_note EN+TR bekleniyordu: %d' % len(
        kayit)
    en, tr = kayit
    assert '4.75' in en, 'EN metinde oran yok — ölçüm dayanağı kayboldu'
    assert 'belongs to this worked example' in en, (
        'EN §8.2 model notu oranı hâlâ ATIFSIZ yazıyor (OH-D33-33): '
        'kampanyanın kendi hükmü (raw/P12B/H2-hukum.md:311-318) bu oranı '
        'motora bağlı buldu, genel kural olarak yazılamaz.\n%s' % en[-220:])
    assert 'not a general rule' in en
    assert 'Bu oran BU örneğe aittir' in tr, (
        'TR beyanı (fix-37c) kaybolmuş')


def test_s82_sablonu_EN_sozlukle_ayni():
    """Ekrana SÖZLÜK çizilir: şablonu tek başına düzeltmek ulaşmaz."""
    sablon = re.search(r'data-i18n="fx\.s8_2\.model_note">(.*?)</span>',
                       FORMULAS_TPL.read_text(encoding='utf-8'), re.S)
    assert sablon, 'şablonda fx.s8_2.model_note düğümü yok'
    sablon_metin = ' '.join(sablon.group(1).split())
    en = ' '.join(_s82_kayitlari()[0].replace("\\'", "'").split())
    assert sablon_metin == en, (
        'şablon metni ile EN sözlük girdisi AYRIŞIK (OH-D33-21 sınıfı)\n'
        'şablon: …%s\nsözlük: …%s' % (sablon_metin[-160:], en[-160:]))


# ===========================================================================
# Sözdizimi — dokunulan dosyalar node ile ayrıştırılabilir kalmalı
# ===========================================================================
@node_gerek
@pytest.mark.parametrize('yol', [HUD, APPJS, CHARTS, FORMULAS_JS])
def test_js_sozdizimi(yol):
    r = subprocess.run([NODE, '--check', str(yol)], capture_output=True,
                       text=True, timeout=300)
    assert r.returncode == 0, '%s: %s' % (yol.name, r.stderr[-1500:])


# ===========================================================================
# ÖH D33-3 · fix-38a (ana model) — TR hüküm CÜMLESİNDEKİ sayı da yerelleşir
# ===========================================================================

def test_hukum_cumlesindeki_sayi_TR_kipte_virgulle_basilir():
    """Kuyruk cümlesindeki emniyet katsayısı NESİRDİR, künye değildir.

    ÖLÇÜLDÜ (kılavuz ekran tazeleme turu, 16 Eylül 2026, tr-02-results):
    OH-D33-12 gösterge kartlarını ``I18N.decimalText`` kanonuna bağladıktan
    SONRA bile, aynı ekrandaki hüküm cümlesi ``toFixed`` çıktısını aynen
    taşıyordu: kart ``0,81`` derken cümle ``Hüküm emniyet katsayısı
    0.8058.`` diyordu. Kuyruk deseni sabit dize yerine işleve çevrildi.

    AYRIM: cümle içindeki sayı yerelleşir; künye dökümündeki
    ``verdict_safety_factor: 0.805757`` MAKİNEDİR ve nokta kalır.
    """
    import json
    import os
    import subprocess
    import tempfile

    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sonda = os.path.join(kok, 'docs', 'scofield', 'raw', 'OH', 'D33-3',
                         'arayuz-i18n', 'a1', 'sonda.js')
    if not os.path.isfile(kanit_gerekli(sonda)):
        import pytest
        pytest.skip('olcum sondasi bu agacta yok')
    cumle = ('The supplied wall thickness was evaluated against the design '
             'pressure; this result is a verification.'
             ' Outcome of that verification: UNSAFE (risk HIGH).'
             ' The verdict safety factor is 0.8058.')
    girdi = {'static_dir': os.path.join(kok, 'hrma', 'static', 'js'),
             'motor': {}, 'results': {}, 'sunucuMetinleri': [cumle]}
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                     encoding='utf-8') as f:
        json.dump(girdi, f, ensure_ascii=False)
        yol = f.name
    try:
        r = subprocess.run(['node', kanit_gerekli(sonda), girdi['static_dir'], yol],
                           capture_output=True, text=True, timeout=180)
    finally:
        os.unlink(yol)
    assert r.returncode == 0, r.stderr[-400:]
    o = json.loads(r.stdout)
    tr, en = o['srv']['tr'][0], o['srv']['en'][0]
    assert '0,8058' in tr, 'TR kipte hukum cumlesi hala NOKTA basiyor: ' + tr[-90:]
    assert '0.8058' not in tr, 'TR cumlede nokta kaldi: ' + tr[-90:]
    assert '0.8058' in en and '0,8058' not in en, 'EN kipte nokta bozuldu: ' + en[-90:]
