# -*- coding: utf-8 -*-
"""ÖH D36 · 2. aşama · kulvar ``dil2-i18n-pdf`` (a1) bekçileri.

Kanıt paketi: ``docs/scofield/raw/OH/D36/dil2-i18n-pdf/a1/`` (``once.json``
taban bb7ee57c dondurulmuş ağaçta, ``sonra.json`` kulvarda, aynı
``olcum.py`` ile; ``mutasyon.md`` ters mutasyon; ``rapor.md`` kalem kalem).

Kalemler:

  K1  i18n devirleri (D35 hibrit kulvarı §5): iki YENİ
      ``warn.validation.expansion_ratio_*`` anahtarı EN+TR sözlükte, emekli
      ``expansion_ratio_out_of_range`` sözlükten ÇIKTI (üreticisi yok). TR
      terimi sözlüğün kendi terimi (``nozul``, ``sesüstü``).
  K2  PDF "Solver Warnings" bölümü iç içe parametreleri Python ``repr``i
      olarak DÖKMEZ (D35 pdf kulvarı devri 1). Ölçüldü: gerçek hibrit
      koşumunda bölümde ``{'`` imzası 20 → 0.
  K2b ``complete`` belgesinin teknik eki (Declarations Made By This
      Analysis) ve ısıl hüküm satırları aynı kaydı İKİNCİ kez basıyordu:
      ölçüldü ``{'`` 20 → 0 (belge toplamı 40 → 0).
  K3  PDF yanma süresi / toplam impuls YOKKEN dürüst düşüş (LU-1 çapraz
      bağı): 'N/A' simgesi korunur, yanına ``not supplied (no burn duration
      was given)`` gerekçesi gelir, F×t türetilmez, çözücünün
      ``burn_time_source`` beyanı (sıvı yanıtında üst seviye) belgeye iner.

(K4 güvenlik paneli, K5 Plotly TR ondalık, K6 fea_panel anahtarları, K7
enjektör bandı uyarısı: ``tests/test_d36_dil2_a2.py``.)

Kaynak okuyan bekçiler kaynağı DOSYADAN okur (``inspect.getsource`` yok —
linecache bayatlıyor, taban kaydı notu).
"""
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from hrma.export.pdf_generator import (BURN_TIME_NOT_SUPPLIED,
                                       PDFReportGenerator)

ROOT = Path(__file__).resolve().parents[1]
STATIC_JS = ROOT / 'hrma' / 'static' / 'js'
I18N_COMMON = STATIC_JS / 'i18n_common.js'
NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node kurulu değil')
PDFTOTEXT = shutil.which('pdftotext') or '/opt/homebrew/bin/pdftotext'


def _oku(yol):
    return Path(yol).read_text(encoding='utf-8')


def _sozluk_blogu(src, lang):
    """``i18n_common.js`` içindeki ``en: {`` / ``tr: {`` bloğunun metni."""
    m = re.search(r'\b%s\s*:\s*\{' % lang, src)
    assert m, 'sözlük bloğu yok: %s' % lang
    i, depth, quote, esc = m.end() - 1, 0, None, False
    while i < len(src):
        ch = src[i]
        if quote:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == quote:
                quote = None
        elif ch in '\'"`':
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return src[m.end():i]
        i += 1
    raise AssertionError('blok kapanmıyor: %s' % lang)


@pytest.fixture(scope='module')
def istemci():
    os.environ.setdefault('HRMA_HEADLESS', '1')
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _pdf_metni(istemci, motor_data, analysis_results, tur='summary'):
    if not os.path.exists(PDFTOTEXT):
        pytest.skip('pdftotext kurulu değil')
    r = istemci.post('/api/export-pdf/%s' % tur, json={
        'motor_data': motor_data, 'analysis_results': analysis_results})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fh:
        fh.write(r.get_data())
        yol = fh.name
    try:
        return subprocess.run([PDFTOTEXT, '-layout', yol, '-'],
                              capture_output=True, text=True,
                              timeout=120).stdout
    finally:
        os.unlink(yol)


