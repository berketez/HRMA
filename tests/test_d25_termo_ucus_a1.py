# -*- coding: utf-8 -*-
"""ÖH Dalga-25 / termo-ucus aşama-1 bekçileri — TEK KALEM: OH-D24-03.

Kalem: süpersonik kanat çarpanında **uç Mach konisi kaybı YAZILMAMIŞTI**.
D24 (OH-D23-17) çarpanı sonlu-açıklık biçimine çevirdi ama süpersonik dalı
saf 2-B Ackeret oranı (``4/β``) olarak bıraktı ve eksikliği yalnızca
docstring'de İLAN ETTİ. Beyan çözüm değildir (doktrin 1).

YAZILAN İKİ KOL (kaynak + türetim + Lean: aşağıda):

    β·AR_f ≥ 1 :  k = 2·D₀·(1 − 1/(4·β·AR_f)) / (π·AR_f·β)
    β·AR_f < 1 :  k = D₀/2            (narin/Jones kolu, Mach'tan bağımsız)

ÖLÇÜLDÜ (taban cdf2106 → bu ağaç; ``docs/scofield/raw/OH/D25/termo-ucus/
a1/once.json`` → ``sonra.json``):

    A aracı (AR_f = 0,667)   k(2,5)  0,91979 → 0,76926   (−%16,4)
                             k(2,9)  0,77421 → 0,66756   (−%13,8)
                             marj M=2,5  4,2058 → 3,7206 kalibre
                             marj M=2,9  3,7390 → 3,2983 kalibre
    B aracı (AR_f = 0,8125)  k(2,9)  0,66045 → 0,58580   (−%11,3)
    D aracı (AR_f = 0,25)    k(1,5)  4,62538 → 1,01539   (−%78,1)
                             marj M=1,5  4,2836 → 0,3779 kalibre

D aracının taban değeri (k = 4,63) kanat etkinliğinin sıkıştırılamaz
değerin **4,6 katı** olduğunu söylüyordu — fiziksel olarak olanaksız;
statik marj da 4,28 kalibre "çok kararlı" diyordu, gerçekte araç
0,38 kalibreyle sınırdadır.

KANIT ZİNCİRİ:
  * literatür  — lineerleştirilmiş süpersonik kanat teorisi (Ackeret /
    Busemann şerit yöntemi + uç Mach konisi; Nielsen *Missile
    Aerodynamics* 1960, USAF DATCOM §4.1.3.2 dikdörtgen kanat bağıntısı
    ``C_Nα = (4/β)[1 − 1/(2βA)]``) ve narin kanat için R. T. Jones (1946),
    NACA TR-835 ``C_Nα → π·A/2``.
  * sembolik türetim + boyut analizi — ``.../a1/turetim.py`` → ``turetim.json``
    (T1..T10, hepsi ``ISPAT: true``).
  * Lean 4 / Mathlib makine ispatı — ``formal/LeanLab/HRMAFinTip.lean``
    (11 teorem, ``#print axioms`` hepsinde
    ``[propext, Classical.choice, Quot.sound]``, ``sorryAx`` YOK);
    ``formal/registry.json``'da 10 kayıt.
  * ters-mutasyon — ``.../a1/mutasyon.json``.
"""
import ast
import contextlib
import io
import json
import math
import os

import pytest

from hrma.analysis import six_dof_trajectory as S
from hrma.analysis.six_dof_trajectory import (
    _FIN_M_SUB, _FIN_M_SUP, _FIN_TIP_CONE_MIN_BETA_AR, BarrowmanAero,
    SixDOFTrajectory, _fin_compressibility_factor)
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------
# Referans araçlar (olcum.py ile BİREBİR aynı geometriler)
# ---------------------------------------------------------------------
def _aero_A():
    """AR_f = 0,6667 — D23/D24'ün 'marj 4,41 → 0,04' aracı."""
    return BarrowmanAero(body_diameter=0.15, nose_length=0.5,
                         body_length=3.0, nose_type='ogive', fin_count=4,
                         fin_root_chord=0.30, fin_tip_chord=0.15,
                         fin_span=0.15, fin_sweep=0.10)


def _aero_B():
    """AR_f = 0,8125 — D23/D24'ün M≈2,91'de TAKLA atan aracı."""
    return BarrowmanAero(body_diameter=0.15, nose_length=0.5,
                         body_length=3.0, fin_count=4, fin_root_chord=0.22,
                         fin_tip_chord=0.1, fin_span=0.13, fin_sweep=0.08)


