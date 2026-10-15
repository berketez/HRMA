# -*- coding: utf-8 -*-
"""ÖH D37 A1a · pdf-grafik-step (a1) — kulvarın davranış bekçileri.

Kalemler ve ölçümleri (``docs/scofield/raw/OH/A1a/pdf-grafik-step/a1/``
``once.json`` ⟷ ``sonra.json``; ters-mutasyonlar ``mutasyon.md``):

* **OH-D33-05** — katı çözücü teslim Isp'sinin iki-faz düzeltme DURUMUNU
  yayımlıyor, ihracat yüzeyi onu taşıyor; PDF'te 0 satır vardı.
* **OH-D32-09** — sıvı chug çevrimi ``tau_choice_sensitivity`` DÖRT alanını
  yayımlıyor; PDF'te 0 satır vardı. Hibrit "ölçülmedi" beyanı yayımlıyor.
* **OH-D30-12** — UQ çekirdeği ``conditionality`` üretiyor; PDF okuyucusu
  yoktu. (Uç gövdesi bloğu TAŞIMIYOR — DEVİR, rapor.)
* **OH-P-17** — sıvı panosu 900 px'te bütçe etiketleri üst üste, dipnot
  sağ kenarda kesik, küçük çubuk değerleri bitişik.
* **CW-SU6** — katı sayfasında güverte POST'u 3B O/F yüzeyini istiyordu.
* **DV36-05** — ``grain_gap_source`` yayımlıyken STEP planı 0,0'ı
  "yayımlanmadı" sayıp künyeye "no solver publishes" yazıyordu.

Kaynak alanı olmayan satır BASILMAZ (fail-closed); hiçbir bekçi sayı
uydurmaz — girdiler örnek projelerin GERÇEK çözücü yanıtlarıdır.
"""
import contextlib
import copy
import io
import json
import os
import pathlib
import re
import subprocess
import tempfile

import pytest

from tests.test_example_projects import (ENDPOINTS, HEADERS,
                                         calculate_payload, load_example_doc)

