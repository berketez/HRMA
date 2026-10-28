"""
Tests for the 1D regenerative-cooling station-marching module (regen_cooling).

Hand-checkable analytic anchors (independent of the implementation):
  - Dittus-Boelter, Re=1e4, Pr=5, heating (n=0.4):
        Nu = 0.023 * 1e4^0.8 * 5^0.4
           = 0.023 * 1584.893 * 1.903654 = 69.39
  - Rectangular hydraulic diameter, w=3 mm, h=2 mm:
        D_h = 2*w*h/(w+h) = 2*6e-6/5e-3 = 2.4e-3 m
        square channel (w=h=a) -> D_h = a
  - Haaland friction factor:
        laminar Re=1000 -> f = 64/1000 = 0.064
        Re=1e5, eps/D=0.001 -> f ~ 0.02196 (hand evaluation below)
        Re=1e5, smooth (eps=0) -> f ~ 0.01783
  - Darcy-Weisbach, f=0.02, L=1 m, D=0.01 m, rho=1000, V=2 m/s:
        dP = f*(L/D)*rho*V^2/2 = 0.02*100*1000*4/2 = 4000 Pa
  - Water @ 300 K (Incropera A.6): rho~997, cp~4179, k~0.613, mu~8.55e-4
  - Energy balance: heat into coolant = mdot * cp_mean * dT (closed enthalpy
    balance; reconstructed independently from q(x) and the wetted area).

Run:
    cd <depo kökü>
    MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest tests/test_regen_cooling.py -v
"""

import math

import numpy as np
import pytest

from hrma.analysis.regen_cooling import (
    RegenCooling,
    dittus_boelter_nu,
    hydraulic_diameter_rect,
    haaland_friction_factor,
    darcy_weisbach_dp,
    water_properties,
    rp1_properties,
    RP1_COKING_TEMP_K,
    RE_LAMINAR_MAX,
)


# ======================================================================
# Ortak fikstürler
# ======================================================================
def make_regen(**overrides):
    """Iyi soğutulmuş su/CuCrZr temel durumu (cidar limitler içinde)."""
    kwargs = dict(
        chamber_pressure=20e5,
        chamber_temperature=3000.0,
        gamma=1.2,
        molecular_weight=24.0,
        throat_diameter=0.03,
        expansion_ratio=6.0,
        coolant='water',
        coolant_mdot=6.0,
        coolant_inlet_temp=300.0,
        coolant_inlet_pressure=40e5,
        n_channels=60,
        channel_width=1.5e-3,
        channel_height=3.0e-3,
        wall_thickness=1.0e-3,
        wall_material='cucrzr',
        n_stations=40,
        coolant_props_source='table',   # tekrar üretilebilir çapa
    )
    kwargs.update(overrides)
    return RegenCooling(**kwargs)


def make_regen_high_expansion(**overrides):
    """P4B2-11'in ölçüm devresi: ε=25, RP-1/bakır, 100 kanal.

    Yüksek genişleme oranında konverjan bölümün EKSENEL payı çok küçüktür
    (z_throat/z_exit ≈ 0.03), bu yüzden istasyonları uzunlukla dağıtan
    ızgara konverjanı bir-iki segmente sıkıştırır. Kırpma sınırlarının
    (20/50) SONUCUNU ölçen bekçiler bu devreyi kullanır.
    """
    kwargs = dict(
        chamber_pressure=70e5,
        chamber_temperature=3500.0,
        gamma=1.2,
        molecular_weight=22.0,
        throat_diameter=0.10,
        expansion_ratio=25.0,
        coolant='rp1',
        coolant_mdot=8.0,
        coolant_inlet_temp=300.0,
        coolant_inlet_pressure=120e5,
        n_channels=100,
        channel_width=2.0e-3,
        channel_height=3.0e-3,
        wall_thickness=1.0e-3,
        wall_material='copper',
        n_stations=50,
        coolant_props_source='table',
    )
    kwargs.update(overrides)
    return RegenCooling(**kwargs)


def independent_wetted_integral(res):
    """Yayımlanan üç diziden BAĞIMSIZ ısı entegrali (trapez kuadratür).

    Kodun marş şemasını (birinci mertebe yukarı-akım) ve istasyon sırasını
    YENİDEN UYGULAMAZ: yalnız yayımlanan ``q_MW_m2``, ``x_mm`` ve ``r_mm``
    dizilerini okur ve ıslak yüzey üzerinde trapez kuralıyla entegre eder.
    Bu, ``test_energy_balance_surface_integral``in şema-özdeşliği kilidinden
    farklı bir ölçüm eksenidir (ÖH defter P4B2-11).
    """
    x_m = np.asarray(res['x_mm'], dtype=float) / 1e3
    r_m = np.asarray(res['r_mm'], dtype=float) / 1e3
    q = np.asarray(res['q_MW_m2'], dtype=float) * 1e6
    ds = np.hypot(np.diff(x_m), np.diff(r_m))
    r_mean = 0.5 * (r_m[:-1] + r_m[1:])
    dA = 2.0 * math.pi * r_mean * ds
    q_mean = 0.5 * (q[:-1] + q[1:])
    return float(np.sum(q_mean * dA))


