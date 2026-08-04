"""Turbopompa boyutlandırma modülü (turbopump_sizing) doğrulama testleri.

Bekçi çapaları (yol haritası C1 — doğrulamasız teslim yok):

(a) Birim/boyut bekçileri: ABD özgül devir geleneğinin boyutsuz karşılığı
    Ns_US = 2733 * Omega_s katsayısı bağımsız türetilir; gpm/ft çevrimleri
    tanım değerleriyle sınanır.
(b) RL10A-3-3 tasarım noktası (PWA FR-1769, Tablo V-I;
    data/validation/turbopump_rl10a33_design_point.json): zincirin Ns
    değerleri dosyanın kendi türetilmiş çapraz kontrolleriyle (MR 5.0:
    LOX 845.4, yakıt kademe başına 503.8, toplam 299.6) ve kademe
    sayıları yayımlanmış mimariyle (yakıt 2, LOX 1) karşılaştırılır.
(c) RL10A-3-3A donanım geometrisi (NASA TM-107318;
    turbopump_rl10a33a_geometry.json): çark çapı ve türbin ortalama çapı
    tahminleri yayımlanmış donanımla karşılaştırılır. Toleranslar vaka
    belirsizliğinden türetilir ve her testte gerekçelendirilir (baş
    katsayısı bandı D ~ psi^-0.5 -> ~%10; LOX pompası geriye hesapla
    psi=0.73, jenerik bandın DIŞINDA -> %25).
(d) F-1 (Saturn V; Oefelein & Yang 1993, Tablo 2;
    turbopump_f1_saturnv.json): iki buçuk mertebe debi farkında ölçek
    bağımsızlığı — Ns çapraz kontrolleri (1127.0 / 2094.7), yayımlanmış
    5500 rpm'in emme zinciriyle tutarlılığı, indüser zorunluluğu
    (indüsersiz zincir 5500 rpm'e ULAŞAMAZ) ve NPSH marjı.
(e) Monotonluk: NPSH_avail düşerse N üst sınırı düşer; N artarsa
    NPSH_req artar ve marj düşer; baş artarsa kademe sayısı artar vb.
(f) Geçersiz aralık beyanları: sessiz ekstrapolasyon yok — sert aralık
    dışı ValueError, yumuşak bant dışı `validity` kaydı.

Merlin/RD-180 için TEST YOKTUR: turbopump_merlin_rd180_unavailable.json
birincil kaynak bulunamadığını kayıt altına alır; boşluk ikincil
derlemelerle doldurulmaz (sahte veri yasağı).
"""

import json
import math
import pathlib

import pytest

from hrma.analysis.turbopump_sizing import (
    npsh_available_m,
    head_from_pressure_rise_m,
    m3s_to_gpm,
    m_to_ft,
    specific_speed_us,
    suction_specific_speed_us,
    npsh_required_m,
    pump_stage_count,
    size_pump,
    size_turbine,
    size_turbopump,
    NSS_NO_INDUCER_MAX_US,
    NSS_INDUCER_DESIGN_US,
    NS_CENTRIFUGAL_MIN_US,
    NS_CENTRIFUGAL_MAX_US,
    PUMP_STAGES_MAX,
    HEAD_COEFF_DEFAULT,
    SPEED_DERATE_DEFAULT,
    TURBINE_STAGES_MAX,
    NOT_MODELLED,
)
from hrma.constants import G_0

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATION_DIR = REPO_ROOT / 'data' / 'validation'

# Birim çevrimleri — tanım gereği kesin değerler (testte bağımsız yazılır
# ki modüldeki bir yazım hatası kendi kendini doğrulamasın). Türetilenler
# literal yerine tanımdan kurulur (parametre tutarlılık kuralı).
FT_M = 0.3048                      # 1 ft [m], kesin tanım
INCH_M = 0.0254                    # 1 in [m], kesin tanım
LB_KG = 0.45359237                 # 1 lb [kg], kesin tanım
LBF_N = LB_KG * G_0                # 1 lbf [N] = lb * g_0 (kesin)
PSI_PA = LBF_N / INCH_M ** 2       # 1 psi [Pa] (~6894.757)
HP_W = 550.0 * FT_M * LBF_N        # 1 hp (mekanik) = 550 ft*lbf/s [W]
LBFT3_KGM3 = LB_KG / FT_M ** 3     # lb/ft^3 -> kg/m^3 (~16.0185)


def _load(name):
    return json.loads((VALIDATION_DIR / name).read_text(encoding='utf-8'))


