"""ÖH Z5S / bekçi-ödeme paketi B2 — KÜNYE TUTAR MI?

Sekiz *onarıldı* kaleminin kapanış şartı: onarımın kilidini vuran bekçi.
Bu dosya ürün koduna DOKUNMAZ; yalnız onarılan davranışı ve künyeyi
sabitler. Her iddia bu depoda ÖLÇÜLDÜ (27 Ağustos 2026); ölçüm çıktıları
``docs/scofield/raw/OH/Z5S/guardb2/`` altındadır.

Ödenen borçlar
--------------

* **P7B3-07** (kritik) — ``/api/get-propellant-properties`` kategori
  etiketi yoğunluğu değiştiriyordu (``oxidizer`` dalı ``props.get('density',
  1200)``, ``liquid_fuel`` dalı ``800``). Kategori yedeği merkezî tabloyu
  eziyordu: N₂O₄ için depo 1443 biliyorken uç 1200 yayımlıyordu (−%16,9) ve
  o sayı ``liquid.html``den form alanına yazılıp ``/calculate_liquid``e
  gidiyordu. Z1 onarımı kanıtsız alanı düşürüyor; t14 bekçisi rp1/htpb
  kolunu kapsıyordu, **n2o4/mmh/udmh uç ölçümü bekçisizdi** — sınıf A.

* **P10B1-20** (orta) — ``hrma/utils/injector_design.py``: oksitleyici
  kimliği ``str(oxidizer_type or 'n2o')`` ile sessizce N₂O oluyordu; adını
  kaybeden bir LOX/H₂O₂ koşusu N₂O'nun σ, P_v ve ρ değerlerini miras
  alıyordu. Tablo dışı oksitleyici (n2o4, h2o2) yüzey gerilimi ve buhar
  basıncı varsayımlarını "varsayıldı" DEMEDEN alıyordu — sınıf B.

* **P14H1-C2** (yüksek) — ``app.get_oxidizer_density('n2o')`` 20 °C'de
  948,80 kg/m³ derken enjektör/motor 1220,00 diyordu (%22,2 ayrışma, ikisi
  de canlı). 948,80 bağımsız bir literatür değeri değil, 1220'nin (N₂O'nun
  normal kaynama noktası yoğunluğu) −2,5 kg/(m³·K) eğimle 293,15 K'ye
  taşınmasıydı — sınıf C.

* **P15B3-07** (orta) — yerel tablo değerinin üstünde yeşil "Real-time
  Data" rozeti ve altında "NASA RP-1 Specification" kaynak metni vardı; o
  yolda canlı istek YOK. Rozetin JS ayağı A2 paketinde
  (``test_z5guard_panel_motor.py::test_d1``) kilitlendi; burada rozeti
  BESLEYEN uç verisi kilitlenir — sınıf D.

* **P15B4-07** (orta) — aynı yanıtta iki ``case_design`` bloğu vardı
  (``design_summary`` 5 alan, ``cad_design`` 11 alan) ve kesişimleri TEK
  alandı (``material``); cidarın kaynağını söyleyen ``thickness_source``
  yalnız birindeydi, yani imalata giden blok cidarın kullanıcıdan mı
  geldiğini söylemiyordu — sınıf E.

* **P15B4-10** (yüksek) — yapısal analiz ön kapağı 1,9948 mm derken imalat
  STEP'i 8,0000 mm çiziyordu (4,01×); aynı dosyada cidar kapılıyken kapak
  sabitti — sınıf F.

* **P15S1-01** (orta) — ``/calculate`` cidar künyesi 11 girdinin 5'inde
  "No wall thickness was supplied" diyordu; kök neden ``_mm_to_m_optional``
  helper'ının "gönderilmedi" ile "okunamadı"yı aynı ``None``'a indirmesiydi.
  Türkçe ondalık ayraçlı ``'5,0'`` de bu kapıya çarpıyordu — sınıf G.

* **P15S1-02** (orta) — aynı fiziksel cidar iki uçta 10 satırın 5'inde ayrı
  kapı sınıfı alıyordu; üç durumlu künyenin fail-closed üçüncü durumu
  ``/analyze_structural_safety`` rotasında HİÇ ateşlemiyordu — sınıf H.

Bekçinin sözleşmesi
-------------------

Bekçiler DAVRANIŞ ve KÜNYE kilitler. Sayısal çapalar ürünün bugün ürettiği
değerlerdir (kanıt dosyalarında ham hâlleriyle duruyor) ve platform kayması
için ``rel=1e-9`` bandıyla sınanır — bit-eşitlik yalnız "aynı fonksiyon mu
çağrılıyor" sorusunun sorulduğu yerde istenir.
"""

import contextlib
import io
import math
import os
import re
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

HEADERS = {'Host': '127.0.0.1:8080'}

APP_PY = os.path.join(REPO_ROOT, 'hrma', 'app.py')
STEP_PY = os.path.join(REPO_ROOT, 'hrma', 'export', 'step_export.py')
PANEL_JS = os.path.join(REPO_ROOT, 'hrma', 'static', 'js', 'panels',
                        'structural_panel.js')

#: Hibrit ``/calculate`` gövdesi (dock sözleşmesiyle aynı).
HIBRIT_YUKU = {
    'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
    'chamber_pressure': 20.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
}

#: ``/analyze_structural_safety`` gövdesi (panelin gönderdiği alanlar).
YAPISAL_YUKU = {
    'chamber_pressure': 40, 'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'throat_diameter': 0.02, 'burn_time': 10, 'material': 'steel_4130',
}

#: Katı motor gövdesi (Z2-A ölçüm koşumlarıyla aynı).
KATI_YUKU = {
    'chamber_diameter': 100, 'grain_length': 500, 'core_diameter': 30,
    'chamber_pressure': 40, 'propellant_type': 'apcp',
}


def _sessiz(fn, *a, **kw):
    """Motor çözücülerinin stdout gürültüsünü yutar."""
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        return fn(*a, **kw)


def _kaynak(yol):
    with open(yol, encoding='utf-8') as tutamac:
        return tutamac.read()


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ===========================================================================
# A — P7B3-07: kategori etiketi yoğunluğu DEĞİŞTİREMEZ
# ===========================================================================
#: Uç noktanın tanıdığı kategori dalları (``get_propellant_for_ui``) +
#: tanımadığı bir etiket: dördü de aynı akışkan için aynı sayıyı vermeli.
KATEGORI_ETIKETLERI = ('oxidizer', 'liquid_fuel', 'hybrid_fuel',
                       'solid_propellant')

#: ``open_source_propellant_api.get_propellant_for_ui`` kategori
#: varsayılanları (ölçüldü, :640/:652/:665/:676). Bunlar akışkanın DEĞİL
#: kategorinin sayılarıdır; akışkanın kendi kaydı varken yayımlanamazlar.
KATEGORI_YEDEKLERI = {'oxidizer': 1200, 'liquid_fuel': 800,
                      'hybrid_fuel': 920, 'solid_propellant': 1800}

