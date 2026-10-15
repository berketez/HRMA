# -*- coding: utf-8 -*-
"""ÖH Dalga-15 / kulvar ui-paneller, aşama 1 — bekçiler.

Kapsanan defter kalemleri:

* **P11B5-01** [kritik] ``protection_panel.js`` ucun ``model_valid:false`` +
  ``validity_note`` hükmünü HİÇ okumuyordu. ÖLÇÜLDÜ (31 Ağustos 2026,
  ``app.test_client`` + node içinde GERÇEK render;
  ``docs/scofield/raw/OH/D15/ui-paneller/a1/olc_b5_01.py``): zarf dışındaki
  ÜÇ koşumun ÜÇÜNDE de ekranda beyanın tek bir izi yoktu; kullanıcı
  gerileme ve cidar sıcaklığı sayılarını, her koşuda basılan (yani sıfır
  bilgi taşıyan) ``SIMPLIFIED MODEL`` rozetinin altında tasarım sayısı
  olarak okuyordu.
* **P11B2-05** [yüksek] ``app.js`` dil değişiminde motor uyarılarını
  düşürüyordu (``displayWarnings`` yalnız enjektör + doğrulama listesiyle
  çağrılıyordu); ilk çizimde 7 satır olan uyarı paneli dil düğmesine bir
  dokunuşta 6 satıra iniyordu ve kaybolan kayıt HTPB regresyon katsayısı
  yanlılığı uyarısıydı.
* **P11B2-07** [yüksek] ``app.js`` uç 4xx/5xx dönünce ekranda BAYAT sonuç
  bırakıyordu: ``currentResults`` eski değerinde, sonuç paneli açık, dışa
  aktarım düğmeleri etkin.
* **P11B2-02/-03/-04** [kritik/yüksek] ``askAI()`` yükü çözücünün
  uyarılarını yutuyor, lüle açılarını/Cd/L-D'yi ve giriş basıncını
  yanıttaki gerçek değerler dururken sabitlerden dolduruyordu.
* **P11B1-04** [yüksek] 3B sahne enjektör plakasını ``injector_design``
  yedeğinden çiziyordu; panelin gösterdiği çözücü sonucu (``data.injector``)
  sahneye HİÇ verilmiyordu.

Yöntem: ürün dosyalarının kendi kaynağı + node içinde GERÇEK render.
İddialar ürün sabitlerinden TÜRETİLMEZ (ÖK / H2 kuralı): beklenen değerler
ucun O KOŞUMDAKİ yanıtından okunur.
"""

import collections
import html as _html
import html as html_varlik
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANELS_DIR = STATIC_JS / 'panels'
PROTECTION_JS = PANELS_DIR / 'protection_panel.js'
APP_JS = STATIC_JS / 'app.js'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(
    NODE is None,
    reason='node kurulu değil — JS panelleri gerçek render altında '
           'ölçen bekçiler koşamaz (kurulum: `brew install node`)')


# ---------------------------------------------------------------------------
# node koşum takımı — sahte DOM, GERÇEK panel dosyaları
# ---------------------------------------------------------------------------
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [staticDir, payloadPath] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this._attrs = {};
    this.innerHTML = '';
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.querySelectorAll = function () { return []; };

