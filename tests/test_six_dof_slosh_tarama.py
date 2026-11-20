"""V307/ÇALKANTI-KARARLILIK — yanma boyunca tarama, en kötü pencere hükmü,
doğrusal sınır işareti, bafl dizisi ve tank ρ(t) bekçileri
(``hrma/analysis/six_dof_slosh.py``, ``slosh_analysis.halka_bafl_dizisi``,
``slosh_motor_baglanti`` ρ(t), hibrit motor ``liquid_density_kg_m3``).

Ne kilitlenir (fizik, bugünkü çıktı değil):
  * (B-1)–(B-3) dış kuvvetsiz enerji, momentum ve açısal momentumu korur;
    itkili boşlukta kökler nötrdür (kararsızlığın kaynağı aerodinamik
    bağlaşımdır, denklem hatası değil);
  * ürünün doğrusal modeli u → ∞'da Bauer'in denklemleriyle (NASA SP-106
    (7.42)–(7.45)) aynı kökleri verir; Bauer'in tehlike bölgesi kenarları
    kaynaktaki kapalı biçimle çıkar;
  * bağımsız Lagrange türetimi (gerçek sarkaç, atalet çerçevesi) ürün
    modeli + yerçekimi kinematiği ile aynı kökleri verir;
  * tarama pencere kenarlarını bağımsız kök bulmayla aynı yerde bulur;
    genel hüküm dört anın kaçırdığı pencereyi yakalar; pencerenin ζ_min'i
    bütün örneklerde kararlılığı sağlar ve fazlası değildir;
  * doğrusal sınır aşımından sonraki sayılar işaretlidir;
  * bafl dizisi hedef sönümü yüzeyin her konumunda sağlar ve pencereyi
    kapatır (zaman alanı yeniden koşusu dahil);
  * ρ(t) verilince doluluk hacimden kurulur; motor seriyi kendi tank
    çözümünden yayımlar.

Kanıt: docs/scofield/raw/OH/V307/calkanti-kararlilik/RAPOR.md.
Araç/tank sayıları KEYFÎ DOĞRULAMA GİRDİSİDİR (boyutça tutarlı).
"""
import json
import math

import numpy as np
import pytest
from scipy.integrate import quad, solve_ivp
from scipy.optimize import brentq

from hrma.analysis import six_dof_slosh as sds
from hrma.analysis import six_dof_trajectory as sdt
from hrma.analysis import slosh_analysis as sa
from hrma.analysis import slosh_motor_baglanti as smb
from hrma.analysis import slosh_tablo as stb
from hrma.analysis.six_dof_trajectory import SixDOFTrajectory
from tests.test_six_dof_slosh import RHO_LOX, _arac, _ornek4, _tank


def _salinimli(lam, esik=1e-9):
    z = np.array([x for x in lam if x.imag > esik])
    return z[np.argsort(z.imag)]


