"""CI kapsam kapısı — "çözüm doğru, LİSTESİ çürümüş" sınıfına karşı bekçi.

Bu deponun tekrar eden kusur sınıfı şudur: bir kör nokta doğru biçimde
kapatılır, kapatma bir ELLE YAZILMIŞ listeye dayanır, sonra listeye
yazılmayan yeni dosyalar sessizce kapsamın dışında kalır.

Ölçülmüş iki vaka:

* 2026-08-03 — 30 ön yüz test dosyası ``node`` ile koşuyordu, CI'da node
  kurulu değildi; hiçbiri bir kez bile koşmamıştı.
* 2026-08-17 (parti 31 / T2-1) — ``tests.yml`` içindeki ``step-export`` işi
  build123d'yi KURUYOR ve fail-closed; ama koşturduğu dosya listesi elle
  yazılmış BEŞ dosyaydı ve çürümüştü. Sonradan eklenen üç build123d-kapılı
  dosya (``test_step_durustluk_kapisi.py``, ``test_faz5_cizim_birim.py``,
  ``test_faz6_sivi.py``) ne o listedeydi ne ``release.yml``'de.

  Ölçüm (bu dosyanın yazıldığı gün, build123d'yi meta_path süzgeciyle
  gizleyerek):

  ==========================================  =======================  ============
  küme                                        build123d YOK            build123d VAR
  ==========================================  =======================  ============
  eski beş dosya                              98 passed / 47 skipped   143 passed / 2 xfailed
  eklenen üç dosya                            84 passed / 19 skipped   102 passed / 1 skipped
  yeni sekiz dosyalık küme                    182 passed / 66 skipped  245 passed / 1 skipped / 2 xfailed
  ==========================================  =======================  ============

  Yani 19 bekçi daha CI'da hiçbir yerde koşmuyordu.

Bu dosyanın işi listeyi bir daha ELLE tutmamaktır: build123d'ye kapılı test
dosyaları KAYNAKTAN türetilir ve iş akışının koşturduğu kümenin içinde olmaları
şart koşulur. Yeni bir kapılı dosya eklenip iş akışına yazılmazsa bu bekçi
KIRILIR. Deponun aynı deseni: ``test_field_wiring_layer_a.py``
``::test_declared_lists_do_not_rot``.
"""

import ast
import functools
import pathlib
import re
import sys
import textwrap

import pytest

from tests.bagimlilik_kapisi import kapi, kurulu_mu

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))

#: ÖH D26 / OH-D25-24 — node kapılı dosya ölçümünün TEK KAYNAĞI. Ölçüm bu
#: bekçide de iş akışlarında da AYNI işlevden gelir; ikinci bir kopya
#: olsaydı ikisi ayrışabilir ve bekçi ürünün ölçtüğünden başka bir sayıyı
#: savunurdu.
import node_kapisi_sayimi  # noqa: E402

#: Depo kökü.
DEPO_KOKU = pathlib.Path(__file__).resolve().parents[1]
#: İş akışı dizini.
ISAKISI_DIZINI = DEPO_KOKU / '.github' / 'workflows'
#: Taranan test dizini.
TEST_DIZINI = DEPO_KOKU / 'tests'

#: Kapının kovaladığı bağımlılık. Tek kaynak: aşağıdaki tarayıcı da, hata
#: mesajları da bunu kullanır.
BAGIMLILIK = 'build123d'

# ---------------------------------------------------------------------------
# CI'da kurulumu DOĞRULANMASI gereken bekçi bağımlılıkları (ÖH FAZ A / A3)
# ---------------------------------------------------------------------------
#: pip ile kurulan, bekçilerin dayandığı kütüphaneler.
ZORUNLU_PAKETLER = ('cantera', 'CoolProp', 'numba', 'rocketcea')

#: pip paketi OLMAYAN ama bekçilerin dayandığı CI araçları. Bunlar
#: requirements dosyalarında ARANMAZ (orada olamazlar); yalnız iş akışında
#: kurulumlarının doğrulanması şart koşulur.
ZORUNLU_ARACLAR = ('node',)

#: CI test işlerinde kurulumu doğrulanacak her şey.
ZORUNLU_CI = ZORUNLU_PAKETLER + ZORUNLU_ARACLAR

#: Test koşan CI işleri: (iş akışı dosyası, iş adı).
CI_TEST_ISLERI = (('tests.yml', 'pytest'), ('release.yml', 'testler'))

#: ÖDENMEMİŞ borçlar: (iş akışı, bağımlılık) -> defter gerekçesi. Bu çiftler
#: ``xfail(strict=True)`` ile imlenir; borç ödendiğinde XPASS olur ve strict
#: im KIRMIZI verir — yani bekçi kendi imini KALDIRTIR.
#:
#: ÖH D26 / OH-B2-01 — BOŞ. Tek borç ('release.yml', 'rocketcea') idi ve bu
#: dalgada ÖDENDİ: `release.yml` `testler` işine tests.yml'deki eşinin aynısı
#: eklendi (`rocketcea` ithali + `from rocketcea.cea_obj import CEA_Obj`).
#: İmin kendi sözleşmesi gereği ödeme XPASS verip strict im kırmızıya döndü,
#: bu yüzden im KALDIRILDI — borç imi kusuru değil kusurun ÖLÇÜLDÜĞÜNÜ imler;
#: kusur gidince im de gider. Sözlük boş kalır ki yeni bir borç doğduğunda
#: mekanizma yerinde olsun (test_borc_listesi_curumuyor onu da denetler).
CI_DOGRULAMA_BORCLARI: dict[tuple[str, str], str] = {}


#: Bir test dosyasını node'a KAPILI yapan deyim — TEK KAYNAK araçtadır.
_NODE_KAPISI = node_kapisi_sayimi.NODE_KAPISI

#: İş akışı YORUMLARINDAKİ "<N> test dosyası" iddiası. Satır içi arar
#: (``[ ]*``): satır sonundan taşan yanlış eşleşme olmasın. ARTIK EŞLEŞME
#: BEKLENMİYOR — bu kalıbın varlığı kusurdur (OH-D25-24).
_YORUM_DOSYA_SAYISI = re.compile(r'(\d+)[ ]*test dosyası')

#: İş akışının sayımı KAYNAKTAN türettiğini gösteren tek kaynak aracın adı.
_SAYIM_ARACI = 'tools/node_kapisi_sayimi.py'


@functools.lru_cache(maxsize=1)
def node_kapili_test_dosyalari() -> frozenset:
    """``node``a kapılı test dosyaları — TEK KAYNAK: sayım aracı."""
    return node_kapisi_sayimi.node_kapili_test_dosyalari(DEPO_KOKU)


def _kod_satirlari(komutlar: str) -> str:
    """Kabuk/Python YORUM satırlarını atar — anmak yapmak değildir."""
    return '\n'.join(s for s in komutlar.splitlines()
                     if not s.lstrip().startswith('#'))


def _ci_dogrulama_vakalari():
    """(iş akışı, iş, bağımlılık) üçlüleri — her biri AYRI bekçi.

    Tek toplu iddia KULLANILMIYOR: release.yml'nin rocketcea borcu (yukarıda)
    tek testte toplansaydı xfail imi aynı testteki dokuz sağlam denetimi de
    sessizleştirirdi. Kampanyanın ölçülmüş dersi — bir borç imi, yanındaki
    sağlam iddiaları rehin alamaz.
    """
    for is_akisi, is_adi in CI_TEST_ISLERI:
        for bagimlilik in ZORUNLU_CI:
            gerekce = CI_DOGRULAMA_BORCLARI.get((is_akisi, bagimlilik))
            imler = ([pytest.mark.xfail(strict=True, reason=gerekce)]
                     if gerekce else [])
            yield pytest.param(is_akisi, is_adi, bagimlilik, marks=imler,
                               id=f'{is_akisi}-{bagimlilik}')

