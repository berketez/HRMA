"""node çağrı sözleşmesi bekçisi — betik argv ile DEĞİL stdin ile verilir.

NEDEN BU DOSYA VAR (ölçülmüş kusur, 2026-08-18)
-----------------------------------------------
Linux CI kırmızıydı:

    tests/test_viz3d_cfd_alan.py::TestHizalama
        ::test_gercek_yenidenornekleme_iki_seviyede_kabul
    OSError: [Errno 7] Argument list too long: node

Test node'a giden betikte HATA YAPMIYORDU; betik hiç KOŞMUYORDU. Koşucu
(``_run``) JS betiğini ``subprocess.run([NODE, <bayrak>, betik])`` ile TEK bir
argv elemanı olarak geçiriyordu. İki ayrı çekirdek tavanı var ve ikisi de
argv'ye uygulanır, stdin'e uygulanmaz:

  * Linux: ``MAX_ARG_STRLEN`` = 131072 bayt — argüman BAŞINA, ARG_MAX'tan
    bağımsız. Aşan tek argüman ``execve`` düzeyinde E2BIG verir.
  * macOS: ``getconf ARG_MAX`` = 1048576 bayt — argv+env TOPLAMI.

Ölçülen betik boyutları (bu depodaki gerçek yükler, yeniden üretildi):

    konik/coarse    60x12 ->   52 612 bayt   (iki tavanın da altında)
    konik/standard 120x24 ->  191 174 bayt   (Linux tavanını AŞIYOR)
    bell /coarse    60x12 ->   53 921 bayt
    bell /standard 120x24 ->  192 570 bayt   (Linux tavanını AŞIYOR)

Yani 'standard' seviye (120x24) betiğe ~190 KB gerçek CFD JSON'u gömüyordu.
macOS'ta tavan 1 MiB olduğu için yerelde YEŞİL, Linux'ta 128 KiB olduğu için
KIRMIZI görünüyordu. Kusur platformun değil MEKANİZMANIN kusuruydu: aynı
koşucu macOS'ta da 1,2 MB'lık betikte ``OSError [Errno 7]`` veriyor (yerel
ölçüm: 400 060 bayt argv -> rc=0; 1 200 060 bayt argv -> E2BIG; aynı iki
betik stdin ile rc=0).

Çözüm: ``subprocess.run([NODE], input=betik, ...)``. stdin bir TTY değilken
node programı stdin'den okur ve CommonJS olarak koşar — ``require``,
``process.stdout.write``, ``JSON.stringify`` davranışı aynıdır (bu dosyanın
canlı kanıt testi ölçer).

BU BEKÇİNİN İKİ AYAĞI
---------------------
1. Tarama: ``tests/`` ağacındaki HİÇBİR python dosyasında node'a betik
   geçiren argv bayrağı kalmadığını YAPISAL olarak (ast) ölçer. Aranan
   bayrak literalleri bu dosyada parça parça kurulur ('-' + 'e' gibi), bu
   yüzden bekçinin kendi kaynağı taramada yanlış pozitif vermez ve tarama
   "kendini muaf tutan" bir istisna listesi TAŞIMAZ.
2. Canlı kanıt: iki tavanın da üstünde (>1,2 MB) bir betiğin gerçekten
   koştuğunu ölçer. Mekanizma ``tests/test_viz3d_cfd_alan.py``'nin GERÇEK
   ``_run`` koşucusundan geçer (import edilir; kopya stdin koşucusu YAZILMAZ
   — kopya olsaydı sözleşme sürüklenir, bekçi ısırmazdı). Isırık: koşucu
   argv biçimine dönerse bu test hem Linux'ta hem macOS'ta E2BIG ile
   kırmızıya döner.
"""

import ast
import collections
import json
import math
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'
NODE = shutil.which('node')

# Koşucu KOPYALANMAZ, ithal edilir — sözleşme tek kaynaktan ölçülsün.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tests.test_viz3d_cfd_alan import _run as CFD_ALAN_KOSUCU  # noqa: E402