# ===========================================================================
# (a) Birim ve boyut bekçileri
# ===========================================================================
class TestBirimVeBoyut:
    def test_ns_us_dimensionless_conversion(self):
        """Omega_s = 1 (rad/s, m^3/s, m) -> Ns_US = 2733 (bilinen katsayı).

        Katsayı burada modülden BAĞIMSIZ kurulur: omega = 1 rad/s
        = 60/(2*pi) rpm, Q = 1 m^3/s, g*H = 1 m^2/s^2 -> H = 1/g m.
        """
        n_rpm = 60.0 / (2.0 * math.pi)
        q_gpm = m3s_to_gpm(1.0)
        h_ft = m_to_ft(1.0 / G_0)
        assert specific_speed_us(n_rpm, q_gpm, h_ft) == pytest.approx(
            2733.0, rel=1e-3)

    def test_gpm_ft_tanimlari(self):
        """gpm ve ft çevrimleri kesin tanımlarla birebir."""
        assert m3s_to_gpm(231.0 * 0.0254 ** 3 / 60.0) == pytest.approx(
            1.0, rel=1e-12)
        assert m_to_ft(0.3048) == pytest.approx(1.0, rel=1e-12)

    def test_npsh_available_hand_calc(self):
        """(3e5 - 2e3 - 1e5) Pa / (1000 kg/m^3 * g) = 20.19 m (el hesabı)."""
        expected = (3e5 - 2e3 - 1e5) / (1000.0 * G_0)
        assert npsh_available_m(3e5, 1e5, 1000.0, 2e3) == pytest.approx(
            expected, rel=1e-12)

    def test_head_from_pressure_rise_hand_calc(self):
        """H = dP/(rho*g): 9.80665e6 Pa / (1000*g) = 1000 m (tam)."""
        assert head_from_pressure_rise_m(9.80665e6, 1000.0) == pytest.approx(
            1000.0, rel=1e-12)

    def test_npsh_required_roundtrip(self):
        """Nss(N, Q, NPSH_req(N, Q, Nss)) = Nss (Eş. 2 <-> Eş. 4 tersleri)."""
        n, q, nss = 12000.0, 0.05, 25000.0
        npsh = npsh_required_m(n, q, nss)
        assert suction_specific_speed_us(
            n, m3s_to_gpm(q), m_to_ft(npsh)) == pytest.approx(nss, rel=1e-9)


# ===========================================================================
# (b) RL10A-3-3 tasarım noktası — MR 5.0 sütunu (indeks 1)
# ===========================================================================
@pytest.fixture(scope='module')
def rl10():
    return _load('turbopump_rl10a33_design_point.json')


@pytest.fixture(scope='module')
def rl10_geom():
    return _load('turbopump_rl10a33a_geometry.json')


def _rl10_fuel_case(rl10, **overrides):
    """RL10 yakıt pompası zinciri, yayımlanmış MR 5.0 değerleriyle.

    NPSH ve buhar basıncı RL10 için YAYIMLANMAMIŞTIR (geometri dosyasının
    NOT_PUBLISHED beyanı); bu yüzden vapor_pressure=0 + tank=giriş toplam
    basıncı yalnız zinciri yürütmek için verilir ve NPSH/indüser alanları
    bu vakalarda TEST EDİLMEZ. Basınç yükselişi dP = rho*g*H_yayım ile
    kurulur ki Ns/çap zinciri baş belirsizliğinden arınmış sınansın.
    """
    fp = rl10['expected_outputs']['fuel_pump']
    rho = fp['inlet_density_lb_ft3'][1] * LBFT3_KGM3
    args = dict(
        mass_flow_kg_s=rl10['inputs']['fuel_flow_lb_s'][1] * LB_KG,
        pressure_rise_Pa=rho * G_0 * fp['head_rise_ft'][1] * FT_M,
        density_kg_m3=rho,
        vapor_pressure_Pa=0.0,
        tank_pressure_Pa=fp['inlet_total_pressure_psia'][1] * PSI_PA,
        shaft_speed_rpm=fp['speed_rpm'][1],
    )
    args.update(overrides)
    return size_turbopump(**args)


def _rl10_ox_case(rl10):
    op = rl10['expected_outputs']['oxidizer_pump']
    rho = op['inlet_density_lb_ft3'][1] * LBFT3_KGM3
    return size_turbopump(
        mass_flow_kg_s=rl10['inputs']['oxidizer_flow_lb_s'][1] * LB_KG,
        pressure_rise_Pa=rho * G_0 * op['head_rise_ft'][1] * FT_M,
        density_kg_m3=rho,
        vapor_pressure_Pa=0.0,
        tank_pressure_Pa=op['inlet_total_pressure_psia'][1] * PSI_PA,
        shaft_speed_rpm=op['speed_rpm'][1])


