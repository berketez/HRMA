"""v2.6.26 — sıvı yanıtındaki SABİT sayıların beyan bekçisi.

Bağlama haritası her koşuda kıpırdamayan ("sabit") çıktı yapraklarını
listeliyor, ``tools/sabit_siniflandirma.py`` da onları sınıflandırıyor.
Anlamlı tek rakam **SINIFLANDIRILMAMIS**: kaç yaprağın NEDEN sabit olduğunu
bilmiyoruz. Sıvı sayfasında 37 kalmıştı; bu dosya kapanışı kilitler.

Ölçüt "alan var mı" DEĞİL, üç ayrı sınavdır:

1. **Sayılır mı** — sınıflandırıcının kendisi (``siniflandir``) çağrılır ve
   yaprağın ``SINIFLANDIRILMAMIS`` olmadığı doğrulanır.
2. **Havada mı** — beyan metni, yaprağın ADINDAKİ sözcükleri geçirmek
   zorundadır (``_kardes_beyan_var`` jeton eşleşmesi). Tek bir genel cümlenin
   koca bir bloğu aklaması böyle engellenir; bu yüzden besleme sistemi
   topoloji metinleri de alan başına üretilir.
3. **Yalan mı** — beyanın DOĞRU olduğu ayrıca ölçülür. Bu en önemlisidir:
   yalnız (1) ve (2) olsaydı, doğru sözcükleri içeren yanlış bir cümle testi
   geçerdi. v2.6.26'da tam olarak bu oldu — ``channel_section_source`` kanal
   kesitini "design default (not auto-sized)" ilan ediyordu, oysa DERİNLİK
   hız hedefine göre otomatik boyutlanıyordu (2 MN'de 6,70 mm).

Ayrıca üç KUSUR kilitlenir:

* ``manifold.v_ratio`` / ``area_ratio`` totolojisi: oran kendi hedefinden
  geri hesaplanıyordu (daima 0,1 ve 10), ``MANIFOLD_V_RATIO_MAX`` /
  ``MANIFOLD_AREA_RATIO_MIN`` bekçi sabitleri hiçbir karşılaştırmaya
  girmiyordu.
* ``feed_lines.*.length`` çift tanımı: ekrandaki boy literaldi, basınç
  düşümü modül sabitini kullanıyordu; biri değişse sessizce ayrışırlardı.
* ``weber_number`` ad çakışması: sıvı motorun bastığı 12 aslında KRİTİK Weber
  sayısıdır (parçalanma eşiği), ``hrma/utils/injector_design.py`` ise aynı ad
  altında GERÇEKTEN hesaplanan Weber sayısını yayımlıyor.

Testler motoru DOĞRUDAN kurar (HTTP katmanı başka dosyaların işi) ve ağa
çıkmaz: ``propellant_data`` enjekte edilir.
"""

from __future__ import annotations

import contextlib
import io
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

from tests.support.shake import leaves

from hrma.engines.injector_design import (
    MANIFOLD_AREA_RATIO_MIN,
    MANIFOLD_V_RATIO_MAX,
    MANIFOLD_V_RATIO_TARGET,
    design_injector,
)
from hrma.engines.liquid_rocket_engine import (
    CONVERGENT_HALF_ANGLE_DEG,
    COOLANT_CHANNEL_TARGET_VELOCITY_MS,
    COOLING_CHANNEL_HEIGHT_DEFAULT_M,
    COOLING_CHANNEL_WIDTH_DEFAULT_M,
    CRITICAL_WEBER_NUMBER,
    FEED_LINE_LENGTH_DEFAULT_M,
    LiquidRocketEngine,
    PROPELLANT_CIRCUIT_COUNT,
    TANK_LD_RATIO,
    TANK_LEVEL_PROBE_POSITIONS,
    TANK_PROPELLANT_RESERVE_FACTOR,
    TANK_ULLAGE_FRACTION,
)

warnings.filterwarnings('ignore')

# Sınıflandırıcı depo aracıdır (paket değil). Testin ÖLÇÜTÜ onun kuralı
# olduğu için kural kopyalanmaz, doğrudan çağrılır.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(_ROOT / 'tools'))
from sabit_siniflandirma import (  # noqa: E402
    _birimsiz,
    _jetonlar,
    _kardes_beyan_var,
    _son_ad,
    siniflandir,
)


