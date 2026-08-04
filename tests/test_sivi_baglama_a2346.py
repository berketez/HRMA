"""v2.6.27 — sıvı motora A2+A3+A4+A6 bağlamalarının bekçisi.

Yol haritası (docs/YOL_HARITASI_2.7_VE_SONRASI.md) dört modülün sıvı motora
bağlanmasını istiyordu; dördü de app.py uçlarında ZATEN vardı ama motor kendi
hesapladığı geometriyle onları hiç çağırmıyordu:

  A2  slosh_analysis   -> yakıt + oksitleyici tankları (tank kartının kendi
                          yarıçapı/sıvı yüksekliği/yoğunluğu; g_eff = 1g
                          BEYANLI, uçuş ivmesi bağlanmaz)
  A3  pressure_vessel  -> sıvı tankları (MEOP/çap/cidar/malzeme tank
                          kartının kendisi; AIAA S-080 membran + kapak)
  A4  bolted_joint     -> kapak/enjektör flanşı cıvataları (oda basıncı +
                          hazne iç çapı; sayı kullanıcı girdisi, yoksa
                          not_sized — sayı uydurulmaz)
  A6  water_hammer     -> besleme hattı (hat çapı/hızı/basıncı motorun
                          kendisi; cidar kalınlığı + vana kapanma süresi
                          kullanıcı girdisi, cidar yoksa NOT_MODELLED)

Bu dosya üç şeyi kilitler:

1. **Bağlama gerçek** — bloklar var ve analizör GERÇEKTEN koşmuş
   (status alanları), girdileri motorun KENDİ çözümüyle birebir aynı.
2. **Fizik doğru** — frekans/Joukowsky/kopma değerleri buradaki bağımsız el
   hesabıyla yeniden üretilir (SP-106 Eq. 2.4; dP = rho*a*dv; ince cidar
   plastik limit). Bağlama girdileri yanlış birimle geçirilirse bu
   karşılaştırmalar kırılır.
3. **Uydurma yok** — kullanıcı girdisi verilmediğinde cıvata birleşimi
   'not_sized', su koçu hattı 'NOT_MODELLED' döner ve sayı taşımaz.

Ağ yok: motora boş ama VAR olan itici verisi enjekte edilir
(test_liquid_wiring_v2626 deseni).
"""

from __future__ import annotations

import contextlib
import io
import math

import numpy as np
import pytest

from hrma.engines.liquid_rocket_engine import (
    FEED_LINE_LENGTH_DEFAULT_M,
    LiquidRocketEngine,
)

# ---------------------------------------------------------------------------
# Çevrimdışı motor koşuları (modül başına bir kez — çözüm pahalı)
# ---------------------------------------------------------------------------

OFFLINE_PROPELLANTS = {'rp1': {}, 'lox': {}}

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

#: A4 + A6 kullanıcı girdileri (form/API alanları) — dolu koşu.
WIRED_OVERRIDES = dict(
    BASE_OVERRIDES,
    closure_bolt_count=12,
    feed_line_wall_thickness=1.5,   # mm
    valve_closure_time_ms=50.0,     # ms
)

BASE_CTOR = dict(thrust=25000, chamber_pressure=70, mixture_ratio=2.3,
                 fuel_type='rp1', oxidizer_type='lox',
                 propellant_data=OFFLINE_PROPELLANTS)

#: SP-106 birinci antisimetrik mod kökü (J1'(x)=0) — el hesabı için.
LAMBDA_1 = 1.8412
G0 = 9.80665


def _make(overrides):
    with contextlib.redirect_stdout(io.StringIO()):
        engine = LiquidRocketEngine(overrides=dict(overrides), **BASE_CTOR)
        result = engine.calculate_performance()
    return engine, result


@pytest.fixture(scope='module')
def wired():
    """Kullanıcı girdileri DOLU koşu: (motor, tam sonuç)."""
    return _make(WIRED_OVERRIDES)


@pytest.fixture(scope='module')
def bare():
    """Kullanıcı girdileri BOŞ koşu: not_sized / NOT_MODELLED yolları."""
    return _make(BASE_OVERRIDES)


def _tank(result, name):
    return result['propellant_tanks'][name]


# ===========================================================================
# A2 — çalkantı (slosh) bağlaması
# ===========================================================================

