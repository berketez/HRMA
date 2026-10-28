"""ÖH Dalga-15 · kulvar app-api · aşama 1 — onarım bekçileri.

Her sınıf TEK bir kalemi tutar ve o kusurun TERSİ enjekte edildiğinde
KIRMIZIYA döner (ters-mutasyon kanıtı; ÖK-05 / P14 kuralı). Mutasyon
kanıtları: ``docs/scofield/raw/OH/D15/app-api/a1/04_mutasyon.txt``.

Ölçüm dosyaları (aynı betik, önce/sonra):
``docs/scofield/raw/OH/D15/app-api/a1/{once,sonra}.json``.
"""
import ast
import contextlib
import io
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with contextlib.redirect_stdout(io.StringIO()):
    from hrma import app as app_modulu

APP_KAYNAK = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'hrma', 'app.py')


@pytest.fixture()
def istemci():
    app_modulu.app.config['TESTING'] = True
    return app_modulu.app.test_client()


def _sessiz_post(istemci, yol, govde):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return istemci.post(yol, json=govde)


# ---------------------------------------------------------------------------
# P17B3-01 [KRİTİK] — iç içe sessizleştirme sys.stdout'u kalıcı bozuyordu
# ---------------------------------------------------------------------------
class TestP17B301StdoutKaliciBozulma:
    """Uzun analiz rotalarının sessizleştirmesi süreç-genel OLAMAZ.

    Ölçülen kusur (once.json): iki ``contextlib.redirect_stdout(devnull)``
    bloğu TEHLİKELİ SIRAYLA (dış blok önce çıkar) iç içe girince
    ``sys.stdout`` KAPANMIŞ bir devnull'a bağlanıyor; ondan sonra tanı
    satırı basan her rota ``ValueError: I/O operation on closed file.`` ile
    HTTP 500 döner ve sunucu kendiliğinden düzelmez.
    """

    def test_ic_ice_sessizlestirme_sonraki_yazmayi_bozmaz(self):
        ilk = sys.stdout
        try:
            akis = app_modulu._install_stdout_dedup()
            # TEHLİKELİ SIRA: dış kapsam iç kapsamdan ÖNCE kapanır.
            dis = app_modulu._motor_stdout_sessiz()
            dis.__enter__()
            ic = app_modulu._motor_stdout_sessiz()
            ic.__enter__()
            dis.__exit__(None, None, None)
            ic.__exit__(None, None, None)

            akis = app_modulu._install_stdout_dedup()
            yakala = io.StringIO()
            yedek = akis._target
            akis._target = yakala
            try:
                akis.write('tanı satırı\n')      # eskiden ValueError atardı
            finally:
                akis._target = yedek
            assert yakala.getvalue() == 'tanı satırı\n'
            hedef = getattr(sys.stdout, 'target', None)
            assert not getattr(hedef, 'closed', False), (
                'sarmalayıcının hedefi kapalı bir dosyaya bağlandı — '
                'P17B3-01 geri geldi')
        finally:
            sys.stdout = ilk

    def test_sessizlestirme_kapsami_is_parcacigi_yereldir(self):
        """Bir istek susturulurken EŞZAMANLI istek susturulmamalı."""
        import threading
        ilk = sys.stdout
        try:
            akis = app_modulu._install_stdout_dedup()
            yakala = io.StringIO()
            akis._target = yakala
            oteki = {}

            def _oteki_istek():
                print('öteki isteğin satırı')
                oteki['bitti'] = True

            with app_modulu._motor_stdout_sessiz():
                print('susturulan satır')
                t = threading.Thread(target=_oteki_istek)
                t.start()
                t.join()
            cikti = yakala.getvalue()
            assert oteki.get('bitti') is True
            assert 'susturulan satır' not in cikti
            assert 'öteki isteğin satırı' in cikti, (
                'sessizleştirme iş parçacığı sınırını aştı — '
                'süreç-genel redirect_stdout geri gelmiş olabilir')
        finally:
            sys.stdout = ilk

    def test_uretim_kodunda_surec_genel_yonlendirme_kalmadi(self):
        """``redirect_stdout(<dosya>)`` çağrısı ÜRÜN KODUNDA olmamalı.

        Metin taraması değil AST: docstring'lerdeki desen anlatımı
        (bu dosya ve ``app.py`` dâhil) yanlış kırmızı vermemeli.
        """
        agac = ast.parse(open(APP_KAYNAK, encoding='utf-8').read())
        cagrilar = []
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.Call)
                    and isinstance(dugum.func, ast.Attribute)
                    and dugum.func.attr == 'redirect_stdout'
                    and isinstance(dugum.func.value, ast.Name)
                    and dugum.func.value.id == 'contextlib'):
                cagrilar.append(dugum.lineno)
        assert cagrilar == [], (
            'süreç-genel stdout yönlendirmesi geri geldi (satır): %r'
            % cagrilar)


# ---------------------------------------------------------------------------
# P7B1-09 — /api/six-dof-analysis: model bandı dışında HÜKÜM yayımlanmaz
# ---------------------------------------------------------------------------
#: ÖH D27 / P16S1-02 — GÖVDE GEOMETRİSİ ARTIK GÖNDERİLİYOR.
#:
#: Bu sözlük ``mass_initial`` / ``mass_final`` / ``diameter`` /
#: ``launch_angle`` gönderiyordu; ucun HİÇBİRİNİ okumadığı ölçüldü
#: (``docs/scofield/raw/OH/D27/app-api/a1/once.json`` K1: uç
#: ``body_diameter``/``fin_*``/``dry_mass`` adlarını okuyor). Yani bu iki
#: bekçi, gövdesi TAMAMEN sunucu yer tutucusundan kurulmuş bir araca
#: basılan ``stable: True`` hükmünü KİLİTLİYORDU — kalemin tam da ölçtüğü
#: kusur. Uç artık Barrowman geometrisi uydurulduğunda kararlılık hükmünü
#: yayımlamıyor, bu yüzden geometri BURADA VERİLİR.
#:
#: SAYILAR, ucun bugüne kadar sessizce koyduğu sayıların TA KENDİSİDİR
#: (``_SIXDOF_UC_VARSAYILANLARI``), dolayısıyla iki testin çözdüğü uçuş
#: eskisiyle bit-aynıdır; değişen tek şey, aracın artık İSTENMİŞ olmasıdır.
#: Okunmayan dört ad bilerek DURUYOR: ``tests/test_d21_app_api_a1.py``
#: H1-Y5 ailesi "gönderilen ama okunmayan ad" davranışını ayrıca ölçüyor.
_SIXDOF_TABAN = {'burn_time': 10.0, 'mass_initial': 50.0,
                 'mass_final': 30.0, 'diameter': 0.1, 'cd0': 0.5,
                 'launch_angle': 85.0,
                 'body_diameter': 0.1, 'body_length': 2.0,
                 'nose_length': 0.3, 'nose_type': 'ogive',
                 'fin_count': 4, 'fin_root_chord': 0.15,
                 'fin_tip_chord': 0.075, 'fin_span': 0.1,
                 'fin_sweep': 0.05}


