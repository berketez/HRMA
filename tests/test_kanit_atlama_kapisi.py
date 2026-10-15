"""ÖH D36 kanit-atlama — docs/ kanıt kapısının bekçisi.

Yayın dalı docs'suz üretilir (``packaging/yayin_dali_uret.sh``: docs/scofield,
docs/arastirma, docs/tasarim ÇIKARILIR). O dalda test süitinin koşabilmesi
için kanıt okuyan her yer ``tests/support/kanit.py`` kapısından geçer: kanıt
yoksa gerekçeli atlama. Bu dosya kapının SESSİZ KAYIP üretmediğini ölçer:

(a) Geliştirme ağacında (docs/scofield VAR) statik olarak bilinen her kanıt
    yolu gerçekten vardır ve kapı eksik kanıtta bile ATLAMAZ.
(b) Test kodunda docs/ kanıtını kapı DIŞINDA okuyan yer kalmamıştır
    (``tests/support/kanit_tarayici.py`` — aynı tarayıcıyı yayın dalı
    dedektörü de kullanır).
(c) Kapıdan geçen okuma sayısı tabanın altına düşmemiştir (tek yönlü mandal).

Ek olarak kapının üç davranışı (atla / hata / geliştirme) sentetik bir
ağaçta GERÇEK pytest koşumuyla sınanır — toplama düşmesi (23 Eylül 2026
ölçümü: ``tests/test_d23_bekci_cevirisi_a1.py`` ithal anında okuyordu) geri
gelemesin.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from tests.support import kanit as K
from tests.support.kanit import kanit_gerekli
from tests.support.kanit_tarayici import HARIC as TARAYICI_HARIC
from tests.support.kanit_tarayici import tara, tara_agac

KOK = pathlib.Path(__file__).resolve().parents[1]
TESTS = KOK / 'tests'

#: Kapının kendi uygulaması taranmaz (kanıt dizinlerini TANIMLAMAK zorunda).
TARAMA_DISI = frozenset({
    'tests/support/kanit.py',
    'tests/support/kanit_tarayici.py',
})

#: (c) TEK YÖNLÜ MANDAL — ölçüldü 23 Eylül 2026 (dal dalga36/kanit-atlama,
#: dönüşüm sonrası; bu dosyanın kendi çağrıları SAYILMAZ): kapı çağrısı
#: (kanit_gerekli + kanit_cikti) sayısı ve kapıyı kullanan dosya sayısı.
#: DÜŞERSE kırmızı: bir okuma ya kapıdan çıkarılmış ya da kanıt okuyan
#: bekçi silinmiştir — ikisi de ADIYLA karar ister. Büyümesi serbesttir
#: (yeni kanıt okuyan bekçi kapıyı kullanıyor demektir).
KAPI_CAGRISI_TABANI = 296
KAPI_KULLANAN_DOSYA_TABANI = 100
BU_DOSYA = 'tests/test_kanit_atlama_kapisi.py'

#: Sentetik kaynaklarda kanıt dizini adı — bu dosyanın kendisi tarayıcıya
#: tohum vermesin diye parçalardan kurulur.
_D = '/'.join(('docs', 'scofield'))


def _test_dosyalari():
    for yol in sorted(TESTS.rglob('*.py')):
        if '__pycache__' in yol.parts:
            continue
        bagil = yol.relative_to(KOK).as_posix()
        if bagil in TARAMA_DISI:
            continue
        yield bagil, yol.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def tarama():
    # Modüller arası: bir test modülünün kanıt sabitini (ör.
    # sahte_sayfa.CANLI_TUR_RAPORU) ithal eden modül de taranır.
    return tara_agac(dict(_test_dosyalari()))


# ---------------------------------------------------------------------------
# Tek kaynak: dışlanan dizin kümesi üç yerde aynı olmalı
# ---------------------------------------------------------------------------
def test_haric_kumesi_yardimci_tarayici_ve_dedektorde_ayni():
    betik = (KOK / 'packaging' / 'yayin_dali_uret.sh').read_text(encoding='utf-8')
    m = re.search(r'HARIC="\$\{HARIC:-([^}]*)\}"', betik)
    assert m, 'yayin_dali_uret.sh içinde HARIC varsayılanı bulunamadı'
    dedektor = tuple(m.group(1).split())
    assert K.HARIC == TARAYICI_HARIC == dedektor, (
        'yayın dalından çıkarılan dizinler ile kapının tanıdığı dizinler '
        'ayrıştı: yardımcı %r, tarayıcı %r, dedektör %r'
        % (K.HARIC, TARAYICI_HARIC, dedektor))


def test_dedektor_ayni_tarayiciyi_kullaniyor():
    betik = (KOK / 'packaging' / 'yayin_dali_uret.sh').read_text(encoding='utf-8')
    assert 'tests/support/kanit_tarayici.py' in betik, (
        'dedektör kapı DIŞINDA okumayı bu bekçiyle aynı tarayıcıyla ölçmüyor')


# ---------------------------------------------------------------------------
# (a) Geliştirme ağacında hiçbir kanıt yolu atlanmaz
# ---------------------------------------------------------------------------
def test_a_gelistirme_agacinda_statik_kanit_yollarinin_hepsi_var(tarama):
    kanit_gerekli(K.GELISTIRME_ISARETI)          # docs'suz ağaçta gerekçeli atla
    assert K.gelistirme_agaci()
    toplam, eksik = 0, []
    for bagil, sonuc in tarama.items():
        for satir, yol in sonuc.tohumlar:
            toplam += 1
            if K._karar(yol, KOK, {}) != 'var':
                eksik.append('%s:%d -> %s' % (bagil, satir, yol))
    assert toplam > 0, 'tarayıcı hiç kanıt yolu bulmadı — ölçüm boş'
    assert not eksik, (
        'geliştirme ağacında OLMAYAN kanıt yolu (yayın dalında gerekçeli '
        'atlanırdı ama burada kırmızı vermesi gerekir): %s' % eksik)


def test_a_gelistirme_agacinda_kapi_eksik_kanitta_bile_atlamaz(monkeypatch):
    kanit_gerekli(K.GELISTIRME_ISARETI)
    monkeypatch.delenv(K.ZORUNLU_DEGISKENI, raising=False)
    yok = _D + '/__kanit_atlama_kapisi_olmayan__.json'
    assert not (KOK / yok).exists()
    assert K._karar(yok, KOK, {}) == 'gelistirme'
    # Atlama istisnası YÜKSELMEZ; yol aynen döner (çağıran kırmızı verir).
    assert kanit_gerekli(yok) == yok
    assert K.kanit_cikti(yok) == yok


# ---------------------------------------------------------------------------
# Kapı kararları — ağaçtan bağımsız (sentetik kök)
# ---------------------------------------------------------------------------
def test_kapi_kararlari_sentetik_kokte(tmp_path):
    (tmp_path / 'tests').mkdir()
    yol = _D + '/x.json'
    assert K._karar(yol, tmp_path, {}) == 'atla'
    assert K._karar(yol, tmp_path, {K.ZORUNLU_DEGISKENI: '1'}) == 'hata'
    assert K._karar('hrma/app.py', tmp_path, {}) == 'kapsam_disi'
    (tmp_path / _D).mkdir(parents=True)
    assert K._karar(yol, tmp_path, {}) == 'gelistirme'
    (tmp_path / yol).write_text('{}', encoding='utf-8')
    assert K._karar(yol, tmp_path, {}) == 'var'
    assert K._karar(str(tmp_path / yol), tmp_path, {}) == 'var'


def test_kapi_docssuz_agacta_gerekceyle_atlar_zorunluda_hata(monkeypatch, tmp_path):
    monkeypatch.setattr(K, 'KOK', tmp_path)
    monkeypatch.delenv(K.ZORUNLU_DEGISKENI, raising=False)
    yol = _D + '/raw/OH/x.json'
    with pytest.raises(pytest.skip.Exception) as atlama:
        kanit_gerekli(yol)
    gerekce = str(atlama.value)
    assert gerekce.startswith(K.GEREKCE_ONEKI + yol), gerekce
    assert "yayın dalı docs'suz üretilir" in gerekce, gerekce
    monkeypatch.setenv(K.ZORUNLU_DEGISKENI, '1')
    # Atlama istisnası da YAKALANIR: zorunlu kipte atlayan bir kapı bu testi
    # "skipped" diye geçirip kusuru saklamasın, KIRMIZI versin.
    for kapi in (kanit_gerekli, K.kanit_cikti):
        with pytest.raises((pytest.fail.Exception, pytest.skip.Exception)) as sonuc:
            kapi(yol)
        assert sonuc.type is pytest.fail.Exception, (
            '%s: HRMA_KANIT_ZORUNLU=1 iken eksik kanıt ATLANDI (%s)'
            % (kapi.__name__, sonuc.value))
    # Tür korunur: str -> str, Path -> Path
    monkeypatch.delenv(K.ZORUNLU_DEGISKENI)
    (tmp_path / yol).parent.mkdir(parents=True)
    (tmp_path / yol).write_text('{}', encoding='utf-8')
    assert kanit_gerekli(yol) == yol
    assert kanit_gerekli(tmp_path / yol) == tmp_path / yol


def test_kanit_yolu_depo_kokune_gore_cozer_ve_kapsami_denetler():
    assert K.kanit_yolu(_D + '/raw') == KOK / _D / 'raw'
    with pytest.raises(ValueError):
        K.kanit_yolu('hrma/app.py')
    with pytest.raises(ValueError):
        K.kanit_yolu('/' + _D)


_ORNEK_MODUL = '''
from tests.support.kanit import kanit_gerekli
VERI = open(kanit_gerekli('@D@/modul.json')).read()
def test_modul():
    assert VERI
'''

_ORNEK_GOVDE = '''
from tests.support.kanit import kanit_gerekli
def test_kanit():
    open(kanit_gerekli('@D@/govde.json')).read()
def test_urun():
    assert 1 + 1 == 2
'''


def _sentetik_kosum(tmp_path, ortam_ek=None, docs_var=False):
    (tmp_path / 'tests' / 'support').mkdir(parents=True)
    (tmp_path / 'tests' / '__init__.py').write_text('', encoding='utf-8')
    shutil.copy(KOK / 'tests' / 'support' / 'kanit.py',
                tmp_path / 'tests' / 'support' / 'kanit.py')
    (tmp_path / 'tests' / 'test_modul.py').write_text(
        _ORNEK_MODUL.replace('@D@', _D), encoding='utf-8')
    (tmp_path / 'tests' / 'test_govde.py').write_text(
        _ORNEK_GOVDE.replace('@D@', _D), encoding='utf-8')
    if docs_var:
        (tmp_path / _D).mkdir(parents=True)
    ortam = {k: v for k, v in os.environ.items()
             if k != K.ZORUNLU_DEGISKENI and not k.startswith('PYTEST_')}
    ortam.update(ortam_ek or {})
    return subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests', '-q', '-rs',
         '-p', 'no:cacheprovider', '--rootdir', str(tmp_path),
         '-c', os.devnull],
        cwd=tmp_path, env=ortam, capture_output=True, text=True, timeout=120)


def test_docssuz_agacta_modul_duzeyi_okuma_toplamayi_dusurmez(tmp_path):
    """23 Eylül ölçümünün kusuru: ithal anında okuma TOPLAMAYI düşürüyordu."""
    r = _sentetik_kosum(tmp_path)
    cikti = r.stdout + r.stderr
    assert r.returncode == 0, cikti
    assert re.search(r'\b1 passed, 2 skipped\b', cikti), cikti
    assert 'error' not in cikti.lower(), cikti
    assert cikti.count(K.GEREKCE_ONEKI) == 2, cikti


def test_docssuz_agacta_zorunlu_kipte_eksik_kanit_hata(tmp_path):
    r = _sentetik_kosum(tmp_path, {K.ZORUNLU_DEGISKENI: '1'})
    cikti = r.stdout + r.stderr
    assert r.returncode != 0, cikti
    assert 'skipped' not in cikti, cikti
    assert '%s=1 ama kanıt eksik' % K.ZORUNLU_DEGISKENI in cikti, cikti


def test_gelistirme_agacinda_eksik_kanit_atlanmaz_kirmizi_verir(tmp_path):
    r = _sentetik_kosum(tmp_path, docs_var=True)
    cikti = r.stdout + r.stderr
    assert r.returncode != 0, cikti
    assert 'skipped' not in cikti, cikti
    assert 'FileNotFoundError' in cikti, cikti


# ---------------------------------------------------------------------------
# (b) Kapı DIŞINDA kanıt okuması yok
# ---------------------------------------------------------------------------
def test_b_kanit_kapi_disinda_okunmuyor(tarama):
    ihlaller = ['%s:%d: %s' % (bagil, i.satir, i.ifade)
                for bagil, sonuc in sorted(tarama.items())
                for i in sonuc.ihlaller]
    assert not ihlaller, (
        '%d yerde docs/ kanıtı kapı DIŞINDA okunuyor — yayın dalında (docs\'suz) '
        'bu yerler FileNotFoundError verir ya da toplamayı düşürür. Okumayı '
        'kanit_gerekli(...) ile (yazılan çıktıyı kanit_cikti(...) ile) sarın:\n  %s'
        % (len(ihlaller), '\n  '.join(ihlaller)))


# ---------------------------------------------------------------------------
# (c) Kapıdan geçen okuma sayısı düşmez
# ---------------------------------------------------------------------------
def test_c_kapi_sayisi_tabanin_altina_dusmedi(tarama):
    donusen = {b: s for b, s in tarama.items() if b != BU_DOSYA}
    cagri = sum(len(s.kapi_cagrilari) for s in donusen.values())
    dosya = sum(1 for s in donusen.values() if s.kapi_cagrilari)
    assert cagri >= KAPI_CAGRISI_TABANI and dosya >= KAPI_KULLANAN_DOSYA_TABANI, (
        'kapıdan geçen okuma DÜŞTÜ: %d çağrı / %d dosya (taban %d / %d). Bir '
        'okuma kapıdan çıkarılmış ya da kanıt okuyan bekçi silinmiş; bilinçli '
        'ise tabanı ölçümle ve gerekçeyle indirin.'
        % (cagri, dosya, KAPI_CAGRISI_TABANI, KAPI_KULLANAN_DOSYA_TABANI))


# ---------------------------------------------------------------------------
# Tarayıcının kendisi boş bekçi olmasın — sentetik vakalar
# ---------------------------------------------------------------------------
_VAKALAR = [
    # (kaynak, beklenen ihlal sayısı)
    ("import os\nKOK='.'\nK = os.path.join(KOK, 'docs', 'scofield', 'a')\n"
     "def test():\n    open(os.path.join(K, 'x.json')).read()\n", 1),
    ("import os\nfrom tests.support.kanit import kanit_gerekli\nKOK='.'\n"
     "K = os.path.join(KOK, 'docs', 'scofield', 'a')\n"
     "def test():\n    open(kanit_gerekli(os.path.join(K, 'x.json'))).read()\n", 0),
    ("import pathlib\nKOK = pathlib.Path('.')\n"
     "def test():\n    assert (KOK / 'docs' / 'scofield' / 'x').exists()\n", 1),
    ("def _oku(y):\n    return open(y).read()\n"
     "def test():\n    _oku('@D@/x.md')\n", 1),
    ("def test():\n    x = 3\n    assert x, 'kanıt: @D@/x.md'\n", 0),
    ("def test(metin):\n    assert '@D@/x.md' in metin\n", 0),
    ("import subprocess\nH = '@D@/h.js'\n"
     "def test():\n    subprocess.run(['node', H])\n", 1),
    ("class T:\n    Y = '@D@/y.json'\n"
     "    def test(self):\n        open(self.Y)\n", 1),
    ("import pytest\nL = ('hrma/a.py', '@D@/b.md')\n"
     "@pytest.mark.parametrize('yol', L)\n"
     "def test(yol):\n    open(yol)\n", 1),
    ("K = '@D@/k'\ndef _k():\n    return K\n", 1),
    ("from tests.support.kanit import kanit_cikti\nC = '@D@/_c.json'\n"
     "def test():\n    open(kanit_cikti(C), 'w')\n", 0),
    # kanıt dizinindeki modülün İTHALİ bir okumadır; önünde kapı yoksa ihlal
    ("def test():\n    from @M@.betikler import izolasyon\n", 1),
    ("from tests.support.kanit import kanit_gerekli\n"
     "def test():\n    kanit_gerekli('@D@/betikler/izolasyon.py')\n"
     "    from @M@.betikler import izolasyon\n", 0),
]


def _yerlestir(kaynak):
    return kaynak.replace('@D@', _D).replace('@M@', _D.replace('/', '.'))


@pytest.mark.parametrize('kaynak,beklenen', _VAKALAR)
def test_tarayici_sentetik_vakalar(kaynak, beklenen):
    sonuc = tara(_yerlestir(kaynak))
    assert len(sonuc.ihlaller) == beklenen, sonuc.ihlaller


def test_tarayici_moduller_arasi_kirliligi_izler():
    """Bir test modülünün kanıt sabitini ithal eden modül de denetlenir."""
    kaynaklar = {
        'tests/support/ikiz.py': _yerlestir(
            "import pathlib\nKOK = pathlib.Path('.')\n"
            "RAPOR = KOK / '@D@/tur/rapor.json'\n"),
        'tests/test_a.py': "from tests.support import ikiz\n"
                           "def test():\n    assert ikiz.RAPOR.is_file()\n",
        'tests/test_b.py': "from tests.support.ikiz import RAPOR\n"
                           "def test():\n    open(RAPOR)\n",
        'tests/test_c.py': "from tests.support import ikiz\n"
                           "def test():\n    assert ikiz.RAPOR.name\n",
    }
    sonuc = tara_agac(kaynaklar)
    assert sonuc['tests/support/ikiz.py'].disa_acik == {'RAPOR'}
    assert len(sonuc['tests/test_a.py'].ihlaller) == 1
    assert len(sonuc['tests/test_b.py'].ihlaller) == 1
    assert sonuc['tests/test_c.py'].ihlaller == []
