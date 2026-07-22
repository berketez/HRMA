"""
hrma/utils/projects.py depo katmanı testleri.

Kapsam:
  - geçerli kaydet/yükle gidiş-dönüşü (inputs byte-eşit)
  - ad enjeksiyonu reddi (../, mutlak yol, unicode hile, ayrılmış adlar)
  - overwrite koruması + created_at korunumu
  - bozuk JSON dosyası listeyi kırmıyor (corrupt işareti)
  - .trash davranışı (kalıcı silme yok)
  - 1 MB boyut sınırı
  - HRMA_PROJECTS_DIR env override + varsayılan dizin mantığı
  - şema doğrulama redleri (uydurma-veri-yasağı: sessiz doldurma yok)
  - sembolik bağ kaçışı reddi (realpath kapsama)

Tüm fixture verileri sentetiktir; ağ erişimi yoktur.
"""

import json
import os
import sys

import pytest

from hrma.utils import projects as store


@pytest.fixture()
def proj_dir(tmp_path, monkeypatch):
    """Her test izole bir proje dizini kullanır (env override)."""
    d = tmp_path / 'projects'
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(d))
    return d


def make_payload(**overrides):
    """Geçerli, sentetik bir proje yükü üret."""
    payload = {
        'format': 'hrma-project',
        'format_version': 1,
        'motor_type': 'hybrid',
        'description': 'Sentetik test projesi',
        'inputs': {
            'fields': {
                'thrust': 1000.0,
                'burn_time': 10,
                'fuel_type': 'htpb',
                'auto_expansion': True,
            },
            'ui_state': {'active_tab': 'motor'},
        },
        'results_summary': {'isp': 245.3, 'thrust': 1000.0},
    }
    payload.update(overrides)
    return payload


# --- Dizin çözümü -----------------------------------------------------------

class TestProjectsDir:
    def test_env_override(self, tmp_path, monkeypatch):
        d = tmp_path / 'ozel' / 'projeler'
        monkeypatch.setenv('HRMA_PROJECTS_DIR', str(d))
        assert store.projects_dir() == str(d)
        assert d.is_dir()  # makedirs çağrıldı

    def test_default_with_documents(self, tmp_path, monkeypatch):
        home = tmp_path / 'ev'
        (home / 'Documents').mkdir(parents=True)
        monkeypatch.delenv('HRMA_PROJECTS_DIR', raising=False)
        monkeypatch.setenv('HOME', str(home))
        monkeypatch.setenv('USERPROFILE', str(home))  # Windows expanduser
        result = store.projects_dir()
        assert result == str(home / 'Documents' / 'HRMA' / 'projects')
        assert os.path.isdir(result)

    def test_default_without_documents(self, tmp_path, monkeypatch):
        home = tmp_path / 'ev2'
        home.mkdir()
        monkeypatch.delenv('HRMA_PROJECTS_DIR', raising=False)
        monkeypatch.setenv('HOME', str(home))
        monkeypatch.setenv('USERPROFILE', str(home))
        result = store.projects_dir()
        assert result == str(home / 'HRMA' / 'projects')
        assert os.path.isdir(result)


# --- Ad doğrulama -----------------------------------------------------------

