"""Faz 6 / F5-app — tarayıcı denetiminden çıkan beş kalemin bekçileri.

Her testin başında DÜZELTMEDEN ÖNCE ölçülen sayı yazılıdır; hiçbiri
"böyle olmalı" varsayımı değildir. Düzeltme geri alınırsa buradaki testler
kırılmak zorundadır.

Kapsanan kalemler
-----------------
T14  ``/api/get-propellant-properties`` sıvı itici gazların GAZ FAZI
     yoğunluğunu döndürüyordu. ÖLÇÜLDÜ (2026-08-03, ``app.test_client``):

         lox : 1,3088 kg/m³   (doğrusu 1141,16 →  872x)
         n2o : 1,8089 kg/m³   (doğrusu  785,10 →  434x)
         lh2 : 0,0823 kg/m³   (doğrusu   70,95 →  862x)
         lox viskozite : 2,055e-5 Pa·s (doğrusu 1,947e-4 → 9,5x)

     Bu sayı /liquid Panel 1'de "Oxidizer Density" alanına YAZILIYOR ve
     yanına yeşil "Real-time Data" rozeti konuyordu; çözücünün kendisi ise
     1141,7 kg/m³ kullanıyordu. Kök neden: ``get_comprehensive_properties``
     imzasındaki ``temperature=298.15`` varsayılanı, CoolProp sarmalayıcının
     ``DEFAULT_STORAGE_STATE`` dalını (kriyojende doymuş sıvı) baypas
     ediyordu.

T30  ``POST /api/flight-vehicle {"source":"project"}`` normalize edilmiş
     araç yerine HAM motor sonucunu dönüyordu. ÖLÇÜLDÜ: 50 anahtar,
     ``thrust=None``, ``motor_type=None``, ``source=None``,
     ``engine_inert_mass=None``. launch_site.html ``num_(veh.thrust) || 6500``
     yazdığı için kullanıcı kendi projesini seçtiğinde çözücüye ÖRNEK aracın
     6500 N'u gidiyordu; itki eğrisi ise projeden geliyordu (karışık köken).

T71  TR sözlüğünde ``web thickness`` -> "Ağ Kalınlığı" (ağ = network).
     Katı yakıtta "web" YANMA ETİdir. Depoda doğru karşılık zaten vardı
     (i18n_common.js ``app.rep.webThickness`` -> "Et Kalınlığı").

T72  "User Guide" düğmesi yalnız ``.nav-links`` şeridine enjekte ediliyordu.
     ÖLÇÜLDÜ — /formulas: var; / : YOK; /launch-site: YOK. Kılavuzun kendisi
     sağlamdı (``POST /api/user-guide/open`` -> ``{"opened": true}``), yani
     iki sayfada erişilemeyen çalışan bir özellik vardı.

T75  Ana sayfa "Recent Projects" şeridinde ``.aux-link { text-transform:
     uppercase }`` SI simgelerini büyütüyordu. ÖLÇÜLDÜ — DOM metni
     "Isp 207.1 s · It 13428 N·s" doğruyken ekranda
     "ISP 207.1 S · IT 13428 N·S" görünüyordu: büyük 'S' SIEMENS'tir.

Kapsam DIŞI (ikinci tura kaldı, dosya sahipliği): T74 — /launch-site TR
kipinde araç rozeti, araç notu, karo göstergesi ve hazır saha listesi.
Dördünün de kökü ``hrma/templates/launch_site.html`` içindedir (bkz. rapor).
"""

import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

from hrma.app import app

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
TEMPLATES = REPO_ROOT / 'hrma' / 'templates'

NODE = shutil.which('node')


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client


def read(path):
    return path.read_text(encoding='utf-8')


# ===========================================================================
# T14 — depolama durumu: sıvı itici gaz gaz fazı yoğunluğuyla dönmemeli
# ===========================================================================

#: Çözücünün LOX için kullandığı referans (liquid_rocket_engine.py:1848,
#: "kg/m³ at NBP"). Uç ile çözücü 1 %'den fazla ayrışırsa form alanı ile
#: hesap yine birbirini tutmuyor demektir.
SOLVER_LOX_DENSITY = 1141.7

