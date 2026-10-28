# tests/test_d25_fea_cfd_a2.py — ÖH D25 · fea-cfd · aşama-2 bekçileri
"""Akış / kararlılık / FEA onarımlarının mutasyon-kanıtlı bekçileri.

Kalemler: OH-D16-01 (ŞART, Fable-D19), P6B3-08, P6B3-09, P6B3-13,
P6B4-07, P6B4-09, P15B2-11, OH-D24-07, OH-D24-02, OH-D21-05.

Her sınıfın docstring'i onarımın ÖLÇÜLEN önce/sonra sayısını taşır; ham
kanıt ``docs/scofield/raw/OH/D25/fea-cfd/a2/`` altındadır.
"""
import math

import numpy as np
import pytest

from hrma.flow import boundary_layer as BL
from hrma.flow import quasi1d as Q1D
from hrma.flow.quasi1d import area_ratio_from_mach, isentropic_ratios
from hrma.flow.separation import assess_separation
from hrma.stability import bands as BANDS
from hrma.stability.chug import chug_rightmost_root
from hrma.stability.response import (CONFIDENCE_EXTRAPOLATED,
                                     CONFIDENCE_FIRM)


# ===========================================================================
# Ortak lüle fikstürü — künyenin ADI GEÇEN vakası (P6B3-08)
# ===========================================================================
def _lule():
    """45 istasyonlu yakınsak-ıraksak kontur (r_t = 30, r_c = 75, r_e = 90 mm)."""
    r_t, r_c, r_e = 0.030, 0.075, 0.090
    x1 = np.linspace(-0.090, 0.0, 20)
    r1 = r_t + (r_c - r_t) * (x1 / -0.090) ** 2
    x2 = np.linspace(0.0, 0.180, 26)[1:]
    r2 = r_t + (r_e - r_t) * (x2 / 0.180) ** 1.4
    return np.concatenate([x1, x2]), np.concatenate([r1, r2])


def _kenar(gamma=1.2, r_gas=340.0, p0=5.0e6, t0=3200.0):
    x, r = _lule()
    i_t = int(np.argmin(r))
    at = np.pi * r.min() ** 2
    mach = np.empty_like(r)
    for i, ri in enumerate(r):
        eps = (np.pi * ri ** 2) / at
        mach[i] = 1.0 if i == i_t else Q1D.mach_from_area_ratio(
            eps, gamma, supersonic=(i > i_t))
    tr = np.array([isentropic_ratios(m, gamma)[0] for m in mach])
    pr = np.array([isentropic_ratios(m, gamma)[1] for m in mach])
    return dict(x_m=x, radius_m=r, mach=mach, pressure_Pa=p0 * pr,
                temperature_K=t0 * tr, gamma=gamma,
                gas_constant_J_kgK=r_gas, prandtl=0.6,
                wall_temperature_K=1000.0,
                viscosity_fn=lambda t: 1.0e-5 * (t / 300.0) ** 0.66)


@pytest.fixture(scope='module')
def lule_kenari():
    return _kenar()


# ===========================================================================
# P6B3-08 — DEFAULT_SUBSTEPS künyesi ADI GEÇEN vakaya bağlandı
# ===========================================================================
class TestP6B308AltAdimKunyesi:
    """Künye eskiden depoda BULUNMAYAN bir vakaya atıfla '%0,11' diyordu.

    Ölçüldü (once_a2.json → P6B3-08): bu lülede 64'e göre sapma
    1 → %0,1285 · 8 → %0,0257; dizi MONOTON. Yani eski künyenin
    '1→64 toplam %0,11' rakamı bu vakada YANLIŞ (%0,1285) ve
    '8-64 arası %0,11'in altında' ifadesi gerçek payı (%0,026) beş kat
    fazla gösteriyordu.
    """

    @pytest.fixture(scope='class')
    def merdiven(self):
        kenar = _kenar()
        out = {}
        for n in (1, 2, 4, 8, 16, 32, 64):
            out[n] = float(BL.solve_boundary_layer(substeps=n, **kenar)
                           ['friction_drag_N'])
        return out

    def test_merdiven_MONOTON_yakinsar(self, merdiven):
        ref = merdiven[64]
        sapma = {n: abs(v - ref) / ref for n, v in merdiven.items()}
        siralı = [sapma[n] for n in (1, 2, 4, 8, 16, 32, 64)]
        assert all(a >= b for a, b in zip(siralı, siralı[1:])), sapma

    def test_1den_64e_toplam_sapma_8den_64e_sapmadan_BUYUK(self, merdiven):
        """Eski künyenin kendi içinde çeliştiği nokta."""
        ref = merdiven[64]
        s1 = abs(merdiven[1] - ref) / ref
        s8 = abs(merdiven[8] - ref) / ref
        assert s1 > s8, (s1, s8)

    def test_kunye_ADI_GECEN_sayilari_TASIR(self, merdiven):
        """Künyedeki sayılar bu bekçiyle aynı vakadan gelir (tek kaynak)."""
        ref = merdiven[64]
        beklenen = {1: 0.1285, 2: 0.0820, 4: 0.0478,
                    8: 0.0257, 16: 0.0123, 32: 0.0045}
        for n, yuzde in beklenen.items():
            olculen = abs(merdiven[n] - ref) / ref * 100.0
            assert olculen == pytest.approx(yuzde, abs=5e-3), (n, olculen)
        kunye = BL.__dict__.get('__doc__') or ''
        del kunye  # künye modül gövdesinde yorum olarak durur

    def test_varsayilan_8_ve_kunye_METNI_dogru(self):
        import inspect
        src = inspect.getsource(BL)
        i = src.index('DEFAULT_SUBSTEPS = 8')
        blok = src[max(0, i - 2600):i]
        # Eski (yanlış) İDDİA geri gelmesin. Metnin tarihçe cümlesinde
        # tırnak içinde ANILMASI serbesttir; İDDİA olarak yazılması değil.
        assert ('#: lülede, çözünürlük merdiveni bekçisi): 1 → 64 alt adım'
                not in blok)
        i_eski = blok.find("8 ile 64 arası %0.11'in altında")
        assert i_eski >= 0, 'tarihçe cümlesi silinmiş'
        assert 'eskiden' in blok[:i_eski], 'eski iddia tarihçesiz duruyor'
        # Yeni künye ölçülen MERDİVENİ satır satır ve bekçisini ADIYLA
        # anar. Merdiven satırı TAM eşleşmeyle kilitlenir: künyedeki tek
        # bir basamağın sessizce değişmesi bile testi kırar.
        merdiven = ('#:   1 → %0,1285 · 2 → %0,0820 · 4 → %0,0478 · '
                    '8 → %0,0257 ·\n'
                    '#:   16 → %0,0123 · 32 → %0,0045')
        assert merdiven in blok, 'künyedeki merdiven satırı değişmiş'
        # Özet cümlesi de aynı iki sayıyı taşımalı (iç tutarlılık).
        assert '1→64 toplam değişim (%0,1285)' in blok
        assert '8→64 bandından (%0,0257) BÜYÜKTÜR' in blok
        assert 'TestP6B308AltAdimKunyesi' in blok
        assert BL.DEFAULT_SUBSTEPS == 8