class TestNameValidation:
    @pytest.mark.parametrize('name', [
        'Motor 1', 'test_projesi', 'a', 'A' * 80, 'v2.5-final', 'x-y_z.1',
    ])
    def test_valid_names(self, name):
        assert store.validate_name(name) == name

    @pytest.mark.parametrize('name', [
        '../evil',            # dizin kaçışı
        '..',                 # nokta ile başlıyor
        '.gizli',             # nokta ile başlıyor
        '/etc/passwd',        # mutlak yol
        'a/b',                # ayraç
        'a\\b',               # Windows ayracı
        'projeı',        # unicode hile (Türkçe ı — beyaz liste dışı)
        'proj​e',        # sıfır genişlikli boşluk
        'café',               # aksanlı harf
        '',                   # boş
        'A' * 81,             # çok uzun
        'ad.',                # nokta ile bitiyor (Windows)
        'ad ',                # boşluk ile bitiyor (Windows)
        'CON',                # Windows ayrılmış ad
        'nul.eski',           # Windows ayrılmış kök
        'COM1',
        None,                 # str değil
        42,                   # str değil
    ])
    def test_invalid_names(self, name):
        with pytest.raises(store.ProjectNameError):
            store.validate_name(name)

    @pytest.mark.parametrize('name', ['../evil', '/abs/yol', 'a/../../b'])
    def test_injection_rejected_everywhere(self, proj_dir, name):
        with pytest.raises(store.ProjectNameError):
            store.save_project(name, make_payload())
        with pytest.raises(store.ProjectNameError):
            store.load_project(name)
        with pytest.raises(store.ProjectNameError):
            store.delete_project(name)

    @pytest.mark.skipif(sys.platform.startswith('win'), reason='POSIX sembolik bağ')
    def test_symlink_escape_rejected(self, proj_dir, tmp_path):
        """Dizine bırakılmış sembolik bağ realpath denetimine takılmalı."""
        store.projects_dir()  # dizini oluştur
        secret = tmp_path / 'sir.txt'
        secret.write_text('gizli', encoding='utf-8')
        os.symlink(str(secret), str(proj_dir / 'kacak.hrma'))
        with pytest.raises(store.ProjectNameError):
            store.load_project('kacak')


# --- Kaydet / yükle ---------------------------------------------------------

class TestSaveLoad:
    def test_roundtrip_inputs_byte_equal(self, proj_dir):
        payload = make_payload()
        info = store.save_project('gidis donus', payload)
        assert info['name'] == 'gidis donus'
        assert info['app_version']

        doc, warnings = store.load_project('gidis donus')
        # inputs byte-eşit olmalı (sessiz dönüştürme/doldurma yok)
        original = json.dumps(payload['inputs'], sort_keys=True, ensure_ascii=False)
        loaded = json.dumps(doc['inputs'], sort_keys=True, ensure_ascii=False)
        assert original.encode('utf-8') == loaded.encode('utf-8')
        assert doc['motor_type'] == 'hybrid'
        assert doc['results_summary'] == payload['results_summary']
        assert warnings == []  # aynı sürümde uyarı yok

    def test_server_stamps(self, proj_dir):
        # İstemcinin gönderdiği damgalar sunucu tarafından ezilir
        payload = make_payload(app_version='0.0.1', created_at='1999-01-01T00:00:00',
                               updated_at='1999-01-01T00:00:00')
        store.save_project('damga', payload)
        doc, _ = store.load_project('damga')
        assert doc['app_version'] != '0.0.1'
        assert not doc['created_at'].startswith('1999')
        assert not doc['updated_at'].startswith('1999')
        assert doc['name'] == 'damga'

    def test_version_mismatch_warning(self, proj_dir):
        store.save_project('eski surum', make_payload())
        path = os.path.join(store.projects_dir(), 'eski surum.hrma')
        doc = json.load(open(path, encoding='utf-8'))
        doc['app_version'] = '0.9.9'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(doc, f)
        _, warnings = store.load_project('eski surum')
        assert any('0.9.9' in w for w in warnings)

    def test_load_missing(self, proj_dir):
        with pytest.raises(store.ProjectNotFoundError):
            store.load_project('yok boyle proje')

    def test_load_corrupt_json(self, proj_dir):
        store.projects_dir()
        with open(proj_dir / 'bozuk.hrma', 'w', encoding='utf-8') as f:
            f.write('{bu json degil')
        with pytest.raises(store.ProjectCorruptError):
            store.load_project('bozuk')

    def test_load_schema_violating_file(self, proj_dir):
        """Elle düzenlenmiş, şemaya uymayan dosya yüklemede reddedilir."""
        store.projects_dir()
        with open(proj_dir / 'sahte.hrma', 'w', encoding='utf-8') as f:
            json.dump({'format': 'baska-format', 'inputs': {}}, f)
        with pytest.raises(store.ProjectCorruptError):
            store.load_project('sahte')


