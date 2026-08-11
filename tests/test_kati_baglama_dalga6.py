"""Katı motora bağlanan doğrulanmış analiz modüllerinin bekçileri (v2.6.27).

Bu dosya YENİ FİZİK doğrulamaz — modüllerin kendi doğrulama testleri zaten
var (test_iki_faz_kayip.py, test_akustik_modlar.py, test_c_kulvari_bilesenler.py,
lüle akışı/ayrılma testleri). Buradaki bekçiler yalnız BAĞLAMAYI kilitler:

  1. Blok GERÇEK motor hesabıyla üretiliyor mu, alanları fiziksel aralıkta mı?
  2. Modüle giden her girdi çözücünün kendi büyüklüğü mü (sahte veri yasağı)?
  3. Girdi eksik senaryosunda blok sayı üretmeyip NOT_MODELLED beyanı mı
     döndürüyor?
  4. Bloklar teşhis amaçlı mı — performansa/geometriye GERİ BESLENMİYOR mu
     (çift sayım yasağı)?

Hiçbir bekçi sabit bir sayıya bağlanmaz: karşılaştırmalar ya çözücünün
kendi çıktısına ya fiziksel aralığa ya da modülün kendi bildirdiği banda
yapılır.
"""

import numpy as np
import pytest

from hrma.analysis.igniter_sizing import pyrotechnic_charge_mass
from hrma.constants import R_UNIVERSAL
from hrma.engines.solid_rocket_engine import (
    SOLID_CONDENSED_MASS_FRACTION,
    SOLID_IGNITER,
    SUMMERFIELD_SEPARATION_RATIO,
    SolidRocketEngine,
    _family_lookup,
    _get_propellant_safe,
)

# Temel motor: metalize APCP — yoğuşmuş faz kütle kesri tablolu, boğaz çapı
# ve kalış süresi iki-fazlı modülün yayımlanmış veri penceresinin içinde.
TEMEL_MOTOR = dict(grain_type='bates', propellant_type='apcp',
                   chamber_diameter=100.0, grain_length=500.0,
                   core_diameter=30.0, chamber_pressure=40.0)


def _motor(**degisiklik):
    kw = dict(TEMEL_MOTOR)
    kw.update(degisiklik)
    return SolidRocketEngine(**kw)


@pytest.fixture(scope='module')
def temel():
    """Deniz seviyesinde, tam genişlemiş temel motor (gerçek hesap)."""
    e = _motor()
    return e, e.calculate_performance()


@pytest.fixture(scope='module')
def asiri_genisleyen():
    """Aşırı genişlemiş motor: düşük Pc, yüksek ortam basıncı.

    Genişleme oranı pratik alt sınırına (2.5) kelepçelendiği için çıkış
    basıncı ortam basıncının çok altında kalır — ayrılma ölçütlerinin
    TETİKLENDİĞİ gerçek bir çalışma noktası (uydurma senaryo değil,
    2 bar geri basınçta yapılan bir yer testinin karşılığı).
    """
    e = _motor(chamber_pressure=5.0, overrides={'atm_pressure': 200.0})
    return e, e.calculate_performance()


# ===========================================================================
# 1) İki-fazlı (tanecik gecikmesi) Isp kaybı — hrma.analysis.two_phase_loss
# ===========================================================================

def test_iki_faz_blogu_hesaplandi_ve_fiziksel(temel):
    _, res = temel
    blok = res['two_phase_loss']
    assert blok['status'] == 'computed', blok.get('basis')
    assert blok['valid'] is True

    kayip = blok['two_phase_loss_pct']
    lo, hi = blok['two_phase_loss_band_pct']
    assert 0.0 < kayip < 100.0, 'kayıp fiziksel yüzde aralığında olmalı'
    assert lo <= kayip <= hi, 'merkez tahmin kendi bandının içinde olmalı'
    assert 0.0 < lo <= hi

    d43 = blok['particle_diameter_um']
    assert d43 is not None and d43 > 0.0
    # Modülün kendi geçerlilik penceresi (Sutton: 0.015 mm üstü kapsam dışı).
    assert d43 <= blok['validity']['ranges']['particle_diameter_um']['range'][1]

    # Modellenmemiş fizik beyanı bloğa taşınmış olmalı.
    assert blok['not_modelled'], 'modülün NOT_MODELLED beyanı bloğa taşınmamış'
    assert 'two_phase_loss' in blok['_basis']


