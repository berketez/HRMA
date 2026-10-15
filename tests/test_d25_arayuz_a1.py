"""ÖH Dalga-25 / arayuz aşama-1 bekçisi — defter kalemi **P11B2-12**.

Kalem: *"Sahte sayı yasağı" bekçisi JS dosyalarını hiç taramıyor; kendi
ölçütü app.js'e uygulandığında 13 kalem yanıyor (8'i gerçek uydurma).*

Onarım iki parçalıdır ve bölünemez:

**(a) Kapsam.** ``tests/test_ui_no_fabricated_numbers.py`` yalnız
``hrma/templates/*.html`` tarıyordu; ``hrma/static/js/**/*.js``
kapsamın tamamen dışındaydı (ölçüldü: ``bekci_js_tariyor = 0``).
Kapsam iki katmanda ve **glob ile türetilerek** açıldı: bütün betiklerde
iki gösterim deseni, gösterim katmanında (``app.js`` + panel ailesi)
ayrıca *çözücü-alanı sayısal yedeği*.

**(b) Uydurmalar.** Yeni ölçüt tabanda 12 kalem yakıyordu; 11'i onarıldı
(10'u ekrana çıkan gerçek uydurma, 1'i bekçiyi yanıltan gereksiz yedek),
1'i gerekçesiyle beyan defterine yazıldı.

Ölçüm: ``docs/scofield/raw/OH/D25/arayuz/a1/olcum.py`` →
``once.json`` (taban) / ``sonra.json`` (bu ağaç):
``bekci_js_tariyor`` 0 → 52, ``cozucu_alani_yedegi`` 12 → 1,
``beyansiz`` 12 → 0.

Bu dosya (b)'nin DAVRANIŞINI kilitler; (a)'nın kendisi genişletilen
bekçinin içindedir ve buradan da çapalanır.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest
from tests.support.kanit import kanit_gerekli

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = REPO_ROOT / 'hrma' / 'static' / 'js'
APP_JS = JS / 'app.js'
#: Parametrik taramanın CANLI yolu: `advanced.html` satır içi sürümü
#: (app.js kopyası D30 panel a1 / 896d2e83 ile SÖKÜLDÜ).
ADVANCED_HTML = REPO_ROOT / 'hrma' / 'templates' / 'advanced.html'

sys.path.insert(0, str(REPO_ROOT / 'tests'))
import test_ui_no_fabricated_numbers as BEKCI  # noqa: E402


def oku(rel):
    return (JS / rel).read_text(encoding='utf-8')


def app_fonksiyonu(ad):
    """app.js'teki üst düzey ``function AD(...)`` gövdesi."""
    src = APP_JS.read_text(encoding='utf-8')
    imza = '\nfunction %s(' % ad
    start = src.index(imza) + 1
    nxt = src.find('\nfunction ', start + 1)
    # Sondaki '\n': parçalar birleştirilirken bir sonraki `function` bildirimi
    # önceki parçanın son satır yorumuna yapışıp yorum içinde kalmasın.
    return src[start:nxt if nxt > 0 else len(src)] + '\n'


def node_kos(kaynak):
    """Verilen JS'i node'da koşturur; (returncode, stdout, stderr)."""
    fd, yol = tempfile.mkstemp(suffix='.js')
    os.write(fd, kaynak.encode('utf-8'))
    os.close(fd)
    try:
        proc = subprocess.run(['node', yol], capture_output=True, text=True,
                              timeout=60)
    finally:
        os.unlink(yol)
    return proc.returncode, proc.stdout, proc.stderr


#: ÖH D35 · OH-GT-25 — app.js'in ekran sayıları artık ortak `numTxt`
#: delegatöründen geçiyor (i18n.js kanonu). Bu önbilgi sayfanın AMBİYANS
#: bağımlılıklarını taklit ediyor (`T` gibi); delegatör de onlardan biri.
#: KOPYA YAZILMAZ — app.js'ten sökülür, tek kaynak üründe kalır. Burada
#: `window` tanımsız olduğundan delegatör eski `toFixed` dalına düşer ve
#: bu dosyanın sayısal iddiaları ('1200.0 cm³') AYNEN geçerli kalır.
ONBILGI = """
const T = (key, en) => en;
const fail = [];
const ok = (cond, msg) => { if (!cond) fail.push(msg); };
""" + app_fonksiyonu('numTxt')
SONBILGI = """
if (fail.length) { console.log(fail.join('\\n')); process.exit(1); }
console.log('OK');
"""

