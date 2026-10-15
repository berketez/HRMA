"""ÖH Dalga-24 / termo-ucus aşama-1 bekçileri — TEK KALEM: OH-D23-17.

Kalem: ``_fin_compressibility_factor`` süpersonik dalı GEÇERSİZDİ.
``k(M) = (4/2π)/√(M²−1)`` İNCE PROFİL 2-B oranıdır; çarpıldığı Barrowman
kanat terimi ise Niskanen eq. (3.40)'ın β = 1 hâli olduğu için DÜŞÜK
EN-BOY düzeltmesini ZATEN taşır → en-boy kaybı İKİ KEZ sayılıyordu.

ÖLÇÜLDÜ (taban 88a29d3 → bu ağaç; ``docs/scofield/raw/OH/D24/termo-ucus/
a1/once.json`` → ``sonra.json``, kontrollü A/B ``ab.json``):

    k(2,5)            0,27784  →  0,91979
    k(2,9)            0,23387  →  0,77421
    statik marj M=2,5 +0,0395  →  +4,2058 kalibre
    statik marj M=2,9 −0,6901  →  +3,7390 kalibre  (ÖNCE KARARSIZ)
    B aracı (bağlıyken)  'tumble_detected', apoje YOK  →  'apogee', 14197,87 m

Her bekçi TERS-MUTASYONLA doğrulandı (onarım geçici geri alınınca KIRMIZI):
``docs/scofield/raw/OH/D24/termo-ucus/a1/mutasyon.json``.
Sembolik türetim + boyut analizi: ``.../a1/turetim.py`` → ``turetim.json``.

ÖH D25 / OH-D24-03 NOTU: bu dosyadaki ÜÇ bekçi (kapalı biçim, çift-sayım
oranı, statik marj sayıları) süpersonik dalı UÇ MACH KONİSİ KAYBI OLMADAN
kilitliyordu; D25'te o kayıp + narin-kanat kolu yazıldı ve üçü de
güncellendi. Gerekçe ve önce/sonra sayıları:
``docs/scofield/raw/OH/D25/termo-ucus/a1/rapor.md``.
"""
import ast
import contextlib
import io
import math
import os

import numpy as np
import pytest

from hrma.analysis import six_dof_trajectory as S
from hrma.analysis.six_dof_trajectory import (
    _FIN_M_SUB, _FIN_M_SUP, BarrowmanAero, SixDOFTrajectory,
    _fin_compressibility_factor)

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _aero_A():
    """D23 raporunun 'marj 4,41 → 0,04' aracı."""
    return BarrowmanAero(body_diameter=0.15, nose_length=0.5,
                         body_length=3.0, nose_type='ogive', fin_count=4,
                         fin_root_chord=0.30, fin_tip_chord=0.15,
                         fin_span=0.15, fin_sweep=0.10)


def _aero_B():
    """D23 raporunun M≈2,91'de TAKLA atan aracı (tests/test_launch_site)."""
    return BarrowmanAero(body_diameter=0.15, nose_length=0.5,
                         body_length=3.0, fin_count=4, fin_root_chord=0.22,
                         fin_tip_chord=0.1, fin_span=0.13, fin_sweep=0.08)


def _kos_B():
    s = SixDOFTrajectory(aero=_aero_B(), dry_mass=25.0, propellant_mass=18.0,
                         thrust=6500.0, burn_time=7.5,
                         launch_elevation_deg=84.0, launch_azimuth_deg=90.0,
                         wind_speed=6.0, wind_direction_deg=270.0)
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return s.solve(t_max=400.0)


def _eski_2B(mach, *a, **kw):
    """Taban 88a29d3'ün çarpanı — geometriyi GÖRMEZ (kusurun kendisi)."""
    m = max(float(mach), 0.0)
    if m <= 0.0:
        return 1.0
    if m < 0.8:
        return 1.0 / math.sqrt(1.0 - m * m)
    k_sub = 1.0 / math.sqrt(1.0 - 0.8 ** 2)
    k_sup = (4.0 / (2.0 * math.pi)) / math.sqrt(1.2 ** 2 - 1.0)
    if m <= 1.2:
        return k_sub + (m - 0.8) / (1.2 - 0.8) * (k_sup - k_sub)
    return (4.0 / (2.0 * math.pi)) / math.sqrt(m * m - 1.0)


