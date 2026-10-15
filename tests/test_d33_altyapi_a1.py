"""ÖH D33-KOLAY / altyapi a1 — bekçiler.

Kapsanan kalemler:

  * **OH-D32-05** — ``hrma/visualization/__init__`` eager ``_VIZ_EXPORTS``
    döngüsü GECİKMELİ çözüme çevrildi (OH-D31-06 ikizi, PEP 562 modül
    ``__getattr__``). Bekçiler paket yüzeyine dokunmanın motor zincirini
    ÇEKMEDİĞİNİ, iki yaprağın birbirini YÜKLEMEDİĞİNİ ve fail-closed
    vekil sözleşmesinin gecikmeli yolda da durduğunu kilitler.

  * **OH-UC-07** — ``hrma/app.py`` modül düzeyi ``trajectory_analyzer``
    ölü nesnesi. Nesnenin SİLİNMESİ bu dalgada ENGELLİ (kardeş dal
    ``bekci-cevirisi`` ``tests/test_d29_app_api_uc_a3.py``ye dokunuyor ve
    oradaki ``TestP7B221TekilAnalizor`` bekçisi nesneyi okuyor; o dosyaya
    dokunma yetkim yok). Silinene kadar KUSURUN BÜYÜMESİ kilitlenir:
    nesne ÜRÜN kodunda okunmaya başlarsa — yani ölü nesne yeniden CANLI
    bir paylaşılan durum kanalına dönerse — bu bekçi kırmızı yanar.

  * **OH-UC-13** (ÖH D33-2) — ``tests/test_release_notes_language.py``nin
    8 node bekçisi HEAD'de kırmızıydı. Ölçüm İKİ kusur buldu, ikisi de
    onarıldı ve dosyanın son bölümü ikisini birden kilitler: (a) sürücünün
    sahte DOM'u ``<script src=…>`` ögesini head'e alıp HİÇ çalıştırmıyordu
    (``a1/once_ohuc13.json``), (b) sürücü tarayıcıyı doğru taklit edince
    ürün kusuru göründü — ``update_check.js::sozlukHazir`` ``force``
    akışında kendi koyduğu etiketi görüp ERKEN DÖNÜYOR, pencereyi sözlük
    inmeden çizdiriyordu (Türkçe arayüzde başlık ``UPDATE AVAILABLE``;
    ``a1/ara_surucu_onarildi.json``).

Not (D27 dersi 10): bu dosyadaki bütün tanımlayıcı ve düğüm adları saf
ASCII'dir (``ASCII_DISI_DUGUM_TAVANI`` yastıksız). Docstring ve yorumlar
Türkçedir.
"""

import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]

#: Paket yüzeyinin BOYU — tek kaynak ``_VIZ_EXPORTS``tan türetilir.
BEKLENEN_AD_SAYISI = 18


def _cevre():
    e = dict(os.environ)
    e.update(PYTHONDONTWRITEBYTECODE='1', HRMA_HEADLESS='1',
             VECLIB_MAXIMUM_THREADS='3', OMP_NUM_THREADS='3',
             OPENBLAS_NUM_THREADS='3')
    return e


def _sonda(kod):
    """Kodu AYRI SÜREÇTE koşturur; son satırdaki JSON'u döndürür.

    Yalıtım süreç düzeyinde kurulur: ``sys.modules`` üzerinde oynayan ya
    da "kim yüklendi" sayan bir ölçüm, aynı süreçteki başka bekçilerin
    yüklediği modülleri sayardı (P8B4-22 dersi).
    """
    r = subprocess.run([sys.executable, '-c', kod], cwd=str(KOK),
                       capture_output=True, text=True, env=_cevre(),
                       timeout=600)
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout.strip().splitlines()[-1])


# ===========================================================================
# OH-D32-05 — paket yüzeyi GECİKMELİ çözülür
# ===========================================================================

