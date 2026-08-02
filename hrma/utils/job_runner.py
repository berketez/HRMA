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
- Kuyruk SINIRLIDIR (v2.6.26). Ölçüm: ``maxsize=0`` ile kurulmuş kuyruğa
  5000 iş atıldı ve HİÇBİRİ reddedilmedi; her iş bir kayıt + bir Event
  tuttuğu için bu, sınırsız bellek büyümesi demekti. Artık kapasite
  dolduğunda ``JobQueueFullError`` fırlatılır — sessizce yutulmaz,
  çağıran "kapasite dolu" bilgisini açıkça alır.
- İptal İŞBİRLİKÇİDİR: kuyrukta bekleyen iş anında iptal edilir; koşan
  iş ancak kendisi haber alırsa durur (``cancel_event`` parametresi ya da
  enjekte edilen ``progress_callback``). Thread zorla öldürülmez.

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
STATE_CANCELLED = 'cancelled'
VALID_STATES = (STATE_QUEUED, STATE_RUNNING, STATE_DONE, STATE_ERROR,
                STATE_CANCELLED)

#: Bitmiş sayılan durumlar (TTL bunlara uygulanır)
FINISHED_STATES = (STATE_DONE, STATE_ERROR, STATE_CANCELLED)

#: Biten işin kayıtta tutulma süresi (saniye). 1 saat: masaüstü oturumunda
#: kullanıcı sonucu almak için makul pencere; sonrası bellek geri verilir.
DEFAULT_TTL_SECONDS = 3600.0

#: Masaüstü tek kullanıcı için 2 worker yeterli: bir uzun analiz + bir
#: kısa iş aynı anda yürüyebilir, CPU'yu boğmaz.
DEFAULT_MAX_WORKERS = 2

#: Kuyrukta BEKLEYEBİLECEK azami iş sayısı (koşanlar bu sayıya dâhil
#: değildir; kuyruktan alınınca yer boşalır). 32: tek kullanıcılı masaüstü
#: için fazlasıyla geniş bir tampon — normal kullanımda asla dolmaz, ama
#: kaçak bir döngü ya da kötü niyetli istek seli belleği tüketemez.
DEFAULT_MAX_QUEUED = 32


class JobQueueFullError(RuntimeError):
    """Kuyruk kapasitesi dolu; iş KABUL EDİLMEDİ.

    Uygulama katmanı bunu 503 (Service Unavailable) ile karşılamalıdır;
    ``http_status`` niteliği bu amaçla taşınır.
    """

    http_status = 503


class JobCancelled(Exception):
    """İş, iptal isteği üzerine kendisi sonlandı (işbirlikçi iptal)."""


