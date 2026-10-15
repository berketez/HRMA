# -*- coding: utf-8 -*-
"""ÖH Dalga-15 / kulvar ui-paneller, aşama 3 — bekçiler.

Kapsanan defter kalemleri (ham kanıt
``docs/scofield/raw/OH/D15/ui-paneller/a3/{once,sonra}.json``):

* **P11B4-13** ``safety_panel`` dürüstlük bloğu "every input behind the
  numbers below came from this form" diyordu; AYNI yanıt iki kez
  ``ASSUMED L/D = 5 (chamber_length was not supplied)`` beyan ediyor ve
  ``chamber_length`` panelin ``FIELDS`` listesinde hiç yok.
* **P11B4-16** ``uncertainty_panel`` kaymayı "(nonlinear response)" diye
  künyeliyordu; ucun ``consistency_note``'u kaymanın %99'unun pinlenmiş
  ``eta_c_star``tan geldiğini yazıyor ve panel o notu hiç basmıyordu.
* **P11B4-20** ``feed_panel`` su koçunda KIRMIZI ``PEAK PRESSURE`` kartı
  215,6 bar gösteriyordu (boru MAWP 229,3 bar); hükmün dayandığı
  ``design_peak_pressure_bar`` = 411,1 bar hiçbir kart/satır değildi.
* **P11B4-31** ``structural_panel`` analizi süren 5,00 mm cidarı ekranda
  hiç göstermiyordu (yalnız 2,62 / 3,14 mm ÖNERİsi).
* **P11B5-04** ``comparative_panel`` Isp'yi ``m.isp`` ile okuyordu; katı ve
  sıvı yanıtlarında o anahtar yok → ``BEST ISP`` kalıcı olarak "—".
* **P11B5-05** ``thermal_panel`` "(steel equiv.) / 200 K rise" etiketi
  ölçümle TERS (kütle seçilen malzemenin cp'siyle, ucun kendi ΔT'siyle).
* **P11B5-06** ıslak alan ve ondan türeyen satırlar, ucun "ıraksak kısım
  BU MOTORUN DEĞİL" beyanını taşımıyordu.
* **P11B5-07** ``injector_schematics`` üç farklı seçimde BAYT-ÖZDEŞ SVG
  basıyor ve üçünü de "Impinging doublet" diye künyeliyordu.
* **P11B5-08** ``blowdown_panel`` NEGATİF ``thrust_decay_fraction``ı
  "THRUST DECAY -32%" diye adlandırıp nötr cyan basıyordu.
* **P11B5-09** ``sixdof_panel`` 2,025 c hızlı bir koşumda ``MAX MACH``
  rozetini nötr cyan basıyor, ``max_speed``i hiç göstermiyor ve grafik
  başlığında "launch to apogee" iddia ederken apoje raporlanmıyordu.
* **P11B5-03** — defter başlığı bu HEAD'de ÖLÇÜMLE ÇÜRÜTÜLDÜ
  (``injector_panel`` artık ``design.warnings`` / ``design.assumptions``
  okuyor). Buradaki bekçi ÇÜRÜTMEYİ KİLİTLER: uyarı/varsayım kanalı
  yeniden ``*_tr`` adlarına dönerse KIRMIZI olur.

Yöntem: hiçbir iddia kaynak okumaya dayanmaz. Paneller
``docs/scofield/raw/P11/B4-repro-03.js`` taklit DOM'unda GERÇEKTEN render
edilir; dışa verilmeyen iç fonksiyonlar (blowdown ``renderBadges``, sixdof
``render``) kaynak metne TEK SATIRLIK bir dışa-verme eklenerek koşturulur —
fonksiyonun kendisi değiştirilmez. Beklenen sayılar ürün sabitlerinden
TÜRETİLMEZ: her eşik o koşumun uç yanıtından okunur. Uç yükleri
``docs/scofield/raw/OH/D15/ui-paneller/a3/yuk/`` altında GERÇEK koşum
çıktılarıdır (``yuk_uret.py``).
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'P11' / 'B4-repro-03.js'
A3 = REPO_ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'D15' / 'ui-paneller' / 'a3'
YUK = A3 / 'yuk'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(
    NODE is None,
    reason='node kurulu değil — panelleri GERÇEK render altında ölçen '
           'bekçiler koşamaz (kurulum: `brew install node`)')

YESIL = 'var(--hd-green'
TURUNCU = 'var(--hd-orange'
KIRMIZI = 'var(--hd-red'
MAVI = 'var(--hd-cyan'
SONUK = 'var(--hd-ink-dim'
RENKLER = ((YESIL, 'yesil'), (TURUNCU, 'turuncu'), (KIRMIZI, 'kirmizi'),
           (MAVI, 'mavi'), (SONUK, 'sonuk'))


def kostur(**cfg):
    p = subprocess.run([NODE, kanit_gerekli(str(HARNESS))], input=json.dumps(cfg),
                       capture_output=True, text=True, cwd=str(REPO_ROOT),
                       timeout=300)
    assert p.returncode == 0, 'harness çöktü:\n' + p.stderr[-2000:]
    out = json.loads(p.stdout)
    assert not out.get('error'), 'panel render hatası: %s' % out.get('error')
    ev = out.get('evaled')
    if isinstance(ev, dict):
        assert not ev.get('_err'), 'evalFn hatası: %s' % ev.get('_err')
    return out


def govde(ad):
    with open(kanit_gerekli(YUK / (ad + '.json'))) as f:
        return json.load(f)['body']


def renk_geri(html, imlec):
    """Rozet: renk jetonu METİNDEN ÖNCE gelir (border/color → metin)."""
    if imlec < 0:
        return None
    onc, en = html[:imlec], None
    for jeton, ad in RENKLER:
        i = onc.rfind(jeton)
        if i > (en[0] if en else -1):
            en = (i, ad)
    return en[1] if en else None


def renk_ileri(html, imlec):
    """statCard: DEĞER etiketten SONRA gelir."""
    if imlec < 0:
        return None
    en = None
    for jeton, ad in RENKLER:
        i = html.find(jeton, imlec)
        if i >= 0 and (en is None or i < en[0]):
            en = (i, ad)
    return en[1] if en else None


def duz(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', html)).strip()


# ======================================================================
# P11B4-13 — dürüstlük cümlesi kazanılmadığında basılmaz
# ======================================================================
@node_gerekli
class TestSafetyVarsayilanDurustlugu:

    def _render(self):
        r = kostur(panelId='safety', dataFile=kanit_gerekli(str(YUK / 'safety.json')),
                   panelFiles=['hrma/static/js/panels/safety_panel.js'])
        assert r['text'].strip(), 'BOŞ render — ölçüm vakuus olurdu'
        return r

    def test_uc_bu_kosumda_gercekten_varsayim_beyan_ediyor(self):
        """Boş-geçme koruması: kusurun ön koşulu o koşumda VAR mı?"""
        b = govde('safety')
        assert b['defaults_applied'] == [], 'uç bu koşumda varsayılan bildirdi'
        sa = b['safety_analysis']
        rad = sa['thermal_safety']['radiating_area_basis']
        frg = sa['explosive_hazards']['fragment_hazards']['case_mass_basis']
        assert 'ASSUMED' in rad and 'chamber_length' in rad
        assert 'ASSUMED' in frg

    def test_hicbir_varsayilan_cumlesi_basilmaz(self):
        t = self._render()['text']
        assert 'declared no defaults' not in t, (
            'uç kendi ASSUMED beyanını yayımlarken panel "her girdi bu '
            'formdan geldi" diyemez')

    def test_beyani_yapan_alanlar_makine_yoluyla_ekranda(self):
        h = self._render()['html']
        assert 'data-safety-defaults="assumed"' in h
        for alan in ('radiating_area_basis', 'case_mass_basis'):
            assert alan in h, alan

    def test_beyan_yokken_mutlak_cumle_KORUNUR(self):
        """Aşırı düzeltme koruması: ASSUMED beyanı yoksa cümle basılmalı."""
        b = json.loads(json.dumps(govde('safety')))
        b['safety_analysis'] = {'risk_assessment':
                                b['safety_analysis'].get('risk_assessment', {})}
        r = kostur(panelId='safety', dataInline=b,
                   panelFiles=['hrma/static/js/panels/safety_panel.js'])
        assert 'declared no defaults' in r['text']


# ======================================================================
# P11B4-16 — panelin kazanmadığı nedensellik iddiası
# ======================================================================
@node_gerekli
class TestBelirsizlikKaymaKunyesi:

    def _render(self, veri=None):
        kw = {'panelId': 'uncertainty',
              'panelFiles': ['hrma/static/js/panels/uncertainty_panel.js']}
        if veri is None:
            kw['dataFile'] = str(YUK / 'uncertainty.json')
        else:
            kw['dataInline'] = veri
        r = kostur(**kw)
        assert r['text'].strip(), 'BOŞ render'
        return r

    def test_uc_kaymanin_nedenini_pinlenmis_parametreye_bagliyor(self):
        b = govde('uncertainty')
        not_ = b['consistency_note']
        assert 'NOT nonlinearity' in not_
        kayma = b['mean_shift_percent']['c_star']
        aciklanan = float(re.search(r'\(([-+]?\d+\.\d+)%\)', not_).group(1))
        # Kaymanın neredeyse tamamı pinlenmiş parametreden: fark < 0,1 puan.
        assert abs(abs(kayma) - abs(aciklanan)) < 0.1, (kayma, aciklanan)

    def test_dogrusalsizlik_iddiasi_basilmaz(self):
        assert 'nonlinear response' not in self._render()['text']

    def test_ucun_kendi_notu_KENDI_paragrafinda_ekranda(self):
        h = self._render()['html']
        assert 'data-uq-consistency-note="1"' in h
        i = h.find('data-uq-consistency-note="1"')
        assert 'pinned to the deterministic path' in h[i:i + 1200], (
            'not yalnız bir `title` niteliğinde durursa "ekranda" sayılmaz')

    def test_not_yokken_eski_cumle_KORUNUR(self):
        """Aşırı düzeltme koruması: eski uç (not yok) → eski davranış."""
        b = json.loads(json.dumps(govde('uncertainty')))
        b.pop('consistency_note', None)
        assert 'nonlinear response' in self._render(b)['text']


# ======================================================================
# P11B4-20 — hüküm rengi kazanılmamış sayının üstünde duruyordu
# ======================================================================
@node_gerekli
class TestSuKocuYoneticiTepe:

    EV = ("var root = document.createElement('div');"
          " window.FeedPanel._renderWaterHammer(body, root);"
          " var h=''; (root.children||[]).forEach(function(c){h+=c.innerHTML;});"
          " return {html: h};")

    def _html(self, ad='feed_wh_unsafe'):
        r = kostur(panelId='_yok', dataFile=kanit_gerekli(str(YUK / (ad + '.json'))),
                   panelFiles=['hrma/static/js/panels/feed_panel.js'],
                   evalFn=self.EV)
        h = r['evaled']['html']
        assert duz(h), 'BOŞ render — ölçüm vakuus olurdu'
        return h

    def test_uc_bu_kosumda_iki_ayri_tepe_yayimliyor(self):
        w = govde('feed_wh_unsafe')['water_hammer']
        assert w['status'] == 'UNSAFE'
        assert w['design_peak_pressure_bar'] > w['peak_pressure_bar']
        # Ekrandaki eski sayı boru sınırının ALTINDA: çelişkinin ön koşulu.
        assert w['peak_pressure_bar'] < w['pipe']['mawp_bar']

    def test_yonetici_tepe_alan_adiyla_ekranda(self):
        h = self._html()
        w = govde('feed_wh_unsafe')['water_hammer']
        assert 'design_peak_pressure_bar' in h
        # Değeriyle birlikte basılıyor mu (yalnız ad değil)?
        assert re.search(r'411\.1', duz(h)), duz(h)[:400]
        assert 'column_separation_peak_factor' in h
        assert str(w['column_separation_peak_factor'])[:3] in duz(h)

    def test_hukum_rengi_kazanilmamis_karttan_alindi(self):
        h = self._html()
        i = h.find('PEAK PRESSURE')
        assert i >= 0
        j = h.find('</div>', i)
        assert renk_ileri(h, j) == 'sonuk', (
            'Joukowsky tepesi hükmü kazanmadı; kırmızı kalamaz')

    def test_yonetici_kart_hukum_rengini_tasiyor(self):
        h = self._html()
        i = h.find('design_peak_pressure_bar')
        j = h.find('</div>', i)
        assert renk_ileri(h, j) == 'kirmizi'

    def test_guvenli_kosuda_yesil_KORUNUR(self):
        """Aşırı düzeltme koruması: SAFE koşuda yönetici kart yeşil kalır."""
        w = govde('feed_wh_safe')['water_hammer']
        assert w['status'] == 'SAFE'
        h = self._html('feed_wh_safe')
        i = h.find('design_peak_pressure_bar')
        if i >= 0:
            assert renk_ileri(h, h.find('</div>', i)) == 'yesil'


# ======================================================================
# P11B4-31 — analizi süren cidar
# ======================================================================
@node_gerekli
class TestKullanilanCidar:

    def _text(self):
        r = kostur(panelId='structural',
                   dataFile=kanit_gerekli(str(YUK / 'structural_5mm.json')),
                   panelFiles=['hrma/static/js/panels/structural_panel.js'])
        assert r['text'].strip(), 'BOŞ render'
        return r['text']

    def test_uc_kullanilan_cidari_yayimliyor(self):
        ca = govde('structural_5mm')['structural_analysis']['chamber_analysis']
        assert ca['wall_thickness_used_mm'] == 5.0
        assert ca['wall_thickness_source'] == 'user_supplied'
        # Ekrandaki iki öneri, kullanılan cidardan FARKLI: kusurun ön koşulu.
        assert ca['minimum_thickness'] < 5.0
        assert ca['recommended_thickness'] < 5.0

    def test_kullanilan_cidar_bolumun_icinde_degeriyle_basiliyor(self):
        t = self._text()
        i = t.find('Wall Thickness')
        assert i >= 0
        blok = t[i:i + 300]
        assert re.search(r'wall_thickness_used_mm\s+5\.00 mm', blok), blok
        assert 'user_supplied' in blok

    def test_oneri_satirlari_hala_basiliyor(self):
        """Aşırı düzeltme koruması: öneriler kaybolmadı."""
        blok = self._text()
        assert 'Minimum required' in blok and 'Recommended' in blok


# ======================================================================
# P11B5-04 — Isp tip-duyarlı okunur
# ======================================================================
@node_gerekli
class TestKarsilastirmaIsp:

    EV = ("window.currentResults = body;"
          " return {metrics: window.ComparativePanel._currentMetrics()};")

    def _metrik(self, ad):
        r = kostur(panelId='_yok', dataFile=kanit_gerekli(str(YUK / (ad + '.json'))),
                   panelFiles=['hrma/static/js/panels/comparative_panel.js'],
                   evalFn=self.EV)
        return r['evaled']['metrics']

    def test_kati_yanitta_isp_anahtari_gercekten_yok(self):
        b = govde('solid_pc40')
        assert b.get('isp') is None, 'ön koşul düştü: katıda `isp` var'
        assert isinstance(b['isp_sea_level'], float)

    def test_isp_metrige_giriyor_ve_uctan_okunuyor(self):
        for ad in ('solid_pc40', 'solid_pc70'):
            m = self._metrik(ad)
            b = govde(ad)
            assert 'isp' in m, ad
            # Sayı UYDURULMAZ: ucun kendi alanının birebir kopyası.
            assert m['isp'] == b['isp_sea_level'], ad
            assert m['isp_basis'] in ('isp_sea_level', 'specific_impulse')

    def test_daha_yuksek_isp_gercekten_daha_yuksek_okunuyor(self):
        a = self._metrik('solid_pc40')['isp']
        b = self._metrik('solid_pc70')['isp']
        assert b > a, (a, b)

    def test_vakum_ispsi_asla_okunmaz(self):
        """Tanım karışması koruması: karşılaştırma deniz seviyesi Isp'sidir."""
        b = govde('solid_pc40')
        m = self._metrik('solid_pc40')
        assert m['isp'] != b.get('isp_vacuum')


