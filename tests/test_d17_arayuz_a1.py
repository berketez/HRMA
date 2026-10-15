# -*- coding: utf-8 -*-
"""ÖH Dalga-17 / kulvar arayuz, aşama 1 — bekçiler.

Kapsanan defter kalemleri (ölçüm: ``docs/scofield/raw/OH/D17/arayuz/a1/``):

* **P17H1-01 ≡ H2-Y1** [kritik] ``advanced.html:updateMixtureDensity``
  paylaşılan motor alanlarını (``fuel_density``, ``regression_a``,
  ``regression_n``) SEÇİLİ YAKIT TİPİNE BAKMADAN eziyordu ve
  ``I18N.onChange`` onu her dil değişiminde çağırıyordu. ÖLÇÜLDÜ
  (``once.json`` M9, ürün kodu node içinde koşuldu): HTPB seçili bir
  kullanıcı dil düğmesine bastığında ``fuel_density`` 920 → **1640**
  kg/m³, ``regression_a`` 3,68e-5 → **9,590e-5**, ``regression_n``
  0,555 → 0,549 oluyordu.
* **P11B2-24** [yüksek] ``exportReport`` içerik kapısı düştüğünde YALNIZ
  ``console.warn`` yazıp sessizce metin yedeğine düşüyordu.
* **P11B1-03** [yüksek] ``solid.html`` / ``liquid.html`` 3B adaptörleri
  ``structural_analysis`` bloğunu viz sözlüğüne geçirmiyor, sahne
  ``max(4, 0,045·D)`` geometrik yedeğine düşüyordu (ölçüldü: çözücü
  2,9943 mm ⟷ sahne 5,6143 mm, 1,875×).
* **OH-Z1-02** [orta] ``OX_REF_DENSITY`` sayı tablosu ``simple.html`` ve
  ``uzaytek.html`` içinde KOPYA duruyordu.
  (Bekçisi ÖH D36'da iki sayfayla birlikte emekli — Berke 23 Eyl,
  dalga36/sokum.)
* **P15B3-03** [yüksek] CEA hüküm/künye cümleleri İngilizce sabit olarak
  yazılıydı (D16 aşaması sözlüğe yazamamıştı).
* **P12bB2-02** [yüksek] (Fable-D15 ŞARTI) deniz-seviyesi sayfa yükünün
  ``/calculate_solid``'te 200 döndüğünü ölçen CANLI bekçi.
* **P11B1-04** / **P12bB2-02** kanıt hijyeni: D15 raporlarındaki sayılar
  kendi JSON'larıyla / ölçülen değerle hizalı.

Yöntem: ürün dosyalarının kendi kaynağı + node içinde GERÇEK koşum +
Flask ``test_client`` ile CANLI uç. İddialar ürün sabitlerinden
TÜRETİLMEZ; beklenen değerler ucun o koşumdaki yanıtından okunur.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
STATIC = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates'
ADVANCED = SABLON / 'advanced.html'
SOLID = SABLON / 'solid.html'
LIQUID = SABLON / 'liquid.html'
APP_JS = STATIC / 'app.js'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(
    NODE is None,
    reason='node kurulu değil — ürün JS\'ini gerçek koşumda ölçen '
           'bekçiler koşamaz (kurulum: `brew install node`)')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _fn(src, ad):
    """Kaynaktan ``function ad(...) { ... }`` gövdesini ayıklar."""
    i = src.find('function ' + ad + '(')
    if i < 0:
        return None
    d = 0
    for j in range(src.index('{', i), len(src)):
        if src[j] == '{':
            d += 1
        elif src[j] == '}':
            d -= 1
            if d == 0:
                return src[i:j + 1]
    return None


def _node(tmp_path, kod, *argv):
    f = tmp_path / 'kos_d17.js'
    f.write_text(kod, encoding='utf-8')
    p = subprocess.run([NODE, str(f)] + [str(a) for a in argv],
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, 'node çöktü:\n' + p.stderr[-3000:]
    return json.loads(p.stdout)


# ===========================================================================
# P17H1-01 ≡ H2-Y1 [kritik] — dil düğmesi motor girdisini değiştiremez
# ===========================================================================
ZINCIR_HARNESS = r"""
'use strict';
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const m = src.match(
    /if \(I18N\.onChange\) I18N\.onChange\(function \(\) \{([\s\S]*?)\n            \}\);/);