# ===========================================================================
# P6B3-09 — theta_initial_m kapısı + tüketicinin march.status körlüğü
# ===========================================================================
class TestP6B309ThetaKapisi:
    """Ölçüldü (once_a2.json → P6B3-09): θ₀ = −1e−4 / NaN / +inf ÜÇÜ DE
    kabul ediliyor, ``march.status = numerical_failure`` ve
    ``friction_drag_N = 0.0`` yayımlanıyordu; tüketici ``nozzle_flow_1d``
    o durumu HİÇ okumadan kesri 'integral_bl_measured' künyesiyle itkiye
    sokuyordu.
    """

    @pytest.mark.parametrize('theta', [-1.0e-4, -1.0, float('nan'),
                                       float('inf'), float('-inf')])
    def test_gecersiz_theta_REDDEDILIR(self, lule_kenari, theta):
        with pytest.raises(ValueError, match='theta_initial_m'):
            BL.solve_boundary_layer(theta_initial_m=theta, **lule_kenari)

    def test_sifir_ve_pozitif_theta_KABUL_EDILIR(self, lule_kenari):
        for theta in (0.0, 1.0e-5):
            res = BL.solve_boundary_layer(theta_initial_m=theta,
                                          **lule_kenari)
            assert res['march']['status'] == BL.MARCH_COMPLETED
            assert res['friction_drag_N'] > 0.0

    def test_tuketici_numerical_failure_KESRI_YAYIMLAMAZ(self):
        """``nozzle_flow_1d`` marşın kendi durumunu OKUR (kaynak bekçisi)."""
        import inspect
        from hrma.analysis import nozzle_flow_1d as NF
        src = inspect.getsource(NF)
        assert '_bl.MARCH_NUMERICAL_FAILURE' in src
        i = src.index('_bl.MARCH_NUMERICAL_FAILURE')
        # Kapı, kesrin hesaplandığı yerin ÖNÜNDE olmalı.
        j = src.index("bl_fraction = float(bl_result['friction_drag_N']")
        assert i < j

    def test_tuketici_kapisi_ISLER(self, monkeypatch):
        """Marş sayısal başarısızlıkla dönerse kesir 'legacy_constant'a düşer."""
        from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
        nf = NozzleFlow1D(chamber_pressure=5.0e6,
                          chamber_temperature=3200.0,
                          throat_diameter=0.060, expansion_ratio=8.0,
                          gamma=1.2, molecular_weight=24.0,
                          ambient_pressure=101325.0)
        gercek = nf._solve_boundary_layer

        def sahte(*a, **k):
            res = gercek(*a, **k)
            res['march'] = dict(res['march'])
            res['march']['status'] = BL.MARCH_NUMERICAL_FAILURE
            res['friction_drag_N'] = 0.0
            return res

        monkeypatch.setattr(nf, '_solve_boundary_layer', sahte)
        out = nf.solve()
        kayip = out['losses']
        assert kayip['friction_loss_fraction_source'] != 'integral_bl_measured'
        assert kayip['friction_loss_fraction_source'] == 'legacy_constant'


