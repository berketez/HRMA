"""ÖH D23 · altyapi a1 — defter P10B4-16 bekçisi.

Kalem: ``wiring_map``/``shake`` ölçüm altyapısı ürünün 3 ucunda koşuyordu,
üründe 80 POST ucu var (kapsam %3,8) ve sarsım matrisi bekçiye YALNIZ
``/calculate`` üzerinden bağlıydı (1/105). Kalemin engeli dört dalga boyunca
aynıydı: ölçüm gövdesi her uç için GEÇERLİ bir taban yük ister, ağaçta merkezî
bir uç-yükü kataloğu YOKTU.

Bu bekçi kataloğun kendisini kilitler:

1. Katalog ürünün BÜTÜN POST uçlarını taşır (yeni uç eklenirse KIRMIZI).
2. Ölçülemeyen her uç adlı bir sınıfa ve GEREKÇEYE bağlıdır (sessiz atlama
   yok); gerekçesiz kayıt kurulamaz.
3. Kataloğun taban yükleri CANLI 200 verir (yük bayatlarsa KIRMIZI).
4. Sarsım matrisi kataloğun uçlarında gerçekten koşar ve harita kapsamını
   katalogtan alır (kapsam sessizce daralamaz).

Kanıt: ``docs/scofield/raw/OH/D23/altyapi/a1/`` (once/sonra JSON, mutasyon,
rapor.md).
"""

import importlib.util
import json
import pathlib

import pytest

from tests.support import shake, uc_katalogu

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Ana CI işinde build123d BİLEREK kurulu değil (tests.yml). O ortamda
#: export-step ucu ürün davranışı olarak 501 ``step_backend_unavailable``
#: döner; 200 beklemek gece koşusunu 16-18 Eki'de üç kez kırmızı yaptı.
STEP_VAR = importlib.util.find_spec('build123d') is not None


def _taban_yuk_uclari():
    """Ölçülebilir uçlar; arka ucu (``arka_uc``) gereken uç o paket yokken
    STEP devri gerekçesiyle atlanır ve ``step-export`` işinde koşar."""
    for yol in uc_katalogu.olculebilir_uclar():
        if uc_katalogu.kayit(yol).arka_uc == 'build123d':
            yield pytest.param(yol, marks=pytest.mark.skipif(
                not STEP_VAR,
                reason='build123d kurulu değil (STEP üretimi atlanır) — '
                       'düğüm step-export işinde koşar'))
        else:
            yield yol

#: Sarsım matrisinin bekçi içinde ucu ucuna koşturulduğu uçlar.
#:
#: Katalogdaki 66 ucun tamamını her pytest koşumunda sarsmak dakikalar sürer
#: (araç işi: ``python3 tools/wiring_map.py --uclar``). Bekçi ölçüm ZİNCİRİNİ
#: kilitler: katalog -> şartname -> shake -> rapor. Uçlar hızlı olduğu ÖLÇÜLEN
#: uçlardan seçildi; kapsamın kendisi (3) yukarıdaki (1)-(3) maddeleriyle
#: 80/80 olarak zaten kilitli.
SARSILAN_UCLAR = (
    '/api/altitude-to-pressure',
    '/api/flow-analysis',
    '/analyze_structural_safety',
)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def app_nesnesi():
    from hrma.app import app
    return app