class TestP7B109AeroBandiKapisi:

    def test_bant_disi_kosumda_hukum_yayimlanmaz(self, istemci):
        r = _sessiz_post(istemci, '/api/six-dof-analysis',
                         dict(_SIXDOF_TABAN, thrust=1e9))
        assert r.status_code == 200
        ozet = r.get_json()['summary']
        # Ölçülen tepe değerler DURUR (sayı silinmez)...
        assert ozet['max_speed'] > 1e8
        assert ozet['max_mach'] > app_modulu._SIXDOF_AERO_MACH_LIMIT
        # ...ama HÜKÜM yayımlanmaz.
        assert ozet['stable'] is None, (
            'ışık hızının üstünde uçan araca kararlılık hükmü basıldı')
        assert ozet['apogee'] is None
        assert ozet['aero_model_out_of_band'] is True
        assert ozet['aero_mach_limit'] == \
            app_modulu._SIXDOF_AERO_MACH_LIMIT
        assert any(u.get('key') == 'warn.sixdof.aero_model_out_of_band'
                   for u in ozet['warnings'])

    def test_gecerli_kosum_degismez(self, istemci):
        """Bant içinde hüküm AYNEN yayımlanır (kapı meşru koşumu kesmez)."""
        r = _sessiz_post(istemci, '/api/six-dof-analysis',
                         dict(_SIXDOF_TABAN, thrust=5000.0))
        ozet = r.get_json()['summary']
        assert r.status_code == 200
        assert ozet['max_mach'] < app_modulu._SIXDOF_AERO_MACH_LIMIT
        assert ozet['stable'] is True
        assert ozet['apogee'] is not None
        assert 'aero_model_out_of_band' not in ozet


# ---------------------------------------------------------------------------
# P7B2-01 — /parametric-analysis: motora bağlı olmayan süpürme adı
# ---------------------------------------------------------------------------
_PARAM_TABAN = {'thrust': 5000, 'burn_time': 10, 'of_ratio': 6.0,
                'chamber_pressure': 20.0, 'fuel_type': 'htpb',
                'oxidizer_type': 'n2o', 'param_steps': 3}


class TestP7B201BagliOlmayanSupurme:

    def test_altitude_supurmesi_reddedilir(self, istemci):
        r = _sessiz_post(istemci, '/parametric-analysis',
                         dict(_PARAM_TABAN, param_type='altitude',
                              param_start=0, param_end=30000))
        assert r.status_code == 422
        g = r.get_json()
        assert g['error'] == 'unwired_sweep_parameter'
        assert g['field'] == 'param_type'
        assert g['reason'] == 'not_wired_to_engine'
        assert 'of_ratio' in g['accepted_parameters']
        assert 'altitude' not in g['accepted_parameters']
        assert 'results' not in g, 'reddedilen tarama yine de nokta üretti'

    def test_bagli_supurme_gercekten_degisen_egri_uretir(self, istemci):
        r = _sessiz_post(istemci, '/parametric-analysis',
                         dict(_PARAM_TABAN, param_type='of_ratio',
                              param_start=2.0, param_end=8.0))
        assert r.status_code == 200
        noktalar = r.get_json()['results']
        assert len(noktalar) == 3
        assert len({repr(n['isp']) for n in noktalar}) == 3, (
            'bağlı bir süpürme bile bit-aynı noktalar üretti')

    def test_bagli_ad_kumesi_motor_kurulumundan_turer(self):
        """``PARAMETRIC_WIRED_PARAMS`` kodun kendisiyle eşleşmeli (AST).

        Kusurun kökü, süpürme adının motor kwarg listesinde OLMAMASIYDI.
        Bekçi o listeyi kaynaktan okur; kwarg listesi büyür/küçülürse ve
        sabit güncellenmezse bu test kırılır.
        """
        agac = ast.parse(open(APP_KAYNAK, encoding='utf-8').read())
        okunan = set()
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Call):
                continue
            f = dugum.func
            if not (isinstance(f, ast.Name) and f.id == 'HybridRocketEngine'):
                continue
            for kw in dugum.keywords:
                d = kw.value
                if not isinstance(d, ast.Call):
                    continue
                # (a) ``current_params.get('<ad>'...)`` — özgün desen.
                if (isinstance(d.func, ast.Attribute)
                        and d.func.attr == 'get'
                        and isinstance(d.func.value, ast.Name)
                        and d.func.value.id == 'current_params'
                        and d.args
                        and isinstance(d.args[0], ast.Constant)):
                    okunan.add(d.args[0].value)
                # (b) ÖH D27 / P16S1-02 — yedeği olan alanlar artık
                # ``_motor_degeri(current_params, '<ad>')`` ile okunuyor:
                # sayı çağrı yerinde DEĞİL tek kaynak tablosunda duruyor
                # (``_PARAMETRIK_UC_VARSAYILANLARI``) ve düşen yedek
                # ``defaults_applied``a giriyor. Bekçinin İDDİASI aynen
                # korunur — süpürülebilir ad kümesi hâlâ MOTOR KURULUMUNDAN
                # türetilir, elle yazılmış bir listeden değil; yalnız
                # okunacak ikinci çağrı biçimi tanıtıldı.
                elif (isinstance(d.func, ast.Name)
                      and d.func.id == '_motor_degeri'
                      and len(d.args) == 2
                      and isinstance(d.args[0], ast.Name)
                      and d.args[0].id == 'current_params'
                      and isinstance(d.args[1], ast.Constant)):
                    okunan.add(d.args[1].value)
        assert okunan, 'parametrik motor kurulumu bulunamadı'
        metinsel = {'nozzle_type', 'combustion_type', 'fuel_type'}
        beklenen = okunan - metinsel
        assert beklenen == set(app_modulu.PARAMETRIC_WIRED_PARAMS), (
            'PARAMETRIC_WIRED_PARAMS motor kurulumuyla uyuşmuyor; '
            'yalnız kodda: %s / yalnız sabitte: %s' % (
                sorted(beklenen - set(app_modulu.PARAMETRIC_WIRED_PARAMS)),
                sorted(set(app_modulu.PARAMETRIC_WIRED_PARAMS) - beklenen)))


# ---------------------------------------------------------------------------
# P7B2-06 — /api/solid-monte-carlo girdi kapısı
# ---------------------------------------------------------------------------
# V301/K-C1: çekirdek 30 -> SOLID_DEFAULT_GEOMETRY_MM (48 mm). K-A'dan beri
# Ø100/30 mm motorun portu boğazdan küçük (A_port,0/A_t = 0,950) ve tasarım
# 422 port_smaller_than_throat ile reddediliyor; "geçerli gövde" bekçisi
# main'de de kırmızıydı (K-C1/RAPOR.md, değiştirilen test beklentileri).
from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_GEOMETRY_MM as _SDG
_MC_GECERLI = {'chamber_diameter': 100.0,
               'core_diameter': float(_SDG['core_diameter']),
               'grain_length': 500.0, 'chamber_pressure': 40.0,
               'propellant_type': 'apcp', 'n_samples': 60}