# ======================================================================
# P11B5-05 / -06 — termal künyeler
# ======================================================================
@node_gerekli
class TestTermalKunyeler:

    def _render(self, mat):
        r = kostur(panelId='thermal',
                   dataFile=kanit_gerekli(str(YUK / ('thermal_' + mat + '.json'))),
                   panelFiles=['hrma/static/js/panels/thermal_panel.js'])
        assert r['text'].strip(), 'BOŞ render'
        return r

    def test_uc_kutleyi_secilen_malzemenin_cpsiyle_hesapliyor(self):
        c = (govde('thermal_graphite')['thermal_analysis']['cooling_analysis'])
        assert c['heat_sink_specific_heat_source'] == 'material_record'
        assert c['heat_sink_delta_T_K'] > 200.0 * 10, (
            'ön koşul düştü: ΔT 200 K yakınına indi')

    def test_yanlis_etiket_ve_ipucu_basilmaz(self):
        r = self._render('graphite')
        assert 'steel equiv' not in r['text']
        assert '200 K temperature rise' not in r['html']

    def test_ucun_kendi_tabani_gorunur_basiliyor(self):
        c = (govde('thermal_graphite')['thermal_analysis']['cooling_analysis'])
        t = self._render('graphite')['text']
        assert 'heat_sink_mass' in t
        assert ('%.2f' % c['heat_sink_delta_T_K']) in t
        assert str(c['heat_sink_specific_heat_source']) in t
        assert 'heat_sink_delta_T_basis' in t

    def test_uc_jenerik_konturu_beyan_ediyor(self):
        g = (govde('thermal_steel')['thermal_analysis']['gas_side_analysis'])
        wb = g['wetted_integral_contour_basis']
        assert 'NOT this motor' in wb['exit_diameter_source']
        assert wb['generic_defaults_used']

    def test_islak_alan_ve_turevleri_beyani_tasiyor(self):
        r = self._render('steel')
        assert 'data-thermal-generic-contour' in r['html']
        # Türeyen satırlar da GÖRÜNÜR im taşır (title metni sayılmaz).
        assert r['html'].count('data-thermal-derived-generic') >= 2
        assert r['text'].count('generic_defaults_used') >= 2

    def test_beyan_yokken_hicbir_sey_iddia_edilmez(self):
        """Fail-closed koruması: beyan yoksa im de basılmaz."""
        b = json.loads(json.dumps(govde('thermal_steel')))
        b['thermal_analysis']['gas_side_analysis'].pop(
            'wetted_integral_contour_basis', None)
        r = kostur(panelId='thermal', dataInline=b,
                   panelFiles=['hrma/static/js/panels/thermal_panel.js'])
        assert 'data-thermal-generic-contour' not in r['html']
        assert 'data-thermal-derived-generic' not in r['html']


