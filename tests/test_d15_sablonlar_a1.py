# -*- coding: utf-8 -*-
"""ÖH Dalga-15 · kulvar `sablonlar` · aşama 1 — onarım bekçileri.

Her test TEK bir kusuru görür ve o kusur geri konduğunda KIRMIZI olur
(ters-mutasyon kanıtı: `docs/scofield/raw/OH/D15/sablonlar/a1/mutasyon.json`).
Ölçümler: aynı dizindeki `once.json` (onarımdan önce) ve `sonra.json`.

Saf yardımcı fonksiyonlar node ile GERÇEKTEN koşturulur (metin sınamak
yetmez: `test_i18n_pages` deseninin aynısı). node yoksa testler atlanır ve
gerekçesi kurulum sorusu olarak yazılır.
"""

import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
SABLONLAR = KOK / 'hrma' / 'templates'
LIQUID = SABLONLAR / 'liquid.html'
SOLID = SABLONLAR / 'solid.html'
ADVANCED = SABLONLAR / 'advanced.html'
MOTOR_SIVI = KOK / 'hrma' / 'engines' / 'liquid_rocket_engine.py'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(
    NODE is None,
    reason=('node yürütülebiliri bulunamadı; şablonun saf JS yardımcıları '
            'GERÇEKTEN koşturulamıyor. Kurulum sorusu: bu ortamda node '
            'kurulu mu? (CI node garantisi P13B1-04/A3 kalemidir.)'))


@pytest.fixture(scope='module')
def liquid_src():
    return LIQUID.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def solid_src():
    return SOLID.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def advanced_src():
    return ADVANCED.read_text(encoding='utf-8')


def _fonksiyon_kaynagi(src, ad):
    """`function ad(` ile başlayan bloğu süslü parantez eşleyerek çıkarır."""
    m = re.search(r'\n(\s*)(?:async\s+)?function %s\s*\(' % re.escape(ad), src)
    assert m, '%s fonksiyonu şablonda bulunamadı' % ad
    i = src.index('{', m.end() - 1)
    derinlik = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            derinlik += 1
        elif src[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return src[m.start():j + 1]
    raise AssertionError('%s bloğu kapanmıyor' % ad)


def _yorumsuz(js):
    """JS gövdesinden yorumları söker (ÖH D19, P12bB1-07 ŞARTI).

    Fable-D17 ölçtü: eski bekçi ``'mItici / trMdot' in liquid_src`` diye
    DOSYA GENELİNDE arıyordu ve bu koşul, ürünün türetimi sabite dönse
    bile, şablonun HTML yorumundaki "(mItici / trMdot)" cümlesiyle
    sağlanıyordu — bekçi körleşmişti (``const tYanma = 30;`` mutasyonu
    HEAD'de YEŞİL, tabanda KIRMIZI). Kanıt yalnız ÇALIŞAN koddan okunur.
    """
    js = re.sub(r'/\*.*?\*/', ' ', js, flags=re.S)
    return '\n'.join(sat for sat in js.split('\n')
                     if not sat.strip().startswith('//'))


def _sabit_kaynagi(src, ad):
    m = re.search(r'\n\s*const %s = \[(.*?)\];' % re.escape(ad), src, re.S)
    assert m, '%s sabiti bulunamadı' % ad
    return 'const %s = [%s];' % (ad, m.group(1))


def _node_kos(parcalar, gövde):
    kod = '\n'.join(parcalar) + '\n' + gövde
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                     encoding='utf-8') as fh:
        fh.write(kod)
        yol = fh.name
    try:
        cp = subprocess.run([NODE, yol], capture_output=True, text=True,
                            timeout=60)
        assert cp.returncode == 0, cp.stderr
        return json.loads(cp.stdout)
    finally:
        pathlib.Path(yol).unlink(missing_ok=True)


