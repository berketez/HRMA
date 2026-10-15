# -*- coding: utf-8 -*-
"""ÖH Z5S / BEKÇİ-ÖDEME A1 — "onarıldı" kalemlerinin KAPANIŞ ŞARTLARI.

Bu dosya yeni bir onarım YAPMAZ. Daha önce (Z2/Z3/Z4 dalgalarında) onarılmış
yedi kalemin kapanış şartı olarak istenen BEKÇİLERİ yazar. Her sınıf tek bir
defter kalemini ödüyor ve şu üç şeyi ayrı ayrı kilitliyor:

  1. ÜRETİM — çözücü/motor o hükmü GERÇEKTEN yayımlıyor mu (fail-closed:
     yayımlamıyorsa bekçi kırılır, çünkü kalemin girdisi kaybolmuştur);
  2. TAŞIMA — hüküm kullanıcının göreceği kanala (uyarı kanalı, kart, panel
     satırı, ihraç dosyası) iniyor mu;
  3. GERİ DÖNÜŞ — hüküm kaynaktan silinirse ekrandan da düşüyor mu
     (mutasyon; ürün dosyası DEĞİŞTİRİLMEZ, mutasyon yanıt/kopya üstünde
     yapılır — sıcak dosyaya dokunulmaz).

Kapsanan kalemler ve kapanış şartları:

* **P16S1-07** (kritik) — ``severity: critical`` TERMAL hükmün teslim kanalı.
  Şart: "kanalda kritik sayısını + DOM inişini kilitleyen bekçi". Hibritte
  kanal ``app.js`` (``collectResultWarnings`` → ``displayWarnings``), katıda
  ``solid.html``in kendi ``displaySolidWarnings`` fonksiyonudur; ikisi de
  GERÇEK dosyadan node içinde koşturulur.
* **P17B1-01** (kritik) — /hybrid termal "EXCEEDS MELTING POINT" hükmü ile
  yapısal panelin yeşil SF'i aynı ekranda çelişiyordu. Şart görsel kapı turu
  imzası olduğu için burada TUR YERİNE GEÇEN makine ölçümü yazılır (tur
  imzası Fable denetimine kalır).
* **P17B1-02** (kritik) — yakınsamamış çözüm hüküm veremez. Şart:
  "converged-kapısı bekçisi + görsel tur". Kapı bekçisi burada ödenir.
* **P17B2-02** (kritik) — /liquid çözücüsünün ``CRITICAL ... liner failure``
  hükmü karta iniyor mu. Şart görsel tur; tur yerine ``liquid.html``in
  Termal Koruma kartı GERÇEK kaynağından çıkarılıp node içinde çizdirilir.
* **P17B3-06** (yüksek) — ekranda iki asgari SF vardı ve ikisi de aynı adı
  taşıyordu. Şart: "çift-SF-etiketi bekçisi + görsel tur". Etiket bekçisi
  burada ödenir (iki dal: künye özdeş → Δ; künye ayrık → ayrışan ALAN ADLARI).
* **P17S1-01** (yüksek) — aynı oturumun ``.eng`` ve ``STEP`` dosyaları iki
  ayrı kasa çapı yazıyordu (97,9 ⟷ 90,03 mm). Şart: ".eng ⟷ STEP çap-eşitliği
  bekçisi". Üç motor tipinde İKİ GERÇEK DOSYA üretilip karşılaştırılır.
* **P8B2-11** (orta) — köprü ikinci bir SF üretip çelişkiyi beyan etmiyordu.
  Şart: "kıyas-beyanı bekçisi + FEA üst düzey verdict'in uçta yüzeye
  çıkarılması". Birincisi ödenir; ikincisi ÜRÜN işi olduğu için
  ``xfail(strict)`` borç imiyle belgelenir (uç düzeltilince XPASS verir).

SÖZLEŞME NOTU — bu dosya KESİN ONDALIK ÇAPALAMAZ. Eşzamanlı onarım dalgaları
sayıları kaydırabilir; kilitlenen şey davranış ve künyedir. Ölçülen kesin
değerler kanıt dosyalarındadır:
``docs/scofield/raw/OH/Z5S/guard1/olcum_once.json`` ve
``docs/scofield/raw/OH/Z5S/guard1/olcum_dom_ihrac.json``.
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings('ignore')

KOK = Path(__file__).resolve().parents[1]
STATIK = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates'
NODE = shutil.which('node')

pytestmark = pytest.mark.filterwarnings('ignore::RuntimeWarning')


# ---------------------------------------------------------------------------
# İstekler — üç motor tipi. Bu dosyanın TEK tanımı (parametre tutarlılığı).
# ---------------------------------------------------------------------------
Z5G_HIBRIT = {'motor_name': 'z5g-h', 'fuel_type': 'htpb',
              'oxidizer_type': 'n2o', 'thrust': 2000, 'burn_time': 10,
              'chamber_pressure': 30, 'of_ratio': 6.0}
# ÖH D26 (defter P15B3-02): ``thrust``/``burn_time`` katı ucunda TASARIM
# NOKTASI HEDEFİDİR; bu katsayılarla (a=0,005 / n=0,35) BATES zarfının
# dışında kalıyordu ve taban 7751531'de sessizce düşürülüp başlangıç
# geometrisinin eğrisi 200 ile yayımlanıyordu — buradaki 1500 N hiçbir zaman
# etkili olmadı. Zarf kapısı fail-closed olduğundan gövde ZATEN ÖLÇÜLEN
# geometri kipine çevrildi; yanıt tasarım noktası bloğu dışında BİT-AYNI.
Z5G_KATI = {'motor_name': 'z5g-s', 'chamber_pressure': 40,
            'grain_type': 'bates', 'chamber_diameter': 100,
            'core_diameter': 35, 'grain_length': 300, 'segments': 1,
            'burn_rate_a': 0.005, 'burn_rate_n': 0.35,
            'chamber_temperature': 3000, 'c_star': 1550,
            'propellant_density': 1800, 'propellant_type': 'apcp'}
Z5G_SIVI = {'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'mixture_ratio': 2.3,
            'thrust': 25000, 'chamber_pressure': 70,
            'engine_cycle': 'gas_generator', 'injector_type': 'impinging',
            'contraction_ratio': 4, 'characteristic_length': 1.2,
            'chamber_material': 'inconel_718', 'cooling_type': 'regenerative',
            'nozzle_type': 'bell_80', 'safety_factor': 2.5}

#: Panel koşumu (/analyze_structural_safety) — hibrit tasarımının yakınları.
Z5G_PANEL_ISTEK = {'chamber_pressure': 30, 'chamber_diameter': 0.101,
                   'chamber_length': 0.6, 'throat_diameter': 0.0243,
                   'burn_time': 10, 'material': 'steel_4130',
                   'wall_thickness': 0.0158, 'thrust': 2000}

#: Köprü koşumları küçük mesh ile sürülür (bekçinin işi sayısal hassasiyet
#: değil, hüküm kapısı). Tek tanım — iki koşum da bunu kullanır.
Z5G_KUCUK_MESH = dict(n_axial0=8, n_radial0=3)

#: Yakınsamayı ZORLA açıkta bırakan tolerans (gerçek çözüm, sahte değil):
#: bir turda ulaşılamayacak kadar sıkı. ``converged ⟺ final_rel_change < tol``.
Z5G_ULASILMAZ_TOL = 1e-9


def _sessiz(fn, *a, **kw):
    """Motor modülleri stdout'a bolca basıyor; testte sessize al."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*a, **kw)


# ---------------------------------------------------------------------------
# Kaynak bloğu çıkarıcı — ŞABLONUN KENDİ kodunu koşturmak için
# ---------------------------------------------------------------------------
def _js_blok(kaynak: str, capa: str) -> str:
    """``capa`` dizesinden başlayan ilk ``{...}`` bloğunu AYNEN döndürür.

    Şablonların içindeki gerçek fonksiyonları node altında koşturabilmek
    için gerekir: bekçi kodun KOPYASINI değil KENDİSİNİ çalıştırır (kopya
    çekmiş bekçi, kusuru koruyan bekçidir).
    """
    i = kaynak.find(capa)
    assert i >= 0, f'çapa bulunamadı: {capa!r}'
    j = kaynak.index('{', i)
    derinlik = 0
    for k in range(j, len(kaynak)):
        if kaynak[k] == '{':
            derinlik += 1
        elif kaynak[k] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[i:k + 1]
    raise AssertionError(f'blok kapanmadı: {capa!r}')


def _node(betik: str, *argv, girdi=None) -> dict:
    """node'u geçici dizinde koşturur, JSON çıktısını döndürür."""
    if not NODE:
        pytest.skip('node bulunamadı')
    with tempfile.TemporaryDirectory() as tmp:
        yol = os.path.join(tmp, 'kos.js')
        with open(yol, 'w', encoding='utf-8') as fh:
            fh.write(betik)
        args = [NODE, yol, *[str(a) for a in argv]]
        if girdi is not None:
            veri = os.path.join(tmp, 'girdi.json')
            with open(veri, 'w', encoding='utf-8') as fh:
                json.dump(girdi, fh)
            args.append(veri)
        proc = subprocess.run(args, capture_output=True, text=True,
                              timeout=300)
    assert proc.returncode == 0, 'node çöktü:\n' + proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