class JobRunner:
    """Thread tabanlı iş kuyruğu.

    Parameters
    ----------
    max_workers : int
        Eşzamanlı worker thread sayısı (>=1).
    ttl_seconds : float
        Bitmiş (done/error/cancelled) işin kayıtta tutulma süresi;
        aşılınca kayıt silinir ve ``status`` KeyError verir.
    time_fn : callable
        Monotonik saat kaynağı. Testlerde sahte saat enjekte edilebilsin
        diye parametreleştirildi (varsayılan ``time.monotonic``).
    max_queued : int
        Kuyrukta bekleyebilecek azami iş sayısı (>=1). Dolduğunda
        ``submit`` ``JobQueueFullError`` fırlatır.
    """

    def __init__(self, max_workers=DEFAULT_MAX_WORKERS,
                 ttl_seconds=DEFAULT_TTL_SECONDS, time_fn=time.monotonic,
                 max_queued=DEFAULT_MAX_QUEUED):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if max_queued < 1:
            raise ValueError("max_queued must be >= 1")
        self._max_workers = int(max_workers)
        self._ttl = float(ttl_seconds)
        self._time = time_fn
        self._max_queued = int(max_queued)
        self._jobs = {}
        self._lock = threading.Lock()
        # maxsize>0: kapasite aşımı sessizce büyümek yerine reddedilir
        self._queue = queue.Queue(maxsize=self._max_queued)
        self._workers_started = False

    # ------------------------------------------------------------------
    # Genel API
    # ------------------------------------------------------------------
    def submit(self, fn, *args, **kwargs):
        """İşi kuyruğa at, benzersiz iş kimliği (uuid4 str) döndür.

        ``fn`` imzasında ``progress_callback`` adlı parametre varsa ve
        çağıran kendisi vermemişse, runner ``progress_callback(frac)``
        geri çağrısını enjekte eder; ``frac`` [0, 1] aralığına kırpılır.
        Aynı şekilde ``cancel_event`` parametresi varsa iptal olayı
        enjekte edilir (bkz. :meth:`cancel`).

        Raises
        ------
        JobQueueFullError
            Kuyrukta bekleyen iş sayısı kapasiteye ulaştı; iş KABUL
            EDİLMEDİ ve hiçbir kayıt bırakılmadı.
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
            'cancel_requested': False,
            'cancel_event': threading.Event(),
        }
        with self._lock:
            self._purge_expired_locked()
            self._jobs[job_id] = record
        self._ensure_workers()
        try:
            # Kayıt ÖNCE eklenir: worker kuyruktan alır almaz kaydı bulsun.
            # Kuyruk reddederse kayıt geri alınır — yarım iş bırakılmaz.
            self._queue.put_nowait((job_id, fn, args, kwargs))
        except queue.Full:
            with self._lock:
                self._jobs.pop(job_id, None)
            raise JobQueueFullError(
                f"Job queue is full ({self._max_queued} pending jobs); "
                "wait for running work to finish and try again.")
        return job_id

    def status(self, job_id):
        """İş durumunu döndür.

        Returns
        -------
        dict
            ``{'state': 'queued'|'running'|'done'|'error'|'cancelled',
            'progress': 0-1, 'cancel_requested': bool}``
            + ``'result'`` (done ise) veya ``'error'`` (error/cancelled ise).

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
            out = {'state': record['state'], 'progress': record['progress'],
                   'cancel_requested': record['cancel_requested']}
            if record['state'] == STATE_DONE:
                out['result'] = record['result']
            elif record['state'] in (STATE_ERROR, STATE_CANCELLED):
                out['error'] = record['error']
            return out

    def cancel(self, job_id):
        """İşbirlikçi iptal iste.

        Kuyrukta bekleyen iş ANINDA iptal edilir (worker onu alınca
        atlar). Koşan iş için yalnız bayrak kaldırılır: iş fonksiyonu
        ``cancel_event`` parametresini okuyorsa ya da enjekte edilen
        ``progress_callback``'i çağırıyorsa durur. Thread ZORLA
        öldürülmez — CPython'da güvenli bir yolu yoktur ve yarım
        bırakılan hesap sessiz veri bozulması demektir.

        Returns
        -------
        bool
            İptal kaydedildiyse True; iş çoktan bittiyse False.

        Raises
        ------
        KeyError
            Bilinmeyen ya da TTL ile temizlenmiş iş kimliği.
        """
        with self._lock:
            self._purge_expired_locked()
            record = self._jobs.get(job_id)
            if record is None:
                raise KeyError(f"Unknown or expired job id: {job_id}")
            if record['state'] in FINISHED_STATES:
                return False
            record['cancel_requested'] = True
            record['cancel_event'].set()
            hemen_bitti = record['state'] == STATE_QUEUED
            if hemen_bitti:
                record['state'] = STATE_CANCELLED
                record['error'] = 'Job cancelled before it started.'
                record['finished_at'] = self._time()
            olay = record['done_event'] if hemen_bitti else None
        if olay is not None:
            olay.set()
        return True

    def pending_count(self):
        """Kuyrukta BEKLEYEN (henüz worker almamış) iş sayısı."""
        return self._queue.qsize()

    @property
    def queue_capacity(self):
        """Kuyruğun kabul edebileceği azami bekleyen iş sayısı."""
        return self._max_queued

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
        """TTL süresi dolan bitmiş (done/error/cancelled) işleri sil."""
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
        # Kilit çağıranda — yalnız bitmiş (done/error/cancelled) işler TTL'e
        # tabidir; kuyruktaki veya koşan iş asla silinmez.
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
    def _accepts_parameter(fn, name):
        # Fonksiyon imzasında açıkça o adda parametre aranır; **kwargs'a
        # körlemesine enjeksiyon YAPILMAZ (fonksiyon beklemiyorsa
        # davranışı bozabilir).
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return False
        return name in sig.parameters

    @classmethod
    def _accepts_progress_callback(cls, fn):
        return cls._accepts_parameter(fn, 'progress_callback')

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
                    if record['cancel_requested']:
                        # Kuyrukta beklerken iptal edildi: hiç başlatma.
                        if record['state'] not in FINISHED_STATES:
                            record['state'] = STATE_CANCELLED
                            record['error'] = 'Job cancelled before it started.'
                            record['finished_at'] = self._time()
                        iptal_kaydi = record
                        iptal_kaydi['done_event'].set()
                        continue
                    record['state'] = STATE_RUNNING

                def _progress(fraction, _record=record):
                    # İlerleme bildirimi aynı zamanda iptal denetim
                    # noktasıdır: uzun işler ekstra kod yazmadan durabilir.
                    if _record['cancel_event'].is_set():
                        raise JobCancelled('Job cancelled while running.')
                    with self._lock:
                        _record['progress'] = min(1.0, max(0.0, float(fraction)))

                if ('progress_callback' not in kwargs
                        and self._accepts_progress_callback(fn)):
                    kwargs = dict(kwargs)
                    kwargs['progress_callback'] = _progress
                if ('cancel_event' not in kwargs
                        and self._accepts_parameter(fn, 'cancel_event')):
                    kwargs = dict(kwargs)
                    kwargs['cancel_event'] = record['cancel_event']

                try:
                    result = fn(*args, **kwargs)
                except JobCancelled as exc:
                    # İş, iptal isteğine kendisi uydu: hata DEĞİL
                    with self._lock:
                        record['state'] = STATE_CANCELLED
                        record['error'] = str(exc) or 'Job cancelled while running.'
                        record['finished_at'] = self._time()
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