#: Deponun merkezî tablosundaki (``propellant_database``) gerçek değerler.
#: n2o4/mmh/udmh kolu bugüne dek BEKÇİSİZDİ — kalemin kapanış şartı budur.
MERKEZI_TABLO = {'n2o4': 1443, 'mmh': 875, 'udmh': 791, 'rp1': 810}


def _uc_ozellikleri(istemci, ad, tur):
    yanit = istemci.post('/api/get-propellant-properties',
                         json={'propellant_type': tur, 'propellant_name': ad},
                         headers=HEADERS)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    govde = yanit.get_json()
    assert govde['status'] == 'success'
    return govde


@pytest.mark.parametrize('ad', ('n2o4', 'mmh', 'udmh', 'rp1'))
def test_a1_kategori_etiketi_yogunlugu_degistirmiyor(istemci, ad):
    """Aynı akışkan, dört kategori etiketi -> TEK yoğunluk.

    Ölçülen kusur (Z1 öncesi): ``oxidizer/n2o4`` 1200, ``liquid_fuel/rp1``
    800, ``hybrid_fuel/rp1`` 920 — sayı akışkanın değil ETİKETİN sayısıydı.
    """
    okunan = {}
    for tur in KATEGORI_ETIKETLERI:
        govde = _sessiz(_uc_ozellikleri, istemci, ad, tur)
        okunan[tur] = (govde['properties'] or {}).get('density')

    benzersiz = {repr(v) for v in okunan.values()}
    assert len(benzersiz) == 1, (
        f'{ad}: kategori etiketi yoğunluğu değiştiriyor -> {okunan}')
    assert okunan['oxidizer'] == MERKEZI_TABLO[ad], (
        f'{ad}: uç {okunan["oxidizer"]!r} yayımlıyor, deponun merkezî '
        f'tablosu {MERKEZI_TABLO[ad]} diyor')


@pytest.mark.parametrize('ad', ('n2o4', 'mmh', 'udmh', 'rp1'))
def test_a2_kategori_yedegi_yayimlanmiyor(istemci, ad):
    """Kategori sabiti (1200/800/1800) akışkanın sayısı olarak basılamaz.

    ``hybrid_fuel`` yedeği (920) HTPB'nin GERÇEK yoğunluğudur; bu yüzden
    yasak literal listesi akışkana göre kurulur — htpb bu testte yok.
    """
    for tur in KATEGORI_ETIKETLERI:
        govde = _sessiz(_uc_ozellikleri, istemci, ad, tur)
        yogunluk = (govde['properties'] or {}).get('density')
        yasak = KATEGORI_YEDEKLERI[tur]
        assert yogunluk != yasak, (
            f'{ad}/{tur}: kategori yedeği {yasak} akışkanın yoğunluğu diye '
            f'yayımlandı (merkezî tablo {MERKEZI_TABLO[ad]} diyor)')


@pytest.mark.parametrize('ad', ('n2o4', 'mmh', 'udmh'))
def test_a3_dusurulen_alanlar_ADIYLA_bildiriliyor(istemci, ad):
    """Sessiz kalınmaz: kanıtı olmayan alan düşürülür ve ADI söylenir."""
    govde = _sessiz(_uc_ozellikleri, istemci, ad, 'oxidizer')
    ozellikler = govde['properties'] or {}
    dusenler = ozellikler.get('category_defaults_suppressed')
    assert isinstance(dusenler, list) and dusenler, (
        f'{ad}: kategori yedeği düşürüldü ama hangi alanlar olduğu '
        f'bildirilmedi ({dusenler!r})')
    assert 'density' in dusenler, (
        f'{ad}: yoğunluk kategori yedeğinden geliyordu, düşürülenler '
        f'listesinde adı yok -> {dusenler}')
    # Düşürülen alan yerine uydurma sayı KONMAZ: yayımlanan yoğunluk
    # merkezî tablonun kendi değeridir.
    assert ozellikler.get('density') == MERKEZI_TABLO[ad]


@pytest.mark.parametrize('ad', ('zzz_bilinmeyen', ''))
def test_a4_taninmayan_akiskan_sayi_uydurmuyor(istemci, ad):
    """Tanınmayan/boş ad: sayı uydurulmaz VE istek reddedilir.

    ÇEVRİLDİ — ÖH D15 / kulvar app-api / aşama 2 (P7B3-10). İddianın
    ÇEKİRDEĞİ ("tanınmayan akışkana sayı uydurulmaz") AYNEN korundu;
    değişen, testin o çekirdeği HTTP **200** gövdesinde aramasıydı.

    Bu hâliyle test kusuru KİLİTLİYORDU: ölçüldü (ÖH D15 a2 ``once.json``)
    ``propellant_name='ZZZ_NOT_A_PROPELLANT'`` HTTP 200 +
    ``source: 'Built-in propellant table'`` dönüyordu — o tabloda böyle bir
    kayıt YOK, yani uç var olmayan bir kayda atıf yapan bir künye
    üretiyordu. Sayılar Z1 sonrası zaten ``None``dı; kalan kusur tam olarak
    "ret yok, künye yalan"dı ve bu testin 200 şartı onarımın önünü
    kesiyordu.

    Yeni sözleşme fail-closed'dır: çözülmüş TEK bir özellik yoksa 422 +
    ``invalid_fields[0].field == 'propellant_name'``. Uydurma sayı iddiası
    hâlâ ölçülüyor — ret gövdesinde de hiçbir özellik sayısı yayımlanmaz.
    """
    for tur in KATEGORI_ETIKETLERI:
        yanit = _sessiz(
            istemci.post, '/api/get-propellant-properties',
            json={'propellant_type': tur, 'propellant_name': ad},
            headers=HEADERS)
        assert yanit.status_code == 422, (
            f'{ad!r}/{tur}: tanınmayan itici adı reddedilmedi -> '
            f'HTTP {yanit.status_code}')
        govde = yanit.get_json() or {}
        assert govde.get('error') == 'unresolved_propellant_name', govde
        alanlar = govde.get('invalid_fields') or []
        assert alanlar and alanlar[0].get('field') == 'propellant_name', (
            f'{ad!r}/{tur}: ret düzeltilecek alanı adlandırmıyor -> {govde}')
        # Uydurma sayı iddiası korunur: ret gövdesinde özellik YOKTUR.
        assert 'properties' not in govde, (
            f'{ad!r}/{tur}: reddedilen istekte özellik yayımlandı -> {govde}')


