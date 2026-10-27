# -*- coding: utf-8 -*-
"""ÖH Dalga-18 · kulvar bekci-cevirisi · aşama 1/1 — bekçi bekçileri.

Bu dosya ÜRÜN davranışını değil BEKÇİLERİN KENDİSİNİ savunur: ürünün
ADIYLA gösterdiği kilidin gerçekten var olduğunu, uç–panel sözleşme
envanterinin iki yönde de büyümediğini, referans dondurma aracının kirli
ağaçtan donmadığını.

Her iddia, savunduğu kusuru gördüğü TERS MUTASYONLA kırmızıya düştüğü
ölçülerek doğrulanmıştır (kanıt:
``docs/scofield/raw/OH/D18/bekci-cevirisi/a1/mutasyon.json``).

Kalemler: P10B3-04 (ürünün adıyla gösterdiği bekçi o dosyayı okumalı),
P13B2-08 (uç–panel sözleşme envanteri iki yönde de kilitli), P10B4-14
(bit-özdeşlik referansı kirli ağaçtan dondurulamaz), P13B1-09
(kendini kapatan bekçi — onarımı ``tests/test_release_notes_language.py``
içinde, buradaki iddia kapının geri gelmediğini sınar).
"""

import ast
import json
import re
from pathlib import Path

import pytest
from tests.support.kanit import kanit_gerekli


KOK = Path(__file__).resolve().parent.parent
TESTS_KOK = KOK / 'tests'


# ===========================================================================
# P10B3-04 — ürünün ADIYLA gösterdiği bekçi o dosyayı GERÇEKTEN okumalı
# ===========================================================================
#
# Ölçülen kusur (`once_p10b304.json`): ``hrma/run.py:18-20`` şu künyeyi
# taşıyor — "Taranacak port aralığı … tests/test_local_api_security.py bu
# iki dosyanın ayrışmasını yakalar." O dosya ``hrma/run.py``'yi HİÇ
# okumuyordu (0 atıf); yani ürünün gösterdiği kilit YOKTU.
#
# Bu, künye/beyanın çözüm sanılmasının saf hâlidir: ürün bir bekçiye
# ATIF yapıyor, atıf denetlenmiyor, bekçi de o dosyaya bakmıyor.
# Onarım ``tests/test_local_api_security.py::
# TestCorsWorksOnEveryLauncherPort::test_runner_port_range_matches_this_suite``
# ile yapıldı (kilit KURULDU); aşağıdaki iddia atfın kendisini sınar ve
# ürün ileride başka bir bekçiyi adıyla gösterirse onu da kapsar.

#: Künyesinde bekçi dosyası ADI geçen ürün kaynakları.
KUNYE_TARANAN_URUN_DOSYALARI = (
    'hrma/run.py',
)

_TEST_ATIF = re.compile(r'tests/(test_[A-Za-z0-9_]+)\.py')


def _urun_kunyesindeki_bekci_atiflari():
    """(ürün dosyası, atıf yapılan bekçi dosyası) çiftleri."""
    for rel in KUNYE_TARANAN_URUN_DOSYALARI:
        metin = (KOK / rel).read_text(encoding='utf-8')
        for ad in sorted(set(_TEST_ATIF.findall(metin))):
            yield rel, f'tests/{ad}.py'


class TestP10B304UrununGosterdigiBekciOkur:

    def test_kunyede_adi_gecen_bekci_dosyasi_vardir(self):
        eksik = [f'{u} -> {t}' for u, t in _urun_kunyesindeki_bekci_atiflari()
                 if not (KOK / t).exists()]
        assert not eksik, f'ürün var olmayan bekçi dosyasını gösteriyor: {eksik}'

    def test_kunyede_adi_gecen_bekci_o_urun_dosyasini_okur(self):
        """"Şu test bu ayrışmayı yakalar" diyen künye ÖLÇÜLÜR.

        Bekçi, gösterildiği ürün dosyasına ya yol olarak
        (``hrma/run.py``) ya da modül olarak (``hrma.run``) atıf
        yapmalıdır. Atıf yoksa künye bir dilekçedir.
        """
        yalan = []
        for urun, bekci in _urun_kunyesindeki_bekci_atiflari():
            yazi = (KOK / bekci).read_text(encoding='utf-8')
            modul = urun.replace('/', '.').removesuffix('.py')
            if urun not in yazi and modul not in yazi:
                yalan.append(f'{urun} künyesi {bekci} bekçisini gösteriyor '
                             f'ama o bekçi {urun} dosyasını hiç okumuyor')
        assert not yalan, yalan

    def test_port_araligi_uc_kaynakta_da_ayni(self):
        """Kilidin kendisi: run.py / launcher.py / bekçi aynı aralıkta.

        Bu iddia bilerek TEKRARDIR: onarım
        ``test_local_api_security.py``te yaşıyor, ama o dosya silinse ya
        da iddia gevşetilse bile ayrışma burada da kırmızı olur.
        """
        run_src = (KOK / 'hrma' / 'run.py').read_text(encoding='utf-8')
        araliklar = []
        for dugum in ast.walk(ast.parse(run_src)):
            if isinstance(dugum, ast.Assign) and any(
                    isinstance(h, ast.Name) and h.id == 'PORT_RANGE'
                    for h in dugum.targets):
                cagri = dugum.value
                assert isinstance(cagri, ast.Call), \
                    'PORT_RANGE artık range(...) literali değil'
                araliklar.append(tuple(a.value for a in cagri.args))
        assert araliklar == [(8080, 8091)], (
            f'hrma/run.py port aralığı değişti: {araliklar}')
        launcher = (KOK / 'packaging' / 'launcher.py').read_text(
            encoding='utf-8')
        assert 'range(8080, 8091)' in launcher, (
            'packaging/launcher.py aralığı hrma/run.py ile ayrıştı')


# ===========================================================================
# P13B1-09 — kendini kapatan bekçi geri gelmesin
# ===========================================================================
#
# Onarım ``tests/test_release_notes_language.py`` içinde: koruduğu
# regresyon gerçekleşince ATLAYAN ``skipif`` kapısı kaldırıldı, yerine
# adlı bir sözleşme iddiası kondu. Aşağıdaki iddia kapının geri
# gelmediğini sınar — bir bekçiyi "yamayı beklerken atla" diye
# kapatan desen, tam da kusur anında sessizleşir.

class TestP13B109KendiniKapatanBekci:

    def test_surum_notu_bekcisi_kendini_kapatmaz(self):
        yazi = (TESTS_KOK / 'test_release_notes_language.py').read_text(
            encoding='utf-8')
        agac = ast.parse(yazi)
        kapali = []
        for dugum in ast.walk(agac):
            if not isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for sus in dugum.decorator_list:
                metin = ast.unparse(sus)
                if 'skipif' in metin or metin.endswith('mark.skip'):
                    kapali.append(f'{dugum.name}: {metin[:80]}')
        assert not kapali, (
            'sürüm notu bekçisi yine koşullu atlamayla kapatılmış — kusur '
            f'anında sessizleşir: {kapali}')

    def test_dil_ayirma_sozlesmesi_adiyla_siniyor(self):
        """``split_notes_by_language`` bir SEÇENEK değil, sözleşmedir."""
        from hrma.utils import update_checker as uc
        assert hasattr(uc, 'split_notes_by_language')
        yazi = (TESTS_KOK / 'test_release_notes_language.py').read_text(
            encoding='utf-8')
        assert 'test_sunucu_dil_ayirma_yamasi_geri_alinamaz' in yazi, (
            'sözleşme iddiası kaldırılmış')


# ===========================================================================
# P13B2-08 — uç ⟷ panel sözleşme envanteri İKİ YÖNDE de kilitli
# ===========================================================================
#
# Ölçüm (P13 `B2-repro-12.py`, D18'de bu ağaca çevrilerek yeniden
# koşuldu -> `once_p13b208.json` / `sonra_p13b208.json`):
#
#   P13 (24 Ağu, taban)   D18 (bu ağaç)
#   ürün yüzünün çağırdığı rota      52          52
#     uç üzerinden bekçisi olan      35          45
#     uç üzerinden bekçisi OLMAYAN   17           7
#   testin postladığı, ürünün hiç
#     çağırmadığı rota (sayfa hariç) 15          18
#
# İki yön iki ayrı kusurdur:
#   (A) Kullanıcının FİİLEN bastığı 7 uç için uç düzeyinde tek bekçi yok
#       — o uçların davranışını hiçbir iddia tanımlamıyor.
#   (B) Ürünün hiç çağırmadığı 18 ucun davranışını YALNIZ test tanımlıyor
#       — test fail-open'ı şart koşarsa uç kalıcı fail-open olur
#       (P13B2-02'nin yapısal açıklaması).
#
# Bu kalem bir ÜRÜN kusuru değil, ENVANTER kusurudur; onarımı da
# envanterin kilitlenmesidir: listeler ADIYLA yazılır, BÜYÜMELERİ
# kırmızıdır (ÖK-22 — sağlıklı envanter gevşetilemez).

# ÖH D18 fix-8 (2 Eyl 2026): ürün yüzü tarayıcısı yalnız ``fetch('/…')`` /
# ``endpoint: '/…'`` / ``url: '/…'`` / ``action='/…'`` bitişik literalleri
# görüyordu; ``const ENDPOINT = '/api/fea/structural'`` gibi SABİTE atanıp
# ``fetch(ENDPOINT, …)`` ile çağrılan rotalar (fea_panel.js:55/1305) ürün
# yüzünde sayılmıyordu. D18 arayuz (525a4b6) şablondaki bitişik literali
# sökünce iki canlı rota 'yalnız test tanımlıyor' diye kırmızı düştü —
# tarayıcının kör noktasıydı, ürünün değil. Atama biçimi de tarandı.
_ROTA_DESENI = re.compile(
    r"""(?:fetch\(\s*|endpoint\s*:\s*|url\s*:\s*|action\s*=\s*"""
    r"""|\b[A-Za-z_][A-Za-z0-9_]*\s*=\s*)"""
    r"""[`'"](/[A-Za-z0-9_\-/\.\$\{\}]+)[`'"]""")

#: Sayfa rotaları: panel "çağırmaz", tarayıcı gezinir. İki yönde de sayılmaz.
SAYFA_ROTALARI = frozenset({'/', '/liquid', '/solid', '/hybrid', '/advanced',
                            '/launch_site', '/validation', '/cfd', '/fea'})
# '/simple', '/uzaytek' girdileri (ÖH D24 / OH-D23-12) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum

