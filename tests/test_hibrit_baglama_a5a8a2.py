"""Hibrit motora A5+A8+A2 modül bağlama bekçileri (v2.6.27, yol haritası).

Üç bağlamayı kilitler (docs/YOL_HARITASI_2.7_VE_SONRASI.md Kulvar A —
üçü de "modül yazılı, hibrite bağlı değil" durumundaydı):

* **A5** — ``thermal_protection`` → hibrit: kamara yalıtım astarı (Seviye-1
  Q* ablasyon boyutlandırması, katı motorun kapak yalıtımı şemasıyla aynı
  alan adları) + çıplak cidar 1B ısı-yutucu sıcaklık geçmişi. Girdiler
  motorun KENDİ ısı transferi sonucundan (Bartz kamara/boğaz akıları,
  kurtarma sıcaklığı) ve zaman-adımlı çözücünün etkin yanma süresinden.
* **A8** — ``launch_site`` → hibrit: rakım/ortam düzeltmesi. Saha atmosferi
  sıvı/katı irtifa tablolarının kullandığı AYNI merkezi ISA kaynağından;
  itki düzeltmesi basınç-itki özdeşliği F_saha − F_tasarım =
  (P_a,tasarım − P_a,saha)·A_e (Sutton & Biblarz 9. baskı Denk. 2-14).
  KRİTİK: Isp her sahada STANDART g0 ile raporlanır (launch_site modülünün
  sözleşmesi); yerel g yalnız ağırlık/T-W için ayrı alanda yayımlanır.
* **A2** — ``slosh_analysis`` → hibrit oksitleyici tankı: NASA SP-106 /
  Dodge doğrusal çalkantı modeli. Tank hacmi/doluluğu blowdown bloğundan
  (aynı tank için iki farklı hacim yasak), sıvı kütlesi çözücünün m_ox'u,
  çap beyanlı L/D tasarım oranından; g_eff SABİT 1 g beyanıyla (uçuş
  ivmesi/yörünge bağlaşımı sonraki iş — blokta NOT_MODELLED notu).

Bekçiler gerçek hesap koşar: değerlerin fiziksel aralıkta olduğu, _basis
beyanlarının bulunduğu ve girdi eksikken bloğun SAYI İÇERMEDEN beyanla boş
döndüğü sınanır. A10 tarafı: bu bağlamalarla çürüyen iki beyanın
(``thermal_protection_liner``, ``oxidizer_tank_structure_slosh``) sonuçta
artık YER ALMADIĞI da burada kilitlenir (tests/test_hibrit_beyan_a10.py
yalnız beklenen kümenin varlığını sınar, bayat beyanı yakalamaz).
"""

import json
import warnings

import numpy as np
import pytest

from hrma.constants import G_0
from hrma.engines.hybrid_rocket_engine import (
    OX_TANK_LD_RATIO,
    HybridRocketEngine,
)

SAHA_RAKIM_M = 2000.0
SAHA_ENLEM_DEG = 39.9


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
def saha_motor():
    """2000 m rakımlı saha girdisiyle koşulmuş varsayılan görev."""
    return _kos(launch_site={'elevation_m': SAHA_RAKIM_M,
                             'latitude_deg': SAHA_ENLEM_DEG})


@pytest.fixture(scope='module')
def sahasiz_motor():
    """Saha girdisi verilmemiş aynı görev (A8 boş-blok beyanı için)."""
    return _kos()


# ---------------------------------------------------------------------------
# A5 — thermal_protection bağlaması
# ---------------------------------------------------------------------------

