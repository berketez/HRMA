# hrma/cfd — duvar poliçizgisine TAM en yakın mesafe (SA türbülans modelinin d alanı)
"""
Hücre merkezlerinden lüle duvar poliçizgisine kesin en yakın Öklid
mesafesi.

AMAÇ (tasarım belgesi docs/mimari/cfd-viskoz-tasarimi.md §5.5)
--------------------------------------------------------------
Spalart-Allmaras (SA-neg) modelinin yok-etme terimi duvar mesafesi d ile
ölçeklenir (ν̃/d² sınıfı; Spalart & Allmaras, AIAA-92-0439, 1992 —
künye belge §7.2'de doğrulanmış). Belge kararı: d, kontur poliçizgisine
**tam** en yakın nokta mesafesidir. İki kaba yaklaşım AÇIKÇA YASAK:

- ``d = r_duvar(z) − r`` YANLIŞTIR: yakınsak bölgede duvar 42° eğimli
  (belgede ÖLÇÜLDÜ, gerçek kontur örnekleyicisi) → kosinüs kadar sapar.
- Yalnız-düğüm mesafesi (poliçizgi köşelerine en yakın nokta) YANLIŞTIR:
  uzun parçanın ortasına yakın noktada hata parça yarı-boyu mertebesine
  çıkar. Fark testte ÖLÇÜLEREK gösterilir
  (tests/cfd/test_viskoz_duvar_mesafesi.py).

YÖNTEM (künye)
--------------
Nokta-parça (point-segment) kesin mesafe: parça (a→b) üstünde dik
izdüşüm parametresi t = ((p−a)·(b−a))/|b−a|², t ∈ [0,1] aralığına
kelepçelenir (t<0 → uç a, t>1 → uç b); en yakın nokta a + t·(b−a).
Standart hesaplamalı geometri (Ericson, *Real-Time Collision Detection*,
2005, §5.1.2 "closest point on line segment"). Poliçizgi mesafesi tüm
parçalar üstünde minimumdur. Kelepçe sayesinde köşe (iki parçanın ortak
ucu) durumu ayrı dal GEREKTİRMEZ: iki komşu parça da aynı uç noktayı
aday verir.

SÖZLEŞME
--------
- ``point_polyline_distance``: genel (z, r) nokta kümesi → poliçizgi;
  saf geometri, ızgara bilmez.
- ``wall_distance_field(grid)``: ``AxisymGrid``'i YALNIZ OKUR (ithal
  edilmez, değiştirilmez — grid_axisym'e dokunmama sözleşmesi): duvar
  poliçizgisi ``grid.Z[:, -1], grid.R[:, -1]`` (j = nj köşe çizgisi,
  grid_axisym yön kuralı "j ekseni +r"), noktalar hücre merkezleri
  ``grid.z_centers, grid.r_centers``. Dönüş biçimi (ni, nj) [m].
- Sıfır uzunluklu parça → ``ValueError`` (yinelenen poliçizgi düğümü
  girdi kusurudur; sessizce atlanmaz). ``build_grid_from_wall`` z'yi
  kesin artan istediğinden ızgara duvarında yapısal olarak oluşmaz.
- Mesafe işaretsizdir (d ≥ 0): SA'nın d alanı tanım gereği negatif
  olamaz; hücre merkezleri akış bölgesinin içindedir.

Saf NumPy, nokta × parça tam yayınlama (broadcast) ile; işlem sırası
deterministik. ÖLÇÜLDÜ (M4 Max, 2026-08-16, 20 çağrı ortalaması): 120×24
ızgara (2880 hücre × 120 parça) 3,9 ms; 256×64 (16384 hücre × 256 parça)
45,5 ms — SA koşumu başına BİR kez hesaplanan alan için yeterli;
optimizasyon gerekirse sonraki tur (ölç → sonra hızlandır).
"""

import numpy as np

__all__ = ['point_polyline_distance', 'wall_distance_field']


def point_polyline_distance(pz, pr, poly_z, poly_r):
    """(z, r) noktalarından poliçizgiye kesin en yakın Öklid mesafesi.

    Args:
        pz: Nokta z koordinatları [m], herhangi biçim.
        pr: Nokta r koordinatları [m], ``pz`` ile aynı biçim.
        poly_z: Poliçizgi düğüm z'leri [m], 1B, uzunluk >= 2.
        poly_r: Poliçizgi düğüm r'leri [m], ``poly_z`` ile aynı uzunluk.

    Returns:
        Mesafe dizisi, ``pz`` biçiminde [m] (işaretsiz, >= 0).

    Raises:
        ValueError: Biçim/uzunluk sözleşmesi bozuksa, girdide sonlu
            olmayan değer varsa ya da poliçizgide sıfır uzunluklu parça
            varsa (yinelenen düğüm).
    """
    pz = np.asarray(pz, dtype=float)
    pr = np.asarray(pr, dtype=float)
    poly_z = np.asarray(poly_z, dtype=float)
    poly_r = np.asarray(poly_r, dtype=float)
    if pz.shape != pr.shape:
        raise ValueError('pz ve pr aynı biçimde olmalı: '
                         f'{pz.shape} != {pr.shape}.')
    if poly_z.ndim != 1 or poly_z.shape != poly_r.shape:
        raise ValueError('poly_z ve poly_r aynı uzunlukta 1B dizi olmalı.')
    if poly_z.size < 2:
        raise ValueError('Poliçizgi en az 2 düğüm gerektirir.')
    for ad, dizi in (('nokta', pz), ('nokta', pr),
                     ('poliçizgi', poly_z), ('poliçizgi', poly_r)):
        if not np.all(np.isfinite(dizi)):
            raise ValueError(f'{ad} koordinatları sonlu olmalı (NaN/inf).')

    # Parçalar (a→b) ve karesel uzunluklar
    az, ar = poly_z[:-1], poly_r[:-1]
    dz = poly_z[1:] - az
    dr = poly_r[1:] - ar
    l2 = dz * dz + dr * dr
    if np.any(l2 == 0.0):
        raise ValueError('Poliçizgide sıfır uzunluklu parça var '
                         '(yinelenen düğüm) — girdi kusuru, sessizce '
                         'atlanmaz.')

    duz = pz.reshape(-1)
    dur = pr.reshape(-1)
    # Dik izdüşüm parametresi, (P, S); uçlara kelepçe köşe durumunu kapsar
    t = ((duz[:, None] - az) * dz + (dur[:, None] - ar) * dr) / l2
    np.clip(t, 0.0, 1.0, out=t)
    yakin_z = az + t * dz
    yakin_r = ar + t * dr
    d2 = (duz[:, None] - yakin_z) ** 2 + (dur[:, None] - yakin_r) ** 2
    return np.sqrt(d2.min(axis=1)).reshape(pz.shape)


def wall_distance_field(grid):
    """Hücre merkezlerinden ızgara duvar poliçizgisine tam mesafe alanı.

    Args:
        grid: ``hrma.cfd.grid_axisym.AxisymGrid`` (ya da aynı alanları
            taşıyan nesne) — YALNIZ okunur: ``Z``, ``R`` köşeleri
            (duvar = son j sütunu) ve ``z_centers``, ``r_centers``.

    Returns:
        d alanı, biçim (ni, nj) [m] — SA modelinin duvar mesafesi girdisi.
    """
    return point_polyline_distance(grid.z_centers, grid.r_centers,
                                   grid.Z[:, -1], grid.R[:, -1])
