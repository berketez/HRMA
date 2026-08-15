"""gimbal_mount bağlaması — C3 yetim kapanışının bekçileri (v2.6.27).

Ölçülen kusur (15 Ağustos 2026, HEAD 9e1410b): ``hrma/analysis/gimbal_mount``
modülü (742 satır, testli, hazır) hiçbir üründen çağrılmıyordu — liquid.html
sayfasında gimbal SEÇENEĞİ (#engine_mount, #gimbal_range) vardı ama arkasında
hesap yoktu; modülü yalnız tests/test_c_kulvari_bilesenler.py çağırıyordu.
Bu, 2.7 kapı ölçütü #2'yi ("çekirdek-yetim modül sıfır") tek başına
engelleyen borçtu.

Bağlama üç halka:
  1. app.py -> POST /api/gimbal-mount (termal-koruma ucunun deseni:
     beyaz liste + zorunlu alan kapısı + 422/400 sözleşmesi),
  2. liquid.html -> sonuç bölümünde gimbal paneli; boş form alanı payload'a
     KONMAZ, eksik zorunlu girdi BEYAN edilir (sayı uydurulmaz), sabit
     montajda NOT_APPLICABLE beyanı,
  3. i18n_pages.js -> panel metinleri EN+TR.

SÖZLEŞME GÜNCELLEMESİ (15 Ağustos 2026) — boş aktüatör kolunda istek atılmaz
Ölçülen kusur: aktüatör kolu alanı BOŞ DOĞAR ("blank: not analysed"), bu yüzden
her hesap sonunda panel uca kesin 422 dönecek bir istek atıyordu
({"thrust_N":10000,"gimbal_angle_deg":8,"yaw_angle_deg":8}). İşlev doğruydu
(beyan basılıyordu) ama tarayıcı konsoluna her hesapta kırmızı "Failed to load
resource: 422" düşüyordu; görsel tur iskelesinin konsol-hata denetimi ve
dev-tools açan kullanıcı bunu ürün hatası sanıyordu. Yeni sözleşme:
  * kol BOŞ (arm === null) -> fetch HİÇ atılmaz, aynı beyan (aynı i18n
    anahtarı, ucun ``missing_fields`` sırasıyla aynı alan adları) YEREL basılır,
  * kol DOLU ama başka zorunlu alan eksik -> 422 yolu emniyet ağı olarak
    AYNEN korunur; sunucu sözleşmesi tek doğru kaynak olarak kalır.
Bu dosyadaki eski bekçilerin hiçbiri "boş kolda da istek atılır" davranışını
kilitlemiyordu (yalnız boş alanın payload'a konmadığını kilitliyorlardı), bu
yüzden gevşetme değil EKLEME yapıldı: §8 yeni bekçileri.

Desen ölçümü (aynı oturum): /api/thermal-protection beyaz liste dışı
fazladan anahtarı 200 ile SESSİZCE düşürüyor (modüle ulaşmaz, TypeError
500 üretmez); eksik zorunlu alanda 422 + ``missing_fields`` dönüyor.
/api/gimbal-mount aynı davranışı sergiler ve bu dosya ikisini de kilitler.

MUTASYON DÜŞÜNCESİ — bağlama geri alınırsa hangi test kırılır:
  * app.py'deki ``from hrma.analysis.gimbal_mount import`` satırı silinirse
    -> test_yetim_kapanisi_app_importu_yapisal (kaynak düzeyi) VE
       uç 500/404 döneceği için test_gecerli_istek_modul_alanlarini_tasir.
  * ``/api/gimbal-mount`` route'u silinirse -> 404 üzerinden bu dosyadaki
    TÜM uç testleri (geçerli/422/400/beyaz liste) birden kırılır.
  * liquid.html'deki fetch çağrısı silinirse (sayfa ucu bırakır) ->
    test_yetim_kapanisi_sayfa_ucu_cagiriyor.
  * Boş-alan-gönderme koruması gevşer de sayfa boş alana sayı dayatırsa ->
    test_bos_alan_payloada_konmaz_yapisal (gimbalFieldValue null yolu).
  * Boş koldaki yerel kapı kalkar da fetch koşulsuz atılırsa (konsol
    gürültüsü geri gelir) -> test_bos_kolda_istek_atilmaz (davranış, node) VE
    test_bos_kol_kapisi_fetchten_once (kaynak sırası).
"""

