"""ÖH Dalga-27 / app-api aşama-1 bekçileri — P16S1-02 (+ ÇİFT P16S1-03).

Kalem: *"kapı YETERLİ değil: aynı fonksiyonda kapının 12 satır altında
``data.get('chamber_pressure', 20)`` sayı uyduruyor — kapı + varsayılan yan
yana durdukça kapı ateşlenemez"*. ÇİFT KALEM P16S1-03 aynı gövdenin
ÖLÇÜMÜdür (*"D1 form yedeği sökümü tek başına 2 ucu 500'e çevirir"*), bu
yüzden tek onarımla kapanır.

Bu aşamanın payı ölçüldü (``docs/scofield/raw/OH/D27/app-api/a1/once.json``,
taban ``8f083ca0``): AST envanteri 79 okuma / 11 uç; ``/calculate``in 24'ü
ÖK-21 (form katmanı) yüzünden kapalı, katı 5 + sıvı 3 kardeş kulvarların,
geriye ``/api/six-dof-analysis`` 17 + ``/parametric-analysis`` 14 = 31 okuma
kalıyor.

Onarımın üç ayağı ve her ayağın bekçisi:

1. TEK KAYNAK (Doktrin 4). 6-DOF aynı sayıyı İKİ yerde yazıyordu — okuma
   yerinde ve ~280 satır aşağıdaki ``_uc_varsayilanlari`` beyan tablosunda
   (K2: 17/17 alan çift yazılı). ``rail_length`` beyanı ise çözücü
   sabitinin (``DEFAULT_RAIL_LENGTH_M``) ikinci kopyasıydı.
   -> ``TestTekKaynakYedekTablosu``

2. BEYAN (ÖK-19). ``/parametric-analysis`` hiçbir yedeğini beyan
   etmiyordu (K4: 6/6 koşumda ``defaults_applied = null``).
   -> ``TestParametrikBeyanKanali``

3. KAZANILMAMIŞ HÜKÜM (Doktrin 1). Beyan çözüm DEĞİLDİR: ``body_diameter``
   gönderilmediğinde apoje 7 483,3472 -> 12 159,2597 m (+%62,5), statik marj
   3,0656 -> 7,0123 kalibre ve ``stable: true`` yine basılıyordu (K3).
   Süpürme ekseni (``param_start``/``param_end``) verilmediğinde ise eğri
   kullanıcının SORMADIĞI aralıkta çiziliyordu — orada beyan yetmez, kapı
   gerekir.
   -> ``TestKazanilmamisKararlilikHukmu``, ``TestSupurmeEkseniKapisi``
"""
import ast
import contextlib
import io
import os
from pathlib import Path

import pytest

os.environ.setdefault('HRMA_HEADLESS', '1')

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_KAYNAK_YOLU = REPO_ROOT / 'hrma' / 'app.py'
APP_KAYNAK = APP_KAYNAK_YOLU.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _sessiz_post(istemci, yol, yuk):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return istemci.post(yol, json=yuk)


def _rota_govdesi(rota):
    """``@app.route('<rota>')`` ile bezenmiş fonksiyonun AST düğümü."""
    agac = ast.parse(APP_KAYNAK)
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.FunctionDef):
            continue
        for dek in dugum.decorator_list:
            if (isinstance(dek, ast.Call)
                    and getattr(dek.func, 'attr', '') == 'route'
                    and dek.args
                    and isinstance(dek.args[0], ast.Constant)
                    and dek.args[0].value == rota):
                return dugum
    raise AssertionError('rota bulunamadı: %s' % rota)


def _sessiz_okumalar(rota):
    """``<x>.get('<ad>', <sayı>)`` — D26 a3 K11 betiğiyle AYNI desen."""
    okumalar = []
    for n in ast.walk(_rota_govdesi(rota)):
        if (isinstance(n, ast.Call)
                and getattr(n.func, 'attr', '') == 'get'
                and len(n.args) == 2
                and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)
                and isinstance(n.args[1], ast.Constant)
                and isinstance(n.args[1].value, (int, float))
                and not isinstance(n.args[1].value, bool)):
            okumalar.append((n.args[0].value, n.args[1].value, n.lineno))
    return okumalar