# ---------------------------------------------------------------------------
# Çevrimdışı motor
# ---------------------------------------------------------------------------

#: Ağ yok: motora boş ama VAR olan itici verisi enjekte edilir.
OFFLINE_PROPELLANTS = {'rp1': {}, 'lox': {}}

#: liquid.html varsayılanlarıyla uyumlu taban ezmeler.
BASE_OVERRIDES = dict(
    fuel_density=810, oxidizer_density=1141, mixture_ratio=2.3,
    combustion_efficiency=97, engine_cycle='gas_generator', feed_pressure=105,
    generator_gas_temp=900, turbine_expansion_ratio=4,
    injector_type='impinging', injector_pressure_drop=20,
    discharge_coefficient=0.7, contraction_ratio=4,
    characteristic_length=1.2, chamber_material='inconel_718',
    cooling_type='regenerative', nozzle_expansion_ratio=12,
    nozzle_type='bell_80', safety_factor=2.5,
)

BASE_CTOR = dict(thrust=25000, chamber_pressure=70, mixture_ratio=2.3,
                 fuel_type='rp1', oxidizer_type='lox',
                 propellant_data=OFFLINE_PROPELLANTS)


def _run(**delta):
    """Motoru taban yükün üstüne ``delta`` ile koşar; tam sonucu döner."""
    overrides = dict(BASE_OVERRIDES)
    ctor = dict(BASE_CTOR)
    for key, value in delta.items():
        overrides[key] = value
        if key in ('thrust', 'chamber_pressure', 'mixture_ratio',
                   'cooling_type', 'injector_type'):
            ctor[key] = value
    with contextlib.redirect_stdout(io.StringIO()):
        return LiquidRocketEngine(overrides=overrides,
                                  **ctor).calculate_performance()


@pytest.fixture(scope='module')
def base():
    return _run()


@pytest.fixture(scope='module')
def buyuk():
    """80 kat itki: ölçek bağımlılığını ölçmek için ikinci nokta."""
    return _run(thrust=2_000_000)


@pytest.fixture(scope='module')
def yapraklar(base):
    return dict(leaves(base))


def _leaf(result, path):
    node = result
    for parca in path.split('.'):
        if parca.endswith(']'):
            ad, _, idx = parca[:-1].partition('[')
            node = node[ad][int(idx)]
        else:
            node = node[parca]
    return node


# ---------------------------------------------------------------------------
# 1) v2.6.26 öncesinde SINIFLANDIRILMAMIS olan 37 yaprak
# ---------------------------------------------------------------------------