# ======================================================================
# 1) Modül-düzeyi yardımcılar — analitik el hesabı çapaları
# ======================================================================
class TestHydraulicHelpers:

    def test_dittus_boelter_heating_anchor(self):
        # Nu = 0.023 * 1e4^0.8 * 5^0.4 = 69.39 (el hesabı)
        nu = dittus_boelter_nu(1.0e4, 5.0, heating=True)
        assert nu == pytest.approx(69.39, abs=0.05)

    def test_dittus_boelter_cooling_exponent(self):
        # Soğutmada n=0.3: Nu_cool < Nu_heat aynı Re,Pr>1 için
        nu_h = dittus_boelter_nu(2.0e4, 6.0, heating=True)
        nu_c = dittus_boelter_nu(2.0e4, 6.0, heating=False)
        assert nu_c < nu_h
        # Bağımsız kapanış: Nu_cool = 0.023*Re^0.8*Pr^0.3
        assert nu_c == pytest.approx(0.023 * 2.0e4 ** 0.8 * 6.0 ** 0.3, rel=1e-12)

    def test_dittus_boelter_invalid(self):
        with pytest.raises(ValueError):
            dittus_boelter_nu(-1.0, 5.0)
        with pytest.raises(ValueError):
            dittus_boelter_nu(1e4, 0.0)

    def test_hydraulic_diameter_rect_anchor(self):
        # w=3mm, h=2mm -> D_h = 2*w*h/(w+h) = 2.4 mm
        assert hydraulic_diameter_rect(3e-3, 2e-3) == pytest.approx(2.4e-3, rel=1e-12)

    def test_hydraulic_diameter_square_equals_side(self):
        # Kare kanal: D_h = a
        assert hydraulic_diameter_rect(4e-3, 4e-3) == pytest.approx(4e-3, rel=1e-12)

    def test_hydraulic_diameter_invalid(self):
        with pytest.raises(ValueError):
            hydraulic_diameter_rect(0.0, 2e-3)
        with pytest.raises(ValueError):
            hydraulic_diameter_rect(2e-3, -1e-3)

    def test_haaland_laminar_branch(self):
        # Re<2300 -> f = 64/Re (White Eq. 6.12)
        assert haaland_friction_factor(1000.0, 0.001) == pytest.approx(0.064, rel=1e-12)
        assert haaland_friction_factor(2000.0, 0.0) == pytest.approx(0.032, rel=1e-12)

    def test_haaland_turbulent_rough_anchor(self):
        # Re=1e5, eps/D=1e-3: 1/sqrt(f) = -1.8*log10(6.9/1e5 + (1e-3/3.7)^1.11)
        inv = -1.8 * math.log10(6.9 / 1e5 + (1e-3 / 3.7) ** 1.11)
        f_hand = 1.0 / inv ** 2
        f = haaland_friction_factor(1.0e5, 1e-3)
        assert f == pytest.approx(f_hand, rel=1e-12)
        assert f == pytest.approx(0.02196, abs=1e-4)   # bağımsız değer

    def test_haaland_smooth_pipe(self):
        # Pürüzsüz boru Re=1e5 -> f ~ 0.0178 (Moody diyagramı)
        f = haaland_friction_factor(1.0e5, 0.0)
        assert f == pytest.approx(0.01783, abs=5e-4)

    def test_haaland_invalid(self):
        with pytest.raises(ValueError):
            haaland_friction_factor(-1.0, 0.001)
        with pytest.raises(ValueError):
            haaland_friction_factor(1e5, -0.1)

    def test_darcy_weisbach_anchor(self):
        # dP = f*(L/D)*rho*V^2/2 = 0.02*100*1000*4/2 = 4000 Pa (el hesabı)
        dp = darcy_weisbach_dp(0.02, 1.0, 0.01, 1000.0, 2.0)
        assert dp == pytest.approx(4000.0, rel=1e-12)

    def test_darcy_weisbach_scaling(self):
        # V iki katına -> dP dört katına (V^2 bağımlılığı)
        dp1 = darcy_weisbach_dp(0.02, 1.0, 0.01, 1000.0, 2.0)
        dp2 = darcy_weisbach_dp(0.02, 1.0, 0.01, 1000.0, 4.0)
        assert dp2 == pytest.approx(4.0 * dp1, rel=1e-12)

    def test_darcy_weisbach_invalid(self):
        with pytest.raises(ValueError):
            darcy_weisbach_dp(0.02, 1.0, 0.0, 1000.0, 2.0)


# ======================================================================
# 2) Soğutucu özellik tabloları
# ======================================================================
class TestCoolantProperties:

    def test_water_anchor_300K(self):
        p = water_properties(300.0)
        assert p['density'] == pytest.approx(997.0, abs=1.0)
        assert p['cp'] == pytest.approx(4179.0, abs=1.0)
        assert p['conductivity'] == pytest.approx(0.613, abs=1e-3)
        # ÖH D19 · P13B3-05 — BANT GEREKÇESİ (ölçülen, D19 taban 60cd341):
        # bugün fark = 0 (bit-özdeş), yani ±1e-5'lik bant bir kez bile
        # sınanmadı. Bant yine de KALIYOR ve gerekçesi şudur: sağ taraf
        # ürünün kopyası değil, Incropera Tablo A.6'nın 300 K satırıdır.
        # Tablo daha hassas bir kaynağa güncellenirse (ör. 0,8538e-3)
        # KİMLİK denetimi doğru bir iyileştirmeyi kırardı; ±1e-5 = referans
        # tablosunun kendi yuvarlama basamağıdır (%1,2). Bandı daraltmak
        # burada kusuru değil kaynağı kilitler.
        assert p['viscosity'] == pytest.approx(0.855e-3, abs=1e-5)
        # Pr = cp*mu/k ~ 5.83 (Incropera A.6)
        assert p['prandtl'] == pytest.approx(4179.0 * 0.855e-3 / 0.613, rel=1e-9)

    def test_water_interpolation_midpoint(self):
        # 310 K, 300-320 arası doğrusal orta değere yakın
        p = water_properties(310.0)
        assert 989.0 < p['density'] < 997.0
        assert p['viscosity'] == pytest.approx(0.5 * (0.855e-3 + 0.577e-3), rel=1e-9)

    def test_water_clamped_outside_range(self):
        low = water_properties(250.0)
        assert low['clamped'] is True
        assert low['density'] == pytest.approx(1000.0, abs=1e-9)  # 280 K uç
        high = water_properties(500.0)
        assert high['clamped'] is True

    def test_rp1_anchor_290K(self):
        p = rp1_properties(290.0)
        assert p['density'] == pytest.approx(806.0, abs=2.0)
        assert p['cp'] == pytest.approx(1880.0, abs=5.0)
        assert 0.10 < p['conductivity'] < 0.15

    def test_rp1_density_decreases_with_temperature(self):
        # Sıvı yakıt: sıcaklıkla genleşir -> yoğunluk düşer
        assert rp1_properties(450.0)['density'] < rp1_properties(300.0)['density']


# ======================================================================
# 3) Geçersiz girdi -> ValueError
# ======================================================================
class TestInputValidation:

    def test_negative_chamber_pressure(self):
        with pytest.raises(ValueError):
            make_regen(chamber_pressure=-1.0)

    def test_gamma_out_of_band(self):
        with pytest.raises(ValueError):
            make_regen(gamma=1.0)
        with pytest.raises(ValueError):
            make_regen(gamma=1.8)

    def test_bad_coolant_name(self):
        with pytest.raises(ValueError):
            make_regen(coolant='mercury')

    def test_nonpositive_coolant_mdot(self):
        with pytest.raises(ValueError):
            make_regen(coolant_mdot=0.0)

    def test_nonpositive_channel_count(self):
        with pytest.raises(ValueError):
            make_regen(n_channels=0)

    def test_nonpositive_channel_dims(self):
        with pytest.raises(ValueError):
            make_regen(channel_width=0.0)
        with pytest.raises(ValueError):
            make_regen(channel_height=-1e-3)

    def test_nonpositive_wall_thickness(self):
        with pytest.raises(ValueError):
            make_regen(wall_thickness=0.0)

    def test_exit_not_exceeding_throat(self):
        with pytest.raises(ValueError):
            make_regen(exit_diameter=0.02, expansion_ratio=None)  # < throat

    def test_missing_throat(self):
        with pytest.raises(ValueError):
            RegenCooling(chamber_pressure=20e5, chamber_temperature=3000.0,
                         throat_diameter=None, exit_diameter=0.08)

    def test_bad_flow_direction(self):
        with pytest.raises(ValueError):
            make_regen(flow_direction='crossflow')

    def test_bad_props_source(self):
        with pytest.raises(ValueError):
            make_regen(coolant_props_source='magic')

    def test_unknown_wall_material(self):
        with pytest.raises(ValueError):
            make_regen(wall_material='unobtanium')


