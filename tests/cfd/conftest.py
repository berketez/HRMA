# tests/cfd — ortak analitik lüle vakası ve paylaşılan kararlı-hâl çözümü
"""
İzantropik lüle ve korunum bekçilerinin ORTAK vakası: analitik, testin
kendi tanımladığı kosinüs geçişli yakınsak-ıraksak kontur (motor sonucuna
bağımlılık YOK) + tam süpersonik çalışma noktası.

Kararlı-hâl çözümü pahalı olduğundan session kapsamında BİR kez koşulur ve
iki test dosyası aynı çözümü sorgular (süit disiplini: hedefli, tekrarsız).

Vaka sabitleri LULE_ önekiyle adlandırılır: γ=1,2 roket gazı sınıfıdır ve
depodaki diğer test sabitleriyle kavram karışmasın diye önek zorunludur.
"""

import numpy as np
import pytest

# Çalışma noktası (roket sınıfı, kalorik mükemmel gaz)
LULE_GAMMA = 1.2
LULE_R = 350.0          # J/(kg·K)
LULE_P0 = 4.0e6         # Pa
LULE_T0 = 3200.0        # K
LULE_PB = 2.0e3         # Pa — derin eksik-genleşme: lüle içi tam süpersonik

# Aşırı-genişlemiş vaka (basamak 3): arka basınç, analitik 1B çözümde iç
# normal şoku ıraksak bölgenin ortası civarına koyar (şok-boğazda çıkış
# basıncı 3,87 MPa, şok-çıkışta 1,83 MPa — ÖLÇÜLDÜ; 2,75 MPa bandın içi).
LULE_PB_SOK = 2.75e6    # Pa

# Analitik kontur (m): kosinüs geçişli, iki uçta sıfır eğim
LULE_L_CONV = 0.12
LULE_L_DIV = 0.18
LULE_R_CHAMBER = 0.040
LULE_R_THROAT = 0.025
LULE_R_EXIT = 0.040

# Izgara (test çözünürlüğü — performans koşusu ayrı, raporda)
LULE_NI = 120
LULE_NJ = 24

# ---------------------------------------------------------------------------
# Vaka sözleşmeleri: çözücü ayarları VAKAYA aittir, ızgaraya değil.
#
# İki vaka vardır (bu dizindeki bekçilerin koştuğu vakalar):
#   izantropik — test_izantropik_lule.py + test_korunum.py (Pb=LULE_PB,
#       derin yakınsama: korunum bütçesi 1e-10 sınıfını ölçer),
#   şoklu      — test_normal_sok.py + test_cozunurluk.py ince basamağı
#       (Pb=LULE_PB_SOK; 1e-10 sınıfı BİLEREK hedeflenmez, gerekçe
#       sok_cozumu docstring'inde).
# Ayarlar burada TEK kez yazılır; ızgara boyu ayrı eksendir (aşağıdaki
# referans kayıtları aynı sözleşmeyi iki çözünürlükte koşar).
# ---------------------------------------------------------------------------
IZANTROPIK_COZUCU = dict(P0=LULE_P0, T0=LULE_T0, gamma=LULE_GAMMA, R=LULE_R,
                         Pb=LULE_PB, max_iters=30000, tol_res=1e-10,
                         settle_tol=1e-11)
SOK_COZUCU = dict(P0=LULE_P0, T0=LULE_T0, gamma=LULE_GAMMA, R=LULE_R,
                  Pb=LULE_PB_SOK, max_iters=40000, tol_res=2e-6,
                  settle_tol=1e-6)

