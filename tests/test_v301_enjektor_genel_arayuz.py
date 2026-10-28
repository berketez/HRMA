# -*- coding: utf-8 -*-
"""V301/E2 (Ayberk tur 1) — enjektör formu, sonuç tablosu, rapor, 4xx metni.

Ayberk: "Hybrit motor kısmında enjektör konfigürasyon bölümünde inputların
açıklamaları yok", "Enjektör kısmı full hatalı düzeltilmeli."
Ölçümler: docs/scofield/raw/OH/V301/ayberk1/enjektor-genel/
(once_en_ekran.json, once_en_form_*.png, once_en_tablo_*.png).
"""
import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
SABLON = KOK / 'hrma' / 'templates' / 'advanced.html'
APP_JS = KOK / 'hrma' / 'static' / 'js' / 'app.js'
REJECT_JS = KOK / 'hrma' / 'static' / 'js' / 'reject_body.js'
I18N_COMMON = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'
I18N_ADV = KOK / 'hrma' / 'static' / 'js' / 'i18n_advanced.js'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _oku(yol):
    return yol.read_text(encoding='utf-8')


def _blok(kaynak, bas):
    """``bas`` ile başlayan JS işlevinin gövdesi (süslü parantez sayarak)."""
    i = kaynak.index(bas)
    j = kaynak.index('{', i)
    derinlik = 0
    for k in range(j, len(kaynak)):
        if kaynak[k] == '{':
            derinlik += 1
        elif kaynak[k] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[i:k + 1]
    raise AssertionError('blok kapanmadı: ' + bas)


def _dal(sablon, tip):
    """updateInjectorParams içindeki bir tipin şablon dizesi."""
    govde = _blok(sablon, 'function updateInjectorParams()')
    i = govde.index("type === '%s'" % tip)
    j = govde.index('`;', govde.index('html += `', i))
    return govde[i:j]


# ---------------------------------------------------------------------------
# Form: tek kaynak, her girdiye ipucu, hibritte anlamsız alan yok
# ---------------------------------------------------------------------------
def test_statik_dinamik_parametre_kopyasi_yok():
    s = _oku(SABLON)
    m = re.search(r'<div id="dynamic_params">(.*?)</div>', s, re.S)
    assert m and m.group(1).strip() == '', (
        'statik duş başlığı alan kopyası geri geldi (updateInjectorParams '
        'onu yükte eziyordu; iki farklı ipucu)')


@pytest.mark.parametrize('tip', ['showerhead', 'impingement', 'swirl',
                                 'coaxial'])
def test_her_girdinin_olcu_ve_bossa_ipucu_var(tip):
    dal = _dal(_oku(SABLON), tip)
    gruplar = re.findall(r'<div class="form-group"[^>]*>(.*?)</div>\s*(?=<div class="form-group"|$)',
                         dal, re.S)
    kimlikler = re.findall(r'<(?:input|select)\b[^>]*\bid="([\w]+)"', dal)
    assert kimlikler, tip
    for kimlik in kimlikler:
        bas = dal.index('id="%s"' % kimlik)
        grup_bas = dal.rfind('<div class="form-group"', 0, bas)
        parca = dal[grup_bas:bas]
        assert 'class="tooltip-text" data-i18n="' in parca, (
            '%s/%s alanının yardım balonu yok' % (tip, kimlik))
        ipucu = re.search(r'class="tooltip-text"[^>]*>([^<]+)<', parca).group(1)
        assert 'Empty' in ipucu or 'empty' in ipucu or kimlik == 'slot_height', (
            '%s ipucu boşsa ne olduğunu söylemiyor: %r' % (kimlik, ipucu))
    del gruplar


def test_hibritte_anlamsiz_alanlar_kalkti():
    s = _oku(SABLON)
    for kimlik in ('impingement_pattern', 'impingement_distance',
                   'momentum_ratio', 'recess_length', 'n_elements',
                   'inner_diameter', 'outer_annulus_diameter'):
        assert not re.search(r'<(?:input|select)\b[^>]*id="%s"' % kimlik, s), \
            kimlik
    for yol in (SABLON, I18N_ADV):
        metin = _oku(yol)
        assert 'Central post diameter for fuel injection' not in metin
        assert 'Momentum Ratio (Fuel/Ox)' not in metin
        assert 'Triplet (F-O-F)' not in metin