class TestRL10TasarimNoktasi:
    def test_debi_ic_tutarlilik(self, rl10):
        """mdot/rho yayımlanmış gpm ile tutmalı (yakıt 580.9, LOX 183.7).

        Tolerans %0.5: kaynak tablo değerleri 3-4 anlamlı basamak.
        """
        res_f = _rl10_fuel_case(rl10)
        res_o = _rl10_ox_case(rl10)
        assert res_f['pump']['volumetric_flow_gpm'] == pytest.approx(
            580.9, rel=5e-3)
        assert res_o['pump']['volumetric_flow_gpm'] == pytest.approx(
            183.7, rel=5e-3)

    def test_ns_capraz_kontrolleri(self, rl10):
        """Ns zinciri, dosyanın türetilmiş çapraz kontrolleriyle (MR 5.0).

        Tolerans %0.5: çapraz kontroller aynı formülle yayımlanmış
        sayılardan türetildi; fark yalnız yuvarlamadan gelebilir.
        """
        derived = rl10['derived_cross_checks'][
            'specific_speed_us_rpm_gpm_ft']
        res_f = _rl10_fuel_case(rl10)
        res_o = _rl10_ox_case(rl10)
        assert res_o['pump']['specific_speed_overall_us'] == pytest.approx(
            derived['oxidizer_pump_MR5.0'], rel=5e-3)
        assert res_f['pump']['specific_speed_overall_us'] == pytest.approx(
            derived['fuel_pump_overall_MR5.0'], rel=5e-3)
        assert res_f['pump']['specific_speed_per_stage_us'] == pytest.approx(
            derived['fuel_pump_per_stage_MR5.0'], rel=5e-3)

    def test_kademe_sayilari(self, rl10):
        """Yakıt pompası 2 kademe (yayımlanmış stages=2), LOX 1 kademe.

        Kademe kuralı (Ns_kademe >= 500) yayımlanmış mimariyi hiçbir
        ayar katsayısı olmadan yeniden üretmeli.
        """
        assert rl10['expected_outputs']['fuel_pump']['stages'] == 2
        assert _rl10_fuel_case(rl10)['pump']['stage_count'] == 2
        assert _rl10_ox_case(rl10)['pump']['stage_count'] == 1

    def test_yakit_cark_capi(self, rl10, rl10_geom):
        """Yakıt çark çapı tahmini yayımlanmış 7.07 in'e karşı, %15 tolerans.

        Gerekçe: donanımdan geriye hesap psi = 0.60 (bant ucu), varsayılan
        psi = 0.50 -> D ~ psi^-0.5 sistematik +%9.5 sapar; kalan pay tablo
        yuvarlamaları için. Hesaplanan sapma ~+%10.
        """
        pub_in = rl10_geom['expected_outputs']['hardware_geometry'][
            'fuel_pump_impeller_diameter_in']['stage1']
        res = _rl10_fuel_case(rl10)
        d_in = res['pump']['impeller_diameter_in']
        assert d_in == pytest.approx(pub_in, rel=0.15)
        lo, hi = res['pump']['impeller_diameter_band_m']
        assert lo < res['pump']['impeller_diameter_m'] < hi

    def test_lox_cark_capi(self, rl10, rl10_geom):
        """LOX çark çapı tahmini yayımlanmış 4.2 in'e karşı, %25 tolerans.

        Gerekçe: geriye hesap psi = 0.73 — jenerik tasarım bandının
        (0.40-0.60) DIŞINDA (düşük özgül devirli, dişli tahrikli pompa;
        modül docstring'i bu vakayı sert bandın gerekçesi olarak anar).
        psi 0.50 -> 0.73 farkı D'de sqrt(0.73/0.50)-1 = +%21 sistematik
        sapma demektir; tolerans bunu kapsayacak şekilde %25 seçildi.
        """
        pub_in = rl10_geom['expected_outputs']['hardware_geometry'][
            'lox_pump_impeller_diameter_in']
        d_in = _rl10_ox_case(rl10)['pump']['impeller_diameter_in']
        assert d_in == pytest.approx(pub_in, rel=0.25)

    def test_turbin_kademe_ve_cap(self, rl10, rl10_geom):
        """Türbin: 2 kademe (yayımlanmış mimari) ve 5.9 in'e karşı %15.

        dh_ideal üçlüden kurulur: P/(mdot*eta), MR 5.0 sütunu (667.8 hp,
        5.35 lb/s, %72.9). Tolerans gerekçesi: geometri A-3-3A donanımı,
        çalışma noktası A-3-3 tasarım tahmini (varyant farkı) + hız oranı
        yaklaşıklığı; hesaplanan sapma ~+%5.
        """
        turb = rl10['expected_outputs']['turbine']
        res = _rl10_fuel_case(
            rl10,
            turbine_power_W=turb['horsepower'][1] * HP_W,
            turbine_mass_flow_kg_s=turb['flow_lb_s'][1] * LB_KG,
            turbine_efficiency=turb['efficiency_pct'][1] / 100.0)
        arch = rl10_geom['inputs']['turbine_architecture']
        assert 'iki kademeli' in arch  # yayımlanmış mimari: 2 kademe
        assert res['turbine']['stage_count'] == 2
        pub_in = rl10_geom['expected_outputs']['hardware_geometry'][
            'turbine_meanline_diameter_in']
        assert res['turbine']['mean_diameter_in'] == pytest.approx(
            pub_in, rel=0.15)

    def test_turbin_girdisi_yoksa_none_ve_beyanli(self, rl10):
        """Türbin girdisi verilmezse turbine=None + NOT_SIZED beyanı
        (sahte veri yasağı: hesaplanmayan gösterilmez)."""
        res = _rl10_ox_case(rl10)  # LOX mili dişliden tahrikli, türbinsiz
        assert res['turbine'] is None
        assert 'NOT_SIZED' in res['turbine_basis']


