"""
HRMA - Rocket Motor Analysis
"""

import os
import sys

# ÖH D37 fea-hiz — BLAS İŞ PARÇACIĞI VARSAYILANI. Bu blok dosyanın en başında
# durur: numpy/scipy İÇE AKTARILMADAN ÖNCE çalışmalıdır, çünkü OpenBLAS iş
# parçacığı sayısını kütüphane yüklenirken ortamdan bir kez okur. Uygulamanın
# üç giriş yolu da (packaging/launcher.py `_hrma_version`, hrma/run.py,
# hrma/run_windows.py) numpy'den önce `hrma`yı içe aktarır.
#
# NEDEN: FEA seyrek çözücüleri (structural_axisym `spsolve`, thermal_axisym
# `splu`, planar_grain `spsolve`) scipy'nin SuperLU'su üzerinden OpenBLAS'ı
# çağırır. OpenBLAS varsayılanda çekirdek sayısı kadar iş parçacığı açar
# (M4 Max: 14) ve işçiler eğirir. Kontrollü ölçüm (fea-hiz/a1, yüklü makine,
# 5 tur): 8.450 serbestlikli yapısal `spsolve` medyan 1,92 s (en kötü 6,1 s)
# ⟷ 1 iş parçacığıyla 0,095 s; düzlem 1,32 s (en kötü 13,0 s) ⟷ 0,12 s.
# Hafif yükte (~5) de varsayılan 7× yavaş (0,263 ⟷ 0,038 s). 2 ve 4 iş
# parçacığı 1'den hızlı değil, daha çok CPU yakıyor; çıktılar dört ayarda
# bit-aynı. Bedeli: büyük YOĞUN BLAS (1500² matmul + solve) 1 iş
# parçacığında yavaş (hafif yükte 3,3×, yüklüde 1,6×) — ürün yolunda böyle
# işlem yok (yoğun çözümler 3×3 yama ve CFD m×m blok yığınları). Seçim
# gerekçesi ve yan etkiler:
# docs/scofield/raw/OH/D37/fea-hiz/a1/rapor.md.
#
# KAPSAM: yalnız OPENBLAS_NUM_THREADS yazılır. Kullanıcı OpenBLAS'ın okuduğu
# değişkenlerden HERHANGİ birini koymuşsa hiçbir şey yazılmaz: OpenBLAS'ta
# OPENBLAS_NUM_THREADS önceliklidir, kullanıcının OMP/GOTO değerinin yanına
# yazmak o değeri ezerdi. OMP_NUM_THREADS BİLEREK yazılmaz: OpenMP havuzlarına
# (ör. /calculate yolunda yüklenen sklearn libomp) ve alt süreçlere sızardı;
# ölçümde OMP=1 CFD'yi değiştirmedi. VECLIB_MAXIMUM_THREADS yazılmaz: bu
# kurulumda Accelerate yok, VECLIB=1 iki OpenBLAS havuzunu da değiştirmedi.
# numpy bu dosyadan ÖNCE içe aktarılmışsa (numpy'yi önce yükleyen bir test
# süreci, `python hrma/app.py`) ayar o süreçte ETKİSİZDİR (ölçüldü: 14 kalır);
# yalnız ortam olarak alt süreçlere geçer.

#: OpenBLAS iş parçacığı varsayılanı — TEK KAYNAK (ölçüm: fea-hiz/a1).
BLAS_DEFAULT_THREADS = 1

#: OpenBLAS'ın iş parçacığı sayısını okuduğu ortam değişkenleri.
BLAS_THREAD_ENV_VARS = ("OPENBLAS_NUM_THREADS", "GOTO_NUM_THREADS",
                        "OMP_NUM_THREADS")


def _set_blas_thread_default() -> None:
    """Kullanıcı bir OpenBLAS değişkeni koymadıysa varsayılanı yazar."""
    if any(ad in os.environ for ad in BLAS_THREAD_ENV_VARS):
        return
    os.environ.setdefault("OPENBLAS_NUM_THREADS", str(BLAS_DEFAULT_THREADS))


_set_blas_thread_default()

__version__ = "3.0.1"
__author__ = "Berke Tezgöçen"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')


def _resolve_user_data_dir() -> str:
    """Platforma uygun, her zaman yazılabilir kullanıcı-veri dizini.

    DATA_DIR paketlenmiş kurulumda salt-okunur olabilir (macOS imzalı .app
    bundle'ı, Windows 'Program Files') — bundle içine her yazma imza mührünü
    bozar. Çalışma zamanında dosya yazmak isteyen modüller DATA_DIR yerine
    USER_DATA_DIR kullanmalı; DATA_DIR paketle gelen salt-okunur kaynak veri
    içindir. HRMA_USER_DATA_DIR ortam değişkeni dizini değiştirir (test için)
    — hrma/data/offline_store.py ile aynı sözleşme.
    """
    override = os.environ.get('HRMA_USER_DATA_DIR')
    if override:
        return override

    home = os.path.expanduser('~')
    if sys.platform == 'darwin':
        return os.path.join(home, 'Library', 'Application Support', 'HRMA')
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.path.join(home, 'AppData', 'Roaming')
        return os.path.join(base, 'HRMA')
    base = os.environ.get('XDG_DATA_HOME') or os.path.join(home, '.local', 'share')
    return os.path.join(base, 'HRMA')


# Dizin burada OLUŞTURULMAZ (import yan etkisiz kalsın); yazacak modül
# os.makedirs(USER_DATA_DIR, exist_ok=True) ile kendisi açar.
USER_DATA_DIR = _resolve_user_data_dir()

# data/ git'te izlenmiyor (*.db gitignore'da) — taze klonda klasör gelmez.
# SQLite eksik dosyayı oluşturabilir ama eksik klasörü oluşturamaz.
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    pass  # salt-okunur kurulum (ör. paketlenmiş uygulama) — DB sınıfları kendi yolunu açar
