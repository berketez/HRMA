"""ÖH Dalga-28 / app-api aşama-1 bekçileri.

Ölçüm: ``docs/scofield/raw/OH/D28/app-api/a1/once.json`` (K1-K11) ve
``once2.json`` (gövdesi düzeltilmiş K3/K8/K9/K10/K11). Taban ``7cd08bcc``.

Kalemler:
  P7B4-19  UQ motor girdisi BANT kapısı (FORM_LIMITS tek kaynak)   ONARILDI
  P7B4-18  UQ yanıtı motorun kendi hüküm defterini taşır           ONARILDI
  OH-D27-18 hibrit UQ fabrikası ``oxidizer_type``ı OKUR            ONARILDI
  OH-D27-03 ``/parametric-analysis`` ``param_type`` fail-closed    ONARILDI
  P16B1-34 ``/api/generate-3d`` lüle geometrisi tutarlılığı        ONARILDI
  P16B1-30 ``/calculate`` istemci reddi 400 ⟷ sunucu arızası 500   ONARILDI
  P16B1-22 regression_a/n ayna kapıları                            ÇÜRÜTÜLDÜ
  P16B1-31 ``mdot_ox`` işareti                                     ÇÜRÜTÜLDÜ
  P16B1-33 cidar 0/negatif/okunamaz sınıflandırması                KISMEN
  P15B2-01 fail-closed merkezinin app-api kapsamı                  KISMEN
"""
import json

import pytest

from hrma.app import app as flask_app

# ---------------------------------------------------------------------------
# ÖH D31 fix-34b — ÜRÜN KAYNAĞI DOSYADAN OKUNUR (``inspect.getsource`` DEĞİL)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (``docs/scofield/raw/OH/D31/fix34/b/olcum_getsource_kaymasi.json``):
# taban kaydı-14 süiti PAYLAŞILAN ``main`` çalışma ağacında 64 dakika koştu;
# koşum sürerken D31 kulvar birleşmeleri main'e indi ve ``hrma/app.py`` ile
# ``hrma/engines/liquid_rocket_engine.py`` DİSKTE DEĞİŞTİ. Kod nesneleri içe
# aktarma anındaki (``93b1ab6f``) satır numaralarını taşıyordu;
# ``inspect.getsource`` ise ``linecache`` üzerinden DEĞİŞMİŞ dosyayı okudu.
# ``co_firstlineno`` yeni dosyada başka bir gövdenin ortasına düştü ve
# ``inspect.findsource`` o indeksten GERİYE doğru ilk ``def`` satırını arayıp
# KOMŞU fonksiyonun kaynağını döndürdü (ör. ``_run_uq_analysis`` yerine
# ``_uq_contract_body``, 114 satır kayma; ``flow_analysis`` yerine
# ``_run_kinetic_chain``, 37 satır). Kırmızı ürün kusuru değil, DEĞİŞEN AĞAÇ
# ÜZERİNDE ÖLÇÜM artefaktıydı — ve aynı kayma ters yönde SAHTE YEŞİL de
# üretebilirdi.
#
# Kapı gevşetilmedi, ÖLÇÜM SAĞLAMLAŞTIRILDI: aranan şey zaten ürünün KAYNAK
# METNİdir, o yüzden metin çalışma-anı nesnesinden değil DOSYADAN alınır ve
# hedef gövde AST ile ADIYLA bulunur. Sonuç dosya değişse bile ya doğru
# gövdedir ya da açık bir hatadır; sessiz kayma imkânsızdır.
def _urun_kaynagi(modul, *ad_yolu):
    """``modul``ün dosyasındaki ``ad_yolu`` gövdesinin kaynak metni."""
    import ast as _a
    import pathlib as _p
    yol = _p.Path(getattr(modul, '__file__', '') or '')
    assert yol.is_file(), 'modül dosyası bulunamadı: %r' % (yol,)
    metin = yol.read_text(encoding='utf-8')
    govde = _a.parse(metin).body
    dugum = None
    for ad in ad_yolu:
        dugum = next((d for d in govde
                      if isinstance(d, (_a.FunctionDef, _a.AsyncFunctionDef,
                                        _a.ClassDef)) and d.name == ad), None)
        assert dugum is not None, (
            '%s içinde %r tanımı yok (aranan yol: %s)'
            % (yol.name, ad, '.'.join(ad_yolu)))
        govde = dugum.body
    parca = _a.get_source_segment(metin, dugum)
    assert parca, 'kaynak parçası çıkarılamadı: %s' % '.'.join(ad_yolu)
    return parca