#: ``step-export`` işinin koşturduğu ama build123d'ye KAPILI OLMAYAN dosyalar.
#: Beyaz liste disiplini (BULGU_KAYIT_DEFTERI.md "Beyaz liste disiplini"):
#: her girişin gerekçesi olmak zorundadır ve giriş listeden düşerse bu dosya
#: kırılır. Tek giriş: ÖH A2 sivi-sogutma denetçi Ş7 (4. tur, 29 Eyl).
EK_DOSYALAR_GEREKCE: dict[str, str] = {
    'tests/step_d37_sivi_a1.py': (
        'YALNIZ bu işte koşan STEP uçtan uca bekçisi (montaj STEP metni). '
        'Dosya bilerek test_*.py desenine uymaz: ana pytest işi (build123d '
        'KURULU DEĞİL) onu toplamaz, bu yüzden importorskip taşımaz ve '
        'kaynak tarayıcısı onu kapılı saymaz; ana işin ölçülmüş atlama '
        'bütçesine +2 yazılmaz. build123d yoksa ATLAMAZ, HATA verir '
        '(bu işin ortam teyidi zaten fail-closed).'),
}


# ---------------------------------------------------------------------------
# Kaynak tarayıcı — "hangi test dosyası build123d'ye kapılı?"
# ---------------------------------------------------------------------------

def _kapi_adlari(agac: ast.Module, kaynak: str) -> set[str]:
    """Modül düzeyinde build123d varlığını tutan değişken adları.

    ``STEP_VAR = importlib.util.find_spec('build123d') is not None`` ya da
    ``_B123D_YOK = not getattr(step_export, 'BUILD123D_AVAILABLE', True)``
    gibi dolaylı kapıları yakalar; böylece ``skipif`` koşulu build123d
    sözcüğünü hiç geçirmese bile dosya kapılı sayılır.
    """
    adlar: set[str] = set()
    for dugum in agac.body:
        if not isinstance(dugum, (ast.Assign, ast.AnnAssign)):
            continue
        deger = dugum.value
        if deger is None:
            continue
        parca = (ast.get_source_segment(kaynak, deger) or '').lower()
        if BAGIMLILIK not in parca:
            continue
        hedefler = (dugum.targets if isinstance(dugum, ast.Assign)
                    else [dugum.target])
        for hedef in hedefler:
            if isinstance(hedef, ast.Name):
                adlar.add(hedef.id)
    # step_export.BUILD123D_AVAILABLE doğrudan ithal edilmiş olabilir.
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.ImportFrom):
            for ad in dugum.names:
                if 'build123d' in (ad.name or '').lower():
                    adlar.add(ad.asname or ad.name)
    return adlar


def _cagri_adi(dugum: ast.Call) -> str:
    """``pytest.mark.skipif`` -> ``skipif`` (çağrının son adı)."""
    f = dugum.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ''


def _dosya_kapili_mi(yol: pathlib.Path) -> bool:
    """Dosyada build123d yokluğuna bağlı bir ATLAMA mekanizması var mı?

    İki idiom aranır (deponun kullandıkları):

    1. ``pytest.importorskip('build123d')``
    2. ``skipif(...)`` — koşulu ya da gerekçesi build123d'ye (veya yukarıdaki
       ``_kapi_adlari`` ile bulunan dolaylı kapı adına) değinen her çağrı;
       ``pytestmark`` ataması, dekoratör ve ``pytest.param(..., marks=...)``
       biçimlerinin üçünü de kapsar.

    DİZE SABİTLERİ SAYILMAZ: ``assert "BUILD123D_AVAILABLE" in komutlar``
    gibi iş akışı sözleşmesini sınayan satırlar dosyayı kapılı yapmaz
    (``test_faz4_yayin_kapisi.py`` tam olarak böyledir).
    """
    kaynak = yol.read_text(encoding='utf-8')
    if BAGIMLILIK not in kaynak.lower():
        return False
    try:
        agac = ast.parse(kaynak)
    except SyntaxError:  # pragma: no cover - depoda sözdizimi hatası yok
        return False

    adlar = _kapi_adlari(agac, kaynak)

    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Call):
            continue
        cagri = _cagri_adi(dugum)

        if cagri == 'importorskip':
            for arg in dugum.args:
                if (isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and arg.value.lower() == BAGIMLILIK):
                    return True
            continue

        if cagri == 'skipif':
            parca = (ast.get_source_segment(kaynak, dugum) or '').lower()
            if BAGIMLILIK in parca:
                return True
            if any(ad.lower() in parca for ad in adlar):
                return True

    return False


@functools.lru_cache(maxsize=1)
def _kapili_test_dosyalari_ham() -> frozenset:
    bulunan = set()
    for yol in sorted(TEST_DIZINI.rglob('test_*.py')):
        if _dosya_kapili_mi(yol):
            bulunan.add(yol.relative_to(DEPO_KOKU).as_posix())
    return frozenset(bulunan)


def kapili_test_dosyalari() -> set[str]:
    """build123d'ye kapılı test dosyalarının depo-göreli yolları.

    Tarama dört ayrı bekçide kullanılıyor; sonuç koşum içinde önbelleklenir
    (kaynak dosyalar koşum sırasında değişmez).
    """
    return set(_kapili_test_dosyalari_ham())


# ---------------------------------------------------------------------------
# İş akışı okuyucu
# ---------------------------------------------------------------------------

def _is_akisi(ad: str) -> dict:
    yaml = pytest.importorskip(
        'yaml', reason='PyYAML yok — requirements-dev.txt bunu ZORUNLU '
                       'kılar; kurulum düşmüşse iş akışı bekçileri koşamaz')
    return yaml.safe_load((ISAKISI_DIZINI / ad).read_text(encoding='utf-8'))


def _is_komutlari(is_akisi_adi: str, is_adi: str) -> str:
    veri = _is_akisi(is_akisi_adi)
    isler = veri['jobs']
    assert is_adi in isler, (
        f"{is_akisi_adi} içinde '{is_adi}' işi yok "
        f'(bulunan işler: {sorted(isler)})')
    return '\n'.join(a.get('run', '') or '' for a in isler[is_adi]['steps'])


#: Komut metninden ``tests/...py`` yollarını çıkarır.
_TEST_YOLU = re.compile(r'tests/[\w/]+\.py')


def _kosulan_dosyalar(komutlar: str) -> set[str]:
    """Komuttaki GERÇEK argümanlar. Kabuk yorumları (``#``) sayılmaz —
    yoksa bir yorumda dosya adı anmak onu 'koşuluyor' göstermiş olurdu."""
    satirlar = [s for s in komutlar.splitlines()
                if not s.lstrip().startswith('#')]
    return set(_TEST_YOLU.findall('\n'.join(satirlar)))


# ---------------------------------------------------------------------------
# 1) Tarayıcının kendisi boş dönmemeli (kapının kapısı)
# ---------------------------------------------------------------------------