#: (ad, tip, alt sınır, üst sınır) — depolama durumundaki SIVI yoğunluk bandı.
#: Bantlar literatür değerinin etrafında ±%5'ten geniş tutuldu; amaç kesin
#: sayıyı değil FAZI kilitlemek (gaz fazı değerleri bu bantların binde
#: birinde kalır).
LIQUID_DENSITY_BANDS = [
    ('lox', 'oxidizer', 1100.0, 1200.0),      # 1141,16 (90,19 K doymuş sıvı)
    ('n2o', 'oxidizer', 700.0, 850.0),        # 785,10  (293,15 K kendinden basınçlı)
    ('lh2', 'oxidizer', 65.0, 75.0),          # 70,95   (20,28 K)
    ('methane', 'liquid_fuel', 400.0, 450.0),  # 422,35  (111,67 K)
]


def _props(client, name, ptype):
    resp = client.post('/api/get-propellant-properties',
                       json={'propellant_type': ptype, 'propellant_name': name})
    assert resp.status_code == 200, (name, ptype, resp.status_code)
    body = resp.get_json()
    assert body['status'] == 'success', body
    return body


@pytest.mark.parametrize('name,ptype,lo,hi', LIQUID_DENSITY_BANDS)
def test_t14_itici_gaz_yogunlugu_sivi_fazda_doner(client, name, ptype, lo, hi):
    """ÖNCE: lox 1,3088 / n2o 1,8089 / lh2 0,0823 kg/m³ (hepsi GAZ).

    SONRA: sırasıyla 1141,16 / 785,10 / 70,95 kg/m³ (doymuş SIVI).
    """
    props = _props(client, name, ptype)['properties']
    rho = props.get('density')
    assert isinstance(rho, (int, float)), f'{name}: yoğunluk sayı değil: {rho!r}'
    assert lo <= rho <= hi, (
        f'{name}: yoğunluk {rho} kg/m³, beklenen sıvı bandı [{lo}, {hi}]. '
        'Gaz fazı değeri sızmış olabilir (298 K / 1 atm sorgusu).')


def test_t14_lox_ucu_ile_cozucu_ayni_yogunlugu_kullanir(client):
    """ÖNCE: form alanı 1,3088 ↔ çözücü 1141,7 kg/m³ → 872x ayrışma.

    SONRA: uç 1141,16 kg/m³ döner; çözücü değerinden sapma < %1.
    Ayrıca değer, çözücünün kabul bandının (20-2500 kg/m³) İÇİNDEDİR —
    eskiden alan "outside the accepted range ... and was ignored" uyarısıyla
    sessizce atılıyordu.
    """
    rho = _props(client, 'lox', 'oxidizer')['properties']['density']
    sapma = abs(rho - SOLVER_LOX_DENSITY) / SOLVER_LOX_DENSITY
    assert sapma < 0.01, (
        f'uç {rho} kg/m³ ile çözücü {SOLVER_LOX_DENSITY} kg/m³ arasında '
        f'%{sapma * 100:.2f} fark var')
    assert 20.0 < rho < 2500.0, 'çözücünün kabul bandının dışında'


def test_t14_lox_viskozitesi_de_sivi_fazda(client):
    """ÖNCE: 2,055e-5 Pa·s (25 °C gaz oksijen). SONRA: 1,947e-4 Pa·s (90,2 K LOX).

    Yoğunluğu düzeltip viskoziteyi gaz fazında bırakmak, tek bir akışkanı iki
    ayrı durumda tarif eden melez bir kart üretirdi.
    """
    mu = _props(client, 'lox', 'oxidizer')['properties']['viscosity']
    assert 1.0e-4 <= mu <= 3.0e-4, f'LOX viskozitesi {mu} Pa·s — gaz fazı değeri'


