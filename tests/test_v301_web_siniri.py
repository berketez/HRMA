"""V301/A1 — geçici (transient) çözücünün web sınırı tane zarfından okunur.

Kusur (taban a367de3d2, ``docs/scofield/raw/OH/V301/makale1/A1/once.json``):
``transient_ballistics.solve`` portu ``0,8·D_ch``'ta durduruyordu. v3.0.1
tane zarfıyla tek portlu otomatik boyutta ``D_ch = D_port_son`` olduğundan
1 kN / 10 s / 20 bar / HTPB-N2O danışma blowdown eğrisi 2,75 s'de (O/F 2,5)
ve 2,70 s'de (O/F 7,5) ``web_exhausted`` ile bitiyor, port 43,01 mm'de
(= 0,8 × 53,77) duruyor, tankta 3,11 kg N2O kalıyordu; /api/transient-analysis
düzenlenmiş koşusu 2,675 s'de bitiyordu. N = 4'te tersine sınır
0,8·k(4)·D_son ≈ 1,93·D_son idi (tek halkada portlar D_son'da birbirine değer).

Karar: sınır ``max_port_diameter_in_envelope_m(D_ch, N, t_artık)`` (tek tanım,
hybrid_rocket_engine); yakıt bütçesi aynı sınırdan. Sayılar ``sonra.json``.
"""

import copy
import math
from types import SimpleNamespace

import numpy as np
import pytest

from hrma.analysis.transient_ballistics import TransientBallistics, web_limit
from hrma.engines.hybrid_rocket_engine import (
    HybridRocketEngine, TANK_BLOWDOWN_N_STEPS, TANK_FILL_FRACTION_DEFAULT,
    TANK_TEMPERATURE_DEFAULT_K, grain_port_layout_factor)

TABAN = dict(thrust=1000, burn_time=10, chamber_pressure=20,
             fuel_type='htpb', oxidizer_type='n2o')

#: Düzenlenmiş beslemede son KAYITLI port / D_son alt sınırı. Ölçüldü
#: (sonra.json S3/S4): 0,999279 (O/F 2,5) ve 0,999282 (O/F 7,5). Çözücü
#: adımın BAŞINDAKİ portu kaydeder; n_steps = 400'de son adımın kendi
#: büyümesi D_son'un ~6,1e-4'ü, kalan ~1,1e-4 tasarım yürüyüşü (200 adım)
#: ile geçici yürüyüşün (400 adım) Euler ayrıklaştırma farkıdır. 1e-3 bu
#: ikisinin toplamını kapsar; eski kural (0,80) bunun çok dışındadır.
DUZENLI_PORT_TOLERANSI = 1e-3

#: Web olayıyla biten blowdown koşusunda son KAYITLI port / sınır alt
#: sınırı. Ölçüldü (sonra.json S7, n_steps = 200): kayıt 0,998907, adım
#: sonu 1,000450 — tek adımın büyümesi sınırın ~%0,15'i. 5e-3 tek adımı
#: rahatça kapsar, 1,93·D_son ya da 0,8·D_ch gibi yanlış sınırları kapsamaz.
WEB_OLAYI_PORT_TOLERANSI = 5e-3


def _motor(**ek):
    e = HybridRocketEngine(**{**TABAN, **ek})
    sonuc = e.calculate()
    return e, sonuc


@pytest.fixture(scope='module')
def n1_of25():
    return _motor(of_ratio=2.5)


@pytest.fixture(scope='module')
def n1_of75():
    return _motor(of_ratio=7.5)


@pytest.fixture(scope='module')
def n4():
    return _motor(of_ratio=2.5, port_count=4)


@pytest.fixture(scope='module')
def kullanici_kamarasi():
    # 62 mm kamara, 3 mm artık et: sınır D_ch − 2t = 56 mm; eski kural
    # 0,8·62 = 49,6 mm, t'siz sınır 62 mm. D_son ≈ 53,77 mm, zarf kapısı geçer.
    return _motor(of_ratio=2.5, chamber_diameter_input=62.0,
                  residual_web_thickness=3.0)


@pytest.fixture(scope='module')
def otomatik_artik_et():
    # Otomatik boyut + 2 mm artık et: D_ch = D_son + 4 mm, sınır D_son.
    return _motor(of_ratio=2.5, residual_web_thickness=2.0)


def _blowdown(e, m_ox_kat=1.0):
    """Danışma bloğunun AYNI ayarlarıyla blowdown çözümü.

    ``m_ox_kat`` > 1: tank tasarımın gerektirdiğinden fazla N2O ile
    doldurulur (büyük tank). Yalnız tankı boyutlandıran ``m_ox`` değişir;
    motorun geri kalanı aynı nesnedir (sığ kopya).
    """
    m = e
    if m_ox_kat != 1.0:
        m = copy.copy(e)
        m.m_ox = float(e.m_ox) * m_ox_kat
    return TransientBallistics(
        m, feed_mode='blowdown', tank_temperature=TANK_TEMPERATURE_DEFAULT_K,
        liquid_fill_fraction=TANK_FILL_FRACTION_DEFAULT,
        n_steps=TANK_BLOWDOWN_N_STEPS).solve()


