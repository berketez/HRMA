# -*- coding: utf-8 -*-
"""ÖH D29 · arayuz-i18n aşama-1 bekçileri.

Kapsam (iş listesi sırasıyla):
  · P12aB2-06  liquid.html'de T()/TF() ile bağlanmamış altı görünür metin
  · OH-D17-22  advanced.html applyOxidizerTempBand bant beyanı i18n'siz
  · OH-D19-29  i18n_shell.js ölü-anahtar kapsamı (ÇÜRÜTÜLDÜ — kilitlenir)
  · P15B3-06   iddia_lint araya-sözcük körlüğü (ÇÜRÜTÜLDÜ — kilitlenir)
  · P15B3-08   çıplak-etiket bekçisinin elle-liste çürümesi

Ölçüm dosyaları: docs/scofield/raw/OH/D29/arayuz-i18n/a1/{once,sonra}.json
"""
import pathlib
import re
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
TPL = KOK / 'hrma' / 'templates'


def oku(p):
    return p.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# P12aB2-06 — bağlanmamış görünür İngilizce metinler
# ---------------------------------------------------------------------------
#: Borcun ADIYLA sayılan altı kalemi. Sol taraf = onarımdan ÖNCEKİ ham
#: biçim (T()/TF() ile SARILMAMIŞ hâli); geri gelirse bekçi kırmızı verir.
#: Sağ taraf = kalemi bağlayan anahtar; anahtar düşerse de kırmızı verir.
P12AB2_06_BORC = (
    ("Trajectory could not be computed: ' + e.message",
     'liq.js.trajectory_could_not_be_computed'),
    ('Detailed CAD generation failed: ${errorData.error}',
     'liq.js.detailed_cad_generation_failed'),
    ("row('Material',", 'liq.js.row_material'),
    ("row('Coolant',", 'liq.js.row_coolant'),
    ("row('Title',", 'liq.js.row_title'),
    ("row('Status',", 'liq.js.row_status'),
)


@pytest.mark.parametrize('ham,anahtar', P12AB2_06_BORC,
                         ids=[a for _, a in P12AB2_06_BORC])
def test_p12ab2_06_metin_baglandi(ham, anahtar):
    """Ham İngilizce dize gitmeli, onu bağlayan anahtar çağrılmalı."""
    sablon = oku(TPL / 'liquid.html')
    assert ham not in sablon, (
        'liquid.html hâlâ bağlanmamış İngilizce metin taşıyor: %r' % ham)
    assert ("'%s'" % anahtar) in sablon, (
        '%s çağrı yeri liquid.html içinde yok — anahtar ÖLÜ çeviri olur'
        % anahtar)


@pytest.mark.parametrize('anahtar', [a for _, a in P12AB2_06_BORC])
def test_p12ab2_06_anahtar_iki_blokta_da_var(anahtar):
    """EN ve TR bloklarının İÇİNE indi mi (dosya sonuna değil)?"""
    sozluk = oku(JS / 'i18n_pages.js')
    n = sozluk.count("'%s':" % anahtar)
    assert n == 2, ('%s sözlükte %d kez tanımlı — EN ve TR bloklarında '
                    'birer kez olmalı' % (anahtar, n))
    # TR karşılığı İngilizce'nin kopyası olmasın (ölü çeviri kılığı).
    tr_baslangic = sozluk.index("\n        tr: {")
    en_deger = re.search(r"'%s': '([^']*)'" % re.escape(anahtar),
                         sozluk[:tr_baslangic]).group(1)
    tr_deger = re.search(r"'%s': '([^']*)'" % re.escape(anahtar),
                         sozluk[tr_baslangic:]).group(1)
    assert en_deger != tr_deger, (
        '%s TR karşılığı İngilizce ile birebir aynı: %r' % (anahtar, en_deger))
    # Yer tutucular iki dilde de aynı kümede olmalı.
    assert (set(re.findall(r'\{(\w+)\}', en_deger))
            == set(re.findall(r'\{(\w+)\}', tr_deger))), (
        '%s yer tutucuları EN/TR arasında ayrışmış' % anahtar)


def test_p12ab2_06_kapsam_beyani_borcu_odenmis_gosteriyor():
    """Başlık ne "TÜM" der, ne de ödenmiş borcu açık gösterir."""
    bas = oku(JS / 'i18n_pages.js')[:4000]
    assert 'sayfalarının TÜM kullanıcı metinleri' not in bas
    assert 'P12aB2-06' in bas
    assert 'ÖDENDİ' in bas, 'ödenmiş borç dökümde işaretlenmemiş'


