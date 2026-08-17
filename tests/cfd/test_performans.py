# tests/cfd — performans turu bekçileri: hoist bit-özdeşliği + arka uç eşdeğerliği
"""
Aşama 1B performans turunun DOĞRULUK bekçileri (tasarım belgesi §5:
ölç → hoist → gerekirse numba; optimizasyon ölçümsüz yapılmaz).

Bekçiler süre DEĞİL özdeşlik kilitler (duvar-saati bekçisi makine yüküne
göre yalancı kırmızı verir; süreler rapora ölçüm olarak girer):
  (1) Geometri hoist'i (precompute_geometry → residual_axisym geom
      parametresi) çağrı-içi hesapla BİT-ÖZDEŞTİR.
  (2) numba çekirdeği (kernels.directional_hllc) saf NumPy yoluyla
      BİT-ÖZDEŞTİR (fastmath kapalı + aynı işlem sırası; ÖLÇÜLDÜ:
      20000 rastgele durumda maks fark tam 0,0 — numba 0.61 / NumPy 1.26 /
      M4 Max). Platform/sürüm değişiminde fark çıkarsa bu bekçi kırmızıya
      döner ve eşik YENİDEN ölçÜMLE gevşetilir — sessiz gevşetme yok.
  (3) HRMA_CFD_DISABLE_NUMBA=1 ortam değişkeni numba'yı gerçekten kapatır
      (alt süreçte içe aktarma düzeyinde doğrulanır).
  (4) Şok sensörü pürüzsüz akışta HİÇ tetiklenmez (izantropik çözümde 0
      kolon → sonuç sensörsüz yolla bit-özdeş) ve arka uç beyanı gerçeği
      söyler.

ÖLÇÜLEN SÜRELER (M4 Max, 2026-08-15; 256×64 izantropik derin yakınsama,
21173 iterasyon — rapor içindir, bekçi değildir):
  saf NumPy (hoist'li)   : 171,5 s  (8,10 ms/iter)
  numba çekirdeği        :  86,6 s  (4,09 ms/iter) → 1,98×
  hoist tek başına       : 4,644 → 4,532 ms/residual çağrısı (%2,4)
  İki yol aynı iterasyon sayısında aynı kütle artığına (1,04e-12) indi —
  bit-özdeşliğin koşum düzeyindeki yankısı.
"""

import pathlib
import subprocess
import sys

import numpy as np
import pytest

from hrma.cfd import kernels
from hrma.cfd.euler_core import (
    _directional_flux_numpy,
    _unit_normals,
    precompute_geometry,
    residual_axisym,
)
from hrma.cfd.grid_axisym import build_grid_from_wall

from .conftest import (
    LULE_GAMMA, LULE_P0, LULE_R, LULE_T0,
    LULE_L_CONV, LULE_L_DIV, lule_duvar_yaricapi,
)
from tests.bagimlilik_kapisi import kurulu_mu


def _kucuk_vaka():
    """60×12 ızgara + düzgün olmayan (izantropik tahmin) durum."""
    from hrma.cfd.steady import _isentropic_initial_state

    z_nodes = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, 61)
    grid = build_grid_from_wall(z_nodes, lule_duvar_yaricapi(z_nodes), 12)
    U, _ = _isentropic_initial_state(grid, LULE_P0, LULE_T0, LULE_GAMMA,
                                     LULE_R, Pb=2.75e6)
    return grid, U


def test_precompute_geometry_sozlesmesi():
    """precompute_geometry içeriği, hoist ÖNCESİ çağrı-içi hesapların
    (dilimlenmiş _unit_normals) BİT-ÖZDEŞ karşılığıdır.

    DİKKAT (mutasyonla öğrenildi): geom=None yolu da precompute_geometry'yi
    çağırdığından 'geom verili vs verilmemiş' kıyası fonksiyon İÇİ kusuru
    yakalayamaz (mutasyon C1, n_out_hat→n_hat_i[0]: H-tipi ızgarada dik
    i-yüzlerinin birim normalleri özdeş — eşdeğer mutant; C2,
    wall_n_hat→n_hat_j[:, -2]: sarmalama kıyası yine yeşil kaldı). Gerçek
    sözleşme referans ifadelere karşı burada kilitlenir."""
    grid, _ = _kucuk_vaka()
    geom = precompute_geometry(grid)
    n_i, a_i = _unit_normals(grid.face_i)
    n_j, a_j = _unit_normals(grid.face_j)
    assert np.array_equal(geom['n_hat_i'], n_i)
    assert np.array_equal(geom['area_i'], a_i)
    assert np.array_equal(geom['n_hat_j'], n_j)
    assert np.array_equal(geom['area_j'], a_j)
    n_out_ref, _ = _unit_normals(grid.face_i[-1])
    assert np.array_equal(geom['n_out_hat'], n_out_ref), (
        'n_out_hat, _unit_normals(face_i[-1]) ile bit-özdeş değil — '
        'çıkış BC yanlış normalle besleniyor')
    wall_ref, _ = _unit_normals(grid.face_j[:, -1])
    assert np.array_equal(geom['wall_n_hat'], wall_ref), (
        'wall_n_hat, _unit_normals(face_j[:, -1]) ile bit-özdeş değil — '
        'duvar aynası/akısı yanlış normalle besleniyor')