# ===========================================================================
# 1. Kararsızlık fiziği — bağımsız sınamalar
# ===========================================================================
class TestFizik:
    def test_dis_kuvvetsiz_enerji_ve_momentum_korunur(self):
        """İtkisiz, aerodinamiksiz, yerçekimsiz gövde + iki çalkantı kütlesi
        (sabit yay, ζ = 0): (B-1)–(B-3) toplam enerjiyi, doğrusal momentumu
        ve KM'ye göre açısal momentumu korur (enerji kaynağı yok)."""
        E = sds.E
        m, I3 = 400.0, np.array([12.0, 380.0, 380.0])
        m1 = np.array([21.6, 11.4])
        xi = np.array([0.63, -0.49])
        w1sq = np.array([18.8 ** 2, 19.8 ** 2])
        n = 2

        def rhs(_t, y):
            q = y[3:7] / np.linalg.norm(y[3:7])
            w = y[7:10]
            eta, etad = y[10:14].reshape(n, 2), y[14:18].reshape(n, 2)
            C = sdt._quat_to_dcm(q)
            w0 = -np.cross(w, I3 * w) / I3
            dxa, dxw, edd = sds.govde_duzeltmesi(
                m, I3, np.zeros(3), np.zeros(3), w0, w, m1, xi, w1sq,
                np.zeros(n), eta, etad)
            return np.concatenate([C @ dxa, sdt._quat_derivative(q, w),
                                   w0 + dxw, etad.ravel(), edd.ravel()])

        def korunan(y):
            q = y[3:7] / np.linalg.norm(y[3:7])
            w = y[7:10]
            eta, etad = y[10:14].reshape(n, 2), y[14:18].reshape(n, 2)
            C = sdt._quat_to_dcm(q)
            vb = C.T @ y[0:3]
            S, p_rel, h_rel = np.zeros(3), np.zeros(3), np.zeros(3)
            IO = np.diag(I3).astype(float)
            Ts = V = 0.0
            for k in range(n):
                r0 = np.array([xi[k], 0.0, 0.0])
                rk = r0 + E @ eta[k]
                Ev = E @ etad[k]
                S += m1[k] * (E @ eta[k])
                p_rel += m1[k] * Ev
                h_rel += m1[k] * np.cross(rk, Ev)
                IO += m1[k] * ((rk @ rk) * np.eye(3) - np.outer(rk, rk)
                               - (r0 @ r0) * np.eye(3) + np.outer(r0, r0))
                Ts += 0.5 * m1[k] * (Ev @ Ev)
                V += 0.5 * m1[k] * w1sq[k] * (eta[k] @ eta[k])
            P = m * vb + np.cross(w, S) + p_rel
            T = (0.5 * m * (vb @ vb) + vb @ (np.cross(w, S) + p_rel)
                 + 0.5 * w @ (IO @ w) + w @ h_rel + Ts)
            H = np.cross(S, vb) + IO @ w + h_rel - np.cross(S / m, P)
            return T + V, C @ P, C @ H, V

        rng = np.random.default_rng(20261116)
        q0 = rng.normal(size=4)
        y0 = np.concatenate([rng.normal(0, 3.0, 3), q0 / np.linalg.norm(q0),
                             [1.5, 0.4, -0.3], rng.normal(0, 0.02, 4),
                             rng.normal(0, 0.3, 4)])
        T_son = 20 * 2 * math.pi / math.sqrt(w1sq.min())
        sol = solve_ivp(rhs, (0, T_son), y0, method='DOP853', rtol=1e-12,
                        atol=1e-14, t_eval=np.linspace(0, T_son, 120))
        E0, P0, H0, _ = korunan(sol.y[:, 0])
        yay = []
        for j in range(sol.t.size):
            Ej, Pj, Hj, Vj = korunan(sol.y[:, j])
            yay.append(Vj)
            assert abs(Ej - E0) / E0 < 1e-10
            assert np.linalg.norm(Pj - P0) / np.linalg.norm(P0) < 1e-10
            assert np.linalg.norm(Hj - H0) / np.linalg.norm(H0) < 1e-10
        # sınama boş değil: yay enerjisi gerçekten alışveriş yapıyor
        assert max(yay) > 3.0 * min(yay) > 0.0

    def test_itkili_bosluk_notr_kararli(self):
        """Aerodinamik yokken (N_α = M_α = M_q = 0, ζ = 0) itki tek başına
        (izleyici kuvvet) büyüme vermez: salınımlı kökler sanal eksende."""
        k4 = _ornek4()
        for tanklar in ([(k4['m1'], k4['xi'], k4['w1sq'], 0.0)],
                        [(k4['m1'], k4['xi'], k4['w1sq'], 0.0),
                         (0.6 * k4['m1'], -1.1, 1.3 * k4['w1sq'], 0.0)]):
            lam = np.linalg.eigvals(sds.dogrusal_model(
                k4['m'], k4['I'], k4['u'], k4['ud'], 0.0, 0.0, 0.0, k4['f'],
                tanklar))
            sal = _salinimli(lam)
            assert sal.size == len(tanklar)
            assert np.max(np.abs(sal.real) / np.abs(sal)) < 1e-12

    # -- Bauer, NASA SP-106 Bölüm 7 (basılı s. 243–246) ---------------------
    @staticmethod
    def _bauer(m, k, F, eps, x_E, a0, a1, m1, x1, w_s, zeta_s):
        """(7.42)–(7.45), g2 = 0; q = [y, φ, y11]; x kıça doğru pozitif."""
        I, g, F2 = m * k * k, F / m, eps * F
        M = np.array([[m, 0.0, m1], [0.0, I, -m1 * x1], [1.0, -x1, 1.0]])
        C = np.array([[0.0, -F2 * a1, 0.0], [0.0, F2 * x_E * a1, 0.0],
                      [0.0, 0.0, 2.0 * zeta_s * w_s]])
        K = np.array([[0.0, -(F + F2 * a0), 0.0],
                      [0.0, F2 * x_E * a0, -g * m1], [0.0, -g, w_s ** 2]])
        Mi = np.linalg.inv(M)
        return np.linalg.eigvals(np.block([[np.zeros((3, 3)), np.eye(3)],
                                           [-Mi @ K, -Mi @ C]]))

    def test_dogrusal_model_bauer_denklemleriyle_ayni_kokler(self):
        """Aerodinamik = tutum denetimi benzeşimi (N_α ↔ F2·a0, M_α ↔
        −x_E·F2·a0, f ↔ F/m, ξ ↔ −x11): u → ∞'da ürün modeli Bauer'in
        denklemleriyle aynı salınımlı kökleri verir; fark 1/u ile küçülür.
        N_α'nın T satırındaki işaretini, M_α'yı ve m1·f·η momentini
        aerodinamik AÇIKKEN birincil kaynağa bağlar."""
        k, m, g = 1.0, 1000.0, 20.0
        F, eps, a0, x_E = m * g, 1.0, 0.8, 1.1
        w_c = math.sqrt(g * x_E * eps * a0 / k ** 2)
        for nu_s in (2.5, 1.1, 0.7):
            for x1 in (-1.2, -0.05, 0.9):
                w_s = nu_s * w_c
                zb = _salinimli(self._bauer(m, k, F, eps, x_E, a0, 0.0,
                                            0.05 * m, x1, w_s, 0.01))
                fark = []
                for u in (1e5, 1e7):
                    zd = _salinimli(np.linalg.eigvals(sds.dogrusal_model(
                        m, m * k * k, u, 0.0, eps * F * a0,
                        -x_E * eps * F * a0, 0.0, g,
                        [(0.05 * m, -x1, w_s ** 2, 0.01)])))
                    fark.append(float(np.max(np.abs(zd - zb) / np.abs(zb))))
                assert fark[1] < 1e-5
                assert fark[0] / fark[1] == pytest.approx(100.0, rel=0.05)

    def test_bauer_tehlike_bolgesi_kenarlari(self):
        """Sönümsüz sıvıda kararlılık sınırı ξ_s eksenini anlık dönme
        merkezinde (ξ1 = −k/x_E; kaynak s. 246) ve askı noktası KM'deyken
        (ξ2 = (1 − μ)·L1/k; kaynaktaki ξ2 = |ξ_d|(1 − μ)/(a0 ν_s²), ε = 1)
        keser; arası kararsızdır."""
        k, m, g, eps, xi_E, a0, zeta_c = 1.0, 1000.0, 20.0, 1.0, 1.1, 3.5, 0.7
        F, x_E = m * g, xi_E * k
        w_c = math.sqrt(g * x_E * eps * a0 / k ** 2)
        a1 = 2.0 * zeta_c * a0 / w_c
        for mu, nu_s in ((0.1, 2.5), (0.02, 1.5)):
            w_s = nu_s * w_c

            def re(x):
                return float(np.max(_salinimli(self._bauer(
                    m, k, F, eps, x_E, a0, a1, mu * m, x * k, w_s, 0.0)).real))
            xi1 = -1.0 / xi_E
            xi2 = (1.0 / xi_E) * (1.0 - mu) / (a0 * nu_s ** 2)
            assert xi2 == pytest.approx((1.0 - mu) * (g / w_s ** 2) / k)
            assert brentq(re, xi1 - 0.2, xi1 + 0.2, xtol=1e-12) == \
                pytest.approx(xi1, abs=1e-9)
            assert brentq(re, xi2 - 0.5 * xi2, xi2 + 0.5 * xi2, xtol=1e-12) \
                == pytest.approx(xi2, rel=1e-6)
            assert re(0.5 * (xi1 + xi2)) > 0.0          # bölge içi kararsız
            assert re(xi1 - 0.1) < 0.0 and re(xi2 + 0.1) < 0.0

    @pytest.mark.slow
    def test_bagimsiz_lagrange_gercek_sarkac(self):
        """Bağımsız formülasyon: atalet çerçevesinde rijit gövde + GERÇEK
        sarkaç (menteşe + çubuk), izleyici itki, BM'de enine akışa karşı
        normal kuvvet; düzgün tırmanış (itki = ağırlık ⇒ u̇ = 0, f = g_a
        tam). Lagrange denklemleri sympy ile türetilir. Dengedeki Jacobian
        kökleri (a) ürün modeli + yerçekimi kinematiği ile 10⁻⁷ bağıl,
        (b) ürünün donmuş modeliyle |ΔRe| ≤ 3·g_a/u·(1/ω) ölçeğinde aynı."""
        import sympy as sp
        t = sp.symbols('t')
        X, Z, th, ps = [sp.Function(a)(t) for a in ('X', 'Z', 'th', 'ps')]
        mR, IR, aR, ga, Th, Fx, Fz, Mp, arm, m1, L1, xh = sp.symbols(
            'mR IR aR ga Th Fx Fz Mp arm m1 L1 xh')
        q = [X, Z, th, ps]
        qd = [sp.diff(x, t) for x in q]
        e1 = sp.Matrix([sp.cos(th), sp.sin(th)])
        rB = sp.Matrix([X, Z])
        rR = rB + aR * e1
        r1 = rB + xh * e1 - L1 * sp.Matrix([sp.cos(th + ps), sp.sin(th + ps)])
        Lg = (sp.Rational(1, 2) * mR * sp.diff(rR, t).dot(sp.diff(rR, t))
              + sp.Rational(1, 2) * IR * sp.diff(th, t) ** 2
              + sp.Rational(1, 2) * m1 * sp.diff(r1, t).dot(sp.diff(r1, t))
              - ga * (mR * rR[0] + m1 * r1[0]))
        rcp = rB - arm * e1
        denk = []
        for j, (qq, qqd) in enumerate(zip(q, qd)):
            Q = Th * e1.dot(sp.diff(rB, qq)) + sp.Matrix([Fx, Fz]).dot(
                sp.diff(rcp, qq)) + (Mp if j == 2 else 0)
            denk.append(sp.diff(sp.diff(Lg, qqd), t) - sp.diff(Lg, qq) - Q)
        qdd = [sp.diff(x, t, 2) for x in q]
        Mm = sp.Matrix([[sp.diff(d, a) for a in qdd] for d in denk])
        bias = sp.Matrix([d.subs({a: 0 for a in qdd}) for d in denk])
        qs, us = sp.symbols('q0:4'), sp.symbols('u0:4')
        yer = {b: d for b, d in zip(qd, us)}
        yer2 = {a: c for a, c in zip(q, qs)}
        arg = [qs, us, mR, IR, aR, ga, Th, Fx, Fz, Mp, arm, m1, L1, xh]
        Mf = sp.lambdify(arg, Mm.subs(yer).subs(yer2), 'numpy')
        bf = sp.lambdify(arg, bias.subs(yer).subs(yer2), 'numpy')

        k4 = _ornek4()
        m, I, u0, Na, Ma, Mq, f = (k4['m'], k4['I'], k4['u'], k4['Na'],
                                   k4['Ma'], k4['Mq'], k4['f'])
        m1v, xiv, L1v = k4['m1'], k4['xi'], k4['L1']
        armv = -Ma / Na
        mRv = m - m1v
        aRv = -m1v * xiv / mRv
        IRv = I - mRv * aRv ** 2 - m1v * xiv ** 2
        assert IRv > 0.0

        def Frhs(y):
            qv, qdv = y[:4], y[4:]
            e1n = np.array([math.cos(qv[2]), math.sin(qv[2])])
            e2n = np.array([-math.sin(qv[2]), math.cos(qv[2])])
            v = qdv[0:2]
            ub, wb = v @ e1n, v @ e2n
            alpha = math.atan2(abs(wb), abs(ub))
            Fn = -Na * (v @ v) / u0 ** 2 * alpha * (1.0 if wb >= 0 else -1.0) * e2n
            a = (qv, qdv, mRv, IRv, aRv, f, m * f, Fn[0], Fn[1], Mq * qdv[2],
                 armv, m1v, L1v, xiv + L1v)
            return np.concatenate([qdv, np.linalg.solve(
                np.asarray(Mf(*a), dtype=float),
                -np.asarray(bf(*a), dtype=float).ravel())])
        y0 = np.zeros(8)
        y0[4] = u0
        J = np.zeros((8, 8))
        for j in range(8):
            h = 1e-3 if j == 4 else 1e-6
            d = np.zeros(8)
            d[j] = h
            J[:, j] = (Frhs(y0 + d) - Frhs(y0 - d)) / (2 * h)
        bag = _salinimli(np.linalg.eigvals(J), 1.0)

        # (a) ürün modeli (u̇ = 0) + yerçekimi kinematiği: durum [α, q, θ, η, η̇]
        w1sq = f / L1v
        M5, K5 = np.zeros((5, 5)), np.zeros((5, 5))
        M5[0, 0], K5[0, 0], K5[0, 1], K5[0, 2] = -m * u0, Na, -m * u0, m * f
        M5[0, 4] = m1v
        M5[1, 1], K5[1, 0], K5[1, 1] = I, Ma, Mq
        M5[1, 4], K5[1, 3] = m1v * xiv, m1v * f
        M5[2, 2], K5[2, 1] = 1.0, 1.0
        M5[3, 3], K5[3, 4] = 1.0, 1.0
        M5[4, 0], M5[4, 1], M5[4, 4] = -u0, xiv, 1.0
        K5[4, 1], K5[4, 2], K5[4, 3] = -u0, f, -w1sq
        gen = _salinimli(np.linalg.eigvals(np.linalg.solve(M5, K5)), 1.0)
        assert bag.size == gen.size == 2
        assert np.max(np.abs(bag - gen) / np.abs(gen)) < 1e-7
        # (b) ürünün donmuş modeli: fark yalnız yerçekimi kinematiği (g/u)
        urun = _salinimli(np.linalg.eigvals(sds.dogrusal_model(
            m, I, u0, 0.0, Na, Ma, Mq, f, [(m1v, xiv, w1sq, 0.0)])), 1.0)
        assert np.max(urun.real) > 0.05            # örnek kararsız (Örnek-4)
        assert np.max(bag.real) > 0.05             # bağımsız benzetim de
        assert np.max(np.abs(bag.imag - urun.imag) / urun.imag) < 2e-3
        assert np.max(np.abs(bag.real - urun.real)) < 3.0 * f / u0 / 6.0


