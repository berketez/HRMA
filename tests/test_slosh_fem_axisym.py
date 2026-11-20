"""V307/K3b — eksenel simetrik tankta sayısal çalkantı (TANK §D, §E).

Modül: ``hrma/analysis/slosh_fem_axisym.py``. Tasarım:
``docs/tasarim/v307/TANK_GEOMETRI_TASARIM.md`` §D (ağ, SE, çıkarım,
süpürme, yakınsama), §E.1–E.3 (doğrulama hedefleri). Sözleşme
``hrma.analysis.slosh_tablo`` (yalnız içe aktarılır).

Silindir kapalı biçimi bu dosyada BAĞIMSIZ yazılır (K1'in üreticisi bu
dalda yok; ana model kararı 4 Kas): Dodge 2000 Denk. (1.40), Tablo 3.2;
SP-8009 Tablo I; Γ1 CALKANTI (A-10). ξn scipy ``jnp_zeros``.
"""

import json
import math

import numpy as np
import pytest
from tests.support.esikler import PLATFORM_GURULTU_TABANI_REL
from scipy.special import jnp_zeros

from hrma.analysis import slosh_fem_axisym as se
from hrma.analysis import slosh_tablo as T
from hrma.analysis.tank_mass_properties import (
    doluluk_yuksekligi,
    kesit_ozellikleri,
)

XI1, XI2 = (float(x) for x in jnp_zeros(1, 2))


# ---------------------------------------------------------------------------
# Profiller (tank çerçevesi, r ≥ 0, z alt kutuptan yukarı)
# ---------------------------------------------------------------------------
def silindir(R, H):
    return np.array([[0.0, 0.0], [R, 0.0], [R, H], [0.0, H]])


def kure(R, n):
    t = np.linspace(0.0, math.pi, n + 1)
    p = np.stack([R * np.sin(t), R * (1.0 - np.cos(t))], axis=1)
    p[0, 0] = 0.0
    p[-1, 0] = 0.0
    return p


def yarim_kure_tabanli_silindir(R, L, n_ceyrek):
    """Alt baş yarım küre (çeyrek çember n_ceyrek parça), üstü düz kapak."""
    t = np.linspace(0.0, 0.5 * math.pi, n_ceyrek + 1)
    alt = np.stack([R * np.sin(t), R * (1.0 - np.cos(t))], axis=1)
    alt[0, 0] = 0.0
    return np.concatenate([alt, [[R, R + L], [0.0, R + L]]])


def kapali_bicim(R, h):
    """Düz tabanlı silindir (CALKANTI §A.1.1); konum serbest yüzeye göre."""
    th = math.tanh(XI1 * h / R)
    k1 = XI1 / R * th
    return {'kappa1': k1,
            'kappa2': XI2 / R * math.tanh(XI2 * h / R),
            'm1_oran': 2.0 * R * th / (XI1 * (XI1 ** 2 - 1.0) * h),
            'z1_yuzey': -(2.0 * R / XI1) * math.tanh(XI1 * h / (2.0 * R)),
            'L1': 1.0 / k1,
            'Gamma1': (XI1 ** 2 - 1.0) / (2.0 * XI1 * th)}


# TANK §E.1 tablosu (betik v1 §3, R = 0,5 m; konumlar yüzeye göre).
E1_TABLO = {
    0.3: (0.7609744626, -0.1462991677, 0.5406599053),
    1.0: (0.4321966868, -0.3944078312, 0.2855841288),
    2.0: (0.2269669687, -0.5164659034, 0.2719085402),
    4.0: (0.1136271982, -0.5424414582, 0.2715646347),
}


# ---------------------------------------------------------------------------
# Kareleme
# ---------------------------------------------------------------------------
class TestKareleme:
    def test_dunavant_derece4_tam_derece5_degil(self):
        L, W = se.UCGEN_KARE_L, se.UCGEN_KARE_W
        assert L.shape == (6, 3) and abs(W.sum() - 1.0) < 1e-15
        assert np.all(L > 0.0)                      # noktalar eleman içinde
        x, y = L[:, 1], L[:, 2]
        # Başvuru üçgeninde ∫ x^a y^b = a! b!/(a+b+2)!, alan 1/2.
        for a in range(6):
            for b in range(6 - a):
                tam = math.factorial(a) * math.factorial(b) \
                    / math.factorial(a + b + 2)
                kare = 0.5 * float(np.sum(W * x ** a * y ** b))
                if a + b <= 4:
                    assert kare == pytest.approx(tam, rel=1e-13, abs=1e-16)
        tam5 = math.factorial(5) / math.factorial(7)
        assert abs(0.5 * float(np.sum(W * x ** 5)) - tam5) > 1e-6