# --- Overwrite koruması -----------------------------------------------------

class TestOverwrite:
    def test_second_save_requires_overwrite(self, proj_dir):
        store.save_project('ayni ad', make_payload())
        with pytest.raises(store.ProjectExistsError):
            store.save_project('ayni ad', make_payload())

    def test_overwrite_true_replaces_and_keeps_created_at(self, proj_dir):
        store.save_project('ayni ad', make_payload())
        doc1, _ = store.load_project('ayni ad')
        payload2 = make_payload(motor_type='solid')
        info = store.save_project('ayni ad', payload2, overwrite=True)
        doc2, _ = store.load_project('ayni ad')
        assert doc2['motor_type'] == 'solid'
        assert doc2['created_at'] == doc1['created_at']  # orijinal damga korunur
        assert info['created_at'] == doc1['created_at']


# --- Şema doğrulama ---------------------------------------------------------

class TestSchemaValidation:
    @pytest.mark.parametrize('mutate', [
        lambda p: p.pop('format'),
        lambda p: p.update(format='baska'),
        lambda p: p.pop('format_version'),
        lambda p: p.update(format_version=2),
        lambda p: p.update(format_version='1'),  # tip sıkı: int olmalı
        lambda p: p.update(format_version=True),
        lambda p: p.pop('motor_type'),
        lambda p: p.update(motor_type='nuclear'),
        lambda p: p.pop('inputs'),
        lambda p: p.update(inputs=[]),
        lambda p: p['inputs'].pop('fields'),
        lambda p: p['inputs'].update(fields='duz degil'),
        lambda p: p.update(bilinmeyen_alan=1),          # bilinmeyen üst anahtar
        lambda p: p['inputs'].update(gizli_alan={}),    # bilinmeyen inputs anahtarı
        lambda p: p.update(description=123),
        lambda p: p.update(results_summary=[1, 2]),
        lambda p: p['results_summary'].update(nested={'a': 1}),
    ])
    def test_invalid_payloads_rejected(self, proj_dir, mutate):
        payload = make_payload()
        mutate(payload)
        with pytest.raises(store.ProjectValidationError):
            store.save_project('gecersiz', payload)
        # Reddedilen kayıt diske yazılmamış olmalı
        assert not os.path.exists(os.path.join(store.projects_dir(), 'gecersiz.hrma'))

    @pytest.mark.parametrize('bad_value', [
        {'ic ice': 1},        # iç içe nesne
        [1, 2, 3],            # liste
        None,                 # boş değer sessizce saklanmaz
        float('nan'),         # sonlu olmayan sayı
        float('inf'),
    ])
    def test_fields_values_must_be_flat_scalars(self, proj_dir, bad_value):
        payload = make_payload()
        payload['inputs']['fields']['kotu'] = bad_value
        with pytest.raises(store.ProjectValidationError):
            store.save_project('duz alanlar', payload)

    def test_payload_must_be_dict(self, proj_dir):
        with pytest.raises(store.ProjectValidationError):
            store.save_project('tip hatasi', ['liste'])

    def test_optional_dynamic_accepted(self, proj_dir):
        payload = make_payload()
        payload['inputs']['dynamic'] = {'rows': [{'id': 1, 'value': 2.5}]}
        payload['inputs']['dock_overrides'] = {'panel': 'safety'}
        store.save_project('dinamik', payload)
        doc, _ = store.load_project('dinamik')
        assert doc['inputs']['dynamic'] == payload['inputs']['dynamic']


# --- Boyut sınırı -----------------------------------------------------------

