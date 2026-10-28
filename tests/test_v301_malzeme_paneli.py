"""v3.0.1 (Ayberk tur 1) kulvar M — malzeme seçim ekranı bekçileri.

Ayberk'in maddesi: "Material seçim ekranı olmalı hem yanma odası hem
enjektör hem nozzle için."

Kanıt: docs/scofield/raw/OH/V301/ayberk1/malzeme/ (once.json, sonra.json,
once_s7.json, sonra_s7.json, RAPOR.md). Bu dosya docs kanıtını OKUMAZ: bütün
girdiler ürün kaynağından (şablon metni, motor/uç modülleri) ya da ucun
kendisinden (Flask test istemcisi) gelir; yayın dalında da koşar.

ÖLÇÜLEN KUSUR (once.json):
  S1  Üç seçici de ilk hesaptan önce GİZLİ ``#designConfigPanel`` içindeydi
      (enjektörünki ayrıca gizli ``#injector_config`` sekmesinde); seçenekler
      şablonda elle yazılmıştı — lülede motorun tanıdığı 7 malzemenin
      (``NOZZLE_MATERIAL_COOLING``) yalnız 3'ü vardı.
  S4  Çözülemeyen malzeme adı HTTP 200 alıyordu: kamara 'peynir' -> çelik
      sayıları (uyarı + geri çekilmiş hüküm), lüle 'peynir' -> grafit
      sayıları 'analyzed', enjektör ``False``/``0`` -> plaka denetimi
      SESSİZCE yok; kardeş uçlar (/api/quick-geometry, /api/transient-
      analysis) aynı.
  S7  Lülede takma ad ham kalıyordu: 'cu_cr_zr' (CuCrZr'nin materials_db
      takma adı) soğutma tablosunu ıskalayıp 'natural' kabulüyle 3261,9 K
      boğaz cidarı, 'cucrzr' ise 'regenerative' ile 1406,3 K veriyordu.

Bekçiler
  K   Kayıt: rol kuralları motorun kendi tablolarından; seçenekler, eski form
      değerleri, varsayılanlar, özellik satırları (kayıtta yoksa satır yok).
  S   Sayfa: panel hesaptan önce görünür bölgede; kimlikler tek; seçenekler
      kayıtla birebir; gizli panelde kopya yok; köken damgası sözleşmesi.
  U   Uç: çözülemeyen ad ADLI 422 (üç uç); geçerli ad kapıdan geçer.
  J   Panel betiği (node ile GERÇEKTEN koşturulur): özellik satırları ve
      gönderim durumu gerçek veriden.
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
SOZLUK = KOK / 'hrma' / 'static' / 'js' / 'i18n_advanced.js'
PANELLER = KOK / 'hrma' / 'static' / 'js' / 'panels'
NODE = shutil.which('node')
MALZEME_SECICI_ALANLARI = ('chamber_material', 'nozzle_material', 'injector_material')


def _oku(yol: pathlib.Path) -> str:
    return yol.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def kayit():
    from hrma.app import _hibrit_malzeme_secim_kaydi
    return _hibrit_malzeme_secim_kaydi()


@pytest.fixture(scope='module')
def sayfa(istemci):
    r = istemci.get('/hybrid')
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _secici(html, alan):
    m = re.search(r'<select id="%s"[^>]*>(.*?)</select>' % alan, html, re.S)
    assert m, alan
    return re.findall(r'<option value="([^"]*)"([^>]*)>', m.group(1))


def _sozluk(dil):
    kaynak = _oku(SOZLUK)
    m = re.search(r'^\s{8}%s:\s*\{' % dil, kaynak, re.M)
    govde = kaynak[m.end():]
    govde = govde[:govde.index('\n        }')]
    return dict(re.findall(r"^\s*'([^']+)':\s*'((?:\\.|[^'\\])*)',?\s*$",
                           govde, re.M))


def _js_listesi(dosya):
    """Panel betiğindeki ``const MATERIALS = [[anahtar, ...], ...]`` anahtarları."""
    metin = _oku(PANELLER / dosya)
    i = metin.index('const MATERIALS = [')
    j = metin.index('];', i)
    return re.findall(r"\[\s*'([\w]+)'", metin[i:j])


# ===========================================================================
# K — kayıt
# ===========================================================================
class TestKayit:
    def test_kamara_rolu_yapisal_etiket_ve_guverte_secicileriyle_ayni(self, kayit):
        """Kamara seçenekleri = 'structural' etiketli kayıtlar ve analiz
        güvertesinin (yapısal/güvenlik/ısıl) seçicileri hepsini gösterebilir.
        Listede olmayan ad güverte seçicisinde sessizce ilk seçeneğe
        düşüyordu (D15/P10B3-08, SF 3,38 kat iyimser)."""
        from hrma.data.materials_db import MATERIALS
        anahtarlar = [o['material_key'] for o in kayit['chamber_material']['options']]
        beklenen = [k for k, r in MATERIALS.items() if 'structural' in r['tags']]
        assert anahtarlar == beklenen
        assert len(anahtarlar) == 16
        for dosya in ('structural_panel.js', 'safety_panel.js', 'thermal_panel.js'):
            eksik = set(anahtarlar) - set(_js_listesi(dosya))
            assert not eksik, (dosya, sorted(eksik))

    def test_nozul_rolu_motorun_kendi_tablosu(self, kayit):
        from hrma.engines.hybrid_rocket_engine import NOZZLE_MATERIAL_COOLING
        anahtarlar = [o['material_key'] for o in kayit['nozzle_material']['options']]
        assert anahtarlar == list(NOZZLE_MATERIAL_COOLING)
        assert len(anahtarlar) == 7
        for o in kayit['nozzle_material']['options']:
            assert o['cooling_assumption'] == NOZZLE_MATERIAL_COOLING[o['material_key']]

    def test_nozul_erozyon_satiri_motorun_kendi_kararindan(self, kayit):
        from hrma.analysis.transient_ballistics import ThroatErosionModel
        for o in kayit['nozzle_material']['options']:
            try:
                ThroatErosionModel.for_material(o['material_key'])
                beklenen = 'published_band'
            except ValueError:
                beklenen = 'no_published_data'
            assert o['erosion_model'] == beklenen, o['material_key']
        durum = {o['material_key']: o['erosion_model']
                 for o in kayit['nozzle_material']['options']}
        assert durum['graphite'] == 'published_band'
        assert durum['carbon_carbon'] == 'published_band'
        assert durum['tungsten'] == 'no_published_data'

    def test_enjektor_rolu_yapisal_ve_boru_etiketi(self, kayit):
        from hrma.data.materials_db import MATERIALS
        anahtarlar = [o['material_key'] for o in kayit['injector_material']['options']]
        beklenen = [k for k, r in MATERIALS.items()
                    if {'structural', 'pipe'} & set(r['tags'])]
        assert anahtarlar == beklenen
        assert 'brass_c360' in anahtarlar      # v3.0.0 formunun pirinç seçeneği

    def test_eski_form_degerleri_secenek_degeri_olarak_korunur(self, kayit):
        """Eski .hrma dosyaları bu değerleri taşır; proje şeridi değeri AYNEN
        atar (project_bar.js restoreFields)."""
        from hrma.app import HYBRID_MATERIAL_FORM_LEGACY_VALUES
        for alan, eskiler in HYBRID_MATERIAL_FORM_LEGACY_VALUES.items():
            degerler = [o['value'] for o in kayit[alan]['options']]
            for eski in eskiler:
                assert eski in degerler, (alan, eski)
        eslem = {o['material_key']: o['value']
                 for o in kayit['injector_material']['options']}
        assert eslem['ss_316'] == 'stainless_steel'
        assert eslem['titanium_6al4v'] == 'titanium'
        assert eslem['brass_c360'] == 'brass'
        eslem = {o['material_key']: o['value']
                 for o in kayit['chamber_material']['options']}
        assert eslem['ss_304'] == 'steel_304'
        assert eslem['steel_4130'] == 'steel_4130'

    def test_sunulan_her_secenek_ucun_cozumleyicisinde_ayni_kayda_doner(self, kayit):
        from hrma.app import _hibrit_malzeme_anahtari
        for alan in MALZEME_SECICI_ALANLARI:
            for o in kayit[alan]['options']:
                assert _hibrit_malzeme_anahtari(alan, o['value']) == o['material_key'], (
                    alan, o['value'])

    def test_varsayilanlar_tek_kaynaktan(self, kayit):
        from hrma.engines.hybrid_rocket_engine import (
            HYBRID_CHAMBER_MATERIAL_DEFAULT, HYBRID_NOZZLE_MATERIAL_DEFAULT)
        assert kayit['chamber_material']['default_value'] == HYBRID_CHAMBER_MATERIAL_DEFAULT
        assert kayit['nozzle_material']['default_value'] == HYBRID_NOZZLE_MATERIAL_DEFAULT
        assert kayit['injector_material']['default_value'] is None

    def test_ozellik_degerleri_kayittan_birim_cevrimiyle(self, kayit):
        from hrma.data.materials_db import get_material, temperature_limits
        o = {x['material_key']: x for x in kayit['chamber_material']['options']}['ss_304']
        p = {x['id']: x for x in o['properties']}
        rec = get_material('ss_304')
        assert p['yield_strength']['value'] == pytest.approx(rec['yield_strength'] / 1e6)
        assert p['yield_strength']['unit'] == 'MPa'
        assert p['ultimate_strength']['value'] == pytest.approx(rec['ultimate_strength'] / 1e6)
        assert p['density']['value'] == rec['density']
        assert p['thermal_conductivity']['value'] == rec['thermal_conductivity']
        assert p['allowable_temperature_K']['value'] == temperature_limits(rec)['allowable_K']
        assert o['source'] == rec['source']
        assert o['name'] == rec['name']
        inj = {x['material_key']: x for x in kayit['injector_material']['options']}['brass_c360']
        assert [x['id'] for x in inj['properties']] == ['yield_strength', 'density']

    def test_kayitta_olmayan_ozellik_satiri_yayimlanmaz(self, monkeypatch):
        from hrma.data import materials_db
        from hrma.engines import hybrid_rocket_engine as m
        kopya = dict(materials_db.MATERIALS)
        kopya['graphite'] = dict(kopya['graphite'], emissivity=None)
        monkeypatch.setattr(materials_db, 'MATERIALS', kopya)
        o = {x['material_key']: x for x in
             m.hybrid_material_role_options('nozzle_material')}['graphite']
        assert 'emissivity' not in [x['id'] for x in o['properties']]
        assert 'thermal_conductivity' in [x['id'] for x in o['properties']]

    def test_her_ozellik_kimliginin_sayfada_etiketi_var(self):
        from hrma.engines.hybrid_rocket_engine import HYBRID_MATERIAL_ROLES
        sablon = _oku(SABLON)
        i = sablon.index('const MALZEME_OZELLIK_ETIKETLERI = {')
        blok = sablon[i:sablon.index('};', i)]
        for rol in HYBRID_MATERIAL_ROLES.values():
            for kimlik, *_ in rol['properties']:
                assert re.search(r'\b%s: \[' % kimlik, blok), kimlik


# ===========================================================================
# S — sayfa
# ===========================================================================
class TestSayfa:
    def test_kimlikler_tek_ve_gorunur_panelde(self, sayfa):
        for alan in MALZEME_SECICI_ALANLARI:
            assert sayfa.count('id="%s"' % alan) == 1, alan
        p = sayfa.index('id="materialsPanel"')
        gizli = sayfa.index('id="designConfigPanel"')
        enj = sayfa.index('data-i18n="adv.sec.injectorConfiguration"')
        analiz = sayfa.index('id="analysis_panel"')
        assert enj < p < analiz, 'panel Enjektör ile Analiz Türü arasında olmalı'
        for alan in MALZEME_SECICI_ALANLARI:
            konum = sayfa.index('id="%s"' % alan)
            assert p < konum < analiz, alan
            assert not (gizli < konum < sayfa.index('<!-- Injector Configuration -->', gizli)
                        ), alan
        acilis = re.search(r'<div class="panel" id="materialsPanel"[^>]*>', sayfa).group(0)
        assert 'display' not in acilis and 'hidden' not in acilis

    def test_gizli_panelde_malzeme_secicisi_kalmadi(self):
        sablon = _oku(SABLON)
        i = sablon.index('<div id="designConfigPanel"')
        j = sablon.index('<!-- v2.6.27 (otuz ikinci parti)', i)
        for alan in MALZEME_SECICI_ALANLARI:
            assert ('id="%s"' % alan) not in sablon[i:j], alan

    @pytest.mark.parametrize('alan', MALZEME_SECICI_ALANLARI)
    def test_secenekler_kayitla_birebir(self, sayfa, kayit, alan):
        secenekler = _secici(sayfa, alan)
        degerler = [v for v, _ in secenekler]
        beklenen = [o['value'] for o in kayit[alan]['options']]
        if alan == 'injector_material':
            beklenen = [''] + beklenen
        assert degerler == beklenen
        secili = [v for v, oz in secenekler if re.search(r'\bselected\b', oz)]
        varsayilan = kayit[alan]['default_value']
        assert secili == [varsayilan if varsayilan is not None else '']

    def test_kayit_jsonu_sayfada_ayni(self, sayfa, kayit):
        import html as _html
        m = re.search(r'id="hybridMaterialRegistry" hidden data-registry=\'([^\']*)\'', sayfa)
        assert m
        assert json.loads(_html.unescape(m.group(1))) == json.loads(json.dumps(kayit))

    def test_sablonda_elle_yazilmis_malzeme_secenegi_yok(self):
        sablon = _oku(SABLON)
        for alan in MALZEME_SECICI_ALANLARI:
            i = sablon.index('<select id="%s"' % alan)
            govde = sablon[i:sablon.index('</select>', i)]
            assert '<option' not in govde, alan
            assert 'malzeme_secenekleri(hybrid_materials.%s' % alan in govde
        # Kamara seçili seçeneği uç varsayılanı sabitinden (10. tur sözleşmesi).
        assert ('malzeme_secenekleri(hybrid_materials.chamber_material, '
                'hybrid_chamber_material_default)') in sablon

    def test_secenek_adlari_iki_dilde_ve_en_kayit_adi(self, kayit):
        en, tr = _sozluk('en'), _sozluk('tr')
        for alan in MALZEME_SECICI_ALANLARI:
            for o in kayit[alan]['options']:
                assert o['i18n_key'] in en and o['i18n_key'] in tr, o['i18n_key']
                assert en[o['i18n_key']] == o['name'], o['i18n_key']
                assert tr[o['i18n_key']] != en[o['i18n_key']], o['i18n_key']

    def test_koken_damgasi_sozlesmesi_korundu(self):
        sablon = _oku(SABLON)
        i = sablon.index('const TASARIM_PANELI_ALANLARI = [')
        liste = sablon[i:sablon.index('];', i)]
        for alan in MALZEME_SECICI_ALANLARI:
            assert "'%s'" % alan in liste, alan
        gfd = sablon[sablon.index('function getFormData('):]
        for alan in MALZEME_SECICI_ALANLARI:
            assert re.search(r"tasarimAlaniGonder\(\w+, '%s'" % alan, gfd), alan

    def test_tarayici_form_geri_yuklemesi_kapali(self, sayfa):
        for alan in MALZEME_SECICI_ALANLARI:
            acilis = re.search(r'<select id="%s"[^>]*>' % alan, sayfa).group(0)
            assert 'autocomplete="off"' in acilis, alan


@pytest.mark.skipif(NODE is None, reason='node yok')
class TestGovde:
    """getFormData GERÇEKTEN koşturulur (test_d36 DOM ikizi)."""

    def test_dokunulmamis_secim_gitmez_damgali_secim_gider(self):
        from tests.test_d36_hibrit_a1 import _govde
        g = _govde()
        for alan in MALZEME_SECICI_ALANLARI:
            assert alan not in g, alan
        g = _govde(damga={'chamber_material': 'user', 'nozzle_material': 'project_file',
                          'injector_material': 'user'},
                   deger={'chamber_material': 'inconel_718',
                          'nozzle_material': 'carbon_carbon',
                          'injector_material': 'brass'})
        assert (g['chamber_material'], g['nozzle_material'],
                g['injector_material']) == ('inconel_718', 'carbon_carbon', 'brass')
        kaynak = {b['field']: b['source'] for b in g['design_config_fields']}
        assert kaynak['nozzle_material'] == 'project_file'

    def test_secilmedi_secenegi_damgali_olsa_da_gitmez(self):
        from tests.test_d36_hibrit_a1 import _govde
        g = _govde(damga={'injector_material': 'user'},
                   deger={'injector_material': ''})
        assert 'injector_material' not in g


# ===========================================================================
# U — uç kapıları
# ===========================================================================
KOTU_DEGERLER = ['peynir', True, False, 0, 123, ['steel_304'], {'a': 1}]


def _yuk():
    from tests.test_z5s_cozulemeyen_kimlik import KIMLIK_HIBRIT
    return dict(KIMLIK_HIBRIT)


class TestUcKapisi:
    @pytest.mark.parametrize('deger', KOTU_DEGERLER)
    def test_kamara_cozulemeyen_ad_adli_422(self, istemci, deger):
        r = istemci.post('/calculate', json=dict(_yuk(), chamber_material=deger))
        assert r.status_code == 422, r.status_code
        j = r.get_json()
        assert j['error'] == 'unresolved_material'
        assert j['invalid_fields'][0]['field'] == 'chamber_material'
        assert j['invalid_fields'][0]['resolution'] == 'unresolved'

    @pytest.mark.parametrize('deger', ['peynir', 'Stainless-Steel-X'])
    def test_nozul_cozulemeyen_ad_adli_422(self, istemci, deger):
        r = istemci.post('/calculate', json=dict(_yuk(), nozzle_material=deger))
        assert r.status_code == 422
        f = r.get_json()['invalid_fields'][0]
        assert f['field'] == 'nozzle_material' and f['resolved_to'] is None
        assert f['available']['canonical']

    @pytest.mark.parametrize('deger', KOTU_DEGERLER)
    def test_enjektor_cozulemeyen_ad_adli_422(self, istemci, deger):
        r = istemci.post('/calculate', json=dict(_yuk(), injector_material=deger))
        assert r.status_code == 422, r.status_code
        f = r.get_json()['invalid_fields'][0]
        assert f['field'] == 'injector_material'
        assert 'stainless_steel' in f['available']['form_aliases']

    @pytest.mark.parametrize('uc', ['/api/quick-geometry', '/api/transient-analysis'])
    @pytest.mark.parametrize('alan', ['chamber_material', 'nozzle_material'])
    def test_kardes_uclar_da_reddeder(self, istemci, uc, alan):
        r = istemci.post(uc, json=dict(_yuk(), **{alan: 'peynir'}))
        assert r.status_code == 422, (uc, alan, r.status_code)
        assert r.get_json()['invalid_fields'][0]['field'] == alan

    def test_verilmedi_sayilanlar_kapiya_takilmaz(self):
        from hrma.app import _hibrit_malzeme_kimlik_reddi, app
        with app.app_context():
            for deger in (None, '', '   '):
                assert _hibrit_malzeme_kimlik_reddi(
                    {'nozzle_material': deger, 'injector_material': deger}) is None

    def test_sunulan_secenekler_kapidan_gecer(self, kayit):
        from hrma.app import _hibrit_malzeme_kimlik_reddi, app
        with app.app_context():
            for alan in ('nozzle_material', 'injector_material'):
                for o in kayit[alan]['options']:
                    assert _hibrit_malzeme_kimlik_reddi({alan: o['value']}) is None, (
                        alan, o['value'])

    def test_kamara_tireli_takma_ad_cozulur(self):
        """'c-c' / 'c-103' materials_db'nin KENDİ takma adlarıdır; eskiden
        tire alt çizgiye çevrilip çözülemiyordu (künye 'unresolved' derken
        motor aynı adı çözüp hesaplıyordu — once_s7.json)."""
        from hrma.app import _resolve_material_request
        assert _resolve_material_request('c-c', 'chamber_material', None)[0] == 'carbon_carbon'
        assert _resolve_material_request('c-103', 'chamber_material', None)[0] == 'niobium_c103'
        # Tire takma adın parçası değilse eski normalleştirme sürer.
        assert _resolve_material_request('17-4ph', 'chamber_material', None)[0] == 'ss_17_4ph'
        assert _resolve_material_request('Stainless-Steel', 'injector_material',
                                         None)[0] == 'ss_316'


class TestNozulTakmaAdi:
    def _cozucu(self):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        e = HybridRocketEngine.__new__(HybridRocketEngine)
        e._defaults_used, e.design_warnings = [], []
        return e

    @pytest.mark.parametrize('ad,kanonik', [
        ('cu_cr_zr', 'cucrzr'), ('c-c', 'carbon_carbon'), ('tzm', 'molybdenum_tzm'),
        ('c103', 'niobium_c103'), ('Graphite', 'graphite'), ('copper', 'copper')])
    def test_lule_takma_adi_kanonik_ada_cozulur(self, ad, kanonik):
        """S7: 'cu_cr_zr' soğutma tablosunu ıskalıyordu ('natural', 3261,9 K)."""
        from hrma.engines.hybrid_rocket_engine import NOZZLE_MATERIAL_COOLING
        e = self._cozucu()
        assert e._resolve_nozzle_material(ad) == kanonik
        assert kanonik in NOZZLE_MATERIAL_COOLING
        assert not e.design_warnings

    def test_varsayilan_ve_dusus_tek_sabitten(self):
        from hrma.engines.hybrid_rocket_engine import HYBRID_NOZZLE_MATERIAL_DEFAULT
        e = self._cozucu()
        assert e._resolve_nozzle_material(None) == HYBRID_NOZZLE_MATERIAL_DEFAULT
        assert e._defaults_used == ['nozzle_material']
        assert e._resolve_nozzle_material('peynir') == HYBRID_NOZZLE_MATERIAL_DEFAULT
        assert e.design_warnings


# ===========================================================================
# J — panel betiği node ile
# ===========================================================================
def _islev(metin, bas):
    i = metin.index(bas)
    j = metin.index('{', i)
    derinlik = 0
    for k in range(j, len(metin)):
        if metin[k] == '{':
            derinlik += 1
        elif metin[k] == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[i:k + 1]
    raise AssertionError(bas)


def _sabit(metin, bas):
    i = metin.index(bas)
    return metin[i:metin.index('};', i) + 2]


_KOSUCU = r"""
const g = JSON.parse(HRMA_GIRDI);
function oge(id) {
  return { id, value: '', dataset: {}, textContent: '', children: [], style: {},
           appendChild(c) { this.children.push(c); },
           getAttribute(a) { return a === 'data-registry' ? g.kayit : null; } };
}
const ogeler = {};
for (const a of ['chamber_material', 'nozzle_material', 'injector_material']) {
  ogeler[a] = oge(a); ogeler[a + '_props'] = oge(a + '_props');
  ogeler[a + '_send'] = oge(a + '_send');
}
ogeler['hybridMaterialRegistry'] = oge('hybridMaterialRegistry');
global.document = {
  getElementById: (id) => ogeler[id] || null,
  createElement: () => oge(''),
  createTextNode: (t) => ({ textContent: t }),
  addEventListener: () => {},
};
global.window = global;
window.I18N = { t: (k, f) => f, tf: (k, p, f) => f.replace('{name}', p.name),
                number: (v, d) => v.toFixed(d) };
