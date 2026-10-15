"""Su koçu (water hammer) besleme hattı analizi doğrulama testleri.

El-hesabı çapaları (Wylie & Streeter, "Fluid Transients"; Joukowsky 1898):

- Rijit borudaki ses hızı a = sqrt(K/rho): su için ~1481 m/s (K=2.19 GPa,
  rho=998) — literatürle uyumlu.
- Klasik çelik boru örneği (K=2.19 GPa, rho=998, D=0.5 m, t=5 mm, E=200 GPa):
  esneklik düzeltmeli a ~= 1023.4 m/s, dv=2 m/s -> dP ~= 20.43 bar.
- Joukowsky dP = rho*a*dv birim tutarlılığı (rho=1000, a=1200, dv=2 -> 2.4 MPa).
- Yavaş kapanma limitleri: t_close -> t_c iken ani değere, t_close -> sonsuz
  iken sıfıra.
"""

import math

import pytest

from hrma.data.materials_db import get_material
from hrma.analysis.water_hammer import (
    WaterHammerAnalyzer,
    wave_speed,
    joukowsky_pressure_rise,
    critical_closure_time,
    slow_closure_pressure_rise,
    COLUMN_SEPARATION_PEAK_FACTOR,
    DEFAULT_PIPE_MATERIAL,
    FLUID_PROPERTIES,
)


# ===========================================================================
# Modül-düzeyi analitik yardımcılar (saf el hesabı)
# ===========================================================================
class TestWaveSpeed:
    def test_rigid_water_matches_sound_speed(self):
        """Rijit borulu su hızı a = sqrt(K/rho) ~= 1481 m/s (K=2.19 GPa)."""
        a_el, a_rigid = wave_speed(2.19e9, 998.0, 0.5, 0.005, 200e9)
        assert a_rigid == pytest.approx(math.sqrt(2.19e9 / 998.0), rel=1e-12)
        # KÜNYE (yerel): a = sqrt(K/rho) = sqrt(2,19e9/998) = 1481,35 m/s.
        # K = 2,19 GPa ve rho = 998 kg/m^3, 20 C suyun standart değerleri
        # (Wylie & Streeter, "Fluid Transients", su tablosu). Üstteki satır
        # özdeşliği 1e-12'de kilitliyor; bu satır SAYININ literatürdeki
        # ses hızıyla (~1480 m/s) uyuştuğunu söyler.
        assert a_rigid == pytest.approx(1481.35, rel=1e-3)

    def test_elasticity_reduces_wave_speed(self):
        """Esneklik düzeltmesi dalga hızını DAİMA düşürür (a_el < a_rigid)."""
        a_el, a_rigid = wave_speed(2.19e9, 998.0, 0.5, 0.005, 200e9)
        assert a_el < a_rigid
        # Klasik çelik boru örneği el-hesabı: ~1023.4 m/s
        assert a_el == pytest.approx(1023.45, rel=1e-3)

    def test_stiffer_pipe_approaches_rigid_speed(self):
        """Daha sert/kalın boru (E*t büyük) rijit hıza yaklaşır."""
        a_thin, a_rigid = wave_speed(2.19e9, 998.0, 0.5, 0.005, 200e9)
        a_thick, _ = wave_speed(2.19e9, 998.0, 0.5, 0.050, 200e9)
        assert a_thin < a_thick < a_rigid

    def test_lower_bulk_modulus_lowers_speed(self):
        """Düşük bulk modül (N2O) su hızının çok altında dalga hızı verir."""
        a_water, _ = wave_speed(2.19e9, 998.0, 0.5, 0.005, 200e9)
        a_n2o, _ = wave_speed(0.19e9, 785.0, 0.5, 0.005, 200e9)
        assert a_n2o < a_water

    def test_wave_speed_rejects_nonpositive(self):
        for bad in ((0.0, 998.0, 0.5, 0.005, 200e9),
                    (2.19e9, 0.0, 0.5, 0.005, 200e9),
                    (2.19e9, 998.0, -0.5, 0.005, 200e9),
                    (2.19e9, 998.0, 0.5, 0.0, 200e9),
                    (2.19e9, 998.0, 0.5, 0.005, 0.0)):
            with pytest.raises(ValueError):
                wave_speed(*bad)


class TestJoukowsky:
    def test_hand_calc_pressure_rise(self):
        """dP = rho*a*dv birim tutarlılığı: 1000*1200*2 = 2.4 MPa (tam)."""
        dp = joukowsky_pressure_rise(1000.0, 1200.0, 2.0)
        assert dp == pytest.approx(2.4e6, rel=1e-12)

    def test_uses_absolute_velocity_change(self):
        """Negatif hız değişimi (yön) aynı büyüklükte basınç verir."""
        assert (joukowsky_pressure_rise(1000.0, 1200.0, -2.0)
                == pytest.approx(2.4e6, rel=1e-12))

    def test_classic_steel_pipe_example(self):
        """Klasik çelik boru su vakası: dP ~= 20.43 bar (el hesabı)."""
        a_el, _ = wave_speed(2.19e9, 998.0, 0.5, 0.005, 200e9)
        dp = joukowsky_pressure_rise(998.0, a_el, 2.0)
        # KÜNYE (yerel): Joukowsky 1898 — dP = rho*a*dv =
        # 998 * 1023,45 * 2,0 = 2,0428e6 Pa = 20,428 bar. a_el yukarıdaki
        # esneklik düzeltmeli dalga hızı (D=0,5 m, t=5 mm, E=200 GPa).
        assert dp / 1e5 == pytest.approx(20.428, rel=1e-3)

    def test_rejects_nonpositive(self):
        with pytest.raises(ValueError):
            joukowsky_pressure_rise(0.0, 1200.0, 2.0)
        with pytest.raises(ValueError):
            joukowsky_pressure_rise(1000.0, 0.0, 2.0)


