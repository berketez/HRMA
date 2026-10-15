"""ÖH Dalga-19 · fizik kulvarı aşama 1 — bekçiler.

Kapsanan kalem:

* **P15B4-09** — iki ürün ucu aynı fiziksel soruya TERS cevap veremez:
  derin aşırı-genleşmede ``/api/flow-analysis`` "ayrılma yok" derken
  kardeş ``/api/cfd/nozzle`` "var" diyordu. Kök sebep rejim
  merdiveninin SIRASIYDI: inviskid normal-şok dalı Summerfield ayrılma
  ölçütünün ÜSTÜNDE duruyordu, oysa iki bant iç içedir ve şok bandının
  tamamı (M_e > ~1,53 olan her lülede) ayrılma bandının içinde kalır.

  Onarım: ``NozzleFlow1D._classify_regime`` merdiveninde Summerfield
  ölçütü şok dalından ÖNCE gelir. Şok dalı KALDIRILMADI — ölçütün
  sağlanmadığı düşük genişleme oranlarında (gamma = 1,2 için
  eps < ~1,24) klasik quasi-1D çözümü hâlâ geçerlidir ve orada koşar.

  Kaynak: Summerfield, Foster & Swan, Jet Propulsion 24(9) 1954,
  s. 319-321; Sutton & Biblarz, Rocket Propulsion Elements 9. baskı
  Böl. 3.3; Anderson, Modern Compressible Flow 3. baskı Böl. 5.4.
"""
import numpy as np
import pytest

from hrma.analysis.nozzle_flow_1d import NozzleFlow1D


def _coz(pc_pa, eps, pa_pa, gamma=1.2, mw=22.0, dt=0.05, tc=3200.0):
    return NozzleFlow1D(chamber_pressure=pc_pa, chamber_temperature=tc,
                        throat_diameter=dt, expansion_ratio=eps,
                        gamma=gamma, molecular_weight=mw,
                        ambient_pressure=pa_pa).solve()