# ===========================================================================
# B — P10B1-20: oksitleyici kimliği SESSİZCE düşmez
# ===========================================================================
@pytest.mark.parametrize('ham', ('', None, '   '))
def test_b1_kimliksiz_oksitleyici_n2o_OLMUYOR(ham):
    """``''``/``None`` -> ``'unspecified'`` + fail-closed.

    Eski davranış: ``str(oxidizer_type or 'n2o')`` — adı kaybolan sıvı
    N₂O'nun yoğunluğunu (785,10), yüzey gerilimini (2,0577e-3 N/m) ve
    buhar basıncını (50,54 bar) miras alıyordu.
    """
    from hrma.data.external_data_fetcher import OxidizerStateError
    from hrma.utils.injector_design import OXIDIZER_UNSPECIFIED, InjectorDesign

    with pytest.raises(OxidizerStateError) as hata:
        _sessiz(InjectorDesign, mdot_ox=1.0, chamber_pressure=20,
                oxidizer_type=ham, tank_pressure=50, oxidizer_temp=293.15)
    metin = str(hata.value)
    assert OXIDIZER_UNSPECIFIED in metin, (
        f'kimliksiz oksitleyici açık etiketle anılmıyor: {metin[:200]}')
    assert '1220' in metin, (
        'gerekçe eski sessiz yedeğin (1220 kg/m³) ne olduğunu söylemiyor')


# h2o2 çapası 1450,0 -> 1438,1 (karar 28 Ağu): 1450 %100 saf H₂O₂'nin değeriydi,
# kaydın '%98' etiketinin değil; çapa kaydın yeni (etiketiyle tutarlı) değerini
# pinliyor — iddia AYNI güçte, hâlâ akışkanın KENDİ yoğunluğunu talep ediyor.
@pytest.mark.parametrize('ox,rho', (('n2o4', 1443.0), ('h2o2', 1438.1)))
def test_b2_tablo_disi_akiskan_sigma_VARSAYIM_diyor(ox, rho):
    """Tablo dışı oksitleyicide σ genel varsayımdır ve öyle bildirilir."""
    from hrma.utils.injector_design import (SIGMA_OX, SIGMA_OX_DEFAULT,
                                            InjectorDesign)

    tasarim = _sessiz(InjectorDesign, mdot_ox=1.0, chamber_pressure=20,
                      oxidizer_type=ox, tank_pressure=50, oxidizer_temp=293.15)
    sonuc = _sessiz(tasarim.calculate)

    assert tasarim.oxidizer_type == ox
    assert tasarim.rho_ox == pytest.approx(rho, rel=1e-9)
    assert sonuc['surface_tension'] == pytest.approx(SIGMA_OX_DEFAULT,
                                                     rel=1e-12)
    kunye = str(sonuc['surface_tension_basis'])
    assert 'generic assumption' in kunye, (
        f'{ox}: varsayılan σ "varsayıldı" demeden veriliyor -> {kunye}')
    assert 'NOT taken from another fluid' in kunye
    assert repr(ox) in kunye, f'{ox}: künye hangi akışkan olduğunu söylemiyor'
    # Başka bir akışkanın sayısı ödünç ALINMIYOR.
    for komsu, deger in SIGMA_OX.items():
        assert sonuc['surface_tension'] != pytest.approx(deger, rel=1e-12), (
            f'{ox}: σ olarak {komsu} tablosunun değeri ({deger}) kullanıldı')


@pytest.mark.parametrize('ox', ('n2o4', 'h2o2'))
def test_b3_tablo_disi_akiskan_buhar_basinci_ODUNC_ALMIYOR(ox):
    """P_v de kimlik düşmesine kapalı: N₂O'nun doyma basıncı ödünç verilmez.

    Ölçüldü: n2o @293,15 K -> 50,5434 bar (doyma tablosu); n2o4/h2o2 ->
    ``VAPOR_PRESSURE_ASSUMED_BAR`` = 0,05 bar (depolanabilir sıvı
    varsayımı). Sayı tek yerde tanımlıdır, akışkan başına kopyalanmaz.
    """
    from hrma.utils.injector_design import (VAPOR_PRESSURE_ASSUMED_BAR,
                                            InjectorDesign)

    tasarim = _sessiz(InjectorDesign, mdot_ox=1.0, chamber_pressure=20,
                      oxidizer_type=ox, tank_pressure=70, oxidizer_temp=293.15)
    assert tasarim.p_vapor_bar == pytest.approx(VAPOR_PRESSURE_ASSUMED_BAR,
                                                rel=1e-12)
    # Varsayımın KENDİSİ de depolanabilir sıvı sınıfında kalmalı: hava
    # basıncının altı. Bu bant olmadan "genel varsayım" adı altında N₂O'nun
    # 50 barı taşınabilirdi (mutasyonla ölçüldü).
    assert 0.0 < tasarim.p_vapor_bar < 1.0, (
        f'{ox}: genel buhar basıncı varsayımı {tasarim.p_vapor_bar!r} bar — '
        f'depolanabilir sıvı bandının (0-1 bar) dışında')

    n2o = _sessiz(InjectorDesign, mdot_ox=1.0, chamber_pressure=20,
                  oxidizer_type='n2o', tank_pressure=70, oxidizer_temp=293.15)
    assert n2o.p_vapor_bar > 40.0, (
        'N₂O buhar basıncı doyma tablosundan gelmiyor: '
        f'{n2o.p_vapor_bar!r}')
    assert n2o.p_vapor_bar / tasarim.p_vapor_bar > 100.0, (
        f'{ox}: buhar basıncı N₂O\'nun doyma basıncına yaklaştırıldı '
        f'({tasarim.p_vapor_bar!r} ⟷ {n2o.p_vapor_bar!r})')

    # --- Kullanılan P_v kullanıcıya GÖRÜNÜR mü? -------------------------
    # ÇEVİRİ (ÖH D15 / bekci-cevirisi, defter D15-BEKCI-03). Bu ayak
    # yukarıdaki ``tasarim`` üstünde kavitasyon uyarısı ARIYORDU ve
    # gerekçesi "K_c 1,5 altına indi" idi. O gerekçe P10-A onarımından
    # ÖNCEKİ ürüne aitti: K_c TANK istasyonundan kuruluyordu
    # (K_c = (P_tank − P_v)/(P_tank − P_c) = (70 − 0,05)/50 = 1,40) ve
    # uyarı yanıyordu. P10-A (P10B1-22) istasyonu düzeltti:
    # K_c = (P₁ − P_v)/dP, P₁ = P_c + dP.
    #
    # ÖLÇÜLDÜ (bu depo, çeviriden önce — betikler
    # ``docs/scofield/raw/OH/D15/bekci-cevirisi/a1/olcum_kavitasyon.py``
    # ve ``olcum_kav2.py``): bu çalışma noktasında dP = 4,0 bar,
    # P₁ = 24,0 bar, P_v = 0,05 bar -> K_c = 5,99. Yani uyarının BASILMAMASI
    # DOĞRUDUR; 0,05 barlık depolanabilir sıvı bu koşulda kavitasyon
    # yapmaz. Eski ayak, testin kendi kanıtladığı şeyin (P_v = 0,05 bar,
    # N₂O'nunkinin 1/1000'i) tersini istiyordu.
    #
    # Bekçinin GERÇEK iddiası korunuyor: kullanılan P_v kullanıcıya
    # görünür. Bunun için uyarının meşru yandığı bir çalışma noktası
    # kuruluyor (dP büyütülür, K_c 1,5 altına iner) ve uyarının taşıdığı
    # K_c sayısının DEPOLANABİLİR P_v'den çıktığı ölçülür — N₂O'nun 50,5
    # barı ödünç alınsaydı aynı noktada K_c 0,39 olurdu.
    assert not [u for u in (_sessiz(tasarim.calculate).get('warnings') or [])
                if 'Cavitation risk' in str(u)], (
        f'{ox}: P_v = {tasarim.p_vapor_bar} bar iken (K_c ≈ 6) kavitasyon '
        'uyarısı basıldı — uyarı buhar basıncından değil başka bir '
        'sayıdan besleniyor')

    DP_BAR = 50.0          # K_c'yi 1,5 altına indiren enjektör basınç düşümü
    P_C_BAR = 20.0
    kav_tasarim = _sessiz(InjectorDesign, mdot_ox=1.0,
                          chamber_pressure=P_C_BAR, oxidizer_type=ox,
                          tank_pressure=90, pressure_drop=DP_BAR,
                          oxidizer_temp=293.15)
    kavitasyon = [str(u) for u in
                  (_sessiz(kav_tasarim.calculate).get('warnings') or [])
                  if 'Cavitation risk' in str(u)]
    assert kavitasyon, (
        f'{ox}: dP = {DP_BAR} bar ile K_c 1,5 altına iniyor ama kavitasyon '
        'uyarısı basılmadı')
    assert 'P_v =' in kavitasyon[0], (
        f'{ox}: uyarı kullandığı buhar basıncını söylemiyor -> {kavitasyon[0]}')
    # Uyarıdaki K_c, DEPOLANABİLİR P_v'den çıkmalı. P₁ = P_c + dP.
    k_c_beklenen = ((P_C_BAR + DP_BAR) - VAPOR_PRESSURE_ASSUMED_BAR) / DP_BAR
    k_c_bildirilen = float(re.search(r'K_c = ([0-9.]+)', kavitasyon[0]).group(1))
    assert k_c_bildirilen == pytest.approx(k_c_beklenen, abs=0.01), (
        f'{ox}: uyarı K_c = {k_c_bildirilen} diyor, depolanabilir P_v ile '
        f'{k_c_beklenen:.2f} olmalıydı — N₂O doyma basıncı ödünç alınsaydı '
        f'{((P_C_BAR + DP_BAR) - n2o.p_vapor_bar) / DP_BAR:.2f} çıkardı')