# ======================================================================
# 4) İstasyon ızgarası ve temel yapı
# ======================================================================
class TestStationGrid:

    def test_array_lengths_equal(self):
        res = make_regen().solve()
        n = res['n_stations']
        keys = ['x_mm', 'r_mm', 'T_wall_hot_K', 'T_wall_cold_K', 'T_coolant_K',
                'P_coolant_bar', 'q_MW_m2', 'velocity_m_s', 'reynolds',
                'h_gas_W_m2K', 'h_coolant_W_m2K', 'area_ratio', 'mach',
                'T_recovery_K']
        for k in keys:
            assert len(res[k]) == n, k

    def test_n_stations_clamped_low(self):
        # NOT (ÖH FAZ B-4/P2): bu bekçi yalnız KIRPMA SINIRINI ölçer,
        # kırpmanın SONUCUNU değil. Kırpılmış ızgaranın yayımladığı toplamın
        # ızgaradan bağımsız olup olmadığı kardeş bekçidedir:
        # ``test_station_clamps_deliver_a_grid_converged_total`` (P4B2-11).
        assert make_regen(n_stations=5).solve()['n_stations'] == 20

    def test_n_stations_clamped_high(self):
        assert make_regen(n_stations=999).solve()['n_stations'] == 50

    # ÇEVİRİ (ÖH D15 birleşme düzeltmesi) — BORÇ İMİ KALKTI.
    # Bu bekçi P4B2-11 borcunu xfail(strict) ile taşıyordu;
    # imin kendi metni "onarım gelince bu im KALKAR" diyordu.
    # Kusur ÖH D15 termo-ucus a3 (06a99d4) tarafından
    # ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta test
    # GEÇİYOR ve strict im XPASS ile kırmızı veriyordu. İm
    # kaldırıldı; iddia artık CANLI bekçidir — onarım geri
    # alınırsa burası kırmızı verir.
    #
    # ÜRÜNDEKİ KANIT: hrma/analysis/regen_cooling.py:227
    # REGEN_MARCH_MAX_PASSES / :228 REGEN_MARCH_TOL; :1421 segment
    # ısısı trapez (ikinci mertebe), marş sabit nokta yinelemesiyle
    # kapatılıyor
    #
    # KALKAN İMİN GEREKÇESİ (kayıt için): ÖH defter P4B2-11 —
    # istasyonlar UZUNLUKLA dağıtıldığı için
    # (regen_cooling.py:956-964 frac_conv = z_throat/z_exit) ε=25
    # lülede konverjan bölüm tek segmente sıkışıyor (ölçülen
    # throat_index=1, n=20/30/40) ve birinci mertebe yukarı-akım
    # entegrali (:1283-1290) ızgaraya bağımlı bir toplam üretiyor:
    # ölçülen Q(20)=4.429.234 W ⟷ Q(50)=4.545.512 W (%2,56 salınım).
    # Konverjan alanın %2,6'sı ama ısının %9,2'si. Onarım gelince
    # bu im KALKAR.
    def test_station_clamps_deliver_a_grid_converged_total(self):
        """Kırpma sınırlarının SONUCU: yayımlanan toplam ızgaradan bağımsız.

        ``n_stations`` kırpması (20 ⟷ 50) bir uygulama ayrıntısıdır;
        kullanıcıya yayımlanan ``total_heat_W`` ise fiziksel bir büyüklüktür.
        Aynı devre, yalnız istasyon sayısı değişerek, iki farklı ısı yükü
        veremez. İkinci iddia konverjan bölümün gerçekten ÇÖZÜLDÜĞÜNÜ ölçer:
        tek segment, birinci mertebe şemada konverjan payını boğaz akısıyla
        doldurur (raporda +%22,4 fazla sayım).
        """
        az = make_regen_high_expansion(n_stations=20).solve()
        cok = make_regen_high_expansion(n_stations=50).solve()

        assert az['throat_index'] >= 2, (
            'konverjan bölüm tek segmentte kalıyor '
            f"(throat_index={az['throat_index']}, n={az['n_stations']}): "
            'birinci mertebe yukarı-akım entegrali o segmentin tamamını '
            'boğaz akısıyla dolduruyor')

        q_az = az['summary']['total_heat_W']
        q_cok = cok['summary']['total_heat_W']
        assert q_az == pytest.approx(q_cok, rel=1e-2), (
            f'aynı devre, iki ızgara: Q(20)={q_az:.1f} W ⟷ '
            f'Q(50)={q_cok:.1f} W (sapma %{100.0 * abs(q_az / q_cok - 1):.2f})')

    # ÇEVİRİ (ÖH D15 birleşme düzeltmesi) — BORÇ İMİ KALKTI.
    # Bu bekçi P4B2-01 borcunu xfail(strict) ile taşıyordu;
    # imin kendi metni "onarım gelince bu im KALKAR" diyordu.
    # Kusur ÖH D15 termo-ucus a3 (06a99d4) tarafından
    # ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta test
    # GEÇİYOR ve strict im XPASS ile kırmızı veriyordu. İm
    # kaldırıldı; iddia artık CANLI bekçidir — onarım geri
    # alınırsa burası kırmızı verir.
    #
    # ÜRÜNDEKİ KANIT: hrma/analysis/regen_cooling.py:1104-1108
    # kamara gövdesi konturun başına ekleniyor; :1168
    # _barrel_length_mm (tek kaynak: motor_data['chamber_length']);
    # :1164 chamber_barrel_length_mm beyanı
    #
    # KALKAN İMİN GEREKÇESİ (kayıt için): ÖH defter P4B2-01 —
    # _build_stations (regen_cooling.py:933-975) ızgarayı YALNIZ
    # sample_nozzle_inner_contour üstünde kuruyor; o konturun z=0'ı
    # KAMARA ÇIKIŞIDIR (nozzle_design.py:1062), yani silindirik
    # kamara gövdesi ceket modelinde YOK ve hiçbir girdiyle
    # eklenemiyor (md_geo kamara BOYUNU taşımıyor). Ölçülen:
    # chamber_length 0,10 m ⟷ 0,40 m ile total_heat_W BİT BİREBİR
    # AYNI (126.913,760323 W) ve ızgara açıklığı iki durumda da
    # 94,89 mm. Rapor ölçümü: gövde eklenirse ısı +%57,8..+89,5,
    # T_out +142,6..+220,6 K, ceket ΔP +%45..56 — üç sayı da AŞAĞI
    # yönde yanlış. Onarım gelince bu im KALKAR.
    def test_jacket_grid_sees_the_cylindrical_chamber_barrel(self):
        """Ceket, ısıttığı yüzeyin tamamını görmeli (kamara gövdesi dahil).

        Modülün kendi künyesi 'thrust chambers and nozzles' (:3-5) ve marş
        künyesi 'coolant ... flows toward the throat and chamber' (:57-65)
        diyor; ``liquid_rocket_engine.py:3832-3836`` da 'the full nozzle is
        inside the jacket' cümlesini üretiyor. İddia bu künyelerin
        DAVRANIŞTAKİ karşılığıdır — hangi L* modelinin doğru olduğuna
        hükmetmez, yalnız gövdenin ceket sözleşmesinde GÖRÜNMESİ gerektiğini
        söyler.
        """
        md = dict(chamber_pressure=20.0, chamber_temperature=3000.0,
                  gamma=1.2, molecular_weight=24.0, throat_diameter=0.03,
                  expansion_ratio=6.0, chamber_diameter=0.045)
        ortak = dict(coolant='water', coolant_mdot=6.0,
                     coolant_inlet_temp=300.0, coolant_inlet_pressure=40e5,
                     n_channels=60, channel_width=1.5e-3,
                     channel_height=3.0e-3, wall_thickness=1.0e-3,
                     wall_material='cucrzr', n_stations=40,
                     coolant_props_source='table')
        kisa = RegenCooling.from_motor_data(
            dict(md, chamber_length=0.10), **ortak).solve()
        uzun = RegenCooling.from_motor_data(
            dict(md, chamber_length=0.40), **ortak).solve()

        span_mm = float(uzun['x_mm'][-1]) - float(uzun['x_mm'][0])
        assert span_mm > 400.0, (
            f'ceket ızgarası {span_mm:.2f} mm eksenel aralık kaplıyor; '
            'yalnız 400 mm\'lik silindirik gövde bile bundan uzun — ızgara '
            'kamara çıkışında başlıyor')

        q_kisa = kisa['summary']['total_heat_W']
        q_uzun = uzun['summary']['total_heat_W']
        assert q_uzun > 1.05 * q_kisa, (
            f'kamara boyu 0,10 m → 0,40 m olurken ısı yükü {q_kisa:.6f} W → '
            f'{q_uzun:.6f} W: ceket gövdeyi görmüyor')

    def test_x_monotonic_increasing(self):
        x = np.array(make_regen().solve()['x_mm'])
        assert np.all(np.diff(x) > 0)

    def test_throat_mach_unity(self):
        res = make_regen().solve()
        ti = res['throat_index']
        assert res['mach'][ti] == pytest.approx(1.0, abs=1e-9)
        assert res['area_ratio'][ti] == pytest.approx(1.0, abs=1e-9)

    def test_from_motor_data_constructor(self):
        md = dict(chamber_pressure=25.0, chamber_temperature=3100.0, gamma=1.18,
                  molecular_weight=23.0, throat_diameter=0.025, expansion_ratio=8.0)
        r = RegenCooling.from_motor_data(
            md, coolant='water', coolant_mdot=4.0, coolant_inlet_temp=300.0,
            coolant_inlet_pressure=40e5, n_channels=50, channel_width=1.5e-3,
            channel_height=3e-3, wall_thickness=1e-3, coolant_props_source='table')
        res = r.solve()
        assert res['n_stations'] > 0
        assert r.chamber_pressure == pytest.approx(25.0e5)