class TestP7B206MonteCarloKapisi:

    def test_bos_govde_guvenilirlik_hukmu_uretmez(self, istemci):
        r = _sessiz_post(istemci, '/api/solid-monte-carlo', {})
        assert r.status_code == 422
        g = r.get_json()
        assert g['status'] == 'incomplete_input'
        assert 'chamber_pressure' in g['missing_fields']
        assert 'success_rate_percent' not in g

    def test_ince_cidar_reddedilir(self, istemci):
        """core=99 / chamber=100 -> 0,5 mm ağ; kardeş uç da reddediyor."""
        r = _sessiz_post(istemci, '/api/solid-monte-carlo',
                         dict(_MC_GECERLI, core_diameter=99.0))
        assert r.status_code == 422
        alanlar = r.get_json()['invalid_fields']
        assert alanlar[0]['field'] == 'core_diameter'
        assert alanlar[0]['reason'] == 'out_of_range'

    def test_bant_disi_basinc_reddedilir(self, istemci):
        r = _sessiz_post(istemci, '/api/solid-monte-carlo',
                         dict(_MC_GECERLI, chamber_pressure=1e6))
        assert r.status_code == 422
        assert any(a['field'] == 'chamber_pressure'
                   for a in r.get_json()['invalid_fields'])

    def test_sayisal_olmayan_cap_500_degil_422(self, istemci):
        """ÖK-17 yönü: ham 5xx yerine adlı 422."""
        r = _sessiz_post(istemci, '/api/solid-monte-carlo',
                         dict(_MC_GECERLI, chamber_diameter='abc'))
        assert r.status_code == 422, 'ham istisna 500 olarak sızıyor'
        assert 'invalid_fields' in r.get_json()

    # --- a2 devralma: yukarıdaki bekçi ``except BandIhlali`` DALINI HİÇ
    # ÇALIŞTIRMIYORDU ve bu ölçüldü (ters-mutasyon "P7B2-06-500" YEŞİL
    # kaldı, ``04_mutasyon.txt``). Sebep: ``chamber_diameter='abc'``
    # gövdesi daha ÖNCEKİ ``_collect_unphysical_fields`` kapısına takılıp
    # 422 alıyor (``error='invalid_solid_monte_carlo_input'``,
    # ``error_type`` YOK) — yani 422'yi üreten şey mutasyonun hedef aldığı
    # dal DEĞİL; o dal bu gövde için ulaşılamaz. Ölçülen dört gövde ise o
    # dala gerçekten giriyor (``error_type='BandIhlali'``); bekçi onlarla
    # güçlendirilir ve mutasyon artık kırmızı verir.
    @pytest.mark.parametrize('ek', [
        {'propellant_type': [1, 2]},
        {'thrust': 'abc'},
        {'burn_time': 'abc'},
        {'thrust': 1e12},
    ])
    def test_bant_ihlali_dali_500_degil_adli_422(self, istemci, ek):
        r = _sessiz_post(istemci, '/api/solid-monte-carlo',
                         dict(_MC_GECERLI, **ek))
        assert r.status_code == 422, 'BandIhlali hâlâ 500 olarak sızıyor'
        govde = r.get_json()
        assert govde.get('error_type') == 'BandIhlali', (
            'yanıt bu kez BAŞKA bir kapıdan geldi; bekçi hedef dalı '
            f'ölçmüyor: {govde.get("error")!r}')
        assert govde.get('invalid_fields')

    def test_gecerli_govde_hala_kosuyor(self, istemci):
        r = _sessiz_post(istemci, '/api/solid-monte-carlo', _MC_GECERLI)
        assert r.status_code == 200
        assert r.get_json()['status'] == 'success'
        assert 'success_rate_percent' in r.get_json()

    def test_cekirdek_payi_kardes_ucla_ayni_sayidir(self):
        """``SOLID_CORE_WALL_MARGIN_MM`` ⟷ ``/calculate_solid`` bandı.

        ÖH D26 a2 (OH-D25-08) — BEKÇİ ÇEVRİLDİ. Eski hâli AST ile
        ``validate_input_range(core_diameter, 5, chamber_diameter-5, ...)``
        çağrısını arıyor ve ilk argümanının sabitle aynı olduğunu çakıyordu.
        O çağrı KUSURUN TA KENDİSİYDİ: bandı grain tipine kör biçimde uç
        katmanında elle kuruyor ve uç-yanmalı grainde motor modülünün
        kanonik kabul kümesiyle (``_core_diameter_domain``, OH-D19-23
        hükmü) çelişiyordu — ölçüldü, aynı motorun iki katmanı 0 / 2 /
        100 mm'de ayrışıyordu. Bekçi o çağrının VARLIĞINI şart koştuğu için
        onarımı engelliyordu.

        Testin ASIL iddiası korundu ve güçlendirildi: iki ucun (bu uç ve
        ``/api/solid-monte-carlo``) çekirdek payı AYNI adlandırılmış sayıdan
        gelir. Artık sayının aynılığı metinden değil, TÜRETMENİN kendisinden
        okunur: ``_core_diameter_uc_bandi`` kanonik kümeye
        ``SOLID_CORE_WALL_MARGIN_MM`` ekler ve elle yazılmış ikinci bir band
        kaynakta KALMAMIŞTIR.
        """
        kaynak = open(APP_KAYNAK, encoding='utf-8').read()
        agac = ast.parse(kaynak)

        # 1) Elle yazılmış band geri gelmiş olmasın.
        elle = [d.lineno for d in ast.walk(agac)
                if isinstance(d, ast.Call)
                and isinstance(d.func, ast.Name)
                and d.func.id == 'validate_input_range'
                and len(d.args) >= 4
                and isinstance(d.args[3], ast.Constant)
                and d.args[3].value == 'Core diameter (mm)']
        assert not elle, (
            'çekirdek bandı yine uç katmanında elle yazılmış (satır %s)'
            % elle)

        # 2) Kardeş uç (Monte Carlo) hâlâ ADLANDIRILMIŞ sabiti kullanıyor.
        assert kaynak.count('SOLID_CORE_WALL_MARGIN_MM') >= 2

        # 3) İki uç AYNI sayıyı taşır — türetme fonksiyonu üzerinden ölçülür.
        from hrma.engines.solid_rocket_engine import _core_diameter_domain
        pay = float(app_modulu.SOLID_CORE_WALL_MARGIN_MM)
        for D in (100.0, 250.0):
            alt, ust = app_modulu._core_diameter_uc_bandi(
                _core_diameter_domain('bates', D), D)
            assert alt == pytest.approx(pay)
            assert ust == pytest.approx(D - pay)


