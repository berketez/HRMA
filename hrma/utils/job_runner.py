"""Hafif, thread tabanlı iş kuyruğu (masaüstü / tek kullanıcı).

Amaç: Flask isteği uzun süren bir analizi (gelecekte CFD sınıfı işler,
Monte Carlo taramaları, yörünge süpürmeleri) kuyruğa atar, istemci
``GET /api/jobs/<id>`` ile durumu yoklar (polling). Celery/Redis gibi
harici broker BİLİNÇLİ olarak kullanılmaz: uygulama tek süreçli masaüstü
dağıtımıdır (PyInstaller bundle), ek servis bağımlılığı kabul edilemez.

Tasarım notları:
- ``queue.Queue`` + sabit sayıda daemon worker thread; CPython'da
  ``queue.Queue`` thread-safe'tir (stdlib dokümantasyonu, "queue" modülü).
- İş kayıtları tek bir ``threading.Lock`` ile korunur; durum sözlüğünün
  kopyası döndürülür, iç kayıt dışarı sızmaz.
- Biten işler TTL (varsayılan 1 saat) sonunda otomatik temizlenir ki
  uzun açık kalan masaüstü oturumunda bellek sızıntısı olmasın.
- İş fonksiyonu imzasında ``progress_callback`` parametresi varsa runner
  0..1 aralığına kırpan bir ilerleme geri çağrısı enjekte eder.

Kullanıcıya dönen tüm metinler İngilizce'dir (UI kuralı).
"""

import inspect
import queue
import threading
import time
import traceback
import uuid

# İş durumları — API sözleşmesi: GET /api/jobs/<id> bu değerleri döndürür
STATE_QUEUED = 'queued'
STATE_RUNNING = 'running'
STATE_DONE = 'done'
STATE_ERROR = 'error'
VALID_STATES = (STATE_QUEUED, STATE_RUNNING, STATE_DONE, STATE_ERROR)

#: Biten işin kayıtta tutulma süresi (saniye). 1 saat: masaüstü oturumunda
#: kullanıcı sonucu almak için makul pencere; sonrası bellek geri verilir.
DEFAULT_TTL_SECONDS = 3600.0

#: Masaüstü tek kullanıcı için 2 worker yeterli: bir uzun analiz + bir
#: kısa iş aynı anda yürüyebilir, CPU'yu boğmaz.
DEFAULT_MAX_WORKERS = 2