# ======================================================================
# 5) Enerji dengesi ve süreklilik
# ======================================================================
class TestEnergyAndContinuity:

    def test_energy_balance_closed(self):
        # soğutucuya geçen ısı = m*cp_mean*dT (kapalı entalpi dengesi)
        res = make_regen().solve()
        s = res['summary']
        q_total = s['total_heat_W']
        mcpdt = 6.0 * s['coolant_cp_mean_J_kgK'] * s['coolant_dT_K']
        assert abs(q_total - mcpdt) / q_total < 1e-3

    def test_energy_balance_surface_integral(self):
        """ŞEMA ÖZDEŞLİĞİ kilidi — BAĞIMSIZ bir kuadratür DEĞİLDİR.

        DÜZELTME (ÖH FAZ B-4/P2, defter P4B2-11): bu bekçinin eski yorumu
        'BAĞIMSIZ yeniden kur' diyordu, oysa aşağıdaki döngü kodun KENDİ
        marş şemasını, KENDİ istasyon sırasını ve KENDİ alan elemanını
        birebir yeniden uygular — bu yüzden rel=1e-9 ile tutar ve şema
        kaynaklı hiçbir hatayı göremez. Bekçinin gerçek değeri şudur ve
        yalnız bu kadardır: yayımlanan ``total_heat_W``, yayımlanan
        ``q_MW_m2``/``x_mm``/``r_mm`` dizileriyle AYNI şemadan çıkmıştır
        (diziler ile toplam arasında sessiz bir kopukluk yok).

        ÇEVİRİ (ÖH D15 / bekci-cevirisi, defter OH-Z5-15). PK5 paketi
        P4B2-11'i onardı: segment ısısı artık BİRİNCİ MERTEBE YUKARI-AKIM
        değil, iki uç istasyonun akı ORTALAMASIDIR (trapez) ve marş bir
        sabit nokta yinelemesiyle kapatılır
        (``hrma/analysis/regen_cooling.py`` marş bloğu; sabitler
        ``REGEN_MARCH_TOL`` / ``REGEN_MARCH_MAX_PASSES``). Bu bekçi eski
        şemayı yeniden uyguladığı için kırmızıya döndü; PK5 raporu
        kırılmayı BEYAN ETTİ ve testin kendisine dokunmadı. Burada bekçi
        onarımdan SONRAKİ şemaya çevriliyor — iddia aynı kalıyor, yalnız
        hangi şemanın özdeşliğinin kilitlendiği güncelleniyor.

        ÖLÇÜLDÜ (bu depo, ÇEVİRİDEN ÖNCE — betik:
        ``docs/scofield/raw/OH/D15/bekci-cevirisi/a1/olcum_regen.py``):

        ============  ==================  ==================
        devre         eski yukarı-akım    yeni trapez marş
        ============  ==================  ==================
        taban         %1,0126 sapma       0,0 (bit-aynı)
        eps=25        %1,9549 sapma       1,57e-13
        ============  ==================  ==================

        Yani eski şema artık yayımlanan toplamı TUTMUYOR (kilit oradaydı),
        yeni şema makine hassasiyetinde tutuyor.

        Şemadan bağımsız ölçüm kardeş bekçidedir:
        ``test_energy_balance_independent_quadrature`` (P4B2-11).
        """
        # Varsayılan counterflow marşı: sıra [n-1,...,0].
        r = make_regen()
        res = r.solve()
        n = res['n_stations']
        x_m = np.array(res['x_mm']) / 1e3
        r_m = np.array(res['r_mm']) / 1e3
        q = np.array(res['q_MW_m2']) * 1e6
        order = list(range(n - 1, -1, -1))   # counterflow
        Q = 0.0
        Q_upwind = 0.0
        for k in range(len(order) - 1):
            i, j = order[k], order[k + 1]
            ds = math.hypot(x_m[j] - x_m[i], r_m[j] - r_m[i])
            dA = 2.0 * math.pi * 0.5 * (r_m[i] + r_m[j]) * ds
            Q += 0.5 * (q[i] + q[j]) * dA      # ürünün ŞU ANKİ şeması
            Q_upwind += q[i] * dA              # ONARIMDAN ÖNCEKİ şema
        pub = res['summary']['total_heat_W']
        assert Q == pytest.approx(pub, rel=1e-9), (
            f'yayımlanan toplam {pub:.6f} W, yayımlanan dizilerin marş '
            f'trapezi {Q:.6f} W — diziler ile toplam AYRI şemadan çıkıyor')
        # Onarımın gerçekten yürürlükte olduğunun kilidi: birinci mertebe
        # yukarı-akım toplamı artık yayımlanan toplamı VERMEZ. Bu ayak
        # olmadan şema sessizce geri alınabilirdi (ölçülen sapma %1,0126).
        assert abs(Q_upwind / pub - 1.0) > 1.0e-3, (
            f'yukarı-akım toplamı {Q_upwind:.6f} W yayımlanan toplamla '
            f'({pub:.6f} W) ayırt edilemiyor — P4B2-11 onarımı geri '
            'alınmış olabilir')

    # ÇEVİRİ (ÖH D15 birleşme düzeltmesi) — BORÇ İMİ KALKTI.
    # Bu bekçi P4B2-11 borcunu xfail(strict) ile taşıyordu;
    # imin kendi metni "onarım gelince bu im KALKAR" diyordu.
    # Kusur ÖH D15 termo-ucus a3 (06a99d4) tarafından
    # ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta test
    # GEÇİYOR ve strict im XPASS ile kırmızı veriyordu. İm
    # kaldırıldı; iddia artık CANLI bekçidir — onarım geri
    # alınırsa burası kırmızı verir.
    #
    # ÜRÜNDEKİ KANIT: hrma/analysis/regen_cooling.py:1421 trapez
    # marş; kardeş bekçi test_energy_balance_surface_integral zaten
    # yeni şemaya çevrilmişti ve eski yukarı-akım toplamının AYIRT
    # EDİLEBİLİR olduğunu kilitliyor
    #
    # KALKAN İMİN GEREKÇESİ (kayıt için): ÖH defter P4B2-11 — ısı
    # entegrali birinci mertebe yukarı-akım
    # (regen_cooling.py:1283-1290: dQ = q·dA, q YUKARI-AKIM
    # istasyonundan). Yayımlanan dizinin bağımsız trapez entegrali
    # ile yayımlanan total_heat_W çelişiyor: ölçülen taban devrede
    # 127.393,47 W ⟷ 126.913,76 W (%0,378), ε=25 devrede 4.618.774,0
    # W ⟷ 4.545.511,6 W (%1,61). Onarım gelince bu im KALKAR.
    def test_energy_balance_independent_quadrature(self):
        """Yayımlanan dizi ile yayımlanan toplam aynı sayıyı vermeli.

        P15 reçetesi: aynı fiziksel büyüklük iki kanaldan yayımlanıyorsa
        (istasyon dizisi ⟷ özet toplamı) iki kanal ayrışamaz. Bu bekçi
        kodun marş şemasını yeniden uygulamaz; yalnız yayımlanan üç diziyi
        trapez kuralıyla entegre eder (``independent_wetted_integral``).
        Hangi kanalın doğru olduğuna HÜKMETMEZ — yalnız ayrıştıklarını
        ölçer.
        """
        for etiket, kur in (('taban', make_regen),
                            ('eps=25', make_regen_high_expansion)):
            res = kur().solve()
            q_pub = res['summary']['total_heat_W']
            q_trapez = independent_wetted_integral(res)
            assert q_trapez == pytest.approx(q_pub, rel=1e-3), (
                f'{etiket}: yayımlanan q(x) dizisinin trapez entegrali '
                f'{q_trapez:.1f} W, yayımlanan total_heat_W {q_pub:.1f} W '
                f'(sapma %{100.0 * abs(q_trapez / q_pub - 1):.3f})')

    def test_cp_mean_physical_for_water(self):
        # Enerji-dengesi cp_mean su için fiziksel bantta olmalı (~4180)
        s = make_regen().solve()['summary']
        assert 4150.0 < s['coolant_cp_mean_J_kgK'] < 4300.0

    def test_channel_velocity_continuity(self):
        # mdot_ch = rho * V * A_c her istasyonda (süreklilik)
        r = make_regen()
        res = r.solve()
        A_c = r.channel_area
        mdot_ch = r.mdot_per_channel
        for T, V in zip(res['T_coolant_K'], res['velocity_m_s']):
            rho = water_properties(T)['density']
            assert rho * V * A_c == pytest.approx(mdot_ch, rel=1e-9)

    def test_dittus_boelter_station_application(self):
        # h_coolant[i] = Nu(Re_i,Pr_i)*k/D_h * ST_i — uçtan uca zincir.
        # V301/L-REJ (26 Eki, Berke "Modeli bugün düzelt"): sıvı soğutucuda
        # yayımlanan h_c artık Sieder-Tate (mu_b/mu_w)^0,14 çarpanını taşır
        # (NASA SP-125 Eş. 4-23); çarpan istasyon başına
        # ``sieder_tate_factor`` dizisinde yayımlanır ve burada BAĞIMSIZ
        # olarak tablodan yeniden kurulur. Eski beklenti çarpansızdı.
        from hrma.analysis.regen_cooling import sieder_tate_factor
        r = make_regen()
        res = r.solve()
        Dh = r.hydraulic_diameter
        for T, Tw, Re, h, st in zip(res['T_coolant_K'], res['T_wall_cold_K'],
                                    res['reynolds'], res['h_coolant_W_m2K'],
                                    res['sieder_tate_factor']):
            p = water_properties(T)
            nu = dittus_boelter_nu(Re, p['prandtl'], heating=True)
            st_bagimsiz = sieder_tate_factor(
                p['viscosity'], water_properties(Tw)['viscosity'])
            # Çarpan, sabit noktanın SON adımından bir önceki T_wc ile
            # kurulur (yakınsama toleransı 1e-3 K) -> yeni iddia için rel 1e-5.
            assert st == pytest.approx(st_bagimsiz, rel=1e-5)
            assert h == pytest.approx(nu * p['conductivity'] / Dh * st,
                                      rel=1e-9)

    def test_wall_series_circuit_consistency(self):
        # q = h_g*(Taw - T_hot) = h_c*(T_cold - T_coolant) her istasyonda
        r = make_regen()
        res = r.solve()
        for i in range(res['n_stations']):
            q = res['q_MW_m2'][i] * 1e6
            hg = res['h_gas_W_m2K'][i]
            hc = res['h_coolant_W_m2K'][i]
            taw = res['T_recovery_K'][i]
            thot = res['T_wall_hot_K'][i]
            tcold = res['T_wall_cold_K'][i]
            tcool = res['T_coolant_K'][i]
            # V301/L-REJ: soğutucu tarafı alanı kanat oranıyla ölçeklenir
            # (A_eff/A_gaz; eskiden su/RP-1'de 1 sayılıyordu).
            ar = res['fin_area_ratio'][i]
            assert q == pytest.approx(hg * (taw - thot), rel=1e-4)
            assert q == pytest.approx(hc * ar * (tcold - tcool), rel=1e-4)


