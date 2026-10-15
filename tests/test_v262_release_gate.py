"""v2.6.2 sürüm kapısı — "bitti" iddiasını mekanik olarak sınar.

Bu dosya bir özellik testi değil, bir KABUL KAPISIDIR. v2.6.2'nin ilan edilen
kapsamındaki her madde ve denetimlerden gelen her kritik bulgu burada tek tek
doğrulanır. Yeşilse sürüm çıkabilir; kırmızıysa hangi maddenin eksik olduğunu
adıyla söyler.

Var olma sebebi: bu projede "modül yazıldı" ile "kullanıcıya ulaşıyor" arasında
tekrar tekrar sessiz kopukluklar oluştu — ``input_guard.py`` yazıldı ama kimse
import etmedi (safe_name NameError'ı oradan çıktı), ``flight_vehicle.py`` ve
``tile_cache.py`` yazıldı ama hiçbir rotaya bağlanmadı, ``flight_handoff.js``
yazıldı ama hiçbir şablon yüklemedi. Bu kapı o kopuklukları yakalar.
"""

import ast
import json
import re
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


# ===========================================================================
# 1. Sürüm hijyeni
# ===========================================================================

class TestVersionHygiene:
    def test_package_version_matches_changelog(self):
        """Paket sürümü ile changelog'un en üst girdisi AYNI olmalı.

        v2.6.25 değişikliği: burada eskiden '2.6.2' sabiti vardı. Sabit sürüm
        beklentisi her yayında elle güncellenmek zorunda kaldığı için gerçek
        bir kapı değil, bakım yüküydü. Şimdi iki kaynağın tutarlılığı
        sınanıyor — sürüm numarası ne olursa olsun kapı çalışır.
        """
        import hrma
        d = json.loads(_read('hrma/data/changelog.json'))
        top = d['versions'][0]
        assert hrma.__version__ == top['version'], (
            'hrma.__version__=%s ama changelog en üst girdi=%s'
            % (hrma.__version__, top['version']))

    def test_changelog_top_entry_is_bilingual_and_measured(self):
        d = json.loads(_read('hrma/data/changelog.json'))
        top = d['versions'][0]
        assert top.get('notes_en') and top.get('notes_tr')
        # Sürüm notu ölçülmüş sayı içermeli, pazarlama cümlesi değil
        assert re.search(r'\d', top['notes_en']), 'sürüm notunda tek sayı yok'
        assert re.search(r'\d', top['notes_tr'])

    def test_262_entry_still_present_with_its_numbers(self):
        """Geçmiş sürüm notları silinmemeli (changelog kümülatiftir)."""
        d = json.loads(_read('hrma/data/changelog.json'))
        girdi = {v['version']: v for v in d['versions']}.get('2.6.2')
        assert girdi is not None, '2.6.2 girdisi changelog\'dan düşmüş'
        assert '15.9' in girdi['notes_en'], 'swirl bulgusu sayısıyla anlatılmamış'
        assert '15,9' in girdi['notes_tr'] or '15.9' in girdi['notes_tr']


# ===========================================================================
# 2. A1/A2/A3/B1 — v2.6.2'nin ilan edilen özellikleri
# ===========================================================================

class TestDeclaredFeatures:
    def test_all_new_routes_registered(self):
        from hrma.app import app
        rules = {str(r) for r in app.url_map.iter_rules()}
        for want in ('/api/flight-vehicle',
                     '/api/tile/<layer_key>/<int:z>/<int:x>/<int:y>',
                     '/api/tile/cache/status',
                     '/api/tile/cache/clear'):
            assert want in rules, f'{want} rotası kayıtlı değil'

    def test_flight_handoff_loaded_and_called(self):
        """A1: köprü betiği üç motor sayfasında yüklü VE çağrılıyor olmalı."""
        for rel in ('hrma/templates/advanced.html', 'hrma/templates/solid.html',
                    'hrma/templates/liquid.html'):
            assert 'flight_handoff.js' in _read(rel), f'{rel}: betik yüklenmiyor'
        for rel, mt in (('hrma/static/js/app.js', 'hybrid'),
                        ('hrma/templates/solid.html', 'solid'),
                        ('hrma/templates/liquid.html', 'liquid')):
            src = _read(rel)
            assert 'FlightHandoff.publish' in src, f'{rel}: publish çağrısı yok'
            assert f"motor_type: '{mt}'" in src, f'{rel}: motor tipi geçilmiyor'

    def test_launch_site_flies_real_vehicle_not_demo(self):
        """A1: sabit demo araç sökülmüş, gerçek araç bağlanmış olmalı."""
        src = _read('hrma/templates/launch_site.html')
        assert 'currentVehicle' in src
        assert 'EXAMPLE_VEHICLE' in src, 'örnek araç ayrı etiketlenmemiş'
        assert '/api/flight-vehicle' in src

    def test_coriolis_latitude_reaches_solver(self):
        """B1: saha enlemi 6-DOF çözücüsüne geçmeli (düz-Dünya varsayımı kalkar)."""
        assert 'latitude_deg: la' in _read('hrma/templates/launch_site.html')
        assert 'latitude_deg' in _read('hrma/app.py')

    def test_flight_controls_gated_on_solution(self):
        """A3: kontroller uçuş çözülene kadar kapalı; kararsız araçta açılmaz."""
        src = _read('hrma/templates/launch_site.html')
        assert 'setFlightControlsEnabled' in src
        assert 'static_margin_full' in src, 'kararlılık kapısı yok'
        assert 'tumble_detected' in src

    def test_tile_cache_ui_present(self):
        """A2: atıf ve önbellek yönetimi kullanıcıya görünmeli."""
        src = _read('hrma/templates/launch_site.html')
        assert 'ls-clear-tiles' in src
        assert '/api/tile/cache/clear' in src


# ===========================================================================
# 3. Denetim bulguları — kritik düzeltmeler geri gelmemeli
# ===========================================================================

class TestAuditFixesHold:
    def test_swirl_coefficient_not_inverted(self):
        import numpy as np
        from hrma.engines.injector_design import _SWIRL_GEOMETRIC_COEF
        assert _SWIRL_GEOMETRIC_COEF == pytest.approx(np.pi / (4 * np.sqrt(2)))

    def test_slosh_damping_has_amplitude_term(self):
        from hrma.analysis.slosh_analysis import CylindricalTankSlosh
        m = CylindricalTankSlosh(radius=0.5, fill_height=1.0)
        lo = m.baffle_damping(0.2, 0.1, amplitude_ratio=0.01)['damping_ratio']
        hi = m.baffle_damping(0.2, 0.1, amplitude_ratio=0.04)['damping_ratio']
        assert hi / lo == pytest.approx(2.0, rel=1e-9), 'sqrt(eta/R) terimi yok'

    def test_non_finite_never_becomes_zero(self):
        from hrma.app import sanitize_json_values
        assert sanitize_json_values(float('nan')) is None
        assert sanitize_json_values(float('inf')) is None
        assert sanitize_json_values(0.0) == 0.0   # gerçek sıfır korunur

    def test_no_process_wide_warning_suppression(self):
        """Süreç geneli catch-all filtre kalmamalı (sessiz NaN zincirinin başı).

        ÖH D32 / OH-D31-19 — ÖLÇÜM TEMİZ ALT SÜREÇTE YAPILIR.

        Bu iddia v2.6.26'ya kadar SÜREÇ İÇİ ``warnings.filters`` listesine
        bakıyordu. O liste, koşumda o ana kadar toplanmış/koşmuş her testin
        mirasını taşır: ÖLÇÜLDÜ (D31 app-api-uc a1 süpürmesi; taban
        ``9d70e9ed``) — aynı iddia 4 dosyalık kümede YEŞİL, 33 dosyalık
        kümede KIRMIZIydı, hem dalda hem TABAN ağacında. Yani hüküm ürüne
        değil KÜME SIRASINA bağlıydı ve kırmızı, kusur bildirmiyordu.

        Kök ÖLÇÜLDÜ (``docs/scofield/raw/OH/D32/altyapi/a1/once_warn.json``):
          * ÜRÜN TEMİZ — temiz yorumlayıcıda ``import hrma.app`` sonrası
            catch-all filtre sayısı 0 (17 filtrenin hiçbiri değil);
          * kirlilik TEST tarafındadır — 35 test modülü modül DÜZEYİNDE
            ``warnings.filterwarnings('ignore')`` çağırır ve bu satırlar
            toplama anında koşar.

        İddianın konusu ÜRÜN olduğuna göre ölçüm de ürünü görmelidir:
        temiz bir yorumlayıcı açılır. Sıra artık hükmü değiştiremez.
        Test tarafındaki susturma envanteri ayrı bir bekçiyle ADIYLA
        kilitlidir: ``tests/test_d32_altyapi_a1.py``
        ``::TestOHD3119WarningsSusturmasi``.
        """
        import json as _json
        import os as _os
        import subprocess as _sp
        import sys as _sys

        betik = (
            "import json, warnings\n"
            "import hrma.app  # noqa: F401  (tüm motor modüllerini içe aktarır)\n"
            "ca = [str(f[:4]) for f in warnings.filters\n"
            "      if f[0] == 'ignore' and f[1] is None and f[2] is Warning\n"
            "      and f[3] is None]\n"
            "print(json.dumps(ca))\n"
        )
        ortam = dict(_os.environ, PYTHONDONTWRITEBYTECODE='1', HRMA_HEADLESS='1')
        cikti = _sp.run([_sys.executable, '-c', betik], cwd=str(ROOT), env=ortam,
                        capture_output=True, text=True, timeout=600)
        assert cikti.returncode == 0, cikti.stderr[-1000:]
        catch_all = _json.loads(cikti.stdout.strip().splitlines()[-1])
        assert not catch_all, (
            f'{len(catch_all)} adet süreç geneli ignore filtresi var — '
            'bir ÜRÜN modülü filterwarnings("ignore") çağırıyor: '
            f'{catch_all}')

    def test_compliance_never_claims_conformity(self):
        from hrma.analysis.safety_analysis import SafetyAnalyzer
        comp = SafetyAnalyzer()._check_safety_compliance(
            {'acceptability': 'ACCEPTABLE', 'individual_risks': {}})
        for k in ('nfpa_compliance', 'osha_compliance', 'dot_compliance'):
            assert comp[k] == 'NOT_EVALUATED'

    def test_source_has_no_nan_coercion(self):
        import inspect

        import hrma.app as appmod
        src = inspect.getsource(appmod.sanitize_json_values)
        body = src[src.index('"""', src.index('"""') + 3) + 3:]
        assert not re.search(r'return\s+0\.0', body)
        assert '1e10' not in body