# ---------------------------------------------------------------------------
# P7B1-08 — /api/launch-site/resolve: tanım dışı değer KIRPILMAZ, reddedilir
# ---------------------------------------------------------------------------
class TestP7B108SahaTanimKapisi:

    @pytest.mark.parametrize('alan,deger', [('latitude', 200.0),
                                            ('latitude', -91.0),
                                            ('longitude', 400.0),
                                            ('longitude', -181.0)])
    def test_wgs84_disi_derece_reddedilir(self, istemci, alan, deger):
        govde = {'latitude': 0.0, 'longitude': 0.0}
        govde[alan] = deger
        r = _sessiz_post(istemci, '/api/launch-site/resolve', govde)
        assert r.status_code == 400
        g = r.get_json()
        assert g['field'] == alan
        assert g['reason'] == 'out_of_range'
        assert 'site' not in g, 'reddedilen istekte saha yine de çözüldü'

    @pytest.mark.parametrize('alan,deger', [('temperature_k', -300.0),
                                            ('temperature_k', 0.0),
                                            ('pressure_pa', -1e5)])
    def test_mutlak_olcek_sifir_alti_reddedilir(self, istemci, alan, deger):
        govde = {'latitude': 0.0, 'longitude': 0.0, alan: deger}
        r = _sessiz_post(istemci, '/api/launch-site/resolve', govde)
        assert r.status_code == 400, (
            '%s = %s sessizce yeniden yazıldı' % (alan, deger))
        assert 'site' not in r.get_json()

    def test_gecerli_saha_degismez(self, istemci):
        r = _sessiz_post(istemci, '/api/launch-site/resolve',
                         {'latitude': 28.5, 'longitude': -80.6})
        assert r.status_code == 200
        saha = r.get_json()['site']
        assert saha['gravity_local_m_s2'] == pytest.approx(
            9.792092464316633, rel=1e-12)


# ===========================================================================
# a2 DEVRALMA — kalan altı kalem (ölçüm: ``once_a2.json`` / ``sonra_a2.json``)
# ===========================================================================

#: ``/calculate`` hafif koşum: ağır figür/CAD/yörünge dalları kapalı. Fizik
#: yolu değişmez, yalnız sunum katmanı atlanır (uç bu alanları zaten okuyor).
HAFIF = {'include_plots': False, 'generate_cad': False,
         'calculate_trajectory': False, 'include_combustion_analysis': False,
         'include_realtime_dashboard': False,
         'include_3d_visualization': False}

HIBRIT_TABAN = dict(HAFIF, **{
    'motor_type': 'hybrid', 'thrust': 1000.0, 'burn_time': 10.0,
    'chamber_pressure': 20.0, 'of_ratio': 6.0, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'l_star': 1.0, 'expansion_ratio': 4.0})

TRANSIENT_TABAN = {'thrust': 5000.0, 'burn_time': 10.0, 'of_ratio': 6.0,
                   'chamber_pressure': 20.0, 'fuel_type': 'htpb',
                   'oxidizer_type': 'n2o'}


# ---------------------------------------------------------------------------
# P7B1-24 — doğrulayıcının EMNİYET uyarıları yanıta çıkar
# ---------------------------------------------------------------------------
class TestP7B124EmniyetUyarisiYutulmaz:
    """Ölçülen kusur (once_a2.json): 3 gövdede 3 uyarı, yanıtta 0 görünüm."""

    #: ÖH D15 birleştirme (1 Eyl 2026): ölçülen üst uç ``thrust=60000``
    #: birleşik ağaçta HTTP 400 veriyor — ihracat kulvarının .eng
    #: zarf-kütle kapısı (fail-closed, kazanır) o yükte dosyayı yazmıyor
    #: ve ret /calculate'in tamamını düşürüyor. Uyarı kanalının konusu
    #: itki BANDI değil uyarının YUTULMAMASIDIR; üst uç kapıyı geçen en
    #: yüksek komşusuna (50 kN) taşındı ve aynı imzayı üretiyor (ölçüldü:
    #: "Moderate thrust (50000.0N) requires reinforced test stand ...").
    @pytest.mark.parametrize('ek,imza', [
        ({'thrust': 50000.0}, 'test stand'),
        ({'thrust': 20000.0}, 'test stand'),
        ({'burn_time': 120.0}, 'thermal management'),
    ])
    def test_uyari_yanitta_gorunur(self, istemci, ek, imza):
        r = _sessiz_post(istemci, '/calculate', dict(HIBRIT_TABAN, **ek))
        assert r.status_code == 200
        govde = r.get_json()
        kayitlar = govde.get('validation_warnings') or []
        assert kayitlar, 'doğrulayıcı uyarısı yine yalnız günlüğe yazıldı'
        metinler = ' '.join(str((k.get('params') or {}).get('message', ''))
                            for k in kayitlar)
        assert imza in metinler.lower(), metinler

    def test_uyari_panelin_okudugu_diziye_katilir(self, istemci):
        """``static/js/app.js::displayWarnings`` bu diziyi basıyor."""
        r = _sessiz_post(istemci, '/calculate',
                         dict(HIBRIT_TABAN, thrust=50000.0))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        dogrulama = (r.get_json() or {}).get('validation') or {}
        havuz = ((dogrulama.get('regular_warnings') or [])
                 + (dogrulama.get('critical_warnings') or []))
        assert any('test stand' in str((k.get('params') or {}).get('message',
                                                                  '')).lower()
                   for k in havuz), (
            'emniyet uyarısı panelin okuduğu kanala hiç girmedi')

    def test_sessiz_kosuda_alan_hic_eklenmez(self, istemci):
        """Sahte gösterge yasağı: uyarı yoksa boş dizi de yayımlanmaz."""
        r = _sessiz_post(istemci, '/calculate', dict(HIBRIT_TABAN))
        assert r.status_code == 200
        assert 'validation_warnings' not in r.get_json()

    def test_kritik_uyari_hukmu_dusurur(self):
        """``CRITICAL:`` önekli mesaj ``validation_passed``i düşürmeli."""
        rapor = {'regular_warnings': [], 'critical_warnings': [],
                 'validation_passed': True, 'overall_status': {
                     'code': 'status.normal', 'params': {},
                     'severity': 'info'}}
        sonuclar = {}
        app_modulu._emniyet_uyarilarini_yayimla(
            sonuclar, rapor,
            app_modulu._dogrulayici_uyari_kayitlari(
                ['CRITICAL: Burst pressure (2400 bar) requires x']))
        assert rapor['validation_passed'] is False
        assert rapor['overall_status']['code'] == 'status.critical'
        assert len(rapor['critical_warnings']) == 1