#: Euler yolunun BİT-ÖZDEŞLİK regresyon sözleşmesinin dört referans vakası
#: (viskoz tasarım belgesi §11.3: "60×12 ve 120×24, izantropik + şoklu").
#: TEK KAYNAK: oturum fikstürleri (lule_cozumu/sok_cozumu), dondurma betiği
#: (tools/cfd_referans_dondur.py) ve bekçi (test_euler_bit_ozdesligi.py)
#: kurulumu buradan okur — kopya kurulum yazılmaz.
#:
#: ÖLÇÜLDÜ (M4 Max, numba 0.61 arka ucu, 2026-08-18 — dondurma koşusunun
#: kendi çıktısı; kaba basamaklar bu parti için ilk kez koşuldu):
#:   izantropik  60×12 : conv @  8874 iter,  5,3 s, kalıntı 9,947e-11
#:   izantropik 120×24 : conv @  9011 iter,  8,7 s, kalıntı 7,297e-12
#:   şoklu       60×12 : conv @ 26896 iter, 13,5 s, kalıntı 1,994e-6
#:   şoklu      120×24 : conv @ 21870 iter, 19,0 s, kalıntı 1,382e-6
#: İnce basamakların 15 Ağustos ölçümleri (8972 iter / ~29500 iter,
#: aşağıdaki fikstür docstring'lerinde) BU KOŞUMLA KAYMIŞTIR: 16-17 Ağustos
#: partileri steady.py'yi değiştirdi (satır-örtük yol + sınırlayıcı
#: dondurma ayarları). Kayma hüküm eşiklerini bozmadı (tests/cfd 235/235
#: yeşil), ama iterasyon sayısı ARTIK dondurulmuştur: bit-özdeşlik bekçisi
#: künyedeki iterasyon sayısını da karşılaştırır.
#: Kaba şok basamağında test_cozunurluk.py'nin gevşek merdiven ayarı
#: (tol_res=1e-5) DEĞİL, vakanın kendi sözleşmesi (2e-6) kullanılır: ölçüldü,
#: ikisi de yakınsıyor (1e-5 ile 24899 iter / 12,9 s), ama regresyon
#: sözleşmesinde ızgara TEK değişken kalsın diye vaka ayarı korunur.
EULER_REFERANS_VAKALARI = {
    'izantropik_60x12': {'ni': 60, 'nj': 12, 'cozucu': IZANTROPIK_COZUCU},
    'izantropik_120x24': {'ni': LULE_NI, 'nj': LULE_NJ,
                          'cozucu': IZANTROPIK_COZUCU},
    'sok_60x12': {'ni': 60, 'nj': 12, 'cozucu': SOK_COZUCU},
    'sok_120x24': {'ni': LULE_NI, 'nj': LULE_NJ, 'cozucu': SOK_COZUCU},
}


def lule_duvar_yaricapi(z):
    """Analitik duvar r_w(z): kosinüs yakınsak + kosinüs ıraksak [m]."""
    z = np.asarray(z, dtype=float)
    conv = LULE_R_THROAT + (LULE_R_CHAMBER - LULE_R_THROAT) * (
        0.5 + 0.5 * np.cos(np.pi * np.clip(z, 0.0, LULE_L_CONV)
                           / LULE_L_CONV))
    div = LULE_R_THROAT + (LULE_R_EXIT - LULE_R_THROAT) * (
        0.5 - 0.5 * np.cos(np.pi * np.clip(z - LULE_L_CONV, 0.0, LULE_L_DIV)
                           / LULE_L_DIV))
    return np.where(z < LULE_L_CONV, conv, div)


def lule_gridi(ni, nj):
    """Analitik konturdan (ni, nj) eksenel simetrik ızgara."""
    from hrma.cfd.grid_axisym import build_grid_from_wall

    z_nodes = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, ni + 1)
    return build_grid_from_wall(z_nodes, lule_duvar_yaricapi(z_nodes), nj)


def euler_referans_coz(kunye):
    """EULER_REFERANS_VAKALARI[kunye] vakasını koşar: (grid, sonuç).

    Kurulumun TEK gerçeklemesi burasıdır: fikstürler, dondurma betiği ve
    bit-özdeşlik bekçisi aynı çağrıdan geçer; ayrı kurulum yazan bir
    çağıran ayrı sonuç üretir ve sözleşme sessizce kayar.
    """
    from hrma.cfd.steady import solve_steady_axisym

    vaka = EULER_REFERANS_VAKALARI[kunye]
    grid = lule_gridi(vaka['ni'], vaka['nj'])
    return grid, solve_steady_axisym(grid, **vaka['cozucu'])


@pytest.fixture(scope='session')
def lule_cozumu():
    """Paylaşılan kararlı-hâl çözümü: (grid, sonuç sözlüğü).

    Derin yakınsama ayarı: korunum bütçesi bekçisi 1e-10 sınıfını ölçer
    (tasarım belgesi basamak 4). ÖLÇÜLDÜ (M4 Max, 2026-08-15): 8972
    iterasyon, ~15 s; kalıntı 6,9e-12'ye indi. Ayarlar IZANTROPIK_COZUCU'da.
    """
    return euler_referans_coz('izantropik_120x24')


@pytest.fixture(scope='session')
def sok_cozumu():
    """Aşırı-genişlemiş (iç normal şoklu) kararlı-hâl çözümü: (grid, sonuç).

    Basamak 3 + eksen sağlığı + çözünürlük merdiveninin ince basamağı bu
    çözümü paylaşır (süit disiplini). Eşikler ÖLÇÜMDEN (M4 Max,
    2026-08-15, 120×24): tol_res=2e-6 ile ~29500 iterasyonda converged=True,
    kütle artığı 4,5e-7, ~27 s (numba arka ucu). İzantropik vakanın 1e-10
    sınıfı burada hedeflenmez: şok ardı ses-altı bölgede dalgalar şok ile
    çıkış arasında gidip gelir, oturma ölçülür biçimde yavaştır (40000
    iterde kalıntı 3,4e-7 — inişte ama test bütçesi bunu beklemez; beyanlı).
    Ayarlar SOK_COZUCU'da.
    """
    return euler_referans_coz('sok_120x24')