import inspect
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIQUID = ROOT / 'hrma' / 'templates' / 'liquid.html'
APP_PY = ROOT / 'hrma' / 'app.py'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


#: Geçerli taban istek — modülün kendi bekçi süitiyle (test_c_kulvari_
#: bilesenler.py) aynı büyüklük sınıfı: 1 MN itki, 6 derece sapma.
GECERLI = {
    'thrust_N': 1.0e6,
    'gimbal_angle_deg': 6.0,
    'actuator_arm_m': 0.5,
    'ring_offset_m': 0.4,
    'thrust_offset_m': 0.01,
    'bolt_circle_diameter_m': 0.6,
    'bolt_count': 12,
}


def _gonder(client, govde):
    return client.post('/api/gimbal-mount', json=govde)


# ---------------------------------------------------------------------------
# 1) Geçerli istek -> 200 + modül alanları yanıtta
# ---------------------------------------------------------------------------
def test_gecerli_istek_modul_alanlarini_tasir(client):
    """Uçtan uca kanıt: istek -> app.py -> analyze_gimbal_mount -> yanıt.

    Yanıt sayıları modülün kendisiyle karşılaştırılır (yankı değil hesap):
    uç, modülü GERÇEKTEN çağırmıyorsa bu eşitlikler tutmaz.
    """
    r = _gonder(client, GECERLI)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    govde = r.get_json()

    # analyze_gimbal_mount sözlüğünün üst düzey alanları aynen taşınmalı.
    for alan in ('thrust', 'actuator', 'moment_budget', 'mount_ring',
                 'bolts', 'validity', 'warnings', 'not_modelled'):
        assert alan in govde, 'yanıtta %r yok — modül sonucu taşınmıyor' % alan

    # Sayılar modülle birebir (uç modülü çağırmıyorsa burada kopar).
    from hrma.analysis.gimbal_mount import analyze_gimbal_mount
    beklenen = analyze_gimbal_mount(**GECERLI)
    assert govde['thrust']['axial_N'] == pytest.approx(
        beklenen['thrust']['axial_N'])
    assert govde['thrust']['side_N'] == pytest.approx(
        beklenen['thrust']['side_N'])
    assert govde['actuator']['stroke_chord_m'] == pytest.approx(
        beklenen['actuator']['stroke_chord_m'])
    assert govde['bolts']['moment_induced_max_N'] == pytest.approx(
        beklenen['bolts']['moment_induced_max_N'])


def test_iki_eksen_yaw_ile_bileske_beyani(client):
    """yaw_angle_deg verilince two_axis bloğu ve tek-eksen beyanı döner."""
    r = _gonder(client, dict(GECERLI, yaw_angle_deg=6.0))
    assert r.status_code == 200
    govde = r.get_json()
    assert govde['two_axis'] is not None
    assert govde['two_axis']['resultant_angle_deg'] > 6.0
    # Modül köşe durumunun TEK eksenle hesaplandığını açıkça beyan eder.
    assert any(v.get('field') == 'two_axis' for v in govde['validity'])


# ---------------------------------------------------------------------------
# 2) Açı 45 derece üstü -> 400 + geçerlilik metni korunmuş
# ---------------------------------------------------------------------------
def test_aci_45_ustu_400_gecerlilik_metniyle(client):
    """Modülün ValueError'ı 400 olur; beyanın İÇERİĞİ yumuşatılmadan taşınır."""
    r = _gonder(client, dict(GECERLI, gimbal_angle_deg=50.0))
    assert r.status_code == 400
    mesaj = r.get_json().get('error', '')
    # Geçerlilik beyanının çekirdek cümleleri (gimbal_mount.py kaynağından).
    assert 'outside the supported validity range' in mesaj
    assert '45' in mesaj
    assert 'no silent extrapolation' in mesaj