# Çekirdek tavanları (yukarıdaki gerekçede ölçüldü)
LINUX_MAX_ARG_STRLEN = 131072
MACOS_ARG_MAX = 1048576
# Canlı kanıtın betik boyutu: İKİ tavanın da üstünde olmalı ki bekçi yalnız
# CI'da değil geliştirme makinesinde de ısırsın.
CANLI_KANIT_BAYT = 1200000

# Aranan bayraklar PARÇALANARAK kurulur: bu dosyanın kaynağında bayrağın
# kendisi bir dizgi literali olarak GEÇMEZ, dolayısıyla tarama bu dosyayı
# istisna tutmadan da temiz bulur.
BETIK_BAYRAKLARI = frozenset({
    '-' + 'e',        # node --eval kısaltması
    '-' + '-eval',
    '-' + 'p',        # değeri basan biçim, yine betik taşır
    '-' + '-print',
})

ALT_SUREC_FONKSIYONLARI = frozenset({
    'run', 'call', 'check_call', 'check_output', 'Popen',
})

NODE_IKILI_ADLARI = frozenset({'node', 'node.exe'})

NodeCagrisi = collections.namedtuple(
    'NodeCagrisi',
    'dosya satir bayraklar stdin_var text_var timeout_var eleman_sayisi')


# ---------------------------------------------------------------------------
# Yapısal tarayıcı — metin değil ast; biçimlendirme/tırnak türü etkilemez
# ---------------------------------------------------------------------------

def _node_referansi_mi(dugum):
    """argv elemanı node ikilisini mi gösteriyor?"""
    if isinstance(dugum, ast.Name):
        return dugum.id.upper().startswith('NODE')
    if isinstance(dugum, ast.Attribute):
        return dugum.attr.upper().startswith('NODE')
    if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
        return pathlib.PurePath(dugum.value).name.lower() in NODE_IKILI_ADLARI
    return False


def _altsurec_cagrisi_mi(cagri):
    fonk = cagri.func
    if isinstance(fonk, ast.Attribute):
        return fonk.attr in ALT_SUREC_FONKSIYONLARI
    if isinstance(fonk, ast.Name):
        return fonk.id in ALT_SUREC_FONKSIYONLARI
    return False


def node_cagrilari(kaynak, dosya_adi):
    """Kaynaktaki ``subprocess.<f>([... NODE ...], ...)`` çağrılarını toplar.

    Her kayıt çağrının sözleşme açısından ölçülen nitelikleriyle döner:
    taşıdığı betik bayrakları (BOŞ olmalı), stdin/text/timeout anahtar
    kelimelerinin varlığı ve argv eleman sayısı.
    """
    agac = ast.parse(kaynak, filename=dosya_adi)
    bulunan = []
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Call) or not _altsurec_cagrisi_mi(dugum):
            continue
        if not dugum.args or not isinstance(dugum.args[0], ast.List):
            continue
        elemanlar = dugum.args[0].elts
        if not any(_node_referansi_mi(e) for e in elemanlar):
            continue
        bayraklar = tuple(sorted({
            e.value for e in elemanlar
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
            and e.value in BETIK_BAYRAKLARI}))
        anahtarlar = {kw.arg for kw in dugum.keywords}
        bulunan.append(NodeCagrisi(
            dosya=dosya_adi, satir=dugum.lineno, bayraklar=bayraklar,
            stdin_var='input' in anahtarlar, text_var='text' in anahtarlar,
            timeout_var='timeout' in anahtarlar,
            eleman_sayisi=len(elemanlar)))
    return bulunan


def _test_dosyalari():
    return sorted(p for p in TESTS.rglob('*.py')
                  if '__pycache__' not in p.parts)


def _tum_cagrilar():
    kayitlar = []
    for yol in _test_dosyalari():
        kayitlar.extend(node_cagrilari(
            yol.read_text(encoding='utf-8'), str(yol.relative_to(ROOT))))
    return kayitlar


# Göçü bu partide yapılan viz ailesi (stdin biçimi burada ZORUNLU)
GOCMUS_DOSYALAR = (
    'tests/test_viz3d_cfd_alan.py',
    'tests/test_viz3d_cad_kipi.py',
    'tests/test_viz3d_gorsel_kalite.py',
    'tests/test_cfd_alan_koprusu.py',
    'tests/test_viz_adaptorleri.py',
)


