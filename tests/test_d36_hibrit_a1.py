"""ÖH D36 · 2. aşama · kulvar onemli2-hibrit bekçileri (23 Eylül 2026).

Kanıt: docs/scofield/raw/OH/D36/onemli2-hibrit/a1/ (once.json, sonra.json,
mutasyon.md, rapor.md).

A-3 · gizli tasarım paneli ilk hesapta "kullanıcı verdi"
    ÖLÇÜLDÜ (once.json, bb7ee57c şablonu, gerçek tarayıcıda getFormData):
    panel hiç açılmadan gövdede chamber_material, wall_thickness=5,
    safety_factor=4, nozzle_material, injector_material, pressure_drop=0,20·Pc,
    hole_pattern, cooling_channels vardı; uç structural_design_basis.
    wall_thickness_source = user_supplied, design_mode = verify basıyordu.
    Onarım: alan yalnız köken damgasıyla (data-hrma-source: user |
    project_file) gider; ΔP pressure_drop_source beyanıyla gider; proje
    kaydı damgasız kapılı alanı yazmaz; uç uygulamadığı ΔP'yi
    inputs_not_used'a yazar.

Bekçiler kaynağı DOSYADAN okur (inspect.getsource yok). getFormData node ile
GERÇEKTEN koşturulur: şablondaki işlev metni, şablonun kendi input/select
varsayılanlarından kurulan küçük bir DOM ikiziyle çalıştırılır.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
SABLON = KOK / 'hrma' / 'templates' / 'advanced.html'
PROJE_SERIDI = KOK / 'hrma' / 'static' / 'js' / 'project_bar.js'
I18N_COMMON = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'
APP_PY = KOK / 'hrma' / 'app.py'

TASARIM_GOVDE_ALANLARI = (
    'chamber_material', 'wall_thickness', 'safety_factor', 'nozzle_material',
    'injector_material', 'pressure_drop', 'hole_pattern', 'cooling_channels')

NODE = shutil.which('node')


def _oku(yol: pathlib.Path) -> str:
    return yol.read_text(encoding='utf-8')


def _islev(metin: str, bas: str) -> str:
    """`bas` ile başlayan işlevin tam metni (süslü parantez eşlemesiyle)."""
    i = metin.index(bas)
    j = metin.index('{', i)
    derinlik = 0
    for k in range(j, len(metin)):
        c = metin[k]
        if c == '{':
            derinlik += 1
        elif c == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[i:k + 1]
    raise AssertionError(f'{bas!r} kapanmadı')


def _dom_ikizi(metin: str) -> dict:
    """Şablondaki id'li öğeler: input/select varsayılanlarıyla, gerisi
    (div, sekme kabı) değersiz genel öğe olarak."""
    ogeler = {}
    for m in re.finditer(r'<(?!input\b|select\b)([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"', metin):
        ogeler[m.group(2)] = {'value': '', 'type': m.group(1), 'checked': False}
    for m in re.finditer(r'<input\b([^>]*)>', metin):
        at = m.group(1)
        idm = re.search(r'\bid="([^"]+)"', at)
        if not idm:
            continue
        val = re.search(r'\bvalue="([^"]*)"', at)
        tip = re.search(r'\btype="([^"]+)"', at)
        ogeler[idm.group(1)] = {
            'value': val.group(1) if val else '',
            'type': tip.group(1) if tip else 'text',
            'checked': bool(re.search(r'\bchecked\b', at)),
        }
    for m in re.finditer(r'<select\b([^>]*)>(.*?)</select>', metin, re.S):
        idm = re.search(r'\bid="([^"]+)"', m.group(1))
        if not idm:
            continue
        secenekler = re.findall(r'<option\b([^>]*)>', m.group(2))
        deger = ''
        for s in secenekler:
            v = re.search(r'\bvalue="([^"]*)"', s)
            if v is None:
                continue
            if not deger:
                deger = v.group(1)
            if re.search(r'\bselected\b', s):
                deger = v.group(1)
                break
        ogeler[idm.group(1)] = {'value': deger, 'type': 'select',
                                'checked': False}
    return ogeler


def _stdin_betigi(kosucu, girdi):
    """Betik + girdi TEK stdin akışında (ÖH V3 taban-b).

    Eski biçim betiği argv'den (``-e``) veriyor, girdiyi stdin'den
    okutuyordu; argv çekirdek tavanına tabidir (Linux MAX_ARG_STRLEN
    128 KiB, tests/test_node_cagri_sozlesmesi.py). Girdi, JSON dizge
    sabiti olarak betiğin başına gömülür; betik stdin'den koşar.
    """
    return 'const HRMA_GIRDI = %s;\n%s' % (json.dumps(json.dumps(girdi)),
                                           kosucu)


_KOSUCU = r"""
const girdi = JSON.parse(HRMA_GIRDI);
const ogeler = {};
for (const [id, o] of Object.entries(girdi.dom)) {
  ogeler[id] = {
    id, value: o.value, type: o.type, checked: o.checked,
    dataset: Object.assign({}, (girdi.damga || {})[id] ? {hrmaSource: girdi.damga[id]} : {}),
    classList: { contains: () => false },
    closest: () => null,
    getAttribute: (a) => (a === 'type' ? o.type : null),
  };
}
for (const [id, v] of Object.entries(girdi.deger || {})) { if (ogeler[id]) ogeler[id].value = String(v); }
global.document = {
  getElementById: (id) => ogeler[id] || null,
  querySelector: () => null,
  querySelectorAll: () => [],
};
global.window = global;
eval(girdi.kod);
process.stdout.write(JSON.stringify(getFormData()));
"""


def _govde(damga: dict | None = None, deger: dict | None = None) -> dict:
    metin = _oku(SABLON)
    kod = '\n'.join([
        _islev(metin, 'function altitudeToPressure('),
        _islev(metin, 'function viskoziteKullaniciGirdisiMi('),
        _islev(metin, 'function viskoziteGovdeDegeri('),
        _islev(metin, 'function tasarimKaynagi('),
        _islev(metin, 'function getFormData('),
    ])
    girdi = {'dom': _dom_ikizi(metin), 'kod': kod,
             'damga': damga or {}, 'deger': deger or {}}
    r = subprocess.run([NODE], input=_stdin_betigi(_KOSUCU, girdi),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@pytest.mark.skipif(NODE is None, reason='node yok')
class TestA3GovdeKapisi:
    def test_dokunulmamis_panel_govdeye_girmez(self):
        g = _govde()
        sizan = [a for a in TASARIM_GOVDE_ALANLARI if a in g]
        assert sizan == [], f'damgasız tasarım alanı gövdede: {sizan}'
        for a in ('pressure_drop_source', 'design_config_opened',
                  'design_config_source', 'design_config_fields'):
            assert a not in g, a

    def test_kullanici_duzenlediyse_beyanla_gider(self):
        g = _govde(damga={'wall_thickness': 'user',
                          'pressure_drop_percent': 'user'},
                   deger={'wall_thickness': 6, 'pressure_drop_percent': 25})
        assert g['wall_thickness'] == 6
        assert g['pressure_drop_source'] == 'user'
        assert g['pressure_drop'] == pytest.approx(0.25 * g['chamber_pressure'])
        assert g['design_config_opened'] is True
        assert g['design_config_source'] == 'user'
        assert {b['field'] for b in g['design_config_fields']} == {
            'wall_thickness', 'pressure_drop'}
        # Damgasız kardeşler yine gitmez.
        assert 'safety_factor' not in g and 'chamber_material' not in g

    def test_proje_dosyasi_beyani(self):
        g = _govde(damga={'wall_thickness': 'project_file',
                          'pressure_drop_percent': 'project_file'},
                   deger={'wall_thickness': 7, 'pressure_drop_percent': 30})
        assert g['wall_thickness'] == 7
        assert g['pressure_drop_source'] == 'project_file'
        assert g['design_config_source'] == 'project_file'

    def test_sahte_damga_gecmez(self):
        g = _govde(damga={'wall_thickness': 'default'})
        assert 'wall_thickness' not in g


class TestA3KaynakKapilari:
    def test_proje_kaydi_damgasiz_kapili_alani_yazmaz(self):
        s = _oku(PROJE_SERIDI)
        govde = _islev(s, 'function serializeFields(')
        assert re.search(
            r"el\.dataset\.hrmaSourceGate\s*===\s*'1'\s*&&\s*!el\.dataset\.hrmaSource\)\s*continue;",
            govde), 'serializeFields kapılı alan süzgeci yok'

    def test_sablon_kapiyi_isaretler(self):
        s = _oku(SABLON)
        assert "el.dataset.hrmaSourceGate = '1';" in s

    def test_geri_yukleme_damgasi_restoring_bayragindan(self):
        s = _oku(SABLON)
        assert 'window.HRMAProjectBar._state.restoring' in s
        # restoring bayrağı gerçekten var ve olay yayımı bayrak açıkken yapılır.
        p = _oku(PROJE_SERIDI)
        apply = _islev(p, 'function applyProject(')
        assert apply.index('state.restoring = true') < apply.index('restoreFields(')
        assert '_state: state' in p

    def test_on_yuz_hesaptan_once_gorunmez_dugme_yok(self):
        # ARA KAYIT'taki 'Design configuration' düğmesi #resultsPanel içindeki
        # paneli açıyordu; resultsPanel hesaptan önce display:none (ölçüldü).
        assert 'toggleDesignConfigPanel' not in _oku(SABLON)

    def test_durum_satiri_anahtarlari_sozlukte(self):
        s = _oku(I18N_COMMON)
        tr = s[s.index('        tr: {'):]
        en = s[:s.index('        tr: {')]
        for k in ('suggestionNote', 'srcUser', 'srcProject',
                  'srcProjectDpNotApplied', 'willSend', 'willNotSend'):
            assert f"'app.design.{k}'" in en, ('EN', k)
            assert f"'app.design.{k}'" in tr, ('TR', k)
        # UI metninde uzun tire yok.
        for m in re.finditer(r"'app\.design\.\w+': '([^']*)'", s):
            assert '—' not in m.group(1)


class TestA3UcBeyani:
    def test_uygulanmayan_dp_beyan_edilir_kaynak(self):
        s = _oku(APP_PY)
        assert "'reason': 'solver_canon_precedence'" in s
        assert re.search(r"inputs_not_used = list\(inputs_not_used or \[\]\) \+ \[_dp_uygulanmayan\]", s)
        # D35 sözleşmesi: ezme yalnız user/request/override beyanıyla.
        assert "_dp_kullanici_ezmesi = _dp_ezme_beyani in ('user', 'request', 'override')" in s


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _ornek_govde() -> dict:
    """examples/ hibrit projesinin gövdesi, tasarım alanları olmadan (ölçülen S3).

    Girdi ``tests/fixtures/`` altında durur (kaynağı dosyanın ``_kaynak``
    alanında): yayın dalı docs/'suz üretildiği için bu davranış bekçileri
    kanıt dizinine bağlı olursa orada koşmaz.
    """
    yol = KOK / 'tests' / 'fixtures' / 'd36_hibrit_ornek_govde.json'
    d = json.loads(yol.read_text(encoding='utf-8'))
    return dict(d['govde'])


class TestA3UcDavranisi:
    def test_alanlar_yokken_hrma_boyutlandirir(self, istemci):
        r = istemci.post('/calculate', json=_ornek_govde())
        assert r.status_code == 200
        j = r.get_json()
        assert j['structural_design_basis']['wall_thickness_source'] == 'sized_by_hrma'
        assert j['structural_design_basis']['design_mode'] == 'size'

    def test_proje_dosyasi_dp_uygulanmaz_ve_beyan_edilir(self, istemci):
        g = _ornek_govde()
        g.update({'pressure_drop': 9.0, 'pressure_drop_source': 'project_file'})
        j = istemci.post('/calculate', json=g).get_json()
        assert j['injector']['pressure_drop_source'] == 'injector circuit solution'
        kayit = [b for b in j.get('inputs_not_used') or []
                 if b.get('field') == 'pressure_drop']
        assert kayit and kayit[0]['reason'] == 'solver_canon_precedence'
        assert kayit[0]['declared_source'] == 'project_file'

    def test_kullanici_dp_ezer(self, istemci):
        g = _ornek_govde()
        g.update({'pressure_drop': 7.5, 'pressure_drop_source': 'user'})
        j = istemci.post('/calculate', json=g).get_json()
        assert j['injector']['pressure_drop_source'] == 'user override'
        assert not [b for b in j.get('inputs_not_used') or []
                    if b.get('field') == 'pressure_drop']


# ---------------------------------------------------------------------------
# G-1 · dört "optimum O/F" (tek kanon + künye). ÖLÇÜLDÜ (once.json G1, örnek
# hibrit proje, Pc 30 bar): çözücü 6,4206 / 247,63 s; yanma paneli tarama
# azamisi 6,8125 / 244,98 s (9 nokta, bant 1-8,75); "Optimumu Bul" 7,1801 /
# 245,14 s; eğri 2,87-12,92 (15 nokta). Hiçbir işaret modelini/bandını/adımını
# söylemiyordu. Hesap DEĞİŞMEDİ (sonra.json G1'de aynı sayılar).
# ---------------------------------------------------------------------------
VIZ = KOK / 'hrma' / 'visualization' / 'visualization.py'
KUNYE_ALANLARI = ('optimum_kind', 'model', 'sweep_range', 'n_points',
                  'canonical')


class _SahteCozucu:
    """Test ikizi: tarama noktası başına Isp döndürür (yalnız künye sınanır)."""

    def analyze_combustion(self, fuel, ox, of, pc, **_):
        return {'performance': {'isp': 250.0 - (float(of) - 6.0) ** 2}}


def _figur(x):
    return json.loads(x) if isinstance(x, str) else x


def _isaret(fig, ad):
    return [t for t in fig['data'] if t.get('name') == ad]


APP_JS = KOK / 'hrma' / 'static' / 'js' / 'app.js'


class TestG1Kunye:
    def test_yanma_paneli_tarama_azamisi_kunyeli(self):
        from hrma.visualization.visualization import (
            create_combustion_analysis_plots)
        fig = _figur(create_combustion_analysis_plots(
            {}, propellant={'fuel_composition': {'htpb': 100.0},
                            'oxidizer_type': 'n2o', 'chamber_pressure': 30.0,
                            'of_range': (1.0, 8.75),
                            'analyzer': _SahteCozucu()}))
        isaret = _isaret(fig, 'Sweep maximum')
        assert len(isaret) == 1
        meta = isaret[0].get('meta') or {}
        for a in KUNYE_ALANLARI:
            assert meta.get(a) not in (None, '', []), a
        assert meta['chamber_pressure_bar'] == 30.0
        assert meta['sweep_range'] == [1.0, 8.75]
        assert meta['step'] == pytest.approx((8.75 - 1.0) / 8)
        assert 'expansion_ratio' in meta and meta['expansion_ratio'] is None
        assert 'not the solver optimum' in isaret[0]['hovertemplate']
        notlar = ' '.join(str(a.get('text', ''))
                          for a in fig['layout'].get('annotations', []))
        assert 'canonical optimum O/F is the solver value' in notlar

    def test_3b_yuzey_izgara_azamisi_kunyeli(self):
        from hrma.visualization.visualization import (
            create_chamber_pressure_mixture_ratio_3d_surface)
        fig = _figur(create_chamber_pressure_mixture_ratio_3d_surface(
            {'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'grid_n': 3}))
        isaret = _isaret(fig, 'Sweep maximum')
        assert len(isaret) == 1
        meta = isaret[0].get('meta') or {}
        for a in KUNYE_ALANLARI + ('chamber_pressure_range_bar', 'step'):
            assert meta.get(a) not in (None, '', []), a
        for t in _isaret(fig, 'Sweep ceiling (refined)'):
            assert (t.get('meta') or {}).get('optimum_kind') == 'surface_refined_ceiling'

    def test_optimumu_bul_ucu_kunye_verir(self, istemci):
        r = istemci.post('/api/find-optimum-of', json={
            'motor_type': 'hybrid', 'oxidizer': 'n2o', 'fuel': 'htpb',
            'chamber_pressure': 30})
        assert r.status_code == 200
        j = r.get_json()
        assert j['model'] and 'sea level' in j['model']
        assert j['sweep_range'] == [1.0, 10.0]
        assert j['chamber_pressure'] == 30.0
        assert 'expansion_ratio' in j and j['expansion_ratio'] is None
        assert 'motor.optimum_of_ratio' in j['canonical_note']
        pc = j['performance_curve']
        assert pc['n_points'] == len(pc['of_ratios'])
        assert pc['sweep_range'] == [pc['of_ratios'][0], pc['of_ratios'][-1]]
        assert pc['step'] == pytest.approx(pc['of_ratios'][1] - pc['of_ratios'][0])

    def test_arayuz_kunyeyi_ve_kanonu_basar(self):
        s = _oku(SABLON)
        bul = _islev(s, 'async function findOptimumOF(')
        assert 'optimumKunyesiniYaz(result);' in bul
        yaz = _islev(s, 'function optimumKunyesiniYaz(')
        assert 'currentResults.motor' in yaz
        assert 'optimumKunyeSatirlari(result, motor)' in yaz
        # Metin app.js'te kurulur (app.* anahtarı; şablon i18n_advanced
        # sözleşmesini korur). Davranış node ile koşturulur.
        a = _oku(APP_JS)
        kod = '\n'.join(_islev(a, f'function {ad}(') for ad in (
            'T', 'TF', 'numTxt', 'optimumKunyeSatirlari'))
        betik = ('global.window = {};' + kod + ';process.stdout.write(JSON.stringify(['
                 'optimumKunyeSatirlari({sweep_range:[1,10], chamber_pressure:30},'
                 ' {optimum_of_ratio: 6.4206, maximum_isp: 247.63}),'
                 'optimumKunyeSatirlari({sweep_range:[1,10], chamber_pressure:30}, null)]))')
        r = subprocess.run([NODE], input=betik, capture_output=True,
                           text=True, timeout=60)
        assert r.returncode == 0, r.stderr[-800:]
        kanonlu, kanonsuz = json.loads(r.stdout)
        assert any('6.42' in x and '247.6' in x for x in kanonlu), kanonlu
        assert any('not available until you run Calculate' in x for x in kanonsuz)
        assert all('1.00 to 10.00' in x for x in kanonlu[:1])
        d = _oku(I18N_COMMON)
        tr = d[d.index('        tr: {'):]
        for k in ('basis', 'canon', 'canonNone', 'curveBasis'):
            assert f"'app.optimum.{k}'" in d[:d.index('        tr: {')]
            assert f"'app.optimum.{k}'" in tr


# ---------------------------------------------------------------------------
# U-7 / U-8 · "Sonuçları Dışa Aktar" / "Özet PDF". ÖLÇÜLDÜ (once.json U78,
# gerçek tarayıcı, örnek hibrit proje): iki düğme AYNI uca giden AYNI PDF'i
# (22548 B) iki ayrı kod yolundan indiriyordu; her tık 1 istek / 1 blob /
# 1 indirme ("çift blob" ÇÜRÜTÜLDÜ). "Sonuçları Dışa Aktar" ekranda iz
# bırakmıyordu ve dosya adı daima HRMA_Motor_summary_report.pdf idi.
# ---------------------------------------------------------------------------
APP_JS = KOK / 'hrma' / 'static' / 'js' / 'app.js'

_DISA_KOSUCU = r"""
const vm = require('vm');
const girdi = JSON.parse(HRMA_GIRDI);
const kayit = { tekYol: [], fetch: 0, uyari: [], indirilen: [] };
const sandbox = {
  console: { log() {}, warn() {}, error() {} },
  currentResults: { motor: { isp: 200, thrust: 1000, chamber_pressure: 20, mdot_total: 1 },
                    injector: { type: 'showerhead' } },
  showWarning: (m) => kayit.uyari.push(String(m)),
  showError: (m) => kayit.uyari.push(String(m)),
  downloadBlobAs: (b, ad) => kayit.indirilen.push(ad),
  T: (k, f) => f, numTxt: (v) => String(v),
  collectResultWarnings: () => [], warnToText: (w) => String(w),
  Blob: function (p, o) { return { parts: p, type: o && o.type }; },
  fetch: async () => { kayit.fetch += 1; throw new Error('fetch çağrılmamalıydı'); },
  Array, String, Number, Math, JSON, isFinite, Error,
};
sandbox.window = sandbox;
sandbox.exportAnalysisPDF = async (tip, sec) => {
  kayit.tekYol.push([tip, sec]);
  if (girdi.basarisiz) throw new Error('PDF yok');
  return true;
};
vm.createContext(sandbox);
vm.runInContext(girdi.kod, sandbox);
vm.runInContext('exportReport', sandbox)().then(() => process.stdout.write(JSON.stringify(kayit)));
"""


def _disa_aktar(basarisiz: bool) -> dict:
    kod = _islev(_oku(APP_JS), 'async function exportReport(')
    r = subprocess.run([NODE],
                       input=_stdin_betigi(_DISA_KOSUCU, {'kod': kod,
                                                         'basarisiz': basarisiz}),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@pytest.mark.skipif(NODE is None, reason='node yok')
class TestU78TekPdfYolu:
    def test_disa_aktar_tek_yola_baglanir(self):
        k = _disa_aktar(basarisiz=False)
        assert k['tekYol'] == [['summary', {'throwOnFail': True}]]
        assert k['fetch'] == 0, 'ikinci PDF yolu hâlâ kendi isteğini atıyor'
        assert k['indirilen'] == []

    def test_tek_yol_dusunce_yedek_sessiz_degil(self):
        k = _disa_aktar(basarisiz=True)
        assert k['uyari'], 'PDF düştü, kullanıcıya hiçbir şey söylenmedi'
        assert any(a.endswith('.txt') for a in k['indirilen'])

    def test_tek_yol_icerik_kapisi_ve_donus(self):
        f = _islev(_oku(SABLON), 'async function exportAnalysisPDF(')
        assert 'await assertPdfBlob(blob, response);' in f
        assert f.index('assertPdfBlob') < f.index('triggerBlobDownload(')
        assert 'if (firlat) throw e;' in f
        assert 'return true;' in f and 'return false;' in f


# ---------------------------------------------------------------------------
# OH-P-11 (TR ondalık) · OH-P-04 · OH-P-05. ÖLÇÜLDÜ (once.json TR, 1440 px,
# TR, örnek proje + hesap, body.innerText): noktalı 138 (Plotly dışı 26;
# bu kulvarın dosyalarında: künye çipi 1, hüküm şeridi künyesi 1, 3B saat 1).
# P-04: görünür 20 seçicinin 5'i kesik, hiçbirinin ipucu tam metni taşımıyor.
# P-05: ölçü kartı künyesi (113-135 px) sözcük ortasından 1 kez kırılıyordu.
# ---------------------------------------------------------------------------
def _node_calistir(betik: str):
    r = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout)


@pytest.mark.skipif(NODE is None, reason='node yok')
class TestTROndalik:
    def test_kunye_cipleri_yerel_ayrac(self):
        a = _oku(APP_JS)
        assert 'earned.toFixed(' not in a and 'vsf.toFixed(' not in a
        assert "numTxt(earned, 2)" in a and "numTxt(vsf, 2)" in a
        assert 'window.I18N.decimalText(_vsfMetin)' in a
        kod = _islev(a, 'function numTxt(')
        tr = ("global.window = {I18N: {number: (v, d) => v.toFixed(d).replace('.', ','),"
              " decimalText: (t) => t.replace('.', ',')}};")
        cikti = _node_calistir(tr + kod + ';process.stdout.write(JSON.stringify(numTxt(0.8266, 2)))')
        assert cikti == '0,83'

    def test_3b_saat_yer_tutucusu_sayi_tasimaz(self):
        s = _oku(SABLON)
        m = re.search(r'<div class="viz-clock" id="viz_clock">([^<]*)</div>', s)
        assert m and not re.search(r'\d', m.group(1)), m and m.group(1)
        assert '—' not in m.group(1)

    def test_i18nNumber_yedegi_ozyinelemez(self):
        kod = _islev(_oku(SABLON), 'function i18nNumber(')
        assert 'i18nNumber(value' not in kod.split('{', 1)[1]
        cikti = _node_calistir('global.window = {};' + kod
                               + ';process.stdout.write(JSON.stringify([i18nNumber(1.5, 2), i18nNumber(3, 0)]))')
        assert cikti == ['1.5', '3']


_SECICI_KOSUCU = r"""
function secici(metin, title) {
  const at = {}; if (title !== undefined) at.title = title;
  return { options: [{ textContent: metin }], selectedIndex: 0, dataset: {},
           getAttribute: (k) => (k in at ? at[k] : null),
           setAttribute: (k, v) => { at[k] = String(v); },
           hasAttribute: (k) => k in at };
}
const s1 = secici('Sayfadaki hesap / form değerleri (varsayılan)');
const s2 = secici('Duş başlığı (varsayılan)', 'Enjektör eleman ailesi.');
const s3 = secici('Grafit', 'Grafit');
const liste = [s1, s2, s3];
global.document = { querySelectorAll: () => liste };
eval(KOD);
seciciIpucuEsitle(document); seciciIpucuEsitle(document);
// Panel/i18n ipucunu yeniden yazarsa taban odur:
s2.setAttribute('title', 'Injector element family.');
seciciIpucuEsitle(document);
process.stdout.write(JSON.stringify(liste.map(s => s.getAttribute('title'))));
"""


@pytest.mark.skipif(NODE is None, reason='node yok')
class TestP04SeciciIpucu:
    def test_ipucu_tam_secili_metni_tasir(self):
        kod = _islev(_oku(SABLON), 'function seciciIpucuEsitle(')
        t = _node_calistir('const KOD = ' + json.dumps(kod) + ';' + _SECICI_KOSUCU)
        assert t[0] == 'Sayfadaki hesap / form değerleri (varsayılan)'
        assert t[1] == 'Injector element family.\nDuş başlığı (varsayılan)'
        assert t[2] == 'Grafit'


@pytest.mark.skipif(NODE is None, reason='node yok')
class TestP05KunyeSarmasi:
    def _html(self, metin, esik=None):
        a = _oku(APP_JS)
        kod = (_islev(a, 'function hdEscape(')
               + '\nconst KUNYE_KIRMA_ESIGI = 30; const KUNYE_DAR_KART_ESIGI = 16;\n'
               + _islev(a, 'function kunyeSarmaHtml('))
        cagri = f'kunyeSarmaHtml({json.dumps(metin)}' + (f', {esik})' if esik else ')')
        return _node_calistir(kod + f';process.stdout.write(JSON.stringify({cagri}))')

    def test_her_oge_kendi_satirinda(self):
        h = self._html('design_mode: size · wall_thickness_source: sized_by_hrma')
        assert h.count('<span style="display:block">') == 2
        assert '·' not in h
        # Geniş şeritte kısa alan adı dokunulmaz (kanon ad aranabilir kalır).
        assert 'wall_thickness_source:' in h

    def test_dar_kartta_uzun_ad_alt_cizgiden_kirilir(self):
        h = self._html('minimum_earned_safety_factor: 0,83', 16)
        assert 'minimum_<wbr>earned_<wbr>safety_<wbr>factor: 0,83' in h

    def test_kacis_korunur(self):
        h = self._html('x: <b>&')
        assert '&lt;b&gt;&amp;' in h

    def test_iki_kap_da_sarmadan_gecer(self):
        a = _oku(APP_JS)
        assert 'kunyeSarmaHtml(m.note, KUNYE_DAR_KART_ESIGI)' in a
        assert "kunyeSarmaHtml(kunye.join(' · '))" in a
