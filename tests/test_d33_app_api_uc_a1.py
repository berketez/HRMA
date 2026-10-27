# -*- coding: utf-8 -*-
"""ÖH Dalga-33 (KOLAY) / app-api-uc aşama-1 bekçileri.

Ölçüm: ``docs/scofield/raw/OH/D33/app-api-uc/a1/once.json`` (K1-K4) ve aynı
betiğin onarım sonrası koşumu ``sonra.json``. Taban ``56f88e70``.

Kalemler:
  OH-D23-21  değer/uç katmanı bool kuralı TEK KAYNAK (ŞART)     ONARILDI
  OH-UC-06   ``_input_guards.reject_bool`` çıplak isinstance     ONARILDI
  OH-UC-01   ``/api/quick-geometry`` ``ambient_temp`` kapısı     ONARILDI
  OH-UC-11   ``/calculate`` ``mdot_ox`` sessiz yutma             ONARILDI
  P7B4-19    katı kolun bandsız alanı GÖRÜNÜR (ŞART)             ONARILDI
             (ölçülen-durum kilidi ``tests/test_d28_app_api_a1.py``
             ``TestP7B419BelirsizlikBandKapisi`` içindedir — denetçi
             şartı düğümün ORADA durmasını istedi.)

DİKKAT — SAYI/BANT BU DOSYADA YAZILMAZ. Beklenen bantlar ürünün kendi tek
kaynağından okunur (``hrma.constants.AMBIENT_TEMPERATURE_BAND_K``,
``hrma.validation.motor_validation.CANONICAL_LIMITS`` / ``FORM_LIMITS``);
bekçi, sayının DEĞERİNİ değil ürünle AYNI kaynaktan geldiğini sınar.
"""
import ast
import contextlib
import hashlib
import io
import json
import pathlib
import re

import pytest

from hrma.app import app as flask_app


CALC_TABAN = {
    'motor_type': 'hybrid', 'thrust': 1000.0, 'burn_time': 10.0,
    'chamber_pressure': 20.0, 'of_ratio': 6.0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
}

#: ``/api/quick-geometry`` gövdesi ``motor_type`` taşımaz (uç hibrit ikizdir).
QG_TABAN = {k: v for k, v in CALC_TABAN.items() if k != 'motor_type'}


@pytest.fixture(scope='module')
def istemci():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _post(c, yol, govde):
    r = c.post(yol, json=govde)
    try:
        return r.status_code, (r.get_json() or {}), r.get_data()
    except Exception:
        return r.status_code, {}, r.get_data()


def _alanlar(govde):
    return {f.get('field') for f in (govde.get('invalid_fields') or [])
            if isinstance(f, dict)}


# ===========================================================================
# OH-D23-21 (ŞART) + OH-UC-06 — bool hükmü TEK KAYNAKTAN
# ===========================================================================
class TestOHD2321BoolKuraliTekKaynak:
    """ÖNCE (once.json K1, taban ``56f88e70``): sekiz örnekten İKİSİ iki
    katmanda ayrı hüküm alıyordu — ``numpy.bool_(True)`` ve
    ``numpy.bool_(False)`` ``_input_guards.reject_bool``tan GEÇİYOR ama
    ``input_guard._is_bool`` onlara ``True`` diyordu. ``numpy.bool_`` Python
    ``bool``un alt sınıfı değildir; ``float()`` yine de 1.0/0.0 verir."""

    ORNEKLER = ['bool', 'numpy_bool', 'int', 'float', 'str', 'numpy_float']

    @staticmethod
    def _ornek(ad, dogru=True):
        if ad == 'bool':
            return dogru
        if ad == 'int':
            return 1 if dogru else 0
        if ad == 'float':
            return 1.0 if dogru else 0.0
        if ad == 'str':
            return '1.0'
        np = pytest.importorskip('numpy')
        if ad == 'numpy_bool':
            return np.bool_(dogru)
        return np.float64(1.0)

    @pytest.mark.parametrize('ad', ORNEKLER)
    @pytest.mark.parametrize('dogru', [True, False])
    def test_iki_katman_ayni_hukmu_verir(self, ad, dogru):
        from hrma.analysis import _input_guards as ig
        from hrma.utils import input_guard as ug
        deger = self._ornek(ad, dogru)
        try:
            ig.reject_bool(deger, 'x')
            deger_katmani_reddetti = False
        except ValueError:
            deger_katmani_reddetti = True
        assert deger_katmani_reddetti == bool(ug._is_bool(deger)), (
            'iki katman %r için ayrıştı (OH-D23-21 / OH-UC-06)' % (deger,))

    def test_numpy_bool_ARTIK_reddediliyor(self):
        """Ölçülen iki ayrışmanın ürün yüzeyindeki karşılığı."""
        np = pytest.importorskip('numpy')
        from hrma.analysis import _input_guards as ig
        for kapi in (ig.require_positive, ig.require_non_negative,
                     ig.require_whole_number):
            with pytest.raises(ValueError):
                kapi(np.bool_(True), 'main_mass_flow', 'kg/s')

    def test_numpy_sayisi_MESRU_kalir(self):
        """Kapı numpy'yi topyekûn elemez — çözücü sonucu numpy taşır."""
        np = pytest.importorskip('numpy')
        from hrma.analysis import _input_guards as ig
        assert ig.require_positive(np.float64(2.0), 'x') == 2.0
        assert ig.require_whole_number(np.int64(4), 'n') == 4

    def test_kural_IKINCI_kez_yazilmadi(self):
        """``reject_bool`` gövdesinde kendi ``isinstance`` hükmü YOK."""
        from hrma.analysis import _input_guards as ig
        metin = pathlib.Path(ig.__file__).read_text(encoding='utf-8')
        agac = ast.parse(metin)
        govde = next(d for d in agac.body
                     if isinstance(d, ast.FunctionDef)
                     and d.name == 'reject_bool')
        ciplak = [d for d in ast.walk(govde)
                  if isinstance(d, ast.Call)
                  and getattr(d.func, 'id', None) == 'isinstance']
        assert not ciplak, (
            'bool hükmü burada İKİNCİ KEZ yazılmış (Doktrin 4): kaynak '
            'hrma.utils.input_guard._is_bool olmalı')
        ithal = [d for d in ast.walk(agac)
                 if isinstance(d, ast.ImportFrom)
                 and (d.module or '') == 'hrma.utils.input_guard']
        assert ithal, 'tek kaynak ithal edilmiyor'
        assert any(a.name == '_is_bool' for d in ithal for a in d.names)

    def test_kunye_ACIK_BORCU_yaziyor(self):
        """Künye "iki dosya birlikte güncellenir" SÖZÜNÜ artık VERMİYOR.

        Cümle silinmedi, TARİHE çevrildi: künye onu tırnak içinde ve geçmiş
        kiple ("diyordu") anar, yani artık yürürlükteki bir sözleşme değil
        ölçülmüş bir kayıttır. Kapanmamış borç (tip kuralının bilerek ayrı
        kalması) ayrıca ADIYLA yazılıdır.
        """
        from hrma.analysis import _input_guards as ig
        duz = ' '.join((ig.__doc__ or '').split())
        assert 'iki dosya birlikte güncellenir"* diyordu' in duz, (
            'tekliği ölçülmeyen bir söze bağlayan cümle hâlâ YÜRÜRLÜKTE')
        assert 'BORÇ' in duz, 'kapanmamış borç künyede yazılı değil'
        assert 'numpy.bool_' in duz, 'ölçülen sürüklenme künyede yok'