class TestA2Slosh:

    @pytest.mark.parametrize('tank_adi', ['oxidizer_tank', 'fuel_tank'])
    def test_blok_var_ve_hesapli(self, wired, tank_adi):
        """Her iki tankta ayrı slosh bloğu var ve analizör gerçekten koşmuş."""
        blok = _tank(wired[1], tank_adi)['slosh']
        assert blok['status'] == 'computed'
        assert blok['f1_hz'] > 0 and math.isfinite(blok['f1_hz'])
        assert 0.0 < blok['slosh_mass_ratio'] < 1.0
        assert blok['pendulum_length'] > 0
        assert len(blok['modes']) >= 4
        assert 'basis' in blok and 'slosh_analysis' in blok['basis']

    @pytest.mark.parametrize('tank_adi', ['oxidizer_tank', 'fuel_tank'])
    def test_frekans_el_hesabiyla_ayni(self, wired, tank_adi):
        """SP-106 Eq. 2.4: omega^2 = (lam*g/R)*tanh(lam*h/R) — bağımsız el
        hesabı bloğun kendi girdileriyle aynı frekansı üretmeli. Bağlama
        yarıçapı/yüksekliği yanlış birimle geçirirse burası kırılır."""
        blok = _tank(wired[1], tank_adi)['slosh']
        R = blok['radius']
        h = blok['fill_height']
        omega2 = (LAMBDA_1 * blok['g_eff'] / R) * math.tanh(LAMBDA_1 * h / R)
        f1_el = math.sqrt(omega2) / (2.0 * math.pi)
        assert blok['f1_hz'] == pytest.approx(f1_el, rel=1e-9)

    @pytest.mark.parametrize('tank_adi', ['oxidizer_tank', 'fuel_tank'])
    def test_geometri_tank_kartinin_kendisi(self, wired, tank_adi):
        """Slosh yarıçapı ve sıvı yüksekliği tank kartından türemeli:
        R = çap/2, h = V_sıvı/(pi R^2). İkinci bir geometri kaynağı yok."""
        tank = _tank(wired[1], tank_adi)
        blok = tank['slosh']
        R_karttan = tank['dimensions']['diameter'] / 2000.0        # mm -> m
        v_liq_m3 = tank['propellant_data']['volume_required'] / 1000.0  # L->m3
        h_karttan = v_liq_m3 / (math.pi * R_karttan ** 2)
        assert blok['radius'] == pytest.approx(R_karttan, rel=1e-9)
        assert blok['fill_height'] == pytest.approx(h_karttan, rel=1e-9)
        # Sıvı tankın içine sığmalı (ullage gerçek).
        assert h_karttan < tank['dimensions']['length'] / 1000.0

    @pytest.mark.parametrize('tank_adi', ['oxidizer_tank', 'fuel_tank'])
    def test_calkanti_kutlesi_yogunluktan(self, wired, tank_adi):
        """m_slosh = oran x (rho pi R^2 h): yoğunluk motorun tek kaynağı."""
        blok = _tank(wired[1], tank_adi)['slosh']
        m_liq = blok['liquid_mass_kg']
        beklenen = blok['slosh_mass_ratio'] * m_liq
        assert blok['slosh_mass_kg'] == pytest.approx(beklenen, rel=1e-9)
        assert m_liq > 0

    def test_g_eff_1g_ve_beyanli(self, wired):
        """g_eff = 1g standart yerçekimi; uçuş ivmesinin BAĞLANMADIĞI beyan
        edilmeli (sayı uydurma yasağının A2 hâli)."""
        for tank_adi in ('oxidizer_tank', 'fuel_tank'):
            blok = _tank(wired[1], tank_adi)['slosh']
            assert blok['g_eff'] == pytest.approx(G0)
            assert 'g_eff_basis' in blok
            assert 'does not couple' in blok['g_eff_basis']
            assert 'sqrt' in blok['g_eff_basis']  # yeniden ölçekleme tarifi

    def test_bafl_gercek_halka_geometrisinden(self, wired):
        """Bafl değerlendirmesi iç yapı listesindeki GERÇEK halkanın
        genişliğiyle yapılmalı (bir 'tipik' oran değil)."""
        tank = _tank(wired[1], 'oxidizer_tank')
        blok = tank['slosh']
        baffle = blok['baffle']
        halkalar = tank['internal_structures']['slosh_baffles']
        assert halkalar, 'iç yapı listesinde halka bafl bekleniyordu'
        R_mm = tank['dimensions']['diameter'] / 2.0
        gercek_oranlar = {round(b['ring_width_mm'] / R_mm, 9)
                          for b in halkalar}
        if 'width_ratio' in baffle:           # yüzeyin altında halka var
            assert round(baffle['width_ratio'], 9) in gercek_oranlar
            assert baffle['confidence'] == 'approximate'
        else:                                  # öneri yolu da beyanlıdır
            assert baffle['confidence'] == 'approximate'
        assert 'baffle_basis' in blok