class TestCriticalTime:
    def test_hand_calc(self):
        """t_c = 2L/a: L=1000 m, a=1000 m/s -> 2.0 s (tam)."""
        assert critical_closure_time(1000.0, 1000.0) == pytest.approx(2.0, rel=1e-12)

    def test_rejects_nonpositive(self):
        with pytest.raises(ValueError):
            critical_closure_time(0.0, 1000.0)
        with pytest.raises(ValueError):
            critical_closure_time(1000.0, 0.0)


class TestSlowClosure:
    def test_returns_instant_at_or_below_critical(self):
        """t_close <= t_c -> tam Joukowsky (ani) değeri döner."""
        assert slow_closure_pressure_rise(1e6, 1.0, 1.0) == pytest.approx(1e6)
        assert slow_closure_pressure_rise(1e6, 1.0, 0.5) == pytest.approx(1e6)

    def test_approaches_instant_as_tclose_to_tc(self):
        """t_close -> t_c^+ iken yavaş değer ani değere yaklaşır."""
        dp = 1e6
        near = slow_closure_pressure_rise(dp, 1.0, 1.0 + 1e-6)
        assert near == pytest.approx(dp, rel=1e-5)

    def test_approaches_zero_as_tclose_large(self):
        """t_close -> sonsuz iken yavaş basınç artışı sıfıra gider."""
        dp = 1e6
        assert slow_closure_pressure_rise(dp, 1.0, 1e9) == pytest.approx(1e-3, abs=1e-6)

    def test_monotonic_decreasing(self):
        """Kapanma süresi arttıkça basınç artışı azalır (t_close > t_c bölgesi)."""
        dp = 1e6
        vals = [slow_closure_pressure_rise(dp, 1.0, tc) for tc in (2, 5, 10, 50)]
        assert all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))

    def test_michaud_arithmetic_form(self):
        """dP_slow = dP*(t_c/t_close) = 2*rho*L*dv/t_close (iki form özdeş)."""
        rho, L, dv, a = 998.0, 100.0, 2.0, 1000.0
        t_c = 2.0 * L / a
        dp_inst = rho * a * dv
        t_close = 5.0 * t_c
        form1 = slow_closure_pressure_rise(dp_inst, t_c, t_close)
        form2 = 2.0 * rho * L * dv / t_close
        assert form1 == pytest.approx(form2, rel=1e-12)

    def test_rejects_nonpositive(self):
        with pytest.raises(ValueError):
            slow_closure_pressure_rise(1e6, 1.0, 0.0)
        with pytest.raises(ValueError):
            slow_closure_pressure_rise(1e6, 0.0, 5.0)


# ===========================================================================
# Sıvı özellik tablosu
# ===========================================================================
class TestFluidTable:
    def test_required_fluids_present(self):
        for key in ('water', 'n2o', 'rp1', 'lox'):
            assert key in FLUID_PROPERTIES

    def test_source_and_band_fields(self):
        """Her kaydın kaynak, bant, güven ve pozitif fiziksel değerleri olmalı."""
        for key, rec in FLUID_PROPERTIES.items():
            assert rec.get('source'), f"{key} missing source"
            assert rec['bulk_modulus_Pa'] > 0
            assert rec['density_kg_m3'] > 0
            assert rec.get('confidence') in ('high', 'medium', 'low')
            band = rec.get('bulk_modulus_band_Pa')
            assert band is not None and band[0] <= rec['bulk_modulus_Pa'] <= band[1]

    def test_propellants_marked_approximate(self):
        """Kriyojen/N2O/RP-1 kayıtları 'approximate' notu taşımalı."""
        for key in ('n2o', 'rp1', 'lox'):
            assert 'APPROXIMATE' in FLUID_PROPERTIES[key]['source'].upper()

    def test_water_high_confidence(self):
        assert FLUID_PROPERTIES['water']['confidence'] == 'high'

    def test_water_sound_speed_physical(self):
        """K/rho'dan su ses hızı literatür aralığında (~1480 m/s)."""
        rec = FLUID_PROPERTIES['water']
        a = math.sqrt(rec['bulk_modulus_Pa'] / rec['density_kg_m3'])
        assert 1450.0 < a < 1520.0