# ===========================================================================
# 2. Tarama mekaniği — analitik katsayılarla (kenar, ζ_min, hüküm)
# ===========================================================================
T_YANMA = 12.0
#: Yapay taban sönümü: birleşme bandının dışındaki zayıf (tehlike bölgesi
#: türü) büyümeyi bastırır; pencerenin iki kenarı da yanma içinde kalır.
ZETA_TABAN = 0.005


def _katsayi(t, kapali_sonra=None, zeta=ZETA_TABAN, m1_carpan=1.0):
    """Örnek-4 (betik v2 §H) + zamana bağlı dinamik basınç ölçeği: gövde
    frekansı çalkantı frekansını süpürür (frekans birleşmesi penceresi)."""
    k4 = _ornek4()
    olcek = 0.55 + 0.085 * t
    acik = kapali_sonra is None or t <= kapali_sonra
    return {'t': t, 'm': k4['m'], 'I': k4['I'], 'x_cg': 2.1, 'u': k4['u'],
            'u_dot': k4['ud'], 'rho': 0.5, 'qbar': 4e4 * olcek, 'mach': 1.2,
            'cn_alpha': 8.0, 'x_cp': 3.6, 'N_alpha': k4['Na'] * olcek,
            'M_alpha': k4['Ma'] * olcek, 'M_q': k4['Mq'] * olcek,
            'f_x': k4['f'], 'dqbar_dt': 0.0, 'altitude_m': 3e3, 'ray': False,
            'prm': [{'acik': acik, 'm1': k4['m1'] * m1_carpan if acik else 0.0,
                     'xi': k4['xi'], 'w1sq': k4['w1sq'], 'c': 0.0,
                     'zeta': zeta, 'L1': k4['L1'], 'doluluk': 0.3, 'h': 0.12,
                     'Gamma1': 1.0, 'x1': 2.0, 'rho': RHO_LOX,
                     'kod': [] if acik else ['SATIR_RET']}]}


def _max_re(t, zeta=ZETA_TABAN, **kw):
    k = _katsayi(t, zeta=zeta, **kw)
    p = k['prm'][0]
    lam = np.linalg.eigvals(sds.dogrusal_model(
        k['m'], k['I'], k['u'], k['u_dot'], k['N_alpha'], k['M_alpha'],
        k['M_q'], k['f_x'], [(p['m1'], p['xi'], p['w1sq'], zeta)]))
    return float(np.max(lam.real))


@pytest.fixture
def sentetik(monkeypatch):
    """Analitik katsayılı tarama: çözücü yalnız tank listesi ve t_burn için."""
    s = SixDOFTrajectory(**_arac(burn_time=T_YANMA),
                         slosh_tanks=[_tank(t_b=T_YANMA)])
    s._r0 = np.zeros(3)
    sol_t = np.concatenate([np.arange(0.0, T_YANMA, 0.05), [T_YANMA]])
    sol_y = np.zeros((17, sol_t.size))

    def kur(**kw):
        monkeypatch.setattr(sds, 'dondurulmus_katsayilar',
                            lambda cozucu, t, y: _katsayi(t, **kw))
        return sds.yanma_taramasi(s, sol_t, sol_y)
    return s, sol_t, kur


