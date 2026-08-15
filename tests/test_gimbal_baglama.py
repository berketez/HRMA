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
     KONMAZ, eksik zorunlu girdi 422 sözleşmesiyle BEYAN edilir (sayı
     uydurulmaz), sabit montajda NOT_APPLICABLE beyanı,
  3. i18n_pages.js -> panel metinleri EN+TR.

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
"""

import inspect
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIQUID = ROOT / 'hrma' / 'templates' / 'liquid.html'
APP_PY = ROOT / 'hrma' / 'app.py'


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