# ======================================================================
# 6) Akış yönü (ters akış / eş akış)
# ======================================================================
class TestFlowDirection:

    def test_counterflow_inlet_at_exit(self):
        # Varsayılan counterflow: soğutucu çıkış ucundan girer (en soğuk)
        res = make_regen(flow_direction='counterflow').solve()
        assert res['T_coolant_K'][-1] == pytest.approx(300.0, abs=1e-9)  # çıkış ucu
        # Kamara ucuna doğru ısınır: T_coolant x ile AZALIR
        assert res['T_coolant_K'][0] > res['T_coolant_K'][-1]
        # Basınç girişte (çıkış ucunda) en yüksek
        assert res['P_coolant_bar'][-1] == pytest.approx(40.0, abs=1e-9)

    def test_coflow_inlet_at_chamber(self):
        res = make_regen(flow_direction='coflow').solve()
        assert res['T_coolant_K'][0] == pytest.approx(300.0, abs=1e-9)   # kamara ucu
        # Çıkışa doğru ısınır: T_coolant x ile ARTAR
        assert res['T_coolant_K'][-1] > res['T_coolant_K'][0]
        assert res['P_coolant_bar'][0] == pytest.approx(40.0, abs=1e-9)

    def test_flow_direction_changes_wall_profile(self):
        # Aynı geometri, ters yön -> cidar sıcaklık dağılımı farklı
        cf = make_regen(flow_direction='counterflow').solve()
        co = make_regen(flow_direction='coflow').solve()
        assert cf['T_wall_hot_K'] != co['T_wall_hot_K']

    def test_pressure_monotonic_along_flow(self):
        # Basınç akış boyunca kesin azalır (sürtünme kaybı)
        res = make_regen(flow_direction='coflow').solve()
        p = np.array(res['P_coolant_bar'])   # coflow: x artışı = akış yönü
        assert np.all(np.diff(p) < 0)


