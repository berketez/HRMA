"""V307/DİL-SON bekçisi (19 Kas 2026).

Ekranda kalan son makine adları ve İngilizce parçalar. Kalemler:

* kalem 2 — YAPISAL hüküm gerekçesi (``minimum_safety_factor_verdict_basis``):
  sunucu cümlesi alan adı (``verdict_safety_factor``,
  ``design_target_assessment``, ``measured_scope_status``) ve istasyon
  anahtarı (``chamber_hoop`` …) yerine okunur İngilizce ad basar; TR ekranda
  ``i18n_charts.js`` deseni Türkçe adla basar. Sayı ve hüküm değişmez.

Motor koşturmaz (yapısal çözümleyici kapalı biçimli ve hızlıdır). TR çeviri
ürünün kendi i18n yığınıyla (i18n.js + i18n_common.js + i18n_charts.js)
node'da ölçülür; tarayıcı yok.

Kanıt: docs/scofield/raw/OH/V307/dil-son/RAPOR.md
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from hrma.analysis.structural_analysis import (
    STRUCTURAL_STATION_NAMES_EN, StructuralAnalyzer,
    structural_station_list_en)

KOK = Path(__file__).resolve().parent.parent
STATIK = KOK / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node bulunamadı')

#: Ekrana basılan cümlede görünmemesi gereken makine adları.
_MAKINE_ADI = re.compile(r'\b[a-z]+(?:_[a-z0-9]+)+\b')
_INGILIZCE = re.compile(
    r'\b(the|is|are|this|that|which|with|not|and|from|were|would)\b')

_MOTOR = {'chamber_pressure': 40.0, 'chamber_diameter': 0.1,
          'chamber_length': 0.5, 'throat_diameter': 0.02, 'thrust': 3000.0,
          'burn_time': 3.0}
#: Dört dal + boş liste ('none') vakası; ölçüm
#: docs/scofield/raw/OH/V307/dil-son/k2_dallar_{once,sonra}.json.
_VAKALAR = {
    'b1_hepsi_boyutlandi': dict(design_safety_factor=2.0),
    'b2_kismi_olcum': dict(design_safety_factor=2.0,
                           actual_wall_thickness=0.004),
    'b3_ince_cidar': dict(design_safety_factor=2.0,
                          actual_wall_thickness=0.0003),
    'b4_hepsi_olculdu': dict(design_safety_factor=2.0,
                             actual_wall_thickness=0.004,
                             actual_throat_thickness=0.004,
                             actual_end_cap_thickness=0.008),
    'b3_hepsi_olculdu_ince': dict(design_safety_factor=2.0,
                                  actual_wall_thickness=0.0003,
                                  actual_throat_thickness=0.0003,
                                  actual_end_cap_thickness=0.0003),
}
#: Dalın TR çapası (i18n_charts.js) ve dalı seçen hüküm.
_TR_CAPA = {
    'b1_hepsi_boyutlandi': 'Ne onay ne de hüküm verildi',
    'b2_kismi_olcum': 'Onay verilmedi: ölçülen kesitler',
    'b3_ince_cidar': 'Hüküm, çizilmiş bir cidar üstünde',
    'b4_hepsi_olculdu': 'Sepetteki her istasyon kullanıcının verdiği',
    'b3_hepsi_olculdu_ince': 'Hüküm, çizilmiş bir cidar üstünde',
}


@pytest.fixture(scope='module')
def gerekceler():
    out = {}
    for ad, kw in _VAKALAR.items():
        r = StructuralAnalyzer().analyze_structure(
            dict(_MOTOR), material='steel_4130', **kw)
        out[ad] = r['safety_analysis']
    return out


_SURUCU = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [staticDir, girdiYolu] = process.argv.slice(2);
const depo = {};
const sb = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: function () { return 0; }, clearInterval: function () {},
    document: { documentElement: { lang: 'en', setAttribute: function () {} },
                addEventListener: function () {}, readyState: 'complete',
                querySelectorAll: function () { return []; },
                querySelector: function () { return null; },
                getElementById: function () { return null; } },
    localStorage: { getItem: function (k) { return (k in depo) ? depo[k] : null; },
                    setItem: function (k, v) { depo[k] = String(v); },
                    removeItem: function (k) { delete depo[k]; } },
    navigator: { language: 'en-US' },
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
for (const f of ['i18n.js', 'i18n_common.js', 'i18n_charts.js']) {
    vm.runInContext(fs.readFileSync(path.join(staticDir, f), 'utf8'), sb,
                    { filename: f });
}
const girdi = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'));
const out = {};
for (const dil of ['tr', 'en']) {
    sb.window.I18N.setLang(dil);
    out[dil] = girdi.map(function (t) { return sb.window.I18N.serverText(t); });
}
process.stdout.write(JSON.stringify(out));
"""


