"""Yakıt/malzeme kataloğunun kapıları, alias uzayı ve öz-denetim dürüstlüğü.

Scofield ÖH — Z5S dalgası, paket P09-E. Sekiz kalemin bekçileri.

Ortak ilke: bu dosyadaki hiçbir bekçi bir FİZİKSEL DEĞERİ savunmaz —
yoğunluk, c*, derating eğrisi ve dayanım sayıları Berke'nin karar alanıdır
ve onarım turunda tek hane oynatılmadı. Bekçiler yalnız şunu savunur:

  * kapısız sarmalayıcıya kapı kondu (P9B4-15),
  * iki modülün anahtar uzayı birleşti (P9B4-16),
  * öz-denetim kendi tanımından değil VERİNİN İÇERİĞİNDEN türüyor
    (P9B4-13) ve kazanılmamış sayı basılmıyor (P9B4-12),
  * katalogda olmayan ama çözücünün desteklediği ad BEYAN ediliyor
    (P9B4-17),
  * gerekçesiz sapma ve karışık yükleme modu ADLANDIRILDI (P9B4-18/-21),
  * "taze kopya" beyanı gerçekten taze kopya üretiyor (P9B4-20).

Sayısal çapalar (onarım ÖNCESİ ölçüldü, docs/scofield/raw/OH/Z5S/p09e/
01_capa_ONCE.json): dokunulmayan yolların bit-aynı kaldığını bu dosyadaki
çapa testleri de bağımsızca sınar.
"""

import math

import pytest

from hrma.data import burn_rate_db
from hrma.data import materials_db
from hrma.data import propellants_db
from hrma.data.chemical_database import ChemicalDatabase, ChemicalSpecies
from hrma.data.chemical_database import chemical_db
from hrma.data.propellant_database import (
    SOLVER_SUPPORTED_NOT_CATALOGUED, PropellantDatabase,
)

# Onarım öncesi ölçülen, DEĞİŞMEMESİ gereken değerler (01_capa_ONCE.json).
#
# ÖH D24 / P10B3-10 — ÜÇ cp ÇAPASI GÜNCELLENDİ (ÖK-05 bekçi çevirisi).
# Sebep: ``chemical_database`` NASA polinomlarında gaz sabitini üç yerde
# ``R = 8.314`` (kesilmiş) olarak yazıyordu; artık merkezden okuyor
# (``hrma.constants.R_MOLAR`` = R_UNIVERSAL/1000 = 8,314462618 J/(mol*K),
# CODATA 2018). cp, R'ye DOĞRUSAL bağlıdır, dolayısıyla üç çapa da AYNI
# çarpanla kaydı — ÖLÇÜLDÜ (sonra.json K1):
#     H2O @500 K   35,21208753752625 -> 35,21404685259871
#     N2  @1000 K  32,7601231096     -> 32,761945989397056
#     CH4 @1000 K  73,61257361221996 -> 73,61666965522926
# üçünde de bağıl fark +5,564325e-05 = 8,314462618/8,314 - 1 (bit düzeyinde
# aynı çarpan; başka hiçbir şey değişmedi).
#
# ÇAPRAZ KANIT: ``CAPA_ENTALPI`` DEĞİŞMEDİ. H(T_ref) = H_f olduğundan
# 298,15 K'de integral terimi (tek R'li terim) sıfırdır; sayı R'den
# bağımsızdır ve -393522,0 olarak KALDI. Yani kayma gerçekten yalnız R
# çarpanından geliyor, katsayı/veri bozulmasından değil.
CAPA_CP = {
    ('H2O', 500.0): 35.21404685259871,
    # ÖH D16 / OH-Z5-06 — ÇAPA GÜNCELLENDİ (ÖK-05 bekçi çevirisi).
    # Eski çapa 28.683662906100004 idi ve BOZUK katsayıları (a4/a5) bit
    # düzeyinde kilitliyordu: o sayı NIST-JANAF'ın 1000 K değerinin
    # (32,697 J/mol/K) %12,27 ALTINDAydı. Bu bekçinin işi "P9B4-12 onarımı
    # gerçek katsayılı türlere dokunmadı" demekti; bir VERİ HATASINI
    # dondurmak değildi. Katsayılar standart NASA-7 düşük-sıcaklık setine
    # döndükten sonra ölçülen değer aşağıdadır (JANAF sapması +%0,19).
    ('N2', 1000.0): 32.761945989397056,
    ('CH4', 1000.0): 73.61666965522926,
}
CAPA_ENTALPI = {('CO2', 298.15): -393522.0}
CAPA_BURN_RATE_MMPS = {
    ('kndx', 4.0): 9.966633730092928,
    ('knsb', 4.0): 8.20248616583065,
}