#: Sunucunun KENDİ ürettiği ve tarayıcıya verdiği rotalar. Ürün yüzü (şablon
#: + JS) bu yolları yazmaz, ``hrma/app.py`` yanıt gövdesinde üretir; bu yüzden
#: ürün-yüzü tarayıcısında görünmezler ama "sözleşmesini yalnız test yazıyor"
#: da DEĞİLDİRLER. Liste ADIYLA ve KANITIYLA tutulur; büyümesi kırmızıdır.
SUNUCUNUN_URETTIGI_ROTALAR = frozenset({
    # ``hrma/app.py:11763`` -> ``'/download/stl/' + _register_stl_download(...)``
    # (CAD ihracat yanıtı indirme bağlantısını böyle döndürür).
    '/download/stl/<filename>',
})

#: (A) Ürünün çağırdığı ama UÇ ÜZERİNDEN hiç bekçisi olmayan rotalar.
#: BÜYÜMESİ kırmızıdır; küçülmesi (bekçi eklenmesi) beklenen yöndür.
UC_BEKCISI_OLMAYAN_URUN_ROTALARI = frozenset({
    # fix-8 (2 Eyl 2026): tarayıcı atama biçimini görünce ZATEN ürün
    # rotası olan ama uç üzerinden hiç sınanmayan 5 rota göründü — ÖK-22:
    # envanter gevşetilmedi, ölçüm düzeltildi; borç ADIYLA sayılır
    # (OH-D18 kalemi: uç bekçileri yazılınca satır satır silinir).
    # ÖH D21 / OH-D18-01 — BEŞ SATIR SİLİNDİ (borç ödendi, envanter
    # GEVŞETİLMEDİ; ÖK-22 yönü korunur, liste DARALDI):
    # '/api/analysis/combustion-stability', '/api/fea/thermal', '/formulas',
    # '/hybrid', '/launch-site' — beşi de artık uç üzerinden sınanıyor
    # (``tests/test_d21_app_api_a1.py::TestOHD1801UcBekcileri``: adsız mod
    # reddi, motor sonucu olmadan termal hesap yapılmaması, üç ürün
    # sayfasının gerçekten açılması).
    # ÖH D21 aşama-2 / P16B1-14 + P16B1-15 — BİR SATIR DAHA SİLİNDİ
    # (liste yine DARALDI, gevşetilmedi): '/api/generate-3d' artık uç
    # üzerinden sınanıyor —
    # ``tests/test_d21_app_api_a2.py::TestCurutulenKalemlerKapaliKalir``
    # (boş gövdede çizim yapılmaması, negatif geometride çizim yapılmaması,
    # sağlıklı geometride çizimin sürmesi).
    # ÖH D31 fix-34a (14 Eylül 2026) — BİR SATIR DAHA SİLİNDİ (liste yine
    # DARALDI, gevşetilmedi): '/api/changelog' artık uç üzerinden
    # sınanıyor. ÖLÇÜLDÜ (``docs/scofield/raw/OH/D31/fix34/a/
    # d18_uc_haritasi.json``, fixture'ın KENDİ hesabıyla): ürün yüzü onu
    # HÂLÂ çağırıyor (``hrma/static/js/release_notes.js``) ama artık testi
    # de var (``tests/test_d30_app_api_uc_a2.py``), yani rota ``bekcisiz``
    # kümesinden ÇIKTI. Satır burada kalsaydı ÖLÜ olurdu ve ileride
    # açılacak bir borcu sessizce affederdi — ``test_envanter_curumez``
    # tam bunu söyledi (taban kaydı-14 kırmızısı).
    # '/api/solid-monte-carlo' — D18 app-api OH-D16-10 uç bekçisi geldi (fix-8'de listeden çıktı)
    '/api/tile/cache/clear',
    '/api/update/open-download',
    # ÖH D24 / OH-D23-12 — İKİ SATIR SİLİNDİ (liste DARALDI, ÖK-22 yönü
    # korunur): '/export_liquid_cad' ve '/export_solid_motor_cad' uç
    # üzerinden ZATEN sınanıyordu; testler rotayı ``parametrize``
    # listesinden alıyordu ve literal-kör tarayıcı görmüyordu. Borç
    # ödenmemişti, ölçüm kördü.
})

#: (B) Yalnız testin postladığı (ürün yüzünün hiç çağırmadığı) rotalar.
#: Bu uçların sözleşmesini tek başına test yazıyor; listenin BÜYÜMESİ
#: yeni bir "yalnız testin tanımladığı uç" demektir ve kırmızıdır.
YALNIZ_TESTIN_CAGIRDIGI_ROTALAR = frozenset({
    # v3.0.1 (Ayberk tur 1, kulvar K; 20 Eki 2026) — BORÇ KAYDI, AF DEĞİL.
    # Hibrit/katı/sıvı sayfalarının açılışta çağırdığı '/api/database-status'
    # yoklaması SÖKÜLDÜ: her makinede yanlışlıkla "NASA CEA / NIST WebBook
    # Offline" rozeti basıyordu (CEA kolu ağsız yerel tablo, NIST ayrıştırıcısı
    # gerçek HTML'le eşleşmiyordu; ikisi de hesaba sayı vermiyordu). Uç API
    # uyumu için kaldı ve dürüstleşti (NIST: connection connected/not_connected
    # + data_parsed ayrı; CEA: bağlantı kavramı yok); sözleşmesini artık
    # tests/test_v301_kaynak_baglanti.py yazıyor. Gerçek çözüm: tüketicisi
    # yoksa v3.1'de emekliye ayırmak.
    '/api/database-status',
    # fix-8: 8 rota (advanced-performance-analysis, analysis/wall-profile,
    # comparative-analysis, correlation-report, flow-analysis,
    # kinetic-efficiency, uncertainty-analysis, validation/upload-csv)
    # ürün JS'inde SABİTE atanmış hâlde çağrılıyordu; tarayıcı atama
    # biçimini görünce ürün yüzüne geçtiler, listeden çıktılar.
    # ÖH D21 aşama-2, ÖNCEKİ AŞAMA DENETİMİ — a1'in P15B1-05 bekçisi bu
    # iki API-only ucu ilk kez uç üzerinden sınadı ve envanter
    # güncellenmediği için bu test a1 commit'inden beri KIRMIZIYDI
    # (a1 raporundaki "19 geçti" iddiası bu iki satırdan ÖNCE ölçülmüş).
    # Ölçüldü (a2, 4 Eylül 2026): ``grep -rn 'chemical-species\|
    # get-fuel-properties' hrma/templates hrma/static`` -> BOŞ, yani ürün
    # yüzü ikisini de gerçekten hiç çağırmıyor; borç GERÇEKTİR.
    #
    # Satırlar bir AF DEĞİL, borç kaydıdır: uçların sözleşmesini bugün
    # yalnız test yazıyor. a1 bekçisi fail-CLOSED yönde (iki uçta birim
    # sözleşmesinin gövdede yayımlanması) olduğu için silinmedi; gerçek
    # çözüm ya ürün yüzüne bağlanmaları ya emekliye ayrılmalarıdır ve
    # ikisi de ``hrma/templates`` (arayuz kulvarı) sahasındadır.
    '/api/advanced-analysis',
    '/api/altitude-to-pressure',
    # ÖH D33-3 / fix-38c (ana model, 16 Eylül 2026) — BORÇ KAYDI, AF DEĞİL.
    # ÖLÇÜLDÜ: '/api/validate-fuel'in ürün yüzündeki TEK çağıranı, D33-KOLAY
    # arayuz-panel a1'in (a21b9419, OH-D32-11) söktüğü ÖLÜ "özel yakıt
    # karışımı" paneliydi. Panel bir kusurdu ve doğru sökülmüştür; uç ise
    # hrma/app.py:14480'de DURUYOR ve sözleşmesini artık yalnız testler
    # yazıyor. Bugün ürün yüzünde kalan tek iz YORUM satırlarıdır
    # (advanced.html:1516/3502/3506, i18n_advanced.js:558/561/1229 — gerçek
    # fetch çağrısı 0, ölçüldü).
    #
    # Bu satır ucu AFFETMEZ, borcu ADIYLA kaydeder: gerçek çözüm ya ucun
    # emekliye ayrılması ya da yeni bir ürün yolundan çağrılmasıdır. Uç
    # SİLME kararı ürün yüzeyini daraltır ve Berke'nin onayına bağlıdır
    # (OH-D33-36). Onay gelince bu satır ÇIKARILIR — test_envanter_curumez
    # ölü satırı zaten kırmızı yakar, yani kayıt kendini süpürür.
    '/api/validate-fuel',
    # ÖH D24 / OH-D23-12 — '/api/analysis/thermal-protection' SİLİNDİ:
    # ürün yüzü onu ``hrma/static/js/panels/thermal_panel.js`` üzerinden
    # gerçekten çağırıyor; eski tarayıcı somut yolu Flask kuralına
    # eşleyemediği için 'yalnız test' sanıyordu.
    '/api/cfd-analysis',
    '/api/chemical-species',
    '/api/get-fuel-properties',
    '/api/export-complete-zip',
    '/api/export-dxf',
    '/api/export-simulation',
    '/api/export-step',
    # ÖH V3 CAD · CADK D-T6-3 (14 Eki 2026) — BORÇ KAYDI, AF DEĞİL.
    # ÖLÇÜLDÜ: '/api/export-stl'in ürün yüzündeki TEK çağıranı
    # advanced.html ``exportMotorSTL`` idi ve hiçbir düğmeye/olaya bağlı
    # DEĞİLDİ (STL düğmesi ``exportSTL`` -> '/api/export-stl-zip');
    # bağlansaydı hibrit ``currentResults.motor`` ``port_diameter``
    # taşımadığı için her zaman 422 alırdı (kanit/t7/olcum/
    # export_stl_hibrit.txt). Ölü işlev söküldü (fix-38c '/api/validate-fuel'
    # emsali); uç API olarak DURUYOR ve sözleşmesini bugün yalnız testler
    # yazıyor. Uç silme kararı Berke'nindir (OH-D33-36); ürün bu ucu yeniden
    # çağırırsa test_envanter_curumez bu satırı ölü diye kırmızı yakar.
    '/api/export-stl',
    '/api/export-stl-zip',
    '/api/kinetic-analysis',
    # ÖH D24 / OH-D23-12 — YENİ GÖRÜNEN BORÇ (yeni borç DEĞİL, yeni
    # GÖRÜNEN borç): keskinleşen tarayıcı bu ucu ilk kez saydı. Ölçüldü
    # (``grep -rn 'professional-analysis' hrma/templates hrma/static``
    # -> 0 dosya): ürün yüzü onu gerçekten hiç çağırmıyor, sözleşmesini
    # bugün yalnız test yazıyor. Satır bir AF DEĞİL, borç kaydıdır.
    '/api/professional-analysis',
    # ÖH D31 fix-34a (14 Eylül 2026) — İKİ SATIR EKLENDİ; YENİ GÖRÜNEN
    # BORÇ (yeni borç DEĞİL). ÖLÇÜLDÜ (``a/d18_uc_haritasi.json``): ürün
    # yüzü ikisini de artık hiç çağırmıyor, sözleşmelerini bugün yalnız
    # test yazıyor (``/api/export-cad``: test_faz4_app_export,
    # test_z5s_govde_kapisi, test_z5s_ihracat_kapisi;
    # ``/api/generate-complete-package``: test_d18/d23/d24_app_api,
    # test_pdf_analysis, test_z5s_ihracat_kapisi).
    #
    # SÖKEN KALEM ADIYLA: ``896d2e83`` (ÖH D30 arayuz-panel a1, OH-D29-02
    # gölgeleme sökümü) ``app.js::generateCAD`` ve ``assertCadContent``
    # ÖLÜ kopyalarını söktü; iki ucun ürün-yüzü çağrısı YALNIZ o ölü
    # gövdedeydi (bugün dosyada kalan iki satır SÖKÜM NOTU yorumudur,
    # çağrı değil). Yani borç D30'dan önce de vardı — canlı yol
    # ``advanced.html`` satır içi sürümüdür ve ``/api/generate-3d``
    # çağırır — ölü kopya onu GİZLİYORDU. Envanter gevşetilmedi: iddia
    # yine tam küme eşitliğidir, yalnız tabanı ÖLÇÜLEN borca hizalar.
    #
    # ÖH D32 / ihracat a2 · OH-D31-02 — ÜRÜN KARARI VERİLDİ, im:
    # API-ONLY-KARAR-2627. İki uç 2.6.27'de ürün yüzüne BAĞLANMAZ ve
    # EMEKLİ EDİLMEZ: "yalnız API" olarak yaşarlar. Karar changelog
    # 2.6.27'ye ("Yalnız API olarak yaşayan iki uç") adıyla yazıldı ve
    # ``tests/test_d32_ihracat_a2.py`` ile bağlandı — o bekçi üç şeyi
    # birlikte tutar: rotalar DURUYOR (sessiz emeklilik kırmızı verir),
    # ürün yüzünde CANLI çağrı YOK (sessiz bağlama kırmızı verir) ve
    # beyan changelog'da ADIYLA duruyor. Bu satırlar bu yüzden artık
    # "karar bekleyen borç" değil, KARARIN kendisidir; envanter yine
    # gevşetilmedi (iddia tam küme eşitliği).
    '/api/export-cad',
    '/api/generate-complete-package',
})


