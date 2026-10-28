# -*- coding: utf-8 -*-
"""ÖH D33-KOLAY · arayuz-panel · aşama-1 bekçileri.

Kalem: OH-D32-11 — OH-D31-05'in ölü panel sökümünden artakalan 14 hayalet
alan ve CANLI KUSUR: dil değişimi zincirinde ``updateMixtureDensity()``
sökülmüş bir elemanı okuyup TypeError fırlatıyor, ``catch`` zinciri kesiyor
ve ``checkDatabaseStatus()`` HİÇ çalışmıyordu.

Kardeş bekçiler (test_d15_sablonlar_a3, d17/d21/d22/d28/d29/d32 arayuz)
ölü fonksiyonların GERİ GELMEDİĞİNİ kaynak metninden ölçüyor. Burada
ölçülen şey ZİNCİRİN KENDİSİ: dil değiştirildiğinde veritabanı durumu
gerçekten yenileniyor mu?

Ölçüm: ``docs/scofield/raw/OH/D33/arayuz-panel/a1/once.json`` /
``sonra.json``; ters mutasyon: aynı dizin ``mutasyon.json``.

-----------------------------------------------------------------------
ÖH D33-2 · arayuz-panel a1 — AYNI DOSYAYA EKLENEN ÜÇ KALEM
-----------------------------------------------------------------------
Yukarıdaki D33-KOLAY bekçileri OLDUĞU GİBİ DURUR (kaldırılmadı,
gevşetilmedi). Aşağıya D33-2 partisinin üç kalemi eklendi; ölçümleri
``docs/scofield/raw/OH/D33-2/arayuz-panel/a1/`` altındadır.

OH-D32-01 (defter zinciri **P7B1-06**) — ``panels/performance_panel.js``
    birim çıkarımı için İKİNCİ BİR BANT taşıyordu: ``DIAMETER_SI_MAX_M =
    1.0`` ve ``LENGTH_SI_MAX_M = 5.0``. Doğrulayıcının kendi kanonu ise
    ``motor_validation.DIAMETER_UNIT_INFERENCE_MAX_M = 5,0`` /
    ``LENGTH_UNIT_INFERENCE_MAX_M = 20,0`` (ikisi de ``CANONICAL_LIMITS``
    tablosundan TÜRETİLİR). ÖLÇÜLDÜ (``D33-2/.../a1/once.json``, bölüm
    K1): normalize ``motor_geometry`` bloğu gelmeyen bir gövdede kanonik
    bandın İÇİNDE kalan meşru ölçüler panelde 1000 kat küçülüyordu —
    ``chamber_diameter 1,5 m -> 0,0015 m``, ``chamber_length 6,0 m ->
    0,006 m``, ``throat_diameter 1,2 m``ten türetilen alan
    ``1,131 m² -> 1,131e-6 m²`` (10^6 kat). Bandı arayüze yayımlayan uç
    YOK; ikinci kopya TAŞINMAZ ve sayı UYDURULMAZ: blok yoksa panel
    çıkarım yapmaz, alanı ÖNERİSİZ bırakır, çözülemeyen alanı ADIYLA
    beyan eder.

OH-D32-03 (zincir **P7B2-23**) — ``/api/slosh-analysis`` ``size_envelope``
    altında YEDİ çocuk yayımlıyor ve blok bir YOKLUK BEYANIDIR ("yarıçap
    bandı BEYAN EDİLMEDİ", "Bond sayısı DEĞERLENDİRİLEMEDİ, eksik girdi:
    yüzey gerilimi"). ÖLÇÜLDÜ (K2): ``feed_panel.js`` okuma envanterinde
    (173 ad) ne blok adı ne de yedi çocuktan BİRİ geçiyordu; kayıt
    ``tests/test_wave4b_contract.py::TERS_PANEL_BORCU`` içinde ADLI BORÇ
    olarak duruyordu. Panel bloğu bastı, borç ödendi.

OH-FT-07 (Fable TOPLU fea-cfd-03) — ayrılma ölçütlerinin ``cfd_tau_w``
    üyesinde ``margin_min`` TANIMSIZDIR (şemanın margin'i ölçüt
    niceliğinin EŞİĞİNE oranıdır; bu üyenin eşiği τ_w = 0'dır). Üretici
    payı KENDİ adıyla (``tau_wall_min_over_max_abs``) ve KRİTİK DEĞERİYLE
    (``tau_wall_margin_critical_value`` = 0) yayımlıyor. ÖLÇÜLDÜ (K3): bu
    iki alanı okuyan JS dosyası sayısı **0**, ekranda ise "attached
    (minimum margin —)" yazıyordu — üyenin ölçtüğü 0,371 hiç
    görünmüyordu.

D33-2 ÖLÇÜM YÖNTEMİ: sunucuya port BAĞLANMAZ; sayılar ürünün KENDİ
üreticilerinden gelir (``hrma.analysis.slosh_analysis``,
``hrma.cfd.separation``), paneller ``node`` içinde GERÇEKTEN koşturulur
(kalıp: ``test_panel_units_v2626.py`` — aynı asgari DOM, aynı yükleme
sırası). Beklenen değerler ELLE yazılmaz, üreticiden türetilir.

D33-2 MUTASYON DÜŞÜNCESİ — onarım geri alınırsa hangi test kırılır
  * ``geoLength``a eşik tabanlı çıkarım geri konursa ->
    ``test_birim_guverte_sozlesmesinden_geliyor_buyuklukten_degil`` +
    ``test_sozlesmesiz_alan_onerisiz_kalir_ve_adiyla_beyan_edilir`` +
    ``test_panelde_ikinci_birim_bandi_yok``.
  * ``sizeEnvelopeHtml`` çağrısı kaldırılırsa ->
    ``test_ekranda_bant_yoklugu_ve_eksik_girdi_adi``.
  * ``cfd_tau_w`` satırı yeniden em tireye düşerse ->
    ``test_yapisik_kosuda_em_tire_yerine_kendi_payi``.
  * (``margin_basis`` için onarım YOK: ölçüldü, beyan zaten değer
    kaynağı künyesiyle ekranda — bkz. ``a1/mutasyon_notu.md`` M3b.)
"""
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import numpy as np
import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADV = os.path.join(KOK, 'hrma', 'templates', 'advanced.html')
JSDIR = os.path.join(KOK, 'hrma', 'static', 'js')

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

