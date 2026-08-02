"""Faz 4B veri güvenliği bekçi testleri (D2, D3, D4, D6).

Kapsanan bulgular:

D2 — Pickle önbelleği kod çalıştırıyordu. ``web_propellant_api._load_cache``
     ``pickle.load`` kullanıyordu; denetimde kurcalanmış bir ``.pkl`` ile
     kabuk çalıştırıldı. Artık yalnız sürümlü + özetli JSON okunur.
D3 — ``offline_store.put`` oku-değiştir-yaz yarışı: 8 süreç × 60 yazmada
     480 kaydın 413'ü kayboluyordu. ``get()`` paylaşılan mutable nesne
     döndürüyordu.
D4 — ``.ork`` DTD/ENTITY bekçisi ham bayt regex'iydi; UTF-16 kodlu aynı
     içerik bekçiyi atlayıp ayrıştırıcıya ulaşıyordu.
D6 — ``job_runner`` kuyruğu ``maxsize=0`` ile kurulmuştu; 5000 iş
     reddedilmedi, iptal API'si yoktu.

Ağa çıkılmaz; kullanıcı-veri dizini her testte tmp_path'e yönlendirilir.
"""

import json
import os
import pickle
import subprocess
import sys
import textwrap
import threading
import time
from datetime import datetime, timedelta

import pytest
import requests

