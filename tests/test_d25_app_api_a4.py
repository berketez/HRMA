# -*- coding: utf-8 -*-
"""ÖH D25 / app-api aşama-4 bekçileri — P07 uçları + P16 sınır turu.

Kapsanan kalemler:

* **P7B2-04** — ``/api/altitude-to-pressure`` geçerlilik bandının ALT ucu.
  D24 ÜST ucu kapatmıştı; alt uçta HTTP 200 ile 6.500.288 K ve 7,69e22 bar
  yayımlanıyordu.
* **P16B3-16** — bool tipi bölgede yanlış gerekçeli 400
  (``/api/flow-analysis``: ``chamber_pressure: true`` -> "ambient_pressure
  must be below chamber_pressure").
* **P16B3-18** — ``/api/analysis/wall-profile`` ``burn_time`` ve (boğaz
  verildiğinde) ``mdot_total`` sessizce yutuluyordu.
* **P7B3-30 (ŞART, Fable-D19)** — panel gövdesi + FEA zinciri ölçümünün
  düzeltilmiş hâli bekçiye bağlandı.
* **P16S1-02 / P16S1-03** — uç katmanındaki varsayılanlı sayı okumaları ve
  iki katmanlı onarım sırası kısıtı: ENVANTER MANDALI (ratchet).
* **P16B4-10 / -11 / -12, P7B3-04** — ölçümle ÇÜRÜTÜLDÜ; bir daha
  dirilmesin diye hükmü sabitleyen bekçiler.

Ölçüm artefaktları: ``docs/scofield/raw/OH/D25/app-api/a4/``.
"""
import contextlib
import io
import json
import math
import os
import re

import pytest

from hrma.app import app
from hrma.constants import ISA_TABLE_BOTTOM_M, ISA_TABLE_TOP_M

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


@pytest.fixture(scope='module')
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ===========================================================================
# P7B2-04 — irtifa bandının ALT ucu
# ===========================================================================
class TestP7B204BandinAltUcu:
    """Tablo altında SAYI YAYIMLANMAZ; tablo içinde gövde BİT-AYNI."""

    def _kos(self, client, h):
        r = _quiet(client.post, '/api/altitude-to-pressure',
                   json={'altitude': h})
        return r.status_code, (r.get_json() or {})

    @pytest.mark.parametrize('h', [-5000.001, -10000.0, -1e6, -1e9])
    def test_tablo_altinda_hicbir_sayi_yayimlanmaz(self, client, h):
        kod, j = self._kos(client, h)
        assert kod == 422, f'h={h} -> {kod}: {str(j)[:200]}'
        assert j['error'] == 'altitude_outside_model'
        # Fail-closed: reddedilen istekte basınç/sıcaklık YOKTUR.
        assert 'pressure' not in j, j
        assert 'temperature' not in j, j
        # Alan ADIYLA söylenir.
        assert j['invalid_fields'][0]['field'] == 'altitude'
        assert j['invalid_fields'][0]['reason'] == 'outside_model_range'
        # Bant iki ucuyla birlikte beyan edilir.
        assert j['tabulated_from_m'] == ISA_TABLE_BOTTOM_M
        assert j['tabulated_to_m'] == ISA_TABLE_TOP_M

    def test_alt_ucta_uydurma_sicaklik_gitti(self, client):
        """ÖLÇÜLDÜ (taban cdf2106): −1e9 m -> 200 + 6.500.288,15 K."""
        kod, j = self._kos(client, -1e9)
        assert kod == 422
        assert '6500288' not in json.dumps(j)

    @pytest.mark.parametrize('h,T', [
        (0.0, 288.15),          # deniz seviyesi
        (-430.0, None),         # Ölüdeniz — bandın İÇİNDE
        (-154.0, None),         # Turfan çukuru
        (-4999.0, None),        # tablo tabanının hemen üstü
        (11000.0, None),
        (84852.0, None),
    ])
    def test_bandin_icinde_bit_ayni(self, client, h, T):
        kod, j = self._kos(client, h)
        assert kod == 200, f'h={h} -> {kod}: {str(j)[:200]}'
        assert sorted(j.keys()) == ['altitude', 'pressure', 'temperature'], j
        assert math.isfinite(j['pressure']) and j['pressure'] > 0
        if T is not None:
            assert j['temperature'] == pytest.approx(T, abs=1e-9)

    def test_sinir_deponun_tek_kaynagi(self, client):
        """Eşik İCAT EDİLMEDİ: hrma.constants'tan gelir."""
        src = open(os.path.join(KOK, 'hrma', 'app.py'),
                   encoding='utf-8').read()
        # Uçta çıplak -5000 literali YOK; sabit adıyla kullanılıyor.
        # ÖH D33-2 / app-api-uc a1 (D31 dersi 22 — KESİK DİLİM): pencere
        # ``i + 6000`` idi ve fonksiyona satır eklendikçe ölçtüğü kodu
        # kapsam DIŞINDA bırakıp sessizce yeşile dönebiliyordu (bu dalgada
        # gerçekten kırmızıya düştü). Dilim artık fonksiyonun GERÇEK
        # sonuna bağlı.
        i = src.index("def altitude_to_pressure")
        j = src.find('\n@app.route(', i)
        assert j > i, 'altitude_to_pressure sonu bulunamadı'
        govde = src[i:j]
        assert 'ISA_TABLE_BOTTOM_M' in govde
        assert re.search(r'h\s*<\s*ISA_TABLE_BOTTOM_M', govde), govde[:200]

    def test_ust_uc_bozulmadi(self, client):
        """D24'ün onarımı yerinde: taşan irtifa hâlâ 422."""
        kod, j = self._kos(client, 1e9)
        assert kod == 422
        assert j['error'] == 'altitude_outside_model'
        kod, j = self._kos(client, 100000.0)
        assert kod == 200
        assert j['model_regime'] == 'isothermal_extension_above_table_top'