# ===========================================================================
# 4. Güvenlik kapıları
# ===========================================================================

class TestSecurityGates:
    @pytest.fixture
    def client(self):
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    def test_no_wildcard_cors(self):
        assert 'from flask_cors import CORS' not in _read('hrma/app.py')

    def test_cross_origin_state_change_rejected(self, client):
        r = client.post('/analyze_safety', json={'chamber_pressure': 20},
                        headers={'Origin': 'https://evil.example'})
        assert r.status_code == 403

    def test_stl_download_blocks_traversal(self, client):
        for bad in ('..\\..\\..\\Windows\\win.ini', '..%5cwindows%5cwin.ini'):
            assert client.get(f'/download/stl/{bad}').status_code in (400, 404)

    def test_request_body_is_bounded(self):
        from hrma.app import app
        assert app.config.get('MAX_CONTENT_LENGTH')

    def test_export_uses_safe_name(self):
        """İhracat modülleri ``safe_name``'i İÇE AKTARIYOR mu (AĞAÇTAN).

        SINIRI (ÖH defteri P13B4-12, orta): bu bekçi yalnız içe aktarma
        BAĞINI ve ad kapısına yapılan ÇAĞRININ varlığını arar.
        ``input_guard`` içindeki bir kapı sessizce sökülse de bu test YEŞİL
        kalır — çünkü hiçbir davranış ölçmez. Modülün DAVRANIŞINI
        :class:`TestInputGuardNumDavranisi` ve :class:`TestInputGuardUcDavranisi`
        sınar (P14M4-04). Bu test SİLİNMEZ: kablonun yerinde olduğunu ucuz
        biçimde söyler; ama "kapı çalışıyor" demez, "import satırı duruyor" der.

        SINIRIN İKİNCİ YARISI ARTIK KAPALI (ÖH Faz B-3 / C5, 2026-08-27):
        aşağıdaki iki dosyalık ELLE liste, kapsamın tamamı değildir —
        defterin cümlesi *"22 indirme noktasının hepsi app.py'de ve kapsam
        dışı"* idi. Kapsamın kendisini artık
        :class:`TestInputGuardCagriEnvanteri` AST ile TÜRETİR (elle liste
        yok): ürün ağacındaki her ``input_guard`` çağrısını sayar, gerilemeyi
        kırmızı yapar ve ``app.py`` uçlarındaki 0/66 kapsamı ölçülü tutar.
        Yani bu test hâlâ "import satırı duruyor" der; "kapı kaç yerde
        takılı" sorusunun cevabı o sınıftadır.
        """
        # ÖH D28 fix-28b: içe aktarım artık METİNLE değil AĞAÇLA ölçülür.
        # Kırılma (taban kaydı-12): D28 ihracat a1 (ac29bda7) merkeze DEĞER
        # kapılarını da bağlayınca satır çok adlı paranteze döndü
        #     from hrma.utils.input_guard import (
        #         finite_number, first_finite_positive, safe_name)
        # ve tek satırlık METİN eşitliği düştü. ÖLÇÜLDÜ: safe_name o anda da
        # hem içe aktarılıyor hem çağrılıyordu (step_export.py:522,
        # drawing_generator.py:618/808), yani kırmızı ürünü değil bekçinin
        # BİÇİME bağlılığını gösteriyordu. Ağaç, bağlanan ADI ölçer; içe
        # aktarmanın kaç satıra yayıldığı, kaç ad taşıdığı, hangi sırada
        # yazıldığı sonucu değiştirmez. Ölçü GEVŞEMEDİ: metin eşitliğinin
        # kabul ettiği her hâl ağaçta da kabul edilir, ağaç ayrıca takma adı
        # (``as``) ve modül biçimini de görür.
        for rel in ('hrma/export/step_export.py',
                    'hrma/export/drawing_generator.py'):
            agac = ast.parse(_read(rel))
            # TEK KAYNAK: üç içe aktarma biçimini de bilen ortak çözümleyici
            # (``_ig_yerel_adlar``) kullanılır; bu testin kendi kopyası yok.
            dogrudan, modul_adlari = _ig_yerel_adlar(agac)
            assert 'safe_name' in dogrudan.values() or modul_adlari, (
                f'{rel} hrma.utils.input_guard ad kapısını HİÇBİR biçimde '
                f'içe aktarmıyor (doğrudan adlar: {sorted(dogrudan)}, '
                f'modül adları: {sorted(modul_adlari)})')
            # ÖH D20 / P13B3... hayır: defter P13B4-12. Kalemin başlığı
            # "dosya safe_name'i import edip HİÇ ÇAĞIRMASA yeşil" idi. O
            # delik burada kapanıyor: içe aktarım YETMEZ, ÇAĞRI da olmalı.
            # ÖLÇÜLDÜ (once.json bölüm F): step_export 1 çağrı,
            # drawing_generator 2 çağrı.
            cagri = [c for c in _ig_cagrilari(agac, dogrudan, modul_adlari)
                     if c[1] in _IG_AD_KAPILARI]
            assert cagri, (
                f'{rel} input_guard ad kapısını İÇE AKTARIYOR ama hiç '
                'ÇAĞIRMIYOR — kablo takılı, kapı kapalı değil')


# ===========================================================================
# 4b. ÖH Faz B-1 #2 — input_guard.num/integer DAVRANIŞ bekçileri
#     Defter: P14M4-04 (yüksek) + P13B4-12 (orta)
# ===========================================================================

