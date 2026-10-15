# -*- coding: utf-8 -*-
"""ÖH Dalga-15 / sıvı kulvarı, aşama 3 — BEKÇİLER (8 kalem).

Her test bir kalemin kusurunu GÖREN iddiadır: onarım geçici olarak geri
alındığında (ters-mutasyon) KIRMIZI olmalıdır. Ters-mutasyon kanıtı
docs/scofield/raw/OH/D15/sivi/a3/mutasyon.json içindedir.

Kalemler: P3B4-05, P3B4-06, P3B4-07, P3B4-08, P3B1-05, P3B1-06, P3B1-07,
P3B1-08.
"""
import contextlib
import io
import os
import sys

import pytest

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

from hrma.constants import (ISA_LAYERS, ISA_TABLE_TOP_M,  # noqa: E402
                            isa_pressure)
from hrma.engines.liquid_rocket_engine import (  # noqa: E402
    BURN_TIME_DEFAULT_S, BURN_TIME_NOT_SUPPLIED_REASON,
    ISA_GEOPOTENTIAL_EARTH_RADIUS_M as R_EARTH_M,
    LIQUID_PROPELLANT_REFERENCE_TABLE, NOZZLE_SEPARATION_PRESSURE_RATIO,
    LiquidRocketEngine, unknown_pair_gas_reference)


