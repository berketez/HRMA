"""Katı motor + emniyet analizinde uydurma sabit bırakılmadığının bekçisi.

2026-07-19 uydurma veri denetimi, katı motor ve emniyet zincirinde dokuz
bulgu çıkardı. Ortak kalıp aynıydı: kullanıcıya hesaplanmış gibi sunulan bir
sayı aslında sabitti (design/burst/relief basınçları, termal verim, yalıtım
etkinliği, kasa sıcaklığı, Isp kayıp kalemleri, grain gerilmesi) ya da
girdinin backend'e ulaşıp hiç okunmadığı bir ölü alandı (verim faktörleri,
motor_type, thrust, burn_time).

Bu dosya o sabitlerin geri gelmesini engeller. Ölçüt tek: kullanıcı bir
girdiyi değiştirdiğinde, o girdiye fiziksel olarak bağlı olan çıktı DEĞİŞMEK
zorundadır.
"""

import numpy as np
import pytest

# NOT (2026-07-25): burada argümansız ``warnings.filterwarnings('ignore')``
# vardı. Argümansız çağrı SÜREÇ GENELİNDE catch-all filtre kurar; bu test
# dosyası toplandığı anda tüm oturumda numpy'nin sıfıra bölme/geçersiz değer
# uyarılarını susturuyordu (pytest'in kendi uyarı özeti dâhil). Kaldırıldı —
# gerçekten susturulması gereken bir uyarı çıkarsa dar kapsamlı
# ``pytest.warns`` / ``warnings.catch_warnings()`` ile ve gerekçesiyle
# yapılır. Kaldırıldıktan sonra bu dosyada bastırılan gerçek bir uyarı
# çıkmadı (koşu temiz).

from hrma.analysis.safety_analysis import (
    SAFETY_MODEL,
    MOTOR_TYPE_TO_EXPLOSIVE_CLASS,
    SafetyAnalyzer,
)
from hrma.engines.solid_rocket_engine import (
    SOLID_CASE_DESIGN,
    SOLID_CONDENSED_MASS_FRACTION,
    SOLID_GRAIN_MECHANICS,
    SolidRocketEngine,
)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def solid(overrides=None, **ctor):
    params = dict(chamber_diameter=100, grain_length=500, core_diameter=30,
                  chamber_pressure=40)
    params.update(ctor)
    return SolidRocketEngine(overrides=overrides, **params).calculate_performance()


def safety(motor_data=None, **kwargs):
    # chamber_length + throat_diameter (parti 31 / F4-1): ısı zinciri artık
    # eksik girdiyle sayı UYDURMUYOR (HEAT_TRANSFER_REQUIRED_FIELDS +
    # boğaz ölçeği kapısı). Bu iki alan olmadan çağrı reddediliyor ve
    # safety_analysis kendi BEYANLI yedeğine (ortam sıcaklığı) düşüyordu;
    # sonuç: cidar sıcaklığı her koşuda 293,15 K çıkıyor ve "soğutma tipi
    # cidarı değiştirir" gibi bekçiler ölçtüklerini sanıp ölçmüyorlardı.
    # Kapı GEVŞETİLMEDİ; eksik olan gerçek girdiler verildi (katı motorun
    # zaten sahip olduğu ölçüler: 100 mm kamara, 500 mm boy, 30 mm boğaz).
    md = dict(chamber_pressure=40.0, chamber_temperature=3000.0, thrust=1000.0,
              burn_time=10.0, chamber_diameter=0.1, chamber_length=0.5,
              throat_diameter=0.03, wall_thickness=0.005)
    md.update(motor_data or {})
    # _dus: bir alanın YOKLUĞUNU sınamak isteyen bekçiler için (ör. ışıma
    # alanı varsayımının beyan edilip edilmediği). Varsayılanı silmek
    # test-içi bir kaçamak değil, sınanan durumun kendisidir.
    for _ad in kwargs.pop('_dus', ()):
        md.pop(_ad, None)
    params = dict(propellant_mass=5.0, propellant_type='composite',
                  material='steel_4130')
    params.update(kwargs)
    return SafetyAnalyzer().analyze_comprehensive_safety(md, **params)


# ---------------------------------------------------------------------------
# Bulgu 1 — katı motor emniyet basınçları sabitti (100 / 150 / 85 bar)
# ---------------------------------------------------------------------------
class TestSolidSafetyPressuresAreComputed:

    def test_pressures_scale_with_chamber_pressure(self):
        low = solid()['safety_analysis']['pressure_safety']
        high = solid(chamber_diameter=200, grain_length=900, core_diameter=60,
                     chamber_pressure=90)['safety_analysis']['pressure_safety']
        assert low['design_pressure_bar'] != high['design_pressure_bar']
        assert low['burst_pressure_bar'] != high['burst_pressure_bar']
        assert low['relief_valve_setting_bar'] != high['relief_valve_setting_bar']

    def test_burst_pressure_depends_on_case_material(self):
        steel = solid()['safety_analysis']['pressure_safety']
        alu = solid({'case_material': 'aluminum_6061'})['safety_analysis']['pressure_safety']
        assert alu['burst_pressure_bar'] < steel['burst_pressure_bar'], (
            'Aluminyum kasa celikten daha dusuk kopma basinci vermeli')

    def test_burst_pressure_depends_on_wall_thickness(self):
        thin = solid({'case_thickness': 3})['safety_analysis']['pressure_safety']
        thick = solid({'case_thickness': 20})['safety_analysis']['pressure_safety']
        assert thick['burst_pressure_bar'] > 3 * thin['burst_pressure_bar'], (
            'Kalin cidar cok daha yuksek kopma basinci vermeli')

    def test_burst_pressure_never_below_operating_pressure_for_a_sane_case(self):
        res = solid(chamber_pressure=200, chamber_diameter=200,
                    grain_length=900, core_diameter=60)
        ps = res['safety_analysis']['pressure_safety']
        assert ps['burst_pressure_bar'] > ps['max_operating_pressure_bar'], (
            'Kopma basinci isletme basincinin altinda raporlanamaz')

    def test_relief_setting_is_labelled_as_a_recommendation(self):
        ps = solid()['safety_analysis']['pressure_safety']
        assert 'recommendation' in ps['relief_valve_basis']
        assert np.isclose(
            ps['relief_valve_setting_bar'],
            ps['design_pressure_bar']
            * SOLID_CASE_DESIGN['relief_fraction_of_design'])

    def test_no_legacy_constants_remain(self):
        ps = solid()['safety_analysis']['pressure_safety']
        assert (ps['design_pressure_bar'], ps['burst_pressure_bar'],
                ps['relief_valve_setting_bar']) != (100, 150, 85)


