"""3.0.7 K3a — tank_mass_properties (TANK §C; §E.1–E.3'ün kütle kısımları).

Kilitlenen fizik:
  * düz tabanlı silindir: V = πR²h, z_km = h/2, I_km = m(R²/4 + h²/12),
    I_eksenel = mR²/2 (kapalı biçim, 10⁻¹²);
  * küre: küresel kapağın kapalı biçim integralleri; profil inceltmesinde
    ikinci mertebe yakınsama (parçalı doğrusal profilin temsil hatası);
  * 3 noktalı Gauss–Legendre parçalı doğrusal profilde TAM: kesik konide
    eksenel eylemsizlik kapalı biçimle 10⁻¹³;
  * tutarlılık: yarım küre tabanlı silindir h ≤ R'de küreyle özdeş; ölçek;
  * doluluk ızgarası ve sebep kodları sözleşmeden (tek yer).
"""

import math
import os
import sys

import numpy as np
import pytest
from tests.support.esikler import PLATFORM_GURULTU_TABANI_REL

from hrma.analysis import slosh_tablo
from hrma.analysis import tank_mass_properties as mp

sys.path.insert(0, os.path.dirname(__file__))
import tank_geometri_ornekleyici as orn  # noqa: E402

RHO = 1000.0
R = 0.5


def _kure_kapali(h, R=R, rho=RHO):
    """Alt kutuptan h yüksekliğine küresel kapak: r² = 2Rz − z²."""
    V = math.pi * (R * h * h - h ** 3 / 3.0)
    S1 = math.pi * (2.0 * R * h ** 3 / 3.0 - h ** 4 / 4.0)
    S2 = math.pi * (R * h ** 4 / 2.0 - h ** 5 / 5.0)
    Q = math.pi / 4.0 * (4.0 * R * R * h ** 3 / 3.0 - R * h ** 4
                         + h ** 5 / 5.0)
    zk = S1 / V
    return {'V_sivi_m3': V, 'z_km_m': zk,
            'I_km_donmus_kgm2': rho * (Q + S2 - V * zk * zk),
            'I_eksenel_donmus_kgm2': rho * 2.0 * Q,
            'R_yuzey_m': math.sqrt(2.0 * R * h - h * h)}


class TestSilindirAnalitik:
    H = 2.0

    def test_izgaranin_her_satiri_kapali_bicimle_ayni(self):
        out = mp.kutle_ozellikleri_tablosu(orn.silindir_duz(R, self.H), RHO)
        assert [s['doluluk'] for s in out['satirlar']] == list(
            slosh_tablo.DOLULUK_IZGARASI)
        g = out['geometri']
        assert g['V_ic_m3'] == pytest.approx(math.pi * R * R * self.H,
                                             rel=1e-14)
        for s in out['satirlar']:
            # Kök: hacim toleransı 10⁻¹² V_iç → silindirde |Δh| ≤ 10⁻¹² H.
            assert abs(s['h_m'] - s['doluluk'] * self.H) <= (
                mp.DOLULUK_KOK_BAGIL_TOL * self.H)
            # İntegraller: modülün bulduğu h'de kapalı biçimle (kareleme tam).
            h = s['h_m']
            m = RHO * math.pi * R * R * h
            assert s['V_sivi_m3'] == pytest.approx(m / RHO, rel=1e-13)
            assert s['z_km_m'] == pytest.approx(h / 2.0, rel=1e-13)
            assert s['I_km_donmus_kgm2'] == pytest.approx(
                m * (R * R / 4.0 + h * h / 12.0), rel=1e-12)
            assert s['I_eksenel_donmus_kgm2'] == pytest.approx(
                m * R * R / 2.0, rel=1e-13)
            assert s['R_yuzey_m'] == R
            assert s['A_yuzey_m2'] == pytest.approx(math.pi * R * R,
                                                    rel=1e-15)

    def test_sozlesme_ozdeslikleri(self):
        """slosh_tablo doğrulayıcısının geometri özdeşlikleri (DEGISMEZ_BAGIL_TOL)."""
        p = orn.kubbeli_silindir(R, 1.0, n=90)
        out = mp.kutle_ozellikleri_tablosu(p, RHO)
        V_ic = out['geometri']['V_ic_m3']
        H = out['geometri']['H_ic_m']
        tol = slosh_tablo.DEGISMEZ_BAGIL_TOL
        for s in out['satirlar']:
            assert abs(s['V_sivi_m3'] - s['doluluk'] * V_ic) <= tol * V_ic
            assert s['m_sivi_kg'] == RHO * s['V_sivi_m3']
            assert 0.0 < s['h_m'] <= H
            assert 0.0 < s['z_km_m'] < s['h_m']
            assert s['R_yuzey_m'] <= out['geometri']['R_ref_m']
            assert s['A_yuzey_m2'] == pytest.approx(
                math.pi * s['R_yuzey_m'] ** 2, rel=1e-15)