#: Ölçülmüş liste (bağlama haritası, sıvı sayfası, v2.6.26 Faz 3 öncesi).
#: Her kalem ya hâlâ yanıtta ve BEYANLI, ya da bilinçli olarak kaldırılmış
#: (yeniden adlandırma / None + NOT_MODELLED). Üçüncü seçenek yoktur.
ESKI_SINIFLANDIRILMAMIS = (
    '.cooling_system.channel_height_mm',
    '.cooling_system.channel_width_mm',
    '.cooling_system.convergent_half_angle_deg',
    '.feed_system.control_system.backup_valves',
    '.feed_system.control_system.control_computers',
    '.feed_system.control_system.flow_sensors',
    '.feed_system.control_system.gimbal_actuators',
    '.feed_system.control_system.main_valves',
    '.feed_system.control_system.pressure_sensors',
    '.feed_system.control_system.temperature_sensors',
    '.feed_system.control_system.throttle_valves',
    '.feed_system.feed_lines.fuel_main.length',
    '.feed_system.feed_lines.oxidizer_main.length',
    '.feed_system.pressurization.check_valves',
    '.feed_system.pressurization.pressurant_tanks',
    '.feed_system.pressurization.pressure_regulators',
    '.feed_system.pressurization.relief_valves',
    '.injection_system.injector_design_detail.fuel_circuit.manifold.area_ratio',
    '.injection_system.injector_design_detail.fuel_circuit.manifold.v_ratio',
    '.injection_system.injector_design_detail.momentum.target',
    '.injection_system.injector_design_detail.ox_circuit.manifold.area_ratio',
    '.injection_system.injector_design_detail.ox_circuit.manifold.v_ratio',
    '.injection_system.injector_design_detail.pattern.impingement'
    '.half_angle_deg',
    '.manufacturing_analysis.critical_tolerances.features.throat_diameter'
    '.tolerance_mm',
    '.nozzle_angles.convergent_half_angle_deg',
    '.propellant_tanks.fuel_tank.internal_structures.instrumentation'
    '.level_sensors.count',
    '.propellant_tanks.fuel_tank.internal_structures.instrumentation'
    '.pressure_transducers',
    '.propellant_tanks.fuel_tank.internal_structures.slosh_baffles[0]'
    '.open_area_ratio_achieved',
    '.propellant_tanks.fuel_tank.internal_structures.slosh_baffles[1]'
    '.open_area_ratio_achieved',
    '.propellant_tanks.oxidizer_tank.internal_structures.instrumentation'
    '.level_sensors.count',
    '.propellant_tanks.oxidizer_tank.internal_structures.instrumentation'
    '.pressure_transducers',
    '.propellant_tanks.oxidizer_tank.internal_structures.slosh_baffles[0]'
    '.open_area_ratio_achieved',
    '.propellant_tanks.oxidizer_tank.internal_structures.slosh_baffles[1]'
    '.open_area_ratio_achieved',
    '.propellant_tanks.system_summary.safety_margin',
    '.propellant_tanks.system_summary.ullage_fraction',
)

#: Bilinçli olarak KALDIRILAN (yeniden adlandırılan) yollar ve yerine geleni.
YENIDEN_ADLANDIRILAN = {
    '.injection_system.weber_number': '.injection_system'
                                      '.critical_weber_number',
    '.injector_design.weber_number': '.injector_design.critical_weber_number',
}


def test_eski_sabitlerin_hepsi_kapandi(yapraklar):
    """37 kalemin tamamı ya beyanlı ya da adıyla kaldırılmış olmalı."""
    acik = []
    for yol in ESKI_SINIFLANDIRILMAMIS:
        assert yol in yapraklar, f'yaprak yanıttan kayboldu: {yol}'
        sinif, gerekce = siniflandir(yol, yapraklar[yol], yapraklar)
        if sinif == 'SINIFLANDIRILMAMIS':
            acik.append((yol, gerekce))
    assert not acik, f'hâlâ sınıflandırılmamış: {acik}'


def test_weber_adi_ayrildi(yapraklar):
    """Aynı ad iki anlam taşıyamaz: eşik ile hesaplanan sayı ayrı adlarda."""
    for eski, yeni in YENIDEN_ADLANDIRILAN.items():
        assert eski not in yapraklar, (
            f'{eski} geri geldi; bu sayı bir Weber sayısı değil, KRİTİK Weber '
            'sayısıdır')
        assert yapraklar[yeni] == CRITICAL_WEBER_NUMBER
        sinif, _ = siniflandir(yeni, yapraklar[yeni], yapraklar)
        assert sinif != 'SINIFLANDIRILMAMIS'


def test_kapatilan_yaprak_sayisi(yapraklar):
    """Kapanan kalem sayısı 37'nin altına düşmemeli (geri adım bekçisi)."""
    kapali = sum(
        1 for yol in ESKI_SINIFLANDIRILMAMIS
        if siniflandir(yol, yapraklar[yol], yapraklar)[0]
        != 'SINIFLANDIRILMAMIS')
    assert kapali + len(YENIDEN_ADLANDIRILAN) == 37


# ---------------------------------------------------------------------------
# 2) Beyan "havada" olamaz — metin alanın adını ANMAK zorunda
# ---------------------------------------------------------------------------