# ---------------------------------------------------------------------------
# Bulgu 2 — termal analiz sabitleri (85.2 / 94.8 / 'Excellent' / 0.1 katsayısı)
# ---------------------------------------------------------------------------
class TestSolidThermalIsComputed:

    def test_case_temperature_depends_on_burn_time(self):
        short = solid(grain_length=200)
        long = solid(grain_length=1200)
        assert long['burn_time'] > short['burn_time']
        t_short = short['thermal_analysis']['heat_transfer']['case_temperature_k']
        t_long = long['thermal_analysis']['heat_transfer']['case_temperature_k']
        assert t_long != t_short, (
            'Kasa sicakligi yanma suresine duyarli olmali (eski formul '
            'yalniz alev sicakligina bagliydi)')

    def test_case_temperature_depends_on_insulation_thickness(self):
        thin = solid({'liner_thickness': 1})
        thick = solid({'liner_thickness': 10})
        t_thin = thin['thermal_analysis']['heat_transfer']['case_temperature_k']
        t_thick = thick['thermal_analysis']['heat_transfer']['case_temperature_k']
        assert t_thick < t_thin, 'Kalin yalitim kasayi daha soguk tutmali'

    def test_case_temperature_depends_on_case_thickness(self):
        thin = solid({'case_thickness': 3})
        thick = solid({'case_thickness': 20})
        t_thin = thin['thermal_analysis']['heat_transfer']['case_temperature_k']
        t_thick = thick['thermal_analysis']['heat_transfer']['case_temperature_k']
        assert t_thick < t_thin, 'Kalin kasa daha cok isi yutar, daha az isinir'

    def test_case_temperature_never_below_ambient_or_above_flame(self):
        res = solid()
        t = res['thermal_analysis']['heat_transfer']['case_temperature_k']
        assert 290.0 <= t <= res['thermal_analysis']['combustion_thermal'][
            'flame_temperature_k']

    def test_insulation_effectiveness_is_zero_without_a_liner(self):
        none = solid({'liner_thickness': 0.1})
        thick = solid({'liner_thickness': 20})
        e_none = none['thermal_analysis']['heat_transfer']['insulation_effectiveness']
        e_thick = thick['thermal_analysis']['heat_transfer']['insulation_effectiveness']
        assert e_thick > e_none
        assert e_none != 94.8 and e_thick != 94.8

    def test_thermal_efficiency_depends_on_propellant(self):
        apcp = solid()['thermal_analysis']['combustion_thermal']
        sugar = solid(propellant_type='knsu')['thermal_analysis']['combustion_thermal']
        assert apcp['thermal_efficiency_percent'] != sugar['thermal_efficiency_percent']
        assert apcp['thermal_efficiency_percent'] != 85.2
        assert 'definition' in ' '.join(apcp.keys())

    def test_protection_rating_follows_the_computed_margin(self):
        cool = solid({'liner_thickness': 20, 'case_thickness': 20})
        rating = cool['thermal_analysis']['heat_transfer']['thermal_protection_rating']
        limits = cool['thermal_analysis']['thermal_management'][
            'material_temperature_limits']
        assert limits['safety_margin_k'] == pytest.approx(
            limits['case_max_temp_k']
            - cool['thermal_analysis']['heat_transfer']['case_temperature_k'])
        assert rating in ('Excellent', 'Adequate', 'Marginal',
                          'Inadequate — case exceeds its service temperature')


# ---------------------------------------------------------------------------
# Bulgu 3 — Isp kayıp kalemleri sabitti (3.2 / 2.1 / 1.8 / 98.5)
# ---------------------------------------------------------------------------
class TestIspLossBreakdownIsComputed:

    def test_two_phase_loss_tracks_the_condensed_phase_fraction(self):
        apcp = solid()['detailed_analysis']['performance_metrics'][
            'theoretical_vs_actual_isp']
        db = solid(propellant_type='double_base')['detailed_analysis'][
            'performance_metrics']['theoretical_vs_actual_isp']
        assert apcp['two_phase_losses'] > 0.0, 'Metalize APCP iki-fazli kayip vermeli'
        assert db['two_phase_losses'] == 0.0, (
            'Dumansiz cift bazli yakit tek fazlidir, iki-fazli kayip olamaz')
        assert apcp['two_phase_losses'] != 1.8

    def test_two_phase_loss_is_declared_as_not_applied(self):
        loss = solid()['detailed_analysis']['performance_metrics'][
            'theoretical_vs_actual_isp']
        assert loss['two_phase_losses_applied'] is False, (
            'Itki katsayisina uygulanmayan bir kayip, uygulanmis gibi '
            'sunulamaz')
        assert 'X_p' in loss['two_phase_losses_basis']

    def test_nozzle_loss_follows_the_applied_efficiency(self):
        base = solid()['detailed_analysis']['performance_metrics'][
            'theoretical_vs_actual_isp']
        derated = solid({'nozzle_efficiency': 0.85})['detailed_analysis'][
            'performance_metrics']['theoretical_vs_actual_isp']
        assert derated['nozzle_losses'] > base['nozzle_losses']
        assert np.isclose(derated['nozzle_losses'],
                          100.0 * (1.0 - derated['nozzle_efficiency_applied']))
        assert base['nozzle_losses'] != 2.1

    def test_web_utilization_is_measured_not_assumed(self):
        a = solid()['detailed_analysis']['grain_regression_analysis'][
            'web_thickness_utilization']
        b = solid(core_diameter=60)['detailed_analysis'][
            'grain_regression_analysis']['web_thickness_utilization']
        assert a != 98.5
        assert 0.0 <= a <= 100.0 and 0.0 <= b <= 100.0