_SAYIM = r'''
import sys, json
%s
mods = [m for m in sys.modules
        if (m == "hrma" or m.startswith("hrma.")) and sys.modules[m] is not None]
print(json.dumps({
    "hrma": sorted(mods),
    "engines": len([m for m in mods if m.startswith("hrma.engines")]),
    "analysis": len([m for m in mods if m.startswith("hrma.analysis")]),
    "ucuncu_parti": sorted({m.split(".")[0] for m in sys.modules
                            if m.split(".")[0] in
                            ("numpy", "scipy", "plotly", "pandas",
                             "matplotlib", "flask")}),
    "viz_alt": sorted(m for m in mods if m.startswith("hrma.visualization.")),
}))
'''


class TestOHD3205GecikmeliYuzey:
    """ÖLÇÜLDÜ (``a1/once.json``, taban ``56f88e70``): eager döngü yüzünden
    ``import hrma.visualization`` 42 hrma modülü, 8 ``hrma.engines.*``,
    12 ``hrma.analysis.*`` ve numpy+scipy+plotly yüklüyordu (0,61 s).
    Gecikmeli çözümle 2 modül, 0 engines, 0 analysis, üçüncü parti YOK.
    """

    def test_paket_ithali_ENGINES_zincirini_CEKMEZ(self):
        d = _sonda(_SAYIM % 'import hrma.visualization')
        assert d['engines'] == 0, d['hrma']
        assert d['analysis'] == 0, d['hrma']
        assert d['ucuncu_parti'] == [], d['ucuncu_parti']
        # Eager döngü geri gelirse iki yaprak da burada yüklü olur.
        assert d['viz_alt'] == [], d['viz_alt']

    def test_visualization_yapragi_advanced_results_YUKLEMEZ(self):
        """İki yaprak birbirine BAĞLI DEĞİL.

        Tabanda ``import hrma.visualization.visualization`` ``__init__``in
        eager döngüsü yüzünden ``advanced_results``ı da yüklüyordu.
        """
        d = _sonda(_SAYIM % 'import hrma.visualization.visualization')
        assert d['viz_alt'] == ['hrma.visualization.visualization'], d['viz_alt']

    def test_yuzey_18_ad_TEK_KAYNAKTAN_turetilir(self):
        import hrma.visualization as P
        assert len(P.__all__) == BEKLENEN_AD_SAYISI
        turetilen = [a for adlar in P._VIZ_EXPORTS.values() for a in adlar]
        assert sorted(P.__all__) == sorted(turetilen)
        # ad -> modül tablosu da AYNI kaynaktan; elle yazılmış ikinci
        # liste yok (tek kaynak doktrini).
        assert sorted(P._AD_MODUL) == sorted(turetilen)
        for ad, modul in P._AD_MODUL.items():
            assert ad in P._VIZ_EXPORTS[modul]

    def test_all_ELLE_YAZILMIS_liste_DEGIL(self):
        """``__all__`` sabit bir ad listesi olarak yeniden yazılamaz."""
        kaynak = (KOK / 'hrma' / 'visualization' / '__init__.py').read_text(
            encoding='utf-8')
        for dugum in ast.walk(ast.parse(kaynak)):
            if (isinstance(dugum, ast.Assign)
                    and any(isinstance(h, ast.Name) and h.id == '__all__'
                            for h in dugum.targets)):
                assert isinstance(dugum.value, ast.ListComp), (
                    '__all__ ELLE yazılmış görünüyor — tek kaynak '
                    '_VIZ_EXPORTS olmalı')
                return
        pytest.fail('__all__ ataması bulunamadi')

    def test_18_ad_CAGRILABILIR_kalir(self):
        import hrma.visualization as P
        for ad in P.__all__:
            f = getattr(P, ad)
            assert callable(f), ad
            assert not hasattr(f, 'unavailable_reason'), ad

    def test_bilinmeyen_ad_AttributeError_verir(self):
        """``from paket import alt_modul`` yedek yolu ÇALIŞMALI.

        ``__getattr__`` bilinmeyen ad için ``ImportError`` fırlatsaydı
        Python'un alt modül içe aktarma yedeği kırılırdı.
        """
        import hrma.visualization as P
        with pytest.raises(AttributeError):
            P.boyle_bir_ad_yok
        from hrma.visualization import visualization as V
        assert V.__name__ == 'hrma.visualization.visualization'

    def test_GECIKMELI_yolda_da_fail_closed_VEKIL(self):
        """Yaprak düşerse ad SESSİZ kaybolmaz: çağrılınca kök sebebi söyler.

        Gecikmeli çözümde de geçerli olduğunu ölçer (vekil ``__getattr__``
        yolundan üretilir, modül düzeyi döngüden değil).
        """
        d = _sonda(r'''
import sys, json, warnings
sys.modules['hrma.visualization.advanced_results'] = None
import hrma.visualization as P
with warnings.catch_warnings(record=True) as y:
    warnings.simplefilter('always')
    saglam = P.create_motor_plot          # oteki yaprak: GERCEK
    kayip = P.create_cea_style_results    # dusen yaprak: VEKIL
    uyari = [str(w.message) for w in y]
try:
    kayip()
    sebep = 'VEKIL_SESSIZ'
except ImportError as e:
    sebep = str(e)
print(json.dumps({
    'saglam_gercek': not hasattr(saglam, 'unavailable_reason'),
    'kayip_vekil': hasattr(kayip, 'unavailable_reason'),
    'sebep': sebep, 'uyari': uyari,
    'hatalar': sorted(P.VISUALIZATION_IMPORT_ERRORS),
}))
''')
        assert d['saglam_gercek'], 'saglam yaprak vekile dondu'
        assert d['kayip_vekil'], 'dusen yaprak icin vekil birakilmadi'
        assert 'advanced_results' in d['sebep'], d['sebep']
        assert d['sebep'] != 'VEKIL_SESSIZ'
        # uyarı ADIYLA söyler (gecikmeli yolda, ilk çözüm anında)
        birlesik = ' '.join(d['uyari'])
        assert 'advanced_results' in birlesik, birlesik
        assert 'create_cea_style_results' in birlesik, birlesik
        assert 'hrma.visualization.advanced_results' in d['hatalar']

    def test_dusen_yaprak_ICIN_uyari_BIR_KEZ(self):
        """Ad başına tekrar tekrar uyarı basılmaz (``_DENENEN``)."""
        d = _sonda(r'''
import sys, json, warnings
sys.modules['hrma.visualization.advanced_results'] = None
import hrma.visualization as P
with warnings.catch_warnings(record=True) as y:
    warnings.simplefilter('always')
    for ad in ('create_cea_style_results', 'create_mass_fractions_plot',
               'create_altitude_performance_plot', 'create_thrust_altitude_plot'):
        getattr(P, ad)
    print(json.dumps({'uyari_sayisi': len(y)}))
''')
        assert d['uyari_sayisi'] == 1, d