# ===========================================================================
# (d) F-1 (Saturn V) — büyük ölçek, düşük devir
# ===========================================================================
@pytest.fixture(scope='module')
def f1():
    return _load('turbopump_f1_saturnv.json')


# F-1 pompa girişleri doymuşa yakın kabul edilir; buhar basıncı girdileri:
# RP-1 @ 289 K: ~2 kPa (ağır kerosen, ihmal mertebesi; girişin < %1'i).
# LOX @ 90 K: ~100 kPa — O2 normal kaynama noktası 90.19 K / 101.325 kPa,
# dosyadaki giriş sıcaklığı 90 K => doymuş varsayım ~2 kPa içinde doğru.
F1_PV_RP1_PA = 2.0e3
F1_PV_LOX_PA = 1.0e5


def _f1_case(f1, pump_key, pv_pa, **overrides):
    p = f1['expected_outputs'][pump_key]
    rho = p['inlet_density_kg_m3']
    args = dict(
        mass_flow_kg_s=p['mass_flow_kg_s'],
        pressure_rise_Pa=rho * G_0 * p['developed_head_m'],
        density_kg_m3=rho,
        vapor_pressure_Pa=pv_pa,
        tank_pressure_Pa=p['inlet_pressure_kpa'] * 1e3,
    )
    args.update(overrides)
    return size_turbopump(**args)