const documentStub = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
};

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: setInterval, clearInterval: clearInterval,
    fetch: function () { return Promise.reject(new Error('sandbox: ag yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

function run(file) {
    vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox, { filename: file });
}

run(path.join(staticDir, 'analysis_dock.js'));
(payload.panels || []).forEach(function (rel) { run(path.join(staticDir, rel)); });

function derle(root) {
    return String(root.innerHTML || '')
        + root.children.map(function (c) { return String(c.innerHTML || ''); }).join('');
}

const out = { renders: {} };
Object.keys(payload.responses || {}).forEach(function (ad) {
    const root = new El('div');
    sandbox.window.ProtectionPanel._render(payload.responses[ad], root);
    out.renders[ad] = derle(root);
});
process.stdout.write(JSON.stringify(out));
"""


def kos_harness(tmp_path, **payload):
    """Sahte DOM içinde gerçek panelleri koşar; JSON çıktısını döner."""
    script = tmp_path / 'kos_d15.js'
    script.write_text(HARNESS_JS, encoding='utf-8')
    girdi = tmp_path / 'girdi_d15.json'
    girdi.write_text(json.dumps(payload), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(STATIC_JS), str(girdi)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, ('panel node altında çöktü:\n'
                                  + proc.stderr[-3000:])
    return json.loads(proc.stdout)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


#: Uç zarfının DIŞINDA (model_valid=False) ve İÇİNDE koşumlar. İddia
#: bu adlardan değil, ucun O KOŞUMDAKİ ``model_valid`` alanından kurulur.
TPS_VAKALARI = {
    'ablatif_zarf_disi_EPDM': {'mode': 'ablative', 'q_net_W_m2': 50e6,
                               'burn_time_s': 120.0, 'material': 'epdm'},
    'ablatif_zarf_disi_silika': {'mode': 'ablative', 'q_net_W_m2': 30e6,
                                 'burn_time_s': 60.0,
                                 'material': 'silica_phenolic'},
    'ablatif_zarf_ICI': {'mode': 'ablative', 'q_net_W_m2': 2e6,
                         'burn_time_s': 10.0, 'material': 'silica_phenolic'},
    'heatsink_ERIME': {'mode': 'heat_sink', 'burn_time_s': 10.0,
                       'wall_thickness_m': 0.005, 'material': 'steel_4130',
                       'h_gas_W_m2K': 3000.0, 'T_recovery_K': 3200.0},
    'heatsink_SAGLIKLI': {'mode': 'heat_sink', 'burn_time_s': 3.0,
                          'wall_thickness_m': 0.010, 'material': 'copper',
                          'h_gas_W_m2K': 800.0, 'T_recovery_K': 900.0},
}


@pytest.fixture(scope='module')
def tps_yanitlari(client):
    """Vaka adı -> gerçek ``/api/thermal-protection`` yanıtı."""
    out = {}
    for ad, yuk in TPS_VAKALARI.items():
        r = client.post('/api/thermal-protection', json=yuk)
        assert r.status_code == 200, (
            ad + ' ' + str(r.status_code) + ' ' + r.get_data(as_text=True)[:300])
        out[ad] = r.get_json()
    return out


# ---------------------------------------------------------------------------
# P11B5-01 — geçerlilik hükmü ekrana iner
# ---------------------------------------------------------------------------
@node_gerekli
class TestProtectionGecerlilikHukmu:
    """Uç ``model_valid:false`` dediğinde ekran bunu SÖYLER."""

    def test_zarf_disi_kosumda_ucun_cumlesi_ekranda(self, tmp_path,
                                                    tps_yanitlari):
        """``validity_note`` cümlesi ekranda GEÇER (kısaltılmadan)."""
        ciz = kos_harness(tmp_path,
                          panels=['panels/protection_panel.js'],
                          responses=tps_yanitlari)['renders']
        gecersiz = {ad: y for ad, y in tps_yanitlari.items()
                    if y.get('model_valid') is False}
        assert gecersiz, ('ölçüm tabanı çürüdü: hiçbir vaka zarf dışına '
                          'çıkmıyor — bekçinin ölçtüğü kusur artık '
                          'üretilemiyor, vakalar yenilenmeli')
        eksik = []
        for ad, y in gecersiz.items():
            not_ = str(y.get('validity_note') or '')
            assert not_, ad + ': uç model_valid=False dedi ama gerekçe yok'
            # Cümlenin ilk cümleciği ekranda birebir geçmeli
            bas = not_.split(':')[0].strip()
            if bas not in ciz[ad]:
                eksik.append((ad, bas))
            # Gerekçe tabloda; hükmün KENDİSİ rozet sırasında da olmalı —
            # kullanıcı tabloyu okumadan önce rengi görür.
            if 'MODEL NOT VALID' not in ciz[ad]:
                eksik.append((ad, 'MODEL NOT VALID rozeti'))
        assert not eksik, (
            'ucun geçerlilik hükmü ekrana inmiyor: ' + repr(eksik))

    def test_gecerlilik_kancasi_her_kosumda_dogru_degeri_tasiyor(
            self, tmp_path, tps_yanitlari):
        """``data-tps-model-valid`` kancası ucun hükmüyle BİREBİR."""
        ciz = kos_harness(tmp_path,
                          panels=['panels/protection_panel.js'],
                          responses=tps_yanitlari)['renders']
        for ad, y in tps_yanitlari.items():
            if y.get('model_valid') is None:
                continue
            beklenen = 'false' if y['model_valid'] is False else 'true'
            kanca = re.findall(r'data-tps-model-valid="(\w+)"', ciz[ad])
            assert kanca, ad + ': geçerlilik kancası ekranda yok'
            assert set(kanca) == {beklenen}, (
                ad + ': uç model_valid=' + repr(y['model_valid'])
                + ' derken ekran ' + repr(kanca) + ' diyor')

    def test_zarf_disinda_ablatif_sayilar_hukum_gibi_basilmaz(
            self, tmp_path, tps_yanitlari):
        """Kazanılmamış hüküm sayı olarak basılmaz ('—' + beyan çipi)."""
        ciz = kos_harness(tmp_path,
                          panels=['panels/protection_panel.js'],
                          responses=tps_yanitlari)['renders']
        for ad, y in tps_yanitlari.items():
            if y.get('model_valid') is not False:
                continue
            if not isinstance(y.get('total_recession_mm'), (int, float)):
                continue
            sayi = '{:.2f}'.format(y['total_recession_mm'])
            assert sayi not in ciz[ad], (
                ad + ': zarf dışı koşumun gerileme sayısı (' + sayi
                + ' mm) ekranda tasarım sayısı olarak duruyor')

    def test_erime_ekseni_ekranda(self, tmp_path, tps_yanitlari):
        """``exceeds_melting`` + erime üçlüsü ekrana iner."""
        ciz = kos_harness(tmp_path,
                          panels=['panels/protection_panel.js'],
                          responses=tps_yanitlari)['renders']
        eriyen = {ad: y for ad, y in tps_yanitlari.items()
                  if y.get('exceeds_melting') is True}
        assert eriyen, ('ölçüm tabanı çürüdü: hiçbir vaka erimeye '
                        'ulaşmıyor — vakalar yenilenmeli')
        for ad, y in eriyen.items():
            assert 'EXCEEDS MELTING' in ciz[ad], (
                ad + ': cidar erime noktasını aşıyor, ekranda tek işaret yok')
            assert 'melting_point_K' in ciz[ad], (
                ad + ': erime noktası satırı ekranda yok')
            if isinstance(y.get('time_to_melting_s'), (int, float)):
                assert '{:.2f}'.format(y['time_to_melting_s']) in ciz[ad], (
                    ad + ': erime anı ekranda yok')

    def test_gecerli_kosumda_kirmizi_rozet_basilmaz(self, tmp_path,
                                                   tps_yanitlari):
        """Yanlış alarm yok: zarf İÇİ koşumda MODEL NOT VALID görünmez."""
        ciz = kos_harness(tmp_path,
                          panels=['panels/protection_panel.js'],
                          responses=tps_yanitlari)['renders']
        for ad, y in tps_yanitlari.items():
            if y.get('model_valid') is not True:
                continue
            assert 'MODEL NOT VALID' not in ciz[ad], (
                ad + ': uç koşumu geçerli ilan etti, ekran geçersiz diyor')


# ---------------------------------------------------------------------------
# P11B2-05 — dil değişiminde motor uyarıları düşmez
# ---------------------------------------------------------------------------
class TestDilDegisimindeUyariKaybi:
    """``displayWarnings`` her iki çağrı yerinde AYNI listeyi alır."""

    def test_dil_geri_cagirimi_motor_uyarilarini_tasir(self):
        kaynak = APP_JS.read_text(encoding='utf-8')
        cagrilar = re.findall(r'displayWarnings\(([^;]*?)\);', kaynak,
                              flags=re.S)
        assert cagrilar, 'displayWarnings çağrısı bulunamadı'
        eksik = [c.strip() for c in cagrilar
                 if 'injector' in c and 'motor' not in c
                 and 'collectWarn' not in c]
        assert not eksik, (
            'displayWarnings motor uyarılarını taşımayan çağrı(lar) ile '
            'kullanılıyor — dil değişiminde motor uyarıları düşer: '
            + repr(eksik))

# ---------------------------------------------------------------------------
# app.js — DOM'suz fonksiyon koşum takımı (yapay zekâ yükü + 3B kablo)
# ---------------------------------------------------------------------------
AI_HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const [staticDir, payloadPath] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
const appSrc = fs.readFileSync(path.join(staticDir, 'app.js'), 'utf8');
const vizSrc = fs.readFileSync(path.join(staticDir, 'motor_viz3d.js'), 'utf8');

function grab(src, name) {
    const start = src.indexOf('function ' + name + '(');
    if (start < 0) return null;
    let depth = 0;
    for (let j = src.indexOf('{', start); j < src.length; j++) {
        if (src[j] === '{') depth++;
        else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(start, j + 1); }
    }
    return null;
}
const FORM = payload.form || {};
const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    window: { HRMA_VERSION: 'test' },
    document: {
        getElementById: function (id) {
            return (id in FORM) ? { value: String(FORM[id]) } : null;
        },
        querySelectorAll: function () { return []; },
    },
    JSON: JSON, Math: Math, Number: Number, Date: Date, Array: Array,
    Object: Object, String: String, isFinite: isFinite,
    parseFloat: parseFloat, parseInt: parseInt,
    T: function (k, f) { return f; },
};
sandbox.window.document = sandbox.document;
vm.createContext(sandbox);
['prepareAIData', 'generateRunId', 'detectGeometryAnomalies',
 'structurizeWarnings', 'buildStructuralExport', 'identifyRiskFactors',
 'getFuelTypeDisplayName', 'collectResultWarnings', 'numOrNull',
 'buildNozzleGeometryExport', 'buildInjectorFlowExport'].forEach(function (n) {
    const kod = grab(appSrc, n);
    if (kod) { try { vm.runInContext(kod, sandbox); } catch (e) { /* atla */ } }
});
vm.runInContext(grab(vizSrc, 'num') + '\n'
                + grab(vizSrc, 'resolveInjectorSource'), sandbox);

const out = {};
out.ai = vm.runInContext('prepareAIData', sandbox)(payload.results);
out.ekranUyarilari = vm.runInContext('collectResultWarnings', sandbox)(payload.results);
// 3B sahneye GERÇEKTEN giden sözlük: app.js kaynağındaki kablodan okunur.
const enjektorKablosu = /injector_results:\s*currentResults\.injector/.test(appSrc);
out.enjektorKablosu = enjektorKablosu;
const md = enjektorKablosu
    ? Object.assign({}, payload.results.motor,
                    { injector_results: payload.results.injector })
    : payload.results.motor;
out.sahne = vm.runInContext('resolveInjectorSource', sandbox)(md);
process.stdout.write(JSON.stringify(out));
"""


def _acisal_bloklari_topla(yuk, yol=''):
    """Yükün İÇİNDEKİ her nozzle açı bloğunu (yol, sözlük) olarak döndürür.

    ÖH D17 / P11B2-03 ŞARTI: bekçi tek bir adrese bakmaz — yükün her
    yerinde ``convergent_angle_deg`` taşıyan sözlük aranır. Yeni bir
    kopya eklenirse bu bekçi onu da ölçer.
    """
    bulunan = []
    if isinstance(yuk, dict):
        if 'convergent_angle_deg' in yuk or 'divergent_angle_deg' in yuk:
            bulunan.append((yol or '<kok>', yuk))
        for k, v in yuk.items():
            bulunan.extend(_acisal_bloklari_topla(v, yol + '.' + str(k)))
    elif isinstance(yuk, list):
        for i, v in enumerate(yuk):
            bulunan.extend(_acisal_bloklari_topla(v, yol + '[' + str(i) + ']'))
    return bulunan


def kos_ai(tmp_path, results, form):
    script = tmp_path / 'kos_ai_d15.js'
    script.write_text(AI_HARNESS_JS, encoding='utf-8')
    girdi = tmp_path / 'girdi_ai_d15.json'
    girdi.write_text(json.dumps({'results': results, 'form': form}),
                     encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(STATIC_JS), str(girdi)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, ('app.js node altında çöktü:\n'
                                  + proc.stderr[-3000:])
    return json.loads(proc.stdout)


#: Ölçüm koşusu — O/F bandı dışında, gerçek uyarı üreten bir hibrit motor.
AI_FORM = {'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
           'tank_pressure': 50.0, 'oxidizer_temp': 288.15,
           'chamber_material': 'steel_4130'}
AI_YUKU = dict(AI_FORM, thrust=1000, burn_time=10, of_ratio=7.5,
               chamber_pressure=20.0, expansion_ratio=8.0)


@pytest.fixture(scope='module')
def calculate_yaniti(client):
    r = client.post('/calculate', json=AI_YUKU)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@node_gerekli
class TestYapayZekaYuku:
    """``prepareAIData`` çözücünün sayılarını ve uyarılarını taşır."""

    def test_cozucunun_butun_uyarilari_yukte(self, tmp_path,
                                             calculate_yaniti):
        """P11B2-02: ekranda görünen her uyarı yükte de var."""
        o = kos_ai(tmp_path, calculate_yaniti, AI_FORM)
        kodlar = [(w.get('code') if isinstance(w, dict) else str(w))
                  for w in o['ekranUyarilari']]
        assert len(kodlar) >= 4, (
            'ölçüm tabanı çürüdü: bu koşum artık uyarı üretmiyor — '
            'bekçinin ölçtüğü kusur gösterilemez, koşum yenilenmeli')
        duz = json.dumps(o['ai'], ensure_ascii=False)
        yutulan = [k for k in kodlar if k not in duz]
        assert not yutulan, (
            'yapay zekâ yükü ekranın gördüğü uyarıları yutuyor: '
            + repr(yutulan))

    def test_uyari_varken_LOW_RISK_hukmu_basilmaz(self, tmp_path,
                                                  calculate_yaniti):
        """P11B2-02: çözücü uyarı yayımlarken 'riskler normal' denmez."""
        o = kos_ai(tmp_path, calculate_yaniti, AI_FORM)
        assert o['ekranUyarilari'], 'ölçüm tabanı çürüdü: uyarı yok'
        riskler = json.dumps(
            o['ai']['safety_considerations']['risk_factors'],
            ensure_ascii=False)
        assert 'LOW_RISK' not in riskler, (
            'çözücü ' + str(len(o['ekranUyarilari'])) + ' uyarı yayımlarken '
            'yük "riskler normal aralıkta" diyor: ' + riskler)

    def test_lule_acilari_ve_enjektor_sayilari_cozucuden(
            self, tmp_path, calculate_yaniti):
        """P11B2-03: yükteki geometri = yanıttaki geometri."""
        o = kos_ai(tmp_path, calculate_yaniti, AI_FORM)
        ang = calculate_yaniti['motor'].get('nozzle_angles') or {}
        inj = calculate_yaniti.get('injector') or {}
        assert ang, 'ölçüm tabanı çürüdü: motor.nozzle_angles yok'
        ng = o['ai']['geometry']['nozzle_geometry']
        assert ng.get('convergent_angle_deg') == ang['convergent_half_angle_deg']
        assert ng.get('divergent_angle_deg') == ang['divergent_half_angle_deg']
        assert ng.get('nozzle_type') == ang.get('nozzle_type')
        ic = o['ai']['injector_design']
        assert ic.get('discharge_coefficient') == inj.get('discharge_coefficient')
        if inj.get('type') == 'showerhead':
            assert ic.get('l_over_d_ratio') == inj.get('L_D_ratio')

        # --- ÖH D17 (Fable-D15 ŞARTI + OH-D16-13): YÜKÜN *HER* NOZZLE AÇI
        # BLOĞU aynı çözücü değerini taşır. D15 onarımı yalnız
        # `geometry.nozzle_geometry`yi düzeltmişti; aynı yükteki
        # `thermal_analysis.nozzle_angles` kopyası `|| 15.0` / `|| 12.0`
        # yedeklerini ateşleyip 15°/12° basmaya devam ediyordu (ölçüldü:
        # raw/OH/D17/arayuz/a1/once.json M1 iki_blok_CELISIK=true). Bekçi
        # ikinci kopyayı GÖRMÜYORDU: 99/99 mutasyonu yeşil geçiyordu.
        beklenen = {'convergent_angle_deg': ang['convergent_half_angle_deg'],
                    'divergent_angle_deg': ang['divergent_half_angle_deg']}
        duz = json.dumps(o['ai'], ensure_ascii=False)
        bloklar = _acisal_bloklari_topla(o['ai'])
        assert len(bloklar) >= 2, (
            'ölçüm tabanı çürüdü: yükte iki nozzle açı bloğu bekleniyordu, '
            + str(len(bloklar)) + ' bulundu — kopya sessizce kaldırılmışsa '
            'bu bekçi güncellenmeli')
        for yol, blok in bloklar:
            for k, v in beklenen.items():
                assert blok.get(k) == v, (
                    'yükün "' + yol + '" bloğu çözücüden BAŞKA bir açı '
                    'taşıyor: ' + k + '=' + repr(blok.get(k))
                    + ' ⟷ çözücü ' + repr(v) + ' (tek-kaynak ihlali)')
        # Uydurma yedek sabitleri yükün hiçbir yerinde olmasın: mutasyon
        # 15.0/12.0 ya da 99/99 koyarsa bu koşul kırmızıya döner.
        for yol, blok in bloklar:
            assert blok.get('source') == 'motor.nozzle_angles', (
                '"' + yol + '" bloğu kaynağını beyan etmiyor: ' + repr(blok))
        # Oda sıcaklığı da çözücüden; `|| 3000` yedeği yok.
        ta = o['ai']['thermal_analysis']
        assert ta.get('chamber_temperature_K') == \
            calculate_yaniti['motor'].get('chamber_temperature'), (
                'thermal_analysis.chamber_temperature_K çözücüden gelmiyor: '
                + repr(ta.get('chamber_temperature_K')))
        assert '"chamber_temperature_K": 3000' not in duz

    def test_akis_blogu_form_girdisini_okur_ve_indis_uydurmaz(
            self, tmp_path, calculate_yaniti):
        """P11B2-04: sabit 293,15 K ve ΔP/25 bar indisi yok."""
        o = kos_ai(tmp_path, calculate_yaniti, AI_FORM)
        fc = o['ai']['injector_design']['flow_characteristics']
        assert fc.get('oxidizer_inlet_temperature_K') == AI_FORM['oxidizer_temp'], (
            'oksitleyici giriş sıcaklığı formdan okunmuyor: '
            + repr(fc.get('oxidizer_inlet_temperature_K')))
        assert 'cavitation_index' not in fc, (
            'kavitasyon indisi hâlâ JS tarafında uyduruluyor: ' + repr(fc))
        assert fc.get('cavitation_status') == 'NOT_MODELLED'
        mp = o['ai']['thermal_analysis']['material_properties']
        assert 'recommended_materials' not in mp, (
            'sabit malzeme listesi hâlâ yükte: ' + repr(mp))
        assert mp.get('selected_material') == AI_FORM['chamber_material']


@node_gerekli
class TestUcBoyutluEnjektorKablosu:
    """P11B1-04: 3B sahne panelin gösterdiği enjektörü çizer."""

    def test_sahne_ve_panel_ayni_enjektoru_gosterir(self, tmp_path,
                                                    calculate_yaniti):
        o = kos_ai(tmp_path, calculate_yaniti, AI_FORM)
        inj = calculate_yaniti.get('injector') or {}
        assert inj.get('n_holes'), 'ölçüm tabanı çürüdü: panel deliği yok'
        assert o['enjektorKablosu'], (
            'app.js mount çağrısı sahneye enjektör çözücüsünün sonucunu '
            'vermiyor — sahne injector_design yedeğine düşer')
        assert o['sahne']['source'] == 'injector_results', (
            'sahne panelin kaynağını değil ' + repr(o['sahne']['source'])
            + ' yedeğini çiziyor')
        assert o['sahne']['nOrifices'] == inj['n_holes'], (
            'sahne ' + repr(o['sahne']['nOrifices']) + ' delik, panel '
            + repr(inj['n_holes']) + ' delik gösteriyor')
        assert o['sahne']['orificeMm'] == inj['hole_diameter']


class TestBayatSonucBeyani:
    """P11B2-07: uç hata dönünce ekran kazanılmamış hâle geçer."""

    def test_hata_dalinda_bayat_sonuc_dusurulur(self):
        kaynak = APP_JS.read_text(encoding='utf-8')
        i = kaynak.index("handleError(error, 'Main Calculation Function')")
        # Hata dalı, bayat sonucu düşüren çağrıyı İÇERMELİ
        pencere = kaynak[max(0, i - 1500):i]
        assert 'invalidateStaleResults()' in pencere, (
            'calculate() hata dalı bayat sonucu düşürmüyor: sayılar, sonuç '
            'paneli ve dışa aktarım düğmeleri eski koşumdan kalır')
        gövde_i = kaynak.index('function invalidateStaleResults()')
        gövde = kaynak[gövde_i:gövde_i + 900]
        for kanit in ('currentResults = null', 'resultsPanel',
                      'exportResultsBtn', 'exportSTLBtn', 'downloadEngBtn'):
            assert kanit in gövde, (
                'bayat sonuç düşürücüsü ' + kanit + ' kanalını kapatmıyor')


# ---------------------------------------------------------------------------
# P11B4-11 — "Comprehensive Safety" paneli ucun YAPRAKLARINI ekrana indirir
# ---------------------------------------------------------------------------
# Defter başlığı ("13 bloğun 4'ü çiziliyor; tahliye mesafesi, patlama
# yarıçapı, TNT, KKD, acil durum eylemleri hiç ekrana çıkmıyor") bu HEAD'de
# ÖLÇÜMLE ÇÜRÜDÜ: adı geçen beş kalemin beşi de ekranda
# (``docs/scofield/raw/OH/D15/ui-paneller/a1/b4_11_alan_ONCE.json``:
# explosive_hazards 50/50, emergency_procedures 31/31, safety_equipment
# 13/13). Ölçüm bunun yerine 12 SAĞIR YAPRAK buldu ve onlar onarıldı:
#   * ``pressure_safety`` 16/23 — ekranda yalnız HEDEF patlama basıncı
#     (80,0 bar) duruyordu; tasarımın gerçekten hesaplanan patlama basıncı
#     (693,5 bar), marjı (8,67), modeli (Faupel) ve kabın hükmü (PASS)
#     inmiyordu; üç güvenlik aygıtının ``severity`` beyanı düşüyordu.
#   * ``risk_assessment.risk_matrix.acceptance`` 4 cümlenin dördü de yok —
#     matris renkli çiziliyor, rengin ne talep ettiği yazmıyordu.
#   * ``compliance.disclaimer_code`` — ekrandaki cümlenin ucun beyanı mı
#     güvertenin kendi metni mi olduğu okunamıyordu.
# Bekçi ucun O KOŞUMDAKİ yanıtından iddia kurar; sabit sayı taşımaz.
SAFETY_JS = STATIC_JS / 'panels' / 'safety_panel.js'

DOCK_HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const [rootDir, payloadPath] = process.argv.slice(2);
const cfg = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

function makeNode(id) {
    return {
        id: id, __html: '', textContent: '', style: {}, attrs: {},
        children: [], value: '',
        classList: { contains: function () { return false; },
                     add: function () {}, remove: function () {} },
        setAttribute: function (k, v) { this.attrs[k] = String(v); },
        getAttribute: function (k) {
            return (k in this.attrs) ? this.attrs[k] : null; },
        appendChild: function (c) { this.children.push(c); return c; },
        querySelector: function () { return makeNode('q'); },
        querySelectorAll: function () { return []; },
        addEventListener: function () {},
        get innerHTML() { return this.__html; },
        set innerHTML(v) { this.__html = v; },
    };
}
function deepText(n) {
    if (!n) return '';
    let s = String(n.innerHTML || '');
    (n.children || []).forEach(function (c) { s += deepText(c); });
    return s;
}
const nodes = {};
global.document = {
    head: makeNode('head'), body: makeNode('body'),
    getElementById: function (id) {
        if (!(id in nodes)) nodes[id] = makeNode(id);
        return nodes[id];
    },
    createElement: function () { return makeNode(null); },
    querySelector: function () { return makeNode('q'); },
    querySelectorAll: function () { return []; },
    addEventListener: function () {},
};
global.window = global;
try {
    Object.defineProperty(global, 'navigator',
                          { value: { language: 'en' }, configurable: true });
} catch (e) { /* node >= 21 salt-okur */ }
global.localStorage = { getItem: function () { return null; },
                        setItem: function () {} };
global.requestAnimationFrame = function (fn) { fn(0); return 1; };
global.fetch = function () {
    return Promise.resolve({ ok: false, json: function () { return {}; } });
};
require(path.join(rootDir, 'hrma/static/js/analysis_dock.js'));
(cfg.panelFiles || []).forEach(function (f) { require(path.join(rootDir, f)); });
const spec = (window.AnalysisDock._registry || [])
    .filter(function (p) { return p.id === cfg.panelId; })[0];
if (!spec) {
    process.stdout.write(JSON.stringify({ error: 'panel kayıtlı değil' }));
} else {
    const root = makeNode('root');
    let err = null;
    try { spec.render(cfg.body, root); }
    catch (e) { err = String((e && e.stack) || e); }
    const html = deepText(root);
    process.stdout.write(JSON.stringify({
        error: err, html: html,
        text: html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim(),
    }));
}
"""

#: Gerçek bir test standı koşumu. İddialar bu adlardan değil, ucun
#: yanıtından kurulur.
SAFETY_YUKU = {'motor_type': 'hybrid', 'chamber_pressure': 40.0,
               'chamber_temperature': 3000.0, 'propellant_mass': 5.0,
               'chamber_diameter': 0.1, 'chamber_length': 0.5,
               'wall_thickness': 0.005, 'thrust': 1000.0, 'burn_time': 10.0,
               'propellant_type': 'composite', 'facility_type': 'test_stand',
               'material': 'steel_4130'}


@pytest.fixture(scope='module')
def safety_yaniti(client):
    r = client.post('/analyze_safety', json=SAFETY_YUKU)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def safety_ekrani(safety_yaniti, tmp_path_factory):
    """safety_panel'in GERÇEK render çıktısı (node, sahte DOM)."""
    if NODE is None:
        pytest.skip('node kurulu değil')
    tmp = tmp_path_factory.mktemp('d15_safety')
    script = tmp / 'kos_dock_d15.js'
    script.write_text(DOCK_HARNESS_JS, encoding='utf-8')
    girdi = tmp / 'girdi_safety_d15.json'
    girdi.write_text(json.dumps({
        'panelId': 'safety', 'body': safety_yaniti,
        'panelFiles': ['hrma/static/js/panels/safety_panel.js']}),
        encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(REPO_ROOT), str(girdi)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, ('safety_panel node altında çöktü:\n'
                                  + proc.stderr[-3000:])
    ciz = json.loads(proc.stdout)
    assert not ciz.get('error'), 'render hatası: ' + str(ciz.get('error'))
    # ÖH D28 / arayuz a1 (OH-D27-16) — ÖLÇÜM KÖRLÜĞÜ DÜZELTMESİ.
    # Harness metni etiketleri söküyor ama HTML VARLIK KODLARINI
    # çözmüyordu; panel ``esc()``ten geçen her sunucu metnini ``&`` ->
    # ``&amp;`` yazdığı için süpürme, ekranda GÖRÜNEN bir dizeyi "sağır"
    # sayıyordu. ÖLÇÜLDÜ: patlama künyesi (``Kinney & Graham``) ekranda
    # tam olarak duruyordu, ``_gorunur`` yine False dönüyordu. Kullanıcı
    # ``&amp;`` değil ``&`` görür — ölçüm artık kullanıcının gördüğünü
    # ölçüyor. Bu bir GEVŞETME DEĞİLDİR: çözme yalnız YANLIŞ "sağır"
    # hükmünü kaldırır, yeni bir alanı affetmez.
    ciz['text'] = _html.unescape(ciz['text'])
    return ciz


@pytest.fixture(scope='module')
def safety_bolgeleri(safety_ekrani):
    """Ekranın ADLI bölgeleri (ad+değer ölçütü) — koşumda bir kez çözülür."""
    return _ekran_bolgeleri(safety_ekrani)


def _ekran_jetonlari(metin):
    """Ekrandaki sayı jetonları: (değer, basamak sayısı)."""
    duz = metin.replace(',', '')
    return [(float(t), len(t.split('.')[1]) if '.' in t else 0)
            for t in re.findall(r'-?\d+(?:\.\d+)?', duz)]


def _duz_metin(govde):
    """Etiketleri söküp boşlukları tekleştirir; VARLIK KODUNU çözer.

    Çözme sırası önemlidir: önce etiket sökülür, sonra ``&amp;`` gibi
    kodlar çözülür — ters sırada ``&lt;div&gt;`` etikete dönüşüp metni
    yutardı. Bugünkü renderda varlık kodu YOKTUR (ölçüldü: 0 eşleşme),
    ama panel ``esc()``ten geçen her sunucu metnini kodlar; kod çözülmezse
    ``Kinney &amp; Graham`` etiketi ``amp`` diye HAYALET bir adlandırma
    sözcüğü üretir ve bölge bağını bozar.
    """
    return html_varlik.unescape(
        re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', govde)).strip())


def _sozcukler(metin):
    return {w for w in re.split(r'[^a-z0-9]+', metin.lower()) if w}


def _yol_parcalari(yol):
    return [p for p in re.split(r'\.', re.sub(r'\[\d+\]', '', yol)) if p]


def _ekran_bolgeleri(ciz):
    """Render çıktısını ADLI bölgelere ayırır — ad+değer ölçütünün tabanı.

    Bölge, ekranda bir DEĞERİN bir ADIN altında durduğu en küçük parçadır:

    * **tablo satırı** — adı ilk hücre + ``data-safety-field`` yolu +
      tablonun ``<th>`` başlıkları + satırın içinde durduğu ``<h4>`` bölüm
      başlığı; gövdesi satırın TÜM hücreleri (çok sütunlu tablolarda değer
      ikinci hücrede olmayabilir);
    * **istatistik kutusu** — adı etiket div'i, gövdesi değer div'i.

    Bölgelerin dışında kalan her şey ETİKETSİZ ``serbest`` metindir (bölüm
    başlıkları, cümleler, liste maddeleri).

    ``genel``: bölgelerin dörtte birinden çoğunu etiketleyen sözcükler.
    Böyle bir sözcük hiçbir yaprağı ADLAMAZ — her bölüm başlığındaki
    ``safety`` gibi. Elle yazılmaz, o koşumun kendi ekranından ÖLÇÜLÜR.
    """
    html = ciz['html']
    basliklar = [(m.start(), _sozcukler(_duz_metin(m.group(1))))
                 for m in re.finditer(r'<h4[^>]*>(.*?)</h4>', html, re.S)]

    def _bolum(yer):
        akt = set()
        for p, sz in basliklar:
            if p < yer:
                akt = sz
        return akt

    def _bolge(alan, sozcukler, govde):
        return {'alan': alan, 'sozcukler': sozcukler, 'govde': govde,
                'jeton': _ekran_jetonlari(govde)}

    bolgeler, kalan = [], html
    for tablo in re.finditer(r'<table[^>]*>(.*?)</table>', html, re.S):
        bassoz = set()
        for th in re.findall(r'<th\b[^>]*>(.*?)</th>', tablo.group(1), re.S):
            bassoz |= _sozcukler(_duz_metin(th))
        bolum = _bolum(tablo.start())
        for tr in re.finditer(r'<tr>(.*?)</tr>', tablo.group(1), re.S):
            hucre = re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', tr.group(1),
                               re.S)
            if not hucre:
                continue
            alan = re.findall(r'data-safety-field="([^"]+)"', hucre[0])
            bolgeler.append(_bolge(
                alan[0] if alan else None,
                _sozcukler(_duz_metin(hucre[0])) | bassoz | bolum,
                ' '.join(_duz_metin(h) for h in hucre)))
        kalan = kalan.replace(tablo.group(0), ' ')
    for kutu in re.finditer(r'letter-spacing:0\.08em;">([^<]{1,60})</div>\s*'
                            r'<div[^>]*>(.*?)</div>', html, re.S):
        bolgeler.append(_bolge(None,
                               _sozcukler(kutu.group(1))
                               | _bolum(kutu.start()),
                               _duz_metin(kutu.group(2))))
        kalan = kalan.replace(kutu.group(0), ' ')

    sik = collections.Counter()
    for b in bolgeler:
        sik.update(b['sozcukler'])
    esik = max(1, int(0.25 * len(bolgeler)))
    serbest = _duz_metin(kalan)
    return {'bolgeler': bolgeler, 'serbest': serbest,
            'serbest_jeton': _ekran_jetonlari(serbest),
            'genel': {w for w, n in sik.items() if n > esik},
            'metin': ciz['text'], 'jeton': _ekran_jetonlari(ciz['text'])}


def _deger_bolgede(v, govde, jeton):
    """Değerin KENDİSİ bu bölgede basılı mı? (ad denetimi çağıranındır)"""
    if isinstance(v, bool):
        return str(v).lower() in govde.lower()
    if isinstance(v, (int, float)):
        return any(round(float(v), d) == t for t, d in jeton)
    n = lambda x: x.replace('_', ' ').lower()  # noqa: E731
    return n(v[:60]) in n(govde)


def _bolge_bagli(bolge, yol, genel):
    """Bölge bu yaprağı ADLIYOR mu?

    İki bağ kabul edilir:

    * **makine yolu** — bölgenin ``data-safety-field`` yolu yaprağın atası
      ya da kendisi (``blast_distances.lethal`` satırı o kaydın
      ``distance_m``ini adlar);
    * **ayırt edici sözcük** — bölgenin adlandıran sözcükleri yaprağın SON
      parçasından bir sözcük taşır (``Design`` kutusu ↔
      ``design_pressure_bar``). ``genel`` sözcükler bağ kurmaz.
    """
    par = _yol_parcalari(yol)
    if bolge['alan']:
        ep = _yol_parcalari(bolge['alan'])
        n = len(ep)
        if ep and n <= len(par) and any(par[i:i + n] == ep
                                        for i in range(len(par) - n + 1)):
            return True
    return bool((bolge['sozcukler'] & _sozcukler(par[-1])) - genel)


def _gorunur(yol, v, ekran):
    """Yaprağın değeri ekranda KENDİ ADININ ALTINDA mı? (ad+değer ölçütü)

    ÖH D28 / **OH-D27-17**. Eski ölçüt yalnız DEĞER düzeyindeydi: ekranın
    HERHANGİ bir jetonu, kendi basamak sayısıyla yuvarlanınca yaprağa eşit
    çıkıyorsa yaprak "görünür" sayılıyordu. Bu SAYI ÇAKIŞMASINA açıktı ve
    süpürmeyi kendi kusuruna kör bırakıyordu — ölçüldü
    (``docs/scofield/raw/OH/D28/bekci-cevirisi/a1/``): 297 yaprağın DÖRDÜ
    ekranda hiç yokken yalnız çakışma sayesinde aklanıyordu, örneğin
    ``blast_distances.lethal.scaled_distance_m_per_kg13`` = 2,7494 ekranın
    başka bir alanındaki "3" jetonuyla, ``pressure_safety.inner_diameter_mm``
    = 100,0 ise patlama satırındaki "100.0 kPa" AŞIRI BASINCIYLA.

    Yeni ölçüt: SAYI ve MANTIK yaprağı, kendisini ADLAYAN bir bölgede
    (kendi tablo satırı ya da kendi kutusu) basılı olmalıdır — bkz.
    ``_ekran_bolgeleri`` ve ``_bolge_bagli``. Jetonun kendi basamağıyla
    yuvarlanması KALDI ama artık yaprağın kendi bölgesiyle sınırlı;
    ölçümde bölge içinde kalan çakışma çıkmadı.

    Etiketsiz serbest metinde (bölüm başlığı, cümle, liste maddesi) duran
    bir SAYI görünür SAYILMAZ. Bu, ölçülerek seçilmiş bir kapıdır: aday
    "adın 140 karakter yakınında ara" gevşemesi gerçek ekranda TEK bir
    yaprağı bile aklamıyordu (bölge ölçütü 10 kör, gevşemeyle de 10),
    buna karşılık bölüm başlığındaki ``5 = highest`` gibi bir jetonu
    komşu bir alanın değeri sayabiliyordu.

    METİN yaprağı tüm ekranda aranır: 60 karakterlik bir cümlenin
    rastlantıyla eşleşmesi diye bir şey yoktur, ölçülen çakışma SAYIDADIR.
    Alt çizgi normalize edilir — panel ``MEDIUM_PRESSURE``'ı "MEDIUM
    PRESSURE" basar.
    """
    if isinstance(v, str):
        return _deger_bolgede(v, ekran['metin'], ekran['jeton']) if v \
            else False
    if not isinstance(v, (bool, int, float)):
        return None
    return any(_bolge_bagli(b, yol, ekran['genel'])
               and _deger_bolgede(v, b['govde'], b['jeton'])
               for b in ekran['bolgeler'])


def _yapraklar(o, yol=''):
    if isinstance(o, dict):
        for k, v in o.items():
            for x in _yapraklar(v, (yol + '.' + k) if yol else k):
                yield x
    elif isinstance(o, list):
        for i, v in enumerate(o):
            for x in _yapraklar(v, yol + '[%d]' % i):
                yield x
    else:
        yield yol, o


#: ÖH D27 / fix-26b — EKRANA İNMEYEN GÜVENLİK YAPRAKLARI (D28 arayuz borcu).
#:
#: Taban ``8abbe822``de süpürme 6/297 kör yaprak buldu; tabanı ``7751531``
#: iken 0/283 idi. Altısı da AYNI D26 aşamasından geldi: yapisal-sistem a1
#: (``aabdcdcd``, P5B2-05) patlama mesafelerini elle yazılmış Z tablosundan
#: alıp Kinney-Graham bağıntısından TÜRETMEYE geçirdi ve her kayda iki yeni
#: alan ekledi — ``basis`` (kaynak künyesi) ve
#: ``scaled_distance_m_per_kg13`` (Hopkinson-Cranz ölçekli mesafe Z).
#:
#: Kusur SUNUCUDA DEĞİL: künye doğru üretiliyor. Kusur, panelin okuyucusu
#: ``addBlastRow``ın (safety_panel.js:605) her kayıttan yalnız
#: ``distance_m`` ve ``overpressure_kpa`` almasıdır — künyeyi de ölçekli
#: mesafeyi de HİÇ okumaz. Panel bağlaması ARAYUZ kulvarının işidir ve D28
#: kalemi olarak kayda geçti (fix26/b/rapor.md §4).
#:
#: LİSTE TEK YÖNLÜDÜR: dışarıda kalan yeni kör yaprak süpürmeyi kırmızı
#: yakar, ödenen satır ise ``test_yaprak_borcu_olu_satir_tasimaz``da
#: kırmızı verir. Böylece envanter "unutulmuş af listesi"ne dönüşemez.
GUVENLIK_YAPRAK_BORCU = {
    # BORÇ TAMAMEN ÖDENDİ — ÖH D28 / arayuz a1 (OH-D27-16).
    # ÖLÇÜLDÜ: taban 7cd08bcc ``D28/arayuz/a1/once.json`` -> ``sonra.json``.
    # ``safety_panel.js::addBlastRow`` artık her kayıtta ölçekli mesafeyi
    # (``Z = ... m/kg^(1/3)``) satır içinde, model künyesini
    # (``basis``) ise ayrı bir ``<path>.basis`` satırında basıyor.
    # Künye dört kaydın DÖRDÜNDE de aynı dizedir, bu yüzden ekrana bir
    # kez yazılır; FARKLI bir künye gelirse o da yazılır (susturma yok).
    # Altı satırın altısı da düştü: kayıt tek yönlüdür ve ödenmiş satır
    # ``test_yaprak_borcu_olu_satir_tasimaz``ta KIRMIZI verir.
    # Sözlüğün BOŞ kalması anlamlıdır: yeni bir kör yaprak doğarsa
    # ``test_ucun_hicbir_guvenlik_yapragi_sagir_degil`` kırmızı yanar ve
    # buraya ADLI gerekçeyle yazılması gerekir.
    # BİRLEŞME NOTU (ana model, 9 Eyl 2026): D28 bekci-cevirisi a1 (OH-D27-17)
    # ölçütü ad+değer düzeyine çekince sekiz patlama yolu (basis ×4, Z ×4)
    # kör çıkmıştı; arayuz a1 hepsini ÖDEDİ, o satırlar buraya girmedi.
    # Aşağıdaki İKİ kap-geometrisi yaprağı ise arayuz'un ödediği borç
    # DEĞİLDİR (panel basınç kabı geometrisini hiç basmıyor) → D29 arayuz.
    # ÖH D29 / OH-D28-04 (kulvar arayuz-panel, a1) — İKİ KAP-GEOMETRİSİ
    # YAPRAĞI ÖDENDİ, SATIRLARI SİLİNDİ. D28 / OH-D27-17 ölçümü bu ikisini
    # (`pressure_safety.inner_diameter_mm`, `pressure_safety.
    # wall_thickness_mm`) kör bırakmış ve gerekçesine "panel bağlaması
    # ARAYUZ kulvarının işidir" yazmıştı. Bağlandı:
    # `safety_panel.js::pressureVesselBlock` ikisini de `addRow` ile
    # MAKİNE ADIYLA ve 'mm' birimiyle basıyor (birim dönüşümü panelde
    # YAPILMAZ — uç bloğu milimetre yayımlar). Ölçüm:
    # `docs/scofield/raw/OH/D29/arayuz-panel/a1/{once,sonra}.json`
    # OH-D28-04 — geçiş sayısı ikisinde de 0 -> 1.
    # Sözlüğün BOŞ kalması anlamlıdır: yeni bir kör yaprak doğarsa
    # `test_ucun_hicbir_guvenlik_yapragi_sagir_degil` kırmızı yanar.
    # Ödenmiş satırın burada kalması `test_yaprak_borcu_olu_satir_tasimaz`
    # ile KIRMIZI verirdi.
}

#: Süpürmenin KENDİ KÖRLÜĞÜ ölçülüp GİDERİLDİ (ÖH D28 / **OH-D27-17**).
#:
#: fix-26b envanterinde dört ``basis`` vardı ama yalnız İKİ ölçekli mesafe.
#: Sebep panelin o ikisini basması DEĞİLDİ — hiçbirini basmıyor —,
#: süpürmenin sayı ölçütünün SAYI ÇAKIŞMASINA açık olmasıydı: ``_gorunur``
#: ekranın HERHANGİ bir jetonunu kendi basamak sayısıyla yuvarlıyordu, öyle
#: ki risk satırındaki "3" (``#3 Pressure 2.0 / 5``) lethal Z'yi 2,7494,
#: ölçeğin "/ 5"i ise serious_injury Z'yi 4,5400 "görünür" sayıyordu —
#: göreli hata %9,1 ve %10,1.
#:
#: D28'de ölçüt AD+DEĞER düzeyine çekildi (``_ekran_bolgeleri`` /
#: ``_bolge_bagli``): değer, yaprağı ADLAYAN bölgede basılı olmalıdır.
#: Ölçüm (``docs/scofield/raw/OH/D28/bekci-cevirisi/a1/``): aynı render,
#: 297 yaprak, kör sayısı **6 → 10**. Çıkan dördü de gerçek borçtur ve
#: yukarıda adıyla kayıtlıdır; ikisi (kap geometrisi) D26'dan daha eski.
#:
#: ``BLAST_KAYITLARI`` bu simetriyi kilitler: dört kaydın DÖRDÜ de hem
#: ``basis`` hem ``scaled_distance_m_per_kg13`` borcunu taşır
#: (``tests/test_d28_bekci_cevirisi_a1.py``).
BLAST_KAYITLARI = ('lethal', 'serious_injury', 'minor_injury',
                   'property_damage')


@node_gerekli
class TestGuvenlikPaneliYapraklari:
    """P11B4-11: ucun yayımladığı her güvenlik yaprağı ekrana iner."""

    def test_patlama_basinci_hukmu_ekranda(self, safety_yaniti,
                                           safety_bolgeleri):
        p = (safety_yaniti['safety_analysis'].get('pressure_safety') or {})
        assert isinstance(p.get('actual_burst_pressure_bar'), float), (
            'ölçüm tabanı çürüdü: uç artık actual_burst_pressure_bar '
            'yayımlamıyor — bekçinin ölçtüğü kusur gösterilemez')
        for alan in ('actual_burst_pressure_bar', 'burst_margin'):
            assert _gorunur('pressure_safety.' + alan, p[alan],
                            safety_bolgeleri), (
                'ekran ucun ' + alan + ' değerini (' + repr(p[alan])
                + ') basmıyor: kullanıcı yalnız HEDEF patlama basıncını '
                + repr(p.get('required_burst_pressure_bar'))
                + ' görüp kabın orada patladığını sanabilir')
        for alan in ('burst_pressure_source', 'vessel_status'):
            assert _gorunur('pressure_safety.' + alan, p[alan],
                            safety_bolgeleri), (
                'ekran ucun ' + alan + ' beyanını basmıyor: '
                + repr(p[alan]))

    def test_guvenlik_aygitlarinin_agirligi_ekranda(self, safety_yaniti,
                                                    safety_bolgeleri):
        dev = ((safety_yaniti['safety_analysis'].get('pressure_safety') or {})
               .get('safety_devices_required') or [])
        assert dev and isinstance(dev[0], dict) and dev[0].get('severity'), (
            'ölçüm tabanı çürüdü: uç artık aygıt kaydında severity '
            'yayımlamıyor')
        for i, d in enumerate(dev):
            assert _gorunur(
                'pressure_safety.safety_devices_required[%d].severity' % i,
                d['severity'], safety_bolgeleri), (
                'aygıt #' + str(i) + ' (' + str(d.get('code'))
                + ') ekranda ağırlık beyanı olmadan duruyor: '
                + repr(d['severity']))

    def test_risk_matrisi_kabul_olcutu_ekranda(self, safety_yaniti,
                                               safety_bolgeleri):
        rm = ((safety_yaniti['safety_analysis'].get('risk_assessment') or {})
              .get('risk_matrix') or {})
        acc = rm.get('acceptance') or {}
        assert acc, 'ölçüm tabanı çürüdü: uç risk_matrix.acceptance vermiyor'
        eksik = [k for k, v in acc.items()
                 if not _gorunur('risk_assessment.risk_matrix.acceptance.'
                                 + k, v, safety_bolgeleri)]
        assert not eksik, (
            'risk matrisi renkli çiziliyor ama bandın NE TALEP ETTİĞİ '
            'ekranda yazmıyor; basılmayan bantlar: ' + repr(eksik))

    def test_uyum_beyan_kodu_ekranda(self, safety_yaniti, safety_ekrani):
        comp = (safety_yaniti['safety_analysis'].get('compliance') or {})
        kod = comp.get('disclaimer_code')
        assert kod, 'ölçüm tabanı çürüdü: uç disclaimer_code vermiyor'
        assert kod in safety_ekrani['text'], (
            'ekrandaki uygunluk cümlesinin ucun beyanı mı güvertenin kendi '
            'metni mi olduğu okunamıyor: ' + repr(kod) + ' ekranda yok')

    def _sagir_yapraklar(self, safety_yaniti, safety_bolgeleri):
        sa = safety_yaniti['safety_analysis']
        toplam, sagir = 0, {}
        for yol, v in _yapraklar(sa):
            g = _gorunur(yol, v, safety_bolgeleri)
            if g is None:
                continue
            toplam += 1
            if not g:
                sagir[yol] = v
        return toplam, sagir

    def test_ucun_hicbir_guvenlik_yapragi_sagir_degil(self, safety_yaniti,
                                                      safety_bolgeleri):
        """Tam süpürme: ``safety_analysis``ın her yaprağı ekranda.

        Tek istisna ``GUVENLIK_YAPRAK_BORCU``dur: orada her satır alanı
        GETİREN D26 aşamasını ve commit'ini adıyla yazar. Envanter dışı
        bir kör yaprak doğarsa bekçi yine kırmızı yanar.
        """
        toplam, sagir = self._sagir_yapraklar(safety_yaniti,
                                              safety_bolgeleri)
        assert toplam >= 200, (
            'ölçüm tabanı çürüdü: uç artık ' + str(toplam) + ' yaprak '
            'yayımlıyor (ölçümde 283, D26 sonrası 297 idi) — süpürme '
            'kusuru gösteremez')
        kayitsiz = sorted(set(sagir) - set(GUVENLIK_YAPRAK_BORCU))
        assert not kayitsiz, (
            str(len(kayitsiz)) + '/' + str(toplam) + ' güvenlik yaprağı '
            'ekrana inmiyor ve adlı borç kaydı da YOK:\n  '
            + '\n  '.join(y + ' = ' + repr(sagir[y]) for y in kayitsiz))

    def test_yaprak_borcu_olu_satir_tasimaz(self, safety_yaniti,
                                            safety_bolgeleri):
        """Borç TEK YÖNLÜDÜR: ödenen ya da düşen satır kalkmak ZORUNDA."""
        _toplam, sagir = self._sagir_yapraklar(safety_yaniti,
                                               safety_bolgeleri)
        yayimlanan = {yol for yol, _v in
                      _yapraklar(safety_yaniti['safety_analysis'])}
        # ÖH D28 / OH-D27-17: şart 'D26' değil, KAYNAĞI ADLANDIRAN bir
        # dalga kodudur. fix-26b'nin ``'D26' in neden`` çakması, D26'dan
        # ESKİ kusurların (kap geometrisi) envantere girmesini engelliyordu
        # — kural "anonim af yok"tur, "yalnız D26 borcu" değil.
        bos = [y for y, neden in GUVENLIK_YAPRAK_BORCU.items()
               if not str(neden).strip()
               or not re.search(r'\bD\d{1,2}\b', str(neden))]
        assert not bos, (
            'borç satırı alanı GETİREN dalgayı (ör. ``D26``) adıyla '
            'yazmıyor: ' + repr(bos))
        dusen = sorted(set(GUVENLIK_YAPRAK_BORCU) - yayimlanan)
        assert not dusen, (
            'borç listesinde ucun artık yayımlamadığı yaprak var (alan '
            'düştüyse borç da düşer): ' + repr(dusen))
        odenmis = sorted(set(GUVENLIK_YAPRAK_BORCU) - set(sagir))
        assert not odenmis, (
            'şu yapraklar ARTIK EKRANDA, yani borç ödendi — satırı '
            'GUVENLIK_YAPRAK_BORCU\'ndan kaldır: ' + repr(odenmis))

    # ÖH D28 / arayuz a1 (OH-D27-16): xfail(strict) BORÇ İMİ KALDIRILDI.
    # Kusur giderildi (ölçüm: a1/once.json -> a1/sonra.json, addBlastRow
    # gövdesinde iki künye adı 0 -> 2), im XPASS(strict) ile kırmızı
    # verdiği için sökülmek ZORUNDAYDI. Bekçi artık CANLIdır: okuyucu
    # künyeyi yeniden bırakırsa test kırmızı verir. İm AD DÜZEYİNDEDİR,
    # yani süpürmenin sayı çakışmasından etkilenmez.
    def test_patlama_kunyesi_panel_okuyucusunda(self):
        kaynak = (REPO_ROOT / 'hrma/static/js/panels/safety_panel.js'
                  ).read_text(encoding='utf-8')
        govde = kaynak[kaynak.index('function addBlastRow'):]
        govde = govde[:govde.index('function addQdRow')]
        eksik = [ad for ad in ('basis', 'scaled_distance_m_per_kg13')
                 if ad not in govde]
        assert not eksik, (
            'patlama mesafesi okuyucusu şu künye alanlarını hiç okumuyor: '
            + repr(eksik))
