# -*- coding: utf-8 -*-
"""ÖH FAZ B-1 / adım #5 — oksitleyici yoğunluğu KAYNAK MATRİSİ bekçisi.

ÖLÇÜLEN KUSUR (P14 mutasyon partisi + savcı §3.1-5)
---------------------------------------------------
1220 kg/m³ (azot protoksidin **kaynama noktası**, 184,67 K yoğunluğu) depoda
altı ayrı yerde canlı ve birbirini gölgeliyor. Hangi sitenin nerede kazandığı
mutasyonla ayrıştırıldı (`raw/P14/H2-probe-rho5.py`, `-rho6.py`):

    P14M2-09  app.py:1510 uç varsayılanı  -> gövdede alan YOKKEN, tüm tipler
    P14M2-08  LOCAL_DENSITY_FALLBACK      -> gövde null + tip n2o
    P14M2-06  external_data_fetcher yedeği-> gövde null + tip n2o DEĞİLKEN
    P14M2-07  database_integrations yedeği-> ölü kod (ürün yolundan erişilemez)
    P14S1-01  simple.html:247 / uzaytek.html:930 -> tarayıcı koşulsuz 1220 yolluyor
    P14H1-Ç2  app.get_oxidizer_density    -> aynı sayıyı BAŞKA bir eğriyle çözüyor

Bunun üstüne H2'nin §5(f) bulgusu geliyor: enjektör, **azot protoksidin
yoğunluğunu LOX ve H2O2 için de kullanıyor** ve bunu ``'NIST WebBook'``
künyesiyle sunuyor. Mekanizma söküldü: ``fetch_nist_oxidizer_properties``
yalnız ``oxidizer_type == 'n2o'`` dalında gerçek bir veri kaynağı
(CoolProp/Span-Wagner) deniyor; diğer her tip doğrudan
``_get_backup_oxidizer_properties``a düşüyor, o da **tipi hiç okumadan**
``backup_data['n2o_properties']`` tablosunu döndürüyor. Kurucu ise
``is_valid`` doğru olduğu anda ``DENSITY_SOURCE_NIST`` etiketini basıyor —
yani künye bir VERİ KAYNAĞI beyanı değil, "doğrulamadan geçti" bayrağı; ama
kullanıcıya kaynak adı olarak gösteriliyor.

DOĞRU DESEN DEPODA ZATEN YAZILI (bu yüzden onarım "icat" değil "kopya")
-----------------------------------------------------------------------
``HybridRocketEngine._get_oxidizer_density`` aynı kusuru **denetim bulgusu
#550** olarak kapatmış: N2O için doyma zinciri, diğer her oksitleyici için
merkezî ``PropellantDatabase``. Ölçüldü — o kanal bugün kanonik değerleri
birebir veriyor (n2o 753,6 / lox 1141 / h2o2 1438,1 / n2o4 1443; h2o2 çapası
28 Ağu'da 1450'den düzeltildi — 1450 %100 safın değeriydi). Kusur, aynı
onarımın **ikize (enjektör kanalına) uygulanmamış** olmasıdır; H2 §5(b)'nin
"İKİZ ÜRETİCİ" deseni.

BU DOSYANIN ÇAPASI: DIŞARIDAN SAYI GETİRMEZ
-------------------------------------------
Referans yoğunluklar literatürden yeniden YAZILMAZ; deponun kendi merkezî
tablosundan (``PropellantDatabase``) OKUNUR. Böylece her iddia bir iç
tutarlılık iddiasıdır: "aynı oksitleyicinin yoğunluğu, aynı depoda iki farklı
sayı olamaz". Uç varsayılanı da elle yazılmaz, ``app.py``den AST ile çekilir.

ONARIM KISITI (savcı §3.1-5, ZORUNLU)
-------------------------------------
Uç/çözücü onarımı **P14S1-01 şablon düzeltmesiyle AYNI commit'te kapanmalı**:
``simple.html:247`` ve ``uzaytek.html:930`` sıvı fazda koşulsuz 1220
gönderdiği sürece, uç varsayılanı düzeltilse bile kullanıcıya giden sayı
değişmez — uç onarımı şablonun altında ÖRTÜLÜR. (``advanced.html`` bu
düzeltmeyi v2.6.26'da aldı: alan boşsa ``null`` gider. İki kardeş şablon
almadı.) Şablon onarımı Z1 yoğunluk dalgasının işidir; burada yalnız BEKÇİSİ
kurulur.

DEFTER KURALI
-------------
Bugün kırmızı olan her iddia ``xfail(strict=True)`` ile kayıtlıdır: onarım
inince XPASS olur, kırmızıya döner ve işaretin SİLİNMESİNİ zorlar. Yani bu
dosya onarımı bekleyen borcu sayar, gizlemez.

Z1 ONARIMI İNDİ (27 Ağustos 2026)
---------------------------------
Çekirdek + şablon onarımı (Z1-A/Z1-B ajanları) yukarıdaki kusurların
gövdesini kapattı: 1220'nin canlı siteleri söküldü, tek doğruluk kaynağı
``oxidizer_reference_density`` (N2OSaturation) kuruldu, künyeler gerçek
kaynağı söylüyor, ``validate_data`` iki kademeli fiziksel zarfa geçti,
iki kardeş şablon koşulsuz 1220 göndermiyor. XPASS'e dönen imler bu
commit'te silindi. AÇIK KALANLAR: (a) n2o hücreleri — merkezî tablonun
kanonu 745,0 (298,15 K), tek kaynak 293,15 K'de 785,10 veriyor; kanonun
sıcaklık etiketi kararı Berke'de, imler o kararla kalkacak; (b) generic
hücreler — ürün artık fail-closed istisna atıyor, bekçi de bunu kilitliyor.
"""