# ---------------------------------------------------------------------------
# OH-D17-22 — oksitleyici sıvı bandı beyanı
# ---------------------------------------------------------------------------
def _band_govdesi():
    adv = oku(TPL / 'advanced.html')
    i = adv.index('function applyOxidizerTempBand')
    j = adv.index('async function updateOxidizerProperties', i)
    return adv[i:j]


def test_oh_d17_22_bant_metinleri_i18n_uzerinden():
    """Bant beyanı ve yokluğu artık sözlükten gelir, sabit İngilizce değil."""
    govde = _band_govdesi()
    assert "'Liquid band not published for '" not in govde
    assert "'Liquid band (server OXIDIZER_LIQUID_BAND) '" not in govde
    cagrilar = re.findall(r"i18nFmt\('(adv\.js\.oxidizerBand\w+)'", govde)
    assert sorted(cagrilar) == ['adv.js.oxidizerBandNotPublished',
                                'adv.js.oxidizerBandRange'], cagrilar


@pytest.mark.parametrize('anahtar', ['adv.js.oxidizerBandNotPublished',
                                     'adv.js.oxidizerBandRange'])
def test_oh_d17_22_anahtar_iki_blokta(anahtar):
    sozluk = oku(JS / 'i18n_advanced.js')
    assert sozluk.count("'%s':" % anahtar) == 2, anahtar
    degerler = re.findall(r"'%s': '([^']*)'" % re.escape(anahtar), sozluk)
    assert len(degerler) == 2 and degerler[0] != degerler[1], degerler
    assert (set(re.findall(r'\{(\w+)\}', degerler[0]))
            == set(re.findall(r'\{(\w+)\}', degerler[1]))), degerler


def test_oh_d17_22_bant_yoklugunda_aralik_uydurulmuyor():
    """FAIL-CLOSED ayağı korunuyor: bant yoksa min/max KALDIRILIR."""
    govde = _band_govdesi()
    assert "el.removeAttribute('min')" in govde
    assert "el.removeAttribute('max')" in govde


def test_oh_d17_22_anahtar_tarayicinin_gordugu_bicimde():
    """Anahtar literali `i18nFmt(` ile AYNI satırda olmalı.

    tests/test_i18n_advanced.py::template_keys deseni açılış parantezinden
    sonra satır sonunu görmez; çok satırlı yazım canlı anahtarı ÖLÜ çeviri
    sayar (ölçüldü: bu aşamada iki anahtar bu yüzden kırmızı verdi).
    """
    govde = _band_govdesi()
    for anahtar in ('adv.js.oxidizerBandNotPublished',
                    'adv.js.oxidizerBandRange'):
        assert ("i18nFmt('%s'" % anahtar) in govde, anahtar


# ---------------------------------------------------------------------------
# OH-D19-29 — i18n_shell.js ölü-anahtar kapsamı (ÇÜRÜTÜLDÜ, kilitlenir)
# ---------------------------------------------------------------------------
def test_oh_d19_29_shell_sozluk_kaynagi_sayiliyor():
    """Bulgu "i18n_shell.js için ölü-anahtar bekçisi yok" diyordu.

    ÖLÇÜLDÜ (D29 a1): bekçi sözlük kaynaklarını DİSKTEN türetiyor ve
    i18n_shell.js o kümede; `stepimp` ön eki de FIELD_RE'de. Yani iddia
    çürük — ama çürüklüğü ancak bu iki ayak yerinde durduğu sürece
    geçerli, o yüzden ikisi de burada kilitlenir.
    """
    sys.path.insert(0, str(KOK))
    from tests import test_i18n_common as ti
    adlar = {p.name for p in ti.SOZLUK_KAYNAKLARI}
    assert 'i18n_shell.js' in adlar, adlar
    assert 'stepimp' in ti.FIELD_RE.pattern
    assert ti.FIELD_RE.search("'stepimp.refuseSolidChamberLen'"), (
        'stepimp anahtarı alan dizisinde görünmüyor — bekçi onu ölü sanır')
    # Anahtar gerçekten üründe yaşıyor (yalnız sözlükte değil).
    assert 'stepimp.refuseSolidChamberLen' in oku(JS / 'step_import_ui.js')


