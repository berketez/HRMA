# -*- coding: utf-8 -*-
"""ÖH D16 · kulvar ARAYUZ · aşama 1 — onarım bekçileri.

Kapsanan defter kalemleri:

* **P11S1-03** — koruma panelinin manşet girdisi ``[A] Net Heat Flux``
  ablatif hesapta HİÇ kullanılmıyordu ve panel bunu SÖYLEMİYORDU. ÖLÇÜLDÜ
  (``docs/scofield/raw/OH/D16/arayuz/a1/once.json`` M1, taban ``6fde52b``):
  güvertenin gövdesiyle 2 → 50 MW/m² (25×) süpürmesinde
  ``required_thickness_mm`` altı koşumda da 3,413436612744386 (ayrık değer
  sayısı 1); uç bunu ``flux_basis="surface_energy_balance"`` ile açıkça
  söylüyor, panel kaynağında ``flux_basis`` geçiş sayısı 0. Üstelik
  "kullanılan sayının künyesi" satırı 50 MW/m² koşumunda "entered in the
  form" diyor ve kalınlık sayısını kazanılmış hüküm gibi basıyordu
  (``once2.json`` A: ``kalinlik_sayisi_ekranda: true``).
* **P15B3-03** — ``/api/validate-fuel`` "not present in the NASA CEA species
  table" künyesi üretirken ``advanced.html`` bu künyeyi hiç okumuyordu
  (``once.json`` M2: ``result.source`` geçiş sayısı 0) ve hükmü yalnız
  "kaç özellik çözüldü" sayısına bağlıyordu.
* **P10B1-07** — XLSX "Injector" sayfası ``injector_design`` bloğunu
  döküyordu; imalat zinciri (STEP/DXF/teknik çizim) ise ``injector``
  bloğundan kuruluyor (``app.py`` ``cad_input['injector_results']``).
  ÖLÇÜLDÜ (``once2.json`` C, ürün kodu node içinde koşularak): sayfa
  Cd 0,78 + delik çapı 2,0486 mm yazıyordu, imalat bloğu ise
  Cd 0,700 + 32 delik + ΔP 4,0 bar + 22,3287 m/s.
* **OH-D15-10** — ``#oxidizer_temp`` ``min="100" max="1000"`` taşıyordu;
  bu aralık hiçbir oksitleyicinin sıvı zarfı değil ve sekiz uç noktanın
  yedisinde motor 400 ``oxidizer_state_undefined`` ile reddediyordu
  (``once.json`` M4).

Yöntem: Flask ``test_client`` (port bağlanmaz) + node içinde GERÇEK panel
dosyası ve GERÇEK şablon kod parçaları. Beklenen değerler elle yazılmaz;
ucun O KOŞUMDAKİ yanıtından ve deponun kendi sabit tablosundan türetilir.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = KOK / 'hrma' / 'static' / 'js'
PANELS = STATIC_JS / 'panels'
ADV_YOL = KOK / 'hrma' / 'templates' / 'advanced.html'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Uygulama yalnız geri döngü Host başlığına yanıt verir (DNS-rebinding kapısı)
HEADERS = {'Host': '127.0.0.1:8080'}

#: Güvertenin (analysis_dock) koruma paneli için gönderdiği gövde: h_gas ve
#: T_recovery alanlarının SONLU varsayılanları var (3000 / 3200), bu yüzden
#: her koşumda gönderilirler ve uç yüzey enerji dengesi yolunu açar.
GUVERTE_GOVDESI = {
    'mode': 'ablative', 'material': 'silica_phenolic', 'design_margin': 1.5,
    'burn_time_s': 10, 'h_gas_W_m2K': 3000, 'T_recovery_K': 3200,
}

#: Eski yol: çift GÖNDERİLMEZ, çağıranın akısı doğrudan kullanılır.
ESKI_YOL_GOVDESI = {
    'mode': 'ablative', 'material': 'silica_phenolic', 'burn_time_s': 10,
}

#: P11 savcısının süpürmesi (25×).
Q_SUPURME = (2.0e6, 5.0e6, 1.0e7, 2.0e7, 3.0e7, 5.0e7)


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
const out = {};
Object.keys(payload.responses || {}).forEach(function (ad) {
  const root = new El('div');
  sb.window.ProtectionPanel._renderAblative(payload.responses[ad], root);
  out[ad] = root.children.map(function (c) { return c.innerHTML; }).join('');
});
process.stdout.write(JSON.stringify(out));
"""


