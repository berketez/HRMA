"""Örnek proje tohumlamasının bekçileri (v2.6.26 bakım dalgası).

Kurulu üründe kullanıcı proje dizini ilk açılışta boştur; paketle gelen üç
örnek .hrma projesi İLK açılışta BİR KEZ kopyalanır. Bu testler şu
sözleşmeyi kilitler (hrma/utils/projects.py::seed_examples +
hrma/app.py::_seed_examples_once):

  1. Kaynak çözümü iki yerleşimde de çalışır: geliştirme (depo kökündeki
     examples/) ve paketli ürün (paket kökünün YANINDAKİ examples/ —
     macOS'ta Resources/app/examples, Windows'ta <INSTDIR>/app/examples).
     Dizin yoksa uydurma yol DEĞİL, açıkça 'no_source' döner.
  2. Tohumlama damga dosyasıyla (.seeded_v1) BİR keredir: kullanıcı
     örnekleri silerse her açılışta geri GELMEZLER.
  3. Var olan dosya ASLA ezilmez — kullanıcı aynı adla kendi projesini
     kaydetmiş olabilir; atlanan dosyalar dönüşte beyan edilir.
  4. Ad kuralına uymayan kaynak dosya kopyalanmaz (kopyalansa
     list_projects onu 'unloadable' işaretlerdi) ve beyan edilir.
  5. Uygulama kancası ilk istekte çalışır, pytest altında çalışmaz
     (aksi halde HRMA_PROJECTS_DIR ayarlamayan her test gerçek kullanıcı
     dizinine yazardı) ve süreç başına bir kez denenir.

Örneklerin İÇERİĞİNİN doğruluğu ayrı bekçinin işi
(tests/test_example_projects.py); burada yalnız tohumlama davranışı sınanır.
"""

import json
import os
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / 'examples'