# ---------------------------------------------------------------------------
# P15B3-06 — iddia_lint araya-sözcük körlüğü (ÇÜRÜTÜLDÜ, kilitlenir)
# ---------------------------------------------------------------------------
IDDIA_ORNEKLERI = (
    'Parametric Solvers · NASA CEA Validated · 3D Model',
    'Data will be validated against NASA CEA database.',
    'NASA CEA doğrulamalı',
    'validated with NASA CEA',
)


@pytest.mark.parametrize('metin', IDDIA_ORNEKLERI)
def test_p15b3_06_araya_sozcuk_giren_iddia_yakalaniyor(metin):
    """Bulgu "araç 0 eşleşme veriyor" diyordu; ölçüm bunu çürütür.

    Kural `nasa_validated` gerçekten araya sözcük girince kopar, ama
    `cea_validated` (KUNYE_YALANI demeti) tam bu biçim için yazılmıştır ve
    ALL_RULES üzerinden taranınca dördü de yakalanır. Bekçi ALL_RULES'u
    tarar: kural demetten çıkarılırsa kırmızı verir.
    """
    sys.path.insert(0, str(KOK))
    from tools import iddia_lint
    isabet = [r.rule_id for r in iddia_lint.ALL_RULES
              if re.search(r.pattern, metin, re.IGNORECASE)]
    assert isabet, ('iddia_lint bu metni kaçırıyor: %r' % metin)


def test_p15b3_06_urunde_iddia_kalmadi():
    """Bulgunun işaret ettiği iki ürün yüzeyi temiz kalmalı."""
    for ad in ('index.html', 'advanced.html'):
        assert 'NASA CEA Validated' not in oku(TPL / ad), ad


# ---------------------------------------------------------------------------
# OH-Z3-04 (liq.* ayağı) — makine alan adı insan etiketiyle adlandırıldı
# ---------------------------------------------------------------------------
def test_oh_z3_04_izin_verilen_sicaklik_adlandirildi():
    """Çıplak makine adı gitti, anahtar geldi, künye KORUNDU."""
    sablon = oku(TPL / 'liquid.html')
    assert " · station_march.material_allowable_K = '" not in sablon, (
        'malzeme sınırı hâlâ yalnız çıplak makine adıyla basılıyor')
    assert "TF('liq.msg.material_allowable_temperature'" in sablon
    sozluk = oku(JS / 'i18n_pages.js')
    assert sozluk.count("'liq.msg.material_allowable_temperature':") == 2
    degerler = re.findall(
        r"'liq\.msg\.material_allowable_temperature': '([^']*)'", sozluk)
    assert len(degerler) == 2 and degerler[0] != degerler[1], degerler
    for d in degerler:
        # Künye (çözücü alan adı) iki dilde de duruyor — sayının nereden
        # geldiği çeviriyle kaybolmaz.
        assert 'station_march.material_allowable_K' in d, d
        assert '{value}' in d, d


# ---------------------------------------------------------------------------
# P15B3-08 — çıplak-etiket bekçisinin kapsamı elle listeden kurtuldu
# ---------------------------------------------------------------------------
def test_p15b3_08_kapsam_elle_listeden_buyuk():
    sys.path.insert(0, str(KOK))
    from tests import test_ciplak_etiket_common as tc
    assert len(tc.TURETILMIS_TUKETICILER) >= 40, len(tc.TURETILMIS_TUKETICILER)
    adlar = {p.name for p in tc.TURETILMIS_TUKETICILER}
    for beklenen in ('app.js', 'thermal_panel.js', 'cooling_panel.js',
                     'comparative_panel.js', 'uncertainty_panel.js'):
        assert beklenen in adlar, beklenen
    # Adlı borç ADIYLA duruyor (sessiz muafiyet değil).
    assert set(tc.ADLI_BORC) == {'comparative_panel.js',
                                 'uncertainty_panel.js'}, tc.ADLI_BORC


# ---------------------------------------------------------------------------
# OH-D19-26 — bekçi hijyeni demeti (kısmen: d ve g onarıldı)
# ---------------------------------------------------------------------------
def test_oh_d19_26_d_emniyet_katsayisi_bandi_kilitli():
    """Tek literal (1.2) yerine BAND yasağı: 1,25 / 6/5 de yakalanmalı."""
    kaynak = oku(KOK / 'tests' / 'test_d17_yapisal_sistem_a1.py')
    assert 'sf_bandi' in kaynak, 'band yasağı geri alınmış'
    assert '1.0 < x <= 4.0' in kaynak
    assert 'ast.literal_eval(dugum)' in kaynak, (
        'sabit-katlanan ifadeler (6 / 5) yine görülmüyor')