# --------------------------------------------------------------- P12bB1-06
def test_b1_06_cad_kapisi_yayimlanan_lule_boyunu_okur(liquid_src):
    """3B CAD kapısı çözücünün HİÇ yayımlamadığı adresi okumaz."""
    m = re.search(r'const cadDims = \[(.*?)\];', liquid_src, re.S)
    assert m, 'cadDims listesi bulunamadı'
    assert 'results.nozzle_length' not in m.group(1), (
        'Kapı `results.nozzle_length` okuyor; çözücü bu adı hiç yayımlamıyor '
        '(once.json: dört konfigürasyonda da yok) → panel %100 ölü.')
    assert 'liquidNozzleLengthMm(results)' in m.group(1)
    assert 'results.nozzle_length * 1000' not in liquid_src


@node_gerekli
def test_b1_06_lule_boyu_yardimcisi_yayimlanan_adresten_cozer(liquid_src):
    fn = _fonksiyon_kaynagi(liquid_src, 'liquidNozzleLengthMm')
    yanit = {'nozzle_angles': {'nozzle_length_mm': 349.05489},
             'design_summary': {}, 'motor_geometry': {},
             'component_sizing': {}, 'cooling_system': {}}
    out = _node_kos([fn], 'console.log(JSON.stringify({'
                          'dolu: liquidNozzleLengthMm(%s),'
                          'bos: liquidNozzleLengthMm({})}));'
                    % json.dumps(yanit))
    assert out['dolu'] == pytest.approx(349.05489)
    # Hiçbir adres yoksa kapı FAIL-CLOSED kalır (uydurma ölçüyle çizim yok).
    assert out['bos'] is None


# --------------------------------------------------------------- P12bB1-08
@node_gerekli
def test_b1_08_toplam_boy_yakinsak_bolumu_sayar(liquid_src):
    """Ekrandaki boy ihracata giden geometriyle AYNI kaynaktan gelir."""
    fn = _fonksiyon_kaynagi(liquid_src, 'liquidOverallLengthMm')
    yanit = {'motor_geometry': {'chamber_length': 0.300,
                                'nozzle_convergent_length': 0.0266834,
                                'nozzle_divergent_length': 0.3490549}}
    out = _node_kos([fn], 'console.log(JSON.stringify({'
                          'tam: liquidOverallLengthMm(%s),'
                          'eksik: liquidOverallLengthMm({motor_geometry:'
                          ' {chamber_length: 0.3}})}));' % json.dumps(yanit))
    assert out['tam'] == pytest.approx(675.7383, abs=1e-3)
    # Yakınsak bölüm sayılmasaydı 649,055 çıkardı (P12bB1-08 ölçümü).
    assert abs(out['tam'] - 649.0549) > 26.0
    assert out['eksik'] is None, 'kaynak eksikse kısa sayıya sessiz dönüş yok'


def test_b1_08_ozet_panosu_yardimciyi_kullanir(liquid_src):
    satir = [ln for ln in liquid_src.splitlines()
             if "liq.msg.overall_length" in ln]
    assert satir, 'Overall Length satırı bulunamadı'
    assert all('liquidOverallLengthMm(results)' in ln for ln in satir), (
        'Özet panosu hâlâ key_dimensions.overall_length_mm basıyor; o sayı '
        'yakınsak bölümü saymıyor ve ihracat geometrisinden kısa.')


# --------------------------------------------------------------- P12bB1-09
def test_b1_09_min_throttle_yalan_yafta_almaz(liquid_src):
    liste = _sabit_kaynagi(liquid_src, 'UNWIRED_INPUT_IDS')
    assert "'min_throttle'" not in liste, (
        'min_throttle statik "Not wired to the solver yet" yaftası alıyor; '
        'oysa alan throttle_map.min_throttle_pct ile chug RİSK hükmünü '
        'çeviriyor (40 -> risk var, 80 -> yok).')