def test_civata_sayisi_3_alti_400(client):
    """İkinci ValueError yolu: n<3 cıvata reddedilir, 500 değil 400."""
    r = _gonder(client, dict(GECERLI, bolt_count=2))
    assert r.status_code == 400
    assert 'below the minimum' in r.get_json().get('error', '')


# ---------------------------------------------------------------------------
# 3) Eksik zorunlu alan -> 422 + missing_fields
# ---------------------------------------------------------------------------
def test_eksik_zorunlu_alan_422_missing_fields(client):
    r = _gonder(client, {'thrust_N': 1.0e6})
    assert r.status_code == 422
    govde = r.get_json()
    assert govde['status'] == 'error'
    assert govde['error'] == 'incomplete_gimbal_mount_input'
    assert govde['missing_fields'] == ['gimbal_angle_deg', 'actuator_arm_m']


def test_bos_govde_422_tum_zorunlular(client):
    r = _gonder(client, {})
    assert r.status_code == 422
    assert r.get_json()['missing_fields'] == [
        'thrust_N', 'gimbal_angle_deg', 'actuator_arm_m']


def test_bos_dize_alan_eksik_sayilir(client):
    """'' gönderilen zorunlu alan yok sayılır -> 422 (TP ucunun deseni).

    Zincir: panel boş alanı payload'a hiç koymaz; buradaki ``not in
    (None, '')`` kapısı ikinci savunma hattıdır — '' sızarsa ham float()
    hatası 500'e düşerdi.
    """
    r = _gonder(client, dict(GECERLI, actuator_arm_m=''))
    assert r.status_code == 422
    assert r.get_json()['missing_fields'] == ['actuator_arm_m']


# ---------------------------------------------------------------------------
# 4) Beyaz liste: fazladan anahtar sessizce düşer (TP ucuyla AYNI davranış)
# ---------------------------------------------------------------------------
def test_beyaz_liste_disi_anahtar_sessizce_duser(client):
    """Fazladan anahtar modüle ULAŞMAZ: 200 döner, TypeError 500 olmaz.

    Desen termal-koruma ucundan ölçüldü: /api/thermal-protection fazladan
    anahtarı 200 ile yok sayıyor. Aynı davranış burada kilitlenir; iki uç
    ayrışırsa (biri 400, biri 200) bu test onu görünür kılar.
    """
    r = _gonder(client, dict(GECERLI, BOGUS_KEY=42, another_unknown='x'))
    assert r.status_code == 200, (
        'beyaz liste dışı anahtar 200 dışı kod üretti: %s %s'
        % (r.status_code, r.get_data(as_text=True)[:200]))
    metin = r.get_data(as_text=True)
    assert 'BOGUS_KEY' not in metin and 'another_unknown' not in metin

    # Referans desen: TP ucu da fazladan anahtarı sessizce düşürür.
    r_tp = client.post('/api/thermal-protection', json={
        'mode': 'radiation_equilibrium', 'h_gas_W_m2K': 1000.0,
        'T_recovery_K': 3000.0, 'emissivity': 0.8, 'BOGUS_KEY': 42})
    assert r_tp.status_code == 200
    assert 'BOGUS_KEY' not in r_tp.get_data(as_text=True)


