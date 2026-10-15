# -*- coding: utf-8 -*-
"""ÖH Dalga-32 · altyapi a1 bekçileri.

Kalemler:
  * OH-D31-06 — ``hrma/utils/__init__`` yüzeyi GECİKMELİ çözülür; yaprak
    modülü isteyen tüketici motor zincirine sokulmaz.
  * OH-D31-19 — ``test_no_process_wide_warning_suppression`` sıraya bağlı
    kırmızıydı; ürün iddiası artık TEMİZ bir alt süreçte ölçülür ve
    test tarafındaki süreç-geneli susturma envanteri ADIYLA kilitlenir.
  * OH-D21-07 — kılavuz yarısı (ekran görüntüsü + PDF ikizi) kılavuz
    dalgasına devredildi; devir dosyası ÖLÇÜLMÜŞ engelleri taşır.

Ölçüm kanıtları: ``docs/scofield/raw/OH/D32/altyapi/a1/``.
"""
import ast
import json
import os
import subprocess
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D32', 'altyapi', 'a1')


def _oku(göreli):
    with open(os.path.join(KOK, göreli), encoding='utf-8') as f:
        return f.read()


def _alt_surec(kod, zaman=300):
    """Kodu TEMİZ bir yorumlayıcıda koşturur, son satırdaki JSON'u döner."""
    ortam = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', HRMA_HEADLESS='1',
                 VECLIB_MAXIMUM_THREADS='3', OMP_NUM_THREADS='3',
                 OPENBLAS_NUM_THREADS='3')
    p = subprocess.run([sys.executable, '-c', kod], cwd=KOK, env=ortam,
                       capture_output=True, text=True, timeout=zaman)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout.strip().splitlines()[-1])


# ===========================================================================
# OH-D31-06 — paket yüzeyi GECİKMELİ çözülür
# ===========================================================================