class TestTarayiciCalisiyor:
    """Tarayıcı sessizce boş dönerse aşağıdaki kapsam testleri BOŞ geçer.

    Bu sınıf o kaçamağı kapatır: tarayıcı hem bilinen kapılı dosyaları
    bulmalı, hem de kapılı OLMAYAN benzer dosyaları kapılı saymamalıdır.
    """

    #: Bu dosyalar ölçümle kapılıdır (build123d gizlenince testleri atlanır).
    ORNEK_KAPILI = (
        'tests/test_step_import.py',
        'tests/test_tank_step_units.py',
        'tests/test_faz4_export_geometri.py',
        'tests/test_faz4_app_export.py',
        'tests/test_export_generators.py',
        'tests/test_step_durustluk_kapisi.py',
        'tests/test_faz5_cizim_birim.py',
        'tests/test_faz6_sivi.py',
    )

    #: Bunlar build123d SÖZCÜĞÜNÜ geçirir ama kapılı DEĞİLDİR:
    #: test_faz4_yayin_kapisi.py sözcüğü iş akışı sözleşmesini sınayan bir
    #: dize sabitinde kullanır; test_faz5_app_export.py yalnız docstring'de
    #: anar. Tarayıcı bunları kapılı sayarsa yalancı kapsam üretir.
    ORNEK_KAPISIZ = (
        'tests/test_faz4_yayin_kapisi.py',
        'tests/test_faz5_app_export.py',
    )

    def test_bilinen_kapili_dosyalar_bulunuyor(self):
        bulunan = kapili_test_dosyalari()
        eksik = [d for d in self.ORNEK_KAPILI if d not in bulunan]
        assert not eksik, (
            'kaynak tarayıcı bilinen build123d-kapılı dosyaları göremiyor: '
            f'{eksik}; tarayıcı bozulduysa aşağıdaki kapsam bekçileri BOŞ '
            'geçer (yalancı yeşil)')

    def test_sozcugu_gecen_her_dosya_kapili_sayilmiyor(self):
        bulunan = kapili_test_dosyalari()
        yanlis = [d for d in self.ORNEK_KAPISIZ if d in bulunan]
        assert not yanlis, (
            f'tarayıcı kapılı OLMAYAN dosyayı kapılı saydı: {yanlis}; '
            'dize sabiti / docstring anımsatması kapı değildir')

    def test_taranan_dosya_sayisi_anlamli(self):
        """Tarama kapsamı sessizce daralmasın (kova boşalırsa kapı körelir)."""
        toplam = len(list(TEST_DIZINI.rglob('test_*.py')))
        assert toplam > 100, (
            f'tests/ altında yalnız {toplam} test dosyası tarandı — '
            'tarama kapsamı çökmüş olabilir')


# ---------------------------------------------------------------------------
# 2) tests.yml — liste ÇÜRÜYEMEZ
# ---------------------------------------------------------------------------

class TestStepExportKapsami:
    """``step-export`` işi build123d'ye kapılı HER dosyayı koşmalı."""

    def test_kapili_her_dosya_step_export_isinde(self):
        komutlar = _is_komutlari('tests.yml', 'step-export')
        kosulan = _kosulan_dosyalar(komutlar)
        kapili = kapili_test_dosyalari()
        eksik = sorted(kapili - kosulan)
        assert not eksik, (
            'build123d\'ye kapılı şu test dosyaları `step-export` işinde '
            f'KOŞMUYOR: {eksik}\n'
            'Bu dosyaların bekçileri CI\'da hiçbir yerde koşmaz: ana `pytest` '
            'işi build123d kurmaz (numpy<2 pini), bu iş de onları listesine '
            'almamıştır. Ya .github/workflows/tests.yml içindeki pytest '
            'komutuna ekleyin, ya da dosyanın build123d kapısını kaldırın.')

    def test_iste_kosulan_her_dosya_ya_kapili_ya_beyanli(self):
        """Ters yön: listeye kapısız dosya sızarsa gerekçesi yazılmalı."""
        komutlar = _is_komutlari('tests.yml', 'step-export')
        kosulan = _kosulan_dosyalar(komutlar)
        kapili = kapili_test_dosyalari()
        beyansiz = sorted(kosulan - kapili - set(EK_DOSYALAR_GEREKCE))
        assert not beyansiz, (
            f'`step-export` işi build123d\'ye kapılı OLMAYAN dosya koşuyor: '
            f'{beyansiz}. Bu işin atlama bütçesi sıfırdır; kapısız dosya '
            'buraya girerse ya gereksiz yere iki kez koşar ya bütçeyi kırar. '
            'Gerekçesi varsa EK_DOSYALAR_GEREKCE sözlüğüne yazın.')

    def test_beyan_listesi_curumuyor(self):
        """EK_DOSYALAR_GEREKCE girişleri gerçekten koşuluyor olmalı."""
        komutlar = _is_komutlari('tests.yml', 'step-export')
        kosulan = _kosulan_dosyalar(komutlar)
        olu = sorted(set(EK_DOSYALAR_GEREKCE) - kosulan)
        assert not olu, (
            f'EK_DOSYALAR_GEREKCE çürüdü — şu girişler artık `step-export` '
            f'işinde koşulmuyor: {olu}')
        gerekcesiz = [d for d, g in EK_DOSYALAR_GEREKCE.items()
                      if not (g or '').strip()]
        assert not gerekcesiz, (
            f'gerekçesiz beyan girişi: {gerekcesiz}')

    def test_kosulan_her_dosya_diskte_var(self):
        """Yeniden adlandırma listeyi sessizce boşaltmasın."""
        komutlar = _is_komutlari('tests.yml', 'step-export')
        yok = sorted(d for d in _kosulan_dosyalar(komutlar)
                     if not (DEPO_KOKU / d).exists())
        assert not yok, (
            f'`step-export` işi var olmayan dosyaları koşuyor: {yok} — '
            'pytest bunları toplayamaz, iş sessizce daralır')


# ---------------------------------------------------------------------------
# 3) Ters kapı sözleşmesi — bütçe istisnası dayanaksız kalmasın
# ---------------------------------------------------------------------------

class TestTersKapiSozlesmesi:
    """`step-export` bütçesi tek bir istisna tanır: TERS kapı.

    Ters kapılı test, build123d KURULU olduğu için atlanır (ör. "STEP
    üretilemiyorsa paket bunu açıkça söyler" bekçisi). O test sınanmamış
    kalmaz — build123d KURULMAYAN ana `pytest` işinde koşar. Bu sınıf o
    dayanağı kilitler: ana iş `tests/` dizinini bütün olarak koşmayı bırakırsa
    istisnanın gerekçesi çöker ve bekçi kırılır.
    """

    def test_ana_is_tests_dizinini_butun_olarak_kosuyor(self):
        komutlar = _is_komutlari('tests.yml', 'pytest')
        assert re.search(r'pytest\s+tests/\s', komutlar + ' '), (
            "ana `pytest` işi artık `tests/` dizinini bütün olarak koşmuyor; "
            'ters kapılı testler (build123d KURULU diye atlananlar) bu işte '
            'koştukları için `step-export` bütçe istisnası meşruydu — o '
            'dayanak kalktı')

    def test_butce_ters_kapiyi_ADIYLA_ayirt_ediyor(self):
        """İstisna 'her atlamayı affet' biçimine kaymamalı.

        Metin araması yetmez — bütçenin KULLANDIĞI düzenli ifade iş
        akışından çıkarılıp GERÇEK atlama gerekçelerine karşı koşulur.
        İki gerekçe repodaki birebir metinlerdir:
          * ters kapı  : test_faz6_sivi.py:400
          * bağımlılık : test_step_durustluk_kapisi.py / test_tank_step_units.py
        """
        komutlar = _is_komutlari('tests.yml', 'step-export')
        assert re.search(r'sys\.exit\(', komutlar), (
            'atlama bütçesi kırmızıya dönmüyor, yalnız bilgi basıyor')

        desen = re.search(r"ters\s*=\s*re\.compile\(r'([^']+)'\)", komutlar)
        assert desen, (
            'bütçe betiğinde ters-kapı düzenli ifadesi bulunamadı — istisna '
            '"her atlamayı affet" biçimine kaymış olabilir')
        ters = re.compile(desen.group(1))

        assert ters.search('build123d kurulu — .step sınanıyor'), (
            'ters kapı gerekçesi tanınmıyor; test_faz6_sivi.py bu işte '
            'haksız yere kırmızı verir')
        for bagimlilik_gerekcesi in (
                'build123d kurulu değil (STEP üretimi atlanır)',
                'build123d kurulu degil (STEP uretimi atlanir)',
                'build123d kurulu değil — STEP üretimi bu ortamda yok'):
            assert not ters.search(bagimlilik_gerekcesi), (
                f'bütçe {bagimlilik_gerekcesi!r} atlamasını TERS KAPI sayıp '
                'affediyor — bağımlılık eksikliğinden doğan atlama bu işte '
                'HER ZAMAN kırmızı olmalı')


