# -*- coding: utf-8 -*-
"""ÖH Dalga-33-3 / app-api-kapilar aşama-1 bekçileri.

Ölçüm: ``docs/scofield/raw/OH/D33-3/app-api-kapilar/a1/once.json`` (K1-K4) ve
aynı betiğin onarım sonrası koşumu ``sonra.json``. Taban ``fa7c4e1d``.

Kalemler:
  OH-D33-30  bilinmeyen oksitleyicide İKİ ayrı kapı  -> ONARILDI (tek kanon)
  OH-D33-16  ``/api/uncertainty-analysis`` kapı sırası -> ONARILDI (+ kilit)
  OH-D33-34  ``_collect_unphysical_fields`` künyesi   -> ONARILDI (metin)
  OH-D33-35  "ölü kol" iddiası                        -> ÇÜRÜTÜLDÜ (+ kilit)

DİKKAT — SAYI/AD LİSTESİ BU DOSYADA YAZILMAZ. Beklenen oksitleyici kümeleri
ürünün kendi tek kaynağından okunur (``hrma.analysis.safety_analysis.
HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL``,
``hrma.data.external_data_fetcher.normalize_oxidizer``); bekçi sayının
DEĞERİNİ değil ürünle AYNI kaynaktan geldiğini sınar.

Kaynak okuyan bekçiler dosyayı AST ile okur (``inspect.getsource`` birleşme
sonrası satır kayması yaşatıyor — taban kaydı dersi).
"""
import ast
import pathlib

import pytest

from hrma.app import app as flask_app

APP_PY = pathlib.Path(flask_app.root_path) / 'app.py'

#: ``/analyze_safety``ın ZORUNLU alanları sağlanmış en küçük geçerli gövde.
SAFETY = {'motor_type': 'hybrid', 'chamber_pressure': 20.0,
          'propellant_mass': 50.0, 'chamber_diameter': 0.1,
          'wall_thickness': 0.005}

UQ = {'motor_type': 'hybrid', 'level': 'fast'}
UQ_INPUTS = {'thrust': 1000.0, 'chamber_pressure': 20.0,
             'burn_time': 10.0, 'of_ratio': 6.0}


@pytest.fixture(scope='module')
def istemci():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _post(c, yol, govde):
    r = c.post(yol, json=govde)
    return r.status_code, (r.get_json(silent=True) or {})


def _patlayici(govde):
    """/analyze_safety yanıtından patlayıcı ekseni bloğu."""
    sa = govde.get('safety_analysis')
    if isinstance(sa, dict) and isinstance(sa.get('explosive_hazards'), dict):
        return sa['explosive_hazards']
    return govde.get('explosive_hazards') or {}


def _fonksiyon_agaci(ad):
    """``app.py``deki fonksiyonun AST düğümü (dosyadan, kaynak okumadan)."""
    agac = ast.parse(APP_PY.read_text(encoding='utf-8'))
    for dugum in ast.walk(agac):
        if isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and dugum.name == ad:
            return dugum
    raise AssertionError('fonksiyon bulunamadı: %s' % ad)


