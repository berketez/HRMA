# -*- coding: utf-8 -*-
"""ÖH Dalga-15 / sıvı kulvarı, aşama 2 — onarım bekçileri.

Her test, onarımdan ÖNCE ölçülmüş somut bir kusuru görür. Ters-mutasyon
kanıtı (onarımı geçici geri al -> test KIRMIZI -> geri koy -> YEŞİL)
``docs/scofield/raw/OH/D15/sivi/a2/mutasyon.py`` ile alınmıştır; ölçüm
sayıları ``once.json`` (onarım öncesi) ve ``sonra.json`` (sonrası)
dosyalarındadır.

Kapsanan kalemler: P3B3-01, P3B3-02, P3B3-03, P3B3-04, P3B3-05, P3B3-06,
P3B4-01, P3B4-03.
"""
import contextlib
import io

import pytest

from hrma.engines.liquid_rocket_engine import (
    BURN_TIME_DEFAULT_S, CRYOGENIC_PROPELLANTS, FEED_LINE_MAX_VELOCITY_MS,
    FEED_LINE_MIN_VELOCITY_MS, FEED_LINE_STANDARD_SIZES_M,
    TANK_CRYO_SUITABLE_MATERIALS, TURBINE_TIP_SPEED_LIMIT_MS,
    TURBINE_VELOCITY_RATIO, LiquidRocketEngine)