class TestF1SaturnV:
    def test_debi_ic_tutarlilik(self, f1):
        """mdot/rho yayımlanmış gpm ile tutmalı (15600 / 25000, %1)."""
        res_f = _f1_case(f1, 'fuel_pump', F1_PV_RP1_PA,
                         shaft_speed_rpm=5500.0)
        res_o = _f1_case(f1, 'oxidizer_pump', F1_PV_LOX_PA,
                         shaft_speed_rpm=5500.0)
        assert res_f['pump']['volumetric_flow_gpm'] == pytest.approx(
            15600.0, rel=1e-2)
        assert res_o['pump']['volumetric_flow_gpm'] == pytest.approx(
            25000.0, rel=1e-2)

    def test_ns_capraz_kontrolleri(self, f1):
        """Ns zinciri dosyanın türetilmiş değerleriyle (1127.0 / 2094.7).

        Tolerans %0.5: türetme aynı formülle, fark yalnız yuvarlama.
        """
        derived = f1['derived_cross_checks']['specific_speed_us_rpm_gpm_ft']
        res_f = _f1_case(f1, 'fuel_pump', F1_PV_RP1_PA,
                         shaft_speed_rpm=f1['expected_outputs']['shaft'][
                             'speed_rpm'])
        res_o = _f1_case(f1, 'oxidizer_pump', F1_PV_LOX_PA,
                         shaft_speed_rpm=5500.0)
        assert res_f['pump']['specific_speed_overall_us'] == pytest.approx(
            derived['fuel_pump'], rel=5e-3)
        assert res_o['pump']['specific_speed_overall_us'] == pytest.approx(
            derived['oxidizer_pump'], rel=5e-3)

    def test_kademe_sayilari_tek(self, f1):
        """Her iki pompa tek kademeli santrifüj (yayımlanmış mimari)."""
        assert _f1_case(f1, 'fuel_pump', F1_PV_RP1_PA,
                        shaft_speed_rpm=5500.0)['pump']['stage_count'] == 1
        assert _f1_case(f1, 'oxidizer_pump', F1_PV_LOX_PA,
                        shaft_speed_rpm=5500.0)['pump']['stage_count'] == 1

    def test_bas_basinc_tutarliligi(self, f1):
        """Gerçek dP'den baş: yayımlanmış başla %2 içinde.

        Dosyanın kendi çapraz kontrolü aynı sapmayı raporlar (yakıt %1.7,
        LOX %0.3) — tolerans oradan alındı.
        """
        fp = f1['expected_outputs']['fuel_pump']
        dp = (fp['discharge_pressure_kpa'] - fp['inlet_pressure_kpa']) * 1e3
        h = head_from_pressure_rise_m(dp, fp['inlet_density_kg_m3'])
        assert h == pytest.approx(fp['developed_head_m'], rel=2e-2)
        op = f1['expected_outputs']['oxidizer_pump']
        dp = (op['discharge_pressure_kpa'] - op['inlet_pressure_kpa']) * 1e3
        h = head_from_pressure_rise_m(dp, op['inlet_density_kg_m3'])
        assert h == pytest.approx(op['developed_head_m'], rel=2e-2)

    def test_devir_secimi_yayimlanmis_5500_ile_tutarli(self, f1):
        """Devir seçim zinciri yayımlanmış 5500 rpm ile tutarlı olmalı.

        LOX pompası bağlayıcı taraftır (daha büyük debi + daha düşük
        NPSH). Nss hedefi 30000 (indüserli tasarım orta değeri) ve 0.9
        marj çarpanıyla seçilen devir ~5500 çıkar; ama hedef Nss bandı
        20000-50000 olduğundan birebir eşitlik İDDİA EDİLMEZ — yayımlanmış
        devrin [0.6, 1.67] bandında kalması (bant oranı = 20000/30000 ..
        50000/30000) ve emme sınırının altında olması test edilir.
        """
        res_o = _f1_case(f1, 'oxidizer_pump', F1_PV_LOX_PA)
        res_f = _f1_case(f1, 'fuel_pump', F1_PV_RP1_PA)
        pub = f1['expected_outputs']['shaft']['speed_rpm']
        sel = res_o['shaft_speed']['selected_rpm']
        assert res_o['shaft_speed']['mode'] == 'suction_limited'
        assert 0.6 <= pub / sel <= 1.67
        # Yayımlanmış devir emme sınırlı azami devrin altında:
        assert pub <= res_o['shaft_speed']['suction_limited_max_rpm']
        # LOX tarafı bağlayıcı: yakıt tarafının seçimi daha yüksek çıkar.
        assert (res_f['shaft_speed']['selected_rpm']
                > res_o['shaft_speed']['selected_rpm'])
        # Marj çarpanı 0.9 -> NPSH marj oranı 0.9^(-4/3) ~ 1.15.
        assert res_o['npsh']['margin_ratio'] == pytest.approx(
            SPEED_DERATE_DEFAULT ** (-4.0 / 3.0), rel=1e-6)

    def test_induser_zorunlu(self, f1):
        """5500 rpm'de her iki pompa indüser İSTER (tarihsel gerçek).

        Gerekli Nss: yakıt ~18100, LOX ~27000 — ikisi de indüsersiz
        bandın (<= 11000) çok üstünde.
        """
        for key, pv in (('fuel_pump', F1_PV_RP1_PA),
                        ('oxidizer_pump', F1_PV_LOX_PA)):
            res = _f1_case(f1, key, pv, shaft_speed_rpm=5500.0)
            ind = res['pump']['inducer']
            assert ind['required'] is True
            assert ind['status'] == 'required'
            nss_req = res['npsh']['suction_specific_speed_required_us']
            assert nss_req > NSS_NO_INDUCER_MAX_US

    def test_indusersiz_5500e_ulasilamaz(self, f1):
        """İndüsersiz seçim zinciri 5500 rpm'in yakınına bile gelemez.

        LOX tarafında indüsersiz emme sınırı ~1630 rpm — yayımlanmış
        devrin üçte birinden az. (F-1 indüserlerinin varlık sebebi.)
        """
        res = _f1_case(f1, 'oxidizer_pump', F1_PV_LOX_PA,
                       inducer_allowed=False)
        assert res['shaft_speed']['selected_rpm'] < 0.5 * 5500.0

    def test_npsh_marji_pozitif(self, f1):
        """Yayımlanmış 5500 rpm'de, indüserli kabiliyette marj pozitif."""
        for key, pv in (('fuel_pump', F1_PV_RP1_PA),
                        ('oxidizer_pump', F1_PV_LOX_PA)):
            res = _f1_case(f1, key, pv, shaft_speed_rpm=5500.0)
            assert res['npsh']['margin_m'] > 0.0
            assert res['npsh']['margin_ratio'] > 1.0
            assert res['npsh']['required_m'] < res['npsh']['available_m']


