# -*- coding: utf-8 -*-
"""ÖH D24 / yapisal-sistem — aşama 1 bekçileri.

Her sınıf, ÖLÇÜLMÜŞ bir kusurun geri gelmesini kırmızıya çevirir. Ölçüm
betiği ``docs/scofield/raw/OH/D24/yapisal-sistem/a1/olcum.py``, taban
çıktısı ``once.json``, onarım sonrası ``sonra.json``; ters mutasyon
kanıtları ``mutasyon.json``.
"""
import ast
import importlib
import json
import os
import subprocess
import sys
import tempfile

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _yeniden_yukle(env_adi=None, env_degeri=None):
    """``tile_cache``i verilen ortam değişkeniyle taze yükle.

    Modül düzeyi sabit (``TILE_CACHE_MAX_BYTES``) ithal anında çözüldüğü
    için ortam değişkeni ancak yeniden yüklemeyle etkili olur. Ortam
    değişikliği ``finally`` ile geri alınır.
    """
    import hrma.analysis.tile_cache as tc
    eski = os.environ.get(env_adi) if env_adi else None
    try:
        if env_adi is not None:
            if env_degeri is None:
                os.environ.pop(env_adi, None)
            else:
                os.environ[env_adi] = env_degeri
        return importlib.reload(tc)
    finally:
        if env_adi is not None:
            if eski is None:
                os.environ.pop(env_adi, None)
            else:
                os.environ[env_adi] = eski


def _yukle_hata_bekleyerek(ham):
    """Bozuk ortam değişkeniyle yeniden yükle; istisnayı DÖNDÜR.

    ``pytest.raises(tc.TileCacheConfigError)`` burada işe yaramaz: reload
    modül ad alanını yeniden çalıştırır, yani sınıf NESNESİ yenilenir ve
    ``with`` satırında yakalanan ESKİ sınıfla kimlik tutmaz. Tip, adıyla
    doğrulanır. Modül her hâlükârda sağlam duruma geri yüklenir.
    """
    import hrma.analysis.tile_cache as tc
    eski = os.environ.get('HRMA_TILE_CACHE_MAX_BYTES')
    os.environ['HRMA_TILE_CACHE_MAX_BYTES'] = ham
    try:
        importlib.reload(tc)
        return None
    except ValueError as e:
        return e
    finally:
        if eski is None:
            os.environ.pop('HRMA_TILE_CACHE_MAX_BYTES', None)
        else:
            os.environ['HRMA_TILE_CACHE_MAX_BYTES'] = eski
        importlib.reload(tc)


@pytest.fixture(autouse=True, scope='module')
def _modulu_temiz_birak():
    """Modül sonunda ``tile_cache``i varsayılan ortamla geri yükle."""
    yield
    import hrma.analysis.tile_cache as tc
    os.environ.pop('HRMA_TILE_CACHE_MAX_BYTES', None)
    importlib.reload(tc)


# ===========================================================================
# P5B4-27 — önbellek tavanı sessizce 0/-1 kabul ediliyordu
# ===========================================================================
class TestP5B427OnbellekTavani:
    """ÖLÇÜLDÜ (taban 88a29d3, ``once.json``): ``HRMA_TILE_CACHE_MAX_BYTES``
    değeri 0 -> cap 0, -1 -> cap -1 kabul ediliyordu; ``abc`` ve ``4.5``
    ise SESSİZCE 400 MB'a düşüyordu. cap=0 iken tek ``_enforce_cap``
    çağrısı 50 karoluk önbelleği 0 karoya indiriyordu (ölçüldü).
    """

    @pytest.mark.parametrize('ham', ['0', '-1', '-1048576'])
    def test_sifir_ve_negatif_cap_reddedilir(self, ham):
        hata = _yukle_hata_bekleyerek(ham)
        assert hata is not None, f'{ham} sessizce kabul edildi'
        assert type(hata).__name__ == 'TileCacheConfigError'
        assert 'HRMA_TILE_CACHE_MAX_BYTES' in str(hata)
        assert ham in str(hata)

    @pytest.mark.parametrize('ham', ['abc', '4.5', ''])
    def test_sayi_olmayan_deger_sessizce_varsayilana_dusmez(self, ham):
        hata = _yukle_hata_bekleyerek(ham)
        assert hata is not None, (
            f'{ham!r} sessizce belgelenmiş varsayılana düştü')
        assert type(hata).__name__ == 'TileCacheConfigError'
        assert 'is not an integer' in str(hata)

    def test_gecerli_deger_uygulanir(self):
        tc = _yeniden_yukle('HRMA_TILE_CACHE_MAX_BYTES', '1048576')
        assert tc.TILE_CACHE_MAX_BYTES == 1048576

    def test_tanimsizsa_belgelenmis_varsayilan(self):
        tc = _yeniden_yukle('HRMA_TILE_CACHE_MAX_BYTES', None)
        assert tc.TILE_CACHE_MAX_BYTES == 400 * 1024 * 1024


