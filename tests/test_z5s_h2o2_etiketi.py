"""ÖH Z5S — H₂O₂ %98 KAYIT ETİKETİ ile DEĞERİ TUTUYOR MU?

Karar #3 (28 Ağustos 2026, Berke-delegasyonlu). Kapatılan kusur: merkezî
tablodaki ``'h2o2'`` kaydı ``'Hydrogen Peroxide (98%)'`` etiketini ve
``'concentration': 98`` alanını taşırken **%100 saf** H₂O₂'nin 20 °C
yoğunluğunu (1450 ≈ 1449,9) tutuyordu. Sayı gerçekti, **etiket yanlıştı** —
ve kayıt kendi künyesini yalanlıyordu, çünkü
``external_data_fetcher.oxidizer_reference_density`` bu değeri
AFRPL'in *%98 çözelti* künyesiyle damgalayıp dışarı veriyordu.

Bu dosya ürün koduna DOKUNMAZ; iki şeyi kilitler:

1. **Etiket-değer tutarlılığı** — kaydın ``concentration`` alanı ne diyorsa
   yoğunluğu o konsantrasyonun referans değeri olmalı. %98 etiketi %100'ün
   değerini TAŞIYAMAZ. Konsantrasyon→yoğunluk karşılıkları deponun kendi
   araştırma kaydından gelir (``docs/arastirma/fizik/Z1-yogunluk-dogrulama.md``,
   AFRPL-TR-67-144 Böl. 2.2.2.1 denkleminden türetilmiş tablo) — bu dosya
   dışarıdan sayı İCAT ETMEZ.

2. **Yanlış-birleştirme bekçisi** — ``thermal_protection`` içindeki ablatif
   MX-4926 yoğunluğu da 1450 kg/m³'tür ve H₂O₂ ile **hiçbir ilgisi yoktur**.
   İki sayının çakışması tesadüftür. Kör bir arama-değiştirme (1450 → 1438,1)
   ablatifi de bozardı; bu bekçi onun bağımsız yaşadığını kanıtlar.

Ölçüm çıktıları: ``docs/scofield/raw/OH/Z5S/h2o2/``.
"""

import pytest


# ---------------------------------------------------------------------------
# AFRPL-TR-67-144 (Rocketdyne 1967) Böl. 2.2.2.1 denkleminden türetilen
# konsantrasyon -> yoğunluk [kg/m³] @ 293,15 K karşılıkları. Sayılar deponun
# KENDİ araştırma kaydındaki tablodan okunur (Z1-yogunluk-dogrulama.md);
# burada yeniden literatür taraması YAPILMAZ.
# ---------------------------------------------------------------------------
AFRPL_293K = {
    90: 1392.3,
    95: 1420.7,
    98: 1438.1,
    100: 1449.9,   # SAF H₂O₂ — '%98' etiketli kaydın taşıyamayacağı değer
}

#: Ablatif MX-4926 yoğunluğu [kg/m³] — H₂O₂'den BAĞIMSIZ büyüklük.
ABLATIF_MX4926 = 1450.0


def _h2o2_kaydi():
    from hrma.data.propellant_database import PropellantDatabase
    kayit = PropellantDatabase().get_propellant_properties('h2o2')
    assert kayit, "merkezî tabloda 'h2o2' kaydı yok"
    return kayit


# ===========================================================================
# 1) ETİKET <-> DEĞER TUTARLILIĞI
# ===========================================================================

def test_a1_konsantrasyon_alani_ile_yogunluk_TUTUYOR():
    """Kaydın ``concentration`` alanı hangi çözeltiyi diyorsa yoğunluk odur."""
    kayit = _h2o2_kaydi()
    w = kayit.get('concentration')

    assert w in AFRPL_293K, (
        f'h2o2 kaydının konsantrasyonu ({w!r}) referans tablosunda yok; '
        f'bilinen değerler: {sorted(AFRPL_293K)}')

    beklenen = AFRPL_293K[w]
    rho = float(kayit['density'])
    assert rho == pytest.approx(beklenen, rel=1e-4), (
        f'ETİKET-DEĞER ÇELİŞKİSİ: kayıt %{w} diyor ama yoğunluğu {rho} '
        f'kg/m³; %{w} çözeltinin 293,15 K değeri {beklenen} kg/m³. '
        'Sayı ile etiket aynı çözeltiyi göstermek ZORUNDA.')


def test_a2_yuzde98_etiketi_SAF_H2O2_degerini_TASIYAMAZ():
    """Asıl kusurun kilidi: %98 kaydı %100'ün (1449,9 ≈ 1450) değerini tutamaz.

    Bu, ``test_a1``in özel hâli değil, onun ters yönden ifadesidir: a1 doğru
    değeri talep eder, a2 kusurun TAM O HÂLİNİN geri gelmesini yasaklar.
    """
    kayit = _h2o2_kaydi()
    rho = float(kayit['density'])
    saf = AFRPL_293K[100]

    assert kayit.get('concentration') == 98, (
        'bu bekçi %98 kaydını korur; kaydın konsantrasyonu değiştiyse '
        'bekçi de bilinçli olarak güncellenmelidir')
    assert '98' in str(kayit.get('name', '')), (
        f"kaydın adı %98 demiyor: {kayit.get('name')!r}")
    assert rho != pytest.approx(saf, rel=1e-3), (
        f'GERİLEME: %98 etiketli kayıt yine SAF H₂O₂ değerini ({saf}) '
        f'taşıyor. 1450 kg/m³ %100 saf H₂O₂’nin 20 °C değeridir, %98’in '
        'değil — sayı gerçek, etiket yanlış olur.')