# Yedi katsayısının tamamı 0.0 olan YER TUTUCU kayıtlar (ölçüldü: 8/37).
YER_TUTUCU_TURLER = ('AN', 'AP', 'HTPB', 'MMH', 'NH4ClO4', 'Paraffin',
                     'RP1', 'UDMH')


# ---------------------------------------------------------------------------
# P9B4-12 — yer tutucu katsayıdan sayı üretilmez
# ---------------------------------------------------------------------------
class TestKimyaYerTutucuKapisi:

    def test_yer_tutucu_turler_sayi_basmiyor(self):
        """cp = 0,0 J/mol/K bir ölçüm değil, imkânsız bir sayıydı."""
        for ad in YER_TUTUCU_TURLER:
            assert chemical_db.get_species(ad) is not None, ad
            for T in (298.15, 500.0, 1000.0, 2000.0, 3000.0):
                assert chemical_db.calculate_cp(ad, T) is None, (
                    '%s @%s K icin cp sayisi basildi (kazanilmamis)' % (ad, T))
                assert chemical_db.calculate_enthalpy(ad, T) is None, ad
                assert chemical_db.calculate_entropy(ad, T) is None, ad

    def test_gerekce_adlandirilmis(self):
        """Sessiz None yok: neden basılmadığı ADIYLA okunabilmeli."""
        durum = chemical_db.species_data_status('HTPB')
        assert durum['known_species'] is True
        assert durum['coefficients_usable'] is False
        assert durum['unavailable_reason'] == (
            ChemicalDatabase.CP_UNAVAILABLE_PLACEHOLDER)

        yok = chemical_db.species_data_status('BOYLE_BIR_TUR_YOK')
        assert yok['known_species'] is False
        assert yok['unavailable_reason'] == (
            ChemicalDatabase.CP_UNAVAILABLE_UNKNOWN_SPECIES)
        # İki durum AYNI None'a düşmemeli — ayrımı bu alan taşır.
        assert (yok['unavailable_reason']
                != durum['unavailable_reason'])

    def test_gercek_katsayili_turler_bit_ayni(self):
        """Onarım katsayısı gerçek olan 29 türe DOKUNMADI."""
        for (ad, T), beklenen in CAPA_CP.items():
            assert chemical_db.calculate_cp(ad, T) == beklenen, ad
        for (ad, T), beklenen in CAPA_ENTALPI.items():
            assert chemical_db.calculate_enthalpy(ad, T) == beklenen, ad

    def test_olu_30_sabiti_geri_gelmedi(self):
        """Belgelenen 'fallback constant Cp = 30.0' dalı ölüydü; kurtarılmadı.

        Kısa katsayı listesi de bir ölçüm değildir: uydurma sabit yerine
        sayı basılmaz.
        """
        db = ChemicalDatabase()
        db.species_data['KISA_KATSAYI'] = ChemicalSpecies(
            name='KISA_KATSAYI', formula='X', molecular_weight=10.0,
            enthalpy_formation=0.0, entropy_standard=100.0,
            cp_coefficients=[1.0, 2.0, 3.0],
            temperature_ranges=[(298, 1000)], phase='gas',
            cas_number='0-00-0', source='Custom')
        assert db.calculate_cp('KISA_KATSAYI', 1000.0) is None
        assert db.species_data_status('KISA_KATSAYI')['unavailable_reason'] \
            == ChemicalDatabase.CP_UNAVAILABLE_TOO_FEW
        assert db.calculate_cp('KISA_KATSAYI', 1000.0) != 30.0