# ===========================================================================
# P6B3-13 — boğaza kırpılan dalda wall_pressure_sep_Pa
# ===========================================================================
class TestP6B313BogazaKirpilanDal:
    """Ölçüldü (once_a2.json → P6B3-13; γ=1,2 · P₀=50 bar · P_a=45 bar):
    kalt_badal 2,937445 MPa yazıyordu, boğazın gerçek duvar basıncı
    2,822370 MPa — %4,077 fark. Kardeş dal schmucker AYNI kırpmada doğru
    yazıyordu (%0,000).
    """

    GAMMA = 1.2
    P0 = 5.0e6
    PA = 4.5e6
    M_EXIT = 4.6

    @pytest.fixture(scope='class')
    def sonuc(self):
        return assess_separation(
            P0=self.P0, Pa=self.PA, gamma=self.GAMMA,
            area_ratio_exit=area_ratio_from_mach(self.M_EXIT, self.GAMMA))

    @property
    def p_throat(self):
        return self.P0 * isentropic_ratios(1.0, self.GAMMA)[1]

    def test_fikstur_GERCEKTEN_bogaza_kirpiyor(self, sonuc):
        kirpilan = [k for k, v in sonuc['criteria'].items()
                    if isinstance(v, dict) and v.get('area_ratio_sep') == 1.0]
        assert set(kirpilan) >= {'kalt_badal', 'schmucker'}, kirpilan

    def test_kirpilan_dalda_duvar_basinci_BOGAZINKIDIR(self, sonuc):
        for ad, v in sonuc['criteria'].items():
            if not isinstance(v, dict) or v.get('area_ratio_sep') != 1.0:
                continue
            assert v['wall_pressure_sep_Pa'] == pytest.approx(
                self.p_throat, rel=1e-12), ad

    def test_esik_SILINMEZ_adiyla_durur(self, sonuc):
        kb = sonuc['criteria']['kalt_badal']
        assert kb['threshold_pressure_Pa'] > kb['wall_pressure_sep_Pa']
        # Eşik, korelasyonun kendi tanımıyla tutarlı: P_sep = ratio · P_a.
        assert kb['threshold_pressure_Pa'] == pytest.approx(
            kb['pressure_ratio_threshold'] * self.PA, rel=1e-12)

    def test_iki_kardes_dal_AYNI_sozlesme(self, sonuc):
        """Her kriter her iki alanı da yayımlar (şema tutarlılığı)."""
        for ad, v in sonuc['criteria'].items():
            if not isinstance(v, dict):
                continue
            assert 'wall_pressure_sep_Pa' in v, ad
            assert 'threshold_pressure_Pa' in v, ad

    def test_kirpilmayan_dalda_iki_alan_OZDES(self):
        """A/A* > 1 dalında istasyon P_sep'ten türetilir → eşik = duvar."""
        res = assess_separation(
            P0=self.P0, Pa=101325.0, gamma=self.GAMMA,
            area_ratio_exit=area_ratio_from_mach(self.M_EXIT, self.GAMMA))
        kb = res['criteria']['kalt_badal']
        assert kb['area_ratio_sep'] > 1.0
        assert kb['wall_pressure_sep_Pa'] == pytest.approx(
            kb['threshold_pressure_Pa'], rel=1e-12)


# ===========================================================================
# P6B4-07 — sayısal menzil kapısı TAŞAN büyüklüğü kolluyor
# ===========================================================================
class TestP6B407TasmaKapisi:
    """Ölçüldü (once_a2.json → P6B4-07): J = 1e−300 ile τ/τ_c = 499 / 100
    ve J = 1e−160 ile τ/τ_c = 400 vakalarında fonksiyon ``(inf + nan·j)``
    DÖNDÜRÜYORDU — kapı yalnız τ/τ_c > 500'e bakıyordu.
    """

    @pytest.mark.parametrize('j,tau,tau_c', [
        (1e-300, 0.499, 1.0e-3),
        (1e-300, 0.100, 1.0e-3),
        (1e-160, 0.400, 1.0e-3),
    ])
    def test_tasan_vaka_REDDEDILIR(self, j, tau, tau_c):
        with pytest.raises(ValueError, match='overflow'):
            chug_rightmost_root(dp_ratio_j=j, tau_s=tau, tau_c_s=tau_c)

    def test_saglikli_vaka_HALA_COZULUR(self):
        s = chug_rightmost_root(dp_ratio_j=0.2, tau_s=0.499, tau_c_s=1.0e-3)
        assert s is not None
        assert math.isfinite(s.real) and math.isfinite(s.imag)

    def test_tipik_motor_noktasi_BOZULMADI(self):
        s = chug_rightmost_root(dp_ratio_j=0.20, tau_s=2.0e-3,
                                tau_c_s=2.5e-3)
        assert math.isfinite(s.real) and math.isfinite(s.imag)

    def test_ASLA_sonsuz_ya_da_nan_DONMEZ(self):
        """Kapıdan geçen hiçbir vaka sessiz (inf, nan) üretmez."""
        for j in (1e-300, 1e-200, 1e-100, 1e-20, 1e-3, 0.2, 0.45):
            for tau in (1e-4, 1e-2, 0.1, 0.4, 0.499):
                try:
                    s = chug_rightmost_root(dp_ratio_j=j, tau_s=tau,
                                            tau_c_s=1.0e-3)
                except ValueError:
                    continue
                if s is None:
                    continue
                assert math.isfinite(s.real) and math.isfinite(s.imag), (
                    j, tau, s)


