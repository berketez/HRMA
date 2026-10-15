# -*- coding: utf-8 -*-
"""ÖH Dalga-15 / sıvı kulvarı, aşama 1 — onarım bekçileri.

Her test, onarımdan ÖNCE ölçülmüş somut bir kusuru görür. Ters-mutasyon
kanıtı (onarımı geçici geri al -> test KIRMIZI) betikleriyle birlikte
``docs/scofield/raw/OH/D15/sivi/a1/`` altında durur; ölçüm sayıları
``once.json`` (onarım öncesi) ve ``sonra.json`` (sonrası) dosyalarındadır.

Kapsanan kalemler: P3B1-01 (kritik), P3B1-02, P3B1-03, P3B1-04, P3B2-02,
P3B2-03, P3B2-04, P3B2-05.
"""
import contextlib
import io
import math

import pytest

from hrma.engines.liquid_rocket_engine import (
    BURN_TIME_DEFAULT_S, LIQUID_HYPERGOLIC_PAIRS, LiquidRocketEngine)

# liquid.html'in kullanıcıya sunduğu 5 yakıt x 2 oksitleyici
ARAYUZ_CIFTLERI = [(f, o) for f in ('rp1', 'lh2', 'methane', 'mmh', 'udmh')
                   for o in ('lox', 'n2o4')]
# Yerleşik çift tablosunda OLMAYAN, ama arayüzde seçilebilen çiftler
TABLO_DISI_CIFTLER = [('rp1', 'n2o4'), ('lh2', 'n2o4'), ('methane', 'n2o4'),
                      ('mmh', 'lox'), ('udmh', 'lox')]
#: ÖH D36 / LU-1 (ÇEVRİLEN BEKÇİ, onemli2-sivi a2): motor yanma süresini
#: ARTIK VARSAYMAZ; süre verilmezse ``propellant_tanks`` ``not_modelled``
#: döner. P3B1-01 künye bekçileri (6 düğüm) tank kartını ölçer, yani SÜRESİ
#: VERİLMİŞ bir tasarımı; süre motorun kendi sabitinden AÇIKÇA verilir (sayı
#: burada yazılmaz) ve sayılar LU-1 öncesindeki sessiz varsayımla birebir
#: aynıdır. Süre yokken fail-closed hâl: tests/test_d36_sivi_a1.py.
SURE = {'max_burn_duration': BURN_TIME_DEFAULT_S}

# Tablonun KENDİ ölçülen tür yoğunlukları [kg/m3] — kaynak: aynı modüldeki
# combinations sözlüğü (rp1/lox, lh2/lox, mmh/n2o4, udmh/n2o4, methane/lox).
TUR_YOGUNLUK = {'rp1': 815.0, 'lh2': 70.85, 'methane': 422.8, 'mmh': 874.5,
                'udmh': 791.3, 'lox': 1141.7, 'n2o4': 1443.2}