def test_beyaz_liste_modul_imzasiyla_birebir():
    """Parametre tutarlılığı: _GIMBAL_KEYS == analyze_gimbal_mount imzası.

    Beyaz liste modül imzasının kopyasıdır; imza değişir de liste kalırsa
    yeni parametre SESSİZCE ulaşılmaz olur. Bu test iki kümeyi kilitler.
    """
    from hrma.app import _GIMBAL_KEYS, _GIMBAL_REQUIRED
    from hrma.analysis.gimbal_mount import analyze_gimbal_mount
    imza = inspect.signature(analyze_gimbal_mount).parameters
    assert set(_GIMBAL_KEYS) == set(imza), (
        'beyaz liste ile modül imzası ayrıştı: yalnız listede %s / '
        'yalnız imzada %s'
        % (sorted(set(_GIMBAL_KEYS) - set(imza)),
           sorted(set(imza) - set(_GIMBAL_KEYS))))
    zorunlu = [n for n, p in imza.items()
               if p.default is inspect.Parameter.empty]
    assert list(_GIMBAL_REQUIRED) == zorunlu


# ---------------------------------------------------------------------------
# 5) Yetim kapanışı — yapısal kanıtlar
# ---------------------------------------------------------------------------
def test_yetim_kapanisi_app_importu_yapisal():
    """app.py, gimbal_mount modülünü GERÇEKTEN import ediyor.

    C3 borcunun tanımı buydu: modül üründen çağrılmıyordu. Bu satır
    silinirse (bağlama geri alınırsa) bu test kırılır.
    """
    kaynak = APP_PY.read_text(encoding='utf-8')
    assert re.search(
        r'^\s*from hrma\.analysis\.gimbal_mount import analyze_gimbal_mount',
        kaynak, re.M), 'app.py gimbal_mount modülünü import etmiyor'


def test_yetim_kapanisi_rota_kayitli(client):
    """/api/gimbal-mount rotası uygulamada kayıtlı (kaynak değil, çalışan)."""
    from hrma.app import app
    kurallar = {r.rule for r in app.url_map.iter_rules()}
    assert '/api/gimbal-mount' in kurallar


def test_yetim_kapanisi_sayfa_ucu_cagiriyor():
    """liquid.html paneli ucu gerçekten çağırıyor; seçenek artık hesapsız değil."""
    html = LIQUID.read_text(encoding='utf-8')
    assert "fetch('/api/gimbal-mount'" in html, (
        'liquid.html /api/gimbal-mount ucunu çağırmıyor — sayfa bağlaması '
        'kopmuş')
    assert 'id="gimbalPanel"' in html


# ---------------------------------------------------------------------------
# 6) Sayfa dürüstlüğü — boş varsayılan, boş alan gönderilmez, NOT_APPLICABLE
# ---------------------------------------------------------------------------
def test_yeni_form_alanlari_bos_varsayilanli():
    """Dört yeni alan value niteliği TAŞIMAZ (sayfa sayı dayatmaz).

    2,3x kusurunun dersi: görünmez varsayılan, kullanıcının hiç girmediği
    sayıyı hesaba sokar. Alanlar boş doğar; placeholder yalnız örnektir.
    """
    html = LIQUID.read_text(encoding='utf-8')
    for alan in ('gimbal_actuator_arm', 'gimbal_ring_offset',
                 'gimbal_bolt_circle', 'gimbal_bolt_count'):
        etiket = re.search(r'<input[^>]*id="%s"[^>]*>' % alan, html)
        assert etiket, 'liquid.html içinde #%s alanı yok' % alan
        assert 'value=' not in etiket.group(0), (
            '#%s alanına varsayılan değer konmuş — boş doğmalı' % alan)
        assert 'placeholder=' in etiket.group(0)


def test_bos_alan_payloada_konmaz_yapisal():
    """gimbalFieldValue boş dizeyi null yapar; null alan payload'a girmez."""
    html = LIQUID.read_text(encoding='utf-8')
    assert re.search(r"if \(raw === ''\) return null;", html), (
        'boş alan koruması (gimbalFieldValue) kaldırılmış')
    # null alanın payload dışı bırakıldığı koşullu ekleme deseni:
    assert re.search(
        r"if \(arm !== null\) \{ payload\.actuator_arm_m = arm; \}", html)