from hrma.data import offline_store
from hrma.data.web_propellant_api import (
    CACHE_SCHEMA_VERSION, DATA_STATE_LIVE, DATA_STATE_OFFLINE,
    DATA_STATE_STALE, web_api,
)
from hrma.importers.ork_import import parse_ork
from hrma.utils.job_runner import (
    JobCancelled, JobQueueFullError, JobRunner, STATE_CANCELLED, STATE_DONE,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLL_TIMEOUT = 5.0


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    """Kullanıcı cache dizinini test başına izole tmp dizine yönlendir."""
    d = tmp_path / "userdata"
    monkeypatch.setenv("HRMA_USER_DATA_DIR", str(d))
    return d


@pytest.fixture
def pkl_dir(tmp_path, monkeypatch):
    """web_api'nin disk önbelleğini izole tmp dizine yönlendir."""
    d = tmp_path / "propcache"
    d.mkdir()
    monkeypatch.setattr(web_api, "cache_dir", str(d))
    monkeypatch.setattr(web_api, "_legacy_reported", set())
    return d


def _agi_kapat(monkeypatch):
    def _patla(*args, **kwargs):
        raise requests.ConnectionError("simulated offline")
    monkeypatch.setattr(web_api.session, "get", _patla)
    monkeypatch.setattr(web_api.session, "post", _patla)


def marker_yaz(yol):
    """Pickle yükünün çağıracağı işaretçi (kod çalıştırma kanıtı).

    Kabuk çağrılmaz: pickle'ın rastgele ÇAĞRILABİLİRİ tetiklediğini
    göstermek için modül düzeyinde sıradan bir fonksiyon yeterlidir.
    """
    with open(yol, "w", encoding="utf-8") as f:
        f.write("pwned")
    return {"compound": "lox", "density": 999.9, "status": "success"}


class _KotuYuk:
    """``pickle.load`` sırasında marker_yaz() çağıran yük."""

    def __init__(self, yol):
        self.yol = yol

    def __reduce__(self):
        return (marker_yaz, (self.yol,))


# ===========================================================================
# D2 — pickle önbelleği kod çalıştırıyordu
# ===========================================================================

def test_d2_kurcalanmis_pickle_kod_calistirmiyor(pkl_dir, user_dir, tmp_path,
                                                 monkeypatch):
    """Eski biçim (.pkl) önbellek yüklenmez → kod çalışmaz, veri kabul edilmez."""
    _agi_kapat(monkeypatch)
    marker = tmp_path / "PWNED.txt"
    cache_key = web_api._get_cache_key("nist", "lox")

    # Denetimdeki saldırının birebir kurulumu: kurcalanmış .pkl, tahmin
    # edilebilir dizinde, tahmin edilebilir adla.
    with open(pkl_dir / f"{cache_key}.pkl", "wb") as f:
        pickle.dump({"data": _KotuYuk(str(marker)),
                     "timestamp": datetime.now()}, f)

    out = web_api.fetch_nist_data("lox")

    assert not marker.exists(), "pickle yükü ÇALIŞTI — kod çalıştırma açığı açık"
    # Yük çalışsaydı density 999.9 olurdu; statik tablo 1141.7 döndürür
    assert out["density"] != 999.9
    assert out.get("data_state") != DATA_STATE_LIVE


def test_d2_pickle_dosyasi_silinmiyor(pkl_dir, user_dir, monkeypatch):
    """Geçişte kullanıcının eski dosyası yok sayılır ama SİLİNMEZ."""
    _agi_kapat(monkeypatch)
    cache_key = web_api._get_cache_key("nist", "lox")
    legacy = pkl_dir / f"{cache_key}.pkl"
    with open(legacy, "wb") as f:
        pickle.dump({"data": {"density": 1.0}, "timestamp": datetime.now()}, f)

    web_api.fetch_nist_data("lox")
    assert legacy.exists()


def test_d2_kurcalanmis_json_reddediliyor(pkl_dir, user_dir, monkeypatch):
    """İçerik özeti tutmayan JSON kaydı kabul edilmez."""
    _agi_kapat(monkeypatch)
    cache_key = web_api._get_cache_key("nist", "lox")
    web_api._save_cache(cache_key, {"compound": "lox", "density": 777.7,
                                    "status": "success"},
                        source_url="https://example.invalid/x")

    yol = pkl_dir / f"{cache_key}.json"
    kayit = json.loads(yol.read_text(encoding="utf-8"))
    assert kayit["schema_version"] == CACHE_SCHEMA_VERSION
    assert kayit["source_url"] == "https://example.invalid/x"
    assert kayit["content_hash"] and kayit["expires_at"]

    # Taze kayıt normalde kullanılır
    assert web_api.fetch_nist_data("lox")["density"] == 777.7

    # Gövde elle değiştirilir; özet artık tutmaz
    kayit["data"]["density"] = 111.1
    yol.write_text(json.dumps(kayit), encoding="utf-8")
    assert web_api._read_cache_record(cache_key) is None
    assert web_api.fetch_nist_data("lox")["density"] != 111.1


def test_d2_yanlis_sema_surumu_reddediliyor(pkl_dir, user_dir, monkeypatch):
    """Gelecekteki/eski şema sürümü sessizce kabul edilmez."""
    _agi_kapat(monkeypatch)
    cache_key = web_api._get_cache_key("nist", "lox")
    web_api._save_cache(cache_key, {"density": 1.0, "status": "success"})
    yol = pkl_dir / f"{cache_key}.json"
    kayit = json.loads(yol.read_text(encoding="utf-8"))
    kayit["schema_version"] = CACHE_SCHEMA_VERSION + 99
    yol.write_text(json.dumps(kayit), encoding="utf-8")
    assert web_api._read_cache_record(cache_key) is None


def test_d2_anahtar_dosya_adi_baglantisi(pkl_dir, user_dir, monkeypatch):
    """Bir anahtarın kaydı başka bir anahtarın dosyasına konamaz."""
    _agi_kapat(monkeypatch)
    kaynak = web_api._get_cache_key("nist", "lox")
    hedef = web_api._get_cache_key("nist", "lh2")
    web_api._save_cache(kaynak, {"density": 1141.7, "status": "success"})
    (pkl_dir / f"{hedef}.json").write_text(
        (pkl_dir / f"{kaynak}.json").read_text(encoding="utf-8"),
        encoding="utf-8")
    assert web_api._read_cache_record(hedef) is None


def test_d2_bayat_kayit_live_etiketi_almiyor(pkl_dir, user_dir, monkeypatch):
    """Süresi geçmiş kayıt 'Live' etiketiyle sunulmaz (stale-if-error)."""
    _agi_kapat(monkeypatch)
    cache_key = web_api._get_cache_key("nist", "lox")
    web_api._save_cache(cache_key, {"compound": "lox", "density": 999.9,
                                    "status": "success",
                                    "source": "NIST API (Live)"})

    # Kaydı 10 yıl geriye al (denetimdeki senaryo)
    yol = pkl_dir / f"{cache_key}.json"
    kayit = json.loads(yol.read_text(encoding="utf-8"))
    eski = datetime.now() - timedelta(days=3650)
    kayit["fetched_at"] = eski.isoformat(timespec="seconds")
    kayit["expires_at"] = (eski + timedelta(hours=1)).isoformat(timespec="seconds")
    yol.write_text(json.dumps(kayit), encoding="utf-8")

    out = web_api.fetch_nist_data("lox")

    # Bayat veri hâlâ servis edilir (stale-if-error sözleşmesi korunur)...
    assert out["density"] == 999.9
    # ...ama artık 'Live' değil, 'stale' olarak işaretlidir
    assert out["data_state"] == DATA_STATE_STALE
    assert "live" not in out["source"].lower()
    assert out["cache_age_seconds"] > 3600


def test_d2_taze_kayit_cached_damgali(pkl_dir, user_dir, monkeypatch):
    """TTL içindeki kayıt 'cached' damgası taşır, 'live' değil."""
    _agi_kapat(monkeypatch)
    cache_key = web_api._get_cache_key("nist", "lox")
    web_api._save_cache(cache_key, {"compound": "lox", "density": 888.8,
                                    "status": "success",
                                    "source": "NIST API (Live)"})
    out = web_api.fetch_nist_data("lox")
    assert out["density"] == 888.8
    assert out["data_state"] == "cached"
    assert "live" not in out["source"].lower()


def test_d2_kalici_depo_yolu_offline_damgali(pkl_dir, user_dir):
    """Kalıcı depodan gelen kayıt 'offline' damgalıdır."""
    key = offline_store.make_key("webapi", "nist", "testfuelx")
    offline_store.put(key, {"compound": "testfuelx", "density": 123.4,
                            "status": "success",
                            "source": "NIST API (Live)"})
    out = web_api.fetch_nist_data("testfuelx")
    assert out["density"] == 123.4
    assert out["data_state"] == DATA_STATE_OFFLINE
    assert "live" not in out["source"].lower()


def test_d2_onbellek_dosyasi_sadece_sahibine_acik(pkl_dir, user_dir):
    """Yazılan kayıt 0600 izinlidir (tahmin edilebilir dizin savunması)."""
    cache_key = web_api._get_cache_key("nist", "lox")
    web_api._save_cache(cache_key, {"density": 1.0, "status": "success"})
    mod = os.stat(pkl_dir / f"{cache_key}.json").st_mode & 0o777
    assert mod == 0o600, oct(mod)


# ===========================================================================
# D3 — offline_store yazma yarışı + paylaşılan mutable dönüş
# ===========================================================================

_YAZICI_BETIK = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {repo!r})
    os.environ['HRMA_USER_DATA_DIR'] = sys.argv[1]
    from hrma.data import offline_store
    pid = sys.argv[2]
    for i in range({adet}):
        assert offline_store.put('p%s:k%d' % (pid, i), {{'v': i}}) is True