def test_beyan_metni_alanin_adini_aniyor(yapraklar):
    """Her beyan metni, yaprağın adındaki sözcükleri geçirmeli.

    Sınıflandırıcı blok beyanlarını jeton eşleşmesiyle kabul ediyor. Ölçüt
    burada BİLEREK daha katı uygulanır: kardeş beyan doğrudan bulunmuş olsa
    bile (kural 1, jeton aramaz) metnin alanı adıyla anması istenir. Aksi
    hâlde "besleme sistemi mimari varsayımıdır" gibi tek bir cümle on ayrı
    sayıyı aklardı ve okuyucu hangi sayının neden orada olduğunu göremezdi.
    """
    eksik = []
    for yol in ESKI_SINIFLANDIRILMAMIS:
        beyan = _kardes_beyan_var(yol, yapraklar)
        if beyan is None:
            # Değer None ise beyan zaten değerin kendisidir (üretilmedi).
            assert yapraklar[yol] is None, f'{yol}: beyan yok'
            continue
        hedef = _jetonlar(_birimsiz(_son_ad(yol)))
        metin = _jetonlar(str(yapraklar.get(beyan) or ''))
        if not hedef.issubset(metin):
            eksik.append((yol, sorted(hedef - metin), beyan))
    assert not eksik, (
        'beyan metni alanın adındaki sözcükleri geçirmiyor '
        f'(yol, eksik sözcükler, beyan alanı): {eksik}')


def test_beyan_metinleri_bos_degil(yapraklar):
    """Beyan alanı var ama içi boş/kısa olamaz — ölçüt anlamlı düzyazıdır.

    ``*_status`` alanları BİLEREK dışarıda: onlar ('NOT_MODELLED' gibi)
    makine tarafından okunan kısa etiketlerdir, gerekçe düzyazısı yanlarındaki
    ``*_basis`` alanındadır. Uyarı yükü (``.params.``) de dışarıdadır: orada
    ``sigma_basis='table'`` gibi kısa bir kaynak etiketi meşrudur.
    """
    kisa = []
    for anahtar, deger in yapraklar.items():
        if not anahtar.endswith('_basis') or '.params.' in anahtar:
            continue
        if not str(anahtar).startswith(('.feed_system', '.cooling_system',
                                        '.propellant_tanks',
                                        '.injection_system',
                                        '.injector_design',
                                        '.nozzle_angles',
                                        '.manufacturing_analysis')):
            continue
        if deger is None or len(str(deger)) < 20:
            kisa.append((anahtar, deger))
    assert not kisa, f'içi boş beyan: {kisa}'


# ---------------------------------------------------------------------------
# 3) KUSUR 1 — manifold oranları artık totoloji değil
# ---------------------------------------------------------------------------

def test_manifold_orani_gerceklenen_alandan_cikiyor(base):
    """Oran, yayımlanan çaptan ve GERÇEK orifis alanından geri hesaplanmalı."""
    detail = _leaf(base, 'injection_system.injector_design_detail')
    for ad in ('ox_circuit', 'fuel_circuit'):
        circ = detail[ad]
        if circ is None:
            continue
        man = circ['manifold']
        a_man = np.pi * (man['d_mm'] * 1e-3) ** 2 / 4.0
        a_orifis = circ['total_area_mm2'] * 1e-6
        assert man['area_ratio'] == pytest.approx(a_man / a_orifis, rel=1e-9), (
            f'{ad}: area_ratio yayımlanan geometriden çıkmıyor')
        # Süreklilik: v_ratio ile area_ratio karşılıklı olmak ZORUNDA.
        assert man['v_ratio'] * man['area_ratio'] == pytest.approx(1.0,
                                                                  rel=1e-9)
        # Ölü bekçi sabitleri artık gerçekten karşılaştırmaya giriyor.
        assert man['v_ratio_within_limit'] is (
            man['v_ratio'] <= MANIFOLD_V_RATIO_MAX)
        assert man['area_ratio_within_limit'] is (
            man['area_ratio'] >= MANIFOLD_AREA_RATIO_MIN)
        assert man['v_ratio_target'] == MANIFOLD_V_RATIO_TARGET
        assert man['v_ratio_target_is_target'] is True