# ===========================================================================
# A3 — basınçlı kap (pressure_vessel) bağlaması
# ===========================================================================

class TestA3PressureVessel:

    @pytest.mark.parametrize('tank_adi', ['oxidizer_tank', 'fuel_tank'])
    def test_girdiler_tank_kartinin_kendisi(self, wired, tank_adi):
        """MEOP/çap/cidar/malzeme tank kartıyla BİREBİR aynı — iki kart
        çelişemez (katıdaki tek-kaynak deseni)."""
        tank = _tank(wired[1], tank_adi)
        v = tank['pressure_vessel']
        assert v['status'] in ('PASS', 'MARGINAL', 'FAIL')
        girdiler = v['inputs']
        assert girdiler['meop_bar'] == pytest.approx(
            tank['structural']['pressure_rating'], rel=1e-9)
        assert girdiler['inner_diameter_mm'] == pytest.approx(
            tank['dimensions']['diameter'], rel=1e-9)
        assert girdiler['wall_thickness_mm'] == pytest.approx(
            tank['dimensions']['wall_thickness'], rel=1e-9)
        assert v['material'] == tank['structural']['material_key']

    @pytest.mark.parametrize('tank_adi', ['oxidizer_tank', 'fuel_tank'])
    def test_kopma_el_hesabiyla_ayni(self, wired, tank_adi):
        """İnce cidar plastik limit: P_b = 2*UTS*t/(D+t) — bağımsız el
        hesabı analizörün kendi yaprağını yeniden üretmeli."""
        v = _tank(wired[1], tank_adi)['pressure_vessel']
        su = v['derating']['derated_ultimate_strength_Pa']
        t = v['wall_thickness_used_mm'] / 1e3
        D = v['inputs']['inner_diameter_mm'] / 1e3
        p_thin_el = 2.0 * su * t / (D + t) / 1e5
        assert v['burst_thin_wall_bar'] == pytest.approx(p_thin_el, rel=1e-9)
        # Gerçek kopma iki modelin min'i; marj gerekli kopmaya oran.
        assert v['actual_burst_pressure_bar'] == pytest.approx(
            min(v['burst_faupel_bar'], v['burst_thin_wall_bar']), rel=1e-12)
        assert v['burst_margin'] == pytest.approx(
            v['actual_burst_pressure_bar'] / v['required_burst_pressure_bar'],
            rel=1e-9)

    @pytest.mark.parametrize('tank_adi', ['oxidizer_tank', 'fuel_tank'])
    def test_kapak_kalinliklari_ve_sicaklik_beyani(self, wired, tank_adi):
        """Kapak (başlık) kalınlıkları raporlanır; cidar sıcaklığının ORTAM
        varsayıldığı ve kriyojenik tokluk taramasının devreye GİRMEDİĞİ
        açıkça beyan edilir (tank termal modeli yok — uydurma yok)."""
        v = _tank(wired[1], tank_adi)['pressure_vessel']
        assert v['head_thickness_selected_mm'] > 0
        assert v['head_type'] in v['head_thicknesses_mm']
        assert 'temperature_basis' in v
        assert 'ambient' in v['temperature_basis']
        assert 'NOT engaged' in v['temperature_basis']
        assert 'basis' in v and 'pressure_vessel' in v['basis']


# ===========================================================================
# A4 — kapak cıvata birleşimi (bolted_joint) bağlaması
# ===========================================================================