#: Depoyla birlikte gelen üç örnek (tek doğruluk kaynağı:
#: tests/test_example_projects.py::NAMES — burada dosya adı düzeyinde).
EXPECTED_EXAMPLES = [
    'Example Hybrid N2O-HTPB 3kN.hrma',
    'Example Liquid LOX-RP1 25kN.hrma',
    'Example Solid KNDX BATES 75mm.hrma',
]


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Proje deposunu tmp'ye, örnek kaynağını depo examples/'ına bağla."""
    from hrma.utils import projects
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(tmp_path / 'projects'))
    monkeypatch.delenv('HRMA_EXAMPLES_DIR', raising=False)
    return projects


def _write_example(dirpath, filename, payload='{"format": "hrma-project"}'):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / filename).write_text(payload, encoding='utf-8')


# ---------------------------------------------------------------------------
# 1. Kaynak çözümü — geliştirme ve paketli yerleşim
# ---------------------------------------------------------------------------

def test_dev_yerlesiminde_kaynak_depo_kokudur(store):
    """Geliştirme modunda kaynak = depo kökündeki examples/ dizinidir."""
    source = store.examples_source_dir()
    assert source is not None
    assert pathlib.Path(source).resolve() == EXAMPLES_DIR.resolve()
    mevcut = sorted(os.listdir(source))
    for filename in EXPECTED_EXAMPLES:
        assert filename in mevcut, f'{filename} depo examples/ dizininde yok'


def test_paketli_yerlesimde_kaynak_paket_yanidir(store, tmp_path, monkeypatch):
    """Paketli üründe kaynak, hrma paket kökünün YANINDAKİ examples/.

    self_install.py yerleşim şeması taklit edilir:
    .../Resources/app/hrma (paket) → .../Resources/app/examples (örnekler).
    """
    app_root = tmp_path / 'Resources' / 'app'
    (app_root / 'hrma').mkdir(parents=True)
    _write_example(app_root / 'examples', 'Example Packaged.hrma')
    monkeypatch.setattr(store, '_package_dir',
                        lambda: str(app_root / 'hrma'))
    source = store.examples_source_dir()
    assert source == str(app_root / 'examples')

    info = store.seed_examples()
    assert info['status'] == 'seeded'
    assert info['copied'] == ['Example Packaged.hrma']
    assert (pathlib.Path(store.projects_dir())
            / 'Example Packaged.hrma').exists()


def test_kaynak_dizin_yoksa_no_source(store, tmp_path, monkeypatch):
    """Kaynak yoksa uydurma yol dönmez; damga da yazılmaz (sonra denenir)."""
    bos_kok = tmp_path / 'yalniz_paket' / 'hrma'
    bos_kok.mkdir(parents=True)  # yanında examples/ YOK
    monkeypatch.setattr(store, '_package_dir', lambda: str(bos_kok))
    assert store.examples_source_dir() is None

    info = store.seed_examples()
    assert info['status'] == 'no_source'
    assert info['copied'] == []
    stamp = pathlib.Path(store.projects_dir()) / store.SEED_STAMP_FILENAME
    assert not stamp.exists(), (
        'no_source damga yazmamalı: kaynak sonradan gelirse tohumlama '
        'yeniden denenebilmeli')


def test_ortam_degiskeni_kaynagi_ezer(store, tmp_path, monkeypatch):
    """HRMA_EXAMPLES_DIR verilirse paket yerleşimine hiç bakılmaz."""
    ozel = tmp_path / 'ozel_kaynak'
    _write_example(ozel, 'Example Env.hrma')
    monkeypatch.setenv('HRMA_EXAMPLES_DIR', str(ozel))
    assert store.examples_source_dir() == str(ozel)
    # Var ama dizin değilse / yoksa: None (uydurma yol yasak)
    monkeypatch.setenv('HRMA_EXAMPLES_DIR', str(tmp_path / 'yok'))
    assert store.examples_source_dir() is None


# ---------------------------------------------------------------------------
# 2. Tohumlama davranışı — bir kez, ezmeden, beyanla
# ---------------------------------------------------------------------------

def test_gelistirme_modunda_uc_ornek_tohumlanir(store):
    """Depo örnekleri boş depoya kopyalanır ve depodan yüklenebilir."""
    info = store.seed_examples()
    assert info['status'] == 'seeded'
    assert info['copied'] == EXPECTED_EXAMPLES
    assert info['skipped_existing'] == []
    assert info['skipped_invalid'] == []

    stamp = pathlib.Path(store.projects_dir()) / store.SEED_STAMP_FILENAME
    assert stamp.exists()
    stamp_doc = json.loads(stamp.read_text(encoding='utf-8'))
    assert stamp_doc['copied'] == EXPECTED_EXAMPLES

    # Kopyalar uygulamanın kendi deposundan gerçekten yüklenebilir olmalı
    # (bozuk kopya = açılışta üç 'corrupt' işaretli proje).
    listed = {p['name'] for p in store.list_projects() if not p['corrupt']}
    for filename in EXPECTED_EXAMPLES:
        assert filename[:-len(store.FILE_EXT)] in listed

    # Damga dosyası proje olarak listelenmez (nokta ile başlar).
    assert not any(store.SEED_STAMP_FILENAME in name for name in listed)


def test_var_olan_dosya_ezilmez(store, tmp_path):
    """Kullanıcının aynı adlı dosyası tohumlamada aynen korunur."""
    dest = pathlib.Path(store.projects_dir())
    dest.mkdir(parents=True, exist_ok=True)
    kullanici_icerigi = '{"benim": "projem"}'
    (dest / EXPECTED_EXAMPLES[0]).write_text(kullanici_icerigi,
                                             encoding='utf-8')
    info = store.seed_examples()
    assert info['status'] == 'seeded'
    assert info['skipped_existing'] == [EXPECTED_EXAMPLES[0]]
    assert EXPECTED_EXAMPLES[0] not in info['copied']
    assert ((dest / EXPECTED_EXAMPLES[0]).read_text(encoding='utf-8')
            == kullanici_icerigi), 'kullanıcı dosyası ezildi!'


def test_damga_sonrasi_silinen_ornek_geri_gelmez(store):
    """Kullanıcı örneği silerse sonraki tohumlama onu geri getirmez."""
    assert store.seed_examples()['status'] == 'seeded'
    silinen = pathlib.Path(store.projects_dir()) / EXPECTED_EXAMPLES[1]
    silinen.unlink()

    info = store.seed_examples()
    assert info['status'] == 'already_seeded'
    assert info['copied'] == []
    assert not silinen.exists(), 'silinen örnek geri geldi!'


def test_gecersiz_adli_kaynak_kopyalanmaz(store, tmp_path, monkeypatch):
    """Ad kuralını bozan kaynak dosya atlanır ve beyan edilir."""
    kaynak = tmp_path / 'kirli_kaynak'
    _write_example(kaynak, 'Example Valid.hrma')
    _write_example(kaynak, 'CON.hrma')          # Windows ayrılmış adı
    _write_example(kaynak, 'notlar.txt')        # .hrma değil: sessizce dışta
    _write_example(kaynak, '.gizli.hrma')       # dot-dosya: sessizce dışta
    monkeypatch.setenv('HRMA_EXAMPLES_DIR', str(kaynak))

    info = store.seed_examples()
    assert info['status'] == 'seeded'
    assert info['copied'] == ['Example Valid.hrma']
    assert info['skipped_invalid'] == ['CON.hrma']
    dest = pathlib.Path(store.projects_dir())
    assert sorted(p.name for p in dest.iterdir()) == [
        store.SEED_STAMP_FILENAME, 'Example Valid.hrma']


# ---------------------------------------------------------------------------
# 3. Uygulama kancası — ilk istekte, pytest altında asla
# ---------------------------------------------------------------------------

@pytest.fixture()
def hook_env(store, tmp_path, monkeypatch):
    """Kancayı tmp depo + tmp kaynakla sınamak için ortam kur."""
    import hrma.app as app_module
    kaynak = tmp_path / 'kanca_kaynak'
    _write_example(kaynak, 'Example Hook.hrma')
    monkeypatch.setenv('HRMA_EXAMPLES_DIR', str(kaynak))
    # Süreç-başına bayrak monkeypatch ile geri sarılır: bu test diğer
    # testlerin kanca durumunu değiştirmiş olmaz.
    monkeypatch.setitem(app_module._example_seed_state, 'done', False)
    return app_module, kaynak


def test_kanca_ilk_istekte_tohumlar_ve_bir_kez_calisir(hook_env, store,
                                                       monkeypatch):
    app_module, kaynak = hook_env
    # Kancanın pytest bekçisini AÇIKÇA kaldırıyoruz — gerçek ilk açılış taklidi.
    monkeypatch.delenv('PYTEST_CURRENT_TEST')
    client = app_module.app.test_client()

    resp = client.get('/')
    assert resp.status_code == 200
    dest = pathlib.Path(store.projects_dir())
    assert (dest / 'Example Hook.hrma').exists()
    assert (dest / store.SEED_STAMP_FILENAME).exists()
    assert app_module._example_seed_state['done'] is True

    # Süreç başına bir kez: damga silinse bile aynı süreçte ikinci istek
    # diske dönmez (bir sonraki uygulama açılışı zaten yeniden dener).
    (dest / store.SEED_STAMP_FILENAME).unlink()
    (dest / 'Example Hook.hrma').unlink()
    client.get('/')
    assert not (dest / 'Example Hook.hrma').exists()


def test_kanca_pytest_altinda_tohumlamaz(hook_env, store):
    """PYTEST_CURRENT_TEST varken kanca diske DOKUNMAZ, bayrağı da yakmaz."""
    app_module, kaynak = hook_env
    assert 'PYTEST_CURRENT_TEST' in os.environ  # pytest bunu kendisi koyar
    client = app_module.app.test_client()
    resp = client.get('/')
    assert resp.status_code == 200
    dest = pathlib.Path(store.projects_dir())
    assert not (dest / 'Example Hook.hrma').exists()
    assert not (dest / store.SEED_STAMP_FILENAME).exists()
    # Bayrak yanmaz: gerçek açılışta (pytest dışı) tohumlama hâlâ yapılabilir.
    assert app_module._example_seed_state['done'] is False
