"""V307/ONARIM2-İTKİ — motor sayfalarındaki kalan hatalar (dalga 2) bekçisi.

Kanıt: docs/scofield/raw/OH/V307/onarim2-itki/RAPOR.md.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')


def _tr_cevir(metinler, dosya='i18n_charts.js', islev='chartText'):
    betik = r"""
const fs=require('fs');
global.window=global; global.I18N={lang:'tr', register:function(){}};
eval(fs.readFileSync(__YOL__,'utf8'));
const g=__VERI__;
process.stdout.write(JSON.stringify(g.map(function(s){return global.I18N.__ISLEV__(s);})));
"""
    betik = (betik.replace('__YOL__', json.dumps(str(JS / dosya)))
             .replace('__VERI__', json.dumps(metinler))
             .replace('__ISLEV__', islev))
    p = subprocess.run([NODE], input=betik, capture_output=True,
                       text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


# ---------------------------------------------------------------------------
# Madde 1 — M7-ITKI-8 sıvı yanı: 3B performans yüzeyi NASA CEA ile
# ---------------------------------------------------------------------------
SIVI_VAKUM = {'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'base_isp': 322.4,
              'optimal_of_ratio': 2.0, 'optimal_chamber_pressure': 50.0,
              'expansion_ratio': 61.0, 'design_point_source': 'solver',
              'design_ambient': {'mode': 'vacuum'}, 'grid_n': 3}


@pytest.fixture(scope='module')
def sivi_yuzey():
    from hrma.visualization import visualization as v
    return json.loads(
        v.create_chamber_pressure_mixture_ratio_3d_surface(dict(SIVI_VAKUM)))


def _not_maddeleri(fig):
    a = [x for x in fig['layout']['annotations']
         if (x.get('text') or '').startswith('- ')][0]
    return [re.sub(r'<br>  ', ' ', m).lstrip('- ')
            for m in a['text'].split('<br>- ')]


def _duz_not(fig):
    return ' '.join(_not_maddeleri(fig))


def test_m7_itki_8_sivi_cift_cea_cozucusune_gider():
    from hrma.visualization import visualization as v
    assert v._surface_solver_kind({'rp1': 100.0}, 'lox') == \
        v.PERF_SURFACE_SOLVER_CEA
    assert v._surface_solver_kind({'methane': 100.0}, 'lox') == \
        v.PERF_SURFACE_SOLVER_CEA
    # Hibrit yakıtlar hibrit çözücüde kalır (bugünkü yol, bit-aynı).
    for yakit, oks in (('htpb', 'n2o'), ('paraffin', 'lox'), ('htpb', 'N2O')):
        assert v._surface_solver_kind({yakit: 100.0}, oks) == \
            v.PERF_SURFACE_SOLVER_HYBRID


def test_m7_itki_8_sivi_yuzey_cozulur_ve_dugum_cea_ile_ayni(sivi_yuzey):
    from hrma.engines.cea_bridge import get_matched_expansion_isp
    from hrma.visualization import visualization as v
    yuzey = sivi_yuzey['data'][0]
    z = np.array(yuzey['z'], dtype=float)
    assert np.isfinite(z).all(), z
    altbaslik = sivi_yuzey['layout']['title']['text']
    assert '9/9 nodes solved' in altbaslik and 'LOX / RP1' in altbaslik
    assert 'reference pair' not in altbaslik
    # Düğüm (Pc 55, O/F 3,5) = cea_bridge'in eşleşik genleşme Isp'si
    beklenen = get_matched_expansion_isp(
        'rp1', 'lox', 55.0, 3.5, v._surface_exit_pressure_bar())['isp_s']
    assert z[1, 1] == pytest.approx(beklenen, rel=1e-12)


def test_m7_itki_8_eslesik_genlesme_tanimi():
    """Isp_eşleşik = Isp_vak − c*·ε/(Pc/Pe)/g0 ve çıkış basıncı istenen."""
    from hrma.engines.cea_bridge import get_matched_expansion_isp
    r = get_matched_expansion_isp('rp1', 'lox', 50.0, 2.0, 1.01325)
    assert r['source'] == 'rocketcea'
    assert r['exit_pressure_bar'] == pytest.approx(1.01325, rel=1e-3)
    assert r['isp_s'] < r['isp_vac_s']
    assert r['isp_s'] == pytest.approx(
        r['isp_vac_s'] - r['c_star_m_s'] * r['expansion_ratio']
        * r['exit_pressure_bar'] / 50.0 / 9.80665, rel=1e-9)
    # Ölçülen değer (RAPOR "yayımlanan sayılar"): 282,87 s, ε 6,77
    assert r['isp_s'] == pytest.approx(282.865, abs=0.01)
    assert r['expansion_ratio'] == pytest.approx(6.772, abs=0.01)
    for kotu in (('htpb', 'n2o', 50.0), ('rp1', 'lox', 0.5)):
        with pytest.raises(ValueError):
            get_matched_expansion_isp(kotu[0], kotu[1], kotu[2], 2.0, 1.01325)


def test_m7_itki_8_vakum_tasarim_noktasi_yuzey_tabaninda_cizilir(sivi_yuzey):
    from hrma.engines.cea_bridge import get_matched_expansion_isp
    from hrma.visualization import visualization as v
    hac = [t for t in sivi_yuzey['data']
           if (t.get('marker') or {}).get('symbol') == 'cross']
    assert len(hac) == 1, [t.get('name') for t in sivi_yuzey['data']]
    hac = hac[0]
    beklenen = get_matched_expansion_isp(
        'rp1', 'lox', 50.0, 2.0, v._surface_exit_pressure_bar())['isp_s']
    assert hac['x'] == [50.0] and hac['y'] == [2.0]
    assert hac['z'][0] == pytest.approx(beklenen, rel=1e-12)
    kunye = hac['hovertemplate']
    assert '322.4 s at expansion ratio 61.00' in kunye
    assert 'design ambient: vacuum' in kunye
    assert ('Difference: %+.1f s' % (322.4 - beklenen)) in kunye
    duz = _duz_not(sivi_yuzey)
    assert 'is NOT drawn on this surface' not in duz
    assert 'NASA CEA (RocketCEA; Gordon & McBride, NASA RP-1311)' in duz
    assert 'Pe = 1.01325 bar' in duz
    assert 'Sea-level expansion (Pe = 1.01325 bar) is used for Isp.' not in duz


def test_m7_itki_8_beyansiz_ortamda_tavan_kapisi_korunur():
    """P14H1-C1 kapısı: ortam beyansız, tavanın üstündeki sayı çizilmez."""
    from hrma.visualization import visualization as v
    ed = dict(SIVI_VAKUM)
    ed.pop('design_ambient')
    fig = json.loads(v.create_chamber_pressure_mixture_ratio_3d_surface(ed))
    assert not [t for t in fig['data']
                if (t.get('marker') or {}).get('symbol') == 'cross']
    assert 'The design point is NOT drawn on this surface' in _duz_not(fig)


@node_gerekli
def test_m7_itki_8_sivi_kunyesi_tr(sivi_yuzey):
    hac = [t for t in sivi_yuzey['data']
           if (t.get('marker') or {}).get('symbol') == 'cross'][0]
    satirlar = hac['hovertemplate'].replace('<extra></extra>', '').split('<br>')
    madde = _not_maddeleri(sivi_yuzey)
    tr = _tr_cevir(satirlar + madde)
    ingilizce = re.compile(r'\b(drawn|surface|basis|nodes|solved|Difference|'
                           r'expansion|efficiencies|thermochemistry|Same)\b')
    for kaynak, cevrilen in zip(satirlar + madde, tr):
        assert not ingilizce.search(cevrilen), (kaynak, cevrilen)
    assert any('NASA CEA ile çözülür' in t for t in tr), tr
    assert any(t.startswith('Fark: ') and 'taban farkıdır' in t for t in tr), tr


# ---------------------------------------------------------------------------
# Madde 2 — M7-ITKI-4: KORELASYON paneli ham JSON / iç ad basmaz
# ---------------------------------------------------------------------------
KOR_OZET = {
    'status_counts': {'insufficient_inputs': 2, 'not_supported': 1, 'ok': 3},
    'not_supported': [{'test_id': 'liq-x', 'reason': 'r'}],
    'insufficient_inputs': [
        {'missing': ['burn_time', 'mdot_ox'], 'test_id': 'hyb-amroc1993-a'},
        {'missing': ['port_diameter_initial'], 'test_id': 'hyb-b'}],
    'runner_errors': [],
    'skipped_score_counts': {'curve_skipped_v1': 4, 'duplicate_base': 28,
                             'no_prediction': 153},
}
KOR_HUCRELER = [
    {'motor_type': 'solid', 'quantity': 'chamber_pressure_avg', 'layer': 'main',
     'n': 3, 'bias_percent': 1.0, 'rms_percent': 2.0, 'median_ape_percent': 1.5},
    {'motor_type': 'liquid', 'quantity': 'isp_sl', 'layer': 'main',
     'n': 2, 'bias_percent': -1.0, 'rms_percent': 2.0, 'median_ape_percent': 1.5},
]


def _korelasyon_html(dil):
    betik = r"""