# ---------------------------------------------------------------------------
# P7B1-03 — aynı motor, iki uç, TEK sözleşme
# ---------------------------------------------------------------------------
class TestP7B103UcSozlesmeAsimetrisi:
    """Ölçülen kusur (once_a2.json): 10 gövdenin 6'sında iki uç ayrışıyordu.

    ``/api/transient-analysis`` ``thrust = 1e12`` N ve ``Pc = 5000 bar``
    dâhil ÜST bantsızdı (HTTP 200 + ~60 KB eğri), kardeş ``/calculate`` aynı
    gövdeye 400 diyordu.
    """

    @pytest.mark.parametrize('ek,alan', [
        ({'thrust': 1e12}, 'thrust'),
        ({'thrust': 1e9}, 'thrust'),
        ({'chamber_pressure': 5000.0}, 'chamber_pressure'),
        ({'burn_time': 1e6}, 'burn_time'),
        ({'of_ratio': 500.0}, 'of_ratio'),
        ({'chamber_temperature': 50.0}, 'chamber_temperature'),
    ])
    def test_fizik_disi_girdi_adiyla_reddedilir(self, istemci, ek, alan):
        r = _sessiz_post(istemci, '/api/transient-analysis',
                         dict(TRANSIENT_TABAN, **ek))
        assert r.status_code == 400, 'üst bant hâlâ açık'
        govde = r.get_json()
        assert alan in {p.get('field')
                        for p in (govde.get('invalid_fields') or [])}
        assert 'transient' not in govde, 'reddedilen gövde için eğri üretildi'

    @pytest.mark.parametrize('ek', [
        {'thrust': 1e12}, {'chamber_pressure': 5000.0}, {'of_ratio': 500.0},
        {'burn_time': 1e6}, {'chamber_temperature': 50.0},
        {'thrust': -100.0}, {'of_ratio': -1.0}, {}])
    def test_iki_uc_ayni_hukmu_verir(self, istemci, ek):
        t = _sessiz_post(istemci, '/api/transient-analysis',
                         dict(TRANSIENT_TABAN, **ek))
        c = _sessiz_post(istemci, '/calculate',
                         dict(HAFIF, **dict(TRANSIENT_TABAN, **ek)))
        assert (t.status_code < 400) == (c.status_code < 400), (
            'aynı gövde iki uçta hâlâ iki ayrı hüküm alıyor: '
            f'transient={t.status_code} calculate={c.status_code}')

    def test_gecerli_govde_hala_cozuluyor(self, istemci):
        r = _sessiz_post(istemci, '/api/transient-analysis',
                         dict(TRANSIENT_TABAN))
        assert r.status_code == 200
        assert 'transient' in r.get_json()