# ===========================================================================
# P5B4-28 — karo kutusu dünya dışına taşıyordu; negatif z ham hata veriyordu
# ===========================================================================
class TestP5B428KaroKutusu:
    """ÖLÇÜLDÜ: z=0 son karo ``(108,0, -198,0, 396,0, 90,0)`` — hem boylam
    hem enlem dünya dışında (z0/z1/z2). Negatif z ise çıplak
    ``ValueError: negative shift count`` veriyordu (alan adı yok).
    """

    @pytest.mark.parametrize('z', [0, 1, 2, 3, 4, 7])
    def test_hicbir_karo_dunyayi_tasmaz(self, z):
        import hrma.analysis.tile_cache as tc
        mw, mh = tc.matrix_size(z)
        for x in (0, mw - 1):
            for y in (0, mh - 1):
                lon_w, lat_s, lon_e, lat_n = tc.tile_to_bbox(z, x, y)
                assert -180.0 <= lon_w <= 180.0
                assert -180.0 <= lon_e <= 180.0
                assert -90.0 <= lat_s <= 90.0
                assert -90.0 <= lat_n <= 90.0

    @pytest.mark.parametrize('z', [3, 4, 5, 6, 7])
    def test_kirpma_gecerli_zoomlarda_etkisiz(self, z):
        """z>=3'te matris dünyayla birebir örtüşür — sayı DEĞİŞMEZ."""
        import hrma.analysis.tile_cache as tc
        span = tc.tile_span_deg(z)
        mw, mh = tc.matrix_size(z)
        for x, y in ((0, 0), (mw - 1, mh - 1), (mw // 2, mh // 2)):
            lon_w, lat_s, lon_e, lat_n = tc.tile_to_bbox(z, x, y)
            assert lon_e - lon_w == pytest.approx(span)
            assert lat_n - lat_s == pytest.approx(span)

    @pytest.mark.parametrize('fn_adi', ['tile_span_deg', 'matrix_size'])
    @pytest.mark.parametrize('z', [-1, -8, True, 1.5, '4', None])
    def test_gecersiz_zoom_alan_adiyla_reddedilir(self, fn_adi, z):
        import hrma.analysis.tile_cache as tc
        with pytest.raises(ValueError) as ex:
            getattr(tc, fn_adi)(z)
        mesaj = str(ex.value)
        assert "'z'" in mesaj and 'negative shift count' not in mesaj

    def test_bbox_da_ayni_kapiyi_kullanir(self):
        import hrma.analysis.tile_cache as tc
        with pytest.raises(ValueError) as ex:
            tc.tile_to_bbox(-1, 0, 0)
        assert "'z'" in str(ex.value)


# ===========================================================================
# P5B4-29 — 'ön yüz viirs'i sunar' iddiası yalandı
# ===========================================================================
class TestP5B429YayimlananKatman:
    """ÖLÇÜLDÜ: depoda ``viirs`` araması ``tile_cache.py`` DIŞINDA yalnız
    testlerde eşleşiyor (JS'te 0 geçiş, ``TILE_LAYER='bluemarble'``
    sabit); buna karşın katman ``/api/tile/cache/status`` gövdesinde
    diğerinin yanında ayırt edilmeden yayımlanıyordu.
    """

    def _js(self):
        yol = os.path.join(KOK, 'hrma', 'static', 'js',
                           'launch_site_globe.js')
        return open(yol, encoding='utf-8').read()

    def test_her_katman_ui_gercegini_beyan_eder(self):
        import hrma.analysis.tile_cache as tc
        kat = tc.list_layers()
        assert 'layers_basis' in kat
        for ad, k in kat['layers'].items():
            assert 'ui_offered' in k, f'{ad}: ui_offered beyanı yok'
            assert 'served' in k, f'{ad}: served beyanı yok'
            assert isinstance(k['ui_offered'], bool)

    def test_beyan_on_yuzun_gercegiyle_ayni(self):
        """``ui_offered=True`` ancak JS gerçekten o katmanı sunuyorsa.

        Ölçüt uydurma değil: JS'in ``TILE_ATTRIBUTION_KEY`` haritası hangi
        katmanın künyesini basabiliyorsa arayüzün sunabildiği katman odur
        (fail-closed: künyesi olmayan katman çizilmez).
        """
        import hrma.analysis.tile_cache as tc
        js = self._js()
        for ad, k in tc.list_layers()['layers'].items():
            js_de_var = (f'{ad}:' in js) or (f"'{ad}'" in js)
            assert k['ui_offered'] is js_de_var, (
                f'{ad}: ui_offered={k["ui_offered"]} ama JS gerçeği '
                f'{js_de_var}')

    def test_viirs_sunuluyor_diye_yayimlanmiyor(self):
        import hrma.analysis.tile_cache as tc
        assert tc.list_layers()['layers']['viirs']['ui_offered'] is False
        assert self._js().count('viirs') == 0

    def test_yanlis_kunye_geri_gelmedi(self):
        kaynak = open(os.path.join(KOK, 'hrma', 'analysis', 'tile_cache.py'),
                      encoding='utf-8').read()
        # Taban satırı aynen: "bulut riski taşır → varsayılan DEĞİL, ön
        # yüz dürüstlük uyarısıyla sunar." Tarihçe alıntısı tırnak
        # içindedir, bu yüzden yalnız İDDİA biçimi aranır.
        assert 'DEĞİL, ön yüz dürüstlük uyarısıyla sunar' not in kaynak

    def test_atif_kunye_anahtari_metni_ikinci_kez_yazmaz(self):
        """Ekrandaki künyenin TEK kaynağı i18n sözlüğü; burada anahtar."""
        import hrma.analysis.tile_cache as tc
        k = tc.list_layers()['layers']['bluemarble']
        assert k['attribution_i18n_key'] == 'site.tileAttribution'
        assert (tc.list_layers()['layers']['viirs']['attribution_i18n_key']
                is None)


# ===========================================================================
# P5B4-35 — app.py künyesi atfın kaynağını yanlış gösteriyordu
# ===========================================================================
class TestP5B435AtifKunyesi:
    """ÖLÇÜLDÜ: künye "arayüz #ls-tile-attr'ı /api/tile/cache/status
    gövdesinden dolduruyor" diyordu; ``refreshTileUsage`` yanıttan yalnız
    ``d.bytes`` ve ``d.tiles`` okuyor, künye metni i18n sözlüğünden
    geliyor (ÖH D21 / P12aB4-19).
    """

    ATIF = 'Blue Marble Shaded Relief + Bathymetry (~500 m)'
    #: Atıf dizesinin ölçülen kopya sayısı (taban 88a29d3: 3 birebir kopya
    #: — tile_cache.py, i18n_launch_site.js EN, launch_site.html
    #: varsayılanı; TR karşılığı ayrı bir çeviridir). Kopyaları TEK
    #: kaynağa indirmek arayüz/P15 borcudur; mandal borcun BÜYÜMESİNİ
    #: engeller ve kopyaların BİRBİRİNDEN AYRILMASINI kırmızıya çevirir.
    KOPYA_TAVANI = 3

    def test_app_kunyesindeki_yanlis_cumle_kalkti(self):
        app_py = open(os.path.join(KOK, 'hrma', 'app.py'),
                      encoding='utf-8').read()
        assert "arayüz #ls-tile-attr'ı oradan\n    # dolduruyor" not in app_py

    def test_atif_kopyalari_birbirinden_ayrilmadi(self):
        sayim = {}
        for rel in ('hrma/analysis/tile_cache.py',
                    'hrma/static/js/i18n_launch_site.js',
                    'hrma/templates/launch_site.html'):
            metin = open(os.path.join(KOK, rel), encoding='utf-8').read()
            sayim[rel] = metin.count(self.ATIF)
        assert all(v >= 1 for v in sayim.values()), (
            f'atıf kopyaları ayrıştı: {sayim}')
        assert sum(sayim.values()) <= self.KOPYA_TAVANI, (
            f'atıf kopyası çoğaldı: {sayim}')


# ===========================================================================
# P5B4-32 — künye metnine Python söz dizimi sızıyordu
# ===========================================================================
class TestP5B432DayanakMetni:
    """ÖLÇÜLDÜ: liste geçirilince ``basis`` metni
    ``... and ['burnout', 'chuffing']. ...`` üretiyordu (İngilizce
    cümlenin ortasında köşeli parantez + tırnak).
    """

    def test_liste_ingilizce_ibareye_cevrilir(self):
        from hrma.analysis.curve_sampling import sampling_block
        b = sampling_block(10, 20, 0.01, ['burnout', 'chuffing'],
                           ['impulse', 'peak thrust'])['basis']
        assert "['" not in b and "']" not in b
        assert 'burnout and chuffing' in b
        assert 'impulse and peak thrust' in b

    def test_dize_ve_liste_ayni_metni_verir(self):
        from hrma.analysis.curve_sampling import sampling_block
        liste = sampling_block(10, 20, 0.01, ['a', 'b'], ['c', 'd'])['basis']
        dize = sampling_block(10, 20, 0.01, 'a and b', 'c and d')['basis']
        assert liste == dize

    def test_dize_geciren_canli_cagiranlarda_metin_degismedi(self):
        """İki canlı çağıran düz dize geçiriyor — çapa bit-aynı kalmalı."""
        from hrma.analysis.curve_sampling import sampling_block
        b = sampling_block(5, 9, 0.02, 'burnout, chuffing and tail-off',
                           'total impulse')['basis']
        assert 'and burnout, chuffing and tail-off.' in b

    @pytest.mark.parametrize('girdi,beklenen', [
        (['a'], 'a'),
        (['a', 'b'], 'a and b'),
        (['a', 'b', 'c'], 'a, b and c'),
        ([], 'no items'),
    ])
    def test_ibare_kurallari(self, girdi, beklenen):
        from hrma.analysis.curve_sampling import _dayanak_metni
        assert _dayanak_metni(girdi) == beklenen


# ===========================================================================
# P5B4-36 — regresyon yanıtı birim beyan etmiyordu
# ===========================================================================
class TestP5B436BirimBeyani:
    """ÖLÇÜLDÜ: yanıtta ``units`` yok; ``regression_rate`` mm/s,
    ``port_diameter`` mm, ``parameters.a`` SI. Tüketici ``r = a·G^n``i
    yanıttaki sayılarla doğrulasa 1000 kat sapardı.
    """

    @pytest.fixture(scope='class')
    def sonuc(self):
        from hrma.analysis.regression_analysis import regression_analyzer
        return regression_analyzer.analyze_regression_vs_time({
            'burn_time': 10.0, 'mdot_ox': 0.5,
            'port_diameter_initial': 0.05, 'port_diameter_final': 0.08,
            'fuel_type': 'htpb'})

    def test_yayimlanan_her_dizi_birimini_beyan_eder(self, sonuc):
        from hrma.analysis.regression_analysis import (
            REGRESSION_OUTPUT_UNITS)
        assert sonuc['units'] == REGRESSION_OUTPUT_UNITS
        for ad in ('time', 'regression_rate', 'port_diameter',
                   'oxidizer_flux', 'total_flux', 'fuel_flux',
                   'fuel_flux_exit', 'fuel_mass_flow'):
            assert ad in sonuc, f'{ad} yayımlanmıyor'
            assert ad in sonuc['units'], f'{ad} birimi beyan edilmiyor'
        assert 'parameters.a' in sonuc['units']
        assert 'parameters.n' in sonuc['units']

    def test_beyan_edilen_birim_gercekle_uyusuyor(self, sonuc):
        """``r_dot = a·G^n`` SI'de; yayımlanan dizi mm/s — 1000 kat."""
        a = sonuc['parameters']['a']
        n = sonuc['parameters']['n']
        g = sonuc['oxidizer_flux'][0]
        si_m_s = a * g ** n
        assert sonuc['units']['regression_rate'] == 'mm/s'
        assert sonuc['regression_rate'][0] == pytest.approx(
            si_m_s * 1000.0, rel=1e-9)

    def test_birim_kunyesi_1000_kati_soyluyor(self, sonuc):
        assert 'units_basis' in sonuc
        assert '1000' in sonuc['units_basis']

    def test_app_ikinci_bir_birim_tablosu_tutmuyor(self):
        """TEK KAYNAK: uç, tabloyu çözümleyicinin sabitinden okur.

        ÖLÇÜLDÜ (taban 88a29d3): ``hrma/app.py`` kendi
        ``_REGRESSION_OUTPUT_UNITS`` sözlüğünü tutuyordu ve o kopya
        EKSİKTİ — ``parameters.a``/``parameters.n`` hiç anılmıyordu, yani
        1000 katlık tuzak yanıtta yazılı değildi.
        """
        kaynak = open(os.path.join(KOK, 'hrma', 'app.py'),
                      encoding='utf-8').read()
        assert '_REGRESSION_OUTPUT_UNITS = {' not in kaynak
        assert ('REGRESSION_OUTPUT_UNITS as _REGRESSION_OUTPUT_UNITS'
                in kaynak)

    def test_uctaki_birim_tablosu_modulunkiyle_ayni(self):
        from hrma.analysis.regression_analysis import (
            REGRESSION_OUTPUT_UNITS)
        from hrma.app import _REGRESSION_OUTPUT_UNITS
        assert _REGRESSION_OUTPUT_UNITS is REGRESSION_OUTPUT_UNITS
        assert 'parameters.a' in _REGRESSION_OUTPUT_UNITS


# ===========================================================================
# P5B4-37 — paket ithalleri sessizce yutuluyordu
# ===========================================================================
class TestP5B437SessizIthalYutumu:
    """ÖLÇÜLDÜ: ``hrma/analysis/__init__.py`` beş ithali
    ``try/except ImportError`` ile yutup ``warnings.warn`` basıyordu; ad
    çok sonra ``AttributeError`` olarak patlıyordu. Bu beş adı paket ad
    alanından çeken tüketici YOK (``git grep`` ile ölçüldü).
    """

    def test_ithaller_try_except_icinde_degil(self):
        yol = os.path.join(KOK, 'hrma', 'analysis', '__init__.py')
        agac = ast.parse(open(yol, encoding='utf-8').read())
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Try):
                icerdekiler = [g for g in ast.walk(dugum)
                               if isinstance(g, (ast.Import, ast.ImportFrom))]
                assert not icerdekiler, (
                    'ithal yeniden try/except içine alındı: '
                    f'{[getattr(g, "module", None) for g in icerdekiler]}')

    def test_hata_yutulmuyor(self):
        """AST ile ölçülür — tarihçe yorumunda geçen ad sayılmaz."""
        yol = os.path.join(KOK, 'hrma', 'analysis', '__init__.py')
        agac = ast.parse(open(yol, encoding='utf-8').read())
        yakalanan = [getattr(h.type, 'id', None)
                     for d in ast.walk(agac) if isinstance(d, ast.Try)
                     for h in d.handlers]
        assert 'ImportError' not in yakalanan
        cagrilar = [ast.unparse(d.func) for d in ast.walk(agac)
                    if isinstance(d, ast.Call)]
        assert 'warnings.warn' not in cagrilar

    def test_bes_ad_hala_paket_yuzunde(self):
        import hrma.analysis as pkt
        for ad in ('HeatTransferAnalyzer', 'StructuralAnalyzer',
                   'SafetyAnalyzer', 'RegressionAnalyzer',
                   'regression_analyzer', 'TrajectoryAnalyzer'):
            assert hasattr(pkt, ad), f'{ad} paket yüzünden düştü'

    def test_bozuk_alt_modul_paket_ithalini_dusurur(self):
        """Alt modül patlarsa ``import hrma.analysis`` de patlar.

        Ölçüm ayrı süreçte: ``hrma.analysis.trajectory_analysis`` yerine
        patlayan bir sahte modül konur; taban davranışı "paket yüklenir,
        ad sonra AttributeError olur" idi.
        """
        kod = (
            'import sys, json\n'
            f'sys.path.insert(0, {KOK!r})\n'
            'import types\n'
            'kirik = types.ModuleType("hrma.analysis.trajectory_analysis")\n'
            'class _Patla:\n'
            '    def __getattr__(self, ad):\n'
            '        raise ImportError("sahte kirik alt modul")\n'
            'sys.modules["hrma.analysis.trajectory_analysis"] = _Patla()\n'
            'try:\n'
            '    import hrma.analysis\n'
            '    print(json.dumps({"paket_yuklendi": True}))\n'
            'except ImportError as e:\n'
            '    print(json.dumps({"paket_yuklendi": False,\n'
            '                      "istisna": type(e).__name__}))\n')
        p = subprocess.run([sys.executable, '-c', kod], capture_output=True,
                           text=True, timeout=300,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                                    HRMA_HEADLESS='1'))
        satir = [s for s in (p.stdout or '').splitlines() if s.startswith('{')]
        assert satir, p.stderr[-400:]
        veri = json.loads(satir[-1])
        assert veri['paket_yuklendi'] is False, (
            'bozuk alt modülle paket yine yüklendi — hata yutuluyor')


