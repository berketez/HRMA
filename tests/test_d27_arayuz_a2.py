"""ÖH Dalga-27 · arayuz · aşama-2 — bekçiler.

Kapsanan kalemler (defter kimlikleriyle):

* **OH-B3-02** (bekci-kirmizi, D26 DEVİR) — kalan ÜÇ sağır blok:
  ``blowdown/tank``ın altı künyesi, ``transient.erosion`` (5 çocuk) ve
  ``transient.flow_separation`` (6 çocuk).
* **P5B2-12** (bekci-kirmizi, D26 DEVİR) — panel yarısı: ``safety_panel.js``
  ısı zinciri geometrisini göndermiyordu.
* **OH-D26-10** — ``tests/test_i18n_dinamik.py`` güverte düzeneği
  ``units_constants.js``i yüklemiyordu (4 setup hatası).
* **OH-D26-16** — ``const YUZDE = 100.0`` iki panelde ayrı tanımlıydı.
* **P12aB1-02** — ``blowdown_panel.js``in 18 kullanıcı metni sözlüksüzdü.
* **P12aB2-02 / -03 / -05 / -07** — Türkçe etiket kusurları.

Bekçiler ÜRÜN kodunu ölçer; ölçüm betiği
``docs/scofield/raw/OH/D27/arayuz/a2/olcum.py`` ile aynı ölçütleri kullanır.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest
from tests.support.kanit import kanit_gerekli

KOK = Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
TPL = KOK / 'hrma' / 'templates'
TESTS = KOK / 'tests'


def oku(p):
    return p.read_text(encoding='utf-8')


def yorumsuz(kaynak):
    """// ve /* */ yorumlarını söker — iddia YORUMA değil KODA dayansın."""
    kaynak = re.sub(r'/\*.*?\*/', '', kaynak, flags=re.S)
    cikti = []
    for satir in kaynak.split('\n'):
        i = satir.find('//')
        while i >= 0:
            on = satir[:i]
            if (on.count("'") % 2 == 0 and on.count('"') % 2 == 0
                    and on.count('`') % 2 == 0):
                satir = on
                break
            i = satir.find('//', i + 2)
        cikti.append(satir)
    return '\n'.join(cikti)


# ====================================================================== OH-B3-02
BLOWDOWN_KUNYE = ('tank_volume_basis', 'of_ratio_basis',
                  'initial_pressure_basis', 'liquid_fill_fraction_basis',
                  'isp_delivered_avg_basis', 'initial_temperature_source')