# ---------------------------------------------------------------------------
# Bulgu 4 — grain gerilmesi 2.5 MPa + Pc*0.1 sabiti
# ---------------------------------------------------------------------------
class TestGrainStressIsRealElasticity:

    def test_stress_depends_on_propellant_mechanical_properties(self):
        htpb = solid()['structural_analysis']['grain_structural']
        sugar = solid(propellant_type='knsu')['structural_analysis'][
            'grain_structural']
        assert sugar['max_grain_stress_mpa'] != htpb['max_grain_stress_mpa']
        assert sugar['grain_elastic_modulus_mpa'] != htpb['grain_elastic_modulus_mpa']

    def test_stress_depends_on_grain_geometry(self):
        narrow = solid(core_diameter=20)['structural_analysis']['grain_structural']
        wide = solid(core_diameter=70)['structural_analysis']['grain_structural']
        assert narrow['max_grain_stress_mpa'] != wide['max_grain_stress_mpa'], (
            'Grain gerilmesi port capina duyarli olmali (eski model yalniz '
            'Pc kullaniyordu)')

    def test_stress_depends_on_storage_temperature(self):
        warm = solid({'ambient_temp': 320})['structural_analysis']['grain_structural']
        cold = solid({'ambient_temp': 250})['structural_analysis']['grain_structural']
        assert abs(cold['thermal_only_bore_strain_percent']) > abs(
            warm['thermal_only_bore_strain_percent']), (
            'Kurlemeden daha cok soguyan grain daha cok buzulur')

    def test_not_the_old_closed_form(self):
        res = solid()['structural_analysis']['grain_structural']
        assert res['max_grain_stress_mpa'] != pytest.approx(2.5 + 40 * 0.1)

    def test_crack_risk_comes_from_strain_margin(self):
        res = solid()['structural_analysis']['grain_structural']
        assert res['strain_capability_percent'] > 0
        assert res['strain_safety_factor'] > 0
        expected = ('Low' if res['strain_safety_factor'] >= 2.0
                    else 'Medium' if res['strain_safety_factor'] >= 1.0 else 'High')
        assert res['crack_propagation_risk'] == expected

    def test_star_grain_reports_its_stress_concentration_assumption(self):
        star = solid(grain_type='star')['structural_analysis']['grain_structural']
        assert star['stress_concentration_factor'] > 1.0
        assert 'stress-concentration' in star['model_note']

    def test_second_grain_stress_source_agrees(self):
        """İkinci (eski) grain gerilme fonksiyonu artık aynı kaynağa bağlı."""
        engine = SolidRocketEngine(chamber_diameter=100, grain_length=500,
                                   core_diameter=30, chamber_pressure=40)
        assert engine._calculate_grain_hoop_stress() == pytest.approx(
            engine._calculate_grain_structural()['bore_hoop_stress_mpa'])

    def test_property_source_is_declared(self):
        res = solid()['structural_analysis']['grain_structural']
        assert res['grain_property_source']
        assert 'case-bonded' in res['bonding_assumption']
        # Yayımlanmış mekanik verisi olan TABAN kayıtlar:
        TABAN = {'apcp', 'double_base', 'sugar', 'knsu', 'black_powder'}
        # Bunların dışındaki her anahtar, mevcut bir kayda TAKMA AD olmak
        # zorundadır — yani yeni bir modül/Poisson/uzama sayısı UYDURULMAMIŞ
        # olmalı. (Eskiden bu satır düz bir beyaz listeydi; v2.6.26'da
        # kndx/knsb/kner şeker ailesine takma ad olarak bağlanınca kırıldı.
        # Öncesinde bu üçü sözlükte YOKTU ve motor sessizce HTPB kompozit
        # kaydına düşüyordu: KNDX grainine 6 MPa modül / %35 uzama atanıyor,
        # gerinim emniyeti 11.7 "Low" çıkıyordu; doğru şeker kaydıyla 0.91
        # "High". Yani anahtarı eklemek düzeltmenin kendisiydi.)
        taban_kimlikler = {id(SOLID_GRAIN_MECHANICS[k]) for k in TABAN
                           if k in SOLID_GRAIN_MECHANICS}
        for ad, kayit in SOLID_GRAIN_MECHANICS.items():
            if ad in TABAN:
                continue
            assert id(kayit) in taban_kimlikler, (
                f"'{ad}': taban kayitlarin hicbirine takma ad degil — bu "
                f"formulasyona ozgu yayimlanmis veri yoksa sayi uydurulmus "
                f"olabilir")


