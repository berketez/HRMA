# tests/cfd — hrma/utils/gci.py TEK GCI tanımının bekçisi (ÖH D37 A3a cfd-kok-a, F-04)
"""
DK kampanyasının hakem düzeltmesinde (24 Eyl 2026, rapor.md §(h)1-2) ölçülen
kusurlar: eski araç büyüyen farkları |ln| ile pozitif mertebeye çeviriyor
((4,2,1) → p = +1, GCI %62,5), eşit farkta sıfıra bölüyor, limit döngüsü /
donmuş kökten GCI yazıyordu. DK ``gci_bekci.py``nin 8 karşı örneği burada
ürün modülüne karşı koşar; geçerlilik kapısı (koşum durumu + iniş kapısı)
ayrıca sınanır. Ters mutasyon (mutasyon.md): ``p_isaretli`` içine mutlak
değer konunca 1. bekçi kırmızıya düşer.
"""

import json
import pathlib

import pytest

from tests.support.kanit import kanit_gerekli
from hrma.utils.gci import (
    GECERLI_HUKUMLER, GCI_DURUMLARI, gci, p_isaretli, ucu_gecerli,
)

N = (16, 4, 1)          # 2B'de h ∝ N^(-1/2) → r21 = r32 = 2
KOK = pathlib.Path(__file__).resolve().parents[2]
DK_DEVRALMA = (KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D37' / 'dogrulama'
               / 'cfd' / 'devralma_denetimi.json')


def test_buyuyen_fark_4_2_1_isaretli_p_eksi_bir_GCI_YOK():
    """Hakem karşı örneği: farklar büyüyor → monoton ıraksama, p = −1."""
    g = gci(N, (4.0, 2.0, 1.0))
    assert g['status'] == 'monotonic_divergent'
    assert g['gci_valid'] is False
    assert 'GCI_fine21' not in g and 'p' not in g
    assert g['p_signed'] == pytest.approx(-1.0, abs=1e-12)


def test_salinimli_1_2_0_GCI_YOK_bant_var():
    g = gci(N, (1.0, 2.0, 0.0))
    assert g['status'] == 'oscillatory'
    assert g['gci_valid'] is False and 'GCI_fine21' not in g
    assert g['band_rel'] is not None and g['band_rel'] == pytest.approx(2.0)


def test_esit_fark_3_2_1_istisnasiz_GCI_YOK():
    g = gci(N, (3.0, 2.0, 1.0))          # eski araç ZeroDivisionError atıyordu
    assert g['status'] == 'equal_differences'
    assert g['gci_valid'] is False


def test_salinimli_iraksama_1_4_3():
    g = gci(N, (1.0, 4.0, 3.0))          # ε21 = 3, ε32 = −1 → R = −3
    assert g['status'] == 'oscillatory_divergent'
    assert g['gci_valid'] is False
    assert g['R'] == pytest.approx(-3.0)


def test_yapay_ikinci_mertebe_dizisi_p2_fext_kesin():
    Nn = (3200, 800, 200)
    f = tuple(1.0 + 0.7 * n ** -1.0 for n in Nn)      # h² = 1/N → p = 2
    g = gci(Nn, f)
    assert g['status'] == 'monotonic' and g['gci_valid'] is True
    assert g['p'] == pytest.approx(2.0, abs=1e-9)
    assert g['f_ext'] == pytest.approx(1.0, abs=1e-12)
    assert g['GCI_fine21'] > 0.0
    assert g['refinement_ok'] is True
    # Celik Eş. 8: asimptotik oran r21^p·GCI21/GCI32 ≈ 1 — e_a bağıl hata
    # olduğundan kesin diziye tam f2/f1 = 1,00066 çıkar (analitik), 1e-3 bant
    assert g['asymptotic_ratio'] == pytest.approx(f[1] / f[0], rel=1e-12)
    assert g['asymptotic_ratio'] == pytest.approx(1.0, rel=1e-3)


def test_esit_olmayan_oran_p2():
    h = (0.01, 0.02, 0.03)
    Nu = tuple(x ** -2.0 for x in h)
    g = gci(Nu, tuple(1.0 + 0.7 * x ** 2 for x in h))
    assert g['status'] == 'monotonic'
    assert g['p'] == pytest.approx(2.0, abs=1e-9)
    assert g['r32'] == pytest.approx(1.5)


def test_esit_olmayan_oranda_iraksama_p_eksi_bir():
    h = (0.01, 0.02, 0.03)
    Nu = tuple(x ** -2.0 for x in h)
    g = gci(Nu, tuple(1.0 + 0.7 / x for x in h))
    assert g['status'] == 'monotonic_divergent'
    assert g['p_signed'] == pytest.approx(-1.0, abs=1e-9)