# ---------------------------------------------------------------------------
# P9B4-13 — öz-denetim totolojisi
# ---------------------------------------------------------------------------
class TestKimyaOzDenetimi:

    def test_sayac_icerikten_turuyor(self):
        rapor = chemical_db.validate_database()
        assert rapor['total_species'] == 37
        # Yapısal sayı (uzunluk) ile içerik sayısı AYRI raporlanır ve
        # aralarındaki fark eksiğin kendisidir.
        assert rapor['species_with_seven_coefficients'] == 37
        assert rapor['species_with_usable_coefficients'] == 29
        assert rapor['species_with_placeholder_coefficients'] == 8
        assert rapor['species_missing_data'] == 8, (
            'oz-denetim yeniden "0 eksik" diyor — totoloji geri geldi')
        assert rapor['species_with_coefficients'] == 29
        assert tuple(rapor['placeholder_species']) == YER_TUTUCU_TURLER

    def test_sayac_toplami_kapaniyor(self):
        rapor = chemical_db.validate_database()
        assert (rapor['species_with_usable_coefficients']
                + rapor['species_with_placeholder_coefficients']
                == rapor['total_species'])

    def test_sayac_veriyi_IZLIYOR_sabit_degil(self):
        """Anti-totoloji kanıtı: veri değişince sayaç DEĞİŞMELİ.

        Eski sayaç `len(coeffs) >= 7` diye baktığı için sıfır katsayılı bir
        kayıt eklemek raporu hiç kıpırdatmıyordu. Bu bekçi, sayacın gerçekten
        içeriği okuduğunu bağımsız bir örnekle ölçer (küresel DB'ye
        dokunmaz).
        """
        db = ChemicalDatabase()
        onceki = db.validate_database()
        db.species_data['SIFIR_KAYIT'] = ChemicalSpecies(
            name='SIFIR_KAYIT', formula='X', molecular_weight=10.0,
            enthalpy_formation=0.0, entropy_standard=100.0,
            cp_coefficients=[0.0] * 7,
            temperature_ranges=[(298, 1000)], phase='gas',
            cas_number='0-00-0', source='Custom')
        sonraki = db.validate_database()

        assert sonraki['total_species'] == onceki['total_species'] + 1
        assert sonraki['species_with_seven_coefficients'] == \
            onceki['species_with_seven_coefficients'] + 1, (
                'yapisal sayac yeni kaydi gormedi')
        assert sonraki['species_missing_data'] == \
            onceki['species_missing_data'] + 1, (
                'icerik sayaci sifir katsayili kaydi "eksik" saymadi — '
                'totoloji geri geldi')
        assert sonraki['species_with_usable_coefficients'] == \
            onceki['species_with_usable_coefficients']
        assert 'SIFIR_KAYIT' in sonraki['placeholder_species']

    def test_rapor_ne_olctugunu_yaziyor(self):
        rapor = chemical_db.validate_database()
        assert 'non-zero' in rapor['coefficient_check_basis']
        assert set(rapor['thermo_properties_withheld_for']) == \
            set(YER_TUTUCU_TURLER)

    def test_beyan_ile_davranis_ayni_kapidan(self):
        """Rapor 'esirgendi' dediği her tür için sayı GERÇEKTEN esirgenir."""
        rapor = chemical_db.validate_database()
        for ad in rapor['thermo_properties_withheld_for']:
            assert chemical_db.calculate_cp(ad, 1000.0) is None, ad
        for ad in chemical_db.get_all_species_names():
            if ad not in rapor['thermo_properties_withheld_for']:
                assert chemical_db.calculate_cp(ad, 1000.0) is not None, ad


