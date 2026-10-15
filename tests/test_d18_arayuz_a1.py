# -*- coding: utf-8 -*-
"""ÖH D18 · kulvar ARAYUZ · aşama 1 — onarım bekçileri.

Kapsanan defter kalemleri:

* **P11S1-03** (Fable-D15/D16 ŞART) — ``protection_panel.js`` yüzey enerji
  dengesi dalında hükmü taşıyan çiftin (``h_gas_W_m2K`` / ``T_recovery_K``)
  yalnız VARLIĞINA bakıyordu, koşuma GİRİP GİRMEDİĞİNE değil. ÖLÇÜLDÜ
  (``docs/scofield/raw/OH/D18/arayuz/a1/once_p11s1_03.json``, taban
  ``9071a64``): güverte gövdesi uca kendi varsayılanlarını (3000 W/m²K,
  3200 K) gönderiyor, panel ise KNDX katı motorundan 16293,324454931333
  W/m²K · 1705,379604616662 K okuyor; iki çift uyuşmadığı hâlde künye
  ``computed`` basılıyor, metin "both read from solid · … station" diyor ve
  3,41 mm kazanılmış hüküm gibi yayımlanıyordu. Onarımdan sonra künye
  ``user``, ``data-tps-pair-match="false"``, kart ``—``.
* **D15-CFD-01** (Fable-D15 ŞART madde 2) — ``panel.cfd.*`` TR sözlüğünde
  "residual" terimi tek karşılığa bağlanır (``i18n_common.js``).

Yöntem: Flask ``test_client`` (port bağlanmaz) + node içinde GERÇEK panel
dosyası. Beklenen değerler elle yazılmaz; ucun O KOŞUMDAKİ yanıtından ve
motorun O KOŞUMDAKİ sonucundan türetilir.
"""

import copy
import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = KOK / 'hrma' / 'static' / 'js'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Uygulama yalnız geri döngü Host başlığına yanıt verir (DNS-rebinding kapısı)
HEADERS = {'Host': '127.0.0.1:8080'}

#: Güvertenin (analysis_dock) koruma paneli için gönderdiği gövde. h_gas ve
#: T_recovery SONLU varsayılanlar taşır (3000 / 3200) — bu yüzden HER
#: koşumda gönderilirler ve uç yüzey enerji dengesi yolunu açar.
GUVERTE_GOVDESI = {
    'mode': 'ablative', 'material': 'silica_phenolic', 'design_margin': 1.5,
    'burn_time_s': 10, 'h_gas_W_m2K': 3000, 'T_recovery_K': 3200,
}

#: Panelin katı motorda okuduğu istasyon (``MEASURED_FLUX_PATHS.solid``).
AFT_YOLU = ('cad_design', 'insulation_system', 'aft_insulation')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# node koşum takımı — sahte DOM, GERÇEK panel dosyası
# ---------------------------------------------------------------------------
PANEL_HARNESS = r"""
const fs = require('fs'), path = require('path'), vm = require('vm');
const [staticDir, payloadPath] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
function El(t) { this.tagName = String(t || 'div').toUpperCase();
  this.children = []; this.style = {}; this._a = {}; this.innerHTML = ''; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._a[k] = String(v); };
El.prototype.getAttribute = function (k) {
  return this._a[k] === undefined ? null : this._a[k]; };
El.prototype.querySelectorAll = function () { return []; };
const doc = { head: new El('head'), body: new El('body'),
  readyState: 'complete', createElement: function (t) { return new El(t); },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  getElementById: function () { return null; },
  addEventListener: function () {} };
const sb = { console: { log: function () {}, warn: function () {},
    error: function () {} },
  setTimeout: setTimeout, clearTimeout: clearTimeout,
  setInterval: setInterval, clearInterval: clearInterval,
  fetch: function () { return Promise.reject(new Error('ag yok')); },
  JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
  String: String, Boolean: Boolean, RegExp: RegExp, isFinite: isFinite,
  parseFloat: parseFloat, parseInt: parseInt, document: doc };
sb.window = sb; sb.globalThis = sb; vm.createContext(sb);
function run(f) { vm.runInContext(fs.readFileSync(f, 'utf8'), sb,
                                  { filename: f }); }
run(path.join(staticDir, 'analysis_dock.js'));
run(path.join(staticDir, 'panels/protection_panel.js'));
if (payload.motorResult) {
  try {
    sb.window.AnalysisDock.init({
      motorType: payload.motorType || 'hybrid',
      resultsProvider: function () { return payload.motorResult; } });
  } catch (e) { /* gercek DOM yok */ }
  const spec = sb.window.AnalysisDock._registry.filter(function (s) {
    return s.id === 'protection'; })[0];
  try { spec.fromResults(payload.motorResult); } catch (e) { /* yok */ }
}
const out = { okunanCift: sb.window.ProtectionPanel._lastFluxRead(),
              ekran: {} };
Object.keys(payload.responses || {}).forEach(function (ad) {
  const root = new El('div');
  sb.window.ProtectionPanel._renderAblative(payload.responses[ad], root);
  out.ekran[ad] = root.children.map(function (c) { return c.innerHTML; })
                              .join('');
});
process.stdout.write(JSON.stringify(out));
"""