# ---------------------------------------------------------------------------
# Bulgu 5 — verim ve yapısal override'ları okunmuyordu
# ---------------------------------------------------------------------------
class TestOverridesActuallyApply:

    @staticmethod
    def _perf(res):
        return (round(res['average_thrust'], 6),
                round(res['specific_impulse'], 6),
                round(res['total_impulse'], 6))

    def test_combustion_efficiency_changes_performance(self):
        base = solid()
        low = solid({'combustion_efficiency': 0.80})
        assert self._perf(low) != self._perf(base)
        assert low['average_thrust'] < base['average_thrust']

    @pytest.mark.parametrize('key,value', [
        ('cf_efficiency', 0.85),
        ('kinetic_efficiency', 0.90),
        ('two_phase_loss', 0.90),
        ('atm_pressure', 60.0),
        ('test_altitude', 5000),
    ])
    def test_efficiency_and_ambient_overrides_change_performance(self, key, value):
        base = solid()
        changed = solid({key: value})
        assert self._perf(changed) != self._perf(base), f'{key} olu girdi'

    def test_discharge_coefficient_changes_the_manufactured_throat(self):
        base = solid()
        cd = solid({'discharge_coeff': 0.85})
        assert cd['throat_diameter'] > base['throat_diameter'], (
            'Bogaz akis katsayisi geometrik bogazi buyutmeli')
        assert cd['average_thrust'] == pytest.approx(base['average_thrust']), (
            'Cd basinc/itki cozumune girmemeli (etkin alan degismedi)')

    @pytest.mark.parametrize('key,value', [
        ('yield_strength', 900),
        ('safety_factor', 1.5),
        ('case_thickness', 20),
        ('case_material', 'aluminum_6061'),
    ])
    def test_structural_overrides_change_the_case_chain(self, key, value):
        base = solid()['structural_analysis']['case_analysis']
        changed = solid({key: value})['structural_analysis']['case_analysis']
        assert (changed['hoop_stress_mpa'], changed['safety_factor'],
                changed['wall_thickness_mm']) != (
            base['hoop_stress_mpa'], base['safety_factor'],
            base['wall_thickness_mm']), f'{key} kasa zincirine islemiyor'

    def test_liner_overrides_change_mass_and_thermal(self):
        base = solid()['thermal_analysis']['heat_transfer']
        changed = solid({'liner_thickness': 8})['thermal_analysis']['heat_transfer']
        # Liner ile yalıtım AYRI alanlardır ve motor bunları bilerek ayırır:
        # yalıtım çap zincirine girer (kasa iç çapı, kütle), liner yalnız
        # termal+kütle katmanıdır (bkz. solid_rocket_engine.py, "Liner (bond
        # katmanı) çap zincirine BİLEREK eklenmedi"). Bu test eskiden liner'ı
        # değiştirip YALITIM alanına bakıyordu; 0.0 != 0.0 ile düşüyordu.
        # Doğru sözleşme: liner girdisi kendi alanına yansır ve ısıl dirence
        # girer (_insulation_resistance = (t_yalitim + t_liner)/k).
        assert changed['liner_thickness_mm'] != base['liner_thickness_mm']
        assert changed['insulation_effectiveness'] != base['insulation_effectiveness']

    def test_declared_overall_efficiency_is_reported_not_double_counted(self):
        base = solid()
        declared = solid({'overall_efficiency': 0.80})
        combustion = declared['advanced_performance']['combustion_analysis']
        assert combustion['user_declared_overall_efficiency_percent'] == 80.0
        assert declared['average_thrust'] == pytest.approx(base['average_thrust']), (
            'Beyan edilen toplam verim, ayrik kayiplarin uzerine ikinci kez '
            'uygulanmamali')

    def test_advanced_performance_is_no_longer_constant(self):
        a = solid()['advanced_performance']
        b = solid({'nozzle_efficiency': 0.85})['advanced_performance']
        assert a['combustion_analysis']['nozzle_efficiency_percent'] != \
            b['combustion_analysis']['nozzle_efficiency_percent']
        assert a['combustion_analysis']['overall_efficiency_percent'] != 86.8
        assert a['mass_utilization']['propellant_mass_fraction'] != 0.75

    def test_defaults_are_unchanged_without_overrides(self):
        """Override yokken davranış birebir korunur (korelasyon bekçileri).

        Çapa 2026-07-25'te YENİDEN ÖLÇÜLDÜ. Eski değer 6807.73 N idi; onu
        İKİ AYRI fizik düzeltmesi taşıdı ve ikisi de aşağıda ayrıştırıldı:

        F024 (yanma hızı varsayılanı) — kurucunun a = 0.005 varsayılanı
        'r[mm/s] = 5.0*P[MPa]^0.35' fitinin MPa TABANLI katsayısıdır, motor
        ise onu BAR ile değerlendiriyordu; yanma hızı 10^0.35 = 2.2387 kat
        şişiyordu. Varsayılan merkezi kataloğa (APCP, a = 0.0022334) çekildi.

        F068 (sabit geometrili nozulda CF) — eski CF her basınçta anlık
        optimum genişleme (Pe = Pa) varsayıyordu, yani ulaşılabilir EN BÜYÜK
        değeri veriyordu. Ölçüm (bu motor, a = 0.005 sabit): CF tasarım
        basıncında birebir aynı (Pc = 40 bar -> 1.4983), yanma kuyruğunda
        ayrışıyor (Pc = 8 bar -> eski 1.1945, yeni 0.9063; eski %31.8 fazla).
        Tepe itki ve yanma süresi bu yüzden DEĞİŞMEDİ (10811.99 N / 2.1863 s),
        toplam impuls %1.51 düştü (14883.67 -> 14659.04 N·s).

        Ayrıştırma: a = 0.005 sabit tutulunca yeni kod 6704.94 N verir
        (yalnız F068 etkisi). Oradan katalog katsayısına geçiş 3063.68 N'e
        indirir (yalnız F024 etkisi). Aşağıdaki ikinci ve üçüncü iddia bu
        ayrıştırmanın bekçisidir — çapa kayarsa hangi düzeltmenin kaydırdığı
        doğrudan okunur.

        ÇAPA ÜÇÜNCÜ KEZ ÖLÇÜLDÜ (v2.6.27, A1-2 sonrası). Eski CF, aşırı
        genişlemede negatife giden basınç-itki terimini ``max(CF, 0)`` ile
        KIRPIYORDU: çalışmaya devam eden motor eğride 0 N görünüyordu. A1-2
        bu kırpmayı kesilmiş-lüle (ayrılma alan oranında) modeliyle
        değiştirdi, dolayısıyla ayrılmış kuyruk artık gerçek (pozitif) itki
        taşıyor ve ORTALAMA itki bir miktar yükseliyor. Ölçüm (bu HEAD):

            varsayılan a : ayrılmış örnek oranı %18,5 -> 3063,68 => 3064,88 N
            a = 0.005    : ayrılmış örnek oranı %22,7 -> 6704,94 => 6739,13 N
            a = 0.005 tepe itki: 10811,99 N — DEĞİŞMEDİ (tasarım noktasında
            akış eklidir, ayrılma yoktur; kayma yalnız kuyruktadır)

        Kayma yönü modelle tutarlıdır: kırpılan (sıfırlanan) kuyruk geri
        gelince impuls ancak ARTAR. B2 seyreltmesinin bu sayılara etkisi
        YOKTUR ve bu ayrıca ölçüldü: türetilmiş büyüklükler tam
        çözünürlüklü diziden hesaplanır (a = 0.005 koşusu 220 örnektir, yani
        seyreltme eşiğinin altında kalır ve hiç seyreltilmez, buna rağmen
        çapası kayar — kaymanın sebebi A1-2'dir).
        """
        res = solid()
        # v2.5.2 (Codex bulgusu): impuls hesabi son adimi atliyordu; terminal
        # tukenis ornegi eklenince ortalama itki %0.18 kaymisti. O kapanis
        # davranisi hâlâ yerinde; asagidaki deger onun F024+F068+A1-2 hâli.
        assert res['average_thrust'] == pytest.approx(3064.88, abs=0.5)
        legacy_a = solid(burn_rate_a=0.005)
        assert legacy_a['average_thrust'] == pytest.approx(6739.13, abs=0.5)
        # F068 ve A1-2 tepe itkiye dokunmaz (tasarim basincinda CF ayni,
        # akis ekli): bu deger uc surumdur degismedi.
        assert legacy_a['max_thrust'] == pytest.approx(10811.99, abs=1.0)