# ======================================================================
# 7) Basınç düşümü tutarlılığı
# ======================================================================
class TestPressureDrop:

    def test_total_dp_matches_inlet_minus_outlet(self):
        r = make_regen()
        res = r.solve()
        s = res['summary']
        expected = 40.0 - s['coolant_exit_pressure_bar']
        assert s['total_pressure_drop_bar'] == pytest.approx(expected, rel=1e-9)

    def test_total_dp_positive(self):
        s = make_regen().solve()['summary']
        assert s['total_pressure_drop_bar'] > 0.0

    def test_higher_mdot_higher_dp(self):
        # Daha yüksek debi -> daha yüksek hız -> daha yüksek dP
        dp_low = make_regen(coolant_mdot=4.0).solve()['summary']['total_pressure_drop_bar']
        dp_high = make_regen(coolant_mdot=10.0).solve()['summary']['total_pressure_drop_bar']
        assert dp_high > dp_low


# ======================================================================
# 8) Malzeme limiti ve koklaşma uyarıları
# ======================================================================
class TestWarnings:

    def test_material_limit_warning_hot_case(self):
        # Zayıf soğutma (az kanal, ince, düşük debi, yüksek Pc) -> cidar aşımı
        res = make_regen(chamber_pressure=70e5, coolant_mdot=0.5,
                         n_channels=20, channel_height=1.0e-3,
                         wall_material='steel').solve()
        s = res['summary']
        assert s['max_wall_hot_K'] > s['material_allowable_temp_K']
        assert any('wall' in w.lower() for w in s['warnings'])

    def test_wellcooled_within_limits(self):
        # Temel su/CuCrZr durumu limitler içinde (kanal sayısı sığar)
        s = make_regen(n_channels=40).solve()['summary']
        assert s['max_wall_hot_K'] < s['material_service_limit_K']

    def test_rp1_coking_warning(self):
        # RP-1 + sıcak cidar -> koklaşma bayrağı + uyarı
        res = make_regen(coolant='rp1', coolant_inlet_temp=300.0,
                         chamber_pressure=60e5, coolant_mdot=1.0,
                         n_channels=30, channel_height=1.5e-3,
                         wall_material='copper').solve()
        s = res['summary']
        assert s['max_wall_cold_K'] > RP1_COKING_TEMP_K
        # V301/L-KABUK (ana model kararı, 27 Eki): kok eşiği İKİ KADEME.
        # coking / coking_threshold_K = 728 K NASA SP-8087 hüküm kademesi;
        # coking_risk / coking_warning_threshold_K = 561 K uyarı kademesi.
        # Bu vakanın soğutucu tarafı iki kademeden hangisini aştıysa o bayrak.
        from hrma.analysis.regen_cooling import RP1_COKING_LIMIT_TEMP_K
        assert s['coking_risk'] is True
        assert s['coking'] is (s['max_wall_cold_K'] > RP1_COKING_LIMIT_TEMP_K)
        assert s['coking_threshold_K'] == pytest.approx(
            RP1_COKING_LIMIT_TEMP_K)
        assert s['coking_warning_threshold_K'] == pytest.approx(
            RP1_COKING_TEMP_K)
        assert any('cok' in w.lower() for w in s['warnings'])

    def test_water_no_coking_flag(self):
        # Su koklaşmaz: bayrak False, eşik None
        s = make_regen().solve()['summary']
        assert s['coking'] is False
        assert s['coking_threshold_K'] is None

    def test_geometry_warning_channels_dont_fit(self):
        # Çok fazla geniş kanal -> boğaz çevresine sığmaz uyarısı
        res = make_regen(n_channels=400, channel_width=2.0e-3).solve()
        assert any('geometry' in w.lower() or 'channel' in w.lower()
                   for w in res['summary']['warnings'])


