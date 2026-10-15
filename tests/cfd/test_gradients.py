# tests/cfd — düzlemsel Green-Gauss hücre gradyanı + yüz gradyanı bekçileri
"""
Doğrulama merdiveni (docs/mimari/cfd-viskoz-tasarimi.md §7) BASAMAK 2 ve 3.

  Basamak 2 — serbest akım korunumu: düzgün (sabit) alanda ∇φ makine
  sıfırı. Bu bekçi YENİ bir geometrik iddia getirmez: tests/cfd/test_grid.py
  içindeki ``test_duzlemsel_kapanis`` (satır 71-78) kapalı hücre çevresinde
  Σ S_düzlem = 0 özdeşliğini zaten kilitliyor; Green-Gauss sabit alanda
  φ·(Σ S)/A verdiğinden buradaki sıfır, ORADAKİ özdeşliğin sayısal
  yankısıdır (tasarım belgesi §5.2). İki bekçi birlikte okunur: kapanış
  bozulursa ikisi birden kırmızıya döner.

  Basamak 3 — gradyan tamlığı: doğrusal alanda ∇φ TAM. Çarpık hücrede de
  sınanır ve çarpıklık UYDURULMAZ: ızgara gerçek motor iç konturundan
  (hrma.engines.nozzle_design.sample_nozzle_inner_contour) ve testin
  conftest'teki gerçek kosinüs geçişli lüle konturundan kurulur.

Ek olarak §5.2'nin "düzeltme terimi olmadan çift-tek (odd-even) ayrışması
görülür" iddiası SAYIYLA ölçülür: düzeltmesiz yüz gradyanı hücre-hücre
salınan moda kördür (ölçülen körlük oranı testin içinde raporlanır).

DÜRÜSTLÜK NOTU (bekçinin ısırmadığı yer): hücre gradyanları yakınsakken
doğrusal alanda düzeltmeli ve düzeltmesiz yüz gradyanı EŞİT derecede tamdır
— düzeltmenin değeri orada değil, çift-tek modundadır. Bu da ayrı bir
bekçiyle (negatif kanıt) kayda geçirilir ki "düzeltme doğrusal alanda
kurtarıyor" diye yanlış bir iddia doğmasın.
"""

import ast
import dataclasses
import inspect

import numpy as np
import pytest

from hrma.cfd import gradients as grad_mod
from hrma.cfd.gradients import (
    BoundaryFaceValues,
    MAX_SKEW_ITERS,
    cell_centroids,
    face_gradients,
    face_midpoints,
    green_gauss_gradient,
    interpolate_to_faces,
)
from hrma.cfd.grid_axisym import AxisymGrid, build_grid_from_wall, build_nozzle_grid
from hrma.engines.nozzle_design import sample_nozzle_inner_contour

from .conftest import LULE_L_CONV, LULE_L_DIV, lule_duvar_yaricapi

# Doğrusal deneme alanı φ = C + A·z + B·r (SI ölçeğinde keyfi katsayılar)
LIN_A = 3.0
LIN_B = -7.0
LIN_C = 1.25
LIN_SCALE = float(np.hypot(LIN_A, LIN_B))


def _lin(z, r):
    return LIN_C + LIN_A * np.asarray(z) + LIN_B * np.asarray(r)


def _lule_grid(ni, nj):
    """conftest'in GERÇEK kosinüs geçişli lüle konturu (uydurma ızgara yok)."""
    z = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, ni + 1)
    return build_grid_from_wall(z, lule_duvar_yaricapi(z), nj)


def _motor_grid(ni, nj):
    """GERÇEK motor iç konturu (nozzle_design örnekleyicisi) → ızgara."""
    points, _meta = sample_nozzle_inner_contour({})
    return build_nozzle_grid(points, ni=ni, nj=nj)


