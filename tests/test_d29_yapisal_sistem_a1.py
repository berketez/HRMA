# -*- coding: utf-8 -*-
"""ÖH D29 · yapisal-sistem a1 — OH-D28-08 bekçisi.

KALEM: "HTPB-N2O için TNT eşdeğeri literatürsüz: /analyze_safety ürünün
başlıca hibrit yakıtı htpb'yi TNT tablosunda bulamıyor."

ÖLÇÜLEN KUSUR (taban ``4dc63c11``,
``docs/scofield/raw/OH/D29/yapisal-sistem/a1/once.json``): hibrit motorun
patlayıcı hükmü ``MOTOR_TYPE_TO_EXPLOSIVE_CLASS['hybrid'] =
'liquid_biprop'`` üzerinden LOX/RP-1 SIVI ÇİFT-İTİCİSİNİN sayısını (0,35)
ödünç alıyordu; ürünün beş hibrit yakıtının hiçbiri tabloda yoktu ve
``'htpb'`` ile ``'sihir'`` birebir aynı üç sayıyı üretiyordu.

ONARIM: hibritin TNT eşdeğeri OKSİTLEYİCİNİN ayrışma entalpisinden
TÜRETİLİR (Karabeyoglu, Dyer, Stevens & Cantwell, "Modeling of N2O
Decomposition Events", AIAA 2008-4933, Denk. 2 ve 17). Sayı SEÇİLMEDİ:

    TNT_eq = (dH_G / M) / e_TNT ,   e_TNT = 1000 cal_th/g (TANIM)

Bu dosyanın en önemli bekçisi ``TestTuretimKalibreDegil``: türetim,
makalenin KENDİ yayımladığı iki özgül enerjiyi (N2O 446 cal/g, H2O2
689 cal/g) yeniden üretmek zorundadır. Üretmezse sayı literatürden değil
uydurmadan geliyor demektir.
"""
import ast
import pathlib

import pytest

from hrma.analysis.safety_analysis import (
    HYBRID_DEFAULT_OXIDIZER,
    HYBRID_EXPLOSIVE_CLASSES,
    HYBRID_INERT_FUEL_NAMES,
    HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL,
    HYBRID_OXIDIZER_MOLAR_MASS_G_PER_MOL,
    HYBRID_OXIDIZER_PUBLISHED_CAL_PER_G,
    MOTOR_TYPE_TO_EXPLOSIVE_CLASS,
    TNT_REFERENCE_CAL_PER_G,
    SafetyAnalyzer,
    hybrid_oxidizer_specific_energy_cal_g,
    hybrid_oxidizer_tnt_equivalent,
)
from hrma.app import app
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
MODUL = KOK / 'hrma' / 'analysis' / 'safety_analysis.py'

#: Kanonik ölçüm gövdesi — kardeş paketlerle AYNI motor (Z5S/s3 çapası,
#: ``tests/test_d28_app_api_a2.py::GUVENLIK``). Sayı yeniden seçilmez.
GUVENLIK = {
    'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
    'thrust': 1000.0, 'burn_time': 10.0, 'propellant_mass': 5.0,
    'chamber_diameter': 0.1, 'wall_thickness': 0.005,
    'material': 'steel_4130', 'motor_type': 'hybrid',
}

#: ÖLÇÜLEN değerler (once.json / sonra.json). Bunlar bu bekçinin çapasıdır.
ONCE_HTPB_FAKTOR = 0.35
ONCE_HTPB_TNT_KG = 1.75
ONCE_HTPB_OLDURUCU_M = 3.313262612359215
SONRA_HTPB_FAKTOR = 0.4455501783563947
SONRA_HTPB_TNT_KG = 2.2277508917819735
SONRA_HTPB_OLDURUCU_M = 3.590862032111756


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _yaprak_ara(dugum, ad):
    """Yanıt ağacındaki TÜM ``ad`` yapraklarının değerleri."""
    bulunan = []
    if isinstance(dugum, dict):
        for k, v in dugum.items():
            if k == ad:
                bulunan.append(v)
            bulunan.extend(_yaprak_ara(v, ad))
    elif isinstance(dugum, list):
        for v in dugum:
            bulunan.extend(_yaprak_ara(v, ad))
    return bulunan