class TestTarama:
    def test_pencere_kenarlari_bagimsiz_kok_bulmayla_ayni(self, sentetik):
        _s, sol_t, kur = sentetik
        tar = kur()
        assert len(tar['pencereler']) == 1
        p = tar['pencereler'][0]
        # bağımsız kenarlar: aynı analitik modelde Brent kök bulma
        kaba = np.linspace(0.0, T_YANMA, 2401)
        rr = np.array([_max_re(x) for x in kaba])
        i = np.flatnonzero(np.diff(np.sign(rr)) != 0)
        assert i.size == 2
        e1 = brentq(_max_re, kaba[i[0]], kaba[i[0] + 1], xtol=1e-10)
        e2 = brentq(_max_re, kaba[i[1]], kaba[i[1] + 1], xtol=1e-10)
        assert 1.0 < e1 < e2 < T_YANMA - 1.0
        assert p['t1_kenar'] == p['t2_kenar'] == sds.KENAR_ISARET_DEGISIMI
        assert abs(p['t1'] - e1) <= sds.TARAMA_KENAR_TOL_S
        assert abs(p['t2'] - e2) <= sds.TARAMA_KENAR_TOL_S
        # örnek aralığı (0,05 s) toleransın 50 katı: inceltme gerçekten çalıştı
        assert sds.TARAMA_KENAR_TOL_S < 0.05 / 10
        # en kötü an ve büyüme üssü
        ic = sol_t[(sol_t > e1) & (sol_t < e2)]
        assert p['max_re'] == pytest.approx(max(_max_re(x) for x in ic))
        assert p['max_re'] > 0.05
        assert p['buyume_ussu'] == pytest.approx(
            quad(_max_re, e1, e2, limit=200)[0], rel=1e-2)
        assert p['mod'] in ('calkanti', 'govde')
        assert p['yakinlik_uyarisi'] is True          # frekans birleşmesi
        assert abs(p['yakinlik_orani'] - 1.0) <= sds.YAKINLIK_BANDI
        assert p['sayisal_tutarli'] is True
        assert p['ornek_sayisi'] == ic.size
        # yapay katsayıda q̄ sabit (ölçüt sonsuz): JSON'a null, pencere yazılabilir
        assert p['dondurulmus_olcut_min'] is None
        json.dumps({k: v for k, v in p.items() if k != '_i'}, allow_nan=False)

    def test_pencere_zeta_min_butun_orneklerde_yeter_fazlasi_degil(self, sentetik):
        _s, sol_t, kur = sentetik
        p = kur()['pencereler'][0]
        z = p['zeta_min']
        assert p['zeta_min_dogrulandi'] is True
        assert ZETA_TABAN < z < sds.ZETA_MIN_UST
        assert p['zeta_gercek'] == ZETA_TABAN
        ic = sol_t[(sol_t >= p['t1']) & (sol_t <= p['t2'])]
        # yeter: bütün örnekler bu ortak sönümle kararlı
        assert max(_max_re(x, zeta=z * (1.0 + 1e-9)) for x in ic) < 0.0
        # fazlası değil: %0,1 azı en az bir örneği kararsız bırakır
        assert max(_max_re(x, zeta=z * 0.999) for x in ic) > 0.0
        # tek andaki (en kötü Re) ζ_min pencerenin ζ_min'ini aşamaz
        k = _katsayi(p['t_max_re'])
        pr = k['prm'][0]
        z_an = sds.zeta_min_ara(k['m'], k['I'], k['u'], k['u_dot'],
                                k['N_alpha'], k['M_alpha'], k['M_q'], k['f_x'],
                                [(pr['m1'], pr['xi'], pr['w1sq'], 0.0)])
        assert z_an <= z + 1e-15

    def test_degerlendirme_siniri_kenari_ve_kapsam(self, sentetik):
        """Sıvı pencere içinde tükenirse (çalkantı kapanır) pencerenin sonu
        bir işaret değişimi değil, değerlendirme sınırıdır; kapsam bunu
        aralık ve kodla söyler."""
        _s, sol_t, kur = sentetik
        tam = kur()['pencereler'][0]
        t_kes = 0.5 * (tam['t1'] + tam['t2'])
        tar = kur(kapali_sonra=t_kes)
        p, = tar['pencereler']
        assert p['t1'] == pytest.approx(tam['t1'], abs=1e-12)
        assert p['t2_kenar'] == sds.KENAR_DEGERLENDIRME_SINIRI
        assert p['t2'] == sol_t[sol_t <= t_kes][-1]
        kap = tar['kapsam']
        bos, = kap['hukum_verilemeyen']
        assert bos['sebep'] == sds.TARAMA_KAPALI and bos['kodlar'] == ['SATIR_RET']
        assert bos['t1'] > t_kes and bos['t2'] == pytest.approx(T_YANMA)
        assert kap['hukum_verilen_oran'] == pytest.approx(
            p['t2'] / T_YANMA, abs=0.01)
        assert sum(kap['sinif_sayilari'].values()) == kap['ornek_sayisi']

    def test_sonumle_pencere_kapanir_kararli_hukum(self, sentetik):
        _s, _t, kur = sentetik
        z = kur()['pencereler'][0]['zeta_min']
        tar = kur(zeta=1.05 * z)
        assert tar['pencereler'] == [] and tar['rijit_pencereler'] == []
        out = {'converged': True}
        assert sds._tarama_hukmu(tar, out, 'apogee') == (
            sds.HUKUM_KARARLI, sds.GEREKCE_KARARLI, [])

    def test_notr_kok_gurultusu_pencere_sayilmaz(self, sentetik):
        """Çalkantı kütlesi yok denecek kadar küçük ve sönümsüzken kök
        sanal eksendedir (Re yuvarlama gürültüsü): pencere açılmaz."""
        _s, _t, kur = sentetik
        tar = kur(m1_carpan=1e-13, zeta=0.0)
        re = [o['max_re'] for o in tar['ornekler']]
        assert max(abs(x) for x in re) < 1e-10      # kök gerçekten nötr
        assert tar['pencereler'] == []
        assert tar['kapsam']['sinif_sayilari'][sds.TARAMA_KARARLI] == \
            tar['kapsam']['ornek_sayisi']

    def test_tarama_hukmu_kurallari(self, sentetik):
        _s, _t, kur = sentetik
        tar = kur()
        ok = {'converged': True}
        assert sds._tarama_hukmu(tar, ok, 'apogee') == (
            sds.HUKUM_CALKANTI_KARARSIZ, sds.GEREKCE_PENCERE, [])
        assert sds._tarama_hukmu(tar, {'converged': False}, 'apogee')[:2] == (
            sds.HUKUM_YOK, 'COZUM_YAKINSAMADI')
        # V307/UÇUŞ-GÖVDE (kalem 5; ÇALKANTI-KARARLILIK KARAR 4 → (b)):
        # apojeye varmama YALNIZ 'KARARLI'yı engeller. Pencere bulunduysa
        # hüküm verilir (eskiden HUKUM_YOK / UCUS_APOJEYE_VARMADI idi:
        # kararsızlık aracı takla attıracak kadar büyüdüğünde yazılım
        # susuyordu); pencere yoksa apojeye varmayan uçuşa KARARLI denmez.
        assert sds._tarama_hukmu(tar, ok, 'ground_impact_under_power') == (
            sds.HUKUM_CALKANTI_KARARSIZ, sds.GEREKCE_PENCERE, [])
        sakin = kur(zeta=1.05 * tar['pencereler'][0]['zeta_min'])
        assert sakin['pencereler'] == [] and sakin['rijit_pencereler'] == []
        assert sds._tarama_hukmu(sakin, ok, 'apogee')[0] == sds.HUKUM_KARARLI
        assert sds._tarama_hukmu(sakin, ok, 'ground_impact_under_power') == (
            sds.HUKUM_YOK, 'UCUS_APOJEYE_VARMADI', ['UCUS_APOJEYE_VARMADI'])
        bozuk = dict(tar, pencereler=[dict(tar['pencereler'][0],
                                           sayisal_tutarli=False)])
        assert sds._tarama_hukmu(bozuk, ok, 'apogee')[:2] == (
            sds.HUKUM_YOK, 'SAYISAL_TUTARSIZLIK')
        rijit = dict(tar, pencereler=[], rijit_pencereler=[
            {'t1': 1.0, 't2': 2.0, 'max_re': 0.1}])
        assert sds._tarama_hukmu(rijit, ok, 'apogee')[:2] == (
            sds.HUKUM_RIJIT_KARARSIZ, sds.GEREKCE_RIJIT)
        # çalkantı penceresi rijit kararsızlığın önündedir (K2 önceliği)
        ikisi = dict(tar, rijit_pencereler=rijit['rijit_pencereler'])
        assert sds._tarama_hukmu(ikisi, ok, 'apogee')[0] == \
            sds.HUKUM_CALKANTI_KARARSIZ
        hic = kur(kapali_sonra=-1.0)
        assert sds._tarama_hukmu(hic, ok, 'apogee') == (
            sds.HUKUM_YOK, sds.GEREKCE_DEGERLENDIRILEMEDI, [sds.TARAMA_KAPALI])