UQ_TABAN = {
    'motor_type': 'hybrid', 'level': 'fast', 'seed': 7, 'n_samples': 2,
    'inputs': {'thrust': 1000.0, 'chamber_pressure': 20.0, 'of_ratio': 6.0,
               'burn_time': 10.0, 'fuel_type': 'htpb',
               'oxidizer_type': 'n2o'},
}

CALC_TABAN = {'motor_name': 'X', 'thrust': 1000, 'burn_time': 10,
              'chamber_pressure': 20, 'of_ratio': 6.0,
              'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
              'nozzle_type': 'conical', 'l_star': 1.0}

PARAM_TABAN = dict(CALC_TABAN, param_start=3.0, param_end=4.0,
                   param_steps=3, time_budget_s=60.0)

GEO_TABAN = {'chamber_diameter': 0.5, 'chamber_length': 0.4,
             'port_diameter_initial': 0.1, 'throat_diameter': 0.05,
             'exit_diameter': 0.15}

REG_TABAN = {'burn_time': 10.0, 'mdot_ox': 0.38,
             'port_diameter_initial': 0.03, 'fuel_type': 'htpb',
             'fuel_density': 920.0, 'regression_a': 0.0001,
             'regression_n': 0.5, 'grain_length': 0.5,
             'chamber_length': 0.6}


@pytest.fixture(scope='module')
def istemci():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _post(c, yol, govde):
    r = c.post(yol, json=govde)
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, None


def _alanlar(govde):
    bulunan = set()

    def yur(x):
        if isinstance(x, dict):
            if isinstance(x.get('field'), str):
                bulunan.add(x['field'])
            for v in x.values():
                yur(v)
        elif isinstance(x, list):
            for v in x:
                yur(v)
    yur(govde)
    return bulunan