class TestKatalogKapsami:
    """Katalog ürünün POST uçlarının tamamını taşır (fail-closed)."""

    def test_katalog_urunun_butun_post_uclarini_tasir(self, app_nesnesi):
        rapor = uc_katalogu.kapsam_raporu(app_nesnesi)
        assert rapor['eksik'] == [], (
            'Katalogda olmayan POST ucu var — yeni uç kataloglanmalı '
            '(fail-closed: sessiz atlama yok): %s' % rapor['eksik'])
        assert rapor['fazla'] == [], (
            'Üründe olmayan uç katalogda duruyor (katalog bayat): %s'
            % rapor['fazla'])
        assert rapor['katalog_kayit_sayisi'] == rapor['urun_post_sayisi']

    def test_kapsam_uc_uctan_cok_daha_genis(self, app_nesnesi):
        """Kalemin ölçtüğü taban 3 uçtu; gerileme bu sayının altına düşmektir.

        Taban ölçümü (``once.json``): ``wiring_map.PAGES`` = 3 uç, POST
        uçlarının %3,8'i. Eşik ölçülmüş sayının kendisidir, yuvarlak bir
        temenni değil.
        """
        olculebilir = uc_katalogu.olculebilir_uclar()
        assert len(olculebilir) >= 60, (
            'Ölçülebilir uç sayısı %d — D23 ölçümü 66 idi, kapsam daralmış'
            % len(olculebilir))
        post = uc_katalogu.post_uclari(app_nesnesi)
        assert len(olculebilir) / len(post) > 0.75

    def test_her_olculemez_kayit_gerekceli(self):
        for yol, kayit in uc_katalogu.kayitlar().items():
            assert kayit.sinif in uc_katalogu.SINIFLAR, yol
            if kayit.sinif != 'olculebilir':
                assert kayit.gerekce.strip(), (
                    '%s: %s sınıfı gerekçesiz — beyan çözüm değildir ama '
                    'gerekçesiz atlama hiç değildir' % (yol, kayit.sinif))

    def test_gerekcesiz_kayit_kurulamaz(self):
        """Fail-closed sözleşme kaydın KENDİSİNDE, çağıran iyi niyetinde değil."""
        with pytest.raises(ValueError) as e1:
            uc_katalogu.UcKaydi(yol='/x', sinif='yan_etkili')
        assert 'gerekcesiz' in str(e1.value)
        with pytest.raises(ValueError) as e2:
            uc_katalogu.UcKaydi(yol='/x', sinif='olculebilir')
        assert 'yuksuz' in str(e2.value)
        with pytest.raises(ValueError) as e3:
            uc_katalogu.UcKaydi(yol='/x', sinif='uydurma-sinif')
        assert 'bilinmeyen sinif' in str(e3.value)

    def test_bilinmeyen_uc_sessizce_bos_yuk_donmez(self):
        with pytest.raises(KeyError) as e1:
            uc_katalogu.kayit('/api/hic-olmayan-uc')
        assert 'kataloglanmali' in str(e1.value)
        with pytest.raises(KeyError) as e2:
            uc_katalogu.taban_yuk('/api/hic-olmayan-uc')
        assert 'fail-closed' in str(e2.value)

    def test_olculemeyen_ucta_taban_yuk_hata_yukseltir(self):
        """Boş yük gönderilse uç 4xx döner ve BÜTÜN alanlar yalancı-ölü olurdu."""
        olculemez = [y for y, k in uc_katalogu.kayitlar().items()
                     if k.sinif != 'olculebilir']
        assert olculemez, 'sınıf ayrımı kayboldu'
        for yol in olculemez:
            with pytest.raises(ValueError) as exc:
                uc_katalogu.taban_yuk(yol)
            # Hata GEREKÇEYİ taşır: "atlandı" demek yetmez, NEDEN atlandığı
            # çağıranın eline geçer.
            assert uc_katalogu.kayit(yol).gerekce[:30] in str(exc.value), yol


class TestTabanYuklerCanli:
    """Katalog yükleri CANLI 200 verir — yük bayatlarsa bekçi kırmızı."""

    def test_uc_motor_sayfasinin_yuku_tek_kaynaktan_gelir(self):
        """Motor sayfalarının tabanı kataloğa KOPYALANMAZ, oradan okunur."""
        hibrit = uc_katalogu.taban_yuk('/calculate')
        from tests.test_field_wiring_layer_b import HYBRID_BASE
        assert hibrit == dict(HYBRID_BASE)
        for yol in ('/calculate_solid', '/calculate_liquid'):
            assert uc_katalogu.taban_yuk(yol), yol

    # ÖH D24 / OH-D23-23 — CI İŞ BÖLÜMÜ İŞARETİ.
    #
    # Bu tek test 66 ucu canlı ``test_client`` ile çağırır ve koşumun
    # ölçülen en pahalı kalemidir (süre kanıtı:
    # docs/scofield/raw/OH/D24/altyapi/a2/once_ohd2323.json). Kapı
    # KALDIRILMADI, TAŞINDI: push/PR koşumu onu ``-m 'not agir_canli_uc'``
    # ile SEÇMEZ, gecelik iş ve yayın kapısı koşar. Seçme (deselect)
    # bilerek atlama (skip) yerine kullanılıyor — atlanan test junit'e
    # 'skipped' yazılıp atlama bütçesi kapısını bozardı; seçilmeyen test
    # rapora hiç girmez.
    #
    # Kardeşi ``test_uc_motor_sayfasinin_yuku_tek_kaynaktan_gelir`` UCUZ
    # olduğu için işaretlenmedi: katalog tek-kaynak sözleşmesi her
    # koşumda sınanmaya devam eder.
    @pytest.mark.agir_canli_uc
    @pytest.mark.parametrize('yol', list(_taban_yuk_uclari()))
    def test_taban_yuk_200_veriyor(self, client, yol):
        kayit = uc_katalogu.kayit(yol)
        yanit = client.post(kayit.cagri_yolu, json=uc_katalogu.taban_yuk(yol),
                            headers=uc_katalogu.headers())
        assert yanit.status_code == 200, (
            '%s taban yükü HTTP %d verdi — katalog bayat, sarsım matrisi bu '
            'uçta HER alanı yalancı-ölü sayardı (kaynak: %s)'
            % (yol, yanit.status_code, kayit.kaynak))