class TestA4BoltedJoint:

    def test_civatasiz_boyutlandirilmaz(self, bare):
        """Cıvata sayısı girilmeden birleşim boyutlandırılmaz — sayı
        uydurulmaz (katıdaki not_sized deseni)."""
        joint = bare[1]['structural_analysis']['closure_joint']
        assert joint['status'] == 'not_sized'
        assert 'bolt' in joint['basis']
        assert 'proof_safety_factor' not in joint

    def test_civatayla_gercek_hesap(self, wired):
        """Sayı girilince birleşim GERÇEK oda basıncı ve hazne iç çapıyla
        boyutlanır; emniyet faktörleri analizörden gelir."""
        motor, sonuc = wired
        joint = sonuc['structural_analysis']['closure_joint']
        assert joint['status'] == 'sized'
        assert joint['bolt_count'] == 12
        assert joint['pressure_bar'] == pytest.approx(70.0)
        # Sızdırmazlık çapı = hazne iç çapı (results['chamber_diameter'] mm).
        assert joint['seal_diameter_mm'] == pytest.approx(
            sonuc['chamber_diameter'], rel=1e-6)
        for alan in ('proof_safety_factor', 'separation_factor',
                     'overload_factor', 'tightening_torque_nm'):
            assert isinstance(joint[alan], float) and joint[alan] > 0

    def test_analizorle_birebir_ayni(self, wired):
        """Bağlama, /api/bolted-joint'in kullandığı analizörün TA KENDİSİNİ
        çağırmalı: aynı girdiyle doğrudan çağrı aynı faktörleri verir."""
        from hrma.analysis.bolted_joint import analyze_bolted_joint
        joint = wired[1]['structural_analysis']['closure_joint']
        dogrudan = analyze_bolted_joint(
            pressure_bar=joint['pressure_bar'],
            seal_diameter_mm=joint['seal_diameter_mm'],
            bolt_count=joint['bolt_count'],
            size=joint['bolt_size'],
            property_class=joint['property_class'],
            member_material=joint['member_material'])
        sf = dogrudan['safety_factors']
        assert joint['proof_safety_factor'] == pytest.approx(
            sf['proof_SF_min'], rel=1e-12)
        assert joint['separation_factor'] == pytest.approx(
            sf['separation_factor_n0_min'], rel=1e-12)

    def test_civata_sayisi_marji_oynatir(self, wired):
        """Bağlama canlı olmalı: cıvata sayısı artınca ayrılma marjı
        büyümeli (sabit kopyalanmış blok değil)."""
        motor, _ = wired
        eski = dict(motor.overrides)
        try:
            motor.overrides['closure_bolt_count'] = 6
            az = motor._closure_joint_analysis()
            motor.overrides['closure_bolt_count'] = 24
            cok = motor._closure_joint_analysis()
        finally:
            motor.overrides = eski
        assert az['status'] == cok['status'] == 'sized'
        assert cok['separation_factor'] > az['separation_factor']


# ===========================================================================
# A6 — besleme hattı su koçu (water_hammer) bağlaması
# ===========================================================================