# ===========================================================================
# OH-UC-01 — /api/quick-geometry ambient_temp kapı asimetrisi
# ===========================================================================
class TestOHUC01QuickGeometryOrtamSicakligi:
    """ÖNCE (once.json K2): ``ambient_temp`` = ``true`` / ``'abc'`` /
    ``5000`` / ``-50`` / ``10`` gönderen BEŞ istek ``/calculate``te 400 +
    ``ambient_temp`` künyesi alırken ``/api/quick-geometry``de BEŞİ DE
    HTTP 200 alıyordu; değer motora ham geçip motor zarfında sessizce
    düşüyordu."""

    SARSIMLAR = [True, 'abc', 5000.0, -50.0, 10.0]

    @pytest.mark.parametrize('deger', SARSIMLAR)
    def test_bant_disi_ADIYLA_reddedilir(self, istemci, deger):
        kod, g, _ = _post(istemci, '/api/quick-geometry',
                          dict(QG_TABAN, ambient_temp=deger))
        assert kod == 400, (deger, kod, str(g)[:300])
        assert 'ambient_temp' in _alanlar(g), (deger, g.get('invalid_fields'))
        assert 'motor' not in g, 'reddedilen istek yine de geometri üretti'

    @pytest.mark.parametrize('deger', SARSIMLAR)
    def test_IKI_UC_ayni_hukmu_verir(self, istemci, deger):
        """Kalemin çekirdeği: aynı ürün, aynı alan, aynı değer, tek hüküm."""
        qg, gq, _ = _post(istemci, '/api/quick-geometry',
                          dict(QG_TABAN, ambient_temp=deger))
        ck, gc, _ = _post(istemci, '/calculate',
                          dict(CALC_TABAN, ambient_temp=deger))
        assert (qg == 400) == (ck == 400), (deger, qg, ck)
        assert 'ambient_temp' in _alanlar(gq) & _alanlar(gc), (
            deger, gq.get('invalid_fields'), gc.get('invalid_fields'))

    def test_bant_IKINCI_kez_yazilmadi(self, istemci):
        """Yayımlanan aralık ürünün kendi sabitinden gelir (Doktrin 4)."""
        from hrma.constants import AMBIENT_TEMPERATURE_BAND_K
        kod, g, _ = _post(istemci, '/api/quick-geometry',
                          dict(QG_TABAN, ambient_temp=5000.0))
        assert kod == 400, (kod, str(g)[:200])
        kayit = [k for k in g['invalid_fields']
                 if k['field'] == 'ambient_temp'][0]
        assert kayit['accepted_range'] == list(AMBIENT_TEMPERATURE_BAND_K), (
            'uçtaki bant hrma.constants ile ayrışmış')
        assert kayit['unit'] == 'K'
        assert kayit['resolved_as'] == 'ambient_temperature'

    @pytest.mark.parametrize('govde,ad', [
        (dict(QG_TABAN, ambient_temp=300.0), 'bant_ici'),
        (dict(QG_TABAN, ambient_temp=''), 'bos_dize'),
        (dict(QG_TABAN), 'alan_yok'),
    ])
    def test_SAGLIKLI_yol_daralmadi(self, istemci, govde, ad):
        """ÖK-22: kapı meşru gövdeyi reddetmez ('' = "verilmedi")."""
        kod, g, _ = _post(istemci, '/api/quick-geometry', govde)
        assert kod == 200, (ad, kod, str(g)[:300])

    def test_gonderilmeyen_alan_govdeyi_DEGISTIRMEZ(self, istemci):
        """Alan yokken yanıt, '' gönderildiğindekiyle BİT-AYNI."""
        _, _, b1 = _post(istemci, '/api/quick-geometry', dict(QG_TABAN))
        _, _, b2 = _post(istemci, '/api/quick-geometry',
                         dict(QG_TABAN, ambient_temp=''))
        assert hashlib.sha256(b1).hexdigest() == \
            hashlib.sha256(b2).hexdigest()