# ---------------------------------------------------------------------------
# P7B1-06 — ÇÖZÜLEN geometri de ürünün kendi bandına tabidir
# ---------------------------------------------------------------------------
# ÇAPA YENİLENDİ (ÖH D19 fix-12, 3 Eyl 2026): değiştiren D19 hibrit B3-12 (09867aa) — reaktan molekül ağırlığı TEK KAYNAĞA alındı, yanma çözümü ve ondan türeyen bütün yapraklar (T_c, boğaz/çıkış geometrisi, ısı akısı, itki eğrisi, apoje) ~1e-5…4e-4 bağıl kaydı; D19 hibrit çapa kaydı 03_capa_kiyas.txt atıflı. Sayı ölçüldü (taban kaydı-4, main d914908).
# ÇAPA YENİLENDİ (ÖH D21 fix-14, 4 Eyl 2026): değiştiren D20 fizik-c B1-12 (34ab8b9) — hibrit manşet C_F tek kayıp kümesine bağlandı (η_kin boyutlandırmadan ÖNCE sabit noktaya çözülür): manşet Isp −%2,36, boğaz çapı +%1,2, kamara çapı 78,88→79,60 mm, ondan türeyen bütün yapraklar (geometri, ısı akısı, itki eğrisi, apoje) kaydı; D20 fizik çapa kaydı docs/scofield/raw/OH/D20/fizik/a1/03_capa_kiyas.txt atıflı. Sayı ölçüldü (taban kaydı-5, main b613b2b). (d_c 0,078894→0,079618 m +%0,92; L_c 0,683285→0,691410 m +%1,19)
# ÇAPA YENİLENDİ (ÖH D21 fix-15, 4 Eyl 2026): değiştiren D21 hibrit a1 P15B1-04 (676a2a5) — çan sapma verimi λ tek kaynağa alındı (nozzle_design ⟷ hybrid_rocket_engine iki kopya birleşti; hibrit çapasında 27.098 yaprak ~1e-5 bağıl kaydı, λ bağıl değişimi 3,77e-05; docs/scofield/raw/OH/D21/hibrit/a1/capa_fark_ozet.json). Sayı ölçüldü (main 7776bfb, D21 14/15 birleşik). (d_c 0,0796176→0,0796188 m +1,5e-5; L_c 0,6914099→0,6914227 m +1,9e-5)
# ÇAPA YENİLENDİ (ÖH D22 fix-18, 4 Eyl 2026): değiştiren D22 hibrit a1 (60509f2) — OH-D21-03: kinetik verim artık İSTENEN değil GERÇEKLEŞEN L*'ı okuyor ve boyutlandırma L* sabit-noktasına sarıldı (η_kin ↔ boğaz/kamara geometrisi); OH-D21-02: transient C_F kayıp kümesini taşıyor. Hibrit zinciri (geometri, ısı akısı, itki eğrisi, apoje) onunla kaydı; D22 hibrit çapa kaydı docs/scofield/raw/OH/D22/hibrit/a1/capa_kiyas.json atıflı. Sayı ölçüldü (main 2e60b9a, D22 12/16 birleşik). (d_c 0,0796188→0,0794332 m −%0,23; L_c 0,6914227→0,6893372 m −%0,30; L*_achieved 3,544 m)
class TestP7B106CozulenGeometriBandi:
    """Ölçülen kusur (once_a2.json + probe): ``{thrust: 50000, of_ratio: 0,5,
    l_star: 100}`` -> HTTP 200, ``chamber_length = 42,607 m``; ürünün kendi
    tablosu ``chamber_length max = 20,0 m`` diyor."""

    def test_bant_disi_oda_yayimlanmaz(self, istemci):
        r = _sessiz_post(istemci, '/calculate', dict(
            HIBRIT_TABAN, thrust=50000.0, of_ratio=0.5, l_star=100.0))
        # ÖH D22 / P16B1-19 — BEKÇİ DARALTILDI, GEVŞETİLMEDİ (gerekçe).
        # Bu gövdedeki ``l_star = 100 m``, ÖH D22'de eklenen GİRDİ kapısının
        # (``hrma.constants.L_STAR_GENERIC_BAND_M`` üst ucu 3,05 m; Huzel &
        # Huang SP-125 Tablo 4-1) bandının dışındadır ve artık motor
        # çözülmeden, ALANIN KENDİ ADIYLA 422 ile reddediliyor. Kalemin
        # güvencesi ("42,6 m oda YAYIMLANMAZ") aynen duruyor — değişen,
        # reddin türetilen sonucu mu (chamber_length, 400) yoksa kullanıcının
        # GÖNDERDİĞİ girdiyi mi (l_star, 422) adlandırdığı. İki yol da
        # fail-closed; hangisi çalışırsa çalışsın gövdede ``motor`` OLMAZ.
        # Ölçüm: docs/scofield/raw/OH/D22/app-api/a2/once.json → P16B1-19
        # (l_star = 1e3 ve 1e9 -> HTTP 200 + BOŞ ``l_star_note``).
        assert r.status_code in (400, 422), (
            f'çözülen 42,6 m oda hâlâ yayımlanıyor (HTTP {r.status_code})')
        govde = r.get_json()
        kayit = govde['invalid_fields'][0]
        if r.status_code == 400:
            assert kayit['field'] == 'chamber_length'
            assert kayit['derived'] is True
            assert kayit['value'] > 20.0
        else:
            assert kayit['field'] == 'l_star', kayit
            assert kayit['reason'] == 'above_generic_band'
        assert 'motor' not in govde, 'reddedilen tasarım yine de yayımlandı'

    def test_gecerli_geometri_degismez(self, istemci):
        r = _sessiz_post(istemci, '/calculate', dict(HIBRIT_TABAN))
        assert r.status_code == 200
        motor = r.get_json()['motor']
        # ÇAPA YENİLENDİ (ÖH D18 fizik-a2, 2 Eyl 2026):
        #   d_c 0,07887050316335845 -> 0,07889347044479032 (+%0,029)
        #   L_c 0,6830167767124546  -> 0,6832746568379089  (+%0,038)
        # DEĞİŞTİREN **bu aşama DEĞİL, D18 fizik-a1**'dir (commit 779a1c6,
        # kalemler B3-05 + B3-02: boğaz/çıkış istasyonları kayan dengeye
        # taşındı, hibrit c* ve ṁ zinciri onunla kaydı). ATIF ÖLÇÜLDÜ:
        # ``git archive 779a1c6`` ile çıkarılan a1 ağacında bu bekçi de
        # KIRMIZI koşuyor ve a1 ağacının verdiği sayı a2 ağacınınkiyle
        # BİT-AYNI (0,07889347044479032 / 0,6832746568379089), yani a2'nin
        # diff'i bu yaprağa hiç dokunmuyor. a1 kendi çapasını yenilememişti.
        # ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K
        # doymuş SIVI giriş entalpisi. Kâhin: CEA kök denetimi
        # (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) +
        # önce/sonra (p1a rapor §12). Tolerans DEĞİŞMEDİ.
        #   d_c 0,0794332055737502 -> 0,07983065065803656
        # ÇAPA YENİLENDİ — v3.0.1 kulvar P (ana model kararı): kaynaksız
        # 1,5·√N·D_son kuralı söküldü, grain dış çapı = son port çapı
        # (N = 1, artık et 0). Eski çapa 1,5 katsayısını KİLİTLİYORDU.
        # Kamara boyu L_pre = 0,5·D_ch ve L_post bandı D_ch'ye bağlı olduğu
        # için o da kısaldı. Ölçüm: docs/scofield/raw/OH/V301/ayberk1/
        # port-kamara/RAPOR.md.
        #   d_c 0,07983065065803656 -> 0,05323547085323697 (= D_port_son)
        #   L_c 0,6938044063822819  -> 0,6727638085755462
        # ÇAPA YENİLENDİ — v3.0.1 H-PANEL (NK-15/NK-20, Berke: 'girdi +
        # kaynaklı varsayılan'): hibrit c* verimi varsayılanı 0,89 (26
        # ölçülmüş N2O/HTPB ateşlemesinin ortancası; docs/scofield/raw/OH/
        # V301/hibrit-panel/RAPOR.md). Teslim c* düşünce aynı itki için ṁ
        # artar, son port (= kamara) genişler. ÖLÇÜLDÜ (ana model, birleşik
        # ağaç): η = %100 verilince ESKİ çapa BİT-AYNI döner (aşağıdaki ikinci
        # istek), yani değişimin tek kaynağı η'dır. Tolerans DEĞİŞMEDİ.
        #   d_c 0,05323547085323697 -> 0,05562952212024063
        #   L_c 0,6727638085755462  -> 0,7122747385131958
        assert motor['chamber_diameter'] == pytest.approx(
            0.05562952212024063, rel=1e-12)
        assert motor['chamber_diameter'] == motor['port_diameter_final']
        assert motor['chamber_length'] == pytest.approx(
            0.7122747385131958, rel=1e-12)
        ideal = _sessiz_post(istemci, '/calculate',
                             dict(HIBRIT_TABAN, combustion_efficiency=100.0))
        assert ideal.status_code == 200
        m_ideal = ideal.get_json()['motor']
        assert m_ideal['chamber_diameter'] == pytest.approx(
            0.05323547085323697, rel=1e-12)
        assert m_ideal['chamber_length'] == pytest.approx(
            0.6727638085755462, rel=1e-12)

    def test_bant_urunun_kendi_tablosundan_okunur(self):
        """Tek kaynak: eşik app.py'ye YAZILMAZ, limits'ten gelir."""
        for alan in app_modulu._COZULEN_GEOMETRI_ALANLARI:
            assert alan in app_modulu.motor_validator.limits, alan
        agac = ast.parse(open(APP_KAYNAK, encoding='utf-8').read())
        govde = [d for d in ast.walk(agac)
                 if isinstance(d, ast.FunctionDef)
                 and d.name == '_cozulen_geometri_ihlali']
        assert len(govde) == 1
        sabitler = {d.value for d in ast.walk(govde[0])
                    if isinstance(d, ast.Constant)
                    and isinstance(d.value, float)}
        assert not sabitler, (
            'bant sayısı fonksiyonun içine yazılmış (tek kaynak ihlali): %s'
            % sabitler)

    def test_mm_sanilan_girdi_hala_adiyla_reddedilir(self, istemci):
        """Kalemin ÖZGÜN reprosu (ÖH Z5S / S3 kapattı) geri gelmesin."""
        r = _sessiz_post(istemci, '/calculate',
                         dict(HIBRIT_TABAN, initial_port_diameter=50.0))
        assert r.status_code == 400
        assert 'initial_port_diameter' in {
            p.get('field') for p in (r.get_json().get('invalid_fields') or [])}