def test_b4_sigma_tablosu_KOPYA_DEGIL_TUREV():
    """σ tablosu kardeş modülden türer; iki dosyada elle durmaz."""
    from hrma.engines.injector_design import SIGMA_LIQUID_REF
    from hrma.utils.injector_design import SIGMA_OX

    assert SIGMA_OX == {ad: deger for ad, (deger, _t)
                        in SIGMA_LIQUID_REF.items()}, (
        'utils σ tablosu kardeş modülün tablosundan ayrıştı')


# ===========================================================================
# C — P14H1-C2: aynı akışkan, aynı depoda iki yoğunluk olamaz
# ===========================================================================
#: 293,15 K'de ölçülen değerler (27 Ağu). 948,80 = eski NBP
#: ekstrapolasyonu (1220 − 2,5·(293,15 − 184,67)); 1220 = N₂O'nun normal
#: kaynama noktası yoğunluğu. İkisi de ARTIK üretilemez.
OLU_YOGUNLUKLAR = (948.8, 1220.0)


@pytest.mark.parametrize('ox', ('n2o', 'lox', 'h2o2', 'n2o4'))
@pytest.mark.parametrize('sicaklik', (293.15, 298.15))
def test_c1_app_fonksiyonu_TEK_KAYNAGA_delege_ediyor(ox, sicaklik):
    """``app.get_oxidizer_density`` kendi eğrisini çözmez, delege eder.

    ÖH D20 / OH-D19-02 — BEKÇİ ÇEVRİLDİ. Delegasyon iddiası aynen durur,
    ama "tek kaynakla BİREBİR aynı sayı" koşulu hâl hatasını da
    kilitliyordu: ``lox @293,15/298,15 K`` ve ``n2o4 @298,15 K`` için tek
    kaynağın künyesi ``state_reason = 'outside_liquid_band'`` derken bu
    bekçi skaler kanaldan o geçersiz sayının DÖNMESİNİ şart koşuyordu
    (ölçüldü: lox 1141,0 kg/m³ — O₂ orada gaz, ~1,31). Bant İÇİNDE eşitlik
    şartı aynen; bant DIŞINDA fail-closed şartı.
    """
    from hrma.app import get_oxidizer_density
    from hrma.data.external_data_fetcher import (
        OxidizerStateError, oxidizer_reference_density)

    kunye = oxidizer_reference_density(ox, sicaklik)
    if kunye['state_reason'] == 'outside_liquid_band':
        with pytest.raises(OxidizerStateError):
            get_oxidizer_density(ox, sicaklik)
        return
    beklenen = kunye['density']
    assert get_oxidizer_density(ox, sicaklik) == beklenen, (
        f'{ox} @{sicaklik} K: app fonksiyonu tek kaynaktan sapıyor')


def test_c2_NBP_ekstrapolasyonu_OLU():
    """948,80 ve 1220,00 293,15 K'de bir daha üretilemez."""
    from hrma.app import get_oxidizer_density

    rho = float(get_oxidizer_density('n2o', 293.15))
    for olu in OLU_YOGUNLUKLAR:
        assert abs(rho - olu) > 1.0, (
            f'N₂O @293,15 K yeniden {rho:.2f} kg/m³ veriyor — ölü değer '
            f'{olu} geri geldi (bkz. docs/arastirma/fizik/'
            f'Z1-yogunluk-dogrulama.md)')
    assert rho == pytest.approx(785.1039703874175, rel=1e-9)