# ===========================================================================
# P7B4-19 — belirsizlik ucunun MOTOR GİRDİSİ BANDI
# ===========================================================================
class TestP7B419BelirsizlikBandKapisi:
    """ÖNCE (once.json K1): ``chamber_pressure = 1e9 bar`` üç motor tipinin
    ikisinde HTTP 200 + tam rapor (12 004 / 7 369 bayt); ``0,001 bar`` üç
    tipte de HTTP **500** ve gövdede ÇIPLAK çözücü metni ("No convergence
    in 500 iterations", "The function value at x=1e-06 is NaN",
    "SolidRocketEngine: Invalid grain geometry"); ``thrust = 1e12`` üç
    tipte de HTTP 200."""

    @pytest.mark.parametrize('deger', [1e9, 0.001])
    def test_bant_disi_basinc_adiyla_reddedilir(self, istemci, deger):
        kod, g = _post(istemci, '/api/uncertainty-analysis',
                       dict(UQ_TABAN,
                            inputs=dict(UQ_TABAN['inputs'],
                                        chamber_pressure=deger)))
        assert kod == 422, (kod, str(g)[:300])
        assert g['error'] == 'uncertainty_input_out_of_range'
        assert 'chamber_pressure' in _alanlar(g)
        assert 'outputs' not in g, 'reddedilen istek yine de rapor üretti'

    def test_bant_disi_itki_adiyla_reddedilir(self, istemci):
        kod, g = _post(istemci, '/api/uncertainty-analysis',
                       dict(UQ_TABAN,
                            inputs=dict(UQ_TABAN['inputs'], thrust=1e12)))
        assert kod == 422, (kod, str(g)[:200])
        assert 'thrust' in _alanlar(g)

    def test_ret_kabul_edilen_bandi_YAYIMLIYOR(self, istemci):
        kod, g = _post(istemci, '/api/uncertainty-analysis',
                       dict(UQ_TABAN,
                            inputs=dict(UQ_TABAN['inputs'],
                                        chamber_pressure=1e9)))
        kunye = [k for k in g['invalid_fields']
                 if k['field'] == 'chamber_pressure'][0]
        from hrma.validation.motor_validation import FORM_LIMITS
        alt, ust, birim = FORM_LIMITS['quick_geometry']['chamber_pressure']
        assert kunye['accepted_range'] == [alt, ust], (
            'yanıttaki bant FORM_LIMITS ile ayrışmış (Doktrin 4)')
        assert kunye['unit'] == birim
        assert kunye['container'] == 'inputs'

    def test_bant_ikinci_kez_yazilmadi(self):
        """Eşleme tablosu FORM_LIMITS'i GÖSTERİR, sayı taşımaz."""
        from hrma.app import _UQ_FORM_BY_MOTOR, _UQ_MOTOR_TYPES
        from hrma.validation.motor_validation import FORM_LIMITS
        assert set(_UQ_FORM_BY_MOTOR) == set(_UQ_MOTOR_TYPES)
        for tip, form in _UQ_FORM_BY_MOTOR.items():
            assert form in FORM_LIMITS, (tip, form)
        # Tablodaki değerler yalnız FORM adıdır — hiçbir SAYI taşımaz.
        for form in _UQ_FORM_BY_MOTOR.values():
            assert isinstance(form, str)

    def test_saglikli_govde_hala_200(self, istemci):
        kod, g = _post(istemci, '/api/uncertainty-analysis', UQ_TABAN)
        assert kod == 200, (kod, str(g)[:300])
        assert g['status'] == 'ok'
        assert g['outputs']['c_star']['nominal'] > 0

    # -- ÖH D33 denetim ŞARTI: KATI KOLU GÖRÜNÜR (P7B4-19 kalan borç) -----
    # Yukarıdaki ``test_bant_disi_itki_adiyla_reddedilir`` HİBRİT gövdeyi
    # sınar (``quick_geometry`` formunda ``thrust`` satırı VARDIR). KATI
    # formda o satır YOKTUR, yani aynı sayı orada denetlenmeden geçer
    # (ölçüldü: ``docs/scofield/raw/OH/D33/app-api-uc/a1/once.json`` K4,
    # taban ``56f88e70`` -> HTTP 200). Denetçi bunu "kapalı sayılan kalemin
    # görünmeyen yarısı" diye işaretledi; aşağıdaki düğümler o yarıyı
    # KİLİTLER: birincisi bugünkü ÖLÇÜLEN durumu dondurur (tabloya satır
    # girdiği gün KIRMIZI verip borcun kapandığını bildirir), ikincisi 200
    # dönen gövdenin denetlenmemiş alanı KENDİSİNİN söylediğini doğrular.
    # Bant SAYISI burada da YAZILMAZ — katı formun itki zarfı bir veri
    # kararıdır (OH-UC-12, Berke).
    # V301/K-A (22 Eki): eski çapa A_p/A_t = 0,947'lik boğulan portlu
    # varsayılan motoru kilitliyordu — burada UQ fabrikasının kendi
    # varsayılanları (çekirdek 30, a = 0,005; uq_adapters.py, K-A kapsamı
    # dışı, DEVİR) 20 bar'da A_p/A_t = 0,26 veriyor ve nominal artık
    # yayımlanmıyor (KT-23). Düğümün konusu itki bandı künyesidir; geçerli
    # portlu kısa tane verilir (L 100, çekirdek 70 mm).
    SOLID_TABAN = {
        'motor_type': 'solid', 'level': 'fast', 'seed': 7, 'n_samples': 2,
        'inputs': {'thrust': 1e12, 'chamber_pressure': 20.0,
                   'burn_time': 10.0, 'chamber_diameter': 100.0,
                   'grain_length': 100.0, 'core_diameter': 70.0},
    }

    def test_kati_itki_bandi_HENUZ_YOK_olculen_durum(self, istemci):
        """ÖLÇÜLEN DURUM KİLİDİ — borç kapanınca bu düğüm KIRMIZI verir.

        Bugün ``FORM_LIMITS['solid']``te ``thrust`` satırı yok, dolayısıyla
        ``inputs.thrust = 1e12`` HTTP 200 alıyor. Tabloya satır girdiği gün
        istek 422 alacak ve bu düğüm düşecek: düşüşü GÖRMEK için duruyor,
        kusuru KORUMAK için değil.
        """
        from hrma.validation.motor_validation import FORM_LIMITS
        assert 'thrust' not in FORM_LIMITS['solid'], (
            'kati forma thrust bandi girmis: borc kapandi. Bu dugumu 422 '
            'bekleyecek bicimde guncelle (bant sayisi OH-UC-12 / Berke '
            'veri kararidir).')
        kod, g = _post(istemci, '/api/uncertainty-analysis',
                       self.SOLID_TABAN)
        assert kod == 200, (kod, str(g)[:300])
        assert g['status'] == 'ok'

    def test_kati_itki_DENETLENMEDIGINI_yanit_soyluyor(self, istemci):
        """200 dönen gövde, hangi sayının denetlenmediğini ADIYLA yazar."""
        from hrma.validation.motor_validation import FORM_LIMITS
        kod, g = _post(istemci, '/api/uncertainty-analysis',
                       self.SOLID_TABAN)
        assert kod == 200, (kod, str(g)[:300])
        kunye = g.get('inputs_not_band_checked')
        assert kunye, ('katı kolda bant uygulanmayan alan var ama yanıt '
                       'bunu söylemiyor (P7B4-19 ŞARTI)')
        kayit = [k for k in kunye if k['field'] == 'thrust']
        assert kayit, [k['field'] for k in kunye]
        assert kayit[0]['reason'] == 'no_band_in_form_limits'
        assert kayit[0]['form'] == 'solid'
        # Künye TEK KAYNAKTAN türer: ilan edilen her ad gerçekten tabloda
        # OLMAYAN addır (liste elle yazılsaydı tablo büyüdüğünde yalan
        # söylerdi).
        for k in kunye:
            assert k['field'] not in FORM_LIMITS['solid'], k

    def test_bandi_OLAN_alan_kunyeye_girmez(self, istemci):
        """Sağlıklı hibrit gövdede her sayının bandı var -> künye DOĞMAZ."""
        kod, g = _post(istemci, '/api/uncertainty-analysis', UQ_TABAN)
        assert kod == 200, (kod, str(g)[:300])
        assert 'inputs_not_band_checked' not in g, (
            'boş künye "denetlendi, temiz" demek olurdu (sahte gösterge)')