# =====================================================================
# 1) Çarpanın KENDİSİ — sonlu açıklık, 2-B oranı DEĞİL
# =====================================================================
class TestCarpanSonluAcikliktir:

    def test_kapali_bicim_eq340_ve_ackeret(self):
        """k, eq. (3.40) ve 4/β'nın ORANIDIR (bağımsız kapalı biçim)."""
        a = _aero_A()
        ar, cg = a._fin_aspect, a._fin_cos_gamma
        q = ar / cg
        d0 = 1.0 + math.sqrt(1.0 + q * q)
        for M in (0.0, 0.3, 0.5, 0.85, 0.9):
            beklenen = d0 / (1.0 + math.sqrt(1.0 + (1.0 - M * M) * q * q))
            assert _fin_compressibility_factor(M, ar, cg) == pytest.approx(
                beklenen, rel=1e-12), f'altsonik dal M={M}'
        # GÜNCELLENDİ (ÖH D25 / OH-D24-03): süpersonik dal artık İKİ
        # KOLLUDUR — uç Mach konisi kaybı (β·AR_f ≥ 1) ve narin kanat
        # (β·AR_f < 1). Eski tek kollu beklenti UÇ KAYBINI YOK SAYIYORDU;
        # gerekçe + türetim docs/scofield/raw/OH/D25/termo-ucus/a1/.
        for M in (1.5, 2.0, 2.5, 2.9, 5.0):
            beta = math.sqrt(M * M - 1.0)
            if beta * ar >= 1.0:
                beklenen = (2.0 * d0 * (1.0 - 1.0 / (4.0 * beta * ar))
                            / (math.pi * ar * beta))
            else:
                beklenen = d0 / 2.0
            assert _fin_compressibility_factor(M, ar, cg) == pytest.approx(
                beklenen, rel=1e-12), f'süpersonik dal M={M}'

    def test_supersonik_dal_2B_oranindan_D0_bolu_AR_kadar_buyuk(self):
        """ÇİFT SAYIM İSPATI: yeni/eski = D₀/AR_f (sembolik T5).

        Bu bekçi kalemin ÖZÜDÜR: eski dal, yenisinin AR_f → ∞ (2-B)
        limitidir; sonlu en-boyda aradaki fark tam olarak Barrowman
        teriminin İÇİNDE zaten bulunan en-boy düzeltmesidir.
        """
        a = _aero_A()
        ar, cg = a._fin_aspect, a._fin_cos_gamma
        d0 = 1.0 + math.sqrt(1.0 + (ar / cg) ** 2)
        # GÜNCELLENDİ (ÖH D25 / OH-D24-03): oran artık uç Mach konisi
        # kayıp çarpanını da taşır. Çift-sayım ispatının ÖZÜ değişmedi —
        # D₀/AR_f çarpanı hâlâ oradadır, üstüne (1 − 1/(4βAR_f)) gelir.
        for M in (2.5, 2.9, 4.0):
            beta = math.sqrt(M * M - 1.0)
            assert beta * ar >= 1.0, f'M={M} uç-kaybı kolunda olmalı'
            uc = 1.0 - 1.0 / (4.0 * beta * ar)
            oran = _fin_compressibility_factor(M, ar, cg) / _eski_2B(M)
            assert oran == pytest.approx(d0 / ar * uc, rel=1e-12), f'M={M}'
        assert d0 / ar == pytest.approx(3.310463415200036, rel=1e-9)
        # M=1,5 artık narin (slender) koldadır: β·AR_f = 0,745 < 1
        assert math.sqrt(1.5 ** 2 - 1.0) * ar < 1.0
        assert _fin_compressibility_factor(1.5, ar, cg) == pytest.approx(
            d0 / 2.0, rel=1e-12)

    def test_2B_limitinde_eski_ifadeye_yakinsar(self):
        """AR_f → ∞ iken yeni çarpan ESKİ ifadeye gider (T3/T4)."""
        for ar in (50.0, 500.0, 5000.0):
            for M in (0.5, 2.5, 2.9):
                yeni = _fin_compressibility_factor(M, ar, 1.0)
                assert yeni / _eski_2B(M) == pytest.approx(
                    1.0, rel=3.0 / ar), f'AR_f={ar}, M={M}'

    def test_sifir_machta_tam_bir(self):
        a = _aero_A()
        k0 = _fin_compressibility_factor(0.0, a._fin_aspect,
                                         a._fin_cos_gamma)
        assert k0 == 1.0, f'k(0) tam 1 olmalı, {k0!r}'
        assert _fin_compressibility_factor(-3.0, a._fin_aspect,
                                           a._fin_cos_gamma) == 1.0

    def test_geometrisiz_cagri_REDDEDILIR(self):
        """FAIL-CLOSED: geometri yoksa sessiz yedek YOK, istisna var."""
        for ar, cg in ((0.0, 1.0), (-1.0, 1.0), (0.6, 0.0), (0.6, -0.5),
                       (float('nan'), 1.0), (0.6, float('nan'))):
            with pytest.raises(ValueError):
                _fin_compressibility_factor(2.5, ar, cg)

    def test_transonik_bant_kaynakli_ve_surekli(self):
        """Bant uçları OpenRocket FinSetCalc sabitleridir (0,9 / 1,5)."""
        assert (_FIN_M_SUB, _FIN_M_SUP) == (0.9, 1.5)
        a = _aero_A()
        ar, cg = a._fin_aspect, a._fin_cos_gamma

        def k(M):
            return _fin_compressibility_factor(M, ar, cg)
        for Mu in (_FIN_M_SUB, _FIN_M_SUP):
            assert k(Mu - 1e-9) == pytest.approx(k(Mu + 1e-9), rel=1e-6), (
                f'bant ucunda sıçrama var: M={Mu}')
        # süpersonikte M büyüdükçe kanat etkinliği DÜŞER (monoton)
        ust = [k(M) for M in (1.6, 2.0, 2.5, 2.9, 4.0, 6.0)]
        assert all(x > y for x, y in zip(ust, ust[1:]))


