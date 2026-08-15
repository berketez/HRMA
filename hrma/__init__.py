"""
HRMA - UZAYTEK Rocket Motor Analysis
"""

import os
import sys

__version__ = "2.6.27"
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
