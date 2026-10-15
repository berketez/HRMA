"""Z5 Paket C bekçileri — rozet / dock sözleşmesi / güverte / şablonlar.

Kapsam (test_client + node; sunucuya port BAĞLANMAZ):

C1 (OH-Z4-05) — KENDİ CİDARINI DOĞRULATMA DÖNGÜSÜ
    ``/calculate`` cidar alanı boş bırakılınca cidarı KENDİ boyutlandırıyor
    (``design_mode: size`` · ``wall_thickness_source: sized_by_hrma``),
    ``structural_panel.fromResults`` o sayıyı alana dolduruyor ve
    ``/analyze_structural_safety`` onu ``user_supplied`` +
    ``is_verification: true`` + *"this result is a verification"* diye
    damgalıyordu. Bekçi: künye artık taşınıyor, HRMA'nın kendi cidarı uca
    GÖNDERİLMİYOR (alan "sen boyutlandır" nöbetçisine çekiliyor), kullanıcının
    GERÇEK girdisi ise aynen gidiyor.

C2 (P17B2-11) — ROZET ANLAMBİLİMİ
    "VERDICT ISSUED" (hüküm üretildi) ile "BUCKLING: SAFE" (geçti) aynı
    yeşildi. Bekçi: hüküm-üretildi rozeti nötr tondadır, yeşil yalnız
    "geçti" demektir; durum rozetleri veriden gelen renklerini korur.

C3 (P17B2-12) — CIVATALI BAĞLANTI ROZET ŞERİDİ
    Üç rozet formun ~1.164 px altında akıp gidiyordu, ikisi düz 'info'
    tonundaydı ve veri gelmese bile "— × — class —" basılıyordu. Bekçi:
    şerit YAPIŞKAN (panel gövdesinin üstünde kalır), rozetler gerçek durum
    renklerini taşır, alanı olmayan rozet HİÇ basılmaz (fail-closed).

C4 (P17B2-04) — GÖRÜNÜRLÜK ASİMETRİSİ
    Üründeki 11 ``<details>``in 11'i varsayılan KAPALI ve 9'u beyan taşıyor;
    beyan bir tıklama arkasında, yeşil rozetler sıfır tıklamada. Bekçi:
    katlının özet satırında ÖLÇÜLMÜŞ (uydurulmamış) bir sayaç rozeti
    sıfır tıklamada görünür; beyan taşıyanlar uyarı imi (▲) alır — ⚠
    (U+26A0) DEĞİL, çünkü Berke'nin emoji yasağı o aralığı kapsıyor.

C5 (OH-Z3-03) — GÜVERTE ISI HARİTASI
    ``/calculate_liquid`` yanıtında ``heat_transfer_analysis`` HİÇ YOKTU ve
    ``buildLiquidVizData`` bloğu geçirmiyordu; 3B güvertenin ısı haritası
    sıvı motorda ERİŞİLEMEZDİ (kapı: ``motor_viz3d.js`` ``if
    (gas.throat_heat_flux)``). Bekçi: sıvı çözücü bloğu AYNI soğutma
    çözümünden yayımlar, iki şablon da geçirir, cidar sıcaklığı yalnız
    ÇÖZÜLDÜĞÜNDE basılır (varsayım ölçüm gibi gösterilmez).

Kanıt dosyaları: ``docs/scofield/raw/OH/Z5/c/``
"""

import contextlib
import io
import json
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest
from tests.support.platform_capa import capa_rel

warnings.filterwarnings('ignore')

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANELS_DIR = STATIC_JS / 'panels'
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'
NODE = shutil.which('node')

DOKUNULAN_JS = (
    STATIC_JS / 'analysis_dock.js',
    STATIC_JS / 'motor_viz_deck.js',
    PANELS_DIR / 'structural_panel.js',
    PANELS_DIR / 'joint_panel.js',
)


# ---------------------------------------------------------------------------
# Girdi çapaları — panellerin KENDİ alan varsayılanlarıyla birebir
# ---------------------------------------------------------------------------

#: Hibrit motor, cidar alanı BOŞ: HRMA cidarı kendisi boyutlandırır.
HIBRIT_CIDARSIZ = {
    'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'expansion_ratio': 4.0,
    'nozzle_type': 'conical', 'chamber_material': 'steel_4130',
}
#: Aynı motor, kullanıcının KENDİ cidarıyla (5 mm) — doğrulama yolu.
HIBRIT_CIDARLI = dict(HIBRIT_CIDARSIZ, wall_thickness=5)

KATI_GOVDE = {
    # ÖH D26 (defter P15B3-02): ``thrust``/``burn_time`` katı ucunda TASARIM
    # NOKTASI HEDEFİDİR; bu katsayılarla (a=0,005 / n=0,35) BATES zarfının
    # dışında kalıyordu (ulaşılabilir en küçük ortalama itki ≈285,82 N) ve
    # taban 7751531'de sessizce düşürülüp başlangıç geometrisinin eğrisi 200
    # ile yayımlanıyordu — yani buradaki 1500 N hiçbir zaman etkili olmadı.
    # Zarf kapısı fail-closed olduğundan gövde ZATEN ÖLÇÜLEN geometri kipine
    # çevrildi; yanıt tasarım noktası bloğu dışında BİT-AYNI.
    'motor_name': 'z5c', 'chamber_pressure': 40,
    'grain_type': 'bates', 'chamber_diameter': 100,
    'core_diameter': 35, 'grain_length': 300, 'segments': 1,
    'burn_rate_a': 0.005, 'burn_rate_n': 0.35, 'chamber_temperature': 3000,
    'c_star': 1550, 'propellant_density': 1800, 'propellant_type': 'apcp',
}
SIVI_TABAN = {
    'oxidizer_type': 'lox', 'thrust': 10000, 'chamber_pressure': 100,
    'mixture_ratio': 2.5, 'nozzle_expansion_ratio': 50,
    'max_burn_duration': 400, 'combustion_efficiency': 97,
    'contraction_ratio': 4, 'characteristic_length': 1.2,
    'cooling_type': 'regenerative', 'injector_type': 'impinging',
    'engine_cycle': 'pressure_fed', 'safety_factor': 2.5,
}
SIVI_RP1 = dict(SIVI_TABAN, fuel_type='rp1')
SIVI_METAN = dict(SIVI_TABAN, fuel_type='methane')

#: joint_panel.js alan varsayılanlarıyla birebir.
CIVATA_GOVDE = {
    'pressure_bar': 40, 'seal_diameter_mm': 100, 'bolt_count': 8,
    'size': 'M8', 'property_class': '8.8', 'grip_length_mm': 20,
    'member_material': 'aluminum_6061', 'lubricated': 'false',
    'reusable': 'true',
}