def test_c3_UC_CANLI_KANAL_ayni_sayiyi_veriyor():
    """app / enjektör / motor: aynı sıcaklıkta bit-aynı sayı.

    P14H1-C2'nin özü buydu: ikisi de CANLI iki kanal aynı akışkan için
    948,80 ve 1220,00 diyordu (%22,2). Bugün üçü de aynı referans kapısını
    çağırıyor; ayrışma yalnız SORULAN SICAKLIKTAN doğabilir.
    """
    from hrma.app import get_oxidizer_density
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    from hrma.utils.injector_design import InjectorDesign

    enjektor = _sessiz(InjectorDesign, mdot_ox=1.0, chamber_pressure=20,
                       oxidizer_type='n2o', tank_pressure=50,
                       oxidizer_temp=293.15)
    assert enjektor.rho_ox == get_oxidizer_density('n2o', 293.15), (
        'enjektör ile app aynı sıcaklıkta ayrışıyor')

    # ÖH D15 birleştirme (1 Eyl 2026) — SICAKLIK ARTIK SABİT DEĞİL.
    # Burada 298,15 K YAZILIYDI. Hibrit kulvarın P1B1-03 onarımı motorun
    # içindeki sabit ``T_tank = 298.15``i kaldırdı: yoğunluk artık
    # KULLANICININ tank sıcaklığından, tank blowdown bloğunun okuduğu AYNI
    # doygunluk modelinden çözülüyor; alan verilmediğinde modülün ilan
    # ettiği ``TANK_TEMPERATURE_DEFAULT_K`` uygulanıyor. Bu bekçinin
    # iddiası "üç kanal AYNI sıcaklıkta bit-aynı sayı verir"dir; sayı
    # burada YENİDEN SEÇİLMEZ, ürünün ilan ettiği sıcaklık okunur — yoksa
    # bekçi ikinci bir kaynak olurdu. Ölçüldü: üçü de 785,1039703874175.
    from hrma.engines.hybrid_rocket_engine import TANK_TEMPERATURE_DEFAULT_K

    motor = _sessiz(HybridRocketEngine, thrust=1000, burn_time=10,
                    of_ratio=6.0, chamber_pressure=20, oxidizer_type='n2o')
    assert _sessiz(motor._get_oxidizer_density) == get_oxidizer_density(
        'n2o', TANK_TEMPERATURE_DEFAULT_K), (
        'hibrit motor ile app aynı sıcaklıkta ayrışıyor')

    # Kanalın GERÇEKTEN bağlı olduğu ayrıca ölçülür: kullanıcı sıcaklığı
    # verdiğinde motor o sıcaklığın sayısını üretmeli (sabit değil).
    for T_tank in (283.15, 293.15, 303.15):
        m2 = _sessiz(HybridRocketEngine, thrust=1000, burn_time=10,
                     of_ratio=6.0, chamber_pressure=20, oxidizer_type='n2o',
                     tank_temperature=T_tank)
        assert _sessiz(m2._get_oxidizer_density) == get_oxidizer_density(
            'n2o', T_tank), (
            f'{T_tank} K: motor tank sıcaklığını okumuyor (sabite döndü)')


def test_c4_kalan_yayilim_YALNIZ_sicaklik_etiketi():
    """Kalan fark sıcaklık etiketidir ve %6'nın altındadır (eskiden %22,2).

    Kanon sıcaklık kararı (293,15 K sorgusu ⟷ 298,15 K depolama durumu)
    Berke'de; bu bekçi kararı ÖNCELEMEZ, yalnız yayılımın büyümesini
    yasaklar.
    """
    from hrma.app import get_oxidizer_density

    dusuk = float(get_oxidizer_density('n2o', 293.15))
    yuksek = float(get_oxidizer_density('n2o', 298.15))
    # Ölçülen çift (27 Ağu). Kanon sıcaklık kararı verildiğinde bu iddia
    # kırmızıya döner — istenen budur: karar bekçiye YAZILARAK kapanır.
    assert dusuk == pytest.approx(785.1039703874175, rel=1e-9)
    assert yuksek == pytest.approx(742.9329783382176, rel=1e-9)
    yayilim = abs(dusuk / yuksek - 1.0)
    assert yayilim < 0.06, (
        f'N₂O kanalları arası yayılım %{100 * yayilim:.2f} — 293,15 K '
        f'{dusuk:.4f}, 298,15 K {yuksek:.4f}; P14H1-C2 ayrışması geri '
        f'büyüyor')


# ===========================================================================
# D — P15B3-07: rozeti BESLEYEN uç verisi (JS ayağı A2 paketinde)
# ===========================================================================
#: ``liquid.html::propellantProvenance`` canlılık ölçütü (birebir).
CANLI_DESEN = re.compile(r'pubchem|webbook|nist\.gov', re.I)


@pytest.mark.parametrize('ad,tur', (('rp1', 'liquid_fuel'),
                                    ('htpb', 'hybrid_fuel'),
                                    ('n2o4', 'oxidizer')))
def test_d1_yerel_tablo_yolu_ROZETI_KAZANAMIYOR(istemci, ad, tur):
    """Yerel tablo künyesi canlı desene UYMAZ -> yeşil rozet kazanılamaz."""
    govde = _sessiz(_uc_ozellikleri, istemci, ad, tur)
    kaynak = str(govde.get('source') or '')
    assert kaynak, f'{ad}: kaynak künyesi boş'
    assert not CANLI_DESEN.search(kaynak), (
        f'{ad}: yerel tablo değeri canlı kaynak gibi künyeleniyor -> '
        f'{kaynak!r}')
    assert (govde['properties'] or {}).get('storage_state') is None, (
        f'{ad}: hâl çözümü yokken storage_state basılıyor; rozet kapısı '
        f'buna bakıyor')


def test_d2_katkisiz_CoolProp_kunyesi_DUZELTILIYOR(istemci):
    """RP-1'de CoolProp tek sayı üretmez; künye yerel tabloya döner."""
    govde = _sessiz(_uc_ozellikleri, istemci, 'rp1', 'liquid_fuel')
    ozellikler = govde['properties'] or {}
    assert str(govde['source']) == 'NASA RP-1 Specification'
    assert not str(ozellikler.get('data_source', '')).startswith('CoolProp'), (
        'RP-1 CoolProp künyesiyle sunuluyor ama CoolProp bu akışkanı '
        'tanımıyor')
    assert ozellikler.get('density') == 810


@pytest.mark.parametrize('ad,tanim', (('n2o', 'saturated liquid at 293 K'),
                                      ('lox', 'saturated liquid at NBP')))
def test_d3_hal_cozumlu_deger_DURUMUNU_soyluyor(istemci, ad, tanim):
    """Rozet ancak hâl çözümlü sayıda yeşile döner; durum ADIYLA gelir."""
    govde = _sessiz(_uc_ozellikleri, istemci, ad, 'oxidizer')
    durum = (govde['properties'] or {}).get('storage_state') or {}
    assert tanim in str(durum.get('description')), (
        f'{ad}: hâl künyesi {durum!r}')
    assert isinstance(durum.get('state_temperature_K'), float)
    assert isinstance((govde['properties'] or {}).get('density'), float)


# ===========================================================================
# E — P15B4-07: iki ``case_design`` bloğu AYNI cümleyi kuruyor
# ===========================================================================
#: Ortak künye çekirdeği (``solid_rocket_engine._case_design_report``).
ORTAK_KASA_ALANLARI = {
    'material', 'yield_strength_mpa', 'design_safety_factor',
    'wall_thickness_mm', 'thickness_source', 'wall_thickness_requested_mm',
    'wall_thickness_hoop_required_mm', 'wall_thickness_manufacturing_floor_mm',
    'wall_thickness_at_minimum_clamp', 'wall_thickness_below_manufacturing_floor',
}

#: ``openrocket_integration`` ve ``motor_geometry``nin okuduğu eski adlar.
TUKETICI_ALANLARI = ('wall_thickness', 'outer_diameter', 'inner_diameter',
                     'length')


