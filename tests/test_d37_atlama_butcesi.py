# -*- coding: utf-8 -*-
"""ÖH D37 · YB-15 — yayın dalı atlama bütçesi: "kanıt yok" ayrı sınıf.

Sorun
-----
Yayın dalı ``docs/scofield``, ``docs/arastirma``, ``docs/tasarim``
çıkarılarak üretilir. O ağaçta ``tests/support/kanit.py`` kapısı eksik
kanıtı ``GEREKCE_ONEKI`` ("kanıt yok: ") önekli gerekçeyle atlar (D36:
~638 test düzeyi + 3 modül). ``ATLAMA_BUTCESI`` 76 ve "toplama düzeyinde
atlama sıfır" kuralı yüzünden yayın dalı CI'ı KIRMIZI olurdu.

Kural (üç gövdede de aynı)
--------------------------
* ``tools/atlama_kapisi.py`` (``release.yml`` bunu çağırır),
* ``tests.yml`` ana ``pytest`` işinin "Atlama bütçesi" adımı,
* ``tests.yml`` ``step-export`` işinin "Atlama bütçesi — SIFIR" adımı:

1. "kanıt yok: " önekli atlama bütçeye SAYILMAZ;
2. modül düzeyinde de olsa "toplama düzeyi sıfır" kuralına takılmaz;
3. AMA yalnız ağaçta ``docs/scofield`` YOKKEN meşrudur — varsa TEK bir
   kanıt atlaması bile HATA;
4. rapor ayrı sayı basar: ``kanit_atlamasi=N (docs'suz agac: evet|hayir)``;
5. önek ve işaret ``tests/support/kanit.py``den AST ile okunur; okunamazsa
   kapı KAPANIR.

Tezgâh gerçek dosyaları KOPYALAR (``tools/atlama_kapisi.py``,
``tests/support/kanit.py``); junit biçimleri 24 Eylül 2026'da pytest 8.3.4
ile gerçek ``kanit.py`` üzerinden ölçüldü ve ``TestGercekPytestCiktisi``
her koşumda yeniden üretir. Ters mutasyon kanıtı:
``docs/scofield/raw/OH/D37/atlama-butcesi/a1/olcum.json``.
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

DEPO = pathlib.Path(__file__).resolve().parents[1]
if str(DEPO) not in sys.path:                        # pragma: no cover
    sys.path.insert(0, str(DEPO))

from tests.support import kanit as K                 # noqa: E402
from tools.atlama_kapisi import (                    # noqa: E402
    ATLAMA_BUTCESI, KANIT_KAYNAGI, TOPLANAN_TABANI, kanit_sozlesmesi, kapi)

#: docs'suz kopyada ölçülen toplama (24 Eylül 2026, ``--collect-only``).
TOPLANAN_DOCSSUZ = 23714
#: step-export kümesinin docs'suz kopyada ölçülen toplaması (aynı gün).
TOPLANAN_STEP_DOCSSUZ = 339

#: Yalnız gerekçe METNİ için örnek yol (dosya sistemine dokunulmaz). Sabit
#: dize DEĞİL: kanıt tarayıcısı (tests/support/kanit_tarayici.py) docs/
#: kanıt dizesini tohum sayar; bu yol hiçbir yerde okunmuyor.
KANIT_YOLU = K.GELISTIRME_ISARETI + '/raw/OH/D00/ornek/kanit.json'


# ---------------------------------------------------------------------------
# Tezgâh
# ---------------------------------------------------------------------------

def _kanit_metni_mutasyonu(ad):
    """``kanit.py``nin bozulmuş bir sürümünü döndürür (None = dosya yok)."""
    asil = (DEPO / KANIT_KAYNAGI).read_text(encoding='utf-8')
    onek_satiri = "GEREKCE_ONEKI = 'kanıt yok: '\n"
    isaret_satiri = "GELISTIRME_ISARETI = 'docs/scofield'\n"
    assert onek_satiri in asil and isaret_satiri in asil, (
        'kanit.py sözleşme satırları değişmiş — tezgâh güncellenmeli')
    if ad == 'kopya':
        return asil
    if ad == 'yok':
        return None
    if ad == 'onek_silindi':
        return asil.replace(onek_satiri, '')
    if ad == 'onek_bos':
        return asil.replace(onek_satiri, "GEREKCE_ONEKI = ''\n")
    if ad == 'onek_literal_degil':
        return asil.replace(onek_satiri,
                            "GEREKCE_ONEKI = 'kanıt' + ' yok: '\n")
    if ad == 'isaret_silindi':
        return asil.replace(isaret_satiri, '')
    if ad == 'ayristirilamaz':
        return asil + '\ndef (:\n'
    raise ValueError(ad)


def _tezgah(tmp_path, docs=False, kanit='kopya'):
    """Kapının koştuğu küçük bir depo kökü kurar (cwd = bu kök)."""
    kok = tmp_path / 'kok'
    (kok / 'tests' / 'support').mkdir(parents=True)
    (kok / 'tests' / 'test_temiz.py').write_text(
        'def test_bir():\n    assert True\n', encoding='utf-8')
    (kok / 'tools').mkdir()
    shutil.copy(DEPO / 'tools' / 'atlama_kapisi.py',
                kok / 'tools' / 'atlama_kapisi.py')
    metin = _kanit_metni_mutasyonu(kanit)
    if metin is not None:
        (kok / KANIT_KAYNAGI).write_text(metin, encoding='utf-8')
    if docs:
        (kok / K.GELISTIRME_ISARETI).mkdir(parents=True)
    return kok


def _gerekce(yol=KANIT_YOLU):
    """ÜRÜNÜN gerekçe metni (``kanit.GEREKCE_KALIBI``), elle yazılmış değil."""
    return K.GEREKCE_KALIBI.format(yol=yol)


def _junit(normal=0, kanit_test=0, kanit_modul=0, normal_modul=0, xfail=0,
           ic_onek=0, xfail_kanit=0, toplam=TOPLANAN_DOCSSUZ):
    """Ölçülen biçimlerle sentetik junit (ElementTree ile — kaçış doğru).

    * gövde içi atlama       : ``type='pytest.skip'``, message = gerekçe
    * modül düzeyi atlama    : ``type`` YOK, message='collection skipped',
      metin = ``repr((yol, satır, 'Skipped: <gerekçe>'))`` (pytest'in yazdığı)
    * xfail                  : ``type='pytest.xfail'``
    """
    kok = ET.Element('testsuites')
    suite = ET.SubElement(kok, 'testsuite', name='pytest',
                          tests=str(toplam))

    def ekle(classname, name, **skipped):
        tc = ET.SubElement(suite, 'testcase', classname=classname, name=name)
        metin = skipped.pop('metin', None)
        s = ET.SubElement(tc, 'skipped', **skipped)
        if metin is not None:
            s.text = metin

    ET.SubElement(suite, 'testcase', classname='tests.test_x', name='gecen')
    for i in range(normal):
        ekle('tests.test_x', f'n{i}', type='pytest.skip',
             message='build123d kurulu degil (STEP uretimi atlanir)',
             metin=f'/x/tests/test_x.py:{i}: atlandi')
    for i in range(kanit_test):
        g = _gerekce()
        ekle(f'tests.test_k{i % 40}', f'k{i}', type='pytest.skip', message=g,
             metin=f'/x/tests/support/kanit.py:166: {g}')
    for i in range(kanit_modul):
        ekle('', f'tests.test_km{i}', message='collection skipped',
             metin=repr(('/x/tests/support/kanit.py', 166,
                         'Skipped: ' + _gerekce())))
    for i in range(normal_modul):
        ekle('', f'tests.test_nm{i}', message='collection skipped',
             metin=repr(('/x/tests/test_nm.py', 2,
                         "Skipped: could not import 'shapely'")))
    for i in range(xfail):
        ekle('tests.test_x', f'x{i}', type='pytest.xfail', message='borc imi')
    for i in range(xfail_kanit):
        ekle('tests.test_x', f'xk{i}', type='pytest.xfail',
             message=_gerekce())
    for i in range(ic_onek):
        # Önek gerekçenin İÇİNDE, BAŞINDA değil: kanıt sınıfına SIZMAMALI.
        ekle('tests.test_x', f'io{i}', type='pytest.skip',
             message='opsiyonel paket yok; ' + _gerekce())
    return ET.tostring(kok, encoding='unicode')


def _arac(kok, xml):
    """``tools/atlama_kapisi.kapi`` — ``release.yml``in çağırdığı gövde."""
    rapor = kok / 'pytest-report.xml'
    if xml is not None:
        rapor.write_text(xml, encoding='utf-8')
    satirlar = []
    hata = kapi(str(rapor), tests_dizini=str(kok / 'tests'),
                yaz=satirlar.append)
    return not hata, '\n'.join(satirlar + hata)


def _yml_govdesi(is_adi):
    import yaml
    veri = yaml.safe_load((DEPO / '.github/workflows/tests.yml').read_text(
        encoding='utf-8'))
    for adim in veri['jobs'][is_adi]['steps']:
        if re.search(r'Atlama bütçesi', adim.get('name', '')):
            m = re.search(r"python\s+-\s+<<'PY'\n(.*?)\n\s*PY\s*$",
                          adim.get('run', ''), re.S)
            assert m, f'{is_adi} bütçe adımı heredoc kalıbında değil'
            return m.group(1)
    raise AssertionError(f'{is_adi} işinde "Atlama bütçesi" adımı yok')


def _yaml(kok, xml, is_adi='pytest'):
    """``tests.yml`` gövdesini ``kok`` içinde EXEC eder (CI'ın yaptığı gibi)."""
    rapor = kok / ('pytest-report.xml' if is_adi == 'pytest'
                   else 'step-report.xml')
    if xml is not None:
        rapor.write_text(xml, encoding='utf-8')
    kod = compile(_yml_govdesi(is_adi), f'<tests.yml::{is_adi}>', 'exec')
    tampon = io.StringIO()
    eski = os.getcwd()
    os.chdir(kok)
    cikis = None
    try:
        with contextlib.redirect_stdout(tampon):
            try:
                exec(kod, {'__name__': '__main__'})   # noqa: S102 — bilerek
            except SystemExit as exc:
                cikis = exc.code
    finally:
        os.chdir(eski)
    cikti = tampon.getvalue() + ('' if cikis in (0, None) else str(cikis))
    return cikis in (0, None), cikti


def _rapor_satiri(cikti):
    m = re.search(r"kanit_atlamasi=(\d+) \(docs'suz agac: (evet|hayir)\)",
                  cikti)
    assert m, f'rapor ayrı kanıt sayısını basmıyor. Çıktı:\n{cikti[-800:]}'
    return int(m.group(1)), m.group(2)


# ---------------------------------------------------------------------------
# Ana bütçe: araç ve YAML gövdesi AYNI girdide AYNI hükmü verir
# ---------------------------------------------------------------------------

#: (ad, junit argümanları, docs/scofield var mı, beklenen hüküm, kanıt sayısı)
ANA_BUTCE_SENARYOLARI = [
    # (a) 700 kanıt atlaması (697 test + 3 modül) + tam bütçe normal: AÇIK
    ('a_700_kanit_76_normal_docssuz',
     dict(normal=ATLAMA_BUTCESI, kanit_test=697, kanit_modul=3), False,
     True, 700),
    # (b) aynı rapor, ağaçta docs/scofield VAR: KAPALI
    ('b_ayni_rapor_docs_VAR',
     dict(normal=ATLAMA_BUTCESI, kanit_test=697, kanit_modul=3), True,
     False, 700),
    # (b') TEK bir kanıt atlaması bile, docs VARKEN: KAPALI
    ('b_tek_kanit_docs_VAR', dict(kanit_test=1), True, False, 1),
    # (c) bütçe +1 normal atlama (kanıt yok): KAPALI; sınırda AÇIK
    ('c_77_normal', dict(normal=ATLAMA_BUTCESI + 1), False, False, 0),
    ('c_76_normal_sinir', dict(normal=ATLAMA_BUTCESI), False, True, 0),
    # (d) kanıt OLMAYAN modül düzeyi atlama: KAPALI
    ('d_kanitsiz_modul', dict(normal_modul=1), False, False, 0),
    # (e) kanıt önekli modül düzeyi atlama, docs'suz: AÇIK ve bütçeyi yemez
    ('e_kanit_modul_docssuz', dict(normal=ATLAMA_BUTCESI, kanit_modul=3),
     False, True, 3),
    # önek gerekçenin BAŞINDA olmalı: içinde geçen normal sayılır -> 77
    ('onek_icinde_sizmaz', dict(normal=ATLAMA_BUTCESI, ic_onek=1), False,
     False, 0),
    # xfail hiçbir sınıfa girmez (önekli gerekçe taşısa bile)
    ('xfail_kanit_sayilmaz', dict(normal=ATLAMA_BUTCESI, xfail_kanit=50),
     False, True, 0),
    # kanıt atlaması toplama tabanını gizlemez
    ('toplama_cokmesi_kanitla_gizlenmez',
     dict(kanit_test=10, toplam=TOPLANAN_TABANI - 1), False, False, 10),
]


@pytest.mark.parametrize('ad,junit,docs,beklenen,kanit_sayisi', ANA_BUTCE_SENARYOLARI,
                         ids=[s[0] for s in ANA_BUTCE_SENARYOLARI])
def test_arac_ve_yaml_ayni_hukum(tmp_path, ad, junit, docs, beklenen,
                                 kanit_sayisi):
    xml = _junit(**junit)
    arac_acik, arac_cikti = _arac(_tezgah(tmp_path / 'a', docs=docs), xml)
    yaml_acik, yaml_cikti = _yaml(_tezgah(tmp_path / 'y', docs=docs), xml)
    assert arac_acik == yaml_acik, (
        f'[{ad}] iki gövde AYRIŞTI: araç={arac_acik}, tests.yml={yaml_acik}.'
        f'\n--- araç:\n{arac_cikti[-600:]}\n--- yaml:\n{yaml_cikti[-600:]}')
    assert arac_acik is beklenen, (
        f'[{ad}] beklenen {"AÇIK" if beklenen else "KAPALI"}, araç '
        f'{"AÇIK" if arac_acik else "KAPALI"}:\n{arac_cikti[-800:]}')
    for cikti in (arac_cikti, yaml_cikti):
        sayi, agac = _rapor_satiri(cikti)
        assert sayi == kanit_sayisi, (ad, sayi, cikti[-400:])
        assert agac == ('hayir' if docs else 'evet'), (ad, agac)


def test_docs_VARKEN_gerekce_sessiz_kaybi_soyler(tmp_path):
    """(b) Kırmızının gerekçesi bütçe değil KANIT kuralı olmalı."""
    xml = _junit(kanit_test=1)
    for kos in (_arac, _yaml):
        acik, cikti = kos(_tezgah(tmp_path / kos.__name__, docs=True), xml)
        assert not acik
        assert 'kanit yok' in cikti and K.GELISTIRME_ISARETI in cikti, cikti
        assert 'butce' not in cikti.split('kanit yok', 1)[1][:40], cikti


def test_kanit_atlamasi_normal_listeye_girmez(tmp_path):
    """(1)+(2): 700 kanıt atlaması ``atlanan`` ve ``toplama_duzeyi``ne girmez."""
    xml = _junit(normal=5, kanit_test=697, kanit_modul=3)
    for kos in (_arac, _yaml):
        _acik, cikti = kos(_tezgah(tmp_path / kos.__name__), xml)
        assert re.search(r'atlanan=5 \(toplama_duzeyi=0\)', cikti), cikti[:400]


# ---------------------------------------------------------------------------
# (f) Önek okunamazsa kapı KAPANIR — üç gövdede de
# ---------------------------------------------------------------------------

BOZUK_KANIT = ['yok', 'onek_silindi', 'onek_bos', 'onek_literal_degil',
               'isaret_silindi', 'ayristirilamaz']


@pytest.mark.parametrize('bozukluk', BOZUK_KANIT)
def test_onek_okunamazsa_KAPALI_ana_butce(tmp_path, bozukluk):
    xml = _junit(normal=1, kanit_test=10)          # sağlam sözleşmede AÇIK
    for kos in (_arac, _yaml):
        acik, cikti = kos(_tezgah(tmp_path / kos.__name__, kanit=bozukluk),
                          xml)
        assert not acik, (
            f'[{bozukluk}] kanit.py sözleşmesi okunamadı ama {kos.__name__} '
            f'AÇIK — önek bilinmeden kanıt sınıfı ayrılamaz:\n{cikti[-600:]}')


@pytest.mark.parametrize('bozukluk', BOZUK_KANIT)
def test_onek_okunamazsa_KAPALI_step_export(tmp_path, bozukluk):
    xml = _junit(kanit_test=2, kanit_modul=1, toplam=TOPLANAN_STEP_DOCSSUZ)
    acik, cikti = _yaml(_tezgah(tmp_path, kanit=bozukluk), xml, 'step-export')
    assert not acik, f'[{bozukluk}] step-export AÇIK kaldı:\n{cikti[-600:]}'


def test_saglam_sozlesmede_ayni_raporlar_ACIK(tmp_path):
    """(f)'nin kontrolü: aynı raporlar sağlam ``kanit.py`` ile AÇIK."""
    assert _arac(_tezgah(tmp_path / 'a'), _junit(normal=1, kanit_test=10))[0]
    assert _yaml(_tezgah(tmp_path / 'y'), _junit(normal=1, kanit_test=10))[0]
    assert _yaml(_tezgah(tmp_path / 's'),
                 _junit(kanit_test=2, kanit_modul=1,
                        toplam=TOPLANAN_STEP_DOCSSUZ), 'step-export')[0]


def test_sozlesme_urunun_kendi_onekini_okuyor():
    assert kanit_sozlesmesi(DEPO) == (K.GEREKCE_ONEKI, K.GELISTIRME_ISARETI)
    assert K.GEREKCE_KALIBI.startswith(K.GEREKCE_ONEKI)


# ---------------------------------------------------------------------------
# step-export (bütçe SIFIR) — kanıt sınıfı aynı kuralla
# ---------------------------------------------------------------------------

STEP_SENARYOLARI = [
    ('kanit_docssuz', dict(kanit_test=2, kanit_modul=1), False, True),
    ('kanit_docs_VAR', dict(kanit_test=2, kanit_modul=1), True, False),
    ('normal_atlama_hala_kirmizi', dict(normal=1), False, False),
    ('kanitsiz_modul_hala_kirmizi', dict(normal_modul=1), False, False),
]


@pytest.mark.parametrize('ad,junit,docs,beklenen', STEP_SENARYOLARI,
                         ids=[s[0] for s in STEP_SENARYOLARI])
def test_step_export_kanit_sinifi(tmp_path, ad, junit, docs, beklenen):
    xml = _junit(toplam=TOPLANAN_STEP_DOCSSUZ, **junit)
    acik, cikti = _yaml(_tezgah(tmp_path, docs=docs), xml, 'step-export')
    assert acik is beklenen, f'[{ad}]\n{cikti[-800:]}'
    _rapor_satiri(cikti)


# ---------------------------------------------------------------------------
# Gerçek pytest çıktısı — biçim varsayımı her koşumda yeniden ölçülür
# ---------------------------------------------------------------------------

class TestGercekPytestCiktisi:
    """Sentetik biçim değil: gerçek ``kanit.py`` + gerçek pytest junit'i.

    docs'suz küçük bir ağaçta üç biçim üretilir (gövde içi, modül düzeyi,
    ``skipif`` koşulunda çağrı). Kapılar üçünü de kanıt sınıfına koymalı;
    tek kırmızı gerekçe toplama tabanı olmalı (ağaçta 3 test var).
    """

    @pytest.fixture(scope='class')
    def rapor(self, tmp_path_factory):
        kok = tmp_path_factory.mktemp('gercek') / 'kok'
        (kok / 'tests' / 'support').mkdir(parents=True)
        (kok / 'tests' / '__init__.py').write_text('', encoding='utf-8')
        (kok / 'tests' / 'support' / '__init__.py').write_text(
            '', encoding='utf-8')
        shutil.copy(DEPO / KANIT_KAYNAGI, kok / KANIT_KAYNAGI)
        (kok / 'pytest.ini').write_text('[pytest]\n', encoding='utf-8')
        bas = 'from tests.support.kanit import kanit_gerekli\n'
        (kok / 'tests' / 'test_govde.py').write_text(
            bas + "def test_a():\n    kanit_gerekli('docs/scofield/a.json')\n",
            encoding='utf-8')
        (kok / 'tests' / 'test_modul.py').write_text(
            bas + "X = kanit_gerekli('docs/scofield/b.json')\n"
            "def test_b():\n    pass\n", encoding='utf-8')
        (kok / 'tests' / 'test_skipif.py').write_text(
            'import os, pytest\n' + bas +
            "@pytest.mark.skipif(not os.path.isdir(kanit_gerekli("
            "'docs/scofield/c')), reason='yok')\n"
            "def test_c():\n    pass\n", encoding='utf-8')
        ortam = dict(os.environ, PYTHONPATH=str(kok))
        ortam.pop('HRMA_KANIT_ZORUNLU', None)
        subprocess.run(
            [sys.executable, '-m', 'pytest', 'tests', '-q',
             '-p', 'no:cacheprovider', '--junitxml=pytest-report.xml'],
            cwd=kok, env=ortam, capture_output=True, text=True, timeout=120)
        yol = kok / 'pytest-report.xml'
        assert yol.is_file(), 'gerçek pytest junit raporu üretmedi'
        return yol.read_text(encoding='utf-8')

    def test_uc_bicim_de_kanit_sinifinda(self, tmp_path, rapor):
        for kos in (_arac, _yaml):
            acik, cikti = kos(_tezgah(tmp_path / kos.__name__), rapor)
            assert _rapor_satiri(cikti) == (3, 'evet'), cikti
            assert re.search(r'atlanan=0 \(toplama_duzeyi=0\)', cikti), cikti
            # Tek kırmızı gerekçe: 3 test toplandı (< taban). Bütçe ve
            # modül kuralı DEVREYE GİRMEMELİ.
            assert not acik and 'toplandi' in cikti, cikti
            assert 'MODUL toplama' not in cikti and 'butce 7' not in cikti

    def test_step_export_de_ayni_siniflandirma(self, tmp_path, rapor):
        acik, cikti = _yaml(_tezgah(tmp_path), rapor, 'step-export')
        assert _rapor_satiri(cikti) == (3, 'evet'), cikti
        assert re.search(r'gercek=0 toplama_duzeyi=0\)', cikti), cikti