#: Tam tarif edilmiş araç — tek bir alanı düşürüp etkisini ölçmek için.
SIXDOF_TAM = {
    'body_diameter': 0.15, 'body_length': 2.5, 'nose_length': 0.4,
    'nose_type': 'ogive', 'dry_mass': 25.0, 'propellant_mass': 12.0,
    'cd0': 0.45, 'fin_count': 4, 'fin_root_chord': 0.2,
    'fin_tip_chord': 0.1, 'fin_span': 0.12, 'fin_sweep': 0.06,
    'thrust': 4000.0, 'burn_time': 6.0,
    'launch_elevation_deg': 85.0, 'launch_azimuth_deg': 10.0,
    'rail_length': 5.0, 'wind_speed': 3.0, 'wind_direction_deg': 45.0,
    'launch_altitude': 0.0, 't_max': 300.0,
}

PARAM_TAM = {
    'param_type': 'of_ratio', 'param_start': 2.0, 'param_end': 4.0,
    'param_steps': 3, 'motor_type': 'hybrid', 'thrust': 1000.0,
    'burn_time': 10.0, 'chamber_pressure': 20.0, 'of_ratio': 3.0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'nozzle_type': 'conical',
    'time_budget_s': 60.0,
}


# ===========================================================================
# 1) TEK KAYNAK — sayı iki kez yazılmaz
# ===========================================================================
class TestTekKaynakYedekTablosu:
    """``_SIXDOF_UC_VARSAYILANLARI`` tek yazım noktasıdır."""

    def test_okuma_yerinde_sayi_yazili_DEGIL(self):
        """6-DOF gövdesinde ``.get(ad, <sayı>)`` deseni KALMADI.

        ÖNCE (K1, taban ``8f083ca0``): 17 okuma. Ters mutasyon: tek bir
        okumayı eski hâline döndürmek bu testi kırar.
        """
        kalan = _sessiz_okumalar('/api/six-dof-analysis')
        assert kalan == [], (
            '6-DOF gövdesinde sayı uyduran okuma geri geldi: %r' % kalan)

    # ÖH D27 fix-27a — DÜĞÜM ADI ASCII'YE ÇEVRİLDİ (OH-D26-14).
    # Eski ad ``test_parametrik_gövdesinde_...`` içindeki ``ö``
    # yüzünden ``pytest 'tests/...::<ad>'`` elle yazıldığında
    # "no tests ran" veriyordu (çıkış kodu 5, kırmızı değil).
    # İddia ve gövde BİT-AYNI; yalnız ad saf ASCII oldu.
    def test_parametrik_govdesinde_sayi_yazili_DEGIL(self):
        """Parametrik gövdesinde de aynı desen KALMADI (önce 14 okuma)."""
        kalan = _sessiz_okumalar('/parametric-analysis')
        assert kalan == [], (
            'parametrik gövdesinde sayı uyduran okuma geri geldi: %r'
            % kalan)

    def test_beyan_tablosu_ELLE_YAZILMIYOR(self):
        """Sökülen ``_uc_varsayilanlari`` demeti geri gelmedi.

        O demet, okuma yerindeki 17 sayının İKİNCİ kopyasıydı; ikisinden
        biri değişirse yanıt kullanmadığı bir sayıyı beyan ederdi.
        """
        atamalar = [h.id
                    for n in ast.walk(ast.parse(APP_KAYNAK))
                    if isinstance(n, (ast.Assign, ast.AnnAssign))
                    for h in ast.walk(n.targets[0] if isinstance(n, ast.Assign)
                                      else n.target)
                    if isinstance(h, ast.Name)
                    and h.id == '_uc_varsayilanlari']
        assert atamalar == [], (
            'elle yazılmış ikinci varsayılan tablosu geri geldi')

    def test_ray_boyu_sayisi_UCTA_YAZILI_DEGIL(self):
        """``rail_length`` beyanı çözücü sabitinden OKUNUR, yazılmaz."""
        from hrma import app as app_modulu
        assert 'rail_length' not in app_modulu._SIXDOF_UC_VARSAYILANLARI
        gov = _rota_govdesi('/api/six-dof-analysis')
        bulundu = 0
        for n in ast.walk(gov):
            if not isinstance(n, ast.Dict):
                continue
            anahtar = {k.value: v for k, v in zip(n.keys, n.values)
                       if isinstance(k, ast.Constant)}
            if anahtar.get('field') is None:
                continue
            alan = anahtar['field']
            if not (isinstance(alan, ast.Constant)
                    and alan.value == 'rail_length'):
                continue
            bulundu += 1
            deger = anahtar.get('value')
            assert not isinstance(deger, ast.Constant), (
                'ray boyu sayısı beyan gövdesine ELLE yazıldı (%r); '
                'çözücü sabiti değişirse yanıt kullanmadığı sayıyı '
                'beyan eder' % getattr(deger, 'value', None))
        assert bulundu == 1, (
            'ray boyu beyanı bulunamadı ya da birden çok yerde: %d'
            % bulundu)
        assert 'DEFAULT_RAIL_LENGTH_M' in ast.get_source_segment(
            APP_KAYNAK, gov)

    def test_kullanilan_sayi_ile_beyan_edilen_sayi_AYNI_KAYNAKTAN(self,
                                                                  istemci):
        """Beyan, tablonun ta kendisini yankılar (ayrışamaz)."""
        from hrma import app as app_modulu
        yanit = _sessiz_post(istemci, '/api/six-dof-analysis',
                             {'thrust': 3000.0, 'burn_time': 5.0})
        assert yanit.status_code == 200
        govde = yanit.get_json()
        kunye = {k['field']: k['value']
                 for k in govde.get('defaults_applied') or []}
        assert kunye, 'düşülen yedekler beyan edilmiyor'
        for ad, deger in kunye.items():
            if ad == 'rail_length':
                continue                      # çözücü sabiti, ayrı sınandı
            beklenen = app_modulu._SIXDOF_UC_VARSAYILANLARI[ad][0]
            assert deger == beklenen, (
                '%s: beyan %r, tablo %r — iki kaynak ayrıştı'
                % (ad, deger, beklenen))
        # Eski sözleşme (``stability_basis.input_defaults_substituted``)
        # KALDIRILMADI: aynı bilgiyi taşımaya devam eder.
        ikame = govde['stability_basis']['input_defaults_substituted']
        assert ikame == kunye