def test_sabit_montaj_not_applicable_beyani():
    """fixed_mount seçiliyken panel NOT_APPLICABLE beyanı basar (hesap yok)."""
    html = LIQUID.read_text(encoding='utf-8')
    assert "T('liq.js.gimbal_computing'" in html or \
        "TF('liq.js.gimbal_not_applicable'" in html
    assert "TF('liq.js.gimbal_not_applicable'" in html
    # Beyan yolu gimbal DIŞI her seçenek için çalışır (fixed + flex).
    assert re.search(
        r"if \(mount !== 'gimbal_2axis' && mount !== 'gimbal_1axis'\)", html)


def test_sifir_moment_butcesinde_kuvvet_satiri_basilmaz():
    """Moment bütçesi sıfırken '0 N aktüatör' göstergesi basılmaz.

    Modülün kendi ilkesi: sıfır kuvvet ideal-model artefaktıdır, tasarım
    yükü değildir — satır yerine modülün validity beyanı basılır.
    """
    html = LIQUID.read_text(encoding='utf-8')
    assert re.search(
        r"if \(typeof mb\.total_N_m === 'number' && mb\.total_N_m > 0\)",
        html), 'sıfır bütçe koruması kaldırılmış — sahte gösterge riski'


# ---------------------------------------------------------------------------
# 7) Sayfa hâlâ ayakta (Jinja kırılmadı)
# ---------------------------------------------------------------------------
def test_liquid_sayfasi_200(client):
    r = client.get('/liquid')
    assert r.status_code == 200
    assert 'gimbalPanel' in r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# 8) Boş aktüatör kolunda istek atılmaz — konsol gürültüsü kapanışı
#
# Panel kodu GERÇEK node altında, küçük bir DOM + fetch taklidiyle koşturulur
# (kalıp: tests/test_liquid_unwired_ui.py ve tests/test_blowdown_panel.py).
# Kaynak taraması tek başına yetmez: "fetch atılmıyor" bir DAVRANIŞTIR, dizge
# değil — koşum bunu ölçer, yapısal testler yalnız sırayı/ortak gövdeyi kilitler.
# ---------------------------------------------------------------------------

#: Panelin gimbal işlevleri liquid.html'in satır içi script'inden bütün olarak
#: alınır (gimbalEsc -> displayGimbalMount arası). Sınırlar kayarsa test
#: sessizce zayıflamaz, ayıklama iddiasında patlar.
_BLOK_BAS = '        function gimbalEsc('
_BLOK_SON = '        // Initialize'


def _gimbal_blok():
    html = LIQUID.read_text(encoding='utf-8')
    bas = html.index(_BLOK_BAS)
    son = html.index(_BLOK_SON, bas)
    blok = html[bas:son]
    for ad in ('function gimbalFieldValue(', 'function gimbalMissingHtml(',
               'async function displayGimbalMount('):
        assert ad in blok, 'gimbal bloğu ayıklanamadı: %r yok' % ad
    return blok


HARNESS = r"""
'use strict';
const SPEC = __SPEC__;
const fetchCalls = [];
const usedKeys = [];

function makeNode(id) {
    return { id: id, value: '', innerHTML: '', style: {},
             addEventListener: function () {} };
}
const nodes = {};
Object.keys(SPEC.fields).forEach(function (id) {
    nodes[id] = makeNode(id);
    nodes[id].value = SPEC.fields[id];
});
['gimbalPanel', 'gimbalPanelBody'].forEach(function (id) {
    nodes[id] = makeNode(id);
});
const document = {
    getElementById: function (id) { return (id in nodes) ? nodes[id] : null; }
};
// Çeviri taklidi anahtarı GÖRÜNÜR kılar: beyanın hangi i18n anahtarıyla
// basıldığı ve alan adları çıktıdan doğrudan okunur (dil bağımsız ölçüm).
function T(key, fallback) { usedKeys.push(key); return '[[' + key + ']]'; }
function TF(key, params, fallback) { usedKeys.push(key); return '[[' + key + ']]'; }
function hrmaFmt(v, digits, unit) { return String(v) + ' ' + unit; }
global.fetch = function (url, opts) {
    fetchCalls.push({ url: url, payload: JSON.parse(opts.body) });
    const r = SPEC.response;
    return Promise.resolve({
        status: r.status,
        ok: r.status >= 200 && r.status < 300,
        json: function () { return Promise.resolve(r.body); }
    });
};

__BLOCK__

(async function () {
    await displayGimbalMount(SPEC.results);
    process.stdout.write(JSON.stringify({
        fetchCalls: fetchCalls,
        usedKeys: usedKeys,
        body: nodes.gimbalPanelBody.innerHTML,
        panelDisplay: nodes.gimbalPanel.style.display
    }));
})();
"""