import ast
import io
import os
import re
import sys
import warnings
from contextlib import redirect_stdout

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.data.external_data_fetcher import data_fetcher        # noqa: E402
from hrma.data.propellant_database import PropellantDatabase    # noqa: E402
from hrma.utils.injector_design import (                        # noqa: E402
    DENSITY_SOURCE_NIST,
    DENSITY_SOURCE_USER,
    LOCAL_DENSITY_FALLBACK,
    InjectorDesign,
)

APP_PY = os.path.join(REPO_ROOT, 'hrma', 'app.py')
ADVANCED_HTML = os.path.join(REPO_ROOT, 'hrma', 'templates', 'advanced.html')

#: Kabul bandı (göreli). Gerekçesi ölçülü: onarılmış ikizin N2O dalı doyma
#: EOS'undan 753,6 kg/m³ veriyor, merkezî tablo 745,0 yazıyor — aradaki %1,15
#: sıcaklık/EOS farkıdır ve gerçektir. Band bunu geçirir; ölçülen kusurların
#: en küçüğü (%+7, LOX) bandın 3,5 katıdır. Bandı GENİŞLETME: kusuru
#: geçirmeye başladığı an bekçi yalan söyler.
BANT = 0.02

#: Gövde şekilleri — hangi sitenin kazandığını AYIRAN eksen (H2 ayrıştırması).
GOVDE_ALAN_YOK = 'alan-yok(uç-varsayılanı)'
GOVDE_ALAN_NULL = 'alan-null(yedek-zinciri)'
GOVDE_KULLANICI = 'kullanıcı-verdi'
GOVDE_SEKILLERI = (GOVDE_ALAN_YOK, GOVDE_ALAN_NULL, GOVDE_KULLANICI)

#: Kullanıcı gövdesinde gönderilen deneme değeri — hiçbir yedeğe eşit
#: OLMAMALI, yoksa "kullanıcı kazandı mı" sorusu ölçülemez.
KULLANICI_YOGUNLUGU = 903.0

OKSITLEYICILER = ('n2o', 'lox', 'h2o2', 'n2o4', 'generic')

_DB = PropellantDatabase()


def _kanonik_yogunluk(tip):
    """Deponun KENDİ merkezî tablosundaki işletme yoğunluğu [kg/m³].

    ``None`` dönerse o oksitleyici için depoda savunulabilir tek bir sayı
    yoktur (``generic``) — o durumda ürünün yapması gereken sayı UYDURMAK
    değil, kaynağını beyan etmektir.
    """
    kayit = _DB.get_propellant_properties(tip)
    if not kayit:
        return None
    yog = kayit.get('density')
    return float(yog) if yog is not None else None


