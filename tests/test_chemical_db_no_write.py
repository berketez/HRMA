"""chemical_database import'unun diske yazmadigini garanti eden bekciler.

v2.6.26 dogrulama turu bulgulari (DBIMPORT-1/2/3): v2.6.26 oncesinde modul
import'u 38 sqlite baglantisi acip 37 INSERT yapiyordu; data/chemical_species.db
her import'ta yeniden yaziliyordu (mtime + icerik). Sonuclari:
  - salt-okunur kurulumda 37 hata satiri, DB'siz salt-okunur dizinde cokme,
  - imzali .app bundle icinde her acilista muhur bozulmasi riski.
SQLite katmani salt-yazilir olu katmandi (dosyada tek SELECT yoktu); kalicilik
import yolundan cikarildi, yalniz acikca cagrilan export_sqlite() kaldi.

Bu testler yazma geri gelirse kirmizi olur:
  - import sirasinda SIFIR sqlite baglantisi,
  - data/chemical_species.db mtime/icerigi degismez,
  - salt-okunur dizin senaryosunda import cokmez,
  - species_data tuketici API'si bozulmaz.
"""

import hashlib
import os
import sqlite3
import subprocess
import sys
import textwrap

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO_ROOT, 'data', 'chemical_species.db')

EXPECTED_SPECIES_COUNT = 37


def _snapshot(path):
    """Dosyanin (mtime_ns, sha256) cifti; dosya yoksa None."""
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return (os.stat(path).st_mtime_ns, digest)


def _run_python(code, extra_env=None):
    """Temiz bir alt surecte Python kodu calistir (taze import icin)."""
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, '-c', code],
        capture_output=True, text=True, cwd=REPO_ROOT, env=env, timeout=300,
    )


def test_import_opens_zero_sqlite_connections_and_leaves_db_untouched():
    """Bekci: import yolu (app.py'nin kullandigi zincir dahil) sifir sqlite
    baglantisi acar ve data/chemical_species.db dosyasina dokunmaz."""
    before = _snapshot(DB_PATH)

    code = textwrap.dedent("""
        import sys, sqlite3
        sys.path.insert(0, {root!r})

        count = {{'n': 0}}
        real_connect = sqlite3.connect
        def wrapped(*args, **kwargs):
            count['n'] += 1
            return real_connect(*args, **kwargs)
        sqlite3.connect = wrapped

        import hrma.data.chemical_database as m

        print('CONNECTS=%d' % count['n'])
        print('SPECIES=%d' % m.chemical_db.get_species_count())
    """).format(root=REPO_ROOT)

    result = _run_python(code)
    assert result.returncode == 0, (
        'import coktu:\n%s\n%s' % (result.stdout, result.stderr))
    assert 'CONNECTS=0' in result.stdout, (
        'import sirasinda sqlite baglantisi acildi (yazma geri mi geldi?):\n%s'
        % result.stdout)
    assert ('SPECIES=%d' % EXPECTED_SPECIES_COUNT) in result.stdout, result.stdout

    after = _snapshot(DB_PATH)
    if before is None:
        # Taze klon: dosya yoktu, import onu OLUSTURMAMALI
        assert after is None, 'import data/chemical_species.db olusturdu'
    else:
        assert before == after, (
            'import data/chemical_species.db dosyasini degistirdi '
            '(mtime veya icerik)')


def test_import_survives_readonly_dir_without_db(tmp_path):
    """Senaryo B regresyonu: yazilamaz dizin + DB yok -> v2.6.25'te
    OperationalError ile uygulama hic acilmiyordu; artik import cokmemeli."""
    ro_parent = tmp_path / 'ro'
    ro_parent.mkdir()
    data_dir = ro_parent / 'data'  # yok ve olusturulamaz
    ro_parent.chmod(0o500)

    try:
        code = textwrap.dedent("""
            import sys
            sys.path.insert(0, {root!r})
            import hrma
            hrma.DATA_DIR = {data_dir!r}
            import hrma.data.chemical_database as m
            print('SPECIES=%d' % m.chemical_db.get_species_count())
            print('IMPORT_OK')
        """).format(root=REPO_ROOT, data_dir=str(data_dir))

        result = _run_python(code)
        assert result.returncode == 0, (
            'salt-okunur senaryoda import coktu (Senaryo B regresyonu):\n%s\n%s'
            % (result.stdout, result.stderr))
        assert 'IMPORT_OK' in result.stdout
        assert ('SPECIES=%d' % EXPECTED_SPECIES_COUNT) in result.stdout
        assert not data_dir.exists(), (
            'import salt-okunur dizinde data/ olusturmaya calisti')
    finally:
        ro_parent.chmod(0o700)


