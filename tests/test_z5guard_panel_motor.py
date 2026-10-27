# -*- coding: utf-8 -*-
"""ÖH Z5S / Bekçi-ödeme paketi A2 — panel · güverte · sıvı kartı · künye.

Bu dosya YENİ bir kusur aramaz. Defterde **onarıldı** durumunda bekleyen altı
kalemin kapanış şartı "bekçi borcu" olarak yazılmıştı; borç burada ödenir.
Her bekçi ürün kodunun BUGÜNKÜ davranışını değil, onarımın **sözleşmesini**
kilitler: sayı ekrana iniyor mu, künye kazanılıyor mu, veri yoksa sayı
uyduruluyor mu.

Kapsanan kalemler ve kapanış şartları
-------------------------------------
**P11S1-01** (yüksek) — yapısal panelin manşet emniyet katsayısı kullanıcının
cidarına DUYARSIZDI: 3 → 15 mm süpürmesinde ekrandaki sayı 4,00'de donuyordu.
Kapanış şartı: *"cidar süpürmesinde manşet DEĞİŞMELİ bekçisi"* (OH-Z4-02 §1).
→ ``test_a1`` / ``test_a2`` / ``test_a3``.

**P11B4-03** (orta) — kullanıcının KAZANDIĞI emniyet katsayısı ekranda hiç
yoktu; onun yerine tasarım hedefinin geri okuması "Minimum SF (all modes)"
diye basılıyordu. Kapanış şartı: P11S1-01 ile AYNI bekçi.
→ ``test_a1`` (manşet ``minimum_earned_safety_factor`` künyesiyle basılıyor),
``test_a2`` (hedef geri okuması AYRI satırda ve donuk), ``test_a4``
(kazanılmış sayı yoksa sayı UYDURULMUYOR).

**P11B1-01** (yüksek) — ısı haritası efsanesi cidar sıcaklığını çıplak
basarken ``wall_temperature_unphysical=True`` ve KRİTİK erime hükümleri
sahneye hiç girmiyordu. Kapanış şartı: *"efsane bekçisi"*.
→ ``test_b1`` (dört kritik, İKİ dilde), ``test_b2`` (kritik yoksa satır hiç
görünmez), ``test_b3`` (bayrak açık ama hüküm yayımlanmamışsa ALAN ADI).

**P12bB1-01** (kritik) — "Termal Koruma" kartı "Wall Temperature" diye
kullanıcının KENDİ ``max_wall_temp`` girdisini geri basıyordu; çözücünün
"CRITICAL … liner failure" hükmü ekrana hiç çıkmıyordu. Kapanış şartı:
*"kart bekçisi"*.
→ ``test_c1`` (çözücünün sıcaklığı + kaynağı; kullanıcının hedefi AYRI
satırda), ``test_c2`` (kritik hüküm karta iniyor), ``test_c3`` (çözülmüş
sıcaklık yoksa sayı uydurulmuyor ve kullanıcının hedefi o satıra KAYMIYOR).

**P12bB1-02** (kritik) — sayfanın kategori etiketi doğru veri tabanı
yoğunluğunu eziyordu (rp1/mmh/udmh → 800; n2o4 → 1200) ve aynı satırda
koşulsuz yeşil "Real-time Data" rozeti basılıyordu. Kapanış şartı:
*"rozet doğruluğunun kendi bekçisi"*.
→ ``test_d1`` (yerel tablo/hâl çözümü değerine "Real-time Data" BASILMAZ),
``test_d2`` (rozet yalnız gerçekten canlı bir kaynakta), ``test_d3``
(kategori yedeği form alanını EZMEZ, hâl çözümlü değer alanı günceller).

**P14H1-C4** (orta) — ``safety_factor_is_tautological`` künyesi "sayı
hedefin kendisidir" diye okunuyordu; oysa bayrak "cidarı HRMA seçti" der.
Kapanış şartı: *"künye-tanımı bekçisi"*.
→ ``test_e1`` (iki alan ayrı yayımlanıyor, künye keskin ölçütü ADIYLA anıyor),
``test_e2`` (gerçek hibrit koşumunda bayrak AÇIK ama sayı hedefi geri
OKUMUYOR — tanım çürütülebilir ve çürümüyor), ``test_e3`` (keskin ölçüt
bayrağın takma adı değil).

Yöntem
------
Flask ``test_client`` (sunucuya port BAĞLANMAZ) + node içinde GERÇEK ürün
kaynağı: ``motor_viz_deck.js``, ``panels/structural_panel.js`` ve
``templates/liquid.html``ten SÖKÜLEN fonksiyonlar. Beklenen değerler elle
yazılmaz, o koşumun KENDİ yanıtından türetilir. Kesin ondalık ÇAPALANMAZ
(eşzamanlı onarımlar değeri kaydırabilir); kilitlenen şey davranıştır:
"değişiyor mu", "hangi alandan geliyor", "yoksa ne basılıyor".

Ölçüm kanıtı: ``docs/scofield/raw/OH/Z5S/guard2/``.
"""

import json
import html as html_mod
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
DECK_JS = STATIC_JS / 'motor_viz_deck.js'
I18N_COMMON_JS = STATIC_JS / 'i18n_common.js'
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Uygulama yalnız geri döngü Host başlığına yanıt verir (DNS-rebinding kapısı)
HEADERS = {'Host': '127.0.0.1:8080'}

#: Panelin KENDİ alan varsayılanları (structural_panel.js `fields`), cidar
#: hariç. Manşet süpürmesi bu yükün üstüne cidar ekleyerek yapılır.
#: ÖH D15 birleştirme (1 Eyl 2026) — ``chamber_temperature`` 0,0 İDİ.
#: Yapısal kulvar ``/analyze_structural_safety``e fiziksel girdi kapısı
#: koydu: sıfır/negatif kamara sıcaklığı 422 + ``must_be_positive`` ile
#: reddediliyor (fail-closed, kazanır). 0 burada "verilmedi" nöbetçisi
#: DEĞİLDİ, yalnız dolgu sayıydı — bu bekçilerin konusu CİDAR süpürmesi.
#: Kampanyanın kanonik sıcaklığı (3000 K, bkz. ``test_z5s_hukum_kanali``
#: TERMAL gövdesi) kullanılıyor; ``wall_thickness=0`` nöbetçisi ise
#: DOKUNULMADAN duruyor, çünkü asıl ölçülen iddia odur.
PANEL_YUKU = {
    'chamber_pressure': 40.0,
    'chamber_diameter': 0.1,
    'chamber_length': 0.5,
    'throat_diameter': 0.02,
    'burn_time': 10.0,
    'chamber_temperature': 3000.0,
    'thrust': 0.0,
    'material': 'steel_4130',
}

#: Cidar süpürmesi (mm). Defter kalemi 3 → 15 mm aralığını anıyor; ortadaki
#: nokta süpürmenin tek bir uçtan değil bütünüyle duyarlı olduğunu gösterir.
CIDAR_SUPURMESI_MM = (3.0, 8.0, 15.0)

#: Varsayılan hibrit koşusu (P11B1-01 ve P14H1-C4 ölçümlerinin yükü).
#: Ağır adımlar kapalı: bekçi yanıt ŞEKLİNİ sınıyor, CAD/yörünge üretmiyor.
HIBRIT_YUKU = {
    'motor_type': 'hybrid',
    'thrust': 1000, 'burn_time': 10, 'of_ratio': 2.5,
    'chamber_pressure': 20.0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'calculate_trajectory': False, 'generate_cad': False,
    'include_3d_visualization': False, 'include_realtime_dashboard': False,
}

#: P11B1-01'in ölçülen dört KRİTİK hükmü (kodlar; metinler sözlükten gelir).
KRITIK_TERMAL_KODLAR = (
    'warn.thermal.wall_exceeds_melting',
    'warn.thermal.wall_pinned_adiabatic',
    'warn.thermal.temp_exceeds_allowable',
    'warn.thermal.max_temp_exceeds_melting',
)


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------
def _duzle(html):
    """Boşlukları tekilleştirir (satır kırığı iddiayı bozmasın)."""
    return re.sub(r'\s+', ' ', html or '')


def _metin(html):
    """Etiketleri söker; ekranda GÖRÜNEN metni bırakır."""
    return _duzle(re.sub(r'<[^>]*>', ' ', html or ''))