def _app_uc_varsayilani():
    """``app.py``deki ``InjectorDesign(oxidizer_density=...)`` varsayılanı.

    Sayı bu dosyaya elle yazılmaz: ``data.get('oxidizer_density', <X>)``
    çağrısının ikinci argümanı AST ile okunur. Varsayılan kaldırılırsa
    (doğru onarım) ``None`` döner.
    """
    with open(APP_PY, encoding='utf-8') as f:
        agac = ast.parse(f.read(), filename=APP_PY)
    for dugum in ast.walk(agac):
        if not (isinstance(dugum, ast.Call)
                and isinstance(dugum.func, ast.Name)
                and dugum.func.id == 'InjectorDesign'):
            continue
        for anahtar in dugum.keywords:
            if anahtar.arg != 'oxidizer_density':
                continue
            deger = anahtar.value
            if (isinstance(deger, ast.Call)
                    and isinstance(deger.func, ast.Attribute)
                    and deger.func.attr == 'get'
                    and len(deger.args) == 2
                    and isinstance(deger.args[1], ast.Constant)):
                return deger.args[1].value
            return None
    raise AssertionError(
        'app.py içinde InjectorDesign(...) çağrısı bulunamadı — bu bekçinin '
        'çapası kaymış, önce çağrıyı bul, sonra bekçiyi güncelle.')


#: Uç varsayılanı ÖLÇÜLDÜ (elle yazılmadı).
UC_VARSAYILANI = _app_uc_varsayilani()


def _enjektor(tip, sekil):
    """(ρ, künye) çifti — verilen oksitleyici tipi ve gövde şekli için.

    Üç gövde şekli, uçtaki üç farklı JSON durumunun kurucu karşılığıdır:
    alan hiç yok (uç varsayılanı devreye girer), alan ``null`` (yedek zinciri
    açılır), alan dolu (kullanıcı kazanmalı).
    """
    if sekil == GOVDE_KULLANICI:
        yogunluk = KULLANICI_YOGUNLUGU
    elif sekil == GOVDE_ALAN_YOK:
        yogunluk = UC_VARSAYILANI
    else:
        yogunluk = None
    yutucu = io.StringIO()
    with warnings.catch_warnings(), redirect_stdout(yutucu):
        warnings.simplefilter('ignore')
        enj = InjectorDesign(mdot_ox=0.4, chamber_pressure=20.0,
                             tank_pressure=50.0, oxidizer_temp=293.15,
                             oxidizer_density=yogunluk, oxidizer_type=tip)
    return float(enj.rho_ox), enj.density_source