nodesiz = pytest.mark.skipif(shutil.which('node') is None, reason='node yok')


# ---------------------------------------------------------------------------
# (a) Kapsam — bekçi artık betikleri de görüyor
# ---------------------------------------------------------------------------
class TestBekciKapsamiJS:
    """P11B2-12'nin birinci yarısı: kapsam körlüğü kapandı mı?"""

    def test_betikler_kapsamda_ve_turetilmis(self):
        diskteki = {p.relative_to(REPO_ROOT).as_posix()
                    for p in JS.rglob('*.js')}
        assert diskteki, 'hrma/static/js altında betik yok — yol mu değişti?'
        assert set(BEKCI.SCANNED_SCRIPTS) == diskteki, (
            'bekçinin betik kapsamı diski yansıtmıyor (elle daraltılmış?):\n'
            '  taranan ama yok : %s\n  var ama taranmıyor: %s'
            % (sorted(set(BEKCI.SCANNED_SCRIPTS) - diskteki),
               sorted(diskteki - set(BEKCI.SCANNED_SCRIPTS))))
        assert 'hrma/static/js/app.js' in BEKCI.SCANNED_SCRIPTS

    def test_gosterim_katmani_bos_degil(self):
        assert 'hrma/static/js/app.js' in BEKCI.DISPLAY_LAYER
        paneller = [f for f in BEKCI.DISPLAY_LAYER if f.endswith('_panel.js')]
        assert len(paneller) >= 5, (
            'panel ailesi kapsamdan düştü: %d dosya' % len(paneller))
        assert set(BEKCI.DISPLAY_LAYER) <= set(BEKCI.SCANNED_SCRIPTS)

    def test_beyansiz_cozucu_alani_yedegi_kalmadi(self):
        """Gösterim katmanının tamamında beyansız yedek sayısı SIFIR."""
        beyanli = {(d, p) for d, p, _ in BEKCI.JS_BEYAN}
        artik = []
        for dosya in BEKCI.DISPLAY_LAYER:
            for ln, metin in BEKCI.js_solver_field_hits(dosya):
                if (dosya, metin) not in beyanli:
                    artik.append('%s:%d %s' % (dosya, ln, metin))
        assert not artik, 'beyansız çözücü-alanı yedeği: %s' % artik

    def test_beyan_defteri_gerekceli_ve_canli(self):
        """Her beyan kaydı gerekçeli ve kodda karşılığı olan olmalı.

        Defterin BOŞ olması yasak değildir — tersine, en iyi hâl odur:
        bir kayıt silinebiliyorsa kod düzelmiş demektir. Yasak olan,
        gerekçesiz ya da çürümüş kayıt tutmaktır.
        """
        for dosya, parca, gerekce in BEKCI.JS_BEYAN:
            assert len(gerekce.strip()) >= 40, (dosya, parca)
            assert parca in {m for _, m in BEKCI.js_solver_field_hits(dosya)}