# ===========================================================================
# OH-UC-11 — /calculate mdot_ox: çözücünün ÜRETTİĞİ sayı girdi değildir
# ===========================================================================
class TestOHUC11HesaplananAlanGirdiDegil:
    """ÖNCE (once.json K3): ``mdot_ox`` 0 / -2 / 0,38 gönderen üç isteğin
    yanıtı, alanı hiç göndermeyen isteğinkiyle BİT-AYNI çıkıyordu (dördü de
    sha256 ``8710d668...``, HTTP 200) ve gövdede alanın yutulduğunu söyleyen
    tek bir yaprak bile yoktu."""

    @pytest.mark.parametrize('deger', [0, -2, 0.38, '0.38', True])
    def test_ADIYLA_reddedilir(self, istemci, deger):
        kod, g, _ = _post(istemci, '/calculate',
                          dict(CALC_TABAN, mdot_ox=deger))
        assert kod == 422, (deger, kod, str(g)[:300])
        assert g['error'] == 'computed_field_not_an_input'
        assert 'mdot_ox' in _alanlar(g)

    def test_RET_tasarim_yayimlamaz(self, istemci):
        kod, g, _ = _post(istemci, '/calculate',
                          dict(CALC_TABAN, mdot_ox=0.38))
        assert kod == 422
        assert 'motor' not in g and 'plots' not in g, (
            'reddedilen istekten hâlâ tasarım yayımlanıyor')

    def test_ret_NEREYE_GIDILECEGINI_soyluyor(self, istemci):
        """Ret çıkmaz sokak değildir: alanı GERÇEKTEN okuyan uçlar anılır."""
        _, g, _ = _post(istemci, '/calculate', dict(CALC_TABAN, mdot_ox=2.0))
        kayit = [k for k in g['invalid_fields'] if k['field'] == 'mdot_ox'][0]
        assert kayit['reason'] == 'computed_output_not_accepted_as_input'
        assert kayit['published_as'] == 'motor.mdot_ox'
        assert '/api/injector-design' in kayit['message']
        assert '/api/regression-analysis' in kayit['message']
        assert kayit['submitted'] == 2.0

    @pytest.mark.parametrize('govde,ad', [
        (dict(CALC_TABAN), 'alan_yok'),
        (dict(CALC_TABAN, mdot_ox=None), 'acik_null'),
        (dict(CALC_TABAN, mdot_ox=''), 'bos_dize'),
    ])
    def test_SAGLIKLI_yol_daralmadi(self, istemci, govde, ad):
        kod, g, _ = _post(istemci, '/calculate', govde)
        assert kod == 200, (ad, kod, str(g)[:300])

    def test_saglikli_govdeler_BIT_AYNI(self, istemci):
        """Kapı bir bayt bile eklemedi: üç meşru gövde aynı sha256."""
        hepsi = set()
        for govde in (dict(CALC_TABAN),
                      dict(CALC_TABAN, mdot_ox=None),
                      dict(CALC_TABAN, mdot_ox='')):
            _, _, b = _post(istemci, '/calculate', govde)
            hepsi.add(hashlib.sha256(b).hexdigest())
        assert len(hepsi) == 1, hepsi

    def test_alan_KARDES_UCTA_hala_gercek_girdi(self, istemci):
        """Ret ``/calculate``e özgüdür: debiyi OKUYAN uç etkilenmedi."""
        kod, g, _ = _post(istemci, '/api/regression-analysis', {
            'motor_data': {'burn_time': 10.0, 'mdot_ox': 0.38,
                           'port_diameter_initial': 0.03,
                           'fuel_type': 'htpb', 'fuel_density': 920.0,
                           'regression_a': 0.0001, 'regression_n': 0.5,
                           'grain_length': 0.5, 'chamber_length': 0.6}})
        assert kod == 200, (kod, str(g)[:300])
        assert 'computed_field_not_an_input' not in json.dumps(g)


# ===========================================================================
# P7B4-19 (ŞART) — künye TEK KAYNAKTAN türer
# ===========================================================================
class TestP7B419BandsizAlanKunyesi:
    """Ölçülen durum kilidi ``tests/test_d28_app_api_a1.py`` içindedir
    (denetçi şartı). Burada yalnız künyenin ELLE YAZILMADIĞI sınanır:
    ilan edilen adlar ``FORM_LIMITS``ten türemelidir."""

    def test_kunye_FORM_LIMITS_ten_turer(self, istemci):
        from hrma.validation.motor_validation import FORM_LIMITS
        from hrma.app import _UQ_FORM_BY_MOTOR
        kod, g, _ = _post(istemci, '/api/uncertainty-analysis', {
            'motor_type': 'solid', 'level': 'fast', 'seed': 7,
            'n_samples': 2,
            'inputs': {'thrust': 1000.0, 'chamber_pressure': 20.0,
                       'burn_time': 10.0, 'chamber_diameter': 100.0,
                       'grain_length': 500.0}})
        assert kod == 200, (kod, str(g)[:300])
        form = _UQ_FORM_BY_MOTOR['solid']
        ilan = {k['field'] for k in (g.get('inputs_not_band_checked') or [])}
        bandi_olan = set(FORM_LIMITS[form])
        assert ilan and not (ilan & bandi_olan), (ilan, bandi_olan)
        # Gönderilen SAYISAL alanlardan bandı olmayan HERKES ilan edilmeli.
        gonderilen = {'thrust', 'chamber_pressure', 'burn_time',
                      'chamber_diameter', 'grain_length'}
        assert ilan == gonderilen - bandi_olan, (ilan, gonderilen)

    def test_SAYI_OLMAYAN_alan_kunyeye_girmez(self, istemci):
        """Bir itici adı bant denetlenebilir ölçü değildir — gürültü yok."""
        kod, g, _ = _post(istemci, '/api/uncertainty-analysis', {
            'motor_type': 'liquid', 'level': 'fast', 'seed': 7,
            'n_samples': 2,
            'inputs': {'thrust': 10000.0, 'chamber_pressure': 30.0,
                       'mixture_ratio': 2.2, 'fuel_type': 'rp1',
                       'oxidizer_type': 'lox'}})
        assert kod == 200, (kod, str(g)[:300])
        ilan = {k['field'] for k in (g.get('inputs_not_band_checked') or [])}
        assert not (ilan & {'fuel_type', 'oxidizer_type'}), ilan