# ---------------------------------------------------------------------------
# Bulgu 6 — radyan tehlike mesafesi alan yerine cidar kalınlığını kullanıyordu
# ---------------------------------------------------------------------------
class TestRadiantHazardUsesRealArea:

    def test_distance_scales_with_area_not_wall_thickness(self):
        analyzer = SafetyAnalyzer()
        # Asgari duruş mesafesi kelepçesinin (3 m) uzağında kal
        d_small = analyzer._calculate_radiant_heat_distance(1200.0, 9.0)
        d_large = analyzer._calculate_radiant_heat_distance(1200.0, 81.0)
        assert d_small > SAFETY_MODEL['min_hazard_distance_m']
        assert d_large == pytest.approx(3.0 * d_small, rel=1e-6), (
            'Mesafe alanin karekokuyle olceklenmelidir')

    def test_thicker_wall_does_not_increase_the_hazard_distance(self):
        thin = safety({'wall_thickness': 0.005})['thermal_safety']
        thick = safety({'wall_thickness': 0.050})['thermal_safety']
        # Kalinlik disa capa 9 cm eklediginden alan cok az buyur; eski hatada
        # mesafe 7.65 -> 24.18 m gibi 3 kat artiyordu.
        assert thick['radiant_heat_hazard_distance_m'] < 1.6 * thin[
            'radiant_heat_hazard_distance_m'], (
            'Cidar kalinligi tehlike mesafesini yonetemez')

    def test_bigger_motor_has_a_bigger_hazard_distance(self):
        small = safety({'chamber_diameter': 0.10})['thermal_safety']
        large = safety({'chamber_diameter': 0.40})['thermal_safety']
        assert large['radiating_area_m2'] > small['radiating_area_m2']
        assert large['radiant_heat_hazard_distance_m'] > small[
            'radiant_heat_hazard_distance_m']

    def test_radiating_area_assumption_is_declared(self):
        # 'assumed' dalı kamara BOYUNUN YOKLUĞUNU sınar; yardımcının artık
        # varsayılan bir boyu var (parti 31 / F4-1 ısı zinciri kapısı), o
        # yüzden burada AÇIKÇA düşürülür — sınanan durum tam olarak budur.
        assumed = safety(_dus=('chamber_length',))['thermal_safety']
        known = safety({'chamber_length': 0.6})['thermal_safety']
        assert 'ASSUMED' in assumed['radiating_area_basis']
        assert 'ASSUMED' not in known['radiating_area_basis']
        assert known['radiating_area_m2'] != assumed['radiating_area_m2']

    def test_radiating_temperature_is_the_outer_wall_not_the_gas(self):
        th = safety()['thermal_safety']
        assert th['radiating_surface_temperature_k'] == pytest.approx(
            th['outer_wall_temperature_k'])
        assert th['radiating_surface_temperature_k'] < th['chamber_temperature_k']


