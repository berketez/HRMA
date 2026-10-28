# -*- coding: utf-8 -*-
"""ÖH D37 A1b-3 · panel-js — panel JS bekçileri (tarayıcısız katman).

Kart: ``docs/scofield/raw/OH/D37/ana-plan/A1b_kartlari.md`` "## A1b-3 ·
panel-js". Kanıt dizini ``docs/scofield/raw/OH/A1b/panel-js/a1/``
(rapor.md, once/, sonra/, mutasyon.md).

Her sınıf bir kalemi DAVRANIŞIYLA kilitler: panel dosyası node'da gerçekten
koşar (kopya yazılmaz), en küçük ``window``/``document`` saplamasıyla;
çıktının kendisi ölçülür. Tarayıcı isteyen iki ölçüm (enjektör şeması
metin kutusu çakışması, regresyon grafiği kap ⟷ çizim boşluğu)
``tests/test_d37_panel_piksel_a1.py``'dedir.

* K1 OH-D30-12 — UQ ``conditionality`` dokuz alanı panelde, her değer kendi
  satırında (alan adıyla, birebir); blok yoksa satır yok.
* K2 OH-D32-09 — chug ``tau_choice_sensitivity`` dört alanı (alan adıyla,
  birebir); beş kaynak hâli; üç durumlu bayrak (true/false/null) ve eşleşme
  toleransının iki yanı (alt kenar: 6 basamak yuvarlaması; üst kenar: 5.
  anlamlı basamak düzenlemesi).
* K3 OH-D33-09 — transient beş kesme alanı rozette; TERS_MUAFIYET'ten düştü;
  bayrak ve sayı rozetlerinin rengi değere (ve tank kipine) bağlı.
* K5 DV36-04  — sixdof/blowdown ekran ``.toFixed(`` sınıflandırması.
* K6 OH-D37-G2 — O/F taraması koşu noktasının künyesi (sayı değişmez); dört
  yayımlanan çıkış künyesinin yol eşlemesi; ε yolunda ipucundaki p_e birebir.
* K7 OH-D37-H1 — test_d22 M4 düğümü boş liste üstünde yeşil kalmaz.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(KOK, 'hrma', 'static', 'js')

NODE = shutil.which('node')
gerek_node = pytest.mark.skipif(NODE is None, reason='node yok — JS paneli koşulamıyor')


def oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


# ---------------------------------------------------------------------------
# Node düzeneği: panel dosyası bir vm bağlamında GERÇEKTEN yüklenir.
# ``I18N.number`` TR biçimlendirici gibi davranır (virgül) — ekran kanalına
# giden her sayı bu kancadan geçmeli; ``.toFixed`` ile atlayan NOKTA basar.
# ---------------------------------------------------------------------------
PRELUDE = r"""
const fs = require('fs'), vm = require('vm');
function tf(k, p, f) { return String(f).replace(/\{(\w+)\}/g,
    (w, n) => (p && n in p) ? String(p[n]) : w); }
