"""V301/K-C2 bekçileri — katı yakıt kimliği, katalog, yanma hızı hazır ayarı,
ipuçları, etiketler ve eski proje göçü.

Kanıt ve önce/sonra: docs/scofield/raw/OH/V301/kati-sivi/K-C2/RAPOR.md.
Kalemler: KT-17, KT-18, KT-19, NK-27, NK-29, NK-52, NK-62, NK-70, K-B DEVİR 10,
N-CEA-2 Y2, K-B AÇIK 3 (eski proje akma göçü).
"""
import json
import os
import re
import shutil
from pathlib import Path

import pytest

from hrma.app import SOLID_ENDPOINT_DEFAULTS, app
from hrma.data.propellants_db import PROPELLANTS
from hrma.engines.solid_rocket_engine import (
    SOLID_CONSTRUCTOR_PROPELLANT_TYPE,
    SOLID_DEFAULT_GEOMETRY_MM,
    SOLID_DEFAULT_PROPELLANT_TYPE,
    SolidRocketEngine,
)

KOK = Path(__file__).resolve().parents[1]
SABLON = (KOK / 'hrma' / 'templates' / 'solid.html').read_text(encoding='utf-8')
SOZLUK = (KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
    encoding='utf-8')
ORTAK = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
    encoding='utf-8')
GRAFIK = (KOK / 'hrma' / 'static' / 'js' / 'i18n_charts.js').read_text(
    encoding='utf-8')
ORNEK = KOK / 'examples' / 'Example Solid KNDX BATES 75mm.hrma'

#: Sayfa biçimli en küçük gövde (geometri kipi; kimlik testte verilir).
TABAN = {'chamber_pressure': SOLID_ENDPOINT_DEFAULTS['chamber_pressure'],
         'outer_diameter': SOLID_DEFAULT_GEOMETRY_MM['chamber_diameter'],
         'core_diameter': SOLID_DEFAULT_GEOMETRY_MM['core_diameter'],
         'grain_length': SOLID_DEFAULT_GEOMETRY_MM['grain_length'],
         'grain_type': 'bates'}


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(istemci, **ek):
    r = istemci.post('/calculate_solid', json=dict(TABAN, **ek))
    return r.status_code, r.get_json()


def _kodlar(js, seviye=None):
    return {w.get('code') for w in js.get('design_warnings') or []
            if isinstance(w, dict)
            and (seviye is None or w.get('severity') == seviye)}


def _bloklar(metin):
    """i18n_pages.js EN ve TR bloklarının anahtar → değer sözlükleri."""
    sat = re.findall(r"^            '([\w.]+)': '((?:[^'\\]|\\.)*)',$", metin, re.M)
    en, tr, gor = {}, {}, set()
    for k, v in sat:
        (tr if k in gor else en)[k] = v
        gor.add(k)
    return en, tr