# =====================================================================
# 2) ÜRÜN ETKİSİ — süpersonik kararlılık hükmü
# =====================================================================
class TestSupersonikKararlilik:

    def test_marj_supersonikte_pozitif_kalir(self):
        """ÖNCE: M=2,5'te +0,04, M=2,9'da −0,69 kalibre (kararsız)."""
        a = _aero_A()
        assert a.static_margin(1.7, mach=2.5) > 1.0
        assert a.static_margin(1.7, mach=2.9) > 1.0
        # GÜNCELLENDİ (ÖH D25 / OH-D24-03): uç Mach konisi kaybı
        # yazılınca kanat etkinliği düştü, marj da düştü —
        # 4,205776 → 3,720632 (M=2,5) ve 3,739006 → 3,298327 (M=2,9).
        # Marj HÂLÂ pozitiftir; D23'teki +0,04 / −0,69 hâline dönmedi.
        assert a.static_margin(1.7, mach=2.5) == pytest.approx(
            3.720632, rel=1e-5)
        assert a.static_margin(1.7, mach=2.9) == pytest.approx(
            3.298327, rel=1e-5)
        # M=0 künyesi DEĞİŞMEDİ (konvansiyon)
        assert a.static_margin(1.7) == pytest.approx(4.414876, rel=1e-6)

    def test_dinamik_at_mach_KULLANIYOR(self):
        """AST: ``_derivatives`` artık Mach'a bağlı çifti çağırıyor.

        D23 bekçisi bunun TERSİNİ kilitliyordu (``at_mach`` çağrılmasın);
        o bekçi ÇEVRİLDİ — gerekçe tests/test_d23_termo_ucus_a1.py'de.
        """
        with open(os.path.join(KOK, 'hrma/analysis/six_dof_trajectory.py'),
                  encoding='utf-8') as f:
            agac = ast.parse(f.read())
        govde = [d for d in ast.walk(agac)
                 if isinstance(d, ast.FunctionDef)
                 and d.name == '_derivatives']
        assert len(govde) == 1
        cagrilar = {c.func.attr for c in ast.walk(govde[0])
                    if isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Attribute)}
        assert 'at_mach' in cagrilar

    def test_supersonik_arac_TAKLA_ATMIYOR_apoje_yayimlaniyor(self):
        """M≈2,91'e çıkan sondaj roketi uçuşunu tamamlar."""
        r = _kos_B()
        assert r['end_reason'] == 'apogee', (
            f"takla yeniden başladı: {r['end_reason']!r}")
        assert math.isfinite(r['apogee']) and r['apogee'] > 10000.0
        assert r['max_mach'] > 2.8
        assert r['max_alpha_deg'] < 5.0
        assert r['stable'] is True

    def test_ESKI_2B_carpanla_AYNI_arac_takla_atiyor(self):
        """Nedensellik bekçisi: kusuru geri koyunca takla GERİ GELİR.

        Bu, onarımın hangi büyüklükten geldiğini kilitler — bağ (at_mach)
        her iki kolda da açıktır, YALNIZ çarpan değişir.
        """
        gercek = S._fin_compressibility_factor
        try:
            S._fin_compressibility_factor = _eski_2B
            r = _kos_B()
        finally:
            S._fin_compressibility_factor = gercek
        assert r['end_reason'] == 'tumble_detected'
        assert r['apogee'] is None

    def test_kunye_M0_degerlerini_yayimlamaya_devam_eder(self):
        """Yayımlanan ``cn_alpha``/``x_cp`` M→0 Barrowman'dır (bit-aynı)."""
        r = _kos_B()
        a = _aero_B()
        assert r['cn_alpha'] == pytest.approx(a.cn_alpha, rel=0, abs=0)
        assert r['x_cp'] == pytest.approx(a.x_cp, rel=0, abs=0)