#: ÇAPA — hibrit ısı zinciri Z5-C'de DEĞİŞMEMELİ (bit-aynı).
#:
#: ÇAPA YENİLENDİ (ÖH D15 fix-3 / taban geçişi, 1 Eyl 2026):
#: 5.964.909,223079122 → 5.753.752,660419232 W/m² (−3,54 %).
#: DEĞİŞTİREN Z5-C DEĞİL, ÖH Z5S / PK5'tir (defter P4B1-03, commit
#: bba33e4): boğaz ışıma bacağı hazne DURGUNLUK durumundan (T_g = Taw,
#: p = P_c, ışın yolu L = 0,9·D_hazne) o istasyonun YEREL STATİK
#: durumuna ve yerel çapına taşındı — bkz.
#: hrma/analysis/heat_transfer_analysis.py:1786-1792 ("Işıma yapan gaz,
#: o istasyondaki gazdır; alanın adı da 'throat_heat_flux'tır") ve tek
#: tanım noktası :887 ``_design_heat_flux``. Boğazda statik sıcaklık ve
#: basınç durgunluk değerlerinin altındadır, ışın yolu da hazne çapı
#: yerine boğaz çapıyla kurulur; Leckner gaz emisivitesi p·L ile arttığı
#: için ışıma payı DÜŞER ve toplam tasarım akısı bu yüzden azalır.
#: Eski çapanın gerekçesi ("Z5-C hibriti değiştirmez") HÂLÂ geçerlidir —
#: hibriti değiştiren Z5-C değil, ısı-soğutma kulvarının fizik
#: onarımıdır. Sayı ÖLÇÜLDÜ (aynı fikstür, iki bağımsız koşum bit-aynı).
#:
#: ÇAPA YENİLENDİ (ÖH D17 fix-7, 2 Eyl 2026):
#: 5.753.752,660419232 → 5.688.519,2896965 W/m² (−1,13 %).
#: DEĞİŞTİREN D17 hibrit kulvarı OH-Z5-02 (commit 2450970): ışıma
#: kompozisyonu x_H2O / x_CO2 artık heat_transfer_analysis'in modül
#: varsayılanı değil, motorun kendi CEA denge kesirleridir (hibrit motor
#: → motor_data; kalem "sabit çıktı yaprağı" kusuruydu). Gerçek kesirler
#: varsayılanın altında → Leckner emisivitesi ve ışıma payı düşer, boğaz
#: tasarım akısı bu yüzden azalır (aynı onarım hazne akısını −%7,03,
#: TPS q_net'i −%19,6 kaydırdı; D17 hibrit capa_fark.json). Sayı ÖLÇÜLDÜ
#: (taban kaydı-2, main 2a6862b, aynı fikstür).
#:
#: ÇAPA YENİLENDİ (ÖH D18 fizik-a2, 2 Eyl 2026):
#: 5.688.519,2896965 → 5.670.371,886919364 W/m² (−0,319 %).
#: DEĞİŞTİREN **bu aşama DEĞİL, D18 fizik-a1**'dir (commit 779a1c6, kalemler
#: B3-05 + B3-02): boğaz ve çıkış istasyonları tek-γ kapalı formundan kayan
#: denge çözümüne taşındı (NASA RP-1311 Part I §6.3.3), c* artık aynı
#: istasyondan geliyor; hibrit boğaz gaz durumu (ρ_t, T_t, v_t) bu yüzden
#: kaydı ve ısı akısı onunla birlikte indi. ATIF ÖLÇÜLDÜ, tahmin edilmedi:
#: bu bekçi ``git archive 779a1c6`` ile çıkarılan a1 ağacında da KIRMIZI
#: koşuyor (a1 kendi çapasını yenilememişti); a2'nin diff'i yalnız sıvı
#: motora, tank basıncına ve L*/ε_c tabanına dokunur ve hibrit yaprağını
#: oynatmaz. Sayı a2 ağacından ölçüldü.
#:
#: ÇAPA YENİLENDİ (ÖH D19 fix-12, 3 Eyl 2026): 5670371.886919364 → 5672675.567434634 W/m²
#: (+%0,041). Değiştiren D19 hibrit B3-12 (09867aa): reaktan molekül ağırlığı tek
#: kaynağa alınınca yanma çözümü (T_c +1,0 K) ve ısı zinciri kaydı. Ölçüldü
#: (taban kaydı-4, main d914908).
#:
#: ÇAPA YENİLENDİ (ÖH D21 fix-14, 4 Eyl 2026): değiştiren D20 fizik-c B1-12 (34ab8b9) — hibrit manşet C_F tek kayıp kümesine bağlandı (η_kin boyutlandırmadan ÖNCE sabit noktaya çözülür): manşet Isp −%2,36, boğaz çapı +%1,2, kamara çapı 78,88→79,60 mm, ondan türeyen bütün yapraklar (geometri, ısı akısı, itki eğrisi, apoje) kaydı; D20 fizik çapa kaydı docs/scofield/raw/OH/D20/fizik/a1/03_capa_kiyas.txt atıflı. Sayı ölçüldü (taban kaydı-5, main b613b2b).
#: 5672675.567434634 → 5659183.214773782 W/m² (−%0,238): boğaz büyüyünce ısı akısı düştü.
#:
#: ÇAPA YENİLENDİ (ÖH D21 fix-15, 4 Eyl 2026): değiştiren D21 hibrit a1 P15B1-04 (676a2a5) — çan sapma verimi λ tek kaynağa alındı (nozzle_design ⟷ hybrid_rocket_engine iki kopya birleşti; hibrit çapasında 27.098 yaprak ~1e-5 bağıl kaydı, λ bağıl değişimi 3,77e-05; docs/scofield/raw/OH/D21/hibrit/a1/capa_fark_ozet.json). Sayı ölçüldü (main 7776bfb, D21 14/15 birleşik). 5659183.214773782 → 5659161.347318558 W/m² (−3,9e-6).
#:
#: ÇAPA YENİLENDİ (ÖH D22 fix-18, 4 Eyl 2026): değiştiren D22 hibrit a1 (60509f2) — OH-D21-03: kinetik verim artık İSTENEN değil GERÇEKLEŞEN L*'ı okuyor ve boyutlandırma L* sabit-noktasına sarıldı (η_kin ↔ boğaz/kamara geometrisi); OH-D21-02: transient C_F kayıp kümesini taşıyor. Hibrit zinciri (geometri, ısı akısı, itki eğrisi, apoje) onunla kaydı; D22 hibrit çapa kaydı docs/scofield/raw/OH/D22/hibrit/a1/capa_kiyas.json atıflı. Sayı ölçüldü (main 2e60b9a, D22 12/16 birleşik). 5659161.347318558 → 5665947.829137343 W/m² (+%0,12).
#: ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K doymuş SIVI
#: giriş entalpisi. Kâhin: CEA kök denetimi
#: (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) + önce/sonra
#: (p1a rapor §12). Tolerans DEĞİŞMEDİ.
#: 5665947.829137343 -> 5443058.87619067 W/m² (−%3,93): daha soğuk oda.
HIBRIT_BOGAZ_AKISI_W_M2 = 5443058.87619067


def _sessiz(fn, *a, **k):
    """Çözücüler stdout'a bolca basıyor; testte sessize alınır."""
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon), contextlib.redirect_stderr(tampon):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post_ok(client, url, payload):
    r = _sessiz(client.post, url, json=payload)
    assert r.status_code == 200, (
        f'{url} 200 dönmedi: {r.status_code} — '
        f'{r.get_data(as_text=True)[:300]}')
    j = r.get_json()
    return j.get('motor', j) if isinstance(j, dict) else j


@pytest.fixture(scope='module')
def hibrit_cidarsiz(client):
    return _post_ok(client, '/calculate', HIBRIT_CIDARSIZ)


@pytest.fixture(scope='module')
def hibrit_cidarli(client):
    return _post_ok(client, '/calculate', HIBRIT_CIDARLI)


@pytest.fixture(scope='module')
def kati(client):
    return _post_ok(client, '/calculate_solid', KATI_GOVDE)


@pytest.fixture(scope='module')
def sivi_rp1(client):
    return _post_ok(client, '/calculate_liquid', SIVI_RP1)


@pytest.fixture(scope='module')
def sivi_metan(client):
    return _post_ok(client, '/calculate_liquid', SIVI_METAN)


def oku(yol: Path) -> str:
    return yol.read_text(encoding='utf-8')