# ---------------------------------------------------------------------------
# 4) release.yml — aynı denetim
# ---------------------------------------------------------------------------

class TestYayinIsAkisiKapsami:
    """Yayın hattı ya aynı kümeyi koşar ya fail-closed olarak devreder.

    ``release.yml``'in kendi test işi build123d KURMAZ; STEP bekçileri orada
    da atlanır. Bugünkü tasarım devirdir: ``ci-durumu`` işi, aynı SHA'da
    ``tests`` iş akışının YEŞİL bittiğini arar ve bulamazsa yayını durdurur.
    Bu bekçi iki şeyi birden korur: (a) devir gerçekten fail-closed, (b)
    yayın hattı KENDİ STEP listesini tutmuyor — tuttuğu an ikinci bir çürüyen
    liste doğardı.
    """

    def test_yayin_kendi_step_listesini_tutmuyor(self):
        veri = _is_akisi('release.yml')
        kapili = kapili_test_dosyalari()
        for is_adi, tanim in veri['jobs'].items():
            komutlar = '\n'.join(a.get('run', '') or ''
                                 for a in tanim.get('steps', []))
            if 'pip install build123d' in komutlar:
                # Kendi kolunu kuruyorsa kümenin TAMAMINI koşmak zorunda.
                eksik = sorted(kapili - _kosulan_dosyalar(komutlar))
                assert not eksik, (
                    f"release.yml '{is_adi}' işi build123d kuruyor ama kapılı "
                    f'şu dosyaları koşmuyor: {eksik}')
                return
        # Kendi kolu yoksa devir sözleşmesi aranır (aşağıdaki test).
        assert 'ci-durumu' in veri['jobs'], (
            'release.yml ne build123d kuran bir iş içeriyor ne de `tests` iş '
            'akışına devreden `ci-durumu` işi — STEP bekçileri yayın hattında '
            'hiçbir yerde koşmuyor demektir')

    def test_release_yml_step_kapsamini_devrediyor(self):
        veri = _is_akisi('release.yml')
        isler = veri['jobs']
        assert 'ci-durumu' in isler, (
            "release.yml'de 'ci-durumu' işi yok — `tests` iş akışının bu "
            "SHA'da yeşil olduğu doğrulanmıyor")
        komutlar = '\n'.join(a.get('run', '') or ''
                             for a in isler['ci-durumu']['steps'])
        assert "'tests'" in komutlar or '"tests"' in komutlar or (
            "k.get('name') == 'tests'" in komutlar), (
            "'ci-durumu' işi `tests` iş akışını adıyla aramıyor")
        # FAIL-CLOSED: üç durumun üçü de yayını durdurmalı.
        cikislar = re.findall(r'sys\.exit\(', komutlar)
        assert len(cikislar) >= 3, (
            "'ci-durumu' devri fail-closed değil: koşu yok / hâlâ koşuyor / "
            f'yeşil değil hâllerinin üçü de durdurmalı (bulunan sys.exit: '
            f'{len(cikislar)})')
        assert isler['ci-durumu'].get('needs'), (
            "'ci-durumu' işi hiçbir işe bağlı değil — test işinden ÖNCE "
            'koşarsa `tests` henüz bitmemiş olur ve devir anlamsızlaşır')


# ===========================================================================
# 5) ATLAMA GEREKÇESİ YALAN SÖYLEYEMEZ  (parti 31 / T2-2, T2-3, T2-4)
#
# Ölçülen kusur sınıfı: bir bekçi "kütüphane kurulu değil" diyerek atlıyor,
# oysa kütüphane KURULU ve atlamanın gerçek sebebi ÜRÜN YOLUNUN BOZUK
# olması. Atlama sessizdir; kusur CI'da görünmez.
#
# ÖLÇÜMLER (17 Ağustos 2026, ürün dosyalarına dokunulmadan — bağımlılığın
# giriş noktası çalışma zamanında bozularak):
#   cantera KURULU + ct.Solution patlıyor
#       önce : 61 passed,  2 failed, **39 skipped**  ("Cantera kurulu değil")
#       sonra: 61 passed,  3 failed + 38 error, **0 skipped**
#   CoolProp KURULU + PropsSI patlıyor  (tests/test_pressurant.py)
#       önce : 35 passed, **5 skipped**  ("CoolProp kurulu değil")
#       sonra: 37 passed,  4 failed,     **0 skipped**
#   numba KURULU + HRMA_CFD_DISABLE_NUMBA=1  (tests/cfd)
#       önce : atlama gerekçesi "numba kurulu değil" — YALAN
#       sonra: "HRMA_CFD_DISABLE_NUMBA=1 ile BİLEREK kapatıldı (numba KURULU)"
#
# Aşağıdaki tarayıcı vaka listelemez, TARAR: bir kütüphanenin YOKLUĞUNU iddia
# eden her atlama kapısını bulur ve koşulunun gerçekten bir KURULUM sorusuna
# dayandığını doğrular.
# ===========================================================================

#: Yokluk iddiası taşıyan gerekçe metni.
_YOKLUK_IDDIASI = re.compile(
    r'(cantera|coolprop|numba|build123d|rocketcea|pyyaml)'
    r'[^)]{0,60}?'
    r'(kurulu de[gğ]il|yok\b|kullanilamiyor|kullanılamıyor'
    r'|not installed|unavailable|is missing)',
    re.IGNORECASE)

#: Doğrudan kurulum sorusu soran belirteçler.
_DOGRUDAN_PROB = ('find_spec', 'importorskip', 'kurulu_mu')

#: Tarayıcının çözemediği, GEREKÇELİ istisnalar. Beyaz liste disiplini: her
#: girişin gerekçesi vardır ve giriş gerçekleşmeyi bırakırsa bu dosya kırılır
#: (aşağıdaki ``test_istisna_listesi_curumuyor``).
YALAN_GEREKCE_ISTISNALARI = {
    'tests/test_no_fabrication.py': (
        'İki atlama (CoolProp yoğunluk/faz vakaları) ürünün DÖNÜŞ DEĞERİNE '
        'bakıyor (`density is None`), kuruluma değil: CoolProp kuruluyken '
        'sorgu patlarsa da atlanır. Aynı sınıf, T2-3 ile aynı düzeltmeyi '
        'ister; dosya bu iş kaleminin (A5) sahipliği DIŞINDA olduğu için '
        'burada beyan edilmiştir, ana modele bildirildi.'),
}


#: "Kurulu mu?" sorusunu GERÇEKTEN yanıtlayan istisna tipleri.
#:
#: ÖH FAZ A / A2 (defter P13B1-01'in tarayıcı ayağı). Ölçülen kusur:
#: ``except Exception`` bir KURULUM sorusu değildir — kütüphane KURULUYKEN
#: ithal yolunun patlamasını (``OSError``: derlenmiş uzantı yok,
#: ``RuntimeError``: başlatma hatası, ``AttributeError``: sürüm uyumsuzluğu)
#: da yakalar ve hepsini "kurulu değil" bayrağına çevirir. P13/S1-savci
#: §1.4a bunu iki farklı sabotajla ölçtü: ``RuntimeError`` ve ``OSError``
#: sabotajları BİREBİR aynı sonucu verdi (1 failed, 30 passed, 31 skipped);
#: yani gerekçe metni yalan söylerken sayı hiç kıpırdamıyordu.
_KURULUM_ISTISNALARI = frozenset({'ImportError', 'ModuleNotFoundError'})


def _istisna_adlari(isleyici: ast.ExceptHandler) -> list[str]:
    """``except X:`` -> ``['X']`` · ``except (X, Y):`` -> ``['X', 'Y']``.

    Çıplak ``except:`` ve çözülemeyen ifadeler ``''`` döndürür — bunlar
    "her şeyi yutar" demektir ve kurulum sorusu SAYILMAZ.
    """
    tip = isleyici.type
    if tip is None:
        return ['']
    parcalar = tip.elts if isinstance(tip, ast.Tuple) else [tip]
    adlar: list[str] = []
    for p in parcalar:
        if isinstance(p, ast.Name):
            adlar.append(p.id)
        elif isinstance(p, ast.Attribute):
            adlar.append(p.attr)
        else:  # pragma: no cover - dinamik ifade; güvenli tarafta kal
            adlar.append('')
    return adlar