if (!m) { process.stdout.write(JSON.stringify({HATA: 'zincir yok'})); process.exit(0); }
const cagrilar = [];
const alanlar = {
    fuel_type: { value: 'htpb' },
    fuel_density: { value: '920' },
    regression_a: { value: '3.68e-5' },
    regression_n: { value: '0.555' }
};
const document = { getElementById: (id) => alanlar[id] || null };
function updateInjectorParams() { cagrilar.push('inj'); }
function refreshPressureModeLabels() { cagrilar.push('prs'); }
function updateCalculatedImpulse() { cagrilar.push('imp'); }
function checkDatabaseStatus() { cagrilar.push('db'); }
const uyari = [];
const console = { warn: (a, b) => uyari.push(String(a) + ' ' + String(b)) };
eval(m[1]);
process.stdout.write(JSON.stringify({
    cagrilar: cagrilar, uyari: uyari,
    fuel_density: alanlar.fuel_density.value,
    regression_a: alanlar.regression_a.value,
    regression_n: alanlar.regression_n.value
}));
"""


@node_gerekli
class TestP17H101DilDugmesiMotorGirdisi:
    """ÇEVRİLDİ (ÖH D33-KOLAY · OH-D32-11) — dil değişimi artık FIRLATMIYOR.

    ESKİ SÖZLEŞME (``KARISIM_HARNESS``): ``updateMixtureDensity()`` node
    altında koşturulup paylaşılan motor alanlarını ezmediği ve karışım
    panelinin kendi göstergesini tazelediği ölçülüyordu. Bu sözleşme ölü
    fonksiyonun sayfada DURMASINI şart koşuyordu — kusuru koruyan bekçi.

    ÖLÇÜLDÜ (raw/OH/D33/arayuz-panel/a1/once.json · M2b, ürün kodu node
    içinde koşuldu): fonksiyonun okuduğu karışım paneli OH-D31-05'te
    sökülmüştü; her dil değişiminde ``null.value`` TypeError'ı fırlıyor,
    ``catch`` onu yutuyor ve ZİNCİR KESİLİYORDU — çağrı dizisi
    ``['inj','prs','imp']``, yani ``checkDatabaseStatus()`` HİÇ
    çalışmıyordu.

    YENİ SÖZLEŞME: fonksiyon SİLİNDİ. Kalemin koruduğu iki şey CANLI
    koşumla kilitlenir — (1) dil değişimi paylaşılan motor alanlarını
    ezmez, (2) zincir sonuna kadar yürür (fırlatma yok).
    """

    def _zincir(self, tmp_path):
        return _node(tmp_path, ZINCIR_HARNESS, ADVANCED)

    def test_olu_karisim_fonksiyonlari_sokuldu(self):
        kod = re.sub(r'<!--.*?-->', '',
                     ADVANCED.read_text(encoding='utf-8'), flags=re.S)
        for ad in ('updateMixtureDensity', 'addCompositionRow',
                   'removeCompositionRow', 'validateComposition'):
            assert not re.search(r'function %s\s*\(' % ad, kod), (
                '%s geri geldi (OH-D32-11: erişilemez panel okuyan ölü '
                'fonksiyon)' % ad)

    def test_dil_degisimi_paylasilan_alanlari_ezmiyor(self, tmp_path):
        o = self._zincir(tmp_path)
        assert (o['fuel_density'], o['regression_a'], o['regression_n']) == \
            ('920', '3.68e-5', '0.555'), (
                'dil düğmesi paylaşılan motor girdilerini ezdi: '
                + json.dumps(o, ensure_ascii=False))

    def test_dil_degisimi_zinciri_kesilmiyor(self, tmp_path):
        o = self._zincir(tmp_path)
        assert o['cagrilar'] == ['inj', 'prs', 'imp', 'db'], (
            'zincir kesildi (ölçülen kusur): %r' % (o['cagrilar'],))
        assert o['uyari'] == [], ('zincir hâlâ fırlatıyor: %r'
                                 % (o['uyari'],))

    def test_dil_geri_cagirimi_olu_fonksiyonu_cagirmiyor(self):
        """Kusurun kanalı KAPATILDI (eskiden yalnız zararsızlaştırılmıştı)."""
        src = re.sub(r'<!--.*?-->', '',
                     ADVANCED.read_text(encoding='utf-8'), flags=re.S)
        src = re.sub(r'//[^\n]*', '', src)
        assert not re.search(r'onChange[\s\S]{0,900}?updateMixtureDensity',
                             src), (
            'fırlatan ölü çağrı dil geri çağırımına geri kondu')


# ===========================================================================
# P11B2-24 [yüksek] — PDF içerik kapısı düşünce kullanıcı DUYAR
# ===========================================================================
EXPORT_HARNESS = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [appYolu] = process.argv.slice(2);
const src = fs.readFileSync(appYolu, 'utf8');
function grab(s, n) {
    let i = s.indexOf('async function ' + n + '(');
    if (i < 0) i = s.indexOf('function ' + n + '(');
    if (i < 0) return null;
    let d = 0;
    for (let j = s.indexOf('{', i); j < s.length; j++) {
        if (s[j] === '{') d++;
        else if (s[j] === '}') { d--; if (d === 0) return s.slice(i, j + 1); }
    }
    return null;
}
const kayit = { uyari: [], hata: [], indirilen: [] };
// Uç HTTP 200 + application/pdf ilan ediyor ama gövde PDF DEĞİL
// (ölçülen gerçek kusur: boş gövdeye 200 dönen uç). İçerik kapısı
// fırlatmalı, sonra kullanıcı DUYMALI.
function sahteBlob(metin, tip) {
    return {
        size: metin.length, type: tip,
        slice: function () {
            return { arrayBuffer: async function () {
                const b = new Uint8Array(5);
                for (let i = 0; i < 5 && i < metin.length; i++) {
                    b[i] = metin.charCodeAt(i);
                }
                return b.buffer;
            } };
        }
    };
}
const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    currentResults: { motor: { motor_name: 'X', isp: 200, thrust: 1000,
                               chamber_pressure: 20, mdot_total: 1 },
                      injector: { type: 'showerhead' } },
    showWarning: function (m) { kayit.uyari.push(String(m)); },
    showError: function (m) { kayit.hata.push(String(m)); },
    downloadBlobAs: function (b, ad) { kayit.indirilen.push(ad); },
    T: function (k, f) { return f; },
    Blob: function (parts, o) { return { parts: parts, type: o && o.type }; },
    Uint8Array, Array, String, Number, Math, JSON, isFinite,
    fetch: async function () {
        return { ok: true, status: 200,
                 headers: { get: () => 'application/pdf' },
                 blob: async () => sahteBlob('<html>not a pdf</html>',
                                             'application/pdf') };
    }
};
sandbox.window = sandbox;
vm.createContext(sandbox);
['PDF_DEGIL', 'BOS_ICERIK', 'TARAMA_IKAME'].forEach(function (ad) {
    const m = src.match(new RegExp('const ' + ad + " = [^;]+;"));
    if (m) vm.runInContext(m[0], sandbox);
});
// ÖH D36: exportReport sayıları artık numTxt (D35 sayi-bicimi) ile basıyor;
// yardımcı da kum havuzuna alınır (yoksa eski app.js — atlanır).
{ const nt = grab(src, 'numTxt'); if (nt) vm.runInContext(nt, sandbox); }
vm.runInContext(grab(src, 'assertPdfBlob'), sandbox);
vm.runInContext(grab(src, 'exportReport'), sandbox);
vm.runInContext('exportReport', sandbox)().then(function () {
    process.stdout.write(JSON.stringify(kayit));
});
"""