def kati_kos(istemci):
    """Üç cidar değeriyle ``/calculate_solid``.

    Düz işlev olarak durur ki mutasyon kanıtı koşumları (fikstür düzeneği
    olmadan) aynı ölçümü yeniden üretebilsin.
    """
    out = {}
    for etiket, cidar in (('yok', None), ('3.0', 3.0), ('8.0', 8.0)):
        govde = dict(KATI_YUKU)
        if cidar is not None:
            govde['case_thickness'] = cidar
        yanit = _sessiz(istemci.post, '/calculate_solid', json=govde,
                        headers=HEADERS)
        assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
        out[etiket] = yanit.get_json()
    return out


@pytest.fixture(scope='module')
def kati_yanitlar(istemci):
    return kati_kos(istemci)


@pytest.mark.parametrize('etiket', ('yok', '3.0', '8.0'))
def test_e1_iki_blok_KESISIMDE_celismiyor(kati_yanitlar, etiket):
    """Kesişim 10 alan, çelişen değer 0 (eskiden kesişim TEK alandı)."""
    yanit = kati_yanitlar[etiket]
    ozet = (yanit.get('design_summary') or {}).get('case_design') or {}
    cad = (yanit.get('cad_design') or {}).get('case_design') or {}

    assert ORTAK_KASA_ALANLARI <= set(ozet), (
        f'design_summary.case_design künye çekirdeğini kaybetti: '
        f'{sorted(ORTAK_KASA_ALANLARI - set(ozet))}')
    assert ORTAK_KASA_ALANLARI <= set(cad), (
        f'cad_design.case_design künye çekirdeğini kaybetti: '
        f'{sorted(ORTAK_KASA_ALANLARI - set(cad))}')

    catisma = {k: (ozet[k], cad[k]) for k in (set(ozet) & set(cad))
               if ozet[k] != cad[k]}
    assert not catisma, (
        f'aynı yanıtta iki case_design bloğu çelişiyor: {catisma}')


@pytest.mark.parametrize('etiket,beklenen,cidar', (
    ('yok', 'hoop_stress_sized', 2.4000000000000004),
    ('3.0', 'user_entered', 3.0),
    ('8.0', 'user_entered', 8.0),
))
def test_e2_thickness_source_IKI_BLOKTA_DA_dogru(kati_yanitlar, etiket,
                                                 beklenen, cidar):
    """Cidarın kaynağı imalata giden blokta da yazılı."""
    yanit = kati_yanitlar[etiket]
    for yol in ('design_summary', 'cad_design'):
        blok = (yanit.get(yol) or {}).get('case_design') or {}
        assert blok.get('thickness_source') == beklenen, (
            f'{yol}.case_design.thickness_source = '
            f'{blok.get("thickness_source")!r}, beklenen {beklenen!r}')
        assert blok.get('wall_thickness_mm') == pytest.approx(cidar, rel=1e-9)


def test_e3_eski_TUKETICI_alanlari_kirilmadi(kati_yanitlar):
    """Ortak çekirdek, eski okuyucuların alanlarını silmedi."""
    cad = (kati_yanitlar['3.0'].get('cad_design') or {}).get('case_design') or {}
    for alan in TUKETICI_ALANLARI:
        assert alan in cad, (
            f'cad_design.case_design.{alan} kayboldu — '
            f'openrocket_integration/motor_geometry bu adı okuyor')
    assert cad['wall_thickness'] == pytest.approx(cad['wall_thickness_mm'],
                                                 rel=1e-9), (
        'aynı blokta cidar iki ayrı sayı: '
        f'{cad["wall_thickness"]!r} ⟷ {cad["wall_thickness_mm"]!r}')


# ===========================================================================
# F — P15B4-10: ön kapak da cidar gibi TEK çözümleyiciden
# ===========================================================================
def yapisal_kos(istemci):
    yanit = _sessiz(istemci.post, '/analyze_structural_safety',
                    json=YAPISAL_YUKU, headers=HEADERS)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    return yanit.get_json()


@pytest.fixture(scope='module')
def yapisal_yanit(istemci):
    return yapisal_kos(istemci)


def test_f1_analiz_VARSA_kapak_analizden_geliyor(yapisal_yanit):
    """Kapak kalınlığı 8,0 sabiti değil, analizin düz kapak değeridir."""
    from hrma.export.cad_visualization import _front_cap_design

    kapak = _front_cap_design(yapisal_yanit, wall_mm=5.0, bore_radius_mm=50.0)
    assert kapak['from_analysis'] is True
    assert kapak['thickness_mm'] == pytest.approx(12.646962171759395,
                                                  rel=1e-9), (
        f'kapak analizden gelmiyor: {kapak["thickness_mm"]!r}')
    assert kapak['thickness_mm'] != pytest.approx(8.0, rel=1e-6), (
        'imalat kapağı yine 8,0 mm sabitine düştü (P15B4-10)')
    kunye = str(kapak['source'])
    assert 'structural analysis' in kunye and 'end_cap_analysis' in kunye
    # Analiz DİŞBÜKEY öneriyorsa fark saklanmaz.
    if kapak['recommended_type'] == 'dished':
        assert 'DISHED' in kunye and 'FLAT' in kunye, (
            f'dişbükey/düz farkı künyede yok: {kunye}')


@pytest.mark.parametrize('cidar,yaricap,beklenen', (
    (5.0, 50.0, 8.0),      # taban: 1,6x5 = 8,0 ile aynı, zemin bağlar
    (2.0, 50.0, 8.0),      # zemin (CAP_FALLBACK_MIN_MM)
    (20.0, 50.0, 23.0),    # tavan: 0,3x50 + 8
))
def test_f2_analiz_YOKSA_kalinlik_TEK_KURALDAN_ve_ASSUMED(cidar, yaricap,
                                                          beklenen):
    """Yedek kural tek yerde tanımlı ve varsayım olduğu ADIYLA beyanlı."""
    from hrma.export.cad_visualization import (CAP_FALLBACK_BASIS,
                                               CAP_FALLBACK_MIN_MM,
                                               CAP_FALLBACK_RADIUS_FRACTION,
                                               CAP_FALLBACK_WALL_MULTIPLIER,
                                               _front_cap_design)

    kapak = _front_cap_design({}, wall_mm=cidar, bore_radius_mm=yaricap)
    kural = min(max(CAP_FALLBACK_WALL_MULTIPLIER * cidar, CAP_FALLBACK_MIN_MM),
                CAP_FALLBACK_RADIUS_FRACTION * yaricap + CAP_FALLBACK_MIN_MM)
    assert kapak['thickness_mm'] == pytest.approx(kural, rel=1e-12)
    assert kapak['thickness_mm'] == pytest.approx(beklenen, rel=1e-9)
    assert kapak['from_analysis'] is False
    assert kapak['source'] == CAP_FALLBACK_BASIS
    assert 'ASSUMED' in CAP_FALLBACK_BASIS
    assert 'NOT a pressure-vessel head calculation' in CAP_FALLBACK_BASIS