# ===========================================================================
# P5B4-34 — sert başlangıç ölçütü kamaradaki gazı saymıyordu
# ===========================================================================
class TestP5B434SertBaslangic:
    """ÖLÇÜLDÜ (taban 88a29d3, ``once_p5b434.json``): ölçüt yalnız ateşleme
    gecikmesi boyunca BİRİKEN iticiyi sayıyordu. Kamarada ateşleme anında
    bulunan gaz (pürj / ullage / kalıntı / atmosfer) hiç geçmiyordu:
    ``safe_window`` içinde ``pre_existing_gas`` alanı YOKTU, ``_basis``
    metni purge/ullage/pre-existing sözcüklerinin hiçbirini anmıyordu ve
    modelin böyle bir girdisi de yoktu (``chamber_initial_pressure_Pa``
    -> ``TypeError``). Terim küçük değil: 1 bar / 293 K pürj sabit hacimde
    3400 K'e ısınınca 11,6041 bar eder — Pc = 30 bar'da payın %38,68'i.
    """

    ORTAK = dict(
        igniter_type='torch', chamber_free_volume_m3=0.002,
        main_mass_flow_kg_s=1.0, ignition_window_s=0.05,
        propellant_specific_heat_J_kg_K=1800.0,
        propellant_ignition_temperature_K=700.0,
        initial_temperature_K=293.0, chamber_pressure_Pa=30e5,
        main_gas_molecular_weight_g_mol=22.0,
        main_flame_temperature_K=3400.0,
        torch_heat_release_J_kg=1.2e7)

    def test_on_gaz_basinci_kapali_cozumle_ayni(self):
        """P = P_0*T_flame/T_0 — sabit hacim, sabit mol (ideal gaz)."""
        from hrma.analysis.igniter_sizing import pre_existing_gas_pressure
        p = pre_existing_gas_pressure(
            initial_pressure_Pa=1e5, initial_temperature_K=293.0,
            flame_temperature_K=3400.0)
        assert p == pytest.approx(1e5 * 3400.0 / 293.0, rel=1e-12)
        assert p / 1e5 == pytest.approx(11.604095563, rel=1e-9)

    def test_verilmediginde_alt_sinir_oldugu_yaziyor(self):
        from hrma.analysis.igniter_sizing import size_igniter
        w = size_igniter(**self.ORTAK)['safe_window']
        assert 'pre_existing_gas' in w
        assert w['pre_existing_gas']['included'] is False
        gerekce = w['pre_existing_gas']['reason'].lower()
        for sozcuk in ('purge', 'ullage', 'lower bound'):
            assert sozcuk in gerekce, f'{sozcuk!r} anılmıyor'

    def test_verilince_tepe_basinca_katilir(self):
        from hrma.analysis.igniter_sizing import (
            hard_start_pressure, pre_existing_gas_pressure)
        ortak = dict(main_mass_flow_kg_s=1.0, ignition_delay_s=0.005,
                     free_volume_m3=0.002,
                     gas_molecular_weight_g_mol=22.0,
                     flame_temperature_K=3400.0)
        yalin = hard_start_pressure(**ortak)
        katkili = hard_start_pressure(
            chamber_initial_pressure_Pa=1e5,
            chamber_initial_temperature_K=293.0, **ortak)
        p_pre = pre_existing_gas_pressure(
            initial_pressure_Pa=1e5, initial_temperature_K=293.0,
            flame_temperature_K=3400.0)
        assert katkili == pytest.approx(yalin + p_pre, rel=1e-12)
        assert katkili > yalin

    def test_pencere_paydan_on_gazi_duser(self):
        from hrma.analysis.igniter_sizing import safe_ignition_window_s
        ortak = dict(main_mass_flow_kg_s=1.0, free_volume_m3=0.002,
                     gas_molecular_weight_g_mol=22.0,
                     flame_temperature_K=3400.0,
                     allowable_pressure_Pa=30e5)
        genis = safe_ignition_window_s(**ortak)
        dar = safe_ignition_window_s(chamber_initial_pressure_Pa=1e5,
                                     chamber_initial_temperature_K=293.0,
                                     **ortak)
        assert dar < genis, 'ön gaz pencereyi kısaltmadı'
        assert dar == pytest.approx(genis * (1.0 - 0.38680318543799774),
                                    rel=1e-9)

    def test_pay_tek_basina_dolduysa_hukum_verilmez(self):
        """Fail-closed: pencere 0'a KIRPILMAZ, hüküm kazanılmaz."""
        from hrma.analysis.igniter_sizing import (
            HardStartAllowanceExceeded, safe_ignition_window_s,
            size_igniter)
        with pytest.raises(HardStartAllowanceExceeded) as ex:
            safe_ignition_window_s(
                main_mass_flow_kg_s=1.0, free_volume_m3=0.002,
                gas_molecular_weight_g_mol=22.0,
                flame_temperature_K=3400.0, allowable_pressure_Pa=5e5,
                chamber_initial_pressure_Pa=1e5,
                chamber_initial_temperature_K=293.0)
        assert 'already in the chamber' in str(ex.value)
        ortak = dict(self.ORTAK)
        ortak['chamber_pressure_Pa'] = 5e5
        w = size_igniter(chamber_initial_pressure_Pa=1e5,
                         chamber_initial_temperature_K=293.0,
                         **ortak)['safe_window']
        assert w['status'] == 'no_safe_window'
        assert 'verdict' not in w, 'kazanılmamış hüküm yayımlandı'
        assert w['pre_existing_gas']['included'] is True

    def test_basis_metni_terimi_aniyor(self):
        from hrma.analysis.igniter_sizing import size_igniter
        w = size_igniter(**self.ORTAK)['safe_window']
        assert 'purge' in w['_basis'].lower()