class TestGaussTam:
    def test_kesik_koni_tam(self):
        """Kesik koni: ∫π r⁴/2 dz = πH(R1⁴+R1³R2+R1²R2²+R1R2³+R2⁴)/10 (derece 4)."""
        R1, R2, H = 0.3, 0.7, 1.3
        p = [(0.0, 0.0), (R1, 0.0), (R2, H), (0.0, H)]
        out = mp.kesit_ozellikleri(p, RHO, H)
        V = math.pi * H * (R1 * R1 + R1 * R2 + R2 * R2) / 3.0
        I_eks = RHO * math.pi * H * (R1 ** 4 + R1 ** 3 * R2 + R1 ** 2 * R2 ** 2
                                     + R1 * R2 ** 3 + R2 ** 4) / 10.0
        assert out['V_sivi_m3'] == pytest.approx(V, rel=1e-14)
        assert out['I_eksenel_donmus_kgm2'] == pytest.approx(I_eks, rel=1e-13)

    def test_kesik_koni_enine_tam(self):
        """I_km: (r²/4 + (z − z_km)²) π r² — derece 4, tam."""
        R1, R2, H = 0.2, 0.9, 0.8
        p = [(0.0, 0.0), (R1, 0.0), (R2, H), (0.0, H)]
        out = mp.kesit_ozellikleri(p, RHO, H)
        # Bağımsız referans: 2000 parçalı yamuk değil, sembolik polinom
        # integrali (numpy.polynomial ile tam).
        from numpy.polynomial import polynomial as P
        r = np.array([R1, (R2 - R1) / H])               # r(z) katsayıları
        r2 = P.polymul(r, r)
        V = math.pi * P.polyval(H, P.polyint(r2))
        S1 = math.pi * P.polyval(H, P.polyint(P.polymul(r2, [0, 1])))
        zk = S1 / V
        f = P.polyadd(P.polymul(P.polymul(r2, r2), [0.25]),
                      P.polymul(r2, P.polymul([-zk, 1], [-zk, 1])))
        I_km = RHO * math.pi * P.polyval(H, P.polyint(f))
        assert out['z_km_m'] == pytest.approx(zk, rel=1e-14)
        assert out['I_km_donmus_kgm2'] == pytest.approx(I_km, rel=1e-13)


class TestKure:
    @pytest.mark.parametrize('h', [0.1, 0.5, 0.9])
    def test_ikinci_mertebe_yakinsama(self, h):
        """Parçalı doğrusal küre profili n ×2 → hata ×1/4 (ölçülen 1,98–2,00)."""
        ref = _kure_kapali(h)
        hatalar = []
        for n in (64, 128, 256, 512):
            out = mp.kesit_ozellikleri(orn.kure(R, n), RHO, h)
            hatalar.append(max(abs(out[k] - ref[k]) / ref[k] for k in
                               ('V_sivi_m3', 'z_km_m', 'I_km_donmus_kgm2',
                                'I_eksenel_donmus_kgm2')))
        mertebe = [math.log2(hatalar[i] / hatalar[i + 1]) for i in range(3)]
        assert all(1.9 <= p <= 2.1 for p in mertebe), mertebe
        assert hatalar[-1] <= 1e-4, hatalar

    def test_yuzey_yaricapi_kapali_bicim(self):
        out = mp.kesit_ozellikleri(orn.kure(R, 1024), RHO, 0.3)
        assert out['R_yuzey_m'] == pytest.approx(
            _kure_kapali(0.3)['R_yuzey_m'], rel=1e-5)