def _dirichlet(grid, fn):
    """Sınır yüzlerinde ORTA NOKTA değerleri (düz kenarda tam integral)."""
    mid_i, mid_j = face_midpoints(grid)
    return BoundaryFaceValues(
        i_lo=fn(mid_i[0, :, 0], mid_i[0, :, 1]),
        i_hi=fn(mid_i[-1, :, 0], mid_i[-1, :, 1]),
        j_lo=fn(mid_j[:, 0, 0], mid_j[:, 0, 1]),
        j_hi=fn(mid_j[:, -1, 0], mid_j[:, -1, 1]))


def _skewness(grid):
    """Çarpıklık: |yüz orta noktası − merkez çifti orta noktası| / |LR|."""
    xc = cell_centroids(grid)
    mid_i, mid_j = face_midpoints(grid)
    d_i = mid_i[1:-1] - 0.5 * (xc[:-1] + xc[1:])
    l_i = np.linalg.norm(xc[1:] - xc[:-1], axis=-1)
    d_j = mid_j[:, 1:-1] - 0.5 * (xc[:, :-1] + xc[:, 1:])
    l_j = np.linalg.norm(xc[:, 1:] - xc[:, :-1], axis=-1)
    return (float(np.max(np.linalg.norm(d_i, axis=-1) / l_i)),
            float(np.max(np.linalg.norm(d_j, axis=-1) / l_j)))


# --------------------------------------------------------------------------
# BASAMAK 2 — serbest akım korunumu (Σ S = 0 bekçisinin sayısal yankısı)
# --------------------------------------------------------------------------

def test_duzgun_alanda_gradyan_makine_sifiri():
    """Sabit alanda ∇φ = φ·(Σ S_düzlem)/A → makine sıfırı.

    Bağlantı: tests/cfd/test_grid.py::test_duzlemsel_kapanis aynı Σ S = 0
    özdeşliğini GEOMETRİK olarak kilitler (1e-13·|S| bandı). Buradaki eşik
    onun operatör tarafındaki karşılığıdır: gradyan ölçeği φ/h olduğundan
    bağıl hata |∇φ|·h/φ ile ölçülür.
    """
    phi0 = 3.7e5
    for grid in (_lule_grid(120, 24), _motor_grid(48, 10)):
        phi = np.full((grid.ni, grid.nj), phi0)
        bc = _dirichlet(grid, lambda z, r: np.full(np.shape(z), phi0))
        grad, info = green_gauss_gradient(grid, phi, bc=bc, return_info=True)
        h = float(np.sqrt(np.min(grid.area_planar)))
        rel = float(np.max(np.abs(grad))) * h / phi0
        assert rel < 1e-14, (
            f'düzgün alanda gradyan sıfır değil (bağıl {rel:.3e}): '
            f'Σ S_düzlem = 0 kapanışı ya da yüz değerleri bozuk — '
            f'test_grid.py::test_duzlemsel_kapanis ile birlikte okunur')
        assert info['converged']


def test_duzgun_alanda_sinir_degeri_verilmeden_de_sifir():
    """bc=None (bir-yanlı uzatma) yolunda da serbest akım korunur.

    Uzatma kipi φ_yüz = φ_C + ∇φ_C·(x_yüz − x_C) kullanır; sabit alanda
    ∇φ_C = 0 olduğundan yüz değeri φ_C'dir ve toplam yine φ·Σ S/A olur.
    """
    phi0 = -812.5
    grid = _lule_grid(60, 12)
    phi = np.full((grid.ni, grid.nj), phi0)
    grad = green_gauss_gradient(grid, phi)
    h = float(np.sqrt(np.min(grid.area_planar)))
    rel = float(np.max(np.abs(grad))) * h / abs(phi0)
    assert rel < 1e-14, f'uzatmalı yolda serbest akım bozuldu ({rel:.3e})'


# --------------------------------------------------------------------------
# BASAMAK 3 — doğrusal alanda gradyan TAM (çarpık hücrede de)
# --------------------------------------------------------------------------