def test_manifold_totolojisi_isaretleniyor():
    """SPI devresi özdeşliktir ve öyle bildirilir; NHNE devresi ayrılır.

    Eski kod ikisini de "gerçeklenen oran" diye sunuyordu. SPI'de
    A = mdot/(rho*v) bir ÖZDEŞLİK olduğu için oran hedefi tekrarlar; N2O
    devresinde alan iki fazlı kütle akısından çözüldüğü için ayrışır. Fark
    ölçülebilir olmalı, yoksa alan hâlâ hiçbir şey ölçmüyor demektir.
    """
    spi = design_injector({
        'motor_type': 'liquid', 'injector_type': 'impinging_doublet',
        'mdot_ox': 10.0, 'mdot_fuel': 4.0, 'rho_ox': 1141.0,
        'rho_fuel': 815.0, 'Pc_bar': 60.0})
    for ad in ('ox_circuit', 'fuel_circuit'):
        man = spi[ad]['manifold']
        assert spi[ad]['flow_model'] == 'SPI'
        assert man['v_ratio_is_tautological'] is True
        assert man['v_ratio'] == pytest.approx(MANIFOLD_V_RATIO_TARGET,
                                               abs=1e-9)

    nhne = design_injector({
        'motor_type': 'hybrid', 'mdot_ox': 1.2, 'Pc_bar': 30.0,
        'fluid_ox': 'n2o', 'T_ox_K': 293.15})
    man = nhne['ox_circuit']['manifold']
    assert nhne['ox_circuit']['flow_model'] == 'NHNE'
    assert man['v_ratio_is_tautological'] is False
    assert abs(man['v_ratio'] - MANIFOLD_V_RATIO_TARGET) > 1e-3, (
        'NHNE devresinde oran hâlâ hedefin kendisi: totoloji geri gelmiş')
    # Bekçi sınırları hâlâ sağlanıyor (kural gerçekten sınanıyor).
    assert man['v_ratio'] <= MANIFOLD_V_RATIO_MAX
    assert man['area_ratio'] >= MANIFOLD_AREA_RATIO_MIN


def test_manifold_hedef_literali_geri_gelmedi():
    """``1.0 / MANIFOLD_V_RATIO_TARGET`` biçimi kaynakta kalmamalı."""
    kaynak = (_ROOT / 'hrma' / 'engines' / 'injector_design.py').read_text(
        encoding='utf-8')
    assert '1.0 / MANIFOLD_V_RATIO_TARGET' not in kaynak
    # Bekçi sabitleri en az bir KARŞILAŞTIRMADA geçmeli (ölü sabit yasağı).
    assert kaynak.count('MANIFOLD_V_RATIO_MAX') >= 2
    assert kaynak.count('MANIFOLD_AREA_RATIO_MIN') >= 2


# ---------------------------------------------------------------------------
# 4) KUSUR 2 — besleme hattı boyunun ÇİFT TANIMI
# ---------------------------------------------------------------------------

def test_hat_boyu_tek_kaynaktan(base):
    """Ekrandaki boy ile basınç düşümünün varsaydığı boy AYNI sabit olmalı."""
    for ad in ('oxidizer_main', 'fuel_main'):
        line = _leaf(base, f'feed_system.feed_lines.{ad}')
        assert line['length'] == FEED_LINE_LENGTH_DEFAULT_M
        assert 'FEED_LINE_LENGTH_DEFAULT_M' in line['length_basis']


def test_hat_boyu_literali_kaynakta_kalmadi():
    """``'length': 2.5`` literali geri gelirse iki değer sessizce ayrışır."""
    kaynak = (_ROOT / 'hrma' / 'engines'
              / 'liquid_rocket_engine.py').read_text(encoding='utf-8')
    assert "'length': 2.5" not in kaynak
    assert "'ld_ratio': 2.5" not in kaynak
    assert 'ld_ratio = 2.5' not in kaynak


def test_hat_boyu_basinc_dusumune_giriyor(base):
    """Boy gerçekten hesapta: hattı uzatınca hat basınç düşümü artmalı.

    Beyan "aynı boy Darcy-Weisbach hat kaybını da sürüyor" diyor. İddia
    ölçülür: sabit dörde katlanınca ``pressure_drops.oxidizer_line.feed_lines``
    de dörde katlanmalı (ΔP_hat ∝ L).
    """
    import hrma.engines.liquid_rocket_engine as mod
    eski = mod.FEED_LINE_LENGTH_DEFAULT_M
    dp0 = _leaf(base, 'feed_system.pressure_drops.oxidizer_line.feed_lines')
    try:
        mod.FEED_LINE_LENGTH_DEFAULT_M = eski * 4.0
        dp1 = _leaf(_run(),
                    'feed_system.pressure_drops.oxidizer_line.feed_lines')
    finally:
        mod.FEED_LINE_LENGTH_DEFAULT_M = eski
    assert dp1 > dp0 * 1.5, (
        'hat boyu dörde katlandı ama hat basınç düşümü kıpırdamadı')