# --------------------------------------------------------------- tanım ----

class TestSinirTanimi:
    def test_otomatik_boyutta_sinir_son_port(self, n1_of25):
        e, _ = n1_of25
        w = web_limit(e)
        assert w['source'] == 'grain_envelope'
        assert w['port_diameter_m'] == pytest.approx(e.D_port_final,
                                                     rel=1e-12)

    def test_otomatik_boyut_artik_et_dahil(self, otomatik_artik_et):
        e, _ = otomatik_artik_et
        assert e.residual_web == pytest.approx(2e-3, rel=1e-12)
        assert e.D_ch == pytest.approx(e.D_port_final + 4e-3, rel=1e-12)
        assert web_limit(e)['port_diameter_m'] == pytest.approx(
            e.D_port_final, rel=1e-12)

    def test_kullanici_kamarasi_D_ch_eksi_2t(self, kullanici_kamarasi):
        e, _ = kullanici_kamarasi
        assert e.D_ch == pytest.approx(0.062, rel=1e-12)
        assert e.D_ch > e.D_port_final
        assert web_limit(e)['port_diameter_m'] == pytest.approx(
            0.062 - 2 * 0.003, abs=1e-12)

    def test_cok_port_sinir_halka_zarfi(self, n4):
        e, _ = n4
        D = web_limit(e)['port_diameter_m']
        # Otomatik boyutta zarf = son port; tanım (D_ch − 2t)/k(N).
        assert D == pytest.approx(e.D_port_final, rel=1e-12)
        assert D == pytest.approx(
            (e.D_ch - 2 * e.residual_web) / grain_port_layout_factor(4),
            rel=1e-12)
        # Eski kural portların ≈1,93·D_son'a kadar büyümesine izin veriyordu.
        assert 0.8 * e.D_ch / e.D_port_final == pytest.approx(
            0.8 * grain_port_layout_factor(4), rel=1e-12)

    @pytest.mark.parametrize('ad', ['n1_of25', 'n4', 'kullanici_kamarasi'])
    def test_yakit_butcesi_ayni_sinirdan(self, ad, request):
        e, _ = request.getfixturevalue(ad)
        assert getattr(e, 'm_fuel', None) is None   # hibritte öznitelik yok
        w = web_limit(e)
        beklenen = (e.port_count * e.rho_f * np.pi / 4.0
                    * (w['port_diameter_m'] ** 2 - e.D_port_initial ** 2)
                    * e.L_grain)
        assert w['fuel_available_kg'] == pytest.approx(beklenen, rel=1e-12)

    def test_taklit_nesnede_eski_sayi_bit_ayni(self):
        D, rho, L = 0.0312345, 930.0, 0.41
        taklit = SimpleNamespace(D_port_initial=D, rho_f=rho, L_grain=L)
        w = web_limit(taklit)
        assert w['source'] == 'legacy_no_chamber_diameter'
        eski_D = float(D * 10) * 0.8
        assert w['port_diameter_m'] == eski_D
        assert w['fuel_available_kg'] == float(
            1 * rho * np.pi / 4.0 * (eski_D ** 2 - D ** 2) * L)

    def test_m_fuel_onceligi_korunur(self):
        taklit = SimpleNamespace(D_port_initial=0.03, rho_f=930.0,
                                 L_grain=0.4, D_ch=0.05, m_fuel=1.234)
        assert web_limit(taklit)['fuel_available_kg'] == 1.234


class TestFailClosed:
    @pytest.mark.parametrize('deger', [
        float('nan'), float('inf'), True, np.bool_(True), '0.05', -0.05, 0.0])
    def test_bozuk_D_ch_reddedilir(self, deger):
        taklit = SimpleNamespace(D_port_initial=0.03, rho_f=930.0,
                                 L_grain=0.4, D_ch=deger)
        with pytest.raises(ValueError):
            web_limit(taklit)

    @pytest.mark.parametrize('deger', [
        float('nan'), float('inf'), False, '0.001', -1e-3])
    def test_bozuk_artik_et_reddedilir(self, deger):
        taklit = SimpleNamespace(D_port_initial=0.03, rho_f=930.0,
                                 L_grain=0.4, D_ch=0.05, residual_web=deger)
        with pytest.raises(ValueError):
            web_limit(taklit)

    @pytest.mark.parametrize('deger', [float('nan'), float('inf'), True,
                                       '1.0', -1.0])
    def test_bozuk_m_fuel_reddedilir(self, deger):
        taklit = SimpleNamespace(D_port_initial=0.03, rho_f=930.0,
                                 L_grain=0.4, D_ch=0.05, m_fuel=deger)
        with pytest.raises(ValueError):
            web_limit(taklit)

    def test_solve_nan_kamarada_sessiz_kalmaz(self, n1_of25):
        e, _ = n1_of25
        bozuk = copy.copy(e)
        bozuk.D_ch = float('nan')
        with pytest.raises(ValueError):
            TransientBallistics(bozuk, feed_mode='regulated').solve()