function yukle(dosyalar, ekstra) {
  const kayit = [];
  const ogeler = {};
  function oge(id) {
    if (!ogeler[id]) ogeler[id] = {id: id, innerHTML: '', textContent: '',
      style: {}, disabled: false, value: '', addEventListener() {},
      setAttribute() {}, getAttribute() { return null; },
      querySelectorAll() { return []; }, appendChild() {}};
    return ogeler[id];
  }
  const ui = new Proxy({}, {get: (t, k) => {
    if (k === 't') return (key, fb) => fb;
    if (k === 'tf') return tf;
    if (k === 'num') return (v, d) => (typeof d === 'number' ? v.toFixed(d)
        : String(v)).replace('.', ',');
    if (k === 'sigFig') return (v) => Number(Number(v).toPrecision(6));
    return (...a) => '';
  }});
  const window = {
    AnalysisDock: {ui: ui, register: (s) => kayit.push(s),
                   getMotorType: () => 'hybrid'},
    I18N: {lang: 'tr', t: (k, f) => f, tf: tf,
           number: (v, d) => (typeof d === 'number' ? v.toFixed(d)
               : String(v)).replace('.', ','),
           decimalText: (s) => /^[+-]?\d+\.\d+$/.test(s) ? s.replace('.', ',') : s,
           serverText: (s) => s, onChange: () => {}, applyTo: () => {}},
  };
  const document = {getElementById: oge, addEventListener() {},
    querySelectorAll: () => [], querySelector: () => null,
    createElement: () => oge('__yeni' + Math.random())};
  const ctx = {window, document, console, Math, JSON, Number, String, Array,
    Object, isFinite, parseFloat, parseInt, Boolean, RegExp, Error,
    setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0,
    clearInterval: () => {},
    Plotly: {react() {}, newPlot() {}, purge() {}}};
  Object.assign(ctx, ekstra || {});
  vm.createContext(ctx);
  dosyalar.forEach((d) => vm.runInContext(fs.readFileSync(d, 'utf8'), ctx,
                                          {filename: d}));
  return {window, ogeler, kayit};
}
"""


def node_kos(govde):
    # Betik STDIN'den verilir, argv'den değil (tests/test_node_cagri_
    # sozlesmesi.py TestArgvBetikYasagi: Linux MAX_ARG_STRLEN / macOS
    # ARG_MAX tavanı). Denetçi 3. tur süpürmesinde bu dosyanın eski argv
    # çağrısı o bekçinin ihlal listesine eklenmişti.
    r = subprocess.run([NODE], input=PRELUDE + govde, capture_output=True,
                       text=True, cwd=KOK, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


# ===========================================================================
# K1 · OH-D30-12 — bandın kapsamı panelde
# ===========================================================================
UQ_ALANLARI = ('applies_to', 'conditional_on_inputs', 'input_count',
               'frozen_at_nominal', 'sampler', 'n_effective',
               'input_correlation_assumed',
               'model_form_uncertainty_included', 'interpretation')


def _js_esc(s):
    """Panellerin ``escapeHtml``/``esc``i ile aynı kaçış (& " < >)."""
    return (str(s).replace('&', '&amp;').replace('"', '&quot;')
            .replace('<', '&lt;').replace('>', '&gt;'))


def _kosulluluk_blogu():
    """Sunucunun GERÇEK bloğu (hrma/analysis/uncertainty.py
    ``_conditionality_block``) — alan adları sözleşmedir (kural 11)."""
    from hrma.analysis.uncertainty import _conditionality_block
    return _conditionality_block({}, ['thrust', 'burn_time', 'of_ratio'],
                                 'lhs', 29)


@gerek_node
class TestK1UqKosulluluk:

    def _html(self, veri):
        return node_kos(r"""
        const Y = yukle(['hrma/static/js/panels/uncertainty_panel.js']);
        const veri = %s;
        const html = Y.window.UncertaintyPanel._conditionalityHtml(veri);
        const satir = [...html.matchAll(/data-uq-cond-field="([a-z_]+)"/g)].map(m => m[1]);
        console.log(JSON.stringify({html: html, satir: satir,
            kutu: (html.match(/data-uq-conditionality="1"/g) || []).length}));
        """ % json.dumps(veri))

    def test_sunucu_blogunun_dokuz_alani_satir_olarak_basilir(self):
        blok = _kosulluluk_blogu()
        assert set(blok) == set(UQ_ALANLARI), (
            'sunucu bloğunun alan kümesi sözleşmeden kaydı: %r' % sorted(blok))
        o = self._html({'conditionality': blok})
        assert o['kutu'] == 1
        assert o['satir'] == list(UQ_ALANLARI), o['satir']
        # Değerler sunucudan AYNEN: sayı/ad türetilmez.
        for parca in ('thrust, burn_time, of_ratio', 'lhs',
                      'every model input not listed',
                      'independent (zero rank correlation)',
                      'NOT a confidence interval'):
            assert parca in o['html'], parca
        # model hatası banda girmiyor → vurgulu "hayır" (makine değeri False)
        assert '<b>no</b>' in o['html']
        # Denetçi 4. tur Ş2(b) (kör nokta W4): her değer KENDİ satırında,
        # alan adıyla okunur ve sunucu bloğunun değerine BİREBİR eşitlenir.
        # Belge düzeyindeki aramalar (yukarıda) satır çapraz bağlamasını
        # görmüyordu: `n_effective` satırı `input_count`ı basınca YEŞİL
        # kalıyordu (bandın dayandığı örnek sayısı yanlış basılır).
        # Sunucu bloğu: 3 örneklenen girdi, 29 örnek (_kosulluluk_blogu).
        assert blok['input_count'] == 3 and blok['n_effective'] == 29, blok
        hucre = self._deger_hucreleri(o['html'])
        assert hucre['input_count'] == '3', hucre
        assert hucre['n_effective'] == '29', hucre
        assert hucre == {
            'applies_to': _js_esc(blok['applies_to']),
            'conditional_on_inputs':
                '<span style="font-family:var(--hd-mono);">'
                + _js_esc(', '.join(blok['conditional_on_inputs']))
                + '</span>',
            'input_count': str(blok['input_count']),
            'frozen_at_nominal': _js_esc(blok['frozen_at_nominal']),
            'sampler': '<span style="font-family:var(--hd-mono);">'
                       + _js_esc(blok['sampler']) + '</span>',
            'n_effective': str(blok['n_effective']),
            'input_correlation_assumed':
                _js_esc(blok['input_correlation_assumed']),
            'model_form_uncertainty_included': '<b>no</b>',
            'interpretation': _js_esc(blok['interpretation']),
        }, hucre

    @staticmethod
    def _deger_hucreleri(html):
        """Koşulluluk tablosunda alan → değer hücresi (üçüncü sütun).

        Satır: ``<tr data-uq-cond-field="alan">`` + etiket + alan adı +
        değer (uncertainty_panel.js ``conditionalityHtml`` ``satir``)."""
        return dict(re.findall(
            r'<tr data-uq-cond-field="([a-z_]+)"><td[^>]*>.*?</td>'
            r'<td[^>]*>.*?</td><td[^>]*>(.*?)</td></tr>', html, flags=re.S))

    def test_blok_yoksa_kutu_da_satir_da_yok(self):
        o = self._html({'outputs': {}})
        assert o['html'] == '' and o['kutu'] == 0 and o['satir'] == []

    def test_yalniz_yayimlanan_alan_basilir_uydurma_yok(self):
        o = self._html({'conditionality': {'sampler': 'mc'}})
        assert o['satir'] == ['sampler'], o['satir']
        o = self._html({'conditionality': {'model_form_uncertainty_included': None}})
        # üç durumlu değil: yalnız bool basılır; null "hayır"a TERFİ ETMEZ
        assert o['satir'] == [] and o['html'] == ''

    def test_render_akisi_kutuyu_kartlarin_ustune_koyar(self):
        """Denetçi 2. tur Ş3 (kör nokta D1). Eski düğüm kaynak dizgesini
        arıyordu: ölü dala alınmış (``0 ? conditionalityHtml(data) : ''``)
        ya da yoruma alınmış çağrı YEŞİL kalıyordu. Şimdi panelin GERÇEK
        ``render(data, root)`` akışı en küçük DOM saplamasıyla koşar; kök
        düğüme eklenen çocukların ``innerHTML``i sırayla okunur ve kutunun
        P5-P95 kartlarından ÖNCE, kartlarla AYNI bölümde durduğu çıktıda
        ölçülür. ``outputs`` sayıları test fikstürüdür (panel yalnız
        biçimler, sayı türetmez); ``conditionality`` sunucunun gerçek
        bloğudur."""
        veri = {'status': 'ok', 'level': 'fast', 'n_samples': 29,
                'failed_samples': 0,
                'conditionality': _kosulluluk_blogu(),
                'outputs': {
                    'isp': {'p5': 240.0, 'p50': 245.0, 'p95': 250.0,
                            'std': 3.0, 'nominal': 245.1},
                    'thrust': {'p5': 2900.0, 'p50': 3000.0, 'p95': 3100.0,
                               'std': 60.0, 'nominal': 3000.0}}}
        o = node_kos(r"""
        const ui = new Proxy({}, {get: (t, k) => {
          if (k === 't') return (key, fb) => fb;
          if (k === 'tf') return tf;
          if (k === 'num') return (v) => String(v);
          if (k === 'source') return {ledgerInto() {}};
          return () => '';
        }});
        function eleman() {
          return {innerHTML: '', textContent: '', style: {}, children: [],
            appendChild(c) { this.children.push(c); },
            querySelector() { return {addEventListener() {}}; },
            addEventListener() {}, setAttribute() {}};
        }
        const W = {AnalysisDock: {ui: ui, register() {},
                                  getMotorType: () => 'hybrid'},
                   I18N: {lang: 'en', t: (k, f) => f, tf: tf,
                          serverText: (s) => s,
                          number: (v, d) => v.toFixed(d)},
                   requestAnimationFrame: () => 0};
        const D = {createElement: eleman, getElementById: () => null,
                   addEventListener() {}, querySelectorAll: () => [],
                   querySelector: () => null};
        yukle(['hrma/static/js/panels/uncertainty_panel.js'],
              {window: W, document: D});
        const kok = eleman();
        W.UncertaintyPanel._render(%s, kok);
        console.log(JSON.stringify({parca: kok.children.map((c) => c.innerHTML)}));
        """ % json.dumps(veri))
        parca = o['parca']
        KUTU = 'data-uq-conditionality="1"'
        KART = '90% band: 5th to 95th percentile'     # ciCard bant ipucu
        tum = ''.join(parca)
        assert tum.count(KUTU) == 1, (
            'kapsam kutusu render akışında basılmıyor (ya da iki kez)')
        assert tum.count(KART) == 2, 'P5-P95 kartları render edilmedi'
        # kutu, kartlarla AYNI bölümde (CI bölümü) ve ilk karttan ÖNCE
        bolum = [i for i, p in enumerate(parca) if KUTU in p]
        kartli = [i for i, p in enumerate(parca) if KART in p]
        assert bolum == kartli == [1], (bolum, kartli)
        assert parca[1].index(KUTU) < parca[1].index(KART), (
            'kapsam kutusu P5-P95 kartlarının ALTINDA basılıyor')
        # dokuz alanın dokuzu da akışta (kutu içeriği boş değil)
        assert [m for m in re.findall(r'data-uq-cond-field="([a-z_]+)"',
                                      parca[1])] == list(UQ_ALANLARI)


# ===========================================================================
# K2 · OH-D32-09 — τ seçimi duyarlılığı panelde
# ===========================================================================
TAU_BLOK = {
    'is_tau_sensitive': True,
    'frequency_hz_span': {'min_hz': 67.68803457167874,
                          'max_hz': 145.95560843309994,
                          'min_candidate': 'mixing_residence_time',
                          'max_candidate': 'selected',
                          'ratio': 2.156298515043145},
    'growth_is_tau_sensitive': None,
    'growth_rate_1_s_span': {'min_1_s': -40.0, 'max_1_s': -12.5,
                             'min_candidate': 'selected',
                             'max_candidate': 'mixing_residence_time',
                             'span_1_s': 27.5,
                             'ratio_not_applicable_reason': 'sign change'},
}
ASSESS = {'dp_ratio_j': 0.2, 'tau_s': 0.003, 'tau_c_s': 0.002,
          'inertance_included': False}


@gerek_node
class TestK2TauSecimi:

    def _gor(self, a, sonuclar=None):
        return node_kos(r"""
        const Y = yukle(['hrma/static/js/panels/stability_panel.js']);
        const S = Y.window.StabilityPanel;
        const sonuclar = %s;
        if (sonuclar) S.specChug.fromResults(sonuclar);
        const a = %s;
        const v = S._tauChoiceView(a, sonuclar ? S._chugLoopOf(sonuclar) : null);
        const html = S._tauChoiceHtml(a);
        console.log(JSON.stringify({durum: v.state, html: html,
          alan: [...html.matchAll(/data-stab-tau-field="([a-z_0-9]+)"/g)].map(m => m[1]),
          gri: [...html.matchAll(/data-stab-grey="([a-z-]+)"/g)].map(m => m[1])}));
        """ % (json.dumps(sonuclar), json.dumps(a)))

    @staticmethod
    def _sonuclar(dongu):
        return {'combustion_analysis': {'stability_analysis': {
            'chug_loop': dongu}}}

    def test_ucun_kendi_blogu_dort_alanla_basilir(self):
        a = dict(ASSESS, tau_choice_sensitivity=TAU_BLOK)
        o = self._gor(a)
        assert o['durum'] == 'block'
        assert o['alan'] == ['is_tau_sensitive', 'frequency_hz_span',
                             'growth_is_tau_sensitive', 'growth_rate_1_s_span']
        # yayımlanan bant ekranda, TR ayraçla (sig → I18N.decimalText)
        assert '67,688 – 145,956 Hz' in o['html'], o['html'][:900]
        assert 'mixing_residence_time → selected' in o['html']
        # null bayrak "ölçülmedi"dir, "hayır"a terfi etmez
        assert 'NOT MEASURED (null)' in o['html']
        assert 'sign change' in o['html']
        # Denetçi 4. tur Ş2(a) (kör noktalar W1, W2): dört hücre ALAN
        # ADIYLA okunur ve kendi beklenen değerine BİREBİR eşitlenir.
        # Belge düzeyindeki aramalar (yukarıda) satır çapraz bağlamasını
        # (bir satırın öteki bayrağı basması) ve büyüme bandında min/max ya
        # da aday sırasının ters basılmasını görmüyordu. Beklenen metin
        # TAU_BLOK'tan elle kurulmuştur: 6 anlamlı basamak (sigFig) + TR
        # ayraç; bant "min – max (min_candidate → max_candidate)".
        hucre = self._bayrak_hucreleri(o['html'])
        assert hucre == {
            'is_tau_sensitive': 'YES',
            'frequency_hz_span': ('67,688 – 145,956 Hz '
                                  '(mixing_residence_time → selected), '
                                  'ratio 2,1563'),
            'growth_is_tau_sensitive': 'NOT MEASURED (null)',
            # V301/PANEL-SAYI (28 Eki, FİZİK-2 DEVİR 5): TR ekranda
            # ÇEVRİLEMEYEN sunucu gerekçesi hücreye İngilizce basılmaz;
            # hücrede sözlük cümlesi (bu koşum sözlüksüz: yedek metin),
            # gerekçenin kendisi tablonun altında kapalı "Teknik ayrıntı
            # (çözücü beyanı, çevrilmedi)" içinde AYNEN.
            'growth_rate_1_s_span': ('-40 – -12,5 1/s '
                                     '(selected → mixing_residence_time), '
                                     'span 27,5 1/s — no ratio is published '
                                     '(reason: solver statement below)'),
        }, hucre
        assert re.search(r'<details data-stab-srv="1"[^>]*>.*?sign change',
                         o['html'], flags=re.S), o['html'][-600:]

    @staticmethod
    def _bayrak_hucreleri(html):
        """Blok tablosunda alan → değer hücresi (dört alanın ekran metni)."""
        return dict(re.findall(
            r'<tr data-stab-tau-field="([a-z_0-9]+)">.*?</span></td>'
            r'<td[^>]*>(.*?)</td></tr>', html, flags=re.S))

    def test_olculmus_duyarsizlik_hayir_basar(self):
        """Denetçi 3. tur Ş3 (kör nokta Y1): ``false`` YAYIMLANAN bir
        değerdir (hrma/stability/chug.py ``chug_tau_sensitivity``: frekans
        ve büyüme bandı ikisi de ölçülüp duyarsız çıkınca ``birlesik =
        False``). Ekranda "NO" basılır; "YES" (uydurma duyarlılık) ya da
        "NOT MEASURED" (ölçülmüş olanı ölçülmemiş gösterme) basılmaz.

        Blok sunucunun GERÇEK çıktısı: ``assess_chug`` ikinci aday τ ile
        (``alternative_taus``) koşulur; aday seçilen τ'ya eşit olduğundan
        iki eksenin bandı da tek noktadır, üç bayrak da ``False``."""
        from hrma.stability.chug import assess_chug
        a = assess_chug(dp_ratio_j=0.2, tau_s=0.003, tau_c_s=0.002,
                        alternative_taus={'mixing_residence_time': 0.003})
        blok = a['tau_choice_sensitivity']
        assert blok['is_tau_sensitive'] is False
        assert blok['growth_is_tau_sensitive'] is False
        o = self._gor(a)
        assert o['durum'] == 'block', o['durum']
        assert o['alan'] == ['is_tau_sensitive', 'frequency_hz_span',
                             'growth_is_tau_sensitive', 'growth_rate_1_s_span']
        hucre = self._bayrak_hucreleri(o['html'])
        assert hucre['is_tau_sensitive'] == 'NO', hucre
        assert hucre['growth_is_tau_sensitive'] == 'NO', hucre
        assert not re.search(r'\bYES\b', o['html']), (
            'ölçülmüş duyarsızlık "YES" diye basılıyor:\n' + o['html'])
        assert 'NOT MEASURED' not in o['html'], (
            'ölçülmüş duyarsızlık "NOT MEASURED" diye basılıyor:\n'
            + o['html'])

    # Denetçi 3. tur Ş4 (kör noktalar Y2, Y3): eşleşme toleransının SINIRI.
    # RUN_MATCH_REL_TOL = 1e-5 (stability_panel.js; gerekçe: dock ön
    # dolumu 6 anlamlı basamak, en kötü yarım-ulp 5e-6). Aşağıdaki vakalar
    # toleransın iki yanını kilitler: gerçek bir düzenleme (%1) motor
    # ölçümünü GİYDİRMEZ; kayan nokta gürültüsü (1e-7) ve 6 basamak
    # yuvarlaması (~4,9e-6) eşleşmeyi BOZMAZ. τ_f iki tarafta da varsa
    # DEĞERİ karşılaştırılır, varlığı değil.
    @pytest.mark.parametrize('dongu_girdisi, assess_eki', [
        pytest.param({'dp_ratio_j': 0.202, 'tau_s': 0.003, 'tau_c_s': 0.002},
                     {}, id='J_yuzde1'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.00303, 'tau_c_s': 0.002},
                     {}, id='tau_yuzde1'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003, 'tau_c_s': 0.00202},
                     {}, id='tau_c_yuzde1'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003, 'tau_c_s': 0.002,
                      'tau_f_s': 0.00101},
                     {'inertance_included': True, 'tau_f_s': 0.001},
                     id='tau_f_yuzde1'),
        # (iii) iki tarafta da τ_f var, değerler farklı
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003, 'tau_c_s': 0.002,
                      'tau_f_s': 0.002},
                     {'inertance_included': True, 'tau_f_s': 0.001},
                     id='tau_f_iki_tarafta_farkli'),
        # Devralma (29 Eyl): tolerans BAĞIL olmalı. Yukarıdaki %1 vakalarında
        # mutlak fark 1e-5 ya da üstünde olduğundan `relClose` mutlak 1e-5'e
        # çevrilince hepsi yine YEŞİL kalıyordu (bağımsız mutasyon V1).
        # Küçük ölçekli τ (0,2-0,3 ms) %1 düzenlemesinde mutlak fark
        # 2e-6 / 3e-6'dır.
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003, 'tau_c_s': 0.002,
                      'tau_f_s': 0.000202},
                     {'inertance_included': True, 'tau_f_s': 0.0002},
                     id='tau_f_kucuk_olcek_yuzde1'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.000303, 'tau_c_s': 0.002},
                     {'tau_s': 0.0003}, id='tau_kucuk_olcek_yuzde1'),
        # Denetçi 4. tur Ş3 (kör noktalar W3/W3b): toleransın ÜST kenarı.
        # stability_panel.js RUN_MATCH_REL_TOL yorumu: eşik "ilk 5 basamağı
        # oynatan her gerçek düzenlemenin ALTINDA". %1 vakaları yalnız 1e-2
        # altını kilitliyordu (1e-3 ve 9e-3 YEŞİL kalıyordu). Tek girdide 5.
        # anlamlı basamak düzenlemesi: bağıl ~1e-4 (J 0,2 → 0,20002;
        # τ_c 0,002 → 0,0020002) ve en dar hâli, mantis ~9,9999'da 5.
        # basamakta bir birim (τ 0,0099999 → 0,0099998; bağıl 1,00001e-5).
        pytest.param({'dp_ratio_j': 0.20002, 'tau_s': 0.003,
                      'tau_c_s': 0.002}, {}, id='J_5_basamak'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003,
                      'tau_c_s': 0.0020002}, {}, id='tau_c_5_basamak'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.0099998,
                      'tau_c_s': 0.002}, {'tau_s': 0.0099999},
                     id='tau_5_basamak_mantis_9'),
    ])
    def test_kucuk_gercek_fark_motor_olcumunu_giydirmez(self, dongu_girdisi,
                                                        assess_eki):
        dongu = {'status': 'modelled', 'inputs': dongu_girdisi,
                 'tau_choice_sensitivity': TAU_BLOK}
        o = self._gor(dict(ASSESS, **assess_eki), self._sonuclar(dongu))
        assert o['durum'] == 'other_inputs', o['durum']
        assert o['alan'] == [] and o['gri'] == ['tau-other-inputs']
        assert '67,688' not in o['html'], (
            'girdisi küçük ama gerçekten farklı koşuya motorun τ bandı '
            'giydirildi')

    @pytest.mark.parametrize('dongu_girdisi, assess_eki', [
        pytest.param({'dp_ratio_j': 0.2 * (1 + 1e-7), 'tau_s': 0.003,
                      'tau_c_s': 0.002}, {}, id='J_1e-7'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003 * (1 + 1e-7),
                      'tau_c_s': 0.002}, {}, id='tau_1e-7'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003,
                      'tau_c_s': 0.002 * (1 - 1e-7)}, {}, id='tau_c_1e-7'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003, 'tau_c_s': 0.002,
                      'tau_f_s': 0.001 * (1 + 1e-7)},
                     {'inertance_included': True, 'tau_f_s': 0.001},
                     id='tau_f_1e-7'),
        # dock ön dolumu: motor döngüsü tam değerle çözülmüş, koşu 6 anlamlı
        # basamağa yuvarlanmış değeri taşır (analysis_dock.js DOCK_SIGFIG =
        # 6) — bağıl fark ~4,99e-6, en kötü yarım-ulp (5e-6) yakını
        pytest.param({'dp_ratio_j': 0.100000499,
                      'tau_s': 0.003, 'tau_c_s': 0.002},
                     {'dp_ratio_j': float('%.6g' % 0.100000499)},
                     id='dock_6_basamak'),
        # Devralma (29 Eyl): küçük ölçekte de gürültü eşleşmeyi bozmaz
        # (bağıl tolerans; üstteki küçük ölçek %1 vakasının karşısı)
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003, 'tau_c_s': 0.002,
                      'tau_f_s': 0.0002 * (1 + 1e-7)},
                     {'inertance_included': True, 'tau_f_s': 0.0002},
                     id='tau_f_kucuk_olcek_1e-7'),
    ])
    def test_kayan_nokta_gurultusu_eslesmeyi_bozmaz(self, dongu_girdisi,
                                                    assess_eki):
        dongu = {'status': 'modelled', 'inputs': dongu_girdisi,
                 'tau_choice_sensitivity': TAU_BLOK}
        o = self._gor(dict(ASSESS, **assess_eki), self._sonuclar(dongu))
        assert o['durum'] == 'block', o['durum']
        assert len(o['alan']) == 4
        assert '67,688 – 145,956 Hz' in o['html']

    def test_motor_dongusu_ayni_girdilerle_okunur(self):
        dongu = {'status': 'modelled', 'inputs': {'dp_ratio_j': 0.2, 'tau_s': 0.003,
                            'tau_c_s': 0.002},
                 'tau_choice_sensitivity': TAU_BLOK}
        o = self._gor(dict(ASSESS), self._sonuclar(dongu))
        assert o['durum'] == 'block', o
        assert len(o['alan']) == 4
        assert 'chug_loop.tau_choice_sensitivity' in o['html']

    # Denetçi 2. tur Ş5 (kör nokta D3): eşleşme dört girdinin HER BİRİNDE
    # ayrı ayrı sınanır (eski düğüm yalnız J'yi değiştiriyordu; τ_c
    # karşılaştırması `true`ya çevrilince 5/5 YEŞİL kalıyordu). Her vakada
    # tek girdi farklıdır, geri kalanı ASSESS ile aynıdır.
    @pytest.mark.parametrize('dongu_girdisi, assess_eki', [
        pytest.param({'dp_ratio_j': 0.5, 'tau_s': 0.003, 'tau_c_s': 0.002},
                     {}, id='J'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.006, 'tau_c_s': 0.002},
                     {}, id='tau'),
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003, 'tau_c_s': 0.004},
                     {}, id='tau_c'),
        # döngü τ_f ile çözülmüş, bu koşu ataletsiz (τ_f yok)
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003, 'tau_c_s': 0.002,
                      'tau_f_s': 0.001}, {}, id='tau_f'),
        # döngü ataletsiz, bu koşu atalet terimini içeriyor
        pytest.param({'dp_ratio_j': 0.2, 'tau_s': 0.003, 'tau_c_s': 0.002},
                     {'inertance_included': True, 'tau_f_s': 0.001},
                     id='inertance'),
    ])
    def test_farkli_girdide_motor_olcumu_giydirilmez(self, dongu_girdisi,
                                                      assess_eki):
        dongu = {'status': 'modelled', 'inputs': dongu_girdisi,
                 'tau_choice_sensitivity': TAU_BLOK}
        o = self._gor(dict(ASSESS, **assess_eki), self._sonuclar(dongu))
        assert o['durum'] == 'other_inputs', o['durum']
        assert o['alan'] == [] and o['gri'] == ['tau-other-inputs']
        assert '67,688' not in o['html'], (
            'farklı girdide motorun τ bandı bu koşuya giydirildi')

    def test_tau_f_ayni_ise_motor_dongusu_okunur(self):
        """Ş5 karşı vakası: τ_f iki tarafta da aynıysa eşleşme kurulur
        (parametrik ret vakaları 'her şeyi reddet' ile geçmesin)."""
        dongu = {'status': 'modelled',
                 'inputs': {'dp_ratio_j': 0.2, 'tau_s': 0.003,
                            'tau_c_s': 0.002, 'tau_f_s': 0.001},
                 'tau_choice_sensitivity': TAU_BLOK}
        o = self._gor(dict(ASSESS, inertance_included=True, tau_f_s=0.001),
                      self._sonuclar(dongu))
        assert o['durum'] == 'block', o['durum']
        assert len(o['alan']) == 4

    def test_olculmedi_gerekcesi_aynen_basilir(self):
        dongu = {'status': 'modelled', 'inputs': {'dp_ratio_j': 0.2, 'tau_s': 0.003,
                            'tau_c_s': 0.002},
                 'tau_choice_not_measured': {
                     'reason': 'hybrid loop has a single candidate'}}
        o = self._gor(dict(ASSESS), self._sonuclar(dongu))
        assert o['durum'] == 'not_measured'
        assert o['gri'] == ['tau-not-measured']
        assert 'hybrid loop has a single candidate' in o['html']
        # Denetçi 2. tur Ş2 (kör nokta D4): hibrit örneğin GERÇEK yolu bu.
        # Ölçülmemiş duyarlılık "ÖLÇÜLMEDİ (null)" basar, "HAYIR"a terfi
        # etmez; gerekçe hükmün hemen ardından gelir.
        assert 'NOT MEASURED (null) — hybrid loop has a single candidate' \
            in o['html'], o['html']
        assert not re.search(r'\bNO\b', o['html']), (
            'ölçülmemiş τ duyarlılığı "NO" (tauNo) diye basılıyor:\n'
            + o['html'])

    def test_kaynak_yoksa_gri_ve_sayi_yok(self):
        o = self._gor(dict(ASSESS))
        assert o['durum'] == 'no_source' and o['gri'] == ['tau-no-source']
        assert not re.search(r'\d+\.\d+\s*(Hz|1/s)', o['html'])