def test_tip_ipucu_bes_tipi_ve_tek_akimi_anlatir():
    s = _oku(SABLON)
    m = re.search(r'data-i18n="adv.tip.injectorType">([^<]+)<', s)
    assert m
    metin = m.group(1)
    for tip in ('Showerhead', 'Impingement', 'Pintle', 'Swirl', 'Coaxial'):
        assert tip in metin, tip
    assert 'ONE liquid stream' in metin


def test_on_dolu_uydurma_sayilar_sokuldu():
    s = _oku(SABLON)
    for kimlik in ('impingement_angle', 'element_pairs', 'orifice_diameter',
                   'swirl_chamber_diameter', 'swirl_angle', 'slot_width',
                   'slot_height', 'coaxial_inner_flow_fraction',
                   'plate_thickness'):
        for etiket in re.findall(r'<input\b[^>]*\bid="%s"[^>]*>' % kimlik, s):
            assert not re.search(r'\bvalue="', etiket), (kimlik, etiket[:120])
    toplayici = _blok(s, 'function getFormData()')
    assert "plate_thickness')?.value || 3.0" not in toplayici
    assert "enjAta('plate_thickness')" in toplayici
    assert "enjAta('n_slots', true)" not in toplayici, \
        'yuva sayısı Math.trunc ile kırpılıyor (kesirli girdi uca gitmeli)'
    for ad in ('impingement_pattern', 'momentum_ratio', 'recess_length',
               'n_elements'):
        assert "'%s'" % ad in toplayici   # delete listesinde


# ---------------------------------------------------------------------------
# /calculate 4xx metni (devir madde 7)
# ---------------------------------------------------------------------------
@needs_node
def test_4xx_ret_cumlesi_kesilmeden_kullaniciya_iner():
    app_js = _oku(APP_JS)
    blok = _blok(app_js, 'function sunucuRetHatasi(')
    uzun = ('No design was published. ' + 'The requested tank pressure is '
            'below the saturation pressure at the oxidizer temperature. ' * 6)
    govde = json.dumps({'status': 'invalid_input',
                        'error': 'tank_pressure_below_saturation',
                        'message': uzun,
                        'invalid_fields': [{'field': 'tank_pressure',
                                            'reason': 'below_saturation'}]})
    betik = (
        "global.window = global;\n"
        f"window.HRMAReject = require({json.dumps(str(REJECT_JS))});\n"
        "function SRV(t) { return t; }\n"
        "function sunucuHataMetni(s) { return 'HTTP ' + s; }\n"
        + blok + "\n"
        f"const e = sunucuRetHatasi(422, 'application/json', {json.dumps(govde)});\n"
        "const h = sunucuRetHatasi(500, 'text/html', '<html></html>');\n"
        "process.stdout.write(JSON.stringify({m: e.message, r: e.hrmaReject,"
        " h: h.message, hr: h.hrmaReject || null}));\n")
    with tempfile.TemporaryDirectory() as td:
        yol = pathlib.Path(td) / 'k.js'
        yol.write_text(betik, encoding='utf-8')
        p = subprocess.run([NODE, str(yol)], capture_output=True, text=True,
                           timeout=60)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout)
    assert uzun.strip() in r['m'], 'açıklama cümlesi kesildi ya da yok'
    assert '[invalid_input]' in r['m'] and 'tank_pressure (below_saturation)' in r['m']
    assert r['r'] == {'status': 422, 'code': 'tank_pressure_below_saturation'}
    assert r['hr'] is None and r['h'] == 'HTTP 500'


