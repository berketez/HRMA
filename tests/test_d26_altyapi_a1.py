"""ÖH Dalga-26 / altyapi aşama-1 bekçileri.

Kalem            Kusur
===============  ==========================================================
OH-D25-24        CI iş akışı yorumundaki node kapılı dosya sayısı ELLE
                 tutuluyordu ve her dalgada çürüyordu (88->92->94->97).
OH-B2-01         `release.yml` rocketcea kurulumunu hiç doğrulamıyordu
                 (bekçi xfail(strict) borç imiyle açık duruyordu).
OH-D25-04        `hrma.nsi` kaldırıcısının "yabancı dizin" dalı, "bu dizine
                 DOKUNULMUYOR" künyesini bastıktan sonra `hrma.ico` ve
                 `uninstall.exe` dosyalarını KOŞULSUZ siliyordu.
OH-D25-01        `tools/sabit_envanteri.py` CLI'si ikizleri saymıyordu
                 (7 ikizde exit 0); muafiyet kapısı yalnız gerekçe
                 UZUNLUĞUNU ölçüyordu, muafiyetin GERÇEK olup olmadığını
                 değil.
OH-D25-02        Tarayıcı harness'i 0 px'lik sentetik görüntüyü geçiriyordu
                 ve `rapor_olustur` tarayıcı denetimini iki kez hesaplıyordu.
P17B1-14         Harness "INVISCID" rozetini KOŞULSUZ bekliyordu; viskoz
                 koşum da aynı beyanı taşıyor sayılıyordu (Fable ŞARTI).

OH-D25-24 ve OH-B2-01'in ana bekçileri `tests/test_ci_kapsam_kapisi.py`
içindedir (borç imlerinin durduğu yer orasıydı); bu dosya onların ürün
tarafını (sayım aracı) ve kalan dört kalemi tutar.
"""

import ast
import pathlib
import re
import subprocess
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / 'tools'))

NSI = KOK / 'packaging' / 'hrma.nsi'


# ---------------------------------------------------------------------------
# OH-D25-24 — node kapılı dosya sayımı TEK KAYNAK araçtan gelir
# ---------------------------------------------------------------------------
class TestOHD2524SayimAraci:
    """Sayı yorumda değil araçta; araç fail-closed."""

    def test_arac_bekci_ile_AYNI_kumeyi_olcuyor(self):
        import node_kapisi_sayimi
        from tests.test_ci_kapsam_kapisi import node_kapili_test_dosyalari
        assert (node_kapisi_sayimi.node_kapili_test_dosyalari(KOK)
                == node_kapili_test_dosyalari())

    def test_arac_ELLE_yazilmis_dosya_listesi_TASIMIYOR(self):
        """Kusurun kökü elle tutulan listeydi; araç onu tekrar etmesin.

        Araçta bir dosya adı listesi olsaydı sayı yine elle tutulurdu —
        yalnız yeri değişmiş olurdu.
        """
        import node_kapisi_sayimi
        kaynak = pathlib.Path(node_kapisi_sayimi.__file__).read_text(
            encoding='utf-8')
        agac = ast.parse(kaynak)
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
                assert not re.match(r'tests/.*test_.*\.py$', dugum.value), (
                    'sayım aracında ELLE yazılmış test dosyası adı var: '
                    f'{dugum.value!r} — ölçüm kaynaktan türetilmeli')

    def test_arac_taban_altinda_SIFIRDAN_FARKLI_donuyor(self, tmp_path):
        """Fail-closed: ölçüm çökerse araç susmaz."""
        import node_kapisi_sayimi
        (tmp_path / 'tests').mkdir()
        (tmp_path / 'tests' / 'test_bos.py').write_text(
            'def test_x():\n    assert True\n', encoding='utf-8')
        assert node_kapisi_sayimi.main(['--kok', str(tmp_path)]) == 1

    def test_arac_gercek_depoda_gecerli(self):
        import node_kapisi_sayimi
        assert node_kapisi_sayimi.main([]) == 0

    @pytest.mark.parametrize('is_akisi', ['tests.yml', 'release.yml'])
    def test_is_akisi_sayim_adimini_kosuyor(self, is_akisi):
        metin = (KOK / '.github' / 'workflows' / is_akisi).read_text(
            encoding='utf-8')
        kod = '\n'.join(s for s in metin.splitlines()
                        if not s.lstrip().startswith('#'))
        assert 'tools/node_kapisi_sayimi.py' in kod, (
            f'{is_akisi} sayım adımını koşmuyor')