# ===========================================================================
# K3 · OH-D33-09 — transient beş kesme alanı
# ===========================================================================
KESME = ('residual_oxidizer_kg', 'residual_impulse_at_cutoff_rate_Ns',
         'residual_impulse_fraction_at_cutoff_rate', 'vapor_phase_integrated',
         'vapor_tail_off_leaves_model_envelope')


def _transient(**ek):
    tr = {'end_event': 'oxidizer_depleted', 'burn_duration': 9.25,
          'total_impulse': 24400.0, 'time': [0, 1], 'thrust': [1, 1],
          'chamber_pressure': [1e6, 1e6], 'feed_mode': 'blowdown'}
    tr.update(ek)
    return {'status': 'success', 'transient': tr, 'design_point': {}}


@gerek_node
class TestK3TransientKesme:

    def _rozetler(self, veri):
        return node_kos(r"""
        const Y = yukle(['hrma/static/js/units_constants.js',
                         'hrma/static/js/transient_panel.js']);
        Y.window.TransientPanel._render(%s);
        const h = Y.ogeler['tp_badges'].innerHTML;
        console.log(JSON.stringify({html: h,
          alan: [...h.matchAll(/data-tp-cutoff-field="([A-Za-z_]+)"/g)].map(m => m[1])}));
        """ % json.dumps(veri))

    # transient_panel.js `badge(text, kind)` rengi kenarlık değişkeninden
    # okunur (kind → theme.css jetonu; bilinmeyen kind `info`ya düşer).
    RENK_JETONU = {'--hd-cyan': 'info', '--hd-orange': 'warn',
                   '--hd-green': 'ok', '--hd-red': 'err'}

    @staticmethod
    def _rozet_metni(html):
        """Kesme alanı → rozetin görünen metni (alan adıyla)."""
        return dict(re.findall(
            r'data-tp-cutoff-field="([A-Za-z_]+)"><span[^>]*>(.*?)</span>',
            html, flags=re.S))

    def _renk(self, html):
        cift = re.findall(r'data-tp-cutoff-field="([A-Za-z_]+)"><span[^>]*?'
                          r'border:1px solid var\((--hd-[a-z]+)', html)
        return {alan: self.RENK_JETONU[jeton] for alan, jeton in cift}

    def test_blowdown_bes_alan_ad_ve_degerle_tr_ondalikla(self):
        o = self._rozetler(_transient(
            residual_oxidizer_kg=2.4206156589045116,
            residual_impulse_at_cutoff_rate_Ns=6449.577218595157,
            residual_impulse_fraction_at_cutoff_rate=0.2650086602951435,
            vapor_phase_integrated=False,
            vapor_tail_off_leaves_model_envelope=True))
        assert o['alan'] == list(KESME), o['alan']
        # blowdown: tank var → sınırlayan yöndeki bayrak `warn`
        renk = self._renk(o['html'])
        assert renk['vapor_phase_integrated'] == 'warn', renk
        assert renk['vapor_tail_off_leaves_model_envelope'] == 'warn', renk
        # Rozet metni ALAN ADIYLA okunur (belge düzeyinde adsız arama
        # değil — tests/test_d28_bekci_cevirisi_a1.py OH-D27-17 sınıf C;
        # denetçi 3. tur süpürmesinde eski döngü o bekçinin listesine
        # ekleniyordu). Her alanın rozeti tam olarak beklenen metindir.
        assert self._rozet_metni(o['html']) == {
            'residual_oxidizer_kg': 'residual_oxidizer_kg 2,421 kg',
            'residual_impulse_at_cutoff_rate_Ns':
                'residual_impulse_at_cutoff_rate_Ns 6449,6 N·s',
            'residual_impulse_fraction_at_cutoff_rate':
                'residual_impulse_fraction_at_cutoff_rate 0,2650',
            'vapor_phase_integrated': 'vapor_phase_integrated false',
            'vapor_tail_off_leaves_model_envelope':
                'vapor_tail_off_leaves_model_envelope true',
        }

    def test_reguleli_kipte_null_alan_basilmaz(self):
        o = self._rozetler(_transient(
            feed_mode='regulated', residual_oxidizer_kg=None,
            residual_impulse_at_cutoff_rate_Ns=None,
            residual_impulse_fraction_at_cutoff_rate=None,
            vapor_phase_integrated=False,
            vapor_tail_off_leaves_model_envelope=None))
        assert o['alan'] == ['vapor_phase_integrated'], o['alan']
        assert 'residual_oxidizer_kg' not in o['html']
        assert ' 0 kg' not in o['html'] and 'null' not in o['html']
        # Denetçi 2. tur Ş5 (kör nokta D6): regüleli kipte tank yok →
        # `vapor_phase_integrated false` sınırlanan bir kuyruk bildirmez,
        # rozet `info` (ad ve değer yine aynen basılır).
        assert self._renk(o['html']) == {'vapor_phase_integrated': 'info'}

    # Denetçi 3. tur Ş5 (kör nokta Y9): blowdown'da bayrak rengi DEĞERE
    # bağlıdır. Sınırlamayan değer (buhar fazı YÜRÜNDÜ = true; kuyruk model
    # zarfında = false) `info`; yalnız sınırlayan değer `warn`. Tank
    # kapısının arkasında da değer okunmazsa her blowdown bayrağı uyarı
    # basar (uydurma sınırlama).
    @pytest.mark.parametrize('buhar, zarf, beklenen', [
        pytest.param(True, False, {'vapor_phase_integrated': 'info',
                                   'vapor_tail_off_leaves_model_envelope':
                                       'info'}, id='ikisi_sinirlamiyor'),
        pytest.param(True, True, {'vapor_phase_integrated': 'info',
                                  'vapor_tail_off_leaves_model_envelope':
                                      'warn'}, id='yalniz_zarf'),
        pytest.param(False, False, {'vapor_phase_integrated': 'warn',
                                    'vapor_tail_off_leaves_model_envelope':
                                        'info'}, id='yalniz_buhar'),
    ])
    def test_blowdown_sinirlamayan_bayrak_info(self, buhar, zarf, beklenen):
        o = self._rozetler(_transient(
            residual_oxidizer_kg=2.4206156589045116,
            residual_impulse_at_cutoff_rate_Ns=6449.577218595157,
            residual_impulse_fraction_at_cutoff_rate=0.2650086602951435,
            vapor_phase_integrated=buhar,
            vapor_tail_off_leaves_model_envelope=zarf))
        assert o['alan'] == list(KESME), o['alan']
        renk = self._renk(o['html'])
        assert {a: renk[a] for a in beklenen} == beklenen, renk
        # değer yine AYNEN basılır (alan adıyla okunur)
        metin = self._rozet_metni(o['html'])
        assert metin['vapor_phase_integrated'] == (
            f'vapor_phase_integrated {str(buhar).lower()}'), metin
        assert metin['vapor_tail_off_leaves_model_envelope'] == (
            f'vapor_tail_off_leaves_model_envelope {str(zarf).lower()}'), metin

    # Denetçi 4. tur Ş4(i) (kör nokta W5): sayısal kesme rozetinin rengi de
    # DEĞERE bağlıdır (transient_panel.js ``k[1] > 0 ? 'warn' : 'info'``).
    # Sunucu aynı eşiği kullanır: kesme uyarısı yalnız tankta oksitleyici
    # kaldığında yazılır (hrma/analysis/transient_ballistics.py
    # ``artik_ox > 0.0``). Sıfır artık (tank tam boşaldı → kesilen impuls ve
    # payı da sıfır) sınırlayan bir kesme değildir → `info`; uyarı rengi
    # almaz. Değer yine AYNEN basılır (sıfır "yok" sayılmaz).
    @pytest.mark.parametrize('kg, ns, pay, renk, metin', [
        pytest.param(0.0, 0.0, 0.0, 'info',
                     ('residual_oxidizer_kg 0,000 kg',
                      'residual_impulse_at_cutoff_rate_Ns 0,0 N·s',
                      'residual_impulse_fraction_at_cutoff_rate 0,0000'),
                     id='sifir_artik_info'),
        pytest.param(2.4206156589045116, 6449.577218595157,
                     0.2650086602951435, 'warn',
                     ('residual_oxidizer_kg 2,421 kg',
                      'residual_impulse_at_cutoff_rate_Ns 6449,6 N·s',
                      'residual_impulse_fraction_at_cutoff_rate 0,2650'),
                     id='pozitif_artik_warn'),
    ])
    def test_sayisal_kesme_rengi_degere_bagli(self, kg, ns, pay, renk,
                                              metin):
        o = self._rozetler(_transient(
            residual_oxidizer_kg=kg,
            residual_impulse_at_cutoff_rate_Ns=ns,
            residual_impulse_fraction_at_cutoff_rate=pay,
            vapor_phase_integrated=True,
            vapor_tail_off_leaves_model_envelope=False))
        assert o['alan'] == list(KESME), o['alan']
        sayisal = KESME[:3]
        r = self._renk(o['html'])
        assert {a: r[a] for a in sayisal} == dict.fromkeys(sayisal, renk), r
        m = self._rozet_metni(o['html'])
        assert tuple(m[a] for a in sayisal) == metin, m

    def test_ters_muafiyetten_bes_satir_dustu(self):
        agac = ast.parse(oku('tests/test_wave3_contract.py'))
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.Assign)
                    and any(getattr(h, 'id', None) == 'TERS_MUAFIYET'
                            for h in dugum.targets)):
                tablo = ast.literal_eval(dugum.value)
                break
        else:
            pytest.fail('TERS_MUAFIYET bulunamadı')
        muaf = tablo['transient'][1]
        assert not set(KESME) & set(muaf), sorted(set(KESME) & set(muaf))