# ===========================================================================
# (e) Monotonluk ve boyut analizi
# ===========================================================================
# Sentetik test akışkanı (su benzeri) — yalnız matematiksel davranış
# sınanır, fiziksel vaka iddiası yoktur.
_BASE = dict(mass_flow_kg_s=50.0, pressure_rise_Pa=8.0e6,
             density_kg_m3=1000.0, vapor_pressure_Pa=3.0e3,
             tank_pressure_Pa=4.0e5, line_pressure_drop_Pa=2.0e4)


class TestMonotonluk:
    def test_npsh_avail_monotonlugu(self):
        """Tank basıncı artarsa NPSH artar; buhar basıncı/hat kaybı
        artarsa düşer."""
        base = npsh_available_m(4e5, 3e3, 1000.0, 2e4)
        assert npsh_available_m(5e5, 3e3, 1000.0, 2e4) > base
        assert npsh_available_m(4e5, 5e4, 1000.0, 2e4) < base
        assert npsh_available_m(4e5, 3e3, 1000.0, 8e4) < base

    def test_npsh_duserse_devir_ust_siniri_duser(self):
        """C1 bekçisi: NPSH_avail düşerse hem emme sınırı hem seçilen
        devir düşer."""
        hi = size_turbopump(**_BASE)
        lo = size_turbopump(**{**_BASE, 'tank_pressure_Pa': 2.0e5})
        assert (lo['npsh']['available_m'] < hi['npsh']['available_m'])
        assert (lo['shaft_speed']['suction_limited_max_rpm']
                < hi['shaft_speed']['suction_limited_max_rpm'])
        assert (lo['shaft_speed']['selected_rpm']
                < hi['shaft_speed']['selected_rpm'])

    def test_devir_artarsa_npsh_req_artar_marj_duser(self):
        n1 = size_turbopump(**_BASE, shaft_speed_rpm=4000.0)
        n2 = size_turbopump(**_BASE, shaft_speed_rpm=8000.0)
        assert n2['npsh']['required_m'] > n1['npsh']['required_m']
        assert n2['npsh']['margin_m'] < n1['npsh']['margin_m']
        # NPSH_req ~ N^(4/3) ölçeklemesi (boyut analizi):
        assert (n2['npsh']['required_m'] / n1['npsh']['required_m']
                == pytest.approx(2.0 ** (4.0 / 3.0), rel=1e-9))

    def test_devir_artarsa_cark_kuculur(self):
        """Sabit başta D2 ~ 1/N (aynı kademe sayısında)."""
        n1 = size_turbopump(**_BASE, shaft_speed_rpm=4000.0)
        n2 = size_turbopump(**_BASE, shaft_speed_rpm=8000.0)
        if n1['pump']['stage_count'] == n2['pump']['stage_count']:
            assert (n1['pump']['impeller_diameter_m']
                    / n2['pump']['impeller_diameter_m']
                    == pytest.approx(2.0, rel=1e-9))
        else:  # kademe değiştiyse en azından küçülme yönü korunur
            assert (n2['pump']['impeller_diameter_m']
                    < n1['pump']['impeller_diameter_m'])

    def test_bas_artarsa_kademe_artar(self):
        """Ns ~ H^-0.75: baş yeterince artarsa kademe sayısı artmalı."""
        lo = size_turbopump(**{**_BASE, 'pressure_rise_Pa': 2.0e6},
                            shaft_speed_rpm=6000.0)
        hi = size_turbopump(**{**_BASE, 'pressure_rise_Pa': 6.0e7},
                            shaft_speed_rpm=6000.0)
        assert hi['pump']['stage_count'] >= lo['pump']['stage_count']
        assert hi['pump']['stage_count'] > 1

    def test_induser_durumu_devirle_gecis(self):
        """Düşük devirde indüser gerekmez, yüksek devirde gerekir."""
        lo = size_turbopump(**_BASE, shaft_speed_rpm=1000.0)
        hi = size_turbopump(**_BASE, shaft_speed_rpm=20000.0)
        assert lo['pump']['inducer']['status'] == 'not_required'
        assert hi['pump']['inducer']['status'] == 'required'

    def test_turbin_monotonlugu(self):
        """dh_ideal artarsa kademe sayısı azalmaz; N artarsa çap küçülür."""
        t_lo = size_turbine(shaft_speed_rpm=20000.0,
                            ideal_specific_work_J_kg=2.0e5,
                            pump_tip_speed_m_s=250.0)
        t_hi = size_turbine(shaft_speed_rpm=20000.0,
                            ideal_specific_work_J_kg=8.0e5,
                            pump_tip_speed_m_s=250.0)
        assert t_hi['stage_count'] >= t_lo['stage_count']
        d1 = size_turbine(shaft_speed_rpm=10000.0,
                          ideal_specific_work_J_kg=3.0e5)
        d2 = size_turbine(shaft_speed_rpm=20000.0,
                          ideal_specific_work_J_kg=3.0e5)
        assert d1['mean_diameter_m'] / d2['mean_diameter_m'] == pytest.approx(
            2.0, rel=1e-9)

    def test_turbin_uclu_ve_dogrudan_dh_esdeger(self):
        """dh_ideal = P/(mdot*eta) yolu ile doğrudan dh yolu aynı sonucu
        vermeli (tanım tutarlılığı)."""
        via_triple = size_turbine(shaft_speed_rpm=15000.0, power_W=1.0e6,
                                  mass_flow_kg_s=4.0, efficiency=0.5)
        direct = size_turbine(shaft_speed_rpm=15000.0,
                              ideal_specific_work_J_kg=1.0e6 / (4.0 * 0.5))
        assert via_triple['mean_diameter_m'] == pytest.approx(
            direct['mean_diameter_m'], rel=1e-12)
        assert via_triple['stage_count'] == direct['stage_count']