def test_f3_cozulemeyen_kapak_UYDURULMUYOR():
    """Yarıçap yoksa kalınlık None + 'not available' (fail-closed)."""
    from hrma.export.cad_visualization import _front_cap_design

    kapak = _front_cap_design({}, wall_mm=5.0, bore_radius_mm=None)
    assert kapak['thickness_mm'] is None
    assert kapak['source'] == 'not available'


def test_f4_STEP_kapagi_AYNI_cozumleyiciden_ve_kunyeyi_TASIYOR():
    """İmalat STEP'i kendi 8,0'ını yazmaz; çözümleyiciyi çağırır."""
    kaynak = _kaynak(STEP_PY)
    assert '_front_cap_design(md, wall_mm=wall, bore_radius_mm=rc)' in kaynak, (
        'step_export ön kapağı tek çözümleyiciden almıyor')
    assert "cap_design['source']" in kaynak, (
        'kapak künyesi STEP notlarına inmiyor')
    assert re.search(r"closure head \{cap:\.2f\} mm - \{cap_design\['source'\]\}",
                     kaynak), 'STEP notu kalınlık + künye çiftini basmıyor'
    assert 'undeclared head' in kaynak, (
        'çözülemeyen kapakla STEP üretimi reddedilmiyor (fail-closed metni yok)')


# ===========================================================================
# G / H — cidar künyesi matrisi (P15S1-01) ve iki uçtaki kapı (P15S1-02)
# ===========================================================================
NAN = float('nan')
INF = float('inf')
YOK = object()

#: (etiket, ham değer). ``/calculate`` alanı MİLİMETRE, ``/analyze_structural
#: _safety`` METRE okur — sayısal satırlar ikinci uca 1/1000 ile gider ki
#: karşılaştırılan şey AYNI FİZİKSEL CİDAR olsun.
CIDAR_MATRISI = (
    ('alan yok', YOK),
    ("bos dize", ''),
    ('None', None),
    ("'abc'", 'abc'),
    ("'5,0' TR ondalik", '5,0'),
    ("'5.0' dize", '5.0'),
    ('sifir', 0),
    ('negatif', -5),
    ('True', True),
    ('liste', [5]),
    ('NaN', NAN),
    ('Infinity', INF),
    ('5 mm', 5),
    ('0.05 mm', 0.05),
    ('500 mm', 500),
)

#: P15S1-01'in birebir yalanı.
YALAN_CUMLE = 'No wall thickness was supplied'

#: Değer GERÇEKTEN gönderilen satırlar (künye "gönderilmedi" diyemez).
DEGER_GONDERILEN = {e for e, d in CIDAR_MATRISI
                    if d is not YOK and d not in ('', None)}


def matris_kos(istemci):
    """İki uçta 15 satırlık cidar matrisi (düz işlev — mutasyon koşumu da çağırır)."""
    satirlar = []
    for etiket, deger in CIDAR_MATRISI:
        hesap = dict(HIBRIT_YUKU)
        if deger is not YOK:
            hesap['wall_thickness'] = deger
        r1 = _sessiz(istemci.post, '/calculate', json=hesap, headers=HEADERS)
        j1 = r1.get_json() if r1.status_code == 200 else {}
        temel = (j1 or {}).get('structural_design_basis') or {}

        yapisal = dict(YAPISAL_YUKU)
        if deger is not YOK:
            if isinstance(deger, bool) or not isinstance(deger, (int, float)):
                yapisal['wall_thickness'] = deger
            elif math.isfinite(deger):
                yapisal['wall_thickness'] = deger / 1000.0
            else:
                yapisal['wall_thickness'] = deger
        r2 = _sessiz(istemci.post, '/analyze_structural_safety', json=yapisal,
                     headers=HEADERS)
        j2 = r2.get_json() if r2.status_code == 200 else {}
        temel2 = (j2 or {}).get('design_basis') or {}

        satirlar.append({
            'etiket': etiket,
            'calculate': {'kod': r1.status_code, **temel},
            'yapisal': {'kod': r2.status_code, **temel2},
        })
    return satirlar


@pytest.fixture(scope='module')
def cidar_matrisi(istemci):
    return matris_kos(istemci)


def test_g1_deger_gonderildiginde_kunye_GONDERILMEDI_DEMIYOR(cidar_matrisi):
    """P15S1-01'in birebir kendisi: 11 girdinin 5'i yalan söylüyordu."""
    yalanlar = [s['etiket'] for s in cidar_matrisi
                if s['etiket'] in DEGER_GONDERILEN
                and YALAN_CUMLE in str(s['calculate'].get('message'))]
    assert not yalanlar, (
        'cidar künyesi değer gönderilmişken "gönderilmedi" diyor: '
        f'{yalanlar}')


def test_g2_TR_ondalik_ADIYLA_reddediliyor(cidar_matrisi):
    """``'5,0'`` okunamadı diye ADLANDIRILIR ve nedeni söylenir."""
    from hrma.app import WALL_GATE_NOT_APPLIED, WALL_INPUT_UNREADABLE

    satir = next(s for s in cidar_matrisi
                 if s['etiket'] == "'5,0' TR ondalik")['calculate']
    assert satir['wall_thickness_input_status'] == WALL_INPUT_UNREADABLE
    assert satir['wall_thickness_source'] == WALL_GATE_NOT_APPLIED
    assert satir['is_verification'] is False
    assert satir['verdict'] == 'withheld'
    mesaj = str(satir['message'])
    assert 'decimal separator' in mesaj and '5.0, not 5,0' in mesaj, (
        f'kullanıcıya ondalık ayracı söylenmiyor: {mesaj[:200]}')


def test_g3_GONDERILMEDI_ile_OKUNAMADI_ayri_kaliyor(cidar_matrisi):
    """Helper'ın sildiği ayrım künyede duruyor."""
    from hrma.app import (WALL_GATE_SIZED, WALL_INPUT_NOT_FINITE,
                          WALL_INPUT_NOT_POSITIVE, WALL_INPUT_NOT_SUPPLIED,
                          WALL_INPUT_OK, WALL_INPUT_UNREADABLE)

    beklenen = {
        'alan yok': WALL_INPUT_NOT_SUPPLIED,
        'bos dize': WALL_INPUT_NOT_SUPPLIED,
        'None': WALL_INPUT_NOT_SUPPLIED,
        "'abc'": WALL_INPUT_UNREADABLE,
        "'5,0' TR ondalik": WALL_INPUT_UNREADABLE,
        "'5.0' dize": WALL_INPUT_OK,
        'sifir': WALL_INPUT_NOT_POSITIVE,
        'negatif': WALL_INPUT_NOT_POSITIVE,
        'True': WALL_INPUT_UNREADABLE,
        'liste': WALL_INPUT_UNREADABLE,
        'NaN': WALL_INPUT_NOT_FINITE,
        'Infinity': WALL_INPUT_NOT_FINITE,
        '5 mm': WALL_INPUT_OK,
        '0.05 mm': WALL_INPUT_OK,
        '500 mm': WALL_INPUT_OK,
    }
    olculen = {s['etiket']: s['calculate'].get('wall_thickness_input_status')
               for s in cidar_matrisi}
    assert olculen == beklenen, f'girdi durum matrisi kaydı: {olculen}'

    # "Alan hiç gelmedi" -> HRMA boyutlandırdı; bu tek dal ONU söyler.
    for etiket in ('alan yok', 'bos dize', 'None'):
        satir = next(s for s in cidar_matrisi
                     if s['etiket'] == etiket)['calculate']
        assert satir['wall_thickness_source'] == WALL_GATE_SIZED
        assert YALAN_CUMLE in str(satir['message']), (
            'cidar GERÇEKTEN gönderilmediğinde dürüst cümle kurulmalı')