# ======================================================================
# P11B5-07 — çizim kimliği
# ======================================================================
@node_gerekli
class TestEnjektorSemasiKimligi:

    EV = ("var g = {n_orifices:8, orifice_d_mm:2.4578, n_elements:4,"
          " half_angle_deg:30};"
          " var out = {};"
          " ['impinging_doublet','impinging_triplet','like_impinging',"
          "  'showerhead'].forEach(function(t){"
          "    out[t] = window.InjectorSchematics.svg(t, g); });"
          " return out;")

    def _svg(self):
        r = kostur(panelId='_yok', dataInline={},
                   panelFiles=['hrma/static/js/injector_schematics.js'],
                   evalFn=self.EV)
        s = r['evaled']
        for k, v in s.items():
            assert isinstance(v, str) and v.strip(), k
        return s

    def test_uc_secim_artik_bayt_ozdes_degil(self):
        s = self._svg()
        uc = {s['impinging_doublet'], s['impinging_triplet'],
              s['like_impinging']}
        assert len(uc) == 3, 'seçimler hâlâ ayırt edilemiyor'

    def test_triplet_ucuncu_jeti_gercekten_ciziyor(self):
        s = self._svg()
        # Üçüncü jet aksan renginde çizilir; doublet'te o çizgi YOKTUR.
        assert 'injector_type: impinging_triplet' in s['impinging_triplet']
        assert len(s['impinging_triplet']) > len(s['impinging_doublet'])

    def test_kanonik_olmayan_secimde_olumlu_kimlik_iddia_edilmez(self):
        s = self._svg()
        for t in ('impinging_triplet', 'like_impinging'):
            assert 'Impinging doublet' not in s[t], t
            assert 'injector_type: ' + t in s[t], t

    def test_kanonik_secimde_aile_basligi_KORUNUR(self):
        """Aşırı düzeltme koruması: doublet ve showerhead adını kaybetmez."""
        s = self._svg()
        assert 'Impinging doublet' in s['impinging_doublet']
        assert 'Showerhead' in s['showerhead']