# ---------------------------------------------------------------------------
# Ağ (kalem 5, TANK §D.3)
# ---------------------------------------------------------------------------
class TestAg:
    def test_silindir_agi_kenarlar_ve_hacim(self):
        R, h = 0.5, 0.4
        p = silindir(R, 1.0)
        ag = se.build_liquid_mesh(p, h, 8, 16)
        X = ag.dugum
        assert np.all(X[ag.eksen, 0] == 0.0)
        assert np.all(X[ag.yuzey, 1] == h)
        assert X[ag.kose_C, 0] == R and X[ag.kose_C, 1] == h
        assert ag.meta['D_r_m'] == R and ag.meta['D_z_m'] == 0.0
        assert ag.eleman.shape == (2 * 8 * 16, 6)
        assert ag.meta['ucgen_kalitesi_min'] > 0.0
        V = se.coz(ag)['hacim_m3']
        assert V == pytest.approx(math.pi * R * R * h, rel=1e-13)

    def test_kutup_dejenere_eleman_yok_ve_ceper_profilde(self):
        R = 1.0
        p = kure(R, 64)
        for f in (0.005, 0.3, 0.5, 0.995):
            h = doluluk_yuksekligi(p, f)
            ag = se.build_liquid_mesh(p, h, 8, 16)
            # Eksende tek düğüme çöken üçgen yok: her köşe üçgeninin en
            # küçük köşe sinüsü pozitif.
            assert ag.meta['ucgen_kalitesi_min'] > 0.0
            E = ag.eleman
            for i in range(3):
                a, b = E[:, i], E[:, (i + 1) % 3]
                assert np.all(np.hypot(*(ag.dugum[a] - ag.dugum[b]).T) > 0)
            # Çeperdeki bütün düğümler (orta düğüm dahil) profil üstünde.
            ceper = se.islak_ceper(p, h)
            na = 2 * ag.n_r + 1
            idx = list(range(na)) + [b * na + na - 1
                                     for b in range(2 * ag.n_z + 1)]
            for (r, z) in ag.dugum[idx]:
                assert _cizgiye_uzaklik(ceper, r, z) <= 1e-13

    def test_kose_oturtma_pahli_kose(self):
        """İki 45° kırıklı pah: D biri, öbürü ızgara düğümüne oturur."""
        R = 0.25
        p = np.array([[0.0, 0.0], [0.245, 0.0], [R, 0.005], [R, 1.0],
                      [0.0, 1.0]])
        ag = se.build_liquid_mesh(p, 0.1, 8, 16)
        assert ag.meta['oturan_kose'] == 1
        assert ag.meta['oturmayan_kose'] == 0
        dugumler = {tuple(np.round(x, 15)) for x in ag.dugum}
        assert (0.245, 0.0) in dugumler and (R, 0.005) in dugumler

    def test_kose_oturtmasi_yakinsamayi_duzeltir(self):
        R = 0.25
        p = np.array([[0.0, 0.0], [0.245, 0.0], [R, 0.005], [R, 1.0],
                      [0.0, 1.0]])
        V = kesit_ozellikleri(p, 1.0, 0.1)['V_sivi_m3']
        yk = se.yakinsama_cozumu(p, 0.1, V, R)
        assert yk['zayif'] == []
        k = [d['modlar'][0]['kappa_1m'] for d in yk['duzeyler']]
        assert abs(k[0] - k[2]) / k[2] < 1e-5

    def test_ic_kenar_orta_dugumu_kiris_ortasinda(self):
        p = kure(1.0, 128)
        ag = se.build_liquid_mesh(p, 0.3, 4, 8)
        na = 2 * ag.n_r + 1
        ceper = set(range(na)) | {b * na + na - 1
                                  for b in range(2 * ag.n_z + 1)}
        for (u, v, w) in ((0, 1, 3), (1, 2, 4), (2, 0, 5)):
            for e in ag.eleman:
                if int(e[w]) in ceper:
                    continue
                orta = 0.5 * (ag.dugum[e[u]] + ag.dugum[e[v]])
                assert np.allclose(ag.dugum[e[w]], orta, rtol=0, atol=1e-15)


def _cizgiye_uzaklik(c, r, z):
    a, b = c[:-1], c[1:]
    v = b - a
    L2 = np.sum(v * v, axis=1)
    t = np.clip(((r - a[:, 0]) * v[:, 0] + (z - a[:, 1]) * v[:, 1]) / L2,
                0.0, 1.0)
    d = np.hypot(r - (a[:, 0] + t * v[:, 0]), z - (a[:, 1] + t * v[:, 1]))
    return float(d.min())