class TestInputGuardNumDavranisi:
    """``input_guard.num`` / ``integer`` sözleşmesinin DOĞRUDAN sınavı.

    Var olma sebebi (ÖH defteri **P14M4-04**, yüksek): P14 mutasyon
    taramasında ``input_guard.py:97``'deki ``isinstance(value, bool)`` reddi
    kaldırıldı ve **süitin hiçbir yerinde kırmızı çıkmadı** (361 test yeşil).
    Ölçüm o gün şunu gösterdi: ``num``/``integer`` deponun HİÇBİR testinde
    doğrudan çağrılmıyordu; ``input_guard`` yalnız ``safe_name`` /
    ``safe_arcname`` / ``is_safe_arcname`` için içe aktarılıyordu. Yani projenin
    tüm sayısal girdi savunmasının merkezî kapısı bekçisizdi.

    Bu sınıf o boşluğu kapatır: aşağıdaki her iddia bugünkü davranışı
    ÖLÇEREK yazıldı (ölçüm tarihi 2026-08-26, üretim kodu değişmeden).

    ÖN KOŞUL NOTU (P14 §3.2-b): P16'nın "``input_guard``'ı 22 uca yayma"
    planı bu sözleşmeyi 22 rotaya kopyalayacak. Yayma işleminin
    sözleşmeyi taşıdığını söyleyebilmek için önce sözleşmenin KENDİSİNİN
    makine tarafından yazılı olması gerekir — bu sınıf o ön koşuldur.
    """

    @staticmethod
    def _guard():
        from hrma.utils import input_guard
        return input_guard

    # -- bool deliği (P14M4-04'ün tam kendisi) ------------------------------

    def test_bool_sayi_degildir(self):
        """``True``/``False`` sayı alanına GİREMEZ.

        Python'da ``float(True) == 1.0`` olduğu için bool bir sayı alanına
        düştüğünde aralık kapıları onu göremez (1,0 s geçerli bir yanma
        süresidir). Tip reddi bu alanlarda TEK savunmadır.
        """
        g = self._guard()
        for deger in (True, False):
            with pytest.raises(g.InputError) as ex:
                g.num({'burn_time': deger}, 'burn_time', unit='s')
            mesaj = str(ex.value)
            assert 'burn_time' in mesaj, 'gerekçe alan adını söylemiyor'
            assert 'bool' in mesaj, ('gerekçe tipi söylemiyor — kullanıcı '
                                     'neyin yanlış olduğunu anlayamaz')

    def test_bool_reddi_integer_icin_de_gecerli(self):
        """``integer`` gövdesini ``num``'a devreder; bool reddi oraya da geçmeli."""
        g = self._guard()
        for deger in (True, False):
            with pytest.raises(g.InputError):
                g.integer({'n': deger}, 'n')

    def test_bool_disi_sayilar_gecer(self):
        """Bekçi yalnız bool'u kesmeli — gerçek sayılar sözleşmede kalır."""
        g = self._guard()
        assert g.num({'k': 1}, 'k') == 1.0
        assert g.num({'k': 1.0}, 'k') == 1.0
        assert g.num({'k': -3}, 'k') == -3.0
        assert isinstance(g.num({'k': 1}, 'k'), float)

    # -- sayı-dize kabulü / reddi -------------------------------------------

    def test_sayi_dizesi_kabul_edilir_ve_float_a_cevrilir(self):
        """Form alanları JSON'a dize olarak düşer; sözleşme onları kabul eder."""
        g = self._guard()
        assert g.num({'k': '12'}, 'k') == 12.0
        assert g.num({'k': ' 12 '}, 'k') == 12.0        # boşluk kırpılır
        assert g.num({'k': '1e3'}, 'k') == 1000.0       # bilimsel gösterim
        assert g.num({'k': '-0.5'}, 'k') == -0.5

    def test_sayi_olmayan_dize_reddedilir(self):
        """Sayıya çevrilemeyen dize sessizce 0 olmaz, hata olur."""
        g = self._guard()
        for kotu in ('abc', '0x10', '12,5', '1/2', '10 s'):
            with pytest.raises(g.InputError) as ex:
                g.num({'k': kotu}, 'k')
            assert 'k' in str(ex.value)

    def test_alt_tire_ayracli_dize_bugun_kabul_ediliyor(self):
        """ÖLÇÜM (onay değil): ``'1_000'`` bugün 1000,0 olarak geçiyor.

        Sebep ``float()``'ın Python 3.6+ rakam ayracı desteğidir; sözleşme
        bunu ayrıca elemez. Kusur olarak KAYDEDİLMEDİ (JSON sayıları bu
        biçimde gelmez, yalnız elle yazılmış dize gelirse geçer) ama davranış
        burada YAZILI dursun: sözleşme sıkılaştırılırsa bu bekçi kırmızıya
        döner ve o zaman SİLİNMEZ, sıkı biçime GÜNCELLENİR.
        """
        g = self._guard()
        assert g.num({'k': '1_000'}, 'k') == 1000.0

    def test_sonsuz_ve_nan_reddedilir(self):
        """NaN/Inf sayı gibi görünür ama hesabı sessizce zehirler."""
        g = self._guard()
        for kotu in (float('nan'), float('inf'), float('-inf'),
                     'nan', 'inf', '-inf'):
            with pytest.raises(g.InputError) as ex:
                g.num({'k': kotu}, 'k')
            assert 'finite' in str(ex.value), (
                'sonluluk reddi başka bir dala düşmüş: %s' % ex.value)

    def test_sayi_disi_nesneler_reddedilir(self):
        """Liste/sözlük/karmaşık sayı sayı alanına giremez."""
        g = self._guard()
        for kotu in ([1], {'a': 1}, complex(1, 0), object()):
            with pytest.raises(g.InputError):
                g.num({'k': kotu}, 'k')

    # -- "verilmedi" ile 0 ayrımı (modülün ilan ettiği ilke) ----------------

    def test_sifir_varsayilana_dusmez(self):
        """``0`` geçerli bir değerdir; modülün kendi ilkesi bunu yazıyor.

        Eski davranış ``thrust=0`` girdisini sessizce 1000 N'a çeviriyordu.
        """
        g = self._guard()
        assert g.num({'k': 0}, 'k', default=1000) == 0.0
        assert g.num({'k': '0'}, 'k', default=1000) == 0.0
        assert g.num({'k': 0.0}, 'k', default=1000) == 0.0

    def test_yalniz_none_ve_bos_dize_varsayilana_duser(self):
        g = self._guard()
        assert g.num({'k': None}, 'k', default=7.5) == 7.5
        assert g.num({'k': ''}, 'k', default=7.5) == 7.5
        assert g.num({'k': '   '}, 'k', default=7.5) == 7.5
        assert g.num({}, 'k', default=7.5) == 7.5
        assert g.num({}, 'k') is None            # varsayılan yoksa None

    # -- aralık / zorunluluk gerekçeleri ------------------------------------

    def test_aralik_kapisi_alan_adini_ve_birimi_soyler(self):
        g = self._guard()
        with pytest.raises(g.InputError) as alt:
            g.num({'burn_time': 0.01}, 'burn_time', lo=0.1, hi=300, unit='s')
        assert 'burn_time' in str(alt.value) and '(s)' in str(alt.value)
        with pytest.raises(g.InputError) as ust:
            g.num({'burn_time': 1e4}, 'burn_time', lo=0.1, hi=300, unit='s')
        assert 'burn_time' in str(ust.value) and '(s)' in str(ust.value)
        # Sınırlar KAPSAYICI: tam sınır değeri geçer (sessiz kısaltma yok)
        assert g.num({'k': 0.1}, 'k', lo=0.1, hi=300) == 0.1
        assert g.num({'k': 300}, 'k', lo=0.1, hi=300) == 300.0

    def test_required_eksik_alani_adiyla_reddeder(self):
        g = self._guard()
        with pytest.raises(g.InputError) as ex:
            g.num({}, 'of_ratio', required=True)
        assert 'of_ratio' in str(ex.value) and 'required' in str(ex.value)

    def test_varsayilan_deger_araligi_denetlenmez_olculdu(self):
        """ÖLÇÜM (onay değil): ``default`` lo/hi kapısından GEÇMEZ.

        ``num({}, 'k', lo=10, default=5)`` bugün 5 döndürür — varsayılan,
        ilan edilen aralığın dışında olsa bile sınanmaz. Bu bir kullanıcı
        girdisi yolu değildir (varsayılanı çağıran kod yazar), o yüzden
        defterde kusur olarak açılmadı; ama sözleşmenin ölçülmüş sınırıdır.
        Sıkılaştırılırsa bu bekçi kırmızıya döner: o gün SİLİNMEZ, sıkı
        biçime güncellenir.
        """
        g = self._guard()
        assert g.num({}, 'k', lo=10, hi=20, default=5) == 5

    # -- integer sözleşmesi -------------------------------------------------

    def test_integer_kesirliyi_yuvarlamaz(self):
        """Kesirli değer sessizce yuvarlanmaz, reddedilir."""
        g = self._guard()
        with pytest.raises(g.InputError) as ex:
            g.integer({'n': 3.5}, 'n')
        assert 'whole number' in str(ex.value) and 'n' in str(ex.value)

    def test_integer_gercek_int_dondurur(self):
        """Dönüş tipi ``int`` olmalı — ``float`` dönerse indeksleme kırılır."""
        g = self._guard()
        for girdi in (3, 3.0, '3', '3.0'):
            sonuc = g.integer({'n': girdi}, 'n')
            assert sonuc == 3
            assert type(sonuc) is int, f'{girdi!r} için {type(sonuc).__name__} döndü'
        assert type(g.integer({}, 'n', default=7)) is int
        assert g.integer({}, 'n') is None

    def test_integer_aralik_kapisini_devralir(self):
        g = self._guard()
        with pytest.raises(g.InputError):
            g.integer({'n': 0}, 'n', lo=1, hi=64)
        with pytest.raises(g.InputError):
            g.integer({'n': 65}, 'n', lo=1, hi=64)
        assert g.integer({'n': 64}, 'n', lo=1, hi=64) == 64

    def test_hata_tipi_valueerror_soyundan(self):
        """``InputError`` ValueError'dan türemeli — rotalar 400'e çevirir."""
        g = self._guard()
        assert issubclass(g.InputError, ValueError)


