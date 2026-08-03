"""``python -m hrma.run`` alt sürecinin ömrü.

Kural: iskele bir sunucu başlattıysa, tur nasıl biterse bitsin (hüküm,
istisna, Ctrl-C) o süreci ÖLDÜRÜR. Arkada kalan bir sunucu 8080-8090
aralığındaki portu tutar ve bir sonraki koşuyu ya da kullanıcının kendi
uygulamasını sessizce bozar.

Dışarıdan ``--base-url`` verildiyse bu modül hiç devreye girmez; başkasının
başlattığı sunucu başkasının sorumluluğudur.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional

from tools.browser_harness import esikler

#: Depo kökü — ``python -m hrma.run`` buradan çalıştırılır.
DEPO_KOKU = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Sunucunun ayakta olduğunu söyleyen uç (hrma/app.py:1127, JSON döner).
SAGLIK_YOLU = '/test'


def bos_port_bul() -> int:
    """İşletim sisteminden boş bir port ister (bind 0), sonra bırakır.

    Yarış payı var (bırakma ile sunucunun bağlanması arası) ama alternatifi
    ``hrma/run.py``ın 8080-8090 taramasına güvenmek olurdu; o durumda
    iskele hangi porta bağlanıldığını çıktıyı ayrıştırmadan bilemez.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return int(s.getsockname()[1])


def komut(python_yolu: Optional[str] = None) -> List[str]:
    """Sunucuyu başlatan komut satırı."""
    return [python_yolu or sys.executable, '-m', 'hrma.run']


def ortam(port: int, temel: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Alt sürecin ortam değişkenleri.

    ``HRMA_PORT``  Portu biz seçeriz; ``hrma/run.py`` bu değişkeni okur ve
                   kendi 8080-8090 taramasını atlar.
    ``BROWSER``    ``hrma/run.py`` açılışta ``webbrowser.open`` çağırır
                   (run.py:88). Denetim koşusunda kullanıcının ekranına
                   gerçek bir tarayıcı penceresi açılmamalı. ``webbrowser``
                   ``BROWSER`` değişkenini ilk sırada dener; ``echo`` başarı
                   döndürdüğü için zincir orada durur ve hiçbir pencere
                   açılmaz.
    """
    yeni = dict(temel if temel is not None else os.environ)
    yeni['HRMA_PORT'] = str(port)
    yeni['BROWSER'] = 'echo'
    # Alt süreç depo kökünü sys.path'e kendisi ekliyor (run.py:15) ama
    # PYTHONPATH'i de vermek, farklı çalışma dizinlerinden çağrıldığında
    # ``import hrma`` hatasını tamamen kapatır.
    onceki = yeni.get('PYTHONPATH', '')
    yeni['PYTHONPATH'] = DEPO_KOKU + (os.pathsep + onceki if onceki else '')
    return yeni


def hazir_mi(temel_url: str, acici: Callable[..., object] = urllib.request.urlopen) -> bool:
    """Sağlık ucu 200 dönüyor mu? Ağ hatası "hazır değil" demektir."""
    try:
        with acici(temel_url.rstrip('/') + SAGLIK_YOLU, timeout=3) as cevap:
            return int(getattr(cevap, 'status', getattr(cevap, 'code', 0))) == 200
    except Exception:
        return False


class UygulamaSunucusu:
    """Alt süreçle başlatılan HRMA sunucusu — bağlam yöneticisi.

    Kullanım::

        with UygulamaSunucusu(gunluk_yolu=...) as s:
            gez(s.temel_url)
        # buraya gelindiğinde süreç kesin ölmüştür
    """

    def __init__(self, port: Optional[int] = None,
                 python_yolu: Optional[str] = None,
                 gunluk_yolu: Optional[str] = None,
                 zaman_asimi_s: float = esikler.SUNUCU_HAZIR_ZAMAN_ASIMI_S):
        self.port = port or bos_port_bul()
        self.python_yolu = python_yolu or sys.executable
        self.gunluk_yolu = gunluk_yolu
        self.zaman_asimi_s = zaman_asimi_s
        self.surec: Optional[subprocess.Popen] = None
        self._gunluk = None
        self.hazir_sure_s: Optional[float] = None

    @property
    def temel_url(self) -> str:
        return 'http://127.0.0.1:%d' % self.port

    # -- ömür ------------------------------------------------------------
    def baslat(self) -> 'UygulamaSunucusu':
        cikti = subprocess.DEVNULL
        if self.gunluk_yolu:
            os.makedirs(os.path.dirname(os.path.abspath(self.gunluk_yolu)), exist_ok=True)
            self._gunluk = open(self.gunluk_yolu, 'wb')
            cikti = self._gunluk
        ek = {}
        if os.name == 'nt':  # pragma: no cover - macOS/Linux'ta koşulmaz
            ek['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            # Kendi süreç grubunda başlat: Flask geliştirme sunucusu çocuk
            # süreç doğurursa grup birlikte öldürülür, yetim kalmaz.
            ek['start_new_session'] = True
        self.surec = subprocess.Popen(
            komut(self.python_yolu), cwd=DEPO_KOKU, env=ortam(self.port),
            stdout=cikti, stderr=subprocess.STDOUT, **ek)
        self._hazir_bekle()
        return self

    def _hazir_bekle(self) -> None:
        baslangic = time.time()
        while time.time() - baslangic < self.zaman_asimi_s:
            if self.surec is not None and self.surec.poll() is not None:
                raise RuntimeError(
                    'sunucu süreci hazır olmadan çıktı (kod %s). Günlük: %s'
                    % (self.surec.returncode, self.gunluk_yolu or '(yok)'))
            if hazir_mi(self.temel_url):
                self.hazir_sure_s = time.time() - baslangic
                return
            time.sleep(esikler.SUNUCU_YOKLAMA_ARALIGI_S)
        self.durdur()
        raise TimeoutError(
            '%s %.0f saniyede hazır olmadı. Günlük: %s'
            % (self.temel_url, self.zaman_asimi_s, self.gunluk_yolu or '(yok)'))

    def durdur(self) -> None:
        """Süreci (ve grubunu) sonlandırır. Birden çok kez çağrılabilir."""
        surec, self.surec = self.surec, None
        if surec is not None and surec.poll() is None:
            _surec_oldur(surec)
        if self._gunluk is not None:
            try:
                self._gunluk.close()
            finally:
                self._gunluk = None

    def __enter__(self) -> 'UygulamaSunucusu':
        return self.baslat()

    def __exit__(self, *_) -> None:
        self.durdur()


def _surec_oldur(surec: subprocess.Popen,
                 bekleme_s: float = esikler.SUNUCU_KAPANMA_BEKLEME_S) -> None:
    """Önce nazik sonlandırma, cevap yoksa öldürme — grup düzeyinde."""
    try:
        if os.name != 'nt':
            os.killpg(os.getpgid(surec.pid), signal.SIGTERM)
        else:  # pragma: no cover - macOS/Linux'ta koşulmaz
            surec.terminate()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            surec.terminate()
        except Exception:
            pass
    try:
        surec.wait(timeout=bekleme_s)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name != 'nt':
            os.killpg(os.getpgid(surec.pid), signal.SIGKILL)
        else:  # pragma: no cover
            surec.kill()
    except Exception:
        try:
            surec.kill()
        except Exception:
            pass
    try:
        surec.wait(timeout=bekleme_s)
    except Exception:
        pass