@node_gerekli
class TestP11B224SessizYedekYasagi:

    def test_kapi_dusunce_kullanici_ekranda_duyuyor(self, tmp_path):
        """ÜRÜN KODU koşulur: PDF olmayan 200 gövdesinde uyarı basılmalı."""
        o = _node(tmp_path, EXPORT_HARNESS, APP_JS)
        assert o['indirilen'], (
            'ölçüm tabanı çürüdü: yedek metin raporu bile inmedi')
        assert any(a.endswith('.txt') for a in o['indirilen']), (
            'PDF olmayan gövde .pdf adıyla indi: içerik kapısı düşmüş '
            + repr(o['indirilen']))
        assert o['uyari'] or o['hata'], (
            'içerik kapısı düştü ve kullanıcıya HİÇBİR ŞEY söylenmedi: '
            'istediği PDF yerine sessizce ' + repr(o['indirilen'])
            + ' indi (sessiz yedek yasağı)')

    def test_export_report_catch_dalinda_kullaniciya_soyluyor(self):
        er = _fn(APP_JS.read_text(encoding='utf-8'), 'exportReport')
        assert er, 'exportReport bulunamadı'
        assert 'assertPdfBlob' in er, (
            'ölçüm tabanı çürüdü: PDF içerik kapısı kaldırılmış')
        i = er.find('} catch')
        assert i > 0, 'exportReport catch dalı yok'
        catch = er[i:]
        assert 'showWarning' in catch or 'showError' in catch, (
            'içerik kapısı düştüğünde ekrana hiçbir şey basılmıyor: '
            'kullanıcı istediği PDF yerine sessizce .txt indiğini '
            'göremiyor. catch dalı: ' + catch[:400])
        assert 'app.msg.pdfReportFallback' in catch, (
            'uyarı metni sözlüğe bağlı değil')

    def test_uyari_metni_EN_ve_TR_sozlukte(self):
        ortak = (STATIC / 'i18n_common.js').read_text(encoding='utf-8')
        assert ortak.count("'app.msg.pdfReportFallback'") == 2, (
            'app.msg.pdfReportFallback için EN+TR çifti yok: '
            + str(ortak.count("'app.msg.pdfReportFallback'")))


