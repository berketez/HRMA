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
- ZAMAN AŞIMI BEYAN EDİLİR, THREAD ÖLDÜRÜLMEZ (v2.6.27). Ölçüm: iptali
  duymayan 2 iş her iki worker'ı süresiz tutuyordu; üçüncü iş sonsuza
  kadar 'queued' kalıyor ve TTL takılan kaydı HİÇ temizlemiyordu (TTL
  yalnız ``finished_at`` dolu kayıtlara işliyor). Artık koşan iş
  ``job_timeout_seconds``i aşarsa (a) işbirlikçi iptal istenir, (b) kayıt
  'error' + ``timed_out=True`` ile SONLANDIRILMIŞ sayılır ve TTL'e girer,
  (c) terk edilen thread'in yerine bir worker açılır, böylece kuyruk
  akmaya devam eder. CPython'da thread zorla öldürülemez: terk edilen iş
  ARKA PLANDA KOŞMAYA DEVAM EDEBİLİR ve bu, hata metninde açıkça
  söylenir — "öldürdük" denmez. İş kendi kendine bittiğinde fazla worker
  bir sonraki turda kendini kapatır (``_surplus``), thread sayısı
  ``max_workers``a geri döner.
- Zaman aşımı YOKLAMA anında değerlendirilir (``submit`` / ``status`` /
  ``cancel`` / ``cleanup_expired``); ayrı bir zamanlayıcı thread'i
  KURULMAZ. Arayüz zaten ``GET /api/jobs/<id>`` ile yokladığı için pratik
  yol budur; hiç yoklanmayan bir işi kimse beklemiyordur.

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