# ===========================================================================
# 3. Uçtan uca — gerçek 6-DOF uçuşunda pencere (yapay araç)
# ===========================================================================
def _coz(s, **kw):
    yak = {}
    asil = sds.cozum_ciktilari

    def sar(cozucu, sol_t, sol_y, *a, **k):
        yak['t'], yak['y'] = sol_t, sol_y
        return asil(cozucu, sol_t, sol_y, *a, **k)
    sds.cozum_ciktilari = sar
    try:
        out = s.solve(**kw)
    finally:
        sds.cozum_ciktilari = asil
    return out, yak


#: Tank KM'nin önünde (taban 1,6 m; x_cg 2,0–2,2 m): yanmanın son yarım
#: saniyesinde gövde frekansı çalkantı frekansına iner ve pencere açılır.
PENCERELI_TANK = dict(x=1.6)


@pytest.fixture(scope='module')
def pencereli():
    s = SixDOFTrajectory(**_arac(), slosh_tanks=[_tank(**PENCERELI_TANK)])
    out, yak = _coz(s)
    return s, out, yak


class TestUctanUca:
    def test_dort_an_kacirir_tarama_yakalar(self, pencereli):
        _s, out, _yak = pencereli
        ss = out['slosh_stability']
        # dört anın hiçbiri kararsızlık görmüyor (K2'nin eski genel hükmü
        # KARARLI olurdu) …
        hk = {d['an']: d['hukum'] for d in ss['dort_an']}
        assert sds.HUKUM_CALKANTI_KARARSIZ not in hk.values()
        assert hk['en_buyuk_q'] == hk['yanma_sonu'] == sds.HUKUM_KARARLI
        assert not any(d['pencere_icinde'] for d in ss['dort_an'])
        # … ama yanma içinde pencere var ve genel hüküm ondan
        p, = ss['pencereler']
        assert ss['genel_hukum'] == ss['hukum'] == sds.HUKUM_CALKANTI_KARARSIZ
        assert ss['gerekce_kodu'] == sds.GEREKCE_PENCERE and ss['sebep'] == []
        assert 0.0 < p['t1'] < p['t2'] < 12.0
        t_q = [d['t'] for d in ss['dort_an'] if d['an'] == 'en_buyuk_q'][0]
        assert p['t2'] < t_q
        assert p['max_re'] > 0.1 and p['tank_id'] == 'oksitleyici'
        assert p['zeta_min'] > p['zeta_gercek'] > 0.0
        assert p['buyume_ussu'] > 0.0
        # uçuşun kendi (rijit) hükmü değişmedi: iki rozet yok
        assert out['flight_verdict']['stability'] == 'stable'

    def test_sozlesme_alanlari_ve_turleri(self, pencereli):
        _s, out, yak = pencereli
        ss = out['slosh_stability']
        for alan in ('genel_hukum', 'gerekce_kodu', 'sebep', 'pencereler',
                     'rijit_pencereler', 'dort_an', 'dogrusal_sinir',
                     'bafl_onerisi', 'beyanlar', 'tarama', 'hukum', 'anlar',
                     'tanklar', 'kapsam_disi', 'esikler', 'basis'):
            assert alan in ss, alan
        assert ss['genel_hukum'] in sds.HUKUMLER
        assert ss['gerekce_kodu'] in sds.GEREKCE_KODLARI
        assert [d['an'] for d in ss['dort_an']] == list(sds.ANLAR)
        for d in ss['dort_an']:
            assert set(d) == {'an', 't', 'hukum', 'sebep', 'max_re',
                              'zeta_min', 'pencere_icinde'}
        p = ss['pencereler'][0]
        for alan in ('t1', 't2', 't1_kenar', 't2_kenar', 'max_re', 't_max_re',
                     'mod', 'tank_id', 'yakinlik_orani', 'yakinlik_uyarisi',
                     'zeta_min', 't_zeta_min', 'zeta_min_dogrulandi',
                     'zeta_gercek', 'buyume_ussu', 'ornek_sayisi',
                     'tank_araligi', 'beyanlar', 'sayisal_tutarli'):
            assert alan in p, alan
        assert '_i' not in p
        d = ss['dogrusal_sinir']
        assert set(d) >= {'asildi', 'max_eta_R', 'sinir', 'kaynak',
                          't_ilk_asim_s', 'tanklar', 'etkilenen_alanlar'}
        assert d['sinir'] == stb.GENLIK_DOGRUSAL_SINIR_ORANI
        assert 'Dodge' in d['kaynak'] and '33' in d['kaynak']
        seri = ss['tarama']['seri']
        n = ss['tarama']['kapsam']['ornek_sayisi']
        assert len(seri['t']) == len(seri['sinif']) == len(seri['max_re']) == n
        assert set(seri['sinif']) <= set(sds.TARAMA_SINIFLARI)
        for s_, r in zip(seri['sinif'], seri['max_re']):
            assert (r is None) == (s_ in (sds.TARAMA_RAYDA, sds.TARAMA_GECERSIZ,
                                          sds.TARAMA_KAPALI))
        for kod in ss['beyanlar']:
            assert kod in sds.K2_KODLARI or kod in stb.SEBEP_KODLARI
        # sözleşme (dört anın ayrıntısı dışında) doğrudan JSON'a yazılabilir
        json.dumps({k: v for k, v in ss.items() if k != 'anlar'},
                   allow_nan=False)
        assert out['slosh_linear_valid'].shape == yak['t'].shape
        assert out['slosh_params_t']['rho_kg_m3'].shape == \
            out['slosh_params_t']['doluluk'].shape

    def test_tarama_ayri_cagrida_ayni_ve_adim_inceltmeye_dayanikli(self, pencereli):
        s, out, yak = pencereli
        p = out['slosh_stability']['pencereler'][0]
        # ürün yolu RHS çağrısını zaman alanı çıktısıyla paylaşır; ayrı çağrı
        # aynı pencereyi BİT-AYNI vermeli
        ayri, = sds.yanma_taramasi(s, yak['t'], yak['y'])['pencereler']
        for alan in ('t1', 't2', 'max_re', 't_max_re', 'zeta_min',
                     'buyume_ussu'):
            assert ayri[alan] == p[alan], alan
        # entegratör adımı 5 kat inceltilince (başka bir çözüm, başka
        # örnekler) kenarlar örnek aralığı mertebesinde aynı kalır
        s2 = SixDOFTrajectory(**_arac(), slosh_tanks=[_tank(**PENCERELI_TANK)])
        ince = s2.solve(max_step=0.02)['slosh_stability']
        q, = ince['pencereler']
        assert abs(q['t1'] - p['t1']) < 0.02 and abs(q['t2'] - p['t2']) < 0.02
        assert q['max_re'] == pytest.approx(p['max_re'], rel=0.02)
        assert q['zeta_min'] == pytest.approx(p['zeta_min'], rel=0.02)
        assert ince['tarama']['kapsam']['ornek_sayisi'] > \
            out['slosh_stability']['tarama']['kapsam']['ornek_sayisi']

    def test_bafl_onerisi_pencereyi_kapatir(self, pencereli):
        s, out, _yak = pencereli
        ss = out['slosh_stability']
        b = ss['bafl_onerisi']
        p = ss['pencereler'][0]
        assert b['zeta_hedef'] == p['zeta_min']
        assert b['aralik_orani'] == sa.BAFL_DIZISI_ARALIK_ORANI
        for ad, hedef in (('nominal', p['zeta_min']),
                          ('tutucu', p['zeta_min'] * b['bant_carpani'])):
            duzey = b[ad]
            assert duzey['zeta_tasarim'] == pytest.approx(hedef)
            t, = duzey['tanklar']
            o = t['oneri']
            assert t['tank_id'] == 'oksitleyici' and 0.0 < o['width_ratio'] < 1.0
            assert o['halka_sayisi'] == len(o['halka_yukseklikleri_m']) >= 1
            # halkalar pencerede yüzeyin gezdiği aralığı kaplar: her yüzey
            # konumunun altında en çok bir aralık derinde halka var
            R = 0.09
            h_ust, h_alt = o['yuzey_araligi_m']
            assert h_ust == p['tank_araligi']['oksitleyici']['h_m'][0]
            for h in np.linspace(h_alt, h_ust, 50):
                derin = [h - z for z in o['halka_yukseklikleri_m'] if z <= h]
                if o['taban_altina_dusen_halka'] == 0:
                    assert derin and min(derin) <= o['spacing_m'] + 1e-12
                    assert sa.halka_bafl_dizisi_sonumu(
                        R, h, o['halka_yukseklikleri_m'], o['width_ratio'],
                        b['genlik_orani']) >= hedef * (1.0 - 1e-12)
            for bant in ('nominal', 'alt_bant'):
                y = duzey['yeniden_tarama'][bant]
                assert y['pencere_kapandi'] == (y['kararsiz_ornek_sayisi'] == 0)
                assert (y['kalan_pencereler'] == []) == y['pencere_kapandi']
        # nominal tasarım nominal sönümle, tutucu tasarım alt bantta kapatır
        assert b['pencere_kapaniyor'] is True
        assert b['pencere_kapaniyor_alt_bantta'] is True
        assert b['nominal']['yeniden_tarama']['nominal']['max_re'] < 0.0

    def test_bafl_sonumuyle_zaman_alani_yeniden_kosusu(self, pencereli):
        """Bafl önerisiyle YENİDEN KOŞU: hedef sönüm tanka ek sönüm olarak
        verilince bağlaşık 6-DOF'un taraması pencere bulmaz; hedefin yarısı
        yetmez (öneri gereksiz büyük değil)."""
        _s, out, _yak = pencereli
        z = out['slosh_stability']['bafl_onerisi']['zeta_hedef']
        for carpan, beklenen in ((1.02, sds.HUKUM_KARARLI),
                                 (0.5, sds.HUKUM_CALKANTI_KARARSIZ)):
            s2 = SixDOFTrajectory(**_arac(), slosh_tanks=[
                _tank(zeta_ek=carpan * z, **PENCERELI_TANK)])
            ss = s2.solve()['slosh_stability']
            assert ss['genel_hukum'] == beklenen
            assert (ss['bafl_onerisi'] is None) == (beklenen == sds.HUKUM_KARARLI)

    def test_pencere_yoksa_kararli_ve_oneri_yok(self):
        out = SixDOFTrajectory(**_arac(), slosh_tanks=[_tank()]).solve()
        ss = out['slosh_stability']
        assert ss['genel_hukum'] == sds.HUKUM_KARARLI
        assert ss['gerekce_kodu'] == sds.GEREKCE_KARARLI
        assert ss['pencereler'] == [] and ss['bafl_onerisi'] is None
        assert ss['dogrusal_sinir']['asildi'] is False
        assert bool(np.all(out['slosh_linear_valid']))
        # yanmanın başı (ray + düşük hız) değerlendirilemez: kapsam söyler
        kap = ss['tarama']['kapsam']
        assert 0.5 < kap['hukum_verilen_oran'] < 1.0
        assert [x['sebep'] for x in kap['hukum_verilemeyen']][:2] == [
            sds.TARAMA_RAYDA, sds.TARAMA_GECERSIZ]
        assert 'TARAMA_KISMI_KAPSAM' in ss['beyanlar']

    def test_uygulanmaz_sozlesmesi(self):
        u = sds.uygulanmaz_ciktisi('TANK_YOK')
        assert u['genel_hukum'] == u['hukum'] == sds.HUKUM_UYGULANMAZ
        assert u['gerekce_kodu'] == 'TANK_YOK'
        assert u['pencereler'] == u['dort_an'] == u['beyanlar'] == []
        assert u['dogrusal_sinir'] is None and u['bafl_onerisi'] is None


