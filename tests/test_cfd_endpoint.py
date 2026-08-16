"""POST /api/cfd/nozzle bekçileri (dalga B — v3 CFD kullanıcı yüzü).

KAPATILAN KUSUR
---------------
``hrma/cfd/`` (2B eksenel simetrik Euler çözücüsü, doğrulama merdiveniyle
birlikte) ve ``hrma/cfd/separation.py`` (Summerfield ayrılma köprüsü) depoda
çalışır hâldeydi ama HİÇBİR uç noktası onları çağırmıyordu: kullanıcı ne akış
alanını ne duvar basıncını ne de ayrılma hükmünü görebiliyordu. Bu uç zinciri
kapatır — yayımlanmış lüle konturu + motor gaz durumu → kararlı-hâl çözümü →
duvar basıncı → ayrılma hükmü → çizilebilir ham veri.

NE KİLİTLENİR
-------------
  1. GİRDİ SÖZLEŞMESİ: altı zorunlu alanın (kontur, P0, T0, gamma, R,
     P_ortam) her biri için eksiklikte 422 + ``missing_fields`` + hangi alanın
     NEDEN gerekli olduğu; bozuk kontur / bant dışı gamma / beyaz liste dışı
     çözünürlük 400 + ``field``. Hiçbir dalda uydurma varsayılan üretilmez.
     P_ortam bunların en kritiğidir: ayrılma ölçütü p_w < k·P_ortam ona göre
     tanımlıdır ve "deniz seviyesi" varsaymak sessiz bir uydurma olurdu.
  2. MUTLU YOL: gerçek örnekleyici konturuyla uçtan uca koşu → 200, sözleşme
     anahtarlarının tamamı, JSON-yerli tipler, kesin artan duvar ekseni.
  3. AYRILMA BLOĞU KÖPRÜDEN BİT-TUTARLI: aynı ızgarayla doğrudan yapılan
     ``assess_cfd_separation`` çağrısının çıktısı, ucun yanıtındaki blokla
     ANAHTAR ANAHTAR aynıdır. Uç ölçütü yeniden gerçeklemez, hükmü
     yumuşatmaz, alan eklemez.
  4. GÖLGELEME KAPISI: ``hrma.flow`` da ``assess_separation`` adını dışa
     verir. Ucun kullandığı fonksiyonun KİMLİĞİ denetlenir — yarı-1B sürüm
     sessizce yerine geçerse (imza ``(P0, Pa, gamma, …)``) bekçi kırmızıya
     döner.
  5. YAKINSAMAYAN KOŞU DÜRÜSTLÜĞÜ: oturmayan koşu 200 döner ama
     ``converged=False``, çözücünün kendi gerekçesi ve ayrılma hükmünde
     ``judgment_confidence='suspect'`` ile döner. Sonuç ne gizlenir ne de
     sağlam sunulur. Bu sözleşme artık AÇIK BİR BÜTÇEYE dayanıyor
     (``max_iterations``, §8): "oturmayan koşu" bir fizik kazasıyla değil,
     istemcinin kendi verdiği tavanla üretiliyor — böylece bekçi çözücünün
     o günkü yakınsama davranışına bağımlı DEĞİL.
  6. İNCELTME BEYANLI: kalıntı geçmişi ve alan bloğu tavanla inceltilir;
     inceltmenin gizleyebileceği sayılar (son/en küçük kalıntı, seçilen
     indeksler) yanıtta TAM olarak yayımlanır.
  7. ÇÖZÜNÜRLÜK BEYAZ LİSTE: serbest ızgara boyu alınmaz; her seviyenin
     (ni, nj) değeri ve ÖLÇÜLEN en kötü süresi yanıtta beyan edilir.
  8. İTERASYON BÜTÇESİ SÖZLEŞMESİ: ``max_iterations`` isteğe bağlıdır, bandı
     ``[CFD_MAX_ITERS_MIN, DEFAULT_MAX_ITERS]``, varsayılanı ÇÖZÜCÜNÜN kendi
     tavanıdır (uçta ikinci tanım yok). Etkin değer ve kaynağı (kullanıcı mı,
     varsayılan mı) yanıtta beyan edilir; bant dışı değer 400 alır.
  9. GİRİŞ KOŞULLANDIRMA BLOĞU BÜTÇE UYARISINA DÖNDÜ: uyarı artık giriş
     Mach'ına DEĞİL, ölçülmüş iterasyon maliyetine bakar; blok tetiklediği
     kuralı adıyla (``budget_advisory_reasons``) ve dayandığı ölçüm tablosunu
     (``measured_expectations``) yayımlar.

ÖLÇÜM YÖNTEMİ
-------------
Sunucuya port BAĞLANMAZ; Flask ``test_client`` kullanılır. Kontur GERÇEK
örnekleyiciden gelir (``hrma.engines.nozzle_design.sample_nozzle_inner_contour``
— motorların ``results['nozzle_contour']['points']`` bloğunu üreten aynı
fonksiyon), motor koşusunun kendisi atlanır: böylece bu bekçi motor
çözücüsünün o günkü durumuna bağımlı olmaz ama kontur uydurulmuş da olmaz.

Bekçi KUSUR KİLİTLEMEZ: hiçbir Mach/basınç/ayrılma konumu sabit sayıya
bağlanmamıştır. Kilitlenen şey sözleşme, iç tutarlılık ve beyan zinciridir.
Tek istisna, ölçülmüş bir olguyu kaydeden §6 bütçe-uyarısı bekçisidir; o da
bir SAYIYI değil, "uyarı ateşlendiğinde gerekçesi ve ölçümü de gelir" bağını
kilitler.

NÖBET DEĞİŞİMİ — ESKİ DAYANAK EMEKLİ (2026-08-16 akşamı)
---------------------------------------------------------
Bu dosyanın önceki sürümü, çözücünün ESKİ ses-altı giriş sınır koşulunun
ölçülmüş oturma sınırını dayanak alıyordu (düşük giriş Mach'ında kalıntının
~%99'u i=0,1,2 kolonlarında toplanıyor, plato oluşuyordu; eşik 0,15). O sınır
ARTIK YOK: giriş sınır koşulu KARAKTERİSTİK (Riemann değişmezi) biçime
çevrildi ve eski tablonun "YAKINSAMADI" satırlarının tamamı yakınsıyor.
Eski dayanağın iki bekçisi bu yüzden YALANCI olmuştu:
  * ``yanit_yakinsamayan`` fixture'ı (CR 11,1) artık YAKINSIYOR — yakınsamama
    sözleşmesini ölçen üç test sessizce kırmızıya düşmüştü;
  * "kötü koşullanmış vakada uyarı var" bekçisi, uyarı ateşlerken koşunun
    yakınsadığı bir vakayı ölçüyordu (uyarı yanlış ateşliyordu).
Yeni dayanak ÖLÇÜLDÜ (2026-08-16 akşamı, bu depo, M4 Max, numba, uç
üzerinden; tam tablo hrma/app.py: ``CFD_MEASURED_CONVERGENCE``):

    CR      M_giriş   coarse 60×12        standard 120×24
     1,77    0,359    YAKINSADI   2169    YAKINSADI   5805
     2,77    0,219    YAKINSADI   2083    YAKINSADI   4505
     4,00    0,150    YAKINSADI   2949    YAKINSADI   6774
     5,41    0,110    YAKINSADI   4131    YAKINSADI  13654
     7,08    0,084    YAKINSADI   6149    TAVANA DAYANDI (20000)
    11,11    0,053    YAKINSADI  13563    YAKINSADI   9345

Kalan risk giriş Mach'ı DEĞİL, yakınsama HIZIDIR (tek kırmızı satır tablonun
ORTASINDADIR — Mach'la monoton değil). Uç bunu gizlemez: ``inlet_conditioning``
bloğu koşu öncesi BÜTÇE beklentisini ölçülmüş dayanağıyla bildirir, koşuyu
ENGELLEMEZ ve hükmü çözücünün ``converged`` bayrağına bırakır.

§5'in "yakınsamayan koşu" vakası artık bir fizik kazasına değil, İSTEMCİNİN
KENDİ VERDİĞİ bütçeye dayanır (``max_iterations=600``; ölçüldü: aynı iyi
kontur 2083 iterasyonda oturuyor, 600'de kalıntı 1,22e-03 ile kesiliyor).
Böylece bekçi çözücünün o günkü yakınsama davranışı değiştiğinde yalancıya
dönmez — ölçtüğü şey BEYAN zinciridir.

MUTASYON DÜŞÜNCESİ — bağlama geri alınırsa hangi test kırılır
--------------------------------------------------------------
  * ``P_ambient_Pa`` eksikken sessiz bir varsayılan (ör. 101325) konursa ->
    test_p_ambient_eksikse_422_ve_gerekce + test_bos_govde_alti_zorunlu_alan
    (422 beklerken 200 gelir).
  * ``/api/cfd/nozzle`` route'u silinirse -> test_rota_kayitli VE 404
    üzerinden bu dosyadaki TÜM uç testleri.
  * Ayrılma köprüsü ``hrma.flow.assess_separation`` ile değiştirilirse ->
    test_ayrilma_koprusu_cfd_modulunden (kimlik) + test_ayrilma_blogu_bit_
    tutarli (imza uyuşmaz, TypeError).
  * Uç, blokta ayrılma alanlarını yeniden hesaplarsa/yuvarlarsa ->
    test_ayrilma_blogu_bit_tutarli.
  * Çözünürlük beyaz listesi kalkıp serbest sayı kabul edilirse ->
    test_cozunurluk_beyaz_liste_disi_400.
  * Yakınsamayan koşu 500'e çevrilir ya da converged=True'ya yuvarlanırsa ->
    test_yakinsamayan_kosu_200_ve_durust.
  * ``max_iterations`` bandı kaldırılır / girdi sessizce yutulursa ->
    TestIterasyonButcesi (bant dışı 400 + etkin değer yankısı).
  * Bütçe uyarısı HÜKME çevrilirse (koşuyu engellerse ya da converged'in
    yerine geçerse) -> test_uyari_hukum_yerine_gecmez.
  * Uyarı bayrağı gerekçe listesinden AYRIŞTIRILIRSA (ör. "her koşuda
    turuncu" davranışına dönülürse) -> test_uyari_bayragi_gerekceyle_ayrisamaz
    + test_iyi_kosullanmis_vakada_uyari_yok.
"""

