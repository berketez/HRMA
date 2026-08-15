# tests/cfd — eksen (r→0) simetri sağlığı bekçisi (basamak 5)
"""
Eksen bir sınır koşulu değil geometrik gerçektir (grid_axisym beyanı:
j=0 yüzleri akısız, hiçbir yerde r'ye bölme yok; euler_core: MUSCL için
ayna hücreleri — ρ, u_z, p çift; u_r tek). Bu bekçi, o kurgunun ÜRÜNÜNÜ
ölçer: eksene komşu hücrelerde parazit radyal hız ve basınç salınımı.

Üç metrik (hepsi eksene komşu ilk hücre satırları üstünden):
  (1) max |u_r|/a  (j=0):  parazit radyal hız, yerel ses hızına oranla.
      NOT: j=0 hücre merkezi r=Δr/2'dedir, orada u_r'nin KÜÇÜK fiziksel
      bileşeni vardır (akım çizgileri daralır/genişler, u_r ∝ r) — metrik
      parazit + bu fiziksel payı BİRLİKTE ölçer, eşik ölçümden konur.
  (2) max |p(j=0) − p(j=1)|/p(j=0): eksen basınç düzlüğü (∂p/∂r → 0).
  (3) max |p0 − 2p1 + p2|/p0: radyal tek-çift (odd-even) salınım dedektörü.

Kırık eksen aynası (ör. u_r işaret hatası) bu metrikleri bir-iki mertebe
patlatır — bekçinin varlık sebebi budur (mutasyon kanıtı raporda).

ÖLÇÜLDÜ (bu depo, M4 Max, 2026-08-15; 120×24 derin çözümler):
  izantropik: |u_r|/a 6,1e-3   |Δp01|/p 1,7e-3   |δ²p|/p 1,7e-3
  şoklu     : |u_r|/a 1,2e-2   |Δp01|/p 8,7e-3   |δ²p|/p 6,0e-3
  (şokluda büyüme şok kolonlarının eksen ayağından — şok cephesi eksene
  dik inmiyor, yerel sıçrama radyal farkları büyütür; parazit değil.)
Eşikler = ölçüm × ~2,5-3 payı.
"""

import numpy as np

from .conftest import LULE_GAMMA, LULE_R

IZAN_UR_A_TOL = 1.5e-2
IZAN_DP01_TOL = 5.0e-3
IZAN_D2P_TOL = 5.0e-3

SOK_UR_A_TOL = 3.0e-2
SOK_DP01_TOL = 2.5e-2
SOK_D2P_TOL = 2.0e-2


def _eksen_metrikleri(res):
    """(max|u_r|/a @ j=0, max|Δp01|/p, max|δ²p|/p) üçlüsü."""
    f = res['fields']
    p = np.asarray(f['pressure_Pa'])
    ur = np.asarray(f['u_r_m_s'])
    temp = np.asarray(f['temperature_K'])
    a = np.sqrt(LULE_GAMMA * LULE_R * temp)
    ur_a = float(np.max(np.abs(ur[:, 0]) / a[:, 0]))
    dp01 = float(np.max(np.abs(p[:, 0] - p[:, 1]) / p[:, 0]))
    d2p = float(np.max(np.abs(p[:, 0] - 2.0 * p[:, 1] + p[:, 2]) / p[:, 0]))
    return ur_a, dp01, d2p


def _kontrol(ad, res, ur_tol, dp_tol, d2p_tol):
    ur_a, dp01, d2p = _eksen_metrikleri(res)
    assert ur_a < ur_tol, (
        f'{ad}: eksen komşusunda parazit radyal hız |u_r|/a = {ur_a:.3e} '
        f'>= {ur_tol:.0e} — eksen aynası (u_r tek parite) bozulmuş olabilir')
    assert dp01 < dp_tol, (
        f'{ad}: eksen basınç düzlüğü bozuk: |p0−p1|/p0 = {dp01:.3e} '
        f'>= {dp_tol:.0e} (∂p/∂r eksende sıfırlanmıyor)')
    assert d2p < d2p_tol, (
        f'{ad}: radyal tek-çift salınım: |p0−2p1+p2|/p0 = {d2p:.3e} '
        f'>= {d2p_tol:.0e} (eksen yakını parazit dalgalanma)')


def test_eksen_sagligi_izantropik(lule_cozumu):
    _, res = lule_cozumu
    _kontrol('izantropik', res, IZAN_UR_A_TOL, IZAN_DP01_TOL, IZAN_D2P_TOL)


def test_eksen_sagligi_soklu(sok_cozumu):
    """Şok eksene çarpan vakada da eksen sağlığı korunmalı (şok cephesinin
    eksen ayağı parazit salınım tohumlayabilir — ölçülen pay eşikte)."""
    _, res = sok_cozumu
    _kontrol('şoklu', res, SOK_UR_A_TOL, SOK_DP01_TOL, SOK_D2P_TOL)