# ===========================================================================
# Tam analiz (analyze)
# ===========================================================================
class TestAnalyze:
    def _steel_water(self, **kw):
        params = dict(
            fluid='water', line_length_m=100.0, line_id_mm=500.0,
            wall_thickness_mm=5.0, working_pressure_bar=10.0,
            flow_velocity_m_s=2.0, pipe_material='steel_4130',
        )
        params.update(kw)
        return WaterHammerAnalyzer().analyze(**params)

    def test_classic_wave_speed_and_rise(self):
        """steel_4130 (E=200 GPa) klasik su vakası: a~1023 m/s, dP~20.4 bar."""
        out = self._steel_water()
        # KÜNYE (yerel): esneklik düzeltmeli dalga hızı (Wylie & Streeter)
        # a = sqrt(K/rho) / sqrt(1 + (K/E)*(D/t)) =
        # 1481,35 / sqrt(1 + (2,19/200)*(500/5)) = 1023,45 m/s.
        # E = 200 GPa steel_4130'un materials_db kaydından gelir.
        assert out['wave_speed_m_s'] == pytest.approx(1023.45, rel=2e-3)
        assert out['joukowsky_pressure_rise_bar'] == pytest.approx(20.43, rel=3e-3)
        assert out['wave_speed_m_s'] < out['wave_speed_rigid_m_s']

    def test_unit_consistency_pa_bar(self):
        """bar alanları Pa alanlarıyla 1e5 çarpanında tutarlı; tepe = çalışma+artış."""
        out = self._steel_water()
        assert out['applied_pressure_rise_bar'] * 1e5 == pytest.approx(
            out['applied_pressure_rise_Pa'], rel=1e-9)
        assert out['peak_pressure_bar'] == pytest.approx(
            out['working_pressure_bar'] + out['applied_pressure_rise_bar'], rel=1e-9)
        assert out['peak_pressure_Pa'] == pytest.approx(
            out['peak_pressure_bar'] * 1e5, rel=1e-9)

    def test_velocity_from_mdot(self):
        """mdot verildiğinde v = mdot/(rho*A) türetilir; hıza eşdeğer sonuç."""
        rho = FLUID_PROPERTIES['water']['density_kg_m3']
        D = 0.5
        area = math.pi * D * D / 4.0
        v = 2.0
        mdot = rho * v * area
        out = self._steel_water(flow_velocity_m_s=None, mdot_kg_s=mdot)
        assert out['flow_velocity_m_s'] == pytest.approx(v, rel=1e-9)
        # Hız yolu ile aynı basınç artışı
        out_v = self._steel_water()
        assert out['joukowsky_pressure_rise_bar'] == pytest.approx(
            out_v['joukowsky_pressure_rise_bar'], rel=1e-9)

    def test_slow_closure_below_instant(self):
        """Yavaş kapanma (t_close > t_c) ani değerin altında basınç verir."""
        out_fast = self._steel_water(valve_closure_time_ms=None)
        t_c_ms = out_fast['critical_closure_time_ms']
        out_slow = self._steel_water(valve_closure_time_ms=10.0 * t_c_ms)
        assert out_slow['closure_regime'] == 'slow'
        assert out_slow['applied_pressure_rise_bar'] < out_fast['applied_pressure_rise_bar']
        # 10x kritik süre -> ~1/10 basınç
        assert out_slow['applied_pressure_rise_bar'] == pytest.approx(
            out_fast['applied_pressure_rise_bar'] / 10.0, rel=1e-6)

    def test_rapid_closure_is_full_joukowsky(self):
        """t_close <= t_c -> tam Joukowsky (ani) tepe basıncı."""
        out_fast = self._steel_water(valve_closure_time_ms=None)
        t_c_ms = out_fast['critical_closure_time_ms']
        out_rapid = self._steel_water(valve_closure_time_ms=0.5 * t_c_ms)
        assert out_rapid['closure_regime'] == 'rapid'
        assert out_rapid['applied_pressure_rise_bar'] == pytest.approx(
            out_fast['applied_pressure_rise_bar'], rel=1e-9)

    def test_n2o_wave_speed_below_water(self):
        """N2O (düşük bulk modül) su hattından çok daha düşük dalga hızı."""
        out_w = self._steel_water()
        out_n = self._steel_water(fluid='n2o')
        assert out_n['wave_speed_m_s'] < out_w['wave_speed_m_s']

    def test_default_pipe_material_fallback(self):
        """Bilinmeyen malzeme -> ss_304 + uyarı + SAFE hükmü VERİLEMEZ.

        ÖH Faz B (defter P4B4-08). Eski hâli yalnız iki yankıydı (malzeme
        adı 'ss_304' mü, uyarı listesinde 'falling back' geçiyor mu) —
        düşüşün SONUCUNU hiç sınamıyordu, dolayısıyla düşüşün fail-closed
        ayağı (varsayılan malzemeyle SAFE sertifikası verilmemesi) sökülse
        bu bekçi yeşil kalırdı.

        ÖLÇÜLDÜ (27 Ağustos 2026, aynı hat/MAWP=500 bar): 'unobtanium'
        -> MARGINAL, açıkça 'ss_304' -> SAFE. İki koşumun bütün sayıları
        birebir aynıdır; tek fark malzemenin VARSAYILMIŞ olmasıdır.
        """
        # ÖH D18 / P4B4-09: bu vakada hüküm çalışma basıncının REFERANS
        # DÜZLEMİNE bağlıdır (mutlak okuma SAFE, gösterge okuma MARGINAL —
        # 1 atm'lik yorum farkı). Düzlem beyan edilmezse modül artık hüküm
        # vermeyi reddeder; bekçinin İDDİASI (varsayılan malzemeyle SAFE
        # sertifikası verilmez) değişmedi, yalnız vaka düzlemini söylüyor.
        # 'gauge' seçildi: eski kodun hüküm merdiveni de çalışma basıncını
        # fiilen gösterge olarak (hoop MAWP ile aynı düzlemde) kıyaslıyordu.
        out = self._steel_water(pipe_material='unobtanium',
                                working_pressure_reference='gauge')
        assert out['pipe']['material'] == DEFAULT_PIPE_MATERIAL
        # (1) Uyarı İKİ adı da anmalı: istenen ve yerine konan.
        dusus = [w for w in out['warnings'] if 'falling back' in w.lower()]
        assert dusus, out['warnings']
        assert any('unobtanium' in w and DEFAULT_PIPE_MATERIAL in w
                   for w in dusus), dusus
        # (2) Sınıflandırma gerçekten ss_304'ün KENDİ sayılarından gelmeli
        #     (ad yankısı değil, malzeme kaydının E'si ve akması).
        ss = get_material(DEFAULT_PIPE_MATERIAL)
        assert out['pipe']['elastic_modulus_GPa'] == pytest.approx(
            float(ss['elastic_modulus']) / 1e9, rel=1e-12)
        r_i = 0.5 * 0.5                      # _steel_water: ID 500 mm
        t_wall = 0.005                       # _steel_water: cidar 5 mm
        akma_bek = float(ss['yield_strength']) * t_wall / r_i / 1e5
        assert out['pipe']['hoop_yield_pressure_bar'] == pytest.approx(
            akma_bek, rel=1e-12)
        # (3) FAIL-CLOSED: varsayılan malzemeyle SAFE sertifikası verilemez.
        #
        # FİKSTÜR ÇEVRİLDİ (ÖH D15 / termo-ucus a2, P4B4-03). Eski hâli
        # ``flow_velocity_m_s=2.0`` + ``pipe_mawp_bar=500.0`` ile koşuyordu
        # ve BAŞKA bir kusuru sözleşme olarak kilitliyordu: o hatta tepe
        # basınç 50,4741 bar iken cidarın KENDİ hoop akma basıncı 43,000
        # bar; yani SAFE beklentisi, akmanın %17,4 ÜSTÜNDE bir tepe için
        # verilmiş SAFE hükmüne dayanıyordu (kullanıcı basınç sınıfı 500 bar
        # akmanın 11,6 katı olduğu için merdivenin ilk dalı her şeyi
        # yutuyordu). Bu tam olarak P4B4-03'ün kusurudur.
        #
        # Bu bekçinin GERÇEK konusu malzeme düşüşüdür: "malzeme
        # VARSAYILDIĞINDA SAFE verilemez". Konu korunur, ama SAFE'in
        # meşru olduğu bir çalışma noktasına taşınır: hız 1,0 m/s (tepe
        # 30,2371 bar) ve basınç sınıfı 40 bar (akmanın ALTINDA). Böylece
        # ss_304 -> SAFE, 'unobtanium' -> MARGINAL ayrımı yine yalnız
        # malzemenin varsayılmış olmasından gelir.
        varsayilan = self._steel_water(pipe_material='unobtanium',
                                       flow_velocity_m_s=1.0,
                                       pipe_mawp_bar=40.0,
                                       working_pressure_reference='gauge')
        acik = self._steel_water(pipe_material=DEFAULT_PIPE_MATERIAL,
                                 flow_velocity_m_s=1.0,
                                 pipe_mawp_bar=40.0,
                                 working_pressure_reference='gauge')
        assert acik['status'] == 'SAFE'
        assert varsayilan['status'] == 'MARGINAL', (
            'malzeme VARSAYILDIĞI hâlde SAFE hükmü verildi — düşüşün '
            'fail-closed ayağı sökülmüş')
        assert varsayilan['design_peak_pressure_bar'] == pytest.approx(
            acik['design_peak_pressure_bar'], rel=1e-12), (
            'iki koşumun fiziği aynı olmalıydı; hüküm farkı YALNIZ '
            'malzemenin varsayılmış olmasından gelmeli')
        assert any('ASSUMED material' in w for w in varsayilan['warnings'])

    # ÖH defter P4B4-08 (künye ayağı) — Z5S/PK4 onarımıyla YEŞİLE DÖNDÜ;
    # xfail(strict) borç imi söküldü. Kusurun kaydı: girdi künyesi
    # ``'pipe_material': resolved_material`` yazıyor, KULLANICININ GÖNDERDİĞİ
    # ad çıktıdan siliniyordu. Ölçüldü: pipe_material='unobtanium' çağrısında
    # inputs.pipe_material 'ss_304' dönüyordu; gönderilen ad yalnız serbest
    # metinli bir uyarı cümlesinde kalıyor, yapısal hiçbir alandan
    # okunamıyordu. Onarım: künye GÖNDERİLENİ taşıyor, yanına deponun
    # tescilli submitted/used/use_instead üçlüsü kondu
    # (warn.liquid.input_field_not_read, P16 §4).
    def test_varsayilan_dususu_girdi_kunyesinde_gorunur(self):
        """Gönderilen malzeme adı yapısal bir alandan okunabilmeli."""
        out = self._steel_water(pipe_material='unobtanium')
        kunye = out['inputs']
        assert kunye['pipe_material'] == 'unobtanium', (
            'girdi künyesi gönderilen adı değil, yerine konan adı '
            f"yayımlıyor: {kunye['pipe_material']!r}")

    def test_custom_fluid_override(self):
        """Özel sıvı: sayılar yankılanır VE kolon ayrılması kapısı çalışır.

        ÖH Faz B (defter P4B4-01, kritik). Eski hâli üç yankıdan ibaretti
        (K, rho ve rijit dalga hızı formülü) — bu yüzden override yolunda
        kolon ayrılması kapısının SESSİZCE kapandığını göremiyordu.

        Buradaki ayak MODÜLE DOĞRUDAN girer (adaptörsüz): kardeş bekçiler
        tests/test_c_kulvari_bilesenler.py::TestSuKocuSozlesmesi'de
        valve_feedline zinciri üzerinden aynı kusuru sayar; ikizlenmez.

        Kapının override yolunda ÇALIŞABİLDİĞİ bu testte kanıtlanır: buhar
        basıncı açıkça verildiğinde hüküm basıncı tablo yoluyla birebir
        aynıdır. Kapanma vakası ayrı bekçilerdedir (P4B4-01; borç imleri
        Z5S/PK4 onarımıyla söküldü).
        """
        out = WaterHammerAnalyzer().analyze(
            fluid='mystery', line_length_m=50.0, line_id_mm=100.0,
            wall_thickness_mm=3.0, working_pressure_bar=20.0,
            flow_velocity_m_s=3.0, pipe_material='ss_304',
            bulk_modulus_Pa=1.5e9, density_kg_m3=900.0)
        assert out['fluid_properties']['bulk_modulus_Pa'] == 1.5e9
        assert out['fluid_properties']['density_kg_m3'] == 900.0
        expect_rigid = math.sqrt(1.5e9 / 900.0)
        assert out['wave_speed_rigid_m_s'] == pytest.approx(expect_rigid, rel=1e-9)
        # Buhar basıncı BİLİNMİYOR: kapı değerlendirilememeli ve bu AÇIKÇA
        # söylenmeli (sessiz 'ayrılma yok' hükmü yasak).
        assert out['column_separation'] is None
        assert out['vapor_pressure_source'] == 'unavailable'
        assert any('vapor pressure is unknown' in w for w in out['warnings'])

        # Buhar basıncı VERİLİNCE kapı override yolunda da çalışıyor:
        # hüküm basıncı tablo yolunun sayısıyla birebir aynı.
        su = FLUID_PROPERTIES['water']
        ortak = dict(fluid='water', line_length_m=100.0, line_id_mm=100.0,
                     wall_thickness_mm=6.0, working_pressure_bar=10.0,
                     flow_velocity_m_s=2.0, pipe_material='steel_4130',
                     pipe_mawp_bar=500.0)
        tablo = WaterHammerAnalyzer().analyze(**ortak)
        ozel = WaterHammerAnalyzer().analyze(
            **ortak, bulk_modulus_Pa=su['bulk_modulus_Pa'],
            density_kg_m3=su['density_kg_m3'],
            vapor_pressure_Pa=su['vapor_pressure_Pa'])
        assert tablo['column_separation'] is True
        assert ozel['column_separation'] is True
        assert ozel['vapor_pressure_source'] == 'user_supplied'
        assert ozel['design_peak_pressure_bar'] == pytest.approx(
            tablo['design_peak_pressure_bar'], rel=1e-12)
        assert ozel['status'] == tablo['status']
        # Hüküm basıncı Joukowsky tepesinin KENDİSİ değil, birleşme tepesi.
        assert ozel['design_peak_pressure_bar'] == pytest.approx(
            ozel['working_pressure_bar'] + COLUMN_SEPARATION_PEAK_FACTOR
            * ozel['applied_pressure_rise_bar'], rel=1e-12)

    # ÖH defter P4B4-01 (KRİTİK) — Z5S/PK4 onarımıyla YEŞİLE DÖNDÜ;
    # xfail(strict) borç imi söküldü. Kusurun kaydı: bulk_modulus_Pa ve
    # density_kg_m3 BİRLİKTE verilince akışkan kaydı "Custom fluid" olarak
    # sıfırdan kuruluyor, tablonun buhar basıncı düşüyordu
    # (vapor_pressure_Pa=None) — üstelik sayılar tablonun KENDİ sayıları olsa
    # bile. Ölçüldü (su, 100 m x 100 mm x 6 mm steel_4130, 10 bar,
    # MAWP 500 bar): 2 m/s'de kolon ayrılması True -> None ve hüküm basıncı
    # 64,38 -> 37,19 bar; 20 m/s'de hüküm UNSAFE -> SAFE (hüküm basıncı
    # 553,81 -> 281,90 bar, akma 552,00 bar). Onarım: akışkan kaydı çağrı
    # biçimine değil akışkanın TABLODA olup olmamasına bağlandı; override
    # yalnız ilgili ALANI eziyor, tablonun buhar basıncı yerinde kalıyor.
    @pytest.mark.parametrize('hiz,tablo_hukmu', [(2.0, 'SAFE'),
                                                 (20.0, 'UNSAFE')])
    def test_tablo_sayilari_override_verilince_kapi_kapanmiyor(self, hiz,
                                                               tablo_hukmu):
        """Tablonun KENDİ sayısı override olarak verilince hüküm değişemez."""
        su = FLUID_PROPERTIES['water']
        ortak = dict(pipe_mawp_bar=500.0, flow_velocity_m_s=hiz)
        tablo = self._steel_water(line_id_mm=100.0, wall_thickness_mm=6.0,
                                  **ortak)
        ovr = self._steel_water(line_id_mm=100.0, wall_thickness_mm=6.0,
                                bulk_modulus_Pa=su['bulk_modulus_Pa'],
                                density_kg_m3=su['density_kg_m3'], **ortak)
        # Ön koşul: iki koşumun Joukowsky fiziği birebir aynı (sayılar aynı).
        assert ovr['peak_pressure_bar'] == pytest.approx(
            tablo['peak_pressure_bar'], rel=1e-12)
        assert tablo['status'] == tablo_hukmu
        assert ovr['column_separation'] == tablo['column_separation']
        assert ovr['design_peak_pressure_bar'] == pytest.approx(
            tablo['design_peak_pressure_bar'], rel=1e-12)
        assert ovr['status'] == tablo['status'], (
            'aynı fizik, iki çağrı biçimi, iki hüküm — hüküm fizikten değil '
            'çağrı biçiminden geliyor')

    # ÖH defter P4B4-01 (KRİTİK), fail-closed ayağı — Z5S/PK4 onarımıyla
    # YEŞİLE DÖNDÜ; xfail(strict) borç imi söküldü. Kusurun kaydı: buhar
    # basıncı bilinmediğinde ürünün KENDİ uyarısı "the Joukowsky peak below
    # is NOT guaranteed to be the upper bound" derken hüküm yine de SAFE
    # yayımlanıyordu (ölçüldü: özel akışkan, 20 bar hat, hüküm SAFE). Onarım:
    # kolon ayrılması kapısı değerlendirilemediğinde (column_separation None)
    # SAFE hükmü MARGINAL'e düşürülüyor — dosyanın malzeme ayağında ZATEN var
    # olan fail-closed desenin ikizi kuruldu.
    def test_buhar_basinci_bilinmeyince_SAFE_hukmu_verilmez(self):
        """Üst sınır olmadığı BEYAN EDİLEN bir tepeden SAFE çıkarılamaz."""
        out = WaterHammerAnalyzer().analyze(
            fluid='mystery', line_length_m=50.0, line_id_mm=100.0,
            wall_thickness_mm=3.0, working_pressure_bar=20.0,
            flow_velocity_m_s=3.0, pipe_material='ss_304',
            bulk_modulus_Pa=1.5e9, density_kg_m3=900.0,
            pipe_mawp_bar=500.0)
        assert out['column_separation'] is None      # kapı değerlendirilemedi
        assert any('NOT guaranteed to be the upper bound' in w
                   for w in out['warnings'])
        assert out['status'] != 'SAFE', (
            'kolon ayrılması kapısı değerlendirilemediği hâlde SAFE '
            'sertifikası verildi (malzeme ayağındaki fail-closed düşüşün '
            'ikizi burada yok)')

    def test_model_note_and_assumptions(self):
        out = self._steel_water()
        assert out['model_note']
        assert isinstance(out['assumptions'], list) and len(out['assumptions']) >= 4
        assert 'Joukowsky' in out['model_note']