# ---------------------------------------------------------------------------
# OH-D25-04 — kaldırıcının 'yabancı dizin' dalındaki koşulsuz `Delete`
# ---------------------------------------------------------------------------
class TestOHD2504YabanciDizindeKosulsuzDelete:
    """Beyan ile davranış aynı dalda çelişemez.

    Ölçülen (taban 7751531, ``once_nsi.json``): ``yabanci_dal_kosulsuz_delete``
    = 2 (``hrma.ico``, ``uninstall.exe``). Dal, iki satır önce
    "$INSTDIR dizinine DOKUNULMUYOR" künyesini basıyordu — yani kusur
    "eksik temizlik" değil, KÜNYENİN YALAN OLMASIYDI. OH-D19-04 aynı dalın
    ``RMDir /r`` ayağını D20'de kapatmıştı; ``Delete`` ayağı kalmıştı.
    """

    @staticmethod
    def _yabanci_dal():
        kod = NSI.read_text(encoding='utf-8', errors='replace')
        kaldirma = kod.split('Section "Uninstall"', 1)[1].split(
            'SectionEnd', 1)[0]
        assert 'yabanci_dizin:' in kaldirma
        return kaldirma.split('yabanci_dizin:', 1)[1]

    def test_yabanci_dalda_KOSULSUZ_delete_yok(self):
        """Her `Delete` satırından önce bir kanıt kapısı olmalı."""
        yab = self._yabanci_dal()
        satirlar = [s.strip() for s in yab.splitlines()]
        kosulsuz = []
        for i, s in enumerate(satirlar):
            m = re.match(r'Delete\s+"\$INSTDIR\\([^"]+)"', s)
            if not m:
                continue
            onceki = ' '.join(satirlar[max(0, i - 6):i])
            if not re.search(r'IfFileExists|StrCmp', onceki):
                kosulsuz.append(m.group(1))
        assert not kosulsuz, (
            f'yabancı dizin dalında KANITSIZ silinen dosya: {kosulsuz} — '
            'dal iki satır önce "$INSTDIR dizinine DOKUNULMUYOR" diyor; '
            'kendi hükmünü çiğneyen künye yalandır (OH-D25-04)')

    def test_iki_dosya_da_kurulum_DUZENI_kanitina_bagli(self):
        """`libs` ile aynı kanıt: app\\launcher.py + python\\pythonw.exe."""
        yab = self._yabanci_dal()
        for ad in ('hrma.ico', 'uninstall.exe'):
            i = yab.find(f'Delete "$INSTDIR\\{ad}"')
            assert i > 0, f'{ad} silme satırı kayboldu (adres göçtü)'
            assert re.search(r'StrCmp\s+\$R2\s+"1"', yab[:i]), (
                f'{ad}, kurulum düzeni kanıtlanmadan siliniyor')

    def test_dokunulmayan_dosya_kullaniciya_SOYLENIYOR(self):
        """Sessiz atlama yasak — bırakılan dosya ADIYLA bildirilir."""
        yab = self._yabanci_dal()
        for ad in ('hrma.ico', 'uninstall.exe'):
            assert re.search(
                rf'DetailPrint\s+"\s*{re.escape(ad)}:.*DOKUNULMADI', yab), (
                f'{ad} bırakıldığında kullanıcıya hiçbir şey söylenmiyor')

    def test_bizim_kurulum_dali_ETKILENMEDI(self):
        """İmza VARKEN temizlik tam kalmalı — onarım kapsamı kaymasın."""
        kod = NSI.read_text(encoding='utf-8', errors='replace')
        kaldirma = kod.split('Section "Uninstall"', 1)[1].split(
            'SectionEnd', 1)[0]
        bizim = kaldirma.split('bizim_kurulum:', 1)[1].split(
            'yabanci_dizin:', 1)[0]
        for ad in ('hrma.ico', 'uninstall.exe'):
            assert f'Delete "$INSTDIR\\{ad}"' in bizim, (
                f'imzalı kurulumda {ad} artık silinmiyor — onarım fazla '
                'daralttı')

    def test_yeni_etiketler_TEK_kez_tanimli(self):
        """NSIS etiketi iki kez tanımlanırsa betik DERLENMEZ."""
        kod = NSI.read_text(encoding='utf-8', errors='replace')
        for etiket in ('yab_kalanlar', 'yab_kalanlar_yabanci',
                       'yab_kalanlar_bitti'):
            tanim = len(re.findall(rf'^\s*{etiket}:\s*$', kod, re.M))
            assert tanim == 1, f'{etiket} etiketi {tanim} kez tanımlı'
            assert re.search(rf'(Goto|StrCmp)[^\n]*\b{etiket}\b', kod), (
                f'{etiket} etiketine hiçbir dallanma yok (ölü etiket)')