# =====================================================================
# 3) Kenar hâller
# =====================================================================
class TestKenarHaller:

    def test_kanatsiz_arac_carpansiz(self):
        a = BarrowmanAero(body_diameter=0.15, nose_length=0.5,
                          body_length=3.0, fin_count=0)
        assert a._fin_aspect is None and a._fin_cos_gamma is None
        cn, xcp = a.at_mach(3.0)
        assert cn == a.cn_alpha and xcp == a.x_cp

    def test_geometri_alanlari_eq340_ile_tutarli(self):
        """AR_f = s²/A_fin, cos Γ_c = s/l_orta, Q = 2·l/(c_r+c_t) (T1)."""
        s_, cr, ct, msw = 0.15, 0.30, 0.15, 0.10
        a = _aero_A()
        l_mid = math.sqrt(s_ ** 2 + (msw + (ct - cr) / 2.0) ** 2)
        a_fin = s_ * (cr + ct) / 2.0
        assert a._fin_aspect == pytest.approx(s_ ** 2 / a_fin, rel=1e-15)
        assert a._fin_cos_gamma == pytest.approx(s_ / l_mid, rel=1e-15)
        assert a._fin_aspect / a._fin_cos_gamma == pytest.approx(
            2.0 * l_mid / (cr + ct), rel=1e-14)

    def test_at_mach_dizi_degil_skaler_dondurur(self):
        a = _aero_A()
        cn, xcp = a.at_mach(2.5)
        assert isinstance(cn, float) and isinstance(xcp, float)
        assert np.isfinite(cn) and np.isfinite(xcp)