def _node_kos(tmp_path, script, *args):
    f = tmp_path / 'kos_d16.js'
    f.write_text(script, encoding='utf-8')
    p = subprocess.run([NODE, str(f)] + [str(a) for a in args],
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, ('node altında çöktü:\n' + p.stderr[-3000:])
    return json.loads(p.stdout)


def _panel_ciz(tmp_path, responses, motor_result=None, motor_type=None):
    girdi = tmp_path / 'girdi_d16.json'
    girdi.write_text(json.dumps({'responses': responses,
                                 'motorResult': motor_result,
                                 'motorType': motor_type}), encoding='utf-8')
    return _node_kos(tmp_path, PANEL_HARNESS, STATIC_JS, girdi)


def _sablon_fonksiyonu(ad):
    """``advanced.html`` içinden ``function <ad>`` bloğunu SÖKER.

    ÖH D30 / fix-29b: sürücülere yardımcı fonksiyon KOPYALANMAZ, şablondan
    sökülür — kopya ürünle ayrışır. (Ölçülen kusur: D29 arayuz-panel a1
    ``applyOxidizerTempBand``a ``i18nFmt`` çağrısı ekledi; sürücü yalnız
    dilimi aldığı için node "ReferenceError: i18nFmt is not defined" ile
    çöktü ve bekçi ürünü HİÇ ölçemedi.)
    """
    t = ADV_YOL.read_text(encoding='utf-8')
    bas = t.find('function ' + ad + '(')
    assert bas >= 0, f'şablon çıpası kayboldu: function {ad}'
    derinlik, i = 0, t.index('{', bas)
    for j in range(i, len(t)):
        if t[j] == '{':
            derinlik += 1
        elif t[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return t[bas:j + 1]
    raise AssertionError(f'şablon bloğu kapanmadı: {ad}')


def _sablon_dilimi(bas, son):
    """``advanced.html`` içinden ÜRÜN KODU dilimi (kopya değil, kaynak)."""
    t = ADV_YOL.read_text(encoding='utf-8')
    i = t.find(bas)
    assert i >= 0, f'şablon çıpası kayboldu: {bas!r}'
    j = t.find(son, i)
    assert j > i, f'şablon bitiş çıpası kayboldu: {son!r}'
    return t[i:j]


# ===========================================================================
# P11S1-03 — girilen akı kullanılmıyorsa EKRAN bunu söyler
# ===========================================================================
class TestP11S1_03KullanilanAkininKunyesi:

    @pytest.fixture(scope='class')
    def supurme(self, client):
        out = {}
        for q in Q_SUPURME:
            r = client.post('/api/thermal-protection',
                            json=dict(GUVERTE_GOVDESI, q_net_W_m2=q),
                            headers=HEADERS)
            assert r.status_code == 200, r.get_data(as_text=True)[:400]
            out[q] = r.get_json()
        return out

    def test_kusurun_dayanagi_hala_uretilebiliyor(self, supurme):
        """Bekçinin ZEMİNİ: güverte gövdesiyle girilen akı GERÇEKTEN
        kullanılmıyor. Bu artık doğru değilse kalem yeniden ölçülmeli."""
        temeller = {y.get('flux_basis') for y in supurme.values()}
        assert temeller == {'surface_energy_balance'}, (
            f'uç artık başka bir akı temeli kullanıyor: {temeller} — '
            'bekçinin dayanağı bayat, P11S1-03 yeniden ölçülmeli')
        kalinliklar = {repr(y.get('required_thickness_mm'))
                       for y in supurme.values()}
        assert len(kalinliklar) == 1, (
            '25× akı süpürmesi artık çıktıyı DEĞİŞTİRİYOR: '
            f'{sorted(kalinliklar)} — kalemin ölçümü bayat')
        yankilar = {y.get('q_caller_W_m2') for y in supurme.values()}
        assert yankilar == set(Q_SUPURME), (
            'uç girilen akıyı q_caller_W_m2 ile yankılamıyor')

    @node_gerekli
    def test_ekran_girilen_akinin_kullanilmadigini_soyluyor(self, tmp_path,
                                                            supurme):
        """Ucun ``flux_basis`` hükmü EKRANA iner ve girilen değerin
        koşuma girmediği açıkça yazılır."""
        cevap = {('q%g' % q): supurme[q] for q in (2.0e6, 5.0e7)}
        ciz = _panel_ciz(tmp_path, cevap)
        for ad, html in ciz.items():
            temel = supurme[float(ad[1:])]['flux_basis']
            assert temel in html, (
                f'{ad}: ucun flux_basis hükmü ({temel!r}) ekranda yok')
            assert 'NOT used in this run' in html, (
                f'{ad}: girilen akının kullanılmadığı ekranda söylenmiyor')
            kanca = re.findall(r'data-tps-caller-used="(\w+)"', html)
            assert kanca == ['false'], (
                f'{ad}: caller kancası {kanca!r} — "false" olmalıydı')

    @node_gerekli
    def test_kazanilmamis_kalinlik_sayisi_basilmiyor(self, tmp_path, supurme):
        """FAIL-CLOSED: hükmü taşıyan çift (h_gas, T_recovery) motordan
        OKUNMADIYSA kalınlık sayısı kart olarak basılmaz.

        ÖLÇÜLEN KUSUR (once2.json A, taban): 50 MW/m² koşumunda ekran
        3,41 mm'yi kazanılmış hüküm gibi basıyordu — oysa o sayı panelin
        KENDİ h_gas/T_recovery varsayılanlarından çıkmıştı.
        """
        y = supurme[5.0e7]
        assert isinstance(y.get('required_thickness_mm'), float), (
            'uç sayıyı üretmiş olmalı — yoksa bekçi boşa döner')
        html = _panel_ciz(tmp_path, {'q5e7': y})['q5e7']
        sayi = '%.2f' % y['required_thickness_mm']
        assert sayi not in html, (
            f'kazanılmamış kalınlık ({sayi} mm) hâlâ kartta')
        assert 'data-tps-flux-kind="assumed"' in html, (
            'ölçülmemiş çiftle kurulan hüküm "assumed" künyesi taşımıyor')

    @node_gerekli
    def test_eski_yol_bit_ayni_kaliyor(self, client, tmp_path):
        """Çift verilmediğinde (eski yol) künye ESKİSİ GİBİ davranır:
        girilen akı gerçekten kullanılır, ekran onu 'kullanılmadı' demez."""
        r = client.post('/api/thermal-protection',
                        json=dict(ESKI_YOL_GOVDESI, q_net_W_m2=2.0e6),
                        headers=HEADERS)
        y = r.get_json()
        assert y['flux_basis'] == 'caller_supplied_no_energy_balance'
        html = _panel_ciz(tmp_path, {'eski': y})['eski']
        assert 'NOT used in this run' not in html, (
            'eski yolda akı KULLANILIYOR ama ekran kullanılmadı diyor')
        assert re.findall(r'data-tps-caller-used="(\w+)"', html) == ['true']

    @node_gerekli
    def test_olculmus_cift_okunduysa_hukum_kazanilir(self, client, tmp_path):
        """Karşı uç: h_gas + T_recovery motorun KENDİ istasyonundan
        okunup UCA DA O ÇİFT gönderildiğinde künye 'computed' olur.

        ÖH D18 · P11S1-03 ŞART (Fable-D15/D16) İLE ÇEVRİLDİ. Bu bekçi
        ``GUVERTE_GOVDESI``yi (3000 / 3200 — güvertenin KENDİ varsayılan
        çifti) gönderiyor, ama künyeden ``computed`` bekliyordu: yani
        panelin motordan okuduğu çift ile koşuma GİREN çift birbirinden
        bambaşkayken (16293,32 W/m²K · 1705,38 K ⟷ 3000 · 3200) hükmün
        kazanılmış sayılmasını KİLİTLİYORDU — kusuru koruyan bekçiydi
        (ölçüm: ``docs/scofield/raw/OH/D18/arayuz/a1/once_p11s1_03.json``).

        Bekçinin İDDİASI korunur ("okunan çift kullanıldıysa künye
        computed"), yalnız KURULUMU dürüstleşir: uca artık motorun O
        KOŞUMDAKİ çifti gönderilir. Bu çiftle uç kendi geçerlilik zarfının
        DIŞINA düştüğünü ilan ediyor (``model_valid`` false, toparlanma
        sıcaklığı ablasyon sıcaklığının altında), bu yüzden kart sayı
        yerine '—' basar: künye kazanılmıştır, hüküm kazanılmamıştır — bu
        iki koşul bağımsızdır (P11B5-01). Uyuşmaz çiftin 'computed'
        BASMADIĞI ayrıca ``tests/test_d18_arayuz_a1.py`` içinde kilitlidir.
        """
        proje = json.loads((KOK / 'examples'
                            / 'Example Solid KNDX BATES 75mm.hrma')
                           .read_text(encoding='utf-8'))
        mr = client.post('/calculate_solid',
                         json=dict(proje['inputs']['fields']),
                         headers=HEADERS).get_json()
        aft = (mr.get('cad_design', {}).get('insulation_system', {})
                 .get('aft_insulation', {}))
        cift = {'h_gas_W_m2K': aft.get('h_gas_W_m2K'),
                'T_recovery_K': aft.get('T_recovery_K')}
        assert all(isinstance(v, float) for v in cift.values()), (
            f'katı motor artık okunacak çifti yayımlamıyor: {cift!r}')
        govde = dict(GUVERTE_GOVDESI)
        govde.update(cift)
        y = client.post('/api/thermal-protection',
                        json=dict(govde, q_net_W_m2=2.0e6),
                        headers=HEADERS).get_json()
        assert y['h_gas_W_m2K'] == cift['h_gas_W_m2K'], (
            'uç gönderilen çifti yankılamıyor — bekçinin ölçütü çalışamaz')
        html = _panel_ciz(tmp_path, {'kati': y}, motor_result=mr,
                          motor_type='solid')['kati']
        kind = re.findall(r'data-tps-flux-kind="(\w+)"', html)
        assert kind == ['computed'], (
            f'ölçülmüş çift okunup gönderildiği hâlde künye {kind!r} — '
            'hüküm kazanılmış sayılmıyor (fail-closed fazla sıkı)')
        assert re.findall(r'data-tps-pair-match="(\w+)"', html) == ['true']
        # Sayının basılıp basılmayacağını ucun KENDİ geçerlilik hükmü
        # belirler; beklenti ucun O KOŞUMDAKİ yanıtından türetilir.
        if y.get('model_valid') is False:
            assert y.get('required_thickness_mm') is None, (
                'uç zarf dışında sayı yayımlıyor — kalem yeniden ölçülmeli')
            assert re.findall(r'data-tps-earned="(\w+)"', html) == ['false']
            assert '—' in html, 'zarf dışı koşumda kart sayı yerine — basmalı'
        else:
            assert ('%.2f' % y['required_thickness_mm']) in html, (
                'kazanılmış hüküm sayı olarak basılmıyor')


# ===========================================================================
# P15B3-03 — CEA künyesi ekranda; tabloda olmayan madde "doğrulandı" olmaz
# ===========================================================================
class TestP15B3_03CeaKaynakKunyesi:

    @pytest.fixture(scope='class')
    def yanitlar(self, client):
        out = {}
        for ad, bilesim in (
                ('tabloda', [{'formula': 'CH4', 'percentage': 100.0}]),
                ('tabloda_yok', [{'formula': 'C12H26', 'percentage': 100.0}]),
                ('karisik', [{'formula': 'CH4', 'percentage': 50.0},
                             {'formula': 'C12H26', 'percentage': 50.0}])):
            r = client.post('/api/validate-fuel',
                            json={'composition': bilesim}, headers=HEADERS)
            assert r.status_code == 200, r.get_data(as_text=True)[:300]
            out[ad] = r.get_json()
        return out

    def test_ucun_kunyesi_hala_uretilebiliyor(self, yanitlar):
        """Bekçinin ZEMİNİ: uç gerçekten 'tabloda yok' diyor mu?"""
        assert ('not present in the NASA CEA species table'
                in yanitlar['tabloda_yok']['source']), (
            'uç artık bu künyeyi üretmiyor — kalem yeniden ölçülmeli')
        assert yanitlar['tabloda']['source'] == 'NASA CEA species table'
        assert [c['found_in_database']
                for c in yanitlar['karisik']['components']] == [True, False]

    @pytest.mark.skip(reason="BAYAT ÇIPA (ana model, ÖH D34 · 21 Eyl 2026): bu test advanced.html içindeki bileşim doğrulama bloğunu (`const bilesenler = Array.isArray` … `ceaHukmu`) node ile koşturuyordu; blok, `#composition_rows` editörü OH-D31-05'te sökülünce çağıransız kaldı ve D33-KOLAY OH-D32-11 temizliğinde (commit a21b9419, kesilen ajan, rapor yok) advanced.html'den kaldırıldı. Ürün davranışı değil, ÖLÜ KOD kalktı; ucun künyesi test_ucun_kunyesi_hala_uretilebiliyor ile bekçili kalır. Editör geri gelirse bu test de yeniden bağlanır.")
    @node_gerekli
    def test_hukum_kaynak_kunyesinden_kuruluyor(self, tmp_path, yanitlar):
        """``ceaHukmu`` ÜRÜN KODUdur ve node içinde koşturulur: tabloda
        olmayan bileşende 'NASA CEA ile doğrulandı' DEMEZ."""
        dilim = _sablon_dilimi('const bilesenler = Array.isArray',
                               'validation.innerHTML =')
        # ÖH D17 / arayuz a1: hüküm cümleleri sözlüğe taşındı
        # (P15B3-03 kalan yarısı). Ürün kodu artık i18nText/i18nFmt
        # çağırıyor; sürücü bu ikisini VARSAYILANI döndüren birer
        # kabukla besler, böylece bekçi AYNI ürün kodunu koşturmaya ve
        # AYNI iddiaları sınamaya devam eder (gevşetme yok).
        surucu = ('const result = JSON.parse(process.argv[2]);\n'
                  'const cozulen = Number(process.argv[3]);\n'
                  'function i18nText(k, f) { return f; }\n'
                  'function i18nFmt(k, p, f) {\n'
                  '  return String(f).replace(/\\{(\\w+)\\}/g,\n'
                  '    function (m, a) { return (a in p) ? p[a] : m; });\n'
                  '}\n'
                  + dilim
                  + '\nprocess.stdout.write(JSON.stringify('
                    '{hukum: ceaHukmu, tumu: tumuTabloda, '
                    'disi: tabloDisi}));')
        for ad, y in yanitlar.items():
            props = y.get('mixture_properties') or {}
            cozulen = sum(1 for k in ('molecular_weight', 'heat_of_formation',
                                      'density', 'specific_heat')
                          if isinstance(props.get(k), (int, float)))
            r = _node_kos(tmp_path, surucu, json.dumps(y), cozulen)
            tabloda = all(c['found_in_database'] for c in y['components'])
            assert r['tumu'] is tabloda, (
                f'{ad}: şablon tablo hükmünü ucun found_in_database '
                'alanından kurmuyor')
            if not tabloda:
                assert 'NOT validated against the NASA CEA' in r['hukum'], (
                    f'{ad}: madde CEA tablosunda yokken ekran hâlâ '
                    f'doğrulama iddia ediyor: {r["hukum"]!r}')
                assert r['disi'], f'{ad}: tablo dışı bileşen adlandırılmıyor'
            else:
                assert 'NOT validated' not in r['hukum'], (
                    f'{ad}: tabloda OLAN madde için yanlış uyarı')

    @pytest.mark.skip(reason="BAYAT ÇIPA (ana model, ÖH D34 · 21 Eyl 2026): bu test advanced.html içindeki bileşim doğrulama bloğunu (`const bilesenler = Array.isArray` … `ceaHukmu`) node ile koşturuyordu; blok, `#composition_rows` editörü OH-D31-05'te sökülünce çağıransız kaldı ve D33-KOLAY OH-D32-11 temizliğinde (commit a21b9419, kesilen ajan, rapor yok) advanced.html'den kaldırıldı. Ürün davranışı değil, ÖLÜ KOD kalktı; ucun künyesi test_ucun_kunyesi_hala_uretilebiliyor ile bekçili kalır. Editör geri gelirse bu test de yeniden bağlanır.")
    def test_ucun_source_dizesi_ekranda_basiliyor(self):
        """Sunucunun kendi künyesi ekranda GEÇER (metin uydurulmaz)."""
        dilim = _sablon_dilimi('const bilesenler = Array.isArray',
                               'Calculated Properties:')
        assert '${result.source' in dilim, (
            'ucun source künyesi ekrana basılmıyor')


# ===========================================================================
# P10B1-07 — XLSX "Injector" sayfası imalat bloğunu döker
# ===========================================================================
class TestP10B1_07XlsxEnjektorSayfasi:

    @pytest.fixture(scope='class')
    def hibrit(self, client):
        r = client.post('/calculate', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o'}, headers=HEADERS)
        assert r.status_code == 200
        return r.get_json()

    def test_iki_blok_hala_ayrisik(self, hibrit):
        """Bekçinin ZEMİNİ: iki blok AYNI donanımı tarif eder (ÖH D35 OH-ON-01).

        (Ad tarihsel kalır: düğüm kimliği taban listesinde bu adla izlenir.
        14 Eki çevirisinin gerekçesi aşağıda, iddiaların yanında.)

        ÖH D25 / P16B1-45 — ZEMİN YENİDEN ÖLÇÜLDÜ. Düğüm ayrışmayı
        ``discharge_coefficient`` üzerinden kanıtlıyordu ve kendi metni
        "ayrışma kapanmış olabilir, kalem yeniden ölçülmeli" diyordu.
        Kapandı: Cd artık TEK kaynaktan gelir — aynı istekte iki farklı
        deşarj katsayısı yayımlanamaz (eskiden plaka 0,70, devre 0,78
        yazıyordu ve plaka geometrisi künyesiz olandan türüyordu).

        P10B1-07'nin zemini zaten Cd DEĞİL, DELİK DESENİdir: XLSX sayfası
        imalat bloğunun (``injector``) desenini dökmeli, devre modelininkini
        değil. Ölçüldü (docs/scofield/raw/OH/D25/app-api/a3/sonra_ABC.json,
        varsayılan hibrit gövde): imalat bloğu 32 delik x 0,88676 mm, devre
        bloğu 3 orifis x 2,06781 mm. Zemin bu iki sayıya bağlandı; Cd
        artık TERS yönde (eşitlik) kilitlenir.
        """
        a = hibrit.get('injector') or {}
        b = hibrit.get('injector_design') or {}
        assert a and b, 'bloklardan biri artık yayımlanmıyor'
        assert (a.get('discharge_coefficient')
                == b.get('discharge_coefficient')), (
            'aynı istekte iki farklı Cd yayımlanıyor — P16B1-45 geri geldi')
        # ÖH V3 taban-v (14 Eki 2026) — ZEMİN YENİDEN ÖLÇÜLDÜ, BEKÇİ ÇEVRİLDİ
        # (dört koşul). Bu iki iddia ayrışmayı (32 × Ø0,887 ⟷ 3 × Ø2,068)
        # kilitliyordu ve kendi metni "ayrışma kapanmış olabilir, kalem
        # yeniden ölçülmeli" diyordu. Kapandı — KAYITLI KARARLA: ÖH D35
        # OH-ON-01 (commit a234ea41, "tek enjektör çözümü"): imalat bloğu
        # delik planını devre çözücüsünden TÜKETİR, yeniden türetmez
        # (``injector_design.py`` ``A_inj_canon`` / ``orifice_plan_is_canon``).
        # Ölçüldü (bu gövde, 14 Eki): ``injector`` 3 × Ø2,08148 mm =
        # ``injector_design`` 3 orifis × Ø2,08148 mm, ``orifice_plan_is_canon``
        # True. P10B1-07'nin niyeti (XLSX sayfası imalat bloğunu döker) aşağıdaki
        # ``test_sayfa_imalat_blogunu_dokuyor``da aynen sınanır; zemin artık
        # "iki blok AYNI donanımı tarif eder" — Cd eşitliği gibi. Kanon plan
        # yeniden türetmeye dönerse (eski ayrışma) bu düğüm KIRMIZI verir.
        assert a.get('orifice_plan_is_canon') is True, (
            'imalat bloğu delik planını devre çözücüsünden tüketmiyor — '
            'OH-ON-01 (iki ayrı enjektör planı) geri geldi')
        assert a.get('n_holes') == b.get('number_of_orifices'), (
            'iki blok farklı delik SAYISI veriyor — OH-ON-01 geri geldi: '
            f"injector={a.get('n_holes')} devre={b.get('number_of_orifices')}")
        assert a.get('hole_diameter') == b.get('orifice_diameter_mm'), (
            'iki blok farklı delik ÇAPI veriyor — OH-ON-01 geri geldi: '
            f"injector={a.get('hole_diameter')} "
            f"devre={b.get('orifice_diameter_mm')}")

    @node_gerekli
    def test_sayfa_imalat_blogunu_dokuyor(self, tmp_path, hibrit):
        """ÜRÜN KODU koşar: satırlar ``motor.injector``dan gelir ve
        kaynak ilk satırda beyan edilir."""
        dilim = _sablon_dilimi('const inj = [];', 'const sheets = [')
        # Yanıt megabaytlarca — argv'ye sığmaz (Errno 7), dosyadan okunur.
        yanit_yolu = tmp_path / 'hibrit.json'
        yanit_yolu.write_text(json.dumps(hibrit), encoding='utf-8')
        surucu = (
            "const currentResults = JSON.parse("
            "require('fs').readFileSync(process.argv[2], 'utf8'));\n"
            "const m = currentResults;\n"
            "const num = (v, f) => (typeof v === 'number' && isFinite(v))\n"
            "  ? Number(v.toFixed(f === undefined ? 4 : f)) : '';\n"
            + dilim
            + "\nconst duz = {}; inj.forEach(function (r) "
              "{ duz[r[0]] = r[1]; });\n"
              "process.stdout.write(JSON.stringify(duz));")
        duz = _node_kos(tmp_path, surucu, yanit_yolu)
        beyan = duz.get('(source block)')
        assert beyan and 'motor.injector' in beyan, (
            'sayfa hangi bloğu döktüğünü beyan etmiyor: ' + repr(beyan))
        man = hibrit['injector']
        for anahtar, deger in man.items():
            if not isinstance(deger, (int, float)) or isinstance(deger, bool):
                continue
            etiket = anahtar.replace('_', ' ')
            assert etiket in duz, (
                f'imalat bloğunun {anahtar!r} alanı sayfaya inmiyor')
            assert duz[etiket] == round(float(deger), 4), (
                f'{anahtar}: sayfa {duz[etiket]!r} yazıyor, imalat bloğu '
                f'{deger!r}')
        alt = hibrit.get('injector_design') or {}
        capi = alt.get('hole_diameter_mm')
        if isinstance(capi, (int, float)):
            assert duz.get('hole diameter mm') != round(float(capi), 4), (
                'sayfa hâlâ imalat DIŞI bloğun delik çapını yazıyor')


# ===========================================================================
# OH-D15-10 — #oxidizer_temp aralığı oksitleyicinin zarfına bağlı
# ===========================================================================
class TestOHD15_10OksitleyiciSicaklikZarfi:

    def test_sablonda_sabit_aralik_kalmadi(self):
        t = ADV_YOL.read_text(encoding='utf-8')
        etk = re.search(r'<input[^>]*id="oxidizer_temp"[^>]*>', t)
        assert etk, '#oxidizer_temp alanı kayboldu'
        assert 'min=' not in etk.group(0) and 'max=' not in etk.group(0), (
            'alan hâlâ sabit bir aralık taşıyor: ' + etk.group(0))
        # ÖK-21: value/|| çifti bu dalgada SÖKÜLMEZ — dokunulmadığı doğrulanır
        assert 'value="293"' in etk.group(0), (
            'ÖK-21 ihlali: form katmanının value yedeği sökülmüş')

    def test_uc_bandi_yayimliyor_ve_tek_kaynak(self, client):
        from hrma.data.external_data_fetcher import OXIDIZER_LIQUID_BAND
        for ox, bant in OXIDIZER_LIQUID_BAND.items():
            T = 0.5 * (bant[0] + bant[1])
            r = client.post('/api/oxidizer-properties',
                            json={'oxidizer_type': ox, 'temperature': T},
                            headers=HEADERS)
            j = r.get_json()
            if r.status_code != 200 or j.get('status') != 'success':
                # Bu akışkanın ucu YOK (ölçüldü: n2o4 -> "Unknown oxidizer
                # type" gövdesi; üstelik HTTP 200 ile — ayrı bir kalem,
                # bu bekçinin konusu değil). Uydurma bant beklenmez.
                assert j.get('liquid_band_K') is None, (
                    f'{ox}: uç çözemediği akışkan için bant yayımlıyor')
                continue
            assert j.get('liquid_band_K') == [float(bant[0]), float(bant[1])], (
                f'{ox}: uç bandı yayımlamıyor ya da tabloyla uyuşmuyor '
                f'({j.get("liquid_band_K")!r} ⟷ {list(bant)!r})')

    @node_gerekli
    def test_bant_alanin_sinirlarina_yaziliyor(self, tmp_path, client):
        """ÜRÜN KODU koşar: ``applyOxidizerTempBand`` sunucunun bandını
        min/max'a yazar, bant yoksa SINIR UYDURMAZ."""
        from hrma.data.external_data_fetcher import OXIDIZER_LIQUID_BAND
        dilim = _sablon_dilimi('function applyOxidizerTempBand',
                               'async function updateOxidizerProperties')
        surucu = (
            "const kayit = {attrs: {}, min: null, max: null};\n"
            "const alan = {removeAttribute: function (k) "
            "{ kayit.attrs[k] = null; },"
            " set min(v) { kayit.min = v; }, set max(v) { kayit.max = v; }};\n"
            "const not = {textContent: ''};\n"
            "const document = {getElementById: function (id) "
            "{ return id === 'oxidizer_temp' ? alan : not; }};\n"
            # i18n yardımcısı ŞABLONDAN sökülür (kopya yazılmaz); sözlük
            # yüklü olmadığı için ürünün KENDİ yedek metni kullanılır.
            "const window = {};\n"
            + _sablon_fonksiyonu('i18nFmt') + "\n"
            + dilim
            + "\napplyOxidizerTempBand(JSON.parse(process.argv[2]), "
              "process.argv[3]);\n"
              "process.stdout.write(JSON.stringify("
              "{min: kayit.min, max: kayit.max, attrs: kayit.attrs, "
              "not: not.textContent}));")
        bant = list(OXIDIZER_LIQUID_BAND['n2o'])
        r = _node_kos(tmp_path, surucu, json.dumps(bant), 'n2o')
        assert r['min'] == str(bant[0]) and r['max'] == str(bant[1]), (
            f'bant alanın sınırlarına yazılmıyor: {r!r}')
        assert str(bant[0]) in r['not'], 'bant ekranda beyan edilmiyor'
        # Bandı olmayan akışkan: aralık UYDURULMAZ
        bos = _node_kos(tmp_path, surucu, json.dumps(None), 'air')
        assert bos['min'] is None and bos['max'] is None, (
            'bant yokken sınır uyduruluyor: ' + repr(bos))
        assert 'not published' in bos['not'], (
            'bant yokluğu ekranda beyan edilmiyor')

    def test_sablon_bandi_iki_daldan_da_okuyor(self):
        t = ADV_YOL.read_text(encoding='utf-8')
        assert 'result.liquid_band_K' in t and 'result.accepted_range' in t, (
            'bant yalnız tek daldan okunuyor — 400 dalında kullanıcı '
            'zarfı öğrenemez')