KOK = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = KOK / 'hrma' / 'static' / 'js'


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _kos(istemci, mt, alanlar):
    r = _sessiz(istemci.post, ENDPOINTS[mt],
                json=calculate_payload(mt, alanlar), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def yanitlar(istemci):
    """Üç örnek projenin API yolundaki GERÇEK yanıtı (bir kez)."""
    return {mt: _kos(istemci, mt, load_example_doc(mt)['inputs']['fields'])
            for mt in ('solid', 'liquid', 'hybrid')}


def _pdf_govdesi(mt, yanit):
    """Sayfaların gönderdiği biçim: katı/sıvı ``analysis_results`` = çözücü
    yanıtı; hibrit ``motor_data`` = ``motor`` sözlüğü."""
    if mt == 'hybrid':
        md = dict(yanit['motor'], motor_name='D37-bekci')
        return {'motor_data': md, 'analysis_results': yanit}
    return {'motor_data': {'motor_type': mt, 'motor_name': 'D37-bekci'},
            'analysis_results': yanit}


def _pdf_metni(bayt):
    from pypdf import PdfReader
    return ' '.join(' '.join((p.extract_text() or '')
                             for p in PdfReader(io.BytesIO(bayt)).pages).split())


def _satirlar(mt, yanit):
    from hrma.export.pdf_generator import PDFReportGenerator
    g = _pdf_govdesi(mt, yanit)
    return PDFReportGenerator._result_qualifier_lines(g['analysis_results'],
                                                      g['motor_data'])


# ===========================================================================
# OH-D33-05 — iki-faz düzeltme durumu PDF'te
# ===========================================================================
class TestOHD3305IkiFazDurumuPdfte:

    def test_kati_pdfinde_cozucunun_durumu_ve_kaynagi_var(self, istemci,
                                                          yanitlar):
        from hrma.export.openrocket_integration import (
            OpenRocketExporter, TWO_PHASE_STATUS_FIELD)
        beklenen = OpenRocketExporter.resolve_two_phase_correction(
            yanitlar['solid'])
        assert beklenen['two_phase_correction_source'], (
            'katı örnek iki-faz durumunu yayımlamıyor — ölçüm zemini kaydı')
        r = _sessiz(istemci.post, '/api/export-pdf/complete',
                    json=_pdf_govdesi('solid', yanitlar['solid']))
        assert r.status_code == 200
        metin = _pdf_metni(r.data)
        assert 'Result Qualifiers Published By The Solver' in metin
        assert 'Two-phase (particle-lag) correction of the delivered Isp:' \
            in metin
        # Durum çözücünün KENDİ enum'udur; ikinci bir durum türetilmez.
        assert beklenen[TWO_PHASE_STATUS_FIELD] in metin
        assert beklenen['two_phase_correction_source'] in metin

    def test_kati_satirinda_verified_cozucunun_degeri(self, yanitlar):
        """Denetçi şartı 2b (A6 mutasyonu): ``verified`` alanı ÇÖZÜCÜNÜN
        değeridir; belge sabit bir doğrulama iddiası basamaz."""
        from hrma.export.openrocket_integration import (
            OpenRocketExporter, TWO_PHASE_VERIFIED_FIELD)
        beklenen = OpenRocketExporter.resolve_two_phase_correction(
            yanitlar['solid'])
        satir = [s for s in _satirlar('solid', yanitlar['solid'])
                 if 'Two-phase' in s]
        assert len(satir) == 1, satir
        assert 'verified = %s' % beklenen[TWO_PHASE_VERIFIED_FIELD] \
            in satir[0], satir[0][:400]

    @pytest.mark.parametrize('mt', ['liquid', 'hybrid'])
    def test_durum_yayimlanmayan_motorda_satir_yok(self, yanitlar, mt):
        """Fail-closed: kaynak yoksa satır YOK (ihracatın 'not published'
        yedeği belgeye satır olarak inmez)."""
        assert not any('Two-phase' in s for s in _satirlar(mt, yanitlar[mt]))


# ===========================================================================
# OH-D32-09 — τ-seçimi duyarlılığı: dört alan
# ===========================================================================
class TestOHD3209TauSecimiPdfte:

    DORT_ALAN = ('is_tau_sensitive', 'frequency_hz_span',
                 'growth_is_tau_sensitive', 'growth_rate_1_s_span')

    def test_sivi_satiri_dort_alani_ve_cozucu_sayisini_tasir(self, yanitlar):
        blok = (yanitlar['liquid']['combustion_analysis']
                ['stability_analysis']['chug_loop']['tau_choice_sensitivity'])
        satir = [s for s in _satirlar('liquid', yanitlar['liquid'])
                 if 'tau-choice' in s]
        assert len(satir) == 1, satir
        for ad in self.DORT_ALAN:
            assert ad in satir[0], (ad, satir[0][:400])
        # Bant uçları çözücünün sayısıdır (rapor kısaltması REPORT_SIGFIG).
        from hrma.export.pdf_generator import PDFReportGenerator as G
        f = blok['frequency_hz_span']
        assert G._param_scalar(f['min_hz']) in satir[0]
        assert G._param_scalar(f['max_hz']) in satir[0]
        assert str(blok['is_tau_sensitive']) in satir[0]

    def test_hibritte_olcmedi_beyani_duyarsiz_diye_okunmaz(self, yanitlar):
        satir = [s for s in _satirlar('hybrid', yanitlar['hybrid'])
                 if 'tau-choice' in s]
        assert len(satir) == 1, satir
        assert 'NOT measured' in satir[0]
        assert 'is_tau_sensitive = False' not in satir[0]

    def test_kaynak_yoksa_satir_yok(self, yanitlar):
        assert not any('tau-choice' in s
                       for s in _satirlar('solid', yanitlar['solid']))

    def test_null_bayrak_olculmedi_kalir_false_olmaz(self, yanitlar):
        """Denetçi şartı 2a (A1 mutasyonu): üç durumlu bayrak — ``None``
        "ölçülmedi" demektir, ``False`` (duyarsız) diye BASILMAZ."""
        from hrma.export.pdf_generator import PDFReportGenerator as G
        kaynak = copy.deepcopy(yanitlar['liquid'])
        blok = (kaynak['combustion_analysis']['stability_analysis']
                ['chug_loop']['tau_choice_sensitivity'])
        blok['is_tau_sensitive'] = None
        blok['growth_is_tau_sensitive'] = None
        satir = G._tau_choice_qualifier_line(kaynak)
        assert satir is not None
        assert 'is_tau_sensitive = not measured (null)' in satir, satir[:400]
        assert 'growth_is_tau_sensitive = not measured (null)' in satir
        assert 'is_tau_sensitive = False' not in satir


# ===========================================================================
# OH-D30-12 — koşulluluk bloğu (PDF okuyucusu)
# ===========================================================================
class TestOHD3012KosullulukPdfte:

    @pytest.fixture(scope='class')
    def cekirdek_blogu(self):
        """UQ ÇEKİRDEĞİNİN gerçek bloğu (uç gövdesi taşımıyor — DEVİR)."""
        from hrma.analysis import uncertainty as uq
        from hrma.analysis import uq_adapters as uqa
        alanlar = load_example_doc('solid')['inputs']['fields']
        sonuc = _sessiz(uq.run_uncertainty, uqa.make_factory('solid', alanlar),
                        uqa.build_distributions('solid', {}), n_samples=4,
                        seed=42)
        assert isinstance(sonuc.get('conditionality'), dict)
        return sonuc['conditionality']

    def test_blok_varsa_satir_kapsami_adiyla_soyler(self, yanitlar,
                                                   cekirdek_blogu):
        from hrma.export.pdf_generator import (PDFReportGenerator,
                                               UQ_RESULT_KEY)
        ar = dict(yanitlar['solid'],
                  **{UQ_RESULT_KEY: {'conditionality': cekirdek_blogu}})
        satir = [s for s in PDFReportGenerator._result_qualifier_lines(ar, {})
                 if 'conditionality' in s]
        assert len(satir) == 1, satir
        for girdi in cekirdek_blogu['conditional_on_inputs']:
            assert girdi in satir[0]
        assert 'model-form uncertainty included: False' in satir[0]

    def test_blok_yoksa_satir_yok(self, yanitlar):
        assert not any('conditionality' in s
                       for s in _satirlar('solid', yanitlar['solid']))

    def test_hicbir_kaynak_yoksa_bolum_basligi_da_yok(self):
        from hrma.export.pdf_generator import PDFReportGenerator
        assert PDFReportGenerator._result_qualifier_lines(
            {'performance': {'thrust': 1.0}}, {'motor_type': 'solid'}) == []


# ===========================================================================
# OH-P-17 — sıvı panosu yerleşimi
# ===========================================================================
class TestOHP17SiviPanoYerlesimi:

    @pytest.fixture(scope='class')
    def fig(self, yanitlar):
        from hrma.visualization.visualization import create_performance_plots
        return json.loads(create_performance_plots(yanitlar['liquid']))

    def test_butce_ekseninde_hicbir_satir_siniri_asmaz(self, fig):
        from hrma.visualization.visualization import (
            PERF_CAT_WRAP_MAX_CHARS, PERF_CAT_WRAP_MAX_LINES)
        eksen = [g for ad, g in fig['layout'].items()
                 if ad.startswith('xaxis') and isinstance(g, dict)
                 and 'Tank<br>Outlet' in (g.get('ticktext') or [])]
        assert len(eksen) == 1
        for etiket in eksen[0]['ticktext']:
            satirlar = etiket.split('<br>')
            assert len(satirlar) <= PERF_CAT_WRAP_MAX_LINES, etiket
            for s in satirlar:
                assert len(s) <= PERF_CAT_WRAP_MAX_CHARS or ' ' not in s, (
                    f'"{s}" ({len(s)} karakter) boşluk taşıyor ama sarılmadı')

    def test_dipnot_satirlara_bolunur_metin_degismez(self, fig):
        from hrma.visualization.visualization import (
            PERF_NOTE_LINE_PX, PERF_NOTE_OFFSET_PX, PERF_NOTE_WRAP_CHARS)
        notlar = [a for a in fig['layout']['annotations']
                  if str(a.get('text', '')).startswith('- Feed budget basis')]
        assert len(notlar) == 1
        a = notlar[0]
        satirlar = a['text'].split('<br>')
        assert all(len(s) <= PERF_NOTE_WRAP_CHARS for s in satirlar), satirlar
        # Birleştirilen satırlar künyenin TAMAMIDIR (kısaltma yok).
        assert ' '.join(satirlar).startswith('- Feed budget basis — ')
        assert 'Crane TP-410' in a['text'] and 'K=10' in a['text']
        # Aşağı doğru büyür, eksen başlığının altından başlar, sığar.
        assert a['yanchor'] == 'top' and a['y'] == 0
        assert a['yshift'] == -PERF_NOTE_OFFSET_PX
        assert fig['layout']['margin']['b'] >= (
            PERF_NOTE_OFFSET_PX + PERF_NOTE_LINE_PX * len(satirlar))

    def test_kalabalik_cok_devreli_panelde_deger_yazisi_dikey(self, fig):
        from hrma.visualization.visualization import (
            PERF_CAT_CROWDED_TEXTANGLE)
        butce = [t for t in fig['data'] if t.get('type') == 'bar'
                 and 'Tank Outlet' in (t.get('x') or [])]
        assert len(butce) == 2
        for t in butce:
            assert t['textangle'] == PERF_CAT_CROWDED_TEXTANGLE
            # Veri dokunulmadı: x tam ad, y çözücünün sayısı.
            assert t['x'][2].startswith('Filters')


# ===========================================================================
# CW-SU6 — katıda O/F yüzeyi istenmez, gri + neden
# ===========================================================================
_CW_SU6_JS = r"""
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const staticDir = process.argv[2];
function El(t){this.tagName=(t||'div').toUpperCase();this.children=[];this.style={};
  this.innerHTML='';this.textContent='';this.attrs={};}
El.prototype.appendChild=function(c){this.children.push(c);return c;};
El.prototype.setAttribute=function(k,v){this.attrs[k]=v;};
El.prototype.querySelectorAll=function(){return [];};
El.prototype.querySelector=function(){return null;};
El.prototype.addEventListener=function(){};
function metin(e){return (e.innerHTML||'')+' '+(e.textContent||'')+' '+
  JSON.stringify(e.attrs||{})+' '+(e.children||[]).map(metin).join(' ');}
const documentStub={head:new El('head'),body:new El('body'),readyState:'complete',
  createElement:function(t){return new El(t);},querySelector:function(){return null;},
  querySelectorAll:function(){return [];},getElementById:function(){return null;},
  addEventListener:function(){}};
const cizilen=[];
const sandbox={console:{log:function(){},warn:function(){},error:function(){}},
  setTimeout:setTimeout,clearTimeout:clearTimeout,JSON:JSON,Math:Math,Number:Number,
  Array:Array,Object:Object,String:String,Boolean:Boolean,Date:Date,RegExp:RegExp,
  isFinite:isFinite,parseFloat:parseFloat,parseInt:parseInt,document:documentStub,
  Plotly:{newPlot:function(el,d,l){cizilen.push((l&&l.title&&l.title.text)||'');}},
  fetch:function(){cizilen.push('FETCH');return Promise.reject(new Error('ag yok'));}};
sandbox.window=sandbox; vm.createContext(sandbox);
function run(f){vm.runInContext(fs.readFileSync(f,'utf8'),sandbox,{filename:f});}
run(path.join(staticDir,'units_constants.js'));
run(path.join(staticDir,'analysis_dock.js'));
run(path.join(staticDir,'panels','performance_panel.js'));
const out={kayit:{}};
['hybrid','liquid','solid'].forEach(function(mt){
  out.kayit[mt]=sandbox.window.AnalysisDock._registry.filter(function(s){
    return s.endpoint==='/api/advanced-performance-analysis' &&
      (!s.motorTypes||s.motorTypes.indexOf(mt)!==-1);}).map(function(s){
    const at=(s.fields||[]).filter(function(f){return f[0]==='analysis_type';})[0];
    return {id:s.id, analysis_type: at ? at[3].map(function(o){return o[0];}) : null,
            alanlar:(s.fields||[]).map(function(f){return f[0];})};});
});
const katı=sandbox.window.AnalysisDock._registry.filter(function(s){
  return s.id==='performance_solid';})[0];
if (katı) {
  const kok=new El('div');
  katı.render({status:'success',plot_data:JSON.stringify({data:[],layout:{title:{text:'MACH'}}}),
               analysis_info:{title:'Nozzle Mach'}}, kok);
  out.katiMetin=metin(kok); out.cizilen=cizilen.slice();
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope='module')
def cw_su6():
    with tempfile.TemporaryDirectory() as tmp:
        js = os.path.join(tmp, 'cw_su6.js')
        pathlib.Path(js).write_text(_CW_SU6_JS, encoding='utf-8')
        p = subprocess.run(['node', js, str(STATIC_JS)], capture_output=True,
                           text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


class TestCWSU6KatidaOFYuzeyiIstenmez:

    def test_katida_hicbir_kayit_yuzeyi_istemez(self, cw_su6):
        kati = cw_su6['kayit']['solid']
        assert kati, 'katıda performans figürleri tamamen düştü'
        for k in kati:
            # analysis_type göndermeyen POST uçta 3d_surface demektir.
            assert k['analysis_type'], (k['id'], 'POST 3d_surface ister')
            assert '3d_surface' not in k['analysis_type']
            assert 'optimal_of_ratio' not in k['alanlar']

    @pytest.mark.parametrize('mt', ['hybrid', 'liquid'])
    def test_hibrit_sivida_figur_istegi_aynen(self, cw_su6, mt):
        kayit = cw_su6['kayit'][mt]
        assert [k['id'] for k in kayit] == ['performance']
        assert kayit[0]['analysis_type'] is None
        assert 'optimal_of_ratio' in kayit[0]['alanlar']

    def test_katida_gri_ve_neden_var_yuzey_cizilmez(self, cw_su6):
        m = cw_su6['katiMetin']
        assert 'of_surface' in m                          # gri blok imi
        assert 'panel.performance.solidOfNa' in pathlib.Path(
            STATIC_JS / 'panels' / 'performance_panel.js').read_text('utf-8')
        assert 'O/F is not a design variable' in m        # neden (EN yedek)
        # Tek çizim: güvertenin döndürdüğü (Mach) figür; ek istek yok.
        assert cw_su6['cizilen'] == ['MACH'], cw_su6['cizilen']

    def test_neden_metni_iki_dilde(self):
        src = (STATIC_JS / 'i18n_common.js').read_text('utf-8')
        assert src.count("'panel.performance.solidOfNa':") == 2
        assert src.count("'panel.performance.titleSolid':") == 2
        assert src.count("'panel.performance.figChoice':") == 2


# ===========================================================================
# DV36-05 — STEP boşluk künyesi çözücünün grain_gap_source'undan
# ===========================================================================
class TestDV3605BoslukKunyesi:

    @staticmethod
    def _plan(gd):
        from hrma.export.step_export import _grain_segment_plan
        taban = {'number_of_segments': 3, 'segment_length_mm': 120.0}
        taban.update(gd)
        return _grain_segment_plan({'grain_design': taban})

    @pytest.mark.parametrize('kaynak', ['user_input', 'not_supplied_zero',
                                        'rejected_input'])
    @pytest.mark.parametrize('gap', [0.0, 2.0])
    def test_uc_kaynak_iki_deger_kunyeye_adiyla(self, kaynak, gap):
        p = self._plan({'grain_gap_mm': gap, 'grain_gap_source': kaynak})
        assert p['gap_published'] is True
        assert p['gap_source'] == kaynak
        assert f'grain_gap_source={kaynak}' in p['source']
        assert p['gap_mm'] == gap
        assert p['stack_mm'] == pytest.approx(3 * 120.0 + 2 * gap)
        assert 'not_published' not in p['source']
        assert 'no solver publishes' not in p['source']

    def test_user_input_sifir_yayimlanmis_gercek_sifir_bitisik(self):
        p = self._plan({'grain_gap_mm': 0.0, 'grain_gap_source': 'user_input'})
        assert p['gap_published'] is True and p['stack_mm'] == 360.0
        assert 'entered by the user' in p['source']
        assert 'flush' in p['source']

    def test_alan_yoksa_yanitta_yok(self):
        p = self._plan({})
        assert p['gap_published'] is False
        assert 'absent_in_response' in p['source']
        assert p['gap_source'] == 'absent_in_response'

    def test_kaynaksiz_sifir_yayimlanmadi_sayilir(self):
        """§0 kural 4: künye yoksa 0,0 = yayımlanmadı."""
        p = self._plan({'grain_gap_mm': 0.0})
        assert p['gap_published'] is False
        assert 'absent_in_response' in p['source']

    def test_gercek_kati_sifir_bosluk_step_kunyesinde(self, istemci,
                                                      tmp_path):
        """Uçtan uca: grain_gap=0 girilen katı örneğin STEP başlığı."""
        from hrma.export.step_export import generate_step_assembly
        alanlar = copy.deepcopy(load_example_doc('solid')['inputs']['fields'])
        alanlar['grain_gap'] = 0.0
        y = _kos(istemci, 'solid', alanlar)
        assert y['grain_design']['grain_gap_source'] == 'user_input'
        dosyalar = _sessiz(generate_step_assembly, y, motor_type='solid',
                           out_dir=str(tmp_path))
        metin = pathlib.Path(dosyalar['fuel_grain']).read_text(
            'utf-8', errors='replace')
        baslik = ' '.join(metin[:metin.find('DATA;')].split())
        assert 'grain_gap_source=user_input' in baslik, baslik[:900]
        assert 'no solver publishes' not in baslik
        assert re.search(r'inter-segment gap 0\.00 mm', baslik), baslik[:900]