def test_b1_09_statik_liste_cozucunun_beyaniyla_celismiyor():
    """Sayfanın statik listesi ile motorun kendi beyanı ayrışamaz."""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    beyan = LiquidRocketEngine.unwired_inputs(None)
    duz = set()
    for v in beyan.values():
        if isinstance(v, (list, tuple)):
            duz.update(v)
    assert 'min_throttle' not in duz, (
        'Motor alanı yeniden bağlanmamış olarak beyan ediyor — bu testin '
        'öncülü değişti, şablon listesi buna göre gözden geçirilmeli.')
    liste = set(re.findall(r"'([\w]+)'",
                           _sabit_kaynagi(LIQUID.read_text(encoding='utf-8'),
                                          'UNWIRED_INPUT_IDS')))
    assert not (liste - duz - {'engine_start_time', 'engine_shutdown_time',
                               'restart_capability'}), (
        'Şablon, motorun beyan etmediği alanlara "bağlanmamış" diyor: %s'
        % sorted(liste - duz))


# --------------------------------------------------------------- P12bB1-05
def test_b1_05_enjektor_dp_birimi_cozucunun_okudugu_birimdir(liquid_src):
    m = re.search(r'injector_pressure_drop_p">[^<]*</span>\s*'
                  r'<span class="unit">\(([^)]*)\)</span>', liquid_src)
    assert m, 'ΔP alanının birim etiketi bulunamadı'
    assert '%' not in m.group(1), (
        'Etiket yüzde diyor, çözücü BAR okuyor: Pc=20 barda "25" girmek '
        'gerekli oksitleyici tank basıncını 53 bara çıkarıyor.')
    assert m.group(1).strip() == 'bar'


def test_b1_05_ipucu_metni_yuzde_semantigi_tasimaz():
    """ÖH D17 (Fable-D15 ŞARTI): ipucu da BAR der, yüzde demez.

    Birim etiketi ``(bar)`` olduğu hâlde aynı alanın ipucu metni
    (``liq.ui.pressure_drop_across_injector_as_percentage``; şablon
    satır içi + ``i18n_pages.js`` EN ve TR) "percentage of chamber
    pressure … 15-25%" diyordu. Kullanıcı ipucuna bakıp yüzde girerse
    kalemin ölçtüğü tehlike (Pc = 20 barda "25" → tank basıncı +15 bar)
    AYNEN yaşanır. Üç metnin üçü de yüzde semantiğinden arınmış olmalı.
    """
    anahtar = 'liq.ui.pressure_drop_across_injector_as_percentage'
    yasak = ('%', 'percent', 'oran', 'yüzde', '15-25')
    # ÖK-10 (D16 sivi a1): metin çözücünün İKİ KİP künyesini birebir
    # anmak ZORUNDA — o künyeler makine damgasıdır, ipucunun "yüzde gir"
    # öğretisi değil. Künyeler ürünün kendi sabitinden okunur (tek
    # kaynak) ve yasak taramasından ÇIKARILIR.
    # V301/L-D (SV-16) — BEKLENTİ DEĞİŞTİ: künyeler hibrit enjektör
    # aracınınkiydi ('auto (20% of Pc)' / 'user override'); SIVI yanıtı bu
    # iki metni HİÇ basmıyor (ölçüldü: kati-sivi/L-D/onceson_sonra.json'da
    # 0 geçiş). Sıvı çözücünün GERÇEK künyeleri motorun tek tanımından
    # (``injection_system.pressure_drop_source``) okunur.
    from hrma.engines.liquid_rocket_engine import (
        INJECTOR_DP_SOURCE_TYPE_RATIO, INJECTOR_DP_SOURCE_USER)
    kunyeler = (INJECTOR_DP_SOURCE_TYPE_RATIO, INJECTOR_DP_SOURCE_USER)
    pages = (KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
        encoding='utf-8')
    metinler = re.findall(r"'" + re.escape(anahtar) + r"':\s*'"
                          r"((?:[^'\\]|\\.)*)'", pages)
    assert len(metinler) == 2, (
        'EN + TR çifti bulunamadı: ' + str(len(metinler)))
    sablon = re.search(r'data-i18n="' + re.escape(anahtar) + r'">([^<]*)<',
                       LIQUID.read_text(encoding='utf-8'))
    assert sablon, 'şablon satır içi ipucu metni bulunamadı'
    for etiket, metin in (('EN', metinler[0]), ('TR', metinler[1]),
                          ('şablon', sablon.group(1))):
        for kunye in kunyeler:
            assert kunye in metin, (
                etiket + ' ipucusu çözücünün kip künyesini anmıyor: '
                + repr(kunye) + ' (ÖK-10)')
        kalinti = metin
        for kunye in kunyeler:
            kalinti = kalinti.replace(kunye, '')
        dusuk = kalinti.lower()
        kirli = [y for y in yasak if y in dusuk]
        assert not kirli, (
            etiket + ' ipucusu hâlâ yüzde semantiği taşıyor ' + repr(kirli)
            + ': kullanıcı bar bekleyen alana yüzde girer. Metin: '
            + metin[:160])
        assert 'bar' in dusuk, (
            etiket + ' ipucusu birimi (bar) hiç anmıyor: ' + metin[:160])