# ===========================================================================
# ÖH D33-2 / app-api-uc · aşama 1 — YENİ KALEMLER
# ===========================================================================
# DİKKAT: yukarısı ÖH D33 (KOLAY) dalgasının bekçileridir ve DOKUNULMADI.
# Aşağıdaki bölüm D33-2 dalgasının kalemlerini ekler; yardımcıları kendi
# adlarını taşır (``_gonder`` ikili döndürür, özgün ``_post`` üçlü) ki iki
# dalganın sözleşmeleri birbirine karışmasın.
# Ölçüm: ``docs/scofield/raw/OH/D33-2/app-api-uc/a1/once_*.json`` ->
# ``sonra_*.json``; ters-mutasyon ``mutasyon.json``. Taban ``5e0714c1``.

KOK_D332 = pathlib.Path(__file__).resolve().parent.parent


def _gonder(c, yol, yuk):
    """D33-2 yardımcısı: ``(durum, gövde)``; çözücü gürültüsü yutulur."""
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            r = c.post(yol, json=yuk)
    try:
        g = r.get_json()
    except Exception:
        g = None
    return r.status_code, (g if isinstance(g, dict) else {})


def _gerekce_kumesi(govde):
    return {k.get('reason') for k in (govde.get('invalid_fields') or [])
            if isinstance(k, dict)}


# ===========================================================================
# OH-D32-13 / OH-D31-14 — /api/flow-analysis alan-alan kapısı + form sökümü
# ===========================================================================
AKIS_TAM = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
            'gamma': 1.21, 'molecular_weight': 22.5, 'throat_diameter': 0.03,
            'ambient_pressure': 101325.0, 'expansion_ratio': 8.0}


class TestOHD3213AkisKapisi:
    """ÖLÇÜLDÜ (``a1/once_ohd3114.json``): zorunlu alanı eksik 18/18 istek
    HTTP 200 + tam hüküm; ``{'fidelity': 'engineering'}`` 882,49 N;
    geometrisiz gövde 1981,64 N (künyesiz ε=4)."""

    @pytest.mark.parametrize('bicim', ['anahtar_yok', 'acik_null', 'bos_dize'])
    def test_zorunlu_alan_eksikse_422_ve_ADIYLA(self, istemci, bicim):
        from hrma.app import FLOW_REQUIRED_FIELDS
        for ad in FLOW_REQUIRED_FIELDS:
            yuk = dict(AKIS_TAM)
            if bicim == 'anahtar_yok':
                yuk.pop(ad)
            else:
                yuk[ad] = None if bicim == 'acik_null' else ''
            kod, g = _gonder(istemci, '/api/flow-analysis', yuk)
            assert kod == 422, '%s/%s eksikken çözüldü (HTTP %d)' % (
                ad, bicim, kod)
            assert g['error'] == 'incomplete_flow_input'
            assert g['missing_fields'] == [ad], g
            # Hiçbir sayı yayımlanmadı ve künye kanalı da susturuldu.
            assert 'flow' not in g and 'performance' not in g, g
            assert g.get('defaults_applied') is None, g

    def test_soguk_panel_govdesi_cozulmez(self, istemci):
        """Panelin SOĞUK hâli: motorun hiçbir alanı yok."""
        kod, g = _gonder(istemci, '/api/flow-analysis',
                       {'fidelity': 'engineering',
                        'kinetic_fidelity': 'engineering'})
        assert kod == 422, 'motorsuz gövde hâlâ itki yayımlıyor'
        from hrma.app import FLOW_REQUIRED_FIELDS
        assert sorted(g['missing_fields']) == sorted(FLOW_REQUIRED_FIELDS)

    def test_lule_geometrisi_UYDURULMAZ(self, istemci):
        """ε=4 sessiz varsayılanı kalktı: iki yazımdan biri ADIYLA istenir."""
        yuk = {k: v for k, v in AKIS_TAM.items() if k != 'expansion_ratio'}
        kod, g = _gonder(istemci, '/api/flow-analysis', yuk)
        assert kod == 422, 'geometrisiz gövde hâlâ çözülüyor'
        assert sorted(g['missing_fields']) == ['exit_diameter',
                                               'expansion_ratio']
        for kayit in g['invalid_fields']:
            assert kayit['reason'] == 'required_one_of'
            assert kayit['accepted_alternatives'], kayit
            assert kayit['basis'], kayit

    @pytest.mark.parametrize('anahtar,deger',
                             [('expansion_ratio', 8.0),
                              ('exit_diameter', 0.0848528137423857)])
    def test_iki_yazimdan_biri_YETER(self, istemci, anahtar, deger):
        yuk = {k: v for k, v in AKIS_TAM.items() if k != 'expansion_ratio'}
        yuk[anahtar] = deger
        kod, g = _gonder(istemci, '/api/flow-analysis', yuk)
        assert kod == 200, g

    def test_sessiz_epsilon_satiri_KAYNAKTA_YOK(self):
        metin = (KOK_D332 / 'hrma' / 'app.py').read_text(encoding='utf-8')
        i = metin.find('def flow_analysis(')
        assert i > 0
        j = metin.find('\n@app.route(', i)
        assert j > i, 'flow_analysis sonu bulunamadı'
        govde = metin[i:j]
        assert 'expansion_ratio = 4.0' not in govde, (
            'sessiz ε=4 varsayılanı geri gelmiş')
        assert '_flow_eksik = [ad for ad in FLOW_REQUIRED_FIELDS' in govde, (
            'kapı alan-alan hâlinden geri dönmüş')

    def test_form_alani_ON_DOLU_DOGMAZ(self):
        """OH-D32-13'ün form ayağı: ``exit_diameter`` sayıyla doğmaz."""
        js = (KOK_D332 / 'hrma' / 'static' / 'js' / 'panels' /
              'flow_panel.js').read_text(encoding='utf-8')
        m = re.search(r"\['exit_diameter',\s*'[^']*',\s*([^,]+),", js)
        assert m, 'exit_diameter alan satırı bulunamadı'
        assert m.group(1).strip() == "''", (
            'alan hâlâ sayıyla ön-dolu doğuyor: %s' % m.group(1))

    def test_zorunlu_alti_alan_da_BOS_DOGAR(self):
        """Kapının ürün yolundan erişilebilir kalmasının şartı."""
        js = (KOK_D332 / 'hrma' / 'static' / 'js' / 'panels' /
              'flow_panel.js').read_text(encoding='utf-8')
        from hrma.app import FLOW_REQUIRED_FIELDS
        for ad in FLOW_REQUIRED_FIELDS:
            m = re.search(r"\['%s',\s*'[^']*',\s*([^,]+)," % ad, js)
            assert m, '%s alan satırı bulunamadı' % ad
            assert m.group(1).strip() == "''", (
                '%s yeniden ön-dolu: %s' % (ad, m.group(1)))