class TestInputGuardUcDavranisi:
    """Aynı kapının ÜRÜN UCUNDAKİ davranışı (P14M4-04 §"kapı taşıyıcı").

    P14 raporunun ham ölçümü (``docs/scofield/raw/P14/M4-mut-04-uc.py``):

        ÜRETİM  : HTTP 400 {"error": "'burn_time' must be a number (got bool)"}
        MUTASYON: HTTP 200  thrust = 1000.0  mdot = 0.4428...  Pc = 20

    Defter başlığındaki "→ 200, burn_time = 1,0 s" MUTASYONUN ölçümüdür;
    üretim kodu bugün fail-closed'dır (2026-08-26'da yeniden ölçüldü, 400).
    Eksik olan tek şey bekçiydi — bu sınıf o bekçidir, bu yüzden xfail DEĞİL
    normal testtir: bugün yeşildir ve tip reddi sökülürse kırmızıya döner.
    """

    YUK = {
        'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
        'chamber_pressure': 20, 'of_ratio': 6.0, 'fuel_type': 'htpb',
        'oxidizer_type': 'n2o', 'l_star': 1.0, 'expansion_ratio': 4.0,
        'nozzle_type': 'conical', 'chamber_temperature': 3000,
        'include_plots': False,
    }
    BASLIKLAR = {'Host': '127.0.0.1:8080'}

    @pytest.fixture
    def client(self):
        from hrma.app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    def test_aralik_dogrulayicisi_bool_yanma_suresini_goremez(self):
        """Neden tip reddi TEK savunma: aralık kapısı ``True``'yu geçiriyor.

        ÖLÇÜLDÜ: ``motor_validator`` ``burn_time=True`` isteğine ``ok=True``
        diyor (``float(True)=1,0`` ve 1,0 s ∈ [0,1; 300]). Yani bu alanda
        aralık kapısının arkasında hiçbir şey yok; ``input_guard``'ın tip
        reddi kaldırılırsa uydurma bir yanma süresiyle tam motor tasarımı
        yayımlanır.
        """
        from hrma.app import motor_validator
        gecerli, mesajlar = motor_validator.validate_motor_data(
            dict(self.YUK, burn_time=True), 'hybrid')
        assert gecerli is True and not mesajlar, (
            'aralık kapısı bool yakalar hâle gelmiş: %s — bu İYİ haber, ama '
            'bu testin gerekçesi değişti: tip reddinin tek savunma olduğu '
            'iddiası artık doğru değil, docstring güncellenmeli' % mesajlar)

    def test_calculate_bool_yanma_suresini_400_ile_reddeder(self, client):
        """``/calculate`` + ``burn_time: true`` → 400 ve gerekçede ALAN ADI."""
        r = client.post('/calculate', json=dict(self.YUK, burn_time=True),
                        headers=self.BASLIKLAR)
        assert r.status_code == 400, (
            'bool yanma süresi 200 ile geçti — fail-open (P14M4-04): %s'
            % r.get_data(as_text=True)[:300])
        gerekce = json.dumps(r.get_json() or {}, ensure_ascii=False)
        assert 'burn_time' in gerekce, (
            'reddin gerekçesi hangi alanın hatalı olduğunu söylemiyor: %s'
            % gerekce[:300])

    def test_calculate_sonsuz_yanma_suresini_400_ile_reddeder(self, client):
        """Aynı kapının sonluluk dalı da uçta taşıyıcı olmalı."""
        r = client.post('/calculate',
                        json=dict(self.YUK, burn_time=float('inf')),
                        headers=self.BASLIKLAR)
        assert r.status_code == 400, r.get_data(as_text=True)[:300]
        assert 'burn_time' in json.dumps(r.get_json() or {}, ensure_ascii=False)


# ===========================================================================
# 4c. ÖH Faz B-3 / C5 — input_guard ÇAĞRI ENVANTERİ (AST ile TÜRETİLMİŞ)
#     Defter: P13B4-12'nin kalan gövdesi (elle liste + kapsam) · ÖK-20
# ===========================================================================

#: ``input_guard``'ın iki yarısı. DEĞER kapısı yarısı sayı/seçim/metin
#: alanlarını fail-closed süzer (kampanyanın ÖK-20 hedefi budur); AD
#: yarısı dosya/arşiv adı bileşenlerini temizler (yol kaçışı savunması).
_IG_MODUL = 'hrma.utils.input_guard'
_IG_DEGER_KAPILARI = ('num', 'integer', 'choice', 'text')
_IG_AD_KAPILARI = ('safe_name', 'safe_arcname', 'is_safe_arcname')


def _ig_yerel_adlar(agac):
    """Bir modülün ``input_guard``'ı hangi adlarla çağırabildiğini çıkarır.

    Üç içe aktarma biçiminin ÜÇÜ de sayılır (bekçinin kör noktası olmasın):
    ``from hrma.utils.input_guard import num`` · ``from hrma.utils import
    input_guard`` · ``import hrma.utils.input_guard as ig``. Ayrıca işlev
    gövdesindeki geç içe aktarmalar da görülür (``ast.walk`` tüm ağacı gezer;
    ``app.py`` bugün ``safe_name``'i iki yerde işlev içinde alıyor).
    """
    dogrudan, modul_adlari = {}, set()
    for n in ast.walk(agac):
        if isinstance(n, ast.ImportFrom):
            if n.module == _IG_MODUL:
                for a in n.names:
                    dogrudan[a.asname or a.name] = a.name
            elif n.module == 'hrma.utils':
                for a in n.names:
                    if a.name == 'input_guard':
                        modul_adlari.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name == _IG_MODUL:
                    modul_adlari.add(a.asname or a.name.split('.')[-1])
    return dogrudan, modul_adlari


def _ig_cagrilari(agac, dogrudan, modul_adlari):
    """``(satır, işlev_adı)`` çiftleri — ``input_guard``'a yapılan ÇAĞRILAR."""
    bulunan = []
    for n in ast.walk(agac):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name) and f.id in dogrudan:
            bulunan.append((n.lineno, dogrudan[f.id]))
        elif (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
              and f.value.id in modul_adlari):
            bulunan.append((n.lineno, f.attr))
    return bulunan


@lru_cache(maxsize=1)
def _ig_envanteri():
    """``hrma/**`` ağacındaki bütün ``input_guard`` çağrılarını AST ile türetir.

    Elle liste YOKTUR: hangi dosyanın kapıyı çağırdığı ağaçtan çıkar, o yüzden
    yeni bir dosya kapıyı çağırmaya başlarsa (ya da bırakırsa) envanter kendi
    kendine değişir ve aşağıdaki kilitler bunu söyler.

    SINIRI (dürüstlük notu): DOĞRUDAN çağrı sayılır. Bir rota kapıyı çağıran
    bir yardımcıyı çağırıyorsa bu envanterde GÖRÜNMEZ — geçişli erişim
    ölçülmez. Bu yüzden envanter bir ALT SINIRDIR.
    """
    kok = ROOT / 'hrma'
    envanter = []
    for py in sorted(kok.rglob('*.py')):
        if py.name == 'input_guard.py':      # kapının kendi tanımları
            continue
        try:
            agac = ast.parse(py.read_text(encoding='utf-8'))
        except SyntaxError:                  # ürün kodu derlenmiyorsa
            continue                         # başka bekçilerin işi
        dogrudan, modul_adlari = _ig_yerel_adlar(agac)
        if not dogrudan and not modul_adlari:
            continue
        rel = py.relative_to(ROOT).as_posix()
        for satir, islev in _ig_cagrilari(agac, dogrudan, modul_adlari):
            envanter.append((rel, satir, islev))
    return tuple(envanter)


def _ig_deger_cagrilari():
    return [k for k in _ig_envanteri() if k[2] in _IG_DEGER_KAPILARI]


def _ig_ad_cagrilari():
    return [k for k in _ig_envanteri() if k[2] in _IG_AD_KAPILARI]