# ===========================================================================
# P16B3-16 — bool tuzağı ve YANLIŞ GEREKÇE
# ===========================================================================
_BOOL_TABAN = {
    '/analyze_thermal_safety': {'chamber_pressure': 50,
                                'chamber_temperature': 3000,
                                'material': 'steel', 'wall_thickness': 0.005},
    '/analyze_structural_safety': {'chamber_pressure': 50,
                                   'chamber_diameter': 0.15,
                                   'material': 'steel',
                                   'wall_thickness': 0.005},
    '/api/six-dof-analysis': {'dry_mass': 20, 'thrust': 5000,
                              'burn_time': 5},
    '/analyze_safety': {'chamber_pressure': 50, 'propellant_mass': 10,
                        'chamber_diameter': 0.15, 'wall_thickness': 0.005,
                        'propellant_type': 'APCP'},
    '/api/analysis/wall-profile': {'chamber_pressure': 50,
                                   'chamber_temperature': 3000,
                                   'material': 'steel',
                                   'wall_thickness': 0.005},
    '/api/flow-analysis': {'chamber_pressure': 50,
                           'chamber_temperature': 3000,
                           'throat_diameter': 0.04, 'exit_diameter': 0.09},
}


class TestP16B316BoolTuzagi:
    """Aynı ``true`` hiçbir uçta sayıya dönüşmez ve gerekçe DOĞRU alanı söyler."""

    def test_flow_analysis_yanlis_gerekce_gitti(self, client):
        """ÖLÇÜLDÜ (taban cdf2106): 400 + 'ambient_pressure must be below…'."""
        g = dict(_BOOL_TABAN['/api/flow-analysis'], chamber_pressure=True)
        r = _quiet(client.post, '/api/flow-analysis', json=g)
        j = r.get_json() or {}
        assert r.status_code == 400, str(j)[:200]
        # Suçlanan alan ARTIK doğru olan.
        assert j['invalid_fields'][0]['field'] == 'chamber_pressure'
        assert j['invalid_fields'][0]['reason'] == 'not_a_number'
        # Ve YANLIŞ gerekçe artık yok.
        assert 'ambient_pressure must be below' not in json.dumps(j)

    @pytest.mark.parametrize('alan', [
        'chamber_pressure', 'chamber_temperature', 'gamma',
        'molecular_weight', 'throat_diameter', 'ambient_pressure',
        'n_stations', 'wall_temperature',
    ])
    def test_flow_analysis_her_alanda_bool_reddedilir(self, client, alan):
        g = dict(_BOOL_TABAN['/api/flow-analysis'])
        g[alan] = True
        r = _quiet(client.post, '/api/flow-analysis', json=g)
        j = r.get_json() or {}
        assert r.status_code == 400, f'{alan} -> {r.status_code}'
        assert j['invalid_fields'][0]['field'] == alan, j
        assert j['invalid_fields'][0]['reason'] == 'not_a_number'

    @pytest.mark.parametrize('uc,alan', [
        ('/analyze_thermal_safety', 'chamber_pressure'),
        ('/analyze_structural_safety', 'chamber_pressure'),
        ('/api/six-dof-analysis', 'dry_mass'),
        ('/analyze_safety', 'chamber_pressure'),
        ('/api/analysis/wall-profile', 'chamber_pressure'),
    ])
    def test_kardes_uclar_422_kalmali(self, client, uc, alan):
        """D23/D24'te kazanılan 422'ler bozulmadı."""
        g = dict(_BOOL_TABAN[uc])
        g[alan] = True
        r = _quiet(client.post, uc, json=g)
        assert r.status_code == 422, f'{uc}::{alan} -> {r.status_code}'

    def test_hicbir_uc_bool_u_1_e_cevirip_200_vermez(self, client):
        for uc, taban in _BOOL_TABAN.items():
            alan = next(iter(taban))
            g = dict(taban)
            g[alan] = True
            r = _quiet(client.post, uc, json=g)
            assert r.status_code != 200, f'{uc}::{alan} sessizce geçti'

    def test_bool_denetimi_float_cagrisindan_once(self, client):
        """``isinstance(True, int)`` doğrudur; sıra bozulursa kapı ölür."""
        src = open(os.path.join(KOK, 'hrma', 'app.py'),
                   encoding='utf-8').read()
        i = src.index('def _flow_float')
        govde = src[i:i + 4000]
        assert govde.index('isinstance(value, bool)') < govde.index(
            'value = float(value)')