""")


def test_d3_paralel_yazmada_kayit_kaybi_yok(tmp_path):
    """8 süreç × 60 yazma → SIFIR kayıp (düzeltme öncesi 413/480 kayıptı)."""
    surec_sayisi, yazma_sayisi = 8, 60
    veri_dir = tmp_path / "userdata"
    veri_dir.mkdir()
    betik = tmp_path / "yazici.py"
    betik.write_text(_YAZICI_BETIK.format(repo=REPO_ROOT, adet=yazma_sayisi),
                     encoding="utf-8")

    surecler = [
        subprocess.Popen([sys.executable, str(betik), str(veri_dir), str(i)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for i in range(surec_sayisi)
    ]
    for p in surecler:
        _, err = p.communicate(timeout=180)
        assert p.returncode == 0, err.decode(errors="replace")

    doc = json.loads((veri_dir / "propellant_cache.json").read_text(encoding="utf-8"))
    beklenen = surec_sayisi * yazma_sayisi
    assert len(doc["entries"]) == beklenen, (
        f"{beklenen - len(doc['entries'])} kayıt kayboldu")
    for pid in range(surec_sayisi):
        for i in range(yazma_sayisi):
            assert doc["entries"][f"p{pid}:k{i}"]["data"] == {"v": i}


def test_d3_thread_paralel_yazmada_kayip_yok(user_dir):
    """Aynı süreç içinde 8 thread × 30 yazma → sıfır kayıp."""
    thread_sayisi, yazma_sayisi = 8, 30
    hatalar = []

    def yaz(tid):
        try:
            for i in range(yazma_sayisi):
                assert offline_store.put(f"t{tid}:k{i}", {"v": i}) is True
        except Exception as exc:  # pragma: no cover - başarısızlıkta rapor
            hatalar.append(exc)

    threadler = [threading.Thread(target=yaz, args=(t,))
                 for t in range(thread_sayisi)]
    for t in threadler:
        t.start()
    for t in threadler:
        t.join(timeout=120)

    assert not hatalar, hatalar
    doc = json.loads((user_dir / "propellant_cache.json").read_text(encoding="utf-8"))
    assert len(doc["entries"]) == thread_sayisi * yazma_sayisi


def test_d3_get_donusu_degistirilince_onbellek_bozulmuyor(user_dir):
    """get() derin kopya döndürür: çağıran mutasyonu depoyu etkilemez."""
    key = offline_store.make_key("webapi", "mutasyon-testi")
    offline_store.put(key, {"density": 815.0, "nested": {"list": [1, 2, 3]}})

    ilk = offline_store.get(key)
    ilk["density"] = -1.0
    ilk["nested"]["list"].append(999)
    ilk["nested"]["yeni"] = "kirlilik"

    ikinci = offline_store.get(key)
    assert ikinci["density"] == 815.0
    assert ikinci["nested"]["list"] == [1, 2, 3]
    assert "yeni" not in ikinci["nested"]
    assert ikinci is not ilk


def test_d3_snapshot_donusu_de_kopya(tmp_path, monkeypatch, user_dir):
    """Paketli snapshot'tan gelen kayıt da kopyadır (paket verisi kirlenmez)."""
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({
        "_meta": {"note": "test"},
        "entries": {"pubchem:foo": {"data": {"x": [1]}, "timestamp": "t"}},
    }), encoding="utf-8")
    monkeypatch.setattr(offline_store, "SNAPSHOT_PATH", str(snap))

    a = offline_store.get("pubchem:foo")
    a["x"].append(2)
    assert offline_store.get("pubchem:foo")["x"] == [1]