# ---------------------------------------------------------------------------
# (b1) Yanma odası hacmi — "hesaplanmadı" ile "sıfır" aynı şey değil
# ---------------------------------------------------------------------------
class TestChamberHacmiFailClosed:

    @nodesiz
    def test_hacim_yoksa_sayi_uretilmiyor(self):
        kaynak = ONBILGI + app_fonksiyonu('isFiniteNum') \
            + app_fonksiyonu('chamberVolumeM3') \
            + app_fonksiyonu('chamberVolumeCm3Text') + """
// 1) Hiçbir hacim alanı yoksa null, ekranda RAKAM yok.
ok(chamberVolumeM3({}) === null, 'boş nesne için null dönmedi');
ok(chamberVolumeM3(null) === null, 'null motor için null dönmedi');
const bos = chamberVolumeCm3Text({});
ok(!/[0-9]/.test(bos), 'eksik hacim RAKAM üretti: ' + bos);
ok(bos.indexOf('not computed') >= 0, 'gerekçe metni yok: ' + bos);

// 2) Sıfır/negatif hacim fiziksel değil — uydurulmuş sıfır basılmaz.
ok(chamberVolumeM3({chamber_volume: 0}) === null, 'sıfır hacim sayı sayıldı');
ok(chamberVolumeM3({chamber_volume: -1}) === null, 'negatif hacim kabul edildi');
ok(!/[0-9]/.test(chamberVolumeCm3Text({chamber_volume: 0})),
   'sıfır hacim ekranda 0.0 cm3 oldu');

// 3) Gerçek değer bozulmadan geçiyor; öncelik actual > nominal.
ok(chamberVolumeM3({chamber_volume: 0.0012}) === 0.0012, 'nominal bozuldu');
ok(chamberVolumeM3({chamber_volume_actual: 0.002, chamber_volume: 0.001})
   === 0.002, 'actual önceliği bozuldu');
ok(chamberVolumeCm3Text({chamber_volume: 0.0012}) === '1200.0 cm³',
   'biçim bozuldu: ' + chamberVolumeCm3Text({chamber_volume: 0.0012}));

// 4) NaN / metin sayı üretmez.
[NaN, Infinity, 'n/a', undefined].forEach(bad => {
    ok(chamberVolumeM3({chamber_volume: bad}) === null,
       'bozuk değer sayı üretti: ' + String(bad));
});
""" + SONBILGI
        rc, out, err = node_kos(kaynak)
        assert rc == 0, 'hacim sözleşmesi bozuk:\n%s\n%s' % (out, err)

    def test_her_iki_tuketici_de_durust_metni_kullaniyor(self):
        """``* 1e6).toFixed(1)`` artık null'a körlemesine uygulanmıyor."""
        src = APP_JS.read_text(encoding='utf-8')
        assert 'chamberVolumeCm3Text(motorData)' in src, (
            'tasarım raporu dürüst metin yardımcısını kullanmıyor')
        assert '${(chamberVolumeM3(motorData) * 1e6).toFixed(1)} cm³' not in src, (
            'rapor tablosu yine null üstünde toFixed çağırıyor')
        tablo = app_fonksiyonu('displayMotorTable')
        assert 'chamberVolumeM3(motorData) === null' in tablo, (
            'displayMotorTable hesaplanmamış hacmi denetlemiyor')
        assert "T('common.notComputed'" in tablo


# ---------------------------------------------------------------------------
# (b2) Duş başlığı yerleşim uyarısı — eksik geometride uyarı UYDURULMAZ
# ---------------------------------------------------------------------------
class TestShowerheadUyarisiFailClosed:

    @nodesiz
    def test_eksik_delik_verisinde_uyari_uretilmiyor(self):
        kaynak = ONBILGI + app_fonksiyonu('isFiniteNum') \
            + app_fonksiyonu('validateAndFixInjectorDiameter') + """
function kos(inj) {
    const r = {motor: {chamber_diameter: 0.05}, injector: Object.assign(
        {type: 'showerhead'}, inj)};
    validateAndFixInjectorDiameter(r);
    return r.injector.warnings || [];
}

// 1) Delik sayısı YOK -> eskiden n=1, d=1 mm varsayılıp "~3.0 mm" yazılıyordu.
ok(kos({hole_diameter: 40}).length === 0,
   'delik sayısı olmadan uyarı üretildi: ' + JSON.stringify(kos({hole_diameter: 40})));
ok(kos({n_holes: 900}).length === 0, 'delik çapı olmadan uyarı üretildi');
ok(kos({}).length === 0, 'hiç geometri yokken uyarı üretildi');
ok(kos({n_holes: 0, hole_diameter: 2}).length === 0, 'sıfır delik kabul edildi');
ok(kos({n_holes: 'x', hole_diameter: 2}).length === 0, 'metin delik sayısı kabul edildi');

// 2) Geometri TAMSA uyarı yine çıkıyor (koruma sökülmedi).
const uyari = kos({n_holes: 100, hole_diameter: 3});
ok(uyari.length === 1, 'gerçek geometride uyarı kayboldu');
ok(uyari[0].indexOf('90%') >= 0, 'uyarı metni bozuldu: ' + uyari[0]);

// 3) Sığan geometride uyarı yok.
ok(kos({n_holes: 4, hole_diameter: 1}).length === 0, 'sığan desende uyarı çıktı');
""" + SONBILGI
        rc, out, err = node_kos(kaynak)
        assert rc == 0, 'duş başlığı kapısı bozuk:\n%s\n%s' % (out, err)