def _kurulum_sorusu_mu(dugum: ast.Try) -> bool:
    """Bu ``try/except`` bloğu bir KURULUM sorusu yanıtlıyor mu?

    Şart: en az bir işleyici var ve işleyicilerin TAMAMI yalnız
    ``ImportError``/``ModuleNotFoundError`` yakalıyor. Tek bir geniş işleyici
    (``except Exception``, çıplak ``except:``, ``except OSError``) bloğun
    tamamını kurulum sorusu olmaktan çıkarır: o bayrak artık "kurulu mu"
    değil "ithal edilebildi mi" sorusunu yanıtlar ve ikisi AYNI ŞEY DEĞİLDİR.
    """
    if not dugum.handlers:
        return False
    return all(ad in _KURULUM_ISTISNALARI
               for isleyici in dugum.handlers
               for ad in _istisna_adlari(isleyici))


def _import_bayraklari(modul_yolu: pathlib.Path) -> set[str]:
    """Bir modülde ``try: import ... except ImportError:`` ile kurulan bayraklar.

    ``BUILD123D_AVAILABLE``, ``CANTERA_AVAILABLE``, ``_COOLPROP`` gibi
    adlar burada üretilir. Bunlar GERÇEK kurulum sorularıdır: gövdesinde
    bir ``import`` bulunan ve YALNIZ ithal istisnası yakalayan bir ``try``
    bloğunun atadığı adlardır.

    İstisna-tipi denetimi (A2) olmadan bu fonksiyon ``except Exception``
    bayraklarını da onaylıyordu; sonuçta yalan gerekçe tarayıcısı, kusuru
    ÖRTEN kapıyı "dürüst kurulum kapısı" sayıp geçiyordu.
    """
    try:
        agac = ast.parse(modul_yolu.read_text(encoding='utf-8'))
    except (OSError, SyntaxError):  # pragma: no cover
        return set()
    adlar: set[str] = set()
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Try):
            continue
        if not any(isinstance(g, (ast.Import, ast.ImportFrom))
                   for g in ast.walk(ast.Module(body=dugum.body,
                                                type_ignores=[]))):
            continue
        if not _kurulum_sorusu_mu(dugum):
            continue
        for bolum in (dugum.body, *[h.body for h in dugum.handlers],
                      dugum.orelse):
            for g in ast.walk(ast.Module(body=bolum, type_ignores=[])):
                if isinstance(g, ast.Assign):
                    for h in g.targets:
                        if isinstance(h, ast.Name):
                            adlar.add(h.id)
    return adlar


def _modul_yolu(nokta_adi: str) -> pathlib.Path | None:
    """``hrma.export.step_export`` -> dosya yolu (depo içi modüller)."""
    aday = DEPO_KOKU / (nokta_adi.replace('.', '/') + '.py')
    if aday.exists():
        return aday
    aday = DEPO_KOKU / nokta_adi.replace('.', '/') / '__init__.py'
    return aday if aday.exists() else None


def _onayli_kapi_adlari(yol: pathlib.Path, kaynak: str,
                        agac: ast.Module) -> set[str]:
    """Bu dosyada KURULUM sorusu temsil eden adlar (geçişli kapanış)."""
    adlar: set[str] = set()

    # (1) İthal edilen depo modüllerinin import bayrakları.
    for dugum in ast.walk(agac):
        modul_adlari: list[str] = []
        if isinstance(dugum, ast.ImportFrom) and dugum.module:
            modul_adlari.append(dugum.module)
            for ad in dugum.names:
                modul_adlari.append(f'{dugum.module}.{ad.name}')
        elif isinstance(dugum, ast.Import):
            modul_adlari.extend(a.name for a in dugum.names)
        for m in modul_adlari:
            p = _modul_yolu(m)
            if p is not None:
                adlar |= _import_bayraklari(p)

    # (2) Bu dosyanın KENDİ try/import bayrakları.
    adlar |= _import_bayraklari(yol)

    # (3) Geçişli kapanış: modül düzeyinde onaylı bir addan ya da doğrudan
    #     bir prob çağrısından türetilen adlar da onaylıdır.
    for _ in range(3):
        onceki = len(adlar)
        for dugum in agac.body:
            if not isinstance(dugum, ast.Assign):
                continue
            parca = ast.get_source_segment(kaynak, dugum.value) or ''
            onayli = (any(t in parca for t in _DOGRUDAN_PROB)
                      or any(re.search(rf'\b{re.escape(a)}\b', parca)
                             for a in adlar))
            if not onayli:
                continue
            for hedef in dugum.targets:
                if isinstance(hedef, ast.Name):
                    adlar.add(hedef.id)
        if len(adlar) == onceki:
            break
    return adlar


def _kosul_baglami(agac: ast.Module, kaynak: str) -> dict[int, str]:
    """Her düğüm için onu SARAN koşulların kaynak metni.

    ``pytest.skip('CoolProp yok')`` çıplak bir çağrıdır; kurulum sorusu onu
    saran ``if not COOLPROP_AVAILABLE:`` satırındadır. Çağrının kendi metnine
    bakmak o koşulu kaçırır ve dürüst kapıyı yalancı biçimde suçlar.
    """
    baglam: dict[int, str] = {}

    def gez(dugum, birikim):
        baglam[id(dugum)] = birikim
        for cocuk in ast.iter_child_nodes(dugum):
            ek = birikim
            if isinstance(dugum, (ast.If, ast.While)):
                ek = birikim + '\n' + (
                    ast.get_source_segment(kaynak, dugum.test) or '')
            gez(cocuk, ek)

    gez(agac, '')
    return baglam


@functools.lru_cache(maxsize=1)
def _yalan_gerekceli_kapilar_ham() -> tuple:
    bulgular: dict[str, list[str]] = {}
    for yol in sorted(TEST_DIZINI.rglob('test_*.py')):
        kaynak = yol.read_text(encoding='utf-8')
        if not _YOKLUK_IDDIASI.search(kaynak):
            continue
        try:
            agac = ast.parse(kaynak)
        except SyntaxError:  # pragma: no cover
            continue
        onayli = _onayli_kapi_adlari(yol, kaynak, agac)
        baglam = _kosul_baglami(agac, kaynak)
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Call):
                continue
            if _cagri_adi(dugum) not in ('skip', 'skipif'):
                continue
            oz = ast.get_source_segment(kaynak, dugum) or ''
            if not _YOKLUK_IDDIASI.search(oz):
                continue
            parca = oz + baglam.get(id(dugum), '')
            if any(t in parca for t in _DOGRUDAN_PROB):
                continue
            if any(re.search(rf'\b{re.escape(a)}\b', parca) for a in onayli):
                continue
            gorec = yol.relative_to(DEPO_KOKU).as_posix()
            bulgular.setdefault(gorec, []).append(
                f'{dugum.lineno}: {" ".join(oz.split())[:120]}')
    return tuple((d, tuple(k)) for d, k in sorted(bulgular.items()))


def yalan_gerekceli_kapilar() -> dict[str, list[str]]:
    """Yokluk iddia eden ama kurulum sorusuna dayanMAYAN atlama kapıları.

    Dört bekçi aynı taramayı kullandığı için sonuç önbelleklenir.
    """
    return {d: list(k) for d, k in _yalan_gerekceli_kapilar_ham()}


