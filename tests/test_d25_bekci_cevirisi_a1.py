# -*- coding: utf-8 -*-
"""ÖH Dalga-25 · kulvar bekci-cevirisi · aşama 1/1 — bekçilerin bekçisi.

Bu dosya ürün davranışını değil BEKÇİLERİN ve YAYIMLANAN BELGENİN kendisini
savunur: geri çekilmiş bir hükmün depoda yayımlı kalmamasını, bir envanterin
saymadığını sayıp saydığını saymamasını, bir iddia kredisinin testin KENDİ
konusundan gelmesini.

Kapsanan kalemler
-----------------
P10B4-07   (Fable-D19 ŞART) yayımlı bağlama haritası HEAD aracıyla yeniden
           üretilir; geri çekilen kapı cümlesi ("izlenen tek sayı
           sınıflandırılmamış, hedefi sıfırdır") yayımlı sayfada duramaz,
           erime ölçümü üç sayfa için de yayımlanır
OH-D24-04  "delegesiz iddiasız test nüfusu 56" başlığı ÖLÇÜLDÜ: 0'ı gerçekten
           iddiasız, 4'ü pytest'in hiç toplamadığı fonksiyon, 1'i iddia
           kredisini KURULUM yardımcısından alan gerçek delik. Envanter
           düzeltildi, delik onarıldı, daha keskin kapı (kredi kaynağı)
           kuruldu

Her iddia, savunduğu kusuru gördüğü TERS MUTASYONLA doğrulanmıştır; kanıt
``docs/scofield/raw/OH/D25/bekci-cevirisi/a1/mutasyon.json``.
"""

import ast
import pathlib
import re

import pytest

# D22'nin ölçüm gövdesi TEK KAYNAKTIR: burada yeniden yazılmaz, içe alınır.
from tests.test_d22_bekci_cevirisi_a1 import (   # noqa: E402
    _iddia_tasiyor, _modul_fonksiyonlari, _pytest_topluyor)

KOK = pathlib.Path(__file__).resolve().parents[1]
TESTS = KOK / 'tests'
DEV = KOK / 'docs' / 'dev'
ARAC = KOK / 'tools' / 'wiring_map.py'

def _arac_sayfalari():
    """Yayımlanan detay sayfaları — aracın KENDİ ``PAGES`` sözlüğünden.

    ÖH D26 / fix-25b: burada eskiden ``SAYFALAR = ('hybrid', 'liquid',
    'solid')`` yazıyordu. Bu, motor türü üçlüsünün ADLANDIRILMIŞ dördüncü
    kopyasıydı ve tek-kaynak bekçisini kırıyordu
    (``tests/test_sabit_tek_kaynak.py::test_motor_types_tek_tanim_noktasi``
    — "YENİ yerel tanım: tests/test_d25_bekci_cevirisi_a1.py, SAYFALAR").
    Liste artık aracın kaynağından AST ile okunur: araç bir gün dördüncü
    sayfa yayımlarsa bu bekçi onunla birlikte büyür, elle güncelleme
    gerekmez. Araç modülü İÇE ALINMAZ (yan etkisiz okuma).
    """
    agac = ast.parse(ARAC.read_text(encoding='utf-8'))
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Assign):
            continue
        if not any(isinstance(h, ast.Name) and h.id == 'PAGES'
                   for h in dugum.targets):
            continue
        if not isinstance(dugum.value, ast.Dict):
            continue
        adlar = tuple(a.value for a in dugum.value.keys
                      if isinstance(a, ast.Constant)
                      and isinstance(a.value, str))
        assert adlar, 'tools/wiring_map.py::PAGES anahtarları okunamadı'
        return adlar
    raise AssertionError(
        'tools/wiring_map.py içinde PAGES sözlüğü bulunamadı — araç mı '
        'yeniden yapılandırıldı?')


SAYFALAR = _arac_sayfalari()