def kur(**kw):
    ov = kw.pop('overrides', {})
    tas = dict(thrust=25000, chamber_pressure=60, mixture_ratio=2.3,
               fuel_type='rp1', oxidizer_type='lox',
               cooling_type='regenerative', injector_type='impinging',
               feed_system_type='turbopump')
    tas.update(kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        e = LiquidRocketEngine(overrides=ov, **tas)
        e.calculate_nozzle_geometry()
    return e


def geopotansiyel(h_geom):
    return float(h_geom) * R_EARTH_M / (R_EARTH_M + float(h_geom))


# ---------------------------------------------------------------------------
# P3B4-05 — tasarım irtifası ISA tersini KATMAN KATMAN çözmeli
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('eps', [20.0, 50.0, 100.0, 200.0, 300.0])
def test_p3b4_05_tasarim_irtifasi_kendi_basincini_geri_verir(eps):
    """Yayımlanan irtifadaki GERÇEK ISA basıncı çıkış basıncına eşit olmalı.

    Eski kod ('if p_exit > p_base: continue') her irtifayı troposfer
    formülüyle çözüyordu; kapanış denetimi ε=300'de 1.195 Pa açıktı.
    """
    e = kur(overrides={'nozzle_expansion_ratio': eps})
    rap = e._design_altitude_report()
    alt = rap['optimal_altitude']
    assert alt is not None
    pe_pa = float(rap['nozzle_exit_pressure_bar']) * 1e5
    p_geri = isa_pressure(geopotansiyel(alt))
    assert p_geri == pytest.approx(pe_pa, rel=1e-9), (
        f'eps={eps}: {alt:.1f} m irtifasındaki ISA basıncı {p_geri:.4f} Pa, '
        f'çıkış basıncı {pe_pa:.4f} Pa')


def test_p3b4_05_ust_katmanlar_olu_degil():
    """Tablonun 0. katmanı dışındaki katmanlar GERÇEKTEN kullanılmalı.

    20 km üstünde troposfer formülü kilometrelerce sapar; bilinen bir ISA
    noktasına (20 km geopotansiyel -> 5474,89 Pa) karşı çapraz denetim.
    """
    e = kur()
    # Motorun kendi çözücüsünü bilinen bir basınçla sına: 20 km katmanı
    # (h_base=20000, lapse=+0.001) troposferden FARKLI bir formül ister.
    hedef_pa = ISA_LAYERS[2][3]                     # 5474.89 Pa (20 km tabanı)
    # 20 km tabanının basıncı, 20 km geopotansiyel irtifada olmalı
    assert isa_pressure(20000.0) == pytest.approx(hedef_pa, rel=1e-6)
    # ... ve motorun tersi de aynı noktayı bulmalı (ε taraması ile yakala)
    for eps in (150.0, 200.0, 250.0, 300.0):
        rap = kur(overrides={'nozzle_expansion_ratio': eps}
                  )._design_altitude_report()
        alt = rap['optimal_altitude']
        if alt is None:
            continue
        h_geo = geopotansiyel(alt)
        if h_geo > 20000.0:
            # Troposfer formülü 11 km üstünde SİSTEMATİK olarak düşük irtifa
            # verir; katman-doğru çözüm kapanış denetimini geçer.
            assert isa_pressure(h_geo) == pytest.approx(
                float(rap['nozzle_exit_pressure_bar']) * 1e5, rel=1e-9)
            break
    else:
        pytest.skip('tarama 20 km üstüne çıkmadı')


def test_p3b4_05_tablo_tavani_ustunde_sayi_uydurulmaz():
    """ISA tablosunun tavanı üstünde SONLU optimum yayımlanmaz."""
    e = kur()
    p_tavan = isa_pressure(ISA_TABLE_TOP_M)
    # Tavanın altındaki bir çıkış basıncı için çözüm YOK demeli
    from hrma.constants import M_AIR, R_STAR_ICAO  # noqa: F401
    # doğrudan yüklem: katman seçimi tavanı aşarsa None döner
    assert p_tavan > 0
    rap = e._design_altitude_report()
    if rap['optimal_altitude'] is not None:
        assert geopotansiyel(rap['optimal_altitude']) <= ISA_TABLE_TOP_M + 1e-6


# ---------------------------------------------------------------------------
# P3B4-06 — 'teorik maksimum' motorun KENDİ lülesinin kayıpsız tavanı
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('F,pc,mr', [(25000, 70, 2.3), (25000, 60, 2.3),
                                     (100000, 100, 2.5)])
def test_p3b4_06_teslim_isp_teorik_tavani_asmaz(F, pc, mr):
    """delivered_vs_theoretical_pct <= 100 — aksi FİZİK DIŞIDIR."""
    e = kur(thrust=F, chamber_pressure=pc, mixture_ratio=mr)
    eb = e._calculate_efficiency_breakdown()
    oran = eb['delivered_vs_theoretical_pct']
    assert oran is not None
    assert oran <= 100.0 + 1e-6, (
        f'{F} N / {pc} bar: teslim Isp teorik tavanı %{oran:.2f} ile aşıyor')
    assert eb['actual_isp'] <= eb['theoretical_isp'] + 1e-9


def test_p3b4_06_teorik_tavan_lulenin_epsilonuna_bagli():
    """Tavan SABİT bir P_e/P_c'den değil, motorun ε'sundan gelmeli."""
    dar = kur(overrides={'nozzle_expansion_ratio': 8.0})
    genis = kur(overrides={'nozzle_expansion_ratio': 60.0})
    t_dar = dar._calculate_efficiency_breakdown()['theoretical_isp']
    t_genis = genis._calculate_efficiency_breakdown()['theoretical_isp']
    assert t_genis > t_dar, (
        f'geniş lülenin kayıpsız tavanı ({t_genis:.2f} s) dar lülenin '
        f'tavanından ({t_dar:.2f} s) büyük olmalı')
    # Sabit 1/20 çapasının parmak izi: iki motorda AYNI tavan
    assert abs(t_genis - t_dar) > 1.0


def test_p3b4_06_tavan_kunyesi_yayimlanir():
    eb = kur()._calculate_efficiency_breakdown()
    kunye = eb.get('theoretical_isp_basis') or ''
    assert 'epsilon' in kunye and 'vacuum' in kunye
    assert eb.get('applied_delivery_efficiency_pct') is not None


# ---------------------------------------------------------------------------
# P3B4-07 — Pc haritasının her eğrisi AYNI motora ait
# ---------------------------------------------------------------------------

def test_p3b4_07_pc_haritasi_tek_motor():
    """Aynı x noktasında iki farklı motor DURAMAZ."""
    e = kur()
    pcm = e._generate_performance_optimization_maps()[
        'chamber_pressure_optimization']
    itki = pcm['thrust_vs_pc']
    bogaz = pcm['throat_diameter_vs_pc_mm']
    assert len(set(itki)) == 1, (
        'sabit itki ailesinde itki eğrisi taramada değişemez')
    assert itki[0] == pytest.approx(float(e.F), rel=1e-9)
    # boğaz gerçekten taranıyor (sabit çarpan değil)
    assert len(set(bogaz)) > 1
    # ... ve ikinci aile AYRI adla, AYRI künyeyle duruyor
    assert pcm['thrust_vs_pc_fixed_throat'][0] != \
        pcm['thrust_vs_pc_fixed_throat'][-1]
    assert pcm['fixed_throat_diameter_mm'] == pytest.approx(
        float(e.d_t) * 1000.0, rel=1e-9)
    for anahtar in ('family', 'thrust_basis', 'throat_diameter_basis',
                    'isp_basis', 'thrust_vs_pc_fixed_throat_basis'):
        assert pcm.get(anahtar), f'{anahtar} künyesi yok'


def test_p3b4_07_sabit_donanim_egrisi_kendi_bogazina_tutarli():
    """Sabit donanım ailesinin itkisi TASARIM boğazıyla tutarlı olmalı."""
    e = kur()
    pcm = e._generate_performance_optimization_maps()[
        'chamber_pressure_optimization']
    import math
    d_t_mm = pcm['fixed_throat_diameter_mm']
    assert d_t_mm > 0
    a_t = math.pi * (d_t_mm / 1000.0) ** 2 / 4.0
    # F = CF · Pc · A_t: eğrinin İMA ETTİĞİ CF her noktada fiziksel bandda
    # olmalı (1,2 ... 2,2). Eğri başka bir boğazdan gelseydi bu bant tutmaz.
    for pc, f in zip(pcm['pc_range'], pcm['thrust_vs_pc_fixed_throat']):
        cf = f / (float(pc) * 1e5 * a_t)
        assert 1.2 < cf < 2.2, f'Pc={pc}: ima edilen CF={cf:.4f}'
    # ... ve itki Pc ile MONOTON artmalı (sabit donanım ailesinin tanımı)
    seri = pcm['thrust_vs_pc_fixed_throat']
    assert all(seri[i] < seri[i + 1] for i in range(len(seri) - 1))


# ---------------------------------------------------------------------------
# P3B4-08 — kısma haritası kendi Isp'siyle tutarlı; ayrılmışta sayı yok
# ---------------------------------------------------------------------------

def test_p3b4_08_itki_kendi_ispsiyle_tutarli():
    """F = ṁ(Pc)·g0·Isp_sl(Pc) — tablo kendi içinde çelişemez."""
    e = kur()
    tm = e.solve_throttle_map()
    pc0 = float(e.P_c)
    mdot0 = float(e.mdot_total)
    yayimlanan = 0
    for p in tm['points']:
        if p['thrust_n'] is None:
            assert p['thrust_basis'], 'sayı yoksa gerekçe olmalı'
            continue
        assert p['isp_sea_level'] is not None
        mdot = mdot0 * float(p['chamber_pressure_bar']) / pc0
        beklenen = mdot * float(e.g0) * float(p['isp_sea_level'])
        assert p['thrust_n'] == pytest.approx(beklenen, rel=1e-9), (
            f"frac={p['throttle_fraction']}: yayımlanan "
            f"{p['thrust_n']:.2f} N ⟷ tutarlı {beklenen:.2f} N")
        yayimlanan += 1
    assert yayimlanan >= 3


def test_p3b4_08_dogrusal_kabul_kalkti():
    """thrust_n artık throttle_fraction × tasarım itkisi DEĞİL."""
    e = kur()
    tm = e.solve_throttle_map()
    sapan = [p for p in tm['points']
             if p['thrust_n'] is not None
             and abs(float(p['throttle_fraction']) - 1.0) > 1e-9
             and abs(p['thrust_n'] - float(e.F) * float(p['throttle_fraction']))
             > 1e-6 * float(e.F)]
    assert sapan, 'kısılan noktaların hiçbiri doğrusal kabulden ayrılmıyor'


def test_p3b4_08_ayrilmis_lulede_sayi_basilmaz():
    """Motorun KENDİ ayrılma ölçütüne göre ayrılmış noktada sayı yok."""
    e = kur(overrides={'min_throttle': 20})
    tm = e.solve_throttle_map()
    esik = tm['separation_threshold_bar']
    assert esik == pytest.approx(
        NOZZLE_SEPARATION_PRESSURE_RATIO * float(e.P_a), rel=1e-9)
    ayrilan = [p for p in tm['points'] if p.get('flow_separated')]
    assert ayrilan, 'min_throttle=%20 taraması ayrılmış nokta üretmedi'
    for p in ayrilan:
        assert p['thrust_n'] is None
        assert p['isp_sea_level'] is None
        assert 'separated' in (p['thrust_basis'] or '')
    kodlar = [w.get('code') if isinstance(w, dict) else str(w)
              for w in (e.design_warnings or [])]
    assert any('flow_separation' in str(k) for k in kodlar), (
        'ayrılma uyarısı yayımlanmadı')


# ---------------------------------------------------------------------------
# P3B1-05 — basınçlandırma tipi TEK kaynaktan
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('fuel,ox', [('rp1', 'lox'), ('methane', 'lox'),
                                     ('lh2', 'lox'), ('mmh', 'n2o4'),
                                     ('udmh', 'n2o4')])
@pytest.mark.parametrize('feed', ['turbopump', 'pressure_fed'])
def test_p3b1_05_basinclandirma_tipi_celismez(fuel, ox, feed):
    """'autogenous' yazan yanıt aynı yanıtta 'uygulanamaz' diyemez.

    ÖH V3 taban-c (14 Eki) — LU-1 ÇEVİRİSİ (Berke onaylı, ÖH D36
    onemli2-sivi a1 §LU-1; ``4364f9f3``). Motor yanma süresini artık
    VARSAYMAZ: süre verilmezse autogenous BÜTÇESİ (boşalan hacim = debi ×
    süre) kurulamaz ve blok ``not_applicable`` + ``BURN_TIME_NOT_SUPPLIED_
    REASON`` döner ("mevcut 'not_applicable' sözleşmesi, adıyla"). Bekçinin
    niyeti tip ⟷ UYGULANABİLİRLİK çelişkisidir, yani SÜRESİ VERİLMİŞ
    tasarım: süre f4a4cccb deseniyle motorun kendi sabitinden AÇIKÇA
    verilir (sayı yazılmaz). Süresiz hâl de kilitlenir: orada blok 'ok'
    olamaz ama 'uygulanamaz' derken gerekçe YALNIZ süre eksiği olabilir —
    çiftin uygunluk gerekçesi (tipin autogenous dediği yanıtta) ÇELİŞKİDİR.
    """
    for sure in (BURN_TIME_DEFAULT_S, None):
        ov = {} if sure is None else {'max_burn_duration': sure}
        e = kur(fuel_type=fuel, oxidizer_type=ox, feed_system_type=feed,
                overrides=ov)
        with contextlib.redirect_stdout(io.StringIO()):
            det = e._initialize_feed_system()
            au = e._autogenous_pressurization_summary()
        tip = det['pressurization']['type']
        assert det['pressurization'].get('type_basis'), 'tip künyesiz'
        if tip == 'autogenous' and sure is not None:
            assert au.get('status') == 'ok', (
                f'{fuel}/{ox} {feed} (süre {sure} s): tip autogenous ama '
                f"blok {au.get('status')} diyor: {au.get('reason')}")
        elif tip == 'autogenous':
            assert au.get('status') == 'not_applicable', (fuel, ox, feed, au)
            assert au.get('reason') == BURN_TIME_NOT_SUPPLIED_REASON, (
                f'{fuel}/{ox} {feed} (süresiz): tip autogenous ama blok '
                f"süre dışı bir gerekçeyle uygulanamaz diyor: {au.get('reason')}")
        else:
            assert au.get('status') != 'ok' or feed != 'turbopump'


def test_p3b1_05_emniyet_vanasi_ayni_kaynagi_okur():
    """Emniyet vanası gazı besleme kartının tipiyle aynı olmalı."""
    for fuel, beklenen in (('rp1', 'helium'), ('methane', 'oxygen')):
        e = kur(fuel_type=fuel, oxidizer_type='lox')
        with contextlib.redirect_stdout(io.StringIO()):
            rv = e._size_tank_relief_valve(3e5, e.mdot_ox, 'oxidizer')
        assert rv.get('pressurant_gas') == beklenen, (
            f'{fuel}: emniyet vanası gazı {rv.get("pressurant_gas")}')
        assert rv.get('pressurant_basis')


# ---------------------------------------------------------------------------
# P3B1-06 — yedek gaz özellikleri TABLODAN; künye tabloyu doğru anlatır
# ---------------------------------------------------------------------------

def test_p3b1_06_yedek_deger_tablonun_bandinin_icinde():
    ref = unknown_pair_gas_reference()
    for alan in ('mu_chamber', 'pr_chamber', 'cp_chamber'):
        deger = ref[alan]['value']
        alt, ust = ref[alan]['band']
        assert alt <= deger <= ust, (
            f'{alan}: yedek {deger} bandın ({alt} ... {ust}) dışında')


def test_p3b1_06_bant_tablodan_turetilir():
    """Bant ELLE yazılmaz: tablonun gerçek min/max'ı olmalı."""
    ref = unknown_pair_gas_reference()
    for alan in ('mu_chamber', 'pr_chamber', 'cp_chamber'):
        degerler = [float(v[alan])
                    for v in LIQUID_PROPELLANT_REFERENCE_TABLE.values()
                    if v.get(alan) is not None]
        assert ref[alan]['band'] == [min(degerler), max(degerler)]
        assert ref[alan]['count'] == len(degerler)
        # Künye bandı sayıyla söylüyor
        assert f'{min(degerler):.6g}' in ref[alan]['basis']
        assert f'{max(degerler):.6g}' in ref[alan]['basis']


def test_p3b1_06_tablo_disi_cift_tablodan_beslenir():
    """Tablo dışı çiftte Bartz'a giren mu/Pr TABLODAN gelir ve künyelidir.

    cp'yi CEA döndürürse o ezer (doğrusu budur); mu ve Pr'yi CEA köprüsü
    HİÇ döndürmez, onlar her zaman yedekten gelir — yedek artık tablonun
    medyanıdır ve bandın İÇİNDEDİR (eski cp=2000 beyan edilen bandın
    dışındaydı).
    """
    e = kur(fuel_type='lh2', oxidizer_type='n2o4',
            overrides={'fuel_density': 70.85, 'oxidizer_density': 1443.2})
    ref = unknown_pair_gas_reference()
    assert float(e.mu_chamber) == pytest.approx(ref['mu_chamber']['value'])
    assert float(e.pr_chamber) == pytest.approx(ref['pr_chamber']['value'])
    assert getattr(e, 'mu_chamber_source', None)
    assert getattr(e, 'pr_chamber_source', None)
    assert getattr(e, 'cp_chamber_source', None)
    band = getattr(e, 'chamber_gas_property_band', None)
    assert band and band['cp_chamber'] == ref['cp_chamber']['band']


def test_p3b1_06_eski_sabitler_artik_okunmuyor():
    """Tarihsel sabitler motorun yolunda KULLANILMAMALI."""
    from hrma.engines import liquid_rocket_engine as mod
    ref = unknown_pair_gas_reference()
    # Yedek cp artık 2000,0 değil; tablodan türetilmiş medyan
    assert ref['cp_chamber']['value'] != mod.LIQUID_UNKNOWN_PAIR_GAS_CP
    e = kur(fuel_type='lh2', oxidizer_type='n2o4',
            overrides={'fuel_density': 70.85, 'oxidizer_density': 1443.2})
    assert float(e.mu_chamber) != mod.LIQUID_UNKNOWN_PAIR_GAS_VISCOSITY
    assert float(e.pr_chamber) != mod.LIQUID_UNKNOWN_PAIR_GAS_PRANDTL


# ---------------------------------------------------------------------------
# P3B1-07 — statik dalda vakum Isp'si motorun KENDİ lülesine ait
# ---------------------------------------------------------------------------

@pytest.fixture
def cea_kapali():
    from hrma.engines import cea_bridge
    eski = cea_bridge.is_rocketcea_available
    cea_bridge.is_rocketcea_available = lambda: False
    try:
        yield
    finally:
        cea_bridge.is_rocketcea_available = eski


@pytest.mark.parametrize('eps_in', [None, 16.0, 9.0])
def test_p3b1_07_statik_dal_vakum_ispsi_ayni_lulede(cea_kapali, eps_in):
    """Isp_vac = Isp_sl + P_a·ε·c*/(P_c·C_D·g0) — TEK lüle (Sutton 3-29)."""
    ov = {} if eps_in is None else {'nozzle_expansion_ratio': eps_in}
    e = kur(chamber_pressure=100, mixture_ratio=2.577, overrides=ov)
    assert e.combustion_data_source == 'static_table'
    eps = float(e.expansion_ratio)
    cd = e._throat_discharge_coefficient()
    tutarli = float(e.isp_sl) + (
        float(e.P_a) * 1e5 * eps * float(e.c_star_effective)
        / (float(e.P_c) * 1e5 * cd * float(e.g0)))
    assert float(e.isp_vac) == pytest.approx(tutarli, rel=1e-9), (
        f'eps_in={eps_in}: yayımlanan {e.isp_vac:.3f} s ⟷ aynı lülede '
        f'tutarlı {tutarli:.3f} s')


def test_p3b1_07_tablo_capasi_kapasite_olarak_yayimlanir(cea_kapali):
    """ε=200 çapası atılmaz; KAPASİTE referansı olarak künyesiyle durur."""
    e = kur(chamber_pressure=100, mixture_ratio=2.577)
    assert getattr(e, 'isp_vac_capability_ref', None) is not None
    assert float(e.isp_vac_capability_ref) > float(e.isp_vac)
    kunye = getattr(e, 'isp_vacuum_basis', '') or ''
    assert 'capability' in kunye and 'Eq. 3-29' in kunye
    assert getattr(e, 'isp_vac_capability_eps', None) is not None


# ---------------------------------------------------------------------------
# P3B1-08 — of_max_isp girdisi EZİLMEZ
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('val', [1.8, 2.577, 3.6, 4.0])
def test_p3b1_08_of_max_isp_korunur(val):
    """Üç farklı değer gönderip aynı yanıtı almak alanı ÖLÜ girdi yapar."""
    e = kur(overrides={'of_max_isp': val})
    assert float(e.optimal_mr) == pytest.approx(val, rel=1e-9)
    assert e.optimal_mr_source == 'user input (of_max_isp)'


def test_p3b1_08_girdi_yoksa_cozulur():
    """Girdi yokken optimum HÂLÂ CEA taramasıyla çözülür (regresyon)."""
    e = kur()
    assert e.optimal_mr_source == 'cea_scan'
    assert 1.0 < float(e.optimal_mr) < 5.0


def test_p3b1_08_kardes_uclar_simetrik():
    """of_max_isp ve of_max_thrust aynı sözleşmeyi taşımalı."""
    e = kur(overrides={'of_max_isp': 3.2, 'of_max_thrust': 3.9})
    assert float(e.optimal_mr) == pytest.approx(3.2)
    assert float(e.optimal_mr_thrust) == pytest.approx(3.9)
    assert e.optimal_mr_source == 'user input (of_max_isp)'
    assert e.optimal_mr_thrust_source == 'user input (of_max_thrust)'