# ------------------------------------------------------------ davranış ----

class TestDanismaBlowdown:
    @pytest.mark.parametrize('ad', ['n1_of25', 'n1_of75'])
    def test_tasarim_suresinin_cok_altinda_web_ile_bitmez(self, ad, request):
        e, sonuc = request.getfixturevalue(ad)
        blok = sonuc['tank_blowdown']
        assert blok['status'] == 'modelled'
        # Ölçüldü: önce web_exhausted 2,75 s / 2,70 s; sonra
        # oxidizer_depleted 10,15 s (tank, tasarım m_ox = ṁ_ox·t_b ile dolu).
        assert blok['end_event'] != 'web_exhausted'
        assert blok['end_event'] == 'oxidizer_depleted'
        assert blok['burn_duration_s'] >= 0.9 * e.t_b
        assert blok['total_impulse_Ns'] > 0.8 * e.F * e.t_b

    @pytest.mark.parametrize('ad', ['n1_of25', 'n1_of75'])
    def test_port_son_portu_asmaz(self, ad, request):
        e, sonuc = request.getfixturevalue(ad)
        sol = _blowdown(e)
        # Aynı ayarlar -> danışma bloğuyla aynı çözüm.
        assert sol['end_event'] == sonuc['tank_blowdown']['end_event']
        assert sol['total_impulse'] == pytest.approx(
            sonuc['tank_blowdown']['total_impulse_Ns'], rel=1e-12)
        assert float(np.max(sol['port_diameter'])) <= (
            e.D_port_final * (1 + 1e-9))


class TestDuzenlenmisBesleme:
    @pytest.mark.parametrize('of', [2.5, 7.5])
    def test_api_t_b_de_biter_port_D_son_a_yakin(self, of):
        from hrma.app import app
        with app.test_client() as ist:
            yanit = ist.post('/api/transient-analysis', json={
                **TABAN, 'of_ratio': of, 'motor_type': 'hybrid',
                'feed_mode': 'regulated'})
        assert yanit.status_code == 200
        tr = yanit.get_json()['transient']
        e, _ = _motor(of_ratio=of)
        assert tr['end_event'] == 'burn_time_reached'
        assert tr['burn_duration'] == pytest.approx(e.t_b, abs=1e-9)
        oran = tr['port_diameter'][-1] / e.D_port_final
        assert 1.0 - DUZENLI_PORT_TOLERANSI <= oran <= 1.0 + 1e-9


class TestWebOlayiNerede:
    def test_n4_web_D_son_da_tetiklenir(self, n4):
        e, _ = n4
        sol = _blowdown(e, m_ox_kat=3.0)
        # Oksitleyici yakıttan uzun sürer: koşu web olayıyla biter ve tankta
        # oksitleyici kalır. Eski kural (≈1,93·D_son) bu koşuyu t_max'a
        # (16 s, time_limit) taşıyordu, port 38,09 mm = 1,16·D_son.
        assert sol['end_event'] == 'web_exhausted'
        assert sol['residual_oxidizer_kg'] > 0.0
        assert sol['burn_duration'] < 1.6 * e.t_b - 1e-9
        port_son = float(sol['port_diameter'][-1])
        assert port_son <= e.D_port_final * (1 + 1e-9)
        assert port_son >= e.D_port_final * (1 - WEB_OLAYI_PORT_TOLERANSI)

    def test_kullanici_kamarasi_web_D_ch_eksi_2t_de(self, kullanici_kamarasi):
        e, _ = kullanici_kamarasi
        sinir = e.D_ch - 2 * e.residual_web
        sol = _blowdown(e, m_ox_kat=3.0)
        # Önce: web_exhausted 7,05 s, port 49,56 mm (0,8·62). Sonra:
        # web_exhausted 12,05 s, port 55,99 mm (sınır 56).
        assert sol['end_event'] == 'web_exhausted'
        assert sol['residual_oxidizer_kg'] > 0.0
        port_son = float(sol['port_diameter'][-1])
        assert port_son <= sinir * (1 + 1e-9)
        assert port_son >= sinir * (1 - WEB_OLAYI_PORT_TOLERANSI)
        assert math.isclose(sinir, 0.056, abs_tol=1e-12)