# ---------------------------------------------------------------------------
# OH-D25-01 — sabit envanteri CLI'si ikizleri saymıyordu; muafiyet kapısı
#             yalnız gerekçe UZUNLUĞUNU ölçüyordu
# ---------------------------------------------------------------------------
class TestOHD2501SabitEnvanteriKapilari:
    """Araç kendi bulduğu kusuru çıkış koduna taşımıyordu.

    ÖLÇÜLDÜ (taban 7751531, ``once_nsi_envanter.json``): gerçek depoda kusur
    GİZLİDİR — bugün 5 yakın-ıska var, o yüzden CLI zaten 1 dönüyor. Kusur,
    yakın-ıskalar onarıldığı an ortaya çıkar. Sentetik ağaç (2 ikiz /
    0 yakın-ıska) tabanda ``cli_cikis_kodu = 0`` verdi: araç üç ikizi ekrana
    basıp ardından "temiz" hükmü döndürüyordu. İkiz sessiz bir kusurdur
    (sayı doğru, kaynak ikiye bölünmüş); sessizliği çıkış koduna da taşımak
    kusuru bir kat daha gizler.
    """

    @staticmethod
    def _sentetik(tmp_path, govde):
        (tmp_path / 'hrma').mkdir()
        (tmp_path / 'hrma' / 'constants.py').write_text(
            'G_0 = 9.80665\nR_UNIVERSAL = 8314.462618\n', encoding='utf-8')
        (tmp_path / 'hrma' / 'a.py').write_text(govde, encoding='utf-8')
        return tmp_path

    def test_YALNIZ_ikiz_varken_CLI_kirmizi_veriyor(self, tmp_path):
        """Onarımın çekirdeği: ``1 if yakin_iska else 0`` yetmez."""
        import sabit_envanteri
        kok = self._sentetik(tmp_path, 'IKIZ = 9.80665\n')
        sonuc = sabit_envanteri.envanter(kok)
        assert sonuc['ikiz'] >= 1 and sonuc['yakin_iska'] == 0, (
            'sentetik ağaç kurulamadı: %r' % sonuc)
        assert sabit_envanteri.main(['--kok', str(kok)]) == 1, (
            'yalnız ikiz varken CLI 0 döndü — araç kendi bulduğu kusuru '
            '"temiz" diye raporluyor (OH-D25-01a)')

    def test_TEMIZ_agacta_CLI_yesil(self, tmp_path):
        """Ters yön: kapı her şeye kırmızı demiyor (yoksa hiçbir şey demez)."""
        import sabit_envanteri
        kok = self._sentetik(tmp_path, 'ILGISIZ = 3.0\n')
        sonuc = sabit_envanteri.envanter(kok)
        assert sonuc['ihlaller'] == []
        assert sabit_envanteri.main(['--kok', str(kok)]) == 0

    def test_yakin_iska_ayagi_KORUNDU(self, tmp_path):
        """Eski davranış daralmadı."""
        import sabit_envanteri
        kok = self._sentetik(tmp_path, 'YAKIN = 9.81\n')
        assert sabit_envanteri.envanter(kok)['yakin_iska'] >= 1
        assert sabit_envanteri.main(['--kok', str(kok)]) == 1

    def test_HAYALET_muafiyet_kirmizi_veriyor(self, tmp_path, monkeypatch):
        """Muafiyet kapısı gerekçenin UZUNLUĞUNU değil GERÇEKLİĞİNİ ölçmeli.

        Mevcut kapı (``tests/test_d20_altyapi_a1.py``
        ::test_mesru_muafiyetlerin_GEREKCESI_var) yalnız ``len(gerekce) >= 40``
        sınıyordu: kırk karakterlik bir cümle yazan herkes, var olmayan bir
        adrese muafiyet tanımlayabilirdi. Envanter mandalı da bunu göremez —
        muafiyet ihlali ``mesru_isabetler``e taşır, envanter KÜÇÜLÜR ve
        ``len(simdi) <= len(kilit)`` yeşil kalır. Yani muafiyet, mandalın
        etrafından dolaşan bir kapıydı.
        """
        import sabit_envanteri
        kok = self._sentetik(tmp_path, 'IKIZ = 9.80665\n')
        uydurma = ({'dosya': 'hrma/a.py', 'sabit': 'G_0', 'deger': 9.80665,
                    'gerekce': 'GERÇEK adres — bu isabet kaynakta vardır, '
                               'muafiyet ona karşılık gelir.'},
                   {'dosya': 'hrma/a.py', 'sabit': 'G_0', 'deger': 1.2345678,
                    'gerekce': 'UYDURMA adres — kırk karakterden uzun bir '
                               'cümle, ama kaynakta karşılığı yok.'})
        monkeypatch.setattr(sabit_envanteri, 'MESRU', uydurma)
        sonuc = sabit_envanteri.envanter(kok)
        hayalet = sabit_envanteri.hayalet_muafiyet(sonuc, kok)
        assert [m['deger'] for m in hayalet] == [1.2345678], (
            'hayalet muafiyet görülmedi: %r' % hayalet)
        assert sabit_envanteri.main(['--kok', str(kok)]) == 1

    def test_hayalet_kapisi_KAPSAM_SINIRINI_beyan_ediyor(self, tmp_path):
        """Muafiyetin dosyası ağaçta yoksa hayalet SAYILMAZ.

        Yalancı kırmızı da bir kör banddır: her koşuda kırmızı veren bekçi
        ilk sıkışıklıkta susturulur ve hiçbir şey korumaz. Bu yüzden kapı,
        taranan ağaçta bulunmayan dosyalar için hüküm vermez.
        """
        import sabit_envanteri
        kok = self._sentetik(tmp_path, 'IKIZ = 9.80665\n')
        sonuc = sabit_envanteri.envanter(kok)
        # Gerçek deponun muafiyetleri bu sentetik ağaçta YOK; hiçbiri hayalet
        # sayılmamalı (dosyaları burada bulunmuyor).
        assert sabit_envanteri.hayalet_muafiyet(sonuc, kok) == []

    def test_gercek_depoda_HAYALET_muafiyet_yok(self):
        """Bugünkü tablo gerçek: üç satırın üçü de ölçülmüş bir isabete uyar."""
        import sabit_envanteri
        sonuc = sabit_envanteri.envanter(KOK)
        hayalet = sabit_envanteri.hayalet_muafiyet(sonuc, KOK)
        assert hayalet == [], (
            'muafiyet tablosunda kaynakta karşılığı OLMAYAN satır: %s'
            % [m['dosya'] + '::' + m['sabit'] for m in hayalet])

    def test_gercek_depoda_CLI_kusuru_SAKLAMIYOR(self):
        """Depoda 8 ihlal var; araç 0 dönerse "temiz" yalanı söyler."""
        import sabit_envanteri
        sonuc = sabit_envanteri.envanter(KOK)
        beklenen = 1 if sonuc['ihlaller'] else 0
        assert sabit_envanteri.main(['--kok', str(KOK)]) == beklenen


