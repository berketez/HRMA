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


# ---------------------------------------------------------------------------
# STEP işine devredilen atlama (tools/atlama_kapisi.STEP_DEVIR_DESENI) —
# araç ve tests.yml gövdesi AYNI hükmü vermeli; devir yalnız gövde içi,
# build123d-yokluğu gerekçeli ve dosyası `step-export` komutunda olan
# atlamaya tanınır.
# ---------------------------------------------------------------------------
from tests.test_d37_atlama_butcesi import _arac, _tezgah, _yaml  # noqa: E402

STEP_AKISI = """jobs:
  pytest:
    steps: []
  step-export:
    steps:
      - run: |
          # tests/test_yorum.py yorumda anılıyor, koşulmuyor
          pytest tests/test_s.py
  sonraki:
    steps:
      - run: pytest tests/test_baska.py
"""
B3D_YOK = "could not import 'build123d': No module named 'build123d'"


def _devir_junit(adet, classname='tests.test_s', tip='pytest.skip',
                 mesaj=B3D_YOK):
    kok = ET.Element('testsuites')
    s = ET.SubElement(kok, 'testsuite', name='pytest', tests='9500')
    for i in range(adet):
        tc = ET.SubElement(s, 'testcase', classname=classname, name='t%d' % i)
        nitelik = {'message': mesaj}
        if tip:
            nitelik['type'] = tip
        ET.SubElement(tc, 'skipped', **nitelik)
    return ET.tostring(kok, encoding='unicode')


@pytest.mark.parametrize('ad,classname,tip,mesaj,beklenen', [
    ('listede_devredilir', 'tests.test_s.TestA', 'pytest.skip', B3D_YOK, True),
    ('liste_disi_sayilir', 'tests.test_x', 'pytest.skip', B3D_YOK, False),
    ('yorumdaki_dosya_sayilir', 'tests.test_yorum', 'pytest.skip', B3D_YOK, False),
    ('baska_isteki_dosya_sayilir', 'tests.test_baska', 'pytest.skip', B3D_YOK, False),
    ('ters_kapi_sayilir', 'tests.test_s', 'pytest.skip',
     'build123d kurulu — .step sınanıyor', False),
    ('modul_duzeyi_devredilmez', 'tests.test_s', None, B3D_YOK, False),
])
def test_step_devri_iki_govdede_ayni(tmp_path, ad, classname, tip, mesaj,
                                     beklenen):
    xml = _devir_junit(100, classname, tip, mesaj)
    sonuc = []
    for alt, kos in (('a', _arac), ('y', _yaml)):
        kok = _tezgah(tmp_path / alt)
        (kok / '.github' / 'workflows').mkdir(parents=True)
        (kok / '.github' / 'workflows' / 'tests.yml').write_text(
            STEP_AKISI, encoding='utf-8')
        acik, cikti = kos(kok, xml)
        sonuc.append((acik, cikti))
    (a_acik, a_cikti), (y_acik, y_cikti) = sonuc
    assert a_acik == y_acik, (ad, a_cikti[-500:], y_cikti[-500:])
    assert a_acik is beklenen, (ad, a_cikti[-500:])
    beklenen_devir = 100 if beklenen else 0
    for cikti in (a_cikti, y_cikti):
        assert 'step_devri=%d ' % beklenen_devir in cikti, (ad, cikti[-400:])