def _motor(**kw):
    ov = kw.pop('overrides', {})
    tas = dict(thrust=25000, chamber_pressure=60, mixture_ratio=2.5,
               fuel_type='rp1', oxidizer_type='lox',
               cooling_type='regenerative', injector_type='impinging')
    tas.update(kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return LiquidRocketEngine(overrides=ov, **tas)


def _kos(**kw):
    e = _motor(**kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return e, e.calculate_performance()


@pytest.fixture(scope='module')
def taban_kosu():
    """25 kN / 60 bar / LOX-RP1, L* = 1,2 m — birden çok bekçinin ortak yükü."""
    return _kos(overrides={'characteristic_length': 1.2})


# ---------------------------------------------------------------------------
# P3B1-01 [kritik] — yoğunluk uydurma sabite düşmez, künye yalan söylemez
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('fuel,oxidizer', TABLO_DISI_CIFTLER)
def test_p3b1_01_tablo_disi_ciftte_yogunluk_uydurulmaz(fuel, oxidizer):
    """Ölçüldü: lh2/n2o4'te rho_fuel 800 (uydurma) ⟷ 70,85 (tablonun kendisi).

    Uydurma sabit tank hacmini 11 kat küçük, hattı 4 kat dar, pompayı 11 kat
    zayıf boyutluyordu — hepsi güvensiz taraf.
    """
    e = _motor(fuel_type=fuel, oxidizer_type=oxidizer)
    assert e.rho_fuel == pytest.approx(TUR_YOGUNLUK[fuel], rel=1e-9), (
        f'{fuel} yakıt yoğunluğu tablonun kendi değeri olmalı')
    assert e.rho_ox == pytest.approx(TUR_YOGUNLUK[oxidizer], rel=1e-9), (
        f'{oxidizer} oksitleyici yoğunluğu tablonun kendi değeri olmalı')
    # Yer tutucu sabitler bir daha ürüne sızmamalı
    assert e.rho_fuel != 800.0 and e.rho_ox != 1200.0


@pytest.mark.parametrize('fuel,oxidizer', TABLO_DISI_CIFTLER)
def test_p3b1_01_kunye_tablo_disi_cifti_tablo_girdisi_gibi_gostermez(
        fuel, oxidizer):
    """Yayımlanan density_source, çift tabloda YOKKEN 'tablodan geldi' diyemez."""
    _e, r = _kos(fuel_type=fuel, oxidizer_type=oxidizer,
                 overrides=dict(SURE))
    for tank in ('fuel_tank', 'oxidizer_tank'):
        kunye = r['propellant_tanks'][tank]['propellant_data']['density_source']
        assert kunye is not None
        assert kunye != 'built-in propellant table', (
            f'{fuel}/{oxidizer} tabloda YOK; {tank} künyesi yine de çiftin '
            f'tablodan geldiğini söylüyor')
        assert 'species' in kunye


def test_p3b1_01_tablo_ici_ciftin_kunyesi_degismedi():
    """Tablodaki çiftte künye eskisi gibi kalır (sözleşme kırılmadı)."""
    _e, r = _kos(overrides=dict(SURE))
    pd = r['propellant_tanks']['fuel_tank']['propellant_data']
    assert pd['density_source'] == 'built-in propellant table'
    assert pd['density'] == pytest.approx(815.0)


# ---------------------------------------------------------------------------
# P3B1-02 — hipergolluk hükmü kimyadan gelir, beyaz listeden değil
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('fuel,oxidizer', ARAYUZ_CIFTLERI)
def test_p3b1_02_atesleme_hukmu_kimyayla_uyumlu(fuel, oxidizer):
    """Ölçüldü: 10 çiftin 8'i 'hypergolic' alıyordu; gerçekte yalnız 2'si.

    LH2/LOX, MMH/LOX, UDMH/LOX, RP-1/N2O4, METHANE/N2O4 hipergolik DEĞİLDİR;
    'hipergolik' hükmü ateşleyici donanımını gereksiz gösterir (güvensiz yön).
    """
    beklenen = (fuel, oxidizer) in LIQUID_HYPERGOLIC_PAIRS
    _e, r = _kos(fuel_type=fuel, oxidizer_type=oxidizer)
    cs = r['feed_system']['control_system']
    assert cs['propellant_hypergolic'] is beklenen
    if beklenen:
        assert cs['ignition_system'] == 'hypergolic'
    else:
        assert cs['ignition_system'] is None, (
            f'{fuel}/{oxidizer} hipergolik değil; ateşleyici donanımı '
            f'modellenmediği hâlde bir hüküm yayımlanıyor')
        assert cs['ignition_system_status'] == 'NOT_MODELLED'
    assert cs['ignition_system_basis']


def test_p3b1_02_lox_hicbir_yakitla_hipergolik_sayilmaz():
    """Sıvı oksijen amin yakıtlarla hipergolik değildir (kimya kilidi)."""
    assert not any(o == 'lox' for _f, o in LIQUID_HYPERGOLIC_PAIRS)


# ---------------------------------------------------------------------------
# P3B1-03 — 50 mm taban kullanıcının oda çapını EZMEZ
# ---------------------------------------------------------------------------
def test_p3b1_03_kucuk_itkide_kullanici_oda_capi_ezilmez():
    """Ölçüldü (500 N / 10 bar): d_c=30 ve d_c=40 girdileri de 50,000 mm
    teslim ediliyordu, üstelik hiçbir uyarı çıkmıyordu."""
    for istenen in (30.0, 40.0):
        _e, r = _kos(thrust=500, chamber_pressure=10,
                     overrides={'chamber_diameter': istenen})
        d = r['combustion_analysis']['chamber_geometry']['diameter']
        assert d == pytest.approx(istenen, rel=1e-6), (
            f'kullanıcı {istenen} mm istedi, {d} mm teslim edildi')


def test_p3b1_03_bant_ici_dort_girdi_ayni_geometriyi_vermez():
    """Dört ayrı kabul-bandı-içi girdi bit-aynı yanıt veriyordu (0/3139 fark)."""
    capla = []
    for ov in ({'chamber_diameter': 30.0}, {'chamber_diameter': 40.0},
               {'contraction_ratio': 2.0}, {'contraction_ratio': 4.0}):
        _e, r = _kos(thrust=500, chamber_pressure=10, overrides=dict(ov))
        capla.append(round(
            r['combustion_analysis']['chamber_geometry']['diameter'], 6))
    assert len(set(capla)) >= 3, (
        f'dört farklı girdi yalnız {len(set(capla))} farklı çap üretti: {capla}')


def test_p3b1_03_taban_altindaki_girdi_sessiz_kalmaz():
    """Taban altı bir çap kabul edilir ama BEYAN edilir (sessiz değil)."""
    _e, r = _kos(thrust=500, chamber_pressure=10,
                 overrides={'chamber_diameter': 30.0})
    kodlar = {w['code'] for w in (r.get('input_warnings') or [])}
    assert 'warn.liquid.chamber_diameter_below_model_floor' in kodlar


# ---------------------------------------------------------------------------
# P3B1-04 — itki optimumu çözülür, yönü doğrudur, künyesi yayımlanır
# ---------------------------------------------------------------------------
def test_p3b1_04_itki_optimumu_isp_optimumunun_ustunde():
    """Ölçüldü: tablodaki 6 çiftin 6'sında da of_thrust < of_isp yazılıydı;
    modülün kendi fizik beyanı ve F ∝ Isp/c* türetmesi TERSİNİ söyler."""
    _e, r = _kos()
    of_isp = r['optimal_mixture_ratio']
    of_thrust = r['optimal_mixture_ratio_thrust']
    if of_thrust is None:
        pytest.skip('CEA çözülemedi; alan dürüstçe boş — kaynak künyesi '
                    'aşağıdaki bekçide sınanıyor')
    assert of_thrust > of_isp, (
        f'itki optimumu {of_thrust} Isp optimumunun ({of_isp}) altında')


def test_p3b1_04_itki_optimumu_oda_basinciyla_hareket_eder():
    """Ölçüldü: Pc=40/100/200 bar'ın üçünde de 2,2700'de çakılıydı."""
    degerler = []
    for pc in (40, 200):
        _e, r = _kos(chamber_pressure=pc)
        degerler.append(r['optimal_mixture_ratio_thrust'])
    if any(v is None for v in degerler):
        pytest.skip('CEA çözülemedi')
    assert abs(degerler[0] - degerler[1]) > 1e-6, (
        f'itki optimumu Pc ile hiç oynamıyor: {degerler}')


def test_p3b1_04_iki_optimum_kunyesi_de_yayimlanir():
    """İki künye motorda üretiliyor ama yanıtın hiçbir yerinde YOKTU."""
    _e, r = _kos()
    assert r['optimal_mixture_ratio_source']
    assert r['optimal_mixture_ratio_thrust_source']


def test_p3b1_04_kullanici_girdisi_cozum_gibi_gosterilmez():
    """of_max_thrust gönderilince künye 'kullanıcı' demeli."""
    _e, r = _kos(overrides={'of_max_thrust': 3.0})
    assert r['optimal_mixture_ratio_thrust'] == pytest.approx(3.0)
    assert 'user input' in (r['optimal_mixture_ratio_thrust_source'] or '')


# ---------------------------------------------------------------------------
# P3B2-02 — L* muhasebesi konverjan koniyi sayar
# ---------------------------------------------------------------------------
def test_p3b2_02_cizilen_l_star_istenen_l_stari_teslim_eder(taban_kosu):
    """Ölçüldü: istenen 1,2 m, çizilen 1,8597 m (+%55) — koni hiç sayılmıyordu."""
    _e, r = taban_kosu
    g = r['combustion_analysis']['chamber_geometry']
    cs = r['cooling_system']
    d_c = float(g['diameter']) / 1000.0
    d_t = float(r['throat_diameter'])
    l_conv = float(cs['convergent_length']) / 1000.0
    a_t = math.pi * (d_t / 2.0) ** 2
    v_sil = math.pi * (d_c / 2.0) ** 2 * (float(g['length']) / 1000.0)
    r1, r2 = d_c / 2.0, d_t / 2.0
    v_kon = math.pi * l_conv / 3.0 * (r1 * r1 + r1 * r2 + r2 * r2)
    l_star_cizilen = (v_sil + v_kon) / a_t
    assert l_star_cizilen == pytest.approx(1.2, rel=2e-3), (
        f'çizilen L* {l_star_cizilen:.4f} m, istenen 1,2 m')


def test_p3b2_02_yayimlanan_hacim_koniyi_icerir(taban_kosu):
    """Yayımlanan chamber_geometry.volume yalnız silindir hacmi değildir."""
    _e, r = taban_kosu
    g = r['combustion_analysis']['chamber_geometry']
    d_c = float(g['diameter']) / 1000.0
    v_sil_cm3 = math.pi * (d_c / 2.0) ** 2 * (float(g['length']) / 1000.0) * 1e6
    assert float(g['volume']) > v_sil_cm3 * 1.05, (
        'yayımlanan hacim silindirle aynı — konverjan koni sayılmıyor')


def test_p3b2_02_buyuk_motor_taban_l_stari_reddedilmez(taban_kosu):
    """Koni tek başına taban L*'ı aşan BÜYÜK motor reddedilmez, beyan edilir.

    Ölçüldü: koninin tek başına tuttuğu L* = 12,088·d_t olduğundan boğazı
    99,3 mm'yi aşan her motorda (60 bar'da ~70 kN üstü) taban L* = 1,2 m
    ulaşılamaz hâle gelir. Onarımın ilk hâli bu motorları 400 ile
    reddediyordu — kusuru düzeltmek yerine ürünü kırıyordu. Doğru davranış:
    kullanılamayan taban YÜKSELTİLİR ve yayımlanan L* çizilen gövdenin
    kendisi olur (250 kN / 200 bar LH2-LOX: eskiden 1,2 yayımlanıyor,
    2,4209 çiziliyordu).
    """
    _e, r = _kos(thrust=250000, chamber_pressure=200, fuel_type='lh2',
                 oxidizer_type='lox')
    cs = r['cooling_system']
    g = r['combustion_analysis']['chamber_geometry']
    d_c = float(g['diameter']) / 1000.0
    d_t = float(r['throat_diameter'])
    l_conv = float(cs['convergent_length']) / 1000.0
    a_t = math.pi * (d_t / 2.0) ** 2
    v_sil = math.pi * (d_c / 2.0) ** 2 * (float(g['length']) / 1000.0)
    r1, r2 = d_c / 2.0, d_t / 2.0
    v_kon = math.pi * l_conv / 3.0 * (r1 * r1 + r1 * r2 + r2 * r2)
    cizilen = (v_sil + v_kon) / a_t
    assert float(cs['l_star']) == pytest.approx(cizilen, rel=2e-3), (
        f"yayımlanan L* {cs['l_star']} ⟷ çizilen {cizilen:.4f}")
    # ÖH D18 fizik-a2 (F2 ≡ OH-D15-01) ÇEVİRİSİ: burada eskiden
    # ``l_star > l_star_requested`` yazıyordu, yani "taban YÜKSELTİLDİ"
    # kaçış yolunun ATEŞLEDİĞİ sınanıyordu. O kaçış yolu D15'te ürünü
    # kırmamak için konmuştu; D18/F2 kaçış yolunu GEREKSİZ kıldı: daralma
    # oranı artık sabit 12,25 değil boğaz çapı korelasyonundan geliyor ve
    # konverjan koni hiçbir boğaz çapında taban L*'ı yutmuyor.
    #
    # İddia tersine döndü ve DARALDI: büyük motor hâlâ REDDEDİLMEZ (asıl
    # iddia), ama artık yayımlanan L* istenen değerin ta kendisidir —
    # yükseltmeye gerek kalmamıştır. Kaçış yolu geri ateşlerse (yani ε_c
    # sabite dönerse) bu satır kırmızı olur.
    assert float(cs['l_star']) == pytest.approx(
        float(cs['l_star_requested']), rel=1e-9), (
        f"D18/F2 sonrası taban L* yükseltilmemeli: istenen "
        f"{cs['l_star_requested']} ⟷ yayımlanan {cs['l_star']}")
    assert 'SP-125' in cs['l_star_source'] or \
        cs['l_star_source'] == 'model default'
    assert cs['l_star_basis']


def test_p3b2_02_kullanicinin_l_stari_kurulamiyorsa_gercek_yayimlanir():
    """Kullanıcının L*'ı bu daralma oranıyla kurulamıyorsa sayı UYDURULMAZ.

    Arayüzün KENDİ varsayılan formu (tests/test_sivi_form_alanlari.py
    BASE_PAYLOAD: chamber_diameter = 200 mm ve characteristic_length =
    1,2 m, boğaz 30,8 mm -> daralma oranı 42) tam bu durumdadır: koni tek
    başına 2,4307 m L* tutar. Çizilen gövde değiştirilmez, ama yayımlanan
    L* artık o gövdenin kendisidir (eskiden 1,2 yazıp 3,63 çiziyordu) ve
    istenen değer yanında durur; kullanıcı ayrıca uyarı alır.
    """
    _e, r = _kos(thrust=10000, chamber_pressure=100,
                 overrides={'characteristic_length': 1.2,
                            'chamber_diameter': 200.0})
    cs = r['cooling_system']
    g = r['combustion_analysis']['chamber_geometry']
    d_c = float(g['diameter']) / 1000.0
    d_t = float(r['throat_diameter'])
    l_conv = float(cs['convergent_length']) / 1000.0
    a_t = math.pi * (d_t / 2.0) ** 2
    v_sil = math.pi * (d_c / 2.0) ** 2 * (float(g['length']) / 1000.0)
    r1, r2 = d_c / 2.0, d_t / 2.0
    v_kon = math.pi * l_conv / 3.0 * (r1 * r1 + r1 * r2 + r2 * r2)
    cizilen = (v_sil + v_kon) / a_t
    assert cizilen > 1.5, 'senaryo kurulamaz L* durumunu üretmiyor'
    assert float(cs['l_star']) == pytest.approx(cizilen, rel=2e-3)
    assert float(cs['l_star_requested']) == pytest.approx(1.2)
    kodlar = {w['code'] for w in (r.get('input_warnings') or [])}
    assert 'warn.liquid.l_star_unreachable' in kodlar


def test_p3b2_02_hazne_hacmi_tek_kaynaktan():
    """component_dimensions.chamber_volume ⟷ chamber_geometry.volume.

    İki yaprak iki ayrı formülden geliyordu (biri L*·A_t, diğeri çizilen
    gövde). İstenen L*'ın kurulamadığı koşuda (arayüzün kendi varsayılan
    formu) ikisi ayrışır; senaryo bilerek o koşudur.
    """
    _e, r = _kos(thrust=10000, chamber_pressure=100,
                 overrides={'characteristic_length': 1.2,
                            'chamber_diameter': 200.0})
    g = r['combustion_analysis']['chamber_geometry']
    cd = r['component_sizing']['component_dimensions']
    a_t = math.pi * (float(r['throat_diameter']) / 2.0) ** 2
    assert float(g['volume']) > 1.2 * a_t * 1e6 * 1.05, (
        'senaryo iki formülü ayrıştırmıyor')
    assert float(cd['chamber_volume']) == pytest.approx(
        float(g['volume']), rel=1e-9)


# ---------------------------------------------------------------------------
# P3B2-03 — motor boyu konverjan koniyi atlamaz
# ---------------------------------------------------------------------------
def test_p3b2_03_overall_length_uc_bolumun_toplami(taban_kosu):
    """Ölçüldü: 274,506 mm yayımlanırken STEP/CAD 402,456 mm çiziyordu (1,47x)."""
    _e, r = taban_kosu
    cs = r['cooling_system']
    toplam = (float(cs['chamber_length']) + float(cs['convergent_length'])
              + float(cs['divergent_length']))
    yayim = float(r['design_summary']['key_dimensions']['overall_length_mm'])
    assert yayim == pytest.approx(toplam, rel=1e-9)
    assert yayim == pytest.approx(float(cs['cooled_channel_length']), rel=1e-9)


# ---------------------------------------------------------------------------
# P3B2-04 — irtifa tablosu donmaz
# ---------------------------------------------------------------------------
def test_p3b2_04_irtifa_tablosu_10_km_ustunde_donmaz(taban_kosu):
    """Ölçüldü: 8 satırın 5'i (10/20/50/80/100 km) birebir aynı Isp ve itkiyi
    yayımlıyordu; motor 10 km'de (26,4 kPa) tam vakum performansı ilan
    ediyordu — iyimser, yörünge hesabında tehlikeli yön."""
    _e, r = taban_kosu
    ust = [x for x in r['altitude_performance']
           if float(x['altitude']) >= 10000.0
           and x['specific_impulse'] is not None]
    assert len(ust) >= 4
    isps = [round(float(x['specific_impulse']), 6) for x in ust]
    assert len(set(isps)) == len(isps), (
        f'10 km üstü satırlar özdeş Isp yayımlıyor: {isps}')


def test_p3b2_04_isp_irtifayla_artar(taban_kosu):
    """Ortam basıncı düştükçe teslim Isp'si artmalı (kırpma bunu donduruyordu)."""
    _e, r = taban_kosu
    sat = [x for x in r['altitude_performance']
           if x['specific_impulse'] is not None]
    isps = [float(x['specific_impulse']) for x in sat]
    assert all(b > a for a, b in zip(isps, isps[1:])), isps


def test_p3b2_04_beyan_ile_sayi_uyusur(taban_kosu):
    """Satırın künyesi Isp = (isp_sl/CF_sl)*CF(h) diyor; sayı bunu vermeli."""
    _e, r = taban_kosu
    sat = [x for x in r['altitude_performance']
           if x['specific_impulse'] is not None]
    yer = sat[0]
    oran = float(yer['specific_impulse']) / float(yer['thrust_coefficient'])
    for x in sat:
        beklenen = oran * float(x['thrust_coefficient'])
        assert float(x['specific_impulse']) == pytest.approx(
            beklenen, rel=1e-6), (
            f"{x['altitude']} m satırı künyesindeki formülü vermiyor")


# ---------------------------------------------------------------------------
# P3B2-05 — kullanıcının cidar limiti sessizce aşılmaz, akı cidarla tutarlı
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def cidar_kosu():
    return _kos(fuel_type='methane', oxidizer_type='lox',
                overrides={'max_wall_temp': 800.0})


def test_p3b2_05_asilan_cidar_limiti_beyan_edilir(cidar_kosu):
    """Ölçüldü: kullanıcı 800 K girdi, çözücü 2107,7 K yayımladı ve üretilen
    5 uyarının hiçbiri kullanıcının limitinden söz etmiyordu."""
    _e, r = cidar_kosu
    cs = r['cooling_system']
    if float(cs['wall_temperature_hot']) <= 800.0:
        pytest.skip('bu yükte limit aşılmıyor')
    kodlar = {w['code'] for w in (r.get('input_warnings') or [])}
    assert 'warn.liquid.wall_temp_limit_exceeded' in kodlar
    assert cs['wall_temperature_limit_K'] == pytest.approx(800.0)
    assert cs['wall_temperature_limit_status'] == 'EXCEEDED'


def test_p3b2_05_isi_akisi_yayimlanan_hazne_yuku_ile_ayni_hesaptan(cidar_kosu):
    """Ölçüldü: aynı sözlükte chamber_heat_flux 800 K cidara, yanındaki
    wall_temperature_hot 2107,7 K'ya aitti — iki cidar tek karttaydı.

    Bekçi iki MUHASEBE denkliği sınar; ikisi birden ancak akı marşın kendi
    hazne payından (q = Q_hazne/A_hazne) gelirse sağlanır:
      (1) q · A_hazne = chamber_heat_load  (taban ağacında BOZUK: akı Bartz'ı
          800 K cidarla değerlendiriyor, hazne yükü ise marştan ölçekleniyor)
      (2) chamber_heat_load + nozzle_heat_load = total_heat_load  (Bartz'ı
          marş sonrası cidarla yeniden değerlendiren ara çözümde BOZULUYOR)
    """
    _e, r = cidar_kosu
    cs = r['cooling_system']
    if 'march' not in str(cs.get('wall_temperature_source') or ''):
        pytest.skip('marş koşmadı; çelişki bu dalda doğmuyor')
    a_hazne = math.pi * (float(cs['chamber_diameter']) / 1000.0) * (
        float(cs['chamber_length']) / 1000.0)
    assert float(cs['chamber_heat_flux']) * a_hazne == pytest.approx(
        float(cs['chamber_heat_load']), rel=1e-9), (
        'yayımlanan akı ile yayımlanan hazne ısı yükü aynı hesaptan gelmiyor')
    assert (float(cs['chamber_heat_load']) + float(cs['nozzle_heat_load'])
            == pytest.approx(float(cs['total_heat_load']), rel=1e-9)), (
        'hazne + lüle ısı yükü toplam yükü vermiyor')
    assert cs['chamber_heat_flux_basis']