def test_hoist_bit_ozdesligi():
    """geom=None (çağrı içi hesap) ile geom verili KALINTI bit-özdeş
    (geom= bağlantı yolunun bekçisi; fonksiyon içi sözleşme yukarıda)."""
    grid, U = _kucuk_vaka()
    geom = precompute_geometry(grid)
    d1, a1 = residual_axisym(U, grid, LULE_GAMMA, LULE_R, LULE_P0, LULE_T0,
                             Pb=2.75e6)
    d2, a2 = residual_axisym(U, grid, LULE_GAMMA, LULE_R, LULE_P0, LULE_T0,
                             Pb=2.75e6, geom=geom)
    assert np.array_equal(d1, d2), (
        'hoist kalıntıyı DEĞİŞTİRDİ — precompute_geometry çağrı-içi '
        'hesapla bit-özdeş olmalıydı (dilimleme sırası bozulmuş olabilir)')
    for k in a1:
        assert a1[k] == a2[k], f'hoist aux alanını değiştirdi: {k}'


#: numba bu ortamda ithal EDİLEBİLİR mi? (ürün bayrağı değil, kurulum)
#: kernels.NUMBA_AVAILABLE üç ayrı durumu tek bayrakta topluyor: kurulu değil /
#: ortam değişkeniyle kapatılmış / kurulu ve açık. Atlama gerekçesi eskiden
#: hepsine "numba kurulu değil" diyordu — ölçüldü (17 Ağustos 2026):
#: HRMA_CFD_DISABLE_NUMBA=1 ile numba KURULUYKEN atlama gerekçesi yine
#: "numba kurulu değil" çıkıyordu (tests/cfd: 163 passed, 1 skipped).
NUMBA_KURULU = kurulu_mu('numba')


def _numba_atlama_gerekcesi():
    """Atlamanın GERÇEK sebebi. Üç durum ayrı ayrı adlandırılır."""
    if not NUMBA_KURULU:
        return ('numba kurulu değil (find_spec ile DOĞRULANDI) — isteğe bağlı '
                'bağımlılık, NumPy yolu diğer bekçilerle sınanıyor')
    if kernels.NUMBA_DISABLED_BY_ENV:
        return ('HRMA_CFD_DISABLE_NUMBA=1 ile BİLEREK kapatıldı; numba '
                'KURULU — kurulum sorunu YOK')
    return ('numba KURULU ve açık; bu atlama hiç tetiklenmemeli — '
            'tetiklendiyse kernels.NUMBA_AVAILABLE yalan söylüyor')


NUMBA_ATLAMA_GEREKCESI = _numba_atlama_gerekcesi()


@pytest.mark.skipif(not kernels.NUMBA_AVAILABLE,
                    reason=NUMBA_ATLAMA_GEREKCESI)
def test_numba_numpy_aki_bit_ozdes():
    """Derlenmiş çekirdek == saf NumPy akısı, tüm HLLC dallarını gezen
    rastgele durum kümesinde (tohumlu; ölçülen fark tam 0,0)."""
    rng = np.random.default_rng(42)
    n = 20000
    rho = rng.uniform(0.01, 10.0, n)
    p = rng.uniform(1e2, 1e7, n)
    uz = rng.uniform(-2000.0, 2000.0, n)
    ur = rng.uniform(-2000.0, 2000.0, n)
    w_l = np.stack([rho, uz, ur, p], axis=-1)
    w_r = np.stack([np.roll(rho, 1), np.roll(uz, 3), np.roll(ur, 5),
                    np.roll(p, 7)], axis=-1)
    th = rng.uniform(0.0, 2.0 * np.pi, n)
    n_hat = np.stack([np.cos(th), np.sin(th)], axis=-1)
    area = rng.uniform(1e-6, 1.0, n)
    f_np = _directional_flux_numpy(w_l, w_r, n_hat, area, LULE_GAMMA)
    f_nb = kernels.directional_hllc(w_l, w_r, n_hat, area, LULE_GAMMA)
    fark = np.abs(f_nb - f_np)
    assert float(fark.max()) == 0.0, (
        f'numba çekirdeği NumPy yolundan saptı: maks mutlak fark '
        f'{fark.max():.3e} ({int(np.sum(fark > 0))} yüzde) — işlem sırası '
        f'veya fastmath sözleşmesi bozulmuş; eşik ancak YENİDEN ölçümle '
        f'gevşetilebilir (dosya başı beyanı)')