def test_t14_yerel_tablonun_kJ_birimli_ozgul_isisi_bozulmaz(client):
    """Birim güvenliği: düzeltme sessiz bir 1000x hata ÜRETMEMELİ.

    Yerel tablo ``specific_heat``'i kJ/(kg·K) tutuyor (LH2 14,3), CoolProp ise
    J/(kg·K) veriyor (20,28 K'de 9722,9). ``oxidizer`` kolunda değer yerel
    tablodan gelir ve DOKUNULMAMALIDIR; ``liquid_fuel`` kolunda CoolProp'tan
    gelir ve ORTAM değeri (14306,3 J/kg·K) yerine DEPOLAMA değeri
    (9722,9 J/kg·K) olmalıdır.
    """
    ox = _props(client, 'lh2', 'oxidizer')['properties']
    assert ox['specific_heat'] == pytest.approx(14.3), (
        'yerel tablodaki kJ/(kg·K) değeri J/(kg·K) ile ezilmiş — 1000x birim hatası')

    fuel = _props(client, 'lh2', 'liquid_fuel')['properties']
    assert fuel['specific_heat'] == pytest.approx(9722.9, rel=1e-3), (
        'liquid_fuel kolunda özgül ısı hâlâ ortam (298 K) değerinde')
    assert fuel['specific_heat'] != pytest.approx(14306.3, rel=1e-3)


def test_t14_depolama_durumu_kunyesi_yayinlanir(client):
    """Değer düzeldi diye yetmez: HANGİ durumda olduğu da söylenmeli."""
    props = _props(client, 'lox', 'oxidizer')['properties']
    state = props.get('storage_state')
    assert isinstance(state, dict) and state, 'storage_state künyesi yok'
    assert state.get('state_temperature_K') == pytest.approx(90.19, abs=0.05)
    assert 'liquid' in str(state.get('phase', '')).lower()


def test_t14_coolprop_tanimadigi_yakitin_kunyesini_uydurmaz(client):
    """ÖNCE: RP-1 ve HTPB için CoolProp TEK sayı bile üretmediği hâlde künye
    'CoolProp (NIST REFPROP-based)' diyordu (open_source_propellant_api.py:378
    kaynak alanını koşulsuz yazıyor).

    SONRA: künye gerçek kaynağı söyler; yoğunluk yerel tablodan geldiği gibi
    kalır (uydurma düzeltme yapılmaz).
    """
    for name, ptype, rho in (('rp1', 'liquid_fuel', 800), ('htpb', 'hybrid_fuel', 920)):
        body = _props(client, name, ptype)
        assert not str(body['source']).startswith('CoolProp'), (
            f'{name}: CoolProp katkısı yokken künye CoolProp diyor')
        assert body['properties']['density'] == pytest.approx(rho), (
            f'{name}: tanınmayan akışkanın yoğunluğuna dokunulmuş')
        assert 'storage_state' not in body['properties']


# ===========================================================================
# T30 — /api/flight-vehicle source='project' normalize edilmiş şema dönmeli
# ===========================================================================

#: flight_vehicle.py modül başındaki şema (docstring). Uç bu kümenin DIŞINA
#: çıkarsa (ham motor sonucu) tüketici alanları boş kalır.
VEHICLE_SCHEMA_KEYS = {
    'motor_type', 'motor_name', 'thrust_curve', 'thrust', 'burn_time',
    'propellant_mass', 'engine_inert_mass', 'engine_inert_mass_is_estimate',
    'engine_inert_mass_note', 'engine_od_m', 'engine_length_m', 'source',
}
#: Uç bunların üstüne yalnız şu iki bilgiyi ekleyebilir.
VEHICLE_EXTRA_KEYS = {'load_warnings', 'airframe'}

#: Ham katı motor sonucunda bulunan, araç şemasında İŞİ OLMAYAN anahtarlar.
#: ÖLÇÜLDÜ: düzeltme öncesi yanıt 50 anahtarlıydı ve bunları içeriyordu.
RAW_ENGINE_KEYS = ('advanced_performance', 'altitude_performance',
                   'grain_design', 'cad_design', 'cost_analysis')