# ===========================================================================
# P16B3-18 — yutulan girdi ADIYLA ilan edilir
# ===========================================================================
_WP = {'chamber_pressure': 50, 'chamber_temperature': 3000,
       'chamber_diameter': 0.15, 'chamber_length': 0.6,
       'material': 'steel', 'wall_thickness': 0.005}


def _wp(client, **ek):
    r = _quiet(client.post, '/api/analysis/wall-profile',
               json=dict(_WP, **ek))
    return r.status_code, (r.get_json() or {})


class TestP16B318YutulanGirdi:

    def test_burn_time_yutuldugu_soylenir(self, client):
        kod, j = _wp(client, throat_diameter=0.04, mdot_total=1.0,
                     burn_time=10)
        assert kod == 200, str(j)[:200]
        alanlar = {b['field'] for b in j.get('inputs_not_used', [])}
        assert 'burn_time' in alanlar, j.get('inputs_not_used')

    def test_burn_time_gercekten_hicbir_sayiyi_oynatmiyor(self, client):
        """Beyanın gerekçesi ÖLÇÜLEBİLİR olmalı, yoksa beyan boş laf."""
        imza = []
        for bt in (1, 10, 300):
            kod, j = _wp(client, throat_diameter=0.04, mdot_total=1.0,
                         burn_time=bt)
            assert kod == 200
            imza.append(json.dumps(j['wall_profile'], sort_keys=True))
        assert len(set(imza)) == 1, 'burn_time artık etkili — beyan yalan'

    def test_mdot_bogaz_verilince_yutulur_ve_ilan_edilir(self, client):
        kod, j = _wp(client, throat_diameter=0.04, mdot_total=50,
                     burn_time=10)
        assert kod == 200
        kayit = next(b for b in j['inputs_not_used']
                     if b['field'] == 'mdot_total')
        assert kayit['reason'] == 'overridden_by_supplied_geometry'
        assert kayit['used_by_model'] is None
        assert kayit['submitted'] == 50

    def test_mdot_bogaz_verilince_gercekten_atil(self, client):
        imza = []
        for m in (1, 50):
            kod, j = _wp(client, throat_diameter=0.04, mdot_total=m,
                         burn_time=10)
            assert kod == 200
            imza.append(json.dumps(j['wall_profile'], sort_keys=True))
        assert len(set(imza)) == 1, 'mdot artık etkili — beyan yalan'

    def test_mdot_bogazsiz_ETKILI_oldugu_icin_ilan_edilmez(self, client):
        """Kalemin 'hiçbir çıktıyı değiştirmiyor' ayağı ÇÜRÜK: boğaz
        gönderilmezse debi boğazı ve akıyı belirler."""
        sonuc = {}
        for m in (1, 50):
            kod, j = _wp(client, expansion_ratio=4.0, mdot_total=m,
                         burn_time=10)
            assert kod == 200, str(j)[:200]
            wp = j['wall_profile']
            sonuc[m] = (wp['throat_diameter_m'],
                        max(x for x in wp['q_MW']
                            if isinstance(x, (int, float))))
            # Etkili olduğu için beyan EDİLMEZ.
            alanlar = {b['field'] for b in j.get('inputs_not_used', [])}
            assert 'mdot_total' not in alanlar, j.get('inputs_not_used')
        assert sonuc[1][0] != sonuc[50][0], sonuc
        assert sonuc[1][1] != sonuc[50][1], sonuc

    def test_burn_time_kullanilmadigi_halde_ZORUNLU_ve_bantli(self, client):
        """Kalemin en sert ayağı: uç, hiç kullanmadığı alanı ŞART koşuyor.

        ÖLÇÜLDÜ (taban ``cdf2106``): ``burn_time`` gönderilmezse
        422 ``incomplete_wall_profile_input`` (``missing_fields:
        ['burn_time']``); 500 s gönderilirse 422 ``out_of_range``
        (``accepted_range [0, 300]``; ÖH D27 a2'ye kadar bu ad
        ``allowed_range`` idi, OH-D25-23 ile kanona geçti) — oysa 1 s
        ile 300 s arasında
        yayımlanan profil BİT-AYNIDIR. Beyan bu çelişkiyi kullanıcıya
        SÖYLER; kapılar (ÖK-22) gevşetilmez.
        """
        kod, j = _wp(client, throat_diameter=0.04, mdot_total=1.0)
        assert kod == 422
        assert 'burn_time' in (j.get('missing_fields') or []), j
        kod, j = _wp(client, throat_diameter=0.04, mdot_total=1.0,
                     burn_time=500)
        assert kod == 422
        assert j['invalid_fields'][0]['field'] == 'burn_time'
        assert j['invalid_fields'][0]['accepted_range'] == [0.0, 300.0]

    def test_mdot_gonderilmezse_kunye_de_yok(self, client):
        """Sağlıklı istek BİT-AYNI kalır: alan yoksa künye de yok.

        ``mdot_total`` da zorunlu olduğundan bu ucun künyesiz gövdesi
        yalnız ``expansion_ratio`` yolunda gözlenebilir."""
        kod, j = _wp(client, expansion_ratio=4.0, mdot_total=1.0,
                     burn_time=10)
        assert kod == 200, str(j)[:200]
        alanlar = {b['field'] for b in j.get('inputs_not_used', [])}
        assert 'mdot_total' not in alanlar

    def test_sozlesme_kardesiyle_ayni_sekilde(self, client):
        """``inputs_not_used`` öğe şekli ``/calculate`` ile aynı."""
        kod, j = _wp(client, throat_diameter=0.04, mdot_total=50,
                     burn_time=10)
        for b in j['inputs_not_used']:
            assert set(b) == {'field', 'submitted', 'used_by_model',
                              'reason', 'message'}, b
            assert b['message'].strip()