# ======================================================================
# P11B5-08 — negatif sönüm
# ======================================================================
@node_gerekli
class TestBlowdownSonumIsareti:

    EV = ("var src = fs.readFileSync(require('path').join(process.cwd(),"
          " 'hrma/static/js/blowdown_panel.js'),'utf8');"
          " src = src.replace('window.BlowdownPanel = {',"
          "   'window.__BD = { renderBadges: renderBadges,"
          " buildViewModel: buildViewModel }; window.BlowdownPanel = {');"
          " (0, eval)(src);"
          " var vm = window.__BD.buildViewModel(body.motor);"
          " var el = document.createElement('div');"
          " window.__BD.renderBadges(el, vm);"
          " return {mode: vm.mode, decay: vm.thrust_decay_fraction,"
          "         html: el.innerHTML};")

    def _rozet(self, ad):
        r = kostur(panelId='_yok', dataFile=kanit_gerekli(str(YUK / (ad + '.json'))),
                   panelFiles=[], evalFn=self.EV)
        e = r['evaled']
        assert e['mode'] == 'modelled', (ad, e['mode'])
        assert e['html'].strip(), 'BOŞ rozet — ölçüm vakuus olurdu'
        return e

    def test_uc_bu_kosumlarda_gercekten_negatif_uretiyor(self):
        for ad in ('calc_pc35', 'calc_pc40'):
            bd = govde(ad)['motor']['tank_blowdown']
            assert bd['thrust_decay_fraction'] < 0, ad
            th = bd['thrust_N']
            assert th[-1] > th[0], (ad, th[0], th[-1])

    def test_negatif_deger_notr_renkte_basilmaz(self):
        for ad in ('calc_pc35', 'calc_pc40'):
            e = self._rozet(ad)
            i = e['html'].find('thrust_decay_fraction')
            assert i >= 0, ad + ': makine alan adı basılmadı'
            assert renk_geri(e['html'], i) == 'turuncu', ad

    def test_yanlis_ad_negatif_degerde_kullanilmaz(self):
        for ad in ('calc_pc35', 'calc_pc40'):
            e = self._rozet(ad)
            # "DECAY %-32" ifadesi artık basılmaz.
            assert 'THRUST DECAY -' not in duz(e['html']), ad

    def test_negatifte_seriden_olculen_itki_araligi_basiliyor(self):
        e = self._rozet('calc_pc40')
        th = govde('calc_pc40')['motor']['tank_blowdown']['thrust_N']
        t = duz(e['html'])
        assert ('%.1f' % th[0]) in t and ('%.1f' % th[-1]) in t, t[:300]

    def test_pozitif_sonum_rozeti_KORUNUR(self):
        """Aşırı düzeltme koruması: gerçek sönüm eski gibi basılır."""
        e = self._rozet('calc_pc20')
        assert e['decay'] > 0
        t = duz(e['html'])
        assert 'THRUST DECAY 25%' in t, t[:300]
        assert renk_geri(e['html'], e['html'].find('THRUST DECAY')) == 'mavi'


