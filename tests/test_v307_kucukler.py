# -*- coding: utf-8 -*-
"""V307/KÜÇÜKLER bekçileri (18 Kas 2026) — dünkü kulvarların devrettiği
küçük görünür hatalar. Kanıt: docs/scofield/raw/OH/V307/kucukler/RAPOR.md.

Bu dosya FİZİĞİ ve SÖZLEŞMEYİ kilitler, bugünkü çıktıyı değil.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

import tests.test_v307_sekme_guverte as SG
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None,
                                  reason='node yok: panel ölçümü koşamaz')


def _oku(p):
    return pathlib.Path(p).read_text(encoding='utf-8')


def _sozluk_degeri(dosya, anahtar):
    """i18n dosyasındaki EN ve TR değer (sırayla). Bulunamazsa []."""
    s = _oku(dosya)
    return re.findall(r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'", s)


# ---------------------------------------------------------------- kalem 3
# YAPISAL, doğrulama kipi: sekmenin gereken cidarının gerilme modeli
# (``sizing_stress_model``) motorun cidarı benimsendiğinde de yayımlanır.

def test_k3_dogrulama_kipinde_boyutlandirma_modeli_yayimlanir():
    """Fizik: ince kullanıcı cidarı ince cidar modeliyle değerlendirilir,
    önerilen (kalın) cidar Lamé'yle boyutlanır. İki model farklı ve ikisi de
    adıyla yayımlanır; önerilen cidar Lamé kapalı biçimiyle aynı sayıdır."""
    from hrma.analysis.structural_analysis import (
        StructuralAnalyzer, THIN_WALL_T_OVER_R_LIMIT)
    A = StructuralAnalyzer()
    motor = {'chamber_pressure': 105.0, 'chamber_diameter': 0.104,
             'chamber_length': 0.4, 'throat_diameter': 0.03,
             'exit_diameter': 0.06, 'chamber_temperature': 300.0}
    boyut = A.analyze_structure(dict(motor), material='aluminum_6061',
                                design_safety_factor=2.5)['chamber_analysis']
    assert boyut['design_mode'] == 'size'
    dogrula = A.analyze_structure(dict(motor), material='aluminum_6061',
                                  design_safety_factor=2.5,
                                  actual_wall_thickness=0.004)['chamber_analysis']
    assert dogrula['design_mode'] == 'verify'
    # Önerilen cidar iki kipte aynı sayı, modeli de aynı (yayımlanır).
    assert dogrula['minimum_thickness'] == boyut['minimum_thickness']
    assert dogrula['sizing_stress_model'] == boyut['sizing_stress_model']
    r = motor['chamber_diameter'] / 2
    beklenen = ('lame_thick_wall'
                if boyut['minimum_thickness'] / 1000 / r >= THIN_WALL_T_OVER_R_LIMIT
                else 'thin_wall')
    assert dogrula['sizing_stress_model'] == beklenen


#: Mühendis turu katı L2 (70 bar, 6061; GÜVERTE-ORTAM kalem 5'in vakası):
#: sekmenin gereken cidarı kalın cidar rejiminde (Lamé) boyutlanır.
KATI_L2 = KOK / 'docs/scofield/raw/OH/V306/muhendis-turu/kati/vakalar/L2.json'


def _kati_l2_govdesi():
    d = json.loads(_oku(kanit_gerekli(KATI_L2)))
    return [i['govde'] for i in d['istekler'] if i['uc'] == '/calculate_solid'][0]


@pytest.fixture(scope='module')
def kati_yapisal():
    motor = SG._motor_yaniti('solid', {'__govde__': _kati_l2_govdesi()})
    sug = SG._node('solid', motor, ['structural'])['structural']
    yuk, eksik = SG._yuk(sug, sug.get('suggested'))
    assert not eksik, eksik
    kod, yanit = SG._uc('/analyze_structural_safety', yuk)
    assert kod == 200, str(yanit)[:300]
    ren = SG._node('solid', motor, ['structural'],
                   data={'structural': yanit})['structural']
    return yanit, ren['html']


@node_gerekli
def test_k3_panel_ikinci_nedeni_gerilme_modeliyle_yazar(kati_yapisal):
    """Katı L2: motorun cidarı benimsenir (doğrulama kipi), sekmenin gereken
    cidarı Lamé'yle boyutlanır; uç modeli yayımlar, panel ikinci nedeni yazar."""
    yanit, html = kati_yapisal
    ca = yanit['structural_analysis']['chamber_analysis']
    gor = SG._gorunur(html)
    assert ca['design_mode'] == 'verify'
    assert ca['sizing_stress_model'] == 'lame_thick_wall'
    en = _sozluk_degeri(JS / 'i18n_common.js', 'panel.structural.wallDefinitionsLame')
    assert len(en) == 2 and en[0] != en[1]
    assert 'Why the two required walls differ' in gor
    assert en[0].replace("\\'", "'") in gor