def test_b1_05_tarayici_kapisi_cozucunun_bandiyla_ayni():
    """HTML min/max, motorun kendi bandından türetilir (tek kaynak)."""
    # V301/L-A (SV-01): bant çözücünün TEK tablosundan (LIQUID_INPUT_BANDS)
    # okunur; motor ``_override_band`` ile, uç kapısı da aynı satırla okur.
    from hrma.engines.liquid_rocket_engine import LIQUID_INPUT_BANDS
    alt, ust = LIQUID_INPUT_BANDS['injector_pressure_drop'][:2]
    inp = re.search(r'<input[^>]*id="injector_pressure_drop"[^>]*>',
                    LIQUID.read_text(encoding='utf-8'))
    assert inp, 'ΔP girdi alanı bulunamadı'
    mn = re.search(r'min="([0-9.]+)"', inp.group(0))
    mx = re.search(r'max="([0-9.]+)"', inp.group(0))
    assert mn and mx, 'ΔP alanında tarayıcı kapısı (min/max) yok'
    assert float(mn.group(1)) == alt
    assert float(mx.group(1)) == ust


# --------------------------------------------------------------- P12bB1-04
DERIN_KANALLAR = (
    'thermal_protection.station_march.warnings',
    'injection_system.injector_design_detail.warnings',
    'detailed_feed_system.engine_cycle_solution.warnings',
    'detailed_feed_system.valve_feedline.fuel_line.validity',
    'detailed_feed_system.valve_feedline.fuel_line.valve.validity',
    'detailed_feed_system.valve_feedline.oxidizer_line.validity',
    'detailed_feed_system.valve_feedline.oxidizer_line.valve.validity',
)


def test_b1_04_derin_uyari_kanallari_okunuyor(liquid_src):
    liste = _sabit_kaynagi(liquid_src, 'LIQUID_DEEP_WARNING_PATHS')
    for yol in DERIN_KANALLAR:
        assert "'%s'" % yol in liste, '%s kanalı hâlâ yutuluyor' % yol
    assert 'liquidDeepWarnings(r)' in liquid_src
    # Excel teslimatı da AYNI listeyi görmeli (ekran ile dosya ayrışamaz).
    toplayici = _fonksiyon_kaynagi(liquid_src, 'liquidCollectWarnings')
    assert 'liquidDeepWarnings(r)' in toplayici