class TestTuretimKalibreDegil:
    """Sayı literatürden TÜRETİLİYOR mu, yoksa seçilmiş mi?

    Doktrin 7: "kalibre ettim" kabul edilmez. Bu sınıf, türetimin
    makalenin kendi yayımladığı sayıları yeniden ürettiğini sınar —
    Kinney-Graham Z=1 doğrulama düğümüyle aynı ruhta bir çapraz kontrol.
    """

    @pytest.mark.parametrize('ox', sorted(HYBRID_OXIDIZER_PUBLISHED_CAL_PER_G))
    def test_turetim_makalenin_yayimladigi_ozgul_enerjiyi_URETIYOR(self, ox):
        yayimlanan = HYBRID_OXIDIZER_PUBLISHED_CAL_PER_G[ox]
        turetilen = hybrid_oxidizer_specific_energy_cal_g(ox)
        bagil = abs(turetilen - yayimlanan) / yayimlanan
        assert bagil < 2e-3, (
            '%s: türetim %.4f cal/g, makale %.1f cal/g (bağıl %.2e) — '
            'türetim literatürü yeniden üretmiyor, sayı kalibrasyona '
            'kaymış olabilir' % (ox, turetilen, yayimlanan, bagil))

    def test_tnt_referansi_TANIMDIR_olcum_degil(self):
        """1 g TNT = 1000 cal_th (NIST SP 811). Ayarlanabilir bir sayı değil."""
        assert TNT_REFERENCE_CAL_PER_G == 1000.0

    @pytest.mark.parametrize('ox', sorted(HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL))
    def test_esdeger_BOYUTSUZ_ve_bolmeyle_cikiyor(self, ox):
        """(kcal/mol ÷ g/mol) ÷ (cal/g) — kalori pay ve paydada sadeleşir."""
        beklenen = (1000.0
                    * HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL[ox]
                    / HYBRID_OXIDIZER_MOLAR_MASS_G_PER_MOL[ox]
                    / TNT_REFERENCE_CAL_PER_G)
        assert hybrid_oxidizer_tnt_equivalent(ox) == pytest.approx(
            beklenen, rel=1e-12)
        assert 0.0 < hybrid_oxidizer_tnt_equivalent(ox) < 1.0

    def test_sinif_faktoru_KAYNAKTA_LITERAL_OLARAK_YAZILI_DEGIL(self):
        """Doktrin 4 (tek kaynak): sayı ikinci kez yazılmaz, türetilir.

        Kaynaktaki HİÇBİR sayısal literal türetilmiş eşdeğere eşit
        olmamalı — eşitse biri elle kopyalanmış demektir.
        """
        agac = ast.parse(MODUL.read_text(encoding='utf-8'))
        literaller = [d.value for d in ast.walk(agac)
                      if isinstance(d, ast.Constant)
                      and isinstance(d.value, float)]
        for sinif, deger in HYBRID_EXPLOSIVE_CLASSES.items():
            for lit in literaller:
                assert abs(lit - deger) > 1e-6, (
                    '%s = %r kaynakta literal olarak da yazılmış (%r): '
                    'tek kaynak bozuldu' % (sinif, deger, lit))

    def test_tablosuz_oksitleyici_icin_sayi_UYDURULMAZ(self):
        """Fail-closed: bilinmeyen oksitleyici için eşdeğer üretilmez."""
        with pytest.raises(KeyError):
            hybrid_oxidizer_tnt_equivalent('unobtainium')


class TestTekKaynak:
    """Türetimin dayandığı ürün gerçekleri başka dosyalarla ayrışmasın."""

    def test_varsayilan_oksitleyici_MOTORUN_varsayilaniyla_ayni(self):
        import inspect

        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        imza = inspect.signature(HybridRocketEngine.__init__)
        motorun = imza.parameters['oxidizer_type'].default
        assert str(motorun).strip().lower() == HYBRID_DEFAULT_OXIDIZER, (
            'HYBRID_DEFAULT_OXIDIZER (%r) motorun varsayılanından (%r) '
            'ayrışmış' % (HYBRID_DEFAULT_OXIDIZER, motorun))

    def test_atil_yakit_adlari_REGRESYON_TABLOSUYLA_ayni(self):
        from hrma.analysis.regression_analysis import RegressionAnalyzer
        urunun = sorted(RegressionAnalyzer().fuel_properties)
        assert sorted(HYBRID_INERT_FUEL_NAMES) == urunun, (
            'HYBRID_INERT_FUEL_NAMES ürünün hibrit yakıt tablosundan '
            'ayrışmış: bekçi=%s ürün=%s'
            % (sorted(HYBRID_INERT_FUEL_NAMES), urunun))

    def test_hibrit_sinifi_tabloya_TURETIMDEN_giriyor(self):
        tablo = SafetyAnalyzer().propellant_tnt_equivalents
        for sinif, deger in HYBRID_EXPLOSIVE_CLASSES.items():
            assert tablo[sinif] == deger