class TestOHD3106GecikmeliPaketYuzeyi:
    """Yaprak modülü isteyen, motor zincirinin bedelini ÖDEMEZ.

    ÖLÇÜLDÜ (``once_import.json`` taban ``dd1dcddc`` -> ``sonra_import.json``):

        import hrma.utils.input_guard
          önce : 41 hrma modülü · 8 engines · 12 analysis · numpy+scipy+plotly
          sonra:  3 hrma modülü · 0 engines ·  0 analysis · üçüncü parti yok

    Bu yalnız hız değil YAPI kalemidir: eski hâlde ``hrma.engines.__init__``
    -> ``heat_transfer_analysis`` -> ``hrma.utils`` -> ``injector_design`` ->
    ``hrma.engines.*`` halkası motor paketini yarım bırakıyordu (OHD2906).
    """

    def test_yaprak_modul_motor_zincirini_tetiklemiyor(self):
        olcum = _alt_surec(
            "import json, sys\n"
            "import hrma.utils.input_guard  # yaprak: gövdesinde hrma yok\n"
            "m = [x for x in sys.modules if x == 'hrma' or x.startswith('hrma.')]\n"
            "print(json.dumps({\n"
            "  'engines': sorted(x for x in m if x.startswith('hrma.engines')),\n"
            "  'analysis': sorted(x for x in m if x.startswith('hrma.analysis')),\n"
            "  'hrma_sayisi': len(m),\n"
            "  'ucuncu_parti': sorted({x.split('.')[0] for x in sys.modules\n"
            "                          if x.split('.')[0] in ('numpy','scipy','plotly')}),\n"
            "}))\n")
        assert olcum['engines'] == [], \
            f"yaprak modül motor zincirini tetikledi: {olcum['engines']}"
        assert olcum['analysis'] == [], \
            f"yaprak modül analiz zincirini tetikledi: {olcum['analysis']}"
        assert olcum['ucuncu_parti'] == [], \
            f"yaprak modül üçüncü parti yığını çekti: {olcum['ucuncu_parti']}"
        # hrma, hrma.utils, hrma.utils.input_guard — üçten fazlası zincirdir.
        assert olcum['hrma_sayisi'] <= 3, olcum['hrma_sayisi']

    def test_bos_paket_ice_aktarimi_da_zincir_cekmiyor(self):
        """``import hrma.utils`` tek başına hiçbir adı çözmemeli."""
        olcum = _alt_surec(
            "import json, sys\n"
            "import hrma.utils\n"
            "print(json.dumps({\n"
            "  'zincir': sorted(x for x in sys.modules\n"
            "                   if x.startswith(('hrma.engines','hrma.analysis'))),\n"
            "  'hatalar': sorted(hrma.utils.IMPORT_ERRORS),\n"
            "}))\n")
        assert olcum['zincir'] == [], olcum['zincir']
        assert olcum['hatalar'] == []

    def test_kaynak_modul_duzeyinde_cozmuyor(self):
        """YAPI bekçisi: ``_load_exports`` modül gövdesinde ÇAĞRILMAMALI.

        Ters-mutasyon tam olarak bunu geri koyar (``mutasyon_ohd3106.json``):
        dosya sonuna ``_load_exports()`` satırı eklenince bu iddia ve
        yukarıdaki iki ölçüm birlikte kırmızıya döner.
        """
        agac = ast.parse(_oku('hrma/utils/__init__.py'))
        modul_duzeyi = []
        for d in agac.body:
            if isinstance(d, ast.Expr) and isinstance(d.value, ast.Call):
                f = d.value.func
                ad = getattr(f, 'id', getattr(f, 'attr', ''))
                if ad == '_load_exports':
                    modul_duzeyi.append(d.lineno)
        assert modul_duzeyi == [], \
            f'eager çözüm modül düzeyine geri kondu: satır {modul_duzeyi}'

    def test_yuzey_daralmadi(self):
        """v2.6.26 yüzeyi AYNEN erişilebilir; ölü yol yüzeyde değil."""
        import hrma.utils as hu
        for ad in ('validation', 'calculations', 'graph_fixes', 'fuel_mixer',
                   'export_fixes', 'InjectorDesign'):
            assert hasattr(hu, ad), f'dışa açılan ad kayboldu: {ad}'
            assert ad in dir(hu), f'__dir__ adı göstermiyor: {ad}'
        for ad in ('of_optimizer', 'OptimumOFRatioFinder'):
            assert not hasattr(hu, ad), f'ölü yol yüzeye geri geldi: {ad}'

    def test_fail_closed_korundu_ve_moduller_yalitik(self):
        """Yüklenemeyen ad SESSİZ kalmaz; arızası kardeşini düşürmez.

        ``plotly`` engellenir (``common_fixes`` onu içe aktarır):
          * ``import hrma.utils`` yine BAŞARILI (paket ölmez),
          * ``hu.validation`` kök sebeple ``ImportError`` verir (None DÖNMEZ),
          * ``IMPORT_ERRORS`` yalnız o modülün 5 adını taşır — kardeş
            modülün adı (``InjectorDesign``) düşmez,
          * arıza ``RuntimeWarning`` ile duyurulur.
        """
        olcum = _alt_surec(
            "import json, sys, warnings\n"
            "class _Engel:\n"
            "    def find_module(self, ad, yol=None):\n"
            "        return self if ad == 'plotly' or ad.startswith('plotly.') else None\n"
            "    def find_spec(self, ad, yol=None, hedef=None):\n"
            "        if ad == 'plotly' or ad.startswith('plotly.'):\n"
            "            raise ImportError('plotly BILEREK engellendi (bekci)')\n"
            "        return None\n"
            "sys.meta_path.insert(0, _Engel())\n"
            "import hrma.utils as hu\n"
            "sonuc = {'paket_yuklendi': True}\n"
            "with warnings.catch_warnings(record=True) as w:\n"
            "    warnings.simplefilter('always')\n"
            "    try:\n"
            "        hu.validation\n"
            "        sonuc['davranis'] = 'SESSIZ GECTI'\n"
            "    except ImportError as e:\n"
            "        sonuc['davranis'] = 'ImportError'\n"
            "        sonuc['kok_sebep'] = str(e.__cause__)[:200]\n"
            "    sonuc['uyari'] = [str(x.message)[:120] for x in w\n"
            "                      if issubclass(x.category, RuntimeWarning)]\n"
            "sonuc['hatalar'] = sorted(hu.IMPORT_ERRORS)\n"
            "print(json.dumps(sonuc))\n")
        assert olcum['paket_yuklendi'] is True
        assert olcum['davranis'] == 'ImportError', olcum['davranis']
        assert 'plotly' in olcum.get('kok_sebep', ''), olcum.get('kok_sebep')
        assert olcum['uyari'], 'arıza sessiz kaldı: RuntimeWarning basılmadı'
        assert olcum['hatalar'] == ['calculations', 'export_fixes', 'fuel_mixer',
                                    'graph_fixes', 'validation'], olcum['hatalar']

    def test_bekciler_yuzeyi_cozduruyor(self):
        """Gecikmeli çözüm, yüzey bütünlüğünü ölçen bekçileri KÖRLEŞTİRMEZ.

        ``IMPORT_ERRORS == {}`` iddiası, hiçbir ad istenmemişse ÖLÇMEDEN
        geçer. D32'de bu üç bekçiye ``_load_exports()`` çağrısı eklendi;
        bu iddia o çağrının yerinde durduğunu ŞART koşar (D31 dersi 23).
        """
        beklenen = {
            'tests/test_z5s_utils_altyapi.py': 1,
            'tests/test_d30_app_api_dogrulama_a1.py': 2,
            'tests/test_d31_app_api_dogrulama_a1.py': 1,
        }
        for yol, sayi in beklenen.items():
            # AST ile GERÇEK çağrı sayılır: yorumdaki ``_load_exports()``
            # metni bekçiyi kandırmasın (ölçüldü: metin sayımı mutasyonda
            # kırmızıya dönmüyordu — mutasyon.json 'bekci_korlesmesi').
            metin = _oku(yol)
            cagri = 0
            for d in ast.walk(ast.parse(metin)):
                if isinstance(d, ast.Call):
                    f = d.func
                    if getattr(f, 'attr', getattr(f, 'id', '')) == '_load_exports':
                        cagri += 1
            # Alt süreç betikleri DİZGİdir: onları ayrıca say.
            cagri += metin.count('hu._load_exports(); ')
            assert cagri >= sayi, \
                f'{yol}: yüzeyi çözdüren çağrı kaldırılmış (bekçi körleşir)'