def test_a5_astar_boyutlari_gercek_akidan(saha_motor):
    _, sonuc = saha_motor
    tp = sonuc['thermal_protection']
    assert tp['status'] == 'modelled'
    assert tp['_basis'], 'blok gerekçesiz yayımlanamaz'

    gs = sonuc['heat_transfer_analysis']['gas_side_analysis']
    q_kamara_kw = float(gs['chamber_heat_flux']) / 1e3
    q_bogaz_kw = float(gs['throat_heat_flux']) / 1e3

    # B6 sözleşmesi (14 Ağu 2026): astar YÜZEY ENERJİ DENGESİYLE sürülür
    # (soğuk-cidar akısı yalnız karşılaştırma değeri) ve geçerlilik kapısını
    # geçemeyen istasyona sayı YAYIMLANMAZ. Eski bekçi 'thickness > 0' diyerek
    # kusuru koruyordu (NASA TM-107041'e karşı ~109x fazla tahmin).
    def _sozlesme(blok):
        """Enerji dengesi sözleşmesi: hüküm hangisiyse TUTARLI olmalı.

        Üç meşru hüküm vardır ve hangisinin çıkacağı GÖREVE bağlıdır
        (fikstür motoru değişirse hüküm değişebilir; bekçi sonucu değil
        sözleşmeyi kilitler):
        1. zarf dışı      -> NOT_MODELLED + kalınlık None + model_valid False,
        2. net ısınma yok -> NOT_MODELLED + kalınlık None + model_valid True
           (GÜNCELLEME 15 Ağu 2026: eskiden 'sized + 0,0 mm' idi. 0,0 mm bir
           tasarım değildir — gerileme sıfırken kalınlığı kasa/bond sıcaklık
           sınırı (iletim/char, SP-8093 pratiği) belirler ve modül onu
           modellemez; çekirdek artık bu rejimde kalınlık YAYIMLAMAZ),
        3. ablasyon       -> sized + bant içi hız + kalınlık özdeşliği.
        """
        assert blok['flux_basis'] == 'surface_energy_balance'
        assert blok['h_gas_W_m2K'] > 0 and blok['T_surface_K'] > 0
        assert blok['model_note'] and blok['source']
        # v2.6.27 blokaj denetimi: psi sabit değil ÇÖZÜLMÜŞ değerdir ve
        # türetimi beyan edilir.
        assert 0.0 < blok['blowing_blockage'] <= 1.0
        assert blok['blockage_basis']
        if blok['thickness_status'] == 'NOT_MODELLED':
            assert blok['thickness'] is None
            assert blok['validity_note']
            if blok['recession_regime'] == 'no_net_heating':
                # Hüküm 2: model zarfın İÇİNDE, kalınlık dürüstçe yok.
                assert blok['model_valid'] is True
                assert 'NO NET HEATING' in blok['validity_note']
                assert blok['recession_rate_mm_s'] == 0.0
                assert blok['total_recession_mm'] == 0.0
                # Üfleme yoksa blokaj da yoktur (psi = 1 zorunlu).
                assert blok['blowing_blockage'] == 1.0
            else:
                # Hüküm 1: zarf dışı.
                assert blok['model_valid'] is False
            return
        assert blok['thickness_status'] == 'sized'
        assert blok['recession_regime'] == 'steady_ablation', (
            'no_net_heating artık sized olamaz — çekirdek kalınlık '
            'yayımlamaz (15 Ağu 2026 sözleşmesi)')
        assert 'design choice' in blok['basis'], (
            'astar malzemesi bir tasarım seçimidir ve öyle beyan edilmeli')
        # Kalınlık = çekilme x tasarım payı özdeşliği (Q* modelinin tanımı)
        assert blok['thickness'] == pytest.approx(
            blok['total_recession_mm'] * blok['design_margin'], rel=1e-9)
        # Fiziksel aralık + kapı sözleşmesi: 'sized' hüküm ancak
        # ölçülmüş geçerlilik tavanının altında verilebilir.
        assert 0.05 < blok['thickness'] < 200.0   # mm
        assert 0 < blok['recession_rate_mm_s'] <= 0.35

    astar = tp['chamber_liner']
    # Karşılaştırma akısı motorun KENDİ kamara akısıdır, kopya/uydurma değil
    assert astar['heat_flux_kw_m2'] == pytest.approx(q_kamara_kw, rel=1e-9)
    _sozlesme(astar)

    giris = tp['nozzle_entry_liner']
    assert giris['heat_flux_kw_m2'] == pytest.approx(q_bogaz_kw, rel=1e-9)
    # Boğaz akısı kamara akısından büyük -> gerileme hızı ondan küçük olamaz
    assert giris['heat_flux_kw_m2'] > astar['heat_flux_kw_m2']
    assert giris['recession_rate_mm_s'] >= astar['recession_rate_mm_s']
    _sozlesme(giris)
    assert 'UPPER bound' in giris['basis'], (
        'boğaz akısıyla boyutlama konservatif üst sınırdır; beyan şart')