def _node_kos(script_src, tmp_path, ad, *args):
    """Verilen JS'i node'da çalıştırır; JSON çıktısını döner."""
    script = tmp_path / (ad + '.js')
    script.write_text(script_src, encoding='utf-8')
    proc = subprocess.run([NODE, str(script)] + [str(a) for a in args],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, ('node koşumu çöktü (%s):\n%s'
                                  % (ad, proc.stderr[-3000:]))
    return json.loads(proc.stdout)


def _sablon_fonksiyonu(html, ad):
    """``liquid.html`` içindeki üst düzey fonksiyon gövdesini söker.

    Sayfadaki üst düzey fonksiyonlar 8 boşluk girintili ve kapanışları da
    öyle — ``tests/test_faz6_f1a_kati.py`` ile AYNI sökme kuralı.
    """
    for imle in ('\n        function %s(' % ad,
                 '\n        async function %s(' % ad):
        bas = html.find(imle)
        if bas >= 0:
            break
    assert bas >= 0, '%s fonksiyonu liquid.html içinde yok' % ad
    son = html.find('\n        }\n', bas)
    assert son > bas, '%s fonksiyonunun kapanışı bulunamadı' % ad
    return html[bas + 1:son + len('\n        }')]


def _i18n_sozlugu(lang):
    """``i18n_common.js`` içindeki dil bloğunu sözlüğe çevirir.

    ``tests/test_z5i18n_supurme.py`` ile aynı sökme kuralı; metinler ÜRÜN
    dosyasından gelir, bekçi kendi çevirisini uydurmaz.
    """
    kaynak = I18N_COMMON_JS.read_text(encoding='utf-8')
    m = re.search(r'^\s{8}%s:\s*\{' % lang, kaynak, re.M)
    assert m, 'i18n_common.js içinde %r bloğu yok' % lang
    govde = kaynak[m.end():]
    govde = govde[:govde.index('\n        }')]
    ciftler = re.findall(r"^\s*'([^']+)':\s*'(.*)',?$", govde, re.M)
    return dict((k, re.sub(r'\\u([0-9a-fA-F]{4})',
                           lambda mm: chr(int(mm.group(1), 16)),
                           v.rstrip(',').rstrip("'")))
                for k, v in ciftler)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ===========================================================================
# A — MANŞET EMNİYET KATSAYISI  (P11S1-01 · P11B4-03)
# ===========================================================================
#: Gerçek ``structural_panel.js``i sahte DOM'da koşturan düzenek. Panel
#: ``AnalysisDock``a kayıtlı olduğu için önce güverte kaynağı yüklenir.
PANEL_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const [staticDir, payloadPath] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = []; this.style = {}; this._attrs = {}; this.innerHTML = '';
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return this._attrs[k] === undefined ? null : this._attrs[k]; };
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
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
    Promise: Promise, isFinite: isFinite, parseFloat: parseFloat,
    parseInt: parseInt, document: documentStub,
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
function run(f) { vm.runInContext(fs.readFileSync(f, 'utf8'), sandbox, { filename: f }); }
run(path.join(staticDir, 'analysis_dock.js'));
run(path.join(staticDir, 'panels', 'structural_panel.js'));