# ===========================================================================
# P7B4-18 — motorun KENDİ hüküm defteri yanıtta
# ===========================================================================
class TestP7B418NominalHukumDefteri:
    """ÖNCE (once.json K2): sağlıklı hibrit gövdenin 19 üst anahtarının
    hiçbiri motorun ``design_warnings`` defterini taşımıyordu; yanıtta
    "anormal" dizesi 0 kez geçiyordu."""

    @pytest.fixture(scope='class')
    def yanit(self, istemci):
        kod, g = _post(istemci, '/api/uncertainty-analysis', UQ_TABAN)
        assert kod == 200, (kod, str(g)[:300])
        return g

    def test_defter_yanitta(self, yanit):
        defter = yanit.get('nominal_design_warnings')
        assert defter, 'motorun hüküm defteri yanıtta yok (P7B4-18)'
        assert all(isinstance(k, dict) and k.get('code') for k in defter)

    def test_defter_MOTORUN_kendi_kaydi_UYDURULMADI(self, yanit):
        """Yayımlanan kodlar motorun gerçekten ürettiği kodlardır."""
        from hrma.analysis import uq_adapters as ua
        f = ua.make_factory('hybrid', dict(UQ_TABAN['inputs']))
        f({})
        beklenen = {k['code'] for k in (f.nominal_design_warnings or [])}
        yayin = {k['code'] for k in yanit['nominal_design_warnings']}
        assert yayin == beklenen, (yayin, beklenen)

    def test_defter_bos_ise_alan_KONMAZ(self):
        """Boş liste "denetlendi, temiz" demek olurdu — sahte gösterge.

        Kaynak metin DOSYADAN, AST ile alınır (bkz. ``_urun_kaynagi``
        başlığındaki ölçüm): ``inspect.getsource`` değişen ağaçta komşu
        gövdeyi döndürebiliyordu.
        """
        from hrma import app as app_modulu
        kaynak = _urun_kaynagi(app_modulu, '_run_uq_analysis')
        assert 'if _defter:' in kaynak, (
            'defter boşken de alan konuyor (sahte gösterge yasağı)')