# ===========================================================================
# P6B4-09 — dejenere zarf 'firm' rozeti KAZANAMAZ
# ===========================================================================
class TestP6B409DejenereZarf:
    """Ölçüldü (once_a2.json → P6B4-09): üç QSHOD kaydının ÜÇÜNDE de
    sıcaklık ekseni dejenere; tam noktada rozet ``firm``, 1 ppm sapmada
    ``extrapolated_low``. Yani rozet ölçü-sıfır bir kümede kazanılıyordu.
    """

    @staticmethod
    def _gercek_kayitlar():
        return {rid: rec for rid, rec in BANDS.QSHOD_BAND_RECORDS.items()
                if getattr(rec, 'band', None) is not None}

    def test_kayitlarin_sicaklik_ekseni_DEJENERE(self):
        kayitlar = self._gercek_kayitlar()
        assert len(kayitlar) == 3, sorted(kayitlar)
        dejenere = [rid for rid, rec in kayitlar.items()
                    if 'temperature_range_K'
                    in rec.band.degenerate_dimensions()]
        assert len(dejenere) == len(kayitlar), dejenere

    def test_dejenere_eksende_TAM_NOKTA_bile_firm_DEGIL(self):
        for rid, rec in self._gercek_kayitlar().items():
            b = rec.band
            p = 0.5 * (b.pressure_range_Pa[0] + b.pressure_range_Pa[1])
            conf, gerekce = b.envelope_check(p, b.temperature_range_K[1])
            assert conf == CONFIDENCE_EXTRAPOLATED, rid
            assert 'SINGLE operating point' in gerekce, rid
            assert 'temperature_range_K' in gerekce, rid

    def test_dejenere_eksen_ADIYLA_yayimlanir(self):
        rec = next(iter(self._gercek_kayitlar().values()))
        assert rec.band.degenerate_dimensions() != ()

    def test_zarfin_DISI_hala_extrapolated(self):
        for rid, rec in self._gercek_kayitlar().items():
            b = rec.band
            conf, _ = b.envelope_check(b.pressure_range_Pa[1] * 10.0,
                                       b.temperature_range_K[1] * 2.0)
            assert conf == CONFIDENCE_EXTRAPOLATED, rid

    def test_GENIS_zarf_hala_firm_KAZANABILIR(self):
        """Rozet ölmedi: iki eksende de genişliği olan bir bant firm alır."""
        from hrma.stability.response import QSHODBand
        b = QSHODBand(a_range=(6.0, 6.0), b_range=(0.55, 0.55),
                      pressure_exponent_n=0.3,
                      formulation_class='test band (two-sided envelope)',
                      pressure_range_Pa=(1.0e6, 2.0e7),
                      temperature_range_K=(2000.0, 3600.0),
                      source='synthetic guard fixture')
        assert b.degenerate_dimensions() == ()
        conf, _ = b.envelope_check(1.0e7, 3000.0)
        assert conf == CONFIDENCE_FIRM


# ===========================================================================
# P15B2-11 — gürültü tabanı ROL başına adlandırılır
# ===========================================================================
class TestP15B211GurultuTabaniAdlandirmasi:
    """Sahamdaki iki dosya: ``boundary_layer._EPS`` çıplaktı ve künyesizdi;
    ``quasi1d`` ikilisinin künyesinde BOYUT yazmıyordu. Üç sayı ORTAK bir
    tabana indirgenemez — boyutları farklıdır (ölçüldü: D24 ihracat ayağı).
    """

    def test_ciplak_EPS_ADI_KALKTI(self):
        assert not hasattr(BL, '_EPS')
        assert BL._LAMBDA_COMPARE_EPS == 1e-12

    def test_lambda_payi_BOYUTSUZ_kullanilir(self):
        """Yalnız boyutsuz λ karşılaştırmasında geçer (kaynak bekçisi)."""
        import inspect
        src = inspect.getsource(BL)
        assert src.count('_LAMBDA_COMPARE_EPS') == 2   # tanım + tek kullanım
        assert 'THWAITES_LAMBDA_SEPARATION - _LAMBDA_COMPARE_EPS' in src

    def test_quasi1d_ikilisi_BOYUTUYLA_kunyeli(self):
        import inspect
        src = inspect.getsource(Q1D)
        i = src.index('_MACH_EPS = 1e-9')
        blok = src[i:i + 400]
        assert '[boyutsuz Mach]' in blok
        assert '[boyutsuz, BAĞIL]' in blok

    def test_degerler_DEGISMEDI(self):
        assert Q1D._MACH_EPS == 1e-9
        assert Q1D._BOUNDARY_RTOL == 1e-9


# ===========================================================================
# FEA kalemleri — köprü koşumu gerektirenler (OH-D16-01 ŞART, D24-07, D24-02,
# D21-05). Motor sözlüğü bir kez kurulur; koşum ağırdır.
# ===========================================================================
@pytest.fixture(scope='module')
def hibrit_motor():
    from hrma.app import app
    app.config['TESTING'] = True
    cli = app.test_client()
    r = cli.post('/calculate', json={
        'motor_name': 'D25A2-HIBRIT', 'thrust': 2000.0,
        'chamber_pressure': 30.0, 'burn_time': 10.0,
        'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
        'of_ratio': 6.0, 'expansion_ratio': 8.0,
        # Ölçüm koşulu AÇIKÇA (ana model, 14 Eki): mekanizma araçları
        # (fea-yuk 2. tur) API'nin eski örtük steel_4130'uyla ayarlandı;
        # HB10 tek varsayılanı steel_304 yaptı. Mekanizma aynı malzemede
        # sınanmaya devam eder.
        'chamber_material': 'steel_4130'})
    md = r.get_json() or {}
    return md.get('motor', md)