# ===========================================================================
# OH-D31-19 — süreç geneli warnings susturması: ürün mü, test mi?
# ===========================================================================

class TestOHD3119WarningsSusturmasi:
    """Sıraya bağlı kırmızının kökü ÖLÇÜLDÜ.

    ÖLÇÜLDÜ (``once_warn.json``, taban ``dd1dcddc``):
      * ÜRÜN TEMİZ: temiz yorumlayıcıda ``import hrma.app`` sonrası
        catch-all filtre sayısı **0** (17 filtrenin hiçbiri değil).
      * TEST TARAFI KİRLİ: **35** test modülü, modül DÜZEYİNDE
        ``warnings.filterwarnings('ignore')`` çağırıyor. Bu satırlar
        toplama (collection) anında koşar; pytest'in ``catch_warnings``
        bağlamı onları çoğu kümede geri alır — bu yüzden kırmızı
        SIRAYA BAĞLIDIR (D31: 4 dosyalık kümede yeşil, 33'lükte kırmızı).

    Onarım: iddianın ölçtüğü şey ÜRÜN olduğuna göre ürün TEMİZ bir alt
    süreçte ölçülür — sıra artık hükmü değiştiremez. Test tarafındaki
    susturma ayrı bir hijyen borcudur ve aşağıda ADIYLA kilitlenir.
    """

    #: ÖLÇÜLDÜ (``once_warn.json`` -> ``B_modul_duzeyi_catchall``). Bu sayı
    #: yalnız KÜÇÜLEBİLİR: envanter gevşetilemez (ÖK-22).
    TAVAN = 35

    def test_urun_temiz_yorumlayicida_susturma_yapmiyor(self):
        olcum = _alt_surec(
            "import json, warnings\n"
            "import hrma.app  # noqa: F401\n"
            "ca = [str(f[:4]) for f in warnings.filters\n"
            "      if f[0] == 'ignore' and f[1] is None and f[2] is Warning\n"
            "      and f[3] is None]\n"
            "print(json.dumps({'catch_all': ca, 'toplam': len(warnings.filters)}))\n",
            zaman=600)
        assert olcum['catch_all'] == [], (
            'bir ÜRÜN modülü süreç geneli filterwarnings("ignore") çağırıyor: '
            f"{olcum['catch_all']}")

    def test_kapi_alt_surecte_olcuyor(self):
        """Kapı iddiası artık süreç içi filtre listesine BAKMAZ.

        Süreç içi liste, o ana kadar koşmuş her testin mirasını taşır;
        ürün hakkında hüküm veremez. Yapı bekçisi: kapı alt süreç ölçümüne
        çevrildi ve öyle kalmalı.
        """
        metin = _oku('tests/test_v262_release_gate.py')
        kesit = metin[metin.index('def test_no_process_wide_warning_suppression'):]
        kesit = kesit[:kesit.index('\n    def ')]
        assert 'subprocess' in kesit, 'kapı süreç içi ölçüme geri döndü'
        assert 'OH-D31-19' in kesit, 'kalem künyesi düştü'

    def test_test_tarafi_susturma_envanteri_buyumuyor(self):
        """35 test modülü toplama anında süreç-geneli filtre kuruyor.

        Sayı YÜKSELTİLEMEZ. Yeni bir test dosyası aynı deseni getirirse bu
        bekçi kırmızıya döner; borcun sahipleri rapor.md'deki devir
        satırındadır (dosyalar kulvar kulvar dağılmıştır).
        """
        suclular = self._suclular()
        assert len(suclular) <= self.TAVAN, (
            'süreç geneli warnings susturması YAYILDI: '
            f'{len(suclular)} > {self.TAVAN}; yeni gelenler: '
            f'{sorted(set(suclular) - set(self._envanter()))}')

    def test_envanter_dosyayla_adiyla_eslesiyor(self):
        """Envanter ADIYLA kayıtlı; 'sayı tuttu' yetmez."""
        kayitli = set(self._envanter())
        olculen = set(self._suclular())
        assert olculen <= kayitli, (
            f'envantere yazılmamış yeni suçlu: {sorted(olculen - kayitli)}')

    # --- yardımcılar -----------------------------------------------------
    @staticmethod
    def _envanter():
        yol = os.path.join(KANIT, 'once_warn.json')
        return json.load(open(kanit_gerekli(yol), encoding='utf-8'))[
            'B_modul_duzeyi_catchall']['dosyalar'].keys()

    @staticmethod
    def _suclular():
        """Modül GÖVDESİNDE argümansız ``filterwarnings('ignore')`` çağıranlar."""
        bulunan = []
        tdir = os.path.join(KOK, 'tests')
        for ad in sorted(os.listdir(tdir)):
            if not ad.endswith('.py'):
                continue
            try:
                agac = ast.parse(open(os.path.join(tdir, ad), encoding='utf-8').read())
            except SyntaxError:
                continue
            for d in agac.body:                      # YALNIZ en üst düzey
                if not (isinstance(d, ast.Expr) and isinstance(d.value, ast.Call)):
                    continue
                c = d.value
                if not isinstance(c.func, ast.Attribute):
                    continue
                if c.func.attr not in ('filterwarnings', 'simplefilter'):
                    continue
                if c.keywords or len(c.args) != 1:
                    continue
                a0 = c.args[0]
                if isinstance(a0, ast.Constant) and a0.value == 'ignore':
                    bulunan.append('tests/' + ad)
                    break
        return bulunan


