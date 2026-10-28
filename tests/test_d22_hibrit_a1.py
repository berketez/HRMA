"""ÖH Dalga-22 · hibrit kulvarı · aşama 1 — bekçiler.

Kapsanan kalemler:
  * OH-D21-02 — geçici seri (TransientBallistics) motorun C_F sözleşmesini
    taşımıyordu: kayıp kümesi uygulanmıyor, λ ölü bir alandan okunuyordu.
  * OH-D21-03 — kinetik verim İSTENEN L*'ı okuyordu, gerçekleşeni değil.
  * B4-13 (kalan ayak) — NHNE kalitesi iki ayrı istasyonu tek ad altında
    yayımlıyordu.
  * B3-13(c) — ``gamma_avg`` ortalama değil, oda gamma'sı; üreticide doğru
    ad yayımlanmıyordu.

Her bekçi ters mutasyonla kırmızı görülmüştür:
docs/scofield/raw/OH/D22/hibrit/a1/mutasyon.json
"""
import numpy as np
import pytest

from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.analysis.transient_ballistics import TransientBallistics


def _motor(**kw):
    p = dict(thrust=3000, burn_time=10, of_ratio=6.0,
             chamber_pressure=30, oxidizer_type='N2O')
    p.update(kw)
    m = HybridRocketEngine(**p)
    m.calculate()
    return m


@pytest.fixture(scope='module')
def motor():
    return _motor()


# ----------------------------------------------------------------------
# OH-D21-02 — geçici seri manşetin C_F sözleşmesini TAŞIR
# ----------------------------------------------------------------------
class TestOHD2102TransientCFSozlesmesi:
    """ÖLÇÜLEN KUSUR (once.json): t=0 itki 3056,0109 N ⟷ tasarım 3000,0000 N
    (+%1,8670). İki kök: kayıp kümesi (+%1,8632 = 1/0,9817089) ve λ'nın ölü
    alandan okunması (+%0,0038 = 0,983 / 0,9829629)."""

    @pytest.mark.parametrize('feed_mode', ['regulated', 'blowdown'])
    def test_t0_tasarim_noktasinin_KENDISI(self, motor, feed_mode):
        tb = (TransientBallistics(motor, feed_mode='blowdown',
                                  tank_temperature=293.15,
                                  liquid_fill_fraction=0.85, n_steps=200)
              if feed_mode == 'blowdown'
              else TransientBallistics(motor, feed_mode='regulated',
                                       n_steps=200))
        sol = tb.solve()
        assert float(sol['thrust'][0]) == pytest.approx(float(motor.F),
                                                        rel=1e-9)
        assert float(sol['chamber_pressure'][0]) / 1e5 == pytest.approx(
            float(motor.P_c), rel=1e-9)

    def test_lambda_motorun_KENDI_degeri(self, motor):
        """λ katalog sabitinden değil, motorun çözdüğü konturdan gelir."""
        tb = TransientBallistics(motor, feed_mode='regulated', n_steps=50)
        assert tb._lambda == pytest.approx(float(motor.lambda_eff), rel=1e-15)
        # Ölü alan gerçekten ölüydü: motorda böyle bir öznitelik YOK.
        assert getattr(motor, 'lambda_divergence', None) is None
        # Ve katalog sabiti artık kullanılmıyor.
        assert tb._lambda != 0.983

    def test_kayip_kumesi_tek_kaynaktan_gelir(self, motor):
        tb = TransientBallistics(motor, feed_mode='regulated', n_steps=50)
        assert tb._loss_product == pytest.approx(
            float(motor.headline_loss_set['loss_product']), rel=1e-15)
        assert tb._loss_product < 1.0

    def test_cf_t0_manset_CF_ile_bit_ayni(self, motor):
        tb = TransientBallistics(motor, feed_mode='regulated', n_steps=50)
        cf0 = tb._thrust_coefficient(float(motor.P_c) * 1e5)
        assert cf0 == pytest.approx(float(motor.CF), rel=1e-9)

    def test_kayipsiz_ve_kayipli_ayri_adlarda(self, motor):
        tb = TransientBallistics(motor, feed_mode='regulated', n_steps=50)
        Pc = float(motor.P_c) * 1e5
        assert (tb._thrust_coefficient(Pc)
                == pytest.approx(tb._thrust_coefficient_lossless(Pc)
                                 * tb._loss_product, rel=1e-15))

    def test_kunye_sozlesmeyi_yayimlar(self, motor):
        tb = TransientBallistics(motor, feed_mode='regulated', n_steps=100)
        sol = tb.solve()
        k = sol['thrust_coefficient_contract']
        assert k['divergence_efficiency'] == pytest.approx(
            float(motor.lambda_eff), rel=1e-15)
        assert k['divergence_efficiency_source'] == 'engine.lambda_eff'
        assert k['loss_set']['source'] == 'engine.headline_loss_set'
        # Kapsam BEYAN EDİLİR: kayıp kümesi tasarım noktasında sabittir.
        assert 'held constant along the trajectory' in k['loss_set']['scope']

    def test_kayip_kumesi_yoksa_FAIL_CLOSED(self, motor):
        """Sessiz 1,0 yedeği YOK: küme yoksa eğri yayımlanmaz."""
        class _Kumesiz:
            pass
        sahte = _Kumesiz()
        for ad in ('At', 'epsilon', 'gamma', 'D_port_initial', 'L_grain',
                   'rho_f', 'a', 'n', 'mdot_ox', 'C_star', 'P_c', 'P_a',
                   't_b', 'lambda_eff', 'nozzle_type', 'm_ox'):
            setattr(sahte, ad, getattr(motor, ad, None))
        with pytest.raises(ValueError) as exc:
            TransientBallistics(sahte, feed_mode='regulated')
        assert 'headline_loss_set' in str(exc.value)

    def test_lambda_yoksa_FAIL_CLOSED(self, motor):
        class _Lambdasiz:
            pass
        sahte = _Lambdasiz()
        for ad in ('At', 'epsilon', 'gamma', 'D_port_initial', 'L_grain',
                   'rho_f', 'a', 'n', 'mdot_ox', 'C_star', 'P_c', 'P_a',
                   't_b', 'headline_loss_set', 'm_ox'):
            setattr(sahte, ad, getattr(motor, ad, None))
        with pytest.raises(ValueError) as exc:
            TransientBallistics(sahte, feed_mode='regulated')
        assert 'lambda_eff' in str(exc.value)