# ======================================================================
# P11B5-09 — büyüklük kapısı
# ======================================================================
@node_gerekli
class TestSixDofBuyuklukKapisi:

    C_LIGHT = 299792458.0
    EV = ("var src = fs.readFileSync(require('path').join(process.cwd(),"
          " 'hrma/static/js/sixdof_panel.js'),'utf8');"
          " src = src.replace('window.SixDofPanel = {',"
          "   'window.__SD = { render: render }; window.SixDofPanel = {');"
          " (0, eval)(src);"
          " window.__SD.render(body, false);"
          " var b = document.getElementById('sd_badges');"
          " var lay = (window.__plots[0]||{}).layout || {};"
          " return {badges: b ? b.innerHTML : null, title: lay.title};")

    def _ekran(self, ad):
        r = kostur(panelId='_yok', dataFile=kanit_gerekli(str(YUK / (ad + '.json'))),
                   panelFiles=[], evalFn=self.EV)
        e = r['evaled']
        assert e['badges'] and e['badges'].strip(), 'BOŞ rozet şeridi'
        return e

    def test_uc_bu_kosumda_gercekten_isik_hizini_asiyor(self):
        s = govde('sixdof_absurd')['summary']
        assert s['max_speed'] > self.C_LIGHT, s['max_speed']
        assert s['apogee'] is None and s['end_reason'] == 'time_limit'

    def test_hiz_ekranda_ve_kirmizi(self):
        e = self._ekran('sixdof_absurd')
        s = govde('sixdof_absurd')['summary']
        i = e['badges'].find('max_speed')
        assert i >= 0, 'max_speed hâlâ ekranda değil'
        assert ('%.1f' % s['max_speed']) in duz(e['badges'])
        assert renk_geri(e['badges'], i) == 'kirmizi'

    def test_mach_rozeti_notr_kalmaz(self):
        e = self._ekran('sixdof_absurd')
        i = e['badges'].find('MAX MACH')
        assert i >= 0
        assert renk_geri(e['badges'], i) == 'kirmizi'

    def test_apoje_yokken_grafik_apojeye_kadar_demez(self):
        e = self._ekran('sixdof_absurd')
        assert 'apogee' not in str(e['title']).lower(), e['title']
        assert 'TIME_LIMIT' in str(e['title'])

    def test_normal_kosuda_hicbiri_kirmizi_degil(self):
        """Aşırı düzeltme koruması: fiziksel koşu eskisi gibi görünür."""
        e = self._ekran('sixdof_normal')
        s = govde('sixdof_normal')['summary']
        assert s['max_speed'] < self.C_LIGHT
        assert renk_geri(e['badges'], e['badges'].find('MAX MACH')) == 'mavi'
        assert renk_geri(e['badges'], e['badges'].find('max_speed')) == 'mavi'
        assert 'launch to apogee' in str(e['title'])