class TestA6WaterHammer:

    def test_girdisiz_not_modelled_ve_sayisiz(self, bare):
        """Cidar kalınlığı girilmeden hat bloğu NOT_MODELLED döner ve HİÇBİR
        sayısal sonuç taşımaz — girdi uydurulmaz."""
        wh = bare[1]['detailed_feed_system']['water_hammer']
        for hat in ('oxidizer_line', 'fuel_line'):
            blok = wh[hat]
            assert blok['status'] == 'NOT_MODELLED'
            assert 'feed_line_wall_thickness' in blok['required_inputs']
            assert 'not invented' in blok['basis']
            sayisal = [k for k, v in blok.items()
                       if isinstance(v, (int, float)) and k != 'status']
            assert not sayisal, f'NOT_MODELLED blokta sayı var: {sayisal}'

    @pytest.mark.parametrize('hat', ['oxidizer_line', 'fuel_line'])
    def test_joukowsky_el_hesabiyla_ayni(self, wired, hat):
        """dP = rho * a * dv (Joukowsky 1898) ve t_c = 2L/a — bloğun kendi
        yapraklarıyla bağımsız el hesabı."""
        blok = wired[1]['detailed_feed_system']['water_hammer'][hat]
        assert blok['status'] in ('SAFE', 'MARGINAL', 'UNSAFE')
        rho = blok['fluid_properties']['density_kg_m3']
        a = blok['wave_speed_m_s']
        dv = blok['delta_v_m_s']
        assert blok['joukowsky_pressure_rise_Pa'] == pytest.approx(
            rho * a * dv, rel=1e-9)
        assert blok['critical_closure_time_s'] == pytest.approx(
            2.0 * FEED_LINE_LENGTH_DEFAULT_M / a, rel=1e-9)

    @pytest.mark.parametrize('hat,ana', [('oxidizer_line', 'oxidizer_main'),
                                         ('fuel_line', 'fuel_main')])
    def test_hat_geometrisi_motorun_kendisi(self, wired, hat, ana):
        """Hat çapı ve uzunluğu besleme sisteminin TEK kaynağından gelmeli
        (ayrı bir 'su koçu çapı' uydurulmaz)."""
        motor, sonuc = wired
        blok = sonuc['detailed_feed_system']['water_hammer'][hat]
        girdiler = blok['inputs']
        beklenen_cap_mm = motor.feed_system['feed_lines'][ana]['diameter'] * 1000.0
        assert girdiler['line_id_mm'] == pytest.approx(beklenen_cap_mm,
                                                       rel=1e-9)
        assert girdiler['line_length_m'] == pytest.approx(
            FEED_LINE_LENGTH_DEFAULT_M)
        assert 'line_length_basis' in blok       # yerleşim varsayımı beyanlı
        # Akış hızı: v = mdot/(rho*A) özdeşliği bloğun kendi yapraklarıyla.
        rho = blok['fluid_properties']['density_kg_m3']
        alan = math.pi * (girdiler['line_id_mm'] / 1e3) ** 2 / 4.0
        assert blok['mass_flow_kg_s'] == pytest.approx(
            rho * blok['flow_velocity_m_s'] * alan, rel=1e-9)

    def test_yavas_kapanma_michaud(self, wired):
        """50 ms kapanma kritik süreden uzun -> yavaş rejim; Michaud
        indirgemesi dP_slow = dP * (t_c / t_close) el hesabıyla aynı."""
        blok = wired[1]['detailed_feed_system']['water_hammer']['oxidizer_line']
        assert blok['closure_regime'] == 'slow'
        assert blok['valve_closure_time_ms'] == pytest.approx(50.0)
        beklenen = (blok['joukowsky_pressure_rise_Pa']
                    * blok['critical_closure_time_ms'] / 50.0)
        assert blok['applied_pressure_rise_Pa'] == pytest.approx(beklenen,
                                                                 rel=1e-9)
        assert blok['peak_pressure_bar'] == pytest.approx(
            blok['working_pressure_bar']
            + blok['applied_pressure_rise_bar'], rel=1e-9)
        assert blok['valve_closure_time_source'] == (
            'user input (valve closure time)')

    def test_calisma_basinci_pompa_basmasi(self, wired):
        """Turbopompalı çevrimde hat çalışma basıncı pompa basma
        basıncıdır ve kaynağı beyanlıdır."""
        sonuc = wired[1]
        blok = sonuc['detailed_feed_system']['water_hammer']['oxidizer_line']
        assert 'pump discharge' in blok['working_pressure_basis']
        # Basma basıncı en az oda basıncı kadar olmalı (Pc + kayıplar).
        assert blok['working_pressure_bar'] >= sonuc['chamber_pressure']

    def test_tablosuz_itici_hatti_not_modelled(self):
        """Hacimsel modülü tablolu olmayan itici (metan) hattı NOT_MODELLED
        döner — bulk modül uydurulmaz; tablolu hat (LOX) yine hesaplanır."""
        with contextlib.redirect_stdout(io.StringIO()):
            motor = LiquidRocketEngine(
                thrust=25000, chamber_pressure=70, mixture_ratio=3.2,
                fuel_type='methane', oxidizer_type='lox',
                propellant_data={'methane': {}, 'lox': {}},
                overrides={'feed_line_wall_thickness': 1.5})
        drops = {
            'oxidizer_line': {'line_diameter_mm': 50.0,
                              'line_velocity_m_s': 5.0},
            'fuel_line': {'line_diameter_mm': 50.0,
                          'line_velocity_m_s': 5.0},
            'pump_discharge_pressure_ox': 90.0,
            'pump_discharge_pressure_fuel': 90.0,
        }
        wh = motor._feed_water_hammer_analysis(drops, 3.0, False)
        assert wh['fuel_line']['status'] == 'NOT_MODELLED'
        assert 'methane' in wh['fuel_line']['basis']
        assert wh['oxidizer_line']['status'] in ('SAFE', 'MARGINAL', 'UNSAFE')

    def test_boru_malzemesi_varsayimi_beyanli(self, wired):
        """Boru malzemesi bir tasarım SEÇİMİ değil: verilmediyse paslanmaz
        varsayımı kaynağıyla beyan edilir."""
        blok = wired[1]['detailed_feed_system']['water_hammer']['oxidizer_line']
        assert 'assumed' in blok['pipe_material_source']
        assert blok['pipe']['material'] == 'ss_304'