class TestTutarlilik:
    def test_yarim_kure_tabanli_silindir_h_R_altinda_kure_ile_ozdes(self):
        n = 256
        kure = orn.kure(R, n)
        kubbe = orn.kubbeli_silindir(R, 1.3, n=n // 2)
        # Alt yarı düğümleri birebir aynı (aynı açı ızgarası).
        assert np.array_equal(kure[:n // 2 + 1], kubbe[:n // 2 + 1])
        for h in (0.05, 0.2, 0.37, 0.5):
            a = mp.kesit_ozellikleri(kure, RHO, h)
            b = mp.kesit_ozellikleri(kubbe, RHO, h)
            for k in a:
                assert b[k] == pytest.approx(a[k], rel=1e-12, abs=0.0), k

    def test_olcek(self):
        p = orn.kubbeli_silindir(R, 1.0, n=60)
        a = mp.kutle_ozellikleri(p, RHO, [0.1, 0.5, 0.95])
        b = mp.kutle_ozellikleri(2.0 * p, RHO, [0.1, 0.5, 0.95])
        assert b['geometri']['V_ic_m3'] == pytest.approx(
            8.0 * a['geometri']['V_ic_m3'], rel=1e-13)
        for sa, sb in zip(a['satirlar'], b['satirlar']):
            assert sb['h_m'] == pytest.approx(2.0 * sa['h_m'], rel=1e-10)
            assert sb['z_km_m'] == pytest.approx(2.0 * sa['z_km_m'],
                                                 rel=1e-10)
            assert sb['I_km_donmus_kgm2'] == pytest.approx(
                32.0 * sa['I_km_donmus_kgm2'], rel=1e-9)
            assert sb['I_eksenel_donmus_kgm2'] == pytest.approx(
                32.0 * sa['I_eksenel_donmus_kgm2'], rel=1e-9)

    def test_doluluk_koku_toleransi(self):
        p = orn.kubbeli_silindir(R, 1.0, n=60)
        V_ic = mp.ic_hacim(p)
        for f in slosh_tablo.DOLULUK_IZGARASI:
            h = mp.doluluk_yuksekligi(p, f)
            V = mp.kesit_ozellikleri(p, RHO, h)['V_sivi_m3']
            assert abs(V - f * V_ic) <= mp.DOLULUK_KOK_BAGIL_TOL * V_ic

    def test_omuz_yatay_parca(self):
        """Ara yatay parça (omuz) hacim taşımaz; r(h) aşağıdan sınırdır."""
        p = [(0, 0), (0.5, 0), (0.5, 1.0), (0.3, 1.0), (0.3, 2.0), (0, 2.0)]
        V = math.pi * (0.25 * 1.0 + 0.09 * 1.0)
        assert mp.ic_hacim(p) == pytest.approx(V, rel=1e-14)
        assert mp.kesit_yaricapi(p, 1.0) == 0.5
        assert mp.kesit_yaricapi(p, 1.5) == pytest.approx(0.3, rel=PLATFORM_GURULTU_TABANI_REL)


class TestProfilKapisi:
    @pytest.mark.parametrize('profil, sebep, ayrinti', [
        ([(0.1, 0), (0.5, 0), (0.5, 1), (0, 1)], 'YUZEY_KAPALI_DEGIL',
         'bas_kapanmiyor'),
        ([(0, 0), (0.5, 0), (0.5, 1), (0.2, 1)], 'YUZEY_KAPALI_DEGIL',
         'bas_kapanmiyor'),
        ([(0, 0), (0.5, 0), (0.5, 1), (0.3, 0.8), (0, 1.2)],
         'PROFIL_TEK_DEGERLI_DEGIL', 'z_monoton_degil'),
        ([(0, 0), (0.5, 0), (0, 0.5), (0.5, 1), (0, 1)],
         'PROFIL_TEK_DEGERLI_DEGIL', 'ic_dugum_eksende'),
        ([(0, 0), (0.5, 0), (0.3, 0), (0.5, 0), (0.5, 1), (0, 1)],
         'PROFIL_TEK_DEGERLI_DEGIL', 'kendini_kesiyor'),
        ([(0, 0), (0.5, 0), (0.5, 0), (0.5, 1), (0, 1)],
         'PROFIL_TEK_DEGERLI_DEGIL', 'kendini_kesiyor'),
    ])
    def test_kapi_redleri(self, profil, sebep, ayrinti):
        with pytest.raises(mp.ProfilHatasi) as e:
            mp.profil_dogrula(profil)
        assert e.value.sebep == sebep
        assert e.value.sebep in slosh_tablo.SEBEP_KODLARI
        assert e.value.ayrinti == ayrinti

    @pytest.mark.parametrize('profil, kod', [
        ([(0, 0), (0.5, float('nan')), (0, 1)], 'DEGER_GECERSIZ'),
        ([(0, 0), (0.5, float('inf')), (0, 1)], 'DEGER_GECERSIZ'),
        ([(0, 0), (0, 1)], 'DEGER_GECERSIZ'),
        ([(0, 0), (-0.5, 0.5), (0, 1)], 'DEGER_GECERSIZ'),
        ([(0, 0, 0), (0.5, 0.5, 0), (0, 1, 0)], 'TUR_HATASI'),
        ('abc', 'TUR_HATASI'),
    ])
    def test_okuma_redleri(self, profil, kod):
        with pytest.raises(mp.ProfilHatasi) as e:
            mp.profil_dogrula(profil)
        assert e.value.okuma_kodu == kod

    def test_nokta_siniri_sozlesmeden(self):
        n = slosh_tablo.PROFIL_NOKTA_SINIRI + 1
        z = np.linspace(0.0, 1.0, n)
        r = np.full(n, 0.5)
        r[0] = r[-1] = 0.0
        z[1] = 0.0
        z[-2] = 1.0
        with pytest.raises(mp.ProfilHatasi) as e:
            mp.profil_dogrula(np.stack([r, z], axis=1))
        assert e.value.okuma_kodu == 'BOYUT_SINIRI'


class TestGirdiKapilari:
    p = [(0, 0), (0.5, 0), (0.5, 1), (0, 1)]

    @pytest.mark.parametrize('d', [0.0, 1.0, -0.1, 1.5, float('nan'), True])
    def test_doluluk_aralik_disi(self, d):
        with pytest.raises(ValueError):
            mp.kutle_ozellikleri(self.p, RHO, [d])

    @pytest.mark.parametrize('rho', [0.0, -1.0, float('inf'), True, '1000'])
    def test_yogunluk(self, rho):
        with pytest.raises(ValueError):
            mp.kutle_ozellikleri(self.p, rho, [0.5])

    def test_tank_cercevesi_zorunlu(self):
        with pytest.raises(ValueError):
            mp.kutle_ozellikleri([(0, 1), (0.5, 1), (0.5, 2), (0, 2)], RHO,
                                 [0.5])

    def test_izgara_ve_kodlar_tek_yerde(self):
        """Bu modül ızgara ya da sebep kodu TANIMLAMAZ; sözleşmeden alır."""
        assert mp.DOLULUK_IZGARASI is slosh_tablo.DOLULUK_IZGARASI
        assert mp.SEBEP_KODLARI is slosh_tablo.SEBEP_KODLARI
        assert mp.PROFIL_NOKTA_SINIRI is slosh_tablo.PROFIL_NOKTA_SINIRI