# ===========================================================================
# Emniyet durumu + öneri
# ===========================================================================
class TestSafetyAndRecommendation:
    def _run(self, **kw):
        params = dict(
            fluid='water', line_length_m=100.0, line_id_mm=100.0,
            wall_thickness_mm=6.0, working_pressure_bar=10.0,
            flow_velocity_m_s=2.0, pipe_material='steel_4130',
        )
        params.update(kw)
        return WaterHammerAnalyzer().analyze(**params)

    def test_safe_when_peak_within_mawp(self):
        """Yüksek basınç sınıflı boru -> tepe MAWP altında -> SAFE."""
        out = self._run(pipe_mawp_bar=500.0)
        assert out['status'] == 'SAFE'
        assert out['peak_pressure_bar'] < out['pipe']['mawp_bar']

    def test_unsafe_when_peak_exceeds_yield(self):
        """Çok düşük MAWP + ince cidar -> tepe akmayı aşar -> UNSAFE."""
        out = self._run(fluid='water', wall_thickness_mm=0.3,
                        pipe_mawp_bar=5.0, working_pressure_bar=4.0,
                        flow_velocity_m_s=5.0)
        assert out['status'] == 'UNSAFE'
        assert out['peak_pressure_bar'] > out['pipe']['hoop_yield_pressure_bar']

    def test_marginal_band(self):
        """MAWP < tepe <= akma -> MARGINAL."""
        base = self._run(pipe_mawp_bar=500.0)
        peak = base['peak_pressure_bar']
        yield_p = base['pipe']['hoop_yield_pressure_bar']
        # MAWP'yi tepe ile akma arasına yerleştir
        mawp = 0.5 * (peak + min(yield_p, peak * 1.5))
        mawp = max(min(mawp, peak - 0.1), 0.1)
        # Faz 5 / H5-6 — FAIL-OPEN ATLAMA kaldırıldı: eskiden
        # ``pytest.skip("geometri bu vakada MARGINAL bandı üretmiyor")`` idi.
        # Testin kendi kurgusu bozulduğunda (tepe basınç akma basıncını aşarsa
        # ya da MAWP tepenin altına yerleştirilemezse) MARGINAL bandı HİÇ
        # sınanmadan yeşil kalıyordu. Ölçüldü (3 Ağustos 2026): 252 testlik
        # koşuda bu atlama tetiklenmiyor — kurgu geçerli.
        assert mawp < peak and peak <= yield_p, (
            f"MARGINAL bandı kurulamadı: tepe={peak:.2f} bar, "
            f"akma={yield_p:.2f} bar, denenen MAWP={mawp:.2f} bar — "
            "model değiştiyse bu testin kurgusu güncellenmeli")
        out = self._run(pipe_mawp_bar=mawp)
        assert out['status'] == 'MARGINAL'

    def test_recommendation_none_when_instant_safe(self):
        """"Kısıt gerekmez" cevabı HÜKÜMLE tutarlı olmak zorunda.

        ÖH Faz B (defter P4B4-02). Eski hâli yalnız "öneri None ve metinde
        'no closure-time restriction' geçiyor" diyordu; önerinin HÜKÜMLE
        çelişip çelişmediğini sormuyordu. Öneri, tepe basıncını MAWP içinde
        tutmakla ilgilidir; dolayısıyla "kısıt gerekmez" cevabı ancak
        HÜKÜM BASINCI (kolon ayrılması dahil, fail-closed) MAWP içindeyken
        doğrudur. Bu vakada (MAWP 500 bar) öyledir — bağlaşım burada kurulur,
        çeliştiği vaka aşağıdaki P4B4-02 bekçisidir (borç imi Z5S/PK4
        onarımıyla söküldü).
        """
        out = self._run(pipe_mawp_bar=500.0)
        assert out['recommended_closure_time_ms'] is None
        assert 'no closure-time restriction' in out['recommendation'].lower()
        # Bağlaşım: kısıt gerekmiyorsa hüküm basıncı da MAWP içinde olmalı.
        assert out['design_peak_pressure_bar'] <= out['pipe']['mawp_bar']
        assert out['status'] == 'SAFE'
        # ...ve bu vakada kapı gerçekten değerlendirilmiş durumdadır
        # (kolon ayrılması VAR, hüküm basıncı Joukowsky tepesinin üstünde).
        assert out['column_separation'] is True
        assert out['design_peak_pressure_bar'] > out['peak_pressure_bar']

    # ÖH defter P4B4-02 — Z5S/PK4 onarımıyla YEŞİLE DÖNDÜ; xfail(strict)
    # borç imi söküldü. Kusurun kaydı: _closure_recommendation yalnız
    # Joukowsky artışını MAWP marjıyla karşılaştırıyor, kolon ayrılması
    # birleşme tepesini (COLUMN_SEPARATION_PEAK_FACTOR ile hesaplanan hüküm
    # basıncı) HİÇ görmüyordu. Ölçüldü (N2O, 55 bar hat, 2 m/s, MAWP 70 bar,
    # 100 m x 100 mm x 6 mm steel_4130): aşağı salınım 47,34 bar, N2O'nun
    # 50,54 bar buhar basıncının ALTINDA -> kolon ayrılması True, hüküm
    # basıncı 70,33 bar > MAWP 70 bar -> MARGINAL; buna rağmen öneri "no
    # closure-time restriction is required" ve önerilen süre None idi.
    # Onarım: öneri artık HÜKÜM basıncını görüyor; aynı vakada önerilen süre
    # None -> 418,7 ms ve metin kısıtın sebebini adıyla yazıyor.
    def test_oneri_yoklugu_kolon_ayrilmasini_gormek_zorunda(self):
        """Hüküm SAFE değilse "kısıt gerekmez" cevabı verilemez."""
        # ÖH D18 / P4B4-09: aynı gerekçe (bkz. yukarıdaki not) — bu vaka
        # da 1 atm'lik yorum penceresinin içinde; düzlem artık beyanlı.
    # ÖH D31 · P4B4-07 / OH-D27-08 — VAKA YENİDEN AYARLANDI (İDDİA AYNI).
    # n2o kaydı D31'de kanona taşındı (yoğunluk 785,0 -> 745,0 kg/m³,
    # N2O_LIQUID_DENSITY_SAT_25C; buhar basıncı 293,15 K -> 298,15 K).
    # Joukowsky artışı dP = rho*a*dv = sqrt(K*rho)*dv olduğundan daha
    # düşük yoğunluk daha düşük tepe verir: ÖLÇÜLDÜ, hüküm basıncı
    # 70,33 bar -> 69,93 bar'a indi ve 70 bar MAWP artık AŞILMIYOR, yani
    # vaka kendi rejiminden (MARGINAL) çıkıp SAFE'e düştü. Bekçinin
    # İDDİASI değişmedi ('hüküm MAWP'yi aşıyorsa kısıt gerekmez denemez');
    # yalnız vakayı o rejimde tutmak için MAWP 70 -> 68 bar'a alındı
    # (peak 62,47 < 68 < design 69,93). Tolerans/eşik GEVŞETİLMEDİ.
        out = self._run(fluid='n2o', working_pressure_bar=55.0,
                        flow_velocity_m_s=2.0, pipe_mawp_bar=68.0,
                        working_pressure_reference='gauge')
        # Ön koşullar ölçümle sabit (bunlar kırmızıysa vaka kaymıştır).
        assert out['column_separation'] is True
        assert out['status'] == 'MARGINAL'
        assert out['design_peak_pressure_bar'] > out['pipe']['mawp_bar']
        assert out['peak_pressure_bar'] < out['pipe']['mawp_bar']
        # Asıl iddia: öneri hükümle çelişemez.
        assert not (out['recommended_closure_time_ms'] is None
                    and 'no closure-time restriction'
                    in out['recommendation'].lower()), (
            f"hüküm {out['status']} iken öneri kısıt gerekmediğini söylüyor: "
            f"{out['recommendation']}")

    def test_recommendation_slower_than_x_ms(self):
        """Tepe MAWP'yi aşıyorsa 'valve closure slower than X ms' önerilir."""
        out = self._run(pipe_mawp_bar=15.0)
        assert out['recommended_closure_time_ms'] is not None
        assert 'valve closure slower than' in out['recommendation'].lower()
        # Önerilen süre kritik süreden büyük olmalı
        assert out['recommended_closure_time_ms'] >= out['critical_closure_time_ms']

    def test_recommended_time_brings_peak_to_mawp(self):
        """Önerilen kapanma süresi uygulanınca tepe ~ MAWP'ye iner."""
        out = self._run(pipe_mawp_bar=15.0)
        t_rec = out['recommended_closure_time_ms']
        # Önerilen süre kritik süreden büyükse yavaş rejim geçerlidir.
        # Faz 5 / H5-6 — FAIL-OPEN ATLAMA kaldırıldı: eskiden
        # ``pytest.skip("öneri kritik süreyle sınırlı; ani zaten güvenli
        # değil")`` idi. Bu vaka (MAWP=15 bar) bilerek tepe > MAWP olacak
        # şekilde seçilmiştir; önerinin kritik süreyle sınırlı kalması
        # önerinin ANLAMSIZ olduğu anlamına gelir ve görünmesi gerekir.
        # Ölçüldü (3 Ağustos 2026): atlama tetiklenmiyor.
        assert t_rec > out['critical_closure_time_ms'] * (1 + 1e-9), (
            f"önerilen kapanma süresi ({t_rec} ms) kritik süreye "
            f"({out['critical_closure_time_ms']} ms) sıkışmış — öneri tepeyi "
            "MAWP'ye indiremez")
        out2 = self._run(pipe_mawp_bar=15.0, valve_closure_time_ms=t_rec)
        assert out2['peak_pressure_bar'] == pytest.approx(
            out2['pipe']['mawp_bar'], rel=1e-3)
        # ÖH Faz B (P4B4-02): öneri "tepeyi MAWP içinde tutar" diyor —
        # tepe, hükmün dayandığı basınçtır. Bu vakada (MAWP 15 bar) önerilen
        # süre uygulanınca aşağı salınım 5,00 bar > 0,023 bar buhar basıncı
        # olduğu için kolon ayrılması OLUŞMAZ ve iki tepe çakışır; öneri bu
        # vakada gerçekten yeterlidir. Yetmediği vaka aşağıdaki xfail imli
        # bekçidedir (MAWP 30 bar).
        assert out2['column_separation'] is False
        assert out2['design_peak_pressure_bar'] == pytest.approx(
            out2['peak_pressure_bar'], rel=1e-12)
        assert out2['design_peak_pressure_bar'] <= (
            out2['pipe']['mawp_bar'] * (1 + 1e-3))
        assert out2['status'] == 'SAFE'

    # DURUM NOTU (Z5S/PK4) — İM YERİNDE BIRAKILDI, ürün ONARILDI.
    # P4B4-02 onarımı bu vakayı da düzeltti: MAWP 30 bar için önerilen süre
    # 199,6 -> 399,2 ms ve uygulanınca HÜKÜM basıncı 50,000 -> 30,000 bara,
    # yani tam MAWP'ye iniyor. Asıl iddia (aşağıdaki design_peak_pressure_bar
    # <= MAWP satırı) artık GEÇİYOR. Kıran şey testin ÖN KOŞULUDUR
    # (out2['peak_pressure_bar'] ≈ MAWP satırı): ayrılma rejiminde hüküm
    # basıncı p_work + F*dP olduğundan Joukowsky tepesi tam MAWP iken hüküm
    # zorunlu olarak 2*MAWP - p_work olur (10 bar hat / MAWP 30 bar: tepe 30
    # ise hüküm 50). İki iddia CEBİRSEL OLARAK bağdaşmıyor. Ölçüldü
    # (--runxfail): yalnız o ön koşul kırılıyor (20,000 != 30,0 ± 0,03),
    # testin gerisi geçiyor. Ön koşulun güncellenip güncellenmeyeceği
    # DEFTER KARARINA bırakıldı; im o karara kadar borç olarak durur.
    @pytest.mark.xfail(strict=True, reason=(
        'ÖH defter P4B4-02 — öneri kolon ayrılmasını görmediği için '
        'ÜRETTİĞİ süre de yetmiyor: önerilen süre uygulandığında Joukowsky '
        'tepesi tam MAWP\'ye iniyor, ama aşağı salınım buhar basıncının '
        'altına düştüğü için birleşme tepesi MAWP\'nin iki katına çıkıyor. '
        'ÖLÇÜLDÜ (su, 100 m x 100 mm x 6 mm steel_4130, 10 bar, 2 m/s, '
        'MAWP 30 bar): önerilen süre 199,6 ms; uygulanınca tepe 30,000 bar '
        '(öneri metninin iddiası) ama hüküm basıncı 50,000 bar ve hüküm '
        'MARGINAL. Öneri metni "keep the peak pressure within the pipe '
        'MAWP" diyor; ürünün kendi hüküm basıncı bunu yalanlıyor'))
    def test_onerilen_sure_hukum_basincini_da_mawpye_indirmeli(self):
        """Önerilen süre uygulanınca HÜKÜM basıncı da MAWP içinde kalmalı."""
        out = self._run(pipe_mawp_bar=30.0)
        t_rec = out['recommended_closure_time_ms']
        assert t_rec is not None
        assert 'within the pipe mawp' in out['recommendation'].lower()
        out2 = self._run(pipe_mawp_bar=30.0, valve_closure_time_ms=t_rec)
        # Ön koşul: Joukowsky tepesi gerçekten MAWP'ye iniyor.
        assert out2['peak_pressure_bar'] == pytest.approx(
            out2['pipe']['mawp_bar'], rel=1e-3)
        assert out2['column_separation'] is True
        # Asıl iddia: hüküm basıncı da MAWP içinde olmalı.
        assert out2['design_peak_pressure_bar'] <= (
            out2['pipe']['mawp_bar'] * (1 + 1e-3)), (
            f"önerilen {t_rec:.1f} ms uygulandı; Joukowsky tepesi "
            f"{out2['peak_pressure_bar']:.3f} bar ile MAWP'de ama hüküm "
            f"basıncı {out2['design_peak_pressure_bar']:.3f} bar "
            f"(hüküm: {out2['status']})")

    def test_hoop_pressures_ordered(self):
        """Akma basıncı < kopma basıncı (sigma_y < sigma_u); MAWP <= akma."""
        out = self._run()
        assert (out['pipe']['hoop_yield_pressure_bar']
                < out['pipe']['hoop_burst_pressure_bar'])
        assert out['pipe']['mawp_bar'] <= out['pipe']['hoop_yield_pressure_bar'] + 1e-9