# ---------------------------------------------------------------------------
# 5) KUSUR 3 / BEYAN ÇÜRÜMESİ — kanal genişliği sabit, DERİNLİĞİ değil
# ---------------------------------------------------------------------------

def test_kanal_genisligi_sabit_derinligi_degil(base, buyuk):
    """Eski tek metin ("not auto-sized") derinlik için YALANDI. Ölçülür."""
    w0 = _leaf(base, 'cooling_system.channel_width_mm')
    w1 = _leaf(buyuk, 'cooling_system.channel_width_mm')
    h0 = _leaf(base, 'cooling_system.channel_height_mm')
    h1 = _leaf(buyuk, 'cooling_system.channel_height_mm')

    assert w0 == w1 == pytest.approx(COOLING_CHANNEL_WIDTH_DEFAULT_M * 1e3)
    assert h0 == pytest.approx(COOLING_CHANNEL_HEIGHT_DEFAULT_M * 1e3)
    assert h1 > h0 * 2, (
        f'derinlik 25 kN -> 2 MN arasında büyümedi ({h0} -> {h1} mm); '
        'beyan "otomatik boyutlanıyor" diyorsa ölçüm de öyle demeli')
    assert _leaf(base, 'cooling_system.channel_height_auto_sized') is False
    assert _leaf(buyuk, 'cooling_system.channel_height_auto_sized') is True


def test_kanal_beyanlari_ayri_ve_sayinin_yaninda(base):
    """Beyan sayının olduğu blokta olmalı; tek metin ikisini anlatamaz."""
    cooling = _leaf(base, 'cooling_system')
    assert 'channel_width_basis' in cooling
    assert 'channel_height_basis' in cooling
    assert cooling['channel_width_basis'] != cooling['channel_height_basis']
    # Genişlik beyanı "auto-sized değil", derinlik beyanı "auto-sized" demeli.
    assert 'not auto-sized' in cooling['channel_width_basis'].lower()
    assert 'auto-sized' in cooling['channel_height_basis'].lower()
    assert f'{COOLANT_CHANNEL_TARGET_VELOCITY_MS:.0f} m/s' in \
        cooling['channel_height_basis']
    # Isıl koruma bloğu da AYNI iki metni taşır (sayı bir yerde, gerekçe
    # başka yerde kalmasın).
    tps = _leaf(base, 'thermal_protection')
    assert tps['channel_width_basis'] == cooling['channel_width_basis']
    assert tps['channel_height_basis'] == cooling['channel_height_basis']


def test_curuyen_beyan_metni_geri_gelmedi():
    kaynak = (_ROOT / 'hrma' / 'engines'
              / 'liquid_rocket_engine.py').read_text(encoding='utf-8')
    assert "'channel_section_source': 'design default" not in kaynak


# ---------------------------------------------------------------------------
# 6) Beyanlar YALAN mı? — her kalem kendi iddiasıyla ölçülür
# ---------------------------------------------------------------------------

def test_bafl_oraninin_olcek_degismezligi_dogru(base, buyuk):
    """Beyan "ölçekten bağımsız" diyor; iki uçta ölçülerek doğrulanır."""
    yol = ('propellant_tanks.oxidizer_tank.internal_structures'
           '.slosh_baffles')
    d0 = _leaf(base, 'propellant_tanks.oxidizer_tank.dimensions.diameter')
    d1 = _leaf(buyuk, 'propellant_tanks.oxidizer_tank.dimensions.diameter')
    assert d1 > d0 * 3, 'iki nokta yeterince ayrışmıyor, sınav anlamsız'

    b0 = _leaf(base, yol)[0]
    b1 = _leaf(buyuk, yol)[0]
    assert b0['open_area_ratio_achieved'] == pytest.approx(
        b1['open_area_ratio_achieved'], rel=1e-9)
    assert b0['hole_count'] == b1['hole_count']
    # Beyandaki mekanizma da doğru olmalı: delik alanı ve halka alanı D²
    # ile ölçekleniyor.
    assert b1['hole_diameter'] / b0['hole_diameter'] == pytest.approx(
        d1 / d0, rel=1e-6)