# ===========================================================================
# P7B3-30 (ŞART, Fable-D19) — düzeltilmiş zincir ölçümü
# ===========================================================================
class TestP7B330SartZinciri:

    def test_panel_govdesi_material_gonderiyor(self):
        """ŞART (1): pencere kapanış satırına kadar; sonuç TRUE."""
        js = open(os.path.join(KOK, 'hrma', 'static', 'js',
                               'thermal_fea_panel.js'),
                  encoding='utf-8').read()
        bas = js.index('function buildWallProfileBody')
        kapanis = 'return { body: body, missing: missing };'
        son = js.index(kapanis, bas) + len(kapanis)
        govde = js[bas:son]
        assert re.search(r'\bbody\.material\s*=', govde), (
            'panel gövdesi material ATAMASINI yapmıyor')
        # D19'un DAR penceresi kusuru göremiyordu — bunu kayda geçir.
        assert len(govde) > 1600, len(govde)

    def test_zincir_farkli_malzemeyi_adiyla_reddediyor(self, client):
        """ŞART (2): gerçek /calculate motoru + 'motor' anahtarı."""
        bas = {'Host': '127.0.0.1:8080'}
        hibrit = {
            'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
            'chamber_pressure': 20, 'of_ratio': 2.5, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o', 'expansion_ratio': 4.0,
            'nozzle_type': 'conical', 'chamber_material': 'steel_4130',
            'wall_thickness': 5,
        }
        rc = _quiet(client.post, '/calculate', json=hibrit, headers=bas)
        assert rc.status_code == 200
        motor = rc.get_json()['motor']
        sa = motor['structural_analysis']
        cozulen = ((sa.get('chamber_structure') or {}).get('material_key')
                   or (sa.get('design_parameters') or {}).get('material'))
        assert cozulen == 'steel_4130', sa.keys()
        g = {k: motor.get(k) for k in (
            'chamber_pressure', 'chamber_temperature', 'chamber_diameter',
            'chamber_length', 'burn_time', 'mdot_total', 'throat_diameter',
            'exit_diameter', 'expansion_ratio')}
        g.update({'nozzle_type': 'conical', 'wall_thickness': 0.005})
        rp = _quiet(client.post, '/api/analysis/wall-profile', json=g,
                    headers=bas)
        assert rp.status_code == 200
        profil = rp.get_json()['wall_profile']
        assert profil['material'] == 'steel'   # malzemesiz -> jenerik
        rf = _quiet(client.post, '/api/fea/thermal', json={
            'n_axial': 12, 'n_radial': 4, 'max_halvings': 3,
            'motor': motor, 'axial_profile': profil,
            'ambient_temperature_K': 293.15}, headers=bas)
        assert rf.status_code == 422
        jf = rf.get_json()
        assert jf['error'] == 'axial_profile_material_mismatch'
        assert jf['expected_material'] == 'steel_4130'