# ===========================================================================
# 0) SAĞLIKLI DESEN TESCİLİ — doğru cevap depoda ZATEN var
# ===========================================================================
def _ikiz_rho(tip, **ek):
    """``HybridRocketEngine._get_oxidizer_density`` — sessiz koşu."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    yutucu = io.StringIO()
    with warnings.catch_warnings(), redirect_stdout(yutucu):
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(thrust=1000, burn_time=10, of_ratio=2.5,
                                   chamber_pressure=20.0, oxidizer_type=tip,
                                   track_performance=False, **ek)
        return float(motor._get_oxidizer_density())


@pytest.mark.parametrize('tip', ('lox', 'h2o2', 'n2o4'))
def test_onarilmis_ikiz_kanonik_degeri_veriyor(tip):
    """``HybridRocketEngine._get_oxidizer_density`` merkezî tabloyla uyuşuyor.

    Bu bekçi bir kusuru değil, **onarımın referansını** kilitler: enjektör
    kanalının hedefi budur. Buradaki kanal bozulursa matris bekçilerinin
    çapası da kaybolur, o yüzden ayrıca korunur.

    ÖH D15 birleşme (1 Eylül 2026): ``n2o`` bu listeden ÇIKARILDI ve kendi
    testine taşındı — gerekçesi aşağıda.
    """
    rho = _ikiz_rho(tip)
    kanon = _kanonik_yogunluk(tip)
    assert kanon is not None
    assert rho == pytest.approx(kanon, rel=BANT), (
        f'{tip}: onarılmış ikiz {rho:.3f} kg/m³ veriyor, merkezî tablo '
        f'{kanon:.3f}. Onarımın REFERANSI kaymış — matris bekçilerinin '
        'çapası bu kanaldır.')


def test_n2o_ikizi_doygunluk_modelinden_ve_tank_sicakligindan():
    """N₂O'nun referansı DURAĞAN TABLO değil, tankın okuduğu doygunluk modeli.

    ÇEVRİLDİ — ÖH D15 birleşme etkileşimi (1 Eylül 2026)
    ----------------------------------------------------
    Eski satır N₂O'yu da merkezî tablonun tek sayısına (745,0 kg/m³ = doygun
    sıvı @ 298,15 K) bağlıyordu. Hibrit kulvarının **P1B1-03** onarımı tam o
    bağı KOPARDI ve yerine tek kaynak koydu: N₂O kendinden basınçlıdır, sıvı
    yoğunluğu tank SICAKLIĞININ fonksiyonudur ve enjektör artık tank blowdown
    bloğunun okuduğu AYNI modeli (``hrma.analysis.tank_blowdown.
    N2OSaturation``) okur.

    ÖLÇÜLDÜ (hibrit a1 ``once.json``): onarımdan önce ``T_tank = 298.15``
    SABİT yazılıydı; tank_temperature = None/280/293,15/305 K'nin DÖRDÜNDE de
    enjektör 742,933 kg/m³ görüyordu, oysa aynı yanıttaki blowdown bloğu
    785,10 / 870,44 / 785,10 / 661,16 kg/m³ yayımlıyordu (280 K'de %14,65
    fark). Durağan tabloya bağlayan iddia, kapatılan kusurun ta kendisini
    talep ediyordu; bu yüzden ÇEVRİLDİ, gevşetilmedi: yeni sözleşme dört
    sıcaklıkta BİT-ÖZDEŞLİK ister (eski hâli tek noktada %2 bant istiyordu).
    """
    from hrma.analysis.tank_blowdown import N2OSaturation
    from hrma.engines.hybrid_rocket_engine import TANK_TEMPERATURE_DEFAULT_K
    doygunluk = N2OSaturation()
    # (1) Varsayılan sıcaklıkta enjektör = tankın modeli, BİT düzeyinde.
    varsayilan = _ikiz_rho('n2o')
    assert varsayilan == pytest.approx(
        float(doygunluk.rho_l(TANK_TEMPERATURE_DEFAULT_K)), rel=1e-12), (
        'N₂O enjektör yoğunluğu tankın doygunluk modelinden gelmiyor — '
        'iki modül yine iki sayı veriyor (P1B1-03 kusuru)')
    # (2) Sıcaklıkla GERÇEKTEN hareket eder (sabit sayı kanalı kopmuş olamaz).
    olculen = {T: _ikiz_rho('n2o', tank_temperature=T)
               for T in (280.0, 293.15, 305.0)}
    for T, rho in olculen.items():
        assert rho == pytest.approx(float(doygunluk.rho_l(T)), rel=1e-12), (
            f'T_tank = {T} K: enjektör {rho!r}, doygunluk modeli '
            f'{doygunluk.rho_l(T)!r}')
    assert len(set(round(v, 9) for v in olculen.values())) == 3, (
        f'yoğunluk tank sıcaklığına yanıt vermiyor: {olculen} — sabit sayı '
        'kanalı geri gelmiş')
    # (3) Merkezî tablonun durağan değeri ARTIK REFERANS DEĞİL; farkın
    #     ölçülebilir olması bu testin kendi ön koşuludur.
    kanon = _kanonik_yogunluk('n2o')
    assert kanon is not None
    assert abs(varsayilan - kanon) / kanon > 1e-3, (
        'durağan tablo değeri ile doygunluk çözümü aynı noktaya düştü — '
        'bu testin ayırt ediciliği kalmadı, senaryo güncellenmeli')


# ===========================================================================
# 1) MATRİS — 5 oksitleyici × 3 gövde şekli için (ρ, künye) çifti
# ===========================================================================
def _matris_param(tip, sekil, defter=None, olculen=None):
    if defter is None:
        return pytest.param(tip, sekil, id=f'{tip}-{sekil}')
    return pytest.param(
        tip, sekil, id=f'{tip}-{sekil}',
        marks=pytest.mark.xfail(strict=True, reason=f'ÖH defter {defter} — {olculen}'))


#: n2o hücrelerinin AÇIK KALMA gerekçesi (Z1 onarımı SONRASI, ölçüldü):
#: 1220 dayatması bitti; kalan fark kanon-sıcaklık uyuşmazlığıdır. Merkezî
#: tablo 745,0 yazıyor (298,15 K doygun sıvı), tek doğruluk kaynağı enjektör
#: sorgusuna (293,15 K) 785,104 veriyor — %+5,38, bandın (%2) dışı. İkisi de
#: fiziksel olarak DOĞRU, farklı sıcaklığın değerleri. Karar Berke'de:
#: (a) bekçi kanonu T'li tek kaynağa bağlansın, (b) sorgu 298,15 K'ye
#: çekilsin, (c) tabloya 293,15 K kanonu eklensin. Karara kadar im kalır.
N2O_KANON_SICAKLIK_KARARI = (
    'Z1 sonrası AÇIK — kanon 745,0 (298,15 K) ⟷ tek kaynak 785,104 '
    '(293,15 K sorgusu), %+5,38; kanonun sıcaklık etiketi kararı Berke\'de')

MATRIS = [
    # --- kullanıcı gövdesi: sözleşme BUGÜN sağlam (yeşil) -------------------
    _matris_param('n2o', GOVDE_KULLANICI),
    _matris_param('lox', GOVDE_KULLANICI),
    _matris_param('h2o2', GOVDE_KULLANICI),
    _matris_param('n2o4', GOVDE_KULLANICI),
    _matris_param('generic', GOVDE_KULLANICI),
    # --- alan yok: Z1 onarımıyla uç varsayılanı KALKTI (None geçiliyor) -----
    _matris_param('n2o', GOVDE_ALAN_YOK, 'P14M2-09 (kalan ayak)',
                  N2O_KANON_SICAKLIK_KARARI),
    _matris_param('lox', GOVDE_ALAN_YOK),
    _matris_param('h2o2', GOVDE_ALAN_YOK),
    _matris_param('n2o4', GOVDE_ALAN_YOK),
    _matris_param('generic', GOVDE_ALAN_YOK),   # fail-closed — aşağıda ayrı iddia
    # --- alan null: yedek zinciri tek kaynağa bağlandı ----------------------
    _matris_param('n2o', GOVDE_ALAN_NULL, 'P14M2-08 (kalan ayak)',
                  N2O_KANON_SICAKLIK_KARARI),
    _matris_param('lox', GOVDE_ALAN_NULL),
    _matris_param('h2o2', GOVDE_ALAN_NULL),
    _matris_param('n2o4', GOVDE_ALAN_NULL),
    _matris_param('generic', GOVDE_ALAN_NULL),  # fail-closed — aşağıda ayrı iddia
]


@pytest.mark.parametrize('tip,sekil', MATRIS)
def test_yogunluk_matrisi_deger_ve_kunye(tip, sekil):
    """Her (tip, gövde şekli) hücresi için (ρ, künye) çifti DOĞRU olmalı.

    İki iddia bir arada tutulur, çünkü kusur da bir aradaydı: yanlış sayı,
    doğru görünen künyeyle geldi. Ayrı ayrı ölçülseydi biri yeşil kalır ve
    hücre "kısmen doğru" görünürdü.
    """
    kanon = _kanonik_yogunluk(tip)
    if kanon is None and sekil != GOVDE_KULLANICI:
        # 'generic' + sayı verilmedi: savunulabilir sayı YOK. Z1 onarımı
        # sonrası doğru davranış SAYI UYDURMAK DEĞİL fail-closed istisnadır
        # (eskiden N2O tablosu "NIST WebBook" künyesiyle dayatılıyordu).
        from hrma.utils.injector_design import OxidizerStateError
        with pytest.raises(OxidizerStateError, match='generic'):
            _enjektor(tip, sekil)
        return

    rho, kunye = _enjektor(tip, sekil)

    if sekil == GOVDE_KULLANICI:
        # Sözleşme: kullanıcı KAZANIR ve künye bunu söyler (yedeğe düşmez).
        assert rho == pytest.approx(KULLANICI_YOGUNLUGU, rel=1e-12), (
            f'{tip}: kullanıcının verdiği yoğunluk ezilmiş -> {rho!r}')
        assert kunye == DENSITY_SOURCE_USER, (
            f'{tip}: kullanıcı değeri kullanılıyor ama künye {kunye!r} diyor')
        return

    if sekil == GOVDE_ALAN_YOK:
        # Kullanıcı HİÇBİR ŞEY vermedi; sayı artık üründen kaynaklı gelmeli.
        # Künyenin "user input" demesi künye yalanıdır (P14M2-09 künye ayağı).
        assert kunye != DENSITY_SOURCE_USER, (
            f'{tip}: kullanıcı yoğunluk vermedi ama künye "{kunye}" diyor; '
            f'sayı ({rho:.3f} kg/m³) üründen geliyor')

    assert rho == pytest.approx(kanon, rel=BANT), (
        f'{tip} / {sekil}: enjektör {rho:.3f} kg/m³ çözüyor, deponun kendi '
        f'merkezî tablosu {kanon:.3f} kg/m³ diyor (sapma '
        f'%{100.0 * (rho / kanon - 1):+.1f}). Aynı oksitleyicinin yoğunluğu '
        'aynı depoda iki sayı olamaz; onarımın deseni '
        'HybridRocketEngine._get_oxidizer_density içinde YAZILI.')


# ===========================================================================
# 2) KAYNAK MATRİSİ — aynı büyüklüğü çözen CANLI kanallar ayrışamaz
# ===========================================================================
@pytest.mark.parametrize('tip', (
    pytest.param('n2o', marks=pytest.mark.xfail(strict=True, reason=(
        'ÖH defter P14H1-Ç2 (kalan ayak) — ' + N2O_KANON_SICAKLIK_KARARI))),
    'lox', 'h2o2', 'n2o4'))
def test_app_yogunluk_fonksiyonu_kanonla_uyusuyor(tip):
    """İkinci canlı çözücü de merkezî tabloyla aynı sayıyı vermeli.

    Z1 onarımı: 948,8 üreten NBP-ekstrapolasyonu söküldü, fonksiyon tek
    doğruluk kaynağına delege ediyor — lox/h2o2/n2o4 yeşile döndü.

    ÖH D20 / OH-D19-02 — BEKÇİ ÇEVRİLDİ. Bu test 293,15 K'de ``lox`` için
    ``1141,0`` kg/m³ İSTİYORDU; oysa O₂ o sıcaklıkta SIVI DEĞİLDİR (kritik
    sıcaklık 154,58 K) ve aynı çağrının künyesi zaten ``state_reason =
    'outside_liquid_band'`` diyordu. Yani bekçi, tek kaynakla uyumu ölçerken
    HÂL HATASINI da kilitliyordu. Uyum iddiası aynen korunur — yalnız
    akışkanın sıvı bandının DIŞINDA sorulduğunda artık sayı değil
    ``OxidizerStateError`` beklenir (fail-closed).
    """
    from hrma.app import get_oxidizer_density
    from hrma.data.external_data_fetcher import (
        OxidizerStateError, oxidizer_reference_density)

    if oxidizer_reference_density(tip, 293.15)['state_reason'] == \
            'outside_liquid_band':
        with pytest.raises(OxidizerStateError):
            get_oxidizer_density(tip, 293.15)
        return
    rho = float(get_oxidizer_density(tip, 293.15))
    kanon = _kanonik_yogunluk(tip)
    assert rho == pytest.approx(kanon, rel=BANT), (
        f'{tip}: app.get_oxidizer_density {rho:.2f} kg/m³, merkezî tablo '
        f'{kanon:.2f} kg/m³ (sapma %{100.0 * (rho / kanon - 1):+.1f})')


def test_yerel_yedek_deponun_kanonuyla_uyusuyor():
    """Yerel yedek, merkezî tablonun N2O değerinden türemiş olmalı."""
    kanon = _kanonik_yogunluk('n2o')
    assert float(LOCAL_DENSITY_FALLBACK) == pytest.approx(kanon, rel=BANT), (
        f'LOCAL_DENSITY_FALLBACK = {LOCAL_DENSITY_FALLBACK}, merkezî tablo '
        f'{kanon}. Yedek sayı elle yazılmak yerine tablodan okunmalı '
        '(magic-number tekrarı + iki farklı fiziksel koşul).')


def test_uc_varsayilani_SESSIZ_sayi_dayatmiyor():
    """Uç, oksitleyiciden bağımsız bir yoğunluk varsayamaz.

    Doğru onarım varsayılanı DEĞİŞTİRMEK değil KALDIRMAKtır: alan yoksa
    ``None`` geçmeli ve çözücü tipe göre kendi kaynaklı değerini kaynağıyla
    birlikte kullanmalı. Bu bekçi tam olarak onu bekler.
    """
    assert UC_VARSAYILANI is None, (
        f'uç varsayılanı hâlâ sabit bir sayı: {UC_VARSAYILANI!r}. Tip bilgisi '
        'zaten aynı gövdede (oxidizer_type); tek sayı beş oksitleyiciyi '
        'birden temsil edemez.')


# ===========================================================================
# 3) KÜNYE BİR DOĞRULAMA BAYRAĞI OLAMAZ
# ===========================================================================
def test_kunye_NIST_ise_sayi_gercekten_NISTten_gelmis_olmali(monkeypatch):
    """"NIST WebBook" künyesi ancak gerçekten oradan gelen sayıya konur.

    Ölçüm yöntemi kendi içinde mutasyonludur: gömülü yedek tablonun değeri
    bir imle (sentinel) değiştirilir. Ürünün yayımladığı ρ o imi taşıyorsa,
    sayının kaynağı kanıtlanmış olur — künye artık NIST diyemez.

    Yön kilidi: onarım sayıyı merkezî tablodan almaya başlarsa im görünmez ve
    iddia kendiliğinden sağlanır (XPASS -> kırmızı -> işaret silinir). Yani
    bekçi hem bugünkü yalanı sayar hem de onarımı fark eder.
    """
    im = 1337.0     # doğrulama bandının (800-1500) içinde, hiçbir yedeğe eşit değil
    monkeypatch.setitem(data_fetcher.backup_data['n2o_properties'],
                        'density_liquid_20C', im)
    rho, kunye = _enjektor('lox', GOVDE_ALAN_NULL)
    yedekten_geldi = abs(rho - im) < 1e-6
    if kunye == DENSITY_SOURCE_NIST:
        assert not yedekten_geldi, (
            f'künye "{kunye}" diyor ama ρ={rho} gömülü yedek tablodan geldi '
            '(im birebir taşındı). Künye bir VERİ KAYNAĞI beyanıdır; '
            '"doğrulamadan geçti" bayrağı olarak kullanılamaz.')


def test_yedek_tablo_oksitleyici_TIPINI_okuyor():
    """Yedek sağlayıcı LOX'a N2O tablosunu veremez."""
    yutucu = io.StringIO()
    with redirect_stdout(yutucu):
        lox = data_fetcher._get_backup_oxidizer_properties('lox', 293.15)
        n2o = data_fetcher._get_backup_oxidizer_properties('n2o', 293.15)
    assert float(lox['density']) != pytest.approx(float(n2o['density']),
                                                  rel=1e-9), (
        f"yedek tablo LOX için de N2O yoğunluğunu ({lox['density']}) "
        'döndürüyor; oxidizer_type argümanı ölü.')