# ===========================================================================
# OH-D27-18 — hibrit UQ fabrikası oxidizer_type'ı OKUR
# ===========================================================================
class TestOHD2718OksitleyiciOkunuyor:
    """ÖNCE (once.json K6): ``oxidizer_type`` 'n2o' ⟷ 'lox' iki istek
    BİT-AYNI rapor alıyordu (``iki_oksitleyici_ayni = true``) ve yanıt
    yalnız "supplied but ... does not read it" beyanı taşıyordu."""

    def test_iki_oksitleyici_farkli_cevap_verir(self, istemci):
        c_star = {}
        for ox in ('n2o', 'lox'):
            kod, g = _post(istemci, '/api/uncertainty-analysis',
                           dict(UQ_TABAN,
                                inputs=dict(UQ_TABAN['inputs'],
                                            oxidizer_type=ox)))
            assert kod == 200, (ox, kod, str(g)[:200])
            c_star[ox] = g['outputs']['c_star']['nominal']
        assert c_star['n2o'] != c_star['lox'], (
            'iki farklı oksitleyici hâlâ BİT-AYNI c* veriyor: %r' % c_star)

    def test_alan_artik_OKUNMAYAN_diye_beyan_edilmiyor(self, istemci):
        kod, g = _post(istemci, '/api/uncertainty-analysis', UQ_TABAN)
        okunmayan = {k['field'] for k in (g.get('inputs_not_read') or [])}
        assert 'oxidizer_type' not in okunmayan

    def test_tek_kaynak_listesi_alani_taniyor(self):
        from hrma.analysis.uq_adapters import FACTORY_INPUT_FIELDS
        assert 'oxidizer_type' in FACTORY_INPUT_FIELDS['hybrid']

    def test_varsayilan_IKINCI_kez_yazilmadi(self):
        """Alan gelmediğinde motorun KENDİ imza varsayılanı geçerlidir."""
        import inspect
        from hrma.analysis import uq_adapters as ua
        kaynak = inspect.getsource(ua.make_hybrid_factory)
        assert "data.get('oxidizer_type')" in kaynak
        assert "oxidizer_type=data.get('oxidizer_type', 'n2o')" not in kaynak


# ===========================================================================
# OH-D27-03 — /parametric-analysis param_type fail-closed
# ===========================================================================
class TestOHD2703SupurmeEkseniAdi:
    """ÖNCE (once.json K7): ``param_type`` HİÇ gönderilmediğinde uç
    sessizce ``'of_ratio'``ya düşüyor ve yanıt, ``param_type='of_ratio'``
    gönderen isteğinkiyle BİT-AYNI (860 bayt) çıkıyordu."""

    def test_gonderilmeyen_eksen_adiyla_reddedilir(self, istemci):
        kod, g = _post(istemci, '/parametric-analysis', dict(PARAM_TABAN))
        assert kod == 422, (kod, str(g)[:200])
        assert g['error'] == 'sweep_parameter_not_supplied'
        assert g['field'] == 'param_type'
        assert g['reason'] == 'not_supplied'
        assert 'results' not in g, 'reddedilen tarama nokta üretti'

    @pytest.mark.parametrize('deger', [None, '', '   '])
    def test_bos_eksen_de_verilmedidir(self, istemci, deger):
        kod, g = _post(istemci, '/parametric-analysis',
                       dict(PARAM_TABAN, param_type=deger))
        assert kod == 422
        assert g['error'] == 'sweep_parameter_not_supplied'

    def test_adlandirilan_eksen_hala_kosuyor(self, istemci):
        kod, g = _post(istemci, '/parametric-analysis',
                       dict(PARAM_TABAN, param_type='of_ratio'))
        assert kod == 200, (kod, str(g)[:200])
        assert g['status'] == 'success'

    def test_taninmayan_ad_ESKI_gerekcesiyle_reddedilir(self, istemci):
        """Yeni kapı, mevcut ``unwired_sweep_parameter`` hükmünü YEMEZ."""
        kod, g = _post(istemci, '/parametric-analysis',
                       dict(PARAM_TABAN, param_type='altitude'))
        assert kod == 422
        assert g['error'] == 'unwired_sweep_parameter'