class TestHibritSiviyiTAKLIT_ETMIYOR:
    """Kalemin ölçülen kusuru: hibrit = LOX/RP-1 sıvı çift-iticisi."""

    def test_esleme_artik_sivi_cift_iticiyi_GOSTERMIYOR(self):
        assert MOTOR_TYPE_TO_EXPLOSIVE_CLASS['hybrid'] != 'liquid_biprop', (
            'hibrit yine sıvı çift-iticinin sınıfını ödünç alıyor')
        assert MOTOR_TYPE_TO_EXPLOSIVE_CLASS['hybrid'] in (
            HYBRID_EXPLOSIVE_CLASSES)
        # Sıvı ve katı kolları DEĞİŞMEDİ.
        assert MOTOR_TYPE_TO_EXPLOSIVE_CLASS['liquid'] == 'liquid_biprop'
        assert MOTOR_TYPE_TO_EXPLOSIVE_CLASS['solid'] == 'composite'

    def test_uc_olcumu_ONCE_SONRA(self, istemci):
        """once.json → sonra.json sayıları, uçtan."""
        govde = dict(GUVENLIK)
        govde['propellant_type'] = 'htpb'
        g = istemci.post('/analyze_safety', json=govde).get_json()
        assert _yaprak_ara(g, 'explosive_class')[0] == 'hybrid_n2o'
        assert _yaprak_ara(g, 'tnt_equivalent_factor')[0] == pytest.approx(
            SONRA_HTPB_FAKTOR)
        assert _yaprak_ara(g, 'tnt_equivalent_kg')[0] == pytest.approx(
            SONRA_HTPB_TNT_KG)
        oldurucu = _yaprak_ara(g, 'blast_distances')[0]['lethal']['distance_m']
        assert oldurucu == pytest.approx(SONRA_HTPB_OLDURUCU_M)
        # Ödünç alınan sayı ARTIK ÜRETİLMİYOR ve yön EMNİYETLİ tarafta:
        # N2O ayrışma enerjisi LOX/RP-1 kabulünden yüksektir.
        assert oldurucu > ONCE_HTPB_OLDURUCU_M

    def test_urunun_BES_hibrit_yakiti_da_hibrit_hukmu_aliyor(self, istemci):
        """htpb/paraffin/pe/pmma/abs — hiçbiri artık sıvı hükmü almıyor."""
        for yakit in HYBRID_INERT_FUEL_NAMES:
            govde = dict(GUVENLIK)
            govde['propellant_type'] = yakit
            g = istemci.post('/analyze_safety', json=govde).get_json()
            assert _yaprak_ara(g, 'explosive_class')[0] == 'hybrid_n2o', yakit
            kunye = _yaprak_ara(g, 'explosive_class_basis')[0]
            assert "'%s'" % yakit in kunye, (
                '%s: künye kullanıcının yazdığı yakıdı anmıyor' % yakit)
            assert 'inert polymer' in kunye, yakit

    def test_sivi_ve_kati_kollari_DEGISMEDI(self, istemci):
        for yama, beklenen_sinif, beklenen_tnt in (
                ({'propellant_type': 'liquid_biprop',
                  'motor_type': 'liquid'}, 'liquid_biprop', 1.75),
                ({'propellant_type': 'composite',
                  'motor_type': 'solid'}, 'composite', 2.1),
                ({'propellant_type': 'composite'}, 'composite', 2.1)):
            govde = dict(GUVENLIK)
            govde.update(yama)
            g = istemci.post('/analyze_safety', json=govde).get_json()
            assert _yaprak_ara(g, 'explosive_class')[0] == beklenen_sinif
            assert _yaprak_ara(g, 'tnt_equivalent_kg')[0] == pytest.approx(
                beklenen_tnt)