# ===========================================================================
# K1 — i18n devirleri
# ===========================================================================
class TestK1ExpansionRatioAnahtarlari:
    YENI = {
        'warn.validation.expansion_ratio_not_evaluated': ('{eps}',),
        'warn.validation.expansion_ratio_not_supersonic': ('{eps}', '{floor}'),
    }
    EMEKLI = 'warn.validation.expansion_ratio_out_of_range'

    @pytest.fixture(scope='class')
    def bloklar(self):
        src = _oku(I18N_COMMON)
        return {lang: _sozluk_blogu(src, lang) for lang in ('en', 'tr')}

    @pytest.mark.parametrize('anahtar', sorted(YENI))
    def test_yeni_anahtar_EN_ve_TR_sozlukte(self, bloklar, anahtar):
        for lang, blok in bloklar.items():
            m = re.search(r"'%s'\s*:\s*'((?:[^'\\]|\\.)*)'" % re.escape(anahtar), blok)
            assert m, '%s %s sözlüğünde yok' % (anahtar, lang.upper())
            for yer in self.YENI[anahtar]:
                assert yer in m.group(1), (
                    '%s (%s): yer tutucu %s metinde yok' % (anahtar, lang, yer))

    def test_TR_metni_turkce_ve_EN_ile_ayni_degil(self, bloklar):
        for anahtar in self.YENI:
            en = re.search(r"'%s'\s*:\s*'((?:[^'\\]|\\.)*)'" % re.escape(anahtar), bloklar['en']).group(1)
            tr = re.search(r"'%s'\s*:\s*'((?:[^'\\]|\\.)*)'" % re.escape(anahtar), bloklar['tr']).group(1)
            assert en != tr
            assert re.search('[çğıöşüÇĞİÖŞÜ]', tr), 'TR metni Türkçe karakter taşımıyor: %r' % tr

    def test_TR_terimi_sozlugun_kendi_terimi(self, bloklar):
        """TR sözlük 'nozul' der (56 geçiş), 'lüle' demez; TDK 'sesüstü'
        bitişik yazar. Kesilen ajanın metni 'lüle ses-üstü' diyordu."""
        tr = re.search(r"'warn.validation.expansion_ratio_not_supersonic'\s*:\s*'((?:[^'\\]|\\.)*)'",
                       bloklar['tr']).group(1)
        assert 'nozul' in tr and 'sesüstü' in tr, tr
        assert 'lüle' not in tr and 'ses-üstü' not in tr, tr

    def test_ureticinin_kodlari_sozlukle_ortusuyor(self):
        """``validation_system.py`` bu iki kodu ÜRETİR; sözlük kodu yayımlayan
        yerle aynı adları taşır (kod → anahtar zinciri, D29 hüküm-18)."""
        src = _oku(ROOT / 'hrma' / 'validation' / 'validation_system.py')
        for anahtar in self.YENI:
            assert ("'%s'" % anahtar) in src, '%s üreticide yok' % anahtar

    def test_emekli_anahtar_sozlukten_CIKTI_ve_ureticisi_yok(self, bloklar):
        for lang, blok in bloklar.items():
            assert ("'%s'" % self.EMEKLI) not in blok, (
                '%s hâlâ %s sözlüğünde — üreticisi yok, ölü çeviri' % (self.EMEKLI, lang))
        ureticiler = [p for p in glob.glob(str(ROOT / 'hrma' / '**' / '*.py'), recursive=True)
                      if ("'%s'" % self.EMEKLI) in _oku(p)]
        assert not ureticiler, 'emekli anahtarın üreticisi geri geldi: %s' % ureticiler


# ===========================================================================
# K2 — PDF Solver Warnings parametre dökümü
# ===========================================================================
#: Gerçek hibrit koşumunun ``warn.hybrid.htpb_coeff_bias`` kaydıyla AYNI
#: şekil (``once.json`` K2 ``independent_campaigns_satiri``); sayılar
#: kısaltılmış, iç içe kap yapısı birebir.
HIBRIT_KAYIT = {
    'code': 'warn.hybrid.htpb_coeff_bias', 'severity': 'warning',
    'params': {
        'bias_pct': -39.5, 'campaign_oxidizer_scope': ['n2o'],
        'campaign_scope_match': True, 'campaign_scope_reason': None,
        'independent_campaign_bias_band_pct': [-50.6, -41.8],
        'independent_campaigns': [
            {'bias_pct': -50.6, 'campaign': 'Rezaei 2018',
             'code': 'warn.hybrid.htpb_campaign_entry', 'medape_pct': 50.9,
             'oxidizer': 'n2o',
             'params': {'bias_pct': -50.6, 'campaign': 'Rezaei 2018',
                        'medape_pct': 50.9, 'oxidizer': 'n2o', 'points': 29},
             'points': 29, 'severity': 'info'},
            {'bias_pct': -41.8, 'campaign': 'Carmicino 2013',
             'code': 'warn.hybrid.htpb_campaign_entry', 'medape_pct': 43.5,
             'oxidizer': 'n2o', 'params': {'points': 16}, 'points': 16,
             'severity': 'info'},
        ],
        'unreconciled_reasons': [
            {'code': 'warn.hybrid.htpb_campaign_entry_no_medape',
             'params': {'campaign': 'Heydari 2017', 'medape_pct': None}},
        ],
        'uzun': 4.914408842346228,
        'material': 'Graphite & <isostatic>',
    },
}