def test_oh_d19_26_g_sarkan_atif_kalmadi():
    """Bekçi yorumlarındaki kanıt yolları GERÇEKTEN var olmalı.

    İstisna: bulunmadığı AYNI SATIRDA "YOK" diye beyan edilen tarihsel
    kayıt. Beyansız her sarkan atıf kırmızıdır — okuyucu var sanır.
    """
    kaynak = oku(KOK / 'tests' / 'test_analysis_dock_contract.py')
    sarkan = []
    for satir in kaynak.split('\n'):
        for yol in re.findall(r'``(docs/scofield/raw/[^`]+)``', satir):
            # Yol METİNDEN çıkarılır (dinamik): kapı elle; 'YOK' beyanı önce.
            if 'YOK' in satir or kanit_gerekli(KOK / yol).exists():
                continue
            sarkan.append(yol)
    assert not sarkan, 'beyansız sarkan kanıt atfı: %s' % sarkan
    # Onarımın kendisi: eski atıf artık BEYANLI ve doğru kayıt yerinde.
    assert 'once_ohz516.json`` YOK' in kaynak
    for var_olan in ('docs/scofield/raw/OH/D17/bekci-cevirisi/a1/rapor.md',
                     'docs/scofield/raw/OH/D17/bekci-cevirisi/a1/'
                     'mutasyon.json'):
        assert var_olan in kaynak and (kanit_gerekli(KOK / var_olan)).exists(), var_olan


# ---------------------------------------------------------------------------
# OH-D19-26 (c) — adres kilidi METİN aramasıydı, CANLILIK sondasına çevrildi
# ---------------------------------------------------------------------------
#: Ölü bekçi numuneleri (pytest bunları TOPLAMAZ; sonda okur).
NUMUNE = 'docs/scofield/raw/OH/D29/arayuz-i18n/a1/ornek_bekciler.py'


def _sonda():
    sys.path.insert(0, str(KOK))
    from tests.test_d17_bekci_cevirisi_a1 import _bekci_canliligi
    return _bekci_canliligi


@pytest.mark.parametrize('ad,beklenen,ipucu', [
    ('test_canli_ornek', 'CANLI', ''),
    ('test_xfail_ornek', 'OLU', 'xfail'),
    ('test_skip_ornek', 'OLU', 'skip'),
    ('test_bos_govde_ornek', 'OLU', 'gövdesi boş'),
    ('OrnekOluSinif', 'OLU', 'üyeleri ölü'),
    ('OrnekCanliSinif', 'CANLI', ''),
    ('OrnekUyesizSinif', 'OLU', 'üyesi yok'),
    ('HicBoyleBirAdYok', 'YOK', 'tanımlı değil'),
])
def test_oh_d19_26_c_canlilik_sondasi_olu_bekciyi_ayirt_ediyor(ad, beklenen,
                                                               ipucu):
    """Sonda numunelerde ölçülür: isim VAR ama hüküm YOKsa 'OLU' demeli."""
    assert (kanit_gerekli(KOK / NUMUNE)).is_file(), NUMUNE
    durum, gerekce = _sonda()(kanit_gerekli(NUMUNE), ad)
    assert durum == beklenen, (ad, durum, gerekce)
    if ipucu:
        assert ipucu in gerekce, (ad, gerekce)


def test_oh_d19_26_c_envanter_metin_aramasina_donmedi():
    """Kilit AST ile ölçülmeli; ``'def X' in metin`` biçimi geri gelmesin."""
    kaynak = oku(KOK / 'tests' / 'test_d17_bekci_cevirisi_a1.py')
    assert '_bekci_canliligi' in kaynak
    # Eski deyim ANLATILDIĞI yerde (docstring/yorum) sayılmaz; yalnız
    # ÇALIŞAN kodda geri gelirse kırmızı.
    kod = re.sub(r'"""[\s\S]*?"""', '', kaynak)
    kod = '\n'.join(x for x in kod.split('\n')
                    if not x.lstrip().startswith('#'))
    assert "f'def {ad}' in metin" not in kod, (
        'adres kilidi yine metin aramasına düşmüş')
    # Envanterin kendisi de ölü adres taşımıyor (bugünkü 9 adres canlı).
    from tests.test_d17_bekci_cevirisi_a1 import OH_Z402_BORCLARI
    sonda = _sonda()
    olu = [f'{d}::{a} ({sonda(d, a)[1]})'
           for adresler in OH_Z402_BORCLARI.values()
           for d, a in adresler if sonda(d, a)[0] == 'OLU']
    assert not olu, olu


