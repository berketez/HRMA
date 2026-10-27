"""v3.0.1 (26 Eki 2026) — Türkçe harfli proje adı kaydedilir ve açılır.

Son kullanıcı testi (NK-51): Hibrit → "Farklı Kaydet" → "NK deneme şüğ hibrit"
"Geçersiz proje adı - adlandırma kuralına bakın" ile reddedildi; kural metni
"İzin verilen: harf, rakam, boşluk, _ . -" diyordu. İleti hangi karakterin
sorun olduğunu da söylemiyordu. Düzeltme: sunucu ve istemci beyaz listesine
yalnız önceden birleşik (NFC) Türkçe harfler eklendi; reddedilen karakter
adıyla söylenir. Öteki alfabeler, NFD yazım ve görünmez karakterler hâlâ
reddedilir.
"""
import json
import re
from pathlib import Path
from urllib.parse import quote

import pytest

from hrma.utils import projects as store

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture
def proje_dizini(tmp_path, monkeypatch):
    d = tmp_path / 'projects'
    d.mkdir()
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(d))
    return d


def _belge():
    return {'format': 'hrma-project', 'format_version': 1,
            'motor_type': 'hybrid', 'inputs': {'fields': {'thrust': 1500}}}


def test_turkce_adli_proje_kaydedilir_listelenir_acilir(proje_dizini):
    ad = 'NK deneme şüğ hibrit İÇÖ'
    store.save_project(ad, _belge())
    assert (proje_dizini / (ad + store.FILE_EXT)).exists()
    adlar = [p['name'] for p in store.list_projects()]
    assert ad in adlar
    girdi = [p for p in store.list_projects() if p['name'] == ad][0]
    assert not girdi['corrupt']
    belge, _uyarilar = store.load_project(ad)
    assert belge['inputs']['fields']['thrust'] == 1500


def test_api_yuzdeli_kodlanmis_turkce_adla_acar(proje_dizini):
    ad = 'Şimşek-1'
    store.save_project(ad, _belge())
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        r = c.get('/api/projects/load/' + quote(ad))
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    assert r.get_json()['project']['inputs']['fields']['thrust'] == 1500


@pytest.mark.parametrize('ad,yasak', [
    ('NK/test?', "'/?'"),
    ('café', "'é'"),
    ('pro​je', "'\\u200b'"),
])
def test_ret_iletisi_yasak_karakteri_soyler(ad, yasak):
    with pytest.raises(store.ProjectNameError) as e:
        store.validate_name(ad)
    assert 'not allowed: ' + yasak in str(e.value)


def test_istemci_sinifi_sunucuyla_ayni_ve_yasaklari_gosterir():
    js = (KOK / 'hrma' / 'static' / 'js' / 'project_bar.js').read_text(
        encoding='utf-8')
    sinif = store._NAME_CHARS
    assert ('var NAME_RE = /^[' + sinif + ']{1,80}$/;') in js
    assert ('var NAME_CHAR_RE = /^[' + sinif + ']$/;') in js
    assert "TF('proj.nameBadChars'" in js


def test_kural_ve_yeni_iletiler_iki_dilde():
    js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    for anahtar in ('proj.nameRule', 'proj.nameBadChars'):
        assert js.count("'" + anahtar + "':") == 2, anahtar
    kurallar = re.findall(r"'proj\.nameRule': '([^']*)'", js)
    assert all('ç ğ ı İ ö ş ü' in k for k in kurallar)
    tr = re.findall(r"'proj\.nameBadChars': '([^']*)'", js)[1]
    assert '{chars}' in tr and 'kullanılamaz' in tr