def _aero_D():
    """AR_f = 0,25 — güdük kanat; tabanda k(1,5) = 4,63 çıkıyordu."""
    return BarrowmanAero(body_diameter=0.20, nose_length=0.6,
                         body_length=3.5, fin_count=4, fin_root_chord=0.50,
                         fin_tip_chord=0.30, fin_span=0.10, fin_sweep=0.10)


def _geo(aero):
    """(AR_f, cos Γ_c, Q, D₀) — çarpanın tüm girdileri."""
    ar, cg = aero._fin_aspect, aero._fin_cos_gamma
    q = ar / cg
    return ar, cg, q, 1.0 + math.sqrt(1.0 + q * q)


def _d24_ksup(mach, ar, cg):
    """TABAN (cdf2106) süpersonik dalı — UÇ KAYBI YOK, narin kol YOK.

    Kusurun kendisi; bekçilerin nedensellik kolunda kullanılır.
    """
    q = ar / cg
    d0 = 1.0 + math.sqrt(1.0 + q * q)
    return 2.0 * d0 / (math.pi * ar * math.sqrt(mach * mach - 1.0))


# =====================================================================
# 1) UÇ MACH KONİSİ KAYBI — kapalı biçim ve sınırları
# =====================================================================
class TestUcMachKonisiKaybi:

    def test_esik_tek_kaynak_ve_deger(self):
        """Geçerlilik eşiği TEK SABİTTİR ve 1,0'dır (β·AR_f ≥ 1)."""
        assert _FIN_TIP_CONE_MIN_BETA_AR == 1.0
        kaynak = open(os.path.join(
            KOK, 'hrma/analysis/six_dof_trajectory.py'),
            encoding='utf-8').read()
        # sabit BİR kez tanımlanır, gövdede adıyla kullanılır (literal yok)
        assert kaynak.count('_FIN_TIP_CONE_MIN_BETA_AR = 1.0') == 1
        assert kaynak.count('_FIN_TIP_CONE_MIN_BETA_AR') >= 2

    def test_kapali_bicim_iki_kollu(self):
        """k, iki bağımsız teorinin kapalı biçimidir (bit düzeyinde)."""
        for aero in (_aero_A(), _aero_B(), _aero_D()):
            ar, cg, q, d0 = _geo(aero)
            for M in (1.5, 1.9, 2.0, 2.5, 2.9, 3.5, 5.0, 8.0):
                beta = math.sqrt(M * M - 1.0)
                if beta * ar >= _FIN_TIP_CONE_MIN_BETA_AR:
                    bekle = (2.0 * d0 * (1.0 - 1.0 / (4.0 * beta * ar))
                             / (math.pi * ar * beta))
                else:
                    bekle = d0 / 2.0
                assert _fin_compressibility_factor(M, ar, cg) == \
                    pytest.approx(bekle, rel=1e-12), f'AR_f={ar}, M={M}'

    def test_uc_kayip_carpani_ucte_dort_ile_bir_arasinda(self):
        """(1 − 1/(4βAR_f)) ∈ [3/4, 1): etkinliği en çok %25 azaltır,
        ASLA artırmaz (Lean: tipLoss_ge_three_quarters, tipLoss_lt_one)."""
        for aero in (_aero_A(), _aero_B(), _aero_D()):
            ar, cg, q, d0 = _geo(aero)
            for M in (1.5, 2.0, 2.5, 2.9, 4.0, 6.0, 12.0):
                beta = math.sqrt(M * M - 1.0)
                if beta * ar < _FIN_TIP_CONE_MIN_BETA_AR:
                    continue
                oran = _fin_compressibility_factor(M, ar, cg) / \
                    _d24_ksup(M, ar, cg)
                assert 0.75 <= oran < 1.0, f'AR_f={ar}, M={M}: {oran!r}'
        # sınırda TAM 3/4
        ar = 1.0 / math.sqrt(2.5 ** 2 - 1.0)      # β·AR_f = 1 olacak şekilde
        oran = _fin_compressibility_factor(2.5, ar, 1.0) / \
            _d24_ksup(2.5, ar, 1.0)
        assert oran == pytest.approx(0.75, rel=1e-12)

    def test_2B_limiti_BOZULMADI(self):
        """AR_f → ∞ iken uç kaybı yok olur; ifade 2-B Ackeret oranına
        döner (Lean: tipLoss_tendsto_one)."""
        for ar in (50.0, 500.0, 5000.0, 50000.0):
            for M in (2.5, 2.9, 5.0):
                oran = _fin_compressibility_factor(M, ar, 1.0) / \
                    _d24_ksup(M, ar, 1.0)
                beta = math.sqrt(M * M - 1.0)
                assert oran == pytest.approx(1.0 - 1.0 / (4.0 * beta * ar),
                                             rel=1e-12)
                assert oran > 1.0 - 1.0 / ar

    def test_supersonikte_tekduze_azalir(self):
        """Kanat etkinliği süpersonikte tekdüze düşer (Lean: kSup_anti)."""
        for aero in (_aero_A(), _aero_B(), _aero_D()):
            ar, cg, _, _ = _geo(aero)
            M_esik = math.sqrt(1.0 + 1.0 / (ar * ar))
            ust = [_fin_compressibility_factor(M, ar, cg)
                   for M in (M_esik + 0.01, M_esik + 0.5, M_esik + 1.5,
                             M_esik + 3.0, M_esik + 6.0)]
            assert all(x > y for x, y in zip(ust, ust[1:])), f'AR_f={ar}'