#: Aracın GERİ ÇEKTİĞİ kapı cümlesi. D19'a kadar giriş sayfası bu cümleyle
#: "sınıflandırılmamış sabit = 0"ı bir KAPI ÖLÇÜTÜ diye öneriyordu; ölçüldü
#: ki o sayı ölçüm gücüne bağlıdır (katıda 215/215 = %100 eriyor), yani kapı
#: kurulsaydı kapatmanın yolu kusuru düzeltmek değil sarsımı zayıflatmak
#: olurdu. Araç hükmü geri çekti; yayımlı sayfa onu taşıyamaz.
GERI_CEKILEN_KAPI = 'izlenen tek sayı sınıflandırılmamış, hedefi sıfırdır'

#: Aracın bugün üretebildiği TEK "hedefi sıfırdır" bağlamı (tools/wiring_map
#: .py::build_index). Yayımlı sayfada bu ifade geçiyorsa YALNIZ bu bağlamda
#: geçebilir.
KAZANILMIS_KAPI = 'hedefi sıfırdır — bu hüküm ölçümle kazanıldı'


def _giris() -> str:
    yol = DEV / 'wiring_map.html'
    if not yol.is_file():                        # pragma: no cover
        pytest.fail('yayımlı giriş sayfası yok: %s' % yol)
    return yol.read_text(encoding='utf-8')


class TestP10B407YayimliHaritaAracıylaAyniHukmuTasir:
    """Fable-D19 ŞART — depo neyi GÖSTERİYORSA aracın hükmü odur."""

    def test_geri_cekilen_kapi_cumlesi_yayimli_sayfada_yok(self):
        """Geri çekilmiş hüküm yayımda duramaz (ŞART'ın çekirdeği).

        ÖLÇÜLEN taban (cdf2106): docs/dev/wiring_map.html 1 Eyl'de (97ca57c,
        D19 ÖNCESİ) üretilmişti ve satır 118'de bu cümleyi taşıyordu; araç
        D19'da hükmü geri çekmişti ama depo bayat sayfayı gösteriyordu.
        """
        metin = _giris()
        assert GERI_CEKILEN_KAPI not in metin, (
            'yayımlı giriş sayfası aracın GERİ ÇEKTİĞİ kapı ölçütünü hâlâ '
            'öneriyor; `python3 tools/wiring_map.py` ile yeniden üretilmeli')

    def test_hedefi_sifirdir_yalniz_olcumle_kazanilmis_baglamda(self):
        """"hedefi sıfırdır" ya hiç geçmez ya ölçümle kazanıldığı yerde."""
        metin = _giris()
        gerekcesiz = []
        for m in re.finditer('hedefi sıfırdır', metin):
            if KAZANILMIS_KAPI not in metin[m.start():m.start() + 200]:
                gerekcesiz.append(m.start())
        assert not gerekcesiz, (
            '"hedefi sıfırdır" %d kez GEREKÇESİZ geçiyor (ölçümle kazanıldığı '
            'söylenmeden); konumlar: %s' % (len(gerekcesiz), gerekcesiz[:5]))

    def test_erime_olcumu_uc_sayfa_icin_de_yayimlanmis(self):
        """Giriş sayfası: 'Erime ÖLÇÜLDÜ' cümlesi + üç kartta rozet."""
        metin = _giris()
        assert 'Erime ÖLÇÜLDÜ' in metin, (
            'giriş cümlesinde erime ölçümü yok; harita --erime-yok ile mi '
            'üretildi? (ölçülmemişken HÜKÜM yayımlanmaz, ama ŞART ölçülmüş '
            'haritayı istiyor)')
        rozetler = re.findall(r'güçlü sarsımda (\d+)/(\d+) eriyor', metin)
        assert len(rozetler) == len(SAYFALAR), (
            'giriş kartlarında %d erime rozeti var, %d bekleniyor: %s'
            % (len(rozetler), len(SAYFALAR), rozetler))
        assert all(int(t) > 0 for _e, t in rozetler), (
            'rozet toplamı sıfır — ölçüm çöktü: %s' % (rozetler,))

    @pytest.mark.parametrize('sayfa', SAYFALAR)
    def test_detay_meta_satirinda_erime_var(self, sayfa):
        """Üç detay sayfasının meta satırı erimeyi ADIYLA taşır."""
        yol = DEV / ('wiring_map_%s.html' % sayfa)
        assert yol.is_file(), 'yayımlı detay sayfası yok: %s' % yol
        metin = yol.read_text(encoding='utf-8')
        m = re.search(r'güçlü sarsımda (\d+)/(\d+) eriyor', metin)
        assert m, ('%s meta satırında "güçlü sarsımda N/M eriyor" yok; sayfa '
                   'erime ölçümü olmadan üretilmiş' % sayfa)
        assert int(m.group(2)) > 0, '%s: sabit yaprak toplamı 0' % sayfa
        assert 'erime ÖLÇÜLMEDİ' not in metin, (
            '%s sayfası adlı reti taşıyor: erime ölçülememiş' % sayfa)

    def test_arac_geri_cekilen_kapiyi_YAYIMLAYAMAZ(self):
        """Yayım ⟷ araç AYRIŞMA bekçisi (ŞART'ın önerdiği küçük bekçi).

        Geri çekilen cümle aracın kaynağında YALNIZ belgede (docstring /
        yorum) geçebilir; HTML'e giden bir dizge sabitinde geçemez. Ayrım
        AST ile yapılır: belge dizgeleri (modül / sınıf / fonksiyon
        gövdesinin ilk deyimi) elenir, kalan her dizge sabiti aracın
        yayımlayabileceği metindir.
        """
        agac = ast.parse(ARAC.read_text(encoding='utf-8'))
        belge = set()
        for d in ast.walk(agac):
            if isinstance(d, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)) and d.body:
                ilk = d.body[0]
                if (isinstance(ilk, ast.Expr)
                        and isinstance(ilk.value, ast.Constant)
                        and isinstance(ilk.value.value, str)):
                    belge.add(id(ilk.value))
        yayimlanabilir = [n.value for n in ast.walk(agac)
                          if isinstance(n, ast.Constant)
                          and isinstance(n.value, str)
                          and id(n) not in belge]
        sizanlar = [t for t in yayimlanabilir if GERI_CEKILEN_KAPI in t]
        assert not sizanlar, (
            'araç geri çekilen kapı cümlesini yayımlanabilir bir dizgede '
            'taşıyor: %r' % sizanlar[:1])
        assert any(KAZANILMIS_KAPI.split(' — ')[1] in t
                   for t in yayimlanabilir), (
            'aracın kazanılmış-kapı metni değişmiş; bu bekçinin çapası '
            'güncellenmeli (tools/wiring_map.py::build_index)')
        assert any('Erime ÖLÇÜLDÜ' in t for t in yayimlanabilir), (
            'araç artık "Erime ÖLÇÜLDÜ" cümlesini üretmiyor ama yayımlı '
            'sayfa taşıyor — sayfa araçtan ESKİ')


