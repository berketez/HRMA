"""v3.0.1 · kulvar P — yanma sonu port çapı ⟷ kamara (grain dış) çapı.

Ayberk (tur 1): "End of burn port neden yanma odası çapına eşit olmuyor da
daha önce bitiyor?"

KİLİTLENEN KUSUR (ölçüm: docs/scofield/raw/OH/V301/ayberk1/port-kamara/
once.json, taban c6fc59aad): kamara çapı verilmeyince
``D_ch = 1,5·√N·D_port_son`` uygulanıyordu (1,5 kaynaksız). Varsayılan
hibritte (1 kN, 10 s, Pc 20 bar, O/F 2,5, HTPB/N2O) D_son 53,76 mm, kamara
80,64 mm; yüklenen 5,579 kg yakıtın 1,579 kg'ı yanıyor, %71,7'si yanmadan
uçuyordu. Kullanıcı kamara çapı verdiğinde ise kaynaksız bir
port <= 0,8·D_ch/√N oranı yanmayı kırpıyordu.

YENİ KURAL (ana model kararı; dayanak Karabeyoglu, Cantwell & Zilliac,
JPP 23(4) 2007 §VI.B s. 745 — birincil metinde doğrulandı):
    N = 1 : D_o = D_son + 2·t
    N >= 2: D_o = D_son·(1 + 1/sin(π/N)) + 2·t   (tek halka, teğet)
Kullanıcı kamara çapı korunur; son portlar sığmıyorsa adlı ret (uçta 422).

TERS MUTASYON (rapor: RAPOR.md): ``calculate`` içindeki otomatik
boyutlandırma eski ``D_son·√N·1,5`` satırına geri konunca bu dosyanın
oran / artık-yakıt bekçileri KIRMIZI; zarf kapısı eski 0,8·D_ch/√N
kırpmasına geri konunca kapı bekçileri KIRMIZI.
"""

import json
import math
import re
import warnings
from pathlib import Path

import pytest

from hrma.engines import hybrid_rocket_engine as hre
from hrma.engines.hybrid_rocket_engine import (
    GrainEnvelopeError,
    HybridRocketEngine,
    grain_outer_diameter_for_ports_m,
    grain_port_layout_factor,
    max_port_diameter_in_envelope_m,
    resolve_residual_web_input,
)

DEPO = Path(__file__).resolve().parents[1]
TEMEL = dict(of_ratio=2.5, chamber_pressure=20, atmospheric_pressure=1.0,
             fuel_type='htpb', oxidizer_type='n2o')


def _kos(**kw):
    ayar = dict(TEMEL)
    ayar.update(kw)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(**ayar)
        return motor, motor.calculate()


@pytest.fixture(scope='module')
def varsayilan():
    return _kos(thrust=1000, burn_time=10)


@pytest.fixture(scope='module')
def artik_et_3mm():
    return _kos(thrust=1000, burn_time=10, residual_web_thickness=3.0)


@pytest.fixture(scope='module')
def dort_port():
    return _kos(thrust=1000, burn_time=10, port_count=4)


@pytest.fixture(scope='module')
def kullanici_kamara_100():
    return _kos(thrust=1000, burn_time=10, chamber_diameter_input=100)


# ---------------------------------------------------------------------------
# 1. GEOMETRİ — halka katsayısı bağımsız koordinat hesabıyla
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('n', [2, 3, 4, 5, 6, 7, 8])
def test_tek_halka_katsayisi_koordinattan_bagimsiz_olculur(n):
    """N port (çap d) merkezleri R yarıçaplı çemberde, komşular teğet ve
    dış zarfa teğet: zarf çapı koordinatlardan ölçülür, formülden değil."""
    d = 1.0
    R = d / (2.0 * math.sin(math.pi / n))       # komşu merkez aralığı = d
    merkez = [(R * math.cos(2 * math.pi * i / n),
               R * math.sin(2 * math.pi * i / n)) for i in range(n)]
    en_yakin = min(math.dist(merkez[i], merkez[j])
                   for i in range(n) for j in range(i + 1, n))
    assert en_yakin == pytest.approx(d, rel=1e-12)   # portlar ÖRTÜŞMEZ
    zarf = 2.0 * max(math.hypot(x, y) + d / 2.0 for x, y in merkez)
    assert grain_port_layout_factor(n) == pytest.approx(zarf / d, rel=1e-12)


