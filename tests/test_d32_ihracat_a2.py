"""ÖH D32 / ihracat a2 — OH-D31-02: iki uç "yalnız API" olarak yaşar.

ÖLÇÜLEN DURUM (taban ``dd1dcddc``, ``docs/scofield/raw/OH/D32/ihracat/a2/
once_oh_d31_02.json``):

* ``/api/export-cad`` ve ``/api/generate-complete-package`` Flask kural
  haritasında DURUYOR (emekli değil), ama ürün yüzünde (``hrma/templates``
  + ``hrma/static``) **sıfır canlı çağrıları** var. Görünen iki satır D30
  arayuz-panel a1 (``896d2e83``) gölgeleme sökümünün YORUM notudur, çağrı
  değildir — ham ``grep`` ikisini ayıramadığı için bu ayrım ölçülmüştür.
* Beyan hiçbir yerde yoktu: changelog 2.6.27 iki ucu ADIYLA anmıyordu
  (``notes_tr``/``notes_en``: yok), d18 uç haritası envanteri onları "karar
  bekleyen borç" diye taşıyordu.

ÜRÜN KARARI (ana model, 15 Eylül 2026; Berke'ye bildirildi, itirazda geri
alınır): iki uç 2.6.27'de ürün yüzüne **BAĞLANMAZ** ve **EMEKLİ EDİLMEZ** —
"yalnız API" olarak yaşarlar.

Bu dosya kararı GERÇEĞE bağlar; üç ayağın üçü birden doğru kalmalıdır:

1. rotalar DURUYOR        -> sessiz emeklilik KIRMIZI verir
2. ürün yüzü ÇAĞIRMIYOR   -> sessiz bağlama KIRMIZI verir
3. beyan ADIYLA duruyor   -> beyanın sessizce silinmesi KIRMIZI verir
   (changelog 2.6.27 + d18 envanteri + uçların kendi belgeleri)

Dördüncü ayak, beyanın DOĞRU olması: "yalnız API" demek, API'nin gerçekten
çalışması demektir. Uçlar gerçek bir çözücü çıktısıyla sınanır. Bilinen
sınır (``motor_type`` yoksa paket ucu hibrit varsayıp ``port_diameter``
ister) KİLİTLENMEZ — beyanla gerçeğin UYUŞMASI sınanır, böylece sınır
ileride onarıldığında bu bekçi yalancı kırmızı vermez (D31 dersi 20).
"""

import contextlib
import io
import json
from pathlib import Path

import pytest
from tests.support.kanit import kanit_gerekli
from tests.support import form_defaults

KOK = Path(__file__).resolve().parent.parent

UCLAR = ('/api/export-cad', '/api/generate-complete-package')

#: d18 uç haritası envanterinde kararı taşıyan im.
KARAR_IMI = 'API-ONLY-KARAR-2627'

#: changelog 2.6.27'deki bölüm başlıkları (TR / EN).
CL_BASLIK_TR = '## Yalnız API olarak yaşayan iki uç (ürün kararı)'
CL_BASLIK_EN = '## Two endpoints that live on as API-only (product decision)'

Z5_SIVI = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'thrust': 10000,
    'chamber_pressure': 100, 'mixture_ratio': 2.5,
    'nozzle_expansion_ratio': 50, 'max_burn_duration': 400,
    'combustion_efficiency': 97, 'contraction_ratio': 4,
    'characteristic_length': 1.2, 'chamber_wall_thickness': 1,
    'cooling_type': 'regenerative', 'injector_type': 'impinging',
    'engine_cycle': 'pressure_fed', 'safety_factor': 2.5,
    # V3.0.5 T-ÇAPA-C1: basınç beslemede ``feed_pressure`` yoksa uç 422
    # ``pressure_fed_feed_pressure_not_supplied`` (V301/L-A a6cf9790b, SV-03:
    # çözücü tank basıncı varsaymaz); sayfanın gönderdiği şablon varsayılanı
    # (tek kaynak, kopyalanmaz — T-ÇAPA-B'nin test_d32_ihracat_a1 deseni).
    'feed_pressure': form_defaults.sayisal_varsayilanlar('liquid')[
        'feed_pressure'],
}


def _quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