def test_atlama_gerekcesi_kurulumla_tutarli():
    """Gerekçe "kurulu değil" diyorsa numba GERÇEKTEN kurulu olmamalı.

    Parti 31 / T2-4: gerekçe SABİT bir dizeydi ve üç durumun üçüne de
    "numba kurulu değil" diyordu. HRMA_CFD_DISABLE_NUMBA=1 ile ölçüldü —
    numba kuruluyken bile atlama gerekçesi kurulum yokluğunu iddia ediyordu.
    Bu bekçi, gerekçenin ORTAMDAN türetilmesini zorunlu kılar: sabit dizeye
    dönülürse en az bir ortamda kırmızı verir.
    """
    iddia_kurulu_degil = 'kurulu değil' in NUMBA_ATLAMA_GEREKCESI
    assert iddia_kurulu_degil == (not NUMBA_KURULU), (
        f'atlama gerekçesi ortamla çelişiyor: numba kurulu={NUMBA_KURULU}, '
        f'gerekçe={NUMBA_ATLAMA_GEREKCESI!r}')


def test_numba_kuruluysa_arka_uc_gercekten_acik():
    """T2-4 bekçisi: kurulum VAR + ortam kapatmamış ⇒ yol AÇIK olmalı.

    ``kernels.NUMBA_AVAILABLE`` üç durumu tek bayrakta topluyordu ve
    üstteki bit-özdeşlik bekçisi üçünde de aynı gerekçeyle ("numba kurulu
    değil") atlanıyordu. Bu bekçi üçüncü durumu — numba KURULU, ortam
    değişkeni kapatMAMIŞ, ama içe aktarma yine de başarısız — atlanacak
    değil KIRILACAK hâle getirir.

    Not: numba'nın kendisi CI'da kurulu OLMAK ZORUNDADIR (requirements-dev.txt
    gerekçesine bakınız); aksi hâlde numba↔NumPy bit-özdeşliğini kanıtlayan
    tek bekçi hiçbir yerde koşmaz.
    """
    if not NUMBA_KURULU:
        pytest.skip('numba kurulu değil — isteğe bağlı bağımlılık '
                    '(gerekçe find_spec ile DOĞRULANDI)')
    if kernels.NUMBA_DISABLED_BY_ENV:
        pytest.skip('HRMA_CFD_DISABLE_NUMBA=1 — numba BİLEREK kapatıldı, '
                    'kurulum sorunu değil')
    assert kernels.NUMBA_AVAILABLE, (
        'numba KURULU ve HRMA_CFD_DISABLE_NUMBA kapatmamış olmasına rağmen '
        'kernels.NUMBA_AVAILABLE False — `from numba import njit, prange` '
        'ImportError verdi. Bu bir ÜRÜN/ORTAM KUSURUDUR: çözücü sessizce '
        'NumPy yoluna düşer ve numba↔NumPy bit-özdeşlik bekçisi atlanır '
        '(parti 31 / T2-4).')


def test_env_degiskeni_numbayi_kapatir():
    """HRMA_CFD_DISABLE_NUMBA=1 alt süreçte numba yolunu kapatmalı."""
    kod = ('import os; os.environ["HRMA_CFD_DISABLE_NUMBA"] = "1"; '
           'from hrma.cfd import kernels; '
           'assert kernels.NUMBA_DISABLED_BY_ENV is True; '
           'assert kernels.NUMBA_AVAILABLE is False; print("OK")')
    # cwd depo kökünden türetilir — mutlak makine yolu CI'da yok
    # (FileNotFoundError, koşum 31908552054).
    repo_koku = pathlib.Path(__file__).resolve().parents[2]
    sonuc = subprocess.run([sys.executable, '-c', kod],
                           capture_output=True, text=True, timeout=120,
                           cwd=repo_koku)
    assert sonuc.returncode == 0 and 'OK' in sonuc.stdout, (
        f'ortam değişkeni numba yolunu kapatmadı: '
        f'stdout={sonuc.stdout!r} stderr={sonuc.stderr[-400:]!r}')


def test_sensor_puruzsuz_akista_sessiz(lule_cozumu):
    """İzantropik (şoksuz) çözümde sensör 0 kolon bayraklar — pürüzsüz
    akış sensörsüz yolla bit-özdeş kalır (euler_core beyanı). Şoklu vakada
    > 0 olduğu test_normal_sok'ta kilitli; ikisi birlikte sensörün ne kör
    ne de aşırı hevesli olduğunu kanıtlar."""
    _, res = lule_cozumu
    assert res['shock_sensor_columns'] == 0, (
        f"pürüzsüz akışta sensör {res['shock_sensor_columns']} kolon "
        f'bayrakladı — eşik (SHOCK_SENSOR_THRESHOLD) aşınmış: izantropik '
        f'sonuçlar artık sensörden etkileniyor demektir')
    assert 'shock_sensor_basis' in res and res['shock_sensor_basis']


def test_arka_uc_beyani_gercek(lule_cozumu):
    """kernel_backend beyanı süreçteki gerçek arka ucu söylemeli."""
    _, res = lule_cozumu
    beklenen = 'numba' if kernels.NUMBA_AVAILABLE else 'numpy'
    assert res['kernel_backend'] == beklenen, (
        f"beyan {res['kernel_backend']!r}, gerçek {beklenen!r} — arka uç "
        f'beyanı yalan söylüyor (dürüstlük sözleşmesi)')
    assert 'kernel_backend_basis' in res and res['kernel_backend_basis']
