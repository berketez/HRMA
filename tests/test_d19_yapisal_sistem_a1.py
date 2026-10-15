"""ÖH Dalga-19 / yapisal-sistem aşama-1 bekçileri.

Kanıt dizini: ``docs/scofield/raw/OH/D19/yapisal-sistem/a1/``.

Kapsam:
  * P5B3-07 — ``size_turbine`` girdi kapısı (zarf hızı, verim bandı,
    sonluluk); D18'de kardeş dal çakışması yüzünden açılamamıştı.
  * D18 devir denetimi — D18'de onarılan yedi kalemin onarımının bu
    tabanda (60cd341) HÂLÂ durduğunu ölçen ince bekçiler. Bu sınıflar
    D18 bekçilerinin yerine geçmez; onarımın ağaçtan düşmediğini
    doğrulayan ikinci mandaldır.
"""
import math

import pytest

from hrma.analysis.turbopump_sizing import (
    TURBINE_EFFICIENCY_VALID, TURBINE_PITCH_SPEED_LIMIT_M_S, size_turbine)


# ===========================================================================
# P5B3-07 — size_turbine girdi kapısı
# ===========================================================================
TEMEL = dict(shaft_speed_rpm=30000.0, power_W=250000.0,
             mass_flow_kg_s=0.9, efficiency=0.65)