# ===========================================================================
# OH-D33-30 — BİLİNMEYEN OKSİTLEYİCİ: TEK KAPI, TEK KANON
# ===========================================================================
class TestOHD3330OksitleyiciKapiKanonu:
    """ÖLÇÜLDÜ (``a1/once.json`` K1, taban ``fa7c4e1d``): ``oxidizer_type=
    'peynir'`` ``POST /api/oxidizer-properties``te 400
    ``oxidizer_type_unknown`` alırken AYNI değer ``POST /analyze_safety``te
    HTTP 200 + sınıf ``hybrid_n2o`` + **22,2775 kg TNT** alıyordu (ürünün
    varsayılan oksitleyicisi, "ASSUMPTION" beyanıyla). Aynı kötü girdi uca
    göre fail-closed ya da fail-open'dı. Berke kararı (16 Eyl 2026): kanon
    TEK, yön ADIYLA 400.
    """

    @pytest.mark.parametrize('ad', ['peynir', 'air'])
    def test_taninmayan_ad_iki_ucta_da_adiyla_400(self, istemci, ad):
        k1, g1 = _post(istemci, '/api/oxidizer-properties',
                       {'oxidizer_type': ad})
        k2, g2 = _post(istemci, '/analyze_safety',
                       dict(SAFETY, oxidizer_type=ad))
        assert (k1, k2) == (400, 400), (ad, k1, k2)
        for g in (g1, g2):
            assert g.get('error_code') == 'oxidizer_type_unknown', g
            assert g.get('field') == 'oxidizer_type', g
            assert g.get('value') == ad, g

    def test_taninmayan_ad_motor_tipinden_bagimsiz_reddedilir(self, istemci):
        """Depoca hiç tanınmayan ad her bağlamda çöptür."""
        for mt in ('hybrid', 'solid', 'liquid'):
            kod, g = _post(istemci, '/analyze_safety',
                           dict(SAFETY, motor_type=mt,
                                oxidizer_type='peynir'))
            assert kod == 400, (mt, kod)
            assert g.get('error_code') == 'oxidizer_type_unknown', (mt, g)

    @pytest.mark.parametrize('ad', ['n2o4', 'lox'])
    def test_hibritte_modelsiz_ad_sayi_uydurmuyor(self, istemci, ad):
        """Depo TANIYOR ama bu ucun TNT türetimi yok -> sayı yayımlanmaz.

        ÖLÇÜLDÜ (K1 matrisi): ``motor_type='hybrid'`` + ``oxidizer_type=
        'n2o4'`` isteği ``hybrid_n2o`` sınıfını ve 22,2775 kg TNT'yi
        alıyordu — kullanıcının yazdığı akışkanın değil, ürün
        varsayılanının sayısı.
        """
        from hrma.data.external_data_fetcher import normalize_oxidizer
        kod, g = _post(istemci, '/analyze_safety',
                       dict(SAFETY, oxidizer_type=ad))
        assert kod == 400, (ad, kod)
        assert g.get('error_code') == 'oxidizer_properties_unavailable', g
        assert g.get('resolved_as') == normalize_oxidizer(ad), g
        assert 'safety_analysis' not in g, 'reddedilen istekte hüküm var'

    def test_kabul_edilen_adlar_TEK_KAYNAKTAN(self, istemci):
        """``accepted_values`` bu dosyada yazılmaz; üründen okunur."""
        from hrma.analysis.safety_analysis import (
            HYBRID_OXIDIZER_DECOMPOSITION_KCAL_PER_MOL as HIB)
        _, g = _post(istemci, '/analyze_safety',
                     dict(SAFETY, oxidizer_type='peynir'))
        assert g.get('accepted_values') == sorted(HIB), g

    @pytest.mark.parametrize('ad', ['h2o2', 'n2o', 'nitrous', 'hp'])
    def test_cozulen_ad_hukmunu_ALMAYA_devam_eder(self, istemci, ad):
        """Kapı DAR: adıyla çözülen oksitleyici bit-aynı hüküm alır."""
        from hrma.analysis.safety_analysis import hybrid_oxidizer_from_text
        kod, g = _post(istemci, '/analyze_safety',
                       dict(SAFETY, oxidizer_type=ad))
        assert kod == 200, (ad, kod, g.get('error'))
        beklenen = 'hybrid_%s' % hybrid_oxidizer_from_text(ad)
        assert _patlayici(g).get('explosive_class') == beklenen, (ad, g)

    @pytest.mark.parametrize('mt', ['solid', 'liquid'])
    def test_hukmu_belirlemeyen_tipte_tanidik_ad_REDDEDILMEZ(self, istemci, mt):
        """ÖLÇÜLDÜ (K1 matrisi, 10/10 satır): katı/sıvı istekte
        ``oxidizer_type`` patlayıcı sınıfını hiç değiştirmiyor — orada
        ``lox``/``n2o4`` reddetmek hiçbir uydurmayı önlemez, yalnız meşru
        bir isteği düşürürdü.
        """
        for ad in ('lox', 'n2o4'):
            kod, g = _post(istemci, '/analyze_safety',
                           dict(SAFETY, motor_type=mt, oxidizer_type=ad))
            assert kod == 200, (mt, ad, kod, g.get('error'))

    def test_alan_verilmediginde_govde_BIT_AYNI(self, istemci):
        """Alan isteğe bağlıdır: yokluğu/boşluğu ret nedeni DEĞİLDİR."""
        kod_yok, g_yok = _post(istemci, '/analyze_safety', dict(SAFETY))
        kod_bos, g_bos = _post(istemci, '/analyze_safety',
                               dict(SAFETY, oxidizer_type=''))
        assert (kod_yok, kod_bos) == (200, 200)
        assert (_patlayici(g_yok).get('explosive_class')
                == _patlayici(g_bos).get('explosive_class'))
        assert 'oxidizer_type' not in (g_yok.get('defaults_applied') or [])

    def test_kardes_ucun_govdesi_DEGISMEDI(self, istemci):
        """Ortak kapıya taşınırken ``/api/oxidizer-properties`` sözleşmesi
        korunmalı: iki ``error_code``, ``resolved_as`` ve tek kaynaktan
        gelen ``accepted_values``.
        """
        kod, g = _post(istemci, '/api/oxidizer-properties',
                       {'oxidizer_type': 'n2o4'})
        assert kod == 400
        assert g['error_code'] == 'oxidizer_properties_unavailable'
        assert g['resolved_as'] == 'n2o4'
        assert 'recognised oxidizer' in g['error']
        assert 'density, viscosity or vapour pressure' in g['error']
        assert g['accepted_values'] and 'n2o' in g['accepted_values']

    def test_iki_uc_AYNI_yardimciyi_cagiriyor(self):
        """Kanon iki yerde yazılmaz (doktrin 4): tek çağrılan yardımcı."""
        cagiranlar = set()
        agac = ast.parse(APP_PY.read_text(encoding='utf-8'))
        for dugum in ast.walk(agac):
            if not isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for alt in ast.walk(dugum):
                if isinstance(alt, ast.Call) and isinstance(alt.func, ast.Name) \
                        and alt.func.id == '_oksitleyici_adi_reddi':
                    cagiranlar.add(dugum.name)
        assert {'analyze_safety', 'get_live_oxidizer_properties'} <= cagiranlar, \
            cagiranlar

    def test_ad_cozumu_modulde_TEK_KAYNAK(self):
        """``hybrid_oxidizer_from_text`` hem uç hem sınıf çözücüsü için."""
        from hrma.analysis import safety_analysis as sa
        assert callable(sa.hybrid_oxidizer_from_text)
        kaynak = pathlib.Path(sa.__file__).read_text(encoding='utf-8')
        agac = ast.parse(kaynak)
        cagiranlar = [d.name for d in ast.walk(agac)
                      if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))
                      for alt in ast.walk(d)
                      if isinstance(alt, ast.Call)
                      and isinstance(alt.func, ast.Name)
                      and alt.func.id == 'hybrid_oxidizer_from_text']
        assert '_resolve_hybrid_explosive_class' in cagiranlar, cagiranlar