def test_iki_faz_girdileri_cozucunun_kendi_buyuklukleri(temel):
    """Sahte veri yasağı: modüle giden HER girdi çözücüden gelir."""
    e, res = temel
    kullanilan = res['two_phase_loss']['inputs_used']

    beta, kaynak = _family_lookup(e.propellant_type,
                                  SOLID_CONDENSED_MASS_FRACTION)
    assert kullanilan['condensed_mass_fraction'] == pytest.approx(beta)
    assert kaynak in kullanilan['condensed_mass_fraction_source']

    # Boğaz çapı: raporlanan (imal edilecek) geometrik çapın TA KENDİSİ.
    assert kullanilan['throat_diameter_m'] == pytest.approx(
        res['throat_diameter'] / 1000.0)
    assert kullanilan['chamber_pressure_bar'] == pytest.approx(float(e.P_c))
    assert kullanilan['gamma'] == pytest.approx(float(e.gamma))
    assert kullanilan['molecular_weight_g_mol'] == pytest.approx(
        float(e.mw_exhaust))

    # Kalış süresi çözücünün kendi bağıntısından yeniden üretilebilmeli.
    tau = e._chamber_gas_residence_time_ms()
    assert tau is not None
    assert kullanilan['residence_time_ms'] == pytest.approx(tau, rel=1e-12)

    # Bağıntının kendisi: tau = V_serbest * c* / (R * T_c * A_t)
    v_free = e._case_free_volume()
    a_t = e._design_throat_area()[0]
    r_gas = R_UNIVERSAL / float(e.mw_exhaust)
    beklenen_ms = v_free * float(e.c_star) / (r_gas * float(e.T_c) * a_t) * 1e3
    assert tau == pytest.approx(beklenen_ms, rel=1e-12)
    assert tau > 0.0


def test_iki_faz_kaybi_isp_ye_uygulanmiyor(temel):
    """Çift sayım yasağı: blok teşhis, uygulanan çarpan ayrı ve beyanlı."""
    _, res = temel
    blok = res['two_phase_loss']
    assert blok['applied_to_isp'] is False
    assert 'two_phase_efficiency' in blok['overlap_declaration']

    # Mevcut kayıp dökümü de aynı şeyi söylemeye devam etmeli.
    dokum = (res['detailed_analysis']['performance_metrics']
             ['theoretical_vs_actual_isp'])
    assert dokum['two_phase_losses_applied'] is False
    # İki sayının NEYİ ölçtüğü blokta adıyla açıklanmış olmalı.
    assert 'two_phase_losses' in blok['relation_to_isp_loss_breakdown']


def test_iki_faz_girdi_eksikse_sayi_uretmiyor(monkeypatch):
    """Kalış süresi üretilemiyorsa modül ÇAĞRILMAZ, eksik girdi adıyla anılır."""
    e = _motor()
    monkeypatch.setattr(e, '_chamber_gas_residence_time_ms', lambda: None)
    blok = e._two_phase_loss_report(0.03)
    assert blok['status'] == 'NOT_MODELLED'
    assert 'residence_time_ms' in blok['missing_inputs']
    assert 'two_phase_loss_pct' not in blok, 'eksik girdiyle sayı yayımlanmış'
    assert blok['applied_to_isp'] is False


def test_iki_faz_bogaz_capi_yoksa_not_modelled():
    e = _motor()
    blok = e._two_phase_loss_report(None)
    assert blok['status'] == 'NOT_MODELLED'
    assert 'throat_diameter' in blok['missing_inputs']


def test_iki_faz_pencere_disinda_sessiz_ekstrapolasyon_yok():
    """KN-şeker ailesi yoğuşmuş faz kesri modülün veri penceresini aşar.

    Beklenen davranış SAYI DEĞİL beyandır: blok yayımlanır, ihlal listelenir,
    kayıp None kalır.
    """
    e = _motor(propellant_type='kndx', chamber_diameter=75.0,
               grain_length=400.0, core_diameter=25.0)
    res = e.calculate_performance()
    assert not res.get('error'), res.get('error')
    blok = res['two_phase_loss']
    assert blok['status'] == 'OUT_OF_PUBLISHED_RANGE'
    assert blok['valid'] is False
    assert blok['two_phase_loss_pct'] is None
    assert blok['two_phase_loss_band_pct'] is None
    assert blok['validity']['violations'], 'ihlal gerekçesi yayımlanmamış'


# ===========================================================================
# 2) Kamara akustik modları — hrma.analysis.acoustic_modes
# ===========================================================================