SOLID_PROJECT_FIELDS = {
    'grain_type': 'bates', 'propellant_type': 'apcp',
    'chamber_diameter': 100, 'grain_length': 500,
    'core_diameter': 30, 'chamber_pressure': 40,
    'burn_rate_a': 0.005, 'burn_rate_n': 0.35,
}


@pytest.fixture
def kayitli_proje(tmp_path, monkeypatch):
    """İzole proje dizinine gerçek bir katı motor projesi yazar."""
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(tmp_path / 'projects'))
    from hrma.utils import projects
    name = 'Faz6-F5-Kati'
    projects.save_project(name, {
        'format': 'hrma-project',
        'format_version': 1,
        'motor_type': 'solid',
        'inputs': {'fields': dict(SOLID_PROJECT_FIELDS)},
        'results_summary': {'isp_s': 207.1},
    })
    return name


def test_t30_proje_kolu_normalize_sema_doner(client, kayitli_proje):
    """ÖNCE: 50 anahtarlı HAM motor sonucu; thrust/motor_type/source = None.

    SONRA: 12 şema anahtarı (+ load_warnings), thrust sonlu ve pozitif.
    """
    resp = client.post('/api/flight-vehicle',
                       json={'source': 'project', 'name': kayitli_proje})
    assert resp.status_code == 200, resp.data[:400]
    body = resp.get_json()
    assert body['status'] == 'success', body
    veh = body['vehicle']

    eksik = VEHICLE_SCHEMA_KEYS - set(veh)
    assert not eksik, f'şema anahtarları eksik: {sorted(eksik)}'
    fazla = set(veh) - VEHICLE_SCHEMA_KEYS - VEHICLE_EXTRA_KEYS
    assert not fazla, f'şema dışı (ham motor) anahtarlar sızmış: {sorted(fazla)[:10]}'
    for key in RAW_ENGINE_KEYS:
        assert key not in veh, f'ham motor anahtarı {key!r} yanıtta'


def test_t30_proje_araci_kendi_itkisini_tasir(client, kayitli_proje):
    """ÖNCE: thrust=None -> şablon ``num_(veh.thrust) || 6500`` ile ÖRNEK
    aracın 6500 N'unu çözücüye gönderiyordu.

    SONRA: thrust projeden hesaplanan ortalama itki (bu projede ~12602 N) ve
    örnek aracın 6500 N'undan farklı.
    """
    veh = client.post('/api/flight-vehicle',
                      json={'source': 'project', 'name': kayitli_proje}
                      ).get_json()['vehicle']
    thrust = veh['thrust']
    assert isinstance(thrust, (int, float)) and thrust > 0, (
        f'thrust={thrust!r} — şablonun 6500 N yedeğine düşer')
    assert thrust != 6500, 'örnek aracın yedek itkisiyle aynı'
    # Atıl kütle ve boyutlar da dolmalı: çift-sayım tuzağı için çözücü
    # airframe_dry_mass + engine_inert_mass topluyor.
    assert veh['engine_inert_mass'] and veh['engine_inert_mass'] > 0
    assert veh['engine_od_m'] and veh['engine_od_m'] > 0


def test_t30_proje_araci_kokenini_ve_adini_beyan_eder(client, kayitli_proje):
    """ÖNCE: motor_name=None, source=None -> rozet "(example, not calculated)"
    diyor, hemen altındaki not "Recomputed from the saved project." diyordu;
    iki etiket birbirini yalanlıyordu.

    SONRA: source='project', motor_name = projenin adı.
    """
    veh = client.post('/api/flight-vehicle',
                      json={'source': 'project', 'name': kayitli_proje}
                      ).get_json()['vehicle']
    assert veh['source'] == 'project'
    assert veh['motor_type'] == 'solid'
    assert veh['motor_name'] == kayitli_proje