# ---------------------------------------------------------------------------
# P9B4-15 — yanma hızı girdi kapısı (kardeş parite)
# ---------------------------------------------------------------------------
class TestYanmaHiziKapisi:

    GECERSIZ = (-0.5, 0.0, float('nan'), float('inf'), True)

    def test_karmasik_sayi_donmuyor(self):
        for p in (-0.5, -1e-9, -1000.0):
            with pytest.raises(ValueError):
                burn_rate_db.burn_rate_mmps('kndx', p)

    def test_gecersiz_girdiler_reddediliyor(self):
        for p in self.GECERSIZ:
            with pytest.raises(ValueError):
                burn_rate_db.burn_rate_mmps('kndx', p)
            with pytest.raises(ValueError):
                burn_rate_db.burn_rate_mps('kndx', p)
            with pytest.raises(ValueError):
                burn_rate_db.in_range('kndx', p)
            with pytest.raises(ValueError):
                burn_rate_db.resolve_engine_coeffs('kndx', p)

    def test_kardes_sarmalayicilar_ayni_kapiyi_tasiyor(self):
        """Aynı yasanın iki sarmalayıcısı aynı girdide aynı kararı verir."""
        for p_bar in (-1.0, 0.0):
            with pytest.raises(ValueError):
                propellants_db.burn_rate_mps('kndx', p_bar)
            with pytest.raises(ValueError):
                burn_rate_db.burn_rate_mps('kndx', p_bar * 1e5)

    def test_saglikli_basinclar_bit_ayni(self):
        for (yakit, p_mpa), beklenen in CAPA_BURN_RATE_MMPS.items():
            assert burn_rate_db.burn_rate_mmps(yakit, p_mpa) == beklenen

    def test_supurmede_hic_karmasik_sayi_yok(self):
        for yakit in ('kndx', 'knsb'):
            for i in range(1, 200):
                p = i * 0.06
                r = burn_rate_db.burn_rate_mmps(yakit, p)
                assert isinstance(r, float) and math.isfinite(r) and r > 0


# ---------------------------------------------------------------------------
# P9B4-16 — iki modülün anahtar uzayı
# ---------------------------------------------------------------------------
class TestAliasUzayi:

    def _yasali_aliaslar(self):
        return [a for a, hedef in propellants_db.ALIASES.items()
                if hedef in tuple(burn_rate_db.BURN_RATE_LAWS)]

    def test_alias_kumesi_bos_degil(self):
        """Bekçinin kendisi totolojik olmasın: ölçtüğü küme dolu olmalı."""
        assert len(self._yasali_aliaslar()) >= 4

    def test_kardes_modul_ayni_yakiti_taniyor(self):
        for alias in self._yasali_aliaslar():
            assert burn_rate_db.has_law(alias) is True, (
                "'%s' propellants_db'de cozuluyor ama burn_rate_db yasayi "
                "'yok' sayiyor" % alias)
            assert burn_rate_db.resolve_key(alias) == \
                propellants_db.ALIASES[alias]

    def test_alias_kanonikle_ayni_sayiyi_veriyor(self):
        for alias in self._yasali_aliaslar():
            hedef = propellants_db.ALIASES[alias]
            for p in (0.5, 4.0, 9.0):
                assert burn_rate_db.burn_rate_mmps(alias, p) == \
                    burn_rate_db.burn_rate_mmps(hedef, p)

    def test_tabloyu_indeksleyen_tuketici_kirilmiyor(self):
        """solid_rocket_engine yolunun aynısı: has_law evet derse indeksleme
        de evet demeli (aksi hâlde KeyError ile çöker)."""
        for alias in self._yasali_aliaslar():
            assert burn_rate_db.has_law(alias)
            law = burn_rate_db.BURN_RATE_LAWS[alias]
            assert law['regimes'], alias
            assert law is burn_rate_db.BURN_RATE_LAWS[
                propellants_db.ALIASES[alias]]

    def test_liste_kunyesi_kanonik_kaliyor(self):
        """`sorted(BURN_RATE_LAWS)` künyesi alias'la şişmemeli."""
        assert sorted(burn_rate_db.BURN_RATE_LAWS) == ['kndx', 'knsb']
        assert len(burn_rate_db.BURN_RATE_LAWS) == 2

    def test_bilinmeyen_ad_hala_hata(self):
        assert burn_rate_db.has_law('boyle_bir_yakit_yok') is False
        assert burn_rate_db.resolve_key('boyle_bir_yakit_yok') is None
        assert burn_rate_db.resolve_key(None) is None
        with pytest.raises(KeyError):
            burn_rate_db.BURN_RATE_LAWS['boyle_bir_yakit_yok']
        # Yasası olmayan gerçek yakıt da 'var' sayılmamalı
        assert burn_rate_db.has_law('apcp') is False