const fs=require('fs');
global.window=global;
let D=null; global.I18N={register:function(d){D=d;}};
eval(fs.readFileSync(__I18N__,'utf8'));
const dil=__DIL__;
function t(k, fb){ const v=(D[dil]||{})[k]; return (v===undefined)?fb:v; }
function tf(k, p, fb){ let s=t(k, fb); Object.keys(p||{}).forEach(function(a){ s=s.split('{'+a+'}').join(String(p[a])); }); return s; }
global.document={createElement:function(){return {style:{}, appendChild:function(){}};},
  getElementById:function(){return null;}, readyState:'complete',
  addEventListener:function(){}};
global.setInterval=function(){return 0;}; global.clearInterval=function(){};
global.setTimeout=function(){return 0;};
global.AnalysisDock={ui:{t:t, tf:tf, num:function(x,d){return Number(x).toFixed(d);},
  TD:'', TBL:'', sectionTitle:function(s){return '<h4>'+s+'</h4>';}, esc:function(s){return String(s);}},
  register:function(){}, getMotorType:function(){return 'solid';}};
eval(fs.readFileSync(__PANEL__,'utf8'));
const P=window.CorrelationPanel;
const ozet=__OZET__;
process.stdout.write(JSON.stringify({
  ozet: P._skippedSummaryHtml(ozet),
  rapor: P._raporMetniHtml('# rapor', ozet),
  tablo: P._cellTableHtml(__HUCRE__),
  anahtarlar: Object.keys(P._quantityKeys),
  nedenler: Object.keys(P._skipReasonKeys)}));