const out = { renders: {} };
Object.keys(payload.panelResponses || {}).forEach(function (k) {
    const root = new El('div');
    sandbox.window.StructuralPanel._render(payload.panelResponses[k], root);
    out.renders[k] = root.innerHTML;
});
process.stdout.write(JSON.stringify(out));
"""


def test_a0_sifir_kamara_sicakligi_ARTIK_reddediliyor(client):
    """ÖH D15 birleştirme kaydı: yukarıdaki yükün NEDEN değiştiği.

    Bu bekçiler taban ağacında ``chamber_temperature=0.0`` ile koşuyordu.
    Yapısal kulvarın kapısı o gövdeyi artık reddediyor; karar burada
    ÖLÇÜLEREK saklanır ki yük sessizce geri alınmasın.
    """
    r = client.post('/analyze_structural_safety',
                    json=dict(PANEL_YUKU, chamber_temperature=0.0,
                              wall_thickness=0.005), headers=HEADERS)
    assert r.status_code == 422, r.get_data(as_text=True)[:200]
    govde = r.get_json()
    assert govde['error'] == 'invalid_structural_input', govde
    kusur = {k['field']: k for k in (govde.get('invalid_fields') or [])}
    assert kusur['chamber_temperature']['reason'] == 'must_be_positive', govde


@pytest.fixture(scope='module')
def panel_supurmesi(client):
    """Cidar süpürmesinin GERÇEK ``/analyze_structural_safety`` yanıtları."""
    out = {}
    for mm in CIDAR_SUPURMESI_MM:
        r = client.post('/analyze_structural_safety',
                        json=dict(PANEL_YUKU, wall_thickness=mm / 1000.0),
                        headers=HEADERS)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        out['%g' % mm] = r.get_json()
    return out


@pytest.fixture(scope='module')
def panel_cidarsiz(client):
    """Cidar VERİLMEMİŞ koşum: uç cidarı kendi boyutlandırır."""
    r = client.post('/analyze_structural_safety',
                    json=dict(PANEL_YUKU, wall_thickness=0.0), headers=HEADERS)
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def panel_ciziimleri(panel_supurmesi, panel_cidarsiz, tmp_path_factory):
    """Süpürmenin + cidarsız koşumun GERÇEK panel çıktısı (node)."""
    if NODE is None:
        pytest.skip('node kurulu değil')
    tmp = tmp_path_factory.mktemp('z5guard_panel')
    yanitlar = dict(panel_supurmesi)
    yanitlar['cidarsiz'] = panel_cidarsiz
    girdi = tmp / 'panel_girdi.json'
    girdi.write_text(json.dumps({'panelResponses': yanitlar}), encoding='utf-8')
    return _node_kos(PANEL_HARNESS, tmp, 'panel_kos', STATIC_JS, girdi)['renders']


def _kunyeli_satirin_hucresi(html, alan):
    """``alan`` künyesini ETİKETİNDE taşıyan satırın DEĞER hücresi.

    Etiket künyeyi ``<span>…</span></strong>`` içinde taşır; hücre etiketin
    hemen ardındaki ``<td>``dur.

    ÖH D24 / fix-22 — SEÇİCİ KESKİNLEŞTİRİLDİ, İDDİA DEĞİŞMEDİ. Eski hâl
    künyeyi düz metin araması (``find``) ile arıyordu. D23 (OH-D22-05)
    panele ``headline_safety_factor`` satırını ekledi ve o satırın künye
    ipucu (``title="…"``) hüküm geri çekildiğinde ucun KENDİ cümlesini
    basıyor: *"… minimum_earned_safety_factor covers only the stations
    that were actually measured …"*. ÖLÇÜLDÜ (taban kaydı-7, 8 mm cidar
    çizimi): ``minimum_earned_safety_factor`` dizesinin İLK geçtiği yer
    (idx 9858) manşet etiketi değil, ÜSTTEKİ satırın ``title`` ipucuydu;
    seçici bu yüzden yanlış satırın hücresini döndürüyor ve bekçi ürün
    doğru davranırken kırmızı veriyordu. Artık künye yalnız ETİKET
    işaretlemesinde aranır — sınanan hücre gerçekten o satırındır.
    """
    duz = _duzle(html)
    m = re.search(r'>\s*%s\s*</span>\s*</strong>' % re.escape(alan), duz)
    assert m, '%s satırı künyesiyle basılmıyor' % alan
    j = duz.find('<td', m.end())
    assert j > 0, '%s değer hücresi yok' % alan
    k = duz.find('</td>', j)
    return duz[j:k]


def _manset_hucresi(html):
    """Manşet satırının DEĞER hücresi (``minimum_earned_safety_factor``)."""
    return _kunyeli_satirin_hucresi(html, 'minimum_earned_safety_factor')


def _ilk_sayi(metin):
    m = re.search(r'-?\d+(?:\.\d+)?', _metin(metin))
    return float(m.group(0)) if m else None


@node_gerekli
def test_a1_manset_cidar_supurmesinde_degisiyor(panel_ciziimleri,
                                                panel_supurmesi):
    """P11S1-01 · P11B4-03 — manşet 3/8/15 mm'de DONUK KALAMAZ.

    Kilitlenen şey sayı değil DAVRANIŞ: üç cidar üç ayrı manşet üretmeli ve
    ekrandaki sayı ucun ``minimum_earned_safety_factor`` alanından gelmeli
    (hedefin geri okumasından değil).
    """
    okunan = {}
    for anahtar in ('%g' % mm for mm in CIDAR_SUPURMESI_MM):
        hucre = _manset_hucresi(panel_ciziimleri[anahtar])
        ekran = _ilk_sayi(hucre)
        assert ekran is not None, (
            'manşet %s mm cidarda sayı basmıyor: %s' % (anahtar, _metin(hucre)))
        ucun = ((panel_supurmesi[anahtar].get('structural_analysis') or {})
                .get('safety_analysis') or {}).get('minimum_earned_safety_factor')
        assert isinstance(ucun, (int, float)), (
            'uç %s mm cidarda kazanılmış SF yayımlamıyor' % anahtar)
        # Ekrandaki sayı ucun ALANINDAN gelmeli (yuvarlama payıyla).
        assert abs(ekran - round(float(ucun), 2)) <= 0.011, (
            'manşet ucun minimum_earned_safety_factor alanını basmıyor: '
            'ekran %s ⟷ uç %s' % (ekran, ucun))
        okunan[anahtar] = ekran

        # ÖH D24 / fix-22 — YENİ MANŞET KAYNAĞI DA AYNI SÖZLEŞMEYİ TAŞIR.
        # D23 (OH-D22-05) panelin ilk satırına ``headline_safety_factor``
        # ekledi; o satır bu satırın YERİNE geçmiyor ama ekranın EN ÜST
        # sayısı oldu. Kural aynı kuraldır: sayı UYDURULMAZ. Uç sayıyı
        # yayımlıyorsa ekran ONU basar; hüküm geri çekilmişse (alan null,
        # ölçüldü: 8 ve 15 mm cidarda ``verdict_withheld = True``) hane
        # "—" kalır ve nedeni ALAN ADIYLA yazılır.
        sfa = ((panel_supurmesi[anahtar].get('structural_analysis') or {})
               .get('safety_analysis') or {})
        if sfa.get('headline_safety_factor_source'):
            manset = _kunyeli_satirin_hucresi(panel_ciziimleri[anahtar],
                                              'headline_safety_factor')
            ucun_manset = sfa.get('headline_safety_factor')
            if isinstance(ucun_manset, (int, float)):
                ekran_manset = _ilk_sayi(manset)
                assert ekran_manset is not None and abs(
                    ekran_manset - round(float(ucun_manset), 2)) <= 0.011, (
                    'manşet satırı ucun headline_safety_factor alanını '
                    'basmıyor (%s mm): ekran %s ⟷ uç %s'
                    % (anahtar, ekran_manset, ucun_manset))
            else:
                assert '—' in manset, (
                    'hüküm geri çekilmişken manşet satırında sayı var '
                    '(%s mm): %s' % (anahtar, _metin(manset)))
                assert 'headline_safety_factor' in manset, (
                    'manşet sayısının neden yok olduğu ALAN ADIYLA '
                    'yazılmıyor (%s mm): %s' % (anahtar, _metin(manset)))

    assert len(set(okunan.values())) == len(okunan), (
        'MANŞET CİDARA SAĞIR (P11S1-01 geri döndü): süpürmede ekrandaki '
        'kazanılmış SF donuk kaldı — %r' % okunan)


@node_gerekli
def test_a2_hedef_geri_okumasi_ayri_satirda_ve_donuk(panel_ciziimleri,
                                                     panel_supurmesi):
    """P11B4-03 — "Minimum SF (all modes)" AYRI satır ve manşet DEĞİL.

    Kusurun özü iki sayının tek satırda birleştirilmesiydi. Bekçi ikisinin
    AYRI kaldığını, üstelik bu satırın süpürmede donuk olduğunu (yani
    manşetin ondan gelmediğini) kilitler.
    """
    hedef_ekran = set()
    for anahtar in ('%g' % mm for mm in CIDAR_SUPURMESI_MM):
        duz = _duzle(panel_ciziimleri[anahtar])
        assert 'Minimum SF (all modes)' in duz, (
            'bütün-modlar satırı %s mm cidarda basılmıyor' % anahtar)
        assert 'minimum_earned_safety_factor' in duz, (
            'manşet künyesi %s mm cidarda basılmıyor' % anahtar)
        # İki satır AYRI: künye etiketleri aynı hücrede değil.
        assert duz.find('minimum_earned_safety_factor') != duz.find(
            'Minimum SF (all modes)')
        sfa = ((panel_supurmesi[anahtar].get('structural_analysis') or {})
               .get('safety_analysis') or {})
        hedef_ekran.add((anahtar,
                         round(float(sfa['minimum_safety_factor']), 2),
                         round(float(sfa['minimum_earned_safety_factor']), 2)))

    # ÖH D15 birleştirme (1 Eyl 2026) — DAYANAK DEĞİŞTİ, İDDİA DEĞİŞMEDİ.
    # Eski ayak "bütün modlar satırı süpürmede DONUK" diyordu; o donukluk
    # ``chamber_temperature=0`` yükünün yan ürünüydü. Yapısal kulvarın
    # girdi kapısı o yükü artık reddediyor (bkz.
    # ``test_a0_sifir_kamara_sicakligi_ARTIK_reddediliyor``) ve gerçek bir
    # sıcaklıkta "bütün modlar" sayısı da cidara tepki veriyor (ölçüldü:
    # 3/8/15 mm -> 2,39 / 4,00 / 4,00 ⟷ manşet 2,39 / 5,62 / 8,73).
    # P11B4-03'ün İDDİASI donukluk değil AYRIKLIKTI: manşet "bütün modlar"
    # sayısından GELMİYOR. Bu artık doğrudan ölçülüyor ve daha güçlü:
    # en az bir cidarda iki sayı AYRIŞMALI, üstelik manşet o cidarda
    # kazanılmış SF'yi basmalı (a1 satır satır sınıyor).
    ayrisan = [(a, hedef, manset) for a, hedef, manset in hedef_ekran
               if abs(hedef - manset) > 0.011]
    assert ayrisan, (
        'bu bekçinin dayanağı düştü: hiçbir cidarda "bütün modlar" ile '
        'manşet ayrışmıyor (%r) — ikisinin ayrı satır olduğu iddiası '
        'ölçülemez hâle geldi, önce onu doğrulayın' % sorted(hedef_ekran))


def test_a3_calculate_ucu_da_cidara_duyarli(client):
    """P11S1-01 — motor ucu da kullanıcının cidarını GERÇEKTEN sınıyor.

    Panelin kıyas satırı (``motorSolve``) motor koşumunun kendi asgari
    katsayısını basar; o sayı da cidara sağır olsaydı ekranda ikinci bir
    donuk sayı kalırdı.
    """
    okunan = {}
    for mm in CIDAR_SUPURMESI_MM:
        r = client.post('/calculate', json=dict(HIBRIT_YUKU, wall_thickness=mm),
                        headers=HEADERS)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        sa = (r.get_json().get('motor') or {}).get('structural_analysis') or {}
        ca = sa.get('chamber_analysis') or {}
        sfa = sa.get('safety_analysis') or {}
        assert ca.get('design_mode') == 'verify', (
            '%g mm cidar gönderildiği hâlde uç doğrulama moduna geçmiyor' % mm)
        assert abs(float(ca['wall_thickness_used_mm']) - mm) <= 1e-6, (
            'gönderilen cidar hesaba girmiyor (%g mm)' % mm)
        okunan['%g' % mm] = sfa.get('minimum_earned_safety_factor')
    assert all(isinstance(v, (int, float)) for v in okunan.values()), (
        'kullanıcının cidarı sınandığı hâlde kazanılmış SF yayımlanmıyor: %r'
        % okunan)
    assert len(set(round(float(v), 6) for v in okunan.values())) == len(okunan), (
        '/calculate kazanılmış SF cidara sağır: %r' % okunan)


@node_gerekli
def test_a4_kazanilmis_sf_yoksa_sayi_uydurulmuyor(panel_ciziimleri,
                                                  panel_cidarsiz):
    """P11B4-03 — fail-closed: cidarı HRMA boyutlandırdıysa manşette sayı YOK.

    Bu kalemin en tehlikeli onarımı, manşete "bir şeyler" basmak olurdu:
    HRMA'nın kendi cidarına verdiği katsayı kullanıcının kazandığı marj
    DEĞİLDİR. Alan yoksa hane "—" kalır ve nedeni ALAN ADIYLA yazılır.
    """
    sfa = ((panel_cidarsiz.get('structural_analysis') or {})
           .get('safety_analysis') or {})
    assert sfa.get('minimum_earned_safety_factor') is None, (
        'fikstür dayanağı düştü: cidarsız koşumda uç artık kazanılmış SF '
        'yayımlıyor — bu bekçi yeniden ölçülmeli')
    hucre = _manset_hucresi(panel_ciziimleri['cidarsiz'])
    assert '—' in hucre, 'kazanılmış SF yokken hane "—" kalmıyor: %s' % _metin(hucre)
    assert 'minimum_earned_safety_factor' in hucre, (
        'sayının neden yok olduğu ALAN ADIYLA yazılmıyor: %s' % _metin(hucre))
    assert _ilk_sayi(hucre) is None, (
        'kazanılmış SF yokken manşete SAYI basılıyor (uydurma): %s'
        % _metin(hucre))


# ===========================================================================
# B — ISI HARİTASI EFSANESİ  (P11B1-01)
# ===========================================================================
#: Gerçek ``motor_viz_deck.js``i sahte DOM'da kuran düzenek. Sahne
#: (``MotorViz3D``) taklit edilir — bekçi 3B çizimi değil, güvertenin
#: yükten HÜKÜM okuyup okumadığını ölçer.
DECK_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const [deckPath, payloadPath] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

function CL() { this._s = {}; }
CL.prototype.toggle = function (k, v) { this._s[k] = !!v; };
CL.prototype.add = function (k) { this._s[k] = true; };
CL.prototype.remove = function (k) { delete this._s[k]; };
CL.prototype.contains = function (k) { return !!this._s[k]; };

function El(id) {
    this.id = id; this.style = { setProperty: function () {} };
    this.classList = new CL(); this.children = []; this.innerHTML = '';
    this.textContent = ''; this._attrs = {}; this.onclick = null;
    this.oninput = null; this.value = '0'; this.dataset = {};
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return this._attrs[k] === undefined ? null : this._attrs[k]; };
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.addEventListener = function () {};

const REG = Object.create(null);
function getEl(id) { if (!REG[id]) REG[id] = new El(id); return REG[id]; }

const vizStub = {
    state: { heatMap: false, playing: false },
    getHeatInfo: function () { return payload.heatInfo || null; },
    setHeatMap: function (v) { this.state.heatMap = !!v; return !!v; },
    setPortShape: function () {}, cyclePortShape: function () { return 'star'; },
    cycleSpeed: function () { return 1; },
    cycleCameraPreset: function () { return 'iso'; },
    getCfdField: function () { return null; }, clearCfdField: function () {},
    setCfdMetric: function () {}, setCutaway: function () {},
    setExploded: function () {}, setLabels: function () {},
    setPlume: function () {}, setQuality: function () {},
    setAutoRotate: function () {}, setTime: function () {},
    resetCamera: function () {}, play: function () {}, pause: function () {},
    snapshot: function () { return null; }, update: function () {},
    dims: {}, cfd: {},
};

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: function () {}, clearTimeout: function () {},
    setInterval: function () {}, clearInterval: function () {},
    requestAnimationFrame: function () {}, cancelAnimationFrame: function () {},
    performance: { now: function () { return 0; } },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, Date: Date,
    Promise: Promise, isFinite: isFinite, parseFloat: parseFloat,
    parseInt: parseInt, isNaN: isNaN,
    document: { body: new El('body'), head: new El('head'),
                readyState: 'complete', getElementById: getEl,
                createElement: function (t) { return new El(t); },
                querySelector: function () { return null; },
                querySelectorAll: function () { return []; },
                addEventListener: function () {} },
    MotorViz3D: { isSupported: function () { return true; },
                  mount: function () { return vizStub; } },
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
if (payload.i18n) {
    sandbox.I18N = {
        tf: function (code, params, fb) {
            const d = payload.i18n[code];
            if (d === undefined) return fb === undefined ? code : fb;
            return d.replace(/\{(\w+)\}/g, function (m, k) {
                return (params && params[k] !== undefined) ? String(params[k]) : m;
            });
        },
        t: function (k, fb) {
            return payload.i18n[k] === undefined
                ? (fb === undefined ? k : fb) : payload.i18n[k];
        },
    };
}
vm.createContext(sandbox);
// ÖH D25 · arayuz a3: units_constants.js güverteden ÖNCE (PA_PER_BAR
// tek kaynak; motor_viz_deck.js yoksa fail-closed fırlatır).
vm.runInContext(fs.readFileSync(path.join(path.dirname(deckPath),
                'units_constants.js'), 'utf8'), sandbox,
                { filename: 'units_constants.js' });
vm.runInContext(fs.readFileSync(deckPath, 'utf8'), sandbox, { filename: deckPath });

const out = {};
out.created = !!sandbox.window.MotorVizDeck.create(
    'host', payload.motorData, payload.opts || {});
const btnId = Object.keys(REG).filter(function (i) {
    return /_btn_heat$/.test(i); })[0];
out.btnId = btnId || null;
out.btnHidden = btnId ? (REG[btnId].style.display === 'none') : null;
if (btnId && REG[btnId].onclick) { REG[btnId].onclick(); out.clicked = true; }
const ids = Object.keys(REG);
const vId = ids.filter(function (i) { return /_hl_verdict$/.test(i); })[0];
const wId = ids.filter(function (i) { return /_hl_wall$/.test(i); })[0];
out.verdictHtml = vId ? REG[vId].innerHTML : null;
out.verdictDisplay = vId ? REG[vId].style.display : null;
out.wallText = wId ? REG[wId].textContent : null;
process.stdout.write(JSON.stringify(out));
"""