# ----------------------------------------------------------------------
# OH-D21-03 — kinetik verim GERÇEKLEŞEN L* ile beslenir
# ----------------------------------------------------------------------
def _kucuk(l_star):
    e = HybridRocketEngine(thrust=1000, burn_time=10, of_ratio=6.0,
                           chamber_pressure=20.0, l_star=l_star,
                           track_performance=False, uq_mode=True)
    return e, e.calculate()


class TestOHD2103GerceklesenLStar:
    """ÖLÇÜLEN KUSUR (once.json): geometrik tabanın altındaki üç L* isteği
    (1 / 2 / 3 m) aynı kamarayı boyutlandırdığı hâlde farklı sayı üretiyordu:
    d_t 21,8410 / 21,8055 / 21,7836 mm, L 0,69122 / 0,69012 / 0,68944 m,
    L*_ach 3,55036 / 3,54686 / 3,54470 m."""

    # v3.0.1 kulvar P: grain dış çapı = son port çapı (eski 1,5·D_son
    # değil); art-yanma odası bandı D_ch'ye bağlı olduğundan bantlar kaydı.
    # Ölçüldü (bu motor): L* <= 2,5 grain_limited (L*_ach 3,0045 m), 3,0 ve
    # 3,5 l_star_derived, >= 4,0 tavanda (3,862 m). Taban üçlüsü 1/2/3 ->
    # 1/2/2,5; etkin bant çifti 4/6 -> 3/3,5.
    UCLU = (1.0, 2.0, 2.5)

    @pytest.fixture(scope='class')
    def band(self):
        return {ls: _kucuk(ls) for ls in self.UCLU}

    def test_grain_limited_bantta_uc_kosum_BIT_AYNI(self, band):
        (_, a), (_, b), (_, c) = (band[1.0], band[2.0], band[2.5])
        for r in (a, b, c):
            assert r['l_star_achieved'] > r['l_star']
        assert b['l_star_achieved'] == a['l_star_achieved']
        assert c['l_star_achieved'] == a['l_star_achieved']
        assert b['chamber_length'] == a['chamber_length']
        assert c['chamber_length'] == a['chamber_length']

    def test_ulasilamayan_L_star_bogaz_capini_OYNATMAZ(self, band):
        (ea, _), (eb, _), (ec, _) = (band[1.0], band[2.0], band[2.5])
        assert eb.d_t == ea.d_t
        assert ec.d_t == ea.d_t

    def test_kinetik_verim_gerceklesen_L_star_ile_cozulur(self, band):
        for ls in self.UCLU:
            e, r = band[ls]
            # Sabit nokta: kayıp modeline giren L*, GERÇEKLEŞEN L*'tır.
            assert e.l_star_kinetic_input_m == pytest.approx(
                float(r['l_star_achieved']), rel=1e-10)
            assert e.l_star_kinetic_input_m != pytest.approx(ls, rel=1e-3)
            assert e.l_star_kinetic_passes >= 2

    def test_etkin_bantta_L_star_hala_geometriyi_degistirir(self):
        """Onarım L*'ı ETKİSİZLEŞTİRMEDİ: tabanın üstünde hâlâ çalışır."""
        _, dusuk = _kucuk(3.0)
        _, yuksek = _kucuk(3.5)
        assert yuksek['chamber_length'] > dusuk['chamber_length'] * 1.02
        assert yuksek['l_star_achieved'] > dusuk['l_star_achieved']

    def test_yakinsama_kunyesi_vardir(self, band):
        e, _ = band[1.0]
        assert 1 <= e.l_star_kinetic_passes <= 12