# ===========================================================================
# OH-D32-16 — _collect_unphysical_fields tel biçimi kapısı
# ===========================================================================
ALTI_DOF = {
    'body_diameter': 0.1, 'body_length': 2.0, 'nose_length': 0.3,
    'dry_mass': 10.0, 'rail_length': 3.0, 'thrust': 1000.0, 'burn_time': 5.0,
    'x_cg_full': 1.0, 'x_cg_empty': 1.1, 'propellant_mass': 2.0,
    'fin_count': 3, 'fin_root_chord': 0.1, 'fin_tip_chord': 0.05,
    'fin_span': 0.08, 'fin_sweep': 0.03, 'fin_position': 1.8,
}
YAPISAL = {'chamber_pressure': 40, 'chamber_diameter': 0.1,
           'chamber_length': 0.5, 'throat_diameter': 0.02, 'burn_time': 10,
           'material': 'steel_4130'}
TERMAL = {'chamber_pressure': 40, 'chamber_temperature': 3000,
          'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10,
          'mdot_total': 1.0, 'wall_thickness': 0.005, 'material': 'steel',
          'cooling_type': 'natural'}


class TestOHD3216TelBicimi:
    """ÖLÇÜLDÜ (``a1/once_gerekce_kanonu.json`` K1/K2): dört dize biçimi
    (``'20.0'``, ``'20'``, ``'2e1'``, ``' 20.0 '``) kapıdan geçiyordu ve
    üç uç aynı dizeye HTTP 200 veriyordu (``/calculate`` 400 verirken)."""

    @pytest.mark.parametrize('dize', ['20.0', '20', '2e1', ' 20.0 '])
    def test_sayi_benzeri_dize_KABUL_EDILMEZ(self, dize):
        from hrma.app import _collect_unphysical_fields
        ihlaller = _collect_unphysical_fields({'x': dize}, positive=('x',))
        assert len(ihlaller) == 1, (
            'sayı-benzeri dize %r sessizce kabul edildi' % dize)
        assert ihlaller[0]['reason'] == 'not_a_json_number', ihlaller

    def test_gercek_sayi_GECER(self):
        from hrma.app import _collect_unphysical_fields
        assert _collect_unphysical_fields({'x': 20.0}, positive=('x',)) == []

    @pytest.mark.parametrize('yol,taban,alan', [
        ('/api/six-dof-analysis', ALTI_DOF, 'body_diameter'),
        ('/analyze_structural_safety', YAPISAL, 'chamber_pressure'),
        ('/analyze_thermal_safety', TERMAL, 'chamber_pressure'),
    ])
    def test_uc_dizeyi_ADIYLA_reddeder(self, istemci, yol, taban, alan):
        yuk = dict(taban)
        yuk[alan] = str(taban[alan])
        kod, g = _gonder(istemci, yol, yuk)
        assert 400 <= kod < 500, (
            '%s: %s dizesi hüküm aldı (HTTP %d)' % (yol, alan, kod))
        assert alan in {k.get('field')
                        for k in (g.get('invalid_fields') or [])}, g
        assert 'not_a_json_number' in _gerekce_kumesi(g), g

    def test_saglikli_govde_BOZULMADI(self, istemci):
        kod, _g = _gonder(istemci, '/api/six-dof-analysis', dict(ALTI_DOF))
        assert kod == 200


# ===========================================================================
# OH-D32-15 — gerekçe kodu kanonu (bir olgu, bir ad)
# ===========================================================================
NAN = float('nan')
INF = float('inf')
AKIS_KANON = dict(AKIS_TAM, expansion_ratio=4.0, throat_diameter=0.02,
                  chamber_temperature=3000.0, gamma=1.2,
                  molecular_weight=24.0)