# ===========================================================================
# Uyarı dalları — kritik durumlar sessiz kalmaz ({code, params} sözleşmesi)
# ===========================================================================

class TestUyariDallari:
    """UNSAFE/FAIL dalları ölü kod değil: gerçekten tetiklenirler ve
    i18n uyarı sözleşmesine ({code, params, severity}) kayıt düşerler."""

    @pytest.fixture()
    def motor(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return LiquidRocketEngine(
                thrust=25000, chamber_pressure=70, mixture_ratio=2.3,
                fuel_type='rp1', oxidizer_type='lox',
                propellant_data=OFFLINE_PROPELLANTS,
                overrides={'feed_line_wall_thickness': 0.3})

    def test_su_kocu_unsafe_uyari_uretir(self, motor):
        """İnce cidar + ani kapanma + yüksek basma basıncı -> UNSAFE hat,
        kritik uyarı kaydı (kod + parametreler)."""
        drops = {
            'oxidizer_line': {'line_diameter_mm': 100.0,
                              'line_velocity_m_s': 8.0},
            'fuel_line': {'line_diameter_mm': 100.0,
                          'line_velocity_m_s': 8.0},
            'pump_discharge_pressure_ox': 150.0,
            'pump_discharge_pressure_fuel': 150.0,
        }
        wh = motor._feed_water_hammer_analysis(drops, 3.0, False)
        assert wh['oxidizer_line']['status'] == 'UNSAFE'
        kayitlar = [w for w in motor.design_warnings
                    if w['code'] == 'warn.liquid.water_hammer_unsafe']
        assert kayitlar, 'UNSAFE hat kritik uyarı üretmeli'
        assert kayitlar[0]['severity'] == 'critical'
        assert {'line', 'peak_bar', 'yield_bar'} <= set(kayitlar[0]['params'])

    def test_kap_fail_uyari_uretir(self, motor):
        """1 mm cidarlı 1 m tank 60 bar MEOP'ta FAIL -> kritik uyarı."""
        v = motor._tank_pressure_vessel_analysis(
            'oxidizer_tank', 60e5, 1.0, 0.001, 'al_2024_t3')
        assert v['status'] == 'FAIL'
        kayitlar = [w for w in motor.design_warnings
                    if w['code'] == 'warn.liquid.tank_vessel_fail']
        assert kayitlar, 'FAIL kap kritik uyarı üretmeli'
        assert kayitlar[0]['severity'] == 'critical'
        assert {'tank', 'burst_margin'} <= set(kayitlar[0]['params'])


# ===========================================================================
# Beyan tazeliği — A2 bağlanınca çürüyen metinler güncellendi mi
# ===========================================================================

class TestBeyanTazeligi:

    def test_bafl_kalinlik_beyani_slosh_blogunu_isaret_eder(self, wired):
        """Bafl kalınlığı hâlâ gauge (yüke boyutlanmadı) ama beyan artık
        modal çalkantının HESAPLANDIĞINI söylemeli — eski 'hiçbiri
        modellenmedi' cümlesi çürümüştü."""
        internals = _tank(wired[1], 'oxidizer_tank')['internal_structures']
        bafl = internals['slosh_baffles'][0]
        assert 'gauge' in bafl['thickness_basis']          # bekçi: eski test
        assert bafl['thickness_load_sized'] is False
        assert 'slosh block' in bafl['thickness_basis']    # tazelenen kısım
        assert any('SP-8031' in kalem for kalem in internals['not_modelled'])
        assert any('slosh block' in kalem
                   for kalem in internals['not_modelled'])