def test_dk_c6_o8_dizisi_monoton_iraksama():
    """Kampanyanın kendi C6 Ö8 dizisi (K0c/K0/K0a) → p ≈ −1,4532 (hakem)."""
    # ÖH V3 taban-b: okuma kanıt KAPISINDAN (tests/support/kanit.py) —
    # docs'suz dalda gerekçeli atlama, geliştirme ağacında eksikse KIRMIZI
    # (eski elle ``exists()`` dalı orada da sessizce atlıyordu).
    dd = json.loads(kanit_gerekli(DK_DEVRALMA).read_text(
        encoding='utf-8'))['C6_O8']['kademeler']
    g = gci((192 * 48, 96 * 24, 48 * 12),
            (dd['K0c']['oran_bogaz'], dd['K0']['oran_bogaz'],
             dd['K0a']['oran_bogaz']))
    assert g['status'] == 'monotonic_divergent'
    assert g['p_signed'] == pytest.approx(-1.4532, abs=5e-4)


def test_p_isaretli_esit_oran_kapali_bicim():
    p, ok = p_isaretli(2.0, 2.0, 4.0)     # ε32/ε21 = 4 → p = 2
    assert ok and p == pytest.approx(2.0)
    p, ok = p_isaretli(2.0, 2.0, 0.5)     # büyüyen fark → p = −1
    assert ok and p == pytest.approx(-1.0)


def test_girdi_kapilari():
    with pytest.raises(ValueError):
        gci((4, 16, 1), (1.0, 2.0, 3.0))     # sıra ince→kaba değil
    with pytest.raises(ValueError):
        gci(N, (1.0, float('nan'), 3.0))
    assert set(GCI_DURUMLARI) >= {'monotonic', 'oscillatory', 'degenerate'}


# ---------------------------------------------------------------------------
# Geçerlilik kapısı (koşum durumu) — limit döngüsü / donmuş kökten GCI yok
# ---------------------------------------------------------------------------

def _sev(st, inis=None, kapi=2.0, frozen=100, kal=1e-11, tol=1e-10):
    return dict(convergence_status=st, residual_last=kal, tol_res=tol,
                limiter_freeze=dict(frozen_at_iter=frozen,
                                    descent_decades_at_freeze=inis,
                                    descent_gate_decades=kapi))


def test_kapi_uc_converged_gecerli():
    ok, etiket, sorun = ucu_gecerli([_sev('converged')] * 3)
    assert ok and not sorun


@pytest.mark.parametrize('st', ['not_converged', 'plateau', 'diverged',
                                'wall_star_pressure_nonpositive', 'bilinmeyen'])
def test_kapi_yakinsamamis_seviye_gecersiz(st):
    ok, etiket, sorun = ucu_gecerli([_sev('converged'), _sev(st),
                                     _sev('converged')])
    assert not ok and sorun[0]['seviye'] == 1 and sorun[0]['durum'] == st


def test_kapi_not_evaluated_inis_kapisini_gecen_donmus_kok_gecerli():
    ok, _e, sorun = ucu_gecerli([_sev('not_evaluated', inis=2.6),
                                 _sev('converged'), _sev('converged')])
    assert ok and not sorun


def test_kapi_not_evaluated_ERKEN_donma_gecersiz():
    """DK C1 240×48 deseni: 0,23 mertebe inişte donma → yapay kök, GCI YOK."""
    ok, _e, sorun = ucu_gecerli([_sev('not_evaluated', inis=0.23),
                                 _sev('converged'), _sev('converged')])
    assert not ok and 'erken dondurma' in sorun[0]['neden']


def test_kapi_not_evaluated_olcumsuz_gecersiz_fail_closed():
    """ÖNCE (DK) koşumlarında limiter_freeze bloğu YOK → geçerli sayılmaz."""
    ok, _e, sorun = ucu_gecerli([dict(convergence_status='not_evaluated',
                                      residual_last=1e-11, tol_res=1e-10),
                                 _sev('converged'), _sev('converged')])
    assert not ok and 'ölçülemeyen' in sorun[0]['neden']


def test_kapi_not_evaluated_kalinti_hedefin_ustunde_gecersiz():
    ok, _e, sorun = ucu_gecerli([_sev('not_evaluated', inis=3.0, kal=5e-9,
                                      tol=1e-10)])
    assert not ok and 'kalıntı' in sorun[0]['neden']
    assert 'converged' in GECERLI_HUKUMLER