def test_a3_kunye_kaynak_soyluyor_ve_degerle_ayni_cozeltiyi_gosteriyor():
    """Dışarı verilen künye AFRPL'i ve %98'i adlandırır; değer onunla tutar."""
    from hrma.data.external_data_fetcher import oxidizer_reference_density

    veri = oxidizer_reference_density('h2o2', 293.15)
    kunye = str(veri['source'])

    assert 'AFRPL-TR-67-144' in kunye, (
        f'yoğunluk künyesi kaynağını adlandırmıyor: {kunye}')
    assert '98' in kunye, (
        f'künye hangi çözeltiyi anlattığını söylemiyor: {kunye}')
    # Künyenin İDDİA ettiği çözelti ile SAYININ ait olduğu çözelti aynı olmalı.
    assert veri['density'] == pytest.approx(AFRPL_293K[98], rel=1e-4), (
        f"künye '%98 çözelti' diyor ama sayı {veri['density']} kg/m³ — "
        f'%98’in değeri {AFRPL_293K[98]} kg/m³.')


def test_a4_yogunluk_zarfin_icinde():
    """Yeni değer h2o2 geçerlilik zarfını ihlal etmiyor (fail-closed korunur)."""
    from hrma.data.external_data_fetcher import OXIDIZER_DENSITY_ENVELOPE

    lo, hi = OXIDIZER_DENSITY_ENVELOPE['h2o2']
    rho = float(_h2o2_kaydi()['density'])
    assert lo <= rho <= hi, (
        f'h2o2 yoğunluğu {rho} kg/m³ zarfın ([{lo}, {hi}]) dışında')


# ===========================================================================
# 2) YANLIŞ-BİRLEŞTİRME BEKÇİSİ — ablatif 1450 H₂O₂'den BAĞIMSIZ yaşar
# ===========================================================================

def test_b1_ablatif_mx4926_yogunlugu_H2O2den_BAGIMSIZ():
    """Kör arama-değiştirme bekçisi: ablatif 1450 kg/m³ yerinde durmalı.

    MX-4926 karbon-fenolik ablatif yoğunluğu ile H₂O₂ çözelti yoğunluğunun
    ikisinin de 1450 olması TESADÜFTÜR. H₂O₂ onarımı yapılırken ablatife
    dokunulduysa bu test kırmızıya döner.
    """
    from hrma.analysis.thermal_protection import ABLATIVE_MATERIALS

    kayit = ABLATIVE_MATERIALS['carbon_phenolic']
    assert kayit['density_kg_m3'] == pytest.approx(ABLATIF_MX4926, rel=1e-9), (
        f"ablatif MX-4926 yoğunluğu {kayit['density_kg_m3']} kg/m³ olmuş; "
        f'{ABLATIF_MX4926} olmalıydı. H₂O₂ onarımı sırasında KÖR bir '
        'arama-değiştirme bu satıra da dokunmuş olabilir — ablatif '
        'malzeme yoğunluğunun H₂O₂ ile ilgisi YOKTUR.')
    assert 'MX-4926' in str(kayit.get('name', '')), (
        'ablatif kaydın kimliği değişmiş')


def test_b2_iki_sayi_artik_AYRISIYOR():
    """Onarımdan sonra iki büyüklük sayısal olarak da ayrışmış olmalı.

    Çakışma bittiği için gelecekteki bir ``1450`` taraması artık H₂O₂'yi
    yanlışlıkla yakalayamaz — bu, kusurun tekrarını yapısal olarak zorlaştırır.
    """
    from hrma.analysis.thermal_protection import ABLATIVE_MATERIALS

    h2o2 = float(_h2o2_kaydi()['density'])
    ablatif = float(ABLATIVE_MATERIALS['carbon_phenolic']['density_kg_m3'])
    assert h2o2 != pytest.approx(ablatif, rel=1e-6), (
        f'H₂O₂ ({h2o2}) ile ablatif ({ablatif}) yoğunlukları yine aynı '
        'sayıya düşmüş; ikisi ilgisiz büyüklüktür ve çakışmaları '
        'kör arama-değiştirmeyi tekrar mümkün kılar.')


# ===========================================================================
# 3) TÜKETİCİ ZİNCİRİ — değer gerçekten aşağı iniyor
# ===========================================================================

def test_c1_enjektor_kanali_yeni_degeri_goruyor():
    """InjectorDesign merkezî tablodan okuyor; kendi kopyasını tutmuyor."""
    import contextlib
    import io

    from hrma.utils.injector_design import InjectorDesign

    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        tasarim = InjectorDesign(mdot_ox=1.0, chamber_pressure=20,
                                 oxidizer_type='h2o2', tank_pressure=50,
                                 oxidizer_temp=293.15)

    assert tasarim.rho_ox == pytest.approx(AFRPL_293K[98], rel=1e-4), (
        f'enjektör kanalı {tasarim.rho_ox} kg/m³ görüyor; merkezî tablo '
        f'{AFRPL_293K[98]} diyor — kanal kendi kopyasını tutuyor olabilir.')