def test_t30_itki_egrisi_ve_itki_ayni_kaynaktan_gelir(client, kayitli_proje):
    """Karışık köken denetimi: eğri projeden gelirken sabit itkinin örnek
    araçtan gelmesi yasak. Ortalama itki, eğrinin tepe değerinin altında ve
    eğri ortalamasıyla aynı büyüklük mertebesinde olmalı.
    """
    veh = client.post('/api/flight-vehicle',
                      json={'source': 'project', 'name': kayitli_proje}
                      ).get_json()['vehicle']
    curve = veh['thrust_curve']
    assert curve and len(curve['time']) > 3, 'itki eğrisi taşınmamış'
    tepe = max(curve['thrust'])
    assert 0 < veh['thrust'] <= tepe, (
        f"ortalama itki {veh['thrust']} eğrinin tepesi {tepe} ile tutarsız")


# ===========================================================================
# T71 — "web thickness" TR çevirisi
# ===========================================================================

WEB_KEYS = ('solid.js.web_thickness', 'solid.msg.web_thickness_mm',
            'solid.ui.web_thickness')


def _dict_bloklari(text):
    """i18n_*.js dosyasından ``en:`` ve ``tr:`` blok metinlerini ayıklar."""
    en_start = text.index('\n        en: {')
    tr_start = text.index('\n        tr: {')
    return text[en_start:tr_start], text[tr_start:]


def _deger(blok, key):
    m = re.search(r"'" + re.escape(key) + r"':\s*'((?:[^'\\]|\\.)*)'", blok)
    return m.group(1) if m else None


def test_t71_web_kalinligi_ag_degil_et():
    """ÖNCE: 'Ağ Kalınlığı' (ağ = network). SONRA: 'Et Kalınlığı'.

    Katı yakıtta "web" yanma etidir; "ağ" yanlış anlam taşıyordu.
    """
    en_blok, tr_blok = _dict_bloklari(read(STATIC_JS / 'i18n_pages.js'))
    for key in WEB_KEYS:
        en = _deger(en_blok, key)
        tr = _deger(tr_blok, key)
        assert en is not None, f'{key}: EN karşılığı yok'
        assert tr is not None, f'{key}: TR karşılığı yok'
        assert 'Ağ' not in tr and 'ağ' not in tr, (
            f'{key}: TR karşılığı hâlâ "ağ" (network) diyor: {tr!r}')
        assert 'Et' in tr or 'et ' in tr, f'{key}: beklenen "et" terimi yok: {tr!r}'


def test_t71_web_terimi_iki_sozlukte_ayni():
    """Terim tutarlılığı: i18n_common.js zaten "Et Kalınlığı" diyordu."""
    _, common_tr = _dict_bloklari(read(STATIC_JS / 'i18n_common.js'))
    ortak = _deger(common_tr, 'app.rep.webThickness')
    assert ortak == 'Et Kalınlığı', f'referans terim değişmiş: {ortak!r}'

    _, pages_tr = _dict_bloklari(read(STATIC_JS / 'i18n_pages.js'))
    assert _deger(pages_tr, 'solid.ui.web_thickness') == ortak


def test_t71_cidar_kalinligi_ile_karismaz():
    """"wall thickness" ayrı bir kavram (Cidar Kalınlığı); ikisi eşitlenmemeli."""
    _, tr_blok = _dict_bloklari(read(STATIC_JS / 'i18n_pages.js'))
    web = _deger(tr_blok, 'solid.ui.web_thickness')
    wall = _deger(tr_blok, 'solid.js.wall_thickness')
    assert web and wall and web.rstrip(':') != wall.rstrip(':')


# ===========================================================================
# T72 — "User Guide" düğmesi üç kabuğun üçünde de belirmeli
# ===========================================================================