# OH-D31-05'te sökülen karışım panelinin alanları — hiçbiri geri gelmemeli.
SOKULEN_PANEL_IDLERI = (
    'composition_rows', 'composition_validation', 'custom_fuel_config',
    'custom_fuel_mixture', 'mixture_al2o3', 'mixture_aluminum',
    'mixture_carbon', 'mixture_density_calc', 'mixture_htpb', 'mixture_other',
    'mixture_paraffin', 'mixture_regression_est', 'mixture_total',
    'mixture_warning',
)

OLU_FONKSIYONLAR = ('updateMixtureDensity', 'addCompositionRow',
                    'removeCompositionRow', 'validateComposition')


def _oku(yol):
    with open(yol, encoding='utf-8') as f:
        return f.read()


def _html_yorumsuz(s):
    return re.sub(r'<!--.*?-->', '', s, flags=re.S)


def _tanimli_idler(src):
    ids = set(re.findall(r'<[a-zA-Z][a-zA-Z0-9]*\b[^>]*?\bid="([^"]+)"', src))
    ids |= set(re.findall(r"<[a-zA-Z][a-zA-Z0-9]*\b[^>]*?\bid='([^']+)'", src))
    ids |= set(re.findall(r'''\bid=\\?["']([A-Za-z0-9_\-]+)\\?["']''', src))
    ids |= set(re.findall(r'''\.id\s*=\s*["']([A-Za-z0-9_\-]+)["']''', src))
    return ids