def test_akustik_blogu_hesaplandi_ve_fiziksel(temel):
    e, res = temel
    blok = res['acoustic_modes']
    assert blok['status'] == 'computed', blok.get('basis')

    a = blok['sound_speed_m_s']
    r_gas = R_UNIVERSAL / float(e.mw_exhaust)
    assert a == pytest.approx(
        float(np.sqrt(float(e.gamma) * r_gas * float(e.T_c))), rel=1e-9)
    assert 300.0 < a < 3000.0, 'yanma gazı ses hızı fiziksel aralıkta olmalı'

    modlar = blok['modes']
    assert modlar, 'mod tablosu boş'
    frekanslar = [m['frequency_hz'] for m in modlar]
    assert all(f > 0.0 for f in frekanslar)
    assert frekanslar == sorted(frekanslar), 'modlar frekansa göre sıralı değil'
    # En düşük mod, kavite boyundan gelen boyuna mod olmalı (a/(2L)).
    assert frekanslar[0] == pytest.approx(
        a / (2.0 * blok['equivalent_cavity']['length_m']), rel=1e-6)


def test_akustik_esdeger_kavite_gercek_hacmi_ve_boyu_koruyor(temel):
    """İdealleştirme beyanlı: hacim ve boy GERÇEK çözücü değerleri."""
    e, res = temel
    kavite = res['acoustic_modes']['equivalent_cavity']
    assert kavite['length_m'] == pytest.approx(float(e._case_inner_length()))
    assert kavite['free_gas_volume_m3'] == pytest.approx(
        float(e._case_free_volume()))
    # Eşdeğer silindirin hacmi serbest hacme TAM eşit olmalı.
    hacim = np.pi * (kavite['diameter_m'] / 2.0) ** 2 * kavite['length_m']
    assert hacim == pytest.approx(kavite['free_gas_volume_m3'], rel=1e-9)
    # Serbest hacim, aynı motorun grain raporundaki değerle aynı kaynaktan.
    assert kavite['free_gas_volume_m3'] * 1000.0 == pytest.approx(
        res['grain_design']['case_free_volume_l'])


def test_akustik_chug_hukmu_uydurulmuyor(temel):
    """Katıda enjektör yok: chug marjı YAPISAL olarak değerlendirilmez."""
    blok = temel[1]['acoustic_modes']
    assert blok['chug_applicability']['applicable'] is False
    gerekce = blok['chug_applicability']['reason']
    assert 'injector' in gerekce and 'feed system' in gerekce

    chug = blok['stability_report']['chug']
    assert chug['evaluated'] is False
    assert chug['status'] == 'NOT_EVALUATED'
    assert chug['injector_dp_ratio'] is None, 'olmayan enjektörden oran türetilmiş'

    # Mod tablosu bir REZONANS ADAYI listesidir; yanma tepkisi modellenmez.
    assert 'combustion_response' in blok['not_modelled']
    assert blok['cavity_state'] == 'ignition'


def test_akustik_girdi_eksikse_not_modelled():
    e = _motor()
    e.mw_exhaust = 0.0
    blok = e._acoustic_mode_report()
    assert blok['status'] == 'NOT_MODELLED'
    assert 'molecular_weight' in blok['missing_inputs']
    assert 'modes' not in blok, 'eksik girdiyle mod tablosu yayımlanmış'


# ===========================================================================
# 3) Lüle iç akışı + ayrılma — hrma.flow.quasi1d / hrma.flow.separation
# ===========================================================================

def test_lule_akis_blogu_hesaplandi_ve_korunumlu(temel):
    e, res = temel
    blok = res['nozzle_flow_quasi1d']
    assert blok['status'] == 'computed', blok.get('basis')

    # Alan profili YAYIMLANAN konturdan kurulmuş olmalı (ikinci geometri yok).
    kontur = res['nozzle_contour']['points']
    assert len(blok['x_m']) == len(kontur)
    assert blok['x_m'][0] == pytest.approx(kontur[0][0])
    assert blok['area_m2'][0] == pytest.approx(np.pi * kontur[0][1] ** 2)

    # Çözücünün kendi öz-denetimi: kütle korunumu artığı.
    assert blok['mass_conservation_rel_residual'] < 1e-6

    p0 = float(e.P_c) * 1e5
    assert blok['inputs_used']['P0_Pa'] == pytest.approx(p0)
    assert 0.0 < blok['exit']['pressure_Pa'] < p0
    assert blok['exit']['mach'] > 1.0, 'ıraksak lülede çıkış ses-üstü olmalı'
    assert blok['throat']['index'] not in (0, len(blok['x_m']) - 1)