@pytest.fixture(scope='module')
def hibrit_kopru(hibrit_motor):
    from hrma.fea import bridge
    return bridge.run_structural_from_motor(hibrit_motor)


@pytest.fixture(scope='module')
def hibrit_kopru_ayrisan(hibrit_motor):
    """AYRIŞAN kip aracı (fea-yuk 2. tur, 14 Eki; karar §28-18 (B)).

    Yayımlanan-kip kapısı yalnız yayımlanan kip birincilden BAŞKA iken
    kurulur. Eski sabit-P_c yükünde bu hibrit varsayılanında kipler yapay
    olarak ayrışıyordu; doğru yükte (izantropik P(x) + kapalı uç) ``z_min``
    hafifçe kötümser (38,4509 ⟷ 38,4646) ve varsayılan koşuda kapı
    kurulmuyor. Birincil kip ürün parametresiyle ``z_max`` seçilince
    yayımlanan kip ``z_min`` olur ve kapı AYNI motorda kurulur
    (tests/fea/yuk_modeli_araci.py).
    """
    from hrma.fea import bridge
    from tests.fea.yuk_modeli_araci import ARAC_BIRINCIL_KIP, izantropik_yukte
    s = bridge.run_structural_from_motor(hibrit_motor,
                                         axial_fix=ARAC_BIRINCIL_KIP)
    izantropik_yukte(s)
    kd = s['meta']['kisit_duyarliligi']
    assert kd['yayimlanan_kip'] != kd['birincil_kip'], (
        'araç önkoşulu: yayımlanan kip birincille aynı — kapı kurulmuyor')
    return s


@pytest.fixture(scope='module')
def hibrit_kopru_ayrisan_tekil():
    """Ham tepesi TEKİL olan hibrit geometride ayrışan kip aracı.

    V3.0.5 A2 — ÖLÇÜM KOŞULU AÇIKÇA SABİTLENDİ (28 Eki). "Ham tepe
    yayımlanan sayıdan KÖTÜ yakınsar" karşılaştırması ancak ham düğüm
    tepesinin kontur köşesindeki zayıf tekillikte oturduğu bir geometride
    anlamlıdır (D25 ölçümü: ham rel %19,285 ⟷ kapı %0,2558). Hibrit
    varsayılanı bilinçli değişti ve tekil tepe ortadan kalktı:

    * a0dca0dc0 (19 Eki, v301/port-kamara): kamara çapı yanma sonu port
      çapına iner; bu gövdede kamara 102,94 → ~68 mm, cidar 19,69 →
      13,13 mm. Ölçüldü (docs'suz çatal): af9e4ee37'de tepe rel %1,163 ⟷
      yayımlanan %0,165 (bekçi YEŞİL); a0dca0dc0'da %0,179 ⟷ %0,232
      (KIRMIZI). c7776576f ve 77d64c641 (H-termal, cidar 1,61 mm) da
      kırmızı; bugün %0,243 ⟷ %0,302. Kök FİZİK-2 değil.
    * Ürün gerilemesi yok: varsayılan geometride kapı yine hüküm
      büyüklüğünü ölçüyor (``test_kapi_*`` yeşil) ve ham tepe kendi
      alanında duruyor; yalnız "ham tepe tekil" önkoşulu artık o
      geometride sağlanmıyor.

    Bu fikstür port-kamara öncesi geometriyi kamara çapı, cidar ve c*
    verimiyle açıkça kurar. Köprü girdisi 78fe2254f / af9e4ee37
    ağacındaki istekle BİT-AYNI (ölçüldü: cidar 0,019689181 m, kontur
    toplamı 2,19005420041, tepe rel 0,0116322, yayımlanan rel
    0,0016475914767941924, min SF 38,4509 — d27 hibrit fea-yuk çapası
    38,45093 ile aynı sayı). Diğer d25 bekçileri varsayılan ``hibrit_motor``
    fikstüründe kalır.
    """
    from hrma.app import app
    from hrma.fea import bridge
    from tests.fea.yuk_modeli_araci import ARAC_BIRINCIL_KIP, izantropik_yukte
    app.config['TESTING'] = True
    cli = app.test_client()
    r = cli.post('/calculate', json={
        'motor_name': 'D25A2-HIBRIT-TEKIL', 'thrust': 2000.0,
        'chamber_pressure': 30.0, 'burn_time': 10.0,
        'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
        'of_ratio': 6.0, 'expansion_ratio': 8.0,
        'chamber_material': 'steel_4130',
        'combustion_efficiency': 100.0,
        'wall_thickness': 19.689181049012443,
        'chamber_diameter_input': 102.94158055298513})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    md = r.get_json() or {}
    s = bridge.run_structural_from_motor(md.get('motor', md),
                                         axial_fix=ARAC_BIRINCIL_KIP)
    izantropik_yukte(s)
    kd = s['meta']['kisit_duyarliligi']
    assert kd['yayimlanan_kip'] != kd['birincil_kip'], (
        'araç önkoşulu: yayımlanan kip birincille aynı — kapı kurulmuyor')
    return s