def _app_rotalari():
    src = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')
    return set(re.findall(r"@app\.route\(\s*'([^']+)'", src))


# ---------------------------------------------------------------------------
# ÖH D24 · OH-D23-12 — SOMUT YOL -> FLASK KURALI EŞLEMESİ (İKİ TARAF DA)
#
# Kalem tarayıcının literal-körlüğünü ürün yüzünde DEĞİL testte gösteriyordu,
# ama ölçüm iki tarafın da aynı körlüğü taşıdığını gösterdi: ürün
# ``fetch('/api/export-pdf/summary')`` çağırıyor, Flask kuralı
# ``/api/export-pdf/<report_type>``; dizge eşitliği tutmadığı için rota
# "ürün çağırmıyor" sayılıyordu. Tek taraflı keskinleştirme, gerçekte canlı
# olan üç ucu ("export-pdf", "jobs", "tile") YALAN bir borç kaydına
# yazardı. Eşleme bu yüzden ORTAKTIR.
# ---------------------------------------------------------------------------


def _kural_esler(kural, parcalar):
    """Somut yol parçaları bu Flask kuralına uyuyor mu?"""
    k = [x for x in kural.split('/') if x != '']
    y = list(parcalar)
    i = 0
    for j, seg in enumerate(k):
        degisken = seg.startswith('<') and seg.endswith('>')
        if degisken and seg[1:-1].startswith('path:'):
            return j == len(k) - 1 and i < len(y)   # kuyruk yutar
        if i >= len(y):
            return False
        if not degisken and seg != y[i]:
            return False
        i += 1
    return i == len(y)


def _rotaya_cevir(ham, rotalar):
    """Üründe/testte geçen bir yolu, eşleştiği Flask kurallarına çevirir.

    Üç durum: (a) kural birebir aynı, (b) yol SOMUT ve kuralın değişken
    segmentlerine oturuyor (``/api/export-pdf/summary`` ->
    ``/api/export-pdf/<report_type>``), (c) yol bir ÖNEK
    (``/api/tile/`` ya da ``/api/export-pdf/${x}``) ve kuralın kalanı
    değişken segmentle başlıyor. Gelişigüzel önek eşlemesi YOKTUR: (c)
    yalnız değişken segmente denk gelirse kabul edilir.
    """
    if not ham.startswith('/'):
        return set()
    if ham in rotalar:
        return {ham}
    # Şablon yer tutucularını ('${x}', '{x}', ':x') tek segment sayarak at.
    temiz = re.sub(r'(\$\{[^}]*\}|\{[^}]*\}|:[A-Za-z_][A-Za-z0-9_]*)', '\x00', ham)
    parcalar = [x for x in temiz.split('/') if x != '']
    bulgu = set()
    if parcalar and '\x00' not in temiz:
        for r in rotalar:
            if _kural_esler(r, parcalar):
                bulgu.add(r)
        if bulgu:
            return bulgu
    # Yer tutuculu ya da eşleşmemiş yol: önek olarak dene.
    onek = ham.split('\x00')[0] if '\x00' in temiz else ham
    onek = temiz.split('\x00')[0]
    for r in rotalar:
        if r == onek:
            bulgu.add(r)
        elif r.startswith(onek) and r[len(onek):].startswith('<'):
            bulgu.add(r)
    return bulgu


def _rota_takimlari():
    """Aynı görünüm fonksiyonuna bağlı rota TAKIMLARI (alias kümeleri).

    ``@app.route('/api/combustion-stability')`` ve
    ``@app.route('/api/analysis/combustion-stability')`` AYNI fonksiyonu
    süslüyor; ürün ikincisini çağırıyorsa uç sınanıyor demektir. Takım
    bilgisi olmadan birincisi "sözleşmesini yalnız test yazıyor" diye
    YALAN bir borç kaydına düşerdi.
    """
    src = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')
    agac = ast.parse(src)
    takimlar = []
    for d in ast.walk(agac):
        if not isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        yollar = set()
        for sus in d.decorator_list:
            if (isinstance(sus, ast.Call)
                    and isinstance(sus.func, ast.Attribute)
                    and sus.func.attr == 'route'
                    and sus.args
                    and isinstance(sus.args[0], ast.Constant)
                    and isinstance(sus.args[0].value, str)):
                yollar.add(sus.args[0].value)
        if len(yollar) > 1:
            takimlar.append(frozenset(yollar))
    return takimlar


def _takim_genislet(kume):
    """Bir rota kümesini, alias kardeşleriyle birlikte döndürür."""
    genis = set(kume)
    for takim in _rota_takimlari():
        if genis & takim:
            genis |= takim
    return genis


def _urun_yuzunun_cagirdiklari(rotalar=None):
    """Ürün yüzünün (şablon + JS) çağırdığı rotalar.

    ÖH D24 / OH-D23-12: ham yol artık ``_rotaya_cevir`` ile Flask
    kuralına eşlenir — ``/api/export-pdf/summary`` çağrısı
    ``/api/export-pdf/<report_type>`` kuralını da işaretler. Ham yol da
    saklanır (eski davranış), çünkü rota olmayan yollar (statik dosya)
    başka iddialarda kullanılıyor.
    """
    if rotalar is None:
        rotalar = _app_rotalari()
    yollar = list((KOK / 'hrma' / 'templates').glob('*.html'))
    yollar += list((KOK / 'hrma' / 'static').rglob('*.js'))
    bulgu = {}
    for p in yollar:
        metin = p.read_text(encoding='utf-8', errors='replace')
        rel = str(p.relative_to(KOK))
        for rota in _ROTA_DESENI.findall(metin):
            bulgu.setdefault(rota, set()).add(rel)
            for kural in _rotaya_cevir(rota, rotalar):
                bulgu.setdefault(kural, set()).add(rel)
    return bulgu


# ---------------------------------------------------------------------------
# ÖH D24 · OH-D23-12 — ROTA ÇIKARIMI LİTERAL-KÖR OLMAZ
#
# Ölçülen kusur (once_ohd23_12.json): ``tests/**`` içindeki 3614
# ``.post()/.get()`` çağrısının ilk argümanı taranırken eski tarayıcı yalnız
# ``ast.Constant`` dizgesini sayıyordu. Rota gibi görünen 1169 çağrının
# 406'sı (365 değişken, 10 f-string, 10 birleştirme, 9 nitelik, 6 indeks,
# 3 diğer) GÖRÜNMÜYORDU. Bu, envanterin B yönünde (``yalniz_test``)
# fail-open olması demekti: sözleşmesini yalnız test yazan bir uç, testte
# rota bir DEĞİŞKENDEN geliyorsa envantere hiç girmiyordu.
#
# Aşağıdaki çözücü üç kaynaktan rota kurtarır ve hiçbirini tahmin etmez:
#   1. modül düzeyi dizge sabitleri (``UC = '/api/x'``),
#   2. ``@pytest.mark.parametrize`` literal listeleri ve fonksiyon içi
#      atamalar / ``for`` döngüsü literalleri,
#   3. STATİK ÖNEK taşıyan biçimlendirmeler (f-string, ``+``, ``%``,
#      ``.format()``) — önek yalnız Flask kuralının DEĞİŞKEN segmentine
#      denk gelen rotalarla eşleştirilir, gelişigüzel önek eşlemesi YOK.
#
# Çözülemeyen çağrı sessizce atılmaz: ``_cozulemeyen_rota_cagrilari()``
# onları dosya:satır ile sayar ve ``ÇÖZÜLEMEYEN_ROTA_ÇAĞRISI_TAVANI``
# büyümelerini yasaklar (ÖK-22 yönünde sıkılaştırma).
# ---------------------------------------------------------------------------