# --------------------------------------------------------------------------
# K-B DEVİR 10 / KT-19 — varsayılan yakıt KNDX, tek tanım, kritik bayraksız
# --------------------------------------------------------------------------
class TestVarsayilanYakit:

    def test_tek_tanim(self):
        assert SOLID_DEFAULT_PROPELLANT_TYPE == 'kndx'
        assert SOLID_ENDPOINT_DEFAULTS['propellant_type'] \
            is SOLID_DEFAULT_PROPELLANT_TYPE
        assert PROPELLANTS[SOLID_DEFAULT_PROPELLANT_TYPE]['validated'] is True
        # Kütüphane kurucusu değişmedi (doğrudan çağıranların sayıları aynı).
        assert SOLID_CONSTRUCTOR_PROPELLANT_TYPE == 'apcp'
        assert SolidRocketEngine().propellant_type == 'apcp'

    def test_ogretici_varsayilan_motor_kritik_bayraksiz(self, istemci):
        r = istemci.post('/calculate_solid', json={'use_tutorial_defaults': True})
        assert r.status_code == 200
        js = r.get_json()
        assert js['propellant_type'] == SOLID_DEFAULT_PROPELLANT_TYPE
        assert not _kodlar(js, 'critical'), _kodlar(js, 'critical')

    def test_sayfa_varsayilan_yuku_kritik_bayraksiz(self, istemci):
        """Sayfanın açılış yükü (kimlik seçiciden, termokimya gönderilmez)."""
        kayit = PROPELLANTS[SOLID_DEFAULT_PROPELLANT_TYPE]
        kod, js = _post(istemci, propellant_type=SOLID_DEFAULT_PROPELLANT_TYPE,
                        propellant_name=kayit['name'],
                        burn_rate_preset=SOLID_DEFAULT_PROPELLANT_TYPE,
                        density=kayit['density'])
        assert kod == 200, js
        assert not _kodlar(js, 'critical'), _kodlar(js, 'critical')
        assert js['thermochemistry']['source'] == 'nasa_cea_at_pc'

    def test_sayfa_acilis_satiri_ve_ad_etiketi(self, istemci):
        html = istemci.get('/solid').get_data(as_text=True)
        sec = re.search(r'<select id="propellant_type"[^>]*>(.*?)</select>',
                        html, re.S)
        assert sec, 'yakıt seçici yok'
        degerler = re.findall(r'<option value="([^"]*)"', sec.group(1))
        assert set(degerler) - {''} == set(PROPELLANTS), degerler
        secili = re.findall(r'<option value="([^"]*)" selected', sec.group(1))
        assert secili == [SOLID_DEFAULT_PROPELLANT_TYPE]
        ad = re.search(r'<input type="text" id="propellant_name" value="([^"]*)"', html)
        assert ad and ad.group(1) == PROPELLANTS[SOLID_DEFAULT_PROPELLANT_TYPE]['name']
        # ΔHc kaynaksız 2500 ile açılmaz (katalogda ΔHc yok, hesap okumaz).
        hv = re.search(r'<input type="number" id="heat_value" value="([^"]*)"', html)
        assert hv and hv.group(1) == ''