def test_dogrulama_bandi_deponun_KENDI_kanonunu_reddetmiyor():
    """Doğrulama bandı, deponun kendi doğru cevabını dışlayamaz.

    Bu, onarım sırasını belirleyen bekçidir: yedek tablo düzeltilse bile bant
    düzeltilmediği sürece doğru sayı ürüne ULAŞAMAZ.
    """
    kanon = _kanonik_yogunluk('n2o')
    gecerli, mesaj = data_fetcher.validate_data(
        {'density': kanon, 'viscosity': 0.0002}, 'oxidizer')
    assert gecerli, (
        f'merkezî tablonun N2O değeri ({kanon} kg/m³) doğrulamadan geçemiyor: '
        f'{mesaj}. Band, düzeltilmiş değeri reddediyor.')


# ===========================================================================
# 4) UÇ ERİŞİLEBİLİRLİĞİ — bulgu laboratuvarda değil üründe
# ===========================================================================
@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _uc_enjektoru(istemci, tip):
    yuk = {'motor_name': 'FAZB-rho-' + tip, 'thrust': 1000.0,
           'burn_time': 10.0, 'chamber_pressure': 20.0, 'of_ratio': 5.0,
           'fuel_type': 'htpb', 'oxidizer_type': tip,
           'oxidizer_density': None, 'include_plots': False}
    yutucu = io.StringIO()
    with warnings.catch_warnings(), redirect_stdout(yutucu):
        warnings.simplefilter('ignore')
        yanit = istemci.post('/calculate', json=yuk,
                             headers={'Content-Type': 'application/json'})
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    return (yanit.get_json() or {}).get('injector') or {}