class TestInputGuardCagriEnvanteri:
    """Kapının ÜRÜNDE KAÇ YERDE ÇAĞRILDIĞININ makine tarafından tutulan sicili.

    Var olma sebebi (ÖH defteri **P13B4-12**, orta — kalan gövde): yukarıdaki
    :meth:`TestSecurityGates.test_export_uses_safe_name` yalnız İKİ dosyanın
    import SATIRININ METNİNİ arar; :class:`TestInputGuardNumDavranisi` ise
    kapının davranışını sınar ama kapının KAÇ UÇTA takılı olduğunu sormaz.
    Aradaki boşluk defterin asıl cümlesiydi: *"22 indirme noktasının hepsi
    app.py'de ve kapsam dışı"*. Bu sınıf o boşluğu kapatır: envanteri elle
    listeden değil AST'den türetir ve GERİLEMEYİ kırmızıya çevirir.

    BUGÜNKÜ ÖLÇÜM (2026-09-01, ÖH D15 fix-3 / taban geçişi; 133 dosya
    tarandı; sayılar bu sınıfın KENDİ AST tarayıcısıyla alındı):

    ==========================================  =====
    DEĞER kapısı (``num``/``integer``/``choice``/``text``) ürün çağrısı   13
    ...``hrma/engines/hybrid_rocket_engine.py`` 760/761/762/887/1042/1534  6
    ...``hrma/utils/common_fixes.py`` 171/407/408/455/456/457/459          7
    AD kapısı (``safe_name``/``safe_arcname``/``is_safe_arcname``)        23
    ...``hrma/app.py`` 20 · ``export/drawing_generator.py`` 2 ·
       ``export/step_export.py`` 1
    ``hrma/app.py``'de DEĞER kapısı çağrısı                                0
    ``hrma/app.py`` rota sayısı / POST ucu / gövde okuyan POST ucu   96/73/66
    gövde okuyan POST uçlarından DEĞER kapısı çağıran                      0
    ==========================================  =====

    ÖNCEKİ TABAN (2026-08-27, P16 savcısının ölçümüyle birebir aynıydı —
    P16 §4.2-ADIM 3: *"DEGER-KAPISI yarisi: 3 → hepsi
    hybrid_rocket_engine.py 636/637/638; app.py'de num() cagrisi: 0"*, AD
    yarısı 20): DEĞER 3, AD 20, rota 94, 132 dosya.

    TABAN NEDEN YÜKSELDİ (ÖK-22: taban ASLA düşürülerek/gevşetilerek
    kırmızı kapatılmaz; kapsam BÜYÜDÜYSE aynı commit'te YÜKSELTİLİR):
    kapsamı büyüten üç dalga ölçüldü (``git blame``) —

    * ``df67bce`` (ÖH Z5S ara-commit, P10-A/P10-B) —
      ``hrma/utils/common_fixes.py``'a 7 ``num`` çağrısı girdi;
    * ``e68d165`` (ÖH D15 hibrit a3) — hibrit motorda 3 yeni kapı
      (``:887`` ``num``, ``:1042`` ``integer`` port_count, ``:1534``
      ``num``), defter P1B1-10/-11 onarımları;
    * ``8565ad3`` (2.6.27 31. parti) — itki üçlüsünün kapısı
      ``:760-762``'ye taşındı (eski ``:636-638``).

    AD yarısındaki 20 → 23 büyümesi ``export/drawing_generator.py``
    (``:582``, ``:702``) ve ``export/step_export.py`` (``:432``)
    dosyalarından geliyor; AD kilidi tek yönlü olduğu için 23 taban
    SIKILAŞTIRMADIR (kayıp yakalanır, kazanç engellenmez).

    HEDEF hâlâ UZAK: 13 < 22. ÖK-20/ADIM 3 kapsamı ``app.py``'nin gövde
    okuyan 66 POST ucuna taşımadan hedef karşılanmaz ve o iş bu dalganın
    işi DEĞİLDİR — burada yalnız ölçülen taban güncellenir.

    HEDEF (ÖK-20 / P16 ADIM 3'ün kabul ölçütü, **bu dalganın işi DEĞİL**):
    ``num``/``integer``/``choice`` ürün çağrısı **≥ 22** olmalı (§2.1'in 22
    fail-open ucu) ve bu ancak ÜRÜN genişletmesiyle olur — ÖK-20 sırası
    bağlayıcıdır: ADIM 1 (ham 500→422) → ADIM 2 (``ranges`` bağlanır) →
    ADIM 3 (kapı 22 uca takılır). Faz B ürün onarımı YAPMAZ; bu yüzden
    3 ile 22 arasındaki fark burada **xfail borç imiyle DEĞİL**, envanterin
    kilitlenmesiyle karşılanır: bugünkü kapsam kaybolamaz, genişleme ise
    tabanı YÜKSELTMEDEN sessizce geçemez.
    """

    # Ölçülen tabanlar — hepsi 2026-09-01 koşumundan, tahmin değil
    # (önceki taban 2026-08-27: DEĞER 3 / {hybrid: 3} / AD 20).
    # ÖH D22 / app-api a2 (P16B2-08 + P16B1-49): taban 13 -> 14 YÜKSELTİLDİ
    # (gevşetme DEĞİL — sınıfın kendi yönergesi uyarınca kapsam büyüdüğü
    # için AYNI commit'te ölçülen yeni değere çekildi, ÖK-22 korunur).
    # Yeni çağrı ``hrma/app.py`` ``calculate_liquid`` içindeki
    # ``tank_pressure`` kapısıdır (sonluluk + üst bant) ve app.py'deki İLK
    # gerçek ``input_guard`` DEĞER çağrısıdır. Ölçüm:
    # ``docs/scofield/raw/OH/D22/app-api/a2/once.json`` P16B1-49 —
    # ``/calculate``in 83 alanının 0'ı, katı/sıvı uçlarının 9'ar alanının
    # da 0'ı kapıdan geçiyordu (P13B4-12 hedefi 22 uç).
    # ÖH D23 / app-api a2 (P13B4-12 · ÖK-20 / P16 ADIM 3): taban 14 -> 50
    # YÜKSELTİLDİ ve HEDEF KARŞILANDI. Bu bir gevşetme DEĞİL, sınıfın kendi
    # yönergesinin uygulanmasıdır (kapsam büyüdüğü için AYNI commit'te
    # ölçülen yeni değere çekilir; ÖK-22 korunur). Ölçüm:
    # ``docs/scofield/raw/OH/D23/app-api/a2/{once,sonra}_p13b4_12.json``.
    #   DEĞER kapısı ürün çağrısı        14 -> 50  (``app.py`` 1 -> 37)
    #   gövde okuyan POST ucu / KAPILI   66 / 1 -> 66 / 22
    #   kapısız gövde ucu                65 -> 44
    # Davranış ölçümü (``{once,sonra}_supurme.json``, 22 uç × düşman değer
    # = 156 vaka): fail-open 2xx 46 -> 8, ham 5xx 4 -> 0, alanı ADIYLA anan
    # 4xx 48 -> 104.
    # ÖH D26 fix-25a (6 Eylül 2026): taban 50 -> 51 (``app.py`` 37 -> 38).
    # Yine sınıfın KENDİ yönergesinin uygulanmasıdır, gevşetme değildir:
    # kapsam BÜYÜDÜ ve taban ölçülen yeni değere çekildi (ÖK-22 yönü).
    # EKLENEN TEK ÇAĞRI ÖLÇÜLDÜ (AST envanteri, taban 7751531):
    #   ``hrma/app.py:3363  input_guard.num(data, _alan)``
    # ``e564fe5`` (ÖH D25 app-api a1, P16B1-49) koydu: ``/calculate``in
    # sayısal alanları artık TİP + SONLULUK kapısından geçiyor
    # (``_CALCULATE_TIP_KAPISI_ALANLARI`` üstünde dönen döngü), yani bool ve
    # sonsuz/NaN girdiler sessiz varsayılana düşmek yerine adıyla reddediliyor.
    # Alt taban (``>= TABAN_DEGER``) sökülmeyi, üst taban (``<=``) sessiz
    # büyümeyi yakalamaya devam eder.
    TABAN_DEGER = 51
    TABAN_DEGER_DOSYA = {'hrma/engines/hybrid_rocket_engine.py': 6,
                         'hrma/utils/common_fixes.py': 7,
                         'hrma/app.py': 38}
    TABAN_AD = 23
    TABAN_AD_DOSYALARI = {'hrma/app.py',
                          'hrma/export/step_export.py',
                          'hrma/export/drawing_generator.py'}
    HEDEF_DEGER = 22            # ÖK-20 / P16 ADIM 3 kabul ölçütü

    # -- envanter kilitleri --------------------------------------------------

    def test_deger_kapisi_envanteri_gerilemez(self):
        """DEĞER kapısı çağrı sayısı ölçülen tabanın ALTINA düşemez.

        Kilit iki yönlüdür, çünkü tek yönlü eşik bu kampanyada iki kez
        sessiz kaldı: sayı DÜŞERSE kapsam kayboluyor, YÜKSELİRSE taban
        güncellenmediği için yeni kapsam kilitsiz kalıyor. İkisi de bu
        satırlarda konuşur.
        """
        cagrilar = _ig_deger_cagrilari()
        yerler = ['%s:%d %s()' % k for k in cagrilar]
        assert len(cagrilar) >= self.TABAN_DEGER, (
            'input_guard DEĞER kapısı çağrısı %d\'e düştü (taban %d). Kapının '
            'takılı olduğu bir yer sökülmüş — sayı alanları yine sessiz '
            'varsayılana düşüyor olabilir (P13B4-12 / P14M4-04). Kalan: %s'
            % (len(cagrilar), self.TABAN_DEGER, yerler))
        assert len(cagrilar) <= self.TABAN_DEGER, (
            'input_guard DEĞER kapısı çağrısı %d oldu (taban %d) — bu İYİ '
            'haber ama sessiz kalamaz: ÖK-20/ADIM 3 kapsamı büyüdüyse bu '
            'sınıftaki TABAN_DEGER (ve TABAN_DEGER_DOSYA) AYNI commit\'te '
            'ölçülen yeni değere YÜKSELTİLİR, defterde P13B4-12 notu '
            'güncellenir. Taban ASLA düşürülerek/gevşetilerek kırmızı '
            'kapatılmaz (ÖK-22). Bugünkü envanter: %s'
            % (len(cagrilar), self.TABAN_DEGER, yerler))

    def test_deger_kapisi_cagri_yerleri_dosya_bazinda_kilitli(self):
        """Çağrılar YER değiştirerek de kaybolabilir: dosya dağılımı kilitli."""
        dagilim = {}
        for rel, _satir, _islev in _ig_deger_cagrilari():
            dagilim[rel] = dagilim.get(rel, 0) + 1
        for dosya, adet in self.TABAN_DEGER_DOSYA.items():
            assert dagilim.get(dosya, 0) >= adet, (
                '%s içindeki DEĞER kapısı çağrısı %d\'e düştü (taban %d). '
                'İtki üçlüsünün (thrust/burn_time/total_impulse) kapısı '
                'buradadır; sökülürse 0 girdisi yine 1000 N\'a döner. '
                'Bugünkü dağılım: %s'
                % (dosya, dagilim.get(dosya, 0), adet, dagilim))

    def test_ad_temizleme_kapsami_gerilemez(self):
        """AD kapısı yarısı (yol kaçışı savunması) tek yönlü kilitli.

        Burada üst sınır YOK: yeni bir dosya adı ``safe_name``'den geçmeye
        başlarsa bu iyileşmedir, bekçi engellemez. Kilit yalnız KAYBI
        yakalar. ``:199-202``'nin iki dosyalık ELLE listesi burada AST'den
        türetilmiş dosya kümesine dönüşür (P13B4-12'nin ikinci yarısı).
        """
        cagrilar = _ig_ad_cagrilari()
        dosyalar = {k[0] for k in cagrilar}
        assert len(cagrilar) >= self.TABAN_AD, (
            'input_guard AD kapısı çağrısı %d\'e düştü (taban %d) — dosya/'
            'arşiv adı bir yerde ham geçiyor olabilir (zip-slip / yol '
            'kaçışı). Bugünkü dosyalar: %s'
            % (len(cagrilar), self.TABAN_AD, sorted(dosyalar)))
        eksik = self.TABAN_AD_DOSYALARI - dosyalar
        assert not eksik, (
            '%s dosyaları input_guard\'ın ad kapısını artık ÇAĞIRMIYOR '
            '(import satırı hâlâ duruyor olabilir — :199-202 bunu göremez, '
            'bu bekçi görür). Bugünkü küme: %s'
            % (sorted(eksik), sorted(dosyalar)))

    # -- uç katmanı kapsamı (ÖK-20'nin ölçülen açığı) -----------------------

    @staticmethod
    def _app_uclari():
        """``app.py``'nin rotaları: ``(yollar, yöntemler, kapı_çağrıları,
        gövde_okuyor_mu)``."""
        agac = ast.parse((ROOT / 'hrma' / 'app.py').read_text(encoding='utf-8'))
        dogrudan, modul_adlari = _ig_yerel_adlar(agac)
        uclar = []
        for n in ast.walk(agac):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            yollar, yontemler = [], set()
            for d in n.decorator_list:
                if not (isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Attribute)
                        and d.func.attr == 'route'):
                    continue
                if d.args and isinstance(d.args[0], ast.Constant):
                    yollar.append(d.args[0].value)
                for kw in d.keywords:
                    if kw.arg == 'methods' and isinstance(
                            kw.value, (ast.List, ast.Tuple)):
                        for e in kw.value.elts:
                            if isinstance(e, ast.Constant):
                                yontemler.add(e.value)
            if not yollar:
                continue
            kapilar = [c for c in _ig_cagrilari(n, dogrudan, modul_adlari)
                       if c[1] in _IG_DEGER_KAPILARI]
            govde = any(
                isinstance(m, ast.Attribute)
                and m.attr in ('get_json', 'json', 'form', 'args')
                and isinstance(m.value, ast.Name) and m.value.id == 'request'
                for m in ast.walk(n))
            uclar.append((yollar, yontemler or {'GET'}, kapilar, govde))
        return uclar

    def test_app_py_kapisiz_govde_ucu_sayisi_buyumez(self):
        """İstek gövdesi okuyup DEĞER kapısı çağırmayan uç sayısı ARTAMAZ.

        ÖLÇÜLDÜ (2026-09-01, ÖH D15 fix-3): ``app.py``'de 96 rota (27 Ağu
        ölçümünde 94), 73 POST ucu, bunların 66'sı
        ``request.get_json``/``form``/``args`` ile istek gövdesi okuyor ve
        **66'sının hiçbiri** ``input_guard``'ın değer kapısını çağırmıyor.
        Yani kapının uç katmanındaki kapsamı bugün **0/66** — iki yeni rota
        gövde okuyan POST ucu DEĞİL, o yüzden aşağıdaki 66 tabanı
        DEĞİŞMEDİ (yükseltilmedi de: taban bir TAVAN'dır, büyütmek
        gevşetme olurdu).

        Bu bir BEYAN değil kilittir: yeni bir gövde okuyan uç kapısız
        eklenirse sayı 67 olur ve bu bekçi kırmızıya döner. ÖK-20/ADIM 3
        uygulandığında sayı DÜŞECEK; o gün bu satırdaki taban aynı commit'te
        ölçülen yeni değere İNDİRİLİR (kapsam kilidi
        :meth:`test_deger_kapisi_envanteri_gerilemez` üzerinden zaten
        yükselecektir).
        """
        uclar = self._app_uclari()
        post = [u for u in uclar if 'POST' in u[1]]
        govde = [u for u in post if u[3]]
        kapisiz = [u for u in govde if not u[2]]
        # ÖH D23 / app-api a2 (P13B4-12): ÖK-20/ADIM 3 uygulandı, sayı
        # DÜŞTÜ — bu satırın kendi yönergesi uyarınca taban aynı commit'te
        # ölçülen yeni değere İNDİRİLDİ (66 -> 44; tavan gevşetilmez).
        assert len(kapisiz) <= 44, (
            'gövde okuyan ama input_guard değer kapısı çağırmayan POST ucu '
            '%d oldu (ölçülen taban 44). Yeni uç kapısız eklenmiş — 22 fail-'
            'open ucun listesi büyüyor (ÖK-20). Kapısız uçlar: %s'
            % (len(kapisiz), sorted(y for u in kapisiz for y in u[0])))
        # Ölçümün kendisi de kilitli: sayı çöküyorsa tarayıcı bozulmuştur.
        assert len(post) >= 60, (
            'app.py POST ucu %d\'e düştü (2026-08-27 ölçümü 73) — ya rotalar '
            'sökülmüş ya bu tarayıcı kör kalmış' % len(post))

    def test_uc_kapsami_hedefi_karsilandi(self):
        """Hedef (≥22) KARŞILANDI — bekçi artık iddiayı korur.

        ÖH D23 / app-api a2, defter **P13B4-12** · ÖK-20 / P16 ADIM 3. Eski
        hâli ``n < HEDEF_DEGER`` diyordu ve kusuru KAYDEDİYORDU; kendi
        yönergesi "kapsam hedefe ulaşınca bu bekçiyi 'kapsam hedefte'
        iddiasına ÇEVİRİN (silmeyin)" idi. Çevrildiği koşum: DEĞER kapısı
        ürün çağrısı 50, ``app.py``'de 37, gövde okuyan 66 POST ucundan
        22'si kapılı (taban 1). Yön DEĞİŞTİ: bundan sonra kapsamın hedefin
        ALTINA düşmesi kırmızıdır.
        """
        n = len(_ig_deger_cagrilari())
        assert n >= self.HEDEF_DEGER, (
            'DEĞER kapısı çağrısı %d < hedef %d — ÖK-20/ADIM 3 kapsamı '
            'SÖKÜLMÜŞ. 22 fail-open ucun kapısı geri alınamaz; kapıyı '
            'kaldıran değişiklik defterde P13B4-12 ile birlikte '
            'gerekçelendirilmeden geçemez.' % (n, self.HEDEF_DEGER))

    def test_uc_katmani_kapsami_gerilemez(self):
        """Gövde okuyan POST uçlarının KAÇI kapılı — alt sınır kilidi.

        Çağrı sayısı tek başına yetmez: 50 çağrının hepsi tek uçta toplanmış
        olabilirdi. Bu kilit kapsamın UÇ eksenini tutar (ölçüldü: 22/66).
        """
        uclar = self._app_uclari()
        govde = [u for u in uclar if 'POST' in u[1] and u[3]]
        kapili = [u for u in govde if u[2]]
        assert len(kapili) >= 22, (
            'DEĞER kapısı çağıran gövde-POST ucu %d\'e düştü (ölçülen taban '
            '22/%d). Kapı bir uçtan sökülmüş.' % (len(kapili), len(govde)))

    # -- tarayıcının kendi bekçisi (envanter kilidi totolojiye düşmesin) ----

    def test_tarayici_uc_ice_aktarma_bicimini_de_gorur(self):
        """Envanteri türeten tarayıcı KÖR olursa bütün kilitler boşa çıkar.

        Bu yüzden tarayıcı sentetik kaynak üzerinde sınanır: üç içe aktarma
        biçimi + işlev içi geç içe aktarma + takma ad. Biri görülmezse
        yukarıdaki sayılar "0 çağrı" demeye başlar ve alt sınır kilitleri
        yanlış sebeple kırmızı olur (ya da yeni kapsam sayılmaz).
        """
        ornek = (
            'from hrma.utils.input_guard import num, integer as tamsayi\n'
            'from hrma.utils import input_guard\n'
            'import hrma.utils.input_guard as ig\n'
            'def f(d):\n'
            '    from hrma.utils.input_guard import safe_name\n'
            '    a = num(d, "x")\n'
            '    b = tamsayi(d, "y")\n'
            '    c = input_guard.choice(d, "z", ["a"])\n'
            '    e = ig.text(d, "t")\n'
            '    return safe_name(a), b, c, e\n')
        agac = ast.parse(ornek)
        dogrudan, modul_adlari = _ig_yerel_adlar(agac)
        islevler = sorted(i for _s, i in _ig_cagrilari(
            agac, dogrudan, modul_adlari))
        assert islevler == ['choice', 'integer', 'num', 'safe_name', 'text'], (
            'tarayıcı bir çağrı biçimini kaçırıyor: %s' % islevler)
        # Ve gerçek ağaçta boş dönmediği de kilitli (dosya yolu değişmiş,
        # kök yanlış çözülmüş, glob kırılmış olabilir).
        assert _ig_envanteri(), 'envanter BOŞ döndü — tarayıcı ürün ağacını ' \
                                'bulamıyor, bütün kilitler totolojik'