# ===========================================================================
# OH-D24-04 — "delegesiz iddiasız nüfus" başlığının ÖLÇÜMÜ
# ===========================================================================

#: pytest'in TOPLAMADIĞI, envanterin "iddiasız test" saydığı fonksiyonlar.
#: Kanıt: docs/scofield/raw/OH/D25/bekci-cevirisi/a1/collect_only_solid.txt
#: (`pytest --collect-only -q tests/test_solid_rocket_validation.py` o
#: dosyada 6 test topluyor; aşağıdaki dördü aralarında YOK).
TOPLANMAYAN_ORNEKLER = (
    ('tests/test_solid_rocket_validation.py', 'test_apcp_reference_validation'),
    ('tests/test_solid_rocket_validation.py', 'test_saint_robert_law'),
)


def _ozneler(dugum):
    """Testin KENDİ ürettiği adlar: atama / for / with hedefleri +
    parametreler (``self``/``cls`` hariç — onlar konu değil kurulumdur)."""
    adlar = set()
    for a in dugum.args.args + dugum.args.kwonlyargs:
        if a.arg not in ('self', 'cls'):
            adlar.add(a.arg)
    for x in ast.walk(dugum):
        if isinstance(x, ast.Assign):
            for h in x.targets:
                adlar |= {n.id for n in ast.walk(h) if isinstance(n, ast.Name)}
        elif isinstance(x, (ast.For, ast.AsyncFor)):
            adlar |= {n.id for n in ast.walk(x.target)
                      if isinstance(n, ast.Name)}
        elif isinstance(x, (ast.With, ast.AsyncWith)):
            for w in x.items:
                if w.optional_vars is not None:
                    adlar |= {n.id for n in ast.walk(w.optional_vars)
                              if isinstance(n, ast.Name)}
        elif isinstance(x, ast.NamedExpr):
            adlar |= {n.id for n in ast.walk(x.target)
                      if isinstance(n, ast.Name)}
    return adlar