# ----------------------------------------------------------------------
# B4-13 (kalan ayak) — iki istasyon, iki ad
# ----------------------------------------------------------------------
class TestB413IkiIstasyonIkiAd:
    """ÖLÇÜLEN (T₁=290 K, p₂=10 bar): x@p₂ = 0,311945 ⟷ x@boğulma =
    0,023582. İki büyüklük tek ``quality_out`` adı altında karışıyordu."""

    def test_iki_kalite_ayri_adlarda_yayimlanir(self):
        from hrma.engines.injector_design import nhne_mass_flow
        r = nhne_mass_flow(0.7, 1e-5, 50.0, 10.0, 50.7, 290.0)
        assert 'quality_out' in r and 'quality_at_flow_station' in r
        assert r['flow_station_pressure_bar'] > 0.0
        assert isinstance(r['choked'], bool)

    def test_bogulmus_akista_iki_kalite_AYRISIR(self):
        from hrma.engines.injector_design import nhne_mass_flow
        r = nhne_mass_flow(0.7, 1e-5, 50.0, 10.0, 50.7, 290.0)
        if r['choked']:
            assert r['quality_at_flow_station'] != pytest.approx(
                r['quality_out'], rel=1e-3)
            assert r['flow_station_pressure_bar'] > 10.0

    def test_olu_parametre_geri_gelmedi(self):
        import inspect
        from hrma.engines.injector_design import _hem_exit_quality
        assert list(inspect.signature(_hem_exit_quality).parameters) == [
            'T1_K', 'p2_pa']


# ----------------------------------------------------------------------
# B3-13(c) — gamma_avg ortalama değil; üretici doğru adı yayımlar
# ----------------------------------------------------------------------
class TestB313GammaAdiUreticide:

    @pytest.fixture(scope='class')
    def perf(self, motor):
        """Ürün yolunun KENDİSİ: motorun kullandığı çağrı."""
        return motor.combustion_analyzer.analyze_combustion(
            {motor.fuel_type: 100.0}, 'n2o', 6.0, 30.0, None,
            expansion_ratio=motor.epsilon)['performance']

    def test_uretici_chamber_gamma_yayimlar(self, perf):
        assert 'chamber_gamma' in perf
        assert perf['chamber_gamma'] == perf['gamma_avg']
        assert perf['gamma_avg_deprecated_alias_of'] == 'chamber_gamma'

    def test_chamber_gamma_gercekten_ODA_gamma_sidir(self, perf):
        istasyonlar = perf['thermodynamic_properties']['stations']
        assert perf['chamber_gamma'] == pytest.approx(
            istasyonlar['chamber']['gamma'], rel=1e-15)
        # Ve gerçekten ortalama DEĞİL: boğaz/çıkış ayrı gamma taşır.
        assert (istasyonlar['throat']['gamma']
                != pytest.approx(istasyonlar['chamber']['gamma'], rel=1e-9)
                or istasyonlar['exit']['gamma']
                != pytest.approx(istasyonlar['chamber']['gamma'], rel=1e-9))


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