# ===========================================================================
# 5. D-track — uyarı sözleşmesi eksiksiz
# ===========================================================================

class TestWarningContract:
    @staticmethod
    def _is_warning_code(node):
        """İlk argüman geçerli bir uyarı kodu mu?

        İki biçim geçerlidir:
          _w('warn.x.y', ...)
          _w('warn.x.ox' if stream == 'ox' else 'warn.x.fuel', ...)
        İkincisi ox/fuel gibi ikiz kodlar için kullanılıyor ve DOĞRUDUR;
        koşullu ifadenin İKİ dalı da kod olmak zorundadır.
        """
        if isinstance(node, ast.Constant):
            return isinstance(node.value, str) and node.value.startswith('warn.')
        if isinstance(node, ast.IfExp):
            return (TestWarningContract._is_warning_code(node.body)
                    and TestWarningContract._is_warning_code(node.orelse))
        return False

    def test_no_raw_warnings_left_in_engines(self):
        """Motor modüllerinde ham metin uyarı kalmamalı."""
        raw = []
        for path in (ROOT / 'hrma' / 'engines').glob('*.py'):
            for n in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if not isinstance(n, ast.Call):
                    continue
                fn = getattr(n.func, 'attr', None) or getattr(n.func, 'id', None)
                if fn not in ('_w', '_warn', '_mk_warning') or not n.args:
                    continue
                if not self._is_warning_code(n.args[0]):
                    raw.append(f'{path.name}:{n.lineno}')
        assert not raw, f'ham uyarı kalmış: {raw}'

    def test_every_engine_code_translated(self):
        """Her motor kodunun EN+TR karşılığı olmalı — ZİNCİR BORCU hariç.

        ÖH D33 · motorlar a1 (OH-UC-05) — BEKÇİ ÇEVRİLDİ, GEVŞETİLMEDİ.
        Bu düğüm ``tests/test_engine_warning_i18n.py::
        test_every_engine_code_has_translation`` ile AYNI sözleşmeyi ölçer;
        tek farkı, o dosyanın 2026'da kazandığı ZİNCİR BORCU imini
        tanımamasıydı. Borç bir gevşetme değildir ve KAZANILIR: koda
        ``fallback`` İngilizce metni koyma şartı ayrı bir bekçiyle
        (``test_zincir_borcu_kodlari_ingilizce_yedek_tasiyor``) kilitli,
        anahtar geldiği gün kodun listeden ÇIKMASI da öyle
        (``test_zincir_borcu_odendiyse_liste_temizlenir``). İki bekçinin
        AYNI kuralı farklı biçimde ölçmesi, motor kodu ile i18n anahtarının
        ayrı dalgalara düştüğü her seferde bu düğümün haksız yere kırmızı
        yanması demekti; küme artık TEK KAYNAKTAN okunuyor (Doktrin 4).

        Kapsam kaybı YOK: borç listesi boşsa bu düğüm eskisiyle bit-aynı
        davranır.
        """
        from tests.test_engine_warning_i18n import ZINCIR_BORCU
        codes = set()
        for path in (ROOT / 'hrma' / 'engines').glob('*.py'):
            codes |= set(re.findall(r"'(warn\.[a-z0-9_.]+)'",
                                    path.read_text(encoding='utf-8')))
        codes -= set(ZINCIR_BORCU)
        js = _read('hrma/static/js/i18n_common.js')
        en = set(re.findall(r"'(warn\.[a-z0-9_.]+)'\s*:",
                            js[js.index('        en: {'):js.index('        tr: {')]))
        tr = set(re.findall(r"'(warn\.[a-z0-9_.]+)'\s*:",
                            js[js.index('        tr: {'):]))
        assert not (codes - en), f'EN çevirisi eksik: {sorted(codes - en)}'
        assert not (codes - tr), f'TR çevirisi eksik: {sorted(codes - tr)}'

    def test_frontend_consumers_translate_recursively(self):
        """İç içe uyarı kayıtları da çevrilmeli ([object Object] regresyonu)."""
        for rel in ('hrma/static/js/analysis_dock.js',
                    'hrma/templates/solid.html',
                    'hrma/static/js/app.js',
                    'hrma/templates/liquid.html'):
            src = _read(rel)
            assert ('warnText' in src or 'warnToText' in src
                    or 'localizeWarning' in src), f'{rel}: çevirici yok'