# ===========================================================================
# D4 — .ork XXE bekçisi kodlamadan bağımsız olmalı
# ===========================================================================

_XXE_SABLONU = ('<?xml version="1.0" encoding="{enc}"?>'
                '<!DOCTYPE openrocket ['
                '<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
                '<openrocket><rocket><subcomponents><stage/>'
                '</subcomponents></rocket></openrocket>')

_TEMIZ_SABLON = ('<?xml version="1.0" encoding="{enc}"?>'
                 '<openrocket><rocket><subcomponents><stage/>'
                 '</subcomponents></rocket></openrocket>')


@pytest.mark.parametrize("bildirim,kodlama", [
    ("UTF-8", "utf-8"),
    ("UTF-16", "utf-16"),     # BOM'lu
    ("UTF-16", "utf-16-be"),
    ("UTF-16", "utf-16-le"),
])
def test_d4_dtd_her_kodlamada_reddediliyor(bildirim, kodlama):
    """UTF-16 kopyası da reddedilmeli (düzeltme öncesi ayrıştırıcıya ulaşıyordu)."""
    ham = _XXE_SABLONU.format(enc=bildirim).encode(kodlama)
    hata = parse_ork(ham).get("error", "")
    assert "security" in hata, f"{kodlama}: {hata!r}"


