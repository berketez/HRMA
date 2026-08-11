"""Hibrit motor — Dalga 6 bağlaması: altı modülün sonuç sözlüğüne bağlanması.

TEŞHİS (2026-08-09, ölçüldü): bu altı üretici metot hibrit motor dosyasında
TANIMLIYDI ama sonuç sözlüğüne HİÇ konmuyordu — yani ölü koddu (def=1,
çağrı=0). Kullanıcı ne hesabı ne de hesabın yokluk beyanını görüyordu:

  _oxidizer_tank_vessel_block   -> oxidizer_tank_pressure_vessel  (A3)
  _closure_joint_block          -> closure_joint                  (A4)
  _feed_water_hammer_block      -> feed_water_hammer              (A6)
  _acoustic_modes_block         -> acoustic_modes
  _nozzle_flow_block            -> nozzle_flow_quasi1d
  _igniter_sizing_block         -> igniter_sizing

Bu dosya bağlamanın İKİ YÜZÜNÜ birden kilitler:

  (a) GİRDİ VARSA alan gerçekten çıkar ve sayıları çözücünün KENDİ
      değerlerinden gelir (tek tank tek geometri, tek gaz tek özellik çifti);
  (b) GİRDİ YOKSA blok NOT_MODELLED beyanıyla çıkar ve İÇİNDE TEK SAYI
      BULUNMAZ — eksik girdinin yerine varsayılan enjekte edip modülü
      "çalışmış" göstermek bu turun düzelttiği hatanın ta kendisidir.

Ayrıca A10 beyanının çürümesi burada da sınanır: akustik modlar artık
GERÇEKTEN hesaplandığı için 'combustion_stability_acoustics' beyanı
yalan hâline gelmişti ve kaldırıldı (bekçi: tests/test_hibrit_beyan_a10.py).
"""

import json
import math
import warnings

import pytest

from hrma.engines.hybrid_rocket_engine import (
    CLOSURE_JOINT_DEFAULTS,
    OX_TANK_MATERIAL_DEFAULT,
    HybridRocketEngine,
)

# Evrensel gaz sabiti: bloklarda R = R_u/MW için kullanılan aynı sayı.
R_EVRENSEL = 8314.462618

ALTI_BLOK = (
    'oxidizer_tank_pressure_vessel',
    'closure_joint',
    'feed_water_hammer',
    'acoustic_modes',
    'nozzle_flow_quasi1d',
    'igniter_sizing',
)


def _kos(**degisiklik):
    """Tasarım noktası koşulmuş hibrit motor + sonuç sözlüğü."""
    ayarlar = dict(thrust=1000, burn_time=10, of_ratio=2.5,
                   chamber_pressure=20.0, track_performance=False)
    ayarlar.update(degisiklik)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(**ayarlar)
        sonuc = motor.calculate()
    return motor, sonuc


@pytest.fixture(scope='module')
def civatasiz():
    """Kapak cıvata sayısı VERİLMEMİŞ koşu (arayüzün bugünkü hâli)."""
    return _kos()


@pytest.fixture(scope='module')
def civatali():
    """Aynı görev, kapak cıvata sayısı verilmiş: A4 gerçekten çözülür."""
    return _kos(closure_bolt_count=12)


def _sayi_yollari(dugum, yol='', atla=()):
    """Ağaçtaki TÜM sayısal yaprakların yolunu döndürür (bool sayılmaz).

    NOT_MODELLED bloklarında bu liste BOŞ olmalıdır: beyan sayı taşımaz.
    """
    bulunan = []
    if isinstance(dugum, bool):
        return bulunan
    if isinstance(dugum, (int, float)):
        bulunan.append(yol or '<kok>')
    elif isinstance(dugum, dict):
        for anahtar, deger in dugum.items():
            if anahtar in atla:
                continue
            alt = f'{yol}.{anahtar}' if yol else anahtar
            bulunan.extend(_sayi_yollari(deger, alt, atla))
    elif isinstance(dugum, (list, tuple)):
        for i, eleman in enumerate(dugum):
            bulunan.extend(_sayi_yollari(eleman, f'{yol}[{i}]', atla))
    return bulunan


# ---------------------------------------------------------------------------
# Bağlamanın kendisi: altı blok da sonuç sözlüğünde
# ---------------------------------------------------------------------------