def test_dogrusal_alanda_gradyan_tam():
    """Gerçek motor konturu ızgarasında ∇φ = (A, B) makine hassasiyetinde."""
    grid = _motor_grid(48, 10)
    phi = _lin(grid.z_centers, grid.r_centers)
    grad, info = green_gauss_gradient(grid, phi, bc=_dirichlet(grid, _lin),
                                      return_info=True)
    rel = float(np.max(np.abs(grad - np.array([LIN_A, LIN_B])))) / LIN_SCALE
    assert rel < 1e-11, (
        f'doğrusal alanda gradyan tam değil (bağıl {rel:.3e}) — '
        f'{info["skew_iters_used"]} çarpıklık süpürmesi')
    assert info['converged'] and info['skew_iters_used'] <= MAX_SKEW_ITERS


def test_carpik_hucrede_dogrusal_alan_tam_ve_duzeltmenin_isirigi():
    """Çarpıklığı ÖLÇÜLEN gerçek kontur ızgarasında tamlık + düzeltmenin payı.

    Izgara uydurma değil: sample_nozzle_inner_contour konturu 30×40 ile
    örneklendiğinde j-yönü çarpıklığı ölçülür (≈0,37 sınıfı) — düzeltmesiz
    düzlemsel Green-Gauss burada %10 sınıfında sapar.
    """
    grid = _motor_grid(30, 40)
    skew_i, skew_j = _skewness(grid)
    assert skew_j > 0.2, (
        f'bu ızgara yeterince çarpık değil (j çarpıklığı {skew_j:.3f}); '
        f'bekçi kolay vakaya kaymış olur')
    phi = _lin(grid.z_centers, grid.r_centers)
    bc = _dirichlet(grid, _lin)
    ref = np.array([LIN_A, LIN_B])

    grad, info = green_gauss_gradient(grid, phi, bc=bc, return_info=True)
    rel_ok = float(np.max(np.abs(grad - ref))) / LIN_SCALE

    grad_ham = green_gauss_gradient(grid, phi, bc=bc, skew_iters=0)
    rel_ham = float(np.max(np.abs(grad_ham - ref))) / LIN_SCALE

    # DEFAULT_SKEW_TOL / MAX_SKEW_ITERS seçimi ÖLÇÜME kilitli: bu en çarpık
    # vakada durma ölçütü yuvarlama tabanının (bağıl 1,1e-13) üstünde
    # kalmalı, yoksa adaptif kip hiç tetiklenmez ve sınırı boşa yakar.
    assert info['converged'] and info['skew_iters_used'] < MAX_SKEW_ITERS, (
        f'adaptif kip en çarpık ızgarada durmuyor: '
        f'{info["skew_iters_used"]} süpürme, son bağıl güncelleme '
        f'{info["last_update_rel"]:.3e} — DEFAULT_SKEW_TOL yuvarlama '
        f'tabanının altına düşmüş olabilir')
    _grad_uz, info_uz = green_gauss_gradient(grid, phi, return_info=True)
    assert info_uz['converged'], (
        f'uzatmalı kip en çarpık ızgarada MAX_SKEW_ITERS içinde yakınsamadı '
        f'({info_uz["last_update_rel"]:.3e})')

    assert rel_ok < 1e-11, (
        f'çarpık hücrede doğrusal alan tam değil (bağıl {rel_ok:.3e}; '
        f'çarpıklık i={skew_i:.3f} j={skew_j:.3f})')
    assert rel_ham > 1e-2, (
        f'düzeltmesiz (skew_iters=0) biçim bu ızgarada sapmıyor '
        f'({rel_ham:.3e}) — bekçi düzeltmenin payını ölçemez hâle gelmiş')
    assert rel_ham / max(rel_ok, 1e-300) > 1e8, (
        f'düzeltmenin ısırığı ölçülemedi: düzeltmesiz {rel_ham:.3e} / '
        f'düzeltmeli {rel_ok:.3e}')