# ---------------------------------------------------------------------------
# OH-D19-26 (f) — sözlük taramasındaki yorum kaçağı
# ---------------------------------------------------------------------------
#: ÖLÇÜLEN hayalet anahtarlar: bütün i18n*.js parçalarının BİRLEŞİMİNDE
#: yalnız YORUMDA geçiyorlar (once_kalan.json, K2.birlesim). Dosya
#: düzeyinde üç aday vardı; ``app.rep.webThickness`` i18n_common.js'te
#: GERÇEK bir anahtardır (i18n_pages.js'te yalnız ona ATIF yapan bir
#: yorum var), o yüzden hayalet değildir — sonda birleşime bakar.
HAYALET_ANAHTARLAR = ('panel.pc', 'panel.thrust')


def test_oh_d19_26_f_yorum_kacagi_kapandi():
    sys.path.insert(0, str(KOK))
    from tests import test_d17_electron_a1 as el
    assert hasattr(el, 'maske_yorum'), 'yorum maskesi sökülmüş'
    tanimli = el.sozlukler()
    sizan = [k for k in HAYALET_ANAHTARLAR if k in tanimli]
    assert not sizan, (
        'yalnız yorumda geçen anahtarlar hâlâ "tanımlı" sayılıyor: %s' % sizan)
    # Maske sözlüğü BOŞALTMASIN: gerçek anahtarlar duruyor.
    assert len(tanimli) > 3000, len(tanimli)
    for gercek in ('liq.js.row_material', 'update.available'):
        assert gercek in tanimli, gercek


def test_oh_d19_26_f_hayalet_anahtarlar_gercekten_yorumdaydi():
    """Mandal bayatlamasın: numune anahtarlar HİÇBİR parçada TANIMLI değil,
    ama ham metinde (yorumda) geçiyorlar — yani sonda gerçek bir kaçağı
    ölçüyor, uydurma bir kaçağı değil."""
    sys.path.insert(0, str(KOK))
    from tests import test_d17_electron_a1 as el
    ham, temiz = set(), set()
    desen = re.compile(r"'([A-Za-z0-9_.]+)':\s*'")
    for yol in sorted(JS.glob('i18n*.js')):
        metin = oku(yol)
        ham |= set(desen.findall(metin))
        temiz |= set(desen.findall(el.maske_yorum(metin)))
    for k in HAYALET_ANAHTARLAR:
        assert k in ham, (
            '%s ham metinden de kalkmış — HAYALET_ANAHTARLAR bayat' % k)
        assert k not in temiz, (
            '%s artık gerçek bir anahtar — HAYALET_ANAHTARLAR listesini '
            'güncelleyin' % k)
    assert (ham - temiz) == set(HAYALET_ANAHTARLAR), (
        'yorum kaçağı kümesi değişti: %s' % sorted(ham - temiz))


# ---------------------------------------------------------------------------
# OH-D19-26 (a,b,e,h) — ÖLÇÜMLE ÇÜRÜTÜLEN ayaklar (kilitlenir)
# ---------------------------------------------------------------------------
def test_oh_d19_26_a_ceviri_borcu_ailesi_bos_kaldi():
    """(a) 'shell.' borcu D27'de ödendi; liste yeniden doldurulmasın."""
    sys.path.insert(0, str(KOK))
    from tests.test_i18n_common import CEVIRI_BORCU_AILELERI as aileler
    assert aileler == (), (
        'çeviri borcu ailesi yeniden açılmış: %s — borç imi değil, '
        'gerçek çeviri eksiği olarak onarın' % (aileler,))


def test_oh_d19_26_b_band_tavani_literal_degil_tablodan():
    """(b) TestOHZ516 eşiği kanonik tablodan okur; 500 literali kilit değil."""
    kaynak = oku(KOK / 'tests' / 'test_d17_bekci_cevirisi_a1.py')
    govde = kaynak[kaynak.index('class TestOHZ516'):]
    govde = govde[:govde.index('\nclass ', 10)]
    assert '_kanonik_tavan' in govde
    kod = '\n'.join(s for s in govde.split('\n')
                    if not s.lstrip().startswith('#'))
    kod = re.sub(r'"""[\s\S]*?"""', '', kod)
    assert not re.search(r'==\s*500(?:\.0)?\b', kod), (
        'band tavanı yine literalle kilitlenmiş')