# ---------------------------------------------------------------------------
# Bulgu 7 — cidar sıcaklığı chamber_temperature * 0.3 sabiti
# ---------------------------------------------------------------------------
class TestSafetyWallTemperatureIsReal:

    def test_not_thirty_percent_of_chamber_temperature(self):
        for tc in (2200.0, 3000.0, 3600.0):
            th = safety({'chamber_temperature': tc})['thermal_safety']
            assert th['estimated_wall_temperature_k'] != pytest.approx(0.3 * tc), (
                'Cidar sicakligi sabit katsayidan gelemez')

    def test_supplied_wall_temperature_contract_is_honoured(self):
        th = safety({'wall_temperature_hot': 900.0,
                     'wall_temperature_cold': 600.0})['thermal_safety']
        assert th['inner_wall_temperature_k'] == pytest.approx(900.0)
        assert th['outer_wall_temperature_k'] == pytest.approx(600.0)
        assert 'contract' in th['wall_temperature_source']

    def test_cooling_changes_the_wall_temperature(self):
        natural = safety({'cooling_type': 'natural'})['thermal_safety']
        regen = safety({'cooling_type': 'regenerative'})['thermal_safety']
        assert regen['inner_wall_temperature_k'] != natural[
            'inner_wall_temperature_k'], (
            'Sogutma tipi cidar sicakligini degistirmeli')

    def test_material_limits_come_from_the_database(self):
        steel = safety(material='steel_4130')['thermal_safety']
        alu = safety(material='aluminum_6061')['thermal_safety']
        assert steel['material_max_service_temp_k'] != alu[
            'material_max_service_temp_k']
        assert steel['material_max_service_temp_k'] not in (800, 600)


# ---------------------------------------------------------------------------
# Bulgu 8 — termal gerilme sabit çelik özellikleriyle hesaplanıyordu
# ---------------------------------------------------------------------------
class TestSafetyThermalStressUsesSelectedMaterial:

    def test_thermal_stress_changes_with_material(self):
        md = {'wall_temperature_hot': 900.0, 'wall_temperature_cold': 500.0}
        steel = safety(md, material='steel_4130')['thermal_safety']
        alu = safety(md, material='aluminum_6061')['thermal_safety']
        inconel = safety(md, material='inconel_718')['thermal_safety']
        values = {steel['thermal_stress_mpa'], alu['thermal_stress_mpa'],
                  inconel['thermal_stress_mpa']}
        assert len(values) == 3, (
            'Termal gerilme secilen malzemenin E/alfa/nu degerlerinden gelmeli')

    def test_thermal_stress_matches_the_classic_wall_gradient_form(self):
        from hrma.data.materials_db import get_material
        md = {'wall_temperature_hot': 900.0, 'wall_temperature_cold': 500.0}
        th = safety(md, material='steel_4130')['thermal_safety']
        mat = get_material('steel_4130')
        expected = (mat['elastic_modulus'] * mat['thermal_expansion'] * 400.0
                    / (2.0 * (1.0 - mat['poisson_ratio']))) / 1e6
        assert th['thermal_stress_mpa'] == pytest.approx(expected, rel=1e-9)

    def test_thermal_stress_is_zero_without_a_gradient(self):
        th = safety({'wall_temperature_hot': 700.0,
                     'wall_temperature_cold': 700.0})['thermal_safety']
        assert th['thermal_stress_mpa'] == pytest.approx(0.0)

    def test_old_constant_value_is_gone(self):
        th = safety()['thermal_safety']
        assert th['thermal_stress_mpa'] != pytest.approx(1456.8, abs=0.1)


# ---------------------------------------------------------------------------
# Bulgu 9 — motor_type / burn_time / thrust backend'e ulaşıp kullanılmıyordu
# ---------------------------------------------------------------------------
class TestSafetyInputsAreUsed:

    def test_motor_type_selects_the_explosive_class(self):
        solid_r = safety(propellant_type='apcp', motor_type='solid')
        liquid_r = safety(propellant_type='apcp', motor_type='liquid')
        assert (solid_r['explosive_hazards']['explosive_class']
                != liquid_r['explosive_hazards']['explosive_class'])
        assert (solid_r['explosive_hazards']['tnt_equivalent_kg']
                != liquid_r['explosive_hazards']['tnt_equivalent_kg'])
        assert set(MOTOR_TYPE_TO_EXPLOSIVE_CLASS) == {'solid', 'hybrid', 'liquid'}

    def test_motor_type_from_motor_data_is_also_honoured(self):
        via_kwarg = safety(propellant_type='apcp', motor_type='liquid')
        via_data = safety({'motor_type': 'liquid'}, propellant_type='apcp')
        assert (via_data['explosive_hazards']['explosive_class']
                == via_kwarg['explosive_hazards']['explosive_class'])

    def test_unresolved_class_is_declared_not_silently_assumed(self):
        res = safety(propellant_type='some_unknown_mix')
        assert 'conservative' in res['explosive_hazards']['explosive_class_basis']

    def test_thrust_changes_the_restraint_requirement(self):
        low = safety({'thrust': 1000.0})
        high = safety({'thrust': 9000.0})
        lo = low['explosive_hazards']['fragment_hazards']['unrestrained_motor']
        hi = high['explosive_hazards']['fragment_hazards']['unrestrained_motor']
        assert hi['required_restraint_force_n'] > lo['required_restraint_force_n']
        assert hi['burnout_velocity_ms'] > lo['burnout_velocity_ms']

    def test_burn_time_changes_the_thermal_exposure(self):
        short = safety({'burn_time': 5.0})['thermal_safety']
        long = safety({'burn_time': 60.0})['thermal_safety']
        assert long['second_degree_burn_distance_m'] > short[
            'second_degree_burn_distance_m'], (
            'Uzun maruziyet ayni akiyi daha tehlikeli yapar')
        assert long['exposure_duration_s'] == 60.0

    def test_inputs_used_block_is_reported(self):
        res = safety(motor_type='solid')
        used = res['inputs_used']
        assert used['motor_type'] == 'solid'
        assert used['thrust_n'] == 1000.0
        assert used['burn_time_s'] == 10.0

    def test_case_mass_uses_real_geometry_when_available(self):
        with_geo = safety({'chamber_length': 0.6})['explosive_hazards'][
            'fragment_hazards']
        assert 'shell mass' in with_geo['case_mass_basis']
        no_geo = SafetyAnalyzer()._calculate_fragment_hazards(5.0, 1000.0, 10.0,
                                                             None, 'steel_4130')
        assert 'EMPIRICAL' in no_geo['case_mass_basis']
        assert no_geo['estimated_case_mass_kg'] == pytest.approx(
            5.0 * SAFETY_MODEL['fallback_case_mass_fraction'])