# ===========================================================================
# OH-UC-07 — modül düzeyi ``trajectory_analyzer`` ÜRÜNDE OKUNMAZ
# ===========================================================================

def _trajectory_analyzer_okumalari():
    """AST: ``hrma/app.py``de adın GLOBAL okunduğu yerler.

    Yerel olarak yeniden bağlanan (gölgeleyen) işlevler GLOBAL okuma
    SAYILMAZ — ``/calculate`` ve ``/api/trajectory-analysis`` adı kendi
    gövdelerinde ``TrajectoryAnalyzer()`` ile yeniden bağlıyor.
    """
    kaynak = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')
    agac = ast.parse(kaynak)
    atama, global_okuma = [], []

    class Gezgin(ast.NodeVisitor):
        def __init__(self):
            self.yigin = []

        def visit_FunctionDef(self, n):
            yerel = any(isinstance(d, ast.Name)
                        and d.id == 'trajectory_analyzer'
                        and isinstance(d.ctx, ast.Store)
                        for d in ast.walk(n))
            genel = any(isinstance(d, ast.Global)
                        and 'trajectory_analyzer' in d.names
                        for d in ast.walk(n))
            self.yigin.append((n.name, yerel, genel))
            self.generic_visit(n)
            self.yigin.pop()
        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Name(self, n):
            if n.id == 'trajectory_analyzer':
                if not self.yigin:
                    (atama if isinstance(n.ctx, ast.Store)
                     else global_okuma).append(('<modul>', n.lineno))
                else:
                    ad, yerel, genel = self.yigin[-1]
                    if isinstance(n.ctx, ast.Load) and (genel or not yerel):
                        global_okuma.append((ad, n.lineno))
            self.generic_visit(n)

    Gezgin().visit(agac)
    return atama, global_okuma