# ---------------------------------------------------------------------------
# (b3) Kesilen parametrik tarama sayaçları
# ---------------------------------------------------------------------------
class TestKesikTaramaSayaclari:
    """ÖH D31 fix-34b — BEKÇİ CANLI KAYNAĞA ÇEVRİLDİ (D30 dersi 18).

    P11B2-12 onarımı (D25, ``9d41eba8``) ``app.js``in parametrik
    kopyasına yazılmıştı. O kopya ÖLÜYDÜ: ``advanced.html``in satır içi
    sürümü hoisting ile kazanıyordu, ve D30 panel a1 (``896d2e83``)
    ölü kopyayı söktü. Bekçi söküleni ölçmeye devam edince kırmızıya
    döndü; ölçüm CANLI yola taşındı ve orada kusurun HÂLÂ DURDUĞU
    görüldü (``Number(kesik.points_started) || 0`` — uydurulmuş sıfır).
    Ürün fix-34b'de onarıldı; iddia AYNEN korunur.
    """

    #: Ekrandaki ileti anahtarı ⟷ ucun yayımladığı alan.
    SAYAC_BAGLARI = (
        ('attempted', 'kesik.points_started'),
        ('requested', 'results.points_requested'),
        ('not_attempted', 'kesik.points_not_attempted'),
    )

    def test_sayaclar_fail_closed(self):
        """ÖLÇÜT YAPISAL (ÖH D33 fix-36) — DİZE DEĞİL BAĞ ölçülür.

        Bekçi eskiden ``requested: sayac(results.points_requested)``
        dizesini ARIYORDU. ÖH D32 arayuz-panel a1 (577bb32d · OH-D31-07,
        hüküm-21 KABUL) ``sayac``ı TEK KAYNAĞA çıkarıp iki çağrı yerini
        ``const istenen = sayac(results.points_requested);`` ara değeriyle
        besledi — bağ GÜÇLENDİ, dize kayboldu, bekçi kırmızıya döndü
        (taban kaydı-16). Ölçüt artık bağın kendisi: alan ``sayac()``
        süzgecinden geçiyor mu, doğrudan mı basılıyor.
        """
        src = ADVANCED_HTML.read_text(encoding='utf-8')
        for eski in ('Number(kesik.points_started) || 0',
                     'Number(kesik.points_not_attempted) || 0'):
            assert eski not in src, (
                'kesilen tarama sayacı yine sıfır uyduruyor: %s' % eski)
        assert "const sayac = (v) => (isFiniteNum(v) ? v : '?');" in src, (
            "sayaçlar komşu budget_s ile aynı fail-closed sözleşmede değil")
        # TEK KAYNAK (OH-D31-07 kazanımı): ikinci bir sayac tanımı, kollar
        # sessizce ayrışırken sözleşmenin yarısını bayatlatır.
        assert src.count('const sayac =') == 1, (
            'sayac ikinci kez tanımlanmış — kollar ayrışabilir: %d'
            % src.count('const sayac ='))
        # ``const <ad> = sayac(<alan>);`` ara değerleri: ad → alan.
        bagli = dict(re.findall(
            r'const\s+([A-Za-z_$][\w$]*)\s*=\s*sayac\(\s*([\w.$]+)\s*\)\s*;',
            src))
        for anahtar, alan in self.SAYAC_BAGLARI:
            kabul = {'sayac(%s)' % alan}
            kabul.update(ad for ad, ifade in bagli.items() if ifade == alan)
            degerler = [d.strip() for d in re.findall(
                r'\b%s\s*:\s*([^,\n}]+)' % re.escape(anahtar), src)]
            assert degerler, 'ileti yükünde %s anahtarı yok' % anahtar
            assert any(d in kabul for d in degerler), (
                'sayaç bağlanmamış: %s alanı sayac() süzgecinden geçmiyor '
                '(kabul edilen biçimler %s; ölçülen %s)'
                % (alan, sorted(kabul), degerler))
            ham = [d for d in degerler if d == alan]
            assert not ham, (
                '%s doğrudan basılıyor — uç alanı yayımlamazsa ekranda '
                'undefined/uydurma sayı görünür: %s' % (alan, ham))

    def test_olu_app_js_kopyasi_geri_gelmedi(self):
        """Sökülen kopya geri gelirse ölçüm yine iki yere ayrılır."""
        src = APP_JS.read_text(encoding='utf-8')
        for olu in ('const kesikTarama = (result.truncated_by_time_budget',
                    "TF('app.msg.paramTruncated'"):
            assert olu not in src, (
                'app.js parametrik kopyası geri geldi (%s) — canlı yol '
                'advanced.html satır içi sürümüdür' % olu)