# ===========================================================================
# 2) BEYAN — parametrik yedekleri artık ADIYLA yayımlanıyor
# ===========================================================================
class TestParametrikBeyanKanali:

    @pytest.fixture(scope='class')
    def tam_yanit(self, istemci):
        return _sessiz_post(istemci, '/parametric-analysis',
                            dict(PARAM_TAM)).get_json()

    def test_dusen_yedekler_beyan_ediliyor(self, tam_yanit):
        """ÖNCE (K4): ``defaults_applied`` 6/6 koşumda ``null``."""
        assert tam_yanit['status'] == 'success'
        alanlar = {k['field'] for k in tam_yanit.get('defaults_applied') or []}
        assert {'gamma', 'l_star', 'atmospheric_pressure'} <= alanlar, (
            'motor yedekleri beyan edilmiyor: %r' % sorted(alanlar))

    def test_supurulen_eksen_kunyeye_GIRMEZ(self, tam_yanit):
        """``of_ratio`` süpürülüyorsa her noktada istekten gelir."""
        alanlar = {k['field'] for k in tam_yanit.get('defaults_applied') or []}
        assert 'of_ratio' not in alanlar

    def test_kunye_nokta_basina_TEKRARLANMIYOR(self, tam_yanit):
        """20 nokta için aynı yedek 20 kez beyan edilmez."""
        alanlar = [k['field'] for k in tam_yanit.get('defaults_applied') or []]
        assert len(alanlar) == len(set(alanlar)), (
            'aynı alan birden çok kez beyan edildi: %r' % alanlar)

    def test_sentinel_alanlar_VARSAYIM_DIYE_BEYAN_EDILMIYOR(self, tam_yanit):
        """``0`` sentineli "çözücü türetsin" demektir, "0 varsaydım" değil."""
        gerekceler = {k['field']: k['reason']
                      for k in tam_yanit.get('defaults_applied') or []}
        for ad in ('expansion_ratio', 'thrust_coefficient',
                   'chamber_diameter_input'):
            assert gerekceler[ad] == 'not_supplied_solver_derives', (
                '%s sentineli varsayım gibi beyan ediliyor' % ad)
        assert gerekceler['gamma'] == 'not_supplied'

    def test_verilen_deger_kunye_URETMEZ(self, istemci):
        """Gönderilmiş alan için beyan yazılmaz (yankı değil, beyan)."""
        yanit = _sessiz_post(istemci, '/parametric-analysis',
                             dict(PARAM_TAM, gamma=1.19, l_star=1.4))
        govde = yanit.get_json()
        alanlar = {k['field'] for k in govde.get('defaults_applied') or []}
        assert 'gamma' not in alanlar and 'l_star' not in alanlar

    def test_yorunge_alanlari_yalniz_ISTENDIGINDE_beyan_edilir(self,
                                                               istemci,
                                                               tam_yanit):
        """``include_trajectory`` kapalıyken yörünge yedeği okunmaz."""
        alanlar = {k['field'] for k in tam_yanit.get('defaults_applied') or []}
        assert 'vehicle_mass_dry' not in alanlar
        yanit = _sessiz_post(istemci, '/parametric-analysis',
                             dict(PARAM_TAM, include_trajectory=True))
        govde = yanit.get_json()
        acik = {k['field'] for k in govde.get('defaults_applied') or []}
        assert {'vehicle_mass_dry', 'vehicle_diameter', 'launch_angle',
                'launch_altitude'} <= acik, (
            'yörünge aracı beyan edilmeden çizildi: %r' % sorted(acik))


