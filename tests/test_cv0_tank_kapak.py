"""ÖH V31 CV-0 · tank-kapak-kapısı bekçileri (B1 §4.3 (c); doktrin §28-42).

KUSUR (19 Eki ölçüldü; ``docs/scofield/raw/OH/V31/cv0/once.json``):
``POST /export_tank_cad`` imalat STEP/STL'ini üretiyordu. Tankın düz kapakları
gövde cidarı kalınlığıyla (3 mm, asgari imalat kalınlığı) çiziliyor, kapağın
yapısal yeterliliği HESAPLANMIYORDU (künye: "NOT computed") ve imalat kapısı
kapağa bakmıyordu. Örnek sıvı (25 kN, 30 s) oksitleyici tankı: basit mesnet
gerilmesi 2938 MPa, akma 345 MPa, SF 0,117 -> HTTP 200 ZIP. NaN, negatif,
sıfır ve dize basınçla da 200.

DÜZELTME: ``cad_visualization.tank_manufacturing_safety_refusals`` kapak
dalı (``head_sf_below_one`` / ``head_sf_not_computable``); ret gövdesi
``sf_gate_body`` sözleşmesinde, parça ``tank_head``.

KÂHİN (bu dosyada BAĞIMSIZ yazılır, ürün işlevi çağrılmaz):
Roark's Formulas for Stress and Strain, 7. baskı, Tablo 11.2, durum 10a
(r_o → 0; dış kenar basit mesnetli dairesel plaka, düzgün basınç):
    σ_maks = 3(3+ν)·q·a² / (8·t²)                (merkezde)
ve analitik çapa için durum 10b (ankastre): σ_maks = 3·q·a² / (4·t²).
Sayfa doğrulanmadı (yerel kopya yok). SF = σ_akma / σ — kapının gövde
dalının tabanı (``structural.safety_factor`` = akma / gerilme; once.json (A)
bölümünde tank kartının yayımından geri hesapla 2,5 = 2,5 ölçüldü).
q = ``structural.pressure_rating`` × ``RELIEF_VALVE_SET_PRESSURE_FACTOR``.

Bu dosya build123d'ye KAPILI DEĞİLDİR: ``/export_tank_cad`` build123d yokken
de 200 ZIP verir (STEP yerine ``STEP_NOT_AVAILABLE.txt``); STEP etiketinin
bekçisi build123d kapılı ``tests/test_v3_cad_duzeltme.py``dedir.
"""
import contextlib
import copy
import io
import json
import math
import os
import re
import shutil
import subprocess
import zipfile

import pytest

from tests.test_example_projects import (
    ENDPOINTS, HEADERS, calculate_payload, load_example_doc)

TANKLAR = ('fuel_tank', 'oxidizer_tank')

#: Kapağı YETERLİ sentetik gövdenin hedef kapak SF'si (test girdisi; ürün
#: sayısı değil). Geometri örnekle aynı kalır, yalnız işletme basıncı
#: düşürülür (σ ∝ q, yani SF ∝ 1/q).
HEDEF_SF_YETERLI = 2.0

#: SF = 1 sınırının iki yanında denenecek bağıl pay.
SINIR_PAYI = 1e-4

#: Kapının SF eşiği (``MANUFACTURING_SF_MIN``in tanımı: hesaplanan yükte
#: malzemenin sınırı). Kâhin eşiği koddan OKUMAZ; karar §28-21 (i) metni.
KARAR_SF_ESIGI = 1.0

SF_GATE_STATUS = 'manufacturing_safety_gate_closed'

#: Analitik çapa — B1 §4.1 ölçümünün oksitleyici tankı
#: (``docs/scofield/raw/OH/V31/cad-v2/olcum/tank_kapak_2026-10-19.json``).
CAPA = {'D_mm': 340.70077901959365, 't_mm': 3.0,
        'p_isletme_bar': 2.4497351206830476, 'nu': 0.33,
        'sigma_basit_mesnet_MPa': 1085.0, 'sigma_ankastre_MPa': 651.7}
#: Çapanın elle hesap yuvarlaması (MPa; brief'te 651,7 / 1085 yazılı).
CAPA_TOL_MPA = 0.05