# ===========================================================================
# OH-D33-16 — /api/uncertainty-analysis KAPI SIRASI
# ===========================================================================
class TestOHD3316KapiSirasi:
    """ÖLÇÜLDÜ (``a1/once.json`` K2): ``inputs`` HİÇ YOK + ``seed=-1``
    gövdesi 400 ``seed`` alıyordu; birincil sorun ("hiç motor girdisi yok")
    hiç anılmıyordu. Kanon kardeş uçtan (``/analyze_safety``): önce ZORUNLU
    yük tamlığı, sonra gönderilmiş DEĞERLER.
    """

    def test_eksik_yuk_ONCE_konusur(self, istemci):
        kod, g = _post(istemci, '/api/uncertainty-analysis',
                       dict(UQ, seed=-1))
        assert kod == 422, (kod, g.get('error'))
        assert g.get('error') == 'incomplete_uncertainty_input', g
        assert g.get('missing_fields') == ['inputs'], g

    def test_bozuk_tipli_yuk_de_ONCE_konusur(self, istemci):
        kod, g = _post(istemci, '/api/uncertainty-analysis',
                       dict(UQ, seed=-1, inputs=[1, 2]))
        assert kod == 400, kod
        assert 'inputs' in str(g.get('error')), g

    def test_tohum_kapisi_KORUNDU(self, istemci):
        """Yük tamken tohum kapısı bit-aynı konuşur (P16B3-36 sözleşmesi)."""
        kod, g = _post(istemci, '/api/uncertainty-analysis',
                       dict(UQ, seed=-1, inputs=dict(UQ_INPUTS)))
        assert kod == 400, kod
        assert "'seed'" in str(g.get('error')), g
        alanlar = [a.get('field') for a in (g.get('invalid_fields') or [])]
        assert 'seed' in alanlar, g

    def test_kimlik_kapilari_HALA_EN_BASTA(self, istemci):
        kod, g = _post(istemci, '/api/uncertainty-analysis',
                       dict(UQ, motor_type='peynir', seed=-1))
        assert kod == 400
        assert 'motor_type' in str(g.get('error')), g

    def test_SIRA_kaynakta_kilitli(self):
        """Yük kapısı, tohum kapısından ÖNCE durmalı (AST, dosyadan)."""
        dugum = _fonksiyon_agaci('uncertainty_analysis')
        yuk = [a.lineno for a in ast.walk(dugum)
               if isinstance(a, ast.Constant)
               and a.value == 'incomplete_uncertainty_input']
        tohum = [a.lineno for a in ast.walk(dugum)
                 if isinstance(a, ast.Call)
                 and isinstance(a.func, ast.Attribute)
                 and a.func.attr == 'integer'
                 and any(isinstance(x, ast.Constant) and x.value == 'seed'
                         for x in a.args)]
        assert yuk and tohum, (yuk, tohum)
        assert min(yuk) < min(tohum), (
            'zorunlu yük kapısı tohum kapısından SONRA: %s > %s'
            % (min(yuk), min(tohum)))


