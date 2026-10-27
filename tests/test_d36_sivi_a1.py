# -*- coding: utf-8 -*-
"""ÖH D36 · kulvar onemli2-sivi · a1 — sıvı sayfası bekçileri (23 Eylül 2026).

Kalemler ve ölçülen kusurlar (kanıt: docs/scofield/raw/OH/D36/onemli2-sivi/a1/):

- LU-1 (Cowork, Berke onaylı, ÖNEMLİ): örnek proje süre GİRİLMEDEN
  hesaplandığında arayüz 400 s ön dolgusunu gönderiyor, motor bunu
  "user input (max burn duration)" diye künyeliyordu; alan boş gönderilince
  motor sessizce 300 s varsayıp itici kütlesi (2756 kg), tank kartı
  (3170 kg yüklü) ve 3515 baytlık .eng üretiyordu. Onarım: fail-closed yayım
  kapısı (``burn_time_source = 'not_supplied'``), varsayılan yalnız öğretici
  kipte ve ``defaults_applied`` beyanıyla.
- LU-2: .eng düğmesi gövdeyi elle kuruyor (form süresinden F x t, mdot x t)
  ve tank kartını göndermiyordu -> 400 s ile bile 422. Ret metni durum
  satırına İngilizce ham kalıpla iniyordu.
- L-6: örnek yüklenince boş kalan alanlarda "isteğe bağlı" işareti yoktu.
- OH-P-19: aynı besleme hattı kaydı iki adresten okunup iki kez basılıyordu.
- OH-GT devirleri: chug hükmü ham enum, gimbal eksik alanları ham anahtar.
- TR ondalık: viskozite üstel gösterimi ve hâl künyesindeki sıcaklık noktalı.

Kaynak okuyan bekçiler dosyayı DOSYADAN okur (inspect.getsource yok); JS
yardımcıları node altında GERÇEKTEN koşturulur (betik stdin ile verilir).
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
LIQUID = KOK / 'hrma' / 'templates' / 'liquid.html'
I18N_COMMON = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'
I18N_PAGES = KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
REJECT_BODY = KOK / 'hrma' / 'static' / 'js' / 'reject_body.js'
ENGINE = KOK / 'hrma' / 'engines' / 'liquid_rocket_engine.py'
APP = KOK / 'hrma' / 'app.py'
ORNEK = KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node yok')

from hrma.engines.liquid_rocket_engine import (  # noqa: E402
    BURN_TIME_DEFAULT_S,
    BURN_TIME_SOURCE_NOT_SUPPLIED,
    BURN_TIME_SOURCE_TUTORIAL,
    BURN_TIME_SOURCE_USER,
)

#: Kanıt paketindeki ölçümün girdi süresi (eski arayüz ön dolgusu); bir
#: kullanıcı girdisi ÖRNEĞİDİR, varsayılan değildir.
KULLANICI_SURESI_S = 400.0


def _html() -> str:
    return LIQUID.read_text(encoding='utf-8')


def _ornek_alanlar() -> dict:
    return json.loads(ORNEK.read_text(encoding='utf-8'))['inputs']['fields']


def _js_blok(kaynak: str, bas: str) -> str:
    """``bas`` ile başlayan ilk fonksiyon/sabit bloğunu parantez dengesiyle al."""
    i = kaynak.index(bas)
    ac = '[' if bas.lstrip().startswith('const ') and '= [' in kaynak[i:i + 200] else '{'
    kap = ']' if ac == '[' else '}'
    j = kaynak.index(ac, i)
    derinlik = 0
    for k in range(j, len(kaynak)):
        if kaynak[k] == ac:
            derinlik += 1
        elif kaynak[k] == kap:
            derinlik -= 1
            if derinlik == 0:
                return kaynak[i:k + 1] + (';' if ac == '[' else '')
    raise AssertionError('blok kapanmadı: %r' % bas)


def _node(betik: str) -> dict:
    out = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


def _sozluk_anahtarlari(yol: pathlib.Path) -> tuple[set, set]:
    """i18n dosyasında EN ve TR bloklarındaki anahtar kümeleri (kaba ayrım).

    Dosyalar ``en: {`` ... ``tr: {`` sırasıyla iki blok taşır; anahtar
    satırları ``'anahtar': 'metin',`` biçimindedir.
    """
    metin = yol.read_text(encoding='utf-8')
    tr_bas = re.search(r"\n\s*tr\s*:\s*\{", metin)
    assert tr_bas, 'TR bloğu bulunamadı: %s' % yol.name
    en_kisim, tr_kisim = metin[:tr_bas.start()], metin[tr_bas.start():]
    desen = re.compile(r"^\s*'([A-Za-z0-9_.]+)'\s*:", re.M)
    return set(desen.findall(en_kisim)), set(desen.findall(tr_kisim))


def _deger(yol: pathlib.Path, anahtar: str) -> list[str]:
    metin = yol.read_text(encoding='utf-8')
    return re.findall(r"'%s'\s*:\s*'((?:[^'\\]|\\.)*)'" % re.escape(anahtar), metin)


# ---------------------------------------------------------------------------
# Uç ölçümleri — modül başına BİR koşu (çözüm pahalı)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def uc():
    from hrma.app import app
    app.config['TESTING'] = True
    alanlar = _ornek_alanlar()
    assert 'max_burn_duration' not in alanlar, 'örnek proje süre taşımamalı'
    with app.test_client() as c:
        sonuc = {}
        for ad, govde in (
                ('bos', dict(alanlar)),
                ('kullanici', dict(alanlar, max_burn_duration=KULLANICI_SURESI_S)),
                ('ogretici', dict(alanlar, use_tutorial_defaults=True)),
                ('ogretici_false', dict(alanlar, use_tutorial_defaults='false'))):
            r = c.post('/calculate_liquid', json=govde)
            assert r.status_code == 200, (ad, r.get_json())
            sonuc[ad] = r.get_json()
        r = c.post('/api/export-eng', json={
            'motor_data': dict(sonuc['bos'], motor_name='HRMA_LIQUID')})
        sonuc['eng_bos'] = (r.status_code, r.get_json())
        r = c.post('/api/export-eng', json={
            'motor_data': dict(sonuc['kullanici'], motor_name='HRMA_LIQUID')})
        sonuc['eng_kullanici'] = (r.status_code, r.get_json())
        r = c.post('/calculate_liquid', json={})
        sonuc['bos_govde'] = (r.status_code, r.get_json())
        yield sonuc


# ---------------------------------------------------------------------------
# LU-1 · yanma süresi yayım kapısı
# ---------------------------------------------------------------------------
class TestLU1YanmaSuresi:
    def test_sure_yoksa_sureye_bagli_alan_yayimlanmaz(self, uc):
        d = uc['bos']
        assert 'burn_time' not in d
        assert d['burn_time_source'] == BURN_TIME_SOURCE_NOT_SUPPLIED
        assert d.get('burn_time_reason')
        assert 'total_impulse' not in d
        masses = d['design_summary']['masses']
        assert 'propellant_mass_kg' not in masses
        assert 'burn_time_s' not in masses
        assert masses['burn_time_source'] == BURN_TIME_SOURCE_NOT_SUPPLIED

    def test_tank_karti_ve_besleme_hacmi_adiyla_yok(self, uc):
        d = uc['bos']
        assert d['propellant_tanks']['status'] == 'not_modelled'
        assert d['propellant_tanks']['reason']
        for tank in ('oxidizer_tank', 'fuel_tank'):
            kart = d['feed_system']['tanks'][tank]
            assert kart['volume'] is None
            assert 'not supplied' in kart['volume_source']

    def test_eng_tasarim_yanitinda_adiyla_reddedilir(self, uc):
        orx = uc['bos']['openrocket']
        assert orx['eng_file'] is None
        assert orx['eng_error']['missing_fields'][0] == 'burn_time'
        assert 'not_supplied' in orx['eng_error']['field_reasons']['burn_time']

    def test_kullanici_suresi_kunyesiyle(self, uc):
        d = uc['kullanici']
        assert d['burn_time'] == KULLANICI_SURESI_S
        assert d['burn_time_source'] == BURN_TIME_SOURCE_USER
        assert d['design_summary']['masses']['propellant_mass_kg'] > 0
        assert d['openrocket']['eng_error'] is None

    def test_ogretici_kipte_beyanli_varsayilan(self, uc):
        d = uc['ogretici']
        assert d['burn_time'] == BURN_TIME_DEFAULT_S
        assert d['burn_time_source'] == BURN_TIME_SOURCE_TUTORIAL
        beyan = [x for x in d.get('defaults_applied') or []
                 if x.get('field') == 'max_burn_duration']
        assert len(beyan) == 1
        assert beyan[0]['value'] == BURN_TIME_DEFAULT_S
        assert beyan[0]['reason'] == 'tutorial_default'

    def test_false_dizesi_ogretici_kipi_acmaz(self, uc):
        d = uc['ogretici_false']
        assert 'burn_time' not in d
        assert d['burn_time_source'] == BURN_TIME_SOURCE_NOT_SUPPLIED

    def test_motorda_sessiz_varsayim_dali_yok(self):
        """``_burn_time`` gövdesi: varsayılan yalnız öğretici bayrağıyla."""
        kaynak = ENGINE.read_text(encoding='utf-8')
        m = re.search(r'def _burn_time\(self\):(.*?)\n    def ', kaynak, re.S)
        assert m, '_burn_time bulunamadı'
        govde = re.sub(r'""".*?"""', '', m.group(1), count=1, flags=re.S)
        assert 'assumed' not in govde
        assert re.search(r"if getattr\(self, 'tutorial_defaults', False\):\s*\n\s*"
                         r"return BURN_TIME_DEFAULT_S, BURN_TIME_SOURCE_TUTORIAL", govde)
        assert 'return None, BURN_TIME_SOURCE_NOT_SUPPLIED' in govde

    def test_arayuz_on_dolgu_ve_yedek_yok(self):
        html = _html()
        m = re.search(r'<input[^>]*id="max_burn_duration"[^>]*>', html)
        assert m, 'max_burn_duration alanı yok'
        assert 'value=' not in m.group(0), 'ön dolgu geri geldi: %s' % m.group(0)
        assert not re.search(r"getElementById\('max_burn_duration'\)\.value\)\s*\|\|\s*\d", html)
        assert "max_burn_duration: liqOptNum('max_burn_duration')" in html
        assert re.search(r"getElementById\('max_burn_duration'\)\.value = '';", html)
        assert not re.search(r"getElementById\('max_burn_duration'\)\.value = '\d", html)

    def test_manset_satiri_sure_yoksa_beyan_basar(self):
        html = _html()
        i = html.index("T('liq.ui.total_impulse', 'Total Impulse')")
        pencere = html[i - 400:i + 1600]
        assert "typeof results.burn_time === 'number'" in pencere
        assert "results.burn_time_source === 'not_supplied'" in pencere
        assert "T('liq.js.burn_time_not_supplied'" in pencere

    def test_kapsam_notu_yalnizca_disa_aktarim_demez(self):
        html = _html()
        assert 'markInputScopeNotes();' in html
        assert 'markExportOnlyInputs();' not in html
        blok = _js_blok(html, 'const INPUT_SCOPE_NOTES')
        assert 'max_burn_duration' in blok
        assert 'liq.msg.burn_duration_scope_note' in blok


# ---------------------------------------------------------------------------
# LU-2 · .eng düğmesi
# ---------------------------------------------------------------------------
_ENG_HARNESS = r"""
// Betik düzeyi `const window` reject_body.js'in `typeof window` denetimini
// TDZ'ye düşürür (ortak global sözcüksel kayıt); `var` kullanılır.
var HRMAReject = require(__REJECT__);
var window = { currentResults: __CR__, HRMAReject: HRMAReject };
const nodes = { liquidExportStatus: { textContent: '' } };
const document = { getElementById: function (id) { return nodes[id] || null; },
                   createElement: function () { return { click: function () {} }; },
                   body: { appendChild: function () {}, removeChild: function () {} } };
const bildirim = [];
function T(k, f) { return f; }
function TF(k, p, f) { return String(f).replace(/\{(\w+)\}/g, function (a, n) { return (p && n in p) ? String(p[n]) : a; }); }
function numTxt(v, d) { return (typeof v === 'number' && isFinite(v)) ? v.toFixed(d) : String(v); }
function showWarning(m) { bildirim.push(['warn', m]); }
function showInfo(m) { bildirim.push(['info', m]); }
function showError(m) { bildirim.push(['error', m]); }
function showSuccess(m) { bildirim.push(['ok', m]); }
function _triggerLiquidDownload() { bildirim.push(['download', 1]); }
const gonderilen = [];
global.fetch = function (url, opts) {
    gonderilen.push({ url: url, body: JSON.parse(opts.body) });
    const r = __YANIT__;
    return Promise.resolve({ status: r.status, ok: r.status >= 200 && r.status < 300,
                             json: function () { return Promise.resolve(r.body); } });
};
__BLOK__
(async function () {
    await downloadLiquidEng();
    process.stdout.write(JSON.stringify({ durum: nodes.liquidExportStatus.textContent,
        bildirim: bildirim, gonderilen: gonderilen }));
})();
"""


def _eng_dugmesi_kos(cr: dict, yanit: dict, mutasyon=None) -> dict:
    html = _html()
    blok = '\n'.join([
        _js_blok(html, 'function _liquidExportStatus(text)'),
        _js_blok(html, 'function _liquidMotorName()'),
        _js_blok(html, 'function _ihracRetMetni(govde, durum)'),
        _js_blok(html, 'async function downloadLiquidEng()'),
    ])
    if mutasyon:
        assert mutasyon[0] in blok
        blok = blok.replace(mutasyon[0], mutasyon[1], 1)
    betik = (_ENG_HARNESS.replace('__REJECT__', json.dumps(str(REJECT_BODY)))
             .replace('__CR__', json.dumps(cr)).replace('__YANIT__', json.dumps(yanit))
             .replace('__BLOK__', blok))
    return _node(betik)


class TestLU2EngDugmesi:
    def test_uc_sure_yoksa_422_ve_kok_alan_adiyla(self, uc):
        durum, govde = uc['eng_bos']
        assert durum == 422
        assert govde['missing_fields'][0] == 'burn_time'
        assert 'not_supplied' in govde['message']

    def test_uc_tam_sonucla_kullanici_suresinde_200(self, uc):
        durum, govde = uc['eng_kullanici']
        assert durum == 200 and govde['status'] == 'success' and govde['content']

    @needs_node
    def test_dugme_tam_sonucu_gonderir_sayi_turetmez(self, uc):
        cr = uc['kullanici']
        kos = _eng_dugmesi_kos(cr, {'status': 200, 'body': {
            'status': 'success', 'content': 'x', 'filename': 'a.eng'}})
        assert len(kos['gonderilen']) == 1
        md = kos['gonderilen'][0]['body']['motor_data']
        # Çözücünün tank kartı gövdede (eski düğme göndermiyordu -> 422).
        assert md['propellant_tanks'] == cr['propellant_tanks']
        assert md['burn_time'] == cr['burn_time']
        assert md['motor_name'] == 'HRMA_LIQUID'
        assert 'total_impulse' not in md and 'propellant_mass_total' not in md
        assert ['download', 1] in kos['bildirim']

    @needs_node
    def test_ret_govdesi_durum_satirina_adiyla_iner(self, uc):
        durum, govde = uc['eng_bos']
        kos = _eng_dugmesi_kos(uc['bos'], {'status': durum, 'body': govde})
        assert kos['durum'].startswith('.eng export failed: ')
        assert 'burn_time' in kos['durum'], kos['durum']
        assert any(t == 'error' and 'burn_time' in m for t, m in kos['bildirim'])
        assert ['download', 1] not in kos['bildirim']

    @needs_node
    def test_tasarim_yanitindaki_eng_hatasi_panele_ve_satira(self, uc):
        html = _html()
        blok = '\n'.join([
            _js_blok(html, 'const LIQUID_DEEP_WARNING_PATHS'),
            _js_blok(html, 'function liquidDeepWarnings(results)'),
            _js_blok(html, 'function _liquidExportStatus(text)'),
            _js_blok(html, 'function liquidEngGateStatus(results)'),
        ])
        betik = ("var window = { HRMAReject: require(%s) };\n"
                 "const nodes = { liquidExportStatus: { textContent: '' } };\n"
                 "const document = { getElementById: function (i) { return nodes[i] || null; } };\n"
                 "function T(k, f) { return f; }\n"
                 "function TF(k, p, f) { return String(f).replace(/\\{(\\w+)\\}/g, function (a, n) { return (p && n in p) ? String(p[n]) : a; }); }\n"
                 "function numTxt(v) { return String(v); }\n"
                 "%s\nconst r = %s;\nconst w = liquidDeepWarnings(r);\nliquidEngGateStatus(r);\n"
                 "process.stdout.write(JSON.stringify({ w: w, durum: nodes.liquidExportStatus.textContent }));\n"
                 % (json.dumps(str(REJECT_BODY)), blok, json.dumps(uc['bos'])))
        kos = _node(betik)
        kayit = [w for w in kos['w'] if isinstance(w, dict)
                 and w.get('code') == 'panelwarn.liquid.eng_not_generated']
        assert len(kayit) == 1
        assert kayit[0]['params']['fields'].startswith('burn_time')
        assert kos['durum'].startswith('.eng not generated: ')


# ---------------------------------------------------------------------------
# L-6 · isteğe bağlı işareti
# ---------------------------------------------------------------------------
def _etiket_govdesi(html: str, alan: str) -> str:
    m = re.search(r'<label for="%s">(.*?)</label>' % re.escape(alan), html, re.S)
    assert m, 'etiket yok: %s' % alan
    return re.sub(r'<div class="tooltip">.*', '', m.group(1), flags=re.S)


def _bos_varsayilanli_alanlar(html: str) -> list[str]:
    etiketli = set(re.findall(r'<label for="([^"]+)"', html))
    bos = []
    for m in re.finditer(r'<input\b[^>]*\bid="([^"]+)"[^>]*>', html):
        etiket = m.group(0)
        if m.group(1) not in etiketli:
            continue
        if not re.search(r'type="(number|text)"', etiket):
            continue
        v = re.search(r'\bvalue="([^"]*)"', etiket)
        if v is None or v.group(1).strip() == '':
            bos.append(m.group(1))
    for m in re.finditer(r'<select\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</select>', html, re.S):
        if m.group(1) not in etiketli:
            continue
        secenekler = re.findall(r'<option\b([^>]*)>', m.group(2))
        secili = [s for s in secenekler if 'selected' in s] or secenekler[:1]
        v = re.search(r'value="([^"]*)"', secili[0]) if secili else None
        if v is not None and v.group(1) == '':
            bos.append(m.group(1))
    return bos


class TestL6IstegeBagli:
    def test_zorunlu_kume_uctan_olculur_ve_isaretsizdir(self, uc):
        durum, govde = uc['bos_govde']
        assert durum == 422
        zorunlu = set(govde['missing_fields'])
        assert zorunlu == {'thrust', 'chamber_pressure', 'mixture_ratio',
                           'fuel_type', 'oxidizer_type'}
        html = _html()
        for alan in zorunlu:
            assert 'optional-mark' not in _etiket_govdesi(html, alan), alan

    def test_ornek_yuklenince_bos_kalan_her_alan_isaretli(self, uc):
        html = _html()
        ornek = _ornek_alanlar()
        zorunlu = set(uc['bos_govde'][1]['missing_fields'])
        bos = [a for a in _bos_varsayilanli_alanlar(html)
               if a not in ornek and a not in zorunlu]
        assert 'max_burn_duration' in bos and 'chamber_diameter' in bos
        isaretsiz = [a for a in bos if 'optional-mark' not in _etiket_govdesi(html, a)]
        assert isaretsiz == [], isaretsiz

    def test_isaret_anahtari_iki_dilde(self):
        # ÇEVRİLEN BEKÇİ (onemli2-sivi a2): anahtar sayfa sözlüğüne taşındı
        # (tests/test_i18n_pages.py şablon anahtarını i18n_pages.js'te arar;
        # a1'de o dosya dil2 kulvarının sahasındaydı). İddia aynı: iki dilde.
        en, tr = _sozluk_anahtarlari(I18N_PAGES)
        assert 'liq.ui.optional_mark' in en and 'liq.ui.optional_mark' in tr


# ---------------------------------------------------------------------------
# OH-P-19 · çift uyarı
# ---------------------------------------------------------------------------
def _derin_uyarilar(results: dict, mutasyon=None) -> list:
    html = _html()
    blok = (_js_blok(html, 'const LIQUID_DEEP_WARNING_PATHS') + '\n'
            + _js_blok(html, 'function liquidDeepWarnings(results)'))
    if mutasyon:
        assert mutasyon[0] in blok
        blok = blok.replace(mutasyon[0], mutasyon[1], 1)
    betik = ("function T(k, f) { return f; }\nfunction TF(k, p, f) { return f; }\n"
             "function numTxt(v) { return String(v); }\nconst window = {};\n"
             "%s\nprocess.stdout.write(JSON.stringify(liquidDeepWarnings(%s)));\n"
             % (blok, json.dumps(results)))
    return _node(betik)


def _vf_sonucu(yakit_mesaj='[fuel line] the choked pressure drop was NOT computed',
               oks_mesaj='[oxidizer line] the choked pressure drop was NOT computed'):
    kayit_y = {'field': 'valve.capacity', 'status': 'not_evaluated', 'message': yakit_mesaj}
    kayit_o = {'field': 'valve.capacity', 'status': 'not_evaluated', 'message': oks_mesaj}
    return {'detailed_feed_system': {'valve_feedline': {
        # Modül üst düzey hat listesini vana kayıtlarıyla GENİŞLETİR.
        'fuel_line': {'validity': [{'field': 'line', 'status': 'ok', 'message': 'ok'}, kayit_y],
                      'valve': {'validity': [kayit_y]}},
        'oxidizer_line': {'validity': [kayit_o], 'valve': {'validity': [kayit_o]}},
    }}}


@needs_node
class TestOHP19CiftUyari:
    def test_ayni_kayit_iki_adresten_bir_kez_basilir(self):
        w = _derin_uyarilar(_vf_sonucu())
        mesajlar = [x['message'] for x in w if isinstance(x, dict) and 'message' in x]
        assert mesajlar.count('[fuel line] the choked pressure drop was NOT computed') == 1
        assert mesajlar.count('[oxidizer line] the choked pressure drop was NOT computed') == 1

    def test_iki_hattin_ayni_cumlesi_bilgi_kaybi_olmadan_kalir(self):
        w = _derin_uyarilar(_vf_sonucu())
        mesajlar = [x.get('message') for x in w if isinstance(x, dict)]
        assert any(m and m.startswith('[fuel line]') for m in mesajlar)
        assert any(m and m.startswith('[oxidizer line]') for m in mesajlar)

    def test_gercek_yanitta_birebir_kopya_yok(self, uc):
        w = _derin_uyarilar(uc['kullanici'])
        anahtarlar = [json.dumps([x.get('field'), x.get('status'), x.get('message'),
                                  x.get('code'), x.get('params')], sort_keys=True)
                      for x in w if isinstance(x, dict)]
        assert len(anahtarlar) == len(set(anahtarlar))


# ---------------------------------------------------------------------------
# OH-GT devirleri · chug enum + gimbal alan adı
# ---------------------------------------------------------------------------
class TestHamEnumVeAnahtar:
    def test_chug_eslemesi_motorun_butun_degerlerini_kapsar(self):
        kaynak = ENGINE.read_text(encoding='utf-8')
        degerler = set(re.findall(r"\bchug = '([a-z_]+)'", kaynak))
        assert {'chug_risk', 'chug_margin_ok', 'chug_margin_marginal'} <= degerler
        blok = _js_blok(_html(), 'var CHUG_STATE_TEXT')
        for d in degerler:
            assert re.search(r'\b%s\s*:' % re.escape(d), blok), d

    def test_chug_hucresi_ham_enum_basmaz(self):
        html = _html()
        assert "esc(p.chug_rating) + '</td>" not in html
        assert 'esc(liqChugText(p.chug_rating))' in html
        assert "TF('liq.cyc.chug_state_unknown'" in html

    def test_gimbal_eslemesi_ucun_butun_adlarini_kapsar(self):
        app = APP.read_text(encoding='utf-8')
        m = re.search(r'_GIMBAL_REQUIRED = \(([^)]*)\)', app)
        assert m
        adlar = set(re.findall(r"'([a-zA-Z_]+)'", m.group(1)))
        m2 = re.search(r"_civata_cifti = \(([^)]*)\)", app)
        assert m2
        adlar |= set(re.findall(r"'([a-zA-Z_]+)'", m2.group(1)))
        blok = _js_blok(_html(), 'const GIMBAL_FIELD_LABELS')
        for ad in adlar:
            assert re.search(r'\b%s\s*:' % re.escape(ad), blok), ad
        en, tr = _sozluk_anahtarlari(I18N_PAGES)
        for anahtar in re.findall(r"T\('([a-z0-9_.]+)'", blok):
            assert anahtar in en and anahtar in tr, anahtar


# ---------------------------------------------------------------------------
# TR ondalık kalanları (sıvı sayfası, bu kulvarın kaynakları)
# ---------------------------------------------------------------------------
@needs_node
class TestTROndalik:
    def _kos(self, cagri: str):
        html = _html()
        blok = (_js_blok(html, 'function liqExpTxt(v, d)') + '\n'
                + _js_blok(html, 'function liqStateTempText(text)'))
        betik = ("const window = { I18N: { decimalText: function (s) {"
                 " return /^[+-]?\\d+\\.\\d+(?:[eE][+-]?\\d+)?$/.test(s) ? s.replace('.', ',') : s; } } };\n"
                 "%s\nprocess.stdout.write(JSON.stringify(%s));\n" % (blok, cagri))
        return _node(betik)

    def test_viskozite_ustel_gosterim_ayraci(self):
        assert self._kos('liqExpTxt(0.0016)') == '1,60e-3'
        assert self._kos('liqExpTxt(null) === undefined') is True

    def test_hal_kunyesi_sicakligi_ayraci(self):
        assert (self._kos("liqStateTempText('saturated liquid at NBP (90.2 K)')")
                == 'saturated liquid at NBP (90,2 K)')

    def test_kartlar_yardimciyi_kullanir(self):
        html = _html()
        assert 'props.viscosity?.toExponential(2)' not in html
        assert html.count('liqExpTxt(props.viscosity)') == 2
        assert html.count('liqStateTempText(state.description)') == 2


# ---------------------------------------------------------------------------
# Sözlük hijyeni (bu kulvarın yeni anahtarları)
# ---------------------------------------------------------------------------
YENI_ANAHTARLAR = (
    'liq.ui.optional_mark', 'liq.msg.burn_duration_scope_note',
    'liq.msg.burn_duration_scope_title', 'liq.js.burn_time_not_supplied',
    'liq.js.propellant_tanks_title', 'liq.js.tank_card_not_modelled',
    'panelwarn.liquid.eng_not_generated', 'liq.msg.eng_not_generated_status',
    'liq.msg.eng_export_failed_detail', 'liq.msg.eng_file_downloaded',
    'liq.cyc.chug_state_risk', 'liq.cyc.chug_state_marginal',
    'liq.cyc.chug_state_ok', 'liq.cyc.chug_state_not_evaluated',
    'liq.cyc.chug_state_unknown', 'liq.js.gimbal_unknown_field',
)


#: ÇEVRİLEN BEKÇİ (onemli2-sivi a2): sayfanın T() ile okuduğu anahtarlar
#: i18n_pages.js'e taşındı (tests/test_i18n_pages.py::
#: test_every_template_key_is_defined[liquid.html] onları orada arar ve
#: a1'den beri kırmızıydı). Nesne alanıyla okunan iki kapsam metni ve panel
#: uyarısı i18n_common.js'te kalır (şablon tarayıcısı onları görmez; sayfa
#: sözlüğüne konsalar "ölü anahtar" bekçisi kırmızı olurdu). İddia aynı:
#: her anahtar TEK sözlükte, iki dilde, uzun tiresiz.
ORTAK_SOZLUKTE_KALAN = ('liq.msg.burn_duration_scope_note',
                        'liq.msg.burn_duration_scope_title',
                        'panelwarn.liquid.eng_not_generated')


def test_yeni_anahtarlar_iki_dilde_ve_uzun_tiresiz():
    for k in YENI_ANAHTARLAR:
        yol = I18N_COMMON if k in ORTAK_SOZLUKTE_KALAN else I18N_PAGES
        diger = I18N_PAGES if yol is I18N_COMMON else I18N_COMMON
        en, tr = _sozluk_anahtarlari(yol)
        assert k in en and k in tr, (k, yol.name)
        degerler = _deger(yol, k)
        assert len(degerler) == 2, (k, degerler)
        assert _deger(diger, k) == [], ('anahtar iki sözlükte birden', k)
        for d in degerler:
            assert '—' not in d, (k, d)


def test_yeni_anahtarlar_sayfada_kullanilir():
    html = _html()
    for k in YENI_ANAHTARLAR:
        assert k in html, k


# ===========================================================================
# EK DENETÇİ ŞARTLARI Ş1-Ş3 (24 Eylül 2026) — ön yüz ayakları DAVRANIŞA bağlı
# ===========================================================================
# Ek denetçinin yoklaması (kanıt: docs/scofield/raw/OH/D36/onemli2-sivi/a1/
# sartlar/): yukarıdaki ön yüz düğümlerinin beşi kaynak dizesi aradığı için
# beş ters mutasyonun beşi de YEŞİL kaldı —
#   W1 collectAllParameters'ta `|| 400` yedeği geri (LU-1'in çekirdek kusuru),
#   W2 manşetteki "yayımlanmadı" dalı `&& false` ile ölü,
#   W3 tank kartının not_modelled dalı tutmaz (eski kart yolu TypeError),
#   W4 displayResults'taki liquidEngGateStatus(results) çağrısı sökülü,
#   W5 gimbal eksik-girdi beyanı ham anahtara dönmüş.
# Aşağıdaki SAYFA İKİZİ bu yolları GERÇEK gövdeleriyle koşturur:
#   form (şablon varsayılanları + örnek proje) -> calculateLiquid ->
#   collectAllParameters + collectClosureAndFeedLineParams -> fetch ->
#   GERÇEK süresiz/süreli yanıt (modül fikstürü `uc`) -> displayResults ->
#   manşet tablosu + displayDetailedAnalysis -> displayPropellantTanks +
#   liquidEngGateStatus -> durum satırı.
# Sözlük motoru da gerçektir (i18n.js + i18n_common.js + i18n_pages.js,
# setLang('tr' | 'en')). Grafik, rozet, 3B ve panel işlevleri boş taslaktır:
# bu düğümler onların çıktısını ÖLÇMEZ, yalnız yukarıdaki zinciri ölçer.
I18N_CORE = KOK / 'hrma' / 'static' / 'js' / 'i18n.js'

#: Şablondan GERÇEK gövdesiyle alınan işlevler (sıra önemsiz; eval tek blok).
_SAYFA_ISLEVLERI = (
    'function numTxt(v, d)', 'function pctTxt(v, d)', 'function hrmaFmt(v, dec, unit)',
    'function liqOptNum(id)', 'function collectAllParameters()',
    'function collectClosureAndFeedLineParams()', 'async function calculateLiquid()',
    'function displayResults(results)', 'function _liquidReliabilityCell(tp)',
    'function displayDetailedAnalysis(results)', 'function displayPropellantTanks(tankData)',
    'function liquidTankMassFractionPct(tankData)', 'function _tankEsc(v)',
    'function tankKunye(alan, deger)', 'function tankKriyoSatiri(cs)',
    'function tankMalzemeHucresi(st)', 'function _liquidExportStatus(text)',
    'function liquidEngGateStatus(results)',
    # v3.0.1 K kulvarı (kaynak-cea, 5e6a70514): displayResults veri kaynağı
    # satırını bu yardımcıyla kurar; ikiz onu almazsa 'not defined' der
    # (26 Eki çapraz denetimde taban kırmızısı olarak ölçüldü).
    'function liquidCombustionSourceText(results)',
    # V301/L-A (SV-15): calculateLiquid zincirinin iki yeni yardımcısı (ret
    # gövdesi -> metin; eski hesap hatası bildirimlerinin temizliği).
    'function _liquidRetMetni(govde, durum)',
    'function _liquidHesapHatalariniTemizle()',
    'function _liquidOpakZemin(el)',
)


def _stdin_betigi(kosucu, girdi):
    """Betik + girdi TEK stdin akışında (ÖH V3 taban-b).

    Eski biçim betiği argv'den (``-e``) veriyor, girdiyi stdin'den
    okutuyordu; argv çekirdek tavanına tabidir (Linux MAX_ARG_STRLEN
    128 KiB, tests/test_node_cagri_sozlesmesi.py). Girdi, JSON dizge
    sabiti olarak betiğin başına gömülür; betik stdin'den koşar.
    """
    return 'const HRMA_GIRDI = %s;\n%s' % (json.dumps(json.dumps(girdi)),
                                           kosucu)


_SAYFA_IKIZI = r"""
const girdi = JSON.parse(HRMA_GIRDI);
function dugum(id, o) {
    const n = { id: id, value: o ? o.value : '', type: o ? o.type : 'div',
        textContent: '', className: '', style: {}, dataset: {}, _attr: {}, children: [],
        classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
        setAttribute(a, v) { this._attr[a] = String(v); },
        getAttribute(a) { return Object.prototype.hasOwnProperty.call(this._attr, a) ? this._attr[a] : null; },
        removeAttribute(a) { delete this._attr[a]; },
        appendChild(c) { this.children.push(c); return c; },
        insertAdjacentElement() {}, insertAdjacentHTML() {}, addEventListener() {},
        querySelector() { return null; }, querySelectorAll() { return []; }, closest() { return null; },
        parentNode: { insertAdjacentElement() {}, appendChild() {} } };
    // innerHTML ataması çocukları siler (tarayıcıdaki gibi): displayResults
    // alt sistem ızgarasını her hesapta yeniden kurar.
    let html = '';
    Object.defineProperty(n, 'innerHTML', { get() { return html; },
        set(v) { html = String(v); n.children = []; } });
    return n;
}
const ogeler = {};
for (const [id, o] of Object.entries(girdi.dom)) ogeler[id] = dugum(id, o);
global.document = {
    body: dugum('body'), readyState: 'complete',
    documentElement: { lang: 'en', setAttribute() {}, getAttribute() { return null; } },
    getElementById(id) { if (!(id in ogeler)) ogeler[id] = dugum(id); return ogeler[id]; },
    createElement(t) { return dugum(null, { type: t, value: '' }); },
    querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener() {}, dispatchEvent() {},
};
global.window = global;
Object.defineProperty(global, 'localStorage', { value: { getItem() { return null; }, setItem() {} }, configurable: true });
Object.defineProperty(global, 'navigator', { value: { language: 'en' }, configurable: true });
require(girdi.yol.i18n); require(girdi.yol.common); require(girdi.yol.pages);
window.I18N.setLang(girdi.lang);
require(girdi.yol.reject);
const kayit = { hata: [], govde: [], yazilan: [] };
function _taslak() {}
for (const ad of girdi.taslak) global[ad] = _taslak;
global.showError = function (m) { kayit.hata.push(String(m)); };
global._buildAltitudeFigure = function () { return { traces: [], layout: {}, note: null }; };
// Uç yerine modül fikstürünün GERÇEK yanıtları: gövdede süre varsa süreli
// yanıt (yalnız kullanıcının girdiği sayı ile), yoksa süresiz yanıt.
global.fetch = function (url, opts) {
    const govde = JSON.parse(opts.body);
    kayit.govde.push({ url: url, govde: govde });
    let yanit = girdi.yanit.suresiz;
    if ('max_burn_duration' in govde) {
        yanit = (govde.max_burn_duration === girdi.yanit.sureli.burn_time)
            ? girdi.yanit.sureli : { error: 'ikizde bu süre için yanıt yok: ' + govde.max_burn_duration };
    }
    return Promise.resolve({ status: 200, ok: true, json() { return Promise.resolve(yanit); } });
};
var currentResults = null;
eval(girdi.kod);
(async function () {
    for (const [id, v] of Object.entries(girdi.ornek)) if (ogeler[id]) ogeler[id].value = String(v);
    const anlar = [];
    for (const a of girdi.adimlar) {
        if (a.tur === 'form') {
            for (const [id, v] of Object.entries(a.deger)) ogeler[id].value = String(v);
            continue;
        }
        if (a.tur === 'disa_aktarim') {
            // Başka bir dışa aktarımın satıra yazması (Excel düğmesinin
            // başarı dalı: aynı yardımcı, aynı sözlük anahtarı).
            const metin = T(a.anahtar, a.yedek);
            _liquidExportStatus(metin);
            kayit.yazilan.push(metin);
            continue;
        }
        kayit.hata.length = 0;
        await calculateLiquid();
        const son = kayit.govde[kayit.govde.length - 1];
        anlar.push({
            url: son.url, govde: son.govde, hata: kayit.hata.slice(),
            rapor: ogeler.designReport.innerHTML,
            tank: ogeler.subsystemsGrid.children.map(function (c) {
                return { attr: c._attr, html: c.innerHTML }; }),
            durum: ogeler.liquidExportStatus.textContent });
    }
    process.stdout.write(JSON.stringify({ anlar: anlar, yazilan: kayit.yazilan }));
})().catch(function (e) { process.stderr.write(String(e && e.stack || e)); process.exit(3); });
"""

#: Zincirin dışında kalan (bu düğümlerin ÖLÇMEDİĞİ) işlevler: boş taslak.
_SAYFA_TASLAKLARI = (
    'showLoading', 'showWarning', 'showInfo', 'showSuccess', 'applyUnwiredBadges',
    'displayLiquidWarnings', 'displayGimbalMount', 'displayMotorDesign',
    'generateCADVisualization', 'displayEngineeringCards', 'updatePerformanceMapsTab',
    'updateFeedSystemTab', 'updateCyclePanel', 'updateCombustionTab',
    'updateEfficiencyTab', 'updateManufacturingTab', 'liquidPlot', '_liquidPlotNote',
    'syncInjectorPanelToSolver', 'updateSixDofEngineNote', 'createTankVisualization',
    'exportTankCAD',
)


def _dom_ikizi(html: str) -> dict:
    """Şablondaki id'li öğeler; input/select şablon varsayılanıyla."""
    ogeler = {}
    for m in re.finditer(r'<(?!input\b|select\b)([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"', html):
        ogeler[m.group(2)] = {'value': '', 'type': m.group(1)}
    for m in re.finditer(r'<input\b([^>]*)>', html):
        idm = re.search(r'\bid="([^"]+)"', m.group(1))
        if not idm:
            continue
        val = re.search(r'\bvalue="([^"]*)"', m.group(1))
        tip = re.search(r'\btype="([^"]+)"', m.group(1))
        ogeler[idm.group(1)] = {'value': val.group(1) if val else '',
                                'type': tip.group(1) if tip else 'text'}
    for m in re.finditer(r'<select\b([^>]*)>(.*?)</select>', html, re.S):
        idm = re.search(r'\bid="([^"]+)"', m.group(1))
        if not idm:
            continue
        deger = ''
        for s in re.findall(r'<option\b([^>]*)>', m.group(2)):
            v = re.search(r'\bvalue="([^"]*)"', s)
            if v is None:
                continue
            if not deger:
                deger = v.group(1)
            if re.search(r'\bselected\b', s):
                deger = v.group(1)
                break
        ogeler[idm.group(1)] = {'value': deger, 'type': 'select'}
    return ogeler


def _sayfa_kos(uc, adimlar, lang='tr') -> dict:
    html = _html()
    kod = '\n'.join([_js_blok(html, b) for b in _SAYFA_ISLEVLERI]
                    + re.findall(r'^\s*const LIQUID_DEC_\w+ = [^;]+;', html, re.M))
    girdi = {
        'dom': _dom_ikizi(html), 'kod': kod, 'lang': lang, 'ornek': _ornek_alanlar(),
        'adimlar': adimlar, 'taslak': list(_SAYFA_TASLAKLARI),
        'yanit': {'suresiz': uc['bos'], 'sureli': uc['kullanici']},
        'yol': {'i18n': str(I18N_CORE), 'common': str(I18N_COMMON),
                'pages': str(I18N_PAGES), 'reject': str(REJECT_BODY)},
    }
    out = subprocess.run([NODE], input=_stdin_betigi(_SAYFA_IKIZI, girdi),
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout)


#: Süresiz hesap -> kullanıcı süreyi girer -> aynı sayfada yeniden hesap.
_IKI_HESAP = [{'tur': 'hesap'},
              {'tur': 'form', 'deger': {'max_burn_duration': str(KULLANICI_SURESI_S)}},
              {'tur': 'hesap'}]


@pytest.fixture(scope='module')
def ikiz(uc):
    if NODE is None:
        pytest.skip('node yok')
    return {lang: _sayfa_kos(uc, _IKI_HESAP, lang) for lang in ('tr', 'en')}


def _sozluk_tr(anahtar: str) -> str:
    """Sayfa sözlüğündeki TR değeri (EN bloğu önce, TR sonra gelir)."""
    degerler = _deger(I18N_PAGES, anahtar) or _deger(I18N_COMMON, anahtar)
    assert len(degerler) == 2, (anahtar, degerler)
    return degerler[1]


def _manset_hucresi(rapor: str) -> str:
    m = re.search(r"<strong>(?:Toplam İmpuls|Total Impulse)</strong></td>\s*<td[^>]*>(.*?)</td>",
                  rapor, re.S)
    assert m, 'manşette toplam impuls satırı yok'
    return m.group(1)


class TestSart1SayfaIkizi:
    """Ş1 (a)-(c): gövde, manşet, tank kartı ve kapı satırı DAVRANIŞLA."""

    def test_a_govdede_sure_bosken_anahtar_yok_girilince_girilen_sayi(self, ikiz):
        bos, sureli = ikiz['tr']['anlar']
        assert bos['url'] == sureli['url'] == '/calculate_liquid'
        # Gövde sayfanın GERÇEK gövdesi: örnek projenin zorunlu alanları var.
        assert bos['govde']['thrust'] == _ornek_alanlar()['thrust']
        assert 'max_burn_duration' not in bos['govde'], bos['govde'].get('max_burn_duration')
        assert sureli['govde']['max_burn_duration'] == KULLANICI_SURESI_S

    def test_b_manset_suresiz_yanitla_beyan_suresiz_sayi_basmaz(self, ikiz, uc):
        bos, sureli = ikiz['tr']['anlar']
        assert bos['hata'] == [] and sureli['hata'] == []
        hucre = _manset_hucresi(bos['rapor'])
        assert hucre.strip() == _sozluk_tr('liq.js.burn_time_not_supplied')
        assert 'kN' not in hucre
        # Süreli yanıtta formül satırı, sayılar yanıttan (TR ayraç).
        d = uc['kullanici']
        beklenen = '%s kN&#183;s = %s kN &#215; %s s' % (
            ('%.1f' % (d['thrust'] * d['burn_time'] / 1000)).replace('.', ','),
            ('%.2f' % (d['thrust'] / 1000)).replace('.', ','),
            ('%.1f' % d['burn_time']).replace('.', ','))
        assert _manset_hucresi(sureli['rapor']).strip() == beklenen

    def test_b_tank_karti_suresiz_yanitla_not_modelled(self, ikiz, uc):
        assert uc['bos']['propellant_tanks']['status'] == 'not_modelled'
        bos, sureli = ikiz['tr']['anlar']
        assert bos['hata'] == [], bos['hata']
        kartlar = [t for t in bos['tank'] if t['attr'].get('data-tank-card') == 'not_modelled']
        assert len(kartlar) == 1 and len(bos['tank']) == 1, [t['attr'] for t in bos['tank']]
        assert _sozluk_tr('liq.js.tank_card_not_modelled') in kartlar[0]['html']
        assert _sozluk_tr('liq.js.propellant_tanks_title') in kartlar[0]['html']
        # Süreli yanıtta boyutlandırılmış kartlar; not_modelled kartı yok.
        assert sureli['hata'] == [], sureli['hata']
        assert not [t for t in sureli['tank'] if t['attr'].get('data-tank-card')]
        assert any('(LOX)' in t['html'] for t in sureli['tank'])

    def test_c_displayresults_kapi_satirini_yazar(self, ikiz):
        """Bağlantı ölçümü: satırı calculateLiquid -> displayResults yazar."""
        bos = ikiz['tr']['anlar'][0]
        assert bos['durum'].startswith(_sozluk_tr('liq.msg.eng_not_generated_status')
                                       .split('{detail}')[0]), bos['durum']


@needs_node
class TestSart1dGimbalBeyani:
    """Ş1 (d): ucun GERÇEK 422 alan listesi 'Etiket (anahtar)' biçimiyle."""

    @pytest.fixture(scope='class')
    def gimbal_ret(self):
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            r = c.post('/api/gimbal-mount', json={})
        assert r.status_code == 422, r.get_json()
        return r.get_json()

    def _kos(self, alanlar, lang='tr'):
        html = _html()
        kod = '\n'.join([_js_blok(html, 'function gimbalEsc(s)'),
                         _js_blok(html, 'const GIMBAL_FIELD_LABELS') + ';',
                         _js_blok(html, 'function gimbalFieldText(key)'),
                         _js_blok(html, 'function gimbalMissingHtml(fields)')])
        betik = ("global.window = global;\n"
                 "global.document = { readyState: 'complete', documentElement: { lang: 'en',"
                 " setAttribute() {}, getAttribute() { return null; } },"
                 " querySelectorAll() { return []; }, querySelector() { return null; },"
                 " getElementById() { return null; }, addEventListener() {}, dispatchEvent() {} };\n"
                 "Object.defineProperty(global, 'localStorage', { value: { getItem() { return null; },"
                 " setItem() {} }, configurable: true });\n"
                 "require(%s); require(%s); require(%s); window.I18N.setLang(%s);\n"
                 "%s\nprocess.stdout.write(JSON.stringify(gimbalMissingHtml(%s)));\n"
                 % (json.dumps(str(I18N_CORE)), json.dumps(str(I18N_COMMON)),
                    json.dumps(str(I18N_PAGES)), json.dumps(lang), kod, json.dumps(alanlar)))
        return _node(betik)

    def test_d_etiket_anahtar_bicimi(self, gimbal_ret):
        alanlar = gimbal_ret['missing_fields']
        assert alanlar == ['thrust_N', 'gimbal_angle_deg', 'actuator_arm_m']
        cikti = self._kos(alanlar)
        esleme = dict(re.findall(r"(\w+): function \(\) \{ return T\('([a-z0-9_.]+)'",
                                 _js_blok(_html(), 'const GIMBAL_FIELD_LABELS')))
        for k in alanlar:
            etiket = _sozluk_tr(esleme[k])
            assert '%s (%s)' % (etiket, k) in cikti, (k, cikti)
            # Anahtar YALNIZ parantez içinde geçer (çıplak ham anahtar yok).
            assert cikti.count(k) == cikti.count('(%s)' % k) == 1, (k, cikti)


class TestSart2BayatSatir:
    """Ş2: süreli yeniden hesapta önceki kapı mesajı kalmaz; başkası korunur."""

    def test_sureli_yeniden_hesapta_kapi_satiri_silinir(self, ikiz, uc):
        assert uc['kullanici']['openrocket']['eng_error'] is None
        for lang in ('tr', 'en'):
            bos, sureli = ikiz[lang]['anlar']
            assert bos['durum'], lang
            assert sureli['durum'] == '', (lang, sureli['durum'])

    @needs_node
    def test_baska_disa_aktarimin_satiri_korunur(self, uc):
        kos = _sayfa_kos(uc, [
            {'tur': 'hesap'},
            {'tur': 'disa_aktarim', 'anahtar': 'liq.msg.excel_workbook_downloaded',
             'yedek': 'Excel workbook downloaded'},
            {'tur': 'form', 'deger': {'max_burn_duration': str(KULLANICI_SURESI_S)}},
            {'tur': 'hesap'}])
        excel = kos['yazilan'][0]
        assert excel == _sozluk_tr('liq.msg.excel_workbook_downloaded')
        assert kos['anlar'][1]['durum'] == excel


def _etiket_tr(anahtar_sozluk: str) -> str:
    return re.sub(r'\s*:\s*$', '', _sozluk_tr(anahtar_sozluk))


class TestSart3KapiSatiriDili:
    """Ş3: satır sözlük cümlesi + alan etiketleri; sunucu paragrafı yok."""

    ETIKET = {'burn_time': 'liq.js.burn_time', 'propellant_mass': 'liq.js.propellant_mass',
              'total_impulse': 'liq.ui.total_impulse',
              'thrust_curve': 'liq.js.eng_field_thrust_curve'}

    def test_tr_satiri_sozluk_cumlesi_ve_etiketler(self, ikiz, uc):
        alanlar = uc['bos']['openrocket']['eng_error']['missing_fields']
        assert set(alanlar) <= set(self.ETIKET), alanlar
        durum = ikiz['tr']['anlar'][0]['durum']
        alan_metni = ', '.join('%s (%s)' % (_etiket_tr(self.ETIKET[k]), k) for k in alanlar)
        detay = _sozluk_tr('liq.msg.eng_gate_fields_missing').replace('{fields}', alan_metni)
        assert durum == _sozluk_tr('liq.msg.eng_not_generated_status').replace('{detail}', detay)
        assert 'NOT generated' not in durum and 'missing_fields' not in durum
        assert 'Yanma Süresi (burn_time)' in durum
        for k in alanlar:
            assert durum.count(k) == 1, (k, durum)
        assert len(durum) < 300, len(durum)

    def test_en_satiri_ayni_kisa_cumle(self, ikiz, uc):
        durum = ikiz['en']['anlar'][0]['durum']
        assert durum.startswith('.eng not generated: the design result lacks Burn Time (burn_time), ')
        assert 'NOT generated' not in durum and 'missing_fields' not in durum
        for k in uc['bos']['openrocket']['eng_error']['missing_fields']:
            assert durum.count(k) == 1, (k, durum)
        assert len(durum) < 300, len(durum)


#: Şart 3'ün yeni anahtarları (sayfa sözlüğü, iki dil).
SART_ANAHTARLARI = ('liq.msg.eng_gate_fields_missing', 'liq.js.eng_field_thrust_curve',
                    'liq.js.eng_gate_unlabelled_field')


def test_sart_anahtarlari_iki_dilde_tek_sozlukte_ve_sayfada():
    html = _html()
    en, tr = _sozluk_anahtarlari(I18N_PAGES)
    for k in SART_ANAHTARLARI:
        assert k in en and k in tr, k
        degerler = _deger(I18N_PAGES, k)
        assert len(degerler) == 2 and degerler[0] != degerler[1], (k, degerler)
        assert _deger(I18N_COMMON, k) == [], k
        assert all('—' not in d for d in degerler), (k, degerler)
        assert "T('%s'" % k in html or "TF('%s'" % k in html, k
