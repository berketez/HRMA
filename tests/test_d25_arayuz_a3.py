"""ÖH D25 · arayuz · aşama 3 — 11 kalemin bekçisi.

Kapsam (defter kimlikleriyle):
  P11B2-20  Analiz Merkezi'nde biten koşum görüntüleyiciyi KAÇIRMAZ
  P11B2-22  app.js'teki ölü ikinci ``updateInjectorParams`` kaldırıldı,
            dosyanın kendi yorumu ölçümle düzeltildi
  P11B2-23  Swirl raporunda ham kayan nokta yok; swirl alanları TABLOYA girer
  P11B3-03  ``rounds`` mesh sayısı değil İNCELTME sayısıdır (bire bir kayma)
  P11B3-05  ``quality.worst`` okunur; en kötü elemanın ÖLÇÜSÜ ekrandadır
  P11B3-08  h_g oranının TERSİ (kaç kat düşük) ekrandadır
  P11B3-09  ``viscous.grid_quality`` bloğu ekrandadır
  P11B3-10  ``separation.not_modelled`` (9 kalem) ekrandadır
  P11B3-11  Merkez satır hükümleri: CFD ayrılmayı, yapısal emniyet
            katsayısını görür
  P11B3-12  Tane panelinde harita (düğüm) tepe değeri + Gauss/düğüm künyesi
  P11B3-14  Em tire disiplini ham String()/şablon yolunda da uygulanır

Ölçüm yöntemi: JS grep DEĞİL — gerçek panel dosyaları ``node`` içinde küçük
bir taklit DOM ile BÜTÜN olarak koşturulur (kalıp:
tests/test_analysis_center_contract.py, tests/test_fea_panel.py). Kaynak
düzeyinde sayılan tek şey ölü kod ve yanlış yorumdur (P11B2-22) — onların
"davranışı" yoktur.

Koşum (süit disiplini):
    python3 -m pytest tests/test_d25_arayuz_a3.py -q
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
APP_JS = KOK / 'hrma/static/js/app.js'
ADV = KOK / 'hrma/templates/advanced.html'
CFD_JS = KOK / 'hrma/static/js/panels/cfd_panel.js'
FEA_JS = KOK / 'hrma/static/js/fea_panel.js'
CENTER_JS = KOK / 'hrma/static/js/analysis_center.js'
I18N_COMMON = KOK / 'hrma/static/js/i18n_common.js'
I18N_PAGES = KOK / 'hrma/static/js/i18n_pages.js'
SOLID = KOK / 'hrma/templates/solid.html'
OLCUM = KOK / 'docs/scofield/raw/OH/D25/arayuz/a3/olcum.py'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def oku(p):
    return p.read_text(encoding='utf-8')


def kodu(p):
    """Yorum satırları çıkarılmış kaynak — künyeler eski kusurun desenini
    alıntılar, bekçi yalnız ÇALIŞAN kodu ölçer."""
    return '\n'.join(l for l in oku(p).splitlines()
                     if not l.lstrip().startswith('//'))


@pytest.fixture(scope='module')
def olcum():
    """a3/olcum.py'yi bu ağaç üstünde koşturur (ölçüm betiği = bekçi girdisi).

    Betiğin kendisi kanıt dizinindedir ve 'önce/sonra' sayılarını üreten
    betikle AYNIDIR: bekçi ile rapor aynı ölçüme bakar, ayrışamazlar.
    """
    if NODE is None:
        pytest.skip('node kurulu değil')
    proc = subprocess.run(['python3', kanit_gerekli(str(OLCUM)), str(KOK)],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, 'olcum.py çöktü:\n' + proc.stderr[-3000:]
    veri = json.loads(proc.stdout)
    assert 'HATA' not in veri, veri.get('HATA')
    return veri


# ---------------------------------------------------------------------------
# P11B2-20 — biten koşum görüntüleyiciyi kaçırmaz
# ---------------------------------------------------------------------------
@needs_node
class TestP11B220GoruntuleyiciKacirmaz:
    def test_capraz_gosterim_yok(self, olcum):
        """Kart B'yi gösterirken görüntüleyici A'nın sonucunu basamaz."""
        d = olcum['p11b2_20']
        assert d['capraz_gosterim'] == 0, (
            'Biten koşum görüntüleyiciyi kaçırdı: kart bir analizi, '
            'görüntüleyici başkasını gösteriyor')
        assert d['goruntuleyici_A_gosteriyor'] == 0

    def test_secim_korunur(self, olcum):
        d = olcum['p11b2_20']
        assert d['secim_kosum_sonrasi'] == d['secim_kosum_sirasinda'], \
            'Koşum bitince kullanıcının seçimi değişti'

    def test_biten_kosum_adiyla_beyan_edilir(self, olcum):
        """Sessizce yutulmaz: durum satırı hangi analizin bittiğini söyler."""
        d = olcum['p11b2_20']
        assert 'CFD-A' in d['durum_satiri'], (
            'Ayrılınan satırda biten koşum durum satırında ADIYLA geçmiyor: '
            + d['durum_satiri'])

    def test_kosum_gecmiste_durur(self, olcum):
        """Görüntüleyiciye atlamamak SİLMEK değildir."""
        assert olcum['p11b2_20']['gecmis'] == ['nozzle_flow.cfd']

    def test_kaynak_kapiyi_kosula_bagliyor(self):
        kaynak = kodu(CENTER_JS)
        assert 'viewerFollowed' in kaynak, \
            'pushEntry biten koşumun izlenip izlenmediğini taşımıyor'
        assert re.search(r'if\s*\(halaSecili\)\s*viewingEntryId', kaynak), \
            'viewingEntryId hâlâ koşulsuz atanıyor'

    def test_yeni_beyan_anahtarlari_iki_dilde(self):
        s = oku(I18N_COMMON)
        for k in ('ac.run.doneOther', 'ac.run.errorOther'):
            assert s.count("'%s'" % k) == 2, \
                '%s anahtarı EN+TR bloklarının ikisinde birden yok' % k


# ---------------------------------------------------------------------------
# P11B2-22 — ölü ikinci updateInjectorParams
# ---------------------------------------------------------------------------
class TestP11B222OluKopya:
    def test_app_js_ikinci_tanimi_tasimaz(self, ):
        assert 'function updateInjectorParams' not in kodu(APP_JS), \
            'app.js hâlâ ikinci (gölgelenen) updateInjectorParams taşıyor'

    def test_sablonun_kopyasi_yerinde(self):
        assert oku(ADV).count('function updateInjectorParams') == 1, \
            'Şablonun GERÇEK kopyası kayboldu'

    def test_cagrilar_fail_closed(self):
        """Tanım yoksa çağrı sessizce atlanır — uydurma alan basılmaz.

        Şablonun inline sürümü yüklenmemişse (app.js'i tanımsız bir sayfa
        yüklerse) çağrı ReferenceError fırlatırdı; her çağrı bir typeof
        kapısıyla eşleşmelidir.
        """
        kaynak = kodu(APP_JS)
        # V301/T-ÇAPA-D: T-ÇAPA-C2 (1e78c9666) dil değişimi çağrısını
        # ``updateInjectorParams(true)`` yaptı (alanları boşaltmayan kip);
        # argümanlı çağrı da çağrıdır — sayım argümandan bağımsız.
        cagri = len(re.findall(r'(?<![\w.])updateInjectorParams\([^)]*\)',
                               kaynak))
        kapi = kaynak.count("typeof updateInjectorParams === 'function'")
        assert cagri >= 2, 'çağrı hiç kalmadı (kapsam kaydı)'
        assert kapi == cagri, (
            '%d çağrıya karşılık %d typeof kapısı var — korumasız çağrı kaldı'
            % (cagri, kapi))

    def test_yanlis_yorum_duzeltildi(self):
        s = oku(APP_JS)
        assert not re.search(
            r"liquid\.html ve solid\.html app\.js'i (?:yukler|yükler)", s), \
            'Yorum hâlâ liquid/solid app.js yükler diyor (ölçüm: yüklemiyor)'
        assert 'HİÇ yüklemez' in s, 'Ölçülen gerçek yorumda yazmıyor'

    def test_olu_kopyanin_anahtarlari_sozlukten_de_gitti(self):
        """Ölü kodun çevirisi de ölüdür (depo şartı:
        test_i18n_common.py::test_every_dictionary_key_is_used)."""
        sozluk = oku(I18N_COMMON)
        assert "'app.inj." not in sozluk, \
            'app.inj.* kayıtları sözlükte duruyor (öksüz çeviri)'
        assert "'app.rep.sprayAngle'" not in sozluk, \
            'halefi (sprayAngleFull) gelen eski etiket sözlükte kaldı'
        assert "'app.rep.sprayAngleFull'" in sozluk

    def test_olcum_gercegi_hala_gecerli(self):
        """Yorum ile depo gerçeği ayrışamaz: app.js'i YALNIZ advanced yükler."""
        yukleyen = sorted(p.name for p in (KOK / 'hrma/templates').glob('*.html')
                          if 'js/app.js' in oku(p))
        assert yukleyen == ['advanced.html'], yukleyen