def _node_kos(tmp_path, script, *args):
    f = tmp_path / 'kos_d18.js'
    f.write_text(script, encoding='utf-8')
    p = subprocess.run([NODE, str(f)] + [str(a) for a in args],
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, ('node altında çöktü:\n' + p.stderr[-3000:])
    return json.loads(p.stdout)


def _panel_ciz(tmp_path, responses, motor_result=None, motor_type=None):
    girdi = tmp_path / 'girdi_d18.json'
    girdi.write_text(json.dumps({'responses': responses,
                                 'motorResult': motor_result,
                                 'motorType': motor_type}), encoding='utf-8')
    return _node_kos(tmp_path, PANEL_HARNESS, STATIC_JS, girdi)


def _aft(motor_result):
    """Panelin katı motorda okuduğu izolasyon istasyonu."""
    cur = motor_result
    for k in AFT_YOLU:
        cur = (cur or {}).get(k) or {}
    return cur


# ===========================================================================
# P11S1-03 — hükmü taşıyan çiftin VARLIĞI değil, KOŞUMA GİRMESİ aranır
# ===========================================================================
class TestP11S1_03CiftinAyniligi:
    """Fable-D15/D16 ŞART: ``pairMeasured`` ölçütü ``lastFluxRead`` çiftinin
    varlığına değil, ucun YANKILADIĞI çiftle AYNILIĞINA bağlanır."""

    @pytest.fixture(scope='class')
    def kati_motor(self, client):
        proje = json.loads((KOK / 'examples'
                            / 'Example Solid KNDX BATES 75mm.hrma')
                           .read_text(encoding='utf-8'))
        r = client.post('/calculate_solid',
                        json=dict(proje['inputs']['fields']), headers=HEADERS)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        return r.get_json()

    @pytest.fixture(scope='class')
    def guverte_yaniti(self, client):
        """Güvertenin KENDİ varsayılan çiftiyle (3000/3200) uç yanıtı."""
        r = client.post('/api/thermal-protection',
                        json=dict(GUVERTE_GOVDESI, q_net_W_m2=2.0e6),
                        headers=HEADERS)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        return r.get_json()

    # -- zemin -------------------------------------------------------------
    def test_kusurun_dayanagi_hala_uretilebiliyor(self, kati_motor,
                                                  guverte_yaniti):
        """Bekçinin ZEMİNİ: güvertenin gönderdiği çift ile motorun kendi
        istasyonundaki çift GERÇEKTEN farklı, ve uç ikisini de yayımlıyor.
        Bu artık doğru değilse kalem yeniden ölçülmeli."""
        assert guverte_yaniti['flux_basis'] == 'surface_energy_balance', (
            'uç artık enerji dengesi yolunu açmıyor — ŞART bayat')
        # Uç GÖNDERİLEN çifti yankılıyor mu? (ölçüt bu yankıya dayanıyor)
        assert guverte_yaniti['h_gas_W_m2K'] == float(
            GUVERTE_GOVDESI['h_gas_W_m2K'])
        assert guverte_yaniti['T_recovery_K'] == float(
            GUVERTE_GOVDESI['T_recovery_K'])
        aft = _aft(kati_motor)
        assert isinstance(aft.get('h_gas_W_m2K'), float), (
            'katı motor artık aft_insulation h_gas yayımlamıyor — '
            'panelin okuduğu istasyon kaybolmuş, kalem yeniden ölçülmeli')
        assert isinstance(aft.get('T_recovery_K'), float)
        assert abs(aft['h_gas_W_m2K']
                   - float(GUVERTE_GOVDESI['h_gas_W_m2K'])) > 1.0, (
            'motorun çifti artık güverte varsayılanına eşit — kusurun '
            'zemini kalktı, ŞART yeniden ölçülmeli')

    # -- ŞART'IN KİLİDİ ----------------------------------------------------
    @node_gerekli
    def test_uyusmaz_cift_computed_basmaz(self, tmp_path, kati_motor,
                                          guverte_yaniti):
        """ÖLÇÜLEN KUSUR (once_p11s1_03.json): okunan çift (16293,32 ·
        1705,38) ile koşuma giren çift (3000 · 3200) uyuşmadığı hâlde künye
        ``computed`` basılıyor, "both read from solid · … station" deniyor
        ve 3,41 mm kazanılmış hüküm gibi yayımlanıyordu."""
        ciz = _panel_ciz(tmp_path, {'kati': guverte_yaniti},
                         motor_result=kati_motor, motor_type='solid')
        html = ciz['ekran']['kati']
        okunan = ciz['okunanCift']
        assert okunan and okunan.get('h_gas_W_m2K') is not None, (
            'panel motorun çiftini hiç okumamış — bekçi boşa dönerdi')

        kind = re.findall(r'data-tps-flux-kind="(\w+)"', html)
        assert kind == ['user'], (
            f'uyuşmaz çiftte künye {kind!r} — koşuma GİRMEMİŞ bir çift '
            'hükmün kaynağı gibi gösteriliyor')
        assert re.findall(r'data-tps-pair-match="(\w+)"', html) == ['false']
        assert re.findall(r'data-tps-earned="(\w+)"', html) == ['false']
        assert re.findall(r'data-tps-caller-used="(\w+)"', html) == ['false'], (
            'girilen akı kullanılmadığı hâlde caller kancası "false" değil')

        # Künye uyuşmazlığı ADIYLA söylüyor ve YALAN söylemiyor.
        assert 'differs from the pair read from' in html, (
            'ekran çift uyuşmazlığını söylemiyor')
        assert 'both read from' not in html, (
            'ekran hâlâ "both read from … station" diyor — koşuma girmeyen '
            'çifti okunmuş gibi gösteriyor')

        # FAIL-CLOSED: kazanılmamış sayı basılmaz.
        sayi = '%.2f' % guverte_yaniti['required_thickness_mm']
        assert sayi not in html, (
            f'kazanılmamış kalınlık ({sayi} mm) hâlâ kartta')

    @node_gerekli
    def test_cift_ortusuyorsa_kunye_computed(self, tmp_path, kati_motor,
                                             guverte_yaniti):
        """KARŞI UÇ (onarım fazla sıkı olmasın): çift ÖRTÜŞTÜĞÜNDE künye
        ``computed`` olur ve sayı basılır.

        Çifti hizalamak için motor sonucunun KOPYASINDA izolasyon
        istasyonu, ucun O KOŞUMDA gerçekten kullandığı çifte çekilir —
        pytest düzeyinde bir bağlam kurgusudur, ürün verisi değildir.
        """
        hizali = copy.deepcopy(kati_motor)
        aft = hizali['cad_design']['insulation_system']['aft_insulation']
        aft['h_gas_W_m2K'] = guverte_yaniti['h_gas_W_m2K']
        aft['T_recovery_K'] = guverte_yaniti['T_recovery_K']

        html = _panel_ciz(tmp_path, {'kati': guverte_yaniti},
                          motor_result=hizali,
                          motor_type='solid')['ekran']['kati']
        assert re.findall(r'data-tps-flux-kind="(\w+)"', html) == ['computed'], (
            'çift örtüştüğü hâlde künye "computed" değil — fail-closed '
            'ölçüt fazla sıkı, hüküm hiç kazanılamıyor')
        assert re.findall(r'data-tps-pair-match="(\w+)"', html) == ['true']
        assert re.findall(r'data-tps-earned="(\w+)"', html) == ['true']
        sayi = '%.2f' % guverte_yaniti['required_thickness_mm']
        assert sayi in html, 'kazanılmış hüküm sayı olarak basılmıyor'

    @node_gerekli
    def test_ucun_yankilamadigi_cift_kazanilmaz(self, tmp_path, kati_motor,
                                                guverte_yaniti):
        """Uç çifti YAYIMLAMIYORSA (eski/eksik yanıt) aynılık
        DOĞRULANAMAZ; fail-closed: hüküm kazanılmaz."""
        eksik = dict(guverte_yaniti)
        eksik['h_gas_W_m2K'] = None
        eksik['T_recovery_K'] = None
        html = _panel_ciz(tmp_path, {'kati': eksik},
                          motor_result=kati_motor,
                          motor_type='solid')['ekran']['kati']
        kind = re.findall(r'data-tps-flux-kind="(\w+)"', html)
        assert kind != ['computed'], (
            'uç çifti yayımlamadığı hâlde künye "computed" — doğrulanamayan '
            'aynılık kazanılmış sayılıyor')
        assert re.findall(r'data-tps-earned="(\w+)"', html) == ['false']

    @node_gerekli
    def test_motor_okunmadiysa_assumed_korunur(self, tmp_path,
                                               guverte_yaniti):
        """Gerileme yok: motor hiç okunmadığında künye ESKİSİ GİBİ
        ``assumed`` kalır (D16'da kazanılan davranış)."""
        html = _panel_ciz(tmp_path, {'kati': guverte_yaniti})['ekran']['kati']
        assert re.findall(r'data-tps-flux-kind="(\w+)"', html) == ['assumed']
        assert re.findall(r'data-tps-earned="(\w+)"', html) == ['false']


# ===========================================================================
# D15-CFD-01 (madde 2) — panel.cfd.* TR sözlüğünde "residual" TEK terim
# ===========================================================================
I18N_COMMON = STATIC_JS / 'i18n_common.js'

#: "residual" için TR sözlüğünde kullanılabilecek terim adayları.
#: ``artık`` Türkçede AYRICA zarftır ("bundan sonra") ve sözlükte o anlamda
#: da geçiyor (``panel.cfd.viz3dShown``); teknik terimi o sözcüğe bağlamak
#: aynı sözlükte iki anlamı çakıştırır.
RESIDUAL_TERIMLERI = {
    'kalıntı': r'kalıntı',
    'artık': r'\bartık|\bartığ',
    'rezidü': r'rezidü',
}
#: Tekleştirmenin bağlandığı terim (ÖH D18 · arayuz a1 kararı).
SECILEN_TERIM = 'kalıntı'


def _i18n_bolum(bas):
    """``i18n_common.js`` içinden bir dil bölümünün ``panel.cfd.*`` girdileri.

    Bölüm kapanışı hem ``\n        },`` (araya giren bölüm) hem
    ``\n        }`` (son bölüm) olabilir — ikisi de kabul edilir, yoksa
    son bölümün tamamı sessizce kuyruğa taşardı.
    """
    metin = I18N_COMMON.read_text(encoding='utf-8')
    i = metin.index(bas)
    kapanis = re.compile(r'\n        \},?\n')
    m = kapanis.search(metin, i)
    assert m, f'sözlük bölümü kapanışı bulunamadı: {bas!r}'
    return dict(re.findall(
        r"'(panel\.cfd\.[A-Za-z0-9_]+)':\s*'((?:[^'\\]|\\.)*)'",
        metin[i:m.start()]))


class TestD15CFD01ResidualTerimi:
    """Fable-D15 ŞART madde 2: ``panel.cfd.*`` TR sözlüğünde "residual"
    terimi tekleştirilir.

    ÖLÇÜLEN KUSUR (``once_d15cfd01.json``, taban ``9071a64``): İngilizcesinde
    ``residual`` geçen 17 anahtarın 9'u "kalıntı", 8'i "artık" diyordu —
    aynı panelde aynı büyüklük iki adla anılıyordu.
    """

    @pytest.fixture(scope='class')
    def sozlukler(self):
        return _i18n_bolum('        en: {'), _i18n_bolum('        tr: {')

    def test_zemin_terim_tasiyan_anahtarlar_duruyor(self, sozlukler):
        """Bekçinin ZEMİNİ: İngilizcesinde 'residual' geçen anahtarlar hâlâ
        var ve hepsinin TR karşılığı yazılı."""
        en, tr = sozlukler
        anahtarlar = [k for k, v in en.items()
                      if re.search(r'residual', v, re.I)]
        assert len(anahtarlar) >= 15, (
            f'yalnız {len(anahtarlar)} residual anahtarı kaldı — ŞART bayat')
        eksik = sorted(k for k in anahtarlar if k not in tr)
        assert not eksik, f'TR karşılığı olmayan residual anahtarları: {eksik}'

    def test_residual_terimi_tek(self, sozlukler):
        """TR sözlüğünde 'residual' TEK Türkçe terime bağlıdır."""
        en, tr = sozlukler
        kullanim = {t: [] for t in RESIDUAL_TERIMLERI}
        for k, v in en.items():
            if not re.search(r'residual', v, re.I):
                continue
            for t, kalip in RESIDUAL_TERIMLERI.items():
                if re.search(kalip, tr[k], re.I):
                    kullanim[t].append(k)
        kullanilan = {t: v for t, v in kullanim.items() if v}
        assert list(kullanilan) == [SECILEN_TERIM], (
            'panel.cfd.* TR sözlüğünde "residual" birden çok terime bağlı: '
            + json.dumps({t: sorted(v) for t, v in kullanilan.items()},
                         ensure_ascii=False))

    def test_artik_yalniz_zarf_olarak_kaliyor(self, sozlukler):
        """"artık" sözcüğü artık YALNIZ zarf anlamında geçer; hiçbir
        residual anahtarı ona bağlı değildir."""
        en, tr = sozlukler
        bagli = sorted(k for k, v in en.items()
                       if re.search(r'residual', v, re.I)
                       and re.search(RESIDUAL_TERIMLERI['artık'], tr[k], re.I))
        assert not bagli, (
            f'"artık" hâlâ residual terimi olarak kullanılıyor: {bagli}')


# ===========================================================================
# fea_panel.js — node koşum takımı (DOM'suz saf katman)
# ===========================================================================
FEA_HARNESS = r"""
const fs = require('fs'), path = require('path'), vm = require('vm');
const [staticDir, yukYolu] = process.argv.slice(2);
const yuk = JSON.parse(fs.readFileSync(yukYolu, 'utf8'));
function El(t) { this.tagName = String(t || 'div').toUpperCase();
  this.children = []; this.style = {}; this._a = {}; this.innerHTML = ''; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function () {};
El.prototype.getAttribute = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.addEventListener = function () {};
const doc = { head: new El('head'), body: new El('body'),
  readyState: 'complete', createElement: function (t) { return new El(t); },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  getElementById: function () { return null; },
  addEventListener: function () {} };
const sb = { console: { log: function () {}, warn: function () {},
    error: function () {} },
  setTimeout: setTimeout, clearTimeout: clearTimeout,
  setInterval: setInterval, clearInterval: clearInterval,
  fetch: function () { return Promise.reject(new Error('ag yok')); },
  JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
  String: String, Boolean: Boolean, RegExp: RegExp, isFinite: isFinite,
  parseFloat: parseFloat, parseInt: parseInt, document: doc };
sb.window = sb; sb.globalThis = sb; vm.createContext(sb);
vm.runInContext(fs.readFileSync(path.join(staticDir, 'analysis_dock.js'),
                                'utf8'), sb, { filename: 'analysis_dock.js' });
// ÖH D25 · arayuz a3 — SAYFANIN GERÇEK YÜKLEME SIRASI TAKLİT EDİLİR.
// ÖLÇÜLDÜ (a3 sembol taraması): aşama-2'nin OH-D24-05 onarımı
// PA_PER_BAR'ı units_constants.js'te TEK KAYNAĞA aldı ve paneller
// sabiti yeniden tanımlamak yerine o dosyayı ZORUNLU kıldı
// (fail-closed: yoksa fırlatır). Üç şablon da units_constants.js'i
// panellerden ÖNCE yükler (advanced 717<729/771, liquid 7363<7441/7501,
// solid 424<6493/6634); bu koşum takımı yüklemiyordu ve panel
// node altında fırlatıyordu. Ürün davranışı DEĞİŞMEDİ — koşum takımı
// sayfanın sırasına hizalandı.
vm.runInContext(fs.readFileSync(path.join(staticDir,
                                'units_constants.js'), 'utf8'), sb,
                { filename: 'units_constants.js' });
vm.runInContext(fs.readFileSync(path.join(staticDir, 'fea_panel.js'), 'utf8'),
                sb, { filename: 'fea_panel.js' });
const P = sb.window.FeaPanel, CT = sb.window.FeaCenterTenants;
const out = { sfScale: P._sfScale || null };
if (yuk.grainYanit) {
  out.grainVerdict = CT.planarGrain.verdict(yuk.grainYanit);
  const b = (yuk.grainYanit.fea || {}).bore || {};
  out.strainMarginKind = CT._strainMarginKind(b.strain_margin);
}
if (yuk.feaYanit) {
  const model = P.buildViewModel(yuk.feaYanit.fea);
  const alan = model.safety_factor;
  out.sfAlanVar = !!alan;
  if (alan) {
    let mn = Infinity, mx = -Infinity;
    alan.forEach(function (s) { s.forEach(function (v) {
      if (typeof v === 'number' && isFinite(v)) {
        if (v < mn) mn = v; if (v > mx) mx = v; } }); });
    out.sfMin = mn; out.sfMax = mx;
    // SF haritası ÜRÜN KAPISINDAN çizilir (çapa argüman değil).
    const fig = P._sfFieldFigure(model, alan, 't', 'c', 'feaCarpetSf');
    const iz = fig.traces.filter(function (t) {
      return t.type === 'contourcarpet'; })[0] || {};
    out.konturIz = { zauto: iz.zauto === undefined ? null : iz.zauto,
                     zmin: iz.zmin === undefined ? null : iz.zmin,
                     zmax: iz.zmax === undefined ? null : iz.zmax };
    const yedek = P._sfFieldFallbackFigure(model, alan, 't', 'c');
    const m = (yedek.traces[0] || {}).marker || {};
    out.yedekIz = { cauto: m.cauto === undefined ? null : m.cauto,
                    cmin: m.cmin === undefined ? null : m.cmin,
                    cmax: m.cmax === undefined ? null : m.cmax };
    // Çapasız çağrı (eski davranış) hâlâ mümkün mü? — geriye uyum.
    const capasiz = P._fieldFigure(model, alan, 't', 'c',
      P._sfScale.colorscale, 'feaCarpetSf');
    const iz2 = capasiz.traces.filter(function (t) {
      return t.type === 'contourcarpet'; })[0] || {};
    out.capasizIz = { zauto: iz2.zauto === undefined ? null : iz2.zauto,
                      zmin: iz2.zmin === undefined ? null : iz2.zmin };
  }
}
process.stdout.write(JSON.stringify(out));
"""


def _fea_kos(tmp_path, yuk):
    (tmp_path / 'yuk_fea.json').write_text(json.dumps(yuk), encoding='utf-8')
    f = tmp_path / 'kos_fea.js'
    f.write_text(FEA_HARNESS, encoding='utf-8')
    p = subprocess.run([NODE, str(f), str(STATIC_JS),
                        str(tmp_path / 'yuk_fea.json')],
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, ('node altında çöktü:\n' + p.stderr[-3000:])
    return json.loads(p.stdout)


#: Panelin ``grainParamsFromResults`` deseniyle kurulan tane uç gövdesi.
GRAIN_GOVDESI = {
    'grain_type': 'star', 'propellant_type': 'apcp',
    'outer_diameter_mm': 98.0, 'core_diameter_mm': 32.0,
    'chamber_pressure_bar': 45.0, 'grain_length_mm': 420.0,
    'star_points': 6, 'star_radius': 12.5,
}


# ===========================================================================
# P11B3-02 [kritik] — oturmamış kabul ölçütüne YEŞİL hüküm yok
# ===========================================================================
class TestP11B3_02OturmamisOlcuteYesilYok:

    @pytest.fixture(scope='class')
    def grain_yaniti(self, client):
        r = client.post('/api/fea/planar-grain', json=GRAIN_GOVDESI,
                        headers=HEADERS)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        return r.get_json()

    def test_zemin_kabul_olcutu_hala_yakinsamiyor(self, grain_yaniti):
        """Bekçinin ZEMİNİ: uç bu kesitte kabul ölçütünü YAKINSAMAMIŞ
        ilan ediyor ve marj YEŞİL eşiğin üstünde. İkisi birden doğru
        değilse kalemin ölçümü bayat."""
        fea = grain_yaniti['fea']
        acc = (fea.get('convergence') or {}).get('acceptance')
        assert isinstance(acc, dict), (
            'uç artık acceptance bloğu yayımlamıyor — kalem yeniden ölçülmeli')
        assert acc.get('converged') is False, (
            f'kabul ölçütü artık yakınsıyor ({acc!r}) — ölçüm bayat')
        assert acc['rel_change'] > acc['tol'], (
            'değişim tolerans içinde — kusurun zemini kalktı')
        marj = (fea.get('bore') or {}).get('strain_margin')
        assert isinstance(marj, float) and marj >= 2.0, (
            f'marj {marj!r} artık yeşil eşikte değil — ölçüm bayat')

    @node_gerekli
    def test_merkez_satiri_yesil_basmaz(self, tmp_path, grain_yaniti):
        """ÖLÇÜLEN KUSUR (once_p11b3_02.json): kabul ölçütü toleransın
        34,49 KATI oynarken Merkez satır hükmü {kind:'ok'} YEŞİL
        "STRAIN MARGIN 41.60" basıyor, yakınsamama satırda TEK KELİMEYLE
        geçmiyordu."""
        r = _fea_kos(tmp_path, {'grainYanit': grain_yaniti})
        v = r['grainVerdict']
        assert v is not None, 'hüküm hiç üretilmiyor — bekçi boşa dönerdi'
        assert r['strainMarginKind'] == 'ok', (
            'marj tek başına artık yeşil değil — kusurun zemini kalktı')
        assert v['kind'] != 'ok', (
            f"kabul ölçütü yakınsamadığı hâlde Merkez satırı {v['kind']!r} "
            '(YEŞİL) hüküm basıyor')
        acc = grain_yaniti['fea']['convergence']['acceptance']
        p = v.get('params') or {}
        assert p.get('q') == acc['quantity'], (
            'hüküm hangi ölçütün oturmadığını adıyla söylemiyor')
        assert p.get('pct') == '%.2f%%' % (100 * acc['rel_change']), (
            f"hükümdeki değişim {p.get('pct')!r} ucun sayısından türemiyor")
        assert p.get('tol') == '%.2f%%' % (100 * acc['tol'])

    @node_gerekli
    def test_kirmizi_hukum_yumusatilmaz(self, tmp_path, grain_yaniti):
        """Gerileme kapısı: marj < 1 iken (akma aşıldı) yakınsamama
        gerekçesiyle KIRMIZI 'warn'a düşürülmez."""
        kirmizi = copy.deepcopy(grain_yaniti)
        kirmizi['fea']['bore']['strain_margin'] = 0.5
        r = _fea_kos(tmp_path, {'grainYanit': kirmizi})
        assert r['grainVerdict']['kind'] == 'err', (
            'akmanın aşıldığı hüküm yakınsamama gerekçesiyle yumuşatılmış')

    @node_gerekli
    def test_yakinsayan_olcutte_davranis_ayni(self, tmp_path, grain_yaniti):
        """Geriye uyum: kabul ölçütü OTURDUĞUNDA hüküm eski anahtarıyla
        ve eski türüyle basılır."""
        oturmus = copy.deepcopy(grain_yaniti)
        oturmus['fea']['convergence']['acceptance']['converged'] = True
        r = _fea_kos(tmp_path, {'grainYanit': oturmus})
        v = r['grainVerdict']
        assert v['kind'] == 'ok'
        assert v['key'] == 'panel.grain.verdictMargin'


# ===========================================================================
# P11B3-04 [yüksek] — SF kontur skalası MUTLAK çapalı
# ===========================================================================
class TestP11B3_04SFSkalasiMutlakCapali:

    @pytest.fixture(scope='class')
    def fea_yaniti(self, client):
        rm = client.post('/calculate', headers=HEADERS, json={
            'motor_name': 'p11', 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
            'thrust': 2000, 'burn_time': 10, 'chamber_pressure': 30,
            'of_ratio': 6.0})
        assert rm.status_code == 200, rm.get_data(as_text=True)[:400]
        r = client.post('/api/fea/structural', headers=HEADERS, json={
            'motor_results': (rm.get_json() or {}).get('motor'),
            'n_axial0': 12, 'n_radial0': 4, 'max_rounds': 2})
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        return r.get_json()

    @node_gerekli
    def test_sf_izi_mutlak_capa_tasiyor(self, tmp_path, fea_yaniti):
        """ÖLÇÜLEN KUSUR (once_p11b3_04.json, taban): kaynakta
        cmin/cmax/zmin/zmax/zauto/cauto anahtarlarının HEPSİ 0 kez geçiyor;
        SF alanı 34,28 … 105,18 iken (3,07 kat) en düşük hücre KIRMIZI, en
        yüksek YEŞİL boyanıyordu — ikisi de akmanın 34+ katı emniyetli."""
        r = _fea_kos(tmp_path, {'feaYanit': fea_yaniti})
        assert r['sfAlanVar'], 'SF alanı yayımlanmıyor — bekçi boşa dönerdi'
        iz = r['konturIz']
        assert iz['zauto'] is False, 'kontur izi hâlâ otomatik ölçekli'
        assert iz['zmin'] == 0 and iz['zmax'] == r['sfScale']['scaleMax'], (
            f'kontur çapası {iz!r} skalanın kendi sınırlarından gelmiyor')
        yed = r['yedekIz']
        assert yed['cauto'] is False and yed['cmin'] == 0, (
            f'carpet yedeği çapasız kalmış: {yed!r} — aynı renk başka anlama '
            'gelir')
        assert yed['cmax'] == iz['zmax']

    @node_gerekli
    def test_duraklar_esiklerden_turuyor(self, tmp_path, fea_yaniti):
        """TEK KAYNAK: renk durakları rozetin eşiklerinden hesaplanır;
        kırmızı "akma aşıldı", yeşil "kabul" demektir."""
        r = _fea_kos(tmp_path, {'feaYanit': fea_yaniti})
        s = r['sfScale']
        assert s['errMax'] == 1.0 and s['okMin'] == 1.5, (
            f'eşikler rozetinkinden ayrılmış: {s!r}')
        assert s['scaleMax'] == 2 * s['okMin']
        duraklar = {round(d[0], 6): d[1] for d in s['colorscale']}
        assert duraklar[round(s['errMax'] / s['scaleMax'], 6)] == '#ff5d73', (
            'SF = 1 durağı kırmızının sonu değil — akma sınırı skalada yok')
        assert duraklar[round(s['okMin'] / s['scaleMax'], 6)] == '#ffcf5c'
        assert duraklar[0.0] == '#ff5d73' and duraklar[1.0] == '#2dd4a8'

    @node_gerekli
    def test_capasiz_cagri_eski_davranisi_korur(self, tmp_path, fea_yaniti):
        """Geriye uyum: çapa VERİLMEYEN alanlarda (von Mises) figür
        birebir eskisi gibi otomatik ölçekli kalır."""
        r = _fea_kos(tmp_path, {'feaYanit': fea_yaniti})
        assert r['capasizIz'] == {'zauto': None, 'zmin': None}, (
            f'çapasız çağrıya çapa sızmış: {r["capasizIz"]!r}')

    # ------------------------------------------------------------------
    # ÖH D20 · P11B3-04 — Fable-D18 ŞARTI: rozet ⟷ skala TEK KAYNAK
    # ------------------------------------------------------------------
    # ÖLÇÜLEN KUSUR (`raw/OH/D20/arayuz/a1/once_p11b3_04.json`, taban
    # 14acd1d): `_sfScale` yalnız SABİTLERİ (errMax=1,0 / okMin=1,5) dışa
    # vuruyordu; eşik KARARINI veren satır (`sf < SF_ERR_MAX ? ... :
    # sf < SF_OK_MIN ? ...`) hiçbir yerden okunamıyordu. Sabitler yerinde
    # dururken karar satırındaki gömülü sayıya kayan bir mutasyon
    # (`sf < 1.2`) bütün mevcut bekçilerden geçiyordu: harita 1,5'te yeşile
    # dönerken rozet 1,2'de yeşile dönerdi ve kullanıcı haritasıyla
    # çelişen bir hüküm görürdü. Bekçi artık kararı İKİ yoldan okur:
    # (a) saf kapı `_sfScale.badgeKind`, (b) ürün yolu `_renderBadges`in
    # bastığı `data-badge`. Sınırlar elle yazılmaz, `_sfScale`ten türer.

    @node_gerekli
    def test_rozet_esigi_skala_esiginden_turuyor(self, tmp_path):
        r = _sf_rozet_kos(tmp_path)
        assert r['badgeKindDisaVurulmus'], (
            'eşik kararı tek fonksiyona alınmamış: _sfScale.badgeKind yok')
        eps = 1e-9
        s = r['sinirlar']
        assert s['errMax-eps'] == 'err', (
            f"akma sınırının {eps} altı 'err' değil: {s!r}")
        assert s['errMax'] == 'warn', (
            f"akma sınırının kendisi 'warn' değil: {s!r}")
        assert s['okMin-eps'] == 'warn', (
            f"kabul eşiğinin {eps} altı 'warn' değil: {s!r} — rozet, "
            'haritanın sarı boyadığı yerde yeşil diyor')
        assert s['okMin'] == 'ok', (
            f"kabul eşiğinin kendisi 'ok' değil: {s!r}")

    @node_gerekli
    def test_ekrandaki_rozet_ayni_sinirda_donuyor(self, tmp_path):
        """Saf kapı ile ÜRÜN yolu ayrışamaz: renderBadges'in bastığı
        `data-badge` aynı sınırda aynı türü vermeli."""
        r = _sf_rozet_kos(tmp_path)
        assert r['renderBadgesDisaVurulmus'], (
            'renderBadges ölçülebilir değil — ürün yolu bekçisiz')
        assert r['ekranSinirlari'] == r['sinirlar'], (
            'rozet HTML’i eşik kapısından ayrışmış: '
            f"ekran={r['ekranSinirlari']!r} kapı={r['sinirlar']!r}")

    @node_gerekli
    def test_esikler_haritanin_duraklarindan_ayrilamaz(self, tmp_path):
        """Rozetin eşiği ile kontur durakları AYNI sayılardan doğar."""
        r = _sf_rozet_kos(tmp_path)
        assert r['errMax'] == 1.0 and r['okMin'] == 1.5, (
            f'eşikler kaymış: {r!r}')


SF_ROZET_HARNESS = r"""
const fs = require('fs'), path = require('path'), vm = require('vm');
const [staticDir] = process.argv.slice(2);
function El(t) { this.tagName = String(t || 'div').toUpperCase();
  this.children = []; this.style = {}; this.innerHTML = ''; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function () {};
El.prototype.getAttribute = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.addEventListener = function () {};
const doc = { head: new El('head'), body: new El('body'),
  readyState: 'complete', createElement: function (t) { return new El(t); },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  getElementById: function () { return null; },
  addEventListener: function () {} };
const sb = { console: { log: function () {}, warn: function () {},
    error: function () {} },
  setTimeout: setTimeout, clearTimeout: clearTimeout,
  setInterval: setInterval, clearInterval: clearInterval,
  fetch: function () { return Promise.reject(new Error('ag yok')); },
  JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
  String: String, Boolean: Boolean, RegExp: RegExp, isFinite: isFinite,
  parseFloat: parseFloat, parseInt: parseInt, document: doc };
sb.window = sb; sb.globalThis = sb; vm.createContext(sb);
vm.runInContext(fs.readFileSync(path.join(staticDir, 'analysis_dock.js'),
                                'utf8'), sb, { filename: 'analysis_dock.js' });
// ÖH D25 · arayuz a3 — SAYFANIN GERÇEK YÜKLEME SIRASI TAKLİT EDİLİR.
// ÖLÇÜLDÜ (a3 sembol taraması): aşama-2'nin OH-D24-05 onarımı
// PA_PER_BAR'ı units_constants.js'te TEK KAYNAĞA aldı ve paneller
// sabiti yeniden tanımlamak yerine o dosyayı ZORUNLU kıldı
// (fail-closed: yoksa fırlatır). Üç şablon da units_constants.js'i
// panellerden ÖNCE yükler (advanced 717<729/771, liquid 7363<7441/7501,
// solid 424<6493/6634); bu koşum takımı yüklemiyordu ve panel
// node altında fırlatıyordu. Ürün davranışı DEĞİŞMEDİ — koşum takımı
// sayfanın sırasına hizalandı.
vm.runInContext(fs.readFileSync(path.join(staticDir,
                                'units_constants.js'), 'utf8'), sb,
                { filename: 'units_constants.js' });
vm.runInContext(fs.readFileSync(path.join(staticDir, 'fea_panel.js'), 'utf8'),
                sb, { filename: 'fea_panel.js' });
const P = sb.window.FeaPanel, S = P._sfScale || {};
const out = { sfScaleVar: !!P._sfScale,
  errMax: S.errMax === undefined ? null : S.errMax,
  okMin: S.okMin === undefined ? null : S.okMin,
  badgeKindDisaVurulmus: typeof S.badgeKind === 'function',
  renderBadgesDisaVurulmus: typeof P._renderBadges === 'function' };
const EPS = 1e-9;
if (out.badgeKindDisaVurulmus) {
  out.sinirlar = { 'errMax-eps': S.badgeKind(S.errMax - EPS),
                   'errMax': S.badgeKind(S.errMax),
                   'okMin-eps': S.badgeKind(S.okMin - EPS),
                   'okMin': S.badgeKind(S.okMin) };
}
function ekrandanTur(sf) {
  const el = new El('div');
  P._renderBadges(el, { mesh_info: { n_elems: 10, n_nodes: 20 },
    scalars: { von_mises_max_mpa: 100, min_safety_factor: sf,
               headline_source: null },
    motor_karsilastirma: null, convergence: null, flags: null });
  const parcalar = String(el.innerHTML).split('<span data-badge="');
  for (let i = 1; i < parcalar.length; i++) {
    if (parcalar[i].indexOf('SAFETY FACTOR') !== -1) {
      return parcalar[i].slice(0, parcalar[i].indexOf('"'));
    }
  }
  return null;
}
if (out.renderBadgesDisaVurulmus && S.okMin !== undefined) {
  out.ekranSinirlari = { 'errMax-eps': ekrandanTur(S.errMax - EPS),
                         'errMax': ekrandanTur(S.errMax),
                         'okMin-eps': ekrandanTur(S.okMin - EPS),
                         'okMin': ekrandanTur(S.okMin) };
}
process.stdout.write(JSON.stringify(out));
"""


def _sf_rozet_kos(tmp_path):
    """P11B3-04 ŞART bekçisi: sunucu GEREKTİRMEZ (saf JS katmanı)."""
    f = tmp_path / 'kos_sf_rozet.js'
    f.write_text(SF_ROZET_HARNESS, encoding='utf-8')
    p = subprocess.run([NODE, str(f), str(STATIC_JS)],
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, ('node altında çöktü:\n' + p.stderr[-3000:])
    return json.loads(p.stdout)