def _server_text(metinler, tmp_path, statik=STATIK):
    surucu = tmp_path / 'surucu.js'
    surucu.write_text(_SURUCU, encoding='utf-8')
    girdi = tmp_path / 'girdi.json'
    girdi.write_text(json.dumps(metinler, ensure_ascii=False),
                     encoding='utf-8')
    p = subprocess.run([NODE, str(surucu), str(statik), str(girdi)],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


def _sozluk_blogu(dil_sirasi):
    """i18n_common.js'teki app.sfst.* değerleri (0: EN, 1: TR blok)."""
    src = (STATIK / 'i18n_common.js').read_text(encoding='utf-8')
    bulunan = re.findall(r"'(app\.sfst\.[A-Za-z]+)': '([^']*)'", src)
    bloklar, simdiki = [], {}
    for k, v in bulunan:
        if k in simdiki:
            bloklar.append(simdiki)
            simdiki = {}
        simdiki[k] = v
    bloklar.append(simdiki)
    return bloklar[dil_sirasi]


def _tablo_adlari_tr():
    """i18n_common.js TR bloğundaki panel.structural.mode* (YAPISAL tablosu) adları."""
    src = (STATIK / 'i18n_common.js').read_text(encoding='utf-8')
    bulunan = re.findall(
        r"'(panel\.structural\.mode(?:Nozzle|EndCap|ChamberHoop|ChamberVm|Buckling))': '([^']*)'",
        src)
    tr = {}
    gorulen = set()
    for k, v in bulunan:
        if k in gorulen:
            tr[k] = v
        gorulen.add(k)
    assert len(tr) == 5, tr
    return tr


# --- kalem 2: istasyon adının tek İngilizcesi ---------------------------------

def test_istasyon_adlari_ekran_karti_ve_pdf_ile_ayni_ingilizce():
    """Gerekçedeki istasyon adı = ekran kartı (app.sfst.*) = PDF künyesi."""
    from hrma.export.pdf_generator import PDFReportGenerator
    assert STRUCTURAL_STATION_NAMES_EN == (
        PDFReportGenerator._SF_SCREEN_STATION_NAMES)
    en = _sozluk_blogu(0)
    assert sorted(STRUCTURAL_STATION_NAMES_EN.values()) == sorted(en.values())


def test_her_istasyon_anahtarinin_okunur_adi_var(gerekceler):
    """Çözümleyicinin yayımladığı her istasyon anahtarı haritada."""
    for sa in gerekceler.values():
        eksik = set(sa['safety_factors']) - set(STRUCTURAL_STATION_NAMES_EN)
        assert not eksik, eksik
    assert 'buckling_axial' in STRUCTURAL_STATION_NAMES_EN
    # Tanınmayan anahtar adıyla kalır, yerine başka ad konmaz.
    assert structural_station_list_en(['yeni_istasyon']) == 'yeni_istasyon'
    assert structural_station_list_en([]) == 'none'


# --- kalem 2: gerekçe cümlesi makine adı taşımaz -------------------------------

@pytest.mark.parametrize('vaka', sorted(_VAKALAR))
def test_hukum_gerekcesi_makine_adi_tasimaz(gerekceler, vaka):
    metin = gerekceler[vaka]['minimum_safety_factor_verdict_basis']
    assert not _MAKINE_ADI.findall(metin), (vaka, _MAKINE_ADI.findall(metin))
    # Alanların kendisi makine-okur yanıtta aynen durur (kaçış kapısı).
    sa = gerekceler[vaka]
    for alan in ('design_target_assessment', 'measured_scope_status',
                 'verdict_safety_factor'):
        assert alan in sa, alan


def test_dort_dal_da_uretiliyor(gerekceler):
    """Vakalar dört dalın dördünü de üretir (bekçi boşa koşmasın)."""
    for vaka, capa in (('b1_hepsi_boyutlandi', 'No acceptance is issued and'),
                       ('b2_kismi_olcum', 'No acceptance is issued: the'),
                       ('b3_ince_cidar', 'The verdict comes from'),
                       ('b4_hepsi_olculdu', 'Every station in the basket')):
        assert gerekceler[vaka][
            'minimum_safety_factor_verdict_basis'].startswith(capa), vaka
    assert 'Sections not verified: none' in gerekceler[
        'b3_hepsi_olculdu_ince']['minimum_safety_factor_verdict_basis']


@needs_node
def test_hukum_gerekcesi_tr_ekranda_turkce_en_ekranda_aynen(gerekceler,
                                                           tmp_path):
    adlar = sorted(_VAKALAR)
    metinler = [gerekceler[a]['minimum_safety_factor_verdict_basis']
                for a in adlar]
    out = _server_text(metinler, tmp_path)
    tr_ad = set(_sozluk_blogu(1).values())
    for ad, girdi, tr, en in zip(adlar, metinler, out['tr'], out['en']):
        assert en == girdi, ad
        assert tr.startswith(_TR_CAPA[ad]), (ad, tr[:120])
        assert not _MAKINE_ADI.findall(tr), (ad, _MAKINE_ADI.findall(tr))
        assert not _INGILIZCE.search(tr), (ad, tr)
        for en_ad in STRUCTURAL_STATION_NAMES_EN.values():
            # İngilizce istasyon adı TR cümlede kalmaz ('nozzle' gibi kısa
            # adlar Türkçe adın parçası olmadığı için kelime sınırıyla).
            assert not re.search(r'\b%s\b' % re.escape(en_ad), tr), (ad, en_ad)
    # V307/ŞERİT-GÜRÜLTÜ (DİL-SON KARAR 2): dört dal da YAPISAL tablosunun
    # adlarını (panel.structural.mode*) basar; şerit adları (app.sfst.*) hüküm
    # cümlesinde yok — aynı panelde aynı istasyona tek ad.
    b1 = out['tr'][adlar.index('b1_hepsi_boyutlandi')]
    tablo_ad = set(_tablo_adlari_tr().values())
    assert sum(1 for a in tablo_ad if a in b1) == len(tablo_ad), b1
    for tr in out['tr']:
        for a in tr_ad:
            if ' ' in a:      # çok sözcüklü şerit adları ('kamara çevresel gerilmesi', 'uç kapak')
                assert a not in tr, (a, tr[:160])
    # Boş liste 'none' TR'de 'yok'.
    bos = out['tr'][adlar.index('b3_hepsi_olculdu_ince')]
    assert 'Doğrulanmayan kesitler: yok; bunlardan yok' in bos, bos


@needs_node
def test_ters_mutasyon_eski_makine_adli_cumle_tr_ekranda_ingilizce_kalir(
        tmp_path):
    """Eski (makine adlı) cümle artık hiçbir desene uymaz: sunucu geri
    dönerse TR ekranda İngilizce kalır ve yukarıdaki bekçi kırmızıya döner."""
    eski = ('The verdict comes from verdict_safety_factor, the lowest safety '
            'factor actually measured on a drawn wall (chamber_hoop). This is '
            'a measured warning and is never suppressed. Sections not '
            'verified: none; of those, none only read the design target back.')
    out = _server_text([eski], tmp_path)
    assert out['tr'][0] == eski


# --- kalem 7 (O10): enjektör devre tablosu Cd ipucu ---------------------------

def _kes_fonksiyon(kaynak, ad):
    """Üst düzey (4 boşluk girintili) JS işlevini süslü parantez sayarak keser."""
    bas = kaynak.index('\n    function %s(' % ad)
    i = kaynak.index('{', bas + len(ad) + 12)
    derinlik, son = 0, i
    while son < len(kaynak):
        if kaynak[son] == '{':
            derinlik += 1
        elif kaynak[son] == '}':
            derinlik -= 1
            if derinlik == 0:
                break
        son += 1
    return kaynak[bas + 1:son + 1]


def _cd_ipucu_kos(tmp_path, cd_basis_listesi, statik=STATIK):
    """injector_panel.js circuitRows'u depodaki kaçış yardımcısıyla koşar."""
    panel = (statik / 'injector_panel.js').read_text(encoding='utf-8')
    dock = (statik / 'analysis_dock.js').read_text(encoding='utf-8')
    betik = (_kes_fonksiyon(dock, 'escAttr') + '\n'
             + 'const window = { AnalysisDock: { ui: { esc: escAttr } },\n'
             + '  I18N: { serverText: function (t) { return "TR:" + t; } } };\n'
             + 'function fmt(v) { return String(v); }\n'
             + _kes_fonksiyon(panel, 'circuitRows') + '\n'
             + 'const girdi = ' + json.dumps(cd_basis_listesi) + ';\n'
             + 'process.stdout.write(JSON.stringify(girdi.map(function (b) {\n'
             + '  const c = {n_orifices: 8, orifice_d_mm: 1.2, cd: 0.78,\n'
             + '             manifold: {}};\n'
             + '  if (b !== null) c.cd_basis = b;\n'
             + '  return circuitRows("ox", c); })));\n')
    yol = tmp_path / 'cd_ipucu.js'
    yol.write_text(betik, encoding='utf-8')
    p = subprocess.run([NODE, str(yol)], capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


@needs_node
def test_cd_ipucu_cevrilir_kacislanir_yoksa_title_yok(tmp_path):
    saldirgan = 'x" onmouseover="alert(1)" a="<b>'
    gercek = 'sharp inlet, short; L/D=0.5 -> Cd=0.63 (outside table, end value)'
    out = _cd_ipucu_kos(tmp_path, [saldirgan, gercek, None, ''])
    # (1) tırnak ve '<' öznitelikten taşmaz: hücrenin tek özniteliği title
    # ve style; ham tırnak/etiket yok.
    td = re.search(r'<td( title="[^"]*")? style="cursor:help;">0\.78</td>',
                   out[0])
    assert td and td.group(1), out[0]
    assert 'onmouseover="' not in out[0] and '<b>' not in out[0]
    assert '&quot;' in td.group(1) and '&lt;b&gt;' in td.group(1)
    # (2) metin çeviri kanalından geçer.
    assert 'title="TR:sharp inlet, short; L/D=0.5 -&gt; Cd=0.63' in out[1]
    # (3) dayanak yoksa / boşsa title özniteliği HİÇ yok.
    for html in out[2:]:
        assert 'title=' not in html, html


@needs_node
def test_cd_dayanagi_gercek_cumlesi_tr_ekranda_turkce(tmp_path):
    """Gerçek üretici cümlesi (salt okunur içe aktarma) TR'ye iner."""
    from hrma.engines.injector_design import discharge_coefficient
    cumleler = [discharge_coefficient('sharp', 1.23093)[1],
                discharge_coefficient('radiused', 40.0)[1]]
    out = _server_text(cumleler, tmp_path)
    for en, tr in zip(cumleler, out['tr']):
        assert tr != en, en
        # Künye parantezi kitap adı taşır ('Atomization and Sprays'):
        # İngilizce denetimi gerekçe kısmında.
        assert not _INGILIZCE.search(tr.split('; L/D=')[0]), tr
        assert '->' not in tr and 'L/D=' in tr
    assert 'L/D=1,23093 → Cd=0,78' in out['tr'][0]


# --- kalem 6 (O9 ikinci yarı): CFD çıkış basıncı açıklaması sayıdan türer -----

def _anahtar_degerleri(anahtar):
    """i18n_common.js'te anahtarın değerleri (sırayla EN bloğu, TR bloğu)."""
    src = (STATIK / 'i18n_common.js').read_text(encoding='utf-8')
    return re.findall(r"'%s': '((?:[^'\\]|\\.)*)'" % re.escape(anahtar), src)


@needs_node
def test_cfd_cikis_aciklamasi_gosterilen_sayilardan_turer(tmp_path):
    src = (STATIK / 'panels' / 'cfd_panel.js').read_text(encoding='utf-8')
    betik = ('function T(k, f) { return f; }\n'
             'function isNum(x) { return typeof x === "number" && isFinite(x); }\n'
             'function fmt(v, d) { return Number(v).toFixed(d); }\n'
             + _kes_fonksiyon(src, 'exitRecNoteText') + '\n'
             'process.stdout.write(JSON.stringify([\n'
             '  exitRecNoteText(1.173, 0.776, false),\n'   # çan (örnek sıvı)
             '  exitRecNoteText(0.971, 1.036, false),\n'   # konik (M-HIBRIT-37)
             '  exitRecNoteText(1.0002, 1.0001, true),\n'  # 3 ondalıkta eşit
             '  exitRecNoteText(null, 1.036, false),\n'
             ']));\n')
    yol = tmp_path / 'not.js'
    yol.write_text(betik, encoding='utf-8')
    p = subprocess.run([NODE, str(yol)], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr[-2000:]
    can, konik, esit, eksik = json.loads(p.stdout)
    for metin in (can, konik, esit, eksik):
        assert 'bell nozzle' not in metin   # sabit genelleme yok
        assert metin.startswith('Compare the 1-D exit pressure')
    assert 'is above the section average' in can and 'throttle' not in can
    assert 'is below the section average' in konik and 'throttle' not in konik
    assert 'equals the section average' in esit and 'throttle point' in esit
    assert 'section average.' not in eksik.split('pressure.')[-1]
    assert 'throttle' not in eksik


def test_cfd_cikis_aciklamasi_anahtarlari_iki_dilde():
    for k in ('panel.cfd.exitRecNote', 'panel.cfd.exitRecWallAbove',
              'panel.cfd.exitRecWallBelow', 'panel.cfd.exitRecWallEqual',
              'panel.cfd.exitRecThrottle'):
        d = _anahtar_degerleri(k)
        assert len(d) == 2 and d[0] != d[1], (k, d)
    en, tr = _anahtar_degerleri('panel.cfd.exitRecNote')
    assert 'bell' not in en and 'çan' not in tr


# --- kalem 8b: PDF derleminin bugünkü çözücü parçaları -----------------------

_PDF_PARCALARI = [
    'Chug (design point):',
    'feed-coupled chug loop model STABLE (growth rate -282,076 1/s, 62,8418 Hz).',
    'feed-coupled chug loop model UNSTABLE (growth rate 63,2952 1/s, 37,4343 Hz)',
    'The built-in size-corrected two-phase (particle-lag) loss estimate of '
    'hrma.analysis.two_phase_loss for this motor is 3.92 %, but it is NOT '
    'applied: a nozzle or kinetic efficiency was supplied with the request.',
    'The thrust coefficient therefore carries no separate two-phase factor '
    '(two_phase_efficiency_applied = 1.0).',
    "oxidizer_type 'lox' names no hybrid oxidiser with a derived TNT "
    'equivalence (derived: h2o2, n2o), so no TNT-equivalent class was won. '
    'The product default oxidiser is NOT substituted for a named oxidiser '
    'HRMA cannot identify.',
    'Throttle map: ratio rule met but the loop model does not say stable at '
    '85 %, 100 % (not counted as stable).',
    "your limit 800 K can only be checked against a SOLVED wall temperature "
    "and none exists on this run - cooling_type 'ablative': HRMA has no "
    'wall-temperature solver for a passively cooled wall in this chain '
    '(passive_thermal_protection sizes the liner/heat sink, it does not '
    'publish an equilibrium wall temperature). The cooling numbers were '
    'evaluated AT your target (a requirement); that does not show the wall '
    'stays below it.',
]


@pytest.mark.parametrize('parca', _PDF_PARCALARI)
def test_pdf_cozucu_parcasi_turkceye_iner_alan_adi_birakmaz(parca):
    """PDF çevirmeni (ekranla aynı sözlük) bugünkü derlemin parçasını çevirir;
    TR çıktıda İngilizce işlev sözcüğü ve alt çizgili alan adı kalmaz."""
    from hrma.export import rapor_sozluk
    tr = rapor_sozluk.cevir(parca, 'tr')
    assert tr != parca, parca
    assert not _INGILIZCE.search(tr), tr
    assert not re.search(r'(?<![\w.])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?!\w)', tr), tr
    for sayi in re.findall(r'\d+', parca.split('hrma.')[0]):
        assert sayi in tr, (sayi, tr)   # sayı kaybolmaz / değişmez


@needs_node
def test_besinci_dal_gecerlilik_disi_gerekce_alan_yolu_tasimaz(tmp_path):
    """5. dal (MODEL_VALIDITY_VERDICT_BASIS) EN ve TR ekranda alan yolu yerine
    ölçütün kendisini söyler; bayrak alanı yanıtta aynen durur."""
    from hrma.analysis.structural_analysis import MODEL_VALIDITY_VERDICT_BASIS
    assert not _MAKINE_ADI.findall(MODEL_VALIDITY_VERDICT_BASIS)
    assert 'melting point' in MODEL_VALIDITY_VERDICT_BASIS
    out = _server_text([MODEL_VALIDITY_VERDICT_BASIS], tmp_path)
    tr = out['tr'][0]
    assert tr != MODEL_VALIDITY_VERDICT_BASIS
    assert tr.startswith('Ne onay ne de sayısal tasarım hükmü verildi')
    assert not _MAKINE_ADI.findall(tr), tr
    assert 'erime noktasında' in tr


# --- kalem 3 / 4: yeni anahtarlar iki dilde, Türkçe karşılık makine adı taşımaz -

@pytest.mark.parametrize('anahtar', [
    'panel.structural.mvMotorWhere', 'panel.structural.mvBlockCase',
    'panel.structural.mvBlockChamber', 'panel.structural.mvBlockChamberStructure',
    'panel.structural.mvMessageWithheld',
    'panel.nzl.frictionSrcUndeclared', 'panel.nzl.frictionSrcMeasured',
    'panel.nzl.frictionSrcUser', 'panel.nzl.frictionSrcLegacy',
    'panel.nzl.thrustDefSolved', 'panel.nzl.thrustDefEffective',
    'panel.nzl.thrustDefFullFlow', 'panel.nzl.thrustDefRatio'])
def test_yeni_anahtar_iki_dilde_makine_adsiz(anahtar):
    d = _anahtar_degerleri(anahtar)
    assert len(d) == 2 and d[0] != d[1], (anahtar, d)
    for metin in d:
        assert not _MAKINE_ADI.findall(metin), (anahtar, metin)
    assert re.search('[çğıöşüÇĞİÖŞÜ]', d[1]), d[1]