# ===========================================================================
# (f) Geçersiz aralık beyanları ve dürüstlük bekçileri
# ===========================================================================
class TestGecerlilikBeyanlari:
    def test_negatif_ve_sifir_girdiler(self):
        for bad in ('mass_flow_kg_s', 'pressure_rise_Pa', 'density_kg_m3'):
            with pytest.raises(ValueError):
                size_turbopump(**{**_BASE, bad: 0.0})
            with pytest.raises(ValueError):
                size_turbopump(**{**_BASE, bad: -1.0})

    def test_buhar_basinci_tank_basincini_asarsa(self):
        """Giriş basıncı buhar basıncını aşmıyorsa NPSH<=0 -> ValueError."""
        with pytest.raises(ValueError, match='NPSH'):
            size_turbopump(**{**_BASE, 'vapor_pressure_Pa': 5.0e5})

    def test_bas_katsayisi_sert_aralik(self):
        """psi hard aralık (0.20-0.75) dışı: geçersiz aralık, sessiz
        ekstrapolasyon yok."""
        for bad_psi in (0.1, 0.9, 0.0, -0.5):
            with pytest.raises(ValueError, match='validity range'):
                size_turbopump(**_BASE, head_coefficient=bad_psi)

    def test_bas_katsayisi_yumusak_bant_beyani(self):
        """psi 0.70: sert aralık içinde ama tasarım bandı dışında ->
        hesap yapılır, validity kaydı düşülür."""
        res = size_turbopump(**_BASE, head_coefficient=0.70)
        fields = [v['field'] for v in res['validity']]
        assert 'head_coefficient' in fields

    def test_nss_hedefi_sert_aralik(self):
        for bad in (1000.0, 100000.0):
            with pytest.raises(ValueError, match='validity range'):
                size_turbopump(
                    **_BASE, target_suction_specific_speed_us=bad)

    def test_indusersiz_hedef_kirpilir(self):
        """inducer_allowed=False + yüksek hedef Nss: hedef kırpılır ve
        uyarı beyan edilir."""
        res = size_turbopump(**_BASE, inducer_allowed=False,
                             target_suction_specific_speed_us=30000.0)
        assert (res['npsh']['suction_specific_speed_capability_us']
                == NSS_NO_INDUCER_MAX_US)
        assert any('capped' in w for w in res['warnings'])

    def test_verilen_devir_emme_sinirini_asarsa_uyari(self):
        """Kullanıcı devri emme sınırını aşarsa: hesap yapılır, negatif
        marj + uyarı beyan edilir (sessiz geçilmez)."""
        res = size_turbopump(**_BASE, shaft_speed_rpm=1.0e5)
        assert res['npsh']['margin_m'] < 0.0
        assert any('exceeds the suction-limited maximum' in w
                   for w in res['warnings'])

    def test_kademe_kirpma_beyani(self):
        """Ns çok düşükse kademe PUMP_STAGES_MAX'ta kırpılır ve geçerlilik
        beyanı düşülür (sessiz ekstrapolasyon yok)."""
        res = size_turbopump(
            **{**_BASE, 'pressure_rise_Pa': 2.0e8, 'mass_flow_kg_s': 10.0},
            shaft_speed_rpm=3000.0)
        assert res['pump']['stage_count'] == PUMP_STAGES_MAX
        assert (res['pump']['specific_speed_per_stage_us']
                < NS_CENTRIFUGAL_MIN_US)
        assert any(v['status'] == 'out_of_validity'
                   for v in res['validity'])

    def test_karisik_akis_beyani(self):
        """Kademe Ns santrifüj bandın üstündeyse geçerlilik beyanı."""
        res = size_turbopump(
            **{**_BASE, 'pressure_rise_Pa': 5.0e5, 'mass_flow_kg_s': 1000.0},
            shaft_speed_rpm=30000.0)
        assert (res['pump']['specific_speed_per_stage_us']
                > NS_CENTRIFUGAL_MAX_US)
        assert any(v['field'] == 'specific_speed_per_stage_us'
                   for v in res['validity'])

    def test_turbin_eksik_girdi(self):
        with pytest.raises(ValueError, match='incomplete'):
            size_turbine(shaft_speed_rpm=10000.0, power_W=1e6)

    def test_turbin_kademe_kirpma_beyani(self):
        """Devasa dh + düşük hız zarfı: kademe 3'te kırpılır, beyan düşer."""
        t = size_turbine(shaft_speed_rpm=5000.0,
                         ideal_specific_work_J_kg=5.0e6,
                         pump_tip_speed_m_s=150.0)
        assert t['stage_count'] == TURBINE_STAGES_MAX
        assert any(v['status'] == 'out_of_validity' for v in t['validity'])
        assert (t['velocity_ratio_per_stage']
                < t['velocity_ratio_optimum_per_stage'])

    def test_turbin_lule_acisi_sert_aralik(self):
        with pytest.raises(ValueError, match='validity range'):
            size_turbine(shaft_speed_rpm=10000.0,
                         ideal_specific_work_J_kg=2e5, nozzle_angle_deg=5.0)

    def test_not_modelled_beyanlari(self):
        """NOT_MODELLED sözlüğü çıktıda eksiksiz: kavitasyon dinamiği,
        off-design haritası, rotordinamik, yapısal (+ akışkan özellikleri
        ve türbin akış ayrıntıları)."""
        res = size_turbopump(**_BASE)
        nm = res['not_modelled']
        for key in ('cavitation_dynamics', 'off_design_map',
                    'rotordynamics', 'structural', 'fluid_properties',
                    'turbine_flow_details'):
            assert key in nm and nm[key], key
        assert nm == NOT_MODELLED

    def test_basis_beyanlari_eksiksiz(self):
        """Her çıktı bloğunda _basis; ampirik alanlarda kaynak künyesi."""
        res = size_turbopump(
            **_BASE, turbine_ideal_specific_work_J_kg=3.0e5)
        assert 'Huzel' in res['shaft_speed']['_basis']
        assert 'NPSH' in res['npsh']['_basis']
        assert 'Sutton' in res['pump']['_basis']
        assert 'Huzel' in res['pump']['impeller_diameter_basis']
        assert 'NOT modelled' in res['pump']['blade_count_basis']
        assert 'Huzel' in res['pump']['inducer']['_basis']
        assert 'Huzel' in res['turbine']['_basis']

    def test_varsayilanlar_tek_kaynaktan(self):
        """Varsayılan psi ve Nss hedefi modül sabitlerinden gelmeli
        (parametre tutarlılık kuralı — magic number kopyası yok)."""
        res = size_turbopump(**_BASE)
        assert res['pump']['head_coefficient'] == HEAD_COEFF_DEFAULT
        assert (res['npsh']['suction_specific_speed_capability_us']
                == NSS_INDUCER_DESIGN_US)

    def test_kademe_sayisi_fonksiyonu(self):
        """pump_stage_count sınır davranışı: bant içinde 1; altında
        n^0.75 kuralı; tabanda kırpma."""
        assert pump_stage_count(NS_CENTRIFUGAL_MIN_US) == 1
        assert pump_stage_count(2000.0) == 1
        # Ns=300: (500/300)^(4/3) = 1.98 -> 2 kademe
        assert pump_stage_count(300.0) == 2
        assert pump_stage_count(1.0) == PUMP_STAGES_MAX