class JobRunner:
    """Thread tabanlı iş kuyruğu.

    Parameters
    ----------
    max_workers : int
        Eşzamanlı worker thread sayısı (>=1).
    ttl_seconds : float
        Bitmiş (done/error) işin kayıtta tutulma süresi; aşılınca kayıt
        silinir ve ``status`` KeyError verir.
    time_fn : callable
        Monotonik saat kaynağı. Testlerde sahte saat enjekte edilebilsin
        diye parametreleştirildi (varsayılan ``time.monotonic``).
    """

    def __init__(self, max_workers=DEFAULT_MAX_WORKERS,
                 ttl_seconds=DEFAULT_TTL_SECONDS, time_fn=time.monotonic):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        self._max_workers = int(max_workers)
        self._ttl = float(ttl_seconds)
        self._time = time_fn
        self._jobs = {}
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        self._workers_started = False

    # ------------------------------------------------------------------
    # Genel API
    # ------------------------------------------------------------------
    def submit(self, fn, *args, **kwargs):
        """İşi kuyruğa at, benzersiz iş kimliği (uuid4 str) döndür.

        ``fn`` imzasında ``progress_callback`` adlı parametre varsa ve
        çağıran kendisi vermemişse, runner ``progress_callback(frac)``
        geri çağrısını enjekte eder; ``frac`` [0, 1] aralığına kırpılır.
        """
        if not callable(fn):
            raise TypeError("fn must be callable")
        job_id = str(uuid.uuid4())
        record = {
            'state': STATE_QUEUED,
            'progress': 0.0,
            'result': None,
            'error': None,
            'traceback': None,
            'submitted_at': self._time(),
            'finished_at': None,
            'done_event': threading.Event(),
        }
        with self._lock:
            self._purge_expired_locked()
            self._jobs[job_id] = record
        self._ensure_workers()
        self._queue.put((job_id, fn, args, kwargs))
        return job_id

    def status(self, job_id):
        """İş durumunu döndür.

        Returns
        -------
        dict
            ``{'state': 'queued'|'running'|'done'|'error', 'progress': 0-1}``
            + ``'result'`` (done ise) veya ``'error'`` (error ise).

        Raises
        ------
        KeyError
            Bilinmeyen ya da TTL ile temizlenmiş iş kimliği.
        """
        with self._lock:
            self._purge_expired_locked()
            record = self._jobs.get(job_id)
            if record is None:
                raise KeyError(
                    f"Unknown or expired job id: {job_id}")
            out = {'state': record['state'], 'progress': record['progress']}
            if record['state'] == STATE_DONE:
                out['result'] = record['result']
            elif record['state'] == STATE_ERROR:
                out['error'] = record['error']
            return out

    def wait(self, job_id, timeout=None):
        """İş bitene dek blokla (test/CLI kolaylığı).

        Returns True if the job finished (done or error) within timeout.
        """
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise KeyError(f"Unknown or expired job id: {job_id}")
            event = record['done_event']
        return event.wait(timeout)

    def cleanup_expired(self):
        """TTL süresi dolan bitmiş işleri sil; silinen adedi döndür."""
        with self._lock:
            return self._purge_expired_locked()

    def job_count(self):
        """Kayıtlı (henüz temizlenmemiş) iş sayısı."""
        with self._lock:
            return len(self._jobs)

    # ------------------------------------------------------------------
    # İç mekanizma
    # ------------------------------------------------------------------
    def _purge_expired_locked(self):
        # Kilit çağıranda — yalnız bitmiş işler TTL'e tabidir; kuyruktaki
        # veya koşan iş asla silinmez.
        now = self._time()
        expired = [jid for jid, rec in self._jobs.items()
                   if rec['finished_at'] is not None
                   and (now - rec['finished_at']) > self._ttl]
        for jid in expired:
            del self._jobs[jid]
        return len(expired)

    def _ensure_workers(self):
        with self._lock:
            if self._workers_started:
                return
            self._workers_started = True
        for i in range(self._max_workers):
            t = threading.Thread(target=self._worker_loop,
                                 name=f"hrma-job-worker-{i}", daemon=True)
            t.start()

    @staticmethod
    def _accepts_progress_callback(fn):
        # Fonksiyon imzasında açıkça 'progress_callback' adlı parametre
        # aranır; **kwargs'a körlemesine enjeksiyon YAPILMAZ (fonksiyon
        # beklemiyorsa davranışı bozabilir).
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return False
        return 'progress_callback' in sig.parameters

    def _worker_loop(self):
        while True:
            job_id, fn, args, kwargs = self._queue.get()
            try:
                with self._lock:
                    record = self._jobs.get(job_id)
                    if record is None:
                        # İş kuyruktayken TTL ile temizlendi (pratikte
                        # olmaz; savunmacı dal)
                        continue
                    record['state'] = STATE_RUNNING

                def _progress(fraction, _record=record):
                    with self._lock:
                        _record['progress'] = min(1.0, max(0.0, float(fraction)))

                if ('progress_callback' not in kwargs
                        and self._accepts_progress_callback(fn)):
                    kwargs = dict(kwargs)
                    kwargs['progress_callback'] = _progress

                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:  # iş hatası işi öldürür, worker'ı değil
                    with self._lock:
                        record['state'] = STATE_ERROR
                        record['error'] = f"{type(exc).__name__}: {exc}"
                        record['traceback'] = traceback.format_exc()
                        record['finished_at'] = self._time()
                else:
                    with self._lock:
                        record['state'] = STATE_DONE
                        record['result'] = result
                        record['progress'] = 1.0
                        record['finished_at'] = self._time()
                record['done_event'].set()
            finally:
                self._queue.task_done()


#: Uygulama genel tekil kuyruk — endpoint'ler bunu kullanır.
job_runner = JobRunner()