def test_d4_bildirimsiz_utf16_dtd_reddediliyor():
    """XML bildirimi olmayan, BOM'suz UTF-16LE belge de yakalanır."""
    ham = ('<!DOCTYPE openrocket [<!ENTITY x "y">]>'
           '<openrocket><rocket/></openrocket>').encode("utf-16-le")
    assert "security" in parse_ork(ham).get("error", "")


def test_d4_billion_laughs_utf16_reddediliyor():
    """İç varlık patlaması (billion laughs) UTF-16'da da reddedilir."""
    ham = ('<?xml version="1.0"?><!DOCTYPE lolz ['
           '<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>'
           '<openrocket>&lol2;</openrocket>').encode("utf-16")
    assert "security" in parse_ork(ham).get("error", "")


@pytest.mark.parametrize("bildirim,kodlama", [
    ("UTF-8", "utf-8"),
    ("UTF-16", "utf-16"),
])
def test_d4_temiz_belge_bekciye_takilmiyor(bildirim, kodlama):
    """Yanlış pozitif yok: DTD'siz belge güvenlik reddi almaz."""
    ham = _TEMIZ_SABLON.format(enc=bildirim).encode(kodlama)
    hata = parse_ork(ham).get("error", "")
    assert "security" not in hata, hata


def test_d4_gzip_icindeki_utf16_dtd_reddediliyor():
    """Sıkıştırılmış kapta gelen UTF-16 DTD de açıldıktan sonra yakalanır."""
    import gzip
    ham = gzip.compress(_XXE_SABLONU.format(enc="UTF-16").encode("utf-16"))
    assert "security" in parse_ork(ham).get("error", "")


# ===========================================================================
# D6 — iş kuyruğu kapasitesi ve iptal
# ===========================================================================

def _poll_until(kosul, timeout=POLL_TIMEOUT):
    son = time.monotonic() + timeout
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.005)
    return False


def test_d6_kuyruk_doluyken_is_reddediliyor():
    """Kapasite aşıldığında submit açıkça reddeder (5000 iş sessizce yutulmaz)."""
    runner = JobRunner(max_workers=1, max_queued=3)
    kapi = threading.Event()
    basladi = threading.Event()

    def tikayici():
        basladi.set()
        kapi.wait(POLL_TIMEOUT)

    runner.submit(tikayici)                       # worker'ı meşgul et
    assert basladi.wait(POLL_TIMEOUT)
    for _ in range(runner.queue_capacity):        # kuyruğu doldur
        runner.submit(lambda: None)

    onceki = runner.job_count()
    with pytest.raises(JobQueueFullError) as exc:
        runner.submit(lambda: None)
    assert "full" in str(exc.value).lower()
    assert exc.value.http_status == 503
    # Reddedilen iş ARDINDA KAYIT BIRAKMAZ
    assert runner.job_count() == onceki

    kapi.set()


def test_d6_varsayilan_kuyruk_sinirli():
    """Genel tekil kuyruk artık sınırsız değil."""
    runner = JobRunner(max_workers=1)
    assert runner.queue_capacity > 0
    assert runner._queue.maxsize == runner.queue_capacity