class TestAtlamaGerekcesiDurust:
    """"Kurulu değil" diyen her atlama, kurulumu GERÇEKTEN sormalı."""

    def test_yokluk_iddiasi_kurulum_sorusuna_dayaniyor(self):
        bulgular = yalan_gerekceli_kapilar()
        beyansiz = {d: k for d, k in bulgular.items()
                    if d not in YALAN_GEREKCE_ISTISNALARI}
        assert not beyansiz, (
            'Şu atlama kapıları bir kütüphanenin YOKLUĞUNU iddia ediyor ama '
            'koşulları kurulum sorusuna dayanmıyor — kütüphane KURULUYKEN '
            'ürün yolu bozulursa da atlanırlar ve kusur sessizleşir:\n'
            + '\n'.join(f'  {d}\n    ' + '\n    '.join(k)
                        for d, k in sorted(beyansiz.items()))
            + '\nÇözüm: kurulum sorusunu tests/bagimlilik_kapisi.py '
              '(kurulu_mu / kapi) ile sorun; ürün yolunun açık olduğunu AYRI '
              'bir bekçi kilitlesin.')

    def test_istisna_listesi_curumuyor(self):
        """Beyan edilen dosya düzelirse istisna SİLİNMEK ZORUNDA."""
        bulgular = yalan_gerekceli_kapilar()
        gereksiz = sorted(set(YALAN_GEREKCE_ISTISNALARI) - set(bulgular))
        assert not gereksiz, (
            f'YALAN_GEREKCE_ISTISNALARI çürüdü: {gereksiz} artık ihlal '
            'içermiyor — beyan silinmeli, yoksa liste gerçekten bozuk olanı '
            'gizlemeye başlar')
        gerekcesiz = [d for d, g in YALAN_GEREKCE_ISTISNALARI.items()
                      if not (g or '').strip()]
        assert not gerekcesiz, f'gerekçesiz istisna: {gerekcesiz}'

    def test_tarayici_bilinen_ihlali_goruyor(self):
        """Tarayıcı sessizce boş dönerse yukarıdaki test BOŞ geçer."""
        bulgular = yalan_gerekceli_kapilar()
        assert 'tests/test_no_fabrication.py' in bulgular, (
            'tarayıcı ölçülmüş ihlali (test_no_fabrication.py, CoolProp '
            'dönüş değerine bakan iki atlama) göremiyor — bozulmuş olabilir')

    def test_durust_kapilar_yanlis_suclanmiyor(self):
        """Gerçek kurulum kapıları ihlal sayılmamalı (yalancı kırmızı)."""
        bulgular = yalan_gerekceli_kapilar()
        durust = ('tests/test_faz6_sivi.py', 'tests/test_tank_step_units.py',
                  'tests/test_step_durustluk_kapisi.py',
                  'tests/test_kinetic_efficiency.py',
                  'tests/test_tank_blowdown.py', 'tests/test_pressurant.py',
                  'tests/cfd/test_performans.py')
        yanlis = [d for d in durust if d in bulgular]
        assert not yanlis, (
            f'tarayıcı dürüst kurulum kapılarını suçladı: {yanlis}')


class TestIstisnaTipiDenetimi:
    """A2 — ``except Exception`` bir KURULUM sorusu DEĞİLDİR (P13B1-01).

    Yukarıdaki tarayıcı bir bayrağı "gerçek kurulum sorusu" saydığında o
    bayrağa dayanan atlamayı DÜRÜST kabul eder. İstisna tipi denetlenmezse
    ``except Exception`` ile kurulan bayrak da onaylanır ve tarayıcı tam da
    kovaladığı kusuru (kütüphane KURULU, ithal yolu KIRIK -> yine de "kurulu
    değil" diye atla) görmez hale gelir. Ölçüldü (ÖH FAZ A / A2, 27 Ağustos
    2026): HEAD ağacında eski tarayıcı 1 dosya buluyordu, istisna-tipi
    denetimiyle 3 — eklenen ikisi ``test_cea_bridge.py`` ve
    ``test_combustion_cea_validation.py``'nin ``except Exception`` kapıları.

    Bu sınıf denetimin KENDİSİNİ kilitler: sentetik kaynaklar üzerinde hem
    yakalaması hem yakalamaMASI gereken vakalar sınanır.
    """

    @staticmethod
    def _bayraklar(tmp_path, kaynak: str) -> set[str]:
        yol = tmp_path / 'ornek_modul.py'
        yol.write_text(textwrap.dedent(kaynak).lstrip(), encoding='utf-8')
        return _import_bayraklari(yol)

    # -- onaylanMAsı gereken (geniş yakalayıcı) -----------------------------
    @pytest.mark.parametrize('yakalayici', [
        'except Exception:',
        'except BaseException:',
        'except:',
        'except OSError:',
        'except (ImportError, OSError):',
        'except (ImportError, Exception):',
    ])
    def test_genis_yakalayici_kurulum_sorusu_SAYILMAZ(self, tmp_path,
                                                      yakalayici):
        adlar = self._bayraklar(tmp_path, f'''
            try:
                import kutuphane
                KUTUPHANE_VAR = True
            {yakalayici}
                KUTUPHANE_VAR = False
        ''')
        assert 'KUTUPHANE_VAR' not in adlar, (
            f'`{yakalayici}` ile kurulan bayrak KURULUM sorusu sayıldı; oysa '
            'kütüphane KURULUYKEN ithal yolu patladığında da False olur. '
            'Bu bayrağa dayanan "kurulu değil" gerekçesi YALAN söyler '
            '(P13B1-01; ölçüm: RuntimeError ve OSError sabotajları birebir '
            'aynı 31 sessiz atlamayı üretti).')

    # -- onaylanMAsı gereken (ithal istisnası) ------------------------------
    @pytest.mark.parametrize('yakalayici', [
        'except ImportError:',
        'except ModuleNotFoundError:',
        'except (ImportError, ModuleNotFoundError):',
    ])
    def test_ithal_istisnasi_kurulum_sorusu_SAYILIR(self, tmp_path,
                                                    yakalayici):
        adlar = self._bayraklar(tmp_path, f'''
            try:
                import kutuphane
                KUTUPHANE_VAR = True
            {yakalayici}
                KUTUPHANE_VAR = False
        ''')
        assert 'KUTUPHANE_VAR' in adlar, (
            f'`{yakalayici}` GERÇEK bir kurulum sorusudur; onaylanmazsa '
            'dürüst kapılar yalancı biçimde suçlanır (yanlış kırmızı)')

    def test_isleyicisiz_try_onaylanmaz(self, tmp_path):
        """``try/finally`` bir soru sormaz; bayrak üretmemeli."""
        adlar = self._bayraklar(tmp_path, '''
            try:
                import kutuphane
                KUTUPHANE_VAR = True
            finally:
                pass
        ''')
        assert 'KUTUPHANE_VAR' not in adlar

    def test_uctan_uca_yalan_gerekce_yakalaniyor(self, tmp_path, monkeypatch):
        """Zincirin tamamı: sentetik dosya -> tarayıcı -> bulgu.

        Yardımcıyı tek başına sınamak yetmez; ``_onayli_kapi_adlari`` ya da
        ``_yalan_gerekceli_kapilar_ham`` bir gün onayı başka yoldan verirse
        birim testi yeşil kalırken kapı yine açılır.
        """
        sahte_tests = tmp_path / 'tests'
        sahte_tests.mkdir()
        (sahte_tests / 'test_sahte_kapi.py').write_text(textwrap.dedent('''
            import pytest

            try:
                from rocketcea.cea_obj import CEA_Obj
                ROCKETCEA_AVAILABLE = True
            except Exception:
                ROCKETCEA_AVAILABLE = False

            needs_cea = pytest.mark.skipif(
                not ROCKETCEA_AVAILABLE,
                reason="RocketCEA kurulu değil; testler atlanıyor.")
        ''').lstrip(), encoding='utf-8')
        # Dürüst karşı örnek: aynı dosya yapısı, ithal istisnasıyla.
        (sahte_tests / 'test_durust_kapi.py').write_text(textwrap.dedent('''
            import pytest

            try:
                import cantera
                CANTERA_VAR = True
            except ImportError:
                CANTERA_VAR = False

            needs_ct = pytest.mark.skipif(
                not CANTERA_VAR, reason="cantera kurulu değil; atlanıyor.")
        ''').lstrip(), encoding='utf-8')

        monkeypatch.setattr(f'{__name__}.DEPO_KOKU', tmp_path)
        monkeypatch.setattr(f'{__name__}.TEST_DIZINI', sahte_tests)
        _yalan_gerekceli_kapilar_ham.cache_clear()
        try:
            bulgular = yalan_gerekceli_kapilar()
        finally:
            _yalan_gerekceli_kapilar_ham.cache_clear()

        assert 'tests/test_sahte_kapi.py' in bulgular, (
            'tarayıcı `except Exception` ile kurulmuş yalan gerekçeyi '
            'GÖRMÜYOR — A2 istisna-tipi denetimi çürümüş olabilir')
        assert 'tests/test_durust_kapi.py' not in bulgular, (
            'tarayıcı `except ImportError` ile kurulmuş DÜRÜST kapıyı '
            'suçladı (yanlış kırmızı)')