#: V3.0.5 T-ÇAPA-C1 — dışa aktarım uçlarının koştuğu sıvı tasarım. İmalat
#: kapısı V301/L-KABUK'tan (6f8240043, 823e59841) beri iki katmanlı
#: rejeneratif cidarı KATMAN KATMAN denetler; ``Z5_SIVI`` (Pc 100 bar,
#: Inconel 1 mm astar) o kapıdan geçmez — ÖLÇÜLDÜ (e038d626f): export-cad
#: ve paket 422 ``chamber_liner`` geçerlilik dışı; 5 mm astar SF 0,2026 ile
#: 422. Kapı doğru çalışıyor (fail-closed), test ise "uç gerçek çözücü
#: çıktısını kabul ediyor mu" diye soruyor. Gövde bu yüzden L-KABUK'un
#: ölçtüğü geçerli noktaya (``GECERLI_NOKTA``: CuCrZr 1 mm astar, O/F 2,0,
#: Pc 50 bar, besleme 75 bar — tek kaynak, kopyalanmaz) çekildi: export-cad
#: 200, paket (motor_type ile) 200, motor_type'sız paket 422
#: ``incomplete_geometry`` (bilinen sınır, aşağıdaki sınıf).
from tests.test_v301_l_kabuk import GECERLI_NOKTA  # noqa: E402

DISA_AKTARIM_SIVI = dict(Z5_SIVI, **GECERLI_NOKTA)


@pytest.fixture(scope='module')
def sivi(client):
    r = _quiet(client.post, '/calculate_liquid', json=DISA_AKTARIM_SIVI)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def surum_2627():
    veri = json.loads((KOK / 'hrma' / 'data' / 'changelog.json')
                      .read_text(encoding='utf-8'))
    for v in veri['versions']:
        # karar §28-19/§28-46: yayımlanmamış 2.6.27 kaydı 3.0.0 adıyla çıkar.
        if v['version'] == '3.0.0':
            return v
    pytest.fail('changelog.json içinde 3.0.0 sürümü yok')


# ---------------------------------------------------------------------------
# 1 — ROTALAR DURUYOR (karar: EMEKLİ EDİLMEZ)
# ---------------------------------------------------------------------------
class TestRotalarDuruyor:
    """Sessiz emeklilik yasak: karar "bağlanmaz" der, "silinir" DEMEZ."""

    @pytest.mark.parametrize('uc', UCLAR)
    def test_rota_kayitli(self, uc):
        from hrma.app import app
        kurallar = {str(r.rule) for r in app.url_map.iter_rules()}
        assert uc in kurallar, (
            '%s rota haritasından düşmüş: ürün kararı (OH-D31-02) bu ucu '
            'EMEKLİ ETMEZ, yalnız arayüze bağlamaz. Emeklilik ayrı bir '
            'karardır ve changelog ile birlikte verilir.' % uc)

    @pytest.mark.parametrize('uc', UCLAR)
    def test_rota_post_kabul_ediyor(self, client, uc):
        """Rota var ama 405/404 veriyorsa "yalnız API" boş bir sözdür."""
        r = _quiet(client.post, uc, json={})
        assert r.status_code not in (404, 405), (
            '%s POST kabul etmiyor (HTTP %s)' % (uc, r.status_code))


# ---------------------------------------------------------------------------
# 2 — ÜRÜN YÜZÜ ÇAĞIRMIYOR (karar: BAĞLANMAZ)
# ---------------------------------------------------------------------------
def _urun_dosyalari():
    for alt in ('templates', 'static'):
        for yol in sorted((KOK / 'hrma' / alt).rglob('*')):
            if yol.suffix in ('.js', '.html') and yol.is_file():
                yield yol


def _yorum_satiri_mi(satir):
    """Satır bir YORUM satırı mı?

    Basit ve denetlenebilir kural: kırpılmış satır ``//``, ``*``, ``/*``
    ya da ``<!--`` ile başlıyorsa yorumdur. Ölçüm betiğindeki tam
    sınıflandırıcının (blok durumu + tırnak makinesi) yerine bilerek DAHA
    KATI bir kural konur: sonuna yorum iliştirilmiş CANLI bir çağrı da
    burada yakalanır.
    """
    s = satir.strip()
    return (s.startswith('//') or s.startswith('*') or s.startswith('/*')
            or s.startswith('<!--'))