# ---------------------------------------------------------------------------
# P17B1-14 (Fable-D20/D21 ŞARTI) — viskoz beyan KOŞULLU çifte çevrildi
# ---------------------------------------------------------------------------
class TestP17B114ViskozKipCifti:
    """INVISCID beyanı koşulsuz bekleniyordu; ürün onu koşullu basar.

    Ürünün dalı (``hrma/static/js/panels/cfd_panel.js::viscousBadgesHtml``)::

        if (!v.enabled)  ->  badgeInviscid      'INVISCID (Euler) — ...'
        else             ->  badgeViscousMode   'VISCOUS — turbulence ...'

    Harness yalnız ilk dalı, üstelik KOŞULSUZ bekliyordu. Ölçüldü (taban
    7751531, ``once_viskoz.json``):

    ====================================  ==========  =========
    durum                                 taban       onarımlı
    ====================================  ==========  =========
    viskoz koşum + ekranda INVISCID       YEŞİL (!)   KIRMIZI
    viskoz koşum + ekranda VISCOUS —      KIRMIZI(!)  YEŞİL
    viskozsuz koşum + ekranda INVISCID    YEŞİL       YEŞİL
    ====================================  ==========  =========

    İlk satır kalemin ağırlığıdır: modelin EN AĞIR beyanı ("duvar kayması
    yok, duvar ısı akısı yok") tersine dönmüş olsa bile harness görmüyordu.
    Canlı ölçüm gerekmez — koşul ürünün kendi ``cfd.viscous.enabled``
    alanından okunur.
    """

    @staticmethod
    def _denet(olcum):
        from tools.browser_harness import denetimler, sayfalar
        K = sayfalar.CFD_KIRACISI
        return denetimler.merkez_rozet_denetimi(
            'cfd', olcum, K.beklenen_imzalar, K.yasak_imzalar, K.notr_imzalar)

    @staticmethod
    def _viskoz(viskoz_rozeti: bool):
        """Viskoz koşum ölçümü; rozet ya doğru (VISCOUS) ya ters (INVISCID)."""
        from tests.test_browser_harness_merkez import cfd_olcumu
        tam = cfd_olcumu()
        o = dict(tam)
        o['yuk'] = dict(tam['yuk'])
        o['yuk'].update(viscous_enabled=True, viscous_turbulence='sa',
                        viscous_wall_thermal='isothermal')
        if viskoz_rozeti:
            o['rozetler'] = (
                [r for r in tam['rozetler'] if 'INVISCID' not in r['metin']]
                + [{'metin': 'VISCOUS — turbulence sa, isothermal wall',
                    'tur': 'info', 'kaynak': 'rozet'}])
            o['metin'] = ' '.join(r['metin'] for r in o['rozetler'])
        return o

    def test_viskoz_kosumda_INVISCID_basiliysa_KIRMIZI(self):
        """ŞART (4) birinci ayağı — kalemin ağır ucu."""
        d = self._denet(self._viskoz(viskoz_rozeti=False))
        assert not d.gecti, (
            'viskoz koşumda ekranda INVISCID duruyor ve denetim GEÇTİ — '
            'ürünün en ağır beyanı tersine dönmüş, harness görmüyor')
        assert 'cfd_viskozsuz_beyani' in d.ozet and 'TERS beyan' in d.ozet, d.ozet

    def test_viskoz_kosumda_VISCOUS_basiliysa_YESIL(self):
        """ŞART (4) ikinci ayağı — yalancı kırmızı da kusurdur."""
        d = self._denet(self._viskoz(viskoz_rozeti=True))
        assert d.gecti, d.ozet

    def test_viskozsuz_kosumda_INVISCID_BEKLENIYOR(self):
        """D21'in kazanımı korundu: viskozsuz dalda beyan hâlâ zorunlu."""
        from tests.test_browser_harness_merkez import cfd_olcumu
        tam = cfd_olcumu()
        assert tam['yuk']['viscous_enabled'] is False, 'fixture koşulu taşımıyor'
        assert self._denet(tam).gecti
        eksik = dict(tam)
        eksik['rozetler'] = [r for r in tam['rozetler']
                             if 'INVISCID' not in r['metin']]
        eksik['metin'] = ' '.join(r['metin'] for r in eksik['rozetler'])
        d = self._denet(eksik)
        assert not d.gecti, (
            'viskozsuz koşumda kapsam beyanı ekrandan düştü ve denetim '
            'GEÇTİ — D21 kazanımı kayboldu')

    def test_viskozsuz_kosumda_VISCOUS_basiliysa_KIRMIZI(self):
        """Ters yön: viskozsuz koşum viskoz kip beyanı basamaz."""
        from tests.test_browser_harness_merkez import cfd_olcumu
        tam = cfd_olcumu()
        o = dict(tam)
        o['rozetler'] = list(tam['rozetler']) + [
            {'metin': 'VISCOUS — turbulence sa, adiabatic wall',
             'tur': 'info', 'kaynak': 'rozet'}]
        o['metin'] = ' '.join(r['metin'] for r in o['rozetler'])
        assert not self._denet(o).gecti

    def test_kosul_OKUNAMAZSA_hukum_verilmiyor(self):
        """Hayalet kırmızı yasağı: alan yayımlanmıyorsa dal seçilemez."""
        from tests.test_browser_harness_merkez import cfd_olcumu
        tam = cfd_olcumu()
        o = dict(tam)
        o['yuk'] = {k: v for k, v in tam['yuk'].items()
                    if k != 'viscous_enabled'}
        assert self._denet(o).gecti, (
            'koşul bilinmezken denetim hüküm vermiş — hangi rozetin doğru '
            'olduğu söylenemez')

    def test_kural_OTEKI_kiracilari_etkilemiyor(self):
        """`viscous_enabled` yayımlamayan kiracıda kural sessiz kalmalı."""
        from tests.test_browser_harness_merkez import akustik_olcumu
        from tools.browser_harness import denetimler, sayfalar
        K = sayfalar.ACOUSTIC_MODES_KIRACISI
        o = akustik_olcumu()
        assert 'viscous_enabled' not in (o.get('yuk') or {})
        d = denetimler.merkez_rozet_denetimi(
            'acoustic_modes', o, K.beklenen_imzalar, K.yasak_imzalar,
            K.notr_imzalar)
        assert d.gecti, d.ozet

    def test_viskoz_imza_varyanti_TIRELI(self):
        """`VISCOUS` yalın sözcüğü başka rozetlerin metninde de geçer.

        ``badgeViscousEnergy`` "VISCOUS budget" der; tiresiz bir varyant onu
        da yutar ve viskoz kip beyanı basılmasa bile denetim yeşil kalırdı.
        """
        from tools.browser_harness import esikler
        imza = esikler.ROZET_IMZALARI['cfd_viskoz_kipi']
        assert imza['varyantlar'] == ('VISCOUS —', 'VİSKOZ —')
        assert imza['sozluk_anahtarlari'] == ('panel.cfd.badgeViscousMode',)
        sozluk = (KOK / 'hrma/static/js/i18n_common.js').read_text(
            encoding='utf-8')
        assert sozluk.count("'panel.cfd.badgeViscousMode'") >= 2, (
            'EN + TR karşılığı sözlükte olmalı')
        js = (KOK / 'hrma/static/js/panels/cfd_panel.js').read_text(
            encoding='utf-8')
        assert 'panel.cfd.badgeViscousMode' in js
        # Enerji rozetinin metni viskoz kip imzasına takılmamalı.
        enerji = 'ENERGY IMBALANCE 8.42e-10 (relative, VISCOUS budget: ...)'
        assert not any(v in enerji for v in imza['varyantlar'])