# ===========================================================================
# K5 · DV36-04 — ekran ondalığı: `.toFixed(` sınıflandırması
# ===========================================================================
def _govde_araligi(kaynak, bas_deseni):
    """``bas_deseni``nden başlayan fonksiyon gövdesinin [bas, son] satırları
    (dize içindeki parantezler atlanır).

    İfade gövdeli ok işlevi (``const f = (v, n) => (...);``) için gövde,
    ``=>``dan sonraki ilk ÜST DÜZEY ``;``de biter (denetçi 2. tur Ş1: eski
    hâl bir sonraki ``{``'nin kapanışına kadar taşıyor, aradaki satırları da
    'yardımcı' sayıyordu).
    """
    m = re.search(bas_deseni, kaynak)
    assert m, bas_deseni
    k = m.end()
    while k < len(kaynak) and kaynak[k].isspace():
        k += 1
    ifade_govdeli = (kaynak[m.start():m.end()].rstrip().endswith('=>')
                     and kaynak[k] != '{')
    if ifade_govdeli:
        d, j, dize = 0, k, None
        while j < len(kaynak):
            c = kaynak[j]
            if dize:
                if c == '\\':
                    j += 2
                    continue
                if c == dize:
                    dize = None
            elif c in '\'"`':
                dize = c
            elif c in '([{':
                d += 1
            elif c in ')]}':
                d -= 1
            elif c == ';' and d == 0:
                break
            j += 1
        return (kaynak.count('\n', 0, m.start()) + 1,
                kaynak.count('\n', 0, j) + 1)
    i = kaynak.index('{', m.end() - 1)
    d, j, dize = 0, i, None
    while j < len(kaynak):
        c = kaynak[j]
        if dize:
            if c == '\\':
                j += 2
                continue
            if c == dize:
                dize = None
        elif c in '\'"`':
            dize = c
        elif c == '{':
            d += 1
        elif c == '}':
            d -= 1
            if d == 0:
                break
        j += 1
    return (kaynak.count('\n', 0, m.start()) + 1,
            kaynak.count('\n', 0, j) + 1)