def test_g4_okuyucu_ayrimi_TEK_YERDE_tanimli():
    """``_mm_to_m_read`` birim sözleşmesi: değer + NEDEN birlikte döner."""
    from hrma.app import (WALL_INPUT_NOT_FINITE, WALL_INPUT_NOT_POSITIVE,
                          WALL_INPUT_NOT_SUPPLIED, WALL_INPUT_OK,
                          WALL_INPUT_UNREADABLE, _mm_to_m_optional,
                          _mm_to_m_read)

    assert _mm_to_m_read(None) == (None, WALL_INPUT_NOT_SUPPLIED)
    assert _mm_to_m_read('') == (None, WALL_INPUT_NOT_SUPPLIED)
    assert _mm_to_m_read('5,0') == (None, WALL_INPUT_UNREADABLE)
    assert _mm_to_m_read(True) == (None, WALL_INPUT_UNREADABLE)
    assert _mm_to_m_read([5]) == (None, WALL_INPUT_UNREADABLE)
    assert _mm_to_m_read(0) == (None, WALL_INPUT_NOT_POSITIVE)
    assert _mm_to_m_read(-5) == (None, WALL_INPUT_NOT_POSITIVE)
    assert _mm_to_m_read(INF) == (None, WALL_INPUT_NOT_FINITE)
    assert _mm_to_m_read(5) == (0.005, WALL_INPUT_OK)
    # Eski sarmalayıcı hâlâ ayrımı SİLİYOR — künye üreten çağıran onu
    # kullanmamalı; bu iddia kökün geri gelmesini yasaklar.
    assert _mm_to_m_optional('5,0') is _mm_to_m_optional('') is None
    kaynak = _kaynak(APP_PY)
    assert '_mm_to_m_read(data.get(\'wall_thickness\'))' in kaynak, (
        '/calculate cidarı yine ayrımı silen sarmalayıcıdan okuyor')


# --- H: iki uç, tek sınıflandırıcı ----------------------------------------
#: 200/200 dönen satırlarda BİLİNEN ve gerekçesi yazılı iki ayrışma.
#: Bunlar sınıflandırma farkı DEĞİL: ``sifir`` ikinci uçta panel sentineli
#: sayılıyor, ``0.05 mm`` ise ikinci ucun kabul bandına giriyor.
#: Tekilleştirme kararı Berke'de; bekçi ÜÇÜNCÜSÜNÜ yasaklar.
BILINEN_AYRISMALAR = {'sifir', '0.05 mm'}


def test_h1_ucuncu_durum_HER_IKI_UCTA_ateşliyor(cidar_matrisi):
    """Fail-closed üçüncü sınıf artık yapısal uçta da doğuyor."""
    from hrma.app import WALL_GATE_NOT_APPLIED

    negatif = next(s for s in cidar_matrisi if s['etiket'] == 'negatif')
    assert negatif['calculate']['wall_thickness_source'] == WALL_GATE_NOT_APPLIED
    assert negatif['yapisal']['kod'] == 200
    assert negatif['yapisal']['wall_thickness_source'] == WALL_GATE_NOT_APPLIED, (
        'üçüncü durum /analyze_structural_safety rotasında hâlâ ateşlemiyor '
        '(P15S1-02 kusurunun kendisi)')
    assert negatif['yapisal']['is_verification'] is False
    assert negatif['yapisal']['verdict'] == 'withheld'


def test_h2_iki_ucta_kapi_sinifi_AYRISMIYOR(cidar_matrisi):
    """200/200 satırlarda sınıf eşliği; iki bilinen istisna ADIYLA."""
    ayrisanlar = set()
    for satir in cidar_matrisi:
        if satir['calculate'].get('kod') != 200:
            continue
        if satir['yapisal'].get('kod') != 200:
            continue          # ikinci uç REDDETTİ — sınıflandırma farkı değil
        if (satir['calculate'].get('wall_thickness_source')
                != satir['yapisal'].get('wall_thickness_source')):
            ayrisanlar.add(satir['etiket'])

    assert ayrisanlar == BILINEN_AYRISMALAR, (
        'iki uçtaki kapı sınıfı beklenmeyen satırlarda ayrışıyor: '
        f'{sorted(ayrisanlar ^ BILINEN_AYRISMALAR)} '
        '(yeni ayrışma doğduysa onarılmalı; bilinen ikisi kapatıldıysa '
        'BILINEN_AYRISMALAR güncellenmeli)')


def test_h3_sinifla_hukum_HER_UCTA_TUTARLI(cidar_matrisi):
    """Sınıf ile hüküm aynı satırda çelişemez (uçlar ayrı olsa bile)."""
    from hrma.app import WALL_GATE_NOT_APPLIED, WALL_GATE_SIZED

    for satir in cidar_matrisi:
        for uc in ('calculate', 'yapisal'):
            veri = satir[uc]
            if veri.get('kod') != 200 or not veri.get('wall_thickness_source'):
                continue
            if veri['wall_thickness_source'] in (WALL_GATE_SIZED,
                                                 WALL_GATE_NOT_APPLIED):
                assert veri.get('is_verification') is False, (
                    f'{satir["etiket"]}/{uc}: cidar kullanıcının değil ama '
                    f'sonuç doğrulama sayılıyor')
                assert veri.get('verdict') == 'withheld', (
                    f'{satir["etiket"]}/{uc}: kazanılmamış hüküm veriliyor '
                    f'({veri.get("verdict")!r})')


def test_h4_panel_rozeti_UC_DURUMLU(cidar_matrisi):
    """Panel sınıflandırıcısı iki değerli kalamaz (rozet yarısı)."""
    kaynak = _kaynak(PANEL_JS)
    assert "src === 'sized_by_hrma'" in kaynak
    assert "src === 'user_supplied' && db.is_verification !== false" in kaynak, (
        'panel "kullanıcının cidarı" rozetini doğrulama bayrağına '
        'bağlamıyor')
    assert "U.badge('wall_thickness_source: ' + src, 'err'" in kaynak, (
        'üçüncü durum kendi (kırmızı) rozetini almıyor — bilinmeyen sınıf '
        'yeşil "AS SUPPLIED" rozetine düşüyor (OH-Z2-06)')