# ===========================================================================
# P16S1-02 / P16S1-03 — varsayılanlı okuma ENVANTERİ (mandal)
# ===========================================================================
_VARSAYILAN_RE = re.compile(
    r"""data\.get\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]\s*,\s*"""
    r"""(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*\)""")


def _uc_varsayilan_envanteri():
    """``@app.route`` gövdelerinde varsayılanlı SAYI okumaları."""
    satirlar = open(os.path.join(KOK, 'hrma', 'app.py'),
                    encoding='utf-8').read().split('\n')
    rotalar = []
    for i, s in enumerate(satirlar):
        m = re.match(r"@app\.route\(\s*['\"]([^'\"]+)['\"]", s.strip())
        if m:
            rotalar.append((i, m.group(1)))
    rotalar.append((len(satirlar), None))
    bulgular = {}
    for idx in range(len(rotalar) - 1):
        bas, yol = rotalar[idx]
        son = rotalar[idx + 1][0]
        if yol is None:
            continue
        govde = '\n'.join(satirlar[bas:son])
        es = _VARSAYILAN_RE.findall(govde)
        if es:
            bulgular.setdefault(yol, []).extend(es)
    return bulgular


class TestP16S102VarsayilanMandali:
    """Kapı + varsayılan yan yana duramaz — envanter BÜYÜYEMEZ.

    ÖLÇÜLDÜ (taban ``cdf2106``, ``a4/once.json`` P16S1-02): 13 uçta 77
    varsayılanlı sayı okuması; 68'i aynı gövdede bir kapı da bulunduran
    uçlarda. Kalemin ADIYLA andığı desen
    (``data.get('chamber_pressure', 20)``) ise 0 kez geçiyor — o ayak
    ÇÜRÜK, envanterin kendisi ayakta.

    Bu bekçi envanteri SÖKMEZ (ÖK-21: form katmanı bu dalgada dokunulmaz
    ve iki katman SIRAYLA sökülür — P16S1-03). Yaptığı, envanterin bir
    daha BÜYÜMEMESİNİ ve ölçülen sayının rapordan sapmamasını sağlamak.
    """

    TAVAN = 77          # taban cdf2106 ölçümü — yalnız AŞAĞI inebilir

    def test_envanter_buyumedi(self):
        env = _uc_varsayilan_envanteri()
        toplam = sum(len(v) for v in env.values())
        assert toplam <= self.TAVAN, (
            f'uç varsayılanlı okuma {toplam} > {self.TAVAN}: '
            f'{ {k: len(v) for k, v in env.items()} }')

    def test_kalemin_adli_ornegi_gercekten_gitti(self):
        src = open(os.path.join(KOK, 'hrma', 'app.py'),
                   encoding='utf-8').read()
        assert not re.search(
            r"data\.get\(\s*['\"]chamber_pressure['\"]\s*,\s*20\s*\)", src)

    def test_bu_dalgada_onarilan_uclar_temiz_kaldi(self):
        """a4'ün dokunduğu uçlar envantere yeni satır eklemedi."""
        env = _uc_varsayilan_envanteri()
        for uc in ('/api/altitude-to-pressure', '/api/flow-analysis',
                   '/api/analysis/wall-profile'):
            assert uc not in env, (uc, env.get(uc))