class TestOHUC07OluNesneCANLANMIYOR:
    """ÖLÇÜLDÜ (``a1/once.json`` -> ``OH-UC-07_olu_nesne``, taban
    ``56f88e70``): ``hrma/app.py`` modül düzeyinde ``trajectory_analyzer``
    bir kez kuruluyor (satır 2752) ama ÜRÜNDE HİÇ OKUNMUYOR — GLOBAL okuma
    0, app.py dışında ürün başvurusu 0; adı kullanan iki uç onu YEREL
    olarak yeniden bağlıyor.

    Nesnenin kendisi a1'de SİLİNEMEDİ (kardeş dal kilidi; bkz. modül
    docstring'i ve ``a1/rapor.md``); kilit çözülünce ana model fix-36b ile
    (16 Eyl 2026) SİLDİ — bu bekçi artık atamanın YOKLUĞUNU da kilitler. Bu bekçi kusurun BÜYÜMESİNİ kilitler:
    ``TrajectoryAnalyzer`` DURUM TAŞIR (araç ve kurtarma parametreleri) ve
    süreç-geneli paylaşılan yazılabilir durum, iki isteğin birbirinin
    aracını değiştirmesi demektir — ölçülmüş bir arızadır (ÖH D23 /
    P4B3-28: birebir aynı istek %53 farklı iniş hızı döndürüyordu).
    Modül düzeyindeki nesne ÜRÜNDE okunmaya başlarsa o kanal yeniden
    açılır; bekçi o anda kırmızı yanar.
    """

    def test_modul_duzeyi_nesne_URUNDE_OKUNMAZ(self):
        atama, global_okuma = _trajectory_analyzer_okumalari()
        # fix-36b (16 Eyl 2026, ana model): nesne KALDIRILDI — atama artik YOK olmali.
        assert not atama, (
            'modul duzeyi paylasilan trajectory_analyzer GERI GELDI (OH-UC-07 '
            'fix-36b ile kaldirildi): %r' % (atama,))
        assert global_okuma == [], (
            'modul duzeyindeki paylasilan trajectory_analyzer URUN yolunda '
            'OKUNUYOR (istekler arasi durum sizintisi kanali yeniden acildi); '
            'her istek kendi TrajectoryAnalyzer() nesnesini kurmali: '
            + repr(global_okuma))

    def test_app_DISINDA_urun_basvurusu_YOK(self):
        bulunan = []
        for kok, dizinler, dosyalar in os.walk(KOK / 'hrma'):
            dizinler[:] = [d for d in dizinler if d != '__pycache__']
            for d in dosyalar:
                if not d.endswith('.py'):
                    continue
                tam = pathlib.Path(kok) / d
                if tam.relative_to(KOK).as_posix() == 'hrma/app.py':
                    continue
                if 'trajectory_analyzer' in tam.read_text(
                        encoding='utf-8', errors='replace'):
                    bulunan.append(tam.relative_to(KOK).as_posix())
        assert bulunan == [], (
            'app.py disinda paylasilan analizore basvuru: %r' % bulunan)


# ===========================================================================
# ÖH D33-2 · OH-UC-13 — guncelleme penceresi node bekcileri
# ===========================================================================
TESTS_DIR = pathlib.Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import test_release_notes_language as RNL   # noqa: E402  (surucu + gercek notlar)

REPO_ROOT = KOK
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