# ---------------------------------------------------------------------------
# 1. Tarama bekçisi
# ---------------------------------------------------------------------------

class TestArgvBetikYasagi:

    def test_hicbir_test_dosyasi_betigi_argv_ile_gecmiyor(self):
        """tests/ ağacında node'a argv ile betik geçiren çağrı KALMADI."""
        ihlaller = [c for c in _tum_cagrilar() if c.bayraklar]
        assert not ihlaller, (
            'node betigi argv ile geciliyor (Linux MAX_ARG_STRLEN=%d bayt '
            'tavani, macOS ARG_MAX=%d bayt tavani): %s\nCozum: '
            'subprocess.run([NODE], input=betik, ...)'
            % (LINUX_MAX_ARG_STRLEN, MACOS_ARG_MAX,
               '; '.join('%s:%d %s' % (c.dosya, c.satir, ','.join(c.bayraklar))
                         for c in ihlaller)))

    def test_tarama_gercek_dosyalari_goruyor(self):
        """Bekçi boşluğu taramıyor — tarandığı küme ölçülür.

        Bu olmadan tarama bekçisi 'hiç dosya bulamadım' halinde de yeşil
        kalırdı (yalancı yeşil).
        """
        dosyalar = _test_dosyalari()
        assert len(dosyalar) >= 100, len(dosyalar)
        cagrilar = _tum_cagrilar()
        assert len(cagrilar) >= 20, len(cagrilar)
        gorulen = {c.dosya for c in cagrilar}
        eksik = [d for d in GOCMUS_DOSYALAR if d not in gorulen]
        assert not eksik, eksik

    def test_tarayici_argv_bicimini_gercekten_yakaliyor(self):
        """Isırık kanıtı: desen geri gelirse tarayıcı KIRMIZI verir.

        Sentetik kaynak, bayrak literali çalışma anında (``%r``) gömülerek
        kurulur — bu dosyanın kaynağında bayrak dizgisi geçmez.
        """
        for bayrak in sorted(BETIK_BAYRAKLARI):
            kaynak = ('import subprocess\n'
                      'subprocess.run([NODE, %r, script], '
                      'capture_output=True, text=True, timeout=60)\n' % bayrak)
            bulunan = node_cagrilari(kaynak, 'sentetik.py')
            assert len(bulunan) == 1, (bayrak, bulunan)
            assert bulunan[0].bayraklar == (bayrak,), bulunan[0]

    def test_tarayici_dolayli_ikili_adini_da_yakaliyor(self):
        """NODE adı değişse (NODE_BIN) ya da yol dizgisi verilse de yakalar."""
        bayrak = sorted(BETIK_BAYRAKLARI)[0]
        for ikili in ('NODE_BIN', None):
            hedef = ikili if ikili else "'/usr/bin/node'"
            kaynak = ('import subprocess\n'
                      'subprocess.check_output([%s, %r, s])\n'
                      % (hedef, bayrak))
            bulunan = node_cagrilari(kaynak, 'sentetik.py')
            assert len(bulunan) == 1 and bulunan[0].bayraklar == (bayrak,), (
                ikili, bulunan)

    def test_tarayici_mesru_bicimlere_yanlis_pozitif_vermiyor(self):
        """--check, dosya yollu koşum ve stdin biçimi ihlal DEĞİLDİR."""
        kaynak = ('import subprocess\n'
                  "subprocess.run([NODE, '--check', str(P)], text=True)\n"
                  'subprocess.run([NODE, str(harness), str(v)], text=True)\n'
                  'subprocess.run([NODE], input=betik, capture_output=True,\n'
                  '               text=True, timeout=60)\n')
        bulunan = node_cagrilari(kaynak, 'sentetik.py')
        assert len(bulunan) == 3, bulunan
        assert [c.bayraklar for c in bulunan] == [(), (), ()], bulunan
        assert [c.stdin_var for c in bulunan] == [False, False, True], bulunan

    def test_gocmus_kosucular_stdin_bicimini_ve_sozlesmeyi_koruyor(self):
        """Beş viz dosyasında stdin koşucusu VAR ve text/timeout korunmuş."""
        cagrilar = _tum_cagrilar()
        for dosya in GOCMUS_DOSYALAR:
            stdin_cagrilari = [c for c in cagrilar
                               if c.dosya == dosya and c.stdin_var]
            assert stdin_cagrilari, dosya
            for cagri in stdin_cagrilari:
                # argv YALNIZ ikiliden ibaret: betik argv'de taşınmıyor
                assert cagri.eleman_sayisi == 1, cagri
                assert cagri.text_var, cagri      # metin kipi korunur
                assert cagri.timeout_var, cagri   # zaman aşımı korunur