def test_d6_yer_acilinca_tekrar_kabul_ediliyor():
    """Kapasite dolması kalıcı değil: işler bitince yeni iş kabul edilir."""
    runner = JobRunner(max_workers=1, max_queued=2)
    kapi = threading.Event()
    basladi = threading.Event()

    def tikayici():
        basladi.set()
        kapi.wait(POLL_TIMEOUT)

    runner.submit(tikayici)
    assert basladi.wait(POLL_TIMEOUT)
    for _ in range(2):
        runner.submit(lambda: None)
    with pytest.raises(JobQueueFullError):
        runner.submit(lambda: None)

    kapi.set()
    assert _poll_until(lambda: runner.pending_count() == 0)
    jid = runner.submit(lambda: 42)
    assert runner.wait(jid, timeout=POLL_TIMEOUT)
    assert runner.status(jid)["result"] == 42


def test_d6_kuyruktaki_is_iptal_edilebiliyor():
    """Henüz başlamamış iş iptal edilir ve HİÇ çalışmaz."""
    runner = JobRunner(max_workers=1, max_queued=8)
    kapi = threading.Event()
    basladi = threading.Event()
    calisti = threading.Event()

    def tikayici():
        basladi.set()
        kapi.wait(POLL_TIMEOUT)

    runner.submit(tikayici)
    assert basladi.wait(POLL_TIMEOUT)
    jid = runner.submit(calisti.set)

    assert runner.cancel(jid) is True
    assert runner.status(jid)["state"] == STATE_CANCELLED
    assert runner.status(jid)["cancel_requested"] is True

    kapi.set()
    assert runner.wait(jid, timeout=POLL_TIMEOUT)
    assert not calisti.is_set(), "iptal edilen iş yine de çalıştı"
    assert runner.status(jid)["state"] == STATE_CANCELLED


def test_d6_kosan_is_ilerleme_noktasinda_iptal_oluyor():
    """İşbirlikçi iptal: progress_callback çağıran uzun iş durur."""
    runner = JobRunner(max_workers=1, max_queued=8)
    basladi = threading.Event()
    tamamlandi = threading.Event()

    def uzun_is(progress_callback=None):
        basladi.set()
        for i in range(2000):
            progress_callback(i / 2000.0)
            time.sleep(0.001)
        tamamlandi.set()
        return "bitti"

    jid = runner.submit(uzun_is)
    assert basladi.wait(POLL_TIMEOUT)
    assert runner.cancel(jid) is True
    assert runner.wait(jid, timeout=POLL_TIMEOUT)
    assert runner.status(jid)["state"] == STATE_CANCELLED
    assert not tamamlandi.is_set()


def test_d6_cancel_event_parametresi_enjekte_ediliyor():
    """``cancel_event`` parametresi olan iş, olayı doğrudan okuyabilir."""
    runner = JobRunner(max_workers=1, max_queued=8)
    basladi = threading.Event()

    def is_fn(cancel_event=None):
        basladi.set()
        if cancel_event.wait(POLL_TIMEOUT):
            raise JobCancelled("iptal edildi")
        return "bitmedi"

    jid = runner.submit(is_fn)
    assert basladi.wait(POLL_TIMEOUT)
    runner.cancel(jid)
    assert runner.wait(jid, timeout=POLL_TIMEOUT)
    assert runner.status(jid)["state"] == STATE_CANCELLED


def test_d6_biten_isin_iptali_false_doner():
    """Bitmiş iş iptal edilemez; sonucu da bozulmaz."""
    runner = JobRunner(max_workers=1, max_queued=8)
    jid = runner.submit(lambda: 7)
    assert runner.wait(jid, timeout=POLL_TIMEOUT)
    assert runner.cancel(jid) is False
    st = runner.status(jid)
    assert st["state"] == STATE_DONE and st["result"] == 7


def test_d6_bilinmeyen_is_iptalinde_keyerror():
    runner = JobRunner(max_workers=1)
    with pytest.raises(KeyError):
        runner.cancel("yok-boyle-bir-is")