# ===========================================================================
# 4. Doğrusal geçerlilik sınırı
# ===========================================================================
class TestDogrusalSinir:
    def test_asim_sonrasi_isaretli(self):
        t = np.linspace(0.0, 10.0, 101)
        ceper = np.vstack([0.03 * t, np.full(t.size, np.nan)])
        ceper[1, 20:60] = 0.05
        ozet, maske = sds.dogrusal_sinir_ozeti(t, ceper, ['oksitleyici', 'yakit'])
        sinir = stb.GENLIK_DOGRUSAL_SINIR_ORANI
        i = int(np.flatnonzero(ceper[0] > sinir)[0])
        assert ozet['asildi'] is True and ozet['sinir'] == sinir
        assert ozet['t_ilk_asim_s'] == t[i]
        assert ozet['tank_id_ilk_asim'] == 'oksitleyici'
        assert ozet['max_eta_R'] == pytest.approx(0.3)
        assert ozet['max_eta_R_gecerlilik'] == sds.DOGRUSAL_GECERLILIK_DISI
        assert ozet['asim_sonrasi_kod'] == sds.DOGRUSAL_GECERLILIK_DISI
        # geçerli bölgedeki en büyük genlik sınırı aşmaz; maske aşımdan
        # sonra (öbür tank dahil, bütün örneklerde) kapalıdır
        assert ozet['max_eta_R_sinir_oncesi'] <= sinir
        assert maske[:i].all() and not maske[i:].any()
        assert set(ozet['etkilenen_alanlar']) >= {
            'slosh_eta', 'slosh_force_body', 'slosh_moment_body',
            'slosh_wall_amplitude_ratio', 'apogee'}
        yak = [x for x in ozet['tanklar'] if x['tank_id'] == 'yakit'][0]
        assert yak['asildi'] is False and yak['max_eta_R'] == pytest.approx(0.05)

    def test_asim_yoksa_her_sey_gecerli(self):
        t = np.linspace(0.0, 5.0, 11)
        ozet, maske = sds.dogrusal_sinir_ozeti(
            t, np.full((1, t.size), 0.19), ['n2o'])
        assert ozet['asildi'] is False and maske.all()
        assert ozet['max_eta_R_gecerlilik'] == 'GECERLI'
        assert ozet['t_ilk_asim_s'] is None and ozet['etkilenen_alanlar'] == []
        assert ozet['max_eta_R'] == ozet['max_eta_R_sinir_oncesi'] == \
            pytest.approx(0.19)

    def test_ucustaki_asim_beyana_ve_maskeye_gecer(self, monkeypatch):
        """Gerçek koşuda sınır aşılırsa (burada sınır düşürülerek) çıktı
        bunu ADIYLA söyler ve maske aşım anından sonra kapalıdır."""
        taban = SixDOFTrajectory(**_arac(), slosh_tanks=[_tank()]).solve()
        oran0 = taban['slosh_wall_amplitude_ratio'][0]
        # sınır: uçuşun ortasında aşılan bir düzey (ilk 2 s'nin en büyüğü ile
        # bütün uçuşun en büyüğü arasında bir yer yoksa rampadaki statik eğim
        # en büyüktür; o zaman aşım t = 0'dadır ve geçerli bölge boştur)
        sinir = 0.5 * float(np.nanmax(oran0))
        monkeypatch.setattr(stb, 'GENLIK_DOGRUSAL_SINIR_ORANI', sinir)
        out = SixDOFTrajectory(**_arac(), slosh_tanks=[_tank()]).solve()
        d = out['slosh_stability']['dogrusal_sinir']
        assert d['asildi'] is True and d['sinir'] == sinir
        assert 'GENLIK_DOGRUSAL_SINIR_DISI' in out['slosh_stability']['beyanlar']
        gec = out['slosh_linear_valid']
        t = out['time']
        oran = out['slosh_wall_amplitude_ratio'][0]
        i = int(np.flatnonzero(np.nan_to_num(oran) > sinir)[0])
        assert d['t_ilk_asim_s'] == t[i]
        assert gec[:i].all() and not gec[i:].any()
        assert d['max_eta_R'] == pytest.approx(float(np.nanmax(oran)))
        assert d['max_eta_R_gecerlilik'] == sds.DOGRUSAL_GECERLILIK_DISI
        if i:
            assert d['max_eta_R_sinir_oncesi'] <= sinir
        else:
            assert d['max_eta_R_sinir_oncesi'] is None
        assert 'GENLIK_DOGRUSAL_SINIR_DISI' in \
            out['slosh_stability']['tanklar'][0]['kodlar']