# ---------------------------------------------------------------------------
# 2. Canlı kanıt — gerçek koşucudan, iki tavanın da üstünde
# ---------------------------------------------------------------------------

def _buyuk_alan(hedef_bayt):
    """JSON gövdesi ``hedef_bayt``ı aşan, gerçek sayısal alan üretir.

    Ölü dolgu dizgisi değil sayı dizisi: node yükü GERÇEKTEN ayrıştırıp
    toplar, yani stdin yolunun büyük yükü taşıdığı hesapla doğrulanır.
    """
    alan = []
    govde = '[]'
    while len(govde.encode('utf-8')) <= hedef_bayt:
        taban = len(alan)
        adet = max(4096, int(len(alan) * 0.7))
        alan.extend((taban + i) * math.pi for i in range(adet))
        govde = json.dumps(alan)
    return alan, govde


@pytest.mark.skipif(NODE is None, reason='node bulunamadi')
class TestStdinCanliKanit:

    def test_iki_tavanin_ustundeki_betik_gercek_kosucudan_geciyor(self):
        """>1,2 MB betik ithal edilen GERÇEK ``_run`` ile koşar.

        Isırık: koşucu argv biçimine dönerse bu betik Linux'ta
        MAX_ARG_STRLEN'i (131072), macOS'ta ARG_MAX'ı (1048576) aşar ve çağrı
        ``OSError [Errno 7]`` ile KOŞMADAN ölür.
        """
        alan, govde = _buyuk_alan(CANLI_KANIT_BAYT)
        betik = ('var ALAN = %s;\n'
                 'var toplam = 0.0;\n'
                 'for (var i = 0; i < ALAN.length; i++) {\n'
                 '  toplam += ALAN[i];\n'
                 '}\n'
                 'process.stdout.write(JSON.stringify('
                 '{n: ALAN.length, toplam: toplam}));\n') % govde
        boyut = len(betik.encode('utf-8'))
        assert boyut > LINUX_MAX_ARG_STRLEN, boyut
        assert boyut > MACOS_ARG_MAX, boyut

        try:
            sonuc = CFD_ALAN_KOSUCU(betik)
        except OSError as hata:
            pytest.fail(
                'kosucu argv bicimine donmus olmali — %d baytlik betik '
                'execve tavanini asti: %r' % (boyut, hata))

        assert sonuc['n'] == len(alan)
        # Python'un sum()'ı da JS döngüsü de soldan sağa çift duyarlıklı
        # toplama yapar — aynı sırada aynı doubleler, aynı sonuç.
        assert sonuc['toplam'] == pytest.approx(sum(alan), rel=1e-12)

    def test_stdin_yolunda_require_calisiyor(self):
        """stdin ile verilen program CommonJS olarak koşar (require sağlam).

        argv'den stdin'e geçişin tek riski buydu: node stdin'i modül
        bağlamında koşmasaydı ``require`` kırılırdı.
        """
        betik = ("var path = require('path');\n"
                 'process.stdout.write(JSON.stringify({\n'
                 # basename yol ayracından bağımsızdır (Windows'ta da 'b.js')
                 "  taban: path.basename('/x/y/b.js'),\n"
                 "  modul: typeof module,\n"
                 "  gerektir: typeof require}));\n")
        sonuc = CFD_ALAN_KOSUCU(betik)
        assert sonuc == {'taban': 'b.js', 'modul': 'object',
                         'gerektir': 'function'}