# ---------------------------------------------------------------- kalem 2
# Varsayılan tank yeri: Fırlatma Sahası formunun sıra seçenekleri ve
# varsayılanı (ilk seçenek) motor sayfasının 6-DOF formuyla aynı.

def _motor_sayfasi_siralari():
    s = _oku(JS / 'calkanti_panel.js')
    i = s.index('const siralar = mt === ')
    blok = s[i:s.index(';', i)]
    sivi = blok[:blok.index("\n            : [")]
    hibrit = blok[blok.index("\n            : ["):]
    deger = lambda b: re.findall(r"\[\s*'([^']*)',\s*'", b)
    return {'liquid': deger(sivi), 'hybrid': deger(hibrit)}


def _fs_siralari():
    s = _oku(SABLON)
    i = s.index('var CALKANTI_SIRALARI = {')
    blok = s[i:s.index('};', i)]
    out = {}
    for mt in ('liquid', 'hybrid'):
        j = blok.index(mt + ':')
        k = blok.index(']]', j)
        out[mt] = re.findall(r"\[\s*'([^']*)',\s*'panel", blok[j:k + 2])
    return out


def test_k2_fs_varsayilan_tank_yeri_motor_sayfasiyla_ayni():
    ms, fs = _motor_sayfasi_siralari(), _fs_siralari()
    assert ms == {'liquid': ['oksitleyici,yakit', 'yakit,oksitleyici', ''],
                  'hybrid': ['n2o', '']}, ms
    # Aynı seçenekler, aynı sıra; varsayılan (ilk seçenek) aynı ve boş değil:
    # kullanıcı hiçbir şey girmeden iki sayfa aynı bloğu gönderir.
    assert fs == ms
    assert all(v[0] for v in fs.values())
    # Formun ilk seçeneği seçili kurulur (select'in varsayılanı) ve yer
    # kaynağı varsayılanı ardışık dizilim.
    saha = _oku(SABLON)
    i = saha.index('function calkantiFormunuKur()')
    blok = saha[i:saha.index('function calkantiDuzeni()', i)]
    assert 'selected' not in blok
    assert blok.index('value="ardisik"') < blok.index('value="istasyon"')
    # Not metni artık "yer girilmezse rijit" demiyor (varsayılan bağlar).
    for dil_degeri in _sozluk_degeri(JS / 'i18n_launch_site.js', 'site.sloshFormNote'):
        assert 'without a location' not in dil_degeri
        assert 'yer girilmezse' not in dil_degeri


# ---------------------------------------------------------------- kalem 1
# Fırlatma Sahası izleme ekranı ve küre yolu: çalkantı bağlaşık koşusunun
# doğrusal sınırdan sonraki bölümü (UÇUŞ-GÖVDE yayım kuralı, yanıtın
# ``calkanti.yayim``; HUKUM_SOZLESMESI §11) işaretli.

import tests.test_v307_fs_izleme as FI