# --------------------------------------------------------------------------
# NK-29 / NK-70 — kimlik ⟷ yanma hızı yasası: karışık kayıt OLMAZ (422)
# --------------------------------------------------------------------------
class TestKarisikKayit:

    def test_apcp_kimligi_kndx_rejim_tablosu_reddedilir(self, istemci):
        kod, js = _post(istemci, propellant_type='apcp', burn_rate_preset='kndx')
        assert kod == 422, js
        assert js['error_code'] == 'burn_rate_law_propellant_mismatch'
        alan = js['invalid_fields'][0]
        assert alan['field'] == 'burn_rate_preset'
        assert alan['submitted'] == 'kndx' and alan['propellant_type'] == 'apcp'
        assert alan['accepted_values'] == ['custom']

    def test_burn_rate_law_alani_da_ayni_kapidan(self, istemci):
        kod, js = _post(istemci, propellant_type='knsb', burn_rate_law='kndx')
        assert kod == 422, js
        assert js['invalid_fields'][0]['field'] == 'burn_rate_law'
        assert js['invalid_fields'][0]['accepted_values'] == ['custom', 'knsb']

    def test_ayni_yakit_ve_custom_gecer(self, istemci):
        kod, js = _post(istemci, propellant_type='kndx', burn_rate_preset='kndx')
        assert kod == 200, js
        kod, js = _post(istemci, propellant_type='apcp', burn_rate_preset='custom')
        assert kod == 200, js
        assert js['propellant_type'] == 'apcp'
        assert 'warn.solid.piecewise_law_active' not in _kodlar(js)

    def test_ad_ile_on_ayar_celisirse_ret(self, istemci):
        kod, js = _post(istemci, propellant_name='APCP', burn_rate_preset='kndx')
        assert kod == 422, js
        assert js['error_code'] == 'propellant_identity_conflict'
        f = js['invalid_fields'][0]
        assert f['field'] == 'propellant_type'
        assert f['resolved_records']['burn_rate_preset'] == 'kndx'
        # 'APCP' adı çözücünün kendi takma ad kuralıyla kompozit kayda iner.
        assert f['resolved_records']['propellant_name'] in ('apcp', 'htpb_ap_al')

    def test_turetme_uyarisi_secici_yok_demez(self, istemci):
        kod, js = _post(istemci, propellant_name='KNDX')
        assert kod == 200
        assert 'warn.solid.propellant_type_derived' in _kodlar(js)
        assert 'no explicit propellant selector' not in ORTAK
        assert 'açık bir yakıt seçici yok' not in ORTAK

    def test_ret_cumleleri_turkce_karsilikli(self, istemci):
        for govde, kod_adi in ((dict(propellant_type='apcp', burn_rate_preset='kndx'),
                                'burn_rate_law_propellant_mismatch'),
                               (dict(propellant_name='APCP', burn_rate_preset='kndx'),
                                'propellant_identity_conflict')):
            kod, js = _post(istemci, **govde)
            assert kod == 422 and js['error_code'] == kod_adi
            desenler = re.findall(r"^\s*\[/(\^No design was published: .*?\$)/,$",
                                  GRAFIK, re.M)
            eslesen = [d for d in desenler
                       if re.match(d.replace('\\/', '/'), js['error'])]
            assert eslesen, js['error']

    def test_ornek_proje_api_yolu_degismedi(self, istemci):
        """Örnek KNDX proje dosyası API'ye: kimlik ön ayardan, 200, CEA."""
        alanlar = json.loads(ORNEK.read_text(encoding='utf-8'))['inputs']['fields']
        r = istemci.post('/calculate_solid', json=dict(alanlar))
        assert r.status_code == 200
        js = r.get_json()
        assert js['propellant_type'] == 'kndx'
        assert js['thermochemistry']['source'] == 'nasa_cea_at_pc'


# --------------------------------------------------------------------------
# Sayfa sözleşmesi (statik): seçici, ön ayar bağı, termokimya kipi, göç
# --------------------------------------------------------------------------
class TestSayfaSozlesmesi:

    def test_kimlik_seciciden_ad_yalniz_etiket(self):
        assert "propellant_type: currentPropellantKey()" in SABLON
        govde = re.search(r'function currentPropellantKey\(\) \{(.*?)\n        \}',
                          SABLON, re.S).group(1)
        assert "getElementById('propellant_type')" in govde
        assert 'burn_rate_preset' not in govde      # ön ayar kimlik değil
        assert "if (id === 'propellant_name') _selectedPropellantKey" not in SABLON

    def test_geri_yukleme_override_sayilmaz(self):
        assert 'if (solidProjectRestoring()) return;' in SABLON
        pb = (KOK / 'hrma' / 'static' / 'js' / 'project_bar.js').read_text(
            encoding='utf-8')
        assert 'isRestoring: function' in pb
        assert "'hrma:project-applied'" in pb

    def test_on_ayar_kimligi_izler(self):
        g = re.search(r'function applyPropellantRecord\(rec\) \{(.*?)\n        \}\n',
                      SABLON, re.S).group(1)
        # Eski dal: a/n'ye dokunulduysa ön ayar ESKİ yakıtta kalıyordu.
        assert 'if (preset && !brOverridden)' not in g
        assert "preset.value = 'custom';" in g

    def test_termokimya_katalog_kipinde_gonderilmez(self):
        assert '...solidThermoFields(),' in SABLON
        for id_ in ('flame_temp', 'molecular_weight', 'gamma', 'char_velocity'):
            assert ('%s: solOptNum(\'%s\')' % (id_, id_)) not in SABLON, id_
            m = re.search(r'<input type="number" id="%s"[^>]*>' % id_, SABLON)
            assert m and 'readonly' in m.group(0), id_
        assert '<option value="catalogue" selected' in re.search(
            r'<select id="thermo_source".*?</select>', SABLON, re.S).group(0)

    def test_eski_proje_gocu_uc_alan(self):
        g = re.search(r'function migrateLegacySolidProject\(fields\) \{(.*?)\n        \}\n',
                      SABLON, re.S).group(1)
        for alan in ("var_('propellant_type')", "var_('thermo_source')",
                     "var_('yield_strength_source')"):
            assert alan in g, alan
        assert "yk.value = 'user'" in g