class TestP16S103SiraKisiti:
    """İki katmanlı onarımın SIRASI bağlayıcıdır (kalem bir ÖLÇÜMDÜR).

    Form katmanı (``value="X"`` + ``|| X``) ÖK-21 gereği bu dalgada
    sökülmez. Kalemin hükmü, sökümün önce UÇ katmanında yapılması
    gerektiğidir: uçta varsayılan dururken form yedeği sökülürse istek
    500'e döner. Bekçi bu iki katmanın da hâlâ dolu olduğunu ve dolayısıyla
    kısıtın hâlâ geçerli olduğunu ÖLÇER.
    """

    def _form_envanteri(self):
        say = {}
        kok = os.path.join(KOK, 'hrma', 'templates')
        for d, _alt, dosyalar in os.walk(kok):
            for f in dosyalar:
                if not f.endswith('.html'):
                    continue
                p = os.path.join(d, f)
                s = open(p, encoding='utf-8', errors='replace').read()
                v = len(re.findall(r'value\s*=\s*"[-\d.]+"', s))
                o = len(re.findall(r'\|\|\s*[-\d.]+', s))
                if v or o:
                    say[os.path.relpath(p, KOK)] = (v, o)
        return say

    def test_iki_katman_da_dolu_kisit_gecerli(self):
        form = self._form_envanteri()
        form_or = sum(o for _v, o in form.values())
        uc = sum(len(v) for v in _uc_varsayilan_envanteri().values())
        assert form_or > 0 and uc > 0, (form_or, uc)

    def test_form_katmani_envanteri_BUYUMUYOR(self):
        """ÖK-21 mandalı ÇEVRİLDİ — ÖH D31 · arayuz-panel a3 (14 Eyl 2026).

        Eski iddia ``>= 270`` idi ve "form yedeği sayısı DÜŞMEDİ" diyordu:
        ÖK-21 kilidi KAPALIYKEN sırayı koruyan bir mandaldı. Berke 14
        Eyl'de kilidi AÇTI; D31 dalgası sökümü başlattı (a2: advanced.html
        + flow_panel; a3: liquid.html 7 alan + solid.html 2 alan). Ölçüm:
        şablon genelinde ``|| SAYI`` **272 -> 263**. Mandal yerinde
        bırakılsaydı onarımı kırmızıya düşürürdü — kusuru koruyan bekçi.

        Yön tersine döndü: envanter artık YALNIZ AZALABİLİR. Yeni bir
        sessiz form yedeği eklenirse bu test kırmızı verir.
        """
        form = self._form_envanteri()
        toplam = sum(o for _v, o in form.values())
        assert toplam <= 263, (
            'şablonlarda yeni sessiz form yedeği (`|| SAYI`) doğmuş '
            '(D31 a3 ölçümü: 263): %d' % toplam, form)
        assert toplam > 0, form