YAYIM_ASILDI = {'kosu_turu': 'BAGLASIK', 'gecerlilik': 'DOGRUSAL_MODEL_GECERLILIGI_DISINDA',
                'neden_kodu': 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', 't_ilk_asim_s': 3.0,
                'tank_id_ilk_asim': 'oksitleyici'}
YAYIM_GECERLI = dict(YAYIM_ASILDI, gecerlilik='GECERLI', neden_kodu=None)

_IZ = """
const n = C.normalizeSozlesme(G);
const ev = C.olaylar(n.iz);
console.log(JSON.stringify({ok: n.ok, gec: n.iz.gecerlilik, ev: ev}));
"""


@node_gerekli
def test_k1_sinir_sonrasi_olaylar_isaretli_sayisi_basilmaz():
    soz = FI.sozlesme()
    soz['slosh_publication'] = YAYIM_ASILDI
    out = FI.node_kos(_IZ, soz)
    assert out['ok'] and out['gec']['t'] == 3.0
    ev = {e['anahtar']: e for e in out['ev']}
    # Sınırdan önceki olaylar değişmedi; sonrakiler (apoje 5 s, iniş 14 s)
    # işaretli ve sayısız; sınır anı yanıtın ilk aşım zamanıyla ayrı olay.
    for k in ('liftoff', 'burnout', 'maxq'):
        assert not ev[k].get('gecersiz'), k
    assert ev['maxq']['deger'] == 8800.0
    assert ev['apogee']['gecersiz'] is True and ev['apogee']['deger'] is None
    assert ev['impact']['gecersiz'] is True
    assert not ev['impact'].get('zamanGecerli')
    assert ev['limit']['t'] == 3.0 and ev['limit']['alan'] == 'slosh_publication.t_ilk_asim_s'
    assert C_RENK()['limit'] == 0xff3d00


def C_RENK():
    return FI.node_kos('console.log(JSON.stringify(C.OLAY_RENGI));', {})


@node_gerekli
@pytest.mark.parametrize('yayim', [None, YAYIM_GECERLI])
def test_k1_sinir_asilmadiysa_iz_bugunku_gibi(yayim):
    soz = FI.sozlesme()
    once = FI.node_kos(_IZ, soz)
    if yayim is not None:
        soz['slosh_publication'] = yayim
    sonra = FI.node_kos(_IZ, soz)
    assert sonra['gec'] is None
    assert sonra['ev'] == once['ev']


@node_gerekli
def test_k1_seri_yolunda_apoje_null_nedeni_adiyla():
    # summary.apogee null (UÇUŞ-GÖVDE yayım kuralı) -> apoje satırı kalır,
    # zamanı/sayısı yok, neden 'gecersiz'; neden kodu yoksa 'yok'.
    y = FI.seri_yaniti()
    y['summary']['apogee'] = None
    y['summary']['apogee_time'] = None
    for pub, neden in ((YAYIM_ASILDI, 'gecersiz'), (None, 'yok')):
        g = dict(y, slosh_publication=pub)
        out = FI.node_kos('const n = C.normalize(G); console.log(JSON.stringify(C.olaylar(n.iz)));', g)
        ap = [e for e in out if e['anahtar'] == 'apogee']
        assert len(ap) == 1 and ap[0]['zamanYok'] is True, out
        assert ap[0]['apogeeNeden'] == neden
        assert ('limit' in [e['anahtar'] for e in out]) == (pub is not None)