@node_gerekli
def test_b1_04_yutulan_yedi_kalem_artik_toplaniyor(liquid_src):
    parcalar = [_sabit_kaynagi(liquid_src, 'LIQUID_DEEP_WARNING_PATHS'),
                _fonksiyon_kaynagi(liquid_src, 'liquidDeepWarnings'),
                _fonksiyon_kaynagi(liquid_src, 'liquidDeepIsCritical')]
    yanit = {
        'validation': {},
        'thermal_protection': {'station_march': {'warnings': [
            'CRITICAL: peak hot-wall temperature 3197 K exceeds melting point',
            'COKING: RP-1 coolant-side wall temperature reaches 1320 K',
            'PROPERTY RANGE: rp1 beyond tabulated range']}},
        'injection_system': {'injector_design_detail': {'warnings': [
            {'code': 'warn.injector.fixed_n_outside_pref_band',
             'severity': 'warning'},
            {'code': 'warn.injector.doublet_momentum_out_of_band',
             'severity': 'warning'},
            {'code': 'warn.injector.chug_risk', 'severity': 'warning'}]}},
        'detailed_feed_system': {
            'engine_cycle_solution': {'warnings': [
                {'code': 'warn.cycle.pressure_fed_infeasible',
                 'severity': 'critical'}]},
            'valve_feedline': {
                'fuel_line': {'validity': [{'field': 'cavitation',
                                            'status': 'not_evaluated'}],
                              'valve': {'validity': [{'field': 'ok_case',
                                                      'status': 'ok'}]}},
                'oxidizer_line': {'validity': [], 'valve': {'validity': []}}}},
    }
    out = _node_kos(parcalar,
                    'const w = liquidDeepWarnings(%s);'
                    'console.log(JSON.stringify({n: w.length,'
                    ' kritik: w.filter(liquidDeepIsCritical).length,'
                    ' bos: liquidDeepWarnings({}).length}));' % json.dumps(yanit))
    assert out['n'] == 8, 'derin kanalların kalemleri eksiksiz toplanmalı'
    # 'ok' hükmü verilmiş geçerlilik kaydı uyarı DEĞİLDİR.
    assert out['bos'] == 0
    # station_march düz metni "CRITICAL:" ile başlıyor, çevrim kaydı
    # severity=critical: ikisi de KRİTİK sayılır (biri yutulursa 1 olur).
    assert out['kritik'] == 2


# --------------------------------------------------------------- P12bB1-17
@node_gerekli
def test_b1_17_kutle_orani_yuzde_yuzu_asamaz(liquid_src):
    fn = _fonksiyon_kaynagi(liquid_src, 'liquidTankMassFractionPct')
    # P12bB1-17 ölçümünün SF=10 durumu: tank iticiden 2,6 kat ağır.
    out = _node_kos([fn], 'console.log(JSON.stringify({'
                          'sf10: liquidTankMassFractionPct({system_summary:'
                          ' {total_propellant_mass: 1915.64,'
                          '  total_tank_mass: 4971.16}}),'
                          'eksik: liquidTankMassFractionPct({system_summary:'
                          ' {total_propellant_mass: 1915.64}})}));')
    assert out['sf10'] == pytest.approx(27.82, abs=0.05), (
        'Kart tank/itici ORANINI kütle oranı diye basıyor (SF=10 -> %259,5).')
    assert out['sf10'] <= 100.0
    assert out['eksik'] is None, 'kütle yoksa hüküm verilmez'


def test_b1_17_kart_ham_orani_basmiyor(liquid_src):
    assert 'overall_mass_fraction * 100' not in liquid_src
    assert 'liquidTankMassFractionPct(tankData)' in liquid_src


# --------------------------------------------------------------- P12bB1-03
def test_b1_03_muhendislik_cad_govdesi_uydurmuyor(liquid_src):
    govde = re.search(r'const motorData = \{(.*?)\n                \};',
                      liquid_src, re.S)
    assert govde, 'detaylı CAD gövdesi bulunamadı'
    g = govde.group(1)
    assert "getElementById('throat_diameter')" not in g, (
        'Boğaz çapı ÖLÜ form alanından gidiyor (50,0 mm ⟷ çözücü 30,811 mm).')
    assert 'chamber_length * 0.75' not in g, 'lüle boyu uydurma kuraldan'
    assert 'injector_holes: 24' not in g, 'enjektör deliği sabiti'
    assert "injector_type: 'unlike_impinging'" not in g
    assert ': 5000' not in g and ': 320' not in g, 'itki/Isp uydurma yedeği'
    assert 'cr.throat_diameter * 1000' in g
    assert 'liquidNozzleLengthMm(cr)' in g
    assert 'injector_design:' in g and 'cooling_system:' in g