def test_seviye_probu_sayisi_yerlesim_listesinden(base):
    """Sayı ile yerleşim listesi ayrı yazılamaz — biri kayarsa öteki yalan."""
    for tank in ('oxidizer_tank', 'fuel_tank'):
        lvl = _leaf(base, f'propellant_tanks.{tank}.internal_structures'
                          f'.instrumentation.level_sensors')
        assert lvl['count'] == len(lvl['positions'])
        assert lvl['count'] == len(TANK_LEVEL_PROBE_POSITIONS)
        assert list(lvl['positions']) == list(TANK_LEVEL_PROBE_POSITIONS)


def test_rezerv_ve_ullage_beyani_hesabin_kendisi(base):
    """%15 / %5 sayıları boyutlandırmayı GERÇEKTEN sürüyor mu?"""
    ozet = _leaf(base, 'propellant_tanks.system_summary')
    assert ozet['safety_margin'] == pytest.approx(
        (TANK_PROPELLANT_RESERVE_FACTOR - 1.0) * 100.0)
    assert ozet['ullage_fraction'] == pytest.approx(
        TANK_ULLAGE_FRACTION * 100.0)
    # Yüklenen kütle = tüketilen x rezerv (beyanın söylediği ilişki).
    ox = _leaf(base, 'propellant_tanks.oxidizer_tank')
    mdot_ox = _leaf(base, 'feed_system.mass_flow_rates.oxidizer')
    tuketilen = mdot_ox * ozet['burn_time']
    assert ox['propellant_data']['mass'] == pytest.approx(
        tuketilen * TANK_PROPELLANT_RESERVE_FACTOR, rel=1e-6)


def test_ld_orani_tank_boyutlarini_gercekten_belirliyor(base):
    for tank in ('oxidizer_tank', 'fuel_tank'):
        dim = _leaf(base, f'propellant_tanks.{tank}.dimensions')
        assert dim['ld_ratio'] == TANK_LD_RATIO
        assert dim['length'] / dim['diameter'] == pytest.approx(TANK_LD_RATIO,
                                                               rel=1e-9)


def test_convergent_aci_tek_tanim_noktasi(base):
    """Aynı açı iki blokta yayımlanıyor; ikisi de TEK sabitten gelmeli."""
    assert _leaf(base, 'cooling_system.convergent_half_angle_deg') == \
        CONVERGENT_HALF_ANGLE_DEG
    assert _leaf(base, 'nozzle_angles.convergent_half_angle_deg') == \
        CONVERGENT_HALF_ANGLE_DEG
    # Yakınsak koni uzunluğu da AYNI açıdan çıkmalı (beyanın iddiası bu).
    cooling = _leaf(base, 'cooling_system')
    d_c = cooling['chamber_diameter'] / 1000.0
    d_t = _leaf(base, 'nozzle_angles.throat_diameter_mm') / 1000.0
    beklenen = ((d_c - d_t) / 2.0
                / np.tan(np.radians(CONVERGENT_HALF_ANGLE_DEG)) * 1000.0)
    assert cooling['convergent_length'] == pytest.approx(beklenen, rel=1e-6)