def test_k1_sayfa_kure_ve_izleme_ayni_kayittan_okur():
    saha = _oku(SABLON)
    kure = _oku(JS / 'launch_site_globe.js')
    izleme = _oku(JS / 'launch_site_tracking.js')
    # Sözleşme yanıtın yayım kaydını aynen taşır (sayfada hesap yok).
    assert 'slosh_publication: (d.calkanti && d.calkanti.yayim' in saha
    assert "y.neden_kodu !== 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI'" in saha
    assert 'globe.opts.invalidFromTime = ucusGecerlilikSiniri;' in saha
    # Kürede sınır işaretçisi ve sınır sonrası katman; renk izlemeyle aynı.
    assert "add(kLim, 0xff3d00, 'limit', this)" in kure
    assert 'this._invalidLine = new THREE.Line(' in kure
    assert "GECERLILIK_DISI_NEDENI = 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI'" in izleme
    # Canlı okuma ve olay listesi işaretli; çözüm sonu / apoje sayısı yok.
    i = saha.index('function updatePlayUI(')
    blok = saha[i:saha.index('function renderEvents(', i)]
    assert "classList.toggle('ls-gecersiz', gecDisi)" in blok
    assert "el('ls-range').textContent = t('site.trackOutsideValidity'" in blok
    for anahtar in ('site.trackLinearLimit', 'site.trackOutsideValidity', 'site.trackInvalidAfter',
                    'site.liveOutsideValidity', 'site.trackApogeeWithheld',
                    'site.trackApogeeNotPublished'):
        v = _sozluk_degeri(JS / 'i18n_launch_site.js', anahtar)
        assert len(v) == 2 and v[0] != v[1], anahtar


# ---------------------------------------------------------------- kalem 5
# ISIL KORUMA ``T_initial_K``: tanım değeri boş, ısı kuyusunda zorunlu,
# motorun yayımladığı cidar başlangıç sıcaklığından tohumlanır.

def test_k5_isi_kuyusu_baslangic_sicakligi_zorunlu_adli_422():
    from hrma.app import app, thermal_protection_form_contract
    assert 'T_initial_K' in thermal_protection_form_contract()['heat_sink']
    govde = {'mode': 'heat_sink', 'h_gas_W_m2K': 3000.0, 'T_recovery_K': 3200.0,
             'burn_time_s': 10.0, 'wall_thickness_m': 0.005}
    r = app.test_client().post('/api/thermal-protection', json=govde)
    assert r.status_code == 422
    assert r.get_json()['missing_fields'] == ['T_initial_K']
    # Verilince eski örtük değerle bit-aynı (300 K açık yazıldı).
    from hrma.analysis.thermal_protection import ThermalProtectionAnalyzer
    import inspect
    imza = inspect.signature(ThermalProtectionAnalyzer.heat_sink_transient)
    assert imza.parameters['T_initial_K'].default == 300.0   # çekirdek değişmedi
    r2 = app.test_client().post('/api/thermal-protection', json=dict(govde, T_initial_K=300.0))
    assert r2.status_code == 200


@node_gerekli
def test_k5_panel_tanim_degeri_bos_ve_motor_tohumu():
    import tests.test_v307_guverte_isil as GI
    ev = GI._node('liquid', None, ['protection'])['protection']
    assert {f[0]: f[2] for f in ev['fields']}['T_initial_K'] == ''
    # Hibrit: motor ısıl koruma geçmişinin başlangıç sıcaklığını yayımlıyor.
    motor = SG._motor_yaniti('hybrid', {'__govde__': SG.HIBRIT_L1_GOVDE})
    beklenen = motor['motor']['thermal_protection']['wall_temperature_history']['T_initial_K']
    sug = GI._node('hybrid', motor, ['protection'])['protection']['suggested']
    assert sug['T_initial_K'] == beklenen
    # Katı motor yayımlamıyor: tohum yok (alan boş kalır, kip zorunlu kılar).
    motor_k = SG._motor_yaniti('solid', {})
    sug_k = GI._node('solid', motor_k, ['protection'])['protection']['suggested']
    assert 'T_initial_K' not in sug_k


# ---------------------------------------------------------------- kalem 8
# Katı .eng dosyasında test ortamı yorum satırı (sıvıdaki GÜVERTE-ORTAM
# kalem 4 deseni). Deniz seviyesi testinde dosya bugünküyle aynı.

def _kati_yaniti(ek):
    return SG._motor_yaniti('solid', ek)


def _eng_dosyasi(r):
    from hrma.app import app
    js = app.test_client().post('/api/export-eng',
                                json={'motor_data': dict(r, motor_name='KK')}).get_json()
    assert js['status'] == 'success', js
    return js