# ---------------------------------------------------------------------------
# (b4) Panel ailesi
# ---------------------------------------------------------------------------
class TestPanelFailClosed:

    def test_enjektor_radyal_pay_uydurmuyor(self):
        src = oku('injector_panel.js')
        assert 'p.radial_flow_fraction || 0' not in src, (
            "radyal akış payı yine '0%' uyduruyor")
        assert 'Number.isFinite(p.radial_flow_fraction)' in src

    def test_karsilastirma_konfig_sayisi_uydurmuyor(self):
        src = oku('panels/comparative_panel.js')
        assert 'analysis.total_configs || 0' not in src, (
            "CONFIGS kartı yine '0' uyduruyor")
        assert 'Number.isFinite(analysis.total_configs)' in src
        assert "? 'info' : 'dim'" in src, (
            'kart, komşularıyla aynı sönük (dim) durumu kullanmıyor')

    def test_sogutma_istasyon_sayisi_uydurmuyor(self):
        src = oku('panels/cooling_panel.js')
        assert 'dbz.stations_using_dittus_boelter || 0' not in src
        assert 'U.fmt(dbz.stations_using_dittus_boelter, 0)' in src, (
            'istasyon sayısı komşu satırların dürüst biçimlendiricisini '
            'kullanmıyor')

    def test_belirsizlik_isi_sahte_ilerleme_basmiyor(self):
        """SAHTE İLERLEME YASAĞI: uç oran vermezse yüzde yazılmaz."""
        src = oku('panels/uncertainty_panel.js')
        assert 'job.progress || 0' not in src, (
            "iş ilerlemesi yine '0%' uyduruyor")
        assert 'Number.isFinite(job.progress)' in src
        assert 'panel.uncertainty.jobProgressNoPct' in src, (
            'yüzdesiz durum metni yok — ilerleme bildirilmediğinde ne '
            'yazılacağı tanımsız')


# ---------------------------------------------------------------------------
# (b5) Yeni sözlük anahtarları iki dilde de var
# ---------------------------------------------------------------------------
class TestI18nAnahtarlari:

    ANAHTARLAR = ('common.notComputed', 'panel.uncertainty.jobProgressNoPct')

    @pytest.mark.parametrize('anahtar', ANAHTARLAR)
    def test_anahtar_en_ve_tr_bloklarinda(self, anahtar):
        src = oku('i18n_common.js')
        en_bas = src.index('\n        en: {')
        tr_bas = src.index('\n        tr: {')
        assert en_bas < tr_bas
        desen = "'%s':" % anahtar
        assert desen in src[en_bas:tr_bas], '%s EN bloğunda yok' % anahtar
        assert desen in src[tr_bas:], '%s TR bloğunda yok' % anahtar

    def test_turkce_karsiliklar_bos_degil(self):
        src = oku('i18n_common.js')
        tr = src[src.index('\n        tr: {'):]
        for anahtar in self.ANAHTARLAR:
            m = re.search(r"'%s':\s*'([^']*)'" % re.escape(anahtar), tr)
            assert m and m.group(1).strip(), (
                '%s için Türkçe karşılık boş' % anahtar)


# ---------------------------------------------------------------------------
# Ölçüm kanıtı — once/sonra dosyaları raporla tutarlı
# ---------------------------------------------------------------------------
def test_olcum_kaniti_yerinde():
    kanit = REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D25' / 'arayuz' / 'a1'
    once = json.loads((kanit_gerekli(kanit / 'once.json')).read_text(encoding='utf-8'))
    sonra = json.loads((kanit_gerekli(kanit / 'sonra.json')).read_text(encoding='utf-8'))
    assert once['bekci_js_tariyor'] == 0, 'taban ölçümü kalemi doğrulamıyor'
    assert sonra['bekci_js_tariyor'] == sonra['js_dosya_sayisi'] > 0
    assert once['beyansiz'] > sonra['beyansiz'] == 0