class TestUrunYuzuCagirmiyor:
    """Sessiz bağlama yasak: uç arayüze bağlanırsa karar değişmiş demektir.

    Bu bekçi bir YASAK değil, bir SENKRON kaydıdır: uçları ürün yüzüne
    bağlamak meşru bir karardır — ama o kararla birlikte changelog ve
    envanter de güncellenmelidir. Bekçi ikisinin ayrışmasını görür.
    """

    @pytest.mark.parametrize('uc', UCLAR)
    def test_canli_cagri_yok(self, uc):
        canli = []
        for yol in _urun_dosyalari():
            try:
                ham = yol.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError):
                continue
            if uc not in ham:
                continue
            for no, satir in enumerate(ham.splitlines(), 1):
                if uc in satir and not _yorum_satiri_mi(satir):
                    canli.append('%s:%d: %s'
                                 % (yol.relative_to(KOK), no, satir.strip()[:110]))
        assert not canli, (
            '%s ürün yüzünden çağrılıyor, oysa 2.6.27 kararı "yalnız API" '
            '(OH-D31-02). Karar değiştiyse changelog 2.6.27 bölümü ve d18 '
            'envanteri de güncellenmelidir:\n  %s' % (uc, '\n  '.join(canli)))


# ---------------------------------------------------------------------------
# 3 — BEYAN ADIYLA DURUYOR
# ---------------------------------------------------------------------------
class TestBeyanChangelogda:
    """Karar kullanıcıya changelog 2.6.27'de ADIYLA söylenir."""

    @pytest.mark.parametrize('alan,baslik',
                             [('notes_tr', CL_BASLIK_TR),
                              ('notes_en', CL_BASLIK_EN)])
    def test_bolum_var(self, surum_2627, alan, baslik):
        assert baslik in surum_2627[alan], (
            '%s içinde "yalnız API" bölümü yok: %s' % (alan, baslik))

    @pytest.mark.parametrize('alan', ['notes_tr', 'notes_en'])
    @pytest.mark.parametrize('uc', UCLAR)
    def test_uc_adiyla_geciyor(self, surum_2627, alan, uc):
        assert uc in surum_2627[alan], (
            '%s changelog %s içinde ADIYLA geçmiyor' % (uc, alan))


class TestBeyanEnvanterde:
    """d18 uç haritası envanteri artık "karar bekliyor" DEMEZ."""

    @pytest.fixture(scope='class')
    def d18(self):
        return (KOK / 'tests' / 'test_d18_bekci_cevirisi_a1.py').read_text(
            encoding='utf-8')

    def test_karar_imi_var(self, d18):
        assert KARAR_IMI in d18, (
            'd18 envanterinde ürün kararının imi (%s) yok; iki uç orada '
            '"karar bekleyen borç" olarak duruyorsa beyan ile envanter '
            'ayrışmıştır' % KARAR_IMI)

    @pytest.mark.parametrize('uc', UCLAR)
    def test_uc_envanterde(self, d18, uc):
        assert ("'%s'" % uc) in d18, (
            '%s d18 envanterinden düşmüş; envanter gevşetilmez' % uc)


class TestBeyanKaynakta:
    """Uçların KENDİ belgesi de kararı söyler (API okuyucusunun gördüğü yer).

    "Yalnız API" bir uç için docstring, belgenin TAMAMIDIR: arayüzde
    karşılığı olmadığı için kullanıcı onu başka hiçbir yerde göremez.
    """

    @pytest.mark.parametrize('islev_adi', ['export_cad_files',
                                           'generate_complete_design_package'])
    def test_docstring_karari_soyluyor(self, islev_adi):
        import inspect

        import hrma.app as appmod

        belge = inspect.getdoc(getattr(appmod, islev_adi)) or ''
        assert 'API-ONLY' in belge, (
            '%s belgesinde "API-ONLY" beyanı yok' % islev_adi)
        assert 'OH-D31-02' in belge, (
            '%s belgesi kararın kimliğini (OH-D31-02) taşımıyor' % islev_adi)


class TestKapsamBelgesiDogru:
    """``docs/kapsam/ne-yapar.md`` iki ucu ürün özelliği gibi saymaz.

    ÖLÇÜLDÜ (taban): tablo ``/api/generate-complete-package``ı
    ``/api/export-complete-zip`` ile AYNI satırda "Tam paket ZIP" diye
    sayıyordu. İki uç aynı şeyi üretmiyor — kardeş uç gerçek bir ZIP
    döndürür, bu uç JSON döndürür — ve bu uç arayüzden hiç çağrılmıyor.
    """

    @pytest.fixture(scope='class')
    def kapsam(self):
        return (KOK / 'docs' / 'kapsam' / 'ne-yapar.md').read_text(
            encoding='utf-8')

    def test_zip_satiri_paket_ucunu_saymiyor(self, kapsam):
        for satir in kapsam.splitlines():
            if 'Tam paket ZIP' in satir:
                assert '/api/generate-complete-package' not in satir, (
                    'kapsam belgesi paket ucunu hâlâ ZIP üreticisi sayıyor; '
                    'ölçüm: o uç JSON döndürür: ' + satir.strip()[:140])

    def test_yalniz_api_beyani_var(self, kapsam):
        assert 'yalnız API' in kapsam, (
            'kapsam belgesi iki ucun "yalnız API" olduğunu söylemiyor')