def test_kritik_weber_beyani_kendi_rolunu_dogru_anlatiyor(base):
    """Beyan, eşiğin GERÇEKTEN ne sürdüğünü söylemek zorunda.

    Ölçüldü: ``injector_design`` modülü çözdüğünde yayımlanan
    ``droplet_diameter`` modülün SMD korelasyonundan gelir; We_krit yalnız
    modül çökerse devreye giren yedek tahmini sürer. Beyan "damlacık çapı
    bundan çözülür" deseydi normal yolda YALAN olurdu — sözcükleri doğru
    ama iddiası yanlış bir cümle de kusurdur.
    """
    inj = _leaf(base, 'injection_system')
    assert inj['critical_weber_number'] == CRITICAL_WEBER_NUMBER
    metin = inj['critical_weber_number_basis'].lower()
    assert 'critical weber number' in metin
    assert 'not a computed weber number' in metin
    assert 'legacy fallback' in metin

    # İddianın ölçümü: yayımlanan damlacık çapı modülün SMD'sidir.
    smd = _leaf(base,
                'injection_system.injector_design_detail.atomization'
                '.smd_ox_um')
    assert inj['droplet_diameter'] == pytest.approx(smd, rel=1e-12)
    # Eşik değişse bile normal yolda çap KIPIRDAMAZ (beyanın dediği bu).
    import hrma.engines.liquid_rocket_engine as mod
    eski = mod.CRITICAL_WEBER_NUMBER
    try:
        mod.CRITICAL_WEBER_NUMBER = eski * 2
        d1 = _leaf(_run(), 'injection_system.droplet_diameter')
    finally:
        mod.CRITICAL_WEBER_NUMBER = eski
    assert d1 == pytest.approx(smd, rel=1e-12)


def test_emniyet_vanasi_sayisi_tank_kartlariyla_tutarli(base):
    """4 literali tank kartlarındaki 2 vanayla çelişiyordu; artık tutarlı."""
    sayi = _leaf(base, 'feed_system.pressurization.relief_valves')
    assert sayi == PROPELLANT_CIRCUIT_COUNT
    boyutlanan = sum(
        1 for tank in ('oxidizer_tank', 'fuel_tank')
        if _leaf(base, f'propellant_tanks.{tank}.internal_structures'
                       f'.instrumentation.relief_valve'))
    assert sayi == boyutlanan


def test_turemeyen_sensor_sayilari_uydurulmuyor(base):
    """Mimariden çıkmayan sayı "varsayım" diye etiketlenmez, KALDIRILIR."""
    ctrl = _leaf(base, 'feed_system.control_system')
    press = _leaf(base, 'feed_system.pressurization')
    for blok, alan in ((ctrl, 'pressure_sensors'),
                       (ctrl, 'temperature_sensors'),
                       (ctrl, 'flow_sensors'),
                       (press, 'check_valves'),
                       (press, 'pressurant_tanks')):
        assert blok[alan] is None, f'{alan} geri geldi'
        assert blok[f'{alan}_status'] == 'NOT_MODELLED'
        assert len(blok[f'{alan}_basis']) > 40


def test_topolojik_sayilar_mimari_sabitlerinden(base):
    """Topolojik kalemler literal değil, adlandırılmış sabitten gelmeli."""
    import hrma.engines.liquid_rocket_engine as mod
    ctrl = _leaf(base, 'feed_system.control_system')
    assert ctrl['main_valves'] == mod.PROPELLANT_CIRCUIT_COUNT
    assert ctrl['backup_valves'] == mod.PROPELLANT_CIRCUIT_COUNT
    assert ctrl['throttle_valves'] == mod.PROPELLANT_CIRCUIT_COUNT
    assert ctrl['gimbal_actuators'] == mod.GIMBAL_AXIS_COUNT
    assert ctrl['control_computers'] == mod.CONTROL_REDUNDANCY
    press = _leaf(base, 'feed_system.pressurization')
    assert press['pressure_regulators'] == (mod.PROPELLANT_CIRCUIT_COUNT
                                            * mod.CONTROL_REDUNDANCY)


def test_iso2768_toleransi_nominal_olcuden_araniyor(base, buyuk):
    """Sabit görünen 0,15 mm bir ARAMA sonucudur; bant değişince değişmeli."""
    kucuk = _leaf(base, 'manufacturing_analysis.critical_tolerances.features'
                        '.throat_diameter')
    genis = _leaf(buyuk, 'manufacturing_analysis.critical_tolerances.features'
                         '.throat_diameter')
    assert genis['nominal_mm'] > kucuk['nominal_mm'] * 3
    assert genis['tolerance_mm'] > kucuk['tolerance_mm'], (
        'boğaz çapı bandı aştığı hâlde tolerans kıpırdamadı: sayı '
        'aranmıyor, uyduruluyor demektir')
    assert 'iso 2768' in kucuk['tolerance_basis'].lower()