def test_class_instantiation_does_no_disk_io(tmp_path):
    """ChemicalDatabase() kurulumu hicbir disk I/O yapmamali — db_path
    yazilamaz bir yeri gosterse bile."""
    ro_dir = tmp_path / 'ro2'
    ro_dir.mkdir()
    ro_dir.chmod(0o500)

    try:
        from hrma.data.chemical_database import ChemicalDatabase
        db = ChemicalDatabase(db_path=str(ro_dir / 'sub' / 'x.db'))
        assert db.get_species_count() == EXPECTED_SPECIES_COUNT
        assert not (ro_dir / 'sub').exists(), (
            'kurulum db_path dizinini olusturdu (import-yolu yazmasi geri geldi)')
    finally:
        ro_dir.chmod(0o700)


def test_species_data_consumer_api_intact():
    """Tuketici API'si (bellekteki species_data) degismedi."""
    from hrma.data.chemical_database import chemical_db

    assert chemical_db.get_species_count() == EXPECTED_SPECIES_COUNT

    h2o = chemical_db.get_species('H2O')
    assert h2o is not None
    assert h2o.molecular_weight == pytest.approx(18.015)
    assert h2o.enthalpy_formation == pytest.approx(-241826.0)
    assert h2o.phase == 'gas'

    # NASA polinomundan Cp — fiziksel olarak makul araliklar
    cp_h2o = chemical_db.calculate_cp('H2O', 500.0)
    assert 30.0 < cp_h2o < 40.0
    cp_n2 = chemical_db.calculate_cp('N2', 1000.0)
    assert 25.0 < cp_n2 < 36.0

    # Referans sicaklikta entalpi = olusum entalpisi
    h_co2 = chemical_db.calculate_enthalpy('CO2', 298.15)
    assert h_co2 == pytest.approx(-393522.0, rel=1e-6)

    names = chemical_db.get_all_species_names()
    for name in ('H2', 'O2', 'N2O', 'HTPB', 'Paraffin', 'AP'):
        assert name in names, 'beklenen tur eksik: %s' % name

    results = chemical_db.search_species(formula='H2O')
    assert any(s.name == 'H2O' for s in results)

    validation = chemical_db.validate_database()
    assert validation['total_species'] == EXPECTED_SPECIES_COUNT


def test_export_sqlite_is_explicit_and_complete(tmp_path):
    """Kalicilik yalniz acik cagriyla: export_sqlite() verilen hedefe tek
    seferde yazar, varsayilan db_path'e dokunmaz."""
    from hrma.data.chemical_database import ChemicalDatabase

    default_path = tmp_path / 'default.db'
    db = ChemicalDatabase(db_path=str(default_path))
    assert not default_path.exists(), 'kurulum varsayilan db_path dosyasini yazdi'

    target = tmp_path / 'out' / 'species.db'
    written = db.export_sqlite(str(target))
    assert written == str(target)
    assert target.exists()

    conn = sqlite3.connect(str(target))
    try:
        row_count = conn.execute(
            'SELECT COUNT(*) FROM chemical_species').fetchone()[0]
        mw = conn.execute(
            "SELECT molecular_weight FROM chemical_species WHERE name='H2O'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert row_count == EXPECTED_SPECIES_COUNT
    assert mw == pytest.approx(18.015)
    # export acik cagri disinda varsayilan yola yazmamali
    assert not default_path.exists()


def test_user_data_dir_constant():
    """hrma.USER_DATA_DIR: yazilabilir kullanici-veri dizini sabiti tanimli
    ve HRMA_USER_DATA_DIR ortam degiskeni sozlesmesine uyuyor."""
    import hrma

    assert isinstance(hrma.USER_DATA_DIR, str) and hrma.USER_DATA_DIR
    assert os.path.isabs(hrma.USER_DATA_DIR)
    # Kaynak veri dizini ile kullanici-veri dizini ayri kavramlar
    assert os.path.abspath(hrma.USER_DATA_DIR) != os.path.abspath(hrma.DATA_DIR)

    # Sabit import aninda cozuldugu icin override taze alt surecte dogrulanir
    override = str(os.path.join(os.sep, 'tmp', 'hrma-test-override'))
    code = textwrap.dedent("""
        import sys
        sys.path.insert(0, {root!r})
        import hrma
        print('USER_DATA_DIR=' + hrma.USER_DATA_DIR)
    """).format(root=REPO_ROOT)
    result = _run_python(code, extra_env={'HRMA_USER_DATA_DIR': override})
    assert result.returncode == 0, result.stderr
    assert ('USER_DATA_DIR=' + override) in result.stdout