def test_b1_03_hesap_yokken_cizim_yok(liquid_src):
    blok = liquid_src.split('async function generateDetailedCAD')[1][:2500]
    assert "cr.thrust === 'number' && cr.thrust > 0" in blok, (
        'Kardeş düğme (generateBasicCAD) kapı koyuyor, bu düğme koymuyordu: '
        'hesap yokken uydurma değerlerle üç boyutlu motor çiziliyordu.')


# --------------------------------------------------------------- P12bB1-07
def test_b1_07_yorunge_yanma_suresi_motorun_debisinden(liquid_src):
    govde = re.search(r'const body = \{(.*?)\n            \};',
                      liquid_src, re.S)
    assert govde, 'yörünge gövdesi bulunamadı'
    g = govde.group(1)
    assert "burn_time: getv('traj_burn_time'" not in g, (
        'Yanma süresi form alanından geliyor; itici bütçesiyle 24,0× '
        'tutarsız bir yörünge çiziliyor.')
    # ÖH D19 · Fable-D17 ŞARTI — türetim ÇALIŞAN KODDA aranır.
    # Eski iki iddia ("… in g or 'burn_time: tYanma' in g" ve dosya
    # genelinde "'mItici / trMdot' in liquid_src") gevşetilmişti: ikincisi
    # şablonun HTML yorumundaki metinle sağlanıyor, dolayısıyla türetimi
    # sabite çeviren mutasyon bekçiyi KIRMIYORDU. Artık computeTrajectory
    # gövdesinde İKİSİ BİRDEN, yorumlar sökülmüş hâlde zorunludur.
    ct = _yorumsuz(_fonksiyon_kaynagi(liquid_src, 'computeTrajectory'))
    assert re.search(r'const\s+tYanma\s*=\s*mItici\s*/\s*trMdot', ct), (
        'yanma süresi computeTrajectory içinde motorun debisinden '
        'TÜRETİLMİYOR (yorumlar sayılmaz)')
    assert re.search(r'burn_time:\s*tYanma\b', ct), (
        'türetilen süre yörünge gövdesine BAĞLANMIYOR: body.burn_time '
        'tYanma değil')
    assert 'trMdot === null' in liquid_src, 'debi yoksa hüküm verilmemeli'


def test_b1_07_olu_alan_etkin_gorunmez_ve_turetileni_gosterir(liquid_src):
    """ÖH D17 (Fable-D15 ŞARTI): #traj_burn_time yanlış beyan etmez.

    D15 onarımından sonra alan HİÇBİR hesabı sürmüyordu ama sayfada
    düzenlenebilir duruyordu: kullanıcı değiştirir, hiçbir şey değişmez
    (sessiz ölü alan = yanlış beyan). Alan artık kilitli (``disabled``),
    yaftası türetimin kaynağını söyler ve hesaplanan süre alana YAZILIR.
    """
    alan = re.search(r'<input[^>]*id="traj_burn_time"[^>]*>', liquid_src)
    assert alan, '#traj_burn_time alanı bulunamadı'
    ham = alan.group(0)
    assert 'disabled' in ham, (
        'alan hâlâ etkin görünüyor: okunmadığı hâlde düzenlenebilir '
        '(yanlış beyan). ' + ham)
    # Yafta: türetimin kaynağını söyleyen i18n anahtarı alanın etiketinde.
    i = liquid_src.rfind('<label', 0, liquid_src.index(ham))
    etiket = liquid_src[i:liquid_src.index(ham)]
    assert 'burn_time_derived_from_mdot' in etiket, (
        'alanın yaftası türetim kaynağını söylemiyor: ' + etiket[-200:])
    # Türetilen süre alana yazılıyor.
    assert re.search(r"getElementById\('traj_burn_time'\)", liquid_src), (
        'türetilen süre alana hiç yazılmıyor')
    assert re.search(r"_tbAlan\.value = ", liquid_src), (
        'türetilen süre alana hiç yazılmıyor')
    # EN + TR anahtar borcu ödendi mi?
    pages = (KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
        encoding='utf-8')
    for anahtar in ('liq.ui.burn_time_derived_from_mdot',
                    'liq.ui.burn_time_placeholder_derived'):
        assert pages.count("'" + anahtar + "'") == 2, (
            anahtar + ' için EN+TR çifti yok: '
            + str(pages.count("'" + anahtar + "'")))