# ===========================================================================
# OH-D33-34 — KÜNYE ÖLÇÜMLE UYUŞUYOR MU
# ===========================================================================
class TestOHD3334KunyeOlcumleUyusur:
    """Künye "ayrım ham değerin kendi SONLULUĞUNDAN okunur" diyordu; bir
    dizenin sonluluğu yoktur. ÖLÇÜLDÜ (``a1/once.json`` K3): ayrım ilkin
    JSON TİPİNDEN (``is_json_number``) okunur.
    """

    def test_yanlis_iddia_kaynakta_YOK(self):
        metin = APP_PY.read_text(encoding='utf-8')
        assert 'ayrım ham değerin kendi sonluluğundan okunur' not in metin, \
            'künye hâlâ dizenin sonluluğundan söz ediyor'

    def test_kunye_olculen_kurali_anlatiyor(self):
        metin = APP_PY.read_text(encoding='utf-8')
        assert 'OH-D33-34' in metin
        assert 'Ayrım ilkin değerin JSON TİPİNDEN' in metin

    @pytest.mark.parametrize('ham,beklenen', [
        ('NaN', 'not_a_json_number'),
        ('inf', 'not_a_json_number'),
        ('20.0', 'not_a_json_number'),
        (True, 'boolean_is_not_a_number'),
    ])
    def test_yayimlanan_gerekce(self, istemci, ham, beklenen):
        kod, g = _post(istemci, '/analyze_safety',
                       dict(SAFETY, chamber_pressure=ham))
        assert kod == 422, kod
        alanlar = g.get('invalid_fields') or []
        assert alanlar and alanlar[0]['reason'] == beklenen, (ham, alanlar)

    def test_gercek_sonsuz_SONLULUKTAN_okunur(self, istemci):
        """Gerçek JSON sayısı için ayrım sonluluktan gelir (kanon böyle)."""
        import json as _json
        r = istemci.post('/analyze_safety',
                         data=_json.dumps(dict(SAFETY,
                                               chamber_pressure=float('inf'))),
                         content_type='application/json')
        g = r.get_json(silent=True) or {}
        assert r.status_code == 422
        assert (g.get('invalid_fields') or [{}])[0].get('reason') == 'not_finite', g