class TestP15B409AyrilmaOnceligi:
    """Ölçüt sağlanıyorsa yanıt "ayrılma yok" diyemez."""

    # (ad, P_c [Pa], eps, P_a [Pa])
    DERIN_ASIRI_GENLESME = [
        ('pc6_eps25_SL', 6.0e5, 25.0, 101325.0),
        ('pc10_eps25_SL', 10.0e5, 25.0, 101325.0),
        ('pc20_eps25_SL', 20.0e5, 25.0, 101325.0),
        ('pc70_eps25_SL', 70.0e5, 25.0, 101325.0),
    ]

    @pytest.mark.parametrize('ad,pc,eps,pa', DERIN_ASIRI_GENLESME)
    def test_olcut_saglaninca_ayrilma_yayimlanir(self, ad, pc, eps, pa):
        """Ölçüt sağlanan HER vakada rejim 'separated' ve ``separation`` dolu.

        ÖNCE (taban 60cd341): pc6 ve pc10 vakaları
        ``normal_shock_in_nozzle`` etiketi alıyor, ``separation`` anahtarı
        None kalıyordu — yani uç "ayrılma yok" diyordu. Aynı koşuda
        ``separation_criterion_met`` True idi: yanıt kendi kendisiyle
        çelişiyordu.
        """
        r = _coz(pc, eps, pa)
        rej = r['regime']
        assert rej['separation_criterion_met'] is True, ad
        assert rej['type'] == NozzleFlow1D.REGIME_SEPARATED, ad
        assert rej['separation'] is not None, ad
        assert rej['normal_shock'] is None, ad
        sep = rej['separation']
        assert 1.0 < sep['area_ratio'] < eps, ad
        assert sep['station_x_mm'] > 0.0, ad

    def test_hicbir_kosuda_olcut_ile_etiket_celismez(self):
        """Geri basınç süpürmesi: ölçüt <=> etiket <=> ``separation`` dolu.

        Üçü de AYNI hükümdür; birinin diğerinden ayrılabildiği tek bir
        nokta bile kalemin kendisidir.
        """
        pc = 20.0e5
        for pa in np.linspace(1.0e3, 0.85 * pc, 60):
            r = _coz(pc, 25.0, float(pa))
            rej = r['regime']
            olcut = bool(rej['separation_criterion_met'])
            ayrik = rej['type'] == NozzleFlow1D.REGIME_SEPARATED
            dolu = rej['separation'] is not None
            bogulmamis = rej['type'] == NozzleFlow1D.REGIME_UNCHOKED
            if bogulmamis:
                continue
            assert olcut == ayrik == dolu, (
                f'P_a = {pa:.1f} Pa: olcut={olcut} etiket={rej["type"]} '
                f'separation_dolu={dolu}')

    def test_sok_dali_olcut_saglanmayan_bantta_hala_kosar(self):
        """Onarım şok dalını KALDIRMAZ — daraltır.

        gamma = 1,2 / eps = 1,15 icin normal-şok basınç sıçraması
        P2/P1 = 2,1313 < 1/k = 2,50; ayrılma eşiği P_a/P_c = 0,82191 iken
        şok bandı (0,70070; 0,78390). Aradaki band ölçütü SAĞLAMAZ, yani
        yapışık inviskid çözüm orada gerçekten geçerlidir.
        """
        pa = 101325.0
        pc = pa / 0.74            # bandın ortası
        r = _coz(pc, 1.15, pa)
        rej = r['regime']
        assert rej['separation_criterion_met'] is False
        assert rej['type'] == NozzleFlow1D.REGIME_SHOCK
        assert rej['separation'] is None
        assert rej['normal_shock'] is not None

    def test_itki_bant_gecisinde_surekli(self):
        """Yapışık şok çözümü itkiyi kırıyordu — süreklilik sınaması.

        ÖNCE (taban): itki/P_c [N/bar] 6 bar 19,5 | 10 bar 32,4 |
        20 bar 263,3 | 70 bar 304,1 — 10->20 bar arasında 8 katlık
        SIÇRAMA, çünkü 20 bar zaten ayrılma bandındaydı.
        SONRA: 206,8 | 233,6 | 263,3 | 304,1 — tek monoton eğri.
        """
        oranlar = []
        for pc_bar in (6.0, 10.0, 20.0, 70.0):
            r = _coz(pc_bar * 1e5, 25.0, 101325.0)
            itki = r['performance']['thrust_N']
            assert itki is not None and itki > 0.0
            oranlar.append(itki / pc_bar)
        # Monotonluk: P_c arttıkça ayrılma düzlemi çıkışa yürür, C_F artar.
        assert all(b < s for b, s in zip(oranlar, oranlar[1:])), oranlar
        # Komşu adımlar arasında kat sıçraması olamaz (taban 8,1x veriyordu).
        for b, s in zip(oranlar, oranlar[1:]):
            assert s / b < 1.5, oranlar

    def test_ayrilma_beklenen_alani_olcutun_kendisidir(self):
        """``separation_expected`` artık rejim etiketiyle çelişemez."""
        for pc, pa in ((10.0e5, 101325.0), (70.0e5, 101325.0),
                       (70.0e5, 0.0)):
            rej = _coz(pc, 25.0, pa)['regime']
            assert (bool(rej['separation_expected'])
                    is bool(rej['separation_criterion_met']))
            if rej['separation_expected']:
                assert rej['separation_station_summerfield'] is not None
                assert rej['separation_expected_because']
                # Ayrı adla yayımlanan istasyon, itki zincirinin okuduğu
                # ``separation`` ile AYNI çözümdür (tek kaynak).
                assert (rej['separation_station_summerfield']['area_ratio']
                        == rej['separation']['area_ratio'])
            else:
                assert rej['separation_station_summerfield'] is None
                assert rej['separation_expected_because'] is None