# ---------------------------------------------------------------------------
# Kâhin ve gövde yardımcıları (başka test dosyaları da buradan okur)
# ---------------------------------------------------------------------------
def kapak_kahini(tank):
    """Tank kartından çizilen düz kapağın sayıları — ürün kodu ÇAĞRILMAZ.

    Veri kaynakları ürünle aynıdır (``materials_db`` kaydı ve emniyet
    vanası çarpanı); bağıntı ve birimler burada ayrıca yazılır (SI, metre).
    """
    from hrma.data.materials_db import get_material
    from hrma.engines.liquid_rocket_engine import (
        RELIEF_VALVE_SET_PRESSURE_FACTOR)
    mat = get_material(tank['structural']['material_key'])
    sy = float(mat['yield_strength'])                       # Pa
    nu = float(mat['poisson_ratio'])
    a = float(tank['dimensions']['diameter']) / 2.0 / 1e3   # m
    t = float(tank['dimensions']['wall_thickness']) / 1e3   # m
    q = (float(tank['structural']['pressure_rating']) * 1e5
         * RELIEF_VALVE_SET_PRESSURE_FACTOR)                # Pa
    sigma = 3.0 * (3.0 + nu) * q * a ** 2 / (8.0 * t ** 2)  # Pa
    return {'sigma_mpa': sigma / 1e6, 'sf': sy / sigma,
            'akma_mpa': sy / 1e6, 'q_bar': q / 1e5,
            't_gerekli_mm': a * math.sqrt(3.0 * (3.0 + nu) * q
                                          / (8.0 * sy)) * 1e3}