# ---------------------------------------------------------------------------
# OH-D25-02 — tarayıcı harness'inin küçük fail-open boşlukları
# ---------------------------------------------------------------------------
# ÖH D27 / OH-D25-02(b) — SÖZLEŞME GENİŞLEDİ: ``tam_sayfa_goruntusu_denetimi``
# artık her dilimin ``sha256`` içerik imzasını da ŞART koşuyor (imzasız dilim
# fail-closed kırmızıdır, iki dilim birebir aynıysa kanıt sahtedir). Aşağıdaki
# sentetik dilimlere imza EKLENDİ; D26 iddialarının ölçtüğü şey (sıfır boylu
# dilim kapısı) değişmedi, yalnız girdi bugünkü sözleşmeye uyduruldu.
class TestOHD2502HarnessBosluklari:
    """Sıfır piksellik "kanıt", iki kez hesaplanan hüküm, elle yazılı bütçe."""

    @staticmethod
    def _denet(goruntuler):
        from tools.browser_harness import denetimler
        return denetimler.tam_sayfa_goruntusu_denetimi(goruntuler)

    def test_SIFIR_px_goruntu_kanit_sayilmiyor(self):
        """Kapı yalnız TAVANI ölçüyordu; taban yoktu.

        Ölçüldü (taban 7751531): ``tam_sayfa_px.yukseklik = 0`` verilen
        denetim GEÇİYOR ve özetinde "tek karede gerçekten yakalanabilir"
        yazıyordu. Sıfır boylu PNG, tarayıcı görüntüyü alamadığında ya da kap
        henüz kurulmamışken üretilen bozuk dosyanın imzasıdır — turun tek
        insan-okur kanıtı sessizce boş çıkabilirdi.
        """
        d = self._denet({'tam_sayfa': 'a.png',
                         'tam_sayfa_px': {'genislik': 1280, 'yukseklik': 0}})
        assert not d.gecti, d.ozet
        assert 'SAHTE KANIT' in d.ozet

    def test_gercek_yukseklik_hala_geciyor(self):
        """Taban, sağlam kanıtı reddetmiyor."""
        d = self._denet({'tam_sayfa': 'a.png',
                         'tam_sayfa_px': {'genislik': 1280, 'yukseklik': 4200}})
        assert d.gecti, d.ozet

    def test_SIFIR_boylu_dilim_kumesi_kanit_sayilmiyor(self):
        """Dilimli dalda sıfırlar birbirini götürüyordu.

        ``kapsanan == sayfa_y`` eşitliği 0 == 0 için de sağlanır: sıfır boylu
        dilimlerden oluşan bir küme, sayfa boyu da sıfır ölçüldüğünde
        "TAM olarak yakalandı" hükmü alıyordu.
        """
        d = self._denet({
            'tam_sayfa': 'a.png', 'sayfa_boyu_px': {'yukseklik': 0},
            'tam_sayfa_dilimleri': [
                {'yol': 'd0.png', 'y0': 0, 'istenen_yukseklik': 0,
                 'px': {'yukseklik': 0}, 'sha256': '0' * 64}]})
        assert not d.gecti, d.ozet

    def test_SIFIR_boylu_dilim_SAYFA_BOYU_dolu_iken_de_kirmizi(self):
        """Asıl sıfır-dilim kapısı: sayfa boyu SAĞLAM, bir dilim sıfır.

        Üstteki iddia sayfa boyunun da sıfır olduğu hâli sınar ve onu
        `sayfa_y <= 0` kapısı yakalar; dilim alt sınırı orada hiç
        çalışmıyordu (ters-mutasyonla ölçüldü: dilim kapısı sökülünce test
        yine yeşildi). Bu iddia sayfa boyunu dolu bırakır, böylece kırmızıyı
        VEREN tek şey dilim alt sınırı olur — toplam kapsam eşitliği
        (10000 == 10000) sağlandığı için başka hiçbir kapı devreye girmez.
        """
        d = self._denet({
            'tam_sayfa': 'a.png', 'sayfa_boyu_px': {'yukseklik': 10000},
            'tam_sayfa_dilimleri': [
                {'yol': 'd0.png', 'y0': 0, 'istenen_yukseklik': 10000,
                 'px': {'yukseklik': 10000}, 'sha256': '1' * 64},
                {'yol': 'd1.png', 'y0': 10000, 'istenen_yukseklik': 0,
                 'px': {'yukseklik': 0}, 'sha256': '2' * 64}]})
        assert not d.gecti, d.ozet
        assert 'sıfır yükseklikli' in d.ozet, d.ozet

    def test_dilimli_dal_saglam_kanitla_geciyor(self):
        d = self._denet({
            'tam_sayfa': 'a.png', 'sayfa_boyu_px': {'yukseklik': 20000},
            'tam_sayfa_dilimleri': [
                {'yol': 'd0.png', 'y0': 0, 'istenen_yukseklik': 10000,
                 'px': {'yukseklik': 10000}, 'sha256': '1' * 64},
                {'yol': 'd1.png', 'y0': 10000, 'istenen_yukseklik': 10000,
                 'px': {'yukseklik': 10000}, 'sha256': '2' * 64}]})
        assert d.gecti, d.ozet

    def test_tarayici_hukmu_TEK_kez_hesaplaniyor(self):
        """Aynı hüküm iki kez hesaplanırsa rapor kendisiyle çelişebilir.

        ``rapor_olustur`` ``tarayici_denetimi``yi iki kez çağırıyordu: biri
        kalan-denetim listesi için, biri raporun ``denetimler`` alanı için.
        Bugün ikisi aynı sonucu veriyor, ama iki AYRI nesnedir; denetim bir
        gün duruma bağlı hâle geldiğinde rapordaki hüküm ile kalan-denetim
        listesi ayrışır ve rapor kendi kendisiyle çelişir.
        """
        kaynak = (KOK / 'tools' / 'browser_harness' / 'run_tour.py').read_text(
            encoding='utf-8')
        agac = ast.parse(kaynak)
        islev = next(d for d in ast.walk(agac)
                     if isinstance(d, ast.FunctionDef) and d.name == 'rapor_olustur')
        cagrilar = [c for c in ast.walk(islev)
                    if isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Attribute)
                    and c.func.attr == 'tarayici_denetimi']
        assert len(cagrilar) == 1, (
            'rapor_olustur tarayici_denetimi\'ni %d kez çağırıyor — tek hesap, '
            'tek gerçek' % len(cagrilar))

    def test_is_akisi_ATLAMA_BUTCESI_ni_TEK_KAYNAKTAN_okuyor(self):
        """Yorumdaki 76 ile aracın sabiti AYNI olmalı.

        OH-D25-02 bu yorumu "bayat" diye açmıştı; ölçüm bunu ÇÜRÜTTÜ (yorum
        76 diyor, ``tools/atlama_kapisi.ATLAMA_BUTCESI`` de 76). Ama sayı
        elle yazılmış bir ikizdir ve OH-D25-24'ün tam olarak bu sınıftan
        çürüdüğü ölçüldü; bu yüzden yorum bekçiyle KİLİTLENİR. İş akışının
        kendi kodu zaten sabiti araçtan okur (``_esik('ATLAMA_BUTCESI')``);
        kilitlenen yalnız insan-okur gerekçedir.
        """
        import atlama_kapisi
        metin = (KOK / '.github' / 'workflows' / 'tests.yml').read_text(
            encoding='utf-8')
        iddialar = {int(m) for m in re.findall(r'BUTCE\s+(\d+)', metin)}
        assert iddialar, 'gerekçedeki bütçe iddiası silinmiş'
        assert iddialar == {atlama_kapisi.ATLAMA_BUTCESI}, (
            'tests.yml gerekçesi BUTCE %s diyor, tek kaynak '
            '(tools/atlama_kapisi.ATLAMA_BUTCESI) %d — yorum çürüdü'
            % (sorted(iddialar), atlama_kapisi.ATLAMA_BUTCESI))
        kod = '\n'.join(s for s in metin.splitlines()
                        if not s.lstrip().startswith('#'))
        assert "_esik('ATLAMA_BUTCESI')" in kod, (
            'iş akışı bütçeyi araçtan okumuyor — sayı ikinci kez yazılmış olur')