INPUTERROR_UCLARI = [
    ('/api/oxidizer-properties', {'oxidizer_type': 'n2o'}, 'temperature'),
    ('/api/altitude-to-pressure', {}, 'altitude'),
    ('/api/get-fuel-properties', {'fuel_type': 'htpb'}, 'temperature'),
    ('/api/flow-analysis', AKIS_KANON, 'chamber_diameter'),
    ('/calculate_liquid',
     {'motor_name': 'X', 'thrust': 10000.0, 'burn_time': 30.0,
      'chamber_pressure': 30.0, 'mixture_ratio': 2.2, 'fuel_type': 'rp1',
      'oxidizer_type': 'lox', 'expansion_ratio': 12.0}, 'tank_pressure'),
]

#: fix-35d kanonu (OH-D31-10) — ``tests/test_fix35d_gerekce_kodu_kanonu.py``
KANON = {True: 'boolean_is_not_a_number', 'yirmi': 'not_a_json_number',
         NAN: 'not_finite', INF: 'not_finite'}


class TestOHD3215GerekceKanonu:
    """ÖLÇÜLDÜ (``a1/once_gerekce_kanonu.json`` K3): beş uç ``bool``,
    metin, ``NaN`` ve ``inf`` için AYNI ``not_a_finite_number`` kodunu,
    altıncısı ``not_a_finite_number_or_out_of_range`` bileşiğini
    basıyordu."""

    @pytest.mark.parametrize('yol,taban,alan', INPUTERROR_UCLARI,
                             ids=[y for y, _t, _a in INPUTERROR_UCLARI])
    @pytest.mark.parametrize('deger', list(KANON),
                             ids=['bool', 'metin', 'nan', 'inf'])
    def test_neden_ADIYLA_ayrilir(self, istemci, yol, taban, alan, deger):
        yuk = dict(taban)
        yuk[alan] = deger
        kod, g = _gonder(istemci, yol, yuk)
        assert 400 <= kod < 500, (yol, alan, deger, kod)
        gerekceler = _gerekce_kumesi(g)
        assert KANON[deger] in gerekceler, (yol, alan, deger, g)

    def test_EMEKLI_adlar_kaynakta_YAYIMLANMAZ(self):
        """``not_a_finite_number`` ailesi hiçbir ret gövdesinde geçmez."""
        metin = (KOK_D332 / 'hrma' / 'app.py').read_text(encoding='utf-8')
        for satir in metin.split('\n'):
            if "'reason'" not in satir and "'reason':" not in satir:
                continue
            assert 'not_a_finite_number' not in satir, (
                'emekli ad ret gövdesine geri gelmiş: %s' % satir.strip())

    def test_kanon_TEK_KAYNAKTAN_okunur(self):
        """Üç soru altı uçta ikinci kez yazılmaz."""
        from hrma.app import _kanonik_gerekce
        assert _kanonik_gerekce(True) == 'boolean_is_not_a_number'
        assert _kanonik_gerekce('20.0') == 'not_a_json_number'
        assert _kanonik_gerekce(NAN) == 'not_finite'
        assert _kanonik_gerekce(INF) == 'not_finite'
        assert _kanonik_gerekce(20.0) is None
        assert _kanonik_gerekce(20.0, sayi_ise='out_of_range') == \
            'out_of_range'

    def test_numpy_bool_da_BOOL_sayilir(self):
        """``numpy.bool_`` ``bool``un alt sınıfı DEĞİLDİR (ördek denetimi)."""
        np = pytest.importorskip('numpy')
        from hrma.app import _kanonik_gerekce
        assert _kanonik_gerekce(np.bool_(True)) == 'boolean_is_not_a_number'


# ===========================================================================
# OH-D33-03 — /calculate: mdot_fuel ve Pc_bar sessizce yutuluyordu
# ===========================================================================
HIBRIT_TABAN = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
                'chamber_pressure': 20.0, 'fuel_type': 'htpb',
                'oxidizer_type': 'n2o'}


class TestOHD3303YutulanAlanlar:
    """ÖLÇÜLDÜ (``a1/once_ohd3303.json`` K1): ``mdot_fuel`` ve ``Pc_bar``
    gönderen SEKİZ isteğin sekizi de (0 / -2 / gerçek değer / 1e9) alanı
    hiç göndermeyen istekle BİT-AYNI yanıt veriyordu (sha256
    ``f24703dd...``, HTTP 200) ve yutulduğunu söyleyen yaprak yoktu."""

    @pytest.mark.parametrize('deger', [0, -2, 0.0644, 1e9])
    def test_mdot_fuel_HESAPLANAN_ALAN_reddedilir(self, istemci, deger):
        yuk = dict(HIBRIT_TABAN, mdot_fuel=deger)
        kod, g = _gonder(istemci, '/calculate', yuk)
        assert kod == 422, 'mdot_fuel=%r sessizce yutuldu' % deger
        assert g['error'] == 'computed_field_not_an_input'
        kayit = g['invalid_fields'][0]
        assert kayit['field'] == 'mdot_fuel'
        assert kayit['reason'] == 'computed_output_not_accepted_as_input'
        assert kayit['published_as'] == 'motor.mdot_f'
        assert 'motor' not in g, 'reddedilen istekte tasarım yayımlandı'

    @pytest.mark.parametrize('deger', [0, -2, 20.0, 1e9])
    def test_Pc_bar_OKUNMAYAN_ES_AD_reddedilir(self, istemci, deger):
        yuk = dict(HIBRIT_TABAN)
        yuk['Pc_bar'] = deger
        kod, g = _gonder(istemci, '/calculate', yuk)
        assert kod == 422, 'Pc_bar=%r sessizce yutuldu' % deger
        assert g['error'] == 'unread_canonical_field'
        kayit = g['invalid_fields'][0]
        assert kayit['field'] == 'Pc_bar'
        assert kayit['reason'] == 'field_not_read'
        # Çıkmaz sokak değil: gösterilecek bir ad VAR.
        assert kayit['use_instead'] == 'chamber_pressure'
        assert kayit['use_instead_unit'] == 'bar'

    def test_mdot_ox_KAPISI_yerinde(self, istemci):
        """OH-UC-11'in kapısı kapsam büyümesinde kaybolmadı."""
        kod, g = _gonder(istemci, '/calculate', dict(HIBRIT_TABAN,
                                                   mdot_ox=0.3866))
        assert kod == 422
        assert g['invalid_fields'][0]['field'] == 'mdot_ox'
        assert g['invalid_fields'][0]['published_as'] == 'motor.mdot_ox'

    def test_saglikli_govde_BOZULMADI(self, istemci):
        kod, g = _gonder(istemci, '/calculate', dict(HIBRIT_TABAN))
        assert kod == 200, g.get('error')
        assert (g.get('motor') or {}).get('mdot_f') is not None


