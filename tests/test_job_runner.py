"""JobRunner testleri: yaşam döngüsü, eşzamanlılık, hata yakalama, TTL.

Zamanlama kırılganlığına karşı testler Event/poll tabanlıdır; sabit
sleep'e dayalı yarış YOK (deterministik gate desenleri).
"""

import threading
import time
import uuid

import pytest

from hrma.utils.job_runner import (
    JobRunner, STATE_QUEUED, STATE_RUNNING, STATE_DONE, STATE_ERROR,
    DEFAULT_TTL_SECONDS,
)

POLL_TIMEOUT = 5.0  # saniye — CI yavaşlığına tolerans


def _poll_until(predicate, timeout=POLL_TIMEOUT):
    """Koşul sağlanana dek yokla; sağlanmazsa False."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


class TestLifecycle:
    def test_submit_returns_unique_uuid_strings(self):
        runner = JobRunner(max_workers=1)
        ids = [runner.submit(lambda: None) for _ in range(5)]
        assert len(set(ids)) == 5
        for jid in ids:
            uuid.UUID(jid)  # geçersizse ValueError atar

    def test_job_completes_with_result(self):
        runner = JobRunner(max_workers=1)
        jid = runner.submit(lambda a, b: a + b, 2, 3)
        assert runner.wait(jid, timeout=POLL_TIMEOUT)
        st = runner.status(jid)
        assert st['state'] == STATE_DONE
        assert st['result'] == 5
        assert st['progress'] == 1.0

    def test_kwargs_are_passed_through(self):
        runner = JobRunner(max_workers=1)
        jid = runner.submit(lambda a, b=0, c=0: (a, b, c), 1, b=2, c=3)
        assert runner.wait(jid, timeout=POLL_TIMEOUT)
        assert runner.status(jid)['result'] == (1, 2, 3)

    def test_queued_state_visible_while_worker_busy(self):
        runner = JobRunner(max_workers=1)
        gate = threading.Event()
        started = threading.Event()

        def blocker():
            started.set()
            gate.wait(POLL_TIMEOUT)

        j1 = runner.submit(blocker)
        assert started.wait(POLL_TIMEOUT)
        j2 = runner.submit(lambda: 'second')
        # Tek worker meşgulken ikinci iş kuyrukta beklemeli
        assert runner.status(j2)['state'] == STATE_QUEUED
        assert runner.status(j1)['state'] == STATE_RUNNING
        gate.set()
        assert runner.wait(j2, timeout=POLL_TIMEOUT)
        assert runner.status(j2)['result'] == 'second'

    def test_fifo_order_with_single_worker(self):
        runner = JobRunner(max_workers=1)
        seen = []
        lock = threading.Lock()

        def record(i):
            with lock:
                seen.append(i)

        ids = [runner.submit(record, i) for i in range(5)]
        for jid in ids:
            assert runner.wait(jid, timeout=POLL_TIMEOUT)
        assert seen == [0, 1, 2, 3, 4]

    def test_unknown_job_id_raises_keyerror(self):
        runner = JobRunner(max_workers=1)
        with pytest.raises(KeyError):
            runner.status('nonexistent-id')
        with pytest.raises(KeyError):
            runner.wait('nonexistent-id', timeout=0.01)


class TestErrorHandling:
    def test_exception_is_captured_as_error_state(self):
        runner = JobRunner(max_workers=1)

        def boom():
            raise ValueError("bad grain geometry")

        jid = runner.submit(boom)
        assert runner.wait(jid, timeout=POLL_TIMEOUT)
        st = runner.status(jid)
        assert st['state'] == STATE_ERROR
        assert 'ValueError' in st['error']
        assert 'bad grain geometry' in st['error']
        assert 'result' not in st

    def test_worker_survives_job_failure(self):
        # Hata worker thread'i öldürmemeli; sonraki iş normal koşmalı
        runner = JobRunner(max_workers=1)
        j1 = runner.submit(lambda: 1 / 0)
        assert runner.wait(j1, timeout=POLL_TIMEOUT)
        assert runner.status(j1)['state'] == STATE_ERROR
        j2 = runner.submit(lambda: 'alive')
        assert runner.wait(j2, timeout=POLL_TIMEOUT)
        assert runner.status(j2)['result'] == 'alive'

    def test_non_callable_submit_rejected(self):
        runner = JobRunner(max_workers=1)
        with pytest.raises(TypeError):
            runner.submit(42)


class TestProgress:
    def test_progress_callback_injected_and_reported(self):
        runner = JobRunner(max_workers=1)
        gate = threading.Event()
        reported = threading.Event()

        def work(progress_callback):
            progress_callback(0.5)
            reported.set()
            gate.wait(POLL_TIMEOUT)
            return 'ok'

        jid = runner.submit(work)
        assert reported.wait(POLL_TIMEOUT)
        assert _poll_until(lambda: runner.status(jid)['progress'] == 0.5)
        assert runner.status(jid)['state'] == STATE_RUNNING
        gate.set()
        assert runner.wait(jid, timeout=POLL_TIMEOUT)
        st = runner.status(jid)
        assert st['state'] == STATE_DONE
        assert st['progress'] == 1.0  # bitişte 1.0'a tamamlanır

    def test_progress_clamped_to_unit_interval(self):
        runner = JobRunner(max_workers=1)
        gate = threading.Event()
        stage = {'n': 0}
        stage_evt = threading.Event()

        def work(progress_callback):
            progress_callback(5.0)   # > 1 -> 1.0'a kırpılır
            stage['n'] = 1
            stage_evt.set()
            gate.wait(POLL_TIMEOUT)
            progress_callback(-3.0)  # < 0 -> 0.0'a kırpılır
            return None

        jid = runner.submit(work)
        assert stage_evt.wait(POLL_TIMEOUT)
        assert _poll_until(lambda: runner.status(jid)['progress'] == 1.0)
        gate.set()
        assert runner.wait(jid, timeout=POLL_TIMEOUT)
        # done olduğunda progress yine 1.0'a çekilir (sözleşme)
        assert runner.status(jid)['progress'] == 1.0

    def test_function_without_progress_param_runs_normally(self):
        runner = JobRunner(max_workers=1)

        def plain(x):
            return x * 2

        jid = runner.submit(plain, 21)
        assert runner.wait(jid, timeout=POLL_TIMEOUT)
        assert runner.status(jid)['result'] == 42

    def test_caller_supplied_progress_callback_not_overridden(self):
        runner = JobRunner(max_workers=1)
        calls = []

        def my_cb(frac):
            calls.append(frac)

        def work(progress_callback):
            progress_callback(0.25)
            return 'done'

        jid = runner.submit(work, progress_callback=my_cb)
        assert runner.wait(jid, timeout=POLL_TIMEOUT)
        assert calls == [0.25]
        # Runner'ın kendi progress'i dokunulmadan kalır (0.0 -> done'da 1.0)
        assert runner.status(jid)['progress'] == 1.0


class TestConcurrency:
    def test_many_jobs_all_complete_with_multiple_workers(self):
        runner = JobRunner(max_workers=4)
        ids = {runner.submit(lambda i=i: i * i): i for i in range(20)}
        for jid, i in ids.items():
            assert runner.wait(jid, timeout=POLL_TIMEOUT)
            assert runner.status(jid)['result'] == i * i

    def test_thread_safe_concurrent_submission(self):
        runner = JobRunner(max_workers=4)
        all_ids = []
        lock = threading.Lock()

        def submitter(base):
            for k in range(5):
                jid = runner.submit(lambda v=base * 10 + k: v)
                with lock:
                    all_ids.append((jid, base * 10 + k))

        threads = [threading.Thread(target=submitter, args=(n,))
                   for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(POLL_TIMEOUT)
        assert len(all_ids) == 40
        assert len({jid for jid, _ in all_ids}) == 40  # kimlik çakışması yok
        for jid, expected in all_ids:
            assert runner.wait(jid, timeout=POLL_TIMEOUT)
            assert runner.status(jid)['result'] == expected


class TestTTL:
    def _runner_with_fake_clock(self, ttl):
        clock = {'t': 0.0}
        runner = JobRunner(max_workers=1, ttl_seconds=ttl,
                           time_fn=lambda: clock['t'])
        return runner, clock

    def test_finished_job_expires_after_ttl(self):
        runner, clock = self._runner_with_fake_clock(ttl=10.0)
        jid = runner.submit(lambda: 'r')
        assert runner.wait(jid, timeout=POLL_TIMEOUT)
        assert runner.status(jid)['state'] == STATE_DONE
        clock['t'] = 10.1  # TTL aşıldı
        assert runner.cleanup_expired() == 1
        with pytest.raises(KeyError):
            runner.status(jid)

    def test_finished_job_kept_within_ttl(self):
        runner, clock = self._runner_with_fake_clock(ttl=10.0)
        jid = runner.submit(lambda: 'r')
        assert runner.wait(jid, timeout=POLL_TIMEOUT)
        clock['t'] = 9.9  # hâlâ pencere içinde
        assert runner.cleanup_expired() == 0
        assert runner.status(jid)['state'] == STATE_DONE

    def test_status_call_purges_expired_jobs(self):
        # cleanup_expired açık çağrısı olmadan da status/submit temizler
        runner, clock = self._runner_with_fake_clock(ttl=5.0)
        j1 = runner.submit(lambda: 1)
        assert runner.wait(j1, timeout=POLL_TIMEOUT)
        clock['t'] = 6.0
        j2 = runner.submit(lambda: 2)  # submit sırasında purge tetiklenir
        assert runner.wait(j2, timeout=POLL_TIMEOUT)
        with pytest.raises(KeyError):
            runner.status(j1)
        assert runner.status(j2)['result'] == 2

    def test_default_ttl_is_one_hour(self):
        assert DEFAULT_TTL_SECONDS == 3600.0

    def test_invalid_constructor_args_rejected(self):
        with pytest.raises(ValueError):
            JobRunner(max_workers=0)
        with pytest.raises(ValueError):
            JobRunner(ttl_seconds=0)


class TestWait:
    def test_wait_times_out_on_blocked_job(self):
        runner = JobRunner(max_workers=1)
        gate = threading.Event()
        jid = runner.submit(lambda: gate.wait(POLL_TIMEOUT))
        assert runner.wait(jid, timeout=0.05) is False
        gate.set()
        assert runner.wait(jid, timeout=POLL_TIMEOUT) is True
        assert runner.status(jid)['state'] == STATE_DONE