def _cagri_araliklari(kaynak, ad):
    """``console.warn(`` gibi bir çağrının açılıştan kapanışa satır aralığı."""
    out = []
    for m in re.finditer(re.escape(ad) + r'\(', kaynak):
        d, j, dize = 0, m.end() - 1, None
        while j < len(kaynak):
            c = kaynak[j]
            if dize:
                if c == '\\':
                    j += 2
                    continue
                if c == dize:
                    dize = None
            elif c in '\'"`':
                dize = c
            elif c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d == 0:
                    break
            j += 1
        out.append((kaynak.count('\n', 0, m.start()) + 1,
                    kaynak.count('\n', 0, j) + 1))
    return out


def tofixed_siniflari(rel, makine_fonksiyonlari=(), yardimcilar=()):
    """Dosyadaki her kod satırı ``.toFixed(`` çağrısını kanala ayırır.

    makine: SVG koordinat kurucusu (adıyla), form ``.value =`` yazımı,
    geliştirici ``console.*`` karşılaştırması; yardımcı: ekran
    yardımcısının i18n.js yokken nokta yedeği. Geri kalan her çağrı EKRAN
    metnidir ve ``I18N.number``ı atlıyordur.
    """
    kaynak = oku(rel)
    satirlar = kaynak.split('\n')
    makine = [_govde_araligi(kaynak, r'function\s+%s\s*\(' % f)
              for f in makine_fonksiyonlari]
    yard = [_govde_araligi(kaynak, d) for d in yardimcilar]
    gunluk = []
    for ad in ('console.warn', 'console.error', 'console.log'):
        gunluk += _cagri_araliklari(kaynak, ad)
    sonuc = {'ekran': [], 'makine': [], 'yardimci': []}
    for no, satir in enumerate(satirlar, 1):
        yalin = satir.strip()
        if yalin.startswith(('//', '*', '/*')):
            continue
        n = satir.count('.toFixed(')
        if not n:
            continue
        if any(a <= no <= b for a, b in yard):
            sinif = 'yardimci'
        elif (any(a <= no <= b for a, b in makine + gunluk)
              or re.search(r'\.value\s*=\s*[^=]', satir)):
            sinif = 'makine'
        else:
            sinif = 'ekran'
        sonuc[sinif] += [(no, yalin[:120])] * n
    return sonuc