def _heat_info(motor):
    """``motor_viz3d.js``in ısı sözlüğünü AYNI kurallarla kurar.

    Sayı UYDURULMAZ: dördü de motorun kendi ısı zincirinden gelir. Sahne
    taklit edildiği için bu sözlüğü bekçi kurar; kuralı (``motor_viz3d.js``
    ``dims.heat``) birebir aynıdır.
    """
    ht = motor.get('heat_transfer_analysis') or {}
    gas = ht.get('gas_side_analysis') or {}
    wall = ht.get('wall_analysis') or {}
    if not gas.get('throat_heat_flux'):
        return None
    return {
        'qThroat': gas.get('throat_heat_flux'),
        'qChamber': gas.get('chamber_heat_flux',
                            gas.get('throat_heat_flux') * 0.12),
        'tWallInner': wall.get('inner_temperature'),
        'tWallOuter': wall.get('outer_temperature'),
    }


@pytest.fixture(scope='module')
def hibrit_sonuc(client):
    """Varsayılan hibrit koşumunun GERÇEK ``/calculate`` yanıtı."""
    r = client.post('/calculate', json=dict(HIBRIT_YUKU), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


def _guverte_kos(tmp_path, motor, i18n=None, ad='guverte'):
    girdi = tmp_path / (ad + '_girdi.json')
    girdi.write_text(json.dumps({
        'motorData': motor,
        'heatInfo': _heat_info(motor),
        'opts': {'motorType': 'hybrid'},
        'i18n': i18n,
    }), encoding='utf-8')
    return _node_kos(DECK_HARNESS, tmp_path, ad + '_kos', DECK_JS, girdi)


@node_gerekli
@pytest.mark.parametrize('lang', ['en', 'tr'])
def test_b1_efsane_dort_kritigi_iki_dilde_basiyor(hibrit_sonuc, tmp_path, lang):
    """P11B1-01 — efsane çıplak sayının yanına çözücünün hükmünü basar.

    Ölçülen kusur: efsane ``T_wall inner … K`` diye çıplak sayı basarken
    aynı yükte duran ``wall_temperature_unphysical`` ve dört KRİTİK hüküm
    sahneye hiç girmiyordu — eriyen bir motorun ısı haritası sağlıklı
    görünüyordu. Metin efsanede ÜRETİLMEZ; sözlükten gelir, o yüzden iki
    dilde de sınanır.
    """
    motor = hibrit_sonuc['motor']
    ht = motor.get('heat_transfer_analysis') or {}
    gas = ht.get('gas_side_analysis') or {}
    assert gas.get('wall_temperature_unphysical') is True, (
        'fikstür dayanağı düştü: varsayılan hibrit koşumu artık fizik-dışı '
        'cidar sıcaklığı üretmiyor — bu bekçi yeniden ölçülmeli')
    kodlar = set()
    for blok in ('gas_side_analysis', 'safety_analysis', 'wall_analysis'):
        for w in (ht.get(blok) or {}).get('warnings') or []:
            if isinstance(w, dict) and str(w.get('severity', '')).lower() == 'critical':
                kodlar.add(w.get('code'))
    assert set(KRITIK_TERMAL_KODLAR) <= kodlar, (
        'fikstür dayanağı düştü: dört kritik koddan bazıları artık '
        'üretilmiyor (%r)' % sorted(kodlar))

    sozluk = _i18n_sozlugu(lang)
    out = _guverte_kos(tmp_path, motor, i18n=sozluk, ad='b1_' + lang)
    assert out['created'], 'güverte kurulmadı'
    assert out['clicked'], 'ısı haritası düğmesi kablolanmamış'
    assert out['verdictDisplay'] == 'block', (
        'kritik hüküm varken hüküm satırı gizli: %r' % out['verdictDisplay'])
    basilan = _metin(out['verdictHtml'])
    assert sozluk['app.warn.critical'] in basilan, (
        '%s efsanesi KRİTİK önekini basmıyor: %s' % (lang, basilan))
    for kod in KRITIK_TERMAL_KODLAR:
        sablon = sozluk.get(kod)
        assert sablon, 'i18n_common.js %s bloğunda %s yok' % (lang, kod)
        # Yer tutucular parametreyle dolduğu için sabit parçalar aranır.
        parcalar = [p.strip() for p in re.split(r'\{\w+\}', sablon)
                    if len(p.strip()) >= 12]
        assert parcalar, 'sözlük satırı sınanacak kadar metin taşımıyor: %s' % kod
        assert all(p in basilan for p in parcalar), (
            'efsane %s dilinde %s hükmünü basmıyor.\nbeklenen parçalar: %r'
            '\nbasılan: %s' % (lang, kod, parcalar, basilan))
        assert kod not in basilan, (
            '%s hükmü çevrilmeden HAM KOD olarak basılıyor (%s)' % (kod, lang))


@node_gerekli
def test_b2_kritik_yoksa_hukum_satiri_hic_gorunmez(hibrit_sonuc, tmp_path):
    """P11B1-01 fail-closed ayağı — uydurma rozet YASAK.

    Sağlıklı bir ısı zincirinde (hüküm yok, bayrak kapalı) satır hiç
    basılmamalı; "hüküm satırı hep görünsün" onarımı, kullanıcıyı her
    motorda kırmızıya alıştırıp gerçek kritiği görünmez kılardı.
    """
    motor = json.loads(json.dumps(hibrit_sonuc['motor']))
    ht = motor.get('heat_transfer_analysis') or {}
    for blok in ('gas_side_analysis', 'safety_analysis', 'wall_analysis'):
        if isinstance(ht.get(blok), dict):
            ht[blok]['warnings'] = []
    (ht.get('gas_side_analysis') or {})['wall_temperature_unphysical'] = False
    out = _guverte_kos(tmp_path, motor, i18n=_i18n_sozlugu('en'), ad='b2')
    assert out['created'] and out['clicked']
    assert out['verdictDisplay'] == 'none', (
        'hüküm yokken satır görünüyor: %r' % out['verdictDisplay'])
    assert not _metin(out['verdictHtml']).strip(), (
        'hüküm yokken satıra metin basılıyor: %r' % out['verdictHtml'])
    # Çıplak sayı yine basılır — kaldırılan şey sayı değil, sessizliktir.
    assert 'T_wall' in (out['wallText'] or ''), (
        'ısı efsanesinin cidar satırı kayboldu: %r' % out['wallText'])


@node_gerekli
def test_b3_bayrak_acik_hukum_yayimlanmamissa_alan_adi_basilir(hibrit_sonuc,
                                                               tmp_path):
    """P11B1-01 — ``wall_temperature_unphysical`` ASLA sessiz kalmaz.

    Hüküm listesi boşalsa bile bayrak açıksa satır basılır ve alanın MAKİNE
    ADINI yazar: "fizik-dışı" bilgisi hiçbir yoldan ekrandan düşemez.
    """
    motor = json.loads(json.dumps(hibrit_sonuc['motor']))
    ht = motor.get('heat_transfer_analysis') or {}
    for blok in ('gas_side_analysis', 'safety_analysis', 'wall_analysis'):
        if isinstance(ht.get(blok), dict):
            ht[blok]['warnings'] = []
    (ht.get('gas_side_analysis') or {})['wall_temperature_unphysical'] = True
    out = _guverte_kos(tmp_path, motor, i18n=_i18n_sozlugu('en'), ad='b3')
    assert out['verdictDisplay'] == 'block', (
        'bayrak açıkken hüküm satırı gizli: %r' % out['verdictDisplay'])
    assert 'wall_temperature_unphysical' in _metin(out['verdictHtml']), (
        'bayrağın alan adı basılmıyor: %r' % out['verdictHtml'])


# ===========================================================================
# C — SIVI "TERMAL KORUMA" KARTI  (P12bB1-01)
# ===========================================================================
#: Tarayıcıda ``hrma/static/js/i18n.js`` hem ``T`` hem ``TF``i KÜRESEL
#: tanımlar (``global.T`` / ``global.TF``), yani şablonun sökülen bloğu
#: ikisini de dışarıdan bulur. Sandbox'lar da İKİSİNİ birden sağlamak
#: zorundadır: ÖH D29 arayuz-panel a3 kart bloğuna ``TF(...)`` ekleyince
#: yalnız ``T`` tanımlayan düzenekler "ReferenceError: TF is not defined"
#: ile çöktü (ÖH D30 / fix-29b). Burası TEK tanım noktasıdır; harness
#: dizeleri bunu birleştirir, kopya yazmaz. Aşağıdaki bekçi de dosyadaki
#: her sandbox literalinin ikisini birden taşıdığını sınar.
I18N_STUB_JS = """\
    T: function (k, fb) {
        return dict[k] === undefined ? (fb === undefined ? k : fb) : dict[k]; },
    TF: function (k, p, fb) {
        const ham = dict[k] === undefined ? (fb === undefined ? k : fb) : dict[k];
        let s = String(ham);
        Object.keys(p || {}).forEach(function (n) {
            s = s.split('{' + n + '}').join(String(p[n])); });
        return s; },"""

#: ``liquid.html``ten sökülen kart üreticisini sahte DOM'da koşturan düzenek.
LIQCARD_HARNESS = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [srcPath, payloadPath] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

function El(tag) { this.tagName = String(tag).toUpperCase(); this.children = [];
    this.innerHTML = ''; this.className = ''; this.style = {}; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
const grid = new El('div');
const dict = payload.i18n || {};

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, isFinite: isFinite,
    parseFloat: parseFloat, parseInt: parseInt,
    document: {
        getElementById: function (id) {
            return id === 'subsystemsGrid' ? grid : null; },
        createElement: function (t) { return new El(t); },
    },
""" + I18N_STUB_JS + r"""
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(srcPath, 'utf8'), sandbox,
                { filename: 'liquid-sokum.js' });
sandbox.displayEngineeringCards(payload.results);
process.stdout.write(JSON.stringify({
    cards: grid.children.map(function (c) { return c.innerHTML; }) }));
"""


@pytest.fixture(scope='module')
def sivi_sonuc(client):
    """Örnek LOX/RP-1 projesinin GERÇEK ``/calculate_liquid`` yanıtı."""
    proje = json.loads((REPO_ROOT / 'examples'
                        / 'Example Liquid LOX-RP1 25kN.hrma')
                       .read_text(encoding='utf-8'))
    r = client.post('/calculate_liquid',
                    json=dict(proje['inputs']['fields']), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def liquid_kaynak():
    """``liquid.html``ten sökülen kart üreticisi + biçimleyicisi."""
    html = LIQUID_HTML.read_text(encoding='utf-8')
    # ÖH D15 birleştirme (1 Eyl 2026): kart üreticisi ``liquid.html``te
    # tanımlı ``liquidOverallLengthMm`` yardımcısını çağırıyor (Overall
    # Length satırı). Söküm listesi bayat kaldığı için node koşumu
    # ``ReferenceError: liquidOverallLengthMm is not defined`` ile
    # çöküyordu — kusur ÜRÜNDE değil sökümde: tarayıcıda iki fonksiyon da
    # aynı betiğin küresel kapsamında duruyor. Çağrılan yardımcı sökülen
    # kümeye eklendi.
    # ÖH D35 (22 Eyl) — AYNI DERS, İKİNCİ KEZ: sayfanın sayı
    # biçimi artık ortak `numTxt` delegatöründen geçiyor (OH-GT-25,
    # i18n.js kanonu). Tarayıcıda ikisi de aynı küresel kapsamdadır;
    # söküm listesi bayat kalırsa node `numTxt is not defined` der.
    # Kusur yine ÜRÜNDE değil SÖKÜMDE.
    # v3.0.1 T-ÇAPA-B — AYNI DERS, ÜÇÜNCÜ KEZ: kart üreticisi model
    # geçerlilik rozetini ortak sözlük yardımcısı ``ortakMetin`` (ÖH D37 A1b,
    # liquid.html) ile yazıyor; söküm listesi bayattı → node
    # ``ortakMetin is not defined``. Kusur ÜRÜNDE değil SÖKÜMDE.
    return '\n'.join([_sablon_fonksiyonu(html, 'numTxt'),
                      _sablon_fonksiyonu(html, 'hrmaFmt'),
                      _sablon_fonksiyonu(html, 'ortakMetin'),
                      _sablon_fonksiyonu(html, 'liquidOverallLengthMm'),
                      _sablon_fonksiyonu(html, 'displayEngineeringCards')])


def _kart_kos(tmp_path, kaynak, results, ad):
    src = tmp_path / (ad + '_src.js')
    src.write_text(kaynak, encoding='utf-8')
    girdi = tmp_path / (ad + '_girdi.json')
    girdi.write_text(json.dumps({'results': results}), encoding='utf-8')
    out = _node_kos(LIQCARD_HARNESS, tmp_path, ad + '_kos', src, girdi)
    for kart in out['cards']:
        if 'Thermal Protection' in kart:
            return kart
    return None


def _satir(kart, etiket):
    """Kartın ``<tr><td>etiket:</td><td>DEĞER</td></tr>`` satırının değeri."""
    duz = _duzle(kart)
    m = re.search(re.escape('<td>' + etiket + ':</td><td>') + r'(.*?)</td>', duz)
    return m.group(1).strip() if m else None


@node_gerekli
def test_c1_kart_cozucunun_sicakligini_basiyor_kullanicinin_hedefini_degil(
        sivi_sonuc, liquid_kaynak, tmp_path):
    """P12bB1-01 — "Wall Temperature" artık ÇÖZÜCÜNÜN sayısı.

    Ölçülen kusur: kart "Wall Temperature 800 K" yazıyordu; 800 K
    kullanıcının form alanına girdiği HEDEFTİ. Aynı yanıtta çözücünün
    istasyon marşı çok daha yüksek bir denge sıcaklığı yayımlıyordu ve o
    sayı ekrana HİÇ çıkmıyordu. Bekçi üç şeyi ayrı ayrı kilitler: çözücünün
    sayısı, sayının KAYNAĞI, kullanıcının hedefinin AYRI satırı.
    """
    tp = sivi_sonuc.get('thermal_protection') or {}
    march = tp.get('station_march') or {}
    cozulmus = march.get('peak_wall_temperature_K')
    hedef = tp.get('wall_temperature')
    assert isinstance(cozulmus, (int, float)) and isinstance(hedef, (int, float)), (
        'fikstür dayanağı düştü: çözücü artık istasyon marşı yayımlamıyor')
    assert abs(cozulmus - hedef) > 1.0, (
        'fikstür dayanağı düştü: çözücünün sıcaklığı ile kullanıcının hedefi '
        'artık ayrışmıyor (%s ⟷ %s) — bu bekçi yeniden ölçülmeli'
        % (cozulmus, hedef))

    kart = _kart_kos(tmp_path, liquid_kaynak, sivi_sonuc, 'c1')
    assert kart, 'Termal Koruma kartı hiç basılmıyor'

    cidar = _satir(kart, 'Wall Temperature')
    assert cidar is not None, 'kartta "Wall Temperature" satırı yok'
    assert cidar == '%d K' % round(cozulmus), (
        'HEDEFİN EKOSU GERİ DÖNDÜ: "Wall Temperature" satırı çözücünün '
        '%s K değerini basmıyor, ekranda %r var' % (round(cozulmus), cidar))

    kaynak_satiri = _metin(kart)
    assert 'thermal_protection.station_march' in kaynak_satiri, (
        'çözülmüş sıcaklığın KAYNAĞI basılmıyor: %s' % kaynak_satiri[:400])
    if isinstance(march.get('material_allowable_K'), (int, float)):
        assert 'station_march.material_allowable_K' in kaynak_satiri, (
            'malzeme sınırı alan adıyla basılmıyor')

    kullanici = _satir(kart, 'Maximum Wall Temperature')
    assert kullanici == '%d K' % round(hedef), (
        'kullanıcının hedefi kendi satırında basılmıyor: %r' % kullanici)
    assert tp.get('wall_temperature_source') in kaynak_satiri, (
        'kullanıcının hedefinin kaynağı (%r) basılmıyor'
        % tp.get('wall_temperature_source'))


@node_gerekli
def test_c2_kritik_hukum_karta_iniyor(sivi_sonuc, liquid_kaynak, tmp_path):
    """P12bB1-01 — çözücünün "CRITICAL … liner failure" hükmü ekranda.

    Hüküm metni ÇÖZÜCÜDEN gelir; kart onu ne özetler ne de yeniden
    sınıflandırır — yalnız vurgular. Bekçi metnin AYNEN indiğini ve
    ciddiyet vurgusunun (kırmızı + CRITICAL imi) takıldığını kilitler.
    """
    march = (sivi_sonuc.get('thermal_protection') or {}).get('station_march') or {}
    uyarilar = [str(w).strip() for w in (march.get('warnings') or [])]
    kritikler = [w for w in uyarilar if re.match(r'^(CRITICAL|UNSAFE)\b', w, re.I)]
    assert kritikler, (
        'fikstür dayanağı düştü: çözücü artık kritik termal hüküm '
        'üretmiyor — bu bekçi yeniden ölçülmeli')

    kart = _kart_kos(tmp_path, liquid_kaynak, sivi_sonuc, 'c2')
    duz_kart = _duzle(kart)
    goruntu = _metin(kart)
    for w in uyarilar:
        # ÖH D15 birleştirme (1 Eyl 2026): karşılaştırma YALNIZ ``&``i geri
        # çeviriyordu. Kardeş kulvarın eklediği model-zarfı notu metninde
        # ``t_w << r_wall`` geçiyor; kart onu doğru biçimde ``&lt;&lt;``
        # diye kaçışlıyor ve bekçi "karta inmiyor" sanıyordu — ölçüldü:
        # ``html.escape(w) in kart`` True. Kusur ÜRÜNDE değil bu
        # karşılaştırmadaydı. Artık kaçışın tamamı çözülüyor.
        assert (html_mod.escape(w, quote=False) in duz_kart
                or w in html_mod.unescape(goruntu)), (
            'çözücünün hükmü karta inmiyor: %r' % w)
    assert 'warning-tag' in duz_kart, (
        'kritik hüküm ciddiyet imi olmadan basılıyor')
    assert '#ff7a85' in duz_kart, 'kritik hüküm kırmızıya boyanmıyor'


@node_gerekli
def test_c3_cozulmus_sicaklik_yoksa_sayi_uydurulmuyor(sivi_sonuc,
                                                      liquid_kaynak, tmp_path):
    """P12bB1-01 fail-closed ayağı — hedef o satıra KAYAMAZ.

    Kusurun kökü buydu: çözücü sayı vermeyince kullanıcının kendi hedefi
    "sonuç" diye basılıyordu. İstasyon marşı düşürülünce hane "—" kalmalı,
    nedeni yazılmalı ve kullanıcının hedefi KENDİ satırında kalmalıdır.
    """
    kirpik = json.loads(json.dumps(sivi_sonuc))
    tp = kirpik.get('thermal_protection') or {}
    tp.pop('station_march', None)
    tp['station_march_status'] = 'not_run (bekçi kırpması)'
    cs = kirpik.get('cooling_system') or {}
    if isinstance(cs, dict):
        cs.pop('wall_temperature_source', None)
        cs.pop('wall_temperature_hot', None)

    kart = _kart_kos(tmp_path, liquid_kaynak, kirpik, 'c3')
    assert kart, 'Termal Koruma kartı hiç basılmıyor'
    cidar = _satir(kart, 'Wall Temperature')
    assert cidar == '—', (
        'çözülmüş sıcaklık yokken "Wall Temperature" satırına sayı '
        'basılıyor: %r' % cidar)
    assert 'not_run (bekçi kırpması)' in _metin(kart), (
        'sayının neden yok olduğu (station_march_status) yazılmıyor')
    hedef = tp.get('wall_temperature')
    assert _satir(kart, 'Maximum Wall Temperature') == '%d K' % round(hedef), (
        'kullanıcının hedefi kendi satırından düştü')


# ===========================================================================
# D — "REAL-TIME DATA" ROZETİ + EZME KAPISI  (P12bB1-02)
# ===========================================================================
#: ``liquid.html``ten sökülen künye/ezme kapısını koşturan düzenek. ``fetch``
#: uca gitmez; GERÇEK uç yanıtları önceden ölçülüp buraya verilir.
PROV_HARNESS = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const [srcPath, payloadPath] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

function Field(id, v) { this.id = id; this.value = String(v); this.style = {};
    this.innerHTML = ''; }
const FIELDS = {};
['fuel_density', 'fuel_viscosity', 'oxidizer_density', 'oxidizer_viscosity']
    .forEach(function (id) { FIELDS[id] = new Field(id, payload.fieldStart); });
const SPANS = {};
const dict = payload.i18n || {};
const RESP = payload.responses || {};

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, RegExp: RegExp, isFinite: isFinite,
    parseFloat: parseFloat, parseInt: parseInt, Promise: Promise,
""" + I18N_STUB_JS + r"""
    document: { getElementById: function (id) {
        if (FIELDS[id]) return FIELDS[id];
        if (/^(fuel|ox)-properties-/.test(id)) {
            if (!SPANS[id]) SPANS[id] = new Field(id, '');
            return SPANS[id];
        }
        return null;
    } },
    fetch: function (url, init) {
        const body = JSON.parse(init.body);
        const key = body.propellant_type + '|' + body.propellant_name;
        if (!RESP[key]) return Promise.reject(new Error('stub: ' + key + ' yok'));
        return Promise.resolve({ ok: true,
            json: function () { return Promise.resolve(RESP[key]); } });
    },
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(srcPath, 'utf8'), sandbox,
                { filename: 'liquid-sokum.js' });

(async function () {
    const out = { provenance: {}, fields: {}, spans: {} };
    (payload.provenanceCases || []).forEach(function (c) {
        out.provenance[c.name] = sandbox.propellantProvenance(c.payload);
    });
    if (payload.load) {
        await sandbox.loadPropellantProperties(payload.load.fuel, payload.load.ox);
        Object.keys(FIELDS).forEach(function (id) {
            out.fields[id] = { value: FIELDS[id].value,
                               background: FIELDS[id].style.backgroundColor };
        });
        Object.keys(SPANS).forEach(function (id) { out.spans[id] = SPANS[id].innerHTML; });
    }
    process.stdout.write(JSON.stringify(out));
})().catch(function (e) {
    console.error(String((e && e.stack) || e)); process.exit(3);
});
"""

#: Sayfanın gerçekten sorduğu dört itici (yakıt + oksitleyici kolları).
ITICILER = (('liquid_fuel', 'rp1'), ('oxidizer', 'lox'),
            ('oxidizer', 'n2o4'), ('liquid_fuel', 'mmh'))

#: Alanın başlangıç değeri — hiçbir iticinin yoğunluğuna eşit olmayan,
#: "kullanıcının kendi girdisi" yerine geçen im.
ALAN_BASLANGICI = '999'


@pytest.fixture(scope='module')
def itici_yanitlari(client):
    """``/api/get-propellant-properties`` GERÇEK yanıtları."""
    out = {}
    for kind, ad in ITICILER:
        r = client.post('/api/get-propellant-properties',
                        json={'propellant_type': kind, 'propellant_name': ad},
                        headers=HEADERS)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert j.get('status') == 'success', j
        out[kind + '|' + ad] = j
    return out


@pytest.fixture(scope='module')
def prov_kaynak():
    """Künye + ezme kapısının ``liquid.html``ten sökülmüş hâli."""
    html = LIQUID_HTML.read_text(encoding='utf-8')
    # ÖH D31 · arayuz-panel a3 (14 Eyl 2026): sökülen birim BÜYÜDÜ.
    # `loadPropellantProperties` artık alanı doğrudan değil, iki
    # sarmalayıcıyla yazıyor (OH-Z1-05: makine dolumu bayraklanır ki
    # hâl çözümü gelmediğinde BAYAT sayı temizlensin, kullanıcının elle
    # yazdığına dokunulmasın). Sarmalayıcılar harness'a alınmazsa çağrı
    # `is not defined` ile patlar, değer HİÇ yazılmaz ve bekçi bunu
    # "kapı değeri yazmıyor" diye okur — yani SAHTE bir kırmızı verir.
    return '\n'.join([
        'const LIQUID_SIGFIG_DENSITY = 6, LIQUID_SIGFIG_TRANSPORT = 4;',
        _sablon_fonksiyonu(html, 'numTxt'),
        _sablon_fonksiyonu(html, 'liquidSigFig'),
        # ÖH D36 · onemli2-sivi a2: a1 (TR ondalık) `propellantProvenance`
        # içinde hâl künyesi sıcaklığını `liqStateTempText` ile
        # yerelleştiriyor; yardımcı sökülen birime alınmazsa çağrı
        # `is not defined` ile patlar (d1). Aynı turda viskozite üstel
        # gösterimi `liqExpTxt`e bağlandı (`loadPropellantProperties` kart
        # metni); o da alınmazsa kart kurulurken patlar ve renk HİÇ
        # yazılmaz (d3 — yukarıdaki notun tarif ettiği SAHTE kırmızı).
        _sablon_fonksiyonu(html, 'liqStateTempText'),
        _sablon_fonksiyonu(html, 'liqExpTxt'),
        _sablon_fonksiyonu(html, 'propellantProvenance'),
        _sablon_fonksiyonu(html, 'markFieldProvenance'),
        _sablon_fonksiyonu(html, 'liquidAutofillBayragi'),
        _sablon_fonksiyonu(html, 'liquidAutofillMi'),
        _sablon_fonksiyonu(html, 'liquidAutofillField'),
        _sablon_fonksiyonu(html, 'liquidClearUnresolvedField'),
        _sablon_fonksiyonu(html, 'loadPropellantProperties'),
    ])


def _prov_kos(tmp_path, kaynak, ad, **payload):
    src = tmp_path / (ad + '_src.js')
    src.write_text(kaynak, encoding='utf-8')
    girdi = tmp_path / (ad + '_girdi.json')
    payload.setdefault('fieldStart', ALAN_BASLANGICI)
    girdi.write_text(json.dumps(payload), encoding='utf-8')
    return _node_kos(PROV_HARNESS, tmp_path, ad + '_kos', src, girdi)


@node_gerekli
def test_d1_yerel_tablo_degerine_gercek_zamanli_rozeti_basilmiyor(
        itici_yanitlari, prov_kaynak, tmp_path):
    """P12bB1-02 · P15B3-07 — sahte "Real-time Data" rozeti öldü.

    Ölçülen kusur: yerel tablo değerinin üstünde koşulsuz yeşil "Real-time
    Data" rozeti ve "NASA RP-1 Specification" kaynak metni basılıyordu; o
    yolda canlı istek YOK. Bekçi sayfanın SORDUĞU dört iticinin hiçbirinde
    bu rozetin çıkmadığını, hâl çözülmemiş değerin uyarı rengine
    boyandığını kilitler.
    """
    vakalar = [{'name': k, 'payload': v} for k, v in itici_yanitlari.items()]
    out = _prov_kos(tmp_path, prov_kaynak, 'd1', provenanceCases=vakalar)
    for ad, prov in out['provenance'].items():
        kaynak = str(itici_yanitlari[ad].get('source') or '')
        canli_mi = bool(re.search(r'pubchem|webbook|nist\.gov', kaynak, re.I))
        assert prov['live'] is canli_mi, (
            '%s: canlılık künyesi kaynakla uyuşmuyor (source=%r)' % (ad, kaynak))
        assert canli_mi is False, (
            'fikstür dayanağı düştü: %s artık gerçekten canlı bir kaynaktan '
            'geliyor (%r) — bu bekçi yeniden ölçülmeli' % (ad, kaynak))
        assert prov['badgeText'] != 'Real-time Data', (
            'SAHTE ROZET GERİ DÖNDÜ: %s yerel/hâl-çözümlü değere "Real-time '
            'Data" basıyor (source=%r)' % (ad, kaynak))
        if prov['stateResolved']:
            # Hâl çözülmüşse rozet hangi hâl olduğunu SÖYLER (yeşil meşru).
            durum = ((itici_yanitlari[ad].get('properties') or {})
                     .get('storage_state') or {})
            assert prov['badgeText'] == (durum.get('description') or kaynak), (
                '%s: hâl çözümü rozeti hâli adıyla anmıyor' % ad)
            assert prov['badgeColor'] == '#28a745'
        else:
            # v3.0.1: eski metin 'Using cached data' kullanılmayan bir önbelleği
            # iddia ediyordu; değer çözülmemiş ve alan değiştirilmiyor.
            assert prov['badgeText'] == 'No state-resolved value: field not changed', (
                '%s: hâl çözülmemişken rozet dürüst değil (%r)'
                % (ad, prov['badgeText']))
            assert prov['badgeColor'] == '#ffc107', (
                '%s: çözülmemiş değer uyarı rengine boyanmıyor' % ad)


@node_gerekli
def test_d2_rozet_yalniz_gercek_canli_kaynakta(prov_kaynak, tmp_path):
    """P12bB1-02 — bekçi rozeti tamamen yasaklamıyor, KAZANILMASINI istiyor.

    Bu, "rozeti silelim geçelim" onarımını da yakalar: künye gerçekten dış
    bir canlı servise işaret ettiğinde rozet BASILMALIDIR. Vaka sentetiktir
    ve bilinçlidir — depoda o yolu koşan bir itici bulunmadığı ölçüldü
    (``test_d1``), dolayısıyla sözleşmenin bu yarısı ancak böyle sınanabilir.
    """
    vakalar = [
        {'name': 'pubchem', 'payload': {
            'source': 'PubChem PUG-REST live query',
            'properties': {'density': 810.0}}},
        {'name': 'webbook', 'payload': {
            'source': 'NIST WebBook (live)', 'properties': {'density': 1141.0}}},
        {'name': 'nistgov', 'payload': {
            'source': 'https://webbook.nist.gov/cgi/cbook.cgi',
            'properties': {'density': 1141.0}}},
        {'name': 'yerel', 'payload': {
            'source': 'CoolProp (NIST REFPROP-based)',
            'properties': {'density': 1141.0}}},
        # v3.0.1: web_propellant_api._damgala canlı OLMAYAN dönüşü damgalar;
        # adında 'WebBook' geçse de paket/önbellek kaydı canlı DEĞİLDİR.
        {'name': 'kayitli_kopya', 'payload': {
            'source': ('NIST WebBook via nist-api.fly.dev third-party '
                       'crawler (Stored copy)'),
            'properties': {'density': 1141.0}}},
        {'name': 'bayat', 'payload': {
            'source': ('NIST WebBook via nist-api.fly.dev third-party '
                       'crawler (Stale cache)'),
            'properties': {'density': 1141.0}}},
    ]
    out = _prov_kos(tmp_path, prov_kaynak, 'd2', provenanceCases=vakalar)
    for ad in ('kayitli_kopya', 'bayat'):
        assert out['provenance'][ad]['live'] is False, (
            '%s: damgalı (canlı olmayan) kayıt canlı sayılıyor' % ad)
        assert out['provenance'][ad]['badgeText'] != 'Real-time Data', (
            '%s: paket/önbellek kaydına "Real-time Data" basılıyor' % ad)
    for ad in ('pubchem', 'webbook', 'nistgov'):
        assert out['provenance'][ad]['live'] is True, (
            '%s: gerçek canlı kaynak canlı sayılmıyor' % ad)
        assert out['provenance'][ad]['badgeText'] == 'Real-time Data', (
            '%s: kazanılmış rozet basılmıyor' % ad)
    # Yerel kütüphane canlı sorgu DEĞİLDİR (CoolProp adında NIST geçse bile).
    assert out['provenance']['yerel']['live'] is False, (
        'yerel kütüphane adındaki "NIST" canlı sayılıyor')
    assert out['provenance']['yerel']['badgeText'] != 'Real-time Data'


@node_gerekli
def test_d3_kategori_yedegi_form_alanini_ezmiyor(itici_yanitlari, prov_kaynak,
                                                 tmp_path):
    """P12bB1-02 · P9B5-06 — yanlış sayı form alanına, oradan motora GİTMEZ.

    Kusurun ürün ayağı buydu: kategori yedeği (rp1 → 800) form alanına
    yazılıp ``/calculate_liquid``e gidiyordu. Bekçi iki yönü de kilitler:
    çözülmemiş değer alanı EZMEZ (uyarı rengine boyanır), hâl çözümlü değer
    alanı GÜNCELLER (kapı fazla sıkılıp faydayı da öldürmesin).
    """
    yakit = itici_yanitlari['liquid_fuel|rp1']
    oks = itici_yanitlari['oxidizer|lox']
    assert (yakit.get('properties') or {}).get('storage_state') is None, (
        'fikstür dayanağı düştü: rp1 artık hâl çözümlü geliyor')
    assert (oks.get('properties') or {}).get('storage_state'), (
        'fikstür dayanağı düştü: lox artık hâl çözümü yayımlamıyor')

    out = _prov_kos(tmp_path, prov_kaynak, 'd3',
                    responses=itici_yanitlari,
                    load={'fuel': 'rp1', 'ox': 'lox'})
    alanlar = out['fields']
    assert alanlar['fuel_density']['value'] == ALAN_BASLANGICI, (
        'EZME KAPISI DÜŞTÜ: kategori yedeği yakıt yoğunluğu alanını ezdi '
        '(%r)' % alanlar['fuel_density']['value'])
    assert alanlar['fuel_viscosity']['value'] == ALAN_BASLANGICI, (
        'kategori yedeği viskozite alanını ezdi')
    assert alanlar['fuel_density']['background'] == '#fff3cd', (
        'çözülmemiş alan görünür kılınmıyor')

    beklenen = float((oks.get('properties') or {})['density'])
    okunan = float(alanlar['oxidizer_density']['value'])
    assert abs(okunan - beklenen) <= abs(beklenen) * 1e-5, (
        'hâl çözümlü değer alana yazılmıyor: %r ⟷ uç %r' % (okunan, beklenen))
    assert not alanlar['oxidizer_density']['background'], (
        'hâl çözümlü alan gereksiz yere uyarı rengine boyanıyor')

    span = out['spans'].get('fuel-properties-rp1') or ''
    assert 'Real-time Data' not in span, (
        'yakıt künye şeridinde sahte rozet basılıyor: %s' % _metin(span)[:300])
    assert 'No state-resolved value: field not changed' in span, (
        'çözülmemiş değerin künyesi dürüst değil: %s' % _metin(span)[:300])


# ===========================================================================
# E — "TOTOLOJİK" KÜNYESİNİN TANIMI  (P14H1-C4)
# ===========================================================================
#: Künyenin sözünü verdiği keskin ölçüt alanları (kardeş adlar).
KESKIN_ALANLAR = {
    'safety_factor_is_tautological': 'safety_factor_reads_back_target',
    'binding_safety_factor_is_tautological':
        'binding_safety_factor_reads_back_target',
}


def test_e1_iki_alan_ayri_yayimlaniyor_ve_kunye_keskin_olcutu_adlandiriyor(
        hibrit_sonuc):
    """P14H1-C4 — künye kendi anlamını ve keskin ölçütünü ADIYLA yazar.

    Ölçülen belirsizlik: bayrak "sayı hedefin kendisidir" diye okunuyordu;
    oysa "cidarı HRMA seçti" diyor. İki cümle aynı şey değil ve tüketiciler
    (ihraç, panel) birincisini varsayıyordu. Bekçi künyenin YANINDA
    durduğunu ve okuyucuyu keskin ölçüte yönlendirdiğini kilitler.
    """
    sa = (hibrit_sonuc.get('motor') or {}).get('structural_analysis') or {}
    ca = sa.get('chamber_analysis') or {}
    sfa = sa.get('safety_analysis') or {}
    gorulen = []
    for kaynak_adi, blok in (('chamber_analysis', ca), ('safety_analysis', sfa)):
        for bayrak, keskin in KESKIN_ALANLAR.items():
            if bayrak not in blok:
                continue
            if isinstance(blok[bayrak], dict):
                # İSTASYON HARİTASI (``safety_analysis.safety_factor_is_``
                # ``tautological``): tekil bir bayrak değil, kesit başına
                # sözlük. Onun keskin karşılığı da envanterdir; künye cümlesi
                # bağlı olduğu TEKİL alanın yanında durur.
                envanter = blok.get('stations_reading_back_target')
                assert isinstance(envanter, list), (
                    '%s: istasyon totoloji haritası yayımlanıyor ama '
                    'geri-okuma envanteri (stations_reading_back_target) yok'
                    % kaynak_adi)
                continue
            gorulen.append(kaynak_adi + '.' + bayrak)
            kunye = blok.get(bayrak + '_basis')
            assert isinstance(kunye, str) and kunye.strip(), (
                '%s.%s künyesiz yayımlanıyor' % (kaynak_adi, bayrak))
            assert keskin in blok, (
                '%s: %s yayımlanıyor ama keskin ölçüt %s YOK'
                % (kaynak_adi, bayrak, keskin))
            assert isinstance(blok[keskin], bool), (
                '%s.%s bool değil: %r' % (kaynak_adi, keskin, blok[keskin]))
            assert keskin in kunye, (
                '%s künyesi keskin ölçütü (%s) adıyla anmıyor:\n%s'
                % (bayrak, keskin, kunye))
            # Künye, yanlış okumayı ADIYLA reddetmeli.
            assert re.search(r'does\s+not|is\s+not|it\s+does\s+NOT', kunye,
                             re.I), (
                '%s künyesi yanlış okumayı reddetmiyor:\n%s' % (bayrak, kunye))
    assert len(gorulen) >= 2, (
        'iki katmanın da tekil künyesi ölçülemedi (görülen: %r) — bekçi boş '
        'kapsamda yeşil sayılmasın' % gorulen)


def test_e2_bayrak_acik_ama_sayi_hedefi_geri_okumuyor(hibrit_sonuc):
    """P14H1-C4 — tanım ÇÜRÜTÜLEBİLİR ve gerçek koşumda çürümüyor.

    Künye "bayrak True iken sayı hedefin altına düşebilir" diyor. Bu bir
    süsleme değilse gerçek bir koşumda görünmelidir: varsayılan hibritte
    ``design_mode='size'`` (cidarı HRMA seçti) iken yayımlanan katsayı
    hedefin ALTINDA — çünkü boyutlandırma yalnız BASINÇ hoop gerilmesini
    hedefe oturtuyor, termal terim sayıyı aşağı çekiyor. Bu koşumda
    ``..._is_tautological`` ile ``..._reads_back_target`` AYRIŞMALIDIR.
    """
    ca = (((hibrit_sonuc.get('motor') or {}).get('structural_analysis') or {})
          .get('chamber_analysis') or {})
    assert ca.get('design_mode') == 'size', (
        'fikstür dayanağı düştü: varsayılan hibrit artık cidarı kendi '
        'boyutlandırmıyor (%r)' % ca.get('design_mode'))
    assert ca.get('safety_factor_is_tautological') is True, (
        'boyutlandırılan kesitte bayrak açık değil: %r'
        % ca.get('safety_factor_is_tautological'))
    hedef = float(ca['design_safety_factor_target'])
    sayi = float(ca['hoop_safety_factor'])
    assert sayi < hedef, (
        'fikstür dayanağı düştü: boyutlandırılan kesitin katsayısı artık '
        'hedefin altına düşmüyor (%s ⟷ %s) — künyenin çürütülebilirliği '
        'başka bir koşumla ölçülmeli' % (sayi, hedef))
    assert ca.get('safety_factor_reads_back_target') is False, (
        'KÜNYE İLE GERÇEK AYRIŞTI: sayı (%s) hedefin (%s) ALTINDA ama '
        'reads_back_target True' % (sayi, hedef))
    assert (ca['safety_factor_is_tautological']
            is not ca['safety_factor_reads_back_target']), (
        'iki alan bu koşumda ayrışmalıydı; künyenin tanımı ölçülemez hâle '
        'geldi')


def test_e3_keskin_olcut_bayragin_takma_adi_degil(client, hibrit_sonuc):
    """P14H1-C4 — ``reads_back_target`` HESAPLANIR, kopyalanmaz.

    Bu bekçinin ödediği borç şu: birisi keskin ölçütü "bayrağın kopyası"
    yapıp künyeyi süse çevirebilir. Ölçüt kendi tanımından türemeli:
    boyutlandırılmış (``size``) VE sayı hedefin üstünde. Bekçi bunu iki
    ayrı koşumda doğrular — kullanıcının cidarı verildiğinde ölçüt de,
    bayrak da düşer; verilmediğinde bayrak kalkar, ölçüt sayının yerine
    göre karar verir.
    """
    def _olc(ca):
        mode = ca.get('design_mode')
        hedef = ca.get('design_safety_factor_target')
        sayi = ca.get('hoop_safety_factor')
        beklenen = bool(mode == 'size' and isinstance(sayi, (int, float))
                        and isinstance(hedef, (int, float))
                        and sayi >= hedef * (1.0 - 1e-9))
        assert ca.get('safety_factor_reads_back_target') is beklenen, (
            'keskin ölçüt kendi tanımından türemiyor: mode=%r sayı=%r '
            'hedef=%r → alan %r' % (mode, sayi, hedef,
                                    ca.get('safety_factor_reads_back_target')))
        assert ca.get('safety_factor_is_tautological') is (mode == 'size'), (
            'bayrak "cidarı kim verdi" sorusundan türemiyor: mode=%r → %r'
            % (mode, ca.get('safety_factor_is_tautological')))
        return beklenen

    ca_size = (((hibrit_sonuc.get('motor') or {}).get('structural_analysis')
                or {}).get('chamber_analysis') or {})
    _olc(ca_size)

    r = client.post('/calculate', json=dict(HIBRIT_YUKU, wall_thickness=15.0),
                    headers=HEADERS)
    assert r.status_code == 200
    ca_verify = (((r.get_json().get('motor') or {}).get('structural_analysis')
                  or {}).get('chamber_analysis') or {})
    assert ca_verify.get('design_mode') == 'verify'
    _olc(ca_verify)
    assert ca_verify.get('safety_factor_is_tautological') is False, (
        'kullanıcının cidarı sınandığı hâlde bayrak açık kalıyor')
    assert ca_verify.get('safety_factor_reads_back_target') is False, (
        'doğrulama koşumunda "hedefin geri okuması" iddiası basılıyor')


# ---------------------------------------------------------------------------
# Harness bayatlama bekçisi (ÖH D30 / fix-29b)
# ---------------------------------------------------------------------------
def test_her_sandbox_i18n_yardimcilarinin_IKISINI_birden_sagliyor():
    """``T`` tanımlayan her sandbox ``TF``i de tanımlamalı.

    Tarayıcıda ikisi de ``i18n.js``in küreselidir; şablonun sökülen bloğu
    hangisini çağıracağını harness bilemez. ÖLÇÜLEN KUSUR (ÖH D29 arayuz
    -panel a3 sonrası): kart bloğuna ``TF(...)`` girdi, yalnız ``T``
    tanımlayan iki düzenek "ReferenceError: TF is not defined" ile çöktü ve
    iki bekçi düğümü ürünü HİÇ ölçemeden kırmızı verdi. Bu test o sınıfı
    kapatır: stub KAYNAKTAN sayılır, elle tutulan bir liste yoktur.
    """
    metin = pathlib.Path(__file__).read_text(encoding='utf-8')
    # Harness dizelerine enjekte edilen tek tanım noktası.
    assert 'I18N_STUB_JS' in metin
    assert 'TF: function' in I18N_STUB_JS, (
        'I18N_STUB_JS artık TF tanımlamıyor — tek tanım noktası bozulmuş.')
    assert 'T: function' in I18N_STUB_JS

    # Hiçbir harness kendi T/TF kopyasını yazmamalı (tek kaynak). Aranan
    # imzalar TEK KAYNAKTAN TÜRETİLİR; bu dosyaya ikinci bir literal
    # yazılmaz (yoksa bekçi kendi arama dizesini yakalar).
    govde = metin.replace(I18N_STUB_JS, '')
    for satir in I18N_STUB_JS.splitlines():
        imza = satir.strip()
        if not imza.endswith('{'):
            continue
        assert imza not in govde, (
            'i18n yardımcısının ikinci bir tanımı doğmuş (%r) — harness '
            'dizeleri I18N_STUB_JS birleştirmeli.' % imza)

    # Ve ``T``yi enjekte eden her harness dizesi TF'i de almış olmalı:
    # enjeksiyon aynı dizeden geldiği için sayıları eşit olmak zorunda.
    assert govde.count('I18N_STUB_JS') >= 2, (
        'harness dizeleri artık I18N_STUB_JS kullanmıyor.')