# ===========================================================================
# 3) KAZANILMAMIŞ HÜKÜM — 6-DOF kararlılığı
# ===========================================================================
class TestKazanilmamisKararlilikHukmu:

    @pytest.mark.parametrize('alan', [
        'body_diameter', 'body_length', 'nose_length', 'nose_type',
        'fin_count', 'fin_root_chord', 'fin_tip_chord', 'fin_span',
        'fin_sweep'])
    def test_geometri_uydurulunca_hukum_YAYIMLANMAZ(self, istemci, alan):
        yuk = {k: v for k, v in SIXDOF_TAM.items() if k != alan}
        yanit = _sessiz_post(istemci, '/api/six-dof-analysis', yuk)
        assert yanit.status_code == 200
        govde = yanit.get_json()
        assert govde['summary']['stable'] is None, (
            '%s uydurulmuşken kararlılık hükmü basıldı' % alan)
        dayanak = govde['stability_basis']
        assert alan in dayanak['stability_verdict_withheld_because']
        assert alan in dayanak['stability_verdict_basis']

    def test_olculen_sayilar_SILINMEZ(self, istemci):
        """"Sayılar silinmez, yayımlanmayan hükümdür" (aero bandı öncülü)."""
        yuk = {k: v for k, v in SIXDOF_TAM.items() if k != 'fin_span'}
        ozet = _sessiz_post(istemci, '/api/six-dof-analysis',
                            yuk).get_json()['summary']
        assert ozet['stable'] is None
        for olcum in ('static_margin_full', 'static_margin_empty',
                      'x_cp', 'cn_alpha', 'apogee'):
            assert isinstance(ozet[olcum], float), (
                '%s ölçümü hükümle birlikte silindi' % olcum)

    def test_tam_tarif_edilmis_aracta_HUKUM_YAYIMLANIR(self, istemci):
        """Kapı meşru koşumu KESMEZ."""
        govde = _sessiz_post(istemci, '/api/six-dof-analysis',
                             dict(SIXDOF_TAM)).get_json()
        assert govde['summary']['stable'] is True
        assert 'stability_verdict_withheld_because' not in \
            govde['stability_basis']

    @pytest.mark.parametrize('alan', ['cd0', 'dry_mass', 'propellant_mass',
                                      'wind_speed', 'launch_elevation_deg'])
    def test_statik_marja_girmeyen_alan_hukmu_TUTMAZ(self, istemci, alan):
        """Kütle/sürükleme/atış alanları yörüngeyi değiştirir, marjı değil.

        Kapı bu yüzden onlara kapanmaz: ölçüldü (K3) — ``cd0`` düşünce
        apoje 7 483 -> 7 005 m ama ``static_margin_full`` 3,0656'da
        bit-aynı kalıyor. Kapıyı buraya genişletmek, hükmü hak eden bir
        koşumu susturmak olurdu.
        """
        yuk = {k: v for k, v in SIXDOF_TAM.items() if k != alan}
        govde = _sessiz_post(istemci, '/api/six-dof-analysis',
                             yuk).get_json()
        assert govde['summary']['stable'] is True
        assert 'stability_verdict_withheld_because' not in \
            govde['stability_basis']
        # ...ama düşülen yedek yine de ADIYLA beyan edilir.
        alanlar = {k['field'] for k in govde.get('defaults_applied') or []}
        assert alan in alanlar

    def test_hukumsuzluk_SUMMARY_ENVANTERINI_buyutmuyor(self, istemci):
        """ÖK-22: gerekçe ``stability_basis``e girer, ``summary``ye değil.

        ``tests/test_wave4b_contract.py`` ``summary`` bloğundaki her
        dürüstlük alanının panelde okunmasını ister; gerekçeyi oraya
        koymak o envanteri büyütürdü. Kullanıcı yüzü zaten doğrudur:
        ``sixdof_panel.js`` ``stable === null`` iken "STABILITY NOT
        EVALUATED" basar.
        """
        yuk = {k: v for k, v in SIXDOF_TAM.items() if k != 'fin_span'}
        ozet = _sessiz_post(istemci, '/api/six-dof-analysis',
                            yuk).get_json()['summary']
        assert 'stability_verdict_withheld_because' not in ozet
        assert 'stability_verdict_basis' not in ozet
        js = (REPO_ROOT / 'hrma' / 'static' / 'js'
              / 'sixdof_panel.js').read_text(encoding='utf-8')
        assert 'stabilityNotEvaluated' in js, (
            'panel null hükmü için ayrı bir yüz basmıyor — hüküm tutmak '
            'kullanıcıya UYDURMA bir "UNSTABLE" gösterir')