def test_ucta_iki_oksitleyici_AYNI_enjektoru_almiyor(istemci):
    """Yoğunluğu farklı iki akışkan aynı orifis geometrisini alamaz.

    v = √(2ΔP/ρ) ve A = ṁ/(C_d·√(2ρΔP)): ρ %65 değişirse çıkış hızı ~%28
    değişmek ZORUNDA. Aynı çıkması, yoğunluğun hiç kullanılmadığının
    (tek bir sayının paylaşıldığının) uç düzeyinde kanıtıdır.
    """
    lox = _uc_enjektoru(istemci, 'lox')
    n2o = _uc_enjektoru(istemci, 'n2o')
    assert lox.get('exit_velocity') is not None
    assert lox['exit_velocity'] != pytest.approx(n2o['exit_velocity'],
                                                 rel=1e-3), (
        f"LOX {lox['exit_velocity']!r} ↔ N2O {n2o['exit_velocity']!r} m/s — "
        'iki oksitleyici aynı enjektörü alıyor')


def test_ucta_kunye_LOX_icin_NIST_demiyor(istemci):
    """Künye yalanı uçtan da görünür olmalı (kullanıcının gördüğü alan)."""
    lox = _uc_enjektoru(istemci, 'lox')
    assert lox.get('density_source') != DENSITY_SOURCE_NIST, (
        f"uç LOX için künyeyi '{lox.get('density_source')}' diye yayımlıyor")