# ---------------------------------------------------------------------------
# P7B1-01 — beyan kendi gövdesinde yalanlanamaz
# ---------------------------------------------------------------------------
class TestP7B101BeyanKendiGovdesiyleOlculur:
    """Ölçülen kusur (once_a2.json): beyan "her yankı 2,57426 kullanır"
    derken aynı gövdedeki 16 ``burn_time`` yaprağının 7'si 40,0 s'te."""

    #: ÖH D15 birleştirme (1 Eyl 2026) — ÖLÇÜLEN gövde ``burn_time=40``
    #: idi ve birleşik ağaçta HTTP 400 veriyor: ihracat kulvarının .eng
    #: zarf-kütle kapısı (``OpenRocketExportDataError``) 40 s'lik yükte
    #: 7.116 kg/m³ dökme itici yoğunluğu hesaplayıp dosyayı YAZMIYOR ve
    #: ret /calculate'in tamamını düşürüyor. Kapı FAIL-CLOSED'dır ve
    #: kazanır. Bu bekçinin konusu yükün kendisi değil, BEYANIN kendi
    #: gövdesine karşı ölçülmesidir; bu yüzden yük, kapıyı geçen ve AYNI
    #: kırpılmayı üreten en yakın komşusuna taşındı: 10 s istenir, çözücü
    #: 2,55 s sürdürür (``burn_time_clipped: true``), beyan yine doğar.
    #:
    #: v3.0.1 kulvar P (ana model kararı) — KIRPMA YOLU KAPANDI. Kaynaksız
    #: port <= 0,8·D_ch/√N kırpması söküldü; zarfı aşan istek (bu fikstürün
    #: eski gövdesi: D_ilk 50 mm, kamara 70 mm) artık 422
    #: ``grain_envelope_too_small_for_final_ports`` alır (ölçüldü). Ürünün
    #: /calculate yolunda gönderilen ``burn_time``ı hâlâ GÖSTEREN yaprak
    #: üreten tek yol kırpmaydı. Beyan yine doğar: aşırı belirlenmiş girdi
    #: (itki 3000 N, süre 10 s, toplam impuls 45 000 N·s -> çözücü 15 s)
    #: ``burn_time``ı ``solved_by_model`` diye beyan eder; o koşuda gönderilen
    #: değerin yankısı 0'dır (ölçüldü). Yankı > 0 hâlinin ÖLÇÜMÜ ayrıca
    #: ``test_yankili_govdede_her_yol_olculur`` ile ``_beyan_yankilarini_olc``
    #: üzerinden doğrudan sınanır — kapsam kaybolmaz, aracı değişir.
    @pytest.fixture(scope='class')
    def kirpilmis(self, request):
        istemci = app_modulu.app.test_client()
        app_modulu.app.config['TESTING'] = True
        eski = _sessiz_post(istemci, '/calculate', dict(
            HIBRIT_TABAN, thrust=3000.0, burn_time=10.0,
            initial_port_diameter=0.05, chamber_diameter_input=70.0))
        assert eski.status_code == 422, eski.get_data(as_text=True)[:300]
        r = _sessiz_post(istemci, '/calculate', dict(
            HIBRIT_TABAN, thrust=3000.0, burn_time=10.0,
            total_impulse=45000.0))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        return r.get_json()

    def test_beyan_metni_her_yankiyi_iddia_etmez(self, kirpilmis):
        beyan = kirpilmis['inputs_not_used'][0]
        assert 'every echo' not in beyan['message'], (
            'beyan hâlâ ölçülmemiş bir iddia taşıyor')

    def test_gonderilen_degeri_tasiyan_yapraklar_adiyla_yayimlanir(
            self, kirpilmis):
        beyan = kirpilmis['inputs_not_used'][0]
        yollar = beyan['submitted_value_still_shown_at']
        assert beyan['field'] == 'burn_time'
        # v3.0.1: bu araçta gönderilen değerin yankısı 0 (ölçüldü); sayaç
        # ile liste yine birbirini tutmak zorunda. Yankı > 0 hâli (eskiden
        # ``design_summary.performance.burn_time_requested_s``) aşağıdaki
        # doğrudan ölçüm bekçisinde.
        assert beyan['submitted_value_echo_count'] == len(yollar)
        assert beyan['solved_value_echo_count'] > 0

    def test_gonderilen_degeri_tasiyan_HICBIR_yaprak_atlanmiyor(
            self, kirpilmis):
        """Beyanın metni "her yol listelendi" diyor — ÖLÇÜLEREK sınanır.

        ÖH D15 birleştirme (1 Eyl 2026) kusuru geri getirmişti: yaprak adı
        ``burn_time_requested_s``e dönünce ölçüm ad kümesine takıldı ve
        gönderilen değeri taşıyan 9 yapraktan 5'i listede YOKTU. Bekçi
        ada değil ÖLÇÜME bağlanır: gövde gezilir, ``burn_time`` adını
        taşıyan ve gönderilen değere eşit HER yaprağın beyanda geçmesi
        şart koşulur. Böylece dördüncü bir ad doğarsa da kırmızıya döner.
        """
        beyan = kirpilmis['inputs_not_used'][0]
        yayimlanan = set(beyan['submitted_value_still_shown_at'])

        def _gez(dugum, on=''):
            if isinstance(dugum, dict):
                for k, v in dugum.items():
                    yield from _gez(v, f'{on}.{k}' if on else str(k))
            elif isinstance(dugum, list):
                for i, v in enumerate(dugum):
                    yield from _gez(v, f'{on}[{i}]')
            else:
                yield on, dugum

        tasiyan = set()
        for yol, deger in _gez(kirpilmis):
            if isinstance(deger, bool) or not isinstance(deger, (int, float)):
                continue
            if 'burn_time' not in yol.split('.')[-1]:
                continue
            if math.isclose(float(deger), beyan['submitted'], rel_tol=1e-9):
                tasiyan.add(yol)

        # v3.0.1: bu araçta gönderilen değer hiç yankılanmıyor (kırpma yolu
        # kapandı); ölçüm yine "listede olmayan taşıyıcı yok" şartını sınar.
        assert not (tasiyan - yayimlanan), (
            'beyan "her yol listelendi" diyor ama şu yapraklar gönderilen '
            'değeri taşıdığı hâlde yayımlanmıyor: %s'
            % sorted(tasiyan - yayimlanan))

    def test_yayimlanan_yollar_gercekten_o_degeri_tasiyor(self, kirpilmis):
        """Beyan ÖLÇÜM olmalı: her yol gövdede gerçekten 40,0 göstermeli."""
        beyan = kirpilmis['inputs_not_used'][0]

        def _oku(kok, yol):
            dugum = kok
            for parca in yol.split('.'):
                dugum = dugum[parca]
            return dugum

        for yol in beyan['submitted_value_still_shown_at']:
            assert _oku(kirpilmis, yol) == pytest.approx(
                beyan['submitted'], rel=1e-9), yol

    def test_yankili_govdede_her_yol_olculur(self):
        """v3.0.1 kulvar P: yankı > 0 hâli ``_beyan_yankilarini_olc``
        üzerinden DOĞRUDAN ölçülür (ürün yolunda kırpma kalmadığı için).
        Gövde test düzeneğidir: istenen değer tasarım noktası bloklarında,
        çözülen değer manşette durur — eski kırpılan yanıtın biçimi."""
        govde = {
            'design_summary': {'performance': {
                'burn_time_requested_s': 40.0, 'burn_time_s': 2.5}},
            'impulse_input_resolution': {'burn_time_s': 40.0},
            'burn_time': 2.5, 'burn_time_effective_s': 2.5,
        }
        beyan = [{'field': 'burn_time', 'submitted': 40.0,
                  'used_by_model': 2.5, 'reason': 'solved_by_model',
                  'message': "'burn_time' was supplied as 40"}]
        olculen = app_modulu._beyan_yankilarini_olc(govde, beyan)[0]
        yollar = set(olculen['submitted_value_still_shown_at'])
        assert yollar == {'design_summary.performance.burn_time_requested_s',
                          'impulse_input_resolution.burn_time_s'}
        assert olculen['submitted_value_echo_count'] == 2
        # Ad kümesi (burn_time, burn_time_s, burn_time_requested_s):
        # ``burn_time_effective_s`` sayılmaz -> çözülen yankı 2.
        assert olculen['solved_value_echo_count'] == 2
        assert 'every echo' not in olculen['message']

    def test_yankisi_olmayan_kosuda_liste_bos_kalir(self, istemci):
        """``burn_time`` gerçekten kullanılıyorsa beyan hiç üretilmez."""
        r = _sessiz_post(istemci, '/calculate', dict(HIBRIT_TABAN))
        assert 'inputs_not_used' not in r.get_json()