# ===========================================================================
# OH-D33-04 — motor_validator özel metodu modül dışından çağrılıyordu
# ===========================================================================
class TestOHD3304KamuyaAcikBantKapisi:

    def test_public_sarmalayici_VAR_ve_ayni_sonucu_dondurur(self):
        from hrma.app import motor_validator
        govde = {'ambient_temp': 5000}
        assert hasattr(motor_validator, 'check_band_problems')
        assert (motor_validator.check_band_problems(govde)
                == motor_validator._bant_sorunlari(govde)), (
            'sarmalayıcı iç uygulamadan AYRIŞMIŞ — ikinci bir kural doğmuş')

    def test_app_ozel_adi_CAGIRMIYOR(self):
        metin = (KOK_D332 / 'hrma' / 'app.py').read_text(encoding='utf-8')
        assert 'motor_validator._bant_sorunlari(' not in metin, (
            'modül dışından ``_``-adı çağrısı geri gelmiş')
        assert 'motor_validator.check_band_problems(' in metin

    def test_kapi_HALA_calisiyor(self, istemci):
        """Sarmalayıcı kuralı değiştirmedi: zarf dışı ortam sıcaklığı 400."""
        kod, g = _gonder(istemci, '/api/quick-geometry',
                       {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
                        'chamber_pressure': 20.0, 'fuel_type': 'htpb',
                        'oxidizer_type': 'n2o', 'ambient_temp': 5000})
        assert kod == 400, g
        assert 'ambient_temp' in {k.get('field')
                                  for k in (g.get('invalid_fields') or [])}


# ===========================================================================
# OH-D33-07 — girdaplı enjektör hedef açısı sessizce kırpılıyordu
# ===========================================================================
SWIRL_TABAN = dict(HIBRIT_TABAN, injector_type='swirl', n_slots=6,
                   slot_width=1.0, slot_height=2.0,
                   swirl_chamber_diameter=20.0)


class TestOHD3307SwirlZarfi:
    """ÖLÇÜLDÜ (``a1/once_ohd3307.json`` K1): ``swirl_angle = 85`` HTTP 200
    alıyor ve yanıtta ``injector.spray_half_angle_target_deg = 71,2``
    yayımlanıyordu — kullanıcının açısı sessizce zarfa kırpılıp ONUN
    etiketiyle geri veriliyordu (``0,5`` -> ``3,7`` aynı şekilde)."""

    @pytest.mark.parametrize('aci', [0.5, 1.0, 85.0, 90.0, 180.0])
    def test_zarf_disi_ADIYLA_reddedilir(self, istemci, aci):
        kod, g = _gonder(istemci, '/calculate', dict(SWIRL_TABAN,
                                                   swirl_angle=aci))
        assert kod == 422, 'swirl_angle=%s kırpılarak çözüldü' % aci
        assert g['error'] == 'swirl_angle_outside_solver_envelope'
        kayit = g['invalid_fields'][0]
        assert kayit['field'] == 'swirl_angle'
        assert kayit['reason'] == 'out_of_range'
        assert kayit['unit'] == 'deg'
        assert kayit['submitted'] == aci
        assert 'injector' not in g, 'reddedilen istekte enjektör yayımlandı'

    def test_bant_COZUCUNUN_KENDI_zarfindan_okunur(self, istemci):
        """Sayı ikinci kez yazılmadı (Doktrin 4)."""
        from hrma.engines.injector_design import (
            _SWIRL_THETA_MIN_DEG, _SWIRL_THETA_MAX_DEG)
        kod, g = _gonder(istemci, '/calculate', dict(SWIRL_TABAN,
                                                   swirl_angle=90.0))
        assert kod == 422
        assert g['invalid_fields'][0]['accepted_range'] == [
            _SWIRL_THETA_MIN_DEG, _SWIRL_THETA_MAX_DEG]

    @pytest.mark.parametrize('aci', [3.7, 45.0, 71.2])
    def test_zarf_ICI_deger_cozulur(self, istemci, aci):
        # V301/E2: yuva ölçüsü (genişlik × yükseklik) atomizör sabiti K'yı ve
        # onunla sprey açısını ZATEN belirler; eskiden hedef açı bu durumda
        # yalnız bir uyarıyla YOK SAYILIYOR ve HTTP 200 dönüyordu (kullanıcının
        # açısı yayımlanan enjektörün açısı değildi — OH-D33-07'nin kardeşi).
        # Artık ikisi birden 422'dir (``conflicts_with_slot_geometry``,
        # tests/test_v301_enjektor_genel_*.py). Zarf İÇİ açının ÇÖZÜLDÜĞÜNÜ
        # ölçmek için yuva ölçüsü gönderilmez; açı devreye girer ve
        # yayımlanan yarı açı istenen açıdır (iddia güçlendi).
        govde = {k: v for k, v in SWIRL_TABAN.items()
                 if k not in ('slot_width', 'slot_height')}
        kod, g = _gonder(istemci, '/calculate', dict(govde, swirl_angle=aci))
        assert kod == 200, g
        assert g['injector']['spray_half_angle_deg'] == pytest.approx(
            aci, rel=1e-9)

    def test_alan_verilmeyince_KAPI_DOKUNMAZ(self, istemci):
        kod, _g = _gonder(istemci, '/calculate', dict(SWIRL_TABAN))
        assert kod == 200

    def test_form_zarf_disini_SUNMUYOR(self):
        """ÖK-22: kapı sağlıklı envanteri daraltmıyor (OH-D32-14)."""
        from hrma.engines.injector_design import (
            _SWIRL_THETA_MIN_DEG, _SWIRL_THETA_MAX_DEG)
        adv = (KOK_D332 / 'hrma' / 'templates' /
               'advanced.html').read_text(encoding='utf-8')
        m = re.search(r'<input[^>]*id="swirl_angle"[^>]*>', adv)
        assert m, 'swirl_angle alanı bulunamadı'
        alt = float(re.search(r'min="([-\d.]+)"', m.group(0)).group(1))
        ust = float(re.search(r'max="([-\d.]+)"', m.group(0)).group(1))
        assert alt >= _SWIRL_THETA_MIN_DEG and ust <= _SWIRL_THETA_MAX_DEG, (
            'form zarf dışı açı sunuyor: [%s, %s]' % (alt, ust))