def _konu_tasiyor(cagri, ozneler):
    """Çağrı testin ürettiği bir değeri alıyor mu."""
    for arg in list(cagri.args) + [k.value for k in cagri.keywords]:
        for n in ast.walk(arg):
            if isinstance(n, ast.Name) and n.id in ozneler:
                return True
            if isinstance(n, ast.Call):          # yerinde türetilmiş değer
                return True
    return False


def _kurulum_kredili_testler():
    """Gövdesi iddiasız VE krediyi veren çağrıların HİÇBİRİ testin konusunu
    almayan testler — yani iddia testin konusuna değil kuruluma ait.

    ÖLÇÜLEN örnek (D25 tabanı): ``test_etkin_oksitleyicilerin_HEPSI_cozulur``
    kredisini ``_select_secenekleri`` içindeki "select bulunamadı"
    iddiasından alıyordu; testin kendi konusu (çözülen yoğunluk) hiç
    sınanmıyordu ve boş listede vakumlu yeşil kalıyordu.
    """
    bulunan = []
    for yol in sorted(TESTS.rglob('test_*.py')):
        try:
            agac = ast.parse(yol.read_text(encoding='utf-8'))
        except SyntaxError:                      # pragma: no cover
            continue
        bagil = str(yol.relative_to(KOK))
        tablo = _modul_fonksiyonlari(agac)
        for d in ast.walk(agac):
            if not (isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and d.name.startswith('test_')):
                continue
            if not _pytest_topluyor(agac, d):
                continue
            if _iddia_tasiyor(d, {}):            # gövdede DOĞRUDAN iddia
                continue
            ozneler = _ozneler(d)
            konulu = False
            for x in ast.walk(d):
                if not isinstance(x, ast.Call):
                    continue
                f = x.func
                ad = (f.attr if isinstance(f, ast.Attribute)
                      else getattr(f, 'id', ''))
                if not ad or ad not in tablo:
                    continue
                if not _iddia_tasiyor(tablo[ad], tablo):
                    continue
                if _konu_tasiyor(x, ozneler):
                    konulu = True
                    break
            if not konulu:
                bulunan.append('%s::%s' % (bagil, d.name))
    return sorted(bulunan)


#: ÖLÇÜLEN ve GEREKÇELİ izin listesi (D25, taban cdf2106 + bu aşamanın
#: onarımı). Her kalem elle denetlendi; ikisi de yanlış pozitif DEĞİL,
#: "konusu bir DEĞER değil DİSKTEKİ AĞAÇ ya da KARDEŞ İDDİA" biçimidir.
KURULUM_KREDISI_IZINLERI = {
    'tests/test_paket_cikti_manifesti.py::test_derlenmis_app_manifesti':
        'konu bir değer değil DİSKTEKİ derleme ağacıdır; _agac_manifesti '
        'sabit yolu alıp ağacı manifestle karşılaştırır, ağaç yoksa test '
        'pytest.skip ile ADIYLA atlanır (fail-closed)',
    'tests/test_paket_cikti_manifesti.py::test_windows_payload_manifesti':
        'konu bir değer değil DİSKTEKİ Windows payload ağacıdır; aynı '
        'gerekçe (sabit yol + manifest karşılaştırması + adlı atlama)',
    'tests/test_scofield_arayuz.py::'
    'test_iki_manifold_capi_celisiyorsa_ekranda_tek_deger_var':
        'iddia KARDEŞ TESTE devredilmiştir (arayüzün kaba kural değerini '
        'göstermediğini o sınar); bu test yalnız çelişkinin sürdüğünü '
        'ölçüp kardeşi çağırır, çelişki bitince adlı atlama yapar',
}