# ======================================================================
# 9) Çıktı sağlığı ve fizik işaretleri
# ======================================================================
class TestOutputSanity:
    """Çıktı sağlığı.

    NOT (ÖH FAZ B-4/P2, defter P4B2-03): bu sınıf uzun süre yalnız
    ``q>0``, ``v>0`` ve ``T_hot>=T_cold`` sıralamalarını sordu; yayımlanan
    sıcaklıkların MUTLAK SICAKLIK olup olmadığını hiç sormadı. Marşta
    (regen_cooling.py:1320-1328) ne ``dT``ye ne ``T``ye sınır olduğundan
    ölçülen uçta 14 istasyon mutlak sıfırın altına iniyor. Aşağıdaki iki
    bekçi o ekseni açar: biri sağlıklı devrede sözleşmeyi kurar, öteki
    patolojik devrede bugünkü açığı kırmızı tutar.
    """

    def test_positive_fluxes_and_velocities(self):
        res = make_regen().solve()
        assert all(q > 0 for q in res['q_MW_m2'])
        assert all(v > 0 for v in res['velocity_m_s'])
        assert all(h > 0 for h in res['h_coolant_W_m2K'])
        assert all(h > 0 for h in res['h_gas_W_m2K'])

    def test_wall_hot_above_cold(self):
        # İç (gaz) cidar her zaman dış (soğutucu) cidardan sıcak
        res = make_regen().solve()
        for thot, tcold in zip(res['T_wall_hot_K'], res['T_wall_cold_K']):
            assert thot >= tcold

    def test_wall_between_coolant_and_recovery(self):
        res = make_regen().solve()
        for i in range(res['n_stations']):
            tcool = res['T_coolant_K'][i]
            thot = res['T_wall_hot_K'][i]
            taw = res['T_recovery_K'][i]
            assert tcool <= thot <= taw

    def test_peak_heat_flux_near_throat(self):
        # En yüksek gaz-tarafı akısı boğaz civarında olmalı
        res = make_regen().solve()
        q = np.array(res['q_MW_m2'])
        ti = res['throat_index']
        assert abs(int(np.argmax(q)) - ti) <= 2

    def test_summary_keys_present(self):
        s = make_regen().solve()['summary']
        for k in ['coolant', 'wall_material', 'coolant_exit_temp_K',
                  'coolant_dT_K', 'total_heat_W', 'total_pressure_drop_bar',
                  'max_wall_hot_K', 'max_wall_cold_K', 'material_allowable_temp_K',
                  'coking', 'flow_direction', 'warnings']:
            assert k in s, k

    def test_model_note_and_references(self):
        res = make_regen().solve()
        note = res['model_note'].lower()
        assert 'bartz' in note
        assert 'dittus' in note
        assert 'haaland' in note

    # -- ÖH FAZ B-4/P2 · defter P4B2-03 -----------------------------------
    def test_published_temperatures_are_absolute_temperatures(self):
        """Yayımlanan HER sıcaklık mutlak sıfırın üstünde olmalı.

        Sağlıklı devrede bugün doğru olan sözleşme burada YAZILI hâle
        getirilir. Ölçüldü (ÖH FAZ B-4/P2): bu satırlardan önce depoda
        yayımlanan bir regen sıcaklığının mutlak sıfırın üstünde olduğunu
        SÖYLEYEN tek bir iddia yoktu — mevcut iddiaların tamamı ya SIRALAMA
        (T_hot>=T_cold, T_cool<=T_hot<=T_aw) ya da yayımlanan alanlardan
        yeniden kurulan ÖZDEŞLİK biçimindeydi; ikisi de bir işaret tabanı
        kurmaz. Patolojik devredeki bugünkü açık kardeş bekçidedir:
        ``test_marching_never_publishes_a_negative_absolute_temperature``.
        """
        res = make_regen().solve()
        for anahtar in ('T_coolant_K', 'T_wall_hot_K', 'T_wall_cold_K',
                        'T_recovery_K'):
            kotu = [(i, t) for i, t in enumerate(res[anahtar]) if not t > 0.0]
            assert not kotu, (
                f'{anahtar}: mutlak sıfırın altında/sıfırda yayımlanan '
                f'istasyonlar {kotu[:5]} (toplam {len(kotu)})')
        s = res['summary']
        for anahtar in ('coolant_exit_temp_K', 'max_wall_hot_K',
                        'max_wall_cold_K'):
            assert s[anahtar] > 0.0, f'summary.{anahtar} = {s[anahtar]}'

    # ÇEVİRİ (ÖH D15 fix-3 / taban geçişi) — BORÇ İMİ KALKTI.
    # Bu bekçi P4B2-03 borcunu ``xfail(strict=True)`` ile taşıyordu;
    # imin kendi metni "onarım gelince bu im KALKAR" diyordu. Kusur
    # ÖH Z5S / PK5 (ısı-soğutma kulvarı, commit bba33e4) tarafından
    # ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta test GEÇİYOR
    # ve strict im XPASS(strict) ile KIRMIZI veriyordu. İm kaldırıldı;
    # iddia artık CANLI bekçidir — onarım geri alınırsa burası kırmızı
    # verir.
    #
    # ÜRÜNDEKİ KANIT: hrma/analysis/regen_cooling.py:1611 "ÖH Z5S / PK5
    # (P4B2-03) — FİZİK KAPISI, FAIL-CLOSED."; :1622 "'MODEL OUT OF
    # ENVELOPE' + NOT_MODELLED" deseni; :1628 "cannot be evaluated from
    # a non-physical state".
    def test_marching_never_publishes_a_negative_absolute_temperature(self):
        """Fizik dışı sıcaklık ya üretilmez ya da ADIYLA bildirilir.

        Kabul edilen üç davranıştan biri yeter (fail-closed politikası):
          (a) marş fizik dışı duruma girince ``ValueError`` ile durur,
          (b) yayımlanan hiçbir istasyon mutlak sıfırın altına inmez,
          (c) uyarılardan biri fizik dışılığı ADIYLA söyler.
        Bugün üçü de yok. Kardeş modülün doğru deseni depoda YAZILI:
        ``thermal_protection`` zarf dışında sayı üretmek yerine
        'MODEL OUT OF ENVELOPE' + NOT_MODELLED diyor.
        """
        r = RegenCooling(
            chamber_pressure=70e5, chamber_temperature=3500.0, gamma=1.2,
            molecular_weight=22.0, throat_diameter=0.10, expansion_ratio=25.0,
            coolant='rp1', coolant_mdot=1e-9, coolant_inlet_temp=300.0,
            coolant_inlet_pressure=100e5, n_channels=100,
            channel_width=2.0e-3, channel_height=3.0e-3,
            wall_thickness=1.0e-3, wall_material='copper', n_stations=40,
            coolant_props_source='table')
        try:
            res = r.solve()
        except ValueError:
            return                      # (a) fail-closed: kabul

        t = np.asarray(res['T_coolant_K'], dtype=float)
        negatif = int(np.sum(t < 0.0))
        if negatif == 0:
            return                      # (b) fizik dışı sayı yayımlanmadı

        adlandiran = [w for w in res['summary']['warnings']
                      if any(s in w.lower() for s in
                             ('negative', 'non-physical', 'nonphysical',
                              'unphysical', 'not modelled', 'not_modelled',
                              'out of envelope', 'invalid'))]
        assert adlandiran, (                                       # (c)
            f'{negatif} istasyon MUTLAK SIFIRIN ALTINDA '
            f'(min {t.min():.1f} K, max {t.max():.1f} K) ve '
            f"{len(res['summary']['warnings'])} uyarının hiçbiri bunu "
            'adlandırmıyor')


# ======================================================================
# 10) CoolProp yolu (kuruluysa)
# ======================================================================
class TestCoolProp:

    def test_coolprop_water_matches_reference(self):
        cp = pytest.importorskip('CoolProp')
        from CoolProp.CoolProp import PropsSI
        r = make_regen(coolant_props_source='coolprop')
        props = r._coolant_properties(320.0, 40e5)
        assert props['source'] == 'coolprop'
        assert props['density'] == pytest.approx(
            PropsSI('D', 'T', 320.0, 'P', 40e5, 'Water'), rel=1e-9)

    def test_coolprop_and_table_agree_within_band(self):
        pytest.importorskip('CoolProp')
        r_cp = make_regen(coolant_props_source='coolprop').solve()
        r_tb = make_regen(coolant_props_source='table').solve()
        # İki kaynak, entegre ısı ~ %10 içinde uyuşmalı
        q_cp = r_cp['summary']['total_heat_W']
        q_tb = r_tb['summary']['total_heat_W']
        assert abs(q_cp - q_tb) / q_tb < 0.10