# ===========================================================================
# OH-UC-12 — ÇÜRÜTÜLDÜ: katı thrust bandı ZATEN bağlı (mandal)
# ===========================================================================
KATI_TABAN = {'motor_name': 'OHUC12', 'propellant_type': 'apcp',
              'grain_type': 'bates', 'chamber_pressure': 40.0,
              'thrust': 5000.0, 'burn_time': 3.0, 'chamber_diameter': 100.0,
              'grain_length': 500.0, 'core_diameter': 30.0,
              'expansion_ratio': 8.0}


class TestOHUC12KatiItkiBandi:
    """Kalemin ikinci yarısı ÖLÇÜMLE ÇÜRÜTÜLDÜ (``a1/once_ohuc12.json``):
    ``FORM_LIMITS['solid']`` gerçekten ``thrust`` satırı taşımıyor (K0) AMA
    ``thrust = 1e12`` HTTP 200 DEĞİL **400** alıyor — bant ``/calculate_solid``
    ucunda ``_tasarim_hedefi_kapisi`` ile ZATEN bağlı ve tek kaynağı
    çözücünün kendi zarfıdır (``SOLID_DESIGN_POINT``). Berke kararı gereği
    yeni bant sayısı İCAT EDİLMEDİ; bu sınıf yalnız bugünkü gerçeği
    mandallar ki kapı sessizce sökülmesin."""

    @pytest.mark.parametrize('itki', [1e9, 1e12])
    def test_zarf_disi_itki_ADIYLA_reddedilir(self, istemci, itki):
        kod, g = _gonder(istemci, '/calculate_solid', dict(KATI_TABAN,
                                                         thrust=itki))
        assert kod == 400, 'katı itki %g sessizce çözüldü' % itki
        kayit = [k for k in (g.get('invalid_fields') or [])
                 if k.get('field') == 'thrust']
        assert kayit, g
        assert kayit[0]['reason'] == 'out_of_range'
        assert kayit[0]['unit'] == 'N'
        assert kayit[0]['motor_form'] == 'solid'

    def test_bant_COZUCUNUN_zarfindan_okunur_SAYI_IKINCI_KEZ_YAZILMAZ(
            self, istemci):
        from hrma.engines.solid_rocket_engine import SOLID_DESIGN_POINT
        kod, g = _gonder(istemci, '/calculate_solid', dict(KATI_TABAN,
                                                         thrust=1e12))
        assert kod == 400
        kayit = [k for k in g['invalid_fields'] if k['field'] == 'thrust'][0]
        assert kayit['accepted_range'] == [
            float(SOLID_DESIGN_POINT['min_target_thrust']),
            float(SOLID_DESIGN_POINT['max_target_thrust'])], (
            'bant çözücünün zarfından KOPMUŞ — ikinci bir sayı yazılmış')

    def test_saglikli_kati_govde_cozulur(self, istemci):
        kod, g = _gonder(istemci, '/calculate_solid', dict(KATI_TABAN))
        assert kod == 200, g.get('error')

    def test_SAHTE_BEYAN_URETILMEZ(self, istemci):
        """Alan bant denetimli olduğu için "denetlenmedi" künyesi BASILMAZ.

        Doktrin 6 (sahte gösterge yasağı): ``inputs_not_band_checked``
        kanalı P7B4-19'un sözleşmesidir ve yalnız GERÇEKTEN denetlenmeyen
        alan için vardır; ``thrust`` denetlendiği hâlde oraya yazılsaydı
        künye yalan söylerdi.
        """
        kod, g = _gonder(istemci, '/calculate_solid', dict(KATI_TABAN))
        assert kod == 200
        kunye = g.get('inputs_not_band_checked') or []
        assert 'thrust' not in {k.get('field') for k in kunye
                                if isinstance(k, dict)}, kunye