class TestP5B307TurbinGirdiKapisi:
    """Zarf hızı / verim / sonluluk kapıları — ÖLÇÜLDÜ: once_p5b307.json."""

    @pytest.mark.parametrize('u_pompa', [
        -50.0,                 # ÖNCE: KABUL, zarf -50,0 yayımlanıyordu
        0.0,                   # ÖNCE: ham ZeroDivisionError
        float('nan'),          # ÖNCE: sessizce yutulup zarf 450 oluyordu
        float('inf'),          # ÖNCE: sessizce yutuluyordu
        float('-inf'),         # ÖNCE: zarf -inf + çap 0,2765 basılıyordu
    ])
    def test_fiziksel_olmayan_zarf_adiyla_reddedilir(self, u_pompa):
        with pytest.raises(ValueError) as hata:
            size_turbine(pump_tip_speed_m_s=u_pompa, **TEMEL)
        assert 'pump_tip_speed_m_s' in str(hata.value)

    def test_negatif_zarf_artik_yayimlanamaz(self):
        """Kusurun ürün yüzündeki hâli: NEGATİF çevre hızı bir 'nicelik'
        gibi basılıyordu. Kapı bunun yayımlanma yolunu kapatır."""
        with pytest.raises(ValueError):
            size_turbine(pump_tip_speed_m_s=-50.0, **TEMEL)

    @pytest.mark.parametrize('eta', [1e-9, 1e-4, 0.01, float('nan')])
    def test_verim_bandi_disi_adiyla_reddedilir(self, eta):
        kw = dict(TEMEL)
        kw['efficiency'] = eta
        with pytest.raises(ValueError) as hata:
            size_turbine(pump_tip_speed_m_s=300.0, **kw)
        metin = str(hata.value)
        assert 'turbine efficiency' in metin
        assert 'validity range' in metin

    def test_verim_bandinin_alt_ucu_hala_gecer(self):
        """Kapı bir KALİBRASYON değil geçerlilik tabanıdır: bandın tam
        alt ucu (0,10) ve uygulama bandı (0,35) geçmelidir."""
        for eta in (TURBINE_EFFICIENCY_VALID[0], 0.35,
                    TURBINE_EFFICIENCY_VALID[1]):
            kw = dict(TEMEL)
            kw['efficiency'] = eta
            r = size_turbine(pump_tip_speed_m_s=300.0, **kw)
            assert math.isfinite(r['spouting_velocity_m_s'])

    def test_fiskirma_hizi_artik_sinirli(self):
        """C0 = sqrt(2*P/(mdot*eta)); eta tabanı C0'a ÜST SINIR verir."""
        kw = dict(TEMEL)
        kw['efficiency'] = TURBINE_EFFICIENCY_VALID[0]
        tavan = size_turbine(pump_tip_speed_m_s=300.0,
                             **kw)['spouting_velocity_m_s']
        # ÖLÇÜLDÜ (once_p5b307.json): eta=1e-9'da C0 = 23 570 226 m/s idi.
        assert tavan < 1.0e4
        for eta in (0.10, 0.35, 0.65, 1.0):
            kw2 = dict(TEMEL)
            kw2['efficiency'] = eta
            c0 = size_turbine(pump_tip_speed_m_s=300.0,
                              **kw2)['spouting_velocity_m_s']
            assert c0 <= tavan + 1e-9

    @pytest.mark.parametrize('ad,kw', [
        ('power_W', dict(power_W=float('inf'))),
        ('mass_flow_kg_s', dict(mass_flow_kg_s=float('inf'))),
        ('pitch_speed_limit_m_s', dict(pitch_speed_limit_m_s=float('inf'))),
        ('pitch_speed_limit_m_s', dict(pitch_speed_limit_m_s=float('nan'))),
    ])
    def test_sonlu_olmayan_girdi_adiyla_reddedilir(self, ad, kw):
        tam = dict(TEMEL)
        tam.update(kw)
        tam.setdefault('pump_tip_speed_m_s', 300.0)
        with pytest.raises(ValueError) as hata:
            size_turbine(**tam)
        assert ad in str(hata.value)

    def test_dogrudan_verilen_ozis_sonlu_olmali(self):
        with pytest.raises(ValueError) as hata:
            size_turbine(shaft_speed_rpm=30000.0,
                         ideal_specific_work_J_kg=float('inf'),
                         pump_tip_speed_m_s=300.0)
        assert 'ideal_specific_work_J_kg' in str(hata.value)

    @pytest.mark.parametrize('ad,kw,beklenen', [
        ('D1_zarfsiz', {},
         (924.5003270420485, 0.276530483429443, 450.0,
          'structural_practice_limit', 1)),
        ('D2_zarf_300', dict(pump_tip_speed_m_s=300.0),
         (924.5003270420485, 0.15965494904712624, 300.0,
          'pump_tip_speed_envelope', 3)),
    ])
    def test_saglikli_govde_bit_ayni(self, ad, kw, beklenen):
        """Kapı sağlıklı gövdeyi DEĞİŞTİRMEZ (once/sonra_p5b307.json)."""
        r = size_turbine(**dict(TEMEL, **kw))
        c0, d, zarf, kaynak, n = beklenen
        assert r['spouting_velocity_m_s'] == c0
        assert r['mean_diameter_m'] == d
        assert r['pitch_speed_bound_m_s'] == zarf
        assert r['pitch_speed_bound_source'] == kaynak
        assert r['stage_count'] == n

    def test_varsayilan_yapisal_sinir_banda_dokunmaz(self):
        assert TURBINE_PITCH_SPEED_LIMIT_M_S > 0
        assert math.isfinite(TURBINE_PITCH_SPEED_LIMIT_M_S)
        assert 0.0 < TURBINE_EFFICIENCY_VALID[0] < TURBINE_EFFICIENCY_VALID[1]
        assert TURBINE_EFFICIENCY_VALID[1] == 1.0

    def test_motor_varsayilani_bandin_icinde(self):
        """TEK KAYNAK denetimi: motorun türbin verimi varsayılanı bandın
        içinde kalmalı, yoksa ürün yüzü kendi varsayılanıyla reddedilir."""
        from hrma.engines.liquid_rocket_engine import (
            TURBINE_EFFICIENCY_DEFAULT)
        lo, hi = TURBINE_EFFICIENCY_VALID
        assert lo <= TURBINE_EFFICIENCY_DEFAULT <= hi