# ===========================================================================
# ÇÜRÜTÜLEN KALEMLER — hüküm sabitlenir (dirilmesin)
# ===========================================================================
_EXPORT_TABAN = {
    'motor_name': 'T1',
    'motor_data': {'chamber_diameter': 0.10, 'chamber_length': 0.30,
                   'throat_diameter': 0.030, 'exit_diameter': 0.060,
                   'chamber_pressure': 50},
}
_EXPORT_UCLAR = ('/api/export-cad', '/api/export-dxf', '/api/export-stl-zip',
                 '/api/export-step', '/api/export-drawings-pdf',
                 '/api/export-complete-zip')


def _sarsim(**degistir):
    g = json.loads(json.dumps(_EXPORT_TABAN))
    g['motor_data'].update(degistir)
    return g


class TestCurutulenIhracatKalemleri:

    @pytest.mark.parametrize('uc', _EXPORT_UCLAR)
    def test_p16b410_negatif_kamara_boyu_imalat_dosyasi_uretmez(
            self, client, uc):
        r = _quiet(client.post, uc, json=_sarsim(chamber_length=-0.30))
        assert r.status_code == 422, f'{uc} -> {r.status_code}'

    @pytest.mark.parametrize('uc', _EXPORT_UCLAR)
    def test_p16b411_bool_cap_yutulmaz(self, client, uc):
        r = _quiet(client.post, uc, json=_sarsim(chamber_diameter=True))
        assert r.status_code == 422, f'{uc} -> {r.status_code}'
        assert (r.get_json() or {}).get('error') == 'invalid_export_geometry'

    @pytest.mark.parametrize('uc', _EXPORT_UCLAR)
    def test_p16b412_ters_lule_reddedilir(self, client, uc):
        r = _quiet(client.post, uc,
                   json=_sarsim(throat_diameter=0.060, exit_diameter=0.030))
        assert r.status_code == 422, f'{uc} -> {r.status_code}'
        assert (r.get_json() or {}).get(
            'error') == 'inconsistent_export_geometry'

    @pytest.mark.parametrize('uc', _EXPORT_UCLAR)
    def test_p16b412_bogaz_odadan_buyuk_reddedilir(self, client, uc):
        r = _quiet(client.post, uc,
                   json=_sarsim(throat_diameter=0.50, chamber_diameter=0.10))
        assert r.status_code == 422, f'{uc} -> {r.status_code}'

    @pytest.mark.parametrize('uc', ['/api/export-simulation',
                                    '/api/generate-complete-package'])
    @pytest.mark.parametrize('govde', [{}, {'motor_data': {}},
                                       {'motor_name': 'X'}])
    def test_p7b304_eksik_alan_ham_500_vermez(self, client, uc, govde):
        r = _quiet(client.post, uc, json=govde)
        assert r.status_code == 422, f'{uc} -> {r.status_code}'
        j = r.get_json() or {}
        assert j.get('error') in ('missing_export_data',
                                  'missing_export_geometry'), j
        # Ham Python istisna metni sızmaz.
        for iz in ('Traceback', 'KeyError', "object is not subscriptable"):
            assert iz not in json.dumps(j), j
