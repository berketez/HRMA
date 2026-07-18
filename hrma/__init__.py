"""
HRMA - UZAYTEK Rocket Motor Analysis
"""

import os

__version__ = "2.5.0"
__author__ = "Berke Tezgöçen"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')

# data/ git'te izlenmiyor (*.db gitignore'da) — taze klonda klasör gelmez.
# SQLite eksik dosyayı oluşturabilir ama eksik klasörü oluşturamaz.
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    pass  # salt-okunur kurulum (ör. paketlenmiş uygulama) — DB sınıfları kendi yolunu açar