# ---------------------------------------------------------------------------
# P11B2-23 — swirl: ham kayan nokta + eksik tablo alanları
# ---------------------------------------------------------------------------
class TestP11B223Swirl:
    def test_ham_kayan_nokta_basilmaz(self, ):
        assert not re.search(r'\$\{\s*injectorData\.spray_angle\s*\}',
                             kodu(APP_JS)), \
            'spray_angle hâlâ yuvarlanmadan basılıyor (90.00000000000001°)'

    def test_aci_basici_tek_kaynak(self):
        kaynak = kodu(APP_JS)
        assert 'function aciBas(' in kaynak
        assert kaynak.count('const ACI_BASAMAK') == 1, \
            'Açı basamağı ikinci bir yerde tanımlanmış (tek kaynak kuralı)'

    def test_aci_basici_yuvarlar_ve_eksigi_beyan_eder(self):
        """Davranış: node'da koşturulur — 90.00000000000001 -> 90.00°."""
        if NODE is None:
            pytest.skip('node kurulu değil')
        kaynak = kodu(APP_JS)
        i = kaynak.index('const ACI_BASAMAK')
        j = kaynak.index('\n}', kaynak.index('function aciBas(', i)) + 2
        # ÖH D35 · OH-GT-25: `aciBas` artık ayracı ortak `numTxt`
        # delegatörüne soruyor (i18n.js kanonu). Yalıtılmış koşumda o da
        # yanında olmalı; KOPYA YAZILMAZ — app.js'ten sökülür, tek kaynak
        # üründe kalır. `window` burada tanımsız olduğundan delegatör
        # `toFixed` dalına düşer ve bu testin iddiaları ('90.00°')
        # AYNEN geçerlidir.
        ni = kaynak.index('function numTxt(')
        nj = kaynak.index('\n}', ni) + 2
        betik = (kaynak[ni:nj] + kaynak[i:j]
                 + "\nconsole.log(JSON.stringify([aciBas(90.00000000000001),"
                   " aciBas(undefined), aciBas(null), aciBas('x'),"
                   " aciBas(0)]));")
        p = subprocess.run([NODE], input=betik, capture_output=True,
                           text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        assert json.loads(p.stdout) == ['90.00°', '—', '—', '—', '0.00°']

    def test_tablo_swirl_dalini_tasir(self, ):
        kaynak = kodu(APP_JS)
        i = kaynak.index('function displayInjectorTable(')
        blok = kaynak[i:kaynak.index('\n}', i)]
        for alan in ('n_slots', 'slot_width', 'slot_height', 'spray_angle',
                     'spray_half_angle_deg', 'film_thickness_mm'):
            assert alan in blok, '%s swirl alanı tabloya girmiyor' % alan

    def test_tam_ve_yari_aci_ayrik_etiketlenir(self):
        """Çözücü spray_angle'ı TAM koni açısı (2θ) diye tanımlıyor."""
        kaynak = kodu(APP_JS)
        assert 'app.rep.sprayAngleFull' in kaynak
        assert 'app.rep.sprayHalfAngle' in kaynak
        cozucu = oku(KOK / 'hrma/utils/injector_design.py')
        assert "'spray_angle': float(2.0 * theta_half)" in cozucu, \
            'Çözücü sözleşmesi değişmiş; etiket yeniden ölçülmeli'

    def test_yeni_etiketler_iki_dilde(self):
        s = oku(I18N_COMMON)
        for k in ('app.rep.sprayAngleFull', 'app.rep.sprayHalfAngle',
                  'app.rep.filmThickness', 'app.rep.slotVelocity',
                  'app.rep.atomizerK', 'app.rep.airCoreX',
                  'app.rep.swirlChamberSource', 'app.rep.cdBasis'):
            assert s.count("'%s'" % k) == 2, '%s iki dilde yok' % k


# ---------------------------------------------------------------------------
# P11B3-03 — 'tur' sayısı bire bir kayıyordu
# ---------------------------------------------------------------------------
@needs_node
class TestP11B303InceltmeTuru:
    """Kusur SAYININ YANLIŞLIĞI değil, ADININ BELİRSİZLİĞİdir.

    Ucun kendi beyan üreticisi de MESH sayısını 'tur' der
    (hrma/fea/structural_axisym.py:1203), katlama sayacı ise inceltme
    ADIMLARINI sayar; ilk mesh bir adım değildir, dolayısıyla katlama =
    mesh - 1. Paneldeki sayıyı kaydırmak çelişkiyi ÇÖZMEZ, yön
    değiştirir (rozet 3 derken hemen altta AYNEN basılan uç beyanı
    '4 turda' derdi). Bekçi: iki büyüklük ayrı adla taşınır ve ekranda
    ADIYLA yazılır.
    """

    def test_iki_buyukluk_ayri_adla_tasinir(self, olcum):
        d = olcum['p11b3_03']
        assert d['mesh_sayisi'] == 4
        assert d['panelin_bastigi_rounds'] == 4, (
            "Rozetin 'tur' sayısı ucun sözleşmesinden (mesh sayısı) "
            'ayrıldı: %r' % d)
        assert d['panelin_bastigi_refinements'] == d['katlama_sayisi_gercek'] == 3, (
            'İnceltme adımı sayısı ucun katlama sayacıyla eşleşmiyor: %r' % d)

    def test_ekranda_ikisinin_de_ne_oldugu_yaziyor(self, olcum):
        d = olcum['p11b3_03']
        assert d['aciklama_ekranda'] == 1, (
            'Not satırı 4 ile 3’ün ne olduğunu ADIYLA söylemiyor: %r'
            % d['not_metni'][:200])

    def test_inceltme_cumlesi_adim_sayisini_basar(self, olcum):
        """'refinement rounds' diyen cümle ADIM sayısını basmalı (3), mesh
        sayısını (4) değil — cümle kendi adına doğru olmalı."""
        nt = olcum['p11b3_03']['not_metni']
        assert 'Converged in 3 refinement rounds' in nt, nt[:200]

    def test_merkez_satiri_ucun_sozlesmesini_korur(self, olcum):
        d = olcum['p11b3_03']
        assert d['merkez_rounds'] == d['panelin_bastigi_rounds'] == 4, \
            'Merkez satırı ile panel ayrı sayı basıyor'

    def test_kaynak_iki_alani_da_tasiyor(self):
        kaynak = kodu(FEA_JS)
        assert re.search(r'meshes:\s*meshSayisi', kaynak)
        assert re.search(r'rounds:\s*meshSayisi,', kaynak), \
            "rounds ucun 'tur' sözleşmesinden (mesh sayısı) ayrılmış"
        assert re.search(
            r'refinements:\s*meshSayisi\s*>\s*0\s*\?\s*meshSayisi\s*-\s*1',
            kaynak), 'inceltme adımı sayısı ayrı alanda taşınmıyor'

    def test_tek_meshli_kosum_yutulmaz(self):
        """Kapılar `meshes`e bakar: tek meshli koşumda hüküm kaybolmaz."""
        kaynak = kodu(FEA_JS)
        assert 'if (!conv || !conv.meshes) return null;' in kaynak
        assert 'if (conv && conv.meshes) {' in kaynak
        assert 'if (conv && conv.rounds)' not in kaynak


# ---------------------------------------------------------------------------
# P11B3-05 — en kötü elemanın ölçüsü ekranda
# ---------------------------------------------------------------------------
@needs_node
class TestP11B305EnKotuEleman:
    def test_worst_alani_okunur(self, olcum):
        assert olcum['p11b3_05']['worst_alani_okunuyor'] == 1, \
            'quality.worst hâlâ görünüm modeline girmiyor'

    def test_sayi_ve_esik_kati_ekranda(self, olcum):
        d = olcum['p11b3_05']
        assert d['en_kotu_ar_ekranda'] == 1, \
            'en kötü en-boy oranı (368,72) rozetlerde yok'
        assert d['esik_kati_ekranda'] == 1, \
            'eşiğin kaç katı olduğu (92,2) ekranda yok'

    def test_oran_uydurulmaz(self):
        """Eşik yayımlanmadıysa oran da YOKTUR."""
        kaynak = kodu(FEA_JS)
        assert re.search(r'aspect_over_threshold:\s*\(wAr !== null '
                         r'&& arMax !== null && arMax !== 0\)', kaynak)

    def test_rozet_iki_panelde_de_bagli(self):
        """Politika tek yerde (qualityBadges), METİN her iki kiracıda."""
        kaynak = kodu(FEA_JS)
        assert kaynak.count("metin('badgeWorstQuality'") == 1, \
            'rozet politikası ikiye ayrılmış (tek kaynak kuralı)'
        assert kaynak.count("ad === 'badgeWorstQuality'") == 2, \
            'iki kiracıdan biri rozeti kendi cümlesiyle bağlamıyor'
        assert "TF('fea.badgeWorstQuality'" in kaynak
        assert "GL('badgeWorstQuality'" in kaynak

    def test_etiketler_iki_dilde_ve_solid_saglayicisinda(self):
        assert oku(I18N_COMMON).count("'fea.badgeWorstQuality'") == 2
        assert oku(I18N_PAGES).count("'solid.fea.badge_worst_quality'") == 2
        assert 'badgeWorstQuality:' in oku(SOLID)


# ---------------------------------------------------------------------------
# P11B3-08 — oranın TERSİ ekranda
# ---------------------------------------------------------------------------
@needs_node
class TestP11B308TersOran:
    def test_ters_oran_satiri_var(self, olcum):
        d = olcum['p11b3_08']
        assert d['oran_satiri_var'] == 1, 'kaynak satır kayboldu'
        assert d['ters_oran_satiri_var'] == 1, \
            'h_g(Bartz)/h_g(CFD) satırı ekranda yok'

    def test_kac_kat_dusuk_ekranda(self, olcum):
        assert olcum['p11b3_08']['ters_sayi_ekranda'] == 1, \
            'boğazdaki 1/0,0125 = 80 kat ekranda yok'

    def test_panel_kendi_kabul_bandini_uydurmaz(self):
        """Bant SAYISI panelde tanımlı olamaz — bandı yalnız ucun künyesi
        beyan eder (kalibrasyon uydurma yasağı)."""
        kaynak = kodu(CFD_JS)
        i = kaynak.index('rowHgRatioInverse')
        blok = kaynak[i - 2000:i + 3000]
        assert not re.search(r'\b1\.45\b|\b2\.68\b', blok), \
            'Panel kaynağına sayısal kabul bandı sızmış'

    def test_sifir_ve_negatif_oranda_ters_alinmaz(self):
        kaynak = kodu(CFD_JS)
        assert re.search(r'return \(isNum\(x\) && x > 0\) \? fmtAuto\(1 / x, 3\)'
                         r' : .—.;', kaynak)

    def test_anahtarlar_iki_dilde(self):
        s = oku(I18N_COMMON)
        for k in ('panel.cfd.rowHgRatioInverse', 'panel.cfd.hgRatioInverseNote'):
            assert s.count("'%s'" % k) == 2, '%s iki dilde yok' % k


# ---------------------------------------------------------------------------
# P11B3-09 — grid_quality ekranda
# ---------------------------------------------------------------------------
@needs_node
class TestP11B309IzgaraKalitesi:
    def test_blok_ekranda(self, olcum):
        d = olcum['p11b3_09']
        assert d['gridquality_basligi'] == 1, 'ızgara kalitesi başlığı yok'
        assert d['skew_ekranda'] == 1, 'maks duvar çarpıklığı (41,7°) yok'

    def test_ucun_okunma_sarti_cumlesi_ekranda(self, olcum):
        assert olcum['p11b3_09']['gridquality_basis_ekranda'] == 1, \
            'ucun "q_w iddiasının okunma şartıdır" künyesi basılmıyor'

    def test_gridQuality_artik_olu_degil(self):
        kaynak = kodu(CFD_JS)
        assert kaynak.count('gridQuality') >= 2, \
            'gridQuality yine yalnız tanım satırında geçiyor (ölü katman)'

    def test_blok_yoksa_bolum_cizilmez(self):
        kaynak = kodu(CFD_JS)
        i = kaynak.index('function gridQualityHtml(')
        assert "if (!gq || typeof gq !== 'object') return '';" \
            in kaynak[i:i + 400], 'blok yokken boş bölüm çiziliyor'


# ---------------------------------------------------------------------------
# P11B3-10 — ayrılmanın kendi not_modelled listesi
# ---------------------------------------------------------------------------
@needs_node
class TestP11B310AyrilmaKapsami:
    def test_dokuz_kalem_ekranda(self, olcum):
        d = olcum['p11b3_10']
        assert d['ayrilma_notmodelled_sayisi'] == 9, \
            'ayrılmanın 9 kalemlik kapsam beyanı eksik: %r' % d
        assert d['side_loads_ekranda'] == 1, 'yanal yükler maddesi ekranda yok'

    def test_criteria_blogundan_bagimsiz(self):
        """Ölçüt üyeleri yayımlanmayan koşuda da kapsam yazılmalı."""
        kaynak = kodu(CFD_JS)
        assert 'function separationNotModelledHtml(' in kaynak
        assert 'separationNotModelledHtml(vm)' in kaynak

    def test_bos_blokta_baslik_basilmaz(self):
        kaynak = kodu(CFD_JS)
        i = kaynak.index('function separationNotModelledHtml(')
        assert 'Object.keys(yok).length' in kaynak[i:i + 500]

    def test_anahtar_iki_dilde(self):
        assert oku(I18N_COMMON).count("'panel.cfd.sepNotModelled'") == 2


# ---------------------------------------------------------------------------
# P11B3-11 — üç kiracının satır hükmü
# ---------------------------------------------------------------------------
@needs_node
class TestP11B311SatirHukmu:
    def test_ayrilan_kosum_yesil_degil(self, olcum):
        d = olcum['p11b3_11']
        assert d['cfd_hukum_kind'] == 'warn', (
            'Ayrılma öngören CFD koşusu hâlâ YEŞİL satır alıyor: %r'
            % d['cfd_hukum_kind'])
        assert 'SEPARATION' in d['cfd_hukum_metni']

    def test_yapisal_hukum_emniyet_katsayisini_gorur(self, olcum):
        d = olcum['p11b3_11']
        assert d['yapisal_hukum_kind'] == 'err', (
            'SF 0,87 olan koşum satırda %r hükmü alıyor'
            % d['yapisal_hukum_kind'])
        assert d['yapisal_hukum_sf_gorunuyor'] == 1, \
            'Satır metninde emniyet katsayısı geçmiyor'

    def test_sf_esikleri_tek_kaynaktan(self):
        """Yeni eşik yok: sınıflama sfRozetTuru'dan (kontur skalasıyla aynı)."""
        kaynak = kodu(FEA_JS)
        i = kaynak.index('function acStructuralVerdict(')
        blok = kaynak[i:i + 3000]
        assert 'sfRozetTuru(hukumSf)' in blok
        assert not re.search(r'hukumSf\s*[<>]=?\s*\d', blok), \
            'Satır hükmüne elle eşik yazılmış'

    def test_en_kotu_sayi_hukmu_verir(self):
        kaynak = kodu(FEA_JS)
        i = kaynak.index('function acStructuralVerdict(')
        assert 'Math.min(kopruSf, motorSf)' in kaynak[i:i + 3000], \
            'Köprü ile motorun sayısından en kötüsü alınmıyor'

    def test_anahtarlar_iki_dilde(self):
        s = oku(I18N_COMMON)
        for k in ('panel.cfd.verdictConvergedSeparated',
                  'panel.fea.verdictConvergedUnsafe',
                  'panel.fea.verdictNotConvergedUnsafe'):
            assert s.count("'%s'" % k) == 2, '%s iki dilde yok' % k


# ---------------------------------------------------------------------------
# P11B3-12 — tane panelinde Gauss/düğüm ayrımı
# ---------------------------------------------------------------------------
@needs_node
class TestP11B312GaussDugum:
    def test_iki_tepe_deger_de_ekranda(self, olcum):
        d = olcum['p11b3_12']
        assert d['gauss_ekranda'] == 1, 'manşet (Gauss) rozeti kayboldu'
        assert d['nodal_ekranda'] == 1, \
            'haritanın çizildiği düğüm tepe değeri (0,1015 MPa) ekranda yok'

    def test_ayrim_kunyesi_basilir(self, olcum):
        assert olcum['p11b3_12']['gauss_dugum_kunyesi'] == 1, \
            'Gauss/düğüm ayrımını anlatan künye cümlesi tane panelinde yok'

    def test_hicbir_sayi_digerine_olceklenmez(self):
        kaynak = kodu(FEA_JS)
        i = kaynak.index("GL('badgeVmNodal'")
        assert 'von_mises_nodal_max_mpa' in kaynak[i - 200:i + 400]
        assert 'rescaled to match the other' in kaynak

    def test_etiketler_iki_dilde_ve_solid_saglayicisinda(self):
        s = oku(I18N_PAGES)
        assert s.count("'solid.fea.badge_vm_nodal'") == 2
        assert s.count("'solid.fea.gauss_note'") == 2
        assert 'badgeVmNodal:' in oku(SOLID)


# ---------------------------------------------------------------------------
# P11B3-14 — em tire disiplini
# ---------------------------------------------------------------------------
@needs_node
class TestP11B314EmTire:
    def test_asgari_yukte_sizinti_yok(self, olcum):
        d = olcum['p11b3_14']
        assert d['cfd_undefined'] == 0, \
            'CFD paneli asgari yükte %d kez undefined basıyor' % d['cfd_undefined']
        assert d['cfd_nan'] == 0

    def test_merkez_satiri_da_temiz(self, olcum):
        d = olcum['p11b3_14']
        assert d['merkez_satiri_undefined'] == 0, \
            'Merkez satır hükmü hâlâ "undefined iterations" basıyor'
        assert '—' in d['merkez_satiri']

    def test_txt_kapisi_tanimli_ve_tek(self):
        kaynak = kodu(CFD_JS)
        assert kaynak.count('function txt(v)') == 1

    def test_ham_String_yolu_kapatildi(self):
        """Rozet/satır şablonlarında çıplak vm alanı kalmamalı."""
        kaynak = kodu(CFD_JS)
        for desen in (r'\{ iters: vm\.iterations \}',
                      r'\{ backend: vm\.kernel \}',
                      r'\{ n: vm\.shockColumns \}',
                      r'String\(vm\.maxIterations\)',
                      r'String\(g\.resolution\)'):
            assert not re.search(desen, kaynak), \
                'em tire kapısından geçmeyen yol kaldı: ' + desen

    def test_txt_davranisi(self):
        if NODE is None:
            pytest.skip('node kurulu değil')
        kaynak = kodu(CFD_JS)
        i = kaynak.index('function txt(v)')
        j = kaynak.index('\n    }', i) + 6
        betik = (kaynak[i:j].replace('    function', 'function')
                 + "\nconsole.log(JSON.stringify([txt(undefined), txt(null),"
                   " txt(''), txt(0), txt(2915), txt('numpy')]));")
        p = subprocess.run([NODE], input=betik, capture_output=True,
                           text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        assert json.loads(p.stdout) == ['—', '—', '—', '0', '2915', 'numpy'], \
            'txt() sıfırı yutuyor ya da yokluğu beyan etmiyor'