class TestOHD1601YayimlananKipKapisi:
    """ŞART (Fable-D19): kapı, HÜKMÜ TAŞIYAN büyüklüğü ölçmeli.

    Ölçüldü (once_fea.json ⟷ sonra_fea.json → OH-D16-01), hibrit 2 kN /
    30 bar VARSAYILAN köprü koşusu:

      TABAN : verdict.verildi = False, gerekçe ['yayimlanan_kip_yakinsamadi'],
              kapı rel = %21,671 (kapı HAM tepeyi ölçüyordu), tol %1
      SONRA : verdict.verildi = TRUE, gerekçe YOK,
              kapı alanı 'max_von_mises_hukum', kapı rel = %0,2558,
              ham tepe rel = %19,285 (kapı DEĞİL), min SF 31,401 → 35,500

    ÇAPA KAYDI — ÖH D31 fea-cfd a1 (``0deae17d``, P8B1-03 ŞARTI,
    Fable TOPLU fea-cfd-01). Yukarıdaki "gerekçe YOK" satırı ARTIK
    GEÇERSİZDİR ve bunun sebebi bu kalemin kapısı DEĞİLDİR: D31'de
    kapama tabanı payı AYRI bir hüküm kapısına bağlandı (ölçüldü: hibrit
    payı n_axial'dan bağımsız 0,1398076 > eşik
    ``mesh_axisym.GEOMETRY_THICKNESS_TOL`` = 0,10) ve aynı hibrit
    varsayılanında hüküm ADIYLA geri çekiliyor:
    ``verildi = False``, ``geri_cekme_gerekceleri =
    ['kapama_taban_payi_asildi']``. Sayı SİLİNMEDİ (min SF yerinde).

    OH-D16-01'in İDDİASI DEĞİŞMEDİ: "yayımlanan kip kapısı HÜKMÜ TAŞIYAN
    büyüklüğü ölçer" — yani ``yayimlanan_kip_yakinsamadi`` gerekçesinin
    listede OLMAMASI ve kapı alanının ``max_von_mises_hukum`` olması.
    Aşağıdaki bekçi o iddiayı ölçmeye devam eder; kaldırılan tek şey
    bütün kapıların TOPLAMINI ölçen ``verildi is True`` satırıdır — o
    satır bu kalemin kapısını değil, komşu kapıları da sınıyordu.
    Kalan gerekçe kümesi ADIYLA kilitlenir ki yeni ve ADSIZ bir geri
    çekme buraya sızmasın (D26/D27 fea-cfd bekçilerinin aynı deseni).
    """

    def test_KENDI_gerekcesi_YOK_ve_kalan_kume_KILITLI(self, hibrit_kopru):
        hukum = hibrit_kopru['meta']['hukum']
        gerekceler = hukum.get('geri_cekme_gerekceleri') or []
        assert 'yayimlanan_kip_yakinsamadi' not in gerekceler, gerekceler
        assert set(gerekceler) <= {'kapama_taban_payi_asildi'}, gerekceler
        # Hüküm YALNIZ adlı bir kapı yüzünden geri çekilebilir: gerekçe
        # listesi boşsa hüküm VERİLMİŞ olmak ZORUNDADIR (fail-open yok).
        assert hukum['verildi'] is (not gerekceler), (
            'hüküm bayrağı gerekçe listesiyle tutarsız: '
            f"verildi={hukum['verildi']} gerekçeler={gerekceler}")

    def test_kapi_HUKUM_buyuklugunu_olcer(self, hibrit_kopru_ayrisan):
        # ARAÇ UYARLANDI (fea-yuk 2. tur): kapı yalnız ayrışan kipte kurulur.
        kd = hibrit_kopru_ayrisan['meta']['kisit_duyarliligi']
        yky = kd['yayimlanan_kip_yakinsamasi']
        assert yky['kapi_alani'] == 'max_von_mises_hukum'
        assert yky['rel_change'] < yky['tol']

    def test_kapi_reli_BAGIMSIZ_hukum_reline_esit_HAM_reline_DEGIL(
            self, hibrit_kopru_ayrisan, hibrit_motor):
        """ŞARTIN çekirdeği: kapı sayısı ham tepenin reli OLAMAZ.

        ARAÇ UYARLANDI (fea-yuk 2. tur): ayrışan kip aracı; bağımsız çözüm
        ÜRÜNÜN yük modeliyle (``pressure_load``) — skaler P_c artık ürünün
        çözdüğü yük değildir."""
        from hrma.fea import bridge
        from hrma.fea.structural_axisym import build_wall_mesh, solve_pressure
        kd = hibrit_kopru_ayrisan['meta']['kisit_duyarliligi']
        yky = kd['yayimlanan_kip_yakinsamasi']
        kaba = yky['kaba_mesh']
        msh = hibrit_kopru_ayrisan['mesh']
        kip = kd.get('yayimlanan_kip')
        gir = bridge.extract_structural_inputs(hibrit_motor)
        cift = {}
        for ad, nn in (('kaba', kaba),
                       ('ince', {'n_axial': msh['n_axial'],
                                 'n_radial': msh['n_radial']})):
            m = build_wall_mesh(gir['contour'], gir['thickness_m'],
                                n_axial=int(nn['n_axial']),
                                n_radial=int(nn['n_radial']),
                                offset_mode=gir.get('offset_mode', 'normal'))
            cift[ad] = solve_pressure(m, gir['material'],
                                      gir['pressure_load'],
                                      axial_fix=kip)

        def _rel(alan):
            a = getattr(cift['ince'], alan)
            b = getattr(cift['kaba'], alan)
            return abs(a - b) / abs(b)

        hukum_rel = _rel('max_von_mises_hukum')
        ham_rel = _rel('max_von_mises_nodal')
        assert hukum_rel != pytest.approx(ham_rel, rel=1e-3), (
            'iki büyüklük ayrışmıyor — fikstür kalemi göstermiyor')
        assert yky['rel_change'] == pytest.approx(hukum_rel, rel=1e-9)
        assert yky['rel_change'] != pytest.approx(ham_rel, rel=1e-3)

    def test_ham_tepe_SILINMEZ_kendi_alaninda_durur(
            self, hibrit_kopru_ayrisan_tekil):
        # ARAÇ UYARLANDI (fea-yuk 2. tur): ayrışan kip aracı.
        # V3.0.5 A2: ölçüm koşulu ham tepesi tekil geometride sabit
        # (gerekçe ve ölçüm ``hibrit_kopru_ayrisan_tekil`` belgesinde).
        kd = hibrit_kopru_ayrisan_tekil['meta']['kisit_duyarliligi']
        tepe = kd['tepe_F_yakinsamasi']
        assert tepe['hukum_kapisi_mi'] is False
        assert tepe['rel_change'] > kd['yayimlanan_kip_yakinsamasi'][
            'rel_change']

    def test_TEK_KAYNAK_iki_tuketici_ayni_kurali_okur(self):
        """Kural iki yerde YAZILMAZ: bridge tek kaynağı ithal eder."""
        import inspect
        from hrma.fea import bridge as B
        from hrma.fea import structural_axisym as SA
        src = inspect.getsource(B)
        assert 'yakinsama_hedef_buyuklugu(res)' in src
        assert 'yakinsama_hedef_buyuklugu(res_kaba)' in src
        # bridge kendi düşüş kuralını YENİDEN yazmaz.
        assert 'getattr(res, "max_von_mises_hukum", None)' not in src
        # ve solve_with_refinement de aynı kaynağı kullanır.
        assert ('return yakinsama_hedef_buyuklugu(r)'
                in inspect.getsource(SA.solve_with_refinement))

    def test_tek_kaynak_DUSUS_sirasi(self):
        from hrma.fea.structural_axisym import yakinsama_hedef_buyuklugu

        class _A:
            max_von_mises_hukum = 3.0
            max_von_mises_nodal = 5.0
            max_von_mises = 7.0

        class _B:
            max_von_mises_hukum = None
            max_von_mises_nodal = 5.0
            max_von_mises = 7.0

        class _C:
            max_von_mises_hukum = None
            max_von_mises_nodal = None
            max_von_mises = 7.0

        assert yakinsama_hedef_buyuklugu(_A()) == 3.0
        assert yakinsama_hedef_buyuklugu(_B()) == 5.0
        assert yakinsama_hedef_buyuklugu(_C()) == 7.0