# ===========================================================================
# P16B1-34 — /api/generate-3d geometri tutarlılığı
# ===========================================================================
class TestP16B134CizimGeometriKapisi:
    """ÖNCE (once2.json K11): boğaz odadan BÜYÜK (0,5 ⟷ 0,05 m) ve çıkış
    boğazdan KÜÇÜK (0,05 ⟷ 0,2 m) gövdeleri HTTP 200 + sahne alıyordu
    (9 073 / 8 973 bayt); uç gövdesinde doğrulayıcı çağrısı 0 idi."""

    @pytest.mark.parametrize('yama,alan', [
        ({'chamber_diameter': 0.05, 'throat_diameter': 0.5,
          'exit_diameter': 0.9}, 'throat_diameter'),
        ({'throat_diameter': 0.2, 'exit_diameter': 0.05}, 'exit_diameter'),
    ])
    def test_celiskili_geometri_cizilmez(self, istemci, yama, alan):
        kod, g = _post(istemci, '/api/generate-3d',
                       {'motor_data': dict(GEO_TABAN, **yama)})
        assert kod == 422, (kod, str(g)[:200])
        assert g['status'] == 'inconsistent_geometry'
        assert alan in _alanlar(g)
        assert 'plot_data' not in g, 'reddedilen geometri yine de çizildi'

    def test_tutarli_geometri_hala_ciziliyor(self, istemci):
        kod, g = _post(istemci, '/api/generate-3d',
                       {'motor_data': dict(GEO_TABAN)})
        assert kod == 200, (kod, str(g)[:200])
        assert g['status'] == 'success' and g.get('plot_data')

    def test_kural_TEK_KAYNAK(self):
        """Doğrulayıcı ile çizim ucu AYNI işlevi okur (Doktrin 4)."""
        import inspect
        from hrma.validation import motor_validation as mv
        assert 'nozzle_geometry_errors' in inspect.getsource(
            mv.MotorDataValidator._check_physical_consistency), (
            'sınıf metodu kuralı yeniden yazıyor')
        from hrma.app import generate_3d
        assert 'nozzle_geometry_errors' in inspect.getsource(generate_3d)

    def test_eksik_alan_TUTARLILIK_kapisina_takilmaz(self):
        """Kapı bir varlık kapısı değildir: eksik alan sessizce geçer."""
        from hrma.validation.motor_validation import nozzle_geometry_errors
        assert nozzle_geometry_errors({}) == []
        assert nozzle_geometry_errors({'throat_diameter': 0.05}) == []


# ===========================================================================
# P16B1-30 — istemci hatası ⟷ sunucu arızası
# ===========================================================================
class TestP16B130HataSinifi:
    """ÖNCE (once2.json K8): sekiz sarsımın 6'sı doğrulama kapısından
    (``status`` VAR, ``error_type`` YOK) 1'i yakalayıcı daldan
    (``error_type`` VAR, ``status`` YOK) HTTP 400 alıyordu; ayrım yalnız
    bir alanın VARLIĞINDAN çıkarılabiliyor ve hiçbir yerde yazılı değildi."""

    def test_istemci_reddi_400_ve_ADIYLA_sinifli(self, istemci):
        kod, g = _post(istemci, '/calculate',
                       dict(CALC_TABAN, fuel_type='peynir'))
        assert kod == 400, (kod, str(g)[:200])
        assert g['error_class'] == 'client_input'
        assert g['status'] == 'invalid_input'
        assert g['field'] == 'fuel_type'

    def test_sunucu_arizasi_400_ile_GIZLENMEZ(self, istemci, monkeypatch):
        """ValueError OLMAYAN istisna 4xx ile örtülemez (kardeş uçların
        ``EngineContractViolation`` -> 500 kuralının aynısı)."""
        import hrma.app as app_mod

        class _Bozuk:
            def __init__(self, *a, **k):
                raise TypeError('sunucu tarafi kirildi (bekci)')

        monkeypatch.setattr(app_mod, 'HybridRocketEngine', _Bozuk)
        kod, g = _post(istemci, '/calculate', dict(CALC_TABAN))
        assert kod == 500, (kod, str(g)[:300])
        assert g['error_class'] == 'server_fault'
        assert g['status'] == 'error'

    def test_iki_dal_da_status_tasiyor(self, istemci):
        """Tüketici bir alanın VARLIĞINI koklamak zorunda kalmaz."""
        for yama in ({'fuel_type': 'peynir'}, {'of_ratio': -5.0}):
            kod, g = _post(istemci, '/calculate', dict(CALC_TABAN, **yama))
            assert kod == 400, (yama, kod)
            assert g.get('status'), (yama, sorted(g))

    def test_saglikli_govde_hala_200(self, istemci):
        kod, g = _post(istemci, '/calculate', dict(CALC_TABAN))
        assert kod == 200, (kod, str(g)[:200])