def test_a5_cidar_sicaklik_gecmisi_fiziksel(saha_motor):
    motor, sonuc = saha_motor
    wh = sonuc['thermal_protection']['wall_temperature_history']
    assert wh['status'] == 'modelled'
    assert wh['wall_material'] == motor.chamber_material
    assert wh['wall_thickness_m'] == pytest.approx(motor.wall_thickness)
    assert wh['h_eff_W_m2K'] > 0
    assert 'single source' in wh['h_eff_basis'], (
        'h_eff ısı modülünün kendi akısından geri çözülür; ikinci Bartz yok')

    t = wh['time_s']
    tw = wh['wall_inner_temperature_K']
    assert len(t) == len(tw)
    # Yanıt boyutu sınırlı (port_history deseni), son nokta korunur
    assert 2 < len(t) <= 240
    assert t[0] == pytest.approx(0.0)
    assert t[-1] == pytest.approx(
        sonuc['thermal_protection']['burn_time_s'], rel=1e-6)
    # Sabit sürücülü ısı-yutucu: iç cidar tekdüze ısınır ve kurtarma
    # sıcaklığının altında kalır
    assert all(b >= a - 1e-9 for a, b in zip(tw, tw[1:]))
    assert tw[-1] > tw[0] + 50.0, 'yanma boyunca cidar gözle görülür ısınmalı'
    assert wh['T_initial_K'] < wh['T_inner_final_K'] < wh['T_recovery_K']
    assert tw[-1] == pytest.approx(wh['T_inner_final_K'], rel=1e-9)
    # Zarf alanları sözleşmede: sınır/erime hükümleri saklanamaz
    for alan in ('max_service_temp_K', 'exceeds_limit', 'time_to_limit_s',
                 'melting_point_K', 'exceeds_melting', 'model_valid'):
        assert alan in wh
    assert 'no liner credit' in wh['basis'], (
        'geçmiş ÇIPLAK cidarındır; astarla kuple değil — beyan şart')


def test_a5_isi_girdisi_yoksa_beyanla_bos(saha_motor):
    motor, _ = saha_motor
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sonuc = motor._compile_results()  # ısı transferi sonucu verilmedi
    tp = sonuc['thermal_protection']
    assert tp['status'] == 'NOT_MODELLED'
    assert 'heat transfer' in tp['reason']
    assert 'thickness' not in tp, 'girdisiz blokta sayı olamaz'


# ---------------------------------------------------------------------------
# A8 — launch_site bağlaması
# ---------------------------------------------------------------------------

def test_a8_saha_duzeltmesi_basinc_itki_ozdesligi(saha_motor):
    motor, sonuc = saha_motor
    ls = sonuc['launch_site_performance']
    assert ls['status'] == 'modelled'
    assert ls['_basis']
    assert ls['elevation_m'] == pytest.approx(SAHA_RAKIM_M)

    # ISA 2000 m: ~0.795 bar / ~275 K (USSA 1976) — merkezi kaynaktan
    assert 0.75 < ls['ambient_pressure_bar'] < 0.85
    assert 270.0 < ls['ambient_temperature_k'] < 280.0
    assert ls['ambient_pressure_bar'] < ls['design_ambient_pressure_bar']

    # Basınç-itki özdeşliği motorun KENDİ değerleriyle (Sutton Denk. 2-14)
    beklenen_delta = (float(motor.P_a) * 1e5
                      - ls['ambient_pressure_pa']) * float(motor.Ae)
    assert ls['thrust_delta_N'] == pytest.approx(beklenen_delta, rel=1e-9)
    assert ls['thrust_site_N'] == pytest.approx(
        float(motor.F) + beklenen_delta, rel=1e-9)
    # Rakımda ortam düşer -> itki ARTAR (işaret fizikle tutarlı)
    assert ls['thrust_delta_N'] > 0
    assert 0.0 < ls['thrust_change_percent'] < 20.0


def test_a8_isp_standart_g0_ile_yerel_g_ayri(saha_motor):
    motor, sonuc = saha_motor
    ls = sonuc['launch_site_performance']
    # Isp zinciri STANDART g0 — yerel g ile bölmek klasik sessiz hatadır
    assert ls['gravity_standard_m_s2'] == pytest.approx(G_0)
    assert ls['isp_site_s'] == pytest.approx(
        ls['thrust_site_N'] / (float(motor.mdot_total) * G_0), rel=1e-9)
    assert '9.80665' in ls['gravity_basis']
    # Yerel g (WGS84, 39.9° + 2000 m): standarttan farklı ve dar fiziksel bant
    assert ls['gravity_local_m_s2'] is not None
    assert 9.74 < ls['gravity_local_m_s2'] < 9.84
    assert ls['gravity_local_m_s2'] != pytest.approx(G_0, abs=1e-6)
    # Yeniden değerlendirilmeyenler açıkça beyanlı
    assert any('separation' in n for n in ls['not_modelled'])