def test_lule_akis_debisi_cozucunun_debisiyle_ayni_mertebede(temel):
    """Birim/kaynak hatası bekçisi: iki bağımsız yol aynı debiyi vermeli.

    Yarı-1B modül debiyi izantropik boğulma bağıntısından (P0, T0, gamma, R,
    A_boğaz) kurar; katı çözücü ise mdot = Pc*A_t/c* ile. Aynı motorun aynı
    boğazında bu ikisi aynı mertebede olmak zorundadır — bar/Pa ya da mm/m
    karışması burada anında yakalanır.
    """
    e, res = temel
    a_t = e._design_throat_area()[0]
    cozucu_mdot = float(e.P_c) * 1e5 * a_t / float(e.c_star)
    modul_mdot = res['nozzle_flow_quasi1d']['mass_flow_kg_s']
    assert cozucu_mdot > 0.0 and modul_mdot > 0.0
    assert 0.5 < modul_mdot / cozucu_mdot < 2.0, (
        f'yarı-1B debi {modul_mdot} ile çözücü debisi {cozucu_mdot} '
        'mertebe olarak uyuşmuyor')


def test_ayrilma_blogu_hesaplandi_ve_esik_tek_kaynaktan(temel):
    _, res = temel
    blok = res['nozzle_flow_separation']
    assert blok['status'] == 'computed', blok.get('basis')
    assert isinstance(blok['separated'], bool)
    assert blok['full_flow_exit']['mach'] > 1.0
    assert blok['full_flow_exit']['pressure_Pa'] > 0.0
    # Eşik motorun KENDİ sabitinden geçirilir (tek tanım noktası).
    assert 'SUMMERFIELD_SEPARATION_RATIO' in blok['summerfield_factor_source']
    kriter = blok['criteria']['summerfield']
    assert kriter['pressure_ratio_threshold'] == pytest.approx(
        SUMMERFIELD_SEPARATION_RATIO)
    assert kriter['wall_pressure_sep_Pa'] == pytest.approx(
        SUMMERFIELD_SEPARATION_RATIO * blok['ambient_pressure_Pa'])


def test_asiri_genislemede_ayrilma_gercekten_yakalaniyor(asiri_genisleyen):
    """Pozitif dal: 2 bar geri basınçta çalışan düşük-Pc motorda ayrılma."""
    e, res = asiri_genisleyen
    assert not res.get('error'), res.get('error')
    akis = res['nozzle_flow_quasi1d']
    ayrilma = res['nozzle_flow_separation']
    assert akis['status'] == 'computed'
    assert ayrilma['status'] == 'computed'

    # Geri basınç kullanıcının verdiği ortam basıncından gelir.
    assert akis['inputs_used']['Pb_Pa'] == pytest.approx(
        float(e.ambient_pressure_bar) * 1e5)
    assert akis['regime'] in ('overexpanded', 'normal_shock_in_nozzle')

    assert ayrilma['separated'] is True
    assert ayrilma['controlling_criterion']
    x_sep = ayrilma['x_sep_m']
    assert x_sep is not None
    # Ayrılma konumu lülenin İÇİNDE, boğazın aşağısında olmalı.
    assert akis['throat']['x_m'] <= x_sep <= akis['x_m'][-1]
    assert ayrilma['area_ratio_sep'] > 1.0


def test_kontur_yoksa_iki_blok_da_not_modelled():
    """Kontur üretilemediyse uydurma alan profili kurulmaz."""
    e = _motor()
    akis, ayrilma = e._nozzle_flow_field_report(None)
    for blok in (akis, ayrilma):
        assert blok['status'] == 'NOT_MODELLED'
        assert 'nozzle_contour' in blok['missing_inputs']
        assert 'regime' not in blok and 'separated' not in blok


# ===========================================================================
# 4) Ateşleyici — hrma.analysis.igniter_sizing (piroteknik şarj yolu)
# ===========================================================================

