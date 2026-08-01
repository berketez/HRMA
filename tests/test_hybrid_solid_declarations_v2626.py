"""v2.6.26 — hibrit ve katı yanıtındaki SABİT sayıların beyan bekçileri.

Bağlama haritası her koşuda değişmeyen ("sabit") çıktı yapraklarını
listeliyor; ``tools/sabit_siniflandirma.py`` bunları sınıflandırıyor. Anlamlı
tek rakam **SINIFLANDIRILMAMIS**: kaç yaprağın neden sabit olduğunu
bilmiyoruz. Hibritte 20, katıda 14 kalmıştı.

Bu dosya o kalemlerin kapanışını kilitler. Ölçüt "alan var mı" DEĞİL:

1. Sınıflandırıcının kendisi çağrılır (``siniflandir``) ve hedef yaprağın
   ``SINIFLANDIRILMAMIS`` OLMADIĞI doğrulanır. Beyan metni yaprağın adındaki
   sözcükleri geçirmezse sınıflandırıcı onu kabul etmez; yani metin
   "havada" bir açıklama olamaz, ait olduğu alanı ADIYLA anmak zorundadır.
2. Beyanın DOĞRU olduğu ayrıca sınanır: tek kaynaktan okunan Cd gerekçesi
   gerçekten aynı metin mi, erozif eşik gerçekten çözücünün kullandığı sabit
   mi, iki-fazlı verim gerçekten yayımlanan partikül kesrinden mi çıkıyor,
   yayımlanan derating eğrisi veritabanı kaydını bozuyor mu.

Bu ikisi ayrı testlerdir: birincisi "beyan sayılır mı", ikincisi "beyan
yalan mı". Yalnız birincisi olsaydı, doğru sözcükleri içeren yanlış bir
cümle testi geçerdi.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.support.shake import leaves

from hrma.data.materials_db import get_material
from hrma.analysis.structural_analysis import (
    MANUFACTURING_ALLOWANCE_FACTOR,
    published_material_record,
)
from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.engines.solid_rocket_engine import (
    EROSIVE_REFERENCE_FLUX_KG_M2S,
    EROSIVE_THRESHOLD_KG_M2S,
    SolidRocketEngine,
)

# Sınıflandırıcı depo aracıdır (paket değil); testin ölçütü onun kuralı
# olduğu için KOPYALANMAZ, doğrudan çağrılır.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(_ROOT / 'tools'))
from sabit_siniflandirma import siniflandir  # noqa: E402


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def hybrid():
    return HybridRocketEngine(
        thrust=5000, burn_time=10, of_ratio=2.5, chamber_pressure=20,
        fuel_type='htpb', oxidizer_type='n2o', l_star=1.0).calculate()


@pytest.fixture(scope='module')
def solid():
    return SolidRocketEngine(
        chamber_diameter=100, grain_length=500, core_diameter=30,
        chamber_pressure=40).calculate_performance()


def _flat(result):
    return dict(leaves(result))


def _assert_declared(result, yol):
    """Yaprak sınıflandırıcıya göre beyanlı/tanımlı mı? Gerekçesini döndürür."""
    yapraklar = _flat(result)
    assert yol in yapraklar, f'yaprak yanıtta yok: {yol}'
    sinif, gerekce = siniflandir(yol, yapraklar[yol], yapraklar)
    assert sinif != 'SINIFLANDIRILMAMIS', (
        f'{yol} hâlâ sınıflandırılmamış: beyan metni alanın adındaki '
        f'sözcükleri geçirmiyor olabilir (gerekçe: {gerekce})')
    return sinif, gerekce


# ---------------------------------------------------------------------------
# 1) Sınıflandırma kapanışı — hibrit
# ---------------------------------------------------------------------------

HIBRIT_KAPANAN = [
    # lüle ayrık kayıp modeli: iki model sabiti + modelin girdisi
    '.nozzle_design.performance.friction_efficiency',
    '.nozzle_design.performance.two_phase_efficiency',
    '.nozzle_design.performance.particle_mass_fraction',
    '.nozzle_design.performance.two_phase_loss_coeff',
    # yapısal: imalat payı, tasarım basıncı çarpanı, kenetli burkulma
    # gerilmesi, çevrim modelinin R oranı
    '.structural_analysis.chamber_analysis.manufacturing_allowance_factor',
    '.structural_analysis.design_parameters.design_pressure_factor',
    '.structural_analysis.buckling_analysis.applied_axial_stress_pressurized_MPa',
    '.structural_analysis.fatigue_analysis.stress_ratio_R',
    # malzeme kaydı: oda sıcaklığı referans noktası (her malzemede 1.0)
    '.structural_analysis.material_properties.derating_curve.yield_retention[0]',
    '.heat_transfer_analysis.material_properties.derating_curve.yield_retention[0]',
    # ortam sıcaklığı: girdi yankısı (hibrit formunda alan yok -> varsayılan)
    '.heat_transfer_analysis.design_parameters.ambient_temperature',
    '.heat_transfer_analysis.cooling_analysis.heat_sink_initial_temperature_K',
    # enjektör özeti: Cd gerekçesi devre çözücüsünden taşınır
    '.injector_design.discharge_coefficient',
]


@pytest.mark.parametrize('yol', HIBRIT_KAPANAN)
def test_hibrit_sabit_yapragi_beyanli(hybrid, yol):
    _assert_declared(hybrid, yol)


# ---------------------------------------------------------------------------
# 2) Sınıflandırma kapanışı — katı
# ---------------------------------------------------------------------------

KATI_KAPANAN = [
    # ateşleyici şarjı: katalog kaydı, motordan hesaplanmaz
    '.cad_design.igniter_system.igniter_grain.flame_temperature_k',
    '.cad_design.igniter_system.igniter_grain.gas_molecular_weight_g_mol',
    # erozif yanma eşiği: model sabiti (çözücüyle ORTAK)
    '.detailed_analysis.grain_regression_analysis.erosive_burning_effects'
    '.erosive_threshold_kg_m2s',
    # imalat kabul bandı: yayımlanmış pratik, ölçüm değil
    '.manufacturing_analysis.propellant_manufacturing.quality_requirements'
    '.density_tolerance_percent',
    '.manufacturing_analysis.propellant_manufacturing.quality_requirements'
    '.void_content_max_percent',
    '.manufacturing_analysis.propellant_manufacturing.quality_requirements'
    '.burn_rate_tolerance_percent',
    # grain mekaniği: literatür kaydı, bu modelin GİRDİSİ
    '.structural_analysis.grain_structural.cure_temperature_k',
    '.structural_analysis.grain_structural.grain_elastic_modulus_mpa',
    '.structural_analysis.grain_structural.grain_poisson_ratio',
    '.structural_analysis.grain_structural.grain_thermal_expansion_1k',
]


@pytest.mark.parametrize('yol', KATI_KAPANAN)
def test_kati_sabit_yapragi_beyanli(solid, yol):
    _assert_declared(solid, yol)


# ---------------------------------------------------------------------------
# 3) Beyan YALAN olmasın — hibrit
# ---------------------------------------------------------------------------

class TestHibritBeyanlariDogru:

    def test_iki_fazli_verim_yayimlanan_kesirden_cikar(self, hybrid):
        """eta_2phase = 1 - k*phi özdeşliği yanıtta DOĞRULANABİLİR olmalı.

        Beyan metni bu bağıntıyı anlatıyor; k ve phi de yayımlandığı için
        okuyucu 1.0'ı kendi eliyle yeniden üretebilir. Eskiden yanıtta yalnız
        1.0 vardı ve nereden geldiği görünmüyordu.
        """
        perf = hybrid['nozzle_design']['performance']
        phi = perf['particle_mass_fraction']
        k = perf['two_phase_loss_coeff']
        assert perf['two_phase_efficiency'] == pytest.approx(
            max(0.0, 1.0 - k * max(0.0, phi)), rel=1e-12)
        # Gaz fazlı hibritte metal yükleme yok: kesir tam sıfır, kayıp yok.
        assert phi == 0.0
        assert perf['two_phase_efficiency'] == pytest.approx(1.0)

    def test_surtunme_verimi_merkezi_sabitle_birlestirilmedi(self, hybrid):
        """0.99 ile hrma.constants'taki 0.985 AYNI sayı değildir; beyan da
        bunu söylemek zorundadır (kalibrasyon farkı).
        """
        from hrma.constants import NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT
        perf = hybrid['nozzle_design']['performance']
        basis = perf['friction_efficiency_basis']
        assert 'NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT' in basis
        assert perf['friction_efficiency'] != pytest.approx(
            1.0 - NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT)

    def test_cd_gerekcesi_TEK_kaynaktan_okunur(self, hybrid):
        """Özet blok metni yeniden yazmaz; devre çözücüsünün metnini taşır.

        İki yerde iki farklı gerekçe olamaz: sayı da gerekçe de aynı
        çözümden gelir.
        """
        ozet = hybrid['injector_design']
        if ozet.get('status') == 'not_analyzed':
            pytest.skip('devre çözücüsü bu tasarımı boyutlandıramadı')
        devre = hybrid['injector_design_detail']['ox_circuit']
        assert ozet['discharge_coefficient'] == devre['cd']
        assert ozet['discharge_coefficient_basis'] == devre['cd_basis']
        assert ozet['discharge_coefficient_basis']

    def test_basincli_burkulma_gerilmesi_kenetli_oldugunu_soyler(self, hybrid):
        """0.0 "model yok" değil, max(...,0) kenedidir — ve iki bileşen de
        yanıtta durur ki okuyucu kenedi doğrulayabilsin."""
        b = hybrid['structural_analysis']['buckling_analysis']
        assert 'axial_compression_force_N' in b
        assert 'pressure_stabilizing_stress_MPa' in b
        # Basınçlı durum kredi aldığı için basınçsız durumdan BÜYÜK olamaz.
        assert (b['applied_axial_stress_pressurized_MPa']
                <= b['applied_axial_stress_unpressurized_MPa'] + 1e-9)
        if b['applied_axial_stress_pressurized_MPa'] == 0.0:
            assert b['governing_load_case'] == 'unpressurized'

    def test_imalat_payi_merkezi_sabittir(self, hybrid):
        c = hybrid['structural_analysis']['chamber_analysis']
        assert c['manufacturing_allowance_factor'] == MANUFACTURING_ALLOWANCE_FACTOR
        # Pay, tavsiye edilen kalınlıkla minimum kalınlık arasındaki oranın TA
        # KENDİSİdir: beyan bunu iddia ediyor, ölçüyoruz.
        assert c['recommended_thickness'] == pytest.approx(
            c['minimum_thickness'] * MANUFACTURING_ALLOWANCE_FACTOR, rel=1e-9)

    def test_tasarim_basinci_carpani_kullanici_SF_si_degildir(self):
        """Beyan "kullanıcının emniyet katsayısı değil" diyor; ölçüyoruz:
        SF girdisi değişince tasarım basıncı çarpanı DEĞİŞMEZ."""
        base = dict(thrust=5000, burn_time=10, of_ratio=2.5,
                    chamber_pressure=20, fuel_type='htpb',
                    oxidizer_type='n2o', l_star=1.0)
        a = HybridRocketEngine(**base, safety_factor=2.0).calculate()
        b = HybridRocketEngine(**base, safety_factor=6.0).calculate()
        fa = a['structural_analysis']['design_parameters']['design_pressure_factor']
        fb = b['structural_analysis']['design_parameters']['design_pressure_factor']
        assert fa == fb
        # Tasarım basıncı ise oda basıncının o çarpan katıdır.
        assert a['structural_analysis']['design_parameters']['design_pressure'] \
            == pytest.approx(20.0 * fa, rel=1e-6)

    def test_ortam_sicakligi_girdi_yankisidir(self):
        """Beyan "girdi yankısı" diyor: girdiyi değiştirince alan değişmeli."""
        base = dict(thrust=5000, burn_time=10, of_ratio=2.5,
                    chamber_pressure=20, fuel_type='htpb',
                    oxidizer_type='n2o', l_star=1.0)
        sicak = HybridRocketEngine(**base, ambient_temperature=320.0).calculate()
        ht = sicak['heat_transfer_analysis']
        assert ht['design_parameters']['ambient_temperature'] == pytest.approx(320.0)
        assert ht['cooling_analysis']['heat_sink_initial_temperature_K'] \
            == pytest.approx(320.0)


# ---------------------------------------------------------------------------
# 4) Yayımlanan malzeme kaydı — biçim ve veritabanı dokunulmazlığı
# ---------------------------------------------------------------------------

class TestYayimlananDeratingEgrisi:

    def test_yayimlanan_bicim_adlandirilmis_dizilerdir(self, hybrid):
        for blok in ('structural_analysis', 'heat_transfer_analysis'):
            egri = hybrid[blok]['material_properties']['derating_curve']
            assert set(egri) == {'temperatures_c', 'yield_retention', 'basis'}
            assert len(egri['temperatures_c']) == len(egri['yield_retention'])
            assert egri['temperatures_c'] == sorted(egri['temperatures_c'])
            # Oda sıcaklığı referansı: TANIM gereği 1.0 (eğri ona normalize).
            assert egri['yield_retention'][0] == pytest.approx(1.0)

    def test_iki_modul_ayni_egriyi_yayimlar(self, hybrid):
        a = hybrid['structural_analysis']['material_properties']['derating_curve']
        b = hybrid['heat_transfer_analysis']['material_properties']['derating_curve']
        assert a == b, 'aynı malzeme iki blokta farklı eğri gösteremez'

    def test_veritabani_kaydi_bozulmaz(self):
        """Yayım biçimi bir KOPYADIR: hesap zinciri hâlâ ham sözlüğü okur."""
        kayit = get_material('steel_4130')
        yayim = published_material_record(kayit)
        assert isinstance(kayit['derating_curve'], dict)
        assert 20 in kayit['derating_curve']
        assert kayit['derating_curve'][20] == pytest.approx(1.0)
        assert yayim['derating_curve'] is not kayit['derating_curve']
        assert (len(yayim['derating_curve']['temperatures_c'])
                == len(kayit['derating_curve']))

    def test_emniyet_katsayisi_ad_cakismasi_beyanli_kalir(self, hybrid):
        for blok in ('structural_analysis', 'heat_transfer_analysis'):
            mp = hybrid[blok]['material_properties']
            assert 'NOT the design safety factor entered by the user' \
                in mp['safety_factor_basis']


# ---------------------------------------------------------------------------
# 5) Beyan YALAN olmasın — katı
# ---------------------------------------------------------------------------

class TestKatiBeyanlariDogru:

    def test_erozif_esik_cozucununkiyle_AYNI_sabittir(self, solid):
        """Rapor, yanma hızını fiilen şekillendiren eşiği göstermeli.

        Eskiden 100.0 iki ayrı yerde yazılıydı; biri değişse rapor sessizce
        başka bir eşik gösterirdi. Artık tek sabit — ve davranış ölçülüyor:
        eşiğin altında erozif çarpan tam 1.0'dır.
        """
        blok = (solid['detailed_analysis']['grain_regression_analysis']
                ['erosive_burning_effects'])
        assert blok['erosive_threshold_kg_m2s'] == EROSIVE_THRESHOLD_KG_M2S
        motor = SolidRocketEngine(chamber_diameter=100, grain_length=500,
                                  core_diameter=30, chamber_pressure=40)
        motor.erosive_burning_coeff = 0.05
        assert motor._erosive_factor(EROSIVE_THRESHOLD_KG_M2S) == 1.0
        assert motor._erosive_factor(EROSIVE_THRESHOLD_KG_M2S - 1.0) == 1.0
        assert motor._erosive_factor(
            EROSIVE_THRESHOLD_KG_M2S + EROSIVE_REFERENCE_FLUX_KG_M2S) > 1.0

    def test_kalite_bandi_olcum_olmadigini_soyler(self, solid):
        blok = (solid['manufacturing_analysis']['propellant_manufacturing']
                ['quality_requirements'])
        metin = blok['basis'].lower()
        # Beyan üç alanın da ADINI anmalı (sınıflandırıcı kuralı ve okuyucu
        # için doğrusu bu).
        for jeton in ('density', 'void content', 'burn rate', 'tolerance'):
            assert jeton in metin, jeton
        assert 'not computed' in metin and 'not a measured' in metin

    def test_grain_mekanik_ozellikleri_girdidir_sonuc_degil(self, solid):
        """Beyan "tasarımdan hesaplanmaz" diyor: geometri değişince bu dört
        alan DEĞİŞMEMELİ (gerilme/gerinim ise değişmeli)."""
        a = solid['structural_analysis']['grain_structural']
        b = SolidRocketEngine(chamber_diameter=160, grain_length=900,
                              core_diameter=60, chamber_pressure=70
                              ).calculate_performance()
        b = b['structural_analysis']['grain_structural']
        for alan in ('cure_temperature_k', 'grain_elastic_modulus_mpa',
                     'grain_poisson_ratio', 'grain_thermal_expansion_1k'):
            assert a[alan] == b[alan], alan
        assert a['bore_strain_percent'] != b['bore_strain_percent']
        assert a['grain_property_source']

    def test_grain_mekanik_kaydi_yakita_gore_degisir(self):
        """Kayıt yakıttan gelir: şeker grain, HTPB kompozitle aynı olamaz."""
        apcp = SolidRocketEngine(chamber_diameter=100, grain_length=500,
                                 core_diameter=30, chamber_pressure=40,
                                 propellant_type='apcp'
                                 ).calculate_performance()
        knsu = SolidRocketEngine(chamber_diameter=100, grain_length=500,
                                 core_diameter=30, chamber_pressure=40,
                                 propellant_type='knsu'
                                 ).calculate_performance()
        a = apcp['structural_analysis']['grain_structural']
        s = knsu['structural_analysis']['grain_structural']
        assert a['grain_elastic_modulus_mpa'] != s['grain_elastic_modulus_mpa']
        assert a['cure_temperature_k'] != s['cure_temperature_k']

    def test_atesleyici_gaz_ozellikleri_katalog_kaydidir(self, solid):
        grain = solid['cad_design']['igniter_system']['igniter_grain']
        if grain.get('mass_status') != 'sized':
            pytest.skip('ateşleyici şarjı boyutlandırılamadı')
        metin = grain['basis'].lower()
        for jeton in ('flame temperature', 'molecular weight', 'mol',
                      'catalogue'):
            assert jeton in metin, jeton
        # Katalog kaydının kimliği metinde geçmeli (hangi şarj?).
        assert str(grain['charge_record']) in grain['basis']

    def test_niteleme_bandi_cikti_metninde_adiyla_gecer(self, solid):
        """Docstring "aralık çıktıda AÇIKÇA yazılır" diyordu; söz tutuluyor mu?"""
        te = solid['environmental_analysis']['temperature_effects']
        metin = te['basis']
        assert 'qualification' in metin.lower()
        assert '-20 C' in metin and '+50 C' in metin
        # Metindeki kelvin değerleri yayımlanan noktalarla AYNI olmalı.
        assert f"{te['cold_day']['ambient_k']:.2f}" in metin
        assert f"{te['hot_day']['ambient_k']:.2f}" in metin