class TestBekciBagimliliklariBildirilmis:
    """Bekçinin dayandığı kütüphane bir yerde BEYAN EDİLMİŞ olmalı.

    Faz 5 / H5-4'ün PyYAML dersinin genellemesi: bir bekçi opsiyonel bir
    kütüphaneye kapılıysa ve o kütüphane hiçbir requirements/iş akışı
    dosyasında yoksa, bekçi CI'da hiç koşmaz ve bunu kimse görmez. numba tam
    olarak bu durumdaydı (parti 31 / T2-4).
    """

    #: Ana `pytest` işinde kurulu OLMASI gereken bekçi bağımlılıkları (pip).
    #:
    #: ``rocketcea`` ÖH FAZ A / A3 ile eklendi (defter P13B1-01): kaynaktan
    #: derlenen (gfortran'a bağlı) bu paket sessizce kırılmaya en açık
    #: bağımlılıktı ve kırıldığında 31 bekçi "kurulu değil" YALANIYLA
    #: atlanıyordu.
    ZORUNLU = ZORUNLU_PAKETLER

    def test_requirements_dosyalarinda_bildirilmis(self):
        metin = '\n'.join(
            (DEPO_KOKU / ad).read_text(encoding='utf-8')
            for ad in ('requirements.txt', 'requirements-dev.txt'))
        # Yorum satırları sayılmaz: bir kütüphaneyi ANMAK kurmak değildir.
        satirlar = [s.split('#')[0].strip() for s in metin.splitlines()]
        bildirilen = '\n'.join(s for s in satirlar if s)
        eksik = [k for k in self.ZORUNLU
                 if not re.search(rf'^\s*{re.escape(k)}\b', bildirilen,
                                  re.IGNORECASE | re.MULTILINE)]
        assert not eksik, (
            f'{eksik} hiçbir requirements dosyasında BEYAN EDİLMEMİŞ — bu '
            'kütüphanelere kapılı bekçiler temiz bir CI makinesinde hiç '
            'koşmaz ve atlama sessiz kalır (Faz 5 / H5-4 dersi, parti 31 / '
            'T2-4 tekrarı)')

    @pytest.mark.parametrize('is_akisi,is_adi,bagimlilik',
                             list(_ci_dogrulama_vakalari()))
    def test_ci_kurulumu_dogruluyor(self, is_akisi, is_adi, bagimlilik):
        """Kurulum düşerse iş KIRILSIN — testler sessizce atlanmasın.

        Yorum satırları SAYILMAZ: bir kütüphaneyi ANMAK doğrulamak değildir
        (aynı kural yukarıda requirements taramasında da uygulanıyor).
        Ölçüldü (A3 mutasyonu, 27 Ağustos 2026): doğrulama adımından
        ``rocketcea`` çıkarıldığında, adımın YORUMUNDA geçen 'rocketcea'
        sözcüğü yüzünden bekçi yeşil kalıyordu — yani bekçi kurulumu değil
        metni sınıyordu.
        """
        komutlar = _kod_satirlari(_is_komutlari(is_akisi, is_adi))
        assert bagimlilik in komutlar, (
            f'{is_akisi} / {is_adi}: `{bagimlilik}` kurulumu DOĞRULANMIYOR; '
            'kurulum düşerse iş yeşil kalır ve bekçiler sessizce atlanır '
            '(PyYAML için aynı adım zaten var)')

    def test_zorunlu_kumeler_kesismiyor(self):
        """Bir ad hem pip paketi hem CI aracı olamaz (liste çürümesi kapısı)."""
        assert not set(ZORUNLU_PAKETLER) & set(ZORUNLU_ARACLAR)
        assert set(ZORUNLU_CI) == set(ZORUNLU_PAKETLER) | set(ZORUNLU_ARACLAR)

    def test_borc_listesi_curumuyor(self):
        """Beyan edilen borcun adresi GERÇEK olmalı (uydurma borç yasak)."""
        gecerli = {(w, d) for w, _ in CI_TEST_ISLERI for d in ZORUNLU_CI}
        hayalet = sorted(set(CI_DOGRULAMA_BORCLARI) - gecerli)
        assert not hayalet, (
            f'CI_DOGRULAMA_BORCLARI hayalet adres taşıyor: {hayalet} — '
            'listedeki çift artık üretilmiyor, im hiçbir şeyi imlemiyor')
        gerekcesiz = [c for c, g in CI_DOGRULAMA_BORCLARI.items()
                      if not (g or '').strip()]
        assert not gerekcesiz, f'gerekçesiz borç imi: {gerekcesiz}'