# ===========================================================================
# Geçersiz girdiler
# ===========================================================================
class TestInvalidInputs:
    def _ok(self):
        return dict(
            fluid='water', line_length_m=100.0, line_id_mm=100.0,
            wall_thickness_mm=5.0, working_pressure_bar=10.0,
            flow_velocity_m_s=2.0)

    def test_unknown_fluid(self):
        p = self._ok(); p['fluid'] = 'plasma'
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_missing_flow_definition(self):
        p = self._ok(); p.pop('flow_velocity_m_s')
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_length(self):
        p = self._ok(); p['line_length_m'] = 0.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_diameter(self):
        p = self._ok(); p['line_id_mm'] = -1.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_wall(self):
        p = self._ok(); p['wall_thickness_mm'] = 0.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_working_pressure(self):
        p = self._ok(); p['working_pressure_bar'] = -5.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_closure_time(self):
        p = self._ok(); p['valve_closure_time_ms'] = 0.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nonpositive_mdot(self):
        p = self._ok(); p.pop('flow_velocity_m_s'); p['mdot_kg_s'] = -1.0
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)

    def test_nan_rejected(self):
        p = self._ok(); p['flow_velocity_m_s'] = float('nan')
        with pytest.raises(ValueError):
            WaterHammerAnalyzer().analyze(**p)