def test_sinir_degeri_verilmeden_dogrusal_alan_tam():
    """bc=None uzatma kipi de doğrusal alanda TAM (yalnız yavaş yakınsar).

    ÖLÇÜM: uzatmalı kipin süpürme başına daralma oranı ≈0,5 (Dirichlet
    kipinde ≈1e-2). Bu yüzden MAX_SKEW_ITERS uzatma kipine göre seçilmiştir;
    çözücü (V1) fiziksel sınır değerlerini DAİMA verir, hızlı yol odur.
    """
    grid = _lule_grid(60, 12)
    phi = _lin(grid.z_centers, grid.r_centers)
    grad, info = green_gauss_gradient(grid, phi, return_info=True)
    rel = float(np.max(np.abs(grad - np.array([LIN_A, LIN_B])))) / LIN_SCALE
    assert rel < 1e-10, (
        f'uzatmalı sınır kipinde doğrusal alan tam değil ({rel:.3e}, '
        f'{info["skew_iters_used"]} süpürme)')
    assert info['converged'], (
        f'uzatmalı kip MAX_SKEW_ITERS={MAX_SKEW_ITERS} içinde yakınsamadı '
        f'(son bağıl güncelleme {info["last_update_rel"]:.3e})')


# --------------------------------------------------------------------------
# YÜZ GRADYANI — Blazek §5.3.2 düzeltmeli ortalama
# --------------------------------------------------------------------------

def test_yuz_gradyani_dogrusal_alanda_tam():
    """Düzeltmeli yüz gradyanı iç ve SINIR yüzlerinde doğrusal alanı verir."""
    grid = _motor_grid(48, 10)
    phi = _lin(grid.z_centers, grid.r_centers)
    bc = _dirichlet(grid, _lin)
    g_i, g_j = face_gradients(grid, phi, bc=bc, corrected=True)
    ref = np.array([LIN_A, LIN_B])
    assert g_i.shape == (grid.ni + 1, grid.nj, 2)
    assert g_j.shape == (grid.ni, grid.nj + 1, 2)
    rel = max(float(np.max(np.abs(g_i - ref))),
              float(np.max(np.abs(g_j - ref)))) / LIN_SCALE
    assert rel < 1e-11, f'yüz gradyanı doğrusal alanda tam değil ({rel:.3e})'


def test_yuz_duzeltmesi_dogrusal_alanda_ISIRMAZ_negatif_kanit():
    """DÜRÜSTLÜK BEKÇİSİ: hücre gradyanları tamken düzeltmesiz biçim de tam.

    Düzeltmenin gerekçesi doğrusal tamlık DEĞİL, çift-tek modudur (bir
    sonraki bekçi). Bu negatif kanıt, ileride "düzeltme doğrusal alanı
    kurtarıyor" diye yanlış bir iddia yazılmasını engeller.
    """
    grid = _motor_grid(48, 10)
    phi = _lin(grid.z_centers, grid.r_centers)
    bc = _dirichlet(grid, _lin)
    ref = np.array([LIN_A, LIN_B])
    g_i, g_j = face_gradients(grid, phi, bc=bc, corrected=False)
    rel = max(float(np.max(np.abs(g_i - ref))),
              float(np.max(np.abs(g_j - ref)))) / LIN_SCALE
    assert rel < 1e-11, (
        f'düzeltmesiz yüz gradyanı doğrusal alanda sapıyor ({rel:.3e}) — '
        f'beklenen davranış bu DEĞİL: hücre gradyanı tamken ortalama da '
        f'tamdır; sapma varsa hücre gradyanı yakınsamamıştır')