"""
    betik = (betik.replace('__I18N__', json.dumps(str(JS / 'i18n_common.js')))
             .replace('__PANEL__', json.dumps(str(JS / 'panels' / 'correlation_panel.js')))
             .replace('__DIL__', json.dumps(dil))
             .replace('__OZET__', json.dumps(KOR_OZET))
             .replace('__HUCRE__', json.dumps(KOR_HUCRELER)))
    p = subprocess.run([NODE], input=betik, capture_output=True,
                       text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


def _gorunen(html):
    """Ekranda görünen metin: etiketler ve nitelikler atılır."""
    return re.sub(r'<[^>]+>', ' ', html)


@node_gerekli
@pytest.mark.parametrize('dil', ['tr', 'en'])
def test_m7_itki_4_atlama_ozeti_okunur_tablo(dil):
    o = _korelasyon_html(dil)
    gorunen = _gorunen(o['ozet'])
    for ham in ('{', '[', '"missing"', 'insufficient_inputs', 'skipped_score_counts',
                'status_counts', 'curve_skipped_v1', 'no_prediction', 'hyb-amroc'):
        assert ham not in gorunen, (ham, gorunen)
    # neden → sayı: listelerin uzunluğu ve sayım sözlüğünün değeri
    assert re.search(r'>\s*2\s*<', o['ozet']) and re.search(r'>\s*153\s*<', o['ozet'])
    if dil == 'tr':
        assert 'yetersiz girdi' in gorunen
        assert 'Bu büyüklük için model tahmini yok' in gorunen
        assert 'Aynı büyüklük kayıtta iki kez bildirilmiş' in gorunen
    else:
        assert 'No model prediction for this quantity' in gorunen
    # Ham özet yalnız "Tam rapor metni" açılırında
    assert '<details' in o['rapor'] and 'data-correlation-skipped-raw' in o['rapor']
    assert 'hyb-amroc1993-a' in o['rapor']


@node_gerekli
@pytest.mark.parametrize('dil', ['tr', 'en'])
def test_m7_itki_4_buyukluk_adi_gorunen_adla(dil):
    o = _korelasyon_html(dil)
    gorunen = _gorunen(o['tablo'])
    assert 'chamber_pressure_avg' not in gorunen and 'isp_sl' not in gorunen
    if dil == 'tr':
        assert 'Ortalama oda basıncı' in gorunen
        assert 'Deniz seviyesi özgül itkisi' in gorunen
    else:
        assert 'Average chamber pressure' in gorunen


@node_gerekli
def test_m7_itki_4_kosucunun_her_buyuklugu_ve_nedeni_adli():
    """Ad tablosu koşucunun yayımlayabildiği her kodu kapsar."""
    o = _korelasyon_html('tr')
    adaptor = (KOK / 'hrma' / 'validation' / 'record_adapters.py').read_text(
        encoding='utf-8')
    kosucu = (KOK / 'hrma' / 'validation' / 'correlation_runner.py').read_text(
        encoding='utf-8')
    tahmin = set(re.findall(r'predictions\["([a-z_0-9]+)"\]', adaptor))
    for blok in re.findall(r'(?:result\["predictions"\]|predictions) = \{(.*?)\}',
                           adaptor, re.S):
        tahmin |= set(re.findall(r'"([a-z_0-9]+)":', blok))
    tahmin -= {'quantities', 'reason', 'reason_code'}
    tahmin.add('web_burn_time_vs_action_time')   # SOLID_CROSS_DEFINITION_TIME
    assert tahmin and tahmin <= set(o['anahtarlar']), sorted(tahmin - set(o['anahtarlar']))
    nedenler = set(re.findall(r'"status": "([a-z_0-9]+)"', kosucu)) - {'scored'}
    assert nedenler and nedenler <= set(o['nedenler']), sorted(nedenler - set(o['nedenler']))


# ---------------------------------------------------------------------------
# Madde 3 — sıvı TR teknik PDF'te İngilizce / iç adlı dayanak satırları
# ---------------------------------------------------------------------------
_KAYNAK = ('solved: 1D RP-1 regenerative station march, peak hot-gas-side wall '
           '(thermal_protection.station_march.peak_wall_temperature_K)')


def _pdf_satirlari():
    from hrma.engines import liquid_rocket_engine as L
    iki = ('two-layer regenerative wall: the verdict quantities of this block '
           '(yield strength at the wall temperature, allowable stress, stress '
           'margin, hoop safety factor) belong to the CLOSEOUT, the layer that '
           'carries the coolant pressure, at its own temperature; the liner is '
           'judged at its own temperatures in the wall-layer rows. '
           + L.CLOSEOUT_TEMPERATURE_BASIS)
    tek = ('the verdict quantities (yield strength at the wall temperature, '
           'allowable stress, stress margin, hoop safety factor, the throat '
           'meridional safety factor and the model validity check) are '
           'evaluated at the SOLVED peak hot-wall temperature 905.3 K ('
           + _KAYNAK + '). The wall THICKNESS was sized at the design wall '
           'temperature target 800 K: the solver itself runs on the drawn '
           'wall, so a solved peak above the target shows up here as a lower '
           'safety factor on that wall, not as a re-sized wall.')
    return [
        'Limit check: solved peak hot-wall temperature 614.6 K (' + _KAYNAK
        + ') compared with your maximum wall temperature 800 K',
        'Structural verdict wall temperature: ' + iki,
        'Structural verdict wall temperature: ' + tek,
        'Wall model: ' + L.WALL_MODEL_TWO_LAYER_BASIS,
        'PROPERTY RANGE (WALL): the rp1 coolant-side wall temperature is above '
        'the internal property table band (290-500 K) at 39 station(s); the '
        'Sieder-Tate wall viscosity there is held at the band edge, so the '
        '(mu_b/mu_w)^0.14 correction is UNDER-stated and the coolant-side '
        'coefficient is a conservative lower bound (peak correction factor '
        'used 1.294).',
    ]


def test_madde3_cozucu_metni_ic_alan_adi_tasimaz():
    """Kaynak metin (EN de) iç alan adı taşımaz; iki dayanak cümlesi aynen
    üretilen metinle aynı (sözlük ile kaynak birlikte değişsin)."""
    kaynak = (KOK / 'hrma' / 'engines' / 'liquid_rocket_engine.py').read_text(
        encoding='utf-8')
    for ic_ad in ("(yield_strength_at_wall_temp, '", 'in wall_layers. ',
                  'wall_temperature_design_target_K = '):
        assert ic_ad not in kaynak, ic_ad
    assert "'this block (yield strength at the wall temperature, '" in kaynak
    assert "f\"target {float(s['wall_temperature_k']):g} K: the solver \"" in kaynak


def test_madde3_tr_pdf_satirlari_turkce():
    from hrma.export import rapor_sozluk as rs
    ingilizce = re.compile(r'\b(solved|peak|compared|verdict|quantities|block|'
                           r'closeout|liner|layer|construction|outer|wall|'
                           r'station|UNDER-stated|coolant|correction|sized)\b')
    for satir in _pdf_satirlari():
        tr = rs.cevir(satir, 'tr')
        assert not ingilizce.search(tr), (satir[:60], tr)
        for ic_ad in ('yield_strength', 'wall_layers', '_K =', 'design_target'):
            assert ic_ad not in tr, (ic_ad, tr)
    # EN belge bit-aynı metin (çeviri katmanı EN'ye dokunmaz)
    for satir in _pdf_satirlari():
        assert rs.cevir(satir, 'en') == satir


# ---------------------------------------------------------------------------
# Madde 4 — hibrit TR PDF girdi uyarısı: iç ad + sayfanın gönderdiği 0
# ---------------------------------------------------------------------------
@node_gerekli
def test_madde4_sifir_otomatik_alanlar_govdeye_gitmez():
    from tests.test_d36_hibrit_a1 import _govde
    g = _govde(deger={'expansion_ratio': '0', 'chamber_diameter_input': '0'})
    assert 'expansion_ratio' not in g and 'chamber_diameter_input' not in g
    g = _govde(deger={'expansion_ratio': '6.5', 'chamber_diameter_input': '90'})
    assert g['expansion_ratio'] == 6.5 and g['chamber_diameter_input'] == 90


@pytest.mark.parametrize('dil,etiket', [('tr', 'Ae/At Oranı'), ('en', 'Ae/At Ratio')],
                         ids=['tr', 'en'])
def test_madde4_pdf_uyarisi_alani_form_etiketiyle_verir(dil, etiket):
    from hrma.export import rapor_sozluk as rs
    from hrma.export.pdf_generator import PDFReportGenerator as G
    kayit = {'code': 'warn.input.solved_by_model',
             'params': {'field': 'expansion_ratio', 'submitted': 0.0,
                        'used': 5.03548}}
    with rs.dil_baglami(dil):
        cumle = G._warning_sentence(kayit)
    assert "'%s'" % etiket in cumle, cumle
    assert 'expansion_ratio' not in cumle
    # Formda karşılığı olmayan ad aynen kalır (etiket uydurulmaz).
    kayit2 = dict(kayit, params=dict(kayit['params'], field='olmayan_alan'))
    with rs.dil_baglami(dil):
        assert 'olmayan_alan' in G._warning_sentence(kayit2)


# ---------------------------------------------------------------------------
# Madde 5 — ısı akısı figürü künyesi TR ekranda İngilizce + malzeme 'steel'
# ---------------------------------------------------------------------------
@node_gerekli
def test_madde5_isi_akisi_kunyesi_tr():
    from hrma.visualization import visualization as v
    kaynak = (KOK / 'hrma' / 'visualization' / 'visualization.py').read_text(
        encoding='utf-8')
    # Künye üreticisi değişirse desen de değişmeli (aynı cümle).
    assert 'f"Bartz axial profile | peak surface flux "' in kaynak
    assert v.HEATFLUX_FIG_DEFAULT_MATERIAL == 'steel'
    satir = ('Bartz axial profile | peak surface flux 35.59 MW/m2 (cold wall, '
             't = 0) | peak design flux 26.04 MW/m2 at the throat (reference '
             'cooled wall) | lumped-capacitance wall (steel, 3.0 mm), '
             'Biot_max = 0.01')
    varsayim = ('Assumed (not supplied by this call): wall material = steel, '
                'wall thickness = 3.0 mm')
    tr = _tr_cevir([satir, varsayim])
    assert tr[0].startswith('Bartz eksenel profili | tepe yüzey akısı ')
    assert 'toplu kapasiteli cidar (çelik, ' in tr[0]
    assert 'cidar malzemesi = çelik' in tr[1]
    ingilizce = re.compile(r'\b(axial|profile|peak|flux|wall|throat|steel|'
                           r'lumped|reference|cooled|material)\b')
    for t in tr:
        assert not ingilizce.search(t), t


# ---------------------------------------------------------------------------
# Madde 6 — sıvı "Uzay Uygulaması: Çok irtifalı iyileştirilmiş tasarım"
# hesaptan gelmeyen sabit hüküm: satır ve anahtarları kaldırıldı
# ---------------------------------------------------------------------------
def test_madde6_hesapsiz_uzay_uygulamasi_hukmu_yok():
    sablon = (KOK / 'hrma' / 'templates' / 'liquid.html').read_text(encoding='utf-8')
    sozluk = (JS / 'i18n_pages.js').read_text(encoding='utf-8')
    for iz in ('liq.js.space_application', 'liq.js.multi_altitude_optimized_design',
               'Multi-altitude optimized design', 'Space Application:',
               'Çok irtifalı iyileştirilmiş tasarım', 'Uzay Uygulaması'):
        assert iz not in sablon, iz
        assert iz not in sozluk, iz


# ---------------------------------------------------------------------------
# Madde 7 + 8 — hibrit plaka malzemesi ve yörünge son kütle ipuçları
# ---------------------------------------------------------------------------
def _sozluk_degeri(metin, anahtar, dil):
    tr_bas = metin.index('        tr: {') if '        tr: {' in metin else None
    bolge = metin[tr_bas:] if dil == 'tr' else metin[:tr_bas]
    m = re.search(r"'%s': '((?:[^'\\]|\\.)*)'" % re.escape(anahtar), bolge)
    assert m, (anahtar, dil)
    return m.group(1)


def test_madde7_plaka_ipucu_sivi_hukmuyle_ayni_kapsam():
    adv = (JS / 'i18n_advanced.js').read_text(encoding='utf-8')
    sayfa = (JS / 'i18n_pages.js').read_text(encoding='utf-8')
    sablon = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(encoding='utf-8')
    en_kapsam = ('The start/shutdown load is a quasi-static upper bound that '
                 'excludes pressure surges. Water hammer, dynamic amplification, '
                 'thermal stress and fatigue are not modelled.')
    tr_kapsam = ('Marş/kesme yükü yarı-statik bir üst sınırdır; basınç darbeleri '
                 'hariçtir. Su koçu, dinamik büyütme, ısıl gerilme ve yorulma '
                 'modellenmez.')
    # Sıvı plaka hükmü aynı kapsamı söylüyor (tek kapsam, iki sayfa).
    assert en_kapsam in _sozluk_degeri(sayfa, 'liq.ui.injplate_analyzed', 'en')
    assert tr_kapsam in _sozluk_degeri(sayfa, 'liq.ui.injplate_analyzed', 'tr')
    assert en_kapsam in _sozluk_degeri(adv, 'adv.tip.injectorMaterial', 'en')
    assert tr_kapsam in _sozluk_degeri(adv, 'adv.tip.injectorMaterial', 'tr')
    assert 'Pressure surges (water hammer) and thermal stress are not modelled' not in sablon
    assert sablon.count(en_kapsam) == 2      # ipucu + seçicinin title'ı


def test_madde8_son_kutle_ipucu_alti_serbestlik_cift_sayim():
    adv = (JS / 'i18n_advanced.js').read_text(encoding='utf-8')
    sablon = (KOK / 'hrma' / 'templates' / 'advanced.html').read_text(encoding='utf-8')
    en = _sozluk_degeri(adv, 'adv.tip.finalMassKg', 'en')
    tr = _sozluk_degeri(adv, 'adv.tip.finalMassKg', 'tr')
    assert 'separate Payload Mass field, so do not enter the payload in both places' in en
    assert 'faydalı yükü iki yere birden girmeyin' in tr
    # Yedek metin = sözlüğün EN metni
    m = re.search(r'data-i18n="adv\.tip\.finalMassKg">([^<]*)</span>', sablon)
    assert m and m.group(1) == en
    # İddia koddan: son kütle 6-DOF kuru kütlesine gider, panelde ayrı yük alanı var.
    assert "dry_mass_kg: 'final_mass'" in sablon
    sixdof = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
    assert "id: 'sd_payload_m'" in sixdof


def test_m7_itki_8_legend_notun_ustune_binmez(sivi_yuzey):
    """4 izli yüzeyde (inceltilmiş tavan + haç) tema legend'ı alt nota
    taşıyordu (plotly_dark.js maybeBottomLegend: konum verilmemişse 4+ iz →
    y = −0,25). Konum açık: yatay, çizimin hemen üstünde; başlık kabın
    tepesinde; üst marjın fazlası yüksekliğe eklenir."""
    from hrma.visualization import visualization as v
    lay = sivi_yuzey['layout']
    assert len(sivi_yuzey['data']) >= 4
    lg = lay['legend']
    assert (lg['orientation'], lg['y'], lg['yanchor']) == ('h', 1.0, 'bottom')
    assert lay['margin']['t'] == v.PERF_SURFACE_MARGIN_T_PX
    assert lay['height'] == 700 + (v.PERF_SURFACE_MARGIN_T_PX - 100)
    assert (lay['title']['yref'], lay['title']['yanchor']) == ('container', 'top')