@pytest.mark.parametrize('tip', ('n2o', 'lox'))
def test_ucta_alan_yokken_kunye_KULLANICI_demiyor(istemci, tip):
    """Gönderilmemiş bir alan "kullanıcı girdisi" diye künyelenemez."""
    yuk = {'motor_name': 'FAZB-rho-yok-' + tip, 'thrust': 1000.0,
           'burn_time': 10.0, 'chamber_pressure': 20.0, 'of_ratio': 5.0,
           'fuel_type': 'htpb', 'oxidizer_type': tip, 'include_plots': False}
    yutucu = io.StringIO()
    with warnings.catch_warnings(), redirect_stdout(yutucu):
        warnings.simplefilter('ignore')
        yanit = istemci.post('/calculate', json=yuk,
                             headers={'Content-Type': 'application/json'})
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    inj = (yanit.get_json() or {}).get('injector') or {}
    assert inj.get('density_source') != DENSITY_SOURCE_USER, (
        f"{tip}: alan gönderilmedi ama yanıt künyeyi "
        f"'{inj.get('density_source')}' diye yayımlıyor")


def test_n2o_ucunun_kunyesi_DURUST(istemci):
    """N2O yolunda künye dürüst kalmalı: kaynağı, hâli ve sıcaklığı söyler.

    Z1 öncesi buradaki çalışan örnek 'local fallback' etiketiydi; onarım
    künyeyi kaynağın kendisinden üretiyor. Bekçi biçime değil İÇERİĞE
    kilitlenir: künye boş olamaz, 'user input' diyemez (kullanıcı vermedi)
    ve doymuş-sıvı hâlini sıcaklığıyla adlandırmak zorundadır.
    """
    n2o = _uc_enjektoru(istemci, 'n2o')
    kunye = n2o.get('density_source') or ''
    assert kunye, 'N2O yolunda density_source künyesi kaybolmuş'
    assert kunye != DENSITY_SOURCE_USER, (
        f'kullanıcı yoğunluk vermedi ama künye {kunye!r}')
    assert 'saturated liquid' in kunye and '293' in kunye, (
        f'künye kaynağın hâlini/sıcaklığını adlandırmıyor: {kunye!r}')


# ===========================================================================
# 5) ŞABLON KISITI (P14S1-01) — uç onarımı şablonun altında ÖRTÜLMESİN
# ===========================================================================
# test_sablonlar_koşulsuz_1220_gondermiyor (1 düğüm; _sablon_1220_siteleri yardımcısıyla) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum


def test_advanced_sablonu_ONARIMI_TASIYOR():
    """Onarılmış kardeş geri kaymamalı (desenin kendisi korunuyor)."""
    with open(ADVANCED_HTML, encoding='utf-8') as f:
        metin = f.read()
    assert not re.search(r"oxidizer_density\s*:.*?1220", metin), (
        'advanced.html v2.6.26 onarımını KAYBETMİŞ — koşulsuz 1220 geri gelmiş')
    assert "oxidizer_density: numById('oxidizer_density')" in metin, (
        'advanced.html artık alanı doğrudan okumuyor; onarım deseni bozulmuş')