# ===========================================================================
# P11B1-03 [yüksek] — kasa cidarı çözücüden çizilir
# ===========================================================================
KATI_YUK = {'motor_name': 'D17-ARAYUZ', 'propellant_type': 'apcp',
            'grain_type': 'bates', 'chamber_pressure': 40.0,
            'thrust': 5000.0, 'burn_time': 3.0, 'chamber_diameter': 100.0,
            'grain_length': 500.0, 'core_diameter': 30.0,
            'expansion_ratio': 8.0}

CIDAR_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const [staticDir, sablonDir, yukYolu] = process.argv.slice(2);
const yuk = JSON.parse(fs.readFileSync(yukYolu, 'utf8'));
const sol = fs.readFileSync(path.join(sablonDir, 'solid.html'), 'utf8');
const viz = fs.readFileSync(path.join(staticDir, 'motor_viz3d.js'), 'utf8');
function grab(s, n) {
    const i = s.indexOf('function ' + n + '(');
    if (i < 0) return null;
    let d = 0;
    for (let j = s.indexOf('{', i); j < s.length; j++) {
        if (s[j] === '{') d++;
        else if (s[j] === '}') { d--; if (d === 0) return s.slice(i, j + 1); }
    }
    return null;
}
function grabVar(s, n) {
    const i = s.indexOf('var ' + n + ' = [');
    if (i < 0) return null;
    return s.slice(i, s.indexOf('];', i) + 2);
}
const sandbox = { console: { log() {}, warn() {}, error() {} },
    Math, Number, JSON, isFinite, parseFloat, Object, Array, String };