def test_cift_tek_modu_duzeltmesiz_gorulmez():
    """§5.2 iddiasının SAYISAL kanıtı: düzeltmesiz yüz gradyanı (−1)^i moduna kör.

    Yüksek en-boy oranlı (Δr/Δz ölçülür) gerçek kontur ızgarasında alan
    'doğrusal + hücre-hücre salınan mod' olarak kurulur. Düzeltmeli biçim
    modu tam kompakt farkla (2ε/|LR|) görür; düzeltmesiz biçim körlük
    oranı kadar sönümsüz bırakır → çift-tek ayrışması.
    """
    grid = _lule_grid(400, 4)
    eps = 1.0
    mod = eps * ((-1.0) ** np.arange(grid.ni))[:, None] * np.ones((grid.ni,
                                                                   grid.nj))
    phi = _lin(grid.z_centers, grid.r_centers) + mod
    bc = _dirichlet(grid, _lin)          # sınırlarda mod yok

    dz = float(np.min(np.diff(grid.Z[:, 0])))
    dr = float(np.min(np.diff(grid.R[0, :])))
    en_boy = dr / dz
    assert en_boy > 5.0, f'ızgara yeterince ince-uzun değil (en-boy {en_boy:.2f})'

    # ÖLÇÜM YALNIZ İÇ YÜZLERDE: çift-tek ayrışması iç şablonun sorunudur.
    # (Sınır yüzleri tek-yanlı kompakt farkla zaten modu görür; onları
    # ortalamaya katmak bekçiyi körleştiriyordu — M2 mutasyonunda ölçüldü.)
    n_hat = grid.face_i_planar[1:-1] / np.linalg.norm(
        grid.face_i_planar[1:-1], axis=-1)[..., None]
    dn_lin = np.sum(np.array([LIN_A, LIN_B]) * n_hat, axis=-1)
    genlik = {}
    for corr in (True, False):
        g_i, _g_j = face_gradients(grid, phi, bc=bc, corrected=corr)
        dn = np.sum(g_i[1:-1] * n_hat, axis=-1)
        genlik[corr] = float(np.max(np.abs(dn - dn_lin)))

    kompakt = 2.0 * eps / dz
    assert abs(genlik[True] - kompakt) / kompakt < 0.05, (
        f'düzeltmeli biçim modu kompakt farkla görmüyor: '
        f'{genlik[True]:.4e} vs 2ε/Δz={kompakt:.4e}')
    oran = genlik[True] / max(genlik[False], 1e-300)
    assert oran > 1e3, (
        f'düzeltmesiz biçim modu görüyor (körlük oranı {oran:.3e}) — '
        f'çift-tek bekçisi ısırmıyor: düzeltmeli {genlik[True]:.4e}, '
        f'düzeltmesiz {genlik[False]:.4e}')


def test_duzeltmeli_yuz_gradyani_kompakt_farki_birebir_verir():
    """Cebirsel kimlik: düzeltmeli yüz gradyanının t̂ bileşeni = (φ_R−φ_L)/|LR|.

    Blazek §5.3.2 düzeltmesi tam olarak bu bileşeni değiştirir; kimlik
    makine sıfırı sınıfında sağlanmalıdır (alan ne olursa olsun).
    """
    rng = np.random.default_rng(20260818)
    grid = _lule_grid(60, 12)
    phi = rng.normal(0.0, 1.0, (grid.ni, grid.nj))
    xc = cell_centroids(grid)
    g_i, g_j = face_gradients(grid, phi, corrected=True)

    d = xc[1:] - xc[:-1]
    L = np.linalg.norm(d, axis=-1)
    t = d / L[..., None]
    proj = np.sum(g_i[1:-1] * t, axis=-1)
    kompakt = (phi[1:] - phi[:-1]) / L
    olcek = float(np.max(np.abs(kompakt)))
    assert float(np.max(np.abs(proj - kompakt))) < 1e-12 * olcek

    d = xc[:, 1:] - xc[:, :-1]
    L = np.linalg.norm(d, axis=-1)
    t = d / L[..., None]
    proj = np.sum(g_j[:, 1:-1] * t, axis=-1)
    kompakt = (phi[:, 1:] - phi[:, :-1]) / L
    olcek = float(np.max(np.abs(kompakt)))
    assert float(np.max(np.abs(proj - kompakt))) < 1e-12 * olcek


# --------------------------------------------------------------------------
# YAPISAL — "yeni metrik üretme" kuralı ve girdi reddi
# --------------------------------------------------------------------------