class TestK5EkranOndaligi:

    def test_sixdof_ekran_cagrisi_kalmadi(self):
        s = tofixed_siniflari(
            'hrma/static/js/sixdof_panel.js',
            makine_fonksiyonlari=('drawSchematic',),
            yardimcilar=(r'function\s+sayiEkran\s*\(',
                         r'const notSayi = \(v, n\) =>',
                         # denetçi 2. tur Ş1: rozet bloğunun gövde içi
                         # yardımcısı (test_faz5_ui harness'ı bloğu keser)
                         r'const rozetSayi = \(v, n\) =>'))
        assert s['ekran'] == [], (
            'sixdof_panel.js ekran metnini hâlâ çıplak .toFixed( ile '
            'kuruyor (TR sayfada nokta basar): %r' % s['ekran'])
        # makine kanalı sayıldı: SVG koordinatları + form + geliştirici
        assert len(s['makine']) >= 30, s['makine'][:5]
        assert len(s['yardimci']) == 3, s['yardimci']

    def test_blowdown_yalniz_devirli_kesme_rozeti_kaldi(self):
        s = tofixed_siniflari(
            'hrma/static/js/blowdown_panel.js',
            yardimcilar=(r'function\s+sayiEkran\s*\(',))
        # DEVİR (rapor.md): tests/test_d29_arayuz_panel_a1.py bu dizgeyi
        # LİTERAL arıyor; kartta adı yok → dokunulmadı.
        assert [m for _n, m in s['ekran']] == [
            "html += badge(k.field + ' ' + k.value.toFixed(k.digits) + k.unit,"
        ], s['ekran']
        assert len(s['yardimci']) == 1

    @gerek_node
    def test_blowdown_rozetleri_tr_ondalikla(self):
        """Canlı: blowdown rozetleri TR biçimlendiriciden geçer."""
        o = node_kos(r"""
        const kaynak = fs.readFileSync('hrma/static/js/blowdown_panel.js', 'utf8');
        const Y = yukle([]);
        const m = kaynak.match(/function sayiEkran\(v, n\) \{[\s\S]*?\n    \}/);
        const ctx = {window: Y.window};
        vm.createContext(ctx);
        vm.runInContext(m[0] + '; this.f = sayiEkran;', ctx);
        console.log(JSON.stringify({a: ctx.f(3006.6, 1), b: ctx.f(-0.0022, 4),
                                    c: ctx.f(9.25, 2)}));
        """)
        assert o == {'a': '3006,6', 'b': '-0,0022', 'c': '9,25'}, o

    @gerek_node
    def test_sixdof_rozet_blogu_tr_ondalikla_ve_i18n_yokken_noktayla(self):
        """Denetçi 2. tur Ş1 — rozet bloğu (``const numOf`` → rozet HTML'i;
        ``tests/test_faz5_ui.py`` ile AYNI kesim) node'da iki kez koşar:
        TR biçimlendiriciyle virgül, ``window`` yokken nokta. Özet
        ``test_faz5_ui`` time_limit ölçümünün kendisi (POST
        /api/six-dof-analysis, 2026-08-03)."""
        ozet = {'apogee': None, 'apogee_time': None, 'stable': None,
                'max_mach': 0.27473448283522395, 'max_alpha_deg': 0.0,
                'static_margin_full': 4.841810538672934,
                'static_margin_empty': 5.841810538672935,
                'cn_alpha': 11.106843491233196, 'x_cp': 1.5841810538672936,
                'max_speed': 93.44179868510761, 'end_reason': 'time_limit'}
        o = node_kos(r"""
        const kaynak = fs.readFileSync('hrma/static/js/sixdof_panel.js', 'utf8');
        const bas = kaynak.indexOf('const numOf = (v) =>');
        const son = kaynak.indexOf('badges.innerHTML = html;', bas);
        function kos(pencere) {
          // T-ÇAPA-C2: render(data, usedCurve, sayfaMotoru, aracKuru) imzası
          // (V301/H-PANEL 4e16c916e, UÇUŞ 34996377f); yük sayfa motoru
          // taşımaz -> ikisi de null (test_faz5_ui ile aynı kesim).
          const ctx = {s: %s, usedCurve: true, sayfaMotoru: null, aracKuru: null,
            Number, Math, String, isFinite,
            badge: (t, k) => '[' + k + ']' + t + '\n', T: (k, f) => f, TF: tf};
          if (pencere) ctx.window = pencere;
          vm.createContext(ctx);
          vm.runInContext(kaynak.slice(bas, son) + '\nthis.__html = html;', ctx);
          return ctx.__html;
        }
        console.log(JSON.stringify({tr: kos(yukle([]).window), yok: kos(null)}));
        """ % json.dumps(ozet))
        for parca in ('MAX MACH 0,27', 'MARGIN 4,84 / 5,84 cal',
                      'max_speed 93,4 m/s', 'CNα 11,11 · CP 1,584 m',
                      'MAX alpha 0,0 deg'):
            assert parca in o['tr'], (parca, o['tr'])
        assert not re.search(r'\d\.\d', o['tr']), (
            'TR rozet metninde noktalı ondalık kaldı:\n' + o['tr'])
        for parca in ('MAX MACH 0.27', 'MARGIN 4.84 / 5.84 cal',
                      'max_speed 93.4 m/s'):
            assert parca in o['yok'], (parca, o['yok'])

    def test_sd_thrust_src_sabit_280_px_ile_kesilmez(self):
        kaynak = oku('hrma/static/js/sixdof_panel.js')
        m = re.search(r'<select id="sd_thrust_src" style="([^"]*)"', kaynak)
        assert m, 'sd_thrust_src seçicisi yok'
        assert 'max-width:280px' not in m.group(1).replace(' ', '')
        assert 'max-width:100%' in m.group(1).replace(' ', '')