#: Çözülemeyen (statik önek bile vermeyen) rota çağrısı tavanı. ÖLÇÜLDÜ.
#: Yalnız AŞAĞI çekilir; büyümesi kör noktanın büyümesidir.
#:
#: ÖH D25 fix-23 (5 Eylül 2026): 84 -> 39. D24 birleşince ölçüm 87'ye çıkmıştı
#: (yeni üç kalem: ``test_d24_altyapi_a2.py:90``, ``test_d24_app_api_a2.py:42``,
#: ``test_materials_db.py:285``) ve bekçi kırmızı verdi. TAVAN YÜKSELTİLMEDİ;
#: kırmızının istediği yapıldı ve ÇÖZÜCÜ GENİŞLETİLDİ — iki ayrı kök:
#:   1. İstemci adı eşlemesi ALT DİZE idi ve liste tek harflik ``'c'``
#:      taşıyordu: ``rec.get(alan)``, ``cur.get(parca)``,
#:      ``app.view_functions.get(...)`` gibi 30 SÖZLÜK okuması kör nokta
#:      sayılıyordu (ölçüldü). Eşleşme sözcük düzeyine çekildi.
#:   2. Yardımcıya sarılmış rota çağrıları (``def _post(c, yol, govde)``)
#:      çözülmüyordu; parametreler artık çağrı yerindeki literallere
#:      bağlanıyor (``_yardimci_parametre_baglari``).
#: Ölçüm (8f30b6d + bu onarım): 39. Ürün envanteri de büyüdü: çözülen rota
#: sayısı ``_testin_cagirdiklari`` ile 125.
#:
#: ÖH D27 fix-26a (8 Eylül 2026): D26 birleşince ölçüm 40'a çıktı ve bekçi
#: kırmızı verdi. TAVAN YİNE YÜKSELTİLMEDİ; kırmızının istediği yapıldı ve
#: ÇÖZÜCÜ ÜÇÜNCÜ KEZ GENİŞLETİLDİ. Tek yeni kalem ölçüldü:
#: ``tests/test_d26_sivi_a1.py:220`` — ``a.get(k) != c.get(k)``, iki taraf da
#: ``duz(...)`` yardımcısının döndürdüğü DÜZ SÖZLÜK. Ad ölçütü sözcük
#: düzeyinde ``'c'`` ile eşleşiyor ve sözlük okuması HTTP isteği sayılıyordu;
#: yani D25'te kapatılan alt-dize körlüğünün TAM EŞLEŞME kardeşi. Onarım:
#: ``_istemci_olmayan_yerel_adlar`` — alıcı bu fonksiyonda istemci
#: ÜRETEMEYEN bir değere (sözlük/liste/literal/yerel yardımcı çağrısı,
#: döngü değişkeni) bağlanmışsa ad ölçütü düşer; HTTP anahtar kelimesi ve
#: ``'/'`` literali ölçütleri yerinde kalır (fail-closed: çözülemeyen ifade
#: hâlâ istemci sayılır). Ölçüm bu onarımla 40 -> 39; çözülen rota sayısı
#: DEĞİŞMEDİ (125), yani genişleme gerçek bir rota çağrısını yutmadı.
#:
#: ÖH V3 taban-b (14 Eki 2026): 12 Eki tabanında ölçüm 43-44'e çıkmıştı
#: (yeni beş kalem: ``test_d15_ui_paneller_a2.py:824``,
#: ``test_d35_onemli_kati_cad_a1.py:65``, ``test_d37_sahte_veri_b1.py``
#: 343/346, ``test_harita_ag_kapisi.py:148``). TAVAN YÜKSELTİLMEDİ;
#: ÇÖZÜCÜ DÖRDÜNCÜ KEZ GENİŞLETİLDİ, üç kesin kalıpla (hiçbiri tahmin
#: etmez, belirsizde boş döner):
#:   1. ``UC[tip]`` — modülde (ya da ``from tests.X import``) TEK KEZ
#:      atanmış literal sözlüğün TÜM değerleri rota ise çözülür;
#:   2. ``'/api/somut/yol' + sorgu`` — sağ işlenenin bütün değerleri
#:      sorgu dizgesiyse (``''``/``'?…'``) sol somut yol kurala eşlenir;
#:   3. çok sütunlu ``parametrize`` listesi modül düzeyinde ADLA
#:      verilmişse (``_PANEL_GOVDELERI``) ad o literale çözülür.
#: Ölçüm 44 -> 23; çözülen 21 kalemin hedef kuralları tek tek dökümlü
#: (``docs/scofield/raw/OH/V3/taban/b/rota_cozulen_21.txt``). Tavan
#: ölçüme indirildi (yastık yok, ``test_tavan_olculen_sayiyla_hizali``).
COZULEMEYEN_ROTA_CAGRISI_TAVANI = 23


#: ``sorted(X)`` / ``list(X)`` / ``tuple(X)`` gibi sarmalayıcılar dizge
#: kümesini DEĞİŞTİRMEZ; içi çözülür.
_SEFFAF_SARMALAYICILAR = ('sorted', 'list', 'tuple', 'set', 'frozenset',
                          'reversed')


def _dizgeler(dugum, kapsam=None):
    """Düğümden çıkarılabilen KESİN dizge değerleri (yoksa boş küme).

    ``kapsam`` verilirse ``ast.Name`` düğümleri de o sözlükten çözülür —
    ``@parametrize('page', sorted(PAGE_MOTOR_TYPE))`` gibi, listesi modül
    düzeyinde duran yaygın kalıbı görmek için gerekli.
    """
    if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
        return {dugum.value}
    if isinstance(dugum, (ast.Tuple, ast.List, ast.Set)):
        bulgu = set()
        for e in dugum.elts:
            bulgu |= _dizgeler(e, kapsam)
        return bulgu
    if isinstance(dugum, ast.Dict):
        bulgu = set()
        for anahtar in dugum.keys:
            if anahtar is not None:
                bulgu |= _dizgeler(anahtar, kapsam)
        return bulgu
    if isinstance(dugum, ast.Name) and kapsam:
        return set(kapsam.get(dugum.id, ()))
    if (isinstance(dugum, ast.Call) and isinstance(dugum.func, ast.Name)
            and dugum.func.id in _SEFFAF_SARMALAYICILAR and dugum.args):
        return _dizgeler(dugum.args[0], kapsam)
    return set()


def _statik_onek(dugum):
    """Biçimlendirilmiş bir ifadenin DEĞİŞMEYEN baş kısmı ('' ise yok).

    ``f'/api/x/{m}'`` -> ``'/api/x/'``; ``'/api/x/' + m`` -> ``'/api/x/'``;
    ``'/api/x/%s' % m`` -> ``'/api/x/'``; ``'/api/x/{}'.format(m)`` aynı.
    """
    if isinstance(dugum, ast.JoinedStr):
        ilk = dugum.values[0] if dugum.values else None
        if isinstance(ilk, ast.Constant) and isinstance(ilk.value, str):
            return ilk.value
        return ''
    if isinstance(dugum, ast.BinOp) and isinstance(dugum.op, ast.Add):
        return _statik_onek(dugum.left) or (
            dugum.left.value
            if isinstance(dugum.left, ast.Constant)
            and isinstance(dugum.left.value, str) else '')
    if isinstance(dugum, ast.BinOp) and isinstance(dugum.op, ast.Mod):
        sol = dugum.left
        if isinstance(sol, ast.Constant) and isinstance(sol.value, str):
            return sol.value.split('%')[0]
        return ''
    if (isinstance(dugum, ast.Call)
            and isinstance(dugum.func, ast.Attribute)
            and dugum.func.attr == 'format'
            and isinstance(dugum.func.value, ast.Constant)
            and isinstance(dugum.func.value.value, str)):
        return dugum.func.value.value.split('{')[0]
    return ''


def _parametrize_degerleri(fonk, dis_kapsam=None, modul_dugumleri=None):
    """``@pytest.mark.parametrize`` süslerinden ad -> dizge kümesi.

    ÖH V3 taban-b: değer listesi modül düzeyinde ADLA verilmişse
    (``@parametrize('panel,uc,govde', _PANEL_GOVDELERI)``) ad, o modülde
    TEK KEZ atanmış literal liste/demet düğümüne çözülür
    (``modul_dugumleri``); çözülemezse eskisi gibi boş kalır.
    """
    kapsam = {}
    for sus in fonk.decorator_list:
        if not isinstance(sus, ast.Call):
            continue
        ad = sus.func
        while isinstance(ad, ast.Attribute):
            if ad.attr == 'parametrize':
                break
            ad = ad.value
        if not (isinstance(ad, ast.Attribute) and ad.attr == 'parametrize'):
            continue
        if len(sus.args) < 2:
            continue
        adlar = sus.args[0]
        if not (isinstance(adlar, ast.Constant)
                and isinstance(adlar.value, str)):
            continue
        sutunlar = [a.strip() for a in adlar.value.split(',') if a.strip()]
        deger_dugumu = sus.args[1]
        if (isinstance(deger_dugumu, ast.Name) and modul_dugumleri
                and deger_dugumu.id in modul_dugumleri):
            deger_dugumu = modul_dugumleri[deger_dugumu.id]
        if len(sutunlar) == 1:
            kapsam.setdefault(sutunlar[0], set())
            kapsam[sutunlar[0]] |= _dizgeler(deger_dugumu, dis_kapsam)
            continue
        if not isinstance(deger_dugumu, (ast.Tuple, ast.List)):
            continue
        for satir in deger_dugumu.elts:
            if not isinstance(satir, (ast.Tuple, ast.List)):
                continue
            for i, hucre in enumerate(satir.elts):
                if i < len(sutunlar):
                    kapsam.setdefault(sutunlar[i], set())
                    kapsam[sutunlar[i]] |= _dizgeler(hucre, dis_kapsam)
    return kapsam


def _yerel_kapsam(fonk, dis_kapsam=None, modul_dugumleri=None):
    """Fonksiyon gövdesindeki atama / döngü literallerinden ad -> dizgeler."""
    kapsam = {}
    for d in ast.walk(fonk):
        if isinstance(d, ast.Assign):
            for hedef in d.targets:
                if isinstance(hedef, ast.Name):
                    kapsam.setdefault(hedef.id, set())
                    kapsam[hedef.id] |= _dizgeler(d.value, dis_kapsam)
        elif isinstance(d, ast.For) and isinstance(d.target, ast.Name):
            kapsam.setdefault(d.target.id, set())
            kapsam[d.target.id] |= _dizgeler(d.iter, dis_kapsam)
    for ad, degerler in _parametrize_degerleri(
            fonk, dis_kapsam, modul_dugumleri).items():
        kapsam.setdefault(ad, set())
        kapsam[ad] |= degerler
    return kapsam


def _modul_kapsami(agac):
    kapsam = {}
    for d in agac.body:
        if isinstance(d, ast.Assign):
            for hedef in d.targets:
                if isinstance(hedef, ast.Name):
                    kapsam.setdefault(hedef.id, set())
                    kapsam[hedef.id] |= _dizgeler(d.value, kapsam)
    return kapsam