#: Sahte DOM + sandbox iskeleti — üç harness da bunu paylaşır.
SANDBOX_JS = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this._a = {};
    this.innerHTML = ''; this.dataset = {}; this.id = '';
}
El.prototype.appendChild = function (x) { this.children.push(x); return x; };
El.prototype.setAttribute = function (k, v) { this._a[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._a, k) ? this._a[k] : null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.addEventListener = function () {};
function kurSandbox(nodes) {
    const doc = {
        head: new El('head'), body: new El('body'), readyState: 'complete',
        createElement: function (t) { return new El(t); },
        querySelector: function () { return null; },
        querySelectorAll: function () { return []; },
        getElementById: function (id) { return nodes[id] || null; },
        addEventListener: function () {},
    };
    const sb = {
        console: { log: function () {}, warn: function () {}, error: function () {} },
        setTimeout: setTimeout, clearTimeout: clearTimeout,
        setInterval: function () {}, clearInterval: clearInterval,
        fetch: function () { return Promise.reject(new Error('sandbox: ag yok')); },
        JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
        String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
        isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
        alert: function () {}, document: doc,
    };
    // ÖH D30 / fix-29b: i18n yardımcıları BURADA tanımlanır. Tarayıcıda
    // ikisi de ``i18n.js``in küreselidir (global.T / global.TF) ve her
    // şablon onları dışarıdan bulur; harness'ın tek tek stub'laması
    // bayatlıyordu — D29 arayuz-panel a3 şablon bloklarına ``TF(...)``
    // ekleyince TF'i tanımlamayan düzenekler "ReferenceError: TF is not
    // defined" ile çöktü. Sözlük yüklü değilken ürünün KENDİ yedek metni
    // kullanılır (ölçüm sayıya/sınıfa/etikete bakar).
    sb.T = function (k, fb) { return fb === undefined ? k : fb; };
    sb.TF = function (k, p, fb) {
        let s = fb === undefined ? k : fb;
        Object.keys(p || {}).forEach(function (n) {
            s = s.split('{' + n + '}').join(String(p[n])); });
        return s;
    };
    sb.window = sb; sb.globalThis = sb;
    vm.createContext(sb);
    return sb;
}
function kosDosya(sb, f) {
    vm.runInContext(fs.readFileSync(f, 'utf8'), sb, { filename: f }); }
function kopya(o) { return JSON.parse(JSON.stringify(o)); }
"""


# ---------------------------------------------------------------------------
# Fikstürler — ağır uçlar modül kapsamında BİR kez koşar
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def hibrit(istemci):
    r = _sessiz(istemci.post, '/calculate', json=Z5G_HIBRIT)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def kati(istemci):
    r = _sessiz(istemci.post, '/calculate_solid', json=Z5G_KATI)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def sivi(istemci):
    pytest.importorskip('rocketcea.cea_obj')
    r = _sessiz(istemci.post, '/calculate_liquid', json=Z5G_SIVI)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def panel_yanit(istemci):
    r = _sessiz(istemci.post, '/analyze_structural_safety',
                json=Z5G_PANEL_ISTEK)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


def _kritikler(kok, ad):
    """``kok[ad]`` listesindeki severity:critical kayıtların kodları."""
    liste = (kok or {}).get(ad)
    if not isinstance(liste, list):
        return []
    return [w.get('code') for w in liste
            if isinstance(w, dict)
            and str(w.get('severity', '')).lower() == 'critical'
            and w.get('code')]


def _termal_mi(kod: str) -> bool:
    """Kod bir TERMAL hüküm mü? (``_critical_thermal_verdicts`` ailesi)"""
    return ('thermal' in kod) or ('over_temp' in kod) or ('melting' in kod)


# ===========================================================================
# P16S1-07 (KRİTİK) — severity:critical TERMAL hükmün TESLİM KANALI
# ===========================================================================
#
# ÖLÇÜLEN KUSUR (defter): hüküm iki dile çevrilmişti ama hiçbir ürün ekranına
# ulaşmıyordu — teslim kanalı YOKTU. Z3 onarımı hükmü
# ``_critical_thermal_verdicts()`` ile ``warnings`` + ``design_warnings``
# kanalına, kimlikle tekilleştirerek taşıdı (katı 0→1, hibrit 0→5).
#
# Bu sınıf kanalın ÜÇ halkasını da kilitler: üretim → kanal → DOM.
# ---------------------------------------------------------------------------
KANAL_ADLARI = ('warnings', 'design_warnings')

APPJS_UYARI_HARNESS = SANDBOX_JS + r"""
const [appJs, payloadPath] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
const nodes = {};
['warningsPanel', 'warningsList'].forEach(function (i) {
    const e = new El('div'); e.id = i; nodes[i] = e; });
const sb = kurSandbox(nodes);
kosDosya(sb, appJs);

function ciz(res) {
    nodes.warningsList.innerHTML = '';
    nodes.warningsPanel.style.display = '';
    sb.displayWarnings(sb.collectResultWarnings(res), res.validation);
    return nodes.warningsList.innerHTML;
}
function olc(dom, kodlar) {
    return {
        oge: (dom.match(/class="warning-item /g) || []).length,
        kritikSinif: (dom.match(/warning-item warning-critical/g) || []).length,
        kritikRozet: (dom.match(/>CRITICAL</g) || []).length,
        kodlar: kodlar.filter(function (k) { return dom.indexOf(k) !== -1; }),
    };
}
const O = {};
const kanal = sb.collectResultWarnings(P.res);
O.toplayici = kanal.length;
O.toplayiciKritik = kanal.filter(sb.warnIsCritical).length;
O.once = olc(ciz(P.res), P.kodlar);

// MUTASYON (yanıt kopyası üstünde; ÜRÜN DOSYASINA DOKUNULMAZ):
// kritik termal hükümler kanaldan silinirse ekrandan da düşmeli.
const m = kopya(P.res);
['warnings', 'design_warnings', 'input_warnings'].forEach(function (ad) {
    if (m.motor && Array.isArray(m.motor[ad])) {
        m.motor[ad] = m.motor[ad].filter(function (w) {
            return P.kodlar.indexOf(w && w.code) === -1; }); }
    if (Array.isArray(m[ad])) {
        m[ad] = m[ad].filter(function (w) {
            return P.kodlar.indexOf(w && w.code) === -1; }); }
});
O.sonra = olc(ciz(m), P.kodlar);
process.stdout.write(JSON.stringify(O));
"""

SOLID_UYARI_HARNESS = SANDBOX_JS + r"""
const [payloadPath] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
const nodes = {};
['warningsPanel', 'warningsPanelBody'].forEach(function (i) {
    const e = new El('div'); e.id = i; nodes[i] = e; });
const sb = kurSandbox(nodes);
// i18n yardımcıları kurSandbox'tan gelir (tek tanım noktası).
vm.runInContext(P.fnKaynak, sb, { filename: 'solid.html#displaySolidWarnings' });

function ciz(res) {
    nodes.warningsPanelBody.innerHTML = '';
    nodes.warningsPanel.style.display = '';
    sb.displaySolidWarnings(res);
    return { dom: nodes.warningsPanelBody.innerHTML,
             gorunur: nodes.warningsPanel.style.display };
}
function olc(c, kodlar) {
    return {
        gorunur: c.gorunur,
        oge: (c.dom.match(/class="warning-item /g) || []).length,
        kritikSinif: (c.dom.match(/warning-item warning-critical/g) || []).length,
        kritikRozet: (c.dom.match(/>CRITICAL</g) || []).length,
        sayacKritik: /(\d+)\s+critical/.exec(c.dom),
        kodlar: kodlar.filter(function (k) { return c.dom.indexOf(k) !== -1; }),
    };
}
const O = {};
O.once = olc(ciz(P.res), P.kodlar);
const m = kopya(P.res);
['warnings', 'validation_warnings', 'safety_warnings'].forEach(function (ad) {
    if (Array.isArray(m[ad])) {
        m[ad] = m[ad].filter(function (w) {
            return P.kodlar.indexOf(w && w.code) === -1; }); }
});
if (m.nozzle_material_analysis
        && Array.isArray(m.nozzle_material_analysis.warnings)) {
    m.nozzle_material_analysis.warnings =
        m.nozzle_material_analysis.warnings.filter(function (w) {
            return P.kodlar.indexOf(w && w.code) === -1; });
}
O.sonra = olc(ciz(m), P.kodlar);
process.stdout.write(JSON.stringify(O));
"""


@pytest.fixture(scope='module')
def hibrit_kritik_termal(hibrit):
    """Hibritin İKİ kanalındaki kritik TERMAL hüküm kodları."""
    motor = hibrit.get('motor') or {}
    return {ad: [k for k in _kritikler(motor, ad) if _termal_mi(k)]
            for ad in KANAL_ADLARI}


@pytest.fixture(scope='module')
def kati_kritik_termal(kati):
    return {ad: [k for k in _kritikler(kati, ad) if _termal_mi(k)]
            for ad in KANAL_ADLARI}


class TestP16S1_07TeslimKanali:
    """severity:critical TERMAL hüküm üretim → kanal → DOM."""

    def test_hibrit_iki_kanalda_da_kritik_termal_hukum_var(
            self, hibrit_kritik_termal):
        """ÜRETİM + KANAL: hüküm iki kanalda da, kimlikle TEKİL."""
        for ad in KANAL_ADLARI:
            kodlar = hibrit_kritik_termal[ad]
            assert kodlar, (
                f'hibrit {ad} kanalında kritik TERMAL hüküm yok — '
                'P16S1-07 teslim kanalı koptu')
            assert len(kodlar) == len(set(kodlar)), (
                f'{ad} kanalında AYNI hüküm iki kez basılmış: {kodlar}')
        assert (set(hibrit_kritik_termal['warnings'])
                == set(hibrit_kritik_termal['design_warnings'])), (
            'iki kanal ayrışıyor; birinin düşmesi hükmü sessizleştirir')

    def test_kati_iki_kanalda_da_kritik_termal_hukum_var(
            self, kati_kritik_termal):
        for ad in KANAL_ADLARI:
            kodlar = kati_kritik_termal[ad]
            assert kodlar, (
                f'katı {ad} kanalında kritik TERMAL hüküm yok — '
                'P16S1-07 katı ayağı koptu')
            assert len(kodlar) == len(set(kodlar)), (
                f'{ad} kanalında AYNI hüküm iki kez basılmış: {kodlar}')

    @pytest.mark.skipif(not NODE, reason='node bulunamadı')
    def test_hibrit_hukum_appjs_uyari_domuna_iniyor(self, hibrit,
                                                   hibrit_kritik_termal):
        """DOM: app.js kanalı hükmü KRİTİK rozetiyle basıyor."""
        kodlar = sorted(set(hibrit_kritik_termal['warnings']))
        assert kodlar, 'kanal boş — bu ölçüm boşa dönerdi (fail-closed)'
        olcum = _node(APPJS_UYARI_HARNESS, STATIK / 'app.js',
                      girdi={'res': hibrit, 'kodlar': kodlar})
        assert olcum['once']['kodlar'] == kodlar, (
            'kritik termal hüküm kodlarının hepsi DOM\'a inmiyor: '
            f"inen {olcum['once']['kodlar']}, beklenen {kodlar}")
        assert olcum['once']['kritikRozet'] >= len(kodlar), (
            'hüküm ekranda KRİTİK rozeti almıyor (amber\'e düşmüş): '
            f"{olcum['once']}")
        assert olcum['once']['kritikSinif'] >= len(kodlar)

    @pytest.mark.skipif(not NODE, reason='node bulunamadı')
    def test_hibrit_hukum_kanaldan_silinirse_ekrandan_duser(
            self, hibrit, hibrit_kritik_termal):
        """MUTASYON: kanal boşalırsa DOM da boşalır (bekçi ölçüyor)."""
        kodlar = sorted(set(hibrit_kritik_termal['warnings']))
        assert kodlar, 'kanal boş — mutasyon ölçümü anlamsız olurdu'
        olcum = _node(APPJS_UYARI_HARNESS, STATIK / 'app.js',
                      girdi={'res': hibrit, 'kodlar': kodlar})
        assert olcum['sonra']['kodlar'] == [], (
            'hüküm kanaldan silindiği hâlde DOM\'da duruyor — bekçi ölçmüyor')
        assert olcum['sonra']['kritikRozet'] < olcum['once']['kritikRozet'], (
            'kritik rozet sayısı mutasyona duyarsız: '
            f"{olcum['once']} -> {olcum['sonra']}")

    @pytest.mark.skipif(not NODE, reason='node bulunamadı')
    def test_kati_hukum_sablonun_kendi_panelinde(self, kati,
                                                 kati_kritik_termal):
        """DOM: ``solid.html``in KENDİ ``displaySolidWarnings``ı koşturulur.

        Katı motorun yanıtı üst düzeydir (``motor`` bloğu yok) ve
        ``app.js/collectResultWarnings`` ``r.motor.warnings`` okur; katı
        ayağının teslim kanalı bu yüzden ŞABLONUN kendi fonksiyonudur.
        Bekçi o fonksiyonun kendisini çalıştırır (kopyasını değil).
        """
        kaynak = (SABLON / 'solid.html').read_text(encoding='utf-8')
        fn = _js_blok(kaynak, 'function displaySolidWarnings(results)')
        kodlar = sorted(set(kati_kritik_termal['warnings']))
        assert kodlar, 'katı kanalı boş — bu ölçüm boşa dönerdi'
        olcum = _node(SOLID_UYARI_HARNESS,
                      girdi={'res': kati, 'kodlar': kodlar, 'fnKaynak': fn})
        assert olcum['once']['kodlar'] == kodlar, (
            'katı termal hüküm şablon paneline inmiyor: '
            f"{olcum['once']}")
        assert olcum['once']['kritikRozet'] >= len(kodlar), (
            f"katı hüküm KRİTİK etiketi almıyor: {olcum['once']}")
        assert olcum['once']['gorunur'] == 'block', (
            'kritik hüküm varken uyarı paneli gizli kalıyor')
        sayac = olcum['once']['sayacKritik']
        assert sayac and int(sayac[1]) >= len(kodlar), (
            f'panel başlığındaki kritik sayacı hükmü saymıyor: {sayac}')

    @pytest.mark.skipif(not NODE, reason='node bulunamadı')
    def test_kati_hukum_silinirse_panel_kritigi_dusuyor(
            self, kati, kati_kritik_termal):
        kaynak = (SABLON / 'solid.html').read_text(encoding='utf-8')
        fn = _js_blok(kaynak, 'function displaySolidWarnings(results)')
        kodlar = sorted(set(kati_kritik_termal['warnings']))
        assert kodlar, 'katı kanalı boş — mutasyon ölçümü anlamsız olurdu'
        olcum = _node(SOLID_UYARI_HARNESS,
                      girdi={'res': kati, 'kodlar': kodlar, 'fnKaynak': fn})
        assert olcum['sonra']['kodlar'] == [], (
            'hüküm kaynaklardan silindiği hâlde panelde duruyor')
        assert (olcum['sonra']['kritikRozet']
                < olcum['once']['kritikRozet']), (
            f"panel mutasyona duyarsız: {olcum['once']} -> {olcum['sonra']}")


# ===========================================================================
# P17B1-01 (KRİTİK) — /hybrid erime hükmü ile yapısal yeşilin AYNI EKRANI
# ===========================================================================
#
# Turun raporu: termal panel kırmızı "EXCEEDS MELTING POINT (3040 K)" ⟷
# yapısal panel AYNI cidara yeşil "MIN SF 12.77" — ve sayfa 15/15 GEÇTİ.
# Kapanış şartı görsel kapı turudur; burada TUR YERİNE GEÇEN makine ölçümü
# yazılır: hükmün üretildiği, ekrana indiği ve yapısal sayının artık
# hangi koşumdan geldiğini söylediği kilitlenir.
# TUR İMZASI FABLE DENETİMİNDE (bu bekçi turun yerine geçmez, onu bekler).
# ---------------------------------------------------------------------------
class TestP17B1_01HibritErimeHukmu:

    def test_erime_hukmu_uretiliyor_ve_beyanli(self, hibrit):
        """ÜRETİM: erime aşımı bayrağı + sıcaklıklar + kritik uyarı kodu."""
        motor = hibrit.get('motor') or {}
        sa = motor.get('structural_analysis') or {}
        derating = (sa.get('thermal_analysis') or {}).get('strength_derating')
        assert isinstance(derating, dict), (
            'strength_derating bloğu yok — erime hükmünün girdisi kayıp')
        assert derating.get('exceeds_melting_point') is True, (
            'bu koşum erime aşımı üretmiyor; kalemin vakası kayboldu: '
            f'{derating.get("exceeds_melting_point")!r}')
        erime = derating.get('melting_point_K')
        tepe = (sa.get('safety_analysis') or {}).get('peak_wall_temperature_K')
        assert isinstance(erime, (int, float)) and erime > 0
        assert isinstance(tepe, (int, float)), (
            'tepe cidar sıcaklığı yayımlanmıyor — bayrak sayısız kalıyor')
        assert tepe > erime, (
            f'bayrak açık ama sayı aşmıyor ({tepe} <= {erime}) — '
            'beyan ile sayı çelişiyor')
        kodlar = _kritikler(motor, 'warnings')
        assert any('melting' in k for k in kodlar), (
            f'erime hükmü uyarı kanalına konmamış: {kodlar}')

    @pytest.mark.skipif(not NODE, reason='node bulunamadı')
    def test_erime_hukmu_ekrana_iniyor(self, hibrit):
        """TAŞIMA (tur yerine geçen ölçüm): hüküm DOM'da ve KRİTİK."""
        motor = hibrit.get('motor') or {}
        kodlar = sorted({k for k in _kritikler(motor, 'warnings')
                         if 'melting' in k})
        assert kodlar, 'erime kodu yok — üretim testi de kırılmalıydı'
        olcum = _node(APPJS_UYARI_HARNESS, STATIK / 'app.js',
                      girdi={'res': hibrit, 'kodlar': kodlar})
        assert olcum['once']['kodlar'] == kodlar, (
            'erime hükmü ekrana inmiyor (turun ölçtüğü kusur geri geldi)')
        assert olcum['once']['kritikRozet'] >= 1
        assert olcum['sonra']['kodlar'] == [], (
            'mutasyon ölçmüyor: hüküm silindiği hâlde ekranda')

    @pytest.mark.skipif(not NODE, reason='node bulunamadı')
    def test_yapisal_sayi_artik_kaynaksiz_degil(self, hibrit, panel_yanit,
                                                panel_olcum):
        """Turdaki çelişkinin ikinci yarısı: yeşil SF hangi koşumdan?

        Erime kırmızısıyla yan yana duran yapısal sayı, artık kendi uç
        adını taşır (P17B3-06 mekanizması). Böylece "aynı cidara iki
        hüküm" görüntüsü kaynaksız kalmıyor.
        """
        assert panel_olcum['ayrikKunye']['panelUcu'], (
            'yapısal SF satırı hangi koşumdan geldiğini söylemiyor')
        assert panel_olcum['ayrikKunye']['motorUcu'], (
            'motor koşumunun sayısı panelde uç adı olmadan duruyor')


# ===========================================================================
# P17B1-02 (KRİTİK) — YAKINSAMAMIŞ ÇÖZÜM HÜKÜM VEREMEZ
# ===========================================================================
@pytest.fixture(scope='module')
def kopru_saglikli(hibrit):
    from hrma.fea import bridge as fea_bridge
    return _sessiz(fea_bridge.run_structural_from_motor, hibrit.get('motor'),
                   max_rounds=2, **Z5G_KUCUK_MESH)


@pytest.fixture(scope='module')
def kopru_saglikli_ayrisan(hibrit):
    """``kopru_saglikli`` ile AYNI motor ve mesh, birincil kip ``z_max``.

    ARAÇ (fea-yuk 2. tur, 14 Eki; karar §28-18 (B), kart OH-DK-04): eski
    sabit-P_c yükünde bu koşumda ``z_max`` kötümserdi ve birincilden BAŞKA
    olarak yayımlanıyordu; o ayrışma ıraksaktaki yapay net eksenel
    kuvvetten geliyordu. Doğru yükte (izantropik P(x) + kapalı uç)
    ``z_min`` hafifçe kötümser (38,4017 ⟷ 38,4146) ve varsayılan koşuda
    yayımlanan = birincil. Birincil kip ürün parametresiyle ``z_max``
    seçilince yayımlanan kip ``z_min`` olur — P8B1-09 kilidinin aradığı
    "yayımlanan ≠ birincil" vakası (tests/fea/yuk_modeli_araci.py).
    """
    from hrma.fea import bridge as fea_bridge
    from tests.fea.yuk_modeli_araci import ARAC_BIRINCIL_KIP, izantropik_yukte
    s = _sessiz(fea_bridge.run_structural_from_motor, hibrit.get('motor'),
                axial_fix=ARAC_BIRINCIL_KIP, max_rounds=2, **Z5G_KUCUK_MESH)
    izantropik_yukte(s)
    return s


@pytest.fixture(scope='module')
def kopru_yakinsamamis(hibrit):
    """AYNI motor, ulaşılamaz tolerans → gerçek yakınsamama (uydurma yok)."""
    from hrma.fea import bridge as fea_bridge
    return _sessiz(fea_bridge.run_structural_from_motor, hibrit.get('motor'),
                   tol=Z5G_ULASILMAZ_TOL, max_rounds=1, **Z5G_KUCUK_MESH)


@pytest.fixture(scope='module')
def kopru_hukum_verilen(istemci):
    """HÜKÜM VERİLEN koşum — kapının POZİTİF yakasının kanıtı.

    FİKSTÜR İKİNCİ KEZ TAŞINDI (ÖH D24, OH-D15-02) — İDDİA DEĞİŞMEDİ.

    Önceki hâl KATI motor + ``axial_fix='z_max'`` + ``max_rounds=6``
    koşumuydu ve ``final_rel_change=0,0073954`` ile "yakınsadı" sayılıyordu.
    O kabul, ``solve_with_refinement``in TEK TURLUK kabul ölçütüne
    dayanıyordu; ölçüt OH-D15-02'de sıkılaştırıldı (tolerans altında
    ARDIŞIK ``REFINE_ONAY_ARDISIK_TUR`` tur gerekli, gerekçesi sabitin
    başındaki ölçüm) ve bu koşum artık ONAY TURUNU TAMAMLAYAMIYOR.

    ÖLÇÜLDÜ (D24, kanıt ``docs/scofield/raw/OH/D24/fea-cfd/a1/``): eski
    fikstür 12 turda gösterge dizisini
    ``… 0,032681 → 0,015477 → 0,009092`` diye bitiriyor; son tur tolerans
    altında (sayaç 1) ama ONAYLAYACAK 13. tur YOK — inceltme sondası bu
    kontur/kalınlıkta 1024×48'den sonra meshlenemiyor (``sonda_hatalari``),
    yani "bir tur daha koş" çaresi bu geometride YOK. Ürünü hüküm
    verdirecek şekilde gevşetmek YASAKTIR (fail-closed kazanır); bunun
    yerine hükmün güçlendirilmiş ölçütle GERÇEKTEN verildiği bir koşum
    ölçülerek bulundu:

    SIVI motor (``Z5G_SIVI``), köprü VARSAYILANLARIYLA. Yayımlanan kip
    BİRİNCİL kiple AYNIdır (``z_min``; kötümser seçim onu seçiyor), yani
    P8B1-09'un şartı — "yayımlanan kip KENDİ mesh yakınsamasını
    kanıtlamalı" — inceltme çalışmasının kendisiyle karşılanır; hiçbir
    kapı gevşetilmez.

    ÖLÇÜLDÜ (D24): ``verildi=True``, ``converged=True``,
    ``converged_birincil_kip=True``, ``converged_yayimlanan_kip=True``,
    ``geri_cekme_gerekceleri=[]``, 9 tur, 16.384 eleman,
    ``final_rel_change=0,00570121289883224`` (tolerans 0,01),
    ``min_safety_factor=1,027440053272749``. Onay turu GERÇEKTEN
    tamamlandı: son iki tur 0,008746 ve 0,005701, ikisi de tol altında
    (``onay_ardisik_tur_sayaci=2``) ve dizi tekdüze azalıyor — yani bu
    kabul bir yerel çukur değil.
    """
    pytest.importorskip('rocketcea.cea_obj')
    from hrma.fea import bridge as fea_bridge
    # /calculate_liquid sonucu 'motor' sarmalayıcısı olmadan üst düzeyde
    # döner (hibritin aksine); köprüye yanıtın kendisi verilir.
    r = _sessiz(istemci.post, '/calculate_liquid', json=Z5G_SIVI_HUKUM)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return _sessiz(fea_bridge.run_structural_from_motor, r.get_json())


#: Pozitif yakanın KENDİ sıvı koşumu (ÖH D25, OH-D24-01 — ÜÇÜNCÜ TAŞIMA).
#: Gerekçe ölçüldü: hüküm büyüklüğü ASME VIII-2 Ek 5-A lineerleştirmesine
#: geçince (max(1,5·P_m, P_L+P_b)) ``Z5G_SIVI`` koşumu (25 kN / 70 bar /
#: inconel_718) birincil kipte ONAY TURUNU tamamlayamıyor
#: (``geri_cekme_gerekceleri=['not_converged']``). Ürünü hüküm verdirecek
#: şekilde GEVŞETMEK yasak; bu yüzden hükmün YENİ ve DAHA SIKI ölçütle
#: GERÇEKTEN kazanıldığı bir koşum ölçülerek bulundu: aşağıdaki 5 kN /
#: 20 bar / bell_80 koşumu ``verildi=True`` ve
#: ``geri_cekme_gerekceleri=[]`` döndürüyor (kanıt
#: docs/scofield/raw/OH/D25/fea-cfd/a1/rapor.md §5). Fikstürün iddiaları
#: AYNEN korundu.
#:
#: DÖRDÜNCÜ TAŞIMA (ÖH D27 a1, OH-D25-28 / OH-D24-01) — İDDİA DEĞİŞMEDİ.
#: İç kontur köşe tabanı ürün varsayılanı olunca 5 kN / 20 bar koşumu
#: hükmü KAYBETTİ, ama SEBEBİ yakınsama DEĞİL: ölçüldü —
#: ``geri_cekme_gerekceleri=['kisit_yeri_duyarliligi_yuksek']``,
#: ``converged_yayimlanan_kip`` rel_change 0,001116 < tol 0,01 (yani
#: P17B1-02 kapısı sağlam, geri çekme kısıt-yeri kapısından geliyor).
#: Ürünü hüküm verdirecek şekilde GEVŞETMEK yasak; hükmün varsayılan
#: AÇIKKEN gerçekten kazanıldığı koşum ölçülerek bulundu: 8 kN / 25 bar /
#: eps=8 → ``verildi=True``, ``geri_cekme_gerekceleri=[]``,
#: ``converged_birincil_kip=True``, ``converged_yayimlanan_kip=True``,
#: ``final_rel_change=0,00144`` (tol 0,01), ``onay_ardisik_tur_sayaci=2``
#: (gerekli 2), mesh 1024×4, ``min_safety_factor=6,5377``. Fikstürün
#: iddiaları AYNEN korundu (kanıt docs/scofield/raw/OH/D27/fea-cfd/a1/).
#:
#: ÖH D28 / OH-D27-06 — BEŞİNCİ TAŞIMA OLMASIN DİYE: bu gövde artık ürün
#: kodundaki KANONİK KAYITTAN (``hrma.fea.bridge.
#: HUKUM_KAZANILAN_KANONIK_VAKA``) tek kaynaklıdır. Aşağıdaki sözlük o
#: kaydın ``govde`` alanının aynısıdır ve iki yazımın sessizce ayrışması
#: mekanik olarak yasaklandı (``TestOHD2706KanonikHukumVakasi::
#: test_FIKSTUR_kanonik_kayittan_TEK_KAYNAK``). Modül gövdesinde ``hrma``
#: içe aktarılmaz (bu dosyanın kuralı: içe aktarımlar tembeldir), bu
#: yüzden bağ bir içe aktarımla değil bir BEKÇİYLE kuruldu; ayrışma
#: mümkün değildir çünkü ayrışınca test kırmızı verir.
Z5G_SIVI_HUKUM = {'motor_name': 'Z5G-HUKUM', 'fuel_type': 'rp1',
                  'oxidizer_type': 'lox', 'mixture_ratio': 2.3,
                  'thrust': 8000, 'chamber_pressure': 25,
                  'expansion_ratio': 8.0, 'burn_time': 10}


class TestOHD2706KanonikHukumVakasi:
    """Hüküm kazanılan vaka ELLE TAŞINMAZ — kayıtlıdır ve KEŞFEDİLİR.

    Pozitif yaka fikstürü dört kez elle arandı (P8B1-09 → OH-D15-02 →
    OH-D24-01 → OH-D25-28). Her seferinde iş aynıydı: ürün sıkılaştı,
    o günkü fikstür hükmü kaybetti, dalga elle bir motor arayıp yazdı.
    Aranan vaka hiçbir yerde kayıt olarak durmadığı için arama her
    seferinde SIFIRDAN yapıldı.

    Bu sınıf o döngüyü kırar: kanonik vaka ürün kodunda kayıtlıdır ve
    kanonik vaka bir gün hükmü kaybederse bu bekçi kayıttaki ARAMA
    IZGARASINI tarar ve kazanan vakayı ADIYLA söyleyerek kırmızı verir.
    Sonraki dalga elle aramaz; ölçülmüş bir vakayı kopyalar.

    Bekçi ürünü GEVŞETMEZ: hiçbir kapıya dokunmaz, yalnız pozitif yakanın
    NEREDE olduğunu ölçer. Izgaranın tamamı kaybederse kırmızı KALIR —
    "hiçbir motorda hüküm veremeyen köprü" sessizce geçemez.
    """

    @staticmethod
    def _kosum(istemci, govde):
        from hrma.fea import bridge as fea_bridge
        r = _sessiz(istemci.post, '/calculate_liquid', json=govde)
        if r.status_code != 200:
            return None
        p = _sessiz(fea_bridge.run_structural_from_motor, r.get_json())
        return (p.get('meta') or {}).get('hukum') or {}

    def test_FIKSTUR_kanonik_kayittan_TEK_KAYNAK(self):
        """Fikstür ile ürün kaydı BİT-AYNI (iki yazım ayrışamaz)."""
        from hrma.fea.bridge import HUKUM_KAZANILAN_KANONIK_VAKA as K
        assert K['uc'] == '/calculate_liquid'
        assert K['govde'] == Z5G_SIVI_HUKUM, (
            'kanonik kayıt ile fikstür AYRIŞTI — biri elle değiştirilmiş. '
            'Hüküm vakası TEK KAYNAKTAN gelir: önce kaydı ölçüp güncelle, '
            f'sonra fikstürü ondan kopyala.\nkayıt : {K["govde"]}\n'
            f'fikstür: {Z5G_SIVI_HUKUM}')
        # Kayıt bir KÜNYE taşımak zorunda: ölçüm nerede, hangi dalga koydu.
        assert K['kanit'].startswith('docs/scofield/raw/'), K['kanit']
        assert K['kayit_dalgasi']
        assert len(K['arama_izgarasi']) >= 5, (
            'arama ızgarası bir vakaya indirgenmiş — kanonik vaka düşerse '
            'keşfedecek yer kalmaz')
        assert tuple(K['arama_izgarasi'][0]) == (
            K['govde']['thrust'], K['govde']['chamber_pressure'],
            K['govde']['expansion_ratio']), (
            'ızgaranın ilk adayı kanonik vakanın KENDİSİ olmalı')

    def test_KANONIK_vaka_hukmu_HALA_kazaniyor_yoksa_YENISINI_SOYLER(
            self, istemci):
        """Kanonik vaka hükmü kazanmalı; kaybederse kazananı KEŞFEDER.

        Mutlu yol tek koşumdur (ölçüldü: ~1-4 s). Izgara taraması ancak
        kanonik vaka düştüğünde koşar — yani bu bekçi kırmızıya dönerken
        aynı zamanda ONARIMIN ADRESİNİ de üretir.
        """
        pytest.importorskip('rocketcea.cea_obj')
        from hrma.fea.bridge import HUKUM_KAZANILAN_KANONIK_VAKA as K
        h = self._kosum(istemci, K['govde'])
        assert h is not None, '/calculate_liquid kanonik gövdede 200 dönmedi'
        if h.get('verildi') is True:
            # Kaydın iddiaları AYNEN doğrulanır (sayı değil, YAPI: float
            # çapası platformlar arası kayar, hüküm yapısı kaymaz).
            o = K['olculen']
            assert h['geri_cekme_gerekceleri'] == o['geri_cekme_gerekceleri']
            assert h['converged_birincil_kip'] is o['converged_birincil_kip']
            assert h['converged_yayimlanan_kip'] is o[
                'converged_yayimlanan_kip']
            assert h['min_safety_factor'] is not None
            return
        # --- KEŞİF: kanonik vaka düştü, kazananı ARA ---------------------
        kazananlar = []
        for thrust, pc, er in K['arama_izgarasi']:
            aday = dict(K['govde'], thrust=thrust, chamber_pressure=pc,
                        expansion_ratio=er)
            ha = self._kosum(istemci, aday)
            if ha and ha.get('verildi') is True:
                kazananlar.append((thrust, pc, er,
                                   ha.get('min_safety_factor')))
        assert not kazananlar, (
            'KANONİK HÜKÜM VAKASI DÜŞTÜ (geri çekme gerekçeleri: '
            f'{h.get("geri_cekme_gerekceleri")}). ELLE ARAMAYIN — ızgarada '
            f'hüküm KAZANAN vaka(lar) ölçüldü: {kazananlar} '
            '(thrust N, Pc bar, eps, min_safety_factor). '
            'hrma.fea.bridge.HUKUM_KAZANILAN_KANONIK_VAKA kaydını bu '
            'ölçümle güncelleyin (govde + olculen + kanit + kayit_dalgasi), '
            'sonra Z5G_SIVI_HUKUM fikstürünü kayıttan kopyalayın.')
        pytest.fail(
            'KANONİK HÜKÜM VAKASI DÜŞTÜ ve ARAMA IZGARASINDA HİÇBİR VAKA '
            'HÜKÜM KAZANMIYOR. Bu bir fikstür sorunu DEĞİL: köprü artık '
            'hiçbir motorda hüküm veremiyor demektir. Kapıları gevşetmek '
            'YASAK; kapıların hangisinin kazanılamaz hâle geldiği ölçülüp '
            f'onarılmalı. Kanonik gerekçeler: {h.get("geri_cekme_gerekceleri")}')


class TestP17B1_02YakinsamaKapisi:

    def test_yakinsayan_cozum_hukum_verir(self, kopru_hukum_verilen):
        """Kapının POZİTİF yakası: yakınsayan çözüm hüküm VERİR.

        FİKSTÜR DEĞİŞTİ (ÖH D15 fix-3 → ÖH D24 OH-D15-02) — İDDİA
        DEĞİŞMEDİ. Fikstürün taşınma gerekçesi ve ölçülen sayılar
        ``kopru_hukum_verilen`` docstring'indedir; kısaca: eski koşum
        güçlendirilmiş yakınsama ölçütünün ONAY TURUNU tamamlayamıyor ve
        ürünü hüküm verdirecek şekilde gevşetmek YASAK. Altı iddia AYNEN
        korundu; üzerine OH-D15-02'nin kazanımı eklendi (kabul tek tura
        değil, ardışık turlara dayanmalı).
        """
        h = kopru_hukum_verilen.get('verdict')
        assert isinstance(h, dict), 'köprü üst düzeyde verdict yayımlamıyor'
        assert h['converged'] is True
        assert h['verildi'] is True
        assert h['geri_cekme_gerekceleri'] == []
        assert isinstance(h['min_safety_factor'], float)
        # P8B1-09 gevşetilmedi: hüküm İKİ kipin de yakınsamasıyla verildi.
        assert h['converged_birincil_kip'] is True
        assert h['converged_yayimlanan_kip'] is True
        # OH-D15-02: bu POZİTİF yaka bir YEREL ÇUKURDAN geçmiş olamaz —
        # kabul, tolerans altında ARDIŞIK turlarla kazanılmış olmalı.
        yak = kopru_hukum_verilen['meta']['yakinsama']
        assert yak['onay_ardisik_tur_sayaci'] >= yak[
            'onay_ardisik_tur_gerekli'], (
            'hüküm verildi ama kabul ardışık tur onayına dayanmıyor — '
            f'tek turluk çukurdan geçilmiş olabilir: {yak}')

    def test_yakinsamayan_cozum_hukum_veremez(self, kopru_yakinsamamis):
        """KAPI: converged=False → verildi=False + ADLI gerekçe."""
        h = kopru_yakinsamamis.get('verdict')
        assert isinstance(h, dict)
        assert h['converged'] is False, (
            'zorlanan koşum yakınsadı — kapı bu vakayla sınanamıyor')
        assert h['verildi'] is False, (
            'yakınsamamış çözümden hüküm çıkıyor (P17B1-02 geri geldi)')
        assert 'not_converged' in h['geri_cekme_gerekceleri']
        assert h['tol'] == Z5G_ULASILMAZ_TOL
        assert (h['final_rel_change'] or 0.0) >= h['tol']

    def test_sayilar_silinmez_gerekce_okunur(self, kopru_yakinsamamis):
        """Hüküm geri çekilir, SAYI silinmez — ve gerekçesi metinde durur."""
        h = kopru_yakinsamamis['verdict']
        assert h['min_safety_factor'] is not None, (
            'sayı silinmiş; sözleşme "hüküm geri çekilir, sayı kalır"')
        assert kopru_yakinsamamis['min_safety_factor'] is not None
        beyan = h['beyan']
        assert 'GERİ ÇEKİLDİ' in beyan and 'not_converged' in beyan, beyan[:200]

    def test_kapi_yanittan_bagimsiz_degil(self, kopru_hukum_verilen,
                                          kopru_yakinsamamis):
        """Kapı ÖLÇÜYOR: bir koşumda hüküm verilir, ötekinde geri çekilir.

        FİKSTÜR DEĞİŞTİ (ÖH D15 fix-3) — İDDİA GÜÇLENDİ. Eski hâl iki
        HİBRİT koşumu kıyaslıyordu ve ikisi de hüküm veremez duruma
        düşünce bekçi "kapı ölçmüyor" diye kırmızı yandı; kırmızının
        söylediği doğruydu ama sebep kapının bozulması DEĞİL, iki koşumun
        da fail-closed yakada olmasıydı. Artık POZİTİF yaka gerçekten
        hüküm veren bir koşumdan geliyor (``kopru_hukum_verilen``) ve
        ayrım hem bayrakta hem GEREKÇE KÜMESİNDE ölçülüyor.
        """
        verilen = kopru_hukum_verilen['verdict']
        cekilen = kopru_yakinsamamis['verdict']
        assert verilen['verildi'] != cekilen['verildi'], (
            'kapı iki koşumda da aynı sonucu veriyor — ölçmüyor')
        assert verilen['geri_cekme_gerekceleri'] == []
        assert cekilen['geri_cekme_gerekceleri'], (
            'geri çekilen hüküm gerekçesiz — kapı sessiz reddediyor')
        assert (verilen['geri_cekme_gerekceleri']
                != cekilen['geri_cekme_gerekceleri'])

    def test_hukum_geri_cekme_gerekcesi_ADLI_ve_fail_closed(
            self, kopru_saglikli_ayrisan):
        """P8B1-09 kilidi: YAYIMLANAN kip kendi yakınsamasını kanıtlamalı.

        ÖH D15 fix-3 (1 Eyl 2026) — ÖLÇÜM KAYDI. ``kopru_saglikli``
        (hibrit, ``n_axial0=8/n_radial0=3``) eskiden bu sınıfın "sağlıklı"
        koşumuydu; bu ağaçta hüküm ÜRETMİYOR ve nedeni ÜRÜN KUSURU DEĞİL,
        ölçülmüş bir SAYISAL GERÇEKTİR:

        * Yayımlanan kip ``z_max``tır (kötümser seçim, P8B2-09) ve tepe
          düğüm von Mises'i mesh inceltmesiyle YAKINSAMIYOR, BÜYÜYOR —
          ölçüldü (aynı kontur, aynı yük):
          16×12 → 13,376 MPa · 32×24 → 13,831 · 64×24 → 15,026 ·
          128×24 → 15,663 MPa. Aynı mesh dizisinde birincil kip ``z_min``
          10,947 → 11,009 MPa ile YAKINSIYOR. Ardışık bağıl değişim
          (64×24 ⟷ 32×24): z_min %0,097 · z_max %8,639.
        * İnceltme doğrudan ``z_max`` ile sürüldüğünde de yakınsamıyor:
          ``max_rounds=4`` → 256×24'te bağıl değişim %1,51 ·
          ``max_rounds=6`` → 1024×96'da %9,31 ve SF 29,06 → 24,57.
          Yani "tur sayısını artırın" öğüdü bu kip için işe YARAMAZ;
          kısıtlanan uçtaki tepe bir mesh tekilliğidir.

        Sonuç: ürünün hükmü GERİ ÇEKMESİ DOĞRUDUR ve bu bekçi o
        fail-closed davranışı kilitler. Kapıyı gevşetip (ör.
        ``yayimlanan_kip_yakinsamadi``yı gerekçe listesinden düşürüp) bu
        koşuma hüküm verdirmek, YAKINSAMAMIŞ bir tepe gerilmeden
        "tasarım güvenlidir" demek olurdu — P17B1-02'nin kapattığı kusurun
        ta kendisi. Kapının pozitif yakası ``kopru_hukum_verilen``
        fikstürüyle ayrıca kanıtlanır.
        """
        # ARAÇ UYARLANDI (fea-yuk 2. tur): fikstür ``kopru_saglikli_ayrisan``
        # (AYNI motor ve mesh, birincil kip ``z_max``; docstring'i). Kilidin
        # iddiaları AYNEN sınanıyor.
        h = kopru_saglikli_ayrisan['verdict']
        kd = kopru_saglikli_ayrisan['meta']['kisit_duyarliligi']

        assert kd['yayimlanan_kip'] != kd['birincil_kip'], (
            'bu fikstür kötümser kipin yayımlandığı vakadır; ön koşul '
            f'kayboldu: {kd.get("yayimlanan_kip")!r}')
        yk = kd['yayimlanan_kip_yakinsamasi']
        assert yk['olculdu'] is True, (
            'yayımlanan kip için mesh yakınsaması ÖLÇÜLMEDİ — P8B1-09 '
            'kazanımı (başka kipin geçmişinden devralma yasağı) kayıp')
        assert yk.get('kaba_mesh'), (
            'yakınsama kıyası hangi kaba mesh\'e karşı yapıldı, '
            'söylenmiyor — devralma yasağı ölçülemez')

        # --- ÇEVRİLDİ (ÖH D25, OH-D24-01) — GEREKÇE ÖLÇÜLDÜ -------------
        # Bu bekçi eskiden ``yk['yakinsadi'] is False`` ve buna bağlı
        # olarak hükmün geri çekilmesini KİLİTLİYORDU. Kilit, kapının
        # HAM TEPEYİ (ASME "F") de ölçmesine dayanıyordu; D25 ölçümü ham
        # tepenin geometrik süreksizlikte TANIM GEREĞİ yakınsamadığını
        # gösterdi (katı motor, tekdüze merdiven 64x4→512x32: gözlenen
        # mertebe p ≈ 0,12, son adım hâlâ %4,0 — kanıt
        # docs/scofield/raw/OH/D25/fea-cfd/a1/teshis_scl.json). Yani eski
        # kilit, KARŞILANMASI İMKÂNSIZ bir şart üzerinden hükmü ilkesel
        # olarak kazanılamaz kılıyordu (katı ve hibrit motorlarda hüküm
        # hiçbir mesh'te verilemiyordu) — kusuru koruyan bekçi buydu.
        # ASME BPVC VIII-2 Bölüm 5 Tablo 5.6 tepeyi plastik çökme
        # hükmünden zaten dışlar. Bu fikstürde HÜKÜM BÜYÜKLÜĞÜ artık
        # gerçekten yakınsıyor (rel %0,48 < tol %1) ve hüküm verilir;
        # ham tepenin yakınsamadığı (%3,60) SİLİNMEZ, adıyla yayımlanır.
        # Kilit, kapının ÖLÇTÜĞÜ ŞEYE taşındı:
        assert yk['kapi_alani'] == 'max_von_mises_hukum', (
            'kapı hükmün taşıdığı büyüklüğü değil başka bir alanı '
            f'ölçüyor: {yk.get("kapi_alani")!r}')
        assert 'max_von_mises_nodal' in yk['olculen_alanlar'], (
            'ham tepenin yakınsaması ÖLÇÜLMÜYOR — sayı yayımlanıyorsa '
            'durumu da ölçülmeli')
        tf = kd['tepe_F_yakinsamasi']
        assert tf['hukum_kapisi_mi'] is False
        assert tf['rel_change'] == pytest.approx(
            yk['olculen_alanlar']['max_von_mises_nodal'])
        assert 'ASME' in tf['beyan'] and 'yorulma' in tf['beyan']
        # Hüküm sınıfı ADIYLA duruyor (sayı hangi gerilme sınıfından?).
        assert 'P_L+P_b' in str(h.get('hukum_gerilme_sinifi'))
        # Ham tepe ve ondan türeyen muhafazakâr katsayı GİZLENMEDİ.
        assert isinstance(h.get('tepe_F_pa'), float)
        assert isinstance(h.get('tepe_emniyet_katsayisi'), float)
        # NOT: "tepe katsayısı ≤ hüküm katsayısı" GENEL BİR DEĞİŞMEZ
        # DEĞİLDİR (ölçüldü, tests/test_d25_fea_cfd_a1.py): membran baskın
        # vakalarda 1,5·P_m ham tepeyi geçer ve hüküm tepeden SIKI çıkar.
        # FAIL-CLOSED HÂLÂ ISIRIYOR: ölçüm yakınsamadı derse hüküm YOK.
        if yk['yakinsadi'] is False:
            assert 'yayimlanan_kip_yakinsamadi' in h[
                'geri_cekme_gerekceleri']
            assert h['converged_yayimlanan_kip'] is False
        else:
            assert 'yayimlanan_kip_yakinsamadi' not in h[
                'geri_cekme_gerekceleri']
            assert h['converged_yayimlanan_kip'] is True
        # ÇEVRİLDİ (ÖH D25, OH-D24-01): koşullu hâle geldi. İddia
        # ('yayımlanan kip kendi yakınsamasını kanıtlamadan hüküm
        # veremez') AYNEN duruyor, yalnız artık ölçüme bağlı — bu
        # fikstürde hüküm büyüklüğü GERÇEKTEN yakınsıyor (%0,48 < %1) ve
        # hükmü engelleyen tek şey imkânsız bir ham-tepe şartıydı.
        if not yk['yakinsadi']:
            assert h['verildi'] is False, (
                'yayımlanan kip kendi mesh yakınsamasını kanıtlayamadığı '
                'hâlde hüküm veriliyor — P8B1-09 geri alınmış')
        # Sayı SİLİNMEZ (P17B1-02 sözleşmesinin ikinci yarısı).
        assert h['min_safety_factor'] is not None
        # ÇEVRİLDİ (ÖH D25): beyan artık koşullu — hüküm verildiyse
        # 'GERİ ÇEKİLDİ' demesi YANLIŞ olurdu. Sözleşmenin özü korunuyor:
        # geri çekildiyse gerekçeleriyle söyler, verildiyse verildiğini.
        if h['verildi']:
            assert 'GERİ ÇEKİLDİ' not in h['beyan']
            assert h['geri_cekme_gerekceleri'] == []
        else:
            assert 'GERİ ÇEKİLDİ' in h['beyan']
            assert h['geri_cekme_gerekceleri']
        # P8B1-09'un cebri: converged İKİ kipin de yakınsamasıdır.
        assert h['converged'] == (h['converged_birincil_kip']
                                  and h['converged_yayimlanan_kip'])

    def test_hukum_uca_iniyor(self, istemci, hibrit):
        """Uç yanıtı ``meta.hukum`` ile hüküm sözleşmesini taşıyor."""
        r = _sessiz(istemci.post, '/api/fea/structural',
                    json={'motor_results': {'motor': hibrit.get('motor')},
                          'max_rounds': 1})
        assert r.status_code == 200
        fea = (r.get_json() or {}).get('fea') or {}
        hukum = (fea.get('meta') or {}).get('hukum')
        assert isinstance(hukum, dict), 'uç hükmü hiç taşımıyor'
        for alan in ('verildi', 'converged', 'geri_cekme_gerekceleri',
                     'beyan'):
            assert alan in hukum, f'hüküm sözleşmesinde {alan} yok'


# ===========================================================================
# P17B2-02 (KRİTİK) — /liquid liner hükmü Termal Koruma kartına
# ===========================================================================
#
# ÖLÇÜLEN KUSUR: çözücü ``station_march.peak_wall_temperature_K = 3419,24``
# ve "CRITICAL ... liner failure" üretirken ekranda VE DOM'da 0 geçiş vardı;
# kart kullanıcının ``max_wall_temp`` HEDEFİNİ "Wall Temperature" diye
# basıyordu. Kapanış şartı görsel turdur; tur yerine ŞABLONUN KENDİ kart
# bloğu çıkarılıp gerçek yanıtla çizdirilir.
# TUR İMZASI FABLE DENETİMİNDE.
# ---------------------------------------------------------------------------
LIQUID_KART_HARNESS = SANDBOX_JS + r"""
const [payloadPath] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
const sb = kurSandbox({});
// Kart yardımcıları: ürünün kendi bloğu bunları DIŞARIDAN alır. Sayı
// biçimlendirici HAM sayıyı da yazar ki ölçüm çözücünün değerini arayabilsin.
sb.__kartlar = [];
sb.addCard = function (baslik, govde) {
    sb.__kartlar.push({ baslik: baslik, govde: govde }); };
sb.row = function (etiket, deger) {
    return '<tr><td class="lbl">' + etiket + '</td><td class="val">'
        + deger + '</td></tr>'; };
sb.hrmaFmt = function (v, d, birim) {
    if (v === null || v === undefined || typeof v !== 'number'
            || !isFinite(v)) { return '&mdash;'; }
    return v.toFixed(d === undefined ? 2 : d) + (birim ? ' ' + birim : ''); };
// ÖH D35 · OH-GT-25: şablonun kart bloğu sayıyı ortak `numTxt`
// delegatörüne soruyor (i18n.js kanonu). Sandbox'ta sözlük yok, bu yüzden
// delegatör eski `toFixed` dalına düşer — bu sınıfın sayısal iddiaları
// (çözücünün değeri DOM'da aranır) AYNEN geçerlidir.
sb.numTxt = function (v, d) {
    return (typeof v === 'number' && isFinite(v))
        ? (d === undefined ? String(v) : v.toFixed(d)) : String(v); };

const KOD = 'function __kart(results, T, addCard, row, hrmaFmt) {\n'
    + P.blok + '\n}';
vm.runInContext(KOD, sb, { filename: 'liquid.html#thermal_protection' });

function ciz(res) {
    sb.__kartlar = [];
    sb.__kart(res, sb.T, sb.addCard, sb.row, sb.hrmaFmt);
    const k = sb.__kartlar.filter(function (c) {
        return String(c.baslik).indexOf('Thermal Protection') !== -1; })[0];
    return k ? k.govde : '';
}
const O = {};
const dom = ciz(P.res);
O.once = {
    uzunluk: dom.length,
    kritikRozet: (dom.match(/>CRITICAL</g) || []).length,
    cozucuSicakligi: dom.indexOf(P.cozucuK) !== -1,
    kaynakStationMarch: dom.indexOf('station_march') !== -1,
    hedefEtiketi: dom.indexOf('Maximum Wall Temperature') !== -1,
    hedefSayisi: P.hedefK ? dom.indexOf(P.hedefK) !== -1 : null,
    hukumMetinleri: (P.hukumler || []).filter(function (h) {
        return dom.indexOf(h) !== -1; }).length,
    // "Wall Temperature" satırının DEĞER hücresi
    wallTempSatiri: (function () {
        const re = /<td class="lbl">Wall Temperature<\/td><td class="val">([^<]*)</;
        const m = re.exec(dom); return m ? m[1].trim() : null;
    })(),
};

// MUTASYON: çözücünün istasyon marşı silinirse kart SAYI UYDURAMAZ.
const m = kopya(P.res);
if (m.thermal_protection) {
    delete m.thermal_protection.station_march;
    if (m.thermal_protection.cooling_system) {
        delete m.thermal_protection.cooling_system; }
}
if (m.cooling_system) { delete m.cooling_system.wall_temperature_source; }
const dom2 = ciz(m);
O.sonra = {
    kritikRozet: (dom2.match(/>CRITICAL</g) || []).length,
    cozucuSicakligi: dom2.indexOf(P.cozucuK) !== -1,
    wallTempSatiri: (function () {
        const re = /<td class="lbl">Wall Temperature<\/td><td class="val">([^<]*)</;
        const m2 = re.exec(dom2); return m2 ? m2[1].trim() : null;
    })(),
};
process.stdout.write(JSON.stringify(O));
"""


@pytest.fixture(scope='module')
def sivi_marsi(sivi):
    tp = sivi.get('thermal_protection') or {}
    return tp.get('station_march') or {}


class TestP17B2_02SiviLinerHukmu:

    def test_cozucu_liner_hukmunu_uretiyor(self, sivi, sivi_marsi):
        """ÜRETİM: tepe cidar sıcaklığı + KRİTİK liner hükmü."""
        tepe = sivi_marsi.get('peak_wall_temperature_K')
        assert isinstance(tepe, (int, float)), (
            'station_march tepe cidar sıcaklığı yayımlamıyor — '
            'kalemin girdisi kayboldu')
        izin = sivi_marsi.get('material_allowable_K')
        assert isinstance(izin, (int, float)) and tepe > izin, (
            f'bu koşum kritik vaka üretmiyor ({tepe} <= {izin})')
        hukumler = sivi_marsi.get('warnings')
        assert isinstance(hukumler, list) and hukumler
        kritik = [h for h in hukumler
                  if str(h).strip().upper().startswith(('CRITICAL', 'UNSAFE'))]
        assert kritik, f'çözücü kritik hüküm üretmiyor: {hukumler}'
        assert any('liner' in str(h).lower() for h in kritik), (
            f'liner hükmü yok: {kritik}')

    def test_kullanicinin_hedefi_cozucunun_sayisi_degil(self, sivi,
                                                        sivi_marsi):
        """İki sayı AYRI: kullanıcının hedefi çözücünün sayısı değildir."""
        tp = sivi.get('thermal_protection') or {}
        hedef = tp.get('wall_temperature')
        tepe = sivi_marsi.get('peak_wall_temperature_K')
        assert isinstance(hedef, (int, float))
        assert abs(hedef - tepe) > 1.0, (
            'hedef ile çözülmüş sıcaklık aynı sayı — ayrım kaybolmuş')
        assert tp.get('wall_temperature_source'), (
            'kullanıcı hedefinin künyesi yok (hangi sayı olduğu okunmuyor)')

    @pytest.mark.skipif(not NODE, reason='node bulunamadı')
    def test_kart_cozucunun_sicakligini_ve_hukmunu_basiyor(self, sivi,
                                                           sivi_marsi):
        """TAŞIMA (tur yerine geçen ölçüm): şablonun KENDİ kartı çizilir."""
        kaynak = (SABLON / 'liquid.html').read_text(encoding='utf-8')
        i = kaynak.index('const tprot = results.thermal_protection;')
        blok = _js_blok(kaynak[i:], 'if (tprot)')
        blok = 'const tprot = results.thermal_protection;\n' + blok
        tepe = sivi_marsi['peak_wall_temperature_K']
        hedef = (sivi.get('thermal_protection') or {}).get('wall_temperature')
        hukumler = [str(h)[:40] for h in (sivi_marsi.get('warnings') or [])]
        olcum = _node(LIQUID_KART_HARNESS, girdi={
            'res': sivi, 'blok': blok,
            'cozucuK': f'{tepe:.0f}', 'hedefK': f'{hedef:.0f}',
            'hukumler': hukumler})
        once = olcum['once']
        assert once['wallTempSatiri'], 'kartta Wall Temperature satırı yok'
        assert once['wallTempSatiri'].startswith(f'{tepe:.0f}'), (
            '"Wall Temperature" satırı ÇÖZÜCÜNÜN sıcaklığını basmıyor: '
            f"{once['wallTempSatiri']!r} (çözücü {tepe:.0f} K)")
        assert once['kaynakStationMarch'], (
            'sayının kaynağı (station_march) kartta yazmıyor')
        assert once['hedefEtiketi'], (
            'kullanıcının hedefi ayrı etiketle basılmıyor')
        assert once['kritikRozet'] >= 1, (
            'çözücünün KRİTİK hükmü kartta rozetsiz')
        assert once['hukumMetinleri'] >= 1, (
            'çözücünün hüküm metinleri karta hiç inmiyor')

    @pytest.mark.skipif(not NODE, reason='node bulunamadı')
    def test_cozucu_susarsa_kart_sayi_uydurmaz(self, sivi, sivi_marsi):
        """MUTASYON: istasyon marşı yoksa hane "—" olur, hüküm rozeti düşer."""
        kaynak = (SABLON / 'liquid.html').read_text(encoding='utf-8')
        i = kaynak.index('const tprot = results.thermal_protection;')
        blok = _js_blok(kaynak[i:], 'if (tprot)')
        blok = 'const tprot = results.thermal_protection;\n' + blok
        tepe = sivi_marsi['peak_wall_temperature_K']
        hedef = (sivi.get('thermal_protection') or {}).get('wall_temperature')
        olcum = _node(LIQUID_KART_HARNESS, girdi={
            'res': sivi, 'blok': blok,
            'cozucuK': f'{tepe:.0f}', 'hedefK': f'{hedef:.0f}',
            'hukumler': []})
        sonra = olcum['sonra']
        assert not sonra['cozucuSicakligi'], (
            'marş silindiği hâlde çözücü sıcaklığı kartta duruyor')
        assert sonra['wallTempSatiri'] in ('&mdash;', '—'), (
            'çözülmüş sıcaklık yokken kart bir sayı basıyor (fail-closed '
            f"ihlali): {sonra['wallTempSatiri']!r}")
        assert sonra['kritikRozet'] == 0, (
            'hüküm kaynağı silindiği hâlde KRİTİK rozeti duruyor')


# ===========================================================================
# P17B3-06 (YÜKSEK) — EKRANDAKİ İKİ SF, HANGİ KOŞUMDAN?
# ===========================================================================
PANEL_HARNESS = SANDBOX_JS + r"""
const [staticDir, payloadPath] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
const sb = kurSandbox({});
kosDosya(sb, path.join(staticDir, 'analysis_dock.js'));
kosDosya(sb, path.join(staticDir, 'panels', 'structural_panel.js'));
try {
    sb.window.AnalysisDock.init({ motorType: 'hybrid',
        resultsProvider: function () { return P.motor; } });
} catch (e) { /* gercek DOM yok; kayit yine kuruldu */ }
const spec = sb.window.AnalysisDock._registry.filter(function (s) {
    return s.id === 'structural'; })[0];

function ciz(motorRes) {
    spec.fromResults(motorRes);
    const kok = new El('div');
    sb.window.StructuralPanel._render(P.panel, kok);
    return kok.innerHTML || kok.children.map(function (x) {
        return x.innerHTML; }).join('');
}
function olc(html) {
    return {
        uzunluk: html.length,
        motorUcu: html.indexOf('/calculate') !== -1,
        panelUcu: html.indexOf('/analyze_structural_safety') !== -1,
        delta: html.indexOf('Δ') !== -1,
        cidarKunyesi: html.indexOf('wall_thickness_used_mm') !== -1,
        ayrisanAlanlar: ['design_pressure', 'material', 'chamber diameter',
                         'chamber length'].filter(function (a) {
            return html.indexOf(a + ' ') !== -1; }),
    };
}
const O = {};
O.motorType = sb.window.AnalysisDock.getMotorType();
O.ayrikKunye = olc(ciz(P.motor));          // gercek kosum: kunyeler ayrik
O.motorsuz = olc(ciz({}));                 // motor kosumu YOK
O.ozdesKunye = olc(ciz(P.ozdesMotor));     // kunye ozdes, sayi farkli
process.stdout.write(JSON.stringify(O));
"""


@pytest.fixture(scope='module')
def panel_olcum(hibrit, panel_yanit):
    """Gerçek panel + gerçek dock, üç dalda çizim."""
    if not NODE:
        pytest.skip('node bulunamadı')
    sa = panel_yanit.get('structural_analysis') or panel_yanit
    ca = dict(sa.get('chamber_analysis') or {})
    sf = sa.get('safety_analysis') or {}
    taban = sf.get('minimum_safety_factor')
    # KÜNYE ÖZDEŞ dal: panelin KENDİ künye alanlarını taşıyan bir motor
    # koşumu kurulur (aynı hazne, ayrı koşum) — sayı bilerek farklıdır.
    ozdes = {'motor': {'structural_analysis': {
        'design_parameters': dict(sa.get('design_parameters') or {}),
        'chamber_analysis': ca,
        'safety_analysis': {'minimum_safety_factor':
                            (taban * 1.5) if isinstance(taban, (int, float))
                            else 2.0},
    }}}
    return _node(PANEL_HARNESS, STATIK,
                 girdi={'motor': hibrit, 'panel': panel_yanit,
                        'ozdesMotor': ozdes})


class TestP17B3_06CiftSFEtiketi:

    def test_panel_kendi_sf_satirini_uc_adiyla_basiyor(self, panel_olcum):
        assert panel_olcum['motorType'] == 'hybrid'
        assert panel_olcum['ayrikKunye']['panelUcu'], (
            'panelin asgari SF satırı hangi uçtan geldiğini söylemiyor')

    def test_motor_kosumu_uc_adiyla_ve_cidar_kunyesiyle_yaninda(
            self, panel_olcum):
        a = panel_olcum['ayrikKunye']
        assert a['motorUcu'], (
            'motor koşumunun SF\'i panelde uç adıyla basılmıyor — '
            'iki sayı yine kaynaksız')
        assert a['cidarKunyesi'], (
            'kıyas satırı hangi cidarı anlattığını söylemiyor')

    def test_motor_kosumu_yoksa_kiyas_satiri_basilmaz(self, panel_olcum):
        """Fail-closed: koşum yoksa uydurma kıyas yok."""
        assert not panel_olcum['motorsuz']['motorUcu'], (
            'motor koşumu olmadan kıyas satırı basılıyor (uydurma kıyas)')
        assert (panel_olcum['motorsuz']['uzunluk']
                < panel_olcum['ayrikKunye']['uzunluk'])

    def test_kunye_ayriksa_delta_degil_ALAN_ADLARI_basilir(self, panel_olcum):
        """Farklı hazne = çelişki DEĞİL: ayrışan alanların adı yazılır."""
        a = panel_olcum['ayrikKunye']
        assert a['ayrisanAlanlar'], (
            'künyeler ayrıkken ayrışan alanların adı basılmıyor')
        assert not a['delta'], (
            'farklı hazne için Δ basılıyor — yanlış alarm (P17B3-06)')

    def test_kunye_ozdesse_delta_basilir(self, panel_olcum):
        """Aynı hazne + farklı sayı = GERÇEK ayrışma: Δ basılır."""
        o = panel_olcum['ozdesKunye']
        assert o['motorUcu'], 'özdeş künye dalında kıyas satırı yok'
        assert o['delta'], (
            'aynı hazneyi anlatan iki sayı ayrıştığı hâlde Δ basılmıyor')


# ===========================================================================
# P17S1-01 (YÜKSEK) — .eng ⟷ STEP KASA ÇAPI EŞİTLİĞİ
# ===========================================================================
#
# ÖLÇÜLEN KUSUR: aynı oturumdan inen iki dosya iki kasa çapı yazıyordu
# (.eng 97,9 ⟷ STEP 90,03 mm; 27 Ağustos yeniden ölçümünde 184,37 ⟷ 162,53).
# Z2 onarımı ikisini de tek çözümleyiciye (``_chamber_wall_design``) bağladı.
#
# .eng RASP başlığı çapı BİR ONDALIKLA yazar; bu yüzden eşitlik ölçütü o
# yazım çözünürlüğünün yarısıdır (0,05 mm). Eski kusur 7,87 mm ayrışmaydı —
# bu ölçüt onu yakalar. KESİN ONDALIK ÇAPALANMAZ.
# ---------------------------------------------------------------------------
ENG_YAZIM_COZUNURLUGU_MM = 0.1
_STEP_NOKTA = re.compile(r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(([^)]*)\)")


def _step_dis_capi_mm(yol: str) -> float:
    """STEP kamara parçasının en büyük yarıçapından dış çap [mm].

    Profil ``(z, r, 0)`` üçlüleriyle yazılır (``_revolve_profile``); en
    büyük ``|r|`` kasanın dış yüzeyidir.
    """
    txt = Path(yol).read_text(encoding='utf-8', errors='replace')
    r_max = 0.0
    for ham in _STEP_NOKTA.findall(txt):
        alan = [x.strip() for x in ham.split(',')]
        if len(alan) != 3:
            continue
        try:
            r = float(alan[1])
        except ValueError:
            continue
        r_max = max(r_max, abs(r))
    assert r_max > 0.0, f'STEP dosyasında yarıçap okunamadı: {yol}'
    return 2.0 * r_max


def _eng_cap_mm(icerik: str):
    """RASP motor satırının 2. alanı = kasa çapı [mm]."""
    for satir in icerik.splitlines():
        s = satir.strip()
        if not s or s.startswith(';'):
            continue
        alan = s.split()
        if len(alan) >= 7:
            return float(alan[1])
    return None


def _ihrac_cifti(yanit, motor_tipi):
    """Aynı sonuçtan .eng metni + STEP kamara parçası üretir."""
    from hrma.export import step_export
    from hrma.export.openrocket_integration import OpenRocketExporter
    eng = _sessiz(OpenRocketExporter().export_motor_file, yanit)
    yollar = _sessiz(step_export.generate_step_assembly, yanit, None,
                     motor_tipi)
    return eng, yollar


@pytest.fixture(scope='module')
def sivi_sureli(istemci):
    """Süresi VERİLMİŞ sıvı yanıtı (.eng + STEP çifti için).

    ÖH D36 / LU-1 (ÇEVRİLEN BEKÇİ, onemli2-sivi a2): motor yanma süresini
    artık VARSAYMAZ; süre verilmezse .eng ÜRETİLMEZ
    (``OpenRocketExportDataError``: burn_time, propellant_mass, ...) ve bu
    fikstür üç motor tipinin de düğümlerini (7) kurulumda düşürüyordu.
    Ölçülen şey (.eng başlığı ile STEP kamarasının aynı kasa çapını
    yazması) SÜRESİ VERİLMİŞ bir tasarımdır; süre motorun kendi sabitinden
    AÇIKÇA verilir (sayı burada yazılmaz), geometri süreden bağımsızdır.
    Diğer düğümlerin ``sivi`` fikstürü aynen kalır.
    """
    pytest.importorskip('rocketcea.cea_obj')
    from hrma.engines.liquid_rocket_engine import BURN_TIME_DEFAULT_S
    r = _sessiz(istemci.post, '/calculate_liquid',
                json=dict(Z5G_SIVI, max_burn_duration=BURN_TIME_DEFAULT_S))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def ihrac_ciftleri(hibrit, kati, sivi_sureli):
    from hrma.export import export_workspace
    kayit, temizlenecek = {}, []
    for etiket, yanit, tip in (('hybrid', hibrit.get('motor'), 'hybrid'),
                               ('solid', kati, 'solid'),
                               ('liquid', sivi_sureli, 'liquid')):
        eng, yollar = _ihrac_cifti(yanit, tip)
        kayit[etiket] = {
            'eng': eng,
            'eng_cap_mm': _eng_cap_mm(eng),
            'step_cap_mm': _step_dis_capi_mm(yollar['chamber']),
            'step_metni': Path(yollar['chamber']).read_text(
                encoding='utf-8', errors='replace'),
        }
        temizlenecek.append(yollar)
    yield kayit
    for yollar in temizlenecek:
        try:
            export_workspace.cleanup_workspace(
                os.path.dirname(yollar['chamber']))
        except Exception:
            shutil.rmtree(os.path.dirname(yollar['chamber']),
                          ignore_errors=True)


class TestP17S1_01EngStepCapEsitligi:

    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_iki_dosya_ayni_kasa_capini_yaziyor(self, ihrac_ciftleri, tip):
        k = ihrac_ciftleri[tip]
        eng, step = k['eng_cap_mm'], k['step_cap_mm']
        assert isinstance(eng, float) and eng > 0, (
            f'{tip}: .eng başlığından kasa çapı okunamadı')
        fark = abs(eng - step)
        assert fark <= ENG_YAZIM_COZUNURLUGU_MM / 2.0 + 1e-9, (
            f'{tip}: aynı oturumun iki dosyası iki kasa çapı yazıyor — '
            f'.eng {eng} mm ⟷ STEP {step} mm (fark {fark:.4f} mm, '
            f'izin {ENG_YAZIM_COZUNURLUGU_MM / 2.0} mm)')

    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_cidar_kunyesi_iki_dosyada_da_ayni(self, ihrac_ciftleri, tip):
        """Çapı üreten CİDAR da iki dosyada aynı sayıyla beyan edilir."""
        k = ihrac_ciftleri[tip]
        satir = next((s.strip() for s in k['eng'].splitlines()
                      if 'wall used in the diameter field' in s), None)
        if satir is None:
            # Kasa çapı doğrudan yayımlanmışsa (.eng cidardan TÜRETMEZ)
            # künye satırı da basılmaz; o zaman iddia da yoktur.
            pytest.skip(f'{tip}: .eng çapı cidardan türetmiyor (künye yok)')
        m = re.search(r'=\s*([\d.]+)\s*mm', satir)
        assert m, f'{tip}: .eng cidar künyesi sayı taşımıyor: {satir}'
        eng_cidar = float(m.group(1))
        adlar = re.findall(r"PRODUCT\s*\(\s*'([^']*)'", k['step_metni'])
        assert adlar, f'{tip}: STEP parça adı okunamadı'
        m2 = re.search(r'wall\s+([\d.]+)\s*mm', adlar[0])
        assert m2, f'{tip}: STEP parça adında cidar künyesi yok: {adlar[0][:80]}'
        step_cidar = float(m2.group(1))
        assert abs(eng_cidar - step_cidar) <= 0.01, (
            f'{tip}: iki dosya iki cidar anlatıyor — '
            f'.eng {eng_cidar} mm ⟷ STEP {step_cidar} mm')

    def test_capin_kaynagi_uydurma_degil(self, ihrac_ciftleri):
        """Üç motor tipinin hiçbirinde çap yer-tutucu değil."""
        for tip, k in ihrac_ciftleri.items():
            assert k['eng_cap_mm'] > 1.0, (
                f'{tip}: .eng kasa çapı yer-tutucu görünüyor '
                f"({k['eng_cap_mm']})")
            assert k['step_cap_mm'] > 1.0


# ===========================================================================
# P8B2-11 (ORTA) — KÖPRÜNÜN İKİNCİ SF'İ: KIYAS BEYANI
# ===========================================================================
class TestP8B2_11KopruKiyasBeyani:

    def test_kiyas_blogu_alan_alan_var(self, kopru_saglikli):
        k = kopru_saglikli.get('motor_safety_factor_comparison')
        assert isinstance(k, dict), (
            'köprü ikinci SF\'yi kıyassız basıyor (P8B2-11 geri geldi)')
        for alan in ('kopru_min_safety_factor', 'kopru_yontemi',
                     'motor_safety_factor', 'motor_kaynagi',
                     'oran_kopru_bolu_motor', 'beyan'):
            assert alan in k, f'kıyas sözleşmesinde {alan} yok'

    def test_motor_sayisinin_kaynagi_ADLI(self, kopru_saglikli):
        k = kopru_saglikli['motor_safety_factor_comparison']
        kaynak = k['motor_kaynagi']
        assert isinstance(kaynak, dict) and kaynak.get('alan'), (
            'motorun SF\'i hangi alandan alındığı söylenmeden kıyaslanıyor')
        assert isinstance(kaynak.get('deger'), (int, float))
        assert kaynak.get('kunye'), 'motor sayısının künyesi yok'

    def test_oran_gercekten_iki_sayidan(self, kopru_saglikli):
        k = kopru_saglikli['motor_safety_factor_comparison']
        a, b, oran = (k['kopru_min_safety_factor'], k['motor_safety_factor'],
                      k['oran_kopru_bolu_motor'])
        assert isinstance(oran, float)
        assert abs(oran - a / b) < 1e-9, 'oran iki sayıdan gelmiyor'
        assert oran > 1.0, (
            'bu koşumda köprü/motor ayrışması kayboldu — kalemin vakası yok')

    def test_beyan_celiskiyi_MODEL_FARKI_diye_adlandiriyor(self,
                                                           kopru_saglikli):
        """Sessiz çelişki yok: fark ADLANDIRILIYOR ve nedeni yazıyor."""
        k = kopru_saglikli['motor_safety_factor_comparison']
        beyan = k['beyan']
        assert 'MODEL FARKIDIR' in beyan, beyan[:200]
        yontem = k['kopru_yontemi']
        for anahtar in ('FEA', 'derating'):
            assert anahtar in yontem, (
                f'köprünün yöntem künyesi {anahtar} demiyor: {yontem[:160]}')

    def test_derating_hukmu_TEK_ve_olculen_akmayla_ayni(self, kopru_saglikli):
        """CANLI ÇELİŞKİ KAPISI: üç cümle aynı şeyi söylemeli.

        ÖH D15 fix-3 (1 Eyl 2026) ürün onarımının bekçisi. Onarımdan önce
        ``bridge.py`` aynı bloğun içinde AYNI soruya İKİ ZIT cevap
        veriyordu: ``kopru_yontemi`` "akma ... cidar sıcaklığına derate
        edilmiş değer varsa o" derken ``beyan`` "motorun katsayısı ...
        dayanım deratingini içerir, KÖPRÜNÜNKİ İÇERMEZ" diyordu; üçüncü yer
        (``meta.not_modelled[0]``) yönteme katılıyordu. ÖLÇÜLDÜ: cevap MOTOR
        TİPİNE bağlıdır — ``_extract_material`` yalnız SIVI dalında
        (P8B2-05) ``chamber_structure.yield_strength_at_wall_temp``i
        kullanır ve derating UYGULANIR; hibrit dalı
        ``material_properties.yield_strength``i (oda sıcaklığı) okur, katı
        dalı çözücünün fiilen kullandığı dayanımı alır — o iki dalda
        derating UYGULANMAZ. Yani her iki cümle de bazı koşumlarda doğru,
        bazılarında yanlıştı.

        Ürün artık tek makine-okur kaynaktan (``girdiler.malzeme
        .akma_derate_edildi``) konuşuyor. Bu bekçi metinlerin BİRBİRİYLE ve
        ÖLÇÜLEN akma kaynağıyla uyumunu kilitler; hangi cevabın çıkacağına
        HÜKMETMEZ (fikstür motoru değişirse dal değişebilir).
        """
        k = kopru_saglikli['motor_safety_factor_comparison']
        meta = kopru_saglikli['meta']
        malzeme = (meta.get('girdiler') or {}).get('malzeme') or {}

        bayrak = k.get('kopru_akma_derate_edildi')
        assert isinstance(bayrak, bool), (
            'köprü deratingi uygulayıp uygulamadığını makine-okur bir '
            'alanda söylemiyor — metin ayıklamak sözleşme değildir')
        assert malzeme.get('akma_derate_edildi') == bayrak, (
            'kıyas bloğu ile malzeme künyesi derating konusunda ayrışıyor')

        # Bayrak ÖLÇÜLEN akma kaynağıyla tutarlı mı? (tek gerçek kaynak)
        kaynak = malzeme.get('akma_kaynagi') or ''
        assert bayrak == ('yield_strength_at_wall_temp' in kaynak), (
            'derating bayrağı ile fiilen kullanılan akma alanı çelişiyor: '
            f'bayrak={bayrak}, kaynak={kaynak[:160]!r}')

        yontem = k['kopru_yontemi']
        beyan = k['beyan']
        nm = meta['not_modelled'][0]
        if bayrak:
            uyumlu = ('deratingi UYGULANDI' in yontem
                      and 'YALNIZ TERMAL GERİLMEDİR' in beyan
                      and 'modellenmemiş değildir' in nm)
        else:
            uyumlu = ('deratingi UYGULANMADI' in yontem
                      and 'TERMAL GERİLME VE DAYANIM DERATİNGİDİR' in beyan
                      and 'UYGULANMADI' in nm)
        assert uyumlu, (
            'üç cümle aynı hükmü vermiyor (bayrak=%r)\n  yöntem: %s\n'
            '  beyan: %s\n  not_modelled[0]: %s'
            % (bayrak, yontem[:200], beyan[:200], nm[:200]))

    def test_derating_bayragi_fiilen_kullanilan_akmadan_gelir(self):
        """Bayrağın İKİ yakası da ölçülür (birim düzeyi, ucuz).

        Üstteki bekçi fikstür motorunun düştüğü dalı ölçer; bu bekçi
        ``_extract_material``ın kendisini iki sentetik girdiyle sınar, yani
        sıvı dalındaki DERATE=True yakası da kilitli kalır (P8B2-05).
        Sayılar sentetiktir ve yalnız hangi ALANIN okunduğunu ayırt eder.
        """
        from hrma.fea.bridge import _extract_material

        sivi_derate = {'structural_analysis': {'chamber_structure': {
            'material_key': 'steel_4130',
            'yield_strength': 1100.0,                 # MPa, oda sıcaklığı
            'yield_strength_at_wall_temp': 700.0}}}   # MPa, derate edilmiş
        mat, beyan = _extract_material(sivi_derate, 'liquid')
        assert mat is not None and isinstance(beyan, dict)
        assert beyan['akma_derate_edildi'] is True, (
            'motor derate edilmiş akmayı yayımladı ve köprü onu kullandı, '
            'ama bayrak bunu söylemiyor')
        assert mat.yield_strength == pytest.approx(700.0e6)
        assert 'yield_strength_at_wall_temp' in beyan['akma_kaynagi']

        sivi_oda = {'structural_analysis': {'chamber_structure': {
            'material_key': 'steel_4130', 'yield_strength': 1100.0}}}
        mat2, beyan2 = _extract_material(sivi_oda, 'liquid')
        assert beyan2['akma_derate_edildi'] is False, (
            'derate edilmiş akma YOKKEN bayrak açık — köprü uygulamadığı '
            'bir deratingi uyguladım diyor')
        assert mat2.yield_strength == pytest.approx(1100.0e6)

    def test_motor_sayisi_yoksa_kiyas_UYDURULMAZ(self, hibrit):
        """Fail-closed: kıyaslanacak sayı yoksa referans icat edilmez."""
        from hrma.fea.bridge import _extract_motor_safety_factor
        motor = hibrit.get('motor') or {}
        kirpik = json.loads(json.dumps({
            k: v for k, v in motor.items() if k != 'structural_analysis'}))
        deger, beyan = _extract_motor_safety_factor(kirpik, 'hybrid')
        assert deger is None, (
            'yapısal blok yokken motor SF\'i yine de üretiliyor')
        assert beyan is None or isinstance(beyan, dict)

    @pytest.mark.xfail(strict=True, reason=(
        'P8B2-11 KAPANIŞ ŞARTININ İKİNCİ YARISI ÖDENMEDİ (borç imi): '
        'köprü hükmü ve motor-SF kıyasını ÜST DÜZEYDE yayımlıyor, '
        '/api/fea/structural ucu ise yanıtı alan alan kurup yalnız '
        'meta içindekini geçiriyor. Bu bekçi uç yüzeye çıkarınca XPASS '
        'verir ve kalem kapanır. Ürün onarımı hrma/app.py: '
        'api_fea_structural içinde (bu paket SALT TEST).'))
    def test_uc_ust_duzeyde_hukum_ve_kiyas_yayimliyor(self, istemci, hibrit):
        r = _sessiz(istemci.post, '/api/fea/structural',
                    json={'motor_results': {'motor': hibrit.get('motor')},
                          'max_rounds': 1})
        assert r.status_code == 200
        fea = (r.get_json() or {}).get('fea') or {}
        assert 'verdict' in fea, 'uç üst düzeyde verdict yayımlamıyor'
        assert 'motor_safety_factor_comparison' in fea, (
            'uç üst düzeyde motor SF kıyasını yayımlamıyor')