# ===========================================================================
# 6. Dürüstlük — uydurma çıktı kalmamalı
# ===========================================================================

class TestOutputHonesty:
    def test_stl_export_is_fail_closed(self):
        import ast as _ast
        import inspect

        import hrma.app as appmod
        src = inspect.getsource(appmod.export_stl)
        tree = _ast.parse(src).body[0]
        body = tree.body[1:] if (tree.body and isinstance(tree.body[0], _ast.Expr)) else tree.body
        called = {n.func.id for n in _ast.walk(_ast.Module(body=body, type_ignores=[]))
                  if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)}
        assert 'generate_basic_stl_content' not in called
        assert 'generate_fallback_cad_geometry' not in called

    def test_tank_checklist_labels_template_fields(self):
        src = _read('hrma/export/cad_export.py')
        assert 'manufacturing_checklist_TEMPLATE.json' in src
        assert "'source': 'template'" in src

    def test_tank_material_comes_from_database(self):
        """Tank dayanımı ve yoğunluğu satır içi sabit olmamalı.

        AST ile bakılır: aynı metin AÇIKLAMA YORUMUNDA geçebilir (düzeltmenin
        neden yapıldığını anlatan not), o yorum bir regresyon değildir.
        Aranan şey gerçek bir ATAMA ifadesidir.
        """
        src = _read('hrma/engines/liquid_rocket_engine.py')
        assert 'get_material_safe' in src, 'malzeme veritabanından okunmuyor'

        bad = []
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Assign):
                continue
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if not (names & {'material_strength', 'material_density',
                             'fuel_material_strength', 'fuel_material_density'}):
                continue
            # Sabit sayı ataması = satır içi malzeme özelliği (yasak).
            if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, (int, float)):
                bad.append(f'{sorted(names)} = {node.value.value} '
                           f'(satır {node.lineno})')
        assert not bad, f'satır içi malzeme sabiti kalmış: {bad}'


# ===========================================================================
# v2.6.25 — saha düzeltmesi kapıları
# ===========================================================================