class TestOHD2407SaintVenantKatDuyarliligi:
    """Ölçüldü (sonra_fea.json → OH-D24-07): kat 1,25 / 2,0 / 2,5 / 3,0 / 5,0
    merdiveninde yayımlanan SF hibrit ve katıda BEŞ değerde de AYNI (%0,000).
    Tabanda aynı merdiven hibritte +%5,272 (kat 3) ve +%24,777 (kat 5)
    veriyordu (katıda tabanda da duyarlılık YOKTU); hibritteki duyarlılık
    hüküm SCL'ye taşınınca söndü.
    """

    @staticmethod
    def _merdiven(motor_ad):
        import hrma.fea.structural_axisym as SA
        from hrma.fea import bridge
        from hrma.app import app
        from hrma.fea.structural_axisym import build_wall_mesh, solve_pressure
        app.config['TESTING'] = True
        cli = app.test_client()
        # ÖH D26 fix-25a — ROTA LİTERAL YAZILIR. Eskiden rota da sözlükte
        # duruyor ve çağrı ``cli.post(istek[0], json=istek[1])`` biçiminde
        # yapılıyordu; OH-D23-12 rota çözücüsü Subscript düğümünü çözemediği
        # için bu çağrı uç kapsamı taramasında KÖR NOKTAYA düşüyordu
        # (çözülemeyen çağrı tavanı 39 -> 40). Bekçinin kendi reçetesi:
        # "ya çözücü genişletilir ya çağrı literal yazılır". Motora göre
        # seçim GÖVDEDE sürer; rota çağrının kendisinde okunur.
        govde = {
            'hibrit': {
                'motor_name': 'D25A2-SV', 'thrust': 2000.0,
                'chamber_pressure': 30.0, 'burn_time': 10.0,
                'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
                'of_ratio': 6.0, 'expansion_ratio': 8.0},
        }[motor_ad]
        md = (cli.post('/calculate', json=govde).get_json() or {})
        gir = bridge.extract_structural_inputs(md.get('motor', md))
        m = build_wall_mesh(gir['contour'], gir['thickness_m'],
                            n_axial=64, n_radial=8,
                            offset_mode=gir.get('offset_mode', 'normal'))
        eski = SA.SAINT_VENANT_KAT
        f = SA.saint_venant_hukum_maskesi
        d0 = tuple(f.__defaults__ or ())
        out = {}
        try:
            for kat in (eski / 2.0, 2.0, eski, 3.0, eski * 2.0):
                SA.SAINT_VENANT_KAT = float(kat)
                d = list(d0)
                d[-1] = float(kat)
                f.__defaults__ = tuple(d)
                r = solve_pressure(m, gir['material'],
                                   gir['inner_pressure_pa'],
                                   axial_fix='z_max')
                out[kat] = float(r.min_safety_factor)
        finally:
            SA.SAINT_VENANT_KAT = eski
            f.__defaults__ = d0
        return out

    def test_SF_kat_secimine_DUYARSIZ(self):
        out = self._merdiven('hibrit')
        ref = out[2.5]
        for kat, sf in out.items():
            assert sf == pytest.approx(ref, rel=1e-12), (kat, sf, ref)

    def test_kunye_OLCUMU_tasiyor(self):
        import inspect
        import hrma.fea.structural_axisym as SA
        src = inspect.getsource(SA)
        i = src.index('SAINT_VENANT_KAT = 2.5')
        # ÇEVRİLDİ — ÖH D32 fea-cfd a1 (OH-FT-08). Pencere SABİT 2200
        # bayt değil, künyenin KENDİ başlığından başlar. OH-FT-08 künyeye
        # ikinci etki kanalını (kisit_yeri_duyarlilik_esigi merdiveni)
        # ekleyince blok ~1,4 KB büyüdü ve OH-D24-07 başlığı 2200 baytlık
        # pencerenin DIŞINA taştı: iddia içerikten değil UZUNLUKTAN
        # düşüyordu (D31 dersi 22, kesik dilim). İDDİA DEĞİŞMEDİ —
        # künye hâlâ ölçümü taşımak zorunda; yalnız sınırı içerik
        # belirliyor.
        j = src.index('# OH-D24-07 — KAT SEÇİMİNİN DUYARLILIĞI')
        blok = src[j:i]
        assert 'OH-D24-07' in blok
        assert '%24,777' in blok and '%0,000' in blok
        assert 'TestOHD2407SaintVenantKatDuyarliligi' in blok
        assert SA.SAINT_VENANT_KAT == 2.5