# ===========================================================================
# OH-D33-35 — "ÖLÜ KOL" İDDİASI ÇÜRÜTÜLDÜ (kol CANLI, kilitlenir)
# ===========================================================================
class TestOHD3335SozlukDegilKoluCANLI:
    """İDDİA: ``_export_geometry_problem``in ``not isinstance(motor_data,
    dict)`` kolu erişilemez, çünkü "iki çağıranı" önce
    ``_reject_non_object_geometry``den geçiyor.

    ÖLÇÜLDÜ (``a1/once.json`` K4, taban ``fa7c4e1d``): çağıran İKİ DEĞİL
    YEDİ ve yedisinin de önünde o koruma YOK; dört canlı rota sözlük
    OLMAYAN ``motor_data`` ile tam olarak bu kola düşüyor. İddia
    ÇÜRÜTÜLDÜ; kol silinirse bu rotalar ham çözücü hatasına düşer, bu
    yüzden canlılık bekçiyle kilitlenir.
    """

    #: İki kapının gövdesi YALNIZ mesajıyla ayrılır.
    MESAJ = 'must be an object with geometry fields'

    @pytest.mark.parametrize('yol,govde', [
        ('/api/export-stl-zip', {'motor_data': [1, 2, 3]}),
        ('/api/export-complete-zip', {'motor_data': 'x'}),
        ('/api/export-dxf', {'motor_data': [1, 2, 3]}),
        ('/api/export-step', {'motor_data': [1, 2, 3]}),
    ])
    def test_kol_CANLI(self, istemci, yol, govde):
        kod, g = _post(istemci, yol, govde)
        assert kod == 422, (yol, kod)
        assert g.get('error') == 'invalid_export_geometry', (yol, g)
        assert self.MESAJ in str(g.get('message')), (yol, g)
        alanlar = g.get('invalid_fields') or []
        assert alanlar and alanlar[0]['reason'] == 'not_an_object', (yol, g)

    def test_korumasiz_cagri_yeri_VAR(self):
        """Statik kanıt: kapıyı çağıran ama önce sözlük kapısından
        geçmeyen çağrı yerleri (bu yüzden kol erişilebilir).
        """
        agac = ast.parse(APP_PY.read_text(encoding='utf-8'))
        KAPILAR = ('_reject_unexportable_geometry',
                   '_reject_nonfinite_export_geometry')
        korumasiz = []
        for dugum in ast.walk(agac):
            if not isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            cagrilar = sorted(
                (alt.lineno, alt.func.id,
                 ast.unparse(alt.args[0]) if alt.args else None)
                for alt in ast.walk(dugum)
                if isinstance(alt, ast.Call) and isinstance(alt.func, ast.Name))
            gorulen = []
            for _satir, ad, arg in cagrilar:
                if ad == '_reject_non_object_geometry':
                    gorulen.append(arg)
                elif ad in KAPILAR and arg not in gorulen:
                    korumasiz.append((dugum.name, ad))
        assert korumasiz, 'kol gerçekten ölüyse iddia yeniden açılmalı'