USER_GUIDE_HARNESS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const staticDir = process.argv[2];
const senaryo = process.argv[3];   // nav | aux | topbar | yok

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.nodeType = 1;
    this.childNodes = [];
    this.className = '';
    this.id = '';
    this.href = '';
    this.style = {};
    this._attrs = {};
    this._listeners = {};
}
Object.defineProperty(El.prototype, 'textContent', {
    get: function () {
        return this.childNodes.map(function (n) {
            return n.nodeType === 3 ? n.nodeValue : n.textContent;
        }).join('');
    },
    set: function (v) {
        this.childNodes = [{ nodeType: 3, nodeValue: String(v) }];
    }
});
El.prototype.appendChild = function (c) { this.childNodes.push(c); return c; };
El.prototype.insertBefore = function (c, ref) {
    const i = this.childNodes.indexOf(ref);
    if (i < 0) this.childNodes.push(c); else this.childNodes.splice(i, 0, c);
    return c;
};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.addEventListener = function (t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn);
};
El.prototype.querySelector = function (sel) {
    for (const c of this.childNodes) {
        if (c.nodeType !== 1) continue;
        if (sel === '[data-shell-aux]' && c.getAttribute('data-shell-aux')) return c;
        if (sel.charAt(0) === '.' && c.className === sel.slice(1)) return c;
    }
    return null;
};

// Üç kabuk: /formulas (.nav-links), / (.aux-links), /launch-site (#ls-topbar)
const host = new El('div');
const HOST_SEL = { nav: '.nav-links', aux: '.aux-links', topbar: '#ls-topbar' }[senaryo];
if (senaryo === 'topbar') {
    const geri = new El('a');           // "Back to app" — en sağda kalmalı
    geri.className = 'ls-link';
    geri.textContent = 'Back to app';
    host.appendChild(geri);
}

const documentStub = {
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    getElementById: function () { return null; },
    querySelector: function (sel) { return (HOST_SEL && sel === HOST_SEL) ? host : null; },
    querySelectorAll: function () { return []; },
    addEventListener: function () {}
};

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, JSON: JSON, Math: Math, String: String,
    Promise: Promise, Error: Error,
    fetch: function () { return Promise.resolve({ json: function () { return Promise.resolve({}); } }); },
    document: documentStub,
    localStorage: { getItem: function () { return null; } }
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(staticDir, 'user_guide.js'), 'utf8'),
                sandbox, { filename: 'user_guide.js' });

