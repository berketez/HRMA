"""v3.0.1 (26 Eki 2026) — eski projeler 3.0.1'de bozuk açılmaz.

ÖLÇÜLDÜ (ana model, gerçek tarayıcı, main 84af545cd): "Aç" ile açılan katı
örnek proje hesaplanınca 422 aldı — "kasa iç çapı (chamber_diameter) 75 mm;
75 mm yakıt bloğunun 2 mm astar ve 3 mm yalıtımla birlikte gerektirdiği en
az 85,0 mm değerinin altında". Kök iki katlı:

1. Tohumlama örnekleri kullanıcı dizinine BİR KEZ kopyalar ve hiç
   güncellemez; geliştirme makinesindeki kopyalar 796a56aab (2.6.27)
   sürümündeydi.
2. Eski katı örnek ``chamber_diameter`` = ``outer_diameter`` = 75 mm
   taşıyordu: 3.0.1 öncesinde alan tane çapı anlamındaydı; 3.0.1'de (K-A
   karar A) ``outer_diameter`` varken alan KASA İÇ ÇAPIDIR.

Düzeltme iki katlıdır, bu bekçiler ikisini de tutar:
``refresh_seeded_examples`` kullanıcının DEĞİŞTİRMEDİĞİ eski örnek
kopyalarını günceller; ``_solid_legacy_case_bore_migration`` eski katı
projede tane çapı anlamındaki kasa çapını beyanlı olarak boşaltır.
"""
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from hrma.utils import projects as store

KOK = Path(__file__).resolve().parents[1]
ORNEKLER = KOK / 'examples'


def _katı_belge(surum, kasa, tane, **ek):
    alanlar = {'outer_diameter': tane, 'core_diameter': 32.0,
               'grain_length': 120.0}
    if kasa is not None:
        alanlar['chamber_diameter'] = kasa
    alanlar.update(ek)
    return {'format': 'hrma-project', 'format_version': 1, 'name': 'Eski',
            'motor_type': 'solid', 'inputs': {'fields': alanlar},
            'app_version': surum, 'created_at': '2026-09-16T13:25:00',
            'updated_at': '2026-09-16T13:25:00'}


@pytest.fixture
def proje_dizini(tmp_path, monkeypatch):
    d = tmp_path / 'projects'
    d.mkdir()
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(d))
    return d


def _yaz(dizin, ad, belge):
    (dizin / (ad + '.hrma')).write_text(json.dumps(belge), encoding='utf-8')