def _okunan_idler(src):
    out = set(re.findall(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", src))
    out |= set(re.findall(r"querySelector\(\s*['\"]#([A-Za-z0-9_\-]+)['\"]\s*\)",
                          src))
    return out


def _hayaletler():
    """advanced.html'de OKUNAN ama hiçbir yerde TANIMLANMAYAN alanlar."""
    src = _oku(ADV)
    paylasilan = ''
    for ad in sorted(os.listdir(JSDIR)):
        if ad.endswith('.js'):
            with open(os.path.join(JSDIR, ad), encoding='utf-8',
                      errors='ignore') as fh:
                paylasilan += fh.read()
    return _okunan_idler(src) - (_tanimli_idler(src)
                                 | _tanimli_idler(paylasilan))


class TestOHD3211HayaletAlanlar:
    """Sökülen panelin alanları ne okunur ne de yeniden tanımlanır."""

    def test_sokulen_panel_alanlari_hayalet_birakmadi(self):
        hayalet = _hayaletler()
        kalan = sorted(set(SOKULEN_PANEL_IDLERI) & hayalet)
        assert not kalan, (
            'OH-D31-05 sökümünden artakalan hayalet alanlar geri geldi: %s '
            '— şablon var olmayan elemanı okuyor' % kalan)

    def test_hayalet_sayisi_tavani(self):
        """ÖLÇÜLDÜ: taban 16 hayalet, onarımdan sonra 2 (a1/once.json M1).

        Tavan bir mandaldır: yeni hayalet alan eklenemez. Kalan iki alan
        (``enable_parametric``, ``parametric_params``) BAŞKA bir ölü panele
        (parametrik süpürme) aitti; ÖH D37 A1a hibrit-beyan (OH-D33-06)
        tek okuyucuları ``toggleParametricParams()``i (çağıranı 0) söktü →
        tavan 2 → 0 (SIKILAŞTIRMA).
        """
        hayalet = _hayaletler()
        assert len(hayalet) == 0, (
            'advanced.html hayalet alan sayısı 0 tavanını aştı: %s'
            % sorted(hayalet))

    def test_olu_fonksiyonlar_geri_gelmedi(self):
        kod = _html_yorumsuz(_oku(ADV))
        geri = [ad for ad in OLU_FONKSIYONLAR
                if re.search(r'function %s\s*\(' % ad, kod)]
        assert not geri, (
            'erişilemez fonksiyonlar geri geldi: %s — tek çağıranları '
            'OH-D31-05 te sökülen paneldi' % geri)


class TestOHD3211DilDegisimiZinciri:
    """CANLI KUSUR: dil değişiminde zincir kırılıyor muydu?"""

    @staticmethod
    def _zincir_govdesi():
        m = re.search(r'if \(I18N\.onChange\) I18N\.onChange\(function \(\) \{'
                      r'(.*?)\n            \}\);', _oku(ADV), re.S)
        assert m, 'dil değişimi zinciri bulunamadı — şablon yeniden düzenlenmiş'
        return m.group(1)

    @node_gerekli
    def test_dil_degisimi_veritabani_durumuna_ULASIYOR(self, tmp_path):
        """Zincir node ikizinde koşturulur; SON halka çalışmalı.

        ÖLÇÜLDÜ (a1/once.json · M2b — taban): zincir
        ``['inj', 'prs', 'imp']`` ile duruyor ve
        ``console.warn('i18n redraw failed: TypeError: Cannot read
        properties of null (reading 'value')')`` basılıyordu;
        ``checkDatabaseStatus`` HİÇ çağrılmıyordu. Kullanıcı dili
        değiştirdiğinde veritabanı durumu bayat kalıyordu.

        Sökülen panel yüzünden ``getElementById`` bu alanlar için ``null``
        döner — ikiz bunu birebir taklit eder.
        """
        betik = (
            'var cagrilanlar = [];\n'
            'var uyarilar = [];\n'
            'var document = { getElementById: function () { return null; },\n'
            '    querySelector: function () { return null; } };\n'
            'var console = { warn: function () {\n'
            '    uyarilar.push(Array.prototype.slice.call(arguments)'
            '.map(String).join(" ")); } };\n'
            'function updateInjectorParams() { cagrilanlar.push("inj"); }\n'
            'function refreshPressureModeLabels() { cagrilanlar.push("prs"); }\n'
            'function updateCalculatedImpulse() { cagrilanlar.push("imp"); }\n'
            # v3.0.1 K: son halka checkDatabaseStatus (rozet yoklaması)
            # idi; rozet söküldü, yerini refreshDataSourceLines aldı.
            'function refreshDataSourceLines() { cagrilanlar.push("db"); }\n'
            + self._zincir_govdesi() + '\n'
            'process.stdout.write(JSON.stringify('
            '{cagrilanlar: cagrilanlar, uyarilar: uyarilar}));\n')
        yol = tmp_path / 'zincir.js'
        yol.write_text(betik, encoding='utf-8')
        p = subprocess.run([NODE, str(yol)], capture_output=True, text=True,
                           timeout=120)
        assert p.returncode == 0, p.stderr
        out = json.loads(p.stdout)
        assert 'db' in out['cagrilanlar'], (
            'dil değiştirildiğinde son halka (refreshDataSourceLines) '
            'çalışmıyor: zincir '
            'kendisinden önceki bir halkada fırlatıp catch e düşüyor — '
            'veritabanı durumu bayat kalıyor (çalışan halkalar: %s, '
            'uyarılar: %s)' % (out['cagrilanlar'], out['uyarilar']))
        assert out['uyarilar'] == [], (
            'dil değişimi zinciri hâlâ uyarı basıyor: %s' % out['uyarilar'])
        # Önceki halkalar da korunur (aşırı söküm kapısı).
        for halka in ('inj', 'prs', 'imp'):
            assert halka in out['cagrilanlar'], (
                '%s halkası zincirden düştü' % halka)

    def test_zincir_sokulen_paneli_ARTIK_OKUMUYOR(self):
        govde = re.sub(r'//.*$', '', self._zincir_govdesi(), flags=re.M)
        for ad in OLU_FONKSIYONLAR:
            assert ad not in govde, (
                'dil değişimi zinciri sökülmüş panelin fonksiyonunu (%s) '
                'yine çağırıyor' % ad)


# ===========================================================================
# ÖH D33-2 · arayuz-panel a1 — ÜÇ KALEM (yukarıdaki D33-KOLAY bekçileri
# olduğu gibi durur; aşağısı EKLEMEdir)
# ===========================================================================
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PERF_JS = STATIC_JS / 'panels' / 'performance_panel.js'

# ---------------------------------------------------------------------------
# Kaynak gövdesi: yorum ve dize literalleri boşlukla doldurulur, böylece
# "yorumda geçiyor" ile "kodda duruyor" karışmaz (kalıp:
# tests/test_panel_units_v2626.py::_js_kod_govdesi).
# ---------------------------------------------------------------------------
_STRING_RE = re.compile(
    r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`", re.S)
_COMMENT_RE = re.compile(r'/\*.*?\*/|//[^\n]*', re.S)


def _js_kod_govdesi(src):
    def _bosluk(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    return _STRING_RE.sub(_bosluk, _COMMENT_RE.sub(_bosluk, src))


# ---------------------------------------------------------------------------
# node koşum takımı — GERÇEK paneller, asgari sahte DOM
# ---------------------------------------------------------------------------
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [staticDir, girdiYolu] = process.argv.slice(2);
const girdi = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.innerHTML = '';
    this.textContent = '';
    this._attrs = {};
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.removeChild = function () {};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k)
        ? this._attrs[k] : null;
};
El.prototype.querySelectorAll = function () { return []; };
El.prototype.querySelector = function () { return null; };
El.prototype.addEventListener = function () {};

function htmlOf(el) {
    let s = String(el.innerHTML || '') + ' ' + String(el.textContent || '');
    (el.children || []).forEach(function (c) { s += ' ' + htmlOf(c); });
    return s;
}

const documentStub = {
    head: new El('head'),
    body: new El('body'),
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    createTextNode: function (t) { const e = new El('span');
                                   e.textContent = String(t); return e; },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
};

const sandbox = {
    console: { log: function () {}, warn: function () {},
               error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: setInterval, clearInterval: clearInterval,
    fetch: function () { return Promise.reject(new Error('sandbox: ağ yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, Date: Date, RegExp: RegExp,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

function run(file) {
    vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox, { filename: file });
}

run(path.join(staticDir, 'units_constants.js'));
run(path.join(staticDir, 'analysis_dock.js'));
if (girdi.motorType) {
    sandbox.window.AnalysisDock._setMotorType(girdi.motorType);
}
run(path.join(staticDir, 'panels', 'performance_panel.js'));
run(path.join(staticDir, 'panels', 'feed_panel.js'));
run(path.join(staticDir, 'panels', 'cfd_panel.js'));

const out = {};

// --- K1: performans paneli ------------------------------------------------
const PP = sandbox.window.PerformancePanel;
out.perfYuzeyi = Object.keys(PP);
if (girdi.perfGovdeler) {
    out.perf = {};
    Object.keys(girdi.perfGovdeler).forEach(function (ad) {
        const sug = PP._fromResults(girdi.perfGovdeler[ad]);
        out.perf[ad] = {
            oneri: sug,
            cozulemeyen: (typeof PP._unresolvedGeometry === 'function')
                ? PP._unresolvedGeometry() : null,
        };
    });
}

// --- K2: besleme paneli, çalkalanma sekmesi -------------------------------
if (girdi.slosh) {
    const kok = new El('div');
    sandbox.window.FeedPanel._renderSlosh({ slosh: girdi.slosh }, kok);
    out.sloshHtml = htmlOf(kok);
}

// --- K3: CFD paneli, ayrılma ölçütleri ------------------------------------
if (girdi.cfdUyeleri) {
    out.cfdHtml = {};
    Object.keys(girdi.cfdUyeleri).forEach(function (ad) {
        const kok = new El('div');
        sandbox.window.CfdPanel._render(
            { cfd: { separation: { criteria: girdi.cfdUyeleri[ad] } } }, kok);
        out.cfdHtml[ad] = htmlOf(kok);
    });
}

process.stdout.write(JSON.stringify(out));
"""


def _kos(**girdi):
    with tempfile.TemporaryDirectory() as tmp:
        harness = os.path.join(tmp, 'harness.js')
        yuk = os.path.join(tmp, 'girdi.json')
        with open(harness, 'w', encoding='utf-8') as fh:
            fh.write(HARNESS_JS)
        with open(yuk, 'w', encoding='utf-8') as fh:
            json.dump(girdi, fh)
        proc = subprocess.run(['node', harness, str(STATIC_JS), yuk],
                              capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, ('node koşum takımı çöktü:\n'
                                  + proc.stderr[-3000:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _metin(html):
    """Etiketleri söküp boşlukları tekilleştirir (ekranda görünen metin)."""
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', html))


# ===========================================================================
# OH-D32-01 — performans panelinin ikinci birim bandı
# ===========================================================================
#: Kanonik bandın İÇİNDE ama emekli JS eşiğinin (1,0 m / 5,0 m) ÜSTÜNDE
#: kalan meşru ölçüler: kusur tam burada yaşıyordu.
GOVDE_ORTAK = {'thrust': 1000.0, 'isp': 250.0, 'mdot_total': 0.4,
               'chamber_pressure': 20.0}
GEOMETRI_M = {'chamber_length': 6.0, 'chamber_diameter': 1.5,
              'throat_diameter': 1.2}


class TestOHD3201PerformansPaneliBirimBandi:

    def test_panelde_ikinci_birim_bandi_yok(self):
        """Çıkarım eşiği KODDA sayı literali olarak duramaz (Doktrin 4)."""
        kod = _js_kod_govdesi(PERF_JS.read_text(encoding='utf-8'))
        for ad in ('DIAMETER_SI_MAX_M', 'LENGTH_SI_MAX_M'):
            assert ad not in kod, (
                f'{ad} panel KODUNDA hâlâ duruyor — sunucu kanonunun '
                '(motor_validation) ikinci kopyası; bant iki yerde '
                'yazılamaz')
        assert 'siLength' not in kod, (
            'eşik tabanlı birim çıkarımı (siLength) geri gelmiş: '
            'normalize motor_geometry bloğu tek kaynaktır')

    def test_sunucu_kanonu_kanonik_tablodan_tureliyor(self):
        """Ölçüm zemini: kanon elle yazılı değil, tablodan türetilmiş."""
        from hrma.validation import motor_validation as MV
        assert MV.DIAMETER_UNIT_INFERENCE_MAX_M == max(
            MV.CANONICAL_LIMITS[a]['max'] for a in MV.DIAMETER_CANONICAL_FIELDS)
        assert MV.LENGTH_UNIT_INFERENCE_MAX_M == max(
            MV.CANONICAL_LIMITS[a]['max'] for a in MV.LENGTH_CANONICAL_FIELDS)
        # Emekli JS eşikleri bu kanonun İÇİNDE kalıyordu: kusurun ölçüsü.
        assert MV.DIAMETER_UNIT_INFERENCE_MAX_M > 1.0
        assert MV.LENGTH_UNIT_INFERENCE_MAX_M > 5.0

    @node_gerekli
    def test_birim_guverte_sozlesmesinden_geliyor_buyuklukten_degil(self):
        """AYNI SAYI, İKİ MOTOR TİPİ, İKİ SONUÇ — ölçüt büyüklük DEĞİL.

        Emekli çıkarım "değer 1,0 m tavanının üstündeyse milimetredir"
        diyordu, yani birimi SAYININ BÜYÜKLÜĞÜNDEN okuyordu. Güvertenin
        merkezi sözleşmesi (``analysis_dock.js::LENGTH_UNITS``, motor
        tipine göre ÖLÇÜLMÜŞ) ise birimi MOTOR TİPİNDEN okur: hibritte
        çaplar metre, katıda milimetredir. Aynı ham sayı bu yüzden iki
        tipte iki farklı SI değeri vermek ZORUNDADIR; eski eşikli yolda
        ikisi de 0,0015 m çıkardı.
        """
        govde = dict(GOVDE_ORTAK, **GEOMETRI_M)   # motor_geometry YOK
        out = _kos(perfGovdeler={'h': govde}, motorType='hybrid')
        hib = out['perf']['h']['oneri']
        assert hib['chamber_diameter'] == pytest.approx(
            GEOMETRI_M['chamber_diameter'], rel=1e-12), (
            'hibritte çap METREDİR (güverte tablosu); panel yine '
            'büyüklükten çıkarım yapıyor olabilir')
        assert hib['chamber_length'] == pytest.approx(
            GEOMETRI_M['chamber_length'], rel=1e-12)

        out = _kos(perfGovdeler={'k': govde}, motorType='solid')
        kat = out['perf']['k']['oneri']
        assert kat['chamber_diameter'] == pytest.approx(
            GEOMETRI_M['chamber_diameter'] / 1000.0, rel=1e-12), (
            'katıda çap MİLİMETREDİR (güverte tablosu)')
        assert kat['chamber_diameter'] != pytest.approx(
            hib['chamber_diameter'], rel=1e-9), (
            'iki motor tipi aynı ham sayıyı AYNI SI değerine çeviriyor — '
            'birim motor tipinden değil büyüklükten okunuyor demektir')

    @node_gerekli
    def test_sozlesmesiz_alan_onerisiz_kalir_ve_adiyla_beyan_edilir(self):
        """Fail-closed + ADLI yokluk (Doktrin 1).

        ``LENGTH_UNITS['solid']`` ``chamber_length`` SATIRI TAŞIMAZ (katı
        motorda üst seviyede o alan yok — ölçülmüş tablo). Normalize blok
        da gelmediğinde alanın birimi ÇÖZÜLEMEZ: panel sayı uydurmaz,
        alanı önerisiz bırakır ve adını beyan eder. Eski eşikli yol burada
        6,0'ı 0,006 m diye okurdu.
        """
        govde = dict(GOVDE_ORTAK, **GEOMETRI_M)
        out = _kos(perfGovdeler={'k': govde}, motorType='solid')
        kayit = out['perf']['k']
        assert kayit['oneri'].get('chamber_length') is None, (
            'sözleşmesiz alan için sayı üretildi: %r'
            % kayit['oneri'].get('chamber_length'))
        assert kayit['cozulemeyen'] is not None, (
            'panel çözülemeyen alanları beyan eden bir yüzey sunmuyor')
        assert 'chamber_length' in kayit['cozulemeyen'], (
            'çözülemeyen alan adıyla beyan edilmiyor: %s'
            % kayit['cozulemeyen'])
        # Birimi tartışmasız öneriler DÜŞMEZ.
        assert kayit['oneri']['base_isp'] == pytest.approx(govde['isp'])
        assert kayit['oneri']['mdot_total'] == pytest.approx(
            govde['mdot_total'])

    @node_gerekli
    def test_normalize_blok_varsa_deger_bit_ayni_tasiniyor(self):
        """Kapı GEVŞEK değil: blok gelince değer olduğu gibi geçer."""
        govde = dict(GOVDE_ORTAK, **GEOMETRI_M)
        govde['motor_geometry'] = dict(GEOMETRI_M)
        out = _kos(perfGovdeler={'geolu': govde}, motorType='solid')
        oneri = out['perf']['geolu']['oneri']
        assert oneri['chamber_length'] == pytest.approx(
            GEOMETRI_M['chamber_length'], rel=1e-12)
        assert oneri['chamber_diameter'] == pytest.approx(
            GEOMETRI_M['chamber_diameter'], rel=1e-12)
        d = GEOMETRI_M['throat_diameter']
        assert oneri['throat_area'] == pytest.approx(
            math.pi * d * d / 4.0, rel=1e-5)
        assert not out['perf']['geolu']['cozulemeyen']


# ===========================================================================
# OH-D32-03 — çalkalanma büyüklük zarfı ekrana iner
# ===========================================================================
@pytest.fixture(scope='module')
def slosh_yuku():
    """GERÇEK üretici çıktısı — uydurma sözlük yok."""
    from hrma.analysis import slosh_analysis as SA
    return SA.analyze_slosh(radius=0.3, fill_height=0.45,
                            liquid_mass=120.0, fluid_density=1000.0)


class TestOHD3203BuyuklukZarfi:

    def test_yedi_cocuk_da_okuma_envanterinde(self, slosh_yuku):
        """C3 ölçütü: blok adı DA yedi çocuk DA panelde okunuyor."""
        import importlib.util
        yol = REPO_ROOT / 'tests' / 'test_wave4b_contract.py'
        spec = importlib.util.spec_from_file_location('_w4b_d33', yol)
        w4b = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(w4b)
        envanter = w4b._okuma_envanteri('panels/feed_panel.js')
        cocuklar = set(slosh_yuku['size_envelope'])
        assert len(cocuklar) == 7, (
            'uç artık 7 çocuk yayımlamıyor — bekçi eskimiş olabilir')
        assert 'size_envelope' in envanter
        eksik = sorted(cocuklar - envanter)
        assert not eksik, f'panel şu çocukları hâlâ okumuyor: {eksik}'

    def test_borc_ve_sagir_satirlari_dustu(self):
        """Borç TEK YÖNLÜ: ödenen satır kalkmak ZORUNDA."""
        import importlib.util
        yol = REPO_ROOT / 'tests' / 'test_wave4b_contract.py'
        spec = importlib.util.spec_from_file_location('_w4b_d33b', yol)
        w4b = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(w4b)
        assert 'size_envelope' not in w4b.TERS_PANEL_BORCU.get('feed/slosh', {})
        sagir = w4b.TestTersYonBorcEnvanteri.SAGIR_ALT_BLOKLAR
        assert 'size_envelope' not in sagir.get('feed/slosh', {})

    @node_gerekli
    def test_ekranda_bant_yoklugu_ve_eksik_girdi_adi(self, slosh_yuku):
        """Ekranda YOKLUK BEYANI görünür; sayı uydurulmaz."""
        zarf = slosh_yuku['size_envelope']
        out = _kos(slosh=_json_uyumlu(slosh_yuku))
        metin = _metin(out['sloshHtml'])
        assert zarf['canonical_radius_band_m'] is None, (
            'ürün artık kanonik yarıçap bandı yayımlıyor — bekçi eskimiş')
        assert str(zarf['radius_band_status']) in metin, (
            'yarıçap bandı DURUMU ekranda yok')
        assert str(zarf['bond_number_status']) in metin, (
            'Bond sayısı DURUMU ekranda yok')
        assert str(zarf['missing_input_for_bond_number']) in metin, (
            'Bond sayısı için EKSİK GİRDİNİN adı ekranda yok')
        assert zarf['basis'][:40] in metin, 'beyanın dayanağı ekranda yok'
        # Bant yokken sayı UYDURULMADI.
        assert 'NOT DECLARED' in metin or 'BEYAN EDİLMEDİ' in metin

    @node_gerekli
    def test_yayimlanmayan_sayi_sifir_diye_basilmaz(self, slosh_yuku):
        """`Number(null) === 0` tuzağı: yokluk SIFIR diye gösterilemez.

        ÖLÇÜLDÜ: uç bu koşuda `bond_number = None` ve
        `canonical_radius_band_m = None` yayımlıyor (ikisi de "bu büyüklüğe
        hükmedilemedi" demek). Bir ara sürümde panel değeri `Number()` ile
        sayıya zorluyordu ve ekrana `0,000` basılıyordu — ürünün hiç
        ölçmediği bir Bond sayısı. Kapı budur: yayımlanmayan nicelik em
        tireyle durur, sıfırla değil.
        """
        zarf = slosh_yuku['size_envelope']
        assert zarf['bond_number'] is None, (
            'uç artık Bond sayısı yayımlıyor — bekçi eskimiş olabilir')
        out = _kos(slosh=_json_uyumlu(slosh_yuku))
        metin = _metin(out['sloshHtml'])
        # Bond satırı: em tire + ucun kendi durum dizesi yan yana.
        kalip = '— · ' + str(zarf['bond_number_status'])
        assert kalip in metin, (
            'Bond satırı em tire + durum dizesi biçiminde değil: %r'
            % metin[metin.find(str(zarf['bond_number_status'])) - 80:
                    metin.find(str(zarf['bond_number_status'])) + 40])
        assert '0.000 · ' + str(zarf['bond_number_status']) not in metin
        assert '0,000 · ' + str(zarf['bond_number_status']) not in metin


def _json_uyumlu(d):
    """numpy dizileri/sayıları JSON'a çevrilebilir hâle getirir."""
    if isinstance(d, dict):
        return {k: _json_uyumlu(v) for k, v in d.items()}
    if isinstance(d, (list, tuple)):
        return [_json_uyumlu(v) for v in d]
    if isinstance(d, np.ndarray):
        return d.tolist()
    if isinstance(d, (np.floating, np.integer)):
        return d.item()
    return d


# ===========================================================================
# OH-FT-07 — CFD üyesinin KENDİ payı em tireye düşmez
# ===========================================================================
def _tau_uye(yapisik=True):
    """GERÇEK üretici: hrma.cfd.separation._tau_wall_member."""
    from hrma.cfd import separation as S
    n = 40
    z = np.linspace(0.0, 0.2, n)
    p = np.linspace(2.0e6, 3.0e5, n)
    tau = (np.linspace(900.0, 300.0, n) if yapisik
           else np.linspace(900.0, -300.0, n))
    return S._tau_wall_member(
        {'viscous': {'wall_shear_Pa': tau, 'wall_z_m': z}}, p, z, 5, 0.15)


@pytest.fixture(scope='module')
def yapisik_uye():
    return _tau_uye(yapisik=True)


@pytest.fixture(scope='module')
def ayrik_uye():
    return _tau_uye(yapisik=False)


class TestOHFT07CFDUyesininKendiPayi:

    def test_olcum_zemini_margin_min_tanimsiz(self, yapisik_uye):
        """Bekçi sessizce eskimesin: kusurun ön koşulu hâlâ geçerli mi?"""
        assert yapisik_uye['separated'] is False
        assert yapisik_uye['margin_min'] is None
        assert yapisik_uye['tau_wall_min_over_max_abs'] > 0.0
        assert yapisik_uye['tau_wall_margin_critical_value'] == 0.0

    @node_gerekli
    def test_yapisik_kosuda_em_tire_yerine_kendi_payi(self, yapisik_uye):
        out = _kos(cfdUyeleri={'yapisik': {'cfd_tau_w':
                                           _json_uyumlu(yapisik_uye)}})
        metin = _metin(out['cfdHtml']['yapisik'])
        assert 'minimum margin —' not in metin, (
            'üyenin satırı hâlâ em tireye düşüyor: kendi payı yayımlı '
            'olduğu hâlde ekranda yok')
        assert 'tau_wall_min_over_max_abs' in metin, (
            'üyenin KENDİ payı adıyla basılmıyor')
        pay = yapisik_uye['tau_wall_min_over_max_abs']
        assert ('%.3f' % pay) in metin.replace(',', '.'), (
            f'ekranda üyenin ölçtüğü {pay:.3f} yok')

    @node_gerekli
    def test_kritik_deger_ekranda_ve_1_degil(self, yapisik_uye):
        """İki büyüklük aynı anahtarda TOPLANMAZ: kritik değer 0 yazılı."""
        out = _kos(cfdUyeleri={'yapisik': {'cfd_tau_w':
                                           _json_uyumlu(yapisik_uye)}})
        metin = _metin(out['cfdHtml']['yapisik']).replace(',', '.')
        kritik = yapisik_uye['tau_wall_margin_critical_value']
        assert ('%.3f' % kritik) in metin, (
            'üyenin kritik değeri (%.3f) ekranda yok — "1\'in altı = '
            'ayrıldı" kuralıyla karıştırılabilir' % kritik)
        assert 'NOT at 1' in metin or 'DEĞİL' in metin

    @node_gerekli
    def test_marjin_neden_tanimsiz_oldugu_ekranda_kaliyor(self, yapisik_uye):
        """Gerekçe ekrandan DÜŞMEZ — ama ikinci kez de BASILMAZ.

        ÖLÇÜLDÜ (``a1/mutasyon_notu.md``, M3b): ``margin_basis`` bu panelde
        ADIYLA okunmuyor, buna rağmen ekranda duruyor — güvertenin değer
        kaynağı künyesi (``AnalysisDock.ui.source.ledgerInto``,
        ``deep: true``) ``*_basis`` alanlarını tarayıp "NOT MODELLED"
        çipiyle basıyor. Bu bekçi O KANALIN kapanmadığını ölçer; kalemin
        ASIL onarımı (ölçüt satırının kendi payını göstermesi) yukarıdaki
        testlerdedir. İkinci bir kopya eklemek aynı uzun cümleyi tek
        ekranda çoğaltmak olurdu, o yüzden sayı da ölçülür.
        """
        out = _kos(cfdUyeleri={'yapisik': {'cfd_tau_w':
                                           _json_uyumlu(yapisik_uye)}})
        ham = out['cfdHtml']['yapisik']
        dayanak = str(yapisik_uye['margin_basis'])[:40]
        metin = _metin(ham)
        assert dayanak in metin, (
            'marjın NEDEN tanımsız olduğu ekranda hiç yok — değer kaynağı '
            'künyesi bu beyanı taşımayı bırakmış')
        assert 'data-src-kind="missing"' in ham, (
            'beyan artık "modellenmedi" künyesiyle gelmiyor')
        assert metin.count(dayanak) == 1, (
            'aynı gerekçe ekranda %d kez basılıyor — beyan çoğaltılmaz'
            % metin.count(dayanak))

    @node_gerekli
    def test_ayrik_kosuda_ayrilma_konumu_basiliyor(self, ayrik_uye):
        """Regresyon: ayrık koşuda satır konumu basar, paya düşmez."""
        assert ayrik_uye['separated'] is True
        out = _kos(cfdUyeleri={'ayrik': {'cfd_tau_w':
                                         _json_uyumlu(ayrik_uye)}})
        metin = _metin(out['cfdHtml']['ayrik'])
        assert 'SEPARATED' in metin or 'AYRILDI' in metin.upper()
        # Pay CÜMLESİ yalnız YAPIŞIK koşuda kurulur; ayrık koşuda hüküm
        # konumdur. (Alanın ADI `margin_basis` metninde de geçiyor — o
        # ucun kendi gerekçesidir, satırın değeri değil; bu yüzden ölçüt
        # alan adı değil CÜMLEdir.)
        assert 'this member separates at' not in metin, (
            'ayrık koşuda pay cümlesi kurulmamalı: hüküm konumdur')
        assert 'attached' not in metin.lower(), (
            'ayrık koşuda "attached" yazamaz')