# ---------------------------------------------------------------------------
# 4 — BEYAN DOĞRU: "yalnız API" demek API ÇALIŞIYOR demektir
# ---------------------------------------------------------------------------
class TestAPIGercektenCalisiyor:
    """Karar uçları YAŞATIYOR; yaşayan uç iş görmelidir."""

    def test_export_cad_gercek_cozucu_ciktisini_kabul_ediyor(self, client, sivi):
        r = _quiet(client.post, '/api/export-cad',
                   json={'motor_data': sivi,
                         'formats': ['technical_drawings']})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert (r.get_json() or {}).get('status') == 'success'

    def test_paket_ucu_motor_type_ile_paket_uretiyor(self, client, sivi):
        """Belgelenen kullanım: ``motor_type`` gönderilirse paket üretilir."""
        r = _quiet(client.post, '/api/generate-complete-package',
                   json={'motor_data': dict(sivi, motor_type='liquid')})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        govde = r.get_json() or {}
        assert govde.get('status') == 'success'
        assert 'complete_package' in govde


class TestBilinenSinirBeyanlaUyusuyor:
    """Beyan ⟷ gerçek senkronu (sınırı KİLİTLEMEZ).

    Bugün ölçülen: ``motor_type`` taşımayan bir sıvı sonucu paket ucundan
    HTTP 422 ``incomplete_geometry`` + ``missing_fields=['port_diameter']``
    alır; ``_STL_REQUIRED_FIELDS['liquid']`` ise ``port_diameter``
    İSTEMEZ — ret, kapının ``motor_type`` yokluğunda ``hybrid`` VARSAYMASINDAN
    doğar (devir bulgusu, bu kalemin kapsamı dışı).

    Bekçi bu davranışı ŞART KOŞMAZ: sınır onarıldığında test yeşil kalır.
    Sınandığı tek şey, sınır DURUYORSA changelog'un onu söylüyor olmasıdır.
    """

    def test_sinir_varsa_changelogda_yaziyor(self, client, sivi, surum_2627):
        r = _quiet(client.post, '/api/generate-complete-package',
                   json={'motor_data': sivi})
        if r.status_code == 200:
            return          # sınır onarılmış: beyan borcu yok
        govde = r.get_json() or {}
        assert govde.get('status') == 'incomplete_geometry', (
            'paket ucu beklenmedik bir hükümle reddetti: %s / %s'
            % (r.status_code, govde.get('status')))
        for alan in ('notes_tr', 'notes_en'):
            metin = surum_2627[alan]
            assert 'motor_type' in metin, (
                'paket ucu motor_type yokluğunda reddediyor ama changelog '
                '%s bunu söylemiyor' % alan)

    def test_liquid_sozlesmesi_port_diameter_istemiyor(self):
        """Devir bulgusunun çapası: ret ``motor_type`` varsayımından doğuyor."""
        from hrma.app import _STL_REQUIRED_FIELDS

        assert 'port_diameter' not in _STL_REQUIRED_FIELDS['liquid'], (
            'sıvı sözleşmesi port_diameter istemeye başlamış; devir '
            'bulgusunun teşhisi (ret motor_type varsayımından doğuyor) '
            'artık geçerli değil, yeniden ölçülmeli')


# ---------------------------------------------------------------------------
# 5 — ÖLÇÜM DOSYALARI DURUYOR
# ---------------------------------------------------------------------------
class TestKanitDosyalari:
    def test_once_sonra_olcumleri_var(self):
        d = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D32' / 'ihracat' / 'a2'
        for ad in ('once_oh_d31_02.json', 'sonra_oh_d31_02.json'):
            assert (kanit_gerekli(d / ad)).is_file(), 'ölçüm dosyası yok: %s' % ad

    def test_once_olcumu_kusuru_gosteriyor(self):
        d = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D32' / 'ihracat' / 'a2'
        once = json.loads((kanit_gerekli(d / 'once_oh_d31_02.json')).read_text(
            encoding='utf-8'))
        for uc in UCLAR:
            assert once['urun_yuzu'][uc]['canli_sayisi'] == 0, (
                'önce ölçümü %s için canlı çağrı bulmuş' % uc)
            assert once['rota'][uc] is True
        assert once['beyan']['changelog']['notes_tr'][UCLAR[0]] is False, (
            'önce ölçümünde changelog beyanı zaten varmış görünüyor')