# ---------------------------------------------------------------------------
# Emniyet paneli: basınç riski gerçek kopma marjını görmeli
# ---------------------------------------------------------------------------
class TestPressureRiskSeesTheRealVessel:

    def test_burst_pressure_is_computed_for_the_selected_material(self):
        steel = safety(material='steel_4130')['pressure_safety']
        alu = safety(material='aluminum_6061')['pressure_safety']
        assert steel['actual_burst_pressure_bar'] is not None
        assert alu['actual_burst_pressure_bar'] < steel['actual_burst_pressure_bar']

    def test_undersized_case_raises_the_pressure_risk_score(self):
        strong = safety({'wall_thickness': 0.02, 'chamber_pressure': 40.0})
        weak = safety({'wall_thickness': 0.0005, 'chamber_pressure': 200.0},
                      material='aluminum_6061')
        assert (weak['risk_assessment']['individual_risks']['pressure']
                > strong['risk_assessment']['individual_risks']['pressure'])


# ---------------------------------------------------------------------------
# Sabitlerin tek tanım noktasında olduğunun bekçisi
# ---------------------------------------------------------------------------
class TestConstantsAreCentralised:

    def test_condensed_phase_table_covers_the_engine_propellants(self):
        for key in ('apcp', 'double_base', 'sugar', 'knsu', 'black_powder'):
            assert key in SOLID_CONDENSED_MASS_FRACTION
            assert 0.0 <= SOLID_CONDENSED_MASS_FRACTION[key] < 1.0

    def test_safety_model_holds_the_thresholds(self):
        for key in ('radiant_pain_threshold_w_m2', 'second_degree_burn_tdu',
                    'gurney_velocity_ms', 'fallback_case_mass_fraction',
                    'min_hazard_distance_m'):
            assert key in SAFETY_MODEL

    def test_case_design_defaults_are_single_sourced(self):
        engine = SolidRocketEngine(chamber_diameter=100, grain_length=500,
                                   core_diameter=30, chamber_pressure=40)
        material, sigma_y, sf, t_wall = engine._case_design()
        assert material == SOLID_CASE_DESIGN['material']
        assert sigma_y == SOLID_CASE_DESIGN['yield_strength_pa']
        assert sf == SOLID_CASE_DESIGN['design_safety_factor']
        assert t_wall >= SOLID_CASE_DESIGN['min_wall_thickness_m']


# ---------------------------------------------------------------------------
# F067 — erozif yanma raporu uydurma bir doğruydu
#
# Eski kod:
#     'erosive_enhancement_percent': min(25, mass_flux / 100 * 5)
#     'port_diameter_effect': 'Moderate'
# Bu doğrunun motorun KENDİ erozif modeliyle hiçbir ilgisi yoktu ve kaynağı
# da yoktu. Ölçüm (G = 1000 kg/m²s, D_p/D_ç = 0.3): eski satır %25 (50'den
# kırpılmış) raporluyordu, çözücünün fiilen uyguladığı artış ise APCP tablo
# katsayısıyla (k = 0.0136) +%3.31 — kullanıcıya gösterilen sayı hesaba
# gireninin 7.6 katıydı ve G > 500'ün her yerinde 25 tavanına yapışıyordu.
# 'Moderate' de hiçbir hesaba dayanmayan sabit metindi.
# Kaynak (uygulanan model): Lenoir & Robillard (1957) indirgenmiş vekili;
# Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 12.
# ---------------------------------------------------------------------------
class TestErosiveReportMatchesTheSolver:

    def _engine(self, **ov):
        return SolidRocketEngine(chamber_diameter=100, grain_length=500,
                                 core_diameter=30, chamber_pressure=40,
                                 overrides=(ov or None))

    def test_reported_enhancement_is_the_applied_enhancement(self):
        """Raporlanan artış, burn_rate() içinde FİİLEN uygulanan artıştır."""
        eng = self._engine()
        curve = eng.calculate_thrust_curve()
        report = eng._calculate_erosive_effects(curve)
        factors = np.asarray(curve['erosive_factor'], dtype=float)
        assert report['model_applied'] is True
        assert report['erosive_enhancement_percent'] == pytest.approx(
            (factors[0] - 1.0) * 100.0, rel=1e-12)
        assert report['erosive_enhancement_max_percent'] == pytest.approx(
            (float(np.nanmax(factors)) - 1.0) * 100.0, rel=1e-12)
        # Eski uydurma dogru bu kosuda 25 tavanina yapisirdi (G >> 500).
        assert report['mass_flux_max_kg_m2s'] > 500.0
        assert report['erosive_enhancement_max_percent'] < 25.0

    def test_report_tracks_the_erosive_coefficient(self):
        """k degistiginde raporlanan artis da degismeli (olu sabit degil)."""
        weak = self._engine(erosive_k=0.0002)
        strong = self._engine(erosive_k=0.02)
        r_weak = weak._calculate_erosive_effects(weak.calculate_thrust_curve())
        r_strong = strong._calculate_erosive_effects(
            strong.calculate_thrust_curve())
        assert r_strong['erosive_enhancement_max_percent'] > 10.0 * r_weak[
            'erosive_enhancement_max_percent']
        assert r_weak['erosive_coefficient_k'] == pytest.approx(0.0002)
        assert r_strong['erosive_coefficient_k'] == pytest.approx(0.02)

    def test_port_diameter_effect_is_computed_not_the_word_moderate(self):
        """'Moderate' sabit metni yerine hesaplanmis geometrik carpan."""
        eng = self._engine()
        report = eng._calculate_erosive_effects(eng.calculate_thrust_curve())
        assert 'port_diameter_effect' not in report
        d_ratio = eng.D_core / eng.D_chamber
        assert report['port_diameter_factor_initial'] == pytest.approx(
            max(d_ratio, 0.05) ** -0.2, rel=1e-12)
        # Modelin bilinen zayifligi ('buyuklugu dusuk tahmin eder') beyan edilir
        assert 'UNDERPREDICT' in report['model_limitation'].upper()

    def test_threshold_is_respected(self):
        """Esik altinda (G <= 100) hicbir erozif artis uygulanmaz."""
        eng = self._engine()
        assert eng._erosive_factor(100.0, 0.3) == 1.0
        assert eng._erosive_factor(99.0, 0.3) == 1.0
        assert eng._erosive_factor(1000.0, 0.3) > 1.0