vm.createContext(sandbox);
vm.runInContext(grab(sol, 'buildSolidVizData'), sandbox);
vm.runInContext("function num(v,d){return (typeof v==='number'&&isFinite(v))?v:d;}", sandbox);
vm.runInContext(grabVar(viz, 'CASING_WALL_SCHEMAS'), sandbox);
vm.runInContext(grab(viz, 'resolveCasingWall'), sandbox);
const md = vm.runInContext('buildSolidVizData', sandbox)(yuk.results);
const Dch = md.chamber_diameter * 1000;
process.stdout.write(JSON.stringify({
    adaptor_gecirdi: ('structural_analysis' in md),
    sahne_cidar_mm: vm.runInContext('resolveCasingWall', sandbox)(md, Dch),
    geometrik_yedek_mm: Math.max(4, 0.045 * Dch),
    oda_capi_mm: Dch
}));
"""


@node_gerekli
class TestP11B103KasaCidari:

    @pytest.fixture(scope='class')
    def kati_yaniti(self, client):
        r = client.post('/calculate_solid', json=KATI_YUK)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        return r.get_json()

    def test_sahne_cidari_cozucunun_cidaridir(self, tmp_path, kati_yaniti):
        ca = ((kati_yaniti.get('structural_analysis') or {})
              .get('case_analysis') or {})
        cozucu = ca.get('wall_thickness_mm')
        assert isinstance(cozucu, (int, float)) and cozucu > 0, (
            'ölçüm tabanı çürüdü: çözücü case_analysis.wall_thickness_mm '
            'yayımlamıyor — bekçinin ölçtüğü kusur gösterilemez')
        yol = tmp_path / 'yuk.json'
        yol.write_text(json.dumps({'results': kati_yaniti}), encoding='utf-8')
        o = _node(tmp_path, CIDAR_HARNESS, STATIC, SABLON, yol)
        assert o['adaptor_gecirdi'], (
            'adaptör structural_analysis bloğunu 3B sözlüğe hiç geçirmiyor')
        assert abs(o['sahne_cidar_mm'] - cozucu) < 1e-9, (
            '3B sahne çözücünün cidarını değil başka bir sayıyı çiziyor: '
            'sahne ' + repr(o['sahne_cidar_mm']) + ' mm ⟷ çözücü '
            + repr(cozucu) + ' mm (geometrik yedek '
            + repr(o['geometrik_yedek_mm']) + ' mm)')
        assert abs(o['sahne_cidar_mm'] - o['geometrik_yedek_mm']) > 1e-9, (
            'ölçüm tabanı çürüdü: çözücünün cidarı ile 0,045·D yedeği '
            'aynı sayıya denk geldi — bu koşumda kusur ayırt edilemez')

    def test_sivi_adaptoru_de_yapisal_blogu_geciriyor(self, tmp_path):
        """Kaynak metni DEĞİL, adaptörün ÜRETTİĞİ sözlük ölçülür.

        (Metin taraması yorum satırındaki ``structural_analysis`` adına
        kanıyordu — ters mutasyon yeşil geçti; bekçi davranışsala
        çevrildi.)
        """
        kod = ("'use strict';\n"
               "const fs=require('fs'), vm=require('vm');\n"
               "const src=fs.readFileSync(process.argv[2],'utf8');\n"
               "function grab(s,n){const i=s.indexOf('function '+n+'(');\n"
               " if(i<0)return null;let d=0;\n"
               " for(let j=s.indexOf('{',i);j<s.length;j++){\n"
               "  if(s[j]==='{')d++;else if(s[j]==='}'){d--;\n"
               "   if(d===0)return s.slice(i,j+1);}}return null;}\n"
               "const sb={console:{log(){},warn(){},error(){}},Math,Number,\n"
               " JSON,isFinite,parseFloat,Object,Array,String};\n"
               "vm.createContext(sb);\n"
               "vm.runInContext(grab(src,'buildLiquidVizData'),sb);\n"
               "const md=vm.runInContext('buildLiquidVizData',sb)(\n"
               "  {chamber_diameter:100,chamber_length:300,\n"
               "   structural_analysis:{chamber_structure:\n"
               "     {wall_thickness:7.25}}});\n"
               "process.stdout.write(JSON.stringify({\n"
               "  gecti:('structural_analysis' in md),\n"
               "  cidar:((md.structural_analysis||{}).chamber_structure||{})\n"
               "        .wall_thickness}));\n")
        o = _node(tmp_path, kod, LIQUID)
        assert o['gecti'], (
            'sıvı adaptörü yapısal bloğu 3B sözlüğe geçirmiyor: sahne '
            '0,045·D yedeğine düşer')
        assert o['cidar'] == 7.25, (
            'yapısal blok bozularak geçiyor: ' + repr(o))


# ===========================================================================
# OH-Z1-02 [orta] — oksitleyici referans yoğunlukları TEK KAYNAK
# ===========================================================================
# TestOHZ102TekKaynakOksitleyici (3 düğüm) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum


# ===========================================================================
# P15B3-03 [yüksek] — CEA hüküm/künye metinleri sözlükte (EN+TR)
# ===========================================================================
#: ÇEVRİLDİ (ÖH D33-KOLAY · OH-D32-11). Bu on beş anahtarın on üçü YALNIZ
#: ``validateComposition()`` gövdesinde kullanılıyordu; o fonksiyon
#: OH-D31-05'te erişilemez kalmış (`#custom_fuel_config` paneli sökülmüştü)
#: ve D33'te SİLİNMİŞTİR. Sözlükten de kaldırıldılar, yoksa
#: ``tests/test_i18n_advanced.py::test_no_unused_dictionary_keys`` ölü
#: anahtar sayardı. Geriye ret gövdesinin ekrana inen üç parçası kalır —
#: onlar CANLI yolda (``_ihracRetMetni`` / ``HRMAReject``) kullanılıyor.
CEA_ANAHTARLARI = (
    'adv.js.rejectCode', 'adv.js.rejectFields', 'adv.js.rejectNoReason',
)

#: Silinen istemci sarmalıyla birlikte sözlükten de kalkan anahtarlar.
SOKULEN_CEA_ANAHTARLARI = (
    'adv.js.ceaValidatedOk', 'adv.js.ceaInTablePartial',
    'adv.js.ceaNotInTable', 'adv.js.ceaSourceLabel',
    'adv.js.ceaSourceNotDeclared', 'adv.js.ceaCalculatedProperties',
    'adv.js.ceaMolecularWeight', 'adv.js.ceaHeatOfFormation',
    'adv.js.ceaEstimatedDensity', 'adv.js.ceaSpecificHeat',
    'adv.js.ceaCheckFailed',
)


class TestP15B303CeaMetinleri:
    """ÇEVRİLDİ: istemci sarmalı söküldü, UÇ SÖZLEŞMESİ aynen duruyor.

    ESKİ SÖZLEŞME: ``validateComposition()`` gövdesindeki CEA hüküm ve künye
    cümlelerinin i18n anahtarlarıyla yazıldığı ölçülüyordu. Sözleşme ölü
    fonksiyonun sayfada DURMASINI şart koşuyordu (kusuru koruyan bekçi):
    ÖLÇÜLDÜ (D33 a1/once.json · M2) ki fonksiyonun tek çağıranı
    OH-D31-05'te sökülen panelin düğmesiydi ve ``#composition_rows``
    sorgusu her koşumda boş dönüyordu — akış HİÇBİR yoldan açılamıyordu.

    YENİ SÖZLEŞME: (1) istemci sarmalı ve onunla ölen anahtarlar geri
    gelmez, (2) ret gövdesinin CANLI parçaları sözlükte EN+TR durur,
    (3) ``/api/validate-fuel`` ucu künyesini yayımlamayı SÜRDÜRÜR — kalemin
    fiziksel kazanımı olan bu üçüncü ayak dokunulmadan kaldı.
    """

    def test_ret_govdesi_anahtarlari_EN_TR_sozlukte(self):
        s = (STATIC / 'i18n_advanced.js').read_text(encoding='utf-8')
        eksik = [a for a in CEA_ANAHTARLARI if s.count("'" + a + "'") != 2]
        assert not eksik, (
            'EN+TR çifti eksik olan ret anahtarları: ' + repr(eksik))

    def test_olu_istemci_sarmali_ve_anahtarlari_geri_gelmedi(self):
        kod = re.sub(r'<!--.*?-->', '',
                     ADVANCED.read_text(encoding='utf-8'), flags=re.S)
        assert 'function validateComposition' not in kod, (
            'erişilemez CEA sarmalı geri geldi (OH-D32-11)')
        s = (STATIC / 'i18n_advanced.js').read_text(encoding='utf-8')
        geri = [a for a in SOKULEN_CEA_ANAHTARLARI if "'" + a + "'" in s]
        assert not geri, (
            'ölü sarmalla birlikte sökülen anahtarlar sözlüğe geri kondu: '
            + repr(geri))

    def test_uc_kunyeyi_hala_yayimliyor(self, client):
        """Ölçüm tabanı: uç tablo dışı maddeye künye basıyor."""
        r = client.post('/api/validate-fuel',
                        json={'composition': [{'formula': 'C12H26',
                                               'percentage': 100}]})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        d = r.get_json()
        assert 'components' in d, d
        assert any('found_in_database' in c for c in d['components']), d


# ===========================================================================
# P12bB2-02 [yüksek] (Fable-D15 ŞARTI) — deniz-seviyesi sayfa yükü CANLI
# ===========================================================================
SAYFA_YUKU_JS = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [solYolu, alt, atm] = process.argv.slice(2);
const src = fs.readFileSync(solYolu, 'utf8');
function grab(s, n) {
    const i = s.indexOf('function ' + n + '(');
    if (i < 0) return null;
    let d = 0;
    for (let j = s.indexOf('{', i); j < s.length; j++) {
        if (s[j] === '{') d++;
        else if (s[j] === '}') { d--; if (d === 0) return s.slice(i, j + 1); }
    }
    return null;
}
const els = { test_altitude: { value: alt }, atm_pressure: { value: atm } };
const sandbox = { document: { getElementById: (id) => els[id] || null },
    console: { log() {}, warn() {}, error() {} },
    Number, parseFloat, isFinite, JSON, String };
vm.createContext(sandbox);
vm.runInContext(grab(src, 'solidAmbientAltitudeM'), sandbox);
vm.runInContext(grab(src, 'solidAmbientFields'), sandbox);
process.stdout.write(JSON.stringify(
    vm.runInContext('solidAmbientFields', sandbox)()));
"""