# --------------------------------------------------------------- P12bB2-05
def test_b2_05_preset_yakit_kimligiyle_termokimyayi_birlikte_tasir(solid_src):
    brp = _fonksiyon_kaynagi(solid_src, 'applyBurnRatePreset')
    assert 'applyPresetThermochemistry' in brp, (
        'Preset yalnız burn_rate_a/n yazıyor; yakıt KİMLİĞİ KNDX olurken '
        'termokimya APCP kalıyor (Isp 199,9 s ⟷ 121,3 s, 1,648×).')
    yardimci = _fonksiyon_kaynagi(solid_src, 'applyPresetThermochemistry')
    assert 'PROPELLANT_FIELD_MAP' in yardimci
    # a/n BİLEREK dışarıda: onları basınç rejimi çözer.
    assert "f.id === 'burn_rate_a'" in yardimci
    assert 'preset_could_not_be_resolved' in brp, (
        'Katalog kaydı yoksa kimlik ile termokimya sessizce ayrışamaz.')


@node_gerekli
def test_b2_05_termokimya_alanlari_gercekten_yaziliyor(solid_src):
    yardimci = _fonksiyon_kaynagi(solid_src, 'applyPresetThermochemistry')
    harita = re.search(r'var PROPELLANT_FIELD_MAP = \[(.*?)\];',
                       solid_src, re.S)
    assert harita
    onhazirlik = (
        'var PROPELLANT_FIELD_MAP = [%s];\n'
        'var _catalogValues = {};\n'
        "var _propellantRows = [{key: 'kndx', name: 'KNDX', density: 1785.0,"
        ' flame_temperature: 1710.0, molecular_weight: 42.39, gamma: 1.1308,'
        ' c_star: 912.4, burn_rate_a: 8.26e-5, burn_rate_n: 0.319}];\n'
        'var _alanlar = {};\n'
        'var document = {getElementById: function (id) {'
        ' if (!_alanlar[id]) _alanlar[id] = {value: null, dataset: {}};'
        ' return _alanlar[id]; }};\n' % harita.group(1))
    out = _node_kos([onhazirlik, yardimci],
                    "const u = applyPresetThermochemistry('kndx');"
                    "console.log(JSON.stringify({uygulanan: u,"
                    " cstar: _alanlar['char_velocity'].value,"
                    " tf: _alanlar['flame_temp'].value,"
                    " ad: _alanlar['propellant_name'].value,"
                    " bilinmeyen: applyPresetThermochemistry('yok_boyle')}));")
    assert out['cstar'] == pytest.approx(912.4)
    assert out['tf'] == pytest.approx(1710.0)
    assert out['ad'] == 'KNDX'
    assert 'burn_rate_a' not in out['uygulanan']
    assert out['bilinmeyen'] is None, 'kayıt yoksa sessiz uygulama olmaz'


# ----------------------------------------------------------- P12bB3-01/-16
def test_b3_01_regresyon_yuku_yakit_kimligini_tasir(advanced_src):
    blok = re.search(r"const response = await fetch\('/api/regression-analysis'"
                     r".*?\}\);", advanced_src, re.S)
    assert blok, 'regresyon çağrısı bulunamadı'
    assert 'motor_data: currentResults.motor,' not in blok.group(0), (
        'Uca yalnız `motor` sözlüğü gidiyor; o sözlükte fuel_type / '
        'regression_a / regression_n YOK, uç HTPB varsayılanına düşüyor ve '
        'kart onu kullanıcının seçimiymiş gibi basıyor.')
    assert 'motor_data: regMotorData,' in blok.group(0)
    kurucu = advanced_src.split('const regMotorData')[1][:1400]
    for alan in ('fuel_type', 'regression_a', 'regression_n'):
        assert alan in kurucu, '%s kimlik kanalında yok' % alan