# ===========================================================================
# 5. Halka bafl dizisi (slosh_analysis)
# ===========================================================================
class TestBaflDizisi:
    def test_aralik_en_az_halka_alani(self):
        """Hedefi en kötü konumda (en yakın batık halka s derinde) sağlayan
        kapanma oranı C1(σ) için birim boya düşen alan C1/σ, seçilen
        aralıkta en küçüktür (Miles: γ ∝ e^(−4,6σ) C1^(3/2))."""
        hedef, eta = 0.03, 0.05
        d = sa.halka_bafl_dizisi(hedef, eta)
        s0 = d['spacing_ratio']
        assert s0 == sa.BAFL_DIZISI_ARALIK_ORANI == pytest.approx(3.0 / 9.2)

        def alan(sig):
            lo, hi = 1e-6, 1.0 - 1e-12       # C1 ∈ (0, 1): γ(σ; C1) = hedef
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                w = 1.0 - math.sqrt(1.0 - mid)
                if sa.halka_bafl_sonumu(w, sig, eta)['gamma'] >= hedef:
                    hi = mid
                else:
                    lo = mid
            return hi / sig
        assert alan(s0) < alan(0.8 * s0) and alan(s0) < alan(1.25 * s0)
        # genişlik tam hedefi verir
        assert sa.halka_bafl_sonumu(d['width_ratio'], s0, eta)['gamma'] == \
            pytest.approx(hedef, rel=1e-12)
        assert d['blocked_area_ratio'] == pytest.approx(
            1.0 - (1.0 - d['width_ratio']) ** 2)

    def test_dizi_her_yuzey_konumunda_hedefi_saglar(self):
        R, hedef = 0.24, 0.05
        d = sa.halka_bafl_dizisi(hedef)
        s = d['spacing_ratio'] * R
        zs = [1.0 - j * s for j in range(1, 9)]
        en_az = min(sa.halka_bafl_dizisi_sonumu(R, h, zs, d['width_ratio'])
                    for h in np.linspace(zs[-1] + s, 1.0, 400))
        assert hedef <= en_az < 1.6 * hedef
        # halkasız bölgede (en alt halkanın altı) sönüm yok
        assert sa.halka_bafl_dizisi_sonumu(R, zs[-1] - 0.2 * R, zs,
                                           d['width_ratio']) == 0.0

    def test_saglanamayan_hedef_ve_girdi_kapisi(self):
        d = sa.halka_bafl_dizisi(0.5)
        assert d['achievable'] is False and d['width_ratio'] is None
        for kotu in (0.0, -0.1, float('nan')):
            with pytest.raises(sa.SloshGirdiHatasi):
                sa.halka_bafl_dizisi(kotu)
        with pytest.raises(sa.SloshGirdiHatasi):
            sa.halka_bafl_dizisi(0.02, amplitude_ratio=0.0)


# ===========================================================================
# 6. Tank ρ(t) arayüzü (K2) ve motorun yoğunluk serisi (K4)
# ===========================================================================
class TestYogunlukSerisi:
    def _cozucu(self, rho_t):
        tank = _tank()
        if rho_t is not None:
            tank['rho_t'] = rho_t
        s = SixDOFTrajectory(**_arac(), slosh_tanks=[tank])
        s._r0 = np.zeros(3)
        return s

    def test_doluluk_hacimden(self):
        """ρ(t) verilince doluluk = m(t)/(ρ(t)·V_iç); m1 kütleden."""
        seri = {'t': [0.0, 6.0, 12.0],
                'rho': [RHO_LOX, 1.10 * RHO_LOX, 1.20 * RHO_LOX]}
        a, b = self._cozucu(None), self._cozucu(seri)
        for t in (0.0, 3.0, 6.0, 9.0):
            pa, = a._slosh.parametreler(t, 2.1, 30.0)
            pb, = b._slosh.parametreler(t, 2.1, 30.0)
            rho = float(np.interp(t, seri['t'], seri['rho']))
            assert pb['rho'] == rho and pa['rho'] == RHO_LOX
            assert pb['m_sivi'] == pa['m_sivi']
            assert pb['doluluk'] == pytest.approx(pa['doluluk'] * RHO_LOX / rho,
                                                  rel=1e-14)
            V = b._slosh.tanklar[0]['V_ic']
            assert pb['doluluk'] == pytest.approx(pb['m_sivi'] / (rho * V),
                                                  rel=1e-14)
        assert 'TANK_YOGUNLUGU_SERIDEN' in b._slosh.tanklar[0]['beyan']
        assert 'TANK_YOGUNLUGU_SERIDEN' not in a._slosh.tanklar[0]['beyan']

    def test_sabit_seri_bit_ayni_ve_seri_disi_kapanir(self):
        a = self._cozucu(None)
        b = self._cozucu({'t': [0.0, 12.0], 'rho': [RHO_LOX, RHO_LOX]})
        rng = np.random.default_rng(7)
        for _ in range(10):
            y = np.concatenate([[0.0, 0.0, 800.0], rng.normal(size=3) * 80.0
                                + [0, 0, 200.0], [1.0, 0.0, 0.0, 0.0],
                                rng.normal(size=3) * 0.2,
                                rng.normal(size=4) * 0.01])
            t = float(rng.uniform(1.0, 11.0))
            assert np.array_equal(a._derivatives(t, y), b._derivatives(t, y))
        c = self._cozucu({'t': [0.0, 5.0], 'rho': [RHO_LOX, RHO_LOX]})
        p, = c._slosh.parametreler(6.0, 2.1, 30.0)
        assert p['acik'] is False and p['kod'] == ['TANK_YOGUNLUK_SERISI_DISI']
        assert sds.K2_KODLARI['TANK_YOGUNLUK_SERISI_DISI'][0] == \
            sds.SINIF_KAPANMA

    @pytest.mark.parametrize('rho_t, kod', [
        ([1.0, 2.0], 'TIP'),
        ({'t': [0.0], 'rho': [1000.0], 'x': 1}, 'TIP'),
        ({'t': [0.0, 1.0], 'rho': [1000.0]}, 'BOYUT'),
        ({'t': [0.0, 1.0], 'rho': [1000.0, 0.0]}, 'ARALIK'),
        ({'t': [0.0, 1.0], 'rho': [1000.0, float('nan')]}, 'SAYI_DEGIL'),
        ({'t': [1.0, 1.0], 'rho': [1000.0, 1000.0]}, 'SIRA'),
        ({'t': [-1.0, 1.0], 'rho': [1000.0, 1000.0]}, 'ARALIK'),
    ])
    def test_adli_ret(self, rho_t, kod):
        with pytest.raises(sds.SloshBaglamaHatasi) as e:
            self._cozucu(rho_t)
        assert e.value.kod == kod and 'rho_t' in e.value.alan

    def test_motor_yogunluk_serisi_birim(self):
        """``tank_liquid_density_series``: adım sınırlarında ρ_l(T); t = 0
        ateşleme sıcaklığı; sıvı hâli olmayan sıcaklıkta None."""
        from hrma.analysis.tank_blowdown import N2OSaturation
        from hrma.engines import hybrid_rocket_engine as hre
        T = [290.0, 285.0, 280.0]
        gecmis = [{'T': x, 'm_liquid': 1.0} for x in T]
        seri = hre.tank_liquid_density_series(gecmis, 293.15)
        ref = N2OSaturation()
        assert seri == [float(ref.rho_l(x)) for x in [293.15] + T]
        assert all(b > a for a, b in zip(seri, seri[1:]))   # soğudukça yoğun
        assert hre.tank_liquid_density_series([], 293.15) is None
        assert hre.tank_liquid_density_series(gecmis, None) is None
        kritik_ustu = hre.tank_liquid_density_series(
            [{'T': 400.0, 'm_liquid': 0.0}], 293.15)
        assert kritik_ustu[0] == seri[0] and kritik_ustu[1] is None