@node_gerekli
class TestP12bB202DenizSeviyesiSayfaYuku:
    """Sayfanın KENDİ ürettiği ortam alanları uçta 200 alır."""

    def test_alt0_90kPa_sayfa_yuku_200_donuyor(self, tmp_path, client):
        alanlar = _node(tmp_path, SAYFA_YUKU_JS, SOLID, '0', '90')
        assert set(alanlar) == {'atm_pressure'}, (
            'deniz-seviyesi dalı hâlâ iki kanal birden gönderiyor: '
            + repr(alanlar) + ' — /calculate_solid ambient kapısı '
            '(P7B2-15) bunu 422 ile reddeder')
        r = client.post('/calculate_solid', json=dict(KATI_YUK, **alanlar))
        assert r.status_code == 200, (
            'kullanıcı ölçülmüş 90 kPa girip irtifayı 0 bıraktığında sayfa '
            'yükü reddediliyor: HTTP ' + str(r.status_code) + ' '
            + r.get_data(as_text=True)[:300])
        assert isinstance(r.get_json().get('isp_sea_level'), float)

    def test_irtifa_verilmisse_yalniz_irtifa_gidiyor(self, tmp_path, client):
        alanlar = _node(tmp_path, SAYFA_YUKU_JS, SOLID, '10000', '101.325')
        assert set(alanlar) == {'test_altitude'}, repr(alanlar)
        r = client.post('/calculate_solid', json=dict(KATI_YUK, **alanlar))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]

    def test_iki_kanal_acikca_gonderilirse_uc_hala_reddediyor(self, client):
        """Ölçüm tabanı: kapı canlı, yani sayfa yükü rastgele geçmiyor."""
        r = client.post('/calculate_solid',
                        json=dict(KATI_YUK, atm_pressure=90.0,
                                  test_altitude=0))
        assert r.status_code == 422, (
            'ölçüm tabanı çürüdü: ambient çakışma kapısı artık kapamıyor')