def test_atesleyici_sarj_kutlesi_moduleden_geliyor(temel):
    """Şarj kütlesi artık motorda elle YAZILMAZ, modülden çağrılır."""
    e, res = temel
    grain = res['cad_design']['igniter_system']['igniter_grain']
    assert grain['mass_status'] == 'sized'
    assert 'igniter_sizing.pyrotechnic_charge_mass' in grain['sizing_module']

    kayit = _get_propellant_safe(SOLID_IGNITER['charge_record'])
    beklenen = pyrotechnic_charge_mass(
        ignition_pressure_Pa=grain['ignition_pressure_bar'] * 1e5,
        free_volume_m3=e._case_free_volume(),
        gas_molecular_weight_g_mol=float(kayit['molecular_weight']),
        gas_temperature_K=float(kayit['flame_temperature']),
        condensed_mass_fraction=float(
            SOLID_CONDENSED_MASS_FRACTION[SOLID_IGNITER['charge_record']]))
    assert grain['mass'] == pytest.approx(
        beklenen['charge_mass_kg'] * 1000.0, rel=1e-12)
    assert grain['gas_mass_g'] == pytest.approx(
        beklenen['gas_mass_kg'] * 1000.0, rel=1e-12)
    # Serbest hacim ateşleyici ile grain raporunda AYNI kaynaktan.
    assert grain['free_volume_l'] == pytest.approx(
        res['grain_design']['case_free_volume_l'])


def test_atesleyici_uygulanmayan_yollar_adiyla_beyanli(temel):
    """Modülün bağlanmayan iki yolu sessizce atlanmaz, gerekçesiyle beyan edilir."""
    beyan = temel[1]['cad_design']['igniter_system']['ignition_energy_and_window']
    assert beyan['status'] == 'NOT_MODELLED'

    enerji = beyan['ignition_energy']
    assert enerji['status'] == 'NOT_MODELLED'
    assert set(enerji['missing_inputs']) == {
        'propellant_specific_heat_J_kg_K',
        'propellant_ignition_temperature_K'}
    # Beyan yalan olmasın: bu iki özellik gerçekten yakıt kaydında yok.
    kayit = _get_propellant_safe('apcp') or {}
    assert 'specific_heat' not in kayit
    assert not [k for k in kayit if 'ignition_temp' in k]

    assert beyan['torch_path']['status'] == 'NOT_APPLICABLE'
    assert beyan['safe_ignition_window']['status'] == 'NOT_APPLICABLE'


# ===========================================================================
# 5) Bloklar TEŞHİS amaçlıdır — performansa geri beslenmez
# ===========================================================================

def test_bloklar_performansa_geri_beslenmiyor(monkeypatch):
    """Üç blok da NOT_MODELLED'e düşürülünce performans BİT-AYNI kalmalı.

    Bir blok Isp'ye, c*'a ya da geometriye uygulansaydı bloğun kaybolması
    sayıları oynatırdı — bu bekçi çift sayımın kapısını kilitler.
    """
    referans = _motor().calculate_performance()

    e = _motor()
    monkeypatch.setattr(e, '_two_phase_loss_report',
                        lambda *a, **k: {'status': 'NOT_MODELLED'})
    monkeypatch.setattr(e, '_acoustic_mode_report',
                        lambda *a, **k: {'status': 'NOT_MODELLED'})
    monkeypatch.setattr(e, '_nozzle_flow_field_report',
                        lambda *a, **k: ({'status': 'NOT_MODELLED'},
                                         {'status': 'NOT_MODELLED'}))
    kisitli = e.calculate_performance()

    for alan in ('specific_impulse', 'isp_vacuum', 'total_impulse', 'c_star',
                 'throat_diameter', 'exit_diameter', 'expansion_ratio',
                 'average_thrust', 'max_thrust', 'burn_time'):
        assert kisitli[alan] == referans[alan], (
            f"'{alan}' bağlanan bloklara bağımlı hale gelmiş — bloklar "
            'teşhis amaçlıdır, performansa geri beslenemez')


# ===========================================================================
# 6) A7 — belirsizlik katıda ZATEN bağlı: doğrula (yeni bağlama yapılmaz)
# ===========================================================================

def test_belirsizlik_katida_bagli_ve_calisiyor():
    from hrma.analysis import uq_adapters as uqa
    from hrma.analysis.uncertainty import run_uncertainty

    dagilimlar = uqa.build_distributions('solid')
    assert dagilimlar, 'katı için belirsiz girdi dağılımı tanımlı değil'

    fabrika = uqa.make_solid_factory(dict(TEMEL_MOTOR))
    sonuc = run_uncertainty(fabrika, dagilimlar, n_samples=8, seed=7)
    assert sonuc.get('status') == 'success', sonuc.get('error')
    assert sonuc.get('failed_samples', 0) == 0

    ciktilar = sonuc.get('outputs') or {}
    assert set(uqa.CONTRACT_OUTPUTS['solid']) <= set(ciktilar), (
        'sözleşmede yazan katı UQ çıktılarının hepsi üretilmemiş')
    for ad, istatistik in ciktilar.items():
        assert np.isfinite(istatistik['mean']), f'{ad} ortalaması sonlu değil'