# ===========================================================================
# P16B1-22 — ÇÜRÜTÜLDÜ: iki ayna kapısı da kapalı
# ===========================================================================
class TestP16B122AynaKapilariKapali:
    """Kalem başlığı ("a'da ÜST kapı yok -> 4176 km oda; n'de ALT kapı
    yok -> 2256 m oda") ÖLÇÜMLE ÇÜRÜTÜLDÜ (once2.json K3, taban
    ``7cd08bcc``): ``regression_a`` 1e9/1e6/1,0 -> HTTP 400 ``field:
    chamber_diameter`` ``accepted_range: [0.01, 5.0]``; ``regression_n``
    -5/5 -> HTTP 400 ``field: regression_n`` ``accepted_range: [0,0; 1,0]``.
    Hiçbir sarsımda dev bir oda yayımlanmıyor. Bekçi durumu KİLİTLER."""

    @pytest.mark.parametrize('a', [1e9, 1e6])
    def test_ust_uc_a_dev_oda_YAYIMLAMIYOR(self, istemci, a):
        kod, g = _post(istemci, '/calculate',
                       dict(CALC_TABAN, regression_a=a))
        assert 400 <= kod < 500, (kod, str(g)[:200])
        assert 'motor' not in g, 'reddedilen a yine de motor yayımladı'

    def test_alt_uc_a_ADIYLA_reddediliyor(self, istemci):
        kod, g = _post(istemci, '/calculate',
                       dict(CALC_TABAN, regression_a=-1.0))
        assert kod == 400
        assert 'regression_a' in _alanlar(g)

    @pytest.mark.parametrize('n', [-5.0, 5.0, 1e9])
    def test_n_iki_ucta_da_ADIYLA_reddediliyor(self, istemci, n):
        kod, g = _post(istemci, '/calculate',
                       dict(CALC_TABAN, regression_n=n))
        assert kod == 400, (n, kod, str(g)[:200])
        assert 'regression_n' in _alanlar(g)
        kunye = [k for k in g.get('invalid_fields', [])
                 if k.get('field') == 'regression_n']
        assert kunye and kunye[0].get('accepted_range'), (
            'ret bandı söylemiyor')


# ===========================================================================
# P16B1-31 — ÇÜRÜTÜLDÜ: mdot_ox işareti yutulmuyor
# ===========================================================================
class TestP16B131OksitleyiciDebisiIsareti:
    """Kalem başlığı ("mdot_ox = 0 ile -2 BİREBİR aynı sonucu veriyor,
    regression_rate sabit 3,72e-07 mm/s") ÖLÇÜMLE ÇÜRÜTÜLDÜ (once2.json
    K9): ikisi de HTTP 422 ``non_physical_oxidizer_flux`` alıyor,
    ``field: mdot_ox``, gövdeler farklı (413 ⟷ 443 bayt) ve hiçbir
    regresyon hızı yayımlanmıyor."""

    @pytest.mark.parametrize('deger', [0.0, -2.0])
    def test_pozitif_olmayan_debi_ADIYLA_reddedilir(self, istemci, deger):
        kod, g = _post(istemci, '/api/regression-analysis',
                       {'motor_data': dict(REG_TABAN, mdot_ox=deger)})
        assert kod == 422, (deger, kod, str(g)[:200])
        assert g['error'] == 'non_physical_oxidizer_flux'
        assert 'mdot_ox' in _alanlar(g)
        assert 'regression_rate' not in json.dumps(g), (
            'reddedilen debiden hâlâ regresyon hızı yayımlanıyor')

    def test_sifir_ile_negatif_AYNI_YANIT_DEGIL(self, istemci):
        yanitlar = []
        for deger in (0.0, -2.0):
            _, g = _post(istemci, '/api/regression-analysis',
                         {'motor_data': dict(REG_TABAN, mdot_ox=deger)})
            yanitlar.append(json.dumps(g, sort_keys=True, default=str))
        assert yanitlar[0] != yanitlar[1], (
            '0 ile -2 bit-aynı yanıt veriyor: işaret bilgisi yutuldu')

    def test_pozitif_debi_hala_egri_uretiyor(self, istemci):
        kod, g = _post(istemci, '/api/regression-analysis',
                       {'motor_data': dict(REG_TABAN)})
        assert kod == 200, (kod, str(g)[:200])


