# -*- coding: utf-8 -*-
"""ÖH Dalga-27 · arayuz · aşama-3 — ONBİR ONARIMIN BEKÇİLERİ.

Her bekçi, kusurun DÖNMESİ hâlinde kırmızı verir. Ölçüm ve ters-mutasyon
kanıtı: ``docs/scofield/raw/OH/D27/arayuz/a3/`` (once.json / sonra.json /
mutasyon.json).

Kalemler:
  P12aB2-08  liquid.html — "aralık" vaat eden iki etiket tek uç değer alıyordu
  P12aB3-03  i18n_charts.js — enjektör künyesinin iki satırı TR'de İngilizce
  P12aB3-06  i18n_charts.js — itki künyesinin iki ÇÖZÜLMÜŞ durumu çevrilmiyor
  P12bB1-11  liquid.html — çevrim paneli ham enum basıyor, uyarıları okumuyor
  P11B4-21   feed_panel.js — kart ipucu kendini "adiabatic bound" ilan ediyor
  P11B4-22   feed_panel.js — slosh modları ve sıvı kütlesi okunmuyor
  P11B4-23   validation_panel.js — tasarım noktası "HRMA prediction" adıyla
  P11B4-24   validation_panel.js — 5/10/20 bandı panele gömülü
  P11B4-25   correlation_panel.js — n=1 hücreleri dağılım istatistiği gibi
  P11B4-26   correlation_panel.js — tabloda şiddet işareti yok
  P11B4-28   stability_panel.js — skipped_points yanlış adresten okunuyor
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from tests.support.kanit import kanit_cikti, kanit_gerekli

KOK = Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
PANELS = JS / 'panels'
SABLON = KOK / 'hrma' / 'templates'
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D27' / 'arayuz' / 'a3'


def oku(yol):
    return yol.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# Canlı i18n koşumu — sözlükler gerçek yükleme sırasıyla kurulur.
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def cevir():
    if shutil.which('node') is None:
        pytest.skip('node kurulu değil')
    harness = KANIT / 'i18n_kosum.js'
    if not kanit_gerekli(harness).exists():
        pytest.skip('i18n koşum harness yok')

    def _kos(chart_metinleri=(), anahtarlar=()):
        gp = kanit_cikti(KANIT / '_bekci_girdi.json')
        gp.write_text(json.dumps({'chart': list(chart_metinleri),
                                  'key': list(anahtarlar)}), encoding='utf-8')
        try:
            ham = subprocess.check_output(
                ['node', kanit_gerekli(str(harness)), str(KOK), str(gp)],
                stderr=subprocess.STDOUT, timeout=120)
        finally:
            if gp.exists():
                gp.unlink()
        return json.loads(ham.decode('utf-8'))
    return _kos


# ===========================================================================
# P12aB2-08 — "aralık" vaat eden etiket, tek uç değer alan alan
# ===========================================================================
UC_ALAN_RE = re.compile(r'^(min|max)_|_(min|max)$')
ARALIK_RE = re.compile(r'range|aralı[kğ]', re.IGNORECASE)
UC_SOZCUK_RE = re.compile(
    r'minimum|maximum|\bmin\b|\bmax\b|alt sınır|üst sınır|asgari|azami',
    re.IGNORECASE)


def _etiket_alan_ciftleri(html):
    ciftler = []
    for m in re.finditer(r'<span data-i18n="([^"]+)">([^<]*)</span>', html):
        kuyruk = html[m.end():m.end() + 900]
        inp = re.search(r'<input\s+type="number"\s+id="([^"]+)"', kuyruk)
        araya = re.search(r'<span data-i18n=', kuyruk)
        if inp and (not araya or araya.start() > inp.start()):
            ciftler.append((m.group(1), m.group(2), inp.group(1)))
    return ciftler


def test_p12ab2_08_tek_uc_alani_aralik_vaat_etmez(cevir):
    """Tek uç değer alan alanın etiketi "aralık" demez, ucu ADIYLA söyler.

    ÖLÇÜLDÜ (once.json): iki alan — ``min_throttle`` etiketi "Throttle Range"
    / "Kısma Aralığı", ``temp_range_min`` etiketi "Ambient Temperature Range"
    / "Ortam Sıcaklığı Aralığı". İkizi ``temp_range_max`` doğru biçimde
    "Max Ambient Temperature" diyordu; form kendi içinde çelişiyordu.
    """
    html = oku(SABLON / 'liquid.html')
    ciftler = _etiket_alan_ciftleri(html)
    assert ciftler, 'etiket/alan çifti bulunamadı — ayrıştırıcı bayatladı'
    cv = cevir(anahtarlar=[a for a, _, _ in ciftler])
    kusurlu = []
    for anahtar, metin, alan in ciftler:
        if not UC_ALAN_RE.search(alan):
            continue
        en = cv['key'].get(anahtar, {}).get('en', '') or metin
        tr = cv['key'].get(anahtar, {}).get('tr', '') or ''
        if not (ARALIK_RE.search(en) or ARALIK_RE.search(tr)):
            continue
        if UC_SOZCUK_RE.search(en) or UC_SOZCUK_RE.search(tr):
            continue
        kusurlu.append('%s -> %s (%r / %r)' % (alan, anahtar, en, tr))
    assert not kusurlu, (
        '"Aralık" vaat edip tek uç değer alan alan(lar): %s' % kusurlu)


# ===========================================================================
# P12aB3-03 / P12aB3-06 — grafik künyelerinin TR karşılığı
# ===========================================================================
#: hrma/visualization/visualization.py'nin ÜRETTİĞİ enjektör künye satırları.
INJEKTOR_SATIRLARI = [
    'Face pattern: circular rings (layout only, total area unchanged)',
    'Face pattern: hex lattice (layout only, total area unchanged)',
    'Face pattern: square grid (layout only, total area unchanged)',
    'Total Flow: 1.234 kg/s',
    'Total Flow: not reported',
]
#: hrma/export/cad_visualization.py'nin ürettiği itki künye AİLESİ.
ITKI_KUNYELERI = [
    'Thrust (computed transient)',
    'Thrust (computed curve)',
    'Thrust (design point, constant-thrust assumption)',
]


def test_p12ab3_03_enjektor_kunyesi_turkce_ekranda_ingilizce_kalmaz(cevir):
    """Enjektör özet kutusunun HER satırı TR ekranda çevrilir.

    ÖLÇÜLDÜ (once.json): altı satırın ikisi aynen İngilizce kalıyordu —
    'Face pattern: …' (çizimin süs olduğunu söyleyen künye) ve
    'Total Flow: not reported' (sayının raporlanmadığını söyleyen dürüstlük
    satırı). Türkçe kullanıcı kutunun sayısını Türkçe, çekincelerini
    İngilizce okuyordu.
    """
    cv = cevir(chart_metinleri=INJEKTOR_SATIRLARI)
    kalan = [s for s in INJEKTOR_SATIRLARI
             if cv['chart'][s].strip() == s.strip()]
    assert not kalan, 'TR ekranda İngilizce kalan enjektör satırı: %s' % kalan


def test_p12ab3_06_itki_kunye_ailesinin_ucu_de_cevrilir(cevir):
    """Üç künyenin parantez içi de çevrilir — aile tek bakışta kıyaslanır.

    ÖLÇÜLDÜ (once.json): sözlükte yalnız VARSAYIM durumu vardı; iki
    ÇÖZÜLMÜŞ durum 'İtki (computed transient)' / 'İtki (computed curve)'
    diye yarı İngilizce çıkıyordu. Sebep: "Taban (birim)" kuralı parantez
    içini BİRİM sanıyor, oysa burada parantez içi KÜNYEDİR.
    """
    cv = cevir(chart_metinleri=ITKI_KUNYELERI)
    tr_harf = re.compile(r'[çğıöşüÇĞİÖŞÜ]')
    yari = []
    for kaynak in ITKI_KUNYELERI:
        cikan = cv['chart'][kaynak]
        ic_kaynak = re.search(r'\(([^()]*)\)$', kaynak).group(1)
        ic_cikan = re.search(r'\(([^()]*)\)$', cikan)
        ic_cikan = ic_cikan.group(1) if ic_cikan else ''
        if ic_cikan == ic_kaynak and not tr_harf.search(ic_cikan):
            yari.append('%s -> %s' % (kaynak, cikan))
    assert not yari, 'Parantez içi İngilizce kalan itki künyesi: %s' % yari


# ===========================================================================
# P12bB1-11 — çevrim paneli: ham enum + okunmayan uyarılar
# ===========================================================================
def _cevrim_blogu():
    html = oku(SABLON / 'liquid.html')
    m = re.search(r'var sol = fs\.engine_cycle_solution.*?// 3\) Kısma haritası',
                  html, re.S)
    assert m, 'çevrim özeti bloğu bulunamadı — panel yeniden düzenlenmiş'
    return m.group(0)


def test_p12bb1_11_cevrim_durumu_ham_enum_olarak_basilmaz():
    """`sol.status` esc() ile OLDUĞU GİBİ basılmaz; çevrim kanalından geçer.

    ÖLÇÜLDÜ (once.json): panel 'converged' / 'not_converged' makine
    dizelerini doğrudan basıyordu — TR seçiliyken de İngilizce ve teknik.
    """
    blok = _cevrim_blogu()
    assert 'esc(sol.status)' not in blok, (
        'Çevrim durumu ham enum olarak basılıyor (esc(sol.status)).')
    assert 'cycleStatusText(sol.status)' in blok, (
        'Durum çevrim kanalı (cycleStatusText) bağlı değil.')


def test_p12bb1_11_cevrim_kritik_uyarilari_okunur():
    """`sol.warnings` okunur ve `severity: critical` kalemler görünür.

    ÖLÇÜLDÜ (once.json ve raw/P12B/B1-repro-14.py): besleme 50 bar / Pc 100
    bar senaryosunda uç `warn.cycle.pressure_fed_infeasible` (severity
    'critical', 72,3 bar açık) yayımlarken ekranda yalnız 'not_converged'
    yazıyordu; panel `sol.warnings`'i HİÇ okumuyordu.
    """
    blok = _cevrim_blogu()
    assert 'sol.warnings' in blok, 'Çevrim uyarıları okunmuyor.'
    assert "severity === 'critical'" in blok, (
        'Kritik şiddet ayıklanmıyor — kullanıcı yakınsama gürültüsü ile '
        'olanaksız tasarımı ayırt edemez.')
    assert 'data-cyc-block="critical"' in blok, (
        'Kritik uyarı bloğu çevrim özetine basılmıyor.')


def _kes_govde(kaynak, imza):
    """İmzadan başlayan JS fonksiyonunu süslü parantez sayarak keser."""
    bas = kaynak.index(imza)
    i = kaynak.index('{', bas + len(imza) - 1)
    derinlik, son = 0, i
    while son < len(kaynak):
        if kaynak[son] == '{':
            derinlik += 1
        elif kaynak[son] == '}':
            derinlik -= 1
            if derinlik == 0:
                break
        son += 1
    return kaynak[bas:son + 1]


@pytest.mark.skipif(shutil.which('node') is None, reason='node kurulu değil')
def test_p12bb1_11_kritik_uyari_ekrana_basiliyor(tmp_path):
    """DAVRANIŞ bekçisi: kritik uyarı GERÇEKTEN `summ.innerHTML`e giriyor mu?

    ÖH D33-KOLAY · P12bB1-11 denetim ŞARTI. Kardeş bekçiler kaynak
    METNİNDE dize arıyor ('data-cyc-block="critical"' vb.); o ölçüt bloğun
    KOŞULDUĞUNU değil YAZILDIĞINI kanıtlar. Burada çevrim özeti bloğu ve
    `liquidWarnText` node ikizinde gerçekten koşturulur: uç
    `warn.cycle.pressure_fed_infeasible` (severity 'critical', 72,3 bar
    açık) yayımladığında kullanıcının ekranında hem kırmızı blok hem
    SAYILAR görünmeli; uyarı yokken blok HİÇ çıkmamalı.

    Kabul ölçütü (mutasyon M8b): kritik blok `if (false)` ile
    susturulduğunda bu bekçi KIRMIZI olur.
    """
    html = oku(SABLON / 'liquid.html')
    blok = _cevrim_blogu()
    warn_govde = _kes_govde(html, 'function liquidWarnText(w) {')
    # Uyarı metni TEK KAYNAKTAN okunur — teste gömülmez.
    sozluk = oku(JS / 'i18n_common.js')
    m = re.search(r"'warn\.cycle\.pressure_fed_infeasible': '([^']*)'", sozluk)
    assert m, 'uyarı metni sözlükte yok — TEK KAYNAK kırıldı'
    sozluk_json = json.dumps({'warn.cycle.pressure_fed_infeasible': m.group(1)})

    betik = (
        'var window = {};\n'
        'var SOZLUK = ' + sozluk_json + ';\n'
        'window.I18N = { tf: function (kod, params, yedek) {\n'
        '    var kalip = SOZLUK[kod] || yedek;\n'
        '    return String(kalip).replace(/\\{(\\w+)\\}/g,'
        ' function (t, ad) {\n'
        '        return (params && ad in params) ? String(params[ad]) : t;\n'
        '    });\n'
        '} };\n'
        'function T(k, f) { return f; }\n'
        'function esc(v) { return String(v).replace(/&/g, "&amp;")\n'
        '    .replace(/</g, "&lt;").replace(/>/g, "&gt;"); }\n'
        + warn_govde + '\n'
        'function kos(uyarilar) {\n'
        '    var summ = { innerHTML: "" };\n'
        '    var shown = false;\n'
        '    var fs = { engine_cycle: "pressure_fed",\n'
        '        engine_cycle_solution: { status: "not_converged",\n'
        '            warnings: uyarilar } };\n'
        + blok + '\n'
        '    return { html: summ.innerHTML, shown: shown };\n'
        '}\n'
        'console.log(JSON.stringify({ kritik: kos([{'
        ' code: "warn.cycle.pressure_fed_infeasible", severity: "critical",'
        ' params: { tank: 50, deficit: 72.3, required: 122.3 } }]),'
        ' bos: kos([]) }));\n')

    yol = tmp_path / 'cevrim.js'
    yol.write_text(betik, encoding='utf-8')
    p = subprocess.run(['node', str(yol)], capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    kritik, bos = out['kritik']['html'], out['bos']['html']

    # 1) Kritik blok GERÇEKTEN basılıyor.
    assert 'data-cyc-block="critical"' in kritik, (
        'kritik çevrim uyarısı ekrana HİÇ çıkmıyor: kullanıcı olanaksız '
        'tasarımı yakınsama gürültüsünden ayırt edemez')
    # 2) SAYILAR ekranda — beyan boş bir başlık değil.
    assert '72.3' in kritik, (
        'uyarının sayıları (açık bar) ekrana ulaşmıyor: liquidWarnText '
        'çıktısı basılmıyor ya da params kanalda düşüyor')
    assert '122.3' in kritik and '50' in kritik
    # 3) Ham enum basılmıyor; durum çevrim kanalından geçiyor.
    assert 'Power balance did not close' in kritik
    assert 'not_converged' not in kritik, (
        'çevrim durumu yine ham makine enum u olarak basılıyor')
    assert out['kritik']['shown'] is True
    # 4) Uyarı yokken blok UYDURULMUYOR (aşırı düzeltme kapısı).
    assert 'data-cyc-block' not in bos, (
        'uyarı yokken bile kritik blok basılıyor')
    assert '72.3' not in bos
    assert 'Power balance did not close' in bos, (
        'uyarısız koşumda durum satırı da kayboldu — aşırı söküm')


# ===========================================================================
# P11B4-21 / P11B4-22 — feed_panel
# ===========================================================================
def _delivered_ipucu():
    feed = oku(PANELS / 'feed_panel.js')
    m = re.search(r"'panel\.feed\.cardDeliveredTip',((?:\s*\+?\s*'[^']*')+)\)",
                  feed)
    assert m, 'DELIVERED GAS ipucu bulunamadı'
    return ''.join(re.findall(r"'([^']*)'", m.group(1)))


def test_p11b4_21_delivered_karti_kendini_adyabatik_sinir_ilan_etmez():
    """Kart ipucu kendini "adiabatic bound" diye TANITMAZ.

    ÖLÇÜLDÜ (once.json): ipucu "Recommended (conservative, adiabatic bound)
    pressurant mass" diyordu; YANINDAKİ 'ADIABATIC BOUND' kartı 1,873 kat
    farklı bir sayı gösteriyor (4,128 kg ⟷ 2,204 kg) ve ucun kendi notu bu
    sınırların "not the sizing basis" olduğunu yazıyor
    (hrma/analysis/pressurant_sizing.py).
    """
    tip = _delivered_ipucu()
    assert not re.search(
        r'\(conservative, adiabatic bound\)|adiabatic bound\)\s*pressurant', tip), (
        'İpucu kartı hâlâ adyabatik sınır diye tanıtıyor: %r' % tip)
    assert 'closed-form energy balance' in tip, (
        'İpucu sayının gerçek dayanağını adıyla anmıyor: %r' % tip)
    assert re.search(r'NOT the basis|not the sizing basis', tip), (
        'İpucu, sınır kartlarının bu sayının dayanağı OLMADIĞINI söylemiyor.')


def test_p11b4_21_ucun_notuyla_ayni_hukum():
    """İpucunun hükmü ucun kendi model notundan gelir (tek kaynak)."""
    uc = oku(KOK / 'hrma' / 'analysis' / 'pressurant_sizing.py')
    assert 'not the sizing basis' in uc, (
        'Ucun model notu değişmiş — ipucu artık ucun hükmünü tekrar '
        'etmiyor olabilir; ikisi birlikte gözden geçirilmeli.')


def test_p11b4_22_slosh_modlari_ve_sivi_kutlesi_ekrana_iner():
    """Uç `modes` ve `liquid_mass_kg` yayımlıyorsa panel onları basar.

    ÖLÇÜLDÜ (once.json): panel ikisini de HİÇ okumuyordu; ekranda yalnız
    1. mod vardı. Yüksek modlar kontrol/yapı frekanslarıyla çakışma
    denetiminin girdisidir.
    """
    feed = oku(PANELS / 'feed_panel.js')
    assert 's.modes' in feed, 'Yüksek çalkalanma modları okunmuyor.'
    assert 's.liquid_mass_kg' in feed, 'Sıvı kütlesi okunmuyor.'
    # Fail-closed: alan yoksa satır ÇIKMAZ.
    assert 'Array.isArray(s.modes) && s.modes.length' in feed, (
        'Mod tablosu fail-closed değil (uç göndermezse satır çıkmamalı).')
    assert 'Number.isFinite(s.liquid_mass_kg)' in feed, (
        'Sıvı kütlesi satırı fail-closed değil.')


def test_p11b4_22_ucun_yayimladigi_alanlar_hala_ayni_adda():
    """Panelin okuduğu adlar ucun yayımladığı adlarla aynı kalır."""
    uc = oku(KOK / 'hrma' / 'analysis' / 'slosh_analysis.py')
    for alan in ("'modes': modal", "'liquid_mass_kg': self.liquid_mass"):
        assert alan in uc, (
            'Uç sözleşmesi değişmiş (%s yok) — panel ölü alan okuyor '
            'olabilir.' % alan)


# ===========================================================================
# P11B4-23 / P11B4-24 — validation_panel
# ===========================================================================
def _vp():
    return oku(PANELS / 'validation_panel.js')


def _vp_render():
    m = re.search(r'function render\(data, root\)(.*?)\n    \}\n', _vp(), re.S)
    assert m, 'validation render() bulunamadı'
    return m.group(1)


def test_p11b4_23_tasarim_noktasi_kunyesi_lejanda_ve_sonuca_iner():
    """İki noktalı tasarım noktası "HRMA prediction" adıyla geçmez.

    ÖLÇÜLDÜ (once.json + raw/P11/B4-repro-08.py): geçici rejim yokken panel
    `{time:[0, burn_time], thrust:[F, F]}` dikdörtgenini çiziyor, lejanda
    'HRMA prediction [N]' yazıyor ve koşturulmuş sonuç bloğunda 'design
    point' dizesi 0 kez geçiyordu. Kullanıcının gerçek atış verisi bu
    dikdörtgene karşı "POOR AGREEMENT" damgası yiyor, metin ona yük hücresi
    kalibrasyonunu sorgulatıyordu.
    """
    vp = _vp()
    assert "kind: 'design_point'" in vp, (
        'Tahmin eğrisinin türü makine künyesiyle işaretlenmiyor.')
    m = re.search(r'function drawCurves\((.*?)\n    \}\n', vp, re.S)
    assert m, 'drawCurves bulunamadı'
    assert 'pred.source' in m.group(1), (
        'Lejant kıyas eğrisinin kaynağını taşımıyor.')
    render = _vp_render()
    assert 'pred.source' in render, (
        'Sonuç bloğu tahmin kaynağını basmıyor.')
    assert "pred.kind === 'design_point'" in render, (
        'Sonuç bloğu tasarım noktası durumunu ayırt etmiyor.')
    assert 'designPointHead' in render, (
        'Tasarım noktası uyarısı sonuç bloğunda yok — düşük not, ölçüm '
        'verisi hakkında bir hüküm sanılır.')


def test_p11b4_24_esik_tablosu_panele_gomulu_degil():
    """5/10/20 bandı panelde YAZILI değildir; uçtan gelir.

    ÖLÇÜLDÜ (once.json): `diffKind` bandı kendi içinde tutuyordu
    (``a <= 5`` / ``a <= 10`` / ``a <= 20``); uç aynı sayıları
    (GRADE_THRESHOLDS_PCT) yayımlamıyordu. Bugün eşitler; uçtaki eşik
    değişse rozetin hükmü ile kartların rengi sessizce ayrışırdı.
    """
    vp = _vp()
    m = re.search(r'function diffKind\(pct[^)]*\)(.*?)\n        \}', vp, re.S)
    assert m, 'diffKind bulunamadı'
    gomulu = re.findall(r'a <= (\d+(?:\.\d+)?)\b', m.group(1))
    assert not gomulu, 'Eşik hâlâ panele gömülü: %s' % gomulu
    assert 'comparison.grade_thresholds_pct' in vp, (
        'Band uçtan okunmuyor.')
    assert 'if (!bands' in m.group(1), (
        'Band gelmediğinde fail-closed değil — panel band uydurabilir.')


def test_p11b4_24_uc_esikleri_ve_skorlanan_metrikleri_yayimlar():
    """Uç, bandı ve skorun BAKTIĞI metrikleri yanıtla birlikte yayımlar."""
    uav = oku(KOK / 'hrma' / 'validation' / 'user_data_validation.py')
    assert "'grade_thresholds_pct': dict(GRADE_THRESHOLDS_PCT)" in uav, (
        'Uç eşik tablosunu yayımlamıyor.')
    assert "'scored_metrics'" in uav, (
        'Uç, skorun hangi metriklere baktığını yayımlamıyor.')


def test_p11b4_24_skorlanmayan_metrige_band_uygulanmaz():
    """Ucun skorlamadığı kart renklendirilmez — rengin arkasında hüküm yok.

    ÖLÇÜLDÜ (once.json): panel bandı `peak_thrust_diff_pct`,
    `mean_thrust_diff_pct` ve `burn_time_diff_pct` kartlarına da
    uyguluyordu; ucun puanı yalnız max(|impuls farkı|, NRMSE).
    """
    vp = _vp()
    cagrilar = dict.fromkeys(re.findall(
        r"diffKind\(metrics\.(\w+),\s*'(\w+)'\)", vp))
    kunyesiz = re.findall(r'diffKind\(metrics\.(\w+)\)', vp)
    assert not kunyesiz, (
        'Künyesiz diffKind çağrısı var (metrik adı geçirilmiyor): %s'
        % kunyesiz)
    assert cagrilar, 'diffKind çağrıları bulunamadı'
    for metrik, kunye in cagrilar:
        assert metrik == kunye, (
            'diffKind künyesi metrikle uyuşmuyor: %s / %s' % (metrik, kunye))
    m = re.search(r'function diffKind\(pct[^)]*\)(.*?)\n        \}', vp, re.S)
    assert 'scored.indexOf(metrik) < 0' in m.group(1), (
        'Panel, ucun skorlamadığı metriği de renklendiriyor.')


# ===========================================================================
# P11B4-25 / P11B4-26 — correlation_panel
# ===========================================================================
def _cp():
    return oku(PANELS / 'correlation_panel.js')


def _cp_satir():
    m = re.search(r'function cellRowHtml\(c[^)]*\)(.*?)\n    \}\n', _cp(), re.S)
    assert m, 'cellRowHtml bulunamadı'
    return m.group(1)


def test_p11b4_25_tek_kayittan_dagilim_istatistigi_basilmaz():
    """n < 2 hücrede RMS ve medyan APE basılmaz; tek kaydın hatası Bias'ta.

    ÖLÇÜLDÜ (once.json + raw/P11/B4-repro-09.py, 212 kayıt): 26 hücrenin
    12'sinde n = 1 ve o hücrelerde
    |bias_percent| = rms_percent = median_ape_percent — üç "istatistik"
    sütunu tek kaydın AYNI sayısı. Katı motor sayfasında en üstte listelenen
    dört satırın dördü de n = 1 ve bunu söyleyen hiçbir işaret yoktu.
    """
    cp, satir = _cp(), _cp_satir()
    assert 'DAGILIM_MIN_N' in cp, 'Dağılım tanım sınırı yok.'
    assert re.search(r'DAGILIM_MIN_N\s*=\s*2', cp), (
        'Dağılım sınırı 2 değil — karesel ortalama tek örnekten türetilemez.')
    assert 'c.n >= DAGILIM_MIN_N' in satir, (
        'Dağılım sütunları n eşiğine bağlanmamış.')
    assert not re.search(r'>\$\{fmtAbsPct\(c\.rms_percent\)\}', satir), (
        'RMS koşulsuz basılıyor.')
    assert not re.search(r'>\$\{fmtAbsPct\(c\.median_ape_percent\)\}', satir), (
        'Medyan APE koşulsuz basılıyor.')
    assert 'tekKayitTip' in satir, 'Tek-kayıt işareti/ipucu yok.'


def test_p11b4_26_tabloda_siddet_isareti_var():
    """Satır büyüklüğü görsel ağırlık taşır; ölçek TABLONUN kendi verisinden.

    ÖLÇÜLDÜ (once.json): koşturulmuş HTML'de şiddet işareti sayısı 0 —
    `hybrid regression_rate` (bias −24,9) ile `hybrid c_star` (bias +0,1)
    aynı gri monospace'te ayırt edilemiyordu.

    Renk BANDI atılmaz: /api/correlation-report eşik yayımlamıyor ve panel
    eşik UYDURAMAZ (fail-closed). Ağırlık |bias|'ın tablodaki en büyük
    |bias|'a oranından gelir.
    """
    cp, satir = _cp(), _cp_satir()
    assert 'magnitudeBar' in satir, 'Satırda şiddet/büyüklük işareti yok.'
    assert 'enBuyukBias' in cp, 'Ölçek tablonun kendi verisinden türemiyor.'
    # Uydurma eşik yasağı: panelde 5/10/20 gibi bir band YAZILI olmamalı.
    m = re.search(r'function magnitudeBar\((.*?)\n    \}', cp, re.S)
    assert m, 'magnitudeBar bulunamadı'
    assert not re.search(r'<=\s*(5|10|20)\b', m.group(1)), (
        'Panel yayımlanmamış bir eşik bandı uyduruyor.')


def test_p11b4_26_kardes_panelin_bandi_uctan_gelir():
    """Kıyas noktası olan validation paneli de bandı uçtan okur (tek kaynak)."""
    assert 'comparison.grade_thresholds_pct' in _vp(), (
        'validation paneli bandı hâlâ kendi içinde tutuyor olabilir.')


# ===========================================================================
# P11B4-28 — stability_panel: atlanan kök-yeri noktaları
# ===========================================================================
def test_p11b4_28_atlanan_noktalar_ucun_adresinden_okunur():
    """Panel `root_locus.skipped_points`'i okur — ucun yayımladığı adres.

    ÖLÇÜLDÜ (once.json + raw/P11/B4-repro-10.py): panel
    `data.skipped_points` okuyordu; uç listeyi `root_locus` sözlüğüne
    koyuyor (hrma/app.py). Üst düzeyde böyle bir anahtar YOK, yani "atlanan
    noktalar sessizce düşürülmez" bloğu hiç çalışamıyordu — bekçi ölüydü.
    Bugünkü çekirdek hiçbir noktayı atlamadığı için kayıp canlı veriyle
    görünmüyordu.
    """
    sp = oku(PANELS / 'stability_panel.js')
    assert 'Array.isArray(rl.skipped_points)' in sp, (
        'Panel atlanan noktaları ucun adresinden okumuyor.')
    assert 'Array.isArray(data.skipped_points)' not in sp, (
        'Panel hâlâ üst düzey (var olmayan) adresi okuyor.')
    # Panelin kendi sözleşme künyesi de ucun şeklini yazmalı.
    assert re.search(r'root_locus:\{[^}]*skipped_points', sp, re.S), (
        'Panel başlığındaki sözleşme künyesi hâlâ üst düzey diyor.')


def test_p11b4_28_uc_listeyi_root_locus_altinda_yayimlar():
    """Ucun şekli değişirse bu bekçi uyarır (panel adresi bayatlamasın)."""
    appy = oku(KOK / 'hrma' / 'app.py')
    assert re.search(r"'root_locus':\s*\{[^}]*'skipped_points'", appy, re.S), (
        'Uç artık skipped_points`i root_locus altında yayımlamıyor — '
        'panelin adresi gözden geçirilmeli.')


# ===========================================================================
# Kanıt dosyaları — ölçüm ve ters-mutasyon defterde durur.
# ===========================================================================
@pytest.mark.parametrize('ad', ['once.json', 'sonra.json', 'mutasyon.json'])
def test_kanit_dosyalari_var(ad):
    assert (kanit_gerekli(KANIT / ad)).exists(), 'Kanıt dosyası eksik: %s' % ad