eval(g.kod);
const sonuc = {};
for (const d of g.durumlar) {
  for (const a of ['chamber_material', 'nozzle_material', 'injector_material']) {
    ogeler[a].value = d.deger[a]; ogeler[a].dataset = d.damga[a] ? {hrmaSource: d.damga[a]} : {};
  }
  malzemePaneliniYaz();
  const r = {};
  for (const a of ['chamber_material', 'nozzle_material', 'injector_material']) {
    r[a] = { satirlar: ogeler[a + '_props'].children.map(
               s => s.children.map(c => c.textContent).join('')),
             durum: ogeler[a + '_send'].textContent };
  }
  sonuc[d.ad] = r;
}
process.stdout.write(JSON.stringify(sonuc));
"""


@pytest.mark.skipif(NODE is None, reason='node yok')
class TestPanelBetigi:
    @pytest.fixture(scope='class')
    def kosu(self, kayit):
        m = _oku(SABLON)
        kod = '\n'.join([
            _islev(m, 'function i18nText('), _islev(m, 'function i18nFmt('),
            _islev(m, 'function i18nNumber('), _islev(m, 'function tasarimKaynagi('),
            "const MALZEME_ALANLARI = ['chamber_material', 'nozzle_material', 'injector_material'];",
            _sabit(m, 'const MALZEME_OZELLIK_ETIKETLERI = {'),
            _sabit(m, 'const MALZEME_SOGUTMA_ETIKETLERI = {'),
            _sabit(m, 'const MALZEME_EROZYON_ETIKETLERI = {'),
            'let malzemeKaydiOnbellek;',
            _islev(m, 'function malzemeKaydi('), _islev(m, 'function malzemeEtiketi('),
            _islev(m, 'function malzemeSecenegi('), _islev(m, 'function malzemeSatiriEkle('),
            _islev(m, 'function malzemeOzellikleriniYaz('),
            _islev(m, 'function malzemeGonderimDurumunuYaz('),
            _islev(m, 'function malzemePaneliniYaz('),
        ])
        durumlar = [
            {'ad': 'varsayilan', 'damga': {},
             'deger': {'chamber_material': 'steel_304', 'nozzle_material': 'graphite',
                       'injector_material': ''}},
            {'ad': 'kullanici', 'damga': {'chamber_material': 'user',
                                          'nozzle_material': 'project_file',
                                          'injector_material': 'user'},
             'deger': {'chamber_material': 'inconel_718', 'nozzle_material': 'copper',
                       'injector_material': 'brass'}},
            {'ad': 'damgasiz_farkli', 'damga': {},
             'deger': {'chamber_material': 'aluminum_6061', 'nozzle_material': 'tungsten',
                       'injector_material': ''}},
        ]
        girdi = {'kod': kod, 'kayit': json.dumps(kayit), 'durumlar': durumlar}
        betik = 'const HRMA_GIRDI = %s;\n%s' % (json.dumps(json.dumps(girdi)), _KOSUCU)
        r = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                           timeout=60)
        assert r.returncode == 0, r.stderr[-2000:]
        return json.loads(r.stdout)

    def test_ozellik_satirlari_kayittan(self, kosu, kayit):
        from hrma.data.materials_db import get_material
        s = kosu['varsayilan']['chamber_material']['satirlar']
        rec = get_material('ss_304')
        assert s[0] == 'Yield strength: %d MPa' % round(rec['yield_strength'] / 1e6)
        assert s[2] == 'Density: %d kg/m³' % rec['density']
        assert s[-1] == 'Source: ' + rec['source']
        n = kosu['kullanici']['nozzle_material']['satirlar']
        assert 'Cooling assumption: regeneratively cooled' in n
        assert any(x.startswith('Throat erosion: not computed') for x in n)
        i = kosu['kullanici']['injector_material']['satirlar']
        assert i[0].startswith('Yield strength: ') and i[1].startswith('Density: ')
        assert len(i) == 3                     # akma, yoğunluk, kaynak

    def test_secim_yoksa_satir_yok(self, kosu):
        assert kosu['varsayilan']['injector_material']['satirlar'] == []

    def test_gonderim_durumu_damgadan(self, kosu):
        v, k = kosu['varsayilan'], kosu['kullanici']
        assert v['chamber_material']['durum'].startswith('Not sent: the server uses this same')
        assert v['injector_material']['durum'].startswith('No material selected')
        assert k['chamber_material']['durum'] == 'Sent to the calculation: your selection.'
        assert k['nozzle_material']['durum'] == 'Sent to the calculation: from the project file.'

    def test_damgasiz_farkli_secim_gonderilmedigini_soyler(self, kosu):
        d = kosu['damgasiz_farkli']
        assert d['chamber_material']['durum'].startswith(
            'Not sent: the server will use its default (Stainless steel 304 (annealed))')
        assert d['nozzle_material']['durum'].startswith(
            'Not sent: the server will use its default (Graphite')