# ===========================================================================
# OH-D21-07 — kılavuz yarısı kılavuz dalgasına devredildi
# ===========================================================================

class TestOHD2107KilavuzDevri:
    """Devir SÜSLEME değil, ÖLÇÜLMÜŞ engel listesidir.

    D31 kalemin üç yarısını ayırmıştı: tur fixture'ı ÇÜRÜTÜLDÜ (0 eşleşme),
    şablon yarısı D24'te kapandı, rozet beyanı changelog + kılavuza yazıldı.
    Kalan yarı EKRAN GÖRÜNTÜSÜ tazelemesidir ve Berke'nin 27 Ağustos emriyle
    kılavuz dalgasına aittir. D32'de o engel ÖLÇÜLDÜ ve dosyaya bağlandı.
    """

    def test_devir_dosyasi_engelleri_olcumle_tasiyor(self):
        veri = json.load(open(kanit_gerekli(os.path.join(KANIT, 'kilavuz_devri.json')),
                              encoding='utf-8'))
        assert veri['kalem'] == 'OH-D21-07'
        engeller = veri['engeller']
        assert len(engeller) >= 3, engeller
        for e in engeller:
            assert e['ad'] and e['olcum'], e
        # TARİHÎ ÖLÇÜM (dd1dcddc, D32): devir dosyası o günün durumunu
        # dondurur — ikizler ayrışıktı ve derleme yolu yoktu. Dosya KANITTIR,
        # bugünkü gerçek değildir; bugünkü gerçeği yukarıdaki
        # test_kilavuz_borcu_ODENDI_im_sokuldu ölçer (ikizler md5 eşit,
        # tools/kilavuz_derle.sh var). Bu yüzden burada donmuş kaydın
        # BİÇİMİ sınanır, iddiası değil.
        for ad, ikiz in veri['pdf_ikizleri'].items():
            assert isinstance(ikiz['ayni_mi'], bool), ad
            assert ikiz['static']['md5'] and ikiz['user_guide']['md5'], ad
        assert '2.6.27' in veri['tex_kaynak'][
            'HRMA-Kullanma-Kilavuzu-TR.tex']['surum_dizgileri']
        assert isinstance(veri['derleme_betigi']['sayi'], int)
        # Bugünkü gerçek: derleme yolu ARTIK VAR (kılavuz dalgası).
        assert os.path.exists(os.path.join(KOK, 'tools', 'kilavuz_derle.sh')), (
            'kılavuz derleme betiği yok: devir dosyasının engeli kapanmadı')

    def test_kilavuz_borcu_ODENDI_im_sokuldu(self):
        """Borç ÖDENDİ (kılavuz dalgası, 16 Eylül 2026); im sökülmüş olmalı.

        D32'de bu düğüm iminin DURDUĞUNU sınıyordu ("sessiz düşmesin").
        Borç ödenince o iddia kendisi kusuru koruyan bir bekçiye dönüştü:
        kılavuzlar tek kaynaktan üretilip ikizler eşitlendiği hâlde kırmızı
        veriyordu. Yön ÇEVRİLDİ — iddia artık ödemenin GERÇEKLİĞİNİ ölçer,
        borcun sürmesini değil. Bu, D32'nin kendi dersidir (kusuru koruyan
        bekçi, gerekçesiyle çevrilir).

        Üç ayak: (1) xfail imi SÖKÜLMÜŞ, (2) bekçinin kendisi hâlâ duruyor
        (sessizce silinmedi), (3) iki PDF ikizi md5 olarak AYNI.
        """
        import hashlib

        metin = _oku('tests/test_d31_altyapi_a1.py')
        i = metin.index('def test_kilavuz_ikizi_kaynaktan_uretilmis')
        kesit = metin[max(0, i - 1200):i + 400]
        assert 'xfail(strict=True' not in kesit, (
            'kılavuz borç imi hâlâ duruyor: borç ödendiyse im sökülmeli '
            '(OH-D31-03 / OH-D21-07)')
        assert 'def test_kilavuz_ikizi_kaynaktan_uretilmis' in metin, (
            'ikiz bekçisi sessizce silinmiş')
        for ad in ('HRMA-Kullanma-Kilavuzu-TR.pdf', 'HRMA-User-Guide-EN.pdf'):
            a = open(os.path.join(KOK, 'hrma/static/docs', ad), 'rb').read()
            b = open(os.path.join(KOK, 'docs/user_guide', ad), 'rb').read()
            assert hashlib.md5(a).hexdigest() == hashlib.md5(b).hexdigest(), (
                '%s: ikizler yine ayrışmış (tools/kilavuz_derle.sh)' % ad)

    @pytest.mark.parametrize('ad', ['HRMA-Kullanma-Kilavuzu-TR', 'HRMA-User-Guide-EN'])
    def test_kaynak_tex_depoda_duruyor(self, ad):
        """Kılavuz dalgası kaynaktan üretecek: .tex + img depoda olmalı."""
        assert os.path.exists(os.path.join(KOK, 'docs/user_guide', ad + '.tex'))
        assert os.path.isdir(os.path.join(KOK, 'docs/user_guide/img'))
