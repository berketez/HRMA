"""ÖH D37 A2-2 · sivi-sogutma — STEP uçtan uca bekçileri (YALNIZ step-export).

Denetçi Ş7 (4. tur): bu iki test üretilen montaj STEP dosyasının KENDİ
metnini okur ve build123d ister. ``tests/test_d37_sivi_a1.py`` içinde
``pytest.importorskip('build123d')`` ile duruyorlardı; ana ``pytest`` işi
build123d KURMADIĞI için orada iki ATLAMA üretiyor, ölçülmüş atlama bütçesini
(``tools/atlama_kapisi.py`` ATLAMA_BUTCESI) +2 aşıyordu.

Bu dosya bilerek ``test_*.py`` desenine UYMAZ: ana işin ``pytest tests/``
komutu onu toplamaz; ``.github/workflows/tests.yml`` ``step-export`` işi onu
ADIYLA koşar (pytest komut satırında verilen dosyayı desenden bağımsız
toplar). O iş build123d'yi kurar ve fail-closed doğrular; bu yüzden burada
``importorskip`` YOKTUR — build123d yoksa bu dosya ATLAMAZ, HATA verir.
İş akışı değişikliği ve kapsam bekçisinin beyaz listesi yama olarak:
``docs/scofield/raw/OH/A2/sivi-sogutma/a1/patch/tests_yml_step_export.patch``
ve ``.../patch/ci_kapsam_step_dosyasi.patch``.
"""
import tempfile

from tests.test_d37_sivi_a1 import _sessiz, _sivi, istemci  # noqa: F401


def _montaj_metni(d, onek):
    from hrma.export.step_export import generate_step_assembly
    cikis = tempfile.mkdtemp(prefix=onek)
    dosyalar = _sessiz(generate_step_assembly, d, out_dir=cikis,
                       motor_type='liquid')
    return open(dosyalar['assembly'], encoding='utf-8',
                errors='replace').read()


def test_f18a_montaj_step_dosyasi_beyani_tasir(istemci):  # noqa: F811
    """Uçtan uca: üretilen montaj STEP'inin KENDİ metninde beyan var."""
    d = _sivi(istemci)
    n = d['cooling_system']['cooling_channels']
    metin = _montaj_metni(d, 'hrma-d37-sivi-step-')
    assert 'cooling_channels: NOT_MODELLED (n=%d, w=3.00 mm' % n in metin


def test_d12_sigmayan_kullanici_n_step_dosyasinda(istemci):  # noqa: F811
    """D12 uçtan uca: üretilen montaj STEP metninde n = kullanıcının N'si."""
    d = _sivi(istemci, cooling_channels=80)
    assert d['cooling_system']['channel_count_fit']['n_max'] != 80
    metin = _montaj_metni(d, 'hrma-d37-sivi-step80-')
    assert 'cooling_channels: NOT_MODELLED (n=80, w=3.00 mm' in metin