# ---------------------------------------------------------------------------
# E.1 düz tabanlı silindir ⟷ analitik
# ---------------------------------------------------------------------------
class TestE1Silindir:
    def test_e1_tablosu_bagimsiz_kapali_bicimle_ayni(self):
        R = 0.5
        for hR, (m1, z1, L1) in E1_TABLO.items():
            c = kapali_bicim(R, hR * R)
            assert c['m1_oran'] == pytest.approx(m1, abs=1e-10)
            assert c['z1_yuzey'] == pytest.approx(z1, abs=1e-10)
            assert c['L1'] == pytest.approx(L1, abs=1e-10)

    @pytest.mark.parametrize('hR', sorted(E1_TABLO))
    def test_se_analitikle_uyusur(self, hR):
        R = 0.5
        h = hR * R
        p = silindir(R, max(4.5 * R, h))
        yk = se.yakinsama_cozumu(p, h, math.pi * R * R * h, R)
        m1, m2 = yk['ince']['modlar']
        c = kapali_bicim(R, h)
        m1_tab, z1_tab, L1_tab = E1_TABLO[hR]
        # Tasarım kabulü (TANK §E.1): bağıl 10⁻³, z1 10⁻³ R. Ölçülen
        # doğruluk (en ince ağ) ≤ 3,5·10⁻⁸; bekçi 10⁻⁶ ile kilitler.
        assert m1['kappa_1m'] == pytest.approx(c['kappa1'], rel=1e-6)
        assert m1['m_oran'] == pytest.approx(m1_tab, rel=1e-6)
        assert m1['z_m'] - h == pytest.approx(z1_tab, abs=1e-6 * R)
        assert m1['L_m'] == pytest.approx(L1_tab, rel=1e-6)
        assert m1['Gamma'] == pytest.approx(c['Gamma1'], rel=1e-5)
        assert m2['kappa_1m'] == pytest.approx(c['kappa2'], rel=1e-5)
        assert yk['zayif'] == []

    def test_yakinsama_mertebesi_p2(self):
        """Kaba temel ağda (2, 4) gözlenen mertebe ≥ 3,5 (P2'de 4)."""
        R, h = 0.5, 0.5
        p = silindir(R, 1.0)
        beta = 4 * math.log(se.SE_BUYUME_ORANI)
        q = []
        for k in (1, 2, 4):
            c = se.cozum_h(p, h, math.pi * R * R * h, 2 * k, 4 * k,
                           math.exp(beta / (4 * k)), beta=beta)
            q.append(c['modlar'][0]['kappa_1m'])
        p_k = math.log2(abs(q[0] - q[1]) / abs(q[1] - q[2]))
        assert p_k >= 3.5


# ---------------------------------------------------------------------------
# E.2 küre ⟷ SP-106 Tablo 2.3, Dodge Şekil 3.4, askı = merkez
# ---------------------------------------------------------------------------
# SP-106 Tablo 2.3 (PDF s. 59): kuram aralığı λ1 = √(κ1 R).
SP106_ARALIK = {0.05: (1.00, 1.02), 0.50: (1.06, 1.10), 1.00: (1.22, 1.25),
                1.8: (1.83, 2.04)}
# Dodge 2000 Şekil 3.4 (sayısallaştırıldı, ±0,01): doluluk → (m1/m, L1/R).
DODGE_SEKIL34 = {0.30: (0.714, 0.743), 0.50: (0.578, 0.638),
                 0.70: (0.428, 0.524), 0.90: (0.222, 0.354)}


@pytest.fixture(scope='module')
def kure1024():
    return kure(1.0, 1024)