def _modul_dugumleri(agac):
    """Modül düzeyinde TEK KEZ atanmış literal liste/demet/sözlük düğümleri.

    ÖH V3 taban-b (OH-D23-12 kör noktası, dördüncü genişleme). İki kez
    atanan ad belirsizdir ve DÜŞÜRÜLÜR (fail-closed: tahmin yok).
    """
    sayac = {}
    dugumler = {}
    for d in agac.body:
        if not isinstance(d, ast.Assign):
            continue
        for hedef in d.targets:
            if isinstance(hedef, ast.Name):
                sayac[hedef.id] = sayac.get(hedef.id, 0) + 1
                if isinstance(d.value, (ast.List, ast.Tuple, ast.Dict)):
                    dugumler[hedef.id] = d.value
    return {ad: dugum for ad, dugum in dugumler.items() if sayac[ad] == 1}


def _ithal_edilen_dugumler(agac):
    """``from tests.<modül> import AD`` ile gelen modül düzeyi literaller.

    Yalnız depo içi ``tests.`` modülleri (mutlak ithal) okunur; dosya
    okunamazsa ad çözülmez (fail-closed).
    """
    bulgu = {}
    for d in agac.body:
        if not (isinstance(d, ast.ImportFrom) and d.level == 0 and d.module
                and d.module.startswith('tests.')):
            continue
        yol = KOK.joinpath(*d.module.split('.')).with_suffix('.py')
        try:
            kaynak = ast.parse(yol.read_text(encoding='utf-8'))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        uzak = _modul_dugumleri(kaynak)
        for a in d.names:
            if a.name in uzak:
                bulgu[a.asname or a.name] = uzak[a.name]
    return bulgu


def _sozluk_dugumleri(agac):
    """Ad -> literal sözlük düğümü (modülün kendisi + ``tests.`` ithalleri)."""
    bulgu = {ad: dg for ad, dg in _ithal_edilen_dugumler(agac).items()
             if isinstance(dg, ast.Dict)}
    bulgu.update({ad: dg for ad, dg in _modul_dugumleri(agac).items()
                  if isinstance(dg, ast.Dict)})
    return bulgu


def _altsimge_degerleri(arg, sozlukler):
    """``UC[tip]`` -> literal sözlüğün TÜM değerleri.

    Değerlerden biri dizge sabiti değilse boş küme döner (fail-closed):
    hangi anahtarın seçildiği bilinmediği için kümenin TAMAMI rota olmak
    zorundadır.
    """
    if not (isinstance(arg, ast.Subscript) and isinstance(arg.value, ast.Name)):
        return set()
    sozluk = sozlukler.get(arg.value.id)
    if sozluk is None or not sozluk.values:
        return set()
    degerler = set()
    for anahtar, deger in zip(sozluk.keys, sozluk.values):
        if anahtar is None or not (isinstance(deger, ast.Constant)
                                   and isinstance(deger.value, str)):
            return set()
        degerler.add(deger.value)
    return degerler


def _sorgu_ekli_somut_yol(arg, kapsam):
    """``'/api/tile/a/5/10/5' + sorgu`` -> sol SOMUT yol.

    Yalnız sağ işlenenin bütün değerleri sorgu dizgesiyse (``''`` ya da
    ``'?'`` ile başlayan) kabul edilir; yol segmenti ekleyebilecek bir
    sağ taraf kabul EDİLMEZ (statik önek yolu o durumu ayrıca dener).
    """
    if not (isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add)):
        return ''
    sol, sag = arg.left, arg.right
    if not (isinstance(sol, ast.Constant) and isinstance(sol.value, str)
            and sol.value.startswith('/')):
        return ''
    if isinstance(sag, ast.Name):
        degerler = set(kapsam.get(sag.id, ()))
    elif isinstance(sag, ast.Constant) and isinstance(sag.value, str):
        degerler = {sag.value}
    else:
        return ''
    if degerler and all(isinstance(x, str) and (x == '' or x.startswith('?'))
                        for x in degerler):
        return sol.value
    return ''


def _yardimci_parametre_baglari(agac, modul):
    """Modüldeki yardımcıların PARAMETRELERİNE bağlanan dizgeler.

    ÖH D25 fix-23 — GERÇEK KÖR NOKTA. Testler rota çağrısını sık sık kendi
    yardımcılarına sarar::

        def _post(c, yol, govde):
            return c.post(yol, json=govde)      # <- ``yol`` çözülemiyordu

        _post(istemci, '/api/x', {...})         # <- rota BURADA literal

    Çağrının kendisi literal görmediği için uç envantere girmiyor, kör
    nokta listesi de büyüyordu. Bağlama KESİNDİR ve tahmin içermez: yalnız
    modül düzeyinde tanımlı bir fonksiyon, aynı modülde ADIYLA çağrılıyorsa
    ve o konumdaki argüman literal bir dizgeye çözülüyorsa parametreye
    yazılır. Çağrı bulunamazsa parametre boş kalır (fail-closed: çözülemedi
    sayılır, uydurma rota ÜRETİLMEZ).
    """
    tanimlar = {d.name: d for d in agac.body
                if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))}
    baglar = {ad: {} for ad in tanimlar}
    for cagri in ast.walk(agac):
        if not (isinstance(cagri, ast.Call)
                and isinstance(cagri.func, ast.Name)
                and cagri.func.id in tanimlar):
            continue
        fonk = tanimlar[cagri.func.id]
        parametreler = [a.arg for a in fonk.args.args]
        for i, arg in enumerate(cagri.args):
            if i >= len(parametreler):
                break
            degerler = _dizgeler(arg, modul)
            if degerler:
                baglar[fonk.name].setdefault(parametreler[i], set())
                baglar[fonk.name][parametreler[i]] |= degerler
        for kw in cagri.keywords:
            if kw.arg and kw.arg in parametreler:
                degerler = _dizgeler(kw.value, modul)
                if degerler:
                    baglar[fonk.name].setdefault(kw.arg, set())
                    baglar[fonk.name][kw.arg] |= degerler
    return baglar


def _fonksiyon_kapsamlari(agac):
    """(çağrı düğümü -> o çağrıyı saran kapsam sözlüğü) eşlemesi."""
    modul = _modul_kapsami(agac)
    baglar = _yardimci_parametre_baglari(agac, modul)
    dugumler = _modul_dugumleri(agac)
    eslesme = {}
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kapsam = dict(modul)
            for ad, degerler in _yerel_kapsam(d, modul, dugumler).items():
                kapsam.setdefault(ad, set())
                kapsam[ad] = set(kapsam[ad]) | degerler
            # Çağrı yerlerinden bağlanan parametreler (yardımcı sarmalayıcı).
            for ad, degerler in baglar.get(d.name, {}).items():
                kapsam.setdefault(ad, set())
                kapsam[ad] = set(kapsam[ad]) | degerler
            for ic in ast.walk(d):
                if isinstance(ic, ast.Call):
                    eslesme[id(ic)] = kapsam
    return modul, eslesme


def _onekten_rotalar(onek, rotalar):
    """Statik önekle GERÇEKTEN eşleşen Flask kuralları.

    Eşleşme yalnız şu iki durumda kabul edilir: kural önekle birebir aynı,
    ya da kuralın kalanı bir DEĞİŞKEN segmentiyle (``<``) başlıyor. Böylece
    ``/api/export-`` gibi bir önek ``/api/export-stl-zip``i YUTMAZ.
    """
    if not onek.startswith('/'):
        return set()
    bulgu = set()
    for r in rotalar:
        if r == onek:
            bulgu.add(r)
        elif r.startswith(onek) and r[len(onek):].startswith('<'):
            bulgu.add(r)
    return bulgu


#: HTTP istemcisi olduğu ADINDAN anlaşılan alıcılar. Eşleşme SÖZCÜK
#: düzeyindedir (aşağıya bakın), alt dize değil.
_ISTEMCI_ADLARI = ('client', 'c', 'istemci', 'session', 'requests', 'app',
                   'cli', 'tc')
#: Yalnız HTTP çağrısında geçen anahtar kelimeler.
_ISTEK_ANAHTARLARI = ('json', 'data', 'headers', 'query_string', 'follow_redirects',
                      'content_type', 'files', 'params')


def _istemci_uretiyor_mu(deger):
    """Bu ifade bir HTTP istemcisi ÜRETEBİLİR mi?

    Çözemediğimizde ``True`` döneriz (fail-closed): tanımadığımız bir
    ifadeye "istemci değil" diyip gerçek bir rota çağrısını kör noktadan
    düşürmek, yanlış isabeti tolere etmekten kötüdür.
    """
    if deger is None:
        return True
    if isinstance(deger, (ast.Dict, ast.DictComp, ast.ListComp,
                          ast.SetComp, ast.GeneratorExp, ast.List,
                          ast.Set, ast.Tuple, ast.JoinedStr)):
        return False
    if isinstance(deger, ast.Constant):
        return False
    try:
        metin = ast.unparse(deger)
    except Exception:                                 # pragma: no cover
        return True
    kucuk = metin.lower()
    if 'client' in kucuk or 'istemci' in kucuk or 'session' in kucuk:
        return True
    if isinstance(deger, ast.Call) and isinstance(deger.func, ast.Name):
        # Yerel yardımcıya yapılan çağrı (``duz(regen)``): istemci üretmez.
        return False
    return True


def _hedef_adlari(hedef):
    if isinstance(hedef, ast.Name):
        yield hedef.id
    elif isinstance(hedef, (ast.Tuple, ast.List)):
        for e in hedef.elts:
            yield from _hedef_adlari(e)
    elif isinstance(hedef, ast.Starred):
        yield from _hedef_adlari(hedef.value)