# ---------------------------------------------------------------------------
# P9B4-17 — katalogda olmayan ama çözücünün desteklediği ad
# ---------------------------------------------------------------------------
class TestBeyanEdilmisBosluk:

    @pytest.fixture(scope='class')
    def db(self):
        return PropellantDatabase()

    def test_gox_sessiz_none_degil(self, db):
        durum = db.get_propellant_status('gox')
        assert durum['catalogued'] is False
        assert durum['record_available'] is False
        assert durum['solver_supported'] is True
        assert durum['gap_reason'] and durum['gap_reason'] != \
            'unknown_propellant_name'
        assert durum['gap_declared_by']

    def test_yazim_hatasindan_ayirt_ediliyor(self, db):
        yok = db.get_propellant_status('goxx')
        assert yok['solver_supported'] is False
        assert yok['gap_reason'] == 'unknown_propellant_name'

    def test_uydurma_kayit_yazilmadi(self, db):
        """Boşluk beyan edildi, DOLDURULMADI: gox'a yoğunluk uydurulmadı."""
        assert db.get_propellant_properties('gox') is None
        assert 'gox' not in db.database
        assert 'gox' not in propellants_db.PROPELLANTS

    def test_beyan_katalogla_celismiyor(self, db):
        """Beyan edilen boşluk gerçekten boş olmalı (çift kayıt yasağı)."""
        for ad in SOLVER_SUPPORTED_NOT_CATALOGUED:
            assert db.get_propellant_properties(ad) is None, (
                "'%s' hem 'katalogda yok' diye beyan ediliyor hem kaydi var "
                '— beyan bayat' % ad)
            assert ad not in propellants_db.PROPELLANTS

    def test_beyan_gerekce_ve_kaynak_tasiyor(self):
        for ad, kayit in SOLVER_SUPPORTED_NOT_CATALOGUED.items():
            assert kayit['reason'].strip(), ad
            assert kayit['supported_in'].strip(), ad

    def test_katalogdaki_ad_bosluk_sayilmiyor(self, db):
        for ad in ('lox', 'n2o', 'htpb'):
            durum = db.get_propellant_status(ad)
            assert durum['catalogued'] is True
            assert durum['gap_reason'] is None