class TestE2Kure:
    @pytest.mark.parametrize('hR', sorted(SP106_ARALIK))
    def test_sp106_tablo23_araligi(self, kure1024, hR):
        R = 1.0
        V = kesit_ozellikleri(kure1024, 1.0, hR * R)['V_sivi_m3']
        yk = se.yakinsama_cozumu(kure1024, hR * R, V, R)
        lam = math.sqrt(yk['ince']['modlar'][0]['kappa_1m'] * R)
        lo, hi = SP106_ARALIK[hR]
        assert lo * 0.98 <= lam <= hi * 1.02
        if hR == 1.0:
            assert abs(lam - 1.25) <= 0.01       # Budiansky, Şekil 3.4

    @pytest.mark.parametrize('f', sorted(DODGE_SEKIL34))
    def test_dodge_sekil34(self, kure1024, f):
        R = 1.0
        h = doluluk_yuksekligi(kure1024, f)
        V = kesit_ozellikleri(kure1024, 1.0, h)['V_sivi_m3']
        m1 = se.yakinsama_cozumu(kure1024, h, V, R)['ince']['modlar'][0]
        m1_ref, L1_ref = DODGE_SEKIL34[f]
        assert abs(m1['m_oran'] - m1_ref) <= 0.02
        assert abs(m1['L_m'] / R - L1_ref) <= 0.02

    @pytest.mark.parametrize('f', (0.005, 0.1, 0.3, 0.5, 0.7, 0.9, 0.995))
    def test_aski_noktasi_kure_merkezinde(self, kure1024, f):
        """Dodge 2000 s. 48: kürede askı noktası merkezde (kesin özellik).
        (A-9) çıkarımının bağımsız testi; kabul 2·10⁻³ R (TANK §E.2)."""
        R = 1.0
        h = doluluk_yuksekligi(kure1024, f)
        V = kesit_ozellikleri(kure1024, 1.0, h)['V_sivi_m3']
        m1 = se.yakinsama_cozumu(kure1024, h, V, R)['ince']['modlar'][0]
        assert abs(m1['z_m'] + m1['L_m'] - R) <= 2e-3 * R
        # Ölçülen ≤ 1,7·10⁻⁴ R (256 parça); 1024 parçada bekçi 5·10⁻⁴ R.
        assert abs(m1['z_m'] + m1['L_m'] - R) <= 5e-4 * R


# ---------------------------------------------------------------------------
# E.3 tutarlılık
# ---------------------------------------------------------------------------
class TestE3Tutarlilik:
    @pytest.mark.parametrize('hR', (0.3, 0.7, 1.0))
    def test_yarim_kure_tabanli_silindir_kureyle_ayni(self, hR):
        """h ≤ R'de ıslak sınır ve yüzey özdeş: sonuç ağdan bağımsız aynı."""
        R = 1.0
        k = kure(R, 256)
        y = yarim_kure_tabanli_silindir(R, 2.0, 128)
        V = kesit_ozellikleri(k, 1.0, hR)['V_sivi_m3']
        Vy = kesit_ozellikleri(y, 1.0, hR)['V_sivi_m3']
        assert Vy == pytest.approx(V, rel=1e-12)
        a = se.cozum_h(k, hR, V)['modlar']
        b = se.cozum_h(y, hR, V)['modlar']
        for ma, mb in zip(a, b):
            for alan in ('kappa_1m', 'm_oran', 'z_m', 'Gamma'):
                assert mb[alan] == pytest.approx(ma[alan], rel=1e-6,
                                                 abs=1e-12)

    def test_olcek(self):
        p = kure(1.0, 128)
        V = kesit_ozellikleri(p, 1.0, 0.6)['V_sivi_m3']
        a = se.cozum_h(p, 0.6, V)['modlar'][0]
        b = se.cozum_h(2.0 * p, 1.2, 8.0 * V)['modlar'][0]
        assert b['kappa_1m'] == pytest.approx(0.5 * a['kappa_1m'], rel=1e-10)
        assert b['m_oran'] == pytest.approx(a['m_oran'], rel=1e-10)
        assert b['z_m'] == pytest.approx(2.0 * a['z_m'], rel=1e-10)
        assert b['L_m'] == pytest.approx(2.0 * a['L_m'], rel=1e-10)

    def test_hacim_tutarliligi_kure(self):
        """Eğri çeper kenarlı ağın hacmi profil hacmine yakınsar (aynı
        eşleme fonksiyonu β ile iç içe düzeyler; ürün yolu da böyle)."""
        p = kure(1.0, 40000)
        V = kesit_ozellikleri(p, 1.0, 1.0)['V_sivi_m3']
        beta = 8 * math.log(se.SE_BUYUME_ORANI)
        hata = []
        for n in (4, 8, 16):
            ag = se.build_liquid_mesh(p, 1.0, n, 2 * n, beta=beta)
            hata.append(abs(se.coz(ag)['hacim_m3'] / V - 1.0))
        assert hata[2] < 1e-7
        assert hata[0] / hata[1] > 8.0 and hata[1] / hata[2] > 8.0