# ======================================================================
# P11B5-03 — ÇÜRÜTME KİLİDİ (başlık bu HEAD'de yanlış)
# ======================================================================
@node_gerekli
class TestEnjektorUyariKanaliCanli:
    """Defter "uyarıların 0'ı ekranda" diyor; ÖLÇÜLDÜ: bu HEAD'de yanlış.

    Onarım taban `e88d096`den ÖNCE inmiş (panel `design.warnings` /
    `design.assumptions` okuyor). Bekçi çürütmeyi KİLİTLER.
    """

    EV = ("return {html: window.InjectorPanel._renderHtml(body.design)};")

    def _html(self):
        r = kostur(panelId='_yok', dataFile=kanit_gerekli(str(YUK / 'injector_swirl.json')),
                   panelFiles=['hrma/static/js/injector_panel.js'],
                   evalFn=self.EV)
        h = r['evaled']['html']
        assert h.strip(), 'BOŞ render'
        return h

    def test_uc_uyari_ve_varsayim_uretiyor(self):
        d = govde('injector_swirl')['design']
        assert len(d['warnings']) == 2 and len(d['assumptions']) == 5
        assert d.get('warnings_tr') is None, (
            'uç `warnings_tr` döndürmeye başlamış — kalem yeniden ölçülmeli')

    def test_uyari_ve_varsayim_bloklari_ekranda(self):
        h = self._html()
        assert 'data-inj-warnings' in h and 'data-inj-assumptions' in h

    def test_imalat_fizibilite_uyarisi_dusmuyor(self):
        h = self._html()
        assert 'infeasible' in h or 'orifice_plan' in h