# ---------------------------------------------------------------------------
# P7B2-02 — sıvı bandı dışında SAYI yayımlanmaz
# ---------------------------------------------------------------------------
class TestP7B202OksitleyiciBandi:
    """Kalemin BAŞLIĞI (negatif yoğunluk) ÖH Z1'de kapanmış; bu bekçi
    kapandığı hâlde kalır (regresyon) ve ölçülen KALAN asimetriyi tutar:
    n2o bant dışında 400 verirken h2o2/lox 200 + depolama değeri veriyordu.
    """

    @pytest.mark.parametrize('akiskan,T', [('h2o2', 2000.0), ('h2o2', 3000.0),
                                           ('h2o2', 500.0), ('lox', 293.15),
                                           ('n2o', 2000.0)])
    def test_bant_disi_sicaklikta_sayi_donmez(self, istemci, akiskan, T):
        r = _sessiz_post(istemci, '/api/oxidizer-properties',
                         {'oxidizer_type': akiskan, 'temperature': T})
        assert r.status_code == 400, f'{akiskan} @ {T} K hâlâ sayı döndürüyor'
        govde = r.get_json()
        assert govde['error_code'] == 'oxidizer_state_undefined'
        assert govde.get('field') == 'temperature'
        assert 'properties' not in govde

    @pytest.mark.parametrize('akiskan,T', [('h2o2', 293.15), ('lox', 90.19),
                                           ('n2o', 293.15)])
    def test_bant_ici_kosum_degismez(self, istemci, akiskan, T):
        r = _sessiz_post(istemci, '/api/oxidizer-properties',
                         {'oxidizer_type': akiskan, 'temperature': T})
        assert r.status_code == 200
        rho = r.get_json()['properties']['density']
        assert rho > 0.0, 'yoğunluk pozitif olmalı (kalemin özgün başlığı)'

    def test_sicaklik_verilmediginde_davranis_bit_ayni(self, istemci):
        """Kapı DAR: durum sorulmadıysa referans durumu meşrudur."""
        r = _sessiz_post(istemci, '/api/oxidizer-properties',
                         {'oxidizer_type': 'lox'})
        assert r.status_code == 200
        assert r.get_json()['properties']['density'] == pytest.approx(1141.0)

    def test_sonlu_olmayan_sicaklik_govdeye_sizmaz(self, istemci):
        r = _sessiz_post(istemci, '/api/oxidizer-properties',
                         {'oxidizer_type': 'h2o2',
                          'temperature': float('inf')})
        assert r.status_code == 400
        ham = r.get_data(as_text=True)
        assert 'Infinity' not in ham and 'NaN' not in ham

    def test_negatif_yogunluk_uretilemez(self, istemci):
        """Kalemin ÖZGÜN başlığı: 1450 - 1,5·(T-293,15) geri gelmesin."""
        for T in (293.15, 400.0, 423.0):
            r = _sessiz_post(istemci, '/api/oxidizer-properties',
                             {'oxidizer_type': 'h2o2', 'temperature': T})
            if r.status_code == 200:
                assert r.get_json()['properties']['density'] > 0.0
        kaynak = open(APP_KAYNAK, encoding='utf-8').read()
        assert '1450 - 1.5' not in kaynak and '1450-1.5' not in kaynak


# ---------------------------------------------------------------------------
# P7B2-05 — dışa aktarma geometri kapısı paritesi (REGRESYON bekçisi)
# ---------------------------------------------------------------------------
class TestP7B205DisaAktarmaKapisiParitesi:
    """Kalem ÖH Z5S / S7 (P16B4-21) tarafından kapatılmış; ölçüm bunu
    doğruladı (once_a2.json: 5 uç x 3 bozuk geometri = 15/15 kez 422,
    117.824 B'lık ZIP üretilemiyor). Bekçi YOKTU — buraya konur ki kapı
    bir daha sessizce düşmesin."""

    _NAN = float('nan')
    VAKALAR = {
        'NaN': {'chamber_diameter': _NAN, 'chamber_length': _NAN,
                'throat_diameter': _NAN},
        'sifir': {'chamber_diameter': 0, 'chamber_length': 0,
                  'throat_diameter': 0},
        'negatif': {'chamber_diameter': -100, 'chamber_length': -500,
                    'throat_diameter': -40},
    }

    @pytest.mark.parametrize('uc,anahtar', [
        ('/export_solid_motor_cad', 'results'),
        ('/export_liquid_cad', 'results'),
        ('/export_tank_cad', 'tank_data'),
        ('/api/export-stl-zip', 'motor_data'),
        ('/api/generate-complete-package', 'motor_data')])
    @pytest.mark.parametrize('vaka', ['NaN', 'sifir', 'negatif'])
    def test_bozuk_geometriyle_zip_uretilmez(self, istemci, uc, anahtar,
                                             vaka):
        r = _sessiz_post(istemci, uc, {anahtar: self.VAKALAR[vaka]})
        assert r.status_code == 422, (
            f'{uc} {vaka} geometriyle {r.status_code} döndü '
            f'({len(r.get_data())} B)')
        assert 'zip' not in (r.headers.get('Content-Type') or '').lower()

    def test_kapi_kardes_uclarda_da_cagriliyor(self):
        """AST: iki CAD ucu kapıyı DÖNÜŞÜMDEN ÖNCE çağırmalı."""
        agac = ast.parse(open(APP_KAYNAK, encoding='utf-8').read())
        for ad in ('export_solid_motor_cad', 'export_liquid_cad'):
            fn = [d for d in ast.walk(agac)
                  if isinstance(d, ast.FunctionDef) and d.name == ad]
            assert len(fn) == 1, ad
            cagrilar = [d.func.id for d in ast.walk(fn[0])
                        if isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Name)]
            assert '_reject_unexportable_geometry' in cagrilar, ad
            assert (cagrilar.index('_reject_unexportable_geometry')
                    < cagrilar.index(f'{ad.split("_")[1]}_results_to'
                                     '_motor_geometry')), (
                f'{ad}: kapı normalleştiricinin ARDINDAN çağrılıyor')