def test_alti_blok_da_sonuc_sozlugunde(civatasiz):
    """Ölü kodun sonu: her blok yayımlanıyor, durumu ve gerekçesi var."""
    _, sonuc = civatasiz
    eksik = [ad for ad in ALTI_BLOK if ad not in sonuc]
    assert not eksik, f'Bağlanmamış blok(lar): {eksik}'
    for ad in ALTI_BLOK:
        blok = sonuc[ad]
        assert isinstance(blok, dict), f'{ad} sözlük olmalı'
        assert blok.get('status') in ('modelled', 'NOT_MODELLED'), (
            f'{ad} durumu beyanlı değil: {blok.get("status")!r}')
        assert blok.get('_basis'), f'{ad} fizik künyesi (_basis) taşımıyor'


def test_uctan_uca_calculate_yanitinda_var():
    """POST /calculate yanıtında alanlar GERÇEKTEN çıkıyor (motor bloğu)."""
    from hrma.app import app

    istemci = app.test_client()
    yanit = istemci.post('/calculate', json={
        'thrust': 1000, 'burn_time': 10, 'of_ratio': 2.5,
        'chamber_pressure': 20.0, 'atmospheric_pressure': 1.0,
        'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    })
    assert yanit.status_code == 200, yanit.get_json()
    motor = yanit.get_json()['motor']
    eksik = [ad for ad in ALTI_BLOK if ad not in motor]
    assert not eksik, f'Uçta görünmeyen blok(lar): {eksik}'
    # Modellenen bloklar uçta da SAYI taşıyor (sadece anahtar değil)
    assert motor['oxidizer_tank_pressure_vessel']['status'] == 'modelled'
    assert motor['oxidizer_tank_pressure_vessel']['meop_bar'] > 0
    assert motor['acoustic_modes']['status'] == 'modelled'
    assert motor['acoustic_modes']['modes']
    assert motor['nozzle_flow_quasi1d']['status'] == 'modelled'
    assert motor['nozzle_flow_quasi1d']['exit']['mach'] > 1.0
    # Arayüzde cıvata sayısı alanı olmadığı için A4 uçta beyanla çıkar
    assert motor['closure_joint']['status'] == 'NOT_MODELLED'
    assert motor['closure_joint']['required_inputs'] == ['closure_bolt_count']


# ---------------------------------------------------------------------------
# A3 — oksitleyici tankı basınçlı kap
# ---------------------------------------------------------------------------

def test_a3_girdiler_cozucunun_kendi_tank_durumundan(civatasiz):
    _, sonuc = civatasiz
    kap = sonuc['oxidizer_tank_pressure_vessel']
    assert kap['status'] == 'modelled'
    blowdown = sonuc['tank_blowdown']
    slosh = sonuc['oxidizer_tank_slosh']
    # MEOP ve cidar tasarım sıcaklığı blowdown serilerinin MAKSİMUMU
    assert kap['meop_bar'] == pytest.approx(max(blowdown['tank_pressure_bar']))
    assert kap['design_temperature_K'] == pytest.approx(
        max(blowdown['tank_temperature_K']))
    # TEK TANK TEK GEOMETRİ: çap slosh bloğunun çapının AYNISI
    assert kap['inner_diameter_m'] == pytest.approx(slosh['tank_diameter_m'])
    # Malzeme beyanlı bir tasarım seçimi; hesap ya da kullanıcı girdisi değil
    assert kap['material'] == OX_TANK_MATERIAL_DEFAULT
    assert 'DECLARED DESIGN CHOICE' in kap['material_source']


def test_a3_cidar_dogrulanmiyor_boyutlandiriliyor(civatasiz):
    """Hibritte çözülmüş bir cidar yok: modül BOYUTLANDIRMA modunda koşar."""
    _, sonuc = civatasiz
    kap = sonuc['oxidizer_tank_pressure_vessel']
    kazan = kap['pressure_vessel']
    assert kazan['auto_sized'] is True
    assert kazan['required_thickness_mm'] > 0
    assert kazan['wall_thickness_used_mm'] >= kazan['required_thickness_mm']
    assert 'not supplied and not computed' in kap['wall_thickness_source']


def test_a3_tank_durumu_yoksa_sayi_uydurulmuyor(civatasiz):
    """Blowdown/slosh çözülmediyse blok SAYI İÇERMEDEN beyan döner."""
    motor, _ = civatasiz
    blok = motor._oxidizer_tank_vessel_block(
        {'status': 'NOT_MODELLED'}, {'status': 'NOT_MODELLED'})
    assert blok['status'] == 'NOT_MODELLED'
    assert 'meop_bar' not in blok
    assert 'pressure_vessel' not in blok
    # Eksik girdiler ADIYLA söyleniyor
    assert 'MEOP' in blok['reason']
    assert 'inner diameter' in blok['reason']
    assert not _sayi_yollari(blok), (
        f'NOT_MODELLED beyanı sayı taşıyor: {_sayi_yollari(blok)}')


# ---------------------------------------------------------------------------
# A4 — kapak cıvata birleşimi
# ---------------------------------------------------------------------------

def test_a4_civata_sayisi_verilince_birlesim_cozuluyor(civatali):
    motor, sonuc = civatali
    birlesim = sonuc['closure_joint']
    assert birlesim['status'] == 'modelled'
    assert birlesim['bolt_count'] == 12
    # Sızdırmazlık çapı ve basınç çözücünün GERÇEK değerleri
    assert birlesim['seal_diameter_mm'] == pytest.approx(motor.D_ch * 1000.0)
    assert birlesim['pressure_bar'] == pytest.approx(motor.P_c)
    # Donanım beyanlı varsayılan (sayfada alan yok), hesap değil
    assert birlesim['bolt_size'] == CLOSURE_JOINT_DEFAULTS['size']
    assert 'DECLARED DEFAULTS' in birlesim['hardware_source']
    # Analiz gerçekten koştu: emniyet katsayıları sonlu sayılar
    for alan in ('proof_safety_factor', 'separation_factor',
                 'overload_factor', 'tightening_torque_nm'):
        assert math.isfinite(float(birlesim[alan])), f'{alan} sonlu değil'


def test_a4_civata_sayisi_yoksa_birlesim_boyutlandirilmiyor(civatasiz):
    _, sonuc = civatasiz
    birlesim = sonuc['closure_joint']
    assert birlesim['status'] == 'NOT_MODELLED'
    assert birlesim['required_inputs'] == ['closure_bolt_count']
    # Uydurma cıvata planı yok: ne tork ne emniyet katsayısı
    for yasak in ('bolt_count', 'tightening_torque_nm', 'proof_safety_factor',
                  'separation_factor'):
        assert yasak not in birlesim, f'{yasak} uydurulmuş'
    assert not _sayi_yollari(birlesim)


def test_a4_gecersiz_civata_sayisi_sessizce_varsayilana_dusmuyor():
    """Bant dışı sayı sessizce 'makul' bir değere çevrilmez; beyan edilir."""
    _lo, hi = CLOSURE_JOINT_DEFAULTS['bolt_count_range']
    motor, sonuc = _kos(closure_bolt_count=hi + 1)
    assert motor.closure_bolt_count is None
    assert sonuc['closure_joint']['status'] == 'NOT_MODELLED'
    assert any('closure_bolt_count(out_of_range' in kayit
               for kayit in motor._defaults_used)


# ---------------------------------------------------------------------------
# A6 — besleme hattı su koçu
# ---------------------------------------------------------------------------

def test_a6_su_kocu_hat_olmadigi_icin_beyanla_cikiyor(civatasiz):
    _, sonuc = civatasiz
    kocu = sonuc['feed_water_hammer']
    assert kocu['status'] == 'NOT_MODELLED'
    # Gerekçe hattın YOKLUĞUNU söylüyor (çap/hız/uzunluk hiç hesaplanmıyor)
    assert 'no line diameter' in kocu['reason']
    assert set(kocu['required_inputs']) == {
        'feed_line_length_m', 'feed_line_inner_diameter_mm',
        'feed_line_wall_thickness_mm', 'valve_closure_time_ms'}
    # Joukowsky basınç sıçraması UYDURULMUYOR
    assert not _sayi_yollari(kocu), (
        f'su koçu beyanı sayı taşıyor: {_sayi_yollari(kocu)}')
    assert kocu['oxidizer_line']['status'] == 'NOT_MODELLED'


# ---------------------------------------------------------------------------
# Kamara akustik modları
# ---------------------------------------------------------------------------

def test_akustik_modlar_kamaranin_gercek_durumundan(civatasiz):
    _, sonuc = civatasiz
    akustik = sonuc['acoustic_modes']
    assert akustik['status'] == 'modelled'
    girdiler = akustik['inputs']
    # Yanma dengesinin kamara kaydı: aynı gama, aynı sıcaklık
    assert girdiler['gamma'] == pytest.approx(sonuc['gamma'])
    assert girdiler['chamber_temperature'] == pytest.approx(
        sonuc['chamber_temperature'])
    assert girdiler['gas_constant'] == pytest.approx(
        R_EVRENSEL / sonuc['molecular_weight'], rel=1e-6)
    # Ses hızı a = sqrt(gamma*R*T) — modül gerçekten bu fiziği koşmuş
    assert akustik['sound_speed_m_s'] == pytest.approx(
        math.sqrt(girdiler['gamma'] * girdiler['gas_constant']
                  * girdiler['chamber_temperature']), rel=1e-6)
    # Mod tablosu boş değil ve 1L modu var
    assert akustik['modes'], 'mod tablosu boş'
    assert any(mod['label'] == '1L' for mod in akustik['modes'])
    assert all(mod['frequency_hz'] > 0 for mod in akustik['modes'])


def test_akustik_chug_orani_gercek_enjektor_dususunden(civatasiz):
    _, sonuc = civatasiz
    chug = sonuc['acoustic_modes']['stability_report']['chug']
    dp_bar = sonuc['injector_design']['injection_pressure_drop_bar']
    assert chug['evaluated'] is True
    assert chug['injector_dp_ratio'] == pytest.approx(
        dp_bar / sonuc['chamber_pressure'], rel=1e-6)


def test_akustik_kamara_durumu_yoksa_frekans_uydurulmuyor(civatasiz):
    motor, _ = civatasiz
    blok = motor._acoustic_modes_block({})
    assert blok['status'] == 'NOT_MODELLED'
    assert 'modes' not in blok
    assert 'sound_speed_m_s' not in blok
    assert 'missing solver output' in blok['reason']
    assert not _sayi_yollari(blok)


def test_akustik_baglamasi_a10_beyanini_curuttu(civatasiz):
    """Modellenen bir şeyi 'modellenmiyor' ilan etmek de yalandır."""
    _, sonuc = civatasiz
    beyanlar = sonuc['not_modelled']
    assert 'combustion_stability_acoustics' not in beyanlar, (
        'akustik modlar artık hesaplanıyor; bu beyan çürümüş olmalı')
    # Kalan GERÇEK yokluk hibride özgü kalem olarak beyanlı
    kalan = beyanlar['hybrid_boundary_layer_instability']
    assert kalan.startswith('NOT_MODELLED')
    assert 'acoustic_modes' in kalan, (
        'kalan beyan, modellenen kısmın nerede olduğunu söylemeli')
    # Modülün KENDİ sınırları kendi bloğunda (tek kaynak ilkesi)
    assert 'combustion_response' in sonuc['acoustic_modes']['not_modelled']


# ---------------------------------------------------------------------------
# Yarı-1B lüle akışı + ayrılma
# ---------------------------------------------------------------------------

def test_lule_akisi_cozuluyor_ve_ayni_gaz_ciftini_kullaniyor(civatasiz):
    _, sonuc = civatasiz
    akis = sonuc['nozzle_flow_quasi1d']
    assert akis['status'] == 'modelled'
    assert akis['throat']['choked'] is True
    assert akis['exit']['mach'] > 1.0
    girdiler = akis['inputs']
    assert girdiler['P0_Pa'] == pytest.approx(sonuc['chamber_pressure'] * 1e5)
    assert girdiler['R_J_kgK'] == pytest.approx(
        R_EVRENSEL / sonuc['molecular_weight'], rel=1e-9)
    # İki blok aynı gaz için iki farklı özellik kullanamaz
    akustik = sonuc['acoustic_modes']['inputs']
    assert girdiler['gamma'] == pytest.approx(akustik['gamma'])
    assert girdiler['R_J_kgK'] == pytest.approx(akustik['gas_constant'])
    # İstasyonlar seyreltilmiş ama SON istasyon her koşulda korunmuş
    istasyon = akis['stations']
    assert len(istasyon['x_m']) == len(istasyon['mach']) == len(
        istasyon['pressure_Pa']) == len(istasyon['area_m2'])
    assert istasyon['x_m'][-1] == pytest.approx(max(istasyon['x_m']))
    assert istasyon['mach'][-1] == pytest.approx(akis['exit']['mach'])


def test_lule_debisi_capraz_denetim_manseti_ezmiyor(civatasiz):
    """Yarı-1B debi bir ÇAPRAZ DENETİMDİR; çözücünün ṁ'sini değiştirmez."""
    motor, sonuc = civatasiz
    akis = sonuc['nozzle_flow_quasi1d']
    assert akis['mass_flow_solver_kg_s'] == pytest.approx(motor.mdot_total)
    assert sonuc['mdot_total'] == pytest.approx(motor.mdot_total)
    assert akis['mass_flow_rel_diff'] == pytest.approx(
        (akis['mass_flow_kg_s'] - akis['mass_flow_solver_kg_s'])
        / akis['mass_flow_solver_kg_s'])
    # Fark GİZLENMİYOR: gerekçe blokta yazılı
    assert 'CROSS-CHECK, not a correction' in akis['mass_flow_check_basis']


def test_lule_ayrilma_denetimi_ayni_kontur_uzerinde(civatasiz):
    _, sonuc = civatasiz
    ayrilma = sonuc['nozzle_flow_quasi1d']['separation']
    assert ayrilma['status'] in ('modelled', 'not_applicable')
    if ayrilma['status'] == 'modelled':
        assert ayrilma['criteria'], 'ayrılma ölçütü tablosu boş'
        assert isinstance(ayrilma['separated'], bool)


def test_lule_kamara_durumu_yoksa_rejim_uydurulmuyor(civatasiz):
    motor, _ = civatasiz
    blok = motor._nozzle_flow_block({})
    assert blok['status'] == 'NOT_MODELLED'
    for yasak in ('regime', 'exit', 'throat', 'stations', 'mass_flow_kg_s'):
        assert yasak not in blok, f'{yasak} uydurulmuş'
    assert 'missing solver output' in blok['reason']
    assert not _sayi_yollari(blok)


# ---------------------------------------------------------------------------
# Ateşleyici boyutlandırma
# ---------------------------------------------------------------------------

def test_atesleyici_yoklugu_denetlenebilir_bicimde_beyanli(civatasiz):
    _, sonuc = civatasiz
    ates = sonuc['igniter_sizing']
    assert ates['status'] == 'NOT_MODELLED'
    # Eksik olan ADIYLA: tutuşma sıcaklığı ve özgül ısı yakıt tablosunda yok
    assert 'propellant_ignition_temperature_K' in ates['required_inputs']
    assert 'propellant_specific_heat_J_kg_K' in ates['required_inputs']
    # VAR OLANLAR çözücünün GERÇEK değerleri (boşluk denetlenebilir olsun)
    mevcut = ates['available_inputs']
    assert mevcut['chamber_free_volume_m3'] == pytest.approx(
        sonuc['chamber_volume_actual_m3'])
    assert mevcut['main_mass_flow_kg_s'] == pytest.approx(sonuc['mdot_total'])
    assert mevcut['chamber_pressure_bar'] == pytest.approx(
        sonuc['chamber_pressure'])
    # Ateşleme enerjisi / şarj kütlesi UYDURULMUYOR
    for yasak in ('ignition_energy_J', 'charge_mass_kg',
                  'hard_start_pressure_bar', 'torch_mass_flow_kg_s'):
        assert yasak not in ates


# ---------------------------------------------------------------------------
# Ortak dürüstlük kapısı + sözleşme
# ---------------------------------------------------------------------------

def test_not_modelled_bloklar_hicbir_sayi_tasimiyor(civatasiz):
    """Beyan sayı taşımaz: eksik girdinin yerine varsayılan enjekte edilmez.

    Tek istisna 'available_inputs' — orası UYDURMA değil, çözücünün zaten
    hesapladığı değerlerin denetlenebilirlik için listelenmiş hâlidir.
    """
    _, sonuc = civatasiz
    for ad in ALTI_BLOK:
        blok = sonuc[ad]
        if blok.get('status') != 'NOT_MODELLED':
            continue
        sayilar = _sayi_yollari(blok, atla={'available_inputs'})
        assert not sayilar, f'{ad} beyanında uydurma sayı: {sayilar}'


def test_bloklar_json_serilestirilebilir(civatasiz):
    """Yeni altı blok yanıt sözleşmesini bozmuyor."""
    _, sonuc = civatasiz
    metin = json.dumps({ad: sonuc[ad] for ad in ALTI_BLOK})
    assert len(metin) > 2000, 'bloklar beklenmedik biçimde boş'