def js_yorumsuz(metin: str) -> str:
    """JS yorumlarını aynı uzunlukta boşlukla değiştirir (ofset korunur).

    Kaynak-sözleşme bekçileri YORUMU değil KODU ölçmelidir: bu dosyalardaki
    açıklama blokları eski kusurun metnini bilerek taşıyor.
    """
    def bosalt(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    metin = re.sub(r'/\*[\s\S]*?\*/', bosalt, metin)
    return re.sub(r'(?m)//[^\n]*', bosalt, metin)


# ===========================================================================
# node koşum altyapısı — asgari sahte DOM (jsdom YOK)
# ===========================================================================

SAHTE_DOM = r"""
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this.dataset = {};
    this._attrs = {}; this._text = ''; this.innerHTML = '';
    this.value = ''; this.options = []; this._listeners = {};
    this.classList = { contains: function () { return false; },
                       add: function () {}, toggle: function () {} };
}
Object.defineProperty(El.prototype, 'textContent', {
    get: function () {
        if (this.children.length) {
            return this._text + this.children.map(function (c) {
                return c.textContent; }).join('');
        }
        return this._text;
    },
    set: function (v) { this._text = String(v); this.children = []; }
});
Object.defineProperty(El.prototype, 'firstElementChild', {
    get: function () { return this._first || (this._first = new El('div')); }
});
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { this.children.push(c); return c; };
El.prototype.remove = function () {};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k)
        ? this._attrs[k] : null; };
El.prototype.addEventListener = function (t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn); };
El.prototype._descendants = function () {
    var out = [];
    this.children.forEach(function (c) {
        out.push(c); out = out.concat(c._descendants()); });
    return out;
};
El.prototype.querySelectorAll = function (sel) {
    if (String(sel).charAt(0) === '[') {
        var ad = String(sel).slice(1, -1);
        return this._descendants().filter(function (e) {
            return e.getAttribute(ad) !== null; });
    }
    var tag = String(sel).replace(/[^a-zA-Z]/g, '').toUpperCase();
    return this._descendants().filter(function (e) { return e.tagName === tag; });
};
El.prototype.querySelector = function (sel) {
    var hepsi = this.querySelectorAll(sel);
    return hepsi.length ? hepsi[0] : null;
};
var _byId = {};
function getEl(id) {
    if (!_byId[id]) _byId[id] = new El('div');
    return _byId[id];
}
var documentStub = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function (s) { return documentStub.body.querySelector(s); },
    querySelectorAll: function (s) { return documentStub.body.querySelectorAll(s); },
    getElementById: getEl,
    addEventListener: function () {}
};
var sandbox = {
    console: { log: console.log, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, Promise: Promise, Error: Error,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub, fetch: function () { return Promise.resolve({}); }
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
function yukle(rel) {
    vm.runInContext(fs.readFileSync(path.join(staticDir, rel), 'utf8'),
                    sandbox, { filename: rel });
}
"""

HARNESS_BASI = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const staticDir = process.argv[2];
const girdiDosyasi = process.argv[3];
""" + SAHTE_DOM


def node_kos(tmp_path, govde_js, girdi=None, ad='z5c_harness.js'):
    """Sahte DOM'lu bir node koşumu çalıştırır ve JSON çıktısını döndürür."""
    harness = tmp_path / ad
    harness.write_text(HARNESS_BASI + govde_js, encoding='utf-8')
    argv = [NODE, str(harness), str(STATIC_JS)]
    if girdi is not None:
        veri = tmp_path / 'girdi.json'
        veri.write_text(json.dumps(girdi), encoding='utf-8')
        argv.append(str(veri))
    sonuc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    assert sonuc.returncode == 0, (
        'node koşumu hata verdi:\n' + sonuc.stderr[-2000:])
    assert sonuc.stdout.strip(), (
        'node koşumu çıktı üretmedi:\n' + sonuc.stderr[-2000:])
    return json.loads(sonuc.stdout.strip())


# ===========================================================================
# C1 — kendi cidarını doğrulatma döngüsü
# ===========================================================================

C1_HARNESS = r"""
yukle('analysis_dock.js');
yukle(path.join('panels', 'structural_panel.js'));
sandbox.window.AnalysisDock._setMotorType('hybrid');
const sonuc = JSON.parse(fs.readFileSync(girdiDosyasi, 'utf8'));
const spec = sandbox.window.AnalysisDock._registry
    .filter(function (s) { return s.id === 'structural'; })[0];
const oneri = spec.fromResults(sonuc);
const w = oneri.wall_thickness;
const gerekceler = oneri[sandbox.window.AnalysisDock.ui.WITHHELD_KEY] || {};
const kunye = sandbox.window.AnalysisDock.ui.readWallThicknessProvenance(sonuc);
console.log(JSON.stringify({
    kunyeSource: kunye.source,
    kunyeDesignMode: kunye.designMode,
    kunyeDeclared: kunye.declared,
    kunyeBlockPath: kunye.blockPath,
    kunyeValueMm: kunye.value_mm,
    geriCekildi: !!gerekceler.wall_thickness,
    alanDegeri: w,
    alanTipi: typeof w,
    gerekce: gerekceler.wall_thickness || null
}));
"""


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_c1_hrma_kendi_cidarini_uca_geri_gondermez(tmp_path, hibrit_cidarsiz):
    """C1: HRMA'nın boyutlandırdığı cidar 'kullanıcının cidarı' diye gitmez.

    ÖNCE (ölçüldü, ``olcum_c1_once.txt``): panel alanına 15,903671 mm
    dolduruluyordu ve uç ``user_supplied`` + ``is_verification: true`` +
    "this result is a verification" diyordu.
    SONRA: öneri GERİ ÇEKİLİYOR, alan "sen boyutlandır" nöbetçisine (0)
    çekiliyor ve gerekçe künyeyle birlikte taşınıyor.
    """
    ca = (hibrit_cidarsiz.get('structural_analysis') or {}).get(
        'chamber_analysis') or {}
    assert ca.get('design_mode') == 'size', (
        'ön koşul kırıldı: cidarsız koşumda motor kendi cidarını '
        f"boyutlandırmıyor (design_mode={ca.get('design_mode')!r})")

    d = node_kos(tmp_path, C1_HARNESS, hibrit_cidarsiz)
    assert d['kunyeSource'] == 'solver_sized', (
        f"künye HRMA'nın kendi cidarını tanımıyor: {d}")
    assert d['kunyeDesignMode'] == 'size'
    assert d['kunyeBlockPath'] == 'structural_analysis.chamber_analysis', (
        f"künye bloğu adıyla taşınmıyor: {d['kunyeBlockPath']!r}")
    assert d['geriCekildi'] is True, (
        "HRMA'nın kendi boyutlandırdığı cidar hâlâ uca öneriliyor "
        f"(alan değeri {d['alanDegeri']!r}) — kendi kendini doğrulatma "
        'döngüsü geri geldi')
    assert d['alanDegeri'] == 0, (
        "geri çekilen alan 'sen boyutlandır' nöbetçisine (0) çekilmiyor: "
        f"{d['alanDegeri']!r}")
    # Gerekçe MAKİNE ADLARINI taşımalı: kullanıcı hangi alanın ne dediğini
    # görebilmeli (çeviri anahtarı açılmaz — Z4 NOT_KEYS kaçışı).
    for parca in ('design_mode', 'wall_thickness_source', 'sized_by_hrma'):
        assert parca in d['gerekce'], (
            f'geri çekme gerekçesi {parca!r} adını taşımıyor: {d["gerekce"]!r}')


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_c1_kullanicinin_gercek_cidari_aynen_gider(tmp_path, hibrit_cidarli):
    """C1 yanlış-pozitif kapısı: GERÇEK kullanıcı cidarı susturulmamalı.

    Kullanıcı /calculate'e 5 mm verdiyse motor ``design_mode: verify``
    diyor; o cidar panele taşınır ve uçta doğrulama yolu (user_supplied)
    aynen çalışır. Geri çekme bu yolu KIRMAMALIDIR.
    """
    ca = (hibrit_cidarli.get('structural_analysis') or {}).get(
        'chamber_analysis') or {}
    assert ca.get('design_mode') == 'verify', (
        'ön koşul kırıldı: kullanıcı cidarıyla koşumda design_mode '
        f"{ca.get('design_mode')!r}")

    d = node_kos(tmp_path, C1_HARNESS, hibrit_cidarli)
    assert d['kunyeSource'] == 'user_supplied', d
    assert d['geriCekildi'] is False, (
        'kullanıcının GERÇEK cidarı da geri çekiliyor — doğrulama yolu öldü')
    assert abs(d['alanDegeri'] - 0.005) < 1e-12, (
        f"kullanıcının 5 mm cidarı metreye çevrilip taşınmıyor: {d['alanDegeri']!r}")


def test_c1_ucun_kapisi_nobetci_sifiri_hic_gelmemis_sayar(client,
                                                          hibrit_cidarsiz):
    """C1 uç ayağı: alan 0 iken uç WALL_GATE_SIZED yolunu kazanır.

    Panelin geri çekmesi ancak uç 0'ı "hiç gelmedi" sayarsa dürüsttür.
    Ölçüldü (``olcum_c1_sifir_cidar.txt``): 0 ile alanın hiç olmaması AYNI
    künyeyi üretir — ``not_supplied`` + ``sized_by_hrma`` +
    ``is_verification: False``.
    """
    taban = {
        'chamber_pressure': hibrit_cidarsiz.get('chamber_pressure'),
        'chamber_diameter': hibrit_cidarsiz.get('chamber_diameter'),
        'chamber_length': hibrit_cidarsiz.get('chamber_length'),
        'throat_diameter': hibrit_cidarsiz.get('throat_diameter'),
        'burn_time': hibrit_cidarsiz.get('burn_time'),
        # ÖH D15 birleştirme (1 Eyl 2026): burada 0 İDİ. Yapısal kulvar
        # ``/analyze_structural_safety``e fiziksel girdi kapısı koydu ve
        # sıfır kamara sıcaklığını 422 + ``must_be_positive`` ile
        # reddediyor (fail-closed, kazanır). 0 bu bekçide "verilmedi"
        # nöbetçisi DEĞİLDİ — nöbetçi ``wall_thickness``tır ve aşağıda
        # aynen duruyor. Sıcaklık motorun KENDİ yanıtından alınır ki
        # ikinci bir sayı kaynağı doğmasın.
        'chamber_temperature': hibrit_cidarsiz.get('chamber_temperature'),
        'thrust': hibrit_cidarsiz.get('thrust'),
        'material': 'steel_4130',
    }
    assert isinstance(taban['chamber_temperature'], (int, float)) and (
        taban['chamber_temperature'] > 0), (
        'fikstür dayanağı düştü: motor yanıtı kamara sıcaklığı yayımlamıyor '
        '(%r)' % taban['chamber_temperature'])
    sifirli = _post_ok(client, '/analyze_structural_safety',
                       dict(taban, wall_thickness=0))
    alansiz = _post_ok(client, '/analyze_structural_safety', taban)
    for ad, govde in (('wall_thickness=0', sifirli), ('alan yok', alansiz)):
        db = govde.get('design_basis') or {}
        assert db.get('wall_thickness_source') == 'sized_by_hrma', (
            f'{ad}: uç kapısı sized_by_hrma demiyor: {db!r}')
        assert db.get('is_verification') is False, (
            f'{ad}: kullanıcının vermediği cidar için "doğrulama" damgası')
        # ÇEVRİLDİ — ÖH D30 / app-api-uc a1 (P16B1-33). Eski hâl İKİ ayrı
        # olayın (alan HİÇ gelmedi ⟷ alan 0 geldi = "sen boyutlandır")
        # AYNI künyeyi taşımasını ŞART KOŞUYORDU; kusur tam buydu: ürün,
        # kullanıcının GÖNDERDİĞİ alan için "hiç vermediniz" diyordu
        # (ölçüldü ``D30/app-api-uc/a1/once.json`` K1). Bu bekçinin ASIL
        # ölçtüğü şey — 0'ın doğrulama modunu AÇMADIĞI — yukarıdaki üç
        # assert'te (``sized_by_hrma`` + ``is_verification False`` +
        # 'DESIGN PROPOSAL') aynen duruyor ve gevşetilmedi. Değişen tek şey:
        # iki olay artık kendi adıyla anılıyor.
        assert db.get('wall_thickness_input_status') == (
            'sizing_sentinel' if ad == 'wall_thickness=0' else 'not_supplied'
        ), (ad, db.get('wall_thickness_input_status'))
        assert 'DESIGN PROPOSAL' in str(db.get('message') or ''), (
            f'{ad}: uç bunun bir öneri olduğunu söylemiyor: '
            f'{db.get("message")!r}')

    # Motorun KENDİ cidarı geri gönderilseydi uç "verification" derdi —
    # kırılan döngünün karşı ölçümü (bu satır kusurun kendisini ölçer).
    ca = (hibrit_cidarsiz.get('structural_analysis') or {}).get(
        'chamber_analysis') or {}
    motor_cidari_mm = ca.get('wall_thickness_used_mm')
    assert isinstance(motor_cidari_mm, float) and motor_cidari_mm > 0
    dongu = _post_ok(client, '/analyze_structural_safety',
                     dict(taban, wall_thickness=motor_cidari_mm / 1000.0))
    dongu_db = dongu.get('design_basis') or {}
    assert dongu_db.get('is_verification') is True, (
        'karşı ölçüm bozuldu: motorun kendi cidarı gönderildiğinde uç artık '
        '"doğrulama" demiyor — bu bekçinin ölçtüğü kusur ortadan kalkmış '
        'olabilir, önce onu doğrulayın')


def test_c1_dock_geri_cekme_sozlesmesi_kaynakta_var():
    """C1 kaynak sözleşmesi: geri çekme kapısı applySuggestions'ın İÇİNDE.

    Geri çekme, kullanıcının elle yazdığı alanı (``data-dirty``) EZMEMELİ;
    bu ancak dirty kapısından SONRA gelirse sağlanır.
    """
    src = js_yorumsuz(oku(STATIC_JS / 'analysis_dock.js'))
    assert 'WITHHELD_KEY' in src, 'geri çekme sözleşmesi kaynakta yok'
    # Ölçüm applySuggestions gövdesinin İÇİNDE yapılır (sabitin tanımı daha
    # yukarıda; sıralama kapısı yalnız uygulama yerinde anlamlı).
    bas = src.index('function applySuggestions(')
    govde = src[bas:src.index('function paintFieldSources(', bas)]
    dirty = govde.index("el.dataset.dirty === '1'")
    withhold = govde.index('gerekceler[k]')
    assert dirty < withhold, (
        'geri çekme kapısı data-dirty kapısından ÖNCE geliyor — kullanıcının '
        'kendi yazdığı cidar da silinir')
    assert 'readWallThicknessProvenance' in src
    # Künye motorun KENDİ beyanından okunmalı, panelde uydurulmamalı.
    assert 'design_mode' in src, 'künye alanı (design_mode) okunmuyor'


def test_c1_panel_kunyeyi_ekrana_basiyor():
    """C1 ekran ayağı: geri çekme gerekçesi panelde görünür."""
    src = js_yorumsuz(oku(PANELS_DIR / 'structural_panel.js'))
    assert 'wall_thickness_suggestion' in src, (
        'panel geri çekme künyesini ekrana hiç basmıyor')
    assert 'wallThicknessSuggestion(r)' in src, (
        'fromResults hâlâ künyesiz ham cidar okumasını kullanıyor')
    assert 'wall_thickness: U.readWallThicknessM(r)' not in src, (
        'künyesiz ham okuma cidar alanına geri döndü (C1 gerilemesi)')


# ===========================================================================
# C2 — rozet anlambilimi
# ===========================================================================

def test_c2_hukum_uretildi_rozeti_yesil_degil():
    """C2: "hüküm üretildi" bir GEÇME değildir; yeşil olamaz.

    ÖNCE: ``U.badge(... , withheld ? 'warn' : 'ok')`` — yeşil "VERDICT
    ISSUED" ile yeşil "BUCKLING: SAFE" birebir aynı renkti.
    """
    src = js_yorumsuz(oku(PANELS_DIR / 'structural_panel.js'))
    kalip = re.compile(
        r"verdictIssued'[^)]*?\)\s*,\s*\n?\s*withheld\s*\?\s*'warn'\s*:\s*'(\w+)'",
        re.S)
    m = kalip.search(src)
    assert m, ('VERDICT ISSUED rozetinin renk ifadesi bulunamadı — '
               'kalıp değiştiyse bekçi güncellenmeli')
    assert m.group(1) != 'ok', (
        "'hüküm üretildi' rozeti yeşil ('ok'): yeşil hem 'geçti' hem "
        "'hüküm üretildi' demek oluyor (P17B2-11 gerilemesi)")
    assert m.group(1) in ('info', 'dim'), (
        f"nötr ton bekleniyordu, {m.group(1)!r} bulundu")


def test_c2_durum_rozetleri_veriden_gelen_rengini_korur():
    """C2 yanlış-pozitif kapısı: SAFE/UNSAFE rozetleri sabitlenmemeli."""
    src = js_yorumsuz(oku(PANELS_DIR / 'structural_panel.js'))
    for ad in ('badgeBuckling', 'badgeStructure', 'badgeFatigue'):
        satir = re.search(ad + r"'[\s\S]{0,400}?statusKind\(", src)
        assert satir, (
            f'{ad} rozeti artık statusKind ile renklenmiyor — durum rengi '
            'veriden geliyor olmalı')


# ===========================================================================
# C3 — cıvatalı bağlantı rozet şeridi
# ===========================================================================

C3_HARNESS = r"""
yukle('analysis_dock.js');
yukle(path.join('panels', 'joint_panel.js'));
const veri = JSON.parse(fs.readFileSync(girdiDosyasi, 'utf8'));
const root = new El('div');
sandbox.window.JointPanel._render(veri, root);
const hepsi = root.children.map(function (c) { return c.innerHTML || ''; }).join('\n');
const seritStil = (hepsi.match(/<div style="(display:flex[^"]*sticky[^"]*)">/) || [])[1] || '';
const serit = (hepsi.match(/<div style="display:flex[^"]*sticky[^"]*">([\s\S]*?)<\/div>/) || [])[1] || '';
const rozetler = serit.match(/<span title="[^"]*" style="border:1px solid [^;]+;/g) || [];
console.log(JSON.stringify({
    seritVar: !!seritStil,
    yapiskan: /position:sticky/.test(seritStil),
    rozetSayisi: rozetler.length,
    renkler: (serit.match(/border:1px solid (var\(--hd-[a-z-]+)/g) || []),
    metinler: (serit.match(/>([^<>]{2,60})<\/span>/g) || []).map(function (s) {
        return s.replace(/^>/, '').replace(/<\/span>$/, ''); })
}));
"""


@pytest.fixture(scope='module')
def civata(client):
    r = _sessiz(client.post, '/api/bolted-joint', json=CIVATA_GOVDE)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_c3_rozet_seridi_yapiskan_ve_uc_rozet_de_basiliyor(tmp_path, civata):
    """C3: üç rozetin üçü de görünür şeritte, gerçek durum renkleriyle.

    ÖNCE (görsel tur): "üç rozetin ikisi ekranda YOK; görünen tek rozet
    sönük gri ve 1.164 px aşağıda". Ölçüldü: üçü de ÜRETİLİYOR ama şerit
    10 alanlık formun altında akıp gidiyor ve son iki rozet düz 'info'
    tonunda, yani hüküm rengiyle künye rengi ayrılmıyor.
    """
    d = node_kos(tmp_path, C3_HARNESS, civata)
    assert d['seritVar'], 'rozet şeridi hiç basılmadı'
    assert d['yapiskan'], (
        'rozet şeridi yapışkan değil — hüküm yine formun altında kalır')
    assert d['rozetSayisi'] >= 3, (
        f'şeritte {d["rozetSayisi"]} rozet var, en az 3 bekleniyordu: '
        f'{d["metinler"]}')
    # Hüküm rozeti (ayrılma) + gerilme hükmü VERİDEN gelen renk taşımalı;
    # düz künye rozetleri nötr kalır. En az bir yeşil/amber/kırmızı olmalı.
    durum_renkleri = [c for c in d['renkler']
                      if 'green' in c or 'orange' in c or 'red' in c]
    assert durum_renkleri, (
        'şeritte tek bir DURUM rengi yok — hepsi nötr künye tonunda: '
        f'{d["renkler"]}')
    assert any('BOLT STRESS' in t for t in d['metinler']), (
        f'cıvata gerilme hükmü şeride inmiyor: {d["metinler"]}')


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_c3_veri_yoksa_rozet_basilmaz(tmp_path):
    """C3 fail-closed: alanı olmayan rozet uydurma künyeyle basılmaz.

    ÖNCE: veri gelmese de "— × — class —" rozeti basılıyordu.
    """
    d = node_kos(tmp_path, C3_HARNESS, {})
    assert d['rozetSayisi'] == 0, (
        f'veri yokken {d["rozetSayisi"]} rozet basıldı: {d["metinler"]}')
    assert not any('—' in t for t in d['metinler']), (
        f'uydurma "—" künyesi hâlâ basılıyor: {d["metinler"]}')


# ===========================================================================
# C4 — katlanmış beyanın sıfır-tıklama sayacı
# ===========================================================================

C4_HARNESS = r"""
yukle('analysis_dock.js');
const KATLILAR = JSON.parse(fs.readFileSync(girdiDosyasi, 'utf8'));
const body = new El('body');
KATLILAR.forEach(function (k) {
    const det = new El('details');
    Object.keys(k.attrs || {}).forEach(function (a) {
        det.setAttribute(a, k.attrs[a]); });
    const sum = new El('summary');
    if (k.i18n) sum.setAttribute('data-i18n', k.i18n);
    sum.textContent = k.ad;
    det.appendChild(sum);
    const govde = new El('div');
    for (var i = 0; i < (k.maddeler || 0); i++) {
        const li = new El('li');
        li.textContent = 'madde ' + (i + 1);
        govde.appendChild(li);
    }
    if (!k.maddeler) govde.textContent = 'x'.repeat(k.karakter || 0);
    det.appendChild(govde);
    body.appendChild(det);
});
function olc() {
    var gorunur = 0;
    body.querySelectorAll('details').forEach(function (d) {
        var slot = d.querySelector('summary')
            .querySelector('[data-hd-declfold-slot]');
        if (slot && String(slot.textContent).trim()) gorunur += 1;
    });
    return gorunur;
}
const once = olc();
const isaretlenen = sandbox.window.AnalysisDock.ui.markDeclarationFolds(body);
const sonra = olc();
const rozetler = body.querySelectorAll('details').map(function (d) {
    var sum = d.querySelector('summary');
    var slot = sum.querySelector('[data-hd-declfold-slot]');
    return { ad: sum._text, rozet: slot ? slot.textContent : '',
             ipucu: slot ? slot.getAttribute('title') : '',
             sinif: d.dataset.hdDeclfold || null };
});
console.log(JSON.stringify({
    once: once, sonra: sonra, isaretlenen: isaretlenen, rozetler: rozetler
}));
"""

#: Ürünün GERÇEK katlıları — kimlik/nitelik değerleri kaynak dosyalardan
#: alınmıştır (envanter: docs/scofield/raw/OH/Z5/c/olcum_c4_details_envanteri).
URUN_KATLILARI = [
    {'ad': 'blowdown bp_basis', 'attrs': {'id': 'bp_basis'},
     'i18n': 'bd.basisTitle', 'karakter': 512},
    {'ad': 'blowdown kanal tablosu', 'attrs': {}, 'karakter': 240},
    {'ad': 'fea fea_basis', 'attrs': {'id': 'fea_basis'},
     'i18n': 'fea.basisTitle', 'karakter': 1180},
    {'ad': 'fea grainfea_basis', 'attrs': {'id': 'grainfea_basis'},
     'i18n': 'fea.basisTitle', 'karakter': 940},
    {'ad': 'fea basis_1', 'attrs': {'id': 'feabasis_1'},
     'i18n': 'fea.basisTitle', 'karakter': 700},
    {'ad': 'fea basis_2', 'attrs': {'id': 'feabasis_2'},
     'i18n': 'fea.basisTitle', 'karakter': 700},
    {'ad': 'thermal_fea fea_t_basis', 'attrs': {'id': 'fea_t_basis'},
     'i18n': 'fea.basisTitle', 'karakter': 860},
    {'ad': 'injector varsayımlar', 'attrs': {},
     'i18n': 'common.assumptions', 'maddeler': 5},
    {'ad': 'stability not-modelled',
     'attrs': {'data-stab-fold': 'not-modelled'}, 'maddeler': 6},
    {'ad': 'stability assumptions',
     'attrs': {'data-stab-fold': 'assumptions'}, 'maddeler': 4},
    {'ad': 'correlation katman', 'attrs': {}, 'karakter': 320},
    # ÖH D26 / P11B2-10 — panel beyan defteri (analysis_dock.js::
    # sourceLedger). Envanter bekçisi kusur değil ÖLÇÜM GEÇERLİLİĞİ
    # bekçisidir ve kendi belgesinde "yeni bir katlı eklenirse
    # envanter güncellenmelidir" der: 12. katlı budur. Varsayılan
    # KAPALI (yalnız opts.open ile açılır) ve gövdesi beyan satırı
    # taşıdığı için C4 sayacı sıfır tıklamada zaten basılır.
    {'ad': 'dock değer kaynakları defteri',
     'attrs': {'data-src-ledger': '3'}, 'maddeler': 3},
]


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_c4_katli_beyan_sifir_tiklamada_sayilir(tmp_path):
    """C4: her katlının özet satırında ÖLÇÜLMÜŞ bir sayaç görünür.

    ÖNCE: 11 katlının 11'i kapalı, özet satırında hiçbir sayaç yok — beyan
    tamamen bir tıklama arkasında.
    """
    d = node_kos(tmp_path, C4_HARNESS, URUN_KATLILARI)
    assert d['once'] == 0, 'ön koşul kırıldı: sahnede zaten sayaç var'
    assert d['sonra'] == len(URUN_KATLILARI), (
        f'{d["sonra"]}/{len(URUN_KATLILARI)} katlıda sıfır-tıklama sayacı var')
    beyan = [r for r in d['rozetler'] if r['sinif'] == 'declaration']
    assert len(beyan) >= 9, (
        f'beyan taşıyan katlı sayısı {len(beyan)} — bulgunun ölçtüğü 9 '
        f'katlının hepsi imlenmedi: {[r["ad"] for r in d["rozetler"]]}')
    for r in beyan:
        assert r['rozet'].startswith('▲'), (
            f'beyan katlısı uyarı imi taşımıyor: {r}')
    # Sayı UYDURULMAZ: ipucu ölçümün üç bileşenini de adıyla yazar.
    for r in d['rozetler']:
        for parca in ('items=', 'lines=', 'chars='):
            assert parca in r['ipucu'], (
                f'sayaç ipucu ölçümü adıyla vermiyor ({parca}): {r}')


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_c4_bos_katliya_rozet_basilmaz(tmp_path):
    """C4 fail-closed: gövdesi boş katlı (henüz doldurulmamış kabuk) sayılmaz."""
    d = node_kos(tmp_path, C4_HARNESS,
                 [{'ad': 'bos fea_basis', 'attrs': {'id': 'fea_basis'},
                   'karakter': 0}])
    assert d['sonra'] == 0, (
        'gövdesi boş katlıya sayaç basıldı — ölçülmemiş bir sayı gösteriliyor')


#: ÖH D31 fix-34b — ÜRÜN KATLI ALANLARININ ÖLÇÜLEN KÜMESİ.
#:
#: Bu küme ``URUN_KATLILARI`` (ÇALIŞMA ANI örnekleri, C4 iskelesinin
#: girdisi) ile AYNI ŞEY DEĞİLDİR; buradaki her satır KAYNAKTA duran bir
#: ``<details`` YERİdir. İkisinin sayısının eşit olması bir TESADÜFTÜ ve
#: bu tesadüf gerçek bir envanter boşluğunu GİZLİYORDU:
#:   * ``stability_panel.js`` tek kaynak yerinden İKİ çalışma-anı katlısı
#:     üretir (``not-modelled`` + ``assumptions``) — envanterde 2 satır,
#:     kaynakta 1 yer;
#:   * ``sixdof_panel.js``in eşleme raporu katlısı envanterde HİÇ YOKTU.
#: İki sapma birbirini götürdüğü için sayı 12 = 12 çıkıyordu. D30
#: arayuz-panel a2 (``edf29b73``, P11B4-19 UQ künyesi) 13. kaynak yerini
#: (``uncertainty_panel.js``, ``data-uq-distributions``) ekleyince eşitlik
#: bozuldu ve bekçi kırmızıya döndü.
#:
#: Sayı BÜYÜTÜLMEDİ, ÖLÇÜYE ÇEVRİLDİ (ÖK-22): kapı artık sayıyı değil
#: KÜMEYİ karşılaştırır — dosya, o dosyadaki sıra ve niteliklerin ADLARI.
#: Nitelik DEĞERLERİ imzaya girmez (birçoğu dize birleştirmesiyle kurulur);
#: adlar girer, çünkü bir katlının kimliğini (``id`` / ``data-*`` kancası)
#: onlar taşır. Yeni bir katlı eklendiğinde bekçi ADIYLA güncelleme ister.
URUN_KATLI_ALANLARI = [
    ("analysis_dock.js", 1, ('data-src-ledger', 'style')),
    ("blowdown_panel.js", 1, ('id', 'style')),
    ("blowdown_panel.js", 2, ()),
    ("fea_panel.js", 1, ('id', 'style')),
    ("fea_panel.js", 2, ('id', 'style')),
    ("fea_panel.js", 3, ('id', 'style')),
    ("fea_panel.js", 4, ('id', 'style')),
    ("injector_panel.js", 1, ('data-inj-assumptions', 'style')),
    ("sixdof_panel.js", 1, ('style',)),
    ("thermal_fea_panel.js", 1, ('id', 'style')),
    ("correlation_panel.js", 1, ('style',)),
    # D31 arayuz-panel a1 (13875eef, P11B4-27): 31 KB rapor metni
    # katlanmış <details> içinde (correlation_panel.js:400). Varsayılan
    # KAPALI — ``open`` yok; ikinci iddia ayrıca ölçer. (ana model, 14 Eyl)
    ("correlation_panel.js", 2, ('style',)),
    ("stability_panel.js", 1, ('data-stab-fold', 'style')),
    # D30 arayuz-panel a2 (edf29b73, P11B4-19): UQ dağılım künyesi.
    # Varsayılan KAPALI (nitelikler arasında ``open`` yok — aşağıdaki
    # ikinci iddia bunu ayrıca ölçer).
    ("uncertainty_panel.js", 1, ('data-uq-distributions', 'style')),
    # ÖH D36 onemli2-kati (a1, 1e93ae89 — main'de birleşti): E-2 iki-faz
    # künyesi katlı (solid.html). Varsayılan KAPALI: nitelikler arasında
    # ``open`` yok (aşağıdaki ikinci iddia ayrıca ölçer). Envantere
    # onemli2-sivi a2 turunda eklendi: bekçi main birleşmesinden beri
    # kırmızıydı (kulvar dışı kök, kulvar-taban kıyasında yakalandı).
    ("solid.html", 1, ('data-hd-declaration', 'style')),
]


def test_c4_urun_katlilarinin_hepsi_hala_varsayilan_kapali():
    """C4 çapası: envanter bayatlamasın — ürün katlıları sayılır.

    Bu bekçi kusuru DEĞİL, ölçümün geçerliliğini korur: yeni bir katlı
    eklenir ya da biri ``open`` yapılırsa envanter güncellenmelidir.
    """
    kaynaklar = (sorted(STATIC_JS.glob('*.js'))
                 + sorted(PANELS_DIR.glob('*.js'))
                 + sorted(TEMPLATES.glob('*.html')))
    yorum = re.compile(r'^\s*(//|\*|/\*|#)')
    toplam, acik = 0, []
    olculen, sira = [], {}
    for yol in kaynaklar:
        ham = oku(yol)
        # ÖH D26 / arayuz a2 — SAYAÇ YORUMU DEĞİL KODU SAYAR.
        # ÖLÇÜLDÜ: aşağıdaki satır-öneki sezgisi (``^\s*(//|*|/*|#)``)
        # yalnız yorumun İLK satırını tanır. Bir ``/* … */`` bloğunun
        # ortasındaki, yıldızla başlamayan devam satırı KOD sayılıyordu;
        # ``thermal_fea_panel.js``de P11B3-15'i anlatan açıklama bloğu
        # ``<details id="fea_t_basis">`` dizesini içerdiği için bu bekçi
        # üründe 13 katlı sayıp KIRMIZI verdi — oysa ürün 12 katlı
        # taşıyordu, 13.'sü bir CÜMLEYDİ. (Bu, D26'da OH-D25-22 olarak
        # onarılan kusurla aynı sınıftır: metin araması sözdizimini
        # göremez.) Ölçüt GEVŞETİLMEDİ — envanter büyütülmedi, sayaç
        # daraltıldı: JS için bu dosyanın KENDİ kaçıcısı kullanılır
        # (``js_yorumsuz``, ofsetleri korur; ikinci bir sökücü
        # yazılmadı). HTML şablonlarında JS sökücüsü uygulanmaz — bir
        # ``href``teki ``//`` satırın kalanını silip GERÇEK bir
        # ``<details``i gizleyebilirdi; orada satır-öneki sezgisi kalır.
        if yol.suffix == '.js':
            ham = js_yorumsuz(ham)
        satirlar = ham.splitlines()
        for i, satir in enumerate(satirlar):
            if yorum.match(satir):
                continue
            for _ in re.finditer(r'<details', satir):
                toplam += 1
                kuyruk = ' '.join(satirlar[i:i + 3])
                bas = kuyruk.find('<details') + len('<details')
                son = kuyruk.find('>', bas)
                nitelik = kuyruk[bas:son] if son > 0 else kuyruk[bas:bas + 160]
                if ' open' in (' ' + nitelik.strip()):
                    acik.append(f'{yol.name}:{i + 1}')
                n = sira[yol.name] = sira.get(yol.name, 0) + 1
                olculen.append((yol.name, n,
                                tuple(sorted(set(re.findall(
                                    r'([A-Za-z-]+)=', nitelik))))))
    # ÖLÇÜLEN KÜME ⟷ ENVANTER (sayı değil küme; bkz. URUN_KATLI_ALANLARI).
    eksik = [k for k in URUN_KATLI_ALANLARI if k not in olculen]
    fazla = [k for k in olculen if k not in URUN_KATLI_ALANLARI]
    assert not eksik and not fazla, (
        f'ürün katlı alanları envanterle birebir değil — envanterde olup '
        f'üründe bulunmayan: {eksik}; üründe olup envantere yazılmayan: '
        f'{fazla}. URUN_KATLI_ALANLARI ADIYLA güncellenmeli (sayı '
        f'büyütmek DEĞİL): yeni katlının varsayılan kapalı olduğu '
        f'aşağıdaki iddiayla ayrıca ölçülür.')
    assert toplam == len(olculen) == len(URUN_KATLI_ALANLARI)
    assert not acik, (
        f'varsayılan AÇIK katlı(lar) belirdi: {acik} — görünürlük ölçümü '
        'yeniden yapılmalı')


# ===========================================================================
# C5 — güverte ısı haritası
# ===========================================================================

def test_c5_sivi_motor_isi_haritasi_blogunu_yayimliyor(sivi_rp1):
    """C5: sıvı yanıtta ``heat_transfer_analysis`` ve güverte kapısı var.

    ÖNCE (``olcum_c5_isi_haritasi_once.txt``): blok HİÇ yoktu, güverte ısı
    düğmesi gizleniyordu (``motor_viz3d.js``: ``if (gas.throat_heat_flux)``).
    """
    ht = sivi_rp1.get('heat_transfer_analysis')
    assert isinstance(ht, dict), 'sıvı yanıtta heat_transfer_analysis yok'
    assert ht.get('status') == 'modelled', ht.get('reason')
    gas = ht.get('gas_side_analysis') or {}
    q_bogaz = gas.get('throat_heat_flux')
    assert isinstance(q_bogaz, float) and q_bogaz > 0, (
        f'güverte kapısı (throat_heat_flux) açılmadı: {q_bogaz!r}')

    # SAHTE VERİ KAPISI: sayı ÜRETİLMEZ, soğutma çözümünden BİREBİR taşınır
    # (kW/m² -> W/m², tam 1000 kat).
    cooling = sivi_rp1.get('cooling_system') or {}
    assert abs(q_bogaz - float(cooling['peak_heat_flux']) * 1000.0) < 1e-6, (
        'boğaz akısı cooling_system.peak_heat_flux ile aynı değil — '
        'ikinci bir ısı hesabı doğmuş olabilir')
    assert abs(gas['chamber_heat_flux']
               - float(cooling['chamber_heat_flux']) * 1000.0) < 1e-6


def test_c5_varsayilan_cidar_sicakligi_olcum_gibi_basilmaz(sivi_rp1):
    """C5 fail-closed: 'assumed' cidar sıcaklığı ısı haritasına inmez.

    ``cooling_system.wall_temperature_source`` "assumed (cooling-type
    default)" iken 800/350 K yuvarlak TASARIM HEDEFİdir; onu haritaya
    ölçüm gibi koymak sahte veri olurdu.
    """
    cooling = sivi_rp1.get('cooling_system') or {}
    assert 'solved' not in str(cooling.get('wall_temperature_source', '')), (
        'ön koşul kırıldı: RP-1 koşumunda cidar sıcaklığı artık çözülüyor')
    wall = (sivi_rp1.get('heat_transfer_analysis') or {}).get(
        'wall_analysis') or {}
    assert wall.get('inner_temperature') is None, (
        'varsayılan cidar sıcaklığı ısı haritasına ölçüm gibi indi')
    assert wall.get('outer_temperature') is None
    assert wall.get('wall_temperature_solved') is False
    assert wall.get('wall_temperature_status') == 'not_solved'
    # Sayı silinmiyor, ADI DEĞİŞİYOR: hedef ayrı alanda beyanlı duruyor.
    assert wall.get('design_target_wall_temperature_hot_K') == 800.0
    assert 'wall_temperature_source' in str(
        wall.get('wall_temperature_withheld_reason'))


def test_c5_cozulmus_cidar_sicakligi_yayimlaniyor(sivi_metan):
    """C5 karşı ölçüm: cidar GERÇEKTEN çözüldüyse haritaya iner.

    Metan süperkritik 1B istasyon marşı cidarı çözer
    (``wall_temperature_source`` içinde 'solved'); kapı o zaman açılır.
    """
    cooling = sivi_metan.get('cooling_system') or {}
    assert 'solved' in str(cooling.get('wall_temperature_source', '')), (
        'ön koşul kırıldı: metan koşumunda marş cidarı çözmüyor')
    wall = (sivi_metan.get('heat_transfer_analysis') or {}).get(
        'wall_analysis') or {}
    assert wall.get('wall_temperature_solved') is True
    assert isinstance(wall.get('inner_temperature'), float), (
        'çözülmüş cidar sıcaklığı hâlâ gizleniyor — kapı tek yönlü kalmış')
    assert wall['inner_temperature'] > wall['outer_temperature'], (
        'sıcak cidar soğuk cidardan düşük — sıralama bozuk')


def test_c5_kati_motor_fail_closed_kalir(kati):
    """C5: katı ısı bloğu ARTIK YAYIMLANIYOR — kapı ölçümle açıldı.

    ÖH D16/kati (OH-Z5-03) — BEKÇİ ÇEVRİLDİ, GEVŞETİLMEDİ.

    Bu test eskiden ``kati.get('heat_transfer_analysis') is None`` şart
    koşuyordu ve gerekçesi "katı thermal_analysis viz'in gas_side/wall
    şemasına sahip değil, akısı da basitleştirilmiş bir yer tutucu" idi.
    İkisi de artık geçerli değil:

    * Akı yer tutucu DEĞİL: ``_calculate_heat_flux`` 2026-07-19 denetiminde
      (#1633) ``HeatTransferAnalyzer``ın doğrulanmış Bartz zincirine
      bağlandı; eski ``T_c*0.002`` yer tutucusu kalmadı.
    * Şema artık VAR: ``_build_heat_transfer_analysis`` güvertenin okuduğu
      alan adlarını (``gas_side_analysis.throat_heat_flux`` /
      ``chamber_heat_flux``) aynı Bartz çağrısından yayımlar; yeni fizik
      yazılmaz, yalnız kW/m² -> W/m² çevrilir.

    Testin kendi salıverme koşulu ("şemasının gerçekten
    ``gas_side_analysis.throat_heat_flux`` taşıdığı doğrulanmadan bu bekçi
    gevşetilmemeli") burada ÖLÇÜLEREK karşılanır: alan aranır, sonlu ve
    pozitif olması istenir. Ölçüm:
    ``docs/scofield/raw/OH/D16/kati/a1/{once,sonra}.json`` (OH-Z5-03).
    Fail-closed tarafı KORUNUR ve aşağıda ayrıca sınanır: cidar sıcaklığı
    çözülmediği için ``inner_temperature`` hâlâ yayımlanmaz.
    """
    ht = kati.get('heat_transfer_analysis')
    assert ht is not None, 'katı ısı bloğu yayımlanmıyor (OH-Z5-03 geriledi)'
    assert ht.get('status') == 'modelled', ht.get('reason')
    gas = ht.get('gas_side_analysis') or {}
    for alan in ('throat_heat_flux', 'chamber_heat_flux'):
        deger = gas.get(alan)
        assert isinstance(deger, float) and deger > 0 and deger == deger, (
            f'{alan} güvertenin okuyacağı biçimde yayımlanmıyor: {deger!r}')
    # Fail-closed yarısı: ÇÖZÜLMEMİŞ cidar sıcaklığı ölçüm gibi inmez.
    wall = ht.get('wall_analysis') or {}
    assert wall.get('inner_temperature') is None, (
        'Bartz referans cidarı (tasarım değeri) ısı haritasına ölçüm gibi '
        'indi')
    assert wall.get('wall_temperature_solved') is False
    assert wall.get('bartz_reference_wall_temperature_K') is not None, (
        'referans sayı silinmiş — ADI DEĞİŞMELİ, kaybolmamalı')
    src = oku(TEMPLATES / 'solid.html')
    assert 'r.heat_transfer_analysis !== undefined' in src, (
        'buildSolidVizData ısı bloğunu koşullu bile geçirmiyor')
    assert 'thermal_analysis' not in re.sub(
        r'//[^\n]*', '', src[src.index('function buildSolidVizData'):
                             src.index('function buildSolidVizData') + 4000]
    ).replace('heat_transfer_analysis', ''), (
        'katı thermal_analysis bloğu ısı haritası şemasına çevriliyor — '
        'yer tutucu akı haritaya dökülüyor olabilir')


def test_c5_sablonlar_isi_blogunu_gecir(client):
    """C5 şablon ayağı: iki güverte sözlüğü de bloğu koşullu taşır."""
    for ad in ('solid.html', 'liquid.html'):
        src = oku(TEMPLATES / ad)
        assert 'heat_transfer_analysis' in src, (
            f'{ad}: ısı bloğu viz sözlüğüne hiç taşınmıyor')
    liquid = oku(TEMPLATES / 'liquid.html')
    blok = liquid[liquid.index('function buildLiquidVizData'):]
    blok = blok[:blok.index('return data;')]
    assert 'data.heat_transfer_analysis = results.heat_transfer_analysis' in blok, (
        'buildLiquidVizData ısı bloğunu AYNEN taşımıyor')
    assert 'results.heat_transfer_analysis !== undefined' in blok, (
        'ısı bloğu koşulsuz konuyor — yokken undefined yazılırsa sahne '
        'fail-closed kapısını kaybeder')


def test_c5_guverte_efsanesi_cidar_kaynagini_beyan_eder():
    """C5 ekran ayağı: sayı yoksa efsane kaynağı yazar, boş kalmaz."""
    src = js_yorumsuz(oku(STATIC_JS / 'motor_viz_deck.js'))
    assert 'wallTempNote' in src, (
        'efsane cidar sıcaklığı satırı kaynak beyanını hiç basmıyor')
    assert 'wall_temperature_status' in src and 'wall_temperature_source' in src


def test_c5_hibrit_isi_zinciri_bit_ayni(hibrit_cidarli):
    """ÇAPA: dokunulmayan hibrit yolu BİT-AYNI kalmalı.

    Z5-C yalnız sıvı motorda yeni blok yayımlıyor; hibritin ısı zinciri
    değişmemeli (aynı girdi, aynı sayı).
    """
    gas = ((hibrit_cidarli.get('heat_transfer_analysis') or {})
           .get('gas_side_analysis') or {})
    # v3.0.0 (15 Eki) — referans platformda (darwin/arm64) BİT-AYNI; CI
    # linux/x86_64'te AYNI kod 8,6e-10 bağıl sapma verdi (koşum
    # 38770162288). Orada 1e-8 bağıl (çapa yenilemeleri 1e-5 – 4e-2).
    akis = gas.get('throat_heat_flux')
    assert akis == pytest.approx(HIBRIT_BOGAZ_AKISI_W_M2,
                                 rel=capa_rel(0.0, 1e-8), abs=0.0), (
        'hibrit boğaz ısı akısı değişti: '
        f'{gas.get("throat_heat_flux")!r} != {HIBRIT_BOGAZ_AKISI_W_M2!r}')


# ===========================================================================
# Sözdizimi kapısı
# ===========================================================================

@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
@pytest.mark.parametrize('yol', DOKUNULAN_JS, ids=lambda p: p.name)
def test_dokunulan_js_sozdizimsel_gecerli(yol):
    sonuc = subprocess.run([NODE, '--check', str(yol)],
                           capture_output=True, text=True, timeout=60)
    assert sonuc.returncode == 0, f'{yol.name} sözdizimi hatalı:\n{sonuc.stderr}'
