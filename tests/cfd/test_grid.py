# tests/cfd — eksenel simetrik ızgara metrik sağlığı bekçileri
"""
grid_axisym üreticisinin geometrik doğruluğu:

  (a) Pozitif hacimler ve pozitif düzlemsel alanlar (her hücre).
  (b) Yüzey vektörü kapanışı — eksenel simetrik per-2π biçiminde kapanış
      özdeşliği DÜZLEMSELDEN FARKLIDIR ve testin sözleşmesi budur:
        Σ_dışa S_z = 0            (teleskopik, tam)
        Σ_dışa S_r = 2π·A_düzlem  (Green özdeşliği; basınç kaynak teriminin
                                   serbest-akım korunumunu tam dengeleyen hâli)
      Saf düzlemsel kapanış (Σ (Δr,−Δz) = 0) da ayrıca sınanır.
  (c) Dönel hacim TAMLIĞI: duvarı doğru parçalı (koni) konturda hücre
      hacimleri toplamı analitik kesik koni hacmine makine hassasiyetinde
      eşit olmalı (hacimler seri açılım değil, gerçek dönel hacim).
  (d) Eksen yüzleri: j=0 yüzlerinin alanı sıfır (r_mid=0) — eksen sınırı
      geometrik olarak akısızdır.
  (e) sample_nozzle_inner_contour (mm) yolundan üretim: birim dönüşümü ve
      boğaz/çıkış yarıçaplarının konturla tutarlılığı.
"""

import numpy as np

from hrma.cfd.grid_axisym import build_grid_from_wall, build_nozzle_grid
from hrma.engines.nozzle_design import sample_nozzle_inner_contour

TWO_PI = 2.0 * np.pi


def _cone_grid(ni=16, nj=8, r0=0.05, r1=0.02, length=0.3):
    z = np.linspace(0.0, length, ni + 1)
    r_wall = r0 + (r1 - r0) * z / length
    return build_grid_from_wall(z, r_wall, nj), r0, r1, length


def _nozzle_like_grid(ni=40, nj=12):
    """Analitik yakınsak-ıraksak duvar (kosinüs geçişli) — testin kendi
    konturu, motor sonucuna bağımlılık yok."""
    z = np.linspace(0.0, 0.3, ni + 1)
    r_wall = np.where(
        z < 0.12,
        0.025 + 0.015 * (0.5 + 0.5 * np.cos(np.pi * z / 0.12)),
        0.025 + 0.015 * (0.5 - 0.5 * np.cos(np.pi * (z - 0.12) / 0.18)))
    return build_grid_from_wall(z, r_wall, nj)


def test_pozitif_hacimler_ve_alanlar():
    grid = _nozzle_like_grid()
    assert np.all(grid.area_planar > 0.0), 'negatif/sıfır düzlemsel alan'
    assert np.all(grid.volume > 0.0), 'negatif/sıfır dönel hacim'
    assert np.all(np.isfinite(grid.volume))


def test_yuzey_vektoru_kapanisi():
    """Hücre başına dışa yönlü yüzey vektörleri: z tam kapanır, r bileşeni
    2π·A_düzlem verir (eksenel simetrik Green özdeşliği)."""
    grid = _nozzle_like_grid()
    # dışa yönlü toplam: +Si(i+1) − Si(i) + Sj(j+1) − Sj(j)
    close = (grid.face_i[1:, :, :] - grid.face_i[:-1, :, :]
             + grid.face_j[:, 1:, :] - grid.face_j[:, :-1, :])
    scale = TWO_PI * grid.area_planar
    assert np.max(np.abs(close[:, :, 0])) < 1e-12 * np.max(scale), (
        'S_z kapanışı bozuk: eksenel yüzey vektörleri teleskopik toplamı '
        'sıfır değil')
    rel = np.abs(close[:, :, 1] - scale) / scale
    assert np.max(rel) < 1e-12, (
        f'S_r kapanış özdeşliği bozuk (maks bağıl {np.max(rel):.3e}): '
        f'Σ S_r = 2π·A_düzlem sağlanmıyor — basınç kaynak terimi '
        f'serbest akımı koruyamaz')


def test_duzlemsel_kapanis():
    """r ağırlıksız (saf düzlemsel) yüzey vektörleri her hücrede tam kapanır."""
    grid = _nozzle_like_grid()
    close = (grid.face_i_planar[1:, :, :] - grid.face_i_planar[:-1, :, :]
             + grid.face_j_planar[:, 1:, :] - grid.face_j_planar[:, :-1, :])
    ref = np.max(np.linalg.norm(grid.face_i_planar, axis=-1))
    assert np.max(np.abs(close)) < 1e-13 * ref


def test_koni_hacim_tamligi():
    """Koni duvarlı ızgarada Σ hücre hacmi = π·h/3·(R²+R·r+r²) (tam)."""
    grid, r0, r1, length = _cone_grid()
    v_exact = np.pi * length / 3.0 * (r0 * r0 + r0 * r1 + r1 * r1)
    v_sum = float(np.sum(grid.volume))
    assert abs(v_sum - v_exact) / v_exact < 1e-13, (
        f'dönel hacim tam değil: Σ={v_sum!r}, analitik={v_exact!r} — '
        f'hacimler gerçek dönel hacim olmalı (seri açılım yasak)')


def test_eksen_yuzleri_akisiz():
    grid = _nozzle_like_grid()
    axis_area = np.linalg.norm(grid.face_j[:, 0, :], axis=-1)
    assert np.max(axis_area) == 0.0, (
        'r=0 eksen yüzlerinin alanı sıfır olmalı (r_mid=0): eksen sınırı '
        'geometrik akısızlık kaybedilmiş')


def test_motor_konturundan_izgara():
    """sample_nozzle_inner_contour (mm) → ızgara (m): birim dönüşümü ve
    duvar yarıçaplarının kontur meta değerleriyle tutarlılığı."""
    points, meta = sample_nozzle_inner_contour({})
    grid = build_nozzle_grid(points, ni=48, nj=10)
    # boğaz yarıçapı: ızgara duvarının minimumu, kontur boğazına yakın olmalı
    r_wall = grid.R[:, -1]
    r_throat_grid = float(np.min(r_wall))
    r_throat_meta = meta['r_throat'] * 1e-3
    assert abs(r_throat_grid - r_throat_meta) / r_throat_meta < 0.01, (
        'ızgara duvar minimumu kontur boğazından sapmış (birim/örnekleme '
        'hatası olabilir)')
    # uzunluk: m cinsinden, kontur z aralığıyla aynı
    z_span = grid.Z[-1, 0] - grid.Z[0, 0]
    z_span_meta = (points[-1][0] - points[0][0]) * 1e-3
    assert abs(z_span - z_span_meta) < 1e-12
    assert np.all(grid.volume > 0.0)