def test_tek_port_katsayisi_bir_ve_n_kapisi():
    assert grain_port_layout_factor(1) == 1.0
    with pytest.raises(ValueError):
        grain_port_layout_factor(0)


def test_zarf_ve_ters_fonksiyon_birbirinin_tersi():
    for n in (1, 2, 4, 7):
        for t in (0.0, 0.002):
            d_o = grain_outer_diameter_for_ports_m(0.05, n, t)
            assert max_port_diameter_in_envelope_m(d_o, n, t) == \
                pytest.approx(0.05, rel=1e-12)


def test_kok_karesi_n_kurali_portlari_sigdirmaz():
    """√N·D yalnız toplam alanı korur; N >= 2'de tek halka zarfından
    küçüktür, yani portlar o çapa SIĞMAZ (Astra; geometrik özdeşlik)."""
    for n in range(2, 9):
        assert math.sqrt(n) < grain_port_layout_factor(n)


# ---------------------------------------------------------------------------
# 2. OTOMATİK BOYUTLANDIRMA — 1,5 kuralının geri dönüşüne karşı bekçi
# ---------------------------------------------------------------------------

def test_varsayilan_kamara_son_port_capina_esit(varsayilan):
    """N = 1, t = 0: grain dış çapı = yanma sonu port çapı (BİT-ÖZDEŞ).

    Ters mutasyon: D_ch = 1,5·√N·D_son geri konunca oran 1,5 olur.
    """
    motor, sonuc = varsayilan
    assert motor.D_ch == motor.D_port_final
    g = sonuc['grain_design']
    assert g['grain_outer_diameter_mm'] == pytest.approx(
        g['port_diameter_final_mm'], rel=1e-12)
    assert sonuc['chamber_diameter'] == motor.D_port_final


def test_varsayilan_artik_yakit_sifir(varsayilan):
    motor, sonuc = varsayilan
    assert motor.m_f_residual == 0.0
    assert sonuc['fuel_sliver_fraction'] == 0.0
    assert sonuc['fuel_mass_loaded'] == pytest.approx(sonuc['fuel_mass'],
                                                      rel=1e-12)
    # Ölçülen kusur %71,7 idi — bekçi iddiayı literal çapaya karşı da sınar.
    assert sonuc['fuel_sliver_fraction'] < 0.717 - 0.5


def test_artik_et_dis_capa_iki_kat_eklenir(artik_et_3mm):
    motor, sonuc = artik_et_3mm
    assert motor.D_ch == pytest.approx(motor.D_port_final + 2 * 0.003,
                                       rel=1e-12)
    g = sonuc['grain_design']
    assert g['residual_web_mm'] == pytest.approx(3.0)
    assert g['residual_web_source'] == 'user_input'
    assert sonuc['residual_web_mm'] == pytest.approx(3.0)
    assert 0.0 < sonuc['fuel_sliver_fraction'] < 1.0


def test_dort_port_tek_halka(dort_port):
    motor, sonuc = dort_port
    assert motor.D_ch / motor.D_port_final == pytest.approx(
        1.0 + math.sqrt(2.0), rel=1e-12)
    kural = sonuc['grain_design']['grain_sizing_rule']
    assert kural['port_layout'] == 'single_ring_tangent_at_burnout'
    assert kural['layout_factor'] == pytest.approx(1.0 + math.sqrt(2.0))
    # Çok portta portlar arası ara bölgelerde yakıt KALIR (doğal artık).
    assert sonuc['fuel_sliver_fraction'] > 0.0


def test_yedi_port_halka_ve_en_siki_degil_beyani():
    motor, sonuc = _kos(thrust=1000, burn_time=10, port_count=7)
    assert motor.D_ch / motor.D_port_final == pytest.approx(
        1.0 + 1.0 / math.sin(math.pi / 7), rel=1e-12)
    assert 'not the densest' in \
        sonuc['grain_design']['grain_sizing_rule']['layout_note']