# ---------------------------------------------------------------------------
# P9B4-18 — c* ⟷ (gamma, T_c, M) özdeşlik beyanı
# ---------------------------------------------------------------------------
class TestCstarBeyani:

    def test_sayilar_degismedi(self):
        """Kayıt çapası — P9B4-18 beyan turu SAYILARI değiştirmedi.

        ÇEVİRİ (ÖH D15 birleşmesi, 1 Eyl 2026 — katı a2 / P2B1-01).
        ``c_star`` çapası 1186,7 → 1406,8 GÜNCELLENDİ. Bu bir gevşetme
        değil, çapanın kaydın kendi hükmüne göre tazelenmesidir: kaydın
        (γ = 1,2612 · T_c = 2789,3 K · M = 26,89) üçlüsünün Sutton Eq. 3-32
        ideali 1406,774 m/s'dir ve 1186,7 tek fazlı (homojen nitrat esteri)
        bir kayıtta -%15,64 sapma demekti; yoğuşmuş faz mazereti bu itici
        için GEÇERSİZ olduğu için sapmanın kaynağı yoktu. P2B1-01 iki
        dosyayı (katalog + solid_rocket_engine yerel tablosu) AYNI commit'te
        1406,8'e taşıdı ve ``_CSTAR_NOTLARI['double_base']`` beyanını
        kaldırdı. Üçlünün kendisi bit-aynı kaldı, çapa olarak burada durur.
        """
        rec = propellants_db.PROPELLANTS['double_base']
        assert rec['c_star'] == 1406.8
        assert rec['gamma'] == 1.2612
        assert rec['flame_temperature'] == 2789.3
        assert rec['molecular_weight'] == 26.89

    def test_sapma_hesaplaniyor_ve_kaydin_kendi_sayilarindan(self):
        for key, rec in propellants_db.PROPELLANTS.items():
            ideal = propellants_db.cstar_from_thermo(
                rec['gamma'], rec['flame_temperature'],
                rec['molecular_weight'])
            assert rec['c_star_ideal_mps'] == pytest.approx(ideal, rel=1e-12), key
            assert rec['c_star_ideal_deviation_pct'] == pytest.approx(
                100.0 * (rec['c_star'] - ideal) / ideal, rel=1e-12), key

    def test_double_base_sapmasi_beyanli(self):
        """double_base'in c* sapması ya YOKTUR ya BEYANLIDIR.

        ÇEVİRİ (ÖH D15 birleşmesi, 1 Eyl 2026 — katı a2 / P2B1-01).
        Bekçi eskiden sapmanın DURDUĞUNU (< -%10) ve gerekçe metninin
        ('homogeneous', 'not explained') yerinde olduğunu kilitliyordu.
        P2B1-01 sapmayı KAPATTI (-%15,64 → %0,0018) ve beyanı kaldırdı;
        eski iddia yürürlükte kalsaydı bekçi kapanmış bir kusuru geri
        çağırıyor olurdu.

        Yeni ölçüt daha DAR: sapma kaydın kendi üçlüsünden yeniden
        hesaplanır, kapandığı ÖLÇÜLÜR ve beyan kanalının bilerek boş
        olduğu doğrulanır. Sapma yeniden açılırsa (birisi c*'ı ya da
        üçlüyü tek başına oynatırsa) burada KIRMIZI verir; gerekçesiz
        büyük sapma ayrıca ``test_buyuk_sapma_beyansiz_kalmiyor``a takılır.
        """
        rec = propellants_db.PROPELLANTS['double_base']
        ideal = propellants_db.cstar_from_thermo(
            rec['gamma'], rec['flame_temperature'], rec['molecular_weight'])
        sapma = rec['c_star_ideal_deviation_pct']
        assert sapma == pytest.approx(
            100.0 * (rec['c_star'] - ideal) / ideal, rel=1e-12)
        assert abs(sapma) < 0.01, (
            'double_base c* sapması yeniden açıldı (%%%.4f): kayıt tek fazlı '
            'bir nitrat esteri, yoğuşmuş faz mazereti GEÇERSİZ — ya sayı '
            'düzeltilir ya sapma _CSTAR_NOTLARI ile ADIYLA beyan edilir'
            % sapma)
        # Beyan KANALI duruyor (istemci sözleşmesi: alan her kayıtta var)
        # ama bu kayıt için bilerek boş: beyan edilecek sapma kalmadı.
        assert 'c_star_deviation_note' in rec
        assert not (rec['c_star_deviation_note'] or '').strip(), (
            'sapma kapandı ama eski gerekçe metni kayıtta duruyor — '
            'beyan çürümesi')
        assert 'double_base' not in propellants_db._CSTAR_NOTLARI

    def test_kayit_sekli_tek_tip_kaldi(self):
        """İstemci sözleşmesi: tüm kayıtlar aynı alan kümesini taşır."""
        sekiller = {frozenset(r) for r in propellants_db.PROPELLANTS.values()}
        assert len(sekiller) == 1
        for alan in ('c_star_ideal_mps', 'c_star_ideal_deviation_pct',
                     'c_star_deviation_note'):
            assert all(alan in r for r in propellants_db.PROPELLANTS.values())

    def test_buyuk_sapma_beyansiz_kalmiyor(self):
        """%10'dan büyük sapma ya kaydın notlarında ya beyan alanında."""
        for key, rec in propellants_db.PROPELLANTS.items():
            if abs(rec['c_star_ideal_deviation_pct']) <= 10.0:
                continue
            metin = ' '.join(str(rec.get(a) or '') for a in
                             ('notes', 'source', 'c_star_deviation_note'))
            assert metin.strip(), key
            assert any(im in metin.lower() for im in
                       ('condensed', 'two-phase', 'below the ideal',
                        'not explained')), (
                '%s: %%%.1f sapma gerekcesiz' % (
                    key, rec['c_star_ideal_deviation_pct']))