def _hibrit_sonuc():
    from tests.test_slosh_motor_baglanti import _coz as motor_coz
    return motor_coz('hybrid')


@pytest.fixture(scope='module')
def hibrit():
    return _hibrit_sonuc()


@pytest.mark.slow
class TestHibritYogunlugu:
    """Örnek hibrit motor (N₂O boşalma): motor ρ_l(T) serisini kendi tank
    çözümünden yayımlar; bağlantı doluluğu hacimden kurar."""

    def _bagla(self, res):
        from hrma.analysis import flight_vehicle as fv
        arac = fv.normalize('hybrid', res)
        L = 0.5 + arac['airframe_resolved']['length_behind_nose_m']
        return arac, L, smb.slosh_tanklari('hybrid', res, arac_duzeni={
            'ardisik': {'sira': ['n2o']}, 'govde_boyu_m': L})

    def test_motor_seriyi_yayimliyor(self, hibrit):
        from hrma.analysis.tank_blowdown import N2OSaturation
        eng = hibrit['motor']
        inv = eng['tank_blowdown']['oxidizer_inventory']
        rho, m = inv['liquid_density_kg_m3'], inv['liquid_mass_kg']
        assert len(rho) == len(m) == len(inv['liquid_mass_time_s'])
        # t = 0: motorun ateşleme yoğunluğu (tek büyüklük, tek sayı)
        assert rho[0] == eng['oxidizer_tank_slosh']['liquid_density_kg_m3']
        # tank soğur, sıvı yoğunlaşır; uçlar motorun sıcaklıklarının ρ_l'si
        assert all(b >= a for a, b in zip(rho, rho[1:]))
        T = eng['tank_blowdown']['tank_temperature_K']
        ref = N2OSaturation()
        assert rho[0] == pytest.approx(float(ref.rho_l(T[0])), rel=1e-12)
        assert rho[-1] > float(ref.rho_l(T[-1])) * (1.0 - 1e-3)
        assert rho[-1] / rho[0] > 1.10                 # ölçülen +%15
        assert 'liquid_density_kg_m3' in inv['liquid_density_basis']

    def test_baglanti_dolulugu_hacimden_kurar(self, hibrit):
        arac, L, b = self._bagla(hibrit)
        st, = b['slosh_tanks']
        inv = hibrit['motor']['tank_blowdown']['oxidizer_inventory']
        assert st['rho_t'] == {'t': inv['liquid_mass_time_s'],
                               'rho': inv['liquid_density_kg_m3']}
        rapor, = b['tanklar']
        assert 'YOGUNLUK_BOSALMA_COZUMU' in rapor['beyan']
        assert 'YOGUNLUK_SABIT' not in rapor['beyan']
        assert rapor['rho_t'] == st['rho_t'] and rapor['rho_seri_kaynagi']
        from tests.test_slosh_motor_baglanti import _cozucu
        degisken = _cozucu(arac, L, [st])
        sabit = _cozucu(arac, L, [{k: v for k, v in st.items()
                                   if k != 'rho_t'}])
        V = st['tablo'].geometri['V_ic_m3']
        rho0 = st['tablo'].sivi['rho_kg_m3']
        fazla = []
        for kesir in (0.25, 0.5, 0.75, 0.9):
            t = kesir * inv['liquid_mass_time_s'][-1]
            pd, = degisken._slosh.parametreler(t, 1.0, 30.0)
            ps, = sabit._slosh.parametreler(t, 1.0, 30.0)
            m = float(np.interp(t, inv['liquid_mass_time_s'],
                                inv['liquid_mass_kg']))
            rho = float(np.interp(t, inv['liquid_mass_time_s'],
                                  inv['liquid_density_kg_m3']))
            assert pd['doluluk'] == pytest.approx(m / (rho * V), rel=1e-12)
            assert ps['doluluk'] == pytest.approx(m / (rho0 * V), rel=1e-12)
            fazla.append(ps['doluluk'] / pd['doluluk'] - 1.0)
        # sabit yoğunluk doluluğu yanma boyunca giderek FAZLA verir
        assert all(b > a for a, b in zip(fazla, fazla[1:]))
        assert 0.03 < fazla[0] < 0.06 and 0.10 < fazla[-1] < 0.16

    def test_seri_yoksa_sabit_tutarsizsa_baglanmaz(self, hibrit):
        import copy
        yok = copy.deepcopy(hibrit)
        del yok['motor']['tank_blowdown']['oxidizer_inventory'][
            'liquid_density_kg_m3']
        _a, _L, b = self._bagla(yok)
        assert b['durum'] == smb.DURUM_BAGLANDI
        assert 'rho_t' not in b['slosh_tanks'][0]
        assert 'YOGUNLUK_SABIT' in b['tanklar'][0]['beyan']
        for boz in (lambda r: r[:-1], lambda r: [r[0] * 1.01] + r[1:],
                    lambda r: [None] + r[1:], lambda r: 'x'):
            kotu = copy.deepcopy(hibrit)
            inv = kotu['motor']['tank_blowdown']['oxidizer_inventory']
            inv['liquid_density_kg_m3'] = boz(inv['liquid_density_kg_m3'])
            _a, _L, b = self._bagla(kotu)
            assert b['durum'] == smb.DURUM_BAGLANMADI
            assert b['sebep'] == ['YOGUNLUK_SERISI_TUTARSIZ']
            assert smb.KODLAR['YOGUNLUK_SERISI_TUTARSIZ'][0] == \
                smb.SINIF_BAGLANMADI
        # sıvı hâli olmayan kuyruk (None) seriden düşer, tank bağlı kalır
        kuyruk = copy.deepcopy(hibrit)
        inv = kuyruk['motor']['tank_blowdown']['oxidizer_inventory']
        inv['liquid_density_kg_m3'][-3:] = [None, None, None]
        _a, _L, b = self._bagla(kuyruk)
        assert b['durum'] == smb.DURUM_BAGLANDI
        assert len(b['slosh_tanks'][0]['rho_t']['t']) == \
            len(inv['liquid_mass_time_s']) - 3