# ---------------------------------------------------------------------------
# Yakınsama hükmü (TANK §D.5, §D.5.1)
# ---------------------------------------------------------------------------
class TestYakinsamaHukmu:
    def test_dorduncu_mertebe(self):
        q = [1.0 + 1e-2 * (0.5 ** k) ** 4 for k in range(3)]
        s = se.gozlenen_mertebe(*q, olcek=1.0, tol=1e-3)
        assert s['durum'] == 'yakinsadi' and s['kabul']
        assert s['p'] == pytest.approx(4.0, rel=1e-9)
        assert s['q_star'] == pytest.approx(1.0, abs=1e-12)

    def test_yavas_yakinsama_beyan(self):
        q = [1.0 + 0.5 * (0.5 ** k) ** 1.0 for k in range(3)]
        s = se.gozlenen_mertebe(*q, olcek=1.0, tol=1e-3)
        assert s['p'] == pytest.approx(1.0) and not s['kabul']

    def test_monoton_degil_esik_ustu_beyan(self):
        s = se.gozlenen_mertebe(1.0, 1.001, 0.9995, olcek=1.0, tol=1e-3)
        assert s['durum'] == 'monoton_degil' and not s['kabul']
        assert s['hata'] == pytest.approx(1.5e-3)

    def test_esik_alti_ve_yuvarlama(self):
        s = se.gozlenen_mertebe(1.0, 1.00002, 1.00001, olcek=1.0, tol=1e-3)
        assert s['durum'] == 'esik_alti' and s['kabul']
        s = se.gozlenen_mertebe(1.0, 1.0, 1.0 + 1e-14, olcek=1.0, tol=1e-3)
        assert s['durum'] == 'yuvarlama' and s['kabul']

    def test_mertebe_dusuk_ama_hata_kucuk_degilse_beyan(self):
        # p < 1,5 olan ve eşik üstü farklı dizi: tasarım kuralı BEYAN.
        q = [1.0 + 2e-3 * (0.5 ** k) ** 1.2 for k in range(3)]
        s = se.gozlenen_mertebe(*q, olcek=1.0, tol=1e-3)
        assert s['p'] < se.SE_MERTEBE_BEYAN_ESIGI and not s['kabul']


# ---------------------------------------------------------------------------
# Doluluk süpürmesi → sözleşme tablosu (kalem 6, TANK §D.4)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def kure_tablosu():
    return se.se_tablosu('oksitleyici', kure(0.6, 512), 1141.0, 'LOX',
                         kaynak='test: analitik küre 512 parça')