class TestOHD2402OnayTuruMaliyeti:
    """Ölçüldü (once_fea.json ⟷ sonra_fea.json → OH-D24-02):
    tur=1 ⟷ tur=2 duvar saati TABANDA katıda 9,55 kat (0,163 → 1,557 s,
    1024 → 16.384 eleman), BU KOŞUMDA 1,53 kat (0,108 → 0,166 s,
    512 → 1024 eleman). Hibritte iki koşumda da 1,54-1,55 kat.
    """

    def test_ek_tur_eleman_sayisini_EN_FAZLA_iki_katlar(self, hibrit_motor):
        import hrma.fea.structural_axisym as SA
        from hrma.fea import bridge
        eski = SA.REFINE_ONAY_ARDISIK_TUR
        elemanlar = {}
        try:
            for tur in (1, 2):
                SA.REFINE_ONAY_ARDISIK_TUR = tur
                rapor = bridge.run_structural_from_motor(hibrit_motor)
                elemanlar[tur] = rapor['mesh']['n_elems']
        finally:
            SA.REFINE_ONAY_ARDISIK_TUR = eski
        assert elemanlar[2] / elemanlar[1] <= 2.0, elemanlar

    def test_kunye_MALIYETI_tasiyor(self):
        import inspect
        import hrma.fea.structural_axisym as SA
        src = inspect.getsource(SA)
        i = src.index('REFINE_ONAY_ARDISIK_TUR = 2 ')
        blok = src[max(0, i - 1800):i]
        assert 'OH-D24-02' in blok
        assert '9,55x' in blok and '1,53x' in blok
        assert 'TestOHD2402OnayTuruMaliyeti' in blok

    def test_sabit_DEGISMEDI(self):
        import hrma.fea.structural_axisym as SA
        assert SA.REFINE_ONAY_ARDISIK_TUR == 2


class TestOHD2105IlkIstekGecikmesi:
    """Ölçüldü (once_fea.json ⟷ sonra_fea.json → OH-D21-05): ilk istek
    3,27 s (taban) / 3,39 s (bu koşum), ikinci istek 0,0096 s (≈350 kat).
    Künye ``_altin_oran_tepe`` docstring'inde durur.
    """

    def test_onbellek_IKINCI_istegi_sifirlar(self, hibrit_motor):
        import time
        from hrma.app import app
        app.config['TESTING'] = True
        cli = app.test_client()
        gonderi = {'motor_data': hibrit_motor}
        sureler = []
        for _ in range(2):
            t0 = time.perf_counter()
            r = cli.post('/api/advanced-performance-analysis', json=gonderi)
            sureler.append(time.perf_counter() - t0)
        assert r.status_code == 200
        # İkinci istek her hâlükârda birinciden HIZLI olmalı (lru_cache).
        assert sureler[1] < sureler[0]

    def test_tek_tepe_varsayimi_ve_OLCUM_docstringde(self):
        from hrma.visualization.visualization import _altin_oran_tepe
        d = _altin_oran_tepe.__doc__ or ''
        assert 'TEK TEPE VARSAYIMI' in d
        assert 'OH-D21-05' in d
        assert '3,39 s' in d and '0,0096 s' in d