# ===========================================================================
# P5B3-08 (D18 devri, kalan ayak) — rejim hükmü etiketten KAZANILIYOR
# ===========================================================================
class TestP5B308KritikBasincEtiketten:
    """D18 hükmü geri çekmişti; D19 onu kazanıyor.

    ÖLÇÜLDÜ (once/sonra_p5b308.json): lox ve n2o hatlarında
    ``regime_verified`` False -> True, ``choked_pressure_drop_Pa`` None ->
    1 089 324,93 / 6 790,13 Pa. Cv üç hatta da BİT-AYNI (bu çalışma
    noktalarında akış boğulmuyor); değişen şey hükmün kazanılmış olması.
    """

    _HAT = dict(mass_flow_kg_s=2.7, line_id_m=0.03, line_length_m=2.0,
                inlet_pressure_Pa=37e5, valve_pressure_drop_Pa=2000.0)

    # ÖH D20 / P5B3-15 — N2O ÇALIŞMA NOKTASI DÜZELTİLDİ (bekçi çevrildi).
    #
    # D19'da n2o kolu ``vapor_pressure_Pa = 5,054e6 Pa`` (50,54 bar, oda
    # sıcaklığındaki doygunluk basıncı) ile 37 bar giriş basıncı
    # kullanıyordu. Bu çalışma noktası FİZİKSEL DEĞİLDİR: girişte basınç
    # buhar basıncının 13,54 bar ALTINDA olduğu için N2O sıvı değil,
    # kaynamış hâldedir; modülün kendi modeli (kararlı, sıkıştırılamaz,
    # TEK FAZLI akış) uygulanamaz. D20'de ``line_pressure_drop`` bu
    # durumu ADIYLA reddetmeye başladı (item P5B3-15: "p_v > p_giriş
    # reddedilmiyor").
    #
    # Testin ASIL konusu (kritik basıncın etiketten kazanılması) korunur;
    # yalnız kendinden-basınçlı bir N2O tankının gerçek besleme basıncı
    # verilir. ÖLÇÜLDÜ: ``cv_required`` giriş basıncından BAĞIMSIZDIR —
    # 37/60/70 bar'da da 89,7281690677676; yani D19'un "sayı değişmedi"
    # hükmü aynen ayakta kalır. Değişen tek sayı hükmün kendisinden
    # üretilmeyen ``choked_pressure_drop_Pa``dır (6 790,125245 -> 702
    # 540,125245 Pa) ve testler onu yalnız ``is not None`` diye ölçer.
    _N2O_GIRIS_PA = 60e5

    def _kos(self, etiket, rho, mu, pv, **ek):
        from hrma.analysis.valve_feedline import analyze_valve_feedline
        hat = dict(self._HAT)
        if pv >= hat['inlet_pressure_Pa']:
            hat['inlet_pressure_Pa'] = self._N2O_GIRIS_PA
        return analyze_valve_feedline(
            density_kg_m3=rho, viscosity_Pa_s=mu, fluid=etiket,
            vapor_pressure_Pa=pv, **dict(hat, **ek))

    @pytest.mark.parametrize('etiket,rho,mu,pv,pc', [
        ('lox', 1141.7, 1.9e-4, 101325.0, 5.043e6),
        ('n2o', 785.0, 1.0e-4, 5.054e6, 7.245e6),
    ])
    def test_etiket_kritik_basinci_kazandirir(self, etiket, rho, mu, pv, pc):
        r = self._kos(etiket, rho, mu, pv)
        pm = r['pipe_materials']
        assert pm['critical_pressure_provenance'] == 'fluid_table:%s' % etiket
        assert pm['critical_pressure_Pa'] == pytest.approx(pc, rel=1e-12)
        assert r['valve']['capacity']['regime_verified'] is True
        assert r['valve']['cavitation']['choked_pressure_drop_Pa'] is not None

    def test_rp1_uydurulmaz_hukum_geri_cekilir(self):
        """RP-1 bir kerosen kesitidir; sözde-kritik değer UYDURULMAZ."""
        r = self._kos('rp1', 815.0, 1.9e-3, 700.0)
        pm = r['pipe_materials']
        assert pm['critical_pressure_provenance'] is None
        assert pm['critical_pressure_Pa'] is None
        assert r['valve']['capacity']['regime_verified'] is False

    def test_etiketsiz_hat_hukmu_kazanamaz(self):
        r = self._kos(None, 1000.0, 1.0e-3, 2339.0)
        assert r['pipe_materials']['critical_pressure_provenance'] is None
        assert r['valve']['capacity']['regime_verified'] is False

    def test_cagiranin_verdigi_deger_ezilmez(self):
        r = self._kos('lox', 1141.7, 1.9e-4, 101325.0,
                      critical_pressure_Pa=4.0e6)
        pm = r['pipe_materials']
        assert pm['critical_pressure_provenance'] == 'caller_supplied'
        assert pm['critical_pressure_Pa'] == pytest.approx(4.0e6, rel=1e-12)

    def test_cv_bu_calisma_noktalarinda_bit_ayni(self):
        """Hüküm kazanıldı ama SAYI değişmedi (akış boğulmuyor)."""
        beklenen = {'lox': 74.40251802926159, 'rp1': 88.06124677452507,
                    'n2o': 89.7281690677676}
        for etiket, rho, mu, pv in (('lox', 1141.7, 1.9e-4, 101325.0),
                                    ('rp1', 815.0, 1.9e-3, 700.0),
                                    ('n2o', 785.0, 1.0e-4, 5.054e6)):
            r = self._kos(etiket, rho, mu, pv)
            assert r['valve']['capacity']['cv_required'] == beklenen[etiket]

    def test_kritik_basinclar_depo_veritabaniyla_ayni(self):
        """TEK KAYNAK mandalı: aynı akışkanın kritik basıncı iki tabloda
        iki sayı olamaz."""
        from hrma.analysis.water_hammer import FLUID_PROPERTIES
        from hrma.data.propellant_database import PropellantDatabase
        depo = PropellantDatabase().database
        sayilan = 0
        for anahtar in ('lox', 'n2o'):
            pc = FLUID_PROPERTIES[anahtar].get('critical_pressure_Pa')
            db_pc = (depo.get(anahtar) or {}).get('critical_pressure')
            assert pc is not None and db_pc is not None, anahtar
            # depo MPa, tablo Pa
            assert pc == pytest.approx(float(db_pc) * 1e6, rel=1e-9), anahtar
            sayilan += 1
        assert sayilan == 2

    def test_rp1_tabloda_bilerek_yok(self):
        from hrma.analysis.water_hammer import FLUID_PROPERTIES
        assert 'critical_pressure_Pa' not in FLUID_PROPERTIES['rp1']