class TestTablo:
    @pytest.mark.slow
    def test_kure_tablosu_sozlesmeyi_gecer(self, kure_tablosu):
        t = kure_tablosu
        assert isinstance(t, T.SloshTablo)
        assert t.yontem == T.YONTEM_SAYISAL_SE
        assert t.geometri['tur'] == T.GEOMETRI_PROFIL
        sat = t.satirlar
        assert [s['doluluk'] for s in sat] == list(T.DOLULUK_IZGARASI)
        R = t.geometri['R_ref_m']
        for s in sat:
            assert s['durum'] == T.DURUM_GECERLI, s['ek']
            assert s['m0_oran'] + s['m1_oran'] == pytest.approx(1.0, abs=PLATFORM_GURULTU_TABANI_REL)
            # moment dengesi (Dodge (3.2)), dogrula() da denetler
            assert (s['m0_oran'] * s['z0_m'] + s['m1_oran'] * s['z1_m']
                    == pytest.approx(s['z_km_m'], abs=1e-12))
            assert s['m1_oran'] + s['m2_oran'] < 1.0
            assert s['I0_kgm2'] == 0.0 and s['I0_kaynak'] == se.I0_KAYNAK_KURE
            assert abs(s['z_aski_m'] - R) <= 2e-3 * R
            assert s['ek']['D_secimi'] in ('kose', 'oran')
        # JSON ve CSV gidiş-dönüş (sözleşme okuyucuları)
        j = T.json_oku(T.json_yaz(t))
        assert j.satirlar == t.satirlar
        c = T.csv_oku(T.csv_yaz(t))
        assert [s['kappa1_1m'] for s in c.satirlar] == \
            [s['kappa1_1m'] for s in sat]

    @pytest.mark.slow
    def test_kure_tablosu_ara_deger_ve_izgara_disi(self, kure_tablosu):
        t = kure_tablosu
        assert t.ara(0.004)['sebep'] == ['IZGARA_DISI']
        assert t.ara(0.996)['durum'] == T.DURUM_RET
        a = t.ara(0.42)
        assert a['durum'] == T.DURUM_GECERLI
        assert a['z_aski_m'] == pytest.approx(a['z1_m'] + a['L1_m'])

    @pytest.mark.slow
    def test_silindir_tablosu_kapali_bicimle(self):
        R, H = 0.5, 2.0
        t = se.se_tablosu('yakit', silindir(R, H), 800.0, 'RP-1')
        for s in t.satirlar:
            c = kapali_bicim(R, s['h_m'])
            assert s['durum'] == T.DURUM_GECERLI
            assert s['kappa1_1m'] == pytest.approx(c['kappa1'], rel=1e-6)
            assert s['m1_oran'] == pytest.approx(c['m1_oran'], rel=1e-6)
            assert s['z1_m'] - s['h_m'] == pytest.approx(c['z1_yuzey'],
                                                         abs=1e-6 * R)
            assert s['I0_kgm2'] is None
            assert s['I0_kaynak'] == se.I0_KAYNAK_HESAPLANMADI
        # Sığ uç (doluluk 0,005; h/R = 0,02): m1/m → 2/(ξ1² − 1) sınırına
        # yakın (CALKANTI §C-d).
        s0 = t.satirlar[0]
        assert s0['m1_oran'] == pytest.approx(kapali_bicim(R, s0['h_m'])
                                              ['m1_oran'], rel=1e-6)
        assert s0['m1_oran'] < 2.0 / (XI1 ** 2 - 1.0)

    def test_zayif_yakinsama_satiri_beyanli(self, monkeypatch):
        monkeypatch.setattr(se, 'SE_YAKINSAMA_BAGIL_TOL', 1e-14)
        monkeypatch.setattr(se, 'SE_YAKINSAMA_Z_TOL_ORANI', 1e-14)
        p = kure(1.0, 64)
        geo = {'R_ref_m': 1.0}
        km = {'doluluk': 0.5, 'h_m': 1.0, 'V_sivi_m3': 2.0 * math.pi / 3.0,
              'm_sivi_kg': 2.0 * math.pi / 3.0, 'z_km_m': 0.625,
              'I_km_donmus_kgm2': 0.1, 'I_eksenel_donmus_kgm2': 0.1,
              'A_yuzey_m2': math.pi, 'R_yuzey_m': 1.0}
        s = se.se_satiri(p, km, geo, 1.0)
        assert s['sebep'] == ['AG_YAKINSAMA_ZAYIF']
        assert s['durum'] == T.DURUM_BEYANLI
        assert s['ek']['yakinsama_zayif']


    def test_ag_kurulamayan_satir_ret_ag_uretilemedi(self, monkeypatch):
        """v307-2 (K6, K3b önerisi): ağı kurulamayan doluluk tabloyu
        düşürmez; o satır RET ``AG_URETILEMEDI``, model alanları null,
        öbür satırlar aynı. Öbür SE hataları satıra indirgenmez."""
        p = silindir(0.5, 1.0)
        once = se.se_tablosu('yakit', p, 800.0, 'RP-1', n_r=2, n_z=4)
        hedef = once.satirlar[12]['h_m']
        asil = se.yakinsama_cozumu

        def bozuk(profil, h, *a, **k):
            if h == hedef:
                raise se.SloshSEHatasi('test: ters dönmüş eleman',
                                       'AG_GECERSIZ', alan='profil_rz_m')
            return asil(profil, h, *a, **k)

        monkeypatch.setattr(se, 'yakinsama_cozumu', bozuk)
        t = se.se_tablosu('yakit', p, 800.0, 'RP-1', n_r=2, n_z=4)
        s = t.satirlar[12]
        assert s['durum'] == T.DURUM_RET and s['sebep'] == ['AG_URETILEMEDI']
        assert all(s[k] is None for k in T.SATIR_MODEL)
        assert s['I0_kgm2'] is None and s['ek']['se_hata_kodu'] == 'AG_GECERSIZ'
        assert s['h_m'] == hedef                       # geometri dolu
        for i, (a, b) in enumerate(zip(once.satirlar, t.satirlar)):
            if i != 12:
                assert a == b
        assert any('AG_URETILEMEDI' in k for k in t.sozluk()['kunye'])
        assert T.json_oku(T.json_yaz(t)).sozluk() == t.sozluk()
        d = T.DOLULUK_IZGARASI
        assert t.ara(0.5 * (d[12] + d[13]))['durum'] == T.DURUM_RET

        def ozdeger(profil, h, *a, **k):
            raise se.SloshSEHatasi('test', 'OZDEGER')

        monkeypatch.setattr(se, 'yakinsama_cozumu', ozdeger)
        with pytest.raises(se.SloshSEHatasi) as e:
            se.se_tablosu('yakit', p, 800.0, 'RP-1', n_r=2, n_z=4)
        assert e.value.kod == 'OZDEGER'