class TestSizeLimit:
    def test_over_one_megabyte_rejected(self, proj_dir):
        payload = make_payload()
        payload['inputs']['ui_state'] = {'big': 'x' * (store.MAX_PROJECT_BYTES + 100)}
        with pytest.raises(store.ProjectTooLargeError):
            store.save_project('devasa', payload)
        assert not os.path.exists(os.path.join(store.projects_dir(), 'devasa.hrma'))

    def test_under_limit_accepted(self, proj_dir):
        payload = make_payload()
        payload['inputs']['ui_state'] = {'big': 'x' * 1000}
        store.save_project('normal boyut', payload)


# --- Listeleme --------------------------------------------------------------

class TestListProjects:
    def test_empty(self, proj_dir):
        assert store.list_projects() == []

    def test_list_fields(self, proj_dir):
        store.save_project('liste projesi', make_payload())
        items = store.list_projects()
        assert len(items) == 1
        item = items[0]
        assert item['name'] == 'liste projesi'
        assert item['motor_type'] == 'hybrid'
        assert item['corrupt'] is False
        assert item['updated_at']
        assert item['results_summary'] == {'isp': 245.3, 'thrust': 1000.0}
        # Liste tam belgeyi taşımaz (yalnız gerekli alanlar)
        assert 'inputs' not in item

    def test_corrupt_file_does_not_break_list(self, proj_dir):
        store.save_project('saglam', make_payload())
        with open(proj_dir / 'kirik.hrma', 'wb') as f:
            f.write(b'\x00\xffJSON degil{{{')
        items = store.list_projects()
        by_name = {i['name']: i for i in items}
        assert by_name['saglam']['corrupt'] is False
        assert by_name['kirik']['corrupt'] is True
        assert by_name['kirik'].get('reason')

    def test_non_hrma_and_hidden_files_skipped(self, proj_dir):
        store.projects_dir()
        (proj_dir / 'not.txt').write_text('x', encoding='utf-8')
        (proj_dir / '.gizli.hrma').write_text('{}', encoding='utf-8')
        assert store.list_projects() == []

    def test_sorted_newest_first(self, proj_dir):
        store.save_project('birinci', make_payload())
        store.save_project('ikinci', make_payload())
        # updated_at aynı saniyeye düşebilir; damgaları ayrıştır
        p1 = proj_dir / 'birinci.hrma'
        doc = json.load(open(p1, encoding='utf-8'))
        doc['updated_at'] = '2000-01-01T00:00:00'
        json.dump(doc, open(p1, 'w', encoding='utf-8'))
        items = store.list_projects()
        assert [i['name'] for i in items] == ['ikinci', 'birinci']


# --- Silme / .trash ---------------------------------------------------------

class TestDelete:
    def test_delete_moves_to_trash(self, proj_dir):
        store.save_project('silinecek', make_payload())
        info = store.delete_project('silinecek')
        assert not os.path.exists(proj_dir / 'silinecek.hrma')
        trash_path = proj_dir / info['trashed_to']
        assert trash_path.exists()
        # İçerik kaybolmadı (kalıcı silme değil)
        doc = json.load(open(trash_path, encoding='utf-8'))
        assert doc['name'] == 'silinecek'
        # Çöpe taşınan proje listede görünmez
        assert store.list_projects() == []

    def test_delete_missing(self, proj_dir):
        with pytest.raises(store.ProjectNotFoundError):
            store.delete_project('hic olmadi')

    def test_delete_same_name_twice_no_collision(self, proj_dir):
        store.save_project('tekrar', make_payload())
        info1 = store.delete_project('tekrar')
        store.save_project('tekrar', make_payload())
        info2 = store.delete_project('tekrar')
        assert info1['trashed_to'] != info2['trashed_to'] or \
            (proj_dir / info1['trashed_to']).exists()
        trash_files = list((proj_dir / '.trash').glob('*.hrma'))
        assert len(trash_files) == 2