def test_ret_hatasi_iletisim_arizasi_diye_etiketlenmez():
    blok = _blok(_oku(APP_JS), 'function handleError(')
    i = blok.index('if (error && error.hrmaReject)')
    j = blok.index("error.message.includes('HTTP')")
    assert i < j, 'ret dalı "Server communication error" dalından sonra'
    assert 'userMessage = error.message;' in blok[i:j]
    assert "'app.err.srcRejected'" in blok[i:j]


# ---------------------------------------------------------------------------
# Sonuç tablosu / tasarım raporu / metin dışa aktarımı (madde 5, 10, 12)
# ---------------------------------------------------------------------------
_STUB = ("function T(k, f) { return f; }\n"
         "function TF(k, p, f) { return String(f).replace(/\\{(\\w+)\\}/g,"
         " function (w, n) { return n in p ? String(p[n]) : w; }); }\n"
         "function numTxt(v, d) { return (typeof v === 'number' && isFinite(v))"
         " ? v.toFixed(d) : 'N/A'; }\n"
         "global.window = global; global.document = { querySelector: function"
         " () { return null; } };\n")


def _tablo_satirlari(veri):
    blok = _blok(_oku(APP_JS), 'function displayInjectorTable(')
    # V301/T-ÇAPA-D: tablo satırı sunucu metnini app.js'in SRV çeviri
    # kanalından basıyor (DİL-2); koşuma sayfanın KENDİ SRV'si alınır (window.I18N
    # yokken metni aynen döndürür). Yoksa node 'SRV is not defined' ile düşer.
    srv = _blok(_oku(APP_JS), 'function SRV(')
    betik = (_STUB + srv + "\n" + blok + "\n"
             f"const r = displayInjectorTable({json.dumps(veri)}, true);\n"
             "process.stdout.write(JSON.stringify(r));\n")
    with tempfile.TemporaryDirectory() as td:
        yol = pathlib.Path(td) / 'k.js'
        yol.write_text(betik, encoding='utf-8')
        p = subprocess.run([NODE, str(yol)], capture_output=True, text=True,
                           timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@needs_node
def test_tablo_carpismali_satirlari_kanondan():
    r = _tablo_satirlari({
        'type': 'impingement', 'exit_velocity': 48.9, 'reynolds_number': 6e5,
        'pressure_drop': 30.5, 'n_pairs': 2, 'n_holes': 4,
        'hole_diameter': 1.8277, 'impingement_angle_deg': 60.0,
        'impingement_distance': 10.97, 'axial_velocity': 42.3,
        'plate_thickness': 5.0, 'plate_thickness_earned': False,
        'impingement_plan_source': 'injector circuit solution'})
    satir = {x[0]: x[1] for x in r['specific']}
    assert satir['Doublet Pairs (holes)'] == '2 (4)'
    assert satir['Hole Diameter'] == '1.828'
    assert satir['Impingement Angle 2θ'] == '60.0'
    assert satir['Plate Thickness'].startswith('not supplied')
    assert satir['Hole Plan Source'] == 'injector circuit solution'


@needs_node
def test_tablo_koaksiyel_ve_swirl_satirlari():
    k = _tablo_satirlari({
        'type': 'coaxial', 'inner_jet_diameter': 3.97,
        'annulus_inner_diameter': 4.97, 'annulus_outer_diameter': 5.93,
        'annulus_gap': 0.48, 'recess_length': 3.97, 'inner_flow_fraction': 0.6,
        'inner_flow_fraction_source': 'module default HRMA choice',
        'circuit_solution': 'not_available: no circuit'})
    satir = {x[0]: x[1] for x in k['specific']}
    assert satir['Inner Jet Flow Share'] == '60.0'
    assert satir['Injector Circuit Solution'].startswith('not_available')
    s = _tablo_satirlari({
        'type': 'swirl', 'n_slots': 6, 'slot_width': 1.27, 'slot_height': 0.64,
        'spray_angle': 90.0, 'spray_half_angle_deg': 45.0, 'n_elements': 7,
        'exit_orifice_diameter': 2.4416, 'swirl_chamber_diameter': 6.10,
        'orifice_mean_velocity': 15.9})
    satir = {x[0]: x[1] for x in s['specific']}
    assert satir['Swirl Elements'] == '7'
    assert satir['Exit Orifice Diameter d_o (per element)'] == '2.442'
    assert satir['Orifice Mean Velocity (circuit definition)'] == '15.9'


def test_tasarim_raporu_ve_disa_aktarim_tablonun_satirlarini_kullanir():
    app_js = _oku(APP_JS)
    rapor = _blok(app_js, 'function displayDesignReport(')
    assert 'displayInjectorTable(injectorData, true)' in rapor
    assert "injectorData.type === 'pintle'" not in rapor, \
        'raporda elle yazılmış üç satırlık pintle dalı geri geldi'
    ihrac = _blok(app_js, 'async function exportReport(')
    assert 'displayInjectorTable(inj, true)' in ihrac
    assert 'ceaKarsilastirmaMetni(currentResults)' in ihrac


@needs_node
def test_metin_raporunda_cea_karsilastirmasi():
    blok = _blok(_oku(APP_JS), 'function ceaKarsilastirmaMetni(')
    blok_var = {
        'schema': 'hrma.cea_comparison/1', 'status': 'available',
        'operating_point': {'chamber_pressure_bar': 20.0, 'of_ratio': 2.5,
                            'expansion_ratio': 4.53},
        'rows': [{'quantity': 'c_star', 'unit': 'm/s', 'hrma': 1520.3,
                  'cea': 1521.1, 'delta_pct': -0.0526}]}
    blok_yok = {'schema': 'hrma.cea_comparison/1', 'status': 'unavailable',
                'reason': {'code': 'rocketcea_not_available'}}
    betik = (_STUB + blok + "\n"
             f"process.stdout.write(JSON.stringify([ceaKarsilastirmaMetni({{cea_comparison: {json.dumps(blok_var)}}}),"
             f" ceaKarsilastirmaMetni({{cea_comparison: {json.dumps(blok_yok)}}}),"
             " ceaKarsilastirmaMetni({})]));\n")
    with tempfile.TemporaryDirectory() as td:
        yol = pathlib.Path(td) / 'k.js'
        yol.write_text(betik, encoding='utf-8')
        p = subprocess.run([NODE, str(yol)], capture_output=True, text=True,
                           timeout=60)
    assert p.returncode == 0, p.stderr
    var, yok, bos = json.loads(p.stdout)
    assert 'NASA CEA COMPARISON' in var and 'HRMA 1520.3000 / CEA 1521.1000' in var
    assert '-0.053 %' in var and 'Pc = 20.000 bar' in var
    assert 'rocketcea_not_available' in yok
    assert bos == '', 'blok yokken bölüm uydurulmamalı'


def test_yeni_etiketler_iki_dilde():
    s = _oku(I18N_COMMON)
    for k in ('app.err.srcRejected', 'app.rep.impPairs', 'app.rep.coaxInnerShare',
              'app.rep.swirlElements', 'app.txt.ceaTitle', 'inj.roleWhatIf',
              'inj.syncedFromEngine', 'inj.typeCoaxialSingle', 'inj.helpPfeed'):
        # V301/H2: 'inj.coaxNotInCircuit' söküldü (devre koaksiyeli artık
        # çözüyor, panel tasarlıyor); yerine panelin koaksiyel tip adı.
        assert s.count("'%s':" % k) == 2, k
    a = _oku(I18N_ADV)
    for k in ('adv.inj.tipElementPairs', 'adv.inj.tipCoaxialInnerShare',
              'adv.inj.tipPlateThickness', 'adv.inj.coaxialCircuit'):
        assert a.count("'%s':" % k) == 2, k


def test_tank_uyarisi_kullanici_tank_kipini_anar():
    s = _oku(I18N_COMMON)
    satirlar = [x for x in s.splitlines()
                if "'warn.hybrid.tank_pressure_not_used':" in x]
    assert len(satirlar) == 2
    assert 'User-supplied tank pressure' in satirlar[0]
    assert 'Kullanıcının verdiği tank basıncı' in satirlar[1]