class TestSarsimZinciri:
    """Katalog -> şartname -> shake -> rapor zinciri gerçekten koşuyor."""

    @pytest.mark.parametrize('yol', SARSILAN_UCLAR)
    def test_sarsim_matrisi_ucta_kosuyor(self, client, yol):
        import tools.wiring_map as wm
        rapor = wm.measure_endpoint(client, yol)
        olculen = (len(rapor.live_inputs) + len(rapor.dead_inputs)
                   + len(rapor.echo_only_inputs) + len(rapor.unmeasurable))
        assert olculen >= 1, '%s: hiçbir alan ölçülmedi' % yol
        assert rapor.baseline_leaf_count > 0

    def test_alan_speclari_taban_yukten_turer(self):
        specs = uc_katalogu.alan_speclari('/api/flow-analysis')
        adlar = {s.name for s in specs}
        yuk = uc_katalogu.taban_yuk('/api/flow-analysis')
        beklenen = {a for a, d in yuk.items()
                    if isinstance(d, (bool, int, float, str))}
        assert adlar == beklenen
        assert all(isinstance(s, shake.FieldSpec) for s in specs)

    def test_ic_anahtarlar_beyan_ediliyor(self):
        """Sarsılmayan iç anahtar SAKLANMAZ; sayısı beyan edilir."""
        ic = uc_katalogu.ic_anahtarlar('/api/export-cad')
        assert 'motor_data' in ic and ic['motor_data'] >= 1


class TestHaritaKapsamKatalogtan:
    """``wiring_map`` kapsamını katalogtan alır; sessizce daralamaz."""

    def test_wiring_map_katalogu_kullaniyor(self):
        kaynak = (ROOT / 'tools' / 'wiring_map.py').read_text(encoding='utf-8')
        assert 'uc_katalogu' in kaynak, (
            'wiring_map kataloğu kullanmıyor — kapsam yine 3 uçta kalır')
        import tools.wiring_map as wm
        assert hasattr(wm, 'measure_endpoint')
        assert hasattr(wm, 'measure_endpoints')
        assert hasattr(wm, 'uc_kapsami')

    def test_measure_endpoints_varsayilan_kapsami_katalogtan_gelir(self,
                                                                    monkeypatch):
        """Haritanın varsayılan uç kümesi = kataloğun ölçülebilirleri.

        Kapsamın sessizce daralmasının en kolay yolu bu satırı üç sayfaya geri
        çevirmektir; bekçi tam olarak onu görür. (Sahte ölçüm nesnesi test
        altyapısıdır — ürün verisi değil.)
        """
        import tools.wiring_map as wm

        class _SahteRapor:
            baseline_leaf_count = 1
            live_inputs: dict = {}
            dead_inputs: list = []
            echo_only_inputs: list = []
            unmeasurable: dict = {}
            constant_outputs: list = []

        cagrilan = []

        def _sahte_olc(_client, yol, probe_all_options=False):
            cagrilan.append(yol)
            return _SahteRapor()

        monkeypatch.setattr(wm, 'measure_endpoint', _sahte_olc)
        wm.measure_endpoints(client=None)
        assert cagrilan == uc_katalogu.olculebilir_uclar(), (
            'harita varsayılan olarak katalogdaki uçları ölçmüyor — kapsam '
            'daralmış')

    def test_uc_kapsami_raporu_butun_uclari_satirlar(self, app_nesnesi):
        import tools.wiring_map as wm
        kapsam = wm.uc_kapsami(app_nesnesi)
        assert len(kapsam['satirlar']) == kapsam['urun_post_sayisi']
        assert all(s['sinif'] != 'KATALOGDA YOK' for s in kapsam['satirlar'])
        # Ölçülemeyen satırın gerekçesi BOŞ olamaz.
        for s in kapsam['satirlar']:
            if s['sinif'] not in ('olculebilir',):
                assert s['gerekce'].strip(), s['yol']

    def test_kapsam_sayfasi_olculemeyeni_temiz_gostermez(self, app_nesnesi):
        import tools.wiring_map as wm
        kapsam = wm.uc_kapsami(app_nesnesi)
        html = wm.build_uc_kapsami_html(kapsam, '2026-01-01 00:00')
        assert 'kataloglanmadı' in html
        for yol, kayit in uc_katalogu.kayitlar().items():
            if kayit.sinif == 'kataloglanmadi':
                assert yol in html, yol


class TestYukDosyasi:
    """Yükler ölçüm verisidir: JSON'da durur, kodda değil."""

    def test_yuk_dosyasi_katalogla_tutarli(self):
        with uc_katalogu.YUK_DOSYASI.open(encoding='utf-8') as fh:
            yukler = json.load(fh)
        yuklu = {y for y, k in uc_katalogu.kayitlar().items()
                 if k.yuk is not None}
        assert set(yukler) == yuklu, (
            'uc_yukleri.json ile katalog ayrıştı: %s'
            % sorted(set(yukler) ^ yuklu))
        for yol, yuk in yukler.items():
            assert isinstance(yuk, dict) and yuk, yol

    def test_taban_yuk_kopya_dondurur(self):
        """Çağıran yükü kirletirse sonraki ölçüm bozulurdu."""
        a = uc_katalogu.taban_yuk('/api/flow-analysis')
        a['chamber_pressure'] = -12345
        b = uc_katalogu.taban_yuk('/api/flow-analysis')
        assert b['chamber_pressure'] != -12345