# ===========================================================================
# Kanıt hijyeni (Fable-D15 ŞARTLARI) — rapor sayıları kendi ölçümüyle hizalı
# ===========================================================================
D15UI = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D15' / 'ui-paneller'
D15SAB = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D15' / 'sablonlar'


class TestKanitHijyeni:

    def test_b1_04_rapor_paragrafi_kendi_jsonunu_yansitiyor(self):
        rap = (kanit_gerekli(D15UI / 'a1' / 'rapor.md')).read_text(encoding='utf-8')
        par = re.search(r'### P11B1-04.*?(?=\n### )', rap, re.S)
        assert par, 'P11B1-04 paragrafı bulunamadı'
        par = par.group(0)
        onc = json.loads((kanit_gerekli(D15UI / 'a1' / 'b1_04_ONCE.json'))
                         .read_text(encoding='utf-8'))
        son = json.loads((kanit_gerekli(D15UI / 'a1' / 'b1_04_SONRA.json'))
                         .read_text(encoding='utf-8'))
        assert str(son['sahne_delik_sayisi']) in par, (
            'rapor paragrafı kanıt JSON\'undaki delik sayısını ('
            + str(son['sahne_delik_sayisi']) + ') anmıyor')
        assert ('%.4f' % son['sahne_delik_capi_mm']).replace('.', ',') in par, (
            'rapor paragrafı SONRA çapını anmıyor')
        assert ('%.4f' % onc['sahne_delik_capi_mm']).replace('.', ',') in par
        assert 'delik sayısı **3 → 32**' not in par, (
            'defter BAŞLIĞINDAN kopyalanan sayı hâlâ ÖLÇÜM İDDİASI gibi '
            'duruyor (32 delik / 0,83 mm bu dizinde ölçülmedi)')

    def test_b2_02_a2_raporu_olculen_yedek_sayisini_yaziyor(self):
        """Rapor, YAPMADIĞI bir sökümü iddia edemez.

        ÖH D31 · arayuz-panel a3 (14 Eyl 2026) — ölçüt GEVŞETİLMEDİ,
        DOĞRU EKSENE çevrildi. Eski hâli raporun yazdığı sayı ile
        dosyanın BUGÜNKÜ sayısının birebir EŞİT olmasını istiyordu; bu,
        raporu yazan dalgadan SONRAKİ her sökümü kırmızıya düşürür.
        D31'de Berke ÖK-21 kilidini açtı ve a3 `solid.html`den iki alan
        daha söktü (`two_phase_loss`, `case_thickness`): **70 → 68**.
        Eşitlik şartı orada raporun dürüstlüğünü değil, ONARIMIN
        OLMAMASINI korur hâle gelmişti.

        Korunan asıl iddia: rapor, dosyada gerçekleşmemiş bir indirimi
        yazamaz. Yön tek taraflıdır — bugünkü sayı raporun yazdığından
        BÜYÜK olamaz. Küçük olması sonraki dalganın daha derin söktüğü
        anlamına gelir; o dalganın kendi bekçisi vardır (D31 a3:
        `tests/test_d31_arayuz_panel_a3.py::TestOK21KumeGerilemesi`).
        """
        src = SOLID.read_text(encoding='utf-8')
        gov = _fn(src, 'collectAllParameters')
        assert gov, 'collectAllParameters bulunamadı'
        olculen = len(re.findall(r'\|\|\s*-?\d', gov))
        rap = (kanit_gerekli(D15SAB / 'a2' / 'rapor.md')).read_text(encoding='utf-8')
        satir = [s for s in rap.split('\n')
                 if '|| SAYI` kalıbı **72 → ' in s]
        assert satir, ('a2 raporundaki onarım sonrası `|| SAYI` satırı '
                       'bulunamadı')
        m = re.search(r'72 → (\d+)', satir[0])
        assert m and int(m.group(1)) < 72, satir[0]
        raporun_sayisi = int(m.group(1))
        assert olculen <= raporun_sayisi, (
            'rapor dosyada OLMAYAN bir indirim yazıyor (rapor '
            + str(raporun_sayisi) + ', ölçülen ' + str(olculen) + '): '
            + satir[0])