def test_a8_sahasiz_beyanla_bos(sahasiz_motor):
    _, sonuc = sahasiz_motor
    ls = sonuc['launch_site_performance']
    assert ls['status'] == 'NOT_MODELLED'
    assert 'no launch site' in ls['reason']
    assert 'thrust_site_N' not in ls, 'girdisiz blokta sayı olamaz'


def test_a8_kullanilamaz_girdi_gerekceyle_bos():
    """Sözlük olmayan saha girdisi sessizce yutulmaz; blok nedenini söyler."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(thrust=1000, burn_time=10, of_ratio=2.5,
                                   chamber_pressure=20.0,
                                   track_performance=False,
                                   launch_site='Ankara')
    blok = motor._launch_site_block()
    assert blok['status'] == 'NOT_MODELLED'
    assert 'not a usable dict' in blok['reason']
    assert 'Ankara' in blok['reason']


# ---------------------------------------------------------------------------
# A2 — slosh_analysis bağlaması (oksitleyici tankı)
# ---------------------------------------------------------------------------

def test_a2_slosh_gercek_tank_geometrisiyle(saha_motor):
    motor, sonuc = saha_motor
    blok = sonuc['oxidizer_tank_slosh']
    assert blok['status'] == 'modelled'
    assert blok['_basis']

    # Tek tank, tek hacim: blowdown bloğu koştuysa hacim ORADAN gelir
    blowdown = sonuc['tank_blowdown']
    assert blowdown['status'] == 'modelled', (
        'varsayılan N2O motorunda blowdown bloğu koşmalı (A1); koşmuyorsa '
        'bu test ortamı A1 bekçisiyle birlikte incelenmeli')
    assert blok['tank_volume_m3'] == pytest.approx(
        blowdown['tank_volume_m3'], rel=1e-9)
    assert blok['liquid_fill_fraction'] == pytest.approx(
        blowdown['liquid_fill_fraction'])
    assert 'tank_blowdown' in blok['tank_volume_source']

    # Geometri özdeşlikleri: V = (π/4)·D²·L, L = D·(L/D), h = doluluk·L
    d, l = blok['tank_diameter_m'], blok['tank_length_m']
    assert l == pytest.approx(d * OX_TANK_LD_RATIO, rel=1e-9)
    assert np.pi / 4.0 * d ** 2 * l == pytest.approx(
        blok['tank_volume_m3'], rel=1e-9)
    assert blok['fill_height_m'] == pytest.approx(
        blok['liquid_fill_fraction'] * l, rel=1e-6)
    assert blok['tank_ld_ratio_basis'], 'L/D bir tasarım seçimidir; beyan şart'

    # Sıvı kütlesi çözücünün m_ox'u; yoğunluk fiziksel sıvı N2O bandında
    assert blok['liquid_mass_kg'] == pytest.approx(float(motor.m_ox))
    assert 600.0 < blok['liquid_density_kg_m3'] < 1000.0

    s = blok['slosh']
    # Modal büyüklükler fiziksel aralıkta (bu ölçekte tank: birkaç Hz)
    assert 0.3 < s['f1_hz'] < 15.0
    assert 0.0 < s['slosh_mass_ratio'] < 1.0
    assert 0.0 < s['slosh_mass_kg'] < blok['liquid_mass_kg']
    assert s['pendulum_length'] > 0
    # SP-106 frekans bağıntısının kendisiyle çapraz sağlama
    lam1 = 1.8412
    r = blok['tank_diameter_m'] / 2.0
    omega2 = (lam1 * blok['g_eff_m_s2'] / r) * np.tanh(
        lam1 * blok['fill_height_m'] / r)
    assert s['f1_hz'] == pytest.approx(np.sqrt(omega2) / (2 * np.pi),
                                       rel=1e-6)
    # Bafl ihtiyacı: hedef sönümlemeye halka genişliği önerisi
    assert 0.0 < s['baffle']['recommended_width_ratio'] <= 1.0
    assert s['baffle']['confidence'] == 'approximate'


def test_a2_g_eff_sabit_1g_beyanli(saha_motor):
    _, sonuc = saha_motor
    blok = sonuc['oxidizer_tank_slosh']
    assert blok['g_eff_m_s2'] == pytest.approx(G_0)
    # Yörünge/uçuş ivmesi bağlaşımı SONRAKİ iş — açık NOT_MODELLED notu
    assert 'NOT_MODELLED' in blok['g_eff_basis']
    assert 'T/m' in blok['g_eff_basis']


def test_a2_cozum_yokken_beyanla_bos():
    """calculate() koşmadan blok sayı üretemez."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(thrust=1000, burn_time=10, of_ratio=2.5,
                                   chamber_pressure=20.0,
                                   track_performance=False)
    blok = motor._oxidizer_tank_slosh_block(None)
    assert blok['status'] == 'NOT_MODELLED'
    assert 'not solved' in blok['reason']
    assert 'slosh' not in blok, 'girdisiz blokta sayı olamaz'