def _eng_metni(js):
    for k in ('eng_content', 'content', 'eng'):
        if isinstance(js.get(k), str):
            return js[k]
    raise AssertionError(sorted(js))


def test_k8_kati_eng_test_ortami_satiri():
    deniz = _kati_yaniti({})
    assert deniz['design_ambient']['is_sea_level'] is True
    d_metin = _eng_metni(_eng_dosyasi(deniz))
    assert '; test ambient' not in d_metin
    irtifa = _kati_yaniti({'test_altitude': 10000, 'atm_pressure': None})
    da = irtifa['design_ambient']
    assert da['is_sea_level'] is False and da['source'] == 'test_altitude_isa'
    metin = _eng_metni(_eng_dosyasi(irtifa))
    satir = [s for s in metin.splitlines() if s.startswith('; test ambient')]
    assert len(satir) == 1, metin[:2000]
    assert ('%.0f m test altitude' % da['altitude_m']) in satir[0]
    assert ('%.4f bar' % da['pressure_bar']) in satir[0]
    assert 'NOT at sea level' in satir[0]
    if not da['sea_level_flow_separated']:
        assert ('total impulse %.1f N-s' % da['total_impulse_sea_level_ns']) in metin
    # Satırlar ASCII (RASP yorum satırı).
    assert all(ord(c) < 128 for s in metin.splitlines() if s.startswith(';') for c in s)


# ---------------------------------------------------------------- kalem 6
# Güvenlik paneli zorunlu kümesi tek kaynaktan: sunucu = şablon = panel.

@node_gerekli
def test_k6_guvenlik_zorunlu_kumesi_sunucu_sablon_panel_ayni():
    from hrma.app import app, SAFETY_REQUIRED_FIELDS
    from tests.support import guvenlik_meta as GM
    assert json.loads(GM.guvenlik_metasi()) == list(SAFETY_REQUIRED_FIELDS)
    # Uç: boş gövdeye yanıt = küme (sırasıyla).
    r = app.test_client().post('/analyze_safety', json={})
    assert r.status_code == 422
    assert r.get_json()['missing_fields'] == list(SAFETY_REQUIRED_FIELDS)
    # Panel aynı kümeyi okur (şablon meta); kendi dosyasında liste yok.
    ev = SG._node('liquid', None, ['safety'])['safety']
    assert ev['required'] == list(SAFETY_REQUIRED_FIELDS)
    assert 'thrust' not in ev['required'] and 'propellant_mass' in ev['required']
    src = _oku(JS / 'panels' / 'safety_panel.js')
    assert not re.search(r"required:\s*\[", src)
    # Üç sayfa da etiketi basar.
    for sayfa in ('/liquid', '/solid', '/hybrid'):
        g = app.test_client().get(sayfa, headers={'Host': '127.0.0.1:8080'})
        assert 'name="hrma-safety-required"' in g.get_data(as_text=True), sayfa


# ---------------------------------------------------------------- kalem 7
# /api/flow-analysis: fizik dışı oda sıcaklığı adlı 422 (eskiden 400 + ham cümle).

@pytest.mark.parametrize('deger', [-3000.0, 0.0])
def test_k7_akis_fizik_disi_sicaklik_adli_422(deger):
    from hrma.app import app
    govde = {'chamber_pressure': 30.0, 'chamber_temperature': deger, 'gamma': 1.2,
             'molecular_weight': 22.0, 'throat_diameter': 0.03,
             'ambient_pressure': 101325.0, 'expansion_ratio': 8.0}
    r = app.test_client().post('/api/flow-analysis', json=govde)
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'invalid_flow_input'
    assert [f['field'] for f in j['invalid_fields']] == ['chamber_temperature']
    assert 'must be positive' not in str(j)
    # Sağlıklı gövde aynı uçtan 200.
    ok = app.test_client().post('/api/flow-analysis', json=dict(govde, chamber_temperature=3000.0))
    assert ok.status_code == 200