# ---------------------------------------------------------------------------
# Saldırgan / geçersiz girdi
# ---------------------------------------------------------------------------
class TestGirdiKapilari:
    @pytest.mark.parametrize('n_r', (1, 10 ** 6, True, 8.0, -3))
    def test_n_r_reddi(self, n_r):
        with pytest.raises(se.SloshSEHatasi) as e:
            se.yakinsama_cozumu(silindir(1.0, 1.0), 0.5, math.pi * 0.5, 1.0,
                                n_r=n_r)
        assert e.value.kod == 'DEGER_GECERSIZ'

    @pytest.mark.parametrize('h', (float('nan'), float('inf'), -0.1, 0.0,
                                   1.5, '0.5'))
    def test_h_reddi(self, h):
        with pytest.raises(se.SloshSEHatasi) as e:
            se.build_liquid_mesh(silindir(1.0, 1.0), h)
        assert e.value.kod == 'DEGER_GECERSIZ'

    def test_ust_kutupta_yuzey_yok(self):
        with pytest.raises(se.SloshSEHatasi) as e:
            se.build_liquid_mesh(kure(1.0, 32), 2.0)
        assert e.value.kod == 'DEGER_GECERSIZ'

    def test_profil_kapisi_adli(self):
        with pytest.raises(se.SloshSEHatasi) as e:
            se.build_liquid_mesh([[0, 0], [1, 0.5], [1, 0.2], [0, 1]], 0.4)
        assert e.value.kod == 'PROFIL'
        assert e.value.profil_hatasi.sebep == 'PROFIL_TEK_DEGERLI_DEGIL'
        with pytest.raises(se.SloshSEHatasi) as e:
            se.build_liquid_mesh([[0, 0], [1, float('nan')], [0, 1]], 0.4)
        assert e.value.kod == 'PROFIL'

    def test_tank_cercevesi_zorunlu(self):
        p = silindir(1.0, 1.0) + np.array([0.0, 0.3])
        with pytest.raises(se.SloshSEHatasi) as e:
            se.build_liquid_mesh(p, 0.5)
        assert e.value.kod == 'DEGER_GECERSIZ'

    def test_yogunluk_reddi(self):
        with pytest.raises(se.SloshSEHatasi):
            se.se_tablosu('yakit', silindir(1.0, 1.0), -5.0, 'x')


# ---------------------------------------------------------------------------
# Kalem 7: kubbe sapması BEYANI ölçümle tutarlı mı?
# ---------------------------------------------------------------------------
def elips_basli_silindir(R, L, k, n=256):
    t = np.linspace(0.0, 0.5 * math.pi, n + 1)
    alt = np.stack([R * np.sin(t), k * R * (1.0 - np.cos(t))], axis=1)
    ust = np.stack([R * np.cos(t), k * R + L + k * R * np.sin(t)], axis=1)
    p = np.concatenate([alt, ust])
    p[0, 0] = 0.0
    p[-1, 0] = 0.0
    return p