# ---------------------------------------------------------------------------
# 1. Sürücü sözleşmesi — sahte DOM tarayıcı gibi davranıyor mu?
# ---------------------------------------------------------------------------
#: Sürücünün DOM bölümünü AYNI betik içinde ölçer (sürücünün `let` bağları
#: görünsün diye). Onarım geri alınırsa `typeof` kapıları sessizce karşılar
#: ve ölçüm "yüklemiyor" der — yani bu sonda iki sürümü de ölçebilir.
SONDA_JS = r"""
try { if (typeof STATIC_DIR !== 'undefined') { STATIC_DIR = __STATIK__; } } catch (e) {}
try {
    if (typeof VM_CTX !== 'undefined') {
        VM_CTX = require('vm').createContext({
            console: { log: function () {}, warn: function () {}, error: function () {} },
            setTimeout: setTimeout, clearTimeout: clearTimeout,
            WeakMap: WeakMap, Promise: Promise
        });
    }
} catch (e) {}

var __head = new El('head');
var __s = new El('script');
__s.src = '/static/js/i18n_common.js';
var __yuklendi = false, __hata = false;
__s.onload = function () { __yuklendi = true; };
__s.onerror = function () { __hata = true; };
__head.appendChild(__s);
var __secici = __s.matches('script[src*="i18n_common.js"]');
var __qs = __head.querySelectorAll('script[src*="i18n_common.js"]').length;
setTimeout(function () {
    var calisan = 0;
    try { if (typeof YUKLENEN !== 'undefined') calisan = YUKLENEN.length; } catch (e) {}
    console.log(JSON.stringify({
        onload_atesledi: __yuklendi,
        onerror_atesledi: __hata,
        betik_calisti: calisan > 0,
        secici_eslesti: __secici,
        querySelector_bulunan: __qs
    }));
}, 400);
"""


def _dom_sondasi():
    """Sürücünün sahte DOM'unu DEĞİŞTİRMEDEN çalıştırıp sözleşmesini ölçer."""
    import json
    harness = RNL.HARNESS_JS
    dom = harness[:harness.index("const body = new El('body');")]
    dom = re.sub(r'^// --- ARGV BLOGU BASLANGIC.*?^// --- ARGV BLOGU BITIS ---$',
                 '', dom, flags=re.S | re.M)
    dom = re.sub(r'^const \[updateJs.*$', '', dom, flags=re.M)
    dom = re.sub(r'^const info = JSON.*$', '', dom, flags=re.M)
    kod = dom + SONDA_JS.replace('__STATIK__', json.dumps(str(STATIC_JS)))
    with tempfile.TemporaryDirectory() as tmp:
        yol = pathlib.Path(tmp) / 'sonda.js'
        yol.write_text(kod, encoding='utf-8')
        p = subprocess.run([NODE, str(yol)], capture_output=True, text=True,
                           timeout=180)
    assert p.returncode == 0, 'sonda çöktü:\n%s' % p.stderr[-800:]
    return json.loads(p.stdout.strip().splitlines()[-1])


@node_gerekli
def test_surucu_enjekte_edilen_betigi_gercekten_calistirir():
    """DOM'a giren `<script src>` tarayıcıda ÇALIŞIR; sürücü de çalıştırmalı.

    Bu sözleşme olmadan `sozlukHazir` gibi "betiği yükle, sonra çiz"
    deseninin HİÇBİRİ sınanamaz: geri çağrım ateşlenmez, pencere açılmaz
    ve bekçi ürünü değil kendi körlüğünü ölçer.
    """
    r = _dom_sondasi()
    assert r['betik_calisti'], (
        'sahte DOM enjekte edilen betiği çalıştırmıyor: talep üzerine '
        'yükleme deseni sınanamaz (once_ohuc13.json ile aynı kusur)')
    assert r['onload_atesledi'], 'betik yüklendiği hâlde onload ateşlenmedi'
    assert not r['onerror_atesledi'], 'var olan betik için onerror ateşlendi'


@node_gerekli
def test_surucu_attribute_contains_secicisini_taniyor():
    """`script[src*="…"]` ürünün erken dönüş dalının TEK kapısıdır.

    Sürücü bu seçiciyi tanımazsa o dal hiçbir koşumda ölçülemez
    (once_ohuc13.json: secici_attr_contains_eslesti=false).
    """
    r = _dom_sondasi()
    assert r['secici_eslesti'], 'matches() [attr*="değer"] biçimini tanımıyor'
    assert r['querySelector_bulunan'] == 1, (
        'querySelectorAll seçiciyi tanımadı: bulunan=%s'
        % r['querySelector_bulunan'])