import contextlib
import io
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

UC = '/api/cfd/nozzle'

#: Gaz durumu — roket sınıfı kalorik mükemmel gaz (tests/cfd/conftest.py ile
#: aynı ruh: γ ve R çözücüye çağırandan gelir, uydurma yedek yoktur).
GAZ = {'P0_Pa': 2.0e6, 'T0_K': 3000.0, 'gamma': 1.2, 'R_J_per_kgK': 350.0}

#: Taban vakanın ortam basıncı: 20 kPa (≈12 km). Eşik k·P_ortam = 8 kPa,
#: ölçülen en küçük duvar basıncının (≈44 kPa) belirgin ALTINDA — yani bu
#: vakada ayrılma beklenmez ve bekçi bunu sabit sayıya değil, bloğun kendi
#: ``wall_pressure_margin_min`` alanına karşı tutarlılıkla ölçer.
P_ORTAM_YUKSEK_IRTIFA = 20000.0

#: Ayrılma vakası: 500 kPa ortam. Eşik 200 kPa, ıraksak bölgedeki duvar
#: basıncı bunun altına düşer -> ayrılma öngörülür. Konum SABİTLENMEZ.
P_ORTAM_AYRILMALI = 500000.0

ZORUNLU_ALANLAR = ('nozzle_contour', 'P0_Pa', 'T0_K', 'gamma',
                   'R_J_per_kgK', 'P_ambient_Pa')