def test_oh_d19_26_e_yayin_kapisi_gercekten_sekiz_adim():
    """(e) '8/8' beyanı bayat DEĞİL: kapının en büyük adım imi 8."""
    gate = oku(KOK / 'packaging' / 'release_gate.sh')
    adimlar = sorted({int(x) for x in re.findall(r'(\d)/8\b', gate)})
    assert adimlar, 'kapıda adım imi kalmamış — beyan artık ölçülemez'
    assert max(adimlar) == 8, (
        'kapı %d adıma inmiş; manifest testindeki "8/8" beyanı bayatladı'
        % max(adimlar))


@pytest.mark.parametrize('dosya', ['tests/test_d17_bekci_cevirisi_a1.py',
                                   'tests/test_analysis_dock_contract.py'])
def test_oh_d19_26_gh_sarkan_kanit_atfi_yok(dosya):
    """(g,h) Bekçi yorumundaki kanıt yolu ya VAR ya 'YOK' diye beyanlı."""
    sarkan = []
    for satir in oku(KOK / dosya).split('\n'):
        for yol in re.findall(r'``(docs/scofield/raw/[^`]+)``', satir):
            # Yol METİNDEN çıkarılır (dinamik): kapı elle; 'YOK' beyanı önce.
            if 'YOK' in satir or kanit_gerekli(KOK / yol).exists():
                continue
            sarkan.append(yol)
    assert not sarkan, '%s: beyansız sarkan atıf %s' % (dosya, sarkan)


# ---------------------------------------------------------------------------
# OH-Z3-04 — kalan iki ayak (ölçüm: K7)
# ---------------------------------------------------------------------------
def test_oh_z3_04_msg_patterns_note_ve_geometry_kapsiyor():
    """Defterin adıyla andığı NOTE:/GEOMETRY: satırları TR'ye geçmeli."""
    charts = oku(JS / 'i18n_charts.js')
    mp = charts[charts.index('var MSG_PATTERNS = ['):]
    mp = mp[:mp.index('\n    ];')]
    assert len(re.findall(r'\[/\^NOTE:', mp)) >= 3, 'NOTE: kuralları eksildi'
    assert len(re.findall(r'\[/\^GEOMETRY:', mp)) >= 1, 'GEOMETRY: kuralı yok'
    assert len(re.findall(r'^\s*\[/\^', mp, re.M)) >= 100, 'kural sayısı düştü'


def test_oh_z3_04_warning_identity_tek_kaynaktan_geliyor():
    """`_warning_identity` tek-kaynak borcu ÖDENDİ (ÖH D30 · katı a1).

    D29'daki hâli: mandal borcun BÜYÜMESİNİ engelliyordu ve METİN
    taramasıyla ölçüyordu — dosyada `_warning_identity` DİZGESİ geçiyor
    mu diye bakıyordu. Docstring'i "küçülürse (tek kaynağa inerse) mandal
    da güncellenmelidir" diyordu; borç D30'da ödendi ve mandal bayatladı:
    iki motor artık tek tanımı İTHAL ettiği için dizge iki dosyada da
    geçmeye devam ediyor, yani eski mandal ödenmiş borcu "iki kopya var"
    diye okuyordu. SAYI YÜKSELTİLMEZ/DÜŞÜRÜLMEZ; ölçü İLİŞKİYE çevrildi
    (D26 dersi 8): kaç dosyada geçtiği değil, iki motorun AYNI nesneyi
    paylaşıp paylaşmadığı ölçülür.

    Ürün ayağının ölçümü ve ters mutasyonu:
    docs/scofield/raw/OH/D30/kati/a1/{once,sonra,mutasyon}.json
    Tam bekçisi: tests/test_d30_kati_a1.py::TestOHZ304WarningIdentityTekKaynak
    """
    from hrma.engines import hybrid_rocket_engine as _hib
    from hrma.engines import solid_rocket_engine as _kati
    from hrma.engines import warning_records as _tek

    assert _kati._warning_identity is _tek.warning_identity
    assert _hib._warning_identity is _tek.warning_identity
    assert _kati._warning_identity is _hib._warning_identity, (
        'iki motor yeniden ayrı kopyalara düştü — tek-kaynak borcu geri geldi')
    # Defterin andığı üçüncü ayak (solid.html) D29'da ölçülüp çürütülmüştü:
    # şablondaki işlev `warningIdentity` adındadır ve JS aynasıdır.
    assert '_warning_identity' not in oku(KOK / 'hrma/templates/solid.html')