# ---------------------------------------------------------------------------
# 3. KÜTLE DENKLİĞİ — yüklenen = yanan + artık (üç ayrı alan ifadesi)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('ad', ['varsayilan', 'artik_et_3mm', 'dort_port',
                                'kullanici_kamara_100'])
def test_kutle_denkligi(ad, request):
    motor, sonuc = request.getfixturevalue(ad)
    yuklu = sonuc['fuel_mass_loaded']
    yanan = sonuc['fuel_mass']
    artik = sonuc['fuel_mass_residual_kg']
    assert yuklu == pytest.approx(yanan + artik, rel=1e-12, abs=1e-15)
    assert sonuc['fuel_sliver_fraction'] == pytest.approx(
        artik / yuklu, rel=1e-12, abs=1e-15)
    # Alanlardan bağımsız yeniden hesap (yoğunluk · boy · halka alanı).
    n = sonuc['port_count']
    beklenen_artik = (motor.rho_f * math.pi / 4.0 * motor.L_grain
                      * (motor.D_ch ** 2 - n * motor.D_port_final ** 2))
    assert artik == pytest.approx(beklenen_artik, rel=1e-12, abs=1e-15)


# ---------------------------------------------------------------------------
# 4. İTKİ / SÜRE değişmez; impuls grain dış çapından bağımsız kalır
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('ad', ['varsayilan', 'artik_et_3mm', 'dort_port'])
def test_itki_ve_sure_degismez(ad, request):
    _motor, sonuc = request.getfixturevalue(ad)
    assert sonuc['thrust'] == 1000.0
    assert sonuc['burn_time'] == 10.0
    assert sonuc['burn_time_clipped'] is False
    # Teslim edilen impuls eğrinin kendi integralidir; O/F kayması dışında
    # F·t_b'den sapmaz (ölçüm: önce 10000,4984, sonra 10000,4981 Ns).
    # V301/B7 (21 Eki, ÖNEMLİ, Berke onaylı): O/F 2,5 N2O/HTPB yakıtça zengin
    # bölgede; dengeye katı karbon C(gr) girince c*(O/F) eğrisinin şekli
    # değişti (tasarım c* 1307,4 → 1370,8 m/s; CEA 1371,0) ve O/F kaymasının
    # impulsa etkisi büyüdü. Ölçüldü (yoğun yol kapalı ⟷ açık):
    #   varsayilan 10000,4981 → 9976,0370 Ns (−%0,245)
    #   artik_et_3mm 10000,4982 → 9976,0369 Ns (−%0,245)
    #   dort_port 10002,1398 → 9960,5781 Ns (−%0,394)
    # Tolerans ölçülen en büyük kaymanın üstüne (%0,5) alındı; bekçinin
    # konusu (port/kamara değişikliği itkiyi/süreyi bozmasın) yukarıdaki
    # birebir itki/süre eşitlikleriyle ve aşağıdaki önce-ölçümü testiyle
    # korunur. Kanıt: docs/scofield/raw/OH/V301/makale1/B7/hibrit_capa.json
    assert sonuc['total_impulse'] == pytest.approx(1e4, rel=5e-3)