def test_b3_16_ihracat_kunyesi_uydurma_yedege_dusmez(advanced_src):
    assert "formVal('oxidizer_type')" in advanced_src, (
        'Dışa aktarılan "Oxidizer" satırı boş kalıyor.')
    # ÖH D28 / arayuz a4 (P12bB3-20) — BEKÇİ ÇEVRİLDİ, GERİ ÇEKİLMEDİ.
    # Eski hâli `formVal('motor_name')` DİZESİNİ arıyordu; o dize tek bir
    # çağrı yerinin (regresyon dışa aktarımı) yerel yardımcısıydı ve
    # sayfadaki DÖRT ad çözücüsünden yalnız birini kapsıyordu. Ölçüldü:
    # kalan üçü (`STL`, `PDF`, `STL paketi`) ile `_motorName()` doğrudan
    # `motor.motor_name || '<literal>'` yedeğine düşüyor, üç FARKLI ad
    # üretiyordu ('HRMA_Motor' / 'HRMA_motor' / 'UZAYTEK_Motor').
    # Ad çözümü tek çözücüde birleştirildi; bekçi artık dizeyi değil
    # DAVRANIŞI kilitler ve eskisinden GENİŞTİR:
    #   (1) tek çözücü kullanıcının form alanını okur (yedeğe doğrudan
    #       düşmez — eski bekçinin koruduğu şey),
    #   (2) hiçbir dışa aktarım yeri çözücüyü atlayıp ham yedek
    #       literaline düşemez (eski bekçinin GÖREMEDİĞİ şey).
    import re as _re
    assert "function disaAktarimMotorAdi(m)" in advanced_src, (
        'Motor adının tek çözücüsü yok.')
    _govde = _re.search(r'function disaAktarimMotorAdi\(m\)(.*?)\n        \}',
                        advanced_src, _re.S).group(1)
    assert "getElementById('motor_name')" in _govde, (
        'Motor adı doğrudan yedeğe düşüyor: kullanıcının forma yazdığı ad '
        'okunmuyor.')
    assert not _re.findall(
        r"motor\.motor_name\s*\|\|\s*'", advanced_src), (
        'Bir dışa aktarım yeri tek çözücüyü atlayıp ham yedeğe düşüyor.')
    assert "formVal('fuel_type')" in advanced_src


# ----------------------------------------------------------- P12bB1-20 (ENGELLİ)
# Kalem ÖK-21 ile kilitli: form katmanındaki 55 `parseFloat('') || SABİT`
# yedeği BU DALGADA sökülemez (D1 sırası EN SON). Onarım yapılmadığı için
# kusuru gören bir bekçi de YAZILMAZ — kusuru koruyan bekçi yasaktır.
# Yazılan tek şey, sökme sırası geldiğinde arkasında duracak SAĞLAM tarafın
# koruması: ucun kendi fail-closed kapısı. Kapı bugün canlı (ölçüm:
# once.json · P12bB1-20 · ucun_kapisi_bos_govde = 422); form katmanı 55
# sabitle onu ulaşılamaz kıldığı için sayfa 200 alıyor. Kapı gevşetilirse
# (ÖK-22: sağlıklı envanter gevşetilemez) D1 sökümü anlamsızlaşır.
def test_b1_20_ucun_fail_closed_kapisi_ayakta_kalir():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        r = c.post('/calculate_liquid', json={})
    assert r.status_code == 422, (
        'Boş gövdeye 422 dönmüyor: /calculate_liquid fail-closed kapısı '
        'gevşetilmiş. P12bB1-20 (form katmanındaki 55 `|| SABİT`) ÖK-21 '
        'gereği henüz sökülmedi; söküm sırası geldiğinde arkasında duracak '
        'tek koruma bu kapıdır.'
    )
    j = r.get_json()
    assert (j or {}).get('defaults_applied') in (None, [], {}), (
        'Kapı reddederken varsayılan uygulandığını beyan ediyor.')