# =====================================================================
# 2) NARİN (JONES) KOLU — örtüşen koni bölgesi
# =====================================================================
class TestNarinKanatKolu:

    def test_narin_kol_D0_bolu_2_ve_MACHTAN_BAGIMSIZ(self):
        aero = _aero_D()
        ar, cg, q, d0 = _geo(aero)
        M_esik = math.sqrt(1.0 + 1.0 / (ar * ar))
        assert M_esik == pytest.approx(4.1231056256, rel=1e-9)
        degerler = {round(_fin_compressibility_factor(M, ar, cg), 12)
                    for M in (1.5, 2.0, 2.5, 2.9, 3.5, 4.0, M_esik - 1e-9)}
        assert len(degerler) == 1, f'narin kol Mach\'a bağlı çıktı: {degerler}'
        assert degerler.pop() == pytest.approx(d0 / 2.0, rel=1e-12)
        assert d0 / 2.0 == pytest.approx(1.0153882032, rel=1e-9)

    def test_narin_kol_SONIK_NOKTAYLA_SUREKLI(self):
        """D₀/2, altsonik Diederich dalının M→1⁻ limitidir — kol uydurma
        sabit DEĞİL (Lean: kSlender_eq_kSub_sonic)."""
        for aero in (_aero_A(), _aero_B(), _aero_D()):
            ar, cg, q, d0 = _geo(aero)

            def k_alt(m):
                b2 = 1.0 - m * m
                return d0 / (1.0 + math.sqrt(1.0 + b2 * q * q))
            assert k_alt(1.0) == pytest.approx(d0 / 2.0, rel=1e-15)
            # M → 1⁻ yaklaşımı: sapma β² ile ikinci mertebe küçülür
            assert k_alt(1.0 - 1e-9) == pytest.approx(d0 / 2.0, rel=1e-8)
            assert k_alt(1.0 - 1e-6) == pytest.approx(d0 / 2.0, rel=1e-5)

    def test_gecisteki_basamak_TAM_1_eksi_3_bolu_pi(self):
        """β·AR_f = 1'de iki kol arasındaki oran tam 3/π'dir; basamak
        %4,507'dir ve AŞAĞI yönlüdür (Lean: kSup_threshold_ratio,
        kSup_lt_kSlender_at_threshold). Kalibre EDİLMEDİ, ilan edildi."""
        for aero in (_aero_A(), _aero_B(), _aero_D()):
            ar, cg, q, d0 = _geo(aero)
            M_esik = math.sqrt(1.0 + 1.0 / (ar * ar))
            alt = _fin_compressibility_factor(M_esik - 1e-9, ar, cg)
            ust = _fin_compressibility_factor(M_esik + 1e-9, ar, cg)
            assert alt == pytest.approx(d0 / 2.0, rel=1e-12)
            assert ust / alt == pytest.approx(3.0 / math.pi, rel=1e-8)
            assert ust < alt          # basamak AŞAĞI
        assert 1.0 - 3.0 / math.pi == pytest.approx(0.045070341, rel=1e-6)

    def test_carpan_sonik_tepeyi_ASLA_ASMAZ(self):
        """k(M) hiçbir Mach'ta D₀/2'yi geçemez — tabandaki 4,6 katlık
        olanaksız değerin bir daha çıkamayacağının bekçisi."""
        for aero in (_aero_A(), _aero_B(), _aero_D()):
            ar, cg, q, d0 = _geo(aero)
            for i in range(0, 121):
                M = i * 0.1
                k = _fin_compressibility_factor(M, ar, cg)
                assert k <= d0 / 2.0 + 1e-12, f'AR_f={ar}, M={M}: k={k!r}'

    def test_TABAN_dali_ayni_bekciyi_KIRAR(self):
        """Nedensellik: uç kaybı + narin kol kaldırılırsa k, D₀/2'yi
        4,6 KAT aşar (tabanın ölçülen hâli)."""
        aero = _aero_D()
        ar, cg, q, d0 = _geo(aero)
        taban_k = _d24_ksup(1.5, ar, cg)
        assert taban_k == pytest.approx(4.62538, rel=1e-4)
        assert taban_k > 4.0 * (d0 / 2.0)
        assert _fin_compressibility_factor(1.5, ar, cg) == pytest.approx(
            1.0153882032, rel=1e-9)