def test_once_olcumune_karsi_impuls_ve_debi_sapmasi_kucuk(varsayilan):
    """Grain dış çapı yalnız kinetik verim zinciri (gerçekleşen L*) yoluyla
    Isp'ye dokunur; ölçülen sapma %0,01 mertebesinde kalmalı."""
    once = json.loads((DEPO / 'docs/scofield/raw/OH/V301/ayberk1/'
                       'port-kamara/once.json').read_text(encoding='utf-8'))
    o = once['tasarimlar']['A_varsayilan_1kN']['ozet']
    _m, sonuc = varsayilan
    # V301/B7 (21 Eki, ÖNEMLİ, Berke onaylı): port-kamara önce ölçümü
    # gaz-yalnız dengeyle alınmıştı. Dengeye katı karbon C(gr) girince bu
    # O/F 2,5 tasarımının sayıları B7 kanıtıyla değişti; port-kamara
    # karşılaştırması artık B7'nin ölçtüğü çarpanla yapılır (yoğun yol
    # kapalı ⟷ açık, aynı tasarım; hibrit_capa.json):
    #   impuls 10000,49813672308 → 9976,037043860768 Ns
    #   Isp    180,8526872785283 → 189,97017865866127 s  (c* +%4,85)
    #   ṁ      0,5638380210560432 → 0,5367769931985777 kg/s
    # Port-kamara önce değeri (10000,4984 Ns) yoğun yol kapalı ölçümle
    # 1e-6 içinde aynıdır, yani çarpan yalnız B7 etkisini taşır.
    b7_impuls = 9976.037043860768 / 10000.49813672308
    b7_isp = 189.97017865866127 / 180.8526872785283
    assert sonuc['total_impulse'] == pytest.approx(
        o['total_impulse_Ns'] * b7_impuls, rel=1e-6)
    assert sonuc['isp'] == pytest.approx(o['isp_s'] * b7_isp, rel=1e-3)
    b7_mdot = 0.5367769931985777 / 0.5638380210560432
    assert sonuc['mdot_total'] == pytest.approx(
        o['mdot_total_kg_s'] * b7_mdot, rel=1e-3)


# ---------------------------------------------------------------------------
# 5. KULLANICI KAMARA ÇAPI — korunur, artık yakıt yayımlanır, sığmazsa ret
# ---------------------------------------------------------------------------

def test_kullanici_kamara_korunur_ve_artik_yayimlanir(kullanici_kamara_100):
    motor, sonuc = kullanici_kamara_100
    assert sonuc['chamber_diameter'] == pytest.approx(0.100)
    g = sonuc['grain_design']
    assert g['grain_outer_diameter_mm'] == pytest.approx(100.0)
    beklenen = ((0.1 ** 2 - motor.D_port_final ** 2)
                / (0.1 ** 2 - motor.D_port_initial ** 2))
    assert sonuc['fuel_sliver_fraction'] == pytest.approx(beklenen,
                                                          rel=1e-12)
    assert g['grain_sizing_rule']['name'] == 'user_chamber_diameter_kept'
    assert 'fit_gate' in g['grain_sizing_rule']


def test_kullanici_kamara_kucukse_adli_ret_ve_onerilen_cap_gecer():
    with pytest.raises(GrainEnvelopeError) as e:
        _kos(thrust=1000, burn_time=10, chamber_diameter_input=50)
    kunye = e.value.invalid_fields[0]
    assert kunye['field'] == 'chamber_diameter_input'
    assert kunye['reason'] == 'grain_envelope_too_small_for_final_ports'
    assert kunye['required_min'] > 50.0
    assert 0.0 < kunye['envelope_reached_at_s'] < 10.0
    assert 'No design was published' in str(e.value)
    # Mesajın önerdiği en küçük çap kapıdan GEÇER (yukarı yuvarlandı).
    motor, sonuc = _kos(thrust=1000, burn_time=10,
                        chamber_diameter_input=kunye['required_min'])
    assert sonuc['burn_time_clipped'] is False
    assert motor.D_port_final <= motor.D_ch


def test_eski_sekiz_onda_kirpmasi_geri_donmez():
    """Eski kural port <= 0,8·D_ch/√N'de kırpıyordu. N = 4, D_ch = 80 mm:
    0,8·80/2 = 32 mm < D_son ≈ 32,8 mm -> eskiden kırpılırdı (yanma
    10 s'den kısa, TARGET_NOT_MET). Tek halka zarfı 32,8 mm portu 80 mm'ye
    sığdırır (k·D = 79,2 mm): tasarım tam süreyle yayımlanır."""
    motor, sonuc = _kos(thrust=1000, burn_time=10, port_count=4,
                        chamber_diameter_input=80)
    assert motor.D_port_final > 0.8 * 0.080 / 2.0
    assert sonuc['burn_time'] == 10.0
    assert sonuc['burn_time_clipped'] is False
    assert sonuc['design_summary']['status'] != 'TARGET_NOT_MET'