class TestK2SolverWarningsRepr:
    def test_parametre_metni_python_repr_TASIMAZ(self):
        detay = PDFReportGenerator._warning_params_text(HIBRIT_KAYIT['params'])
        assert "{'" not in detay and "': " not in detay, detay
        assert '[{' not in detay

    def test_hicbir_alan_dusmez_alt_satir_olur(self):
        detay = PDFReportGenerator._warning_params_text(HIBRIT_KAYIT['params'])
        for ad in ('independent_campaigns=', 'unreconciled_reasons=',
                   'Rezaei 2018', 'Carmicino 2013', 'Heydari 2017',
                   'campaign_scope_reason=None', 'campaign_scope_match=True',
                   'independent_campaign_bias_band_pct=[-50.6, -41.8]'):
            assert ad in detay, '%r alt satırlarda yok:\n%s' % (ad, detay)
        assert detay.count('<br/>') >= 4, 'kap taşıyan parametreler alt satıra açılmamış'
        assert '&nbsp;&nbsp;&nbsp;&nbsp;• ' in detay

    def test_basamak_kurali_ve_kacirma(self):
        detay = PDFReportGenerator._warning_params_text(HIBRIT_KAYIT['params'])
        assert 'uzun=4.91441' in detay, 'REPORT_SIGFIG kuralı uygulanmıyor'
        assert '4.914408842346228' not in detay
        assert 'bias_pct=-39.5' in detay, 'kısa yazılmış sayı DEĞİŞMEMELİ'
        assert 'material=Graphite &amp; &lt;isostatic&gt;' in detay, (
            'metin ReportLab paragraf diline karşı kaçırılmıyor')

    def test_skaler_sozlesme_degismedi(self):
        """OH-D17-01 / Z5 sözleşmesi: skaler parametreler ``k=v; k=v``."""
        detay = PDFReportGenerator._warning_params_text(
            {'t_used_mm': 1.0, 't_required_mm': 2.0, 'used': None})
        assert detay == 't_required_mm=2.0; t_used_mm=1.0; used=None', detay
        assert PDFReportGenerator._warning_params_text(None) == ''
        assert PDFReportGenerator._warning_params_text('plain') == 'plain'

    def test_bolum_metninde_repr_yok(self):
        g = PDFReportGenerator()
        govde = {'design_warnings': [HIBRIT_KAYIT]}
        hucreler = []
        for eleman in g._create_solver_warnings_section(govde, govde):
            for satir in (getattr(eleman, '_cellvalues', None) or []):
                for hucre in satir:
                    hucreler.append(getattr(hucre, 'text', hucre))
        metin = ' '.join(str(h) for h in hucreler)
        assert 'warn.hybrid.htpb_coeff_bias' in metin
        assert "{'" not in metin, metin
        assert 'Rezaei 2018' in metin

    def test_belge_metninde_repr_imzasi_SIFIR(self, istemci):
        """Uçtan uca: ``/api/export-pdf/summary`` belgesinde ``{'`` 0 kez.
        (Gerçek koşum ölçümü: ``once.json`` K2 → 20, ``sonra.json`` → 0.)"""
        motor = {'motor_name': 'D36-K2', 'motor_type': 'hybrid',
                 'thrust': 4000.0, 'design_warnings': [HIBRIT_KAYIT]}
        metin = _pdf_metni(istemci, motor, dict(motor))
        assert 'Solver Warnings' in metin
        assert metin.count("{'") == 0, [s for s in metin.splitlines() if "{'" in s][:4]
        assert 'Rezaei 2018' in metin