class TestKunyeGERCEGI_SOYLUYOR:
    """Doktrin 1: beyan çözüm değildir ama beyan da YALAN olamaz."""

    def test_oksitleyici_ADIYLA_yazilinca_COZULUYOR(self, istemci):
        """Kullanıcı oksitleyiciyi yazarsa varsayım kalkar."""
        govde = dict(GUVENLIK)
        govde['propellant_type'] = 'h2o2_htpb'
        g = istemci.post('/analyze_safety', json=govde).get_json()
        assert _yaprak_ara(g, 'explosive_class')[0] == 'hybrid_h2o2'
        kunye = _yaprak_ara(g, 'explosive_class_basis')[0]
        assert 'was read from it' in kunye
        assert 'ASSUMPTION' not in kunye, (
            'kullanıcı oksitleyiciyi yazdı, künye hâlâ varsayım diyor')
        assert 'AIAA 2008-4933' in kunye

    def test_oksitleyici_YOKSA_varsayim_ADIYLA_beyan_ediliyor(self, istemci):
        govde = dict(GUVENLIK)
        govde['propellant_type'] = 'htpb'
        kunye = _yaprak_ara(
            istemci.post('/analyze_safety', json=govde).get_json(),
            'explosive_class_basis')[0]
        assert 'ASSUMPTION' in kunye
        assert "'%s'" % HYBRID_DEFAULT_OXIDIZER in kunye
        # Kullanıcı hangi alternatifin ne kadar yüksek olduğunu GÖRÜR.
        assert 'HIGHER equivalence' in kunye
        assert 'h2o2' in kunye

    def test_TANINMAYAN_ad_atil_grain_IDDIASI_ALMIYOR(self, istemci):
        """'sihir' bir yakıt değil: adı anıp 'atıl polimer' denemez."""
        govde = dict(GUVENLIK)
        govde['propellant_type'] = 'sihir'
        kunye = _yaprak_ara(
            istemci.post('/analyze_safety', json=govde).get_json(),
            'explosive_class_basis')[0]
        assert 'inert polymer' not in kunye, (
            "tanınmayan ad için 'atıl polimer' hükmü kazanılmadı")
        assert 'carries no oxidiser' in kunye


class TestToksikKolFAIL_OPEN_OLMADI:
    """Sınıf adı değişti; toksik hüküm DEĞİŞMEDİ (P7B3-21 koruması).

    ``hybrid_n2o`` toksik kolun 'envanteri belirlenemedi' dalına
    girmeseydi 'tablolu bileşeni yok' dalına düşer ve kazanılmamış bir
    ``'NONE'`` yayımlanırdı — fail-open. Ölçüldü: girmiyor.
    """

    @pytest.mark.parametrize('ad', ['htpb', 'sihir', 'paraffin'])
    def test_hibrit_toksik_hukmu_GERI_CEKILIYOR(self, istemci, ad):
        govde = dict(GUVENLIK)
        govde['propellant_type'] = ad
        g = istemci.post('/analyze_safety', json=govde).get_json()
        assert _yaprak_ara(g, 'toxic_inventory_resolution')[0] == (
            'class_inventory_undetermined')
        assert _yaprak_ara(g, 'toxic_hazard_level')[0] == 'NOT_EVALUATED'
        assert _yaprak_ara(g, 'toxic_components')[0] == []

    def test_oksitleyici_adiyla_yazilinca_envanter_KAZANILIYOR(self, istemci):
        govde = dict(GUVENLIK)
        govde['propellant_type'] = 'n2o_htpb'
        g = istemci.post('/analyze_safety', json=govde).get_json()
        assert _yaprak_ara(g, 'toxic_inventory_resolution')[0] == 'tabulated'
        assert _yaprak_ara(g, 'toxic_components')[0] == ['n2o']


def test_kanit_dosyalari_yerinde():
    """Rapor iddiası dosyayla eşleşir."""
    import json
    dizin = KOK / 'docs/scofield/raw/OH/D29/yapisal-sistem/a1'
    for ad in ('olcum.py', 'once.json', 'sonra.json', 'mutasyon.py',
               'mutasyon.json', 'rapor.md'):
        assert (kanit_gerekli(dizin / ad)).exists(), ad
    once = json.loads((kanit_gerekli(dizin / 'once.json')).read_text(encoding='utf-8'))
    sonra = json.loads((kanit_gerekli(dizin / 'sonra.json')).read_text(encoding='utf-8'))
    # Kusur ÖNCE ölçüldü: hibrit ile sıvı çift-itici ayırt edilemiyordu.
    assert once['K2b_hibrit_sivi_ayrimi']['ayni_mi'] is True
    assert once['K1_tablo_kapsami']['hibrit_sinifi_var_mi'] is False
    assert sonra['K2b_hibrit_sivi_ayrimi']['ayni_mi'] is False
    assert sonra['K1_tablo_kapsami']['hibrit_sinifi_var_mi'] is True