def _istemci_olmayan_yerel_adlar(fonksiyon):
    """Fonksiyon gövdesinde İSTEMCİ OLMAYAN bir değere bağlanan adlar.

    ÖH D27 fix-26a — OH-D23-12 kör noktasının ölçülen üçüncü kökü.
    ``_ISTEMCI_ADLARI`` tek harflik ``'c'`` taşıyor (Flask sözleşmesinde
    yaygın), bu yüzden ``c.get(k)`` biçimindeki HER çağrı — ``c`` yerel bir
    SÖZLÜK olsa bile — HTTP isteği sayılıyordu. ÖLÇÜLDÜ (taban 8abbe822):
    ``tests/test_d26_sivi_a1.py:220`` (``a.get(k) != c.get(k)``, iki taraf da
    ``duz(...)`` yardımcısının döndürdüğü düz sözlük) kör-nokta listesine
    girdi ve tavanı 39 -> 40'a çıkardı.

    Ölçüt: ad bu fonksiyonda bir değere BAĞLANIYORSA ve bağlandığı değer
    istemci üretemiyorsa (sözlük/liste/literal/yerel yardımcı çağrısı),
    ad ölçütü o çağrı için DÜŞER. Diğer iki ölçüt (HTTP anahtar kelimesi,
    ``'/'`` ile başlayan literal) yerinde kalır; yani gerçek bir rota
    çağrısı adı ne olursa olsun yakalanmaya devam eder.
    """
    adlar = set()
    for d in ast.walk(fonksiyon):
        if isinstance(d, ast.Assign):
            for hedef in d.targets:
                if (isinstance(hedef, (ast.Tuple, ast.List))
                        and isinstance(d.value, (ast.Tuple, ast.List))
                        and len(hedef.elts) == len(d.value.elts)):
                    for h, v in zip(hedef.elts, d.value.elts):
                        if not _istemci_uretiyor_mu(v):
                            adlar.update(_hedef_adlari(h))
                elif not _istemci_uretiyor_mu(d.value):
                    adlar.update(_hedef_adlari(hedef))
        elif isinstance(d, ast.AnnAssign) and d.target is not None:
            if not _istemci_uretiyor_mu(d.value):
                adlar.update(_hedef_adlari(d.target))
        elif isinstance(d, (ast.For, ast.AsyncFor)):
            # Döngü değişkeni bir istemci DEĞİLDİR (ad ne olursa olsun).
            adlar.update(_hedef_adlari(d.target))
        elif isinstance(d, ast.comprehension):
            adlar.update(_hedef_adlari(d.target))
    return adlar


def _sozluk_alicilari(agac):
    """(çağrı düğümü -> o kapsamda istemci OLMAYAN adlar) eşlemesi."""
    eslesme = {}
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
            adlar = _istemci_olmayan_yerel_adlar(d)
            if not adlar:
                continue
            for ic in ast.walk(d):
                if isinstance(ic, ast.Call):
                    eslesme[id(ic)] = adlar
    return eslesme


def _istemci_cagrisi_mi(cagri, sozluk_adlari=()):
    """``.get``/``.post`` bir HTTP isteği mi, yoksa ``dict.get`` mi?

    Ayrım şart: ``hf.get(k, '')`` gibi sözlük okumaları rota çağrısı
    DEĞİLDİR ve kör-nokta sayımını şişirirse tavan anlamsızlaşır.
    Ölçüt üç yoldan biri: (a) alıcı adı istemci gibi, (b) çağrıda HTTP
    anahtar kelimesi var, (c) ilk argüman '/' ile başlayan literal.
    """
    alici = cagri.func.value
    ad = ''
    if isinstance(alici, ast.Name):
        ad = alici.id
    elif isinstance(alici, ast.Attribute):
        ad = alici.attr
    elif isinstance(alici, ast.Call):
        ic = alici.func
        ad = ic.attr if isinstance(ic, ast.Attribute) else getattr(ic, 'id', '')
    # ÖH D25 fix-23 — ALT DİZE DEĞİL SÖZCÜK (kör-nokta şişmesinin kökü).
    # Eski satır ``any(im in ad.lower() for im in _ISTEMCI_ADLARI)`` idi ve
    # liste tek harflik ``'c'`` içeriyordu: içinde 'c' geçen HER alıcı adı
    # HTTP istemcisi sayılıyordu. ÖLÇÜLDÜ (8f30b6d, 87 kalemlik kör-nokta
    # listesi): 30 kalem sözlük okumasıydı — ``rec.get(alan)``,
    # ``sayfalar.CANLI_READY_SATIRLAR.get(ad)``,
    # ``app.view_functions.get(kural.endpoint)``, ``cur.get(parca)`` … Yani
    # tavanın üçte biri HTTP'yle ilgisi olmayan çağrılardan geliyordu ve
    # sınıfın kendi docstring'i ("kör-nokta sayımını şişirirse tavan
    # anlamsızlaşır") çiğneniyordu. Ad artık sözcüklerine ayrılır
    # ('view_functions' -> {'view','functions'}) ve TAM eşleşme aranır;
    # 'test_client', 'flask_client', 'self.client' gibi bileşik adlar
    # sözcük eşleşmesiyle YİNE tanınır.
    #
    # ÖH D27 fix-26a — ÜÇÜNCÜ kök: ad SÖZCÜK düzeyinde eşleşse bile, alıcı
    # bu fonksiyonda istemci OLMAYAN bir değere bağlanmışsa ad ölçütü
    # düşer (``a, c = duz(regen), duz(film)`` -> ``c.get(k)``). Diğer iki
    # ölçüt yerinde kalır.
    if not (isinstance(alici, ast.Name) and alici.id in sozluk_adlari):
        if set(re.split(r'[^a-z0-9]+', ad.lower())) & set(_ISTEMCI_ADLARI):
            return True
    if any(kw.arg in _ISTEK_ANAHTARLARI for kw in cagri.keywords if kw.arg):
        return True
    ilk = cagri.args[0]
    return (isinstance(ilk, ast.Constant) and isinstance(ilk.value, str)
            and ilk.value.startswith('/'))


def _rota_cagrilari(agac, yalniz_istemci=False):
    """Modüldeki ``.post()/.get()`` çağrılarını verir."""
    sozlukler = _sozluk_alicilari(agac) if yalniz_istemci else {}
    for d in ast.walk(agac):
        if (isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr in ('post', 'get')
                and d.args):
            if yalniz_istemci and not _istemci_cagrisi_mi(
                    d, sozlukler.get(id(d), ())):
                continue
            yield d