# ===========================================================================
# 4) SÜPÜRME EKSENİ — beyan yetmez, kapı gerekir
# ===========================================================================
class TestSupurmeEkseniKapisi:

    @pytest.mark.parametrize('alan', ['param_start', 'param_end'])
    def test_aralik_verilmezse_TARAMA_BASLAMAZ(self, istemci, alan):
        yuk = {k: v for k, v in PARAM_TAM.items() if k != alan}
        yanit = _sessiz_post(istemci, '/parametric-analysis', yuk)
        assert yanit.status_code == 422
        govde = yanit.get_json()
        assert govde['error'] == 'sweep_interval_not_supplied'
        assert [a['field'] for a in govde['invalid_fields']] == [alan]
        assert govde['invalid_fields'][0]['reason'] == 'not_supplied'
        # Sayı ÜRETİLMEZ: hiçbir nokta hesaplanmaz.
        assert 'results' not in govde and 'sweep_range' not in govde

    def test_bos_dize_de_VERILMEDI_sayilir(self, istemci):
        yanit = _sessiz_post(istemci, '/parametric-analysis',
                             dict(PARAM_TAM, param_start=''))
        assert yanit.status_code == 422
        assert yanit.get_json()['error'] == 'sweep_interval_not_supplied'

    def test_sifir_VERILMEDI_SAYILMAZ(self, istemci):
        """``0`` ile "verilmedi" karıştırılmaz (input_guard ilkesi)."""
        yanit = _sessiz_post(istemci, '/parametric-analysis',
                             dict(PARAM_TAM, param_start=0.0, param_end=1.0))
        assert yanit.status_code != 422 or \
            yanit.get_json().get('error') != 'sweep_interval_not_supplied'

    def test_aralik_verilince_ESKI_DAVRANIS_AYNEN(self, istemci):
        govde = _sessiz_post(istemci, '/parametric-analysis',
                             dict(PARAM_TAM)).get_json()
        assert govde['status'] == 'success'
        assert govde['sweep_range'] == [2.0, 4.0]
        assert len(govde['results']) == 3