class TestOHD2404KrediKaynagi:
    """Delegasyon kredisi testin KONUSUNDAN gelmeli, kurulumdan değil."""

    def test_kurulum_kredili_test_kumesi_buyumedi(self):
        olculen = set(_kurulum_kredili_testler())
        izinli = set(KURULUM_KREDISI_IZINLERI)
        yeni = olculen - izinli
        assert not yeni, (
            'iddia kredisini KURULUM yardımcısından alan yeni test(ler): %s '
            '— testin kendi konusu sınanmıyor, boş/None sonuçta yeşil kalır'
            % sorted(yeni))

    def test_izin_listesinde_olu_satir_yok(self):
        """ÖK-22: onarılan kalem izin listesinde kalamaz."""
        olculen = set(_kurulum_kredili_testler())
        olu = set(KURULUM_KREDISI_IZINLERI) - olculen
        assert not olu, (
            'izin listesi bayat: %s artık kurulum kredisi almıyor, satır '
            'silinmeli' % sorted(olu))

    def test_izin_gerekceleri_gercek(self):
        for ad, gerekce in KURULUM_KREDISI_IZINLERI.items():
            assert len(gerekce) >= 40, '%s: gerekçe çok kısa' % ad

    def test_envanter_pytestin_toplamadigini_saymaz(self):
        """OH-D24-04'ün ölçülen yanlış pozitifi geri gelemez."""
        for bagil, ad in TOPLANMAYAN_ORNEKLER:
            agac = ast.parse((KOK / bagil).read_text(encoding='utf-8'))
            hedefler = [d for d in ast.walk(agac)
                        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and d.name == ad]
            assert hedefler, '%s::%s kayboldu' % (bagil, ad)
            for d in hedefler:
                assert not _pytest_topluyor(agac, d), (
                    '%s::%s pytest tarafından TOPLANIYOR sayılıyor; envanter '
                    'yine hiç koşulmayan fonksiyonu "iddiasız test" '
                    'sayacak' % (bagil, ad))

    def test_toplama_suzgeci_fail_closed(self):
        """Şüphede TOPLANIYOR: modül düzeyi, Test* sınıfı, TestCase türevi."""
        agac = ast.parse(
            'def test_a():\n    pass\n'
            'class TestX:\n    def test_b(self):\n        pass\n'
            'class Sey(unittest.TestCase):\n'
            '    def test_c(self):\n        pass\n'
            'class Sey2(bilinmeyen()):\n'
            '    def test_d(self):\n        pass\n'
            'class Duz:\n    def test_e(self):\n        pass\n')
        durum = {}
        for d in ast.walk(agac):
            if isinstance(d, ast.FunctionDef) and d.name.startswith('test_'):
                durum[d.name] = _pytest_topluyor(agac, d)
        assert durum == {'test_a': True, 'test_b': True, 'test_c': True,
                         'test_d': True, 'test_e': False}, durum


class TestOHD2404OnarilanBekciKonusunuSiniyor:
    """Onarılan tek gerçek delik geri alınamaz."""

    def test_oksitleyici_bekcisi_dogrudan_iddia_tasiyor(self):
        yol = KOK / 'tests' / 'test_d20_ihracat_a1.py'
        agac = ast.parse(yol.read_text(encoding='utf-8'))
        hedef = [d for d in ast.walk(agac)
                 if isinstance(d, ast.FunctionDef)
                 and d.name == 'test_etkin_oksitleyicilerin_HEPSI_cozulur']
        assert len(hedef) == 1, hedef
        d = hedef[0]
        assert _iddia_tasiyor(d, {}), (
            'onarım geri alınmış: gövdede doğrudan iddia yok')
        kaynak = ast.unparse(d)
        for alan in ('density', 'source', 'state_applied', 'state_reason'):
            assert alan in kaynak, (
                'sözleşmenin %r ayağı sınanmıyor' % alan)
        # Vakumlu geçiş kapısı: boş listede test yeşil kalamaz.
        assert re.search(r'assert etkin\b', kaynak), (
            'boş seçenek listesinde test vakumlu yeşil kalır')