def _testin_cagirdiklari(rotalar=None):
    """Rota -> onu çağıran test dosyaları.

    ÖH D24 / OH-D23-12: literal dizgeye ek olarak değişken, f-string, ``+``,
    ``%`` ve ``.format()`` biçimleri de çözülür. Çözüm KESİNDİR: değişken
    ancak literal bir kaynağa (modül sabiti, ``parametrize`` listesi, yerel
    atama, ``for`` literali) bağlanabiliyorsa kullanılır; statik önek ancak
    Flask kuralının değişken segmentine denk geliyorsa rotaya çevrilir.
    """
    if rotalar is None:
        rotalar = _app_rotalari()
    bulgu = {}
    for p in sorted(TESTS_KOK.rglob('test_*.py')):
        try:
            agac = ast.parse(p.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        modul, kapsamlar = _fonksiyon_kapsamlari(agac)
        sozlukler = _sozluk_dugumleri(agac)
        rel = str(p.relative_to(KOK))
        for cagri in _rota_cagrilari(agac):
            arg = cagri.args[0]
            kapsam = kapsamlar.get(id(cagri), modul)
            adaylar = set()
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                adaylar = {arg.value}
            elif isinstance(arg, ast.Name):
                adaylar = set(kapsam.get(arg.id, ()))
            elif isinstance(arg, ast.Subscript):
                adaylar = _altsimge_degerleri(arg, sozlukler)
            else:
                onek = _statik_onek(arg)
                if onek:
                    adaylar = _onekten_rotalar(onek, rotalar)
                somut = _sorgu_ekli_somut_yol(arg, kapsam)
                if somut:
                    adaylar = set(adaylar) | {somut}
            for aday in adaylar:
                if not (isinstance(aday, str) and aday.startswith('/')):
                    continue
                bulgu.setdefault(aday, set()).add(rel)
                for kural in _rotaya_cevir(aday, rotalar):
                    bulgu.setdefault(kural, set()).add(rel)
    return bulgu


def _cozulemeyen_rota_cagrilari():
    """Rota gibi görünüp ÇÖZÜLEMEYEN çağrılar (dosya:satır listesi).

    "Rota gibi görünmek" ölçütü dar tutuldu: argüman ne literal ne de
    literale bağlanabilen bir ad; buna karşılık çağrı bir istemci üzerinde
    yapılıyor ve statik öneki de yok. Bu liste kör noktanın KENDİSİDİR;
    tavanı yalnız aşağı çekilir.
    """
    kalanlar = []
    rotalar = _app_rotalari()
    for p in sorted(TESTS_KOK.rglob('test_*.py')):
        try:
            agac = ast.parse(p.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        modul, kapsamlar = _fonksiyon_kapsamlari(agac)
        sozlukler = _sozluk_dugumleri(agac)
        rel = str(p.relative_to(KOK))
        for cagri in _rota_cagrilari(agac, yalniz_istemci=True):
            arg = cagri.args[0]
            kapsam = kapsamlar.get(id(cagri), modul)
            if isinstance(arg, ast.Constant):
                continue
            # ÖH V3 taban-b: ``UC[tip]`` — sözlüğün HER değeri gerçek bir
            # Flask kuralına çözülüyorsa çözülmüştür (biri bile çözülmezse
            # kör nokta sayılır).
            degerler = _altsimge_degerleri(arg, sozlukler)
            if degerler and all(d.startswith('/') and _rotaya_cevir(d, rotalar)
                                for d in degerler):
                continue
            somut = _sorgu_ekli_somut_yol(arg, kapsam)
            if somut and _rotaya_cevir(somut, rotalar):
                continue
            if isinstance(arg, ast.Name):
                degerler = kapsam.get(arg.id, ())
                if any(str(d).startswith('/') for d in degerler):
                    continue
                if degerler:
                    continue          # literal ama rota değil
                kalanlar.append('%s:%d (%s)' % (rel, cagri.lineno, arg.id))
                continue
            onek = _statik_onek(arg)
            if onek.startswith('/') and _onekten_rotalar(onek, rotalar):
                continue
            if onek and not onek.startswith('/'):
                continue              # rota değil (ör. dizge birleştirme)
            kalanlar.append('%s:%d (%s)'
                            % (rel, cagri.lineno, type(arg).__name__))
    return kalanlar


@pytest.fixture(scope='module')
def akis_haritasi():
    rotalar = _app_rotalari()
    urun = _urun_yuzunun_cagirdiklari(rotalar)
    test = _testin_cagirdiklari(rotalar)
    # ÖH D24 / OH-D23-12: alias kardeşler birlikte sayılır (aynı görünüm
    # fonksiyonu). Ürün alias'lardan BİRİNİ çağırıyorsa uç çağrılmıştır.
    urun = dict(urun)
    for kural in _takim_genislet({u for u in urun if u in rotalar}):
        urun.setdefault(kural, set()).add('<alias kardeşi>')
    test = dict(test)
    for kural in _takim_genislet({u for u in test if u in rotalar}):
        test.setdefault(kural, set()).add('<alias kardeşi>')
    urun_uclari = sorted(u for u in urun if u in rotalar)
    return {
        'rotalar': rotalar,
        'urun_uclari': urun_uclari,
        'bekcisiz': sorted(u for u in urun_uclari if u not in test),
        'yalniz_test': sorted(
            u for u in test
            if u in rotalar and u not in urun and u not in SAYFA_ROTALARI
            and u not in SUNUCUNUN_URETTIGI_ROTALAR),
    }


class TestP13B208UcPanelEnvanteri:

    def test_envanter_bosalmadi(self, akis_haritasi):
        """Süzgeç kırılırsa iki liste de boşalır ve iddia totolojiye döner."""
        assert len(akis_haritasi['rotalar']) >= 90, (
            f"app.py rota süzgeci kırık: {len(akis_haritasi['rotalar'])}")
        assert len(akis_haritasi['urun_uclari']) >= 45, (
            'ürün yüzü rota süzgeci kırık: '
            f"{len(akis_haritasi['urun_uclari'])}")

    def test_uc_bekcisi_olmayan_urun_rotasi_buyumez(self, akis_haritasi):
        """Kullanıcının bastığı yeni bir uç bekçisiz eklenemez (ÖK-22)."""
        yeni = sorted(set(akis_haritasi['bekcisiz'])
                      - UC_BEKCISI_OLMAYAN_URUN_ROTALARI)
        assert not yeni, (
            'ürün yüzü uç üzerinden hiç sınanmayan YENİ rota çağırıyor; '
            'ya uç bekçisi yazılır ya envanter gerekçeyle güncellenir: '
            f'{yeni}')

    def test_yalniz_testin_tanimladigi_uc_buyumez(self, akis_haritasi):
        """Sözleşmesini yalnız testin yazdığı yeni uç eklenemez.

        P13B2-02'nin kökü: ürünün çağırmadığı bir ucun davranışını tek
        başına test tanımlarsa, o test fail-open'ı şart koştuğunda uç
        kalıcı olarak fail-open olur.
        """
        yeni = sorted(set(akis_haritasi['yalniz_test'])
                      - YALNIZ_TESTIN_CAGIRDIGI_ROTALAR)
        assert not yeni, (
            'ürün yüzünün hiç çağırmadığı bir ucu YALNIZ test tanımlıyor: '
            f'{yeni}')

    def test_envanter_curumez(self, akis_haritasi):
        """Kapanan borç listede kalırsa, ileride açılan borcu affeder.

        Bir rota bekçi kazandıysa (ya da ürün onu çağırmaya başladıysa)
        envanterden ÇIKARILMALIDIR; ölü satır sessiz af demektir.
        """
        olu_a = sorted(UC_BEKCISI_OLMAYAN_URUN_ROTALARI
                       - set(akis_haritasi['bekcisiz']))
        olu_b = sorted(YALNIZ_TESTIN_CAGIRDIGI_ROTALAR
                       - set(akis_haritasi['yalniz_test']))
        assert not olu_a, (
            'UC_BEKCISI_OLMAYAN_URUN_ROTALARI ölü satır taşıyor (bu rotalar '
            f'artık uç üzerinden sınanıyor, listeden çıkarın): {olu_a}')
        assert not olu_b, (
            'YALNIZ_TESTIN_CAGIRDIGI_ROTALAR ölü satır taşıyor (ürün artık '
            f'bu rotaları çağırıyor ya da rota kalkmış): {olu_b}')


# ===========================================================================
# P10B4-14 — bit-özdeşlik referansı KİRLİ ağaçtan dondurulamaz
# ===========================================================================
#
# Ölçülen kusur (`once_p10b414.json`): ``tools/cfd_referans_dondur.py``
# dondurduğu referansın künyesine ``git status`` çıktısından türettiği
# bir "kirli mi" bilgisini yazıyor ama KİRLİYKEN DE donduruyor; dört
# referansın dördü de kirli ağaçtan donmuş. Künye gerçeği söylüyor,
# kapı yok — beyan çözüm değildir.
#
# Bu kulvarın sahası ``tests/**`` (ürün/araç kodu değil) ve ``tests/cfd``
# CFD kulvarının sahası; bu yüzden burada kurulan kilit ARACIN künye
# sözleşmesidir: dondurulmuş referanslar kendi kirlilik durumlarını
# YAYIMLAMAK ZORUNDADIR ve kirli bir referans ADIYLA sayılır. Aracın
# fail-closed'a çevrilmesi (kirliyken dondurmayı REDDETMEK) araç
# sahibinin işidir; envanter büyürse bu iddia kırmızıdır.

REFERANS_KOKU = KOK / 'data' / 'cfd_referans'

#: Kirli çalışma ağacından dondurulmuş, ADIYLA sayılan referanslar.
#: BÜYÜMESİ kırmızıdır: yeni bir referans temiz ağaçtan donmalıdır.
#: (D18 ölçümü: dördünün dördü de ``git_calisma_agaci_kirli: true``,
#: commit a8e03547.)
#:
#: ENVANTER BOŞALDI — ÖH D32 / fix-35b (15 Eylül 2026). D31 fea-cfd a1
#: (``d9003b57``, P10B4-14) dört referansı TEMİZ ağaçtan yeniden
#: dondurdu; diziler bit-özdeş kaldı, değişen yalnız künyedir. Bugünkü
#: ÖLÇÜM (``data/cfd_referans/*.npz`` meta_json, beş referansın beşi):
#: ``git_calisma_agaci_kirli: false``, ``git_kirli_dosya_sayisi: 0``,
#: ``git_kirli_dosyalar: []``, ``git_commit: 88e7926c``. Yani kirli
#: nüfus 4 -> 0.
#:
#: Satırlar SİLİNDİ, yorum satırına çevrilmedi: envanter TEK YÖNLÜ bir
#: mandaldır ve ölü satır sessiz aftır — bunu zaten
#: ``test_kirli_referans_envanteri_curumez`` ölçüyor ve bu kırmızıyı o
#: yaktı. Boş küme mandalı GEVŞETMEZ, EN SIKI hâline getirir:
#: ``test_kirli_referans_envanteri_buyumez`` artık kirli ağaçtan donmuş
#: TEK bir referansın doğduğu anda kırmızı yanar. Aracın fail-closed'a
#: çevrilmesi (kirliyken dondurmayı REDDETMEK) hâlâ araç sahibinin
#: borcudur; bu envanter onun yerini tutmaz, yalnız nüfusu sayar.
KIRLI_DONMUS_REFERANSLAR = frozenset()

#: P13B1-03 — bit-özdeşlik SÖZLEŞMESİ yalnız referansın üretildiği
#: platformda kurulabilir; başka platformda test TOLERANS dalına düşer.
#: D18 ölçümü: 4 referansın 4'ü de darwin/arm64. CI ubuntu koştuğu için
#: 1e-12 beyanı CI'da BİR KEZ bile sınanmıyor. Envanter ADIYLA yazılır;
#: yeni bir platform eklenirse (istenen yön) bu liste güncellenir.
REFERANS_PLATFORMLARI = frozenset({('darwin', 'arm64')})


def _referans_kunyeleri(okunamayan=None):
    """{referans adı: meta sözlüğü} — .npz içindeki ``meta_json``.

    ``okunamayan`` verilirse künyesi ÇÖZÜLEMEYEN referanslar oraya
    {ad: sebep} olarak yazılır. Bu kanal ÖH D32 / fix-35b'de açıldı ve
    sebebi ölçümdür: eski hâl künyesi bozuk (ya da hiç künyesi olmayan)
    bir ``.npz``yi sessizce ATLIYORDU, yani dosya envanterden düşüyordu.
    ``KIRLI_DONMUS_REFERANSLAR`` mandalı "kirli nüfus BÜYÜMESİN" der;
    kaybolan bir referansın kirliliği de kaybolduğu için mandal künye
    bozulmasına karşı fail-OPEN'dı. ÖLÇÜLDÜ (ters mutasyon #1, ilk
    deneme): ``euler_sok_60x12``in künyesine ``kirli: true`` yazıldığında
    JSON dtype genişliğini (U2072) aştı, kırpıldı, ``json.loads``
    ``ValueError`` verdi ve bekçi KIRMIZI YERİNE YEŞİL kaldı. Kanal
    açıldı ve ``test_referans_kunyesi_COZULEMEYEN_yok`` ile kapatıldı.
    """
    if not REFERANS_KOKU.exists():
        return {}
    import numpy as np
    kunye = {}
    for p in sorted(REFERANS_KOKU.glob('*.npz')):
        try:
            with np.load(p, allow_pickle=False) as z:
                if 'meta_json' not in z:
                    if okunamayan is not None:
                        okunamayan[p.stem] = 'meta_json anahtarı YOK'
                    continue
                ham = z['meta_json']
                kunye[p.stem] = json.loads(
                    ham.item() if hasattr(ham, 'item') else str(ham))
        except (OSError, ValueError) as hata:
            if okunamayan is not None:
                okunamayan[p.stem] = f'{type(hata).__name__}: {hata}'
            continue
    return kunye


def _kirli_mi(meta):
    for ad in ('git_calisma_agaci_kirli', 'git_dirty', 'dirty',
               'working_tree_dirty'):
        if ad in meta:
            return bool(meta[ad])
    return None


class TestP10B414ReferansKirliligi:
    """Referansın KÜNYESİ değil, KAPISI ölçülür.

    ``tools/cfd_referans_dondur.py`` kirliliği künyeye yazıyor ama
    kirliyken dondurmayı REDDETMİYOR; bekçi de künyeyi denetlemiyordu.
    Bu kulvarın sahası ``tests/**`` ve ``tests/cfd`` CFD kulvarının
    sahası olduğu için burada kurulan kilit ENVANTERDİR: bugünkü dört
    kirli referans adıyla sayılır, BEŞİNCİSİ kırmızıdır.
    """

    def test_referans_envanteri_bosalmadi(self):
        kunye = _referans_kunyeleri()
        assert len(kunye) >= 4, (
            f'CFD bit-özdeşlik referansı envanteri boşaldı: {sorted(kunye)}')

    def test_referans_kunyesi_COZULEMEYEN_yok(self):
        """Künyesi çözülemeyen referans envanterden DÜŞMEZ, KIRMIZI yakar.

        Fail-closed: ``_referans_kunyeleri`` eskiden bozuk künyeyi sessizce
        atlıyordu; atlanan dosya kirlilik sayımından da düşüyordu. Bu bekçi
        o kapıyı kapatır — sevk edilen her ``.npz`` künyesini ÇÖZÜLEBİLİR
        biçimde taşımak zorundadır.
        """
        okunamayan = {}
        _referans_kunyeleri(okunamayan)
        assert okunamayan == {}, (
            'CFD referansının künyesi çözülemiyor (envanterden sessizce '
            f'düşerdi): {okunamayan}')

    def test_referans_kunyesi_kirlilik_yayimlar(self):
        """Her dondurulmuş referans kendi kirlilik durumunu YAYIMLAR."""
        kunye = _referans_kunyeleri()
        eksik = sorted(a for a, v in kunye.items() if _kirli_mi(v) is None)
        assert not eksik, (
            f'referans künyesi kirlilik durumunu yayımlamıyor: {eksik}')

    def test_kirli_referans_envanteri_buyumez(self):
        """Yeni bir referans KİRLİ ağaçtan dondurulamaz (ÖK-22)."""
        kunye = _referans_kunyeleri()
        kirli = {a for a, v in kunye.items() if _kirli_mi(v)}
        yeni = sorted(kirli - KIRLI_DONMUS_REFERANSLAR)
        assert not yeni, (
            'KİRLİ çalışma ağacından dondurulmuş YENİ bit-özdeşlik '
            f'referansı: {yeni} — araç kirliyken dondurmayı reddetmeli')

    def test_kirli_referans_envanteri_curumez(self):
        """Temiz ağaçtan yeniden dondurulan referans listede kalamaz."""
        kunye = _referans_kunyeleri()
        kirli = {a for a, v in kunye.items() if _kirli_mi(v)}
        olu = sorted(KIRLI_DONMUS_REFERANSLAR - kirli)
        assert not olu, (
            'KIRLI_DONMUS_REFERANSLAR ölü satır taşıyor (bu referanslar '
            f'artık temiz ağaçtan donmuş, listeden çıkarın): {olu}')

    def test_referans_platform_evreni_adiyla_yazili(self):
        """P13B1-03: bit-özdeşlik sözleşmesi hangi platformlarda kurulu?

        Referans başka platformda üretilmemişse, o platformdaki koşum
        1e-12 bit-özdeşliğini DEĞİL tolerans dalını sınar. Bu iddia,
        beyanın gerçekle uyuştuğunu ölçer; yeni bir platform eklenmesi
        (CI'nın kendi referansını üretmesi) istenen yöndür ve listeyi
        güncellemeyi gerektirir.
        """
        kunye = _referans_kunyeleri()
        gercek = {(str(v.get('platform')), str(v.get('machine')))
                  for v in kunye.values()}
        assert gercek == set(REFERANS_PLATFORMLARI), (
            'CFD referans platform evreni beyanla uyuşmuyor: '
            f'gerçek={sorted(gercek)} beyan={sorted(REFERANS_PLATFORMLARI)}')


# ===========================================================================
# P13B4-10 — kampanya kritiklerinin bekçi kapsamı ENVANTERİ kilitlenir
# ===========================================================================
#
# Kalemin başlığı: "kampanya kritiklerinin 44'ünde kusuru tanımlayan
# sembolü ANAN tek test yok". Bu bir ÜRÜN kusuru değil, kapsam
# envanteridir ve P13'ün kendi ölçütüyle (B4-repro-13.py) üç kademelidir:
#
#   D0 BEKÇİSİZ  kritiğin ürün DOSYASINI hiçbir test anmıyor
#   D1 DOLAYLI   dosya anılıyor ama kritiğin SEMBOLÜ anılmıyor
#   D2 ADAY      sembol bir testte geçiyor (kilit demek DEĞİL, aday)
#
# D18 ölçümü (`once_p13b410.json`, P13'ün betiği bu ağaca çevrilerek
# yeniden koşuldu):  D0 = 0,  D1 = 30,  D2 = 13,  ?dosya-yok = 11.
# P13'ün 24 Ağu ölçümüne göre D0 tükenmiş; kalan borç D1'dir.
#
# NEDEN BU DALGADA 20 BEKÇİ YAZILMADI (dürüst rapor): D1'deki 30 kritiğin
# her biri BUGÜN AÇIK bir ürün kusurudur (uydurma varsayılan, ters dönen
# uyarı, yanlış künye, çizilmeyen blok). Sembolü ANAN bir test yazmanın
# iki yolu var ve ikisi de doktrine aykırı: (a) bugünkü kusurlu davranışı
# iddia etmek = KUSURU KORUYAN BEKÇİ (ÖK-05/doktrin 3 yasak), (b) doğru
# davranışı iddia etmek = ürün onarılmadan KIRMIZI test. Ürün onarımları
# başka kulvarların sahasında (hrma/static/js, hrma/templates, hrma/export,
# hrma/data). Bu kulvarın sahasında (tests/**) doktrine uyan tek kazanım
# envanterin KİLİTLENMESİDİR: kapsam geriye gidemez.

_P13_KRITIK_TABLOSU = (KOK / 'docs' / 'scofield' / 'raw' / 'P13' /
                       'B4-cikti-12-kritikler.json')
_P13_SEMBOL = re.compile(r'`([A-Za-z_][\w./\-]{3,})`')

#: D18'de ölçülen D1 kümesi (dosya anılıyor, SEMBOL anılmıyor).
#: BÜYÜMESİ kırmızıdır: bir kritik D2'den D1'e düşemez.
KRITIK_SEMBOLSUZ = frozenset({
    'P7B3-16', 'P7B3-20', 'P9B1-02', 'P9B1-03', 'P9B2-01', 'P9B2-07',
    'P9B2-25', 'P9B3-01', 'P9B3-09', 'P9B4-01', 'P9B4-03', 'P9B4-04',
    'P9B4-08', 'P9B4-10', 'P9B5-01', 'P10B1-06', 'P10B1-07', 'P10B2-04',
    'P10B4-01', 'P11B1-01', 'P11B3-01', 'P11B3-02', 'P11B4-11',
    'P12aB2-01', 'P12bB1-01', 'P12bB1-03', 'P12bB1-20', 'P12bB2-01',
    'P12bB2-06', 'P12bB3-01',
})

#: Kayıtta ürün dosyası olmayan kritikler (kademe ölçülemez).
#: BÜYÜMESİ kırmızıdır: yeni bir kritik dosyasız kaydedilemez.
KRITIK_DOSYASIZ = frozenset({
    'P4B1-01', 'P4B4-01', 'P5B1-01', 'P5B2-01', 'P5B2-02', 'P5B2-03',
    'P5B4-38', 'P11B2-01', 'P11B2-02', 'P12bB1-02', 'P12bB2-05',
})


def _test_govdeleri():
    parca = []
    for p in sorted(TESTS_KOK.rglob('*.py')):
        if '__pycache__' in p.parts:
            continue
        parca.append(p.read_text(encoding='utf-8', errors='replace'))
    return '\n'.join(parca)


@pytest.fixture(scope='module')
def kritik_kademeleri():
    veri = json.loads(kanit_gerekli(_P13_KRITIK_TABLOSU).read_text(encoding='utf-8'))
    yazi = _test_govdeleri()
    kademe = {}
    for kid, k in veri.items():
        dosya = k.get('dosya', '')
        modul = Path(dosya).stem if dosya else ''
        if not modul:
            kademe[kid] = '?dosya-yok'
            continue
        semboller = [s for s in _P13_SEMBOL.findall(k['baslik'])
                     if not s.endswith(('.py', '.js', '.html'))
                     and '/' not in s]
        if modul not in yazi:
            kademe[kid] = 'D0'
        elif not any(s in yazi for s in semboller):
            kademe[kid] = 'D1'
        else:
            kademe[kid] = 'D2'
    return kademe


class TestP13B410KritikBekciKapsami:

    def test_kritik_evreni_bosalmadi(self, kritik_kademeleri):
        """Tablo boşalırsa aşağıdaki iddialar totolojiye döner."""
        assert len(kritik_kademeleri) >= 54, (
            f'kampanya kritik tablosu küçüldü: {len(kritik_kademeleri)}')

    def test_urun_dosyasi_hic_anilmayan_kritik_kalmadi(self,
                                                      kritik_kademeleri):
        """D0 tükendi ve geri gelemez (ÖK-22).

        P13 ölçümünde D0 vardı; D15-D17 dalgaları kapattı. Bir kritiğin
        ürün dosyasını HİÇBİR testin anmaması, o dosyanın tümüyle
        bekçisiz olduğu anlamına gelir.
        """
        d0 = sorted(k for k, v in kritik_kademeleri.items() if v == 'D0')
        assert not d0, f'ürün dosyası hiçbir testte anılmayan kritik: {d0}'

    def test_sembolsuz_kritik_kumesi_buyumez(self, kritik_kademeleri):
        """Bir kritik D2'den D1'e DÜŞEMEZ.

        Sembolü anan bekçi silinir ya da yeniden adlandırılırsa kapsam
        geriye gider; bu iddia o gerilemeyi kırmızıya çevirir.
        """
        d1 = {k for k, v in kritik_kademeleri.items() if v == 'D1'}
        yeni = sorted(d1 - KRITIK_SEMBOLSUZ)
        assert not yeni, (
            'kusuru tanımlayan sembolü anan bekçisini KAYBEDEN kritik: '
            f'{yeni}')

    def test_dosyasiz_kritik_kumesi_buyumez(self, kritik_kademeleri):
        """Ürün dosyası kaydedilmemiş yeni kritik eklenemez."""
        dosyasiz = {k for k, v in kritik_kademeleri.items()
                    if v == '?dosya-yok'}
        yeni = sorted(dosyasiz - KRITIK_DOSYASIZ)
        assert not yeni, (
            'ürün dosyası kaydedilmemiş (kademesi ölçülemeyen) yeni '
            f'kritik: {yeni}')

    def test_kapsam_envanteri_curumez(self, kritik_kademeleri):
        """Sembol bekçisi KAZANAN kritik envanterde kalamaz.

        Ölü satır, ileride gerçekten kapsam kaybeden bir kritiği sessizce
        affeder. Bir kritik D1'den D2'ye çıktığında bu liste GÜNCELLENİR —
        kalemin kapanış yönü budur.
        """
        d1 = {k for k, v in kritik_kademeleri.items() if v == 'D1'}
        dosyasiz = {k for k, v in kritik_kademeleri.items()
                    if v == '?dosya-yok'}
        olu_d1 = sorted(KRITIK_SEMBOLSUZ - d1)
        olu_dz = sorted(KRITIK_DOSYASIZ - dosyasiz)
        assert not olu_d1, (
            'KRITIK_SEMBOLSUZ ölü satır taşıyor (bu kritikler artık '
            f'sembolünü anan bir bekçiye sahip, listeden çıkarın): {olu_d1}')
        assert not olu_dz, (
            f'KRITIK_DOSYASIZ ölü satır taşıyor: {olu_dz}')