# --------------------------------------------------------------------------
# KT-17, KT-18, NK-27, NK-52, NK-62 — metinler EN + TR
# --------------------------------------------------------------------------
YENI_ANAHTARLAR = (
    'solid.ui.propellant_catalogue_record', 'solid.ui.propellant_catalogue_record_help',
    'solid.ui.propellant_not_selected', 'solid.ui.catalogue_basis',
    'solid.ui.basis_validated', 'solid.ui.basis_not_validated',
    'solid.ui.cstar_basis_cea', 'solid.ui.cstar_basis_eq3_32',
    'solid.ui.cstar_basis_measured', 'solid.ui.cstar_basis_typical',
    'solid.ui.thermo_source', 'solid.ui.thermo_source_help',
    'solid.ui.burn_profile_progressive_regressive',
    'solid.ui.burn_profile_unrecognised',
    'solid.msg.thermo_used_line', 'solid.msg.legacy_yield_user',
    'solid.msg.throat_diameter_geometric', 'solid.msg.throat_diameter_effective',
    'solid.msg.case_length_chamber', 'solid.msg.total_motor_length',
    'solid.msg.burn_window_note', 'solid.js.suggested_vacuum_nozzle_eps',
)


class TestMetinler:

    def test_yeni_anahtarlar_en_ve_tr(self):
        en, tr = _bloklar(SOZLUK)
        for k in YENI_ANAHTARLAR:
            assert en.get(k) and tr.get(k), k
            assert en[k] != tr[k], k

    def test_yanma_profili_dorduncu_sinif(self):
        g = re.search(r'function burnProfileLabel\(p\) \{(.*?)\n        \}',
                      SABLON, re.S).group(1)
        assert "case 'progressive-regressive':" in g
        assert 'burn_profile_unrecognised' in SABLON

    @pytest.mark.parametrize('yanlis', [
        'APCP: 1500-1600', 'KNSU: 1200-1300', '2000-3000 kJ/kg', '3000-4000 kJ/kg',
        '~0.001 mm/s', '~0,001 mm/s', '20-35 g/mol', '1.2-1.3', '1,2-1,3',
        '0.003-0.008', '0,003-0,008', 'validated properties',
        'Doğrulanmış özelliklerini', 'Initial chamber temperature',
        'Ateşleme öncesi oda sıcaklığı', 'for Monte Carlo analysis',
    ])
    def test_yanlis_ipucu_sayilari_ve_iddialar_yok(self, yanlis):
        en, tr = _bloklar(SOZLUK)
        for k, v in list(en.items()) + list(tr.items()):
            if k.startswith('solid.'):
                assert yanlis not in v, (k, yanlis)

    def test_kasa_capi_ipucu_turetme_kurali(self):
        en, tr = _bloklar(SOZLUK)
        k = 'solid.ui.internal_diameter_of_the_motor_casing'
        assert 'grain outer diameter + 2·(liner + insulation)' in en[k]
        assert 'yakıt bloğu dış çapı + 2·(astar + yalıtım)' in tr[k]

    def test_sablon_yedekleri_sozlukle_ayni(self):
        en, _ = _bloklar(SOZLUK)
        for k in ('solid.ui.axial_length_of_individual_propellant_grain',
                  'solid.ui.initial_chamber_temperature_before_ignition_affe',
                  'solid.ui.rate_of_throat_diameter_increase_due'):
            m = re.search(r'data-i18n="%s">([^<]*)</span>' % re.escape(k), SABLON)
            assert m, k
            beklenen = en[k].replace("\\'", "'")
            assert m.group(1) == beklenen, k