# ======================================================================
# 11) Özellik tablosu geçerlilik zarfı (fizik denetimi F057)
# ======================================================================
class TestPropertyTableEnvelope:
    """Tablo bandı dışına taşan istasyonlar bildirilmeli.

    F057: ``_interp_table`` 'clamped' bayrağını üretiyor ama ``solve()``
    onu HİÇ okumuyordu. RP-1 tablosu 500 K'de, su tablosu 400 K'de bitiyor;
    band dışında özellikler en yakın uca DONUYOR. Ölçülen etki (su, 459 K /
    80 bar, CoolProp referanslı): mu %48 yüksek, Pr 1.342 yerine 0.960,
    h_c oranı 0.856 — yani soğutucu tarafı katsayısı %14 eksik. Bu testler
    (a) band içinde yanlış alarm olmadığını, (b) band dışında uyarının ve
    sayacın geldiğini kilitler.
    """

    def test_in_band_case_reports_no_clamp(self):
        s = make_regen(coolant_props_source='table').solve()['summary']
        assert s['property_table_clamped_stations'] == 0
        # V301/L-REJ: YIĞIN bandı içinde -> yığın klamp uyarısı yok. Cidar
        # tarafının (Sieder-Tate mu_w) bant dışı beyanı AYRI adlıdır
        # ('PROPERTY RANGE (WALL)') ve bu devrede soğutucu tarafı cidar
        # 400 K'yi aştığı için beklenir.
        assert not [w for w in s['warnings']
                    if w.startswith('PROPERTY RANGE:')]

    def test_out_of_band_rp1_warns(self):
        r = RegenCooling(
            chamber_pressure=70e5, chamber_temperature=3500.0, gamma=1.2,
            molecular_weight=22.0, throat_diameter=0.06, expansion_ratio=20.0,
            coolant='rp1', coolant_mdot=0.8, coolant_inlet_temp=300.0,
            coolant_inlet_pressure=120e5, n_channels=80,
            channel_width=1.5e-3, channel_height=3.0e-3,
            wall_thickness=1.0e-3, wall_material='copper', n_stations=30)
        s = r.solve()['summary']
        # Bu devre soğutucuyu 500 K RP-1 tablo sınırının çok üstüne taşır.
        assert s['coolant_exit_temp_K'] > 500.0
        assert s['property_table_clamped_stations'] > 0
        assert s['property_table_band_K'] == [290.0, 500.0]
        hits = [w for w in s['warnings'] if 'PROPERTY RANGE' in w]
        # DÜZELTME (ÖH FAZ B-4/P2, defter P4B2-03): eski hâli
        # ``len(hits) == 1`` idi. Bu eşitlik bekçiyi ÜST sınıra da
        # kilitliyordu: modül aynı duruma ikinci bir hüküm (ör. sıcaklığın
        # model zarfının dışına çıktığını ADIYLA söyleyen uyarı) eklerse
        # bekçi kırmızıya düşerdi — yani doğru yönde bir onarımı
        # engelliyordu. Buradaki iddia "uyarı GELİYOR mu"dur; kaç tane
        # geldiği bir sözleşme değildir.
        assert len(hits) >= 1
        # Uyarı hangi bandın aşıldığını ve kaç istasyonu etkilediğini söylemeli
        assert '290-500 K' in hits[0]
        assert 'FROZEN' in hits[0]

    # ÇEVİRİ (ÖH D15 fix-3 / taban geçişi) — BORÇ İMİ KALKTI.
    # Aynı kalemin (P4B2-03) ikinci ayağı; kardeş ayağıyla birlikte
    # ÖH Z5S / PK5 (bba33e4) tarafından ONARILDI ve im BAYATLADI:
    # birleşik ağaçta test GEÇİYOR, strict im XPASS(strict) ile kırmızı
    # veriyordu. İm kaldırıldı; iddia CANLI bekçidir.
    #
    # ÜRÜNDEKİ KANIT: hrma/analysis/regen_cooling.py:1715 "ÖH Z5S / PK5
    # (P4B2-03) — MODEL ZARFI BEYANI."; :1740 f"MODEL OUT OF ENVELOPE:
    # {self.coolant} bulk temperature ...".
    def test_far_out_of_band_coolant_temperature_is_declared_out_of_envelope(self):
        """Tavanın katlarına çıkan sıcaklık 'dondurulmuş özellik' değildir.

        Bant kenarında donmuş özellikler bir DOĞRULUK sorunudur ve bugünkü
        PROPERTY RANGE uyarısı onu dürüstçe bildirir. Tavanın 5 katına çıkan
        bir 'soğutucu sıcaklığı' ise artık bir doğruluk sorunu değil, model
        zarfının terk edilmesidir: RP-1 o sıcaklıkta sıvı değildir, cp/rho
        tablosunun uzantısı diye bir şey yoktur. Depo bu ayrımın doğru
        desenini başka modülde yazmıştır (``thermal_protection``:
        'MODEL OUT OF ENVELOPE' + NOT_MODELLED + gerekçe). Bu bekçi o desenin
        soğutucu tarafındaki karşılığını ister; hangi eşiğin doğru olduğuna
        HÜKMETMEZ, yalnız 5× aşımın adlandırılmasını ister.
        """
        s = make_regen_high_expansion(
            throat_diameter=0.06, coolant_mdot=0.01, n_channels=100,
            channel_width=1.5e-3, n_stations=40).solve()['summary']
        tavan = s['property_table_band_K'][1]
        cikis = s['coolant_exit_temp_K']
        if cikis is None:
            return                      # sonuç geri çekildi: kabul
        assert cikis > 2.0 * tavan, (
            f'ön koşul: bu devre tavanı katlarca aşmalı (çıkış {cikis:.1f} K, '
            f'tavan {tavan:.1f} K)')

        hukum = [w for w in s['warnings']
                 if any(k in w.lower() for k in
                        ('out of envelope', 'not modelled', 'not_modelled',
                         'unphysical', 'non-physical', 'invalid',
                         'withheld'))]
        assert hukum, (
            f'soğutucu çıkışı {cikis:.1f} K = tablo tavanının '
            f'{cikis / tavan:.1f} katı, ama {len(s["warnings"])} uyarının '
            'hiçbiri sonucu model zarfının dışında saymıyor — yalnız '
            'özelliklerin donduğu söyleniyor')

    def test_interp_table_exposes_band(self):
        p = rp1_properties(600.0)
        assert p['clamped'] is True
        assert p['table_t_min_K'] == 290.0
        assert p['table_t_max_K'] == 500.0
        # Klamp gerçekten donduruyor: 600 K ve 500 K aynı değerleri verir
        assert p['density'] == pytest.approx(rp1_properties(500.0)['density'])
        assert water_properties(350.0)['clamped'] is False


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
