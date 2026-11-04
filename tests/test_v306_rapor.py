"""V306/RAPOR-HATA bekçileri — indirilen raporlar ve DOĞRULAMA paneli
(3.0.6, mühendis turu 2 Kas).

D1  DOĞRULAMA paneli motorun KENDİ itki eğrisini kullanır (M-KATI-1): katı
    motorda kıyas eğrisi motorun ``thrust_curve``'üdür (uçuşla aynı tek
    kural, flight_vehicle.motor_flight_thrust); tepe itki Performans
    Özeti'nin ``max_thrust``ıdır. Sıvıda (kararlı rejim modeli eğri
    yayımlamaz) dikdörtgen kalır ve NEDENİ doğru yazılır; "Geçici rejim F(t)
    yoktu" cümlesi kalmaz. Zaman Çözümlü paneli öncelik almaz.

Vakalar mühendis turunun gerçek API gövdeleridir
(docs/scofield/raw/OH/V306/muhendis-turu/*/vakalar/L*.json). Kanıt ve ters
mutasyonlar: docs/scofield/raw/OH/V306/rapor/RAPOR.md.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from hrma.analysis.flight_vehicle import normalize
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
VP_JS = JS / 'panels' / 'validation_panel.js'
VAKA = KOK / 'docs/scofield/raw/OH/V306/muhendis-turu'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')
TIP = {'sivi': 'liquid', 'hibrit': 'hybrid', 'kati': 'solid'}


def _vaka(sistem, L):
    yol = kanit_gerekli(VAKA / sistem / 'vakalar' / (L + '.json'))
    return json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))


def _govde(vaka, uc):
    return dict([r for r in vaka['istekler'] if r['uc'] == uc][-1]['govde'])


def _sonuc(sistem, L):
    """Turun /api/flight-vehicle gövdesindeki ``results`` = sayfanın
    currentResults'ı (aynı hesap)."""
    return _govde(_vaka(sistem, L), '/api/flight-vehicle')['results']


# ---------------------------------------------------------------------------
# D1 — DOĞRULAMA paneli (node altında GERÇEK validation_panel.js)
# ---------------------------------------------------------------------------
VP_HARNESS = r"""
'use strict';
const fs = require('fs');
const girdi = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
function dugum(id) {
    return { id: id, innerHTML: '', textContent: '', style: {}, value: '',
             children: [], firstElementChild: null,
             appendChild(c) { this.children.push(c); return c; },
             insertBefore(c) { this.children.push(c); return c; },
             addEventListener() {}, setAttribute() {}, getAttribute() { return null; } };
}
const dugumler = {};
global.document = {
    readyState: 'complete',
    getElementById(id) { if (!(id in dugumler)) dugumler[id] = dugum(id); return dugumler[id]; },
    createElement() { return dugum(null); },
    querySelectorAll() { return []; },
    addEventListener() {},
};
global.window = global;
function tf(k, p, fb) {
    return String(fb).replace(/\{(\w+)\}/g, (b, a) => (p && a in p) ? String(p[a]) : b);
}
const U = {
    t: (k, fb) => fb, tf: tf, esc: s => String(s), fmt: (v) => String(v),
    num: (v) => String(v), sectionTitle: s => '<h>' + s + '</h>',
    badge: s => '<b>' + s + '</b>', listBlock: (h, xs) => '<l>' + h + ': ' + xs.join(' | ') + '</l>',
    statCard: (a, b, c) => '<c>' + a + ' ' + b + ' ' + c + '</c>', purgePlots() {},
    kindColor: () => '#000', motorDict: r => (r && r.motor) || r || {},
};
global.AnalysisDock = { ui: U, register() {} };
window.currentResults = girdi.results;
window.FlightHandoff = { vehicleFor: r => (r === window.currentResults ? girdi.vehicle : null),
                         vehicleReady: r => Promise.resolve(r === window.currentResults ? girdi.vehicle : null) };
require(process.argv[3]);
const pred = window.ValidationPanel._predictedCurve();
const kok = dugum('kok');
window.ValidationPanel._render({ parsed: { time: [0, 1], thrust: [0, 1], n_points: 2 },
    comparison: { grade: 'poor', metrics: {} }, _predicted: pred }, kok);
const html = kok.children.map(c => c.innerHTML).join('\n');
process.stdout.write(JSON.stringify({ pred: pred, html: html }));
"""