#: KOŞAN bir işin üst süre sınırı (saniye). YENİ BİR EŞİK İCAT EDİLMEDİ:
#: değer, zaten var olan ``DEFAULT_TTL_SECONDS`` penceresinden türetilir —
#: runner biten bir işin sonucunu en fazla o kadar süre saklar, dolayısıyla
#: o pencereden uzun süredir koşan bir iş, sonucu okunmaya yetişemeyecek
#: kadar takılmış demektir. ``None`` verilirse sınır uygulanmaz (eski
#: davranış); ölçüm/CI'da kısa değer enjekte edilir.
DEFAULT_JOB_TIMEOUT_SECONDS = DEFAULT_TTL_SECONDS

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
    job_timeout_seconds : float or None
        KOŞAN bir işin üst süre sınırı. Aşılırsa iş 'error' +
        ``timed_out=True`` ile sonlandırılmış SAYILIR ve worker'ının
        yerine yenisi açılır; thread ÖLDÜRÜLMEZ (arka planda koşmaya
        devam edebilir, hata metninde beyan edilir). ``None`` sınırı
        kapatır.
    """

    def __init__(self, max_workers=DEFAULT_MAX_WORKERS,
                 ttl_seconds=DEFAULT_TTL_SECONDS, time_fn=time.monotonic,
                 max_queued=DEFAULT_MAX_QUEUED,
                 job_timeout_seconds=DEFAULT_JOB_TIMEOUT_SECONDS):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if max_queued < 1:
            raise ValueError("max_queued must be >= 1")
        if job_timeout_seconds is not None and job_timeout_seconds <= 0:
            raise ValueError("job_timeout_seconds must be > 0 or None")
        self._max_workers = int(max_workers)
        self._ttl = float(ttl_seconds)
        self._time = time_fn
        self._max_queued = int(max_queued)
        self._job_timeout = (None if job_timeout_seconds is None
                             else float(job_timeout_seconds))
        self._jobs = {}
        self._lock = threading.Lock()
        # maxsize>0: kapasite aşımı sessizce büyümek yerine reddedilir
        self._queue = queue.Queue(maxsize=self._max_queued)
        self._workers_started = False
        # Terk edilmiş (zaman aşımına uğramış) iş sayısı ve bunların yerine
        # açılan fazla worker sayısı. Sessiz sızıntı olmasın diye SAYILIR.
        self._abandoned = 0
        self._surplus = 0
        self._pending_spawn = 0

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
            'started_at': None,
            'finished_at': None,
            'timed_out': False,
            'done_event': threading.Event(),
            'cancel_requested': False,
            'cancel_event': threading.Event(),
        }
        with self._lock:
            self._purge_expired_locked()
            self._jobs[job_id] = record
        self._ensure_workers()
        self._drain_pending_spawn()
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
            'progress': 0-1, 'cancel_requested': bool, 'timed_out': bool}``
            + ``'result'`` (done ise) veya ``'error'`` (error/cancelled ise).

            ``timed_out`` True ise iş süre sınırını aşmıştır: 'error'
            sayılmıştır ama thread'i arka planda koşuyor OLABİLİR.

        Raises
        ------
        KeyError
            Bilinmeyen ya da TTL ile temizlenmiş iş kimliği.
        """
        try:
            with self._lock:
                self._purge_expired_locked()
                record = self._jobs.get(job_id)
                if record is None:
                    raise KeyError(
                        f"Unknown or expired job id: {job_id}")
                out = {'state': record['state'],
                       'progress': record['progress'],
                       'cancel_requested': record['cancel_requested'],
                       'timed_out': record['timed_out']}
                if record['state'] == STATE_DONE:
                    out['result'] = record['result']
                elif record['state'] in (STATE_ERROR, STATE_CANCELLED):
                    out['error'] = record['error']
                if 'late_result' in record:
                    # Zaman aşımından SONRA gelen sonuç. Durum 'error'
                    # kalır (verilmiş hüküm geriye dönük değiştirilmez) ama
                    # sonuç ÇÖPE ATILMAZ: ayrı alanda beyan edilir, çağıran
                    # kullanıp kullanmayacağına kendisi karar verir.
                    out['late_result'] = record['late_result']
                return out
        finally:
            # Yoklama, takılan worker'ın yerine yenisini açar: kuyrukta
            # bekleyen iş sonsuza kadar 'queued' kalmasın.
            self._drain_pending_spawn()

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
        self._drain_pending_spawn()
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
        """TTL süresi dolan bitmiş (done/error/cancelled) işleri sil.

        Süre sınırını aşan KOŞAN iş önce sonlandırılmış sayılır (bkz.
        ``_timeout_running_locked``), böylece TTL'e girebilir; eskiden
        takılan iş ``finished_at is None`` olduğu için hiç temizlenmiyordu.
        """
        try:
            with self._lock:
                return self._purge_expired_locked()
        finally:
            self._drain_pending_spawn()

    def job_count(self):
        """Kayıtlı (henüz temizlenmemiş) iş sayısı."""
        with self._lock:
            return len(self._jobs)

    # ------------------------------------------------------------------
    # İç mekanizma
    # ------------------------------------------------------------------
    def _purge_expired_locked(self):
        # Kilit çağıranda — önce süresi aşan KOŞAN işler sonlandırılmış
        # sayılır (yoksa TTL'e hiç girmezler), sonra bitmiş (done/error/
        # cancelled) işler TTL'e tabi tutulur. Kuyrukta BEKLEYEN iş asla
        # silinmez ve zaman aşımına da girmez: sırasını bekliyor olması
        # kendi kusuru değildir.
        now = self._time()
        yedek_gerek = self._timeout_running_locked(now)
        expired = [jid for jid, rec in self._jobs.items()
                   if rec['finished_at'] is not None
                   and (now - rec['finished_at']) > self._ttl]
        for jid in expired:
            del self._jobs[jid]
        if yedek_gerek:
            # Thread başlatma kilidin DIŞINDA yapılmalı; kilit çağıranda
            # olduğu için istek biriktirilir, _drain_pending_spawn açar.
            self._pending_spawn += yedek_gerek
        return len(expired)

    def _timeout_running_locked(self, now):
        """Süre sınırını aşan KOŞAN işleri sonlandırılmış sayar.

        Dönen değer: açılması gereken yedek worker sayısı. Thread ZORLA
        ÖLDÜRÜLMEZ (CPython'da güvenli yolu yok); iş arka planda koşmaya
        devam edebilir ve hata metni bunu açıkça söyler.
        """
        if self._job_timeout is None:
            return 0
        sayac = 0
        for rec in self._jobs.values():
            if (rec['state'] != STATE_RUNNING or rec['started_at'] is None
                    or rec['timed_out']):
                continue
            if (now - rec['started_at']) <= self._job_timeout:
                continue
            rec['timed_out'] = True
            rec['state'] = STATE_ERROR
            rec['error'] = (
                f"Job exceeded the {self._job_timeout:g} s time limit and was "
                "abandoned. A cancel request was sent; if the job does not "
                "check for cancellation it may still be running in the "
                "background (worker threads cannot be killed safely).")
            rec['finished_at'] = now
            rec['cancel_requested'] = True
            rec['cancel_event'].set()
            rec['done_event'].set()
            self._abandoned += 1
            sayac += 1
        return sayac

    def abandoned_count(self):
        """Zaman aşımıyla TERK EDİLMİŞ iş sayısı (thread'i hâlâ koşuyor olabilir)."""
        with self._lock:
            return self._abandoned

    def _start_worker(self, index):
        t = threading.Thread(target=self._worker_loop,
                             name=f"hrma-job-worker-{index}", daemon=True)
        t.start()

    def _ensure_workers(self):
        with self._lock:
            if self._workers_started:
                return
            self._workers_started = True
        for i in range(self._max_workers):
            self._start_worker(i)

    def _drain_pending_spawn(self):
        """Terk edilen worker'ların yerine yenilerini açar (kilit DIŞINDA).

        Zaman aşımı sweep'i kilit altında çalıştığı için thread başlatma
        isteği biriktirilir; her yoklama noktası (submit/status/cancel/
        cleanup_expired) kilidi bıraktıktan sonra burayı çağırır.
        """
        etiket = 0
        with self._lock:
            bekleyen = self._pending_spawn
            self._pending_spawn = 0
            if bekleyen:
                # Terk edilen thread işini bitirip geri dönerse FAZLA worker
                # olur; o zaman kendini kapatsın diye borç kaydedilir
                # (sızıntı sessiz değil, sayılı).
                self._surplus += bekleyen
                etiket = self._abandoned
        for j in range(bekleyen):
            self._start_worker(f"replacement-{etiket}-{j}")

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
                    # Zaman aşımı KOŞMA anından itibaren sayılır: kuyrukta
                    # sıra beklemek işin kendi kusuru değildir.
                    record['started_at'] = self._time()

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
                        if not record['timed_out']:
                            record['state'] = STATE_CANCELLED
                            record['error'] = (str(exc)
                                               or 'Job cancelled while running.')
                            record['finished_at'] = self._time()
                except Exception as exc:  # iş hatası işi öldürür, worker'ı değil
                    with self._lock:
                        record['traceback'] = traceback.format_exc()
                        if not record['timed_out']:
                            record['state'] = STATE_ERROR
                            record['error'] = f"{type(exc).__name__}: {exc}"
                            record['finished_at'] = self._time()
                else:
                    with self._lock:
                        if record['timed_out']:
                            # GEÇ GELEN SONUÇ: iş zaman aşımıyla terk edilmiş
                            # sayıldı ve çağıran 'error' cevabını çoktan aldı.
                            # Sonucu şimdi 'done' diye geri yazmak, bitmiş bir
                            # yoklamayı geriye dönük değiştirmek olurdu; sonuç
                            # SESSİZCE ATILMAZ, ayrı alanda beyan edilir.
                            record['late_result'] = result
                            record['late_finished_at'] = self._time()
                        else:
                            record['state'] = STATE_DONE
                            record['result'] = result
                            record['progress'] = 1.0
                            record['finished_at'] = self._time()
                record['done_event'].set()
            finally:
                self._queue.task_done()

            # Bu thread, zaman aşımıyla TERK EDİLMİŞ bir işten yeni döndü:
            # yerine bir worker açılmıştı, yani şu an fazlayız. Borcu kapatıp
            # kendimizi kapatırız; thread sayısı max_workers'a geri döner.
            # (Kontrol yalnız terk edilmiş işi bitiren thread'e aittir —
            # yedek worker'lar bu daldan geçmez, yoksa hemen kapanırlardı.)
            if record['timed_out']:
                with self._lock:
                    if self._surplus > 0:
                        self._surplus -= 1
                        return


#: Uygulama genel tekil kuyruk — endpoint'ler bunu kullanır.
job_runner = JobRunner()