def test_yeni_metrik_uretilmedi():
    """gradients.py yalnız AxisymGrid'in MEVCUT alanlarını okur.

    Tasarım belgesi §5.2: gerekli iki büyüklük (face_i_planar,
    face_j_planar) ızgarada ZATEN var. Bu bekçi, ileride ızgaraya sessizce
    yeni metrik alanı eklenmesini (ya da gradyan modülünün ızgarayı
    değiştirmesini) yapısal olarak yakalar.
    """
    # METRİK alanlar DONDURULMUŞTUR (kural bunlar içindir). Beyan alanları
    # (V2, §5.7 radyal dağılım künyesi) metrik DEĞİLDİR ve ayrı tutulur —
    # ayrı tutulmasalardı "yeni metrik eklendi" kuralı, beyan eklemekle
    # metrik eklemeyi ayırt edemez ve ya kör kalır ya yanlış alarm verirdi.
    metrik = {
        'Z', 'R', 'area_planar', 'volume', 'face_i', 'face_j',
        'face_i_planar', 'face_j_planar', 'z_centers', 'r_centers',
        'ni', 'nj'}
    # wall_collar (V1b, parti 39 A4) da BEYANDIR: duvar-normal yakanın
    # künyesi (katman sayıları, ulaşılan normal kalınlık, harman ölçüleri).
    # Gradyan katmanı onu OKUMAZ — düğüm konumları zaten Z/R'de, yani yeni
    # bir metrik ALANI doğmamıştır; aşağıdaki AST bekçisi bunu ayrıca
    # ölçer (grid.<alan> okumaları dondurulmuş kümenin içinde kalır).
    beyan = {'radial_distribution', 'radial_stretch', '_basis',
             'wall_collar'}
    izinli = {f.name for f in dataclasses.fields(AxisymGrid)}
    assert izinli == metrik | beyan, (
        'AxisymGrid alan kümesi değişmiş: gradyan katmanı yeni metrik '
        'üretmeme kuralını ancak dondurulmuş kümeye karşı bekçileyebilir '
        f'(fazla: {sorted(izinli - (metrik | beyan))}, '
        f'eksik: {sorted((metrik | beyan) - izinli)})')

    agac = ast.parse(inspect.getsource(grad_mod))
    okunan = {n.attr for n in ast.walk(agac)
              if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
              and n.value.id == 'grid'}
    assert okunan <= metrik, (
        'gradients.py ızgarada METRİK OLMAYAN (ya da hiç olmayan) alan '
        f'okuyor: {sorted(okunan - metrik)}')
    assert {'face_i_planar', 'face_j_planar'} <= okunan, (
        'düzlemsel yüzey vektörleri kullanılmıyor — operatör 2π ağırlıklı '
        'yüzeylere kaymış olabilir (tasarım belgesi §5.2 düzlemsel ister)')
    yasak = {'face_i', 'face_j', 'volume'} & okunan
    assert not yasak, (
        f'gradyan operatörü 2π ağırlıklı/dönel metrik okuyor: {sorted(yasak)} '
        f'— §5.2 gradyanın DÜZLEMSEL olmasını ister (dönel ağırlık gerilme '
        f'tensörünün kendisine değil, akı toplamına girer)')


def test_gecersiz_girdi_reddedilir():
    """Boyut/kip hataları sessiz yayılmaz (fail-closed)."""
    grid = _lule_grid(20, 6)
    phi = np.zeros((grid.ni, grid.nj))
    with pytest.raises(ValueError):
        green_gauss_gradient(grid, np.zeros((grid.ni, grid.nj + 1)))
    with pytest.raises(ValueError):
        green_gauss_gradient(grid, phi,
                             bc=BoundaryFaceValues(j_hi=np.zeros(grid.ni + 3)))
    with pytest.raises(ValueError):
        green_gauss_gradient(grid, phi, skew_iters=-1)
    with pytest.raises(ValueError):
        interpolate_to_faces(grid, phi, np.zeros((grid.ni, grid.nj)))