def _motor(**kw):
    ov = kw.pop('overrides', {})
    tas = dict(thrust=250000, chamber_pressure=150, mixture_ratio=2.5,
               fuel_type='rp1', oxidizer_type='lox',
               cooling_type='regenerative', injector_type='impinging',
               feed_system_type='turbopump')
    tas.update(kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return LiquidRocketEngine(overrides=ov, **tas)


def _besleme(**kw):
    """(motor, feed_system.turbopump kartı, detailed_feed_system) üçlüsü."""
    e = _motor(**kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        e.calculate_nozzle_geometry()
        det = e._analyze_detailed_feed_system()
    return e, (e.feed_system.get('turbopump') or {}), det


def _kodlar(e):
    return {w['code'] for w in e.design_warnings}


CEVRIMLER = ['gas_generator', 'staged_combustion', 'full_flow_staged']


# =====================================================================
# P3B3-01 — aynı yanıtta iki gaz jeneratörü kartı
# ÖLÇÜLDÜ (250 kN / Pc 150): feed_system.turbopump.gas_generator
# {MR 1,75; T 1200 K; P 195 bar; flow_fraction 0,05} ⟷ çevrim çözümünün
# kartı {MR 0,058; T 900 K; P 215,98 bar; flow_fraction 30,23} — karışım
# oranı 30,16 KAT ayrı, flow_fraction alanı biri kesir biri yüzde.
# =====================================================================
@pytest.mark.parametrize('cyc', CEVRIMLER)
def test_p3b3_01_iki_gg_karti_ayni_sayiyi_soyler(cyc):
    e, tp, det = _besleme(overrides={'engine_cycle': cyc})
    a = tp['gas_generator']
    b = det['turbopump_analysis']['gas_generator']
    assert a['status'] == b['status'], (
        f'{cyc}: iki gaz jeneratörü kartı farklı durumda')
    if a['status'] != 'modelled':
        pytest.skip(f'{cyc}: çevrim kapanmadı, iki kart da fail-closed')
    for alan in ('mixture_ratio', 'temperature', 'chamber_pressure',
                 'flow_fraction', 'mass_flow_rate'):
        av, bv = a[alan], b[alan]
        assert av == pytest.approx(bv, rel=1e-9), (
            f'{cyc}: gas_generator.{alan} iki kartta ayrışıyor: {av} / {bv}')


@pytest.mark.parametrize('cyc', CEVRIMLER)
def test_p3b3_01_flow_fraction_birimi_iki_kartta_ayni_ve_beyanli(cyc):
    """Aynı ad, aynı yanıt, İKİ BİRİM kusuru: kesir (0,05) ⟷ yüzde (30,23)."""
    e, tp, det = _besleme(overrides={'engine_cycle': cyc})
    a = tp['gas_generator']
    b = det['turbopump_analysis']['gas_generator']
    assert a['flow_fraction_unit'] == 'percent'
    assert b['flow_fraction_unit'] == 'percent'
    if a['status'] == 'modelled':
        # Yüzde birimi: %5'lik bir GG payı 5,0 olarak yayımlanır, 0,05 değil.
        assert a['flow_fraction'] > 0.5, (
            'flow_fraction yüzde birimindeyse kesir büyüklüğünde olamaz')


def test_p3b3_01_gg_karti_cevrim_kapanmazsa_sayi_uydurmaz():
    """Fail-closed: çözüm yoksa MR = 0,7·MR_ana gibi varsayım yayımlanmaz."""
    e, tp, det = _besleme(overrides={'engine_cycle': 'expander'},
                          fuel_type='rp1')
    a = tp['gas_generator']
    if a['status'] == 'modelled':
        pytest.skip('bu çevrim kapandı; fail-closed dalı burada kurulamıyor')
    for alan in ('mixture_ratio', 'temperature', 'chamber_pressure',
                 'flow_fraction'):
        assert a[alan] is None, f'{alan} çözüm yokken yayımlanıyor'
    assert 'NOT published' in str(a['source'])


# =====================================================================
# P3B3-02 — aynı yanıtta iki/üç türbin kartı
# ÖLÇÜLDÜ: {T 1200 K; PR 8,5; verim 0,65} ⟷ {T 900 K; PR 1,25; verim 65,0}
# ve çevrimin gerçekten kullandığı verim 0,78 (üçüncü değer).
# =====================================================================
@pytest.mark.parametrize('cyc', CEVRIMLER)
def test_p3b3_02_iki_turbin_karti_ayni_sayiyi_soyler(cyc):
    e, tp, det = _besleme(overrides={'engine_cycle': cyc})
    a = tp['turbine']
    b = det['turbopump_analysis']['turbine']
    if a['status'] != 'modelled':
        pytest.skip(f'{cyc}: çevrim kapanmadı')
    for alan in ('inlet_temperature', 'pressure_ratio', 'efficiency'):
        assert a[alan] == pytest.approx(b[alan], rel=1e-9), (
            f'{cyc}: turbine.{alan} iki kartta ayrışıyor: '
            f'{a[alan]} / {b[alan]}')


@pytest.mark.parametrize('cyc', CEVRIMLER)
def test_p3b3_02_verim_birimi_iki_kartta_kesir_ve_beyanli(cyc):
    e, tp, det = _besleme(overrides={'engine_cycle': cyc})
    a = tp['turbine']
    b = det['turbopump_analysis']['turbine']
    assert a['efficiency_unit'] == 'fraction'
    assert b['efficiency_unit'] == 'fraction'
    for kart, ad in ((a, 'A'), (b, 'B')):
        v = kart['efficiency']
        if v is not None:
            assert 0.0 < v <= 1.0, (
                f'{cyc}: {ad} kartında verim kesir değil ({v})')


@pytest.mark.parametrize('cyc', ['staged_combustion', 'full_flow_staged'])
def test_p3b3_02_yayimlanan_verim_cevrimin_kullandigi_verimdir(cyc):
    """Ölçüldü: kartlar 0,65 derken çözücü 0,78 kullanıyordu."""
    e, tp, det = _besleme(overrides={'engine_cycle': cyc})
    cs = det['engine_cycle_solution']
    if cs.get('status') != 'converged':
        pytest.skip('çevrim kapanmadı')
    eta_solved = (cs['shafts'][0].get('turbine') or {}).get('efficiency')
    assert isinstance(eta_solved, (int, float))
    assert tp['turbine']['efficiency'] == pytest.approx(eta_solved, rel=1e-9)
    assert (det['turbopump_analysis']['turbine']['efficiency']
            == pytest.approx(eta_solved, rel=1e-9))


# =====================================================================
# P3B3-03 — NPSH_mevcut negatifken donanım uydurma 1000 Pa yükle boyutlanıyor
# ÖLÇÜLDÜ (250 kN / Pc 200): panelin okuduğu kartta rpm=281,5,
# impeller_diameter=11,98 m yayımlanırken NPSH_a=−4,65 m ve speed_source
# alanları YALNIZ ayrıntılı blokta duruyordu.
# =====================================================================
@pytest.mark.parametrize('F', [25000, 250000, 1000000])
def test_p3b3_03_durustluk_alanlari_panelin_kartinda(F):
    e, tp, det = _besleme(thrust=F, chamber_pressure=200)
    for ad in ('oxidizer_pump', 'fuel_pump'):
        kart = tp[ad]
        for alan in ('npsh_available', 'npsh_required', 'speed_source',
                     'suction_feasible', 'status', 'status_basis'):
            assert alan in kart, f'{F} N / {ad}: {alan} kartta yok'
        b = det['turbopump_analysis'][ad]
        assert kart['npsh_available'] == pytest.approx(b['npsh_available'],
                                                       rel=1e-9)
        assert kart['speed_source'] == b['speed_source']


def test_p3b3_03_gerceklesemez_pompada_geometri_yayimlanmaz(monkeypatch):
    """NPSH_a<=0 iken 11,98 m'lik çark artık 'tasarım' diye çıkmaz.

    ÖH D18 fizik-a2 (F3 ≡ OH-D15-06 / P3B3-03 kalan yarısı) ÇEVİRİSİ:
    fikstür 250 kN / Pc 200'ü seçiyordu çünkü SABİT 3,0 bar tank basıncıyla
    o nokta NPSH_a = −4,65 m veriyordu. Tank basıncı artık pompaların NPSH
    gereksiniminden boyutlandırılıyor (SP-8109 §3.2.1.2), yani aynı nokta
    sağlıklı çıkıyor (+6,08 m) — bu kalemin ONARIMININ ta kendisidir.

    Bekçinin iddiası (gerçekleşemez emme dalında donanım YAYIMLANMAZ)
    korunuyor; o dala artık tank basıncı ELLE düşürülerek giriliyor.
    Aksi hâlde bekçi ya ölür ya da onarımı geri almayı şart koşardı.
    """
    monkeypatch.setattr(
        LiquidRocketEngine, '_tank_pressure_bar',
        lambda self: (1.0, 'test fixture: forced low tank pressure'))
    e, tp, det = _besleme(thrust=250000, chamber_pressure=200)
    kart = tp['oxidizer_pump']
    assert kart['npsh_available'] < 0, (
        'fikstür seçimi: bu nokta gerçekleşemez emme dalını kurmalı')
    assert kart['suction_feasible'] is False
    assert kart['status'] == 'not_feasible'
    assert kart['impeller_diameter'] is None
    assert kart['impeller_tip_speed'] is None
    assert kart['impeller_geometry_status'] == 'not_computed'
    # Sayı kaybolmuyor: taban devriyle ima edilen geometri ayrı adla durur.
    b = det['turbopump_analysis']['oxidizer_pump']
    assert b['impeller_diameter_if_inlet_head_floor'] > 0


def test_p3b3_03_motor_ve_modul_ayni_pompa_icin_ayni_hukmu_verir():
    """Ölçüldü: C1 modülü 'not_computed' derken motor tam donanım kartı
    yayımlıyordu — aynı yanıtta iki zıt hüküm."""
    e, tp, det = _besleme(thrust=250000, chamber_pressure=200)
    modul = (det.get('turbopump_sizing') or {}).get('oxidizer_pump') or {}
    motor = tp['oxidizer_pump']
    if modul.get('status') == 'not_computed':
        assert motor['status'] == 'not_feasible', (
            'modül pompayı reddederken motor kartı "modelled" diyemez')
        assert motor['impeller_diameter'] is None


# =====================================================================
# P3B3-04 — hat çapı kaba merdivene sessizce yuvarlanıyor
# ÖLÇÜLDÜ (RP-1/LOX, Pc 70, MR 2,3): 25 kN oksitleyici 11,03 m/s — beyan
# edilen 3-8 m/s bandının %38 üstü, SIFIR uyarı, yayımlanan sözlükte band
# beyanı yok.
# =====================================================================
@pytest.mark.parametrize('F', [5000, 25000, 40000, 100000, 250000,
                               1000000, 2000000])
def test_p3b4_hat_hizi_tavani_asamaz_ya_da_uyarilir(F):
    e = _motor(thrust=F, chamber_pressure=70, mixture_ratio=2.3)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        e.calculate_nozzle_geometry()
        fs = e.feed_system
    for ad in ('oxidizer_line', 'fuel_line'):
        blk = fs['pressure_drops'][ad]
        v = blk['line_velocity_m_s']
        assert blk['line_velocity_band_m_s'] == [FEED_LINE_MIN_VELOCITY_MS,
                                                 FEED_LINE_MAX_VELOCITY_MS]
        assert blk['line_diameter_source']
        if v > FEED_LINE_MAX_VELOCITY_MS or v < FEED_LINE_MIN_VELOCITY_MS:
            assert blk['line_velocity_band_status'] != 'within'
            # ÖH D17 · P3B3-04 ŞART (Fable-D15): uyarı HAT ADINA göre
            # eşlenir. Eski satır yalnız kodun kümede BULUNMASINA bakıyordu;
            # iki hattan biri band dışıyken öbürünün uyarısı bu kontrolü
            # geçiriyordu, yani bir hattın bastırılan uyarısı kırmızı
            # doğurmuyordu (Fable ölçümü: ters mutasyonda beklenen 3 yerine
            # 1 kırmızı). Uyarının params.line alanı hattın kendisidir
            # (motor: _warn(..., line=prop_kind)); 'oxidizer_line' ->
            # 'oxidizer', 'fuel_line' -> 'fuel'.
            hat_adi = ad.replace('_line', '')
            eslesen = [w for w in e.design_warnings
                       if w['code'] == 'warn.liquid.feed_line_velocity'
                                       '_out_of_band'
                       and str((w.get('params') or {}).get('line')) == hat_adi]
            assert eslesen, (
                f'{F} N / {ad}: hız {v:.2f} m/s band dışı ama BU HATTIN '
                f'uyarısı yok (kümede yalnız öbür hattınki olabilir); '
                f'yayımlanan uyarılar: '
                f'{[(w["code"], (w.get("params") or {}).get("line")) for w in e.design_warnings if "feed_line" in w["code"]]}')
            # Uyarı yayımlanan hızın kendisini söylemeli (künye ⟷ sayı).
            assert float(eslesen[0]['params']['velocity_ms']) == pytest.approx(
                float(v), abs=0.01)
        else:
            assert blk['line_velocity_band_status'] == 'within'
            # Band içindeki hat için o hattın uyarısı ATEŞLEMEMELİ.
            yanlis = [w for w in e.design_warnings
                      if w['code'] == 'warn.liquid.feed_line_velocity'
                                      '_out_of_band'
                      and str((w.get('params') or {}).get('line'))
                      == ad.replace('_line', '')]
            assert not yanlis, (
                f'{F} N / {ad}: hız {v:.2f} m/s band İÇİNDE ama uyarı var')


def test_p3b3_04_25kn_tavan_ihlali_kapandi():
    """Savcının ölçtüğü tam nokta: 25 kN oksitleyici hattı 11,03 m/s idi."""
    e = _motor(thrust=25000, chamber_pressure=70, mixture_ratio=2.3)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        e.calculate_nozzle_geometry()
        blk = e.feed_system['pressure_drops']['oxidizer_line']
    assert blk['line_velocity_m_s'] <= FEED_LINE_MAX_VELOCITY_MS, (
        f"25 kN oksitleyici hattı hâlâ tavanın üstünde: "
        f"{blk['line_velocity_m_s']:.3f} m/s")


def test_p3b3_04_secim_bandin_icindeki_en_iyi_basamaktir():
    """Merdivende banda düşen basamak varsa seçim ONLARDAN biri olmalı."""
    e = _motor(thrust=250000, chamber_pressure=70, mixture_ratio=2.3)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        e.calculate_nozzle_geometry()
    secim = e._line_diameter_selection(e.mdot_ox, 'oxidizer')
    assert secim['diameter_m'] in FEED_LINE_STANDARD_SIZES_M
    assert secim['band_status'] == 'within'
    assert (FEED_LINE_MIN_VELOCITY_MS <= secim['velocity_m_s']
            <= FEED_LINE_MAX_VELOCITY_MS)


# =====================================================================
# P3B3-05 — REDDEDİLEN girdi yayımlanan sayıyı değiştiriyor
# ÖLÇÜLDÜ (250 kN, gas_generator): girdi yok -> TIT 1000 K, GG debisi
# 2,4288 kg/s; generator_gas_temp=99999 (REDDEDİLDİ) -> TIT 1200 K,
# 1,9755 kg/s (-%18,7). staged'de 900 -> 1200 K.
# =====================================================================
def _cevrim_imzasi(det):
    b = det['turbopump_analysis']['turbine']
    gg = det['turbopump_analysis']['gas_generator']
    cs = det['engine_cycle_solution']
    return (b['inlet_temperature'], b['pressure_ratio'],
            gg['mass_flow_rate'], cs.get('turbine_power_total_W'))


@pytest.mark.parametrize('cyc', ['gas_generator', 'staged_combustion'])
@pytest.mark.parametrize('kotu', [99999, -50, 'x', 3000])
def test_p3b3_05_reddedilen_tit_yaniti_degistirmez(cyc, kotu):
    """Savcının kapanış ölçütü: bant dışı değer gönderilen koşunun yanıtı,
    alan hiç gönderilmemiş koşunun yanıtıyla BİT-AYNI olmalı."""
    _e0, _tp0, det0 = _besleme(overrides={'engine_cycle': cyc})
    e1, _tp1, det1 = _besleme(overrides={'engine_cycle': cyc,
                                         'generator_gas_temp': kotu})
    assert _cevrim_imzasi(det1) == _cevrim_imzasi(det0), (
        f'{cyc}: reddedilen generator_gas_temp={kotu} yanıtı değiştiriyor')
    assert ({'warn.liquid.input_out_of_range',
             'warn.liquid.input_not_a_number'} & _kodlar(e1)), (
        'reddedilen girdi için uyarı çıkmıyor')


@pytest.mark.parametrize('cyc', ['gas_generator', 'staged_combustion'])
def test_p3b3_05_reddedilen_turbin_pr_yaniti_degistirmez(cyc):
    _e0, _tp0, det0 = _besleme(overrides={'engine_cycle': cyc})
    _e1, _tp1, det1 = _besleme(
        overrides={'engine_cycle': cyc, 'turbine_expansion_ratio': 999})
    assert _cevrim_imzasi(det1) == _cevrim_imzasi(det0), (
        f'{cyc}: reddedilen turbine_expansion_ratio yanıtı değiştiriyor')


def test_p3b3_05_kabul_edilen_tit_yaniti_DEGISTIRIR():
    """Karşı kontrol: doğru girdi hâlâ sonuca giriyor (körleşmedik)."""
    _e0, _tp0, det0 = _besleme(overrides={'engine_cycle': 'gas_generator'})
    _e1, _tp1, det1 = _besleme(overrides={'engine_cycle': 'gas_generator',
                                          'generator_gas_temp': 1600})
    assert det1['turbopump_analysis']['turbine']['inlet_temperature'] == (
        pytest.approx(1600.0, rel=1e-6))
    assert _cevrim_imzasi(det1) != _cevrim_imzasi(det0)


def test_p3b3_05_reddedilen_girdi_kunyesi_user_input_demez():
    _e, _tp, det = _besleme(overrides={'engine_cycle': 'gas_generator',
                                       'generator_gas_temp': 99999})
    b = det['turbopump_analysis']['turbine']
    assert b['inlet_temperature_input_status'] == 'rejected'
    assert 'REJECTED' in str(b['inlet_temperature_input_basis'])
    assert not str(b['inlet_temperature_source']).startswith('user input (')
    # Karşı kontrol: kabul edilen girdi 'accepted', gönderilmeyen
    # 'not_supplied' der — alan üç durumu AYIRT eder.
    _e2, _tp2, det2 = _besleme(overrides={'engine_cycle': 'gas_generator',
                                          'generator_gas_temp': 1600})
    assert (det2['turbopump_analysis']['turbine']
            ['inlet_temperature_input_status'] == 'accepted')
    _e3, _tp3, det3 = _besleme(overrides={'engine_cycle': 'gas_generator'})
    assert (det3['turbopump_analysis']['turbine']
            ['inlet_temperature_input_status'] == 'not_supplied')


# =====================================================================
# P3B3-06 — LH2 yakıt tankı KARBON ÇELİĞİ (A36) olarak boyutlanıp PASS
# ÖLÇÜLDÜ (250 kN LH2/LOX): material='Carbon steel (generic, A36-class)',
# material_key='steel', tank_mass 2710,20 kg, pressure_vessel PASS,
# sıfır uyarı — fonksiyonun kendi yorumu ise '316L' diyordu.
# =====================================================================
#: ÖH D36 / LU-1 (ÇEVRİLEN BEKÇİ, onemli2-sivi a2): motor yanma süresini
#: ARTIK VARSAYMAZ; süre verilmezse ``_design_propellant_tanks`` tank
#: kartını ``not_modelled`` döndürür. P3B3-06 bekçileri (5 düğüm) tank
#: malzemesinin kriyojenik taramasını ölçer, yani SÜRESİ VERİLMİŞ bir
#: tasarımı; süre motorun kendi sabitinden AÇIKÇA verilir (sayı burada
#: yazılmaz), sayılar LU-1 öncesindeki sessiz varsayımla birebir aynıdır.
SURE = {'max_burn_duration': BURN_TIME_DEFAULT_S}


def _tanklar(**kw):
    e = _motor(overrides=dict(SURE, **kw.pop('overrides', {})), **kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        e.calculate_nozzle_geometry()
        return e, e._design_propellant_tanks()


def test_p3b3_06_lh2_tanki_karbon_celik_degil():
    e, tanks = _tanklar(fuel_type='lh2', mixture_ratio=6.0,
                        chamber_pressure=200)
    st = tanks['fuel_tank']['structural']
    assert st['material_key'] != 'steel', (
        'LH2 tankı hâlâ karbon çelik (A36) ile boyutlanıyor')
    assert st['material_key'] in TANK_CRYO_SUITABLE_MATERIALS
    assert st['cryogenic_suitability']['verdict'] == 'pass'
    assert st['material_source']


@pytest.mark.parametrize('yakit,mr', [('lh2', 6.0), ('methane', 3.4),
                                      ('rp1', 2.5)])
def test_p3b3_06_kriyojenik_tarama_her_tankta_yayimlanir(yakit, mr):
    e, tanks = _tanklar(fuel_type=yakit, mixture_ratio=mr,
                        chamber_pressure=200)
    for ad, itici in (('fuel_tank', yakit), ('oxidizer_tank', 'lox')):
        tar = tanks[ad]['structural']['cryogenic_suitability']
        assert tar['verdict'] in ('pass', 'fail', 'not_required')
        assert tar['propellant_is_cryogenic'] == (
            itici in CRYOGENIC_PROPELLANTS)
        assert tar['basis']


def test_p3b3_06_uygunsuz_malzeme_sessiz_gecmez():
    """Çağıran karbon çeliği dayatırsa hüküm 'fail' ve KRİTİK uyarı çıkar."""
    e = _motor(fuel_type='lh2', mixture_ratio=6.0, chamber_pressure=200,
               overrides=dict(SURE))
    e.fuel_tank_material = 'steel'
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        e.calculate_nozzle_geometry()
        tanks = e._design_propellant_tanks()
    tar = tanks['fuel_tank']['structural']['cryogenic_suitability']
    assert tar['verdict'] == 'fail'
    assert 'warn.liquid.tank_material_not_cryogenic' in _kodlar(e)


# =====================================================================
# P3B4-01 — blade_tip_speed yayımlanan türbine ait değil
# ÖLÇÜLDÜ: tek kademeli kestirim BEŞ farklı motorda bit-aynı 615,4852 m/s
# (yerel varsayımlardan: 1200 K / PR 8,5) ve uç hızı uyarısı 6/6 koşuda
# ateşliyordu — bilgi taşımayan sabit alarm.
# =====================================================================
P3B4_VAKALAR = [
    ('rp1_25kN', dict(thrust=25000, chamber_pressure=70)),
    ('rp1_250kN', dict(thrust=250000, chamber_pressure=200)),
    ('lh2_250kN', dict(thrust=250000, chamber_pressure=200,
                       fuel_type='lh2', mixture_ratio=6.0)),
    ('rp1_1MN', dict(thrust=1000000, chamber_pressure=200)),
    ('ch4_50kN', dict(thrust=50000, chamber_pressure=100,
                      fuel_type='methane', mixture_ratio=3.4)),
]


def test_p3b4_01_tek_kademeli_kestirim_motora_gore_degisir():
    degerler = []
    for _ad, kw in P3B4_VAKALAR:
        _e, _tp, det = _besleme(**kw)
        degerler.append(round(float(det['turbopump_analysis']['turbine']
                                    ['blade_speed_single_stage_optimum_m_s']),
                              4))
    assert len(set(degerler)) > 1, (
        f'tek kademeli uç hızı kestirimi hâlâ sabit: {degerler}')


@pytest.mark.parametrize('ad,kw', P3B4_VAKALAR)
def test_p3b4_01_kestirim_cozulen_turbinin_isinden_turer(ad, kw):
    """U = (U/C0)·sqrt(2·Δh_ideal) özdeşliği kartın KENDİ sayılarıyla."""
    _e, _tp, det = _besleme(**kw)
    b = det['turbopump_analysis']['turbine']
    dh_ideal = b.get('ideal_specific_work_J_kg')
    if dh_ideal is None:
        pytest.skip(f'{ad}: çevrim kapanmadı, kartın yerel kestirimi geçerli')
    beklenen = TURBINE_VELOCITY_RATIO * (2.0 * float(dh_ideal)) ** 0.5
    assert b['blade_speed_single_stage_optimum_m_s'] == pytest.approx(
        beklenen, rel=1e-9)
    # Δh_ideal gerçekten İDEAL iştir: gerçek iş = ideal x verim.
    assert float(b['specific_work_J_kg']) == pytest.approx(
        float(dh_ideal) * float(b['efficiency']), rel=1e-6)


def test_p3b4_01_uc_hizi_uyarisi_ayirt_edicidir():
    """Uyarı her koşuda çıkan sabit alarm olamaz: yayımlanan çevre hızı
    sınırın altındaysa ATEŞLENMEZ, üstündeyse ATEŞLENİR."""
    ateslenen = 0
    for ad, kw in P3B4_VAKALAR:
        e, _tp, det = _besleme(**kw)
        u = det['turbopump_analysis']['turbine']['blade_tip_speed']
        var = 'warn.liquid.turbine_tip_speed_exceeded' in _kodlar(e)
        assert var == (float(u) > TURBINE_TIP_SPEED_LIMIT_MS), (
            f'{ad}: yayımlanan uç hızı {u:.1f} m/s ile uyarı durumu '
            f'({var}) tutmuyor')
        ateslenen += int(var)
    # ÖH D15 birleştirme (ana model, 1 Eyl 2026): 'hepsinde ateşlemesin' sezgisi
    # kulvar worktree'sinde rp1_25kN'nin 114,5 m/s değerine yaslanıyordu; o
    # değer yapisal-sistem a2 P5B3-04'ün kapattığı DEJENERE ÇAP (kademe tavanı
    # → u_pitch = u_env) kusurunun ürünüymüş. Birleşmiş ağaçta yayımlanan sayı
    # dürüst tek-kademe optimumu (752 m/s) ve RP-1 gaz jeneratörü koşullarında
    # tek kademe 2-25-250 kN'nin HEPSİNDE 500 m/s sınırını aşar (ölçüldü:
    # 740-775 m/s) — alarm sabit değil, "tek kademe yetmez" bilgisidir. Ayırt
    # edicilik yukarıdaki vaka-başına eşitlikle sınanıyor; burada yalnız alarmın
    # ÇALIŞTIĞI (en az bir vakada ateşlediği) kilitlenir.
    # ÖH D15 fix-4 (ana model, 1 Eyl 2026 — Fable sıvı denetimi, P3B4-01 ŞART):
    # d15fix/sivi-turbin (821a1ff) kartı boyutlandırmanın pitch hızına bağladı;
    # birleşik ağaçta ölçüm 3/5 (rp1_25kN 114,49 ve rp1_1MN 178,26 m/s sized
    # pitch hızı uyarısız). 'en az bir' gevşemesi artık gereksiz ve zayıf:
    # alarm hem ÇALIŞMALI hem SABİT OLMAMALI.
    # ÖH D18 fizik-a2 (F3) ÇEVİRİSİ: 'en az bir vakada ateşlesin' toplamı
    # SABİT 3,0 bar tank basıncına yaslanıyordu — pompa basma yüksekliği ve
    # dolayısıyla türbin işi o sabitten geliyordu. Tank basıncı artık NPSH
    # gereksiniminden boyutlanıyor; ölçüldü ki beş vakanın BEŞİNDE de
    # yayımlanan uç hızı 109-178 m/s, yani 500 m/s sınırının çok altında
    # (2 MN ve LH2 1 MN'de bile 198 m/s). Alarmın ateşlemediği bir dünya
    # KUSUR DEĞİL, sağlıklı tasarımdır.
    #
    # 'Ayırt edicilik' iddiası ZAYIFLAMADI, doğru yere taşındı:
    #   (1) vaka başına EŞİTLİK (yukarıda) — uyarı ancak ve ancak sınır
    #       aşıldığında çıkar; beş vakada da tutuyor;
    #   (2) kanalın CANLI olduğu, sınırı ölçülen değerin altına indirerek
    #       doğrudan sınanır (aşağıda). Böylece 'kanal kopuk' hâli hâlâ
    #       kırmızı verir ama sağlıklı tasarım artık testi düşürmez.
    assert ateslenen == 0 or ateslenen < len(P3B4_VAKALAR), (
        f'uyarı {ateslenen}/{len(P3B4_VAKALAR)} vakanın HEPSİNDE ateşledi: '
        'sabit alarm (ayırt edici değil)')


def test_p3b4_01_uc_hizi_kanali_canli(monkeypatch):
    """Uyarı kanalı kopuk değil: sınır ölçülenin altına inince ateşler.

    ÖH D18 fizik-a2 (F3): sağlıklı tasarımda hiçbir vaka 500 m/s sınırını
    aşmıyor, bu yüzden 'en az bir vaka ateşlesin' toplamı artık kanalın
    canlılığını ölçemiyordu. Kanal burada DOĞRUDAN ölçülür.
    """
    ad, kw = P3B4_VAKALAR[3]          # rp1_1MN — en büyük çevre hızı
    e, _tp, det = _besleme(**kw)
    u = float(det['turbopump_analysis']['turbine']['blade_tip_speed'])
    assert u > 0.0
    assert 'warn.liquid.turbine_tip_speed_exceeded' not in _kodlar(e), (
        f'{ad}: {u:.1f} m/s sınırın altındayken uyarı çıkmış')

    import hrma.engines.liquid_rocket_engine as _LRE
    monkeypatch.setattr(_LRE, 'TURBINE_TIP_SPEED_LIMIT_MS', u * 0.5)
    e2, _tp2, _det2 = _besleme(**kw)
    assert 'warn.liquid.turbine_tip_speed_exceeded' in _kodlar(e2), (
        f'{ad}: sınır {u * 0.5:.1f} m/s yapıldığı hâlde {u:.1f} m/s uç '
        'hızı uyarı üretmedi — uyarı kanalı kopuk')


# =====================================================================
# P3B4-03 — power_margin ideal-iş sınırını GERÇEK işe bölüyor
# ÖLÇÜLDÜ (250 kN / Pc 200): yayımlanan marj −%29,86; ideal/ideal −%54,41
# — 24,55 PUAN İYİMSER. 25 kN'da −%31,94 ⟷ −%55,76 (23,82 puan).
# =====================================================================
@pytest.mark.parametrize('ad,kw', [
    ('rp1_250kN', dict(thrust=250000, chamber_pressure=200)),
    ('rp1_25kN', dict(thrust=25000, chamber_pressure=70)),
    ('staged_250kN', dict(thrust=250000, chamber_pressure=200,
                          overrides={'engine_cycle': 'staged_combustion'})),
])
def test_p3b4_03_power_margin_ideal_ise_bolunur(ad, kw):
    _e, _tp, det = _besleme(**kw)
    m = det['performance_margins']
    b = det['turbopump_analysis']['turbine']
    dh_limit = (TURBINE_TIP_SPEED_LIMIT_MS / TURBINE_VELOCITY_RATIO) ** 2 / 2.0
    dh_ideal = m['power_margin_specific_work_J_kg']
    assert dh_ideal is not None
    assert m['power_margin'] == pytest.approx(
        (dh_limit / float(dh_ideal) - 1.0) * 100.0, rel=1e-9)
    # Payda GERÇEK iş DEĞİLDİR: gerçek iş ideal x verim olduğundan ikisi
    # verim kadar ayrışır ve marj 1/eta katı iyimser okunurdu.
    dh_real = float(b['specific_work_J_kg'])
    eta = float(b['efficiency'])
    if eta < 0.999:
        assert float(dh_ideal) > dh_real * 1.001, (
            f'{ad}: power_margin hâlâ gerçek işe bölünüyor')


def test_p3b4_03_marjin_paydasi_adiyla_yayimlanir():
    _e, _tp, det = _besleme(thrust=250000, chamber_pressure=200)
    m = det['performance_margins']
    assert m['power_margin_specific_work_source']
    assert 'IDEAL' in str(m['power_margin_basis'])