# --------------------------------------------------------------------------
# K-B AÇIK 3 + NK-70 — canlı tarayıcı: v3.0.0 biçimli proje göçü
# --------------------------------------------------------------------------
CHROME = ('/Users/apple/Library/Caches/ms-playwright/chromium-1208/'
          'chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/'
          'Google Chrome for Testing')


def _tarayici_var():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return os.path.exists(CHROME)


# kabul_ui: yerel Mac Chromium'una bağlı tarayıcı düğümü — Linux CI'da
# SEÇİLMEZ (tests.yml -m "not kabul_ui"); packaging/release_gate.sh 5/10
# yerelde koşar (28 Eki, v3.0.5).
@pytest.mark.kabul_ui
@pytest.mark.skipif(not _tarayici_var(), reason='playwright/chromium yok')
def test_v300_projesi_elle_akma_ve_apcp_gecisi(tmp_path, monkeypatch, istemci):
    from playwright.sync_api import sync_playwright
    from tools.browser_harness.sunucu import UygulamaSunucusu

    doc = json.loads(ORNEK.read_text(encoding='utf-8'))
    doc['name'] = 'K-C2 eski akma'
    doc['inputs']['fields'] = dict(doc['inputs']['fields'],
                                   case_material='steel', yield_strength=333.0)
    (tmp_path / 'K-C2 eski akma.hrma').write_text(
        json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(tmp_path))
    with UygulamaSunucusu() as s, sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, headless=True,
                               args=['--disable-3d-apis', '--disable-gpu',
                                     '--use-gl=disabled'])
        try:
            p = b.new_page(viewport={'width': 1440, 'height': 900})
            p.set_default_timeout(30000)
            hatalar = []
            p.on('pageerror', lambda e: hatalar.append(str(e)))
            p.goto(s.temel_url + '/solid?project=' + 'K-C2%20eski%20akma')
            p.wait_for_load_state('networkidle')
            p.wait_for_function(
                "() => document.getElementById('yield_strength_source').value === 'user'")
            p.wait_for_timeout(800)
            durum = p.evaluate("""() => ({
                yuk: JSON.parse(JSON.stringify(collectAllParameters())),
                over: overriddenFieldIds(),
                kip: document.getElementById('thermo_source').value})""")
            p.select_option('#propellant_type', 'apcp')
            p.wait_for_timeout(800)
            apcp = p.evaluate(
                "() => JSON.parse(JSON.stringify(collectAllParameters()))")
        finally:
            b.close()
    assert hatalar == []
    yuk = durum['yuk']
    # Akma kaybolmaz: "Benim değerim" kipinde dosyanın değeri gider.
    assert yuk['yield_strength_source'] == 'user'
    assert yuk['yield_strength'] == 333.0
    assert yuk['propellant_type'] == 'kndx'
    # Yüklenen proje değerleri "elle değiştirildi" sayılmaz (NK-70).
    assert durum['over'] == []
    # Dosyanın termokimyası kaydın kendisi → katalog kipi (CEA).
    assert durum['kip'] == 'catalogue'
    r = istemci.post('/calculate_solid', json=yuk)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    ps = r.get_json()['safety_analysis']['pressure_safety']
    assert ps['case_yield_strength_mpa'] == pytest.approx(333.0)
    # APCP seçilince ön ayar KNDX'te kalmaz; katalog a-n çifti gider.
    assert apcp['propellant_type'] == 'apcp'
    assert apcp['burn_rate_preset'] == 'custom'
    assert apcp['burn_rate_a'] == round(PROPELLANTS['apcp']['burn_rate_a'], 7)
    r = istemci.post('/calculate_solid', json=apcp)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    js = r.get_json()
    assert js['propellant_type'] == 'apcp'
    assert 'warn.solid.piecewise_law_active' not in _kodlar(js)