def test_dort_port_halka_kapisi_sinirin_iki_yaninda():
    with pytest.raises(GrainEnvelopeError) as e:
        _kos(thrust=1000, burn_time=10, port_count=4,
             chamber_diameter_input=70)
    kunye = e.value.invalid_fields[0]
    assert kunye['port_layout'] == 'single_ring_tangent_at_burnout'
    assert kunye['required_min'] == pytest.approx(
        kunye['final_port_diameter_mm'] * (1 + math.sqrt(2)), abs=0.11)


def test_artik_et_kapiyi_daraltir():
    """Port gövdeye sığsa bile beyan edilen artık ete giriyorsa ret."""
    motor, _ = _kos(thrust=1000, burn_time=10, chamber_diameter_input=60)
    d_son_mm = motor.D_port_final * 1e3
    t = (60.0 - d_son_mm) / 2.0 + 0.5           # zarfı 1 mm aşan artık et
    with pytest.raises(GrainEnvelopeError) as e:
        _kos(thrust=1000, burn_time=10, chamber_diameter_input=60,
             residual_web_thickness=t)
    assert 'residual web you declared' in str(e.value)


# ---------------------------------------------------------------------------
# 6. ARTIK ET GİRDİ KAPISI (saldırgan girdi)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('ham, neden', [
    (-1.0, 'negative'), (True, 'not_a_json_number'),
    ('3', 'not_a_json_number'), ([1], 'not_a_json_number'),
    ({'a': 1}, 'not_a_json_number'), (float('nan'), 'not_finite'),
    (float('inf'), 'not_finite'), (1e12, 'above_chamber_diameter_band'),
])
def test_artik_et_aykiri_girdi_adiyla_reddedilir(ham, neden):
    with pytest.raises(GrainEnvelopeError) as e:
        resolve_residual_web_input(ham)
    assert e.value.invalid_fields[0]['reason'] == neden
    assert e.value.invalid_fields[0]['field'] == 'residual_web_thickness'


@pytest.mark.parametrize('ham', [None, '', '   '])
def test_artik_et_verilmezse_idealizasyon_varsayilani(ham):
    t, kaynak = resolve_residual_web_input(ham)
    assert t == hre.GRAIN_RESIDUAL_WEB_DEFAULT_MM / 1e3 == 0.0
    assert kaynak == 'default_zero_idealisation'


def test_artik_et_ust_siniri_kanonik_banttan_turer():
    from hrma.validation.motor_validation import CANONICAL_LIMITS
    assert hre.residual_web_upper_bound_mm() == pytest.approx(
        CANONICAL_LIMITS['chamber_diameter']['max'] * 1e3 / 2.0)


# ---------------------------------------------------------------------------
# 7. KÜNYE — kural, dayanak, idealizasyon beyanı
# ---------------------------------------------------------------------------

def test_kunye_dayanagi_ve_idealizasyon_beyani(varsayilan):
    _m, sonuc = varsayilan
    g = sonuc['grain_design']
    kural = g['grain_sizing_rule']
    assert kural == sonuc['grain_sizing_rule']
    assert kural['name'] == 'final_port_envelope'
    assert kural['formula'] == 'D_grain_outer = D_port_final + 2*t_residual'
    assert '10.2514/1.19226' in kural['basis']
    assert 'p. 745' in kural['basis']
    assert kural['liner_insulation_modelled'] is False
    assert kural['chamber_inner_equals_grain_outer'] is True
    assert kural['idealisation'].startswith(
        'zero nominal residual fuel; thermal protection and regression '
        'uncertainty not included')
    assert g['residual_web_source'] == 'default_zero_idealisation'
    assert 'no source' in kural['superseded_rule']


def test_kaynaksiz_katsayilar_kaynakta_yok():
    kaynak = (DEPO / 'hrma/engines/hybrid_rocket_engine.py').read_text(
        encoding='utf-8')
    assert 'np.sqrt(self.port_count) * 1.5' not in kaynak
    assert not re.search(r'^PORT_TO_CHAMBER_MAX_RATIO\s*=', kaynak, re.M)