# ===========================================================================
# D18 DEVİR DENETİMİ — D18 onarımları bu tabanda hâlâ duruyor mu?
# ===========================================================================
class TestD18DevirOnarimlariDuruyor:
    """Görev listesi bu yedi kalemi 'acik' diye devretti; defter kaydı
    'onarildi'/'kapali' diyor. Ölçüm: onarımlar ağaçta duruyor."""

    def test_p5b309_kavitasyon_taramasi_kritik_basinca_bagli_degil(self):
        from hrma.analysis.valve_feedline import size_valve
        r = size_valve(mass_flow_kg_s=40.0, density_kg_m3=1141.0,
                       inlet_pressure_Pa=60e5, pressure_drop_Pa=30e5,
                       vapor_pressure_Pa=1.01e5)
        assert r['cavitation'] is not None
        assert r['cavitation']['sigma'] is not None

    def test_p5b308_rejim_hukmu_kazanilmadan_beyan_edilmez(self):
        from hrma.analysis.valve_feedline import size_valve
        r = size_valve(mass_flow_kg_s=40.0, density_kg_m3=1141.0,
                       inlet_pressure_Pa=60e5, pressure_drop_Pa=30e5,
                       vapor_pressure_Pa=1.01e5)
        assert r['capacity']['regime_verified'] is False
        r2 = size_valve(mass_flow_kg_s=40.0, density_kg_m3=1141.0,
                        inlet_pressure_Pa=60e5, pressure_drop_Pa=30e5,
                        vapor_pressure_Pa=1.01e5,
                        critical_pressure_Pa=50.43e5)
        assert r2['capacity']['regime_verified'] is True

    def test_p5b310_olculdu_yalani_geri_gelmedi(self):
        from hrma.analysis.valve_feedline import line_pressure_drop
        r = line_pressure_drop(mass_flow_kg_s=5.0, density_kg_m3=1141.0,
                               viscosity_Pa_s=1.9e-4, line_id_m=0.03,
                               line_length_m=2.0, roughness_m=4.5e-05)
        kaynak = r['inputs']['roughness_source']
        assert 'user-supplied measured absolute roughness' not in kaynak
        assert 'UNDECLARED' in kaynak
        assert r['inputs']['roughness_provenance'] is None

    def test_p5b306_regulator_marji_alt_sinirli(self):
        from hrma.analysis.pressurant_sizing import regulated_pressurant
        for marj in (0.0, -0.5, -0.9, -1.0, float('nan'), float('inf')):
            with pytest.raises(ValueError):
                regulated_pressurant(propellant_volume=0.5,
                                     tank_pressure=30e5,
                                     storage_pressure=300e5,
                                     regulator_margin=marj)
        # sağlıklı marj hâlâ geçiyor
        assert regulated_pressurant(propellant_volume=0.5,
                                    tank_pressure=30e5,
                                    storage_pressure=300e5,
                                    regulator_margin=0.10)

    def test_p5b219_uq_band_isaret_kapisi_duruyor(self):
        from hrma.analysis.uncertainty import UncertainInput
        with pytest.raises(ValueError):
            UncertainInput(name='eta_c_star', dist='uniform',
                           low=-0.5, high=0.5, mode='multiplier')
        # offset kipi negatif kalabilir (toplamsal fark)
        UncertainInput(name='dummy', dist='uniform',
                       low=-0.09, high=0.09, mode='offset')

    def test_p5b218_yanlis_kunye_geri_gelmedi(self):
        """Yanlış MUTLAK iddia künyeden kalktı; iki ölü kalibrasyon
        sabiti geri gelmedi. Metin taraması değil AST + tarihçe ölçütü:
        cümle yalnız 'eskiden böyle yazıyordu' açıklamasında geçebilir."""
        import inspect

        from hrma.analysis import safety_analysis
        satirlar = inspect.getsource(safety_analysis).splitlines()
        iddia = 'Bu blok dışında sayısal sabit yazılmaz'
        gecen = [s for s in satirlar if iddia in s]
        assert len(gecen) <= 1
        for s in gecen:
            assert 'yazıyordu' in s or 'eskiden' in s
        assert 'loose_motor_range_cap_m' not in safety_analysis.SAFETY_MODEL
        assert ('relief_setting_fraction_of_design'
                not in safety_analysis.SAFETY_MODEL)

    def test_p9b117_analiz_ayagi_iki_tipin_hukmunu_yayimliyor(self):
        """AST: ``_analyze_end_caps`` iki alanı da yayımlamaya devam
        ediyor (D18 onarımı ağaçtan düşmedi)."""
        import ast
        import inspect

        from hrma.analysis.structural_analysis import StructuralAnalyzer
        kaynak = inspect.getsource(StructuralAnalyzer._analyze_end_caps)
        agac = ast.parse(kaynak.lstrip())
        anahtarlar = {d.value for d in ast.walk(agac)
                      if isinstance(d, ast.Constant)
                      and isinstance(d.value, str)}
        assert 'head_safety_factor_by_type' in anahtarlar
        assert 'head_stress_by_type_MPa' in anahtarlar
        assert 'head_safety_factor_by_type_basis' in anahtarlar