# =====================================================================
# 3) ÜRÜN ETKİSİ — statik marj hükmü
# =====================================================================
class TestUrunEtkisi:

    def test_A_araci_marj_sayilari(self):
        a = _aero_A()
        assert a.static_margin(1.7, mach=2.5) == pytest.approx(
            3.720632, rel=1e-5)
        assert a.static_margin(1.7, mach=2.9) == pytest.approx(
            3.298327, rel=1e-5)
        # M=0 künyesi DEĞİŞMEDİ (konvansiyon; D24 ile bit-aynı)
        assert a.static_margin(1.7) == pytest.approx(4.414876, rel=1e-6)

    def test_D_araci_marji_ARTIK_SISIRILMIYOR(self):
        """Güdük kanatlı araç süpersonikte 'çok kararlı' görünmüyor."""
        d = _aero_D()
        ar, cg, q, d0 = _geo(d)
        s = SixDOFTrajectory(aero=d, dry_mass=40.0, propellant_mass=25.0,
                             thrust=9000.0, burn_time=8.0,
                             launch_elevation_deg=86.0, wind_speed=4.0)
        xcg = float(s.x_cg_full)
        marj = d.static_margin(xcg, mach=2.5)
        assert marj == pytest.approx(0.377949, rel=1e-4)
        # M→0 marjıyla neredeyse aynı: güdük kanat Mach'la kararlılık
        # KAZANMAZ. ÖLÇÜLDÜ: M=0 marjı 0,32531, M=2,5 marjı 0,37795 —
        # fark 0,0526 kalibre. Tabanda aynı fark 2,4803 kalibreydi
        # (0,32531 → 2,80558), yani 47 KAT büyüktü.
        assert abs(marj - d.static_margin(xcg)) < 0.08
        assert d.static_margin(xcg) == pytest.approx(0.325308, rel=1e-4)
        # tabanın iddiası: aynı araç, aynı x_cg, uç kaybı YOKKEN
        gercek = S._fin_compressibility_factor
        try:
            S._fin_compressibility_factor = _d24_ksup
            taban_marj = d.static_margin(xcg, mach=2.5)
        finally:
            S._fin_compressibility_factor = gercek
        assert taban_marj == pytest.approx(2.805578, rel=1e-4)
        assert taban_marj > 7.0 * marj

    def test_B_araci_UCUSU_TAMAMLIYOR(self):
        """Kanat etkinliği düştü ama araç hâlâ takla atmıyor."""
        s = SixDOFTrajectory(aero=_aero_B(), dry_mass=25.0,
                             propellant_mass=18.0, thrust=6500.0,
                             burn_time=7.5, launch_elevation_deg=84.0,
                             launch_azimuth_deg=90.0, wind_speed=6.0,
                             wind_direction_deg=270.0)
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                r = s.solve(t_max=400.0)
        assert r['end_reason'] == 'apogee'
        assert r['max_mach'] > 2.9
        assert r['apogee'] == pytest.approx(14217.5, rel=1e-3)
        assert r['stable'] is True

    def test_kunye_M0_degerleri_BIT_AYNI(self):
        """Yayımlanan cn_alpha/x_cp M→0 Barrowman'dır; değişmedi."""
        for aero in (_aero_A(), _aero_B(), _aero_D()):
            cn, xcp = aero.at_mach(0.0)
            assert cn == aero.cn_alpha and xcp == aero.x_cp