class TestOHB302BlowdownKunyeleri:
    """Uç altı künye yayımlıyor; panel altısını da ADIYLA basmalı."""

    @pytest.mark.parametrize('alan', BLOWDOWN_KUNYE)
    def test_kunye_panelde_acik_ozellik_erisimiyle_okunuyor(self, alan):
        """AÇIK ``bd.<alan>`` erişimi aranır, çıplak dizge DEĞİL.

        Dinamik ``bd[ad]`` erişimi hem okuyana hem sözleşme bekçisinin
        okuma envanterine görünmez; "panel bu alanı basıyor" iddiası o
        hâlde kanıtlanamazdı (ölçüldü: ilk onarım denemesi wave3
        sözleşmesini kırmızı bıraktı).
        """
        gövde = yorumsuz(oku(JS / 'blowdown_panel.js'))
        assert re.search(r'\breturn bd\.%s;' % alan, gövde), (
            'blowdown_panel.js `%s` künyesini açık özellik erişimiyle '
            'okumuyor — künye ekrana inmez ve wave3 ters-yön sözleşmesi '
            'onu göremez' % alan)

    def test_kunye_dom_a_adiyla_iniyor(self):
        gövde = yorumsuz(oku(JS / 'blowdown_panel.js'))
        assert 'data-basis-field=' in gövde, (
            'künye satırları alan adını DOM\'a taşımıyor — tarayıcı turu '
            've bekçi satırı adıyla bulamaz')
        assert "getElementById('bp_basis_fields')" in gövde

    def test_kunye_uydurulmuyor(self):
        """Alan yoksa satır da YOK (fail-closed) — boş künye basılmaz."""
        gövde = yorumsuz(oku(JS / 'blowdown_panel.js'))
        assert re.search(r"typeof v === 'string' && v", gövde), (
            'künye toplayıcısı boş/eksik alanı süzmüyor')

    def test_sunucu_metni_html_kacisindan_geciyor(self):
        gövde = yorumsuz(oku(JS / 'blowdown_panel.js'))
        assert 'esc(SRV(k.text))' in gövde, (
            'künye metni innerHTML yoluna kaçışsız giriyor — SRV() HTML '
            'kaçışı YAPMAZ')

    def test_gorunum_modeli_alti_kunyeyi_de_topluyor(self, tmp_path):
        """ÜRÜN KOŞUMU (node): metin araması değil, gerçek görünüm modeli.

        Panelin saf görünüm modeli bölümü node altında koşturulur ve
        gerçek bir ``tank_blowdown`` bloğuyla beslenir. Metin bekçileri
        "kod bu adı anıyor" der; bu bekçi "kod bu değeri GERÇEKTEN
        çıkarıyor" der.
        """
        import shutil
        node = shutil.which('node')
        if node is None:
            pytest.skip('node kurulu değil')
        betik = r"""
const fs=require('fs'),vm=require('vm');
const src=fs.readFileSync(process.argv[2],'utf8');
const i=src.indexOf('// >>> BLOWDOWN_VIEWMODEL_START');
const j=src.indexOf('// <<< BLOWDOWN_VIEWMODEL_END');
const box={window:{I18N:null},console:console};box.globalThis=box;
vm.createContext(box);
vm.runInContext(src.slice(i,j)+'; this.__vm = buildViewModel;', box);
const bd={status:'modelled',basis:'B',time_s:[0,1],
  tank_pressure_bar:[40,20],chamber_pressure_bar:[30,15],
  mdot_ox_kg_s:[1,0.5],thrust_N:[1000,500],
  tank_volume_basis:'V1',of_ratio_basis:'O1',initial_pressure_basis:'P1',
  liquid_fill_fraction_basis:'F1',isp_delivered_avg_basis:'I1',
  initial_temperature_source:'T1'};
const tam=box.__vm({tank_blowdown:bd});
const bd2=Object.assign({},bd);
delete bd2.of_ratio_basis;              // alan YOK
bd2.isp_delivered_avg_basis='';         // boş dize
bd2.liquid_fill_fraction_basis=42;      // dize DEĞİL
const eksik=box.__vm({tank_blowdown:bd2});
process.stdout.write(JSON.stringify({
  mod: tam.mode,
  tam: (tam.kunyeler||[]).map(k=>[k.field,k.text]),
  eksik: (eksik.kunyeler||[]).map(k=>k.field)}));
"""
        # Geçici betik pytest'in tmp_path'ine yazılır — depo köküne
        # geçici dosya bırakmak paralel koşumları (ve depo temizliği
        # bekçilerini) tedirgin eder.
        yol = tmp_path / 'bd_gorunum.js'
        yol.write_text(betik, encoding='utf-8')
        r = subprocess.run([node, str(yol), str(JS / 'blowdown_panel.js')],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-600:]
        o = json.loads(r.stdout)
        assert o['mod'] == 'modelled'
        assert [a for a, _ in o['tam']] == list(BLOWDOWN_KUNYE), o['tam']
        assert [t for _, t in o['tam']] == ['V1', 'O1', 'P1', 'F1', 'I1', 'T1']
        # FAIL-CLOSED: eksik / boş / dize-olmayan künye UYDURULMAZ
        assert o['eksik'] == ['tank_volume_basis', 'initial_pressure_basis',
                              'initial_temperature_source'], o['eksik']

    def test_odenen_kunye_borc_defterinde_tasinmiyor(self):
        """Bu aşamanın ÖDEDİĞİ altı künye borç defterinde DURMAMALI.

        ÖLÇÜT DÜZELTİLDİ — ÖH D27 fix-27b (birleşme etkileşimi).
        Eski ölçüt blok ADININ iki sözlükte de bulunmamasıydı ve testin
        adı ``test_borc_imi_kaldirildi`` idi. O vekil, bu aşama kendi
        dalında yalnızken DOĞRUYDU: blokta tek borç kaynağı bu aşamanın
        ödediği altı künyeydi. Birleşmeden sonra D27 hibrit a1
        (``d198489``, ara commit ``d44f9548``; defter P13B4-04) AYNI
        bloğa ÜÇ dürüstlük alanı ekledi — ``tank_model_envelope_basis``,
        ``tank_saturation_band_clamped``, ``vapor_model_valid`` — ve
        ``blowdown_panel.js`` üçünü de 0 kez basıyor. Yani blok GERÇEK
        ve AÇIK bir borç taşıyor; eski ölçüt korunsaydı tek çıkış yolu
        o gerçek körlüğü kayıt DIŞI bırakmak olurdu — bekçi kusuru
        koruyacaktı.

        Yeni ölçüt aşamanın gerçekten iddia ettiği şeyi ölçer: ALTI
        KÜNYE ödendi ve borç olarak taşınmıyor. Blok adı defterde
        durabilir, ama yalnız BAŞKA alanlar için. Kapsam DARALMADI, yön
        değişti: ödenen künyelerden biri geri düşerse hem burası hem
        ``test_wave3_contract.py::test_durustluk_borcu_buyumez`` kırmızı
        verir (ikincisi ölçüldü — fix-27b ters mutasyon M5).
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            '_w3_bekci', TESTS / 'test_wave3_contract.py')
        w3 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(w3)
        borc = None
        for ad in dir(w3):
            nesne = getattr(w3, ad)
            if isinstance(nesne, type) and hasattr(nesne, 'DURUSTLUK_BORCU'):
                borc = nesne.DURUSTLUK_BORCU
                break
        assert borc is not None
        acik = tuple(borc.get('blowdown/tank', ()))
        tasinan = sorted(set(BLOWDOWN_KUNYE) & set(acik))
        assert not tasinan, (
            'bu aşamanın ÖDEDİĞİ künye hâlâ borç defterinde: %s' % tasinan)

        # İm ile defter tutarlı olmalı: borç imi ancak defterde açık alan
        # varken durabilir (bayat im XPASS(strict) ile süiti kırar), ve
        # defterdeki her alan panelde GERÇEKTEN geçmemelidir. Ölçüt
        # wave3'ün KENDİ okuma envanteridir — burada ikinci bir tanım
        # yazılmaz.
        im_var = 'blowdown/tank' in w3.TERS_BORCLU_BLOKLAR
        assert im_var == bool(acik), (
            'borç imi ile borç defteri çelişiyor (im=%s, defter=%s)'
            % (im_var, acik))
        envanter = w3._envanter_metinden(
            (JS / 'blowdown_panel.js').read_text(encoding='utf-8'))
        yanlis = sorted(set(acik) & envanter)
        assert not yanlis, (
            'defterde borçlu yazan alan panelde okunuyor — kayıt BAYAT: %s'
            % yanlis)


EROSION_COCUK = ('total_recession_mm', 'final_throat_diameter_mm')
FLOWSEP_COCUK = ('steps_floored', 'steps_total', 'criterion',
                 'steps_zero_clamped')


class TestOHB302TransientSagirBloklar:
    """``transient.erosion`` ve ``transient.flow_separation`` ekrana iner."""

    @pytest.mark.parametrize('alan', EROSION_COCUK + FLOWSEP_COCUK)
    def test_cocuk_alan_panelde_geciyor(self, alan):
        gövde = yorumsuz(oku(JS / 'transient_panel.js'))
        assert re.search(r'\.%s\b' % alan, gövde), (
            'transient_panel.js `%s` alanını hiç anmıyor — blok sağır' % alan)

    def test_erozyon_ornek_yokken_sayi_uydurmuyor(self):
        gövde = yorumsuz(oku(JS / 'transient_panel.js'))
        assert "ero.status === 'no_samples'" in gövde, (
            'örnek yokken gerileme sayısı uydurulabilir — fail-closed dal yok')
        assert 'badgeErosionNoSamples' in gövde

    def test_ayrilma_sifirda_da_basiliyor(self):
        """``steps_floored = 0`` da bir BİLGİdir: eğri yapışık akışta kalmış."""
        gövde = yorumsuz(oku(JS / 'transient_panel.js'))
        assert re.search(r"kirpik > 0 \? 'warn' : 'ok'", gövde), (
            'ayrılma rozeti yalnız kırpılma varken basılıyor olabilir')

    def test_sagir_taban_kucultuldu(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            '_w3_sagir', TESTS / 'test_wave3_contract.py')
        w3 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(w3)
        for ad in dir(w3):
            nesne = getattr(w3, ad)
            if isinstance(nesne, type) and hasattr(nesne, 'SAGIR_ALT_BLOKLAR'):
                assert 'transient' not in nesne.SAGIR_ALT_BLOKLAR, (
                    'iki blok kablolandı ama sağır taban küçültülmedi')
                return
        pytest.fail('SAGIR_ALT_BLOKLAR bulunamadı')


# ====================================================================== P5B2-12
class TestP5B212IsiZinciriPaneli:
    """``safety_panel.js`` ısı zinciri geometrisini de göndermeli."""

    @pytest.mark.parametrize('alan', ('chamber_length', 'throat_diameter'))
    def test_alan_fields_listesinde(self, alan):
        sp = oku(JS / 'panels' / 'safety_panel.js')
        blok = re.search(r'const FIELDS = \[(.*?)\n    \];', sp, re.S)
        assert blok, 'FIELDS listesi bulunamadı'
        assert re.search(r"\['%s'" % alan, blok.group(1)), (
            'safety_panel.js `%s` göndermiyor — uç termal hükmü '
            'fail-closed geri çeker ve termal eksen ekranda hiç hüküm '
            'üretemez' % alan)

    def test_varsayilan_bos_dize(self):
        """Boş varsayılan = isteğe bağlı alan; sayı UYDURULMAZ."""
        sp = oku(JS / 'panels' / 'safety_panel.js')
        for alan in ('chamber_length', 'throat_diameter'):
            m = re.search(r"\['%s',\s*\n\s*'[^']*',\s*\n\s*('[^']*'|\"\")"
                          % alan, sp)
            assert m, 'varsayılan okunamadı: %s' % alan
            assert m.group(1) == "''", (
                '%s varsayılanı boş dize değil (%s) — panel kullanıcı '
                'vermediği bir geometriyi uydurur' % (alan, m.group(1)))

    def test_dock_aynasi_guncel(self):
        """``SAFETY_PAYLOAD`` panelin FIELDS listesinin aynasıdır."""
        dock = oku(TESTS / 'test_analysis_dock_contract.py')
        yuk = re.search(r'^SAFETY_PAYLOAD = \{.*?^\}', dock,
                        re.S | re.M)
        assert yuk, 'SAFETY_PAYLOAD bulunamadı'
        for alan in ('chamber_length', 'throat_diameter'):
            assert ("'%s'" % alan) in yuk.group(0), (
                'dock aynası panelle ayrıştı: %s' % alan)

    def test_borc_imi_kaldirildi(self):
        dock = oku(TESTS / 'test_analysis_dock_contract.py')
        assert 'ÖH defter P5B2-12 — KALAN BORÇ' not in dock, (
            'panel yarısı ödendi ama xfail(strict) imi duruyor')


# ===================================================================== OH-D26-10
class TestOHD2610GuverteDuzenegi:
    """Node düzeneği ürünün ``<script>`` sırasını TAKLİT etmeli."""

    def test_duzenek_units_constants_yukluyor(self):
        dinamik = oku(TESTS / 'test_i18n_dinamik.py')
        listeler = re.findall(r"for \(const f of \[([^\]]*)\]\)", dinamik)
        dosyalar = {p.strip().strip('\'"')
                    for l in listeler for p in l.split(',') if p.strip()}
        assert 'units_constants.js' in dosyalar, (
            'güverte düzeneği units_constants.js yüklemiyor — '
            'motor_viz_deck.js onu (tek-kaynak kapısı) zorunlu kılar ve '
            'dosyadaki dört test setup hatasıyla düşer')

    def test_units_motor_viz_deckten_once(self):
        dinamik = oku(TESTS / 'test_i18n_dinamik.py')
        listeler = re.findall(r"for \(const f of \[([^\]]*)\]\)", dinamik)
        sira = [q.strip().strip('\'"')
                for l in listeler for q in l.split(',') if q.strip()]
        assert sira.index('units_constants.js') < sira.index('motor_viz_deck.js')

    @pytest.mark.parametrize('sablon', ('liquid.html', 'solid.html'))
    def test_urun_sablonu_dogru_sirali(self, sablon):
        """Kusur ÜRÜNDE DEĞİL düzenektedir — bu bekçi onu kilitler."""
        metin = oku(TPL / sablon)
        i_u = metin.find('/static/js/units_constants.js')
        i_d = metin.find('/static/js/motor_viz_deck.js')
        assert i_d >= 0
        assert 0 <= i_u < i_d, (
            '%s: units_constants.js motor_viz_deck.js\'ten SONRA (ya da hiç) '
            'yükleniyor — sayfa fail-closed kapıya çarpar' % sablon)


# ===================================================================== OH-D26-16
class TestOHD2616YuzdeTekKaynak:
    """Saf birim çarpanı 100 tek yerde yaşar."""

    def test_yerel_tanim_kalmadi(self):
        bulunan = {}
        for p in sorted(JS.rglob('*.js')):
            n = len(re.findall(r'const\s+YUZDE\s*=\s*100',
                               yorumsuz(oku(p))))
            if n:
                bulunan[str(p.relative_to(KOK))] = n
        assert not bulunan, (
            'yerel yüzde tanımı duruyor: %s — birinde düzeltilen çevrim '
            'diğerinde sessizce eski kalır' % bulunan)

    def test_merkezi_tanim_var(self):
        uc = oku(JS / 'units_constants.js')
        assert 'PERCENT_PER_FRACTION' in uc
        assert 'requirePercentPerFraction' in uc

    @pytest.mark.parametrize('panel', ('fea_panel.js', 'thermal_fea_panel.js'))
    def test_panel_merkezden_okuyor(self, panel):
        gövde = yorumsuz(oku(JS / panel))
        assert 'requirePercentPerFraction' in gövde, (
            '%s yüzde çarpanını tek kaynaktan okumuyor' % panel)
        # YARDIMCININ VARLIĞI YETMEZ, KULLANILMASI gerekir: ters-mutasyon
        # yalnız ÇAĞRI YERİNİ `* 100.0` yapınca bu bekçi (eski hâlinde)
        # yeşil kalıyordu — yardımcı tanımı dosyada durduğu için. İddia
        # artık dönüşümün KENDİSİNE bakar.
        assert 'sapma * yuzdeCarpani()' in gövde, (
            '%s yüzde dönüşümünü tek kaynaktan DEĞİL çıplak sayıyla '
            'yapıyor olabilir' % panel)
        assert not re.search(r'sapma \* 1[0-9.]*\b', gövde), (
            '%s içinde çıplak yüzde çarpanı kaldı' % panel)

    def test_merkez_fail_closed(self):
        """Modül yoksa yedek sayı UYDURULMAZ — hata fırlar."""
        uc = oku(JS / 'units_constants.js')
        duz = ' '.join(uc.replace("'\n", '').replace("+ '", '').split())
        assert 'no fallback value is invented' in duz.lower(), (
            'merkezi yüzde erişimcisi sessiz bir yedek sayıya düşüyor '
            'olabilir — fail-closed cümlesi yok')


# ===================================================================== P12aB1-02
class TestP12aB102BlowdownSozlugu:
    """Panelin kullandığı her ``blowdown.*`` anahtarı sözlükte olmalı."""

    def test_sozluksuz_anahtar_kalmadi(self):
        ortak = oku(JS / 'i18n_common.js')
        panel = oku(JS / 'blowdown_panel.js')
        kullanilan = set(re.findall(
            r"['\"](blowdown\.[A-Za-z0-9_.]+)['\"]", panel))
        tanimli = set(re.findall(
            r"['\"](blowdown\.[A-Za-z0-9_.]+)['\"]\s*:", ortak))
        eksik = sorted(kullanilan - tanimli)
        assert not eksik, (
            'Türkçe ekranda İngilizce kalacak %d anahtar: %s — T() anahtarı '
            'bulamayınca İngilizce varsayılana düşer' % (len(eksik), eksik))
        assert len(kullanilan) >= 18

    def test_anahtarlar_iki_blogun_da_icinde(self):
        """i18n anahtarı kuralı: EN ve TR bloklarının İÇİNE."""
        ortak = oku(JS / 'i18n_common.js')
        i_en, i_tr = ortak.find('        en: {'), ortak.find('        tr: {')
        assert 0 <= i_en < i_tr
        en_blok, tr_blok = ortak[i_en:i_tr], ortak[i_tr:]
        for blok, ad in ((en_blok, 'en'), (tr_blok, 'tr')):
            n = len(re.findall(r"'blowdown\.[A-Za-z0-9_.]+':", blok))
            assert n >= 24, '%s bloğunda yalnız %d blowdown anahtarı' % (ad, n)


# ============================================== P12aB2-02 / -03 / -05 / -07
def _tr_blok(metin):
    i = metin.find('        tr: {')
    return metin[i:] if i >= 0 else ''


def _en_blok(metin):
    i, j = metin.find('        en: {'), metin.find('        tr: {')
    return metin[i:j] if 0 <= i < j else ''


class TestP12aTurkceEtiketler:

    def test_p12ab202_itici_kutlesi(self):
        """Oksitleyici kartında LOX kütlesi "Yakıt Kütlesi" diye anılamaz."""
        trp = _tr_blok(oku(JS / 'i18n_pages.js'))
        kalan = re.findall(
            r"'(?:liq|solid)\.(?:js|ui)\.propellant_mass': 'Yakıt Kütlesi", trp)
        assert not kalan, (
            '%d anahtar hâlâ "Yakıt Kütlesi" diyor — aynı anahtar '
            'OKSİTLEYİCİ tankı kartında da kullanılıyor ve oradaki sayı '
            'LOX kütlesidir (gerçek yakıt kütlesinin ~2,5 katı)' % len(kalan))
        assert len(re.findall(
            r"'(?:liq|solid)\.(?:js|ui)\.propellant_mass': 'İtici Kütlesi",
            trp)) == 3

    def test_p12ab203_thin_web(self):
        """"thin web" = ince yakıt eti; "ince ağ" rozeti totolojik yapıyordu."""
        trp = _tr_blok(oku(JS / 'i18n_pages.js'))
        assert 'ince ağ' not in trp, (
            'mesh rozeti gerekçesini yine mesh\'e dayandırıyor')
        m = re.search(r"'solid\.fea\.badge_elongated': '([^']*)'", trp)
        assert m and 'YAKIT ETİNDE' in m.group(1).upper()

    def test_p12ab205_tek_terim(self):
        """Aynı kavram tek Türkçe terimle anılır (sözlük başlığının kuralı)."""
        # KAPSAM: bu kulvarın sahasındaki ÜÇ sözlük. ``i18n_shell.js``
        # electron kulvarının sahasıdır ve D27'de o dal ona dokunuyor
        # (kardeş-dal ölçümü) — iki kalan "lüle" orada durur, bu
        # dalgada DOKUNULMADI ve raporda ilan edildi.
        metinler = ''.join(oku(JS / f) for f in
                           ('i18n.js', 'i18n_pages.js', 'i18n_common.js'))
        assert not re.findall(r'[Ll]üle', metinler), (
            'nozzle için ikinci terim ("lüle") duruyor; baskın terim "nozul"')
        # GRAIN AYAĞI **KISMEN** ÖDENDİ — dürüst sınır. Onarılan DÖRT
        # anahtar aşağıda tek tek kilitlenir. Depoda çevrilmemiş "grain"
        # taşıyan başka Türkçe değerler DE var (ölçüldü: `solid.ui.
        # initial_diameter_of_the_central_core` ipucundaki "BATES grain
        # tipi" gibi uzun kanıt metinleri). Onlar bu aşamada AÇILMADI:
        # kimi teknik özel ad ("BATES grain") kimi de ölçüm kanıtı
        # taşıyan uzun metindir ve tek tek yargılanmaları gerekir.
        # Süpürmeyi burada TAM ilan etmek, yapılmamış bir işi yeşil
        # göstermek olurdu.
        onarilan = {
            'solid.ui.preview_unknown_grain': 'yakıt bloğu tipi',
            'solid.ui.slotted_configuration': 'Yarıklı Yakıt Bloğu',
            'card.solid.desc': 'yakıt bloğu geometrileriyle',
            'card.solid.f1': 'yakıt blokları',
        }
        govde = oku(JS / 'i18n_pages.js') + oku(JS / 'i18n.js')
        for anahtar, beklenen in onarilan.items():
            m = re.findall(r"'%s': '([^']*)'" % re.escape(anahtar), govde)
            assert m, 'anahtar yok: %s' % anahtar
            assert any(beklenen in v for v in m), (
                '%s Türkçe değeri "%s" içermiyor: %s'
                % (anahtar, beklenen, m))
            assert not any(re.search(r'\bgrain', v, re.I) for v in m
                           if beklenen in v), (
                '%s hâlâ çevrilmemiş "grain" taşıyor' % anahtar)


    def test_p12ab207_tank_ic_yapilari_tankini_adlandiriyor(self):
        """Altı satırın altısı da oksitleyici tankından — ad bunu söylemeli."""
        pages = oku(JS / 'i18n_pages.js')
        tr = re.search(r"'liq\.js\.tank_internal_structures': '([^']*)'",
                       _tr_blok(pages))
        en = re.search(r"'liq\.js\.tank_internal_structures': '([^']*)'",
                       _en_blok(pages))
        assert tr and en
        assert 'ksitleyici' in tr.group(1), tr.group(1)
        assert 'Oxidizer' in en.group(1), en.group(1)
        # kartın verisi gerçekten yalnız oksitleyici tankından mı
        liquid = oku(TPL / 'liquid.html')
        i = liquid.find("T('liq.js.tank_internal_structures'")
        assert i > 0
        kart = liquid[i:liquid.find('</table>', i)]
        assert 'fuel_tank' not in kart, (
            'kart artık yakıt tankından da veri çekiyor — başlık yeniden '
            'gözden geçirilmeli')
        assert kart.count('oxidizer_tank.internal_structures') == 6


# ------------------------------------------------------------------ düzenek
class TestDuzenekCanli:
    """Ölçüm betiği ile bekçi AYNI ölçütü kullanır — betik koşabilmeli."""

    def test_olcum_betigi_kosuyor(self, tmp_path):
        betik = (KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D27' / 'arayuz'
                 / 'a2' / 'olcum.py')
        assert kanit_gerekli(betik).exists()
        r = subprocess.run(['python3', kanit_gerekli(str(betik)), str(KOK)],
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr[-800:]
        o = json.loads(r.stdout)
        assert o['blowdown_kunye_okunan_sayisi'] == 6
        assert o['blowdown_sozluksuz_anahtar_sayisi'] == 0
        assert o['safety_fields_isi_zinciri_sayisi'] == 4
        assert o['yuzde_yerel_tanim_sayisi'] == 0
        assert o['deck_harness_units_yukluyor'] == 1
        assert o['tr_propellant_mass_yakit'] == 0
        assert o['tr_thin_web_ince_ag'] == 0
        assert o['tank_internals_oksitleyici_adli'] == 1
        assert o['terim_lule'] == 0
        # ÖH D27 fix-27b — ÖLÇÜT AŞAMANIN İDDİASINA ÇEVRİLDİ.
        # Eski satır ``blowdown_borc_imi_var == 0`` idi; birleşmeden
        # sonra 1 oldu, çünkü D27 hibrit a1 (`d198489`, P13B4-04) AYNI
        # bloğa ÜÇ yeni dürüstlük alanı getirdi ve panel üçünü de
        # basmıyor — yani im BAYAT DEĞİL, GERÇEK. Eski ölçüt korunsaydı
        # tek çıkış yolu gerçek körlüğü kayıt dışı bırakmaktı.
        # Bu aşamanın ödemesi ise AYNEN ölçülüyor: altı künyenin hiçbiri
        # borç defterinde taşınmıyor (ve yukarıdaki
        # ``blowdown_kunye_okunan_sayisi == 6`` panelde okunduklarını
        # gösteriyor).
        assert o['blowdown_odenmis_kunye_borcu'] == []
        # İm ile defter TUTARLI olmalı: im ancak defterde açık alan
        # varken durabilir. Bayat im wave3'te XPASS(strict) ile zaten
        # kırmızı verir; bu satır aynı tutarlılığı düzenek tarafında da
        # bağlar.
        assert o['blowdown_borc_imi_var'] == int(
            bool(o['blowdown_acik_borc_alanlari']))
        assert o['sagir_taban_transient'] == []
        assert o['dock_p5b212_xfail_imi'] == 0