# ---------------------------------------------------------------------------
# F071 — boğaz erozyonu hiç yoktu, 'erosion_factor' alanı ölüydü
#
# Eski kod A_t'yi tasarım noktasında bir kez hesaplayıp koşu boyunca SABİT
# tutuyor, docstring bunu 'gerçek motorda boğaz rijittir' diye
# gerekçelendiriyordu. Grafit/fenolik boğaz rijit DEĞİLDİR: difüzyon
# kontrollü oksidasyonla geriler. solid.html'in 'erosion_factor' alanı her
# koşuda backend'e gidiyor ama HİÇBİR YERDE okunmuyordu.
# Kaynak: Thakre & Yang, 'Chemical Erosion of Graphite and Refractory Metal
# Nozzles in Solid-Propellant Rocket Motors', J. Propulsion and Power 24(4),
# 2008; Bartz 1957 (h_g ~ Pc^0.8); Geisler grafit bandı 0.05-0.25 mm/s.
# Model tek tanım noktasında: transient_ballistics.ThroatErosionModel.
# ---------------------------------------------------------------------------
class TestThroatErosionIsWired:

    def _engine(self, **ov):
        return SolidRocketEngine(grain_type='end_burner', chamber_diameter=100,
                                 grain_length=500, core_diameter=30,
                                 chamber_pressure=40, overrides=(ov or None))

    def test_erosion_factor_field_is_no_longer_dead(self):
        """Uzun yanma + kucuk bogaz: erozyon acilinca sayilar KIMILDAR.

        Olcum (end-burner, APCP, Pc = 40 bar, a_ref = 0.15 mm/s grafit):
          A_t  4.6135e-05 -> 1.6811e-04 m2  (+%264)
          d_t  7.66 -> 14.63 mm
          yanma sonu Pc  40.0 -> 5.47 bar
          yanma sonu itki  276.5 -> 51.9 N
        Rijit bogazla bu koşuda basınç sabit 40 bar kalıyordu.
        """
        rigid = self._engine().calculate_thrust_curve()
        eroded = self._engine(erosion_factor=0.15).calculate_thrust_curve()

        assert rigid['throat_erosion']['enabled'] is False
        assert rigid['throat_area_final'] == pytest.approx(
            rigid['throat_area'], rel=1e-12)

        assert eroded['throat_erosion']['enabled'] is True
        assert eroded['throat_area_final'] > 2.0 * eroded['throat_area']
        assert float(eroded['pressure'][-1]) < 0.5 * float(
            rigid['pressure'][-1])
        assert float(eroded['thrust'][-1]) < 0.5 * float(rigid['thrust'][-1])

    def test_rigid_throat_assumption_is_declared_not_silent(self):
        """Erozyon kapaliyken varsayimin ADI raporda yazar."""
        rigid = self._engine().calculate_thrust_curve()
        assert 'rigid-throat assumption' in rigid['throat_erosion']['basis']
        assert rigid['throat_erosion']['input_field'].startswith(
            'erosion_factor')

    @pytest.mark.parametrize('overrides, code', [
        ({}, 'warn.solid.rigid_throat_assumption'),
        ({'erosion_factor': 0.15}, 'warn.solid.throat_erosion_significant'),
        ({'erosion_factor': 0.001},
         'warn.solid.throat_erosion_coeff_off_band'),
    ])
    def test_each_case_produces_its_warning(self, overrides, code):
        """Uc durumun ucu de kullaniciya gorunur (sessiz kabul yok).

        0.001 mm/s solid.html varsayilanidir ve grafitin yayimlanmis
        bandinin (0.05-0.15 mm/s) 50 kat altindadir -> sorgulanir.
        """
        res = self._engine(**overrides).calculate_performance()
        codes = {w['code'] for w in (res.get('design_warnings') or [])}
        assert code in codes, sorted(codes)

    def test_short_fat_throat_motor_is_not_nagged(self):
        """Kisa yanma + buyuk bogazda rijit varsayim uyarisi CIKMAZ.

        Uyari gurultu olmamali: BATES, Pc = 40 bar, t_b ~ 2.2 s, d_t ~ 45 mm
        kosusunda ongorulen alan artisi esigin (%5) altinda kalir.
        """
        res = solid()
        codes = {w['code'] for w in (res.get('design_warnings') or [])}
        assert 'warn.solid.rigid_throat_assumption' not in codes

    def test_model_is_the_shared_one_not_a_copy(self):
        """Formul transient_ballistics'te tek yerde tanimli (CLAUDE.md k.11)."""
        from hrma.analysis.transient_ballistics import ThroatErosionModel
        eng = self._engine(erosion_factor=0.15)
        model = eng._throat_erosion_model()
        assert isinstance(model, ThroatErosionModel)
        assert model.a_ref_mm_s == pytest.approx(0.15)
        # r_dot = a_ref * (Pc/70 bar)^0.8
        assert model.rate_m_s(40e5) == pytest.approx(
            0.15 * (40.0 / 70.0) ** 0.8 / 1000.0, rel=1e-12)