def test_a2_tank_ld_orani_sivi_motorla_ayni():
    """Kopya sabit bekçisi: hibrit OX_TANK_LD_RATIO == sıvı TANK_LD_RATIO.

    Motor dosyaları arası çapraz import bilinçli olarak yapılmıyor (durum
    sözlüğü notu, hybrid_rocket_engine.py); değer bu yüzden iki dosyada da
    tanımlı ve eşitliği BURADA makinece kilitli (aynı desen: DESIGN_STATUS
    sözlüğü, tests/test_faz4_motor_kapilari.py).
    """
    from hrma.engines.liquid_rocket_engine import TANK_LD_RATIO
    assert OX_TANK_LD_RATIO == TANK_LD_RATIO


# ---------------------------------------------------------------------------
# A10 etkileşimi + sözleşme
# ---------------------------------------------------------------------------

def test_curuyen_beyanlar_sonucta_yok(saha_motor):
    """A5/A2 bağlamalarıyla çürüyen beyanlar sonuçtan gerçekten kalktı.

    test_hibrit_beyan_a10 yalnız beklenen kümenin VARLIĞINI sınar; bayat
    beyanın geri gelmesini bu bekçi yakalar (yanlış beyan beyansızlıktan
    kötüdür — modellenen şeye 'modellenmiyor' demek de yalandır).
    """
    _, sonuc = saha_motor
    beyanlar = set(sonuc['not_modelled'])
    assert 'thermal_protection_liner' not in beyanlar
    assert 'oxidizer_tank_structure_slosh' not in beyanlar
    # Daralan beyan yerinde: tank YAPISI hâlâ modellenmiyor (A3 işi)
    # v2.6.27 Dalga 6: beyan DARALDI — tankın yapısal KÜTLESİ hâlâ
    # modellenmiyor ama basınçlı kap boyutlandırması artık
    # oxidizer_tank_pressure_vessel bloğunda GERÇEKTEN hesaplanıyor,
    # bu yüzden eski geniş 'oxidizer_tank_structure' adı çürüdü.
    assert 'oxidizer_tank_structural_mass' in beyanlar
    # Beyan, artık modellenen parçaları GERÇEKTEN modelleyen bloğa atıf
    # yapmalı — yoksa "modellenmiyor" derken yalan söylemiş olur. Metnin
    # kendisine değil ATIFA bakıyoruz: prosa değişebilir, sözleşme değişmez.
    metin = sonuc['not_modelled']['oxidizer_tank_structural_mass']
    assert 'oxidizer_tank_slosh' in metin, (
        'beyan, çalkalanmanın nerede modellendiğini söylemiyor')
    assert 'oxidizer_tank_pressure_vessel' in metin, (
        'beyan, cidar boyutlandırmasının nerede modellendiğini söylemiyor')


def test_yeni_bloklar_json_serilestirilebilir(saha_motor, sahasiz_motor):
    for _, sonuc in (saha_motor, sahasiz_motor):
        json.dumps({
            'thermal_protection': sonuc['thermal_protection'],
            'launch_site_performance': sonuc['launch_site_performance'],
            'oxidizer_tank_slosh': sonuc['oxidizer_tank_slosh'],
        })