# --------------------------------------------------------------------------
# Katı eski kasa çapı göçü
# --------------------------------------------------------------------------
class TestKatiEskiKasaGocu:

    def test_tane_capina_esit_kasa_bosaltilir_ve_soylenir(self, proje_dizini):
        _yaz(proje_dizini, 'Eski', _katı_belge('2.6.27', 75.0, 75.0))
        belge, kayitlar = store.load_project_records('Eski')
        assert belge['inputs']['fields']['chamber_diameter'] == ''
        goc = [k for k in kayitlar
               if k['code'] == store.LOAD_WARNING_SOLID_LEGACY_CASE_BORE]
        assert len(goc) == 1
        assert goc[0]['params'] == {'saved_version': '2.6.27',
                                    'chamber_diameter_mm': 75,
                                    'outer_diameter_mm': 75}
        # diskteki dosya DEĞİŞMEZ (göç yalnız bellekte)
        disk = json.loads((proje_dizini / 'Eski.hrma').read_text())
        assert disk['inputs']['fields']['chamber_diameter'] == 75.0

    def test_metin_listesi_ile_kayitlar_ayni_sirada(self, proje_dizini):
        _yaz(proje_dizini, 'Eski', _katı_belge('3.0.0', 70.0, 75.0))
        _belge, metinler = store.load_project('Eski')
        _b2, kayitlar = store.load_project_records('Eski')
        assert metinler == [store.load_warning_text(k) for k in kayitlar]
        assert any('Versions before 3.0.1' in m for m in metinler)

    @pytest.mark.parametrize('surum,kasa,tane,motor', [
        ('3.0.0', 90.0, 75.0, 'solid'),   # kasa taneden büyük: gerçek kasa
        ('3.0.1', 75.0, 75.0, 'solid'),   # yeni sürümün kaydı
        ('3.1.0', 75.0, 75.0, 'solid'),
        ('bilinmiyor', 75.0, 75.0, 'solid'),
        ('3.0.0', None, 75.0, 'solid'),   # kasa alanı yok
        ('3.0.0', 75.0, 75.0, 'hybrid'),  # katı değil
    ])
    def test_imza_disinda_dokunulmaz(self, proje_dizini, surum, kasa, tane,
                                     motor):
        belge = _katı_belge(surum, kasa, tane)
        belge['motor_type'] = motor
        _yaz(proje_dizini, 'Eski', belge)
        yuklenen, kayitlar = store.load_project_records('Eski')
        assert yuklenen['inputs']['fields'] == belge['inputs']['fields']
        assert not [k for k in kayitlar
                    if k['code'] == store.LOAD_WARNING_SOLID_LEGACY_CASE_BORE]

    def test_api_kayitlari_metinlerle_birebir(self, proje_dizini):
        _yaz(proje_dizini, 'Eski', _katı_belge('2.6.27', 75.0, 75.0))
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            r = c.get('/api/projects/load/Eski')
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        j = r.get_json()
        assert len(j['warnings']) == len(j['warning_records'])
        kodlar = [k['code'] for k in j['warning_records']]
        assert store.LOAD_WARNING_SOLID_LEGACY_CASE_BORE in kodlar
        assert j['project']['inputs']['fields']['chamber_diameter'] == ''

    def test_uyari_iki_dilde_sozlukte(self):
        js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
            encoding='utf-8')
        assert js.count("'warn.project.solid_legacy_case_bore':") == 2
        tr = re.findall(r"'warn\.project\.solid_legacy_case_bore': '([^']*)'",
                        js)[1]
        for yer in ('{saved_version}', '{chamber_diameter_mm}',
                    '{outer_diameter_mm}'):
            assert yer in tr
        assert 'kasa iç çapı' in tr


# --------------------------------------------------------------------------
# Eski örnek kopyalarının tazelenmesi
# --------------------------------------------------------------------------
@pytest.fixture
def ornek_kaynagi(tmp_path, monkeypatch):
    kaynak = tmp_path / 'examples'
    kaynak.mkdir()
    (kaynak / 'Ornek A.hrma').write_bytes(b'{"yeni": 1}')
    (kaynak / 'Ornek B.hrma').write_bytes(b'{"yeni": 2}')
    eski_a = hashlib.sha256(b'{"eski": 1}').hexdigest()
    eski_b = hashlib.sha256(b'{"eski": 2}').hexdigest()
    (kaynak / store.SHIPPED_EXAMPLE_HASHES_FILENAME).write_text(json.dumps(
        {'hashes': {'Ornek A.hrma': [eski_a], 'Ornek B.hrma': [eski_b]}}))
    monkeypatch.setenv('HRMA_EXAMPLES_DIR', str(kaynak))
    return kaynak


def _tohumlanmis(dizin):
    (dizin / store.SEED_STAMP_FILENAME).write_text('{}')