class TestKubbeSapmasiBeyani:
    """Beyan metnindeki sayılar ölçümün yukarı yuvarlanmışıdır; ölçüm
    değişirse (çözücü ya da çıkarım kayarsa) bekçi kırmızı olur."""

    @pytest.mark.parametrize('k, f, onek', ((0.5, 0.075, 'elips21'),
                                             (1.0, 0.3, 'yarim_kure')))
    def test_en_kotu_satir_beyanin_icinde_ve_yakininda(self, k, f, onek):
        R, L = 1.0, (4.0 if k == 0.5 else 1.0)
        p = elips_basli_silindir(R, L, k)
        h = doluluk_yuksekligi(p, f)
        V = kesit_ozellikleri(p, 1.0, h)['V_sivi_m3']
        Vb = 2.0 / 3.0 * math.pi * R * R * k * R
        assert Vb < V                                   # silindir bölgesi
        m1 = se.yakinsama_cozumu(p, h, V, R)['ince']['modlar'][0]
        c = kapali_bicim(R, V / (math.pi * R * R))
        f1 = abs(math.sqrt(c['kappa1'] / m1['kappa_1m']) - 1.0) * 100.0
        mm = abs(c['m1_oran'] / m1['m_oran'] - 1.0) * 100.0
        par = se.TANK_BASLARI_BEYANI['parametreler']
        assert f1 <= par[f'{onek}_f1_yuzde']
        assert mm <= par[f'{onek}_m1_yuzde']
        # Beyan şişirilmiş değil: en kötü satır sınırın %75'inden büyük.
        assert f1 >= 0.75 * par[f'{onek}_f1_yuzde']
        assert mm >= 0.75 * par[f'{onek}_m1_yuzde']

    @pytest.mark.parametrize('k, onek', ((0.5, 'elips21'),
                                         (1.0, 'yarim_kure')))
    def test_birlesim_cizgisinde_beyan_sinirda(self, k, onek):
        """K6 tasarım düzeltmesi: sapmanın üst sınırı yüzeyin tam alt baş
        birleşim çizgisinde (h = kR) olduğu değerdir; ürünün bölge kuralı
        (gerçek profil hacmi) bu satırı silindir bölgesi sayar. Beyan bu
        değeri kapsar ve şişirilmiş değildir (≥ %95)."""
        R = 1.0
        p = elips_basli_silindir(R, 2.0, k)
        h = k * R
        V = kesit_ozellikleri(p, 1.0, h)['V_sivi_m3']
        m1 = se.yakinsama_cozumu(p, h, V, R)['ince']['modlar'][0]
        c = kapali_bicim(R, V / (math.pi * R * R))
        par = se.TANK_BASLARI_BEYANI['parametreler']
        olcum = {
            'f1_yuzde': abs(math.sqrt(c['kappa1'] / m1['kappa_1m']) - 1) * 100,
            'm1_yuzde': abs(c['m1_oran'] / m1['m_oran'] - 1) * 100,
            'z1_R': abs(c['z1_yuzey'] - (m1['z_m'] - h)) / R,
            'aski_R': abs((c['z1_yuzey'] + c['L1'])
                          - (m1['z_m'] + m1['L_m'] - h)) / R,
        }
        for ad, deger in olcum.items():
            sinir = par[f'{onek}_{ad}']
            assert 0.95 * sinir <= deger <= sinir, (ad, deger, sinir)

    def test_beyan_metni_parametreleri_eksiksiz(self):
        b = se.TANK_BASLARI_BEYANI
        assert b['kod'] in T.SEBEP_KODLARI
        b['en'].format(**b['parametreler'])            # eksik yer tutucu yok
        assert 'invented' not in b['en'].lower()


# ---------------------------------------------------------------------------
# Kalem 8: (A-9) hacim integrali ⟷ Lomen CR-222 (3.83) + (B.7) çeper biçimi
# ---------------------------------------------------------------------------
class TestLomenCR222:
    """CR-222 (3.83): kütle konumu KM'ye göre −L(b_n − h_n)/b_n; (B.7)
    h_n'yi çeper integraline çevirir: −L + 2W/(κP), W = π∫(z − z_KM)Φ r dz
    (A→C çeper boyunca). Aynı SE çözümünde (A-9) ile uyuşmalı."""

    @pytest.mark.parametrize('profil, f', ((kure(1.0, 512), 0.5),
                                           (yarim_kure_tabanli_silindir(
                                               1.0, 2.0, 256), 0.6)))
    def test_kutle_konumu_iki_bicim(self, profil, f):
        h = doluluk_yuksekligi(profil, f)
        km = kesit_ozellikleri(profil, 1.0, h)
        ag = se.build_liquid_mesh(profil, h, 8, 16)
        c = se.coz(ag)
        k, P, Phi = float(c['kappa'][0]), float(c['P'][0]), c['Phi'][0]
        z_A9 = h + float(c['G'][0]) / (k * P)
        na, nb = 2 * ag.n_r + 1, 2 * ag.n_z + 1
        yol = list(range(na)) + [b * na + na - 1 for b in range(1, nb)]
        u, w = se.GAUSS_DUGUMLERI, se.GAUSS_AGIRLIKLARI
        N1 = np.stack([0.5 * u * (u - 1), 1 - u * u, 0.5 * u * (u + 1)], 1)
        dN = np.stack([u - 0.5, -2 * u, u + 0.5], 1)
        W = 0.0
        for i in range(0, len(yol) - 2, 2):
            kk = yol[i:i + 3]
            r, z, fi = ag.dugum[kk, 0], ag.dugum[kk, 1], Phi[kk]
            W += math.pi * float(np.sum(w * (N1 @ z - km['z_km_m'])
                                        * (N1 @ fi) * (N1 @ r) * (dN @ z)))
        L = h - km['z_km_m']
        z_cr222 = km['z_km_m'] - L + 2.0 * W / (k * P)
        assert z_cr222 == pytest.approx(z_A9, abs=1e-6)