def kapagi_yeterli(pt, hedef_sf=HEDEF_SF_YETERLI):
    """Örnek tank gövdesinin AYNI geometrisi; kapak SF'si ``hedef_sf``.

    Yalnız ``structural.pressure_rating`` değişir: σ ∝ q olduğundan
    p_yeni = p · SF_eski / hedef. Dönüşte her tankın kâhin SF'si hedefe
    eşit olduğu DENETLENİR (girdinin kapağı yeterli olduğu test içinde
    hesapla gösterilir).
    """
    g = copy.deepcopy(pt)
    for ad in TANKLAR:
        st = g[ad]['structural']
        st['pressure_rating'] = (float(st['pressure_rating'])
                                 * kapak_kahini(g[ad])['sf'] / hedef_sf)
        assert kapak_kahini(g[ad])['sf'] == pytest.approx(hedef_sf,
                                                          rel=1e-12)
    return g


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('projeler')))
    os.environ.setdefault('BROWSER', 'echo')
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def ornek_tanklar(client):
    """Örnek sıvı + ``max_burn_duration`` (kartın vakası): tank bloğu."""
    from tests.test_v3_cad_duzeltme import SART_TANK_YANMA_SURESI_S
    doc = load_example_doc('liquid')
    f = dict(doc['inputs']['fields'])
    f['max_burn_duration'] = SART_TANK_YANMA_SURESI_S
    r = _sessiz(client.post, ENDPOINTS['liquid'],
                json=calculate_payload('liquid', f), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()['propellant_tanks']


def _uc(client, govde):
    return _sessiz(client.post, '/export_tank_cad',
                   json={'tank_data': govde}, headers=HEADERS)


def _kapak_kayitlari(g):
    return [x for x in g['refusals'] if x['part'] == 'tank_head']


# ---------------------------------------------------------------------------
# 1) Analitik çapa ve boyut analizi
# ---------------------------------------------------------------------------
class TestAnalitikCapa:
    def test_kahin_capayi_elle_yeniden_uretir(self):
        """651,7 / 1085 MPa (B1 §4.1) kâhinin bağıntısından yeniden çıkar."""
        from hrma.engines.liquid_rocket_engine import (
            RELIEF_VALVE_SET_PRESSURE_FACTOR as RELIEF)
        a = CAPA['D_mm'] / 2.0 / 1e3
        t = CAPA['t_mm'] / 1e3
        q = CAPA['p_isletme_bar'] * 1e5 * RELIEF
        nu = CAPA['nu']
        ss = 3.0 * (3.0 + nu) * q * a * a / (8.0 * t * t) / 1e6
        cl = 3.0 * q * a * a / (4.0 * t * t) / 1e6
        assert ss == pytest.approx(CAPA['sigma_basit_mesnet_MPa'],
                                   abs=CAPA_TOL_MPA)
        assert cl == pytest.approx(CAPA['sigma_ankastre_MPa'],
                                   abs=CAPA_TOL_MPA)

    def test_kapi_capa_gerilmesini_verir(self):
        from hrma.export.cad_visualization import tank_head_assessment
        kart = {'dimensions': {'diameter': CAPA['D_mm'],
                               'wall_thickness': CAPA['t_mm']},
                'structural': {'safety_factor': 2.5,
                               'pressure_rating': CAPA['p_isletme_bar'],
                               'material_key': 'al_2024_t3'}}
        h = tank_head_assessment('oxidizer_tank', kart)
        assert h['computed'] and h['verdict'] == 'refused'
        assert h['head_stress_mpa'] == pytest.approx(
            CAPA['sigma_basit_mesnet_MPa'], abs=CAPA_TOL_MPA)
        assert h['head_stress_mpa'] == pytest.approx(
            kapak_kahini(kart)['sigma_mpa'], rel=1e-12)
        assert h['safety_factor'] == pytest.approx(
            kapak_kahini(kart)['sf'], rel=1e-12)

    def test_boyut_analizi(self):
        """σ yalnız (a/t)² ve q ile ölçeklenir: a ve t aynı katla
        büyütülünce σ değişmez; q iki katına çıkınca σ iki kat; t iki
        katına çıkınca σ dörtte bir."""
        from hrma.export.cad_visualization import tank_head_assessment

        def s(D, t, p):
            return tank_head_assessment('fuel_tank', {
                'dimensions': {'diameter': D, 'wall_thickness': t},
                'structural': {'safety_factor': 2.5, 'pressure_rating': p,
                               'material_key': 'al_2024_t3'},
            })['head_stress_mpa']
        taban = s(300.0, 3.0, 2.0)
        assert s(3000.0, 30.0, 2.0) == pytest.approx(taban, rel=1e-12)
        assert s(300.0, 3.0, 4.0) == pytest.approx(2.0 * taban, rel=1e-12)
        assert s(300.0, 6.0, 2.0) == pytest.approx(taban / 4.0, rel=1e-12)


# ---------------------------------------------------------------------------
# 2) Önce/sonra: örnek tanklar 422, kapağı yeterli gövde 200
# ---------------------------------------------------------------------------
class TestKapakKapisi:
    def test_ornek_sivi_tanklari_422(self, client, ornek_tanklar):
        for ad in TANKLAR:
            assert kapak_kahini(ornek_tanklar[ad])['sf'] < KARAR_SF_ESIGI, (
                'ön koşul: örnek tankın çizilen kapağı yetersiz')
        r = _uc(client, ornek_tanklar)
        assert r.status_code == 422, r.status_code
        g = r.get_json()
        assert g['status'] == SF_GATE_STATUS
        assert g['message_key'] == 'out.export.sfGate.refused'
        # Örnekte gövde dalı temiz: retlerin TAMAMI kapaktan.
        assert sorted((x['part'], x['tank'], x['reason'])
                      for x in g['refusals']) == [
            ('tank_head', ad, 'head_sf_below_one') for ad in TANKLAR]
        for x in g['refusals']:
            k = kapak_kahini(ornek_tanklar[x['tank']])
            assert x['reason_key'] == (
                'out.export.sfGate.reason.head_sf_below_one')
            assert x['part_key'] == (
                f"out.export.sfGate.part.{x['tank']}_head")
            assert x['safety_factor'] == pytest.approx(k['sf'], abs=1e-4)
            assert x['head_stress_mpa'] == pytest.approx(k['sigma_mpa'],
                                                         abs=0.01)
            assert x['qualification_pressure_bar'] == pytest.approx(
                k['q_bar'], abs=1e-4)
            assert x['yield_strength_mpa'] == pytest.approx(k['akma_mpa'])
            assert x['required_head_thickness_mm'] == pytest.approx(
                k['t_gerekli_mm'], abs=1e-3)
            assert x['drawn_head_mm'] == pytest.approx(float(
                ornek_tanklar[x['tank']]['dimensions']['wall_thickness']))
        assert {f['field'] for f in g['invalid_fields']} == {
            f'{ad}.dimensions.wall_thickness' for ad in TANKLAR}

    def test_kapagi_yeterli_govde_200(self, client, ornek_tanklar):
        from hrma.export.cad_visualization import (
            tank_manufacturing_safety_refusals)
        g = kapagi_yeterli(ornek_tanklar)
        assert tank_manufacturing_safety_refusals(g) == []
        r = _uc(client, g)
        assert r.status_code == 200, r.get_data()[:400]
        assert r.headers['content-type'].startswith('application/zip')

    @pytest.mark.parametrize('kat,beklenen', [
        (1.0 + SINIR_PAYI, []),
        (1.0 - SINIR_PAYI, ['head_sf_below_one', 'head_sf_below_one'])])
    def test_sf_bir_siniri(self, ornek_tanklar, kat, beklenen):
        from hrma.export.cad_visualization import (
            tank_manufacturing_safety_refusals)
        r = tank_manufacturing_safety_refusals(
            kapagi_yeterli(ornek_tanklar, hedef_sf=kat))
        assert [x['reason'] for x in r] == beklenen

    def test_ters_mutasyon_dal_kapatilinca_eski_davranis(
            self, client, ornek_tanklar, monkeypatch):
        """Kapak dalı kapatılınca örnek tank yine 200 ZIP alır: 422'nin
        TEK nedeni kapak dalıdır (eski davranış = kusur)."""
        from hrma.export import cad_visualization as cv
        monkeypatch.setattr(cv, '_tank_head_refusals', lambda *a: [])
        r = _uc(client, ornek_tanklar)
        assert r.status_code == 200, r.get_data()[:400]

    def test_sf_yayimlamayan_tank_kapsam_disi(self):
        """Kapak dalı gövdeyle AYNI kapsamdadır (karar §28-21 (i): tank SF
        yayımlıyorsa). SF yayımlamayan gövde iki daldan da geçer."""
        from hrma.export.cad_visualization import (
            tank_head_assessment, tank_manufacturing_safety_refusals)
        kart = {'dimensions': {'diameter': 400.0, 'wall_thickness': 3.0},
                'structural': {'pressure_rating': 30.0,
                               'material_key': 'al_2024_t3'}}
        assert tank_manufacturing_safety_refusals({'fuel_tank': kart}) == []
        h = tank_head_assessment('fuel_tank', kart)
        assert h['verdict'] == 'not_engaged'
        assert h['computed'] and h['safety_factor'] < KARAR_SF_ESIGI


# ---------------------------------------------------------------------------
# 3) Girdi doğrulaması: adlı 422
# ---------------------------------------------------------------------------
class TestGirdiDogrulamasi:
    @pytest.mark.parametrize('deger,sorun', [
        (float('nan'), 'not_finite'),
        (float('inf'), 'not_finite'),
        (-2.0, 'not_positive'),
        (0.0, 'not_positive'),
        ('2.5', 'not_finite'),
        (True, 'not_finite'),
    ], ids=['nan', 'inf', 'negatif', 'sifir', 'dize', 'bool'])
    def test_gecersiz_basinc_adli_422(self, client, ornek_tanklar, deger,
                                      sorun):
        g = kapagi_yeterli(ornek_tanklar)
        g['oxidizer_tank']['structural']['pressure_rating'] = deger
        r = _uc(client, g)
        assert r.status_code == 422, r.status_code
        j = r.get_json()
        assert j['status'] == SF_GATE_STATUS
        kayit = _kapak_kayitlari(j)
        assert [(x['tank'], x['reason'], x['head_input_field'],
                 x['head_input_problem']) for x in kayit] == [
            ('oxidizer_tank', 'head_sf_not_computable',
             'oxidizer_tank.structural.pressure_rating', sorun)]
        assert {'field': 'oxidizer_tank.structural.pressure_rating',
                'reason': 'head_sf_not_computable',
                'part': 'tank_head'} in j['invalid_fields']

    @pytest.mark.parametrize('alan,deger,sorun', [
        ('dimensions.diameter', -1.0, 'not_positive'),
        ('dimensions.wall_thickness', float('nan'), 'not_finite'),
        ('structural.material_key', 'unobtainium', 'unknown_material'),
        ('structural.material_key', 'x' * 100000, 'unknown_material'),
        ('structural.material_key', ['al_2024_t3'], 'unknown_material'),
        ('structural.material_key', None, 'missing'),
        # Uçta eksik basınç kapıdan ÖNCE sözleşme kapısında adıyla
        # reddedilir (``tank_data_contract_problem``); işlev düzeyinde de
        # kapak dalı onu adıyla söyler.
        ('structural.pressure_rating', None, 'missing'),
    ], ids=['cap', 'kalinlik', 'malzeme', 'uzun-dize', 'liste', 'yok',
            'basinc-yok'])
    def test_gecersiz_girdi_adli_ve_yansitmasiz(self, alan, deger, sorun):
        from hrma.export.cad_visualization import (
            sf_gate_body, tank_manufacturing_safety_refusals)
        kart = {'dimensions': {'diameter': 300.0, 'wall_thickness': 3.0},
                'structural': {'safety_factor': 2.5, 'pressure_rating': 0.1,
                               'material_key': 'al_2024_t3'},
                'pressure_vessel': {'wall_thickness_used_mm': 3.0}}
        blok, ad = alan.split('.')
        kart[blok][ad] = deger
        r = [x for x in tank_manufacturing_safety_refusals(
            {'fuel_tank': kart}) if x['part'] == 'tank_head']
        assert [(x['reason'], x['head_input_field'], x['head_input_problem'])
                for x in r] == [('head_sf_not_computable',
                                 f'fuel_tank.{alan}', sorun)]
        govde = json.dumps(sf_gate_body(r, 'Tank CAD package'))
        assert 'unobtainium' not in govde and 'xxxxxxxx' not in govde


# ---------------------------------------------------------------------------
# 4) i18n ve ret metni
# ---------------------------------------------------------------------------
def _sozluk(dil):
    from tests.test_i18n_common import dict_block
    return dict_block(dil)


def _ornek_kayitlar():
    from hrma.export.cad_visualization import (
        tank_manufacturing_safety_refusals)
    kart = {'dimensions': {'diameter': 300.0, 'wall_thickness': 3.0},
            'structural': {'safety_factor': 2.5, 'pressure_rating': 30.0,
                           'material_key': 'al_2024_t3'},
            'pressure_vessel': {'wall_thickness_used_mm': 3.0}}
    alti = tank_manufacturing_safety_refusals({'oxidizer_tank': kart})
    kart = copy.deepcopy(kart)
    kart['structural']['pressure_rating'] = -1.0
    yok = tank_manufacturing_safety_refusals({'fuel_tank': kart})
    return {x['reason']: x for x in alti + yok}


def test_kapak_anahtarlari_en_tr_ve_yer_tutucular():
    from hrma.export import cad_visualization as cv
    en, tr = _sozluk('en'), _sozluk('tr')
    kayitlar = _ornek_kayitlar()
    assert set(kayitlar) == set(cv.TANK_HEAD_GATE_REASON_KEYS)
    for k in (list(cv.TANK_HEAD_GATE_REASON_KEYS.values())
              + list(cv.TANK_HEAD_PART_KEYS.values())):
        assert k in en and k in tr, k
        assert en[k] != tr[k], f'{k} Türkçeye çevrilmemiş'
        assert (set(re.findall(r'\{(\w+)\}', en[k]))
                == set(re.findall(r'\{(\w+)\}', tr[k]))), k
    for neden, kayit in kayitlar.items():
        yt = set(re.findall(r'\{(\w+)\}',
                            en[cv.TANK_HEAD_GATE_REASON_KEYS[neden]]))
        assert not yt - set(kayit) - {'part'}, (neden, yt - set(kayit))
        assert kayit['reason_key'] == cv.TANK_HEAD_GATE_REASON_KEYS[neden]
        assert kayit['part_key'] == cv.TANK_HEAD_PART_KEYS[kayit['tank']]
    # Sunucunun EN cümlesi kayıttan kurulur (eksik alan KeyError olurdu).
    g = cv.sf_gate_body(list(kayitlar.values()), 'Tank CAD package')
    assert 'oxidizer_tank' in g['message'] and 'fuel_tank' in g['message']


# ---------------------------------------------------------------------------
# 5) Künye: paket metinleri kapak SF'sini ve kapının hükmünü taşır
# ---------------------------------------------------------------------------
def test_paket_metinleri_kapak_sf_ve_hukmu_tasir(client, ornek_tanklar):
    g = kapagi_yeterli(ornek_tanklar)
    r = _uc(client, g)
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        cizim = json.loads(z.read('engineering_drawings.json'))
        geo = {ad: json.loads(z.read(f'{ad}_geometry.json')) for ad in TANKLAR}
    for ad in TANKLAR:
        sf = kapak_kahini(g[ad])['sf']
        for metin in (cizim['dimensions'][ad]['heads'],
                      geo[ad]['cad_instructions']['step3_boolean_cut']
                      ['result']):
            assert 'NOT computed' not in metin
            assert f'head safety factor {sf:.3f}' in metin, metin
            assert 'manufacturing safety gate: head cleared' in metin


def test_kunye_cumlesi_ham_metin_almaz():
    """Etiket cümlesi yalnız sayı ve sabit koddan kurulur."""
    from hrma.export.cad_visualization import tank_head_declaration
    zehir = '<script>alert(1)</script>'
    for h in ({'verdict': 'cleared', 'computed': True,
               'safety_factor': zehir, 'drawn_head_mm': 3.0},
              {'verdict': 'refused', 'computed': False,
               'problem_field': zehir, 'problem': zehir},
              {'verdict': zehir}, None, zehir):
        metin = tank_head_declaration(h)
        assert 'script' not in metin and isinstance(metin, str)


def test_ret_govdesi_arayuzde_turkce_basilir(client, ornek_tanklar,
                                             tmp_path):
    """Sıvı sayfası reddi ``reject_body.js`` ile sözlükten basar: kapak
    satırı Türkçe, parça adı çevrilmiş, yer tutucu açıkta kalmamış."""
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: ön yüz çözücüsü bu ortamda koşturulamaz')
    g = _uc(client, ornek_tanklar).get_json()
    govde = tmp_path / 'g.json'
    govde.write_text(json.dumps(g), encoding='utf-8')
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    betik = tmp_path / 'r.js'
    betik.write_text(r'''
const fs = require('fs'); const path = require('path');
const R = process.argv[2];
global.window = global;
global.localStorage = { getItem: () => null, setItem: () => {} };
global.document = { documentElement: { setAttribute(){}, lang: 'en' },
  addEventListener(){}, querySelectorAll: () => [], readyState: 'complete' };
global.navigator = { language: 'en' };
for (const f of ['i18n.js', 'i18n_common.js', 'reject_body.js']) {
  eval(fs.readFileSync(path.join(R, 'hrma/static/js', f), 'utf8'));
}
const g = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
window.I18N.setLang('tr');
process.stdout.write(window.HRMAReject.metni(g, 422));
''', encoding='utf-8')
    p = subprocess.run([node, str(betik), kok, str(govde)],
                       capture_output=True, timeout=60)
    metin = p.stdout.decode('utf-8')
    assert 'İmalat dışa aktarımı emniyet kapısında reddedildi' in metin, (
        metin + p.stderr.decode(errors='replace')[-400:])
    assert 'Oksitleyici tankı kapağı (oxidizer_tank):' in metin
    assert 'Yakıt tankı kapağı (fuel_tank):' in metin
    assert metin.count('1,0 değerinin altında') == 2
    assert 'Roark Tablo 11.2 durum 10a' in metin
    assert 'refused' not in metin, 'TR kipinde İngilizce cümle kaldı'
    assert not re.search(r'\{\w+\}', metin), 'açıkta yer tutucu kaldı'