class TestNodeKapisiKilitli:
    """P13B1-04 — node kapısını YORUM değil BEKÇİ kilitlesin.

    ÖH D26 / OH-D25-24: başlıkta da artık SAYI yok. Sınıfın iddiaları
    "yorumdaki sayı doğru mu" değil "sayı elle tutulmuyor ve her koşuda
    kaynaktan üretiliyor mu" biçimindedir.

    Ölçülen (P13/B1 + H1, bu partide yeniden ölçüldü): ``shutil.which('node')``
    ile kapılı **67** test dosyası var; iki iş akışı da node'u kuruyor ve
    doğruluyor, ama ``grep -rln "setup-node" tests/`` **0** sonuç veriyordu —
    yani deponun en pahalı ölçülmüş dersi (2026-08-03: node kurulu değildi,
    67 dosyanın bekçileri CI'da bir kez bile koşmamıştı) mekanik korumasız
    bırakılmıştı. Kural yorumla tutuluyordu; yorum çürür, bekçi çürümez —
    nitekim yorumun kendisi de çürümüştü ("30 test dosyası").
    """

    def test_tarayici_node_kapili_dosyalari_goruyor(self):
        """Kapının kapısı: ölçüm boş dönerse aşağıdaki iddialar BOŞ geçer."""
        dosyalar = node_kapili_test_dosyalari()
        assert len(dosyalar) >= node_kapisi_sayimi.TABAN, (
            f'node kapılı test dosyası ölçümü {len(dosyalar)} döndü; taban '
            f'{node_kapisi_sayimi.TABAN} (P13 ölçümü 67 idi). Bu kadar büyük '
            'bir düşüş ya gerçek bir kaldırma ya da ölçümün (regex) '
            'bozulmasıdır — ikisi de sessiz kalamaz.')

    @pytest.mark.parametrize('is_akisi', [w for w, _ in CI_TEST_ISLERI])
    def test_is_akisi_node_kuruyor(self, is_akisi):
        """`setup-node` adımı düşerse 67 dosyanın bekçisi SESSİZCE atlanır."""
        metin = (ISAKISI_DIZINI / is_akisi).read_text(encoding='utf-8')
        assert 'actions/setup-node' in metin, (
            f'{is_akisi} içinde `actions/setup-node` adımı YOK. '
            f'{len(node_kapili_test_dosyalari())} test dosyası node\'a '
            'kapılıdır ve node yoksa hepsi KIRMIZI VERMEDEN atlanır — '
            '2026-08-03 vakasının birebir tekrarı (defter P13B1-04).')

    @pytest.mark.parametrize('is_akisi', [w for w, _ in CI_TEST_ISLERI])
    def test_is_akisi_node_kurulumunu_dogruluyor(self, is_akisi):
        """Kurulum adımı VAR ama işe yaramazsa da sessizlik doğar."""
        metin = (ISAKISI_DIZINI / is_akisi).read_text(encoding='utf-8')
        assert _NODE_KAPISI.search(metin), (
            f'{is_akisi} node kurulumunu DOĞRULAMIYOR '
            "(`shutil.which('node')` denetimi yok): setup-node bir gün "
            'sessizce başarısız olursa iş yeşil kalır.')

    @pytest.mark.parametrize('is_akisi', [w for w, _ in CI_TEST_ISLERI])
    def test_yorumda_ELLE_yazilmis_dosya_sayisi_YOK(self, is_akisi):
        """ÖH D26 / OH-D25-24 — sayı YORUMDA tutulamaz.

        Bu bekçinin eski hâli "yorumdaki sayı ölçülene EŞİT olmalı" diyordu
        ve doğru bir iddiaydı; ama onarımı her seferinde ELLE yapılıyordu ve
        elle yapılan onarım bir sonraki birleşmede yeniden çürüyordu:

            88 (D21) -> 92 (fix-20) -> 94 (fix-23) -> 97 (D26 tabanı)

        Dördüncü çürümede kusurun sayının yanlışlığı DEĞİL sayının elle
        tutulması olduğu hükme bağlandı: bir dosyayı ``node`` kapısına alan
        kulvar, ilgisiz bir iş akışı yorumunu aynı commit'te güncellemek
        zorunda kalıyordu. Artık iş akışlarında güncellenecek sayı YOKTUR;
        sayıyı ``tools/node_kapisi_sayimi.py`` üretir ve iş akışı onu KOŞAR
        (aşağıdaki bekçi). Bir sayı geri yazılırsa bu iddia KIRMIZI verir.
        """
        metin = (ISAKISI_DIZINI / is_akisi).read_text(encoding='utf-8')
        iddialar = sorted({int(s) for s in _YORUM_DOSYA_SAYISI.findall(metin)})
        assert not iddialar, (
            f'{is_akisi} yorumunda ELLE yazılmış dosya sayısı var: {iddialar}. '
            f'Bu sayı üç dalgada üst üste çürüdü; tek kaynak {_SAYIM_ARACI} '
            'ölçümüdür. Sayıyı güncellemeyin — yorumdan KALDIRIN, iş akışı '
            'zaten sayım adımını koşuyor.')

    @pytest.mark.parametrize('is_akisi', [w for w, _ in CI_TEST_ISLERI])
    def test_is_akisi_sayimi_KAYNAKTAN_turetiyor(self, is_akisi):
        """Sayıyı kaldırmak yetmez — iş akışı onu ÜRETMELİ.

        Yalnız "yorumda sayı olmasın" deseydik, sayıyı silmek bekçiyi
        susturmanın en kolay yolu olurdu ve ölçüm CI'dan tamamen düşerdi.
        Bu yüzden iki iddia birlikte durur: sayı elle YAZILMAZ ama her koşuda
        kaynaktan TÜRETİLİR (ve taban altına düşerse iş kırılır).
        """
        metin = (ISAKISI_DIZINI / is_akisi).read_text(encoding='utf-8')
        komutlar = _kod_satirlari(metin)
        assert _SAYIM_ARACI in komutlar, (
            f'{is_akisi} `{_SAYIM_ARACI}` sayım adımını KOŞMUYOR (yorumda '
            'anmak koşmak değildir). Sayı yorumdan kaldırıldığına göre '
            'ölçümün CI\'da gerçekten üretildiği tek kanıt bu adımdır.')

    def test_sayim_araci_ile_bekci_AYNI_kumeyi_olcuyor(self):
        """Tek kaynak gerçekten tek mi? Araç ile bekçi ayrışamaz.

        Ayrışırlarsa iş akışı bir sayıyı, bekçi başka bir sayıyı savunur ve
        ikisi de kendince yeşil kalır — bu dosyanın kovaladığı kusur sınıfının
        ta kendisi.
        """
        assert (node_kapili_test_dosyalari()
                == node_kapisi_sayimi.node_kapili_test_dosyalari(DEPO_KOKU))
        assert node_kapisi_sayimi.TABAN >= 50, (
            'taban 50\'nin altına çekilmiş — ölçüm çökse bile sessiz kalır')

    def test_sayim_araci_taban_altinda_KIRMIZI_veriyor(self, tmp_path):
        """Aracın fail-closed davranışı ölçülür (beyan değil, koşum).

        Sentetik bir ağaçta node kapılı dosya YOKTUR: araç sıfır sayıp
        tabanın altında kaldığı için sıfırdan farklı çıkış kodu vermeli.
        Vermezse 2026-08-03 vakası (kapı sökülü, iş yeşil) geri döner.
        """
        (tmp_path / 'tests').mkdir()
        (tmp_path / 'tests' / 'test_ornek.py').write_text(
            'def test_bir():\n    assert True\n', encoding='utf-8')
        assert node_kapisi_sayimi.main(['--kok', str(tmp_path)]) == 1
        assert node_kapisi_sayimi.main([]) == 0, (
            'gerçek depoda sayım tabanın altında — ön yüz kapısı sökülmüş '
            'olabilir')


class TestBagimlilikKapisiDavranisi:
    """``tests/bagimlilik_kapisi.kapi`` üç durumlu sözleşmesini tutuyor mu?

    Yukarıdaki tarayıcı YAPIYI denetler; bu sınıf DAVRANIŞI. İkisi birbirinin
    yerine geçmez: yapı doğru olup davranış bozulabilir (kapı her durumda
    atlarsa tarayıcı bunu göremez).
    """

    @staticmethod
    def _sonuc(modul_adi, urun_yolu_acik, aciklama):
        """Kapıyı çağırır ve SONUCUNU döndürür.

        pytest'in ``Skipped``/``Failed`` sınıfları ``BaseException``
        türevidir; ``pytest.raises(Exception)`` onları YAKALAMAZ (yakaladığını
        sanan bir bekçi kendi kendini atlar — ölçüldü).
        """
        try:
            kapi(modul_adi, urun_yolu_acik, aciklama)
        except BaseException as exc:          # noqa: BLE001 - kasıtlı
            return type(exc).__name__, str(exc)
        return None, ''

    def test_bagimlilik_yoksa_ATLAR(self):
        tur, _ = self._sonuc('hrma_kesinlikle_olmayan_modul_31', False, 'teşhis')
        assert tur == 'Skipped', (
            f'bağımlılık yokken atlaması gerekirdi, sonuç: {tur}')

    def test_bagimlilik_VARKEN_urun_kusuru_ATLANMAZ(self):
        """Kapının varlık sebebi: ``pytest`` kesin kurulu, yol kapalı."""
        tur, metin = self._sonuc('pytest', False, 'ürün yolu kapalı (ölçüm)')
        assert tur == 'Failed', (
            'bağımlılık KURULUYKEN ürün yolu kapalıysa kapı KIRMIZI vermeli; '
            f'sonuç: {tur} — eski sessiz atlama geri gelmiş olabilir')
        assert 'ürün yolu kapalı' in metin

    def test_yol_acikken_hicbir_sey_yapmaz(self):
        assert self._sonuc('pytest', True, 'çağrılmamalı') == (None, '')

    def test_kurulu_mu_gercegi_soyluyor(self):
        assert kurulu_mu('pytest') is True
        assert kurulu_mu('hrma_kesinlikle_olmayan_modul_31') is False