class TestOrnekTazeleme:

    def test_degistirilmemis_eski_kopya_tazelenir(self, proje_dizini,
                                                   ornek_kaynagi):
        _tohumlanmis(proje_dizini)
        (proje_dizini / 'Ornek A.hrma').write_bytes(b'{"eski": 1}')
        sonuc = store.refresh_seeded_examples()
        assert sonuc['status'] == 'refreshed'
        assert sonuc['refreshed'] == ['Ornek A.hrma']
        assert (proje_dizini / 'Ornek A.hrma').read_bytes() == b'{"yeni": 1}'
        # ikinci açılış: aynı sürümde bir daha çalışmaz
        assert store.refresh_seeded_examples()['status'] == 'already_refreshed'

    def test_kullanicinin_degistirdigi_kopyaya_dokunulmaz(self, proje_dizini,
                                                          ornek_kaynagi):
        _tohumlanmis(proje_dizini)
        (proje_dizini / 'Ornek A.hrma').write_bytes(b'{"benim": 1}')
        sonuc = store.refresh_seeded_examples()
        assert sonuc['kept_modified'] == ['Ornek A.hrma']
        assert (proje_dizini / 'Ornek A.hrma').read_bytes() == b'{"benim": 1}'

    def test_silinen_ornek_geri_gelmez(self, proje_dizini, ornek_kaynagi):
        _tohumlanmis(proje_dizini)
        sonuc = store.refresh_seeded_examples()
        assert set(sonuc['skipped_missing']) == {'Ornek A.hrma', 'Ornek B.hrma'}
        assert not (proje_dizini / 'Ornek A.hrma').exists()

    def test_tohumlanmamis_dizinde_calismaz(self, proje_dizini, ornek_kaynagi):
        (proje_dizini / 'Ornek A.hrma').write_bytes(b'{"eski": 1}')
        assert store.refresh_seeded_examples()['status'] == 'not_seeded'
        assert (proje_dizini / 'Ornek A.hrma').read_bytes() == b'{"eski": 1}'

    def test_karma_dosyasi_yoksa_hicbir_sey_ezilmez(self, proje_dizini,
                                                     ornek_kaynagi):
        (ornek_kaynagi / store.SHIPPED_EXAMPLE_HASHES_FILENAME).unlink()
        _tohumlanmis(proje_dizini)
        (proje_dizini / 'Ornek A.hrma').write_bytes(b'{"eski": 1}')
        sonuc = store.refresh_seeded_examples()
        assert sonuc['kept_modified'] == ['Ornek A.hrma']
        assert (proje_dizini / 'Ornek A.hrma').read_bytes() == b'{"eski": 1}'

    def test_onceki_tazelemenin_yazdigi_surum_de_taninir(self, proje_dizini,
                                                         ornek_kaynagi):
        """Bir sonraki sürüm, bu sürümün yazdığı (karma listesinde olmayan)
        kopyayı da 'değiştirilmemiş' tanır: damga yazılan karmayı taşır."""
        _tohumlanmis(proje_dizini)
        (proje_dizini / 'Ornek A.hrma').write_bytes(b'{"ara": 1}')
        (proje_dizini / store.EXAMPLE_REFRESH_STAMP_FILENAME).write_text(
            json.dumps({'app_version': '0.0.1', 'written': {
                'Ornek A.hrma': hashlib.sha256(b'{"ara": 1}').hexdigest()}}))
        sonuc = store.refresh_seeded_examples()
        assert sonuc['refreshed'] == ['Ornek A.hrma']


class TestGercekOrnekKarmaListesi:
    """Depodaki örneklerin GÜNCEL karmaları listede olmalı: yoksa bir sonraki
    sürüm bu sürümün örneklerini 'kullanıcı değiştirmiş' sanıp tazelemez.
    examples/generate_examples.py her üretimde listeyi günceller."""

    def test_guncel_ornekler_dagitilmis_listede(self):
        belge = json.loads((ORNEKLER / store.SHIPPED_EXAMPLE_HASHES_FILENAME)
                           .read_text(encoding='utf-8'))
        for yol in sorted(ORNEKLER.glob('*.hrma')):
            h = hashlib.sha256(yol.read_bytes()).hexdigest()
            assert h in belge['hashes'].get(yol.name, []), (
                f'{yol.name}: güncel karma listede yok — '
                'python3 examples/generate_examples.py ile üretin')

    def test_uretici_listeyi_gunceller(self):
        s = (ORNEKLER / 'generate_examples.py').read_text(encoding='utf-8')
        assert '_dagitilmis_karmaya_ekle(name + store.FILE_EXT)' in s