# =====================================================================
# 4) BEYAN DEĞİL ÇÖZÜM + fail-closed + kanıt zinciri
# =====================================================================
class TestKanitZinciri:

    def test_eksiklik_ILANI_KALDIRILDI_cunku_YAZILDI(self):
        """Doktrin 1: beyan çözüm değildir. D24'ün 'YAZILMAYAN düzeltme'
        ilanı yerini gerçek koda bıraktı."""
        kaynak = open(os.path.join(
            KOK, 'hrma/analysis/six_dof_trajectory.py'),
            encoding='utf-8').read()
        assert 'YAZILMAYAN düzeltme' not in kaynak
        agac = ast.parse(kaynak)
        fn = [d for d in ast.walk(agac) if isinstance(d, ast.FunctionDef)
              and d.name == '_fin_compressibility_factor']
        assert len(fn) == 1
        yurutulen = '\n'.join(
            ast.get_source_segment(kaynak, st) or ''
            for st in fn[0].body
            if not (isinstance(st, ast.Expr)
                    and isinstance(st.value, ast.Constant)))
        assert '4.0 * beta_ar' in yurutulen      # uç kaybı GÖVDEDE
        assert '0.5 * d0' in yurutulen           # narin kol GÖVDEDE

    def test_geometrisiz_cagri_REDDEDILIR(self):
        """FAIL-CLOSED korundu: geometri yoksa sessiz yedek YOK."""
        for ar, cg in ((0.0, 1.0), (-1.0, 1.0), (0.6, 0.0), (0.6, -0.5),
                       (float('nan'), 1.0), (0.6, float('nan'))):
            with pytest.raises(ValueError):
                _fin_compressibility_factor(2.5, ar, cg)

    def test_transonik_bant_uclari_SUREKLI_KALDI(self):
        """0,9 / 1,5 uçlarında sıçrama yok (D24 bekçisi korunuyor)."""
        assert (_FIN_M_SUB, _FIN_M_SUP) == (0.9, 1.5)
        for aero in (_aero_A(), _aero_B(), _aero_D()):
            ar, cg, _, _ = _geo(aero)
            for Mu in (_FIN_M_SUB, _FIN_M_SUP):
                assert _fin_compressibility_factor(Mu - 1e-9, ar, cg) == \
                    pytest.approx(
                        _fin_compressibility_factor(Mu + 1e-9, ar, cg),
                        rel=1e-6), f'AR_f={ar}, bant ucu M={Mu}'

    def test_LEAN_ispati_var_ve_DEFTERE_BAGLI(self):
        """Fizik doktrini: literatür + boyut + Lean. Lean ayağı burada."""
        lean = os.path.join(KOK, 'formal/LeanLab/HRMAFinTip.lean')
        assert os.path.exists(lean)
        metin = open(lean, encoding='utf-8').read()
        assert 'sorry' not in metin
        for ad in ('tipLoss_deficit', 'tipLoss_lt_one',
                   'tipLoss_ge_three_quarters', 'tipLoss_tendsto_one',
                   'kSup_lt_kSupNoTip', 'kSlender_eq_kSub_sonic',
                   'kSup_threshold_ratio', 'kSup_lt_kSlender_at_threshold',
                   'kSup_anti', 'kSup_pos'):
            assert f'theorem {ad}' in metin, ad
        with open(os.path.join(KOK, 'formal/registry.json'),
                  encoding='utf-8') as f:
            kayit = json.load(f)
        benim = [e for e in kayit['entries']
                 if e['lean_file'].endswith('HRMAFinTip.lean')]
        assert len(benim) == 10
        py = open(os.path.join(
            KOK, 'hrma/analysis/six_dof_trajectory.py'),
            encoding='utf-8').read().splitlines()
        for e in benim:
            assert e['python_file'] == 'hrma/analysis/six_dof_trajectory.py'
            assert e['status'] == 'proved'
            assert e['anchor'] in py[e['python_line'] - 1], e['theorem']

    def test_TURETIM_kaniti_dosyada_ve_TAMAMI_ISPAT(self):
        yol = os.path.join(
            KOK, 'docs/scofield/raw/OH/D25/termo-ucus/a1/turetim.json')
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            t = json.load(f)
        assert t['TUM_ISPATLAR'] is True
        for k in ('T1_ISPAT', 'T2_ISPAT', 'T3_ISPAT', 'T4_ISPAT', 'T5_ISPAT',
                  'T6_ISPAT', 'T7_ISPAT', 'T8_ISPAT', 'T9_ISPAT'):
            assert t[k] is True, k
        assert t['T6_oran'] == '3/pi'
        assert t['T1_kayip_orani_AR_cinsinden'] == '1/(4*AR*beta)'