const kids = host.childNodes.filter(function (c) { return c.nodeType === 1; });
const link = kids.filter(function (c) { return c.id === 'userGuideLink'; })[0] || null;
console.log(JSON.stringify({
    baglantiVar: !!link,
    metin: link ? link.textContent : null,
    i18nAnahtari: link ? link.getAttribute('data-i18n') : null,
    sinif: link ? link.className : null,
    tiklamaDinleyicisi: link ? (link._listeners.click || []).length : 0,
    sira: kids.map(function (c) { return c.id || ('.' + c.className); }),
    apiVar: typeof sandbox.window.hrmaOpenUserGuide === 'function'
}));
"""


def _user_guide_harness(tmp_path, senaryo):
    h = tmp_path / 'faz6_user_guide_harness.js'
    h.write_text(USER_GUIDE_HARNESS, encoding='utf-8')
    res = subprocess.run([NODE, str(h), str(STATIC_JS), senaryo],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, 'node koşumu hata verdi:\n' + res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
@pytest.mark.parametrize('senaryo', ['nav', 'aux', 'topbar'])
def test_t72_kilavuz_baglantisi_uc_kabukta_da_belirir(tmp_path, senaryo):
    """ÖNCE (ölçüldü): /formulas ✔, / ✘, /launch-site ✘ — çünkü enjeksiyon
    yalnız ``.nav-links`` arıyordu.

    SONRA: üç kabukta da bağlantı var, metni ve i18n anahtarı yerinde.
    """
    d = _user_guide_harness(tmp_path, senaryo)
    assert d['baglantiVar'], (
        f'{senaryo} kabuğunda userGuideLink oluşmadı — enjeksiyon çapası eksik')
    assert d['metin'] == 'User Guide'
    assert d['i18nAnahtari'] == 'link.userGuide'
    assert d['tiklamaDinleyicisi'] == 1, 'tıklama dinleyicisi bağlanmamış'


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_t72_launch_site_seridinde_geri_baglantisi_en_sagda_kalir(tmp_path):
    """Yerleşim sözleşmesi: /launch-site üst şeridinde "Uygulamaya dön" en
    sonda durur; kılavuz bağlantısı ondan ÖNCE eklenir.
    """
    d = _user_guide_harness(tmp_path, 'topbar')
    assert d['sira'] == ['userGuideLink', '.ls-link'], d['sira']
    assert d['sinif'] == 'ls-link', 'şeridin kendi bağlantı sınıfı verilmemiş'


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_t72_capasiz_sayfada_sessizce_vazgecer(tmp_path):
    """Bilinen şeritlerden hiçbiri yoksa hata fırlatılmaz; yerel pencere
    menüsünün kullandığı ``window.hrmaOpenUserGuide`` yine tanımlıdır.
    """
    d = _user_guide_harness(tmp_path, 'yok')
    assert d['baglantiVar'] is False
    assert d['apiVar'] is True


def test_t72_uc_kabugun_capasi_da_sablonlarda_duruyor():
    """Bekçinin varsayımı: seçiciler gerçekten bu üç şablonda var.

    Şablon yeniden adlandırılırsa (ör. .aux-links -> .shell-links) bu test
    kırılır ve user_guide.js'in çapa tablosu güncellenir.
    """
    assert '.nav-links' in read(TEMPLATES / 'formulas.html')
    assert 'class="aux-links"' in read(TEMPLATES / 'index.html')
    assert 'id="ls-topbar"' in read(TEMPLATES / 'launch_site.html')
    js = read(STATIC_JS / 'user_guide.js')
    for sel in ("'.nav-links'", "'.aux-links'", "'#ls-topbar'"):
        assert sel in js, f'user_guide.js {sel} çapasını tanımıyor'


# ===========================================================================
# T75 — Recent Projects şeridinde SI simgeleri büyütülmemeli
# ===========================================================================

PROJECT_BAR_HARNESS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const staticDir = process.argv[2];

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.nodeType = 1;
    this.childNodes = [];
    this.className = '';
    this.id = '';
    this.href = '';
    this.style = {};
    this._attrs = {};
    this._listeners = {};
}
Object.defineProperty(El.prototype, 'textContent', {
    get: function () {
        return this.childNodes.map(function (n) {
            return n.nodeType === 3 ? n.nodeValue : n.textContent;
        }).join('');
    },
    set: function (v) {
        this.childNodes = [{ nodeType: 3, nodeValue: String(v) }];
    }
});
El.prototype.appendChild = function (c) { this.childNodes.push(c); return c; };
El.prototype.insertBefore = function (c, ref) {
    const i = this.childNodes.indexOf(ref);
    if (i < 0) this.childNodes.push(c); else this.childNodes.splice(i, 0, c);
    return c;
};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.addEventListener = function () {};
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };

const container = new El('div');
container.className = 'container';

const documentStub = {
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    getElementById: function () { return null; },
    querySelector: function (sel) { return sel === '.container' ? container : null; },
    querySelectorAll: function () { return []; },
    addEventListener: function () {}
};

// ÖLÇÜLEN gerçek proje kaydı (GET /api/projects, 2026-08-03)
const PROJECTS = { count: 1, projects: [{
    name: 'UI-Denetim-Test', motor_type: 'solid', corrupt: false,
    results_summary: {
        peak_thrust_N: 8262.173070535855,
        isp_s: 207.12175524404446,
        total_impulse_Ns: 13428.24943542937
    }
}] };

function fakeFetch(url) {
    return Promise.resolve({
        ok: true, status: 200,
        json: function () { return Promise.resolve(PROJECTS); }
    });
}

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, Promise: Promise, Error: Error,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    encodeURIComponent: encodeURIComponent,
    URLSearchParams: URLSearchParams,
    location: { pathname: '/', search: '' },
    document: documentStub,
    fetch: fakeFetch
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(staticDir, 'project_bar.js'), 'utf8'),
                sandbox, { filename: 'project_bar.js' });

setTimeout(function () {
    let link = null;
    (function ara(node) {
        for (const c of node.childNodes) {
            if (c.nodeType !== 1) continue;
            if (c.className === 'aux-link' && !link) link = c;
            ara(c);
        }
    })(container);
    if (!link) { console.log(JSON.stringify({ error: 'şerit bağlantısı oluşmadı' })); return; }
    const dogrudanMetin = link.childNodes
        .filter(function (n) { return n.nodeType === 3; })
        .map(function (n) { return n.nodeValue; }).join('');
    const korumali = link.childNodes.filter(function (n) {
        return n.nodeType === 1 && n.style && n.style.textTransform === 'none';
    });
    console.log(JSON.stringify({
        tamMetin: link.textContent,
        dogrudanMetin: dogrudanMetin,
        korumaliSayisi: korumali.length,
        korumaliMetin: korumali.length ? korumali[0].textContent : null
    }));
}, 80);
"""