class TestFieldFixV2625:
    """v2.6.2'yi kullanılamaz yapan sınıftan hataları kilitler."""

    def test_cors_filter_has_no_hardcoded_port_list(self):
        """Süzgeç sabit port listesine geri dönmemeli.

        v2.6.2'de ``_ALLOWED_HOSTS`` içinde '127.0.0.1:8080' gibi sabitler
        vardı; başlatıcı 8081'e düşünce uygulama kendi API'sinden 403 aldı ve
        hiçbir motor tipi hesap yapamadı. Kapı: kaynakta port taşıyan sabit
        köken kalmasın.
        """
        src = _read('hrma/app.py')
        assert '_ALLOWED_HOSTS' not in src, (
            'sabit köken listesi geri gelmiş — port değişince uygulama '
            'kendi kendini 403 ile reddeder')
        assert re.search(r'def _is_loopback', src), (
            'geri döngü denetimi yok; köken süzgeci porta bağımlı olmuş olabilir')

    def test_launcher_and_runner_share_the_same_port_range(self):
        """Port aralığı iki dosyada da AYNI olmalı (ayrışma bu hatayı doğurdu)."""
        launcher = _read('packaging/launcher.py')
        runner = _read('hrma/run.py')
        assert 'range(8080, 8091)' in launcher, 'launcher port aralığı değişmiş'
        assert 'range(8080, 8091)' in runner, (
            'hrma/run.py başlatıcının port aralığını paylaşmıyor — '
            '8080 meşgulken çöker')
        assert 'port=8080' not in runner, 'run.py içinde sabit 8080 kalmış'

    def test_release_notes_are_bilingual_with_markers(self):
        """Güncelleme penceresi arayüz dilini izleyebilsin diye iki dilli im.

        Notlar tek dilde yayımlanınca Türkçe arayüzde soru Türkçe, sürüm notu
        İngilizce çıkıyordu (Berke'nin saha bildirimi, 2026-07-27).
        """
        import hrma
        notlar = _read('packaging/release_notes_v%s.md' % hrma.__version__)
        for dil in ('en', 'tr'):
            assert '<!--HRMA-LANG:%s-->' % dil in notlar, (
                '%s dil imi yok — güncelleme penceresi tek dil gösterir' % dil)
        # İmlerin arası gerçekten o dilde olmalı (blokların karışmaması)
        parcalar = re.split(r'<!--HRMA-LANG:(\w+)-->', notlar)
        bolum = {parcalar[i]: parcalar[i + 1] for i in range(1, len(parcalar), 2)}
        assert not re.search(r'[çğıİöşüÇĞÖŞÜ]', bolum['en']), (
            'İngilizce bölümde Türkçe karakter var — bloklar karışmış')
        assert re.search(r'[çğıİöşüÇĞÖŞÜ]', bolum['tr']), (
            'Türkçe bölüm Türkçe karakter içermiyor — çeviri yapılmamış olabilir')

    def test_update_modal_picks_language_section(self):
        """İstemci tarafı imleri ayıklayan işlevi taşımalı."""
        src = _read('hrma/static/js/update_check.js')
        assert 'pickLanguageSection' in src, (
            'güncelleme penceresi dil ayıklama işlevini kaybetmiş')
        assert 'HRMA-LANG' in src, 'dil imi deseni yok'

    def test_bundle_icon_is_full_bleed(self):
        """macOS 26 (Tahoe) bundle simgesine kendi karo maskesini uygular.

        Sanat eserinin kendi yuvarlatılmış karosunu çizmesi ve tuvali
        doldurmaması "karo içinde karo" görüntüsü üretiyordu (uygulama
        KAPALIYKEN). Kapı: bundle simgesi tam taşma kalsın.
        """
        from PIL import Image
        png = ROOT / 'packaging' / 'icon_1024_fullbleed.png'
        assert png.is_file(), (
            'tam taşma simge kaynağı yok — packaging/make_icons.py çalıştırın')
        im = Image.open(png).convert('RGBA')
        kutu = im.split()[3].getbbox()
        assert kutu == (0, 0, im.width, im.height), (
            'bundle simgesi tuvali doldurmuyor (alfa kutusu %s); Tahoe bunu '
            'kendi gri karosunun içine gömer' % (kutu,))

    def test_release_gate_script_exists_and_is_wired(self):
        """Yayın betiği kapıyı çağırmadan release oluşturmamalı."""
        assert (ROOT / 'packaging' / 'release_gate.sh').is_file(), (
            'yayın kapısı betiği yok')
        publish = _read('packaging/publish_release.sh')
        assert 'release_gate.sh' in publish, (
            'publish_release.sh kapıyı çağırmıyor — v2.6.2 kırmızı CI ile '
            'bu yüzden yayınlandı')
        # Sıra denetimi YORUMLARI saymaz: betiğin baş açıklaması hem kapıdan
        # hem 'gh release create'ten söz ediyor; ham metinde arama yapmak
        # açıklamayı çalışan kod sanar (bu testin ilk hâli buna takıldı).
        kod = '\n'.join(satir for satir in publish.split('\n')
                        if not satir.lstrip().startswith('#'))
        assert 'gh release create' in kod, 'yayın çağrısı bulunamadı'
        assert kod.index('release_gate.sh') < kod.index('gh release create'), (
            'kapı, release oluşturulduktan SONRA çalışıyor')

    def test_no_icloud_conflict_copies_in_source(self):
        """iCloud çakışma kopyaları kaynak ağacında kalmamalı.

        Proje iCloud Masaüstü içinde durduğu için servis zaman zaman
        "dosya 2.py" biçiminde çakışma kopyaları üretiyor. Bunlar git'te
        izlenmez ama derleme betikleri dizinleri OLDUĞU GİBİ kopyaladığından
        kurulum paketine girerler. 2026-07-27'de pakete iki bayat kopya
        girmişti: 'combustion_analysis 2.py' (16 saat eski) ve
        'nozzle_design 2.py' (15 gün eski, gerçek dosyanın yarısı boyutunda).

        İçe aktarılamazlar (adlarında boşluk var), ama pakette bulunmaları
        kafa karıştırır ve bir sonraki geliştiricinin yanlış dosyayı
        düzenlemesine yol açar.
        """
        desen = re.compile(r' \d+\.(py|js|json|md|html|tex)$')
        bulunan = []
        for klasor in ('hrma', 'tests', 'docs'):
            for yol in (ROOT / klasor).rglob('*'):
                if yol.is_file() and desen.search(yol.name):
                    bulunan.append(str(yol.relative_to(ROOT)))
        assert not bulunan, (
            'iCloud çakışma kopyaları kaynak ağacında: %s' % bulunan[:10])

    def test_ci_check_cannot_be_skipped_in_gate(self):
        """Kapıda CI kontrolü atlanabilir OLMAMALI.

        v2.6.25 yayınında `HIZLI=1` hem yerel tam takımı hem CI kontrolünü
        atlıyordu; ikisi aynı bayrağın altındaydı. Oysa maliyetleri taban
        tabana zıt: tam takım yerelde 20-40 dakika, CI kontrolü tek bir API
        çağrısı. Aynı bayrağa bağlamak, "hızlı geçeyim" diyen kişinin farkında
        olmadan projenin EN GÜÇLÜ kanıtını (temiz makinede yeşil takım)
        atlamasına yol açar — v2.6.2'yi yayınlayan hatanın ta kendisi.

        O yayında CI elle teyit edildi; bir dahakine kimse teyit etmeyebilir.

        v2.6.26 güncellemesi: bölümler eskiden '3/5' gibi sabit sayaçlarla
        aranıyordu; kapıya yeni bir bölüm eklenince (6/6 macOS imzası) sayaç
        kaydı ve test kapının İÇERİĞİNE değil NUMARASINA kırılmış oldu.
        Bölümler artık ``baslik "..."`` çağrılarının BAŞLIK METNİYLE bulunur;
        kapı sayısı kaç olursa olsun denetim aynı kalır.
        """
        src = _read('packaging/release_gate.sh')

        def _kod(metin):
            """Yorum satırlarını eler — açıklama metni kod sayılmamalı.

            Bu adımın NEDEN atlanamaz olduğunu anlatan yorum doğal olarak
            'HIZLI' kelimesini içerir; ham metinde arama yapmak o açıklamayı
            çalışan kod sanar.
            """
            return '\n'.join(s for s in metin.split('\n')
                             if not s.lstrip().startswith('#'))

        def _bolum(baslik_parcasi):
            """Başlığı verilen bölümün gövdesi (bir sonraki bölüme kadar)."""
            parcalar = re.split(r'baslik\s+"([^"]*)"', src)
            basliklar = parcalar[1::2]
            eslesen = [i for i, b in enumerate(basliklar)
                       if baslik_parcasi in b]
            assert len(eslesen) == 1, (
                "kapıda '%s' başlıklı TEK bölüm beklenirdi, bulunan: %s"
                % (baslik_parcasi, [basliklar[i] for i in eslesen]))
            return parcalar[2 + 2 * eslesen[0]]

        ci_bolumu = _kod(_bolum('GitHub Actions'))
        for bayrak in ('HIZLI', 'TAKIMI_ATLA', 'KAPIYI_ATLA'):
            assert bayrak not in ci_bolumu, (
                'CI kontrolü %s bayrağıyla atlanabilir hâle gelmiş — '
                'bu adım koşulsuz çalışmalı' % bayrak)
        # CI yeşil değilse kapı GERÇEKTEN kapanmalı: bölümde hem başarısızlık
        # kaydı hem gerçek kontrol çağrısı (gh run list) bulunmalı.
        assert 'basarisiz' in ci_bolumu, (
            'CI bölümü başarısızlık kaydetmiyor — kapı kapanamaz')
        assert 'gh run list' in ci_bolumu, (
            'CI bölümü gerçek CI durumunu sorgulamıyor')
        # Yerel tam takım ise atlanabilir olmalı (CI zaten koşturuyor)
        takim_bolumu = _kod(_bolum('Tam test takımı'))
        assert 'TAKIMI_ATLA' in takim_bolumu, (
            'yerel tam takımı atlama seçeneği kaybolmuş')