# ===========================================================================
# K6 · OH-D37-G2 — koşu noktasının künyesi
# ===========================================================================
def _son_ipucu_satiri(iz):
    """Koşu noktası ipucunun son satırı (çıkış künyesi), Plotly'nin
    ``<extra></extra>`` kuyruğu atılmış olarak."""
    h = iz['hovertemplate']
    assert h.endswith('<extra></extra>'), h
    return h[:-len('<extra></extra>')].split('<br>')[-1]


class TestK6KosuNoktasiKunyesi:

    @staticmethod
    def _nokta(eps=None, sil_taban=False, sil_pe=False, taban=None):
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        from hrma.visualization.visualization import (
            create_combustion_analysis_plots)
        a = CombustionAnalyzer()
        cd = (a.analyze_combustion({'htpb': 100.0}, 'n2o', 7.0, 30.0,
                                   expansion_ratio=eps)
              if eps else a.analyze_combustion({'htpb': 100.0}, 'n2o', 7.0, 30.0))
        if taban is not None:
            # Denetçi 3. tur Ş5: künye YANIT üstünde değiştirilir (sil_taban
            # deseni); sayı (performance.isp, O/F) aynen kalır.
            cd = json.loads(json.dumps(cd))
            cd['conditions']['exit']['basis'] = taban
        if sil_taban:
            cd = json.loads(json.dumps(cd))
            del cd['conditions']['exit']['basis']
        if sil_pe:
            cd = json.loads(json.dumps(cd))
            del cd['conditions']['exit']['P']
        f = json.loads(create_combustion_analysis_plots(cd))
        kosu = [t for t in f['data'] if t.get('name') == 'This run (solver)']
        assert len(kosu) == 1
        # v3.0.1 (V301/N-grafik G3): pano dipnotu satırlara sarılır (sağdan
        # taşıyordu); satır sonu sunumdur, cümle aynıdır — '<br>' + girinti
        # tek boşluğa indirgenerek karşılaştırılır.
        notlar = re.sub(r'<br>\s*', ' ', ' '.join(
            x.get('text', '') for x in f['layout']['annotations']))
        return cd, kosu[0], notlar

    def test_deniz_seviyesi_capasi_ayni_capa_notu(self):
        cd, k, notlar = self._nokta()
        assert k['y'][0] == cd['performance']['isp']           # sayı aynı
        m = k['meta']
        assert m['exit_basis'] == 'sea_level_default_equilibrium'
        assert m['same_exit_anchor_as_curve'] is True
        assert m['isp_source'] == 'combustion_data.performance.isp'
        assert 'Exit: ISA sea level, no nozzle ε' in k['hovertemplate']
        assert 'the same exit anchor as the sweep curve' in notlar
        # Ş6: G-1 sözlüğüyle eşlik — ε anahtarı var, değer uydurulmaz
        assert 'expansion_ratio' in m and m['expansion_ratio'] is None

    def test_genlesme_oraniyla_cozulen_nokta_farkli_yol_notu(self):
        cd, k, notlar = self._nokta(eps=6.0)
        assert k['y'][0] == cd['performance']['isp']
        assert k['meta']['same_exit_anchor_as_curve'] is False
        assert k['meta']['exit_pressure_bar'] == pytest.approx(
            cd['conditions']['exit']['P'])
        assert 'supplied nozzle ε' in k['hovertemplate']
        # Denetçi 4. tur Ş4(ii) (kör nokta W6): ipucundaki p_e EKRANDA
        # görünen değerdir; yalnız 'p_e ' öneki aranınca p_e ×10 basılsa da
        # YEŞİL kalıyordu. Son ipucu satırı sunucunun yayımladığı çıkış
        # basıncıyla (conditions.exit.P, bar; combustion_analysis.py
        # ``eq_exit['P'] / 1e5``) BİREBİR kurulur.
        assert _son_ipucu_satiri(k) == (
            f"Exit: supplied nozzle ε, p_e "
            f"{cd['conditions']['exit']['P']:.3f} bar"), k['hovertemplate']
        assert 'a different thermochemistry path' in notlar
        # Ş6: ε yolunda da combustion_data ε yayımlamıyor → None (uydurma yok)
        assert k['meta']['expansion_ratio'] is None

    # Denetçi 3. tur Ş5 (kör nokta Y8): combustion_analysis.py'nin
    # yayımladığı DÖRT çıkış künyesinin hepsi eşlenir. Tek-γ geri dönüş
    # künyeleri ('sea_level_default', 'expansion_ratio'; denge çözücüsü
    # kullanılamadığında) denge künyeleriyle AYNI yola gider: deniz
    # seviyesi çapası "aynı çapa", ε ile çözülen çıkış "farklı yol".
    @pytest.mark.parametrize('taban, eps, deniz', [
        pytest.param('sea_level_default_equilibrium', None, True,
                     id='sea_level_default_equilibrium'),
        pytest.param('sea_level_default', None, True, id='sea_level_default'),
        pytest.param('expansion_ratio_equilibrium', 6.0, False,
                     id='expansion_ratio_equilibrium'),
        pytest.param('expansion_ratio', 6.0, False, id='expansion_ratio'),
    ])
    def test_dort_yayimlanan_kunye_dogru_yola_eslenir(self, taban, eps,
                                                       deniz):
        cd, k, notlar = self._nokta(eps=eps, taban=taban)
        assert k['y'][0] == cd['performance']['isp']           # sayı aynı
        assert k['meta']['exit_basis'] == taban
        assert k['meta']['same_exit_anchor_as_curve'] is deniz
        assert f'(exit basis {taban})' in notlar
        if deniz:
            assert 'Exit: ISA sea level, no nozzle ε' in k['hovertemplate']
            assert 'the same exit anchor as the sweep curve' in notlar
            assert 'different thermochemistry path' not in notlar
        else:
            assert 'Exit: supplied nozzle ε, p_e ' in k['hovertemplate']
            # Ş4(ii): ipucundaki p_e yayımlanan çıkış basıncına birebir
            assert _son_ipucu_satiri(k) == (
                f"Exit: supplied nozzle ε, p_e "
                f"{cd['conditions']['exit']['P']:.3f} bar"), (
                k['hovertemplate'])
            assert 'a different thermochemistry path' in notlar
            assert 'same exit anchor' not in notlar

    def test_eps_yolunda_cikis_basinci_yoksa_nan_basilmaz(self):
        """Denetçi 2. tur Ş6: ε yolunda P yayımlanmazsa ipucu 'p_e nan bar'
        değil 'p_e not published' der (fail-closed); nokta yine aynı."""
        cd, k, _notlar = self._nokta(eps=6.0, sil_pe=True)
        assert k['y'][0] == cd['performance']['isp']
        assert k['meta']['exit_pressure_bar'] is None
        assert 'Exit: supplied nozzle ε, p_e not published' in k['hovertemplate']
        assert 'nan' not in k['hovertemplate'].lower()

    def test_kunye_yoksa_yol_iddiasi_yok(self):
        _cd, k, notlar = self._nokta(sil_taban=True)
        assert k['meta']['exit_basis'] is None
        assert k['meta']['same_exit_anchor_as_curve'] is None
        assert 'does not publish its exit basis' in notlar
        assert 'same exit anchor' not in notlar
        assert 'different thermochemistry path' not in notlar


# ===========================================================================
# K7 · OH-D37-H1 — D22 düzeneği kullanıcı kanalını topluyor
# ===========================================================================
@gerek_node
class TestK7AgKopmasiKanali:

    def test_m4_uc_imzanin_her_biri_kullaniciya_metin_ulastirir(self):
        from tests.support.kanit import kanit_gerekli
        harness = os.path.join(KOK, 'docs/scofield/raw/OH/D22/arayuz/a1/kanit_node.js')
        r = subprocess.run([NODE, kanit_gerekli(harness)], capture_output=True,
                           text=True, cwd=KOK, timeout=300)
        assert r.returncode == 0, r.stderr[-1500:]
        m4 = json.loads(r.stdout)['M4_hata']
        assert len(m4['uyari_metinleri']) == len(m4['ag_kopmasi']) == 3, m4
        for metin in m4['uyari_metinleri']:
            assert 'Could not reach the HRMA server' in metin