# ---------------------------------------------------------------------------
# 2. Ürün sözleşmesi — pencere arayüz diliyle AYNI dilde açılıyor mu?
# ---------------------------------------------------------------------------
BASLIK = {'tr': 'GÜNCELLEME MEVCUT', 'en': 'UPDATE AVAILABLE'}


@node_gerekli
@pytest.mark.parametrize('sozluk', RNL.SOZLUK_KIPLERI)
@pytest.mark.parametrize('dil', ('tr', 'en'))
def test_pencere_basligi_arayuz_diliyle_ayni(dil, sozluk):
    """Her iki sayfa modelinde de başlık arayüz dilinde basılmalı.

    `lazy`   = launch_site/liquid/solid (ortak sözlük sayfada yok),
    `onceden`= index/formulas (sözlük sayfayla gelir).
    Kusurlu sürümde `lazy` + `tr` çifti İngilizce başlık veriyordu.
    """
    sonuc = RNL._pencereyi_ac(RNL._bilgi(notes=RNL.NOTLAR), dil, sozluk=sozluk)
    assert sonuc['lang'] == dil
    assert BASLIK[dil] in sonuc['baslik'], (
        '%s arayüzünde %s kipinde başlık %r — pencere sözlüğü beklemeden '
        'çizilmiş' % (dil, sozluk, sonuc['baslik']))


@node_gerekli
def test_sozluk_pencere_cizilmeden_once_ve_TEK_kez_iniyor():
    """D30/OH-D21-06 kazancı korunur: sözlük ancak metin basılacakken iner.

    Ama bir kez iner: `force` akışında işlev iki kez çağrılır ve ikinci
    çağrı erken dönmek yerine inen isteğin KUYRUĞUNA girer.
    """
    sonuc = RNL._pencereyi_ac(RNL._bilgi(notes=RNL.NOTLAR), 'tr', sozluk='lazy')
    inenler = [y for y in sonuc['yuklenen_betikler'] if 'i18n_common.js' in y]
    assert len(inenler) == 1, (
        'ortak sözlük %d kez indi (force akışı iki kez çağırıyor); '
        'çift indirme kapısı çalışmıyor: %s'
        % (len(inenler), sonuc['yuklenen_betikler']))


def test_sozluk_sayfa_acilisinda_inmiyor():
    """OH-D21-06 geri alınmadı: 505 KB sözlük açılışta inmez (üç sayfa)."""
    for sayfa in ('launch_site.html', 'liquid.html', 'solid.html'):
        s = (REPO_ROOT / 'hrma' / 'templates' / sayfa).read_text(encoding='utf-8')
        s = re.sub(r'<!--.*?-->', '', s, flags=re.S)
        assert '<script src="/static/js/i18n_common.js"' not in s, (
            '%s sözlüğü yine açılışta indiriyor' % sayfa)


def test_hazir_olma_olcutu_etikete_degil_sozluge_soruluyor():
    """Kusurun kökü: etiketin VARLIĞI sözlüğün HAZIR olduğu değildi.

    Davranış bekçisi yukarıda; bu, kökün geri gelmesini adıyla yakalar.
    """
    g = (STATIC_JS / 'update_check.js').read_text(encoding='utf-8')
    m = re.search(r'function sozlukHazir\(cb\) \{(.*?)\n    \}', g, re.S)
    assert m, 'sozlukHazir bulunamadı'
    govde = m.group(1)
    assert 'sozlukYuklu()' in govde, (
        'hazır olma ölçütü sözlüğe sorulmuyor (I18N.has); etiket sayımına '
        'dönülmüş — force akışında pencere yine İngilizce çizilir')
    assert 'SOZLUK_KUYRUK' in govde, (
        'ikinci çağrı kuyruğa girmiyor: inen istek varken erken dönülüyor')
