"""CI dilimleme (tools/ci_dilim.py) — bölümleme ve birleştirme bekçileri.

v3.0.0 (15 Eki 2026): ``tests.yml`` ``pytest`` işi matrise bölündü. Bu
dosya üç şeyi ölçer: (1) bölümleme deterministik ve kümeyi TAM örtüyor,
(2) birleştirici eksik/çift dilimi ve kümeyi örtmeyen seçimi REDDEDİYOR,
(3) her dilimde tekrar eden toplama düzeyi kayıtları bir kez sayılıyor.
"""

import json
import pathlib
import xml.etree.ElementTree as ET

import pytest
import yaml

from tools import ci_dilim

DEPO = pathlib.Path(__file__).resolve().parents[1]


def _sayilar():
    return {'tests/a.py': 10, 'tests/b.py': 3, 'tests/c.py': 7,
            'tests/d.py': 1, 'tests/e.py': 5}


class TestBolumleme:
    def test_dilim_coz(self):
        assert ci_dilim.dilim_coz('3/10') == (3, 10)
        for bozuk in ('0/3', '4/3', '3', 'a/b', '1/0'):
            with pytest.raises(ValueError):
                ci_dilim.dilim_coz(bozuk)

    def test_her_dosya_tek_dilimde_ve_kume_ortulu(self):
        atama = ci_dilim.dilimle(_sayilar(), 3, {'tests/a.py': 9.0}, 0.5)
        assert set(atama) == set(_sayilar())
        assert set(atama.values()) <= {1, 2, 3}

    def test_deterministik(self):
        a = ci_dilim.dilimle(_sayilar(), 3, {'tests/c.py': 4.0}, 0.5)
        b = ci_dilim.dilimle(dict(reversed(list(_sayilar().items()))), 3,
                             {'tests/c.py': 4.0}, 0.5)
        assert a == b

    def test_agirlik_dosyasi_okunuyor(self):
        agirliklar, ortalama = ci_dilim.agirliklari_oku()
        assert agirliklar, 'ci_dilim_agirliklari.json okunamadı — dengeleme körleşir'
        assert ortalama > 0


def _junit(yol, kayitlar):
    kok = ET.Element('testsuites')
    s = ET.SubElement(kok, 'testsuite', name='pytest', tests=str(len(kayitlar)),
                      time='1.0')
    for cn, ad, atla in kayitlar:
        tc = ET.SubElement(s, 'testcase', classname=cn, name=ad)
        if atla:
            ET.SubElement(tc, 'skipped', message=atla)
    ET.ElementTree(kok).write(yol, encoding='utf-8')


def _dilim(kok, k, n, toplanan, kayitlar, secilen=None):
    d = kok / ('pytest-report-dilim-%d' % k)
    d.mkdir()
    _junit(d / 'pytest-report.xml', kayitlar)
    (d / ci_dilim.KUNYE_ADI).write_text(json.dumps(
        {'dilim': k, 'dilim_sayisi': n, 'toplanan': toplanan,
         'secilen': len(kayitlar) if secilen is None else secilen}),
        encoding='utf-8')


class TestBirlestirme:
    def test_tam_kume_birlesir_ve_toplama_tekrari_atilir(self, tmp_path):
        modul = ('', 'tests.test_m', 'collection skipped')
        _dilim(tmp_path, 1, 2, 3, [('tests.test_a', 'x', None), modul], secilen=1)
        _dilim(tmp_path, 2, 2, 3, [('tests.test_b', 'y', None),
                                   ('tests.test_b', 'z', None), modul], secilen=2)
        cikti = tmp_path / 'birlesik.xml'
        assert ci_dilim.birlestir(tmp_path, cikti) == []
        s = ET.parse(cikti).getroot().find('testsuite')
        assert s.get('tests') == '4'      # 3 test + 1 modül kaydı (tekrar atıldı)
        assert s.get('skipped') == '1'

    def test_eksik_dilim_reddedilir(self, tmp_path):
        _dilim(tmp_path, 1, 3, 2, [('tests.test_a', 'x', None)])
        _dilim(tmp_path, 3, 3, 2, [('tests.test_c', 'y', None)])
        hata = ci_dilim.birlestir(tmp_path, tmp_path / 'b.xml')
        assert any('beklenen 1..3' in h for h in hata), hata

    def test_kumeyi_ortmeyen_secim_reddedilir(self, tmp_path):
        _dilim(tmp_path, 1, 2, 5, [('tests.test_a', 'x', None)])
        _dilim(tmp_path, 2, 2, 5, [('tests.test_b', 'y', None)])
        hata = ci_dilim.birlestir(tmp_path, tmp_path / 'b.xml')
        assert any('örtmüyor' in h for h in hata), hata

    def test_kunye_yoksa_reddedilir(self, tmp_path):
        assert ci_dilim.birlestir(tmp_path, tmp_path / 'b.xml')


class TestIsAkisi:
    """Dilim sayısının tek kaynağı matris listesidir; birleştirme işi bağlı."""

    def test_matris_ve_birlesim_isi(self):
        veri = yaml.safe_load((DEPO / '.github/workflows/tests.yml')
                              .read_text(encoding='utf-8'))
        isler = veri['jobs']
        dilimler = isler['pytest']['strategy']['matrix']['dilim']
        assert dilimler == list(range(1, len(dilimler) + 1))
        assert isler['pytest']['strategy'].get('fail-fast') is False
        birlesik = isler['pytest-birlesik']
        assert birlesik.get('needs') == 'pytest' and birlesik.get('if') == 'always()'
        komutlar = '\n'.join(a.get('run', '') or '' for a in birlesik['steps'])
        assert 'tools/ci_dilim.py birlestir' in komutlar
        assert 'tools/atlama_kapisi.py pytest-report.xml' in komutlar
        assert 'needs.pytest.result' in komutlar