def _project_bar_harness(tmp_path):
    h = tmp_path / 'faz6_project_bar_harness.js'
    h.write_text(PROJECT_BAR_HARNESS, encoding='utf-8')
    res = subprocess.run([NODE, str(h), str(STATIC_JS)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, 'node koşumu hata verdi:\n' + res.stderr
    out = res.stdout.strip().splitlines()
    assert out, 'koşum çıktı üretmedi:\n' + res.stdout + res.stderr
    data = json.loads(out[-1])
    assert 'error' not in data, data['error']
    return data


#: index.html'in şeridi büyük harfe çeviren kuralı. Kural KALKARSA tehlike de
#: kalkar; bekçi o zaman kendini geçersiz saymalı (yanlış şeyi kilitlememek
#: için koşullu yazıldı).
AUX_LINK_UPPERCASE = re.compile(
    r'\.aux-link\s*\{[^}]*text-transform:\s*uppercase', re.S)


def test_t75_serit_kuralinin_hala_buyuk_harfe_cevirdigi_dogrulanir():
    """Bekçinin ön koşulu: tehlike hâlâ mevcut mu?"""
    assert AUX_LINK_UPPERCASE.search(read(TEMPLATES / 'index.html')), (
        '.aux-link artık büyük harfe çevirmiyor — T75 bekçisi güncellenmeli')


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_t75_si_simgeleri_buyuk_harf_donusumunden_muaf(tmp_path):
    """ÖNCE (ölçüldü): tüm özet, büyük harfe çeviren ``.aux-link``in DOĞRUDAN
    metin düğümüydü; ekranda "ISP 207.1 S · IT 13428 N·S" görünüyordu.
    SI'da 'S' siemens, 's' saniyedir.

    SONRA: özet, ``text-transform: none`` taşıyan kendi kabında; ekranda
    "Isp 207.1 s · It 13428 N·s".
    """
    if not AUX_LINK_UPPERCASE.search(read(TEMPLATES / 'index.html')):
        pytest.skip('.aux-link artık büyük harfe çevirmiyor')
    d = _project_bar_harness(tmp_path)

    assert 'Isp 207.1 s' in d['tamMetin'], d['tamMetin']
    assert 'It 13428 N·s' in d['tamMetin'], d['tamMetin']
    assert d['korumaliSayisi'] == 1, (
        'özet, büyük harf dönüşümünü kapatan bir kapta değil — '
        f"doğrudan metin: {d['dogrudanMetin']!r}")
    for parca in ('Isp', ' s', 'N·s', 'Fpk'):
        assert parca in d['korumaliMetin'], (parca, d['korumaliMetin'])
    for parca in ('Isp', 'N·s'):
        assert parca not in d['dogrudanMetin'], (
            f'{parca!r} hâlâ büyük harfe çevrilen doğrudan metinde')


@pytest.mark.skipif(NODE is None, reason='node kurulu değil')
def test_t75_proje_adi_ve_tip_rozeti_seridin_duzeninde_kalir(tmp_path):
    """Düzeltme her şeyi kapatmamalı: proje adı ve [SOLID] rozeti şeridin
    görsel düzenine (büyük harf) uymayı sürdürür.
    """
    d = _project_bar_harness(tmp_path)
    assert d['dogrudanMetin'] == 'UI-Denetim-Test [SOLID]', d['dogrudanMetin']