# ---------------------------------------------------------------------------
# P9B4-20 — "taze kopya" beyanı
# ---------------------------------------------------------------------------
class TestGorunumKopyalari:

    def test_alias_kanonikle_ayni_nesne_degil(self):
        view = propellants_db.build_propellants_view()
        for alias, hedef in propellants_db.ALIASES.items():
            assert view[alias] is not view[hedef], alias
            assert view[alias] == view[hedef], alias

    def test_alias_uzerinden_yazma_sizmiyor(self):
        view = propellants_db.build_propellants_view()
        onceki = propellants_db.PROPELLANTS['apcp']['density']
        view['ap']['density'] = -1.0
        assert propellants_db.PROPELLANTS['apcp']['density'] == onceki
        assert view['apcp']['density'] == onceki
        # Taze görünüm de kirlenmemeli
        assert propellants_db.build_propellants_view()['ap']['density'] == \
            onceki

    def test_her_cagri_taze(self):
        a = propellants_db.build_propellants_view()
        b = propellants_db.build_propellants_view()
        assert a['kndx'] is not b['kndx']
        assert a == b


# ---------------------------------------------------------------------------
# P9B4-21 — ablative kaydında iki yükleme modu
# ---------------------------------------------------------------------------
class TestDayanimModuBeyani:

    def test_degerler_degismedi(self):
        rec = materials_db.get_material('ablative')
        assert rec['yield_strength'] == 40e6
        assert rec['ultimate_strength'] == 90e6

    def test_modlar_adlandirildi(self):
        beyan = materials_db.strength_mode_declaration('ablative')
        assert beyan['declared'] is True
        assert beyan['yield_strength_mode'] == 'tensile_fiber_direction'
        assert beyan['ultimate_strength_mode'] == 'compressive'
        assert beyan['modes_mixed'] is True
        assert 'TENSILE' in beyan['note'] and 'COMPRESSIVE' in beyan['note']

    def test_alias_ayni_beyani_goruyor(self):
        for ad in ('ablative', 'silica_phenolic', 'silica-phenolic'):
            beyan = materials_db.strength_mode_declaration(ad)
            assert beyan['material'] == 'ablative'
            assert beyan['modes_mixed'] is True

    def test_beyansiz_kayda_mod_UYDURULMUYOR(self):
        """Beyanı olmayan kayıt 'çekme' varsayılmaz — declared: False."""
        beyan = materials_db.strength_mode_declaration('steel_4130')
        assert beyan['declared'] is False
        assert beyan['yield_strength_mode'] is None
        assert beyan['modes_mixed'] is False

    def test_karisik_modlu_kayit_beyansiz_kalamaz(self):
        """Kayıt modları karışıksa beyan alanları ZORUNLU."""
        for ad, rec in materials_db.MATERIALS.items():
            if rec.get('strength_modes_mixed'):
                assert rec.get('yield_strength_mode'), ad
                assert rec.get('ultimate_strength_mode'), ad
                assert rec['yield_strength_mode'] != \
                    rec['ultimate_strength_mode'], ad
                assert rec.get('strength_mode_note'), ad