def _sessiz(fn, *args, **kwargs):
    """Motor/çözücü modülleri stdout'a bolca basıyor; testte sessize al."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*args, **kwargs)


def gercek_kontur(chamber_diameter=0.050, throat_diameter=0.030,
                  exit_diameter=0.075):
    """GERÇEK örnekleyiciden yayımlanmış kontur bloğu ({'points': [[z_m, r_m]]}).

    Motorların ``results['nozzle_contour']`` bloğuyla AYNI üreticidir
    (hrma.engines.nozzle_design.sample_nozzle_inner_contour, milimetre döner;
    üç motor da metreye çevirip yayımlar — hybrid_rocket_engine.py ~5688,
    liquid_rocket_engine.py ~5268, solid_rocket_engine.py ~9512). Kontur
    burada UYDURULMAZ, yalnız aynı birim çevirisi tekrarlanır.
    """
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    pts, _meta = _sessiz(sample_nozzle_inner_contour, {
        'chamber_diameter': chamber_diameter,
        'throat_diameter': throat_diameter,
        'exit_diameter': exit_diameter,
        'nozzle_angles': {'nozzle_type': 'conical',
                          'convergent_half_angle_deg': 30,
                          'divergent_half_angle_deg': 15},
    })
    return {
        'points': [[float(z) / 1000.0, float(r) / 1000.0] for z, r in pts],
        '_basis': 'sample_nozzle_inner_contour (test), [z_m, r_m] in metres',
    }


def govde(**degisiklik):
    """Tam geçerli istek gövdesi; anahtar ``None`` verilirse ÇIKARILIR."""
    g = dict(GAZ)
    g['nozzle_contour'] = gercek_kontur()
    g['P_ambient_Pa'] = P_ORTAM_YUKSEK_IRTIFA
    for k, v in degisiklik.items():
        if v is None:
            g.pop(k, None)
        else:
            g[k] = v
    return g


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def kontur_iyi():
    """İyi koşullanmış kontur (daralma oranı 2,78 — ölçümde yakınsayan bant)."""
    return gercek_kontur()


@pytest.fixture(scope='module')
def yanit_iyi(client, kontur_iyi):
    """Taban koşu: en kaba seviye, yüksek irtifa ortamı. ~1,6 s (ölçüldü)."""
    r = _sessiz(client.post, UC, json=govde(nozzle_contour=kontur_iyi))
    assert r.status_code == 200, r.get_data(as_text=True)[:800]
    return r.get_json()


@pytest.fixture(scope='module')
def yanit_ayrilmali(client, kontur_iyi):
    """Aynı akış alanı, yüksek ortam basıncı -> ayrılma öngörülür."""
    r = _sessiz(client.post, UC, json=govde(
        nozzle_contour=kontur_iyi, P_ambient_Pa=P_ORTAM_AYRILMALI))
    assert r.status_code == 200, r.get_data(as_text=True)[:800]
    return r.get_json()


@pytest.fixture(scope='module')
def yanit_vakum(client, kontur_iyi):
    """P_ortam = 0: ölçüt tanımsız, köprü hüküm VERMEZ (red dalı)."""
    r = _sessiz(client.post, UC, json=govde(
        nozzle_contour=kontur_iyi, P_ambient_Pa=0.0))
    assert r.status_code == 200, r.get_data(as_text=True)[:800]
    return r.get_json()


@pytest.fixture(scope='module')
def yerel_cozum(kontur_iyi, yanit_iyi):
    """Ucun DIŞINDA, aynı yardımcı + aynı çözücü varsayılanlarıyla çözüm.

    Bit-tutarlılık ölçümünün referansı budur. Izgara ucun kendi
    yardımcısıyla (``_cfd_build_grid``) kurulur — test ızgara kuralını
    yeniden TÜRETMEZ, aynı kuralı ÇAĞIRIR; ölçülen şey ayrılma bloğunun
    taşınması, ızgara aritmetiği değildir. Modül kapsamında BİR kez koşar
    (~1,1 s) ve üç ortam basıncı vakası aynı alanı paylaşır.
    """
    from hrma.app import _cfd_build_grid
    from hrma.cfd.steady import solve_steady_axisym

    grid, _z, _r = _cfd_build_grid(
        np.asarray(kontur_iyi['points'], dtype=float),
        yanit_iyi['cfd']['grid']['ni'], yanit_iyi['cfd']['grid']['nj'])
    return _sessiz(solve_steady_axisym, grid,
                   P0=GAZ['P0_Pa'], T0=GAZ['T0_K'], gamma=GAZ['gamma'],
                   R=GAZ['R_J_per_kgK'], Pb=None)


#: Bütçe kısıtlı vakanın tavanı. ÖLÇÜLDÜ (2026-08-16 akşamı, bu fixture
#: yazılırken, aynı iyi kontur + 'coarse'): serbest bütçeyle koşu 2083
#: iterasyonda oturuyor; tavan 500 → kalıntı 4,61e-03, 600 → 1,22e-03,
#: 1000 → 8,49e-06, 2000 → 5,33e-09 ve HEPSİ converged=False (2000'de kalıntı
#: toleransın altına inse bile debi/boğaz Mach bantları henüz OTURMAMIŞ).
#: 600 seçildi: bandın alt ucuna (500) yapışık değil ama oturmaya da uzak —
#: küçük bir çözücü hızlanması bu vakayı sessizce yeşile çeviremez.
BUTCE_KISITLI_TAVAN = 600


def _bant_konturu(carpan):
    """Ölçülen riskli bandın alt kenarına GÖRE kontur (sabit CR yazılmaz).

    Daralma oranı A_oda/A_boğaz = (D_oda/D_boğaz)² olduğundan istenen orana
    karşılık gelen oda çapı doğrudan çözülür; boğaz/çıkış çapı ve açılar
    ölçüm tablosunun kontur ailesiyle AYNI kalır.
    """
    from hrma.app import _cfd_budget_risk_bands
    bant = _cfd_budget_risk_bands('coarse')[0]
    return gercek_kontur(chamber_diameter=0.030 * math.sqrt(bant['cr_min']
                                                            * carpan))


@pytest.fixture(scope='module')
def yanit_bant_ici(client):
    """Bandın İÇİNDE bir kontur, serbest bütçe. ÖLÇÜLDÜ: CR 9,68 →
    11277 iterasyon (bütçenin %56'sı), converged=True, uyarı ATEŞLER
    (measured_slow_band). "Uyarı hüküm değildir"in canlı kanıtı. (~6,7 s)"""
    r = _sessiz(client.post, UC, json=govde(
        nozzle_contour=_bant_konturu(1.10)))
    assert r.status_code == 200, r.get_data(as_text=True)[:800]
    return r.get_json()


@pytest.fixture(scope='module')
def yanit_bant_disi(client):
    """Bandın DIŞINDA bir kontur, serbest bütçe. ÖLÇÜLDÜ: CR 6,81 →
    5561 iterasyon (%28), converged=True, uyarı ateşlemez. (~3,2 s)"""
    r = _sessiz(client.post, UC, json=govde(
        nozzle_contour=_bant_konturu(1.0 / 1.30)))
    assert r.status_code == 200, r.get_data(as_text=True)[:800]
    return r.get_json()


@pytest.fixture(scope='module')
def yanit_yakinsamayan(client, kontur_iyi):
    """AÇIK BÜTÇEYLE oturmayan koşu: iyi kontur + ``max_iterations``=600.

    NÖBET DEĞİŞİMİ (2026-08-16 akşamı): bu fixture eskiden bir FİZİK KAZASINA
    dayanıyordu (daralma oranı 11,1 — o günün çözücüsünde oturmayan vaka).
    Çözücünün giriş sınır koşulu karakteristik biçime çevrilince o vaka
    yakınsamaya başladı ve fixture'a bağlı üç test sessizce kırmızıya düştü:
    çözücünün DÜZELMESİ bekçiyi yalancı yapmıştı.

    Yeni vaka bir kaza değil, İSTEMCİNİN AÇIK KARARIDIR: aynı iyi kontur,
    ama 600 iterasyonluk bütçe (ölçüm BUTCE_KISITLI_TAVAN'da). Ölçülen:
    converged=False, iterations=600, kalıntı 1,22e-03, ayrılma hükmü
    'suspect'. Sözleşme aynı kaldı (200 + converged=False + suspect); yalnız
    onu üreten sebep artık çözücünün o günkü davranışından BAĞIMSIZ. (~0,4 s)
    """
    r = _sessiz(client.post, UC, json=govde(
        nozzle_contour=kontur_iyi, max_iterations=BUTCE_KISITLI_TAVAN))
    assert r.status_code == 200, r.get_data(as_text=True)[:800]
    return r.get_json()


# ---------------------------------------------------------------------------
# §1 — GİRDİ SÖZLEŞMESİ: eksik alan 422, bozuk değer 400
# ---------------------------------------------------------------------------

class TestZorunluAlanlar:
    def test_rota_kayitli(self):
        """Uç gerçekten bağlı mı (route silinirse tüm dosya 404'e düşer)."""
        from hrma.app import app
        kurallar = {str(r.rule) for r in app.url_map.iter_rules()}
        assert UC in kurallar

    def test_bos_govde_alti_zorunlu_alan(self, client):
        r = client.post(UC, json={})
        assert r.status_code == 422, r.get_data(as_text=True)[:500]
        j = r.get_json()
        assert j['error'] == 'incomplete_cfd_nozzle_input'
        assert set(j['missing_fields']) == set(ZORUNLU_ALANLAR)
        # Her eksik alan için GEREKÇE gelmeli (panel bunu basacak).
        for alan in ZORUNLU_ALANLAR:
            assert alan in j['field_reasons']
            assert len(j['field_reasons'][alan]) > 40, alan

    @pytest.mark.parametrize('alan', ZORUNLU_ALANLAR)
    def test_tek_alan_eksik_422(self, client, alan):
        r = client.post(UC, json=govde(**{alan: None}))
        assert r.status_code == 422, f'{alan}: {r.get_data(as_text=True)[:400]}'
        j = r.get_json()
        assert j['missing_fields'] == [alan]
        assert alan in j['field_reasons']

    def test_p_ambient_eksikse_422_ve_gerekce(self, client):
        """MUTASYON HEDEFİ: sessiz bir deniz seviyesi varsayılanı konursa
        bu test 200 alır ve kırmızıya döner."""
        r = client.post(UC, json=govde(P_ambient_Pa=None))
        assert r.status_code == 422
        gerekce = r.get_json()['field_reasons']['P_ambient_Pa'].lower()
        # Gerekçe NEDEN'i söylemeli: ölçüt ortam basıncına göre tanımlı ve
        # varsayılan üretmek uydurmadır.
        assert 'ambient' in gerekce
        assert 'separation' in gerekce
        assert 'fabricated' in gerekce or 'invent' in gerekce

    def test_bos_dize_de_eksik_sayilir(self, client):
        """Panel boş form alanını '' olarak gönderirse de 422 gelmeli."""
        r = client.post(UC, json=govde(P_ambient_Pa=''))
        assert r.status_code == 422
        assert r.get_json()['missing_fields'] == ['P_ambient_Pa']

    def test_bozuk_json_govdesi_uca_ulasmaz(self, client):
        """Bozuk gövde uygulama GENELİNDEKİ kapıda durur (app.py
        ``_reject_malformed_json_body`` before_request kapısı, makine-okur
        ``malformed_json_body``). Uç yine de kendi ikinci savunma hattını
        tutar (``get_json(silent=True) or {}`` -> 422); bekçi burada
        uygulamanın TEK sözleşmesini kilitler ki uç kendi 400/422'sini
        uydurup kapıyla çelişmesin."""
        r = client.post(UC, data='bu json degil',
                        content_type='application/json')
        assert r.status_code == 400
        assert r.get_json()['error'] == 'malformed_json_body'


class TestBozukKontur:
    @pytest.mark.parametrize('kontur,neden', [
        ({'points': 'metin'}, 'sayı olmayan'),
        ({'points': [1.0, 2.0, 3.0]}, '1B dizi'),
        ({'points': [[0.0, 0.05], [0.1, 0.03]]}, '3 noktadan az'),
        ({'points': [[0.0, 0.05], [0.1, float('nan')], [0.2, 0.04]]},
         'sonlu değil'),
        ({'points': [[0.0, 0.05], [0.1, 0.03], [0.05, 0.04]]}, 'z azalıyor'),
        ({'points': [[0.0, 0.05], [0.1, 0.0], [0.2, 0.04]]}, 'r sıfır'),
        ({'points': [[0.0, 0.05], [0.0, 0.03], [0.0, 0.04]]}, 'eksenel boy 0'),
        ({'points': []}, 'boş'),
    ])
    def test_bozuk_kontur_400(self, client, kontur, neden):
        r = client.post(UC, json=govde(nozzle_contour=kontur))
        assert r.status_code == 400, f'{neden}: {r.status_code}'
        j = r.get_json()
        assert j['error'] == 'invalid_cfd_nozzle_input'
        assert 'nozzle_contour' in j['field']
        assert len(j['message']) > 30

    def test_bogaz_iceride_olmali_400(self, client):
        """Boğazsız (tek yönde açılan) kontur reddedilir — ayrılma ölçütünün
        arayacağı ıraksak bölge kalmazdı ve köprü 10 saniyelik koşudan SONRA
        ValueError yükseltirdi."""
        r = client.post(UC, json=govde(nozzle_contour={'points': [
            [0.0, 0.02], [0.05, 0.03], [0.10, 0.04], [0.15, 0.05]]}))
        assert r.status_code == 400
        assert 'throat' in r.get_json()['message'].lower()

    def test_kontur_motor_sonucundan_da_okunur(self, client, kontur_iyi):
        """Panel elindeki motor sonucunu olduğu gibi gönderebilmeli."""
        g = govde(nozzle_contour=None)
        g['motor_results'] = {'nozzle_contour': kontur_iyi}
        r = _sessiz(client.post, UC, json=g)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        assert (r.get_json()['cfd']['inputs']['contour_field']
                == 'motor_results.nozzle_contour.points')


class TestSayisalBantlar:
    @pytest.mark.parametrize('deger', [1.0, 2.0, 0.9, 2.5, -1.0, 0.0])
    def test_gamma_bant_disi_400(self, client, deger):
        """Çözücünün kendi bandı (1, 2) — uçta AYNI bant, ama 400 ile
        (çözücüye bırakılsaydı ham ValueError 500'e sızardı)."""
        r = client.post(UC, json=govde(gamma=deger))
        assert r.status_code == 400, f'gamma={deger}'
        assert r.get_json()['field'] == 'gamma'

    @pytest.mark.parametrize('alan', ['P0_Pa', 'T0_K', 'R_J_per_kgK'])
    @pytest.mark.parametrize('deger', [0.0, -1.0])
    def test_pozitif_olmali_400(self, client, alan, deger):
        r = client.post(UC, json=govde(**{alan: deger}))
        assert r.status_code == 400, f'{alan}={deger}'
        assert r.get_json()['field'] == alan

    @pytest.mark.parametrize('alan', ['P0_Pa', 'T0_K', 'gamma',
                                      'R_J_per_kgK', 'P_ambient_Pa'])
    def test_sayi_olmayan_400(self, client, alan):
        r = client.post(UC, json=govde(**{alan: 'abc'}))
        assert r.status_code == 400, alan
        assert r.get_json()['field'] == alan

    def test_p_ambient_negatif_400(self, client):
        r = client.post(UC, json=govde(P_ambient_Pa=-1.0))
        assert r.status_code == 400
        assert r.get_json()['field'] == 'P_ambient_Pa'

    def test_sonsuz_deger_400(self, client):
        """NaN/Inf sessizce geçmemeli (IEEE-754 karşılaştırma tuzağı)."""
        for deger in ('NaN', 'Infinity'):
            r = client.post(UC, data=json.dumps(dict(govde(), P0_Pa=deger)),
                            content_type='application/json')
            assert r.status_code == 400, deger
            assert r.get_json()['field'] == 'P0_Pa'

    def test_separation_factor_bant_disi_400(self, client):
        """k'nın bandı köprüden İTHAL edilir; bant dışı değer koşudan ÖNCE
        400 alır (köprüye bırakılsaydı 10 saniye harcanırdı)."""
        from hrma.cfd.separation import (SEPARATION_FACTOR_MAX,
                                         SEPARATION_FACTOR_MIN)
        for deger in (SEPARATION_FACTOR_MIN - 0.01,
                      SEPARATION_FACTOR_MAX + 0.01):
            r = client.post(UC, json=govde(separation_factor=deger))
            assert r.status_code == 400, deger
            assert r.get_json()['field'] == 'separation_factor'


class TestCozunurlukBeyazListe:
    def test_bos_cozunurluk_varsayilana_duser(self, client, kontur_iyi):
        """Panel boş seçim gönderirse uydurma bir seviye seçilmez, ilan
        edilmiş VARSAYILAN kullanılır ve yanıtta adıyla beyan edilir."""
        from hrma.app import CFD_DEFAULT_RESOLUTION
        for bos in ('', None):
            r = _sessiz(client.post, UC, json=govde(
                nozzle_contour=kontur_iyi, resolution=bos))
            assert r.status_code == 200, repr(bos)
            assert (r.get_json()['cfd']['grid']['resolution']
                    == CFD_DEFAULT_RESOLUTION)

    @pytest.mark.parametrize('deger', ['ultra', 'fine', 240, '120x24'])
    def test_cozunurluk_beyaz_liste_disi_400(self, client, deger):
        r = client.post(UC, json=govde(resolution=deger))
        assert r.status_code == 400, deger
        j = r.get_json()
        assert j['field'] == 'resolution'
        # Kabul edilen seviyeler mesajda ADLANDIRILMALI (panel listeyi
        # buradan öğrenir).
        from hrma.app import CFD_RESOLUTION_LEVELS
        for ad in CFD_RESOLUTION_LEVELS:
            assert ad in j['message']

    def test_serbest_sayi_alinmaz(self, client):
        """Uzun koşu riski: istemci kendi ızgara boyunu dayatamaz."""
        for alan in ('ni', 'nj', 'n_axial', 'n_radial'):
            r = _sessiz(client.post, UC, json=govde(**{alan: 400}))
            # Alan tanınmaz -> sessizce düşer, koşu VARSAYILAN seviyede olur.
            assert r.status_code == 200, alan
            from hrma.app import (CFD_DEFAULT_RESOLUTION,
                                  CFD_RESOLUTION_LEVELS)
            ni, nj = CFD_RESOLUTION_LEVELS[CFD_DEFAULT_RESOLUTION]
            grid = r.get_json()['cfd']['grid']
            assert (grid['ni'], grid['nj']) == (ni, nj), alan


# ---------------------------------------------------------------------------
# §2 — MUTLU YOL: sözleşme anahtarları, JSON-yerli tipler, iç tutarlılık
# ---------------------------------------------------------------------------

class TestMutluYolSozlesme:
    def test_ust_seviye_kabuk(self, yanit_iyi):
        assert yanit_iyi['status'] == 'success'
        assert 'cfd' in yanit_iyi

    @pytest.mark.parametrize('anahtar', [
        'converged', 'convergence_basis', 'iterations', 'max_iterations',
        'residual_history', 'shock_sensor_columns', 'shock_sensor_basis',
        'budget', 'throat', 'section_average', 'wall_pressure', 'field',
        'separation', 'inlet_conditioning', 'grid', 'inputs',
        'kernel_backend', 'kernel_backend_basis', 'not_modelled',
        'assumptions', 'solver_runtime_s', 'runtime_s', 'runtime_basis',
        'limiter_frozen_at_iter', 'limiter_freeze_count',
    ])
    def test_sozlesme_anahtari_var(self, yanit_iyi, anahtar):
        assert anahtar in yanit_iyi['cfd'], anahtar

    def test_json_yerli_tipler(self, yanit_iyi):
        """numpy sızıntısı olmamalı: yanıt tekrar serileşebilmeli ve içinde
        yalnız JSON-yerli tipler bulunmalı."""
        json.dumps(yanit_iyi)          # sızıntı olsaydı burada patlardı

        def yuru(dugum, yol=''):
            if isinstance(dugum, dict):
                for k, v in dugum.items():
                    assert isinstance(k, str), yol
                    yuru(v, f'{yol}.{k}')
            elif isinstance(dugum, list):
                for i, v in enumerate(dugum):
                    yuru(v, f'{yol}[{i}]')
            else:
                assert isinstance(dugum, (str, int, float, bool, type(None))), \
                    f'{yol}: {type(dugum)}'
                assert not isinstance(dugum, (np.ndarray, np.generic)), yol

        yuru(yanit_iyi['cfd'])

    def test_beyanlar_bos_degil(self, yanit_iyi):
        cfd = yanit_iyi['cfd']
        assert len(cfd['convergence_basis']) > 60
        assert len(cfd['kernel_backend_basis']) > 40
        assert len(cfd['runtime_basis']) > 40
        assert len(cfd['grid']['_basis']) > 80
        assert len(cfd['field']['_basis']) > 80
        assert len(cfd['residual_history']['_basis']) > 80
        assert len(cfd['wall_pressure']['_basis']) > 40
        assert len(cfd['budget']['_basis']) > 40

    def test_not_modelled_cfd_beyani_aynen(self, yanit_iyi):
        """not_modelled paket kökünden gelmeli — uç kendi listesini yazmaz."""
        from hrma.cfd import CFD_NOT_MODELLED
        nm = yanit_iyi['cfd']['not_modelled']
        assert set(nm) == set(CFD_NOT_MODELLED)
        for k, v in CFD_NOT_MODELLED.items():
            assert nm[k] == v

    def test_varsayimlar_euler_zincirini_tasir(self, yanit_iyi):
        varsayim = yanit_iyi['cfd']['assumptions']
        for beklenen in ('steady', 'axisymmetric', 'inviscid'):
            assert beklenen in varsayim

    def test_kernel_backend_beyanli(self, yanit_iyi):
        assert yanit_iyi['cfd']['kernel_backend'] in ('numba', 'numpy')


class TestIcTutarlilik:
    def test_duvar_ekseni_kesin_artan_ve_izgarayla_ayni_boy(self, yanit_iyi):
        cfd = yanit_iyi['cfd']
        z = np.asarray(cfd['wall_pressure']['z_m'], dtype=float)
        p = np.asarray(cfd['wall_pressure']['pressure_Pa'], dtype=float)
        assert z.shape == p.shape
        assert z.size == cfd['grid']['ni']
        assert np.all(np.diff(z) > 0.0)
        assert np.all(p > 0.0)

    def test_kesit_ortalamasi_ni_uzunlugunda(self, yanit_iyi):
        cfd = yanit_iyi['cfd']
        ni = cfd['grid']['ni']
        for anahtar in ('z_m', 'mach', 'pressure_Pa'):
            assert len(cfd['section_average'][anahtar]) == ni, anahtar

    def test_bogaz_beyani_izgarayla_tutarli(self, yanit_iyi):
        cfd = yanit_iyi['cfd']
        bogaz = cfd['throat']
        assert 0 < bogaz['i'] < cfd['grid']['ni'] - 1
        assert bogaz['radius_m'] > 0.0
        # Boğaz alanı πr² olmalı (uç yeniden ölçeklemiyor)
        assert bogaz['area_m2'] == pytest.approx(
            np.pi * bogaz['radius_m'] ** 2, rel=1e-12)
        # İKİ AYRI TANIM, ikisi de beyanlı: grid.r_throat_m yeniden
        # örneklenmiş DÜĞÜM yarıçaplarının en küçüğü (koşu öncesi boğaz
        # kapısı ve daralma oranı ondan ölçülür), throat.radius_m ise
        # çözücünün HÜCRE KOLONU duvar yarıçapı (iki komşu düğümün
        # ortalaması). Aynı sayı DEĞİLLERDİR; farkları bir hücrenin duvar
        # yükselişini aşmamalı — aşarsa boğaz iki katmanda ayrışmış demektir.
        hucre_yukselisi = ((cfd['grid']['r_inlet_m']
                            - cfd['grid']['r_throat_m'])
                           / cfd['grid']['ni'])
        assert bogaz['radius_m'] >= cfd['grid']['r_throat_m']
        assert (bogaz['radius_m'] - cfd['grid']['r_throat_m']
                <= 2.0 * hucre_yukselisi)
        assert 'r_throat_m' in cfd['grid']['_basis'], (
            'iki boğaz yarıçapı tanımı beyanda ayrışmalı')

    def test_alan_blogu_sekli_ve_indeksleri(self, yanit_iyi):
        alan = yanit_iyi['cfd']['field']
        ni, nj = alan['grid_shape']
        n_i, n_j = alan['shape']
        assert len(alan['axial_indices']) == n_i
        assert len(alan['radial_indices']) == n_j
        assert alan['axial_indices'][0] == 0
        assert alan['axial_indices'][-1] == ni - 1
        assert alan['radial_indices'][0] == 0
        assert alan['radial_indices'][-1] == nj - 1
        assert alan['n_cells_total'] == ni * nj
        assert alan['n_cells_returned'] == n_i * n_j
        for ad in ('z_m', 'r_m', 'mach', 'pressure_Pa'):
            dizi = alan[ad]
            assert len(dizi) == n_i, ad
            assert all(len(satir) == n_j for satir in dizi), ad

    def test_alan_blogu_tavani_asmaz(self, client, kontur_iyi):
        """Her seviyede hücre tavanı tutulmalı ve inceltme BEYAN edilmeli."""
        from hrma.app import CFD_FIELD_MAX_CELLS, CFD_RESOLUTION_LEVELS
        for seviye in CFD_RESOLUTION_LEVELS:
            r = _sessiz(client.post, UC, json=govde(
                nozzle_contour=kontur_iyi, resolution=seviye))
            assert r.status_code == 200, seviye
            alan = r.get_json()['cfd']['field']
            assert alan['n_cells_returned'] <= CFD_FIELD_MAX_CELLS, seviye
            beklenen = alan['n_cells_returned'] < alan['n_cells_total']
            assert alan['decimated'] is beklenen, seviye

    def test_alan_blogu_duvara_kadar_gidiyor(self, yanit_iyi):
        """Radyal yön inceltilmemeli: son sütun duvara komşu hücredir ve
        kontur haritasının duvar kenarı ondan çizilir."""
        cfd = yanit_iyi['cfd']
        alan = cfd['field']
        assert alan['radial_indices'] == list(range(cfd['grid']['nj']))
        # Duvara komşu hücre basıncı, duvar basıncı dizisiyle aynı olmalı
        # (ikisi de aynı hücrenin ham değeri — uç ikisini ayrı ÜRETMİYOR).
        duvar_p = np.asarray(cfd['wall_pressure']['pressure_Pa'], dtype=float)
        alan_p = np.asarray([satir[-1] for satir in alan['pressure_Pa']],
                            dtype=float)
        secilen = np.asarray(alan['axial_indices'], dtype=int)
        assert np.allclose(alan_p, duvar_p[secilen], rtol=0, atol=0)

    def test_kalinti_gecmisi_inceltmesi_beyanli(self, yanit_iyi):
        from hrma.app import CFD_RESIDUAL_MAX_POINTS
        rh = yanit_iyi['cfd']['residual_history']
        assert rh['n_returned'] <= CFD_RESIDUAL_MAX_POINTS
        assert rh['n_total'] == yanit_iyi['cfd']['iterations']
        assert rh['iteration'][0] == 0
        assert rh['iteration'][-1] == rh['n_total'] - 1
        assert len(rh['value']) == rh['n_returned']
        assert rh['decimated'] is (rh['n_returned'] < rh['n_total'])
        # İnceltmenin gizleyebileceği iki sayı TAM gelmeli
        assert rh['last'] == pytest.approx(rh['value'][-1], rel=1e-12)
        assert rh['min'] <= min(rh['value'])

    def test_yakinsayan_kosuda_korunum_butcesi_kapali(self, yanit_iyi):
        """Bu bir DOĞRULAMA değil, tutarlılık bekçisidir: çözücü yakınsadı
        dediyse kütle bütçesi de kapanmış olmalı (aksi hâlde hüküm ile
        ölçüm çelişirdi)."""
        cfd = yanit_iyi['cfd']
        assert cfd['converged'] is True, cfd['convergence_basis']
        assert cfd['budget']['mass_balance_rel'] < 1e-6
        assert cfd['budget']['energy_balance_rel'] < 1e-6
        assert cfd['budget']['mass_flow_in_kg_s'] > 0.0

    def test_sureler_pozitif_ve_siralı(self, yanit_iyi):
        cfd = yanit_iyi['cfd']
        assert cfd['solver_runtime_s'] > 0.0
        assert cfd['runtime_s'] >= cfd['solver_runtime_s']


class TestGirdiYankisi:
    def test_girdiler_yankilanir(self, yanit_iyi):
        g = yanit_iyi['cfd']['inputs']
        assert g['P0_Pa'] == pytest.approx(GAZ['P0_Pa'])
        assert g['T0_K'] == pytest.approx(GAZ['T0_K'])
        assert g['gamma'] == pytest.approx(GAZ['gamma'])
        assert g['R_J_kgK'] == pytest.approx(GAZ['R_J_per_kgK'])
        assert g['P_ambient_Pa'] == pytest.approx(P_ORTAM_YUKSEK_IRTIFA)
        assert g['contour_field'] == 'nozzle_contour.points'
        assert g['contour_points'] > 3

    def test_Pb_yoksa_dısdegerleme_beyan_edilir(self, yanit_iyi):
        """Pb verilmediğinde iç şok ARANAMAZ; bu sessiz kalmamalı."""
        g = yanit_iyi['cfd']['inputs']
        assert g['Pb_Pa'] is None
        beyan = g['back_pressure_basis'].lower()
        assert 'not supplied' in beyan
        assert 'extrapolation' in beyan
        assert 'shock' in beyan

    def test_Pb_verilirse_yankilanir(self, client, kontur_iyi):
        r = _sessiz(client.post, UC, json=govde(
            nozzle_contour=kontur_iyi, Pb_Pa=3.0e5))
        assert r.status_code == 200
        g = r.get_json()['cfd']['inputs']
        assert g['Pb_Pa'] == pytest.approx(3.0e5)
        assert 'was supplied' in g['back_pressure_basis']


# ---------------------------------------------------------------------------
# §3 — AYRILMA KÖPRÜSÜ: bit-tutarlılık + gölgeleme kapısı
# ---------------------------------------------------------------------------

class TestAyrilmaKoprusu:
    def test_ayrilma_koprusu_cfd_modulunden(self):
        """GÖLGELEME KAPISI: uçtaki fonksiyonun KİMLİĞİ denetlenir.

        ``hrma.flow`` da ``assess_separation`` adını dışa verir (yarı-1B
        sürüm, ilk argümanı P0). Uç yanlışlıkla onu alsaydı ilk argüman
        sözlük olduğu için ya patlardı ya da sessizce yanlış hüküm üretirdi.
        """
        import hrma.cfd.separation as cfd_sep
        import hrma.flow as flow
        from hrma.app import _cfd_separation_fn

        fn = _cfd_separation_fn()
        assert fn is cfd_sep.assess_separation
        assert fn is not flow.assess_separation
        assert fn.__module__ == 'hrma.cfd.separation'

    def test_app_ad_alaninda_ciplak_assess_separation_yok(self):
        """app modülünde çıplak ``assess_separation`` adı BULUNMAMALI —
        bulunursa ileride biri onu ithal edip diğerini gölgeler."""
        import hrma.app as app_modulu
        assert not hasattr(app_modulu, 'assess_separation')

    def test_kaynakta_takma_adsiz_ithal_yok(self):
        """Kaynak düzeyi bekçi: app.py'de ``assess_separation`` ithal eden
        HER satır takma ad kullanmalı."""
        kaynak = Path('hrma/app.py').read_text(encoding='utf-8')
        satirlar = [s.strip() for s in kaynak.splitlines()
                    if re.match(r'\s*from\s+\S+\s+import\b', s)
                    and 'assess_separation' in s]
        assert satirlar, 'köprü hiç ithal edilmiyor — uç bağlanmamış olmalı'
        for s in satirlar:
            assert 'as assess_cfd_separation' in s, s

    def test_cozum_uc_disinda_bit_aynisiyla_uretilebiliyor(self, yerel_cozum,
                                                           yanit_iyi):
        """Aşağıdaki bit-tutarlılık ölçümünün ÖN KOŞULU: uç sürücü ayarı
        VERMEDİĞİ için (çözücünün kendi varsayılanları) uç dışında yapılan
        koşu aynı alanı üretmeli. Üretmiyorsa alt bekçinin karşılaştırması
        anlamsız olurdu, bu yüzden ayrıca ölçülür."""
        cfd = yanit_iyi['cfd']
        assert yerel_cozum['iterations'] == cfd['iterations']
        assert yerel_cozum['converged'] is cfd['converged']
        assert np.allclose(
            np.asarray(yerel_cozum['wall_pressure_Pa'], dtype=float),
            np.asarray(cfd['wall_pressure']['pressure_Pa'], dtype=float),
            rtol=0, atol=0)

    @pytest.mark.parametrize('vaka,p_ortam', [
        ('taban (ayrılma yok)', P_ORTAM_YUKSEK_IRTIFA),
        ('ayrılmalı', P_ORTAM_AYRILMALI),
        ('vakum', 0.0),
    ])
    def test_ayrilma_blogu_bit_tutarli(self, request, yerel_cozum, vaka,
                                       p_ortam):
        """Uç, köprünün çıktısını AYNEN taşımalı — anahtar anahtar.

        ÜÇ VAKA BİRDEN, bilerek: yalnız taban vakada ölçmek YETMEZ. Orada
        ``separation_z_m`` ve ``separation_z_interp_m`` ``None``, eşik ise
        yuvarlak bir sayıdır (0,40 × 20 kPa = 8000 Pa); ucun köprünün
        sayılarını "temizlemesi" (ör. round(…, 4)) o vakada GÖRÜNMEZ kalır.
        Ayrılmalı vaka bu alanları ondalıklı gerçek sayılarla doldurur ve
        yuvarlamayı yakalar; vakum vakası da red dalını (applicable=False)
        aynı sözleşmeyle ölçer. (Mutasyon M3 tam olarak bu boşluktan
        geçmişti; bekçi ondan sonra genişletildi.)
        """
        from hrma.app import sanitize_json_values
        from hrma.cfd.separation import (
            assess_separation as assess_cfd_separation)

        yanit = request.getfixturevalue({
            P_ORTAM_YUKSEK_IRTIFA: 'yanit_iyi',
            P_ORTAM_AYRILMALI: 'yanit_ayrilmali',
            0.0: 'yanit_vakum',
        }[p_ortam])
        gelen = yanit['cfd']['separation']
        beklenen = sanitize_json_values(
            assess_cfd_separation(yerel_cozum, p_ortam))

        assert set(gelen) == set(beklenen), (vaka,
                                             set(gelen) ^ set(beklenen))
        for anahtar, deger in beklenen.items():
            assert gelen[anahtar] == deger, f'{vaka}: {anahtar}'

    def test_ayrilmali_vakada_karsilastirma_bos_degil(self, yanit_ayrilmali):
        """Üstteki bekçinin ayrılmalı vakası GERÇEKTEN ondalıklı sayı
        taşımalı — taşımasaydı yuvarlama mutasyonu yine görünmezdi.

        ``threshold_Pa`` bu listede YOK ve olması da doğru olmazdı: eşik
        k·P_ortam çarpımıdır, makul bir ortam basıncında dört haneden fazla
        ondalık ASLA taşımaz, yani onu yuvarlamak ölçülebilir bir kusur
        değildir. Karşılaştırmanın gerçek yükünü çözücüden gelen konum ve
        oran alanları taşır (17 anlamlı haneli).
        """
        sep = yanit_ayrilmali['cfd']['separation']
        for anahtar in ('separation_z_m', 'separation_z_interp_m',
                        'separated_length_m', 'separated_length_fraction',
                        'wall_pressure_min_Pa', 'wall_pressure_margin_min'):
            deger = sep[anahtar]
            assert isinstance(deger, float), anahtar
            # 4 haneye yuvarlanmış olsaydı fark 0 olurdu
            assert deger != round(deger, 4), anahtar

    def test_taban_vakada_olcut_kendiyle_tutarli(self, yanit_iyi):
        """Sayı SABİTLENMEZ: ayrılma bayrağı bloğun kendi marjıyla tutarlı
        olmalı (margin = min p_w / eşik; < 1 ise ayrılma)."""
        sep = yanit_iyi['cfd']['separation']
        assert sep['applicable'] is True
        assert sep['separated'] is (sep['wall_pressure_margin_min'] < 1.0)
        assert sep['threshold_Pa'] == pytest.approx(
            sep['separation_factor'] * P_ORTAM_YUKSEK_IRTIFA, rel=1e-12)
        assert sep['ambient_pressure_Pa'] == pytest.approx(
            P_ORTAM_YUKSEK_IRTIFA)
        assert sep['judgment_confidence'] == 'firm'
        assert sep['criterion']

    def test_yuksek_ortam_basincinda_ayrilma_ongorulur(self, yanit_ayrilmali):
        """Ayrılma DALI da koşulmalı (yalnız 'ayrılma yok' dalı test edilseydi
        köprünün yarısı ölçülmemiş kalırdı). Konum sabitlenmez; yalnız
        ıraksak bölgede ve boğazın aşağısında olduğu ölçülür."""
        cfd = yanit_ayrilmali['cfd']
        sep = cfd['separation']
        assert sep['applicable'] is True
        assert sep['separated'] is True, sep['wall_pressure_margin_min']
        assert sep['separation_index'] > sep['throat_index']
        assert sep['throat_z_m'] < sep['separation_z_m'] <= sep['exit_z_m']
        assert 0.0 < sep['separated_length_fraction'] <= 1.0
        assert sep['separation_wall_pressure_Pa'] < sep['threshold_Pa']
        assert len(sep['search_domain_basis']) > 80
        assert len(sep['criterion_basis']) > 80

    def test_vakumda_hukum_verilmez(self, yanit_vakum):
        """P_ortam = 0: eşik 0 olur, hiçbir sonlu basınç altına inemez.
        'Ayrılma yok' demek yanıltıcı olurdu -> applicable=False + gerekçe."""
        sep = yanit_vakum['cfd']['separation']
        assert sep['applicable'] is False
        assert sep.get('separated') is False
        assert len(sep['not_applicable_reason']) > 60
        assert 'bridge_refused' not in sep   # bu bir RED değil, TANIMSIZLIK

    def test_koprunun_reddi_beyanla_gecer(self, client, kontur_iyi,
                                          monkeypatch):
        """Köprü kendi sözleşmesini ihlal eden bir sonuca hüküm VERMEZ
        (ValueError). Bu red 500'e çevrilmez ve 'ayrılma yok' diye
        yumuşatılmaz: akış alanı yine döner, red BEYAN edilir."""
        import hrma.app as app_modulu

        def reddet(*_a, **_k):
            raise ValueError('sözleşme ihlali: duvar ekseni bozuk (test)')

        monkeypatch.setattr(app_modulu, '_cfd_separation_fn',
                            lambda: reddet)
        r = _sessiz(client.post, UC, json=govde(nozzle_contour=kontur_iyi))
        assert r.status_code == 200
        cfd = r.get_json()['cfd']
        sep = cfd['separation']
        assert sep['applicable'] is False
        assert sep['bridge_refused'] is True
        assert 'sözleşme ihlali' in sep['not_applicable_reason']
        assert 'separated' not in sep      # hüküm UYDURULMADI
        assert cfd['field']['n_cells_returned'] > 0   # alan gizlenmedi

    def test_beklenmedik_istisna_yutulmaz(self, client, kontur_iyi,
                                          monkeypatch):
        """ValueError köprünün BEYAN EDİLMİŞ reddidir; başka bir istisna
        sözleşme ihlalidir ve sessizce 'hüküm verilemedi'ye dönüşmemeli
        (gölgeleme kusuru tam böyle normalleşirdi)."""
        import hrma.app as app_modulu

        def patla(*_a, **_k):
            raise TypeError('yanlış imza (test)')

        monkeypatch.setattr(app_modulu, '_cfd_separation_fn', lambda: patla)
        r = _sessiz(client.post, UC, json=govde(nozzle_contour=kontur_iyi))
        assert r.status_code == 500
        j = r.get_json()
        assert j['status'] == 'error'
        assert 'TypeError' in j['detail']

    def test_separation_factor_yankilanir(self, client, kontur_iyi):
        """Çağıranın verdiği k kullanılmalı (varsayılana sessizce dönmemeli)."""
        from hrma.cfd.separation import SEPARATION_FACTOR_DEFAULT
        k = round(SEPARATION_FACTOR_DEFAULT - 0.05, 4)
        r = _sessiz(client.post, UC, json=govde(
            nozzle_contour=kontur_iyi, P_ambient_Pa=P_ORTAM_AYRILMALI,
            separation_factor=k))
        assert r.status_code == 200
        sep = r.get_json()['cfd']['separation']
        assert sep['separation_factor'] == pytest.approx(k, rel=1e-12)
        assert sep['separation_factor_source'] == 'caller'
        assert r.get_json()['cfd']['inputs']['separation_factor'] == \
            pytest.approx(k)


# ---------------------------------------------------------------------------
# §4 — ÇÖZÜNÜRLÜK BEYAZ LİSTESİ VE SÜRE CÜZDANI BEYANI
# ---------------------------------------------------------------------------

class TestCozunurlukBeyani:
    def test_varsayilan_seviye(self, yanit_iyi):
        from hrma.app import CFD_DEFAULT_RESOLUTION, CFD_RESOLUTION_LEVELS
        grid = yanit_iyi['cfd']['grid']
        assert grid['resolution'] == CFD_DEFAULT_RESOLUTION
        ni, nj = CFD_RESOLUTION_LEVELS[CFD_DEFAULT_RESOLUTION]
        assert (grid['ni'], grid['nj']) == (ni, nj)
        assert grid['default_resolution'] == CFD_DEFAULT_RESOLUTION

    def test_seviyeler_ve_olculen_sureler_yanitta(self, yanit_iyi):
        """Panel süre beklentisini yanıttan okumalı — kaynakta ikinci kez
        yazılmamalı (parametre tutarlılığı) ve sahte ilerleme çubuğu için
        uydurma sayı ÜRETİLMEMELİ."""
        from hrma.app import (CFD_RESOLUTION_LEVELS,
                              CFD_RESOLUTION_WORST_CASE_S)
        seviyeler = yanit_iyi['cfd']['grid']['levels']
        assert set(seviyeler) == set(CFD_RESOLUTION_LEVELS)
        for ad, (ni, nj) in CFD_RESOLUTION_LEVELS.items():
            assert seviyeler[ad]['ni'] == ni
            assert seviyeler[ad]['nj'] == nj
            assert seviyeler[ad]['n_cells'] == ni * nj
            olculen = seviyeler[ad]['worst_case_s']
            assert set(olculen) == {'numba', 'numpy'}
            assert olculen == CFD_RESOLUTION_WORST_CASE_S[ad]
            assert olculen['numpy'] > olculen['numba'] > 0.0

    def test_varsayilan_seviye_numbasiz_da_cuzdanda(self):
        """Varsayılan seviye, numba OLMADAN da ~20 s cüzdanını tutmalı —
        numba isteğe bağlı bağımlılıktır, varsayılan ona bel bağlayamaz."""
        from hrma.app import (CFD_DEFAULT_RESOLUTION,
                              CFD_RESOLUTION_WORST_CASE_S)
        assert (CFD_RESOLUTION_WORST_CASE_S[CFD_DEFAULT_RESOLUTION]['numpy']
                <= 20.0)

    def test_standard_seviyesi_gercekten_daha_ince(self, client, kontur_iyi):
        from hrma.app import CFD_RESOLUTION_LEVELS
        r = _sessiz(client.post, UC, json=govde(
            nozzle_contour=kontur_iyi, resolution='standard'))
        assert r.status_code == 200
        grid = r.get_json()['cfd']['grid']
        assert (grid['ni'], grid['nj']) == CFD_RESOLUTION_LEVELS['standard']
        assert grid['n_cells'] == grid['ni'] * grid['nj']


# ---------------------------------------------------------------------------
# §5 — YAKINSAMAYAN KOŞU: sonuç gizlenmez, hüküm de verilmez
# ---------------------------------------------------------------------------

class TestYakinsamayanKosu:
    def test_yakinsamayan_kosu_200_ve_durust(self, yanit_yakinsamayan):
        cfd = yanit_yakinsamayan['cfd']
        assert cfd['converged'] is False
        # Sonuç GİZLENMEZ: alanlar ve bütçe yine gelir.
        assert cfd['field']['n_cells_returned'] > 0
        assert cfd['budget']['mass_flow_in_kg_s'] > 0.0
        # Gerekçe, hangi ölçütün sağlanmadığını SÖYLEMELİ.
        gerekce = cfd['convergence_basis']
        assert 'OTURMADI' in gerekce or 'DIVERGED' in gerekce
        assert cfd['iterations'] == cfd['max_iterations']

    def test_oturmamanin_sebebi_ACIK_butcedir(self, yanit_yakinsamayan):
        """Vakanın kendisi de beyanlı olmalı: koşu bir fizik kazasından
        değil, İSTEMCİNİN verdiği tavandan durdu ve yanıt bunu söylüyor."""
        cfd = yanit_yakinsamayan['cfd']
        assert cfd['max_iterations'] == BUTCE_KISITLI_TAVAN
        assert cfd['max_iterations_source'] == 'caller'
        assert cfd['inputs']['max_iterations'] == BUTCE_KISITLI_TAVAN
        assert 'caller supplied' in cfd['max_iterations_basis']

    def test_hukum_supheli_etiketle_gelir(self, yanit_yakinsamayan):
        """Ayrılma hükmü ne gizlenir ne sağlam sunulur."""
        sep = yanit_yakinsamayan['cfd']['separation']
        assert sep['converged'] is False
        assert sep['judgment_confidence'] == 'suspect'
        assert 'YAKINSAMADI' in sep['judgment_basis']
        # Çözücünün kendi beyanı hükümle birlikte taşınmalı
        assert sep['solver_convergence_basis'] == \
            yanit_yakinsamayan['cfd']['convergence_basis']

    def test_kalinti_gecmisi_tavana_kadar_gelir(self, yanit_yakinsamayan):
        from hrma.app import CFD_RESIDUAL_MAX_POINTS
        rh = yanit_yakinsamayan['cfd']['residual_history']
        assert rh['n_total'] > CFD_RESIDUAL_MAX_POINTS
        assert rh['decimated'] is True
        assert rh['n_returned'] <= CFD_RESIDUAL_MAX_POINTS
        # İnceltme "son kalıntı"yı gizleyemez
        assert rh['last'] == pytest.approx(rh['value'][-1], rel=1e-12)


# ---------------------------------------------------------------------------
# §6 — GİRİŞ KOŞULLANDIRMA BLOĞU: BÜTÇE UYARISI (ölçülmüş olgu, HÜKÜM DEĞİL)
# ---------------------------------------------------------------------------

class TestGirisKosullandirma:
    def test_uyari_blogu_her_kosuda_var(self, yanit_iyi):
        u = yanit_iyi['cfd']['inlet_conditioning']
        for anahtar in ('contraction_ratio', 'inlet_mach_isentropic',
                        'inlet_bc', 'resolution', 'max_iterations',
                        'budget_advisory', 'budget_advisory_reasons',
                        'budget_advisory_bands', 'budget_risk_fraction',
                        'nearest_measured', 'measured_expectations',
                        '_basis'):
            assert anahtar in u, anahtar
        assert len(u['_basis']) > 300      # ölçüm künyesi beyanda

    def test_emekli_mach_esigi_geri_gelmemis(self, yanit_iyi):
        """NÖBET DEĞİŞİMİ BEKÇİSİ: eski Mach eşikli sözleşme geri konursa
        (``threshold_mach`` / ``advisory``) bu test kırmızıya döner. İki
        sözleşmenin YAN YANA yaşaması en kötüsü olurdu: panel hangisine
        bakacağını bilemez, kullanıcı iki farklı uyarı görür."""
        u = yanit_iyi['cfd']['inlet_conditioning']
        assert 'threshold_mach' not in u
        assert 'advisory' not in u
        import hrma.app as app_modulu
        assert not hasattr(app_modulu, 'CFD_INLET_MACH_ADVISORY')

    def test_daralma_orani_izgaradan_olculur(self, yanit_iyi):
        cfd = yanit_iyi['cfd']
        u = cfd['inlet_conditioning']
        beklenen = (cfd['grid']['r_inlet_m'] / cfd['grid']['r_throat_m']) ** 2
        assert u['contraction_ratio'] == pytest.approx(beklenen, rel=1e-9)

    def test_giris_machi_depo_bagintisindan(self, yanit_iyi):
        """Mach, ikinci kez GERÇEKLENMEZ: quasi1d alan-Mach terslemesinden.
        (Artık hiçbir uyarıyı tetiklemez, yalnız BİLGİ olarak durur.)"""
        from hrma.flow.quasi1d import mach_from_area_ratio
        u = yanit_iyi['cfd']['inlet_conditioning']
        beklenen = float(mach_from_area_ratio(u['contraction_ratio'],
                                              GAZ['gamma'], supersonic=False))
        assert u['inlet_mach_isentropic'] == pytest.approx(beklenen, rel=1e-9)

    def test_giris_bc_cozucunun_beyanindan(self, yanit_iyi):
        """``inlet_bc`` uçta YENİDEN adlandırılmaz: çözücünün kendi beyanı
        (bu ad değişirse blok da değişmeli — yoksa panel bayat BC adı basar)."""
        from hrma.cfd.euler_core import INLET_BC_NAME
        cfd = yanit_iyi['cfd']
        u = cfd['inlet_conditioning']
        assert u['inlet_bc'] == INLET_BC_NAME
        assert u['inlet_bc'] in cfd['convergence_basis']
        assert len(u['inlet_bc_basis']) > 200

    def test_iyi_kosullanmis_vakada_uyari_yok(self, yanit_iyi):
        """Sağlıklı, hızlı yakınsayan koşuda turuncu rozet OLMAMALI.

        Eski (Mach eşikli) sözleşmenin kusuru buydu: her yüksek daralma
        oranlı gerçek motorda uyarı ateşliyordu. Yeni ölçüt bütçe
        maliyetidir — bu vaka bütçenin %11'ini kullanıyor.
        """
        cfd = yanit_iyi['cfd']
        u = cfd['inlet_conditioning']
        assert u['budget_advisory'] is False
        assert u['budget_advisory_reasons'] == []
        assert cfd['converged'] is True
        assert cfd['iterations'] < 0.5 * cfd['max_iterations']

    def test_butce_kisitliyken_uyari_var_ve_gerekcesi_adiyla_gelir(
            self, yanit_yakinsamayan):
        u = yanit_yakinsamayan['cfd']['inlet_conditioning']
        assert u['budget_advisory'] is True
        assert 'budget_below_measured_need' in u['budget_advisory_reasons']
        # Uyarı hangi ÖLÇÜM satırına bakarak verildiğini söylemeli
        en_yakin = u['nearest_measured']
        assert en_yakin is not None
        assert en_yakin['resolution'] == u['resolution']
        assert u['max_iterations'] < en_yakin['iterations']

    def test_uyari_bayragi_gerekceyle_ayrisamaz(self, yanit_iyi,
                                                yanit_yakinsamayan):
        """Bayrak ile gerekçe listesi TEK kaynaktan türemeli. Ayrışabilselerdi
        "uyarı var ama sebebi yok" (ya da tersi) bir ekran mümkün olurdu."""
        for yanit in (yanit_iyi, yanit_yakinsamayan):
            u = yanit['cfd']['inlet_conditioning']
            assert u['budget_advisory'] is bool(u['budget_advisory_reasons'])
            for gerekce in u['budget_advisory_reasons']:
                assert gerekce in ('measured_slow_band',
                                   'budget_below_measured_need'), gerekce

    def test_olcum_tablosu_makine_okur_ve_tam(self, yanit_iyi):
        """``measured_expectations`` uçtaki tablonun AYNISI olmalı — panel
        beklentiyi buradan okur, ikinci bir tablo yazmaz."""
        from hrma.app import CFD_MEASURED_CONVERGENCE, CFD_RESOLUTION_LEVELS
        tablo = yanit_iyi['cfd']['inlet_conditioning']['measured_expectations']
        assert len(tablo) == len(CFD_MEASURED_CONVERGENCE)
        assert {s['resolution'] for s in tablo} == set(CFD_RESOLUTION_LEVELS)
        for satir, kaynak in zip(tablo, CFD_MEASURED_CONVERGENCE):
            assert satir == dict(kaynak)
            for alan in ('contraction_ratio', 'inlet_mach_isentropic',
                         'iterations', 'converged', 'residual_last',
                         'mass_balance_rel'):
                assert alan in satir, alan
        # Tabloda EN AZ bir tavana dayanan satır olmalı: bütçe uyarısının
        # varlık sebebi odur (hepsi yakınsıyorsa uyarı da gerekmezdi).
        assert any(s['converged'] is False for s in tablo)

    def test_riskli_bant_tablodan_turetilir(self):
        """Bant SERBEST SAYI DEĞİL: ölçüm tablosundan türetilen kuralın
        çıktısıdır. Tablo değişirse bant da değişmeli (aksi hâlde bant
        bayatlar ve kimse fark etmez)."""
        from hrma.app import (CFD_BUDGET_RISK_FRACTION, _cfd_budget_risk_bands,
                              _cfd_iteration_budget_band, _cfd_measured_rows)
        _alt, butce = _cfd_iteration_budget_band()
        for seviye in ('coarse', 'standard'):
            satirlar = _cfd_measured_rows(seviye)
            riskli = [r for r in satirlar
                      if (not r['converged'])
                      or r['iterations'] >= CFD_BUDGET_RISK_FRACTION * butce]
            bantlar = _cfd_budget_risk_bands(seviye)
            assert bool(bantlar) is bool(riskli), seviye
            for b in bantlar:
                # Her bant en az bir ÖLÇÜLEN riskli satır taşımalı
                assert b['measured_rows']
                for cr in b['measured_rows']:
                    assert any(r['contraction_ratio'] == cr for r in riskli)
                # Kenar ya ölçülen komşuların geometrik ortası ya da AÇIK
                if b['cr_min'] is not None:
                    assert b['cr_min'] < min(b['measured_rows'])
                if b['cr_max'] is not None:
                    assert b['cr_max'] > max(b['measured_rows'])
                assert b['open_below'] is (b['cr_min'] is None)
                assert b['open_above'] is (b['cr_max'] is None)

    def test_bant_kenarlari_olculen_sayilarla_civili(self):
        """AYNA-TEST KIRICI (H1 hakem bulgusu S-1, 16 Ağu 2026): üstteki
        test riskli-satır kuralını uygulamadan KOPYALAYARAK doğruluyor —
        kural iki yerde birden aynı biçimde bozulursa yeşil kalırdı. Bu
        bekçi kenarları ÖLÇÜLEN sabit sayılarla çiviler (hakem bağımsız
        koşumla yeniden üretti): coarse alt kenar 8,8668 (üst AÇIK),
        standard [4,6633; 8,8768] — komşu satırların geometrik ortaları.
        Ölçüm tablosu bilerek değişirse bu sayılar da bilerek güncellenir
        (yanına yeni ölçüm koşumu yazılarak); kendiliğinden kayma kırmızı."""
        from hrma.app import _cfd_budget_risk_bands
        coarse = _cfd_budget_risk_bands('coarse')
        standard = _cfd_budget_risk_bands('standard')
        assert len(coarse) == 1 and len(standard) == 1
        assert abs(coarse[0]['cr_min'] - 8.8668) < 5e-4, coarse[0]['cr_min']
        assert coarse[0]['cr_max'] is None  # tablo ucunda AÇIK — ekstrapolasyon beyanı
        assert abs(standard[0]['cr_min'] - 4.6633) < 5e-4, standard[0]['cr_min']
        assert abs(standard[0]['cr_max'] - 8.8768) < 5e-4, standard[0]['cr_max']

    @pytest.mark.parametrize('vaka,beklenen', [('yanit_bant_ici', True),
                                               ('yanit_bant_disi', False)])
    def test_bant_ici_kontur_uyari_alir_bant_disi_almaz(self, request, vaka,
                                                        beklenen):
        """Bandın İKİ yakası da koşulur: uyarı ne her koşuda ateşler ne de
        hiç ateşlemez. Vakalar bandın KENDİSİNDEN seçilir (sabit CR yazmak
        tabloyu ikinci kez tanımlamak olurdu)."""
        from hrma.app import _cfd_budget_risk_bands
        b = _cfd_budget_risk_bands('coarse')[0]
        u = request.getfixturevalue(vaka)['cfd']['inlet_conditioning']
        icinde = ((b['cr_min'] is None
                   or u['contraction_ratio'] >= b['cr_min'])
                  and (b['cr_max'] is None
                       or u['contraction_ratio'] <= b['cr_max']))
        assert icinde is beklenen, (
            f'vaka kurulumu bozuk: CR {u["contraction_ratio"]}')
        assert (('measured_slow_band' in u['budget_advisory_reasons'])
                is beklenen), u['budget_advisory_reasons']
        assert u['budget_advisory'] is beklenen

    def test_uyari_hukum_yerine_gecmez(self, yanit_yakinsamayan):
        """Uyarı bir HÜKÜM değildir: koşuyu engellemez ve 'converged'
        alanının yerini almaz. Bu ikisi AYRI alanlardır ve ikisi de gelir."""
        cfd = yanit_yakinsamayan['cfd']
        assert cfd['inlet_conditioning']['budget_advisory'] is True
        assert 'converged' in cfd and cfd['converged'] is False
        assert cfd['iterations'] > 0          # koşu gerçekten YAPILDI
        basis = cfd['inlet_conditioning']['_basis']
        assert 'NOT A VERDICT' in basis
        assert 'never blocks the run' in basis

    def test_uyari_atesleyen_kosu_YAKINSAYABILIR(self, yanit_bant_ici):
        """"Hüküm değildir"in CANLI kanıtı: uyarı ateşlerken koşu YAKINSAR.

        Eski (Mach eşikli) sözleşmede bu ikili "uyarı hep haksız" demekti;
        yeni sözleşmede uyarı DOĞRUDUR ve hüküm de doğrudur: koşu gerçekten
        bütçenin yarısından fazlasını yedi (ölçüldü) ama oturdu. Uyarı
        beklentiyi, hüküm çözücünün beyanını taşır; ikisi ÇELİŞMEZ.
        """
        cfd = yanit_bant_ici['cfd']
        assert cfd['inlet_conditioning']['budget_advisory'] is True, (
            'vaka kurulumu bozuk: uyarı ateşlemedi')
        assert cfd['converged'] is True, (
            'uyarı ateşledi diye koşu engellenmiş ya da hüküm bastırılmış')
        # Uyarının HAKLI olduğu da ölçülür: bu koşu bütçenin yarısından
        # fazlasını yedi (bandın tanımı buydu).
        from hrma.app import CFD_BUDGET_RISK_FRACTION
        assert (cfd['iterations']
                >= CFD_BUDGET_RISK_FRACTION * cfd['max_iterations'])


# ---------------------------------------------------------------------------
# §7 — İTERASYON BÜTÇESİ: açık sözleşme, bant, etkin değerin beyanı
# ---------------------------------------------------------------------------

class TestIterasyonButcesi:
    def test_varsayilan_cozucunun_tavani(self, yanit_iyi):
        """Uçta İKİNCİ bir tavan tanımı yok: bütçe verilmediğinde çözücünün
        kendi DEFAULT_MAX_ITERS'i geçerlidir ve bu beyan edilir."""
        from hrma.cfd.steady import DEFAULT_MAX_ITERS
        cfd = yanit_iyi['cfd']
        assert cfd['max_iterations'] == int(DEFAULT_MAX_ITERS)
        assert cfd['max_iterations_source'] == 'default'
        assert 'did not supply' in cfd['max_iterations_basis']

    def test_bant_cozucunun_sabitlerinden(self):
        from hrma.app import CFD_MAX_ITERS_MIN, _cfd_iteration_budget_band
        from hrma.cfd.steady import (DEFAULT_MAX_ITERS, DEFAULT_RAMP_ITERS,
                                     DEFAULT_SETTLE_WINDOW)
        alt, ust = _cfd_iteration_budget_band()
        assert (alt, ust) == (CFD_MAX_ITERS_MIN, int(DEFAULT_MAX_ITERS))
        # Alt sınır rampayı geçmeli: rampa bitmeden kesilen koşunun
        # "yakınsamadı" beyanı akış hakkında hiçbir şey söylemez.
        assert alt > DEFAULT_RAMP_ITERS
        # ve oturma penceresi kadar veri toplanabilmeli
        assert alt >= DEFAULT_SETTLE_WINDOW

    @pytest.mark.parametrize('deger', [499, 0, -5, 20001, 100000])
    def test_bant_disi_400(self, client, deger):
        r = client.post(UC, json=govde(max_iterations=deger))
        assert r.status_code == 400, deger
        j = r.get_json()
        assert j['field'] == 'max_iterations'
        assert str(deger) in j['message'] or 'must be in' in j['message']

    @pytest.mark.parametrize('deger', ['abc', 600.5, True, False, 'NaN',
                                       'Infinity', [600], {'v': 600}])
    def test_sayi_olmayan_ya_da_kesirli_400(self, client, deger):
        """Kesirli bütçe sessizce YUVARLANMAZ: kullanıcının yazdığından başka
        bir bütçeyle koşmak, bütçeyi açık kılma amacını yerle bir ederdi.
        ``True``/``False`` de sayı SAYILMAZ (Python'da bool bir int'tir ve
        denetimsiz bırakılsaydı ``true`` → 1 iterasyon bütçesi olurdu)."""
        govde_metni = json.dumps(dict(govde(), max_iterations=deger))
        r = client.post(UC, data=govde_metni,
                        content_type='application/json')
        assert r.status_code == 400, f'{deger!r}: {r.status_code}'
        assert r.get_json()['field'] == 'max_iterations', repr(deger)

    def test_bos_deger_varsayilana_duser(self, client, kontur_iyi):
        """Panel boş form alanını '' / None gönderirse uydurma bir tavan
        seçilmez, ilan edilmiş varsayılan kullanılır."""
        from hrma.cfd.steady import DEFAULT_MAX_ITERS
        for bos in ('', None):
            r = _sessiz(client.post, UC, json=govde(
                nozzle_contour=kontur_iyi, max_iterations=bos))
            assert r.status_code == 200, repr(bos)
            cfd = r.get_json()['cfd']
            assert cfd['max_iterations'] == int(DEFAULT_MAX_ITERS)
            assert cfd['max_iterations_source'] == 'default'

    def test_etkin_deger_cozucuye_GERCEKTEN_gecirilir(self, client,
                                                      kontur_iyi):
        """Yanıttaki sayı süs değil: koşu gerçekten o tavanda kesilmeli."""
        r = _sessiz(client.post, UC, json=govde(
            nozzle_contour=kontur_iyi, max_iterations=700))
        assert r.status_code == 200
        cfd = r.get_json()['cfd']
        assert cfd['max_iterations'] == 700
        assert cfd['iterations'] == 700
        assert cfd['residual_history']['n_total'] == 700
        assert cfd['converged'] is False

    def test_tam_sayili_kesirsiz_float_kabul(self, client, kontur_iyi):
        """JSON tarafı 700.0 gönderebilir (JS'te tamsayı ayrı tip değil);
        tam değerli float REDDEDİLMEZ."""
        r = _sessiz(client.post, UC, json=govde(
            nozzle_contour=kontur_iyi, max_iterations=700.0))
        assert r.status_code == 200
        assert r.get_json()['cfd']['max_iterations'] == 700

    def test_butce_ust_sinirda_bit_ayni_sonuc(self, client, kontur_iyi,
                                              yanit_iyi):
        """Bütçeyi AÇIKÇA varsayılana eşit vermek sonucu değiştirmemeli
        (bant üst ucu = çözücünün tavanı; ikinci bir tanım olsaydı burada
        ayrışırdı)."""
        from hrma.cfd.steady import DEFAULT_MAX_ITERS
        r = _sessiz(client.post, UC, json=govde(
            nozzle_contour=kontur_iyi,
            max_iterations=int(DEFAULT_MAX_ITERS)))
        assert r.status_code == 200
        cfd = r.get_json()['cfd']
        assert cfd['max_iterations_source'] == 'caller'
        assert cfd['iterations'] == yanit_iyi['cfd']['iterations']
        assert np.allclose(
            np.asarray(cfd['wall_pressure']['pressure_Pa'], dtype=float),
            np.asarray(yanit_iyi['cfd']['wall_pressure']['pressure_Pa'],
                       dtype=float), rtol=0, atol=0)