# ===========================================================================
# P16B1-33 — KISMEN: sınıf adı doğru, kalan borç adıyla
# ===========================================================================
class TestP16B133CidarGirdiDurumu:
    """Kalem başlığının BİRİNCİ yarısı ("0/negatif/okunamaz 'hiç
    vermediniz' diye yeniden sınıflandırılıyor") ÇÜRÜTÜLDÜ (once2.json
    K10): ``wall_thickness_input_status`` üç hâli AYRI adlandırıyor
    (``not_positive`` / ``unreadable`` / ``not_supplied``) ve gövdede
    ``user_value_not_applied`` kapı sınıfı bulunuyor."""

    @pytest.mark.parametrize('deger,durum', [
        (0, 'not_positive'), (-3, 'not_positive'),
        ('abc', 'unreadable'), (True, 'unreadable'),
    ])
    def test_ret_NEDENI_adiyla_yayimlaniyor(self, istemci, deger, durum):
        kod, g = _post(istemci, '/calculate',
                       dict(CALC_TABAN, wall_thickness=deger))
        assert kod == 200, (kod, str(g)[:200])
        metin = json.dumps(g, default=str)
        assert f'"{durum}"' in metin, (
            f'{deger!r} için girdi durumu {durum!r} yayımlanmıyor')
        assert 'user_value_not_applied' in metin, (
            'değer geldi ama "hiç vermediniz" sınıfına düşürüldü')

    def test_verilmeyen_cidar_AYRI_sinifta(self, istemci):
        kod, g = _post(istemci, '/calculate', dict(CALC_TABAN))
        metin = json.dumps(g, default=str)
        assert '"not_supplied"' in metin
        assert 'user_value_not_applied' not in metin, (
            'hiç gönderilmemiş cidar "gönderdiniz ama uygulanmadı" '
            'sınıfına düştü')


# ===========================================================================
# P15B2-01 — KISMEN: app-api sahasının fail-closed merkezi DONDURULDU
# ===========================================================================
class TestP15B201MerkezinAppApiKapsami:
    """ÖNCE (once.json K5): app-api sahasının tek okuma noktası
    ``hrma/utils/input_guard.py``tır; ``hrma/app.py`` onu içe aktarıyor ama
    kendi içinde 10 yerel dönüştürücü tanımı taşıyor. Bekçi sayıyı
    BÜYÜTMEYE kapatır: yeni bir yerel dönüştürücü eklemek kırmızıdır."""

    #: ÖLÇÜLEN nüfus (taban 7cd08bcc, once.json K5) — TAVAN, hedef değil.
    APP_YEREL_TAVAN = 10

    def test_app_yerel_donusturucu_nufusu_BUYUMUYOR(self):
        import re
        import hrma.app as app_mod
        kaynak = open(app_mod.__file__, encoding='utf-8').read()
        desen = re.compile(
            r'^\s*def\s+(_?(?:require_positive|pozitif|mm_to_m|json_float|'
            r'_num|to_float|safe_float|_float))\w*\s*\(', re.M)
        bulunan = desen.findall(kaynak)
        assert len(bulunan) <= self.APP_YEREL_TAVAN, (
            'app.py yeni bir YEREL sayı dönüştürücüsü kazandı (%d > %d): '
            '%r — dönüştürme hrma.utils.input_guard\'da yaşar (P15B2-01).'
            % (len(bulunan), self.APP_YEREL_TAVAN, bulunan))

    def test_merkez_hala_TEK_okuma_noktasi(self):
        from hrma.utils import input_guard
        assert 'mm_to_m_read' in input_guard.__all__
        assert 'num' in input_guard.__all__
        import hrma.app as app_mod
        kaynak = open(app_mod.__file__, encoding='utf-8').read()
        assert 'input_guard' in kaynak

    def test_saha_modulleri_kendi_sozlesmesini_yazmiyor(self):
        """injector_design / uq_adapters / motor_validation yerel bir
        sayı-okuma sözleşmesi TANIMLAMIYOR (ölçüldü: 0 tanım)."""
        import re
        desen = re.compile(
            r'^\s*def\s+(_?(?:require_positive|mm_to_m|json_float|'
            r'to_float|safe_float))\w*\s*\(', re.M)
        for modul in ('hrma/engines/injector_design.py',
                      'hrma/analysis/uq_adapters.py',
                      # ÖH D28 a1: brief bu ikisini
                      # ``hrma/analysis/status_report.py`` ve
                      # ``hrma/api/web_propellant_api.py`` diye
                      # adlandırıyor; GERÇEK yollar aşağıdadır (ölçüldü).
                      'hrma/validation/status_report.py',
                      'hrma/data/web_propellant_api.py'):
            kaynak = open(modul, encoding='utf-8').read()
            assert desen.findall(kaynak) == [], modul
            assert not re.findall(
                r'float\(\s*(?:data|payload|body|params|motor_data)\.get\(',
                kaynak), modul