# ===========================================================================
# K2b — teknik ek beyan satırları ve ısıl hüküm satırları
# ===========================================================================
class TestK2bTeknikEkRepr:
    def test_beyan_satirlari_repr_TASIMAZ(self):
        satirlar = PDFReportGenerator._solver_declaration_lines(
            {'warnings': [HIBRIT_KAYIT], 'design_warnings': [HIBRIT_KAYIT]})
        metin = ' '.join(satirlar)
        assert metin.count('warn.hybrid.htpb_coeff_bias') == 2
        assert "{'" not in metin and "': " not in metin, metin
        for ad in ('independent_campaigns = [(', 'Rezaei 2018', 'Heydari 2017',
                   'campaign_scope_reason = None', 'uzun = 4.91441',
                   'material = Graphite &amp; &lt;isostatic&gt;'):
            assert ad in metin, '%r beyan satırında yok:\n%s' % (ad, metin)

    def test_isil_hukum_satirlari_repr_TASIMAZ(self):
        satirlar = PDFReportGenerator._thermal_verdict_lines(
            {'warnings': [{'code': 'warn.thermal.x', 'severity': 'critical',
                           'params': {'nested': {'a': 1.23456789012, 'b': [1, 2]},
                                      'T_wall': 3323}}]})
        metin = ' '.join(satirlar)
        assert "{'" not in metin, metin
        assert 'nested = (a: 1.23457; b: [1, 2])' in metin, metin
        assert 'T_wall = 3323' in metin

    def test_complete_belgesinde_repr_imzasi_SIFIR(self, istemci):
        """Uçtan uca ``complete``: özet bölümü + teknik ek birlikte 0.
        (Gerçek koşum: ``once.json`` belge toplamı 40, ``sonra.json`` 0.)"""
        motor = {'motor_name': 'D36-K2b', 'motor_type': 'hybrid',
                 'thrust': 4000.0, 'design_warnings': [HIBRIT_KAYIT],
                 'solver_declarations': {'warnings': [HIBRIT_KAYIT]}}
        metin = _pdf_metni(istemci, motor, dict(motor), tur='complete')
        assert metin.count("{'") == 0, [s for s in metin.splitlines() if "{'" in s][:4]


# ===========================================================================
# K3 — yanma süresi / toplam impuls yokken dürüst düşüş
# ===========================================================================
class TestK3YanmaSuresiYok:
    def _paragraflar(self, story):
        return ' '.join(getattr(e, 'text', '') for e in story if hasattr(e, 'text'))

    def test_ozet_gerekce_basar_sayi_uydurmaz(self):
        g = PDFReportGenerator()
        ozet = self._paragraflar(g._create_executive_summary(
            {'thrust': 4000.0}, {'thrust': 4000.0}))
        assert 'Burn Time: N/A — %s' % BURN_TIME_NOT_SUPPLIED in ozet, ozet
        assert 'no burn duration was given' in ozet
        assert 'Total Impulse: N/A — not supplied' in ozet
        assert 'F×t is not derived' in ozet
        assert not re.search(r'Burn Time: \d', ozet)
        assert not re.search(r'Total Impulse: \d', ozet), 'F×t türetilmiş'

    def test_burn_time_varken_gerekce_yok(self):
        g = PDFReportGenerator()
        ozet = self._paragraflar(g._create_executive_summary(
            {'performance': {'burn_time': 8.0, 'thrust': 4000.0}}, {}))
        assert 'Burn Time: 8.0 s' in ozet
        assert 'not supplied' not in ozet.split('Burn Time')[1].split('•')[0]

    def test_burn_time_source_beyani_belgeye_iner(self):
        g = PDFReportGenerator()
        ozet = self._paragraflar(g._create_executive_summary(
            {'performance': {'burn_time': 300.0}},
            {'burn_time_source': 'assumed 300 s burn (no max_burn_duration supplied)'}))
        assert ('Burn time source (solver declaration): assumed 300 s burn '
                '(no max_burn_duration supplied)') in ozet, ozet

    def test_ic_bloktaki_beyan_okunmaz(self):
        """Hibrit yanıtta ``burn_time_source`` yalnız ``thermal_protection``
        altında durur ve ısıl koruma süresini anlatır: rapor onu yanma
        süresi kaynağı diye BASMAZ."""
        g = PDFReportGenerator()
        ozet = self._paragraflar(g._create_executive_summary(
            {'thermal_protection': {'burn_time_source': 'design burn time'}},
            {'thermal_protection': {'burn_time_source': 'design burn time'}}))
        assert 'Burn time source' not in ozet

    def test_beyan_yoksa_uydurulmaz(self):
        g = PDFReportGenerator()
        ozet = self._paragraflar(g._create_executive_summary({}, {'burn_time_source': 42}))
        assert 'Burn time source' not in ozet

    def test_belge_ozet_ve_tablo_ayni_simge_gerekce_altinda(self, istemci):
        motor = {'motor_name': 'D36-K3', 'motor_type': 'hybrid', 'thrust': 4000.0,
                 'specific_impulse': 239.7}
        metin = _pdf_metni(istemci, motor, dict(motor))
        okunan = re.findall(r'Burn Time\s*:?\s*([-\w./]+)', metin)
        assert okunan and set(okunan) == {'N/A'}, okunan
        assert metin.count('no burn duration was given') >= 2, (
            'gerekçe özet + tablo altında olmalı')
        assert 'F×t is not derived' in metin
        assert not re.search(r'Total Impulse\s*:?\s*\d', metin)