def _vp_kos(results, vehicle, tmp_path):
    betik = tmp_path / 'vp.js'
    betik.write_text(VP_HARNESS, encoding='utf-8')
    veri = tmp_path / 'vp.json'
    veri.write_text(json.dumps({'results': results, 'vehicle': vehicle}),
                    encoding='utf-8')
    p = subprocess.run([NODE, str(betik), str(veri), str(VP_JS)],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


@needs_node
def test_D1_kati_dogrulama_motorun_itki_egrisini_kullanir(tmp_path):
    """M-KATI-1: L1 (KSB-002 kopyası) — kıyas eğrisi motorun eğrisidir.

    ÖLÇÜLDÜ (taban 686c34b98, rapor/once/tarayici_tr.json): gönderilen
    predicted_curve 2 noktalı {0, 1,8648 s} × 1 139,86 N dikdörtgendi;
    tepe itki 1 140 ⟷ Performans Özeti 1 258 N.
    """
    res = _sonuc('kati', 'L1')
    arac = normalize('solid', res)
    o = _vp_kos(res, arac, tmp_path)
    pred = o['pred']
    assert pred['kind'] == 'motor_curve', pred
    tc = res['thrust_curve']
    assert pred['time'] == tc['time'] and pred['thrust'] == tc['thrust']
    # Tek büyüklük tek sayı: panelin tepe itkisi Performans Özeti'ninki.
    assert max(pred['thrust']) == res['max_thrust']
    assert len(pred['time']) > 3
    assert 'transient F(t) was available' not in o['html']
    assert 'design point' not in o['html']


@needs_node
def test_D1_sivi_dikdortgen_dogru_nedenle(tmp_path):
    """Sıvı kararlı rejim modeli eğri yayımlamaz: dikdörtgen + doğru neden."""
    res = _sonuc('sivi', 'L2')
    arac = normalize('liquid', res)
    assert arac['flight_thrust']['thrust_curve'] is None
    o = _vp_kos(res, arac, tmp_path)
    pred = o['pred']
    assert pred['kind'] == 'design_point' and pred['steadyState'] is True
    u = arac['flight_thrust']
    assert pred['thrust'] == [u['thrust'], u['thrust']]
    assert pred['time'] == [0, u['burn_time']]
    assert 'steady-state design-point model' in o['html']
    assert 'No transient F(t) was available' not in o['html']
    assert 'run the transient analysis' not in o['html']


@needs_node
def test_D1_hibrit_motorun_egrisi_zaman_cozumlu_oncelik_almaz(tmp_path):
    """Hibrit: motorun eğrisi (regüle ya da boşalma) — tek kural."""
    res = _sonuc('hibrit', 'L1')
    arac = normalize('hybrid', res)
    u = arac['flight_thrust']
    # Zaman Çözümlü eki sonuca iliştirilmiş olsa bile kullanılmaz.
    res = dict(res)
    res['motor'] = dict(res['motor'], transient={'time': [0, 1, 2, 3, 4],
                                                 'thrust': [9, 9, 9, 9, 9]})
    o = _vp_kos(res, arac, tmp_path)
    pred = o['pred']
    assert pred['kind'] == 'motor_curve'
    assert pred['curveSource'] == u['curve_source']
    assert pred['thrust'] == u['thrust_curve']['thrust']


def test_D1_panel_zaman_cozumlu_ya_da_transient_okumaz():
    """Kaynak tek kuraldır: panel TransientPanel/transient anahtarını okumaz."""
    js = VP_JS.read_text(encoding='utf-8')
    kod = re.sub(r'/\*.*?\*/', '', js, flags=re.S)
    kod = re.sub(r'//[^\n]*', '', kod)
    assert 'TransientPanel' not in kod
    assert '.transient' not in kod
    assert 'flight_thrust' in kod and 'vehicleFor' in kod
    m = re.search(r'function predictedCurve\(vehicle\)(.*?)\n    \}\n', kod, re.S)
    assert m, 'predictedCurve bulunamadı'
    assert 'readThrust' not in m.group(1)


# ---------------------------------------------------------------------------
# PDF yardımcıları — gerçek uç (/api/export-pdf/<tür>), sayfanın gövdesi
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _pdf_metni(bayt):
    import io
    from pypdf import PdfReader
    return '\n'.join((p.extract_text() or '')
                     for p in PdfReader(io.BytesIO(bayt)).pages)


#: Rapor türü -> uç (rota çözücüsü literal ister; test_d24 bekçisi).
PDF_UCLARI = {'summary': '/api/export-pdf/summary',
              'technical': '/api/export-pdf/technical'}


def _pdf(istemci, tur, govde):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        r = istemci.post(PDF_UCLARI[tur], json=govde)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return _pdf_metni(r.data)


def _hibrit_govde(L, ad):
    """advanced.html exportAnalysisPDF gövdesi (motor adı + tür eklenir)."""
    res = _sonuc('hibrit', L)
    return {'motor_data': dict(res['motor'], motor_name=ad,
                               motor_type='hybrid'),
            'analysis_results': res}


# ---------------------------------------------------------------------------
# D5 — Teknik PDF hibrit motoru tanır (M-HIBRIT-8)
# ---------------------------------------------------------------------------
def test_D5_hibrit_teknik_pdf_motoru_tanir(istemci):
    metin = _pdf(istemci, 'technical', _hibrit_govde('L1', 'MUH-HIB-L1'))
    assert 'Hybrid Motor Analysis Report' in metin
    assert 'MUH-HIB-L1' in metin
    assert 'Unnamed Motor' not in metin
    assert 'not supplied in the analysis payload' not in metin
    assert re.search(r'Oxidizer\s+n2o', metin)


def test_D5_kimlik_yanitin_ic_ice_yollarindan_cozulur():
    """Sayfa tür göndermese de yanıtın kendi beyanından okunur."""
    from hrma.export.pdf_generator import resolve_report_identity
    res = _sonuc('hibrit', 'L1')
    k = resolve_report_identity(res['motor'], res)
    assert k['motor_type'][0] == 'hybrid'
    assert k['oxidizer_type'][0] == 'n2o'
    assert k['propellant_type'][0].startswith('n2o / htpb')


# ---------------------------------------------------------------------------
# D2 — Özet PDF: patlayıcı hükmü geri çekildiyse türev sayı basılmaz
# (M-HIBRIT-31)
# ---------------------------------------------------------------------------
def test_D2_geri_cekilmis_patlayici_hukmunde_parca_sayilari_basilmaz(istemci):
    """L4 LOX/HTPB: hüküm geri çekili → Gurney sayıları yok, neden var.

    ÖLÇÜLDÜ (taban 686c34b98, rapor/once/hibrit_L4_summary_tr.txt): aynı
    bölümde "fragment velocity ms: 3439.71", "lethal fragment range m: 1600",
    "maximum range m: 2000" basılıyordu.
    """
    metin = _pdf(istemci, 'summary', _hibrit_govde('L4', 'MUH-HIB-L4'))
    duz = ' '.join(metin.split())
    assert 'explosive verdict withheld because' in duz
    assert 'fragment velocity ms' not in duz
    assert 'lethal fragment range m' not in duz
    assert 'maximum range m:' not in duz
    assert 'not published: the fragment velocity' in duz
    # Şarjdan bağımsız alanlar kalır.
    assert 'estimated case mass kg' in duz


def test_D2_kazanilmis_hukumde_parca_sayilari_basilir():
    """Hüküm kazanılmışsa (sınıf çözüldü) Gurney sayıları AYNEN basılır."""
    from hrma.export.pdf_generator import PDFReportGenerator as G
    blok = {'explosive_class': 'hybrid_n2o',
            'fragment_hazards': {'fragment_velocity_ms': 812.5,
                                 'maximum_range_m': 2000.0,
                                 'lethal_fragment_range_m': 1600.0}}
    assert G._explosive_block_for_print(blok) is blok
    satir = ' '.join(G._hazard_lines(G._explosive_block_for_print(blok)))
    assert 'fragment velocity ms: 812.5' in satir


# ---------------------------------------------------------------------------
# D3 — Teknik PDF yapısal: çember gerilmesinin tabanı adıyla (M-HIBRIT-9)
# ---------------------------------------------------------------------------
def test_D3_cember_gerilmesi_tabani_yazilir(istemci):
    """L1: 44,79 MPa = tasarım basıncı 30 bar × r / t — taban belgede.

    ÖLÇÜLDÜ (taban 686c34b98): rapor yalnız "Hoop Stress (total) 44.79 MPa"
    basıyordu; mühendis oda basıncıyla 29,9 MPa kurup farkı açıklayamadı.
    """
    res = _sonuc('hibrit', 'L1')
    ca = res['motor']['structural_analysis']['chamber_analysis']
    dp = res['motor']['structural_analysis']['design_parameters']
    metin = _pdf(istemci, 'technical', _hibrit_govde('L1', 'MUH-HIB-L1'))
    duz = ' '.join(metin.split())
    assert 'Stress basis:' in duz
    assert 'Design Pressure (stress basis) %.1f bar' % dp['design_pressure'] in duz
    assert 'design pressure factor %g' % dp['design_pressure_factor'] in duz
    assert 'Evaluated Chamber Wall Thickness %.3f mm' % ca['wall_thickness_used_mm'] in duz
    assert 'Hoop Stress (pressure, at design pressure) %.2f MPa' % ca['pressure_hoop_stress'] in duz
    # Sayılar çözücünün kendi alanları: P_tas·r/t tutarlılığı (ince cidar).
    p_mpa = dp['design_pressure'] / 10.0
    r = ca['diameter'] / 2.0
    assert ca['pressure_hoop_model'] == 'thin_wall'
    assert p_mpa * r / ca['wall_thickness_used_mm'] == pytest.approx(
        ca['pressure_hoop_stress'], rel=1e-9)


# ---------------------------------------------------------------------------
# D4 — Sıvı PDF: "Exit Velocity" kayıpsız değer adıyla; Isp ekranın adıyla
# (M-SIVI-14)
# ---------------------------------------------------------------------------
def test_D4_cikis_hizi_kayipsiz_diye_adlanir_isp_ekran_adini_tasir(istemci):
    """L2 teknik PDF gövdesi (sayfanın gerçek gövdesi, tur yakalaması).

    ÖLÇÜLDÜ (taban 686c34b98): "Exit Velocity 2821.7 m/s" niteliksiz,
    teslim Isp 263,4 s'nin yanında; teslim itkiyle tutarlı u_e ≈ 2 593 m/s.
    """
    from hrma.export.rapor_sozluk import metin as sozluk_metni
    from hrma.export.pdf_generator import PDFReportGenerator as G
    govde = _govde(_vaka('sivi', 'L2'), '/api/export-pdf/technical')
    govde['charts'] = []
    ar = govde['analysis_results']
    ev = ar['performance']['exit_velocity']
    assert ev == ar['altitude_performance'][0]['exit_velocity']
    duz = ' '.join(_pdf(istemci, 'technical', govde).split())
    assert ('Exit Velocity — ideal (isentropic, loss-free) %.1f m/s' % ev) in duz
    assert 'not the same quantity' in duz
    # Anahtar tek kaynaktan (ürün sabiti): ekranın başlık Isp kartı.
    ad = sozluk_metni(G.LIQUID_HEADLINE_ISP_KEY, 'en')
    assert G.LIQUID_HEADLINE_ISP_KEY in open(
        'hrma/templates/liquid.html', encoding='utf-8').read(), (
        'PDF\'in okuduğu Isp anahtarı ekranda kullanılmıyor')
    assert ad and ('Specific Impulse above is the engine\u2019s \u201c%s\u201d' % ad) in duz


def test_D4_temeli_bilinmeyen_cikis_hizi_niteliksiz_kalmaz():
    from hrma.export.pdf_generator import PDFReportGenerator as G
    assert G._exit_velocity_label(None, {}, {}) == ('Exit Velocity', None)
    etiket, _ = G._exit_velocity_label(2500.0, {}, {})
    assert 'basis not published' in etiket


# ---------------------------------------------------------------------------
# D7 — .eng: yayımlanmayan kabuk kalınlığı dışa aktarımda da yok
# (SIVI-SOĞUTMA DEVİR d)
# ---------------------------------------------------------------------------
def _f1_sonuc(istemci):
    import contextlib
    import io
    v = _vaka('sivi', 'L5')
    govde = [r for r in v['istekler'] if r['uc'] == '/calculate_liquid'
             and r.get('yakalama_etiketi') == 'f1-b'][-1]['govde']
    with contextlib.redirect_stdout(io.StringIO()):
        r = istemci.post('/calculate_liquid', json=govde)
    assert r.status_code == 200
    return r.get_json()


def test_D7_eng_geri_cekilmis_kabugu_basmaz(istemci):
    """F-1: devre çözülmedi → cidar ne yorumda ne çap alanında.

    ÖLÇÜLDÜ (taban 686c34b98, rapor/once/sivi_F1_tr.eng): "wall used in the
    diameter field = 161.00 mm", "it does resolve a case wall thickness of
    161.00 mm", RASP çap alanı 2178.2 mm (= 1856,2 + 2 × 161).
    """
    import contextlib
    import io
    res = _f1_sonuc(istemci)
    cs = res['structural_analysis']['chamber_structure']
    assert cs['cooling_circuit_status'] == 'not_solved'
    with contextlib.redirect_stdout(io.StringIO()):
        r = istemci.post('/api/export-eng', json={
            'motor_data': dict(res, motor_name='F1')})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    eng = r.get_json()['content']
    assert '161.00 mm' not in eng
    assert 'case wall thickness of' not in eng
    assert 'wall thickness NOT published' in eng
    # RASP motor satırı: ad, çap (mm), boy (mm), gecikme, itici, yüklü, üretici
    satir = [s for s in eng.splitlines() if s and not s.startswith(';')][0]
    alanlar = satir.split()
    assert len(alanlar) == 7, satir
    cap_mm = float(alanlar[1])
    d_ic_mm = res['motor_geometry']['chamber_diameter'] * 1000.0
    assert cap_mm == pytest.approx(d_ic_mm, abs=0.051)


def test_D7_cozulmus_devrede_cidar_aynen_kalir():
    from hrma.export.openrocket_integration import OpenRocketExporter as E
    md = {'structural_analysis': {'chamber_structure': {
        'cooling_circuit_status': 'solved',
        'wall_layers': [{'role': 'closeout', 'verdict': 'pass'}]}}}
    assert E._wall_withheld(md) is False
    # Astarın 'withheld' hükmü kalınlığı geri çekmez (çözülmüş devrede de
    # görülür); yalnız dış kabuk.
    md['structural_analysis']['chamber_structure']['wall_layers'].append(
        {'role': 'liner', 'verdict': 'withheld'})
    assert E._wall_withheld(md) is False
    md['structural_analysis']['chamber_structure']['wall_layers'][0][
        'verdict'] = 'withheld'
    assert E._wall_withheld(md) is True


# ---------------------------------------------------------------------------
# D6 — PDF'te ham anahtar / ham şablon yok (M-SIVI-13 / M-KATI-3, kalem 6a);
#      katı manşet impulsu iki anlamlı basamağa inmez (kalem 6b, M-KATI-18)
# ---------------------------------------------------------------------------
HAM_KOD = re.compile(r'\bwarn\.[a-z0-9_]+(?:\.[a-z0-9_]+)+')
HAM_SABLON = re.compile(r'\{[a-z_][a-z0-9_]*\}')


def _kati_govde(tur):
    """solid.html exportPDF gövdesinin alan listesi (turun currentResults'ı)."""
    r = _sonuc('kati', 'L1')
    geo = r.get('motor_geometry') or {}
    md = {'motor_name': 'L1-KSB002', 'motor_type': 'solid',
          'grain_type': 'bates'}
    for k, v in (('propellant_type', r.get('propellant_name')),
                 ('chamber_diameter', geo.get('chamber_diameter', 0) * 1000),
                 ('chamber_length', geo.get('chamber_length', 0) * 1000),
                 ('throat_diameter', r.get('throat_diameter')),
                 ('max_thrust', r.get('max_thrust')),
                 ('thrust', r.get('max_thrust')),
                 ('specific_impulse', r.get('specific_impulse')),
                 ('burn_time', r.get('burn_time')),
                 ('total_impulse', r.get('total_impulse')),
                 ('chamber_pressure', r.get('chamber_pressure'))):
        if v is not None:
            md[k] = v
    return {'motor_data': md, 'analysis_results': r, 'charts': []}


@pytest.mark.parametrize('vaka', ['kati_L1_technical', 'kati_L1_summary',
                                  'hibrit_L1_technical', 'hibrit_L4_summary',
                                  'sivi_L2_technical'])
def test_D6a_pdf_ham_kod_ve_ham_sablon_basmaz(istemci, vaka):
    """ÖLÇÜLDÜ (taban 686c34b98, olcum_ham_anahtar_once.json): uyarı kodu
    katı teknik 24, hibrit L1 46; doldurulmamış şablon katı 20 kez."""
    if vaka.startswith('kati'):
        tur = vaka.split('_')[-1]
        govde = _kati_govde(tur)
    elif vaka.startswith('hibrit'):
        L, tur = vaka.split('_')[1], vaka.split('_')[2]
        govde = _hibrit_govde(L, 'MUH-HIB-' + L)
    else:
        tur = 'technical'
        govde = _govde(_vaka('sivi', 'L2'), '/api/export-pdf/technical')
        govde['charts'] = []
    metin = _pdf(istemci, tur, govde)
    duz = ' '.join(metin.split())
    assert not HAM_KOD.findall(duz), sorted(set(HAM_KOD.findall(duz)))[:10]
    assert not HAM_SABLON.findall(duz), sorted(set(HAM_SABLON.findall(duz)))
    for ham in ('safety_factor_is_tautological', 'tau_choice_sensitivity]',
                'is_tau_sensitive', 'input_warnings', 'design_warnings'):
        assert ham not in duz, ham


def test_D6a_uyari_cumlesi_ekranin_sozlugunden_ve_doldurulur():
    from hrma.export.rapor_sozluk import uyari_cumlesi, sozluk
    kayit = {'code': 'warn.solid.erosion_exponent_extrapolated',
             'params': {'exponent': 0.8, 'valid_low_bar': 10.0,
                        'valid_high_bar': 70.0, 'chamber_pressure_bar': 75.5,
                        'material': 'graphite'},
             'fallback': 'x {exponent}'}
    en = uyari_cumlesi(kayit, 'en')
    assert en.startswith(sozluk('en')[kayit['code']].split('{')[0])
    assert '(n = 0.8)' in en and '10-70 bar' in en and '{' not in en
    tr = uyari_cumlesi(kayit, 'tr')
    assert '0,8' in tr and '{' not in tr
    # Sözlükte olmayan kod: kaydın kendi cümlesi (doldurulmuş).
    assert uyari_cumlesi({'code': 'warn.yok', 'params': {'a': 2.5},
                          'fallback': 'a = {a}'}, 'en') == 'a = 2.5'
    # Hiç cümle yok: None (ham kod basılmaz).
    assert uyari_cumlesi({'code': 'warn.yok'}, 'en') is None


def test_D6b_kati_manset_impulsu_iki_anlamli_basamaga_inmez():
    """M-KATI-18: '2,1 kN·s' (L1 2 125,6 ve KDX-002 2 087,0 N·s aynı)."""
    html = (KOK / 'hrma' / 'templates' / 'solid.html').read_text(
        encoding='utf-8')
    satir = [s for s in html.splitlines()
             if "T('solid.msg.total_impulse', 'Total Impulse')" in s
             and 'value:' in s]
    assert len(satir) == 1, satir
    assert 'results.total_impulse,' in satir[0]
    assert "decimals: 0, unit: 'N·s'" in satir[0]
    assert '/ 1000' not in satir[0]