def _alanlar(**degisiklik):
    """Sayfanın DOĞDUĞU hâl: gimbal seçili, açı 8, diğer dört alan BOŞ."""
    alanlar = {
        'engine_mount': 'gimbal_2axis',
        'gimbal_range': '8',
        'gimbal_actuator_arm': '',
        'gimbal_ring_offset': '',
        'gimbal_bolt_circle': '',
        'gimbal_bolt_count': '',
    }
    alanlar.update(degisiklik)
    return alanlar


def _panel_kos(tmp_path, alanlar, sonuclar, yanit=None, mutasyon=None):
    """Paneli node'da koşturur; fetch çağrıları + basılan gövde döner."""
    blok = _gimbal_blok()
    if mutasyon is not None:
        eski, yeni = mutasyon
        assert eski in blok, 'mutasyon dayanağı kaynakta yok: %r' % eski
        blok = blok.replace(eski, yeni, 1)
    spec = {'fields': alanlar, 'results': sonuclar,
            'response': yanit or {'status': 200, 'body': {}}}
    script = tmp_path / 'gimbal_kos.js'
    script.write_text(
        HARNESS.replace('__SPEC__', json.dumps(spec)).replace('__BLOCK__', blok),
        encoding='utf-8')
    proc = subprocess.run([NODE, str(script)], capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 0, 'gimbal paneli node altında çöktü:\n' + proc.stderr
    return json.loads(proc.stdout)


def _beyan_alanlari(govde):
    """Basılan eksik-girdi beyanından alan adları listesi."""
    m = re.search(r'\[\[liq\.js\.gimbal_missing_inputs\]\]\s*([^<]*)</p>', govde)
    assert m, 'eksik-girdi beyanı basılmamış; basılan gövde: %r' % govde[:300]
    return [p.strip() for p in m.group(1).split(',') if p.strip()]


#: Yerel kapıyı devre dışı bırakan mutasyon — "fetch koşulsuz atılsın".
#: Hem kusuru kilitleyen bekçinin dayanağı hem de köprü testinde ucun ne
#: göreceğini panelin KENDİ payload'ıyla ölçmenin aracı.
_KAPIYI_KALDIR = ('if (arm === null) {', 'if (false) {')


@needs_node
def test_bos_kolda_istek_atilmaz(tmp_path):
    """Kol boşken /api/gimbal-mount'a istek ATILMAZ; beyan yerel basılır.

    Ölçülen kusur buydu: istek atılıyor, uç doğru şekilde 422 dönüyor ve
    konsola her hesapta kırmızı satır düşüyordu. Beyanın İÇERİĞİ değişmedi
    (aynı anahtar, aynı alan adı) — değişen, gürültünün kaynağı.
    """
    kosum = _panel_kos(tmp_path, _alanlar(), {'thrust': 10000.0})
    assert kosum['fetchCalls'] == [], (
        'boş kolda hâlâ istek atılıyor (konsol gürültüsü geri geldi): %s'
        % kosum['fetchCalls'])
    assert _beyan_alanlari(kosum['body']) == ['actuator_arm_m']
    assert 'liq.js.gimbal_missing_inputs' in kosum['usedKeys']
    # "Hesaplanıyor…" ara metni bile basılmaz: hesap hiç başlamadı.
    assert 'liq.js.gimbal_computing' not in kosum['usedKeys']
    # Panel yine de görünür ve NEDENİ söyler (sessiz boş kutu değil).
    assert kosum['panelDisplay'] == 'block'


@needs_node
def test_bos_kolda_istek_atilmamasi_mutasyonla_kilitli(tmp_path):
    """Kusuru kilitleyen bekçi: kapı kaldırılırsa koşum KIRMIZI olmalı.

    Mutasyon ``if (arm === null)`` -> ``if (false)``; yani panel eski
    davranışına (koşulsuz fetch) döner. Bu testin ölçtüğü şey, yukarıdaki
    bekçinin gerçekten davranışa bağlı olduğudur.
    """
    mutant = _panel_kos(tmp_path, _alanlar(), {'thrust': 10000.0},
                        yanit={'status': 422,
                               'body': {'missing_fields': ['actuator_arm_m']}},
                        mutasyon=_KAPIYI_KALDIR)
    assert len(mutant['fetchCalls']) == 1, (
        'mutasyon istek attırmadı — bekçi kaynağı yanlış yere bağlanmış')
    assert mutant['fetchCalls'][0]['url'] == '/api/gimbal-mount'


@needs_node
@pytest.mark.parametrize('alanlar, sonuclar', [
    (_alanlar(), {'thrust': 10000.0}),                    # yalnız kol eksik
    (_alanlar(), {}),                                     # itki + kol eksik
    (_alanlar(gimbal_range=''), {}),                      # üç zorunlu da eksik
    (_alanlar(engine_mount='gimbal_1axis'), {'thrust': 5.0e5}),  # tek eksen
])
def test_yerel_beyan_sunucu_422_listesiyle_birebir(tmp_path, client, alanlar,
                                                   sonuclar):
    """Yerel beyan, ucun döneceği ``missing_fields`` ile BİREBİR aynı.

    Köprü ölçümü: payload testte yeniden kurulmaz (kopya mantık yalan
    söyleyebilir) — panelin KENDİ gövdesi, kapı mutasyonla açılarak fetch
    taklidinden yakalanır ve GERÇEK uca gönderilir. Ucun listesi ile yerel
    kapının bastığı liste ayrışırsa (ör. sıra değişir, alan adı kayar)
    kullanıcı iki farklı beyan görürdü; bu test onu engeller.
    """
    yerel = _panel_kos(tmp_path, alanlar, sonuclar)
    assert yerel['fetchCalls'] == []
    yerel_alanlar = _beyan_alanlari(yerel['body'])

    mutant = _panel_kos(tmp_path, alanlar, sonuclar, mutasyon=_KAPIYI_KALDIR)
    assert len(mutant['fetchCalls']) == 1
    gercek = _gonder(client, mutant['fetchCalls'][0]['payload'])
    assert gercek.status_code == 422
    assert yerel_alanlar == gercek.get_json()['missing_fields'], (
        'yerel beyan ile uç sözleşmesi ayrıştı')
    assert 'actuator_arm_m' in yerel_alanlar


@needs_node
def test_dolu_kolda_422_emniyet_agi_korunur(tmp_path, client):
    """Kol DOLU ama itki yoksa: istek atılır, ucun 422 beyanı basılır.

    Yerel kapı yalnız boş kol içindir; sunucu sözleşmesi tek doğru kaynak
    olarak kalır. Yanıt uydurulmaz — gerçek uçtan alınıp panele verilir.
    """
    alanlar = _alanlar(gimbal_actuator_arm='0.5')
    ilk = _panel_kos(tmp_path, alanlar, {})
    assert len(ilk['fetchCalls']) == 1, 'dolu kolda istek atılmadı'
    payload = ilk['fetchCalls'][0]['payload']
    assert payload['actuator_arm_m'] == 0.5
    assert 'thrust_N' not in payload

    gercek = _gonder(client, payload)
    assert gercek.status_code == 422
    ikinci = _panel_kos(tmp_path, alanlar, {},
                        yanit={'status': 422, 'body': gercek.get_json()})
    assert _beyan_alanlari(ikinci['body']) == gercek.get_json()['missing_fields']


@needs_node
def test_dolu_kolda_gecerli_hesap_gostergeleri_basilir(tmp_path, client):
    """Başarı yolu bozulmadı: gerçek 200 yanıtı tabloya dönüşür.

    Ortak beyan gövdesine (gimbalMissingHtml) geçiş, hesap yolunu
    etkilemez; bu test onu uçtan uca ölçer.
    """
    alanlar = _alanlar(gimbal_actuator_arm='0.5', gimbal_ring_offset='0.4',
                       gimbal_bolt_circle='600', gimbal_bolt_count='12')
    ilk = _panel_kos(tmp_path, alanlar, {'thrust': 1.0e6})
    payload = ilk['fetchCalls'][0]['payload']
    assert payload['bolt_circle_diameter_m'] == pytest.approx(0.6)  # mm -> m

    gercek = _gonder(client, payload)
    assert gercek.status_code == 200, gercek.get_data(as_text=True)[:300]
    kosum = _panel_kos(tmp_path, alanlar, {'thrust': 1.0e6},
                       yanit={'status': 200, 'body': gercek.get_json()})
    assert 'spec-table' in kosum['body']
    assert 'liq.js.gimbal_missing_inputs' not in kosum['usedKeys']
    assert 'liq.js.gimbal_axial_thrust' in kosum['usedKeys']


def test_bos_kol_kapisi_fetchten_once():
    """Yapısal sıra: yerel kapı fetch'ten ÖNCE ve ``return`` ile biter."""
    blok = _gimbal_blok()
    kapi = blok.index('if (arm === null) {')
    istek = blok.index("fetch('/api/gimbal-mount'")
    assert kapi < istek, 'yerel kapı fetch çağrısından sonra kalmış'
    ara = blok[kapi:istek]
    assert 'gimbalMissingHtml(' in ara and 'return;' in ara, (
        'kapı beyan basmadan/erken dönmeden geçiyor')


def test_yerel_ve_422_beyani_ortak_govdeyi_kullanir():
    """Tek gövde: iki yol da gimbalMissingHtml çağırır, metin bir yerde durur.

    Beyan metni iki yere kopyalanırsa biri güncellenip diğeri kalır ve
    kullanıcı aynı durumu iki farklı cümleyle görür.
    """
    blok = _gimbal_blok()
    assert blok.count('gimbalMissingHtml(') >= 3, (
        'tanım + iki çağrı yerinden azı var — beyan yolları ayrışmış')
    assert blok.count("'liq.js.gimbal_missing_inputs'") == 1, (
        'eksik-girdi metni birden fazla yerde kurulmuş')


def test_yerel_zorunlu_alan_listesi_uc_ile_ayni():
    """Parametre tutarlılığı: sayfadaki liste == app.py'deki _GIMBAL_REQUIRED.

    Sıra dahil aynı olmalı; uçta yeni bir zorunlu alan doğar da sayfadaki
    kopya kalırsa yerel beyan eksik alan gizler.
    """
    from hrma.app import _GIMBAL_REQUIRED
    blok = _gimbal_blok()
    m = re.search(r'const GIMBAL_REQUIRED_FIELDS = \[(.*?)\];', blok, re.S)
    assert m, 'liquid.html içinde GIMBAL_REQUIRED_FIELDS listesi yok'
    sayfa = re.findall(r"'([A-Za-z_0-9]+)'", m.group(1))
    assert sayfa == list(_GIMBAL_REQUIRED), (
        'sayfa listesi %s ile uç listesi %s ayrıştı' % (sayfa,
                                                       list(_GIMBAL_REQUIRED)))
